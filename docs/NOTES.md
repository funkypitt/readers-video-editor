# Reader's Video Editor — notes

## Where things live

- Settings: `~/.config/readers-video-editor/config.json` (Linux), `%APPDATA%\Readers Video Editor`
  (Windows), `~/Library/Application Support/readers-video-editor` (macOS).
- Projects: `projects/<name>-<id>/` in the data folder (`~/.local/share/readers-video-editor` on
  Linux): `audio16k.wav` (the sound as the transcription hears it), `transcription.json`
  (the tokens, the language), `translation-<lang>.json` (traduire.py's segments with `text_tgt`,
  the translated tokens, the analysis), `cues-<key>.json` (the subtitles of a text once made or
  edited, 1.4.0), `selection.json` (the highlighting, by token ranges of
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
gauge. The passes are those of `traduire.main()`: `analyze_content` (by the model chosen, or by
Claude when the box « Analysis of the content by Claude » is ticked: the toolkit's « auto » rule,
made a visible choice in 1.4.0, off by default), `translate_chunks`, `review_translation` (the « proofreading »
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

## The subtitle editor (1.4.0)

Cues become data once the editor is opened: `cues-<key>.json` in the project folder (`src` or a
language code: `language`, `cues` as `[start, end, text]` on the timeline of the whole file,
`edited`), loaded by `show_tokens`, saved in the project file under `cues`, dropped when the
text they came from is made again (`forget_cues`: a new transcription, new subtitles, a new
translation of that language). `ensure_cues` makes them once with `make_cues` (the toolkit's
`resegment()` through the bridge, `simple_cues` without it) in the background, the patience page
with a Stop; « Re-cut from the text » makes them again, after a question when they were edited.

`CueEditor` sits in the page stack beside the page and the patience page: two rows of buttons,
the hint, a `QTableView` on `CueModel` (Start, End, c/s, Text, and Original for a translation:
the original words whose middle falls inside the cue, `words_during`). Times are typed as
`1:02.345` (`parse_clock`), the text in a `CueTextEditor` (a `QPlainTextEdit` in the cell:
Enter → `split`, Shift+Enter a line break, Tab commits and edits the next row through the
delegate's event filter). Splitting shares the time in proportion to the letters, with 0.05 s
between the halves, and snaps a cut inside a word to the space before it; merging joins the
texts and `two_lines` re-wraps. The history is whole snapshots of the list (200 at most); Ctrl+Z
and the bar's Undo go to the editor while the mode is on (`Main.undo`), to the page otherwise.
`cue_issues` colours a row (bad: a line over 42, three lines, an overlap; warn: over 7 s, under
1 s) and fills its tooltip. The pace has its own colour on the c/s number (`pace_level`): green
up to `CPS_TARGET` 17 (the toolkit's target), amber up to `MAX_CPS` 22 (the app's limit, 17
being harsh as one), red beyond, in bold when not green; `pace_note` adds the reading to the
tooltip. The highlighting tools are
disabled in the mode, the passage list and the output stay live. Reading and Subtitles exclude
each other.

The picture: `QLabel#overlay` over the black screen, placed by `place_overlay` inside the
picture rectangle (the video's aspect fitted in the screen), the letters 24/288 of the picture
height as traduire's style (`FontSize=24` for `PlayResY` 288), smaller for pictures narrower
than 16:9 as `scale_style` does, 16/288 above the bottom. It shows the editor's cues in the
mode, else the cues chosen for the output when they exist (`refresh_overlay`), driven by
`on_position` like the page's current word.

Shortening: `ask_shorten` offers the rows that read too fast, the selected rows or all, and the
model (Ollama here or Claude, the same fields as the translation dialog, `_llm_rows`).
`start_shorten` sends the chosen rows with two neighbours each side for context as segments
(`index` = row, `text` = the original words during the cue, `text_tgt` = the cue's text) to the
bridge task `review`: `review_translation` alone, with the translation's `ContentAnalysis`
(glossary) when there is one, then `_clean_translation_artifacts`; the job carries `max_cps`
(the app's 22), set on the toolkit module for the call, so it marks the segments over that pace
with ⚠️ and its prompt asks to shorten them. Only the chosen rows take the
answer (`apply_texts`, one undo step). The `🔎 Fenêtre i/n` lines move the gauge.

At the output and for « Save the subtitles… », stored cues win over a fresh cutting: whole-file
cues are written as they are; for the edit, `cues_in_edit` trims each cue to the kept pieces and
shifts it, drops what a cut leaves of a cue when it is less than half of it and under a second,
and joins the two halves of a cue around a join when their text is the same.

## The square frame and the improved sound (1.5.0)

Two combos in the production block, « Picture » and « Sound », kept in the config (`frame`,
`sound`) and in the project file's `output`.

**Square (1:1), centred**: each piece gets `crop=2*floor(min(iw,ih)/2):…` before its fades
(`SQUARE_FILTER`): the centre of the picture, the shorter side as the square, even for yuv420p;
`iw`/`ih` are the displayed size, since ffmpeg turns a phone's picture upright before the
filters. The pieces are re-encoded anyway, so the crop costs nothing more. The burn-in style is
scaled for a square picture (`scale_style(…, side, side)`, traduire.py's rule for pictures
narrower than 16:9). The frame combo is greyed when the sound alone is produced.

**Improved: background noise, level**: the edit's sound is handed to the toolkit's `finaliser.py`
(`finish_sound`), run as a subprocess in the toolkit's Python (the rule of the translation:
`TRADUCTION_PYTHON`, the conda env `interview` or `traduction`, else the app's own) with
`--format <fmt> --sans-rognage --forcer --canaux stereo|mono -o <tmp>`: `--sans-rognage` keeps
the length to the sample, so the log, the edit list and the subtitles stay true; the channels
follow the source. To avoid a second lossy generation, the join writes a MOV with the raw
sound (`joined.mov`, no subtitle tracks) when the sound is to be finished, finaliser.py writes
`joined_podcast.mp4` beside it (picture copied: nothing trimmed, no picture fade asked), and a
last copy adds the subtitle tracks and `+faststart`. For MP3/M4A/WAV the pieces go to a raw
`joined.wav` and finaliser.py encodes the format itself (MP3 at a constant bit rate, 128 kbit/s
mono / 192 stereo, 44.1 kHz; AAC 96/160; WAV 16 bits 48 kHz). Its `[k/9]` lines move the gauge
(« Sound: Channels », « Analysis », « Background noise »…), its `✗ échec : …` line is the
error shown. The JSON report (`joined_podcast.json`) becomes `sound_summary()`: translated lines
built from the structured fields (hum at … Hz removed; background noise reduced by … dB at most
/ reduced gently / left as it is: already clean, music, or changing; voice levels evened out;
level … dB → … LUFS, … dB taken from the peaks alone; voice quality before → after by DNSMOS),
shown in the finished panel and written in the log's « Sound » line with finaliser.py's alerts
(in French, verbatim) under it. The decisions are finaliser.py's: nothing is denoised when the
background is already 40 dB under the voice, is music, or changes along the file; otherwise
DeepFilterNet3 at 8 dB (12 when the background is strong) judged by DNSMOS, with a gentle
spectral subtraction or nothing when the voice suffers; levelling only when the loudness range
passes 14 LU.

When the toolkit is not found, or has no `finaliser.py`, « Produce the edit » first opens a
small dialog asking for the toolkit folder (`toolkit_for_sound`, the translation's row with
another message); Cancel leaves the settings as they were. Checked headless 2026-10-29 on
synthetic media (espeak-ng + testsrc2, white noise −42 dB and a 50 Hz hum added): the square
MP4 is 720×720 with the subtitles burnt at the right size and the `mov_text` track kept, the MP3
path works, the hum at 50.2 Hz and the noise are found and the voice level stays flat (gain
difference between the plain edit and the finished one, 0.25 s frames on the voice: p10 −4.7 dB,
p90 −3.0 dB: a constant gain, the rest is the removed hum and noise; the floor drops 9.6 dB).

## Instagram-like captions (1.6.0)

A second combo beside « Subtitles » (`caption_style`: `subtitles` or `captions`, config and
project file). With `captions`, the burnt-in text is not the cues but an ASS file written by
`captions_ass()` from the words of the chosen text on the edit's timeline
(`tokens_in_edit`): `caption_cards()` groups the words into cards of 4 words / 26 characters
at most, cut at a join, a sentence change, a word ending in .!?, or a pause ≥ 0.8 s; one
Dialogue event per spoken word shows its card with that word in the accent colour
(`{\c&H4AE8FF&}` = the stabilo #ffe84a); a card stays 0.5 s after its last word unless the
next card starts sooner. Style: Montserrat ExtraBold (bundled, OFL, `fontsdir=` on the
subtitles filter so the bundles find it without any installation), size 6.5 % of the shorter
side (47 px on 720, 70 px on 1080×1920), outline 8 % and shadow 6 % of the size, alignment 2
(bottom centre) with MarginV 10 % of the height, 24 % on a vertical picture (H > 1.2 W: the
band Reels lay at the bottom), and 8 % side margins, PlayRes = the picture (the square side
when the frame is square). 1.6.2: the 26 % of 1.6.0 on every frame put the cards over a face
framed in the middle of a square video (the user's own test); the classic subtitles sit at
the bottom (MarginV 16 of 288) and were never concerned. No animation, no uppercase, one accent colour.
The classic path is unchanged (`force_style`, now also with `fontsdir`); the `.srt` files
beside the edit stay the cues. The overlay preview in the window still shows the cues, not
the cards. Checked 2026-10-29 on the synthetic media: 16:9 and square frames.

The choices follow the trend guides of 2025-2026 (vendor blogs, consistent with one another):
word-by-word highlight in a heavy sans with one accent colour is the style that holds
attention best on talk videos; white with a black outline; centred in the lower-middle third,
never at the bottom, where Reels put the account name, the caption and the audio ticker
(a dead zone of 310–480 px on 1920); 60–75 px on 1080×1920; two lines at most; rotating
through several colours is the most common mistake. Sources: Blitzcut (best caption style
for Reels 2026; caption size for Reels 2026; caption placement), vfxai (trending caption
styles 2026), vsubtitle (Reels caption best practices), clipspeed (Reels captions, safe zones),
krumzi (captions on Reels 2026).

## Times past the hour (1.6.1)

The margin of the page and the list of passages took `hmsm(t)[3:8]`, which cut the hours off:
at 1:05:05 the margin said 05:05. `stamp()` now gives `MM:SS` under the hour and `H:MM:SS`
past it (the passage list's time column widened from 52 to 64 px). A passage without words of
a minute or more is shown as `34:28` rather than `2067.6 s`. Checked on a 66-minute recording.

## Captions lowered (1.6.2)

See above: the cards sit 10 % above the bottom on a square or landscape picture, 24 % on a
vertical one. Checked on the square test media and on a 720×1280 vertical one.

## Getting started (1.8.0)

A page in the views stack (`_build_setup`, `show_setup`, `leave_setup`), shown at the first
start (`cfg["welcomed"]` = VERSION afterwards) and from « Getting started… » on the home page
or Project ▾. `probe_setup(cfg)` runs in the background (python_has imports torch: seconds)
and `fill_setup()` draws five rows (`_setup_row`: dot, name, detail, a segmented choice, a
field, buttons) under three headings: level 1 editing (ffmpeg; faster-whisper installed by
`install_whisper`, the model fetched by `download_whisper_model`, present when
`models--Systran--faster-whisper-<size>/snapshots/*/model.bin` exists), level 2 optional
(the toolkit by `install_toolkit`; the model by `fill_model_row`: Ollama — `find_ollama`,
`ollama_start` (the Mac app or `ollama serve` detached), `recommended_model` from
`MODEL_LADDER` against the GPU memory, a Mac's unified memory or 70 % of the RAM, `ollama_pull`
through `/api/pull` with the percentage, `ollama_test` through `/api/generate` —, Claude Code —
`find_claude` as Reader's Writer, `install_claude` (the claude.ai script in `bash -lc`),
`open_terminal` (osascript on macOS, the usual terminals on Linux) for the interactive
sign-in, `claude_test` = `claude -p … --tools "" --output-format json` with the API variables
stripped —, or a key — `anthropic_key_test`, one 8-token request), level 3 optional (the sound
libraries and, on macOS, the ffmpeg zips). Optional rows stay grey (`opt`) until their test
turns them green; level 1 rows are orange when something is missing. One background job at a
time (`setup_job`: the row's buttons become a Stop, progress in the row's detail through
`on_progress`, then the probe runs again). « That is enough for me: start editing » sits right
after level 1.

**Claude Code in the bridge**: `_ClaudeCodeClient` in `TOOLKIT_BRIDGE` mimics
`client.messages.create` through `claude -p --output-format json --tools "" --system-prompt …`
(the plan pays, so the API variables are removed from the environment; `job["work"]` =
`<data>/work` as cwd). traduire.py forces a `submit_texts` tool call: the tool's JSON schema is
appended to the prompt as the only allowed answer, the answer is parsed (fences stripped, the
outer braces) into a `tool_use` block, so `_claude_submit_texts` reads it as from the API;
thinking blocks never appear. traduire's retry wrapper imports `anthropic` on an error: a
stand-in module with `APIStatusError` and `APIConnectionError` is put in `sys.modules` when
the real one is absent. `job["llm"] = "claude_code"`, `claude_exe`, `claude_kind` (which Claude
the analysis pass takes when the local model is chosen: Claude Code when the command is there
and no key is set). Checked 2026-10-30: two sentences translated with analysis, consistency
and glossary passes in 21 s on the Max plan.

**No fade from black at the start** (1.8.0, user: the first frame is the thumbnail X shows):
`compute_cuts` sets `vi` only for a piece after a removed second or more; the fade to black at
the very end stays. Checked: first frame mean luma 128, the join at 11.87 s at 7.

## The toolkit installs itself (1.7.0)

Four pieces, so that a macOS (or Linux) user never opens a terminal for the toolkit:

- `install_toolkit()`: the GitHub zip of the toolkit's main branch into `<data>/toolkit` (the
  `.new` folder, then moved into place; members with `..` refused); `toolkit_dir()` looks there
  last. The dialog row (`_toolkit_row`) has « Install it here (download, a few MB) », run in a
  thread while the modal dialog pumps events, then the folder field is filled and remembered.
- `prepare_toolkit_python(packages, progress, task)`: `toolkit_python()` (TRADUCTION_PYTHON,
  conda envs, then `<data>/toolkit-venv`, then `system_python()`: the app's interpreter when not
  frozen, else `python3` on macOS, `py`/`python` on Windows) is kept when `python_has()` imports
  the packages; otherwise the app's venv is made (`python -m venv`, no system site packages)
  and pip installs them (`anthropic` for Claude; `deepfilternet pyloudnorm speechmos` for the
  sound), pip's Collecting/Downloading/Installing lines on the waiting page, cancel kills pip.
  The person's own environments are never written to. Called in `start_translation`,
  `start_shorten` and in the production's `work()` before `finish_sound`; `run_bridge` and
  `finish_sound` take the `python` chosen.
- The Anthropic key: a password field in `_llm_rows` (shown when Claude is chosen), kept in
  `cfg["anthropic_key"]`, passed as `ANTHROPIC_API_KEY` in the subprocess environment
  (`claude_env`); the environment's own variable still works.
- `FINISH_ERRORS`: finaliser.py's known French messages said in the app's words (ffmpeg
  missing, libraries missing, silent file, no picture).
- macOS: the toolkit calls `ffmpeg`/`ffprobe` by name and the bundle has neither on the PATH
  (imageio's binary has another name, no ffprobe). `ensure_ffmpeg_tools()` fetches the Apple
  silicon static zips from https://ffmpeg.martin-riedl.de/ (the page is read for the newest
  `/download/macos/arm64/…/ffmpeg.zip` and `ffprobe.zip`, about 28 MB each) into `<data>/bin`,
  put first on the PATH for finaliser.py; `ffmpeg_exe()`/`ffprobe_exe()` use them too.
  evermeet.cx, the usual source, answers 410 since 2026. The Intel build is gone from the CI:
  the app is built for Apple silicon only.

Checked 2026-10-30 headless on Linux: the toolkit download into a temporary data folder, the
venv + pip path with a small package (`pyloudnorm`) and a Python that lacks it, the
translation dialog with the install row and the key field. Not checked: the whole chain on a
real Mac (venv from the Xcode python3, torch wheels, the ffmpeg zips) — the user has the Mac.

## Project files (1.3.0)

`<stem>.rve.json` beside the video (or wherever asked): `source`, `source_name`, the
`transcription.json` content, the `translation-*.json` contents, the `cues-*.json` contents
(1.4.0), the selection (view, ranges,
mode, fade, picture fade) and the output settings (format, burnt subtitles, srt files). Opening
one (`open_project_file`, by drop, Ctrl+Shift+O, the home field, the command line) installs
those files into the project folder of the source (`install_project`) and opens the source; a
source not found at its path is looked for beside the project file by name. The folder keeps
autosaving as before; the file changes only on Save. Several files for one video = several clips.
