"""Métriques de simulation d'une page A4 et d'un travail complet.

Ce module chiffre ce qu'une page **représente** géométriquement : surface de
texte occupée, longueur réellement tracée, temps décomposé (contact,
déplacements, levées, manipulation humaine). Il ne pilote rien et ne mesure rien.

CE QUI N'EST PAS DÉMONTRÉ ICI — à mesurer par des essais physiques, à plusieurs
vitesses, avant toute promesse : lisibilité du tracé, alignement recto/verso
après retournement manuel, traits parasites, taux de ratés réel, temps réel.
Aucune optimisation « sans erreur » n'est revendiquée : les durées ci-dessous
sont une arithmétique sur des vitesses **déclarées et non mesurées**, sur une
machine **non calibrée**. Elles servent à dimensionner une interface, pas à
promettre un délai.

Le texte n'est jamais réduit et l'écriture garde sa taille : ces métriques
décrivent la page telle qu'elle est composée, elles ne servent pas à la tasser.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import numeric as num
from .duplex import OperatorCosts, Sides, UNKNOWN_COSTS, flips_for, sheets_for
from .errors import ProfileError
from .layout import LayoutResult
from .machine import ReachabilityReport
from .strokes import PageTrajectory, SpeedProfile

SIMULATION_VERSION = "1.0.0"

#: Ce que seuls des essais physiques pourront établir. Repris tel quel dans
#: l'interface, le rapport et le dossier de préparation.
UNMEASURED_TRIALS: tuple[str, ...] = (
    "lisibilité du tracé sur papier réel, à plusieurs vitesses",
    "alignement recto/verso après retournement et recalage manuels",
    "traits parasites : bavures, reprises, filage d'encre, marquage au levé",
    "taux de ratés réel, par face et par feuille",
    "temps réel d'exécution, manipulation humaine comprise",
)

TRIALS_NOTE = (
    "Aucune optimisation sans erreur n'est revendiquée. Les durées et surfaces "
    "ci-dessous sont calculées à partir de vitesses DÉCLARÉES, non mesurées, sur "
    "une machine NON CALIBRÉE. Elles seront invalidées ou corrigées par des essais "
    "physiques menés à plusieurs vitesses."
)


@dataclass(frozen=True)
class TimingHypotheses:
    """Durées de levée/pose de plume. Déclarées ici, jamais mesurées."""

    id: str
    version: str
    pen_up_seconds: float | None
    pen_down_seconds: float | None
    measured: bool
    provenance: str

    def __post_init__(self) -> None:
        problems = self.numeric_problems()
        if problems:
            raise ProfileError(
                f"hypothèses de temps {self.id}@{self.version} incohérentes : "
                + " ; ".join(problems))

    def numeric_problems(self) -> tuple[str, ...]:
        p: list[str] = []
        if not isinstance(self.id, str) or not self.id.strip():
            p.append("id : identifiant vide")
        if not isinstance(self.version, str) or not self.version.strip():
            p.append("version : version vide")
        if not isinstance(self.measured, bool):
            p.append("measured : booléen attendu")
        for name in ("pen_up_seconds", "pen_down_seconds"):
            value = getattr(self, name)
            if value is not None:
                num.require_non_negative(p, name, value)
        if self.measured and not self.known:
            p.append("measured=True alors que des durées restent inconnues")
        return tuple(p)

    @property
    def known(self) -> bool:
        return self.pen_up_seconds is not None and self.pen_down_seconds is not None

    @property
    def seconds_per_lift(self) -> float | None:
        if not self.known:
            return None
        return float(self.pen_up_seconds) + float(self.pen_down_seconds)

    def ref(self) -> str:
        return f"{self.id}@{self.version}"

    def as_dict(self) -> dict:
        return {
            "profil": self.ref(),
            "secondes_levee": self.pen_up_seconds,
            "secondes_pose": self.pen_down_seconds,
            "secondes_par_levee": self.seconds_per_lift,
            "mesure": self.measured,
            "provenance": self.provenance,
        }


DEMO_TIMING = TimingHypotheses(
    id="demo-timing",
    version="1.0.0",
    pen_up_seconds=0.15,
    pen_down_seconds=0.15,
    measured=False,
    provenance=(
        "HYPOTHÈSE déclarée dans paperx/simulation.py pour donner un ordre de "
        "grandeur à l'interface. Aucune mesure sur machine, aucun essai réel : "
        "la hauteur de plume et l'offset Z sont eux-mêmes inconnus."
    ),
)

UNKNOWN_TIMING = TimingHypotheses(
    id="timing-inconnu",
    version="1.0.0",
    pen_up_seconds=None,
    pen_down_seconds=None,
    measured=False,
    provenance="Aucune durée de levée/pose renseignée : le temps de levée reste inconnu.",
)


def _round_or_none(value: float | None, digits: int) -> float | None:
    if value is None or not num.is_finite(value):
        return None
    return round(float(value), digits)


@dataclass(frozen=True)
class PageMetrics:
    """Ce qu'une page occupe et ce qu'elle coûterait en temps, sous hypothèses."""

    page_number: int
    page_area_mm2: float
    text_area_mm2: float
    ink_bbox_mm: tuple[float, float, float, float] | None
    lines: int
    drawn_chars: int
    strokes: int
    points: int
    pen_lifts: int
    draw_length_mm: float
    travel_length_mm: float
    contact_seconds: float | None
    travel_seconds: float | None
    lift_seconds: float | None
    unreachable_points: int
    unreachable_area_mm2: float | None

    @property
    def text_area_ratio(self) -> float:
        return self.text_area_mm2 / self.page_area_mm2 if self.page_area_mm2 else 0.0

    @property
    def machine_seconds(self) -> float | None:
        parts = (self.contact_seconds, self.travel_seconds, self.lift_seconds)
        if any(p is None for p in parts):
            return None
        return sum(parts)  # type: ignore[arg-type]

    def as_dict(self) -> dict:
        bbox = self.ink_bbox_mm
        return {
            "page": self.page_number,
            "surface_page_mm2": round(self.page_area_mm2, 1),
            "surface_texte_occupee_mm2": round(self.text_area_mm2, 1),
            "part_page_occupee": round(self.text_area_ratio, 4),
            "boite_encre_mm": [round(v, 2) for v in bbox] if bbox else None,
            "lignes": self.lines,
            "caracteres_dessines": self.drawn_chars,
            "traits": self.strokes,
            "points": self.points,
            "levees_plume": self.pen_lifts,
            "longueur_tracee_mm": round(self.draw_length_mm, 2),
            "longueur_deplacements_mm": round(self.travel_length_mm, 2),
            "temps_contact_s": _round_or_none(self.contact_seconds, 1),
            "temps_deplacements_s": _round_or_none(self.travel_seconds, 1),
            "temps_levees_s": _round_or_none(self.lift_seconds, 1),
            "temps_machine_s": _round_or_none(self.machine_seconds, 1),
            "points_hors_course": self.unreachable_points,
            "surface_hors_course_mm2": _round_or_none(self.unreachable_area_mm2, 1),
        }


def page_metrics(layout: LayoutResult, traj: PageTrajectory,
                 speeds: SpeedProfile,
                 timing: TimingHypotheses = DEMO_TIMING,
                 reach: ReachabilityReport | None = None) -> PageMetrics:
    paper = layout.paper
    m = layout.metrics
    page = next(p for p in layout.pages if p.number == traj.page_number)

    # Surface de texte occupée : bande d'encre de chaque ligne × sa largeur réelle.
    text_area = sum(max(0.0, line.width_mm) * m.ink_band_mm for line in page.lines)

    draw = traj.draw_length_mm
    travel = traj.travel_length_mm()
    contact = (draw / speeds.draw_speed_mm_s
               if num.is_finite(draw) and speeds.draw_speed_mm_s > 0 else None)
    move = (travel / speeds.travel_speed_mm_s
            if num.is_finite(travel) and speeds.travel_speed_mm_s > 0 else None)
    per_lift = timing.seconds_per_lift
    lifts = traj.pen_lifts * per_lift if per_lift is not None else None

    unreachable_points = 0
    if reach is not None:
        for stroke in traj.strokes:
            for x, y in stroke.points:
                if num.is_finite(x) and num.is_finite(y) and reach.is_unreachable_point(x, y):
                    unreachable_points += 1

    return PageMetrics(
        page_number=traj.page_number,
        page_area_mm2=paper.width_mm * paper.height_mm,
        text_area_mm2=text_area,
        ink_bbox_mm=traj.bounds_mm(),
        lines=len(page.lines),
        drawn_chars=sum(len(line.chars) for line in page.lines),
        strokes=len(traj.strokes),
        points=traj.point_count,
        pen_lifts=traj.pen_lifts,
        draw_length_mm=draw if num.is_finite(draw) else 0.0,
        travel_length_mm=travel if num.is_finite(travel) else 0.0,
        contact_seconds=contact,
        travel_seconds=move,
        lift_seconds=lifts,
        unreachable_points=unreachable_points,
        unreachable_area_mm2=reach.unreachable_area_mm2 if reach else None,
    )


# --- Manipulations humaines --------------------------------------------------

MANIP_RETOURNEMENT = "retournement_recalage"
MANIP_CHANGEMENT_FEUILLE = "changement_feuille"


@dataclass(frozen=True)
class ManualStep:
    """Une intervention HUMAINE obligatoire entre deux faces.

    Aucune reprise automatique : la face suivante n'est simulée qu'après une
    confirmation explicite de la personne qui manipule la feuille.
    """

    after_page: int
    next_page: int
    kind: str
    sheet: int
    instructions: tuple[str, ...]
    requires_confirmation: bool = True

    def as_dict(self) -> dict:
        return {
            "apres_page": self.after_page,
            "page_suivante": self.next_page,
            "type": self.kind,
            "feuille": self.sheet,
            "consignes": list(self.instructions),
            "confirmation_requise": self.requires_confirmation,
            "reprise_automatique": False,
        }


_FLIP_STEPS = (
    "Retirer la feuille du support sans la faire glisser.",
    "La retourner bord long, face écrite vers le bas.",
    "La recaler contre les butées, sans forcer.",
    "Contrôler l'alignement : repères de marge, bord haut, bord gauche.",
    "Confirmer explicitement ci-dessous pour reprendre la simulation.",
)

_SHEET_STEPS = (
    "Retirer la feuille terminée et la mettre à sécher à plat.",
    "Poser une feuille vierge et la recaler contre les butées.",
    "Contrôler l'alignement avant de confirmer.",
)


def manual_steps(pages: int, sides: Sides) -> tuple[ManualStep, ...]:
    """Interventions humaines entre les faces, dans l'ordre d'exécution."""
    steps: list[ManualStep] = []
    for page in range(1, pages):
        nxt = page + 1
        if sides is Sides.RECTO_VERSO:
            if page % 2 == 1:      # recto -> verso de la même feuille
                steps.append(ManualStep(page, nxt, MANIP_RETOURNEMENT,
                                        sheet=(page + 1) // 2, instructions=_FLIP_STEPS))
            else:                  # feuille suivante
                steps.append(ManualStep(page, nxt, MANIP_CHANGEMENT_FEUILLE,
                                        sheet=page // 2 + 1, instructions=_SHEET_STEPS))
        else:
            steps.append(ManualStep(page, nxt, MANIP_CHANGEMENT_FEUILLE,
                                    sheet=nxt, instructions=_SHEET_STEPS))
    return tuple(steps)


@dataclass(frozen=True)
class JobMetrics:
    pages: tuple[PageMetrics, ...]
    sides: Sides
    faces: int
    sheets: int
    steps: tuple[ManualStep, ...]
    manipulation_seconds: float | None
    speeds: SpeedProfile
    timing: TimingHypotheses
    costs: OperatorCosts

    @property
    def machine_seconds(self) -> float | None:
        values = [p.machine_seconds for p in self.pages]
        if any(v is None for v in values):
            return None
        return sum(values)  # type: ignore[arg-type]

    @property
    def total_seconds(self) -> float | None:
        machine = self.machine_seconds
        if machine is None or self.manipulation_seconds is None:
            return None
        return machine + self.manipulation_seconds

    def as_dict(self) -> dict:
        return {
            "version_simulation": SIMULATION_VERSION,
            "mode": self.sides.value,
            "faces_ecrites": self.faces,
            "feuilles": self.sheets,
            "profil_vitesses": self.speeds.as_dict(),
            "hypotheses_temps": self.timing.as_dict(),
            "couts_operateur": self.costs.as_dict(),
            "pages": [p.as_dict() for p in self.pages],
            "cumul": {
                "surface_texte_occupee_mm2": round(
                    sum(p.text_area_mm2 for p in self.pages), 1),
                "longueur_tracee_mm": round(sum(p.draw_length_mm for p in self.pages), 1),
                "longueur_deplacements_mm": round(
                    sum(p.travel_length_mm for p in self.pages), 1),
                "levees_plume": sum(p.pen_lifts for p in self.pages),
                "temps_machine_s": _round_or_none(self.machine_seconds, 1),
                "temps_manipulation_s": _round_or_none(self.manipulation_seconds, 1),
                "temps_total_s": _round_or_none(self.total_seconds, 1),
                "temps_total_confirme": False,
            },
            "interventions_humaines": [s.as_dict() for s in self.steps],
            "retournement_manuel": self.sides is Sides.RECTO_VERSO,
            "reprise_automatique": False,
            "calibre": False,
            "mesure": False,
            "reserves": {
                "note": TRIALS_NOTE,
                "a_mesurer_par_essais_physiques": list(UNMEASURED_TRIALS),
            },
        }


def job_metrics(layout: LayoutResult,
                trajectories: tuple[PageTrajectory, ...],
                speeds: SpeedProfile,
                sides: Sides,
                timing: TimingHypotheses = DEMO_TIMING,
                costs: OperatorCosts = UNKNOWN_COSTS,
                reach: ReachabilityReport | None = None) -> JobMetrics:
    pages = tuple(page_metrics(layout, t, speeds, timing, reach) for t in trajectories)
    faces = len(trajectories)
    flips = flips_for(faces, sides)

    manipulation: float | None = None
    if costs.known:
        manipulation = flips * (float(costs.flip_seconds) + float(costs.realign_seconds)
                                + float(costs.check_seconds))

    return JobMetrics(
        pages=pages,
        sides=sides,
        faces=faces,
        sheets=sheets_for(faces, sides),
        steps=manual_steps(faces, sides),
        manipulation_seconds=manipulation,
        speeds=speeds,
        timing=timing,
        costs=costs,
    )
