#!/usr/bin/env python3
"""BANC DE LA PROMOTION HUMAINE — `check_lesson_promotion` (T-00000647).

« promotion humaine revue » (décision pilote du 2026-09-17) : `cadre lessons
promote` transitionne une forme généralisée en attente vers l'état d'équipe,
écrit UN fichier JSON par forme (`.agents/state/lessons/<ulid>.json`, clés
triées, LF) AVANT de commiter, et tout refus sort en 2 avec sa cause sur `stderr`
sans traceback.

Ce banc n'opère que sur un magasin en FICHIER TEMPORAIRE RÉEL et sur le paquet
`cadre`, qui voyage. Les témoins qui jouent `main(...)` sont CONFINÉS par
`$CADRE_PROJECT_ROOT` sur un arbre temporaire (`vider_cache_racine()` en `setUp`
et en nettoyage) : jamais un octet dans le `.agents/state/lessons/` du dépôt réel.
Aucun `skipTest` : la partie tourne sur le kit comme sur un arbre adoptant.

Le littéral `.agents/state/lessons/<ulid>.json` se joint TOUJOURS à l'arbre
temporaire (`self.projet`), JAMAIS au jeton `ROOT` — la séparation des deux jetons
est ce qui tient `test_adopting_gate.py`, pas l'ancrage de la fixture.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
# Le paquet `cadre` de CETTE racine, où qu'il vive, chargé par chemin (vendor_paths) :
# aucun `src` inséré en tête de sys.path (T-01M5BXTPQE, lot H).
_SPEC_VENDOR = importlib.util.spec_from_file_location(
    "_ledger_promotion_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
assert _SPEC_VENDOR is not None and _SPEC_VENDOR.loader is not None
_VENDOR = importlib.util.module_from_spec(_SPEC_VENDOR)
sys.modules[_SPEC_VENDOR.name] = _VENDOR
_SPEC_VENDOR.loader.exec_module(_VENDOR)
_VENDOR.charger_paquet(ROOT, "cadre")

from cadre import cli  # noqa: E402
from cadre.ledger import ids, lessons, promotion, schema, store, version  # noqa: E402
from cadre.paths import project_root, vider_cache_racine  # noqa: E402
from cadre.workspace import Workspace  # noqa: E402

#: GOLDEN FIGÉ des octets promus (clés ALPHABÉTIQUES, indent 2, LF final). L'ordre
#: des colonnes du store N'EST PAS alphabétique (schema.py:89-96 finit par
#: validateur_1/_2/revue_par/revue_horodatage), donc `sort_keys=False` produirait
#: l'ordre des colonnes et ce golden mordrait. Texte, encodé UTF-8 à la comparaison.
GOLDEN = (
    '{\n'
    '  "cle_sujet": "G",\n'
    '  "contenu": "leçon générique figée",\n'
    '  "hash_contenu": "h:golden",\n'
    '  "horodatage": "2026-01-01T00:00:00+00:00",\n'
    '  "identite_declaree": null,\n'
    '  "origine_agent": null,\n'
    '  "origine_hote": null,\n'
    '  "origine_projet": null,\n'
    '  "origine_run": null,\n'
    '  "portee": "partageable",\n'
    '  "project_id": "p",\n'
    '  "provenance": "locale",\n'
    '  "ref_forme_generalisee": null,\n'
    '  "reference_accord": null,\n'
    '  "revue_horodatage": "2026-03-03T00:00:00+00:00",\n'
    '  "revue_par": "Bob",\n'
    '  "statut_partage": "revue_faite",\n'
    '  "statut_sync": "local",\n'
    '  "tenant_id": "t",\n'
    '  "type": null,\n'
    '  "ulid": "01GOLDEN0PROMOTE00000000AB",\n'
    '  "validateur_1": null,\n'
    '  "validateur_2": null,\n'
    '  "version_schema_lecon": 1\n'
    '}\n'
).encode("utf-8")


class _InterposeAvantUpdate:
    """Proxy de connexion : joue `hook` juste AVANT le PREMIER `UPDATE` que
    `promouvoir` exécute. REPRODUIT DÉTERMINISTIQUEMENT une promotion concurrente
    survenue ENTRE la lecture de précondition et l'écriture — la précondition a déjà
    lu `en_attente_de_revue`, mais la ligne ne l'est plus à l'`UPDATE`. Forward tout
    le reste à la connexion réelle (`sqlite3.Connection` n'accepte pas qu'on lui
    greffe un attribut, d'où le proxy plutôt qu'un monkeypatch d'instance)."""

    def __init__(self, reel, hook):
        self._reel = reel
        self._hook = hook
        self._joue = False

    def execute(self, sql, *args):
        if not self._joue and sql.lstrip().upper().startswith("UPDATE"):
            self._joue = True
            self._hook()
        return self._reel.execute(sql, *args)

    def __getattr__(self, nom):
        return getattr(self._reel, nom)


class _Confine(unittest.TestCase):
    def setUp(self):
        self._env = dict(os.environ)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.projet = self.base / "projet"
        self.projet.mkdir()
        self.magasin = self.base / "lecons.db"
        os.environ["CADRE_PROJECT_ROOT"] = str(self.projet)
        vider_cache_racine()
        self.addCleanup(vider_cache_racine)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)
        vider_cache_racine()

    def _conn(self):
        conn = store.connect(self.magasin)
        version.garantir_schema(conn)
        self.addCleanup(conn.close)
        return conn

    def _inserer(self, conn, *, portee, provenance, statut_partage, contenu="x",
                 cle_sujet="S", revue_par=None, revue_horodatage=None):
        ul = ids.nouvel_ulid()
        lessons.inserer(conn, lessons.Lecon(
            ulid=ul, hash_contenu="h:" + ul, contenu=contenu, cle_sujet=cle_sujet,
            portee=portee, provenance=provenance, statut_partage=statut_partage,
            statut_sync="local", version_schema_lecon=1, tenant_id="t", project_id="p",
            horodatage="2026-01-01T00:00:00+00:00", revue_par=revue_par,
            revue_horodatage=revue_horodatage))
        conn.commit()
        return ul

    def _poser_generalisee(self, contenu="leçon générique"):
        """Un magasin FICHIER portant UNE forme généralisée en attente ; rend l'ulid.
        La connexion est refermée pour que les témoins relisent sur une connexion
        DISTINCTE (preuve du commit)."""
        conn = store.connect(self.magasin)
        version.garantir_schema(conn)
        ul = self._inserer(conn, portee="partageable", provenance="locale",
                           statut_partage="en_attente_de_revue", contenu=contenu,
                           cle_sujet="S")
        conn.close()
        return ul


