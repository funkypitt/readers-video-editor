#!/usr/bin/env python3
"""Reader's Video Editor — cut a video or a recording by highlighting its text. The words are
transcribed on this computer (or read from a subtitle file), shown on a page; what you highlight
is kept (or cut), the cuts land in the quiet between two words, each piece gets its fades, and
ffmpeg writes the new file with a log of the cuts and an edit list. One file, PyQt5 + numpy +
soundfile; faster-whisper for the transcription. MIT licence."""

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
VERSION = "1.1.0"


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
FADES = [0.0, 0.3, 0.5, 1.0, 2.0, 3.0]
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

def whisper_available():
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:
        return False


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
            if text:
                words.append([text, float(w.start), float(w.end), k])
    return words, info.language


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


def produce_video(task, source, cuts, fade, image_fade, out):
    """One intermediate file per piece (x264 picture + raw sound), then one join: the picture is
    copied as it is, the sound encoded once."""
    ff = ffmpeg_exe()
    total = sum(c["f"] - c["d"] for c in cuts)
    tmp = Path(tempfile.mkdtemp(prefix="edit_", dir=str(out.parent)))
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
                task["progress"] = 0.96 * (base + min(t, dur)) / total

            _run_ffmpeg(cmd, task, str(tmp / "ffmpeg.log"), advance)
            pieces.append(piece)
            done += dur
        task["message"] = _("Joining")
        lst = tmp / "list.txt"
        with open(lst, "w", encoding="utf-8") as f:
            for p in pieces:
                f.write("file '" + str(p).replace("'", "'\\''") + "'\n")
        partial = out.with_name(out.stem + ".partial" + out.suffix)
        cmd = [ff, "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
               "-movflags", "+faststart", str(partial)]
        try:
            _run_ffmpeg(cmd, task, str(tmp / "ffmpeg.log"), lambda t: task.update(progress=0.96 + 0.04 * min(t / total, 1.0)))
            os.replace(partial, out)
        finally:
            if partial.exists():
                partial.unlink()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


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
    cfg.setdefault("dark", True)
    cfg.setdefault("font_size", 11)
    cfg.setdefault("model", MODEL_DEFAULT)
    cfg.setdefault("language", "")
    cfg.setdefault("fade", FADE_DEFAULT)
    cfg.setdefault("image_fade", True)
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
    return n


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


HIGHLIGHT = "#ffe84a"        # the highlighter
STRIKE = "#ff5f8e"           # what is struck in the cut mode


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
        cur = QtGui.QTextCursor(doc)
        fg = self.palette().color(QtGui.QPalette.Text)
        dim = QtGui.QColor(fg)
        dim.setAlphaF(0.5)
        time_fmt = QtGui.QTextCharFormat()
        time_fmt.setForeground(dim)
        time_fmt.setFontPointSize(max(7.0, self.main.font_size - 2))
        word_fmt = QtGui.QTextCharFormat()
        pause_fmt = QtGui.QTextCharFormat()
        pause_fmt.setForeground(dim)
        pause_fmt.setFontItalic(True)
        block_fmt = QtGui.QTextBlockFormat()
        block_fmt.setBottomMargin(self.main.font_size * 1.2)
        block_fmt.setLineHeight(150, QtGui.QTextBlockFormat.ProportionalHeight)
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
                cur.insertText(hmsm(d)[3:8] + "  ", time_fmt)
                where = _("Start") + " · " if i == 0 else (_("End") + " · " if i == len(self.tokens) - 1 else "")
                start = cur.position()
                cur.insertText(f"{where}{f - d:.1f} s {label_without}", pause_fmt)
                self.spans[i] = (start, cur.position())
                continue
            gap = d - prev_end
            new_sentence = s != prev_sentence
            if not open_block or gap >= 2.0 or (new_sentence and gap >= 0.9) or (new_sentence and chars >= 900 and gap >= 0.25):
                if not first:
                    cur.insertBlock(block_fmt)
                first = False
                cur.insertText(hmsm(d)[3:8] + "  ", time_fmt)
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
        for i in range(a, b + 1):
            span = self.spans[i]
            if not span:
                continue
            fmt = QtGui.QTextCharFormat()
            fg = self.palette().color(QtGui.QPalette.Text)
            if self.tokens[i][0] is None:
                dim = QtGui.QColor(fg)
                dim.setAlphaF(0.5)
                fmt.setForeground(dim)
                fmt.setFontItalic(True)
            selected = self.sel[i] == 1
            in_preview = pa <= i <= pb
            if in_preview:
                col = QtGui.QColor(STRIKE if (self.mode == "cut") else HIGHLIGHT)
                col.setAlphaF(0.45 if not self.erase_gesture else 0.15)
                fmt.setBackground(col)
                if self.erase_gesture:
                    fmt.setBackground(QtGui.QColor(rgba("#808080", 0.3)))
            elif selected:
                if self.mode == "cut":
                    fmt.setBackground(QtGui.QColor(STRIKE))
                    fmt.setForeground(QtGui.QColor("#000000"))
                    fmt.setFontStrikeOut(True)
                else:
                    fmt.setBackground(QtGui.QColor(HIGHLIGHT))
                    fmt.setForeground(QtGui.QColor("#000000"))
            if i == self.current:
                fmt.setFontUnderline(True)
                fmt.setFontWeight(QtGui.QFont.Bold)
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

    def mousePressEvent(self, e):
        if e.button() != QtCore.Qt.LeftButton or not self.tokens:
            return
        i = self.token_at(e.pos())
        if i < 0:
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

