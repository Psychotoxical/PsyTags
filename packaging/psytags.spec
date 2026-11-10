# PyInstaller spec: builds dist/PsyTags/PsyTags.exe (one folder, no console window).
# Run from the repository root:  pyinstaller packaging/psytags.spec
# On Windows the package brings its own ffmpeg: the one in PSYTAGS_FFMPEG, otherwise the one in
# the PATH. On Linux it does so only if PSYTAGS_FFMPEG is set, as for the AppImage.
# Next to its bin folder the build expects the LICENSE of that ffmpeg.
import os
import shutil
import sys

from PyInstaller.utils.hooks import collect_dynamic_libs


def ffmpeg_files():
    if sys.platform != "win32" and not os.environ.get("PSYTAGS_FFMPEG"):
        return []                       # Linux: from the package manager
    found = os.environ.get("PSYTAGS_FFMPEG") or shutil.which("ffmpeg")
    if not found:
        raise SystemExit("ffmpeg not found: set PSYTAGS_FFMPEG or put it in the PATH")
    exe = os.path.realpath(found)
    notice = os.path.join(os.path.dirname(os.path.dirname(exe)), "LICENSE")
    if not os.path.isfile(notice):
        raise SystemExit(f"The license of ffmpeg is missing: {notice}")
    return [(exe, "ffmpeg"), (notice, "ffmpeg")]


root = os.path.abspath(".")
a = Analysis(
    [os.path.join(root, "packaging", "psytags_main.py")],
    pathex=[root],
    datas=[(os.path.join(root, "psytags", "resources"), os.path.join("psytags", "resources"))] + ffmpeg_files(),
    binaries=collect_dynamic_libs("onnxruntime"),
    hiddenimports=["mutagen._constants", "psytags.moodanalysis", "onnxruntime"],
    excludes=["tkinter", "PySide6.QtQml", "PySide6.QtQuick",
              "PySide6.QtWebEngineCore", "PySide6.QtMultimedia", "PySide6.Qt3DCore"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="PsyTags", console=False,
          icon=os.path.join(root, "packaging", "psytags.ico"))
coll = COLLECT(exe, a.binaries, a.datas, name="PsyTags")
