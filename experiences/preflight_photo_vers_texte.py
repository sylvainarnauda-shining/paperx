#!/usr/bin/env python3
"""Diagnostic préalable à une expérience « photo manuscrite -> nouveau texte ».

Ce programme **ne conclut jamais qu'une inférence est possible**. Il ne sait
produire que des preuves, et il dit lesquelles lui manquent. Chaque point de
contrôle reçoit l'un de trois statuts :

  VERIFIE      preuve positive obtenue ici même ;
  REFUTE       preuve négative obtenue ici même (blocage constaté) ;
  NON_VERIFIE  aucune preuve ni dans un sens ni dans l'autre — bloquant.

Plusieurs points sont NON_VERIFIE **par construction** : ce programme ne
télécharge aucun poids, n'installe rien, n'exécute aucun code tiers et ne peut
pas attester d'un droit d'usage. Un tunnel HTTPS ouvert vers un domaine ne
prouve pas l'accès au fichier de poids exact ; la présence du pilote NVIDIA ne
prouve pas qu'un GPU calcule.

    python3 experiences/preflight_photo_vers_texte.py
    python3 experiences/preflight_photo_vers_texte.py --repos /chemin/clones
    python3 experiences/preflight_photo_vers_texte.py --hors-ligne

Codes de retour :
    1  au moins un point bloquant est REFUTE (blocage prouvé) ;
    2  aucun blocage prouvé, mais des points bloquants restent NON_VERIFIE ;
    0  tous les points bloquants sont VERIFIE — inatteignable par ce seul
       programme, et ne vaudrait toujours pas « prêt pour l'inférence ».
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import os
import shutil
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

VERIFIE, REFUTE, NON_VERIFIE = "VERIFIE", "REFUTE", "NON_VERIFIE"

# --- Sources amont, épinglées (relevé du 2026-09-09, clone superficiel) -------
UPSTREAM = {
    "One-DM": {
        "url": "https://github.com/dailenson/One-DM",
        "commit": "dde2205a70a2c70d1786503d198a795358c80ee4",
        "dir": "one-dm",
        "alphabet_file": "data_loader/loader.py",
        "licence_attendue": "MIT License",
    },
    "DiffBrush": {
        "url": "https://github.com/dailenson/DiffBrush",
        "commit": "da9addc1140bdfec463b2d41a974a0a392f80798",
        "dir": "diffbrush",
        "alphabet_file": "data_loader/IAMDataset.py",
        "licence_attendue": "MIT License",
    },
}

HOTES = {
    "github.com": "code source (lecture git anonyme)",
    "pypi.org": "roues Python",
    "huggingface.co": "VAE stable-diffusion-v1-5 exigé par les deux modèles",
    "drive.google.com": "poids pré-entraînés (lien principal)",
    "pan.baidu.com": "poids pré-entraînés (miroir)",
    "wisemodel.cn": "poids pré-entraînés (miroir One-DM)",
}

TEMOINS = {
    "ascii": "experiences/temoin_ascii.txt",
    "francais": "experiences/temoin_francais.txt",
}

MODULES_REQUIS = ("torch", "torchvision", "diffusers", "transformers", "numpy", "PIL")


@dataclass(frozen=True)
class Constat:
    """Un point de contrôle et la preuve qui le soutient — ou son absence."""

    domaine: str
    nom: str
    statut: str
    preuve: str
    bloquant: bool = True


# --- Extraction de l'alphabet : analyse syntaxique, jamais d'exécution -------

def alphabet_publie(chemin: Path) -> tuple[str | None, str]:
    """Lit la constante `letters` d'un fichier tiers **sans l'exécuter**.

    Le fichier est traité comme du texte : `ast.parse` en construit l'arbre,
    puis seule une valeur littérale (`ast.literal_eval`) est acceptée. Aucun
    import, aucun appel, aucune interpolation ne passe : une valeur calculée
    est refusée, pas devinée.
    """
    try:
        source = chemin.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"lecture impossible ({type(exc).__name__})"
    try:
        arbre = ast.parse(source, filename=str(chemin))
    except SyntaxError as exc:
        return None, f"source non analysable ({exc.msg})"

    for noeud in arbre.body:                      # affectations de premier niveau
        if isinstance(noeud, ast.Assign):
            cibles, valeur = noeud.targets, noeud.value
        elif isinstance(noeud, ast.AnnAssign) and noeud.value is not None:
            cibles, valeur = [noeud.target], noeud.value
        else:
            continue
        if not any(isinstance(c, ast.Name) and c.id == "letters" for c in cibles):
            continue
        try:
            litteral = ast.literal_eval(valeur)
        except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
            return None, "valeur de `letters` non littérale (calculée) : refusée"
        if isinstance(litteral, str):
            return litteral, "littéral chaîne"
        if isinstance(litteral, (list, tuple)) and all(isinstance(v, str) for v in litteral):
            return "".join(litteral), "littéral séquence de chaînes"
        return None, f"littéral de type inattendu ({type(litteral).__name__})"
    return None, "aucune affectation `letters` de premier niveau"


def premiere_ligne_utile(chemin: Path) -> str | None:
    """Première ligne non vide d'un fichier, ou None (fichier absent ou vide)."""
    try:
        texte = chemin.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for ligne in texte.splitlines():
        if ligne.strip():
            return ligne.strip()
    return None


