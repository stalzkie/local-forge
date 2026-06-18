#!/usr/bin/env bash
# Build the full LocalForge release: Rust binary + macOS .app
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
BUILD_DIR="$REPO_ROOT/build"

echo "==> [1/3] Building Rust release binary..."
source "$HOME/.cargo/env"
cargo build --release --target aarch64-apple-darwin 2>&1
BINARY="$REPO_ROOT/target/aarch64-apple-darwin/release/localforge"
echo "    Binary: $BINARY"

echo ""
echo "==> [2/3] Building macOS app with xcodebuild..."
mkdir -p "$BUILD_DIR"

xcodebuild \
    -project "$REPO_ROOT/ui/LocalForge.xcodeproj" \
    -scheme LocalForge \
    -configuration Release \
    -archivePath "$BUILD_DIR/LocalForge.xcarchive" \
    MACOSX_DEPLOYMENT_TARGET=14.0 \
    archive \
    | grep -E "^(Build|error:|warning:|note:|Archive)" || true

echo ""
echo "==> [3/3] Exporting .app..."
xcodebuild \
    -exportArchive \
    -archivePath "$BUILD_DIR/LocalForge.xcarchive" \
    -exportPath "$BUILD_DIR/export" \
    -exportOptionsPlist "$REPO_ROOT/ui/ExportOptions.plist" \
    | grep -E "^(Export|error:|warning:)" || true

# Copy the Rust binary into the .app bundle
APP_PATH="$BUILD_DIR/export/LocalForge.app"
MACOS_DIR="$APP_PATH/Contents/MacOS"
if [ -d "$MACOS_DIR" ]; then
    cp "$BINARY" "$MACOS_DIR/localforge-core"
    chmod +x "$MACOS_DIR/localforge-core"
    echo "    Bundled: $MACOS_DIR/localforge-core"
fi

echo ""
echo "==> Done. App: $APP_PATH"
