# Limites réelles

Document volontairement sec. Tout ce qui suit est une limite constatée, pas une
précaution de style.

## 1. L'écriture n'est pas une écriture

`paperx/synthetic_hand.py` contient 117 glyphes tracés à la main à partir de
segments et d'arcs. Ce sont des squelettes monotraits : épaisseur constante,
pas de pression, pas de liaison cursive, pas de variabilité. Une ligature comme
`œ` est **approximée par juxtaposition** de `o` et `e`, ce qui n'est pas une
forme calligraphique correcte. Personne ne doit présenter ces tracés comme une
écriture manuscrite, ni comme une imitation de qui que ce soit.

## 2. Aucune personnalisation

Il n'existe aucun modèle dans ce dépôt, aucun poids, aucun appel d'inférence.
`paperx.provider.UnavailableProvider` refuse explicitement. Une photo de papier
vierge renseigne le support, jamais la main : le contrat la rejette
(`InvalidSampleKind`).

Constat externe, consigné séparément par le coordinateur (branche
`project/initial-evidence`, PR #1, non modifiée ici) : l'alphabet publié de
One-DM (`data_loader/loader.py`, blob `6ccae08`) ne contient ni `À à é ù ç è ë û
œ ’` — le français n'est donc pas pris en charge par cette version publiée, et
aucun modèle n'a été exécuté. Aucun des trois supports MakerWorld examinés n'est
validé pour un stylo bille du commerce (licences Stabilo/POSCA restrictives).
Ces points ne sont pas rejoués par ce banc d'essai.

## 3. Le validateur valide des nombres, pas une machine

`paperx/validator.py` contrôle des valeurs finies, des bornes de page, des
vitesses, des levées et le versionnement des profils. Il **ne modélise pas** :

- les offsets XY réels entre l'origine machine et la feuille ;
- les hauteurs de contact et de levée de la plume (Z de pose, Z de retrait) ;
- les obstacles physiques (pinces, bords de plateau, tête, capot) ;
- l'état réel de la machine au moment de l'exécution.

Conséquence assumée : `paperx.gate.MACHINE_OUTPUT_AVAILABLE` vaut `False` et le
constat `CHAINE_NON_VALIDEE` est émis systématiquement. Écrire `calibrated=True`
dans un profil ne prouve rien et ne débloque rien.

Le verrou est fermé **à cette étape**, pas définitivement. Il sera levé dans un
composant local séparé du site public, à l'intérieur de ce dépôt `paperx` — qui
reste la source de vérité — une fois la calibration et les essais réels
effectués et revus. Ce n'est pas une interdiction perpétuelle de réaliser le
projet, c'est le refus de produire une sortie machine avant d'avoir mesuré.

## 4. Course machine insuffisante pour une A4

Une aire de travail nominale de 256 × 256 mm ne couvre pas une feuille de
210 × 297 mm. Sous l'hypothèse **explicitement non mesurée** « feuille au coin
plateau (0,0), non tournée » : bande de 210 × 41 mm inaccessible, soit
8 610 mm², **13,8 % de la page**. Cette bande contient la marge haute et les
premières lignes de texte. Aucune mise à l'échelle n'est appliquée : le rapport
compte les points et les caractères concernés, l'aperçu les hachure en rouge.

Une pose mesurée, une feuille tournée ou une autre géométrie changeraient ce
chiffre — il faudrait alors le remesurer, pas le supposer.

## 5. Profils non mesurés

`demo-a4@1.0.0` et `demo-speeds@1.0.0` portent `measured=False`. Les 210 × 297 mm
viennent d'ISO 216 ; marges, interligne, corps, largeur de trait et vitesses sont
des choix de démonstration écrits dans le code. Aucun papier, aucun stylo, aucune
machine n'a été caractérisé.

## 6. Limites de la mise en page

- Un mot plus large que la bande utile est **coupé au caractère**, sans trait
  d'union : le texte reste exact, la coupure est signalée (`coupe_dure`).
- Les espaces qui dépassent la bande utile sont conservées mais de largeur nulle
  (`espaces_repliees`) : une ligne de 200 espaces ne déborde pas de la page.
- La tabulation `\t` n'est pas prise en charge : elle est signalée, pas convertie.
- Les césures typographiques françaises ne sont pas implémentées.
- Le rendu ne modélise ni la diffusion de l'encre, ni le grain du papier.

## 7. Ce que le dépôt ne contient pas

Aucun secret, aucun identifiant imprimante, aucune donnée client, aucune photo,
aucun poids. `.gitignore` et `tests/test_depot_public.py` le vérifient.
