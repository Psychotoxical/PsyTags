# Cover-Plugins

PsyTags lädt Cover aus dem Cover Art Archive. Weitere Quellen fügen Sie mit einem Cover-Plugin hinzu: einer kleinen Textdatei, die beschreibt, wo ein Dienst seine Cover hat. Ein Plugin enthält keinen Programmcode, und installiert werden muss auch nichts.

| Probieren Sie ein neues Plugin zuerst an Kopien einiger Alben aus. Ein falsches Cover landet direkt in Ihren Dateien. |
|---|

## Ein Plugin einrichten

1. **Optionen → Konten und Quellen → Plugin-Ordner öffnen** aufrufen.
2. Die `.json`-Datei in diesen Ordner kopieren.
3. **Optionen** schließen und neu öffnen. Die neue Quelle steht jetzt unter **Automatik → Cover**.
4. Die Quellen in die gewünschte Reihenfolge ziehen. Von oben nach unten gilt: Die erste Quelle, die ein Cover liefert, gewinnt.

Der Ordner ist unter Windows `%LOCALAPPDATA%\psytags\cover-provider` und unter Linux `~/.config/psytags/cover-provider`. Um ein Plugin zu entfernen, löschen Sie seine Datei. Pausieren können Sie es unter **Optionen → Automatik → Cover**.

PsyTags liefert kein Plugin für einen Dienst mit unklaren Nutzungsbedingungen mit. Für die Plugins, die Sie hinzufügen, sind Sie selbst verantwortlich: Prüfen Sie, ob der Dienst das erlaubt.

## Das erste eigene Plugin

Sie brauchen einen Dienst, den man über eine Web-Adresse durchsuchen kann und der mit JSON antwortet. Dieses Beispiel benutzt einen erfundenen Dienst unter `api.example.com`.

**Schritt 1: Die Suchadresse finden.** Sehen Sie in der Dokumentation des Dienstes nach und probieren Sie die Adresse mit einem echten Künstler und Album im Browser aus:

```
https://api.example.com/search/album?q=Example%20Band%20Example%20Album
```

**Schritt 2: Die Antwort ansehen.** Suchen Sie die Liste der Treffer und darin bei einem Treffer den Titel, den Künstler und die Adresse des Bildes:

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

**Schritt 3: Beschreiben.** Legen Sie eine Textdatei mit der Endung `.json` an, gespeichert als UTF-8:

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

Zeile für Zeile:

- `search_url` ist die Adresse aus Schritt 1, mit `{artist}` und `{album}` an der Stelle der echten Namen.
- `results` sagt, dass die Treffer die Einträge der Liste `data` sind.
- `album`, `artist`, `tracks`, `image` und `page` sind Pfade von einem Treffer zu seinen Werten.
- `only_if` überspringt alles, was kein Album ist, etwa Singles.
- `image_replace` fragt nach einem größeren Bild als dem aus der Antwort. Dieser Dienst hat die Größe in der Adresse. Bei anderen fehlt sie, dann lassen Sie das Feld weg.

**Schritt 4: Ausprobieren.** Richten Sie die Datei wie oben beschrieben ein. Markieren Sie ein Album Ihrer Kopien, öffnen Sie das Kontextmenü des Covers und wählen Sie **Cover von Example Covers laden**. Klappt etwas nicht, hilft „Wenn es nicht klappt“ weiter unten.

## Felder

Pflicht:

| Feld | Bedeutung |
|---|---|
| `format` | Version dieses Formats, derzeit `1`. |
| `name` | Name im Programm. Muss eindeutig sein. |
| `search_url` | Suchadresse, `http` oder `https`, mit `{artist}` und/oder `{album}`. Beide werden für Adressen kodiert. Braucht der Dienst einen Schlüssel, gehört er in diese Adresse. |
| `results` | Pfad zu den Treffern in der Antwort, siehe „Pfade“. |
| `album` | Pfad von einem Treffer zum Albumtitel. |
| `artist` | Pfad von einem Treffer zum Künstler. |
| `image` | Pfad von einem Treffer zur Adresse des Bildes. |

Optional:

| Feld | Bedeutung |
|---|---|
| `tracks` | Pfad von einem Treffer zur Anzahl der Tracks. Hilft, Editionen zu unterscheiden. |
| `page` | Pfad von einem Treffer zu einer Webseite, die der Knopf Vorschau öffnet. |
| `only_if` | Nur Treffer mit diesen Werten zählen, als `{ "pfad": "wert" }`. |
| `embedded_json` | Für Webseiten: ein regulärer Ausdruck, dessen einzige Gruppe das JSON in der Seite ist. |
| `browser_agent` | `true` meldet sich als Webbrowser statt als PsyTags. |
| `min_interval` | Sekunden zwischen zwei Anfragen an diese Quelle. Vorgabe `1.0`. Halten Sie den Wert so hoch, wie der Dienst es verlangt. |
| `image_replace` | Liste von `[Muster, Ersatz]` als reguläre Ausdrücke für die Bildadresse, etwa für eine größere Variante. |
| `preview_replace` | Dasselbe für die Vorschau in der Trefferliste. Ohne dieses Feld wird die Bildadresse benutzt. |

