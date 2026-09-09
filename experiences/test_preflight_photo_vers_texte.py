#!/usr/bin/env python3
"""Tests du diagnostic — bibliothèque standard, aucun accès réseau.

Ils prouvent surtout ce que le diagnostic doit REFUSER : exécuter du code tiers,
et conclure à une faisabilité qu'il n'a pas établie.

    python3 experiences/test_preflight_photo_vers_texte.py
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import preflight_photo_vers_texte as pf  # noqa: E402


class TestExtractionAlphabet(unittest.TestCase):
    """`letters` est lu par analyse syntaxique, jamais par exécution."""

    def _ecrire(self, contenu: str) -> Path:
        dossier = Path(tempfile.mkdtemp())
        chemin = dossier / "faux_loader.py"
        chemin.write_text(contenu, encoding="utf-8")
        return chemin

    def test_litteral_chaine_accepte(self):
        chemin = self._ecrire("import os\nletters = 'abc'\nstyle_len = 352\n")
        self.assertEqual(pf.alphabet_publie(chemin), ("abc", "littéral chaîne"))

    def test_litteral_sequence_accepte(self):
        valeur, _ = pf.alphabet_publie(self._ecrire("letters = ['a', 'b']\n"))
        self.assertEqual(valeur, "ab")

    def test_appel_de_fonction_refuse(self):
        """Cas exigé par la revue : une expression d'appel doit être rejetée."""
        valeur, motif = pf.alphabet_publie(self._ecrire("letters = open('x').read()\n"))
        self.assertIsNone(valeur)
        self.assertIn("non littérale", motif)

    def test_valeurs_calculees_refusees(self):
        for source in ("letters = 'a' + 'b'\n",
                       "x = 'a'\nletters = f'{x}'\n",
                       "import os\nletters = os.environ['PATH']\n",
                       "letters = [chr(i) for i in range(10)]\n",
                       "letters = {'a': 1}\n"):
            with self.subTest(source=source.strip()):
                valeur, _ = pf.alphabet_publie(self._ecrire(source))
                self.assertIsNone(valeur)

    def test_aucun_code_tiers_execute(self):
        """Preuve directe : un effet de bord au niveau module ne se produit pas."""
        dossier = Path(tempfile.mkdtemp())
        temoin = dossier / "temoin.txt"
        temoin.write_text("intact", encoding="utf-8")
        module = dossier / "faux_loader.py"
        module.write_text(
            "import pathlib\n"
            f"pathlib.Path({str(temoin)!r}).write_text('EXECUTE')\n"
            "raise SystemExit('ce module ne doit jamais tourner')\n"
            "letters = 'abc'\n", encoding="utf-8")
        valeur, _ = pf.alphabet_publie(module)
        self.assertEqual(valeur, "abc")
        self.assertEqual(temoin.read_text(encoding="utf-8"), "intact")

    def test_affectation_non_globale_ignoree(self):
        valeur, motif = pf.alphabet_publie(
            self._ecrire("def f():\n    letters = 'abc'\n    return letters\n"))
        self.assertIsNone(valeur)
        self.assertIn("premier niveau", motif)

    def test_fichier_absent_ou_illisible(self):
        valeur, motif = pf.alphabet_publie(Path("/inexistant/loader.py"))
        self.assertIsNone(valeur)
        self.assertIn("lecture impossible", motif)
        valeur, motif = pf.alphabet_publie(self._ecrire("def ((\n"))
        self.assertIsNone(valeur)
        self.assertIn("non analysable", motif)


class TestLicence(unittest.TestCase):
    """Une licence vide ou absente ne doit ni planter ni passer pour conforme."""

    def test_fichier_vide_ne_leve_pas_index_error(self):
        dossier = Path(tempfile.mkdtemp())
        for contenu in ("", "\n\n", "   \n\t\n"):
            with self.subTest(contenu=repr(contenu)):
                chemin = dossier / "LICENSE"
                chemin.write_text(contenu, encoding="utf-8")
                self.assertIsNone(pf.premiere_ligne_utile(chemin))

    def test_fichier_absent(self):
        self.assertIsNone(pf.premiere_ligne_utile(Path("/inexistant/LICENSE")))

    def test_premiere_ligne_non_vide(self):
        chemin = Path(tempfile.mkdtemp()) / "LICENSE"
        chemin.write_text("\n\n  MIT License  \nCopyright\n", encoding="utf-8")
        self.assertEqual(pf.premiere_ligne_utile(chemin), "MIT License")

    def test_licence_vide_donne_non_verifie_bloquant(self):
        racine = Path(tempfile.mkdtemp())
        for meta in pf.UPSTREAM.values():
            depot = racine / meta["dir"]
            depot.mkdir(parents=True)
            (depot / "LICENSE").write_text("", encoding="utf-8")
        constats, _ = pf.constats_depots(racine)
        licences = [c for c in constats if c.nom.endswith("licence du code")]
        self.assertEqual(len(licences), 2)
        for c in licences:
            self.assertEqual(c.statut, pf.NON_VERIFIE)
            self.assertTrue(c.bloquant, "la licence doit peser sur le verdict")

    def test_licence_inattendue_donne_refute(self):
        racine = Path(tempfile.mkdtemp())
        for meta in pf.UPSTREAM.values():
            depot = racine / meta["dir"]
            depot.mkdir(parents=True)
            (depot / "LICENSE").write_text("Proprietary — all rights reserved\n",
                                           encoding="utf-8")
        constats, _ = pf.constats_depots(racine)
        for c in (c for c in constats if c.nom.endswith("licence du code")):
            self.assertEqual(c.statut, pf.REFUTE)


