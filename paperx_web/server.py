"""Serveur local paperx.

    python3 -m paperx_web            # http://127.0.0.1:8080

Le serveur REFUSE de s'attacher à une adresse qui n'est pas la boucle locale :
ce site n'est pas fait pour être exposé sur un réseau, et rien dans ce dépôt ne
permet de le déployer publiquement.
"""

from __future__ import annotations

import argparse
import ipaddress
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import PAPERX_WEB_VERSION, http_app
from .store import Store, default_root

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8080


def is_loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host in ("localhost", "localhost.localdomain")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = f"paperx-local/{PAPERX_WEB_VERSION}"
    sys_version = ""            # aucune version Python annoncée

    @property
    def app(self) -> http_app.App:
        return self.server.app          # type: ignore[attr-defined]

    def do_GET(self) -> None:           # noqa: N802 - API de BaseHTTPRequestHandler
        http_app.handle(self.app, self)

    def do_HEAD(self) -> None:          # noqa: N802
        http_app.handle(self.app, self)

    def do_POST(self) -> None:          # noqa: N802
        http_app.handle(self.app, self)

    def do_DELETE(self) -> None:        # noqa: N802
        http_app.handle(self.app, self)

    def log_message(self, fmt: str, *args) -> None:
        """Journal minimal. Ni contenu client, ni chaîne de requête (elle pourrait
        porter une clé) : seuls la méthode, le chemin et le code sont écrits."""
        ligne = (fmt % args).replace("\n", " ")
        ligne = re.sub(r"(\s\S+?)\?\S*", r"\1", ligne)
        sys.stderr.write("%s - %s\n" % (self.address_string(), ligne))


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, host: str, port: int, store: Store) -> None:
        if not is_loopback(host):
            raise SystemExit(
                f"paperx_web : refus de servir sur {host!r}. Ce site est local : "
                "seule la boucle locale (127.0.0.1, ::1, localhost) est autorisée.")
        super().__init__((host, port), Handler)
        bound_host, bound_port = self.server_address[:2]
        self.app = http_app.App(store, host, bound_port)
        self.bound_port = bound_port


def build_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
                 data_dir: str | Path | None = None) -> LocalServer:
    return LocalServer(host, port, Store(data_dir))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="paperx_web", description=__doc__)
    parser.add_argument("--host", default=DEFAULT_HOST,
                        help="adresse d'écoute (boucle locale uniquement)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--data", default=None,
                        help=f"répertoire de données local (défaut : {default_root()})")
    args = parser.parse_args(argv)

    try:
        server = build_server(args.host, args.port, args.data)
    except OSError as exc:
        print(f"paperx_web : impossible d'écouter sur {args.host}:{args.port} — {exc}",
              file=sys.stderr)
        return 2

    purges = server.app.store.purge_orphan_samples()
    base = f"http://{args.host}:{server.bound_port}"
    print(f"paperx — site local")
    print(f"  espace client    : {base}/")
    print(f"  espace opérateur : {base}/operateur")
    print(f"  clé opérateur    : {server.app.operator_key}")
    print("     (elle n'est servie par aucune page : recopiez-la depuis ce terminal)")
    print(f"  données locales  : {server.app.store.root}")
    if purges:
        print(f"  {len(purges)} dépôt(s) abandonné(s) effacé(s) au démarrage.")
    print("  aucun accès imprimante, aucun G-code, aucun paiement, aucun service distant.")
    print("  Ctrl+C pour arrêter.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\narrêt demandé.")
    finally:
        server.server_close()
    return 0
