import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from musings_inbox.inbox import Inbox  # noqa: E402

NOW = datetime(2026, 10, 23, 9, 30)


def test_add_and_search(tmp_path):
    box = Inbox(tmp_path / "inbox")
    entry = box.add("fact", "The workshop opens at nine.", now=NOW)
    assert entry.entry_id == "20261023-01"
    assert box.search("workshop")[0].startswith("facts.md:")


def test_append_never_glues_lines(tmp_path):
    """Regression test for the trailing-newline rule."""
    box = Inbox(tmp_path / "inbox")
    box.init()
    facts = box.root / "facts.md"
    facts.write_bytes(b"# Facts\n- old entry without trailing newline")
    entry = box.add("fact", "A brand new entry.", now=NOW)
    lines = facts.read_text(encoding="utf-8").splitlines()
    assert lines[-1].endswith("A brand new entry.")
    assert entry.entry_id in lines[-1]
    assert lines[-2].endswith("without trailing newline")


def test_ids_increment_within_a_day(tmp_path):
    box = Inbox(tmp_path / "inbox")
    first = box.add("preference", "Quiet mornings.", now=NOW)
    second = box.add("experience", "Fixed a glued index line by splitting it.", now=NOW)
    assert (first.entry_id, second.entry_id) == ("20261023-01", "20261023-02")


def test_verify_detects_index_mismatch(tmp_path):
    box = Inbox(tmp_path / "inbox")
    box.add("fact", "Something verifiable.", now=NOW)
    assert box.verify()  # passes when index and content agree
    (box.root / "facts.md").write_text("# Facts\n- [20260101-99] forged\n", encoding="utf-8")
    try:
        box.verify()
    except IOError:
        return
    raise AssertionError("verify() should have raised on mismatch")


def test_list_all_and_by_category(tmp_path):
    box = Inbox(tmp_path / "inbox")
    box.add("fact", "The workshop opens at nine.", now=NOW)
    box.add("preference", "Quiet mornings.", now=NOW)
    box.add("experience", "Fixed a glued index line.", now=NOW)
    all_entries = box.list_entries()
    assert [(e.entry_id, e.category) for e in all_entries] == [
        ("20261023-01", "fact"),
        ("20261023-02", "preference"),
        ("20261023-03", "experience"),
    ]
    facts = box.list_entries(category="fact")
    assert len(facts) == 1 and facts[0].text == "The workshop opens at nine."
    assert box.list_entries(category="material") == []


def test_list_by_date_and_chronological_order(tmp_path):
    box = Inbox(tmp_path / "inbox")
    box.add("fact", "First day note.", now=datetime(2026, 10, 22, 9, 0))
    box.add("fact", "Second day note.", now=datetime(2026, 10, 23, 9, 0))
    box.add("preference", "Second day preference.", now=datetime(2026, 10, 23, 8, 0))
    day23 = box.list_entries(on_date="2026-10-23")
    # Chronological, not file order: the 08:00 preference comes first.
    assert [e.entry_id for e in day23] == ["20261023-02", "20261023-01"]
    assert box.list_entries(on_date="2026-10-24") == []
    combined = box.list_entries(category="fact", on_date="2026-10-23")
    assert [e.text for e in combined] == ["Second day note."]


def test_list_rejects_bad_category_and_date(tmp_path):
    box = Inbox(tmp_path / "inbox")
    box.add("fact", "Something listable.", now=NOW)
    for bad_category, bad_date in [("diary", None), (None, "23-10-2026"), (None, "2026-13-01")]:
        try:
            box.list_entries(category=bad_category, on_date=bad_date)
        except ValueError:
            continue
        raise AssertionError(f"should reject {bad_category=} {bad_date=}")


def test_list_cli_prints_entries_and_empty(tmp_path, capsys):
    from musings_inbox.inbox import main

    root = str(tmp_path / "inbox")
    assert main(["--root", root, "list"]) == 0
    assert capsys.readouterr().out.strip() == "no entries"
    box = Inbox(tmp_path / "inbox")
    box.add("fact", "CLI-listed entry.", now=NOW)
    assert main(["--root", root, "list", "--category", "fact"]) == 0
    out = capsys.readouterr().out
    assert "20261023-01 2026-10-23 09:30 [fact] CLI-listed entry." in out


def test_stats_counts_earliest_latest_and_total_chars(tmp_path):
    box = Inbox(tmp_path / "inbox")
    box.add("fact", "First day note.", now=datetime(2026, 10, 22, 9, 0))
    box.add("fact", "Second day note.", now=datetime(2026, 10, 23, 9, 0))
    box.add("preference", "Second day preference.", now=datetime(2026, 10, 23, 8, 0))
    stats = box.stats()
    assert stats.total == 3
    assert stats.by_category == {"fact": 2, "preference": 1, "experience": 0, "material": 0}
    # Chronological: the 08:00 preference is earliest, the 09:00 fact latest.
    assert stats.earliest.entry_id == "20261022-01"
    assert stats.latest.entry_id == "20261023-01"
    assert stats.total_chars == 15 + 16 + 22


def test_stats_empty_inbox(tmp_path):
    stats = Inbox(tmp_path / "inbox").stats()
    assert stats.total == 0
    assert stats.by_category == {"fact": 0, "preference": 0, "experience": 0, "material": 0}
    assert stats.earliest is None and stats.latest is None
    assert stats.total_chars == 0


def test_stats_cli_prints_summary_and_empty(tmp_path, capsys):
    from musings_inbox.inbox import main

    root = str(tmp_path / "inbox")
    assert main(["--root", root, "stats"]) == 0
    out = capsys.readouterr().out
    assert "total: 0" in out
    assert "earliest: none" in out and "latest: none" in out
    assert "total characters: 0" in out
    box = Inbox(tmp_path / "inbox")
    box.add("fact", "CLI-counted entry.", now=NOW)
    assert main(["--root", root, "stats"]) == 0
    out = capsys.readouterr().out
    assert "total: 1" in out and "fact: 1" in out and "preference: 0" in out
    assert "earliest: 20261023-01 2026-10-23 09:30 [fact] CLI-counted entry." in out
    assert "latest: 20261023-01 2026-10-23 09:30 [fact] CLI-counted entry." in out
    assert "total characters: 18" in out


