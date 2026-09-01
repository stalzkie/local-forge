## What

<!-- One sentence: what does this PR do? -->

## Why

<!-- Why is this change needed? Link any related issues: Closes #123 -->

## Changes

<!-- Bullet list of the meaningful changes -->

## Version sync checklist

If you changed `hooks/pre-commit` hook behaviour, bump all three constants:

- [ ] `EXPECTED_HOOK_VERSION` in `src/main.rs`
- [ ] `expectedHookVersion` in `ui/LocalForgeApp/ReposViewModel.swift`
- [ ] `# LOCALFORGE_HOOK_VERSION=` in `hooks/pre-commit`

If you changed the semantic version in `Cargo.toml`:

- [ ] `Cargo.toml` `version` field
- [ ] `scripts/package_dmg.sh` `DMG_NAME` literal

## Test plan

<!-- How did you verify this? `cargo test`, manual scan, walkthrough file, etc. -->
