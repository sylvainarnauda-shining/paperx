"""Stockage LOCAL : commandes, échantillons privés, artefacts figés.

Tout vit hors du dépôt de code, dans un répertoire de données dédié
(`~/.paperx-web` par défaut, ou `$PAPERX_WEB_DATA`). Aucun texte client, aucune
photo n'entre jamais dans le dépôt : le code ne sait pas écrire à l'intérieur.

Trois garanties tenues ici :

1. **Les métadonnées d'un échantillon sont celles du serveur.** Elles sont
   écrites au moment du dépôt et relues depuis le disque ; ce qu'un client
   annonce n'est jamais repris tel quel. Un identifiant sans fichier est refusé,
   et l'empreinte est recalculée à la relecture.
2. **Les artefacts d'une commande sont figés à sa création.** Le dossier remis
   est celui qui a été calculé au moment du devis : changer un profil plus tard
   ne réécrit pas rétroactivement une commande passée.
3. **Les transitions d'état sont déterministes.** Une attente de retournement ne
   se contourne pas en passant par un autre état : la table ci-dessous est la
   seule autorité.

Les fichiers sont créés en 0600 et écrits de façon atomique. Supprimer une
commande efface aussi son échantillon et ses artefacts.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import uploads

STORE_VERSION = "2.0.0"

ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")

#: Un dépôt jamais rattaché à une commande est effacé passé ce délai.
ORPHAN_TTL_SECONDS = 30 * 60

# --- États du parcours opérateur --------------------------------------------
ETAT_RECUE = "RECUE"
ETAT_ATTENTE_PERSONNALISATION = "EN_ATTENTE_PERSONNALISATION"
ETAT_PRETE_REVUE = "PRETE_POUR_REVUE"
ETAT_EN_COURS = "SIMULATION_EN_COURS"
ETAT_ATTENTE_RETOURNEMENT = "EN_ATTENTE_RETOURNEMENT_MANUEL"
ETAT_TERMINEE = "SIMULATION_TERMINEE"
ETAT_ANNULEE = "ANNULEE"

ETATS = (ETAT_RECUE, ETAT_ATTENTE_PERSONNALISATION, ETAT_PRETE_REVUE, ETAT_EN_COURS,
         ETAT_ATTENTE_RETOURNEMENT, ETAT_TERMINEE, ETAT_ANNULEE)

ETAT_LABELS = {
    ETAT_RECUE: "reçue",
    ETAT_ATTENTE_PERSONNALISATION: "en attente de personnalisation (aucun fournisseur)",
    ETAT_PRETE_REVUE: "prête pour revue",
    ETAT_EN_COURS: "simulation en cours",
    ETAT_ATTENTE_RETOURNEMENT: "arrêt — retournement manuel à confirmer",
    ETAT_TERMINEE: "simulation terminée",
    ETAT_ANNULEE: "annulée",
}

#: Suivi montré au client : sans jargon, sans code interne.
ETAT_CLIENT = {
    ETAT_RECUE: "Commande reçue",
    ETAT_ATTENTE_PERSONNALISATION: "En attente — votre écriture n'est pas encore reproductible",
    ETAT_PRETE_REVUE: "Prête à être relue",
    ETAT_EN_COURS: "Simulation en cours",
    ETAT_ATTENTE_RETOURNEMENT: "En pause — retournement de la feuille à faire à la main",
    ETAT_TERMINEE: "Simulation terminée",
    ETAT_ANNULEE: "Annulée",
}

#: Transitions autorisées par `POST /etat`. Tout le reste est refusé.
#: Sortir d'une attente de retournement passe UNIQUEMENT par la confirmation
#: humaine (`POST /retournement`) : aucun chemin détourné n'existe.
TRANSITIONS: dict[str, frozenset[str]] = {
    ETAT_RECUE: frozenset({ETAT_PRETE_REVUE, ETAT_ATTENTE_PERSONNALISATION, ETAT_ANNULEE}),
    ETAT_ATTENTE_PERSONNALISATION: frozenset({ETAT_ANNULEE}),
    ETAT_PRETE_REVUE: frozenset({ETAT_EN_COURS, ETAT_ANNULEE}),
    ETAT_EN_COURS: frozenset({ETAT_ATTENTE_RETOURNEMENT, ETAT_TERMINEE, ETAT_ANNULEE}),
    ETAT_ATTENTE_RETOURNEMENT: frozenset({ETAT_ANNULEE}),
    ETAT_TERMINEE: frozenset({ETAT_ANNULEE}),
    ETAT_ANNULEE: frozenset(),
}


class StoreError(Exception):
    """Identifiant invalide, commande absente, transition refusée."""


def default_root() -> Path:
    override = os.environ.get("PAPERX_WEB_DATA")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".paperx-web"


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _age_seconds(horodatage: str) -> float:
    try:
        instant = datetime.fromisoformat(horodatage)
    except (TypeError, ValueError):
        return float("inf")
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - instant).total_seconds()


def new_id() -> str:
    return secrets.token_hex(16)


def valid_id(value: object) -> bool:
    return isinstance(value, str) and bool(ID_PATTERN.fullmatch(value))


def allowed_transitions(etat: str) -> frozenset[str]:
    return TRANSITIONS.get(etat, frozenset())


class Store:
    """File opérateur minimale, persistante, entièrement locale."""

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root is not None else default_root()
        self.orders_dir = self.root / "commandes"
        self.samples_dir = self.root / "echantillons"
        self.artifacts_dir = self.root / "dossiers"
        for directory in (self.root, self.orders_dir, self.samples_dir, self.artifacts_dir):
            directory.mkdir(parents=True, exist_ok=True)
            try:
                directory.chmod(0o700)
            except OSError:              # système de fichiers sans permissions POSIX
                pass

    # --- chemins sûrs ------------------------------------------------------

    def _order_path(self, order_id: str) -> Path:
        return self._safe(self.orders_dir, order_id, ".json", "commande")

    def _sample_meta_path(self, sample_id: str) -> Path:
        return self._safe(self.samples_dir, sample_id, ".json", "échantillon")

    def _artifact_path(self, order_id: str, variante: str) -> Path:
        if variante not in ("client", "operateur"):
            raise StoreError(f"variante de dossier inconnue : {variante!r}")
        return self._safe(self.artifacts_dir, order_id, f"-{variante}.zip", "dossier")

    def _safe(self, directory: Path, identifier: str, suffix: str, quoi: str) -> Path:
        if not valid_id(identifier):
            raise StoreError(f"identifiant de {quoi} invalide : {identifier!r}")
        path = (directory / f"{identifier}{suffix}").resolve()
        if path.parent != directory.resolve():
            raise StoreError(f"chemin de {quoi} hors du répertoire de données")
        return path

    def sample_path(self, storage_name: str) -> Path:
        if not uploads._SAFE_NAME.fullmatch(storage_name):
            raise StoreError(f"nom d'échantillon refusé : {storage_name!r}")
        path = (self.samples_dir / storage_name).resolve()
        if path.parent != self.samples_dir.resolve():
            raise StoreError("chemin d'échantillon hors du répertoire de données")
        return path

    # --- écriture atomique -------------------------------------------------

    @staticmethod
    def _write(path: Path, data: bytes) -> None:
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            os.chmod(tmp, 0o600)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    @staticmethod
    def _dump(record: dict) -> bytes:
        return (json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2,
                           allow_nan=False) + "\n").encode("utf-8")

    # --- échantillons ------------------------------------------------------

    def save_sample(self, data: bytes, verdict: uploads.UploadCheck,
                    consent_ref: str) -> dict:
        """Enregistre un échantillon accepté ET ses métadonnées serveur."""
        if not verdict.accepted or verdict.kind is None:
            raise StoreError("échantillon refusé : rien n'est enregistré")
        sample_id = new_id()
        name = uploads.storage_name(sample_id, verdict.kind)
        self._write(self.sample_path(name), data)
        meta = {
            "id": sample_id,
            "nom_stockage": name,
            "type": verdict.kind,
            "sha256": verdict.sha256,
            "octets": verdict.byte_length,
            "largeur_px": verdict.width,
            "hauteur_px": verdict.height,
            "consentement": True,
            "reference_consentement": consent_ref,
            "depose_le": now(),
            "commande": None,
        }
        self._write(self._sample_meta_path(sample_id), self._dump(meta))
        return meta

    def get_sample(self, sample_id: str) -> dict:
        """Métadonnées SERVEUR d'un échantillon, avec vérification du fichier.

        Rien de ce que le client annonce n'est repris : l'existence du fichier
        et son empreinte sont revérifiées ici.
        """
        path = self._sample_meta_path(sample_id)
        if not path.exists():
            raise StoreError(f"échantillon inconnu : {sample_id}")
        meta = json.loads(path.read_text(encoding="utf-8"))
        fichier = self.sample_path(meta["nom_stockage"])
        if not fichier.exists():
            raise StoreError(f"échantillon absent du disque : {sample_id}")
        empreinte = hashlib.sha256(fichier.read_bytes()).hexdigest()
        if empreinte != meta.get("sha256"):
            raise StoreError(
                f"échantillon {sample_id} : empreinte différente de celle enregistrée")
        return meta

    def attach_sample(self, sample_id: str, order_id: str) -> dict:
        meta = self.get_sample(sample_id)
        if meta.get("commande") not in (None, order_id):
            raise StoreError("échantillon déjà rattaché à une autre commande")
        meta["commande"] = order_id
        self._write(self._sample_meta_path(sample_id), self._dump(meta))
        return meta

    def delete_sample(self, sample_id: str) -> bool:
        try:
            meta_path = self._sample_meta_path(sample_id)
        except StoreError:
            return False
        supprime = False
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            fichier = self.sample_path(meta["nom_stockage"])
            if fichier.exists():
                fichier.unlink()
                supprime = True
            meta_path.unlink()
        return supprime

    def purge_orphan_samples(self, ttl_seconds: int = ORPHAN_TTL_SECONDS) -> list[str]:
        """Efface les dépôts jamais rattachés à une commande, passé leur délai."""
        purges: list[str] = []
        for meta_path in self.samples_dir.glob("*.json"):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if meta.get("commande") is not None:
                continue
            if _age_seconds(meta.get("depose_le", "")) < ttl_seconds:
                continue
            if self.delete_sample(meta.get("id", "")):
                purges.append(meta.get("id", ""))
        return purges

    # --- artefacts figés ---------------------------------------------------

    def save_artifact(self, order_id: str, variante: str, content: bytes) -> dict:
        path = self._artifact_path(order_id, variante)
        self._write(path, content)
        return {"variante": variante, "octets": len(content),
                "sha256": hashlib.sha256(content).hexdigest()}

    def read_artifact(self, order_id: str, variante: str, expected_sha: str) -> bytes:
        """Relit un dossier figé et refuse toute divergence d'empreinte."""
        path = self._artifact_path(order_id, variante)
        if not path.exists():
            raise StoreError(f"dossier {variante} absent pour la commande {order_id}")
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != expected_sha:
            raise StoreError(
                f"dossier {variante} de la commande {order_id} : empreinte différente "
                "de celle enregistrée à la création. Il n'est pas servi.")
        return content

    # --- commandes ---------------------------------------------------------

    def create_order(self, record: dict) -> dict:
        order_id = new_id()
        record = dict(record)
        record["id"] = order_id
        record["version_store"] = STORE_VERSION
        record["cree_le"] = now()
        record["journal"] = [{"horodatage": now(), "evenement": "commande_creee",
                              "detail": "commande enregistrée en local, artefacts figés"}]
        self._write(self._order_path(order_id), self._dump(record))
        return record

    def get_order(self, order_id: str) -> dict:
        path = self._order_path(order_id)
        if not path.exists():
            raise StoreError(f"commande inconnue : {order_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def save_order(self, record: dict) -> dict:
        self._write(self._order_path(record["id"]), self._dump(record))
        return record

    def list_orders(self) -> list[dict]:
        out: list[dict] = []
        for path in self.orders_dir.glob("*.json"):
            try:
                out.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        out.sort(key=lambda r: (r.get("cree_le", ""), r.get("id", "")), reverse=True)
        return out

    def delete_order(self, order_id: str) -> dict:
        """Efface la commande, son échantillon et ses dossiers figés."""
        record = self.get_order(order_id)
        sample = record.get("echantillon") or {}
        deleted_sample = bool(sample.get("id")) and self.delete_sample(sample["id"])
        dossiers = 0
        for variante in ("client", "operateur"):
            path = self._artifact_path(order_id, variante)
            if path.exists():
                path.unlink()
                dossiers += 1
        self._order_path(order_id).unlink(missing_ok=True)
        return {
            "id": order_id,
            "commande_supprimee": True,
            "echantillon_supprime": deleted_sample,
            "dossiers_supprimes": dossiers,
            "note": "texte, options, photo et dossiers effacés du disque local ; "
                    "aucune copie conservée",
        }

    def log(self, record: dict, event: str, detail: str) -> dict:
        record.setdefault("journal", []).append(
            {"horodatage": now(), "evenement": event, "detail": detail})
        return record


# --- vues --------------------------------------------------------------------


def next_manual_step(record: dict) -> dict | None:
    return next((s for s in record.get("etapes_manuelles", []) if not s.get("confirme")), None)


def client_view(record: dict) -> dict:
    """Ce que voit la personne qui commande : suivi, pages, prix. Rien d'interne.

    Ni temps de tracé, ni temps de manipulation, ni coûts d'atelier, ni codes du
    validateur, ni profils : ces informations appartiennent à l'espace opérateur.
    """
    etat = record.get("etat", "")
    etape = next_manual_step(record)
    devis = record.get("devis_client") or {}
    return {
        "id": record.get("id"),
        "cree_le": record.get("cree_le"),
        "suivi": ETAT_CLIENT.get(etat, etat),
        "etat": etat,
        "en_pause": etat == ETAT_ATTENTE_RETOURNEMENT,
        "mode_ecriture": record.get("mode_ecriture"),
        "mode_impression": record.get("mode_impression"),
        "pages": record.get("faces"),
        "feuilles": record.get("feuilles"),
        "caracteres": record.get("caracteres"),
        "photo_conservee": bool(record.get("echantillon")),
        "personnalisation_disponible": False,
        "devis": devis,
        "etapes_a_la_main_total": len(record.get("etapes_manuelles", [])),
        "etapes_a_la_main_faites": sum(
            1 for s in record.get("etapes_manuelles", []) if s.get("confirme")),
        "en_attente_de": (
            f"retournement de la feuille {etape['feuille']}"
            if etape and etat == ETAT_ATTENTE_RETOURNEMENT else None),
    }


def operator_view(record: dict) -> dict:
    """Vue opérateur : tout, y compris les coûts internes et les codes techniques."""
    etat = record.get("etat", "")
    etape = next_manual_step(record)
    return {
        **client_view(record),
        "etat_libelle": ETAT_LABELS.get(etat, etat),
        "transitions_autorisees": sorted(allowed_transitions(etat)),
        "style": record.get("style"),
        "texte_sha256": record.get("texte_sha256"),
        "profils_figes": record.get("profils_figes"),
        "devis_operateur": record.get("devis_operateur"),
        "couts_operateur": record.get("couts_operateur"),
        "simulation": record.get("simulation"),
        "validation": record.get("validation"),
        "production": record.get("production"),
        "echantillon": record.get("echantillon"),
        "personnalisation": record.get("personnalisation"),
        "etapes_manuelles": record.get("etapes_manuelles", []),
        "etape_en_attente": etape,
        "confirmation_possible": bool(etape) and etat == ETAT_ATTENTE_RETOURNEMENT,
        "dossiers": record.get("dossiers"),
        "journal": record.get("journal", []),
    }
