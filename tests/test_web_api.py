"""Parcours complet par HTTP, sur un vrai serveur local.

Ce que ces tests tiennent : le texte ressort à l'identique, le devis n'invente
rien, le dossier se télécharge et se vérifie, la sortie machine est refusée, un
dépôt invalide est refusé, la suppression efface tout, et l'espace client ne
reçoit jamais les coûts internes.
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from tests.aide_web import TEXTE_FR, ServeurLocal, png

#: Motifs qui n'ont RIEN à faire dans l'espace client.
MOTIFS_INTERNES = (
    "temps_contact", "temps_levees", "temps_manipulation", "temps_total",
    "taux_horaire", "taux_rates", "secondes_retournement", "secondes_recalage",
    "secondes_controle", "main_doeuvre", "rebut_centimes", "vitesse_trace_mm_s",
    "vitesse_deplacement_mm_s", "CHAINE_NON_VALIDEE", "MACHINE_NON_CALIBREE",
    "PAPIER_NON_MESURE", "bambu-p1s", "demo-speeds", "demo-timing", "ceil(",
)


def sans_motifs_internes(cas, charge) -> None:
    texte = charge if isinstance(charge, str) else json.dumps(charge, ensure_ascii=False)
    for motif in MOTIFS_INTERNES:
        cas.assertNotIn(motif, texte, f"fuite interne vers le client : {motif}")


class BaseAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.srv = ServeurLocal(Path(cls._tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.srv.stop()
        cls._tmp.cleanup()

    def commande_demo(self, texte: str = TEXTE_FR, mode: str = "recto") -> dict:
        statut, corps = self.srv.post("/api/commande", {
            "texte": texte, "mode_ecriture": "demo", "style": "synthetic-generic",
            "mode_impression": mode,
        })
        self.assertEqual(statut, 201, corps)
        return corps["commande"]


class TestTexteExact(BaseAPI):
    def test_unicode_preserve_a_lidentique(self):
        statut, corps = self.srv.post("/api/composer", {"texte": TEXTE_FR})
        self.assertEqual(statut, 200, corps)
        self.assertTrue(corps["texte"]["preservation_exacte"])
        self.assertEqual(corps["texte"]["caracteres"], len(TEXTE_FR))

    def test_le_dossier_rend_les_octets_exacts(self):
        commande = self.commande_demo()
        statut, contenu, _ = self.srv.get_brut(
            f"/api/commande/{commande['id']}/dossier.zip")
        self.assertEqual(statut, 200)
        archive = zipfile.ZipFile(io.BytesIO(contenu))
        self.assertEqual(archive.read("texte-source.txt").decode("utf-8"), TEXTE_FR)

    def test_caractere_absent_signale_et_conserve(self):
        texte = "Un engrenage ⚙ dans le texte.\n"
        statut, corps = self.srv.post("/api/composer", {"texte": texte})
        self.assertEqual(statut, 200, corps)
        self.assertTrue(corps["texte"]["preservation_exacte"])
        self.assertEqual([s["caractere"] for s in corps["signalements"]], ["⚙"])

    def test_texte_trop_long_refuse_jamais_tronque(self):
        statut, corps = self.srv.post("/api/composer", {"texte": "a" * 20_001})
        self.assertEqual(statut, 400)
        self.assertIn("PAS tronqué", corps["erreur"])

    def test_texte_vide_refuse(self):
        statut, corps = self.srv.post("/api/composer", {"texte": ""})
        self.assertEqual(statut, 400)


class TestDevisParHTTP(BaseAPI):
    def test_recto_verso_feuilles_et_supplement_inconnu(self):
        statut, corps = self.srv.post("/api/composer", {
            "texte": TEXTE_FR * 12, "mode_impression": "recto_verso"})
        self.assertEqual(statut, 200, corps)
        devis = corps["devis"]
        self.assertEqual(devis["feuilles"], -(-devis["pages_ecrites"] // 2))
        self.assertEqual(devis["sous_total_centimes"], 100 * devis["pages_ecrites"])
        self.assertIsNone(devis["supplement_retournement_centimes"])
        self.assertIsNone(devis["total_centimes"])
        self.assertFalse(devis["total_confirme"])

    def test_couts_operateur_ignores_cote_client(self):
        """Même envoyés, les coûts d'atelier ne changent rien dans l'espace client."""
        statut, corps = self.srv.post("/api/composer", {
            "texte": TEXTE_FR, "mode_impression": "recto_verso",
            "couts_operateur": {"secondes_retournement": 20, "secondes_recalage": 15,
                                "secondes_controle_alignement": 10,
                                "taux_horaire_centimes": 2500, "taux_rates": 0.03},
        })
        self.assertEqual(statut, 200, corps)
        self.assertIsNone(corps["devis"]["supplement_retournement_centimes"])
        sans_motifs_internes(self, corps)

    def test_commande_client_sans_couts_datelier_injectes(self):
        """Un navigateur ne peut pas doter sa propre commande de durées d'atelier."""
        statut, corps = self.srv.post("/api/commande", {
            "texte": TEXTE_FR, "mode_impression": "recto_verso",
            "couts_operateur": {"secondes_retournement": 1, "secondes_recalage": 1,
                                "secondes_controle_alignement": 1,
                                "taux_horaire_centimes": 100000, "taux_rates": 0.9},
        })
        self.assertEqual(statut, 201, corps)
        identifiant = corps["commande"]["id"]
        self.assertIsNone(corps["commande"]["devis"]["supplement_retournement_centimes"])

        _, vue = self.srv.get(f"/api/operateur/commande/{identifiant}", operateur=True)
        couts = vue["commande"]["couts_operateur"]
        self.assertFalse(couts["complet"])
        self.assertIsNone(couts["taux_horaire_centimes"])
        self.assertIsNone(
            vue["commande"]["devis_operateur"]["supplement"]["centimes"])

    def test_recto_seul_total_connu_mais_non_confirme(self):
        statut, corps = self.srv.post("/api/composer", {
            "texte": TEXTE_FR, "mode_impression": "recto"})
        devis = corps["devis"]
        self.assertEqual(devis["total_centimes"],
                         100 * devis["pages_ecrites"])
        self.assertFalse(devis["total_confirme"])


