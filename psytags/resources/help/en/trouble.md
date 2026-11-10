# Troubleshooting

Why single albums stay open is explained under [The summary](help:summary).

## Workflow

| Problem | What helps |
|---|---|
| Something looks wrong after the run | **Undo** (Ctrl+Z), while the program is running. Work on [copies](help:start) first. |
| The run is slow | MusicBrainz allows only one request per second, and the mood analysis listens to each song. With many albums this takes a while. |
| "All albums in this list are already done" | Finished albums do not run again in this session. Load the folder again or do single steps by hand. |
| The summary is empty | It shows the last automatic run of this session. After a restart there is none yet. |

## Files

| Problem | What helps |
|---|---|
| Write errors | The file is read-only or open in a player. Close the player and try again. |
| A file cannot be read or tagged | It is probably damaged. Check whether it plays. |
| Songs are missing from the album | PsyTags cannot add them. The album stays open, unless only the last track is missing. |
| Images or cue files are gone after renaming | They are in the recycle bin if cleaning up old folders was on. |

## Moods

| Problem | What helps |
|---|---|
| ffmpeg is not found | The Windows package and the AppImage bring it along, so download PsyTags again. If you run PsyTags on Linux any other way, install it with your package manager and restart PsyTags. |
| The models do not load | Check your internet connection and open the **setup assistant** in the ≡ menu again. |
| The moods seem wrong | Choose another amount under **Options → Moods** and analyze again. |

## Services

| Problem | What helps |
|---|---|
| Red cross behind a key | Check the key, also for spaces. If it appears suddenly, the service may just be unreachable. |
| "Discogs refuses the token" | Create a new token at discogs.com/settings/developers and enter it under **Options → Discogs**. |
| Discogs is grayed out in the menu | No token has been entered yet. |
| MusicBrainz is busy | PsyTags tries again by itself. If it stays that way, start again later. |
| No cover | The Cover Art Archive needs a MusicBrainz ID. Add more sources with [cover plugins](help:plugins). |
| Cover too small | Lower the [minimum size](help:covers) or use another source. |
| No genres | Last.fm does not know the album, or the API key is missing. |
