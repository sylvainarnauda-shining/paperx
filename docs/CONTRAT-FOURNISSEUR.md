# Contrat du futur fournisseur de personnalisation

Interface : `paperx/provider.py`. Contrôle automatique :
`paperx.provider.check_conformance(fournisseur)` renvoie la liste des
manquements (vide = conforme). Aucun modèle n'est exécuté par ce dépôt ; ce
document décrit ce qu'un fournisseur devra respecter **le jour où il existera**.

## Types d'échantillon

| Type | Ce qu'il décrit | Peut personnaliser ? |
|---|---|---|
| `PHOTO_PAPIER_VIERGE` | grain, teinte, bords, éclairage du support | **Non**, refus obligatoire |
| `ECHANTILLON_MANUSCRIT_CLIENT` | tracés réellement écrits par la personne | Oui, seule source admissible |
| `ECRITURE_GENERIQUE_SYNTHETIQUE` | gabarit interne de test | Non, jamais |

Confondre les deux premiers revient à déduire une écriture d'un morceau de
papier. Le contrat l'interdit explicitement.

## Règles

- **R1** — `capabilities()` est déterministe et versionnée (`id@version`).
- **R2** — `is_personalized = True` exige `ECHANTILLON_MANUSCRIT_CLIENT`.
- **R3** — `build_hand()` refuse `PHOTO_PAPIER_VIERGE` par `InvalidSampleKind`.
- **R4** — `build_hand()` refuse tout type non déclaré dans `requires_sample_kinds`.
- **R5** — une écriture « personnalisée » ne peut pas naître d'un gabarit générique.
- **R6** — la couverture de caractères est déclarée ; les caractères non couverts
  sont signalés à l'appelant, jamais supprimés ni remplacés.
- **R7** — tout poids ou code tiers est référencé avec sa licence, et
  `licence_verified` dit si elle a été **vérifiée** (pas supposée).
- **R8** — l'indisponibilité se signale par `PersonalizationUnavailable` ; rendre
  discrètement une écriture générique à la place est un manquement.

## Données personnelles

Un échantillon manuscrit est une donnée personnelle. `Sample` ne transporte
qu'une **référence opaque** (`storage_ref`) et une référence de consentement :
aucun octet d'image n'entre dans ce dépôt public, et `.gitignore` bloque les
formats concernés. Le fournisseur devra documenter durée de conservation,
suppression et localisation du stockage — hors de ce dépôt.

## Vérification d'un candidat

Avant toute intégration :

1. licence des poids et du code **lue et vérifiée**, compatible avec l'usage visé ;
2. couverture du français vérifiée caractère par caractère (`Capabilities.missing_for`) ;
3. `check_conformance()` sans manquement ;
4. comportement sur `PHOTO_PAPIER_VIERGE` testé explicitement ;
5. aucune régression de la préservation exacte du texte.
