"""Rapport de démonstration, déterministe et strictement JSON-able.

Aucune date, aucun identifiant aléatoire, aucun NaN ni Infinity : le même texte
d'entrée produit exactement le même rapport, octet pour octet.
"""

from __future__ import annotations

import json

from . import gate, pricing
from .charset import missing_from_french_baseline
from .layout import LayoutResult
from .machine import MachineProfile
from .provider import DEFAULT_PROVIDER, check_conformance
from .strokes import PageTrajectory, SpeedProfile
from .synthetic_hand import (HAND_LABEL, HAND_PROVENANCE, IS_PERSONALIZED, hand_ref)
from .validator import ValidationLimits, ValidationReport

REPORT_VERSION = "1.1.0"

#: Ce qui a réellement été exécuté par ce dépôt, et ce qui ne l'a pas été.
CLAIMS = {
    "execute": [
        "décodage UTF-8 strict du texte source et empreinte SHA-256 des octets",
        "pagination A4 sur un profil papier explicite, avec preuve de "
        "reconstruction exacte du texte",
        "signalement des caractères non pris en charge, sans suppression ni "
        "remplacement",
        "construction de trajectoires monotraits et validation déterministe "
        "(nombres finis, bornes, vitesses, levées, profils versionnés)",
        "calcul des zones inaccessibles d'une A4 par une aire de travail "
        "256 x 256 mm, sous hypothèse de pose explicitement non mesurée",
        "rendu d'un aperçu SVG lisible séparant écriture et annotations",
        "refus de toute sortie machine (verrou global + profil non calibré)",
    ],
    "non_demontre": [
        "toute ressemblance de l'écriture générique synthétique avec une "
        "écriture humaine",
        "toute personnalisation à partir d'une photo ou d'un échantillon",
        "toute écriture réellement tracée sur du papier",
        "toute calibration machine : offsets XY, hauteurs de contact et de "
        "levée, obstacles, état machine",
        "tout comportement d'encre, de papier ou de stylo réel",
        "toute exécution d'un modèle appris (aucun poids n'est présent ni "
        "téléchargé)",
    ],
}


def build(layout: LayoutResult,
          trajectories: tuple[PageTrajectory, ...],
          validations: tuple[ValidationReport, ...],
          machine: MachineProfile,
          speeds: SpeedProfile,
          limits: ValidationLimits) -> dict:
    caps = DEFAULT_PROVIDER.capabilities()
    return {
        "version_rapport": REPORT_VERSION,
        "source": {
            "origine": layout.source.origin,
            "sha256": layout.source.sha256,
            "octets": layout.source.byte_length,
            "caracteres": layout.source.char_length,
            "preservation_exacte": layout.preservation_ok(),
        },
        "profils": {
            "papier": layout.paper.as_dict(),
            "machine": machine.as_dict(),
            "vitesses": speeds.as_dict(),
            "limites_validation": limits.as_dict(),
        },
        "ecriture": {
            "reference": hand_ref(),
            "libelle": HAND_LABEL,
            "personnalisee": IS_PERSONALIZED,
            "provenance": HAND_PROVENANCE,
            "socle_francais_manquant": list(missing_from_french_baseline()),
        },
        "mise_en_page": layout.as_dict(),
        "pages": [
            {
                "page": traj.page_number,
                "traits": len(traj.strokes),
                "levees_plume": traj.pen_lifts,
                "validation": val.as_dict(),
            }
            for traj, val in zip(trajectories, validations)
        ],
        "sortie_machine": {
            "disponible": gate.MACHINE_OUTPUT_AVAILABLE,
            "code_verrou": gate.GATE_CODE,
            "raison": gate.GATE_REASON,
            "gcode_executable_produit": False,
            "acces_imprimante": False,
        },
        "fournisseur_personnalisation": {
            **caps.as_dict(),
            "conformite_contrat": list(check_conformance(DEFAULT_PROVIDER)) or "conforme",
        },
        "tarif": pricing.quote(len(layout.pages)).as_dict(),
        "revendications": CLAIMS,
    }


def to_json(report: dict) -> str:
    """Sérialisation stricte : `allow_nan=False` interdit NaN et Infinity."""
    return json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2,
                      allow_nan=False) + "\n"
