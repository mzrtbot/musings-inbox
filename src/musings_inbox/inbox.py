"""musings-inbox: local-first life-log / inspiration inbox for AI agents.

File-based, vendor-neutral memory: every entry is plain Markdown on disk,
timestamped only from a real clock read, appended with a trailing-newline
check, and verified by read-back + fingerprint. No database, no cloud lock-in.
"""
from __future__ import annotations

import argparse
import hashlib
import re
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
# Lines written by Inbox.add, e.g.:
# - [20261023-01] 2026-10-23 09:30 — The workshop opens at nine.
_ENTRY_LINE = re.compile(r"^-\s\[(\d{8}-\d+)\]\s(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2})\s—\s(.*)$")


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


def _today_id(inbox: Path, now: datetime) -> str:
    index = inbox / INDEX_NAME
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


class Inbox:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def init(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        for filename in CATEGORIES.values():
            p = self.root / filename
            if not p.exists():
                title = filename.removesuffix(".md").title()
                p.write_text(f"# {title}\n", encoding="utf-8")
        index = self.root / INDEX_NAME
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
        entry_id = _today_id(self.root, now)
        timestamp = now.strftime("%Y-%m-%d %H:%M")
        target = self.root / CATEGORIES[category]
        _ensure_trailing_newline(target)
        line = f"- [{entry_id}] {timestamp} — {text}\n"
        with target.open("a", encoding="utf-8") as fh:
            fh.write(line)
        # read-back verification: the new entry must be its own line
        lines = target.read_text(encoding="utf-8").splitlines()
        if not lines or lines[-1] != line.rstrip("\n"):
            raise IOError("read-back failed: appended entry is not a standalone last line")
        index = self.root / INDEX_NAME
        _ensure_trailing_newline(index)
        summary = text[:60].replace("|", "/")
        with index.open("a", encoding="utf-8") as fh:
            fh.write(f"| {entry_id} | {timestamp} | {category} | {summary} |\n")
        return Entry(entry_id, category, text, timestamp)

    def list_entries(self, category: str | None = None, on_date: str | None = None) -> list[Entry]:
        """List entries, optionally filtered by category and/or date.

        ``category`` must be one of the known categories; ``on_date`` must
        be ``YYYY-MM-DD`` and matches the date part of the entry timestamp.
        Entries are returned in chronological order (timestamp, then ID),
        so listing is stable regardless of which category file they live in.
        Non-entry lines (headers, hand-written notes) are skipped, never
        treated as entries.
        """
        if category is not None and category not in CATEGORIES:
            raise ValueError(f"unknown category: {category} (choose from {sorted(CATEGORIES)})")
        if on_date is not None:
            try:
                datetime.strptime(on_date, "%Y-%m-%d")
            except ValueError:
                raise ValueError(f"invalid date: {on_date!r} (expected YYYY-MM-DD)") from None
        categories = [category] if category is not None else list(CATEGORIES)
        entries: list[Entry] = []
        for cat in categories:
            p = self.root / CATEGORIES[cat]
            if not p.exists():
                continue
            for ln in p.read_text(encoding="utf-8").splitlines():
                match = _ENTRY_LINE.match(ln)
                if match is None:
                    continue
                entry_id, timestamp, text = match.groups()
                if on_date is not None and not timestamp.startswith(on_date):
                    continue
                entries.append(Entry(entry_id, cat, text, timestamp))
        entries.sort(key=lambda e: (e.timestamp, e.entry_id))
        return entries

    def search(self, query: str) -> list[str]:
        hits: list[str] = []
        for filename in CATEGORIES.values():
            p = self.root / filename
            if p.exists():
                for ln in p.read_text(encoding="utf-8").splitlines():
                    if query.lower() in ln.lower():
                        hits.append(f"{filename}: {ln}")
        return hits

    def verify(self) -> dict[str, str]:
        """Return {filename: md5} for every inbox file; raise on index mismatch."""
        result = {}
        indexed_ids: set[str] = set()
        index = self.root / INDEX_NAME
        if index.exists():
            indexed_ids = set(re.findall(r"\d{8}-\d+", index.read_text(encoding="utf-8")))
        found_ids: set[str] = set()
        for filename in list(CATEGORIES.values()) + [INDEX_NAME]:
            p = self.root / filename
            if p.exists():
                result[filename] = _md5(p)
                if filename != INDEX_NAME:
                    found_ids |= set(re.findall(r"\d{8}-\d+", p.read_text(encoding="utf-8")))
        if indexed_ids != found_ids:
            raise IOError(f"index/content mismatch: indexed={sorted(indexed_ids)} found={sorted(found_ids)}")
        return result


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
    p_list = sub.add_parser("list", help="list entries, optionally filtered by category and/or date")
    p_list.add_argument("--category", dest="category", default=None, choices=sorted(CATEGORIES))
    p_list.add_argument("--date", dest="on_date", default=None, help="filter by date, YYYY-MM-DD")
    sub.add_parser("verify")
    args = ap.parse_args(argv)
    inbox = Inbox(args.root)
    try:
        if args.cmd == "init":
            inbox.init()
            print(f"initialized: {inbox.root}")
        elif args.cmd == "add":
            entry = inbox.add(args.category, args.text)
            print(f"{entry.entry_id} {entry.timestamp} [{entry.category}] {entry.text}")
        elif args.cmd == "search":
            hits = inbox.search(args.query)
            print("\n".join(hits) if hits else "no matches")
        elif args.cmd == "list":
            entries = inbox.list_entries(category=args.category, on_date=args.on_date)
            if entries:
                for entry in entries:
                    print(f"{entry.entry_id} {entry.timestamp} [{entry.category}] {entry.text}")
            else:
                print("no entries")
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
