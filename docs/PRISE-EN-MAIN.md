# Prise en main de Reader's Video Editor

Ce guide vous accompagne de l'installation jusqu'à votre premier montage, puis vers la
traduction, les sous-titres et les fichiers de projet, sur **Linux**, **macOS** et **Windows**.
Il est écrit pour quelqu'un qui n'a jamais ouvert l'application. Chaque étape dit ce que vous
devez voir à l'écran et ce qui se passe derrière.

**La traduction est facultative.** L'application est complète sans elle : transcrire,
surligner, monter, lire, sous-titrer, garder des projets. Si c'est le montage qui vous
intéresse, suivez le parcours *Montage seul* décrit au § 1 : il n'y a rien d'autre à installer
que l'application.

Version décrite : 1.4.0.

---

## 1. Avant de commencer

### Ce que fait l'application

Vous ouvrez une vidéo ou un enregistrement sonore. L'application écrit ce qui est dit, mot à
mot, sur une page qui ressemble à du papier. Vous surlignez sur cette page ce que vous voulez
garder (ou ce que vous voulez couper), et l'application fabrique un nouveau fichier qui ne
contient que ces passages, avec des coupes placées dans les silences entre les mots et des
fondus propres. Elle peut aussi traduire le texte, préparer des sous-titres, les incruster dans
l'image, et garder plusieurs montages différents de la même vidéo dans des fichiers de projet.

### Ce qui reste sur votre ordinateur

Tout se fait sur votre machine : la transcription (faster-whisper), les coupes (ffmpeg), les
sous-titres. Rien ne part sur Internet, sauf dans trois cas que vous choisissez :

- vous ouvrez une vidéo par son **adresse** (YouTube, X…) : la vidéo est téléchargée ;
- vous **traduisez** ou **raccourcissez des sous-titres** en choisissant **Claude (API)** plutôt
  que le modèle local : le texte est envoyé à l'API d'Anthropic ;
- la première transcription télécharge un modèle de reconnaissance de la parole (une fois).

### Ce dont chaque fonction a besoin

| Fonction | Ce qu'il faut | Linux | macOS | Windows |
|---|---|---|---|---|
| Ouvrir, surligner, monter, lire | l'application et ffmpeg | ffmpeg installé par le paquet | inclus dans l'app | inclus dans l'app |
| Transcrire la parole | faster-whisper + un modèle | s'installe seul au premier usage (≈ 300 Mo) | inclus dans l'app | inclus dans l'app |
| Ouvrir une vidéo par son adresse | yt-dlp | téléchargé seul au premier usage (40 Mo) | idem | idem |
| Traduire, raccourcir des sous-titres (**facultatif**) | le **traduction toolkit** + Ollama ou une clé Anthropic | oui | oui | **non** (voir § 5) |
| Améliorer le son du montage (**facultatif**) | le **traduction toolkit** avec `deepfilternet`, `pyloudnorm`, `speechmos` dans son Python | oui | oui | **non** (voir § 3.5) |
| Incruster des sous-titres dans l'image | un ffmpeg avec libass | les ffmpeg habituels l'ont | inclus | inclus |

### Deux parcours : montage seul, ou montage et traduction

Choisissez dès maintenant ; vous pourrez toujours ajouter la traduction plus tard.

**Parcours A, montage seul.** Vous installez l'application et rien d'autre. Vous avez :

