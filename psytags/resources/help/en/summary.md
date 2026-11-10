# The summary

| This is where all corrections happen after an automatic run. |
|---|

The summary opens by itself at the end of a run. The **Summary** button at the top brings it back at any time while the program is running. It always shows the last run.

Open albums are listed first.

## What the columns mean

| Column | Meaning |
|---|---|
| Album | Artist and album |
| Result | **Done** or **Open** |
| Cover, Genres | ☒ worked, ☐ failed, – did not run. The tooltip gives the reason. |
| Details | The chosen release and notes such as "From Discogs" or "Last track missing"; for open albums, the reason |

## What you correct here

**Open albums:** the **Edit** button or a double click opens the MusicBrainz results, with the reason the album stayed open above them. You choose and adjust the assignment yourself. Afterwards it says "Tagged manually".

If MusicBrainz finds nothing, select the album in the list and search by hand with **Tag Sources → Discogs**.

**Missing cover or genres:** the **Retry** button asks again. For a cover, you can pick from the results when no match is certain. The summary notices a cover you set some other way the next time it opens.

**Files without a track:** at the bottom are files the release has no track for, such as bonus tracks. Tick what should go and press **Move to recycle bin**.

## Why an album stays open

| Message | Meaning | What helps |
|---|---|---|
| Title does not match: "A" instead of "B" | A title in your files finds no track in the release. | Check that it really is the same album, then choose by hand. |
| 12 tracks / 10 files | The release has a different number of tracks than the folder. | Songs are often missing. Assign by hand or leave the album open. |
| Length differs by 45 s: title | A song is clearly longer or shorter. | May be another version. Check by hand. |
| Title is ambiguous: title | A title occurs twice and the lengths do not help. | Assign by hand. |
| Several editions with different track lists | Several editions fit equally well. | Choose the edition you want by hand. |
| No matching edition found | The database does not know the album. | Check the album tag, try Discogs, otherwise tag by hand. |
| No album tag | The files have no album name. | Enter the album in the Tag Panel and start again. |

Open albums are not an error. Self-tagged downloads, promos and rare pressings are often in no database at all.

## Afterwards

Once the open albums are settled, go on with [Rename](help:rename).