class TestSeparationClientOperateur(BaseAPI):
    def test_config_client_sans_interne(self):
        statut, corps = self.srv.get("/api/config")
        self.assertEqual(statut, 200)
        sans_motifs_internes(self, corps)

    def test_composer_apercu_simulation_sans_interne(self):
        for chemin in ("/api/composer", "/api/apercu", "/api/simulation"):
            statut, corps = self.srv.post(chemin, {"texte": TEXTE_FR,
                                                   "mode_impression": "recto_verso"})
            self.assertEqual(statut, 200, corps)
            sans_motifs_internes(self, corps)

    def test_simulation_client_sans_vitesse_machine(self):
        statut, corps = self.srv.post("/api/simulation", {"texte": TEXTE_FR, "page": 1})
        segments = corps["trajectoire"]["segments"]
        self.assertTrue(segments)
        for segment in segments:
            self.assertNotIn("vitesse_mm_s", segment)

    def test_espace_operateur_ferme_sans_cle(self):
        for chemin in ("/api/operateur/config", "/api/operateur/commandes"):
            statut, corps = self.srv.get(chemin)
            self.assertEqual(statut, 403, chemin)
        statut, _ = self.srv.post("/api/operateur/composer", {"texte": TEXTE_FR})
        self.assertEqual(statut, 403)

    def test_espace_operateur_ouvert_avec_cle(self):
        statut, corps = self.srv.post("/api/operateur/composer", {
            "texte": TEXTE_FR, "mode_impression": "recto_verso",
            "couts_operateur": {"secondes_retournement": 20, "secondes_recalage": 15,
                                "secondes_controle_alignement": 10,
                                "taux_horaire_centimes": 2500, "taux_rates": 0.03},
        }, operateur=True)
        self.assertEqual(statut, 200, corps)
        self.assertIsNotNone(corps["devis_operateur"]["supplement"]["centimes"])
        self.assertIn("temps_total_s", corps["simulation"]["cumul"])
        self.assertIn("couts_operateur", corps["profils_figes"])

    def test_dossiers_client_et_operateur_distincts(self):
        commande = self.commande_demo(mode="recto_verso")
        _, client, _ = self.srv.get_brut(f"/api/commande/{commande['id']}/dossier.zip")
        statut_refuse, _, _ = self.srv.get_brut(
            f"/api/operateur/commande/{commande['id']}/dossier.zip")
        self.assertEqual(statut_refuse, 403)
        statut, operateur, _ = self.srv.get_brut(
            f"/api/operateur/commande/{commande['id']}/dossier.zip", operateur=True)
        self.assertEqual(statut, 200)

        noms_client = set(zipfile.ZipFile(io.BytesIO(client)).namelist())
        noms_op = set(zipfile.ZipFile(io.BytesIO(operateur)).namelist())
        self.assertNotIn("simulation.json", noms_client)
        self.assertNotIn("devis-operateur.json", noms_client)
        self.assertFalse(any(n.startswith("trajectoires/") for n in noms_client))
        self.assertFalse(any(n.startswith("validation/") for n in noms_client))
        self.assertIn("simulation.json", noms_op)
        self.assertIn("validation/rapport.json", noms_op)

        archive = zipfile.ZipFile(io.BytesIO(client))
        contenu = "".join(archive.read(n).decode("utf-8", "replace")
                          for n in archive.namelist())
        sans_motifs_internes(self, contenu)


