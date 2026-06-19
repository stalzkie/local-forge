#!/usr/bin/env bash
# Build the full LocalForge release: Rust binary + macOS .app
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD_DIR="$REPO_ROOT/build"

echo "==> [1/4] Building Rust release binary (aarch64-apple-darwin)..."
source "$HOME/.cargo/env"
cargo build --release --target aarch64-apple-darwin
BINARY="$REPO_ROOT/target/aarch64-apple-darwin/release/localforge"
echo "    Binary: $BINARY ($(du -sh "$BINARY" | cut -f1))"

echo ""
echo "==> [2/4] Archiving macOS app with xcodebuild..."
mkdir -p "$BUILD_DIR"

xcodebuild \
    -project "$REPO_ROOT/ui/LocalForge.xcodeproj" \
    -scheme LocalForge \
    -configuration Release \
    -archivePath "$BUILD_DIR/LocalForge.xcarchive" \
    CODE_SIGNING_ALLOWED=NO \
    archive 2>&1 | grep -E "^(Build|error:|warning:|Archive|CREATE)" || true

echo ""
echo "==> [3/4] Exporting .app and bundling Rust binary..."
mkdir -p "$BUILD_DIR/export"
cp -r "$BUILD_DIR/LocalForge.xcarchive/Products/Applications/LocalForge.app" \
      "$BUILD_DIR/export/"

MACOS_DIR="$BUILD_DIR/export/LocalForge.app/Contents/MacOS"
RESOURCES_DIR="$BUILD_DIR/export/LocalForge.app/Contents/Resources"

cp "$BINARY" "$MACOS_DIR/localforge-core"
chmod +x "$MACOS_DIR/localforge-core"
echo "    Bundled binary: $MACOS_DIR/localforge-core"

echo ""
echo "==> [4/4] Bundling CoreML model and Python shims into Resources/..."

# CoreML model (Layer 2)
if [ -e "$REPO_ROOT/coreml/LocalForgeModel.mlpackage" ]; then
    rm -rf "$RESOURCES_DIR/LocalForgeModel.mlpackage"
    cp -r "$REPO_ROOT/coreml/LocalForgeModel.mlpackage" "$RESOURCES_DIR/"
    echo "    Bundled: LocalForgeModel.mlpackage ($(du -sh "$RESOURCES_DIR/LocalForgeModel.mlpackage" | cut -f1))"
elif [ -e "$HOME/.localforge/LocalForgeModel.mlpackage" ]; then
    rm -rf "$RESOURCES_DIR/LocalForgeModel.mlpackage"
    cp -r "$HOME/.localforge/LocalForgeModel.mlpackage" "$RESOURCES_DIR/"
    echo "    Bundled: LocalForgeModel.mlpackage from ~/.localforge/"
else
    echo "    WARNING: LocalForgeModel.mlpackage not found — Layer 2 will be skipped in the app."
    echo "             Build it first: pip3 install coremltools scikit-learn numpy && python3 coreml/build_model.py"
fi

# Python shims (Layer 2 & 3)
mkdir -p "$RESOURCES_DIR/coreml"
for shim in infer.py advisory.py; do
    if [ -f "$REPO_ROOT/coreml/$shim" ]; then
        cp "$REPO_ROOT/coreml/$shim" "$RESOURCES_DIR/coreml/$shim"
        echo "    Bundled: coreml/$shim"
    fi
done

# Pre-commit hook template
mkdir -p "$RESOURCES_DIR/hooks"
cp "$REPO_ROOT/hooks/pre-commit" "$RESOURCES_DIR/hooks/pre-commit"
echo "    Bundled: hooks/pre-commit"

echo ""
echo "==> Done. App: $BUILD_DIR/export/LocalForge.app"
echo "    Bundle size: $(du -sh "$BUILD_DIR/export/LocalForge.app" | cut -f1)"
echo ""
echo "    Next steps:"
echo "      scripts/package_dmg.sh          — create distributable DMG"
echo "      scripts/notarize.sh             — notarize for Gatekeeper-free distribution"
