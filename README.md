# PsyTags

PsyTags is a tag editor for music collections. It runs on Windows, Linux and macOS, and its interface is available in English and German.

The main window has a file list and a tag panel. One command tags every loaded album, and each step can also be run on its own. Moods are determined locally from the audio.

PsyTags is young. Downloads for Windows, Linux and macOS are on the [Releases](https://github.com/Psychotoxical/PsyTags/releases) page.

![Main window of PsyTags with the file list on the left and the tag panel on the right](docs/screenshot.png)

## Why PsyTags

For about 25 years Mp3tag by Florian Heidenreich has been one of the programs I use most. What I came to miss was automation for a large collection. PsyTags is built for my own workflow first: it does as much as possible on its own, and the final check stays as simple and clear as in Mp3tag, which inspired it. I am grateful for those years and for that inspiration.

PsyTags is an independent project and is not affiliated with or endorsed by Mp3tag or its author.

## Before you start

PsyTags writes to your music files and renames them. Try it on copies of a few albums first.

Undo (Ctrl+Z, on a Mac ⌘Z) reverts tag changes and renames while the program is running. Deleted files always go to the recycle bin.

## Usage

1. Open a folder (Ctrl+D).
2. Run **All albums automatically** (Ctrl+Alt+B).
3. Check the summary and finish whatever stayed open.
4. Rename the files with **All** in the Rename step. **Selection** (Alt+1) renames only the selected files.

F1 opens the help, which covers every feature.

On a Mac, Ctrl is the Command key (⌘) and Alt the Option key (⌥); the step bar and the help show the Mac symbols. Showing the Tag Panel, adding a folder and switching between panel, search and list use the Control key there (⌃Q, ⌃H, ⌃⇥), since macOS keeps ⌘Q, ⌘H and ⌘⇥ for itself.

## The automatic run

For each album in the list, in this order:

| Step | Result |
|---|---|
| Moods | Each song is analyzed and the MOOD field is written. |
| MusicBrainz | The matching release is looked up and the tags are written. If it stays open and a token is set, Discogs is asked. |
| Numbers | Track and disc numbers are written. |
| Cover | The enabled cover sources are asked in order. |
| Genres | Genres are fetched from Last.fm. |

An album is only tagged when the match is certain. A release must have a file for every track, matched by title. Otherwise the album stays unchanged apart from its moods, and the summary lists it as open.

## Moods

The analysis uses two models of about 20 MB, downloaded on first use. No audio leaves your computer. The result is written to MOOD and no later step overwrites it. Options lets you choose between few, normal and many moods per song.

## Services

| Service | Used for | Setup |
|---|---|---|
| MusicBrainz | Tags | None |
| Cover Art Archive | Covers | None |
| Discogs | Second source for albums MusicBrainz leaves open, text only | Free personal token |
| Last.fm | Genres | Free API key |

More cover sources can be added as plugins. The help describes the format.

## Supported formats

AAC, AIFF, APE, DSF, FLAC, M4A, M4B, MP2, MP3, MP4, MPC, OGG, Opus, Speex, TAK, TTA, WAV, WMA, WavPack

## Installation

Download from the [Releases](https://github.com/Psychotoxical/PsyTags/releases) page:

- **Windows 10 and 11:** `PsyTags-Setup-<version>.exe`. It installs for your user without admin rights; the first page also offers an installation for all users. Your settings stay when you uninstall.
- **Debian, Ubuntu, Mint:** `psytags_<version>_amd64.deb`, installed with `sudo apt install ./psytags_<version>_amd64.deb`.
- **Fedora, openSUSE:** `psytags-<version>-1.x86_64.rpm`, installed with `sudo dnf install ./psytags-<version>-1.x86_64.rpm` or `sudo zypper install`.
- **Other Linux:** `PsyTags-x86_64.AppImage`. Make it executable (`chmod +x`) and start it.
- **macOS 13 or newer:** `PsyTags-<version>-macOS-arm64.dmg` for Apple Silicon (M1 and later), `PsyTags-<version>-macOS-x86_64.dmg` for Intel. Open it and drag PsyTags into Applications. The app is signed and notarized by Apple.

All of them come with ffmpeg for the mood analysis.

## Running from source

Requires Python 3.11 or newer and, for the mood analysis, ffmpeg.

```
git clone https://github.com/Psychotoxical/PsyTags.git
cd PsyTags
python -m venv .venv
.venv/bin/pip install .
.venv/bin/psytags [folder ...]
```

On Windows the scripts are in `.venv\Scripts`.

## Tests

```
pip install -e .
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests
ruff check .
```

Changes go to `main` through pull requests only. Every pull request runs the tests on Linux, Windows and macOS (Intel and Apple Silicon), Ruff, ShellCheck and actionlint, and builds all packages; the Linux packages are test-installed on Ubuntu and Fedora, the Mac apps are signed, notarized and checked by Gatekeeper.

## Releases

A release starts with a new version number in `psytags/__init__.py` and `pyproject.toml` and its section in `CHANGELOG.md`. Once that is on `main`, the workflow creates a release draft with the section as text and the installer, AppImage, deb, rpm and both Mac disk images attached. Publishing the draft creates the tag.

## Acknowledgements

The color themes Mocha and Latte come from Catppuccin and are licensed under MIT.

## License

Copyright (C) 2026 Psychotoxical. PsyTags is licensed under GPL-3.0-or-later; the full text is in [LICENSE](LICENSE).

The mood models are not part of this repository. They come from the Music Technology Group at Universitat Pompeu Fabra and are licensed under CC BY-NC-SA 4.0. The Last.fm terms allow non-commercial use only. The in-app About window lists all libraries and services with their licenses.