class PromotionModuleTests(_Confine):
    """Témoins 7 et 8 : `promouvoir` seul (aucun magasin de CLI, aucune E/S)."""

    def test_promouvoir_REFUSE_toute_ligne_qui_n_est_pas_une_generalisee_en_attente(self):
        """TÉMOIN 7 — trois bras, chaque valeur des trois champs
        `(portee, provenance, statut_partage)` donnée EXPLICITEMENT. Chacun lève
        `ValueError` et la ligne reste INCHANGÉE. Mord : précondition à trois
        membres retirée → le bras 1 (embarquée) rend un dict et marque revue_faite."""
        conn = self._conn()
        b1 = self._inserer(conn, portee="partageable", provenance="embarquee",
                           statut_partage="en_attente_de_revue")  # seul provenance diffère
        b2 = self._inserer(conn, portee="locale", provenance="locale",
                           statut_partage="prive")  # portee ET statut (schema.py:142)
        b3 = self._inserer(conn, portee="partageable", provenance="locale",
                           statut_partage="revue_faite", revue_par="X",
                           revue_horodatage="2026-01-01T00:00:00+00:00")
        for ul in (b1, b2, b3):
            avant = lessons.lire_lecon(conn, ul)
            with self.assertRaises(ValueError):
                promotion.promouvoir(conn, ul, revue_par="R",
                                     horodatage="2026-05-05T00:00:00+00:00")
            self.assertEqual(lessons.lire_lecon(conn, ul), avant,
                             "promouvoir a modifié une ligne qu'il devait refuser")

    def test_les_octets_promus_sont_EGAUX_a_un_GOLDEN_fige(self):
        """TÉMOIN 8 — les octets d'une ligne à valeurs FIXES égalent un GOLDEN
        littéral. Mord : `sort_keys=True → False` (l'ordre des colonnes n'est pas
        alphabétique) ; seconde mutation, retrait du `\\n` final."""
        conn = self._conn()
        lessons.inserer(conn, lessons.Lecon(
            ulid="01GOLDEN0PROMOTE00000000AB", hash_contenu="h:golden",
            contenu="leçon générique figée", cle_sujet="G", portee="partageable",
            provenance="locale", statut_partage="en_attente_de_revue",
            statut_sync="local", version_schema_lecon=1, tenant_id="t", project_id="p",
            horodatage="2026-01-01T00:00:00+00:00"))
        conn.commit()
        ligne, octets = promotion.promouvoir(
            conn, "01GOLDEN0PROMOTE00000000AB", revue_par="Bob",
            horodatage="2026-03-03T00:00:00+00:00")
        self.assertEqual(octets, GOLDEN, "les octets promus ont divergé du GOLDEN figé")
        self.assertEqual(ligne["statut_partage"], "revue_faite")

    def test_promouvoir_REFUSE_un_relecteur_ou_un_horodatage_VIDE(self):
        """A-C6 / B-(2) — sur une forme généralisée VALIDE, un `revue_par` ou un
        `horodatage` vide (ou seulement blanc) est refusé par `ValueError` et NE
        promeut PAS : « aucune leçon ne sort sans acte de revue enregistré »
        (spec §5bis-B). Le `CHECK` schema.py:153-154 ne voit que `NOT NULL` — `''` le
        satisferait, la garde vit donc dans `promouvoir`. Mord : retrait de la garde
        `revue_par`/`horodatage` → le blanc passe, la ligne devient `revue_faite`
        avec un relecteur anonyme."""
        conn = self._conn()
        for revue_par, horodatage in (
            ("", "2026-05-05T00:00:00+00:00"),
            ("   ", "2026-05-05T00:00:00+00:00"),
            ("Alice", ""),
            ("Alice", "   "),
        ):
            ul = self._inserer(conn, portee="partageable", provenance="locale",
                               statut_partage="en_attente_de_revue")
            with self.assertRaises(ValueError):
                promotion.promouvoir(conn, ul, revue_par=revue_par, horodatage=horodatage)
            self.assertEqual(lessons.lire_lecon(conn, ul)["statut_partage"],
                             "en_attente_de_revue",
                             "une entrée de revue vide a tout de même promu la ligne")

    def test_promouvoir_CONCURRENT_ne_perd_pas_l_acte_du_premier_relecteur(self):
        """A-C3 — perte de mise à jour. L'`UPDATE` est CONDITIONNÉ sur
        `statut_partage = 'en_attente_de_revue'` : si un AUTRE geste promeut `ulid`
        entre la lecture de précondition et l'écriture, `rowcount` vaut 0 et
        `promouvoir` lève `ValueError` — l'acte du PREMIER relecteur SURVIT.

        DÉTERMINISTE : un proxy joue la promotion concurrente (Alice, commitée) JUSTE
        AVANT que l'`UPDATE` de Mallory ne parte ; la précondition de Mallory a déjà
        lu `en_attente_de_revue`, mais la ligne ne l'est plus à l'écriture. Mord :
        `UPDATE ... WHERE ulid = ?` inconditionnel (sans `AND statut_partage =
        'en_attente_de_revue'` ni le contrôle `rowcount`) → Mallory écrase Alice,
        aucune `ValueError`, `revue_par == 'Mallory'`."""
        ul = self._poser_generalisee()
        conn = store.connect(self.magasin)
        self.addCleanup(conn.close)

        def promue_par_alice():
            # Un AUTRE geste promeut `ulid` et COMMITE, entre la lecture de
            # précondition et l'écriture de Mallory. Même connexion : aucun verrou
            # inter-connexions à orchestrer, la course est reproduite à l'état près.
            conn.execute(
                "UPDATE " + schema.TABLE + " SET statut_partage = 'revue_faite', "
                "revue_par = 'Alice', revue_horodatage = ? WHERE ulid = ?",
                ("2026-04-04T00:00:00+00:00", ul))
            conn.commit()

        proxy = _InterposeAvantUpdate(conn, promue_par_alice)
        with self.assertRaises(ValueError):
            promotion.promouvoir(proxy, ul, revue_par="Mallory",
                                 horodatage="2026-05-05T00:00:00+00:00")
        relu = store.connect(self.magasin)
        self.addCleanup(relu.close)
        self.assertEqual(lessons.lire_lecon(relu, ul)["revue_par"], "Alice",
                         "l'acte de revue du premier relecteur (Alice) a été écrasé "
                         "par une promotion concurrente")


