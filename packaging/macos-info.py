"""The macOS build's Info.plist completed after PyInstaller: the version, and the documents the
app opens from the Finder (Open With, the Dock icon), as an alternative, never the default.
usage: python packaging/macos-info.py "dist/Readers Video Editor.app" 1.12.1"""
import plistlib
import sys

app, version = sys.argv[1], sys.argv[2]
path = app + "/Contents/Info.plist"
with open(path, "rb") as f:
    info = plistlib.load(f)
info["CFBundleShortVersionString"] = version
info["CFBundleVersion"] = version
# numpy, PyAV and onnxruntime wheels for Apple silicon are built for macOS 14: an older Mac must be
# told by the Finder, not see the app vanish at its first import
info["LSMinimumSystemVersion"] = "14.0"
info["CFBundleDocumentTypes"] = [
    {"CFBundleTypeName": "Video or recording", "CFBundleTypeRole": "Viewer", "LSHandlerRank": "Alternate",
     "LSItemContentTypes": ["public.movie", "public.audio", "public.audiovisual-content"]},
    {"CFBundleTypeName": "Subtitles or project", "CFBundleTypeRole": "Viewer", "LSHandlerRank": "Alternate",
     "CFBundleTypeExtensions": ["srt", "json"]},
]
with open(path, "wb") as f:
    plistlib.dump(info, f)
print("Info.plist:", version, len(info["CFBundleDocumentTypes"]), "document types")
