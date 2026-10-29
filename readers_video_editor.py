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
VERSION = "1.4.0"


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


def ffmpeg_exe():
    found = shutil.which("ffmpeg") or _bundled_tool("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def ffprobe_exe():
    return shutil.which("ffprobe") or _bundled_tool("ffprobe")


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
    segments, info = model.transcribe(audio.astype(np.float32), language=language or None, word_timestamps=True,
                                      vad_filter=True, beam_size=5)
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
    return words, info.language


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
    return "Claude " + LLM_CLAUDE_MODEL if llm == "claude" else "Ollama " + (model or LLM_LOCAL_MODEL)


def lang_label(code):
    """'fr' → 'Français'; a code the app does not list stays as it is; '' is the original text."""
    if not code:
        return _("Original")
    return next((name for c, name in LANGUAGES if c == code), code.upper())


def toolkit_dir(cfg=None):
    for d in (os.environ.get("TRADUCTION_DIR"), (cfg or {}).get("toolkit_dir"),
              os.path.expanduser("~/code/traduction"), os.path.expanduser("~/code/traduction-toolkit")):
        if d and os.path.isfile(os.path.join(d, "traduire.py")):
            return d
    return None


def toolkit_python():
    """The toolkit's interpreter (the rule of gui.py and monter.py); traduire.py itself needs only
    the standard library, anthropic when Claude is asked for."""
    cands = [os.environ.get("TRADUCTION_PYTHON")] + [os.path.expanduser(f"~/miniconda3/envs/{e}/bin/python") for e in ("interview", "traduction")]
    for c in cands:
        if c and os.path.exists(c):
            return c
    if getattr(sys, "frozen", False):
        return shutil.which("python3") or shutil.which("python")
    return sys.executable


# What runs in the toolkit's Python: traduire.py's passes, in the order of its main(). Its own
# messages go to stderr, the app reads them for its gauge; the answers come as "@@ {json}".
TOOLKIT_BRIDGE = r"""
import json, os, sys, traceback
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

    def make_client(job):
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
        if job.get("llm") != "claude" and job.get("analysis_by_claude"):
            analysis_client = make_client(dict(job, llm="claude"))
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


def run_bridge(task, job, folder, on_message=None):
    """Runs the toolkit on `job` (a dict) in a subprocess and returns its result dict.
    on_message(dict) receives each "@@" message and each printed line ({"line": …})."""
    folder = Path(folder)
    script = folder / "toolkit_bridge.py"
    script.write_text(TOOLKIT_BRIDGE, encoding="utf-8")
    job_file = folder / "toolkit_job.json"
    write_json(job_file, job)
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    proc = subprocess.Popen([toolkit_python(), str(script), str(job_file)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
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
        c["vi"] = k == 0 or c["d"] - cuts[k - 1]["f"] >= IMAGE_FADE_MIN
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


def produce_video(task, source, cuts, fade, image_fade, out, burn=None, tracks=()):
    """One intermediate file per piece (x264 picture + raw sound), then one join: the picture is
    copied as it is, the sound encoded once. With `burn` = (srt, style) the subtitles are drawn
    into the picture at the join (encoded once more, as traduire.py burns them); `tracks` =
    [(language, srt), …] go into the MP4 as subtitle tracks one can switch on."""
    ff = ffmpeg_exe()
    total = sum(c["f"] - c["d"] for c in cuts)
    tmp = Path(tempfile.mkdtemp(prefix="edit_", dir=str(out.parent)))
    share = 0.6 if burn else 0.96
    sub = None
    try:
        done, pieces = 0.0, []
        for k, c in enumerate(cuts):
            dur = c["f"] - c["d"]
            task["message"] = _("Piece %1 of %2", k + 1, len(cuts))
            vf = []
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
        cmd = [ff, "-y", "-f", "concat", "-safe", "0", "-i", str(lst)]
        for _lang, srt in tracks:
            cmd += ["-i", str(srt)]
        cmd += ["-map", "0:v:0", "-map", "0:a:0"]
        for k in range(len(tracks)):
            cmd += ["-map", f"{k + 1}:0"]
        if burn:
            # ffmpeg's filter parser is picky about paths: a copy with a plain name (as traduire.py)
            sub = Path(tempfile.mkdtemp(prefix="subs_")) / "subs.srt"
            shutil.copy2(burn[0], sub)
            cmd += ["-vf", f"subtitles='{filter_path(sub)}':force_style='{burn[1]}'",
                    "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p"]
        else:
            cmd += ["-c:v", "copy"]
        cmd += ["-c:a", "aac", "-b:a", "192k"]
        if tracks:
            cmd += ["-c:s", "mov_text"]
            for k, (lang, _srt) in enumerate(tracks):
                cmd += [f"-metadata:s:s:{k}", "language=" + ISO3.get(lang, "und")]
        cmd += ["-movflags", "+faststart", str(partial)]
        try:
            _run_ffmpeg(cmd, task, str(tmp / "ffmpeg.log"), lambda t: task.update(progress=share + (1.0 - share) * min(t / total, 1.0)))
            os.replace(partial, out)
        finally:
            if partial.exists():
                partial.unlink()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        if sub is not None:
            shutil.rmtree(sub.parent, ignore_errors=True)


def produce_audio(task, source, cuts, audio, fmt, out):
    """The sound is decoded once from start to end and the pieces taken on the fly, to the sample."""
    ff = ffmpeg_exe()
    sr, ch = audio["rate"], audio["channels"]
    codec = {"mp3": ["-c:a", "libmp3lame", "-b:a", "192k"], "m4a": ["-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"],
             "wav": ["-c:a", "pcm_s16le"]}[fmt]
    partial = out.with_name(out.stem + ".partial" + out.suffix)
    log = tempfile.NamedTemporaryFile(prefix="edit_", suffix=".log", delete=False)
    raw = ["-f", "f32le", "-ar", str(sr), "-ac", str(ch)]
    dec = subprocess.Popen([ff, "-nostdin", "-v", "error", "-i", source, "-vn", "-map", "0:a:0", "-acodec", "pcm_f32le"] + raw + ["-"],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, **_RUN_FLAGS)
    enc = subprocess.Popen([ff, "-nostdin", "-y", "-v", "error"] + raw + ["-i", "-"] + codec + [str(partial)],
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
            task["progress"] = 0.97 * min(pos / max(last, 1), 1.0)
        task["message"] = _("Encoding")
        enc.stdin.close()
        if enc.wait() != 0:
            log.flush()
            with open(log.name) as f:
                raise RuntimeError(f.read()[-600:].strip() or "ffmpeg failed")
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


# ------------------------------------------------------------------------------------------
# The log of the cuts and the edit list (CMX 3600)
# ------------------------------------------------------------------------------------------

def hmsm(t):
    ms = int(round(max(0.0, t) * 1000))
    h, r = divmod(ms, 3600000)
    m, r = divmod(r, 60000)
    s, ms = divmod(r, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


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


def log_text(out, project, tokens, cuts, mode, fade, image_fade, fmt):
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


def write_logs(out, project, tokens, cuts, mode, fade, image_fade, fmt):
    image = image_fade and fade > 0
    cuts_edl = cuts if image else [dict(c, vi=False, vo=False) for c in cuts]
    written = []
    for ext, content in (("txt", log_text(out, project, tokens, cuts, mode, fade, image_fade, fmt)),
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
                cur.insertText(hmsm(d)[3:8] + "\t", tf)
                where = _("Start") + " · " if i == 0 else (_("End") + " · " if i == len(self.tokens) - 1 else "")
                start = cur.position()
                cur.insertText(f" {where}{f - d:.1f} s {label_without} ", pause_fmt)
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
                cur.insertText(hmsm(d)[3:8] + "\t", tf)
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
        painter.drawText(QtCore.QRect(r.left(), r.top(), 52, r.height()), QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop, hmsm(t)[3:8])
        small = QtGui.QFont(option.font)
        small.setPointSizeF(max(7.0, option.font.pointSizeF() * 0.85))
        painter.setFont(small)
        painter.setPen(QtGui.QColor(C_MUTED))
        painter.drawText(QtCore.QRect(r.right() - 90, r.top(), 60, r.height()), QtCore.Qt.AlignRight | QtCore.Qt.AlignTop, plain(dur))
        painter.setFont(QtGui.QFont(option.font.family(), option.font.pointSize() + 2))
        painter.drawText(QtCore.QRect(r.right() - 20, r.top() - 2, 20, r.height()), QtCore.Qt.AlignRight | QtCore.Qt.AlignTop, "×")
        painter.setFont(option.font)
        painter.setPen(QtGui.QColor(C_TEXT))
        box = QtCore.QRect(r.left() + 58, r.top(), r.width() - 58 - 96, r.height())
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
    def __init__(self, source=None, srt=None):
        super().__init__()
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
        hc = QtWidgets.QHBoxLayout()
        hc.addStretch(1)
        hc.addWidget(card, 20)
        hc.addStretch(1)
        outer.addLayout(hc)
        outer.addStretch(40)
        home.setWidget(inner)
        self.home = home
        self.views.addWidget(home)

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
        self.l_subs = QtWidgets.QLabel(_("Subtitles"))
        self.l_subs.setObjectName("label")
        g.addWidget(self.l_subs, 3, 0, 1, 2)
        self.subs = QtWidgets.QComboBox()
        self.subs.currentIndexChanged.connect(lambda _i: self.remember_output())
        g.addWidget(self.subs, 4, 0)
        self.srt_files = QtWidgets.QCheckBox(_("Subtitle files beside the edit (.srt)"))
        self.srt_files.setChecked(bool(self.cfg.get("srt_files", False)))
        self.srt_files.toggled.connect(lambda _c: self.remember_output())
        g.addWidget(self.srt_files, 4, 1)
        self.b_produce = self._btn(_("Produce the edit"), self.produce_or_stop, kind="strong", tip="Ctrl+E")
        g.addWidget(self.b_produce, 5, 0, 1, 2)
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
        dv.addWidget(self.fin_detail)
        dv.addWidget(self.fin_path)
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
                  self.b_project, self.subs, self.srt_files, self.lang_box):
            w.setEnabled(loaded)
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
        self.refresh_overlay()

    def remember_output(self):
        if self.subs.currentData():
            self.cfg["burn"] = self.subs.currentData()
        self.cfg["srt_files"] = self.srt_files.isChecked()
        save_config(self.cfg)
        self.refresh_overlay()

    def show_project_name(self):
        name = Path(self.project_file).name if self.project_file else ""
        self.a_detail.setText(self.detail + (" · " + name if name else ""))

    # ---- the translation (traduire.py, through the toolkit's Python) ----
    def _toolkit_row(self, dlg, v):
        """When the toolkit is not found: the message and a field for its folder, in a dialog.
        Returns the field, or None when the toolkit is there."""
        if toolkit_dir(self.cfg):
            return None
        lab = QtWidgets.QLabel(_("The traduction toolkit does the translation (traduire.py). It was not found: give its folder, or install it from %1.", TOOLKIT_URL))
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
        return folder

    def _toolkit_from(self, folder, error):
        """The toolkit folder a dialog settled on, or None after the error is shown."""
        where = toolkit_dir(self.cfg)
        if folder is not None:
            where = folder.text().strip()
            if not os.path.isfile(os.path.join(where, "traduire.py")):
                error.setText(_("traduire.py is not in this folder."))
                return None
            self.cfg["toolkit_dir"] = where
        return where

    def _llm_rows(self, g, row, label):
        """Two fields of a dialog: who does the work, the model on this computer (Ollama) or
        Claude, and which Ollama model. Returns the two widgets."""
        llm = QtWidgets.QComboBox()
        llm.addItem(_("On this computer (Ollama)"), "local")
        llm.addItem(_("Claude (API)") + " · " + LLM_CLAUDE_MODEL, "claude")
        llm.setCurrentIndex(1 if self.cfg.get("llm") == "claude" else 0)
        model = QtWidgets.QLineEdit(self.cfg.get("ollama_model") or LLM_LOCAL_MODEL)
        model.setPlaceholderText(LLM_LOCAL_MODEL)
        llm.currentIndexChanged.connect(lambda i: model.setEnabled(i == 0))
        model.setEnabled(llm.currentIndex() == 0)
        for col, (text, w) in enumerate(((label, llm), (_("Ollama model"), model))):
            lab = QtWidgets.QLabel(text)
            lab.setObjectName("label")
            g.addWidget(lab, row, col)
            g.addWidget(w, row + 1, col)
        return llm, model

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
        llm, model = self._llm_rows(g, 2, _("Translation by"))
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
        analysis.setVisible(llm.currentData() == "local" and bool(os.environ.get("ANTHROPIC_API_KEY")))
        llm.currentIndexChanged.connect(lambda i: analysis.setVisible(i == 0 and bool(os.environ.get("ANTHROPIC_API_KEY"))))
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
               "context": context, "review": review, "analysis_by_claude": analysis_by_claude}
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
            result = run_bridge(task, job, d, on_message)
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
                "output": {"format": self.format.currentData(), "burn": self.subs.currentData() or "none", "srt_files": self.srt_files.isChecked()}}
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
        llm, model = self._llm_rows(g, 0, _("Proofreading by"))
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
               "analysis": analysis or {}, "context": "", "max_cps": MAX_CPS}
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
            result = run_bridge(task, job, d, on_message)
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
        srt_files = self.srt_files.isChecked()
        keys = sorted(self.texts) if srt_files else ([burn] if burn in self.texts else [])
        texts = {k: list(self.texts[k]["tokens"]) for k in keys}
        codes = {k: (self.src_lang if k == "src" else k) for k in keys}
        tk = toolkit_dir(self.cfg)
        stored = {k: sorted(self.cues[k]["cues"]) for k in keys if k in self.cues}
        style = SUBTITLE_STYLE
        if project.get("video"):
            style = scale_style(SUBTITLE_STYLE, project["video"].get("width", 0), project["video"].get("height", 0))
        self.task = {"cancelled": False, "progress": 0.0, "message": "", "proc": None}
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
                if fmt == "mp4":
                    produce_video(task, project["source"], cuts, fade, image_fade, out,
                                  burn=(paths[burn], style) if burn in paths else None,
                                  tracks=[(codes[k], paths[k]) for k in keys if srt_files])
                else:
                    produce_audio(task, project["source"], cuts, project["audio"], fmt, out)
            finally:
                stop.set()
            write_logs(out, project, tokens, cuts, mode, fade, image_fade, fmt)
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
