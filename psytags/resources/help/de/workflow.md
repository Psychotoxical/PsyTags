# So läuft es ab

Der übliche Weg besteht aus vier Handgriffen:

1. **Ordner öffnen** (Strg+D) und die Alben laden. Mit **Ordner hinzufügen** (Strg+H) kommen weitere dazu.
2. **Alle Alben automatisch** (Strg+Alt+B) drücken.
3. In der [Übersicht](help:summary) nachsehen, was offen geblieben ist, und es dort erledigen.
4. Alles markieren (Strg+A) und mit **Umbenennen** (Alt+1) Dateien und Ordner benennen.

## Was der automatische Lauf macht

Für jedes Album der Liste, in dieser Reihenfolge:

| Schritt | Was passiert |
|---|---|
| [Moods](help:moods) | Jeder Song wird aus dem Audio analysiert. |
| [MusicBrainz](help:sources) | Das passende Release wird gesucht und die Tags werden geschrieben. Bleibt es offen und ist ein Token eingetragen, wird Discogs gefragt. |
| [Nummern](help:numbers) | Track- und Discnummern werden geschrieben. |
| [Cover](help:covers) | Die Cover-Quellen werden der Reihe nach gefragt. |
| [Genres](help:genres) | Last.fm liefert die Genres. |

Ein Album wird nur getaggt, wenn es eindeutig passt. Sonst bleibt es unverändert und steht in der Übersicht als offen, nur die Moods sind dann schon geschrieben. Lieber offen als falsch.

Während des Laufs kann das Fenster im Hintergrund bleiben. Ein Lauf lässt sich abbrechen, was bis dahin fertig ist, bleibt erhalten.

## Einzelne Schritte

Jeder Schritt lässt sich auch allein für die markierten Dateien ausführen, über die Leiste oben oder die [Tastaturkürzel](help:shortcuts).

In der Dateiliste zeigt jede Album-Zeile rechts den Stand von Album, Cover, Genres und Moods.
