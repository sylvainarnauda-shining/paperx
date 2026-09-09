"""ÉCRITURE GÉNÉRIQUE SYNTHÉTIQUE — outil de test mécanique uniquement.

CE N'EST PAS UNE ÉCRITURE PERSONNALISÉE. Ces tracés sont écrits à la main dans
ce fichier, à partir de segments et d'arcs paramétriques. Ils ne proviennent
d'aucune photo, d'aucun échantillon manuscrit et d'aucun modèle appris. Ils ne
prétendent ressembler à l'écriture de personne.

Rôle : fournir des trajectoires monotraits déterministes pour exercer la
pagination, la validation et l'aperçu. Toute personnalisation réelle devra
passer par le contrat `paperx.provider.PersonalizationProvider`.

Repère d'un glyphe : origine sur la ligne de base, x vers la droite, y vers le
haut, unités em (1.0 = corps). Métriques : hauteur d'x 0.48, capitale 0.70,
ascendante 0.75, descendante -0.22.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# --- Identité de l'écriture, versionnée -------------------------------------

HAND_ID = "synthetic-generic"
HAND_VERSION = "1.0.0"
IS_PERSONALIZED = False
HAND_LABEL = "ÉCRITURE GÉNÉRIQUE SYNTHÉTIQUE (tests mécaniques uniquement)"
HAND_PROVENANCE = (
    "Tracés écrits à la main dans paperx/synthetic_hand.py. "
    "Aucune photo, aucun échantillon manuscrit, aucun modèle, aucun poids."
)

# --- Métriques ---------------------------------------------------------------

X_HEIGHT = 0.48
CAP_HEIGHT = 0.70
ASCENDER = 0.75
DESCENDER = -0.22
MARK_Y_LOWER = 0.54  # base des accents sur bas-de-casse
MARK_Y_UPPER = 0.76  # base des accents sur capitales
TOFU_ADVANCE = 0.52  # chasse réservée à un caractère NON pris en charge

Point = tuple[float, float]
Stroke = list[Point]


@dataclass(frozen=True)
class Glyph:
    """Un glyphe monotrait : chasse + liste de traits (un trait = plume posée)."""

    char: str
    advance: float
    strokes: tuple[tuple[Point, ...], ...]

    @property
    def pen_lifts(self) -> int:
        """Nombre de levées de plume internes au glyphe."""
        return max(0, len(self.strokes) - 1)


# --- Petit DSL de tracé ------------------------------------------------------


def _arc(cx: float, cy: float, rx: float, ry: float, a0: float, a1: float,
         step_deg: float = 18.0) -> Stroke:
    """Arc échantillonné, angles en degrés (y vers le haut, 90 = sommet)."""
    span = a1 - a0
    n = max(2, int(math.ceil(abs(span) / step_deg)) + 1)
    pts: Stroke = []
    for i in range(n):
        a = math.radians(a0 + span * i / (n - 1))
        pts.append((cx + rx * math.cos(a), cy + ry * math.sin(a)))
    return pts


def _circle(cx: float, cy: float, rx: float, ry: float, start: float = 90.0) -> Stroke:
    return _arc(cx, cy, rx, ry, start, start - 360.0)


def _cat(*parts: Stroke) -> Stroke:
    """Concatène des morceaux en un seul trait, sans point dupliqué consécutif."""
    out: Stroke = []
    for part in parts:
        for p in part:
            if out and abs(p[0] - out[-1][0]) < 1e-9 and abs(p[1] - out[-1][1]) < 1e-9:
                continue
            out.append(p)
    return out


def _L(*pts: Point) -> Stroke:
    return list(pts)


# --- Bas-de-casse ------------------------------------------------------------

_XH = X_HEIGHT
_BOWL_RY = _XH / 2

_LOWER: dict[str, tuple[float, list[Stroke]]] = {
    "a": (0.52, [_circle(0.24, _BOWL_RY, 0.17, _BOWL_RY), _L((0.41, _XH), (0.41, 0.0))]),
    "b": (0.52, [_L((0.08, ASCENDER), (0.08, 0.0)),
                 _circle(0.27, _BOWL_RY, 0.17, _BOWL_RY)]),
    "c": (0.46, [_arc(0.26, _BOWL_RY, 0.17, _BOWL_RY, -55.0, 235.0)]),
    "d": (0.52, [_circle(0.22, _BOWL_RY, 0.17, _BOWL_RY), _L((0.41, ASCENDER), (0.41, 0.0))]),
    "e": (0.48, [_cat(_L((0.43, 0.26), (0.09, 0.26)),
                      _arc(0.26, _BOWL_RY, 0.18, _BOWL_RY, 180.0, -50.0))]),
    "f": (0.34, [_cat(_L((0.13, 0.0), (0.13, 0.60)),
                      _arc(0.25, 0.60, 0.12, 0.15, 180.0, 80.0)),
                 _L((0.02, _XH), (0.32, _XH))]),
    "g": (0.52, [_circle(0.24, _BOWL_RY, 0.17, _BOWL_RY),
                 _cat(_L((0.41, _XH), (0.41, -0.12)),
                      _arc(0.28, -0.12, 0.13, 0.10, 0.0, -150.0))]),
    "h": (0.52, [_L((0.08, ASCENDER), (0.08, 0.0)),
                 _cat(_arc(0.26, 0.31, 0.18, 0.17, 180.0, 0.0), _L((0.44, 0.0)))]),
    "i": (0.24, [_L((0.11, _XH), (0.11, 0.0)), _L((0.11, 0.60), (0.11, 0.65))]),
    "i.dotless": (0.24, [_L((0.11, _XH), (0.11, 0.0))]),
    "j": (0.26, [_cat(_L((0.14, _XH), (0.14, -0.10)),
                      _arc(0.02, -0.10, 0.12, 0.10, 0.0, -150.0)),
                 _L((0.14, 0.60), (0.14, 0.65))]),
    "k": (0.48, [_L((0.08, ASCENDER), (0.08, 0.0)),
                 _L((0.40, _XH), (0.08, 0.19)), _L((0.18, 0.28), (0.42, 0.0))]),
    "l": (0.22, [_L((0.11, ASCENDER), (0.11, 0.0))]),
    "m": (0.78, [_L((0.08, _XH), (0.08, 0.0)),
                 _cat(_arc(0.22, 0.33, 0.14, 0.15, 180.0, 0.0), _L((0.36, 0.0))),
                 _cat(_arc(0.50, 0.33, 0.14, 0.15, 180.0, 0.0), _L((0.64, 0.0)))]),
    "n": (0.52, [_L((0.08, _XH), (0.08, 0.0)),
                 _cat(_arc(0.26, 0.33, 0.18, 0.15, 180.0, 0.0), _L((0.44, 0.0)))]),
    "o": (0.52, [_circle(0.26, _BOWL_RY, 0.18, _BOWL_RY)]),
    "p": (0.52, [_L((0.08, _XH), (0.08, DESCENDER)),
                 _circle(0.27, _BOWL_RY, 0.17, _BOWL_RY)]),
    "q": (0.52, [_circle(0.24, _BOWL_RY, 0.17, _BOWL_RY),
                 _L((0.41, _XH), (0.41, DESCENDER))]),
    "r": (0.36, [_L((0.10, _XH), (0.10, 0.0)),
                 _arc(0.24, 0.32, 0.14, 0.16, 180.0, 55.0)]),
    "s": (0.44, [_L((0.38, 0.40), (0.30, 0.47), (0.17, 0.46), (0.11, 0.39),
                    (0.15, 0.31), (0.29, 0.25), (0.36, 0.19), (0.35, 0.09),
                    (0.25, 0.02), (0.12, 0.03), (0.05, 0.09))]),
    "t": (0.34, [_cat(_L((0.16, 0.66), (0.16, 0.08)),
                      _arc(0.27, 0.08, 0.11, 0.08, 180.0, 250.0)),
                 _L((0.03, _XH), (0.31, _XH))]),
    "u": (0.52, [_cat(_L((0.08, _XH), (0.08, 0.14)),
                      _arc(0.26, 0.14, 0.18, 0.14, 180.0, 360.0),
                      _L((0.44, _XH)))
                 , _L((0.44, 0.14), (0.44, 0.0))]),
    "v": (0.48, [_L((0.05, _XH), (0.24, 0.0), (0.43, _XH))]),
    "w": (0.70, [_L((0.04, _XH), (0.18, 0.0), (0.33, 0.34), (0.48, 0.0), (0.62, _XH))]),
    "x": (0.46, [_L((0.05, _XH), (0.41, 0.0)), _L((0.41, _XH), (0.05, 0.0))]),
    "y": (0.48, [_L((0.05, _XH), (0.25, 0.06)),
                 _L((0.43, _XH), (0.18, DESCENDER))]),
    "z": (0.44, [_L((0.06, _XH), (0.39, _XH), (0.06, 0.02), (0.41, 0.02))]),
}

# --- Capitales ---------------------------------------------------------------

_CH = CAP_HEIGHT

_UPPER: dict[str, tuple[float, list[Stroke]]] = {
    "A": (0.62, [_L((0.04, 0.0), (0.29, _CH), (0.54, 0.0)), _L((0.13, 0.25), (0.45, 0.25))]),
    "B": (0.58, [_L((0.08, _CH), (0.08, 0.0)),
                 _cat(_L((0.08, _CH), (0.34, _CH)),
                      _arc(0.34, 0.53, 0.16, 0.17, 90.0, -90.0), _L((0.08, 0.36))),
                 _cat(_L((0.08, 0.0), (0.36, 0.0)),
                      _arc(0.36, 0.18, 0.17, 0.18, -90.0, 90.0), _L((0.08, 0.36)))]),
    "C": (0.60, [_arc(0.32, 0.35, 0.25, 0.35, -50.0, 230.0)]),
    "D": (0.62, [_cat(_L((0.08, 0.0), (0.08, _CH), (0.28, _CH)),
                      _arc(0.28, 0.35, 0.26, 0.35, 90.0, -90.0), _L((0.08, 0.0)))]),
    "E": (0.54, [_L((0.10, 0.0), (0.10, _CH), (0.46, _CH)),
                 _L((0.10, 0.36), (0.38, 0.36)), _L((0.10, 0.0), (0.47, 0.0))]),
    "F": (0.52, [_L((0.10, 0.0), (0.10, _CH), (0.46, _CH)),
                 _L((0.10, 0.37), (0.38, 0.37))]),
    "G": (0.64, [_cat(_arc(0.32, 0.35, 0.25, 0.35, -20.0, 230.0),
                      _L((0.56, 0.23), (0.56, 0.28))),
                 _L((0.40, 0.28), (0.58, 0.28))]),
    "H": (0.62, [_L((0.08, 0.0), (0.08, _CH)), _L((0.50, 0.0), (0.50, _CH)),
                 _L((0.08, 0.36), (0.50, 0.36))]),
    "I": (0.24, [_L((0.12, 0.0), (0.12, _CH))]),
    "J": (0.44, [_cat(_L((0.34, _CH), (0.34, 0.14)),
                      _arc(0.19, 0.14, 0.15, 0.14, 0.0, -170.0))]),
    "K": (0.58, [_L((0.09, 0.0), (0.09, _CH)), _L((0.48, _CH), (0.09, 0.28)),
                 _L((0.21, 0.38), (0.50, 0.0))]),
    "L": (0.50, [_L((0.10, _CH), (0.10, 0.0), (0.45, 0.0))]),
    "M": (0.74, [_L((0.06, 0.0), (0.06, _CH), (0.33, 0.22), (0.60, _CH), (0.60, 0.0))]),
    "N": (0.64, [_L((0.08, 0.0), (0.08, _CH), (0.52, 0.0), (0.52, _CH))]),
    "O": (0.68, [_circle(0.33, 0.35, 0.26, 0.35)]),
    "P": (0.56, [_cat(_L((0.09, 0.0), (0.09, _CH), (0.30, _CH)),
                      _arc(0.30, 0.52, 0.18, 0.18, 90.0, -90.0), _L((0.09, 0.34)))]),
    "Q": (0.68, [_circle(0.33, 0.35, 0.26, 0.35), _L((0.38, 0.16), (0.60, -0.08))]),
    "R": (0.58, [_cat(_L((0.09, 0.0), (0.09, _CH), (0.30, _CH)),
                      _arc(0.30, 0.52, 0.18, 0.18, 90.0, -90.0), _L((0.09, 0.34))),
                 _L((0.28, 0.34), (0.52, 0.0))]),
    "S": (0.54, [_L((0.47, 0.58), (0.38, 0.68), (0.20, 0.68), (0.11, 0.58),
                    (0.14, 0.45), (0.34, 0.36), (0.45, 0.27), (0.45, 0.12),
                    (0.34, 0.02), (0.15, 0.02), (0.06, 0.12))]),
    "T": (0.54, [_L((0.02, _CH), (0.52, _CH)), _L((0.27, _CH), (0.27, 0.0))]),
    "U": (0.62, [_cat(_L((0.08, _CH), (0.08, 0.20)),
                      _arc(0.29, 0.20, 0.21, 0.20, 180.0, 360.0),
                      _L((0.50, _CH)))]),
    "V": (0.62, [_L((0.04, _CH), (0.29, 0.0), (0.54, _CH))]),
    "W": (0.86, [_L((0.03, _CH), (0.19, 0.0), (0.37, 0.50), (0.55, 0.0), (0.72, _CH))]),
    "X": (0.60, [_L((0.06, _CH), (0.52, 0.0)), _L((0.52, _CH), (0.06, 0.0))]),
    "Y": (0.60, [_L((0.05, _CH), (0.29, 0.36), (0.53, _CH)), _L((0.29, 0.36), (0.29, 0.0))]),
    "Z": (0.56, [_L((0.07, _CH), (0.49, _CH), (0.07, 0.0), (0.51, 0.0))]),
}

# --- Chiffres ----------------------------------------------------------------

_DIGITS: dict[str, tuple[float, list[Stroke]]] = {
    "0": (0.54, [_circle(0.27, 0.35, 0.20, 0.35)]),
    "1": (0.36, [_L((0.10, 0.55), (0.22, _CH), (0.22, 0.0))]),
    "2": (0.52, [_cat(_arc(0.26, 0.50, 0.18, 0.20, 170.0, -60.0),
                      _L((0.06, 0.0), (0.46, 0.0)))]),
    "3": (0.52, [_cat(_arc(0.24, 0.53, 0.17, 0.17, 160.0, -90.0),
                      _L((0.16, 0.36), (0.24, 0.36)),
                      _arc(0.24, 0.18, 0.19, 0.18, 90.0, -160.0))]),
    "4": (0.54, [_L((0.36, 0.0), (0.36, _CH), (0.04, 0.18), (0.50, 0.18))]),
    "5": (0.52, [_cat(_L((0.44, _CH), (0.14, _CH), (0.11, 0.40), (0.26, 0.44)),
                      _arc(0.26, 0.22, 0.20, 0.22, 90.0, -160.0))]),
    "6": (0.52, [_cat(_arc(0.28, 0.48, 0.19, 0.22, 60.0, 190.0),
                      _L((0.09, 0.30), (0.09, 0.22)),
                      _arc(0.28, 0.22, 0.19, 0.22, 180.0, -180.0))]),
    "7": (0.50, [_L((0.05, _CH), (0.45, _CH), (0.19, 0.0))]),
    "8": (0.52, [_circle(0.26, 0.53, 0.16, 0.17), _circle(0.26, 0.18, 0.20, 0.18)]),
    "9": (0.52, [_circle(0.26, 0.50, 0.19, 0.20),
                 _L((0.45, 0.50), (0.43, 0.24), (0.36, 0.0))]),
}

# --- Ponctuation et signes ---------------------------------------------------

_PUNCT: dict[str, tuple[float, list[Stroke]]] = {
    ".": (0.24, [_L((0.10, 0.0), (0.12, 0.03))]),
    ",": (0.24, [_L((0.13, 0.05), (0.11, 0.0), (0.05, -0.09))]),
    ";": (0.24, [_L((0.12, 0.26), (0.14, 0.29)), _L((0.13, 0.05), (0.11, 0.0), (0.05, -0.09))]),
    ":": (0.24, [_L((0.10, 0.0), (0.12, 0.03)), _L((0.10, 0.26), (0.12, 0.29))]),
    "!": (0.26, [_L((0.13, _CH), (0.11, 0.14)), _L((0.10, 0.0), (0.12, 0.03))]),
    "?": (0.46, [_cat(_arc(0.24, 0.55, 0.16, 0.15, 175.0, -60.0), _L((0.24, 0.28), (0.22, 0.16))),
                 _L((0.21, 0.0), (0.23, 0.03))]),
    "'": (0.20, [_L((0.11, _CH), (0.08, 0.52))]),
    "’": (0.20, [_L((0.11, _CH), (0.08, 0.52))]),  # apostrophe typographique
    '"': (0.34, [_L((0.10, _CH), (0.07, 0.52)), _L((0.24, _CH), (0.21, 0.52))]),
    "«": (0.42, [_L((0.20, 0.42), (0.06, 0.24), (0.20, 0.06)),
                      _L((0.36, 0.42), (0.22, 0.24), (0.36, 0.06))]),
    "»": (0.42, [_L((0.06, 0.42), (0.20, 0.24), (0.06, 0.06)),
                      _L((0.22, 0.42), (0.36, 0.24), (0.22, 0.06))]),
    "(": (0.28, [_arc(0.30, 0.28, 0.22, 0.45, 150.0, 210.0, step_deg=12.0)]),
    ")": (0.28, [_arc(-0.02, 0.28, 0.22, 0.45, 30.0, -30.0, step_deg=12.0)]),
    "-": (0.34, [_L((0.06, 0.26), (0.28, 0.26))]),
    "–": (0.46, [_L((0.05, 0.26), (0.41, 0.26))]),  # tiret demi-cadratin
    "—": (0.62, [_L((0.04, 0.26), (0.58, 0.26))]),  # tiret cadratin
    "…": (0.62, [_L((0.08, 0.0), (0.10, 0.03)), _L((0.28, 0.0), (0.30, 0.03)),
                      _L((0.48, 0.0), (0.50, 0.03))]),   # points de suspension
    "/": (0.40, [_L((0.04, 0.0), (0.34, _CH))]),
    "°": (0.30, [_circle(0.15, 0.58, 0.09, 0.09)]),  # degré
    "%": (0.66, [_circle(0.15, 0.55, 0.10, 0.12), _circle(0.51, 0.14, 0.10, 0.12),
                 _L((0.06, 0.0), (0.60, _CH))]),
}

# --- Accents (marques composables) ------------------------------------------

_MARKS: dict[str, list[Stroke]] = {
    "acute": [_L((-0.06, 0.0), (0.07, 0.10))],
    "grave": [_L((-0.07, 0.10), (0.06, 0.0))],
    "circumflex": [_L((-0.09, 0.0), (0.0, 0.11), (0.09, 0.0))],
    "diaeresis": [_L((-0.08, 0.02), (-0.08, 0.07)), _L((0.08, 0.02), (0.08, 0.07))],
    "cedilla": [_L((0.0, 0.0), (0.03, -0.07), (-0.07, -0.11))],
}

# base -> (glyphe de base, marque)
_COMPOSED: dict[str, tuple[str, str]] = {
    "é": ("e", "acute"), "è": ("e", "grave"),
    "ê": ("e", "circumflex"), "ë": ("e", "diaeresis"),
    "à": ("a", "grave"), "â": ("a", "circumflex"), "ä": ("a", "diaeresis"),
    "ù": ("u", "grave"), "û": ("u", "circumflex"), "ü": ("u", "diaeresis"),
    "î": ("i.dotless", "circumflex"), "ï": ("i.dotless", "diaeresis"),
    "ô": ("o", "circumflex"), "ö": ("o", "diaeresis"),
    "ç": ("c", "cedilla"), "ÿ": ("y", "diaeresis"),
    "É": ("E", "acute"), "È": ("E", "grave"),
    "Ê": ("E", "circumflex"), "Ë": ("E", "diaeresis"),
    "À": ("A", "grave"), "Â": ("A", "circumflex"), "Ä": ("A", "diaeresis"),
    "Ù": ("U", "grave"), "Û": ("U", "circumflex"), "Ü": ("U", "diaeresis"),
    "Î": ("I", "circumflex"), "Ï": ("I", "diaeresis"),
    "Ô": ("O", "circumflex"), "Ö": ("O", "diaeresis"),
    "Ç": ("C", "cedilla"),
}

# Ligatures approximées par juxtaposition (approximation assumée, non calligraphique).
_LIGATURES: dict[str, tuple[str, str, float]] = {
    "œ": ("o", "e", 0.86),   # oe
    "Œ": ("O", "E", 0.90),   # OE
    "æ": ("a", "e", 0.86),   # ae
    "Æ": ("A", "E", 0.86),   # AE
}


def _shift(strokes: list[Stroke], dx: float, dy: float) -> list[Stroke]:
    return [[(x + dx, y + dy) for (x, y) in s] for s in strokes]


def _build() -> dict[str, Glyph]:
    table: dict[str, Glyph] = {}
    raw: dict[str, tuple[float, list[Stroke]]] = {}
    raw.update(_LOWER)
    raw.update(_UPPER)
    raw.update(_DIGITS)
    raw.update(_PUNCT)
    for ch, (adv, strokes) in raw.items():
        table[ch] = Glyph(ch, adv, tuple(tuple(s) for s in strokes))

    for ch, (base_name, mark) in _COMPOSED.items():
        base = table[base_name]
        mark_y = MARK_Y_UPPER if base_name[0].isupper() else MARK_Y_LOWER
        if mark == "cedilla":
            mark_y = 0.0
        marks = _shift(_MARKS[mark], base.advance / 2.0, mark_y)
        table[ch] = Glyph(ch, base.advance, base.strokes + tuple(tuple(s) for s in marks))

    for ch, (left_name, right_name, overlap) in _LIGATURES.items():
        left, right = table[left_name], table[right_name]
        dx = left.advance * overlap
        strokes = list(left.strokes) + [tuple((x + dx, y) for (x, y) in s) for s in right.strokes]
        table[ch] = Glyph(ch, dx + right.advance, tuple(strokes))

    # Les noms techniques ne sont pas des caractères adressables.
    table.pop("i.dotless", None)
    return table


#: Composition publique : caractère accentué -> (glyphe de base, marque).
COMPOSED_BASES: dict[str, tuple[str, str]] = dict(_COMPOSED)
#: Ligatures approximées : caractère -> (gauche, droite, recouvrement).
LIGATURES: dict[str, tuple[str, str, float]] = dict(_LIGATURES)


GLYPHS: dict[str, Glyph] = _build()

#: Espaces reconnues. Insécables : la ligne ne peut pas être coupée dessus.
SPACE_ADVANCES: dict[str, float] = {
    " ": 0.30,
    " ": 0.30,   # espace insécable
    " ": 0.18,   # espace fine insécable
}
NON_BREAKING_SPACES = frozenset({" ", " "})


def advance_of(char: str) -> float:
    """Chasse d'un caractère. Un caractère non pris en charge garde une chasse
    réservée (`TOFU_ADVANCE`) : il n'est ni supprimé, ni remplacé."""
    if char in SPACE_ADVANCES:
        return SPACE_ADVANCES[char]
    glyph = GLYPHS.get(char)
    return glyph.advance if glyph is not None else TOFU_ADVANCE


