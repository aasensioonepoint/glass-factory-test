#!/usr/bin/env python3
"""BANCS DU SERVICE LEDGER — schéma de leçon, colonnes machine, validateurs,
refus de version, lecture seule, dualité. Créés à l'étape C (point 5) de T-012.

RÈGLE DES TÉMOINS (ticket T-00000625) : tout témoin prouve (a) qu'il mesure une
population NON VIDE, (b) qu'elle vient de la SOURCE qu'il prétend lire, ET (c)
qu'elle est UTILISABLE — jamais l'un sans les deux autres. Aucun nombre attendu
n'entre ici sans avoir été obtenu PAR EXÉCUTION : chaque store est un FICHIER
TEMPORAIRE RÉEL (jamais `:memory:`, perdu avant lecture), et les colonnes sont
lues par `PRAGMA table_info` sur ce fichier.

LIEN SPEC↔BANC. La liste des champs ATTENDUS (`CHAMPS_SPEC`) est écrite ici, et
chaque champ est RELIÉ À LA SPEC par un fragment de texte que le banc GREP dans
`docs/PROMPT-refonte-packaging-cadre.md`. Si un champ attendu n'a pas d'ancrage
textuel dans la spec, le banc rougit sur la PROVENANCE avant même de comparer au
schéma réel — c'est la moitié (b) de la règle des témoins. Le seul champ hors
spec est `cle_sujet` : il vient du PLAN §12 B-C3 (`docs/interne/chantier/arcs/PLAN-LOT-2-phase-2.md`)
et il est ancré dans le PLAN, pas la spec, ce que le banc DIT explicitement.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
# Le paquet `cadre` de CETTE racine, où qu'il vive, chargé par chemin (vendor_paths) :
# aucun `src` inséré en tête de sys.path (T-01M5BXTPQE, lot H ; témoin test_vendor_seul_h).
_SPEC_VENDOR = importlib.util.spec_from_file_location(
    "_ledger_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
assert _SPEC_VENDOR is not None and _SPEC_VENDOR.loader is not None
_VENDOR = importlib.util.module_from_spec(_SPEC_VENDOR)
sys.modules[_SPEC_VENDOR.name] = _VENDOR
_SPEC_VENDOR.loader.exec_module(_VENDOR)
_VENDOR.charger_paquet(ROOT, "cadre")

from cadre.ledger import ids, lessons, schema, store, version  # noqa: E402

# adopting-tree: le marqueur d'identité du kit ne voyage pas (strip: .agents/IS_THE_KIT) ;
# son absence EST le signal « arbre adoptant », où l'ancrage spec/plan saute.
EST_LE_KIT = (ROOT / ".agents" / "IS_THE_KIT").is_file()

# adopting-tree: spec et plan ne voyagent pas (strip: de la spec et de docs/interne/) ;
# le seul test qui les lit saute HORS du kit, et ROUGIT dans le kit s'ils manquent.
SPEC = ROOT / "docs" / "PROMPT-refonte-packaging-cadre.md"
PLAN = ROOT / "docs" / "interne" / "chantier" / "arcs" / "PLAN-LOT-2-phase-2.md"  # adopting-tree: idem

#: CHAQUE COLONNE ↔ un fragment TEXTUEL de la spec qui la fonde. Le banc grep ces
#: fragments dans TOUTE la spec (pas seulement un paragraphe) : un champ attendu
#: sans ancrage y rougit. Écrit depuis la spec, jamais deviné : le § 5bis-B
#: « Capitalisation des leçons apprises » ancre la plupart des champs ;
#: `tenant_id` et `project_id` n'y figurent pas et sont ancrés ailleurs
#: (§ 5bis-A « Identifiants globalement stables », et les phases).
CHAMPS_SPEC = {
    "ulid": "ULID",
    "hash_contenu": "hash de contenu",
    # Le CONTENU en clair, pas seulement son hash : la leçon candidate est
    # « présentée en clair au relecteur » (§ « Capitalisation des leçons apprises »,
    # revue du contenu) — un hash ne
    # se relit pas.
    "contenu": "présentée en clair au relecteur",
    "portee": "portée",
    "type": "un **type** ou catégorie",
    "origine_projet": "projet, hôte, agent, run",
    "origine_hote": "projet, hôte, agent, run",
    "origine_agent": "projet, hôte, agent, run",
    "origine_run": "projet, hôte, agent, run",
    "statut_partage": "statut de partage",
    "statut_sync": "statut de synchronisation",
    "version_schema_lecon": "version de schéma de leçon",
    "ref_forme_generalisee": "forme généralisée",
    "provenance": "provenance",
    "tenant_id": "tenant_id",
    "project_id": "project_id",
    "reference_accord": "référence de l'accord",
    "identite_declaree": "identité déclarée",
    "horodatage": "horodatage",
    "validateur_1": "deux comptes distincts",
    "validateur_2": "deux comptes distincts",
    # « Aucune leçon ne sort sans acte de revue enregistré » : le relecteur et
    # l'horodatage de la revue sont EUX AUSSI portés par le schéma.
    "revue_par": "acte de revue enregistré",
    "revue_horodatage": "acte de revue enregistré",
}

#: Les noms de colonnes machine que la spec INTERDIT, énumérés VERBATIM dans son
#: texte (« informations machine (hostname, utilisateur système, IP) »). Ce
#: fragment est RETIRÉ du texte de spec avant le grep des ancres : sans quoi un
#: `CHAMPS_SPEC` fautif ancré sur « hostname » y trouverait sa provenance et
#: passerait, alors que hostname est précisément une colonne PROSCRITE.
INTERDITS = "(hostname, utilisateur système, IP)"

#: HORS SPEC : `cle_sujet` vient du PLAN §12 B-C3 (précédence par sujet). Ancré
#: dans le PLAN, pas la spec — et le banc le vérifie contre le bon fichier.
CHAMP_PLAN = {"cle_sujet": "cle_sujet"}

#: Motifs d'un NOM DE COLONNE MACHINE, interdits par la spec (données
#: personnelles). `origine_hote` (hôte D'AGENT) n'en fait PAS partie et ne doit
#: pas être un faux positif : aucun motif ci-dessous n'est un sous-mot de `hote`.
MOTIFS_MACHINE = ("hostname", "host_name", "machine", "ip_", "_ip", "adresse",
                  "username", "user_name", "utilisateur", "system_user",
                  "os_user", "mac_addr", "mac_address")


class _StoreReelMixin(unittest.TestCase):
    def _store_reel(self):
        """Un store sur FICHIER RÉEL, schéma garanti. Nettoyage enregistré."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        chemin = Path(tmp.name) / "lecons.db"
        conn = store.connect(chemin)
        self.addCleanup(conn.close)
        version.garantir_schema(conn)
        return chemin, conn

    def _colonnes_reelles(self, conn) -> set[str]:
        rows = conn.execute("PRAGMA table_info(" + schema.TABLE + ")").fetchall()
        return {r["name"] for r in rows}