class Main(QtWidgets.QMainWindow):
    def __init__(self, source=None, srt=None):
        super().__init__()
        self.cfg = load_config()
        self.font_size = int(self.cfg.get("font_size", 11))
        self.dark = bool(self.cfg.get("dark", True))
        self.project = None         # {source, type, duration, video, audio, dir}
        self.tokens = []
        self.cuts = []
        self.origin = ""
        self.estimated = False
        self.thread = None
        self.worker = None
        self.task = None
        self.previewing = -1
        self.wanted_seek = False
        self.media_ok = True
        self.setWindowTitle("Reader's Video Editor")
        self.setAcceptDrops(True)
        self.resize(1180, 760)
        self._build()
        self.apply_style()
        self.update_summary()
        if source:
            QtCore.QTimer.singleShot(0, lambda: self.open_source(source, srt))

    # ---- widgets ----
    def _build(self):
        root = QtWidgets.QWidget()
        self.setCentralWidget(root)
        outer = QtWidgets.QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        top = QtWidgets.QHBoxLayout()
        top.setContentsMargins(14, 10, 14, 10)
        top.setSpacing(10)
        self.b_open = QtWidgets.QPushButton(_("open…"))
        self.b_open.clicked.connect(self.ask_open)
        self.b_url = QtWidgets.QPushButton(_("address…"))
        self.b_url.clicked.connect(self.ask_url)
        self.b_srt = QtWidgets.QPushButton(_("subtitles…"))
        self.b_srt.clicked.connect(self.ask_srt)
        self.lang = QtWidgets.QComboBox()
        for code, name in LANGUAGES:
            self.lang.addItem(name, code)
        self.lang.setCurrentIndex(max(0, [c for c, _n in LANGUAGES].index(self.cfg.get("language", "")) if self.cfg.get("language", "") in [c for c, _n in LANGUAGES] else 0))
        self.model = QtWidgets.QComboBox()
        self.model.addItems(MODELS)
        self.model.setCurrentText(self.cfg.get("model", MODEL_DEFAULT))
        self.b_transcribe = QtWidgets.QPushButton(_("transcribe"))
        self.b_transcribe.clicked.connect(self.transcribe_or_stop)
        self.b_read = QtWidgets.QPushButton(_("read"))
        self.b_read.setCheckable(True)
        self.b_read.setAutoDefault(False)
        self.b_read.clicked.connect(lambda c: self.set_reading(c))
        self.b_text = QtWidgets.QPushButton(_("save the text…"))
        self.b_text.setAutoDefault(False)
        self.b_text.clicked.connect(self.save_text)
        self.title = QtWidgets.QLabel("")
        self.title.setObjectName("dim")
        self.title.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        for w in (self.b_open, self.b_url, self.b_srt, self.b_transcribe):
            w.setAutoDefault(False)
        top.addWidget(self.b_open)
        top.addWidget(self.b_url)
        top.addWidget(self.b_srt)
        top.addWidget(QtWidgets.QLabel(_("language")))
        top.addWidget(self.lang)
        top.addWidget(QtWidgets.QLabel(_("model")))
        top.addWidget(self.model)
        top.addWidget(self.b_transcribe)
        top.addWidget(self.b_read)
        top.addWidget(self.b_text)
        top.addWidget(self.title, 1)
        outer.addLayout(top)

        split = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        outer.addWidget(split, 1)

        # left: the picture, the controls, the settings, the summary
        left = QtWidgets.QWidget()
        lv = QtWidgets.QVBoxLayout(left)
        lv.setContentsMargins(14, 0, 8, 10)
        lv.setSpacing(8)
        self.video = QVideoWidget()
        self.video.setMinimumHeight(160)
        self.video.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.player = QMediaPlayer(self, QMediaPlayer.VideoSurface)
        self.player.setVideoOutput(self.video)
        self.player.setNotifyInterval(50)
        self.player.positionChanged.connect(self.on_position)
        self.player.stateChanged.connect(lambda _s: self.update_play_button())
        self.player.error.connect(self.on_media_error)
        self.player.durationChanged.connect(lambda d: self.slider.setMaximum(max(0, int(d))))
        self.drop_hint = QtWidgets.QLabel(_("Drop a video, a recording or a link here, or press Ctrl+O / Ctrl+L."))
        self.drop_hint.setAlignment(QtCore.Qt.AlignCenter)
        self.drop_hint.setWordWrap(True)
        self.drop_hint.setObjectName("dim")
        stack = QtWidgets.QStackedLayout()
        stack.setStackingMode(QtWidgets.QStackedLayout.StackOne)
        self.stack_host = QtWidgets.QWidget()
        self.stack_host.setLayout(stack)
        stack.addWidget(self.drop_hint)
        stack.addWidget(self.video)
        self.stack = stack
        lv.addWidget(self.stack_host, 1)

        self.controls = QtWidgets.QWidget()
        ctl = QtWidgets.QHBoxLayout(self.controls)
        ctl.setContentsMargins(0, 0, 0, 0)
        self.b_back = QtWidgets.QPushButton("−5")
        self.b_back.setObjectName("glyph")
        self.b_back.setAutoDefault(False)
        self.b_back.clicked.connect(lambda: self.go(self.player.position() / 1000.0 - 5, None))
        self.b_fwd = QtWidgets.QPushButton("+10")
        self.b_fwd.setObjectName("glyph")
        self.b_fwd.setAutoDefault(False)
        self.b_fwd.clicked.connect(lambda: self.go(self.player.position() / 1000.0 + 10, None))
        self.speed = QtWidgets.QComboBox()
        for r in (0.8, 1.0, 1.25, 1.5, 2.0):
            self.speed.addItem(f"{r:g}×", r)
        self.speed.setCurrentIndex(1)
        self.speed.currentIndexChanged.connect(lambda _i: self.player.setPlaybackRate(float(self.speed.currentData())))
        self.b_play = QtWidgets.QPushButton("▶")
        self.b_play.setObjectName("glyph")
        self.b_play.setAutoDefault(False)
        self.b_play.clicked.connect(self.toggle_play)
        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider.sliderMoved.connect(lambda v: self.go(v / 1000.0, None))
        self.time_label = QtWidgets.QLabel("0:00 / 0:00")
        self.time_label.setObjectName("mono")
        ctl.addWidget(self.b_back)
        ctl.addWidget(self.b_play)
        ctl.addWidget(self.b_fwd)
        ctl.addWidget(self.slider, 1)
        ctl.addWidget(self.time_label)
        ctl.addWidget(self.speed)
        lv.addWidget(self.controls)
        self.left = left

        tools = QtWidgets.QHBoxLayout()
        self.b_highlight = QtWidgets.QPushButton(_("highlight"))
        self.b_erase = QtWidgets.QPushButton(_("erase"))
        for b, tool in ((self.b_highlight, "highlight"), (self.b_erase, "erase")):
            b.setCheckable(True)
            b.setAutoDefault(False)
            b.clicked.connect(lambda _c, t=tool: self.choose_tool(t))
        self.b_highlight.setChecked(True)
        self.mode = QtWidgets.QComboBox()
        self.mode.addItem(_("I highlight what I keep"), "keep")
        self.mode.addItem(_("I highlight what I cut"), "cut")
        self.mode.currentIndexChanged.connect(self.on_mode)
        tools.addWidget(self.b_highlight)
        tools.addWidget(self.b_erase)
        tools.addWidget(self.mode, 1)
        lv.addLayout(tools)

        opts = QtWidgets.QHBoxLayout()
        opts.addWidget(QtWidgets.QLabel(_("fade")))
        self.fade = QtWidgets.QComboBox()
        for f in FADES:
            self.fade.addItem(_("none") if f == 0 else f"{f:g} " + _("s"), f)
        idx = [i for i in range(self.fade.count()) if abs(self.fade.itemData(i) - float(self.cfg.get("fade", FADE_DEFAULT))) < 1e-6]
        self.fade.setCurrentIndex(idx[0] if idx else FADES.index(FADE_DEFAULT))
        self.fade.currentIndexChanged.connect(lambda _i: self.on_selection())
        self.image_fade = QtWidgets.QCheckBox(_("fade the picture to black"))
        self.image_fade.setChecked(bool(self.cfg.get("image_fade", True)))
        self.format = QtWidgets.QComboBox()
        opts.addWidget(self.fade)
        opts.addWidget(self.image_fade)
        opts.addStretch(1)
        opts.addWidget(self.format)
        lv.addLayout(opts)

        self.summary = QtWidgets.QLabel("")
        self.summary.setWordWrap(True)
        self.summary.setObjectName("summary")
        lv.addWidget(self.summary)
        self.passages = QtWidgets.QListWidget()
        self.passages.setObjectName("passages")
        self.passages.itemClicked.connect(self.on_passage)
        self.passages.setMaximumHeight(170)
        lv.addWidget(self.passages)

        act = QtWidgets.QHBoxLayout()
        self.b_preview = QtWidgets.QPushButton(_("preview the edit"))
        self.b_preview.setAutoDefault(False)
        self.b_preview.clicked.connect(self.toggle_preview)
        self.b_export = QtWidgets.QPushButton(_("export…"))
        self.b_export.setAutoDefault(False)
        self.b_export.clicked.connect(self.export_or_stop)
        act.addWidget(self.b_preview)
        act.addStretch(1)
        act.addWidget(self.b_export)
        lv.addLayout(act)
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        self.progress.setMaximumHeight(6)
        self.progress.hide()
        lv.addWidget(self.progress)
        self.status = QtWidgets.QLabel("")
        self.status.setWordWrap(True)
        self.status.setObjectName("dim")
        lv.addWidget(self.status)
        split.addWidget(left)

        # right: the page
        self.page = Page(self)
        self.page.changed.connect(self.on_selection)
        self.page.seek.connect(lambda t: self.go(t, True))
        right = QtWidgets.QWidget()
        rv = QtWidgets.QVBoxLayout(right)
        rv.setContentsMargins(8, 0, 14, 10)
        rv.addWidget(self.page, 1)
        self.rv = rv
        self.reading = False
        self.help = QtWidgets.QLabel(_("Shortcuts: Space play/pause · ← → 5 s · S highlight · G erase · Ctrl+Z undo · Ctrl+Y redo · Ctrl+T ink · Ctrl+= Ctrl+- text size") + " · Ctrl+R " + _("read") + " · Ctrl+S " + _("save the text…") + " · " + _("Ctrl+L address"))
        self.help.setWordWrap(True)
        self.help.setObjectName("dim")
        rv.addWidget(self.help)
        split.addWidget(right)
        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 3)
        split.setSizes([460, 700])

        # shortcuts
        def sc(keys, fn):
            s = QtWidgets.QShortcut(QtGui.QKeySequence(keys), self)
            s.setContext(QtCore.Qt.ApplicationShortcut)
            s.activated.connect(fn)
        sc("Ctrl+O", self.ask_open)
        sc("Ctrl+L", self.ask_url)
        sc("Ctrl+Z", self.page.undo)
        sc("Ctrl+Y", self.page.redo)
        sc("Ctrl+Shift+Z", self.page.redo)
        sc("Ctrl+T", self.toggle_ink)
        sc("Ctrl+=", lambda: self.resize_text(1))
        sc("Ctrl++", lambda: self.resize_text(1))
        sc("Ctrl+-", lambda: self.resize_text(-1))
        sc("Space", self.toggle_play)
        sc("Left", lambda: self.go(self.player.position() / 1000.0 - 5, None))
        sc("Right", lambda: self.go(self.player.position() / 1000.0 + 5, None))
        sc("S", lambda: self.choose_tool("highlight"))
        sc("G", lambda: self.choose_tool("erase"))
        sc("Ctrl+E", self.export_or_stop)
        sc("Ctrl+R", lambda: self.b_read.click())
        sc("Ctrl+S", self.save_text)
        sc("Ctrl+Shift+C", self.copy_text)
        self.position_timer = QtCore.QTimer(self)
        self.position_timer.timeout.connect(self.tick)
        self.position_timer.start(80)
        self.update_play_button()
        self.enable(False)

    def apply_style(self):
        bg, fg = ("#000000", "#ffffff") if self.dark else ("#ffffff", "#000000")
        dim, rule = rgba(fg, 0.55), rgba(fg, 0.25)
        s = self.font_size
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{ background: {bg}; color: {fg}; font-family: "{SANS_FAMILY}"; font-size: {s}pt; font-weight: 300; }}
            QLabel#dim {{ color: {dim}; }}
            QLabel#mono {{ font-family: monospace; }}
            QLabel#summary {{ font-size: {s + 2}pt; padding: 4px 0; }}
            QTextEdit {{ background: {bg}; color: {fg}; border: none; font-family: "{SANS_FAMILY}"; font-size: {s + (5 if getattr(self, "reading", False) else 3)}pt; padding: 6px; }}
            QListWidget#passages {{ background: {bg}; border: 1px solid {rule}; outline: none; }}
            QListWidget#passages::item {{ padding: 4px 6px; }} QListWidget#passages::item:selected {{ background: {fg}; color: {bg}; }}
            QScrollBar:vertical {{ background: {bg}; width: 8px; }} QScrollBar::handle:vertical {{ background: {rule}; min-height: 24px; }}
            QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }} QScrollBar::add-page, QScrollBar::sub-page {{ background: {bg}; }}
            QComboBox {{ background: {bg}; color: {fg}; border: 1px solid {rule}; padding: 5px 8px; }}
            QComboBox QAbstractItemView {{ background: {bg}; color: {fg}; selection-background-color: {fg}; selection-color: {bg}; }}
            QPushButton {{ background: {bg}; color: {fg}; border: 1px solid {fg}; padding: 6px 16px; }}
            QPushButton:checked {{ background: {fg}; color: {bg}; }}
            QPushButton:disabled {{ color: {dim}; border-color: {rule}; }}
            QPushButton#glyph {{ min-width: 36px; padding: 6px 10px; }}
            QCheckBox {{ spacing: 6px; }} QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid {fg}; }}
            QCheckBox::indicator:checked {{ background: {fg}; }}
            QSlider::groove:horizontal {{ height: 4px; background: {rule}; }} QSlider::handle:horizontal {{ width: 12px; margin: -6px 0; background: {fg}; }}
            QSlider::sub-page:horizontal {{ background: {fg}; }}
            QProgressBar {{ border: none; background: {rule}; }} QProgressBar::chunk {{ background: {fg}; }}
            QSplitter::handle {{ background: {rule}; width: 1px; }}
            QToolTip {{ background: {bg}; color: {fg}; border: 1px solid {rule}; }}
        """)
        if self.tokens:
            self.page.rebuild()

    def set_reading(self, on):
        """Reading: the page alone across the window, a measure of about 70 characters, the
        picture hidden and the player's controls under the text. The highlighting stays."""
        self.reading = bool(on)
        self.b_read.setChecked(self.reading)
        self.b_read.setText(_("edit") if self.reading else _("read"))
        if self.reading:
            self.left.hide()
            self.rv.insertWidget(1, self.controls)
        else:
            self.rv.removeWidget(self.controls)
            self.left.layout().insertWidget(1, self.controls)
            self.left.show()
        self.apply_style()
        self.fit_measure()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.fit_measure()

    def fit_measure(self):
        if not self.reading:
            self.page.setViewportMargins(0, 0, 0, 0)
            return
        chars = self.page.fontMetrics().averageCharWidth() * 72
        margin = max(24, (self.page.width() - chars) // 2)
        self.page.setViewportMargins(margin, 12, margin, 12)

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

    def toggle_ink(self):
        self.dark = not self.dark
        self.cfg["dark"] = self.dark
        save_config(self.cfg)
        self.apply_style()

    def resize_text(self, d):
        self.font_size = max(7, min(24, self.font_size + d))
        self.cfg["font_size"] = self.font_size
        save_config(self.cfg)
        self.apply_style()

    def enable(self, loaded):
        for w in (self.b_highlight, self.b_erase, self.mode, self.fade, self.image_fade, self.format, self.b_preview):
            w.setEnabled(loaded)
        self.b_export.setEnabled(loaded and bool(self.cuts))
        self.b_text.setEnabled(loaded)
        self.b_read.setEnabled(loaded)
        self.b_srt.setEnabled(self.project is not None)
        self.b_transcribe.setEnabled(self.project is not None)

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
        if media:
            self.open_source(media, srt)
        elif srt and self.project:
            self.load_srt(srt)
        elif link:
            self.open_url(link)

    def ask_url(self):
        if self.thread:
            if self.task is not None and self.task.get("download"):
                self.export_or_stop()       # the same stop: the task is cancelled, its process killed
            return
        clip = QtWidgets.QApplication.clipboard().text().strip()
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(_("Open an address"))
        v = QtWidgets.QVBoxLayout(dlg)
        v.setContentsMargins(18, 16, 18, 14)
        v.setSpacing(10)
        hint = QtWidgets.QLabel(_("The address of a video (YouTube, X…). It is fetched here, with its subtitles when the site has them."))
        hint.setWordWrap(True)
        v.addWidget(hint)
        field = QtWidgets.QLineEdit(clip if is_url(clip) else "")
        field.setMinimumWidth(field.fontMetrics().averageCharWidth() * 64)
        field.selectAll()
        v.addWidget(field)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        v.addWidget(buttons)
        if dlg.exec_() == QtWidgets.QDialog.Accepted and is_url(field.text()):
            self.open_url(field.text().strip())

    def open_url(self, url):
        if self.thread or not is_url(url):
            return
        if not ffmpeg_exe():
            self.say(_("ffmpeg was not found. Install it (ffmpeg.org) and start again."))
            return
        folder = downloads_dir()
        language = self.lang.currentData() or ""
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
            self.progress.hide()
            self.b_url.setText(_("address…"))
            media, srt = result
            self.open_source(media, srt)
            self.say(_("Downloaded: %1", media))

        def failed(msg):
            self.task = None
            self.progress.hide()
            self.b_url.setText(_("address…"))
            self.say(msg or _("Cancelled."))
        self.b_url.setText(_("stop"))
        self.say(_("Downloading…"))
        self.run_in_background(work, done, failed)

    def ask_open(self):
        start = self.cfg.get("last_dir") or os.path.expanduser("~")
        exts = " ".join("*" + e for e in sorted(EXT_VIDEO | EXT_AUDIO))
        path, _f = QtWidgets.QFileDialog.getOpenFileName(self, _("Open a video or a recording"), start, _("Video and audio files") + f" ({exts})")
        if path:
            self.open_source(path, None)

    def ask_srt(self):
        if not self.project:
            return
        start = str(Path(self.project["source"]).parent)
        path, _f = QtWidgets.QFileDialog.getOpenFileName(self, _("Open the subtitles of this file"), start, _("Subtitles (*.srt)"))
        if path:
            self.load_srt(path)

    def open_source(self, path, srt):
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
        self.title.setText(Path(path).name + "  ·  " + plain(info["duration"]))
        self.tokens, self.cuts = [], []
        self.page.set_tokens([], [])
        self.format.clear()
        if info["type"] == "video":
            self.format.addItem("MP4", "mp4")
            self.stack.setCurrentWidget(self.video)
        else:
            self.stack.setCurrentWidget(self.drop_hint)
            self.drop_hint.setText(Path(path).name)
        for fmt in ("mp3", "m4a", "wav"):
            self.format.addItem(fmt.upper(), fmt)
        self.media_ok = True
        self.player.setMedia(QMediaContent(QtCore.QUrl.fromLocalFile(os.path.abspath(path))))
        self.slider.setMaximum(int(info["duration"] * 1000))
        self.enable(False)
        self.b_srt.setEnabled(True)
        self.b_transcribe.setEnabled(True)
        # a text already made for this file, or subtitles beside it
        saved = read_json(d / "transcription.json")
        beside = Path(path).with_suffix(".srt")
        if srt:
            self.load_srt(srt)
        elif saved and saved.get("tokens"):
            self.show_tokens(saved["tokens"], saved.get("origin", "transcription"), bool(saved.get("estimated")))
            self.say(_("Text ready: %1 words", sum(1 for t in self.tokens if t[0] is not None)))
        elif beside.exists():
            self.load_srt(str(beside))
        else:
            self.say(_("Drop a video, a recording or a link here, or press Ctrl+O / Ctrl+L.") if False else "")
            self.start_transcription()

    def say(self, text):
        self.status.setText(text)

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
        self.progress.show()
        self.progress.setValue(int(fraction * 1000))
        if text:
            self.say(text)

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
            w.progress.emit(0.6, _("Reading the file…"))
            return tokens_from_srt(cues, wav, duration)

        def done(tokens):
            self.progress.hide()
            write_json(d / "transcription.json", {"tokens": tokens, "origin": "subtitles", "estimated": True, "language": ""})
            self.show_tokens(tokens, "subtitles", True)
            self.say(_("Text read from the subtitles: %1 words", sum(1 for t in tokens if t[0] is not None)))

        def failed(msg):
            self.progress.hide()
            self.say(msg or _("Cancelled."))
        self.say(_("Reading the file…"))
        self.run_in_background(work, done, failed)

    def transcribe_or_stop(self):
        if self.thread and self.worker and self.task is None:
            self.worker.cancelled = True
            return
        self.start_transcription()

    def start_transcription(self):
        if self.thread or not self.project:
            return
        if not whisper_available():
            self.say(_("The transcription needs faster-whisper: pip install faster-whisper — or open a subtitle file."))
            return
        d = Path(self.project["dir"])
        wav = d / "audio16k.wav"
        duration = self.project["duration"]
        src = self.project["source"]
        language = self.lang.currentData() or ""
        model_size = self.model.currentText()
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
            self.progress.hide()
            write_json(d / "transcription.json", {"tokens": tokens, "origin": "transcription", "estimated": False, "language": lang})
            self.show_tokens(tokens, "transcription", False)
            self.say(_("Text ready: %1 words", sum(1 for t in tokens if t[0] is not None)))
            self.b_transcribe.setText(_("transcribe"))

        def failed(msg):
            self.progress.hide()
            self.say(msg or _("Cancelled."))
            self.b_transcribe.setText(_("transcribe"))
        self.b_transcribe.setText(_("stop"))
        self.run_in_background(work, done, failed)

    def show_tokens(self, tokens, origin, estimated):
        self.tokens, self.origin, self.estimated = tokens, origin, estimated
        d = Path(self.project["dir"])
        sel = read_json(d / "selection.json", {}) or {}
        if sel.get("times") and "ranges" not in sel:
            sel["ranges"] = ranges_from_times(tokens, sel.pop("times"))
            write_json(d / "selection.json", sel)
        mode = sel.get("mode", "keep")
        self.mode.setCurrentIndex(1 if mode == "cut" else 0)
        self.page.mode = mode
        self.page.set_tokens(tokens, sel.get("ranges", []), origin)
        self.enable(True)
        self.on_selection()

    # ---- the selection and the cuts ----
    def choose_tool(self, tool):
        self.page.tool = tool
        self.b_highlight.setChecked(tool == "highlight")
        self.b_erase.setChecked(tool == "erase")

    def on_mode(self, _i):
        self.page.set_mode(self.mode.currentData())
        self.on_selection()

    def on_selection(self):
        if not self.project or not self.tokens:
            self.update_summary()
            return
        d = Path(self.project["dir"])
        ranges = self.page.ranges()
        fade = float(self.fade.currentData())
        mode = self.mode.currentData()
        self.cfg["fade"], self.cfg["image_fade"] = fade, self.image_fade.isChecked()
        write_json(d / "selection.json", {"ranges": ranges, "fade": fade, "mode": mode})
        if mode == "cut" and not clean_ranges(ranges, len(self.tokens)):
            self.cuts = []
        else:
            self.cuts = compute_cuts(d / "audio16k.wav", self.tokens, ranges, fade, self.project["duration"],
                                     inverse=(mode == "cut"), estimated=self.estimated)
        self.stop_preview()
        self.update_summary()

    def update_summary(self):
        self.passages.clear()
        self.b_export.setEnabled(bool(self.cuts) and self.thread is None)
        if not self.tokens:
            self.summary.setText("")
            return
        mode = self.mode.currentData()
        ranges = self.page.ranges()
        total = self.project["duration"]
        if not ranges:
            self.summary.setText(_("Nothing struck") if mode == "cut" else _("Nothing highlighted"))
            self.say((_("Drag over the text to strike what you remove: the edit keeps all the rest.") if mode == "cut"
                      else _("Drag over the text to highlight what you keep.")) + " "
                     + _("A click on a word plays from there. A click on a passage without words marks it. A double click takes the whole sentence. For a long passage, click its first word, then its last one with Shift held."))
            return
        kept = sum(c["f"] - c["d"] for c in self.cuts)
        n = len(self.cuts)
        if mode != "cut":
            self.summary.setText(_("Edit of %1", plain(kept)) + "  ·  " + (_("%1 passages", n) if n != 1 else _("%1 passage", n)) + " " + _("out of %1", plain(total)))
            for c in self.cuts:
                self._add_passage(c["range"][0], c["range"][1], c["d"], c["f"] - c["d"], _("remove"))
        else:
            self.summary.setText((_("Edit of %1", plain(kept)) if n else _("Nothing is left")) + "  ·  "
                                 + (_("%1 cuts", len(ranges)) if len(ranges) != 1 else _("%1 cut", len(ranges))) + " · "
                                 + _("%1 less out of %2", plain(max(0.0, total - kept)), plain(total)))
            for a, b in ranges:
                self._add_passage(a, b, self.tokens[a][1], self.tokens[b][2] - self.tokens[a][1], _("keep"))
        self.say("")

    def _add_passage(self, a, b, t, dur, action):
        words = [self.tokens[i][0] for i in range(a, b + 1) if self.tokens[i][0] is not None][:14]
        text = " ".join(words) or _("Without words")
        item = QtWidgets.QListWidgetItem(f"{hmsm(t)[3:8]}  {plain(dur):>5}   {text}")
        item.setData(QtCore.Qt.UserRole, (a, b, t))
        item.setToolTip(action)
        self.passages.addItem(item)

    def on_passage(self, item):
        a, b, t = item.data(QtCore.Qt.UserRole)
        if QtWidgets.QApplication.keyboardModifiers() & QtCore.Qt.ControlModifier:
            self.page.change(a, b, 0)
            return
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
        self.b_preview.setText(_("stop the preview"))
        self.player.setPosition(int(self.cuts[0]["d"] * 1000))
        self.player.play()

    def stop_preview(self):
        if self.previewing >= 0:
            self.previewing = -1
        self.b_preview.setText(_("preview the edit"))

    # ---- exporting ----
    def export_or_stop(self):
        if self.task is not None:
            self.task["cancelled"] = True
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
        suggested = src.with_name(f"{src.stem}_edit.{fmt}")
        k = 1
        while suggested.exists() or any(suggested.with_suffix("." + e).exists() for e in ("txt", "edl")):
            k += 1
            suggested = src.with_name(f"{src.stem}_edit-{k}.{fmt}")
        out, _f = QtWidgets.QFileDialog.getSaveFileName(self, _("Export the edit"), str(suggested), f"{fmt.upper()} (*.{fmt})")
        if not out:
            return
        out = Path(out)
        if out.suffix.lower() != "." + fmt:
            out = out.with_suffix("." + fmt)
        cuts = [dict(c) for c in self.cuts]
        fade = float(self.fade.currentData())
        image_fade = self.image_fade.isChecked()
        mode = self.mode.currentData()
        project = dict(self.project)
        tokens = list(self.tokens)
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
                if fmt == "mp4":
                    produce_video(task, project["source"], cuts, fade, image_fade, out)
                else:
                    produce_audio(task, project["source"], cuts, project["audio"], fmt, out)
            finally:
                stop.set()
            write_logs(out, project, tokens, cuts, mode, fade, image_fade, fmt)
            return out

        def done(path):
            self.task = None
            self.progress.hide()
            self.b_export.setText(_("export…"))
            size = os.path.getsize(path)
            self.say(_("Done: %1 (%2). Beside it, the log of the cuts (.txt) and the edit list (.edl).", path, f"{size / 1e6:.1f} MB"))
            self.enable(True)

        def failed(msg):
            self.task = None
            self.progress.hide()
            self.b_export.setText(_("export…"))
            self.say(_("Cancelled.") if not msg else _("The edit could not be made: %1", msg))
            self.enable(True)
        self.b_export.setText(_("stop"))
        self.run_in_background(work, done, failed)

    def closeEvent(self, e):
        if self.task is not None:
            self.task["cancelled"] = True
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
    source = next((a for a in args if Path(a).suffix.lower() in EXT_VIDEO | EXT_AUDIO), None)
    srt = next((a for a in args if a.lower().endswith(".srt")), None)
    w = Main(source, srt)
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
