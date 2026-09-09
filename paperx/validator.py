"""Validateur déterministe de trajectoires.

Contrôles : nombres finis (NaN, ±inf et magnitudes hors domaine refusés) sur
**tous** les profils comme sur les points, bornes page et marges, vitesses,
levées de plume, versionnement des profils, calibration machine et zones
inaccessibles. Aucun cas ne doit produire d'exception non maîtrisée : une
trajectoire malformée donne un refus déterministe, pas une trace d'erreur.

Deux verdicts distincts :

- `trajectoire_valide` : les données elles-mêmes sont saines (aperçu possible) ;
- `pret_machine` : rien ne s'oppose à une sortie machine.

LIMITE ASSUMÉE DU VALIDATEUR — il valide des NOMBRES et une GÉOMÉTRIE de page.
Il ne représente pas les offsets XY réels entre l'origine machine et la feuille,
les hauteurs de contact et de levée de la plume, les obstacles physiques, ni
l'état de la machine. Un profil ne devient donc jamais « prêt machine » ici :
`paperx.gate.MACHINE_OUTPUT_AVAILABLE` est faux et le constat `CHAINE_NON_VALIDEE`
est émis systématiquement. Passer `calibrated=True` dans le code ne prouve rien
et ne débloque rien.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import gate
from . import numeric as num
from .errors import ProfileError
from .machine import MachineProfile, Placement, ReachabilityReport, reachability
from .paper import PaperProfile
from .strokes import PageTrajectory, SpeedProfile, _is_point

SEVERITY_ERROR = "erreur"                     # trajectoire invalide
SEVERITY_MACHINE_BLOCK = "bloquant_machine"   # valide, mais interdit d'envoi machine
SEVERITY_WARNING = "avertissement"

_SEVERITY_ORDER = {SEVERITY_ERROR: 0, SEVERITY_MACHINE_BLOCK: 1, SEVERITY_WARNING: 2}

VALIDATOR_ID = "paperx-validator"
VALIDATOR_VERSION = "1.1.0"


@dataclass(frozen=True)
class ValidationLimits:
    """Limites de validation, versionnées et déclarées."""

    id: str
    version: str
    max_segment_len_mm: float
    min_segment_len_mm: float
    max_points_per_page: int
    max_abs_coord_mm: float
    provenance: str

    def __post_init__(self) -> None:
        problems = self.numeric_problems()
        if problems:
            raise ProfileError(
                f"limites {self.id}@{self.version} incohérentes : " + " ; ".join(problems))

    def numeric_problems(self) -> tuple[str, ...]:
        p: list[str] = []
        if not isinstance(self.id, str) or not self.id.strip():
            p.append("id : identifiant vide")
        if not isinstance(self.version, str) or not self.version.strip():
            p.append("version : version vide")
        num.require_positive(p, "max_segment_len_mm", self.max_segment_len_mm)
        num.require_non_negative(p, "min_segment_len_mm", self.min_segment_len_mm)
        num.require_positive(p, "max_abs_coord_mm", self.max_abs_coord_mm)
        num.require_int(p, "max_points_per_page", self.max_points_per_page, minimum=1)
        if not p and self.min_segment_len_mm >= self.max_segment_len_mm:
            p.append("min_segment_len_mm doit être strictement inférieur à max_segment_len_mm")
        return tuple(p)

    def ref(self) -> str:
        return f"{self.id}@{self.version}"

    def as_dict(self) -> dict:
        return {
            "profil": self.ref(),
            "segment_max_mm": self.max_segment_len_mm,
            "segment_min_mm": self.min_segment_len_mm,
            "points_max_par_page": self.max_points_per_page,
            "coordonnee_max_mm": self.max_abs_coord_mm,
            "provenance": self.provenance,
        }


DEFAULT_LIMITS = ValidationLimits(
    id="demo-limits",
    version="1.1.0",
    max_segment_len_mm=25.0,
    min_segment_len_mm=0.01,
    max_points_per_page=400_000,
    max_abs_coord_mm=1000.0,
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
    page_number: int | None
    profiles: tuple[str, ...]
    issues: tuple[Issue, ...]
    reach: ReachabilityReport | None
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

    def blocking_codes(self) -> tuple[str, ...]:
        return tuple(i.code for i in self.issues
                     if i.severity in (SEVERITY_ERROR, SEVERITY_MACHINE_BLOCK))

    def as_dict(self) -> dict:
        return {
            "validateur": self.validator_ref,
            "page": self.page_number,
            "profils": list(self.profiles),
            "trajectoire_valide": self.trajectory_valid,
            "pret_machine": self.machine_ready,
            "constats": [i.as_dict() for i in self.issues],
            "atteignabilite": self.reach.as_dict() if self.reach else None,
            "statistiques": self.stats,
            "limite_validateur": (
                "Ce validateur contrôle des nombres et une géométrie de page. Il ne "
                "modélise ni les offsets XY réels, ni les hauteurs de contact et de "
                "levée, ni les obstacles physiques, ni l'état de la machine."
            ),
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


def _ref_is_versioned(ref: object) -> bool:
    if not isinstance(ref, str) or "@" not in ref:
        return False
    ident, _, version = ref.partition("@")
    return bool(ident.strip()) and bool(version.strip())


def _round_or_none(value: float, digits: int) -> float | None:
    """Arrondi sûr : `None` si la valeur n'est pas finie (JSON strict, sans NaN)."""
    return round(float(value), digits) if num.is_finite(value) else None


