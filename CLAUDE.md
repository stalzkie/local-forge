# LocalForge — Claude Code Instructions

## Rules

1. **Never commit or push without explicit user instruction.** Do not run `git commit`, `git push`, `git tag`, or any destructive git command unless the user explicitly says to commit or push. Staging files with `git add` is fine; creating commits is not.

2. **Never create documentation files** (README updates, markdown docs, etc.) unless asked.

3. **No unsolicited refactoring.** Only touch code that is directly related to the requested task. Do not clean up surrounding code, rename variables, or restructure files unless that is the explicit request.

4. **No comments in code** unless the reason is genuinely non-obvious (a hidden constraint, a workaround for a specific bug, a subtle invariant). Never narrate what the code does.

5. **Test before reporting done.** Run `cargo test` after any Rust change. If tests fail, fix them before surfacing the result.

6. **`.localforgeignore` is the source of truth** for files that should be excluded from scanning. Update it whenever a new source file intentionally contains fake keys or risky patterns.

## Project Layout

```
src/
  main.rs              — CLI entry, install/uninstall, scan pipeline orchestration
  ast_validator.rs     — Layer 1: compiled regex patterns (once_cell::Lazy)
  ane_bridge.rs        — Layer 2: CoreML inference via Python shim
  advisory_engine.rs   — Layer 3: Qwen advisory via MLX shim
  mcp_server.rs        — JSON-RPC 2.0 MCP server
  tui/                 — ratatui dashboard
coreml/
  build_model.py       — Train + export Layer 2 model
  advisory.py          — Layer 3 Qwen shim
  LocalForgeModel.mlpackage/
hooks/
  pre-commit           — Git hook; version-stamped LOCALFORGE_HOOK_VERSION=4
scripts/
  install_hook.sh      — Bootstrap install for new users
  build_release.sh     — Bundles binary + assets into .app
  notarize.sh          — Apple notarytool pipeline
  package_homebrew.sh  — Tarball + SHA256 for Homebrew
ui/
  LocalForgeApp/       — SwiftUI macOS app (Swift 6, macOS 14+)
Formula/
  localforge.rb        — Homebrew formula
tests/
  verify.py            — Layer 1 + 2 manual verification
  benchmark_v2.py      — Benchmark charts
```

## Version Sync

These three values must always match:

| Location | Constant |
|---|---|
| `src/main.rs` | `EXPECTED_HOOK_VERSION: u32` |
| `ui/LocalForgeApp/ReposViewModel.swift` | `expectedHookVersion` |
| `hooks/pre-commit` | `# LOCALFORGE_HOOK_VERSION=` |

## Key Invariants

- Layer 1 and Layer 2 **block** commits (`exit 1`). Layer 3 **never blocks**.
- `ast_validator::scan()` only scans `+` diff lines — never `-` lines.
- The Layer 3 advisory always writes to a single consolidated report file per commit, never one file per finding.
- `~/.localforge/` is the canonical install directory: `bin/`, `coreml/`, `reports/`, `repos`, `prefs`, `hook.log`.
- All regex patterns in `ast_validator.rs` use `once_cell::Lazy` — compiled once, never per-commit.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
