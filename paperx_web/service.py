"""Cœur métier du site local : il assemble le moteur `paperx`, sans le refaire.

Toutes les règles dures viennent du moteur : préservation exacte du texte,
profils versionnés, validateur, verrou de sortie machine, prix cible. Ce module
n'en réécrit aucune ; il choisit les profils, applique les limites d'usage du
site et compose les réponses.

Deux modes d'écriture, jamais confondus :

- `demo` : écriture GÉNÉRIQUE SYNTHÉTIQUE, style choisi parmi des
  transformations géométriques déclarées. Rien n'est appris de personne.
- `personnalise` : un échantillon manuscrit est conservé en privé et la commande
  passe **en attente**. Aucune écriture générique n'est servie à la place en
  douce : les aperçus restent possibles, mais ils sont marqués « aperçu
  technique — ce n'est pas votre écriture », et l'export de production est
  refusé.
"""

from __future__ import annotations

from dataclasses import dataclass

from paperx import (PAPERX_VERSION, duplex, emit, hands, layout as layout_mod,
                    machine as machine_mod, package, paper, pricing, simulation,
                    strokes, svg as svg_mod, textsource, trajexport, validator)
from paperx.errors import CalibrationRequired, PaperxError
from paperx.gate import GATE_CODE, GATE_REASON, MACHINE_OUTPUT_AVAILABLE
from paperx.provider import DEFAULT_PROVIDER

SERVICE_VERSION = "1.0.0"

#: Limites d'usage du site local. Un dépassement est REFUSÉ, jamais tronqué.
MAX_CHARS = 20_000
MAX_PAGES = 40

MODE_DEMO = "demo"
MODE_PERSONNALISE = "personnalise"
MODES = (MODE_DEMO, MODE_PERSONNALISE)

PERSO_SANS_OBJET = "SANS_OBJET"
PERSO_EN_ATTENTE = "EN_ATTENTE_FOURNISSEUR"

APERCU_TECHNIQUE_NOTE = (
    "APERÇU TECHNIQUE — ce n'est PAS votre écriture. Aucun fournisseur de "
    "personnalisation n'existe : votre échantillon est conservé en privé et la "
    "commande reste en attente. Cet aperçu emploie une écriture générique "
    "synthétique, uniquement pour vérifier la mise en page et la mécanique."
)

DEMO_NOTE = (
    "Écriture GÉNÉRIQUE SYNTHÉTIQUE : tracés écrits à la main dans le moteur, "
    "puis transformés géométriquement. Elle ne ressemble à l'écriture de personne "
    "et ne prétend pas le faire."
)

#: Profils employés par le site. Tous versionnés, tous non mesurés.
PAPER = paper.DEMO_A4
MACHINE = machine_mod.P1S_UNCALIBRATED
SPEEDS = strokes.DEMO_SPEEDS
LIMITS = validator.DEFAULT_LIMITS
TIMING = simulation.DEMO_TIMING


class ServiceError(PaperxError):
    """Demande refusée : texte hors limites, option inconnue, échantillon manquant."""


@dataclass(frozen=True)
class Options:
    mode: str
    style_id: str
    sides: duplex.Sides
    costs: duplex.OperatorCosts

    def as_dict(self) -> dict:
        return {
            "mode_ecriture": self.mode,
            "style": self.style_id,
            "mode_impression": self.sides.value,
            "couts_operateur": self.costs.as_dict(),
        }


def parse_options(payload: dict) -> Options:
    mode = payload.get("mode_ecriture", MODE_DEMO)
    if mode not in MODES:
        raise ServiceError(f"mode d'écriture inconnu : {mode!r} (attendu : {list(MODES)})")

    style_id = payload.get("style") or hands.DEFAULT_STYLE_ID
    if style_id not in hands.STYLES:
        raise ServiceError(
            f"style inconnu : {style_id!r} (disponibles : {sorted(hands.STYLES)})")

    sides = duplex.parse_sides(payload.get("mode_impression", duplex.Sides.RECTO.value))
    return Options(mode=mode, style_id=style_id, sides=sides,
                   costs=parse_costs(payload.get("couts_operateur")))


