# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/), versions follow SemVer.

## [Unreleased]

### Security
- `--root` hardening: a symlinked inbox root (or a symlink anywhere in its existing parent prefix) is rejected; relative roots containing `..` that would climb above the working directory are rejected. Every file the inbox reads or writes must be one of the five whitelisted filenames (four category files + index), must resolve inside the resolved inbox root, and must not be a symlink — `add` / `verify` / `search` now raise instead of following a swapped-in link.

### Added
- `list` command: list entries, optionally filtered by `--category` and/or `--date` (YYYY-MM-DD), in chronological order; non-entry lines are skipped.
- `stats` command: total entries, per-category counts (all four categories, zero when empty), earliest/latest entries in chronological order, and total entry-text characters; empty inboxes report `earliest: none` / `latest: none`.
- `export` command: export the whole inbox as one Markdown document (default) or one JSON array (`--format json`), with the same `--category` / `--date` filters, to stdout or to `--output` file (parent directories are created); empty inboxes export as a Markdown header with `no entries` or as `[]`, with matching library method `Inbox.export()`.

## [0.1.1] - 2026-10-23

### Added
- GitHub Actions CI: pytest on Python 3.10 / 3.11 / 3.12 plus a demo smoke test on every push and pull request.
- `ROADMAP.md` with the public development plan.
- This changelog.

## [0.1.0] - 2026-10-23

### Added
- Initial public release: `musings-inbox` CLI with `init` / `add` / `search` / `verify`.
- Protocol rules enforced in code: real-clock timestamps, trailing-newline check before append, read-back verification, index/content consistency check with md5 fingerprints.
- `SKILL.md`: the public edition of the agent protocol (trigger words, classification, verification discipline).
- Templates for the four category files and the index; fictional demo in `examples/`.
- Test suite (5 tests) including the glued-line regression test and an index-forgery detection test.
- MIT license.
