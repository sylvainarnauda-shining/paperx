"""La démonstration doit être reproductible et l'exemple versionné à jour."""

from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from paperx import cli, report

EXEMPLES = pathlib.Path("docs/exemples")


class TestDemonstrationReproductible(unittest.TestCase):
    def test_deux_executions_donnent_les_memes_octets(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            cli.run_demo("samples/extrait_demo_fr.txt", a)
            cli.run_demo("samples/extrait_demo_fr.txt", b)
            fichiers_a = sorted(p.name for p in pathlib.Path(a).iterdir())
            self.assertEqual(fichiers_a, sorted(p.name for p in pathlib.Path(b).iterdir()))
            for nom in fichiers_a:
                self.assertEqual((pathlib.Path(a) / nom).read_bytes(),
                                 (pathlib.Path(b) / nom).read_bytes(), nom)

    def test_exemple_versionne_a_jour(self):
        with tempfile.TemporaryDirectory() as tmp:
            cli.run_demo("samples/extrait_demo_fr.txt", tmp)
            for nom in ("page-01.svg", "rapport.json", "revue-page-01.txt"):
                attendu = (EXEMPLES / nom).read_text(encoding="utf-8")
                obtenu = (pathlib.Path(tmp) / nom).read_text(encoding="utf-8")
                self.assertEqual(obtenu, attendu,
                                 f"docs/exemples/{nom} est périmé : relancez la démo")

    def test_texte_complet_pagine_sur_plusieurs_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = cli.run_demo("samples/texte_demo_fr.txt", tmp)
        self.assertGreaterEqual(data["mise_en_page"]["pages"], 2)
        self.assertTrue(data["source"]["preservation_exacte"])
        self.assertEqual(data["mise_en_page"]["couverture"]
                         ["caracteres_non_pris_en_charge"], 0)

    def test_rapport_json_strict_et_revendications(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = cli.run_demo("samples/caracteres_absents_fr.txt", tmp)
            texte = (pathlib.Path(tmp) / "rapport.json").read_text(encoding="utf-8")

        def interdit(constante):
            raise AssertionError(f"littéral JSON non valide : {constante}")

        json.loads(texte, parse_constant=interdit)
        self.assertEqual(data["revendications"], report.CLAIMS)
        self.assertFalse(data["sortie_machine"]["disponible"])
        self.assertFalse(data["sortie_machine"]["gcode_executable_produit"])
        self.assertFalse(data["sortie_machine"]["acces_imprimante"])
        self.assertFalse(data["ecriture"]["personnalisee"])
        self.assertGreater(
            data["mise_en_page"]["couverture"]["caracteres_non_pris_en_charge"], 0)
        for page in data["pages"]:
            self.assertFalse(page["validation"]["pret_machine"])

    def test_ligne_de_commande(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(
                cli.main(["demo", "--text", "samples/extrait_demo_fr.txt", "--out", tmp]),
                0)
        self.assertEqual(cli.main(["demo", "--text", "samples/extrait_demo_fr.txt",
                                   "--out", tempfile.mkdtemp(), "--paper", "demo-a4"]), 0)


if __name__ == "__main__":
    unittest.main()


class TestExperienceFalsifiable(unittest.TestCase):
    def test_les_quatre_hypotheses_tiennent_sur_le_texte_inedit(self):
        from paperx import cli as cli_mod

        resultats, tout_ok = cli_mod.run_experiment("samples/texte_experience_fr.txt")
        self.assertEqual(len(resultats), 4)
        for r in resultats:
            with self.subTest(hypothese=r["hypothese"]):
                self.assertTrue(r["verdict"], r["hypothese"])
                self.assertTrue(r["refute_si"], "chaque hypothèse doit être réfutable")
        self.assertTrue(tout_ok)

    def test_experience_detecte_une_perte_de_texte(self):
        """Témoin négatif : si la reconstruction perdait un accent, H1 doit tomber."""
        import pathlib as _pathlib
        import tempfile as _tempfile

        from paperx import cli as cli_mod, layout as layout_mod

        original = layout_mod.LayoutResult.reconstruct

        def tronque(self):
            return original(self).replace("é", "e")

        with _tempfile.TemporaryDirectory() as tmp:
            chemin = _pathlib.Path(tmp) / "texte.txt"
            chemin.write_text("répétition\n", encoding="utf-8")
            layout_mod.LayoutResult.reconstruct = tronque
            try:
                resultats, tout_ok = cli_mod.run_experiment(str(chemin))
            finally:
                layout_mod.LayoutResult.reconstruct = original
        self.assertFalse(tout_ok)
        self.assertFalse(resultats[0]["verdict"], "H1 doit être réfutée")

    def test_ligne_de_commande_experience(self):
        from paperx import cli as cli_mod

        self.assertEqual(
            cli_mod.main(["experience", "--text", "samples/texte_experience_fr.txt"]), 0)
