"""Trajectoires monotraits en coordonnées page (mm).

Repère page : origine au coin haut-gauche, x vers la droite, y vers le BAS
(même convention que le SVG produit). Un `Stroke` = une pose de plume ; entre
deux `Stroke` il y a une levée explicite, matérialisée par un déplacement à vide.

Un caractère NON pris en charge ne produit AUCUN trait : rien n'est inventé et
rien n'est substitué. Sa position est conservée dans `unsupported_marks` pour
être signalée dans l'aperçu et dans le rapport.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import numeric as num
from .layout import LayoutResult
from .paper import PaperProfile
from .errors import ProfileError


@dataclass(frozen=True)
class SpeedProfile:
    """Vitesses DÉCLARÉES de démonstration — non mesurées sur une machine."""

    id: str
    version: str
    measured: bool
    draw_speed_mm_s: float
    travel_speed_mm_s: float
    provenance: str

    def __post_init__(self) -> None:
        problems = self.numeric_problems()
        if problems:
            raise ProfileError(
                f"profil de vitesses {self.id}@{self.version} incohérent : "
                + " ; ".join(problems)
            )

    def numeric_problems(self) -> tuple[str, ...]:
        p: list[str] = []
        if not isinstance(self.id, str) or not self.id.strip():
            p.append("id : identifiant vide")
        if not isinstance(self.version, str) or not self.version.strip():
            p.append("version : version vide")
        if not isinstance(self.measured, bool):
            p.append("measured : booléen attendu")
        num.require_positive(p, "draw_speed_mm_s", self.draw_speed_mm_s)
        num.require_positive(p, "travel_speed_mm_s", self.travel_speed_mm_s)
        return tuple(p)

    def ref(self) -> str:
        return f"{self.id}@{self.version}"

    def as_dict(self) -> dict:
        return {
            "profil": self.ref(),
            "mesure_sur_machine_reelle": self.measured,
            "vitesse_trace_mm_s": self.draw_speed_mm_s,
            "vitesse_deplacement_mm_s": self.travel_speed_mm_s,
            "provenance": self.provenance,
        }


DEMO_SPEEDS = SpeedProfile(
    id="demo-speeds",
    version="1.0.0",
    measured=False,
    draw_speed_mm_s=20.0,
    travel_speed_mm_s=60.0,
    provenance=(
        "Valeurs de démonstration choisies dans paperx/strokes.py pour exercer le "
        "validateur. Aucune mesure sur machine réelle, aucun essai d'écriture."
    ),
)


def _is_point(value: object) -> bool:
    """Un point valide = couple de réels finis."""
    return (
        isinstance(value, tuple) and len(value) == 2
        and num.is_finite(value[0]) and num.is_finite(value[1])
    )


@dataclass(frozen=True)
class Stroke:
    """Un trait continu, plume posée."""

    points: tuple[tuple[float, float], ...]
    speed_mm_s: float
    char_index: int | None
    char: str | None

    @property
    def length_mm(self) -> float:
        """Longueur tracée. Robuste : renvoie `inf` plutôt que de déborder, et
        `nan` si un point est malformé — jamais d'exception."""
        total = 0.0
        for a, b in zip(self.points, self.points[1:]):
            if not (_is_point(a) and _is_point(b)):
                return float("nan")
            total += num.safe_hypot(b[0] - a[0], b[1] - a[1])
        return total


@dataclass(frozen=True)
class UnsupportedMark:
    """Emplacement laissé VIDE parce que le caractère n'est pas pris en charge."""

    char_index: int
    char: str
    codepoint: str
    x_mm: float
    baseline_y_mm: float
    width_mm: float
    height_mm: float


@dataclass(frozen=True)
class PageTrajectory:
    page_number: int
    strokes: tuple[Stroke, ...]
    unsupported_marks: tuple[UnsupportedMark, ...]
    paper_ref: str
    hand_ref: str
    speed_ref: str

    @property
    def pen_lifts(self) -> int:
        """Levées de plume : une entre chaque paire de traits consécutifs."""
        return max(0, len(self.strokes) - 1)

    @property
    def point_count(self) -> int:
        return sum(len(s.points) for s in self.strokes)

    @property
    def draw_length_mm(self) -> float:
        return sum(s.length_mm for s in self.strokes)

    def travel_length_mm(self) -> float:
        """Longueur cumulée des déplacements plume levée.

        Les traits vides ou malformés sont ignorés ici : ils sont refusés par le
        validateur, qui doit pouvoir rendre un verdict sans planter.
        """
        total = 0.0
        previous: tuple[float, float] | None = None
        for stroke in self.strokes:
            if not stroke.points:
                continue
            first, last = stroke.points[0], stroke.points[-1]
            if not (_is_point(first) and _is_point(last)):
                previous = None
                continue
            if previous is not None:
                total += num.safe_hypot(first[0] - previous[0], first[1] - previous[1])
            previous = last
        return total

    def bounds_mm(self) -> tuple[float, float, float, float] | None:
        pts = [p for s in self.strokes for p in s.points if _is_point(p)]
        if not pts:
            return None
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return (min(xs), min(ys), max(xs), max(ys))


def build_page(layout: LayoutResult, page_number: int,
               speeds: SpeedProfile = DEMO_SPEEDS) -> PageTrajectory:
    paper: PaperProfile = layout.paper
    hand = layout.hand
    em = paper.font_size_mm
    page = next(p for p in layout.pages if p.number == page_number)

    strokes: list[Stroke] = []
    marks: list[UnsupportedMark] = []
    for line in page.lines:
        for placed in line.chars:
            if not placed.supported:
                marks.append(UnsupportedMark(
                    char_index=placed.index,
                    char=placed.char,
                    codepoint=f"U+{ord(placed.char):04X}",
                    x_mm=placed.x_mm,
                    baseline_y_mm=placed.baseline_y_mm,
                    width_mm=placed.advance_mm,
                    height_mm=hand.CAP_HEIGHT * em,
                ))
                continue
            glyph = hand.GLYPHS.get(placed.char)
            if glyph is None:      # espaces : avance seule, aucun trait
                continue
            for gs in glyph.strokes:
                pts = tuple(
                    (placed.x_mm + gx * em, placed.baseline_y_mm - gy * em)
                    for (gx, gy) in gs
                )
                strokes.append(Stroke(pts, speeds.draw_speed_mm_s, placed.index, placed.char))

    return PageTrajectory(
        page_number=page_number,
        strokes=tuple(strokes),
        unsupported_marks=tuple(marks),
        paper_ref=paper.ref(),
        hand_ref=layout.hand_ref,
        speed_ref=speeds.ref(),
    )


def build_all(layout: LayoutResult,
              speeds: SpeedProfile = DEMO_SPEEDS) -> tuple[PageTrajectory, ...]:
    return tuple(build_page(layout, page.number, speeds) for page in layout.pages)
