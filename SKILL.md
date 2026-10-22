# Skill: musings-inbox (public edition)

A life-log / inspiration inbox protocol for file-capable AI agents.
Trigger words: a message starting with `Musings` or `随想` (case-insensitive,
as a standalone word at the start of the message, followed by punctuation
or a space) means: file this, do not debate it.

## Filing protocol

1. Read the real clock first. The entry ID (`YYYYMMDD-NN`) and timestamp
   must come from that read — never from memory or estimation.
2. Classify the entry into exactly one category file:
   - `facts.md` — verifiable facts (people, dates, accounts, decisions)
   - `preferences.md` — likes, dislikes, standing instructions
   - `experience.md` — lessons and post-mortems
   - `materials.md` — links, quotes, reusable material
3. Before appending: check the target file's tail. If it does not end
   with a newline, add one first.
4. Append one line: `- [YYYYMMDD-NN] YYYY-MM-DD HH:MM — <text>`
5. Append the index row to `index.md` in the same turn.
6. Read back both files. Confirm the new entry is a standalone line and
   the index row exists. Report the entry ID and the raw timestamp.

## Query protocol

- Answer from the files, not from parametric memory. Search all category
  files, cite entry IDs, and quote the recorded timestamp as-is.
- If nothing is recorded, say so plainly. Never fill gaps by invention.

## Hard rules

- Timestamps: real clock reads only, reported raw.
- Verification: a write counts only after read-back from the real path.
- Deletes: never by entry number; full filename + full path only, with a
  stop-and-report rule if names or fingerprints do not match. (In the
  reference workflow, deletes are performed by the human, not the agent.)
- Privacy: log content belongs to the user. Examples and tests in this
  repository use fictional entries only.

## Reference implementation

`src/musings_inbox/inbox.py` implements init / add / search / verify with
the newline and read-back rules enforced in code. Agents may call it as a
CLI or follow this protocol directly with their own file tools.
