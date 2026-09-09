"""Profils papier EXPLICITES et versionnés.

Aucune valeur n'est mesurée sur un papier réel : le profil livré est un profil
de DÉMONSTRATION dont toutes les cotes sont déclarées ici, en clair, et marquées
`measured=False`. Il ne doit pas être présenté comme une caractérisation d'un
papier du commerce.
"""

from __future__ import annotations

from dataclasses import dataclass

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
        if not self.id or not self.version:
            raise ProfileError("profil papier sans identifiant ou sans version")
        for name in ("width_mm", "height_mm", "line_height_mm", "font_size_mm"):
            if getattr(self, name) <= 0:
                raise ProfileError(f"profil papier {self.ref()}: {name} doit être > 0")
        if self.usable_width_mm <= 0 or self.usable_height_mm <= 0:
            raise ProfileError(f"profil papier {self.ref()}: marges plus larges que la page")

    def ref(self) -> str:
        return f"{self.id}@{self.version}"

    @property
    def usable_width_mm(self) -> float:
        return self.width_mm - self.margin_left_mm - self.margin_right_mm

    @property
    def usable_height_mm(self) -> float:
        return self.height_mm - self.margin_top_mm - self.margin_bottom_mm

    @property
    def lines_per_page(self) -> int:
        """Nombre de lignes de base tenant dans la zone utile (aucun tassement)."""
        last_allowed = self.height_mm - self.margin_bottom_mm
        span = last_allowed - self.first_baseline_mm
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
            "lignes_par_page": self.lines_per_page,
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
