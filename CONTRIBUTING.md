# Contributing to LocalForge

Thank you for your interest in contributing. LocalForge is a security-sensitive project — please read this guide before opening a PR.

## Before You Start

- Check [open issues](https://github.com/stalzkie/local-forge-production/issues) to avoid duplicating work
- For significant changes, open an issue first to discuss the approach
- All contributions are subject to the [Code of Conduct](CODE_OF_CONDUCT.md)

## Development Setup

**Requirements:** macOS 14+, Apple Silicon, Rust 1.78+, Python 3.11+

```bash
git clone https://github.com/stalzkie/local-forge-production.git
cd local-forge-production

# Install Rust (if needed)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source "$HOME/.cargo/env"

# Build
cargo build --target aarch64-apple-darwin

# Build the Layer 2 CoreML model
pip3 install coremltools scikit-learn numpy
python3 coreml/build_model.py

# (Optional) Layer 3 Qwen advisory
pip3 install mlx-lm

# Install skills (restores Claude Code agent skills from skills-lock.json)
npx skills install
```

## Running Tests

Always run the full test suite before submitting a PR:

```bash
# Rust unit tests (must all pass)
cargo test --target aarch64-apple-darwin

# Clippy — warnings are errors in CI
cargo clippy --target aarch64-apple-darwin -- -D warnings

# L1 binary integration tests (golden TP/FP set)
pytest tests/test_l1_integration.py -v

# Corpus integrity check (no Qwen model required)
pytest tests/check_corpus.py -v

# Layer 3 eval (requires Qwen model, ~900 MB download on first run)
python3 tests/layer3_eval.py
```

## What CI Checks

Every PR runs the full [testing pyramid](.github/workflows/ci.yml):

| Level | What | Runner |
|-------|------|--------|
| L0 | `cargo fmt`, version-sync, shellcheck, ruff, corpus integrity | ubuntu |
| L1 | `cargo clippy -D warnings` + `cargo test` | macos-15 (Apple Silicon) |
| L2 | Binary golden TP/FP set via `localforge --scan` | macos-15 |
| Gate | `ci-pass` job — required for merge | ubuntu |

The PR will not merge unless all jobs are green.

## Version Sync Invariant

If you change the hook version, you **must** update all three locations simultaneously or CI will fail:

| File | Constant |
|------|----------|
| `src/main.rs` | `EXPECTED_HOOK_VERSION: u32` |
| `ui/LocalForgeApp/ReposViewModel.swift` | `expectedHookVersion` |
| `hooks/pre-commit` | `# LOCALFORGE_HOOK_VERSION=` |

The PR template includes a checklist for this.

## Adding a Layer 1 Pattern

Layer 1 patterns live in `src/ast_validator.rs`. Each new pattern requires **two tests**:

1. A detection test (`TP_CASES` in `tests/test_l1_integration.py` and the Rust unit tests in `ast_validator.rs`)
2. A false-positive guard test (a clean variant that must **not** trigger)

Pattern rules:
- All patterns use `once_cell::Lazy` — never compile inside a hot loop
- Only `+` diff lines are ever scanned — never `-` lines
- No real credentials in test fixtures — construct them at runtime: `format!("AKIA{}", "IOSFODNN7EXAMPLE")`
- Add the file to `.localforgeignore` if it contains fake-but-pattern-matching keys

## Retraining Layer 2

If you add training data to `coreml/build_model.py`, retrain and commit the updated artifacts:

```bash
python3 coreml/build_model.py
# Commit: coreml/LocalForgeModel.mlpackage/ and coreml/model_metadata.json
```

Include the before/after CV F1 in your PR description.

## Commit Style

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add Azure SAS token pattern to Layer 1
fix: correct chunk boundary in Layer 3 large-diff path
test: add FP guard for parameterized queries
ci: pin macos runner to macos-15
```

One logical change per commit. Keep commits focused.

## Pull Request Checklist

- [ ] `cargo test` passes
- [ ] `cargo clippy -- -D warnings` passes
- [ ] `pytest tests/test_l1_integration.py` passes
- [ ] New Layer 1 patterns have both a TP test and an FP guard test
- [ ] No real secrets in any committed file
- [ ] `.localforgeignore` updated if new files contain intentional fake keys
- [ ] Version sync constants updated if hook version changed
- [ ] PR description explains the *why*, not just the *what*

## Security-Sensitive Areas

Changes to these files receive extra scrutiny:

- `src/ast_validator.rs` — secret detection patterns
- `hooks/pre-commit` — executes on every commit for all users
- `src/mcp_server.rs` — network-exposed endpoint
- `coreml/advisory.py` — runs arbitrary shell tools (static analysis layer)
- `scripts/install_hook.sh` — modifies the user's shell profile

If your change touches any of these, explain the security implications in the PR.

## Reporting Security Issues

**Do not open a public issue for vulnerabilities.** See [SECURITY.md](SECURITY.md).