# --- A. Matériel et pile logicielle ------------------------------------------

def constats_materiel(trouver=None) -> list[Constat]:
    """`trouver` remplace importlib.util.find_spec (utilisé par les tests)."""
    out: list[Constat] = []
    pilote = shutil.which("nvidia-smi") is not None or any(Path("/dev").glob("nvidia*"))
    out.append(Constat("matériel", "pilote GPU NVIDIA présent",
                       VERIFIE if pilote else REFUTE,
                       "nvidia-smi ou /dev/nvidia* détecté" if pilote
                       else "ni nvidia-smi ni /dev/nvidia*", bloquant=False))
    out.append(Constat(
        "matériel", "GPU réellement utilisable pour le calcul",
        REFUTE if not pilote else NON_VERIFIE,
        "aucun pilote : aucun contexte CUDA possible" if not pilote
        else "non testé : exigerait torch et une allocation réelle, "
             "que ce programme n'effectue pas"))

    ram = None
    try:
        for ligne in Path("/proc/meminfo").read_text().splitlines():
            if ligne.startswith("MemTotal:"):
                ram = int(ligne.split()[1]) / 1024 / 1024
                break
    except (OSError, ValueError, IndexError):
        pass
    libre = shutil.disk_usage(".").free / 1e9
    out.append(Constat("matériel", "ressources mesurées", VERIFIE,
                       f"{os.cpu_count()} processeurs, "
                       f"{f'{ram:.1f} Gio' if ram else 'mémoire inconnue'}, "
                       f"{libre:.1f} Go libres, Python {sys.version.split()[0]}",
                       bloquant=False))

    trouver = trouver or importlib.util.find_spec
    manquants = []
    for module in MODULES_REQUIS:
        try:
            repere = trouver(module) is not None
        except (ImportError, ValueError):
            repere = False
        if not repere:
            manquants.append(module)
    out.append(Constat(
        "matériel", "modules d'inférence repérables (find_spec)",
        REFUTE if manquants else VERIFIE,
        f"introuvables : {', '.join(manquants)}" if manquants
        else f"repérés : {', '.join(MODULES_REQUIS)} — la repérabilité ne dit rien "
             "de leur fonctionnement ni de leurs versions",
        bloquant=False))
    out.append(Constat(
        "matériel", "pile d'inférence fonctionnelle et versions compatibles",
        REFUTE if manquants else NON_VERIFIE,
        f"modules introuvables : {', '.join(manquants)}" if manquants
        else "non testé : exigerait d'importer et de faire tourner ces modules, "
             "et de confronter leurs versions à celles des dépôts amont"))
    return out


# --- B. Réseau : un tunnel n'est pas un accès au fichier ---------------------

def tunnel_https(hote: str, timeout: float = 12.0) -> tuple[bool, str]:
    """Ouvre un tunnel HTTPS vers le domaine. Ne lit aucun contenu, ne prouve
    l'accès à aucun fichier particulier."""
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    try:
        if proxy:
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({"https": proxy}))
            opener.open(urllib.request.Request(f"https://{hote}/", method="HEAD"),
                        timeout=timeout).close()
        else:
            socket.create_connection((hote, 443), timeout=timeout).close()
        return True, "tunnel ouvert"
    except urllib.error.HTTPError as exc:
        return True, f"tunnel ouvert (le domaine répond HTTP {exc.code})"
    except Exception as exc:                      # noqa: BLE001
        return False, f"{type(exc).__name__}: {str(exc)[:70]}"


