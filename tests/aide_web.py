"""Utilitaires partagés des tests du site local.

Aucune dépendance externe : serveur lancé dans un thread sur un port libre,
répertoire de données temporaire, images de test fabriquées à la main.
"""

from __future__ import annotations

import json
import struct
import threading
import urllib.error
import urllib.request
import zlib
from pathlib import Path

from paperx_web import server as _server_module
from paperx_web.server import build_server

#: Les tests n'ont pas besoin du journal d'accès du serveur.
_server_module.Handler.log_message = lambda *args, **kwargs: None


# --- images de test ----------------------------------------------------------


def _chunk(kind: bytes, payload: bytes) -> bytes:
    corps = kind + payload
    return (struct.pack(">I", len(payload)) + corps
            + struct.pack(">I", zlib.crc32(corps) & 0xFFFFFFFF))


def png(width: int, height: int, declared: tuple[int, int] | None = None) -> bytes:
    """PNG RVB 8 bits. `declared` permet de FABRIQUER un en-tête menteur."""
    lignes = bytearray()
    for y in range(height):
        lignes.append(0)                      # filtre « none »
        for x in range(width):
            lignes += bytes(((x * 7) % 256, (y * 3) % 256, 128))
    dw, dh = declared or (width, height)
    return (b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", struct.pack(">IIBBBBB", dw, dh, 8, 2, 0, 0, 0))
            + _chunk(b"IDAT", zlib.compress(bytes(lignes)))
            + _chunk(b"IEND", b""))


def multipart(champs: dict[str, str], nom_fichier: str | None = None,
              contenu: bytes = b"") -> tuple[bytes, str]:
    limite = "----paperxtest0123456789"
    morceaux: list[bytes] = []
    for nom, valeur in champs.items():
        morceaux.append(
            f"--{limite}\r\nContent-Disposition: form-data; name=\"{nom}\"\r\n\r\n"
            f"{valeur}\r\n".encode("utf-8"))
    if nom_fichier is not None:
        morceaux.append(
            f"--{limite}\r\nContent-Disposition: form-data; name=\"echantillon\"; "
            f"filename=\"{nom_fichier}\"\r\nContent-Type: application/octet-stream\r\n\r\n"
            .encode("utf-8") + contenu + b"\r\n")
    morceaux.append(f"--{limite}--\r\n".encode("utf-8"))
    return b"".join(morceaux), f"multipart/form-data; boundary={limite}"


# --- serveur de test ---------------------------------------------------------


class ServeurLocal:
    """Serveur paperx_web lancé sur un port libre, données dans un dossier jetable."""

    def __init__(self, data_dir: Path) -> None:
        self.server = build_server("127.0.0.1", 0, data_dir)
        self.port = self.server.bound_port
        self.base = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.jeton = self.get("/api/config")[1]["jeton"]
        self.cle = self.server.app.operator_key

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    # --- requêtes ----------------------------------------------------------

    def _appel(self, methode: str, chemin: str, corps: bytes | None,
               content_type: str | None, *, jeton: bool, operateur: bool,
               entetes: dict[str, str] | None = None, host: str | None = None):
        requete = urllib.request.Request(self.base + chemin, data=corps, method=methode)
        requete.add_header("Host", host or f"127.0.0.1:{self.port}")
        if content_type:
            requete.add_header("Content-Type", content_type)
        if jeton:
            requete.add_header("X-Paperx-Jeton", self.jeton)
        if operateur:
            requete.add_header("X-Paperx-Operateur", self.cle)
        for nom, valeur in (entetes or {}).items():
            requete.add_header(nom, valeur)
        try:
            with urllib.request.urlopen(requete) as reponse:
                return reponse.status, reponse.read(), reponse.headers
        except urllib.error.HTTPError as erreur:
            return erreur.code, erreur.read(), erreur.headers

    def get(self, chemin: str, *, operateur: bool = False, host: str | None = None):
        statut, corps, entetes = self._appel("GET", chemin, None, None,
                                             jeton=False, operateur=operateur, host=host)
        return statut, self._decoder(corps, entetes)

    def get_brut(self, chemin: str, *, operateur: bool = False):
        statut, corps, entetes = self._appel("GET", chemin, None, None,
                                             jeton=False, operateur=operateur)
        return statut, corps, entetes

    def post(self, chemin: str, payload: dict, *, jeton: bool = True,
             operateur: bool = False, entetes: dict[str, str] | None = None,
             host: str | None = None):
        corps = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        statut, brut, entetes_reponse = self._appel(
            "POST", chemin, corps, "application/json", jeton=jeton,
            operateur=operateur, entetes=entetes, host=host)
        return statut, self._decoder(brut, entetes_reponse)

    def post_multipart(self, chemin: str, champs: dict[str, str],
                       nom_fichier: str | None, contenu: bytes,
                       *, jeton: bool = True):
        corps, content_type = multipart(champs, nom_fichier, contenu)
        statut, brut, entetes = self._appel("POST", chemin, corps, content_type,
                                            jeton=jeton, operateur=False)
        return statut, self._decoder(brut, entetes)

    def delete(self, chemin: str, *, jeton: bool = True, operateur: bool = False):
        statut, brut, entetes = self._appel("DELETE", chemin, None, None,
                                            jeton=jeton, operateur=operateur)
        return statut, self._decoder(brut, entetes)

    @staticmethod
    def _decoder(corps: bytes, entetes) -> object:
        if "application/json" in (entetes.get("Content-Type") or ""):
            return json.loads(corps.decode("utf-8"))
        return corps


TEXTE_FR = (
    "Chère Anaïs,\n\n"
    "Le libraire dit « au bout de la rue, à gauche » — et c'était vrai.\n"
    "Cœur, æil, 18 °C, 5 %, 3/4… tout doit ressortir à l'identique.\n"
    "Deux  espaces, une espace insécable : intactes elles aussi.\n"
)
