#!/usr/bin/env bash
# Packs dist/PsyTags into dist/psytags_VERSION_amd64.deb and dist/psytags-VERSION-1.x86_64.rpm.
# Run from the repository root after PyInstaller.
set -euo pipefail

NFPM_URL=https://github.com/goreleaser/nfpm/releases/download/v2.48.0/nfpm_2.48.0_Linux_x86_64.tar.gz
NFPM_SHA256=6d7f9a28b2f397934403950fcbba83f598b08d02edbe79a0815b3b4897341750

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
curl -fsSL -o "$work/nfpm.tar.gz" "$NFPM_URL"
echo "$NFPM_SHA256  $work/nfpm.tar.gz" | sha256sum -c -
tar -xzf "$work/nfpm.tar.gz" -C "$work" nfpm

VERSION=$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' psytags/__init__.py)
test -n "$VERSION"
export VERSION
"$work/nfpm" package --config packaging/nfpm.yaml --packager deb --target "dist/psytags_${VERSION}_amd64.deb"
"$work/nfpm" package --config packaging/nfpm.yaml --packager rpm --target "dist/psytags-${VERSION}-1.x86_64.rpm"
ls -l dist/*.deb dist/*.rpm