def constats_reseau(hors_ligne: bool) -> list[Constat]:
    out: list[Constat] = []
    for hote, role in HOTES.items():
        if hors_ligne:
            out.append(Constat("réseau", f"tunnel HTTPS vers {hote}", NON_VERIFIE,
                               f"mode hors ligne : non testé ({role})"))
            continue
        ok, detail = tunnel_https(hote)
        out.append(Constat("réseau", f"tunnel HTTPS vers {hote}",
                           VERIFIE if ok else REFUTE, f"{detail} — {role}"))
    out.append(Constat(
        "réseau", "téléchargement du fichier de poids exact", NON_VERIFIE,
        "aucun téléchargement tenté : un tunnel vers le domaine ne prouve ni "
        "l'existence, ni l'accessibilité, ni la taille du fichier de poids"))
    return out


# --- C. Dépôts amont ---------------------------------------------------------

def commit_de(chemin: Path) -> str | None:
    try:
        return subprocess.run(["git", "-C", str(chemin), "rev-parse", "HEAD"],
                              capture_output=True, text=True, timeout=30,
                              check=True).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return None


def constats_depots(racine: Path) -> tuple[list[Constat], dict]:
    out: list[Constat] = []
    etat: dict = {}
    for nom, meta in UPSTREAM.items():
        chemin = racine / meta["dir"]
        etat[nom] = {"chemin": chemin, "present": chemin.exists()}
        if not chemin.exists():
            out.append(Constat("sources", f"{nom} : dépôt au commit épinglé", NON_VERIFIE,
                               f"absent de {chemin} — cloner puis "
                               f"git checkout {meta['commit'][:12]}"))
            out.append(Constat("sources", f"{nom} : licence du code", NON_VERIFIE,
                               "dépôt absent, licence non lue"))
            continue
        tete = commit_de(chemin)
        conforme = tete == meta["commit"]
        out.append(Constat("sources", f"{nom} : dépôt au commit épinglé",
                           VERIFIE if conforme else REFUTE,
                           f"HEAD {(tete or 'illisible')[:12]}…, "
                           f"attendu {meta['commit'][:12]}…"))
        ligne = premiere_ligne_utile(chemin / "LICENSE")
        if ligne is None:
            statut, preuve = NON_VERIFIE, "LICENSE absent ou vide : licence non établie"
        elif ligne == meta["licence_attendue"]:
            statut, preuve = VERIFIE, f"LICENSE commence par « {ligne} »"
        else:
            statut, preuve = REFUTE, f"LICENSE commence par « {ligne} », attendu « {meta['licence_attendue']} »"
        out.append(Constat("sources", f"{nom} : licence du code", statut, preuve))

    out.append(Constat(
        "sources", "droit d'usage des poids pré-entraînés", NON_VERIFIE,
        "aucune licence énoncée pour les poids dans les deux dépôts (la licence "
        "MIT porte sur le code) : accord écrit des auteurs à obtenir"))
    peuples = [nom for nom, e in etat.items()
               if e["present"] and (e["chemin"] / "model_zoo").is_dir()
               and any((e["chemin"] / "model_zoo").iterdir())]
    out.append(Constat(
        "sources", "dossier model_zoo contenant des fichiers",
        VERIFIE if peuples else REFUTE,
        f"non vide dans : {', '.join(peuples)} — la présence de fichiers ne dit pas "
        "lesquels" if peuples
        else "aucun model_zoo non vide dans les clones",
        bloquant=False))
    out.append(Constat(
        "sources", "poids exacts présents et intègres", NON_VERIFIE,
        "non vérifié : ce programme ne télécharge rien, ne connaît aucune empreinte "
        "de référence publiée, et ne distingue pas un point de contrôle d'un simple "
        "fichier déposé dans model_zoo"))
    return out, etat


# --- D. Couverture des phrases témoins ---------------------------------------

