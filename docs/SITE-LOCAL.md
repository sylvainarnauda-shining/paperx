# Site local paperx

Un site **français**, servi sur `127.0.0.1:8080`, qui va du texte au dossier de
préparation. Bibliothèque standard uniquement : aucun cadriciel, aucun CDN,
aucun service payant, aucun accès imprimante, aucun déploiement public.

```bash
python3 -m paperx_web            # http://127.0.0.1:8080
```

Le terminal imprime alors deux adresses et **une clé opérateur**. Cette clé
n'est servie par aucune page : elle se recopie depuis le terminal.

```
espace client    : http://127.0.0.1:8080/
espace opérateur : http://127.0.0.1:8080/operateur
clé opérateur    : …
```

## Deux espaces, pas deux onglets

| | Espace client `/` | Espace opérateur `/operateur` |
|---|---|---|
| Texte, photo, aperçu des pages | oui | oui |
| Prix et suivi de commande | oui | oui |
| Durées : contact, déplacements, levées, manipulation | **non** | oui |
| Coûts d'atelier, taux horaire, taux de ratés | **non** | oui |
| Détail de calcul du supplément | **non** | oui |
| Profils versionnés, codes du validateur | **non** | oui |
| Dossier téléchargé | 6 fichiers | 13 fichiers |

Ce n'est pas un simple masquage d'affichage : le serveur **n'envoie pas** ces
données à l'espace client, et l'espace opérateur exige la clé. Une personne qui
ouvre le site sans la clé ne peut pas les obtenir, même en appelant l'API.

## Le parcours client

1. **Texte** — saisi ou importé. Il est repris à l'identique : décodage UTF-8
   strict, aucune normalisation Unicode, aucun rognage. L'empreinte SHA-256 est
   consultable derrière « Vérifier que mon texte est intact ». Un caractère que
   l'écriture ne sait pas tracer est **signalé** et conservé, jamais remplacé.
2. **Écriture** — mode démonstration (styles synthétiques distincts) ou mode
   personnalisé. Le mode personnalisé exige un consentement **avant** tout dépôt,
   conserve la photo en local et laisse la commande **en attente** : aucune
   écriture générique n'est présentée comme celle du client.
3. **Recto ou recto-verso** — en langage courant : « une page par feuille » ou
   « deux pages par feuille ». Aucune formule n'est affichée.
4. **Devis** — pages écrites, feuilles, prix par page, sous-total, supplément de
   retournement, total. Le supplément vaut « reste à chiffrer » tant qu'aucune
   durée d'atelier n'a été mesurée, et le total reste « à confirmer ».
5. **Commande** — enregistrée en local, avec un dossier téléchargeable. La
   simulation animée montre le tracé page par page, s'arrête à chaque
   retournement manuel et ne repart qu'après confirmation explicite.

## Ce que la simulation montre, et ce qu'elle ne prouve pas

La vue affiche la feuille A4 entière, ses marges, la zone que la machine atteint
et, hachurées en rouge, **les zones qu'elle n'atteint pas** : une aire de travail
nominale de 256 × 256 mm ne couvre pas une A4 de 210 × 297 mm. Rien n'est réduit
pour masquer ce manque — ni le texte, ni la taille de l'écriture, fixée par le
profil papier.

Le stylo posé et le stylo levé sont distingués, et chaque déplacement à vide est
tracé. Cette géométrie **ne valide ni les collisions, ni la physique du tracé**.
Les offsets XY réels entre l'origine machine et la feuille, la hauteur de contact
et de levée, les obstacles et l'état de la machine restent **inconnus** et sont
affichés comme tels dans l'espace opérateur.

Les durées affichées à l'opérateur sont une arithmétique sur des vitesses
**déclarées**, non mesurées. Aucune optimisation sans erreur n'est revendiquée.
Restent à établir par des essais physiques, à plusieurs vitesses : lisibilité du
tracé, alignement recto/verso après retournement manuel, traits parasites, taux
de ratés réel, temps réel d'exécution.

## Le retournement est manuel

En recto-verso, la simulation s'arrête à la fin de chaque recto. Une personne
retourne la feuille, la recale, **vérifie l'alignement**, puis confirme. Aucune
reprise automatique n'existe :

- la confirmation exige une case cochée explicitement ;
- côté opérateur, l'état `EN_ATTENTE_RETOURNEMENT_MANUEL` n'a qu'une seule sortie
  autorisée en dehors de l'annulation : la confirmation humaine. La table de
  transitions de `paperx_web/store.py` fait autorité et est testée ;
