# MusicBrainz and Discogs

This is where title, album, artist, year, label and catalog number come from.

## Automatically

**MusicBrainz automatically** (Ctrl+Shift+B) tags the selected album when it is recognized for certain. Otherwise the results open. **All albums automatically** (Ctrl+Alt+B) does this for the whole list without asking.

A release is only taken when:

- every track of the release finds its own file, by title and independent of the order,
- at most three files are left over, and at most a quarter of all files,
- the lengths do not differ a lot. Files may differ by some seconds and still be the same song.

Digital editions are preferred when there are any. Additions like "(Deluxe Edition)" in the album tag are left out in a second search.

If exactly the last track is missing, the release is taken when everything else fits exactly. The [summary](help:summary) then names the missing track. If a track is missing in the middle of an album, it stays open.

## Discogs as a second source

If an album stays open at MusicBrainz, PsyTags looks it up on Discogs when a token is set. You get one for free at [discogs.com/settings/developers](https://www.discogs.com/settings/developers) and enter it under **Options → Discogs**. A green check mark shows that it works.

The same rules apply to Discogs, and all track lengths must be known as well. Only texts come from there and never pictures, because covers there are mostly photos by users. The other sources fetch the cover.

## By hand

**Search MusicBrainz** (Ctrl+I) or **Tag Sources → Discogs** open the search form. Then you choose from the results.

In the window **Check the assignment**, the tracks of the source are on the left and your files on the right. Move files into the right row by drag and drop or with Alt+↑/↓. Rows marked in yellow differ by more than 3 seconds. On the left you choose which fields are written.

**Search MusicBrainz (Quick)** (Ctrl+Shift+I) skips the search form.

Comments are deleted on import while **Options → MusicBrainz → Delete comments by default** is on. Year and original year get only the year (2026 instead of 2026-10-11). For the full date, set **Options → MusicBrainz → Release date** to **Full date**; this applies to Discogs as well.
