"""Chargement du texte source avec préservation exacte.

Règles :
- lecture binaire puis décodage UTF-8 strict (pas de `errors="replace"`) ;
- aucune normalisation Unicode, aucun `strip()`, aucune conversion de fin de ligne ;
- l'empreinte SHA-256 porte sur les octets d'origine.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .errors import DecodingError


@dataclass(frozen=True)
class SourceText:
    """Texte source immuable + preuve d'intégrité."""

    text: str
    sha256: str
    byte_length: int
    char_length: int
    origin: str

    def as_bytes(self) -> bytes:
        """Ré-encode le texte ; doit redonner les octets d'origine (UTF-8)."""
        return self.text.encode("utf-8")


def from_bytes(raw: bytes, origin: str = "<bytes>") -> SourceText:
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:  # pragma: no cover - dépend du fichier
        raise DecodingError(
            f"{origin}: octets non UTF-8 à l'offset {exc.start}. "
            "Aucun remplacement n'est effectué : corrigez la source."
        ) from exc
    return SourceText(
        text=text,
        sha256=hashlib.sha256(raw).hexdigest(),
        byte_length=len(raw),
        char_length=len(text),
        origin=origin,
    )


def load(path: str | Path) -> SourceText:
    p = Path(path)
    return from_bytes(p.read_bytes(), origin=str(p))
