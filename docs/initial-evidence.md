# Paperx — preuves initiales, 9 septembre 2026

## État vérifié

Dépôt initial : README seul, commit `b76a290`. Le développement du banc d'essai est délégué à Claude Code en cloud sur une branche distincte ; sa livraison doit être revue avant validation. Aucun modèle d'écriture exécuté, aucun STL retenu ou imprimé, aucune commande moteur envoyée, aucune calibration physique réalisée.

Objectif inchangé : texte exact + photo d'écriture autorisée → nouveau texte manuscrit au stylo à bille sur A4 à carreaux ; 1 € par page, Montpellier centre, remise à définir. La X1C fabrique les supports ; la P1S trace sans plastique. Photos clients, textes réels, commandes et secrets restent hors dépôt public.

## Fixation : décision encore ouverte

| Source primaire | Constat | Décision |
|---|---|---|
| [KEV_3DP 3011022](https://makerworld.com/en/models/3011022-p1-x1-pen-plotter-module) | P1S déclarée compatible ; Stabilo, prise de 7,8 mm selon l'auteur ; profil annoncé 28 min / 12 g sans supports ; collision avant droit rapportée en commentaire | Simple piste mécanique, pas une validation bille. Standard Digital File License : redistribution et utilisation payante sans permission interdites |
| [P1S/P1P 1382919](https://makerworld.com/en/models/1382919-p1s-p1p-pen-plotter-attachment) | Stabilo avec ressort ; P1S/P1P, X1C explicitement exclue ; profil annoncé 1,5 h sans supports ; remplacé par 3011022 | Pas de validation bille ; Standard Digital File License restrictive identique au modèle récent |
| [Falu 2029113](https://makerworld.com/en/models/2029113-modular-system-for-a1-p1-x1-series) | Ressort et réglage de profondeur ; Stabilo/POSCA ; obstacles explicités ; licence Exclusive et adhésion commerciale proposée | Intérêt pour la pression, mais adaptation bille et permission commerciale nécessaires. Pas de redistribution hors MakerWorld |

Les trois pages ont été lues dans le navigateur. Ne pas copier leurs fichiers dans ce dépôt. La gratuité de téléchargement ne valide pas le droit d'exploitation commerciale. Aucun abonnement souscrit.

Le [guide rebelthor](https://github.com/rebelthor/bambu-lab-pen-plotter) et les instructions Falu ne sont pas une séquence Paperx : ils contiennent chauffe, extrusion et changements de sécurités. Le démarrage Falu comporte notamment une désactivation des fins de course logicielles, des déplacements au-delà de 256 et des contacts buse. Ne pas l'exécuter sur notre montage.

## A4 : contrainte conservée

210 × 297 mm ne tient pas intégralement dans un carré 256 × 256, même tourné. Une zone textuelle alignée pourrait tenir avec au moins 41 mm de marges haut/bas cumulées, avant prise en compte du support et des obstacles. Cela ne prouve pas que le papier peut être posé sans collision. La zone exclue publiée par Falu laisse un rectangle théorique 210 × 203 mm dans son repère de 258 mm ; ce n'est ni notre calibration ni une page A4 complète.

Comparer après mesures : une passe avec les vraies marges de la feuille standard ; sinon deux passes avec butée et repérage reproductible. Le repositionnement sera une manipulation manuelle chronométrée tant qu'aucun mécanisme réel ne le réalise.

## Écriture : première expérience choisie

[One-DM](https://github.com/dailenson/One-DM) est candidat expérimental photo → nouveaux mots, avec sortie image. Code MIT ; droits des poids externes et dépendances à vérifier séparément. Ce n'est pas une chaîne de production validée.

Inspection statique exécutée sur son alphabet d'entrée : voir `evidence/one-dm-alphabet-check.json`. Le texte ASCII témoin est couvert ; les phrases françaises échouent sur accents, œ et apostrophe typographique. Le chargeur effectue une indexation directe de cet alphabet : la version publiée ne couvre donc pas ces entrées. Aucun accent ne doit être retiré pour cacher cette limite.

[DiffBrush](https://github.com/dailenson/DiffBrush) génère des lignes raster, code MIT, configuration avec 15 images de référence. Une page peut contenir plusieurs extraits mais cette intégration n'est pas démontrée. [handwriting_line_generation](https://github.com/herobd/handwriting_line_generation) porte une licence non commerciale : pas de dépendance commerciale retenue.

[BambuPlot](https://github.com/Joep648/BambuPlot) propose P1S et glyphes, mais le mode monotraits capitalise les minuscules et le mode personnel se replie sur un glyphe générique. Aucune licence racine trouvée. [Octoprint_penploter](https://github.com/Happy123455/octoprint_penploter), code MIT, propose notamment une réécriture du texte pour le faire tenir : fonction incompatible, à exclure. Ces projets ne démontrent pas notre transfert de style depuis photo.

Expérience : échantillon autorisé conservé en privé → mots nouveaux ASCII puis français → contrôle humain exact du texte et comparaison aveugle des styles → seulement si acceptable, squelette central et trajectoires neutres en mm. Vérifier ensuite sur papier produit : liaisons, accents, taille, lisibilité, ressemblance, traits parasites, temps et ratés. Une image réussie ne prouve ni les chemins ni la page physique.

## Prochaines preuves nécessaires

1. Identifier le stylo disponible et vérifier une fixation adaptée avec des droits suffisants.
2. Rétablir l'accès aux imprimantes ; vérifier buse, filament et plateau X1C avant fabrication.
3. Revoir et exécuter le banc d'essai livré par Claude ; profils matériels non calibrés bloquants.
4. Recevoir séparément la feuille standard et un échantillon manuscrit autorisé au moment des essais correspondants.
5. Mesurer les coûts réels (papier, encre, calcul, paiement, ratés, manipulation) sans changer le tarif cible.
