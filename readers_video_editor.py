#!/usr/bin/env python3
"""Reader's Video Editor — cut a video or a recording by highlighting its text. The words are
transcribed on this computer (or read from a subtitle file), shown on a page; what you highlight
is kept (or cut), the cuts land in the quiet between two words, each piece gets its fades, and
ffmpeg writes the new file with a log of the cuts and an edit list. One file, PyQt5 + numpy +
soundfile; faster-whisper for the transcription. MIT licence."""

import glob
import hashlib
import json
import locale
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
from pathlib import Path

import numpy as np
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer
from PyQt5.QtMultimediaWidgets import QVideoWidget

APP = "readers-video-editor"
VERSION = "1.9.0"


def _app_dirs():
    """Settings and work folders, one place per desktop (as the other Reader's desktop apps)."""
    if sys.platform == "win32":
        base = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "Readers Video Editor")
        return base, base
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support/" + APP)
        return base, base
    return (os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), APP),
            os.path.join(os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")), APP))


CONFIG_DIR, DATA_DIR = _app_dirs()
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
PROJECTS_DIR = os.path.join(DATA_DIR, "projects")
MODELS_DIR = os.path.join(DATA_DIR, "models")

# A gap of PAUSE_GAP seconds or more between two words becomes a token "without words" of its
# own, visible and markable like a word (music, silence, a passage the transcription dropped).
PAUSE_GAP = 2.0
# At the very start and end of the file the marker appears from EDGE_GAP on: that is where the
# microphone noises one wants to remove sit.
EDGE_GAP = 0.3
FADE_DEFAULT = 0.5
FADE_MAX = 3.0
FADES = [0.0, 0.2, 0.5, 1.0, 1.5]
# A join that removes less than this (a word, a hesitation) is a straight cut in the picture: a
# fade to black there would make the screen blink.
IMAGE_FADE_MIN = 1.0
ANTI_CLICK = 0.01           # the shortest fade, even with "fade = 0"
ESTIMATED_PLAY = 0.25       # words placed from subtitles: the quiet point is looked for on both sides
PAUSE_SPEECH = 0.15         # below, a dip is part of the speech
PAUSE_MARK = 0.25           # a pause of the voice serves as a landmark for the ends of sentences from here
SENTENCE_END = ".!?…"
PUNCTUATION = SENTENCE_END + ",;:—–"
CLOSERS = "»\"”’')]   "

EXT_VIDEO = {".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi", ".wmv", ".flv", ".mpg", ".mpeg", ".ts", ".mts", ".3gp", ".ogv"}
EXT_AUDIO = {".mp3", ".m4a", ".wav", ".flac", ".ogg", ".oga", ".opus", ".aac", ".wma", ".aiff", ".aif", ".amr", ".mka"}
LANGUAGES = [("", "auto"), ("fr", "Français"), ("en", "English"), ("de", "Deutsch"), ("es", "Español"), ("it", "Italiano"),
             ("pt", "Português"), ("nl", "Nederlands"), ("ru", "Русский"), ("pl", "Polski"), ("ja", "日本語"), ("zh", "中文")]
MODELS = ["tiny", "base", "small", "medium", "large-v3"]
MODEL_DEFAULT = "small"
HALLUCINATION_SILENCE = 2.0  # faster-whisper: a doubtful passage between silences this long is dropped
WORD_MAX_DUR = 3.0          # traduire.ABERRANT_WORD_MAX_DUR_SEC: no word lasts longer
WORD_RATIO = 4.0            # traduire.ABERRANT_WORD_RATIO: nor 4 times the median word of its segment
WORD_CPS = 14.0             # traduire.CHARS_PER_SECOND_ESTIMATE: the length given back to such a word


# ------------------------------------------------------------------------------------------
# Six languages, the English text as the key (the launcher's languages: en, fr, de, es, pt, ru)
# ------------------------------------------------------------------------------------------

_TR = {
 "fr": {
  "Cancel": "Annuler",
  "Choose a video or a recording, or give the address of a video online. The text appears, you highlight what you keep, or what you remove, and the edit is made for you.": "Choisissez une vidéo ou un enregistrement, ou donnez l'adresse d'une vidéo en ligne. Le texte s'affiche, vous surlignez ce que vous gardez, ou ce que vous retirez, et le montage se fait tout seul.",
  "File location, or address of a video (YouTube, X…)": "Emplacement du fichier, ou adresse d'une vidéo (YouTube, X…)",
  "Browse…": "Parcourir…",
  "Open": "Ouvrir",
  "Spoken language": "Langue parlée",
  "Resume": "Reprendre",
  "Give a file or an address.": "Indiquez un fichier ou une adresse.",
  "Video": "Vidéo",
  "Recording": "Enregistrement",
  "I highlight": "Je surligne",
  "what I keep": "ce que je garde",
  "what I cut": "ce que je coupe",
  "Highlighter": "Stabilo",
  "Eraser": "Gomme",
  "Undo": "Annuler",
  "Redo": "Rétablir",
  "Another file": "Autre fichier",
  "Text": "Texte",
  "Read": "Lire",
  "Edit": "Monter",
  "▶ Watch the edit": "▶ Voir le montage",
  "▶ Listen to the edit": "▶ Écouter le montage",
  "■ Stop": "■ Arrêter",
  "Clear all": "Tout effacer",
  "Strike the silence": "Rayer le silence",
  "Strike the %1 silences": "Rayer les %1 silences",
  "Produce": "Produire",
  "Fade at each cut": "Fondu à chaque coupe",
  "None": "Aucun",
  "Brief (0.2 s)": "Bref (0,2 s)",
  "Normal (0.5 s)": "Normal (0,5 s)",
  "Slow (1 s)": "Lent (1 s)",
  "Very slow (1.5 s)": "Très lent (1,5 s)",
  "A video (MP4)": "Une vidéo (MP4)",
  "The sound alone (%1)": "Le son seul (%1)",
  "Produce the edit": "Produire le montage",
  "Stop": "Arrêter",
  "Edit finished": "Montage terminé",
  "Watch": "Regarder",
  "Listen": "Écouter",
  "Open the folder": "Ouvrir le dossier",
  "Close": "Fermer",
  "The transcription failed.": "La transcription a échoué.",
  "Start the transcription again": "Recommencer la transcription",
  "Open subtitles…": "Ouvrir des sous-titres…",
  "Transcribe again…": "Transcrire à nouveau…",
  "Transcribe": "Transcrire",
  "Save the text…": "Enregistrer le texte…",
  "Installing the transcription (faster-whisper, once, about 300 MB)…": "Installation de la transcription (faster-whisper, une fois, environ 300 Mo)…",
  "The transcription could not be installed: %1": "La transcription n'a pas pu être installée : %1",
  "Shortcuts: Space play/pause · ← → 5 s · S highlighter · G eraser · Ctrl+Z undo · Ctrl+R read · Ctrl+= Ctrl+- text size · Ctrl+O file · Ctrl+L address": "Raccourcis : Espace lecture/pause · ← → 5 s · S stabilo · G gomme · Ctrl+Z annuler · Ctrl+R lire · Ctrl+= Ctrl+- taille du texte · Ctrl+O fichier · Ctrl+L adresse",
  "Transcribing…": "Transcription en cours…",
  "Beside it: the log of the cuts (.txt) and the edit list (.edl).": "À côté : le journal des coupes (.txt) et la liste de montage (.edl).",
  "Looking for the words in the sound…": "Recherche des mots dans le son…",
  "auto": "auto",
  "address…": "adresse…",
  "Open an address": "Ouvrir une adresse",
  "The address of a video (YouTube, X…). It is fetched here, with its subtitles when the site has them.": "L'adresse d'une vidéo (YouTube, X…). Elle est téléchargée ici, avec ses sous-titres quand le site en a.",
  "Fetching yt-dlp (once)…": "Téléchargement de yt-dlp (une fois)…",
  "Updating yt-dlp…": "Mise à jour de yt-dlp…",
  "Downloading…": "Téléchargement…",
  "Downloading… %1 %": "Téléchargement… %1 %",
  "Joining the picture and the sound…": "Assemblage de l'image et du son…",
  "The download failed: %1": "Le téléchargement a échoué : %1",
  "no video in the answer": "pas de vidéo dans la réponse",
  "yt-dlp could not be fetched (no network?): %1": "yt-dlp n'a pas pu être téléchargé (pas de réseau ?) : %1",
  "Downloaded: %1": "Téléchargé : %1",
  "Ctrl+L address": "Ctrl+L adresse",
  "read": "lire",
  "edit": "monter",
  "save the text…": "enregistrer le texte…",
  "copy the text": "copier le texte",
  "Save the text": "Enregistrer le texte",
  "Text (*.txt)": "Texte (*.txt)",
  "Text saved: %1": "Texte enregistré : %1",
  "Text copied.": "Texte copié.",
  "speed": "vitesse",
  "open…": "ouvrir…", "subtitles…": "sous-titres…", "transcribe": "transcrire", "stop": "arrêter",
  "highlight": "stabilo", "erase": "gomme", "I highlight what I keep": "je surligne ce que je garde",
  "I highlight what I cut": "je surligne ce que je coupe", "fade": "fondu", "s": "s", "none": "aucun",
  "fade the picture to black": "fondu au noir de l'image", "export…": "exporter…", "preview the edit": "écouter le montage",
  "stop the preview": "arrêter l'écoute", "undo": "annuler", "redo": "rétablir", "language": "langue", "model": "modèle",
  "Open a video or a recording": "Ouvrir une vidéo ou un enregistrement",
  "Video and audio files": "Fichiers vidéo et audio", "Subtitles (*.srt)": "Sous-titres (*.srt)",
  "Open the subtitles of this file": "Ouvrir les sous-titres de ce fichier",
  "Drop a video, a recording or a link here, or press Ctrl+O / Ctrl+L.": "Déposez ici une vidéo, un enregistrement ou un lien, ou appuyez sur Ctrl+O / Ctrl+L.",
  "Reading the file…": "Lecture du fichier…", "Extracting the sound…": "Extraction du son…",
  "Loading the model %1 (downloaded once)…": "Chargement du modèle %1 (téléchargé une fois)…",
  "Transcribing… %1 %": "Transcription… %1 %", "Text ready: %1 words": "Texte prêt : %1 mots",
  "Text read from the subtitles: %1 words": "Texte repris des sous-titres : %1 mots",
  "The transcription needs faster-whisper: pip install faster-whisper — or open a subtitle file.": "La transcription demande faster-whisper : pip install faster-whisper — ou ouvrez un fichier de sous-titres.",
  "ffmpeg was not found. Install it (ffmpeg.org) and start again.": "ffmpeg est introuvable. Installez-le (ffmpeg.org) et relancez.",
  "This file cannot be read.": "Ce fichier ne peut pas être lu.", "No speech was found in this file.": "Aucune parole trouvée dans ce fichier.",
  "No subtitle in this file.": "Aucun sous-titre dans ce fichier.",
  "Drag over the text to highlight what you keep.": "Glissez sur le texte pour surligner ce que vous gardez.",
  "Drag over the text to strike what you remove: the edit keeps all the rest.": "Glissez sur le texte pour rayer ce que vous retirez : le montage garde tout le reste.",
  "A click on a word plays from there. A click on a passage without words marks it. A double click takes the whole sentence. For a long passage, click its first word, then its last one with Shift held.":
    "Un clic sur un mot lance la lecture à cet endroit. Un clic sur un passage sans paroles le marque. Un double clic prend la phrase entière. Pour un long passage, cliquez sur son premier mot puis, majuscule enfoncée, sur son dernier.",
  "Nothing highlighted": "Rien de surligné", "Nothing struck": "Rien de rayé", "Nothing is left": "Il ne reste rien",
  "Edit of %1": "Montage de %1", "%1 passage": "%1 passage", "%1 passages": "%1 passages", "out of %1": "sur %1",
  "%1 cut": "%1 coupe", "%1 cuts": "%1 coupes", "%1 less out of %2": "%1 en moins sur %2",
  "Without words": "Sans paroles", "Start": "Début", "Fin": "Fin", "End": "Fin", "without words": "sans paroles",
  "Export the edit": "Exporter le montage", "Piece %1 of %2": "Passage %1 sur %2", "Joining": "Assemblage",
  "Taking the passages": "Prélèvement des passages", "Encoding": "Encodage", "Exporting… %1 %": "Exportation… %1 %",
  "Done: %1 (%2). Beside it, the log of the cuts (.txt) and the edit list (.edl).": "Fait : %1 (%2). À côté, le journal des coupes (.txt) et la liste de montage (.edl).",
  "The edit could not be made: %1": "Le montage n'a pas pu être produit : %1", "Cancelled.": "Annulé.",
  "white on black / black on white": "blanc sur noir / noir sur blanc", "larger text": "texte plus grand", "smaller text": "texte plus petit",
  "remove": "retirer", "keep": "garder", "sound": "son", "video": "vidéo",
  "LOG OF THE CUTS": "JOURNAL DES COUPES", "Original file": "Fichier d'origine", "duration %1": "durée %1",
  "Edit produced": "Montage produit", "duration %1, on %2": "durée %1, le %2", "Setting": "Réglage",
  "the marked text is removed, all the rest is kept": "le texte marqué est retiré, tout le reste est gardé", "the marked text is kept": "le texte marqué est gardé",
  "Fade asked": "Fondu demandé", "(the sound fade never bites a word: it is shorter when the cut is tight)": "(le fondu du son ne mord jamais sur un mot : il est plus court quand la coupe est serrée)",
  "Picture": "Image", "straight cuts": "coupes franches", "fade to black where %1 or more is removed, straight cut elsewhere": "fondu au noir là où %1 ou plus est retirée, coupe franche ailleurs",
  "Pieces kept": "Morceaux gardés", "Removed in all": "Retiré en tout", "Times are hours:minutes:seconds.thousandths.": "Les instants sont en heures:minutes:secondes.millièmes.",
  "REMOVED": "RETIRÉ", "(without words)": "(sans paroles)", "PIECE %1": "MORCEAU %1", "in the original": "dans l'origine", "in the edit": "dans le montage",
  "fade in %1, fade out %2": "fondu d'entrée %1, fondu de sortie %2", "fade in": "entrée en fondu", "straight in": "entrée franche",
  "fade out to black": "sortie en fondu au noir", "straight out": "sortie franche", "straight in and out": "entrée et sortie franches", "text": "texte",
  "[%1 without words]": "[%1 sans paroles]", "Shortcuts: Space play/pause · ← → 5 s · S highlight · G erase · Ctrl+Z undo · Ctrl+Y redo · Ctrl+T ink · Ctrl+= Ctrl+- text size":
    "Raccourcis : Espace lecture/pause · ← → 5 s · S stabilo · G gomme · Ctrl+Z annuler · Ctrl+Y rétablir · Ctrl+T encre · Ctrl+= Ctrl+- taille du texte",
  "The sound of this file cannot be played here, the text still works and the export too.": "Le son de ce fichier ne peut pas être joué ici ; le texte et l'exportation marchent quand même.",
  "subtitles": "sous-titres", "transcription": "transcription",
 },
 "de": {
  "Cancel": "Abbrechen",
  "Choose a video or a recording, or give the address of a video online. The text appears, you highlight what you keep, or what you remove, and the edit is made for you.": "Wählen Sie ein Video oder eine Aufnahme, oder geben Sie die Adresse eines Videos im Netz an. Der Text erscheint, Sie markieren, was Sie behalten oder was wegfällt, und der Schnitt macht sich von selbst.",
  "File location, or address of a video (YouTube, X…)": "Speicherort der Datei, oder Adresse eines Videos (YouTube, X…)",
  "Browse…": "Durchsuchen…",
  "Open": "Öffnen",
  "Spoken language": "Gesprochene Sprache",
  "Resume": "Weitermachen",
  "Give a file or an address.": "Geben Sie eine Datei oder eine Adresse an.",
  "Video": "Video",
  "Recording": "Aufnahme",
  "I highlight": "Ich markiere",
  "what I keep": "was bleibt",
  "what I cut": "was wegfällt",
  "Highlighter": "Marker",
  "Eraser": "Radierer",
  "Undo": "Rückgängig",
  "Redo": "Wiederholen",
  "Another file": "Andere Datei",
  "Text": "Text",
  "Read": "Lesen",
  "Edit": "Schneiden",
  "▶ Watch the edit": "▶ Schnitt ansehen",
  "▶ Listen to the edit": "▶ Schnitt anhören",
  "■ Stop": "■ Stopp",
  "Clear all": "Alles löschen",
  "Strike the silence": "Die Stille streichen",
  "Strike the %1 silences": "Die %1 Stillen streichen",
  "Produce": "Erzeugen",
  "Fade at each cut": "Blende an jedem Schnitt",
  "None": "Keine",
  "Brief (0.2 s)": "Kurz (0,2 s)",
  "Normal (0.5 s)": "Normal (0,5 s)",
  "Slow (1 s)": "Langsam (1 s)",
  "Very slow (1.5 s)": "Sehr langsam (1,5 s)",
  "A video (MP4)": "Ein Video (MP4)",
  "The sound alone (%1)": "Nur der Ton (%1)",
  "Produce the edit": "Schnitt erzeugen",
  "Stop": "Stopp",
  "Edit finished": "Schnitt fertig",
  "Watch": "Ansehen",
  "Listen": "Anhören",
  "Open the folder": "Ordner öffnen",
  "Close": "Schließen",
  "The transcription failed.": "Die Transkription ist fehlgeschlagen.",
  "Start the transcription again": "Transkription neu starten",
  "Open subtitles…": "Untertitel öffnen…",
  "Transcribe again…": "Neu transkribieren…",
  "Transcribe": "Transkribieren",
  "Save the text…": "Text speichern…",
  "Installing the transcription (faster-whisper, once, about 300 MB)…": "Die Transkription wird installiert (faster-whisper, einmalig, etwa 300 MB)…",
  "The transcription could not be installed: %1": "Die Transkription konnte nicht installiert werden: %1",
  "Shortcuts: Space play/pause · ← → 5 s · S highlighter · G eraser · Ctrl+Z undo · Ctrl+R read · Ctrl+= Ctrl+- text size · Ctrl+O file · Ctrl+L address": "Tasten: Leertaste Wiedergabe/Pause · ← → 5 s · S Marker · G Radierer · Strg+Z rückgängig · Strg+R lesen · Strg+= Strg+- Textgröße · Strg+O Datei · Strg+L Adresse",
  "Transcribing…": "Transkription läuft…",
  "Beside it: the log of the cuts (.txt) and the edit list (.edl).": "Daneben: das Protokoll der Schnitte (.txt) und die Schnittliste (.edl).",
  "Looking for the words in the sound…": "Die Wörter werden im Ton gesucht…",
  "auto": "auto",
  "address…": "Adresse…",
  "Open an address": "Eine Adresse öffnen",
  "The address of a video (YouTube, X…). It is fetched here, with its subtitles when the site has them.": "Die Adresse eines Videos (YouTube, X…). Es wird hierher geladen, mit seinen Untertiteln, wenn die Seite welche hat.",
  "Fetching yt-dlp (once)…": "yt-dlp wird geladen (einmalig)…",
  "Updating yt-dlp…": "yt-dlp wird aktualisiert…",
  "Downloading…": "Wird heruntergeladen…",
  "Downloading… %1 %": "Wird heruntergeladen… %1 %",
  "Joining the picture and the sound…": "Bild und Ton werden zusammengefügt…",
  "The download failed: %1": "Der Download ist fehlgeschlagen: %1",
  "no video in the answer": "kein Video in der Antwort",
  "yt-dlp could not be fetched (no network?): %1": "yt-dlp konnte nicht geladen werden (kein Netz?): %1",
  "Downloaded: %1": "Heruntergeladen: %1",
  "Ctrl+L address": "Strg+L Adresse",
  "read": "lesen",
  "edit": "schneiden",
  "save the text…": "Text speichern…",
  "copy the text": "Text kopieren",
  "Save the text": "Text speichern",
  "Text (*.txt)": "Text (*.txt)",
  "Text saved: %1": "Text gespeichert: %1",
  "Text copied.": "Text kopiert.",
  "speed": "Tempo",
  "open…": "öffnen…", "subtitles…": "Untertitel…", "transcribe": "transkribieren", "stop": "stopp",
  "highlight": "Marker", "erase": "Radierer", "I highlight what I keep": "ich markiere, was bleibt",
  "I highlight what I cut": "ich markiere, was wegfällt", "fade": "Blende", "s": "s", "none": "keine",
  "fade the picture to black": "Bild nach Schwarz blenden", "export…": "exportieren…", "preview the edit": "Schnitt anhören",
  "stop the preview": "Anhören beenden", "undo": "rückgängig", "redo": "wiederholen", "language": "Sprache", "model": "Modell",
  "Open a video or a recording": "Ein Video oder eine Aufnahme öffnen",
  "Video and audio files": "Video- und Audiodateien", "Subtitles (*.srt)": "Untertitel (*.srt)",
  "Open the subtitles of this file": "Die Untertitel dieser Datei öffnen",
  "Drop a video, a recording or a link here, or press Ctrl+O / Ctrl+L.": "Ein Video, eine Aufnahme oder einen Link hierher ziehen, oder Strg+O / Strg+L drücken.",
  "Reading the file…": "Datei wird gelesen…", "Extracting the sound…": "Ton wird ausgelesen…",
  "Loading the model %1 (downloaded once)…": "Modell %1 wird geladen (einmal heruntergeladen)…",
  "Transcribing… %1 %": "Transkription… %1 %", "Text ready: %1 words": "Text bereit: %1 Wörter",
  "Text read from the subtitles: %1 words": "Text aus den Untertiteln: %1 Wörter",
  "The transcription needs faster-whisper: pip install faster-whisper — or open a subtitle file.": "Die Transkription braucht faster-whisper: pip install faster-whisper — oder eine Untertiteldatei öffnen.",
  "ffmpeg was not found. Install it (ffmpeg.org) and start again.": "ffmpeg wurde nicht gefunden. Installieren (ffmpeg.org) und neu starten.",
  "This file cannot be read.": "Diese Datei kann nicht gelesen werden.", "No speech was found in this file.": "Keine Sprache in dieser Datei gefunden.",
  "No subtitle in this file.": "Kein Untertitel in dieser Datei.",
  "Drag over the text to highlight what you keep.": "Über den Text ziehen, um zu markieren, was bleibt.",
  "Drag over the text to strike what you remove: the edit keeps all the rest.": "Über den Text ziehen, um durchzustreichen, was wegfällt: der Schnitt behält alles andere.",
  "A click on a word plays from there. A click on a passage without words marks it. A double click takes the whole sentence. For a long passage, click its first word, then its last one with Shift held.":
    "Ein Klick auf ein Wort spielt ab dort. Ein Klick auf eine Stelle ohne Worte markiert sie. Ein Doppelklick nimmt den ganzen Satz. Für eine lange Stelle: erstes Wort anklicken, dann mit gedrückter Umschalttaste das letzte.",
  "Nothing highlighted": "Nichts markiert", "Nothing struck": "Nichts durchgestrichen", "Nothing is left": "Nichts bleibt übrig",
  "Edit of %1": "Schnitt von %1", "%1 passage": "%1 Stelle", "%1 passages": "%1 Stellen", "out of %1": "von %1",
  "%1 cut": "%1 Schnitt", "%1 cuts": "%1 Schnitte", "%1 less out of %2": "%1 weniger von %2",
  "Without words": "Ohne Worte", "Start": "Anfang", "End": "Ende", "without words": "ohne Worte",
  "Export the edit": "Schnitt exportieren", "Piece %1 of %2": "Stück %1 von %2", "Joining": "Zusammenfügen",
  "Taking the passages": "Stellen werden entnommen", "Encoding": "Kodierung", "Exporting… %1 %": "Export… %1 %",
  "Done: %1 (%2). Beside it, the log of the cuts (.txt) and the edit list (.edl).": "Fertig: %1 (%2). Daneben das Schnittprotokoll (.txt) und die Schnittliste (.edl).",
  "The edit could not be made: %1": "Der Schnitt konnte nicht erstellt werden: %1", "Cancelled.": "Abgebrochen.",
  "white on black / black on white": "weiss auf schwarz / schwarz auf weiss", "larger text": "grösserer Text", "smaller text": "kleinerer Text",
  "remove": "entfernen", "keep": "behalten", "sound": "Ton", "video": "Video",
  "LOG OF THE CUTS": "SCHNITTPROTOKOLL", "Original file": "Originaldatei", "duration %1": "Dauer %1",
  "Edit produced": "Erstellter Schnitt", "duration %1, on %2": "Dauer %1, am %2", "Setting": "Einstellung",
  "the marked text is removed, all the rest is kept": "der markierte Text fällt weg, alles andere bleibt", "the marked text is kept": "der markierte Text bleibt",
  "Fade asked": "Gewünschte Blende", "(the sound fade never bites a word: it is shorter when the cut is tight)": "(die Tonblende schneidet nie in ein Wort: sie ist kürzer, wenn der Schnitt eng ist)",
  "Picture": "Bild", "straight cuts": "harte Schnitte", "fade to black where %1 or more is removed, straight cut elsewhere": "Schwarzblende, wo %1 oder mehr wegfällt, sonst harter Schnitt",
  "Pieces kept": "Behaltene Stücke", "Removed in all": "Insgesamt entfernt", "Times are hours:minutes:seconds.thousandths.": "Zeiten in Stunden:Minuten:Sekunden.Tausendstel.",
  "REMOVED": "ENTFERNT", "(without words)": "(ohne Worte)", "PIECE %1": "STÜCK %1", "in the original": "im Original", "in the edit": "im Schnitt",
  "fade in %1, fade out %2": "Einblende %1, Ausblende %2", "fade in": "Einblende", "straight in": "harter Einstieg",
  "fade out to black": "Ausblende nach Schwarz", "straight out": "harter Ausstieg", "straight in and out": "harter Ein- und Ausstieg", "text": "Text",
  "[%1 without words]": "[%1 ohne Worte]", "Shortcuts: Space play/pause · ← → 5 s · S highlight · G erase · Ctrl+Z undo · Ctrl+Y redo · Ctrl+T ink · Ctrl+= Ctrl+- text size":
    "Tasten: Leertaste Wiedergabe/Pause · ← → 5 s · S Marker · G Radierer · Strg+Z rückgängig · Strg+Y wiederholen · Strg+T Tinte · Strg+= Strg+- Textgrösse",
  "The sound of this file cannot be played here, the text still works and the export too.": "Der Ton dieser Datei kann hier nicht abgespielt werden; Text und Export funktionieren trotzdem.",
  "subtitles": "Untertitel", "transcription": "Transkription",
 },
 "es": {
  "Cancel": "Cancelar",
  "Choose a video or a recording, or give the address of a video online. The text appears, you highlight what you keep, or what you remove, and the edit is made for you.": "Elija un vídeo o una grabación, o dé la dirección de un vídeo en línea. El texto aparece, usted marca lo que conserva, o lo que quita, y el montaje se hace solo.",
  "File location, or address of a video (YouTube, X…)": "Ubicación del archivo, o dirección de un vídeo (YouTube, X…)",
  "Browse…": "Examinar…",
  "Open": "Abrir",
  "Spoken language": "Idioma hablado",
  "Resume": "Retomar",
  "Give a file or an address.": "Indique un archivo o una dirección.",
  "Video": "Vídeo",
  "Recording": "Grabación",
  "I highlight": "Marco",
  "what I keep": "lo que conservo",
  "what I cut": "lo que quito",
  "Highlighter": "Marcador",
  "Eraser": "Goma",
  "Undo": "Deshacer",
  "Redo": "Rehacer",
  "Another file": "Otro archivo",
  "Text": "Texto",
  "Read": "Leer",
  "Edit": "Montar",
  "▶ Watch the edit": "▶ Ver el montaje",
  "▶ Listen to the edit": "▶ Escuchar el montaje",
  "■ Stop": "■ Detener",
  "Clear all": "Borrar todo",
  "Strike the silence": "Tachar el silencio",
  "Strike the %1 silences": "Tachar los %1 silencios",
  "Produce": "Producir",
  "Fade at each cut": "Fundido en cada corte",
  "None": "Ninguno",
  "Brief (0.2 s)": "Breve (0,2 s)",
  "Normal (0.5 s)": "Normal (0,5 s)",
  "Slow (1 s)": "Lento (1 s)",
  "Very slow (1.5 s)": "Muy lento (1,5 s)",
  "A video (MP4)": "Un vídeo (MP4)",
  "The sound alone (%1)": "Solo el sonido (%1)",
  "Produce the edit": "Producir el montaje",
  "Stop": "Detener",
  "Edit finished": "Montaje terminado",
  "Watch": "Ver",
  "Listen": "Escuchar",
  "Open the folder": "Abrir la carpeta",
  "Close": "Cerrar",
  "The transcription failed.": "La transcripción ha fallado.",
  "Start the transcription again": "Reiniciar la transcripción",
  "Open subtitles…": "Abrir subtítulos…",
  "Transcribe again…": "Transcribir de nuevo…",
  "Transcribe": "Transcribir",
  "Save the text…": "Guardar el texto…",
  "Installing the transcription (faster-whisper, once, about 300 MB)…": "Instalando la transcripción (faster-whisper, una vez, unos 300 MB)…",
  "The transcription could not be installed: %1": "No se pudo instalar la transcripción: %1",
  "Shortcuts: Space play/pause · ← → 5 s · S highlighter · G eraser · Ctrl+Z undo · Ctrl+R read · Ctrl+= Ctrl+- text size · Ctrl+O file · Ctrl+L address": "Atajos: Espacio reproducir/pausa · ← → 5 s · S marcador · G goma · Ctrl+Z deshacer · Ctrl+R leer · Ctrl+= Ctrl+- tamaño del texto · Ctrl+O archivo · Ctrl+L dirección",
  "Transcribing…": "Transcribiendo…",
  "Beside it: the log of the cuts (.txt) and the edit list (.edl).": "Al lado: el registro de los cortes (.txt) y la lista de montaje (.edl).",
  "Looking for the words in the sound…": "Buscando las palabras en el sonido…",
  "auto": "auto",
  "address…": "dirección…",
  "Open an address": "Abrir una dirección",
  "The address of a video (YouTube, X…). It is fetched here, with its subtitles when the site has them.": "La dirección de un vídeo (YouTube, X…). Se descarga aquí, con sus subtítulos cuando el sitio los tiene.",
  "Fetching yt-dlp (once)…": "Descargando yt-dlp (una vez)…",
  "Updating yt-dlp…": "Actualizando yt-dlp…",
  "Downloading…": "Descargando…",
  "Downloading… %1 %": "Descargando… %1 %",
  "Joining the picture and the sound…": "Uniendo la imagen y el sonido…",
  "The download failed: %1": "La descarga ha fallado: %1",
  "no video in the answer": "ningún vídeo en la respuesta",
  "yt-dlp could not be fetched (no network?): %1": "No se pudo descargar yt-dlp (¿sin red?): %1",
  "Downloaded: %1": "Descargado: %1",
  "Ctrl+L address": "Ctrl+L dirección",
  "read": "leer",
  "edit": "montar",
  "save the text…": "guardar el texto…",
  "copy the text": "copiar el texto",
  "Save the text": "Guardar el texto",
  "Text (*.txt)": "Texto (*.txt)",
  "Text saved: %1": "Texto guardado: %1",
  "Text copied.": "Texto copiado.",
  "speed": "velocidad",
  "open…": "abrir…", "subtitles…": "subtítulos…", "transcribe": "transcribir", "stop": "parar",
  "highlight": "marcador", "erase": "goma", "I highlight what I keep": "marco lo que guardo",
  "I highlight what I cut": "marco lo que quito", "fade": "fundido", "s": "s", "none": "ninguno",
  "fade the picture to black": "fundir la imagen a negro", "export…": "exportar…", "preview the edit": "escuchar el montaje",
  "stop the preview": "parar la escucha", "undo": "deshacer", "redo": "rehacer", "language": "idioma", "model": "modelo",
  "Open a video or a recording": "Abrir un vídeo o una grabación",
  "Video and audio files": "Archivos de vídeo y audio", "Subtitles (*.srt)": "Subtítulos (*.srt)",
  "Open the subtitles of this file": "Abrir los subtítulos de este archivo",
  "Drop a video, a recording or a link here, or press Ctrl+O / Ctrl+L.": "Suelte aquí un vídeo, una grabación o un enlace, o pulse Ctrl+O / Ctrl+L.",
  "Reading the file…": "Leyendo el archivo…", "Extracting the sound…": "Extrayendo el sonido…",
  "Loading the model %1 (downloaded once)…": "Cargando el modelo %1 (descargado una vez)…",
  "Transcribing… %1 %": "Transcribiendo… %1 %", "Text ready: %1 words": "Texto listo: %1 palabras",
  "Text read from the subtitles: %1 words": "Texto tomado de los subtítulos: %1 palabras",
  "The transcription needs faster-whisper: pip install faster-whisper — or open a subtitle file.": "La transcripción necesita faster-whisper: pip install faster-whisper — o abra un archivo de subtítulos.",
  "ffmpeg was not found. Install it (ffmpeg.org) and start again.": "No se encontró ffmpeg. Instálelo (ffmpeg.org) y vuelva a abrir.",
  "This file cannot be read.": "Este archivo no se puede leer.", "No speech was found in this file.": "No se encontró habla en este archivo.",
  "No subtitle in this file.": "No hay subtítulos en este archivo.",
  "Drag over the text to highlight what you keep.": "Arrastre sobre el texto para marcar lo que guarda.",
  "Drag over the text to strike what you remove: the edit keeps all the rest.": "Arrastre sobre el texto para tachar lo que quita: el montaje guarda todo lo demás.",
  "A click on a word plays from there. A click on a passage without words marks it. A double click takes the whole sentence. For a long passage, click its first word, then its last one with Shift held.":
    "Un clic en una palabra reproduce desde ahí. Un clic en un pasaje sin palabras lo marca. Un doble clic toma la frase entera. Para un pasaje largo, pulse su primera palabra y luego la última con Mayús pulsada.",
  "Nothing highlighted": "Nada marcado", "Nothing struck": "Nada tachado", "Nothing is left": "No queda nada",
  "Edit of %1": "Montaje de %1", "%1 passage": "%1 pasaje", "%1 passages": "%1 pasajes", "out of %1": "de %1",
  "%1 cut": "%1 corte", "%1 cuts": "%1 cortes", "%1 less out of %2": "%1 menos de %2",
  "Without words": "Sin palabras", "Start": "Inicio", "End": "Fin", "without words": "sin palabras",
  "Export the edit": "Exportar el montaje", "Piece %1 of %2": "Pasaje %1 de %2", "Joining": "Ensamblado",
  "Taking the passages": "Tomando los pasajes", "Encoding": "Codificación", "Exporting… %1 %": "Exportando… %1 %",
  "Done: %1 (%2). Beside it, the log of the cuts (.txt) and the edit list (.edl).": "Hecho: %1 (%2). Al lado, el registro de cortes (.txt) y la lista de montaje (.edl).",
  "The edit could not be made: %1": "No se pudo producir el montaje: %1", "Cancelled.": "Cancelado.",
  "white on black / black on white": "blanco sobre negro / negro sobre blanco", "larger text": "texto más grande", "smaller text": "texto más pequeño",
  "remove": "quitar", "keep": "guardar", "sound": "sonido", "video": "vídeo",
  "LOG OF THE CUTS": "REGISTRO DE CORTES", "Original file": "Archivo original", "duration %1": "duración %1",
  "Edit produced": "Montaje producido", "duration %1, on %2": "duración %1, el %2", "Setting": "Ajuste",
  "the marked text is removed, all the rest is kept": "el texto marcado se quita, todo lo demás se guarda", "the marked text is kept": "el texto marcado se guarda",
  "Fade asked": "Fundido pedido", "(the sound fade never bites a word: it is shorter when the cut is tight)": "(el fundido del sonido nunca muerde una palabra: es más corto cuando el corte es ajustado)",
  "Picture": "Imagen", "straight cuts": "cortes secos", "fade to black where %1 or more is removed, straight cut elsewhere": "fundido a negro donde se quita %1 o más, corte seco en el resto",
  "Pieces kept": "Pasajes guardados", "Removed in all": "Quitado en total", "Times are hours:minutes:seconds.thousandths.": "Los instantes van en horas:minutos:segundos.milésimas.",
  "REMOVED": "QUITADO", "(without words)": "(sin palabras)", "PIECE %1": "PASAJE %1", "in the original": "en el original", "in the edit": "en el montaje",
  "fade in %1, fade out %2": "entrada %1, salida %2", "fade in": "entrada en fundido", "straight in": "entrada seca",
  "fade out to black": "salida en fundido a negro", "straight out": "salida seca", "straight in and out": "entrada y salida secas", "text": "texto",
  "[%1 without words]": "[%1 sin palabras]", "Shortcuts: Space play/pause · ← → 5 s · S highlight · G erase · Ctrl+Z undo · Ctrl+Y redo · Ctrl+T ink · Ctrl+= Ctrl+- text size":
    "Atajos: Espacio reproducir/pausa · ← → 5 s · S marcador · G goma · Ctrl+Z deshacer · Ctrl+Y rehacer · Ctrl+T tinta · Ctrl+= Ctrl+- tamaño del texto",
  "The sound of this file cannot be played here, the text still works and the export too.": "El sonido de este archivo no puede reproducirse aquí; el texto y la exportación funcionan igual.",
  "subtitles": "subtítulos", "transcription": "transcripción",
 },
 "pt": {
  "Cancel": "Cancelar",
  "Choose a video or a recording, or give the address of a video online. The text appears, you highlight what you keep, or what you remove, and the edit is made for you.": "Escolha um vídeo ou uma gravação, ou dê o endereço de um vídeo em linha. O texto aparece, você marca o que guarda, ou o que retira, e a montagem faz-se sozinha.",
  "File location, or address of a video (YouTube, X…)": "Localização do ficheiro, ou endereço de um vídeo (YouTube, X…)",
  "Browse…": "Procurar…",
  "Open": "Abrir",
  "Spoken language": "Língua falada",
  "Resume": "Retomar",
  "Give a file or an address.": "Indique um ficheiro ou um endereço.",
  "Video": "Vídeo",
  "Recording": "Gravação",
  "I highlight": "Eu marco",
  "what I keep": "o que guardo",
  "what I cut": "o que retiro",
  "Highlighter": "Marcador",
  "Eraser": "Borracha",
  "Undo": "Anular",
  "Redo": "Refazer",
  "Another file": "Outro ficheiro",
  "Text": "Texto",
  "Read": "Ler",
  "Edit": "Montar",
  "▶ Watch the edit": "▶ Ver a montagem",
  "▶ Listen to the edit": "▶ Ouvir a montagem",
  "■ Stop": "■ Parar",
  "Clear all": "Apagar tudo",
  "Strike the silence": "Riscar o silêncio",
  "Strike the %1 silences": "Riscar os %1 silêncios",
  "Produce": "Produzir",
  "Fade at each cut": "Fundido em cada corte",
  "None": "Nenhum",
  "Brief (0.2 s)": "Breve (0,2 s)",
  "Normal (0.5 s)": "Normal (0,5 s)",
  "Slow (1 s)": "Lento (1 s)",
  "Very slow (1.5 s)": "Muito lento (1,5 s)",
  "A video (MP4)": "Um vídeo (MP4)",
  "The sound alone (%1)": "Só o som (%1)",
  "Produce the edit": "Produzir a montagem",
  "Stop": "Parar",
  "Edit finished": "Montagem terminada",
  "Watch": "Ver",
  "Listen": "Ouvir",
  "Open the folder": "Abrir a pasta",
  "Close": "Fechar",
  "The transcription failed.": "A transcrição falhou.",
  "Start the transcription again": "Recomeçar a transcrição",
  "Open subtitles…": "Abrir legendas…",
  "Transcribe again…": "Transcrever de novo…",
  "Transcribe": "Transcrever",
  "Save the text…": "Guardar o texto…",
  "Installing the transcription (faster-whisper, once, about 300 MB)…": "A instalar a transcrição (faster-whisper, uma vez, cerca de 300 MB)…",
  "The transcription could not be installed: %1": "Não foi possível instalar a transcrição: %1",
  "Shortcuts: Space play/pause · ← → 5 s · S highlighter · G eraser · Ctrl+Z undo · Ctrl+R read · Ctrl+= Ctrl+- text size · Ctrl+O file · Ctrl+L address": "Atalhos: Espaço reproduzir/pausa · ← → 5 s · S marcador · G borracha · Ctrl+Z anular · Ctrl+R ler · Ctrl+= Ctrl+- tamanho do texto · Ctrl+O ficheiro · Ctrl+L endereço",
  "Transcribing…": "A transcrever…",
  "Beside it: the log of the cuts (.txt) and the edit list (.edl).": "Ao lado: o registo dos cortes (.txt) e a lista de montagem (.edl).",
  "Looking for the words in the sound…": "A procurar as palavras no som…",
  "auto": "auto",
  "address…": "endereço…",
  "Open an address": "Abrir um endereço",
  "The address of a video (YouTube, X…). It is fetched here, with its subtitles when the site has them.": "O endereço de um vídeo (YouTube, X…). É descarregado aqui, com as legendas quando o site as tem.",
  "Fetching yt-dlp (once)…": "A descarregar o yt-dlp (uma vez)…",
  "Updating yt-dlp…": "A atualizar o yt-dlp…",
  "Downloading…": "A descarregar…",
  "Downloading… %1 %": "A descarregar… %1 %",
  "Joining the picture and the sound…": "A juntar a imagem e o som…",
  "The download failed: %1": "A transferência falhou: %1",
  "no video in the answer": "nenhum vídeo na resposta",
  "yt-dlp could not be fetched (no network?): %1": "Não foi possível descarregar o yt-dlp (sem rede?): %1",
  "Downloaded: %1": "Descarregado: %1",
  "Ctrl+L address": "Ctrl+L endereço",
  "read": "ler",
  "edit": "montar",
  "save the text…": "guardar o texto…",
  "copy the text": "copiar o texto",
  "Save the text": "Guardar o texto",
  "Text (*.txt)": "Texto (*.txt)",
  "Text saved: %1": "Texto guardado: %1",
  "Text copied.": "Texto copiado.",
  "speed": "velocidade",
  "open…": "abrir…", "subtitles…": "legendas…", "transcribe": "transcrever", "stop": "parar",
  "highlight": "marcador", "erase": "borracha", "I highlight what I keep": "marco o que fica",
  "I highlight what I cut": "marco o que sai", "fade": "fundido", "s": "s", "none": "nenhum",
  "fade the picture to black": "fundir a imagem para preto", "export…": "exportar…", "preview the edit": "ouvir a montagem",
  "stop the preview": "parar a audição", "undo": "anular", "redo": "refazer", "language": "língua", "model": "modelo",
  "Open a video or a recording": "Abrir um vídeo ou uma gravação",
  "Video and audio files": "Ficheiros de vídeo e áudio", "Subtitles (*.srt)": "Legendas (*.srt)",
  "Open the subtitles of this file": "Abrir as legendas deste ficheiro",
  "Drop a video, a recording or a link here, or press Ctrl+O / Ctrl+L.": "Largue aqui um vídeo, uma gravação ou uma ligação, ou prima Ctrl+O / Ctrl+L.",
  "Reading the file…": "A ler o ficheiro…", "Extracting the sound…": "A extrair o som…",
  "Loading the model %1 (downloaded once)…": "A carregar o modelo %1 (descarregado uma vez)…",
  "Transcribing… %1 %": "A transcrever… %1 %", "Text ready: %1 words": "Texto pronto: %1 palavras",
  "Text read from the subtitles: %1 words": "Texto tirado das legendas: %1 palavras",
  "The transcription needs faster-whisper: pip install faster-whisper — or open a subtitle file.": "A transcrição precisa do faster-whisper: pip install faster-whisper — ou abra um ficheiro de legendas.",
  "ffmpeg was not found. Install it (ffmpeg.org) and start again.": "O ffmpeg não foi encontrado. Instale-o (ffmpeg.org) e abra de novo.",
  "This file cannot be read.": "Este ficheiro não pode ser lido.", "No speech was found in this file.": "Não há fala neste ficheiro.",
  "No subtitle in this file.": "Não há legendas neste ficheiro.",
  "Drag over the text to highlight what you keep.": "Arraste sobre o texto para marcar o que fica.",
  "Drag over the text to strike what you remove: the edit keeps all the rest.": "Arraste sobre o texto para riscar o que sai: a montagem guarda tudo o resto.",
  "A click on a word plays from there. A click on a passage without words marks it. A double click takes the whole sentence. For a long passage, click its first word, then its last one with Shift held.":
    "Um clique numa palavra reproduz a partir daí. Um clique numa passagem sem palavras marca-a. Um duplo clique toma a frase inteira. Para uma passagem longa, clique na primeira palavra e depois na última com Shift premido.",
  "Nothing highlighted": "Nada marcado", "Nothing struck": "Nada riscado", "Nothing is left": "Não resta nada",
  "Edit of %1": "Montagem de %1", "%1 passage": "%1 passagem", "%1 passages": "%1 passagens", "out of %1": "de %1",
  "%1 cut": "%1 corte", "%1 cuts": "%1 cortes", "%1 less out of %2": "%1 a menos de %2",
  "Without words": "Sem palavras", "Start": "Início", "End": "Fim", "without words": "sem palavras",
  "Export the edit": "Exportar a montagem", "Piece %1 of %2": "Passagem %1 de %2", "Joining": "Junção",
  "Taking the passages": "A recolher as passagens", "Encoding": "Codificação", "Exporting… %1 %": "A exportar… %1 %",
  "Done: %1 (%2). Beside it, the log of the cuts (.txt) and the edit list (.edl).": "Feito: %1 (%2). Ao lado, o registo dos cortes (.txt) e a lista de montagem (.edl).",
  "The edit could not be made: %1": "A montagem não pôde ser produzida: %1", "Cancelled.": "Cancelado.",
  "white on black / black on white": "branco sobre preto / preto sobre branco", "larger text": "texto maior", "smaller text": "texto menor",
  "remove": "retirar", "keep": "guardar", "sound": "som", "video": "vídeo",
  "LOG OF THE CUTS": "REGISTO DOS CORTES", "Original file": "Ficheiro original", "duration %1": "duração %1",
  "Edit produced": "Montagem produzida", "duration %1, on %2": "duração %1, em %2", "Setting": "Definição",
  "the marked text is removed, all the rest is kept": "o texto marcado é retirado, tudo o resto fica", "the marked text is kept": "o texto marcado fica",
  "Fade asked": "Fundido pedido", "(the sound fade never bites a word: it is shorter when the cut is tight)": "(o fundido do som nunca morde uma palavra: é mais curto quando o corte é apertado)",
  "Picture": "Imagem", "straight cuts": "cortes secos", "fade to black where %1 or more is removed, straight cut elsewhere": "fundido para preto onde sai %1 ou mais, corte seco no resto",
  "Pieces kept": "Passagens guardadas", "Removed in all": "Retirado no total", "Times are hours:minutes:seconds.thousandths.": "Os instantes estão em horas:minutos:segundos.milésimos.",
  "REMOVED": "RETIRADO", "(without words)": "(sem palavras)", "PIECE %1": "PASSAGEM %1", "in the original": "no original", "in the edit": "na montagem",
  "fade in %1, fade out %2": "entrada %1, saída %2", "fade in": "entrada em fundido", "straight in": "entrada seca",
  "fade out to black": "saída em fundido para preto", "straight out": "saída seca", "straight in and out": "entrada e saída secas", "text": "texto",
  "[%1 without words]": "[%1 sem palavras]", "Shortcuts: Space play/pause · ← → 5 s · S highlight · G erase · Ctrl+Z undo · Ctrl+Y redo · Ctrl+T ink · Ctrl+= Ctrl+- text size":
    "Atalhos: Espaço reproduzir/pausa · ← → 5 s · S marcador · G borracha · Ctrl+Z anular · Ctrl+Y refazer · Ctrl+T tinta · Ctrl+= Ctrl+- tamanho do texto",
  "The sound of this file cannot be played here, the text still works and the export too.": "O som deste ficheiro não pode ser reproduzido aqui; o texto e a exportação funcionam na mesma.",
  "subtitles": "legendas", "transcription": "transcrição",
 },
 "ru": {
  "Cancel": "Отмена",
  "Choose a video or a recording, or give the address of a video online. The text appears, you highlight what you keep, or what you remove, and the edit is made for you.": "Выберите видео или запись, или укажите адрес видео в сети. Появится текст, вы выделяете то, что оставить, или то, что убрать, и монтаж делается сам.",
  "File location, or address of a video (YouTube, X…)": "Расположение файла или адрес видео (YouTube, X…)",
  "Browse…": "Обзор…",
  "Open": "Открыть",
  "Spoken language": "Язык речи",
  "Resume": "Продолжить",
  "Give a file or an address.": "Укажите файл или адрес.",
  "Video": "Видео",
  "Recording": "Запись",
  "I highlight": "Я выделяю",
  "what I keep": "то, что оставляю",
  "what I cut": "то, что убираю",
  "Highlighter": "Маркер",
  "Eraser": "Ластик",
  "Undo": "Отменить",
  "Redo": "Вернуть",
  "Another file": "Другой файл",
  "Text": "Текст",
  "Read": "Читать",
  "Edit": "Монтаж",
  "▶ Watch the edit": "▶ Смотреть монтаж",
  "▶ Listen to the edit": "▶ Слушать монтаж",
  "■ Stop": "■ Стоп",
  "Clear all": "Очистить всё",
  "Strike the silence": "Вычеркнуть тишину",
  "Strike the %1 silences": "Вычеркнуть паузы (%1)",
  "Produce": "Создать",
  "Fade at each cut": "Затухание на каждом стыке",
  "None": "Нет",
  "Brief (0.2 s)": "Короткое (0,2 с)",
  "Normal (0.5 s)": "Обычное (0,5 с)",
  "Slow (1 s)": "Медленное (1 с)",
  "Very slow (1.5 s)": "Очень медленное (1,5 с)",
  "A video (MP4)": "Видео (MP4)",
  "The sound alone (%1)": "Только звук (%1)",
  "Produce the edit": "Создать монтаж",
  "Stop": "Стоп",
  "Edit finished": "Монтаж готов",
  "Watch": "Смотреть",
  "Listen": "Слушать",
  "Open the folder": "Открыть папку",
  "Close": "Закрыть",
  "The transcription failed.": "Расшифровка не удалась.",
  "Start the transcription again": "Начать расшифровку заново",
  "Open subtitles…": "Открыть субтитры…",
  "Transcribe again…": "Расшифровать заново…",
  "Transcribe": "Расшифровать",
  "Save the text…": "Сохранить текст…",
  "Installing the transcription (faster-whisper, once, about 300 MB)…": "Установка расшифровки (faster-whisper, один раз, около 300 МБ)…",
  "The transcription could not be installed: %1": "Не удалось установить расшифровку: %1",
  "Shortcuts: Space play/pause · ← → 5 s · S highlighter · G eraser · Ctrl+Z undo · Ctrl+R read · Ctrl+= Ctrl+- text size · Ctrl+O file · Ctrl+L address": "Клавиши: Пробел воспроизведение/пауза · ← → 5 с · S маркер · G ластик · Ctrl+Z отменить · Ctrl+R читать · Ctrl+= Ctrl+- размер текста · Ctrl+O файл · Ctrl+L адрес",
  "Transcribing…": "Идёт расшифровка…",
  "Beside it: the log of the cuts (.txt) and the edit list (.edl).": "Рядом: журнал склеек (.txt) и монтажный лист (.edl).",
  "Looking for the words in the sound…": "Поиск слов в звуке…",
  "auto": "авто",
  "address…": "адрес…",
  "Open an address": "Открыть адрес",
  "The address of a video (YouTube, X…). It is fetched here, with its subtitles when the site has them.": "Адрес видео (YouTube, X…). Оно загружается сюда вместе с субтитрами, если они есть на сайте.",
  "Fetching yt-dlp (once)…": "Загрузка yt-dlp (один раз)…",
  "Updating yt-dlp…": "Обновление yt-dlp…",
  "Downloading…": "Загрузка…",
  "Downloading… %1 %": "Загрузка… %1 %",
  "Joining the picture and the sound…": "Объединение изображения и звука…",
  "The download failed: %1": "Загрузка не удалась: %1",
  "no video in the answer": "в ответе нет видео",
  "yt-dlp could not be fetched (no network?): %1": "Не удалось загрузить yt-dlp (нет сети?): %1",
  "Downloaded: %1": "Загружено: %1",
  "Ctrl+L address": "Ctrl+L адрес",
  "read": "читать",
  "edit": "монтаж",
  "save the text…": "сохранить текст…",
  "copy the text": "копировать текст",
  "Save the text": "Сохранить текст",
  "Text (*.txt)": "Текст (*.txt)",
  "Text saved: %1": "Текст сохранён: %1",
  "Text copied.": "Текст скопирован.",
  "speed": "скорость",
  "open…": "открыть…", "subtitles…": "субтитры…", "transcribe": "расшифровать", "stop": "стоп",
  "highlight": "маркер", "erase": "ластик", "I highlight what I keep": "выделяю то, что остаётся",
  "I highlight what I cut": "выделяю то, что вырезаю", "fade": "затухание", "s": "с", "none": "нет",
  "fade the picture to black": "затемнять изображение", "export…": "экспорт…", "preview the edit": "прослушать монтаж",
  "stop the preview": "остановить прослушивание", "undo": "отменить", "redo": "вернуть", "language": "язык", "model": "модель",
  "Open a video or a recording": "Открыть видео или запись",
  "Video and audio files": "Видео- и аудиофайлы", "Subtitles (*.srt)": "Субтитры (*.srt)",
  "Open the subtitles of this file": "Открыть субтитры этого файла",
  "Drop a video, a recording or a link here, or press Ctrl+O / Ctrl+L.": "Перетащите сюда видео, запись или ссылку, или нажмите Ctrl+O / Ctrl+L.",
  "Reading the file…": "Чтение файла…", "Extracting the sound…": "Извлечение звука…",
  "Loading the model %1 (downloaded once)…": "Загрузка модели %1 (скачивается один раз)…",
  "Transcribing… %1 %": "Расшифровка… %1 %", "Text ready: %1 words": "Текст готов: %1 слов",
  "Text read from the subtitles: %1 words": "Текст взят из субтитров: %1 слов",
  "The transcription needs faster-whisper: pip install faster-whisper — or open a subtitle file.": "Для расшифровки нужен faster-whisper: pip install faster-whisper — или откройте файл субтитров.",
  "ffmpeg was not found. Install it (ffmpeg.org) and start again.": "ffmpeg не найден. Установите его (ffmpeg.org) и запустите снова.",
  "This file cannot be read.": "Этот файл не читается.", "No speech was found in this file.": "В этом файле нет речи.",
  "No subtitle in this file.": "В этом файле нет субтитров.",
  "Drag over the text to highlight what you keep.": "Проведите по тексту, чтобы выделить то, что остаётся.",
  "Drag over the text to strike what you remove: the edit keeps all the rest.": "Проведите по тексту, чтобы зачеркнуть то, что вырезается: остальное остаётся.",
  "A click on a word plays from there. A click on a passage without words marks it. A double click takes the whole sentence. For a long passage, click its first word, then its last one with Shift held.":
    "Клик по слову запускает воспроизведение с этого места. Клик по отрезку без слов отмечает его. Двойной клик берёт всё предложение. Для длинного отрезка кликните первое слово, затем последнее с зажатым Shift.",
  "Nothing highlighted": "Ничего не выделено", "Nothing struck": "Ничего не зачёркнуто", "Nothing is left": "Ничего не остаётся",
  "Edit of %1": "Монтаж %1", "%1 passage": "%1 отрезок", "%1 passages": "отрезков: %1", "out of %1": "из %1",
  "%1 cut": "%1 вырезка", "%1 cuts": "вырезок: %1", "%1 less out of %2": "минус %1 из %2",
  "Without words": "Без слов", "Start": "Начало", "End": "Конец", "without words": "без слов",
  "Export the edit": "Экспортировать монтаж", "Piece %1 of %2": "Отрезок %1 из %2", "Joining": "Сборка",
  "Taking the passages": "Извлечение отрезков", "Encoding": "Кодирование", "Exporting… %1 %": "Экспорт… %1 %",
  "Done: %1 (%2). Beside it, the log of the cuts (.txt) and the edit list (.edl).": "Готово: %1 (%2). Рядом журнал вырезок (.txt) и монтажный лист (.edl).",
  "The edit could not be made: %1": "Монтаж не удался: %1", "Cancelled.": "Отменено.",
  "white on black / black on white": "белым по чёрному / чёрным по белому", "larger text": "крупнее", "smaller text": "мельче",
  "remove": "убрать", "keep": "оставить", "sound": "звук", "video": "видео",
  "LOG OF THE CUTS": "ЖУРНАЛ ВЫРЕЗОК", "Original file": "Исходный файл", "duration %1": "длительность %1",
  "Edit produced": "Готовый монтаж", "duration %1, on %2": "длительность %1, %2", "Setting": "Настройка",
  "the marked text is removed, all the rest is kept": "отмеченный текст вырезан, остальное оставлено", "the marked text is kept": "отмеченный текст оставлен",
  "Fade asked": "Запрошенное затухание", "(the sound fade never bites a word: it is shorter when the cut is tight)": "(затухание звука никогда не задевает слово: оно короче при тесной вырезке)",
  "Picture": "Изображение", "straight cuts": "резкие склейки", "fade to black where %1 or more is removed, straight cut elsewhere": "затемнение там, где вырезано %1 и больше, иначе резкая склейка",
  "Pieces kept": "Оставленных отрезков", "Removed in all": "Вырезано всего", "Times are hours:minutes:seconds.thousandths.": "Время в часах:минутах:секундах.тысячных.",
  "REMOVED": "ВЫРЕЗАНО", "(without words)": "(без слов)", "PIECE %1": "ОТРЕЗОК %1", "in the original": "в оригинале", "in the edit": "в монтаже",
  "fade in %1, fade out %2": "нарастание %1, затухание %2", "fade in": "вход с нарастанием", "straight in": "резкий вход",
  "fade out to black": "выход с затемнением", "straight out": "резкий выход", "straight in and out": "резкие вход и выход", "text": "текст",
  "[%1 without words]": "[%1 без слов]", "Shortcuts: Space play/pause · ← → 5 s · S highlight · G erase · Ctrl+Z undo · Ctrl+Y redo · Ctrl+T ink · Ctrl+= Ctrl+- text size":
    "Клавиши: Пробел пуск/пауза · ← → 5 с · S маркер · G ластик · Ctrl+Z отменить · Ctrl+Y вернуть · Ctrl+T цвет · Ctrl+= Ctrl+- размер текста",
  "The sound of this file cannot be played here, the text still works and the export too.": "Звук этого файла здесь не воспроизводится; текст и экспорт всё равно работают.",
  "subtitles": "субтитры", "transcription": "расшифровка",
 },
}

# The strings of 1.3.0: translation, subtitles, project files
_TR_MORE = {
 "fr": {
  "Translate…": "Traduire…", "Translation": "Traduction", "Original": "Original", "From": "De", "Into": "Vers",
  "Translation by": "Traduction par", "On this computer (Ollama)": "Sur cet ordinateur (Ollama)", "Claude (API)": "Claude (API)",
  "Ollama model": "Modèle Ollama",
  "Context for the translator: names, subject, register (optional)": "Contexte pour le traducteur : noms, sujet, registre (facultatif)",
  "Proofreading pass (a second reading by the model)": "Passe de relecture (une seconde lecture par le modèle)",
  "Translating into %1…": "Traduction en %1…", "The translation failed: %1": "La traduction a échoué : %1",
  "Translated: %1 words": "Traduit : %1 mots", "The translation came back empty.": "La traduction est revenue vide.",
  "The traduction toolkit does the translation (traduire.py). It was not found: give its folder, or install it from %1.":
    "La traduction est faite par le traduction toolkit (traduire.py). Il n'a pas été trouvé : indiquez son dossier, ou installez-le depuis %1.",
  "Folder of the traduction toolkit": "Dossier du traduction toolkit", "traduire.py is not in this folder.": "traduire.py n'est pas dans ce dossier.",
  "Same as the source language.": "C'est la langue d'origine.",
  "ANTHROPIC_API_KEY is not set.": "ANTHROPIC_API_KEY n'est pas définie.", "Ollama does not answer at %1.": "Ollama ne répond pas à %1.",
  "Analysing the text…": "Analyse du texte…", "Translating…": "Traduction…", "Translating… %1 of %2": "Traduction… %1 sur %2",
  "Proofreading…": "Relecture…", "Checking the consistency…": "Vérification de la cohérence…", "Checking the glossary…": "Vérification du glossaire…",
  "Save the subtitles…": "Enregistrer les sous-titres…", "Save the subtitles": "Enregistrer les sous-titres",
  "Subtitles saved: %1": "Sous-titres enregistrés : %1", "Making the subtitles…": "Préparation des sous-titres…",
  "Subtitles": "Sous-titres", "In the picture: %1": "Dans l'image : %1",
  "Subtitle files beside the edit (.srt)": "Fichiers de sous-titres à côté du montage (.srt)",
  "Project": "Projet", "Save the project": "Enregistrer le projet", "Save the project…": "Enregistrer le projet…",
  "Save the project as…": "Enregistrer le projet sous…", "Open a project…": "Ouvrir un projet…", "Open a project": "Ouvrir un projet",
  "Project (*.rve.json)": "Projet (*.rve.json)", "Project saved: %1": "Projet enregistré : %1",
  "The file of this project was not found: %1": "Le fichier de ce projet est introuvable : %1", "This is not a project file.": "Ce n'est pas un fichier de projet.",
  "Beside it: the log of the cuts (.txt), the edit list (.edl) and the subtitles (.srt).": "À côté : le journal des coupes (.txt), la liste de montage (.edl) et les sous-titres (.srt).",
 },
 "de": {
  "Translate…": "Übersetzen…", "Translation": "Übersetzung", "Original": "Original", "From": "Von", "Into": "Nach",
  "Translation by": "Übersetzung durch", "On this computer (Ollama)": "Auf diesem Rechner (Ollama)", "Claude (API)": "Claude (API)",
  "Ollama model": "Ollama-Modell",
  "Context for the translator: names, subject, register (optional)": "Kontext für den Übersetzer: Namen, Thema, Register (optional)",
  "Proofreading pass (a second reading by the model)": "Korrekturdurchgang (ein zweites Lesen durch das Modell)",
  "Translating into %1…": "Übersetzung nach %1…", "The translation failed: %1": "Die Übersetzung ist fehlgeschlagen: %1",
  "Translated: %1 words": "Übersetzt: %1 Wörter", "The translation came back empty.": "Die Übersetzung kam leer zurück.",
  "The traduction toolkit does the translation (traduire.py). It was not found: give its folder, or install it from %1.":
    "Die Übersetzung macht das traduction toolkit (traduire.py). Es wurde nicht gefunden: geben Sie seinen Ordner an, oder installieren Sie es von %1.",
  "Folder of the traduction toolkit": "Ordner des traduction toolkit", "traduire.py is not in this folder.": "traduire.py liegt nicht in diesem Ordner.",
  "Same as the source language.": "Das ist die Ausgangssprache.",
  "ANTHROPIC_API_KEY is not set.": "ANTHROPIC_API_KEY ist nicht gesetzt.", "Ollama does not answer at %1.": "Ollama antwortet nicht unter %1.",
  "Analysing the text…": "Der Text wird analysiert…", "Translating…": "Übersetzung…", "Translating… %1 of %2": "Übersetzung… %1 von %2",
  "Proofreading…": "Korrekturlesen…", "Checking the consistency…": "Prüfung der Einheitlichkeit…", "Checking the glossary…": "Prüfung des Glossars…",
  "Save the subtitles…": "Untertitel speichern…", "Save the subtitles": "Untertitel speichern",
  "Subtitles saved: %1": "Untertitel gespeichert: %1", "Making the subtitles…": "Untertitel werden erstellt…",
  "Subtitles": "Untertitel", "In the picture: %1": "Im Bild: %1",
  "Subtitle files beside the edit (.srt)": "Untertiteldateien neben dem Schnitt (.srt)",
  "Project": "Projekt", "Save the project": "Projekt speichern", "Save the project…": "Projekt speichern…",
  "Save the project as…": "Projekt speichern unter…", "Open a project…": "Ein Projekt öffnen…", "Open a project": "Ein Projekt öffnen",
  "Project (*.rve.json)": "Projekt (*.rve.json)", "Project saved: %1": "Projekt gespeichert: %1",
  "The file of this project was not found: %1": "Die Datei dieses Projekts wurde nicht gefunden: %1", "This is not a project file.": "Das ist keine Projektdatei.",
  "Beside it: the log of the cuts (.txt), the edit list (.edl) and the subtitles (.srt).": "Daneben: das Protokoll der Schnitte (.txt), die Schnittliste (.edl) und die Untertitel (.srt).",
 },
 "es": {
  "Translate…": "Traducir…", "Translation": "Traducción", "Original": "Original", "From": "De", "Into": "A",
  "Translation by": "Traducción por", "On this computer (Ollama)": "En este ordenador (Ollama)", "Claude (API)": "Claude (API)",
  "Ollama model": "Modelo Ollama",
  "Context for the translator: names, subject, register (optional)": "Contexto para el traductor: nombres, tema, registro (opcional)",
  "Proofreading pass (a second reading by the model)": "Pasada de relectura (una segunda lectura por el modelo)",
  "Translating into %1…": "Traduciendo al %1…", "The translation failed: %1": "La traducción ha fallado: %1",
  "Translated: %1 words": "Traducido: %1 palabras", "The translation came back empty.": "La traducción ha vuelto vacía.",
  "The traduction toolkit does the translation (traduire.py). It was not found: give its folder, or install it from %1.":
    "La traducción la hace el traduction toolkit (traduire.py). No se ha encontrado: indique su carpeta, o instálelo desde %1.",
  "Folder of the traduction toolkit": "Carpeta del traduction toolkit", "traduire.py is not in this folder.": "traduire.py no está en esta carpeta.",
  "Same as the source language.": "Es la lengua de origen.",
  "ANTHROPIC_API_KEY is not set.": "ANTHROPIC_API_KEY no está definida.", "Ollama does not answer at %1.": "Ollama no responde en %1.",
  "Analysing the text…": "Analizando el texto…", "Translating…": "Traduciendo…", "Translating… %1 of %2": "Traduciendo… %1 de %2",
  "Proofreading…": "Relectura…", "Checking the consistency…": "Comprobando la coherencia…", "Checking the glossary…": "Comprobando el glosario…",
  "Save the subtitles…": "Guardar los subtítulos…", "Save the subtitles": "Guardar los subtítulos",
  "Subtitles saved: %1": "Subtítulos guardados: %1", "Making the subtitles…": "Preparando los subtítulos…",
  "Subtitles": "Subtítulos", "In the picture: %1": "En la imagen: %1",
  "Subtitle files beside the edit (.srt)": "Archivos de subtítulos junto al montaje (.srt)",
  "Project": "Proyecto", "Save the project": "Guardar el proyecto", "Save the project…": "Guardar el proyecto…",
  "Save the project as…": "Guardar el proyecto como…", "Open a project…": "Abrir un proyecto…", "Open a project": "Abrir un proyecto",
  "Project (*.rve.json)": "Proyecto (*.rve.json)", "Project saved: %1": "Proyecto guardado: %1",
  "The file of this project was not found: %1": "No se encuentra el archivo de este proyecto: %1", "This is not a project file.": "Esto no es un archivo de proyecto.",
  "Beside it: the log of the cuts (.txt), the edit list (.edl) and the subtitles (.srt).": "Al lado: el registro de los cortes (.txt), la lista de montaje (.edl) y los subtítulos (.srt).",
 },
 "pt": {
  "Translate…": "Traduzir…", "Translation": "Tradução", "Original": "Original", "From": "De", "Into": "Para",
  "Translation by": "Tradução por", "On this computer (Ollama)": "Neste computador (Ollama)", "Claude (API)": "Claude (API)",
  "Ollama model": "Modelo Ollama",
  "Context for the translator: names, subject, register (optional)": "Contexto para o tradutor: nomes, assunto, registo (opcional)",
  "Proofreading pass (a second reading by the model)": "Passagem de revisão (uma segunda leitura pelo modelo)",
  "Translating into %1…": "A traduzir para %1…", "The translation failed: %1": "A tradução falhou: %1",
  "Translated: %1 words": "Traduzido: %1 palavras", "The translation came back empty.": "A tradução voltou vazia.",
  "The traduction toolkit does the translation (traduire.py). It was not found: give its folder, or install it from %1.":
    "A tradução é feita pelo traduction toolkit (traduire.py). Não foi encontrado: indique a sua pasta, ou instale-o a partir de %1.",
  "Folder of the traduction toolkit": "Pasta do traduction toolkit", "traduire.py is not in this folder.": "traduire.py não está nesta pasta.",
  "Same as the source language.": "É a língua de origem.",
  "ANTHROPIC_API_KEY is not set.": "ANTHROPIC_API_KEY não está definida.", "Ollama does not answer at %1.": "Ollama não responde em %1.",
  "Analysing the text…": "A analisar o texto…", "Translating…": "A traduzir…", "Translating… %1 of %2": "A traduzir… %1 de %2",
  "Proofreading…": "Revisão…", "Checking the consistency…": "A verificar a coerência…", "Checking the glossary…": "A verificar o glossário…",
  "Save the subtitles…": "Guardar as legendas…", "Save the subtitles": "Guardar as legendas",
  "Subtitles saved: %1": "Legendas guardadas: %1", "Making the subtitles…": "A preparar as legendas…",
  "Subtitles": "Legendas", "In the picture: %1": "Na imagem: %1",
  "Subtitle files beside the edit (.srt)": "Ficheiros de legendas ao lado da montagem (.srt)",
  "Project": "Projeto", "Save the project": "Guardar o projeto", "Save the project…": "Guardar o projeto…",
  "Save the project as…": "Guardar o projeto como…", "Open a project…": "Abrir um projeto…", "Open a project": "Abrir um projeto",
  "Project (*.rve.json)": "Projeto (*.rve.json)", "Project saved: %1": "Projeto guardado: %1",
  "The file of this project was not found: %1": "O ficheiro deste projeto não foi encontrado: %1", "This is not a project file.": "Isto não é um ficheiro de projeto.",
  "Beside it: the log of the cuts (.txt), the edit list (.edl) and the subtitles (.srt).": "Ao lado: o registo dos cortes (.txt), a lista de montagem (.edl) e as legendas (.srt).",
 },
 "ru": {
  "Translate…": "Перевести…", "Translation": "Перевод", "Original": "Оригинал", "From": "С", "Into": "На",
  "Translation by": "Переводчик", "On this computer (Ollama)": "На этом компьютере (Ollama)", "Claude (API)": "Claude (API)",
  "Ollama model": "Модель Ollama",
  "Context for the translator: names, subject, register (optional)": "Контекст для переводчика: имена, тема, стиль (необязательно)",
  "Proofreading pass (a second reading by the model)": "Проход вычитки (второе чтение моделью)",
  "Translating into %1…": "Перевод на %1…", "The translation failed: %1": "Перевод не удался: %1",
  "Translated: %1 words": "Переведено: %1 слов", "The translation came back empty.": "Перевод вернулся пустым.",
  "The traduction toolkit does the translation (traduire.py). It was not found: give its folder, or install it from %1.":
    "Перевод выполняет traduction toolkit (traduire.py). Он не найден: укажите его папку или установите с %1.",
  "Folder of the traduction toolkit": "Папка traduction toolkit", "traduire.py is not in this folder.": "В этой папке нет traduire.py.",
  "Same as the source language.": "Это язык оригинала.",
  "ANTHROPIC_API_KEY is not set.": "ANTHROPIC_API_KEY не задан.", "Ollama does not answer at %1.": "Ollama не отвечает по адресу %1.",
  "Analysing the text…": "Анализ текста…", "Translating…": "Перевод…", "Translating… %1 of %2": "Перевод… %1 из %2",
  "Proofreading…": "Вычитка…", "Checking the consistency…": "Проверка согласованности…", "Checking the glossary…": "Проверка глоссария…",
  "Save the subtitles…": "Сохранить субтитры…", "Save the subtitles": "Сохранить субтитры",
  "Subtitles saved: %1": "Субтитры сохранены: %1", "Making the subtitles…": "Подготовка субтитров…",
  "Subtitles": "Субтитры", "In the picture: %1": "В кадре: %1",
  "Subtitle files beside the edit (.srt)": "Файлы субтитров рядом с монтажом (.srt)",
  "Project": "Проект", "Save the project": "Сохранить проект", "Save the project…": "Сохранить проект…",
  "Save the project as…": "Сохранить проект как…", "Open a project…": "Открыть проект…", "Open a project": "Открыть проект",
  "Project (*.rve.json)": "Проект (*.rve.json)", "Project saved: %1": "Проект сохранён: %1",
  "The file of this project was not found: %1": "Файл этого проекта не найден: %1", "This is not a project file.": "Это не файл проекта.",
  "Beside it: the log of the cuts (.txt), the edit list (.edl) and the subtitles (.srt).": "Рядом: журнал склеек (.txt), монтажный лист (.edl) и субтитры (.srt).",
 },
}
for _code, _more in _TR_MORE.items():
    _TR.setdefault(_code, {}).update(_more)

# The strings of 1.4.0: the subtitle editor
_TR_SUBS = {
 "fr": {
  "Re-cut from the text": "Redécouper depuis le texte",
  "The subtitles were edited by hand. Cut them again from the text and lose these changes?":
    "Les sous-titres ont été retouchés à la main. Les redécouper depuis le texte et perdre ces retouches ?",
  "Shorten what reads too fast…": "Raccourcir ce qui se lit trop vite…", "Shorten": "Raccourcir",
  "The model rereads these subtitles and shortens the ones that read too fast, with the proofreading pass of traduire.py.":
    "Le modèle relit ces sous-titres et raccourcit ceux qui se lisent trop vite, avec la passe de relecture de traduire.py.",
  "The subtitles that read too fast (%1)": "Les sous-titres qui se lisent trop vite (%1)", "The selected subtitles (%1)": "Les sous-titres sélectionnés (%1)",
  "All the subtitles (%1)": "Tous les sous-titres (%1)", "Proofreading by": "Relecture par", "Nothing to shorten.": "Rien à raccourcir.",
  "Proofreading… %1 of %2": "Relecture… %1 sur %2", "Shortened: %1 subtitles": "Raccourcis : %1 sous-titres",
  "The model changed nothing.": "Le modèle n'a rien changé.", "The shortening failed: %1": "Le raccourcissement a échoué : %1",
  "Split": "Scinder", "Merge with the next": "Fusionner avec le suivant", "Delete": "Supprimer",
  "Start": "Début", "End": "Fin", "Text": "Texte", "here": "ici", "Start here": "Début ici", "End here": "Fin ici",
  "Too fast: %1 characters a second (the limit is %2)": "Trop rapide : %1 caractères par seconde (la limite est %2)",
  "A line of %1 characters (the limit is %2)": "Une ligne de %1 caractères (la limite est %2)", "%1 lines": "%1 lignes",
  "Longer than %1 s": "Plus long que %1 s", "Shorter than %1 s": "Plus court que %1 s", "Overlaps the next subtitle": "Chevauche le sous-titre suivant",
  "%1 subtitles": "%1 sous-titres", "edited by hand": "retouchés à la main",
  "Enter splits the subtitle at the cursor, Shift+Enter breaks the line, Tab goes to the next one. A click on a subtitle plays from there; the buttons move its edges by a tenth of a second, or to the instant being played.":
    "Entrée scinde le sous-titre au curseur, Maj+Entrée passe à la ligne, Tab passe au suivant. Un clic sur un sous-titre lit à partir de là ; les boutons déplacent ses bords d'un dixième de seconde, ou à l'instant en cours de lecture.",
  "Fast: %1 characters a second (comfortable up to %2)": "Rapide : %1 caractères par seconde (confortable jusqu'à %2)",
  "characters a second": "caractères par seconde",
  "Analysis of the content (names, glossary) by Claude rather than the local model": "Analyse du contenu (noms, glossaire) par Claude plutôt que par le modèle local",
 },
 "de": {
  "Re-cut from the text": "Aus dem Text neu schneiden",
  "The subtitles were edited by hand. Cut them again from the text and lose these changes?":
    "Die Untertitel wurden von Hand bearbeitet. Aus dem Text neu schneiden und diese Änderungen verlieren?",
  "Shorten what reads too fast…": "Kürzen, was zu schnell zu lesen ist…", "Shorten": "Kürzen",
  "The model rereads these subtitles and shortens the ones that read too fast, with the proofreading pass of traduire.py.":
    "Das Modell liest diese Untertitel erneut und kürzt die zu schnellen, mit dem Korrekturdurchgang von traduire.py.",
  "The subtitles that read too fast (%1)": "Die zu schnellen Untertitel (%1)", "The selected subtitles (%1)": "Die ausgewählten Untertitel (%1)",
  "All the subtitles (%1)": "Alle Untertitel (%1)", "Proofreading by": "Korrektur durch", "Nothing to shorten.": "Nichts zu kürzen.",
  "Proofreading… %1 of %2": "Korrektur… %1 von %2", "Shortened: %1 subtitles": "Gekürzt: %1 Untertitel",
  "The model changed nothing.": "Das Modell hat nichts geändert.", "The shortening failed: %1": "Das Kürzen ist fehlgeschlagen: %1",
  "Split": "Teilen", "Merge with the next": "Mit dem nächsten verbinden", "Delete": "Löschen",
  "Start": "Anfang", "End": "Ende", "Text": "Text", "here": "hier", "Start here": "Anfang hier", "End here": "Ende hier",
  "Too fast: %1 characters a second (the limit is %2)": "Zu schnell: %1 Zeichen pro Sekunde (Grenze %2)",
  "A line of %1 characters (the limit is %2)": "Eine Zeile mit %1 Zeichen (Grenze %2)", "%1 lines": "%1 Zeilen",
  "Longer than %1 s": "Länger als %1 s", "Shorter than %1 s": "Kürzer als %1 s", "Overlaps the next subtitle": "Überschneidet den nächsten Untertitel",
  "%1 subtitles": "%1 Untertitel", "edited by hand": "von Hand bearbeitet",
  "Enter splits the subtitle at the cursor, Shift+Enter breaks the line, Tab goes to the next one. A click on a subtitle plays from there; the buttons move its edges by a tenth of a second, or to the instant being played.":
    "Eingabe teilt den Untertitel am Cursor, Umschalt+Eingabe bricht die Zeile um, Tab geht zum nächsten. Ein Klick auf einen Untertitel spielt von dort; die Knöpfe verschieben seine Ränder um eine Zehntelsekunde oder auf den gerade gespielten Augenblick.",
  "Fast: %1 characters a second (comfortable up to %2)": "Schnell: %1 Zeichen pro Sekunde (bequem bis %2)",
  "characters a second": "Zeichen pro Sekunde",
  "Analysis of the content (names, glossary) by Claude rather than the local model": "Analyse des Inhalts (Namen, Glossar) durch Claude statt durch das lokale Modell",
 },
 "es": {
  "Re-cut from the text": "Volver a cortar desde el texto",
  "The subtitles were edited by hand. Cut them again from the text and lose these changes?":
    "Los subtítulos fueron retocados a mano. ¿Volver a cortarlos desde el texto y perder esos retoques?",
  "Shorten what reads too fast…": "Acortar lo que se lee demasiado rápido…", "Shorten": "Acortar",
  "The model rereads these subtitles and shortens the ones that read too fast, with the proofreading pass of traduire.py.":
    "El modelo relee estos subtítulos y acorta los que se leen demasiado rápido, con la pasada de revisión de traduire.py.",
  "The subtitles that read too fast (%1)": "Los subtítulos que se leen demasiado rápido (%1)", "The selected subtitles (%1)": "Los subtítulos seleccionados (%1)",
  "All the subtitles (%1)": "Todos los subtítulos (%1)", "Proofreading by": "Revisión por", "Nothing to shorten.": "Nada que acortar.",
  "Proofreading… %1 of %2": "Revisión… %1 de %2", "Shortened: %1 subtitles": "Acortados: %1 subtítulos",
  "The model changed nothing.": "El modelo no cambió nada.", "The shortening failed: %1": "El acortamiento falló: %1",
  "Split": "Dividir", "Merge with the next": "Unir con el siguiente", "Delete": "Eliminar",
  "Start": "Inicio", "End": "Fin", "Text": "Texto", "here": "aquí", "Start here": "Inicio aquí", "End here": "Fin aquí",
  "Too fast: %1 characters a second (the limit is %2)": "Demasiado rápido: %1 caracteres por segundo (el límite es %2)",
  "A line of %1 characters (the limit is %2)": "Una línea de %1 caracteres (el límite es %2)", "%1 lines": "%1 líneas",
  "Longer than %1 s": "Más largo que %1 s", "Shorter than %1 s": "Más corto que %1 s", "Overlaps the next subtitle": "Se solapa con el subtítulo siguiente",
  "%1 subtitles": "%1 subtítulos", "edited by hand": "retocados a mano",
  "Enter splits the subtitle at the cursor, Shift+Enter breaks the line, Tab goes to the next one. A click on a subtitle plays from there; the buttons move its edges by a tenth of a second, or to the instant being played.":
    "Intro divide el subtítulo en el cursor, Mayús+Intro salta de línea, Tab pasa al siguiente. Un clic en un subtítulo reproduce desde ahí; los botones mueven sus bordes una décima de segundo, o al instante que se está reproduciendo.",
  "Fast: %1 characters a second (comfortable up to %2)": "Rápido: %1 caracteres por segundo (cómodo hasta %2)",
  "characters a second": "caracteres por segundo",
  "Analysis of the content (names, glossary) by Claude rather than the local model": "Análisis del contenido (nombres, glosario) por Claude en lugar del modelo local",
 },
 "pt": {
  "Re-cut from the text": "Voltar a cortar a partir do texto",
  "The subtitles were edited by hand. Cut them again from the text and lose these changes?":
    "As legendas foram retocadas à mão. Voltar a cortá-las a partir do texto e perder esses retoques?",
  "Shorten what reads too fast…": "Encurtar o que se lê depressa demais…", "Shorten": "Encurtar",
  "The model rereads these subtitles and shortens the ones that read too fast, with the proofreading pass of traduire.py.":
    "O modelo relê estas legendas e encurta as que se leem depressa demais, com a passagem de revisão do traduire.py.",
  "The subtitles that read too fast (%1)": "As legendas que se leem depressa demais (%1)", "The selected subtitles (%1)": "As legendas selecionadas (%1)",
  "All the subtitles (%1)": "Todas as legendas (%1)", "Proofreading by": "Revisão por", "Nothing to shorten.": "Nada a encurtar.",
  "Proofreading… %1 of %2": "Revisão… %1 de %2", "Shortened: %1 subtitles": "Encurtadas: %1 legendas",
  "The model changed nothing.": "O modelo não mudou nada.", "The shortening failed: %1": "O encurtamento falhou: %1",
  "Split": "Dividir", "Merge with the next": "Juntar à seguinte", "Delete": "Apagar",
  "Start": "Início", "End": "Fim", "Text": "Texto", "here": "aqui", "Start here": "Início aqui", "End here": "Fim aqui",
  "Too fast: %1 characters a second (the limit is %2)": "Depressa demais: %1 caracteres por segundo (o limite é %2)",
  "A line of %1 characters (the limit is %2)": "Uma linha de %1 caracteres (o limite é %2)", "%1 lines": "%1 linhas",
  "Longer than %1 s": "Mais longa que %1 s", "Shorter than %1 s": "Mais curta que %1 s", "Overlaps the next subtitle": "Sobrepõe-se à legenda seguinte",
  "%1 subtitles": "%1 legendas", "edited by hand": "retocadas à mão",
  "Enter splits the subtitle at the cursor, Shift+Enter breaks the line, Tab goes to the next one. A click on a subtitle plays from there; the buttons move its edges by a tenth of a second, or to the instant being played.":
    "Enter divide a legenda no cursor, Shift+Enter muda de linha, Tab passa à seguinte. Um clique numa legenda reproduz a partir daí; os botões movem os seus limites um décimo de segundo, ou para o instante em reprodução.",
  "Fast: %1 characters a second (comfortable up to %2)": "Rápido: %1 caracteres por segundo (confortável até %2)",
  "characters a second": "caracteres por segundo",
  "Analysis of the content (names, glossary) by Claude rather than the local model": "Análise do conteúdo (nomes, glossário) pelo Claude em vez do modelo local",
 },
 "ru": {
  "Re-cut from the text": "Нарезать заново из текста",
  "The subtitles were edited by hand. Cut them again from the text and lose these changes?":
    "Субтитры правились вручную. Нарезать их заново из текста и потерять эти правки?",
  "Shorten what reads too fast…": "Сократить то, что читается слишком быстро…", "Shorten": "Сократить",
  "The model rereads these subtitles and shortens the ones that read too fast, with the proofreading pass of traduire.py.":
    "Модель перечитывает эти субтитры и сокращает те, что читаются слишком быстро, проходом вычитки traduire.py.",
  "The subtitles that read too fast (%1)": "Субтитры, которые читаются слишком быстро (%1)", "The selected subtitles (%1)": "Выделенные субтитры (%1)",
  "All the subtitles (%1)": "Все субтитры (%1)", "Proofreading by": "Вычитка", "Nothing to shorten.": "Нечего сокращать.",
  "Proofreading… %1 of %2": "Вычитка… %1 из %2", "Shortened: %1 subtitles": "Сокращено: %1 субтитров",
  "The model changed nothing.": "Модель ничего не изменила.", "The shortening failed: %1": "Сокращение не удалось: %1",
  "Split": "Разделить", "Merge with the next": "Объединить со следующим", "Delete": "Удалить",
  "Start": "Начало", "End": "Конец", "Text": "Текст", "here": "здесь", "Start here": "Начало здесь", "End here": "Конец здесь",
  "Too fast: %1 characters a second (the limit is %2)": "Слишком быстро: %1 знаков в секунду (предел %2)",
  "A line of %1 characters (the limit is %2)": "Строка в %1 знаков (предел %2)", "%1 lines": "%1 строк",
  "Longer than %1 s": "Длиннее %1 с", "Shorter than %1 s": "Короче %1 с", "Overlaps the next subtitle": "Перекрывает следующий субтитр",
  "%1 subtitles": "%1 субтитров", "edited by hand": "правлены вручную",
  "Enter splits the subtitle at the cursor, Shift+Enter breaks the line, Tab goes to the next one. A click on a subtitle plays from there; the buttons move its edges by a tenth of a second, or to the instant being played.":
    "Enter делит субтитр по курсору, Shift+Enter переносит строку, Tab переходит к следующему. Щелчок по субтитру воспроизводит с этого места; кнопки сдвигают его границы на десятую секунды или к текущему моменту воспроизведения.",
  "Fast: %1 characters a second (comfortable up to %2)": "Быстро: %1 знаков в секунду (удобно до %2)",
  "characters a second": "знаков в секунду",
  "Analysis of the content (names, glossary) by Claude rather than the local model": "Анализ содержания (имена, глоссарий) делает Claude, а не локальная модель",
 },
}
for _code, _more in _TR_SUBS.items():
    _TR.setdefault(_code, {}).update(_more)

# The strings of 1.5.0: the square frame, the sound finished by finaliser.py
_TR_SOUND = {
 "fr": {
  "Sound": "Son", "As it is": "Tel quel", "Square (1:1), centred": "Carré (1:1), centré",
  "Improved: background noise, level": "Amélioré : bruit de fond, niveau",
  "finaliser.py of the traduction toolkit: mains hum and a steady background noise removed when there are some, the level brought to the norm. The length does not change.":
    "finaliser.py de la boîte à outils traduction : ronflette secteur et bruit de fond régulier retirés s'il y en a, niveau mis à la norme. La durée ne change pas.",
  "Improve the sound": "Améliorer le son", "Continue": "Continuer",
  "The traduction toolkit improves the sound (finaliser.py). It was not found: give its folder, or install it from %1.":
    "La boîte à outils traduction améliore le son (finaliser.py). Elle n'a pas été trouvée : indiquez son dossier, ou installez-la depuis %1.",
  "finaliser.py is not in this folder.": "finaliser.py n'est pas dans ce dossier.",
  "finaliser.py is not in the toolkit folder %1.": "finaliser.py n'est pas dans le dossier de la boîte à outils %1.",
  "the sound could not be improved (finaliser.py): %1": "le son n'a pas pu être amélioré (finaliser.py) : %1",
  "Sound: %1": "Son : %1", "Channels": "Canaux", "Hum and rumble": "Ronflette et grondements", "Analysis": "Analyse",
  "Background noise": "Bruit de fond", "Levelling": "Nivelage", "Level": "Niveau", "Fades": "Fondus", "Check": "Contrôle",
  "Frame": "Cadre", "square (1:1), the centre of the picture": "carré (1:1), le centre de l'image", "finished by finaliser.py": "finition par finaliser.py",
  "mains hum at %1 Hz removed": "ronflette secteur à %1 Hz retirée",
  "background noise reduced, by %1 dB at most": "bruit de fond réduit, de %1 dB au plus",
  "background noise reduced gently (the stronger cleaning harmed the voice)": "bruit de fond réduit doucement (le nettoyage plus fort abîmait la voix)",
  "background left as it is: cleaning it harmed the voice": "fond laissé tel quel : le nettoyer abîmait la voix",
  "background already clean (%1 dB under the voice)": "fond déjà propre (%1 dB sous la voix)",
  "background left as it is: music, not noise": "fond laissé tel quel : de la musique, pas un bruit",
  "background left as it is: it changes along the file": "fond laissé tel quel : il change au fil du fichier",
  "uneven voice levels evened out, slowly": "niveaux de voix inégaux égalisés, lentement",
  "level %1 dB": "niveau %1 dB", "%1 dB taken from the peaks alone": "%1 dB retirés aux seules crêtes",
  "voice quality %1 → %2 (DNSMOS, out of 5)": "qualité de la voix %1 → %2 (DNSMOS, sur 5)",
 },
 "de": {
  "Sound": "Ton", "As it is": "Wie er ist", "Square (1:1), centred": "Quadrat (1:1), zentriert",
  "Improved: background noise, level": "Verbessert: Hintergrundrauschen, Pegel",
  "finaliser.py of the traduction toolkit: mains hum and a steady background noise removed when there are some, the level brought to the norm. The length does not change.":
    "finaliser.py des traduction-Toolkits: Netzbrummen und ein gleichmäßiges Hintergrundrauschen werden entfernt, falls vorhanden, der Pegel auf die Norm gebracht. Die Länge ändert sich nicht.",
  "Improve the sound": "Ton verbessern", "Continue": "Weiter",
  "The traduction toolkit improves the sound (finaliser.py). It was not found: give its folder, or install it from %1.":
    "Das traduction-Toolkit verbessert den Ton (finaliser.py). Es wurde nicht gefunden: Geben Sie seinen Ordner an, oder installieren Sie es von %1.",
  "finaliser.py is not in this folder.": "finaliser.py ist nicht in diesem Ordner.",
  "finaliser.py is not in the toolkit folder %1.": "finaliser.py ist nicht im Toolkit-Ordner %1.",
  "the sound could not be improved (finaliser.py): %1": "der Ton konnte nicht verbessert werden (finaliser.py): %1",
  "Sound: %1": "Ton: %1", "Channels": "Kanäle", "Hum and rumble": "Brummen und Rumpeln", "Analysis": "Analyse",
  "Background noise": "Hintergrundrauschen", "Levelling": "Angleichen", "Level": "Pegel", "Fades": "Blenden", "Check": "Prüfung",
  "Frame": "Bildausschnitt", "square (1:1), the centre of the picture": "Quadrat (1:1), die Bildmitte", "finished by finaliser.py": "Nachbearbeitung durch finaliser.py",
  "mains hum at %1 Hz removed": "Netzbrummen bei %1 Hz entfernt",
  "background noise reduced, by %1 dB at most": "Hintergrundrauschen um höchstens %1 dB verringert",
  "background noise reduced gently (the stronger cleaning harmed the voice)": "Hintergrundrauschen sanft verringert (die stärkere Reinigung schadete der Stimme)",
  "background left as it is: cleaning it harmed the voice": "Hintergrund belassen: die Reinigung schadete der Stimme",
  "background already clean (%1 dB under the voice)": "Hintergrund bereits sauber (%1 dB unter der Stimme)",
  "background left as it is: music, not noise": "Hintergrund belassen: Musik, kein Rauschen",
  "background left as it is: it changes along the file": "Hintergrund belassen: er ändert sich im Lauf der Datei",
  "uneven voice levels evened out, slowly": "ungleiche Stimmpegel langsam angeglichen",
  "level %1 dB": "Pegel %1 dB", "%1 dB taken from the peaks alone": "%1 dB nur von den Spitzen genommen",
  "voice quality %1 → %2 (DNSMOS, out of 5)": "Stimmqualität %1 → %2 (DNSMOS, von 5)",
 },
 "es": {
  "Sound": "Sonido", "As it is": "Tal cual", "Square (1:1), centred": "Cuadrado (1:1), centrado",
  "Improved: background noise, level": "Mejorado: ruido de fondo, nivel",
  "finaliser.py of the traduction toolkit: mains hum and a steady background noise removed when there are some, the level brought to the norm. The length does not change.":
    "finaliser.py del toolkit traduction: zumbido de red y ruido de fondo constante eliminados si los hay, nivel llevado a la norma. La duración no cambia.",
  "Improve the sound": "Mejorar el sonido", "Continue": "Continuar",
  "The traduction toolkit improves the sound (finaliser.py). It was not found: give its folder, or install it from %1.":
    "El toolkit traduction mejora el sonido (finaliser.py). No se encontró: indique su carpeta, o instálelo desde %1.",
  "finaliser.py is not in this folder.": "finaliser.py no está en esta carpeta.",
  "finaliser.py is not in the toolkit folder %1.": "finaliser.py no está en la carpeta del toolkit %1.",
  "the sound could not be improved (finaliser.py): %1": "no se pudo mejorar el sonido (finaliser.py): %1",
  "Sound: %1": "Sonido: %1", "Channels": "Canales", "Hum and rumble": "Zumbido y retumbo", "Analysis": "Análisis",
  "Background noise": "Ruido de fondo", "Levelling": "Nivelación", "Level": "Nivel", "Fades": "Fundidos", "Check": "Control",
  "Frame": "Encuadre", "square (1:1), the centre of the picture": "cuadrado (1:1), el centro de la imagen", "finished by finaliser.py": "acabado por finaliser.py",
  "mains hum at %1 Hz removed": "zumbido de red a %1 Hz eliminado",
  "background noise reduced, by %1 dB at most": "ruido de fondo reducido, %1 dB como máximo",
  "background noise reduced gently (the stronger cleaning harmed the voice)": "ruido de fondo reducido suavemente (la limpieza más fuerte dañaba la voz)",
  "background left as it is: cleaning it harmed the voice": "fondo dejado tal cual: limpiarlo dañaba la voz",
  "background already clean (%1 dB under the voice)": "fondo ya limpio (%1 dB por debajo de la voz)",
  "background left as it is: music, not noise": "fondo dejado tal cual: música, no ruido",
  "background left as it is: it changes along the file": "fondo dejado tal cual: cambia a lo largo del archivo",
  "uneven voice levels evened out, slowly": "niveles de voz desiguales igualados, lentamente",
  "level %1 dB": "nivel %1 dB", "%1 dB taken from the peaks alone": "%1 dB quitados solo a los picos",
  "voice quality %1 → %2 (DNSMOS, out of 5)": "calidad de la voz %1 → %2 (DNSMOS, sobre 5)",
 },
 "pt": {
  "Sound": "Som", "As it is": "Tal como está", "Square (1:1), centred": "Quadrado (1:1), centrado",
  "Improved: background noise, level": "Melhorado: ruído de fundo, nível",
  "finaliser.py of the traduction toolkit: mains hum and a steady background noise removed when there are some, the level brought to the norm. The length does not change.":
    "finaliser.py do toolkit traduction: zumbido da rede e ruído de fundo constante removidos quando existem, nível levado à norma. A duração não muda.",
  "Improve the sound": "Melhorar o som", "Continue": "Continuar",
  "The traduction toolkit improves the sound (finaliser.py). It was not found: give its folder, or install it from %1.":
    "O toolkit traduction melhora o som (finaliser.py). Não foi encontrado: indique a sua pasta, ou instale-o a partir de %1.",
  "finaliser.py is not in this folder.": "finaliser.py não está nesta pasta.",
  "finaliser.py is not in the toolkit folder %1.": "finaliser.py não está na pasta do toolkit %1.",
  "the sound could not be improved (finaliser.py): %1": "não foi possível melhorar o som (finaliser.py): %1",
  "Sound: %1": "Som: %1", "Channels": "Canais", "Hum and rumble": "Zumbido e ronco", "Analysis": "Análise",
  "Background noise": "Ruído de fundo", "Levelling": "Nivelamento", "Level": "Nível", "Fades": "Fundidos", "Check": "Controlo",
  "Frame": "Enquadramento", "square (1:1), the centre of the picture": "quadrado (1:1), o centro da imagem", "finished by finaliser.py": "acabamento por finaliser.py",
  "mains hum at %1 Hz removed": "zumbido da rede a %1 Hz removido",
  "background noise reduced, by %1 dB at most": "ruído de fundo reduzido, %1 dB no máximo",
  "background noise reduced gently (the stronger cleaning harmed the voice)": "ruído de fundo reduzido suavemente (a limpeza mais forte prejudicava a voz)",
  "background left as it is: cleaning it harmed the voice": "fundo deixado tal como está: limpá-lo prejudicava a voz",
  "background already clean (%1 dB under the voice)": "fundo já limpo (%1 dB abaixo da voz)",
  "background left as it is: music, not noise": "fundo deixado tal como está: música, não ruído",
  "background left as it is: it changes along the file": "fundo deixado tal como está: muda ao longo do ficheiro",
  "uneven voice levels evened out, slowly": "níveis de voz desiguais igualados, lentamente",
  "level %1 dB": "nível %1 dB", "%1 dB taken from the peaks alone": "%1 dB retirados apenas aos picos",
  "voice quality %1 → %2 (DNSMOS, out of 5)": "qualidade da voz %1 → %2 (DNSMOS, em 5)",
 },
 "ru": {
  "Sound": "Звук", "As it is": "Как есть", "Square (1:1), centred": "Квадрат (1:1), по центру",
  "Improved: background noise, level": "Улучшенный: фоновый шум, уровень",
  "finaliser.py of the traduction toolkit: mains hum and a steady background noise removed when there are some, the level brought to the norm. The length does not change.":
    "finaliser.py из набора traduction: сетевой гул и равномерный фоновый шум убираются, если они есть, уровень приводится к норме. Длительность не меняется.",
  "Improve the sound": "Улучшить звук", "Continue": "Продолжить",
  "The traduction toolkit improves the sound (finaliser.py). It was not found: give its folder, or install it from %1.":
    "Набор traduction улучшает звук (finaliser.py). Он не найден: укажите его папку или установите его с %1.",
  "finaliser.py is not in this folder.": "finaliser.py нет в этой папке.",
  "finaliser.py is not in the toolkit folder %1.": "finaliser.py нет в папке набора %1.",
  "the sound could not be improved (finaliser.py): %1": "не удалось улучшить звук (finaliser.py): %1",
  "Sound: %1": "Звук: %1", "Channels": "Каналы", "Hum and rumble": "Гул и рокот", "Analysis": "Анализ",
  "Background noise": "Фоновый шум", "Levelling": "Выравнивание", "Level": "Уровень", "Fades": "Затухания", "Check": "Проверка",
  "Frame": "Кадр", "square (1:1), the centre of the picture": "квадрат (1:1), центр изображения", "finished by finaliser.py": "обработка finaliser.py",
  "mains hum at %1 Hz removed": "сетевой гул на %1 Гц убран",
  "background noise reduced, by %1 dB at most": "фоновый шум уменьшен, не более чем на %1 дБ",
  "background noise reduced gently (the stronger cleaning harmed the voice)": "фоновый шум уменьшен мягко (более сильная чистка портила голос)",
  "background left as it is: cleaning it harmed the voice": "фон оставлен как есть: чистка портила голос",
  "background already clean (%1 dB under the voice)": "фон уже чистый (%1 дБ ниже голоса)",
  "background left as it is: music, not noise": "фон оставлен как есть: музыка, а не шум",
  "background left as it is: it changes along the file": "фон оставлен как есть: он меняется по ходу файла",
  "uneven voice levels evened out, slowly": "неровные уровни голоса выровнены, медленно",
  "level %1 dB": "уровень %1 дБ", "%1 dB taken from the peaks alone": "%1 дБ снято только с пиков",
  "voice quality %1 → %2 (DNSMOS, out of 5)": "качество голоса %1 → %2 (DNSMOS, из 5)",
 },
}
for _code, _more in _TR_SOUND.items():
    _TR.setdefault(_code, {}).update(_more)

# The strings of 1.6.0: Instagram-like captions
_TR_CAPTIONS = {
 "fr": {"Two lines at the bottom": "Deux lignes en bas", "Instagram-like captions": "Légendes façon Instagram",
        "A few big words at a time, centred near the bottom of the picture (higher on a vertical one), the spoken word in yellow: the style of the short videos.":
        "Quelques grands mots à la fois, centrés près du bas de l'image (plus haut sur une vidéo verticale), le mot prononcé en jaune : le style des vidéos courtes."},
 "de": {"Two lines at the bottom": "Zwei Zeilen unten", "Instagram-like captions": "Untertitel im Instagram-Stil",
        "A few big words at a time, centred near the bottom of the picture (higher on a vertical one), the spoken word in yellow: the style of the short videos.":
        "Wenige große Wörter auf einmal, mittig nahe dem unteren Bildrand (bei Hochformat höher), das gesprochene Wort in Gelb: der Stil der Kurzvideos."},
 "es": {"Two lines at the bottom": "Dos líneas abajo", "Instagram-like captions": "Rótulos estilo Instagram",
        "A few big words at a time, centred near the bottom of the picture (higher on a vertical one), the spoken word in yellow: the style of the short videos.":
        "Pocas palabras grandes a la vez, centradas cerca de la parte inferior de la imagen (más arriba en vertical), la palabra pronunciada en amarillo: el estilo de los vídeos cortos."},
 "pt": {"Two lines at the bottom": "Duas linhas em baixo", "Instagram-like captions": "Legendas ao estilo Instagram",
        "A few big words at a time, centred near the bottom of the picture (higher on a vertical one), the spoken word in yellow: the style of the short videos.":
        "Poucas palavras grandes de cada vez, centradas perto da parte inferior da imagem (mais acima na vertical), a palavra dita a amarelo: o estilo dos vídeos curtos."},
 "ru": {"Two lines at the bottom": "Две строки внизу", "Instagram-like captions": "Подписи в стиле Instagram",
        "A few big words at a time, centred near the bottom of the picture (higher on a vertical one), the spoken word in yellow: the style of the short videos.":
        "Несколько крупных слов за раз, по центру у нижнего края кадра (выше на вертикальном видео), произносимое слово жёлтым: стиль коротких видео."},
}
for _code, _more in _TR_CAPTIONS.items():
    _TR.setdefault(_code, {}).update(_more)

# The strings of 1.7.0: the toolkit installs itself
_TR_SETUP = {
 "fr": {
  "Install it here (download, a few MB)": "L'installer ici (téléchargement, quelques Mo)",
  "Downloading the traduction toolkit…": "Téléchargement de la boîte à outils traduction…",
  "Installed in %1. Its libraries will be installed by the app when a feature needs them.": "Installée dans %1. Ses bibliothèques seront installées par l'application quand une fonction en aura besoin.",
  "The download failed: %1": "Le téléchargement a échoué : %1", "The archive does not hold traduire.py.": "L'archive ne contient pas traduire.py.",
  "No Python was found to set the toolkit up with.": "Aucun Python trouvé pour préparer la boîte à outils.",
  "Preparing the toolkit's environment (once)…": "Préparation de l'environnement de la boîte à outils (une fois)…",
  "The toolkit's environment could not be made: %1": "L'environnement de la boîte à outils n'a pas pu être créé : %1",
  "Installing %1 (once)…": "Installation de %1 (une fois)…", "%1 could not be installed: %2": "%1 n'a pas pu être installé : %2",
  "Anthropic API key": "Clé API Anthropic", "Give an Anthropic API key.": "Indiquez une clé API Anthropic.",
  "Fetching %1 (once)…": "Récupération de %1 (une fois)…", "%1 could not be fetched.": "%1 n'a pas pu être récupéré.",
  "ffmpeg and ffprobe were not found on this computer: install ffmpeg.": "ffmpeg et ffprobe sont introuvables sur cet ordinateur : installez ffmpeg.",
  "some of the toolkit's libraries are missing.": "des bibliothèques de la boîte à outils manquent.",
  "this file is silent, or too short to be analysed.": "ce fichier est muet, ou trop court pour être analysé.",
  "this file has no picture.": "ce fichier n'a pas d'image.",
 },
 "de": {
  "Install it here (download, a few MB)": "Hier installieren (Download, wenige MB)",
  "Downloading the traduction toolkit…": "Das traduction-Toolkit wird heruntergeladen…",
  "Installed in %1. Its libraries will be installed by the app when a feature needs them.": "Installiert in %1. Seine Bibliotheken installiert die App, sobald eine Funktion sie braucht.",
  "The download failed: %1": "Der Download ist fehlgeschlagen: %1", "The archive does not hold traduire.py.": "Das Archiv enthält kein traduire.py.",
  "No Python was found to set the toolkit up with.": "Kein Python gefunden, um das Toolkit einzurichten.",
  "Preparing the toolkit's environment (once)…": "Die Umgebung des Toolkits wird vorbereitet (einmalig)…",
  "The toolkit's environment could not be made: %1": "Die Umgebung des Toolkits konnte nicht erstellt werden: %1",
  "Installing %1 (once)…": "%1 wird installiert (einmalig)…", "%1 could not be installed: %2": "%1 konnte nicht installiert werden: %2",
  "Anthropic API key": "Anthropic-API-Schlüssel", "Give an Anthropic API key.": "Geben Sie einen Anthropic-API-Schlüssel an.",
  "Fetching %1 (once)…": "%1 wird geholt (einmalig)…", "%1 could not be fetched.": "%1 konnte nicht geholt werden.",
  "ffmpeg and ffprobe were not found on this computer: install ffmpeg.": "ffmpeg und ffprobe wurden auf diesem Rechner nicht gefunden: Installieren Sie ffmpeg.",
  "some of the toolkit's libraries are missing.": "einige Bibliotheken des Toolkits fehlen.",
  "this file is silent, or too short to be analysed.": "diese Datei ist stumm oder zu kurz für eine Analyse.",
  "this file has no picture.": "diese Datei hat kein Bild.",
 },
 "es": {
  "Install it here (download, a few MB)": "Instalarlo aquí (descarga, unos MB)",
  "Downloading the traduction toolkit…": "Descargando el toolkit traduction…",
  "Installed in %1. Its libraries will be installed by the app when a feature needs them.": "Instalado en %1. La aplicación instalará sus bibliotecas cuando una función las necesite.",
  "The download failed: %1": "La descarga ha fallado: %1", "The archive does not hold traduire.py.": "El archivo no contiene traduire.py.",
  "No Python was found to set the toolkit up with.": "No se encontró ningún Python para preparar el toolkit.",
  "Preparing the toolkit's environment (once)…": "Preparando el entorno del toolkit (una vez)…",
  "The toolkit's environment could not be made: %1": "No se pudo crear el entorno del toolkit: %1",
  "Installing %1 (once)…": "Instalando %1 (una vez)…", "%1 could not be installed: %2": "No se pudo instalar %1: %2",
  "Anthropic API key": "Clave API de Anthropic", "Give an Anthropic API key.": "Indique una clave API de Anthropic.",
  "Fetching %1 (once)…": "Obteniendo %1 (una vez)…", "%1 could not be fetched.": "No se pudo obtener %1.",
  "ffmpeg and ffprobe were not found on this computer: install ffmpeg.": "ffmpeg y ffprobe no se encontraron en este equipo: instale ffmpeg.",
  "some of the toolkit's libraries are missing.": "faltan bibliotecas del toolkit.",
  "this file is silent, or too short to be analysed.": "este archivo es mudo, o demasiado corto para analizarlo.",
  "this file has no picture.": "este archivo no tiene imagen.",
 },
 "pt": {
  "Install it here (download, a few MB)": "Instalá-lo aqui (transferência, alguns MB)",
  "Downloading the traduction toolkit…": "A transferir o toolkit traduction…",
  "Installed in %1. Its libraries will be installed by the app when a feature needs them.": "Instalado em %1. As suas bibliotecas serão instaladas pela aplicação quando uma função precisar delas.",
  "The download failed: %1": "A transferência falhou: %1", "The archive does not hold traduire.py.": "O arquivo não contém traduire.py.",
  "No Python was found to set the toolkit up with.": "Nenhum Python encontrado para preparar o toolkit.",
  "Preparing the toolkit's environment (once)…": "A preparar o ambiente do toolkit (uma vez)…",
  "The toolkit's environment could not be made: %1": "Não foi possível criar o ambiente do toolkit: %1",
  "Installing %1 (once)…": "A instalar %1 (uma vez)…", "%1 could not be installed: %2": "Não foi possível instalar %1: %2",
  "Anthropic API key": "Chave API Anthropic", "Give an Anthropic API key.": "Indique uma chave API Anthropic.",
  "Fetching %1 (once)…": "A obter %1 (uma vez)…", "%1 could not be fetched.": "Não foi possível obter %1.",
  "ffmpeg and ffprobe were not found on this computer: install ffmpeg.": "ffmpeg e ffprobe não foram encontrados neste computador: instale o ffmpeg.",
  "some of the toolkit's libraries are missing.": "faltam bibliotecas do toolkit.",
  "this file is silent, or too short to be analysed.": "este ficheiro é mudo, ou demasiado curto para ser analisado.",
  "this file has no picture.": "este ficheiro não tem imagem.",
 },
 "ru": {
  "Install it here (download, a few MB)": "Установить сюда (загрузка, несколько МБ)",
  "Downloading the traduction toolkit…": "Загрузка набора traduction…",
  "Installed in %1. Its libraries will be installed by the app when a feature needs them.": "Установлен в %1. Его библиотеки приложение установит, когда они понадобятся какой-либо функции.",
  "The download failed: %1": "Загрузка не удалась: %1", "The archive does not hold traduire.py.": "В архиве нет traduire.py.",
  "No Python was found to set the toolkit up with.": "Не найден Python для подготовки набора.",
  "Preparing the toolkit's environment (once)…": "Подготовка окружения набора (один раз)…",
  "The toolkit's environment could not be made: %1": "Не удалось создать окружение набора: %1",
  "Installing %1 (once)…": "Установка %1 (один раз)…", "%1 could not be installed: %2": "Не удалось установить %1: %2",
  "Anthropic API key": "Ключ API Anthropic", "Give an Anthropic API key.": "Укажите ключ API Anthropic.",
  "Fetching %1 (once)…": "Получение %1 (один раз)…", "%1 could not be fetched.": "Не удалось получить %1.",
  "ffmpeg and ffprobe were not found on this computer: install ffmpeg.": "ffmpeg и ffprobe не найдены на этом компьютере: установите ffmpeg.",
  "some of the toolkit's libraries are missing.": "не хватает библиотек набора.",
  "this file is silent, or too short to be analysed.": "этот файл беззвучен или слишком короток для анализа.",
  "this file has no picture.": "в этом файле нет изображения.",
 },
}
for _code, _more in _TR_SETUP.items():
    _TR.setdefault(_code, {}).update(_more)

# The strings of 1.8.0: the getting-started page, Claude Code
_TR_START = {
 "fr": {
  "Getting started": "Prise en main", "Getting started…": "Prise en main…", "Optional —": "Facultatif —", "Model": "Modèle", "« %1 »: %2.": "« %1 » : %2.",
  "the fastest, rough words and timings: good to try the app, not to publish": "le plus rapide, mots et minutages approximatifs : bon pour essayer l'application, pas pour publier",
  "fast, still rough; acceptable for English only": "rapide, encore approximatif ; acceptable pour l'anglais seulement",
  "the default: good words in most languages, about as long as the recording lasts": "le choix par défaut : de bons mots dans la plupart des langues, à peu près la durée de l'enregistrement",
  "better words and names, about three times slower, 1.5 GB": "meilleurs mots et noms propres, environ trois fois plus lent, 1,5 Go",
  "the best words, about ten times slower on a processor, 3 GB on disk and 4 GB of memory": "les meilleurs mots, environ dix fois plus lent sur un processeur, 3 Go sur le disque et 4 Go de mémoire",
  "small and fast; translations to be reread": "petit et rapide ; traductions à relire", "decent translations, a few minutes for a talk": "traductions correctes, quelques minutes pour une causerie",
  "good translations, fast on a Mac with 32 GB": "bonnes traductions, rapide sur un Mac de 32 Go", "the toolkit's best local model; slow without a big graphics card": "le meilleur modèle local du toolkit ; lent sans grosse carte graphique",
  "Quality and cost: Claude gives the best translations; Claude Code costs nothing beyond your plan, the API key pays by the call, both send the text to Anthropic. A local model keeps everything on this computer, slower, and the smaller the model, the rougher the translation.":
    "Qualité et coût : Claude donne les meilleures traductions ; Claude Code ne coûte rien au-delà de votre abonnement, la clé API paie à l'appel, les deux envoient le texte chez Anthropic. Un modèle local garde tout sur cet ordinateur, plus lentement, et plus le modèle est petit, plus la traduction est approximative.",
  "Speed: about the length of the edit on a processor, much less with a graphics card; the length and the picture do not change.": "Vitesse : à peu près la durée du montage sur un processeur, bien moins avec une carte graphique ; la durée et l'image ne changent pas.",
  "Three levels. Level 1 is all you need to cut a video: it works as soon as the app is installed. Levels 2 and 3 are optional extras; if you never translate, skip them, nothing there is needed for the editing. One step at a time, each checked by a real test, each with the button that does the work. You can come back here any time: « Getting started… » on the home page, or Project ▾ › Getting started… while editing.":
    "Trois niveaux. Le niveau 1 suffit pour monter une vidéo : il marche dès que l'application est installée. Les niveaux 2 et 3 sont des suppléments facultatifs ; si vous ne traduisez jamais, sautez-les, rien de ce qui s'y trouve ne sert au montage. Une étape à la fois, chacune vérifiée par un vrai essai, chacune avec le bouton qui fait le travail. Vous pouvez revenir ici à tout moment : « Prise en main… » sur la page d'accueil, ou Projet ▾ › Prise en main… pendant le montage.",
  "Level 1 · Editing": "Niveau 1 · Le montage", "The whole point of the app: open, highlight, produce. Nothing to install.": "Le cœur de l'application : ouvrir, surligner, produire. Rien à installer.",
  "That is enough for me: start editing": "Cela me suffit : commencer à monter",
  "Level 2 · Translation and subtitles — optional": "Niveau 2 · Traduction et sous-titres — facultatif",
  "Only if you want to translate the text, or to cut subtitles with the toolkit's rules. Otherwise skip this level entirely.": "Seulement si vous voulez traduire le texte, ou découper des sous-titres avec les règles de la boîte à outils. Sinon, sautez ce niveau entièrement.",
  "Level 3 · Improved sound — optional": "Niveau 3 · Son amélioré — facultatif",
  "Only if you want the edit's sound cleaned and levelled on the way out. Needs the toolkit of level 2 (not the model).": "Seulement si vous voulez le son du montage nettoyé et mis à niveau à la sortie. Demande la boîte à outils du niveau 2 (pas le modèle).",
  "What this computer has, and the buttons that put the rest in place.": "Ce que cet ordinateur a, et les boutons qui mettent le reste en place.",
  "Three levels. The first works as soon as the app is installed. The next two are optional: one step at a time, each checked by a real test, each with the button that does the work. You can come back here any time: « Getting started… » on the home page, or Project ▾ › Getting started… while editing.":
    "Trois niveaux. Le premier marche dès que l'application est installée. Les deux suivants sont facultatifs : une étape à la fois, chacune vérifiée par un vrai essai, chacune avec le bouton qui fait le travail. Vous pouvez revenir ici à tout moment : « Prise en main… » sur la page d'accueil, ou Projet ▾ › Prise en main… pendant le montage.",
  "Cut a video by its text": "Monter une vidéo par son texte", "Transcribe the speech": "Transcrire la parole",
  "Translate and subtitle: the toolkit": "Traduire et sous-titrer : la boîte à outils", "Translate and subtitle: the language model": "Traduire et sous-titrer : le modèle de langue",
  "Improve the sound": "Améliorer le son", "Check again": "Vérifier à nouveau", "Start editing": "Commencer à monter", "Checking…": "Vérification…", "Working…": "En cours…",
  "Ready: ffmpeg is here. Open a video or a recording, highlight, produce.": "Prêt : ffmpeg est là. Ouvrez une vidéo ou un enregistrement, surlignez, produisez.",
  "ffmpeg is missing. On Linux: sudo apt install ffmpeg, then « Check again ».": "ffmpeg manque. Sur Linux : sudo apt install ffmpeg, puis « Vérifier à nouveau ».",
  "The transcription is missing from this build.": "La transcription manque dans cette version.",
  "faster-whisper is not installed yet: the app installs it in a folder of its own (about 300 MB, once).": "faster-whisper n'est pas encore installé : l'application l'installe dans un dossier à elle (environ 300 Mo, une fois).",
  "Install the transcription": "Installer la transcription",
  "faster-whisper is here. The model « %1 » (%2) is downloaded at the first transcription; or now:": "faster-whisper est là. Le modèle « %1 » (%2) est téléchargé à la première transcription ; ou maintenant :",
  "Download the model now": "Télécharger le modèle maintenant", "Downloading the model « %1 » (%2)…": "Téléchargement du modèle « %1 » (%2)…",
  "Ready: faster-whisper and the model « %1 ». A subtitle file beside the video is used instead when there is one.": "Prêt : faster-whisper et le modèle « %1 ». Un fichier de sous-titres à côté de la vidéo est utilisé à la place quand il y en a un.",
  "Found: %1": "Trouvée : %1",
  "The traduction toolkit does the translation, the subtitles and the sound. It is not on this computer: the app can download it (a few MB, no git).": "La boîte à outils traduction fait la traduction, les sous-titres et le son. Elle n'est pas sur cet ordinateur : l'application peut la télécharger (quelques Mo, sans git).",
  "Install it here": "L'installer ici", "Needs the toolkit (step 2).": "Demande la boîte à outils (étape 2).",
  "Ready: the libraries of finaliser.py are here. « Sound: improved » in the production block uses them.": "Prêt : les bibliothèques de finaliser.py sont là. « Son : amélioré » dans le bloc de production s'en sert.",
  "The libraries (deepfilternet, pyloudnorm, speechmos, with torch: about 500 MB) are installed at the first use, in an environment of the app's own. Or now:": "Les bibliothèques (deepfilternet, pyloudnorm, speechmos, avec torch : environ 500 Mo) s'installent au premier usage, dans un environnement propre à l'application. Ou maintenant :",
  "On this Mac, ffmpeg and ffprobe for Apple silicon are fetched too (2 × 28 MB).": "Sur ce Mac, ffmpeg et ffprobe pour puce Apple sont récupérés aussi (2 × 28 Mo).",
  "Install now": "Installer maintenant",
  "Ollama, on this computer": "Ollama, sur cet ordinateur", "Claude Code, your own plan": "Claude Code, votre abonnement", "Claude, an API key": "Claude, une clé API",
  "Ollama runs the model on this computer. It is not installed: get it from ollama.com (the app on a Mac, one command on Linux), open it, then « Check again ».": "Ollama fait tourner le modèle sur cet ordinateur. Il n'est pas installé : prenez-le sur ollama.com (l'application sur Mac, une commande sur Linux), ouvrez-le, puis « Vérifier à nouveau ».",
  "Get Ollama": "Obtenir Ollama", "Ollama is installed but not running.": "Ollama est installé mais ne tourne pas.", "Start Ollama": "Démarrer Ollama",
  "Ollama answers, but this computer (%1 GB of memory) is too small for a model of the toolkit's family: choose Claude.": "Ollama répond, mais cet ordinateur (%1 Go de mémoire) est trop petit pour un modèle de la famille du toolkit : choisissez Claude.",
  "Ollama answers. This computer (%1 GB of memory) can carry « %2 »%3; the download happens once.": "Ollama répond. Cet ordinateur (%1 Go de mémoire) peut porter « %2 »%3 ; le téléchargement se fait une fois.",
  "Download %1": "Télécharger %1", "Downloading %1… %2 %": "Téléchargement de %1… %2 %", "Downloading %1…": "Téléchargement de %1…",
  "the model is not there after the download": "le modèle n'est pas là après le téléchargement",
  "Ready: Ollama answers and « %1 » replied to a test.": "Prêt : Ollama répond et « %1 » a répondu à un essai.",
  "Ollama answers and « %1 » is here. One test to be sure:": "Ollama répond et « %1 » est là. Un essai pour être sûr :", "Test": "Essayer", "Asking « %1 »…": "Question à « %1 »…",
  "Claude Code is the claude command, on your own Claude plan: no key, no bill by the call. It is not installed; the app can run its installer (from claude.ai).": "Claude Code est la commande claude, sur votre abonnement Claude : pas de clé, pas de facture à l'appel. Il n'est pas installé ; l'application peut lancer son installateur (depuis claude.ai).",
  "Install Claude Code": "Installer Claude Code", "Installing Claude Code…": "Installation de Claude Code…",
  "Ready: Claude Code answers (%1).": "Prêt : Claude Code répond (%1).",
  "Claude Code found: %1. Sign in once with your Claude account (a terminal opens: type /login and follow the browser), then test.": "Claude Code trouvé : %1. Connectez-vous une fois avec votre compte Claude (un terminal s'ouvre : tapez /login et suivez le navigateur), puis essayez.",
  "Asking Claude Code…": "Question à Claude Code…", "Sign in": "Se connecter",
  "No terminal was found: open one yourself, type claude, then /login.": "Aucun terminal trouvé : ouvrez-en un vous-même, tapez claude, puis /login.",
  "Claude Code did not answer in time.": "Claude Code n'a pas répondu à temps.",
  "Claude Code is installed but not signed in: click « Sign in ».": "Claude Code est installé mais pas connecté : cliquez « Se connecter ».",
  "Ready: the key is accepted by Anthropic.": "Prêt : la clé est acceptée par Anthropic.",
  "A key from console.anthropic.com (API Keys › Create Key), paid by the call; the text goes to Anthropic. Paste it, then test.": "Une clé de console.anthropic.com (API Keys › Create Key), payée à l'appel ; le texte part chez Anthropic. Collez-la, puis essayez.",
  "Asking Anthropic…": "Question à Anthropic…", "Test the key": "Essayer la clé", "The key is refused by Anthropic.": "La clé est refusée par Anthropic.",
  "Claude Code (your own plan)": "Claude Code (votre abonnement)", "Claude (API key)": "Claude (clé API)",
  "Claude Code found: %1": "Claude Code trouvé : %1",
  "Claude Code is not installed: « Getting started » on the home page installs it.": "Claude Code n'est pas installé : « Prise en main », sur la page d'accueil, l'installe.",
  "Ollama answers.": "Ollama répond.", "Ollama does not answer: « Getting started » on the home page sets it up.": "Ollama ne répond pas : « Prise en main », sur la page d'accueil, le met en place.",
 },
 "de": {
  "Getting started": "Erste Schritte", "Getting started…": "Erste Schritte…", "Optional —": "Freiwillig —", "Model": "Modell", "« %1 »: %2.": "„%1“: %2.",
  "the fastest, rough words and timings: good to try the app, not to publish": "das schnellste, grobe Wörter und Zeiten: gut zum Ausprobieren, nicht zum Veröffentlichen",
  "fast, still rough; acceptable for English only": "schnell, noch grob; nur für Englisch annehmbar",
  "the default: good words in most languages, about as long as the recording lasts": "die Voreinstellung: gute Wörter in den meisten Sprachen, etwa so lang wie die Aufnahme dauert",
  "better words and names, about three times slower, 1.5 GB": "bessere Wörter und Namen, etwa dreimal langsamer, 1,5 GB",
  "the best words, about ten times slower on a processor, 3 GB on disk and 4 GB of memory": "die besten Wörter, etwa zehnmal langsamer auf einem Prozessor, 3 GB auf der Platte und 4 GB Speicher",
  "small and fast; translations to be reread": "klein und schnell; Übersetzungen zum Nachlesen", "decent translations, a few minutes for a talk": "ordentliche Übersetzungen, einige Minuten für einen Vortrag",
  "good translations, fast on a Mac with 32 GB": "gute Übersetzungen, schnell auf einem Mac mit 32 GB", "the toolkit's best local model; slow without a big graphics card": "das beste lokale Modell des Toolkits; langsam ohne große Grafikkarte",
  "Quality and cost: Claude gives the best translations; Claude Code costs nothing beyond your plan, the API key pays by the call, both send the text to Anthropic. A local model keeps everything on this computer, slower, and the smaller the model, the rougher the translation.":
    "Qualität und Kosten: Claude liefert die besten Übersetzungen; Claude Code kostet nichts über Ihr Abo hinaus, der API-Schlüssel zahlt pro Aufruf, beide senden den Text an Anthropic. Ein lokales Modell behält alles auf diesem Rechner, langsamer, und je kleiner das Modell, desto gröber die Übersetzung.",
  "Speed: about the length of the edit on a processor, much less with a graphics card; the length and the picture do not change.": "Geschwindigkeit: etwa die Länge des Schnitts auf einem Prozessor, viel weniger mit Grafikkarte; Länge und Bild ändern sich nicht.",
  "Three levels. Level 1 is all you need to cut a video: it works as soon as the app is installed. Levels 2 and 3 are optional extras; if you never translate, skip them, nothing there is needed for the editing. One step at a time, each checked by a real test, each with the button that does the work. You can come back here any time: « Getting started… » on the home page, or Project ▾ › Getting started… while editing.":
    "Drei Stufen. Stufe 1 genügt, um ein Video zu schneiden: sie funktioniert, sobald die App installiert ist. Die Stufen 2 und 3 sind freiwillige Zugaben; wer nie übersetzt, überspringt sie, nichts davon braucht der Schnitt. Ein Schritt nach dem anderen, jeder durch einen echten Test geprüft, jeder mit dem Knopf, der die Arbeit macht. Sie kommen jederzeit hierher zurück: „Erste Schritte…“ auf der Startseite oder Projekt ▾ › Erste Schritte… während des Schneidens.",
  "Level 1 · Editing": "Stufe 1 · Der Schnitt", "The whole point of the app: open, highlight, produce. Nothing to install.": "Der Kern der App: öffnen, markieren, erzeugen. Nichts zu installieren.",
  "That is enough for me: start editing": "Das genügt mir: mit dem Schneiden beginnen",
  "Level 2 · Translation and subtitles — optional": "Stufe 2 · Übersetzung und Untertitel — freiwillig",
  "Only if you want to translate the text, or to cut subtitles with the toolkit's rules. Otherwise skip this level entirely.": "Nur wenn Sie den Text übersetzen oder Untertitel nach den Regeln des Toolkits schneiden wollen. Sonst diese Stufe ganz überspringen.",
  "Level 3 · Improved sound — optional": "Stufe 3 · Verbesserter Ton — freiwillig",
  "Only if you want the edit's sound cleaned and levelled on the way out. Needs the toolkit of level 2 (not the model).": "Nur wenn der Ton des Schnitts beim Export gereinigt und ausgepegelt werden soll. Braucht das Toolkit der Stufe 2 (nicht das Modell).",
  "What this computer has, and the buttons that put the rest in place.": "Was dieser Rechner hat, und die Knöpfe, die den Rest einrichten.",
  "Three levels. The first works as soon as the app is installed. The next two are optional: one step at a time, each checked by a real test, each with the button that does the work. You can come back here any time: « Getting started… » on the home page, or Project ▾ › Getting started… while editing.":
    "Drei Stufen. Die erste funktioniert, sobald die App installiert ist. Die beiden nächsten sind freiwillig: ein Schritt nach dem anderen, jeder durch einen echten Test geprüft, jeder mit dem Knopf, der die Arbeit macht. Sie kommen jederzeit hierher zurück: „Erste Schritte…“ auf der Startseite oder Projekt ▾ › Erste Schritte… während des Schneidens.",
  "Cut a video by its text": "Ein Video über seinen Text schneiden", "Transcribe the speech": "Die Sprache transkribieren",
  "Translate and subtitle: the toolkit": "Übersetzen und untertiteln: das Toolkit", "Translate and subtitle: the language model": "Übersetzen und untertiteln: das Sprachmodell",
  "Improve the sound": "Ton verbessern", "Check again": "Erneut prüfen", "Start editing": "Mit dem Schneiden beginnen", "Checking…": "Prüfung…", "Working…": "Läuft…",
  "Ready: ffmpeg is here. Open a video or a recording, highlight, produce.": "Bereit: ffmpeg ist da. Video oder Aufnahme öffnen, markieren, erzeugen.",
  "ffmpeg is missing. On Linux: sudo apt install ffmpeg, then « Check again ».": "ffmpeg fehlt. Unter Linux: sudo apt install ffmpeg, dann „Erneut prüfen“.",
  "The transcription is missing from this build.": "Die Transkription fehlt in dieser Version.",
  "faster-whisper is not installed yet: the app installs it in a folder of its own (about 300 MB, once).": "faster-whisper ist noch nicht installiert: die App installiert es in einem eigenen Ordner (etwa 300 MB, einmalig).",
  "Install the transcription": "Transkription installieren",
  "faster-whisper is here. The model « %1 » (%2) is downloaded at the first transcription; or now:": "faster-whisper ist da. Das Modell „%1“ (%2) wird bei der ersten Transkription geladen; oder jetzt:",
  "Download the model now": "Modell jetzt laden", "Downloading the model « %1 » (%2)…": "Modell „%1“ (%2) wird geladen…",
  "Ready: faster-whisper and the model « %1 ». A subtitle file beside the video is used instead when there is one.": "Bereit: faster-whisper und das Modell „%1“. Eine Untertiteldatei neben dem Video wird stattdessen verwendet, wenn es eine gibt.",
  "Found: %1": "Gefunden: %1",
  "The traduction toolkit does the translation, the subtitles and the sound. It is not on this computer: the app can download it (a few MB, no git).": "Das traduction-Toolkit macht die Übersetzung, die Untertitel und den Ton. Es ist nicht auf diesem Rechner: die App kann es herunterladen (wenige MB, ohne git).",
  "Install it here": "Hier installieren", "Needs the toolkit (step 2).": "Braucht das Toolkit (Schritt 2).",
  "Ready: the libraries of finaliser.py are here. « Sound: improved » in the production block uses them.": "Bereit: die Bibliotheken von finaliser.py sind da. „Ton: verbessert“ im Produktionsblock nutzt sie.",
  "The libraries (deepfilternet, pyloudnorm, speechmos, with torch: about 500 MB) are installed at the first use, in an environment of the app's own. Or now:": "Die Bibliotheken (deepfilternet, pyloudnorm, speechmos, mit torch: etwa 500 MB) werden beim ersten Gebrauch in einer eigenen Umgebung der App installiert. Oder jetzt:",
  "On this Mac, ffmpeg and ffprobe for Apple silicon are fetched too (2 × 28 MB).": "Auf diesem Mac werden auch ffmpeg und ffprobe für Apple Silicon geholt (2 × 28 MB).",
  "Install now": "Jetzt installieren",
  "Ollama, on this computer": "Ollama, auf diesem Rechner", "Claude Code, your own plan": "Claude Code, Ihr eigenes Abo", "Claude, an API key": "Claude, ein API-Schlüssel",
  "Ollama runs the model on this computer. It is not installed: get it from ollama.com (the app on a Mac, one command on Linux), open it, then « Check again ».": "Ollama lässt das Modell auf diesem Rechner laufen. Es ist nicht installiert: holen Sie es von ollama.com (die App auf dem Mac, ein Befehl unter Linux), öffnen Sie es, dann „Erneut prüfen“.",
  "Get Ollama": "Ollama holen", "Ollama is installed but not running.": "Ollama ist installiert, läuft aber nicht.", "Start Ollama": "Ollama starten",
  "Ollama answers, but this computer (%1 GB of memory) is too small for a model of the toolkit's family: choose Claude.": "Ollama antwortet, aber dieser Rechner (%1 GB Speicher) ist zu klein für ein Modell aus der Familie des Toolkits: wählen Sie Claude.",
  "Ollama answers. This computer (%1 GB of memory) can carry « %2 »%3; the download happens once.": "Ollama antwortet. Dieser Rechner (%1 GB Speicher) trägt „%2“%3; der Download geschieht einmalig.",
  "Download %1": "%1 laden", "Downloading %1… %2 %": "%1 wird geladen… %2 %", "Downloading %1…": "%1 wird geladen…",
  "the model is not there after the download": "das Modell ist nach dem Download nicht da",
  "Ready: Ollama answers and « %1 » replied to a test.": "Bereit: Ollama antwortet und „%1“ hat auf einen Test geantwortet.",
  "Ollama answers and « %1 » is here. One test to be sure:": "Ollama antwortet und „%1“ ist da. Ein Test zur Sicherheit:", "Test": "Testen", "Asking « %1 »…": "Frage an „%1“…",
  "Claude Code is the claude command, on your own Claude plan: no key, no bill by the call. It is not installed; the app can run its installer (from claude.ai).": "Claude Code ist der Befehl claude, auf Ihrem eigenen Claude-Abo: kein Schlüssel, keine Abrechnung pro Aufruf. Er ist nicht installiert; die App kann seinen Installer ausführen (von claude.ai).",
  "Install Claude Code": "Claude Code installieren", "Installing Claude Code…": "Claude Code wird installiert…",
  "Ready: Claude Code answers (%1).": "Bereit: Claude Code antwortet (%1).",
  "Claude Code found: %1. Sign in once with your Claude account (a terminal opens: type /login and follow the browser), then test.": "Claude Code gefunden: %1. Melden Sie sich einmal mit Ihrem Claude-Konto an (ein Terminal öffnet sich: /login eingeben und dem Browser folgen), dann testen.",
  "Asking Claude Code…": "Frage an Claude Code…", "Sign in": "Anmelden",
  "No terminal was found: open one yourself, type claude, then /login.": "Kein Terminal gefunden: öffnen Sie selbst eines, tippen Sie claude, dann /login.",
  "Claude Code did not answer in time.": "Claude Code hat nicht rechtzeitig geantwortet.",
  "Claude Code is installed but not signed in: click « Sign in ».": "Claude Code ist installiert, aber nicht angemeldet: klicken Sie „Anmelden“.",
  "Ready: the key is accepted by Anthropic.": "Bereit: der Schlüssel wird von Anthropic angenommen.",
  "A key from console.anthropic.com (API Keys › Create Key), paid by the call; the text goes to Anthropic. Paste it, then test.": "Ein Schlüssel von console.anthropic.com (API Keys › Create Key), pro Aufruf bezahlt; der Text geht an Anthropic. Einfügen, dann testen.",
  "Asking Anthropic…": "Frage an Anthropic…", "Test the key": "Schlüssel testen", "The key is refused by Anthropic.": "Der Schlüssel wird von Anthropic abgelehnt.",
  "Claude Code (your own plan)": "Claude Code (Ihr eigenes Abo)", "Claude (API key)": "Claude (API-Schlüssel)",
  "Claude Code found: %1": "Claude Code gefunden: %1",
  "Claude Code is not installed: « Getting started » on the home page installs it.": "Claude Code ist nicht installiert: „Erste Schritte“ auf der Startseite installiert es.",
  "Ollama answers.": "Ollama antwortet.", "Ollama does not answer: « Getting started » on the home page sets it up.": "Ollama antwortet nicht: „Erste Schritte“ auf der Startseite richtet es ein.",
 },
 "es": {
  "Getting started": "Primeros pasos", "Getting started…": "Primeros pasos…", "Optional —": "Opcional —", "Model": "Modelo", "« %1 »: %2.": "« %1 »: %2.",
  "the fastest, rough words and timings: good to try the app, not to publish": "el más rápido, palabras y tiempos aproximados: bueno para probar la aplicación, no para publicar",
  "fast, still rough; acceptable for English only": "rápido, aún aproximado; aceptable solo para inglés",
  "the default: good words in most languages, about as long as the recording lasts": "el predeterminado: buenas palabras en la mayoría de idiomas, más o menos lo que dura la grabación",
  "better words and names, about three times slower, 1.5 GB": "mejores palabras y nombres, unas tres veces más lento, 1,5 GB",
  "the best words, about ten times slower on a processor, 3 GB on disk and 4 GB of memory": "las mejores palabras, unas diez veces más lento en un procesador, 3 GB en disco y 4 GB de memoria",
  "small and fast; translations to be reread": "pequeño y rápido; traducciones para releer", "decent translations, a few minutes for a talk": "traducciones decentes, unos minutos para una charla",
  "good translations, fast on a Mac with 32 GB": "buenas traducciones, rápido en un Mac de 32 GB", "the toolkit's best local model; slow without a big graphics card": "el mejor modelo local del toolkit; lento sin una gran tarjeta gráfica",
  "Quality and cost: Claude gives the best translations; Claude Code costs nothing beyond your plan, the API key pays by the call, both send the text to Anthropic. A local model keeps everything on this computer, slower, and the smaller the model, the rougher the translation.":
    "Calidad y coste: Claude da las mejores traducciones; Claude Code no cuesta nada más allá de su suscripción, la clave API paga por llamada, ambos envían el texto a Anthropic. Un modelo local lo guarda todo en este equipo, más despacio, y cuanto más pequeño el modelo, más tosca la traducción.",
  "Speed: about the length of the edit on a processor, much less with a graphics card; the length and the picture do not change.": "Velocidad: más o menos la duración del montaje en un procesador, mucho menos con tarjeta gráfica; la duración y la imagen no cambian.",
  "Three levels. Level 1 is all you need to cut a video: it works as soon as the app is installed. Levels 2 and 3 are optional extras; if you never translate, skip them, nothing there is needed for the editing. One step at a time, each checked by a real test, each with the button that does the work. You can come back here any time: « Getting started… » on the home page, or Project ▾ › Getting started… while editing.":
    "Tres niveles. El nivel 1 basta para montar un vídeo: funciona en cuanto la aplicación está instalada. Los niveles 2 y 3 son extras opcionales; si nunca traduce, sáltelos, nada de eso hace falta para el montaje. Un paso a la vez, cada uno comprobado con una prueba real, cada uno con el botón que hace el trabajo. Puede volver aquí cuando quiera: « Primeros pasos… » en la página de inicio, o Proyecto ▾ › Primeros pasos… durante el montaje.",
  "Level 1 · Editing": "Nivel 1 · El montaje", "The whole point of the app: open, highlight, produce. Nothing to install.": "El corazón de la aplicación: abrir, resaltar, producir. Nada que instalar.",
  "That is enough for me: start editing": "Con esto me basta: empezar a montar",
  "Level 2 · Translation and subtitles — optional": "Nivel 2 · Traducción y subtítulos — opcional",
  "Only if you want to translate the text, or to cut subtitles with the toolkit's rules. Otherwise skip this level entirely.": "Solo si quiere traducir el texto, o cortar subtítulos con las reglas del toolkit. Si no, sáltese este nivel por completo.",
  "Level 3 · Improved sound — optional": "Nivel 3 · Sonido mejorado — opcional",
  "Only if you want the edit's sound cleaned and levelled on the way out. Needs the toolkit of level 2 (not the model).": "Solo si quiere el sonido del montaje limpiado y nivelado a la salida. Necesita el toolkit del nivel 2 (no el modelo).",
  "What this computer has, and the buttons that put the rest in place.": "Lo que tiene este equipo, y los botones que ponen el resto en su sitio.",
  "Three levels. The first works as soon as the app is installed. The next two are optional: one step at a time, each checked by a real test, each with the button that does the work. You can come back here any time: « Getting started… » on the home page, or Project ▾ › Getting started… while editing.":
    "Tres niveles. El primero funciona en cuanto la aplicación está instalada. Los dos siguientes son opcionales: un paso a la vez, cada uno comprobado con una prueba real, cada uno con el botón que hace el trabajo. Puede volver aquí cuando quiera: « Primeros pasos… » en la página de inicio, o Proyecto ▾ › Primeros pasos… durante el montaje.",
  "Cut a video by its text": "Montar un vídeo por su texto", "Transcribe the speech": "Transcribir el habla",
  "Translate and subtitle: the toolkit": "Traducir y subtitular: el toolkit", "Translate and subtitle: the language model": "Traducir y subtitular: el modelo de lenguaje",
  "Improve the sound": "Mejorar el sonido", "Check again": "Comprobar de nuevo", "Start editing": "Empezar a montar", "Checking…": "Comprobando…", "Working…": "En curso…",
  "Ready: ffmpeg is here. Open a video or a recording, highlight, produce.": "Listo: ffmpeg está aquí. Abra un vídeo o una grabación, resalte, produzca.",
  "ffmpeg is missing. On Linux: sudo apt install ffmpeg, then « Check again ».": "Falta ffmpeg. En Linux: sudo apt install ffmpeg, luego « Comprobar de nuevo ».",
  "The transcription is missing from this build.": "La transcripción falta en esta versión.",
  "faster-whisper is not installed yet: the app installs it in a folder of its own (about 300 MB, once).": "faster-whisper aún no está instalado: la aplicación lo instala en una carpeta propia (unos 300 MB, una vez).",
  "Install the transcription": "Instalar la transcripción",
  "faster-whisper is here. The model « %1 » (%2) is downloaded at the first transcription; or now:": "faster-whisper está aquí. El modelo « %1 » (%2) se descarga en la primera transcripción; o ahora:",
  "Download the model now": "Descargar el modelo ahora", "Downloading the model « %1 » (%2)…": "Descargando el modelo « %1 » (%2)…",
  "Ready: faster-whisper and the model « %1 ». A subtitle file beside the video is used instead when there is one.": "Listo: faster-whisper y el modelo « %1 ». Si hay un archivo de subtítulos junto al vídeo, se usa en su lugar.",
  "Found: %1": "Encontrado: %1",
  "The traduction toolkit does the translation, the subtitles and the sound. It is not on this computer: the app can download it (a few MB, no git).": "El toolkit traduction hace la traducción, los subtítulos y el sonido. No está en este equipo: la aplicación puede descargarlo (unos MB, sin git).",
  "Install it here": "Instalarlo aquí", "Needs the toolkit (step 2).": "Necesita el toolkit (paso 2).",
  "Ready: the libraries of finaliser.py are here. « Sound: improved » in the production block uses them.": "Listo: las bibliotecas de finaliser.py están aquí. « Sonido: mejorado » en el bloque de producción las usa.",
  "The libraries (deepfilternet, pyloudnorm, speechmos, with torch: about 500 MB) are installed at the first use, in an environment of the app's own. Or now:": "Las bibliotecas (deepfilternet, pyloudnorm, speechmos, con torch: unos 500 MB) se instalan en el primer uso, en un entorno propio de la aplicación. O ahora:",
  "On this Mac, ffmpeg and ffprobe for Apple silicon are fetched too (2 × 28 MB).": "En este Mac también se obtienen ffmpeg y ffprobe para Apple silicon (2 × 28 MB).",
  "Install now": "Instalar ahora",
  "Ollama, on this computer": "Ollama, en este equipo", "Claude Code, your own plan": "Claude Code, su propia suscripción", "Claude, an API key": "Claude, una clave API",
  "Ollama runs the model on this computer. It is not installed: get it from ollama.com (the app on a Mac, one command on Linux), open it, then « Check again ».": "Ollama ejecuta el modelo en este equipo. No está instalado: obténgalo en ollama.com (la aplicación en Mac, un comando en Linux), ábralo y luego « Comprobar de nuevo ».",
  "Get Ollama": "Obtener Ollama", "Ollama is installed but not running.": "Ollama está instalado pero no se está ejecutando.", "Start Ollama": "Iniciar Ollama",
  "Ollama answers, but this computer (%1 GB of memory) is too small for a model of the toolkit's family: choose Claude.": "Ollama responde, pero este equipo (%1 GB de memoria) es demasiado pequeño para un modelo de la familia del toolkit: elija Claude.",
  "Ollama answers. This computer (%1 GB of memory) can carry « %2 »%3; the download happens once.": "Ollama responde. Este equipo (%1 GB de memoria) puede con « %2 »%3; la descarga se hace una vez.",
  "Download %1": "Descargar %1", "Downloading %1… %2 %": "Descargando %1… %2 %", "Downloading %1…": "Descargando %1…",
  "the model is not there after the download": "el modelo no está tras la descarga",
  "Ready: Ollama answers and « %1 » replied to a test.": "Listo: Ollama responde y « %1 » contestó a una prueba.",
  "Ollama answers and « %1 » is here. One test to be sure:": "Ollama responde y « %1 » está aquí. Una prueba para estar seguros:", "Test": "Probar", "Asking « %1 »…": "Preguntando a « %1 »…",
  "Claude Code is the claude command, on your own Claude plan: no key, no bill by the call. It is not installed; the app can run its installer (from claude.ai).": "Claude Code es el comando claude, con su propia suscripción a Claude: sin clave, sin factura por llamada. No está instalado; la aplicación puede ejecutar su instalador (desde claude.ai).",
  "Install Claude Code": "Instalar Claude Code", "Installing Claude Code…": "Instalando Claude Code…",
  "Ready: Claude Code answers (%1).": "Listo: Claude Code responde (%1).",
  "Claude Code found: %1. Sign in once with your Claude account (a terminal opens: type /login and follow the browser), then test.": "Claude Code encontrado: %1. Inicie sesión una vez con su cuenta de Claude (se abre un terminal: escriba /login y siga el navegador), luego pruebe.",
  "Asking Claude Code…": "Preguntando a Claude Code…", "Sign in": "Iniciar sesión",
  "No terminal was found: open one yourself, type claude, then /login.": "No se encontró ningún terminal: abra uno usted mismo, escriba claude y luego /login.",
  "Claude Code did not answer in time.": "Claude Code no respondió a tiempo.",
  "Claude Code is installed but not signed in: click « Sign in ».": "Claude Code está instalado pero sin sesión: pulse « Iniciar sesión ».",
  "Ready: the key is accepted by Anthropic.": "Listo: Anthropic acepta la clave.",
  "A key from console.anthropic.com (API Keys › Create Key), paid by the call; the text goes to Anthropic. Paste it, then test.": "Una clave de console.anthropic.com (API Keys › Create Key), pagada por llamada; el texto va a Anthropic. Péguela y luego pruebe.",
  "Asking Anthropic…": "Preguntando a Anthropic…", "Test the key": "Probar la clave", "The key is refused by Anthropic.": "Anthropic rechaza la clave.",
  "Claude Code (your own plan)": "Claude Code (su propia suscripción)", "Claude (API key)": "Claude (clave API)",
  "Claude Code found: %1": "Claude Code encontrado: %1",
  "Claude Code is not installed: « Getting started » on the home page installs it.": "Claude Code no está instalado: « Primeros pasos », en la página de inicio, lo instala.",
  "Ollama answers.": "Ollama responde.", "Ollama does not answer: « Getting started » on the home page sets it up.": "Ollama no responde: « Primeros pasos », en la página de inicio, lo configura.",
 },
 "pt": {
  "Getting started": "Primeiros passos", "Getting started…": "Primeiros passos…", "Optional —": "Opcional —", "Model": "Modelo", "« %1 »: %2.": "« %1 »: %2.",
  "the fastest, rough words and timings: good to try the app, not to publish": "o mais rápido, palavras e tempos aproximados: bom para experimentar a aplicação, não para publicar",
  "fast, still rough; acceptable for English only": "rápido, ainda aproximado; aceitável só para inglês",
  "the default: good words in most languages, about as long as the recording lasts": "a predefinição: boas palavras na maioria das línguas, mais ou menos a duração da gravação",
  "better words and names, about three times slower, 1.5 GB": "melhores palavras e nomes, cerca de três vezes mais lento, 1,5 GB",
  "the best words, about ten times slower on a processor, 3 GB on disk and 4 GB of memory": "as melhores palavras, cerca de dez vezes mais lento num processador, 3 GB em disco e 4 GB de memória",
  "small and fast; translations to be reread": "pequeno e rápido; traduções a reler", "decent translations, a few minutes for a talk": "traduções razoáveis, alguns minutos para uma palestra",
  "good translations, fast on a Mac with 32 GB": "boas traduções, rápido num Mac de 32 GB", "the toolkit's best local model; slow without a big graphics card": "o melhor modelo local do toolkit; lento sem uma grande placa gráfica",
  "Quality and cost: Claude gives the best translations; Claude Code costs nothing beyond your plan, the API key pays by the call, both send the text to Anthropic. A local model keeps everything on this computer, slower, and the smaller the model, the rougher the translation.":
    "Qualidade e custo: o Claude dá as melhores traduções; o Claude Code não custa nada além da sua subscrição, a chave API paga por chamada, ambos enviam o texto à Anthropic. Um modelo local guarda tudo neste computador, mais devagar, e quanto mais pequeno o modelo, mais grosseira a tradução.",
  "Speed: about the length of the edit on a processor, much less with a graphics card; the length and the picture do not change.": "Velocidade: cerca da duração da montagem num processador, muito menos com placa gráfica; a duração e a imagem não mudam.",
  "Three levels. Level 1 is all you need to cut a video: it works as soon as the app is installed. Levels 2 and 3 are optional extras; if you never translate, skip them, nothing there is needed for the editing. One step at a time, each checked by a real test, each with the button that does the work. You can come back here any time: « Getting started… » on the home page, or Project ▾ › Getting started… while editing.":
    "Três níveis. O nível 1 chega para montar um vídeo: funciona assim que a aplicação está instalada. Os níveis 2 e 3 são extras opcionais; se nunca traduzir, salte-os, nada daí é preciso para a montagem. Um passo de cada vez, cada um verificado por um teste real, cada um com o botão que faz o trabalho. Pode voltar aqui a qualquer momento: « Primeiros passos… » na página inicial, ou Projeto ▾ › Primeiros passos… durante a montagem.",
  "Level 1 · Editing": "Nível 1 · A montagem", "The whole point of the app: open, highlight, produce. Nothing to install.": "O essencial da aplicação: abrir, sublinhar, produzir. Nada a instalar.",
  "That is enough for me: start editing": "Isto chega-me: começar a montar",
  "Level 2 · Translation and subtitles — optional": "Nível 2 · Tradução e legendas — opcional",
  "Only if you want to translate the text, or to cut subtitles with the toolkit's rules. Otherwise skip this level entirely.": "Só se quiser traduzir o texto, ou cortar legendas com as regras do toolkit. Caso contrário, salte este nível por completo.",
  "Level 3 · Improved sound — optional": "Nível 3 · Som melhorado — opcional",
  "Only if you want the edit's sound cleaned and levelled on the way out. Needs the toolkit of level 2 (not the model).": "Só se quiser o som da montagem limpo e nivelado à saída. Precisa do toolkit do nível 2 (não do modelo).",
  "What this computer has, and the buttons that put the rest in place.": "O que este computador tem, e os botões que põem o resto no lugar.",
  "Three levels. The first works as soon as the app is installed. The next two are optional: one step at a time, each checked by a real test, each with the button that does the work. You can come back here any time: « Getting started… » on the home page, or Project ▾ › Getting started… while editing.":
    "Três níveis. O primeiro funciona assim que a aplicação está instalada. Os dois seguintes são opcionais: um passo de cada vez, cada um verificado por um teste real, cada um com o botão que faz o trabalho. Pode voltar aqui a qualquer momento: « Primeiros passos… » na página inicial, ou Projeto ▾ › Primeiros passos… durante a montagem.",
  "Cut a video by its text": "Montar um vídeo pelo seu texto", "Transcribe the speech": "Transcrever a fala",
  "Translate and subtitle: the toolkit": "Traduzir e legendar: o toolkit", "Translate and subtitle: the language model": "Traduzir e legendar: o modelo de linguagem",
  "Improve the sound": "Melhorar o som", "Check again": "Verificar de novo", "Start editing": "Começar a montar", "Checking…": "A verificar…", "Working…": "Em curso…",
  "Ready: ffmpeg is here. Open a video or a recording, highlight, produce.": "Pronto: o ffmpeg está aqui. Abra um vídeo ou uma gravação, sublinhe, produza.",
  "ffmpeg is missing. On Linux: sudo apt install ffmpeg, then « Check again ».": "Falta o ffmpeg. No Linux: sudo apt install ffmpeg, depois « Verificar de novo ».",
  "The transcription is missing from this build.": "A transcrição falta nesta versão.",
  "faster-whisper is not installed yet: the app installs it in a folder of its own (about 300 MB, once).": "O faster-whisper ainda não está instalado: a aplicação instala-o numa pasta própria (cerca de 300 MB, uma vez).",
  "Install the transcription": "Instalar a transcrição",
  "faster-whisper is here. The model « %1 » (%2) is downloaded at the first transcription; or now:": "O faster-whisper está aqui. O modelo « %1 » (%2) é transferido na primeira transcrição; ou agora:",
  "Download the model now": "Transferir o modelo agora", "Downloading the model « %1 » (%2)…": "A transferir o modelo « %1 » (%2)…",
  "Ready: faster-whisper and the model « %1 ». A subtitle file beside the video is used instead when there is one.": "Pronto: faster-whisper e o modelo « %1 ». Um ficheiro de legendas ao lado do vídeo é usado em vez disso quando existe.",
  "Found: %1": "Encontrado: %1",
  "The traduction toolkit does the translation, the subtitles and the sound. It is not on this computer: the app can download it (a few MB, no git).": "O toolkit traduction faz a tradução, as legendas e o som. Não está neste computador: a aplicação pode transferi-lo (alguns MB, sem git).",
  "Install it here": "Instalá-lo aqui", "Needs the toolkit (step 2).": "Precisa do toolkit (passo 2).",
  "Ready: the libraries of finaliser.py are here. « Sound: improved » in the production block uses them.": "Pronto: as bibliotecas do finaliser.py estão aqui. « Som: melhorado » no bloco de produção usa-as.",
  "The libraries (deepfilternet, pyloudnorm, speechmos, with torch: about 500 MB) are installed at the first use, in an environment of the app's own. Or now:": "As bibliotecas (deepfilternet, pyloudnorm, speechmos, com torch: cerca de 500 MB) instalam-se no primeiro uso, num ambiente próprio da aplicação. Ou agora:",
  "On this Mac, ffmpeg and ffprobe for Apple silicon are fetched too (2 × 28 MB).": "Neste Mac, ffmpeg e ffprobe para Apple silicon são obtidos também (2 × 28 MB).",
  "Install now": "Instalar agora",
  "Ollama, on this computer": "Ollama, neste computador", "Claude Code, your own plan": "Claude Code, a sua subscrição", "Claude, an API key": "Claude, uma chave API",
  "Ollama runs the model on this computer. It is not installed: get it from ollama.com (the app on a Mac, one command on Linux), open it, then « Check again ».": "O Ollama corre o modelo neste computador. Não está instalado: obtenha-o em ollama.com (a aplicação no Mac, um comando no Linux), abra-o, depois « Verificar de novo ».",
  "Get Ollama": "Obter o Ollama", "Ollama is installed but not running.": "O Ollama está instalado mas não está a correr.", "Start Ollama": "Iniciar o Ollama",
  "Ollama answers, but this computer (%1 GB of memory) is too small for a model of the toolkit's family: choose Claude.": "O Ollama responde, mas este computador (%1 GB de memória) é demasiado pequeno para um modelo da família do toolkit: escolha o Claude.",
  "Ollama answers. This computer (%1 GB of memory) can carry « %2 »%3; the download happens once.": "O Ollama responde. Este computador (%1 GB de memória) aguenta « %2 »%3; a transferência faz-se uma vez.",
  "Download %1": "Transferir %1", "Downloading %1… %2 %": "A transferir %1… %2 %", "Downloading %1…": "A transferir %1…",
  "the model is not there after the download": "o modelo não está lá depois da transferência",
  "Ready: Ollama answers and « %1 » replied to a test.": "Pronto: o Ollama responde e « %1 » respondeu a um teste.",
  "Ollama answers and « %1 » is here. One test to be sure:": "O Ollama responde e « %1 » está aqui. Um teste para ter a certeza:", "Test": "Testar", "Asking « %1 »…": "A perguntar a « %1 »…",
  "Claude Code is the claude command, on your own Claude plan: no key, no bill by the call. It is not installed; the app can run its installer (from claude.ai).": "O Claude Code é o comando claude, na sua própria subscrição Claude: sem chave, sem fatura por chamada. Não está instalado; a aplicação pode correr o seu instalador (de claude.ai).",
  "Install Claude Code": "Instalar o Claude Code", "Installing Claude Code…": "A instalar o Claude Code…",
  "Ready: Claude Code answers (%1).": "Pronto: o Claude Code responde (%1).",
  "Claude Code found: %1. Sign in once with your Claude account (a terminal opens: type /login and follow the browser), then test.": "Claude Code encontrado: %1. Inicie sessão uma vez com a sua conta Claude (abre-se um terminal: escreva /login e siga o navegador), depois teste.",
  "Asking Claude Code…": "A perguntar ao Claude Code…", "Sign in": "Iniciar sessão",
  "No terminal was found: open one yourself, type claude, then /login.": "Nenhum terminal encontrado: abra um você mesmo, escreva claude, depois /login.",
  "Claude Code did not answer in time.": "O Claude Code não respondeu a tempo.",
  "Claude Code is installed but not signed in: click « Sign in ».": "O Claude Code está instalado mas sem sessão: clique « Iniciar sessão ».",
  "Ready: the key is accepted by Anthropic.": "Pronto: a chave é aceite pela Anthropic.",
  "A key from console.anthropic.com (API Keys › Create Key), paid by the call; the text goes to Anthropic. Paste it, then test.": "Uma chave de console.anthropic.com (API Keys › Create Key), paga por chamada; o texto vai para a Anthropic. Cole-a, depois teste.",
  "Asking Anthropic…": "A perguntar à Anthropic…", "Test the key": "Testar a chave", "The key is refused by Anthropic.": "A chave é recusada pela Anthropic.",
  "Claude Code (your own plan)": "Claude Code (a sua subscrição)", "Claude (API key)": "Claude (chave API)",
  "Claude Code found: %1": "Claude Code encontrado: %1",
  "Claude Code is not installed: « Getting started » on the home page installs it.": "O Claude Code não está instalado: « Primeiros passos », na página inicial, instala-o.",
  "Ollama answers.": "O Ollama responde.", "Ollama does not answer: « Getting started » on the home page sets it up.": "O Ollama não responde: « Primeiros passos », na página inicial, configura-o.",
 },
 "ru": {
  "Getting started": "Первые шаги", "Getting started…": "Первые шаги…", "Optional —": "Необязательно —", "Model": "Модель", "« %1 »: %2.": "«%1»: %2.",
  "the fastest, rough words and timings: good to try the app, not to publish": "самая быстрая, слова и тайминги грубые: годится попробовать приложение, не публиковать",
  "fast, still rough; acceptable for English only": "быстрая, всё ещё грубая; приемлема только для английского",
  "the default: good words in most languages, about as long as the recording lasts": "по умолчанию: хорошие слова на большинстве языков, примерно столько же, сколько длится запись",
  "better words and names, about three times slower, 1.5 GB": "лучше слова и имена, примерно втрое медленнее, 1,5 ГБ",
  "the best words, about ten times slower on a processor, 3 GB on disk and 4 GB of memory": "лучшие слова, примерно в десять раз медленнее на процессоре, 3 ГБ на диске и 4 ГБ памяти",
  "small and fast; translations to be reread": "маленькая и быстрая; переводы нужно перечитывать", "decent translations, a few minutes for a talk": "приличные переводы, несколько минут на беседу",
  "good translations, fast on a Mac with 32 GB": "хорошие переводы, быстро на Mac с 32 ГБ", "the toolkit's best local model; slow without a big graphics card": "лучшая локальная модель набора; медленно без мощной видеокарты",
  "Quality and cost: Claude gives the best translations; Claude Code costs nothing beyond your plan, the API key pays by the call, both send the text to Anthropic. A local model keeps everything on this computer, slower, and the smaller the model, the rougher the translation.":
    "Качество и цена: Claude даёт лучшие переводы; Claude Code не стоит ничего сверх подписки, ключ API платит за вызов, оба отправляют текст в Anthropic. Локальная модель держит всё на этом компьютере, медленнее, и чем меньше модель, тем грубее перевод.",
  "Speed: about the length of the edit on a processor, much less with a graphics card; the length and the picture do not change.": "Скорость: примерно длительность монтажа на процессоре, намного меньше с видеокартой; длительность и изображение не меняются.",
  "Three levels. Level 1 is all you need to cut a video: it works as soon as the app is installed. Levels 2 and 3 are optional extras; if you never translate, skip them, nothing there is needed for the editing. One step at a time, each checked by a real test, each with the button that does the work. You can come back here any time: « Getting started… » on the home page, or Project ▾ › Getting started… while editing.":
    "Три уровня. Уровня 1 достаточно для монтажа видео: он работает сразу после установки. Уровни 2 и 3 — необязательные дополнения; если вы никогда не переводите, пропустите их, для монтажа ничего из этого не нужно. По одному шагу, каждый проверяется реальной пробой, у каждого есть кнопка, которая делает работу. Сюда можно вернуться в любой момент: «Первые шаги…» на главной странице или Проект ▾ › Первые шаги… во время монтажа.",
  "Level 1 · Editing": "Уровень 1 · Монтаж", "The whole point of the app: open, highlight, produce. Nothing to install.": "Суть приложения: открыть, выделить, создать. Ничего устанавливать не нужно.",
  "That is enough for me: start editing": "Мне этого достаточно: начать монтаж",
  "Level 2 · Translation and subtitles — optional": "Уровень 2 · Перевод и субтитры — необязательно",
  "Only if you want to translate the text, or to cut subtitles with the toolkit's rules. Otherwise skip this level entirely.": "Только если вы хотите переводить текст или резать субтитры по правилам набора. Иначе пропустите этот уровень целиком.",
  "Level 3 · Improved sound — optional": "Уровень 3 · Улучшенный звук — необязательно",
  "Only if you want the edit's sound cleaned and levelled on the way out. Needs the toolkit of level 2 (not the model).": "Только если вы хотите, чтобы звук монтажа чистился и выравнивался на выходе. Нужен набор уровня 2 (не модель).",
  "What this computer has, and the buttons that put the rest in place.": "Что есть на этом компьютере, и кнопки, которые добавят остальное.",
  "Three levels. The first works as soon as the app is installed. The next two are optional: one step at a time, each checked by a real test, each with the button that does the work. You can come back here any time: « Getting started… » on the home page, or Project ▾ › Getting started… while editing.":
    "Три уровня. Первый работает сразу после установки. Два следующих необязательны: по одному шагу, каждый проверяется реальной пробой, у каждого есть кнопка, которая делает работу. Сюда можно вернуться в любой момент: «Первые шаги…» на главной странице или Проект ▾ › Первые шаги… во время монтажа.",
  "Cut a video by its text": "Монтаж видео по его тексту", "Transcribe the speech": "Расшифровка речи",
  "Translate and subtitle: the toolkit": "Перевод и субтитры: набор инструментов", "Translate and subtitle: the language model": "Перевод и субтитры: языковая модель",
  "Improve the sound": "Улучшить звук", "Check again": "Проверить снова", "Start editing": "Начать монтаж", "Checking…": "Проверка…", "Working…": "Выполняется…",
  "Ready: ffmpeg is here. Open a video or a recording, highlight, produce.": "Готово: ffmpeg на месте. Откройте видео или запись, выделите, создайте.",
  "ffmpeg is missing. On Linux: sudo apt install ffmpeg, then « Check again ».": "Нет ffmpeg. В Linux: sudo apt install ffmpeg, затем «Проверить снова».",
  "The transcription is missing from this build.": "В этой сборке нет расшифровки.",
  "faster-whisper is not installed yet: the app installs it in a folder of its own (about 300 MB, once).": "faster-whisper ещё не установлен: приложение установит его в собственную папку (около 300 МБ, один раз).",
  "Install the transcription": "Установить расшифровку",
  "faster-whisper is here. The model « %1 » (%2) is downloaded at the first transcription; or now:": "faster-whisper на месте. Модель «%1» (%2) загружается при первой расшифровке; или сейчас:",
  "Download the model now": "Загрузить модель сейчас", "Downloading the model « %1 » (%2)…": "Загрузка модели «%1» (%2)…",
  "Ready: faster-whisper and the model « %1 ». A subtitle file beside the video is used instead when there is one.": "Готово: faster-whisper и модель «%1». Файл субтитров рядом с видео используется вместо неё, если он есть.",
  "Found: %1": "Найден: %1",
  "The traduction toolkit does the translation, the subtitles and the sound. It is not on this computer: the app can download it (a few MB, no git).": "Набор traduction делает перевод, субтитры и звук. Его нет на этом компьютере: приложение может загрузить его (несколько МБ, без git).",
  "Install it here": "Установить сюда", "Needs the toolkit (step 2).": "Нужен набор инструментов (шаг 2).",
  "Ready: the libraries of finaliser.py are here. « Sound: improved » in the production block uses them.": "Готово: библиотеки finaliser.py на месте. «Звук: улучшенный» в блоке создания использует их.",
  "The libraries (deepfilternet, pyloudnorm, speechmos, with torch: about 500 MB) are installed at the first use, in an environment of the app's own. Or now:": "Библиотеки (deepfilternet, pyloudnorm, speechmos, с torch: около 500 МБ) устанавливаются при первом использовании в собственное окружение приложения. Или сейчас:",
  "On this Mac, ffmpeg and ffprobe for Apple silicon are fetched too (2 × 28 MB).": "На этом Mac также загружаются ffmpeg и ffprobe для Apple silicon (2 × 28 МБ).",
  "Install now": "Установить сейчас",
  "Ollama, on this computer": "Ollama, на этом компьютере", "Claude Code, your own plan": "Claude Code, ваша подписка", "Claude, an API key": "Claude, ключ API",
  "Ollama runs the model on this computer. It is not installed: get it from ollama.com (the app on a Mac, one command on Linux), open it, then « Check again ».": "Ollama запускает модель на этом компьютере. Он не установлен: возьмите его на ollama.com (приложение на Mac, одна команда в Linux), откройте, затем «Проверить снова».",
  "Get Ollama": "Получить Ollama", "Ollama is installed but not running.": "Ollama установлен, но не запущен.", "Start Ollama": "Запустить Ollama",
  "Ollama answers, but this computer (%1 GB of memory) is too small for a model of the toolkit's family: choose Claude.": "Ollama отвечает, но этот компьютер (%1 ГБ памяти) слишком мал для модели из семейства набора: выберите Claude.",
  "Ollama answers. This computer (%1 GB of memory) can carry « %2 »%3; the download happens once.": "Ollama отвечает. Этот компьютер (%1 ГБ памяти) потянет «%2»%3; загрузка выполняется один раз.",
  "Download %1": "Загрузить %1", "Downloading %1… %2 %": "Загрузка %1… %2 %", "Downloading %1…": "Загрузка %1…",
  "the model is not there after the download": "после загрузки модели нет",
  "Ready: Ollama answers and « %1 » replied to a test.": "Готово: Ollama отвечает, и «%1» ответила на пробу.",
  "Ollama answers and « %1 » is here. One test to be sure:": "Ollama отвечает, и «%1» на месте. Одна проба для уверенности:", "Test": "Проверить", "Asking « %1 »…": "Вопрос к «%1»…",
  "Claude Code is the claude command, on your own Claude plan: no key, no bill by the call. It is not installed; the app can run its installer (from claude.ai).": "Claude Code — это команда claude на вашей подписке Claude: без ключа и без оплаты за вызов. Он не установлен; приложение может запустить его установщик (с claude.ai).",
  "Install Claude Code": "Установить Claude Code", "Installing Claude Code…": "Установка Claude Code…",
  "Ready: Claude Code answers (%1).": "Готово: Claude Code отвечает (%1).",
  "Claude Code found: %1. Sign in once with your Claude account (a terminal opens: type /login and follow the browser), then test.": "Claude Code найден: %1. Войдите один раз со своей учётной записью Claude (откроется терминал: введите /login и следуйте браузеру), затем проверьте.",
  "Asking Claude Code…": "Вопрос к Claude Code…", "Sign in": "Войти",
  "No terminal was found: open one yourself, type claude, then /login.": "Терминал не найден: откройте его сами, введите claude, затем /login.",
  "Claude Code did not answer in time.": "Claude Code не ответил вовремя.",
  "Claude Code is installed but not signed in: click « Sign in ».": "Claude Code установлен, но вход не выполнен: нажмите «Войти».",
  "Ready: the key is accepted by Anthropic.": "Готово: Anthropic принимает ключ.",
  "A key from console.anthropic.com (API Keys › Create Key), paid by the call; the text goes to Anthropic. Paste it, then test.": "Ключ с console.anthropic.com (API Keys › Create Key), оплата за вызов; текст уходит в Anthropic. Вставьте его, затем проверьте.",
  "Asking Anthropic…": "Вопрос к Anthropic…", "Test the key": "Проверить ключ", "The key is refused by Anthropic.": "Anthropic отклоняет ключ.",
  "Claude Code (your own plan)": "Claude Code (ваша подписка)", "Claude (API key)": "Claude (ключ API)",
  "Claude Code found: %1": "Claude Code найден: %1",
  "Claude Code is not installed: « Getting started » on the home page installs it.": "Claude Code не установлен: «Первые шаги» на главной странице установят его.",
  "Ollama answers.": "Ollama отвечает.", "Ollama does not answer: « Getting started » on the home page sets it up.": "Ollama не отвечает: «Первые шаги» на главной странице настроят его.",
 },
}
for _code, _more in _TR_START.items():
    _TR.setdefault(_code, {}).update(_more)

# The strings of 1.9.0: the graphics card made free before the sound is improved
_TR_GPU = {
 "fr": {"Waiting for the graphics card (another task of the toolkit is using it)…": "En attente de la carte graphique (une autre tâche de la boîte à outils l'utilise)…",
        "Freeing the graphics card…": "Libération de la carte graphique…"},
 "de": {"Waiting for the graphics card (another task of the toolkit is using it)…": "Warten auf die Grafikkarte (eine andere Aufgabe des Werkzeugkastens benutzt sie)…",
        "Freeing the graphics card…": "Die Grafikkarte wird freigegeben…"},
 "es": {"Waiting for the graphics card (another task of the toolkit is using it)…": "Esperando la tarjeta gráfica (otra tarea de la caja de herramientas la está usando)…",
        "Freeing the graphics card…": "Liberando la tarjeta gráfica…"},
 "pt": {"Waiting for the graphics card (another task of the toolkit is using it)…": "À espera da placa gráfica (outra tarefa da caixa de ferramentas está a usá-la)…",
        "Freeing the graphics card…": "A libertar a placa gráfica…"},
 "ru": {"Waiting for the graphics card (another task of the toolkit is using it)…": "Ожидание видеокарты (её использует другая задача набора инструментов)…",
        "Freeing the graphics card…": "Освобождение видеокарты…"},
}
for _code, _more in _TR_GPU.items():
    _TR.setdefault(_code, {}).update(_more)


def _lang():
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        v = os.environ.get(var)
        if v:
            return v[:2].lower()
    try:                    # Windows, and macOS opened from the Finder: no LANG at all
        return QtCore.QLocale.system().name()[:2].lower()
    except Exception:
        return "en"


_LANG = _lang()


def _(key, *args):
    s = _TR.get(_LANG, {}).get(key, key)
    for i, a in enumerate(args):
        s = s.replace("%" + str(i + 1), str(a))
    return s


# ------------------------------------------------------------------------------------------
# ffmpeg, probing, the sound
# ------------------------------------------------------------------------------------------

def _bundled_tool(name):
    """A tool shipped inside the Windows/macOS build (PyInstaller), if any."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        for cand in (os.path.join(base, name), os.path.join(base, name + ".exe"), os.path.join(base, "tools", name),
                     os.path.join(base, "tools", name + ".exe")):
            if os.path.exists(cand):
                return cand
    return None


def _own_tool(name):
    """A copy the app fetched for itself into its data folder (macOS: ffmpeg and ffprobe)."""
    for cand in (os.path.join(DATA_DIR, "bin", name), os.path.join(DATA_DIR, "bin", name + ".exe")):
        if os.path.isfile(cand):
            return cand
    return None


def ffmpeg_exe():
    found = shutil.which("ffmpeg") or _bundled_tool("ffmpeg") or _own_tool("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def ffprobe_exe():
    return shutil.which("ffprobe") or _bundled_tool("ffprobe") or _own_tool("ffprobe")


# Static builds for macOS on Apple silicon (the only Mac the app is built for), fetched once when
# the toolkit needs `ffmpeg` and `ffprobe` by name on the PATH (the bundle carries imageio's
# ffmpeg under another name, and no ffprobe). The page lists its builds; the newest zip is taken.
FFMPEG_MAC_PAGE = "https://ffmpeg.martin-riedl.de/"
FFMPEG_MAC_LINK = r'href="(/download/macos/arm64/[^"]+/%s\.zip)"'


def ensure_ffmpeg_tools(progress, task):
    """ffmpeg and ffprobe reachable by name for the toolkit: the system's, or copies fetched into
    the app's bin folder (macOS). Returns the folder to put first on the PATH, or None."""
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return None
    own = os.path.join(DATA_DIR, "bin")
    if _own_tool("ffmpeg") and _own_tool("ffprobe"):
        return own
    if sys.platform != "darwin":
        raise RuntimeError(_("ffmpeg and ffprobe were not found on this computer: install ffmpeg."))
    import urllib.request
    import zipfile
    os.makedirs(own, exist_ok=True)
    req = urllib.request.Request(FFMPEG_MAC_PAGE, headers={"User-Agent": APP + "/" + VERSION})
    with urllib.request.urlopen(req, timeout=60) as r:
        page = r.read().decode("utf-8", "replace")
    for name in ("ffmpeg", "ffprobe"):
        if _own_tool(name):
            continue
        m = re.search(FFMPEG_MAC_LINK % name, page)
        if not m:
            raise RuntimeError(_("%1 could not be fetched.", name))
        progress(_("Fetching %1 (once)…", name))
        zpath = os.path.join(own, name + ".zip")
        req = urllib.request.Request(FFMPEG_MAC_PAGE.rstrip("/") + m.group(1), headers={"User-Agent": APP + "/" + VERSION})
        with urllib.request.urlopen(req, timeout=300) as r, open(zpath, "wb") as f:
            while True:
                if task.get("cancelled"):
                    raise Cancelled()
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                f.write(chunk)
        with zipfile.ZipFile(zpath) as z:
            member = next((m for m in z.namelist() if m.rstrip("/").split("/")[-1] == name), None)
            if member is None:
                raise RuntimeError(_("%1 could not be fetched.", name))
            with z.open(member) as src, open(os.path.join(own, name), "wb") as dst:
                shutil.copyfileobj(src, dst)
        os.chmod(os.path.join(own, name), 0o755)
        os.unlink(zpath)
    return own


_RUN_FLAGS = {"creationflags": 0x08000000} if sys.platform == "win32" else {}   # no console window on Windows


# ------------------------------------------------------------------------------------------
# A video from an address: YouTube, X (Twitter) and the other sites yt-dlp knows. The app keeps
# its own copy of the standalone yt-dlp in the data folder (fetched once, 40 MB) and lets it
# update itself once a day: the sites change every few weeks and yt-dlp follows.
# ------------------------------------------------------------------------------------------

BIN_DIR = os.path.join(DATA_DIR, "bin")
YTDLP_RELEASES = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/"
YTDLP_CHECK_EVERY = 24 * 3600
YTDLP_FORMAT = "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/bv*[height<=1080]+ba/b[height<=1080]/b"


def _ytdlp_asset():
    """The yt-dlp release file for this machine (a standalone build that updates itself)."""
    if sys.platform == "win32":
        return "yt-dlp.exe"
    if sys.platform == "darwin":
        return "yt-dlp_macos"
    return "yt-dlp_linux_aarch64" if platform.machine().lower() in ("aarch64", "arm64") else "yt-dlp_linux"


def ytdlp_managed():
    return os.path.join(BIN_DIR, "yt-dlp.exe" if sys.platform == "win32" else "yt-dlp")


def ytdlp_exe():
    """The app's own yt-dlp first; the system's one if the app's was never fetched."""
    managed = ytdlp_managed()
    if os.path.exists(managed):
        return managed
    return shutil.which("yt-dlp")


def is_url(text):
    return bool(re.match(r"^https?://\S+$", (text or "").strip()))


def fetch_ytdlp(progress, cancelled):
    """Downloads the standalone yt-dlp into the data folder. Afterwards it updates itself."""
    import urllib.request
    os.makedirs(BIN_DIR, exist_ok=True)
    target = ytdlp_managed()
    part = target + ".part"
    req = urllib.request.Request(YTDLP_RELEASES + _ytdlp_asset(), headers={"User-Agent": APP + "/" + VERSION})
    with urllib.request.urlopen(req, timeout=60) as r, open(part, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        got = 0
        while True:
            if cancelled():
                raise Cancelled()
            chunk = r.read(256 * 1024)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            progress(got / total if total else 0.0)
    os.chmod(part, 0o755)
    os.replace(part, target)
    write_json(os.path.join(BIN_DIR, "yt-dlp-checked.json"), {"time": time.time()})
    return target


def update_ytdlp(exe, progress):
    """`yt-dlp -U` on the app's copy, at most once a day. A failure (no network) is not an error."""
    if exe != ytdlp_managed():
        return
    stamp = os.path.join(BIN_DIR, "yt-dlp-checked.json")
    last = (read_json(stamp, {}) or {}).get("time", 0)
    if time.time() - last < YTDLP_CHECK_EVERY:
        return
    progress()
    try:
        subprocess.run([exe, "-U"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600, **_RUN_FLAGS)
    except (OSError, subprocess.TimeoutExpired):
        return
    write_json(stamp, {"time": time.time()})


def downloads_dir():
    """Where the fetched videos land: the Videos folder, in a folder of the app."""
    base = QtCore.QStandardPaths.writableLocation(QtCore.QStandardPaths.MoviesLocation)
    if not base:
        base = os.path.join(DATA_DIR, "downloads")
    folder = os.path.join(base, "Reader's Video Editor")
    os.makedirs(folder, exist_ok=True)
    return folder


def _sub_lang(path, stem):
    """'name.fr.srt' beside 'name' → 'fr'; '' when the file carries no language."""
    name = Path(path).name
    if not name.startswith(stem + "."):
        return ""
    return name[len(stem) + 1:-4]


def download_media(task, exe, url, folder, language, progress):
    """Fetches the video (MP4, 1080p at most) and its subtitles in the wanted language, if the site
    has them; returns (media path, srt path or None). The files land in `folder` under the video's
    title; what the site added for other languages is dropped."""
    work = Path(folder) / (".part-" + format(int(time.time() * 1000), "x"))
    work.mkdir(parents=True, exist_ok=True)
    cmd = [exe, "--no-playlist", "--newline", "--no-colors", "-f", YTDLP_FORMAT, "--merge-output-format", "mp4",
           "--write-subs", "--sub-langs", "all", "--sub-format", "srt/best", "--convert-subs", "srt",
           "--write-info-json", "--windows-filenames", "-o", str(work / "%(title).120B [%(id)s].%(ext)s")]
    ff = ffmpeg_exe()
    if ff:
        cmd += ["--ffmpeg-location", ff]
    cmd.append(url)
    tail = []
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace", **_RUN_FLAGS)
    task["proc"] = proc
    try:
        for line in proc.stdout:
            if task.get("cancelled"):
                proc.kill()
                break
            line = line.rstrip()
            tail = (tail + [line])[-12:]
            m = re.match(r"\[download\]\s+([\d.]+)%", line)
            if m:
                progress(float(m.group(1)) / 100, _("Downloading… %1 %", int(float(m.group(1)))))
            elif line.startswith("[Merger]"):
                progress(1.0, _("Joining the picture and the sound…"))
            elif line.startswith("[download] Destination:") or line.startswith("[info]"):
                progress(0.0, _("Downloading…"))
        proc.wait()
    finally:
        task["proc"] = None
    if task.get("cancelled"):
        shutil.rmtree(work, ignore_errors=True)
        raise Cancelled()
    if proc.returncode != 0:
        shutil.rmtree(work, ignore_errors=True)
        errors = [l for l in tail if l.startswith("ERROR:")]
        raise RuntimeError(_("The download failed: %1", (errors[-1] if errors else " ".join(tail))[:400]))
    files = list(work.iterdir())
    media = max((f for f in files if f.suffix.lower() in EXT_VIDEO | EXT_AUDIO), key=lambda f: f.stat().st_size, default=None)
    if media is None:
        shutil.rmtree(work, ignore_errors=True)
        raise RuntimeError(_("The download failed: %1", _("no video in the answer")))
    info = next((read_json(f, {}) for f in files if f.name.endswith(".info.json")), {}) or {}
    wanted = (language or (info.get("language") or "")).lower()
    stem = media.stem
    srt = None
    if wanted:
        subs = [f for f in files if f.suffix == ".srt"]
        srt = next((f for f in subs if _sub_lang(f, stem).lower() == wanted), None) or \
              next((f for f in subs if _sub_lang(f, stem).lower().startswith(wanted + "-")), None)
    final = Path(folder) / media.name
    os.replace(media, final)
    final_srt = None
    if srt is not None:
        final_srt = final.with_suffix(".srt")
        os.replace(srt, final_srt)
    shutil.rmtree(work, ignore_errors=True)
    return str(final), (str(final_srt) if final_srt else None)


def probe(path):
    """{type, duration, video:{codec, width, height, fps}, audio:{codec, rate, channels}} or {}."""
    fp = ffprobe_exe()
    if fp:
        cmd = [fp, "-v", "error", "-show_entries", "format=duration:stream=codec_type,codec_name,width,height,"
               "r_frame_rate,sample_rate,channels:stream_disposition=attached_pic", "-of", "json", path]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60, **_RUN_FLAGS)
            raw = json.loads(r.stdout or "{}")
        except (OSError, ValueError, subprocess.TimeoutExpired):
            raw = {}
        video = audio = None
        for s in raw.get("streams", []):
            kind = s.get("codec_type")
            if kind == "video" and video is None:
                if (s.get("disposition") or {}).get("attached_pic"):
                    continue
                fps = 0.0
                try:
                    num, den = (s.get("r_frame_rate") or "0/1").split("/")
                    fps = float(num) / float(den) if float(den) else 0.0
                except ValueError:
                    pass
                video = {"codec": s.get("codec_name", ""), "width": s.get("width", 0), "height": s.get("height", 0), "fps": round(fps, 3)}
            elif kind == "audio" and audio is None:
                audio = {"codec": s.get("codec_name", ""), "rate": int(s.get("sample_rate") or 0) or 48000,
                         "channels": int(s.get("channels") or 0) or 2}
        try:
            duration = float(raw.get("format", {}).get("duration") or 0)
        except ValueError:
            duration = 0.0
        if audio is None and video is None:
            return {}
        return {"type": "video" if video else "audio", "duration": duration, "video": video, "audio": audio}
    # No ffprobe (a bundle with only ffmpeg): ffmpeg's own description of the file
    ff = ffmpeg_exe()
    if not ff:
        return {}
    try:
        r = subprocess.run([ff, "-nostdin", "-hide_banner", "-i", path], capture_output=True, text=True, timeout=60, **_RUN_FLAGS)
        out = r.stderr
    except (OSError, subprocess.TimeoutExpired):
        return {}
    m = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", out)
    duration = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0
    video = audio = None
    for line in out.splitlines():
        if "Stream #" not in line:
            continue
        if ": Video:" in line and video is None and "attached pic" not in line:
            codec = re.search(r"Video: (\w+)", line)
            size = re.search(r"(\d{2,5})x(\d{2,5})", line)
            fps = re.search(r"([\d.]+) fps", line)
            video = {"codec": codec.group(1) if codec else "", "width": int(size.group(1)) if size else 0,
                     "height": int(size.group(2)) if size else 0, "fps": float(fps.group(1)) if fps else 0.0}
        elif ": Audio:" in line and audio is None:
            codec = re.search(r"Audio: (\w+)", line)
            rate = re.search(r"(\d+) Hz", line)
            ch = 1 if "mono" in line else 2
            m2 = re.search(r"(\d+) channels", line)
            if m2:
                ch = int(m2.group(1))
            audio = {"codec": codec.group(1) if codec else "", "rate": int(rate.group(1)) if rate else 48000, "channels": ch}
    if audio is None and video is None:
        return {}
    return {"type": "video" if video else "audio", "duration": duration, "video": video, "audio": audio}


def extract_audio(source, wav):
    """The sound of the file as 16 kHz mono WAV (the same one the transcription hears)."""
    wav = Path(wav)
    if wav.exists():
        return
    tmp = wav.with_name("audio16k.tmp.wav")
    r = subprocess.run([ffmpeg_exe(), "-nostdin", "-y", "-v", "error", "-i", source, "-vn", "-acodec", "pcm_s16le",
                        "-ar", "16000", "-ac", "1", str(tmp)], capture_output=True, text=True, **_RUN_FLAGS)
    if r.returncode != 0 or not tmp.exists():
        raise RuntimeError(_("This file cannot be read."))
    os.replace(tmp, wav)


def listening_copy(source, folder):
    """The file the window plays. An MP3 is played from an AAC copy (made once, in the project
    folder), as monter.py does: seeking in an MP3 of variable bitrate lands by estimate, seconds
    away on a long file, so a click on a word or the preview of the edit would miss it. Both
    copies come from ffmpeg's decoding, the one the cuts are measured on."""
    if Path(source).suffix.lower() != ".mp3":
        return source
    copy = Path(folder) / "listening.m4a"
    try:
        if copy.exists() and copy.stat().st_mtime >= Path(source).stat().st_mtime:
            return str(copy)
    except OSError:
        pass
    tmp = copy.with_name("listening.tmp.m4a")
    r = subprocess.run([ffmpeg_exe(), "-nostdin", "-y", "-v", "error", "-i", source, "-vn", "-map", "0:a:0", "-c:a", "aac",
                        "-b:a", "160k", "-aac_pns", "0", "-movflags", "+faststart", str(tmp)],
                       capture_output=True, text=True, **_RUN_FLAGS)
    if r.returncode != 0 or not tmp.exists():
        return source
    os.replace(tmp, copy)
    return str(copy)


def read_wav(path):
    import soundfile as sf
    x, sr = sf.read(str(path), dtype="float32", always_2d=True)
    return x.mean(axis=1), sr


# ------------------------------------------------------------------------------------------
# Tokens: [text, start, end, sentence]; text None = a passage without words
# ------------------------------------------------------------------------------------------

def tokens_from_words(words, duration):
    prev = 0.0
    for w in words:
        w[1] = max(w[1], prev)
        prev = w[1]
    for i, w in enumerate(words):
        w[2] = max(w[2], w[1] + 0.01)
        if i + 1 < len(words) and w[2] > words[i + 1][1]:
            w[2] = max(w[1], words[i + 1][1])
    if duration > 0:
        for w in words:
            w[1] = min(w[1], duration)
            w[2] = min(w[2], duration)
    tokens, cursor = [], 0.0
    for w in words:
        if w[1] - cursor >= PAUSE_GAP:
            tokens.append([None, round(cursor, 3), round(w[1], 3), -1])
        tokens.append([w[0], round(w[1], 3), round(w[2], 3), w[3]])
        cursor = w[2]
    if duration - cursor >= PAUSE_GAP:
        tokens.append([None, round(cursor, 3), round(duration, 3), -1])
    return place_edges(tokens, duration)


def place_edges(tokens, duration):
    if tokens and tokens[0][0] is not None and tokens[0][1] >= EDGE_GAP:
        tokens = [[None, 0.0, tokens[0][1], -1]] + tokens
    if tokens and tokens[-1][0] is not None and duration - tokens[-1][2] >= EDGE_GAP:
        tokens = tokens + [[None, tokens[-1][2], round(duration, 3), -1]]
    return tokens


def read_srt(path):
    """SRT (or the cue lines of a WebVTT) → [(start, end, text)]."""
    try:
        raw = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return []
    stamp = r"(\d+):(\d\d):(\d\d)[,.](\d{1,3})"
    cues = []
    for block in re.split(r"\n\s*\n", raw.replace("\r", "")):
        m = re.search(stamp + r"\s*-->\s*" + stamp + r"[^\n]*\n(.*)", block, re.S)
        if not m:
            continue
        g = m.groups()
        start = int(g[0]) * 3600 + int(g[1]) * 60 + int(g[2]) + int(g[3].ljust(3, "0")) / 1000
        end = int(g[4]) * 3600 + int(g[5]) * 60 + int(g[6]) + int(g[7].ljust(3, "0")) / 1000
        text = " ".join(re.sub(r"<[^>]+>|\{\\[^}]*\}", "", g[8]).split())
        if text and end > start:
            cues.append((start, end, text))
    cues.sort()
    return cues


def speech_moments(x, sr):
    """A voice alone → [[start, end], …]: when it speaks, between its pauses."""
    total = len(x) / float(sr)
    step = max(1, int(sr * 0.010))
    n = len(x) // step
    if n < 5:
        return [[0.0, total]]
    e = np.sqrt((x[:n * step].reshape(n, step) ** 2).mean(axis=1))
    loud = float(np.percentile(e, 95))
    if loud <= 1e-5:
        return [[0.0, total]]
    speaking = e > max(loud * 0.03, 1e-4)
    moments, start = [], None
    for i in range(n + 1):
        on = i < n and bool(speaking[i])
        if on and start is None:
            start = i
        elif not on and start is not None:
            a, b = start * step / sr, i * step / sr
            if moments and a - moments[-1][1] < PAUSE_SPEECH:
                moments[-1][1] = b
            elif b - a >= 0.03 or not moments:
                moments.append([a, b])
            start = None
    return moments or [[0.0, total]]


def words_of(text):
    """The words of a text; a punctuation mark standing alone stays with its word."""
    words, opening = [], ""
    for m in text.split():
        if not any(c.isalnum() for c in m):
            if m[0] in "«“([¿¡" or not words:
                opening += m + " "
            else:
                words[-1] += " " + m
            continue
        words.append(opening + m)
        opening = ""
    return words


def _strength(word):
    bare = word.rstrip(CLOSERS)
    if bare and bare[-1] in SENTENCE_END:
        return 2
    return 1 if bare and bare[-1] in PUNCTUATION else 0


def _spread(words, weights, moments):
    spoken = sum(b - a for a, b in moments)
    total = float(sum(weights))
    if spoken <= 0 or total <= 0:
        return []

    def instant(position, word_end):
        left = position
        for k, (a, b) in enumerate(moments):
            length = b - a
            if left < length or (word_end and left <= length + 1e-9) or k == len(moments) - 1:
                return a + min(max(left, 0.0), length)
            left -= length
        return moments[-1][1]

    placed, cum = [], 0.0
    for word, w in zip(words, weights):
        d = instant(cum / total * spoken, False)
        cum += w
        f = instant(cum / total * spoken, True)
        placed.append([word, d, max(f, d)])
    return placed


def spread_words(words, moments):
    """Places the words of a text on the moments the voice speaks: each word gets a share of the
    spoken time by its length; the voice's pauses go to the nearest punctuation marks."""
    moments = [[a, b] for a, b in moments if b > a]
    if not words or not moments:
        return []
    weights = [len(m) + 1 for m in words]
    total = float(sum(weights))
    spoken = sum(b - a for a, b in moments)
    borders, cum = [], 0.0
    for k in range(1, len(words)):
        cum += weights[k - 1]
        force = _strength(words[k - 1])
        if force:
            borders.append((k, cum / total * spoken, force))
    pauses, cum = [], 0.0
    for j in range(len(moments) - 1):
        cum += moments[j][1] - moments[j][0]
        length = moments[j + 1][0] - moments[j][1]
        if length >= PAUSE_MARK:
            pauses.append((length, j, cum))
    pauses.sort(reverse=True)
    tolerance = max(1.0, 0.2 * spoken)
    marks = []
    for _, j, position in pauses:
        best = None
        for k, expected, force in borders:
            gap = abs(expected - position)
            if gap > tolerance or any(k == k2 or (k < k2) != (j < j2) for k2, j2 in marks):
                continue
            score = gap + (0.0 if force == 2 else 0.6)
            if best is None or score < best[0]:
                best = (score, k)
        if best:
            marks.append((best[1], j))
    marks.sort()
    placed, k0, j0 = [], 0, 0
    for k, j in marks + [(len(words), len(moments) - 1)]:
        placed += _spread(words[k0:k], weights[k0:k], moments[j0:j + 1])
        k0, j0 = k, j + 1
    return placed


def tokens_from_srt(cues, wav, duration):
    """Subtitle cues → tokens: the words of each cue spread over the moments the voice speaks
    inside the cue (measured in the sound), the ends of sentences on its pauses."""
    x, sr = read_wav(wav)
    words, sentence = [], 0
    for start, end, text in cues:
        a, b = max(0, int(start * sr)), min(len(x), int(end * sr))
        moments = [[start + m0, start + m1] for m0, m1 in speech_moments(x[a:b], sr)] if b - a > sr // 10 else [[start, end]]
        for w, d, f in spread_words(words_of(text), moments):
            words.append([w, d, f, sentence])
            if _strength(w) == 2:
                sentence += 1
        sentence += 1
    return tokens_from_words(words, duration)


# ------------------------------------------------------------------------------------------
# Transcription on this computer (faster-whisper, CPU)
# ------------------------------------------------------------------------------------------

VENV_DIR = os.path.join(DATA_DIR, "venv")


def _venv_python():
    return os.path.join(VENV_DIR, "Scripts", "python.exe") if sys.platform == "win32" else os.path.join(VENV_DIR, "bin", "python")


def _venv_site():
    if sys.platform == "win32":
        d = os.path.join(VENV_DIR, "Lib", "site-packages")
        return d if os.path.isdir(d) else None
    lib = os.path.join(VENV_DIR, "lib")
    if not os.path.isdir(lib):
        return None
    for name in sorted(os.listdir(lib)):
        d = os.path.join(lib, name, "site-packages")
        if os.path.isdir(d):
            return d
    return None


def whisper_available():
    """faster-whisper from the Python at hand, or from the copy the app installed for itself."""
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:
        pass
    site = _venv_site()
    if site and site not in sys.path:
        sys.path.append(site)
        try:
            import faster_whisper  # noqa: F401
            return True
        except Exception:
            sys.path.remove(site)
    return False


def install_whisper(progress, cancelled):
    """pip installs faster-whisper into a small environment of the app's own (once, ~300 MB):
    nothing to type for the person. The Windows and macOS builds carry it already."""
    if getattr(sys, "frozen", False):
        raise RuntimeError("faster-whisper is missing from this build")
    os.makedirs(DATA_DIR, exist_ok=True)
    vpy = _venv_python()
    if not os.path.exists(vpy):
        progress(_("Installing the transcription (faster-whisper, once, about 300 MB)…"))
        r = subprocess.run([sys.executable, "-m", "venv", "--system-site-packages", VENV_DIR],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, **_RUN_FLAGS)
        if r.returncode != 0:
            raise RuntimeError(_("The transcription could not be installed: %1", (r.stdout or "")[-300:].strip() or "venv"))
    cmd = [vpy, "-m", "pip", "install", "--upgrade", "--disable-pip-version-check", "--progress-bar", "off", "faster-whisper"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace", **_RUN_FLAGS)
    tail = []
    for line in proc.stdout:
        if cancelled():
            proc.kill()
            raise Cancelled()
        line = line.strip()
        if line:
            tail = (tail + [line])[-8:]
            if line.startswith(("Collecting", "Downloading", "Installing")):
                progress(_("Installing the transcription (faster-whisper, once, about 300 MB)…") + "  " + line[:60])
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(_("The transcription could not be installed: %1", " ".join(tail)[-300:]))
    if not whisper_available():
        raise RuntimeError(_("The transcription could not be installed: %1", "import"))


def transcribe(wav, language, model_size, duration, progress, cancelled):
    """→ (words [[text, start, end, sentence]], language). progress(fraction) along the way."""
    from faster_whisper import WhisperModel
    os.makedirs(MODELS_DIR, exist_ok=True)
    model = WhisperModel(model_size, device="cpu", compute_type="int8", download_root=MODELS_DIR)
    # the sound is handed over as samples: no PyAV decoding, the same WAV the cuts are measured on
    audio, _sr = read_wav(wav)
    # faster-whisper's voice detection needs onnxruntime, which the Windows build leaves out:
    # without it the whole sound is listened to, rather than nothing transcribed at all
    try:
        import onnxruntime  # noqa: F401
        vad = True
    except Exception:
        vad = False
    # each window is heard on its own (no loop that repeats a sentence over a long stretch), and a
    # stretch of silence of 2 s around a doubtful passage drops what Whisper invented in it
    segments, info = model.transcribe(audio.astype(np.float32), language=language or None, word_timestamps=True,
                                      vad_filter=vad, beam_size=5, condition_on_previous_text=False,
                                      hallucination_silence_threshold=HALLUCINATION_SILENCE)
    words = []
    for k, seg in enumerate(segments):
        if cancelled():
            raise InterruptedError()
        if duration > 0:
            progress(min(seg.end / duration, 1.0))
        ws = seg.words or []
        if not ws:
            # no timings for this segment: its words spread evenly over it
            parts = words_of(seg.text)
            if parts:
                step = (seg.end - seg.start) / len(parts)
                ws = [type("W", (), {"word": p, "start": seg.start + i * step, "end": seg.start + (i + 1) * step})()
                      for i, p in enumerate(parts)]
        for w in ws:
            text = (w.word or "").strip()
            if not text:
                continue
            glued = words and words[-1][3] == k and (text[0] in "'’-" or words[-1][0][-1] in "'’")
            if glued:
                words[-1][0] += text
                words[-1][2] = float(w.end)
            else:
                words.append([text, float(w.start), float(w.end), k])
    return repair_word_timings(words), info.language


def repair_word_timings(words):
    """A word that lasts too long (Whisper stretched it over a pause or some music) is brought back
    to a plausible length on the side of its reliable neighbour: traduire.py's
    _repair_aberrant_word_timings, on the words of each segment. A cut placed on such a word
    would otherwise fall seconds away from where it is spoken."""
    by_seg = {}
    for w in words:
        by_seg.setdefault(w[3], []).append(w)
    for ws in by_seg.values():
        if len(ws) < 2:
            continue
        durs = sorted(w[2] - w[1] for w in ws)
        limit = max(WORD_MAX_DUR, WORD_RATIO * durs[len(durs) // 2])
        for i, w in enumerate(ws):
            if w[2] - w[1] <= limit:
                continue
            est = max(0.25, len(w[0]) / WORD_CPS)
            prev_gap = w[1] - ws[i - 1][2] if i > 0 else 999.0
            next_gap = ws[i + 1][1] - w[2] if i + 1 < len(ws) else 999.0
            if next_gap < 2.0:
                w[1] = max(w[2] - est, ws[i - 1][2] if i > 0 else 0.0)
            elif prev_gap < 2.0:
                w[2] = min(w[1] + est, ws[i + 1][1] if i + 1 < len(ws) else w[2])
            else:
                w[2] = w[1] + est
    return words


# ------------------------------------------------------------------------------------------
# Translation and subtitles: the traduction toolkit (traduire.py) does that work, nothing is
# written twice. The app finds it where its own launcher looks (TRADUCTION_DIR, ~/code/traduction,
# ~/code/traduction-toolkit), runs it with the toolkit's Python (TRADUCTION_PYTHON, the conda
# env interview or traduction: the rule of gui.py and monter.py) in a subprocess, and reads
# small JSON lines from it. The translation itself is traduire.py's pipeline: analysis of the
# content (summary, glossary), translation by chunks, proofreading, consistency and glossary
# checks, with a local model (Ollama) or Claude. The subtitles are its re-segmentation
# (two lines of 42 characters, 17 characters a second, the cuts on the speaker's pauses).
# ------------------------------------------------------------------------------------------

TOOLKIT_URL = "https://github.com/funkypitt/traduction-toolkit"
OLLAMA_URL = "http://localhost:11434"
LLM_LOCAL_MODEL = "gemma4:31b"          # traduire.OLLAMA_MODEL (bench 2026-06-22 of the toolkit)
LLM_CLAUDE_MODEL = "claude-opus-5"      # traduire.CLAUDE_MODEL
# The default burn-in style of traduire.py (SUBTITLE_STYLES["default"]) and its rule for a
# picture narrower than 16:9: the lines of 42 characters must still fit.
SUBTITLE_STYLE = ("FontName=Arial,FontSize=24,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
                  "BorderStyle=1,Outline=2,Shadow=1,MarginV=16")
MAX_LINE = 42                 # traduire.MAX_CHARS_PER_LINE
MAX_CUE = 7.0                 # traduire.MAX_DURATION_SEC
ISO3 = {"fr": "fra", "en": "eng", "de": "deu", "es": "spa", "it": "ita", "pt": "por", "nl": "nld", "ru": "rus",
        "pl": "pol", "ja": "jpn", "zh": "zho"}
PROJECT_EXT = ".rve.json"


def model_label(llm, model=""):
    """Who does the work, named on the patience page: Claude and its model, or Ollama and its."""
    if llm == "claude_code":
        return "Claude Code · " + LLM_CLAUDE_MODEL
    return "Claude " + LLM_CLAUDE_MODEL if llm == "claude" else "Ollama " + (model or LLM_LOCAL_MODEL)


def claude_job(cfg, llm):
    """What a toolkit job needs to reach Claude: the command of Claude Code and its work folder,
    or the key (in the environment); `claude_kind` = which of the two the analysis pass takes."""
    exe = find_claude(quick=True)
    kind = "claude_code" if (llm == "claude_code" or (llm != "claude" and exe and not (cfg.get("anthropic_key") or os.environ.get("ANTHROPIC_API_KEY")))) else "claude"
    return {"claude_exe": exe or "", "work": WORK_DIR, "claude_kind": kind}


def lang_label(code):
    """'fr' → 'Français'; a code the app does not list stays as it is; '' is the original text."""
    if not code:
        return _("Original")
    return next((name for c, name in LANGUAGES if c == code), code.upper())


TOOLKIT_DIR_APP = os.path.join(DATA_DIR, "toolkit")        # the copy the app downloads for itself (1.7.0)
TOOLKIT_ZIP = "https://github.com/funkypitt/traduction-toolkit/archive/refs/heads/main.zip"
TOOLKIT_VENV = os.path.join(DATA_DIR, "toolkit-venv")      # the app's own environment for the toolkit's libraries
TOOLKIT_PACKAGES = {"claude": ["anthropic"], "sound": ["deepfilternet", "pyloudnorm", "speechmos"]}
TOOLKIT_IMPORTS = {"deepfilternet": "df"}                  # pip name → module name, when they differ


def toolkit_dir(cfg=None):
    for d in (os.environ.get("TRADUCTION_DIR"), (cfg or {}).get("toolkit_dir"),
              os.path.expanduser("~/code/traduction"), os.path.expanduser("~/code/traduction-toolkit"), TOOLKIT_DIR_APP):
        if d and os.path.isfile(os.path.join(d, "traduire.py")):
            return d
    return None


def _toolkit_venv_python():
    return os.path.join(TOOLKIT_VENV, "Scripts", "python.exe") if sys.platform == "win32" else os.path.join(TOOLKIT_VENV, "bin", "python")


def toolkit_python():
    """The toolkit's interpreter (the rule of gui.py and monter.py): TRADUCTION_PYTHON, the conda
    envs, then the environment the app made for itself, then a system Python. traduire.py itself
    needs only the standard library, anthropic when Claude is asked for."""
    cands = [os.environ.get("TRADUCTION_PYTHON")] + [os.path.expanduser(f"~/miniconda3/envs/{e}/bin/python") for e in ("interview", "traduction")]
    cands.append(_toolkit_venv_python())
    for c in cands:
        if c and os.path.exists(c):
            return c
    return system_python()


def system_python():
    """A Python outside the bundle, to make environments with: the one running the app, or the
    system's (python3 of the Xcode tools on macOS, py or python on Windows)."""
    if not getattr(sys, "frozen", False):
        return sys.executable
    for name in (("py", "python", "python3") if sys.platform == "win32" else ("python3", "python")):
        found = shutil.which(name)
        if found:
            return found
    return None


def python_has(py, packages):
    """Whether `py` imports the modules of these pip packages."""
    mods = [TOOLKIT_IMPORTS.get(p, p) for p in packages]
    if not mods:
        return True
    try:
        r = subprocess.run([py, "-c", "import " + ", ".join(mods)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=180, **_RUN_FLAGS)
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def install_toolkit(progress, task):
    """Downloads the toolkit (the GitHub zip of its main branch, a few MB) into the app's data
    folder, without git; a copy already there is replaced. Returns its folder."""
    import urllib.request
    import zipfile
    os.makedirs(DATA_DIR, exist_ok=True)
    zpath = os.path.join(DATA_DIR, "toolkit.zip")
    progress(_("Downloading the traduction toolkit…"))
    req = urllib.request.Request(TOOLKIT_ZIP, headers={"User-Agent": APP + "/" + VERSION})
    with urllib.request.urlopen(req, timeout=120) as r, open(zpath, "wb") as f:
        while True:
            if task.get("cancelled"):
                raise Cancelled()
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
    fresh = TOOLKIT_DIR_APP + ".new"
    shutil.rmtree(fresh, ignore_errors=True)
    with zipfile.ZipFile(zpath) as z:
        names = z.namelist()
        if any(n.startswith("/") or ".." in n.split("/") for n in names):
            raise RuntimeError("archive")
        z.extractall(fresh)
        top = names[0].split("/")[0] if names else ""
    src = os.path.join(fresh, top) if top and os.path.isdir(os.path.join(fresh, top)) else fresh
    if not os.path.isfile(os.path.join(src, "traduire.py")):
        shutil.rmtree(fresh, ignore_errors=True)
        raise RuntimeError(_("The archive does not hold traduire.py."))
    shutil.rmtree(TOOLKIT_DIR_APP, ignore_errors=True)
    shutil.move(src, TOOLKIT_DIR_APP)
    shutil.rmtree(fresh, ignore_errors=True)
    os.unlink(zpath)
    return TOOLKIT_DIR_APP


def prepare_toolkit_python(packages, progress, task):
    """The Python that will run the toolkit, with `packages` importable: the one toolkit_python()
    names when it has them; otherwise the app's own environment, made once with the system
    Python and completed by pip (anthropic for Claude; deepfilternet, pyloudnorm and speechmos
    for the sound, which bring torch: about half a gigabyte, once). The person's own
    environments are never touched. pip's lines go to `progress`."""
    py = toolkit_python()
    if py and python_has(py, packages):
        return py
    vpy = _toolkit_venv_python()
    if not os.path.exists(vpy):
        base = system_python()
        if not base:
            raise RuntimeError(_("No Python was found to set the toolkit up with."))
        progress(_("Preparing the toolkit's environment (once)…"))
        r = subprocess.run([base, "-m", "venv", TOOLKIT_VENV], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, **_RUN_FLAGS)
        if r.returncode != 0 or not os.path.exists(vpy):
            raise RuntimeError(_("The toolkit's environment could not be made: %1", (r.stdout or "")[-300:].strip() or "venv"))
    if python_has(vpy, packages):
        return vpy
    what = ", ".join(packages)
    progress(_("Installing %1 (once)…", what))
    cmd = [vpy, "-m", "pip", "install", "--upgrade", "--disable-pip-version-check", "--progress-bar", "off"] + packages
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace", **_RUN_FLAGS)
    task["proc"] = proc
    tail = []
    try:
        for line in proc.stdout:
            if task.get("cancelled"):
                proc.kill()
                raise Cancelled()
            line = line.strip()
            if line:
                tail = (tail + [line])[-8:]
                if line.startswith(("Collecting", "Downloading", "Installing")):
                    progress(_("Installing %1 (once)…", what) + "  " + line[:60])
        proc.wait()
    finally:
        task["proc"] = None
    if proc.returncode != 0 or not python_has(vpy, packages):
        raise RuntimeError(_("%1 could not be installed: %2", what, " ".join(tail)[-300:] or "import"))
    return vpy


def claude_env(cfg):
    """The Anthropic key the app keeps in its settings (1.7.0), for the toolkit's subprocess;
    the environment's own key otherwise."""
    key = (cfg or {}).get("anthropic_key") or ""
    return {"ANTHROPIC_API_KEY": key} if key else {}


# ------------------------------------------------------------------------------------------
# Getting started (1.8.0): what this computer has, and the buttons that put the rest in place.
# Claude Code = the `claude` command on the person's own plan (no key), the way Reader's Writer
# uses it; Ollama = a model on this computer; or an Anthropic key.
# ------------------------------------------------------------------------------------------

STRIP_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_BASE_URL")
CLAUDE_INSTALL = "curl -fsSL https://claude.ai/install.sh | bash"
WORK_DIR = os.path.join(DATA_DIR, "work")
OLLAMA_DOWNLOAD = "https://ollama.com/download"
OLLAMA_INSTALL_LINUX = "curl -fsSL https://ollama.com/install.sh | sh"
# The local models of the toolkit's family, by what the computer can carry: (model, memory needed in GB, download in GB)
MODEL_LADDER = [("gemma4:31b", 40, 20), ("gemma4:26b-a4b", 28, 18), ("gemma4:12b", 14, 8), ("gemma4:e4b", 9, 7)]
WHISPER_SIZES = {"tiny": "75 MB", "base": "145 MB", "small": "460 MB", "medium": "1.5 GB", "large-v3": "3 GB"}
# What each choice costs and gives, said on the getting-started page (measured on a laptop's processor)
WHISPER_NOTES = {"tiny": "the fastest, rough words and timings: good to try the app, not to publish",
                 "base": "fast, still rough; acceptable for English only",
                 "small": "the default: good words in most languages, about as long as the recording lasts",
                 "medium": "better words and names, about three times slower, 1.5 GB",
                 "large-v3": "the best words, about ten times slower on a processor, 3 GB on disk and 4 GB of memory"}
LOCAL_NOTES = {"gemma4:e4b": "small and fast; translations to be reread", "gemma4:12b": "decent translations, a few minutes for a talk",
               "gemma4:26b-a4b": "good translations, fast on a Mac with 32 GB", "gemma4:31b": "the toolkit's best local model; slow without a big graphics card"}


def claude_places():
    """Where Claude Code's installers put the command: the native installer, npm (global,
    Homebrew, nvm, volta), the distribution."""
    home = os.path.expanduser("~")
    places = [os.path.join(home, ".local", "bin", "claude"), os.path.join(home, ".claude", "local", "claude"),
              os.path.join(home, ".npm-global", "bin", "claude"), os.path.join(home, ".volta", "bin", "claude"),
              "/opt/homebrew/bin/claude", "/usr/local/bin/claude", "/usr/bin/claude"]
    places += sorted(glob.glob(os.path.join(home, ".nvm", "versions", "node", "*", "bin", "claude")), reverse=True)
    return places


def login_shell_which(name):
    """The command as the login shell sees it: an app opened from the Finder or a launcher
    inherits none of the PATH set in .zshrc or .profile."""
    try:
        shell = os.environ.get("SHELL") or "/bin/sh"
        out = subprocess.run([shell, "-l", "-c", "command -v " + name], capture_output=True, text=True, timeout=10).stdout.strip().splitlines()
        if out and os.path.isfile(out[-1]) and os.access(out[-1], os.X_OK):
            return out[-1]
    except Exception:
        pass
    return None


def find_claude(quick=False):
    """The claude command; quick = without the login shell (10 s at worst)."""
    for c in claude_places():
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return shutil.which("claude") or (None if quick or sys.platform == "win32" else login_shell_which("claude"))


def claude_child_env():
    """The environment for `claude`: no API key or token (the plan is what pays), the usual
    places on the PATH, a HOME."""
    env = dict(os.environ)
    for k in STRIP_ENV:
        env.pop(k, None)
    extra = [os.path.dirname(c) for c in claude_places()] + ["/usr/local/bin", "/usr/bin", "/bin"]
    env["PATH"] = os.pathsep.join(extra + [d for d in env.get("PATH", "").split(os.pathsep) if d and d not in extra])
    env.setdefault("HOME", os.path.expanduser("~"))
    return env


def claude_test(exe):
    """One short answer through `claude -p`. Returns (ok, message)."""
    os.makedirs(WORK_DIR, exist_ok=True)
    cmd = [exe, "-p", "--output-format", "json", "--setting-sources", "", "--strict-mcp-config", "--tools", "",
           "--model", "sonnet", "Answer with the single word OK."]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180, env=claude_child_env(), cwd=WORK_DIR, **_RUN_FLAGS)
    except subprocess.TimeoutExpired:
        return False, _("Claude Code did not answer in time.")
    except OSError as ex:
        return False, str(ex)
    out = (r.stdout or "").strip()
    low = (out + " " + (r.stderr or "")).lower()
    if "not logged in" in low or "/login" in low or "authentication" in low or "oauth" in low:
        return False, _("Claude Code is installed but not signed in: click « Sign in ».")
    try:
        data = json.loads(out)
        if data.get("is_error"):
            return False, str(data.get("result", ""))[:200]
        return "ok" in str(data.get("result", "")).lower(), str(data.get("result", ""))[:80]
    except ValueError:
        return False, (r.stderr or out or "claude")[-200:]


def install_claude(progress, task):
    """The native installer of Claude Code, as its site says. Returns the command found after."""
    proc = subprocess.Popen(["bash", "-lc", CLAUDE_INSTALL], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace",
                            env=claude_child_env(), **_RUN_FLAGS)
    task["proc"] = proc
    tail = []
    try:
        for line in proc.stdout:
            if task.get("cancelled"):
                proc.kill()
                raise Cancelled()
            line = line.strip()
            if line:
                tail = (tail + [line])[-6:]
                progress(_("Installing Claude Code…") + "  " + line[:70])
        proc.wait()
    finally:
        task["proc"] = None
    found = find_claude()
    if proc.returncode != 0 or not found:
        raise RuntimeError(" ".join(tail)[-300:] or "install.sh")
    return found


def open_terminal(command):
    """Opens the person's terminal on `command` (the sign-in of Claude Code is interactive).
    Returns False when no terminal was found."""
    if sys.platform == "darwin":
        script = 'tell application "Terminal" to do script "%s"' % command.replace('"', '\\"')
        return subprocess.run(["osascript", "-e", script, "-e", 'tell application "Terminal" to activate'], capture_output=True).returncode == 0
    for term, args in (("x-terminal-emulator", ["-e"]), ("cosmic-term", ["--"]), ("gnome-terminal", ["--"]), ("konsole", ["-e"]),
                       ("xfce4-terminal", ["-x"]), ("kitty", []), ("alacritty", ["-e"]), ("xterm", ["-e"])):
        exe = shutil.which(term)
        if exe:
            try:
                subprocess.Popen([exe] + args + ["bash", "-lc", command + "; exec bash"], start_new_session=True)
                return True
            except OSError:
                continue
    return False


def find_ollama():
    places = ["/usr/local/bin/ollama", "/opt/homebrew/bin/ollama", "/usr/bin/ollama",
              "/Applications/Ollama.app/Contents/Resources/ollama", os.path.expanduser("~/Applications/Ollama.app/Contents/Resources/ollama")]
    for c in places:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return shutil.which("ollama") or (None if sys.platform == "win32" else login_shell_which("ollama"))


def ollama_json(url, path, timeout=5, data=None):
    import urllib.request
    req = urllib.request.Request(url.rstrip("/") + path, data=json.dumps(data).encode() if data is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace") or "{}")


def ollama_models(url):
    try:
        return [m["name"] for m in ollama_json(url, "/api/tags").get("models", [])]
    except Exception:
        return []


def ollama_start(exe):
    """Starts Ollama: the Mac app when it is there, else `ollama serve` detached. Waits up to 10 s."""
    try:
        if sys.platform == "darwin" and os.path.isdir("/Applications/Ollama.app"):
            subprocess.Popen(["open", "-a", "Ollama"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        return False
    for _k in range(20):
        time.sleep(0.5)
        if ollama_answers(OLLAMA_URL):
            return True
    return False


def ram_mb():
    try:
        if sys.platform == "darwin":
            return int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=5).stdout.strip() or 0) // 2 ** 20
        if sys.platform != "win32":
            for line in open("/proc/meminfo"):
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) // 1024
    except Exception:
        pass
    return 0


def vram_mb():
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10)
        return int(out.stdout.strip().splitlines()[0]) if out.returncode == 0 and out.stdout.strip() else 0
    except Exception:
        return 0


def recommended_model(ram, vram=0):
    """(model, download GB) this computer can carry, or None: a graphics card's memory, or the
    unified memory of a Mac, or the RAM (slower)."""
    room = max(vram, ram if sys.platform == "darwin" else ram * 0.7) / 1024
    for model, need, size in MODEL_LADDER:
        if room >= need:
            return model, size
    return None


def ollama_pull(url, model, progress, task):
    """Downloads a model through Ollama's API, the percentage on the way."""
    import urllib.request
    req = urllib.request.Request(url.rstrip("/") + "/api/pull", data=json.dumps({"name": model, "stream": True}).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        for raw in r:
            if task.get("cancelled"):
                raise Cancelled()
            try:
                msg = json.loads(raw.decode("utf-8", "replace"))
            except ValueError:
                continue
            if msg.get("error"):
                raise RuntimeError(msg["error"])
            total, done = msg.get("total") or 0, msg.get("completed") or 0
            if total:
                progress(_("Downloading %1… %2 %", model, int(100 * done / total)))
            else:
                progress(_("Downloading %1…", model) + "  " + str(msg.get("status", ""))[:50])
    if model not in ollama_models(url) and model + ":latest" not in ollama_models(url):
        raise RuntimeError(_("the model is not there after the download"))


def ollama_test(url, model):
    """One word from the model. Returns (ok, message)."""
    try:
        data = ollama_json(url, "/api/generate", timeout=300, data={"model": model, "prompt": "Answer with the single word OK.", "stream": False, "think": False})
        text = str(data.get("response", "")).strip()
        return bool(text), text[:80]
    except Exception as ex:
        return False, str(ex)[:200]


def anthropic_key_test(key):
    """One tiny request to the API. Returns (ok, message)."""
    import urllib.request
    import urllib.error
    body = {"model": LLM_CLAUDE_MODEL, "max_tokens": 8, "messages": [{"role": "user", "content": "Answer with the single word OK."}]}
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
        return True, "".join(b.get("text", "") for b in data.get("content", []))[:80]
    except urllib.error.HTTPError as ex:
        if ex.code in (401, 403):
            return False, _("The key is refused by Anthropic.")
        return False, f"HTTP {ex.code}"
    except Exception as ex:
        return False, str(ex)[:200]


def whisper_model_present(size):
    """faster-whisper's model files, as it stores them under the data folder."""
    for d in glob.glob(os.path.join(MODELS_DIR, f"models--*--faster-whisper-{size}", "snapshots", "*")):
        if os.path.isfile(os.path.join(d, "model.bin")):
            return True
    return False


def download_whisper_model(size):
    from faster_whisper import WhisperModel
    os.makedirs(MODELS_DIR, exist_ok=True)
    WhisperModel(size, device="cpu", compute_type="int8", download_root=MODELS_DIR)
    return whisper_model_present(size)


def probe_setup(cfg):
    """What the getting-started page shows: one dict, measured in the background."""
    tk = toolkit_dir(cfg)
    up = ollama_answers(OLLAMA_URL)
    ram, vram = ram_mb(), vram_mb()
    size = cfg.get("model", MODEL_DEFAULT)
    return {"ffmpeg": ffmpeg_exe(), "whisper": whisper_available(), "size": size, "whisper_model": whisper_model_present(size),
            "toolkit": tk, "claude": find_claude(quick=True), "ollama_bin": find_ollama(), "ollama_up": up,
            "ollama_models": ollama_models(OLLAMA_URL) if up else [], "ram": ram, "vram": vram, "recommended": recommended_model(ram, vram),
            "sound_ready": bool(tk) and python_has(toolkit_python(), TOOLKIT_PACKAGES["sound"]),
            "ffmpeg_named": bool(shutil.which("ffmpeg") and shutil.which("ffprobe")) or bool(_own_tool("ffmpeg") and _own_tool("ffprobe"))}


# What runs in the toolkit's Python: traduire.py's passes, in the order of its main(). Its own
# messages go to stderr, the app reads them for its gauge; the answers come as "@@ {json}".
TOOLKIT_BRIDGE = r"""
import json, os, sys, time, traceback
from dataclasses import asdict
job = json.load(open(sys.argv[1], encoding="utf-8"))
sys.path.insert(0, job["toolkit"])
channel = sys.stdout
sys.stdout = sys.stderr


def say(**kw):
    channel.write("@@ " + json.dumps(kw, ensure_ascii=False) + "\n")
    channel.flush()


try:
    import traduire as t
    segments = [t.Segment(d["index"], d["start"], d["end"], d["text"], d.get("text_tgt", ""),
                          words=d.get("words", []), lang=d.get("lang", "")) for d in job["segments"]]

    class _ClaudeCodeClient:
        # client.messages.create through `claude -p` on the person's own plan (no key). A forced
        # tool_use becomes an answer in JSON, parsed here into a tool_use block; thinking never shows.
        def __init__(self, exe, model, work):
            self.exe, self.model, self.work = exe, model, work
            self.messages = self

        @staticmethod
        def _flat(content):
            if isinstance(content, list):
                return "\n".join(str(b.get("text", "")) for b in content if isinstance(b, dict))
            return str(content or "")

        def create(self, **kw):
            import re as _re
            import subprocess as _sp
            from types import SimpleNamespace as NS
            system = self._flat(kw.get("system"))
            prompt = "\n\n".join(self._flat(m.get("content")) for m in kw.get("messages", []))
            tool = None
            choice = kw.get("tool_choice") or {}
            if kw.get("tools") and choice.get("type") == "tool":
                tool = next((x for x in kw["tools"] if x.get("name") == choice.get("name")), None)
            if tool:
                prompt += ("\n\n=== FORMAT DE RÉPONSE OBLIGATOIRE ===\nRéponds UNIQUEMENT par un objet JSON, sans texte autour et sans "
                           "balises ```, conforme à ce schéma JSON :\n" + json.dumps(tool.get("input_schema", {}), ensure_ascii=False)
                           + "\nRôle de cet objet : " + str(tool.get("description", "")))
            cmd = [self.exe, "-p", "--output-format", "json", "--setting-sources", "", "--strict-mcp-config", "--tools", ""]
            if self.model:
                cmd += ["--model", self.model]
            if system:
                cmd += ["--system-prompt", system]
            env = dict(os.environ)
            for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_BASE_URL"):
                env.pop(k, None)
            os.makedirs(self.work, exist_ok=True)
            # traduire.py retries only the errors of the anthropic library: an overloaded plan, a
            # timeout or an answer that is not JSON are retried here, three tries in all
            delays = [15, 45]
            while True:
                try:
                    return self._once(cmd, prompt, env, tool, _re, _sp, NS)
                except Exception as ex:
                    said = str(ex).lower()
                    if any(k in said for k in ("login", "log in", "authenticat", "credit")):
                        raise
                    if not delays:
                        if tool and isinstance(ex, ValueError):
                            # still no JSON: an empty answer, and traduire.py asks again for the missing lines
                            return NS(content=[NS(type="tool_use", name=tool["name"], input={})], stop_reason="tool_use")
                        raise
                    print(f"claude: {type(ex).__name__}: {str(ex)[:200]} — another try in {delays[0]} s", flush=True)
                    time.sleep(delays.pop(0))

        def _once(self, cmd, prompt, env, tool, _re, _sp, NS):
            r = _sp.run(cmd, input=prompt, capture_output=True, text=True, env=env, cwd=self.work, timeout=1800)
            if r.returncode != 0:
                raise RuntimeError("claude: " + (r.stderr or r.stdout or "")[-300:].strip())
            data = json.loads(r.stdout)
            text = str(data.get("result", ""))
            if data.get("is_error"):
                raise RuntimeError("claude: " + text[:300])
            if tool:
                body = _re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text.strip())
                a, b = body.find("{"), body.rfind("}")
                if a < 0 or b <= a:
                    raise ValueError("no JSON object in the answer")
                obj = json.loads(body[a:b + 1])
                return NS(content=[NS(type="tool_use", name=tool["name"], input=obj)], stop_reason="tool_use")
            return NS(content=[NS(type="text", text=text)], stop_reason="end_turn")

    def make_client(job):
        if job.get("llm") == "claude_code":
            import types
            if "anthropic" not in sys.modules:
                # traduire.py's retry wrapper imports anthropic on an error: a stand-in with its two classes
                fake = types.ModuleType("anthropic")
                fake.APIStatusError = type("APIStatusError", (Exception,), {})
                fake.APIConnectionError = type("APIConnectionError", (Exception,), {})
                sys.modules["anthropic"] = fake
            if job.get("claude_model"):
                t.CLAUDE_MODEL = job["claude_model"]
            return _ClaudeCodeClient(job["claude_exe"], job.get("claude_model", ""), job.get("work") or os.getcwd())
        if job.get("llm") == "claude":
            if not os.environ.get("ANTHROPIC_API_KEY"):
                say(error="ANTHROPIC_API_KEY")
                sys.exit(1)
            import anthropic
            if job.get("claude_model"):
                t.CLAUDE_MODEL = job["claude_model"]
            return anthropic.Anthropic()
        return t._OllamaClient(job.get("ollama_url") or t.OLLAMA_URL, job.get("ollama_model") or t.OLLAMA_MODEL)

    if job["task"] == "translate":
        src, tgt, context = job["source_lang"], job["target_lang"], job.get("context", "")
        client = make_client(job)
        # the analysis (names, glossary, domain) by Claude when the user asked for it (traduire.py's "auto")
        analysis_client = client
        if job.get("llm") == "local" and job.get("analysis_by_claude"):
            analysis_client = make_client(dict(job, llm=job.get("claude_kind") or "claude"))
        say(step="analysis")
        analysis = t.analyze_content(segments, analysis_client, src, tgt, context)
        say(step="translate")
        segments = t.translate_chunks(segments, analysis, client, src, tgt, context)
        if job.get("review", True):
            say(step="review")
            segments = t.review_translation(segments, analysis, client, src, tgt, context)
        say(step="consistency")
        segments = t.check_consistency(segments, analysis, client, src, tgt)
        say(step="glossary")
        segments = t.verify_glossary(segments, analysis, client, src, tgt)
        segments = t._clean_translation_artifacts(segments)
        segments = t._clear_same_lang_translations(segments, src, tgt)
        say(result={"segments": [asdict(s) for s in segments], "analysis": asdict(analysis)})
    elif job["task"] == "subtitles":
        subs = t.resegment(segments, job.get("target_lang") or "en")
        say(result={"cues": [[s.start, s.end, s.text] for s in subs]})
    elif job["task"] == "review":
        # the proofreading pass alone, on subtitles already cut: it shortens the ones marked too fast
        client = make_client(job)
        if job.get("max_cps"):
            t.MAX_CPS = job["max_cps"]      # the toolkit marks ⚠️ (to shorten) above this pace
        fields = ("summary", "glossary", "speakers_description", "tone", "domain")
        analysis = t.ContentAnalysis(**{k: v for k, v in (job.get("analysis") or {}).items() if k in fields})
        segments = t.review_translation(segments, analysis, client, job["source_lang"], job["target_lang"], job.get("context", ""))
        segments = t._clean_translation_artifacts(segments)
        say(result={"segments": [asdict(s) for s in segments]})
except SystemExit:
    raise
except Exception as ex:
    traceback.print_exc()
    say(error=f"{type(ex).__name__}: {ex}"[:400])
    sys.exit(1)
"""


def run_bridge(task, job, folder, on_message=None, python=None, env_extra=None):
    """Runs the toolkit on `job` (a dict) in a subprocess and returns its result dict.
    on_message(dict) receives each "@@" message and each printed line ({"line": …})."""
    folder = Path(folder)
    script = folder / "toolkit_bridge.py"
    script.write_text(TOOLKIT_BRIDGE, encoding="utf-8")
    job_file = folder / "toolkit_job.json"
    write_json(job_file, job)
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1", **(env_extra or {}))
    proc = subprocess.Popen([python or toolkit_python(), str(script), str(job_file)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, errors="replace", env=env, **_RUN_FLAGS)
    task["proc"] = proc
    result, error, tail = None, "", []
    try:
        for line in proc.stdout:
            if task.get("cancelled"):
                proc.kill()
                break
            line = line.rstrip()
            if line.startswith("@@ "):
                try:
                    msg = json.loads(line[3:])
                except ValueError:
                    continue
                if "result" in msg:
                    result = msg["result"]
                elif "error" in msg:
                    error = msg["error"]
                elif on_message:
                    on_message(msg)
            else:
                if line.strip():
                    tail = (tail + [line.strip()])[-12:]
                if on_message:
                    on_message({"line": line})
        proc.wait()
    finally:
        task["proc"] = None
    if task.get("cancelled"):
        raise Cancelled()
    if error == "ANTHROPIC_API_KEY":
        raise RuntimeError(_("ANTHROPIC_API_KEY is not set."))
    if proc.returncode != 0 or result is None:
        raise RuntimeError(error or " · ".join(tail)[-400:] or "traduire.py")
    return result


def ollama_answers(url):
    import urllib.request
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/api/tags", timeout=5) as r:
            return r.status == 200
    except Exception:
        return False


def segments_from_tokens(tokens):
    """The tokens grouped by sentence, in the shape of traduire.py's segments:
    {index, start, end, text, text_tgt, words: [{word, start, end}]}. A passage without words
    closes the sentence."""
    segs, after_pause = [], True
    for t, d, f, s in tokens:
        if t is None:
            after_pause = True
            continue
        if segs and not after_pause and segs[-1]["_s"] == s:
            seg = segs[-1]
        else:
            seg = {"index": len(segs) + 1, "start": d, "end": f, "text": "", "text_tgt": "", "words": [], "_s": s}
            segs.append(seg)
        seg["words"].append({"word": t, "start": d, "end": f})
        seg["end"] = f
        after_pause = False
    for seg in segs:
        seg["text"] = " ".join(w["word"] for w in seg["words"])
        del seg["_s"]
    return segs


def tokens_from_translation(segments, duration):
    """The translated text as tokens. The words of each segment are spread over the moments its
    original words are spoken (a share of the time by their length, the ends of sentences on
    the pauses), as monter.py reuses a translation: the positions are estimated."""
    words, sentence = [], 0
    for seg in segments:
        text = (seg.get("text_tgt") or "").strip()
        if not text:
            continue
        spans = []
        for w in seg.get("words") or []:
            try:
                a, b = float(w["start"]), float(w["end"])
            except (KeyError, TypeError, ValueError):
                continue
            if b > a:
                spans.append((a, b))
        moments = []
        for a, b in sorted(spans):
            if moments and a - moments[-1][1] < PAUSE_SPEECH:
                moments[-1][1] = max(moments[-1][1], b)
            else:
                moments.append([a, b])
        if not moments:
            moments = [[float(seg["start"]), float(seg["end"])]]
        for w, d, f in spread_words(words_of(text), moments):
            words.append([w, d, f, sentence])
            if _strength(w) == 2:
                sentence += 1
        sentence += 1
    words.sort(key=lambda w: w[1])
    return tokens_from_words(words, duration)


def tokens_in_edit(tokens, cuts):
    """The tokens of the edit on its own timeline: those inside a kept piece, shifted; a
    passage without words marks each join."""
    out, position = [], 0.0
    for k, c in enumerate(cuts):
        if k:
            out.append([None, round(position, 3), round(position, 3), -1])
        for t, d, f, s in tokens:
            if t is None:
                continue
            mid = (d + f) / 2.0
            if c["d"] <= mid <= c["f"]:
                out.append([t, round(max(d, c["d"]) - c["d"] + position, 3), round(min(f, c["f"]) - c["d"] + position, 3), s])
        position += c["f"] - c["d"]
    return out


def two_lines(text):
    """A cue of more than one line is cut at the space nearest its middle, after a punctuation
    mark when one is near."""
    if len(text) <= MAX_LINE:
        return text
    mid = len(text) / 2.0
    spaces = [i for i, c in enumerate(text) if c == " "]
    if not spaces:
        return text
    best = min(spaces, key=lambda i: abs(i - mid) - (6 if text[i - 1] in PUNCTUATION else 0))
    return text[:best].rstrip() + "\n" + text[best + 1:].lstrip()


def simple_cues(tokens):
    """Subtitles when the toolkit is not there: a cue ends on a sentence end followed by a
    pause, on a pause of 2 s, at two lines of 42 characters or at 7 seconds."""
    cues, cur = [], None
    for t, d, f, s in tokens:
        if t is None:
            if cur:
                cues.append(cur)
            cur = None
            continue
        if cur:
            text = cur[2] + " " + t
            fresh = (d - cur[1] >= 2.0 or len(text) > 2 * MAX_LINE or f - cur[0] > MAX_CUE
                     or (s != cur[3] and (d - cur[1] >= 0.9 or len(cur[2]) >= 2 * MAX_LINE - 12)))
            if not fresh:
                cur[1], cur[2] = f, text
                continue
            cues.append(cur)
        cur = [d, f, t, s]
    if cur:
        cues.append(cur)
    out = []
    for k, (a, b, text, _s) in enumerate(cues):
        b = max(b, a + 1.0)
        if k + 1 < len(cues):
            b = min(b, cues[k + 1][0] - 0.08)
        out.append([round(a, 3), round(max(b, a + 0.3), 3), two_lines(text)])
    return out


def make_cues(tokens, language, toolkit, task, folder):
    """[[start, end, text], …]: traduire.py's re-segmentation when the toolkit is there, the
    plain cutting otherwise."""
    if toolkit:
        segments = segments_from_tokens(tokens)
        for seg in segments:
            seg["text_tgt"] = seg["text"]
        if segments:
            try:
                cues = run_bridge(task, {"task": "subtitles", "toolkit": toolkit, "segments": segments, "target_lang": language or "en"}, folder)["cues"]
                return [[float(a), float(b), str(text)] for a, b, text in cues if b > a and str(text).strip()]
            except Cancelled:
                raise
            except Exception:
                pass
    return simple_cues(tokens)


def srt_text(cues):
    return "".join(f"{k + 1}\n{hmsm(a).replace('.', ',')} --> {hmsm(b).replace('.', ',')}\n{text}\n\n" for k, (a, b, text) in enumerate(cues))


def scale_style(style, width, height):
    """traduire._scale_style_for_video: libass scales with the picture, but a picture narrower
    than 16:9 (square, vertical) needs smaller letters for its lines to fit."""
    if width <= 0 or height <= 0 or width / height >= 16 / 9 - 0.05:
        return style
    ratio = width / (height * 16 / 9)

    def scale(m):
        name, val = m.group(1), int(m.group(2))
        return f"{name}={max(14 if name == 'FontSize' else 8, round(val * ratio))}"
    return re.sub(r"(FontSize|MarginV)=(\d+)", scale, style)


def filter_path(path):
    """A path inside an ffmpeg filter: forward slashes, the colon and the quote escaped."""
    return str(path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


# Instagram-like captions (1.6.0): the style the short videos of 2025-2026 share — a few big words
# at a time in a heavy sans, white with a black outline, centred near the bottom of the picture
# (higher on a vertical one, above the band the apps cover), the spoken word in one accent
# colour (the app's stabilo yellow). Sizes are shares of the picture, so a vertical, a square and a landscape
# picture get the same look.
CAPTION_FONT = "Montserrat ExtraBold"   # bundled in packaging/fonts (OFL)
CAPTION_WORDS = 4                       # words per card at most
CAPTION_CHARS = 26                      # characters per card at most (long words make shorter cards)
CAPTION_PAUSE = 0.8                     # a pause this long ends a card
CAPTION_HOLD = 0.5                      # how long a card stays after its last word, when nothing follows
CAPTION_ACCENT = "&H4AE8FF&"            # STABILO #ffe84a as ASS blue-green-red


def caption_cards(tokens):
    """The words of the edit grouped into cards: [[(text, start, end), …], …]. A card ends on a
    join, at a sentence end, on a pause, at CAPTION_WORDS words or CAPTION_CHARS characters."""
    cards, card, chars, last = [], [], 0, None
    for t, d, f, sidx in tokens:
        if t is None:
            if card:
                cards.append(card)
            card, chars, last = [], 0, None
            continue
        word = re.sub(r"[{}\\]", "", t).strip()
        if not word:
            continue
        if card and (sidx != last[3] or d - last[2] > CAPTION_PAUSE or len(card) >= CAPTION_WORDS
                     or chars + 1 + len(word) > CAPTION_CHARS or last[0].rstrip()[-1:] in ".!?…"):
            cards.append(card)
            card, chars = [], 0
        card.append((word, d, f))
        chars += len(word) + (1 if chars else 0)
        last = (word, d, f, sidx)
    if card:
        cards.append(card)
    return cards


def _ass_time(t):
    t = max(0.0, t)
    h, rest = divmod(t, 3600)
    m, sec = divmod(rest, 60)
    return f"{int(h)}:{int(m):02d}:{sec:05.2f}"


def captions_ass(tokens, width, height):
    """An ASS subtitle file of Instagram-like captions for the words given (on the edit's
    timeline): one event per spoken word, showing its card with that word in the accent colour."""
    W, H = (width, height) if width > 0 and height > 0 else (1280, 720)
    size = max(18, round(0.065 * min(W, H)))
    outline, shadow = max(2, round(size * 0.08)), max(1, round(size * 0.06))
    # near the bottom, like subtitles, so the cards never cover a face framed in the middle; higher
    # only on a vertical picture, above the band the apps lay over a Reel (about a quarter)
    ml, mv = round(0.08 * W), round((0.24 if H > W * 1.2 else 0.10) * H)
    L = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
         "[V4+ Styles]",
         "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
         "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
         f"Style: Captions,{CAPTION_FONT},{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,{outline},{shadow},2,{ml},{ml},{mv},1",
         "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    cards = caption_cards(tokens)
    for k, card in enumerate(cards):
        start = card[0][1]
        end = card[-1][2] + CAPTION_HOLD
        if k + 1 < len(cards):
            end = min(end, cards[k + 1][0][1])
        end = max(end, card[-1][2])
        at = start
        for i, (word, d, f) in enumerate(card):
            a = at
            b = card[i + 1][1] if i + 1 < len(card) else end
            b = max(b, a + 0.05)
            at = b
            text = " ".join(("{\\c" + CAPTION_ACCENT + "}" + w + "{\\c&HFFFFFF&}") if j == i else w for j, (w, _d, _f) in enumerate(card))
            L.append(f"Dialogue: 0,{_ass_time(a)},{_ass_time(b)},Captions,,0,0,0,,{text}")
    return "\n".join(L) + "\n"


# ---- the subtitle editor: cues on the timeline of the whole file, kept in the project ----
MAX_CPS = 22                  # characters a second a subtitle must not exceed (the toolkit's 17 is its target, harsh as a limit)
CPS_TARGET = 17               # traduire.MAX_CPS: comfortable reading; above it the pace is shown amber, above MAX_CPS red
MIN_CUE = 1.0                 # traduire.MIN_DURATION_SEC
NUDGE = 0.1                   # what one press of a timing button moves, in seconds


def clock(t):
    """A time for the editor: 1:02.345, with the hours when there are some."""
    ms = int(round(max(0.0, t) * 1000))
    h, r = divmod(ms, 3600000)
    m, r = divmod(r, 60000)
    s, ms = divmod(r, 1000)
    return f"{h}:{m:02d}:{s:02d}.{ms:03d}" if h else f"{m}:{s:02d}.{ms:03d}"


def parse_clock(text):
    """1:02.345, 62.3 or 0:01:02,345 → seconds; None when it is not a time."""
    text = text.strip().replace(",", ".")
    if not re.fullmatch(r"(\d+:){0,2}\d+(\.\d*)?", text):
        return None
    value = 0.0
    for part in text.split(":"):
        value = value * 60 + float(part or 0)
    return value


def cue_issues(cues, k):
    """What is wrong with a subtitle's shape and timing, for the editor: [(level, text)], the
    level "bad" or "warn". The pace has its own colour (pace_level)."""
    a, b, text = cues[k]
    lines = text.split("\n")
    longest = max(len(line) for line in lines)
    dur = b - a
    out = []
    if longest > MAX_LINE:
        out.append(("bad", _("A line of %1 characters (the limit is %2)", longest, MAX_LINE)))
    if len(lines) > 2:
        out.append(("bad", _("%1 lines", len(lines))))
    if k + 1 < len(cues) and b > cues[k + 1][0] + 0.001:
        out.append(("bad", _("Overlaps the next subtitle")))
    if dur > MAX_CUE + 0.05:
        out.append(("warn", _("Longer than %1 s", int(MAX_CUE))))
    if dur < MIN_CUE - 0.05:
        out.append(("warn", _("Shorter than %1 s", int(MIN_CUE))))
    return out


def cue_pace(cue):
    a, b, text = cue
    return len(" ".join(text.split("\n"))) / (b - a) if b > a else 0.0


def pace_level(cue):
    """0 comfortable (up to CPS_TARGET), 1 fast (up to MAX_CPS), 2 too fast."""
    pace = cue_pace(cue)
    return 2 if pace > MAX_CPS + 0.5 else (1 if pace > CPS_TARGET + 0.5 else 0)


def pace_note(cue):
    pace, level = cue_pace(cue), pace_level(cue)
    if level == 2:
        return _("Too fast: %1 characters a second (the limit is %2)", round(pace), MAX_CPS)
    if level == 1:
        return _("Fast: %1 characters a second (comfortable up to %2)", round(pace), CPS_TARGET)
    return ""


PACE_COLOURS = ("#2e7d32", "#b26a00", "#b3261e")     # green, amber, red, on the paper


def cue_at(cues, t):
    """The subtitle shown at an instant, or -1."""
    for k, (a, b, _text) in enumerate(cues):
        if a <= t < b:
            return k
    return -1


def words_during(tokens, a, b):
    """The words spoken between two instants (their middle inside): the original beside a cue."""
    return " ".join(t for t, d, f, _s in tokens if t is not None and a <= (d + f) / 2.0 <= b)


def cues_in_edit(cues, cuts):
    """The subtitles of the edit on its own timeline: each one trimmed to the kept pieces and
    shifted; what a cut leaves of a cue is dropped when it is less than half of it and under a
    second, the two halves of a cue around a join are made one again."""
    out, position = [], 0.0
    cues = sorted(cues)
    for c in cuts:
        for a, b, text in cues:
            lo, hi = max(a, c["d"]), min(b, c["f"])
            if hi > lo and hi - lo >= min(1.0, (b - a) * 0.5):
                start, end = round(lo - c["d"] + position, 3), round(hi - c["d"] + position, 3)
                if out and out[-1][2] == text and start - out[-1][1] < 0.15:
                    out[-1][1] = end
                else:
                    out.append([start, end, text])
        position += c["f"] - c["d"]
    return out


# ------------------------------------------------------------------------------------------
# The cuts
# ------------------------------------------------------------------------------------------

def margins(fade):
    before = min(max(fade * 0.6, 0.15), 0.5)
    after = min(max(fade * 0.8, 0.25), 0.6)
    return before, after, max(before, after) + 0.25


def quiet_point(sound, a, b, aim):
    """The quietest instant of [a, b] nearest to `aim`."""
    aim = min(max(aim, a), b)
    if b - a < 0.03 or sound is None:
        return aim
    sr = sound.samplerate
    step = max(1, int(sr * 0.010))
    start = max(0, int((a - 0.015) * sr))
    end = min(sound.frames, int((b + 0.015) * sr))
    if end - start < step * 3:
        return aim
    sound.seek(start)
    x = sound.read(end - start, dtype="float32", always_2d=True).mean(axis=1)
    n = len(x) // step
    if n < 3:
        return aim
    e = np.sqrt((x[:n * step].reshape(n, step) ** 2).mean(axis=1) + 1e-12)
    e = np.convolve(e, np.ones(3) / 3.0, mode="same")
    t = (start + (np.arange(n) + 0.5) * step) / sr
    inside = (t >= a) & (t <= b)
    if not inside.any():
        return aim
    threshold = max(float(e[inside].min()) * 2.0, 1e-4)
    quiet = inside & (e <= threshold)
    if not quiet.any():
        return aim
    tq = t[quiet]
    return float(tq[int(np.argmin(np.abs(tq - aim)))])


def clean_ranges(ranges, n):
    raw = []
    for p in ranges:
        try:
            i, j = int(p[0]), int(p[1])
        except (TypeError, ValueError, IndexError):
            continue
        i, j = max(0, min(i, j)), min(n - 1, max(i, j))
        if i <= j:
            raw.append((i, j))
    clean = []
    for i, j in sorted(raw):
        if clean and i <= clean[-1][1] + 1:
            clean[-1] = (clean[-1][0], max(j, clean[-1][1]))
        else:
            clean.append((i, j))
    return clean


def complement(clean, n):
    rest, start = [], 0
    for i, j in clean:
        if i > start:
            rest.append((start, i - 1))
        start = j + 1
    if start < n:
        rest.append((start, n - 1))
    return rest


def compute_cuts(wav, tokens, ranges, fade, duration, inverse=False, estimated=False):
    """Ranges of tokens [i, j] → pieces kept {d, f, fi, fo, vi, vo, range} in seconds."""
    n = len(tokens)
    clean = clean_ranges(ranges, n)
    if inverse:
        clean = complement(clean, n)
    if not clean:
        return []
    end_media = duration if duration > 0 else tokens[-1][2]
    aim_before, aim_after, reach = margins(fade)
    overrun = 0.0 if inverse else 0.04
    play = ESTIMATED_PLAY if estimated else 0.0
    sound = None
    if wav and Path(wav).exists():
        try:
            import soundfile as sf
            sound = sf.SoundFile(str(wav))
        except Exception:
            sound = None
    cuts = []
    try:
        for i, j in clean:
            d_raw, f_raw = tokens[i][1], tokens[j][2]
            k = i - 1
            while k >= 0 and tokens[k][0] is None:
                k -= 1
            prev_end = tokens[k][2] if k >= 0 else 0.0
            k = j + 1
            while k < n and tokens[k][0] is None:
                k += 1
            next_start = tokens[k][1] if k < n else end_media
            a = max(0.0, prev_end - overrun - play, d_raw - reach)
            d = quiet_point(sound, min(a, d_raw), min(d_raw + play, f_raw), d_raw - aim_before)
            b = min(end_media, next_start + overrun + play, f_raw + reach)
            f = quiet_point(sound, max(f_raw - play, d), max(b, f_raw), f_raw + aim_after)
            if inverse and i == 0:
                d = 0.0
            if inverse and j == n - 1:
                f = end_media
            if cuts and d < cuts[-1]["f"]:
                middle = (tokens[cuts[-1]["range"][1] + 1][1] + tokens[i - 1][2]) / 2.0
                middle = min(max(middle, cuts[-1]["d"] + 0.05), f)
                cuts[-1]["f"] = d = middle
            if f - d < 0.05:
                continue
            if fade > 0:
                fi = min(max(d_raw - d, 0.03), fade)
                fo = min(max(f - f_raw, 0.03), fade)
            else:
                fi = fo = ANTI_CLICK
            cuts.append({"d": d, "f": f, "fi": fi, "fo": fo, "range": [i, j]})
    finally:
        if sound is not None:
            sound.close()
    for k, c in enumerate(cuts):
        # no fade from black at the very start: the first frame is the thumbnail the social networks show
        c["vi"] = k > 0 and c["d"] - cuts[k - 1]["f"] >= IMAGE_FADE_MIN
        c["vo"] = k == len(cuts) - 1 or cuts[k + 1]["d"] - c["f"] >= IMAGE_FADE_MIN
    for c in cuts:
        half = (c["f"] - c["d"]) / 2.0
        c["d"], c["f"] = round(c["d"], 3), round(c["f"], 3)
        c["fi"] = round(min(c["fi"], half), 3)
        c["fo"] = round(min(c["fo"], half), 3)
    return cuts


# ------------------------------------------------------------------------------------------
# Producing the edit
# ------------------------------------------------------------------------------------------

class Cancelled(Exception):
    pass


def _run_ffmpeg(cmd, task, log, on_time=None):
    cmd = cmd[:1] + ["-nostdin", "-v", "error", "-progress", "pipe:1", "-nostats"] + cmd[1:]
    with open(log, "w") as err:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=err, text=True, **_RUN_FLAGS)
    task["proc"] = proc
    try:
        for line in proc.stdout:
            if task.get("cancelled"):
                proc.kill()
                break
            if on_time and line.startswith("out_time_us="):
                try:
                    on_time(int(line.split("=", 1)[1]) / 1e6)
                except ValueError:
                    pass
        proc.wait()
    finally:
        task["proc"] = None
    if task.get("cancelled"):
        raise Cancelled()
    if proc.returncode != 0:
        try:
            with open(log) as f:
                detail = f.read()[-600:].strip()
        except OSError:
            detail = ""
        raise RuntimeError(detail or "ffmpeg failed")


# The centre of the picture, as a square of its shorter side (even, for yuv420p). iw and ih are
# the size as displayed: ffmpeg turns a phone's picture upright before the filters run.
SQUARE_FILTER = "crop=2*floor(min(iw\\,ih)/2):2*floor(min(iw\\,ih)/2)"

# finaliser.py's nine passes, as the gauge names them
FINISH_STEPS = {1: "Channels", 2: "Hum and rumble", 3: "Analysis", 4: "Background noise", 5: "Levelling",
                6: "Level", 7: "Fades", 8: "Encoding", 9: "Check"}


# finaliser.py's messages the app knows, said in its own words
FINISH_ERRORS = (("ffmpeg introuvable", "ffmpeg and ffprobe were not found on this computer: install ffmpeg."),
                 ("Dépendances manquantes", "some of the toolkit's libraries are missing."),
                 ("pyloudnorm manquant", "some of the toolkit's libraries are missing."),
                 ("muet, ou trop court", "this file is silent, or too short to be analysed."),
                 ("n'a pas d'image", "this file has no picture."))


GPU_LOCK = os.path.expanduser("~/.cache/traduction_gpu.lock")   # traduire.acquire_gpu_lock's file
GPU_FREE_MIB = 6000                                               # traduire.wait_for_vram_release's floor


def take_gpu_lock(task):
    """The toolkit's shared lock on the graphics card (Linux and macOS), so that finaliser.py never
    runs beside a transcription or a dub of the toolkit. Returns the open file (closing it frees
    the lock), or None where there is no such lock."""
    try:
        import fcntl
    except ImportError:
        return None
    try:
        os.makedirs(os.path.dirname(GPU_LOCK), exist_ok=True)
        fh = open(GPU_LOCK, "w")
    except OSError:
        return None
    while True:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fh
        except BlockingIOError:
            task["message"] = _("Waiting for the graphics card (another task of the toolkit is using it)…")
            if task.get("cancelled"):
                fh.close()
                raise Cancelled()
            time.sleep(1.0)
        except OSError:
            fh.close()
            return None


def free_gpu(task, url=OLLAMA_URL, timeout=60.0):
    """traduire.free_gpu_for_task: the models Ollama keeps loaded (a translation a few minutes ago
    leaves gemma4:31b in the card for five minutes) are unloaded, then the card's memory is
    awaited, so that DeepFilterNet does not run out of it."""
    unloaded = False
    try:
        for m in (ollama_json(url, "/api/ps", timeout=3) or {}).get("models", []):
            name = m.get("name") or m.get("model")
            if name:
                task["message"] = _("Freeing the graphics card…")
                ollama_json(url, "/api/generate", timeout=30, data={"model": name, "keep_alive": 0})
                unloaded = True
    except Exception:
        pass
    if not unloaded or not shutil.which("nvidia-smi"):
        return
    end = time.time() + timeout
    while time.time() < end and not task.get("cancelled"):
        try:
            out = subprocess.run(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                                 capture_output=True, text=True, timeout=10, **_RUN_FLAGS).stdout
            if min(int(v) for v in out.split()) >= GPU_FREE_MIB:
                return
        except Exception:
            return
        time.sleep(1.0)


def finish_sound(task, toolkit, src, fmt, channels, folder, share=(0.0, 1.0), python=None, path_first=None):
    """finaliser.py of the toolkit on `src`, written into `folder` as `<stem>_podcast.<fmt>`:
    the sound finished as for a podcast (mains hum, the background when it is a steady noise,
    the level to the norm, constant gain), its length kept to the sample so the log, the edit
    list and the subtitles stay true (--sans-rognage). Returns (path, the JSON report)."""
    script = os.path.join(toolkit, "finaliser.py")
    if not os.path.isfile(script):
        raise RuntimeError(_("finaliser.py is not in the toolkit folder %1.", toolkit))
    src, folder = Path(src), Path(folder)
    cmd = [python or toolkit_python(), script, str(src), "--format", fmt, "--sans-rognage", "--forcer",
           "--canaux", "stereo" if channels >= 2 else "mono", "-o", str(folder)]
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    if path_first:
        env["PATH"] = path_first + os.pathsep + env.get("PATH", "")
    lock = take_gpu_lock(task)
    try:
        free_gpu(task)
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace",
                                env=env, cwd=toolkit, **_RUN_FLAGS)
    except BaseException:
        if lock:
            lock.close()
        raise
    task["proc"] = proc
    a, b = share
    lines = []
    try:
        for line in proc.stdout:
            if task.get("cancelled"):
                proc.kill()
                break
            line = line.strip()
            if not line:
                continue
            lines.append(line)
            m = re.match(r"\[(\d)/9\]", line)
            if m:
                k = int(m.group(1))
                task["progress"] = a + (b - a) * (k - 1) / 9.0
                task["message"] = _("Sound: %1", _(FINISH_STEPS.get(k, "")))
        proc.wait()
    finally:
        task["proc"] = None
        if lock:
            lock.close()
    if task.get("cancelled"):
        raise Cancelled()
    done = folder / f"{src.stem}_podcast.{fmt}"
    if proc.returncode != 0 or not done.exists():
        failed = [l.split(":", 1)[1].strip() for l in lines if l.startswith("✗") and ":" in l]
        detail = failed[0] if failed else " · ".join(lines[-6:])
        whole = "\n".join(lines)
        for french, known in FINISH_ERRORS:
            if french in whole:
                detail = _(known)
                break
        raise RuntimeError(_("the sound could not be improved (finaliser.py): %1", detail[-500:]))
    report = read_json(folder / f"{src.stem}_podcast.json", {}) or {}
    task["progress"] = b
    return done, report


def sound_summary(report):
    """What finaliser.py did, in the words of the app, from its JSON report; [] without one."""
    if not report:
        return []
    plan, a, m = report.get("plan") or {}, report.get("analyse") or {}, report.get("mesures") or {}
    L = []
    if a.get("ronflette"):
        L.append(_("mains hum at %1 Hz removed", ", ".join(str(h) for h in a["ronflette"])))
    what = str(m.get("debruitage") or "")
    if plan.get("debruitage") and "DeepFilterNet" in what:
        L.append(_("background noise reduced, by %1 dB at most", plan["debruitage"]))
    elif plan.get("debruitage") and "spectrale" in what:
        L.append(_("background noise reduced gently (the stronger cleaning harmed the voice)"))
    elif plan.get("debruitage"):
        L.append(_("background left as it is: cleaning it harmed the voice"))
    elif a.get("ecart_db") is not None and a["ecart_db"] >= 40:
        L.append(_("background already clean (%1 dB under the voice)", int(round(a["ecart_db"]))))
    elif a.get("part_tonale") is not None and a["part_tonale"] > 0.25:
        L.append(_("background left as it is: music, not noise"))
    elif (a.get("regularite_db") or 0) > 5:
        L.append(_("background left as it is: it changes along the file"))
    if plan.get("nivelage"):
        L.append(_("uneven voice levels evened out, slowly"))
    if m.get("gain_db") is not None:
        final = (m.get("final") or {}).get("lufs")
        line = _("level %1 dB", f"{m['gain_db']:+.1f}") + (f" → {final:.1f} LUFS" if final is not None else "")
        if m.get("limiteur"):
            line += ", " + _("%1 dB taken from the peaks alone", f"{m.get('retire_aux_cretes_db') or 0:.1f}")
        L.append(line)
    d = report.get("dnsmos") or {}
    if (d.get("avant") or {}).get("sig") and (d.get("apres") or {}).get("sig"):
        L.append(_("voice quality %1 → %2 (DNSMOS, out of 5)", d["avant"]["sig"], d["apres"]["sig"]))
    return L


def produce_video(task, source, cuts, fade, image_fade, out, burn=None, tracks=(), square=False, finish=None):
    """One intermediate file per piece (x264 picture + raw sound), then one join: the picture is
    copied as it is, the sound encoded once. With `burn` = (srt, style) the subtitles are drawn
    into the picture at the join (encoded once more, as traduire.py burns them); `tracks` =
    [(language, srt), …] go into the MP4 as subtitle tracks one can switch on. `square` takes
    the centre of the picture as a 1:1 square (each piece, before its fades). `finish` =
    {toolkit, channels} hands the joined sound to finaliser.py: the join is then a MOV with the
    raw sound, finished into an MP4, and the tracks are added in a last copy."""
    ff = ffmpeg_exe()
    total = sum(c["f"] - c["d"] for c in cuts)
    tmp = Path(tempfile.mkdtemp(prefix="edit_", dir=str(out.parent)))
    share = 0.6 if burn else 0.96
    if finish:
        share *= 0.55
    sub = None
    try:
        done, pieces = 0.0, []
        for k, c in enumerate(cuts):
            dur = c["f"] - c["d"]
            task["message"] = _("Piece %1 of %2", k + 1, len(cuts))
            vf = [SQUARE_FILTER] if square else []
            if image_fade and fade > 0:
                fv = min(fade, dur / 2.0)
                if c.get("vi", True):
                    vf.append(f"fade=t=in:st=0:d={fv:.3f}")
                if c.get("vo", True):
                    vf.append(f"fade=t=out:st={dur - fv:.3f}:d={fv:.3f}")
            af = [f"afade=t=in:st=0:d={c['fi']:.3f}:curve=hsin",
                  f"afade=t=out:st={max(0.0, dur - c['fo']):.3f}:d={c['fo']:.3f}:curve=hsin"]
            piece = tmp / f"piece_{k:04d}.mkv"
            cmd = [ff, "-y", "-ss", f"{c['d']:.3f}", "-i", source, "-t", f"{dur:.3f}", "-map", "0:v:0", "-map", "0:a:0"]
            if vf:
                cmd += ["-vf", ",".join(vf)]
            cmd += ["-af", ",".join(af), "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p",
                    "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", str(piece)]
            base = done

            def advance(t, base=base, dur=dur):
                task["progress"] = share * (base + min(t, dur)) / total

            _run_ffmpeg(cmd, task, str(tmp / "ffmpeg.log"), advance)
            pieces.append(piece)
            done += dur
        task["message"] = _("Joining")
        lst = tmp / "list.txt"
        with open(lst, "w", encoding="utf-8") as f:
            for p in pieces:
                f.write("file '" + str(p).replace("'", "'\\''") + "'\n")
        partial = out.with_name(out.stem + ".partial" + out.suffix)
        joined = tmp / "joined.mov" if finish else partial
        cmd = [ff, "-y", "-f", "concat", "-safe", "0", "-i", str(lst)]
        if not finish:
            for _lang, srt in tracks:
                cmd += ["-i", str(srt)]
        cmd += ["-map", "0:v:0", "-map", "0:a:0"]
        if not finish:
            for k in range(len(tracks)):
                cmd += ["-map", f"{k + 1}:0"]
        if burn:
            # ffmpeg's filter parser is picky about paths: a copy with a plain name (as traduire.py)
            sub = Path(tempfile.mkdtemp(prefix="subs_")) / ("subs" + Path(burn[0]).suffix.lower())
            shutil.copy2(burn[0], sub)
            vf = f"subtitles='{filter_path(sub)}'"
            if burn[1]:
                vf += f":force_style='{burn[1]}'"
            fonts = bundled_fonts_dir()
            if fonts:
                vf += f":fontsdir='{filter_path(fonts)}'"
            cmd += ["-vf", vf, "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p"]
        else:
            cmd += ["-c:v", "copy"]
        if finish:
            cmd += ["-c:a", "copy", str(joined)]
        else:
            cmd += ["-c:a", "aac", "-b:a", "192k"]
            if tracks:
                cmd += ["-c:s", "mov_text"]
                for k, (lang, _srt) in enumerate(tracks):
                    cmd += [f"-metadata:s:s:{k}", "language=" + ISO3.get(lang, "und")]
            cmd += ["-movflags", "+faststart", str(partial)]
        join_end = share + (1.0 - share) * (0.3 if finish else 1.0)
        try:
            _run_ffmpeg(cmd, task, str(tmp / "ffmpeg.log"), lambda t: task.update(progress=share + (join_end - share) * min(t / total, 1.0)))
            if finish:
                finished, report = finish_sound(task, finish["toolkit"], joined, "mp4", finish["channels"], tmp, share=(join_end, 0.98),
                                                python=finish.get("python"), path_first=finish.get("path_first"))
                task["sound"] = report
                task["message"] = _("Joining")
                cmd = [ff, "-y", "-i", str(finished)]
                for _lang, srt in tracks:
                    cmd += ["-i", str(srt)]
                cmd += ["-map", "0:v:0", "-map", "0:a:0"]
                for k in range(len(tracks)):
                    cmd += ["-map", f"{k + 1}:0"]
                cmd += ["-c:v", "copy", "-c:a", "copy"]
                if tracks:
                    cmd += ["-c:s", "mov_text"]
                    for k, (lang, _srt) in enumerate(tracks):
                        cmd += [f"-metadata:s:s:{k}", "language=" + ISO3.get(lang, "und")]
                cmd += ["-movflags", "+faststart", str(partial)]
                _run_ffmpeg(cmd, task, str(tmp / "ffmpeg.log"))
            os.replace(partial, out)
        finally:
            if partial.exists():
                partial.unlink()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        if sub is not None:
            shutil.rmtree(sub.parent, ignore_errors=True)


def produce_audio(task, source, cuts, audio, fmt, out, finish=None):
    """The sound is decoded once from start to end and the pieces taken on the fly, to the sample.
    With `finish` = {toolkit, channels} the pieces go to a raw WAV first, which finaliser.py
    finishes and encodes in `fmt`."""
    ff = ffmpeg_exe()
    sr, ch = audio["rate"], audio["channels"]
    codec = {"mp3": ["-c:a", "libmp3lame", "-b:a", "192k"], "m4a": ["-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"],
             "wav": ["-c:a", "pcm_s16le"]}[fmt]
    partial = out.with_name(out.stem + ".partial" + out.suffix)
    tmp = Path(tempfile.mkdtemp(prefix="edit_", dir=str(out.parent))) if finish else None
    target = tmp / "joined.wav" if finish else partial
    if finish:
        codec = ["-c:a", "pcm_f32le"]
    taking = 0.55 if finish else 0.97
    log = tempfile.NamedTemporaryFile(prefix="edit_", suffix=".log", delete=False)
    raw = ["-f", "f32le", "-ar", str(sr), "-ac", str(ch)]
    dec = subprocess.Popen([ff, "-nostdin", "-v", "error", "-i", source, "-vn", "-map", "0:a:0", "-acodec", "pcm_f32le"] + raw + ["-"],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, **_RUN_FLAGS)
    enc = subprocess.Popen([ff, "-nostdin", "-y", "-v", "error"] + raw + ["-i", "-"] + codec + [str(target)],
                           stdin=subprocess.PIPE, stderr=log, **_RUN_FLAGS)
    bounds = [(int(round(c["d"] * sr)), int(round(c["f"] * sr)), max(1, int(c["fi"] * sr)), max(1, int(c["fo"] * sr))) for c in cuts]
    last = bounds[-1][1]
    size = ch * 4
    block = sr
    pos, k = 0, 0
    task["message"] = _("Taking the passages")
    try:
        while k < len(bounds):
            if task.get("cancelled"):
                raise Cancelled()
            data = dec.stdout.read(block * size)
            if not data:
                break
            n = len(data) // size
            x = np.frombuffer(data[:n * size], dtype="<f4").reshape(n, ch)
            while k < len(bounds):
                d, f, fi, fo = bounds[k]
                if d >= pos + n:
                    break
                a, b = max(d, pos), min(f, pos + n)
                if b > a:
                    idx = np.arange(a, b, dtype=np.float64)
                    g = np.clip((idx - d) / fi, 0.0, 1.0) * np.clip((f - idx) / fo, 0.0, 1.0)
                    g = 0.5 - 0.5 * np.cos(np.pi * g)
                    piece = x[a - pos:b - pos] * g[:, None].astype(np.float32)
                    enc.stdin.write(piece.astype("<f4").tobytes())
                if f <= pos + n:
                    k += 1
                else:
                    break
            pos += n
            task["progress"] = taking * min(pos / max(last, 1), 1.0)
        task["message"] = _("Encoding")
        enc.stdin.close()
        if enc.wait() != 0:
            log.flush()
            with open(log.name) as f:
                raise RuntimeError(f.read()[-600:].strip() or "ffmpeg failed")
        if finish:
            finished, report = finish_sound(task, finish["toolkit"], target, fmt, finish["channels"], tmp, share=(taking, 0.99),
                                            python=finish.get("python"), path_first=finish.get("path_first"))
            task["sound"] = report
            os.replace(finished, partial)
        os.replace(partial, out)
    except BrokenPipeError:
        with open(log.name) as f:
            raise RuntimeError(f.read()[-600:].strip() or "ffmpeg failed")
    finally:
        for p in (dec, enc):
            if p.poll() is None:
                p.kill()
        try:
            dec.stdout.close()
        except OSError:
            pass
        log.close()
        os.unlink(log.name)
        if partial.exists():
            partial.unlink()
        if tmp is not None:
            shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------------------------------------
# The log of the cuts and the edit list (CMX 3600)
# ------------------------------------------------------------------------------------------

def hmsm(t):
    ms = int(round(max(0.0, t) * 1000))
    h, r = divmod(ms, 3600000)
    m, r = divmod(r, 60000)
    s, ms = divmod(r, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def stamp(t):
    """A time in the margin of the page and in the list of passages: 05:05, and 1:05:05 past
    the hour (the hours were cut off until 1.6.1)."""
    t = max(0, int(round(t)))
    h, r = divmod(t, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def plain(t):
    """A duration for a human: 1:02:03 or 2:03."""
    t = max(0, int(round(t)))
    h, r = divmod(t, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _secs(t, digits=3):
    return f"{t:.{digits}f} " + _("s")


def _text_of(tokens, a, b):
    return " ".join(t[0] if t[0] is not None else _("[%1 without words]", _secs(t[2] - t[1], 1)) for t in tokens[max(0, a):b + 1])


def _para(text, indent):
    return textwrap.wrap(text, width=72, initial_indent=indent, subsequent_indent=indent) or [indent + _("(without words)")]


def log_text(out, project, tokens, cuts, mode, fade, image_fade, fmt, square=False, sound=None, subtitles=None):
    duration = project.get("duration") or 0.0
    kept = sum(c["f"] - c["d"] for c in cuts)
    video = fmt == "mp4"
    title = _("LOG OF THE CUTS")
    L = [title, "=" * len(title), "",
         f"{_('Original file'):<18}: {project['source']}",
         f"{'':<18}  " + _("duration %1", hmsm(duration)),
         f"{_('Edit produced'):<18}: {out}",
         f"{'':<18}  " + _("duration %1, on %2", hmsm(kept), time.strftime("%Y-%m-%d %H:%M")),
         f"{_('Setting'):<18}: " + (_("the marked text is removed, all the rest is kept") if mode == "cut" else _("the marked text is kept")),
         f"{_('Fade asked'):<18}: {_secs(fade, 1)} " + _("(the sound fade never bites a word: it is shorter when the cut is tight)")]
    if video:
        L.append(f"{_('Picture'):<18}: " + (_("straight cuts") if not (image_fade and fade > 0)
                                           else _("fade to black where %1 or more is removed, straight cut elsewhere", _secs(IMAGE_FADE_MIN, 0))))
        if square:
            L.append(f"{_('Frame'):<18}: " + _("square (1:1), the centre of the picture"))
        if subtitles:
            L.append(f"{_('Subtitles'):<18}: {subtitles}")
    if sound:
        lines = sound_summary(sound) or [_("finished by finaliser.py")]
        L.append(f"{_('Sound'):<18}: " + "; ".join(lines))
        for alert in sound.get("alertes") or []:
            L.append(f"{'':<18}  ⚠ {alert}")
    L += [f"{_('Pieces kept'):<18}: {len(cuts)}", f"{_('Removed in all'):<18}: {hmsm(max(0.0, duration - kept))}", "",
          _("Times are hours:minutes:seconds.thousandths."), ""]

    def removed(start, end, a, b):
        if end - start < 0.05:
            return
        L.append(f"  {_('REMOVED')}  {hmsm(start)} → {hmsm(end)}   ({_secs(end - start)})")
        L.extend(_para(_text_of(tokens, a, b), "    ") if a <= b else ["    " + _("(without words)")])
        L.append("")

    n = len(tokens)
    removed(0.0, cuts[0]["d"], 0, cuts[0]["range"][0] - 1)
    position = 0.0
    for k, c in enumerate(cuts):
        dur = c["f"] - c["d"]
        L.append("-" * 72)
        L.append(_("PIECE %1", k + 1))
        L.append(f"  {_('in the original'):<16} {hmsm(c['d'])} → {hmsm(c['f'])}   ({_secs(dur)})")
        L.append(f"  {_('in the edit'):<16} {hmsm(position)} → {hmsm(position + dur)}")
        L.append(f"  {_('sound'):<16} " + _("fade in %1, fade out %2", _secs(c["fi"]), _secs(c["fo"])))
        if video:
            if image_fade and fade > 0:
                L.append(f"  {_('Picture').lower():<16} " + (_("fade in") if c.get("vi", True) else _("straight in")) + ", "
                         + (_("fade out to black") if c.get("vo", True) else _("straight out")))
            else:
                L.append(f"  {_('Picture').lower():<16} " + _("straight in and out"))
        L.append("  " + _("text"))
        L.extend(_para(_text_of(tokens, c["range"][0], c["range"][1]), "    "))
        L.append("")
        position += dur
        if k + 1 < len(cuts):
            removed(c["f"], cuts[k + 1]["d"], c["range"][1] + 1, cuts[k + 1]["range"][0] - 1)
    removed(cuts[-1]["f"], duration, cuts[-1]["range"][1] + 1, n - 1)
    return "\n".join(L) + "\n"


def _timecode(frames, base, drop):
    if drop:
        d = 2 if base == 30 else 4
        per_ten, per_minute = base * 600 - d * 9, base * 60 - d
        tens, rest = divmod(frames, per_ten)
        frames += d * 9 * tens
        if rest >= d:
            frames += d * ((rest - d) // per_minute)
    ff = frames % base
    ss = (frames // base) % 60
    mm = (frames // (base * 60)) % 60
    hh = (frames // (base * 3600)) % 24
    return f"{hh:02d}:{mm:02d}:{ss:02d}{';' if drop else ':'}{ff:02d}"


def log_edl(out, project, cuts, fmt):
    """CMX 3600 edit list, straight cuts only; the fades are comments."""
    fps = ((project.get("video") or {}).get("fps") or 0.0) if project["type"] == "video" else 0.0
    if not 1.0 <= fps <= 120.0:
        fps = 25.0
    base = int(round(fps))
    drop = abs(fps - 29.97) < 0.01 or abs(fps - 59.94) < 0.01
    channels = (project.get("audio") or {}).get("channels", 2)
    track = ("AA/V" if channels >= 2 else "B") if fmt == "mp4" else ("AA" if channels >= 2 else "A")
    title = re.sub(r"[^A-Za-z0-9 _.-]+", "_", out.stem)[:60]
    L = [f"TITLE: {title}", "FCM: " + ("DROP FRAME" if drop else "NON-DROP FRAME"), ""]
    notes = [f"* READERS VIDEO EDITOR - {time.strftime('%Y-%m-%d %H:%M')}",
             f"* FRAME RATE : {fps:g} FPS, CODES COUNTED IN BASE {base}" + ("" if project["type"] == "video" else " (SOUND ONLY: A CONVENTION)"),
             "* SOURCE STARTS AT 00:00:00:00", "* THE EDIT STARTS AT 01:00:00:00",
             "* STRAIGHT CUTS ONLY : THE FADES ARE GIVEN AS COMMENTS"]
    width = max(3, len(str(len(cuts))))
    position = base * 3600
    for k, c in enumerate(cuts):
        start = int(round(c["d"] * fps))
        end = max(start + 1, int(round(c["f"] * fps)))
        n = end - start
        L.append(f"{k + 1:0{width}d}  {'AX':<8} {track:<5} C        {_timecode(start, base, drop)} {_timecode(end, base, drop)} "
                 f"{_timecode(position, base, drop)} {_timecode(position + n, base, drop)}")
        L.append(f"* FROM CLIP NAME: {Path(project['source']).name}")
        L.append(f"* SOURCE FILE: {project['source']}")
        L.append(f"* AUDIO FADE : IN {c['fi']:.3f} S, OUT {c['fo']:.3f} S")
        if fmt == "mp4":
            L.append("* PICTURE : IN " + ("FADE" if c.get("vi", True) else "STRAIGHT") + ", OUT " + ("FADE TO BLACK" if c.get("vo", True) else "STRAIGHT"))
        L.append("")
        position += n
    return "\n".join(L + notes) + "\n"


def write_logs(out, project, tokens, cuts, mode, fade, image_fade, fmt, square=False, sound=None, subtitles=None):
    image = image_fade and fade > 0
    cuts_edl = cuts if image else [dict(c, vi=False, vo=False) for c in cuts]
    written = []
    for ext, content in (("txt", log_text(out, project, tokens, cuts, mode, fade, image_fade, fmt, square, sound, subtitles)),
                         ("edl", log_edl(out, project, cuts_edl, fmt))):
        path = out.with_suffix("." + ext)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        written.append(str(path))
    return written


# ------------------------------------------------------------------------------------------
# Projects on disk: one folder per source file (sound, text, highlighting)
# ------------------------------------------------------------------------------------------

def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def project_dir(source):
    st = os.stat(source)
    key = f"{os.path.abspath(source)}|{st.st_size}|{int(st.st_mtime)}"
    pid = hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]
    slug = (re.sub(r"[^\w.-]+", "_", Path(source).stem).strip("_.") or "file")[:60]
    d = Path(PROJECTS_DIR) / f"{slug}-{pid}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ranges_from_times(tokens, times):
    chosen = []
    for i, t in enumerate(tokens):
        mid = (t[1] + t[2]) / 2.0
        if any(a <= mid <= b for a, b in times):
            chosen.append([i, i])
    return [list(p) for p in clean_ranges(chosen, len(tokens))]


# ------------------------------------------------------------------------------------------
# Settings, look
# ------------------------------------------------------------------------------------------

def load_config():
    cfg = read_json(CONFIG_FILE, {}) or {}
    cfg.setdefault("page_pt", 14)
    cfg.setdefault("model", MODEL_DEFAULT)
    cfg.setdefault("language", "")
    cfg.setdefault("fade", FADE_DEFAULT)
    cfg.setdefault("image_fade", True)
    cfg.setdefault("llm", "local")             # the translation: a local model (Ollama) or Claude
    cfg.setdefault("ollama_model", LLM_LOCAL_MODEL)
    cfg.setdefault("review", True)
    cfg.setdefault("target_lang", "fr")
    cfg.setdefault("burn", "none")             # subtitles drawn into the picture of the edit: "none", "src" or a language
    cfg.setdefault("srt_files", False)
    cfg.setdefault("caption_style", "subtitles")  # what is drawn into the picture: "subtitles" (two lines at the bottom) or "captions" (Instagram-like)
    cfg.setdefault("frame", "as_is")           # the picture of the edit: as it is, or a centred square (1:1)
    cfg.setdefault("sound", "as_is")           # the sound of the edit: as it is, or finished by the toolkit (finaliser.py)
    cfg.setdefault("toolkit_dir", "")
    return cfg


def save_config(cfg):
    write_json(CONFIG_FILE, cfg)


SANS_FAMILY = "sans-serif"   # "Roboto" once the bundled font is loaded


def bundled_fonts_dir():
    here = os.path.dirname(os.path.abspath(__file__))
    for d in (os.path.join(getattr(sys, "_MEIPASS", ""), "fonts"), os.path.join(here, "fonts"), os.path.join(here, "packaging", "fonts")):
        if d and os.path.isdir(d):
            return d
    return None


def load_bundled_fonts():
    global SANS_FAMILY
    d = bundled_fonts_dir()
    if not d:
        return 0
    n = 0
    for name in sorted(os.listdir(d)):
        if name.lower().endswith((".ttf", ".otf")) and QtGui.QFontDatabase.addApplicationFont(os.path.join(d, name)) >= 0:
            n += 1
    if n:
        SANS_FAMILY = "Roboto"
    return n       # Literata (the serif of Reader's Books) comes from the same folder


def _icon():
    here = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    for name in (APP + ".png", os.path.join("packaging", APP + ".png")):
        path = os.path.join(here, name)
        if os.path.exists(path):
            return QtGui.QIcon(path)
    return QtGui.QIcon()


def rgba(hex_colour, alpha):
    h = hex_colour.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


# The colours of the original stabilo page (monter.py in the traduction toolkit): a dark
# chrome around a paper page, a yellow highlighter, pink strike-through in the cut mode.
C_BG, C_PANEL, C_PANEL2, C_BORDER = "#14161a", "#1c1f26", "#0c0e12", "#2a2e38"
C_TEXT, C_MUTED, C_ACCENT, C_ACCENT_H = "#e6e8ec", "#8a90a0", "#ff8a3d", "#ffa362"
C_OK, C_DANGER, C_DANGER_T = "#4ad27e", "#e04b4b", "#ff9d9d"
PAPER, INK, INK2, RULE = "#f6f2e8", "#23211d", "#8b8578", "#e2dccd"
STABILO, STABILO_PRE, GOMME = "#ffe84a", "#fff3a0", "#e9e4d8"
RAYE, RAYE_PRE, RAYE_INK = "#ffc9c2", "#ffe1dc", "#8f3a31"
CURRENT = "#e0621a"
PAUSE_BG = "#eee8d8"
SERIF_CANDIDATES = ["Literata", "Iowan Old Style", "Palatino Linotype", "Palatino", "Book Antiqua", "Georgia", "Noto Serif",
                    "DejaVu Serif", "Liberation Serif", "FreeSerif"]
MONO_CANDIDATES = ["Menlo", "SF Mono", "Consolas", "DejaVu Sans Mono", "Liberation Mono", "Noto Sans Mono", "Courier New"]
GUTTER = 64                  # the time column in front of each paragraph, in pixels


def pick_font(candidates, fallback):
    families = set(QtGui.QFontDatabase().families())
    return next((f for f in candidates if f in families), fallback)


# ------------------------------------------------------------------------------------------
# The page of text: tokens one after the other, highlighted with the mouse
# ------------------------------------------------------------------------------------------

class Page(QtWidgets.QTextEdit):
    """Read-only text whose words are the tokens. A drag highlights (or erases), a click plays
    from the word, a double click takes the sentence, Shift+click extends from the last word."""
    changed = QtCore.pyqtSignal()
    seek = QtCore.pyqtSignal(float)

    def __init__(self, main):
        super().__init__()
        self.main = main
        self.setReadOnly(True)
        self.setUndoRedoEnabled(False)
        self.setMouseTracking(True)
        self.setTextInteractionFlags(QtCore.Qt.NoTextInteraction)
        self.setCursor(QtCore.Qt.ArrowCursor)
        self.viewport().setCursor(QtCore.Qt.ArrowCursor)
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.setAcceptDrops(False)
        self.tokens = []
        self.sel = np.zeros(0, dtype=np.uint8)
        self.spans = []             # (start, end) char positions of each token, or None for a hidden one
        self.anchor = -1
        self.tail = -1
        self.dragged = False
        self.erase_gesture = False
        self.last = -1
        self.preview = (-1, -1)
        self.current = -1
        self.history, self.future = [], []
        self.tool = "highlight"
        self.mode = "keep"
        self.origin = ""
        self.scroll_dir = 0
        self.scroll_timer = QtCore.QTimer(self)
        self.scroll_timer.timeout.connect(self._autoscroll)
        self.click_timer = QtCore.QTimer(self)
        self.click_timer.setSingleShot(True)
        self.click_timer.timeout.connect(self._single_click)
        self.pending_seek = None

    # ---- building the document ----
    def set_tokens(self, tokens, ranges, origin=""):
        self.tokens = tokens
        self.origin = origin
        self.sel = np.zeros(len(tokens), dtype=np.uint8)
        for a, b in ranges:
            self.sel[max(0, a):min(len(tokens) - 1, b) + 1] = 1
        self.history, self.future = [], []
        self.last = -1
        self.current = -1
        self.rebuild()

    def rebuild(self):
        """The text from the tokens: a paragraph per sentence or long pause, its time in front."""
        self.clear()
        self.spans = [None] * len(self.tokens)
        if not self.tokens:
            return
        doc = self.document()
        opt = doc.defaultTextOption()
        opt.setTabStopDistance(GUTTER)
        doc.setDefaultTextOption(opt)
        cur = QtGui.QTextCursor(doc)
        pt = self.main.page_pt + (2 if self.main.reading else 0)
        time_fmt = QtGui.QTextCharFormat()
        time_fmt.setForeground(QtGui.QColor(INK2))
        time_fmt.setFontFamily(self.main.mono)
        time_fmt.setFontPointSize(max(7.0, pt * 0.62))
        word_fmt = QtGui.QTextCharFormat()
        word_fmt.setFontFamily(self.main.serif)
        word_fmt.setFontPointSize(pt)
        word_fmt.setForeground(QtGui.QColor(INK))
        pause_fmt = QtGui.QTextCharFormat()
        pause_fmt.setForeground(QtGui.QColor(INK2))
        pause_fmt.setFontFamily(SANS_FAMILY)
        pause_fmt.setFontPointSize(max(7.0, pt * 0.68))
        pause_fmt.setBackground(QtGui.QColor(PAUSE_BG))
        # a hanging indent: the time sits in a column of its own, the lines of the paragraph align after it
        block_fmt = QtGui.QTextBlockFormat()
        block_fmt.setLeftMargin(GUTTER)
        block_fmt.setTextIndent(-GUTTER)
        block_fmt.setBottomMargin(pt * 1.1)
        block_fmt.setLineHeight(150 if "Literata" in self.main.serif else 175, QtGui.QTextBlockFormat.ProportionalHeight)
        cur.setBlockFormat(block_fmt)
        open_block = False
        chars, prev_sentence, prev_end = 0, None, 0.0
        label_without = {"subtitles": _("without words"), "transcription": _("without words")}.get(self.origin, _("without words"))
        first = True
        for i, (t, d, f, s) in enumerate(self.tokens):
            if t is None:
                if not first:
                    cur.insertBlock(block_fmt)
                first = False
                open_block = False
                tf = QtGui.QTextCharFormat(time_fmt)
                tf.setProperty(QtGui.QTextFormat.UserProperty, float(d))
                cur.insertText(stamp(d) + "\t", tf)
                where = _("Start") + " · " if i == 0 else (_("End") + " · " if i == len(self.tokens) - 1 else "")
                start = cur.position()
                cur.insertText(f" {where}{plain(f - d) if f - d >= 60 else f'{f - d:.1f} s'} {label_without} ", pause_fmt)
                self.spans[i] = (start, cur.position())
                continue
            gap = d - prev_end
            new_sentence = s != prev_sentence
            if not open_block or gap >= 2.0 or (new_sentence and gap >= 0.9) or (new_sentence and chars >= 900 and gap >= 0.25):
                if not first:
                    cur.insertBlock(block_fmt)
                first = False
                tf = QtGui.QTextCharFormat(time_fmt)
                tf.setProperty(QtGui.QTextFormat.UserProperty, float(d))
                cur.insertText(stamp(d) + "\t", tf)
                open_block, chars = True, 0
            start = cur.position()
            cur.insertText(t, word_fmt)
            self.spans[i] = (start, cur.position())
            cur.insertText(" ", word_fmt)
            chars += len(t) + 1
            prev_sentence, prev_end = s, f
        self.paint(0, len(self.tokens) - 1)

    def plain_text(self):
        """The transcript as paragraphs, without the passages without words."""
        paras, cur, prev_sentence, prev_end, chars = [], [], None, 0.0, 0
        for t, d, f, sn in self.tokens:
            if t is None:
                if cur:
                    paras.append(" ".join(cur))
                    cur, chars = [], 0
                continue
            gap = d - prev_end
            new_sentence = sn != prev_sentence
            if cur and (gap >= 2.0 or (new_sentence and gap >= 0.9) or (new_sentence and chars >= 900 and gap >= 0.25)):
                paras.append(" ".join(cur))
                cur, chars = [], 0
            cur.append(t)
            chars += len(t) + 1
            prev_sentence, prev_end = sn, f
        if cur:
            paras.append(" ".join(cur))
        return "\n\n".join(p.replace("\u00a0", " ") for p in paras) + "\n"

    # ---- painting ----
    def paint(self, a, b):
        a, b = max(0, a - 1), min(len(self.tokens) - 1, b + 1)
        if b < a:
            return
        cur = QtGui.QTextCursor(self.document())
        pa, pb = self.preview
        pt = self.main.page_pt + (2 if self.main.reading else 0)
        cut = self.mode == "cut"
        for i in range(a, b + 1):
            span = self.spans[i]
            if not span:
                continue
            fmt = QtGui.QTextCharFormat()
            pause = self.tokens[i][0] is None
            if pause:
                fmt.setForeground(QtGui.QColor(INK2))
                fmt.setFontFamily(SANS_FAMILY)
                fmt.setFontPointSize(max(7.0, pt * 0.68))
                fmt.setBackground(QtGui.QColor(PAUSE_BG))
            else:
                fmt.setForeground(QtGui.QColor(INK))
                fmt.setFontFamily(self.main.serif)
                fmt.setFontPointSize(pt)
            selected = self.sel[i] == 1
            in_preview = pa <= i <= pb
            if in_preview:
                if self.erase_gesture:
                    fmt.setBackground(QtGui.QColor(GOMME))
                    fmt.setForeground(QtGui.QColor(INK2))
                else:
                    fmt.setBackground(QtGui.QColor(RAYE_PRE if cut else STABILO_PRE))
            elif selected:
                if cut:
                    fmt.setBackground(QtGui.QColor(RAYE))
                    fmt.setForeground(QtGui.QColor(RAYE_INK))
                    fmt.setFontStrikeOut(not pause)
                else:
                    fmt.setBackground(QtGui.QColor(STABILO))
                    fmt.setForeground(QtGui.QColor(INK))
            if i == self.current:
                fmt.setFontUnderline(True)
                fmt.setUnderlineStyle(QtGui.QTextCharFormat.SingleUnderline)
                fmt.setUnderlineColor(QtGui.QColor(CURRENT))
            cur.setPosition(span[0])
            cur.setPosition(span[1], QtGui.QTextCursor.KeepAnchor)
            cur.setCharFormat(fmt)
            # the space after a word: highlighted with it when the next word is highlighted too,
            # so that a passage reads as one stroke of the pen
            nxt = self.spans[i + 1] if i + 1 < len(self.spans) else None
            if nxt and nxt[0] == span[1] + 1:
                joined = (selected and self.sel[i + 1] == 1 and not in_preview) or (in_preview and i + 1 <= pb)
                sp = QtGui.QTextCharFormat()
                if joined:
                    sp.setBackground(fmt.background())
                    sp.setFontStrikeOut(fmt.fontStrikeOut())
                cur.setPosition(span[1])
                cur.setPosition(span[1] + 1, QtGui.QTextCursor.KeepAnchor)
                cur.setCharFormat(sp)

    def set_mode(self, mode):
        self.mode = mode
        self.paint(0, len(self.tokens) - 1)

    def ranges(self):
        r, a = [], -1
        n = len(self.tokens)
        for i in range(n + 1):
            s = i < n and self.sel[i] == 1
            if s and a < 0:
                a = i
            if not s and a >= 0:
                r.append([a, i - 1])
                a = -1
        return r

    def change(self, a, b, value):
        if a > b:
            a, b = b, a
        if not any(self.sel[i] != value for i in range(a, b + 1)):
            return
        self.history.append(self.sel.copy())
        if len(self.history) > 200:
            self.history.pop(0)
        self.future = []
        self.sel[a:b + 1] = value
        self.paint(a, b)
        self.changed.emit()

    def undo(self):
        if not self.history:
            return
        self.future.append(self.sel.copy())
        self.sel = self.history.pop()
        self.paint(0, len(self.tokens) - 1)
        self.changed.emit()

    def redo(self):
        if not self.future:
            return
        self.history.append(self.sel.copy())
        self.sel = self.future.pop()
        self.paint(0, len(self.tokens) - 1)
        self.changed.emit()

    def set_current(self, t):
        """The word being played: found by time, shown underlined, scrolled into view."""
        if not self.tokens:
            return
        lo, hi, r = 0, len(self.tokens) - 1, -1
        while lo <= hi:
            m = (lo + hi) >> 1
            if self.tokens[m][1] <= t:
                r = m
                lo = m + 1
            else:
                hi = m - 1
        if r == self.current:
            return
        old, self.current = self.current, r
        if old >= 0:
            self.paint(old, old)
        if r >= 0:
            self.paint(r, r)
            if self.anchor < 0 and self.spans[r]:
                cur = QtGui.QTextCursor(self.document())
                cur.setPosition(self.spans[r][0])
                rect = self.cursorRect(cur)
                vh = self.viewport().height()
                if rect.bottom() > vh - 40 or rect.top() < 10:
                    bar = self.verticalScrollBar()
                    bar.setValue(bar.value() + rect.top() - int(vh * 0.3))

    # ---- the mouse ----
    def token_at(self, pos):
        cur = self.cursorForPosition(pos)
        p = cur.position()
        # the token whose span contains p (a click just after the word counts for the word)
        lo, hi = 0, len(self.tokens) - 1
        while lo <= hi:
            m = (lo + hi) >> 1
            span = self.spans[m]
            if span is None:
                return -1
            if p < span[0]:
                hi = m - 1
            elif p > span[1]:
                lo = m + 1
            else:
                return m
        return -1

    def strike_silences(self):
        """Every passage without words marked at once (the cut mode)."""
        free = [i for i, t in enumerate(self.tokens) if t[0] is None and not self.sel[i]]
        if not free:
            return
        self.history.append(self.sel.copy())
        self.future = []
        for i in free:
            self.sel[i] = 1
        self.paint(0, len(self.tokens) - 1)
        self.changed.emit()

    def clear_all(self):
        if not self.tokens or not self.sel.any():
            return
        self.history.append(self.sel.copy())
        self.future = []
        self.sel[:] = 0
        self.paint(0, len(self.tokens) - 1)
        self.changed.emit()

    def mousePressEvent(self, e):
        if e.button() != QtCore.Qt.LeftButton or not self.tokens:
            return
        i = self.token_at(e.pos())
        if i < 0:
            # the time in front of a paragraph: the sound goes there
            fmt = self.cursorForPosition(e.pos()).charFormat()
            if fmt.hasProperty(QtGui.QTextFormat.UserProperty):
                self.seek.emit(fmt.doubleProperty(QtGui.QTextFormat.UserProperty))
            return
        self.erase_gesture = (self.tool == "erase") != bool(e.modifiers() & QtCore.Qt.AltModifier)
        if e.modifiers() & QtCore.Qt.ShiftModifier and self.last >= 0:
            self.change(self.last, i, 0 if self.erase_gesture else 1)
            self.last = i
            return
        self.anchor = self.tail = i
        self.dragged = False

    def mouseMoveEvent(self, e):
        if self.anchor < 0:
            return
        y = e.pos().y()
        h = self.viewport().height()
        self.scroll_dir = -1 if y < 40 else (1 if y > h - 40 else 0)
        if self.scroll_dir and not self.scroll_timer.isActive():
            self.scroll_timer.start(30)
        i = self.token_at(e.pos())
        if i < 0 or i == self.tail:
            return
        self.tail = i
        if self.tail != self.anchor:
            self.dragged = True
        if self.dragged:
            self.show_preview(min(self.anchor, self.tail), max(self.anchor, self.tail))

    def _autoscroll(self):
        if not self.scroll_dir or self.anchor < 0:
            self.scroll_timer.stop()
            return
        bar = self.verticalScrollBar()
        bar.setValue(bar.value() + self.scroll_dir * 12)

    def show_preview(self, a, b):
        pa, pb = self.preview
        self.preview = (a, b)
        lo = min(pa if pa >= 0 else a, a)
        hi = max(pb, b)
        self.paint(lo, hi)

    def mouseReleaseEvent(self, e):
        if self.anchor < 0:
            return
        a, b, dragged = self.anchor, self.tail, self.dragged
        self.anchor = -1
        self.scroll_dir = 0
        pa, pb = self.preview
        self.preview = (-1, -1)
        if pa >= 0:
            self.paint(pa, pb)
        if dragged:
            self.change(a, b, 0 if self.erase_gesture else 1)
            self.last = b
        elif self.tokens[a][0] is None:
            self.last = a
            self.change(a, a, 0 if self.sel[a] else 1)
        else:
            self.last = a
            # a double click must not start the sound: the click waits for the second one
            self.pending_seek = self.tokens[a][1]
            self.click_timer.start(QtWidgets.QApplication.doubleClickInterval())

    def _single_click(self):
        if self.pending_seek is not None:
            t, self.pending_seek = self.pending_seek, None
            self.seek.emit(t)

    def mouseDoubleClickEvent(self, e):
        self.click_timer.stop()
        self.pending_seek = None
        i = self.token_at(e.pos())
        if i < 0 or self.tokens[i][0] is None:
            return
        a = b = i
        while a > 0 and self.tokens[a - 1][3] == self.tokens[i][3] and self.tokens[a - 1][0] is not None:
            a -= 1
        while b < len(self.tokens) - 1 and self.tokens[b + 1][3] == self.tokens[i][3] and self.tokens[b + 1][0] is not None:
            b += 1
        full = all(self.sel[k] for k in range(a, b + 1))
        self.change(a, b, 0 if (full or self.tool == "erase") else 1)

    def wheelEvent(self, e):
        super().wheelEvent(e)


# ------------------------------------------------------------------------------------------
# Background work
# ------------------------------------------------------------------------------------------

class Worker(QtCore.QObject):
    done = QtCore.pyqtSignal(object)
    failed = QtCore.pyqtSignal(str)
    progress = QtCore.pyqtSignal(float, str)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self.cancelled = False

    @QtCore.pyqtSlot()
    def run(self):
        try:
            self.done.emit(self.fn(self))
        except (Cancelled, InterruptedError):
            self.failed.emit("")
        except Exception as ex:          # noqa: BLE001
            self.failed.emit(str(ex)[:600] or ex.__class__.__name__)


# ------------------------------------------------------------------------------------------
# The window
# ------------------------------------------------------------------------------------------

class Passages(QtWidgets.QListWidget):
    """The passages of the edit: time, words, length, and a × to drop one."""
    dropped = QtCore.pyqtSignal(int)
    chosen = QtCore.pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.setObjectName("passages")
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self.setMouseTracking(True)
        self.setItemDelegate(PassageDelegate(self))
        self.setCursor(QtCore.Qt.PointingHandCursor)

    def mousePressEvent(self, e):
        item = self.itemAt(e.pos())
        if item is None or e.button() != QtCore.Qt.LeftButton:
            return
        row = self.row(item)
        if e.pos().x() > self.viewport().width() - 30 or QtWidgets.QApplication.keyboardModifiers() & QtCore.Qt.ControlModifier:
            self.dropped.emit(row)
        else:
            self.chosen.emit(row)


class PassageDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, view):
        super().__init__(view)
        self.view = view

    def sizeHint(self, option, index):
        fm = QtGui.QFontMetrics(option.font)
        return QtCore.QSize(option.rect.width(), fm.lineSpacing() * 2 + 18)

    def paint(self, painter, option, index):
        t, dur, text, hover = index.data(QtCore.Qt.UserRole + 1)
        r = option.rect.adjusted(10, 6, -8, -6)
        painter.save()
        if option.state & QtWidgets.QStyle.State_MouseOver:
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(QtGui.QColor("#181b22"))
            painter.drawRoundedRect(option.rect.adjusted(4, 1, -4, -1), 9, 9)
        mono = QtGui.QFont(self.view.window().mono, max(7, int(option.font.pointSize() * 0.9)))
        painter.setFont(mono)
        painter.setPen(QtGui.QColor(C_ACCENT))
        painter.drawText(QtCore.QRect(r.left(), r.top(), 64, r.height()), QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop, stamp(t))
        small = QtGui.QFont(option.font)
        small.setPointSizeF(max(7.0, option.font.pointSizeF() * 0.85))
        painter.setFont(small)
        painter.setPen(QtGui.QColor(C_MUTED))
        painter.drawText(QtCore.QRect(r.right() - 90, r.top(), 60, r.height()), QtCore.Qt.AlignRight | QtCore.Qt.AlignTop, plain(dur))
        painter.setFont(QtGui.QFont(option.font.family(), option.font.pointSize() + 2))
        painter.drawText(QtCore.QRect(r.right() - 20, r.top() - 2, 20, r.height()), QtCore.Qt.AlignRight | QtCore.Qt.AlignTop, "×")
        painter.setFont(option.font)
        painter.setPen(QtGui.QColor(C_TEXT))
        box = QtCore.QRect(r.left() + 66, r.top(), r.width() - 66 - 96, r.height())
        painter.setClipRect(box)
        painter.drawText(box, QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop | QtCore.Qt.TextWordWrap, text)
        painter.restore()


class Recent(QtWidgets.QFrame):
    """One line of the « Resume » list on the home page."""
    clicked = QtCore.pyqtSignal(str)

    def __init__(self, source, kind, duration, present):
        super().__init__()
        self.source = source
        self.setObjectName("recent")
        self.setProperty("absent", not present)
        h = QtWidgets.QHBoxLayout(self)
        h.setContentsMargins(14, 9, 14, 9)
        h.setSpacing(12)
        name = QtWidgets.QLabel(Path(source).name)
        name.setObjectName("recentName")
        name.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        detail = QtWidgets.QLabel((_("Video") if kind == "video" else _("Recording")) + " · " + plain(duration))
        detail.setObjectName("muted")
        h.addWidget(name, 1)
        h.addWidget(detail)
        self.setToolTip(source)
        if present:
            self.setCursor(QtCore.Qt.PointingHandCursor)

    def mousePressEvent(self, e):
        if e.button() == QtCore.Qt.LeftButton and not self.property("absent"):
            self.clicked.emit(self.source)


# ------------------------------------------------------------------------------------------
# The subtitle editor: a table of cues, the text of each one edited in place
# ------------------------------------------------------------------------------------------
class CueModel(QtCore.QAbstractTableModel):
    START, END, PACE, TEXT, ORIGINAL = range(5)

    def __init__(self, editor):
        super().__init__()
        self.editor = editor
        self.cues = []
        self.original = None        # the tokens of the original text, beside a translation's cues
        self.current = -1
        self.cache = {}

    def reset(self, cues, original):
        self.beginResetModel()
        self.cues, self.original, self.cache, self.current = cues, original, {}, -1
        self.endResetModel()

    def rowCount(self, parent=QtCore.QModelIndex()):
        return 0 if parent.isValid() else len(self.cues)

    def columnCount(self, parent=QtCore.QModelIndex()):
        return 5 if self.original is not None else 4

    def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
        if role == QtCore.Qt.DisplayRole:
            if orientation == QtCore.Qt.Horizontal:
                return [_("Start"), _("End"), "c/s", _("Text"), _("Original")][section]
            return str(section + 1)
        if role == QtCore.Qt.ToolTipRole and orientation == QtCore.Qt.Horizontal and section == self.PACE:
            return _("characters a second")
        return None

    def flags(self, index):
        f = QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable
        if index.column() in (self.START, self.END, self.TEXT):
            f |= QtCore.Qt.ItemIsEditable
        return f

    def data(self, index, role=QtCore.Qt.DisplayRole):
        r, c = index.row(), index.column()
        if not 0 <= r < len(self.cues):
            return None
        a, b, text = self.cues[r]
        if role in (QtCore.Qt.DisplayRole, QtCore.Qt.EditRole):
            if c == self.START:
                return clock(a)
            if c == self.END:
                return clock(b)
            if c == self.PACE:
                return f"{cue_pace(self.cues[r]):.0f}" if b > a else "—"
            if c == self.TEXT:
                return text
            if r not in self.cache:
                self.cache[r] = words_during(self.original, a, b)
            return self.cache[r]
        if role == QtCore.Qt.BackgroundRole:
            if r == self.current:
                return QtGui.QColor(STABILO_PRE)
            issues = self.editor.issues(r)
            if any(level == "bad" for level, _t in issues):
                return QtGui.QColor(RAYE_PRE)
            if issues:
                return QtGui.QColor("#fbe4ad")
            return None
        if role == QtCore.Qt.ToolTipRole:
            notes = [t for _l, t in self.editor.issues(r)] + [pace_note(self.cues[r])]
            return "\n".join(t for t in notes if t) or None
        if role == QtCore.Qt.TextAlignmentRole:
            return int((QtCore.Qt.AlignRight if c in (self.START, self.END, self.PACE) else QtCore.Qt.AlignLeft) | QtCore.Qt.AlignTop)
        if role == QtCore.Qt.ForegroundRole and c == self.PACE:
            return QtGui.QColor(PACE_COLOURS[pace_level(self.cues[r])])
        if role == QtCore.Qt.ForegroundRole and c == self.ORIGINAL:
            return QtGui.QColor(INK2)
        if role == QtCore.Qt.FontRole and c in (self.START, self.END, self.PACE):
            if c == self.PACE and pace_level(self.cues[r]):
                font = QtGui.QFont(self.editor.mono_font)
                font.setBold(True)
                return font
            return self.editor.mono_font
        return None

    def setData(self, index, value, role=QtCore.Qt.EditRole):
        if role != QtCore.Qt.EditRole:
            return False
        r, c = index.row(), index.column()
        a, b, text = self.cues[r]
        if c == self.TEXT:
            new = "\n".join(" ".join(line.split()) for line in str(value).split("\n") if line.strip())
            if not new or new == text:
                return False
            self.editor.snapshot()
            self.cues[r][2] = new
        else:
            t = parse_clock(str(value))
            if t is None:
                return False
            t = round(t, 3)
            if c == self.START and (t == a or t >= b):
                return False
            if c == self.END and (t == b or t <= a):
                return False
            self.editor.snapshot()
            self.cues[r][0 if c == self.START else 1] = t
        self.editor.after_change()
        return True


class CueTextEditor(QtWidgets.QPlainTextEdit):
    """The text of one cue, edited in its cell: Enter splits the cue at the cursor, Shift+Enter
    breaks the line."""
    split = QtCore.pyqtSignal(str, int)

    def keyPressEvent(self, e):
        if e.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            if e.modifiers() & QtCore.Qt.ShiftModifier:
                self.insertPlainText("\n")
            else:
                self.split.emit(self.toPlainText(), self.textCursor().position())
            return
        super().keyPressEvent(e)


class CueDelegate(QtWidgets.QStyledItemDelegate):
    split = QtCore.pyqtSignal(int, str, int)      # row, the text being typed, the cursor
    jump = QtCore.pyqtSignal(int)                  # edit this row next (Tab)

    def createEditor(self, parent, option, index):
        if index.column() != CueModel.TEXT:
            return super().createEditor(parent, option, index)
        ed = CueTextEditor(parent)
        ed.setFrameShape(QtWidgets.QFrame.NoFrame)
        ed.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        ed.row = index.row()
        ed.split.connect(lambda text, pos, ed=ed: self._split(ed, text, pos))
        return ed

    def _split(self, ed, text, pos):
        self.closeEditor.emit(ed, QtWidgets.QAbstractItemDelegate.NoHint)
        self.split.emit(ed.row, text, pos)

    def setEditorData(self, ed, index):
        if isinstance(ed, CueTextEditor):
            ed.setPlainText(index.data(QtCore.Qt.EditRole) or "")
            ed.moveCursor(QtGui.QTextCursor.End)
        else:
            super().setEditorData(ed, index)

    def setModelData(self, ed, model, index):
        if isinstance(ed, CueTextEditor):
            model.setData(index, ed.toPlainText(), QtCore.Qt.EditRole)
        else:
            super().setModelData(ed, model, index)

    def eventFilter(self, ed, ev):
        if isinstance(ed, CueTextEditor) and ev.type() == QtCore.QEvent.KeyPress and ev.key() in (QtCore.Qt.Key_Tab, QtCore.Qt.Key_Backtab):
            self.commitData.emit(ed)
            self.closeEditor.emit(ed, QtWidgets.QAbstractItemDelegate.NoHint)
            self.jump.emit(ed.row + (1 if ev.key() == QtCore.Qt.Key_Tab else -1))
            return True
        return super().eventFilter(ed, ev)


class CueEditor(QtWidgets.QWidget):
    changed = QtCore.pyqtSignal()
    seek = QtCore.pyqtSignal(float)
    recut = QtCore.pyqtSignal()
    shorten = QtCore.pyqtSignal()

    def __init__(self, main):
        super().__init__()
        self.main = main
        self.history, self.future = [], []
        self.edited = False
        self.duration = 0.0
        self.mono_font = QtGui.QFont(main.mono, 10)
        self.model = CueModel(self)
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(20, 14, 20, 10)
        v.setSpacing(8)
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(main._btn(_("Re-cut from the text"), self.recut.emit, kind="paper"))
        row.addWidget(main._btn(_("Shorten what reads too fast…"), self.shorten.emit, kind="paper"))
        row.addStretch(1)
        self.count = QtWidgets.QLabel("")
        self.count.setObjectName("muted")
        row.addWidget(self.count)
        v.addLayout(row)
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(main._btn(_("Split"), lambda: self.split_at(self.row()), kind="paper", tip=_("Split")))
        row.addWidget(main._btn(_("Merge with the next"), self.merge_next, kind="paper", tip="Ctrl+J"))
        row.addWidget(main._btn(_("Delete"), self.delete_cues, kind="paper", tip="Del"))
        row.addStretch(1)
        for which, name in ((0, _("Start")), (1, _("End"))):
            row.addWidget(main._btn(name + " −", lambda _c=False, w=which: self.nudge(w, -NUDGE), kind="paper", tip=f"{name} −{NUDGE:g} s"))
            row.addWidget(main._btn(name + " +", lambda _c=False, w=which: self.nudge(w, NUDGE), kind="paper", tip=f"{name} +{NUDGE:g} s"))
            row.addWidget(main._btn(name + " " + _("here"), lambda _c=False, w=which: self.set_edge(w, self.main.player.position() / 1000.0),
                                    kind="paper", tip=_("Start here") if which == 0 else _("End here")))
            if which == 0:
                row.addSpacing(10)
        v.addLayout(row)
        hint = QtWidgets.QLabel(_("Enter splits the subtitle at the cursor, Shift+Enter breaks the line, Tab goes to the next one. A click on a subtitle plays from there; the buttons move its edges by a tenth of a second, or to the instant being played."))
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        v.addWidget(hint)
        self.table = QtWidgets.QTableView()
        self.table.setModel(self.model)
        self.delegate = CueDelegate(self.table)
        self.table.setItemDelegate(self.delegate)
        self.delegate.split.connect(self.split_at)
        self.delegate.jump.connect(self.edit_row)
        self.table.setWordWrap(True)
        self.table.setShowGrid(False)
        self.table.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.DoubleClicked | QtWidgets.QAbstractItemView.SelectedClicked | QtWidgets.QAbstractItemView.EditKeyPressed)
        self.table.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self.table.verticalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Fixed)
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.clicked.connect(self._clicked)
        v.addWidget(self.table, 1)
        for keys, fn in (("Delete", self.delete_cues), ("Ctrl+J", self.merge_next),
                         ("Alt+Left", lambda: self.nudge(0, -NUDGE)), ("Alt+Right", lambda: self.nudge(0, NUDGE)),
                         ("Alt+Shift+Left", lambda: self.nudge(1, -NUDGE)), ("Alt+Shift+Right", lambda: self.nudge(1, NUDGE))):
            s = QtWidgets.QShortcut(QtGui.QKeySequence(keys), self.table)
            s.setContext(QtCore.Qt.WidgetWithChildrenShortcut)
            s.activated.connect(fn)
        self.refont()

    # ---- what is shown ----
    def set_cues(self, cues, original, edited):
        self.history, self.future = [], []
        self.edited = bool(edited)
        self.model.reset([list(c) for c in cues], original)
        self._columns()
        self.refresh_count()

    def cues(self):
        return [list(c) for c in self.model.cues]

    def issues(self, r):
        return cue_issues(self.model.cues, r)

    def too_fast_rows(self):
        return [r for r, c in enumerate(self.model.cues) if pace_level(c) == 2]

    def refont(self):
        """The font of the page, a little smaller; two lines of text to a row."""
        pt = max(8, self.main.page_pt - 1)
        self.mono_font = QtGui.QFont(self.main.mono, max(8, pt - 3))
        fm = QtGui.QFontMetrics(QtGui.QFont(SANS_FAMILY, pt))
        self.table.verticalHeader().setDefaultSectionSize(fm.lineSpacing() * 2 + 14)
        self._columns()

    def _columns(self):
        head = self.table.horizontalHeader()
        fm = QtGui.QFontMetrics(self.mono_font)
        for col, chars in ((CueModel.START, 11), (CueModel.END, 11), (CueModel.PACE, 4)):
            head.setSectionResizeMode(col, QtWidgets.QHeaderView.Fixed)
            self.table.setColumnWidth(col, fm.horizontalAdvance("0") * chars + 16)
        head.setSectionResizeMode(CueModel.TEXT, QtWidgets.QHeaderView.Stretch)
        if self.model.columnCount() > CueModel.ORIGINAL:
            head.setSectionResizeMode(CueModel.ORIGINAL, QtWidgets.QHeaderView.Stretch)

    def refresh_count(self):
        n = len(self.model.cues)
        self.count.setText(_("%1 subtitles", n) + (" · " + _("edited by hand") if self.edited else ""))

    # ---- the history ----
    def snapshot(self):
        self.history.append(self.cues())
        del self.history[:-200]
        self.future.clear()

    def after_change(self):
        self.model.cache.clear()
        self.edited = True
        n = self.model.rowCount()
        if n:
            self.model.dataChanged.emit(self.model.index(0, 0), self.model.index(n - 1, self.model.columnCount() - 1))
        self.refresh_count()
        self.changed.emit()

    def _restore(self, cues):
        row = self.row()
        self.model.reset(cues, self.model.original)
        self.edited = True
        self.select(min(row, len(cues) - 1))
        self.refresh_count()
        self.changed.emit()

    def undo(self):
        if self.history:
            self.future.append(self.cues())
            self._restore(self.history.pop())

    def redo(self):
        if self.future:
            self.history.append(self.cues())
            self._restore(self.future.pop())

    # ---- the rows ----
    def row(self):
        idx = self.table.currentIndex()
        return idx.row() if idx.isValid() else -1

    def selected_rows(self):
        rows = sorted({i.row() for i in self.table.selectionModel().selectedRows()})
        return rows or ([self.row()] if self.row() >= 0 else [])

    def select(self, r):
        if 0 <= r < len(self.model.cues):
            idx = self.model.index(r, CueModel.TEXT)
            self.table.setCurrentIndex(idx)
            self.table.scrollTo(idx)

    def _clicked(self, idx):
        if self.table.state() != QtWidgets.QAbstractItemView.EditingState and idx.isValid():
            self.seek.emit(self.model.cues[idx.row()][0])

    def edit_row(self, r):
        if 0 <= r < len(self.model.cues):
            self.select(r)
            self.table.edit(self.model.index(r, CueModel.TEXT))

    def set_current(self, t):
        """The subtitle being played, marked and kept in view (unless one is being edited)."""
        k = cue_at(self.model.cues, t)
        if k == self.model.current:
            return
        old, self.model.current = self.model.current, k
        for r in (old, k):
            if r >= 0:
                self.model.dataChanged.emit(self.model.index(r, 0), self.model.index(r, self.model.columnCount() - 1), [QtCore.Qt.BackgroundRole])
        if k >= 0 and self.table.state() != QtWidgets.QAbstractItemView.EditingState:
            self.table.scrollTo(self.model.index(k, 0))

    # ---- the changes ----
    def apply_texts(self, texts):
        """New texts for some rows (the model's shortening)."""
        self.snapshot()
        for r, text in texts.items():
            if 0 <= r < len(self.model.cues):
                self.model.cues[r][2] = text
        self.after_change()

    def split_at(self, row, text=None, pos=None):
        """Two cues out of one: at the cursor while typing, at the space nearest the middle otherwise;
        the time is shared in proportion to the letters."""
        cues = self.model.cues
        if not 0 <= row < len(cues):
            return
        a, b, cur = cues[row]
        if text is None:
            text = " ".join(cur.split())
            spaces = [i for i, ch in enumerate(text) if ch == " "]
            if not spaces:
                return
            pos = min(spaces, key=lambda i: abs(i - len(text) / 2.0))
        if 0 < pos < len(text) and not text[pos - 1].isspace() and not text[pos].isspace():
            # inside a word: the cut goes to the nearest space before it (after it when there is none)
            before = max(text.rfind(" ", 0, pos), text.rfind("\n", 0, pos))
            after = min(i for i in (text.find(" ", pos), text.find("\n", pos), len(text)) if i >= 0)
            pos = before + 1 if before >= 0 else after
        left, right = " ".join(text[:pos].split()), " ".join(text[pos:].split())
        if not left or not right:
            return
        self.snapshot()
        cut = a + (b - a) * len(left) / (len(left) + len(right))
        end = round(max(a + 0.3, cut - 0.05), 3)
        self.model.beginInsertRows(QtCore.QModelIndex(), row + 1, row + 1)
        cues[row] = [a, end, two_lines(left)]
        cues.insert(row + 1, [round(max(end + 0.05, cut), 3), b, two_lines(right)])
        self.model.endInsertRows()
        self.after_change()
        self.select(row + 1)

    def merge_next(self):
        row, cues = self.row(), self.model.cues
        if row < 0 or row + 1 >= len(cues):
            return
        self.snapshot()
        a, _b, t1 = cues[row]
        _a2, b, t2 = cues[row + 1]
        self.model.beginRemoveRows(QtCore.QModelIndex(), row + 1, row + 1)
        cues[row] = [a, b, two_lines(" ".join((t1 + " " + t2).split()))]
        del cues[row + 1]
        self.model.endRemoveRows()
        self.after_change()
        self.select(row)

    def delete_cues(self):
        rows = self.selected_rows()
        if not rows:
            return
        self.snapshot()
        for r in reversed(rows):
            self.model.beginRemoveRows(QtCore.QModelIndex(), r, r)
            del self.model.cues[r]
            self.model.endRemoveRows()
        self.after_change()
        self.select(min(rows[0], len(self.model.cues) - 1))

    def set_edge(self, which, t):
        row = self.row()
        if row < 0:
            return
        a, b, _text = self.model.cues[row]
        t = round(max(0.0, min(t, self.duration or t)), 3)
        new = max(0.0, min(t, b - 0.3)) if which == 0 else max(a + 0.3, t)
        if new == (a if which == 0 else b):
            return
        self.snapshot()
        self.model.cues[row][which] = round(new, 3)
        self.after_change()

    def nudge(self, which, delta):
        row = self.row()
        if row >= 0:
            self.set_edge(which, self.model.cues[row][which] + delta)


class Main(QtWidgets.QMainWindow):
    listening_ready = QtCore.pyqtSignal(str, str)     # the source, the copy to play in its place

    def __init__(self, source=None, srt=None):
        super().__init__()
        self.listening_ready.connect(self.use_listening_copy)
        self.cfg = load_config()
        self.page_pt = int(self.cfg.get("page_pt", 14))
        self.serif = pick_font(SERIF_CANDIDATES, "serif")
        self.mono = pick_font(MONO_CANDIDATES, "monospace")
        self.project = None         # {source, type, duration, video, audio, dir}
        self.tokens = []
        self.cuts = []
        self.origin = ""
        self.estimated = False
        self.texts = {}             # "src" and each translated language → {tokens, origin, estimated, language}
        self.view = "src"           # the text on the page: "src" or a language code
        self.src_lang = ""
        self.cues = {}              # "src" and each language → {language, cues, edited}: the subtitles, once made or edited
        self.subs_mode = False      # the subtitle editor in place of the page
        self.overlay_src, self.overlay_idx = None, -1
        self.project_file = None    # the .rve.json this project was opened from or saved to
        self.detail = ""
        self.thread = None
        self.worker = None
        self.task = None
        self.previewing = -1
        self.wanted_seek = False
        self.media_ok = True
        self.reading = False
        self.mode_value = "keep"
        self.setup_active = None       # the getting-started row whose job runs, while one does
        self.setup_probe = {}
        self.setup_ok = {}             # the real tests that passed on this page: "ollama", "claude_code", "claude"
        self.setWindowTitle("Reader's Video Editor")
        self.setAcceptDrops(True)
        self.resize(1200, 780)
        self._build()
        self.apply_style()
        self.show_home()
        if source and source.endswith(PROJECT_EXT):
            QtCore.QTimer.singleShot(0, lambda: self.open_project_file(source))
        elif source:
            QtCore.QTimer.singleShot(0, lambda: self.open_source(source, srt))
        elif not self.cfg.get("welcomed"):
            QtCore.QTimer.singleShot(0, self.show_setup)

    # ---- building ----
    def _btn(self, text, fn=None, kind=None, tip=None):
        b = QtWidgets.QPushButton(text)
        b.setAutoDefault(False)
        b.setCursor(QtCore.Qt.PointingHandCursor)
        if kind:
            b.setProperty("kind", kind)
        if tip:
            b.setToolTip(tip)
        if fn:
            b.clicked.connect(fn)
        return b

    def _menu_action(self, menu, text, fn, keys=None):
        """An entry of a menu; with `keys` its shortcut works everywhere in the window (the
        action is the window's too), and the menu shows it."""
        act = menu.addAction(text, fn)
        if keys:
            act.setShortcut(QtGui.QKeySequence(keys))
            act.setShortcutContext(QtCore.Qt.ApplicationShortcut)
            self.addAction(act)
        return act

    def _segment(self, buttons):
        """Two or three buttons in one rounded frame, one of them active."""
        box = QtWidgets.QWidget()
        box.setObjectName("seg")
        h = QtWidgets.QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        for k, b in enumerate(buttons):
            b.setCheckable(True)
            b.setObjectName("segbtn")
            b.setProperty("side", "first" if k == 0 else ("last" if k == len(buttons) - 1 else "mid"))
            h.addWidget(b)
        return box

    def _build(self):
        self.views = QtWidgets.QStackedWidget()
        self.setCentralWidget(self.views)
        self._build_home()
        self._build_setup()
        self._build_workshop()
        # the player
        self.player = QMediaPlayer(self, QMediaPlayer.VideoSurface)
        self.player.setVideoOutput(self.video)
        self.player.setNotifyInterval(50)
        self.player.positionChanged.connect(self.on_position)
        self.player.stateChanged.connect(lambda _s: self.update_play_button())
        self.player.error.connect(self.on_media_error)
        self.player.durationChanged.connect(lambda d: self.slider.setMaximum(max(0, int(d))))
        # shortcuts

        def sc(keys, fn):
            s = QtWidgets.QShortcut(QtGui.QKeySequence(keys), self)
            s.setContext(QtCore.Qt.ApplicationShortcut)
            s.activated.connect(fn)
        sc("Ctrl+O", self.ask_open)
        sc("Ctrl+L", self.ask_url)
        sc("Ctrl+Z", self.undo)
        sc("Ctrl+Y", self.redo)
        sc("Ctrl+Shift+Z", self.redo)
        sc("Ctrl+U", lambda: self.b_subs.click())
        sc("Ctrl+=", lambda: self.resize_text(1))
        sc("Ctrl++", lambda: self.resize_text(1))
        sc("Ctrl+-", lambda: self.resize_text(-1))
        sc("Space", self.toggle_play)
        sc("Left", lambda: self.go(self.player.position() / 1000.0 - 5, None))
        sc("Right", lambda: self.go(self.player.position() / 1000.0 + 5, None))
        sc("S", lambda: self.choose_tool("highlight"))
        sc("G", lambda: self.choose_tool("erase"))
        sc("Ctrl+E", self.produce_or_stop)
        sc("Ctrl+R", lambda: self.b_read.click())
        sc("Ctrl+S", self.save_text)
        sc("Ctrl+Shift+C", self.copy_text)
        self.position_timer = QtCore.QTimer(self)
        self.position_timer.timeout.connect(self.tick)
        self.position_timer.start(80)
        self.update_play_button()
        self.enable(False)

    def _build_home(self):
        home = QtWidgets.QScrollArea()
        home.setWidgetResizable(True)
        home.setFrameShape(QtWidgets.QFrame.NoFrame)
        inner = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(inner)
        outer.setContentsMargins(24, 0, 24, 40)
        outer.addStretch(9)
        card = QtWidgets.QWidget()
        card.setObjectName("card")
        card.setMaximumWidth(680)
        v = QtWidgets.QVBoxLayout(card)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        title = QtWidgets.QLabel("Reader's <span style=\"background:#ffe84a; color:#1b1a12\">&nbsp;Video&nbsp;</span> Editor")
        title.setObjectName("h1")
        title.setTextFormat(QtCore.Qt.RichText)
        v.addWidget(title)
        lead = QtWidgets.QLabel(_("Choose a video or a recording, or give the address of a video online. The text appears, you highlight what you keep, or what you remove, and the edit is made for you."))
        lead.setObjectName("lead")
        lead.setWordWrap(True)
        v.addWidget(lead)
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(8)
        self.h_field = QtWidgets.QLineEdit()
        self.h_field.setPlaceholderText(_("File location, or address of a video (YouTube, X…)"))
        self.h_field.returnPressed.connect(self.home_open)
        row.addWidget(self.h_field, 1)
        row.addWidget(self._btn(_("Browse…"), self.ask_open))
        v.addLayout(row)
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(8)
        self.h_lang = QtWidgets.QComboBox()
        for code, name in LANGUAGES:
            self.h_lang.addItem(_("auto") if not code else name, code)
        codes = [c for c, _n in LANGUAGES]
        self.h_lang.setCurrentIndex(codes.index(self.cfg.get("language", "")) if self.cfg.get("language", "") in codes else 0)
        self.h_lang.setToolTip(_("Spoken language"))
        self.h_model = QtWidgets.QComboBox()
        self.h_model.addItems(MODELS)
        self.h_model.setCurrentText(self.cfg.get("model", MODEL_DEFAULT))
        self.h_model.setToolTip(_("model"))
        lab = QtWidgets.QLabel(_("Spoken language"))
        lab.setObjectName("muted")
        row.addWidget(lab)
        row.addWidget(self.h_lang)
        lab = QtWidgets.QLabel(_("model"))
        lab.setObjectName("muted")
        row.addWidget(lab)
        row.addWidget(self.h_model)
        row.addStretch(1)
        self.h_open = self._btn(_("Open"), self.home_open, kind="strong")
        row.addWidget(self.h_open)
        v.addLayout(row)
        self.h_error = QtWidgets.QLabel("")
        self.h_error.setObjectName("danger")
        self.h_error.setWordWrap(True)
        v.addWidget(self.h_error)
        # a download in progress
        self.h_follow = QtWidgets.QWidget()
        fv = QtWidgets.QVBoxLayout(self.h_follow)
        fv.setContentsMargins(0, 0, 0, 0)
        fv.setSpacing(6)
        self.h_gauge = QtWidgets.QProgressBar()
        self.h_gauge.setRange(0, 1000)
        self.h_gauge.setTextVisible(False)
        self.h_gauge.setFixedHeight(6)
        fv.addWidget(self.h_gauge)
        fr = QtWidgets.QHBoxLayout()
        self.h_msg = QtWidgets.QLabel("")
        self.h_msg.setObjectName("muted")
        self.h_msg.setWordWrap(True)
        fr.addWidget(self.h_msg, 1)
        fr.addWidget(self._btn(_("Stop"), self.produce_or_stop, kind="danger"))
        fv.addLayout(fr)
        self.h_follow.hide()
        v.addWidget(self.h_follow)
        self.h_resume = QtWidgets.QLabel(_("Resume"))
        self.h_resume.setObjectName("label")
        v.addWidget(self.h_resume)
        self.h_recents = QtWidgets.QVBoxLayout()
        self.h_recents.setSpacing(6)
        v.addLayout(self.h_recents)
        keys = QtWidgets.QLabel(_("Shortcuts: Space play/pause · ← → 5 s · S highlighter · G eraser · Ctrl+Z undo · Ctrl+R read · Ctrl+= Ctrl+- text size · Ctrl+O file · Ctrl+L address"))
        keys.setObjectName("muted")
        keys.setWordWrap(True)
        v.addSpacing(16)
        v.addWidget(keys)
        gs = QtWidgets.QHBoxLayout()
        gs.addWidget(self._btn(_("Getting started…"), self.show_setup, tip=_("What this computer has, and the buttons that put the rest in place.")))
        gs.addStretch(1)
        v.addLayout(gs)
        hc = QtWidgets.QHBoxLayout()
        hc.addStretch(1)
        hc.addWidget(card, 20)
        hc.addStretch(1)
        outer.addLayout(hc)
        outer.addStretch(40)
        home.setWidget(inner)
        self.home = home
        self.views.addWidget(home)

    # ---- getting started: five steps, each checked by a real test, each with the button that does it ----
    def _build_setup(self):
        page = QtWidgets.QScrollArea()
        page.setWidgetResizable(True)
        page.setFrameShape(QtWidgets.QFrame.NoFrame)
        inner = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(inner)
        outer.setContentsMargins(24, 28, 24, 40)
        card = QtWidgets.QWidget()
        card.setObjectName("card")
        card.setMaximumWidth(760)
        v = QtWidgets.QVBoxLayout(card)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)
        title = QtWidgets.QLabel(_("Getting started"))
        title.setObjectName("h1")
        v.addWidget(title)
        lead = QtWidgets.QLabel(_("Three levels. Level 1 is all you need to cut a video: it works as soon as the app is installed. Levels 2 and 3 are optional extras; if you never translate, skip them, nothing there is needed for the editing. One step at a time, each checked by a real test, each with the button that does the work. You can come back here any time: « Getting started… » on the home page, or Project ▾ › Getting started… while editing."))
        lead.setObjectName("lead")
        lead.setWordWrap(True)
        v.addWidget(lead)
        self.setup_rows = {}

        def heading(text, sub):
            h = QtWidgets.QLabel(f"<b>{text}</b><br><span style='color:{C_MUTED}'>{sub}</span>")
            h.setTextFormat(QtCore.Qt.RichText)
            h.setWordWrap(True)
            h.setContentsMargins(0, 10, 0, 0)
            v.addWidget(h)
        heading(_("Level 1 · Editing"), _("The whole point of the app: open, highlight, produce. Nothing to install."))
        self.setup_rows["edit"] = self._setup_row(v, 1, _("Cut a video by its text"))
        self.setup_rows["transcribe"] = self._setup_row(v, 1, _("Transcribe the speech"))
        go1 = QtWidgets.QHBoxLayout()
        go1.addWidget(self._btn(_("That is enough for me: start editing"), self.leave_setup, kind="strong"))
        go1.addStretch(1)
        v.addLayout(go1)
        heading(_("Level 2 · Translation and subtitles — optional"), _("Only if you want to translate the text, or to cut subtitles with the toolkit's rules. Otherwise skip this level entirely."))
        self.setup_rows["toolkit"] = self._setup_row(v, 2, _("Translate and subtitle: the toolkit"))
        self.setup_rows["model"] = self._setup_row(v, 2, _("Translate and subtitle: the language model"))
        heading(_("Level 3 · Improved sound — optional"), _("Only if you want the edit's sound cleaned and levelled on the way out. Needs the toolkit of level 2 (not the model)."))
        self.setup_rows["sound"] = self._setup_row(v, 3, _("Improve the sound"))
        bottom = QtWidgets.QHBoxLayout()
        self.b_setup_refresh = self._btn(_("Check again"), self.refresh_setup)
        bottom.addWidget(self.b_setup_refresh)
        bottom.addStretch(1)
        bottom.addWidget(self._btn(_("Start editing"), self.leave_setup, kind="strong"))
        v.addLayout(bottom)
        hc = QtWidgets.QHBoxLayout()
        hc.addStretch(1)
        hc.addWidget(card, 20)
        hc.addStretch(1)
        outer.addLayout(hc)
        outer.addStretch(1)
        page.setWidget(inner)
        self.setup = page
        self.views.addWidget(page)

    def _setup_row(self, v, level, name):
        """A step: a coloured dot and its name on one line, a sentence of detail, a row for a
        choice, a field when the step needs one, a row of buttons. Returns the row as a namespace."""
        from types import SimpleNamespace
        box = QtWidgets.QFrame()
        box.setObjectName("setuprow")
        bv = QtWidgets.QVBoxLayout(box)
        bv.setContentsMargins(14, 10, 14, 10)
        bv.setSpacing(6)
        head_row = QtWidgets.QHBoxLayout()
        head_row.setSpacing(8)
        dot = QtWidgets.QLabel("●")
        dot.setObjectName("dot")
        head_row.addWidget(dot)
        head = QtWidgets.QLabel(f"<span style='color:{C_MUTED}'>{level} ·</span> <b>{name}</b>")
        head.setTextFormat(QtCore.Qt.RichText)
        head_row.addWidget(head, 1)
        bv.addLayout(head_row)
        detail = QtWidgets.QLabel("")
        detail.setObjectName("muted")
        detail.setWordWrap(True)
        detail.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        bv.addWidget(detail)
        choice = QtWidgets.QWidget()
        ch = QtWidgets.QHBoxLayout(choice)
        ch.setContentsMargins(0, 0, 0, 0)
        choice.hide()
        bv.addWidget(choice)
        field = QtWidgets.QLineEdit()
        field.hide()
        bv.addWidget(field)
        buttons = QtWidgets.QWidget()
        bh = QtWidgets.QHBoxLayout(buttons)
        bh.setContentsMargins(0, 0, 0, 0)
        bh.setSpacing(8)
        bh.addStretch(1)
        buttons.hide()
        bv.addWidget(buttons)
        v.addWidget(box)
        row = SimpleNamespace(box=box, dot=dot, detail=detail, choice=choice, choice_layout=ch, field=field, buttons=buttons, buttons_layout=bh, widgets=[])

        def set_state(state, text):
            colour = {"ok": C_OK, "todo": C_ACCENT, "busy": C_ACCENT, "off": C_MUTED, "opt": C_MUTED, "bad": C_DANGER}[state]
            dot.setStyleSheet(f"color: {colour}; font-size: 14pt;")
            detail.setText(text)

        def set_buttons(items):
            for w in row.widgets:
                bh.removeWidget(w)
                w.deleteLater()
            row.widgets = []
            for k, (text, fn, strong) in enumerate(items):
                b = self._btn(text, fn, kind="strong" if strong else None)
                bh.insertWidget(k, b)
                row.widgets.append(b)
            buttons.setVisible(bool(items))
        row.set = set_state
        row.set_buttons = set_buttons
        return row

    def show_setup(self):
        if self.thread:
            return
        self.views.setCurrentWidget(self.setup)
        self.refresh_setup()

    def leave_setup(self):
        if self.setup_active is not None:
            return
        self.cfg["welcomed"] = VERSION
        save_config(self.cfg)
        self.views.setCurrentWidget(self.home)

    def refresh_setup(self):
        if self.thread or self.setup_active is not None:
            return
        for r in self.setup_rows.values():
            r.set("busy", _("Checking…"))
            r.set_buttons([])
        self.b_setup_refresh.setEnabled(False)

        def done(p):
            self.setup_probe = p
            self.b_setup_refresh.setEnabled(True)
            self.fill_setup()

        def failed(msg):
            self.b_setup_refresh.setEnabled(True)
            self.setup_rows["edit"].set("bad", msg)
        self.run_in_background(lambda w: probe_setup(self.cfg), done, failed)

    def setup_job(self, key, fn, after=None):
        """Runs `fn(task)` in the background for the step `key`, its progress in the step's detail,
        a Stop button meanwhile; then checks everything again."""
        if self.thread or self.setup_active is not None:
            return
        row = self.setup_rows[key]
        self.setup_active = row
        task = {"cancelled": False, "proc": None}
        for r in self.setup_rows.values():
            for b in r.widgets:
                b.setEnabled(False)
        self.b_setup_refresh.setEnabled(False)

        def stop():
            task["cancelled"] = True
            proc = task.get("proc")
            if proc:
                try:
                    proc.kill()
                except OSError:
                    pass
        row.set_buttons([(_("Stop"), stop, False)])
        row.set("busy", _("Working…"))

        def work(w):
            return fn(task, lambda text: w.progress.emit(0.0, text))

        def done(result):
            self.setup_active = None
            if after:
                after(result)
            self.refresh_setup()

        def failed(msg):
            self.setup_active = None
            self.fill_setup()
            row.set("bad", msg or _("Cancelled."))
        self.run_in_background(work, done, failed)

    def fill_setup(self):
        p = self.setup_probe
        if not p:
            return
        R = self.setup_rows
        self._fill_setup_rows(p, R)

    def _fill_setup_rows(self, p, R):
        # 1 · the edit
        if p["ffmpeg"]:
            R["edit"].set("ok", _("Ready: ffmpeg is here. Open a video or a recording, highlight, produce."))
            R["edit"].set_buttons([])
        else:
            R["edit"].set("todo", _("ffmpeg is missing. On Linux: sudo apt install ffmpeg, then « Check again »."))
            R["edit"].set_buttons([(_("Check again"), self.refresh_setup, False)])
        # 1 · the transcription: the model chosen here is the one of the home page
        size = p["size"]
        tr = R["transcribe"]
        for i in reversed(range(tr.choice_layout.count())):
            w = tr.choice_layout.itemAt(i).widget()
            if w:
                tr.choice_layout.removeWidget(w)
                w.deleteLater()
        lab = QtWidgets.QLabel(_("Model"))
        lab.setObjectName("muted")
        combo = QtWidgets.QComboBox()
        for m in MODELS:
            combo.addItem(f"{m} · {WHISPER_SIZES.get(m, '')}", m)
        combo.setCurrentIndex(max(0, combo.findData(size)))
        combo.currentIndexChanged.connect(lambda i: self.setup_pick_whisper(combo.itemData(i)))
        tr.choice_layout.addWidget(lab)
        tr.choice_layout.addWidget(combo)
        tr.choice_layout.addStretch(1)
        tr.choice.show()
        note = " " + _("« %1 »: %2.", size, _(WHISPER_NOTES.get(size, "")))
        if not p["whisper"]:
            if getattr(sys, "frozen", False):
                R["transcribe"].set("bad", _("The transcription is missing from this build."))
                R["transcribe"].set_buttons([])
            else:
                R["transcribe"].set("todo", _("faster-whisper is not installed yet: the app installs it in a folder of its own (about 300 MB, once)."))
                R["transcribe"].set_buttons([(_("Install the transcription"), lambda: self.setup_job("transcribe", lambda t, say: install_whisper(say, lambda: t.get("cancelled"))), True)])
        elif not p["whisper_model"]:
            R["transcribe"].set("todo", _("faster-whisper is here. The model « %1 » (%2) is downloaded at the first transcription; or now:", size, WHISPER_SIZES.get(size, "")) + note)
            R["transcribe"].set_buttons([(_("Download the model now"), lambda: self.setup_job("transcribe", lambda t, say: (say(_("Downloading the model « %1 » (%2)…", size, WHISPER_SIZES.get(size, ""))), download_whisper_model(size))), True)])
        else:
            R["transcribe"].set("ok", _("Ready: faster-whisper and the model « %1 ». A subtitle file beside the video is used instead when there is one.", size) + note)
            R["transcribe"].set_buttons([])
        # 2 · the toolkit
        if p["toolkit"]:
            R["toolkit"].set("ok", _("Found: %1", p["toolkit"]))
            R["toolkit"].set_buttons([])
        else:
            R["toolkit"].set("opt", _("Optional —") + " " + _("The traduction toolkit does the translation, the subtitles and the sound. It is not on this computer: the app can download it (a few MB, no git)."))
            R["toolkit"].set_buttons([(_("Install it here"), lambda: self.setup_job("toolkit", lambda t, say: install_toolkit(say, t)), True)])
        self.fill_model_row()
        # 3 · the sound
        if not p["toolkit"]:
            R["sound"].set("off", _("Needs the toolkit (step 2)."))
            R["sound"].set_buttons([])
        elif p["sound_ready"] and p["ffmpeg_named"]:
            R["sound"].set("ok", _("Ready: the libraries of finaliser.py are here. « Sound: improved » in the production block uses them."))
            R["sound"].set_buttons([])
        else:
            R["sound"].set("opt", _("Optional —") + " " + _("The libraries (deepfilternet, pyloudnorm, speechmos, with torch: about 500 MB) are installed at the first use, in an environment of the app's own. Or now:")
                           + " " + _("Speed: about the length of the edit on a processor, much less with a graphics card; the length and the picture do not change.")
                           + ("" if p["ffmpeg_named"] else " " + _("On this Mac, ffmpeg and ffprobe for Apple silicon are fetched too (2 × 28 MB).")))

            def install_sound(t, say):
                ensure_ffmpeg_tools(say, t)
                return prepare_toolkit_python(TOOLKIT_PACKAGES["sound"], say, t)
            R["sound"].set_buttons([(_("Install now"), lambda: self.setup_job("sound", install_sound), True)])

    def fill_model_row(self):
        """Step 2, the model: three ways, the one chosen in the settings; the buttons of that way."""
        p, row = self.setup_probe, self.setup_rows["model"]
        llm = self.cfg.get("llm") or "local"
        # the three ways, as a segmented control
        for i in reversed(range(row.choice_layout.count())):
            w = row.choice_layout.itemAt(i).widget()
            if w:
                row.choice_layout.removeWidget(w)
                w.deleteLater()
        buttons, kinds = [], ("local", "claude_code", "claude")
        for kind, text in zip(kinds, (_("Ollama, on this computer"), _("Claude Code, your own plan"), _("Claude, an API key"))):
            b = QtWidgets.QPushButton(text)
            b.clicked.connect(lambda _c, k=kind: self.setup_choose(k))
            buttons.append(b)
        row.choice_layout.addWidget(self._segment(buttons))
        for kind, b in zip(kinds, buttons):
            b.setChecked(kind == llm)
        row.choice_layout.addStretch(1)
        row.choice.show()
        row.field.hide()
        url = OLLAMA_URL
        ways = " " + _("Quality and cost: Claude gives the best translations; Claude Code costs nothing beyond your plan, the API key pays by the call, both send the text to Anthropic. A local model keeps everything on this computer, slower, and the smaller the model, the rougher the translation.")
        if llm == "local":
            wanted = self.cfg.get("ollama_model") or (p["recommended"][0] if p["recommended"] else LLM_LOCAL_MODEL)
            have = wanted in p["ollama_models"] or wanted + ":latest" in p["ollama_models"]
            gb = f"{p['ram'] / 1024:.0f}"
            if not p["ollama_bin"] and not p["ollama_up"]:
                row.set("opt", _("Optional —") + " " + _("Ollama runs the model on this computer. It is not installed: get it from ollama.com (the app on a Mac, one command on Linux), open it, then « Check again »."))
                row.set_buttons([(_("Get Ollama"), lambda: QtGui.QDesktopServices.openUrl(QtCore.QUrl(OLLAMA_DOWNLOAD)), True), (_("Check again"), self.refresh_setup, False)])
            elif not p["ollama_up"]:
                row.set("opt", _("Optional —") + " " + _("Ollama is installed but not running."))
                row.set_buttons([(_("Start Ollama"), lambda: self.setup_job("model", lambda t, say: ollama_start(p["ollama_bin"])), True), (_("Check again"), self.refresh_setup, False)])
            elif not have:
                if p["recommended"] is None and not self.cfg.get("ollama_model"):
                    row.set("opt", _("Optional —") + " " + _("Ollama answers, but this computer (%1 GB of memory) is too small for a model of the toolkit's family: choose Claude.", gb))
                    row.set_buttons([])
                else:
                    size = next((s for m, _n, s in MODEL_LADDER if m == wanted), None)
                    row.set("opt", _("Optional —") + " " + _("Ollama answers. This computer (%1 GB of memory) can carry « %2 »%3; the download happens once.", gb, wanted, f" ({size} GB)" if size else "")
                            + (" " + _("« %1 »: %2.", wanted, _(LOCAL_NOTES[wanted])) if wanted in LOCAL_NOTES else "") + ways)

                    def pull(t, say, m=wanted):
                        ollama_pull(url, m, say, t)
                        return m
                    row.set_buttons([(_("Download %1", wanted), lambda: self.setup_job("model", pull, lambda m: self.cfg.update(ollama_model=m)), True), (_("Check again"), self.refresh_setup, False)])
            elif self.setup_ok.get("ollama") == wanted:
                row.set("ok", _("Ready: Ollama answers and « %1 » replied to a test.", wanted))
                row.set_buttons([])
            else:
                row.set("opt", _("Optional —") + " " + _("Ollama answers and « %1 » is here. One test to be sure:", wanted)
                        + (" " + _("« %1 »: %2.", wanted, _(LOCAL_NOTES[wanted])) if wanted in LOCAL_NOTES else "") + ways)

                def test(t, say, m=wanted):
                    say(_("Asking « %1 »…", m))
                    ok, msg = ollama_test(url, m)
                    if not ok:
                        raise RuntimeError(msg)
                    return m
                row.set_buttons([(_("Test"), lambda: self.setup_job("model", test, lambda m: self.setup_ok.update(ollama=m) or self.cfg.update(ollama_model=m)), True)])
        elif llm == "claude_code":
            exe = p["claude"]
            if not exe:
                row.set("opt", _("Optional —") + " " + _("Claude Code is the claude command, on your own Claude plan: no key, no bill by the call. It is not installed; the app can run its installer (from claude.ai).") + ways)
                row.set_buttons([(_("Install Claude Code"), lambda: self.setup_job("model", lambda t, say: install_claude(say, t)), True), (_("Check again"), self.refresh_setup, False)])
            elif self.setup_ok.get("claude_code") == exe:
                row.set("ok", _("Ready: Claude Code answers (%1).", exe))
                row.set_buttons([])
            else:
                row.set("opt", _("Optional —") + " " + _("Claude Code found: %1. Sign in once with your Claude account (a terminal opens: type /login and follow the browser), then test.", exe))

                def test(t, say, e=exe):
                    say(_("Asking Claude Code…"))
                    ok, msg = claude_test(e)
                    if not ok:
                        raise RuntimeError(msg)
                    return e

                def sign_in():
                    if not open_terminal(exe):
                        row.set("bad", _("No terminal was found: open one yourself, type claude, then /login."))
                row.set_buttons([(_("Sign in"), sign_in, False), (_("Test"), lambda: self.setup_job("model", test, lambda e: self.setup_ok.update(claude_code=e)), True)])
        else:
            row.field.setEchoMode(QtWidgets.QLineEdit.Password)
            row.field.setPlaceholderText("sk-ant-…")
            row.field.setText(self.cfg.get("anthropic_key") or os.environ.get("ANTHROPIC_API_KEY") or "")
            row.field.show()
            key = row.field.text().strip()
            if key and self.setup_ok.get("claude") == key:
                row.set("ok", _("Ready: the key is accepted by Anthropic."))
            else:
                row.set("opt", _("Optional —") + " " + _("A key from console.anthropic.com (API Keys › Create Key), paid by the call; the text goes to Anthropic. Paste it, then test.") + ways)

            def test(t, say):
                k = row.field.text().strip()
                if not k:
                    raise RuntimeError(_("Give an Anthropic API key."))
                say(_("Asking Anthropic…"))
                ok, msg = anthropic_key_test(k)
                if not ok:
                    raise RuntimeError(msg)
                return k

            def keep(k):
                self.cfg["anthropic_key"] = k
                self.setup_ok["claude"] = k
                save_config(self.cfg)
            row.set_buttons([(_("Test the key"), lambda: self.setup_job("model", test, keep), True)])

    def setup_pick_whisper(self, size):
        """The transcription model chosen on the getting-started page: the setting of the home page."""
        if not size or size == self.cfg.get("model"):
            return
        self.cfg["model"] = size
        save_config(self.cfg)
        self.h_model.setCurrentText(size)
        self.setup_probe["size"], self.setup_probe["whisper_model"] = size, whisper_model_present(size)
        self.fill_setup()

    def setup_choose(self, kind):
        self.cfg["llm"] = kind
        save_config(self.cfg)
        self.fill_model_row()

    def _build_workshop(self):
        shop = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(shop)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # the bar
        bar = QtWidgets.QWidget()
        bar.setObjectName("bar")
        h = QtWidgets.QHBoxLayout(bar)
        h.setContentsMargins(16, 10, 16, 10)
        h.setSpacing(10)
        tbox = QtWidgets.QVBoxLayout()
        tbox.setSpacing(0)
        self.a_name = QtWidgets.QLabel("")
        self.a_name.setObjectName("name")
        self.a_name.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        self.a_detail = QtWidgets.QLabel("")
        self.a_detail.setObjectName("muted")
        tbox.addWidget(self.a_name)
        tbox.addWidget(self.a_detail)
        h.addLayout(tbox, 1)
        # the original and the translated texts: one button each, when there is a translation
        self.lang_box = QtWidgets.QWidget()
        lb = QtWidgets.QHBoxLayout(self.lang_box)
        lb.setContentsMargins(0, 0, 0, 0)
        lb.setSpacing(0)
        self.lang_box.hide()
        h.addWidget(self.lang_box)
        lab = QtWidgets.QLabel(_("I highlight"))
        lab.setObjectName("muted")
        h.addWidget(lab)
        self.b_keep = self._btn(_("what I keep"), lambda: self.set_mode("keep"), tip=_("I highlight what I keep"))
        self.b_cut = self._btn(_("what I cut"), lambda: self.set_mode("cut"), kind="cut", tip=_("I highlight what I cut"))
        self.b_keep.setChecked(True)
        h.addWidget(self._segment([self.b_keep, self.b_cut]))
        self.b_highlight = self._btn(_("Highlighter"), lambda: self.choose_tool("highlight"), tip="S")
        self.b_erase = self._btn(_("Eraser"), lambda: self.choose_tool("erase"), kind="erase", tip="G")
        self.b_highlight.setChecked(True)
        h.addWidget(self._segment([self.b_highlight, self.b_erase]))
        self.b_undo = self._btn(_("Undo"), self.undo, tip="Ctrl+Z")
        self.b_redo = self._btn(_("Redo"), self.redo, tip="Ctrl+Y")
        h.addWidget(self.b_undo)
        h.addWidget(self.b_redo)
        self.b_read = self._btn(_("Read"), None, tip="Ctrl+R")
        self.b_read.setCheckable(True)
        self.b_read.clicked.connect(lambda c: self.set_reading(c))
        h.addWidget(self.b_read)
        self.b_subs = self._btn(_("Subtitles"), None, tip="Ctrl+U")
        self.b_subs.setCheckable(True)
        self.b_subs.clicked.connect(lambda c: self.set_subtitles(c))
        h.addWidget(self.b_subs)
        self.b_text = QtWidgets.QToolButton()
        self.b_text.setText(_("Text") + " ▾")
        self.b_text.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        self.b_text.setCursor(QtCore.Qt.PointingHandCursor)
        menu = QtWidgets.QMenu(self.b_text)
        menu.addAction(_("Save the text…"), self.save_text)
        menu.addAction(_("copy the text"), self.copy_text)
        menu.addAction(_("Save the subtitles…"), self.save_srt)
        menu.addSeparator()
        self._menu_action(menu, _("Translate…"), self.ask_translate, "Ctrl+T")
        menu.addSeparator()
        menu.addAction(_("Open subtitles…"), self.ask_srt)
        menu.addAction(_("Transcribe again…"), self.ask_transcribe)
        self.b_text.setMenu(menu)
        h.addWidget(self.b_text)
        self.b_project = QtWidgets.QToolButton()
        self.b_project.setText(_("Project") + " ▾")
        self.b_project.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        self.b_project.setCursor(QtCore.Qt.PointingHandCursor)
        pm = QtWidgets.QMenu(self.b_project)
        self._menu_action(pm, _("Save the project…"), lambda: self.save_project(ask=False), "Ctrl+Shift+S")
        self._menu_action(pm, _("Save the project as…"), lambda: self.save_project(ask=True))
        self._menu_action(pm, _("Open a project…"), self.ask_project, "Ctrl+Shift+O")
        pm.addSeparator()
        self._menu_action(pm, _("Getting started…"), self.show_setup)
        self.b_project.setMenu(pm)
        h.addWidget(self.b_project)
        h.addWidget(self._btn(_("Another file"), self.show_home))
        outer.addWidget(bar)

        split = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        split.setChildrenCollapsible(False)
        outer.addWidget(split, 1)

        # the side column
        side = QtWidgets.QWidget()
        side.setObjectName("side")
        sv = QtWidgets.QVBoxLayout(side)
        sv.setContentsMargins(0, 0, 0, 0)
        sv.setSpacing(0)
        self.video = QVideoWidget()
        self.video.setMinimumHeight(140)
        self.video.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.screen = QtWidgets.QWidget()
        self.screen.setObjectName("screen")
        sl = QtWidgets.QVBoxLayout(self.screen)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.addWidget(self.video)
        self.overlay = QtWidgets.QLabel(self.screen)
        self.overlay.setObjectName("overlay")
        self.overlay.setAlignment(QtCore.Qt.AlignCenter)
        self.overlay.setWordWrap(True)
        self.overlay.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.overlay.hide()
        self.screen.installEventFilter(self)
        sv.addWidget(self.screen, 3)
        self.controls = QtWidgets.QWidget()
        self.controls.setObjectName("controls")
        ctl = QtWidgets.QHBoxLayout(self.controls)
        ctl.setContentsMargins(12, 8, 12, 8)
        ctl.setSpacing(6)
        self.b_back = self._btn("−5", lambda: self.go(self.player.position() / 1000.0 - 5, None), kind="glyph")
        self.b_play = self._btn("▶", self.toggle_play, kind="glyph")
        self.b_fwd = self._btn("+10", lambda: self.go(self.player.position() / 1000.0 + 10, None), kind="glyph")
        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider.sliderMoved.connect(lambda v: self.go(v / 1000.0, None))
        self.time_label = QtWidgets.QLabel("0:00 / 0:00")
        self.time_label.setObjectName("mono")
        self.speed = QtWidgets.QComboBox()
        for r in (0.8, 1.0, 1.25, 1.5, 2.0):
            self.speed.addItem(f"{r:g}×", r)
        self.speed.setCurrentIndex(1)
        self.speed.currentIndexChanged.connect(lambda _i: self.player.setPlaybackRate(float(self.speed.currentData())))
        for w in (self.b_back, self.b_play, self.b_fwd):
            ctl.addWidget(w)
        ctl.addWidget(self.slider, 1)
        ctl.addWidget(self.time_label)
        ctl.addWidget(self.speed)
        sv.addWidget(self.controls)

        bilan = QtWidgets.QWidget()
        bilan.setObjectName("bilan")
        bv = QtWidgets.QVBoxLayout(bilan)
        bv.setContentsMargins(16, 12, 16, 10)
        bv.setSpacing(2)
        self.l_big = QtWidgets.QLabel(_("Nothing highlighted"))
        self.l_big.setObjectName("big")
        self.l_small = QtWidgets.QLabel("")
        self.l_small.setObjectName("muted")
        bv.addWidget(self.l_big)
        bv.addWidget(self.l_small)
        br = QtWidgets.QHBoxLayout()
        br.setContentsMargins(0, 8, 0, 0)
        br.setSpacing(8)
        self.b_preview = self._btn(_("▶ Watch the edit"), self.toggle_preview)
        self.b_clear = self._btn(_("Clear all"), lambda: self.page.clear_all())
        self.b_silences = self._btn(_("Strike the silence"), lambda: self.page.strike_silences())
        self.b_silences.hide()
        br.addWidget(self.b_preview)
        br.addWidget(self.b_clear)
        br.addWidget(self.b_silences)
        br.addStretch(1)
        bv.addLayout(br)
        sv.addWidget(bilan)

        self.passages = Passages()
        self.passages.dropped.connect(self.drop_passage)
        self.passages.chosen.connect(self.go_passage)
        self.hint = QtWidgets.QLabel("")
        self.hint.setObjectName("hint")
        self.hint.setWordWrap(True)
        self.hint.setAlignment(QtCore.Qt.AlignTop)
        self.list_stack = QtWidgets.QStackedWidget()
        self.list_stack.addWidget(self.hint)
        self.list_stack.addWidget(self.passages)
        sv.addWidget(self.list_stack, 4)

        prod = QtWidgets.QWidget()
        prod.setObjectName("production")
        pv = QtWidgets.QVBoxLayout(prod)
        pv.setContentsMargins(16, 12, 16, 12)
        pv.setSpacing(8)
        self.settings = QtWidgets.QWidget()
        self.settings.setObjectName("settings")
        g = QtWidgets.QGridLayout(self.settings)
        g.setContentsMargins(0, 0, 0, 0)
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(4)
        lab = QtWidgets.QLabel(_("Produce"))
        lab.setObjectName("label")
        g.addWidget(lab, 0, 0)
        self.format = QtWidgets.QComboBox()
        g.addWidget(self.format, 1, 0)
        lab = QtWidgets.QLabel(_("Fade at each cut"))
        lab.setObjectName("label")
        g.addWidget(lab, 0, 1)
        self.fade = QtWidgets.QComboBox()
        for f, name in zip(FADES, (_("None"), _("Brief (0.2 s)"), _("Normal (0.5 s)"), _("Slow (1 s)"), _("Very slow (1.5 s)"))):
            self.fade.addItem(name, f)
        idx = [i for i in range(self.fade.count()) if abs(self.fade.itemData(i) - float(self.cfg.get("fade", FADE_DEFAULT))) < 1e-6]
        self.fade.setCurrentIndex(idx[0] if idx else FADES.index(FADE_DEFAULT))
        self.fade.currentIndexChanged.connect(lambda _i: self.on_selection())
        g.addWidget(self.fade, 1, 1)
        self.image_fade = QtWidgets.QCheckBox(_("fade the picture to black"))
        self.image_fade.setChecked(bool(self.cfg.get("image_fade", True)))
        self.image_fade.toggled.connect(lambda _c: self.on_selection())
        g.addWidget(self.image_fade, 2, 0, 1, 2)
        self.l_frame = QtWidgets.QLabel(_("Picture"))
        self.l_frame.setObjectName("label")
        g.addWidget(self.l_frame, 3, 0)
        self.frame = QtWidgets.QComboBox()
        self.frame.addItem(_("As it is"), "as_is")
        self.frame.addItem(_("Square (1:1), centred"), "square")
        self.frame.setCurrentIndex(max(0, self.frame.findData(self.cfg.get("frame", "as_is"))))
        self.frame.currentIndexChanged.connect(lambda _i: self.remember_output())
        g.addWidget(self.frame, 4, 0)
        lab = QtWidgets.QLabel(_("Sound"))
        lab.setObjectName("label")
        g.addWidget(lab, 3, 1)
        self.sound = QtWidgets.QComboBox()
        self.sound.addItem(_("As it is"), "as_is")
        self.sound.addItem(_("Improved: background noise, level"), "finish")
        self.sound.setCurrentIndex(max(0, self.sound.findData(self.cfg.get("sound", "as_is"))))
        self.sound.currentIndexChanged.connect(lambda _i: self.remember_output())
        self.sound.setToolTip(_("finaliser.py of the traduction toolkit: mains hum and a steady background noise removed when there are some, the level brought to the norm. The length does not change."))
        g.addWidget(self.sound, 4, 1)
        self.format.currentIndexChanged.connect(lambda _i: self.refresh_frame_option())
        self.l_subs = QtWidgets.QLabel(_("Subtitles"))
        self.l_subs.setObjectName("label")
        g.addWidget(self.l_subs, 5, 0, 1, 2)
        self.subs = QtWidgets.QComboBox()
        self.subs.currentIndexChanged.connect(lambda _i: self.remember_output())
        g.addWidget(self.subs, 6, 0)
        self.caption_style = QtWidgets.QComboBox()
        self.caption_style.addItem(_("Two lines at the bottom"), "subtitles")
        self.caption_style.addItem(_("Instagram-like captions"), "captions")
        self.caption_style.setCurrentIndex(max(0, self.caption_style.findData(self.cfg.get("caption_style", "subtitles"))))
        self.caption_style.setToolTip(_("A few big words at a time, centred near the bottom of the picture (higher on a vertical one), the spoken word in yellow: the style of the short videos."))
        self.caption_style.currentIndexChanged.connect(lambda _i: self.remember_output())
        g.addWidget(self.caption_style, 6, 1)
        self.srt_files = QtWidgets.QCheckBox(_("Subtitle files beside the edit (.srt)"))
        self.srt_files.setChecked(bool(self.cfg.get("srt_files", False)))
        self.srt_files.toggled.connect(lambda _c: self.remember_output())
        g.addWidget(self.srt_files, 7, 0, 1, 2)
        self.b_produce = self._btn(_("Produce the edit"), self.produce_or_stop, kind="strong", tip="Ctrl+E")
        g.addWidget(self.b_produce, 8, 0, 1, 2)
        pv.addWidget(self.settings)
        self.following = QtWidgets.QWidget()
        self.following.setObjectName("following")
        fv = QtWidgets.QVBoxLayout(self.following)
        fv.setContentsMargins(0, 0, 0, 0)
        fv.setSpacing(6)
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        fv.addWidget(self.progress)
        fr = QtWidgets.QHBoxLayout()
        self.f_text = QtWidgets.QLabel("")
        self.f_text.setObjectName("muted")
        self.f_text.setWordWrap(True)
        fr.addWidget(self.f_text, 1)
        fr.addWidget(self._btn(_("Stop"), self.produce_or_stop, kind="danger"))
        fv.addLayout(fr)
        self.following.hide()
        pv.addWidget(self.following)
        self.finished = QtWidgets.QWidget()
        self.finished.setObjectName("finished")
        dv = QtWidgets.QVBoxLayout(self.finished)
        dv.setContentsMargins(0, 0, 0, 0)
        dv.setSpacing(4)
        self.fin_detail = QtWidgets.QLabel("")
        self.fin_detail.setTextFormat(QtCore.Qt.RichText)
        self.fin_path = QtWidgets.QLabel("")
        self.fin_path.setObjectName("path")
        self.fin_path.setWordWrap(True)
        self.fin_logs = QtWidgets.QLabel(_("Beside it: the log of the cuts (.txt) and the edit list (.edl)."))
        self.fin_logs.setObjectName("muted")
        self.fin_logs.setWordWrap(True)
        self.fin_sound = QtWidgets.QLabel("")
        self.fin_sound.setObjectName("muted")
        self.fin_sound.setWordWrap(True)
        self.fin_sound.hide()
        dv.addWidget(self.fin_detail)
        dv.addWidget(self.fin_path)
        dv.addWidget(self.fin_sound)
        dv.addWidget(self.fin_logs)
        dr = QtWidgets.QHBoxLayout()
        dr.setContentsMargins(0, 6, 0, 0)
        dr.setSpacing(8)
        self.b_watch = self._btn(_("Watch"), lambda: QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(self.last_out)), kind="strong")
        dr.addWidget(self.b_watch)
        dr.addWidget(self._btn(_("Open the folder"), lambda: QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(Path(self.last_out).parent)))))
        dr.addWidget(self._btn(_("Close"), lambda: self.show_production("settings")))
        dr.addStretch(1)
        dv.addLayout(dr)
        self.finished.hide()
        pv.addWidget(self.finished)
        self.fail = QtWidgets.QLabel("")
        self.fail.setObjectName("danger")
        self.fail.setWordWrap(True)
        self.fail.hide()
        pv.addWidget(self.fail)
        self.status = QtWidgets.QLabel("")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        self.status.hide()
        pv.addWidget(self.status)
        sv.addWidget(prod)
        self.side = side
        self.sv = sv
        split.addWidget(side)

        # the page, and the waiting view that takes its place while the text is made
        self.page = Page(self)
        self.page.changed.connect(self.on_selection)
        self.page.seek.connect(lambda t: self.go(t, True))
        right = QtWidgets.QWidget()
        right.setObjectName("paper")
        rv = QtWidgets.QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)
        self.page_stack = QtWidgets.QStackedWidget()
        self.page_stack.addWidget(self.page)
        self.editor = CueEditor(self)
        self.editor.changed.connect(self.on_cues_changed)
        self.editor.seek.connect(lambda t: self.go(t, None))
        self.editor.recut.connect(self.recut_cues)
        self.editor.shorten.connect(self.ask_shorten)
        self.page_stack.addWidget(self.editor)
        patience = QtWidgets.QWidget()
        patience.setObjectName("paper")
        pl = QtWidgets.QVBoxLayout(patience)
        pl.setContentsMargins(28, 0, 28, 0)
        pl.addStretch(16)
        self.p_msg = QtWidgets.QLabel("")
        self.p_msg.setObjectName("patience")
        self.p_msg.setAlignment(QtCore.Qt.AlignCenter)
        self.p_msg.setWordWrap(True)
        pl.addWidget(self.p_msg)
        self.p_gauge = QtWidgets.QProgressBar()
        self.p_gauge.setRange(0, 1000)
        self.p_gauge.setTextVisible(False)
        self.p_gauge.setFixedHeight(6)
        self.p_gauge.setMaximumWidth(420)
        pl.addWidget(self.p_gauge, 0, QtCore.Qt.AlignHCenter)
        self.p_detail = QtWidgets.QLabel("")
        self.p_detail.setObjectName("patienceDetail")
        self.p_detail.setAlignment(QtCore.Qt.AlignCenter)
        self.p_detail.setWordWrap(True)
        pl.addWidget(self.p_detail)
        self.p_retry = QtWidgets.QWidget()
        rr = QtWidgets.QHBoxLayout(self.p_retry)
        rr.setContentsMargins(0, 18, 0, 0)
        rr.setSpacing(8)
        rr.addStretch(1)
        self.p_lang = QtWidgets.QComboBox()
        for code, name in LANGUAGES:
            self.p_lang.addItem(_("auto") if not code else name, code)
        self.p_model = QtWidgets.QComboBox()
        self.p_model.addItems(MODELS)
        rr.addWidget(self.p_lang)
        rr.addWidget(self.p_model)
        rr.addWidget(self._btn(_("Start the transcription again"), self.retry_transcription, kind="paper"))
        rr.addWidget(self._btn(_("Open subtitles…"), self.ask_srt, kind="paper"))
        rr.addStretch(1)
        self.p_retry.hide()
        pl.addWidget(self.p_retry)
        self.p_cancel = QtWidgets.QWidget()
        cr = QtWidgets.QHBoxLayout(self.p_cancel)
        cr.setContentsMargins(0, 18, 0, 0)
        cr.addStretch(1)
        cr.addWidget(self._btn(_("Stop"), self.produce_or_stop, kind="paper"))
        cr.addStretch(1)
        self.p_cancel.hide()
        pl.addWidget(self.p_cancel)
        pl.addStretch(84)
        self.page_stack.addWidget(patience)
        self.patience = patience
        rv.addWidget(self.page_stack, 1)
        self.rv = rv
        split.addWidget(right)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([400, 800])
        self.split = split
        self.views.addWidget(shop)
        self.shop = shop
        self.last_out = ""

    def apply_style(self):
        pt = self.page_pt + (2 if self.reading else 0)
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{ background: {C_BG}; color: {C_TEXT}; font-family: "{SANS_FAMILY}"; font-size: 10.5pt; }}
            QLabel, QCheckBox, QStackedWidget, QScrollArea {{ background: transparent; }}
            QToolTip {{ background: {C_PANEL}; color: {C_TEXT}; border: 1px solid {C_BORDER}; padding: 4px 6px; }}
            QLabel#muted, QLabel#hint, QLabel#patienceDetail {{ color: {C_MUTED}; }}
            QLabel#label {{ color: {C_MUTED}; font-weight: 600; font-size: 9pt; }}
            QLabel#danger {{ color: {C_DANGER_T}; }}
            QLabel#mono, QLabel#path {{ font-family: "{self.mono}"; font-size: 9pt; }}
            QLabel#path {{ color: {C_MUTED}; }}
            QLabel#h1 {{ font-size: 20pt; font-weight: 700; }}
            QLabel#lead {{ color: {C_MUTED}; font-size: 11.5pt; }}
            QLabel#name {{ font-weight: 700; }}
            QLabel#big {{ font-size: 15pt; font-weight: 700; }}
            QLabel#hint {{ padding: 14px 16px; font-size: 10pt; }}
            QLabel#patience {{ background: {PAPER}; color: {INK}; font-family: "{self.serif}"; font-size: 13pt; }}
            QLabel#patienceDetail {{ background: {PAPER}; color: {INK2}; font-family: "{self.mono}"; font-size: 9pt; }}
            QWidget#bar, QWidget#side {{ background: {C_PANEL2}; }}
            QWidget#bar {{ border-bottom: 1px solid {C_BORDER}; }}
            QWidget#side {{ border-right: 1px solid {C_BORDER}; }}
            QWidget#screen {{ background: #000000; }}
            QWidget#controls {{ background: {C_PANEL2}; }}
            QWidget#bilan {{ background: {C_PANEL2}; border-bottom: 1px solid {C_BORDER}; }}
            QWidget#production {{ background: {C_PANEL2}; border-top: 1px solid {C_BORDER}; }}
            QFrame#setuprow {{ background: {C_PANEL}; border: 1px solid {C_BORDER}; border-radius: 10px; }}
            QWidget#settings, QWidget#following, QWidget#finished {{ background: {C_PANEL2}; }}
            QWidget#paper, QWidget#paper QWidget {{ background: {PAPER}; }}
            QTextEdit {{ background: {PAPER}; color: {INK}; border: none; font-family: "{self.serif}"; font-size: {pt}pt; padding: 26px 20px; selection-background-color: {STABILO}; }}
            QListWidget#passages {{ background: {C_PANEL2}; border: none; outline: none; padding: 4px; }}
            QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }} QScrollBar::handle:vertical {{ background: {C_BORDER}; min-height: 24px; border-radius: 5px; }}
            QTextEdit QScrollBar::handle:vertical {{ background: {RULE}; }}
            QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }} QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
            QLineEdit, QComboBox {{ background: {C_PANEL}; color: {C_TEXT}; border: 1px solid {C_BORDER}; border-radius: 9px; padding: 7px 11px; }}
            QLineEdit:focus, QComboBox:focus {{ border-color: {C_ACCENT}; }}
            QComboBox::drop-down {{ border: none; width: 22px; }} QComboBox::down-arrow {{ image: none; border-left: 4px solid transparent; border-right: 4px solid transparent; border-top: 5px solid {C_MUTED}; margin-right: 8px; }}
            QComboBox QAbstractItemView {{ background: {C_PANEL}; color: {C_TEXT}; border: 1px solid {C_BORDER}; selection-background-color: {C_BORDER}; selection-color: {C_TEXT}; outline: none; }}
            QPushButton, QToolButton {{ background: {C_PANEL}; color: {C_TEXT}; border: 1px solid {C_BORDER}; border-radius: 9px; padding: 7px 14px; font-weight: 600; }}
            QToolButton::menu-indicator {{ image: none; width: 0; }}
            QPushButton:hover, QToolButton:hover {{ border-color: #454b5a; }}
            QPushButton:disabled {{ color: {C_MUTED}; border-color: {C_BORDER}; background: {C_PANEL}; }}
            QPushButton[kind="strong"] {{ background: {C_ACCENT}; border-color: {C_ACCENT}; color: #1b1205; padding: 10px 16px; }}
            QPushButton[kind="strong"]:hover {{ background: {C_ACCENT_H}; }}
            QPushButton[kind="strong"]:disabled {{ background: {C_PANEL}; border-color: {C_BORDER}; color: {C_MUTED}; }}
            QPushButton[kind="danger"] {{ background: transparent; border-color: {C_DANGER}; color: {C_DANGER_T}; }}
            QPushButton[kind="glyph"] {{ min-width: 30px; padding: 6px 8px; }}
            QPushButton[kind="paper"] {{ background: #ffffff; color: {INK}; border-color: #d5cebd; }}
            QWidget#seg {{ border: 1px solid {C_BORDER}; border-radius: 9px; background: {C_PANEL}; }}
            QPushButton#segbtn {{ border: none; border-radius: 0; background: {C_PANEL}; color: {C_MUTED}; padding: 7px 14px; }}
            QPushButton#segbtn[side="first"] {{ border-top-left-radius: 9px; border-bottom-left-radius: 9px; }}
            QPushButton#segbtn[side="last"] {{ border-top-right-radius: 9px; border-bottom-right-radius: 9px; }}
            QPushButton#segbtn:checked {{ background: {STABILO}; color: #1b1a12; }}
            QPushButton#segbtn[kind="erase"]:checked {{ background: #d9d4c7; color: #1b1a12; }}
            QPushButton#segbtn[kind="cut"]:checked {{ background: {RAYE}; color: #4a1712; }}
            QFrame#recent {{ background: {C_PANEL}; border: 1px solid {C_BORDER}; border-radius: 10px; }}
            QFrame#recent:hover {{ border-color: {C_ACCENT}; }}
            QFrame#recent[absent="true"] {{ color: {C_MUTED}; }}
            QFrame#recent QLabel {{ background: transparent; }}
            QLabel#recentName {{ font-weight: 600; }}
            QCheckBox {{ spacing: 8px; }} QCheckBox::indicator {{ width: 15px; height: 15px; border: 1px solid {C_MUTED}; border-radius: 4px; background: {C_PANEL}; }}
            QCheckBox::indicator:checked {{ background: {C_ACCENT}; border-color: {C_ACCENT}; }}
            QSlider::groove:horizontal {{ height: 4px; background: {C_BORDER}; border-radius: 2px; }} QSlider::handle:horizontal {{ width: 12px; margin: -5px 0; background: {C_TEXT}; border-radius: 6px; }}
            QSlider::sub-page:horizontal {{ background: {C_ACCENT}; border-radius: 2px; }}
            QProgressBar {{ border: none; background: #262a34; border-radius: 3px; }} QProgressBar::chunk {{ background: {C_ACCENT}; border-radius: 3px; }}
            QWidget#paper QProgressBar {{ background: {RULE}; }}
            QWidget#paper QPushButton, QWidget#paper QComboBox {{ background: #ffffff; color: {INK}; border-color: #d5cebd; }}
            QWidget#paper QComboBox QAbstractItemView {{ background: #ffffff; color: {INK}; selection-background-color: {RULE}; selection-color: {INK}; }}
            QSplitter::handle {{ background: {C_BORDER}; width: 1px; }}
            QWidget#paper QTableView {{ background: {PAPER}; color: {INK}; border: none; font-size: {max(8, pt - 1)}pt; selection-background-color: {RULE}; selection-color: {INK}; outline: none; }}
            QWidget#paper QTableView::item {{ padding: 4px 8px; border-bottom: 1px solid {RULE}; }}
            QWidget#paper QTableView::item:selected {{ background: {RULE}; color: {INK}; }}
            QWidget#paper QHeaderView {{ background: {PAPER}; }}
            QWidget#paper QHeaderView::section {{ background: {PAPER}; color: {INK2}; border: none; border-bottom: 1px solid {RULE}; padding: 4px 8px; font-weight: 600; font-size: 9pt; }}
            QWidget#paper QTableView QPlainTextEdit {{ background: #ffffff; color: {INK}; border: 1px solid {C_ACCENT}; font-size: {max(8, pt - 1)}pt; padding: 2px 6px; }}
            QWidget#paper QTableView QLineEdit {{ background: #ffffff; color: {INK}; border: 1px solid {C_ACCENT}; border-radius: 0; padding: 2px 6px; font-family: "{self.mono}"; }}
            QTableCornerButton::section {{ background: {PAPER}; border: none; }}
            QLabel#overlay {{ background: rgba(0, 0, 0, 0.55); color: #ffffff; font-family: Arial, "{SANS_FAMILY}"; font-weight: 600; padding: 2px 10px; border-radius: 4px; }}
            QWidget#controls, QWidget#paper QWidget#controls, QWidget#controls QWidget {{ background: {C_PANEL2}; }}
            QWidget#controls QPushButton, QWidget#controls QComboBox {{ background: {C_PANEL}; color: {C_TEXT}; border-color: {C_BORDER}; }}
            QWidget#controls QLabel {{ background: transparent; color: {C_TEXT}; }}
            QMenu {{ background: {C_PANEL}; color: {C_TEXT}; border: 1px solid {C_BORDER}; padding: 4px; }}
            QMenu::item {{ padding: 6px 18px; border-radius: 6px; }} QMenu::item:selected {{ background: {C_BORDER}; }}
            QMenu::separator {{ height: 1px; background: {C_BORDER}; margin: 4px 8px; }}
        """)
        if self.tokens:
            self.page.rebuild()
        self.fit_measure()
        if hasattr(self, "editor"):
            self.editor.refont()
            self.place_overlay()

    # ---- the two views ----
    def show_home(self):
        if self.thread and not (self.task and self.task.get("download")):
            return
        self.stop_preview()
        self.player.stop()
        self.player.setMedia(QMediaContent())
        self.project, self.tokens, self.cuts = None, [], []
        self.texts, self.view, self.project_file, self.cues = {}, "src", None, {}
        self.subs_mode = False
        self.b_subs.setChecked(False)
        self.page_stack.setCurrentWidget(self.page)
        self.refresh_overlay()
        self.page.set_tokens([], [])
        self.views.setCurrentWidget(self.home)
        self.h_error.setText("")
        self.refresh_recents()
        self.h_field.setFocus()

    def refresh_recents(self):
        while self.h_recents.count():
            item = self.h_recents.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        rows = []
        try:
            for d in Path(PROJECTS_DIR).iterdir():
                pj = read_json(d / "project.json")
                if pj and pj.get("source"):
                    stamp = max((f.stat().st_mtime for f in d.iterdir() if f.is_file()), default=0)
                    rows.append((stamp, pj))
        except OSError:
            pass
        rows.sort(key=lambda r: -r[0])
        seen = set()
        for _stamp, pj in rows:
            if pj["source"] in seen:
                continue
            seen.add(pj["source"])
            w = Recent(pj["source"], pj.get("type", "video"), float(pj.get("duration", 0)), os.path.exists(pj["source"]))
            w.clicked.connect(lambda path: self.open_source(path, None))
            self.h_recents.addWidget(w)
            if len(seen) >= 8:
                break
        self.h_resume.setVisible(bool(seen))

    def home_open(self):
        text = self.h_field.text().strip()
        if not text:
            self.h_error.setText(_("Give a file or an address."))
            return
        if is_url(text):
            self.open_url(text)
        elif os.path.isfile(text) and text.endswith(PROJECT_EXT):
            self.open_project_file(text)
        elif os.path.isfile(text):
            self.open_source(text, None)
        else:
            self.h_error.setText(_("This file cannot be read."))

    def set_reading(self, on):
        """Reading: the page alone across the window, the picture hidden and the player's
        controls under the text. The highlighting stays."""
        self.reading = bool(on)
        if self.reading and self.subs_mode:
            self.set_subtitles(False)
        self.b_read.setChecked(self.reading)
        self.b_read.setText(_("Edit") if self.reading else _("Read"))
        if self.reading:
            self.side.hide()
            self.rv.addWidget(self.controls)
        else:
            self.rv.removeWidget(self.controls)
            self.sv.insertWidget(1, self.controls)
            self.side.show()
        self.apply_style()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.fit_measure()

    def fit_measure(self):
        """The text no wider than about 72 characters, centred on the page (as the original page)."""
        if not hasattr(self, "page"):
            return
        fm = QtGui.QFontMetrics(QtGui.QFont(self.serif, self.page_pt + (2 if self.reading else 0)))
        chars = fm.averageCharWidth() * 72 + GUTTER + 48
        margin = max(0, (self.page.width() - chars) // 2)
        self.page.setViewportMargins(margin, 8, margin, 8)

    def save_text(self):
        if not self.tokens or not self.project:
            return
        src = Path(self.project["source"])
        out, _f = QtWidgets.QFileDialog.getSaveFileName(self, _("Save the text"), str(src.with_suffix(".txt")), _("Text (*.txt)"))
        if not out:
            return
        with open(out, "w", encoding="utf-8") as f:
            f.write(self.page.plain_text())
        self.say(_("Text saved: %1", out))

    def copy_text(self):
        if not self.tokens:
            return
        QtWidgets.QApplication.clipboard().setText(self.page.plain_text())
        self.say(_("Text copied."))

    def resize_text(self, d):
        self.page_pt = max(9, min(28, self.page_pt + d))
        self.cfg["page_pt"] = self.page_pt
        save_config(self.cfg)
        self.apply_style()

    def enable(self, loaded):
        for w in (self.fade, self.image_fade, self.format, self.b_preview, self.b_clear, self.b_silences, self.b_read, self.b_subs, self.b_text, self.b_undo, self.b_redo,
                  self.b_project, self.subs, self.srt_files, self.lang_box, self.sound):
            w.setEnabled(loaded)
        self.caption_style.setEnabled(loaded and (self.subs.currentData() or "none") != "none")
        self.refresh_frame_option()
        for w in (self.b_highlight, self.b_erase, self.b_keep, self.b_cut):
            w.setEnabled(loaded and not self.subs_mode)
        self.b_produce.setEnabled(loaded and bool(self.cuts) and self.thread is None)

    # ---- opening ----
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        urls = e.mimeData().urls()
        paths = [u.toLocalFile() for u in urls if u.isLocalFile()]
        srt = next((p for p in paths if p.lower().endswith(".srt")), None)
        media = next((p for p in paths if Path(p).suffix.lower() in EXT_VIDEO | EXT_AUDIO), None)
        link = next((u.toString() for u in urls if not u.isLocalFile() and is_url(u.toString())), None)
        project = next((p for p in paths if p.endswith(PROJECT_EXT)), None)
        if project:
            self.open_project_file(project)
        elif media:
            self.open_source(media, srt)
        elif srt and self.project:
            self.load_srt(srt)
        elif link:
            self.open_url(link)

    def ask_url(self):
        if self.thread:
            return
        self.show_home()
        clip = QtWidgets.QApplication.clipboard().text().strip()
        if is_url(clip):
            self.h_field.setText(clip)
        self.h_field.setFocus()
        self.h_field.selectAll()

    def open_url(self, url):
        if self.thread or not is_url(url):
            return
        if not ffmpeg_exe():
            self.say(_("ffmpeg was not found. Install it (ffmpeg.org) and start again."))
            return
        self.views.setCurrentWidget(self.home)
        self.h_field.setText(url)
        self.h_error.setText("")
        folder = downloads_dir()
        language = self.h_lang.currentData() or ""
        self.task = {"cancelled": False, "proc": None, "download": True}
        task = self.task

        def work(w):
            exe = ytdlp_exe()
            if not exe:
                try:
                    exe = fetch_ytdlp(lambda f: w.progress.emit(0.1 * f, _("Fetching yt-dlp (once)…")), lambda: w.cancelled or task["cancelled"])
                except Cancelled:
                    raise
                except Exception as ex:      # noqa: BLE001
                    raise RuntimeError(_("yt-dlp could not be fetched (no network?): %1", str(ex)[:200]))
            update_ytdlp(exe, lambda: w.progress.emit(0.1, _("Updating yt-dlp…")))
            return download_media(task, exe, url, folder, language, lambda f, t: w.progress.emit(0.1 + 0.9 * f, t))

        def done(result):
            self.task = None
            self.h_follow.hide()
            self.h_open.setEnabled(True)
            media, srt = result
            self.open_source(media, srt)

        def failed(msg):
            self.task = None
            self.h_follow.hide()
            self.h_open.setEnabled(True)
            self.h_error.setText(msg or _("Cancelled."))
        self.h_open.setEnabled(False)
        self.h_follow.show()
        self.h_gauge.setValue(0)
        self.h_msg.setText(_("Downloading…"))
        self.run_in_background(work, done, failed)

    def ask_open(self):
        if self.thread:
            return
        start = self.cfg.get("last_dir") or os.path.expanduser("~")
        exts = " ".join("*" + e for e in sorted(EXT_VIDEO | EXT_AUDIO))
        path, _f = QtWidgets.QFileDialog.getOpenFileName(self, _("Open a video or a recording"), start,
                                                         _("Video and audio files") + f" ({exts});;" + _("Project (*.rve.json)"))
        if path and path.endswith(PROJECT_EXT):
            self.open_project_file(path)
        elif path:
            self.open_source(path, None)

    def ask_srt(self):
        if not self.project or self.thread:
            return
        start = str(Path(self.project["source"]).parent)
        path, _f = QtWidgets.QFileDialog.getOpenFileName(self, _("Open the subtitles of this file"), start, _("Subtitles (*.srt)"))
        if path:
            self.load_srt(path)

    def ask_transcribe(self):
        """The language and the model, then the text is made again (the highlighting stays, by time)."""
        if not self.project or self.thread:
            return
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(_("Transcribe again…"))
        v = QtWidgets.QVBoxLayout(dlg)
        v.setContentsMargins(18, 16, 18, 14)
        v.setSpacing(10)
        row = QtWidgets.QHBoxLayout()
        lang = QtWidgets.QComboBox()
        for code, name in LANGUAGES:
            lang.addItem(_("auto") if not code else name, code)
        lang.setCurrentIndex(self.h_lang.currentIndex())
        model = QtWidgets.QComboBox()
        model.addItems(MODELS)
        model.setCurrentText(self.h_model.currentText())
        lab = QtWidgets.QLabel(_("Spoken language"))
        lab.setObjectName("muted")
        row.addWidget(lab)
        row.addWidget(lang)
        lab = QtWidgets.QLabel(_("model"))
        lab.setObjectName("muted")
        row.addWidget(lab)
        row.addWidget(model)
        v.addLayout(row)
        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self._btn(_("Cancel"), dlg.reject))
        buttons.addWidget(self._btn(_("Transcribe"), dlg.accept, kind="strong"))
        v.addLayout(buttons)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            self.h_lang.setCurrentIndex(lang.currentIndex())
            self.h_model.setCurrentText(model.currentText())
            self.start_transcription()

    def retry_transcription(self):
        self.h_lang.setCurrentIndex(self.p_lang.currentIndex())
        self.h_model.setCurrentText(self.p_model.currentText())
        self.start_transcription()

    def open_source(self, path, srt, project=None):
        """Opens a video or a recording; with `project` (the content of a project file) its text,
        translations and highlighting take the place of what the project folder holds."""
        if self.thread:
            return
        if not ffmpeg_exe():
            self.say(_("ffmpeg was not found. Install it (ffmpeg.org) and start again."))
            return
        self.stop_preview()
        self.player.stop()
        info = probe(path)
        if not info:
            self.say(_("This file cannot be read."))
            return
        self.cfg["last_dir"] = str(Path(path).parent)
        save_config(self.cfg)
        d = project_dir(path)
        self.project = dict(info, source=os.path.abspath(path), dir=str(d))
        write_json(d / "project.json", {k: v for k, v in self.project.items() if k != "dir"})
        self.project_file = None
        if project:
            self.install_project(d, project)
        self.a_name.setText(Path(path).name)
        self.detail = (_("Video") if info["type"] == "video" else _("Recording")) + " · " + plain(info["duration"])
        self.show_project_name()
        self.tokens, self.cuts, self.texts, self.view, self.cues = [], [], {}, "src", {}
        self.subs_mode = False
        self.b_subs.setChecked(False)
        self.page_stack.setCurrentWidget(self.page)
        self.refresh_overlay()
        self.page.set_tokens([], [])
        self.lang_box.hide()
        self.format.clear()
        if info["type"] == "video":
            self.format.addItem(_("A video (MP4)"), "mp4")
        self.screen.setVisible(info["type"] == "video")
        for fmt in ("mp3", "m4a", "wav"):
            self.format.addItem(_("The sound alone (%1)", fmt.upper()), fmt)
        if project and (project.get("output") or {}).get("format"):
            k = self.format.findData(project["output"]["format"])
            if k >= 0:
                self.format.setCurrentIndex(k)
        self.b_preview.setText(_("▶ Watch the edit") if info["type"] == "video" else _("▶ Listen to the edit"))
        self.b_watch.setText(_("Watch") if info["type"] == "video" else _("Listen"))
        self.media_ok = True
        self.player.setMedia(QMediaContent(QtCore.QUrl.fromLocalFile(os.path.abspath(path))))
        if Path(path).suffix.lower() == ".mp3":
            src = os.path.abspath(path)
            threading.Thread(target=lambda: self.listening_ready.emit(src, listening_copy(src, d)), daemon=True).start()
        self.slider.setMaximum(int(info["duration"] * 1000))
        self.views.setCurrentWidget(self.shop)
        self.show_production("settings")
        self.status.hide()
        self.enable(False)
        self.set_reading(False)
        # a text already made for this file, or subtitles beside it
        saved = read_json(d / "transcription.json")
        beside = Path(path).with_suffix(".srt")
        if srt:
            self.load_srt(srt)
        elif saved and saved.get("tokens"):
            self.show_tokens(saved["tokens"], saved.get("origin", "transcription"), bool(saved.get("estimated")), saved.get("language", ""))
        elif beside.exists():
            self.load_srt(str(beside))
        else:
            self.start_transcription()

    def use_listening_copy(self, source, copy):
        """The AAC copy of an MP3 takes its place in the player, at the same moment."""
        if not self.project or self.project.get("source") != source or copy == source:
            return
        pos = self.player.position()
        playing = self.player.state() == QMediaPlayer.PlayingState
        self.player.setMedia(QMediaContent(QtCore.QUrl.fromLocalFile(copy)))
        if pos:
            self.player.setPosition(pos)
        if playing:
            self.player.play()

    def say(self, text):
        if self.views.currentWidget() is self.home:
            self.h_error.setText(text)
        else:
            self.status.setText(text)
            self.status.setVisible(bool(text))

    # ---- the waiting view ----
    def wait(self, message, detail="", failed=False):
        self.page_stack.setCurrentWidget(self.patience)
        self.p_msg.setText(message)
        self.p_detail.setText(detail)
        self.p_gauge.setVisible(not failed)
        self.p_retry.setVisible(failed)
        if failed:
            self.p_lang.setCurrentIndex(self.h_lang.currentIndex())
            self.p_model.setCurrentText(self.h_model.currentText())

    # ---- text: subtitles or transcription ----
    def run_in_background(self, fn, on_done, on_failed):
        self.thread = QtCore.QThread(self)
        self.worker = Worker(fn)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)

        def finish():
            self.thread.quit()
            self.thread.wait(2000)
            self.thread, self.worker = None, None

        def done(result):
            finish()
            on_done(result)

        def failed(msg):
            finish()
            on_failed(msg)
        self.worker.done.connect(done)
        self.worker.failed.connect(failed)
        self.worker.progress.connect(self.on_progress)
        self.thread.start()

    def on_progress(self, fraction, text):
        if self.setup_active is not None:
            self.setup_active.detail.setText(text)
            return
        if self.task and self.task.get("download"):
            self.h_gauge.setValue(int(fraction * 1000))
            self.h_msg.setText(text)
        elif self.task is not None and not self.task.get("page"):
            self.progress.setValue(int(fraction * 1000))
            self.f_text.setText(text)
        else:
            self.p_gauge.setValue(int(fraction * 1000))
            self.p_detail.setText(text)

    def load_srt(self, path):
        if self.thread or not self.project:
            return
        cues = read_srt(path)
        if not cues:
            self.say(_("No subtitle in this file."))
            return
        d = Path(self.project["dir"])
        wav = d / "audio16k.wav"
        duration = self.project["duration"]
        src = self.project["source"]

        def work(w):
            w.progress.emit(0.1, _("Extracting the sound…"))
            extract_audio(src, wav)
            w.progress.emit(0.6, _("Looking for the words in the sound…"))
            return tokens_from_srt(cues, wav, duration)

        def done(tokens):
            self.forget_cues("src")
            write_json(d / "transcription.json", {"tokens": tokens, "origin": "subtitles", "estimated": True, "language": ""})
            self.show_tokens(tokens, "subtitles", True)

        def failed(msg):
            self.wait(_("The transcription failed."), msg or _("Cancelled."), failed=True)
        self.wait(_("Reading the file…"))
        self.run_in_background(work, done, failed)

    def start_transcription(self):
        if self.thread or not self.project:
            return
        d = Path(self.project["dir"])
        wav = d / "audio16k.wav"
        duration = self.project["duration"]
        src = self.project["source"]
        language = self.h_lang.currentData() or ""
        model_size = self.h_model.currentText()
        self.cfg["language"], self.cfg["model"] = language, model_size
        save_config(self.cfg)
        # what was highlighted stays, by time, when the text is made again
        if self.tokens:
            clean = clean_ranges(self.page.ranges(), len(self.tokens))
            sel = read_json(d / "selection.json", {}) or {}
            sel["times"] = [[self.tokens[i][1], self.tokens[j][2]] for i, j in clean]
            sel.pop("ranges", None)
            write_json(d / "selection.json", sel)

        def work(w):
            if not whisper_available():
                install_whisper(lambda t: w.progress.emit(0.01, t), lambda: w.cancelled)
            w.progress.emit(0.02, _("Extracting the sound…"))
            extract_audio(src, wav)
            w.progress.emit(0.05, _("Loading the model %1 (downloaded once)…", model_size))
            words, lang = transcribe(wav, language, model_size, duration,
                                     lambda f: w.progress.emit(0.05 + 0.93 * f, _("Transcribing… %1 %", int(f * 100))),
                                     lambda: w.cancelled)
            if not words:
                raise RuntimeError(_("No speech was found in this file."))
            return tokens_from_words(words, duration), lang

        def done(result):
            tokens, lang = result
            self.forget_cues("src")
            write_json(d / "transcription.json", {"tokens": tokens, "origin": "transcription", "estimated": False, "language": lang})
            self.show_tokens(tokens, "transcription", False, lang)

        def failed(msg):
            self.wait(_("The transcription failed."), msg or _("Cancelled."), failed=True)
        self.wait(_("Transcribing…"))
        self.run_in_background(work, done, failed)

    def show_tokens(self, tokens, origin, estimated, language=""):
        """The original text is ready: it and the translations of the project folder become the
        views, and the page shows the one the project was on."""
        d = Path(self.project["dir"])
        self.src_lang = language or ""
        self.texts = {"src": {"tokens": tokens, "origin": origin, "estimated": estimated, "language": self.src_lang}}
        for f in sorted(d.glob("translation-*.json")):
            tr = read_json(f)
            if tr and tr.get("tokens") and tr.get("language"):
                self.texts[tr["language"]] = {"tokens": tr["tokens"], "origin": "translation", "estimated": True, "language": tr["language"]}
        self.cues = {}
        for f in sorted(d.glob("cues-*.json")):
            c = read_json(f)
            key = f.stem[5:]
            if c and isinstance(c.get("cues"), list) and (key == "src" or key in self.texts):
                self.cues[key] = {"language": c.get("language", ""), "cues": [list(x) for x in c["cues"]], "edited": bool(c.get("edited"))}
        sel = read_json(d / "selection.json", {}) or {}
        view = sel.get("view", "src")
        self.show_view(view if view in self.texts else "src", first=True)

    def show_view(self, key, first=False):
        """The page shows the original text or a translation. The highlighting is kept in
        seconds and finds its words in the other text (the rule of monter.py)."""
        if key not in self.texts or self.thread:
            return
        d = Path(self.project["dir"])
        sel = read_json(d / "selection.json", {}) or {}
        if not first and self.tokens:
            clean = clean_ranges(self.page.ranges(), len(self.tokens))
            sel["times"] = [[self.tokens[i][1], self.tokens[j][2]] for i, j in clean]
            sel.pop("ranges", None)
        text = self.texts[key]
        tokens = text["tokens"]
        if sel.get("times") and "ranges" not in sel:
            sel["ranges"] = ranges_from_times(tokens, sel.pop("times"))
        sel["view"] = key
        write_json(d / "selection.json", sel)
        self.view = key
        self.tokens, self.origin, self.estimated = tokens, text["origin"], text["estimated"]
        self.set_mode(sel.get("mode", "keep"), quiet=True)
        self.page.set_tokens(tokens, sel.get("ranges", []), text["origin"])
        self.rebuild_language_switch()
        self.rebuild_subtitle_options()
        self.enable(True)
        self.on_selection()
        if self.subs_mode:
            self.show_editor()
        else:
            self.page_stack.setCurrentWidget(self.page)
            self.refresh_overlay()

    def view_code(self):
        """The language of the text on the page ('' when the original's is unknown)."""
        return self.src_lang if self.view == "src" else self.view

    def rebuild_language_switch(self):
        lay = self.lang_box.layout()
        while lay.count():
            item = lay.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        keys = ["src"] + sorted(k for k in self.texts if k != "src")
        self.lang_box.setVisible(len(keys) > 1)
        if len(keys) < 2:
            return
        buttons = []
        for k in keys:
            b = self._btn(lang_label(self.src_lang if k == "src" else k), lambda _c=False, k=k: self.show_view(k),
                          tip=_("Original") if k == "src" else _("Translation"))
            buttons.append(b)
        lay.addWidget(self._segment(buttons))
        for k, b in zip(keys, buttons):
            b.setChecked(k == self.view)

    def rebuild_subtitle_options(self):
        """The subtitles that can go into the picture: none, the original, each translation."""
        if not self.project:
            return
        video = self.project["type"] == "video"
        wanted = self.subs.currentData() or self.cfg.get("burn", "none")
        self.subs.blockSignals(True)
        self.subs.clear()
        self.subs.addItem(_("None"), "none")
        for k in ["src"] + sorted(k for k in self.texts if k != "src"):
            self.subs.addItem(_("In the picture: %1", lang_label(self.src_lang if k == "src" else k)), k)
        i = self.subs.findData(wanted)
        self.subs.setCurrentIndex(i if i >= 0 else 0)
        self.subs.blockSignals(False)
        self.subs.setVisible(video)
        self.l_subs.setVisible(video)
        self.caption_style.setVisible(video)
        self.refresh_overlay()

    def remember_output(self):
        if self.subs.currentData():
            self.cfg["burn"] = self.subs.currentData()
        self.cfg["srt_files"] = self.srt_files.isChecked()
        self.cfg["frame"], self.cfg["sound"] = self.frame.currentData() or "as_is", self.sound.currentData() or "as_is"
        self.cfg["caption_style"] = self.caption_style.currentData() or "subtitles"
        self.caption_style.setEnabled((self.subs.currentData() or "none") != "none")
        save_config(self.cfg)
        self.refresh_overlay()

    def refresh_frame_option(self):
        """The square frame concerns the picture: greyed when the sound alone is produced."""
        video = self.format.currentData() == "mp4" and bool(self.project) and bool(self.tokens)
        self.frame.setEnabled(video)
        self.l_frame.setEnabled(video)

    def toolkit_for_sound(self):
        """The toolkit folder for finaliser.py: the one found, or asked for in a small dialog;
        None when the user gives up."""
        where = toolkit_dir(self.cfg)
        if where and os.path.isfile(os.path.join(where, "finaliser.py")):
            return where
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(_("Improve the sound"))
        dlg.setMinimumWidth(620)
        v = QtWidgets.QVBoxLayout(dlg)
        v.setContentsMargins(18, 16, 18, 14)
        v.setSpacing(10)
        folder = self._toolkit_row(dlg, v, _("The traduction toolkit improves the sound (finaliser.py). It was not found: give its folder, or install it from %1.", TOOLKIT_URL), force=True)
        error = QtWidgets.QLabel("")
        error.setObjectName("danger")
        error.setWordWrap(True)
        v.addWidget(error)
        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self._btn(_("Cancel"), dlg.reject))
        go = self._btn(_("Continue"), None, kind="strong")
        buttons.addWidget(go)
        v.addLayout(buttons)
        chosen = []

        def accept():
            where = self._toolkit_from(folder, error, "finaliser.py")
            if not where:
                return
            save_config(self.cfg)
            chosen.append(where)
            dlg.accept()
        go.clicked.connect(accept)
        dlg.exec_()
        return chosen[0] if chosen else None

    def show_project_name(self):
        name = Path(self.project_file).name if self.project_file else ""
        self.a_detail.setText(self.detail + (" · " + name if name else ""))

    # ---- the translation (traduire.py, through the toolkit's Python) ----
    def _toolkit_row(self, dlg, v, message=None, force=False):
        """When the toolkit is not found: the message and a field for its folder, in a dialog.
        Returns the field, or None when the toolkit is there (unless `force`)."""
        if toolkit_dir(self.cfg) and not force:
            return None
        lab = QtWidgets.QLabel(message or _("The traduction toolkit does the translation (traduire.py). It was not found: give its folder, or install it from %1.", TOOLKIT_URL))
        lab.setObjectName("danger")
        lab.setWordWrap(True)
        v.addWidget(lab)
        row = QtWidgets.QHBoxLayout()
        folder = QtWidgets.QLineEdit(self.cfg.get("toolkit_dir") or "")
        folder.setPlaceholderText(_("Folder of the traduction toolkit"))
        row.addWidget(folder, 1)

        def browse():
            d = QtWidgets.QFileDialog.getExistingDirectory(dlg, _("Folder of the traduction toolkit"), folder.text() or os.path.expanduser("~"))
            if d:
                folder.setText(d)
        row.addWidget(self._btn(_("Browse…"), browse))
        v.addLayout(row)
        status = QtWidgets.QLabel("")
        status.setObjectName("muted")
        status.setWordWrap(True)
        here = self._btn(_("Install it here (download, a few MB)"), None, kind="strong")

        def install():
            here.setEnabled(False)
            status.setText(_("Downloading the traduction toolkit…"))
            box, task = {}, {"cancelled": False}

            def run():
                try:
                    box["where"] = install_toolkit(lambda t: None, task)
                except Exception as ex:        # noqa: BLE001
                    box["error"] = str(ex)[:300]
            th = threading.Thread(target=run, daemon=True)
            th.start()
            while th.is_alive():
                QtWidgets.QApplication.processEvents()
                time.sleep(0.05)
            if "where" in box:
                folder.setText(box["where"])
                self.cfg["toolkit_dir"] = box["where"]
                save_config(self.cfg)
                status.setText(_("Installed in %1. Its libraries will be installed by the app when a feature needs them.", box["where"]))
            else:
                status.setText(_("The download failed: %1", box.get("error", "")))
                here.setEnabled(True)
        here.clicked.connect(install)
        row2 = QtWidgets.QHBoxLayout()
        row2.addWidget(here)
        row2.addWidget(status, 1)
        v.addLayout(row2)
        return folder

    def _toolkit_from(self, folder, error, needs="traduire.py"):
        """The toolkit folder a dialog settled on, or None after the error is shown."""
        where = toolkit_dir(self.cfg)
        if folder is not None:
            where = folder.text().strip()
            if not os.path.isfile(os.path.join(where, needs)):
                error.setText(_("traduire.py is not in this folder.") if needs == "traduire.py" else _("finaliser.py is not in this folder."))
                return None
            self.cfg["toolkit_dir"] = where
        return where

    def _llm_rows(self, g, row, label):
        """Two fields of a dialog: who does the work, the model on this computer (Ollama) or
        Claude, and which Ollama model. Returns the two widgets."""
        llm = QtWidgets.QComboBox()
        llm.addItem(_("On this computer (Ollama)"), "local")
        llm.addItem(_("Claude Code (your own plan)"), "claude_code")
        llm.addItem(_("Claude (API key)") + " · " + LLM_CLAUDE_MODEL, "claude")
        llm.setCurrentIndex(max(0, llm.findData(self.cfg.get("llm") or "local")))
        model = QtWidgets.QLineEdit(self.cfg.get("ollama_model") or LLM_LOCAL_MODEL)
        model.setPlaceholderText(LLM_LOCAL_MODEL)
        llm.currentIndexChanged.connect(lambda i: model.setEnabled(i == 0))
        model.setEnabled(llm.currentIndex() == 0)
        for col, (text, w) in enumerate(((label, llm), (_("Ollama model"), model))):
            lab = QtWidgets.QLabel(text)
            lab.setObjectName("label")
            g.addWidget(lab, row, col)
            g.addWidget(w, row + 1, col)
        # the Anthropic key, kept in the app's settings (1.7.0): no environment variable to set
        key_lab = QtWidgets.QLabel(_("Anthropic API key"))
        key_lab.setObjectName("label")
        key = QtWidgets.QLineEdit(self.cfg.get("anthropic_key") or os.environ.get("ANTHROPIC_API_KEY") or "")
        key.setEchoMode(QtWidgets.QLineEdit.Password)
        key.setPlaceholderText("sk-ant-…")
        g.addWidget(key_lab, row + 2, 0, 1, 2)
        g.addWidget(key, row + 3, 0, 1, 2)

        hint = QtWidgets.QLabel("")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        g.addWidget(hint, row + 4, 0, 1, 2)

        def show_key(i):
            kind = llm.itemData(i)
            key_lab.setVisible(kind == "claude")
            key.setVisible(kind == "claude")
            if kind == "claude_code":
                exe = find_claude(quick=True)
                hint.setText(_("Claude Code found: %1", exe) if exe else _("Claude Code is not installed: « Getting started » on the home page installs it."))
            elif kind == "local":
                hint.setText(_("Ollama answers.") if ollama_answers(OLLAMA_URL) else _("Ollama does not answer: « Getting started » on the home page sets it up."))
            else:
                hint.setText("")
            hint.setVisible(bool(hint.text()))
        llm.currentIndexChanged.connect(show_key)
        show_key(llm.currentIndex())
        return llm, model, key

    def anthropic_key(self):
        return self.cfg.get("anthropic_key") or os.environ.get("ANTHROPIC_API_KEY") or ""

    def ask_translate(self):
        if not self.project or self.thread or not self.texts.get("src"):
            return
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(_("Translate…"))
        dlg.setMinimumWidth(660)
        v = QtWidgets.QVBoxLayout(dlg)
        v.setContentsMargins(18, 16, 18, 14)
        v.setSpacing(10)
        folder = self._toolkit_row(dlg, v)
        g = QtWidgets.QGridLayout()
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(6)
        langs = [(c, n) for c, n in LANGUAGES if c]
        src = QtWidgets.QComboBox()
        tgt = QtWidgets.QComboBox()
        for code, name in langs:
            src.addItem(name, code)
            tgt.addItem(name, code)
        src_code = self.src_lang or self.h_lang.currentData() or "en"
        src.setCurrentIndex(max(0, src.findData(src_code)))
        tgt_code = self.cfg.get("target_lang", "fr")
        if tgt_code == src_code:
            tgt_code = "en" if src_code != "en" else "fr"
        tgt.setCurrentIndex(max(0, tgt.findData(tgt_code)))
        for col, (label, w) in enumerate(((_("From"), src), (_("Into"), tgt))):
            lab = QtWidgets.QLabel(label)
            lab.setObjectName("label")
            g.addWidget(lab, 0, col)
            g.addWidget(w, 1, col)
        llm, model, key = self._llm_rows(g, 2, _("Translation by"))
        v.addLayout(g)
        context = QtWidgets.QPlainTextEdit()
        context.setPlaceholderText(_("Context for the translator: names, subject, register (optional)"))
        context.setFixedHeight(70)
        v.addWidget(context)
        review = QtWidgets.QCheckBox(_("Proofreading pass (a second reading by the model)"))
        review.setChecked(bool(self.cfg.get("review", True)))
        v.addWidget(review)
        # with the local model, the analysis pass can still go to Claude (traduire.py's "auto"): said and chosen here
        analysis = QtWidgets.QCheckBox(_("Analysis of the content (names, glossary) by Claude rather than the local model"))
        analysis.setChecked(bool(self.cfg.get("analysis_by_claude", False)))
        analysis.setVisible(llm.currentData() == "local" and bool(self.anthropic_key() or find_claude(quick=True)))
        llm.currentIndexChanged.connect(lambda i: analysis.setVisible(i == 0 and bool(self.anthropic_key() or key.text().strip() or find_claude(quick=True))))
        v.addWidget(analysis)
        error = QtWidgets.QLabel("")
        error.setObjectName("danger")
        error.setWordWrap(True)
        v.addWidget(error)
        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self._btn(_("Cancel"), dlg.reject))
        go = self._btn(_("Translate…").rstrip("…"), None, kind="strong")
        buttons.addWidget(go)
        v.addLayout(buttons)

        def accept():
            where = self._toolkit_from(folder, error)
            if not where:
                return
            if src.currentData() == tgt.currentData():
                error.setText(_("Same as the source language."))
                return
            self.cfg["anthropic_key"] = key.text().strip()
            if llm.currentData() == "claude" and not self.anthropic_key():
                error.setText(_("Give an Anthropic API key."))
                return
            if llm.currentData() == "claude_code" and not find_claude(quick=True):
                error.setText(_("Claude Code is not installed: « Getting started » on the home page installs it."))
                return
            self.cfg["llm"], self.cfg["ollama_model"] = llm.currentData(), model.text().strip() or LLM_LOCAL_MODEL
            self.cfg["review"], self.cfg["target_lang"] = review.isChecked(), tgt.currentData()
            self.cfg["analysis_by_claude"] = analysis.isChecked()
            save_config(self.cfg)
            dlg.accept()
            self.start_translation(where, src.currentData(), tgt.currentData(), llm.currentData(), self.cfg["ollama_model"],
                                   context.toPlainText().strip(), review.isChecked(), analysis.isVisible() and analysis.isChecked())
        go.clicked.connect(accept)
        dlg.exec_()

    def start_translation(self, tk, src, tgt, llm, model, context, review, analysis_by_claude=False):
        d = Path(self.project["dir"])
        segments = segments_from_tokens(self.texts["src"]["tokens"])
        if not segments:
            return
        duration = self.project["duration"]
        job = {"task": "translate", "toolkit": tk, "segments": segments, "source_lang": src, "target_lang": tgt,
               "llm": llm, "ollama_model": model, "ollama_url": OLLAMA_URL, "claude_model": LLM_CLAUDE_MODEL,
               "context": context, "review": review, "analysis_by_claude": analysis_by_claude, **claude_job(self.cfg, llm)}
        # the passes of traduire.py, where each one starts on the gauge, and who does it
        who = model_label(llm, model)
        steps = [("analysis", 0.02, _("Analysing the text…") + " · " + (model_label("claude") if analysis_by_claude else who)),
                 ("translate", 0.08, _("Translating…") + " · " + who), ("review", 0.62, _("Proofreading…") + " · " + who),
                 ("consistency", 0.86, _("Checking the consistency…") + " · " + who), ("glossary", 0.94, _("Checking the glossary…") + " · " + who)]
        self.task = {"cancelled": False, "proc": None, "page": True}
        task = self.task

        def work(w):
            if llm == "local" and not ollama_answers(OLLAMA_URL):
                raise RuntimeError(_("Ollama does not answer at %1.", OLLAMA_URL))
            state = {"base": 0.0, "next": 0.08, "text": ""}

            def on_message(msg):
                if "step" in msg:
                    for k, (name, base, text) in enumerate(steps):
                        if name == msg["step"]:
                            state.update(base=base, text=text, next=steps[k + 1][1] if k + 1 < len(steps) else 1.0)
                            w.progress.emit(base, text)
                elif "line" in msg:
                    m = re.search(r"Chunk (\d+)/(\d+)", msg["line"])
                    if m:
                        i, n = int(m.group(1)), int(m.group(2))
                        w.progress.emit(state["base"] + (state["next"] - state["base"]) * (i - 1) / max(n, 1),
                                        state["text"] + "  " + _("Translating… %1 of %2", i, n).split("…")[-1].strip())
            needs = TOOLKIT_PACKAGES["claude"] if (llm == "claude" or (analysis_by_claude and job["claude_kind"] == "claude")) else []
            py = prepare_toolkit_python(needs, lambda t: w.progress.emit(0.0, t), task)
            result = run_bridge(task, job, d, on_message, python=py, env_extra=claude_env(self.cfg))
            tokens = tokens_from_translation(result["segments"], duration)
            if not any(t[0] for t in tokens):
                raise RuntimeError(_("The translation came back empty."))
            return {"language": tgt, "source_language": src, "segments": result["segments"], "analysis": result.get("analysis"),
                    "tokens": tokens, "llm": llm if llm == "claude" else "ollama " + model, "date": time.strftime("%Y-%m-%d %H:%M")}

        def done(tr):
            self.task = None
            self.p_cancel.hide()
            write_json(d / f"translation-{tgt}.json", tr)
            self.forget_cues(tgt)
            self.texts[tgt] = {"tokens": tr["tokens"], "origin": "translation", "estimated": True, "language": tgt}
            if not self.src_lang:
                # subtitles carry no language: the one given for the translation names the original from now on
                self.src_lang = src
                self.texts["src"]["language"] = src
                saved = read_json(d / "transcription.json", {}) or {}
                if saved.get("tokens"):
                    saved["language"] = src
                    write_json(d / "transcription.json", saved)
            self.show_view(tgt)
            self.say(_("Translated: %1 words", sum(1 for t in tr["tokens"] if t[0] is not None)))

        def failed(msg):
            self.task = None
            self.p_cancel.hide()
            self.page_stack.setCurrentWidget(self.page)
            self.enable(True)
            self.on_selection()
            self.say(_("The translation failed: %1", msg) if msg else _("Cancelled."))
        self.wait(_("Translating into %1…", lang_label(tgt)), steps[0][2])
        self.p_cancel.show()
        self.enable(False)
        self.run_in_background(work, done, failed)

    # ---- the subtitles of the whole file (the text on the page) ----
    def save_srt(self):
        if not self.tokens or not self.project or self.thread:
            return
        src = Path(self.project["source"])
        code = self.view_code()
        out, _f = QtWidgets.QFileDialog.getSaveFileName(self, _("Save the subtitles"), str(src.with_name(f"{src.stem}.{code or 'src'}.srt")), _("Subtitles (*.srt)"))
        if not out:
            return
        tokens, tk, d = list(self.tokens), toolkit_dir(self.cfg), Path(self.project["dir"])
        stored = self.cues.get(self.view)
        task = {"cancelled": False, "proc": None}

        def work(w):
            cues = sorted(stored["cues"]) if stored else make_cues(tokens, code, tk, task, d)
            with open(out, "w", encoding="utf-8") as f:
                f.write(srt_text(cues))
            return out

        def failed(msg):
            self.say(msg or _("Cancelled."))
        self.say(_("Making the subtitles…"))
        self.run_in_background(work, lambda p: self.say(_("Subtitles saved: %1", p)), failed)

    # ---- project files: the same video, one file per edit ----
    def install_project(self, d, project):
        """What a project file holds goes into the project folder, in place of what was there."""
        write_json(d / "transcription.json", project["transcription"])
        for f in d.glob("translation-*.json"):
            f.unlink()
        for k, tr in (project.get("translations") or {}).items():
            if tr and tr.get("tokens"):
                write_json(d / f"translation-{k}.json", tr)
        for f in d.glob("cues-*.json"):
            f.unlink()
        for k, c in (project.get("cues") or {}).items():
            if c and isinstance(c.get("cues"), list):
                write_json(d / f"cues-{k}.json", c)
        sel = dict(project.get("selection") or {})
        sel.pop("times", None)
        write_json(d / "selection.json", sel)
        if "fade" in sel:
            idx = [i for i in range(self.fade.count()) if abs(self.fade.itemData(i) - float(sel["fade"])) < 1e-6]
            if idx:
                self.fade.setCurrentIndex(idx[0])
        if "image_fade" in sel:
            self.image_fade.setChecked(bool(sel["image_fade"]))
        out = project.get("output") or {}
        if "burn" in out:
            self.cfg["burn"] = out["burn"]
        if "srt_files" in out:
            self.srt_files.setChecked(bool(out["srt_files"]))
        for key, combo in (("frame", self.frame), ("sound", self.sound), ("caption_style", self.caption_style)):
            if out.get(key) and combo.findData(out[key]) >= 0:
                combo.setCurrentIndex(combo.findData(out[key]))

    def save_project(self, ask=False):
        if not self.project or not self.tokens or self.thread:
            return
        path = self.project_file
        if ask or not path:
            src = Path(self.project["source"])
            path, _f = QtWidgets.QFileDialog.getSaveFileName(self, _("Save the project"), path or str(src.with_name(src.stem + PROJECT_EXT)), _("Project (*.rve.json)"))
            if not path:
                return
            if not path.endswith(".json"):
                path += PROJECT_EXT
        d = Path(self.project["dir"])
        clean = clean_ranges(self.page.ranges(), len(self.tokens))
        data = {"app": APP, "version": 1, "saved": time.strftime("%Y-%m-%d %H:%M"),
                "source": self.project["source"], "source_name": Path(self.project["source"]).name,
                "type": self.project["type"], "duration": self.project["duration"],
                "transcription": read_json(d / "transcription.json"),
                "translations": {k: read_json(d / f"translation-{k}.json") for k in self.texts if k != "src"},
                "cues": {k: c for k, c in self.cues.items() if k == "src" or k in self.texts},
                "selection": {"view": self.view, "ranges": [list(p) for p in clean], "mode": self.mode_value,
                              "fade": float(self.fade.currentData()), "image_fade": self.image_fade.isChecked()},
                "output": {"format": self.format.currentData(), "burn": self.subs.currentData() or "none", "srt_files": self.srt_files.isChecked(),
                           "frame": self.frame.currentData() or "as_is", "sound": self.sound.currentData() or "as_is",
                           "caption_style": self.caption_style.currentData() or "subtitles"}}
        write_json(path, data)
        self.project_file = path
        self.show_project_name()
        self.say(_("Project saved: %1", path))

    def ask_project(self):
        if self.thread:
            return
        start = self.cfg.get("last_dir") or os.path.expanduser("~")
        path, _f = QtWidgets.QFileDialog.getOpenFileName(self, _("Open a project"), start, _("Project (*.rve.json)"))
        if path:
            self.open_project_file(path)

    def open_project_file(self, path):
        if self.thread:
            return
        data = read_json(path)
        if not isinstance(data, dict) or data.get("app") != APP or not (data.get("transcription") or {}).get("tokens"):
            self.say(_("This is not a project file."))
            return
        source = data.get("source") or ""
        if not os.path.isfile(source):
            beside = Path(path).with_name(data.get("source_name") or "")
            if data.get("source_name") and beside.is_file():
                source = str(beside)
            else:
                self.say(_("The file of this project was not found: %1", source))
                return
        self.open_source(source, None, project=data)
        if self.project and os.path.abspath(self.project["source"]) == os.path.abspath(source):
            self.project_file = path
            self.show_project_name()

    # ---- the subtitle editor ----
    def undo(self):
        (self.editor if self.subs_mode else self.page).undo()

    def redo(self):
        (self.editor if self.subs_mode else self.page).redo()

    def update_undo_buttons(self):
        who = self.editor if self.subs_mode else self.page
        self.b_undo.setEnabled(bool(who.history))
        self.b_redo.setEnabled(bool(who.future))

    def set_subtitles(self, on):
        """Subtitles: the cues of the text on the page take its place, to be read, timed and
        corrected; the picture shows the one being played. The highlighting stays."""
        on = bool(on) and bool(self.tokens) and self.thread is None
        if on and self.reading:
            self.set_reading(False)
        self.subs_mode = on
        self.b_subs.setChecked(on)
        self.enable(bool(self.tokens))
        if on:
            self.show_editor()
        else:
            self.page_stack.setCurrentWidget(self.page)
            self.refresh_overlay()
            self.update_undo_buttons()

    def show_editor(self):
        key = self.view

        def ready():
            if not self.subs_mode or key != self.view or key not in self.cues:
                return
            c = self.cues[key]
            self.editor.duration = self.project["duration"]
            self.editor.set_cues(c["cues"], self.texts["src"]["tokens"] if key != "src" else None, c.get("edited"))
            self.page_stack.setCurrentWidget(self.editor)
            self.refresh_overlay()
            self.update_undo_buttons()
            self.editor.set_current(self.player.position() / 1000.0 + 0.05)
        self.ensure_cues(key, ready)

    def ensure_cues(self, key, then, fresh=False):
        """The subtitles of a text: made once (traduire.py's re-segmentation, in the background),
        then kept in the project folder as they are left."""
        if key in self.cues and not fresh:
            then()
            return
        if self.thread or key not in self.texts:
            return
        tokens, code = list(self.texts[key]["tokens"]), (self.src_lang if key == "src" else key)
        tk, d = toolkit_dir(self.cfg), Path(self.project["dir"])
        self.task = {"cancelled": False, "proc": None, "page": True}
        task = self.task

        def work(w):
            return make_cues(tokens, code, tk, task, d)

        def back():
            self.task = None
            self.p_cancel.hide()
            self.p_gauge.setRange(0, 1000)
            self.enable(True)

        def done(cues):
            back()
            self.store_cues(key, cues, False)
            then()

        def failed(msg):
            back()
            self.set_subtitles(False)
            self.say(msg or _("Cancelled."))
        self.wait(_("Making the subtitles…"))
        self.p_gauge.setRange(0, 0)
        self.p_cancel.show()
        self.enable(False)
        self.run_in_background(work, done, failed)

    def store_cues(self, key, cues, edited):
        code = self.src_lang if key == "src" else key
        self.cues[key] = {"language": code, "cues": [list(c) for c in cues], "edited": bool(edited)}
        write_json(Path(self.project["dir"]) / f"cues-{key}.json", self.cues[key])
        self.refresh_overlay()

    def forget_cues(self, key):
        self.cues.pop(key, None)
        if self.project:
            f = Path(self.project["dir"]) / f"cues-{key}.json"
            if f.exists():
                f.unlink()

    def on_cues_changed(self):
        if self.subs_mode and self.view in self.cues:
            self.store_cues(self.view, self.editor.cues(), True)
        self.update_undo_buttons()

    def recut_cues(self):
        if self.thread or not self.subs_mode:
            return
        c = self.cues.get(self.view)
        if c and c.get("edited"):
            answer = QtWidgets.QMessageBox.question(self, _("Re-cut from the text"),
                                                    _("The subtitles were edited by hand. Cut them again from the text and lose these changes?"))
            if answer != QtWidgets.QMessageBox.Yes:
                return
        self.ensure_cues(self.view, self.show_editor, fresh=True)

    # the picture shows the subtitle being played: the editor's, or the one chosen for the output
    def refresh_overlay(self):
        cues = None
        if self.project and self.project["type"] == "video" and hasattr(self, "subs"):
            key = self.view if self.subs_mode else (self.subs.currentData() or "none")
            if key in self.cues:
                cues = self.cues[key]["cues"]
        self.overlay_src, self.overlay_idx = cues, -2
        self.update_overlay(self.player.position() / 1000.0 + 0.05 if hasattr(self, "player") else 0.0)

    def update_overlay(self, t):
        k = cue_at(self.overlay_src, t) if self.overlay_src else -1
        if k == self.overlay_idx:
            return
        self.overlay_idx = k
        if k < 0:
            self.overlay.hide()
            return
        self.overlay.setText(self.overlay_src[k][2])
        self.place_overlay()
        self.overlay.show()

    def place_overlay(self):
        """Where the picture is inside the black screen, the letters about as big as the burn-in
        makes them (traduire's style: 24 for a height of 288, smaller for a narrow picture)."""
        if not self.project or not hasattr(self, "overlay"):
            return
        W, H = self.screen.width(), self.screen.height()
        vid = self.project.get("video") or {}
        vw, vh = vid.get("width") or 16, vid.get("height") or 9
        scale = min(W / vw, H / vh)
        pw, ph = vw * scale, vh * scale
        px, py = (W - pw) / 2, (H - ph) / 2
        size = ph * 24 / 288
        if pw / ph < 16 / 9 - 0.05:
            size *= pw / (ph * 16 / 9)
        self.overlay.setStyleSheet(f"QLabel#overlay {{ font-size: {max(9, int(size))}px; }}")
        self.overlay.setFixedWidth(max(40, int(pw * 0.92)))
        self.overlay.adjustSize()
        self.overlay.move(int(px + (pw - self.overlay.width()) / 2), int(py + ph - self.overlay.height() - ph * 16 / 288))
        self.overlay.raise_()

    def eventFilter(self, obj, ev):
        if obj is getattr(self, "screen", None) and ev.type() == QtCore.QEvent.Resize and self.overlay.isVisible():
            self.place_overlay()
        return super().eventFilter(obj, ev)

    # the model shortens what reads too fast: traduire.py's proofreading pass on the cues
    def ask_shorten(self):
        if not self.subs_mode or self.thread or self.view not in self.cues:
            return
        cues = self.editor.cues()
        fast, chosen = self.editor.too_fast_rows(), self.editor.selected_rows()
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(_("Shorten what reads too fast…").rstrip("…"))
        dlg.setMinimumWidth(520)
        v = QtWidgets.QVBoxLayout(dlg)
        v.setContentsMargins(18, 16, 18, 14)
        v.setSpacing(10)
        folder = self._toolkit_row(dlg, v)
        lab = QtWidgets.QLabel(_("The model rereads these subtitles and shortens the ones that read too fast, with the proofreading pass of traduire.py."))
        lab.setWordWrap(True)
        v.addWidget(lab)
        scope = QtWidgets.QComboBox()
        scope.addItem(_("The subtitles that read too fast (%1)", len(fast)), "fast")
        scope.addItem(_("The selected subtitles (%1)", len(chosen)), "selected")
        scope.addItem(_("All the subtitles (%1)", len(cues)), "all")
        scope.setCurrentIndex(1 if len(chosen) > 1 else 0)
        v.addWidget(scope)
        g = QtWidgets.QGridLayout()
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(6)
        llm, model, key = self._llm_rows(g, 0, _("Proofreading by"))
        v.addLayout(g)
        error = QtWidgets.QLabel("")
        error.setObjectName("danger")
        error.setWordWrap(True)
        v.addWidget(error)
        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self._btn(_("Cancel"), dlg.reject))
        go = self._btn(_("Shorten"), None, kind="strong")
        buttons.addWidget(go)
        v.addLayout(buttons)

        def accept():
            where = self._toolkit_from(folder, error)
            if not where:
                return
            rows = {"fast": fast, "selected": chosen, "all": list(range(len(cues)))}[scope.currentData()]
            if not rows:
                error.setText(_("Nothing to shorten."))
                return
            self.cfg["anthropic_key"] = key.text().strip()
            if llm.currentData() == "claude" and not self.anthropic_key():
                error.setText(_("Give an Anthropic API key."))
                return
            if llm.currentData() == "claude_code" and not find_claude(quick=True):
                error.setText(_("Claude Code is not installed: « Getting started » on the home page installs it."))
                return
            self.cfg["llm"], self.cfg["ollama_model"] = llm.currentData(), model.text().strip() or LLM_LOCAL_MODEL
            save_config(self.cfg)
            dlg.accept()
            self.start_shorten(where, rows, llm.currentData(), self.cfg["ollama_model"])
        go.clicked.connect(accept)
        dlg.exec_()

    def start_shorten(self, tk, rows, llm, model):
        key, d, cues = self.view, Path(self.project["dir"]), self.editor.cues()
        src = self.src_lang or "en"
        tgt = (self.src_lang if key == "src" else key) or "en"
        scope = set(rows)
        send = sorted({r for k in rows for r in range(k - 2, k + 3) if 0 <= r < len(cues)})
        src_tokens = self.texts["src"]["tokens"]
        segments = []
        for r in send:
            a, b, text = cues[r]
            flat = " ".join(text.split())
            original = words_during(src_tokens, a, b) if key != "src" else flat
            segments.append({"index": r, "start": a, "end": b, "text": original or flat, "text_tgt": flat, "words": [], "lang": src})
        analysis = (read_json(d / f"translation-{key}.json", {}) or {}).get("analysis") if key != "src" else None
        job = {"task": "review", "toolkit": tk, "segments": segments, "source_lang": src, "target_lang": tgt,
               "llm": llm, "ollama_model": model, "ollama_url": OLLAMA_URL, "claude_model": LLM_CLAUDE_MODEL,
               "analysis": analysis or {}, "context": "", "max_cps": MAX_CPS, **claude_job(self.cfg, llm)}
        self.task = {"cancelled": False, "proc": None, "page": True}
        task = self.task

        def work(w):
            if llm == "local" and not ollama_answers(OLLAMA_URL):
                raise RuntimeError(_("Ollama does not answer at %1.", OLLAMA_URL))

            def on_message(msg):
                m = re.search(r"Fen[êe]tre (\d+)/(\d+)", msg.get("line", ""))
                if m:
                    i, n = int(m.group(1)), int(m.group(2))
                    w.progress.emit((i - 1) / max(n, 1), _("Proofreading… %1 of %2", i, n) + " · " + model_label(llm, model))
            py = prepare_toolkit_python(TOOLKIT_PACKAGES["claude"] if llm == "claude" else [], lambda t: w.progress.emit(0.0, t), task)
            result = run_bridge(task, job, d, on_message, python=py, env_extra=claude_env(self.cfg))
            changes = {}
            for s in result["segments"]:
                r, new = int(s["index"]), " ".join((s.get("text_tgt") or "").split())
                if r in scope and new and new != " ".join(cues[r][2].split()):
                    changes[r] = two_lines(new)
            return changes

        def back():
            self.task = None
            self.p_cancel.hide()
            self.enable(True)
            self.page_stack.setCurrentWidget(self.editor if self.subs_mode else self.page)

        def done(changes):
            back()
            if changes and self.subs_mode and self.view == key:
                self.editor.apply_texts(changes)
                self.say(_("Shortened: %1 subtitles", len(changes)))
            else:
                self.say(_("The model changed nothing."))

        def failed(msg):
            back()
            self.say(_("The shortening failed: %1", msg) if msg else _("Cancelled."))
        self.wait(_("Proofreading…"), model_label(llm, model))
        self.p_gauge.setValue(0)
        self.p_cancel.show()
        self.enable(False)
        self.run_in_background(work, done, failed)

    # ---- the selection and the cuts ----
    def choose_tool(self, tool):
        self.page.tool = tool
        self.b_highlight.setChecked(tool == "highlight")
        self.b_erase.setChecked(tool == "erase")

    def set_mode(self, mode, quiet=False):
        self.mode_value = mode
        self.b_keep.setChecked(mode == "keep")
        self.b_cut.setChecked(mode == "cut")
        self.b_silences.setVisible(mode == "cut")
        self.page.set_mode(mode)
        if not quiet:
            self.on_selection()

    def on_selection(self):
        self.update_undo_buttons()
        if not self.project or not self.tokens:
            self.update_summary()
            return
        d = Path(self.project["dir"])
        ranges = self.page.ranges()
        fade = float(self.fade.currentData())
        mode = self.mode_value
        self.cfg["fade"], self.cfg["image_fade"] = fade, self.image_fade.isChecked()
        write_json(d / "selection.json", {"ranges": ranges, "fade": fade, "mode": mode, "view": self.view})
        if mode == "cut" and not clean_ranges(ranges, len(self.tokens)):
            self.cuts = []
        else:
            self.cuts = compute_cuts(d / "audio16k.wav", self.tokens, ranges, fade, self.project["duration"],
                                     inverse=(mode == "cut"), estimated=self.estimated)
        self.stop_preview()
        self.update_summary()

    def update_summary(self):
        self.passages.clear()
        self.b_produce.setEnabled(bool(self.cuts) and self.thread is None)
        self.b_preview.setEnabled(bool(self.cuts) and self.thread is None)
        mode = self.mode_value
        if not self.tokens:
            self.l_big.setText("—")
            self.l_small.setText("")
            self.hint.setText("")
            self.list_stack.setCurrentWidget(self.hint)
            self.b_clear.setEnabled(False)
            return
        ranges = self.page.ranges()
        total = self.project["duration"]
        free = sum(1 for i, t in enumerate(self.tokens) if t[0] is None and not self.page.sel[i])
        self.b_silences.setText(_("Strike the %1 silences", free) if free > 1 else _("Strike the silence"))
        self.b_silences.setEnabled(free > 0)
        self.b_clear.setEnabled(bool(ranges))
        if not ranges:
            self.l_big.setText(_("Nothing struck") if mode == "cut" else _("Nothing highlighted"))
            self.l_small.setText("")
            self.hint.setText((_("Drag over the text to strike what you remove: the edit keeps all the rest.") if mode == "cut"
                               else _("Drag over the text to highlight what you keep.")) + " "
                              + _("A click on a word plays from there. A click on a passage without words marks it. A double click takes the whole sentence. For a long passage, click its first word, then its last one with Shift held."))
            self.list_stack.setCurrentWidget(self.hint)
            return
        self.list_stack.setCurrentWidget(self.passages)
        kept = sum(c["f"] - c["d"] for c in self.cuts)
        n = len(self.cuts)
        if mode != "cut":
            self.l_big.setText(_("Edit of %1", plain(kept)))
            self.l_small.setText((_("%1 passages", n) if n != 1 else _("%1 passage", n)) + " " + _("out of %1", plain(total)))
            for c in self.cuts:
                self._add_passage(c["range"][0], c["range"][1], c["d"], c["f"] - c["d"])
        else:
            self.l_big.setText(_("Edit of %1", plain(kept)) if n else _("Nothing is left"))
            self.l_small.setText((_("%1 cuts", len(ranges)) if len(ranges) != 1 else _("%1 cut", len(ranges))) + " · "
                                 + _("%1 less out of %2", plain(max(0.0, total - kept)), plain(total)))
            for a, b in ranges:
                self._add_passage(a, b, self.tokens[a][1], self.tokens[b][2] - self.tokens[a][1])

    def _add_passage(self, a, b, t, dur):
        words = [self.tokens[i][0] for i in range(a, b + 1) if self.tokens[i][0] is not None][:30]
        text = " ".join(words) or _("Without words")
        item = QtWidgets.QListWidgetItem()
        item.setData(QtCore.Qt.UserRole, (a, b, t))
        item.setData(QtCore.Qt.UserRole + 1, (t, dur, text, False))
        self.passages.addItem(item)

    def drop_passage(self, row):
        item = self.passages.item(row)
        if item:
            a, b, _t = item.data(QtCore.Qt.UserRole)
            self.page.change(a, b, 0)

    def go_passage(self, row):
        item = self.passages.item(row)
        if not item:
            return
        a, b, t = item.data(QtCore.Qt.UserRole)
        if self.page.spans[a]:
            cur = QtGui.QTextCursor(self.page.document())
            cur.setPosition(self.page.spans[a][0])
            self.page.setTextCursor(cur)
            self.page.ensureCursorVisible()
        self.go(t, None)

    # ---- playing ----
    def toggle_play(self):
        if not self.project:
            return
        if self.player.state() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def update_play_button(self):
        self.b_play.setText("❚❚" if self.player.state() == QMediaPlayer.PlayingState else "▶")

    def go(self, t, play):
        if not self.project:
            return
        self.stop_preview()
        self.wanted_seek = True
        self.player.setPosition(int(max(0.0, t) * 1000))
        if play:
            self.player.play()

    def on_media_error(self, _err):
        if self.media_ok:
            self.media_ok = False
            self.say(_("The sound of this file cannot be played here, the text still works and the export too."))

    def on_position(self, ms):
        if not self.slider.isSliderDown():
            self.slider.setValue(int(ms))
        self.time_label.setText(plain(ms / 1000.0) + " / " + plain(self.project["duration"] if self.project else 0))
        self.page.set_current(ms / 1000.0 + 0.05)
        if self.subs_mode:
            self.editor.set_current(ms / 1000.0 + 0.05)
        self.update_overlay(ms / 1000.0 + 0.05)

    def tick(self):
        """The preview of the edit: at the end of a kept piece, jump to the next one."""
        if self.previewing < 0 or self.player.state() != QMediaPlayer.PlayingState:
            return
        t = self.player.position() / 1000.0
        if self.previewing >= len(self.cuts):
            self.stop_preview()
            return
        c = self.cuts[self.previewing]
        if t >= c["f"] - 0.03:
            self.previewing += 1
            if self.previewing < len(self.cuts):
                self.player.setPosition(int(self.cuts[self.previewing]["d"] * 1000))
            else:
                self.player.pause()
                self.stop_preview()

    def toggle_preview(self):
        if self.previewing >= 0:
            self.player.pause()
            self.stop_preview()
            return
        if not self.cuts:
            return
        self.previewing = 0
        self.b_preview.setText(_("■ Stop"))
        self.player.setPosition(int(self.cuts[0]["d"] * 1000))
        self.player.play()

    def stop_preview(self):
        if self.previewing >= 0:
            self.previewing = -1
        if self.project:
            self.b_preview.setText(_("▶ Watch the edit") if self.project["type"] == "video" else _("▶ Listen to the edit"))

    # ---- producing the edit ----
    def show_production(self, state):
        self.settings.setVisible(state == "settings")
        self.following.setVisible(state == "following")
        self.finished.setVisible(state == "finished")
        self.fail.setVisible(state == "failed")

    def produce_or_stop(self):
        if self.task is not None:
            self.task["cancelled"] = True
            if self.worker:
                self.worker.cancelled = True
            proc = self.task.get("proc")
            if proc:
                try:
                    proc.kill()
                except OSError:
                    pass
            return
        if not self.cuts or self.thread or not self.project:
            return
        fmt = self.format.currentData() or "mp4"
        src = Path(self.project["source"])
        out = src.with_name(f"{src.stem}_edit.{fmt}")
        k = 1
        while out.exists() or any(out.with_suffix("." + e).exists() for e in ("txt", "edl")) or glob.glob(glob.escape(str(out.with_suffix(""))) + ".*.srt"):
            k += 1
            out = src.with_name(f"{src.stem}_edit-{k}.{fmt}")
        cuts = [dict(c) for c in self.cuts]
        fade = float(self.fade.currentData())
        image_fade = self.image_fade.isChecked()
        mode = self.mode_value
        project = dict(self.project)
        tokens = list(self.tokens)
        d = Path(project["dir"])
        # the subtitles of the edit: the ones drawn into the picture, the files beside it
        burn = self.subs.currentData() if fmt == "mp4" and project["type"] == "video" else "none"
        captions = burn in self.texts and self.caption_style.currentData() == "captions"
        srt_files = self.srt_files.isChecked()
        keys = sorted(self.texts) if srt_files else ([burn] if burn in self.texts and not captions else [])
        burn_tokens = list(self.texts[burn]["tokens"]) if captions else None
        burn_code = (self.src_lang if burn == "src" else burn) if burn in self.texts else None
        sub_line = None
        if burn_code is not None:
            sub_line = _("In the picture: %1", lang_label(burn_code)) + (", " + _("Instagram-like captions") if captions else "")
        texts = {k: list(self.texts[k]["tokens"]) for k in keys}
        codes = {k: (self.src_lang if k == "src" else k) for k in keys}
        tk = toolkit_dir(self.cfg)
        stored = {k: sorted(self.cues[k]["cues"]) for k in keys if k in self.cues}
        square = fmt == "mp4" and project["type"] == "video" and self.frame.currentData() == "square"
        finish = None
        if self.sound.currentData() == "finish":
            where = self.toolkit_for_sound()
            if not where:
                return
            finish = {"toolkit": where, "channels": (project.get("audio") or {}).get("channels", 2)}
        style = SUBTITLE_STYLE
        if project.get("video"):
            w, h = project["video"].get("width", 0), project["video"].get("height", 0)
            if square and w > 0 and h > 0:
                w = h = min(w, h)
            style = scale_style(SUBTITLE_STYLE, w, h)
        size = (w, h) if project.get("video") else (0, 0)
        self.task = {"cancelled": False, "progress": 0.0, "message": "", "proc": None, "sound": None}
        task = self.task

        def work(w):
            stop = threading.Event()

            def pump():
                while not stop.is_set():
                    w.progress.emit(task["progress"], _("Exporting… %1 %", int(task["progress"] * 100)) + ("  ·  " + task["message"] if task["message"] else ""))
                    stop.wait(0.4)
            threading.Thread(target=pump, daemon=True).start()
            try:
                paths = {}
                if texts:
                    task["message"] = _("Making the subtitles…")
                for key, toks in texts.items():
                    cues = cues_in_edit(stored[key], cuts) if key in stored else make_cues(tokens_in_edit(toks, cuts), codes[key], tk, task, d)
                    path = out.with_name(f"{out.stem}.{codes[key] or 'src'}.srt") if srt_files else d / "burn.srt"
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(srt_text(cues))
                    paths[key] = path
                task["message"] = ""
                if finish:
                    finish["path_first"] = ensure_ffmpeg_tools(lambda t: task.update(message=t), task)
                    finish["python"] = prepare_toolkit_python(TOOLKIT_PACKAGES["sound"], lambda t: task.update(message=t), task)
                    task["message"] = ""
                burn_style = style
                if captions:
                    ass = d / "captions.ass"
                    with open(ass, "w", encoding="utf-8") as f:
                        f.write(captions_ass(tokens_in_edit(burn_tokens, cuts), *size))
                    paths[burn], burn_style = ass, None
                if fmt == "mp4":
                    produce_video(task, project["source"], cuts, fade, image_fade, out,
                                  burn=(paths[burn], burn_style) if burn in paths else None,
                                  tracks=[(codes[k], paths[k]) for k in keys if srt_files], square=square, finish=finish)
                else:
                    produce_audio(task, project["source"], cuts, project["audio"], fmt, out, finish=finish)
            finally:
                stop.set()
            write_logs(out, project, tokens, cuts, mode, fade, image_fade, fmt, square=square, sound=task.get("sound"), subtitles=sub_line)
            return out

        def done(path):
            self.task = None
            self.last_out = str(path)
            size = os.path.getsize(path)
            kept = sum(c["f"] - c["d"] for c in cuts)
            self.fin_detail.setText(f'<span style="color:{C_OK}; font-weight:700">' + _("Edit finished") + "</span> · " + plain(kept) + f" · {size / 1e6:.1f} MB")
            self.fin_path.setText(str(path))
            self.fin_logs.setText(_("Beside it: the log of the cuts (.txt), the edit list (.edl) and the subtitles (.srt).") if srt_files
                                  else _("Beside it: the log of the cuts (.txt) and the edit list (.edl)."))
            summary = sound_summary(task.get("sound"))
            self.fin_sound.setText(_("Sound: %1", "; ".join(summary)) if summary else "")
            self.fin_sound.setVisible(bool(summary))
            self.show_production("finished")
            self.enable(True)

        def failed(msg):
            self.task = None
            if msg:
                self.fail.setText(_("The edit could not be made: %1", msg))
                self.show_production("failed")
                QtCore.QTimer.singleShot(8000, lambda: self.show_production("settings") if self.fail.isVisible() else None)
            else:
                self.show_production("settings")
            self.enable(True)
        self.progress.setValue(0)
        self.f_text.setText(_("Exporting… %1 %", 0))
        self.show_production("following")
        self.b_produce.setEnabled(False)
        self.run_in_background(work, done, failed)

    def closeEvent(self, e):
        if self.task is not None:
            self.task["cancelled"] = True
            proc = self.task.get("proc")
            if proc:
                try:
                    proc.kill()
                except OSError:
                    pass
        if self.worker:
            self.worker.cancelled = True
        self.player.stop()
        super().closeEvent(e)


def main():
    try:
        locale.setlocale(locale.LC_TIME, "")
    except locale.Error:
        pass
    if hasattr(QtCore.Qt, "HighDpiScaleFactorRoundingPolicy"):
        QtGui.QGuiApplication.setHighDpiScaleFactorRoundingPolicy(QtCore.Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)
    app = QtWidgets.QApplication(sys.argv)
    load_bundled_fonts()
    app.setApplicationName("reader's video editor")
    app.setDesktopFileName(APP)
    app.setWindowIcon(_icon())
    qt_tr = QtCore.QTranslator(app)
    qt_dir = QtCore.QLibraryInfo.location(QtCore.QLibraryInfo.TranslationsPath)
    if any(qt_tr.load("qtbase_" + name, qt_dir) for name in (_LANG, {"pt": "pt_BR"}.get(_LANG, _LANG))):
        app.installTranslator(qt_tr)
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    source = next((a for a in args if Path(a).suffix.lower() in EXT_VIDEO | EXT_AUDIO or a.endswith(PROJECT_EXT)), None)
    srt = next((a for a in args if a.lower().endswith(".srt")), None)
    w = Main(source, srt)
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
