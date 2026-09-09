# Première expérience réelle : photo manuscrite → NOUVEAU texte

Objet borné : choisir **une** voie expérimentale pour produire, à partir d'une
photo d'écriture autorisée, un **texte nouveau** (pas une vectorisation du texte
photographié), et dire précisément ce qui est exécutable aujourd'hui et ce qui
ne l'est pas.

Ce document ne revendique aucune personnalisation. Aucun modèle n'a été exécuté.

## 1. Voie retenue et voie écartée

| Candidat | Ce qu'il produit | Décision |
|---|---|---|
| **One-DM** (ECCV 2024) | image raster d'un **mot** isolé, style imité depuis **une** référence | **Retenu** pour la première expérience : une seule photo suffit en entrée |
| **DiffBrush** (ICCV 2025) | image raster d'une **ligne** entière, `NUM_IMGS: 15` références | Deuxième étape : plus proche d'une page, mais exige 15 échantillons du même scripteur |

Les deux viennent du même auteur (Gang Dai) et partagent la même architecture
de diffusion latente et le même VAE externe. Écarter l'un ne change rien aux
blocages ci-dessous : ils sont communs.

## 2. Sources vérifiables

Relevé le 2026-09-09 par clone superficiel du dépôt public, sans exécution du
code tiers.

