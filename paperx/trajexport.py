"""Export JSON des trajectoires : suite explicite de poses et de levées.

Ce format est un **aperçu**, pas une tâche machine : il ne contient ni G-code,
ni commande, ni vitesse d'avance machine, ni Z. Chaque déplacement plume levée
est écrit en clair, entre deux traits, pour qu'une animation puisse montrer
exactement où la plume se lève et se repose.

Repère : millimètres, origine au coin haut-gauche de la feuille, y vers le bas
(même convention que l'aperçu SVG).
"""

from __future__ import annotations

from . import numeric as num
from .strokes import PageTrajectory

TRAJ_FORMAT = "paperx-trajectoires"
TRAJ_VERSION = "1.0.0"

NON_EXECUTABLE_NOTE = (
    "APERÇU NON EXÉCUTABLE. Ce fichier décrit une géométrie de tracé pour "
    "affichage et relecture. Ce n'est ni du G-code, ni un fichier de tâche "
    "machine : ni hauteur de plume, ni offset Z, ni origine machine n'y figurent "
    "— ces valeurs ne sont pas connues."
)


def _pt(point: tuple[float, float]) -> list[float] | None:
    x, y = point
    if not (num.is_finite(x) and num.is_finite(y)):
        return None
    return [round(float(x), 3), round(float(y), 3)]


def page_as_dict(traj: PageTrajectory) -> dict:
    """Trajectoire d'une page : traits posés et déplacements levés, dans l'ordre."""
    segments: list[dict] = []
    previous: list[float] | None = None
    lifts = 0

    for stroke in traj.strokes:
        points = [p for p in (_pt(pt) for pt in stroke.points) if p is not None]
        if len(points) < 2:
            continue
        if previous is not None:
            lifts += 1
            segments.append({
                "type": "deplacement",
                "plume": "levee",
                "de": previous,
                "a": points[0],
                "vitesse_mm_s": None,
                "note": "levée de plume : hauteur de levée inconnue, non calibrée",
            })
        segments.append({
            "type": "trace",
            "plume": "posee",
            "points": points,
            "vitesse_mm_s": (round(float(stroke.speed_mm_s), 3)
                             if num.is_finite(stroke.speed_mm_s) else None),
            "index_caractere": stroke.char_index,
            "caractere": stroke.char,
        })
        previous = points[-1]

    return {
        "format": TRAJ_FORMAT,
        "version": TRAJ_VERSION,
        "executable": False,
        "avertissement": NON_EXECUTABLE_NOTE,
        "page": traj.page_number,
        "unite": "mm",
        "repere": "origine au coin haut-gauche de la feuille, x vers la droite, y vers le bas",
        "papier": traj.paper_ref,
        "ecriture": traj.hand_ref,
        "vitesses": traj.speed_ref,
        "traits": len([s for s in segments if s["type"] == "trace"]),
        "levees_plume": lifts,
        "segments": segments,
        "emplacements_non_traces": [
            {
                "index_caractere": mark.char_index,
                "caractere": mark.char,
                "codepoint": mark.codepoint,
                "x_mm": round(mark.x_mm, 3),
                "ligne_de_base_y_mm": round(mark.baseline_y_mm, 3),
                "largeur_mm": round(mark.width_mm, 3),
                "hauteur_mm": round(mark.height_mm, 3),
                "note": "caractère non pris en charge : aucun trait produit, "
                        "emplacement réservé et signalé, jamais remplacé",
            }
            for mark in traj.unsupported_marks
        ],
    }
