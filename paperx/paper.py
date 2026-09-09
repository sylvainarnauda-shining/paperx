"""Profils papier EXPLICITES et versionnés.

Aucune valeur n'est mesurée sur un papier réel : le profil livré est un profil
de DÉMONSTRATION dont toutes les cotes sont déclarées ici, en clair, et marquées
`measured=False`. Il ne doit pas être présenté comme une caractérisation d'un
papier du commerce.

Toutes les cotes sont vérifiées à la construction : nombres finis, domaines
valides et géométrie cohérente (une première ligne de base au-dessus de la marge
haute, ou une zone utile négative, est refusée, pas rattrapée).
"""

from __future__ import annotations

from dataclasses import dataclass

from . import numeric as num
from .errors import ProfileError


@dataclass(frozen=True)
class PaperProfile:
    """Géométrie de page + grille de lignes, entièrement déclarée."""

    id: str
    version: str
    label: str
    measured: bool
    provenance: str
    width_mm: float
    height_mm: float
    margin_top_mm: float
    margin_bottom_mm: float
    margin_left_mm: float
    margin_right_mm: float
    line_height_mm: float
    font_size_mm: float          # 1 em, en mm
    first_baseline_mm: float     # distance bord haut -> 1re ligne de base
    pen_width_mm: float

    def __post_init__(self) -> None:
        problems = self.numeric_problems()
        if problems:
            raise ProfileError(
                f"profil papier {self.id}@{self.version} incohérent : "
                + " ; ".join(problems)
            )

    def numeric_problems(self) -> tuple[str, ...]:
        """Défauts de ce profil, sans lever d'exception (utilisé par le validateur)."""
        p: list[str] = []
        if not isinstance(self.id, str) or not self.id.strip():
            p.append("id : identifiant vide")
        if not isinstance(self.version, str) or not self.version.strip():
            p.append("version : version vide")
        if not isinstance(self.measured, bool):
            p.append("measured : booléen attendu")

        for name in ("width_mm", "height_mm", "line_height_mm", "font_size_mm",
                     "pen_width_mm", "first_baseline_mm"):
            num.require_positive(p, name, getattr(self, name))
        for name in ("margin_top_mm", "margin_bottom_mm",
                     "margin_left_mm", "margin_right_mm"):
            num.require_non_negative(p, name, getattr(self, name))
        for name in ("width_mm", "height_mm", "first_baseline_mm"):
            num.require_in_mm_domain(p, name, getattr(self, name))
        if p:
            return tuple(p)

        if self.usable_width_mm <= 0:
            p.append("marges gauche/droite plus larges que la page")
        if self.usable_height_mm <= 0:
            p.append("marges haut/bas plus hautes que la page")
        if self.first_baseline_mm < self.margin_top_mm:
            p.append(
                f"first_baseline_mm ({self.first_baseline_mm}) au-dessus de la marge "
                f"haute ({self.margin_top_mm}) : la première ligne sortirait de la zone"
            )
        if self.first_baseline_mm > self.height_mm - self.margin_bottom_mm:
            p.append("first_baseline_mm sous la marge basse : aucune ligne ne tiendrait")
        if self.line_height_mm > self.usable_height_mm:
            p.append("interligne plus grand que la zone utile")
        return tuple(p)

    def ref(self) -> str:
        return f"{self.id}@{self.version}"

    @property
    def usable_width_mm(self) -> float:
        return self.width_mm - self.margin_left_mm - self.margin_right_mm

    @property
    def usable_height_mm(self) -> float:
        return self.height_mm - self.margin_top_mm - self.margin_bottom_mm

    def last_baseline_mm(self, ink_below_baseline_mm: float = 0.0) -> float:
        """Ordonnée maximale admise pour une ligne de base.

        `ink_below_baseline_mm` réserve la place des descendantes et de la
        demi-largeur de trait : l'encre, pas seulement la ligne de base, doit
        rester au-dessus de la marge basse.
        """
        return self.height_mm - self.margin_bottom_mm - max(0.0, ink_below_baseline_mm)

    def lines_per_page(self, ink_below_baseline_mm: float = 0.0) -> int:
        """Nombre de lignes tenant dans la zone utile, réserve comprise.

        Aucun tassement : si une ligne de plus ne tient pas, elle passe à la page
        suivante.
        """
        span = self.last_baseline_mm(ink_below_baseline_mm) - self.first_baseline_mm
        if span < 0:
            return 0
        return int(span // self.line_height_mm) + 1

    def baseline_y_mm(self, line_index: int) -> float:
        """Ordonnée (mm, origine coin haut-gauche, y vers le bas) d'une ligne."""
        return self.first_baseline_mm + line_index * self.line_height_mm

    def as_dict(self) -> dict:
        return {
            "profil": self.ref(),
            "libelle": self.label,
            "mesure_sur_papier_reel": self.measured,
            "provenance": self.provenance,
            "format_mm": [self.width_mm, self.height_mm],
            "marges_mm": {
                "haut": self.margin_top_mm, "bas": self.margin_bottom_mm,
                "gauche": self.margin_left_mm, "droite": self.margin_right_mm,
            },
            "interligne_mm": self.line_height_mm,
            "corps_mm": self.font_size_mm,
            "premiere_ligne_de_base_mm": self.first_baseline_mm,
            "largeur_trait_mm": self.pen_width_mm,
            "zone_utile_mm": [round(self.usable_width_mm, 3), round(self.usable_height_mm, 3)],
        }


#: Profil de démonstration. A4 normalisé (210 x 297 mm) ; toutes les autres
#: cotes sont des choix de démonstration, assumés et déclarés ici.
DEMO_A4 = PaperProfile(
    id="demo-a4",
    version="1.0.0",
    label="A4 — PROFIL DE DÉMONSTRATION (cotes déclarées, non mesurées)",
    measured=False,
    provenance=(
        "210x297 mm = ISO 216 (A4). Marges, interligne, corps et largeur de trait "
        "sont des valeurs de démonstration choisies dans ce fichier ; elles ne "
        "décrivent aucun papier ni aucun stylo réellement caractérisé."
    ),
    width_mm=210.0,
    height_mm=297.0,
    margin_top_mm=20.0,
    margin_bottom_mm=20.0,
    margin_left_mm=20.0,
    margin_right_mm=18.0,
    line_height_mm=8.0,
    font_size_mm=5.0,
    first_baseline_mm=26.0,
    pen_width_mm=0.4,
)

PROFILES: dict[str, PaperProfile] = {DEMO_A4.id: DEMO_A4}


def get(profile_id: str) -> PaperProfile:
    try:
        return PROFILES[profile_id]
    except KeyError:
        raise ProfileError(
            f"profil papier inconnu : {profile_id!r} "
            f"(disponibles : {sorted(PROFILES)})"
        ) from None
