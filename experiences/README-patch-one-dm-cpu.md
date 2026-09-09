# Correctif One-DM : démarrage mono-processus, sans NCCL ni CUDA

`test.py` de One-DM appelle `dist.init_process_group(backend='nccl')` puis
`torch.cuda.set_device()` **sans condition**, avant toute lecture de `--device`.
L'option `--device cpu` existe donc dans le code mais n'est jamais atteinte.

Ce correctif n'active le mode multi-GPU que s'il est réellement demandé —
périphérique CUDA **et** variable `WORLD_SIZE` définie, ce que fait `torchrun`.
La voie CUDA distribuée existante est inchangée. Aucun autre fichier n'est
touché.

**Il ne démontre aucune inférence réussie.** Il ne traite que le démarrage.

## Cible stricte

| | |
|---|---|
| dépôt | https://github.com/dailenson/One-DM |
| commit | `dde2205a70a2c70d1786503d198a795358c80ee4` |
| blob `test.py` | `cde1922c4362f20ec096cd0233e122c332dcc281` |

L'applicateur refuse tout autre commit, tout autre blob, et tout clone modifié.
Aucun dépôt public supplémentaire n'est créé, aucune copie du code amont n'est
versionnée ici : seul le différentiel l'est.

## La commande

```bash
python3 experiences/appliquer_patch_one_dm_cpu.py --clone <chemin-du-clone> --appliquer
```

Sans `--appliquer`, seules les vérifications tournent et rien n'est écrit.
Retour arrière : `git -C <chemin-du-clone> checkout -- test.py`.

Obtenir le clone (aucun poids n'est téléchargé par cette commande) :

```bash
GIT_LFS_SKIP_SMUDGE=1 git clone https://github.com/dailenson/One-DM <chemin-du-clone>
git -C <chemin-du-clone> checkout dde2205a70a2c70d1786503d198a795358c80ee4
```

Tests : `python3 experiences/test_patch_one_dm_cpu.py`
(variable `ONE_DM_CLONE` pour désigner le clone ; les tests qui en dépendent
sont **ignorés** avec un message si le clone est absent, jamais remplacés par un
faux dépôt qui simulerait une réussite).

## Vérifié

- Le correctif s'applique au commit exact (`git apply`), et le fichier obtenu
  est **syntaxiquement valide** — contrôlé par `compile()` en mémoire, sans
  aucun import ni exécution du code amont, sans écriture de `.pyc`.
- Une version divergente et un clone modifié sont refusés **sans qu'un seul
  octet ne change**.
- **Simulation** : la fonction ajoutée par le correctif est extraite du fichier
  corrigé par analyse syntaxique, puis exécutée seule avec des doublures à la
  place de `torch` et `torch.distributed`. En mono-processus (`cpu`, `mps`, ou
  `cuda` sans `WORLD_SIZE`), **aucun appel NCCL ni CUDA** n'est émis et le
  résultat est `(0, 1, False)`. En `cuda` avec `WORLD_SIZE`,
  `init_process_group(backend='nccl')` puis `cuda.set_device(rang)` sont bien
  appelés dans cet ordre, et le résultat est `(rang, taille, True)`.
- L'applicateur n'importe aucun module réseau et ne lance que des commandes
  `git` locales — vérifié par analyse syntaxique de son propre source.

## Non testé, et pas démontré

- **Aucune inférence.** Ni image générée, ni mot écrit, ni ressemblance de
  style. Aucun poids n'a été téléchargé, aucun modèle instancié.
- **Le comportement réel du fichier corrigé sous torch** : il n'a jamais été
  importé. `compile()` prouve la syntaxe, pas l'exécution.
- **La suite du démarrage.** Après ce correctif, l'exécution progresse jusqu'aux
  besoins suivants, tous inchangés : point de contrôle One-DM, VAE
  stable-diffusion-v1-5, `data/unifont.pickle`, images de style et laplaciennes,
  et trois demandes de poids ImageNet à `download.pytorch.org` faites à la
  construction du modèle (`fusion.py:56` et `:64`).
- **MPS (Apple)** : le correctif rend `--device mps` atteignable au démarrage,
  rien de plus. Les tenseurs de pas de temps sont en `int64`
  (`diffusion.py:120-121`) ; le support MPS correspondant dépend de la version
  de torch et reste à constater sur machine.
- **Hors périmètre volontaire** : `pin_memory=True` et `num_workers=8`
  (`test.py:52-53`) restent tels quels. Sur CPU, `pin_memory` produit un
  avertissement mais ne bloque pas.
- **Le nombre de paramètres du UNet**, donc le coût d'un mot en 50 pas DDIM.
  L'établir demanderait d'instancier le modèle, ce que ce travail s'interdit.

Une génération réelle reste à faire, avec des artefacts et une licence
d'usage vérifiés.

## Licence

Le correctif modifie du code publié sous licence MIT par Gang Dai (One-DM,
© 2024) et est lui-même distribué sous licence MIT.
