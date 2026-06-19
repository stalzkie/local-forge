#!/usr/bin/env bash
# Package a Homebrew-ready tarball for the current release.
# Produces: build/localforge-v<VERSION>-aarch64-apple-darwin.tar.gz
# Then prints the SHA-256 to paste into Formula/localforge.rb
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION=$(grep '^version' "$REPO_ROOT/Cargo.toml" | head -1 | sed 's/.*= *"//; s/".*//')
BINARY="$REPO_ROOT/target/aarch64-apple-darwin/release/localforge"
BUILD_DIR="$REPO_ROOT/build"
STAGING="$BUILD_DIR/homebrew_staging"
TARBALL="$BUILD_DIR/localforge-v${VERSION}-aarch64-apple-darwin.tar.gz"

if [ ! -f "$BINARY" ]; then
    echo "ERROR: Release binary not found. Run scripts/build_release.sh first."
    exit 1
fi

echo "==> Staging Homebrew tarball for v$VERSION..."
rm -rf "$STAGING"
mkdir -p "$STAGING/coreml" "$STAGING/hooks"

cp "$BINARY"                                "$STAGING/localforge"
cp "$REPO_ROOT/coreml/infer.py"            "$STAGING/coreml/infer.py"
cp "$REPO_ROOT/coreml/advisory.py"         "$STAGING/coreml/advisory.py"
cp "$REPO_ROOT/hooks/pre-commit"           "$STAGING/hooks/pre-commit"

chmod +x "$STAGING/localforge"
chmod +x "$STAGING/hooks/pre-commit"

echo "==> Creating tarball..."
tar -czf "$TARBALL" -C "$STAGING" .

SHA=$(shasum -a 256 "$TARBALL" | awk '{print $1}')

echo ""
echo "==> Homebrew tarball ready: $TARBALL"
echo "    Size: $(du -sh "$TARBALL" | cut -f1)"
echo "    SHA-256: $SHA"
echo ""
echo "==> Update Formula/localforge.rb:"
echo "    url \"https://github.com/stalzkie/local-forge/releases/download/v${VERSION}/localforge-v${VERSION}-aarch64-apple-darwin.tar.gz\""
echo "    sha256 \"$SHA\""
echo ""
echo "==> Then upload $TARBALL to the GitHub release:"
echo "    gh release upload v${VERSION} $TARBALL"
