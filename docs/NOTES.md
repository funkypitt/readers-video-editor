# Reader's Video Editor — notes

## Where things live

- Settings: `~/.config/readers-video-editor/config.json` (Linux), `%APPDATA%\Readers Video Editor`
  (Windows), `~/Library/Application Support/readers-video-editor` (macOS).
- Projects: `projects/<name>-<id>/` in the data folder (`~/.local/share/readers-video-editor` on
  Linux): `audio16k.wav` (the sound as the transcription hears it), `transcription.json`
  (the tokens), `selection.json` (the highlighting, by token ranges; by times when the text is
  made again), `project.json`. The id is a hash of the path, size and date of the source.
- Models of faster-whisper: `models/` in the same data folder (tiny 75 MB … large-v3 3 GB).

## Tokens

`[text, start, end, sentence]`; `text` is `None` for a passage without words. A gap of 2 s or
more between two words becomes such a token; at the very start and end of the file, 0.3 s is
enough (microphone noises). From a transcription the word timings come from faster-whisper
(`word_timestamps=True`). From subtitles, the words of each cue are spread over the moments
the voice actually speaks inside the cue (energy 30 dB under the loud parts, pauses ≥ 0.15 s),
each word by its length, the ends of sentences on the voice's pauses; those positions are
*estimated*, so the quiet point is searched 0.25 s on both sides of a boundary.

## Cuts

For each kept range the start is moved back and the end forward into the quietest instant
within the margins (before: 0.6 × fade, 0.15–0.5 s; after: 0.8 × fade, 0.25–0.6 s), never past
the neighbouring word (0.04 s of overrun when keeping, none when cutting). Two kept ranges whose
margins overlap are joined by one cut in the middle of what is removed. Fades: sound in and out
per piece (`afade`, hsin, shortened when the cut is tight, 0.01 s at least); picture fade to
black only where ≥ 1 s is removed. MP4: one x264 intermediate per piece (crf 18, pcm sound),
then a concat with the picture copied and the sound encoded once (AAC 192k). MP3/M4A/WAV: the
sound is decoded once from start to end and the pieces are taken on the fly, to the sample,
with raised-cosine fades.

## Reading

Paragraphs follow the rule of the Reader's apps: a new paragraph on a pause ≥ 2 s, on a pause
≥ 0.9 s after a sentence end, or after 900 characters at a sentence end with ≥ 0.25 s of pause.
The saved text has those paragraphs and no timings.

## Player

QtMultimedia: GStreamer on Linux (`gstreamer1.0-plugins-good` + `gstreamer1.0-libav` for H.264
and AAC), Media Foundation on Windows, AVFoundation on macOS. When a file cannot be played, the
page and the export still work.
