"""Dossiers de préparation : une archive ZIP relisible, jamais exécutable.

Deux variantes, volontairement distinctes :

- **client** — ce que la personne qui commande reçoit : son texte exact, les
  pages simulées, son devis en langage courant, un manifeste haché. Aucun coût
  d'atelier, aucune durée d'exécution, aucun code de validateur : ces
  informations sont internes.
- **opérateur** — tout ce qui précède, plus les trajectoires, le rapport de
  validation complet, les métriques de simulation, les durées décomposées et les
  coûts d'atelier avec leur provenance.

État déclaré dans les deux cas : `NON_EXECUTABLE`. Aucun G-code, aucun fichier de
tâche, aucune coordonnée machine, aucun Z. Les archives sont déterministes :
mêmes entrées → mêmes octets (horodatage figé, ordre stable).
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import dataclass

from . import PAPERX_VERSION, gate, pricing
from .duplex import Estimate
from .layout import LayoutResult
from .machine import MachineProfile
from .simulation import JobMetrics, TRIALS_NOTE, UNMEASURED_TRIALS
from .strokes import PageTrajectory, SpeedProfile
from .trajexport import page_as_dict
from .validator import ValidationLimits, ValidationReport
from . import emit, report as report_mod, svg as svg_mod

PACKAGE_FORMAT = "paperx-dossier-preparation"
PACKAGE_VERSION = "2.0.0"
STATE_NON_EXECUTABLE = "NON_EXECUTABLE"

VARIANTE_CLIENT = "client"
VARIANTE_OPERATEUR = "operateur"

#: Horodatage figé : l'archive ne doit pas changer d'octets d'une seconde à l'autre.
_FIXED_TIME = (1980, 1, 1, 0, 0, 0)

LISEZ_MOI_CLIENT = """VOTRE DOSSIER paperx
====================

Ce dossier sert à relire votre commande avant toute écriture réelle.

Ce qu'il contient
-----------------
  texte-source.txt     votre texte, exactement tel que vous l'avez donné
  pages/page-NN.svg    la simulation du tracé, page par page
  devis.json           pages écrites, feuilles, prix
  MANIFESTE.json       l'empreinte de chaque fichier, pour vérifier qu'il est intact

Important
---------
  * Les pages de ce dossier sont une SIMULATION du tracé, pas une photo du
    résultat final. Rien n'a encore été écrit sur du papier.
  * L'écriture employée est une écriture de démonstration. Elle ne reproduit
    l'écriture de personne.
  * Ce dossier ne contient aucun fichier destiné à une machine, et rien ici ne
    déclenche d'impression.
"""

LISEZ_MOI_OPERATEUR = """DOSSIER DE PRÉPARATION paperx — NON EXÉCUTABLE (vue opérateur)
==============================================================

Contenu
-------
  texte-source.txt          les octets exacts du texte, sans normalisation
  pages/page-NN.svg         un aperçu par page (écriture + annotations séparées)
  trajectoires/page-NN.json les traits posés et les levées de plume, en mm
  validation/rapport.json   profils versionnés et constats du validateur
  validation/revue-*.txt    fiches de revue humaine, une par page
  devis-client.json         le devis tel qu'il est remis au client
  devis-operateur.json      le même devis avec le détail du supplément
  simulation.json           surfaces, longueurs, temps décomposés, manipulations
  MANIFESTE.json            empreinte SHA-256 de chaque fichier + empreinte globale

Ce qu'il NE contient PAS, et pourquoi
-------------------------------------
  * Aucun G-code, aucun fichier de tâche, aucune commande machine.
    La chaîne n'est pas calibrée : offsets XY réels, hauteur de contact et de
    levée de la plume, obstacles physiques et état machine sont INCONNUS. Rien
    n'est deviné pour combler ce vide.
  * Aucune écriture personnalisée. L'écriture employée est GÉNÉRIQUE et
    SYNTHÉTIQUE ; elle ne ressemble à l'écriture de personne.

