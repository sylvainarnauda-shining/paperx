"""Garde-fous numériques partagés.

Toute valeur qui traverse le banc d'essai doit être un réel FINI dans un
domaine explicite. NaN, ±inf, booléens déguisés en nombres et magnitudes
absurdes sont refusés là où ils apparaissent — jamais propagés jusqu'au rapport.
"""

from __future__ import annotations

import math

#: Magnitude maximale admise pour une longueur exprimée en mm dans ce banc.
#: Très au-delà de toute feuille et de toute machine : sert à couper court aux
#: coordonnées « finies mais absurdes » qui font déborder les calculs.
MAX_ABS_MM = 1.0e6


def is_real(value: object) -> bool:
    """Vrai pour un int/float réel. `True`/`False` ne sont PAS des nombres ici."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def is_finite(value: object) -> bool:
    return is_real(value) and math.isfinite(float(value))


def require_finite(problems: list[str], name: str, value: object) -> bool:
    if not is_real(value):
        problems.append(f"{name} : valeur non numérique ({value!r})")
        return False
    if not math.isfinite(float(value)):
        problems.append(f"{name} : valeur non finie ({value!r})")
        return False
    return True


def require_positive(problems: list[str], name: str, value: object) -> bool:
    if not require_finite(problems, name, value):
        return False
    if float(value) <= 0.0:
        problems.append(f"{name} : doit être strictement positif ({value!r})")
        return False
    return True


def require_non_negative(problems: list[str], name: str, value: object) -> bool:
    if not require_finite(problems, name, value):
        return False
    if float(value) < 0.0:
        problems.append(f"{name} : doit être positif ou nul ({value!r})")
        return False
    return True


def require_in_mm_domain(problems: list[str], name: str, value: object,
                         limit: float = MAX_ABS_MM) -> bool:
    if not require_finite(problems, name, value):
        return False
    if abs(float(value)) > limit:
        problems.append(f"{name} : magnitude hors domaine (|{value!r}| > {limit} mm)")
        return False
    return True


def require_int(problems: list[str], name: str, value: object,
                minimum: int = 0) -> bool:
    if not isinstance(value, int) or isinstance(value, bool):
        problems.append(f"{name} : entier attendu ({value!r})")
        return False
    if value < minimum:
        problems.append(f"{name} : doit être >= {minimum} ({value!r})")
        return False
    return True


def safe_hypot(dx: float, dy: float) -> float:
    """Norme sans OverflowError : renvoie `inf` si le calcul déborde."""
    try:
        return math.hypot(float(dx), float(dy))
    except (OverflowError, ValueError, TypeError):
        return math.inf


def finite_or_none(value: float) -> float | None:
    """Valeur arrondissable pour un rapport JSON strict, ou `None` si non finie."""
    return float(value) if is_finite(value) else None