- la transcription de la parole (ou la lecture d'un `.srt`), la page, le surlignage, les
  coupes, les fondus, le montage en MP4 ou en son seul, le journal et la liste de montage (§ 3) ;
- le mode lecture et l'enregistrement du texte (§ 3.6) ;
- les sous-titres dans la langue de la vidéo : le fichier `.srt`, l'incrustation dans l'image,
  les pistes dans le MP4, et l'éditeur de sous-titres avec ses couleurs et ses outils (§ 6) ;
  sans le toolkit, le découpage en sous-titres est fait par l'application elle-même ;
- les fichiers de projet, plusieurs clips d'une même vidéo (§ 7).

Rien ne quitte l'ordinateur (hors l'ouverture d'une vidéo par son adresse). Aucune clé, aucun
modèle de langue, aucun autre logiciel. Lisez les § 2, 3, 4, 6, 7 et 8, et **sautez le § 5**.
**Sous Windows, c'est le seul parcours possible** : la traduction par le toolkit n'y fonctionne
pas (§ 2.3).
Dans l'éditeur de sous-titres, le bouton *Raccourcir ce qui se lit trop vite…* est le seul qui
demande le toolkit : il vous le dira si vous cliquez dessus.

**Parcours B, montage et traduction.** Tout ce qui précède, plus : la traduction du texte vers
une autre langue, une seconde page sur laquelle on surligne aussi, les sous-titres traduits,
le raccourcissement des sous-titres par un modèle de langue, et le découpage en sous-titres du
toolkit (plus soigné). Il faut installer en plus le traduction toolkit, un Python, et Ollama
ou une clé Anthropic (§ 5.1). **Linux et macOS seulement** : sous Windows, restez au parcours A
(ou passez par WSL, § 2.3).

### Les mots du guide

- **La page** : le texte transcrit, affiché comme une page de livre.
- **Surligner** : passer la souris sur des mots pour les marquer en jaune (gardés) ou en rose
  (coupés).
- **Le montage** : le fichier produit à partir de ce que vous avez surligné.
- **Un passage** : un morceau continu surligné.
- **Les sous-titres** (ou *cues*) : des blocs de texte avec un début et une fin, au format `.srt`.
- **Un projet** : un fichier `.rve.json` qui garde le texte, les traductions, les sous-titres,
  le surlignage et les réglages de sortie d'un montage.

---

## 2. Installer

### 2.1 Linux

#### Debian, Ubuntu, Pop!_OS, Linux Mint (paquet `.deb`)

Deux manières. La première vous donne les mises à jour automatiquement.

**A. Par le dépôt apt** (une fois pour toutes) :

```bash
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://funkypitt.github.io/apt-repo/funkypitt.gpg | sudo tee /etc/apt/keyrings/funkypitt.gpg >/dev/null
echo "deb [signed-by=/etc/apt/keyrings/funkypitt.gpg] https://funkypitt.github.io/apt-repo stable main" | sudo tee /etc/apt/sources.list.d/funkypitt.list
sudo apt update
sudo apt install readers-video-editor
```

**B. Par le fichier `.deb`** pris sur la page des versions du dépôt
(https://github.com/funkypitt/readers-video-editor/releases/latest) :

```bash
sudo apt install ./readers-video-editor_*_all.deb
```

Le paquet installe avec lui ce qu'il faut : Python 3, PyQt5 (avec QtMultimedia pour le lecteur),
numpy, soundfile, ffmpeg et les greffons GStreamer qui lisent le son et l'image dans la fenêtre.

Ce qui s'ajoute **au premier usage**, sans rien faire :

- la transcription : l'application installe faster-whisper dans un environnement Python à
  elle (`~/.local/share/readers-video-editor/venv`, ≈ 300 Mo), puis télécharge le modèle choisi
  (de 75 Mo à 3 Go selon le modèle, voir § 3.1) ;
- yt-dlp, si vous ouvrez une vidéo par son adresse (40 Mo).

**Lancer** : dans le menu des applications, *Reader's Video Editor* ; ou dans un terminal :

```bash
readers-video-editor
readers-video-editor ma-video.mp4            # ouvre directement un fichier
readers-video-editor mon-clip.rve.json       # ouvre un projet
```

#### Arch Linux, Manjaro

```bash
git clone https://github.com/funkypitt/readers-video-editor
cd readers-video-editor/packaging
makepkg -si
```

Pour la transcription, le paquet suggère `python-faster-whisper` ; sans lui, l'application
s'en installe une copie au premier usage, comme sur Debian.

#### Toute autre distribution (depuis les sources)

Il faut Python 3.8 ou plus, PyQt5 **avec QtMultimedia**, numpy, soundfile, ffmpeg, et que
`python3 -m venv` fonctionne (paquet `python3-venv` sur Debian).

```bash
git clone https://github.com/funkypitt/readers-video-editor
cd readers-video-editor
python3 -m pip install PyQt5 numpy soundfile
python3 readers_video_editor.py
```

Si l'image ou le son ne se lisent pas dans la fenêtre, installez les greffons GStreamer de
votre distribution (`gstreamer1.0-plugins-good` et `gstreamer1.0-libav` sur Debian, `gst-plugins-good`
et `gst-libav` sur Arch). Le texte et le montage marchent même sans lecteur.

### 2.2 macOS

1. **Téléchargez** le `.dmg` sur la page des versions du dépôt. Il y en a deux : prenez
   `apple-silicon` si votre Mac a une puce Apple (M1, M2, M3, M4…), `intel` sinon. Pour le
   savoir : menu  › *À propos de ce Mac* › la ligne *Puce* ou *Processeur*.
2. **Ouvrez** le `.dmg` et glissez *Readers Video Editor* dans le dossier *Applications*.
3. **Premier lancement** : l'application n'est pas signée par Apple, macOS refuse donc de
   l'ouvrir d'un double clic. Faites un **clic droit** (ou Ctrl + clic) sur l'application › **Ouvrir**
   › **Ouvrir** dans la boîte qui s'affiche. C'est à faire une seule fois.
   Sur macOS 15 (Sequoia), si le clic droit ne suffit pas : *Réglages Système* › *Confidentialité et
   sécurité*, descendez jusqu'au message qui parle de *Readers Video Editor* › **Ouvrir quand même**.
4. L'application contient ffmpeg et la transcription : rien d'autre à installer pour monter.

Dans ce guide, les raccourcis sont écrits avec **Ctrl**. Sur un Mac, lisez **⌘ Cmd** à la place
(Ctrl+T devient ⌘T, Ctrl+Maj+S devient ⌘⇧S).

Ses données vivent dans `~/Library/Application Support/readers-video-editor`.

### 2.3 Windows

1. **Téléchargez** `readers-video-editor_<version>_windows_x64.exe` sur la page des versions du
   dépôt. C'est un seul fichier, sans installateur : posez-le où vous voulez (par exemple dans
   un dossier *Readers* de vos documents) et faites-en un raccourci sur le bureau si vous voulez.
2. **Premier lancement** : Windows SmartScreen affiche *Windows a protégé votre ordinateur*,
   parce que le fichier n'est pas signé. Cliquez sur **Informations complémentaires**, puis sur
   **Exécuter quand même**. C'est à faire une seule fois.
3. Le premier démarrage prend quelques secondes de plus que les suivants : le `.exe` se
   déballe dans un dossier temporaire.
4. L'application contient ffmpeg et la transcription : rien d'autre à installer pour monter.

Ses données vivent dans `%APPDATA%\Readers Video Editor` (tapez ce chemin dans la barre de
l'Explorateur pour y aller).

**Limite sous Windows : le parcours A (montage seul) est le seul possible.** La traduction et
le raccourcissement des sous-titres par le modèle ne sont pas disponibles, parce que le script
`traduire.py` du toolkit s'appuie sur un module propre à Unix (`fcntl`). Tout le reste fonctionne, sous-titres compris (ils sont alors découpés
par l'application elle-même). Si vous avez **WSL** avec Ubuntu (Windows 11 lance les
applications graphiques de WSL), vous pouvez y installer la version Linux de l'application et
y faire la traduction. Voir § 5.

### 2.4 Vérifier l'installation

Lancez l'application. Vous devez voir **la page d'accueil** : un titre, un champ *Emplacement
du fichier, ou adresse d'une vidéo*, un bouton **Ouvrir**, deux listes (la langue parlée et le
modèle de transcription) et, plus bas, la liste des fichiers récemment ouverts (vide la
première fois).