class SchemaLeconTests(_StoreReelMixin):
    @unittest.skipUnless(EST_LE_KIT,
                         "arbre adoptant (marqueur .agents/IS_THE_KIT absent) : spec et "
                         "plan ne voyagent pas, l'ancrage n'a pas de sujet")
    def test_le_schema_de_lecon_porte_EXACTEMENT_les_champs_de_la_spec(self):
        # DANS LE KIT, une source absente ROUGIT, jamais ne saute : un chemin
        # périmé (déplacement de fichier) éteignait sinon ce banc en silence.
        self.assertTrue(SPEC.is_file(), f"spec absente dans le kit : {SPEC}")
        self.assertTrue(PLAN.is_file(), f"plan absent dans le kit : {PLAN}")
        # (b) PROVENANCE : chaque champ attendu est ANCRÉ dans sa source. Le
        # fragment ÉNUMÉRANT les colonnes INTERDITES est retiré d'abord, sinon
        # « hostname » (proscrit) pourrait ancrer une colonne. Sa PRÉSENCE se
        # vérifie sur le texte BRUT, avant le retrait : vérifiée après, elle
        # était tautologique, et une spec reformulée laissait le filet sans sujet.
        # `assertTrue(… in …)` plutôt qu'`assertIn` : ce dernier recopie la spec
        # entière (~80 ko) dans le message d'échec.
        brut = SPEC.read_text(encoding="utf-8")
        self.assertTrue(INTERDITS in brut,
                        "fragment des colonnes interdites introuvable dans la spec : "
                        "le filet anti-hostname n'a plus de sujet")
        texte_spec = brut.replace(INTERDITS, "")
        self.assertTrue(CHAMPS_SPEC, "liste de champs vide — le banc ne mesure rien")
        sans_ancrage = sorted(
            col for col, frag in CHAMPS_SPEC.items() if frag not in texte_spec
        )
        self.assertEqual(
            sans_ancrage, [],
            "champs attendus SANS ancrage textuel dans la spec (provenance non "
            f"prouvée) : {sans_ancrage}",
        )
        texte_plan = PLAN.read_text(encoding="utf-8")
        for col, frag in CHAMP_PLAN.items():
            self.assertIn(
                frag, texte_plan,
                f"`{col}` (hors spec) sans ancrage dans le plan §12 B-C3",
            )
        # (a)+(c) ÉGALITÉ D'ENSEMBLE : schéma RÉEL (fichier) == attendu, non vide.
        _chemin, conn = self._store_reel()
        reelles = self._colonnes_reelles(conn)
        self.assertTrue(reelles, "PRAGMA table_info vide — store non peuplé")
        attendues = set(CHAMPS_SPEC) | set(CHAMP_PLAN)
        self.assertEqual(
            reelles, attendues,
            "schéma ≠ attendu.\n  en trop : "
            + str(sorted(reelles - attendues))
            + "\n  manquants : " + str(sorted(attendues - reelles)),
        )

    def test_aucune_colonne_machine(self):
        _chemin, conn = self._store_reel()
        reelles = self._colonnes_reelles(conn)
        self.assertTrue(reelles, "aucune colonne lue — le banc serait vert par vacuité")
        fautives = sorted(
            c for c in reelles if any(m in c.lower() for m in MOTIFS_MACHINE)
        )
        self.assertEqual(
            fautives, [],
            "colonnes machine (hostname / utilisateur système / IP), interdites "
            f"par la spec (données personnelles à valeur probante faible) : {fautives}",
        )


