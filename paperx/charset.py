"""Couverture de caractères et SIGNALEMENT des caractères non pris en charge.

Règle non négociable : un caractère non pris en charge est **signalé**, jamais
supprimé, jamais remplacé, jamais « translittéré » (é -> e est interdit).
Il occupe une chasse réservée et reste présent dans le texte reconstruit.
"""

from __future__ import annotations

import unicodedata
from collections import Counter
from dataclasses import dataclass, field

from . import synthetic_hand

CHARSET_ID = "paperx-charset"
CHARSET_VERSION = "1.0.0"

#: Sous-ensemble français explicitement attendu par le banc d'essai.
FRENCH_REQUIRED = (
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "àâäçéèêëîïôöùûüÿœæ"
    "ÀÂÄÇÉÈÊËÎÏÔÖÙÛÜŒÆ"
    "0123456789"
    ".,;:!?'’\"«»()-–—…/°%"
    "   \n"
)


@dataclass(frozen=True)
class UnsupportedChar:
    """Un caractère non couvert, localisé dans le texte source."""

    char: str
    codepoint: str
    name: str
    count: int
    first_index: int
    indices: tuple[int, ...]

    def as_dict(self) -> dict:
        return {
            "caractere": self.char,
            "codepoint": self.codepoint,
            "nom_unicode": self.name,
            "occurrences": self.count,
            "premier_index": self.first_index,
            "index": list(self.indices),
        }


@dataclass(frozen=True)
class CoverageReport:
    charset_ref: str
    hand_ref: str
    total_chars: int
    supported_chars: int
    unsupported: tuple[UnsupportedChar, ...] = field(default=())

    @property
    def ok(self) -> bool:
        return not self.unsupported

    @property
    def unsupported_count(self) -> int:
        return sum(u.count for u in self.unsupported)

    def as_dict(self) -> dict:
        return {
            "charset": self.charset_ref,
            "ecriture": self.hand_ref,
            "caracteres_total": self.total_chars,
            "caracteres_pris_en_charge": self.supported_chars,
            "caracteres_non_pris_en_charge": self.unsupported_count,
            "detail_non_pris_en_charge": [u.as_dict() for u in self.unsupported],
        }


def charset_ref() -> str:
    return f"{CHARSET_ID}@{CHARSET_VERSION}"


def is_supported(char: str, hand=synthetic_hand) -> bool:
    return char in hand.supported_chars()


def _unicode_name(char: str) -> str:
    try:
        return unicodedata.name(char)
    except ValueError:
        return "SANS NOM UNICODE"


def scan(text: str, hand=synthetic_hand) -> CoverageReport:
    """Inventorie les caractères non pris en charge, sans modifier le texte.

    `hand` est l'écriture consultée (module `synthetic_hand` par défaut, ou un
    `paperx.hands.HandStyle`) : la couverture dépend du gabarit réellement utilisé.
    """
    supported = hand.supported_chars()
    positions: dict[str, list[int]] = {}
    counts: Counter[str] = Counter()
    for index, char in enumerate(text):
        if char in supported:
            continue
        counts[char] += 1
        positions.setdefault(char, []).append(index)

    unsupported = tuple(
        UnsupportedChar(
            char=char,
            codepoint=f"U+{ord(char):04X}",
            name=_unicode_name(char),
            count=counts[char],
            first_index=idx_list[0],
            indices=tuple(idx_list),
        )
        # tri déterministe : par point de code
        for char, idx_list in sorted(positions.items(), key=lambda kv: ord(kv[0]))
    )
    total_unsupported = sum(u.count for u in unsupported)
    return CoverageReport(
        charset_ref=charset_ref(),
        hand_ref=hand.hand_ref(),
        total_chars=len(text),
        supported_chars=len(text) - total_unsupported,
        unsupported=unsupported,
    )


def missing_from_french_baseline(hand=synthetic_hand) -> tuple[str, ...]:
    """Caractères du socle français attendu qui ne seraient pas couverts."""
    supported = hand.supported_chars()
    return tuple(sorted({c for c in FRENCH_REQUIRED if c not in supported}, key=ord))
