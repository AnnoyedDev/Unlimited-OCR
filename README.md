# Unlimited-OCR Subtitler

Logiciel d'OCR vidéo : on charge une vidéo, on définit une zone de rognage (rectangle
rouge redimensionnable) sur les sous-titres incrustés, on affine le texte avec des
filtres en direct, puis le logiciel fait l'OCR (modèle IA [baidu/Unlimited-OCR](models/Unlimited-OCR))
pour produire un fichier `.ass` (sous-titres) avec le bon timing.

Ce document a deux parties :
- **[Guide simple](#guide-simple)** — pour installer et utiliser le logiciel sans avoir
  besoin de savoir coder.
- **[Section avancée](#section-avancée)** — architecture du code, réglages fins,
  comportements internes, pour les utilisateurs à l'aise avec le développement.

---

# Guide simple

## 1. Ce dont vous avez besoin

- **Python 3.12** installé sur votre machine.
  - Windows : téléchargez-le sur [python.org/downloads](https://www.python.org/downloads/)
    et cochez "Add python.exe to PATH" pendant l'installation.
  - Linux : la plupart des distributions l'ont déjà, ou passez par le gestionnaire de
    paquets de votre distro.
- **`uv`** (l'outil qui installe tout le reste automatiquement) :
  - Windows (PowerShell) : `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
  - Linux : `curl -LsSf https://astral.sh/uv/install.sh | sh`
  - (redémarrez votre terminal après l'installation de `uv`)
- **Une carte graphique** n'est pas obligatoire mais fortement recommandée : sans elle,
  le logiciel fonctionne quand même (sur le processeur, "CPU") mais l'OCR est bien plus
  lent (plusieurs secondes par image analysée au lieu d'un peu plus d'une seconde).

Vous n'avez **rien d'autre à installer manuellement** (pas de CUDA, pas de ROCm à part
entière, etc.) : le script d'installation fourni s'en charge en détectant votre matériel.

## 2. Installer le logiciel

Ouvrez un terminal dans le dossier du projet, puis lancez :

```
python install.py
```

Ce script :
1. crée un environnement Python isolé (dossier `.venv`) pour ne rien mélanger avec le
   reste de votre système ;
2. installe toutes les briques nécessaires (interface graphique, lecture vidéo, etc.) ;
3. **détecte automatiquement votre carte graphique** et installe la bonne version de
   PyTorch (le moteur qui fait tourner l'IA) :

| Votre configuration | Ce qui est installé | Vitesse |
|---|---|---|
| **NVIDIA** (Windows ou Linux) | build CUDA (accélération GPU) | Rapide |
| **AMD sous Linux** | build ROCm (accélération GPU) | Rapide |
| **AMD sous Windows** | build CPU (pas d'accélération GPU disponible côté PyTorch pour AMD+Windows) | Lent |
| **Pas de carte dédiée / carte non reconnue** | build CPU | Lent |

Ça peut prendre plusieurs minutes (l'installation des dépendances Python). C'est
normal, ça ne se refait qu'une fois.

Si l'installation échoue en cours de route, relancez simplement `python install.py` —
il réutilise ce qui a déjà été téléchargé.

> ⚠️ **N'oubliez pas de télécharger le modèle !** `python install.py` installe
> uniquement les dépendances logicielles — **il ne télécharge pas le modèle IA**.
> Le dossier `models/` est ignoré par git (fichiers trop volumineux, plusieurs Go),
> donc c'est une étape manuelle obligatoire avant de pouvoir lancer le logiciel :
>
> 1. Allez sur [huggingface.co/baidu/Unlimited-OCR](https://huggingface.co/baidu/Unlimited-OCR).
> 2. Téléchargez **tout le repo** (pas juste un fichier — tous les poids, configs,
>    tokenizer, etc.), par exemple avec `huggingface-cli` :
>    ```
>    huggingface-cli download baidu/Unlimited-OCR --local-dir models/Unlimited-OCR
>    ```
>    ou via `git clone` (avec [Git LFS](https://git-lfs.com/) installé) :
>    ```
>    git clone https://huggingface.co/baidu/Unlimited-OCR models/Unlimited-OCR
>    ```
> 3. Vérifiez que le résultat se trouve bien dans `models/Unlimited-OCR/` à la racine
>    du projet (donc `models/Unlimited-OCR/config.json`,
>    `models/Unlimited-OCR/model-00001-of-000001.safetensors`, etc.) — c'est le chemin
>    attendu par le logiciel.

## 3. Lancer le logiciel

Chaque fois que vous voulez utiliser le logiciel :

**Windows :**
```
.venv\Scripts\activate
python -m app.main
```

**Linux / macOS :**
```
source .venv/bin/activate
python -m app.main
```

## 4. Utiliser l'interface

1. **Fichier → Ouvrir une vidéo...** (ou le bouton correspondant).
2. Un **rectangle rouge** apparaît sur la vidéo, au centre : c'est la zone qui sera
   analysée par l'IA. Faites-le glisser et redimensionnez-le (par les coins/bords)
   pour qu'il entoure précisément la zone où apparaissent vos sous-titres.
3. **Panneau de gauche** : des filtres pour rendre le texte plus lisible avant l'OCR
   (agrandir, contraste, netteté, etc.). Cochez-en et ajustez les curseurs — l'aperçu
   en bas du panneau se met à jour en direct, réglez-le jusqu'à ce que le texte
   ressorte bien.
4. **Panneau de droite** : les réglages avant de lancer (détaillés dans la section
   suivante) puis le bouton **"Lancer l'OCR"**. Une barre de progression et une liste
   de résultats en direct s'affichent.
5. Une fois terminé, cliquez sur **"Exporter en .ass..."** pour sauvegarder le fichier
   de sous-titres, utilisable dans VLC, Aegisub, ou n'importe quel lecteur/éditeur qui
   accepte le format `.ass`.

### Mode image (jeu d'images) — OCR à partir de sous-titres bitmap

Si vous avez déjà un fichier de sous-titres **image** plutôt qu'une vidéo — un flux
**PGS** (`.sup`, format Blu-ray) ou **VobSub** (`.idx` + `.sub`, format DVD) — pas besoin
de ressortir la vidéo :

1. **Fichier → Ouvrir un jeu d'images (.sup/.idx)...** et choisissez le fichier.
   L'appli bascule automatiquement en **mode image**.
2. L'aperçu central change : au lieu du lecteur vidéo (lecture/pause, curseur de
   défilement), vous avez une **liste de toutes les images** de sous-titres à gauche
   (avec leur horodatage début → fin) et un bouton **< / >** pour naviguer une par une —
   chaque entrée est déjà un sous-titre distinct, pas la peine de scruter une timeline.
3. Le rectangle rouge de rognage et les filtres du panneau de gauche fonctionnent
   pareil (chaque image de sous-titre étant déjà assez cadrée, le rectangle par défaut
   couvre presque tout, ajustez si besoin).
4. **Fichier → Mode image (jeu d'images)** (case à cocher) permet de rebasculer
   manuellement entre les deux modes ; certains réglages du panneau de droite propres
   au défilement vidéo (intervalle N frames, vérifications périodiques) sont grisés en
   mode image car ils n'ont pas de sens ici — chaque image du jeu est déjà un événement
   à part entière, il n'y a rien à "échantillonner".
5. **Lancer l'OCR** et **Exporter en .ass...** fonctionnent exactement pareil.

### Les réglages du panneau de droite, expliqués simplement

- **Seuil de similarité image (skip)** : décide si deux images se ressemblent assez
  pour être considérées comme "le même sous-titre, pas la peine de relire". **Plus le
  pourcentage est haut, plus il faut que les images soient proches pour être sautées**
  (donc plus sûr, mais plus lent). Voir les exemples chiffrés dans la
  [section avancée](#seuil-de-similarité-image-skip---explication-détaillée) si vous
  voulez comprendre exactement comment ça marche — c'est un réglage facile à mal
  interpréter dans le mauvais sens.
  - Par défaut : **99 %** — recommandé pour la plupart des vidéos. Par défaut, **aucun**
    appel OCR n'est fait sur une image jugée "pareille" — pas d'exception, pas de
    vérification forcée qui gaspille des appels sur des passages vides/statiques.
  - Si des sous-titres très courts ("Hé !", "Wouah") manquent encore dans le `.ass` :
    montez ce seuil (ex. 99,5 %) avant toute chose, et resserrez le rectangle rouge
    autour du texte.

- **Vérification de sécurité périodique** (case décochée par défaut) : si activée,
  force un appel OCR toutes les N frames même sans changement détecté — au cas où une
  dérive très lente et progressive ne franchirait jamais le seuil de similarité.
  Coûte des appels OCR en plus (y compris sur de longues zones vides), donc à activer
  seulement si vous soupçonnez ce cas précis sur votre vidéo. Laissez décochée sinon.

- **Vérifier le changement toutes les N frames seulement** (case décochée par défaut) :
  accélère la lecture vidéo en ne regardant qu'une frame sur N au lieu de toutes les
  regarder, au prix d'un vrai risque de rater un sous-titre affiché moins de N frames
  de suite. À activer seulement si vous avez besoin d'aller plus vite et que vous savez
  que vos sous-titres restent affichés longtemps.

- **Taille du batch OCR** (par défaut 4) : regroupe plusieurs images à envoyer d'un
  coup au modèle au lieu d'une par une. Mesuré ~2,5x plus rapide par image (batch de 8
  vs une par une, sur GPU). Plus haut = plus rapide mais plus de mémoire GPU utilisée,
  et les résultats en direct arrivent un peu par à-coups (le batch se remplit avant
  d'être envoyé, au lieu d'un résultat immédiat par image). Mettez 1 pour revenir au
  comportement "une image à la fois".

- **Seuil de fusion des textes similaires** : quand l'IA relit deux fois presque le
  même sous-titre avec une petite variation (une faute de lecture, un caractère en
  trop), ce réglage décide si on les fusionne en un seul sous-titre au lieu d'en créer
  plusieurs qui scintillent dans le `.ass`.
  - Par défaut : **85 %** — fusionne les petites variations, garde séparées les phrases
    vraiment différentes.
  - Trop haut (> 95 %) : le scintillement peut revenir (plus rien n'est fusionné).
  - Trop bas (< 70 %) : risque de fusionner deux sous-titres réellement différents
    s'ils partagent des mots.

- **Durée min. d'un sous-titre** : les sous-titres plus courts que cette durée sont
  supprimés du `.ass` final (utile pour éliminer un dernier scintillement résiduel).
  0 = désactivé.

- **Deuxième passe si rien détecté (zoom auto)** (cochée par défaut) : quand une image
  signalée comme "changée" revient vide de l'OCR, ce n'est pas toujours qu'il n'y a
  vraiment rien à lire — sur de la vraie vidéo (pas un fond uni), un texte court sur un
  fond chargé (photo, mur en pierre, grain de l'image...) peut suffire à perturber le
  modèle au point qu'il ne renvoie rien du tout, alors que le texte est parfaitement
  lisible à l'œil. Cette option relance l'OCR une seconde fois sur un zoom automatique
  et resserré autour de la zone la plus lumineuse de l'image (le texte est presque
  toujours plus clair que le fond), avec un fort seuillage pour éliminer le fond
  chargé. Voir la section avancée pour le détail et les limites de cette heuristique.

- **Prompt** et **case "écarter le chinois"** : réglages avancés, voir plus bas.

---

# Section avancée

## Installation manuelle / options d'`install.py`

```bash
python install.py --device cpu            # forcer le CPU
python install.py --device cuda           # forcer le build CUDA (NVIDIA)
python install.py --device rocm           # forcer le build ROCm (AMD/Linux)
python install.py --device rocm --rocm-tag rocm7.0   # épingler un tag ROCm précis
```

`install.py` utilise `uv` pour créer `.venv` (Python 3.12) et installer les dépendances
de base depuis `pyproject.toml`, puis installe `torch`/`torchvision` séparément selon le
device détecté/forcé :
- **NVIDIA** → wheels par défaut de PyPI (CUDA embarqué).
- **AMD sous Linux** → `download.pytorch.org/whl/rocmX.Y`. Les tags `rocm6.x` ne
  proposent que d'anciennes versions de torch ; le tag qui correspond à la version
  ciblée par ce projet (`torch==2.10.0`) est **`rocm7.0`** — c'est le premier tag
  essayé. Testé et validé sur une RX 7900 XTX (ROCm système 7.2.4).
- **CPU** → `download.pytorch.org/whl/cpu`.

Le script est idempotent : relancer `python install.py` réutilise le `.venv` existant.

## Architecture du code

```
app/
  device.py         détection device/dtype (torch.cuda.is_available() couvre CUDA ET
                     ROCm, qui exposent tous les deux l'API torch.cuda ; torch.version.hip
                     permet de distinguer les deux pour l'affichage)
  ocr_engine.py      chargement du modèle + réimplémentation "device-agnostic" du
                     chemin d'inférence single-image "gundam" du modèle (voir plus bas)
  config.py          constantes (prompt par défaut, max_new_tokens, etc.)
  video/
    reader.py        lecture vidéo (OpenCV), extraction de frames + timestamps
    filters.py        pipeline de filtres live (upscale, débruitage, CLAHE, contraste,
                       gamma, netteté, seuillage, morphologie, inversion)
    similarity.py     comparaison rapide de deux images (miniature 64x64 en niveaux de
                       gris, différence absolue moyenne)
  subtitles/
    builder.py         regroupe les résultats OCR image-par-image en sous-titres
                        temporisés, avec fusion floue des textes proches (difflib)
    ass_writer.py       écriture du fichier .ass
    lang_filter.py       heuristique de filtrage "probablement chinois"
  formats/
    image_set.py       représentation commune d'un "jeu d'images" (ImageEvent avec
                        horodatage début/fin, ImageSetReader) -- ce que produisent
                        les deux parsers ci-dessous, consommé comme un quasi-VideoReader
    pgs.py              parseur PGS (.sup, sous-titres bitmap Blu-ray) : segments
                        PCS/WDS/PDS/ODS/END, RLE, palette YCbCr -> BGR
    vobsub.py            parseur VobSub (.idx + .sub, sous-titres bitmap DVD) : index
                        texte + démultiplexage MPEG-PS (stream privé 1) + décodage SPU
                        (RLE 2bpp entrelacé pair/impair, zone d'affichage, palette/alpha)
  gui/
    main_window.py     assemble tout, gère le fil d'exécution OCR (QThread), bascule
                        entre mode vidéo et mode image (jeu d'images)
    video_widget.py     lecteur vidéo + zone de rognage
    image_set_widget.py  navigateur d'images (liste + aperçu + rognage) pour le mode
                        image, alternative à video_widget quand la source est un jeu
                        d'images plutôt qu'une vidéo
    crop_rect_item.py   le rectangle rouge redimensionnable (QGraphicsItem custom)
    filter_panel.py     panneau de gauche
    controls_panel.py   panneau de droite
    ocr_worker.py        la boucle qui scanne les frames et appelle l'OCR (voir plus
                        bas) ; ImageSetOcrWorker fait l'équivalent pour un jeu d'images
```

## Comment tourne réellement le pipeline d'analyse (`app/gui/ocr_worker.py`)

Le pipeline **scanne toutes les images de la vidéo**, pas seulement 1 sur N. Pour
chaque image :

1. La zone rognée (rectangle rouge) est extraite en brut (sans les filtres du panneau
   gauche, pour rester rapide).
2. Elle est comparée à la **dernière image sur laquelle l'OCR a réellement tourné**
   (`app/video/similarity.py::DuplicateSkipper`), via une miniature 64x64 en niveaux de
   gris. Ce n'est *pas* nécessairement "l'image précédente" au sens strict, mais "la
   dernière image de référence connue" — la référence n'avance que quand un changement
   est détecté.
3. L'OCR (coûteux, ~1-8s selon le device) ne tourne, par défaut, **que si un
   changement a été détecté à l'étape 2** — aucune exception, aucun appel gaspillé sur
   une image jugée identique. Si la case "Vérification de sécurité périodique" est
   cochée, un appel OCR est aussi forcé toutes les N frames même sans changement
   détecté (voir plus bas pourquoi c'est désactivé par défaut).
4. Si l'OCR tourne, les filtres du panneau gauche sont appliqués *avant* de lui
   envoyer l'image (c'est bien la version filtrée que l'IA voit).

Ce design remplace un ancien design plus simple ("1 image analysée sur N, avec skip
des doublons parmi ces N-là") qui pouvait rater des sous-titres affichés moins de N
images de suite, puisqu'aucune des images échantillonnées ne tombait forcément dedans.

### Seuil de similarité image (skip) — explication détaillée

Le calcul (`app/video/similarity.py`) : on compte la **fraction de pixels qui ont
changé de plus d'un certain seuil brut**, pas une simple différence moyenne. Une
différence moyenne dilue un petit texte à fort contraste (ex. "Oui !" qui n'occupe
qu'une fraction du rectangle rouge) dans une moyenne quasi nulle sur toute l'image —
c'est ce qui causait un vrai bug : des phrases courtes ("Oui !", "Non", "Je vois.")
mesuraient jusqu'à 99 %+ de similarité face à un fond vide avec l'ancienne méthode,
donc **au-dessus du seuil par défaut** → elles étaient sautées avant même d'atteindre
l'OCR, sans erreur ni message. La méthode actuelle reste proche de 100 % pour du
contenu vraiment statique (le bruit de compression pixel par pixel ne franchit pas le
seuil brut, donc ne compte pas), mais chute nettement dès qu'un vrai bloc de texte
apparaît, même petit.

`DuplicateSkipper.should_skip()` saute (= considère comme doublon) une image dès que
`similarité >= seuil`. **Le seuil est donc la barre minimale de ressemblance pour être
traité comme "pareil".** Ce qui donne un effet parfois contre-intuitif :

- **Seuil haut (proche de 100 %)** → barre difficile à atteindre → seules les images
  quasiment identiques (bruit de compression) sont sautées → dedup **prudent**, l'OCR
  tourne souvent → lent mais fiable.
- **Seuil bas** → barre facile à atteindre → dedup **plus agressif**, l'OCR tourne
  moins souvent → plus rapide mais plus de risque de rater de vrais changements.

Exemples mesurés (texte français court, fond uni, avec artefacts JPEG simulés) :

| Similarité mesurée | Situation |
|---|---|
| 100 % | deux images identiques, ou même contenu re-compressé différemment (bruit JPEG) |
| ~90 % | image "vide" vs "Oui !" / "Non" (phrase très courte) qui vient d'apparaître |
| ~80-85 % | image "vide" vs "D'accord" / "Je vois." / "Tu es là ?" |
| ~45-86 % | deux phrases différentes, toutes deux non vides |

D'où le défaut à **99 %** : large marge de sécurité entre "vraiment pareil" (100 %) et
"un texte, même très court, vient d'apparaître" (~90 % ou moins) — contrairement à
l'ancienne méthode où cette marge pouvait être quasi nulle (99,0 % vs 100 %) pour les
phrases très courtes. Cas limite qui reste risqué : un texte d'un seul caractère
("!", ".") isolé peut encore friser les 98-99 % — il y a une limite physique à ce
qu'une mesure de pixels peut distinguer du bruit quand il y a vraiment très peu d'encre
à l'écran.

**Descendre le seuil ne rend pas le dedup "plus prudent" ni "plus sensible aux petites
différences" — c'est l'inverse : ça le rend plus agressif**, au point que la référence
de comparaison peut rester figée sur une image très ancienne pendant longtemps (elle
n'avance que quand une différence dépasse la barre — donc plus la barre est basse,
plus elle avance rarement), et de vrais changements de sous-titre peuvent alors être
classés "pareil".

**Important** : par défaut (case "Vérification de sécurité périodique" décochée), une
image jugée "pareille" par ce seuil n'est **jamais** envoyée à l'OCR, point. Si vous
cochez cette case, vous réintroduisez volontairement des appels OCR périodiques même
sur des passages statiques/vides — dans ce cas, la liste de résultats en direct
regroupe visuellement les lectures identiques consécutives (`... (x12)`) plutôt que de
les dupliquer ligne par ligne, mais l'appel OCR a bien lieu à chaque fois derrière.
Ça n'a de toute façon aucun impact sur le `.ass` final : le texte vide ne crée jamais
de sous-titre (`app/subtitles/builder.py` n'ouvre un "cue" que pour du texte non vide).

**Recommandation** : gardez ce seuil proche du défaut (99 %) sauf raison précise, et
laissez la vérification périodique décochée. Descendez le seuil seulement si votre
vidéo est très bruitée et génère trop de faux "changements" (donc trop d'appels OCR
inutiles) ; montez-le si des textes très brefs sont encore ratés.

### Seuil de fusion des textes similaires — explication détaillée

Contrairement au seuil ci-dessus, celui-ci compare du **texte** (les lectures OCR),
pas des pixels, via `difflib.SequenceMatcher.ratio()` dans `app/subtitles/builder.py`.
Ici, l'intuition normale s'applique : **plus le pourcentage est haut, plus il faut que
les textes soient proches pour être fusionnés.**

Exemples réels (calculés avec `difflib`) :

| Similarité | Paire de textes |
|---|---|
| 100,0 % | `"Bonjour tout le monde"` vs `"Bonjour tout le monde"` |
| 97,7 % | `"Bonjour tout le monde"` vs `"Bonjour tout le monde."` |
| 95,2 % | `"Bonjour tout le monde"` vs `"Bonjour tout le mande"` (1 lettre mal lue) |
| 90,0 % | `"Je t'aime"` vs `"Je t'aime !"` |
| 88,9 % | `"Salut"` vs `"Salu"` |
| 85,7 % | `"Hé !"` vs `"Hé!"` |
| 83,3 % | `"Salut"` vs `"Salut !"` |
| 72,7 % | `"Bonjour tout le monde"` vs `"Au revoir tout le monde"` (vraiment différent) |
| 53,3 % | `"Bonjour tout le monde"` vs `"Bonjour, comment ça va ?"` (vraiment différent) |

Le texte retenu pour le sous-titre fusionné est **la variante la plus fréquente** du
groupe (égalité départagée par la plus longue), pas simplement la première lue.

Défaut : **85 %**. Attention avec les textes très courts ("Salut" vs "Salut !" = 83,3 %)
: au-dessus de ~84 %, ce genre de variante ne fusionne plus — pour du dialogue avec
beaucoup d'exclamations courtes, restez plutôt entre 80 et 85 %, pas plus haut.

## Langue

Le modèle fait de l'OCR multilingue "libre" : il n'y a pas de sélecteur de langue en
dur. Pour le français/japonais occasionnel ça fonctionne nativement. Pour éviter le
chinois (jamais souhaité ici), une heuristique est appliquée (`app/subtitles/lang_filter.py`) :
les idéogrammes CJK sont partagés entre le chinois et les kanjis japonais (même bloc
Unicode), donc impossibles à distinguer à coup sûr. Un bloc de texte contenant des
idéogrammes CJK **sans aucun** kana (hiragana/katakana) ni lettre latine est considéré
comme probablement chinois et écarté. Un bloc avec du kana est gardé (japonais). C'est
une heuristique, pas une garantie absolue.

## Deuxième passe si rien détecté (zoom auto) — explication détaillée

Sur de la vidéo réelle (contrairement à des fonds synthétiques unis utilisés pendant le
développement), il arrive qu'une image correctement signalée comme "changée" par le
dédoublonnage revienne malgré tout **vide** de l'OCR — pas parce qu'il n'y a rien à
lire, mais parce qu'un texte court sur un fond visuellement chargé (cadre photo avec
grain du bois, mur en pierre, etc.) suffit à perturber le modèle. Confirmé sur un vrai
épisode : plusieurs répliques courtes ("Obo ?", "Hamelin !") totalement absentes du
`.ass` alors que le texte était parfaitement lisible à l'œil, alors que le
dédoublonnage avait bien déclenché l'OCR au bon moment — ce n'était donc ni un problème
de seuil de similarité, ni un problème de résolution.

Le mécanisme (`app/video/textbox.py`) :
1. Détecte la zone la plus lumineuse de l'image (le texte est presque toujours plus
   clair que le fond), avec des contraintes de forme pour ignorer les zones lumineuses
   qui ne ressemblent pas à une ligne de texte (rapport largeur/hauteur, hauteur et
   surface maximales) — sans ça, un col de vêtement ou un reflet lumineux quelconque
   pouvait être pris pour du texte et provoquer des résultats aberrants.
2. Rogne serré autour de cette zone (avec une marge), agrandit, et applique un fort
   seuillage de luminosité pour éliminer le fond chargé autour du texte.
3. Relance l'OCR sur cette image "nettoyée".
4. Si le résultat ressemble à du charabia (balises `<|det|>`, `<img>`, `<td>`,
   fragments LaTeX, texte anormalement long...) — un vrai risque quand on force le
   modèle à lire une image binarisée qui ne contient en fait pas de texte — il est
   rejeté et le résultat vide d'origine est conservé plutôt que de créer un faux
   sous-titre.

**Limites connues** : ce n'est pas magique. Sur le cas le plus difficile testé
("Obo ?"), la deuxième passe a récupéré quelque chose (`"050?"`, `"Jlé, Obo !"` selon
la frame) plutôt que de rester muette, mais avec des erreurs de lecture (0/O, 5/b
confondus). Un sous-titre approximatif reste largement préférable à un sous-titre
disparu silencieusement, mais si vous voyez de tels résultats, une relecture manuelle
du `.ass` reste nécessaire sur ces lignes-là.

## Mode image : parseurs PGS/VobSub — détails et limites

`app/formats/pgs.py` et `app/formats/vobsub.py` réimplémentent ces deux formats
bitmap directement depuis leurs spécifications publiques (aucune dépendance externe,
type `ffmpeg`/`mkvextract`, requise pour les lire) :

- **PGS (`.sup`)** : découpe les segments PCS/WDS/PDS/ODS/END, réassemble les objets
  fragmentés (>64 Ko), décode le RLE palette-indexée et convertit la palette YCbCr en
  BGR (conversion pleine plage, approximation courante pour ce format). La fin
  d'affichage d'un sous-titre est déduite de la composition suivante (image ou écran
  vide), comme le fait le format lui-même.
- **VobSub (`.idx` + `.sub`)** : lit l'index texte (taille, palette 16 couleurs,
  horodatages + positions octet), démultiplexe le flux MPEG-PS (paquets PES du flux
  privé 1) à chaque position, puis décode le paquet SPU (RLE 2 bits/pixel, entrelacé
  pair/impair, zone d'affichage, palette/contraste par sous-titre). La commande
  `STP_DSP` du flux de contrôle donne la fin réelle d'affichage quand elle est
  présente ; sinon l'horodatage du sous-titre suivant sert d'approximation.

**Limites connues** : les deux parseurs ont été validés par des tests de bout en bout
sur des flux synthétiques construits à la main (segments/paquets fabriqués pour
couvrir chaque chemin de code), pas sur des fichiers réels issus de tous les
mixeurs/graveurs existants — des variantes rares du format (objets PGS multiples par
composition avec zones qui se chevauchent, options `.idx` non standard, etc.) peuvent
nécessiter des ajustements. Un fichier malformé ou non reconnu affiche une erreur
plutôt que de planter l'application.

## Notes techniques / limites connues sur le modèle Unlimited-OCR

- `models/Unlimited-OCR/modeling_unlimitedocr.py` (code fourni par Baidu) code en dur
  `.cuda()`. `app/ocr_engine.py` **ré-implémente** la passe d'inférence "gundam" (image
  unique) de façon agnostique au device, en réutilisant les fonctions utilitaires du
  module chargé dynamiquement par `transformers` (aucune modification du fichier
  vendor). Sur CPU, l'inférence reste fonctionnelle mais lente (~3.3 milliards de
  paramètres) — attendez-vous à un OCR par frame de plusieurs secondes.
- Le loader dynamique de `transformers` exige `matplotlib` installé (scan statique des
  imports du fichier vendor), même s'il n'est utilisé que dans une branche de code
  jamais atteinte par ce projet.
- **`max_new_tokens` plutôt que `max_length`** : le `infer()` d'origine utilise
  `max_length` (budget prompt+sortie). Pour des crops déclenchant `dynamic_preprocess`
  (>640px sur un axe → ajoute des tokens de "crops locaux"), l'entrée seule peut
  dépasser un `max_length` mal dimensionné et faire planter `generate()`. On utilise
  `max_new_tokens` (256 par défaut), qui ne borne que la sortie et est insensible à la
  taille d'entrée.
- **La sortie du modèle est toujours encapsulée** dans des balises
  `<|det|>catégorie [bbox]<|/det|>`, même avec le prompt `"Free OCR."`.
  `app/ocr_engine.py::strip_det_markup()` les retire avant de renvoyer le texte.
- **Piège de précision sur les petits crops** : une image ≤ 640px sur ses deux côtés ne
  reçoit que la vue basse résolution du modèle (pas de tuiles "crop local") et a été
  observée à tronquer le texte de façon reproductible (ex. "en français." → coupé à
  "en f"). Agrandir le même crop au-delà de 640px sur son plus grand côté (déclenchant
  les crops locaux) corrige totalement ce problème dans tous les tests effectués —
  c'est pourquoi le filtre "Agrandir (upscale)" est **activé par défaut** (facteur 2.0)
  dans le pipeline. Le désactiver risque de tronquer silencieusement les sous-titres
  issus de petits rectangles de rognage.
- Le seek vidéo (`cv2.CAP_PROP_POS_FRAMES`) peut être imprécis sur certains conteneurs
  à *frame rate variable* ; en usage normal (VOD à fps constant) ça reste fiable.
- **Batching (`app/ocr_engine.py::ocr_images_batch`)** : le modèle supporte
  structurellement un batch > 1 côté transformer (`UnlimitedOCRModel.forward` itère
  `zip(images, images_spatial_crop)` par élément du batch), donc on construit un batch
  de séquences *left-padded* à une longueur commune (technique standard pour la
  génération causale par batch) et un seul `generate()` traite tout le batch. Mesuré
  ~2,5x plus rapide par image (batch=8) sur ROCm/RX 7900 XTX, 0/8 divergences vs séquentiel.
  Attention : les encodeurs visuels (SAM ViT-B + CLIP-L) tournent quand même **en boucle
  Python, un échantillon à la fois** à l'intérieur du forward — seule la partie
  décodage du transformer (DeepSeek-V2) bénéficie du vrai batching. Comme la génération
  par batch continue jusqu'à ce que le plus long échantillon finisse, les échantillons
  plus courts reçoivent des tokens EOS/pad en trop après leur propre fin ; le décodage
  tronque donc chaque ligne à sa **propre première occurrence du token EOS** plutôt que
  de vérifier juste un suffixe `STOP_STR`, sinon les textes plus courts que le plus
  long du batch ressortent avec du bruit de padding à la fin.