class ValidateursTests(_StoreReelMixin):
    def _lecon(self, **kw):
        base = dict(
            ulid=ids.nouvel_ulid(), hash_contenu="h", contenu="c", cle_sujet="s",
            portee="partageable", provenance="locale",
            statut_partage="en_attente_de_revue", statut_sync="local",
            version_schema_lecon=1, tenant_id="t", project_id="p",
            horodatage="2026-01-01T00:00:00+00:00",
        )
        base.update(kw)
        return lessons.Lecon(**base)

    def _refuse(self, lecon):
        """Un INSERT qui viole un CHECK / une FK lève `IntegrityError`. Le
        `rollback` remet la connexion en état pour l'assertion suivante."""
        _chemin, conn = self._store_reel()
        with self.assertRaises(sqlite3.IntegrityError):
            lessons.inserer(conn, lecon)
            conn.commit()
        conn.rollback()

    def test_deux_validateurs_identiques_sont_REFUSES(self):
        _chemin, conn = self._store_reel()
        identique = self._lecon(validateur_1="compte-A", validateur_2="compte-A")
        with self.assertRaises(sqlite3.IntegrityError):
            lessons.inserer(conn, identique)
            conn.commit()
        conn.rollback()
        # CONTRÔLE POSITIF : deux validateurs DISTINCTS passent — sinon le refus
        # ci-dessus pourrait venir d'une AUTRE contrainte que l'inégalité.
        distinct = self._lecon(validateur_1="compte-A", validateur_2="compte-B")
        lessons.inserer(conn, distinct)
        conn.commit()
        self.assertIsNotNone(lessons.lire_lecon(conn, distinct.ulid))

    def test_une_locale_partagee_est_REFUSEE(self):
        # portée `locale` ⇒ statut FORCÉ 'prive' : une locale non privée est refusée.
        self._refuse(self._lecon(portee="locale", statut_partage="en_attente_de_revue"))

    def test_deux_validateurs_ne_differant_que_par_la_CASSE_sont_REFUSES(self):
        # `lower(trim(...))` : « Compte-A » et « compte-a » sont le MÊME compte.
        self._refuse(self._lecon(validateur_1="Compte-A", validateur_2=" compte-a "))

    def test_un_validateur_2_SEUL_est_REFUSE(self):
        self._refuse(self._lecon(validateur_1=None, validateur_2="compte-B"))

    def test_un_partage_SANS_accord_est_REFUSE(self):
        # statut 'partage' : la revue et les deux validateurs sont fournis, mais
        # `reference_accord` manque — c'est CE manque qui refuse (niveau 1 du partage).
        self._refuse(self._lecon(
            statut_partage="partage", revue_par="r",
            revue_horodatage="2026-01-01T00:00:00+00:00",
            validateur_1="a", validateur_2="b", reference_accord=None))

    def test_un_lien_vers_un_ulid_INEXISTANT_est_REFUSE(self):
        # FK `ref_forme_generalisee` : PRAGMA foreign_keys=ON (posé par store.py)
        # refuse un lien qui ne pointe aucune ligne.
        self._refuse(self._lecon(
            portee="locale", statut_partage="prive",
            ref_forme_generalisee="ULIDINEXISTANT0000000000000"))


