"""A video opened with its subtitle file: the language the file names, the video beside it, the
sentences and the paragraphs of the text read from it.

Run: python3 -m unittest discover -s tests
"""
import os
import sys
import tempfile
import unittest

import numpy as np
import soundfile as sf

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import readers_video_editor as r  # noqa: E402

SR = 16000


def recording(path, seconds, pauses=(), room=0.02):
    """A steady « voice » over a room that is far from silent, quiet during `pauses`."""
    rng = np.random.default_rng(1)
    x = rng.normal(0, 0.2, int(seconds * SR))
    for a, b in pauses:
        x[int(a * SR):int(b * SR)] *= room / 0.2
    sf.write(path, x.astype("float32"), SR)


class Names(unittest.TestCase):
    def test_language_named_by_the_file(self):
        self.assertEqual(r.srt_language("/x/talk.fr.srt"), "fr")
        self.assertEqual(r.srt_language("/x/talk.pt-BR.srt"), "pt")
        self.assertEqual(r.srt_language("/x/talk.srt"), "")
        self.assertEqual(r.srt_language("/x/talk.final.srt"), "")

    def test_the_video_beside_the_subtitles(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ("talk.mp4", "talk.mp3", "other.mkv"):
                open(os.path.join(d, name), "w").close()
            self.assertEqual(r.media_beside(os.path.join(d, "talk.srt")), os.path.join(d, "talk.mp4"))
            self.assertEqual(r.media_beside(os.path.join(d, "talk.fr.srt")), os.path.join(d, "talk.mp4"))
            self.assertIsNone(r.media_beside(os.path.join(d, "nothing.srt")))


class Text(unittest.TestCase):
    def tokens(self, cues, seconds, pauses=()):
        with tempfile.TemporaryDirectory() as d:
            wav = os.path.join(d, "a.wav")
            recording(wav, seconds, pauses)
            return r.tokens_from_srt(cues, wav, seconds)

    def test_a_cue_cut_inside_a_sentence_does_not_end_it(self):
        t = self.tokens([(0.0, 2.0, "One sentence that goes on"), (2.0, 4.0, "over two cues. And another one.")], 4.0)
        words = [x for x in t if x[0]]
        self.assertEqual(len({x[3] for x in words}), 2)
        self.assertEqual(words[0][3], next(x for x in words if x[0] == "cues.")[3])

    def test_without_punctuation_each_cue_is_a_sentence(self):
        t = self.tokens([(0.0, 2.0, "no punctuation here"), (2.0, 4.0, "nor there at all")], 4.0)
        self.assertEqual(len({x[3] for x in t if x[0]}), 2)

    def test_a_pause_in_a_room_that_is_not_silent_is_heard(self):
        # the room at a tenth of the voice (-20 dB): against the loud passages alone it was « speech »
        t = self.tokens([(0.0, 6.0, "A first sentence here. Then a second one comes.")], 6.0, pauses=[(2.5, 3.7)])
        words = [x for x in t if x[0]]
        k = next(i for i, x in enumerate(words) if x[0] == "here.")
        self.assertGreaterEqual(words[k + 1][1] - words[k][2], 0.9)
        self.assertEqual(len(r.paragraph_spans(t)), 2)

    def test_a_long_text_without_a_measured_pause_still_has_paragraphs(self):
        sentence = "This sentence is said without the least pause after it."
        cues = [(k * 3.0, k * 3.0 + 3.0, sentence) for k in range(60)]
        t = self.tokens(cues, 180.0)
        sizes = [sum(len(t[i][0]) + 1 for i in range(a, b + 1)) for a, b in r.paragraph_spans(t)]
        self.assertGreater(len(sizes), 2)
        self.assertLess(max(sizes), 1100)
        for a, _b in r.paragraph_spans(t)[1:]:
            self.assertEqual(r._strength(t[a - 1][0]), 2)       # a paragraph starts after a full stop


if __name__ == "__main__":
    unittest.main()
