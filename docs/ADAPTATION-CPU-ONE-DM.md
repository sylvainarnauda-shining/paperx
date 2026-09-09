# One-DM sur CPU (ou MPS) : analyse ciblée

Analyse **statique** du dépôt `dailenson/One-DM` au commit
`dde2205a70a2c70d1786503d198a795358c80ee4`. Aucun code tiers n'a été exécuté,
aucun poids téléchargé, aucun modèle instancié. Rien ici ne promet qu'une
inférence CPU soit rapide, ni même possible : le but est de savoir **ce qu'il
faudrait changer**, et **ce qui empêche encore d'essayer**.

Aucun GPU payant n'est supposé nécessaire, et aucun n'est recommandé à ce stade :
tant que les poids sont inaccessibles, la question du matériel ne se pose pas.

## 1. Ce dont une inférence « un mot » a réellement besoin

Le chemin de test (`test.py`) est nettement plus court que ce que le README
laisse croire.

| Artefact | Requis pour un mot ? | Source |
|---|---|---|
| Point de contrôle One-DM (`--one_dm`) | **oui** | `test.py:68` |
| VAE de stable-diffusion-v1-5 (`--stable_dif_path`) | **oui**, en décodage seul | `test.py:74`, `diffusion.py:147` |
| Poids ImageNet de torchvision `resnet18` | **oui, ×3, à la construction** | `fusion.py:56` et `fusion.py:64` (appelée deux fois) |
| `data/unifont.pickle` (images de contenu) | **oui** | `loader.py:get_symbols` |
| Une image de style + son laplacien | **oui** | `Random_StyleIAMDataset` |
| Un fichier corpus listé dans `generate_type` | **oui** | `loader.py:19`, `test.py:29` |
| `RN18_class_10400.pth` | non | `train.py --feat_model` seulement |
| `vae_HTR138.pth` | non | `train_finetune.py --ocr_model` seulement |

Deux des trois poids annoncés dans le « Model Zoo » ne servent donc **pas** à
générer un mot. En revanche un quatrième téléchargement, absent du README,
est exigé : les poids ImageNet de `resnet18`, tirés de `download.pytorch.org`.

Taille du calcul, dérivée de `test.py:98` : pour un mot de *n* caractères, le
latent vaut `1 × 4 × 8 × 4n` et l'image décodée `64 × 32n` pixels — 512 valeurs
latentes pour « dawn », 1 408 pour « handwriting ». L'échantillonnage DDIM par
défaut fait **50 passes du UNet** plus **un décodage VAE**.

## 2. Appels CUDA / NCCL sur le chemin de test

| Fichier:ligne | Appel | Effet sur CPU |
|---|---|---|
| `test.py:11` | `import torch.distributed as dist` | inoffensif |
| `test.py:22` | `dist.init_process_group(backend='nccl')` | **échec** : NCCL exige un GPU |
| `test.py:23` | `local_rank = dist.get_rank()` | échec en cascade |
| `test.py:24` | `torch.cuda.set_device(local_rank)` | **échec** : aucun contexte CUDA |
| `test.py:27`, `32-39` | `dist.get_world_size()`, découpe du corpus par rang | échec en cascade |
| `test.py:52-53` | `num_workers=8`, `pin_memory=True` | fonctionne, mais avertissement et surcoût inutiles pour un lot de 1 |
| `test.py:125` | `--device` par défaut `'cuda'` | à passer en `cpu` |

`--device cpu` existe donc déjà, mais **n'est jamais atteint** : les lignes 22-24
s'exécutent avant toute prise en compte de l'option.

Hors chemin de test, et sans effet ici : `train.py`, `train_finetune.py`,
`trainer/trainer.py` (`dist.*`, `torch.cuda.empty_cache()`), et
`models/loss.py:28` (`torch.device('cuda') if features.is_cuda`), qui n'est
utilisé qu'à l'entraînement.

## 3. Ce qui est déjà neutre vis-à-vis du périphérique

Bonne surprise, et elle réduit beaucoup l'ampleur du correctif :

- **aucun `.cuda()` en dur** dans tout le dépôt (0 occurrence) ;
- `utils/util.py:11` teste `torch.cuda.is_available()` avant d'y toucher ;
- `test.py:68` charge le point de contrôle avec `map_location='cpu'` ;
- `unet.py:767` : `self.dtype` vaut `float32` car `use_fp16=False` par défaut et
  `test.py` ne le change pas — pas de demi-précision à gérer ;
- `Diffusion.__init__` place ses tampons sur le `device` reçu ; passer `'cpu'`
  est cohérent de bout en bout ;
- `diffusion.py:150` ramène déjà l'image sur CPU avant conversion.

