"""Une création refusée ne laisse ni commande ni dossier, et conserve la photo."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from paperx_web import http_app, uploads
from paperx_web.store import Store, StoreError
from tests.aide_web import png


class TestCreationAtomique(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(self.tmp.name)
        self.app = http_app.App(self.store, '127.0.0.1', 9999)
        data = png(400, 500)
        self.sample = self.store.save_sample(data, uploads.check(data), 'test')
        self.payload = {'texte': 'Bonjour é\r\n', 'mode_ecriture': 'personnalise',
                        'echantillon': {'id': self.sample['id']}}

    def snapshot(self):
        return {str(p.relative_to(self.store.root)): p.read_bytes()
                for p in self.store.root.rglob('*') if p.is_file()}

    def test_reutilisation_refusee_sans_commande_ni_archive_supplementaire(self):
        http_app.route_creer_commande(self.app, self.payload)
        before = self.snapshot()
        with self.assertRaises(StoreError):
            http_app.route_creer_commande(self.app, self.payload)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(len(self.store.list_orders()), 1)
        self.assertEqual(len(list(self.store.root.rglob('*.zip'))), 2)
        self.store.get_sample(self.sample['id'])

    def test_echec_deuxieme_archive_nettoie_et_conserve_photo(self):
        before = self.snapshot()
        original = self.store.save_artifact
        def fail_second(order_id, variant, content):
            if variant == 'operateur':
                raise OSError('échec disque simulé')
            return original(order_id, variant, content)
        with patch.object(self.store, 'save_artifact', side_effect=fail_second):
            with self.assertRaises(OSError):
                http_app.route_creer_commande(self.app, self.payload)
        self.assertEqual(before, self.snapshot())

    def test_echec_apres_rattachement_detache_sans_effacer_photo(self):
        before = self.snapshot()
        original = self.store.attach_sample
        def attach_then_fail(sample_id, order_id):
            original(sample_id, order_id)
            raise StoreError('échec après rattachement simulé')
        with patch.object(self.store, 'attach_sample', side_effect=attach_then_fail):
            with self.assertRaises(StoreError):
                http_app.route_creer_commande(self.app, self.payload)
        self.assertEqual(before, self.snapshot())


if __name__ == '__main__':
    unittest.main()
