"""Contrat d'un FUTUR fournisseur de personnalisation d'écriture.

Ce module définit une interface et ses règles de conformité. Il ne contient
aucun modèle, aucun poids, aucune inférence — et ce banc d'essai n'en exécute
aucun. L'implémentation par défaut, `UnavailableProvider`, refuse explicitement :
c'est l'état réel du projet aujourd'hui.

Distinction imposée par le contrat, parce qu'elle est régulièrement confondue :

- `PHOTO_PAPIER_VIERGE` : photo d'un support vierge. Renseigne la géométrie et
  le fond du papier. **Ne décrit aucune écriture.** Un fournisseur DOIT la
  refuser comme source de personnalisation.
- `ECHANTILLON_MANUSCRIT_CLIENT` : tracés réellement écrits par la personne.
  Seule source admissible d'une personnalisation, et donnée personnelle : elle
  ne doit jamais être versionnée dans ce dépôt public (voir .gitignore).
- `ECRITURE_GENERIQUE_SYNTHETIQUE` : gabarit synthétique interne, réservé aux
  tests mécaniques. Ne produit jamais `is_personalized = True`.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from enum import Enum

from .errors import InvalidSampleKind, PersonalizationUnavailable

CONTRACT_ID = "paperx-personalization-contract"
CONTRACT_VERSION = "1.0.0"


class SampleKind(str, Enum):
    PHOTO_PAPIER_VIERGE = "photo_papier_vierge"
    ECHANTILLON_MANUSCRIT_CLIENT = "echantillon_manuscrit_client"
    ECRITURE_GENERIQUE_SYNTHETIQUE = "ecriture_generique_synthetique"


#: Seule source admissible d'une écriture personnalisée.
PERSONALIZING_KINDS = frozenset({SampleKind.ECHANTILLON_MANUSCRIT_CLIENT})


@dataclass(frozen=True)
class Sample:
    """Référence à un échantillon. Le contenu reste HORS de ce dépôt.

    `storage_ref` est un identifiant opaque (ex. chemin dans un espace privé) ;
    aucune image, aucun octet client n'est stocké ni versionné ici.
    """

    kind: SampleKind
    storage_ref: str
    consent_ref: str | None = None

    def as_dict(self) -> dict:
        return {
            "type": self.kind.value,
            "reference_stockage": self.storage_ref,
            "reference_consentement": self.consent_ref,
        }


@dataclass(frozen=True)
class Capabilities:
    """Ce qu'un fournisseur déclare — vérifiable, versionné, et falsifiable."""

    provider_id: str
    version: str
    is_personalized: bool
    supported_chars: frozenset[str]
    requires_sample_kinds: frozenset[SampleKind]
    licence_ref: str
    licence_verified: bool
    weights_ref: str | None
    executed_locally: bool
    notes: str

    def ref(self) -> str:
        return f"{self.provider_id}@{self.version}"

    def missing_for(self, text: str) -> tuple[str, ...]:
        """Caractères du texte que le fournisseur ne couvre pas (à signaler)."""
        return tuple(sorted({c for c in text if c not in self.supported_chars}, key=ord))

    def as_dict(self) -> dict:
        return {
            "fournisseur": self.ref(),
            "personnalise": self.is_personalized,
            "caracteres_couverts": len(self.supported_chars),
            "types_echantillon_requis": sorted(k.value for k in self.requires_sample_kinds),
            "licence": self.licence_ref,
            "licence_verifiee": self.licence_verified,
            "poids": self.weights_ref,
            "execute_localement": self.executed_locally,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class Hand:
    """Écriture rendue par un fournisseur : glyphes -> traits en unités em."""

    hand_id: str
    version: str
    is_personalized: bool
    provenance: str
    glyphs: dict[str, tuple[tuple[tuple[float, float], ...], ...]]

    def ref(self) -> str:
        return f"{self.hand_id}@{self.version}"


class PersonalizationProvider(abc.ABC):
    """Interface que devra respecter tout futur fournisseur.

    Règles de conformité (vérifiées par `check_conformance`) :

    R1. `capabilities()` est déterministe et versionnée (`id@version`).
    R2. Un fournisseur ne peut annoncer `is_personalized = True` que s'il exige
        un `ECHANTILLON_MANUSCRIT_CLIENT`.
    R3. `build_hand()` refuse `PHOTO_PAPIER_VIERGE` par `InvalidSampleKind`.
    R4. `build_hand()` refuse un type d'échantillon non déclaré dans
        `requires_sample_kinds`.
    R5. Une écriture personnalisée ne peut pas être produite à partir d'un
        gabarit générique synthétique — y compris si le fournisseur déclare
        accepter ce type d'échantillon.
    R6. Les caractères non couverts sont exposés par `capabilities()` et doivent
        être signalés à l'appelant — jamais supprimés ni remplacés.
    R7. Si le fournisseur s'appuie sur des poids ou du code tiers, la licence
        est référencée et `licence_verified` dit si elle a été vérifiée.
    R8. L'indisponibilité se signale par `PersonalizationUnavailable`, jamais en
        rendant discrètement une écriture générique à la place.
    """

    @abc.abstractmethod
    def capabilities(self) -> Capabilities: ...

    @abc.abstractmethod
    def build_hand(self, sample: Sample) -> Hand: ...


class UnavailableProvider(PersonalizationProvider):
    """État réel du projet : aucune personnalisation n'est disponible."""

    PROVIDER_ID = "aucun-fournisseur"
    VERSION = "1.0.0"

    def capabilities(self) -> Capabilities:
        return Capabilities(
            provider_id=self.PROVIDER_ID,
            version=self.VERSION,
            is_personalized=False,
            supported_chars=frozenset(),
            requires_sample_kinds=frozenset({SampleKind.ECHANTILLON_MANUSCRIT_CLIENT}),
            licence_ref="sans objet — aucun modèle, aucun poids, aucun code tiers",
            licence_verified=True,
            weights_ref=None,
            executed_locally=False,
            notes=(
                "Aucun fournisseur de personnalisation n'existe à ce stade. "
                "Toute demande est refusée explicitement."
            ),
        )

    def build_hand(self, sample: Sample) -> Hand:
        if sample.kind is SampleKind.PHOTO_PAPIER_VIERGE:
            raise InvalidSampleKind(
                "une photo de papier vierge décrit le support, pas une écriture : "
                "elle ne peut pas servir de source de personnalisation."
            )
        raise PersonalizationUnavailable(
            "aucun fournisseur de personnalisation n'est disponible. "
            "Le banc d'essai n'imite pas une écriture personnelle à la place."
        )


def check_conformance(provider: PersonalizationProvider) -> tuple[str, ...]:
    """Vérifie les règles R1..R8. Renvoie la liste des manquements (vide = conforme)."""
    failures: list[str] = []
    caps = provider.capabilities()

    if caps.ref() != provider.capabilities().ref():
        failures.append("R1 : capabilities() n'est pas déterministe")
    if not caps.provider_id or not caps.version:
        failures.append("R1 : fournisseur non versionné (id@version attendu)")

    if caps.is_personalized and not (caps.requires_sample_kinds & PERSONALIZING_KINDS):
        failures.append(
            "R2 : personnalisation annoncée sans exiger d'échantillon manuscrit client")

    try:
        provider.build_hand(Sample(SampleKind.PHOTO_PAPIER_VIERGE, "ref:papier-vierge"))
    except InvalidSampleKind:
        pass
    except Exception as exc:  # noqa: BLE001 - on veut le type exact
        failures.append(
            f"R3 : photo de papier vierge refusée par {type(exc).__name__} "
            "au lieu de InvalidSampleKind")
    else:
        failures.append("R3 : photo de papier vierge acceptée comme source d'écriture")

    undeclared = set(SampleKind) - set(caps.requires_sample_kinds) - {
        SampleKind.PHOTO_PAPIER_VIERGE}
    for kind in sorted(undeclared, key=lambda k: k.value):
        try:
            hand = provider.build_hand(Sample(kind, f"ref:{kind.value}"))
        except (InvalidSampleKind, PersonalizationUnavailable):
            pass
        except Exception as exc:  # noqa: BLE001
            failures.append(f"R4 : {kind.value} refusé par {type(exc).__name__} inattendu")
        else:
            failures.append(f"R4 : {kind.value} accepté alors qu'il n'est pas déclaré requis")

    # R5 : contrôlé systématiquement, même quand le gabarit générique est déclaré
    # accepté — c'est précisément le cas où la revendication est trompeuse.
    try:
        hand = provider.build_hand(
            Sample(SampleKind.ECRITURE_GENERIQUE_SYNTHETIQUE, "ref:gabarit-generique"))
    except (InvalidSampleKind, PersonalizationUnavailable):
        pass
    except Exception as exc:  # noqa: BLE001
        failures.append(
            f"R5 : gabarit générique refusé par {type(exc).__name__} inattendu")
    else:
        if hand.is_personalized:
            failures.append(
                "R5 : écriture déclarée « personnalisée » produite à partir d'un "
                "gabarit générique synthétique")

    if caps.is_personalized and not caps.supported_chars:
        failures.append("R6 : aucune couverture de caractères déclarée")
    if caps.weights_ref and not caps.licence_verified:
        failures.append("R7 : poids référencés sans licence vérifiée")

    try:
        provider.build_hand(Sample(SampleKind.ECHANTILLON_MANUSCRIT_CLIENT, "ref:absent"))
    except PersonalizationUnavailable:
        pass
    except Exception:  # noqa: BLE001 - un fournisseur réel peut réussir
        pass

    return tuple(failures)


#: Fournisseur utilisé par le banc d'essai. Il refuse : c'est voulu.
DEFAULT_PROVIDER: PersonalizationProvider = UnavailableProvider()
