"""Faces, feuilles, supplément inconnu : le devis ne suppose jamais rien."""

from __future__ import annotations

import math
import unittest

from paperx import duplex, pricing
from paperx.errors import PaperxError, ProfileError


class TestFacesEtFeuilles(unittest.TestCase):
    def test_prix_porte_sur_la_face_ecrite(self):
        for faces in (0, 1, 2, 3, 17):
            for mode in duplex.Sides:
                devis = duplex.estimate(faces, mode)
                self.assertEqual(devis.base_cents, pricing.PRICE_PER_A4_CENTS * faces,
                                 "le recto-verso ne divise jamais le prix de l'écriture")

    def test_feuilles_recto_verso_plafond(self):
        for faces in range(0, 40):
            self.assertEqual(duplex.sheets_for(faces, duplex.Sides.RECTO_VERSO),
                             math.ceil(faces / 2))
            self.assertEqual(duplex.sheets_for(faces, duplex.Sides.RECTO), faces)

    def test_pas_de_demi_tarif_implicite(self):
        recto = duplex.estimate(4, duplex.Sides.RECTO)
        verso = duplex.estimate(4, duplex.Sides.RECTO_VERSO)
        self.assertEqual(recto.base_cents, verso.base_cents)
        self.assertLess(verso.sheets, recto.sheets)

    def test_faces_invalides_refusees(self):
        for mauvais in (-1, 1.5, "2", True, None):
            with self.subTest(valeur=mauvais):
                with self.assertRaises(PaperxError):
                    duplex.estimate(mauvais, duplex.Sides.RECTO)


class TestSupplementInconnu(unittest.TestCase):
    def test_par_defaut_a_etablir_jamais_zero(self):
        devis = duplex.estimate(6, duplex.Sides.RECTO_VERSO)
        self.assertEqual(devis.supplement.status, duplex.STATUS_A_ETABLIR)
        self.assertIsNone(devis.supplement.cents)
        self.assertIsNone(devis.total_cents)
        self.assertFalse(devis.total_confirmed)
        self.assertIn("à établir", devis.as_dict()["supplement"]["libelle"])

    def test_cout_partiel_reste_inconnu(self):
        partiel = duplex.OperatorCosts(
            id="partiel", version="1.0.0", flip_seconds=20.0, realign_seconds=15.0,
            check_seconds=None, hourly_rate_cents=2500, spoilage_rate=0.03,
            measured=False, provenance="test")
        devis = duplex.estimate(4, duplex.Sides.RECTO_VERSO, partiel)
        self.assertIsNone(devis.supplement.cents)
        self.assertIn("secondes_controle_alignement",
                      devis.supplement.detail["manquant"])

    def test_hypothese_marquee_et_total_non_confirme(self):
        couts = duplex.hypothesis_costs(20.0, 15.0, 10.0, 2500, 0.03)
        devis = duplex.estimate(4, duplex.Sides.RECTO_VERSO, couts)
        self.assertEqual(devis.supplement.status, duplex.STATUS_SOUS_HYPOTHESE)
        self.assertTrue(devis.supplement.hypothetical)
        self.assertEqual(devis.supplement.provenance_code, duplex.PROVENANCE_HYPOTHESE)
        self.assertIsNotNone(devis.total_cents)
        self.assertFalse(devis.total_confirmed)

    def test_supplement_compte_manipulation_et_controle(self):
        sans = duplex.hypothesis_costs(20.0, 15.0, 0.0, 3600, 0.0)
        avec = duplex.hypothesis_costs(20.0, 15.0, 10.0, 3600, 0.0)
        faces = 4
        self.assertGreater(
            duplex.estimate(faces, duplex.Sides.RECTO_VERSO, avec).supplement.cents,
            duplex.estimate(faces, duplex.Sides.RECTO_VERSO, sans).supplement.cents,
            "le contrôle d'alignement doit peser dans le supplément")

    def test_recto_seul_sans_supplement(self):
        devis = duplex.estimate(5, duplex.Sides.RECTO)
        self.assertEqual(devis.supplement.status, duplex.STATUS_SANS_OBJET)
        self.assertEqual(devis.supplement.cents, 0)
        self.assertEqual(devis.supplement.flips, 0)

    def test_couts_mesures_incomplets_refuses(self):
        with self.assertRaises(ProfileError):
            duplex.OperatorCosts(
                id="menteur", version="1.0.0", flip_seconds=None, realign_seconds=1.0,
                check_seconds=1.0, hourly_rate_cents=1, spoilage_rate=0.0,
                measured=True, provenance="prétend être mesuré sans tout connaître")


class TestDevisClient(unittest.TestCase):
    def test_devis_client_sans_formule_ni_cout_interne(self):
        couts = duplex.hypothesis_costs(20.0, 15.0, 10.0, 2500, 0.03)
        devis = duplex.estimate(5, duplex.Sides.RECTO_VERSO, couts).as_client_dict()
        texte = repr(devis)
        for interdit in ("ceil(", "formule", "taux_horaire", "secondes",
                         "main_doeuvre", "rebut"):
            self.assertNotIn(interdit, texte, f"{interdit} ne doit pas fuiter au client")
        self.assertIn("deux pages par feuille", devis["explication_feuilles"])
        self.assertFalse(devis["total_confirme"])

    def test_derniere_feuille_impaire_annoncee(self):
        devis = duplex.estimate(5, duplex.Sides.RECTO_VERSO).as_client_dict()
        self.assertEqual(devis["feuilles"], 3)
        self.assertIn("dernière", devis["explication_feuilles"])


if __name__ == "__main__":
    unittest.main()
