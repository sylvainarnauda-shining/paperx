#!/usr/bin/env python3
"""Applique le correctif de démarrage mono-processus à un clone One-DM.

Le correctif ne vaut que pour **une** version précise du dépôt amont, et ne doit
toucher qu'**un** fichier. Cet applicateur refuse tout le reste, et n'écrit rien
tant que chaque vérification n'est pas passée :

  1. le chemin est bien la racine d'un dépôt git ;
  2. son HEAD est exactement le commit ciblé ;
  3. le clone est propre — aucun fichier modifié, aucun fichier non suivi ;
  4. le blob du fichier visé correspond à celui attendu ;
  5. l'empreinte SHA-256 du correctif est exactement celle attendue ;
  6. le correctif ne touche que les chemins autorisés, sans création,
     suppression, renommage, changement de mode ni contenu binaire ;
  7. `git apply --check` réussit sur le clone ;
  8. **le résultat est préparé et compilé dans un dossier temporaire**, hors du
     clone : si le fichier corrigé n'est pas syntaxiquement valide, le clone
     n'est jamais touché.

Ce n'est qu'ensuite, et si `--appliquer` est demandé, que le clone est modifié —
puis le résultat est comparé octet pour octet à ce qui a été préparé. Au moindre
écart, le fichier est restauré et l'opération est déclarée en échec.

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
import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

#: Version amont ciblée. Aucune autre n'est acceptée.
COMMIT_ATTENDU = "dde2205a70a2c70d1786503d198a795358c80ee4"
FICHIER_VISE = "test.py"
BLOB_ATTENDU = "cde1922c4362f20ec096cd0233e122c332dcc281"

#: Empreinte du correctif livré. Un correctif modifié, même d'un octet, est refusé.
PATCH_SHA256 = "e9b93f31927e8a8c7ca06cf716e4038c4a7f5d695822594a48d350c62d34c2c8"

#: Seuls chemins qu'un correctif accepté a le droit de toucher.
CHEMINS_AUTORISES = frozenset({FICHIER_VISE})

PATCH_PAR_DEFAUT = Path(__file__).resolve().parent / "one-dm-cpu-monoprocessus.patch"

#: Marqueur que le fichier corrigé doit contenir après application.
MARQUEUR = "paperx_setup_distributed"

#: En-têtes de diff interdits : ce correctif ne fait que modifier du contenu.
ENTETES_INTERDITS = (
    "new file mode", "deleted file mode", "rename from", "rename to",
    "copy from", "copy to", "old mode", "new mode", "similarity index",
    "dissimilarity index", "GIT binary patch", "index ---",
)


class Refus(Exception):
    """Une vérification a échoué : rien n'est écrit."""


def git(cwd: Path, *args: str, check: bool = True) -> str:
    resultat = subprocess.run(["git", "-C", str(cwd), *args],
                              capture_output=True, text=True, timeout=120)
    if check and resultat.returncode != 0:
        raise Refus(f"git {' '.join(args)} a échoué : "
                    f"{(resultat.stderr or resultat.stdout).strip()[:200]}")
    return resultat.stdout


def chemins_du_correctif(texte: str) -> set[str]:
    """Chemins touchés par le correctif, refus si le diff fait autre chose.

    L'analyse ne commence qu'au premier en-tête de diff : le préambule
    documentaire du correctif n'est jamais interprété.
    """
    lignes = texte.splitlines()
    debut = next((i for i, l in enumerate(lignes)
                  if l.startswith("diff --git ") or l.startswith("--- ")), None)
    if debut is None:
        raise Refus("le correctif ne contient aucun en-tête de diff")

    chemins: set[str] = set()
    for ligne in lignes[debut:]:
        for interdit in ENTETES_INTERDITS:
            if ligne.startswith(interdit):
                raise Refus(
                    f"en-tête de diff interdit : « {ligne.strip()[:60]} ». Ce "
                    "correctif ne doit que modifier du contenu existant.")
        if ligne.startswith("--- ") or ligne.startswith("+++ "):
            brut = ligne[4:].split("\t")[0].strip()
            if brut == "/dev/null":
                raise Refus("le correctif crée ou supprime un fichier : refusé")
            if brut.startswith(("a/", "b/")):
                brut = brut[2:]
            chemins.add(brut)

    inattendus = sorted(chemins - CHEMINS_AUTORISES)
    if inattendus:
        raise Refus(
            f"le correctif touche des chemins non autorisés : {', '.join(inattendus)}. "
            f"Seul {', '.join(sorted(CHEMINS_AUTORISES))} peut l'être ; rien n'a été modifié.")
    if not chemins:
        raise Refus("le correctif ne désigne aucun fichier")
    return chemins


