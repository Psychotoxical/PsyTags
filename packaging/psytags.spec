# PyInstaller spec: builds dist/PsyTags/PsyTags.exe (one folder, no console window).
# Run from the repository root:  pyinstaller packaging/psytags.spec
import os

from PyInstaller.utils.hooks import collect_dynamic_libs

root = os.path.abspath(".")
a = Analysis(
    [os.path.join(root, "packaging", "psytags_main.py")],
    pathex=[root],
    datas=[(os.path.join(root, "psytags", "resources"), os.path.join("psytags", "resources"))],
    binaries=collect_dynamic_libs("onnxruntime"),
    hiddenimports=["mutagen._constants", "psytags.moodanalysis", "onnxruntime"],
    excludes=["tkinter", "PySide6.QtQml", "PySide6.QtQuick",
              "PySide6.QtWebEngineCore", "PySide6.QtMultimedia", "PySide6.Qt3DCore"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="PsyTags", console=False,
          icon=os.path.join(root, "packaging", "psytags.ico"))
coll = COLLECT(exe, a.binaries, a.datas, name="PsyTags")
