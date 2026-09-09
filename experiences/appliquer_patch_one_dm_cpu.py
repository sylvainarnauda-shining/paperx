#!/usr/bin/env python3
"""Applique le correctif de démarrage mono-processus à un clone One-DM.

Le correctif ne vaut que pour **une** version précise du dépôt amont. Cet
applicateur refuse tout le reste, et n'écrit rien tant que chaque vérification
n'est pas passée :

  1. le chemin est bien un dépôt git ;
  2. son HEAD est exactement le commit ciblé ;
  3. le clone est propre — aucun fichier modifié, aucun fichier non suivi ;
  4. le blob du fichier visé correspond à celui attendu ;
  5. l'en-tête du correctif désigne bien ce commit et ce blob ;
  6. `git apply --check` réussit.

Sans `--appliquer`, rien n'est écrit : seules les vérifications tournent.

Ce programme n'ouvre aucune connexion réseau, ne télécharge aucun poids,
n'importe ni n'exécute le code amont, et ne pilote aucune machine. Les seules
commandes lancées sont des commandes `git` locales.

    python3 experiences/appliquer_patch_one_dm_cpu.py --clone <chemin>
    python3 experiences/appliquer_patch_one_dm_cpu.py --clone <chemin> --appliquer

Codes de retour : 0 vérifications (et application) réussies, 1 refus motivé,
2 erreur inattendue.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

#: Version amont ciblée. Aucune autre n'est acceptée.
COMMIT_ATTENDU = "dde2205a70a2c70d1786503d198a795358c80ee4"
FICHIER_VISE = "test.py"
BLOB_ATTENDU = "cde1922c4362f20ec096cd0233e122c332dcc281"
PATCH_PAR_DEFAUT = Path(__file__).resolve().parent / "one-dm-cpu-monoprocessus.patch"

#: Marqueur que le fichier corrigé doit contenir après application.
MARQUEUR = "paperx_setup_distributed"


class Refus(Exception):
    """Une vérification a échoué : rien n'est écrit."""


def git(clone: Path, *args: str, check: bool = True) -> str:
    resultat = subprocess.run(["git", "-C", str(clone), *args],
                              capture_output=True, text=True, timeout=120)
    if check and resultat.returncode != 0:
        raise Refus(f"git {' '.join(args)} a échoué : "
                    f"{(resultat.stderr or resultat.stdout).strip()[:200]}")
    return resultat.stdout


def verifier(clone: Path, patch: Path) -> list[str]:
    """Toutes les vérifications préalables. Lève `Refus` au premier problème."""
    lignes: list[str] = []

    if not clone.is_dir():
        raise Refus(f"{clone} n'est pas un dossier")
    if not patch.is_file():
        raise Refus(f"correctif introuvable : {patch}")

    racine = git(clone, "rev-parse", "--show-toplevel").strip()
    if Path(racine).resolve() != clone.resolve():
        raise Refus(f"{clone} n'est pas la racine d'un dépôt git (racine : {racine})")
    lignes.append(f"dépôt git      : {racine}")

    tete = git(clone, "rev-parse", "HEAD").strip()
    if tete != COMMIT_ATTENDU:
        raise Refus(
            f"version amont différente. HEAD = {tete}, attendu = {COMMIT_ATTENDU}. "
            "Ce correctif ne vaut que pour ce commit ; rien n'a été modifié.")
    lignes.append(f"commit         : {tete} (conforme)")

    sale = git(clone, "status", "--porcelain").strip()
    if sale:
        premieres = "; ".join(sale.splitlines()[:5])
        raise Refus(
            "le clone n'est pas propre — aucune modification silencieuse ne sera "
            f"faite dessus. Entrées : {premieres}")
    lignes.append("état du clone  : propre")

    blob = git(clone, "rev-parse", f"HEAD:{FICHIER_VISE}").strip()
    if blob != BLOB_ATTENDU:
        raise Refus(f"blob de {FICHIER_VISE} = {blob}, attendu = {BLOB_ATTENDU}")
    lignes.append(f"{FICHIER_VISE:14s} : blob {blob} (conforme)")

    entete = patch.read_text(encoding="utf-8")
    for attendu in (COMMIT_ATTENDU, BLOB_ATTENDU):
        if attendu not in entete:
            raise Refus(f"l'en-tête du correctif ne mentionne pas {attendu}")
    lignes.append(f"correctif      : {patch.name} (en-tête cohérent)")

    git(clone, "apply", "--check", str(patch.resolve()))
    lignes.append("git apply --check : applicable")
    return lignes


def appliquer(clone: Path, patch: Path) -> list[str]:
    """Applique le correctif, puis contrôle la syntaxe SANS importer le module."""
    lignes: list[str] = []
    git(clone, "apply", str(patch.resolve()))
    lignes.append("correctif appliqué")

    cible = clone / FICHIER_VISE
    source = cible.read_text(encoding="utf-8")
    if MARQUEUR not in source:
        raise Refus(f"{FICHIER_VISE} ne contient pas {MARQUEUR} après application")
    try:
        # compile() analyse et compile en mémoire : aucun import, aucune
        # exécution du code amont, aucun fichier .pyc écrit.
        compile(source, str(cible), "exec")
    except SyntaxError as exc:
        raise Refus(f"le fichier corrigé n'est pas syntaxiquement valide : {exc}") from exc
    lignes.append("compilation syntaxique : réussie (aucun import, aucune exécution)")
    lignes.append(f"retour arrière : git -C {clone} checkout -- {FICHIER_VISE}")
    return lignes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Applique le correctif de démarrage mono-processus à un clone One-DM.")
    parser.add_argument("--clone", required=True, help="racine du clone One-DM")
    parser.add_argument("--patch", default=str(PATCH_PAR_DEFAUT),
                        help="correctif à appliquer (défaut : %(default)s)")
    parser.add_argument("--appliquer", action="store_true",
                        help="écrire réellement ; sans cette option, rien n'est modifié")
    args = parser.parse_args(argv)

    clone, patch = Path(args.clone), Path(args.patch)
    print("Correctif One-DM — démarrage mono-processus sans NCCL")
    print(f"cible : {COMMIT_ATTENDU}\n")
    try:
        for ligne in verifier(clone, patch):
            print(f"  {ligne}")
        if args.appliquer:
            for ligne in appliquer(clone, patch):
                print(f"  {ligne}")
            print("\nAppliqué. Ceci ne démontre AUCUNE inférence réussie : poids, VAE,")
            print("jeu de données et licences restent à obtenir et à vérifier.")
        else:
            print("\nVérifications seules — rien n'a été écrit. "
                  "Ajoutez --appliquer pour modifier le clone.")
    except Refus as refus:
        print(f"\nREFUS : {refus}", file=sys.stderr)
        return 1
    except Exception as exc:                       # noqa: BLE001
        print(f"\nERREUR inattendue : {type(exc).__name__} — {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
