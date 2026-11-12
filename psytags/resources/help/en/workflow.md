# How it works

The usual way takes four moves:

1. **Open folder** (Ctrl+D) to load the albums. **Add folder** (Ctrl+H) adds more.
2. Press **All albums automatically** (Ctrl+Alt+B).
3. Look in the [summary](help:summary) for what stayed open, and settle it there.
4. Name all files and folders with **All** under **Rename**. **Selection** (Alt+1) only takes the selected files.

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

If some files of an album already have a MusicBrainz release and others do not, such as bonus tracks added later, MusicBrainz is not asked. The other files take the album's values from the tagged ones: album ID, release group, album artist, year, original year and sort names. Only empty fields are filled; titles and track IDs stay as they are. That way players such as Navidrome see all files as one album.

The window can stay in the background during a run. You can cancel a run, and whatever is finished by then stays.

## Single steps

Each step can also run alone, from the bar at the top or with the [keyboard shortcuts](help:shortcuts). **Selection** takes the selected files, **All** every album in the list, for instance to catch up on missing covers.

**All** under **MusicBrainz** skips albums that already have a MusicBrainz album ID and analyzes no moods. As in the automatic run, only clear matches are tagged; the summary shows the result afterwards.

In the file list, the right side of each album row shows the state of album, cover, genres and moods. A yellow **Discogs** means: tagged, but from Discogs instead of MusicBrainz.
