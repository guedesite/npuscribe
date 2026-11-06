# NPUScribe

Dictée vocale locale pour Windows, **exécutée sur le NPU Intel**.
Remplace un service de dictée en ligne : la combinaison de touches lance
l'écoute, la parole est transcrite au fil de l'eau, et le texte est collé au
curseur.

Rien ne passe par le GPU. Le CPU ne fait que recopier des blocs audio de 20 ms.

## Matériel mesuré

Intel Core Ultra 7 265K (Arrow Lake-S), NPU 3 « Intel AI Boost », pilote
32.0.100.5540, OpenVINO 2026.4.1.

| Modèle | RAM | Vitesse | Quantification |
|---|---|---|---|
| **whisper-large-v3-turbo FP16** (retenu) | **3,6 Go** | 1,5 s pour 20 s d'audio | **aucune** |
| whisper-large-v3-turbo INT4 | 4,2 Go | 3,3 s | int4 |
| whisper-large-v3 INT8 | — | — | rejeté par le NPU (`ZE_RESULT_ERROR_INVALID_NATIVE_BINARY`) |
| whisper-large-v3 FP16 | — | — | rejeté par le NPU (même erreur) |

La variante int4 est à la fois **plus lente et plus gourmande** que le FP16 :
la quantification n'apporte rien ici, d'où le choix du FP16.

Qualité : 10,7 % de mots différents du `large-v3` FP16 de référence sur un
enregistrement français de 17 minutes, l'essentiel de l'écart étant de la
ponctuation et de la paraphrase, pas des erreurs de reconnaissance.

## Installation

### L'installateur (recommandé)

Télécharger `NPUScribe-Setup-x.y.z.exe` depuis les *Releases* GitHub et le
lancer. Installation **par utilisateur**, sans droits administrateur :

- programme dans `%LOCALAPPDATA%\Programs\NPUScribe` ;
- raccourcis dans le menu Démarrer, désinstalleur dans « Applications et
  fonctionnalités » ;
- lancement automatique à l'ouverture de session (décochable dans l'assistant
  et dans le menu de l'icône) ;
- au premier lancement, le modèle (1,6 Go) est téléchargé puis compilé pour le
  NPU — cinq à huit minutes, une seule fois. Les lancements suivants prennent
  trois secondes.

Données, modèle, cache et historique vivent dans `%LOCALAPPDATA%\NPUScribe`.
La désinstallation propose de les supprimer.

### Depuis les sources

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe tools\fetch_model.py     # télécharge le modèle
.venv\Scripts\python.exe tools\warmup.py          # compile pour le NPU (5-8 min)
.venv\Scripts\pythonw.exe run.pyw
```

### Intégration continue

`.github/workflows/build.yml` construit l'exécutable et l'installateur à chaque
poussée sur `main`, et les publie dans une *Release* quand un tag `v*` est
poussé. Binaires produits : `dist\NPUScribe\` (dossier autonome) et
`dist_installer\NPUScribe-Setup-<version>.exe`.

En local, la même chaîne :

```bash
python tools\make_icon.py
pyinstaller NPUScribe.spec --noconfirm
"C:\Program Files\Inno Setup 7\ISCC.exe" installer\npuscribe.iss
```

## Utilisation

```bash
.venv\Scripts\pythonw.exe run.pyw
```

La combinaison par défaut est **Ctrl + Win**.

| Geste | Effet |
|---|---|
| maintenir la combinaison | dicte tant que les touches restent enfoncées |
| double appui | passe en **écoute continue**, les touches peuvent être lâchées |
| nouvel appui en continu | arrête et insère le texte |
| `Échap` pendant l'écoute | annule, rien n'est inséré |

À l'arrêt, le texte est copié et collé au curseur ; le presse-papier précédent
est restauré. La pastille en bas de l'écran montre l'onde, la transcription en
cours, et signale **« Aucun son »** si le micro choisi ne capte rien.

L'icône de la zone de notification donne accès à l'historique, au diagnostic,
au choix du micro, aux réglages, au lancement automatique et à la fermeture.
Son infobulle reflète l'état courant (prêt, écoute, transcription).

## Historique

Chaque dictée est conservée dans `history.jsonl` avec sa date, sa durée, la
langue et le micro utilisé. La fenêtre **Historique…** permet de rechercher,
relire, **copier** une transcription, la **recoller au curseur** dans
l'application active, ou la supprimer.

## Diagnostic

La fenêtre **Diagnostic…** affiche en direct : micro utilisé, état (prêt,
écoute, maintien), modèle chargé, raccourci actif, latence de la dernière
transcription, niveau du micro et dernière transcription produite. C'est le
moyen de vérifier d'un coup d'œil que la chaîne complète fonctionne.

## Réglages

`config.json`, créé au premier lancement, ou l'entrée « Paramètres… » du menu.

| Clé | Rôle |
|---|---|
| `hotkey` | combinaison globale, ex. `ctrl+win`, `ctrl+alt+space` |
| `input_device` | nom du micro ; vide = périphérique Windows par défaut |
| `language` | `fr`, `en` ou `auto` |
| `dictionary` | termes à privilégier (appliqués en post-traitement) |
| `replacements` | corrections déterministes, insensibles à la casse |
| `silence_ms` | silence qui clôt une phrase |
| `max_chunk_s` | durée maximale d'un segment envoyé au NPU |
| `paste_mode` | `ctrl+v` ou `ctrl+shift+v` pour les terminaux |
| `autostart` | lancement à l'ouverture de session |

## Coût mesuré

Processus complet (modèle chargé, pastille, crochet clavier), mesuré sur la
machine ci-dessus :

| Situation | CPU | RAM |
|---|---|---|
| Au repos | **0,000 %** d'un cœur | 3,6 Go |
| Pendant l'écoute | **0,94 %** d'un cœur | 3,6 Go |
| Coût d'une frappe quelconque | **20 µs** | — |

La pastille coûte 0,38 ms par image : le fond et le texte sont mis en cache,
seules les barres de l'onde sont recalculées, sur une bande de 96 pixels.

## Comment ça marche

```
crochet clavier (WH_KEYBOARD_LL)
        │
        ▼
