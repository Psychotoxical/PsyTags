# MusicBrainz und Discogs

Von hier kommen Titel, Album, Künstler, Jahr, Label und Katalognummer.

## Automatisch

**MusicBrainz automatisch** (Strg+Shift+B) taggt das markierte Album, wenn es sicher erkannt wird. Sonst öffnet sich die Trefferliste. **Alle Alben automatisch** (Strg+Alt+B) macht das für die ganze Liste ohne Rückfragen.

Ein Release wird nur genommen, wenn:

- jeder Track des Releases seine eigene Datei findet, und zwar über den Titel, unabhängig von der Reihenfolge,
- höchstens drei Dateien übrig bleiben, und höchstens ein Viertel aller Dateien,
- die Längen nicht stark abweichen. Dateien dürfen um einige Sekunden abweichen und bleiben trotzdem derselbe Song.

Gibt es digitale Ausgaben, werden sie bevorzugt. Zusätze wie „(Deluxe Edition)“ im Album-Tag werden bei einer zweiten Suche weggelassen.

Fehlt genau der letzte Track, wird das Release genommen, wenn alles andere exakt passt. Die [Übersicht](help:summary) nennt dann den fehlenden Track. Fehlt ein Track mitten im Album, bleibt es offen.

## Discogs als zweite Quelle

Bleibt ein Album bei MusicBrainz offen, sieht PsyTags bei Discogs nach, wenn ein Token eingetragen ist. Sie bekommen ihn kostenlos unter [discogs.com/settings/developers](https://www.discogs.com/settings/developers) und tragen ihn unter **Optionen → Discogs** ein. Ein grüner Haken zeigt, dass er funktioniert.

Bei Discogs gelten dieselben Regeln, zusätzlich müssen alle Tracklängen bekannt sein. Von dort kommen nur Texte und nie Bilder, denn Cover sind dort meist Fotos von Nutzern. Das Cover holen die übrigen Quellen.

## Von Hand

**MusicBrainz durchsuchen** (Strg+I) oder **Tag-Quellen → Discogs** öffnen das Suchformular. Danach wählen Sie aus der Trefferliste.

Im Fenster **Zuordnung prüfen** stehen links die Tracks der Quelle und rechts Ihre Dateien. Dateien lassen sich per Drag & Drop oder Alt+↑/↓ in die passende Zeile schieben. Gelb markierte Zeilen weichen um mehr als 3 Sekunden ab. Links wählen Sie, welche Felder geschrieben werden.

**MusicBrainz durchsuchen (Schnell)** (Strg+Shift+I) überspringt das Suchformular.

Kommentare werden beim Import gelöscht, solange **Optionen → MusicBrainz → Kommentare standardmäßig löschen** eingeschaltet ist. Beim Jahr wird nur die Jahreszahl geschrieben.