class TestRefusDesFauxPositifs(unittest.TestCase):
    """Le diagnostic ne doit jamais se déclarer prêt sur des indices faibles."""

    def test_tunnel_ouvert_ne_prouve_pas_l_acces_aux_poids(self):
        constats = pf.constats_reseau(hors_ligne=True)   # aucun appel réseau
        telechargement = [c for c in constats
                          if c.nom == "téléchargement du fichier de poids exact"]
        self.assertEqual(len(telechargement), 1)
        self.assertEqual(telechargement[0].statut, pf.NON_VERIFIE)
        self.assertTrue(telechargement[0].bloquant)
        for c in constats:
            if c.nom.startswith("tunnel HTTPS"):
                self.assertIn("tunnel", c.nom, "le nom doit dire tunnel, pas « accès »")

    def test_pilote_present_ne_prouve_pas_un_gpu_utilisable(self):
        constats = pf.constats_materiel()
        gpu = [c for c in constats if c.nom == "GPU réellement utilisable pour le calcul"]
        self.assertEqual(len(gpu), 1)
        self.assertIn(gpu[0].statut, (pf.REFUTE, pf.NON_VERIFIE))
        self.assertNotEqual(gpu[0].statut, pf.VERIFIE,
                            "ce programme ne peut pas prouver qu'un GPU calcule")
        pilote = [c for c in constats if c.nom == "pilote GPU NVIDIA présent"][0]
        self.assertFalse(pilote.bloquant, "la présence du pilote n'est qu'un indice")

    def test_points_non_verifiables_toujours_presents(self):
        """Un verdict vert est hors d'atteinte de ce programme, par construction."""
        racine = Path(tempfile.mkdtemp())
        constats = pf.constats_materiel() + pf.constats_reseau(hors_ligne=True)
        depots, etat = pf.constats_depots(racine)
        constats += depots + pf.constats_alphabet(etat, Path(__file__).resolve().parent.parent)
        invariants = {"téléchargement du fichier de poids exact",
                      "droit d'usage des poids pré-entraînés",
                      "poids pré-entraînés présents localement"}
        presents = {c.nom for c in constats if c.statut == pf.NON_VERIFIE and c.bloquant}
        self.assertTrue(invariants <= presents, invariants - presents)
        self.assertNotEqual(pf.synthese(constats)[0], 0)

    def test_synthese_refute_prime_sur_tout(self):
        constats = [pf.Constat("d", "ok", pf.VERIFIE, "preuve") for _ in range(10)]
        constats.append(pf.Constat("d", "cassé", pf.REFUTE, "preuve négative"))
        code, lignes = pf.synthese(constats)
        self.assertEqual(code, 1)
        self.assertIn("BLOCAGES PROUVÉS (1) :", lignes)

    def test_synthese_non_verifie_bloque_meme_sans_refute(self):
        constats = [pf.Constat("d", "ok", pf.VERIFIE, "preuve") for _ in range(10)]
        constats.append(pf.Constat("d", "inconnu", pf.NON_VERIFIE, "aucune preuve"))
        code, _ = pf.synthese(constats)
        self.assertEqual(code, 2, "un point bloquant non vérifié interdit le vert")

    def test_non_bloquant_ne_declenche_pas_de_blocage(self):
        constats = [pf.Constat("d", "indice", pf.REFUTE, "preuve", bloquant=False),
                    pf.Constat("d", "ok", pf.VERIFIE, "preuve")]
        self.assertEqual(pf.synthese(constats)[0], 0)

    def test_aucune_promesse_de_faisabilite_dans_la_sortie(self):
        constats = [pf.Constat("d", "x", pf.NON_VERIFIE, "aucune preuve")]
        texte = " ".join(pf.synthese(constats)[1]).lower()
        for promesse in ("inférence possible", "prêt pour l'inférence", "prêt machine",
                         "faisable", "il ne reste plus qu'à", "rien d'autre"):
            self.assertNotIn(promesse, texte)
        self.assertIn("ne peut", texte)


if __name__ == "__main__":
    unittest.main(verbosity=2)
