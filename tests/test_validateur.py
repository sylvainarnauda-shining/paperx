"""Validateur : refus déterministes, aucun plantage, aucun NaN dans le rapport."""

from __future__ import annotations

import dataclasses as dc
import json
import math
import unittest

from paperx import gate, machine, paper, strokes, validator
from paperx.errors import ProfileError

P = paper.DEMO_A4
HAND = "synthetic-generic@1.0.0"


def traj(*strokes_):
    return strokes.PageTrajectory(1, tuple(strokes_), (), P.ref(), HAND,
                                  strokes.DEMO_SPEEDS.ref())


def bon_trait():
    return strokes.Stroke(((50.0, 100.0), (51.0, 101.0)), 20.0, None, None)


def valide(t, p=P, m=machine.P1S_UNCALIBRATED, s=strokes.DEMO_SPEEDS):
    return validator.validate_page(t, p, m, s)


class TestProfilsNumeriques(unittest.TestCase):
    """Régression de revue : NaN/inf dans un profil rendaient la page « prête »."""

    def test_profil_machine_nan_refuse_a_la_construction(self):
        with self.assertRaises(ProfileError):
            dc.replace(machine.P1S_UNCALIBRATED, calibrated=True,
                       pen_z_height_mm=float("nan"), z_offset_mm=float("inf"),
                       placement=machine.Placement(0.0, 0.0, True, "test"))

    def test_profil_machine_nan_force_refuse_par_le_validateur(self):
        m = dc.replace(machine.P1S_UNCALIBRATED)
        object.__setattr__(m, "calibrated", True)
        object.__setattr__(m, "pen_z_height_mm", float("nan"))
        object.__setattr__(m, "z_offset_mm", float("inf"))
        object.__setattr__(m, "placement", machine.Placement(0.0, 0.0, True, "test"))
        report = valide(traj(bon_trait()), m=m)
        self.assertFalse(report.machine_ready)
        self.assertFalse(report.trajectory_valid)
        self.assertIn("PROFIL_NUMERIQUE_INVALIDE", report.codes())

    def test_vitesses_nan_refusees(self):
        with self.assertRaises(ProfileError):
            dc.replace(strokes.DEMO_SPEEDS, travel_speed_mm_s=float("nan"))
        s = dc.replace(strokes.DEMO_SPEEDS)
        object.__setattr__(s, "travel_speed_mm_s", float("nan"))
        report = validator.validate_page(
            dc.replace(traj(bon_trait()), speed_ref=s.ref()), P,
            machine.P1S_UNCALIBRATED, s)
        self.assertFalse(report.trajectory_valid)
        self.assertIn("PROFIL_NUMERIQUE_INVALIDE", report.codes())

    def test_papier_et_vitesses_non_mesures_bloquent(self):
        report = valide(traj(bon_trait()))
        self.assertIn("PAPIER_NON_MESURE", report.blocking_codes())
        self.assertIn("VITESSES_NON_MESUREES", report.blocking_codes())

    def test_limites_incoherentes_refusees(self):
        with self.assertRaises(ProfileError):
            dc.replace(validator.DEFAULT_LIMITS, max_segment_len_mm=float("inf"))
        with self.assertRaises(ProfileError):
            dc.replace(validator.DEFAULT_LIMITS, min_segment_len_mm=99.0)