class TestManifesteEtDossier(BaseAPI):
    def test_manifeste_versionne_hache_et_non_executable(self):
        commande = self.commande_demo()
        _, contenu, entetes = self.srv.get_brut(
            f"/api/commande/{commande['id']}/dossier.zip")
        self.assertIn("attachment", entetes.get("Content-Disposition", ""))
        archive = zipfile.ZipFile(io.BytesIO(contenu))
        manifeste = json.loads(archive.read("MANIFESTE.json"))

        self.assertEqual(manifeste["etat"], "NON_EXECUTABLE")
        self.assertFalse(manifeste["gcode_present"])
        self.assertFalse(manifeste["acces_imprimante"])
        self.assertTrue(manifeste["version_manifeste"])
        self.assertTrue(manifeste["texte"]["preservation_exacte"])

        import hashlib
        for fiche in manifeste["fichiers"]:
            reel = hashlib.sha256(archive.read(fiche["chemin"])).hexdigest()
            self.assertEqual(reel, fiche["sha256"], fiche["chemin"])
        attendu = hashlib.sha256("\n".join(
            f"{f['chemin']}:{f['sha256']}" for f in manifeste["fichiers"]
        ).encode()).hexdigest()
        self.assertEqual(attendu, manifeste["empreinte_dossier"])

    def test_aucun_fichier_machine_dans_le_dossier(self):
        commande = self.commande_demo()
        _, contenu, _ = self.srv.get_brut(f"/api/commande/{commande['id']}/dossier.zip")
        for nom in zipfile.ZipFile(io.BytesIO(contenu)).namelist():
            self.assertFalse(nom.endswith((".gcode", ".gco", ".bgcode", ".3mf")), nom)

    def test_dossier_fige_a_la_creation(self):
        """Modifier la commande après coup ne change pas le dossier remis."""
        commande = self.commande_demo()
        _, avant, _ = self.srv.get_brut(f"/api/commande/{commande['id']}/dossier.zip")

        chemin = self.srv.server.app.store.orders_dir / f"{commande['id']}.json"
        record = json.loads(chemin.read_text(encoding="utf-8"))
        record["texte"] = "TEXTE REMPLACÉ APRÈS COUP\n"
        record["faces"] = 99
        chemin.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")

        _, apres, _ = self.srv.get_brut(f"/api/commande/{commande['id']}/dossier.zip")
        self.assertEqual(avant, apres)
        self.assertEqual(
            zipfile.ZipFile(io.BytesIO(apres)).read("texte-source.txt").decode(),
            TEXTE_FR)

    def test_dossier_altere_nest_pas_servi(self):
        commande = self.commande_demo()
        chemin = (self.srv.server.app.store.artifacts_dir
                  / f"{commande['id']}-client.zip")
        donnees = bytearray(chemin.read_bytes())
        donnees[-20] ^= 0xFF
        chemin.write_bytes(bytes(donnees))
        statut, corps = self.srv.get(f"/api/commande/{commande['id']}/dossier.zip")
        self.assertEqual(statut, 404)
        self.assertIn("empreinte différente", corps["erreur"])


