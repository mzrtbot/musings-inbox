#!/bin/sh
# Fictional demo entries only — no real log content.
set -e
cd "$(dirname "$0")/.."
export PYTHONPATH=src
python3 -m musings_inbox.inbox --root /tmp/demo-inbox init
python3 -m musings_inbox.inbox --root /tmp/demo-inbox add --type fact --text "Ada's workshop opens at nine."
python3 -m musings_inbox.inbox --root /tmp/demo-inbox add --type preference --text "Quiet mornings, no meetings before ten."
python3 -m musings_inbox.inbox --root /tmp/demo-inbox search workshop
python3 -m musings_inbox.inbox --root /tmp/demo-inbox verify
