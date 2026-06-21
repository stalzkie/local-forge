#!/usr/bin/env bash
# Package LocalForge.app into a distributable DMG
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
APP_PATH="$REPO_ROOT/build/export/LocalForge.app"
DMG_NAME="LocalForge-v2.1.3-arm64.dmg"
DMG_OUT="$REPO_ROOT/build/$DMG_NAME"
STAGING="$REPO_ROOT/build/dmg_staging"

if [ ! -d "$APP_PATH" ]; then
    echo "ERROR: $APP_PATH not found. Run scripts/build_release.sh first."
    exit 1
fi

if ! command -v create-dmg &>/dev/null; then
    echo "ERROR: create-dmg not found. Install with: brew install create-dmg"
    exit 1
fi

echo "==> Staging app..."
rm -rf "$STAGING"
mkdir -p "$STAGING"
cp -r "$APP_PATH" "$STAGING/"

echo "==> Creating DMG..."
create-dmg \
    --volname "LocalForge" \
    --volicon "$REPO_ROOT/ui/LocalForgeApp/Assets.xcassets/AppIcon.appiconset/icon_512.png" \
    --window-pos 200 120 \
    --window-size 580 380 \
    --icon-size 100 \
    --icon "LocalForge.app" 150 180 \
    --hide-extension "LocalForge.app" \
    --app-drop-link 420 180 \
    "$DMG_OUT" \
    "$STAGING/"

echo ""
echo "==> Distributable DMG: $DMG_OUT"
echo "    Size: $(du -sh "$DMG_OUT" | cut -f1)"
