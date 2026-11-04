#!/usr/bin/env python3
"""Generate the fictional worked-example inbox at examples/sample-inbox/.

Every entry below is fictional — invented people, places, and times chosen
to exercise every feature (all four categories, English and Chinese #tags,
multiple dates). Regenerating produces byte-identical files, so the shipped
copy is always in sync with this fixture list.

Usage:
    python3 examples/generate-sample-inbox.py [target-dir]
"""
import shutil
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from musings_inbox.inbox import Inbox  # noqa: E402

BANNER = (
    "> This is a fictional example inbox: invented people, places, and times.\n"
    "> It exists to demonstrate the protocol — see docs/walkthrough.md.\n"
)

# (category, timestamp, text) — listed in chronological order so entry IDs
# are generated per day exactly as the library would assign them.
SAMPLE_ENTRIES = [
    ("fact", "2026-10-20 09:30",
     "Ada opens her pottery workshop at nine every morning. #routine"),
    ("preference", "2026-10-20 09:45",
     "Quiet mornings: no meetings before ten. #routine"),
    ("experience", "2026-10-21 09:10",
     "A glued line once cost an hour — always check the file tail before appending. #discipline"),
    ("fact", "2026-10-21 18:05",
     "Bruno's birthday is 14 May; he turns 30 in 2027. #personal"),
    ("material", "2026-10-21 18:30",
     'Quote: "We shape our tools, and thereafter our tools shape us." #quotes'),
    ("fact", "2026-10-22 09:00",
     "The Blue Heron Cafe closes on Mondays. #food"),
    ("experience", "2026-10-22 21:10",
     "A read-back after every write caught a dropped index row today. #verify"),
    ("fact", "2026-10-23 11:15",
     "The night market opens at six on Fridays. #food"),
    ("preference", "2026-10-23 11:20",
     "Prefer aisle seats on trains. #travel"),
    ("material", "2026-10-24 10:30",
     "A field guide to urban birdwatching — chapters on gulls. #reading"),
    ("experience", "2026-10-24 10:45",
     "Back up the inbox before any manual edit. #discipline"),
    ("fact", "2026-10-24 11:00",
     "午后沿河散步是放空的好办法。 #灵感"),
]

FILES = ("facts.md", "preferences.md", "experience.md", "materials.md", "index.md")


def build(target: Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    box = Inbox(target)
    box.init()
    # Mark every shipped file as fictional data: plain non-entry lines are
    # never treated as entries by the parser, so this banner cannot be
    # mistaken for a log record by list/search/verify.
    for name in FILES:
        p = target / name
        p.write_text(p.read_text(encoding="utf-8") + BANNER, encoding="utf-8")
    for category, timestamp, text in SAMPLE_ENTRIES:
        box.add(category, text, now=datetime.strptime(timestamp, "%Y-%m-%d %H:%M"))
    fingerprints = box.verify()
    print(f"built {target} — {len(SAMPLE_ENTRIES)} entries, index and content agree")
    for name, digest in fingerprints.items():
        print(f"  {name} {digest}")


if __name__ == "__main__":
    build(Path(sys.argv[1]) if len(sys.argv) > 1 else REPO_ROOT / "examples" / "sample-inbox")
