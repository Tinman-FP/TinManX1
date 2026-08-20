#!/bin/bash

set -euo pipefail

FFMPEG_VERSION="8.1.2"
FFMPEG_SHA256="464beb5e7bf0c311e68b45ae2f04e9cc2af88851abb4082231742a74d97b524c"
FFMPEG_URL="https://ffmpeg.org/releases/ffmpeg-${FFMPEG_VERSION}.tar.xz"

ARCH="${1:-$(uname -m)}"
case "$ARCH" in
    arm64) FFMPEG_ARCH="arm64" ;;
    x86_64) FFMPEG_ARCH="x86_64" ;;
    *) echo "Unsupported macOS architecture: $ARCH" >&2; exit 2 ;;
esac

FFMPEG_ARCH_ARGS=()
if [ "$ARCH" = "x86_64" ] && ! command -v nasm >/dev/null 2>&1; then
    echo "nasm is unavailable; building the Intel RTSP bridge without x86 assembly" >&2
    FFMPEG_ARCH_ARGS+=(--disable-x86asm)
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_ROOT="${TMPDIR:-/tmp}/tinmanx1-rtsp-bridge-${FFMPEG_VERSION}-${ARCH}"
ARCHIVE="$BUILD_ROOT/ffmpeg-${FFMPEG_VERSION}.tar.xz"
SOURCE="$BUILD_ROOT/ffmpeg-${FFMPEG_VERSION}"
BUILD="$BUILD_ROOT/build"
DESTINATION="$ROOT/resources/orcaslicer_codex/tools"
CONFIG_SIGNATURE="$(shasum -a 256 "$0" | awk '{print $1}')"
CONFIG_STAMP="$BUILD/.tinman-config-$CONFIG_SIGNATURE"

mkdir -p "$BUILD_ROOT" "$BUILD" "$DESTINATION"
if [ ! -f "$ARCHIVE" ]; then
    curl --fail --location --retry 3 "$FFMPEG_URL" --output "$ARCHIVE"
fi
printf '%s  %s\n' "$FFMPEG_SHA256" "$ARCHIVE" | shasum -a 256 -c -

if [ ! -x "$SOURCE/configure" ]; then
    tar -xf "$ARCHIVE" -C "$BUILD_ROOT"
fi

if [ ! -f "$CONFIG_STAMP" ]; then
    rm -rf "$BUILD"
    mkdir -p "$BUILD"
    (
        cd "$BUILD"
        "$SOURCE/configure" \
            --cc=clang \
            --arch="$FFMPEG_ARCH" \
            --target-os=darwin \
            "${FFMPEG_ARCH_ARGS[@]}" \
            --disable-autodetect \
            --disable-doc \
            --disable-debug \
            --disable-ffplay \
            --disable-ffprobe \
            --disable-avdevice \
            --disable-swresample \
            --disable-everything \
            --enable-ffmpeg \
            --enable-network \
            --enable-protocol=file,pipe,tcp,udp,rtp \
            --enable-demuxer=rtsp,rtp \
            --enable-decoder=h264 \
            --enable-parser=h264 \
            --enable-filter=fps,scale \
            --enable-encoder=mjpeg \
            --enable-muxer=image2,image2pipe \
            --enable-swscale \
            --enable-pthreads \
            --extra-cflags="-O2 -arch $ARCH -mmacosx-version-min=10.15" \
            --extra-ldflags="-arch $ARCH -mmacosx-version-min=10.15"
        touch "$CONFIG_STAMP"
    )
fi

make -C "$BUILD" -j"$(sysctl -n hw.logicalcpu)" ffmpeg
strip "$BUILD/ffmpeg"
cp "$BUILD/ffmpeg" "$DESTINATION/tinman-rtsp-bridge"
chmod 755 "$DESTINATION/tinman-rtsp-bridge"
cp "$SOURCE/COPYING.LGPLv2.1" "$DESTINATION/FFmpeg-LGPL-2.1.txt"

echo "Built $DESTINATION/tinman-rtsp-bridge for $ARCH"