class VersionTests(_StoreReelMixin):
    def test_un_schema_plus_recent_que_le_binaire_REFUSE_de_demarrer(self):
        _chemin, conn = self._store_reel()  # user_version = VERSION_SCHEMA
        futur = version.VERSION_SCHEMA + 5
        conn.execute("PRAGMA user_version = " + str(futur))
        conn.commit()
        self.assertEqual(
            version.lire_version(conn), futur,
            "la version future n'a pas été posée — banc non armé",
        )
        with self.assertRaises(version.SchemaPlusRecent):
            version.garantir_schema(conn)

    # --- T-00000905 : le refus N'ÉCRIT RIEN, même quand la course le provoque ---
    def _store_ferme(self, valeur: int, *, wal: bool = False) -> Path:
        """Un store réel, schéma garanti, puis tamponné à `valeur` et FERMÉ."""
        chemin, conn = self._store_reel()
        if wal:
            self.assertEqual(conn.execute("PRAGMA journal_mode=WAL").fetchone()[0],
                             "wal", "le store n'est pas passé en WAL — banc non armé")
        conn.execute("PRAGMA user_version = " + str(int(valeur)))
        conn.commit()
        conn.close()
        return chemin

    def _refus_sans_ecrire(self, valeur: int, attendue: type, *,
                           wal: bool = False) -> str:
        """Ouvre comme un appelant le store tamponné à `valeur`, exige `attendue`,
        puis prouve qu'AUCUN octet n'a bougé : fichier identique, version de
        l'en-tête intacte, aucune annexe APRÈS fermeture (en WAL, `-wal`/`-shm`
        existent légitimement tant qu'une connexion lit). Rend le message."""
        chemin = self._store_ferme(valeur, wal=wal)
        avant = _octets_et_version(chemin)
        self.assertEqual(avant[1], valeur, "version absente de l'en-tête — banc non armé")
        conn = store.connect(chemin)
        self.addCleanup(conn.close)
        with self.assertRaises(attendue) as ctx:
            version.garantir_schema(conn)
        self.assertFalse(conn.in_transaction, "le refus laisse une transaction ouverte")
        conn.close()
        self.assertEqual(_octets_et_version(chemin), avant, "le store refusé a été écrit")
        self.assertEqual(_annexes(chemin), [])
        return str(ctx.exception)

    def test_a_N_plus_1_est_refuse_SANS_ECRIRE_et_dit_le_remede(self):
        futur = version.VERSION_SCHEMA + 1
        message = self._refus_sans_ecrire(futur, version.SchemaPlusRecent)
        self.assertIn("version " + str(futur), message)
        self.assertIn("mets à jour le kit", message)

    def test_b_N_plus_1_en_WAL_est_refuse_SANS_ECRIRE(self):
        self._refus_sans_ecrire(version.VERSION_SCHEMA + 1, version.SchemaPlusRecent,
                                wal=True)

    def test_c_un_kit_plus_recent_qui_gagne_la_course_n_est_JAMAIS_retrograde(self):
        """La sonde lit v1 ; un kit PLUS RÉCENT tamponne N+1 avant la migration.
        La montée doit RE-SONDER sous le verrou et refuser : jamais rétrograder
        le tampon, jamais créer de table dans le store du futur."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        chemin = Path(tmp.name) / "lecons.db"
        conn = store.connect(chemin)
        self.addCleanup(conn.close)
        schema.creer_schema(conn)
        conn.execute("PRAGMA user_version = 1")
        conn.commit()
        futur = version.VERSION_SCHEMA + 1
        vraie, lues = version.lire_version, []

        def sonde_puis_kit_plus_recent(c):
            lue = vraie(c)
            lues.append(lue)
            if len(lues) == 1:  # entre la sonde et la migration
                tiers = sqlite3.connect(str(chemin))
                try:
                    tiers.execute("PRAGMA user_version = " + str(int(futur)))
                    tiers.commit()
                finally:
                    tiers.close()
            return lue

        with mock.patch.object(version, "lire_version", sonde_puis_kit_plus_recent):
            with self.assertRaises(version.SchemaPlusRecent):
                version.garantir_schema(conn)
        self.assertEqual(lues[0], 1, "la sonde n'a pas lu v1 — banc non armé")
        self.assertFalse(conn.in_transaction, "le refus laisse une transaction ouverte")
        conn.close()
        self.assertEqual(_octets_et_version(chemin)[1], futur,
                         "le tampon du kit plus récent a été RÉTROGRADÉ")
        relu = sqlite3.connect(str(chemin))
        try:
            tables = {r[0] for r in relu.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'")}
        finally:
            relu.close()
        self.assertIn(schema.TABLE, tables, "store v1 sans table de leçons — banc non armé")
        self.assertNotIn(schema.TABLE_APPLIQUEE, tables,
                         "une migration a écrit dans le store du futur")

    def test_d_une_version_negative_leve_une_erreur_NOMMEE_sans_ecrire(self):
        message = self._refus_sans_ecrire(-1, version.SchemaInconnu)
        self.assertIn("version -1", message)

    def test_egale_ou_plus_ancienne_monte_comme_avant(self):
        for depart in (0, 1, version.VERSION_SCHEMA):
            with self.subTest(depart=depart):
                tmp = tempfile.TemporaryDirectory()
                self.addCleanup(tmp.cleanup)
                chemin = Path(tmp.name) / "lecons.db"
                conn = store.connect(chemin)
                self.addCleanup(conn.close)
                for cible in range(1, depart + 1):
                    schema.MIGRATIONS[cible](conn)
                conn.execute("PRAGMA user_version = " + str(int(depart)))
                conn.commit()
                mode = conn.isolation_level
                self.assertEqual(version.garantir_schema(conn), version.VERSION_SCHEMA)
                self.assertEqual(conn.isolation_level, mode,
                                 "le mode de transaction de l'appelant a changé")
                self.assertFalse(conn.in_transaction)
                conn.close()
                self.assertEqual(_octets_et_version(chemin)[1], version.VERSION_SCHEMA)
                relu = sqlite3.connect(str(chemin))
                try:
                    tables = {r[0] for r in relu.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'")}
                finally:
                    relu.close()
                self.assertLessEqual({schema.TABLE, schema.TABLE_APPLIQUEE}, tables)

    def test_une_transaction_ouverte_de_l_appelant_est_VALIDEE_puis_le_store_monte(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        chemin = Path(tmp.name) / "lecons.db"
        conn = store.connect(chemin)
        self.addCleanup(conn.close)
        schema.creer_schema(conn)
        conn.execute("PRAGMA user_version = 1")
        conn.commit()
        conn.execute("CREATE TABLE appelant(x)")
        conn.execute("INSERT INTO appelant VALUES (7)")
        self.assertTrue(conn.in_transaction, "aucune transaction ouverte — banc non armé")
        self.assertEqual(version.garantir_schema(conn), version.VERSION_SCHEMA)
        conn.close()
        relu = sqlite3.connect(str(chemin))
        try:
            lignes = relu.execute("SELECT x FROM appelant").fetchall()
        finally:
            relu.close()
        self.assertEqual(lignes, [(7,)], "l'écriture de l'appelant a été perdue")
        self.assertEqual(_octets_et_version(chemin)[1], version.VERSION_SCHEMA)

    def test_la_montee_v1_v2_marche_sous_les_trois_modes_de_transaction(self):
        """`autocommit` (PEP 249, Python >= 3.12, exec-critic S-00004751) : sous
        `autocommit=False`, `isolation_level = None` est sans effet et une
        transaction reste ouverte — `BEGIN IMMEDIATE` levait. Chaque mode monte
        v1 -> v2 et retrouve son réglage `autocommit` et `isolation_level`."""
        pep249 = hasattr(sqlite3, "LEGACY_TRANSACTION_CONTROL")
        for mode in ("legacy", True, False):
            with self.subTest(autocommit=mode):
                if mode != "legacy" and not pep249:
                    self.skipTest("Python < 3.12 : pas d'attribut `autocommit`")
                tmp = tempfile.TemporaryDirectory()
                self.addCleanup(tmp.cleanup)
                chemin = Path(tmp.name) / "lecons.db"
                prep = store.connect(chemin)
                schema.creer_schema(prep)
                prep.execute("PRAGMA user_version = 1")
                prep.commit()
                prep.close()
                conn = (sqlite3.connect(str(chemin)) if mode == "legacy"
                        else sqlite3.connect(str(chemin), autocommit=mode))
                self.addCleanup(conn.close)
                auto, isolation = getattr(conn, "autocommit", None), conn.isolation_level
                self.assertEqual(version.garantir_schema(conn), version.VERSION_SCHEMA)
                self.assertEqual(getattr(conn, "autocommit", None), auto,
                                 "le réglage autocommit de l'appelant a changé")
                self.assertEqual(conn.isolation_level, isolation,
                                 "le mode de transaction de l'appelant a changé")
                conn.close()
                self.assertEqual(_octets_et_version(chemin)[1], version.VERSION_SCHEMA)
                relu = sqlite3.connect(str(chemin))
                try:
                    tables = {r[0] for r in relu.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'")}
                finally:
                    relu.close()
                self.assertIn(schema.TABLE_APPLIQUEE, tables, "la migration v2 n'a pas eu lieu")


def _octets_et_version(chemin: Path) -> tuple[bytes, int]:
    """Les OCTETS du fichier et le `user_version` LU DANS L'EN-TÊTE (4 octets
    gros-boutiens SIGNÉS à l'offset 60), sans connexion — donc sans `-wal`/`-shm`."""
    octets = chemin.read_bytes()
    return octets, int.from_bytes(octets[60:64], "big", signed=True)


