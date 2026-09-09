"""Aperçu SVG : bien formé, lisible, honnête, déterministe."""

from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET

from paperx import layout, machine, paper, strokes, svg, textsource, validator

SVG_NS = "{http://www.w3.org/2000/svg}"


def rendu(chemin: str):
    src = textsource.load(chemin)
    result = layout.paginate(src, paper.DEMO_A4)
    traj = strokes.build_page(result, 1)
    report = validator.validate_page(traj, paper.DEMO_A4, machine.P1S_UNCALIBRATED,
                                     strokes.DEMO_SPEEDS)
    return result, traj, report, svg.render_page(result, traj, report.reach,
                                                 report.machine_ready)


class TestApercuSVG(unittest.TestCase):
    def setUp(self):
        self.result, self.traj, self.report, self.texte = rendu(
            "samples/extrait_demo_fr.txt")
        self.racine = ET.fromstring(self.texte)

    def test_xml_bien_forme_et_dimensions_a4(self):
        self.assertEqual(self.racine.get("width"), "210mm")
        self.assertEqual(self.racine.get("height"), "297mm")
        self.assertEqual(self.racine.get("viewBox"), "0 0 210 297")

    def test_couches_separees_ecriture_et_annotations(self):
        ids = {g.get("id") for g in self.racine.iter(f"{SVG_NS}g")}
        self.assertIn("ecriture-generique-synthetique", ids)
        self.assertIn("annotations-repere", ids)
        self.assertIn("annotations-texte", ids)

    def test_tous_les_traits_sont_rendus(self):
        polylignes = list(self.racine.iter(f"{SVG_NS}polyline"))
        self.assertEqual(len(polylignes), len(self.traj.strokes))
        self.assertGreater(len(polylignes), 100, "l'aperçu doit contenir de l'écriture")

    def test_avertissements_visibles(self):
        textes = " ".join(t.text or "" for t in self.racine.iter(f"{SVG_NS}text"))
        self.assertIn("ÉCRITURE GÉNÉRIQUE SYNTHÉTIQUE", textes)
        self.assertIn("non exécutable", self.texte)
        self.assertIn("prêt machine = NON", textes)

    def test_zone_hors_course_signalee(self):
        textes = " ".join(t.text or "" for t in self.racine.iter(f"{SVG_NS}text"))
        self.assertIn("ZONE HORS COURSE MACHINE", textes)
        self.assertIn("hors course", textes)

    def test_aucune_valeur_non_finie_dans_le_svg(self):
        for interdit in ("nan", "NaN", "inf", "Infinity"):
            self.assertNotIn(interdit, self.texte.replace("infini", ""))

    def test_caracteres_non_pris_en_charge_encadres(self):
        _, traj, report, texte = rendu("samples/caracteres_absents_fr.txt")
        racine = ET.fromstring(texte)
        ids = {g.get("id") for g in racine.iter(f"{SVG_NS}g")}
        self.assertIn("annotations-caracteres-non-pris-en-charge", ids)
        self.assertIn("U+20AC", texte)
        self.assertGreater(len(traj.unsupported_marks), 0)

    def test_determinisme(self):
        _, _, _, encore = rendu("samples/extrait_demo_fr.txt")
        self.assertEqual(self.texte, encore)


if __name__ == "__main__":
    unittest.main()
