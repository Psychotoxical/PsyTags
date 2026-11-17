#!/usr/bin/env bash
# Signs PsyTags.app with a Developer ID for notarization: every program and library inside
# first, then the frameworks, then the app, all with the hardened runtime and a timestamp.
# Usage: sign_macos.sh APP "Developer ID Application: Name (TEAMID)"
set -euo pipefail

app=${1:?app bundle}
identity=${2:?signing identity}
entitlements=$(cd "$(dirname "$0")" && pwd)/psytags.entitlements

# Apple's timestamp service sometimes does not answer ("A timestamp was expected but was not
# found"); a few more tries with a pause get past that.
sign() {
    local try
    for try in 1 2 3 4 5; do
        if codesign --force --timestamp --options runtime --entitlements "$entitlements" \
            --sign "$identity" "$1"; then
            return 0
        fi
        echo "codesign failed for $1 (try $try), trying again" >&2
        sleep $((try * 10))
    done
    return 1
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
