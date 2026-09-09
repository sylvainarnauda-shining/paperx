"""Recto / recto-verso : faces écrites, feuilles consommées, supplément opérateur.

Trois règles, toutes vérifiables :

1. Le prix cible porte sur la **face A4 écrite** (`pricing.PRICE_PER_A4_CENTS`).
   Le recto-verso économise du **papier**, pas de l'**écriture** : il n'ouvre
   droit à aucun demi-tarif implicite. La base reste `faces × prix unitaire`.
2. Les **feuilles** consommées valent `ceil(faces / 2)` en recto-verso et
   `faces` en recto. C'est une conséquence arithmétique, pas une remise.
3. Le retournement est **manuel** : une personne retourne la feuille, la recale,
   puis **contrôle l'alignement** avant toute reprise. Rien ne reprend tout seul.
   Le supplément compte donc ces trois temps humains, plus les ratés. Il n'est
   pas deviné : sans coûts d'atelier renseignés, il vaut « à établir » (`None`),
   jamais `0`. Renseigné, il porte sa provenance (mesurée ou hypothèse) et le
   total reste **non confirmé** dans tous les cas.

Aucun paiement, aucun encaissement, aucun appel réseau ici.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from . import numeric as num
from . import pricing
from .errors import PaperxError, ProfileError

DUPLEX_VERSION = "1.0.0"


class Sides(str, Enum):
    """Faces écrites par feuille."""

    RECTO = "recto"
    RECTO_VERSO = "recto_verso"


def parse_sides(value: object) -> Sides:
    try:
        return Sides(value)
    except ValueError:
        raise PaperxError(
            f"mode d'impression inconnu : {value!r} "
            f"(attendu : {[s.value for s in Sides]})"
        ) from None


def sheets_for(faces: int, sides: Sides) -> int:
    """Feuilles consommées. Recto-verso : `ceil(faces / 2)`, sans exception."""
    if not isinstance(faces, int) or isinstance(faces, bool) or faces < 0:
        raise PaperxError(f"nombre de faces invalide : {faces!r}")
    if sides is Sides.RECTO:
        return faces
    return math.ceil(faces / 2)


def flips_for(faces: int, sides: Sides) -> int:
    """Retournements nécessaires : une feuille écrite des deux côtés = 1 retournement."""
    if sides is Sides.RECTO:
        return 0
    return sheets_for(faces, sides) if faces % 2 == 0 else sheets_for(faces, sides) - 1


# --- Coûts opérateur ---------------------------------------------------------

STATUS_SANS_OBJET = "sans_objet"
STATUS_A_ETABLIR = "a_etablir"
STATUS_SOUS_HYPOTHESE = "sous_hypothese"
STATUS_MESURE = "mesure"

PROVENANCE_MESUREE = "mesuree"
PROVENANCE_HYPOTHESE = "hypothese"


@dataclass(frozen=True)
class OperatorCosts:
    """Coûts d'atelier, configurables et versionnés.

    `None` signifie **inconnu**, jamais zéro. `measured` dit si ces valeurs
    viennent d'un chronométrage réel ou d'une hypothèse déclarée ; l'interface
    doit reprendre cette distinction telle quelle.
    """

    id: str
    version: str
    flip_seconds: float | None          # retourner la feuille (geste humain)
    realign_seconds: float | None        # la recaler sur le support
    check_seconds: float | None          # contrôler l'alignement avant reprise
    hourly_rate_cents: int | None
    spoilage_rate: float | None
    measured: bool
    provenance: str

    def __post_init__(self) -> None:
        problems = self.numeric_problems()
        if problems:
            raise ProfileError(
                f"coûts opérateur {self.id}@{self.version} incohérents : "
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
        if self.flip_seconds is not None:
            num.require_non_negative(p, "flip_seconds", self.flip_seconds)
        if self.realign_seconds is not None:
            num.require_non_negative(p, "realign_seconds", self.realign_seconds)
        if self.check_seconds is not None:
            num.require_non_negative(p, "check_seconds", self.check_seconds)
        if self.hourly_rate_cents is not None:
            num.require_int(p, "hourly_rate_cents", self.hourly_rate_cents, minimum=0)
        if self.spoilage_rate is not None:
            if num.require_non_negative(p, "spoilage_rate", self.spoilage_rate) \
                    and float(self.spoilage_rate) > 1.0:
                p.append("spoilage_rate : proportion attendue entre 0 et 1")
        if self.measured and not self.known:
            p.append("measured=True alors que des coûts restent inconnus")
        return tuple(p)

    @property
    def known(self) -> bool:
        return None not in (self.flip_seconds, self.realign_seconds,
                            self.check_seconds, self.hourly_rate_cents,
                            self.spoilage_rate)

    @property
    def provenance_code(self) -> str:
        return PROVENANCE_MESUREE if self.measured else PROVENANCE_HYPOTHESE

    def ref(self) -> str:
        return f"{self.id}@{self.version}"

    def as_dict(self) -> dict:
        return {
            "profil": self.ref(),
            "secondes_retournement": self.flip_seconds,
            "secondes_recalage": self.realign_seconds,
            "secondes_controle_alignement": self.check_seconds,
            "taux_horaire_centimes": self.hourly_rate_cents,
            "taux_rates": self.spoilage_rate,
            "complet": self.known,
            "provenance_code": self.provenance_code,
            "mesure": self.measured,
            "provenance": self.provenance,
        }


#: Défaut du projet : rien n'est mesuré, rien n'est supposé.
UNKNOWN_COSTS = OperatorCosts(
    id="couts-operateur-inconnus",
    version="1.0.0",
    flip_seconds=None,
    realign_seconds=None,
    check_seconds=None,
    hourly_rate_cents=None,
    spoilage_rate=None,
    measured=False,
    provenance=(
        "Aucun chronométrage d'atelier, aucun taux horaire arrêté, aucun taux de "
        "ratés observé. Le supplément recto-verso reste À ÉTABLIR : il n'est pas "
        "supposé nul."
    ),
)


def hypothesis_costs(flip_seconds: float, realign_seconds: float,
                     check_seconds: float, hourly_rate_cents: int,
                     spoilage_rate: float,
                     label: str = "hypothese-atelier") -> OperatorCosts:
    """Coûts d'atelier **supposés**, pour simuler — jamais présentés comme mesurés."""
    return OperatorCosts(
        id=label,
        version="1.0.0",
        flip_seconds=flip_seconds,
        realign_seconds=realign_seconds,
        check_seconds=check_seconds,
        hourly_rate_cents=hourly_rate_cents,
        spoilage_rate=spoilage_rate,
        measured=False,
        provenance=(
            "HYPOTHÈSE saisie dans l'interface : aucune de ces valeurs n'a été "
            "chronométrée ni observée en atelier. Le montant obtenu est une "
            "simulation, pas un tarif."
        ),
    )