def test_stats_since_until_filters_and_month_counts(tmp_path):
    box = Inbox(tmp_path / "inbox")
    box.add("fact", "First day note.", now=datetime(2026, 10, 22, 9, 0))
    box.add("fact", "Second day note.", now=datetime(2026, 10, 23, 9, 0))
    box.add("preference", "Second day preference.", now=datetime(2026, 10, 23, 8, 0))
    box.add("material", "November note here.", now=datetime(2026, 11, 5, 10, 0))
    stats = box.stats()
    assert stats.total == 4
    assert stats.by_month == {"2026-10": 3, "2026-11": 1}
    assert stats.earliest.entry_id == "20261022-01"
    assert stats.latest.entry_id == "20261105-01"
    assert stats.total_chars == 15 + 16 + 22 + 19
    # --since keeps the boundary day; the 08:00 preference is earliest in range.
    ranged = box.stats(since="2026-10-23")
    assert ranged.total == 3
    assert ranged.by_month == {"2026-10": 2, "2026-11": 1}
    assert ranged.earliest.entry_id == "20261023-02"
    assert ranged.latest.entry_id == "20261105-01"
    assert ranged.total_chars == 16 + 22 + 19
    # --until keeps its boundary day too.
    ranged = box.stats(until="2026-10-23")
    assert ranged.total == 3
    assert ranged.by_month == {"2026-10": 3}
    assert ranged.earliest.entry_id == "20261022-01"
    assert ranged.latest.entry_id == "20261023-01"
    assert ranged.total_chars == 15 + 16 + 22
    # Both bounds on one day: that day only.
    ranged = box.stats(since="2026-10-23", until="2026-10-23")
    assert ranged.total == 2
    assert ranged.by_month == {"2026-10": 2}
    assert ranged.by_category == {"fact": 1, "preference": 1, "experience": 0, "material": 0}
    # A range with no entries reports zeros, not an error.
    ranged = box.stats(since="2027-01-01")
    assert ranged.total == 0
    assert ranged.by_month == {}
    assert ranged.by_category == {"fact": 0, "preference": 0, "experience": 0, "material": 0}
    assert ranged.earliest is None and ranged.latest is None
    assert ranged.total_chars == 0


def test_stats_range_validation(tmp_path):
    box = Inbox(tmp_path / "inbox")
    box.add("fact", "First day note.", now=datetime(2026, 10, 22, 9, 0))
    for bad in ("2026-13-01", "2026-10-32", "22-10-2026", "not-a-date"):
        try:
            box.stats(since=bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"stats(since={bad!r}) should raise ValueError")
        try:
            box.stats(until=bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"stats(until={bad!r}) should raise ValueError")
    try:
        box.stats(since="2026-10-23", until="2026-10-22")
    except ValueError as exc:
        assert "after" in str(exc)
    else:
        raise AssertionError("stats(since > until) should raise ValueError")


def test_stats_cli_since_until_and_months(tmp_path, capsys):
    from musings_inbox.inbox import main

    box = Inbox(tmp_path / "inbox")
    box.add("fact", "First day note.", now=datetime(2026, 10, 22, 9, 0))
    box.add("fact", "Second day note.", now=datetime(2026, 10, 23, 9, 0))
    box.add("material", "November note here.", now=datetime(2026, 11, 5, 10, 0))
    root = str(tmp_path / "inbox")
    assert main(["--root", root, "stats"]) == 0
    out = capsys.readouterr().out
    assert "total: 3" in out
    assert "per month:\n  2026-10: 2\n  2026-11: 1" in out
    assert "range:" not in out
    assert main(["--root", root, "stats", "--since", "2026-10-23", "--until", "2026-10-23"]) == 0
    out = capsys.readouterr().out
    assert "range: 2026-10-23 to 2026-10-23" in out
    assert "total: 1" in out
    assert "per month:\n  2026-10: 1" in out
    assert "earliest: 20261023-01 2026-10-23 09:00 [fact] Second day note." in out
    assert main(["--root", root, "stats", "--since", "2026-11-01"]) == 0
    out = capsys.readouterr().out
    assert "range: from 2026-11-01" in out
    assert "total: 1" in out and "per month:\n  2026-11: 1" in out
    assert main(["--root", root, "stats", "--until", "2026-10-22"]) == 0
    out = capsys.readouterr().out
    assert "range: until 2026-10-22" in out
    assert "total: 1" in out and "per month:\n  2026-10: 1" in out
    # An invalid range exits 1 with an error, like the other commands.
    assert main(["--root", root, "stats", "--since", "2026-11-06", "--until", "2026-11-05"]) == 1
    err = capsys.readouterr().err
    assert "error: invalid date range" in err


def test_stats_cli_empty_inbox_shows_no_months(tmp_path, capsys):
    from musings_inbox.inbox import main

    root = str(tmp_path / "inbox")
    assert main(["--root", root, "stats"]) == 0
    out = capsys.readouterr().out
    assert "total: 0" in out
    assert "per month: none" in out


def test_export_markdown_chronological_and_filtered(tmp_path):
    box = Inbox(tmp_path / "inbox")
    box.add("fact", "First day note.", now=datetime(2026, 10, 22, 9, 0))
    box.add("fact", "Second day note.", now=datetime(2026, 10, 23, 9, 0))
    box.add("preference", "Second day preference.", now=datetime(2026, 10, 23, 8, 0))
    doc = box.export()
    assert doc.startswith("# Export\n\ntotal: 3\n")
    # Chronological, not file order: the 08:00 preference comes first.
    lines = [ln for ln in doc.splitlines() if ln.startswith("- [")]
    assert lines == [
        "- [20261022-01] 2026-10-22 09:00 [fact] First day note.",
        "- [20261023-02] 2026-10-23 08:00 [preference] Second day preference.",
        "- [20261023-01] 2026-10-23 09:00 [fact] Second day note.",
    ]
    day23 = box.export(category="fact", on_date="2026-10-23")
    assert "total: 1" in day23 and "Second day note." in day23
    assert "First day note." not in day23


def test_export_json_parses_and_is_one_array(tmp_path):
    import json

    box = Inbox(tmp_path / "inbox")
    box.add("fact", "The workshop opens at nine.", now=NOW)
    box.add("preference", "Quiet mornings.", now=NOW)
    payload = json.loads(box.export(format="json"))
    assert payload == [
        {"entry_id": "20261023-01", "category": "fact",
         "text": "The workshop opens at nine.", "timestamp": "2026-10-23 09:30"},
        {"entry_id": "20261023-02", "category": "preference",
         "text": "Quiet mornings.", "timestamp": "2026-10-23 09:30"},
    ]


def test_export_empty_inbox_and_bad_args(tmp_path):
    box = Inbox(tmp_path / "inbox")
    assert box.export() == "# Export\n\ntotal: 0\n\nno entries\n"
    assert box.export(format="json") == "[]\n"
    for kwargs in [dict(format="yaml"), dict(category="diary"), dict(on_date="23-10-2026")]:
        try:
            box.export(**kwargs)
        except ValueError:
            continue
        raise AssertionError(f"should reject {kwargs}")


def test_export_html_offline_toc_anchors_and_escaping(tmp_path):
    box = Inbox(tmp_path / "inbox")
    box.add("fact", "First day note.", now=datetime(2026, 10, 22, 9, 0))
    box.add("preference", "Second day preference.", now=datetime(2026, 10, 23, 8, 0))
    box.add("fact", '<script>alert(1)</script> & "quotes"', now=datetime(2026, 10, 23, 9, 0))
    doc = box.export(format="html")
    assert doc.startswith("<!DOCTYPE html>\n")
    assert doc.rstrip().endswith("</html>")
    assert "total: 3" in doc
    # Fully offline: no scripts, no external resources or links.
    assert "<script" not in doc
    assert "http://" not in doc and "https://" not in doc
    assert "<style>" in doc
    # Contents list links to one section per category, with counts.
    assert '<a href="#category-fact">fact (2)</a>' in doc
    assert '<a href="#category-preference">preference (1)</a>' in doc
    assert '<section id="category-fact">' in doc
    assert '<section id="category-preference">' in doc
    assert '<section id="category-experience">' not in doc
    # Entries keep their IDs and chronological order inside their section.
    assert '<li id="entry-20261022-01">' in doc
    assert doc.index("First day note.") < doc.index("&lt;script&gt;alert(1)&lt;/script&gt;")
    # Entry text is escaped, never emitted raw.
    assert "<script>alert(1)</script>" not in doc
    assert "&lt;script&gt;alert(1)&lt;/script&gt; &amp; &quot;quotes&quot;" in doc
    # Filters apply to HTML too.
    day23 = box.export(format="html", category="fact", on_date="2026-10-23")
    assert "total: 1" in day23 and "Second day preference." not in day23
    assert "category-preference" not in day23


