# NPUScribe

[![build](https://github.com/guedesite/npuscribe/actions/workflows/build.yml/badge.svg)](https://github.com/guedesite/npuscribe/actions/workflows/build.yml)
[![licence](https://img.shields.io/badge/licence-Apache--2.0-blue.svg)](LICENSE)

**Dictée vocale locale pour Windows, exécutée sur le NPU Intel.**
Aucun cloud, aucune clé API, aucun passage sur le GPU. Vous parlez, le texte
arrive au curseur.

![La pastille pendant l'écoute](assets/pastille.png)

## Ce que ça fait

- **Maintien pour parler, double appui pour l'écoute continue.** La combinaison
  de touches est configurable (`Ctrl + Win` par défaut).
- **Transcription au fil de l'eau.** Le texte apparaît pendant que vous parlez,
  pas après. Une dictée longue ne s'accumule pas en mémoire.
- **Collage au curseur.** Le texte est copié puis collé dans l'application
  active, et le presse-papier précédent est restauré.
- **Historique.** Chaque dictée est conservée ; on peut la rechercher, la
  relire, la recopier ou la recoller.
- **Dictionnaire.** Vos noms propres et vos tournures, appliqués après
  transcription.
- **Choix du micro** et **diagnostic** en direct : niveau du signal, latence,
  état du modèle.

## Prérequis

- Windows 11 sur **Intel Core Ultra** avec NPU « Intel AI Boost » et son
  pilote à jour.
- Environ 6 Go d'espace disque (modèle 1,6 Go + cache de compilation 2,2 Go +
  programme 352 Mo).
- Une connexion internet au premier lancement, pour télécharger le modèle.

Sans NPU, l'application ne peut pas fonctionner : c'est le principe, pas une
option.

## Installation

Télécharger `NPUScribe-Setup-x.y.z.exe` dans les
[Releases](https://github.com/guedesite/npuscribe/releases), ou dans les
artefacts de la
[dernière exécution](https://github.com/guedesite/npuscribe/actions/workflows/build.yml)
de la CI.

L'installateur ne demande **aucun droit administrateur** :

| | |
|---|---|
| Programme | `%LOCALAPPDATA%\Programs\NPUScribe` |
| Données, modèle, cache, historique | `%LOCALAPPDATA%\NPUScribe` |
| Raccourcis | menu Démarrer (bureau en option) |
| Désinstallation | « Applications et fonctionnalités », avec proposition de supprimer aussi les ~4 Go de données |

Le lancement automatique à l'ouverture de session est activé par défaut et
peut être décoché dans l'assistant comme dans le menu de l'icône.

> L'installateur n'est pas signé. Windows affichera « Windows a protégé votre
> PC » au premier lancement : *Informations complémentaires* → *Exécuter quand
> même*.

### Premier démarrage

Le modèle (1,6 Go) est téléchargé puis compilé pour le NPU. **Comptez cinq à
huit minutes, une seule fois** — la pastille indique où elle en est. Les
lancements suivants prennent trois secondes.

## Utilisation

La combinaison par défaut est **Ctrl + Win**.

| Geste | Effet |
|---|---|
| maintenir la combinaison | dicte tant que les touches restent enfoncées |
| double appui | passe en **écoute continue** : vous pouvez lâcher les touches |
| nouvel appui en continu | arrête et insère le texte |
| `Échap` pendant l'écoute | annule, rien n'est inséré |

La pastille en bas de l'écran montre l'onde et la transcription en cours. Si le
micro choisi ne capte rien, elle passe au rouge et nomme le périphérique.

L'icône de la zone de notification donne accès à l'historique, au diagnostic,
au choix du micro, aux réglages, au lancement automatique et à la fermeture.
Son infobulle reflète l'état courant.

## Réglages

`%LOCALAPPDATA%\NPUScribe\config.json`, créé au premier lancement, ou l'entrée
« Paramètres… » du menu.

| Clé | Rôle |
|---|---|
| `hotkey` | combinaison globale, ex. `ctrl+win`, `ctrl+alt+space` |
| `input_device` | nom du micro ; vide = périphérique Windows par défaut |
| `language` | `fr`, `en` ou `auto` |
| `dictionary` | termes à privilégier |
| `replacements` | corrections déterministes, insensibles à la casse |
| `silence_ms` | silence qui clôt une phrase (650 ms par défaut) |
| `max_chunk_s` | durée maximale d'un segment envoyé au NPU |
| `paste_mode` | `ctrl+v`, ou `ctrl+shift+v` pour les terminaux |
| `autostart` | lancement à l'ouverture de session |

## Sous le capot

```
crochet clavier (WH_KEYBOARD_LL)
        │
        ▼
capture micro 16 kHz ──► segmentation (VAD énergie, trames de 20 ms)
        │                         │
        │                         ▼
        │                 segments ≤ 24 s
        ▼                         ▼
  pastille (GDI)  ◄──── Whisper large-v3-turbo FP16 sur NPU
                                  │
                                  ▼
                 presse-papier + Ctrl+V (SendInput)
```

Le module d'inférence est OpenVINO GenAI. Le modèle est
`whisper-large-v3-turbo` en **FP16, sans aucune quantification** : la variante
int4 est à la fois plus lente et plus gourmande en mémoire sur cette puce.

## Coût mesuré

Intel Core Ultra 7 265K (Arrow Lake-S), NPU 3, pilote 32.0.100.5540,
OpenVINO 2026.4.1.

| Situation | CPU | RAM |
|---|---|---|
| Au repos | **0,000 %** d'un cœur | 3,6 Go |
| Pendant l'écoute | **1,6 %** d'un cœur | 3,6 Go |
| Coût d'une frappe clavier | **20 µs** | — |
| Une image de pastille | **0,38 ms** | — |

Après la toute première compilation, la mémoire du compilateur NPU n'est pas
rendue au système : comptez 4,6 Go jusqu'au redémarrage suivant.

## Limites connues

- `Ctrl+V` n'est pas honoré par certains terminaux et applications élevées ;
  `paste_mode` accepte `ctrl+shift+v` pour ces cas.
- Les segments sont transcrits indépendamment : sans le contexte des phrases
  précédentes, un homophone isolé peut être mal choisi.
- `large-v3` complet et sa variante int8 sont **rejetés par ce NPU** ; `turbo`
  est le plafond matériel.
- L'installateur n'est pas signé.

## Développement

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt

.venv\Scripts\python.exe tools\fetch_model.py     # modèle OpenVINO
.venv\Scripts\python.exe tools\warmup.py          # compilation NPU (5-8 min)
.venv\Scripts\pythonw.exe run.pyw                 # depuis les sources
```

| Outil | Rôle |
|---|---|
| `tools/selftest.py` | bout en bout sans micro : un WAV tient lieu de flux audio |
| `tools/make_icon.py` | régénère `assets/app.ico` |
| `tools/warmup.py` | précompile le modèle pour le NPU |
| `research/` | sondes matérielles et mesures qui ont guidé les choix |

### Construire l'installateur

```bash
python tools\make_icon.py
pyinstaller NPUScribe.spec --noconfirm
"C:\Program Files\Inno Setup 7\ISCC.exe" installer\npuscribe.iss
```

`.github/workflows/build.yml` enchaîne ces étapes à chaque poussée sur `main`
et publie l'installateur en artefact. Pousser un tag `v*` attache l'installateur
à une Release.

## Pièges du NPU, déjà traités

Trois défauts d'`openvino_genai` coûtent des heures si on ne les connaît pas ;
ils sont contournés dans `wispr/asr.py`.

1. **`return_timestamps=True` est obligatoire.** Sans lui, le pipeline renvoie
   une chaîne vide sur une fraction importante des entrées (13 % des segments
   de référence).
2. **Une entrée de 30,0 s pile renvoie du vide.** Le contenu est plafonné à
   24 s.
3. **`hotwords` et `initial_prompt` font échouer l'inférence** sur NPU,
   silencieusement côté texte. Le dictionnaire passe par un remplacement
   déterministe après transcription.

## Licence

Apache 2.0 — voir [LICENSE](LICENSE).
