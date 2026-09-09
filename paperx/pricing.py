"""Prix cible IMMUABLE et devis indicatif. Aucun paiement réel.

Ce module ne contacte aucun service, n'encaisse rien et ne stocke aucune donnée
client. Il calcule un montant affichable à partir d'un prix cible figé.
"""

from __future__ import annotations

from dataclasses import dataclass

from .errors import PaperxError

#: Prix cible, en centimes d'euro, par page A4. Valeur figée.
PRICE_PER_A4_CENTS: int = 100

#: Zone de service déclarée.
SERVICE_AREA: str = "Montpellier centre"

#: Remise : à définir. `None` signifie « non décidée », pas « zéro ».
DISCOUNT = None

PAYMENT_ENABLED: bool = False
PRICING_VERSION = "1.0.0"


class PaymentDisabled(PaperxError):
    """Toute tentative d'encaissement est refusée dans ce dépôt."""


class DiscountUndefined(PaperxError):
    """Une remise non définie ne peut pas être appliquée (surtout pas comme 0 %)."""


@dataclass(frozen=True)
class Quote:
    pages: int
    unit_price_cents: int
    total_cents: int
    service_area: str
    discount_applied: None
    binding: bool
    version: str

    def as_dict(self) -> dict:
        return {
            "pages": self.pages,
            "prix_unitaire_centimes": self.unit_price_cents,
            "total_centimes": self.total_cents,
            "total_euros": round(self.total_cents / 100, 2),
            "zone": self.service_area,
            "remise": "à définir",
            "engageant": self.binding,
            "paiement_active": PAYMENT_ENABLED,
            "version_tarif": self.version,
        }


def quote(pages: int) -> Quote:
    """Devis indicatif, non engageant, sans remise (la remise reste à définir)."""
    if not isinstance(pages, int) or isinstance(pages, bool) or pages < 0:
        raise PaperxError(f"nombre de pages invalide : {pages!r}")
    return Quote(
        pages=pages,
        unit_price_cents=PRICE_PER_A4_CENTS,
        total_cents=PRICE_PER_A4_CENTS * pages,
        service_area=SERVICE_AREA,
        discount_applied=None,
        binding=False,
        version=PRICING_VERSION,
    )


def apply_discount(*_args, **_kwargs):
    """Refuse d'appliquer une remise tant qu'elle n'est pas définie."""
    raise DiscountUndefined(
        "la remise est à définir : aucune valeur n'est supposée, pas même 0 %."
    )


def charge(*_args, **_kwargs):
    """Refuse tout encaissement : ce dépôt ne fait aucun paiement réel."""
    raise PaymentDisabled(
        "aucun paiement réel n'est possible depuis ce dépôt : "
        "ni encaissement, ni appel à un prestataire de paiement."
    )