class TestRefusMachine(BaseAPI):
    def test_refus_client_sans_jargon(self):
        statut, corps = self.srv.post("/api/machine", {"texte": TEXTE_FR})
        self.assertEqual(statut, 403)
        self.assertFalse(corps["autorise"])
        sans_motifs_internes(self, corps)

    def test_refus_operateur_avec_message_moteur(self):
        statut, corps = self.srv.post("/api/operateur/machine", {"texte": TEXTE_FR},
                                      operateur=True)
        self.assertEqual(statut, 403)
        self.assertFalse(corps["autorise"])
        self.assertIn("sortie machine refusée", corps["message_moteur"])
        self.assertFalse(corps["production"]["gcode_produit"])
        self.assertFalse(corps["production"]["acces_imprimante"])


class TestDepotEtPersonnalisation(BaseAPI):
    def test_depot_sans_consentement_refuse_et_rien_ecrit(self):
        avant = list(self.srv.server.app.store.samples_dir.glob("*"))
        statut, corps = self.srv.post_multipart(
            "/api/echantillon", {}, "ecriture.png", png(400, 500))
        self.assertEqual(statut, 400)
        self.assertIn("consentement", corps["erreur"])
        self.assertEqual(list(self.srv.server.app.store.samples_dir.glob("*")), avant)

    def test_depot_invalide_refuse(self):
        statut, corps = self.srv.post_multipart(
            "/api/echantillon", {"consentement": "oui"}, "ecriture.png",
            png(400, 500, declared=(1200, 1200)))
        self.assertEqual(statut, 200)
        self.assertFalse(corps["accepte"])
        self.assertTrue(corps["echantillon"]["refus"])

    def test_echantillon_invente_refuse(self):
        statut, corps = self.srv.post("/api/commande", {
            "texte": TEXTE_FR, "mode_ecriture": "personnalise",
            "echantillon": {"id": "a" * 32, "type": "image/png", "sha256": "FAUX",
                            "largeur_px": 1200, "hauteur_px": 1200},
            "consentement": True,
        })
        self.assertEqual(statut, 404)
        self.assertIn("échantillon inconnu", corps["erreur"])

    def test_mode_personnalise_sans_echantillon_refuse(self):
        statut, corps = self.srv.post("/api/commande", {
            "texte": TEXTE_FR, "mode_ecriture": "personnalise", "consentement": True})
        self.assertEqual(statut, 400)
        self.assertIn("déposez d'abord", corps["erreur"])

    def test_metadonnees_serveur_font_foi(self):
        statut, depot = self.srv.post_multipart(
            "/api/echantillon", {"consentement": "oui"}, "ecriture.png", png(600, 800))
        self.assertTrue(depot["accepte"], depot)

        statut, corps = self.srv.post("/api/commande", {
            "texte": TEXTE_FR, "mode_ecriture": "personnalise", "consentement": True,
            "echantillon": {"id": depot["echantillon"]["id"], "type": "image/jpeg",
                            "sha256": "MENSONGE", "largeur_px": 9, "hauteur_px": 9},
        })
        self.assertEqual(statut, 201, corps)
        identifiant = corps["commande"]["id"]
        self.assertEqual(corps["commande"]["etat"], "EN_ATTENTE_PERSONNALISATION")

        _, vue = self.srv.get(f"/api/operateur/commande/{identifiant}", operateur=True)
        echantillon = vue["commande"]["echantillon"]
        self.assertEqual(echantillon["type"], "image/png")
        self.assertEqual((echantillon["largeur_px"], echantillon["hauteur_px"]), (600, 800))
        self.assertNotEqual(echantillon["sha256"], "MENSONGE")

    def test_aucune_substitution_silencieuse(self):
        statut, depot = self.srv.post_multipart(
            "/api/echantillon", {"consentement": "oui"}, "ecriture.png", png(600, 800))
        statut, corps = self.srv.post("/api/commande", {
            "texte": TEXTE_FR, "mode_ecriture": "personnalise", "consentement": True,
            "echantillon": {"id": depot["echantillon"]["id"]},
        })
        identifiant = corps["commande"]["id"]
        _, vue = self.srv.get(f"/api/operateur/commande/{identifiant}", operateur=True)
        perso = vue["commande"]["personnalisation"]
        self.assertFalse(perso["ecriture_personnalisee"])
        self.assertFalse(perso["export_production_autorise"])
        self.assertTrue(perso["apercu_technique"])
        self.assertEqual(perso["statut"], "EN_ATTENTE_FOURNISSEUR")