# --- Supplément et estimation ------------------------------------------------


@dataclass(frozen=True)
class Supplement:
    status: str
    cents: int | None
    flips: int
    costs_ref: str
    provenance_code: str
    detail: dict

    @property
    def known(self) -> bool:
        return self.cents is not None

    @property
    def hypothetical(self) -> bool:
        return self.status == STATUS_SOUS_HYPOTHESE

    def label(self) -> str:
        return {
            STATUS_SANS_OBJET: "sans objet (recto seul)",
            STATUS_A_ETABLIR: "à établir",
            STATUS_SOUS_HYPOTHESE: "simulation sous hypothèses opérateur",
            STATUS_MESURE: "établi sur coûts mesurés",
        }[self.status]

    def as_dict(self) -> dict:
        return {
            "statut": self.status,
            "libelle": self.label(),
            "centimes": self.cents,
            "retournements": self.flips,
            "couts_operateur": self.costs_ref,
            "provenance_code": self.provenance_code,
            "hypothetique": self.hypothetical,
            "detail": self.detail,
        }


def supplement(faces: int, sides: Sides,
               costs: OperatorCosts = UNKNOWN_COSTS) -> Supplement:
    """Supplément recto-verso. Inconnu par défaut, jamais ramené à zéro."""
    flips = flips_for(faces, sides)

    if sides is Sides.RECTO:
        return Supplement(
            status=STATUS_SANS_OBJET, cents=0, flips=0, costs_ref=costs.ref(),
            provenance_code=costs.provenance_code,
            detail={"note": "aucun retournement en recto seul"},
        )

    if not costs.known:
        return Supplement(
            status=STATUS_A_ETABLIR, cents=None, flips=flips, costs_ref=costs.ref(),
            provenance_code=costs.provenance_code,
            detail={
                "manquant": [nom for nom, val in (
                    ("secondes_retournement", costs.flip_seconds),
                    ("secondes_recalage", costs.realign_seconds),
                    ("secondes_controle_alignement", costs.check_seconds),
                    ("taux_horaire_centimes", costs.hourly_rate_cents),
                    ("taux_rates", costs.spoilage_rate),
                ) if val is None],
                "note": "supplément non calculable : il reste à établir, il ne vaut pas 0",
            },
        )

    seconds = flips * (float(costs.flip_seconds) + float(costs.realign_seconds)
                       + float(costs.check_seconds))
    labour_cents = int(round(seconds / 3600.0 * float(costs.hourly_rate_cents)))
    # Une feuille ratée au retournement doit être réécrite des deux côtés.
    waste_cents = int(round(
        float(costs.spoilage_rate) * flips * 2 * pricing.PRICE_PER_A4_CENTS))
    total = labour_cents + waste_cents

    return Supplement(
        status=STATUS_MESURE if costs.measured else STATUS_SOUS_HYPOTHESE,
        cents=total, flips=flips, costs_ref=costs.ref(),
        provenance_code=costs.provenance_code,
        detail={
            "secondes_manipulation": round(seconds, 1),
            "main_doeuvre_centimes": labour_cents,
            "rebut_centimes": waste_cents,
            "secondes_par_retournement": round(
                float(costs.flip_seconds) + float(costs.realign_seconds)
                + float(costs.check_seconds), 1),
            "formule": (
                "main d'œuvre = retournements × (retournement + recalage + contrôle "
                "d'alignement) ÷ 3600 × taux horaire ; rebut = taux de ratés × "
                "retournements × 2 faces × prix unitaire"
            ),
            "note_manuel": (
                "Chaque retournement est un geste humain : la feuille est retournée, "
                "recalée, puis son alignement est contrôlé avant toute reprise. "
                "Aucune reprise automatique n'est prévue."
            ),
        },
    )


