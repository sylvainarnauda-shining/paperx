"""Profil P1S non calibré ; contrainte 256x256 face à l'A4 signalée, jamais masquée."""

from __future__ import annotations

import dataclasses as dc
import unittest

from paperx import layout, machine, paper, strokes, textsource, validator
from paperx.errors import ProfileError


class TestProfilP1S(unittest.TestCase):
    def test_non_calibre_par_defaut_et_sans_valeur_inventee(self):
        m = machine.P1S_UNCALIBRATED
        self.assertFalse(m.calibrated)
        self.assertIsNone(m.pen_z_height_mm)
        self.assertIsNone(m.z_offset_mm)
        self.assertIsNone(m.placement)
        self.assertIn("NON CALIBRÉ", m.label)
        self.assertIn("@", m.ref())

    def test_aire_de_travail_nominale(self):
        self.assertEqual((machine.P1S_UNCALIBRATED.work_area_x_mm,
                          machine.P1S_UNCALIBRATED.work_area_y_mm), (256.0, 256.0))

    def test_calibre_sans_mesure_refuse(self):
        with self.assertRaises(ProfileError):
            dc.replace(machine.P1S_UNCALIBRATED, calibrated=True)
        with self.assertRaises(ProfileError):
            dc.replace(machine.P1S_UNCALIBRATED, calibrated=True, pen_z_height_mm=1.0,
                       z_offset_mm=0.0,
                       placement=machine.Placement(0.0, 0.0, False, "non mesurée"))

    def test_profil_inconnu_refuse(self):
        with self.assertRaises(ProfileError):
            machine.get("prusa-imaginaire")


class TestZonesInaccessibles(unittest.TestCase):
    def setUp(self):
        self.reach = machine.reachability(paper.DEMO_A4, machine.P1S_UNCALIBRATED)

    def test_bande_haute_hors_course_sous_hypothese(self):
        self.assertTrue(self.reach.hypothesis, "la pose n'est pas mesurée")
        self.assertFalse(self.reach.fully_reachable)
        self.assertEqual(len(self.reach.unreachable), 1)
        bande = self.reach.unreachable[0]
        # 297 mm de haut - 256 mm de course = 41 mm inaccessibles
        self.assertAlmostEqual(bande.y1 - bande.y0, 41.0, places=6)
        self.assertAlmostEqual(self.reach.unreachable_area_mm2, 210.0 * 41.0, places=3)
        self.assertGreater(self.reach.unreachable_ratio, 0.13)

    def test_aucune_mise_a_echelle(self):
        self.assertFalse(self.reach.as_dict()["mise_a_echelle_appliquee"])

    def test_caracteres_reellement_touches_sont_comptes(self):
        src = textsource.load("samples/texte_demo_fr.txt")
        result = layout.paginate(src, paper.DEMO_A4)
        traj = strokes.build_page(result, 1)
        report = validator.validate_page(traj, paper.DEMO_A4, machine.P1S_UNCALIBRATED,
                                         strokes.DEMO_SPEEDS)
        self.assertIn("ZONE_INACCESSIBLE", report.blocking_codes())
        self.assertGreater(report.stats["points_en_zone_inaccessible"], 0)
        self.assertGreater(report.stats["caracteres_en_zone_inaccessible"], 0)

    def test_machine_assez_grande_couvre_toute_la_page(self):
        grande = machine.MachineProfile(
            id="fictive-grande", version="1.0.0", label="machine fictive",
            calibrated=False, work_area_x_mm=400.0, work_area_y_mm=400.0,
            max_draw_speed_mm_s=30.0, max_travel_speed_mm_s=100.0,
            max_pen_lifts_per_page=20000, pen_z_height_mm=None, z_offset_mm=None,
            placement=None, provenance="profil de test")
        self.assertTrue(machine.reachability(paper.DEMO_A4, grande).fully_reachable)


if __name__ == "__main__":
    unittest.main()
