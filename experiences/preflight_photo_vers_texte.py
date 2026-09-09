#!/usr/bin/env python3
"""Contrôle préalable à une première expérience « photo manuscrite -> nouveau texte ».

Ce script ne lance AUCUNE inférence et ne télécharge RIEN. Il constate, dans
l'environnement où il tourne, si les conditions d'une inférence réelle sont
réunies :

  A. matériel disponible (CPU, mémoire, disque, GPU) ;
  B. joignabilité des hôtes nécessaires (code, poids, VAE, index de paquets) ;
  C. présence des dépôts amont aux commits épinglés, et leur licence ;
  D. couverture des phrases témoins par l'alphabet PUBLIÉ de chaque modèle,
     avec la liste exacte des caractères impossibles ;
  E. verdict : inférence possible ou bloquée, et prochaine action minimale.

Il est volontairement isolé : bibliothèque standard uniquement, aucun import du
banc d'essai paperx, aucune écriture hors de la sortie console.

    python3 experiences/preflight_photo_vers_texte.py
    python3 experiences/preflight_photo_vers_texte.py --repos /home/user/dailenson

Code de retour : 0 si une inférence réelle est possible ici, 1 sinon.
"""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

# --- Sources amont, épinglées -------------------------------------------------
# Commits relevés le 2026-09-09 par clone superficiel du dépôt public.
UPSTREAM = {
    "One-DM": {
        "url": "https://github.com/dailenson/One-DM",
        "commit": "dde2205a70a2c70d1786503d198a795358c80ee4",
        "dir": "one-dm",
        "alphabet_file": "data_loader/loader.py",
        "licence_attendue": "MIT License",
        "entree": "test.py",
    },
    "DiffBrush": {
        "url": "https://github.com/dailenson/DiffBrush",
        "commit": "da9addc1140bdfec463b2d41a974a0a392f80798",
        "dir": "diffbrush",
        "alphabet_file": "data_loader/IAMDataset.py",
        "licence_attendue": "MIT License",
        "entree": "generate.py",
    },
}

#: Hôtes indispensables à une inférence réelle, et ce qu'ils portent.
HOSTS = {
    "github.com": "code source des deux dépôts (lecture git anonyme)",
    "pypi.org": "roues Python (torch, diffusers, …)",
    "huggingface.co": "VAE stable-diffusion-v1-5 exigé par les deux modèles",
    "drive.google.com": "poids pré-entraînés (lien principal des deux dépôts)",
    "pan.baidu.com": "poids pré-entraînés (miroir)",
    "wisemodel.cn": "poids pré-entraînés (miroir One-DM)",
}

TEMOINS = {
    "ASCII témoin": "experiences/temoin_ascii.txt",
    "français": "experiences/temoin_francais.txt",
}


def titre(texte: str) -> None:
    print(f"\n{texte}\n" + "-" * len(texte))


# --- A. Matériel --------------------------------------------------------------

def controle_materiel() -> dict:
    total_ram = None
    try:
        for ligne in Path("/proc/meminfo").read_text().splitlines():
            if ligne.startswith("MemTotal:"):
                total_ram = int(ligne.split()[1]) / 1024 / 1024
                break
    except OSError:
        pass
    disque = shutil.disk_usage(".")
    gpu = shutil.which("nvidia-smi") is not None or any(
        Path("/dev").glob("nvidia*"))

    titre("A. Matériel disponible")
    print(f"  processeurs        : {os.cpu_count()}")
    print(f"  mémoire vive       : {total_ram:.1f} Gio" if total_ram
          else "  mémoire vive       : inconnue")
    print(f"  disque libre       : {disque.free / 1e9:.1f} Go")
    print(f"  GPU NVIDIA         : {'oui' if gpu else 'NON'}")
    print(f"  Python             : {sys.version.split()[0]}")
    return {"gpu": gpu, "ram_gio": total_ram, "disque_go": disque.free / 1e9}


# --- B. Réseau ----------------------------------------------------------------

