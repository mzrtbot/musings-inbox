# musings-inbox protocol — full reference

The musings-inbox is a local-first life-log / inspiration inbox for file-capable
AI agents: a message with a trigger word gets classified, timestamped, appended
to one of four Markdown files, indexed, and verified by read-back — all on the
user's own disk, with no vendor lock-in. `SKILL.md` in this repo is the short
operational edition of this document; this file is the full reference.

## 1. Trigger words

A message whose **first word** is `Musings` or `随想` means: **file this, do not
debate it**. Matching rules:

- Case-insensitive (`musings`, `MUSINGS`, `随想` — Chinese has no case).
- It must be a standalone word at the start of the message — a message that
  merely contains the word in the middle does not trigger filing.
- The trigger word must be followed by punctuation or a space
  (e.g. `Musings:`, `随想：`, `Musings about lunch`).

When triggered, the agent runs the filing protocol below in the same turn.

## 2. The only permitted time source

Timestamps come from a **real clock read taken in that turn** — never from
memory, estimation, or a previous turn's reading.

- Entry ID: `YYYYMMDD-NN` (two-digit sequence per day, e.g. `20261023-02`).
- Timestamp: `YYYY-MM-DD HH:MM` (24-hour, e.g. `2026-10-23 09:30`).
- The reported timestamp is reported **raw**, exactly as read — no rounding,
  no timezone guessing, no invention.

## 3. Classification

Every entry goes into exactly one of four category files:

| Category | File | What belongs here |
|---|---|---|
| fact | `facts.md` | Verifiable facts: people, dates, accounts, decisions |
| preference | `preferences.md` | Likes, dislikes, standing instructions |
| experience | `experience.md` | Lessons, post-mortems, what worked |
| material | `materials.md` | Links, quotes, reusable material |

If an entry plausibly fits two categories, pick the one the user will look for
it under — never file it twice.

## 4. Filing protocol

1. **Read the real clock.** The entry ID and timestamp are taken from that read.
2. **Classify** the entry into exactly one category file (§3).
3. **Check the target file's tail.** If it does not end with a newline, add one
   first, so the new entry never glues onto the previous line.
4. **Append one line** to the category file:
   ```
   - [YYYYMMDD-NN] YYYY-MM-DD HH:MM — <text>
   ```
   The separator is an em dash (`—`). Example (fictional):
   `- [20261023-01] 2026-10-23 09:30 — The fictional workshop opens at nine.`
5. **Append one index row** to `index.md` in the same turn:
   ```
   | YYYYMMDD-NN | YYYY-MM-DD HH:MM | <category> | <first 60 chars of text> |
   ```
   In a summary, `|` characters are replaced with `/`.
6. **Read back both files** from their real paths. Confirm the new entry is a
   standalone line in the category file and the index row exists. A write
   counts only after this read-back.
7. **Report** the entry ID and the raw timestamp back to the user.

## 5. Tag syntax

Entry text may carry `#tags`: `#` followed by one or more word characters.
`\w` is Unicode-aware, so `#灵感` and `#inbox` both work. Tags are
case-insensitive and deduplicated in order of first appearance
(`#Trip #trip` yields one `trip`). `#` must not be glued to a preceding word
character (`a#b` is not a tag), and a `#` followed by a space (a Markdown
header) is not a tag. Queries can filter by tag, accepting a leading `#`.

## 6. Query protocol

- Answer **from the files**, not from parametric memory. Search all category
  files, cite entry IDs, and quote the recorded timestamp as-is.
- If nothing is recorded, say so plainly. Never fill gaps by invention.
- Hand-written non-entry lines (headers, notes) are never treated as entries.

## 7. Hard rules

- **Timestamps:** real clock reads only, reported raw (§2).
- **Verification:** a write counts only after read-back from the real path (§4,
  step 6). Index and content must agree — the consistency check compares entry
  IDs across the index and the four category files, and the reference CLI
  (`verify`) reports an md5 fingerprint per file.
- **Deletes:** never by entry number. A delete names the full filename and the
  full path, carries a stop-and-report rule if names or fingerprints do not
  match, and in the reference workflow is performed by the human, not the
  agent.
- **Privacy:** log content belongs to the user. Examples and tests in this
  repository use fictional entries only; never commit real personal data.

## 8. Security model

The reference implementation only ever touches five whitelisted files (the four
category files plus `index.md`) — a hostile filename can never become a path on
disk. Additional guards:

- No component of the existing inbox-root path may be a symlink; a swapped-in
  link could silently redirect writes outside the visible tree.
- A relative `--root` must resolve inside the working directory; `..` segments
  that climb above it are rejected. Absolute roots are the caller's explicit
  choice and are kept.
- Every resolved file path must stay inside the resolved inbox root and must
  not itself be a symlink. Violations raise instead of following the link.

## 9. Reference implementation

`src/musings_inbox/inbox.py` implements `init` / `add` / `search` / `list` /
`stats` / `export` / `verify` with the newline, read-back, whitelist, and
traversal rules enforced in code, covered by `tests/test_inbox.py`.
`templates/` (English) and `templates/zh/` (Chinese) hold drop-in starter
files. Agents may call the CLI or follow this protocol directly with their own
file tools.
