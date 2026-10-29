# Reader's Video Editor — notes

## Where things live

- Settings: `~/.config/readers-video-editor/config.json` (Linux), `%APPDATA%\Readers Video Editor`
  (Windows), `~/Library/Application Support/readers-video-editor` (macOS).
- Projects: `projects/<name>-<id>/` in the data folder (`~/.local/share/readers-video-editor` on
  Linux): `audio16k.wav` (the sound as the transcription hears it), `transcription.json`
  (the tokens, the language), `translation-<lang>.json` (traduire.py's segments with `text_tgt`,
  the translated tokens, the analysis), `selection.json` (the highlighting, by token ranges of
  the `view` shown; by times when the text changes), `project.json`, and the toolkit's job files
  while it runs. The id is a hash of the path, size and date of the source.
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

## Addresses (yt-dlp)

`download_media` runs the standalone yt-dlp as a subprocess: `--no-playlist`, MP4 up to 1080p
(`bv*[height<=1080][ext=mp4]+ba[ext=m4a]/…`), `--write-subs --sub-langs all` converted to SRT,
`--write-info-json`, everything into a `.part-<hex>` folder inside the Videos folder of the app.
Afterwards the biggest media file is moved up under the video's title; the SRT kept is the one
whose language is the language chosen in the window, or the language the site declares for the
video when the window says « auto » (no guess: a French video with only English subtitles is
transcribed instead). The info json and the other subtitle files are dropped. Progress comes
from the `[download]  12.3%` lines (`--newline`); an `ERROR:` line becomes the message.

The binary is the app's own copy in `<data>/bin` (`yt-dlp_linux`, `yt-dlp_linux_aarch64`,
`yt-dlp.exe`, `yt-dlp_macos` from the latest GitHub release, fetched with urllib on first use),
and `yt-dlp -U` runs on it at most once a day (`yt-dlp-checked.json`), quietly; without network
the download simply proceeds with the copy at hand. A system `yt-dlp` is used only when the app's
copy was never fetched. Since yt-dlp 2025.11 a JavaScript runtime (Deno) is recommended for
YouTube; checked 2026-10-28 with 2026.10.26: no warning and the full format list (1080p) without
any runtime, so none is managed. If YouTube downloads start to fail with a runtime warning, the
next step is to fetch Deno the same way and pass `--js-runtimes deno:<path>`.

## The look (1.2.0)

The window follows the original stabilo page of monter.py (traduction toolkit) rather than the
Reader's white-on-black register: dark chrome (#14161a, panels #1c1f26, orange #ff8a3d for the
one strong action), a paper page (#f6f2e8, Literata bundled as in Reader's Books, 150 % line height since its line
boxes are tall; the system serifs only if the font files are missing) with the times in a column of
their own (a hanging indent: block left margin = GUTTER, text indent = −GUTTER, one tab stop),
yellow highlighter (#ffe84a), pink strike-through (#ffc9c2, ink #8f3a31) in the cut mode, a grey
eraser preview, an orange underline under the word being spoken. Home page = title, lead, file
or address field + Browse, spoken language + model + Open, the projects to resume (project.json
of each project folder, newest first, absent files dimmed). Workshop = bar (name, « I highlight
[what I keep | what I cut] », [Highlighter | Eraser], Undo, Redo, Read, Text ▾, Another file),
side column 400 px (picture, controls, the edit's length + passages with × to drop one, the
production block: Produce / Fade at each cut / fade to black / the orange button; while running
a gauge + Stop; afterwards « Edit finished · length · size », the path, Watch / Open the folder
/ Close), and the page. While the text is made, the page shows a waiting view (message, gauge,
detail); on failure, the language and model combos and « Start the transcription again » /
« Open subtitles… » take its place. The edit is produced beside the original without asking a
name (`<stem>_edit.<ext>`, numbered when taken), as the original page did.

## faster-whisper installed by the app (1.2.0)

`install_whisper`: `python3 -m venv --system-site-packages <data>/venv`, then
`pip install faster-whisper` there (pip's Collecting/Downloading/Installing lines in the waiting
view), then the venv's site-packages is appended to `sys.path` and the import tried again
(`whisper_available`). Needs `python3-venv` + `python3-pip` on Debian (Depends), `python-pip`
on Arch. The Windows/macOS builds (frozen) carry faster-whisper and never install anything.

The first paragraph must get the block format explicitly (`cur.setBlockFormat` after `clear()`): a
document's first block is never inserted with `insertBlock`, so it kept the default format (no
gutter, no line height) — seen on a real screenshot 2026-10-28. faster-whisper splits French
elisions into two words (« d » + « 'autres », « l' » + « usage », « Est » + « -ce »); `transcribe`
glues a word starting with an apostrophe or a hyphen, or following a word ending with an
apostrophe, to its neighbour (end time of the pair), so no cut ever lands inside « n'y ».