def supported_chars() -> frozenset[str]:
    return frozenset(GLYPHS) | frozenset(SPACE_ADVANCES) | frozenset({"\n"})


def hand_ref() -> str:
    return f"{HAND_ID}@{HAND_VERSION}"


# --- Métriques d'encre réelles (mesurées sur la table ci-dessus) --------------
# Elles servent aux réserves de mise en page : une lettre peut déborder de sa
# chasse (le 'j' déborde à gauche) et descendre sous la ligne de base. La mise
# en page raisonne sur ces bornes, jamais sur la seule avance.

def _ink_bounds() -> tuple[float, float, float, float]:
    xs_min, xs_over, ys_min, ys_max = 0.0, 0.0, 0.0, 0.0
    for glyph in GLYPHS.values():
        for stroke in glyph.strokes:
            for x, y in stroke:
                xs_min = min(xs_min, x)
                xs_over = max(xs_over, x - glyph.advance)
                ys_min = min(ys_min, y)
                ys_max = max(ys_max, y)
    return xs_min, xs_over, ys_min, ys_max


#: Débord d'encre à gauche de l'origine du glyphe (em, <= 0).
INK_MIN_X: float
#: Débord d'encre à droite de la chasse (em, >= 0).
INK_OVERHANG_X: float
#: Encre la plus basse sous la ligne de base (em, <= 0) et la plus haute (em).
INK_MIN_Y: float
INK_MAX_Y: float
INK_MIN_X, INK_OVERHANG_X, INK_MIN_Y, INK_MAX_Y = _ink_bounds()


def ink_reserve_left_em() -> float:
    return max(0.0, -INK_MIN_X)


def ink_reserve_right_em() -> float:
    return max(0.0, INK_OVERHANG_X)


def ink_above_baseline_em() -> float:
    return max(0.0, INK_MAX_Y)


def ink_below_baseline_em() -> float:
    return max(0.0, -INK_MIN_Y)
