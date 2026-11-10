#!/usr/bin/env bash
# Packs dist/PsyTags into dist/PsyTags-x86_64.AppImage. Run from the repository root after PyInstaller.
set -euo pipefail

TOOL_URL=https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage
TOOL_SHA256=ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0
RUNTIME_URL=https://github.com/AppImage/type2-runtime/releases/download/20251108/runtime-x86_64
RUNTIME_SHA256=2fca8b443c92510f1483a883f60061ad09b46b978b2631c807cd873a47ec260d

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
curl -fsSL -o "$work/appimagetool" "$TOOL_URL"
curl -fsSL -o "$work/runtime" "$RUNTIME_URL"
echo "$TOOL_SHA256  $work/appimagetool" | sha256sum -c -
echo "$RUNTIME_SHA256  $work/runtime" | sha256sum -c -
chmod +x "$work/appimagetool"

app="$work/PsyTags.AppDir"
mkdir "$app"
cp -a dist/PsyTags "$app/PsyTags"
cp packaging/psytags.svg "$app/psytags.svg"
ln -s psytags.svg "$app/.DirIcon"
sed -e 's/^Exec=.*/Exec=PsyTags %F/' -e '/^MimeType=/d' psytags.desktop > "$app/psytags.desktop"
cat > "$app/AppRun" <<'EOF'
#!/bin/sh
here="$(dirname "$(readlink -f "$0")")"
exec "$here/PsyTags/PsyTags" "$@"
EOF
chmod +x "$app/AppRun"

ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$work/appimagetool" --no-appstream --runtime-file "$work/runtime" \
    "$app" dist/PsyTags-x86_64.AppImage