def _annexes(chemin: Path) -> list[str]:
    return [s for s in ("-wal", "-shm", "-journal") if Path(str(chemin) + s).exists()]


class LectureSeuleTests(unittest.TestCase):
    def test_un_store_en_chmod_444_se_LIT_et_REFUSE_l_ecriture(self):
        with tempfile.TemporaryDirectory() as d:
            chemin = Path(d) / "lecons.db"
            conn = store.connect(chemin)
            version.garantir_schema(conn)
            lessons.ecrire_lecon(conn, contenu="c", cle_sujet="s",
                                 tenant_id="t", project_id="p")
            conn.close()
            os.chmod(chemin, 0o444)
            ro = store.connect(chemin, lecture_seule=True)
            try:
                n = ro.execute("SELECT COUNT(*) FROM " + schema.TABLE).fetchone()[0]
                self.assertGreater(n, 0, "la lecture seule ne rend rien — store vide ?")
                with self.assertRaises(sqlite3.OperationalError):
                    ro.execute(
                        "INSERT INTO " + schema.TABLE + " (ulid, hash_contenu, "
                        "contenu, cle_sujet, portee, provenance, statut_partage, "
                        "statut_sync, version_schema_lecon, tenant_id, "
                        "project_id, horodatage) VALUES "
                        "('x','h','c','s','locale','locale','prive','local',1,'t','p','2026')"
                    )
                    ro.commit()
            finally:
                ro.close()
                # rendre le fichier supprimable pour le nettoyage du TemporaryDirectory
                os.chmod(chemin, 0o644)

    def test_un_chemin_relatif_en_lecture_seule_est_un_refus_nomme(self):
        """Un relatif en lecture seule est refusé PAR MESSAGE, jamais résolu contre le cwd."""
        with self.assertRaisesRegex(ValueError, "chemin relatif refusé"):
            store.connect(Path("rel") / "lecons.db", lecture_seule=True)