capture micro 16 kHz ──► segmentation (VAD énergie, 20 ms)
        │                         │
        │                         ▼
        │                 segments ≤ 24 s
        ▼                         ▼
  pastille (GDI)  ◄──── Whisper FP16 sur NPU
                                  │
                                  ▼
                 presse-papier + Ctrl+V (SendInput)
```

- **Aucun framework graphique au repos.** La pastille est une fenêtre en
  couches Win32 dessinée dans un DIB 32 bits ; le texte est rendu par GDI puis
  composé en alpha.
- **Crochet clavier plutôt que `RegisterHotKey`.** Windows se réserve
  Ctrl+Win, que `RegisterHotKey` refuse d'enregistrer ; un crochet bas niveau
  accepte n'importe quelle combinaison et ne s'exécute qu'à la frappe. Si le
  crochet ne peut pas être installé, le code retombe sur une scrutation à
  30 Hz (`GetAsyncKeyState`).
- **Découpage intelligent.** Le segment se ferme sur un silence réel, jamais
  au milieu d'un mot, et la transcription commence avant que vous ayez fini de
  parler. Une dictée longue ne s'accumule pas en mémoire : seuls le segment
  courant et le texte produit sont conservés.

## Limites connues

- `Ctrl+V` n'est pas honoré par certains terminaux et applications élevées ;
  `paste_mode` accepte `ctrl+shift+v` pour ces cas.
- Les segments sont transcrits indépendamment : sans contexte des phrases
  précédentes, un homophone isolé peut être mal choisi.
- `large-v3` complet et sa variante int8 ne s'exécutent pas sur ce NPU ;
  `turbo` est le plafond matériel.

## Pièges du NPU, déjà traités dans le code

Ces trois défauts d'`openvino_genai` coûtent des heures si on ne les connaît
pas ; ils sont contournés explicitement dans `wispr/asr.py`.

1. **`return_timestamps=True` est obligatoire.** Sans lui, le pipeline renvoie
   une chaîne vide sur une fraction importante des entrées (13 % des segments
   de référence). Le chemin « notimestamps » a une porte anti-parole
   défaillante.
2. **Une entrée de 30,0 s pile renvoie du vide.** Le contenu est donc plafonné
   à 24 s.
3. **`hotwords` et `initial_prompt` font échouer l'inférence sur NPU**
   (`infer_request`), silencieusement côté texte. Le dictionnaire passe par un
   remplacement déterministe après transcription.

## Licence

Apache 2.0 — voir `LICENSE`.
