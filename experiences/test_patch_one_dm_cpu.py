#!/usr/bin/env python3
"""Tests du correctif de démarrage mono-processus One-DM.

Bibliothèque standard, aucun accès réseau, aucun poids, aucune inférence.

Deux familles de tests :

- ceux qui n'ont besoin de rien (en-tête du correctif, refus d'une version
  divergente sur un dépôt fabriqué, absence de réseau dans l'applicateur) ;
- ceux qui ont besoin d'un clone amont au commit exact. Ils sont **ignorés**
  avec un message explicite si le clone est absent — jamais contournés par un
  faux dépôt qui simulerait une réussite.

    python3 experiences/test_patch_one_dm_cpu.py
    ONE_DM_CLONE=/chemin/vers/one-dm python3 experiences/test_patch_one_dm_cpu.py
"""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import appliquer_patch_one_dm_cpu as app  # noqa: E402

RACINE = Path(__file__).resolve().parent
PATCH = RACINE / "one-dm-cpu-monoprocessus.patch"
CLONE = Path(os.environ.get("ONE_DM_CLONE", "/home/user/dailenson/one-dm"))

MOTIF_ABSENT = (
    f"clone amont absent de {CLONE} — le cloner au commit "
    f"{app.COMMIT_ATTENDU[:12]}… ou définir ONE_DM_CLONE"
)


def clone_utilisable() -> bool:
    if not (CLONE / ".git").is_dir():
        return False
    tete = subprocess.run(["git", "-C", str(CLONE), "rev-parse", "HEAD"],
                          capture_output=True, text=True)
    return tete.stdout.strip() == app.COMMIT_ATTENDU


def copie_du_clone(dossier: Path) -> Path:
    cible = dossier / "one-dm"
    shutil.copytree(CLONE, cible)
    return cible