def preparer(clone: Path, patch: Path, chemins: set[str]) -> dict[str, str]:
    """Applique le correctif dans un dossier temporaire et compile le résultat.

    Le clone n'est pas touché. Renvoie le contenu préparé, par chemin.
    """
    prepare: dict[str, str] = {}
    with tempfile.TemporaryDirectory(prefix="paperx-preparation-") as tmp:
        bac = Path(tmp)
        for relatif in sorted(chemins):
            source = clone / relatif
            if not source.is_file():
                raise Refus(f"{relatif} est absent du clone")
            destination = bac / relatif
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

        resultat = subprocess.run(["git", "apply", str(patch.resolve())],
                                  cwd=bac, capture_output=True, text=True, timeout=120)
        if resultat.returncode != 0:
            raise Refus("le correctif ne s'applique pas en préparation : "
                        f"{(resultat.stderr or resultat.stdout).strip()[:200]}")

        apparus = [str(p.relative_to(bac)) for p in bac.rglob("*") if p.is_file()]
        surplus = sorted(set(apparus) - chemins)
        if surplus:
            raise Refus(f"la préparation a produit des fichiers imprévus : {', '.join(surplus)}")

        for relatif in sorted(chemins):
            contenu = (bac / relatif).read_text(encoding="utf-8")
            if MARQUEUR not in contenu:
                raise Refus(f"{relatif} ne contient pas {MARQUEUR} après application")
            try:
                # compile() analyse et compile en mémoire, sur la COPIE : aucun
                # import, aucune exécution du code amont, aucun .pyc écrit.
                compile(contenu, relatif, "exec")
            except SyntaxError as exc:
                raise Refus(
                    f"le résultat n'est pas syntaxiquement valide ({relatif} ligne "
                    f"{exc.lineno} : {exc.msg}). Le clone n'a pas été touché.") from exc
            prepare[relatif] = contenu
    return prepare


def verifier(clone: Path, patch: Path,
             verifier_empreinte: bool = True) -> tuple[list[str], dict[str, str]]:
    """Toutes les vérifications préalables. Lève `Refus` au premier problème.

    `verifier_empreinte=False` n'existe que pour les tests, afin d'exercer les
    couches suivantes avec un correctif volontairement altéré. La ligne de
    commande ne l'expose pas.
    """
    lignes: list[str] = []

    if not clone.is_dir():
        raise Refus(f"{clone} n'est pas un dossier")
    if not patch.is_file():
        raise Refus(f"correctif introuvable : {patch}")

    racine = git(clone, "rev-parse", "--show-toplevel").strip()
    if Path(racine).resolve() != clone.resolve():
        raise Refus(f"{clone} n'est pas la racine d'un dépôt git (racine : {racine})")
    lignes.append(f"dépôt git        : {racine}")

    tete = git(clone, "rev-parse", "HEAD").strip()
    if tete != COMMIT_ATTENDU:
        raise Refus(
            f"version amont différente. HEAD = {tete}, attendu = {COMMIT_ATTENDU}. "
            "Ce correctif ne vaut que pour ce commit ; rien n'a été modifié.")
    lignes.append(f"commit           : {tete} (conforme)")

    sale = git(clone, "status", "--porcelain").strip()
    if sale:
        raise Refus("le clone n'est pas propre — aucune modification silencieuse ne "
                    f"sera faite dessus. Entrées : {'; '.join(sale.splitlines()[:5])}")
    lignes.append("état du clone    : propre")

    blob = git(clone, "rev-parse", f"HEAD:{FICHIER_VISE}").strip()
    if blob != BLOB_ATTENDU:
        raise Refus(f"blob de {FICHIER_VISE} = {blob}, attendu = {BLOB_ATTENDU}")
    lignes.append(f"{FICHIER_VISE:16s} : blob {blob} (conforme)")

    octets = patch.read_bytes()
    empreinte = hashlib.sha256(octets).hexdigest()
    if verifier_empreinte and empreinte != PATCH_SHA256:
        raise Refus(
            f"empreinte du correctif inattendue. sha256 = {empreinte}, "
            f"attendu = {PATCH_SHA256}. Un correctif modifié est refusé.")
    lignes.append(f"empreinte        : sha256 {empreinte[:16]}…"
                  f"{' (conforme)' if verifier_empreinte else ' (NON VÉRIFIÉE)'}")

    texte = octets.decode("utf-8", errors="replace")
    for attendu in (COMMIT_ATTENDU, BLOB_ATTENDU):
        if attendu not in texte:
            raise Refus(f"l'en-tête du correctif ne mentionne pas {attendu}")
    chemins = chemins_du_correctif(texte)
    lignes.append(f"chemins touchés  : {', '.join(sorted(chemins))} (autorisés)")

    git(clone, "apply", "--check", str(patch.resolve()))
    lignes.append("git apply --check : applicable")

    prepare = preparer(clone, patch, chemins)
    lignes.append("préparation      : appliqué et compilé hors du clone, "
                  "sans import ni exécution")
    return lignes, prepare


def appliquer(clone: Path, patch: Path, prepare: dict[str, str]) -> list[str]:
    """Écrit dans le clone, puis contrôle que le résultat est bien le préparé."""
    lignes: list[str] = []
    git(clone, "apply", str(patch.resolve()))
    try:
        for relatif, attendu in prepare.items():
            obtenu = (clone / relatif).read_text(encoding="utf-8")
            if obtenu != attendu:
                raise Refus(f"{relatif} diffère de ce qui avait été préparé")
        etat = {l[3:] for l in git(clone, "status", "--porcelain").splitlines()}
        surplus = sorted(etat - set(prepare))
        if surplus:
            raise Refus(f"des fichiers imprévus ont été touchés : {', '.join(surplus)}")
    except Refus:
        for relatif in prepare:
            git(clone, "checkout", "--", relatif, check=False)
        raise
    lignes.append(f"correctif appliqué : {', '.join(sorted(prepare))}")
    lignes.append("résultat identique à la préparation déjà compilée")
    lignes.append(f"retour arrière   : git -C {clone} checkout -- "
                  f"{' '.join(sorted(prepare))}")
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
        lignes, prepare = verifier(clone, patch)
        for ligne in lignes:
            print(f"  {ligne}")
        if args.appliquer:
            for ligne in appliquer(clone, patch, prepare):
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
