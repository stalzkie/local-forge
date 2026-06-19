#!/usr/bin/env bash
# LocalForge installer — sets up ~/.localforge/ and installs the git hook
# Usage: ./scripts/install_hook.sh [/path/to/repo/to/protect]
set -euo pipefail

LF_DIR="$HOME/.localforge"
LF_BIN="$LF_DIR/bin"
LF_COREML="$LF_DIR/coreml"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── 1. Create ~/.localforge directory structure ───────────────────────────────
mkdir -p "$LF_BIN" "$LF_COREML" "$LF_DIR/reports"

# ── 2. Copy Rust binary ───────────────────────────────────────────────────────
BINARY="$REPO_ROOT/target/release/localforge"
if [ ! -f "$BINARY" ]; then
    echo "[LocalForge] Binary not found. Building now..."
    source "$HOME/.cargo/env" 2>/dev/null || true
    cargo build --release --manifest-path "$REPO_ROOT/Cargo.toml"
fi
cp "$BINARY" "$LF_BIN/localforge"
chmod +x "$LF_BIN/localforge"
echo "[LocalForge] ✓ Binary installed → $LF_BIN/localforge"

# ── 3. Copy CoreML model and Python shims ────────────────────────────────────
if [ -e "$REPO_ROOT/coreml/LocalForgeModel.mlpackage" ]; then
    cp -r "$REPO_ROOT/coreml/LocalForgeModel.mlpackage" "$LF_DIR/LocalForgeModel.mlpackage"
    echo "[LocalForge] ✓ CoreML model installed → $LF_DIR/LocalForgeModel.mlpackage"
else
    echo "[LocalForge] ⚠ CoreML model not found. Run: python3 coreml/build_model.py"
fi

cp "$REPO_ROOT/coreml/infer.py"    "$LF_COREML/infer.py"
cp "$REPO_ROOT/coreml/advisory.py" "$LF_COREML/advisory.py"
echo "[LocalForge] ✓ Python shims installed → $LF_COREML/"

# ── 4. Check Qwen model ───────────────────────────────────────────────────────
QWEN_DIR="$LF_DIR/qwen2.5-coder-1.5b-4bit"
if [ ! -d "$QWEN_DIR" ]; then
    echo "[LocalForge] ⚠ Qwen model not found at $QWEN_DIR"
    echo "             To install: pip3 install mlx-lm && python3 -c \\"
    echo "             \"from mlx_lm import load; load('Qwen/Qwen2.5-Coder-1.5B-Instruct-4bit')\""
    echo "             Then move the model to: $QWEN_DIR"
fi

# ── 5. Install git hook into target repo ─────────────────────────────────────
# Default to current directory if no argument given
TARGET_REPO="${1:-$(pwd)}"
if [ ! -d "$TARGET_REPO/.git" ]; then
    echo "[LocalForge] ✗ Not a git repository: $TARGET_REPO"
    echo "             Usage: ./scripts/install_hook.sh /path/to/your/repo"
    exit 1
fi

HOOK_DST="$TARGET_REPO/.git/hooks/pre-commit"
cp "$REPO_ROOT/hooks/pre-commit" "$HOOK_DST"
chmod +x "$HOOK_DST"
echo "[LocalForge] ✓ Hook installed → $HOOK_DST"

# ── 6. Register repo in ~/.localforge/repos ───────────────────────────────────
REPOS_FILE="$LF_DIR/repos"
touch "$REPOS_FILE"
ABS_TARGET="$(cd "$TARGET_REPO" && pwd)"
if ! grep -qF "$ABS_TARGET" "$REPOS_FILE" 2>/dev/null; then
    echo "$ABS_TARGET" >> "$REPOS_FILE"
    echo "[LocalForge] ✓ Registered → $REPOS_FILE"
fi

# ── 7. Add ~/.localforge/bin to PATH hint ────────────────────────────────────
if ! echo "$PATH" | grep -q "$LF_BIN"; then
    echo ""
    echo "[LocalForge] Add to your shell profile to use 'localforge' globally:"
    echo "             export PATH=\"\$HOME/.localforge/bin:\$PATH\""
fi

echo ""
echo "[LocalForge] Installation complete."
echo "             Every commit in $ABS_TARGET is now protected."