def joignable(hote: str, timeout: float = 12.0) -> tuple[bool, str]:
    """Teste l'ouverture d'un tunnel HTTPS. Aucun octet de contenu n'est lu."""
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    try:
        if proxy:
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({"https": proxy}))
            requete = urllib.request.Request(f"https://{hote}/", method="HEAD")
            opener.open(requete, timeout=timeout).close()
        else:
            socket.create_connection((hote, 443), timeout=timeout).close()
        return True, "joignable"
    except urllib.error.HTTPError as exc:            # répond, donc joignable
        return True, f"joignable (HTTP {exc.code})"
    except Exception as exc:                          # noqa: BLE001
        return False, f"REFUSÉ ({type(exc).__name__}: {str(exc)[:60]})"


def controle_reseau() -> dict:
    titre("B. Hôtes nécessaires")
    etat = {}
    for hote, role in HOSTS.items():
        ok, detail = joignable(hote)
        etat[hote] = ok
        print(f"  {hote:20s} {'OK    ' if ok else 'BLOQUÉ'}  {role}")
        if not ok:
            print(f"  {'':20s}        {detail}")
    return etat


# --- C. Dépôts amont ----------------------------------------------------------

def commit_de(chemin: Path) -> str | None:
    try:
        return subprocess.run(["git", "-C", str(chemin), "rev-parse", "HEAD"],
                              capture_output=True, text=True, timeout=30,
                              check=True).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return None


def controle_depots(racine: Path) -> dict:
    titre("C. Dépôts amont (commits épinglés)")
    etat = {}
    for nom, meta in UPSTREAM.items():
        chemin = racine / meta["dir"]
        if not chemin.exists():
            print(f"  {nom:10s} ABSENT — clonez-le :")
            print(f"             GIT_LFS_SKIP_SMUDGE=1 git clone {meta['url']} {chemin}")
            print(f"             git -C {chemin} checkout {meta['commit']}")
            etat[nom] = {"present": False, "chemin": chemin}
            continue
        tete = commit_de(chemin)
        conforme = tete == meta["commit"]
        licence = chemin / "LICENSE"
        texte_licence = licence.read_text(encoding="utf-8", errors="replace").splitlines()[0].strip() \
            if licence.exists() else "AUCUN fichier LICENSE"
        licence_ok = texte_licence == meta["licence_attendue"]
        print(f"  {nom:10s} présent | commit {'conforme' if conforme else 'DIFFÉRENT'} "
              f"({(tete or '?')[:12]}…, attendu {meta['commit'][:12]}…)")
        print(f"  {'':10s} licence du CODE : {texte_licence} "
              f"{'(conforme)' if licence_ok else '(À VÉRIFIER)'}")
        etat[nom] = {"present": True, "chemin": chemin,
                     "commit_ok": conforme, "licence_ok": licence_ok}
    print("  Rappel : la licence MIT porte sur le CODE. Les POIDS pré-entraînés sont")
    print("  distribués à part (Google Drive / Baidu / wisemodel) sans licence propre")
    print("  énoncée dans les dépôts : droit d'usage à établir avant tout usage payant.")
    return etat


# --- D. Couverture des phrases témoins ---------------------------------------

def alphabet_publie(chemin_fichier: Path) -> str | None:
    """Lit la constante `letters` du dépôt amont. Rien n'est recopié ici."""
    try:
        for ligne in chemin_fichier.read_text(encoding="utf-8").splitlines():
            if ligne.startswith("letters"):
                valeur = ligne.split("=", 1)[1].strip()
                resultat = eval(valeur, {"__builtins__": {}}, {})  # littéral seul
                if isinstance(resultat, str):
                    return resultat
                if isinstance(resultat, (list, tuple)):
                    return "".join(resultat)
    except (OSError, SyntaxError, ValueError, IndexError):
        return None
    return None