L'application parle la langue de votre système : français, anglais, allemand, espagnol,
portugais ou russe.

**Parcours A, montage seul : l'installation est terminée.** Passez au § 3. Le § 5 ne vous
concerne pas. Sous Windows, c'est le cas de toute façon.

---

## 3. Le premier montage, pas à pas

Prenez une courte vidéo (deux ou trois minutes) pour ce premier essai.

### 3.1 Ouvrir et transcrire

Trois manières d'ouvrir :

- **glisser** le fichier sur la fenêtre ;
- cliquer sur **Ouvrir** (ou Ctrl+O) et choisir le fichier ;
- coller une **adresse** (YouTube, X, ou tout site que yt-dlp connaît) dans le champ de l'accueil,
  ou Ctrl+L. La vidéo est téléchargée dans un dossier *Reader's Video Editor* de votre dossier
  *Vidéos* (MP4, 1080p au plus) avec les
  sous-titres du site dans la langue choisie quand il en a, puis s'ouvre.

Formats acceptés : MP4, MKV, MOV, WebM, AVI, et le son seul : MP3, M4A, WAV, FLAC, OGG, Opus…

Avant d'ouvrir, choisissez sur l'accueil :

- **la langue parlée** (*auto* laisse le modèle la reconnaître ; dire la langue est plus sûr) ;
- **le modèle** de transcription :

| Modèle | Taille à télécharger | Qualité | Vitesse |
|---|---|---|---|
| tiny | ≈ 75 Mo | grossière | très rapide |
| base | ≈ 140 Mo | correcte sur de l'anglais clair | rapide |
| **small** (défaut) | ≈ 460 Mo | bonne pour la plupart des usages | raisonnable |
| medium | ≈ 1,5 Go | meilleure sur les accents et les termes rares | lente |
| large-v3 | ≈ 3 Go | la meilleure | très lente, beaucoup de mémoire |

La transcription se fait sur le processeur. Le modèle est téléchargé une fois, puis gardé.

**Ce que vous voyez** : la page de patience, avec une jauge et un message (*Préparation…*,
*Téléchargement du modèle…*, *Transcription…*). Si un fichier `.srt` du même nom est posé à côté
de la vidéo, il est lu tout de suite, sans transcription.

Si la transcription échoue, la page propose de **recommencer** avec une autre langue ou un
autre modèle, ou d'**ouvrir des sous-titres** à la place.

### 3.2 Lire la page

Le texte apparaît sur la page, en paragraphes, avec l'instant de chaque paragraphe dans la
marge. À gauche : l'image, les commandes du lecteur (−5 s, lecture, +10 s, le curseur, la
vitesse de 0,8× à 2×), le bilan du montage et, en bas, la sortie.

- **Un clic sur un mot** lit à partir de là. Le mot en cours de lecture est souligné et la page
  suit.