def parse_costs(raw: object) -> duplex.OperatorCosts:
    """Coûts opérateur saisis dans l'interface : toujours des HYPOTHÈSES.

    Une valeur absente ou vide laisse le coût INCONNU — donc le supplément reste
    « à établir ». Rien n'est complété par défaut.
    """
    if not isinstance(raw, dict):
        return duplex.UNKNOWN_COSTS

    def number(key: str) -> float | None:
        value = raw.get(key)
        if value is None or value == "":
            return None
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            raise ServiceError(f"coût opérateur invalide pour {key} : {value!r}") from None
        if parsed != parsed or parsed in (float("inf"), float("-inf")) or parsed < 0:
            raise ServiceError(f"coût opérateur invalide pour {key} : {value!r}")
        return parsed

    flip = number("secondes_retournement")
    realign = number("secondes_recalage")
    control = number("secondes_controle_alignement")
    rate = number("taux_horaire_centimes")
    spoil = number("taux_rates")

    if None in (flip, realign, control, rate, spoil):
        return duplex.UNKNOWN_COSTS
    if spoil > 1.0:
        raise ServiceError("taux de ratés attendu entre 0 et 1")
    return duplex.hypothesis_costs(flip, realign, control, int(round(rate)), spoil)


def load_text(raw_text: object) -> textsource.SourceText:
    """Charge le texte SANS le modifier : ni rognage, ni normalisation, ni troncature."""
    if not isinstance(raw_text, str):
        raise ServiceError("texte manquant : envoyez une chaîne de caractères.")
    if not raw_text:
        raise ServiceError("texte vide : rien à écrire.")
    if len(raw_text) > MAX_CHARS:
        raise ServiceError(
            f"texte trop long pour ce site local : {len(raw_text)} caractères "
            f"(maximum {MAX_CHARS}). Le texte n'est PAS tronqué : réduisez-le "
            "vous-même ou découpez la commande.")
    return textsource.from_bytes(raw_text.encode("utf-8"), origin="<saisie navigateur>")


@dataclass(frozen=True)
class Composition:
    """Un texte composé avec un jeu d'options : tout ce dont l'interface a besoin."""

    source: textsource.SourceText
    options: Options
    layout: layout_mod.LayoutResult
    trajectories: tuple[strokes.PageTrajectory, ...]
    validations: tuple[validator.ValidationReport, ...]
    estimate: duplex.Estimate
    metrics: simulation.JobMetrics

    @property
    def faces(self) -> int:
        return len(self.layout.pages)

    @property
    def reach(self):
        return self.validations[0].reach if self.validations else None


def compose(source: textsource.SourceText, options: Options) -> Composition:
    hand = hands.get(options.style_id)
    result = layout_mod.paginate(source, PAPER, hand)

    if len(result.pages) > MAX_PAGES:
        raise ServiceError(
            f"{len(result.pages)} pages : au-delà de la limite de {MAX_PAGES} pages "
            "de ce site local. Aucune réduction du texte ni de l'écriture n'est "
            "appliquée pour faire tenir : découpez la commande.")

    trajectories = strokes.build_all(result, SPEEDS)
    validations = tuple(
        validator.validate_page(t, PAPER, MACHINE, SPEEDS, LIMITS) for t in trajectories)
    reach = validations[0].reach if validations else None
    estimate = duplex.estimate(len(result.pages), options.sides, options.costs)
    metrics = simulation.job_metrics(result, trajectories, SPEEDS, options.sides,
                                     TIMING, options.costs, reach)
    return Composition(source, options, result, trajectories, validations,
                       estimate, metrics)


# --- Personnalisation --------------------------------------------------------


