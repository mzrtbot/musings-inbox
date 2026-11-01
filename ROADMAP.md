# Roadmap

## Now (0.1.x)
- CI on every push (pytest, 3 Python versions) and a demo smoke test.
- `list` and `stats` commands for reading an inbox back without grep.
- `export` to a single Markdown file or JSON for backup and migration.

## Next (0.2.x)
- Security hardening of file paths: traversal/symlink guards and a strict filename whitelist for category files.
- `#tag` support in entries, with `search --tag` filtering.
- Search filters: `--since` and `--category`.
- Chinese template pack (`templates/zh/`) and a full protocol document (`docs/protocol.md`) — shipped.
- A worked example inbox with a step-by-step walkthrough.

## Later
- Optional summarization command that compresses older entries (kept out of the dependency-free core).
- Interop notes for more agent runtimes (skill-directory layouts beyond ClawHub-style).

Ideas and bug reports are welcome as issues. The core stays dependency-free:
anything that needs a network call or a model lives outside it.
