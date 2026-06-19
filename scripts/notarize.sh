#!/usr/bin/env bash
# Notarize and staple the LocalForge DMG for Gatekeeper-free distribution.
# Requires an Apple Developer account with an app-specific password stored in Keychain.
#
# One-time keychain setup:
#   xcrun notarytool store-credentials "LocalForge-Notary" \
#     --apple-id "your@email.com" \
#     --team-id  "YOUR_TEAM_ID" \
#     --password "xxxx-xxxx-xxxx-xxxx"   # app-specific password from appleid.apple.com
#
# Usage: ./scripts/notarize.sh [path/to/LocalForge-vX.X-arm64.dmg]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DMG="${1:-$REPO_ROOT/build/LocalForge-v2.0-arm64.dmg}"
KEYCHAIN_PROFILE="LocalForge-Notary"

if [ ! -f "$DMG" ]; then
    echo "ERROR: DMG not found: $DMG"
    echo "       Run scripts/build_release.sh && scripts/package_dmg.sh first."
    exit 1
fi

echo "==> Submitting $DMG for notarization..."
xcrun notarytool submit "$DMG" \
    --keychain-profile "$KEYCHAIN_PROFILE" \
    --wait

echo ""
echo "==> Stapling notarization ticket to DMG..."
xcrun stapler staple "$DMG"

echo ""
echo "==> Verifying staple..."
spctl --assess --type open --context context:primary-signature -v "$DMG"

echo ""
echo "==> Done. $DMG is notarized and ready for distribution."
echo "    SHA-256: $(shasum -a 256 "$DMG" | awk '{print $1}')"