class DualiteTests(_StoreReelMixin):
    def test_la_dualite_produit_deux_enregistrements_lies_jamais_fusionnes(self):
        """AXE 2 du schéma : une leçon locale et sa forme généralisée sont DEUX
        enregistrements distincts, liés par `ref_forme_generalisee`, jamais
        fusionnés — et la forme généralisée ne porte AUCUN contexte projet."""
        _chemin, conn = self._store_reel()
        loc, gen = lessons.ecrire_lecon(
            conn, contenu="contexte local du projet", cle_sujet="sujet-X",
            tenant_id="t", project_id="p", origine_projet="projet-secret",
            origine_hote="claude", forme_generalisee="leçon générique sans contexte",
        )
        self.assertIsNotNone(gen, "aucune forme généralisée écrite")
        self.assertNotEqual(loc, gen, "les deux enregistrements ne sont pas distincts")
        rloc = lessons.lire_lecon(conn, loc)
        rgen = lessons.lire_lecon(conn, gen)
        # LE CONTENU EST STOCKÉ EN CLAIR, chacun le SIEN (pas seulement le hash).
        self.assertEqual(rloc["contenu"], "contexte local du projet",
                         "la locale ne stocke pas son contenu en clair")
        self.assertEqual(rgen["contenu"], "leçon générique sans contexte",
                         "la forme généralisée ne stocke pas son texte générique")
        self.assertEqual(rloc["portee"], "locale")
        self.assertEqual(rloc["statut_partage"], "prive")
        self.assertEqual(rloc["ref_forme_generalisee"], gen,
                         "le lien local→généralisée est rompu")
        self.assertEqual(rgen["portee"], "partageable")
        self.assertEqual(rgen["statut_partage"], "en_attente_de_revue")
        self.assertIsNone(rgen["origine_projet"],
                          "la forme généralisée porte un contexte projet")
        self.assertIsNone(rgen["ref_forme_generalisee"],
                          "la forme généralisée pointe un lien qu'elle ne doit pas porter")