class PromotionCLITests(_Confine):
    """Témoins 9, 10, 12 : `cadre lessons promote` de bout en bout, CONFINÉ."""

    def _fichier(self, ulid: str) -> Path:
        # Le littéral se joint à l'arbre TEMPORAIRE (self.projet), jamais à ROOT.
        return self.projet / ".agents" / "state" / "lessons" / (ulid + ".json")

    def test_le_fichier_est_ecrit_AVANT_le_commit_et_un_echec_n_ecrit_RIEN(self):
        """TÉMOIN 9 — `Workspace.write_bytes` lève : rollback, la ligne reste
        `en_attente_de_revue`, aucun fichier, code 2. L'échec injecté est un
        `PermissionError` (sous-classe d'`OSError`) — la classe RÉELLE d'un disque
        plein ou d'un `.agents/` en lecture seule, PAS un `ValueError` déjà attrapé
        (A-C1). Mord : `conn.commit()` déplacé AVANT l'écriture → la ligne est
        commitée malgré l'échec ; mord AUSSI : retrait de l'`except OSError` de la
        CLI → l'exception remonte, `main` lève au lieu de rendre 2."""
        ul = self._poser_generalisee()

        def boom(self, *a, **k):
            raise PermissionError(13, "écriture simulée en échec")

        with mock.patch.object(Workspace, "write_bytes", boom):
            rc = cli.main(["lessons", "promote", ul, "--revue-par", "Alice",
                           "--magasin", str(self.magasin)])
        self.assertEqual(rc, 2)
        conn = store.connect(self.magasin)
        self.addCleanup(conn.close)
        self.assertEqual(lessons.lire_lecon(conn, ul)["statut_partage"],
                         "en_attente_de_revue",
                         "la promotion a été commitée malgré l'échec d'écriture")
        self.assertFalse(self._fichier(ul).exists(),
                         "un fichier a été écrit malgré l'échec")

    def test_le_chemin_NOMINAL_ecrit_le_fichier_PUIS_commite(self):
        """TÉMOIN 10 — bout en bout : code 0, le fichier existe SOUS L'ARBRE
        TEMPORAIRE avec les octets canoniques, la ligne est `revue_faite` relue sur
        une connexion DISTINCTE. Mord : `conn.commit()` final retiré → la connexion
        distincte voit encore `en_attente_de_revue`."""
        ul = self._poser_generalisee(contenu="leçon nominale")
        rc = cli.main(["lessons", "promote", ul, "--revue-par", "Alice",
                       "--magasin", str(self.magasin)])
        self.assertEqual(rc, 0)
        # confinement : la cible d'écriture EST l'arbre temporaire, pas le dépôt réel.
        self.assertEqual(project_root(), self.projet.resolve(),
                         "la racine de projet n'est pas l'arbre temporaire confiné")
        f = self._fichier(ul)
        self.assertTrue(f.exists(), "le fichier de leçon promue n'a pas été écrit")
        conn = store.connect(self.magasin)
        self.addCleanup(conn.close)
        row = lessons.lire_lecon(conn, ul)
        self.assertEqual(row["statut_partage"], "revue_faite",
                         "la connexion distincte ne voit pas la promotion — commit manquant")
        attendu = json.dumps(row, ensure_ascii=False, sort_keys=True,
                             indent=2).encode("utf-8") + b"\n"
        self.assertEqual(f.read_bytes(), attendu,
                         "les octets écrits ne sont pas la forme canonique de la ligne")
        # B-(5) : l'acte de revue de la CLI est ENREGISTRÉ — le RELECTEUR passé et la
        # FORME de l'horodatage. Sans ces deux assertions, permuter revue_par et
        # horodatage à l'appel de `promouvoir` (cli.py:105) laissait le témoin vert.
        self.assertEqual(row["revue_par"], "Alice",
                         "le relecteur passé à la CLI n'est pas enregistré")
        self.assertRegex(row["revue_horodatage"], r"^\d{4}-\d{2}-\d{2}T.*\+00:00$",
                         "l'horodatage de revue n'a pas la forme UTC ISO 8601")

    def test_tout_refus_de_promote_sort_en_2_avec_sa_cause_et_sans_traceback(self):
        """TÉMOIN 12 — quatre bras.
        (a) drapeau SURNUMÉRAIRE sur une commande COMPLÈTE → `SystemExit(2)`,
            `stderr` nomme l'option et JAMAIS « NOM RÉSERVÉ ». Mord : rétablir
            `if extra and args.commande not in RESERVEES` → l'option est avalée,
            promote s'exécute et rend 0.
        (b) magasin non-SQLite → `sqlite3.DatabaseError` attrapée, `return 2`,
            `stderr` nomme le magasin illisible, aucun traceback. Mord :
            `except sqlite3.DatabaseError` → `except sqlite3.OperationalError`
            (qui ne couvre pas) → l'exception remonte.
        (c) `main(["lessons"])` nu → `return 2`, `stderr` porte l'usage de promote.
            Mord : retirer la branche `sous_lessons is None` → aide en 0 sur stdout.
        (d) `--magasin` INTROUVABLE → `return 2`, `stderr` nomme « introuvable »,
            AUCUN fichier créé. Mord : retrait du garde `Path(...).is_file()` (A-C5).
        BORNE (A-B2) : l'ordre `IntegrityError` puis `DatabaseError` est PRESCRIT
        et NON prouvé — aucune entrée de la CLI n'atteint un `CHECK`."""
        ul = self._poser_generalisee()

        # (a)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit) as cm:
                cli.main(["lessons", "promote", ul, "--revue-par", "Alice",
                          "--magasin", str(self.magasin), "--zzz-inconnu"])
        self.assertEqual(cm.exception.code, 2)
        self.assertIn("--zzz-inconnu", err.getvalue())
        self.assertNotIn("NOM RÉSERVÉ", err.getvalue())

        # (b)
        bad = self.base / "pas_sqlite.db"
        bad.write_bytes(b"this is not a sqlite database")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = cli.main(["lessons", "promote", ul, "--revue-par", "Alice",
                           "--magasin", str(bad)])
        self.assertEqual(rc, 2)
        self.assertNotIn("Traceback", err.getvalue())
        self.assertIn("illisible", err.getvalue())

        # (c)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = cli.main(["lessons"])
        self.assertEqual(rc, 2)
        self.assertIn("promote", err.getvalue())

        # (d) A-C5/B-(3) : un --magasin INTROUVABLE est refusé AVANT toute ouverture,
        # rc 2, message « introuvable », et AUCUN fichier de 0 octet laissé sur
        # disque. Mord : retrait du garde `Path(...).is_file()` → sqlite3.connect
        # CRÉE le fichier (0 octet) puis « no such table » — le fichier survit.
        absent = self.base / "inexistant.db"
        self.assertFalse(absent.exists(), "le magasin de test existe déjà")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = cli.main(["lessons", "promote", ul, "--revue-par", "Alice",
                           "--magasin", str(absent)])
        self.assertEqual(rc, 2)
        self.assertIn("introuvable", err.getvalue())
        self.assertFalse(absent.exists(),
                         "un fichier de magasin a été créé sur un chemin introuvable")

    def test_un_magasin_disparu_apres_la_sonde_n_est_pas_recree_t770(self):
        """P1 (T-00000770) — le magasin DISPARAÎT entre la garde `is_file()` et
        l'ouverture : rc 2, « a disparu entre la sonde et l'ouverture », et RIEN
        n'est créé à sa place. BASE : `store.connect` recréait un fichier vide,
        puis « magasin illisible ». La disparition est jouée par la garde elle-même
        (`Path.is_file` enveloppé : il répond, PUIS le fichier est retiré)."""
        ul = self._poser_generalisee()
        reel = Path.is_file
        joue: list = []

        def is_file_puis_retire(chemin):
            rendu = reel(chemin)
            if not joue and Path(chemin) == self.magasin:
                joue.append(chemin)
                self.magasin.unlink()
            return rendu

        err = io.StringIO()
        with mock.patch.object(Path, "is_file", is_file_puis_retire), \
                contextlib.redirect_stderr(err):
            rc = cli.main(["lessons", "promote", ul, "--revue-par", "Alice",
                           "--magasin", str(self.magasin)])
        self.assertEqual(len(joue), 1, "banc non armé : la garde n'a pas été jouée")
        self.assertEqual(rc, 2, err.getvalue())
        self.assertIn("a disparu entre la sonde et l'ouverture", err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())
        self.assertFalse(self.magasin.exists(), "un magasin a été recréé à la place")
        self.assertFalse(self._fichier(ul).exists())

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"), "O_NOFOLLOW absent (R3 de T-00000759)")
    def test_un_magasin_lien_vers_un_vrai_magasin_est_refuse_t770(self):
        """P2 (T-00000770) — `--magasin` est un LIEN vers un VRAI magasin portant
        une forme généralisée en attente : rc 2, refus nommé (« lien
        symbolique »), le magasin cible inchangé octet pour octet, aucun fichier
        de leçon écrit. BASE SUIVAIT le lien et promouvait dans le magasin d'un
        autre. Mord : Mp (`store.connect(args.magasin)` rétabli)."""
        import hashlib  # noqa: PLC0415

        ul = self._poser_generalisee()
        avant = hashlib.sha256(self.magasin.read_bytes()).hexdigest()
        lien = self.base / "lien.db"
        os.symlink(self.magasin, lien)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = cli.main(["lessons", "promote", ul, "--revue-par", "Alice",
                           "--magasin", str(lien)])
        self.assertEqual(rc, 2, err.getvalue())
        self.assertIn("lien symbolique", err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())
        self.assertEqual(hashlib.sha256(self.magasin.read_bytes()).hexdigest(), avant,
                         "le magasin cible du lien a été écrit")
        self.assertFalse(self._fichier(ul).exists(), "une leçon a été promue à travers le lien")


