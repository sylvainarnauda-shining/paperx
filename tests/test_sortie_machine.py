"""Aucune sortie machine : ni G-code exécutable, ni accès imprimante."""

from __future__ import annotations

import ast
import pathlib
import unittest

from paperx import emit, gate, machine, paper, strokes, validator
from paperx.errors import CalibrationRequired

PAQUET = pathlib.Path("paperx")

#: Modules qui ouvriraient un accès machine, réseau ou processus.
MODULES_INTERDITS = {
    "socket", "ssl", "serial", "pyserial", "usb", "http", "httplib", "urllib",
    "urllib3", "requests", "ftplib", "telnetlib", "smtplib", "asyncio",
    "subprocess", "multiprocessing", "ctypes", "webbrowser", "xmlrpc",
}


def _trajectoire():
    return strokes.PageTrajectory(
        1, (strokes.Stroke(((50.0, 100.0), (51.0, 101.0)), 20.0, None, None),), (),
        paper.DEMO_A4.ref(), "synthetic-generic@1.0.0", strokes.DEMO_SPEEDS.ref())


class TestRefusSortieMachine(unittest.TestCase):
    def test_verrou_global_ferme(self):
        self.assertFalse(gate.MACHINE_OUTPUT_AVAILABLE)

    def test_sortie_refusee_sur_profil_non_calibre(self):
        traj = _trajectoire()
        report = validator.validate_page(traj, paper.DEMO_A4, machine.P1S_UNCALIBRATED,
                                         strokes.DEMO_SPEEDS)
        with self.assertRaises(CalibrationRequired) as ctx:
            emit.machine_output(traj, machine.P1S_UNCALIBRATED, report)
        message = str(ctx.exception)
        self.assertIn("non calibré", message)
        self.assertIn("chaîne non validée", message)

    def test_fiche_de_revue_non_executable(self):
        traj = _trajectoire()
        report = validator.validate_page(traj, paper.DEMO_A4, machine.P1S_UNCALIBRATED,
                                         strokes.DEMO_SPEEDS)
        fiche = emit.review_sheet(traj, machine.P1S_UNCALIBRATED, report)
        self.assertTrue(fiche.startswith(emit.NON_EXECUTABLE_HEADER))
        for commande in ("G0 ", "G1 ", "G28", "M104", "M106", "G21", "G90"):
            self.assertNotIn(commande, fiche)


class TestAucunGcodeNiAccesMachine(unittest.TestCase):
    def _sources(self):
        return sorted(PAQUET.glob("*.py"))

    def test_aucun_module_reseau_ou_serie_importe(self):
        for chemin in self._sources():
            arbre = ast.parse(chemin.read_text(encoding="utf-8"))
            for noeud in ast.walk(arbre):
                if isinstance(noeud, ast.Import):
                    noms = [a.name.split(".")[0] for a in noeud.names]
                elif isinstance(noeud, ast.ImportFrom):
                    noms = [(noeud.module or "").split(".")[0]] if noeud.level == 0 else []
                else:
                    continue
                for nom in noms:
                    self.assertNotIn(nom, MODULES_INTERDITS,
                                     f"{chemin} importe {nom}")

    def test_aucune_commande_gcode_dans_le_paquet(self):
        motifs = ("G0 X", "G1 X", "G28", "M104 S", "M106 S", "G92 E")
        for chemin in self._sources():
            contenu = chemin.read_text(encoding="utf-8")
            for motif in motifs:
                self.assertNotIn(motif, contenu, f"{chemin} contient {motif!r}")

    def test_paquet_en_bibliotheque_standard_uniquement(self):
        import sys

        autorises = set(sys.stdlib_module_names) | {"paperx"}
        for chemin in self._sources():
            arbre = ast.parse(chemin.read_text(encoding="utf-8"))
            for noeud in ast.walk(arbre):
                if isinstance(noeud, ast.Import):
                    for alias in noeud.names:
                        self.assertIn(alias.name.split(".")[0], autorises)
                elif isinstance(noeud, ast.ImportFrom) and noeud.level == 0:
                    self.assertIn((noeud.module or "").split(".")[0], autorises)


if __name__ == "__main__":
    unittest.main()
