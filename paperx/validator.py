"""Validateur déterministe de trajectoires.

Contrôles : nombres finis (NaN / inf refusés), bornes page et marges, vitesses,
levées de plume, versionnement des profils, calibration machine et zones
inaccessibles. Deux verdicts distincts :

- `trajectoire_valide` : les données elles-mêmes sont saines (aperçu possible) ;
- `pret_machine` : rien ne s'oppose à une sortie machine. Il est FAUX tant que
  la machine n'est pas réellement calibrée, et cela n'est pas contournable ici.

Le résultat est déterministe : mêmes entrées -> mêmes constats, dans le même
ordre (tri par code puis par localisation).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .errors import ProfileError
from .machine import MachineProfile, Placement, ReachabilityReport, reachability
from .paper import PaperProfile
from .strokes import PageTrajectory, SpeedProfile

SEVERITY_ERROR = "erreur"                 # trajectoire invalide
SEVERITY_MACHINE_BLOCK = "bloquant_machine"  # valide, mais interdit d'envoi machine
SEVERITY_WARNING = "avertissement"

_SEVERITY_ORDER = {SEVERITY_ERROR: 0, SEVERITY_MACHINE_BLOCK: 1, SEVERITY_WARNING: 2}

VALIDATOR_ID = "paperx-validator"
VALIDATOR_VERSION = "1.0.0"


@dataclass(frozen=True)
class ValidationLimits:
    """Limites de validation, versionnées et déclarées."""

    id: str
    version: str
    max_segment_len_mm: float
    min_segment_len_mm: float
    max_points_per_page: int
    provenance: str

    def __post_init__(self) -> None:
        if not self.id or not self.version:
            raise ProfileError("limites de validation sans identifiant ou sans version")

    def ref(self) -> str:
        return f"{self.id}@{self.version}"

    def as_dict(self) -> dict:
        return {
            "profil": self.ref(),
            "segment_max_mm": self.max_segment_len_mm,
            "segment_min_mm": self.min_segment_len_mm,
            "points_max_par_page": self.max_points_per_page,
            "provenance": self.provenance,
        }


DEFAULT_LIMITS = ValidationLimits(
    id="demo-limits",
    version="1.0.0",
    max_segment_len_mm=25.0,
    min_segment_len_mm=0.01,
    max_points_per_page=400_000,
    provenance=(
        "Garde-fous choisis dans paperx/validator.py pour exercer la validation. "
        "Non mesurés sur machine."
    ),
)


@dataclass(frozen=True)
class Issue:
    code: str
    severity: str
    message: str
    count: int
    loci: tuple[str, ...] = field(default=())

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "gravite": self.severity,
            "message": self.message,
            "occurrences": self.count,
            "exemples": list(self.loci),
        }


@dataclass(frozen=True)
class ValidationReport:
    validator_ref: str
    page_number: int
    profiles: tuple[str, ...]
    issues: tuple[Issue, ...]
    reach: ReachabilityReport
    stats: dict

    @property
    def trajectory_valid(self) -> bool:
        return not any(i.severity == SEVERITY_ERROR for i in self.issues)

    @property
    def machine_ready(self) -> bool:
        return self.trajectory_valid and not any(
            i.severity == SEVERITY_MACHINE_BLOCK for i in self.issues)

    def codes(self) -> tuple[str, ...]:
        return tuple(i.code for i in self.issues)

    def as_dict(self) -> dict:
        return {
            "validateur": self.validator_ref,
            "page": self.page_number,
            "profils": list(self.profiles),
            "trajectoire_valide": self.trajectory_valid,
            "pret_machine": self.machine_ready,
            "constats": [i.as_dict() for i in self.issues],
            "atteignabilite": self.reach.as_dict(),
            "statistiques": self.stats,
        }


class _Collector:
    def __init__(self) -> None:
        self._buckets: dict[tuple[str, str, str], list[str]] = {}

    def add(self, code: str, severity: str, message: str, locus: str) -> None:
        self._buckets.setdefault((code, severity, message), []).append(locus)

    def issues(self, max_examples: int = 5) -> tuple[Issue, ...]:
        out = [
            Issue(code, severity, message, len(loci), tuple(loci[:max_examples]))
            for (code, severity, message), loci in self._buckets.items()
        ]
        out.sort(key=lambda i: (_SEVERITY_ORDER.get(i.severity, 9), i.code))
        return tuple(out)


def _ref_is_versioned(ref: str) -> bool:
    if "@" not in ref:
        return False
    ident, _, version = ref.partition("@")
    return bool(ident.strip()) and bool(version.strip())


def validate_page(
    traj: PageTrajectory,
    paper: PaperProfile,
    machine: MachineProfile,
    speeds: SpeedProfile,
    limits: ValidationLimits = DEFAULT_LIMITS,
    placement: Placement | None = None,
) -> ValidationReport:
    col = _Collector()

    # --- Profils versionnés --------------------------------------------------
    refs = (paper.ref(), machine.ref(), speeds.ref(), limits.ref(),
            traj.hand_ref, traj.paper_ref)
    for ref in refs:
        if not _ref_is_versioned(ref):
            col.add("PROFIL_NON_VERSIONNE", SEVERITY_ERROR,
                    "un profil utilisé n'est pas versionné (forme attendue : id@version)",
                    ref)
    if traj.paper_ref != paper.ref():
        col.add("PROFIL_PAPIER_DIVERGENT", SEVERITY_ERROR,
                "la trajectoire a été construite avec un autre profil papier",
                f"{traj.paper_ref} != {paper.ref()}")
    if traj.speed_ref != speeds.ref():
        col.add("PROFIL_VITESSE_DIVERGENT", SEVERITY_ERROR,
                "la trajectoire a été construite avec un autre profil de vitesses",
                f"{traj.speed_ref} != {speeds.ref()}")

    # --- Calibration : verrou de sortie machine ------------------------------
    if not machine.calibrated:
        col.add("MACHINE_NON_CALIBREE", SEVERITY_MACHINE_BLOCK,
                "profil machine non calibré : aucune sortie machine autorisée",
                machine.ref())
    if machine.pen_z_height_mm is None or machine.z_offset_mm is None:
        col.add("HAUTEUR_PLUME_INCONNUE", SEVERITY_MACHINE_BLOCK,
                "hauteur de plume et/ou offset Z inconnus : rien n'est deviné",
                machine.ref())
    reach = reachability(paper, machine, placement)
    if reach.hypothesis:
        col.add("POSE_FEUILLE_NON_MESUREE", SEVERITY_MACHINE_BLOCK,
                "la pose de la feuille est une hypothèse non mesurée ; "
                "l'atteignabilité ci-dessous est donc hypothétique",
                reach.placement.label)

    # --- Parcours des traits -------------------------------------------------
    x_min, x_max = 0.0, paper.width_mm
    y_min, y_max = 0.0, paper.height_mm
    m_left, m_right = paper.margin_left_mm, paper.width_mm - paper.margin_right_mm
    m_top, m_bottom = paper.margin_top_mm, paper.height_mm - paper.margin_bottom_mm

    unreachable_points = 0
    unreachable_chars: set[int] = set()
    longest_segment = 0.0

    for si, stroke in enumerate(traj.strokes):
        where = f"page {traj.page_number}, trait {si}"
        if not math.isfinite(stroke.speed_mm_s):
            col.add("VITESSE_NON_FINIE", SEVERITY_ERROR,
                    "vitesse non finie (NaN ou inf)", where)
        elif stroke.speed_mm_s <= 0:
            col.add("VITESSE_NON_POSITIVE", SEVERITY_ERROR,
                    "vitesse nulle ou négative", where)
        elif stroke.speed_mm_s > machine.max_draw_speed_mm_s:
            col.add("VITESSE_TRACE_EXCESSIVE", SEVERITY_ERROR,
                    f"vitesse de tracé supérieure au plafond machine "
                    f"({machine.max_draw_speed_mm_s} mm/s)",
                    f"{where} : {stroke.speed_mm_s} mm/s")

        if len(stroke.points) < 2:
            col.add("TRAIT_DEGENERE", SEVERITY_ERROR,
                    "trait comportant moins de deux points", where)

        for pi, (x, y) in enumerate(stroke.points):
            locus = f"{where}, point {pi}"
            if not (math.isfinite(x) and math.isfinite(y)):
                col.add("COORDONNEE_NON_FINIE", SEVERITY_ERROR,
                        "coordonnée non finie (NaN ou inf)", locus)
                continue
            if not (x_min <= x <= x_max and y_min <= y <= y_max):
                col.add("HORS_PAGE", SEVERITY_ERROR,
                        f"point hors de la feuille {paper.width_mm}x{paper.height_mm} mm",
                        f"{locus} ({x:.3f}, {y:.3f})")
            elif not (m_left <= x <= m_right and m_top <= y <= m_bottom):
                col.add("HORS_MARGES", SEVERITY_WARNING,
                        "point hors de la zone utile définie par les marges",
                        f"{locus} ({x:.3f}, {y:.3f})")
            if reach.is_unreachable_point(x, y):
                unreachable_points += 1
                if stroke.char_index is not None:
                    unreachable_chars.add(stroke.char_index)

        for pi, ((x0, y0), (x1, y1)) in enumerate(zip(stroke.points, stroke.points[1:])):
            if not all(math.isfinite(v) for v in (x0, y0, x1, y1)):
                continue
            seg = math.hypot(x1 - x0, y1 - y0)
            longest_segment = max(longest_segment, seg)
            if seg < limits.min_segment_len_mm:
                col.add("SEGMENT_NUL", SEVERITY_WARNING,
                        f"segment plus court que {limits.min_segment_len_mm} mm "
                        "(point dupliqué ou inutile)",
                        f"{where}, segment {pi}")
            elif seg > limits.max_segment_len_mm:
                col.add("SEGMENT_TROP_LONG", SEVERITY_WARNING,
                        f"segment plus long que {limits.max_segment_len_mm} mm",
                        f"{where}, segment {pi} : {seg:.2f} mm")

    # --- Levées de plume -----------------------------------------------------
    if traj.pen_lifts > machine.max_pen_lifts_per_page:
        col.add("LEVEES_EXCESSIVES", SEVERITY_ERROR,
                f"plus de {machine.max_pen_lifts_per_page} levées sur la page",
                f"page {traj.page_number} : {traj.pen_lifts}")
    for si, (prev, nxt) in enumerate(zip(traj.strokes, traj.strokes[1:])):
        if not prev.points or not nxt.points:
            continue
        (ax, ay), (bx, by) = prev.points[-1], nxt.points[0]
        if all(math.isfinite(v) for v in (ax, ay, bx, by)) and math.hypot(bx - ax, by - ay) < 1e-9:
            col.add("LEVEE_INUTILE", SEVERITY_WARNING,
                    "levée de plume entre deux traits jointifs", f"traits {si}/{si + 1}")

    if traj.point_count > limits.max_points_per_page:
        col.add("TROP_DE_POINTS", SEVERITY_ERROR,
                f"plus de {limits.max_points_per_page} points sur la page",
                str(traj.point_count))

    travel = traj.travel_length_mm()
    if speeds.travel_speed_mm_s > machine.max_travel_speed_mm_s:
        col.add("VITESSE_DEPLACEMENT_EXCESSIVE", SEVERITY_ERROR,
                f"vitesse de déplacement supérieure au plafond machine "
                f"({machine.max_travel_speed_mm_s} mm/s)",
                f"{speeds.travel_speed_mm_s} mm/s")

    if unreachable_points:
        col.add("ZONE_INACCESSIBLE", SEVERITY_MACHINE_BLOCK,
                "des points de tracé tombent dans une zone hors course machine ; "
                "aucune mise à l'échelle n'est appliquée pour les y ramener",
                f"page {traj.page_number} : {unreachable_points} points, "
                f"{len(unreachable_chars)} caractères")

    for mark in traj.unsupported_marks:
        col.add("CARACTERE_SANS_TRACE", SEVERITY_MACHINE_BLOCK,
                "caractère non pris en charge : aucun trait produit, emplacement "
                "laissé vide et signalé (jamais supprimé ni remplacé)",
                f"index {mark.char_index} {mark.codepoint}")

    stats = {
        "traits": len(traj.strokes),
        "points": traj.point_count,
        "levees_plume": traj.pen_lifts,
        "longueur_tracee_mm": round(traj.draw_length_mm, 2),
        "longueur_deplacements_mm": round(travel, 2),
        "segment_le_plus_long_mm": round(longest_segment, 3),
        "points_en_zone_inaccessible": unreachable_points,
        "caracteres_en_zone_inaccessible": len(unreachable_chars),
        "caracteres_sans_trace": len(traj.unsupported_marks),
        "duree_theorique_s": round(
            (traj.draw_length_mm / speeds.draw_speed_mm_s
             + travel / speeds.travel_speed_mm_s), 1)
        if speeds.draw_speed_mm_s > 0 and speeds.travel_speed_mm_s > 0 else None,
    }

    return ValidationReport(
        validator_ref=f"{VALIDATOR_ID}@{VALIDATOR_VERSION}",
        page_number=traj.page_number,
        profiles=refs,
        issues=col.issues(),
        reach=reach,
        stats=stats,
    )