- **La barre d'espace** lance ou arrête la lecture ; **←** et **→** reculent et avancent de 5 s.
- Les **passages sans mots** (musique, silence, un passage que le modèle a laissé) sont aussi sur
  la page, sur fond grisé : ils se marquent d'un clic.

### 3.3 Surligner

Dans la barre du haut, **Je surligne** : **ce que je garde** (le mode normal) ou **ce que je
coupe**.

- **Glissez** sur les mots pour les surligner. En mode *garde*, ils deviennent jaunes ; en mode
  *coupe*, ils sont rayés de rose.
- **Double clic** sur un mot : toute la phrase.
- **Maj + clic** : étend le surlignage du dernier mot marqué jusqu'à celui-là. Pour un long
  passage, cliquez son premier mot, puis son dernier avec Maj.
- **La gomme** (bouton *Gomme*, ou touche **G**, ou Alt + glisser) efface ; **S** revient au
  stabilo.
- **Annuler** / **Rétablir** : Ctrl+Z / Ctrl+Y.
- **Tout effacer** enlève tout le surlignage ; en mode *coupe*, **Rayer le silence** (ou *Rayer
  les 12 silences*) marque d'un coup tous les passages sans mots.

Le surlignage est enregistré à chaque geste : vous pouvez fermer et rouvrir le même fichier,
vous le retrouvez.

### 3.4 Le bilan et les passages

À gauche, le bilan dit la durée du montage et le nombre de passages (*Montage de 2:14, 3
passages sur 12:30*). Dessous, la liste des passages : un clic sur un passage y va dans le
lecteur, la croix à sa droite le retire.

**▶ Voir le montage** lit le montage tel qu'il sera produit, en sautant ce qui est enlevé.

### 3.5 Produire

En bas à gauche :

- **Produire** : *Une vidéo (MP4)*, ou *Le son seul* en MP3, M4A ou WAV.
- **Fondu à chaque coupe** : *Aucun*, *Bref (0,2 s)*, *Normal (0,5 s)*, *Lent (1 s)*, *Très lent (1,5 s)*.
  Le son entre et sort en fondu à chaque morceau.
- **fondu au noir de l'image** : l'image passe au noir seulement là où une seconde ou plus est
  enlevée.
- **Image** : *Tel quel*, ou *Carré (1:1), centré* pour les réseaux sociaux : le centre de
  l'image, le petit côté comme côté du carré ; les sous-titres incrustés sont dimensionnés pour
  ce carré. Grisé quand on produit le son seul.
- **Son** : *Tel quel*, ou *Amélioré : bruit de fond, niveau*. Le son du montage passe alors par
  `finaliser.py` du traduction toolkit (§ 5.1 pour l'installer) : ronflette secteur et bruit de
  fond régulier retirés s'il en trouve (DeepFilterNet3 à faible dose, contrôlé par DNSMOS : si la
  voix en souffre, un nettoyage plus doux, ou aucun), niveaux de voix très inégaux égalisés,
  niveau mis à la norme des podcasts par un gain constant, fondus courts. La durée ne change pas,
  le journal, la liste de montage et les sous-titres restent justes. À la fin, le panneau et le
  journal disent ce qui a été fait (« ronflette secteur à 50 Hz retirée ; bruit de fond réduit,
  de 8 dB au plus ; niveau +2,1 dB → −16,0 LUFS »). Il faut, dans le Python du toolkit :
  `pip install deepfilternet pyloudnorm speechmos` ; une carte graphique sert si elle est là,
  sinon le processeur suffit (plus lent). Si le toolkit n'est pas trouvé, une petite boîte
  demande son dossier.
- **Sous-titres** : voir § 6.

Cliquez **Produire le montage** (Ctrl+E). La jauge avance ; *Stop* interrompt. Le fichier est
écrit **à côté de l'original**, avec le suffixe `_edit` : `ma-video_edit.mp4`, puis
`ma-video_edit-2.mp4` s'il en existe déjà un. L'image est ré-encodée une fois (x264).

À côté du montage :

- `ma-video_edit.txt` : le journal des coupes, mot à mot, ce qui est gardé et ce qui est enlevé ;
- `ma-video_edit.edl` : la liste de montage (CMX 3600), pour rouvrir le découpage dans un
  logiciel de montage.

À la fin, **Regarder** (ou **Écouter**) ouvre le fichier dans votre lecteur habituel, **Ouvrir le
dossier** le montre.

### 3.6 Le mode lecture

**Lire** (Ctrl+R) met la page seule dans toute la fenêtre, en lignes d'environ soixante-dix
caractères, les commandes du lecteur dessous : pour lire une transcription confortablement, le
mot prononcé souligné. Le surlignage reste. **Monter** revient au montage.

**Texte ▾ › Enregistrer le texte…** écrit la transcription en paragraphes dans un `.txt` ;
**copier le texte** la met dans le presse-papiers (Ctrl+Maj+C). Ctrl+= et Ctrl+− changent la
taille du texte.

---

## 4. Où vivent vos données

