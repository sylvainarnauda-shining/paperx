"""Dépôt d'un échantillon : type, taille, résolution, et image RÉELLEMENT vérifiée.

Une signature PNG suivie d'un en-tête complaisant ne suffit pas : les pixels
doivent être là, en nombre exact.
"""

from __future__ import annotations

import struct
import unittest
import zlib

from paperx_web import uploads
from tests.aide_web import png, _chunk


class TestTypesRefuses(unittest.TestCase):
    def test_svg_refuse(self):
        svg = (b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg">'
               + b"<rect/>" * 200 + b"</svg>")
        verdict = uploads.check(svg, "ecriture.svg")
        self.assertFalse(verdict.accepted)
        self.assertTrue(any("actif" in p for p in verdict.problems))

    def test_extension_ne_fait_pas_foi(self):
        verdict = uploads.check(b"\x00" * 4000, "ecriture.png")
        self.assertFalse(verdict.accepted)
        self.assertTrue(any("signature" in p for p in verdict.problems))

    def test_fichier_trop_petit(self):
        self.assertFalse(uploads.check(b"\xff\xd8\xff" + b"0" * 10).accepted)

    def test_fichier_trop_gros(self):
        gros = b"\x89PNG\r\n\x1a\n" + b"0" * (uploads.MAX_BYTES + 1)
        verdict = uploads.check(gros)
        self.assertFalse(verdict.accepted)
        self.assertTrue(any("volumineux" in p for p in verdict.problems))


class TestImageReellementVerifiee(unittest.TestCase):
    def test_png_authentique_accepte(self):
        verdict = uploads.check(png(600, 800), "ecriture.png")
        self.assertTrue(verdict.accepted, verdict.problems)
        self.assertEqual((verdict.width, verdict.height), (600, 800))
        self.assertEqual(verdict.kind, uploads.KIND_PNG)

    def test_entete_menteur_refuse(self):
        """Un IHDR qui annonce 1200x1200 sans les pixels correspondants."""
        verdict = uploads.check(png(400, 600, declared=(1200, 1200)))
        self.assertFalse(verdict.accepted)
        self.assertTrue(any("n'en contient pas autant" in p for p in verdict.problems),
                        verdict.problems)

    def test_squelette_sans_pixels_refuse(self):
        squelette = (b"\x89PNG\r\n\x1a\n"
                     + _chunk(b"IHDR", struct.pack(">IIBBBBB", 1200, 1200, 8, 2, 0, 0, 0))
                     + _chunk(b"IEND", b"") + b"\x00" * 2000)
        self.assertFalse(uploads.check(squelette).accepted)

    def test_somme_de_controle_cassee_refusee(self):
        casse = bytearray(png(400, 400))
        casse[30] ^= 0xFF
        verdict = uploads.check(bytes(casse))
        self.assertFalse(verdict.accepted)
        self.assertTrue(any("contrôle" in p for p in verdict.problems))

    def test_octets_ajoutes_apres_la_fin_refuses(self):
        verdict = uploads.check(png(400, 400) + b"A" * 500)
        self.assertFalse(verdict.accepted)
        self.assertTrue(any("en trop" in p for p in verdict.problems))

    def test_png_tronque_refuse(self):
        entier = png(400, 500)
        self.assertFalse(uploads.check(entier[: len(entier) // 2]).accepted)

    def test_jpeg_bidon_refuse(self):
        self.assertFalse(uploads.check(b"\xff\xd8\xff" + b"\x00" * 4000).accepted)

    def test_bombe_de_decompression_bornee(self):
        """Un IDAT qui se décompresse énormément ne doit pas être suivi jusqu'au bout."""
        charge = zlib.compress(b"\x00" * (40 * 1024 * 1024))
        bombe = (b"\x89PNG\r\n\x1a\n"
                 + _chunk(b"IHDR", struct.pack(">IIBBBBB", 400, 400, 8, 2, 0, 0, 0))
                 + _chunk(b"IDAT", charge) + _chunk(b"IEND", b""))
        verdict = uploads.check(bombe)
        self.assertFalse(verdict.accepted)


class TestResolution(unittest.TestCase):
    def test_trop_petite(self):
        verdict = uploads.check(png(120, 120))
        self.assertFalse(verdict.accepted)
        self.assertTrue(any("résolution trop faible" in p for p in verdict.problems))


class TestNomDeStockage(unittest.TestCase):
    def test_identifiant_invalide_refuse(self):
        for mauvais in ("../evasion", "a" * 31, "A" * 32, "", "0" * 33):
            with self.subTest(valeur=mauvais):
                with self.assertRaises(ValueError):
                    uploads.storage_name(mauvais, uploads.KIND_PNG)

    def test_nom_genere_seulement(self):
        nom = uploads.storage_name("0" * 32, uploads.KIND_JPEG)
        self.assertEqual(nom, "0" * 32 + ".jpg")

    def test_politique_publiee(self):
        politique = uploads.policy()
        self.assertFalse(politique["svg_accepte"])
        self.assertIn("png", politique["verification"])


if __name__ == "__main__":
    unittest.main()
