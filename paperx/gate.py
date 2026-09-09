"""Verrou global de sortie machine.

Tant que ce drapeau est faux, AUCUNE trajectoire ne peut être déclarée prête
pour une machine, quel que soit l'état des profils. Ce n'est pas une précaution
de style : à cette étape, le banc d'essai ne représente pas

- les offsets XY réels entre l'origine machine et la feuille,
- les hauteurs de contact et de levée de la plume (Z de pose, Z de retrait),
- les obstacles physiques (pinces, bords de plateau, tête, capot),
- l'état réel de la machine au moment de l'exécution.

Un profil marqué `calibrated=True` dans le code ne prouve rien de tout cela.

Ce verrou décrit l'état actuel de la chaîne, pas une renonciation : il est fait
pour être levé. Il le sera dans un composant local séparé du site public, à
l'intérieur de ce dépôt `paperx` qui reste la source de vérité, une fois la
calibration et les essais réels effectués et revus — pas par un simple
changement de valeur.
"""

from __future__ import annotations

#: Sortie machine indisponible à cette étape du projet.
MACHINE_OUTPUT_AVAILABLE: bool = False

GATE_CODE = "CHAINE_NON_VALIDEE"

GATE_REASON = (
    "chaîne non validée de bout en bout : offsets XY réels, hauteurs de contact "
    "et de levée, obstacles physiques et état machine ne sont pas représentés à "
    "cette étape du banc d'essai. Aucun profil ne peut devenir « prêt machine » "
    "tant que la calibration, les essais réels et leur revue n'ont pas eu lieu ; "
    "la sortie machine sera alors ouverte par un composant local séparé du site "
    "public, dans ce dépôt."
)