def depot_fabrique(dossier: Path, contenu: str = "print('autre version')\n") -> Path:
    """Dépôt git minimal, volontairement à un autre commit que celui ciblé."""
    depot = dossier / "faux-depot"
    depot.mkdir()
    (depot / "test.py").write_text(contenu, encoding="utf-8")
    for args in (["init", "-q"], ["add", "test.py"],
                 ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"]):
        subprocess.run(["git", "-C", str(depot), *args], check=True,
                       capture_output=True)
    return depot


def extraire_fonction(chemin: Path, nom: str) -> str | None:
    """Renvoie le source de la seule fonction voulue, par analyse syntaxique."""
    source = chemin.read_text(encoding="utf-8")
    for noeud in ast.parse(source).body:
        if isinstance(noeud, ast.FunctionDef) and noeud.name == nom:
            return ast.get_source_segment(source, noeud)
    return None


# --- Doublures de simulation (aucune n'est torch) ----------------------------

class FauxCuda:
    def __init__(self, journal: list) -> None:
        self.journal = journal

    def set_device(self, rang) -> None:
        self.journal.append(("torch.cuda.set_device", rang))


class FauxTorch:
    def __init__(self) -> None:
        self.journal: list = []
        self.cuda = FauxCuda(self.journal)


class FauxDist:
    def __init__(self, journal: list, rang: int = 2, monde: int = 4) -> None:
        self.journal, self._rang, self._monde = journal, rang, monde

    def init_process_group(self, backend=None, **_kw) -> None:
        self.journal.append(("dist.init_process_group", backend))

    def get_rank(self) -> int:
        self.journal.append(("dist.get_rank", None))
        return self._rang

    def get_world_size(self) -> int:
        self.journal.append(("dist.get_world_size", None))
        return self._monde


class TestCorrectif(unittest.TestCase):
    def test_entete_cible_le_commit_et_le_blob_exacts(self):
        texte = PATCH.read_text(encoding="utf-8")
        self.assertIn(app.COMMIT_ATTENDU, texte)
        self.assertIn(app.BLOB_ATTENDU, texte)
        self.assertIn("MIT", texte, "attribution de licence attendue")
        self.assertIn("Gang Dai", texte, "paternité du code amont attendue")
        self.assertIn("--- a/test.py", texte)

    def test_correctif_ne_touche_que_test_py(self):
        cibles = [l for l in PATCH.read_text(encoding="utf-8").splitlines()
                  if l.startswith("+++ b/")]
        self.assertEqual(cibles, ["+++ b/test.py"])


class TestRefus(unittest.TestCase):
    def test_version_divergente_refusee_sans_modification(self):
        with tempfile.TemporaryDirectory() as tmp:
            depot = depot_fabrique(Path(tmp))
            cible = depot / "test.py"
            avant = cible.read_bytes()
            code = app.main(["--clone", str(depot), "--patch", str(PATCH), "--appliquer"])
            self.assertEqual(code, 1, "une autre version doit être refusée")
            self.assertEqual(cible.read_bytes(), avant, "aucun octet ne doit changer")
            propre = subprocess.run(["git", "-C", str(depot), "status", "--porcelain"],
                                    capture_output=True, text=True).stdout
            self.assertEqual(propre.strip(), "", "le dépôt doit rester propre")

    def test_chemin_inexistant_refuse(self):
        self.assertEqual(app.main(["--clone", "/inexistant/one-dm",
                                   "--patch", str(PATCH)]), 1)

    @unittest.skipUnless(clone_utilisable(), MOTIF_ABSENT)
    def test_clone_sale_refuse_sans_modification(self):
        with tempfile.TemporaryDirectory() as tmp:
            copie = copie_du_clone(Path(tmp))
            (copie / "README.md").write_text("modifié\n", encoding="utf-8")
            cible = copie / app.FICHIER_VISE
            avant = cible.read_bytes()
            code = app.main(["--clone", str(copie), "--patch", str(PATCH), "--appliquer"])
            self.assertEqual(code, 1, "un clone modifié doit être refusé")
            self.assertEqual(cible.read_bytes(), avant)

    @unittest.skipUnless(clone_utilisable(), MOTIF_ABSENT)
    def test_verification_seule_n_ecrit_rien(self):
        with tempfile.TemporaryDirectory() as tmp:
            copie = copie_du_clone(Path(tmp))
            avant = (copie / app.FICHIER_VISE).read_bytes()
            self.assertEqual(app.main(["--clone", str(copie), "--patch", str(PATCH)]), 0)
            self.assertEqual((copie / app.FICHIER_VISE).read_bytes(), avant)


class TestApplication(unittest.TestCase):
    @unittest.skipUnless(clone_utilisable(), MOTIF_ABSENT)
    def test_applicable_au_commit_exact(self):
        with tempfile.TemporaryDirectory() as tmp:
            copie = copie_du_clone(Path(tmp))
            cible = copie / app.FICHIER_VISE
            avant = cible.read_text(encoding="utf-8")
            code = app.main(["--clone", str(copie), "--patch", str(PATCH), "--appliquer"])
            self.assertEqual(code, 0)
            apres = cible.read_text(encoding="utf-8")
            self.assertNotEqual(apres, avant)
            self.assertIn(app.MARQUEUR, apres)
            # les trois appels inconditionnels d'origine ont disparu de main()
            self.assertNotIn("    dist.init_process_group(backend='nccl')", apres)
            self.assertNotIn("    torch.cuda.set_device(local_rank)", apres)
            self.assertNotIn("totol_process = dist.get_world_size()", apres)
            # syntaxiquement valide, sans import ni exécution du dépôt amont
            compile(apres, str(cible), "exec")


class TestLogiqueDeDemarrage(unittest.TestCase):
    """SIMULATION — la fonction ajoutée par le correctif est extraite du fichier
    corrigé puis exécutée seule, avec des doublures à la place de torch et de
    torch.distributed. Rien du dépôt amont n'est importé ni exécuté, et rien ici
    ne démontre qu'une inférence fonctionne."""

    @classmethod
    def setUpClass(cls):
        cls.fonction = None
        if not clone_utilisable():
            return
        cls._tmp = tempfile.TemporaryDirectory()
        copie = copie_du_clone(Path(cls._tmp.name))
        if app.main(["--clone", str(copie), "--patch", str(PATCH), "--appliquer"]) != 0:
            return
        extrait = extraire_fonction(copie / app.FICHIER_VISE, app.MARQUEUR)
        if extrait is None:
            return
        espace: dict = {}
        exec(compile(extrait, "<simulation>", "exec"), espace)  # noqa: S102
        # staticmethod : sinon l'accès par self passerait self en 1er argument
        cls.fonction = staticmethod(espace[app.MARQUEUR])

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "_tmp"):
            cls._tmp.cleanup()

    def setUp(self):
        if self.fonction is None:
            self.skipTest(MOTIF_ABSENT)
        self.journal: list = []
        self.torch = FauxTorch()
        self.torch.journal = self.journal
        self.torch.cuda.journal = self.journal
        self.dist = FauxDist(self.journal)

    def test_monoprocessus_ne_demande_ni_nccl_ni_cuda(self):
        for device, environ in (("cpu", {}),
                                ("cpu", {"WORLD_SIZE": "4"}),
                                ("mps", {"WORLD_SIZE": "4"}),
                                ("cuda", {})):
            with self.subTest(device=device, environ=environ):
                self.journal.clear()
                rang, monde, distribue = self.fonction(device, self.torch, self.dist, environ)
                self.assertEqual((rang, monde, distribue), (0, 1, False))
                self.assertEqual(self.journal, [],
                                 "aucun appel NCCL ni CUDA ne doit avoir lieu")

    def test_voie_cuda_distribuee_conservee(self):
        rang, monde, distribue = self.fonction(
            "cuda", self.torch, self.dist, {"WORLD_SIZE": "4"})
        self.assertEqual((rang, monde, distribue), (2, 4, True))
        self.assertIn(("dist.init_process_group", "nccl"), self.journal)
        self.assertIn(("torch.cuda.set_device", 2), self.journal)
        self.assertLess(self.journal.index(("dist.init_process_group", "nccl")),
                        self.journal.index(("torch.cuda.set_device", 2)))

    def test_decoupe_du_corpus_inchangee_en_monoprocessus(self):
        """Avec un seul processus, tout le corpus est traité (aucun texte perdu)."""
        textes = [f"mot{i}" for i in range(7)]
        _rang, monde, _ = self.fonction("cpu", self.torch, self.dist, {})
        chacun = len(textes) // monde
        if len(textes) % monde:
            chacun += 1
        self.assertEqual(textes[0 * chacun:1 * chacun], textes)


