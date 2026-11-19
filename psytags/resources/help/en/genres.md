# Genres

Genres come from Last.fm. PsyTags asks for the tags of the album first, then for those of the artist if that finds nothing, and only takes entries that really are genres.

PsyTags brings a key for Last.fm, so there is nothing to set up. Since December 2026 Last.fm only gives API keys to Pro accounts. If you have one of your own from [last.fm/api/account/create](https://www.last.fm/api/account/create), enter it under **Options → Accounts and sources → Last.fm**; PsyTags then uses yours. A green check mark shows that it works.

**Fetch genres from Last.fm** (Ctrl+Shift+L) writes the genres of the selected files. In the automatic run this is the last step. If Last.fm finds nothing, the GENRE field stays as it was.

Whatever failed can be retried in the [summary](help:summary).
