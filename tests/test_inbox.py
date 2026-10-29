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
