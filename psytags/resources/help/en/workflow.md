# How it works

The usual way takes four moves:

1. **Open folder** (Ctrl+D) to load the albums. **Add folder** (Ctrl+H) adds more.
2. Press **All albums automatically** (Ctrl+Alt+B).
3. Look in the [summary](help:summary) for what stayed open, and settle it there.
4. Select everything (Ctrl+A) and name files and folders with **Rename** (Alt+1).

## What the automatic run does

For each album in the list, in this order:

| Step | What happens |
|---|---|
| [Moods](help:moods) | Each song is analyzed from its audio. |
| [MusicBrainz](help:sources) | The matching release is looked up and the tags are written. If it stays open and a token is set, Discogs is asked. |
| [Numbers](help:numbers) | Track and disc numbers are written. |
| [Cover](help:covers) | The cover sources are asked in order. |
| [Genres](help:genres) | Last.fm delivers the genres. |

An album is only tagged when it clearly fits. Otherwise it stays unchanged and is listed as open in the summary, with only the moods already written. Better open than wrong.

The window can stay in the background during a run. You can cancel a run, and whatever is finished by then stays.

## Single steps

Each step can also run alone for the selected files, from the bar at the top or with the [keyboard shortcuts](help:shortcuts).

In the file list, the right side of each album row shows the state of album, cover, genres and moods.