def validate_page(
    traj: PageTrajectory,
    paper: PaperProfile,
    machine: MachineProfile,
    speeds: SpeedProfile,
    limits: ValidationLimits = DEFAULT_LIMITS,
    placement: Placement | None = None,
) -> ValidationReport:
    col = _Collector()

    # --- 1. Profils : versionnement et santé numérique complète --------------
    refs = tuple(str(r) for r in (paper.ref(), machine.ref(), speeds.ref(), limits.ref(),
                                  traj.hand_ref, traj.paper_ref, traj.speed_ref))
    for ref in refs:
        if not _ref_is_versioned(ref):
            col.add("PROFIL_NON_VERSIONNE", SEVERITY_ERROR,
                    "un profil utilisé n'est pas versionné (forme attendue : id@version)",
                    ref)

    profile_objects: list[tuple[str, object]] = [
        ("papier", paper), ("machine", machine), ("vitesses", speeds), ("limites", limits)
    ]
    if placement is not None:
        profile_objects.append(("pose_feuille", placement))
    if machine.placement is not None:
        profile_objects.append(("pose_feuille_machine", machine.placement))

    profiles_sane = True
    for label, obj in profile_objects:
        problems = obj.numeric_problems()  # type: ignore[attr-defined]
        for problem in problems:
            profiles_sane = False
            col.add("PROFIL_NUMERIQUE_INVALIDE", SEVERITY_ERROR,
                    "valeur de profil non finie ou hors domaine ; aucun calcul machine "
                    "ne peut s'appuyer dessus",
                    f"{label} {getattr(obj, 'ref', lambda: label)()} : {problem}"
                    if hasattr(obj, "ref") else f"{label} : {problem}")

    if traj.paper_ref != paper.ref():
        col.add("PROFIL_PAPIER_DIVERGENT", SEVERITY_ERROR,
                "la trajectoire a été construite avec un autre profil papier",
                f"{traj.paper_ref} != {paper.ref()}")
    if traj.speed_ref != speeds.ref():
        col.add("PROFIL_VITESSE_DIVERGENT", SEVERITY_ERROR,
                "la trajectoire a été construite avec un autre profil de vitesses",
                f"{traj.speed_ref} != {speeds.ref()}")

    # --- 2. Profils non mesurés : jamais « prêt machine » --------------------
    if not paper.measured:
        col.add("PAPIER_NON_MESURE", SEVERITY_MACHINE_BLOCK,
                "profil papier de démonstration, non mesuré sur un papier réel",
                paper.ref())
    if not speeds.measured:
        col.add("VITESSES_NON_MESUREES", SEVERITY_MACHINE_BLOCK,
                "vitesses déclarées, jamais mesurées sur une machine réelle",
                speeds.ref())

    # --- 3. Calibration machine ---------------------------------------------
    if not machine.calibrated:
        col.add("MACHINE_NON_CALIBREE", SEVERITY_MACHINE_BLOCK,
                "profil machine non calibré : aucune sortie machine autorisée",
                machine.ref())
    if machine.pen_z_height_mm is None or machine.z_offset_mm is None:
        col.add("HAUTEUR_PLUME_INCONNUE", SEVERITY_MACHINE_BLOCK,
                "hauteur de plume et/ou offset Z inconnus : rien n'est deviné",
                machine.ref())

    # --- 4. Verrou global : la chaîne n'est pas validée de bout en bout ------
    if not gate.MACHINE_OUTPUT_AVAILABLE:
        col.add(gate.GATE_CODE, SEVERITY_MACHINE_BLOCK, gate.GATE_REASON,
                "paperx.gate.MACHINE_OUTPUT_AVAILABLE = False")

    # --- 5. Atteignabilité ---------------------------------------------------
    reach: ReachabilityReport | None = None
    if profiles_sane:
        reach = reachability(paper, machine, placement)
        if reach.hypothesis:
            col.add("POSE_FEUILLE_NON_MESUREE", SEVERITY_MACHINE_BLOCK,
                    "la pose de la feuille est une hypothèse non mesurée ; "
                    "l'atteignabilité ci-dessous est donc hypothétique",
                    reach.placement.label)
    else:
        col.add("ATTEIGNABILITE_NON_CALCULEE", SEVERITY_MACHINE_BLOCK,
                "atteignabilité non calculée : des profils portent des valeurs "
                "invalides", "voir PROFIL_NUMERIQUE_INVALIDE")

    # --- 6. Parcours des traits ---------------------------------------------
    page_ok = isinstance(traj.page_number, int) and not isinstance(traj.page_number, bool)
    if not page_ok:
        col.add("PAGE_INVALIDE", SEVERITY_ERROR, "numéro de page non entier",
                repr(traj.page_number))

    x_max_page, y_max_page = paper.width_mm, paper.height_mm
    m_left, m_right = paper.margin_left_mm, paper.width_mm - paper.margin_right_mm
    m_top, m_bottom = paper.margin_top_mm, paper.height_mm - paper.margin_bottom_mm
    geometry_checkable = profiles_sane

    unreachable_points = 0
    unreachable_chars: set[int] = set()
    longest_segment = 0.0
    draw_length = 0.0
    length_finite = True

    for si, stroke in enumerate(traj.strokes):
        where = f"page {traj.page_number}, trait {si}"

        if not num.is_finite(stroke.speed_mm_s):
            col.add("VITESSE_NON_FINIE", SEVERITY_ERROR,
                    "vitesse non finie (NaN, inf ou non numérique)", where)
        elif stroke.speed_mm_s <= 0:
            col.add("VITESSE_NON_POSITIVE", SEVERITY_ERROR,
                    "vitesse nulle ou négative", where)
        elif num.is_finite(machine.max_draw_speed_mm_s) and \
                stroke.speed_mm_s > machine.max_draw_speed_mm_s:
            col.add("VITESSE_TRACE_EXCESSIVE", SEVERITY_ERROR,
                    f"vitesse de tracé supérieure au plafond machine "
                    f"({machine.max_draw_speed_mm_s} mm/s)",
                    f"{where} : {stroke.speed_mm_s} mm/s")

        if not isinstance(stroke.points, tuple):
            col.add("TRAIT_MALFORME", SEVERITY_ERROR,
                    "les points d'un trait doivent être un tuple", where)
            continue
        if len(stroke.points) < 2:
            col.add("TRAIT_DEGENERE", SEVERITY_ERROR,
                    "trait comportant moins de deux points (trait vide ou incomplet)",
                    f"{where} : {len(stroke.points)} point(s)")

        for pi, point in enumerate(stroke.points):
            locus = f"{where}, point {pi}"
            if not isinstance(point, tuple) or len(point) != 2:
                col.add("POINT_MALFORME", SEVERITY_ERROR,
                        "point qui n'est pas un couple (x, y)", f"{locus} : {point!r}")
                continue
            x, y = point
            if not (num.is_finite(x) and num.is_finite(y)):
                col.add("COORDONNEE_NON_FINIE", SEVERITY_ERROR,
                        "coordonnée non finie (NaN, inf ou non numérique)",
                        f"{locus} : {point!r}")
                continue
            if abs(x) > limits.max_abs_coord_mm or abs(y) > limits.max_abs_coord_mm:
                col.add("COORDONNEE_HORS_DOMAINE", SEVERITY_ERROR,
                        f"coordonnée finie mais hors domaine "
                        f"(|valeur| > {limits.max_abs_coord_mm} mm) : refus déterministe "
                        "avant tout calcul de longueur",
                        f"{locus} : ({x!r}, {y!r})")
                continue
            if not geometry_checkable:
                continue
            if not (0.0 <= x <= x_max_page and 0.0 <= y <= y_max_page):
                col.add("HORS_PAGE", SEVERITY_ERROR,
                        f"point hors de la feuille {paper.width_mm}x{paper.height_mm} mm",
                        f"{locus} ({x:.3f}, {y:.3f})")
            elif not (m_left <= x <= m_right and m_top <= y <= m_bottom):
                col.add("HORS_MARGES", SEVERITY_WARNING,
                        "point hors de la zone utile définie par les marges",
                        f"{locus} ({x:.3f}, {y:.3f})")
            if reach is not None and reach.is_unreachable_point(x, y):
                unreachable_points += 1
                if stroke.char_index is not None:
                    unreachable_chars.add(stroke.char_index)

        for pi, (a, b) in enumerate(zip(stroke.points, stroke.points[1:])):
            if not (_is_point(a) and _is_point(b)):
                continue
            seg = num.safe_hypot(b[0] - a[0], b[1] - a[1])
            if not math.isfinite(seg):
                length_finite = False
                col.add("LONGUEUR_NON_FINIE", SEVERITY_ERROR,
                        "longueur de segment non finie (débordement de calcul)",
                        f"{where}, segment {pi}")
                continue
            draw_length += seg
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

    # --- 7. Levées de plume --------------------------------------------------
    if num.is_real(machine.max_pen_lifts_per_page) and \
            traj.pen_lifts > machine.max_pen_lifts_per_page:
        col.add("LEVEES_EXCESSIVES", SEVERITY_ERROR,
                f"plus de {machine.max_pen_lifts_per_page} levées sur la page",
                f"page {traj.page_number} : {traj.pen_lifts}")
    for si, (prev, nxt) in enumerate(zip(traj.strokes, traj.strokes[1:])):
        if not prev.points or not nxt.points:
            continue
        a, b = prev.points[-1], nxt.points[0]
        if _is_point(a) and _is_point(b) and num.safe_hypot(b[0] - a[0], b[1] - a[1]) < 1e-9:
            col.add("LEVEE_INUTILE", SEVERITY_WARNING,
                    "levée de plume entre deux traits jointifs", f"traits {si}/{si + 1}")

    if traj.point_count > limits.max_points_per_page:
        col.add("TROP_DE_POINTS", SEVERITY_ERROR,
                f"plus de {limits.max_points_per_page} points sur la page",
                str(traj.point_count))

    travel = traj.travel_length_mm()
    if not num.is_finite(travel):
        length_finite = False
        col.add("LONGUEUR_NON_FINIE", SEVERITY_ERROR,
                "longueur de déplacement non finie (débordement de calcul)",
                f"page {traj.page_number}")
    if num.is_finite(speeds.travel_speed_mm_s) and num.is_finite(machine.max_travel_speed_mm_s) \
            and speeds.travel_speed_mm_s > machine.max_travel_speed_mm_s:
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

    # --- 8. Statistiques : jamais de NaN ni d'Infinity dans le rapport -------
    duration: float | None = None
    if (length_finite and num.is_finite(draw_length) and num.is_finite(travel)
            and num.is_finite(speeds.draw_speed_mm_s) and speeds.draw_speed_mm_s > 0
            and num.is_finite(speeds.travel_speed_mm_s) and speeds.travel_speed_mm_s > 0):
        duration = _round_or_none(
            draw_length / speeds.draw_speed_mm_s + travel / speeds.travel_speed_mm_s, 1)

    stats = {
        "traits": len(traj.strokes),
        "points": traj.point_count,
        "levees_plume": traj.pen_lifts,
        "longueur_tracee_mm": _round_or_none(draw_length, 2),
        "longueur_deplacements_mm": _round_or_none(travel, 2),
        "segment_le_plus_long_mm": _round_or_none(longest_segment, 3),
        "points_en_zone_inaccessible": unreachable_points,
        "caracteres_en_zone_inaccessible": len(unreachable_chars),
        "caracteres_sans_trace": len(traj.unsupported_marks),
        "duree_theorique_s": duration,
    }

    return ValidationReport(
        validator_ref=f"{VALIDATOR_ID}@{VALIDATOR_VERSION}",
        page_number=traj.page_number if page_ok else None,
        profiles=refs,
        issues=col.issues(),
        reach=reach,
        stats=stats,
    )
