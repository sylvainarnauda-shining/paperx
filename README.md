# paperx

Python ≥ 3.11 requis. Banc d'essai local **minimal** pour une seule question : est-ce qu'un texte
français confié à une chaîne d'écriture mécanique ressort **exactement**
identique ? Bibliothèque standard uniquement, aucune dépendance, aucun poids de
modèle, aucun accès réseau ni imprimante.

Ce n'est pas un produit, pas une boutique, pas une interface web.

## Démarrer

```bash
python3 -m unittest discover -s tests -t . -v      # 90 tests
python3 -m paperx demo --text samples/texte_demo_fr.txt --out out
python3 -m paperx experience                        # expérience falsifiable
```

`demo` écrit dans `out/` : un aperçu SVG par page, une fiche de revue humaine
non exécutable, et `rapport.json` (déterministe, JSON strict sans NaN).
Exemple versionné : [`docs/exemples/`](docs/exemples/).

## Exécuté ici

- Décodage UTF-8 strict, aucune normalisation Unicode, empreinte SHA-256.
- Pagination A4 sur un profil papier **explicite** de démonstration, avec preuve
  de reconstruction exacte du texte (chaque index du source apparaît une fois).
- Signalement des caractères non pris en charge : conservés dans le texte,
  marqués dans l'aperçu, **jamais supprimés ni remplacés** (pas de « é → e »).
- Trajectoires monotraits, levées de plume explicites, validateur déterministe
  (nombres finis, bornes page/marges, vitesses, levées, profils versionnés).
- Zones **inaccessibles** chiffrées : 256 × 256 mm face à une A4 210 × 297 mm →
  8 610 mm², 13,8 % de la page hors course sous une hypothèse de pose déclarée
  non mesurée. Rien n'est réduit pour masquer le problème.
- Refus de toute sortie machine, y compris avec un profil marqué calibré.
- Aperçu SVG lisible séparant la couche écriture de la couche annotations.

## Non démontré

- Toute **ressemblance** de l'écriture avec une main humaine : l'écriture livrée
  est une **écriture générique synthétique**, tracée à la main dans
  `paperx/synthetic_hand.py`, réservée aux tests mécaniques.
- Toute **personnalisation** depuis une photo ou un échantillon : aucun modèle
  n'existe ni n'est exécuté ici. Voir [le contrat fournisseur](docs/CONTRAT-FOURNISSEUR.md).
- Toute **calibration** : offsets XY, hauteurs de contact et de levée, obstacles,
  état machine. Le profil `bambu-p1s@0.0.0+non-calibre` a `pen_z_height_mm`,
  `z_offset_mm` et `placement` à `None` — rien n'est deviné.
- Tout comportement réel d'encre, de papier ou de stylo. Aucune feuille écrite.

Limites détaillées : [`docs/LIMITES.md`](docs/LIMITES.md).

## Refus explicites

Aucun G-code exécutable, aucun accès imprimante, aucun paiement, aucune donnée
client, aucun secret, aucune interface web. Prix cible figé : **100 centimes par
A4**, Montpellier centre, remise **à définir** (jamais supposée nulle).

## Fichiers

| Chemin | Rôle |
|---|---|
| `paperx/textsource.py` | lecture UTF-8 stricte, empreinte |
| `paperx/charset.py` | couverture et signalement des caractères absents |
| `paperx/synthetic_hand.py` | écriture générique synthétique (tests mécaniques) |
| `paperx/paper.py` | profil papier A4 de démonstration, géométrie vérifiée |
| `paperx/layout.py` | pagination à préservation exacte, réserves d'encre |
| `paperx/strokes.py` | trajectoires monotraits, vitesses déclarées |
| `paperx/machine.py` | profil P1S non calibré, zones inaccessibles |
| `paperx/validator.py` | validation déterministe |
| `paperx/gate.py`, `paperx/emit.py` | verrou global, refus de sortie machine |
| `paperx/provider.py` | contrat du futur fournisseur de personnalisation |
| `paperx/svg.py`, `paperx/report.py`, `paperx/cli.py` | aperçu, rapport, CLI |
| `samples/`, `docs/exemples/` | textes originaux, sorties de référence |

## Pour les agents

1. Ne jamais inventer une cote, un offset ou une vitesse : si la valeur n'est pas
   mesurée, elle vaut `None` et le code refuse.
2. Ne jamais supprimer, remplacer ni translittérer un caractère : signaler.
3. Ne jamais réduire le texte ou l'écriture pour faire tenir : signaler.
4. Tout profil est versionné (`id@version`) et porte `measured` / `calibrated`.
5. `MACHINE_OUTPUT_AVAILABLE` reste faux tant que la calibration, les essais
   réels et leur revue n'ont pas eu lieu ; le verrou sera alors levé par un
   composant local séparé du site public, dans ce dépôt. Ne pas le basculer avant.
6. Rien de binaire, rien de client, rien de secret dans le dépôt (voir
   `.gitignore` et `tests/test_depot_public.py`).
7. Après toute modification : `python3 -m unittest discover -s tests -t .` puis
   régénérer `docs/exemples/` (`python3 -m paperx demo --text
   samples/extrait_demo_fr.txt --out docs/exemples`), sinon un test échoue.
8. `docs/initial-evidence.md` et `docs/evidence/` appartiennent à la revue
   matériel : ne pas les modifier ici.
