@echo off
rem Builds dist\PsyTags\PsyTags.exe on Windows. Needs Python 3.11+ (python.org).
cd /d "%~dp0\.."
python -m pip install --upgrade pyside6-essentials mutagen pyinstaller || exit /b 1
python -m PyInstaller --noconfirm --clean packaging\psytags.spec || exit /b 1
echo Fertig: dist\PsyTags\PsyTags.exe
