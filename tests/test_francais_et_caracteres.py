"""Français couvert ; caractères absents signalés, jamais supprimés ni remplacés."""

from __future__ import annotations

import unittest

from paperx import charset, layout, paper, strokes, synthetic_hand, textsource

ACCENTS = "àâäçéèêëîïôöùûüÿœæÀÂÄÇÉÈÊËÎÏÔÖÙÛÜŒÆ"


class TestFrancais(unittest.TestCase):
    def test_socle_francais_entierement_couvert(self):
        self.assertEqual(charset.missing_from_french_baseline(), ())

    def test_chaque_accent_a_un_glyphe_distinct_de_sa_base(self):
        for accentue, base in (("é", "e"), ("è", "e"), ("ê", "e"), ("ë", "e"),
                               ("à", "a"), ("ç", "c"), ("ù", "u"), ("î", "i"),
                               ("ô", "o"), ("É", "E"), ("Ç", "C")):
            with self.subTest(accentue=accentue):
                g_acc = synthetic_hand.GLYPHS[accentue]
                g_base = synthetic_hand.GLYPHS[base]
                self.assertNotEqual(g_acc.strokes, g_base.strokes,
                                    "un accent doit ajouter des traits, pas être ignoré")
                self.assertGreater(len(g_acc.strokes), len(g_base.strokes) - 1)

    def test_aucune_translitteration(self):
        text = ACCENTS + "\n"
        result = layout.paginate(textsource.from_bytes(text.encode()), paper.DEMO_A4)
        self.assertEqual(result.reconstruct(), text)
        rendus = "".join(c.char for line in result.lines for c in line.chars)
        self.assertEqual(rendus, ACCENTS, "les accents ne doivent pas être remplacés")


class TestCaracteresNonPrisEnCharge(unittest.TestCase):
    def setUp(self):
        self.source = textsource.load("samples/caracteres_absents_fr.txt")
        self.result = layout.paginate(self.source, paper.DEMO_A4)

    def test_tous_signales_avec_leur_codepoint(self):
        report = self.result.coverage
        self.assertGreater(report.unsupported_count, 0)
        codes = {u.codepoint for u in report.unsupported}
        for attendu in ("U+20AC", "U+6F22", "U+0009", "U+00DF", "U+00F1"):
            self.assertIn(attendu, codes)
        for u in report.unsupported:
            self.assertTrue(u.indices, "chaque caractère absent doit être localisé")
            self.assertEqual(self.source.text[u.first_index], u.char)

    def test_conserves_dans_le_texte_reconstruit(self):
        self.assertEqual(self.result.reconstruct(), self.source.text)

    def test_aucun_trait_invente_mais_emplacement_marque(self):
        traj = strokes.build_page(self.result, 1)
        marques = {m.char for m in traj.unsupported_marks}
        self.assertIn("€", marques)
        self.assertIn("漢", marques)
        traces = {s.char for s in traj.strokes}
        self.assertNotIn("€", traces, "aucun glyphe ne doit être inventé")
        self.assertNotIn("漢", traces)

    def test_evenement_de_mise_en_page_emis(self):
        codes = [e.code for e in self.result.events]
        self.assertIn("caractere_non_pris_en_charge", codes)

    def test_charset_et_ecriture_versionnes(self):
        self.assertIn("@", charset.charset_ref())
        self.assertIn("@", synthetic_hand.hand_ref())


if __name__ == "__main__":
    unittest.main()
