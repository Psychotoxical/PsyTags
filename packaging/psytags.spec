# PyInstaller spec: builds dist/PsyTags/PsyTags.exe (one folder, no console window), on macOS
# also dist/PsyTags.app.
# Run from the repository root:  pyinstaller packaging/psytags.spec
# On Windows and macOS the package brings its own ffmpeg: the one in PSYTAGS_FFMPEG, otherwise the
# one in the PATH. On Linux it does so only if PSYTAGS_FFMPEG is set, as for the AppImage.
# Next to its bin folder the build expects the LICENSE of that ffmpeg.
# The macOS icon is drawn from psytags.svg; PyInstaller needs Pillow to turn it into .icns.
import os
import shutil
import sys

from PyInstaller.utils.hooks import collect_dynamic_libs

sys.path.insert(0, os.path.abspath("."))
from psytags import __version__  # noqa: E402

MAC = sys.platform == "darwin"


def ffmpeg_files():
    """(binaries, datas) for the bundled ffmpeg."""
    if sys.platform.startswith("linux") and not os.environ.get("PSYTAGS_FFMPEG"):
        return [], []                   # Linux: from the package manager
    found = os.environ.get("PSYTAGS_FFMPEG") or shutil.which("ffmpeg")
    if not found:
        raise SystemExit("ffmpeg not found: set PSYTAGS_FFMPEG or put it in the PATH")
    exe = os.path.realpath(found)
    notice = os.path.join(os.path.dirname(os.path.dirname(exe)), "LICENSE")
    if not os.path.isfile(notice):
        raise SystemExit(f"The license of ffmpeg is missing: {notice}")
    if MAC:                             # a program in the bundle must be signed like a library
        return [(exe, "ffmpeg")], [(notice, "ffmpeg")]
    return [], [(exe, "ffmpeg"), (notice, "ffmpeg")]


def mac_icon():
    """A 1024 px PNG of the app icon; PyInstaller converts it."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841
    image = QImage(1024, 1024, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    QSvgRenderer(os.path.join(root, "packaging", "psytags.svg")).render(painter)
    painter.end()
    path = os.path.join(workpath, "psytags-1024.png")
    image.save(path)
    return path


root = os.path.abspath(".")
ffmpeg_binaries, ffmpeg_datas = ffmpeg_files()
a = Analysis(
    [os.path.join(root, "packaging", "psytags_main.py")],
    pathex=[root],
    datas=[(os.path.join(root, "psytags", "resources"), os.path.join("psytags", "resources"))] + ffmpeg_datas,
    binaries=collect_dynamic_libs("onnxruntime") + ffmpeg_binaries,
    hiddenimports=["mutagen._constants", "psytags.moodanalysis", "onnxruntime"],
    excludes=["tkinter", "PySide6.QtQml", "PySide6.QtQuick",
              "PySide6.QtWebEngineCore", "PySide6.QtMultimedia", "PySide6.Qt3DCore"],
)
# Fontconfig reads the configuration of the running system; one from the build machine
# rejects newer files ("invalid attribute 'xsi:nil'"). FreeType goes with it. Every desktop
# Linux has both, so the package uses the system's, as AppImages usually do.
if sys.platform.startswith("linux"):
    SYSTEM_LIBS = ("libfontconfig.so", "libfreetype.so")
    a.binaries = [b for b in a.binaries if not os.path.basename(b[0]).startswith(SYSTEM_LIBS)]

icon = mac_icon() if MAC else os.path.join(root, "packaging", "psytags.ico")
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="PsyTags", console=False, icon=icon)
coll = COLLECT(exe, a.binaries, a.datas, name="PsyTags")
if MAC:
    app = BUNDLE(
        coll,
        name="PsyTags.app",
        icon=icon,
        bundle_identifier="io.github.psychotoxical.psytags",
        version=__version__,
        info_plist={
            "CFBundleDisplayName": "PsyTags",
            "CFBundleShortVersionString": __version__,
            "LSMinimumSystemVersion": "13.0",
            "NSHighResolutionCapable": True,
            "NSHumanReadableCopyright": "GPL-3.0-or-later",
        },
    )