## 4. Changements minimaux

Cinq modifications, toutes dans `test.py`, aucune dans les modèles. **Non
appliquées et non testées** : elles ne peuvent pas l'être sans point de contrôle.

1. **Lignes 22-24** — n'initialiser le mode distribué que s'il est réellement
   demandé :

   ```python
   distribue = opt.device.startswith("cuda") and "WORLD_SIZE" in os.environ
   if distribue:
       dist.init_process_group(backend="nccl")
       local_rank = dist.get_rank()
       torch.cuda.set_device(local_rank)
   else:
       local_rank = 0
   ```

2. **Lignes 27 et 32-39** — en mono-processus, `totol_process = 1`,
   `temp_texts = texts`, sans découpe par rang.
3. **Ligne 125** — `--device` par défaut `'cpu'`, ou passer `--device cpu`
   explicitement une fois le point 1 corrigé.
4. **Lignes 52-53** — `num_workers=0` et `pin_memory=False` hors CUDA.
5. **Lancement** — `python3 test.py …` au lieu de `torchrun --nproc_per_node=4`.

Pour MPS (Apple), les mêmes changements plus une vérification à faire sur
machine : les tenseurs de pas de temps sont en `int64` (`diffusion.py:120-121`)
et le support MPS des entiers 64 bits dépend de la version de torch. À
constater, pas à supposer.

## 5. Obstacles réels, du plus bloquant au moins

1. **Rien à exécuter.** Point de contrôle One-DM et VAE restent inaccessibles
   (voir `docs/EXPERIENCE-PHOTO-VERS-TEXTE.md`). Le correctif ci-dessus est donc
   pour l'instant du code que personne ne peut faire tourner.
2. **`download.pytorch.org` est bloqué ici** (`000` au CONNECT). Or
   `fusion.py:56` et `fusion.py:64` demandent `ResNet18_Weights.DEFAULT` **à la
   construction du modèle**, avant même le chargement du point de contrôle. Deux
   contournements, tous deux à vérifier :
   - pré-remplir le cache torch hub (`TORCH_HOME`) avec le fichier ImageNet ;
   - passer `weights=None`. `load_state_dict` écrase ensuite ces paramètres, donc
     l'initialisation ImageNet est *probablement* sans effet à l'inférence —
     **probablement n'est pas vérifié** : seul un `load_state_dict(..., strict=True)`
     réussi avec le vrai point de contrôle le prouvera. Ne pas modifier ces
     lignes sur une intuition.
3. **`data/unifont.pickle` est absent du dépôt** : il vient de l'archive de jeu
   de données, hébergée sur les mêmes hôtes bloqués. Sans lui, `ContentData`
   échoue avant tout calcul.
4. **Aucun prétraitement laplacien n'est fourni.** Une photo réelle doit être
   découpée en mots de 64 px de haut et plus de 128 px de large, et chaque image
   doit avoir son laplacien de même nom dans un dossier parallèle.
5. **Pile Python.** Le couple épinglé `torch 1.13.1` / `torchvision 0.14.1` n'a
   pas de roue Python 3.11 côté torchvision ; les dépôts visent Python 3.8.
6. **Coût de calcul inconnu.** Le latent est minuscule, mais la taille du UNet ne
   l'est pas forcément, et elle n'est pas établie : la mesurer exigerait
   d'instancier du code tiers, ce que cette analyse s'interdit. 50 passes UNet
   par mot sur 4 cœurs peut aussi bien prendre quelques secondes que plusieurs
   minutes. **Aucun chiffre n'est avancé ici.**

## 6. Ce que cette analyse ne dit pas

Elle ne dit pas qu'une inférence CPU réussira, ni combien de temps elle prendra,
ni que le résultat ressemblera à l'écriture de référence. Elle ne dit rien non
plus du français : l'alphabet publié reste celui de 81 caractères, et les
9 caractères impossibles de la phrase témoin française le restent quel que soit
le périphérique de calcul.

## 7. Prochain pas mesurable

Dès qu'un point de contrôle et le VAE sont en main, deux mesures d'une ligne
chacune, dans cet ordre :

1. `load_state_dict(torch.load(ckpt, map_location="cpu"), strict=True)` sur un
   `UNetModel` construit avec `weights=None` : réussit ou échoue, ce qui tranche
   l'obstacle 2 sans discussion ;
2. chronométrer une génération d'un mot ASCII témoin, 50 pas DDIM, sur CPU :
   ce chiffre décide seul si la voie CPU est praticable.

Tant que ces deux mesures ne sont pas faites, toute affirmation sur la
faisabilité CPU serait une supposition.
