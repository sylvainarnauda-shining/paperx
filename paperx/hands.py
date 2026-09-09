"""Styles d'écriture GÉNÉRIQUE SYNTHÉTIQUE, distincts et versionnés.

AUCUN de ces styles n'est l'écriture de quelqu'un. Chacun est une TRANSFORMATION
GÉOMÉTRIQUE DÉCLARÉE de l'écriture générique synthétique de
`paperx/synthetic_hand.py` : inclinaison, échelle horizontale, échelle
verticale. Les valeurs de ces transformations sont écrites en clair ici.

Ils existent pour une seule raison : donner au mode démonstration plusieurs
rendus visiblement différents sans jamais laisser croire qu'un rendu a été
appris, copié ou dérivé d'un échantillon manuscrit. `is_personalized` vaut
`False` pour tous, sans exception possible : la classe le fige.

Interface : un style expose exactement ce que `paperx.synthetic_hand` expose et
que la mise en page, les trajectoires et le jeu de caractères consomment
(`GLYPHS`, `CAP_HEIGHT`, `advance_of`, `supported_chars`, `hand_ref`, réserves
d'encre). Le module `synthetic_hand` reste la valeur par défaut partout : les
appels existants ne changent pas de comportement.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import synthetic_hand
from .errors import ProfileError
from . import numeric as num


@dataclass(frozen=True)
class HandStyle:
    """Un style synthétique : transformation déclarée du gabarit générique."""

    style_id: str
    version: str
    label: str
    provenance: str
    slant_deg: float
    x_scale: float
    y_scale: float
    GLYPHS: dict[str, synthetic_hand.Glyph] = field(repr=False)
    CAP_HEIGHT: float = synthetic_hand.CAP_HEIGHT
    SPACE_ADVANCES: dict[str, float] = field(default_factory=dict, repr=False)

    #: Immuable et non surchargeable : un style synthétique n'est jamais
    #: personnalisé, quelle que soit la transformation appliquée.
    IS_PERSONALIZED: bool = False

    def __post_init__(self) -> None:
        problems = self.numeric_problems()
        if problems:
            raise ProfileError(
                f"style {self.style_id}@{self.version} incohérent : " + " ; ".join(problems)
            )

    def numeric_problems(self) -> tuple[str, ...]:
        p: list[str] = []
        if not isinstance(self.style_id, str) or not self.style_id.strip():
            p.append("style_id : identifiant vide")
        if not isinstance(self.version, str) or not self.version.strip():
            p.append("version : version vide")
        num.require_positive(p, "x_scale", self.x_scale)
        num.require_positive(p, "y_scale", self.y_scale)
        num.require_finite(p, "slant_deg", self.slant_deg)
        if num.is_finite(self.slant_deg) and abs(float(self.slant_deg)) >= 60.0:
            p.append("slant_deg : inclinaison absurde (|angle| >= 60°)")
        if self.IS_PERSONALIZED:
            p.append("IS_PERSONALIZED : un style synthétique ne peut pas être personnalisé")
        return tuple(p)

    def ref(self) -> str:
        return f"{self.style_id}@{self.version}"

    # --- interface consommée par layout / strokes / charset -----------------

    def advance_of(self, char: str) -> float:
        if char in self.SPACE_ADVANCES:
            return self.SPACE_ADVANCES[char]
        glyph = self.GLYPHS.get(char)
        return glyph.advance if glyph is not None else synthetic_hand.TOFU_ADVANCE * self.x_scale

    def supported_chars(self) -> frozenset[str]:
        return frozenset(self.GLYPHS) | frozenset(self.SPACE_ADVANCES) | frozenset({"\n"})

    def hand_ref(self) -> str:
        return self.ref()

    def _ink_bounds(self) -> tuple[float, float, float, float]:
        xs_min = xs_over = ys_min = ys_max = 0.0
        for glyph in self.GLYPHS.values():
            for stroke in glyph.strokes:
                for x, y in stroke:
                    xs_min = min(xs_min, x)
                    xs_over = max(xs_over, x - glyph.advance)
                    ys_min = min(ys_min, y)
                    ys_max = max(ys_max, y)
        return xs_min, xs_over, ys_min, ys_max

    def ink_reserve_left_em(self) -> float:
        return max(0.0, -self._ink_bounds()[0])

    def ink_reserve_right_em(self) -> float:
        return max(0.0, self._ink_bounds()[1])

    def ink_above_baseline_em(self) -> float:
        return max(0.0, self._ink_bounds()[3])

    def ink_below_baseline_em(self) -> float:
        return max(0.0, -self._ink_bounds()[2])

    def as_dict(self) -> dict:
        return {
            "style": self.ref(),
            "libelle": self.label,
            "personnalise": self.IS_PERSONALIZED,
            "transformation": {
                "inclinaison_deg": self.slant_deg,
                "echelle_horizontale": self.x_scale,
                "echelle_verticale": self.y_scale,
            },
            "provenance": self.provenance,
        }


def _transform(slant_deg: float, x_scale: float, y_scale: float
               ) -> dict[str, synthetic_hand.Glyph]:
    """Applique cisaillement + échelles au gabarit générique.

    Ordre déclaré : mise à l'échelle (x, y) puis cisaillement horizontal
    proportionnel à y. La chasse suit `x_scale` — l'écriture n'est jamais
    resserrée en douce pour faire tenir davantage de texte.
    """
    shear = math.tan(math.radians(slant_deg))
    out: dict[str, synthetic_hand.Glyph] = {}
    for char, glyph in synthetic_hand.GLYPHS.items():
        strokes = tuple(
            tuple(((x * x_scale) + (y * y_scale) * shear, y * y_scale) for (x, y) in stroke)
            for stroke in glyph.strokes
        )
        out[char] = synthetic_hand.Glyph(char, glyph.advance * x_scale, strokes)
    return out


def _make(style_id: str, version: str, label: str, provenance: str,
          slant_deg: float, x_scale: float, y_scale: float) -> HandStyle:
    return HandStyle(
        style_id=style_id,
        version=version,
        label=label,
        provenance=provenance,
        slant_deg=slant_deg,
        x_scale=x_scale,
        y_scale=y_scale,
        GLYPHS=_transform(slant_deg, x_scale, y_scale),
        CAP_HEIGHT=synthetic_hand.CAP_HEIGHT * y_scale,
        SPACE_ADVANCES={c: a * x_scale for c, a in synthetic_hand.SPACE_ADVANCES.items()},
    )


_BASE_PROVENANCE = (
    "Transformation géométrique déclarée du gabarit de paperx/synthetic_hand.py, "
    "lui-même tracé à la main. Aucune photo, aucun échantillon manuscrit, aucun "
    "modèle appris, aucun poids. Ne ressemble à l'écriture de personne."
)

#: Style neutre : identité. Sa référence reste celle du gabarit d'origine pour
#: que rien de ce qui existait déjà ne change de version.
DROITE = HandStyle(
    style_id=synthetic_hand.HAND_ID,
    version=synthetic_hand.HAND_VERSION,
    label="Générique droite — écriture générique synthétique",
    provenance=_BASE_PROVENANCE + " Transformation : aucune (identité).",
    slant_deg=0.0,
    x_scale=1.0,
    y_scale=1.0,
    GLYPHS=dict(synthetic_hand.GLYPHS),
    CAP_HEIGHT=synthetic_hand.CAP_HEIGHT,
    SPACE_ADVANCES=dict(synthetic_hand.SPACE_ADVANCES),
)

PENCHEE = _make(
    "synthetic-penchee", "1.0.0",
    "Générique penchée — cisaillement 12°",
    _BASE_PROVENANCE + " Transformation : cisaillement horizontal de 12°.",
    slant_deg=12.0, x_scale=1.0, y_scale=1.0,
)

ETROITE = _make(
    "synthetic-etroite", "1.0.0",
    "Générique étroite — chasse × 0,86",
    _BASE_PROVENANCE + " Transformation : échelle horizontale 0,86 (chasse comprise).",
    slant_deg=0.0, x_scale=0.86, y_scale=1.0,
)

AMPLE = _make(
    "synthetic-ample", "1.0.0",
    "Générique ample — chasse × 1,12, hauteur × 1,06",
    _BASE_PROVENANCE + " Transformation : échelles 1,12 (horizontale) et 1,06 (verticale).",
    slant_deg=0.0, x_scale=1.12, y_scale=1.06,
)

#: Styles proposés en mode démonstration. Ordre stable (affichage déterministe).
STYLES: dict[str, HandStyle] = {
    s.style_id: s for s in (DROITE, PENCHEE, ETROITE, AMPLE)
}

DEFAULT_STYLE_ID = DROITE.style_id


def get(style_id: str) -> HandStyle:
    try:
        return STYLES[style_id]
    except KeyError:
        raise ProfileError(
            f"style d'écriture inconnu : {style_id!r} (disponibles : {sorted(STYLES)})"
        ) from None


def catalogue() -> list[dict]:
    """Description des styles, pour une interface. Aucun n'est personnalisé."""
    return [STYLES[k].as_dict() for k in STYLES]
