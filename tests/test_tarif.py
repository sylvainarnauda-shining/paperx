"""Prix cible immuable, remise à définir, aucun paiement réel."""

from __future__ import annotations

import unittest

from paperx import pricing
from paperx.errors import PaperxError


class TestTarif(unittest.TestCase):
    def test_prix_cible_immuable(self):
        self.assertEqual(pricing.PRICE_PER_A4_CENTS, 100)
        self.assertEqual(pricing.SERVICE_AREA, "Montpellier centre")

    def test_devis_lineaire_et_non_engageant(self):
        for pages in (0, 1, 2, 37):
            devis = pricing.quote(pages)
            self.assertEqual(devis.total_cents, 100 * pages)
            self.assertFalse(devis.binding)
            self.assertIsNone(devis.discount_applied)
            self.assertEqual(devis.as_dict()["remise"], "à définir")

    def test_remise_non_definie_refusee(self):
        self.assertIsNone(pricing.DISCOUNT)
        with self.assertRaises(pricing.DiscountUndefined):
            pricing.apply_discount(10)

    def test_aucun_paiement(self):
        self.assertFalse(pricing.PAYMENT_ENABLED)
        with self.assertRaises(pricing.PaymentDisabled):
            pricing.charge(100)

    def test_entrees_invalides(self):
        for mauvais in (-1, 1.5, "2", True, None):
            with self.subTest(valeur=mauvais):
                with self.assertRaises(PaperxError):
                    pricing.quote(mauvais)


if __name__ == "__main__":
    unittest.main()
