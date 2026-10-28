# Reader's Video Editor

Cut a video or a recording by highlighting its text. The words are transcribed on this
computer (or read from a subtitle file) and shown on a page; what you highlight is kept, or
cut; the cuts land in the quiet between two words, each piece gets its fades, and ffmpeg
writes the new file with a log of the cuts and an edit list. The same page reads well on its
own: a transcript in airy paragraphs that follows the sound, to read, save or copy. One of the
[Reader's](https://gallaz.ch/apps) apps: white on black, Roboto, six languages, nothing leaves
the computer.

## Key points

- **Open** a video or a recording (MP4, MKV, MOV, WebM, MP3, M4A, WAV, FLAC…), or drop it on the
  window. A `.srt` beside it with the same name is read at once; otherwise the words are
  transcribed here (faster-whisper, CPU; the model is downloaded once).
- **Highlight** by dragging over the words. A click on a word plays from there; a double click
  takes the sentence; Shift + click extends from the last word; Alt or the eraser removes. The
  passages without words (music, silence, a dropped bit) are tokens too, marked by one click.
- **Keep or cut**: « I highlight what I keep » makes the edit of the highlighted passages;
  « I highlight what I cut » removes them and keeps all the rest.
- **The cuts** are placed in the quietest instant near each boundary, never on a word; the sound
  fades in and out at each piece (0 to 3 s), the picture fades to black only where a second or
  more is removed. The log (.txt) says what was kept and removed, word for word; the edit list
  (.edl, CMX 3600) reopens the cut in a video editor.
- **Preview** plays the edit, jumping over what is removed. **Export** writes MP4 (picture
  re-encoded once, x264), or MP3 / M4A / WAV from the sound alone, beside the original.
- **Read**: the page alone across the window, about seventy characters a line, the word being
  spoken underlined, −5 s / +10 s, speed 0.8 to 2×. **Save the text…** writes the transcript as
  paragraphs; Ctrl+Shift+C copies it.
- Projects are kept (sound, text, highlighting): the same file opens again with its text.
- Ctrl+T flips white on black / black on white; Ctrl+= and Ctrl+- change the text size.
  English, French, German, Spanish, Portuguese and Russian, following the system language.

More detail: [docs/NOTES.md](docs/NOTES.md).

## Install

- Debian, Ubuntu, Pop!_OS: add the [apt repository](https://funkypitt.github.io/apt-repo/), then `sudo apt install readers-video-editor`. Or take the `.deb` from the [latest release](https://github.com/funkypitt/readers-video-editor/releases/latest): `sudo apt install ./readers-video-editor_*_all.deb`. For the transcription: `pip install faster-whisper` (a subtitle file works without it).
- Arch, Manjaro: `git clone https://github.com/funkypitt/readers-video-editor && cd readers-video-editor/packaging && makepkg -si`.
- Windows (`.exe`) and macOS (`.dmg`, `apple-silicon` or `intel`): from the latest release; they carry ffmpeg and the transcription. They are unsigned: on Windows *More info* › *Run anyway*, on macOS right click on the app › *Open* the first time.
- Anywhere else: `python3 readers_video_editor.py [video] [subtitles.srt]` with PyQt5 (with QtMultimedia), numpy, soundfile and ffmpeg installed; faster-whisper for the transcription.

## Build

`packaging/build-deb.sh` builds the .deb. The Windows and macOS binaries are built by GitHub
Actions at every `v*` tag. Single file, PyQt5 + numpy + soundfile + ffmpeg; faster-whisper optional.

## Crédits / Credits

© 2026 Pierre Gallaz. Développé avec [Claude Code](https://claude.com/claude-code) (Anthropic).
Licence MIT, voir `LICENSE`. The cutting method comes from the author's `monter.py`
(traduction toolkit); transcription by [faster-whisper](https://github.com/SYSTRAN/faster-whisper).
