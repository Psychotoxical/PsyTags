# Fehlersuche

Warum einzelne Alben offen bleiben, steht unter [Die Übersicht](help:summary).

## Ablauf

| Problem | Was hilft |
|---|---|
| Etwas sieht nach dem Lauf falsch aus | **Rückgängig** (Strg+Z), solange das Programm läuft. Arbeiten Sie zuerst an [Kopien](help:start). |
| Der Lauf ist langsam | MusicBrainz erlaubt nur eine Anfrage pro Sekunde, die Mood-Analyse hört jeden Song an. Bei vielen Alben dauert das. |
| „Alle Alben dieser Liste sind schon erledigt“ | Erledigte Alben laufen in dieser Sitzung nicht noch einmal. Laden Sie den Ordner neu oder arbeiten Sie einzelne Schritte von Hand ab. |
| Die Übersicht ist leer | Sie zeigt den letzten automatischen Lauf dieser Sitzung. Nach einem Neustart gibt es noch keinen. |

## Dateien

| Problem | Was hilft |
|---|---|
| Schreibfehler | Die Datei ist schreibgeschützt oder von einem Player geöffnet. Schließen Sie den Player und versuchen Sie es erneut. |
| Eine Datei lässt sich nicht lesen oder taggen | Sie ist wahrscheinlich beschädigt. Prüfen Sie, ob sie sich abspielen lässt. |
| Songs fehlen im Album | Das kann PsyTags nicht ergänzen. Das Album bleibt offen, außer es fehlt nur der letzte Track. |
| Nach dem Umbenennen fehlen Bilder oder Cue-Dateien | Sie liegen im Papierkorb, wenn das Aufräumen alter Ordner eingeschaltet war. |

## Moods

| Problem | Was hilft |
|---|---|
| ffmpeg wird nicht gefunden | Installieren Sie ffmpeg und legen Sie es in den PATH. Starten Sie PsyTags danach neu. |
| Die Modelle laden nicht | Internetverbindung prüfen und den **Einrichtungs-Assistenten** im Menü ≡ erneut öffnen. |
| Die Moods wirken falsch | Unter **Optionen → Moods** eine andere Menge wählen und neu analysieren. |

## Dienste

| Problem | Was hilft |
|---|---|
| Rotes Kreuz hinter einem Schlüssel | Schlüssel prüfen, auch auf Leerzeichen. Tritt es plötzlich auf, ist vielleicht nur der Dienst nicht erreichbar. |
| „Discogs lehnt den Token ab“ | Unter discogs.com/settings/developers einen neuen Token erzeugen und unter **Optionen → Discogs** eintragen. |
| Discogs steht ausgegraut im Menü | Es ist noch kein Token eingetragen. |
| MusicBrainz ist ausgelastet | PsyTags versucht es selbst noch einmal. Bleibt es dabei, später erneut starten. |
| Kein Cover | Das Cover Art Archive braucht eine MusicBrainz-ID. Fügen Sie weitere Quellen mit [Cover-Plugins](help:plugins) hinzu. |
| Cover zu klein | Die [Mindestgröße](help:covers) senken oder eine andere Quelle verwenden. |
| Keine Genres | Last.fm kennt das Album nicht, oder der API-Key fehlt. |
