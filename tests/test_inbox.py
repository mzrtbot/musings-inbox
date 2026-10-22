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


def test_rejects_empty_and_unknown(tmp_path):
    box = Inbox(tmp_path / "inbox")
    for bad in [("fact", "  "), ("diary", "hello")]:
        try:
            box.add(bad[0], bad[1], now=NOW)
        except ValueError:
            continue
        raise AssertionError(f"should reject {bad}")
