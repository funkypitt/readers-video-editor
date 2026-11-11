"""The choice of the spoken language: where to listen, which passages, the average, the question.

Run: python3 -m unittest discover -s tests
"""
import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import readers_video_editor as r  # noqa: E402

W = r.LANG_WINDOW


class Language(unittest.TestCase):
    def test_short_recording_is_one_window(self):
        self.assertEqual(r.language_candidates(W // 2), [0])

    def test_nine_places_inside_the_recording(self):
        places = r.language_candidates(40 * W)
        self.assertEqual(len(places), 9)
        self.assertTrue(all(0 < p and p + W < 40 * W for p in places))
        self.assertEqual(places, sorted(places))

    def test_no_more_places_than_windows(self):
        self.assertEqual(len(r.language_candidates(3 * W)), 3)

    def test_the_most_spoken_passages(self):
        shares = [(0, 0.1), (1, 0.9), (2, 0.5), (3, 0.0), (4, 0.8), (5, 0.7)]
        self.assertEqual(r.choose_passages(shares), [1, 4, 5])

    def test_tones_alone_give_nothing(self):
        self.assertEqual(r.choose_passages([(0, 0.0), (1, 0.01)]), [])

    def test_little_speech_takes_the_best_place(self):
        self.assertEqual(r.choose_passages([(0, 0.1), (1, 0.3)]), [1])

    def test_without_the_detector_passages_are_spread(self):
        self.assertEqual(r.choose_passages([(i, None) for i in range(9)]), [1, 4, 7])

    def test_average(self):
        heard = r.combine_guesses([{"en": 0.9, "fr": 0.1}, {"en": 0.7, "fr": 0.3}, {}])
        self.assertEqual(heard["language"], "en")
        self.assertAlmostEqual(heard["confidence"], 0.8)
        self.assertEqual(heard["passages"], 2)
        self.assertIsNone(r.combine_guesses([]))

    def test_question_only_when_plain(self):
        sure = {"language": "en", "confidence": 0.95, "probs": {"en": 0.95, "fr": 0.02}, "passages": 3}
        self.assertEqual(r.suggest_language("fr", sure), "en")
        self.assertIsNone(r.suggest_language("en", sure))
        self.assertIsNone(r.suggest_language("", sure))
        self.assertIsNone(r.suggest_language("fr", None))
        mixed = {"language": "en", "confidence": 0.75, "probs": {"en": 0.75, "fr": 0.2}, "passages": 3}
        self.assertIsNone(r.suggest_language("fr", mixed))
        unsure = {"language": "en", "confidence": 0.6, "probs": {"en": 0.6, "fr": 0.05}, "passages": 3}
        self.assertIsNone(r.suggest_language("fr", unsure))

    def test_last_language_is_forgotten(self):
        import tempfile
        kept = r.CONFIG_FILE
        with tempfile.TemporaryDirectory() as tmp:
            r.CONFIG_FILE = os.path.join(tmp, "config.json")
            try:
                r.write_json(r.CONFIG_FILE, {"language": "fr", "model": "small"})
                self.assertNotIn("language", r.load_config())
            finally:
                r.CONFIG_FILE = kept

if __name__ == "__main__":
    unittest.main()
