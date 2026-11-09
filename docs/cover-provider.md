# Cover providers

PsyTags fetches covers from the Cover Art Archive. Further sources are plain description
files: no code, nothing to install. Put a `*.json` file into the folder `cover-provider` of the
configuration and it counts at once, even while the program is running. **Options → Cover →
Open folder** takes you there.

A file with a mistake is refused with a message that names the file and the problem. It does
not disturb the other sources.

Under **Options → Cover** you switch sources on and off and set their order. From top to
bottom, the first source that delivers a cover wins. The Cover Art Archive starts on top.

PsyTags ships no provider with unclear terms of use. You are responsible for the providers you
add: check whether the service allows what you are doing.

## Example

[`cover-provider-example.json`](cover-provider-example.json):

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

## Fields

Required:

| Field | Meaning |
|---|---|
| `format` | Version of this format, currently `1`. |
| `name` | Name shown in the program. Must be unique. |
| `search_url` | Search address, `http` or `https`, with `{artist}` and/or `{album}`. Both are URL-encoded. |
| `results` | Path to the hits in the answer, see [Paths](#paths). |
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
| `min_interval` | Seconds between two requests to this source. Default `1.0`. |
| `image_replace` | List of `[pattern, replacement]` regular expressions for the picture address, e.g. for a larger size. |
| `preview_replace` | The same for the preview in the result list. Without it the picture address is used. |

## Paths

A path is a list of steps separated by dots:

- a name selects a field of an object: `artist.name`
- a number selects one element of a list, starting at 0: `artists.0.name`
- `*` selects every element of a list: `data.*`, also several times: `pages.*.items.*`

A hit without a title or a picture is skipped, and the same picture counts only once.

## How a cover is chosen

Hits are rated by album title, artist and number of tracks. During an automatic run only a
certain match is taken, so a wrong cover does not end up in your files. With **Retry** in the
result window and with the entry in the context menu of the cover, you pick from the list when no
match is certain. The minimum cover size applies to every source.