class TestApplicateurSansReseau(unittest.TestCase):
    INTERDITS = {"socket", "ssl", "urllib", "urllib3", "http", "requests",
                 "ftplib", "telnetlib", "asyncio", "webbrowser", "serial"}

    def test_aucun_module_reseau_importe(self):
        arbre = ast.parse(Path(app.__file__).read_text(encoding="utf-8"))
        for noeud in ast.walk(arbre):
            if isinstance(noeud, ast.Import):
                noms = [a.name.split(".")[0] for a in noeud.names]
            elif isinstance(noeud, ast.ImportFrom) and noeud.level == 0:
                noms = [(noeud.module or "").split(".")[0]]
            else:
                continue
            for nom in noms:
                self.assertNotIn(nom, self.INTERDITS)

    def test_seules_des_commandes_git_sont_lancees(self):
        source = Path(app.__file__).read_text(encoding="utf-8")
        arbre = ast.parse(source)
        lancements = [n for n in ast.walk(arbre)
                      if isinstance(n, ast.Call)
                      and isinstance(n.func, ast.Attribute) and n.func.attr == "run"]
        self.assertTrue(lancements, "au moins un appel subprocess.run attendu")
        for appel in lancements:
            premier = appel.args[0]
            self.assertIsInstance(premier, ast.List)
            self.assertIsInstance(premier.elts[0], ast.Constant)
            self.assertEqual(premier.elts[0].value, "git")


if __name__ == "__main__":
    unittest.main(verbosity=2)