| | Linux | macOS | Windows |
|---|---|---|---|
| Réglages | `~/.config/readers-video-editor/config.json` | `~/Library/Application Support/readers-video-editor/config.json` | `%APPDATA%\Readers Video Editor\config.json` |
| Projets (son, texte, surlignage, sous-titres) | `~/.local/share/readers-video-editor/projects/` | `~/Library/Application Support/readers-video-editor/projects/` | `%APPDATA%\Readers Video Editor\projects\` |
| Modèles de transcription | `…/models/` | `…/models/` | `…\models\` |
| yt-dlp | `…/bin/` | `…/bin/` | `…\bin\` |
| faster-whisper (Linux) | `~/.local/share/readers-video-editor/venv/` | — | — |

Chaque vidéo ouverte a un dossier dans `projects/`, nommé d'après le fichier et une empreinte de
son chemin, sa taille et sa date. C'est ce qui permet de rouvrir un fichier avec son texte sans
retranscrire. Vous pouvez supprimer ces dossiers pour faire de la place : le texte sera refait
au prochain usage.

---

## 5. Traduire (facultatif)

Cette partie ne concerne que le parcours B. Sans elle, l'application fait tout le reste ; vous
pouvez la lire plus tard, quand vous en aurez l'usage.

### 5.1 Ce qu'il faut installer

La traduction n'est pas faite par l'application mais par **`traduire.py`**, le script du
**traduction toolkit** (https://github.com/funkypitt/traduction-toolkit), que l'application
lance dans son propre Python. Elle en reprend toutes les passes : analyse du contenu (noms,
glossaire), traduction par morceaux, relecture, cohérence, glossaire.

**1. Le toolkit.** Clonez-le dans l'un des dossiers où l'application le cherche :

```bash
git clone https://github.com/funkypitt/traduction-toolkit ~/code/traduction-toolkit
```

L'application regarde, dans l'ordre : la variable d'environnement `TRADUCTION_DIR`, le dossier
donné une fois dans la boîte de traduction (retenu dans les réglages), `~/code/traduction`,
`~/code/traduction-toolkit`. Si elle ne le trouve pas, la boîte *Traduire…* le dit et vous
demande son dossier.

**2. Un Python pour le toolkit.** `traduire.py` n'a besoin que de la bibliothèque standard de
Python 3.10 ou plus, et du paquet `anthropic` seulement si vous choisissez Claude.
L'application prend, dans l'ordre : `TRADUCTION_PYTHON`, `~/miniconda3/envs/interview/bin/python`,
`~/miniconda3/envs/traduction/bin/python`, sinon le `python3` de votre système (sur Linux
depuis les sources, le Python qui lance l'application).

- Linux : le Python du système convient. Pour Claude : `python3 -m pip install anthropic`.
- macOS : `python3` vient avec les outils en ligne de commande de Xcode. La première fois que
  vous tapez `python3` dans le Terminal, macOS propose de les installer : acceptez. Pour
  Claude : `python3 -m pip install anthropic`.
- Windows : pas disponible (voir § 2.3). Avec WSL : installez l'application Linux dans WSL
  (§ 2.1), le toolkit dans `~/code/traduction-toolkit` de WSL, et lancez tout depuis WSL.

**3. Un modèle de langue**, l'un ou l'autre :

- **Local, avec Ollama** (gratuit, hors ligne). Installez Ollama depuis https://ollama.com
  (Linux : `curl -fsSL https://ollama.com/install.sh | sh` ; macOS : l'application Ollama ;
  Windows : l'installateur, utile seulement avec WSL). Puis téléchargez un modèle :

  ```bash
  ollama pull gemma4:31b
  ```

  `gemma4:31b` est le modèle que le toolkit recommande pour la traduction. Il demande une
  carte graphique avec 24 Go de mémoire, ou un Mac avec au moins 32 Go de mémoire unifiée.
  Sur une machine plus petite, prenez un modèle plus léger que le toolkit cite aussi, par
  exemple `mistral-small`, et écrivez son nom dans le champ *Modèle Ollama* de la boîte.
  Ollama doit tourner (sur Linux il tourne en service après l'installation ; sur macOS, lancez
  l'application Ollama) : l'application l'attend sur `http://localhost:11434` et dit *Ollama ne
  répond pas* sinon.

- **Claude, par l'API d'Anthropic** (payant, meilleur, le texte part chez Anthropic). Créez une
  clé sur https://console.anthropic.com (*API Keys* › *Create Key*) et mettez-la dans la
  variable d'environnement `ANTHROPIC_API_KEY` **de façon que l'application la voie** :

  - Linux, lancée depuis le menu : écrivez `ANTHROPIC_API_KEY=sk-ant-…` dans le fichier
    `~/.config/environment.d/anthropic.conf` (créez-le), puis fermez et rouvrez la session. Ou
    lancez l'application depuis un terminal où la clé est exportée.
  - macOS, lancée depuis le Finder : dans le Terminal, `launchctl setenv ANTHROPIC_API_KEY sk-ant-…`
    (à refaire après un redémarrage), puis relancez l'application. Ou lancez-la depuis le
    Terminal : `ANTHROPIC_API_KEY=sk-ant-… open -a "Readers Video Editor"`.

  L'application dit *ANTHROPIC_API_KEY n'est pas définie* quand elle ne la voit pas.

### 5.2 La boîte Traduire…

**Texte ▾ › Traduire…** (Ctrl+T).

- **De** / **Vers** : la langue parlée et la langue voulue. Quand le texte vient d'un `.srt`,
  la langue d'origine n'est pas connue : celle que vous donnez ici la nomme désormais.
- **Traduction par** : *Sur cet ordinateur (Ollama)* ou *Claude (API) · claude-opus-5*. Votre
  choix vaut pour **toutes** les passes. Il est retenu pour la prochaine fois, et pour la boîte
  de raccourcissement des sous-titres (§ 6.3), qui partage ce réglage.
- **Modèle Ollama** : le nom du modèle local (`gemma4:31b` par défaut).
- **Contexte** : noms propres, sujet, registre (tutoiement ou vouvoiement…). Facultatif mais
  précieux : il est donné au modèle à chaque passe.
- **Passe de relecture** : une seconde lecture par le modèle (plus long, meilleur).
- **Analyse du contenu par Claude plutôt que par le modèle local** : ne s'affiche qu'avec le
  modèle local **et** une clé présente. Décochée par défaut : tout reste local. Cochée,
  l'analyse seule (un appel, quelques centimes) va à Claude, et la traduction reste locale :
  c'est la règle *auto* du toolkit, que l'application vous laisse choisir.

**Ce que vous voyez** : la page de patience, avec à chaque étape **le nom de qui travaille** :
*Analyse du texte… · Ollama gemma4:31b*, *Traduction… 3 sur 12 · Ollama gemma4:31b*,
*Relecture…*, *Vérification de la cohérence…*, *Vérification du glossaire…*. **Stop** arrête
tout. À titre d'idée : une vidéo de trente secondes a pris quarante secondes avec `gemma4:31b`
sur une RTX 3090 ; comptez des dizaines de minutes pour une heure de parole.

### 5.3 Deux pages, un surlignage

Après la traduction, un **sélecteur** apparaît dans la barre : *English* | *Français* (ou les
langues de votre projet). La page montre l'original ou la traduction. Les mots traduits sont
placés sur les instants des mots originaux, donc leurs positions sont *estimées* : les coupes
cherchent le silence des deux côtés, comme pour des sous-titres.

**Le surlignage suit par le temps** : ce que vous avez surligné sur l'original est retrouvé sur
la traduction, et inversement. Vous pouvez donc monter dans la langue que vous lisez le mieux.
On peut traduire vers plusieurs langues : chacune ajoute un bouton.

Refaire une traduction vers une langue déjà présente la remplace (et refait ses sous-titres).

---

## 6. Les sous-titres

### 6.1 Enregistrer un fichier `.srt`

**Texte ▾ › Enregistrer les sous-titres…** écrit le texte de la page affichée (original ou
traduction) en `.srt`, sur toute la durée du fichier, proposé sous le nom `ma-video.fr.srt`.
Le découpage en sous-titres est celui du toolkit quand il est là (deux lignes de 42
caractères, coupes sur les pauses et la ponctuation, 17 caractères par seconde visés), sinon
un découpage plus simple fait par l'application (fin de phrase suivie d'une pause, pause de
2 s, deux lignes de 42 caractères, 7 s au plus). En parcours A, c'est ce découpage que vous
avez, et l'éditeur de sous-titres permet de le retoucher.