def controle_couverture(etat_depots: dict, racine_projet: Path) -> dict:
    titre("D. Caractères impossibles avec l'alphabet PUBLIÉ")
    phrases = {}
    for nom, rel in TEMOINS.items():
        chemin = racine_projet / rel
        if not chemin.exists():
            print(f"  phrase témoin absente : {rel}")
            continue
        phrases[nom] = chemin.read_text(encoding="utf-8").rstrip("\n")

    resultats = {}
    for modele, meta in UPSTREAM.items():
        infos = etat_depots.get(modele, {})
        if not infos.get("present"):
            print(f"  {modele} : dépôt absent, vérification impossible")
            continue
        lettres = alphabet_publie(infos["chemin"] / meta["alphabet_file"])
        if lettres is None:
            print(f"  {modele} : alphabet illisible dans {meta['alphabet_file']}")
            continue
        print(f"  {modele} — alphabet publié : {len(lettres)} caractères "
              f"({meta['alphabet_file']})")
        resultats[modele] = {}
        for nom, phrase in phrases.items():
            manquants = sorted({c for c in phrase if c not in lettres}, key=ord)
            resultats[modele][nom] = manquants
            if manquants:
                detail = ", ".join(f"{c!r} U+{ord(c):04X}" for c in manquants)
                print(f"      {nom:14s} : {len(manquants)} caractère(s) IMPOSSIBLE(S) "
                      f"-> {detail}")
                print(f"      {'':14s}   (à signaler tels quels ; ne jamais retirer "
                      "un accent pour masquer la limite)")
            else:
                print(f"      {nom:14s} : intégralement couvert")
    return resultats


# --- E. Verdict ---------------------------------------------------------------

def verdict(materiel: dict, reseau: dict, depots: dict) -> bool:
    titre("E. Verdict")
    blocages: list[str] = []

    if not materiel["gpu"]:
        blocages.append(
            "aucun GPU : les points d'entrée publiés appellent "
            "dist.init_process_group(backend='nccl') et torch.cuda.set_device() "
            "sans condition ; --device cpu ne suffit pas")
    for hote in ("huggingface.co",):
        if not reseau.get(hote):
            blocages.append(
                f"{hote} injoignable : le VAE stable-diffusion-v1-5 exigé par les "
                "deux modèles ne peut pas être obtenu")
    if not any(reseau.get(h) for h in ("drive.google.com", "pan.baidu.com", "wisemodel.cn")):
        blocages.append(
            "aucun hôte de poids joignable (Google Drive, Baidu, wisemodel) : "
            "aucun point de contrôle pré-entraîné ne peut être obtenu")
    for nom, infos in depots.items():
        if not infos.get("present"):
            blocages.append(f"dépôt {nom} absent localement")
        elif not infos.get("commit_ok"):
            blocages.append(f"dépôt {nom} sur un autre commit que celui épinglé")

    if blocages:
        print("  INFÉRENCE IMPOSSIBLE ICI. Blocages constatés :")
        for i, b in enumerate(blocages, 1):
            print(f"    {i}. {b}")
        print("\n  Prochaine action minimale : obtenir un environnement avec GPU et")
        print("  accès sortant à huggingface.co et à un miroir de poids, puis relancer")
        print("  ce script. Rien d'autre n'est à faire tant que ces accès manquent.")
        return False

    print("  Conditions matérielles, réseau et sources réunies.")
    print("  Restent à vérifier AVANT toute inférence, hors de la portée de ce script :")
    print("    - droit d'usage des poids pré-entraînés (aucune licence propre publiée) ;")
    print("    - échantillon de style explicitement réutilisable — les images livrées")
    print("      dans DiffBrush/test_data suivent le nommage des formulaires IAM,")
    print("      base réservée à la recherche : ne pas s'en servir pour un service payant ;")
    print("    - jamais d'échantillon client dans un dépôt public.")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repos", default="/home/user/dailenson",
                        help="dossier contenant les clones amont (défaut : %(default)s)")
    args = parser.parse_args(argv)

    racine_projet = Path(__file__).resolve().parent.parent
    print("Contrôle préalable — photo manuscrite vers nouveau texte")
    print("Aucune inférence lancée, aucun téléchargement effectué.")

    materiel = controle_materiel()
    reseau = controle_reseau()
    depots = controle_depots(Path(args.repos))
    controle_couverture(depots, racine_projet)
    return 0 if verdict(materiel, reseau, depots) else 1


if __name__ == "__main__":
    sys.exit(main())
