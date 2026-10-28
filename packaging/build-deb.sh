#!/bin/bash
# Builds readers-video-editor_<version>_all.deb next to this script. Needs dpkg-deb and fakeroot.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"; SRC="$HERE/.."
VERSION=$(grep -oE '^VERSION = "[^"]+"' "$SRC/readers_video_editor.py" | cut -d'"' -f2)
ROOT="$HERE/deb-root"; rm -rf "$ROOT"
install -Dm755 "$SRC/readers_video_editor.py" "$ROOT/usr/lib/readers-video-editor/readers_video_editor.py"
for f in "$HERE"/fonts/*; do install -Dm644 "$f" "$ROOT/usr/lib/readers-video-editor/fonts/$(basename "$f")"; done
install -Dm755 /dev/stdin "$ROOT/usr/bin/readers-video-editor" <<'SH'
#!/bin/sh
exec python3 /usr/lib/readers-video-editor/readers_video_editor.py "$@"
SH
install -Dm644 "$HERE/readers-video-editor.desktop" "$ROOT/usr/share/applications/readers-video-editor.desktop"
install -Dm644 "$HERE/readers-video-editor.svg" "$ROOT/usr/share/icons/hicolor/scalable/apps/readers-video-editor.svg"
install -Dm644 "$SRC/LICENSE" "$ROOT/usr/share/doc/readers-video-editor/copyright"
mkdir -p "$ROOT/DEBIAN"
cat > "$ROOT/DEBIAN/control" <<CTRL
Package: readers-video-editor
Version: $VERSION
Section: video
Priority: optional
Architecture: all
Depends: python3 (>= 3.8), python3-pyqt5, python3-pyqt5.qtmultimedia, python3-numpy, python3-soundfile, ffmpeg, gstreamer1.0-plugins-good, gstreamer1.0-libav
Recommends: python3-pip
Maintainer: funkypitt <pierregallaz@gmail.com>
Homepage: https://github.com/funkypitt/readers-video-editor
Description: Cut a video or a recording by highlighting its text
 The words of a video or a recording, transcribed on this computer or read
 from a subtitle file, on a page; what you highlight is kept (or cut), the
 cuts land in the quiet between two words, each piece gets its fades, and
 ffmpeg writes the new file with a log of the cuts and an edit list. Also a
 comfortable reading of the transcript, which can be saved as text.
 The transcription needs faster-whisper (pip install faster-whisper).
CTRL
fakeroot dpkg-deb --build "$ROOT" "$HERE/readers-video-editor_${VERSION}_all.deb"
rm -rf "$ROOT"
echo "built $HERE/readers-video-editor_${VERSION}_all.deb"
