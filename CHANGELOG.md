# Changelog

Every version has its own section. The section of the version in `psytags/__init__.py` becomes the text of the release draft; the download table is added automatically. Changes that are not released yet collect under `## [Unreleased]`, which becomes the next version's section when the version number is raised.

## [Unreleased]

### Fixed

- Renaming into new folders left the new album inside the old one when the album sat in a folder of the same name with nothing else in it, as unpacked archives often do. The new album now goes next to that outer folder, and the outer folder goes to the recycle bin with the old album.

## [0.1.7] - 2026-11-13

### Fixed

- Downloading the mood models could fail on Windows with `CERTIFICATE_VERIFY_FAILED`. The model server switched to a certificate whose root Windows only adds to its store when a site first needs it. PsyTags now also trusts Mozilla's root list (certifi) on every system.

## [0.1.6] - 2026-11-12

PsyTags now runs on macOS, signed and notarized for Apple Silicon and Intel.

### Added

- **PsyTags for macOS 13 and newer**, as a disk image for Apple Silicon and one for Intel. The app is signed and notarized, so it opens without a Gatekeeper warning. It brings its own ffmpeg like the other packages.
- **Every step of the bar has Selection and All**, like Moods and Rename before: MusicBrainz, numbers, cover and genres also run on every album of the list, for instance to catch up on missing covers. All under MusicBrainz skips albums that already have a MusicBrainz album ID and analyzes no moods.

### Changed

- **Dialog buttons keep one order on every system:** < Back, Next >, Cancel, as on Windows. Linux desktops and macOS had their own order.
- **On a Mac the step bar shows the shortcuts with the Mac's symbols** (⇧⌘M), since the Command key takes the place of Ctrl there. Showing the Tag Panel, adding a folder and switching between panel, search and list use ⌃Q, ⌃H and ⌃⇥ on a Mac, because ⌘Q quits, ⌘H hides and ⌘⇥ switches programs. ⌫ also removes files from the list, as a MacBook has no forward delete. The help shows every shortcut in Mac symbols.

## [0.1.5] - 2026-11-12

A long automatic run no longer fills the memory: PsyTags stays at about 180 MB where 0.1.4 ended at several GB.

### Added

- **Files added to a tagged album**, such as bonus tracks, take the album's values from the other files during the automatic run: album ID, release group, album artist, year, original year and sort names. MusicBrainz is not asked, only empty fields are filled, and players such as Navidrome see one album again.

### Changed

- **The summary lists every album that still needs work first**, whatever is missing: open albums, then albums from Discogs, then albums without a cover or genres. Finished albums follow below.

### Fixed

- **Memory grew with every saved album** and stayed high after a run: each save kept another copy of the album's covers for undo. Every picture is now held once, shared by the files of an album and the undo history.
- **The mood analysis analyzed four songs at once on every computer**, about 600 MB each. Computers with few cores now analyze two at a time; large ones stay at four.
- **Files with a path longer than 260 characters** could not be saved, renamed or analyzed on Windows ("The system cannot find the path specified"). They now work like every other file.
- **The Tag Panel kept the values of removed files** when every file was taken out of the list. It is now empty.
- **The description of the last hovered button stayed in the status bar**, for example after a run. It now goes away after a few seconds.
- **Adding a cover from a file** opens in the folder of the selected album instead of the last opened folder.

## [0.1.4] - 2026-11-11

### Added

- **Options in four pages:** Automatic, Accounts and sources, Files, Program. Under Automatic, every step of “All albums automatically” has its own switch: moods, numbers, cover and genres can be left out.
- **New choices:** prefer digital releases, replace existing covers, minimum cover size. All of them start as before.
- **Ctrl+click on the row above an album** adds the whole album to the selection, or takes it out.
- **Fetch cover** in the right-click menu of the file list: all cover sources in order, or a single one.
- **Activity box at the foot of the Tag Panel:** what is running, with progress and the last three messages. It can be switched off under Customize Tag Panel.
- **Statistics after “All albums automatically”:** how many albums and files in how much time, how many done and open.
- **Albums tagged from Discogs are marked:** a yellow Discogs in the album row, a highlighted row in the summary with “Try MusicBrainz again”. PsyTags writes the Discogs release ID for this; a later MusicBrainz tagging removes it.

### Changed

- **“Tag Sources” is now “Search manually”**, with “MusicBrainz …” and “Discogs …”. In the ≡ menu it sits under Tagging.
- **Comments are kept by default** for new users. A stored choice stays as it is.
- **A manual search takes its cover from the cover sources** in their order, as the automatic run does.

### Fixed

- **The summary did not notice albums tagged by hand** from the main window, or genres fetched later. Their rows now show the result.

## [0.1.3] - 2026-11-11

### Changed

- **Album type is a default Tag Panel field again**, right after the MusicBrainz album ID. Existing custom panel layouts stay as they are.
- **Progress windows only show the close button.** Minimize and maximize are gone.

### Fixed

- **Customize columns and Customize Tag Panel showed the default names in German** even with English selected. They now follow the language setting.

## [0.1.2] - 2026-11-10

### Changed

- **Language and theme apply at once.** No restart needed, in the options and in the setup assistant. Loaded files, selection, search and undo history stay.
- **The setup assistant asks for the language on its first page** and switches right away.
- **First start follows the system language:** German on a German system, English everywhere else.

### Fixed

- **Linux AppImage:** no more Fontconfig errors at startup on newer distributions. The AppImage now uses the system's Fontconfig and FreeType.

## [0.1.1] - 2026-11-10

### Fixed

- **Linux AppImage:** Last.fm, Discogs, MusicBrainz, covers and the mood models could not connect on distributions such as Arch or CachyOS ("not accepted, or the server cannot be reached right now"). PsyTags now also loads the system's certificate bundle.

## [0.1.0] - 2026-11-10

The first public version of PsyTags, a tag editor for large music collections on Windows and Linux.

### Highlights

- **One command for the whole list:** moods, MusicBrainz tags, track and disc numbers, cover and genres, album by album. An album is only tagged when the match is certain; everything else stays open and is listed in the summary.
- **Moods from the audio:** analyzed locally, no audio leaves your computer.
- **Discogs as second source** for albums MusicBrainz leaves open (free token, text only).
- **Rename by chips:** click a naming scheme together, no format language.
- **Setup assistant** on first start, help for every function (F1), English and German.
