# Moods

PsyTags hört sich jeden Song selbst an und schreibt daraus Stimmungen in das Feld MOOD. Das passiert lokal auf Ihrem Rechner, es werden keine Audiodaten verschickt.

Dafür braucht es zwei Modelle (20 MB, sie werden beim ersten Mal geladen oder im Einrichtungs-Assistenten) und das Programm **ffmpeg**. Unter Windows bringt PsyTags es mit, unter Linux installieren Sie es über die Paketverwaltung.

## So starten Sie es

| Befehl | Taste |
|---|---|
| Moods der Auswahl analysieren | Strg+Shift+M |
| Moods aller Dateien analysieren | Strg+Alt+M |

Beim automatischen Lauf ist die Analyse der erste Schritt.

## Wie viele Moods

Unter **Optionen → Moods** wählen Sie **Wenige**, **Normal** oder **Viele**. Das gilt für neue Analysen. Vorhandene Moods ändern sich erst, wenn die Songs neu analysiert werden.

Eine Analyse ersetzt das Feld MOOD. Kein späterer Schritt überschreibt das Ergebnis wieder, auch nicht die Tag-Quellen.

Das Modell ist nicht unfehlbar. Es erkennt Stimmungen im Klang und kennt keine Texte. Moods lassen sich jederzeit im Tag-Panel ändern.
