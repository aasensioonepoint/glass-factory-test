"""Kit sans `agentic_v3` : la `sync_outbox` est bornée par le déversement de T-00001006 (T-00001052, S-00003315).
(Rév. 2 : 15 témoins, un par GARDE écrite ; la table des mutants dit lequel retire laquelle. Plus S6c, l'arme
`ValueError` du pré-contrôle, réserve B-C3 de S-00003521 ; et S13, la garde FIFO de T-00001006 face à un déversement
kit seul : 17 témoins.)

Sans `agentic_v3` sous la racine du code, `replay_sync` sortait par deux `return 0` muets (dossier absent, ou paquet
incomplet : `ModuleNotFoundError` sur `agentic_v3.*`) : aucun drain, l'outbox croissait d'un intent par tâche changée
(mesuré à 4f46233c : 205 `new` -> 205 intents, 0 ligne stderr). Les deux sorties déversent désormais l'excédent au-delà
de `_SYNC_OUTBOX_SEUIL` dans le fichier local de T-00001006. Aucun pont ne se construit ici : le fichier n'est rejoué
qu'une fois `agentic_v3` présent (S2 le prouve), et une ligne `TASKS: agentic_v3 absent` dit sa taille.

Kit seul SIMULÉ par `tasks.__file__` -> `<bac>/kit/.agents/bin/tasks.py` (précédent : SYM-02924 de test_tasks.py) ;
`events.py` y est copié pour que l'émission soit réelle. Montage EMPRUNTÉ par référence, jamais hérité.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sqlite3
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

import test_tasks_pont_v3 as base
import test_tasks_pont_v3_deverse as deverse

tasks = base.tasks


class KitSansAgenticV3Tests(unittest.TestCase):
    setUp_base = base.PontV3RefuseNeGelePasLeBoardTests.setUp
    _main = base.PontV3RefuseNeGelePasLeBoardTests._main
    _board = base.PontV3RefuseNeGelePasLeBoardTests._board
    _lignes = staticmethod(base.PontV3RefuseNeGelePasLeBoardTests._lignes)
    _seuil = deverse.DeversementSousRefusTests._seuil
    _auteur = deverse.DeversementSousRefusTests._auteur
    _deverses = deverse.DeversementSousRefusTests._deverses
    _outbox = deverse.DeversementSousRefusTests._outbox
    _raisons = deverse.DeversementSousRefusTests._raisons
    _v3 = deverse.DeversementSousRefusTests._v3
    _relever = deverse.DeversementSousRefusTests._relever
    fichier = deverse.DeversementSousRefusTests.fichier

    def setUp(self) -> None:
        tasks._RESOLVEUR_V3.charger_paquet(base.REPO, "agentic_v3")
        self.setUp_base()
        self.kit = Path(self.tmp.name).resolve() / "kit"  # résolu : tasks_sync lit `Path(__file__).resolve()` (macOS : /var → /private/var, T-00001092)
        (self.kit / ".agents" / "bin").mkdir(parents=True)
        (self.kit / ".agents" / "bin" / "tasks.py").write_text("# kit sans agentic_v3\n", encoding="utf-8")
        shutil.copy(Path(base.TASKS_PATH).with_name("events.py"), self.kit / ".agents" / "bin" / "events.py")
        # FRÈRES D'ALLOCATION (plan T-00000726, E20) : ce kit factice ALLOUE (`new`), il porte donc `record_id.py`
        # et le générateur `ids.py`, comme tout harnais qui alloue (E13). Copie INCONDITIONNELLE :
        # un frère absent fait échouer le montage, jamais sauter le provisionnement en silence. `redaction.py`
        # n'est PAS posé : S4b caractérise justement le kit qui ne l'a pas (R31). Source : le paquet `cadre` où
        # il vit (`exiger`, vendor d'abord) ; destination : le repli `src/cadre/ledger/ids.py` du `record_id.py`
        # copié, le kit ne copiant pas `vendor_paths.py` (S-01M5BXT85VP4JBBMXVXR9STP5F).
        self.cadre = tasks._RESOLVEUR_V3.exiger(base.REPO, "cadre")
        shutil.copy(Path(base.TASKS_PATH).with_name("record_id.py"), self.kit / ".agents" / "bin" / "record_id.py")
        generateur = self.kit / "src" / "cadre" / "ledger"
        generateur.mkdir(parents=True)
        shutil.copy(self.cadre / "ledger" / "ids.py", generateur / "ids.py")
        self.assertFalse((self.kit / "agentic_v3").exists())

    def _seul(self):
        return mock.patch.object(tasks, "__file__", str(self.kit / ".agents" / "bin" / "tasks.py"))

    def _commandes(self, n: int, *, seuil: int | None = None) -> tuple[list[str], str]:
        """`n` `new` sous kit seul ; rend (operation_id écrits dans l'ordre, stderr cumulé) ; borne vérifiée à CHAQUE commande."""
        ecrits, erreurs = [], ""
        borne = seuil if seuil is not None else tasks._SYNC_OUTBOX_SEUIL
        with self._seul(), (self._seuil(seuil) if seuil is not None else mock.patch.object(tasks, "_SYNC_OUTBOX_SEUIL", borne)):
            for i in range(n):
                vus = set(self._outbox()) | set(self._deverses())
                rc, _out, err = self._main("new", f"s{i}")
                self.assertEqual(0, rc, err)
                erreurs += err
                ecrits += [o for o in self._deverses() + self._outbox() if o not in vus and o not in ecrits]
                self.assertLessEqual(len(self._outbox()), borne, f"borne dépassée à la commande {i + 1}")
        return ecrits, erreurs

    def test_vendor_seul_present(self) -> None:
        """Un paquet sous vendor seul est présent, même si sa copie volontairement incomplète ne peut être drainée."""
        paquet = self.kit / ".agents" / "vendor" / "agentic_v3"
        paquet.mkdir(parents=True)
        (paquet / "__init__.py").write_text("", encoding="utf-8")
        self.assertFalse((self.kit / "agentic_v3").exists())
        with mock.patch.dict(sys.modules) as modules, self._seul(), self._seuil(0):
            for nom in [n for n in modules if n == "agentic_v3" or n.startswith("agentic_v3.")]:
                modules.pop(nom)
            rc, _out, err = self._main("new", "vendor")
        self.assertEqual(0, rc, err)
        self.assertIn("TASKS: agentic_v3 non chargé dans ", err)
        self.assertIn("paquet incomplet", err)
        self.assertNotIn("TASKS: agentic_v3 absent", err)
        self.assertEqual(1, len(self._deverses()))

    def test_S1_205_commandes_sans_agentic_v3_outbox_200_et_205_retrouvables(self) -> None:
        """Critère de BK-765, seuil de production NON patché."""
        self.assertEqual(200, tasks._SYNC_OUTBOX_SEUIL)
        ecrits, _ = self._commandes(205)
        self.assertEqual(205, len(ecrits))
        self.assertEqual(200, len(self._outbox()))
        self.assertEqual(5, len(self._deverses()))
        self.assertEqual(ecrits, self._deverses() + self._outbox(), "ordre FIFO rompu ou intent perdu")
        self.assertEqual(205, len(set(self._deverses() + self._outbox())), "doublon")
        self.assertEqual(set(ecrits), set(self._board()["sync_correlations"]))

    def test_S2_agentic_v3_installe_ensuite_le_premier_drain_rejoue_tout_et_V3_est_complet(self) -> None:
        ecrits, _ = self._commandes(5, seuil=3)
        self.assertEqual(2, len(self._deverses()))
        fichier = self.fichier
        with self._seuil(3):
            err = self._relever(ecrits)  # `tasks.__file__` réel : agentic_v3 présent
        self.assertEqual(1, len(self._lignes(err, "2 intent(s) déversé(s) réinjecté(s) en tête, 0 écarté(s)")))
        self.assertEqual(1, len(list(fichier.parent.glob(fichier.name + ".rejoue-*"))))

    def test_S3_une_ligne_absent_par_deversement_avec_la_taille_en_octets_et_silence_sous_le_seuil(self) -> None:
        _, err = self._commandes(3, seuil=3)
        self.assertEqual("", err, "un kit seul sous le seuil reste muet, comme avant")
        _, err = self._commandes(2, seuil=3)
        absent = self._lignes(err, "TASKS: agentic_v3 absent")
        self.assertEqual(2, len(absent))
        self.assertEqual(2, len(self._lignes(err, "AU SEUIL")))
        self.assertEqual(
            f"TASKS: agentic_v3 absent de {self.kit} — aucun pont ne se construit ici : {self.fichier} n'est ni rejoué "
            f"ni vidé tant qu'agentic_v3 n'est pas installé ({self.fichier.stat().st_size} octets)", absent[-1])

    def _sans_paquet_cadre(self):
        return mock.patch.dict(sys.modules, {"cadre": None, "cadre.ledger": None, "cadre.ledger.redaction": None})

    def _donnees(self) -> list[dict]:
        donnees = []
        for f in sorted(Path(os.environ["AGENTS_EVENTS_DIR"]).glob("*.jsonl")):
            for ligne in f.read_text(encoding="utf-8").splitlines():
                r = json.loads(ligne)
                if r.get("kind") == "gate.coverage_degraded":
                    donnees.append(r.get("data"))
        return donnees

    def test_S4a_kit_avec_redaction_evenement_de_deversement_seul_aucune_raison_de_refus(self) -> None:
        # `redaction.py` posé aux DEUX lieux, dont le lieu que lit events.py (`_CHEMIN_REDACTION`) (S-01M5BXT85VP4JBBMXVXR9STP5F).
        for red in (self.kit / "src" / "cadre" / "ledger", self.kit / ".agents" / "vendor" / "cadre" / "ledger"):
            red.mkdir(parents=True, exist_ok=True)  # `src/…` déjà créé par le provisionnement de `ids.py` (setUp, E20)
            shutil.copy(self.cadre / "ledger" / "redaction.py", red / "redaction.py")
        with self._sans_paquet_cadre():
            self._commandes(5, seuil=3)
        self.assertEqual(["sync-outbox-deverse", "sync-outbox-deverse"], self._raisons())

    def test_S4b_kit_sans_redaction_la_ligne_existe_mais_la_raison_est_neutralisee(self) -> None:
        """BORNE ADOPTANT d'events.py, CARACTÉRISÉE : ni clone du kit ni paquet `cadre` -> `data` neutralisé."""
        with self._sans_paquet_cadre():
            self._commandes(5, seuil=3)
        self.assertEqual([{"redaction_unavailable": True}] * 2, self._donnees())

    def test_S5_paquet_agentic_v3_incomplet_seconde_sortie_deverse_aussi(self) -> None:
        erreurs = ""
        with mock.patch.dict(sys.modules, {"agentic_v3.reconciliation.board_bridge": None}), self._seuil(3):
            for i in range(5):
                rc, _out, err = self._main("new", f"m{i}")
                self.assertEqual(0, rc, err)
                erreurs += err
        self.assertEqual(3, len(self._outbox()))
        self.assertEqual(2, len(self._deverses()))
        self.assertEqual(2, len(self._lignes(erreurs, "AU SEUIL")))
        # Paquet présent mais incomplet : `non chargé`, sa cause dite, jamais `absent` (T-01M5BXTGX5YN8XEXTG1PP7A5ZX).
        non_charge = self._lignes(erreurs, "TASKS: agentic_v3 non chargé dans ")
        self.assertEqual(2, len([ligne for ligne in non_charge if " (paquet incomplet : " in ligne]), erreurs)
        self.assertEqual([], self._lignes(erreurs, "TASKS: agentic_v3 absent"))
        self.assertEqual(["sync-outbox-deverse", "sync-outbox-deverse"], self._raisons())

    def test_S5b_un_ModuleNotFoundError_d_un_autre_nom_remonte_sans_deverser(self) -> None:
        """Garde du NOM, sortie 2 : seul `agentic_v3.*` est un kit seul. Un arriéré de 5 attend : un déversement
        AVANT la garde, ou sans elle, le ramènerait à 3 ; la levée doit remonter, l'arriéré intact."""
        self._commandes(5, seuil=10**6)

        def _lever(nom: str) -> None:
            raise ModuleNotFoundError("No module named 'cadre'", name="cadre")

        faux = types.ModuleType("agentic_v3.reconciliation.board_bridge")
        faux.__getattr__ = _lever
        with mock.patch.dict(sys.modules, {"agentic_v3.reconciliation.board_bridge": faux}), self._seuil(3):
            with self.assertRaises(ModuleNotFoundError):
                tasks.replay_sync(str(self.root))
        self.assertEqual((5, 0), (len(self._outbox()), len(self._deverses())))

    def test_S6_board_illisible_BoardError_aucun_deversement_impossible_et_replay_sync_ne_leve_pas(self) -> None:
        self.board.write_text("{pas du json", encoding="utf-8")
        with self._seul():
            rc, _out, err = self._main("new", "x")
            with mock.patch("sys.stderr"):
                self.assertEqual(0, tasks.replay_sync(str(self.root)), "comme avant : le board n'est pas lu ici")
        self.assertNotEqual(0, rc)
        self.assertEqual([], self._lignes(err, "déversement IMPOSSIBLE"))
        self.assertEqual([], self._raisons())

    def test_S6b_board_illisible_par_OSError_replay_sync_rend_0_comme_avant(self) -> None:
        with self._seul(), mock.patch.object(tasks, "load", side_effect=PermissionError(13, "banc")):
            rc, out, err = self._main("replay-sync")
        self.assertEqual(0, rc, err)
        self.assertIn("replayed 0", out)
        self.assertEqual([], self._lignes(err, "déversement IMPOSSIBLE"))
        self.assertEqual([], self._raisons())

    def test_S6c_board_non_UTF8_replay_sync_rend_0_comme_avant(self) -> None:
        """Arme `ValueError` (réserve B-C3) : `load` ne convertit que `JSONDecodeError` ; un board non UTF-8 lève
        `UnicodeDecodeError`. Avant T-00001052, `replay-sync` en kit seul ne lisait pas le board : rc 0, il le reste."""
        self.board.write_bytes(b'{"next_id": 2, "tasks": [{"id": "T-00000001", "state": "pending", "task": "caf\xe9"}]}')
        with self._seul():
            rc, out, err = self._main("replay-sync")
        self.assertEqual(0, rc, err)
        self.assertIn("replayed 0", out)
        self.assertEqual([], self._lignes(err, "déversement IMPOSSIBLE"))
        self.assertEqual([], self._raisons())

    def test_S7_kit_mis_a_jour_avec_un_arriere_deverse_d_un_bloc(self) -> None:
        ecrits, err = self._commandes(6, seuil=10**6)
        self.assertEqual("", err)
        e2, err = self._commandes(1, seuil=3)
        self.assertEqual(3, len(self._outbox()))
        self.assertEqual(4, len(self._deverses()))
        self.assertEqual(ecrits + e2, self._deverses() + self._outbox())
        self.assertEqual(1, len(self._lignes(err, "— 3 intent(s) déversé(s)")), "avant le verbe : l'arriéré")
        self.assertEqual(1, len(self._lignes(err, "— 1 intent(s) déversé(s)")), "après le verbe : son intent")
        self.assertEqual(2, len(self._lignes(err, "TASKS: agentic_v3 absent")))

    def test_S8_replay_sync_explicite_kit_seul_borne_aussi_et_rend_0(self) -> None:
        self._commandes(5, seuil=10**6)
        with self._seul(), self._seuil(3):
            rc, out, err = self._main("replay-sync")
        self.assertEqual(0, rc, err)
        self.assertIn("replayed 0", out)
        self.assertEqual((3, 2), (len(self._outbox()), len(self._deverses())))

    def test_S9_appel_direct_sans_memo_borne_et_se_tait_sur_le_canal(self) -> None:
        self._commandes(5, seuil=10**6)
        with self._seul(), self._seuil(3), mock.patch("sys.stderr"):
            self.assertEqual(0, tasks.replay_sync(str(self.root)))
        self.assertEqual((3, 2), (len(self._outbox()), len(self._deverses())))
        self.assertEqual([], self._raisons(), "hors commande : aucun événement (T-00001006, D11)")

    def test_S10_deversement_impossible_la_ligne_absent_n_est_pas_dite(self) -> None:
        """Garde `is None` : si le déversement échoue (chemin du fichier = un DOSSIER, `OSError`), rien n'est écrit,
        donc aucune taille n'est annoncée ; seule la ligne « IMPOSSIBLE » de T-00001006 et son événement."""
        self._commandes(3, seuil=3)
        self.fichier.mkdir(parents=True, exist_ok=True)
        with self._seul(), self._seuil(3):
            rc, _out, err = self._main("new", "z")
        self.assertEqual(0, rc, err)
        self.assertEqual(1, len(self._lignes(err, "déversement IMPOSSIBLE")))
        self.assertEqual([], self._lignes(err, "TASKS: agentic_v3 absent"))
        self.assertEqual(1, len(self._donnees()), "un seul événement : le déversement impossible de T-00001006")

    def test_S11_taille_illisible_est_dite_sans_lever_et_la_taille_lue_est_en_octets(self) -> None:
        bac = Path(self.tmp.name) / "taille.bin"
        self.assertTrue(tasks._taille_deverse(bac).startswith("taille illisible : "))
        bac.write_bytes(b"123456")
        self.assertEqual("6 octets", tasks._taille_deverse(bac))

    def test_S12_premiere_commande_d_un_kit_sans_board_aucune_levee(self) -> None:
        """`load` d'un board ABSENT rend `{"tasks": []}` (sans compteur depuis T-00000726), SANS `sync_outbox` : le pré-contrôle lit ce défaut."""
        self.board.rename(self.board.with_name("TASKS.json.avant"))  # board ABSENT, rien n'est supprimé
        with self._seul():
            rc, _out, err = self._main("new", "premier")
        self.assertEqual(0, rc, err)
        self.assertEqual(1, len(self._board()["tasks"]))

    def test_S13_un_deversement_kit_seul_pendant_un_drain_V3_vivant_ne_depasse_rien(self) -> None:
        """Garde FIFO de T-00001006 face à un kit seul. Sans `agentic_v3`, aucun drain n'a lieu : les deux sorties rendent
        0 AVANT `drain_sync_outbox`, donc `claim_sync_event` n'est jamais atteint. Mais un kit seul déverse dans le MÊME
        fichier que sous refus (`_chemin_deverse`). Né pendant un drain V3 vivant sur ce board (un kit seul lancé par
        `--root`), il arrête ce drain (rien n'est réservé tant que le fichier existe) ; le drain suivant le rejoue
        d'abord ; V3 reçoit [0..4] dans l'ordre d'écriture. Mutant k22, garde `lexists` retirée : W dépasse P, rend 3."""
        ecrits, _ = self._commandes(5, seuil=10**6)
        vrai, appels = tasks.claim_sync_event, []

        def claim(root, owner, **kw):
            appels.append(owner)
            if len(appels) == 2:  # P, kit seul, entre l'ACK du premier intent et le claim suivant de W
                with self._seuil(2):
                    tasks._deverser_sans_pont(root, self.kit, None)
                self.assertEqual(ecrits[1:3], self._deverses(), "P n'a rien déversé : le banc ne mesure rien")
            return vrai(root, owner, **kw)

        with self._auteur():
            with mock.patch.object(tasks, "claim_sync_event", claim), mock.patch("sys.stderr", io.StringIO()):
                self.assertEqual(1, tasks.replay_sync(str(self.root)))
            self.assertTrue(self.fichier.exists(), "le déversement de P a disparu pendant le drain de W")
            self.assertEqual(ecrits[3:], self._outbox(), "W a dépassé le déversement de P")
        self._relever(ecrits)
        c = sqlite3.connect(str(self.store))
        try:
            ordre = [r[0] for r in c.execute("SELECT operation_id FROM board_sync_inbox ORDER BY rowid")]
        finally:
            c.close()
        self.assertEqual(list(range(5)), [ecrits.index(o) for o in ordre])


if __name__ == "__main__":
    unittest.main()
