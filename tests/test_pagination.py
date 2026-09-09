"""Pagination A4 : géométrie honnête, encre dans les marges, régressions de revue."""

from __future__ import annotations

import dataclasses as dc
import unittest

from paperx import layout, paper, strokes, synthetic_hand, textsource
from paperx.errors import LayoutError, ProfileError


def ink_bbox(result: layout.LayoutResult):
    xs, ys = [], []
    for page in result.pages:
        for stroke in strokes.build_page(result, page.number).strokes:
            for x, y in stroke.points:
                xs.append(x)
                ys.append(y)
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


class TestGeometriePage(unittest.TestCase):
    def test_pages_et_lignes_du_profil_demo(self):
        src = textsource.load("samples/texte_demo_fr.txt")
        result = layout.paginate(src, paper.DEMO_A4)
        self.assertGreaterEqual(len(result.pages), 2, "le texte de démonstration doit paginer")
        self.assertTrue(all(len(p.lines) <= result.metrics.lines_per_page
                            for p in result.pages))
        for page in result.pages:
            for line in page.lines:
                self.assertEqual(line.page_number, page.number)

    def test_regression_descendantes_sous_marge_basse(self):
        """Revue : first_baseline_mm=29 plaçait un 'g' à y=278,1 > marge basse 277."""
        profile = dc.replace(paper.DEMO_A4, first_baseline_mm=29.0)
        self.assertEqual(profile.lines_per_page(), 32)          # sans réserve
        result = layout.paginate(textsource.from_bytes(("\n" * 31 + "g").encode()), profile)
        self.assertEqual(result.metrics.lines_per_page, 31)     # avec réserve
        _, _, _, ymax = ink_bbox(result)
        self.assertLessEqual(ymax, profile.height_mm - profile.margin_bottom_mm)

    def test_regression_debord_gauche_du_j(self):
        """Revue : un 'j' en début de ligne sortait à x=19,58 (marge gauche 20)."""
        self.assertLess(synthetic_hand.INK_MIN_X, 0.0, "le 'j' doit bien déborder à gauche")
        result = layout.paginate(textsource.from_bytes("jjj jjj\n".encode()), paper.DEMO_A4)
        xmin, _, xmax, _ = (ink_bbox(result)[0], 0, ink_bbox(result)[2], 0)
        self.assertGreaterEqual(xmin, paper.DEMO_A4.margin_left_mm)
        self.assertLessEqual(xmax, paper.DEMO_A4.width_mm - paper.DEMO_A4.margin_right_mm)

    def test_encre_dans_les_marges_sur_tout_le_corpus(self):
        src = textsource.load("samples/texte_demo_fr.txt")
        result = layout.paginate(src, paper.DEMO_A4)
        xmin, ymin, xmax, ymax = ink_bbox(result)
        p = paper.DEMO_A4
        self.assertGreaterEqual(xmin, p.margin_left_mm)
        self.assertLessEqual(xmax, p.width_mm - p.margin_right_mm)
        self.assertGreaterEqual(ymin, p.margin_top_mm)
        self.assertLessEqual(ymax, p.height_mm - p.margin_bottom_mm)

    def test_regression_profils_geometriquement_incoherents(self):
        """Revue : first_baseline_mm=0 était accepté, capitales hors page."""
        for champ in ({"first_baseline_mm": 0.0}, {"first_baseline_mm": -3.0},
                      {"margin_left_mm": 200.0}, {"line_height_mm": 0.0},
                      {"first_baseline_mm": 400.0}):
            with self.subTest(champ=champ):
                with self.assertRaises(ProfileError):
                    dc.replace(paper.DEMO_A4, **champ)
        # accepté par le profil, mais incompatible avec l'encre de l'écriture
        with self.assertRaises(LayoutError):
            layout.paginate(textsource.from_bytes(b"A"),
                            dc.replace(paper.DEMO_A4, first_baseline_mm=22.0))

    def test_regression_ligne_de_200_espaces(self):
        """Revue : 200 espaces puis 'b' produisaient une ligne de 300 mm."""
        text = " " * 200 + "b"
        result = layout.paginate(textsource.from_bytes(text.encode()), paper.DEMO_A4)
        self.assertEqual(result.reconstruct(), text)
        for line in result.lines:
            self.assertLessEqual(line.width_mm, result.metrics.usable_width_mm + 1e-9)
        self.assertIn("espaces_repliees", [e.code for e in result.events])

    def test_espaces_finales_ne_debordent_pas(self):
        text = "mot" + " " * 300 + "\n" + " " * 120
        result = layout.paginate(textsource.from_bytes(text.encode()), paper.DEMO_A4)
        self.assertEqual(result.reconstruct(), text)
        for line in result.lines:
            self.assertLessEqual(line.width_mm, result.metrics.usable_width_mm + 1e-9)

    def test_aucune_reduction_pour_faire_tenir(self):
        """Le corps ne doit jamais être réduit : il reste celui du profil."""
        src = textsource.load("samples/texte_demo_fr.txt")
        result = layout.paginate(src, paper.DEMO_A4)
        self.assertEqual(result.paper.font_size_mm, paper.DEMO_A4.font_size_mm)
        largeurs = {round(c.advance_mm / synthetic_hand.advance_of(c.char), 6)
                    for line in result.lines for c in line.chars
                    if synthetic_hand.advance_of(c.char) > 0}
        self.assertEqual(largeurs, {paper.DEMO_A4.font_size_mm})


if __name__ == "__main__":
    unittest.main()
