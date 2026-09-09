"""Le texte doit ressortir exactement tel qu'il est entré."""

from __future__ import annotations

import random
import unittest

from paperx import layout, paper, textsource
from paperx.errors import DecodingError


class TestPreservationExacte(unittest.TestCase):
    def _check(self, text: str, profile=None) -> layout.LayoutResult:
        src = textsource.from_bytes(text.encode("utf-8"), origin="<test>")
        result = layout.paginate(src, profile or paper.DEMO_A4)
        self.assertEqual(result.reconstruct(), text, "le texte reconstruit diffère du source")
        self.assertTrue(result.preservation_ok())
        return result

    def test_octets_inchanges(self):
        raw = "Été à Montpellier — l'œuvre coûte 100 %.\n".encode("utf-8")
        src = textsource.from_bytes(raw)
        self.assertEqual(src.as_bytes(), raw)
        self.assertEqual(src.char_length, len(raw.decode("utf-8")))

    def test_aucune_normalisation_unicode(self):
        # 'e' + accent combinant ne doit PAS être recomposé en 'é'
        text = "été\n"
        src = textsource.from_bytes(text.encode("utf-8"))
        self.assertEqual(src.text, text)
        self.assertNotIn("é", src.text)

    def test_utf8_invalide_refuse_sans_substitution(self):
        with self.assertRaises(DecodingError):
            textsource.from_bytes(b"caf\xe9\n", origin="<test>")

    def test_espaces_multiples_et_lignes_vides(self):
        self._check("a   b\n\n\n   c   \nd\n")

    def test_espaces_insecables_preservees(self):
        self._check("Prix : 100 % ; « oui »\n")

    def test_texte_vide_et_sans_retour_final(self):
        self.assertEqual(self._check("").reconstruct(), "")
        self._check("sans retour final")

    def test_mot_plus_long_que_la_ligne_coupe_mais_conserve(self):
        mot = "a" * 400
        result = self._check(f"debut {mot} fin\n")
        self.assertIn("coupe_dure", [e.code for e in result.events])

    def test_caracteres_non_pris_en_charge_conserves(self):
        text = "prix : 100 € et 漢 puis\tfin\n"
        result = self._check(text)
        self.assertIn("€", result.reconstruct())
        self.assertIn("漢", result.reconstruct())
        self.assertIn("\t", result.reconstruct())

    def test_chaque_index_place_une_fois_et_une_seule(self):
        text = "Un texte  avec\n\ndes trous   et « des accents » : é ù ç.\n"
        result = self._check(text)
        seen: list[int] = []
        for page in result.pages:
            for line in page.lines:
                for span in line.spans:
                    seen.extend(range(span.start, span.end))
        self.assertEqual(seen, list(range(len(text))),
                         "les index doivent couvrir le source, dans l'ordre, sans doublon")

    def test_corpus_aleatoires_deterministes(self):
        alphabet = list("abcde ÉÈàçœ«»…\n\t€ 漢-'’.,;:!?0123456789   ")
        rng = random.Random(20260909)
        for _ in range(300):
            n = rng.randint(0, 400)
            self._check("".join(rng.choice(alphabet) for _ in range(n)))


if __name__ == "__main__":
    unittest.main()