class EcritureTransactionnelleTests(_StoreReelMixin):
    def test_une_ecriture_qui_echoue_ne_laisse_RIEN(self):
        """TRANSACTIONNEL : la généralisée est insérée AVANT la locale ; si la
        suite échoue (`contenu=None` — la locale porte un `contenu` NOT NULL et
        son hash n'est même pas calculable), le `rollback` annule AUSSI la
        généralisée déjà insérée. Jamais une moitié écrite."""
        _chemin, conn = self._store_reel()
        with self.assertRaises(Exception):
            lessons.ecrire_lecon(
                conn, contenu=None, cle_sujet="s", tenant_id="t", project_id="p",
                forme_generalisee="une forme générique")
        conn.commit()
        n = conn.execute("SELECT COUNT(*) FROM " + schema.TABLE).fetchone()[0]
        self.assertEqual(n, 0, "un enregistrement a survécu à une écriture échouée")


class DedupTests(_StoreReelMixin):
    def test_deux_ecritures_de_la_meme_forme_generalisee_partagent_UNE_ligne(self):
        """DÉDUP : deux écritures dont la forme généralisée est IDENTIQUE
        réutilisent l'unique ligne partageable (même ulid), au lieu de violer
        `ux_lecons_dedup`. Contenus locaux distincts pour isoler l'axe partageable."""
        _chemin, conn = self._store_reel()
        kw = dict(cle_sujet="s", tenant_id="t", project_id="p",
                  forme_generalisee="leçon générique partageable")
        _loc1, gen1 = lessons.ecrire_lecon(conn, contenu="contexte A", **kw)
        _loc2, gen2 = lessons.ecrire_lecon(conn, contenu="contexte B", **kw)
        self.assertIsNotNone(gen1)
        self.assertEqual(gen1, gen2, "la forme généralisée n'a pas été réutilisée")
        n = conn.execute(
            "SELECT COUNT(*) FROM " + schema.TABLE + " WHERE portee = 'partageable'"
        ).fetchone()[0]
        self.assertEqual(n, 1, "deux lignes partageables au lieu d'une (dédup KO)")