Reste à établir par des essais physiques, à plusieurs vitesses
--------------------------------------------------------------
"""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(obj: dict) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2,
                       allow_nan=False) + "\n").encode("utf-8")


def _zip(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(entries):
            info = zipfile.ZipInfo(filename=name, date_time=_FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, entries[name])
    return buffer.getvalue()


def _file_list(entries: dict[str, bytes]) -> tuple[list[dict], str]:
    files = [{"chemin": name, "octets": len(data), "sha256": _sha(data)}
             for name, data in sorted(entries.items())]
    fingerprint = _sha("\n".join(f"{f['chemin']}:{f['sha256']}" for f in files).encode())
    return files, fingerprint


@dataclass(frozen=True)
class PreparationPackage:
    variant: str
    filename: str
    content: bytes
    manifest: dict

    @property
    def sha256(self) -> str:
        return _sha(self.content)


def _common_manifest(order_ref: str, layout: LayoutResult, variante: str) -> dict:
    return {
        "format": PACKAGE_FORMAT,
        "variante": variante,
        "version_manifeste": PACKAGE_VERSION,
        "version_moteur": PAPERX_VERSION,
        "reference_commande": order_ref,
        "etat": STATE_NON_EXECUTABLE,
        "gcode_present": False,
        "acces_imprimante": False,
        "paiement_active": pricing.PAYMENT_ENABLED,
        "texte": {
            "sha256": layout.source.sha256,
            "octets": layout.source.byte_length,
            "caracteres": layout.source.char_length,
            "preservation_exacte": layout.preservation_ok(),
            "normalisation_unicode": "aucune",
        },
    }


def build_client(order_ref: str,
                 layout: LayoutResult,
                 trajectories: tuple[PageTrajectory, ...],
                 validations: tuple[ValidationReport, ...],
                 estimate: Estimate,
                 personalization: dict) -> PreparationPackage:
    """Dossier remis au client. Ni coûts d'atelier, ni durées, ni codes internes."""
    entries: dict[str, bytes] = {"texte-source.txt": layout.source.text.encode("utf-8")}
    for traj, val in zip(trajectories, validations):
        entries[f"pages/page-{traj.page_number:02d}.svg"] = svg_mod.render_page(
            layout, traj, val.reach, val.machine_ready).encode("utf-8")
    entries["devis.json"] = _json_bytes(estimate.as_client_dict())
    entries["LISEZ-MOI.txt"] = LISEZ_MOI_CLIENT.encode("utf-8")

    files, fingerprint = _file_list(entries)
    manifest = {
        **_common_manifest(order_ref, layout, VARIANTE_CLIENT),
        "raison_etat": (
            "Les pages de ce dossier sont une simulation du tracé. Rien n'a été "
            "écrit sur du papier, et aucune machine n'a été pilotée."
        ),
        "pages": len(layout.pages),
        "feuilles": estimate.sheets,
        "ecriture": {
            "personnalisee": False,
            "libelle": "écriture de démonstration, ne reproduit l'écriture de personne",
            "statut_personnalisation": personalization.get("statut"),
        },
        "devis": estimate.as_client_dict(),
        "retournement_a_la_main": estimate.sides.value == "recto_verso",
        "fichiers": files,
        "empreinte_dossier": fingerprint,
    }
    entries["MANIFESTE.json"] = _json_bytes(manifest)
    return PreparationPackage(VARIANTE_CLIENT, f"paperx-dossier-{order_ref}.zip",
                              _zip(entries), manifest)


def build_operator(order_ref: str,
                   layout: LayoutResult,
                   trajectories: tuple[PageTrajectory, ...],
                   validations: tuple[ValidationReport, ...],
                   machine: MachineProfile,
                   speeds: SpeedProfile,
                   limits: ValidationLimits,
                   estimate: Estimate,
                   metrics: JobMetrics,
                   personalization: dict) -> PreparationPackage:
    """Dossier interne : tout, coûts d'atelier et durées compris."""
    entries: dict[str, bytes] = {"texte-source.txt": layout.source.text.encode("utf-8")}

    for traj, val in zip(trajectories, validations):
        n = f"{traj.page_number:02d}"
        entries[f"pages/page-{n}.svg"] = svg_mod.render_page(
            layout, traj, val.reach, val.machine_ready).encode("utf-8")
        entries[f"trajectoires/page-{n}.json"] = _json_bytes(page_as_dict(traj))
        entries[f"validation/revue-page-{n}.txt"] = emit.review_sheet(
            traj, machine, val).encode("utf-8")

    entries["validation/rapport.json"] = _json_bytes(
        report_mod.build(layout, trajectories, validations, machine, speeds, limits))
    entries["devis-client.json"] = _json_bytes(estimate.as_client_dict())
    entries["devis-operateur.json"] = _json_bytes(estimate.as_dict())
    entries["simulation.json"] = _json_bytes(metrics.as_dict())
    entries["LISEZ-MOI.txt"] = (
        LISEZ_MOI_OPERATEUR + "".join(f"  - {t}\n" for t in UNMEASURED_TRIALS)
        + "\n" + TRIALS_NOTE + "\n").encode("utf-8")

    files, fingerprint = _file_list(entries)
    manifest = {
        **_common_manifest(order_ref, layout, VARIANTE_OPERATEUR),
        "raison_etat": gate.GATE_REASON,
        "code_verrou": gate.GATE_CODE,
        "sortie_machine_disponible": gate.MACHINE_OUTPUT_AVAILABLE,
        "profils": {
            "papier": layout.paper.ref(),
            "ecriture": layout.hand_ref,
            "machine": machine.ref(),
            "vitesses": speeds.ref(),
            "limites_validation": limits.ref(),
            "hypotheses_temps": metrics.timing.ref(),
            "couts_operateur": metrics.costs.ref(),
        },
        "personnalisation": personalization,
        "devis_client": estimate.as_client_dict(),
        "devis_operateur": estimate.as_dict(),
        "couts_operateur": metrics.costs.as_dict(),
        "retournement": {
            "mode": estimate.sides.value,
            "manuel": estimate.sides.value == "recto_verso",
            "reprise_automatique": False,
            "interventions_humaines": [s.as_dict() for s in metrics.steps],
        },
        "validation": {
            "trajectoire_valide": all(v.trajectory_valid for v in validations),
            "pret_machine": any(v.machine_ready for v in validations),
            "constats_bloquants": sorted({
                code for v in validations for code in v.blocking_codes()}),
        },
        "a_mesurer_par_essais_physiques": list(UNMEASURED_TRIALS),
        "note_essais": TRIALS_NOTE,
        "fichiers": files,
        "empreinte_dossier": fingerprint,
    }
    entries["MANIFESTE.json"] = _json_bytes(manifest)
    return PreparationPackage(VARIANTE_OPERATEUR,
                              f"paperx-dossier-operateur-{order_ref}.zip",
                              _zip(entries), manifest)
