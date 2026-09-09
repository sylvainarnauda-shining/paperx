"""Profils machine versionnés et calcul des zones INACCESSIBLES.

Le profil livré par défaut, `P1S_UNCALIBRATED`, est **NON CALIBRÉ** :
- aucun offset, aucune hauteur de plume, aucun Z : ces champs valent `None` et
  ne sont pas devinés ;
- la pose de la feuille n'est pas mesurée ;
- aucune sortie machine n'est autorisée (voir `paperx.emit`).

Contrainte structurelle traitée ici : une aire de travail 256 x 256 mm ne couvre
pas une feuille A4 de 210 x 297 mm. Le manque est SIGNALÉ (zones inaccessibles,
lignes et caractères concernés). Rien n'est réduit, ni le texte ni l'écriture.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import numeric as num
from .errors import ProfileError
from .paper import PaperProfile


@dataclass(frozen=True)
class Placement:
    """Pose de la feuille dans le repère machine.

    Convention DÉCLARÉE ici (et non mesurée) : le coin BAS-GAUCHE de la feuille
    est posé en (origin_x_mm, origin_y_mm) du plateau, feuille non tournée,
    axe machine y vers le haut.
    """

    origin_x_mm: float
    origin_y_mm: float
    measured: bool
    label: str

    def __post_init__(self) -> None:
        problems = self.numeric_problems()
        if problems:
            raise ProfileError("pose de feuille incohérente : " + " ; ".join(problems))

    def numeric_problems(self) -> tuple[str, ...]:
        p: list[str] = []
        num.require_in_mm_domain(p, "origin_x_mm", self.origin_x_mm)
        num.require_in_mm_domain(p, "origin_y_mm", self.origin_y_mm)
        if not isinstance(self.measured, bool):
            p.append("measured : booléen attendu")
        if not isinstance(self.label, str) or not self.label.strip():
            p.append("label : libellé vide")
        return tuple(p)

    def as_dict(self) -> dict:
        return {
            "origine_mm": [self.origin_x_mm, self.origin_y_mm],
            "mesuree": self.measured,
            "libelle": self.label,
        }


#: Hypothèse de travail, explicitement NON MESURÉE, utilisée uniquement pour
#: chiffrer l'ampleur du problème 256 x 256 face à l'A4.
HYPOTHETICAL_ORIGIN = Placement(
    origin_x_mm=0.0,
    origin_y_mm=0.0,
    measured=False,
    label="HYPOTHÈSE NON MESURÉE : feuille au coin plateau (0,0), non tournée",
)


@dataclass(frozen=True)
class MachineProfile:
    id: str
    version: str
    label: str
    calibrated: bool
    work_area_x_mm: float
    work_area_y_mm: float
    max_draw_speed_mm_s: float
    max_travel_speed_mm_s: float
    max_pen_lifts_per_page: int
    pen_z_height_mm: float | None
    z_offset_mm: float | None
    placement: Placement | None
    provenance: str

    def __post_init__(self) -> None:
        problems = self.numeric_problems()
        if problems:
            raise ProfileError(
                f"profil machine {self.id}@{self.version} incohérent : "
                + " ; ".join(problems)
            )

    def numeric_problems(self) -> tuple[str, ...]:
        """Défauts de ce profil, sans lever d'exception.

        Un profil ne devient pas crédible parce que `calibrated` vaut `True` :
        la calibration exige une pose de feuille MESURÉE et des hauteurs
        réellement connues, toutes finies.
        """
        p: list[str] = []
        if not isinstance(self.id, str) or not self.id.strip():
            p.append("id : identifiant vide")
        if not isinstance(self.version, str) or not self.version.strip():
            p.append("version : version vide")
        if not isinstance(self.calibrated, bool):
            p.append("calibrated : booléen attendu")

        for name in ("work_area_x_mm", "work_area_y_mm",
                     "max_draw_speed_mm_s", "max_travel_speed_mm_s"):
            num.require_positive(p, name, getattr(self, name))
        num.require_in_mm_domain(p, "work_area_x_mm", self.work_area_x_mm)
        num.require_in_mm_domain(p, "work_area_y_mm", self.work_area_y_mm)
        num.require_int(p, "max_pen_lifts_per_page", self.max_pen_lifts_per_page, minimum=0)

        if self.pen_z_height_mm is not None:
            num.require_positive(p, "pen_z_height_mm", self.pen_z_height_mm)
            num.require_in_mm_domain(p, "pen_z_height_mm", self.pen_z_height_mm)
        if self.z_offset_mm is not None:
            num.require_in_mm_domain(p, "z_offset_mm", self.z_offset_mm)
        if self.placement is not None:
            p.extend(f"placement.{msg}" for msg in self.placement.numeric_problems())

        if self.calibrated:
            if self.placement is None or not self.placement.measured:
                p.append("calibrated=True sans pose de feuille mesurée")
            if self.pen_z_height_mm is None:
                p.append("calibrated=True sans hauteur de plume connue")
            if self.z_offset_mm is None:
                p.append("calibrated=True sans offset Z connu")
        return tuple(p)

    def ref(self) -> str:
        return f"{self.id}@{self.version}"

    def as_dict(self) -> dict:
        return {
            "profil": self.ref(),
            "libelle": self.label,
            "calibre": self.calibrated,
            "aire_travail_mm": [self.work_area_x_mm, self.work_area_y_mm],
            "vitesse_max_trace_mm_s": self.max_draw_speed_mm_s,
            "vitesse_max_deplacement_mm_s": self.max_travel_speed_mm_s,
            "levees_max_par_page": self.max_pen_lifts_per_page,
            "hauteur_plume_mm": self.pen_z_height_mm,
            "offset_z_mm": self.z_offset_mm,
            "pose_feuille": self.placement.as_dict() if self.placement else None,
            "provenance": self.provenance,
        }


#: Profil par défaut : NON CALIBRÉ. Les seules valeurs renseignées sont l'aire de
#: travail nominale annoncée par le constructeur et des plafonds de sécurité
#: conservateurs ; aucun offset ni hauteur de plume n'est inventé.
P1S_UNCALIBRATED = MachineProfile(
    id="bambu-p1s",
    version="0.0.0+non-calibre",
    label="Bambu Lab P1S — NON CALIBRÉ (aucun essai réel, aucune mesure)",
    calibrated=False,
    work_area_x_mm=256.0,
    work_area_y_mm=256.0,
    max_draw_speed_mm_s=30.0,
    max_travel_speed_mm_s=100.0,
    max_pen_lifts_per_page=20000,
    pen_z_height_mm=None,
    z_offset_mm=None,
    placement=None,
    provenance=(
        "Aire de travail 256x256 mm = valeur nominale annoncée pour la P1S. "
        "Plafonds de vitesse = garde-fous de validation choisis ici, non mesurés. "
        "Hauteur de plume, offset Z et pose de la feuille : INCONNUS, non devinés."
    ),
)

PROFILES: dict[str, MachineProfile] = {P1S_UNCALIBRATED.id: P1S_UNCALIBRATED}


def get(profile_id: str) -> MachineProfile:
    try:
        return PROFILES[profile_id]
    except KeyError:
        raise ProfileError(
            f"profil machine inconnu : {profile_id!r} (disponibles : {sorted(PROFILES)})"
        ) from None


@dataclass(frozen=True)
class Rect:
    """Rectangle en coordonnées page (mm, origine haut-gauche, y vers le bas)."""

    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def area_mm2(self) -> float:
        return max(0.0, self.x1 - self.x0) * max(0.0, self.y1 - self.y0)

    def contains(self, x: float, y: float) -> bool:
        return self.x0 <= x <= self.x1 and self.y0 <= y <= self.y1

    def as_dict(self) -> dict:
        return {"x0": round(self.x0, 3), "y0": round(self.y0, 3),
                "x1": round(self.x1, 3), "y1": round(self.y1, 3),
                "aire_mm2": round(self.area_mm2, 1)}


@dataclass(frozen=True)
class ReachabilityReport:
    machine_ref: str
    paper_ref: str
    placement: Placement
    hypothesis: bool
    reachable: Rect | None
    unreachable: tuple[Rect, ...]
    page_area_mm2: float

    @property
    def unreachable_area_mm2(self) -> float:
        return sum(r.area_mm2 for r in self.unreachable)

    @property
    def unreachable_ratio(self) -> float:
        return self.unreachable_area_mm2 / self.page_area_mm2 if self.page_area_mm2 else 0.0

    @property
    def fully_reachable(self) -> bool:
        return not self.unreachable

    def is_unreachable_point(self, x: float, y: float) -> bool:
        return any(r.contains(x, y) for r in self.unreachable)

    def as_dict(self) -> dict:
        return {
            "machine": self.machine_ref,
            "papier": self.paper_ref,
            "pose_feuille": self.placement.as_dict(),
            "resultat_hypothetique": self.hypothesis,
            "zone_atteignable_mm": self.reachable.as_dict() if self.reachable else None,
            "zones_inaccessibles_mm": [r.as_dict() for r in self.unreachable],
            "aire_inaccessible_mm2": round(self.unreachable_area_mm2, 1),
            "part_page_inaccessible": round(self.unreachable_ratio, 4),
            "mise_a_echelle_appliquee": False,
            "note": (
                "Aucune réduction d'échelle du texte ni de l'écriture n'est appliquée "
                "pour masquer le manque de course."
            ),
        }


def reachability(paper: PaperProfile, machine: MachineProfile,
                 placement: Placement | None = None) -> ReachabilityReport:
    """Zones de la page hors d'atteinte de la machine, sous une pose donnée.

    Si aucune pose mesurée n'existe (cas par défaut), l'hypothèse explicite
    `HYPOTHETICAL_ORIGIN` est utilisée et le résultat est marqué hypothétique.
    """
    place = placement or machine.placement or HYPOTHETICAL_ORIGIN
    hypothesis = not place.measured

    # page -> machine : mx = ox + px ; my = oy + (H - py)
    ox, oy = place.origin_x_mm, place.origin_y_mm
    H, W = paper.height_mm, paper.width_mm

    px_min, px_max = -ox, machine.work_area_x_mm - ox
    py_min, py_max = oy + H - machine.work_area_y_mm, oy + H

    rx0, rx1 = max(0.0, px_min), min(W, px_max)
    ry0, ry1 = max(0.0, py_min), min(H, py_max)
    reachable = Rect(rx0, ry0, rx1, ry1) if rx1 > rx0 and ry1 > ry0 else None

    unreachable: list[Rect] = []
    if ry0 > 0.0:
        unreachable.append(Rect(0.0, 0.0, W, min(ry0, H)))          # bande haute
    if ry1 < H:
        unreachable.append(Rect(0.0, max(ry1, 0.0), W, H))          # bande basse
    if rx0 > 0.0:
        unreachable.append(Rect(0.0, max(ry0, 0.0), min(rx0, W), min(ry1, H)))
    if rx1 < W:
        unreachable.append(Rect(max(rx1, 0.0), max(ry0, 0.0), W, min(ry1, H)))
    unreachable = [r for r in unreachable if r.area_mm2 > 1e-9]

    return ReachabilityReport(
        machine_ref=machine.ref(),
        paper_ref=paper.ref(),
        placement=place,
        hypothesis=hypothesis,
        reachable=reachable,
        unreachable=tuple(unreachable),
        page_area_mm2=W * H,
    )
