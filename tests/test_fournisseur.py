"""Contrat du futur fournisseur de personnalisation.

Aucun modèle n'est exécuté. On vérifie que le contrat refuse ce qu'il doit
refuser, en particulier la confusion photo de papier vierge / échantillon
manuscrit client.
"""

from __future__ import annotations

import unittest

from paperx import provider, synthetic_hand
from paperx.errors import InvalidSampleKind, PersonalizationUnavailable


class FournisseurMenteur(provider.PersonalizationProvider):
    """Fournisseur non conforme : sert de témoin négatif au contrôle."""

    def capabilities(self) -> provider.Capabilities:
        return provider.Capabilities(
            provider_id="menteur", version="0.1.0", is_personalized=True,
            supported_chars=frozenset("abc"),
            requires_sample_kinds=frozenset({provider.SampleKind.PHOTO_PAPIER_VIERGE}),
            licence_ref="inconnue", licence_verified=False,
            weights_ref="poids-inconnus.bin", executed_locally=True,
            notes="prétend personnaliser depuis une photo de papier vierge")

    def build_hand(self, sample: provider.Sample) -> provider.Hand:
        return provider.Hand("menteur", "0.1.0", True, "photo de papier vierge", {})


class TestFournisseurParDefaut(unittest.TestCase):
    def test_conforme_au_contrat(self):
        self.assertEqual(provider.check_conformance(provider.DEFAULT_PROVIDER), ())

    def test_refuse_explicitement_la_personnalisation(self):
        echantillon = provider.Sample(
            provider.SampleKind.ECHANTILLON_MANUSCRIT_CLIENT, "ref:hors-depot")
        with self.assertRaises(PersonalizationUnavailable):
            provider.DEFAULT_PROVIDER.build_hand(echantillon)

    def test_photo_papier_vierge_refusee(self):
        photo = provider.Sample(provider.SampleKind.PHOTO_PAPIER_VIERGE, "ref:feuille")
        with self.assertRaises(InvalidSampleKind):
            provider.DEFAULT_PROVIDER.build_hand(photo)

    def test_gabarit_synthetique_ne_personnalise_pas(self):
        gabarit = provider.Sample(
            provider.SampleKind.ECRITURE_GENERIQUE_SYNTHETIQUE, "ref:gabarit")
        with self.assertRaises(PersonalizationUnavailable):
            provider.DEFAULT_PROVIDER.build_hand(gabarit)

    def test_aucun_poids_ni_licence_non_verifiee(self):
        caps = provider.DEFAULT_PROVIDER.capabilities()
        self.assertIsNone(caps.weights_ref)
        self.assertTrue(caps.licence_verified)
        self.assertFalse(caps.executed_locally)
        self.assertFalse(caps.is_personalized)


class FournisseurGeneriqueDeguise(provider.PersonalizationProvider):
    """Déclare accepter CLIENT et GENERIQUE, puis revendique une personnalisation
    à partir du gabarit générique. Témoin négatif de la règle R5."""

    def capabilities(self) -> provider.Capabilities:
        return provider.Capabilities(
            provider_id="generique-deguise", version="1.0.0", is_personalized=True,
            supported_chars=frozenset("abc"),
            requires_sample_kinds=frozenset({
                provider.SampleKind.ECHANTILLON_MANUSCRIT_CLIENT,
                provider.SampleKind.ECRITURE_GENERIQUE_SYNTHETIQUE}),
            licence_ref="MIT", licence_verified=True, weights_ref=None,
            executed_locally=True, notes="témoin négatif")

    def build_hand(self, sample: provider.Sample) -> provider.Hand:
        if sample.kind is provider.SampleKind.PHOTO_PAPIER_VIERGE:
            raise InvalidSampleKind("photo de papier vierge refusée")
        return provider.Hand("generique-deguise", "1.0.0", True, "gabarit générique", {})


class TestControleDeConformite(unittest.TestCase):
    def test_detecte_un_fournisseur_non_conforme(self):
        manquements = provider.check_conformance(FournisseurMenteur())
        self.assertTrue(manquements)
        codes = " ".join(manquements)
        self.assertIn("R2", codes)   # personnalisation sans échantillon manuscrit
        self.assertIn("R3", codes)   # photo de papier vierge acceptée
        self.assertIn("R7", codes)   # poids sans licence vérifiée

    def test_regression_gabarit_generique_declare_accepte(self):
        """Revue : R5 ne se déclenchait que sur un type NON déclaré."""
        manquements = provider.check_conformance(FournisseurGeneriqueDeguise())
        self.assertTrue(any(m.startswith("R5") for m in manquements), manquements)

    def test_couverture_manquante_signalee(self):
        caps = FournisseurMenteur().capabilities()
        self.assertEqual(caps.missing_for("abcé"), ("é",))


class TestEcritureGeneriqueEtiquetee(unittest.TestCase):
    def test_declaree_non_personnalisee(self):
        self.assertFalse(synthetic_hand.IS_PERSONALIZED)
        self.assertIn("GÉNÉRIQUE SYNTHÉTIQUE", synthetic_hand.HAND_LABEL)
        self.assertIn("Aucune photo", synthetic_hand.HAND_PROVENANCE)


if __name__ == "__main__":
    unittest.main()