def personalization(options: Options, sample: dict | None) -> dict:
    """État de la personnalisation. Jamais de substitution silencieuse."""
    caps = DEFAULT_PROVIDER.capabilities()
    style = hands.get(options.style_id)
    common = {
        "fournisseur": caps.ref(),
        "fournisseur_disponible": False,
        "ecriture_employee": style.as_dict(),
        "ecriture_personnalisee": False,
        "export_production_autorise": False,
    }
    if options.mode == MODE_DEMO:
        return {
            **common,
            "mode": MODE_DEMO,
            "statut": PERSO_SANS_OBJET,
            "libelle": "mode démonstration — écriture générique synthétique",
            "apercu_technique": False,
            "echantillon_conserve": False,
            "message": DEMO_NOTE,
        }
    return {
        **common,
        "mode": MODE_PERSONNALISE,
        "statut": PERSO_EN_ATTENTE,
        "libelle": "personnalisation EN ATTENTE — aucun fournisseur disponible",
        "apercu_technique": True,
        "echantillon_conserve": bool(sample),
        "echantillon": {k: sample.get(k) for k in ("sha256", "type", "largeur_px",
                                                   "hauteur_px", "consentement")}
        if sample else None,
        "message": APERCU_TECHNIQUE_NOTE,
    }


def production_refusal(composition: Composition, perso: dict) -> dict:
    """Raisons du refus d'export production/machine. Toujours au moins une."""
    reasons = [
        f"{GATE_CODE} — {GATE_REASON}",
        f"profil machine {MACHINE.ref()} non calibré : hauteur de plume et offset Z inconnus",
        f"profil papier {PAPER.ref()} non mesuré",
        f"vitesses {SPEEDS.ref()} déclarées, jamais mesurées",
    ]
    if perso["statut"] == PERSO_EN_ATTENTE:
        reasons.append(
            "personnalisation demandée mais indisponible : aucune écriture "
            "personnalisée ne peut être produite, et aucune écriture générique "
            "ne sera substituée à la vôtre")
    blocking = sorted({c for v in composition.validations for c in v.blocking_codes()})
    if blocking:
        reasons.append("constats bloquants du validateur : " + ", ".join(blocking))
    return {
        "autorise": False,
        "sortie_machine_disponible": MACHINE_OUTPUT_AVAILABLE,
        "gcode_produit": False,
        "acces_imprimante": False,
        "paiement_active": pricing.PAYMENT_ENABLED,
        "raisons": reasons,
        "a_mesurer_par_essais_physiques": list(simulation.UNMEASURED_TRIALS),
        "note_essais": simulation.TRIALS_NOTE,
    }


def machine_refusal_message(composition: Composition) -> str:
    """Message produit par le moteur lui-même, pas réécrit ici."""
    try:
        emit.machine_output(composition.trajectories[0], MACHINE, composition.validations[0])
    except CalibrationRequired as exc:
        return str(exc)
    except NotImplementedError as exc:      # pragma: no cover - verrou levé un jour
        return str(exc)
    raise AssertionError("le moteur a laissé passer une sortie machine")


# --- Sorties -----------------------------------------------------------------


def page_svg(composition: Composition, page_number: int) -> str:
    for traj, val in zip(composition.trajectories, composition.validations):
        if traj.page_number == page_number:
            return svg_mod.render_page(composition.layout, traj, val.reach,
                                       val.machine_ready)
    raise ServiceError(f"page inconnue : {page_number}")


def page_trajectory(composition: Composition, page_number: int) -> dict:
    for traj in composition.trajectories:
        if traj.page_number == page_number:
            return trajexport.page_as_dict(traj)
    raise ServiceError(f"page inconnue : {page_number}")


RAISONS_COURTES = (
    "La machine n'est pas encore réglée : personne ne sait exactement où elle "
    "poserait le stylo sur la feuille.",
    "Les vitesses affichées sont choisies sur le papier, pas mesurées.",
    "Rien n'a encore été écrit sur du vrai papier : lisibilité, alignement et "
    "ratés restent à vérifier.",
)


def build_packages(order_ref: str, composition: Composition, perso: dict):
    """Construit les deux dossiers figés : celui du client, celui de l'opérateur."""
    client = package.build_client(
        order_ref=order_ref,
        layout=composition.layout,
        trajectories=composition.trajectories,
        validations=composition.validations,
        estimate=composition.estimate,
        personalization=perso,
    )
    operateur = package.build_operator(
        order_ref=order_ref,
        layout=composition.layout,
        trajectories=composition.trajectories,
        validations=composition.validations,
        machine=MACHINE,
        speeds=SPEEDS,
        limits=LIMITS,
        estimate=composition.estimate,
        metrics=composition.metrics,
        personalization=perso,
    )
    return client, operateur