### 6.2 Les sous-titres dans le montage

En bas à gauche, sous *Sous-titres* :

- **Dans l'image : Français** (ou *Original*, ou chaque traduction) : les sous-titres sont
  **incrustés** dans l'image du MP4, dans le style par défaut du toolkit (Arial, blanc à
  contour noir), réduits pour les vidéos plus étroites que 16:9. *Aucun* n'incruste rien.
- Le style, à côté : **Deux lignes en bas** (les sous-titres habituels), ou **Légendes façon
  Instagram** : quelques grands mots à la fois (quatre au plus, Montserrat ExtraBold, blanc à
  contour noir), centrés près du bas de l'image, et plus haut sur une vidéo verticale,
  au-dessus de la bande que les applications posent sur un Reel, le mot prononcé en jaune ; une carte par groupe de mots, coupée aux
  fins de phrase et aux pauses. Les cartes suivent le minutage des mots : exact quand le texte
  vient de la transcription, estimé quand il vient d'un fichier de sous-titres ou d'une
  traduction. Les tailles sont des parts de l'image : une vidéo verticale, carrée ou 16:9 reçoit
  le même rendu. Les `.srt` à côté du montage restent les sous-titres classiques.
- **Fichiers de sous-titres à côté du montage (.srt)** : un `.srt` par langue, sur la durée du
  montage (`ma-video_edit.fr.srt`, `ma-video_edit.en.srt`), **et** ces mêmes sous-titres
  ajoutés au MP4 comme pistes que le lecteur peut afficher ou cacher.