Ein Feld, das hier nicht steht, wird abgelehnt. So bleibt kein Tippfehler unbemerkt.

## Pfade

Ein Pfad ist eine Folge von Schritten, getrennt durch Punkte:

- ein Name wählt ein Feld eines Objekts: `artist.name`
- eine Zahl wählt einen Eintrag einer Liste, beginnend bei 0: `artists.0.name`
- `*` wählt alle Einträge einer Liste: `data.*`, auch mehrfach: `pages.*.items.*`

Ein Treffer ohne Titel oder Bild wird übersprungen, und dasselbe Bild zählt nur einmal.

## Dienste ohne JSON

Manche Webseiten tragen ihre Daten als JSON im HTML. `embedded_json` schneidet es heraus. Der reguläre Ausdruck braucht genau eine Gruppe in runden Klammern, und `.` passt auch auf Zeilenumbrüche:

```
"embedded_json": "<script id=\"data\">(.*?)</script>"
```

Die Pfade beginnen dann bei dem herausgeschnittenen JSON. Eine Seite ganz ohne JSON lässt sich nicht verwenden.

## Wie ein Cover ausgewählt wird

Treffer werden nach Albumtitel, Künstler und Trackzahl bewertet. Sicher ist ein Treffer, wenn der Titel gleich ist, abgesehen von Zusätzen wie „(Deluxe Edition)“, und auch der Künstler stimmt.

| Wo | Was passiert |
|---|---|
| Automatischer Lauf | Nur ein sicherer Treffer wird genommen, damit kein falsches Cover in Ihren Dateien landet. |
| **Nachholen** in der [Übersicht](help:summary) | Sie wählen aus der Liste, wenn kein Treffer sicher ist. |
| **Cover von … laden** im Kontextmenü des Covers | Sie wählen aus der Liste, wenn kein Treffer sicher ist. |

Die Cover-Mindestgröße gilt für jede Quelle.

## Wenn es nicht klappt

Eine fehlerhafte Datei wird abgelehnt und unter **Optionen → Konten und Quellen → Cover-Plugins** rot aufgeführt. Die übrigen Quellen stört das nicht. Diese Meldungen beginnen mit dem Dateinamen:

| Meldung | Was zu tun ist |
|---|---|
| keine gültige JSON-Datei | Meist ein Komma zu viel oder zu wenig oder ein fehlendes Anführungszeichen. Ein JSON-Prüfer im Web nennt die Zeile. |
| format muss 1 sein | `"format": 1` ergänzen. |
| unbekanntes Feld … | Schreibweise mit „Felder“ vergleichen. |
| Feld … fehlt | Das Feld ergänzen. Es braucht einen Wert. |
| name … ist schon vergeben | Dem Plugin einen anderen `name` geben. `Cover Art Archive` ist reserviert. |
| search_url braucht http(s) und {album} oder {artist} | Die Adresse muss mit `http` beginnen und mindestens einen Platzhalter enthalten. |
| embedded_json braucht genau eine Klammer-Gruppe | Genau ein Paar runder Klammern um das JSON setzen. |
| muss eine Liste aus Paaren [Muster, Ersatz] sein | `[["alt", "neu"]]` schreiben, mit zwei Paar eckigen Klammern. |
| Muster in … ist ungültig | Der reguläre Ausdruck enthält einen Fehler, oft eine nicht maskierte Klammer. |
| min_interval muss eine Zahl ab 0 sein | Eine Zahl ohne Anführungszeichen schreiben. |
| only_if muss ein Objekt sein | `{ "pfad": "wert" }` schreiben. |

Im Betrieb steht der Grund in der Übersicht des Laufs:

| Meldung | Wahrscheinliche Ursache |
|---|---|
| Kein Cover bei … gefunden | Der Dienst hat nichts gefunden, oder ein Pfad stimmt nicht. Vergleichen Sie `results`, `album` und `image` mit der Antwort aus Schritt 2. |
| Kein sicherer Treffer bei … | Die Treffer weichen von Ihren Tags ab. Passiert das bei jedem Album, prüfen Sie den Pfad `artist`: Ohne Künstler kann kein Treffer sicher sein. |
| … Antwort nicht lesbar | Der Dienst hat nicht mit JSON geantwortet, oder `embedded_json` findet nichts in der Seite. |
| HTTP 401 oder 403 | Der Dienst will einen Schlüssel oder lehnt die Anfrage ab. Sehen Sie in seiner Dokumentation nach. |
| HTTP 429 | Zu viele Anfragen. `min_interval` erhöhen. |
| Cover von … zu klein | Das Bild liegt unter der Mindestgröße. Suchen Sie mit `image_replace` eine größere Variante. |

Das Plugin fehlt unter **Optionen → Automatik → Cover**? Die Datei muss auf `.json` enden und direkt im Plugin-Ordner liegen, und **Optionen** muss nach dem Kopieren neu geöffnet werden.