class TestRetournementManuel(BaseAPI):
    def parcours(self):
        commande = self.commande_demo(TEXTE_FR * 14, mode="recto_verso")
        self.assertGreaterEqual(commande["etapes_a_la_main_total"], 1)
        return commande["id"]

    def etat(self, identifiant: str) -> dict:
        _, corps = self.srv.get(f"/api/operateur/commande/{identifiant}", operateur=True)
        return corps["commande"]

    def test_attente_puis_confirmation_explicite(self):
        identifiant = self.parcours()
        self.srv.post(f"/api/operateur/commande/{identifiant}/etat",
                      {"etat": "SIMULATION_EN_COURS"}, operateur=True)
        statut, corps = self.srv.post(
            f"/api/operateur/commande/{identifiant}/attente", {}, operateur=True)
        self.assertEqual(statut, 200, corps)
        self.assertEqual(self.etat(identifiant)["etat"],
                         "EN_ATTENTE_RETOURNEMENT_MANUEL")

        statut, corps = self.srv.post(
            f"/api/operateur/commande/{identifiant}/retournement",
            {"index": 0}, operateur=True)
        self.assertEqual(statut, 400)
        self.assertIn("retournée, recalée", corps["erreur"])

        statut, corps = self.srv.post(
            f"/api/operateur/commande/{identifiant}/retournement",
            {"index": 0, "alignement_controle": True}, operateur=True)
        self.assertEqual(statut, 200, corps)
        self.assertNotEqual(self.etat(identifiant)["etat"],
                            "EN_ATTENTE_RETOURNEMENT_MANUEL")

    def test_attente_non_contournable_par_les_etats(self):
        identifiant = self.parcours()
        self.srv.post(f"/api/operateur/commande/{identifiant}/etat",
                      {"etat": "SIMULATION_EN_COURS"}, operateur=True)
        self.srv.post(f"/api/operateur/commande/{identifiant}/attente", {},
                      operateur=True)
        for cible in ("PRETE_POUR_REVUE", "SIMULATION_EN_COURS", "SIMULATION_TERMINEE",
                      "RECUE", "EN_ATTENTE_PERSONNALISATION"):
            statut, corps = self.srv.post(
                f"/api/operateur/commande/{identifiant}/etat", {"etat": cible},
                operateur=True)
            self.assertEqual(statut, 400, cible)
            self.assertIn("transition refusée", corps["erreur"])
            self.assertEqual(self.etat(identifiant)["etat"],
                             "EN_ATTENTE_RETOURNEMENT_MANUEL")

    def test_confirmation_impossible_hors_attente(self):
        identifiant = self.parcours()
        statut, corps = self.srv.post(
            f"/api/operateur/commande/{identifiant}/retournement",
            {"index": 0, "alignement_controle": True}, operateur=True)
        self.assertEqual(statut, 400)
        self.assertIn("aucune intervention manuelle", corps["erreur"])

    def test_etat_inconnu_refuse(self):
        identifiant = self.parcours()
        statut, corps = self.srv.post(
            f"/api/operateur/commande/{identifiant}/etat", {"etat": "IMPRIME"},
            operateur=True)
        self.assertEqual(statut, 400)