Ces deux réglages sont retenus, et enregistrés dans le projet.

### 6.3 L'éditeur de sous-titres

Le bouton **Sous-titres** (Ctrl+U) dans la barre remplace la page par **le tableau des
sous-titres** de la langue affichée. La première fois pour une langue, ils sont découpés par
le toolkit (page de patience, quelques secondes), puis **gardés tels que vous les laissez**,
dans le dossier du projet et dans le fichier de projet.

**Le tableau**, une ligne par sous-titre :

| Colonne | Contenu |
|---|---|
| Début, Fin | les instants, écrits `1:02.345`. Modifiables : double clic, ou Entrée. |
| c/s | la vitesse de lecture en **caractères par seconde** : **vert** jusqu'à 17 (confortable), **ambre** jusqu'à 22, **rouge** au-delà (à raccourcir). |
| Texte | le sous-titre, modifiable en place. |
| Original | pour une traduction : les mots originaux prononcés pendant ce sous-titre. |

Une ligne **teintée** signale un défaut de forme, et son infobulle dit lequel : rouge pour une
ligne de plus de 42 caractères, trois lignes, ou un chevauchement avec le suivant ; ambre pour
un sous-titre de plus de 7 s ou de moins de 1 s. La ligne **jaune** est celle en cours de
lecture : le tableau la suit pendant la lecture.

**Travailler dans le tableau** :

- **Un clic** sur une ligne va à son début dans le lecteur.
- **Double clic** (ou Entrée) sur le texte : vous tapez dedans. **Entrée** coupe le sous-titre
  en deux à l'endroit du curseur (le temps est partagé au prorata des lettres ; une coupe au
  milieu d'un mot est ramenée à l'espace précédent). **Maj+Entrée** passe à la ligne.
  **Tab** valide et passe au sous-titre suivant. **Échap** abandonne.
- **Scinder** coupe le sous-titre sélectionné à l'espace le plus proche du milieu.
- **Fusionner avec le suivant** (Ctrl+J) réunit deux sous-titres.
- **Supprimer** (touche Suppr) enlève les lignes sélectionnées (plusieurs avec Maj ou Ctrl).
- **Début −** / **Début +** et **Fin −** / **Fin +** déplacent le bord d'un dixième de seconde
  (Alt+← / Alt+→ pour le début, Alt+Maj+← / Alt+Maj+→ pour la fin). **Début ici** / **Fin ici**
  posent le bord à l'instant où en est le lecteur : lancez la lecture, arrêtez au bon moment,
  cliquez.
- **Annuler** / **Rétablir** (Ctrl+Z / Ctrl+Y) portent sur les sous-titres tant que l'éditeur
  est affiché.
- **Redécouper depuis le texte** refait le découpage (celui du toolkit s'il est là, celui de
  l'application sinon), après une question si vous aviez retouché.
- **Raccourcir ce qui se lit trop vite…** envoie au modèle les sous-titres **rouges** (ou ceux
  sélectionnés, ou tous) pour qu'il les abrège sans perdre le sens, par la **passe de relecture
  de `traduire.py`** (glossaire de la traduction compris). La boîte offre le même choix que la
  traduction : *Sur cet ordinateur (Ollama)* ou *Claude (API)*. Seules les lignes demandées
  changent, en une seule étape annulable. Même besoin que la traduction (§ 5.1) : sans le
  toolkit, la boîte le dit et demande son dossier ; en parcours A, retouchez le texte à la main.

**L'image** montre le sous-titre en cours de lecture, dans les proportions de l'incrustation.
Hors de l'éditeur, elle montre ceux choisis pour *Dans l'image* dès qu'ils existent.

Les sous-titres retouchés sont ceux qu'utilisent *Enregistrer les sous-titres…* et la sortie ;
pour un montage, chacun est rogné aux passages gardés et décalé sur le temps du montage.

Le mode Sous-titres et le mode Lire s'excluent ; les outils de surlignage sont en pause tant
que l'éditeur est affiché, la liste des passages et la sortie restent actives.

---

## 7. Les fichiers de projet

Une même vidéo peut donner plusieurs clips. Chaque clip est un **projet** : un fichier
`ma-video.rve.json`, posé par défaut à côté de la vidéo, qui contient le texte, les traductions,
les sous-titres, le surlignage, le mode (garde ou coupe), le fondu, et les réglages de sortie.

- **Projet ▾ › Enregistrer le projet…** (Ctrl+Maj+S) : la première fois, demande le nom ;
  ensuite réécrit le même fichier. **Enregistrer le projet sous…** en fait un autre.
- **Projet ▾ › Ouvrir un projet…** (Ctrl+Maj+O), ou glisser le `.rve.json` sur la fenêtre,
  ou le donner sur l'accueil, ou en ligne de commande.
- À l'ouverture, le projet remplace ce que le dossier de travail de la vidéo contenait (texte,
  traductions, sous-titres, surlignage). Si la vidéo n'est plus à son chemin, elle est cherchée
  **à côté du fichier de projet**, sous son nom : vous pouvez donc déplacer les deux ensemble,
  ou les donner à quelqu'un.

