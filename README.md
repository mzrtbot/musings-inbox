# musings-inbox

[![CI](https://github.com/mzrtbot/musings-inbox/actions/workflows/ci.yml/badge.svg)](https://github.com/mzrtbot/musings-inbox/actions/workflows/ci.yml)

**A local-first life-log ("inspiration inbox") for AI agents — plain Markdown files, no vendor lock-in.**

You say one trigger word to your agent — `Musings:` in English, `随想：` in Chinese — and it files the thought away: classified, timestamped from a real clock read, indexed, and verifiable months later. When you ask a question, the agent answers from *your own recorded history*, not from a cloud profile you cannot inspect.

Built and used daily on a dGEN1 device running AndyClaw (an OpenClaw-family agent), and designed to work with any agent that can read and write local files: OpenClaw, AndyClaw, Codex, Claude Code, or a plain shell.

## Why this exists

Agent memory products usually lock your life-log inside one vendor's cloud and one model's ecosystem. This project takes the opposite position — **architecture is the stance**:

| Layer | Choice | Replaceable? |
|---|---|---|
| Storage | Plain Markdown files on your device | Yes — read them with any editor |
| Format | One file per category + one index | Yes — no database to migrate |
| Agent | Any file-capable agent / skill runtime | Yes |
| Model | Any LLM behind the agent | Yes |

Every layer can be swapped without losing the log.

## The rules that make it trustworthy

These were not designed on a whiteboard; each one is a scar from real use:

1. **Real-clock timestamps only.** Entry IDs and times come from a clock read taken in the same turn. An agent must never invent, round, or reconstruct a time.
2. **Trailing-newline check before every append.** Check the file tail first; if it does not end with a newline, add one. After writing, read back and confirm the new entry is a standalone line. (This rule exists because appends kept gluing entries together.)
3. **Verify the disk, not the agent's word.** Acceptance means: full path + real read-back + md5 fingerprint. A claim in chat is a lead, never proof.
4. **Index is generated, never hand-waved.** The index is rebuilt/checked against content; a mismatch fails verification loudly.
5. **Deletes are named, never numbered.** Entry numbers are temporary seat numbers. Deletion (a human-only operation in our workflow) always names full filenames and paths, with a stop-if-mismatch rule.

## Quick start

```bash
git clone https://github.com/mzrtbot/musings-inbox.git
cd musings-inbox
python3 -m pip install -e .

musings-inbox --root ./my-inbox init
musings-inbox --root ./my-inbox add --type fact --text "The workshop opens at nine."
musings-inbox --root ./my-inbox search workshop
musings-inbox --root ./my-inbox list --category fact --date 2026-10-23
musings-inbox --root ./my-inbox stats
musings-inbox --root ./my-inbox export --format json --output ./my-inbox-export.json
musings-inbox --root ./my-inbox export  # one Markdown document on stdout
musings-inbox --root ./my-inbox verify
```

No installation? The core is a single dependency-free module:

```bash
PYTHONPATH=src python -m musings_inbox.inbox --root ./my-inbox add --type fact --text "Hello, inbox."
```

## Layout of an inbox

```
my-inbox/
  facts.md         # what is true: people, dates, accounts, decisions
  preferences.md   # what you like / dislike, standing instructions
  experience.md    # lessons, post-mortems, what worked
  materials.md     # links, quotes, things to reuse
  index.md         # generated index: ID | time | category | summary
```

## Using it as an agent skill

`SKILL.md` in this repo is the public edition of the skill that drives the workflow above (trigger words, classification, read/write discipline, verification). Drop it into your agent's skills directory (ClawHub-compatible layout) and your agent can run the same protocol.

## Status

v0.1.1 — the CLI implements init / add / search / list / stats / export / verify with the newline and read-back rules enforced in code and covered by tests. `list` filters by `--category` and/or `--date` (YYYY-MM-DD) and prints entries in chronological order. `stats` reports per-category counts, earliest/latest entries, and total entry-text characters. `export` writes the whole inbox as one Markdown document or one JSON array, with the same `--category` / `--date` filters, to stdout or `--output` file. The skill protocol is at v1.0.13 in daily on-device use; this repo is its public, sanitized edition (no private log content is included — `examples/` uses fictional entries).

## 中文简介

随手记 + 长期记忆 + 基于自己历史的决策辅助。触发词「随想：」或 "Musings:"，agent 即把一句话归类落盘：事实 / 偏好 / 经验 / 素材四类 Markdown 文件 + 一份索引。时间只许来自当轮真实时钟读数；追加前先查文件末尾换行、写后回读验指纹；验收认盘不认嘴。数据全在自己设备上，不锁定任何厂商模型或云。

## License

MIT — see `LICENSE`.
