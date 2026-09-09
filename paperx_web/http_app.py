"""Routeur HTTP local, garde-fous, et séparation client / opérateur.

Deux espaces distincts, pas deux onglets d'une même page :

- **client** (`/`) : son texte, sa photo, la simulation du tracé, ses pages, son
  prix, le suivi de sa commande. Aucun temps d'exécution, aucun coût d'atelier,
  aucun code interne — pas même replié ;
- **opérateur** (`/operateur`) : tout le reste, derrière une clé imprimée au
  démarrage du serveur dans le terminal. Une personne qui ouvre le site sans
  cette clé ne peut pas obtenir les données internes, même en appelant l'API.

Garde-fous, sur toutes les requêtes :

- `Host` vérifié (protection contre le re-liage DNS) ;
- `Origin` et `Referer`, s'ils sont présents, doivent être locaux ;
- jeton de session obligatoire sur `POST` et `DELETE` : il est lu via
  `GET /api/config`, qu'une page tierce ne peut pas lire (aucun en-tête CORS) ;
- corps de requête plafonnés, types de contenu contrôlés ;
- fichiers statiques servis depuis une liste blanche fermée.

Aucune sortie machine, aucun G-code, aucun paiement, aucun appel réseau sortant.
"""

from __future__ import annotations

import json
import re
import secrets
import threading
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from paperx import duplex, hands, pricing, simulation
from paperx.errors import PaperxError
from paperx.gate import GATE_CODE, GATE_REASON, MACHINE_OUTPUT_AVAILABLE

from . import PAPERX_WEB_VERSION, service, store as store_mod, uploads
from .store import Store, StoreError

MAX_JSON_BYTES = 1024 * 1024
MAX_UPLOAD_BYTES = uploads.MAX_BYTES + 1024 * 1024      # marge d'enveloppe multipart
SESSION_TOKEN_HEADER = "X-Paperx-Jeton"
OPERATOR_HEADER = "X-Paperx-Operateur"
OPERATOR_COOKIE = "paperx_operateur"

STATIC_DIR = Path(__file__).resolve().parent / "static"

#: Liste blanche fermée : aucun chemin client n'est concaténé à un répertoire.
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/operateur": ("operateur.html", "text/html; charset=utf-8"),
    "/static/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/static/app.js": ("app.js", "application/javascript; charset=utf-8"),
    "/static/operateur.js": ("operateur.js", "application/javascript; charset=utf-8"),
}

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    ),
}

_ORDER_PATH = re.compile(
    r"^/api/commande/([0-9a-f]{32})(/[a-z_]+|/dossier\.zip)?$")
_OPERATOR_ORDER_PATH = re.compile(
    r"^/api/operateur/commande/([0-9a-f]{32})(/[a-z_]+|/dossier\.zip)?$")


class Refus(Exception):
    """Refus HTTP explicite : code, message, détails."""

    def __init__(self, status: int, message: str, detail: object = None) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.detail = detail


class App:
    """État du serveur : jeton de session, clé opérateur, magasin local."""

    def __init__(self, store: Store, host: str, port: int) -> None:
        self.store = store
        self.host = host
        self.port = port
        self.token = secrets.token_urlsafe(32)
        self.operator_key = secrets.token_urlsafe(24)
        self.order_creation_lock = threading.RLock()
        self.allowed_hosts = frozenset({
            f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}",
        })
        self.allowed_origins = frozenset({
            f"http://127.0.0.1:{port}", f"http://localhost:{port}",
            f"http://[::1]:{port}",
        })

    # --- garde-fous --------------------------------------------------------

    def check_host(self, headers) -> None:
        host = (headers.get("Host") or "").strip().lower()
        if host not in self.allowed_hosts:
            raise Refus(403, "hôte non autorisé : ce site ne répond qu'en local.",
                        {"host_recu": host, "hotes_attendus": sorted(self.allowed_hosts)})

    def check_mutation(self, headers) -> None:
        origin = (headers.get("Origin") or "").strip()
        if origin and origin.lower() not in self.allowed_origins:
            raise Refus(403, "origine refusée pour une requête modifiante.",
                        {"origine_recue": origin})
        referer = (headers.get("Referer") or "").strip()
        if referer and not any(referer.lower().startswith(o) for o in self.allowed_origins):
            raise Refus(403, "référent refusé pour une requête modifiante.",
                        {"referent_recu": referer})
        token = (headers.get(SESSION_TOKEN_HEADER) or "").strip()
        if not token or not secrets.compare_digest(token, self.token):
            raise Refus(403,
                        "jeton de session absent ou invalide : les requêtes modifiantes "
                        "doivent porter l'en-tête " + SESSION_TOKEN_HEADER + ".",
                        {"en_tete_attendu": SESSION_TOKEN_HEADER})

    def check_operator(self, headers) -> None:
        """L'espace opérateur exige la clé imprimée au démarrage du serveur."""
        fourni = (headers.get(OPERATOR_HEADER) or "").strip()
        if not fourni:
            raw = headers.get("Cookie")
            if raw:
                cookie = SimpleCookie()
                try:
                    cookie.load(raw)
                except Exception:                       # noqa: BLE001 - en-tête hostile
                    cookie = SimpleCookie()
                morsel = cookie.get(OPERATOR_COOKIE)
                fourni = morsel.value.strip() if morsel else ""
        if not fourni or not secrets.compare_digest(fourni, self.operator_key):
            raise Refus(403,
                        "espace opérateur : clé absente ou invalide. Elle est imprimée "
                        "dans le terminal au démarrage du serveur.",
                        {"en_tete_attendu": OPERATOR_HEADER})


