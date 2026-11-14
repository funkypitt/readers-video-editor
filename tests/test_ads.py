"""Passages that look like ads: SponsorBlock's question and answer, the phrases in the text, the
paragraphs they mark, and what accepting a proposal does to the highlighting.

Run: python3 -m unittest discover -s tests
"""
import hashlib
import os
import sys
import unittest
from urllib.parse import unquote

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import readers_video_editor as r  # noqa: E402


class SponsorBlock(unittest.TestCase):
    def test_youtube_ids(self):
        vid = "dQw4w9WgXcQ"
        for url in (f"https://www.youtube.com/watch?v={vid}", f"https://youtu.be/{vid}?t=3", f"https://m.youtube.com/watch?v={vid}&list=x",
                    f"https://youtube.com/shorts/{vid}", f"https://www.youtube.com/live/{vid}", f"https://music.youtube.com/watch?v={vid}"):
            self.assertEqual(r.youtube_id(url), vid, url)
        for url in ("https://x.com/a/status/1234567890123", "https://vimeo.com/123", "https://www.youtube.com/@channel", "", "not a url"):
            self.assertEqual(r.youtube_id(url), "", url)

    def test_only_the_prefix_leaves(self):
        vid = "dQw4w9WgXcQ"
        url = r.sponsorblock_url(vid)
        prefix = hashlib.sha256(vid.encode()).hexdigest()[:4]
        self.assertTrue(url.startswith("https://sponsor.ajay.app/api/skipSegments/" + prefix + "?"))
        self.assertNotIn(vid, url)
        self.assertEqual(unquote(url.split("categories=")[1]), '["sponsor","selfpromo","interaction"]')

    def test_answer_for_this_video_only(self):
        answer = [
            {"videoID": "other000000", "segments": [{"category": "sponsor", "actionType": "skip", "segment": [1, 20]}]},
            {"videoID": "dQw4w9WgXcQ", "segments": [
                {"category": "selfpromo", "actionType": "skip", "segment": [300.5, 320]},
                {"category": "sponsor", "actionType": "skip", "segment": [60, 95.25]},
                {"category": "sponsor", "actionType": "mute", "segment": [10, 20]},
                {"category": "poi_highlight", "actionType": "poi", "segment": [5, 5]},
                {"category": "interaction", "actionType": "skip", "segment": [400, 400.1]},
                {"category": "sponsor", "actionType": "skip", "segment": "broken"}]},
        ]
        self.assertEqual(r.sponsorblock_segments(answer, "dQw4w9WgXcQ"),
                         [{"start": 60.0, "end": 95.25, "category": "sponsor"}, {"start": 300.5, "end": 320.0, "category": "selfpromo"}])
        self.assertEqual(r.sponsorblock_segments({"error": 1}, "dQw4w9WgXcQ"), [])


AD = {
    "en": ["This video is sponsored by NordVPN.",
           "Today's sponsor is Squarespace, the all-in-one platform.",
           "This episode is brought to you by Athletic Greens.",
           "Get 20% off with promo code LINUS.",
           "Use code SAVE20 at checkout to save on your first order.",
           "Thanks to Brilliant for sponsoring this video.",
           "Head to squarespace.com and grab a free trial, link in the description."],
    "fr": ["Cette vidéo est sponsorisée par Dashlane.",
           "Avec le code promo SALUT, vous avez dix euros offerts.",
           "Merci à Le Slip Français, partenaire de cette vidéo.",
           "Cet épisode vous est offert par Qonto.",
           "Notre partenaire Holy vous offre 15 % de réduction, le lien en description."],
    "de": ["Dieses Video wird von Raid Shadow Legends gesponsert.",
           "Gesponsert von Squarespace.",
           "Mit dem Rabattcode HALLO bekommt ihr zehn Prozent.",
           "Dieses Video enthält Werbung für Holyfat.",
           "Der Link in der Beschreibung bringt euch 20 % Rabatt."],
    "es": ["Este vídeo está patrocinado por Audible.",
           "Usa el código de descuento HOLA en la tienda.",
           "Antes de empezar, unas palabras de nuestro patrocinador.",
           "Tienes un 30 % de descuento con el enlace en la descripción."],
    "pt": ["Este vídeo é patrocinado pela Hostinger.",
           "Use o cupom de desconto OI e economize.",
           "Antes de começar, uma palavra do nosso patrocinador.",
           "Com o código promocional TCHAU você ganha frete grátis."],
    "ru": ["Используйте промокод ПРИВЕТ, чтобы получить подарок.",
           "Спонсор этого видео — Скиллбокс.",
           "Этот выпуск спонсирует сервис доставки.",
           "Спонсор дарит скидку 20% по ссылке в описании."],
}
NOT_AD = {
    "en": ["The bill was sponsored by Senator Warren and passed the House.",
           "The conference sponsored by the university drew two hundred people.",
           "You will find the link in the description if you want to read the study.",
           "Prices fell by 20 percent off-peak, and the code of conduct changed.",
           "We use code reviews to catch mistakes before they ship.",
           "A sponsor is a person who supports someone in recovery."],
    "fr": ["Le projet de loi parrainé par la députée a été adopté hier.",
           "Notre partenaire historique, la commune, a voté le budget.",
           "Le tournoi sponsorisé par la banque a été annulé.",
           "Le code de la route a changé au premier janvier."],
    "de": ["Die Studie wurde vom Ministerium gesponsert durch Steuergelder.",
           "Unser Sponsor im Verein ist die örtliche Bäckerei.",
           "Werbung im Fernsehen wirkt weniger als früher.",
           "Der Link in der Beschreibung führt zum Artikel."],
    "es": ["El proyecto de ley patrocinado por la senadora fue aprobado.",
           "Encontrarás el enlace en la descripción para leer el informe.",
           "El cupón de racionamiento era común en la posguerra."],
    "pt": ["O projeto de lei patrocinado pelo deputado foi votado.",
           "O link na descrição leva ao artigo completo.",
           "Trabalhamos em parceria com a prefeitura neste projeto."],
    "ru": ["Главный спонсор турнира отказался от участия.",
           "Ссылка в описании ведёт на статью.",
           "Цены выросли на 20 процентов за год."],
}


