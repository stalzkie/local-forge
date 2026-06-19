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
MODEL_DEST="$LF_DIR/LocalForgeModel.mlpackage"
if [ -e "$REPO_ROOT/coreml/LocalForgeModel.mlpackage" ]; then
    # Remove stale copy first to avoid nesting (cp -r into existing dir nests it)
    rm -rf "$MODEL_DEST"
    cp -r "$REPO_ROOT/coreml/LocalForgeModel.mlpackage" "$MODEL_DEST"
    echo "[LocalForge] ✓ CoreML model installed → $MODEL_DEST"
elif [ -e "$MODEL_DEST" ]; then
    echo "[LocalForge] ✓ CoreML model already at $MODEL_DEST"
else
    echo "[LocalForge] ⚠ CoreML model not found. Run: python3 $REPO_ROOT/coreml/build_model.py"
fi

cp "$REPO_ROOT/coreml/infer.py"    "$LF_COREML/infer.py"
cp "$REPO_ROOT/coreml/advisory.py" "$LF_COREML/advisory.py"
echo "[LocalForge] ✓ Python shims installed → $LF_COREML/"

# ── 4. Handle Qwen model ─────────────────────────────────────────────────────
QWEN_DEST="$LF_DIR/qwen2.5-coder-1.5b-4bit"
QWEN_SRC="$REPO_ROOT/coreml/qwen2.5-coder-1.5b-4bit"

if [ -d "$QWEN_DEST" ]; then
    echo "[LocalForge] ✓ Qwen model already at $QWEN_DEST"
elif [ -d "$QWEN_SRC" ]; then
    # Move from repo coreml/ into ~/.localforge/ (avoids doubling disk usage)
    mv "$QWEN_SRC" "$QWEN_DEST"
    echo "[LocalForge] ✓ Qwen model moved → $QWEN_DEST"
else
    # Check if it landed in HuggingFace cache from a prior download
    HF_SNAPSHOT=$(find "$HOME/.cache/huggingface/hub" -maxdepth 4 \
        -type d -name "qwen2.5-coder-1.5b*" 2>/dev/null | head -1 || true)
    if [ -d "$HF_SNAPSHOT" ]; then
        cp -r "$HF_SNAPSHOT" "$QWEN_DEST"
        echo "[LocalForge] ✓ Qwen model copied from HuggingFace cache → $QWEN_DEST"
    else
        echo ""
        echo "[LocalForge] ⚠ Qwen model not found (Layer 3 advisory will be skipped)."
        echo "             To enable it, run:"
        echo "               pip3 install mlx-lm"
        echo "               python3 -c \"from mlx_lm import load; load('Qwen/Qwen2.5-Coder-1.5B-Instruct-4bit')\""
        echo "             The model will be auto-detected from your HuggingFace cache on next install."
    fi
fi

# ── 5. Install git hook into target repo ─────────────────────────────────────
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

# ── 6. Register repo in ~/.localforge/repos ──────────────────────────────────
REPOS_FILE="$LF_DIR/repos"
touch "$REPOS_FILE"
ABS_TARGET="$(cd "$TARGET_REPO" && pwd)"
if ! grep -qF "$ABS_TARGET" "$REPOS_FILE" 2>/dev/null; then
    echo "$ABS_TARGET" >> "$REPOS_FILE"
    echo "[LocalForge] ✓ Registered → $REPOS_FILE"
fi

# ── 7. Add ~/.localforge/bin to PATH (write to shell profile if missing) ──────
add_to_path() {
    local profile="$1"
    local export_line='export PATH="$HOME/.localforge/bin:$PATH"'
    if [ -f "$profile" ] && grep -qF ".localforge/bin" "$profile"; then
        return 0  # already present
    fi
    echo "" >> "$profile"
    echo "# LocalForge" >> "$profile"
    echo "$export_line" >> "$profile"
    echo "[LocalForge] ✓ PATH updated in $profile"
    echo "             Run: source $profile"
}

if ! echo "$PATH" | grep -q ".localforge/bin"; then
    # Detect which profile to write to
    if [ -n "${ZSH_VERSION:-}" ] || [ "$SHELL" = "/bin/zsh" ]; then
        add_to_path "$HOME/.zshrc"
    elif [ -n "${BASH_VERSION:-}" ] || [ "$SHELL" = "/bin/bash" ]; then
        add_to_path "$HOME/.bash_profile"
    else
        add_to_path "$HOME/.profile"
    fi
else
    echo "[LocalForge] ✓ $LF_BIN already in PATH"
fi

echo ""
echo "[LocalForge] Installation complete."
echo "             Every commit in $ABS_TARGET is now protected."