def test_export_html_empty_inbox(tmp_path):
    box = Inbox(tmp_path / "inbox")
    doc = box.export(format="html")
    assert doc.startswith("<!DOCTYPE html>\n")
    assert "total: 0" in doc
    assert "<p>no entries</p>" in doc
    assert "<section" not in doc
    assert "<script" not in doc


def test_export_cli_stdout_and_output_file(tmp_path, capsys):
    import json

    from musings_inbox.inbox import main

    root = str(tmp_path / "inbox")
    box = Inbox(tmp_path / "inbox")
    box.add("fact", "CLI-exported entry.", now=NOW)
    assert main(["--root", root, "export", "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["text"] == "CLI-exported entry."
    out_file = tmp_path / "nested" / "export.md"
    assert main(["--root", root, "export", "--output", str(out_file)]) == 0
    assert "exported:" in capsys.readouterr().out
    assert out_file.read_text(encoding="utf-8").startswith("# Export\n\ntotal: 1\n")
    assert "CLI-exported entry." in out_file.read_text(encoding="utf-8")
    html_file = tmp_path / "export.html"
    assert main(["--root", root, "export", "--format", "html", "--output", str(html_file)]) == 0
    assert "exported:" in capsys.readouterr().out
    html_doc = html_file.read_text(encoding="utf-8")
    assert html_doc.startswith("<!DOCTYPE html>\n")
    assert "CLI-exported entry." in html_doc
    assert main(["--root", root, "export", "--format", "html"]) == 0
    assert capsys.readouterr().out.startswith("<!DOCTYPE html>\n")


def test_rejects_empty_and_unknown(tmp_path):
    box = Inbox(tmp_path / "inbox")
    for bad in [("fact", "  "), ("diary", "hello")]:
        try:
            box.add(bad[0], bad[1], now=NOW)
        except ValueError:
            continue
        raise AssertionError(f"should reject {bad}")


def test_root_rejects_symlink(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    try:
        Inbox(link)
    except ValueError:
        return
    raise AssertionError("Inbox should reject a symlinked root")


def test_root_rejects_symlink_in_parent_prefix(tmp_path):
    real = tmp_path / "real"
    (real / "sub").mkdir(parents=True)
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    try:
        Inbox(link / "sub")
    except ValueError:
        return
    raise AssertionError("Inbox should reject a symlink in the root's parent prefix")


def test_root_rejects_relative_escape(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for bad in ["../outside", "a/../../outside", "../../x"]:
        try:
            Inbox(bad)
        except ValueError:
            continue
        raise AssertionError(f"Inbox should reject escaping relative root {bad!r}")


def test_root_accepts_absolute_and_nested_relative(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    box = Inbox(tmp_path / "abs-inbox")
    entry = box.add("fact", "Absolute roots are the caller's explicit choice.", now=NOW)
    assert entry.entry_id == "20261023-01"
    box2 = Inbox("nested/rel-inbox")
    box2.init()
    assert (tmp_path / "nested" / "rel-inbox" / "facts.md").exists()


def test_file_whitelist_rejects_unknown_names(tmp_path):
    box = Inbox(tmp_path / "inbox")
    for bad in ["evil.md", "../outside.md", "facts.md ", "FACTS.MD"]:
        try:
            box._file(bad)
        except ValueError:
            continue
        raise AssertionError(f"_file should reject {bad!r}")


def test_guarded_files_stay_inside_root(tmp_path):
    box = Inbox(tmp_path / "inbox")
    box.add("fact", "Guarded write.", now=NOW)
    for name in ("facts.md", "preferences.md", "experience.md", "materials.md", "index.md"):
        resolved = box._file(name).resolve()
        resolved.relative_to(box._root_abs)  # raises if outside


def test_symlinked_entry_file_is_refused(tmp_path):
    box = Inbox(tmp_path / "inbox")
    box.init()
    facts = box.root / "facts.md"
    facts.unlink()
    outside = tmp_path / "outside.txt"
    outside.write_text("redirected\n", encoding="utf-8")
    facts.symlink_to(outside)
    try:
        box.add("fact", "Should never land outside.", now=NOW)
    except IOError:
        pass
    else:
        raise AssertionError("add() should refuse a symlinked facts.md")
    try:
        box.verify()
    except IOError:
        return
    raise AssertionError("verify() should refuse a symlinked facts.md")


def test_cli_rejects_escaping_root(tmp_path, monkeypatch, capsys):
    from musings_inbox.inbox import main

    monkeypatch.chdir(tmp_path)
    assert main(["--root", "../escape", "init"]) == 1
    assert "escapes the working directory" in capsys.readouterr().err
    assert not (tmp_path.parent / "escape").exists()


def test_parse_tags_english_chinese_and_punctuation():
    from musings_inbox.inbox import parse_tags

    assert parse_tags("Morning walk #routine #quiet") == ["routine", "quiet"]
    assert parse_tags("一杯茶 #灵感 随后写作") == ["灵感"]
    assert parse_tags("#Trip notes, packed!") == ["trip"]
    assert parse_tags("#tag #TAG #Tag") == ["tag"]  # deduplicated, lowercased
    assert parse_tags("no tags here") == []
    assert parse_tags("# ") == []  # bare hash with no word after it
    assert parse_tags("a#b glued") == []  # glued to a word is not a tag


def test_list_entries_tag_filter(tmp_path):
    box = Inbox(tmp_path / "inbox")
    box.add("fact", "The workshop opens at nine. #routine", now=NOW)
    box.add("preference", "Quiet mornings. #Routine", now=NOW)
    box.add("experience", "No tags on this one.", now=NOW)
    tagged = box.list_entries(tag="routine")
    assert [e.entry_id for e in tagged] == ["20261023-01", "20261023-02"]
    assert all(e.tags == ["routine"] for e in tagged)
    assert [e.entry_id for e in box.list_entries(tag="#ROUTINE")] == ["20261023-01", "20261023-02"]
    assert box.list_entries(tag="missing") == []
    # tag composes with the other filters
    assert [e.entry_id for e in box.list_entries(category="fact", tag="routine")] == ["20261023-01"]
    assert box.list_entries(category="preference", tag="routine", on_date="2026-10-24") == []
    untagged = box.list_entries()
    assert untagged[2].tags == []


def test_search_tag_filter(tmp_path, capsys):
    from musings_inbox.inbox import main

    box = Inbox(tmp_path / "inbox")
    box.add("fact", "The workshop opens at nine. #routine", now=NOW)
    box.add("preference", "The workshop cat naps. No tag.", now=NOW)
    # library: tag narrows, non-entry lines never match with a tag given
    assert len(box.search("workshop")) == 2
    hits = box.search("workshop", tag="routine")
    assert len(hits) == 1 and "opens at nine" in hits[0]
    assert box.search("workshop", tag="missing") == []
    assert box.search("opens", tag="#ROUTINE") == box.search("opens", tag="routine")
    # CLI
    root = str(tmp_path / "inbox")
    assert main(["--root", root, "search", "workshop", "--tag", "routine"]) == 0
    out = capsys.readouterr().out
    assert "opens at nine" in out and "cat naps" not in out
    assert main(["--root", root, "search", "workshop", "--tag", "missing"]) == 0
    assert capsys.readouterr().out.strip() == "no matches"


def test_search_since_and_category_filters(tmp_path):
    box = Inbox(tmp_path / "inbox")
    box.add("fact", "The workshop opens at nine.", now=datetime(2026, 10, 22, 9, 0))
    box.add("fact", "The workshop kettle whistles. #routine", now=datetime(2026, 10, 23, 9, 0))
    box.add("preference", "The workshop cat naps by the stove.", now=datetime(2026, 10, 23, 8, 0))
    box.add("experience", "The workshop roof leaked in the rain.", now=datetime(2026, 10, 24, 9, 0))
    assert len(box.search("workshop")) == 4
    # --since is inclusive: the boundary day itself is kept.
    since23 = box.search("workshop", since="2026-10-23")
    assert len(since23) == 3
    for entry_id in ("20261023-01", "20261023-02", "20261024-01"):
        assert any(entry_id in ln for ln in since23)
    assert box.search("workshop", since="2026-10-25") == []
    # --category restricts to one file.
    facts = box.search("workshop", category="fact")
    assert len(facts) == 2 and all(ln.startswith("facts.md:") for ln in facts)
    assert box.search("workshop", category="material") == []
    # filters compose: category + since + tag together.
    assert len(box.search("workshop", category="fact", since="2026-10-23")) == 1
    assert box.search("workshop", category="fact", since="2026-10-24") == []
    assert len(box.search("workshop", since="2026-10-23", tag="routine")) == 1
    assert box.search("workshop", category="preference", tag="routine") == []
    # a filtered search never returns a hand-written header or note line.
    (box.root / "facts.md").write_text(
        "# Workshop notes\n- [20261022-01] 2026-10-22 09:00 — The workshop opens at nine.\n"
        "- [20261023-01] 2026-10-23 09:00 — The workshop kettle whistles. #routine\n"
        "workshop scribbled in the margin\n",
        encoding="utf-8",
    )
    assert len(box.search("workshop", category="fact")) == 2


def test_search_rejects_bad_category_and_since(tmp_path):
    box = Inbox(tmp_path / "inbox")
    box.add("fact", "Something searchable.", now=NOW)
    for kwargs in [dict(category="diary"), dict(since="23-10-2026"),
                   dict(since="2026-13-01"), dict(since="2026-10-32")]:
        try:
            box.search("searchable", **kwargs)
        except ValueError:
            continue
        raise AssertionError(f"should reject {kwargs}")


def test_search_cli_since_and_category_filters(tmp_path, capsys):
    from musings_inbox.inbox import main

    root = str(tmp_path / "inbox")
    box = Inbox(tmp_path / "inbox")
    box.add("fact", "The workshop opens at nine.", now=datetime(2026, 10, 22, 9, 0))
    box.add("preference", "The workshop cat naps.", now=datetime(2026, 10, 23, 8, 0))
    assert main(["--root", root, "search", "workshop", "--since", "2026-10-23"]) == 0
    out = capsys.readouterr().out
    assert "cat naps" in out and "opens at nine" not in out
    assert main(["--root", root, "search", "workshop", "--category", "fact"]) == 0
    out = capsys.readouterr().out
    assert "opens at nine" in out and "cat naps" not in out
    assert main(["--root", root, "search", "workshop", "--since", "2026-10-24"]) == 0
    assert capsys.readouterr().out.strip() == "no matches"
    assert main(["--root", root, "search", "workshop", "--since", "bad-date"]) == 1
    assert "invalid date" in capsys.readouterr().err


def test_list_cli_tag_filter(tmp_path, capsys):
    from musings_inbox.inbox import main

    root = str(tmp_path / "inbox")
    box = Inbox(tmp_path / "inbox")
    box.add("fact", "Tagged entry. #trip", now=NOW)
    box.add("fact", "Untagged entry.", now=NOW)
    assert main(["--root", root, "list", "--tag", "trip"]) == 0
    out = capsys.readouterr().out
    assert "Tagged entry." in out and "Untagged entry." not in out


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read_shipped(path: Path) -> str:
    # Every shipped template/doc must honor the trailing-newline discipline
    # the protocol itself teaches, so read bytes and check the tail.
    data = path.read_bytes()
    assert data.endswith(b"\n"), f"{path} must end with a newline"
    return data.decode("utf-8")


def test_zh_template_pack_is_complete():
    zh = REPO_ROOT / "templates" / "zh"
    expected = {"facts.md", "preferences.md", "experience.md", "materials.md",
                "index.md", "README.md"}
    assert {p.name for p in zh.glob("*.md")} == expected
    headers = {"facts.md": "# 事实", "preferences.md": "# 偏好",
               "experience.md": "# 经验", "materials.md": "# 素材",
               "index.md": "# 索引"}
    for name, header in headers.items():
        text = _read_shipped(zh / name)
        assert text.startswith(header), f"{name} must start with {header}"
    index_text = _read_shipped(zh / "index.md")
    assert "| 编号 | 时间 | 类别 | 摘要 |" in index_text
    readme = _read_shipped(zh / "README.md")
    assert "docs/protocol.md" in readme


def test_zh_templates_carry_no_fictional_entries():
    # Templates ship guidance only; a "- [ID]" entry line must not appear.
    import re as _re

    zh = REPO_ROOT / "templates" / "zh"
    for name in ("facts.md", "preferences.md", "experience.md", "materials.md"):
        text = _read_shipped(zh / name)
        assert not _re.search(r"^-\s\[\d{8}-\d+\]", text, _re.M), \
            f"{name} must not contain an entry line"


def test_protocol_doc_covers_the_protocol():
    doc = _read_shipped(REPO_ROOT / "docs" / "protocol.md")
    for phrase in [
        "Musings", "随想",
        "- [YYYYMMDD-NN] YYYY-MM-DD HH:MM",  # entry line format
        "| YYYYMMDD-NN |",                    # index row format
        "real clock",                         # time discipline
        "read-back",                          # verification discipline
        "whitelist",                          # security model
        "#tags",                              # tag syntax
        "--since",                            # search date filter
        "--category",                         # search category filter
        "backup",                             # timestamped backups
        "restore",                            # restore with integrity checks
        "SKILL.md",                           # relation to the short edition
    ]:
        assert phrase in doc, f"protocol.md should document {phrase!r}"


def _pyproject_version():
    import re

    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
    assert m, "could not find version in pyproject.toml"
    return m.group(1)


def test_release_version_is_consistent():
    """Release hygiene: pyproject version must match the latest CHANGELOG section."""
    version = _pyproject_version()
    changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## [{version}]" in changelog, (
        f"pyproject version {version} has no matching CHANGELOG section"
    )


SAMPLE_INBOX = REPO_ROOT / "examples" / "sample-inbox"


def test_sample_inbox_verify_passes():
    """The shipped worked example must be a consistent, verifiable inbox."""
    from musings_inbox.inbox import Inbox

    fingerprints = Inbox(SAMPLE_INBOX).verify()
    assert set(fingerprints) == {"facts.md", "preferences.md", "experience.md",
                                 "materials.md", "index.md"}


def test_sample_inbox_is_reproducible(tmp_path):
    """The generator script must rebuild the shipped copy byte-for-byte."""
    import subprocess
    import sys

    out = subprocess.run(
        [sys.executable, str(REPO_ROOT / "examples" / "generate-sample-inbox.py"),
         str(tmp_path / "sample-inbox")],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert out.returncode == 0, out.stderr
    for name in ("facts.md", "preferences.md", "experience.md",
                 "materials.md", "index.md"):
        rebuilt = tmp_path / "sample-inbox" / name
        shipped = SAMPLE_INBOX / name
        assert rebuilt.exists(), f"generator did not produce {name}"
        assert rebuilt.read_bytes() == shipped.read_bytes(), \
            f"shipped {name} drifted from the generator script"


def test_sample_inbox_coverage():
    """The example exercises every feature the walkthrough demonstrates."""
    from musings_inbox.inbox import Inbox

    box = Inbox(SAMPLE_INBOX)
    entries = box.list_entries()
    assert len(entries) == 12
    by_category = {}
    for entry in entries:
        by_category[entry.category] = by_category.get(entry.category, 0) + 1
    assert by_category == {"fact": 5, "preference": 2, "experience": 3, "material": 2}
    # tags: english and chinese, exercised by search/list --tag
    assert [e.entry_id for e in box.list_entries(tag="food")] == ["20261022-01", "20261023-01"]
    assert [e.entry_id for e in box.list_entries(tag="灵感")] == ["20261024-03"]
    assert box.search("workshop", tag="routine")
    # entry IDs ascend within each day in chronological order
    for a, b in zip(entries, entries[1:]):
        assert (a.timestamp, a.entry_id) <= (b.timestamp, b.entry_id)
    assert entries[0].entry_id == "20261020-01"
    assert entries[-1].entry_id == "20261024-03"


def test_walkthrough_doc_covers_steps():
    doc = _read_shipped(REPO_ROOT / "docs" / "walkthrough.md")
    for phrase in [
        "examples/sample-inbox",        # the worked example it queries
        "verify",                       # step 1: trust the disk
        "stats",                        # step 2: shape of the log
        "search workshop --tag",        # step 3: tag-filtered search
        "list --tag",                   # step 4: list filters
        "export --format json",         # step 5: backup/migration
        "add --type",                   # step 6: filing your own entries
        "docs/protocol.md",             # where the rules live
        "fictional",                    # all entries are invented
    ]:
        assert phrase in doc, f"walkthrough.md should cover {phrase!r}"
    assert "generate-sample-inbox.py" in doc  # reproducible, not hand-written


def _seeded_inbox(tmp_path, name="src"):
    """An inbox with three fictional entries across two days and tags."""
    box = Inbox(tmp_path / name)
    box.add("fact", "The workshop opens at nine. #routine", now=datetime(2026, 10, 22, 9, 0))
    box.add("preference", "Quiet mornings before the kettle boils.", now=datetime(2026, 10, 23, 8, 0))
    box.add("experience", "Fixed a glued index line by splitting it.", now=datetime(2026, 10, 23, 9, 30))
    return box


def test_import_json_round_trip(tmp_path):
    src = _seeded_inbox(tmp_path)
    payload = src.export(format="json")
    import_file = tmp_path / "export.json"
    import_file.write_text(payload, encoding="utf-8")
    dst = Inbox(tmp_path / "dst")
    result = dst.import_entries(import_file)
    assert result.duplicates == 0 and not result.dry_run
    assert [(e.category, e.text, e.timestamp) for e in result.imported] == [
        ("fact", "The workshop opens at nine. #routine", "2026-10-22 09:00"),
        ("preference", "Quiet mornings before the kettle boils.", "2026-10-23 08:00"),
        ("experience", "Fixed a glued index line by splitting it.", "2026-10-23 09:30"),
    ]
    # Timestamps are preserved; IDs are freshly assigned for the new inbox.
    assert [e.entry_id for e in result.imported] == ["20261022-01", "20261023-01", "20261023-02"]
    assert result.imported[0].tags == ["routine"]
    assert dst.verify()
    assert [e.text for e in dst.list_entries()] == [e.text for e in src.list_entries()]


def test_import_markdown_export_round_trip(tmp_path):
    src = _seeded_inbox(tmp_path)
    import_file = tmp_path / "export.md"
    import_file.write_text(src.export(), encoding="utf-8")
    dst = Inbox(tmp_path / "dst")
    result = dst.import_entries(import_file)
    assert len(result.imported) == 3 and result.duplicates == 0
    assert [e.entry_id for e in result.imported] == ["20261022-01", "20261023-01", "20261023-02"]
    assert dst.verify()
    # The empty export imports cleanly as zero entries.
    empty_file = tmp_path / "empty.md"
    empty_file.write_text(Inbox(tmp_path / "empty-src").export(), encoding="utf-8")
    empty_result = Inbox(tmp_path / "empty-dst").import_entries(empty_file)
    assert empty_result.imported == [] and empty_result.duplicates == 0


def test_import_deduplicates_on_reimport(tmp_path):
    src = _seeded_inbox(tmp_path)
    import_file = tmp_path / "export.json"
    import_file.write_text(src.export(format="json"), encoding="utf-8")
    dst = Inbox(tmp_path / "dst")
    first = dst.import_entries(import_file)
    assert len(first.imported) == 3
    second = dst.import_entries(import_file)
    assert second.imported == [] and second.duplicates == 3
    assert len(dst.list_entries()) == 3
    # Importing an inbox's own export into itself is all duplicates.
    own = src.import_entries(import_file)
    assert own.imported == [] and own.duplicates == 3
    # Duplicates inside one file are counted too.
    doubled = tmp_path / "doubled.json"
    doubled.write_text(src.export(format="json").replace("]\n", "") + ",\n"
                       + src.export(format="json").strip()[1:], encoding="utf-8")
    fresh = Inbox(tmp_path / "fresh")
    result = fresh.import_entries(doubled)
    assert len(result.imported) == 3 and result.duplicates == 3


def test_import_dry_run_writes_nothing(tmp_path):
    src = _seeded_inbox(tmp_path)
    import_file = tmp_path / "export.md"
    import_file.write_text(src.export(), encoding="utf-8")
    dst_root = tmp_path / "dst"
    dst = Inbox(dst_root)
    result = dst.import_entries(import_file, dry_run=True)
    assert result.dry_run and len(result.imported) == 3 and result.duplicates == 0
    assert result.imported[0].entry_id == "20261022-01"  # the ID it would receive
    assert not dst_root.exists()  # not even init() ran
    # Dry run against an inbox that already holds the entries: all duplicates.
    again = src.import_entries(import_file, dry_run=True)
    assert again.imported == [] and again.duplicates == 3
    assert len(src.list_entries()) == 3


def test_import_markdown_category_file(tmp_path):
    src = _seeded_inbox(tmp_path)
    category_file = tmp_path / "facts.md"
    category_file.write_text((src.root / "facts.md").read_text(encoding="utf-8"), encoding="utf-8")
    dst = Inbox(tmp_path / "dst")
    # Without --category the file has no category per line: rejected.
    try:
        dst.import_entries(category_file)
    except ValueError as exc:
        assert "--category" in str(exc)
    else:
        raise AssertionError("category-file import without --category should raise")
    assert not (tmp_path / "dst").exists()
    result = dst.import_entries(category_file, category="fact")
    assert len(result.imported) == 1 and result.imported[0].category == "fact"
    assert result.imported[0].timestamp == "2026-10-22 09:00"
    assert dst.verify()


def test_import_rejects_bad_json_and_writes_nothing(tmp_path):
    dst = Inbox(tmp_path / "dst")
    bad_cases = [
        "{not json",
        '{"entry_id": "20261023-01"}',  # not a list
        '[{"category": "diary", "text": "No such category.", "timestamp": "2026-10-23 09:00"}]',
        '[{"category": "fact", "text": "Bad month.", "timestamp": "2026-13-01 09:00"}]',
        '[{"category": "fact", "text": "Bad shape.", "timestamp": "23-10-2026 09:00"}]',
        '[{"category": "fact", "text": "   ", "timestamp": "2026-10-23 09:00"}]',
        '[{"category": "fact", "timestamp": "2026-10-23 09:00"}]',  # missing text
        '["just a string"]',
    ]
    for i, payload in enumerate(bad_cases):
        bad_file = tmp_path / f"bad{i}.json"
        bad_file.write_text(payload, encoding="utf-8")
        try:
            dst.import_entries(bad_file)
        except ValueError:
            continue
        raise AssertionError(f"bad JSON case {i} should raise ValueError")
    assert not (tmp_path / "dst").exists()
    assert dst.list_entries() == []


def test_import_rejects_bad_markdown_and_writes_nothing(tmp_path):
    dst = Inbox(tmp_path / "dst")
    bad = (
        "# Export\n\ntotal: 2\n\n"
        "- [20261023-01] 2026-10-23 09:00 [fact] A fine entry.\n"
        "this line matches no entry shape\n"
        "- [20261023-02] 2026-10-23 09:30 [diary] Unknown category.\n"
    )
    bad_file = tmp_path / "bad.md"
    bad_file.write_text(bad, encoding="utf-8")
    try:
        dst.import_entries(bad_file)
    except ValueError as exc:
        assert "line 6" in str(exc) and "line 7" in str(exc)
    else:
        raise AssertionError("bad Markdown import should raise ValueError")
    assert not (tmp_path / "dst").exists()
    # --format json on a Markdown file fails to parse as JSON.
    md_file = tmp_path / "export.md"
    md_file.write_text("- [20261023-01] 2026-10-23 09:00 [fact] Fine.\n", encoding="utf-8")
    try:
        dst.import_entries(md_file, format="json")
    except ValueError:
        pass
    else:
        raise AssertionError("--format json on Markdown should raise ValueError")
    # An undetectable suffix cannot auto-detect a format.
    dat_file = tmp_path / "export.dat"
    dat_file.write_text("[]", encoding="utf-8")
    try:
        dst.import_entries(dat_file)
    except ValueError as exc:
        assert "cannot detect import format" in str(exc)
    else:
        raise AssertionError("undetectable suffix should raise ValueError")
    assert not (tmp_path / "dst").exists()


def test_import_cli(tmp_path, capsys):
    from musings_inbox.inbox import main

    src = _seeded_inbox(tmp_path)
    import_file = tmp_path / "export.json"
    import_file.write_text(src.export(format="json"), encoding="utf-8")
    root = str(tmp_path / "dst")
    assert main(["--root", root, "import", "--file", str(import_file), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "dry run: no changes written" in out
    assert "imported: 3" in out and "duplicates skipped: 0" in out
    assert not (tmp_path / "dst").exists()
    assert main(["--root", root, "import", "--file", str(import_file)]) == 0
    out = capsys.readouterr().out
    assert "imported: 3" in out
    assert "20261023-02" in out  # the imported entries are listed
    assert main(["--root", root, "import", "--file", str(import_file)]) == 0
    out = capsys.readouterr().out
    assert "imported: 0" in out and "duplicates skipped: 3" in out
    # A bad file fails through the CLI with exit code 1 and no partial import.
    bad_file = tmp_path / "bad.json"
    bad_file.write_text('[{"category": "fact", "text": "", "timestamp": "2026-10-23 09:00"}]', encoding="utf-8")
    assert main(["--root", root, "import", "--file", str(bad_file)]) == 1
    assert "error:" in capsys.readouterr().err
    assert len(Inbox(tmp_path / "dst").list_entries()) == 3


def _doctor_check_names(report, severity=None):
    """(check, message) pairs from a doctor report, optionally severity-filtered."""
    return [(i.check, i.message) for i in report.issues
            if severity is None or i.severity == severity]


def test_doctor_healthy_inbox(tmp_path):
    box = _seeded_inbox(tmp_path)
    report = box.doctor()
    assert report.ok and report.issues == []
    # Fingerprints are the same values verify() reports.
    assert report.fingerprints == box.verify()
    assert set(report.fingerprints) == {"facts.md", "preferences.md", "experience.md",
                                        "materials.md", "index.md"}


def test_doctor_empty_initialized_inbox_is_healthy(tmp_path):
    box = Inbox(tmp_path / "inbox")
    box.init()
    report = box.doctor()
    assert report.ok and report.issues == []
    assert len(report.fingerprints) == 5


def test_doctor_missing_trailing_newline(tmp_path):
    box = _seeded_inbox(tmp_path)
    facts = box.root / "facts.md"
    facts.write_bytes(facts.read_bytes().rstrip(b"\n"))
    report = box.doctor()
    assert not report.ok
    errors = _doctor_check_names(report, "error")
    assert ("trailing newline", "facts.md does not end with a newline") in errors
    assert all(check != "index consistency" for check, _ in errors)


def test_doctor_index_mismatch(tmp_path):
    box = _seeded_inbox(tmp_path)
    index = box.root / "index.md"
    lines = [ln for ln in index.read_text(encoding="utf-8").splitlines()
             if "20261022-01" not in ln]
    index.write_text("\n".join(lines) + "\n", encoding="utf-8")
    report = box.doctor()
    assert not report.ok
    errors = _doctor_check_names(report, "error")
    assert any(check == "index consistency" and "20261022-01" in msg
               and "missing from index" in msg for check, msg in errors)


def test_doctor_duplicate_entry_ids(tmp_path):
    box = _seeded_inbox(tmp_path)
    facts = box.root / "facts.md"
    line = [ln for ln in facts.read_text(encoding="utf-8").splitlines()
            if ln.startswith("- [")][0]
    with facts.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    report = box.doctor()
    assert not report.ok
    errors = _doctor_check_names(report, "error")
    assert any(check == "duplicate entry ids" and "20261022-01" in msg
               and "2 times" in msg for check, msg in errors)


def test_doctor_malformed_entry_and_index_lines(tmp_path):
    box = _seeded_inbox(tmp_path)
    facts = box.root / "facts.md"
    with facts.open("a", encoding="utf-8") as fh:
        fh.write("- [20260101-99] forged\n")
    index = box.root / "index.md"
    with index.open("a", encoding="utf-8") as fh:
        fh.write("| 20261023-01 | not-a-date | fact | broken row |\n")
    report = box.doctor()
    assert not report.ok
    errors = _doctor_check_names(report, "error")
    assert any(check == "entry format" and "facts.md" in msg for check, msg in errors)
    assert any(check == "index format" and "index.md" in msg for check, msg in errors)


def test_doctor_missing_file(tmp_path):
    box = _seeded_inbox(tmp_path)
    (box.root / "materials.md").unlink()
    report = box.doctor()
    assert not report.ok
    errors = _doctor_check_names(report, "error")
    assert any(check == "files present" and "materials.md is missing" in msg
               for check, msg in errors)
    # A missing file reports just itself, not a cascade of consistency errors.
    assert all(check != "index consistency" for check, _ in errors)
    assert "materials.md" not in report.fingerprints


def test_doctor_file_permissions(tmp_path):
    import os

    box = _seeded_inbox(tmp_path)
    facts = box.root / "facts.md"
    os.chmod(facts, 0o666)  # world-writable: an error
    report = box.doctor()
    assert not report.ok
    assert any(check == "file permissions" and "world-writable" in msg
               for check, msg in _doctor_check_names(report, "error"))
    os.chmod(facts, 0o660)  # group-writable is the normal umask-002 state: fine
    report = box.doctor()
    assert report.ok and report.issues == []


def test_doctor_uninitialized_inbox_reports_missing_files(tmp_path):
    root = tmp_path / "inbox"
    box = Inbox(root)
    report = box.doctor()
    assert not report.ok
    errors = _doctor_check_names(report, "error")
    assert len([c for c, _ in errors if c == "files present"]) == 5
    assert report.fingerprints == {}
    assert not root.exists()  # doctor never writes


def test_doctor_symlinked_file(tmp_path):
    box = _seeded_inbox(tmp_path)
    facts = box.root / "facts.md"
    facts.unlink()
    outside = tmp_path / "outside.txt"
    outside.write_text("# Facts\n", encoding="utf-8")
    facts.symlink_to(outside)
    report = box.doctor()
    assert not report.ok
    assert any(check == "file access" and "symlink" in msg
               for check, msg in _doctor_check_names(report, "error"))


def test_doctor_does_not_write(tmp_path):
    box = _seeded_inbox(tmp_path)
    before = box.verify()
    report = box.doctor()
    assert report.ok
    assert box.verify() == before  # fingerprints unchanged: nothing was written


def test_doctor_cli(tmp_path, capsys):
    from musings_inbox.inbox import main

    root = str(tmp_path / "inbox")
    box = _seeded_inbox(tmp_path, name="inbox")
    assert main(["--root", root, "doctor"]) == 0
    out = capsys.readouterr().out
    assert "[ok] files present" in out
    assert "[ok] index consistency" in out
    assert "fingerprints:" in out and "facts.md " in out
    assert "OK: inbox is healthy" in out
    # Break it: strip the trailing newline and the CLI must fail loudly.
    facts = box.root / "facts.md"
    facts.write_bytes(facts.read_bytes().rstrip(b"\n"))
    assert main(["--root", root, "doctor"]) == 1
    out = capsys.readouterr().out
    assert "[error] trailing newline: facts.md does not end with a newline" in out
    assert "doctor found 1 error(s) and 0 warning(s)" in out
    assert "OK: inbox is healthy" not in out


def _backup_manifest(backup_dir: Path) -> dict:
    import json

    return json.loads((backup_dir / "manifest.json").read_text(encoding="utf-8"))


def _resign_manifest(backup_dir: Path) -> None:
    """Rewrite manifest.json fingerprints to match the files on disk.

    Used to build backups that are internally consistent except for the
    one defect the test wants to exercise (e.g. index/content mismatch).
    """
    import hashlib
    import json

    manifest = _backup_manifest(backup_dir)
    manifest["files"] = {
        name: hashlib.md5((backup_dir / name).read_bytes()).hexdigest()
        for name in ("facts.md", "preferences.md", "experience.md",
                     "materials.md", "index.md")
    }
    (backup_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def test_backup_creates_timestamped_dir_with_manifest(tmp_path):
    import hashlib

    box = _seeded_inbox(tmp_path)
    when = datetime(2026, 10, 23, 9, 30, 15)
    result = box.backup(tmp_path / "backups", now=when)
    assert result.path == tmp_path / "backups" / "musings-inbox-backup-20261023-093015"
    assert result.created == "2026-10-23 09:30"
    assert result.entries == 3
    manifest = _backup_manifest(result.path)
    assert manifest["format"] == "musings-inbox-backup"
    assert manifest["version"] == 1
    assert manifest["created"] == "2026-10-23 09:30"
    assert manifest["entries"] == 3
    assert set(manifest["files"]) == {"facts.md", "preferences.md", "experience.md",
                                      "materials.md", "index.md"}
    for name in ("facts.md", "preferences.md", "experience.md",
                 "materials.md", "index.md"):
        copied = result.path / name
        assert copied.read_bytes() == (box.root / name).read_bytes()
        assert manifest["files"][name] == hashlib.md5(copied.read_bytes()).hexdigest()
    assert result.fingerprints == manifest["files"]


def test_backup_same_second_gets_suffix(tmp_path):
    box = _seeded_inbox(tmp_path)
    when = datetime(2026, 10, 23, 9, 30, 15)
    first = box.backup(tmp_path / "backups", now=when)
    second = box.backup(tmp_path / "backups", now=when)
    assert first.path.name == "musings-inbox-backup-20261023-093015"
    assert second.path.name == "musings-inbox-backup-20261023-093015-2"
    assert first.path != second.path
    assert first.path.exists() and second.path.exists()


def test_backup_requires_complete_inbox(tmp_path):
    box = Inbox(tmp_path / "inbox")  # never initialized
    try:
        box.backup(tmp_path / "backups")
    except ValueError as exc:
        assert "missing inbox files" in str(exc)
    else:
        raise AssertionError("backup of an uninitialized inbox should raise")
    assert not (tmp_path / "backups").exists()
    # One file missing is enough to refuse.
    seeded = _seeded_inbox(tmp_path)
    (seeded.root / "materials.md").unlink()
    try:
        seeded.backup(tmp_path / "backups")
    except ValueError:
        pass
    else:
        raise AssertionError("backup with a missing file should raise")
    assert not (tmp_path / "backups").exists()


def test_restore_round_trip_keeps_ids_and_timestamps(tmp_path):
    src = _seeded_inbox(tmp_path)
    result = src.backup(tmp_path / "backups", now=datetime(2026, 10, 23, 9, 30, 15))
    dst = Inbox(tmp_path / "dst")
    restored = dst.restore(result.path)
    assert not restored.dry_run
    assert [(e.entry_id, e.category, e.text, e.timestamp) for e in restored.restored] == [
        ("20261022-01", "fact", "The workshop opens at nine. #routine", "2026-10-22 09:00"),
        ("20261023-01", "preference", "Quiet mornings before the kettle boils.", "2026-10-23 08:00"),
        ("20261023-02", "experience", "Fixed a glued index line by splitting it.", "2026-10-23 09:30"),
    ]
    assert dst.verify()
    assert [e.text for e in dst.list_entries()] == [e.text for e in src.list_entries()]
    assert restored.fingerprints == result.fingerprints


def test_restore_replaces_current_contents(tmp_path):
    src = _seeded_inbox(tmp_path)
    result = src.backup(tmp_path / "backups", now=datetime(2026, 10, 23, 9, 30, 15))
    dst = Inbox(tmp_path / "dst")
    dst.add("fact", "A later entry that must not survive the restore.",
            now=datetime(2026, 10, 24, 10, 0))
    assert len(dst.list_entries()) == 1
    restored = dst.restore(result.path)
    assert len(restored.restored) == 3
    assert [e.text for e in dst.list_entries()] == [e.text for e in src.list_entries()]
    assert dst.verify()


def test_restore_dry_run_writes_nothing(tmp_path):
    src = _seeded_inbox(tmp_path)
    result = src.backup(tmp_path / "backups", now=datetime(2026, 10, 23, 9, 30, 15))
    dst_root = tmp_path / "dst"
    dst = Inbox(dst_root)
    restored = dst.restore(result.path, dry_run=True)
    assert restored.dry_run and len(restored.restored) == 3
    assert restored.restored[0].entry_id == "20261022-01"  # the entry it would restore
    assert not dst_root.exists()
    # Dry run against an inbox that already holds the entries: no writes.
    before = src.verify()
    again = src.restore(result.path, dry_run=True)
    assert len(again.restored) == 3
    assert src.verify() == before


def test_restore_rejects_tampered_backup_and_writes_nothing(tmp_path):
    src = _seeded_inbox(tmp_path)
    result = src.backup(tmp_path / "backups", now=datetime(2026, 10, 23, 9, 30, 15))
    facts = result.path / "facts.md"
    with facts.open("a", encoding="utf-8") as fh:
        fh.write("- [20261024-99] 2026-10-24 09:00 — Tampered entry.\n")
    dst_root = tmp_path / "dst"
    dst = Inbox(dst_root)
    try:
        dst.restore(result.path)
    except ValueError as exc:
        assert "does not match the manifest fingerprint" in str(exc)
    else:
        raise AssertionError("restore of a tampered backup should raise")
    assert not dst_root.exists()


def test_restore_rejects_missing_manifest_and_missing_file(tmp_path):
    src = _seeded_inbox(tmp_path)
    result = src.backup(tmp_path / "backups", now=datetime(2026, 10, 23, 9, 30, 15))
    dst = Inbox(tmp_path / "dst")
    (result.path / "manifest.json").unlink()
    try:
        dst.restore(result.path)
    except ValueError as exc:
        assert "manifest.json is missing" in str(exc)
    else:
        raise AssertionError("restore without a manifest should raise")
    assert not (tmp_path / "dst").exists()
    # A backup missing one inbox file fails too.
    result2 = src.backup(tmp_path / "backups", now=datetime(2026, 10, 23, 9, 31, 0))
    (result2.path / "materials.md").unlink()
    try:
        dst.restore(result2.path)
    except ValueError as exc:
        assert "materials.md is missing" in str(exc)
    else:
        raise AssertionError("restore missing a file should raise")
    assert not (tmp_path / "dst").exists()
    # A path that is not a backup directory at all.
    try:
        dst.restore(tmp_path / "no-such-backup")
    except ValueError as exc:
        assert "not found" in str(exc)
    else:
        raise AssertionError("restore of a missing directory should raise")


def test_restore_rejects_index_mismatch(tmp_path):
    src = _seeded_inbox(tmp_path)
    result = src.backup(tmp_path / "backups", now=datetime(2026, 10, 23, 9, 30, 15))
    index = result.path / "index.md"
    lines = [ln for ln in index.read_text(encoding="utf-8").splitlines()
             if "20261022-01" not in ln]
    index.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _resign_manifest(result.path)  # fingerprints now match; only the index is wrong
    dst = Inbox(tmp_path / "dst")
    try:
        dst.restore(result.path)
    except ValueError as exc:
        assert "index/content mismatch" in str(exc) and "20261022-01" in str(exc)
    else:
        raise AssertionError("restore with an inconsistent index should raise")
    assert not (tmp_path / "dst").exists()


def test_restore_rejects_unknown_format_and_version(tmp_path):
    import json

    src = _seeded_inbox(tmp_path)
    result = src.backup(tmp_path / "backups", now=datetime(2026, 10, 23, 9, 30, 15))
    dst = Inbox(tmp_path / "dst")
    manifest_path = result.path / "manifest.json"
    manifest = _backup_manifest(result.path)
    manifest["format"] = "some-other-backup"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
    try:
        dst.restore(result.path)
    except ValueError as exc:
        assert "unknown backup format" in str(exc)
    else:
        raise AssertionError("restore with an unknown format should raise")
    manifest["format"] = "musings-inbox-backup"
    manifest["version"] = 99
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
    try:
        dst.restore(result.path)
    except ValueError as exc:
        assert "unsupported backup version" in str(exc)
    else:
        raise AssertionError("restore with an unsupported version should raise")
    assert not (tmp_path / "dst").exists()


def test_restore_rejects_symlinked_backup_file(tmp_path):
    src = _seeded_inbox(tmp_path)
    result = src.backup(tmp_path / "backups", now=datetime(2026, 10, 23, 9, 30, 15))
    facts = result.path / "facts.md"
    facts.unlink()
    outside = tmp_path / "outside.txt"
    outside.write_text("# Facts\n", encoding="utf-8")
    facts.symlink_to(outside)
    dst = Inbox(tmp_path / "dst")
    try:
        dst.restore(result.path)
    except ValueError as exc:
        assert "symlink" in str(exc)
    else:
        raise AssertionError("restore with a symlinked backup file should raise")
    assert not (tmp_path / "dst").exists()


def test_backup_restore_cli(tmp_path, capsys):
    from musings_inbox.inbox import main

    src = _seeded_inbox(tmp_path, name="inbox")
    root = str(tmp_path / "inbox")
    backups = str(tmp_path / "backups")
    assert main(["--root", root, "backup", "--output", backups]) == 0
    out = capsys.readouterr().out
    assert "backup: " in out and "musings-inbox-backup-" in out
    assert "entries: 3" in out
    backup_dir = next((tmp_path / "backups").iterdir())
    dst_root = str(tmp_path / "dst")
    assert main(["--root", dst_root, "restore", "--from", str(backup_dir), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "dry run: no changes written" in out
    assert "restored: 3" in out
    assert not (tmp_path / "dst").exists()
    assert main(["--root", dst_root, "restore", "--from", str(backup_dir)]) == 0
    out = capsys.readouterr().out
    assert "restored: 3" in out
    assert "20261023-02" in out
    assert Inbox(tmp_path / "dst").verify()
    # A tampered backup fails through the CLI with exit code 1 and no restore.
    facts = backup_dir / "facts.md"
    with facts.open("a", encoding="utf-8") as fh:
        fh.write("- [20261024-99] 2026-10-24 09:00 — Tampered entry.\n")
    assert main(["--root", str(tmp_path / "dst2"), "restore", "--from", str(backup_dir)]) == 1
    assert "error:" in capsys.readouterr().err
    assert not (tmp_path / "dst2").exists()
