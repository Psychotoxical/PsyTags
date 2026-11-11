# Changelog

Every version has its own section. The section of the version in `psytags/__init__.py` becomes the text of the release draft; the download table is added automatically. Changes that are not released yet collect under `## [Unreleased]`, which becomes the next version's section when the version number is raised.

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
