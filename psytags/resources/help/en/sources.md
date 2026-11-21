# MusicBrainz and Discogs

This is where title, album, artist, year, label and catalog number come from.

## Automatically

**MusicBrainz automatically** (Ctrl+Shift+B) tags the selected album when it is recognized for certain. Otherwise the results open. **All albums automatically** (Ctrl+Alt+B) does this for the whole list without asking.

A release is only taken when:

- every track of the release finds its own file, by title and independent of the order,
- at most three files are left over, and at most a quarter of all files,
- the lengths do not differ a lot. Files may differ by some seconds and still be the same song.

Digital editions are preferred when there are any, as long as **Options → Automatic → MusicBrainz → Prefer digital releases** is on. Additions like "(Deluxe Edition)" in the album tag are left out in a second search.

If exactly the last track is missing, the release is taken when everything else fits exactly. The [summary](help:summary) then names the missing track. If a track is missing in the middle of an album, it stays open.

## Discogs as a second source

If an album stays open at MusicBrainz, PsyTags looks it up on Discogs when a token is set. You get one for free at [discogs.com/settings/developers](https://www.discogs.com/settings/developers) and enter it under **Options → Accounts and sources → Discogs**. A green check mark shows that it works.

The same rules apply to Discogs, and all track lengths must be known as well. Only texts come from there and never pictures, because covers there are mostly photos by users. The other sources fetch the cover.

## Beatport as a third source

If MusicBrainz and Discogs leave an album open, PsyTags looks it up on Beatport. This needs your own API access: Beatport grants a client ID and secret only on request, through the [Beatport partner portal](https://partnerportal.beatport.com/hc/en-us/requests/new). Enter both with your Beatport account and password under **Options → Accounts and sources → Beatport** and click **Sign in**. PsyTags keeps the sign-in, not the password; it renews the sign-in by itself.

The same rules apply as for Discogs. Beatport also delivers BPM and key for every track. The title carries the mix, for example "Title (Extended Mix)"; the original mix gets no note. Once you are signed in, Beatport also appears in the list of [cover sources](help:covers).

## By hand

**Search MusicBrainz** (Ctrl+I), **Search manually → Discogs …** or **Search manually → Beatport …** in the right-click menu open the search form. Then you choose from the results.

In the window **Check the assignment**, the tracks of the source are on the left and your files on the right. Move files into the right row by drag and drop or with Alt+↑/↓; several selected files move together and stay selected. Rows marked in yellow differ by more than 3 seconds. If the file names do not fit the sound, **By length** matches the files by their playing time; **By title** matches them by their titles again. On the left you choose which fields are written.

**Search MusicBrainz (Quick)** (Ctrl+Shift+I) skips the search form.

Comments are deleted on import when **Options → Automatic → MusicBrainz → Delete comments by default** is on (default: off). Year and original year get only the year (2026 instead of 2026-10-11). For the full date, set **Options → Automatic → MusicBrainz → Release date** to **Full date**; this applies to Discogs as well.

## Releases with a DVD

When a release has a DVD or Blu-ray beside its CDs, only the tracks of the CDs count, in the automatic and by hand: the files of a rip are the CDs. The disc numbers then count without the DVD. When there is a file for every track of the release, the whole release stays.

When files are left over after the CD tracks and their titles fit tracks of the DVD, those DVD tracks are matched too; their track and disc numbers are those of the whole release. The window **Check the assignment** then has **Show DVD tracks**: it shows every track of the DVD, so files left over can be placed by hand. The box appears only when there are more files than tracks on the CDs.

## When MusicBrainz is overloaded

When MusicBrainz answers “HTTP 503”, PsyTags asks again. How often and how far apart is set under **Options → Automatic → MusicBrainz**: **Further tries when the server is busy** (default 6) and **Pause before the first further try** (default 5 s). The pause grows by its value with every try and never exceeds 60 s. The progress window shows the current try.
