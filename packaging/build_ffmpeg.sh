#!/usr/bin/env bash
# Builds a small LGPL ffmpeg that can only turn the audio formats PsyTags reads into raw samples.
# Usage: build_ffmpeg.sh linux|windows|macos OUTPUT_FOLDER
# macos builds on a Mac for its own architecture; the others build on Linux.
# Result: OUTPUT_FOLDER/bin/ffmpeg (or ffmpeg.exe) and OUTPUT_FOLDER/LICENSE
set -euo pipefail

VERSION=9.0.2
SHA256=8c3850283eb25fa026482078a04051e0be17347b09ef81a0849bec15a96e002e

target=${1:?linux, windows or macos}
mkdir -p "${2:?output folder}"
output=$(cd "$2" && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

curl -fsSL -o "$work/ffmpeg.tar.xz" "https://ffmpeg.org/releases/ffmpeg-$VERSION.tar.xz"
echo "$SHA256  $work/ffmpeg.tar.xz" | shasum -a 256 -c -
tar -xf "$work/ffmpeg.tar.xz" -C "$work"
cd "$work/ffmpeg-$VERSION"

case "$target" in
    linux) platform=(--extra-ldflags=-static) ;;
    windows) platform=(--target-os=mingw32 --arch=x86_64 --cross-prefix=x86_64-w64-mingw32- --extra-ldflags=-static) ;;
    # macOS links only against its own libraries, never fully static
    macos) platform=(--extra-cflags=-mmacosx-version-min=13.0 --extra-ldflags=-mmacosx-version-min=13.0) ;;
    *) echo "unknown target: $target" >&2; exit 1 ;;
esac

decoders=aac,aac_latm,alac,ape,dsd_lsbf,dsd_lsbf_planar,dsd_msbf,dsd_msbf_planar,flac,mp1float,mp2float,mp3float
decoders+=,mpc7,mpc8,opus,speex,tak,tta,vorbis,wavpack,wmalossless,wmapro,wmav1,wmav2,wmavoice,'pcm_*','adpcm_*'
demuxers=aac,aiff,ape,asf,dsf,flac,mov,mp3,mpc,mpc8,ogg,tak,tta,wav,wv
parsers=aac,aac_latm,flac,mpegaudio,opus,tak,vorbis

./configure "${platform[@]}" \
    --disable-everything --disable-autodetect --disable-doc --disable-debug --disable-network \
    --disable-ffplay --disable-ffprobe --disable-iconv \
    --enable-small --enable-static --disable-shared \
    --enable-ffmpeg --enable-avfilter --enable-swresample \
    --enable-protocol=file,pipe \
    --enable-filter=aformat,anull,aresample,format,null \
    --enable-muxer=pcm_f32le --enable-encoder=pcm_f32le \
    --enable-demuxer="$demuxers" --enable-decoder="$decoders" --enable-parser="$parsers"
make -j"$(getconf _NPROCESSORS_ONLN)"

mkdir -p "$output/bin"
binary=ffmpeg
[ "$target" = windows ] && binary=ffmpeg.exe
cp "$binary" "$output/bin/$binary"
cp COPYING.LGPLv2.1 "$output/LICENSE"