class TestSuppression(BaseAPI):
    def test_suppression_efface_commande_photo_et_dossiers(self):
        _, depot = self.srv.post_multipart(
            "/api/echantillon", {"consentement": "oui"}, "ecriture.png", png(600, 800))
        _, corps = self.srv.post("/api/commande", {
            "texte": TEXTE_FR, "mode_ecriture": "personnalise", "consentement": True,
            "echantillon": {"id": depot["echantillon"]["id"]},
        })
        identifiant = corps["commande"]["id"]
        magasin = self.srv.server.app.store
        self.assertTrue((magasin.orders_dir / f"{identifiant}.json").exists())
        self.assertTrue((magasin.artifacts_dir / f"{identifiant}-client.zip").exists())

        statut, resultat = self.srv.delete(f"/api/commande/{identifiant}")
        self.assertEqual(statut, 200, resultat)
        self.assertTrue(resultat["commande_supprimee"])
        self.assertTrue(resultat["echantillon_supprime"])
        self.assertEqual(resultat["dossiers_supprimes"], 2)

        self.assertFalse((magasin.orders_dir / f"{identifiant}.json").exists())
        self.assertFalse((magasin.artifacts_dir / f"{identifiant}-client.zip").exists())
        self.assertFalse((magasin.artifacts_dir / f"{identifiant}-operateur.zip").exists())
        self.assertEqual(list(magasin.samples_dir.glob(
            depot["echantillon"]["id"] + "*")), [])
        self.assertEqual(self.srv.get(f"/api/commande/{identifiant}")[0], 404)


class TestSecuriteLocale(BaseAPI):
    def test_hote_etranger_refuse(self):
        statut, corps = self.srv.get("/api/config", host="evil.example")
        self.assertEqual(statut, 403)
        self.assertIn("hôte non autorisé", corps["erreur"])

    def test_jeton_obligatoire_sur_les_mutations(self):
        statut, corps = self.srv.post("/api/composer", {"texte": TEXTE_FR}, jeton=False)
        self.assertEqual(statut, 403)
        self.assertIn("jeton", corps["erreur"])

    def test_origine_etrangere_refusee(self):
        statut, corps = self.srv.post("/api/composer", {"texte": TEXTE_FR},
                                      entetes={"Origin": "http://evil.example"})
        self.assertEqual(statut, 403)

    def test_referent_etranger_refuse(self):
        statut, corps = self.srv.post("/api/composer", {"texte": TEXTE_FR},
                                      entetes={"Referer": "http://evil.example/x"})
        self.assertEqual(statut, 403)

    def test_suppression_sans_jeton_refusee(self):
        commande = self.commande_demo()
        statut, _ = self.srv.delete(f"/api/commande/{commande['id']}", jeton=False)
        self.assertEqual(statut, 403)
        self.assertEqual(self.srv.get(f"/api/commande/{commande['id']}")[0], 200)

    def test_traversee_de_chemin_impossible(self):
        for chemin in ("/static/../server.py", "/static/%2e%2e/server.py",
                       "/api/commande/../../etc/passwd",
                       "/api/commande/" + "0" * 32 + "/../../etc/passwd"):
            statut, _ = self.srv.get(chemin)
            self.assertIn(statut, (403, 404), chemin)

    def test_entetes_de_securite_presents(self):
        _, _, entetes = self.srv.get_brut("/")
        self.assertEqual(entetes.get("X-Content-Type-Options"), "nosniff")
        self.assertIn("default-src 'none'", entetes.get("Content-Security-Policy", ""))
        self.assertNotIn("Access-Control-Allow-Origin", entetes)

    def test_type_de_contenu_impose(self):
        statut, corps, _ = self.srv._appel(
            "POST", "/api/composer", b"texte=abc",
            "application/x-www-form-urlencoded", jeton=True, operateur=False)
        self.assertEqual(statut, 415)

    def test_corps_trop_gros_refuse(self):
        gros = json.dumps({"texte": "a" * 2_000_000}).encode()
        statut, _, _ = self.srv._appel("POST", "/api/composer", gros,
                                       "application/json", jeton=True, operateur=False)
        self.assertEqual(statut, 413)

    def test_le_serveur_refuse_une_adresse_non_locale(self):
        from paperx_web.server import build_server, is_loopback
        self.assertFalse(is_loopback("0.0.0.0"))
        self.assertTrue(is_loopback("127.0.0.1"))
        with tempfile.TemporaryDirectory() as dossier:
            with self.assertRaises(SystemExit):
                build_server("0.0.0.0", 0, dossier)

    def test_methode_non_supportee(self):
        statut, _, _ = self.srv._appel("PUT", "/api/config", b"{}", "application/json",
                                       jeton=True, operateur=False)
        self.assertIn(statut, (405, 501))


if __name__ == "__main__":
    unittest.main()
