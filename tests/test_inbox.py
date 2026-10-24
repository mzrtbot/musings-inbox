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


def test_rejects_empty_and_unknown(tmp_path):
    box = Inbox(tmp_path / "inbox")
    for bad in [("fact", "  "), ("diary", "hello")]:
        try:
            box.add(bad[0], bad[1], now=NOW)
        except ValueError:
            continue
        raise AssertionError(f"should reject {bad}")
