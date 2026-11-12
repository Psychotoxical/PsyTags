#!/usr/bin/env bash
# Signs PsyTags.app with a Developer ID for notarization: every program and library inside
# first, then the frameworks, then the app, all with the hardened runtime and a timestamp.
# Usage: sign_macos.sh APP "Developer ID Application: Name (TEAMID)"
set -euo pipefail

app=${1:?app bundle}
identity=${2:?signing identity}
entitlements=$(cd "$(dirname "$0")" && pwd)/psytags.entitlements

sign() {
    codesign --force --timestamp --options runtime --entitlements "$entitlements" --sign "$identity" "$1"
}

# Deepest paths first, so that a folder is signed after everything in it.
by_depth() {
    awk -F/ '{ print NF "\t" $0 }' | sort -rn | cut -f2-
}

find "$app/Contents" -type f | while IFS= read -r f; do
    if file -b "$f" | grep -q "Mach-O"; then
        printf '%s\n' "$f"
    fi
done | by_depth | while IFS= read -r f; do
    sign "$f"
done

find "$app/Contents" -type d -name "*.framework" | by_depth | while IFS= read -r f; do
    sign "$f"
done

sign "$app"
codesign --verify --deep --strict --verbose=2 "$app"