def constats_alphabet(etat: dict, racine_projet: Path) -> list[Constat]:
    out: list[Constat] = []
    phrases = {}
    for cle, rel in TEMOINS.items():
        chemin = racine_projet / rel
        if chemin.exists():
            phrases[cle] = chemin.read_text(encoding="utf-8").rstrip("\n")
        else:
            out.append(Constat("alphabet", f"phrase témoin {cle}", NON_VERIFIE,
                               f"fichier absent : {rel}"))

    for nom, meta in UPSTREAM.items():
        infos = etat.get(nom, {})
        if not infos.get("present"):
            out.append(Constat("alphabet", f"{nom} : couverture des témoins", NON_VERIFIE,
                               "dépôt absent, alphabet non lu"))
            continue
        lettres, comment = alphabet_publie(infos["chemin"] / meta["alphabet_file"])
        if lettres is None:
            out.append(Constat("alphabet", f"{nom} : couverture des témoins", NON_VERIFIE,
                               f"alphabet non extrait — {comment}"))
            continue
        for cle, phrase in phrases.items():
            manquants = sorted({c for c in phrase if c not in lettres}, key=ord)
            if manquants:
                detail = ", ".join(f"{c!r} U+{ord(c):04X}" for c in manquants)
                out.append(Constat(
                    "alphabet", f"{nom} : témoin {cle} écrivable", REFUTE,
                    f"{len(manquants)} caractère(s) impossible(s) : {detail} "
                    "— à signaler tels quels, jamais à retirer"))
            else:
                out.append(Constat("alphabet", f"{nom} : témoin {cle} écrivable", VERIFIE,
                                   f"tous les caractères figurent dans l'alphabet publié "
                                   f"({len(lettres)} caractères, {comment})"))
    return out


# --- E. Synthèse -------------------------------------------------------------

def synthese(constats: list[Constat]) -> tuple[int, list[str]]:
    """Rend un code de retour et les lignes de conclusion.

    Ne produit jamais d'affirmation de faisabilité : au mieux « aucun blocage
    prouvé », ce qui n'est pas « prêt pour l'inférence ».
    """
    bloquants = [c for c in constats if c.bloquant]
    refutes = [c for c in bloquants if c.statut == REFUTE]
    inconnus = [c for c in bloquants if c.statut == NON_VERIFIE]

    lignes = [
        f"Points de contrôle : {len(constats)} "
        f"({sum(c.statut == VERIFIE for c in constats)} VERIFIE, "
        f"{sum(c.statut == REFUTE for c in constats)} REFUTE, "
        f"{sum(c.statut == NON_VERIFIE for c in constats)} NON_VERIFIE)",
        "",
    ]
    if refutes:
        lignes.append(f"BLOCAGES PROUVÉS ({len(refutes)}) :")
        lignes += [f"  - {c.nom} : {c.preuve}" for c in refutes]
        lignes.append("")
    if inconnus:
        lignes.append(f"NON VÉRIFIÉ, donc bloquant ({len(inconnus)}) :")
        lignes += [f"  - {c.nom} : {c.preuve}" for c in inconnus]
        lignes.append("")

    lignes.append("Ce diagnostic rapporte ses propres preuves et rien de plus.")
    lignes.append("Il ne peut, à lui seul, établir qu'une inférence est réalisable.")
    if refutes or inconnus:
        lignes += [
            "",
            "Pistes ouvertes, sans promesse et sans imposer de GPU payant :",
            "  - adaptation CPU (ou MPS sur Apple) des points d'entrée, qui appellent",
            "    aujourd'hui nccl et cuda.set_device sans condition : à étudier, le",
            "    coût réel dépendant de la taille du UNet, inconnue tant que les poids",
            "    ne sont pas obtenus ;",
            "  - demande écrite du droit d'usage des poids, indépendante du calcul ;",
            "  - échantillon manuscrit explicitement réutilisable, jamais client.",
        ]
    return (1 if refutes else 2 if inconnus else 0), lignes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Diagnostic — ne conclut jamais à la faisabilité d'une inférence.")
    parser.add_argument("--repos", default="/home/user/dailenson",
                        help="dossier contenant les clones amont (défaut : %(default)s)")
    parser.add_argument("--hors-ligne", action="store_true",
                        help="ne teste aucun hôte ; les points réseau restent NON_VERIFIE")
    args = parser.parse_args(argv)

    racine_projet = Path(__file__).resolve().parent.parent
    print("Diagnostic — photo manuscrite vers nouveau texte")
    print("Aucune inférence, aucun téléchargement de poids, aucun code tiers exécuté.\n")

    constats = list(constats_materiel())
    constats += constats_reseau(args.hors_ligne)
    depots, etat = constats_depots(Path(args.repos))
    constats += depots
    constats += constats_alphabet(etat, racine_projet)

    domaine = None
    for c in constats:
        if c.domaine != domaine:
            domaine = c.domaine
            print(f"\n[{domaine}]")
        marque = "" if c.bloquant else "  (non bloquant)"
        print(f"  {c.statut:11s} {c.nom}{marque}")
        print(f"              {c.preuve}")

    code, lignes = synthese(constats)
    print("\n" + "=" * 72)
    for ligne in lignes:
        print(ligne)
    return code


if __name__ == "__main__":
    sys.exit(main())