def frozen_profiles(composition: Composition) -> dict:
    """Profils employés au moment du devis : ils figent la commande."""
    return {
        "version_moteur": PAPERX_VERSION,
        "version_service": SERVICE_VERSION,
        "papier": composition.layout.paper.ref(),
        "ecriture": composition.layout.hand_ref,
        "machine": MACHINE.ref(),
        "vitesses": SPEEDS.ref(),
        "limites_validation": LIMITS.ref(),
        "hypotheses_temps": TIMING.ref(),
        "couts_operateur": composition.options.costs.ref(),
    }


def client_summary(composition: Composition, perso: dict) -> dict:
    """Ce que voit la personne qui commande.

    Sans temps d'exécution, sans coûts d'atelier, sans code de validateur : ces
    informations appartiennent à l'espace opérateur, y compris repliées.
    """
    layout = composition.layout
    return {
        "texte": {
            "caracteres": layout.source.char_length,
            "sha256": layout.source.sha256,
            "preservation_exacte": layout.preservation_ok(),
            "note": "votre texte est repris à l'identique : rien n'est supprimé, "
                    "remplacé ni simplifié",
        },
        "pages": len(layout.pages),
        "feuilles": composition.estimate.sheets,
        "apercu": {
            "nature": "simulation du tracé",
            "note": "ces pages montrent le chemin que suivrait le stylo ; "
                    "ce n'est pas une photo du résultat final",
        },
        "ecriture": {
            "personnalisee": False,
            "libelle": hands.get(composition.options.style_id).label,
            "statut_personnalisation": perso["statut"],
            "message": perso["message"],
        },
        "signalements": [
            {
                "caractere": u.char,
                "occurrences": u.count,
                "message": f"le caractère « {u.char} » ne peut pas être tracé pour "
                           "l'instant : il reste dans votre texte, mais son "
                           "emplacement sera laissé vide et signalé",
            }
            for u in layout.coverage.unsupported
        ],
        "devis": composition.estimate.as_client_dict(),
        "production": {
            "autorise": False,
            "resume": "Ce site simule l'écriture. Il ne lance aucune écriture réelle.",
            "raisons": list(RAISONS_COURTES),
        },
    }


def operator_summary(composition: Composition, perso: dict) -> dict:
    """Vue interne : profils, validation, temps décomposés, coûts d'atelier."""
    layout = composition.layout
    return {
        "version_service": SERVICE_VERSION,
        "profils_figes": frozen_profiles(composition),
        "texte": {
            "sha256": layout.source.sha256,
            "caracteres": layout.source.char_length,
            "octets": layout.source.byte_length,
            "preservation_exacte": layout.preservation_ok(),
            "normalisation_unicode": "aucune",
        },
        "mise_en_page": {
            "pages": len(layout.pages),
            "lignes": len(layout.lines),
            "caracteres_dessines": sum(len(l.chars) for l in layout.lines),
            "papier": layout.paper.as_dict(),
            "metriques": layout.metrics.as_dict(),
            "evenements": [e.as_dict() for e in layout.events],
            "couverture": layout.coverage.as_dict(),
            "taille_ecriture_mm": layout.paper.font_size_mm,
            "note_taille": (
                f"corps fixé à {layout.paper.font_size_mm} mm : l'écriture garde sa "
                "taille humaine, elle n'est jamais réduite pour faire tenir le texte"
            ),
        },
        "devis_client": composition.estimate.as_client_dict(),
        "devis_operateur": composition.estimate.as_dict(),
        "couts_operateur": composition.options.costs.as_dict(),
        "simulation": composition.metrics.as_dict(),
        "personnalisation": perso,
        "validation": [v.as_dict() for v in composition.validations],
        "production": production_refusal(composition, perso),
        "options": composition.options.as_dict(),
        "pages": [
            {"numero": t.page_number, "traits": len(t.strokes), "levees": t.pen_lifts}
            for t in composition.trajectories
        ],
    }