class Phrases(unittest.TestCase):
    def test_ads_are_seen(self):
        for lang, texts in AD.items():
            for t in texts:
                self.assertTrue(r.looks_like_ad(t), f"{lang}: {t}")

    def test_ordinary_speech_is_left(self):
        for lang, texts in NOT_AD.items():
            for t in texts:
                self.assertFalse(r.looks_like_ad(t), f"{lang}: {t}")

    def test_every_language_has_phrases(self):
        for lang in ("en", "fr", "de", "es", "pt", "ru"):
            self.assertTrue(r.AD_STRONG[lang] and r.AD_WEAK[lang], lang)

    def test_typographic_apostrophe(self):
        self.assertTrue(r.looks_like_ad("Today’s sponsor is Brilliant."))
        self.assertTrue(r.looks_like_ad("Partenaire de l’épisode : Qonto."))


def tok(words, start, sentence, step=0.4):
    """Tokens (word, start, end, sentence) one after the other."""
    out, t = [], start
    for w in words.split():
        out.append([w, t, t + step - 0.05, sentence])
        t += step
        if w[-1] in ".!?":
            sentence += 1
    return out


class Passages(unittest.TestCase):
    def setUp(self):
        # three paragraphs (2 s pauses), the middle two an ad, then a passage without words, an ad, and the talk again
        self.tokens = (tok("Hello and welcome to the show.", 0.0, 0)
                       + tok("This video is sponsored by Acme.", 5.0, 1)
                       + tok("Use code ACME at checkout for 10% off.", 10.0, 2)
                       + [[None, 14.0, 20.0, 3]]
                       + tok("Acme gives you a free trial, link in the description.", 20.0, 4)
                       + tok("Back to our story about the river.", 30.0, 5))

    def test_paragraphs(self):
        spans = r.paragraph_spans(self.tokens)
        self.assertEqual(len(spans), 5)
        self.assertEqual(spans[0], (0, 5))

    def test_neighbouring_ads_are_one_passage(self):
        p = r.ad_passages(self.tokens)
        self.assertEqual(len(p), 1)
        a, b = p[0]
        self.assertEqual(self.tokens[a][0], "This")
        self.assertEqual(self.tokens[b][0], "description.")

    def test_paragraph_rule_matches_the_page(self):
        many = tok("One. Two three.", 0.0, 0) + tok("Four five.", 3.0, 2) + tok("Six.", 10.0, 3)
        self.assertEqual([(a, b) for a, b in r.paragraph_spans(many)], [(0, 2), (3, 4), (5, 5)])

    def test_proposals(self):
        sb = [{"start": 4.0, "end": 9.0, "category": "sponsor"}]
        items = r.ad_proposals(sb, [(5.0, 26.0), (40.0, 50.0)])
        self.assertEqual([x["source"] for x in items], ["sponsorblock", "text"])
        self.assertEqual(items[1]["start"], 40.0)
        self.assertEqual(r.ad_proposals(sb, [(40.0, 50.0)], dismissed=[items[0]["key"]])[0]["source"], "text")

    def test_ranges_and_cuts(self):
        items = r.ad_proposals([], [(5.0, 26.0)])
        (x, a, b), = r.ad_ranges(self.tokens, items)
        self.assertEqual((self.tokens[a][0], self.tokens[b][0]), ("This", "description."))
        n = len(self.tokens)
        sel = np.zeros(n, dtype=np.uint8)
        self.assertFalse(r.is_cut(sel, "keep", a, b))
        self.assertFalse(r.is_cut(sel, "cut", a, b))
        cut = r.with_cuts(sel, "cut", [(a, b)])
        self.assertTrue(r.is_cut(cut, "cut", a, b))
        self.assertEqual(int(cut.sum()), b - a + 1)
        keep = r.with_cuts(sel, "keep", [(a, b)])
        self.assertTrue(r.is_cut(keep, "keep", a, b))
        self.assertEqual(int(keep.sum()), n - (b - a + 1))
        partly = np.zeros(n, dtype=np.uint8)
        partly[0:3] = 1
        self.assertTrue(r.is_cut(partly, "keep", a, b))
        self.assertEqual(int(sel.sum()), 0)


if __name__ == "__main__":
    unittest.main()