Le nom du projet ouvert s'affiche sous le nom de la vidéo, dans la barre.

---

## 8. Les raccourcis

Sur Mac, Ctrl se lit ⌘ Cmd.

| Touche | Effet |
|---|---|
| Ctrl+O | Ouvrir un fichier |
| Ctrl+L | Ouvrir une adresse |
| Espace | Lecture / pause |
| ← / → | −5 s / +5 s |
| S / G | Stabilo / Gomme |
| Ctrl+Z / Ctrl+Y | Annuler / Rétablir (le surlignage, ou les sous-titres dans l'éditeur) |
| Ctrl+E | Produire le montage |
| Ctrl+R | Lire / Monter |
| Ctrl+U | Éditeur de sous-titres |
| Ctrl+T | Traduire… |
| Ctrl+S | Enregistrer le texte |
| Ctrl+Maj+C | Copier le texte |
| Ctrl+Maj+S / Ctrl+Maj+O | Enregistrer / Ouvrir un projet |
| Ctrl+= / Ctrl+− | Texte plus grand / plus petit |
| Dans l'éditeur de sous-titres : Entrée, Maj+Entrée, Tab, Échap | Scinder au curseur, passer à la ligne, suivant, abandonner |
| Suppr, Ctrl+J | Supprimer, fusionner avec le suivant |
| Alt+← / Alt+→, Alt+Maj+← / Alt+Maj+→ | Début −/+ 0,1 s, Fin −/+ 0,1 s |

---

## 9. Dépannage

**« ffmpeg n'a pas été trouvé »** (installation depuis les sources sur Linux) : installez ffmpeg
avec votre distribution et relancez. Les versions macOS et Windows l'emportent avec elles.

**Pas de son ou pas d'image dans la fenêtre, mais le texte est là** : sur Linux, il manque des
greffons GStreamer (`gstreamer1.0-plugins-good`, `gstreamer1.0-libav`). Le montage et la sortie
marchent quand même : l'application le dit dans un message.

**La transcription ne démarre pas sur Linux** : elle a besoin de `python3 -m venv` (paquet
`python3-venv`) et d'un accès à Internet la première fois (≈ 300 Mo, puis le modèle). Un
fichier `.srt` à côté de la vidéo se passe de transcription.

**« Ce fichier ne peut pas être lu »** : ffmpeg ne reconnaît pas le fichier ; essayez de le
convertir en MP4 ou MP3.

**L'adresse ne s'ouvre pas** : yt-dlp se met à jour seul une fois par jour, parce que les sites
changent souvent ; réessayez plus tard. Certaines vidéos demandent d'être connecté : prenez
alors le fichier autrement.

**« Le traduction toolkit… n'a pas été trouvé »** : clonez-le (§ 5.1) ou donnez son dossier
dans la boîte ; le dossier doit contenir `traduire.py`.

**« Ollama ne répond pas à http://localhost:11434 »** : lancez Ollama (`ollama serve` dans un
terminal, ou l'application Ollama sur macOS) et vérifiez que le modèle est téléchargé
(`ollama list`).

**« ANTHROPIC_API_KEY n'est pas définie »** : la clé n'est pas visible de l'application ; voir
§ 5.1 pour la poser de façon que le menu ou le Finder la transmettent.

**« La traduction a échoué : … »** : le message reprend l'erreur du toolkit. Les causes
courantes : un modèle Ollama qui n'est pas téléchargé, un Python trop ancien pour le toolkit
(il faut 3.10 ou plus), le paquet `anthropic` absent avec Claude.

**Les sous-titres ne sont pas dans l'image du montage** (Linux depuis les sources) : il faut un
ffmpeg compilé avec libass ; les paquets des distributions l'ont.

**Windows affiche « Windows a protégé votre ordinateur », macOS « ne peut pas être ouvert »** :
l'application n'est pas signée ; voir § 2.2 et § 2.3, c'est à faire une fois.

**Faire de la place** : supprimez des dossiers dans `projects/` (le texte sera refait), ou des
modèles dans `models/` (retéléchargés au besoin). Voir § 4.

---

## 10. Pour aller plus loin

- `README.md` : le résumé des fonctions, en anglais.
- `docs/NOTES.md` : comment l'application fait ce qu'elle fait (les coupes, les positions
  estimées, le pont vers le toolkit, le format des projets).
- Le traduction toolkit : https://github.com/funkypitt/traduction-toolkit, et son `README`
  pour les modèles, les clés et la ligne de commande.