class ContratTests(_Confine):
    """Témoin 11 : le contrat déclare EXACTEMENT la feuille publique."""

    def test_seule_la_feuille_promote_est_publique_et_l_espace_reste_reserve(self):
        """TÉMOIN 11 — `contract.lock.json` : `cadre lessons` = reserve,
        `cadre lessons promote` = public ; `CONTRAT-v0.md` porte la ligne de table ;
        `cli.RESERVEES` contient encore `lessons` et `cli.IMPLEMENTEES` ne le
        contient pas. Mord : déplacer `lessons` de RESERVEES vers IMPLEMENTEES →
        rouge ici ET sur test_contract_diff.py::ContractDiffTests
        .test_un_nom_reserve_de_la_CLI_est_promis_au_verrou (recoupement)."""
        verrou = json.loads((ROOT / "contract.lock.json").read_text(encoding="utf-8"))
        cli_par_nom = {e["element"]: e for e in verrou["elements"] if e["type"] == "cli"}
        self.assertEqual(cli_par_nom["cadre lessons"]["statut"], "reserve",
                         "l'espace `cadre lessons` ne doit PAS devenir public")
        self.assertIn("cadre lessons promote", cli_par_nom,
                      "la feuille `cadre lessons promote` n'est pas au verrou")
        self.assertEqual(cli_par_nom["cadre lessons promote"]["statut"], "public")
        self.assertEqual(cli_par_nom["cadre lessons promote"]["type"], "cli")

        doc = (ROOT / "docs" / "contrat" / "CONTRAT-v0.md").read_text(encoding="utf-8")
        self.assertRegex(
            doc, r"(?m)^\|\s*`cadre lessons promote`\s*\|\s*cli\s*\|\s*public\s*\|",
            "CONTRAT-v0.md ne porte pas la ligne de table `cadre lessons promote`")

        self.assertIn("lessons", cli.RESERVEES,
                      "`lessons` doit RESTER un espace réservé de la CLI")
        self.assertNotIn("lessons", cli.IMPLEMENTEES,
                         "`lessons` ne doit PAS entrer dans IMPLEMENTEES (l'espace reste réservé)")

        # A-C7 — assertion de COMPORTEMENT qui LIE la feuille publique au CODE. Les
        # nets de contrat tronquent l'élément à `mots[1]` (`lessons`), donc aucun ne
        # rougirait si `_lessons_promote` disparaissait. `cadre lessons promote` sans
        # argument DOIT lever `SystemExit(2)` (argparse : ulid/--revue-par/--magasin
        # requis), pas retomber sur le rappel d'usage. Mord : retrait du sous-parseur
        # `promote` → « invalid choice » ou rappel d'usage, `stderr` sans « ulid ».
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit) as cm:
                cli.main(["lessons", "promote"])
        self.assertEqual(cm.exception.code, 2)
        self.assertIn("ulid", err.getvalue().lower(),
                      "le verrou déclare `cadre lessons promote` PUBLIQUE mais la CLI "
                      "n'exige plus l'ulid — la feuille n'est plus exposée")


if __name__ == "__main__":
    unittest.main()
