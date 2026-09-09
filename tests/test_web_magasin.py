"""Magasin local : métadonnées serveur, transitions déterministes, artefacts figés."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from paperx_web import store as store_mod, uploads
from paperx_web.store import Store, StoreError
from tests.aide_web import png


class BaseMagasin(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.racine = Path(self._tmp.name)
        self.store = Store(self.racine)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def depose(self, data: bytes | None = None) -> dict:
        data = data if data is not None else png(400, 500)
        return self.store.save_sample(data, uploads.check(data), "test")


class TestEchantillons(BaseMagasin):
    def test_metadonnees_relues_du_disque(self):
        meta = self.depose()
        relu = self.store.get_sample(meta["id"])
        self.assertEqual(relu["sha256"], meta["sha256"])
        self.assertEqual((relu["largeur_px"], relu["hauteur_px"]), (400, 500))

    def test_identifiant_inconnu_refuse(self):
        with self.assertRaises(StoreError):
            self.store.get_sample("a" * 32)

    def test_identifiant_malforme_refuse(self):
        for mauvais in ("../../etc/passwd", "zz", "A" * 32):
            with self.subTest(valeur=mauvais):
                with self.assertRaises(StoreError):
                    self.store.get_sample(mauvais)

    def test_fichier_absent_refuse(self):
        meta = self.depose()
        self.store.sample_path(meta["nom_stockage"]).unlink()
        with self.assertRaises(StoreError):
            self.store.get_sample(meta["id"])

    def test_fichier_altere_refuse(self):
        meta = self.depose()
        chemin = self.store.sample_path(meta["nom_stockage"])
        chemin.write_bytes(chemin.read_bytes() + b"altere")
        with self.assertRaises(StoreError):
            self.store.get_sample(meta["id"])

    def test_echantillon_refuse_nest_pas_enregistre(self):
        mauvais = b"pas une image"
        with self.assertRaises(StoreError):
            self.store.save_sample(mauvais, uploads.check(mauvais), "test")
        self.assertEqual(list(self.store.samples_dir.glob("*")), [])

    def test_purge_des_depots_abandonnes(self):
        garde = self.depose()
        abandonne = self.depose(png(420, 520))
        self.store.attach_sample(garde["id"], "0" * 32)

        chemin = self.store.samples_dir / f"{abandonne['id']}.json"
        meta = json.loads(chemin.read_text(encoding="utf-8"))
        meta["depose_le"] = "2020-01-01T00:00:00+00:00"
        chemin.write_text(json.dumps(meta), encoding="utf-8")

        purges = self.store.purge_orphan_samples()
        self.assertEqual(purges, [abandonne["id"]])
        self.assertFalse(self.store.sample_path(abandonne["nom_stockage"]).exists())
        self.assertTrue(self.store.sample_path(garde["nom_stockage"]).exists())

    def test_depot_recent_non_purge(self):
        recent = self.depose()
        self.assertEqual(self.store.purge_orphan_samples(), [])
        self.assertTrue(self.store.sample_path(recent["nom_stockage"]).exists())


class TestTransitions(BaseMagasin):
    def test_attente_ne_sort_que_par_annulation(self):
        autorisees = store_mod.allowed_transitions(store_mod.ETAT_ATTENTE_RETOURNEMENT)
        self.assertEqual(autorisees, frozenset({store_mod.ETAT_ANNULEE}))

    def test_personnalisation_bloquee(self):
        autorisees = store_mod.allowed_transitions(store_mod.ETAT_ATTENTE_PERSONNALISATION)
        self.assertEqual(autorisees, frozenset({store_mod.ETAT_ANNULEE}))

    def test_annulation_terminale(self):
        self.assertEqual(store_mod.allowed_transitions(store_mod.ETAT_ANNULEE), frozenset())

    def test_table_complete_et_close(self):
        for etat in store_mod.ETATS:
            self.assertIn(etat, store_mod.TRANSITIONS)
            for cible in store_mod.TRANSITIONS[etat]:
                self.assertIn(cible, store_mod.ETATS)


class TestArtefactsFiges(BaseMagasin):
    def test_relecture_verifie_lempreinte(self):
        record = self.store.create_order({"etat": store_mod.ETAT_PRETE_REVUE})
        fiche = self.store.save_artifact(record["id"], "client", b"contenu fige")
        self.assertEqual(
            self.store.read_artifact(record["id"], "client", fiche["sha256"]),
            b"contenu fige")

        chemin = self.store.artifacts_dir / f"{record['id']}-client.zip"
        chemin.write_bytes(b"contenu modifie")
        with self.assertRaises(StoreError):
            self.store.read_artifact(record["id"], "client", fiche["sha256"])

    def test_variante_inconnue_refusee(self):
        record = self.store.create_order({"etat": store_mod.ETAT_PRETE_REVUE})
        with self.assertRaises(StoreError):
            self.store.save_artifact(record["id"], "../evasion", b"x")


class TestVues(BaseMagasin):
    RECORD = {
        "id": "0" * 32, "etat": store_mod.ETAT_ATTENTE_RETOURNEMENT,
        "faces": 4, "feuilles": 2, "caracteres": 120,
        "texte": "secret client", "texte_sha256": "abc",
        "devis_client": {"total_centimes": None},
        "devis_operateur": {"supplement": {"detail": {"main_doeuvre_centimes": 12}}},
        "couts_operateur": {"taux_horaire_centimes": 2500},
        "simulation": {"cumul": {"temps_total_s": 42}},
        "etapes_manuelles": [{"index": 0, "apres_page": 1, "feuille": 1,
                              "confirme": False, "type": "retournement_recalage"}],
    }

    def test_vue_client_sans_donnees_internes(self):
        vue = store_mod.client_view(self.RECORD)
        texte = repr(vue)
        for interdit in ("taux_horaire", "main_doeuvre", "temps_total_s",
                         "secret client", "devis_operateur", "couts_operateur"):
            self.assertNotIn(interdit, texte)
        self.assertEqual(vue["suivi"], store_mod.ETAT_CLIENT[
            store_mod.ETAT_ATTENTE_RETOURNEMENT])
        self.assertTrue(vue["en_pause"])

    def test_vue_operateur_complete(self):
        vue = store_mod.operator_view(self.RECORD)
        self.assertIn("couts_operateur", vue)
        self.assertIn("devis_operateur", vue)
        self.assertTrue(vue["confirmation_possible"])
        self.assertEqual(vue["transitions_autorisees"], [store_mod.ETAT_ANNULEE])

    def test_le_texte_client_ne_sort_dans_aucune_vue(self):
        for vue in (store_mod.client_view(self.RECORD),
                    store_mod.operator_view(self.RECORD)):
            self.assertNotIn("secret client", repr(vue))


if __name__ == "__main__":
    unittest.main()
