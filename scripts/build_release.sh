#!/usr/bin/env bash
# Build the full LocalForge release: Rust binary + macOS .app
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD_DIR="$REPO_ROOT/build"

echo "==> [1/3] Building Rust release binary (aarch64-apple-darwin)..."
source "$HOME/.cargo/env"
cargo build --release --target aarch64-apple-darwin
BINARY="$REPO_ROOT/target/aarch64-apple-darwin/release/localforge"
echo "    Binary: $BINARY ($(du -sh "$BINARY" | cut -f1))"

echo ""
echo "==> [2/3] Archiving macOS app with xcodebuild..."
mkdir -p "$BUILD_DIR"

xcodebuild \
    -project "$REPO_ROOT/ui/LocalForge.xcodeproj" \
    -scheme LocalForge \
    -configuration Release \
    -archivePath "$BUILD_DIR/LocalForge.xcarchive" \
    CODE_SIGNING_ALLOWED=NO \
    archive 2>&1 | grep -E "^(Build|error:|warning:|Archive|CREATE)" || true

echo ""
echo "==> [3/3] Exporting .app and bundling Rust binary..."
mkdir -p "$BUILD_DIR/export"
cp -r "$BUILD_DIR/LocalForge.xcarchive/Products/Applications/LocalForge.app" \
      "$BUILD_DIR/export/"

MACOS_DIR="$BUILD_DIR/export/LocalForge.app/Contents/MacOS"
cp "$BINARY" "$MACOS_DIR/localforge-core"
chmod +x "$MACOS_DIR/localforge-core"
echo "    Bundled: $MACOS_DIR/localforge-core"

echo ""
echo "==> Done. App: $BUILD_DIR/export/LocalForge.app"
echo "    Run scripts/package_dmg.sh to create the distributable DMG."
