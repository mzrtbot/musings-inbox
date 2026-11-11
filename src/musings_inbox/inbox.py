"""musings-inbox: local-first life-log / inspiration inbox for AI agents.

File-based, vendor-neutral memory: every entry is plain Markdown on disk,
timestamped only from a real clock read, appended with a trailing-newline
check, and verified by read-back + fingerprint. No database, no cloud lock-in.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

CATEGORIES = {
    "fact": "facts.md",
    "preference": "preferences.md",
    "experience": "experience.md",
    "material": "materials.md",
}
INDEX_NAME = "index.md"
# Every file the inbox is ever allowed to touch. Category arguments map
# through CATEGORIES into this set; _file() refuses anything else, so a
# hostile category/filename can never become a path on disk.
KNOWN_FILES = {INDEX_NAME, *CATEGORIES.values()}
# Lines written by Inbox.add, e.g.:
# - [20261023-01] 2026-10-23 09:30 — The workshop opens at nine.
_ENTRY_LINE = re.compile(r"^-\s\[(\d{8}-\d+)\]\s(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2})\s—\s(.*)$")
# Lines written by Inbox.export(format="markdown"), e.g.:
# - [20261023-01] 2026-10-23 09:30 [fact] The workshop opens at nine.
_EXPORT_LINE = re.compile(r"^-\s\[(\d{8}-\d+)\]\s(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2})\s\[([A-Za-z]+)\]\s(.*)$")
# Index rows written by Inbox.add, e.g.:
# | 20261023-01 | 2026-10-23 09:30 | fact | The workshop opens at nine. |
_INDEX_ROW = re.compile(
    r"^\| (\d{8}-\d+) \| (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) \| ([A-Za-z]+) \| (.*) \|$"
)
_INDEX_HEADER = "| ID | Time | Category | Summary |"
_INDEX_SEPARATOR = "|---|---|---|---|"
# so '#灵感' and '#inbox' both match; '#' must not be glued to a preceding
# word character, so "a#b" is not a tag). The '#' of a Markdown header
# ("# Title") followed by a space does not match either.
_TAG_RE = re.compile(r"(?<!\w)#(\w+)")


def parse_tags(text: str) -> list[str]:
    """Extract #tags from entry text.

    Tags are returned lowercased, deduplicated, in order of first
    appearance. A bare '#' with no word characters after it (or glued
    to a preceding word, as in "a#b") yields nothing.
    """
    seen: set[str] = set()
    tags: list[str] = []
    for match in _TAG_RE.finditer(text):
        tag = match.group(1).lower()
        if tag not in seen:
            seen.add(tag)
            tags.append(tag)
    return tags


def _normalize_tag(tag: str) -> str:
    """Accept 'trip' or '#trip'; normalize to the lowercase bare tag name."""
    return tag.lstrip("#").strip().lower()


def _validate_date(value: str) -> None:
    """Raise ValueError unless ``value`` is a valid YYYY-MM-DD date."""
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"invalid date: {value!r} (expected YYYY-MM-DD)") from None


def _parse_timestamp(value: str) -> datetime:
    """Parse a ``YYYY-MM-DD HH:MM`` timestamp, or raise ValueError."""
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M")
    except ValueError:
        raise ValueError(f"invalid timestamp: {value!r} (expected YYYY-MM-DD HH:MM)") from None


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _ensure_trailing_newline(path: Path) -> None:
    """Rule learned the hard way: check the file tail before appending.

    If the file does not end with a newline, add one first, so the new
    entry never glues onto the previous line.
    """
    data = path.read_bytes()
    if data and not data.endswith(b"\n"):
        with path.open("ab") as fh:
            fh.write(b"\n")


def _today_id(index: Path, now: datetime) -> str:
    prefix = now.strftime("%Y%m%d")
    count = 0
    if index.exists():
        count = len(re.findall(rf"{prefix}-\d+", index.read_text(encoding="utf-8")))
    return f"{prefix}-{count + 1:02d}"


@dataclass
class Entry:
    entry_id: str
    category: str
    text: str
    timestamp: str
    tags: list[str] | None = None

    def __post_init__(self) -> None:
        if self.tags is None:
            self.tags = parse_tags(self.text)


@dataclass
class Stats:
    total: int
    by_category: dict[str, int]
    earliest: Entry | None
    latest: Entry | None
    total_chars: int
    by_month: dict[str, int]


@dataclass
class ImportResult:
    imported: list[Entry]
    duplicates: int
    dry_run: bool = False


@dataclass
class DoctorIssue:
    severity: str  # "error" | "warning"
    check: str
    message: str


@dataclass
class DoctorReport:
    ok: bool
    issues: list[DoctorIssue]
    fingerprints: dict[str, str]


@dataclass
class BackupResult:
    path: Path
    created: str
    fingerprints: dict[str, str]
    entries: int


@dataclass
class RestoreResult:
    restored: list[Entry]
    fingerprints: dict[str, str]
    dry_run: bool = False


BACKUP_MANIFEST = "manifest.json"
BACKUP_FORMAT = "musings-inbox-backup"
BACKUP_FORMAT_VERSION = 1


def _parse_import_json(raw: str) -> list[tuple[str, str, datetime]]:
    """Parse a JSON import file (the shape :meth:`Inbox.export` writes).

    The file must be a JSON array of objects with ``category`` (a known
    category), ``text`` (non-empty), and ``timestamp`` (``YYYY-MM-DD
    HH:MM``). ``entry_id`` is accepted when present but ignored: imported
    entries always get fresh IDs. Every problem is collected and reported
    together, so a bad file fails as a whole instead of importing halfway.
    """
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON import file: {exc}") from None
    if not isinstance(payload, list):
        raise ValueError("JSON import file must contain a list of entries")
    candidates: list[tuple[str, str, datetime]] = []
    errors: list[str] = []
    for pos, item in enumerate(payload):
        if not isinstance(item, dict):
            errors.append(f"entry {pos}: expected an object, got {type(item).__name__}")
            continue
        category = item.get("category")
        text = item.get("text")
        stamp = item.get("timestamp")
        if category not in CATEGORIES:
            errors.append(
                f"entry {pos}: unknown category: {category!r} (choose from {sorted(CATEGORIES)})"
            )
            continue
        if not isinstance(text, str) or not text.strip():
            errors.append(f"entry {pos}: entry text must not be empty")
            continue
        if not isinstance(stamp, str):
            errors.append(f"entry {pos}: timestamp must be a string, got {type(stamp).__name__}")
            continue
        try:
            when = _parse_timestamp(stamp)
        except ValueError as exc:
            errors.append(f"entry {pos}: {exc}")
            continue
        candidates.append((category, text.strip(), when))
    if errors:
        raise ValueError("invalid import file:\n" + "\n".join(errors))
    return candidates


def _parse_import_markdown(raw: str, category: str | None) -> list[tuple[str, str, datetime]]:
    """Parse a Markdown import file: export output or a raw category file.

    Accepted lines are the ``export`` Markdown lines
    (``- [ID] timestamp [category] text``) and, when ``category`` is
    given, raw category-file lines (``- [ID] timestamp — text``). Blank
    lines, ``#`` headers, and the ``export`` header lines (``total: N``,
    ``no entries``) are skipped. Any other line is a format error, and
    all errors are reported together so a bad file fails as a whole.
    """
    candidates: list[tuple[str, str, datetime]] = []
    errors: list[str] = []
    for lineno, ln in enumerate(raw.splitlines(), start=1):
        stripped = ln.strip()
        if (
            not stripped
            or stripped.startswith("#")
            or stripped == "no entries"
            or re.fullmatch(r"total: \d+", stripped)
        ):
            continue
        cat: str | None = None
        text: str | None = None
        stamp: str | None = None
        match = _EXPORT_LINE.match(ln)
        if match is not None:
            _entry_id, stamp, cat, text = match.groups()
            if cat not in CATEGORIES:
                errors.append(
                    f"line {lineno}: unknown category: {cat!r} (choose from {sorted(CATEGORIES)})"
                )
                continue
        else:
            match = _ENTRY_LINE.match(ln)
            if match is None:
                errors.append(f"line {lineno}: unrecognized line: {ln!r}")
                continue
            if category is None:
                errors.append(
                    f"line {lineno}: category-file line needs --category "
                    "(the file has no [category] on its lines)"
                )
                continue
            _entry_id, stamp, text = match.groups()
            cat = category
        try:
            when = _parse_timestamp(stamp)
        except ValueError as exc:
            errors.append(f"line {lineno}: {exc}")
            continue
        if not text.strip():
            errors.append(f"line {lineno}: entry text must not be empty")
            continue
        candidates.append((cat, text.strip(), when))
    if errors:
        raise ValueError("invalid import file:\n" + "\n".join(errors))
    return candidates


class Inbox:
    def __init__(self, root: str | Path):
        if root is None or not str(root).strip():
            raise ValueError("inbox root must not be empty")
        p = Path(root).expanduser()
        # Symlink guard: no component of the existing root path may be a
        # symlink, otherwise files could silently land outside the visible
        # tree (e.g. --root pointing at a link into /etc or another inbox).
        for existing in (p, *p.parents):
            if existing.is_symlink():
                raise ValueError(f"refusing symlinked path in inbox root: {existing}")
        resolved = p.resolve()
        # Traversal guard: a relative --root must stay inside the working
        # directory; ".." segments that climb above it are rejected.
        # Absolute roots are the caller's explicit choice and are kept.
        if not p.is_absolute():
            try:
                resolved.relative_to(Path.cwd())
            except ValueError:
                raise ValueError(
                    f"relative inbox root escapes the working directory: {root!r}"
                ) from None
        self.root = p
        self._root_abs = resolved

    def _file(self, name: str) -> Path:
        """Return the path of a whitelisted inbox file, guarded.

        ``name`` must be one of the fixed inbox filenames (the four
        category files plus the index). The resolved path must stay
        inside the resolved inbox root and must not be a symlink — so a
        swapped-in link can never redirect a write outside the inbox.
        Violations raise ``ValueError`` (bad name) or ``IOError``
        (escape attempt / symlink).
        """
        if name not in KNOWN_FILES:
            raise ValueError(f"unexpected inbox filename: {name!r} (known: {sorted(KNOWN_FILES)})")
        p = self.root / name
        if p.is_symlink():
            raise IOError(f"refusing to follow symlink: {p}")
        resolved = p.resolve()
        try:
            resolved.relative_to(self._root_abs)
        except ValueError:
            raise IOError(f"inbox file escapes the inbox root: {p}") from None
        return p

    def init(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        for filename in CATEGORIES.values():
            p = self._file(filename)
            if not p.exists():
                title = filename.removesuffix(".md").title()
                p.write_text(f"# {title}\n", encoding="utf-8")
        index = self._file(INDEX_NAME)
        if not index.exists():
            index.write_text("# Index\n\n| ID | Time | Category | Summary |\n|---|---|---|---|\n", encoding="utf-8")

    def add(self, category: str, text: str, now: datetime | None = None) -> Entry:
        if category not in CATEGORIES:
            raise ValueError(f"unknown category: {category} (choose from {sorted(CATEGORIES)})")
        text = text.strip()
        if not text:
            raise ValueError("entry text must not be empty")
        self.init()
        now = now or datetime.now()  # the only permitted time source: a real clock read
        entry_id = _today_id(self._file(INDEX_NAME), now)
        timestamp = now.strftime("%Y-%m-%d %H:%M")
        target = self._file(CATEGORIES[category])
        _ensure_trailing_newline(target)
        line = f"- [{entry_id}] {timestamp} — {text}\n"
        with target.open("a", encoding="utf-8") as fh:
            fh.write(line)
        # read-back verification: the new entry must be its own line
        lines = target.read_text(encoding="utf-8").splitlines()
        if not lines or lines[-1] != line.rstrip("\n"):
            raise IOError("read-back failed: appended entry is not a standalone last line")
        index = self._file(INDEX_NAME)
        _ensure_trailing_newline(index)
        summary = text[:60].replace("|", "/")
        with index.open("a", encoding="utf-8") as fh:
            fh.write(f"| {entry_id} | {timestamp} | {category} | {summary} |\n")
        return Entry(entry_id, category, text, timestamp)

    def list_entries(
        self,
        category: str | None = None,
        on_date: str | None = None,
        tag: str | None = None,
    ) -> list[Entry]:
        """List entries, optionally filtered by category, date, and/or tag.

        ``category`` must be one of the known categories; ``on_date`` must
        be ``YYYY-MM-DD`` and matches the date part of the entry timestamp;
        ``tag`` matches a ``#tag`` in the entry text (case-insensitive,
        a leading '#' is accepted).
        Entries are returned in chronological order (timestamp, then ID),
        so listing is stable regardless of which category file they live in.
        Non-entry lines (headers, hand-written notes) are skipped, never
        treated as entries.
        """
        if category is not None and category not in CATEGORIES:
            raise ValueError(f"unknown category: {category} (choose from {sorted(CATEGORIES)})")
        if on_date is not None:
            _validate_date(on_date)
        wanted = _normalize_tag(tag) if tag is not None else None
        categories = [category] if category is not None else list(CATEGORIES)
        entries: list[Entry] = []
        for cat in categories:
            p = self._file(CATEGORIES[cat])
            if not p.exists():
                continue
            for ln in p.read_text(encoding="utf-8").splitlines():
                match = _ENTRY_LINE.match(ln)
                if match is None:
                    continue
                entry_id, timestamp, text = match.groups()
                if on_date is not None and not timestamp.startswith(on_date):
                    continue
                entry = Entry(entry_id, cat, text, timestamp)
                if wanted is not None and wanted not in entry.tags:
                    continue
                entries.append(entry)
        entries.sort(key=lambda e: (e.timestamp, e.entry_id))
        return entries

    def stats(self, since: str | None = None, until: str | None = None) -> Stats:
        """Summarize the inbox: per-category counts, earliest/latest
        entries, total entry-text characters, and per-month counts.

        ``by_category`` always lists every known category (zero when
        empty) so callers can rely on the keys. ``by_month`` counts
        entries per ``YYYY-MM`` month, in chronological order; it is
        empty for an empty (or empty-in-range) inbox. ``earliest`` /
        ``latest`` use the same chronological order as
        :meth:`list_entries` and are ``None`` for an empty inbox.
        ``total_chars`` counts entry text only, not IDs, timestamps, or
        Markdown markup.

        ``since`` / ``until`` (``YYYY-MM-DD``) restrict the summary to
        entries dated on or after ``since`` / on or before ``until`` —
        both boundary days are included. A range with ``since`` after
        ``until`` raises ``ValueError``.
        """
        if since is not None:
            _validate_date(since)
        if until is not None:
            _validate_date(until)
        if since is not None and until is not None and since > until:
            raise ValueError(f"invalid date range: since {since!r} is after until {until!r}")
        entries = [
            e for e in self.list_entries()
            if (since is None or e.timestamp[:10] >= since)
            and (until is None or e.timestamp[:10] <= until)
        ]
        by_category = {cat: 0 for cat in CATEGORIES}
        by_month: dict[str, int] = {}
        for entry in entries:
            by_category[entry.category] += 1
            month = entry.timestamp[:7]
            by_month[month] = by_month.get(month, 0) + 1
        return Stats(
            total=len(entries),
            by_category=by_category,
            earliest=entries[0] if entries else None,
            latest=entries[-1] if entries else None,
            total_chars=sum(len(entry.text) for entry in entries),
            by_month=by_month,
        )

    def export(
        self,
        format: str = "markdown",
        category: str | None = None,
        on_date: str | None = None,
    ) -> str:
        """Export the inbox as one Markdown document or one JSON array.

        ``format`` is ``markdown`` (default) or ``json``. The same
        ``category`` / ``on_date`` filters as :meth:`list_entries` apply,
        so callers get the same validation and chronological order.
        Markdown is one document with a header, a total line, and one
        ``- [ID] timestamp [category] text`` line per entry; JSON is a
        list of ``entry_id`` / ``category`` / ``text`` / ``timestamp``
        objects. An empty inbox exports as a Markdown header with
        ``no entries`` or as ``[]`` — never as an error.
        """
        if format not in ("markdown", "json"):
            raise ValueError(f"unknown export format: {format!r} (choose from markdown, json)")
        entries = self.list_entries(category=category, on_date=on_date)
        if format == "json":
            payload = [
                {
                    "entry_id": e.entry_id,
                    "category": e.category,
                    "text": e.text,
                    "timestamp": e.timestamp,
                }
                for e in entries
            ]
            return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        lines = ["# Export", "", f"total: {len(entries)}", ""]
        if entries:
            for e in entries:
                lines.append(f"- [{e.entry_id}] {e.timestamp} [{e.category}] {e.text}")
        else:
            lines.append("no entries")
        return "\n".join(lines) + "\n"

    def import_entries(
        self,
        source: str | Path,
        format: str = "auto",
        category: str | None = None,
        dry_run: bool = False,
    ) -> ImportResult:
        """Import entries from an exported Markdown or JSON file.

        ``format`` is ``auto`` (default, detected from the file suffix:
        ``.json`` for JSON, ``.md`` / ``.markdown`` / ``.txt`` for
        Markdown), ``json``, or ``markdown``. Markdown accepts both the
        ``export`` output (``- [ID] timestamp [category] text``) and raw
        category-file lines (``- [ID] timestamp — text``); the latter
        needs ``category`` to say which category they belong to, and
        ``--category`` is rejected for JSON, whose entries carry their
        own category. Timestamps are preserved; entry IDs are always
        freshly assigned for the target inbox. An entry is a duplicate
        when the inbox already holds the same category, timestamp, and
        text — duplicates are counted and skipped, both against existing
        entries and within the file itself. The whole file is validated
        before anything is written, so a bad file imports nothing.
        With ``dry_run`` nothing is written (not even ``init``) and the
        returned entries carry the IDs they would have received.
        """
        if format not in ("auto", "json", "markdown"):
            raise ValueError(f"unknown import format: {format!r} (choose from auto, json, markdown)")
        if category is not None and category not in CATEGORIES:
            raise ValueError(f"unknown category: {category} (choose from {sorted(CATEGORIES)})")
        if format == "json" and category is not None:
            raise ValueError("--category only applies to Markdown category files, not JSON")
        path = Path(source)
        if format == "auto":
            suffix = path.suffix.lower()
            if suffix == ".json":
                format = "json"
            elif suffix in (".md", ".markdown", ".txt"):
                format = "markdown"
            else:
                raise ValueError(
                    f"cannot detect import format from {source!r} "
                    "(use --format json|markdown)"
                )
        raw = path.read_text(encoding="utf-8")
        if format == "json":
            candidates = _parse_import_json(raw)
        else:
            candidates = _parse_import_markdown(raw, category)
        seen = {(e.category, e.timestamp, e.text) for e in self.list_entries()}
        imported: list[Entry] = []
        duplicates = 0
        if dry_run:
            # Predict the IDs add() would assign, from the index alone,
            # without touching any file.
            index = self._file(INDEX_NAME)
            index_text = index.read_text(encoding="utf-8") if index.exists() else ""
            counts: dict[str, int] = {}
            for prefix in re.findall(r"(\d{8})-\d+", index_text):
                counts[prefix] = counts.get(prefix, 0) + 1
            for cat, text, when in candidates:
                stamp = when.strftime("%Y-%m-%d %H:%M")
                if (cat, stamp, text) in seen:
                    duplicates += 1
                    continue
                seen.add((cat, stamp, text))
                day = when.strftime("%Y%m%d")
                counts[day] = counts.get(day, 0) + 1
                imported.append(Entry(f"{day}-{counts[day]:02d}", cat, text, stamp))
        else:
            for cat, text, when in candidates:
                stamp = when.strftime("%Y-%m-%d %H:%M")
                if (cat, stamp, text) in seen:
                    duplicates += 1
                    continue
                seen.add((cat, stamp, text))
                imported.append(self.add(cat, text, now=when))
        return ImportResult(imported=imported, duplicates=duplicates, dry_run=dry_run)

    def search(
        self,
        query: str,
        tag: str | None = None,
        category: str | None = None,
        since: str | None = None,
    ) -> list[str]:
        """Search entry lines for ``query`` (case-insensitive).

        ``tag`` additionally requires the hit to be an entry line whose
        parsed tags contain the tag (case-insensitive, a leading '#' is
        accepted). ``category`` restricts the search to one category
        file. ``since`` (``YYYY-MM-DD``) keeps only entries dated on or
        after that day — the boundary day itself is included.
        Whenever any filter is given, hits must be entry lines (only
        they carry a category, a date, and tags); hand-written headers
        and notes never match a filtered search.
        """
        if category is not None and category not in CATEGORIES:
            raise ValueError(f"unknown category: {category} (choose from {sorted(CATEGORIES)})")
        if since is not None:
            _validate_date(since)
        wanted = _normalize_tag(tag) if tag is not None else None
        filtered = tag is not None or category is not None or since is not None
        files = [CATEGORIES[category]] if category is not None else list(CATEGORIES.values())
        hits: list[str] = []
        for filename in files:
            p = self._file(filename)
            if p.exists():
                for ln in p.read_text(encoding="utf-8").splitlines():
                    if query.lower() not in ln.lower():
                        continue
                    if filtered:
                        match = _ENTRY_LINE.match(ln)
                        if match is None:
                            continue
                        if wanted is not None and wanted not in parse_tags(match.group(3)):
                            continue
                        # Timestamps are "YYYY-MM-DD HH:MM", so the date
                        # part compares lexicographically with ``since``.
                        if since is not None and match.group(2)[:10] < since:
                            continue
                    hits.append(f"{filename}: {ln}")
        return hits

    def verify(self) -> dict[str, str]:
        """Return {filename: md5} for every inbox file; raise on index mismatch."""
        result = {}
        indexed_ids: set[str] = set()
        index = self._file(INDEX_NAME)
        if index.exists():
            indexed_ids = set(re.findall(r"\d{8}-\d+", index.read_text(encoding="utf-8")))
        found_ids: set[str] = set()
        for filename in list(CATEGORIES.values()) + [INDEX_NAME]:
            p = self._file(filename)
            if p.exists():
                result[filename] = _md5(p)
                if filename != INDEX_NAME:
                    found_ids |= set(re.findall(r"\d{8}-\d+", p.read_text(encoding="utf-8")))
        if indexed_ids != found_ids:
            raise IOError(f"index/content mismatch: indexed={sorted(indexed_ids)} found={sorted(found_ids)}")
        return result

    def doctor(self) -> DoctorReport:
        """Run a read-only health self-check over the inbox.

        Checks: every known file is present and reachable (not a symlink,
        inside the root); every non-empty file ends with a newline; every
        line that looks like an entry line (``- [ID] ...``) matches the
        entry format and no entry ID is used twice; every index row
        matches the row format and names a known category with a valid
        timestamp; the set of IDs in the index agrees with the set of IDs
        in the category files (checked only when every file is present,
        so a missing file reports just itself); no file is world-writable.
        (Group-writable is not flagged: a umask of 002 makes it the
        normal state of freshly created files.) The report also
        carries the md5 fingerprint of every file found — the same values
        :meth:`verify` returns. Nothing is written: a doctor run on an
        uninitialized inbox reports the missing files and leaves the disk
        untouched.
        """
        issues: list[DoctorIssue] = []
        fingerprints: dict[str, str] = {}
        found_ids: dict[str, int] = {}
        indexed_ids: dict[str, int] = {}
        all_present = True
        for filename in list(CATEGORIES.values()) + [INDEX_NAME]:
            try:
                p = self._file(filename)
            except (ValueError, IOError) as exc:
                issues.append(DoctorIssue("error", "file access", str(exc)))
                all_present = False
                continue
            if not p.exists():
                issues.append(DoctorIssue(
                    "error", "files present",
                    f"{filename} is missing (run `musings-inbox init` to create it)",
                ))
                all_present = False
                continue
            fingerprints[filename] = _md5(p)
            try:
                text = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                issues.append(DoctorIssue(
                    "error", "file access", f"{filename} is not valid UTF-8"
                ))
                continue
            if text and not text.endswith("\n"):
                issues.append(DoctorIssue(
                    "error", "trailing newline",
                    f"{filename} does not end with a newline",
                ))
            mode = stat.S_IMODE(p.stat().st_mode)
            if mode & 0o002:
                issues.append(DoctorIssue(
                    "error", "file permissions",
                    f"{filename} is world-writable (mode {mode:03o})",
                ))
            if filename != INDEX_NAME:
                for lineno, ln in enumerate(text.splitlines(), start=1):
                    if not ln.startswith("- ["):
                        continue
                    match = _ENTRY_LINE.match(ln)
                    if match is None:
                        issues.append(DoctorIssue(
                            "error", "entry format",
                            f"{filename}:{lineno}: malformed entry line: {ln!r}",
                        ))
                    else:
                        entry_id = match.group(1)
                        found_ids[entry_id] = found_ids.get(entry_id, 0) + 1
            else:
                for lineno, ln in enumerate(text.splitlines(), start=1):
                    if not ln.startswith("| "):
                        continue
                    if ln in (_INDEX_HEADER, _INDEX_SEPARATOR):
                        continue
                    match = _INDEX_ROW.match(ln)
                    if match is None:
                        issues.append(DoctorIssue(
                            "error", "index format",
                            f"{filename}:{lineno}: malformed index row: {ln!r}",
                        ))
                        continue
                    entry_id, timestamp, category, _summary = match.groups()
                    if category not in CATEGORIES:
                        issues.append(DoctorIssue(
                            "error", "index format",
                            f"{filename}:{lineno}: unknown category {category!r} in index row",
                        ))
                    try:
                        _parse_timestamp(timestamp)
                    except ValueError as exc:
                        issues.append(DoctorIssue(
                            "error", "index format", f"{filename}:{lineno}: {exc}",
                        ))
                    indexed_ids[entry_id] = indexed_ids.get(entry_id, 0) + 1
        for entry_id, count in sorted(found_ids.items()):
            if count > 1:
                issues.append(DoctorIssue(
                    "error", "duplicate entry ids",
                    f"{entry_id} appears {count} times in category files",
                ))
        for entry_id, count in sorted(indexed_ids.items()):
            if count > 1:
                issues.append(DoctorIssue(
                    "error", "duplicate entry ids",
                    f"{entry_id} appears {count} times in the index",
                ))
        if all_present:
            indexed = set(indexed_ids)
            found = set(found_ids)
            if indexed != found:
                detail = []
                if found - indexed:
                    detail.append(
                        "in category files but missing from index: "
                        f"{sorted(found - indexed)}"
                    )
                if indexed - found:
                    detail.append(
                        "indexed but not in any category file: "
                        f"{sorted(indexed - found)}"
                    )
                issues.append(DoctorIssue(
                    "error", "index consistency", "; ".join(detail),
                ))
        errors = sum(1 for issue in issues if issue.severity == "error")
        return DoctorReport(ok=errors == 0, issues=issues, fingerprints=fingerprints)

    def backup(self, destination: str | Path | None = None, now: datetime | None = None) -> BackupResult:
        """Create a timestamped backup of the whole inbox.

        ``destination`` is the directory that receives the backup (created
        when needed; default ``./backups``). Inside it a new directory
        ``musings-inbox-backup-YYYYMMDD-HHMMSS`` is created holding a copy
        of every inbox file plus a ``manifest.json`` with the backup
        format version, the creation time, the md5 fingerprint of each
        file, and the entry count. The timestamp comes from a real clock
        read (or the injected ``now``, for tests). A second backup in the
        same second gets a ``-2``, ``-3`` suffix instead of overwriting
        the first. All five inbox files must be present — a missing file
        fails the backup before anything is written.
        """
        now = now or datetime.now()  # the only permitted time source: a real clock read
        missing = [name for name in list(CATEGORIES.values()) + [INDEX_NAME]
                   if not self._file(name).exists()]
        if missing:
            raise ValueError(
                f"cannot back up: missing inbox files: {missing} "
                "(run `musings-inbox init` to create them)"
            )
        dest = Path(destination) if destination is not None else Path("backups")
        stamp = now.strftime("%Y%m%d-%H%M%S")
        target = dest / f"musings-inbox-backup-{stamp}"
        suffix = 2
        while target.exists():
            target = dest / f"musings-inbox-backup-{stamp}-{suffix}"
            suffix += 1
        target.mkdir(parents=True)
        fingerprints: dict[str, str] = {}
        for name in list(CATEGORIES.values()) + [INDEX_NAME]:
            data = self._file(name).read_bytes()
            (target / name).write_bytes(data)
            fingerprints[name] = hashlib.md5(data).hexdigest()
        created = now.strftime("%Y-%m-%d %H:%M")
        manifest = {
            "format": BACKUP_FORMAT,
            "version": BACKUP_FORMAT_VERSION,
            "created": created,
            "files": fingerprints,
            "entries": len(self.list_entries()),
        }
        (target / BACKUP_MANIFEST).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return BackupResult(path=target, created=created,
                            fingerprints=fingerprints, entries=manifest["entries"])

    def restore(self, source: str | Path, dry_run: bool = False) -> RestoreResult:
        """Restore the inbox from a timestamped backup directory.

        ``source`` is a directory created by :meth:`backup` (the five
        inbox files plus ``manifest.json``). The backup is fully validated
        before anything is written: the manifest must exist, parse, and
        name this backup format at the supported version; every listed
        file must be present, inside the backup directory, not a symlink,
        and match the manifest's md5 fingerprint; every entry-looking line
        must match the entry format and every index row the row format;
        and the set of IDs in the index must agree with the set in the
        category files. Any problem raises ``ValueError`` listing every
        problem found, and nothing is written. A successful restore
        replaces the current inbox contents with the backup (timestamps
        and entry IDs are kept as backed up, not reassigned). With
        ``dry_run`` the backup is validated and the entries it would
        restore are reported, but the disk is left untouched.
        """
        source_dir = Path(source)
        errors: list[str] = []
        if not source_dir.is_dir():
            raise ValueError(f"backup not found: {source!r} is not a directory")
        resolved_source = source_dir.resolve()
        manifest_path = source_dir / BACKUP_MANIFEST
        manifest: dict = {}
        if manifest_path.is_symlink() or not manifest_path.is_file():
            errors.append(f"{BACKUP_MANIFEST} is missing from the backup")
        else:
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                errors.append(f"{BACKUP_MANIFEST} does not parse: {exc}")
            if isinstance(manifest, dict):
                if manifest.get("format") != BACKUP_FORMAT:
                    errors.append(
                        f"{BACKUP_MANIFEST} names unknown backup format: "
                        f"{manifest.get('format')!r} (expected {BACKUP_FORMAT!r})"
                    )
                if manifest.get("version") != BACKUP_FORMAT_VERSION:
                    errors.append(
                        f"{BACKUP_MANIFEST} names unsupported backup version: "
                        f"{manifest.get('version')!r} (expected {BACKUP_FORMAT_VERSION})"
                    )
                listed = manifest.get("files")
                expected = {INDEX_NAME, *CATEGORIES.values()}
                if not isinstance(listed, dict) or set(listed) != expected:
                    errors.append(
                        f"{BACKUP_MANIFEST} must list md5 fingerprints for exactly "
                        f"{sorted(expected)}"
                    )
            else:
                errors.append(f"{BACKUP_MANIFEST} must contain a JSON object")
        # Read every backup file (guarded: no symlinks, stays inside the
        # backup directory) and check it against the manifest fingerprint.
        contents: dict[str, str] = {}
        fingerprints: dict[str, str] = {}
        for name in list(CATEGORIES.values()) + [INDEX_NAME]:
            p = source_dir / name
            if p.is_symlink():
                errors.append(f"{name} is a symlink; refusing to follow it")
                continue
            try:
                resolved = p.resolve()
                resolved.relative_to(resolved_source)
            except (ValueError, RuntimeError):
                errors.append(f"{name} escapes the backup directory")
                continue
            if not p.is_file():
                errors.append(f"{name} is missing from the backup")
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                errors.append(f"{name} is not valid UTF-8")
                continue
            contents[name] = text
            digest = hashlib.md5(p.read_bytes()).hexdigest()
            fingerprints[name] = digest
            listed = manifest.get("files") if isinstance(manifest, dict) else None
            if isinstance(listed, dict) and name in listed and listed[name] != digest:
                errors.append(
                    f"{name} does not match the manifest fingerprint "
                    "(backup may be tampered with or damaged)"
                )
        if len(contents) == len(CATEGORIES) + 1:
            found_ids: set[str] = set()
            indexed_ids: set[str] = set()
            entries: list[Entry] = []
            for cat, filename in CATEGORIES.items():
                for lineno, ln in enumerate(contents[filename].splitlines(), start=1):
                    if not ln.startswith("- ["):
                        continue
                    match = _ENTRY_LINE.match(ln)
                    if match is None:
                        errors.append(
                            f"{filename}:{lineno}: malformed entry line: {ln!r}"
                        )
                        continue
                    entry_id, timestamp, text = match.groups()
                    found_ids.add(entry_id)
                    entries.append(Entry(entry_id, cat, text, timestamp))
            for lineno, ln in enumerate(contents[INDEX_NAME].splitlines(), start=1):
                if not ln.startswith("| "):
                    continue
                if ln in (_INDEX_HEADER, _INDEX_SEPARATOR):
                    continue
                match = _INDEX_ROW.match(ln)
                if match is None:
                    errors.append(
                        f"{INDEX_NAME}:{lineno}: malformed index row: {ln!r}"
                    )
                    continue
                entry_id, _timestamp, _category, _summary = match.groups()
                indexed_ids.add(entry_id)
            if indexed_ids != found_ids:
                detail = []
                if found_ids - indexed_ids:
                    detail.append(
                        "in category files but missing from index: "
                        f"{sorted(found_ids - indexed_ids)}"
                    )
                if indexed_ids - found_ids:
                    detail.append(
                        "indexed but not in any category file: "
                        f"{sorted(indexed_ids - found_ids)}"
                    )
                errors.append("index/content mismatch: " + "; ".join(detail))
        if errors:
            raise ValueError("invalid backup:\n" + "\n".join(errors))
        entries.sort(key=lambda e: (e.timestamp, e.entry_id))
        if dry_run:
            return RestoreResult(restored=entries, fingerprints=fingerprints, dry_run=True)
        self.root.mkdir(parents=True, exist_ok=True)
        for name in list(CATEGORIES.values()) + [INDEX_NAME]:
            self._file(name).write_text(contents[name], encoding="utf-8")
        # Read-back verification: the restored inbox must verify cleanly.
        self.verify()
        return RestoreResult(restored=self.list_entries(),
                             fingerprints=fingerprints, dry_run=False)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="musings-inbox", description=__doc__)
    ap.add_argument("--root", default="inbox", help="inbox directory (default: ./inbox)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    p_add = sub.add_parser("add")
    p_add.add_argument("--type", dest="category", required=True, choices=sorted(CATEGORIES))
    p_add.add_argument("--text", required=True)
    p_search = sub.add_parser("search")
    p_search.add_argument("query")
    p_search.add_argument("--tag", dest="tag", default=None,
                          help="only match entries carrying this #tag")
    p_search.add_argument("--category", dest="category", default=None, choices=sorted(CATEGORIES),
                          help="only search this category")
    p_search.add_argument("--since", dest="since", default=None,
                          help="only entries on or after this date, YYYY-MM-DD")
    p_list = sub.add_parser("list", help="list entries, optionally filtered by category and/or date")
    p_list.add_argument("--category", dest="category", default=None, choices=sorted(CATEGORIES))
    p_list.add_argument("--date", dest="on_date", default=None, help="filter by date, YYYY-MM-DD")
    p_list.add_argument("--tag", dest="tag", default=None, help="filter by #tag in entry text")
    p_stats = sub.add_parser("stats", help="show per-category counts, earliest/latest entries, total characters, "
                                            "and per-month counts, optionally within a date range")
    p_stats.add_argument("--since", dest="since", default=None,
                         help="only entries on or after this date, YYYY-MM-DD")
    p_stats.add_argument("--until", dest="until", default=None,
                         help="only entries on or before this date, YYYY-MM-DD")
    p_export = sub.add_parser("export", help="export the inbox as one Markdown document or JSON array")
    p_export.add_argument("--format", dest="format", default="markdown", choices=["markdown", "json"],
                          help="output format (default: markdown)")
    p_export.add_argument("--category", dest="category", default=None, choices=sorted(CATEGORIES))
    p_export.add_argument("--date", dest="on_date", default=None, help="filter by date, YYYY-MM-DD")
    p_export.add_argument("--output", dest="output", default=None,
                          help="write to this file instead of stdout")
    p_import = sub.add_parser("import", help="import entries from an exported Markdown or JSON file")
    p_import.add_argument("--file", dest="source", required=True,
                          help="Markdown or JSON file to import (usually an export output)")
    p_import.add_argument("--format", dest="format", default="auto", choices=["auto", "json", "markdown"],
                          help="input format; auto detects it from the file suffix (default: auto)")
    p_import.add_argument("--category", dest="category", default=None, choices=sorted(CATEGORIES),
                          help="category for Markdown category-file lines (the file has no [category] per line)")
    p_import.add_argument("--dry-run", dest="dry_run", action="store_true",
                          help="show what would be imported without writing anything")
    sub.add_parser("doctor", help="health self-check: trailing newlines, md5 fingerprints, "
                                  "index consistency, file permissions")
    p_backup = sub.add_parser("backup", help="create a timestamped backup of the whole inbox")
    p_backup.add_argument("--output", dest="output", default=None,
                          help="directory receiving the backup (default: ./backups)")
    p_restore = sub.add_parser("restore", help="restore the inbox from a backup, after checking it")
    p_restore.add_argument("--from", dest="source", required=True,
                           help="backup directory created by `backup`")
    p_restore.add_argument("--dry-run", dest="dry_run", action="store_true",
                           help="validate the backup without writing anything")
    sub.add_parser("verify")
    args = ap.parse_args(argv)
    try:
        inbox = Inbox(args.root)
        if args.cmd == "init":
            inbox.init()
            print(f"initialized: {inbox.root}")
        elif args.cmd == "add":
            entry = inbox.add(args.category, args.text)
            print(f"{entry.entry_id} {entry.timestamp} [{entry.category}] {entry.text}")
        elif args.cmd == "search":
            hits = inbox.search(args.query, tag=args.tag, category=args.category, since=args.since)
            print("\n".join(hits) if hits else "no matches")
        elif args.cmd == "list":
            entries = inbox.list_entries(category=args.category, on_date=args.on_date, tag=args.tag)
            if entries:
                for entry in entries:
                    print(f"{entry.entry_id} {entry.timestamp} [{entry.category}] {entry.text}")
            else:
                print("no entries")
        elif args.cmd == "stats":
            stats = inbox.stats(since=args.since, until=args.until)
            if args.since is not None and args.until is not None:
                print(f"range: {args.since} to {args.until}")
            elif args.since is not None:
                print(f"range: from {args.since}")
            elif args.until is not None:
                print(f"range: until {args.until}")
            print(f"total: {stats.total}")
            for cat in CATEGORIES:
                print(f"{cat}: {stats.by_category[cat]}")
            if stats.by_month:
                print("per month:")
                for month, count in stats.by_month.items():
                    print(f"  {month}: {count}")
            else:
                print("per month: none")
            if stats.earliest is not None:
                e = stats.earliest
                print(f"earliest: {e.entry_id} {e.timestamp} [{e.category}] {e.text}")
            else:
                print("earliest: none")
            if stats.latest is not None:
                e = stats.latest
                print(f"latest: {e.entry_id} {e.timestamp} [{e.category}] {e.text}")
            else:
                print("latest: none")
            print(f"total characters: {stats.total_chars}")
        elif args.cmd == "export":
            text = inbox.export(format=args.format, category=args.category, on_date=args.on_date)
            if args.output is not None:
                out_path = Path(args.output)
                if out_path.parent != Path("."):
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(text, encoding="utf-8")
                print(f"exported: {out_path}")
            else:
                sys.stdout.write(text)
        elif args.cmd == "import":
            result = inbox.import_entries(
                args.source, format=args.format, category=args.category, dry_run=args.dry_run
            )
            if result.dry_run:
                print("dry run: no changes written")
            for entry in result.imported:
                print(f"{entry.entry_id} {entry.timestamp} [{entry.category}] {entry.text}")
            print(f"imported: {len(result.imported)}")
            print(f"duplicates skipped: {result.duplicates}")
        elif args.cmd == "doctor":
            report = inbox.doctor()
            checks = ["files present", "file access", "trailing newline",
                      "entry format", "index format", "index consistency",
                      "duplicate entry ids", "file permissions"]
            for check in checks:
                flagged = [i for i in report.issues if i.check == check]
                if not flagged:
                    print(f"[ok] {check}")
                else:
                    for issue in flagged:
                        print(f"[{issue.severity}] {check}: {issue.message}")
            if report.fingerprints:
                print("fingerprints:")
                for name in sorted(report.fingerprints):
                    print(f"  {name} {report.fingerprints[name]}")
            errors = sum(1 for i in report.issues if i.severity == "error")
            warnings = sum(1 for i in report.issues if i.severity == "warning")
            if errors == 0 and warnings == 0:
                print("OK: inbox is healthy")
            else:
                print(f"doctor found {errors} error(s) and {warnings} warning(s)")
                return 1
        elif args.cmd == "backup":
            result = inbox.backup(destination=args.output)
            print(f"backup: {result.path}")
            print(f"created: {result.created}")
            print(f"entries: {result.entries}")
            for name in sorted(result.fingerprints):
                print(f"  {name} {result.fingerprints[name]}")
        elif args.cmd == "restore":
            result = inbox.restore(args.source, dry_run=args.dry_run)
            if result.dry_run:
                print("dry run: no changes written")
            for entry in result.restored:
                print(f"{entry.entry_id} {entry.timestamp} [{entry.category}] {entry.text}")
            print(f"restored: {len(result.restored)}")
        elif args.cmd == "verify":
            for name, digest in inbox.verify().items():
                print(f"{name} {digest}")
            print("OK: index and content agree")
    except (ValueError, IOError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
