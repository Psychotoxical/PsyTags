# Moods

PsyTags listens to each song itself and writes moods into the MOOD field. This happens locally on your computer, no audio is sent anywhere.

It needs two models (20 MB, loaded the first time or in the setup assistant) and the program **ffmpeg**. The Windows package and the AppImage bring it along. If you run PsyTags on Linux any other way, install it with your package manager.

## How to start it

| Command | Key |
|---|---|
| Analyze moods of selection | Ctrl+Shift+M |
| Analyze moods of all files | Ctrl+Alt+M |

In the automatic run, the analysis is the first step.

## How many moods

Under **Options → Automatic → Moods** choose **Few**, **Normal** or **Many**. This applies to new analyses. Existing moods only change when the songs are analyzed again.

An analysis replaces the MOOD field. No later step overwrites the result, not even the tag sources.

The model is not infallible. It hears moods in the sound and knows nothing about the lyrics. You can change moods at any time in the Tag Panel.
