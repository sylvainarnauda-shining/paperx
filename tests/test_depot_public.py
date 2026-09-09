"""Hygiène d'un dépôt public : aucun secret, aucune donnée client, aucun poids."""

from __future__ import annotations

import pathlib
import re
import unittest

RACINE = pathlib.Path(".")
RESERVES = {"docs/initial-evidence.md", "docs/evidence/one-dm-alphabet-check.json"}

MOTIFS_INTERDITS = (
    re.compile(r"ACCESS[_ ]?CODE\s*[:=]\s*\S", re.IGNORECASE),
    re.compile(r"\bLAN[_ ]?CODE\b", re.IGNORECASE),
    re.compile(r"\bserial[_ ]?number\s*[:=]\s*['\"]\w", re.IGNORECASE),
    re.compile(r"\bapi[_-]?key\s*[:=]\s*['\"]\w", re.IGNORECASE),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}"),
)

ENTREES_GITIGNORE_ATTENDUES = (
    "out/", ".env", "*.gcode", "*.3mf", "*.jpg", "*.png", "*.pt", "*.safetensors",
    "weights/", "samples/client/",
)


def fichiers_suivis():
    for chemin in RACINE.rglob("*"):
        if chemin.is_dir() or ".git/" in str(chemin):
            continue
        if any(part in {".git", "__pycache__", "out"} for part in chemin.parts):
            continue
        yield chemin


class TestHygieneDepot(unittest.TestCase):
    def test_aucun_secret_apparent(self):
        for chemin in fichiers_suivis():
            try:
                contenu = chemin.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for motif in MOTIFS_INTERDITS:
                self.assertIsNone(motif.search(contenu),
                                  f"{chemin} : motif sensible {motif.pattern}")

    def test_gitignore_couvre_les_categories_a_risque(self):
        contenu = pathlib.Path(".gitignore").read_text(encoding="utf-8")
        for entree in ENTREES_GITIGNORE_ATTENDUES:
            self.assertIn(entree, contenu, f".gitignore : entrée manquante {entree}")

    def test_aucun_poids_ni_binaire_de_modele(self):
        interdits = {".pt", ".pth", ".ckpt", ".safetensors", ".onnx", ".bin"}
        for chemin in fichiers_suivis():
            self.assertNotIn(chemin.suffix, interdits, f"{chemin} ressemble à des poids")

    def test_aucune_image_ni_pdf_versionne(self):
        """Photos de papier et échantillons manuscrits restent hors du dépôt."""
        interdits = {".jpg", ".jpeg", ".png", ".heic", ".tif", ".tiff", ".pdf"}
        for chemin in fichiers_suivis():
            self.assertNotIn(chemin.suffix.lower(), interdits, f"{chemin} versionné")

    def test_fichiers_reserves_au_coordinateur_intacts(self):
        """Ces fichiers appartiennent à la branche de preuves : on ne les modifie pas."""
        for nom in RESERVES:
            chemin = pathlib.Path(nom)
            if chemin.exists():
                self.assertGreater(chemin.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