class TestTrajectoiresMalformees(unittest.TestCase):
    def test_trait_vide_puis_trait_valide_ne_plante_pas(self):
        """Régression de revue : IndexError dans travel_length_mm."""
        report = valide(traj(strokes.Stroke((), 20.0, None, None), bon_trait()))
        self.assertFalse(report.trajectory_valid)
        self.assertIn("TRAIT_DEGENERE", report.codes())

    def test_nan_et_inf_dans_les_points(self):
        for mauvais in (float("nan"), float("inf"), -float("inf")):
            with self.subTest(valeur=mauvais):
                report = valide(traj(strokes.Stroke(
                    ((50.0, 100.0), (mauvais, 101.0)), 20.0, None, None)))
                self.assertFalse(report.trajectory_valid)
                self.assertIn("COORDONNEE_NON_FINIE", report.codes())

    def test_coordonnees_enormes_finies(self):
        """Régression de revue : débordement de calcul de longueur."""
        report = valide(traj(strokes.Stroke(
            ((1e308, 1e308), (-1e308, -1e308)), 20.0, None, None)))
        self.assertFalse(report.trajectory_valid)
        self.assertIn("COORDONNEE_HORS_DOMAINE", report.codes())
        for cle, valeur in report.stats.items():
            if isinstance(valeur, float):
                self.assertTrue(math.isfinite(valeur), f"{cle} non fini")

    def test_point_malforme_ou_non_numerique(self):
        arite = valide(traj(strokes.Stroke(((1.0, 2.0, 3.0), (3.0, 4.0)), 20.0, None, None)))
        self.assertFalse(arite.trajectory_valid)
        self.assertIn("POINT_MALFORME", arite.codes())
        texte = valide(traj(strokes.Stroke((("a", 2.0), (3.0, 4.0)), 20.0, None, None)))
        self.assertFalse(texte.trajectory_valid)
        self.assertIn("COORDONNEE_NON_FINIE", texte.codes())

    def test_hors_page_et_hors_marges(self):
        hors_page = valide(traj(strokes.Stroke(((-5.0, 10.0), (5.0, 10.0)), 20.0, None, None)))
        self.assertIn("HORS_PAGE", hors_page.codes())
        hors_marges = valide(traj(strokes.Stroke(((5.0, 100.0), (6.0, 101.0)), 20.0, None, None)))
        self.assertIn("HORS_MARGES", hors_marges.codes())

    def test_vitesses_de_trait_hors_plafond(self):
        report = valide(traj(strokes.Stroke(((50.0, 100.0), (51.0, 101.0)),
                                            999.0, None, None)))
        self.assertIn("VITESSE_TRACE_EXCESSIVE", report.codes())
        self.assertFalse(report.trajectory_valid)
        nan_speed = valide(traj(strokes.Stroke(((50.0, 100.0), (51.0, 101.0)),
                                               float("nan"), None, None)))
        self.assertIn("VITESSE_NON_FINIE", nan_speed.codes())

    def test_levees_de_plume_comptees_et_plafonnees(self):
        t = traj(bon_trait(), bon_trait(), bon_trait())
        self.assertEqual(t.pen_lifts, 2)
        m = dc.replace(machine.P1S_UNCALIBRATED, max_pen_lifts_per_page=1)
        self.assertIn("LEVEES_EXCESSIVES", valide(t, m=m).codes())

    def test_rapport_json_strict_sans_nan(self):
        report = valide(traj(strokes.Stroke(((float("nan"), 1.0), (2.0, 3.0)),
                                            float("inf"), None, None)))
        texte = json.dumps(report.as_dict(), allow_nan=False, ensure_ascii=False)

        def interdit(constante):  # NaN / Infinity / -Infinity littéraux
            raise AssertionError(f"littéral JSON non valide : {constante}")

        json.loads(texte, parse_constant=interdit)


class TestVerrouMachine(unittest.TestCase):
    def test_profil_non_calibre_refuse(self):
        report = valide(traj(bon_trait()))
        self.assertFalse(report.machine_ready)
        for code in ("MACHINE_NON_CALIBREE", "HAUTEUR_PLUME_INCONNUE",
                     "POSE_FEUILLE_NON_MESUREE"):
            self.assertIn(code, report.blocking_codes())

    def test_aucun_profil_ne_devient_pret_meme_calibre(self):
        """Régression de revue : `calibrated=True` ne doit rien débloquer."""
        self.assertFalse(gate.MACHINE_OUTPUT_AVAILABLE)
        pose = machine.Placement(10.0, 10.0, True, "pose mesurée (fictive)")
        m = machine.MachineProfile(
            id="fictif", version="1.0.0", label="machine fictive", calibrated=True,
            work_area_x_mm=400.0, work_area_y_mm=400.0, max_draw_speed_mm_s=30.0,
            max_travel_speed_mm_s=100.0, max_pen_lifts_per_page=20000,
            pen_z_height_mm=1.0, z_offset_mm=0.0, placement=pose,
            provenance="profil de test, aucune machine réelle")
        p = dc.replace(P, id="papier-fictif-mesure", measured=True)
        s = dc.replace(strokes.DEMO_SPEEDS, id="vitesses-fictives-mesurees", measured=True)
        t = strokes.PageTrajectory(1, (bon_trait(),), (), p.ref(), HAND, s.ref())
        report = validator.validate_page(t, p, m, s)
        self.assertFalse(report.machine_ready)
        self.assertEqual(report.blocking_codes(), (gate.GATE_CODE,))

    def test_determinisme(self):
        t = traj(bon_trait(), strokes.Stroke(((60.0, 120.0), (61.0, 121.0)), 20.0, 7, "a"))
        self.assertEqual(valide(t).as_dict(), valide(t).as_dict())


if __name__ == "__main__":
    unittest.main()
