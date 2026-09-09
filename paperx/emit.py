"""Verrou de sortie machine.

Ce dépôt ne produit AUCUN G-code exécutable et n'ouvre AUCUN accès imprimante
(ni série, ni réseau, ni fichier de tâche). Deux barrières successives :

0. un verrou global (`paperx.gate.MACHINE_OUTPUT_AVAILABLE`, faux ici) refuse
   toute sortie tant que la chaîne n'est pas validée de bout en bout : ni les
   offsets XY réels, ni les hauteurs de contact et de levée, ni les obstacles
   physiques, ni l'état machine ne sont représentés dans ce banc d'essai ;
1. tant que le profil machine n'est pas réellement calibré (pose de feuille
   mesurée, hauteur de plume et offset Z connus), toute demande de sortie
   machine lève `CalibrationRequired` ;
2. même avec un profil calibré, l'émission d'un format exécutable n'est pas
   implémentée ici, volontairement : elle relèvera d'un dépôt séparé, après
   essais réels et revue matériel.

La seule sortie autorisée est une **fiche de revue humaine**, non exécutable,
destinée à la lecture.
"""

from __future__ import annotations

from . import gate
from .errors import CalibrationRequired
from .machine import MachineProfile
from .strokes import PageTrajectory
from .validator import ValidationReport

#: Marqueur présent en tête de toute fiche de revue : elle n'est pas une tâche.
NON_EXECUTABLE_HEADER = (
    "FICHE DE REVUE HUMAINE — NON EXÉCUTABLE. "
    "Ce document n'est ni du G-code, ni un fichier de tâche machine."
)


def machine_output(traj: PageTrajectory, machine: MachineProfile,
                   report: ValidationReport) -> str:
    """Refuse toute sortie machine. Ne renvoie jamais de format exécutable."""
    reasons: list[str] = []
    if not gate.MACHINE_OUTPUT_AVAILABLE:
        # Verrou global : indépendant des profils. Un profil marqué calibré ne
        # prouve ni les offsets XY réels, ni les hauteurs de contact et de levée,
        # ni l'absence d'obstacle, ni l'état de la machine.
        reasons.append(gate.GATE_REASON)
    if not machine.calibrated:
        reasons.append("profil machine non calibré")
    if machine.placement is None or not machine.placement.measured:
        reasons.append("pose de la feuille non mesurée")
    if machine.pen_z_height_mm is None:
        reasons.append("hauteur de plume inconnue")
    if machine.z_offset_mm is None:
        reasons.append("offset Z inconnu")
    if not report.machine_ready:
        blocking = sorted({i.code for i in report.issues
                           if i.severity in ("erreur", "bloquant_machine")})
        reasons.append("constats bloquants du validateur : " + ", ".join(blocking))

    if reasons:
        raise CalibrationRequired(
            "sortie machine refusée (" + " ; ".join(reasons) + "). "
            "Aucune calibration réelle n'a été faite : aucune valeur n'est inventée "
            "pour contourner ce refus."
        )

    raise NotImplementedError(
        "émission machine volontairement non implémentée dans ce dépôt : "
        "aucun format exécutable (G-code ou autre) n'y est produit, même avec un "
        "profil calibré. Voir docs/LIMITES.md."
    )


def review_sheet(traj: PageTrajectory, machine: MachineProfile,
                 report: ValidationReport) -> str:
    """Fiche texte, non exécutable, pour relecture humaine d'une page."""
    lines = [
        NON_EXECUTABLE_HEADER,
        "",
        f"page                : {traj.page_number}",
        f"papier              : {traj.paper_ref}",
        f"écriture            : {traj.hand_ref} (générique synthétique, non personnalisée)",
        f"vitesses            : {traj.speed_ref}",
        f"machine             : {machine.ref()} — calibrée : {machine.calibrated}",
        f"traits              : {len(traj.strokes)}",
        f"levées de plume     : {traj.pen_lifts}",
        f"points              : {traj.point_count}",
        f"longueur tracée     : {traj.draw_length_mm:.1f} mm",
        f"déplacements        : {traj.travel_length_mm():.1f} mm",
        f"trajectoire valide  : {report.trajectory_valid}",
        f"prêt machine        : {report.machine_ready}",
        "",
        "constats :",
    ]
    lines.extend(
        f"  [{issue.severity}] {issue.code} × {issue.count} — {issue.message}"
        for issue in report.issues
    ) or lines.append("  (aucun)")
    return "\n".join(lines) + "\n"