@dataclass(frozen=True)
class Estimate:
    faces: int
    sheets: int
    sides: Sides
    unit_price_cents: int
    base_cents: int
    supplement: Supplement
    service_area: str
    version: str

    @property
    def total_cents(self) -> int | None:
        """Total, ou `None` tant que le supplément n'est pas établi."""
        return None if self.supplement.cents is None else self.base_cents + self.supplement.cents

    @property
    def total_confirmed(self) -> bool:
        """Toujours faux : remise à définir, aucun paiement, aucun engagement."""
        return False

    def as_dict(self) -> dict:
        total = self.total_cents
        return {
            "version_devis": self.version,
            "mode": self.sides.value,
            "faces_ecrites": self.faces,
            "feuilles": self.sheets,
            "regle_feuilles": (
                "feuilles = ceil(faces / 2)" if self.sides is Sides.RECTO_VERSO
                else "feuilles = faces"
            ),
            "prix_unitaire_centimes": self.unit_price_cents,
            "base_centimes": self.base_cents,
            "supplement": self.supplement.as_dict(),
            "total_centimes": total,
            "total_euros": round(total / 100, 2) if total is not None else None,
            "total_confirme": self.total_confirmed,
            "statut_total": (
                "NON CONFIRMÉ — supplément recto-verso à établir"
                if total is None else
                "NON CONFIRMÉ — supplément " + self.supplement.label()
            ),
            "zone": self.service_area,
            "remise": "à définir",
            "engageant": False,
            "paiement_active": pricing.PAYMENT_ENABLED,
            "note_recto_verso": (
                "Le recto-verso économise du papier, pas de l'écriture : chaque face "
                "écrite reste facturée au prix unitaire. Aucun demi-tarif n'est "
                "appliqué, et le retournement ajoute un coût au lieu d'en retirer."
            ),
            "retournement_manuel": self.sides is Sides.RECTO_VERSO,
            "note_retournement": (
                "Retournement MANUEL : la reprise exige une confirmation humaine "
                "explicite (feuille retournée, recalée, alignement contrôlé). "
                "Aucune reprise machine automatique n'existe dans ce parcours."
            ),
        }


    def sheets_sentence(self) -> str:
        """Le nombre de feuilles en français courant, sans formule."""
        if self.sides is Sides.RECTO:
            return "une page par feuille"
        if self.faces == 0:
            return "aucune feuille"
        if self.faces % 2 == 1:
            return "deux pages par feuille ; la dernière n'est écrite que d'un côté"
        return "deux pages par feuille"

    def supplement_sentence(self) -> str:
        """Étiquette courte, pour tenir dans une case de devis."""
        return {
            STATUS_SANS_OBJET: "sans objet",
            STATUS_A_ETABLIR: "reste à chiffrer",
            STATUS_SOUS_HYPOTHESE: "estimation",
            STATUS_MESURE: "chiffré",
        }[self.supplement.status]

    def as_client_dict(self) -> dict:
        """Devis remis au client : montants et langage courant, rien d'interne.

        Les durées d'atelier, le taux horaire, la part de feuilles ratées et le
        détail de calcul du supplément n'y figurent pas : ils appartiennent à
        l'espace opérateur.
        """
        total = self.total_cents
        return {
            "mode": self.sides.value,
            "pages_ecrites": self.faces,
            "feuilles": self.sheets,
            "explication_feuilles": self.sheets_sentence(),
            "prix_par_page_centimes": self.unit_price_cents,
            "sous_total_centimes": self.base_cents,
            "supplement_retournement_centimes": self.supplement.cents,
            "supplement_explication": self.supplement_sentence(),
            "total_centimes": total,
            "total_euros": round(total / 100, 2) if total is not None else None,
            "total_confirme": self.total_confirmed,
            "statut_total": (
                "Total à confirmer : le retournement se fait à la main et son "
                "supplément reste à chiffrer."
                if total is None else
                "Total indicatif, non engageant."
            ),
            "zone": self.service_area,
            "remise": "à définir",
            "engageant": False,
            "paiement_active": pricing.PAYMENT_ENABLED,
            "note_recto_verso": (
                "Le recto-verso économise du papier, pas de l'écriture : chaque page "
                "écrite reste au même prix."
            ),
        }


def estimate(faces: int, sides: Sides,
             costs: OperatorCosts = UNKNOWN_COSTS) -> Estimate:
    """Devis indicatif par faces écrites. Jamais engageant, jamais encaissé."""
    if not isinstance(faces, int) or isinstance(faces, bool) or faces < 0:
        raise PaperxError(f"nombre de faces invalide : {faces!r}")
    return Estimate(
        faces=faces,
        sheets=sheets_for(faces, sides),
        sides=sides,
        unit_price_cents=pricing.PRICE_PER_A4_CENTS,
        base_cents=pricing.PRICE_PER_A4_CENTS * faces,
        supplement=supplement(faces, sides, costs),
        service_area=pricing.SERVICE_AREA,
        version=DUPLEX_VERSION,
    )