- le supplément compte ces trois temps humains — retourner, recaler, contrôler —
  plus les ratés.

## Prix

`100 centimes par face A4 écrite`, Montpellier centre, remise **à définir**.

Le recto-verso divise le nombre de **feuilles** (`ceil(faces / 2)`), pas le prix
de l'écriture : chaque face écrite reste au prix unitaire. Il **ajoute** un coût
au lieu d'en retirer. Sans durées d'atelier renseignées, ce supplément vaut
« à établir » — jamais `0`. Renseigné depuis l'espace opérateur, il porte sa
provenance (`hypothèse` ou `mesurée`) et le total reste non confirmé.

Aucun paiement réel n'est possible : `pricing.charge()` refuse, et rien dans ce
dépôt ne contacte un prestataire.

## Le dossier de préparation

Deux archives ZIP déterministes, figées **à la création de la commande** : un
changement de profil plus tard ne réécrit pas une commande passée, et l'empreinte
de chaque archive est vérifiée avant de la servir.

Dossier client :

```
LISEZ-MOI.txt   MANIFESTE.json   devis.json   pages/page-NN.svg   texte-source.txt
```

Dossier opérateur : les fichiers ci-dessus, plus `trajectoires/page-NN.json`,
`validation/rapport.json`, `validation/revue-page-NN.txt`, `simulation.json`,
`devis-operateur.json`.

Le manifeste est versionné, porte l'empreinte SHA-256 de **chaque** entrée et une
empreinte globale, et déclare l'état `NON_EXECUTABLE`. **Aucun G-code**, aucun
fichier de tâche, aucune coordonnée machine, aucun Z : la chaîne n'est pas
calibrée et rien n'est deviné pour combler ce vide.

## Personnalisation : indisponible, et dit comme tel

Déposer une photo ne produit aucune écriture personnalisée. Aucun modèle n'est
présent ni exécuté ; `paperx.provider.UnavailableProvider` refuse explicitement.
Le dépôt sert à préparer une étape future.

- Le consentement est exigé **avant** l'enregistrement : sans lui, rien n'est
  écrit sur le disque.
- La photo reste dans le répertoire de données local, hors du dépôt de code.
- Un dépôt jamais rattaché à une commande est effacé automatiquement au bout de
  30 minutes.
- La commande reste `EN_ATTENTE_PERSONNALISATION`, et l'export de production est
  refusé.
- Les aperçus restent possibles, mais marqués « ce n'est PAS votre écriture ».

## Garde-fous locaux

- Écoute **uniquement** sur la boucle locale : le serveur refuse de démarrer sur
  une autre adresse.
- `Host` vérifié à chaque requête (re-liage DNS) ; `Origin` et `Referer`, s'ils
  sont présents, doivent être locaux.
- Jeton de session obligatoire sur `POST` et `DELETE`, transmis par un en-tête
  qu'une page tierce ne peut pas lire (aucun en-tête CORS n'est émis).
- Fichiers statiques servis depuis une **liste blanche fermée** : aucun chemin
  fourni par le client n'atteint le système de fichiers.
- Dépôts : JPEG et PNG seulement, signature du fichier faisant foi. **SVG et tout
  contenu actif refusés.** Taille et résolution bornées. Pour un PNG, la
  structure entière est parcourue (CRC de chaque bloc) puis les pixels sont
  décompressés et comparés, à l'octet près, aux dimensions annoncées : un en-tête
  qui prétend 1200 × 1200 sans les pixels correspondants est refusé. Pour un
  JPEG, la structure et le flux entropique sont vérifiés de bout en bout, mais
  les pixels **ne sont pas décodés** — ce module ne contient pas de décodeur.
- Le nom de fichier fourni n'est jamais utilisé pour écrire sur le disque.
- Les données locales (`~/.paperx-web` par défaut, ou `$PAPERX_WEB_DATA`) vivent
  hors du dépôt, en 0600. La suppression d'une commande efface son texte, sa
  photo et ses deux dossiers.

## Tests

```bash
python3 -m unittest discover -s tests -t .
```

Couvrent notamment : préservation Unicode exacte par HTTP, faces/feuilles et
supplément inconnu, manifeste haché et téléchargeable, refus de sortie machine,
dépôt invalide (dont le faux PNG), suppression complète, sécurité locale
(hôte, origine, jeton, traversée de chemin, corps hors limites), séparation
client/opérateur, artefacts figés et attente de retournement non contournable.