## Translation and subtitles (1.3.0)

Nothing of the translation is written here: `traduire.py` of the traduction toolkit does it.
The app finds the toolkit as its launcher does (`TRADUCTION_DIR`, `toolkit_dir` in the config,
`~/code/traduction`, `~/code/traduction-toolkit`), takes its Python by the rule of `gui.py` and
`monter.py` (`TRADUCTION_PYTHON`, the conda env `interview` or `traduction`, else the app's own:
`traduire.py` imports only the standard library, `anthropic` when Claude is asked), writes
`TOOLKIT_BRIDGE` as `toolkit_bridge.py` in the project folder and runs it on `toolkit_job.json`.
The bridge moves the toolkit's prints to stderr and answers on stdout with `@@ {json}` lines
(`step`, `result`, `error`); the app reads the merged stream, the `📦 Chunk i/n` lines move the
gauge. The passes are those of `traduire.main()`: `analyze_content` (by Claude when a key is
there, the toolkit's « auto »), `translate_chunks`, `review_translation` (the « proofreading »
box), `check_consistency`, `verify_glossary`, `_clean_translation_artifacts`,
`_clear_same_lang_translations`. Segments are the tokens grouped by sentence index
(`segments_from_tokens`: faster-whisper's segments, or one per cue from subtitles), with the
word timings as `words`.

The translated page (`tokens_from_translation`) is monter.py's reuse of a translation: the words
of each segment's `text_tgt` are spread over the moments its original words are spoken
(`spread_words`: a share of the time by length, sentence ends on the pauses ≥ 0.25 s), so their
positions are *estimated* and the cuts search the quiet point on both sides, as for subtitles.
Switching views (`show_view`) keeps the highlighting in seconds (`times` in `selection.json`) and
maps it back by token midpoints (`ranges_from_times`), monter.py's `/api/retranscrire` rule.

Subtitles: `make_cues` asks the bridge for `resegment()` (the toolkit's re-segmentation, task
`subtitles`, `text_tgt` = the text wanted) and falls back on `simple_cues` (sentence end + pause,
2 s, two lines of 42, 7 s) without the toolkit. For the edit, the tokens are first moved onto the
edit's timeline (`tokens_in_edit`: those inside a kept piece, shifted; a wordless token marks a
join so no cue straddles it), then cut into cues; the files are `<edit>.<lang>.srt`
(`src` when the original's language is unknown). Burning happens at the join of `produce_video`
(`subtitles=` filter with `SUBTITLE_STYLE`, traduire.py's default style scaled for pictures
narrower than 16:9 as `_scale_style_for_video` does, picture encoded once more, x264 crf 18); the
srt files also go into the MP4 as `mov_text` tracks with their ISO 639-2 language.

## Project files (1.3.0)

`<stem>.rve.json` beside the video (or wherever asked): `source`, `source_name`, the
`transcription.json` content, the `translation-*.json` contents, the selection (view, ranges,
mode, fade, picture fade) and the output settings (format, burnt subtitles, srt files). Opening
one (`open_project_file`, by drop, Ctrl+Shift+O, the home field, the command line) installs
those files into the project folder of the source (`install_project`) and opens the source; a
source not found at its path is looked for beside the project file by name. The folder keeps
autosaving as before; the file changes only on Save. Several files for one video = several clips.