# --- lecture de corps --------------------------------------------------------


def _drain(handler: BaseHTTPRequestHandler, combien: int) -> None:
    """Vide une partie du corps sans la conserver. Jamais plus que `combien`."""
    restant = combien
    while restant > 0:
        morceau = handler.rfile.read(min(65536, restant))
        if not morceau:
            return
        restant -= len(morceau)


def _read_body(handler: BaseHTTPRequestHandler, limit: int) -> bytes:
    raw_length = handler.headers.get("Content-Length")
    if raw_length is None:
        raise Refus(411, "longueur de contenu absente : requête refusée.")
    try:
        length = int(raw_length)
    except ValueError:
        raise Refus(400, "longueur de contenu illisible.") from None
    if length < 0:
        raise Refus(400, "longueur de contenu négative.")
    if length > limit:
        # Le corps est lu et jeté, dans une limite bornée, pour que le client
        # puisse finir d'émettre et LIRE le refus plutôt que de se prendre une
        # connexion coupée en pleine écriture.
        _drain(handler, min(length, limit * 8))
        raise Refus(413, f"corps de requête trop volumineux : {length} octets "
                         f"(maximum {limit}).")
    data = handler.rfile.read(length)
    if len(data) != length:
        raise Refus(400, "corps de requête incomplet.")
    return data