def test_vendor_seul_h():
    """TÉMOIN H (T-01M5BXTPQE, lot H) : dans un kit jetable où le paquet vit sous
    `.agents/vendor/cadre`, un `src/cadre` LEURRE subsiste (ancien emplacement) et un
    `cadre` ÉTRANGER est sur PYTHONPATH, ce banc importe le ledger du paquet VENDOR.
    MUTANT : `sys.path.insert(0, ROOT / "src")` rétabli → le leurre gagne, rouge."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        kit = base / "kit"
        banc = kit / ".agents" / "evals" / Path(__file__).name
        banc.parent.mkdir(parents=True)
        shutil.copyfile(__file__, banc)
        resolveur = kit / ".agents" / "bin" / "vendor_paths.py"
        resolveur.parent.mkdir(parents=True)
        shutil.copyfile(ROOT / ".agents" / "bin" / "vendor_paths.py", resolveur)
        cible = kit / ".agents" / "vendor" / "cadre"
        shutil.copytree(_VENDOR.exiger(ROOT, "cadre"), cible,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        for leurre in (kit / "src" / "cadre", base / "etranger" / "cadre"):
            leurre.mkdir(parents=True)
            (leurre / "__init__.py").write_text("", encoding="utf-8")
        env = dict(os.environ, PYTHONPATH=str(base / "etranger"))
        sonde = ("import runpy, sys; m = runpy.run_path(sys.argv[1], run_name='ledger_sonde'); "
                 "print(m['ids'].__file__); print(m['store'].__file__)")
        resultat = subprocess.run([sys.executable, "-B", "-c", sonde, str(banc)],
                                  cwd=base, env=env, capture_output=True, text=True, timeout=60)
        assert resultat.returncode == 0, resultat.stderr
        lus = [Path(ligne).resolve() for ligne in resultat.stdout.split()]
        attendus = [(cible / "ledger" / "ids.py").resolve(), (cible / "ledger" / "store.py").resolve()]
        assert lus == attendus, resultat.stdout


if __name__ == "__main__":
    unittest.main()
