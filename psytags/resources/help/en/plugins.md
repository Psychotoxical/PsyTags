# Cover plugins

PsyTags loads covers from the Cover Art Archive. You can add more sources with a cover plugin: one small text file that describes where a service keeps its covers. A plugin contains no program code and nothing needs to be installed.

| Try a new plugin on copies of a few albums first. A cover that is wrong goes straight into your files. |
|---|

## Installing a plugin

1. Open **Options → Accounts and sources → Open plugin folder**.
2. Copy the `.json` file into that folder.
3. Close and reopen **Options**. The new source now appears under **Automatic → Cover**.
4. Drag the sources into the order you want. From top to bottom, the first source that delivers a cover wins.

The folder is `%LOCALAPPDATA%\psytags\cover-provider` on Windows `~/.config/psytags/cover-provider` on Linux and `~/Library/Preferences/psytags/cover-provider` on macOS. To remove a plugin, delete its file. To pause it, switch it off under **Options → Automatic → Cover**.

PsyTags ships no plugin for a service with unclear terms of use. You are responsible for the plugins you add: check whether the service allows what you are doing.

## Writing your first plugin

You need a service that can be searched through a web address and answers with JSON. This example uses a made-up service at `api.example.com`.

**Step 1: Find the search address.** Look in the documentation of the service, then try the address in your browser with a real artist and album:

```
https://api.example.com/search/album?q=Example%20Band%20Example%20Album
```

**Step 2: Look at the answer.** Find the list of hits, and inside one hit the title, the artist and the address of the picture:

```json
{
  "data": [
    {
      "title": "Example Album",
      "record_type": "album",
      "nb_tracks": 10,
      "link": "https://www.example.com/album/1",
      "cover_url": "https://img.example.com/1/250x250.jpg",
      "artist": { "name": "Example Band" }
    }
  ]
}
```

**Step 3: Describe it.** Create a text file with the ending `.json`, saved as UTF-8:

```json
{
  "format": 1,
  "name": "Example Covers",
  "search_url": "https://api.example.com/search/album?q={artist}%20{album}",
  "min_interval": 1.0,
  "results": "data.*",
  "only_if": { "record_type": "album" },
  "album": "title",
  "artist": "artist.name",
  "tracks": "nb_tracks",
  "image": "cover_url",
  "page": "link",
  "image_replace": [["/250x250", "/1400x1400"]],
  "preview_replace": [["/250x250", "/500x500"]]
}
```

Line by line:

- `search_url` is the address from step 1, with `{artist}` and `{album}` in place of the real names.
- `results` says that the hits are the elements of the list `data`.
- `album`, `artist`, `tracks`, `image` and `page` are paths from one hit to its values.
- `only_if` skips everything that is not an album, such as singles.
- `image_replace` asks for a larger picture than the one in the answer. This service has the size in the address, others don't, and then you leave it out.

**Step 4: Try it.** Install the file as described above. Select an album on your copies, open the context menu of the cover and choose **Load cover from Example Covers**. If something goes wrong, see "When it does not work" below.

## Fields

Required:

| Field | Meaning |
|---|---|
| `format` | Version of this format, currently `1`. |
| `name` | Name shown in the program. Must be unique. |
| `search_url` | Search address, `http` or `https`, with `{artist}` and/or `{album}`. Both are URL-encoded. If the service needs a key, put it into this address. |
| `results` | Path to the hits in the answer, see "Paths". |
| `album` | Path from one hit to the album title. |
| `artist` | Path from one hit to the artist. |
| `image` | Path from one hit to the address of the picture. |

Optional:

| Field | Meaning |
|---|---|
| `tracks` | Path from one hit to the number of tracks. Helps to tell editions apart. |
| `page` | Path from one hit to a web page, opened by the Preview button. |
| `only_if` | Only hits with these values count, as `{ "path": "value" }`. |
| `embedded_json` | For web pages: a regular expression whose one group is the JSON inside the page. |
| `browser_agent` | `true` sends the identity of a web browser instead of PsyTags. |
| `min_interval` | Seconds between two requests to this source. Default `1.0`. Keep it as high as the service asks for. |
| `image_replace` | List of `[pattern, replacement]` regular expressions for the picture address, e.g. for a larger size. |
| `preview_replace` | The same for the preview in the result list. Without it the picture address is used. |

A field that is not listed here is refused, so a typing mistake does not go unnoticed.

## Paths

A path is a list of steps separated by dots:

- a name selects a field of an object: `artist.name`
- a number selects one element of a list, starting at 0: `artists.0.name`
- `*` selects every element of a list: `data.*`, also several times: `pages.*.items.*`

A hit without a title or a picture is skipped, and the same picture counts only once.

## Services without JSON

Some web pages carry their data as JSON inside the HTML. `embedded_json` cuts it out. The regular expression needs exactly one group in round brackets, and `.` also matches line breaks:

```
"embedded_json": "<script id=\"data\">(.*?)</script>"
```

Paths then start at the JSON that was cut out. A page without any JSON cannot be used.

## How a cover is chosen

Hits are rated by album title, artist and number of tracks. A match is certain when the title is the same, apart from notes like "(Deluxe Edition)", and the artist agrees as well.

| Where | What happens |
|---|---|
| Automatic run | Only a certain match is taken, so a wrong cover does not end up in your files. |
| **Retry** in the [summary](help:summary) | You pick from the list when no match is certain. |
| **Load cover from …** in the context menu of the cover | You pick from the list when no match is certain. |

The minimum cover size applies to every source.

## When it does not work

A file with a mistake is refused and listed in red under **Options → Accounts and sources → Cover plugins**. It does not disturb the other sources. These messages start with the file name:

| Message | What to do |
|---|---|
| not a valid JSON file | Usually a comma too many or too few, or a missing quote. A JSON checker on the web names the line. |
| format must be 1 | Add `"format": 1`. |
| unknown field … | Check the spelling against "Fields". |
| field … is missing | Add the field. It needs a value. |
| the name … is already taken | Give the plugin another `name`. `Cover Art Archive` is reserved. |
| search_url needs http(s) and {album} or {artist} | The address must start with `http` and contain at least one placeholder. |
| embedded_json needs exactly one group in brackets | Use exactly one pair of round brackets around the JSON. |
| must be a list of pairs [pattern, replacement] | Write `[["old", "new"]]`, with two pairs of square brackets. |
| pattern in … is invalid | The regular expression has a mistake, often an unescaped bracket. |
| min_interval must be a number from 0 | Write a number without quotes. |
| only_if must be an object | Write `{ "path": "value" }`. |

During use, the reason appears in the summary of the run:

| Message | Likely cause |
|---|---|
| No cover found at … | The service found nothing, or a path is wrong. Compare `results`, `album` and `image` with the answer from step 2. |
| No certain match at … | The hits differ from your tags. If this happens for every album, check the `artist` path: without an artist no match can be certain. |
| … the answer cannot be read | The service did not answer with JSON, or `embedded_json` finds nothing in the page. |
| HTTP 401 or 403 | The service wants a key or refuses the request. Check its documentation. |
| HTTP 429 | Too many requests. Raise `min_interval`. |
| Cover from … too small | The picture is below the minimum cover size. Look for a larger size with `image_replace`. |

Is the plugin missing from **Options → Automatic → Cover**? The file must end in `.json` and lie directly in the plugin folder, and **Options** must be opened again after copying it.
