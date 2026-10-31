# Reader's Video Editor

Cut a video or a recording by highlighting its text. The words are transcribed on this
computer (or read from a subtitle file) and shown on a paper page, set in Literata; what you highlight in
yellow is kept, or struck in pink and cut; the cuts land in the quiet between two words, each
piece gets its fades, and ffmpeg writes the new file with a log of the cuts and an edit list.
The same page reads well on its own: a transcript in airy paragraphs that follows the sound, to
read, save or copy. A video can also come from a YouTube or X address. One of the
[Reader's](https://gallaz.ch/apps) apps, with the look of the original stabilo page of the
traduction toolkit: six languages, nothing to install by hand, nothing leaves the computer but
that download.

## Key points

- **Transcription and sound like the toolkit** (1.9.0): no repeated sentences, no word stretched over a pause, the graphics card freed before the sound is improved, exact playback of MP3 files, Claude Code retried when it fails.
- **Getting started** (1.8.0): a page shown at the first start, and again from « Getting
  started… » on the home page or Project ▾ while editing. Three levels, each step checked by a
  real test and fitted with the button that does the work: level 1, the editing (ffmpeg, the
  transcription and its model: nothing to install, « that is enough for me » leads straight to
  the editing); level 2, optional, translation and subtitles (the toolkit downloaded by the app;
  the language model, three ways: Ollama on this computer with the model this machine can carry
  downloaded by the app and tested, **Claude Code** on your own Claude plan with no key —
  installed by the app, signed in once in a terminal, tested —, or an Anthropic API key tested
  against the API); level 3, optional, the improved sound (the libraries, and on a Mac ffmpeg and
  ffprobe, fetched now rather than at the first use). Each choice says what it costs in
  quality and speed (the Whisper model from tiny to large-v3, the local models, Claude).
  Someone who never translates skips levels 2 and 3 entirely.
- **Open** a video or a recording (MP4, MKV, MOV, WebM, MP3, M4A, WAV, FLAC…) from the home
  page, or drop it on the window; the home page lists the files to resume. A `.srt` beside it
  with the same name is read at once; otherwise the words are transcribed here (faster-whisper,
  CPU; the model is downloaded once). On Linux the transcription installs itself on first use
  (about 300 MB, once); the Windows and macOS builds carry it.
- **Address…** (Ctrl+L) takes the address of a video on YouTube, X (Twitter) or any site
  [yt-dlp](https://github.com/yt-dlp/yt-dlp) knows, or a link dropped on the window: the video
  lands in your Videos folder (MP4, 1080p at most) with the site's subtitles in the chosen
  language when it has them, and opens. yt-dlp is fetched on first use (40 MB) and updates
  itself once a day, since the sites change often.
- **Highlight** by dragging over the words. A click on a word plays from there; a double click
  takes the sentence; Shift + click extends from the last word; Alt or the eraser removes. The
  passages without words (music, silence, a dropped bit) are tokens too, marked by one click.
- **Keep or cut**: « I highlight what I keep » makes the edit of the highlighted passages;
  « I highlight what I cut » removes them and keeps all the rest.
- **The cuts** are placed in the quietest instant near each boundary, never on a word; the sound
  fades in and out at each piece (0 to 3 s), the picture fades to black only where a second or
  more is removed, and never at the very start of the edit: its first frame is the thumbnail
  the social networks show. The log (.txt) says what was kept and removed, word for word; the edit list
  (.edl, CMX 3600) reopens the cut in a video editor.
- **Watch the edit** plays it, jumping over what is removed. **Produce the edit** writes MP4
  (picture re-encoded once, x264), or MP3 / M4A / WAV from the sound alone, beside the original,
  then offers to watch it or open its folder.
- **Picture**: as it is, or **square (1:1)**: the centre of the picture, the shorter side as the
  square, for the social networks; the burnt-in subtitles are sized for it.
- **Sound**: as it is, or **improved**: the edit's sound goes through the
  [traduction toolkit](https://github.com/funkypitt/traduction-toolkit)'s `finaliser.py`, which
  removes a mains hum and a steady background noise when it finds some (DeepFilterNet3 at a low
  dose, checked by DNSMOS: if the voice suffers, a gentler cleaning, or none), evens out very
  uneven voice levels, brings the level to the podcast norm by a constant gain and adds short
  fades; the length does not change, so the log, the edit list and the subtitles stay true. The
  finished panel and the log say what was done.
- **Read**: the page alone across the window, about seventy characters a line, the word being
  spoken underlined, −5 s / +10 s, speed 0.8 to 2×. **Save the text…** writes the transcript as
  paragraphs; Ctrl+Shift+C copies it.
- **Translate…** (Ctrl+T) hands the text to the
  [traduction toolkit](https://github.com/funkypitt/traduction-toolkit)'s `traduire.py`: analysis
  of the content (names, glossary), translation by chunks, proofreading, consistency and glossary
  checks, by a local model (Ollama, `gemma4:31b`), by Claude Code on your own plan (the `claude`
  command, no key: the toolkit's forced tool call becomes a JSON answer the app parses) or by
  Claude through an API key; every pass
  goes to the model you chose, and the waiting page names it at each step (a box can hand the
  analysis alone to Claude, as the toolkit does by default). The
  translation becomes a second page: a switch in the bar shows the original or the translation,
  and you highlight on either one, the highlighting follows by time. The app looks for the
  toolkit in `TRADUCTION_DIR`, `~/code/traduction` or `~/code/traduction-toolkit`, and asks for
  its folder otherwise.
- **Subtitles**: **Save the subtitles…** writes the text on the page as `.srt` (the toolkit's
  re-segmentation when it is there: two lines of 42 characters, 17 characters a second, cuts
  on the pauses). At the output, « Subtitles » draws the original or a translation into the
  picture of the edit (the toolkit's style), and « Subtitle files beside the edit » writes an
  `.srt` per language on the edit's timeline, carried in the MP4 as tracks too.
- **Instagram-like captions**: instead of the two lines at the bottom, the style the short
  videos share: a few big words at a time (four at most, Montserrat ExtraBold, white with a
  black outline), centred near the bottom of the picture, higher on a vertical one above the
  band the apps lay over a Reel, the spoken word in yellow, one card per group of words cut at sentence ends and pauses.
  Built from the words' timings (exact from the transcription, estimated from subtitles or a
  translation); sized as a share of the picture, so a vertical, a square and a landscape
  picture get the same look.
- **Subtitle editor**: the **Subtitles** button (Ctrl+U) replaces the page with the cues of the
  text shown, made once by the toolkit and kept with the project as you leave them: the text of
  each one edited in place (Enter splits at the cursor, Shift+Enter breaks the line, Tab goes
  on), split, merge, delete, the edges moved by a tenth of a second or set to the instant being
  played, undo. A translation's cues show the original words beside them. The pace of each cue
  (characters a second) is green up to 17, amber up to 22, red beyond; the rows that break the
  shape rules (42 characters a line, two lines, 7 s, overlaps) are tinted and say why. The picture shows the cue being played, in the burn-in proportions. **Shorten what reads
  too fast…** hands the chosen cues to `traduire.py`'s proofreading pass, by the local model or
  Claude. **Re-cut from the text** starts again from the toolkit's cutting. Edited cues are what
  **Save the subtitles…** and the output use, trimmed to the kept pieces.
- **Project files**: Project ▾ › **Save the project…** (Ctrl+Shift+S) writes a `.rve.json`
  beside the video with the text, the translations, the subtitles, the highlighting and the
  output settings;
  one file per clip from the same video, opened again by Ctrl+Shift+O, a drop, the home page
  field or the command line.
- Projects are kept (sound, text, highlighting): the same file opens again with its text.
- Ctrl+= and Ctrl+- change the text size. English, French, German, Spanish, Portuguese and
  Russian, following the system language.

More detail: [docs/NOTES.md](docs/NOTES.md). Prise en main pas à pas, en français, pour Linux,
macOS et Windows : [docs/PRISE-EN-MAIN.md](docs/PRISE-EN-MAIN.md).

## Install

- Debian, Ubuntu, Pop!_OS: add the [apt repository](https://funkypitt.github.io/apt-repo/), then `sudo apt install readers-video-editor`. Or take the `.deb` from the [latest release](https://github.com/funkypitt/readers-video-editor/releases/latest): `sudo apt install ./readers-video-editor_*_all.deb`. The transcription installs itself the first time (a subtitle file works without it).
- Arch, Manjaro: `git clone https://github.com/funkypitt/readers-video-editor && cd readers-video-editor/packaging && makepkg -si`.
- Windows (`.exe`) and macOS on Apple silicon (`.dmg`): from the latest release; they carry ffmpeg and the transcription. They are unsigned: on Windows *More info* › *Run anyway*, on macOS right click on the app › *Open* the first time.
- Anywhere else: `python3 readers_video_editor.py [video | project.rve.json] [subtitles.srt]` with PyQt5 (with QtMultimedia), numpy, soundfile and ffmpeg installed; faster-whisper is installed by the app on first use (python3 -m venv must work).
- The translation and the improved sound go through the [traduction toolkit](https://github.com/funkypitt/traduction-toolkit), which the app installs by itself (1.7.0): when it is not found, the dialog offers **Install it here** (the GitHub zip, a few MB, into the app's data folder, no git); the libraries a feature needs go into an environment of the app's own, made with the system Python and completed by pip on first use (`anthropic` for Claude; `deepfilternet`, `pyloudnorm`, `speechmos` for the sound, with torch: about half a gigabyte, once), the waiting page showing pip's lines. Your own Python environments are never touched; `TRADUCTION_DIR`, `TRADUCTION_PYTHON` and a toolkit in `~/code/traduction[-toolkit]` are still honoured first. The Anthropic key is asked for in the dialog and kept in the app's settings (plain text in its config file; the environment's `ANTHROPIC_API_KEY` works too). Ollama remains an app to install yourself. On macOS the sound improvement also fetches static `ffmpeg` and `ffprobe` builds for Apple silicon (martin-riedl.de) into the app's folder, since the toolkit calls them by name. Burning subtitles needs an ffmpeg with libass (the usual builds).
- The address feature needs nothing installed: the app keeps its own copy of yt-dlp in its data folder (`~/.local/share/readers-video-editor/bin`, `%APPDATA%\Readers Video Editor\bin`, `~/Library/Application Support/readers-video-editor/bin`).

## Build

`packaging/build-deb.sh` builds the .deb. The Windows and macOS binaries are built by GitHub
Actions at every `v*` tag. Single file, PyQt5 + numpy + soundfile + ffmpeg; faster-whisper fetched by the app.

## Crédits / Credits

© 2026 Pierre Gallaz. Développé avec [Claude Code](https://claude.com/claude-code) (Anthropic).
Licence MIT, voir `LICENSE`. The cutting method comes from the author's `monter.py`
(traduction toolkit); transcription by [faster-whisper](https://github.com/SYSTRAN/faster-whisper);
videos from addresses by [yt-dlp](https://github.com/yt-dlp/yt-dlp); translation and subtitle
re-segmentation by the author's `traduire.py`, sound finishing by the author's `finaliser.py` and
`nettoyer.py` (traduction toolkit; [DeepFilterNet](https://github.com/Rikorose/DeepFilterNet),
pyloudnorm, DNSMOS). Fonts: Roboto (Apache 2.0), Montserrat (SIL OFL 1.1, the captions)
and Literata (SIL OFL 1.1), bundled in `packaging/fonts`.