| Dépôt | Commit épinglé | Licence du code | Poids |
|---|---|---|---|
| [dailenson/One-DM](https://github.com/dailenson/One-DM) | `dde2205a70a2c70d1786503d198a795358c80ee4` (2025-10-15) | MIT (`LICENSE`, © 2024 Gang Dai) | hors dépôt : Google Drive / Baidu / wisemodel.cn |
| [dailenson/DiffBrush](https://github.com/dailenson/DiffBrush) | `da9addc1140bdfec463b2d41a974a0a392f80798` (2025-11-24) | MIT (`LICENSE`, © 2025 Gang Dai) | hors dépôt : Google Drive / Baidu |

Contrôle croisé avec la preuve du coordinateur (PR #1) : le blob de
`data_loader/loader.py` au commit ci-dessus vaut
`6ccae081d4694fbdf77b5dbc03f4b9579132852e`, **identique** à celui inspecté
séparément. Le constat sur l'alphabet est donc reproductible sur la même source.

**La licence MIT porte sur le code, pas sur les poids.** Aucun des deux dépôts
n'énonce de licence pour les points de contrôle pré-entraînés, distribués
ailleurs. Le droit d'usage — a fortiori pour un service payant — reste à établir
auprès des auteurs avant toute exploitation.

**Les deux exigent un VAE tiers** : `runwayml/stable-diffusion-v1-5`, sous-dossier
`vae`, chargé par `AutoencoderKL.from_pretrained` (One-DM `test.py:74`,
DiffBrush `generate.py:55`). Sa licence (CreativeML Open RAIL-M) et sa
disponibilité sont à vérifier séparément : les deux README signalent eux-mêmes
des difficultés d'accès à ce modèle.

## 3. Ce qui a été exécuté ici

```bash
GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 https://github.com/dailenson/One-DM   /home/user/dailenson/one-dm
GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 https://github.com/dailenson/DiffBrush /home/user/dailenson/diffbrush
python3 experiences/preflight_photo_vers_texte.py            # code retour 1
python3 experiences/test_preflight_photo_vers_texte.py       # 22 tests, hors réseau
```

Le diagnostic ne lance aucune inférence, ne télécharge aucun poids et
**n'exécute aucun code tiers** : la constante `letters` des dépôts amont est
extraite par `ast.parse` + `ast.literal_eval`, jamais par `eval` ni par import.
Une valeur calculée (appel de fonction, f-chaîne, concaténation) est refusée,
pas devinée — un test le prouve, ainsi que l'absence d'effet de bord.

Il **ne conclut jamais qu'une inférence est possible.** Chaque point reçoit un
statut : `VERIFIE` (preuve positive obtenue ici), `REFUTE` (preuve négative
obtenue ici), `NON_VERIFIE` (aucune preuve — bloquant). Codes de retour : `1`
au moins un blocage prouvé, `2` aucun blocage prouvé mais des points bloquants
non vérifiés, `0` tous les points bloquants vérifiés — inatteignable par ce seul
programme, et qui ne vaudrait toujours pas « prêt pour l'inférence ».

Trois points restent `NON_VERIFIE` **par construction** : le téléchargement du
fichier de poids exact, le droit d'usage de ces poids, et leur présence locale.
Un tunnel HTTPS ouvert vers un domaine ne prouve ni l'existence, ni
l'accessibilité, ni la taille d'un fichier ; la présence du pilote NVIDIA ne
prouve pas qu'un GPU calcule.

Résultats mesurés (2026-09-09, session cloud) :

| Grandeur | Valeur mesurée |
|---|---|
| Processeurs / mémoire / disque libre | 4 · 15,7 Gio · 31,9 Go |
| GPU | **aucun** |
| Python de la session | 3.11.15 (les deux dépôts épinglent 3.8) |
| Clone One-DM | 15 Mo |
| Clone DiffBrush | 268 Mo (dont `test_data/` 131 Mo, 2 924 images) |
| Roue `torch==1.13.1` linux x86_64 | 887,4 Mo (cp311 disponible) |
| Roue `torchvision==0.14.1` | 24,2 Mo — **aucune roue cp311** |
| `diffusers` 0.29.0 · `transformers` 4.46.3 | 2,2 Mo · 10,0 Mo (pur Python) |
| Poids pré-entraînés | **taille inconnue** : hôtes injoignables, aucune requête aboutie |

Aucun coût externe engagé : aucun téléchargement de poids, aucun compte, aucun
service payant.

## 4. Ce qui est bloqué, précisément

1. **Aucun GPU, et le CPU ne suffit pas en l'état.** Les deux points d'entrée
   appellent sans condition `dist.init_process_group(backend='nccl')` puis
   `torch.cuda.set_device(local_rank)` (One-DM `test.py:22-24`, DiffBrush
   `generate.py:34-36`). L'option `--device cpu` existe mais n'est pas atteinte :
   NCCL exige un GPU. Un correctif minimal est décrit dans
   [`docs/ADAPTATION-CPU-ONE-DM.md`](ADAPTATION-CPU-ONE-DM.md) — proposition non
   validée, mais dont le premier point est vérifiable **sans aucun poids** par
   un test structurel : le script doit démarrer en mono-processus et échouer sur
   l'absence de point de contrôle, non sur NCCL.
2. **Aucun tunnel vers les hôtes de poids depuis cette session cloud.**
   `drive.google.com`, `pan.baidu.com` et `wisemodel.cn` répondent
   `403 Forbidden` au CONNECT de la passerelle sortante **de l'environnement où
   ce diagnostic a tourné** ; ailleurs, ces hôtes sont probablement joignables.
   Le constat porte sur le tunnel vers le domaine : l'accès au fichier de poids
   lui-même n'a pas été tenté et reste `NON_VERIFIE`.
3. **Aucun tunnel vers le VAE depuis cette session cloud.** `huggingface.co`
   répond également `403` au CONNECT, avec la même réserve de portée. Les deux
   modèles en dépendent pour décoder le latent en image.
4. **Chaîne de dépendances incompatible avec ce runtime.** Le couple épinglé
   `torch 1.13.1` / `torchvision 0.14.1` n'a pas de roue pour Python 3.11 côté
   torchvision ; les dépôts prévoient conda et Python 3.8.

Ces quatre blocages sont indépendants : lever un seul ne rend pas l'inférence
possible. Les deux du milieu tiennent à l'environnement d'exécution, pas au
dépôt amont : ils sont à re-tester sur chaque machine.

## 5. Caractères impossibles — constat exact

Phrases témoins, écrites pour cette expérience et jamais utilisées ailleurs :

- `experiences/temoin_ascii.txt` — « The quiet bench writes eight new words before dawn. »
- `experiences/temoin_francais.txt` — « Été à Montpellier, la façade de l’œuvre coûte cent centimes ; « oui ». »

Alphabets **publiés** (lus dans les dépôts, non recopiés ici) : One-DM 81
caractères (`data_loader/loader.py:25`), DiffBrush 80 caractères
(`data_loader/IAMDataset.py:8`).

| Phrase | One-DM | DiffBrush |
|---|---|---|
| ASCII témoin | intégralement couverte | intégralement couverte |
| française | **9 caractères impossibles** | **9 caractères impossibles** |

Identiques pour les deux modèles :
`«` U+00AB, `»` U+00BB, `É` U+00C9, `à` U+00E0, `ç` U+00E7, `é` U+00E9,
`û` U+00FB, `œ` U+0153, `’` U+2019.

Le mécanisme est plus profond qu'une liste : `ContentData.get_content` indexe
`letter2index[c]` — un caractère absent lève `KeyError` — et les images de
contenu proviennent d'un `data/unifont.pickle` construit **pour cet alphabet**.
Le modèle de diffusion, l'encodeur de style et la tête OCR ont été entraînés sur
ces 80-81 classes. Ajouter les accents ne relève donc pas d'un réglage : il
faudrait un ré-entraînement ou un affinage sur des données françaises annotées.

**Aucun accent ne doit être retiré pour faire passer une phrase.** Le rapport
doit lister les caractères impossibles tels quels, comme le fait déjà le banc
d'essai.

## 6. Échantillon de style : ce qui est utilisable, ce qui ne l'est pas

- Les 2 924 images livrées dans `DiffBrush/test_data/` suivent toutes le nommage
  des formulaires de la base **IAM** (`c04-110-00.png`, `p02-…`, `n01-…`). Aucun
  fichier de provenance ni de licence de données n'accompagne ce dossier. La base
  IAM est réservée à la recherche : **ne pas s'en servir pour un service payant**,
  ni comme « échantillon explicitement réutilisable ».
- Une photo client ne doit jamais entrer dans ce dépôt public (`.gitignore` bloque
  déjà les formats image).
- Il reste donc à obtenir un échantillon **explicitement réutilisable** : écriture
  d'un membre de l'équipe, avec autorisation écrite, conservée hors dépôt.

Format attendu par One-DM pour une référence (lu dans
`Random_StyleIAMDataset`) : `STYLE_PATH/test/<id_scripteur>/*.png` en niveaux de
gris, hauteur 64 px, **largeur > 128 px** sinon l'image est ignorée ; plus un
dossier parallèle `LAPLACE_PATH/test/<id_scripteur>/` contenant l'image
laplacienne de **même nom**. Aucun script de préparation laplacienne n'est fourni
dans le dépôt : il vient avec le jeu de données téléchargé. Préparer une photo
réelle suppose donc d'écrire ce prétraitement (découpe en mots, normalisation à
64 px, calcul du laplacien).

## 7. Protocole reproductible, quand les accès existeront

Ordre imposé : ASCII d'abord, français ensuite. Passer au français avant d'avoir
réussi l'ASCII masquerait la cause d'un échec.

1. **Vérifier les préconditions** — `python3 experiences/preflight_photo_vers_texte.py`.
   Ne continuer que si le code de retour vaut 0.
2. **Établir le droit d'usage des poids** auprès des auteurs, par écrit. Sans
   réponse, s'arrêter ici.
3. **Obtenir l'échantillon autorisé** (hors dépôt), le découper en images de mots
   64 px de haut, > 128 px de large, et produire les images laplaciennes
   correspondantes.
4. **Étape A — ASCII témoin.** Placer le contenu de `experiences/temoin_ascii.txt`
   dans le corpus pointé par `generate_type` (One-DM `data_loader/loader.py:19`),
   puis lancer `test.py` avec `--generate_type oov_u`. Sortie attendue : un PNG
   par mot, hauteur 64 px.
5. **Étape B — français.** Même chose avec `experiences/temoin_francais.txt`.
   Résultat attendu d'après l'inspection statique : **échec sur 9 caractères**.
   Consigner l'erreur exacte, ne rien retirer de la phrase.
6. **Contrôle humain du texte**, caractère par caractère, sur les images ASCII :
   le mot demandé est-il celui qui est écrit ? Une image plausible ne prouve rien.
7. **Comparaison de style à l'aveugle** : mélanger sorties générées et écriture
   réelle du scripteur, faire trancher quelqu'un qui n'a pas vu la manipulation.
   Sans ce test, une sortie générique ne prouve **aucune** personnalisation.

Un résultat convaincant à l'étape 7 ne prouverait toujours ni les trajectoires,
ni la page physique.

## 8. Besoin raster → monotrait

Les deux modèles produisent **uniquement des images raster** (`image.save(...png)`).
Aucun fichier `.py` des deux dépôts ne mentionne squelettisation, amincissement,
extraction de ligne centrale, vectorisation, SVG ou G-code — vérifié par
recherche sur l'ensemble des sources.

Il manque donc un maillon entier entre ces modèles et le banc d'essai paperx :
image 64 px de haut → squelette monotrait → trajectoires en millimètres. Ce
maillon n'existe nulle part dans la chaîne actuelle. Métriques à relever le jour
où il sera écrit, sur l'ASCII témoin d'abord :

- taux de reconnaissance humaine du texte (mot juste / mots demandés) ;
- nombre de traits et de levées par mot après squelettisation ;
- écart entre le squelette et l'image d'origine (largeur de trait supprimée) ;
- traits parasites introduits par la squelettisation ;
- temps de calcul par mot, mesuré, non estimé.

## 9. Prochaine action minimale

Obtenir un accès sortant à `huggingface.co` et à au moins un miroir de poids,
puis relancer `experiences/preflight_photo_vers_texte.py`. Tant qu'il rend un
code non nul, une **génération d'image** ne peut pas être vérifiée ; en
revanche, le correctif de démarrage se teste structurellement dès maintenant,
sans poids.

Trois pistes restent ouvertes en parallèle, sans promesse et sans qu'un GPU
payant soit imposé :

- **Adaptation CPU, ou MPS sur Apple.** Analyse ciblée faite :
  [`docs/ADAPTATION-CPU-ONE-DM.md`](ADAPTATION-CPU-ONE-DM.md) — cinq
  modifications dans le seul `test.py`, aucune dans les modèles — proposition
  non validée. Obstacle supplémentaire découvert au passage : trois **demandes**
  de poids ImageNet à `download.pytorch.org` à la construction du modèle (le
  nombre de transferts réseau réels n'a pas été mesuré, torchvision passant par
  un cache local), hôte refusé depuis cette session cloud. Aucun chiffre de
  performance n'est avancé : l'architecture du UNet, elle, est inspectable dans
  le code et la configuration, indépendamment des poids ; ce qui manque ici est
  son **nombre de paramètres**, que seule une instanciation — donc l'exécution
  de code tiers, exclue de cette analyse — établirait.
- **Droit d'usage des poids**, à demander par écrit aux auteurs — démarche
  indépendante du calcul.
- **Échantillon manuscrit explicitement réutilisable**, hors dépôt, jamais
  client.

## 10. Hors périmètre

Aucun serveur, aucune boutique, aucun G-code, aucun accès imprimante. Aucune
donnée client. Le banc d'essai validé (`paperx/`, `tests/`) n'est pas modifié par
cette expérience.