def _read_json(handler: BaseHTTPRequestHandler) -> dict:
    content_type = (handler.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    if content_type != "application/json":
        raise Refus(415, "type de contenu attendu : application/json.",
                    {"recu": content_type})
    body = _read_body(handler, MAX_JSON_BYTES)
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Refus(400, f"corps JSON illisible : {exc}") from None
    if not isinstance(payload, dict):
        raise Refus(400, "objet JSON attendu.")
    return payload


def _parse_multipart(body: bytes, content_type: str) -> tuple[dict[str, str], str, bytes]:
    """Renvoie (champs texte, nom de fichier annoncé, octets). Analyseur minimal."""
    match = re.search(r'boundary="?([^";]+)"?', content_type)
    if not match:
        raise Refus(400, "limite multipart absente.")
    boundary = b"--" + match.group(1).encode("latin-1")
    champs: dict[str, str] = {}
    fichier: tuple[str, bytes] | None = None

    for part in body.split(boundary):
        part = part.lstrip(b"\r\n")
        if part in (b"", b"--", b"--\r\n"):
            continue
        head, separator, payload = part.partition(b"\r\n\r\n")
        if not separator:
            continue
        headers = head.decode("latin-1", errors="replace")
        disposition = next(
            (line for line in headers.splitlines()
             if line.lower().startswith("content-disposition:")), "")
        payload = payload.rstrip(b"\r\n")
        nom_fichier = re.search(r'filename="([^"]*)"', disposition)
        if nom_fichier is not None:
            if fichier is None:
                fichier = (nom_fichier.group(1), payload)
            continue
        nom_champ = re.search(r'name="([^"]*)"', disposition)
        if nom_champ is not None:
            champs[nom_champ.group(1)] = payload.decode("utf-8", errors="replace")

    if fichier is None:
        raise Refus(400, "aucun fichier trouvé dans la requête.")
    return champs, fichier[0], fichier[1]


# --- réponses ----------------------------------------------------------------


def _send(handler: BaseHTTPRequestHandler, status: int, body: bytes,
          content_type: str, extra: dict | None = None) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    for key, value in SECURITY_HEADERS.items():
        handler.send_header(key, value)
    for key, value in (extra or {}).items():
        handler.send_header(key, value)
    handler.end_headers()
    if handler.command != "HEAD":
        handler.wfile.write(body)


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    body = (json.dumps(payload, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    _send(handler, status, body, "application/json; charset=utf-8")


# --- composition partagée ----------------------------------------------------


def _composition_from(payload: dict, *, operateur: bool) -> tuple[service.Composition, dict]:
    """Compose un texte. Les coûts d'atelier ne sont lus que côté opérateur."""
    source = service.load_text(payload.get("texte"))
    options = service.parse_options(payload if operateur
                                    else {**payload, "couts_operateur": None})
    composition = service.compose(source, options)
    perso = service.personalization(options, payload.get("echantillon"))
    return composition, perso


# --- routes client -----------------------------------------------------------


def route_config(app: App) -> dict:
    app.store.purge_orphan_samples()
    return {
        "version_site": PAPERX_WEB_VERSION,
        "jeton": app.token,
        "en_tete_jeton": SESSION_TOKEN_HEADER,
        "adresse": f"http://{app.host}:{app.port}",
        "tarif": {
            "prix_par_page_centimes": pricing.PRICE_PER_A4_CENTS,
            "zone": pricing.SERVICE_AREA,
            "remise": "à définir",
            "paiement_active": pricing.PAYMENT_ENABLED,
            "note": "Le prix porte sur la page écrite. Le recto-verso économise du "
                    "papier, pas de l'écriture.",
        },
        "styles": [
            {"code": style.style_id, "libelle": style.label, "personnalise": False}
            for style in hands.STYLES.values()
        ],
        "modes_ecriture": [
            {"code": service.MODE_DEMO,
             "libelle": "Écriture de démonstration",
             "note": "Elle ne reproduit l'écriture de personne."},
            {"code": service.MODE_PERSONNALISE,
             "libelle": "Mon écriture",
             "note": "Pas encore possible : votre photo est conservée et la commande "
                     "reste en attente."},
        ],
        "modes_impression": [
            {"code": duplex.Sides.RECTO.value, "libelle": "Recto seul",
             "explication": "une page par feuille"},
            {"code": duplex.Sides.RECTO_VERSO.value, "libelle": "Recto-verso",
             "explication": "deux pages par feuille",
             "note": "le retournement se fait à la main"},
        ],
        "limites": {
            "caracteres_max": service.MAX_CHARS,
            "pages_max": service.MAX_PAGES,
            "depot": uploads.policy(),
            "note": "un dépassement est refusé, jamais tronqué",
        },
        "avertissement": (
            "Ce site simule l'écriture : aucune feuille n'est écrite, aucune machine "
            "n'est pilotée, aucun paiement n'est possible."
        ),
    }


def route_composer(payload: dict) -> dict:
    composition, perso = _composition_from(payload, operateur=False)
    resume = service.client_summary(composition, perso)
    resume["liste_pages"] = [t.page_number for t in composition.trajectories]
    return resume


def route_apercu(payload: dict) -> dict:
    composition, _ = _composition_from(payload, operateur=False)
    demandees = payload.get("pages")
    numeros = ([p.number for p in composition.layout.pages] if not demandees
               else [int(n) for n in demandees])
    return {
        "pages": [{"numero": n, "svg": service.page_svg(composition, n)} for n in numeros],
        "total": len(composition.layout.pages),
        "nature": "simulation du tracé",
    }


def _trajectoire_client(brut: dict) -> dict:
    """Géométrie seule : les vitesses machine restent dans l'espace opérateur."""
    segments = []
    for segment in brut.get("segments", []):
        allege = {k: v for k, v in segment.items() if k != "vitesse_mm_s"}
        segments.append(allege)
    return {
        "page": brut.get("page"),
        "unite": brut.get("unite"),
        "repere": brut.get("repere"),
        "segments": segments,
        "emplacements_non_traces": brut.get("emplacements_non_traces", []),
        "nature": "simulation du tracé — la vitesse d'affichage n'a rien à voir avec "
                  "une vitesse d'écriture réelle",
    }


def _papier_client(papier: dict) -> dict:
    """Géométrie de la feuille, sans référence de profil interne."""
    return {
        "format_mm": papier["format_mm"],
        "marges_mm": papier["marges_mm"],
        "largeur_trait_mm": papier["largeur_trait_mm"],
    }


def _atteignabilite_client(reach) -> dict | None:
    """Rectangles seuls : ni profil machine, ni profil papier, ni pose de feuille."""
    if reach is None:
        return None
    brut = reach.as_dict()
    return {
        "zone_atteignable_mm": brut["zone_atteignable_mm"],
        "zones_inaccessibles_mm": brut["zones_inaccessibles_mm"],
        "part_page_inaccessible": brut["part_page_inaccessible"],
        "mise_a_echelle_appliquee": False,
        "note": "la machine n'atteint pas toute la feuille ; rien n'est réduit pour "
                "faire tenir le texte dans ce qu'elle atteint",
    }


def route_simulation(payload: dict) -> dict:
    composition, _ = _composition_from(payload, operateur=False)
    numero = int(payload.get("page", 1))
    return {
        "page": numero,
        "total_pages": len(composition.layout.pages),
        "trajectoire": _trajectoire_client(service.page_trajectory(composition, numero)),
        "papier": _papier_client(composition.layout.paper.as_dict()),
        "atteignabilite": _atteignabilite_client(composition.reach),
        "zone_machine": {
            "note": "la machine n'atteint pas toute la feuille, et sa position exacte "
                    "par rapport à la feuille n'est pas encore réglée",
        },
        "interventions_a_la_main": [
            {"apres_page": s.after_page, "page_suivante": s.next_page,
             "type": s.kind, "feuille": s.sheet, "consignes": list(s.instructions),
             "confirmation_requise": True, "reprise_automatique": False}
            for s in composition.metrics.steps
        ],
    }


def route_machine_refus(payload: dict) -> dict:
    composition, perso = _composition_from(payload, operateur=False)
    return {
        "autorise": False,
        "resume": "Ce site ne lance aucune écriture réelle.",
        "raisons": list(service.RAISONS_COURTES),
        "personnalisation_en_attente": perso["statut"] == service.PERSO_EN_ATTENTE,
    }


def route_echantillon(app: App, handler: BaseHTTPRequestHandler) -> dict:
    content_type = handler.headers.get("Content-Type") or ""
    if not content_type.lower().startswith("multipart/form-data"):
        raise Refus(415, "type de contenu attendu : multipart/form-data.")
    body = _read_body(handler, MAX_UPLOAD_BYTES)
    champs, declared_name, data = _parse_multipart(body, content_type)

    # Le consentement est exigé AVANT tout enregistrement : rien n'est écrit sur
    # le disque tant qu'il n'a pas été donné.
    if champs.get("consentement", "").strip().lower() not in ("oui", "true", "1"):
        raise Refus(400,
                    "consentement requis avant tout dépôt : votre photo n'est pas "
                    "enregistrée tant que vous ne l'avez pas donné.",
                    {"champ_attendu": "consentement"})

    verdict = uploads.check(data, declared_name)
    if not verdict.accepted:
        return {"accepte": False, "echantillon": verdict.as_dict(),
                "message": "dépôt refusé : " + " ; ".join(verdict.problems)}

    meta = app.store.save_sample(data, verdict, consent_ref="consentement navigateur")
    app.store.purge_orphan_samples()
    return {
        "accepte": True,
        "echantillon": {
            "id": meta["id"],
            "type": meta["type"],
            "largeur_px": meta["largeur_px"],
            "hauteur_px": meta["hauteur_px"],
            "octets": meta["octets"],
            "sha256": meta["sha256"],
            "statut": service.PERSO_EN_ATTENTE,
        },
        "message": (
            "Photo conservée sur cet ordinateur. Elle ne fabrique pas votre écriture : "
            "cette étape n'existe pas encore. Votre commande restera en attente, et "
            "aucune autre écriture ne sera présentée comme la vôtre."
        ),
        "note_suppression": (
            f"Un dépôt jamais rattaché à une commande est effacé automatiquement "
            f"au bout de {store_mod.ORPHAN_TTL_SECONDS // 60} minutes."
        ),
    }


def route_creer_commande(app: App, payload: dict) -> dict:
    # Le contrôle du rattachement et sa création forment une seule opération.
    with app.order_creation_lock:
        return _creer_commande(app, payload)


def _creer_commande(app: App, payload: dict) -> dict:
    """Crée la commande ET fige ses artefacts : le dossier remis ne bougera plus.

    Les coûts d'atelier ne sont PAS lus ici : une commande passée depuis l'espace
    client ne peut pas se voir attribuer des durées d'atelier inventées côté
    navigateur. Son supplément de retournement reste « à établir ».
    """
    composition, _ = _composition_from(payload, operateur=False)
    options = composition.options

    sample: dict | None = None
    if options.mode == service.MODE_PERSONNALISE:
        raw = payload.get("echantillon")
        sample_id = raw.get("id") if isinstance(raw, dict) else raw
        if not store_mod.valid_id(sample_id or ""):
            raise service.ServiceError(
                "mode personnalisé : déposez d'abord une photo de votre écriture. "
                "Aucune autre écriture ne sera enregistrée à sa place.")
        # Métadonnées SERVEUR uniquement : ce que le client annonce est ignoré.
        meta = app.store.get_sample(sample_id)
        if meta.get("commande") is not None:
            raise StoreError("échantillon déjà rattaché à une autre commande")
        if not meta.get("consentement"):
            raise service.ServiceError("échantillon sans consentement enregistré.")
        sample = {
            "id": meta["id"], "sha256": meta["sha256"], "type": meta["type"],
            "largeur_px": meta["largeur_px"], "hauteur_px": meta["hauteur_px"],
            "octets": meta["octets"], "consentement": True,
            "depose_le": meta["depose_le"], "statut": service.PERSO_EN_ATTENTE,
        }

    perso = service.personalization(options, sample)
    steps = [
        {**step.as_dict(), "index": i, "confirme": False, "confirme_le": None}
        for i, step in enumerate(composition.metrics.steps)
    ]
    etat = (store_mod.ETAT_ATTENTE_PERSONNALISATION
            if options.mode == service.MODE_PERSONNALISE else store_mod.ETAT_PRETE_REVUE)

    record = app.store.create_order({
        "etat": etat,
        "mode_ecriture": options.mode,
        "style": options.style_id,
        "mode_impression": options.sides.value,
        "texte": composition.layout.source.text,
        "texte_sha256": composition.layout.source.sha256,
        "caracteres": composition.layout.source.char_length,
        "faces": composition.estimate.faces,
        "feuilles": composition.estimate.sheets,
        "devis_client": composition.estimate.as_client_dict(),
        "devis_operateur": composition.estimate.as_dict(),
        "couts_operateur": options.costs.as_dict(),
        "profils_figes": service.frozen_profiles(composition),
        "simulation": composition.metrics.as_dict(),
        "validation": [v.as_dict() for v in composition.validations],
        "production": service.production_refusal(composition, perso),
        "echantillon": sample,
        "personnalisation": perso,
        "etapes_manuelles": steps,
    })

    try:
        client_pkg, operator_pkg = service.build_packages(record["id"], composition, perso)
        record["dossiers"] = {
            "client": app.store.save_artifact(record["id"], "client", client_pkg.content),
            "operateur": app.store.save_artifact(record["id"], "operateur",
                                                 operator_pkg.content),
            "fige_le": record["cree_le"],
            "note": "dossiers calculés une seule fois, à la création : un changement de "
                    "profil plus tard ne réécrit pas cette commande",
        }
        app.store.log(record, "artefacts_figes",
                      f"dossiers client et opérateur figés "
                      f"({composition.estimate.faces} page(s), "
                      f"{composition.estimate.sheets} feuille(s))")
        app.store.save_order(record)
        if sample:
            app.store.attach_sample(sample["id"], record["id"])
    except Exception:
        # Ne jamais utiliser delete_order ici : la photo doit rester disponible.
        app.store.discard_incomplete_order(record["id"], sample["id"] if sample else None)
        raise
    app.store.purge_orphan_samples()

    return {
        "commande": store_mod.client_view(record),
        "message": "Commande enregistrée sur cet ordinateur. Aucun paiement, aucune "
                   "écriture réelle, aucun envoi à une machine.",
    }


def route_dossier(app: App, order_id: str, variante: str) -> tuple[bytes, str]:
    """Sert le dossier FIGÉ à la création. Rien n'est recalculé ici."""
    record = app.store.get_order(order_id)
    dossiers = record.get("dossiers") or {}
    fiche = dossiers.get(variante)
    if not fiche:
        raise StoreError(f"aucun dossier {variante} figé pour cette commande")
    content = app.store.read_artifact(order_id, variante, fiche["sha256"])
    prefixe = "paperx-dossier" if variante == "client" else "paperx-dossier-operateur"
    return content, f"{prefixe}-{order_id}.zip"


# --- routes opérateur --------------------------------------------------------


def route_operateur_config(app: App) -> dict:
    return {
        "version_site": PAPERX_WEB_VERSION,
        "version_service": service.SERVICE_VERSION,
        "profils": {
            "papier": service.PAPER.as_dict(),
            "machine": service.MACHINE.as_dict(),
            "vitesses": service.SPEEDS.as_dict(),
            "limites_validation": service.LIMITS.as_dict(),
            "hypotheses_temps": service.TIMING.as_dict(),
        },
        "machine": {
            "sortie_disponible": MACHINE_OUTPUT_AVAILABLE,
            "code_verrou": GATE_CODE,
            "raison": GATE_REASON,
            "aire_travail_mm": [service.MACHINE.work_area_x_mm,
                                service.MACHINE.work_area_y_mm],
            "offsets_connus": False,
        },
        "etats": [{"code": e, "libelle": store_mod.ETAT_LABELS[e],
                   "transitions": sorted(store_mod.allowed_transitions(e))}
                  for e in store_mod.ETATS],
        "essais_a_mener": list(simulation.UNMEASURED_TRIALS),
        "note_essais": simulation.TRIALS_NOTE,
        "duree_vie_depot_orphelin_s": store_mod.ORPHAN_TTL_SECONDS,
    }


def route_operateur_composer(payload: dict) -> dict:
    composition, perso = _composition_from(payload, operateur=True)
    return service.operator_summary(composition, perso)


def route_operateur_simulation(payload: dict) -> dict:
    composition, perso = _composition_from(payload, operateur=True)
    numero = int(payload.get("page", 1))
    reach = composition.reach
    metrics = next((m for m in composition.metrics.pages if m.page_number == numero), None)
    if metrics is None:
        raise service.ServiceError(f"page inconnue : {numero}")
    return {
        "page": numero,
        "total_pages": len(composition.layout.pages),
        "trajectoire": service.page_trajectory(composition, numero),
        "metriques_page": metrics.as_dict(),
        "simulation": composition.metrics.as_dict(),
        "papier": composition.layout.paper.as_dict(),
        "bande_utile_mm": composition.layout.metrics.as_dict(),
        "atteignabilite": reach.as_dict() if reach else None,
        "machine": {
            "profil": service.MACHINE.ref(),
            "aire_travail_mm": [service.MACHINE.work_area_x_mm,
                                service.MACHINE.work_area_y_mm],
            "calibre": service.MACHINE.calibrated,
            "offsets_xy": None,
            "hauteur_plume_mm": service.MACHINE.pen_z_height_mm,
            "offset_z_mm": service.MACHINE.z_offset_mm,
            "note": (
                "Zone XY nominale 256 × 256 mm annoncée par le constructeur. Les "
                "offsets réels entre l'origine machine et la feuille sont INCONNUS."
            ),
        },
        "production": service.production_refusal(composition, perso),
    }


def route_operateur_machine(payload: dict) -> dict:
    composition, perso = _composition_from(payload, operateur=True)
    return {
        "autorise": False,
        "message_moteur": service.machine_refusal_message(composition),
        "production": service.production_refusal(composition, perso),
    }


def route_etat(app: App, order_id: str, payload: dict) -> dict:
    """Transition d'état. La table de `store` est la seule autorité."""
    cible = payload.get("etat")
    if cible not in store_mod.ETATS:
        raise service.ServiceError(
            f"état inconnu : {cible!r} (attendu : {list(store_mod.ETATS)})")
    record = app.store.get_order(order_id)
    actuel = record.get("etat", "")
    autorisees = store_mod.allowed_transitions(actuel)
    if cible == actuel:
        return {"commande": store_mod.operator_view(record), "inchange": True}
    if cible not in autorisees:
        detail = ""
        if actuel == store_mod.ETAT_ATTENTE_RETOURNEMENT:
            detail = (" Une intervention manuelle attend confirmation : la seule "
                      "sortie est la confirmation humaine du retournement.")
        raise service.ServiceError(
            f"transition refusée : {actuel} → {cible}. "
            f"Transitions autorisées : {sorted(autorisees) or 'aucune'}.{detail}")
    if cible == store_mod.ETAT_TERMINEE and store_mod.next_manual_step(record):
        raise service.ServiceError(
            "impossible de terminer : une intervention manuelle n'est pas confirmée.")

    record["etat"] = cible
    app.store.log(record, "changement_etat", f"{actuel} → {cible}")
    app.store.save_order(record)
    return {"commande": store_mod.operator_view(record)}


def route_attente_retournement(app: App, order_id: str, payload: dict) -> dict:
    """L'opérateur signale l'arrêt sur une intervention manuelle."""
    record = app.store.get_order(order_id)
    etape = store_mod.next_manual_step(record)
    if etape is None:
        raise service.ServiceError("aucune intervention manuelle en attente.")
    actuel = record.get("etat", "")
    if store_mod.ETAT_ATTENTE_RETOURNEMENT not in store_mod.allowed_transitions(actuel) \
            and actuel != store_mod.ETAT_ATTENTE_RETOURNEMENT:
        raise service.ServiceError(
            f"transition refusée : {actuel} → {store_mod.ETAT_ATTENTE_RETOURNEMENT}.")
    record["etat"] = store_mod.ETAT_ATTENTE_RETOURNEMENT
    app.store.log(record, "arret_intervention_manuelle",
                  f"arrêt après la page {etape['apres_page']} : {etape['type']}")
    app.store.save_order(record)
    return {"commande": store_mod.operator_view(record), "etape_en_attente": etape}


def route_confirmer_retournement(app: App, order_id: str, payload: dict) -> dict:
    """Seule sortie d'une attente de retournement : une confirmation humaine."""
    record = app.store.get_order(order_id)
    if record.get("etat") != store_mod.ETAT_ATTENTE_RETOURNEMENT:
        raise service.ServiceError(
            "aucune intervention manuelle n'est en attente de confirmation "
            f"(état actuel : {record.get('etat')}).")
    etape = store_mod.next_manual_step(record)
    if etape is None:
        raise service.ServiceError("toutes les interventions manuelles sont confirmées.")
    index = payload.get("index")
    if index is not None and index != etape["index"]:
        raise service.ServiceError(
            f"les interventions se confirment dans l'ordre : l'étape {etape['index']} "
            f"(après la page {etape['apres_page']}) attend toujours.")
    if payload.get("alignement_controle") is not True:
        raise service.ServiceError(
            "confirmation refusée : indiquez explicitement que la feuille est "
            "retournée, recalée et son alignement vérifié. Rien ne reprend seul.")

    etape["confirme"] = True
    etape["confirme_le"] = store_mod.now()
    etape["confirme_par"] = "opérateur (confirmation humaine explicite)"
    reste = [s for s in record.get("etapes_manuelles", []) if not s.get("confirme")]
    record["etat"] = store_mod.ETAT_EN_COURS if reste else store_mod.ETAT_TERMINEE
    app.store.log(record, "retournement_confirme",
                  f"intervention {etape['index']} ({etape['type']}) confirmée "
                  f"après la page {etape['apres_page']}")
    app.store.save_order(record)
    return {
        "commande": store_mod.operator_view(record),
        "etape_confirmee": etape,
        "reste": len(reste),
        "message": ("reprise autorisée : simulation uniquement, aucune machine n'est "
                    "pilotée." if reste else
                    "dernière intervention confirmée : simulation terminée."),
    }


# --- répartiteur -------------------------------------------------------------


def handle(app: App, handler: BaseHTTPRequestHandler) -> None:
    method = handler.command
    path = handler.path.split("?", 1)[0]
    operateur = path.startswith("/api/operateur/")

    try:
        app.check_host(handler.headers)
        if method in ("POST", "DELETE"):
            app.check_mutation(handler.headers)
        if operateur:
            app.check_operator(handler.headers)

        if method in ("GET", "HEAD"):
            if path in STATIC_FILES:
                name, content_type = STATIC_FILES[path]
                _send(handler, 200, (STATIC_DIR / name).read_bytes(), content_type)
                return
            if path == "/api/config":
                _json_response(handler, 200, route_config(app))
                return
            if path == "/api/operateur/config":
                _json_response(handler, 200, route_operateur_config(app))
                return
            if path == "/api/operateur/commandes":
                _json_response(handler, 200, {
                    "commandes": [store_mod.operator_view(r)
                                  for r in app.store.list_orders()]})
                return
            match = _OPERATOR_ORDER_PATH.match(path)
            if match:
                order_id, suffix = match.group(1), match.group(2)
                if suffix == "/dossier.zip":
                    content, filename = route_dossier(app, order_id, "operateur")
                    _send(handler, 200, content, "application/zip",
                          {"Content-Disposition": f'attachment; filename="{filename}"'})
                    return
                if suffix is None:
                    _json_response(handler, 200, {
                        "commande": store_mod.operator_view(app.store.get_order(order_id))})
                    return
            match = _ORDER_PATH.match(path)
            if match:
                order_id, suffix = match.group(1), match.group(2)
                if suffix == "/dossier.zip":
                    content, filename = route_dossier(app, order_id, "client")
                    _send(handler, 200, content, "application/zip",
                          {"Content-Disposition": f'attachment; filename="{filename}"'})
                    return
                if suffix is None:
                    _json_response(handler, 200, {
                        "commande": store_mod.client_view(app.store.get_order(order_id))})
                    return
            raise Refus(404, f"route inconnue : {path}")

        if method == "POST":
            if path == "/api/composer":
                _json_response(handler, 200, route_composer(_read_json(handler)))
                return
            if path == "/api/apercu":
                _json_response(handler, 200, route_apercu(_read_json(handler)))
                return
            if path == "/api/simulation":
                _json_response(handler, 200, route_simulation(_read_json(handler)))
                return
            if path == "/api/machine":
                _json_response(handler, 403, route_machine_refus(_read_json(handler)))
                return
            if path == "/api/echantillon":
                _json_response(handler, 200, route_echantillon(app, handler))
                return
            if path == "/api/commande":
                _json_response(handler, 201, route_creer_commande(app, _read_json(handler)))
                return
            if path == "/api/operateur/composer":
                _json_response(handler, 200,
                               route_operateur_composer(_read_json(handler)))
                return
            if path == "/api/operateur/simulation":
                _json_response(handler, 200,
                               route_operateur_simulation(_read_json(handler)))
                return
            if path == "/api/operateur/machine":
                _json_response(handler, 403, route_operateur_machine(_read_json(handler)))
                return
            match = _OPERATOR_ORDER_PATH.match(path)
            if match:
                order_id, suffix = match.group(1), match.group(2)
                payload = _read_json(handler)
                if suffix == "/etat":
                    _json_response(handler, 200, route_etat(app, order_id, payload))
                    return
                if suffix == "/attente":
                    _json_response(handler, 200,
                                   route_attente_retournement(app, order_id, payload))
                    return
                if suffix == "/retournement":
                    _json_response(handler, 200,
                                   route_confirmer_retournement(app, order_id, payload))
                    return
            raise Refus(404, f"route inconnue : {path}")

        if method == "DELETE":
            match = _OPERATOR_ORDER_PATH.match(path)
            if match and match.group(2) is None:
                _json_response(handler, 200, app.store.delete_order(match.group(1)))
                return
            match = _ORDER_PATH.match(path)
            if match and match.group(2) is None:
                _json_response(handler, 200, app.store.delete_order(match.group(1)))
                return
            raise Refus(404, f"route inconnue : {path}")

        raise Refus(405, f"méthode non autorisée : {method}")

    except Refus as refus:
        _json_response(handler, refus.status,
                       {"erreur": refus.message, "detail": refus.detail})
    except StoreError as exc:
        _json_response(handler, 404, {"erreur": str(exc)})
    except PaperxError as exc:
        _json_response(handler, 400, {"erreur": str(exc), "type": type(exc).__name__})
    except FileNotFoundError as exc:
        _json_response(handler, 404, {"erreur": f"fichier absent : {exc}"})
