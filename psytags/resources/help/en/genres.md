# Genres

Genres come from Last.fm. PsyTags asks for the tags of the album first, then for those of the artist if that finds nothing, and only takes entries that really are genres.

You need your own free API key from [last.fm/api/account/create](https://www.last.fm/api/account/create). Enter it under **Options → Genres**. A green check mark shows that it works.

**Fetch genres from Last.fm** (Ctrl+Shift+L) writes the genres of the selected files. In the automatic run this is the last step. If Last.fm finds nothing, the GENRE field stays as it was.

Whatever failed can be retried in the [summary](help:summary).
