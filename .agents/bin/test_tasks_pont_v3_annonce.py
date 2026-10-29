"""Annonce du pont V3 refusé : dite APRÈS le verbe, selon son issue (T-00001007, points g, h, i de T-00000792).

L'annonce « pont V3 REFUSÉ …, board écrit … » partait au PREMIER drain, AVANT le verbe, et restait affichée s'il
échouait (mesuré : `start T-99999` sous lien -> « board écrit » puis « unknown task id », rc 2). `main` pose
`differer` sur le mémo d'un verbe mutant ; `replay_sync` range l'annonce, `_annoncer_refus_pont` la dit après le
verbe : telle quelle s'il aboutit (T21), « verbe refusé — board NON écrit » sur `BoardError` (T20, et T6 de la base)
comme sur le `RecordIdError` d'une allocation sans générateur ULID (T27, C6 de T-00000726), « verbe interrompu —
écriture du board NON confirmée » sur toute autre levée (T23). Tout autre appelant de
`replay_sync` reçoit la ligne aussitôt (T4b et R4 de la base, inchangés). Au DRAIN, `EmplacementRefuse` de la couture
reprend le libellé REFUSÉ, épinglé EN ENTIER (T22) ; son docstring, lu dans la SOURCE, renvoie PAR NOM à l'exception
mesurée (T24). La fenêtre du report est CLOSE avant le drain d'après le verbe : un refus que ce drain est le premier à
voir (racine nue, saut non mémorisé, S-00003321) se dit aussitôt, « board écrit » (T25) ; `--statusline` combiné à un
verbe mutant ne draine ni n'annonce rien (T26).

Montage EMPRUNTÉ à `test_tasks_pont_v3.PontV3RefuseNeGelePasLeBoardTests` (fonctions référencées, jamais héritées :
aucun témoin de la base n'est recollecté ici), patron de `test_tasks_pont_v3_deverse.py`. Règle (relevée à 1600 par S-00004034) des 800 lignes
(S-00002684) : module neuf.
"""
from __future__ import annotations

import ast
import io
import json
import os
import re
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

import test_tasks_pont_v3 as base

tasks = base.tasks


class AnnonceApresLeVerbeTests(unittest.TestCase):
    setUp = base.PontV3RefuseNeGelePasLeBoardTests.setUp
    _main = base.PontV3RefuseNeGelePasLeBoardTests._main
    _board = base.PontV3RefuseNeGelePasLeBoardTests._board
    _lignes = staticmethod(base.PontV3RefuseNeGelePasLeBoardTests._lignes)
    _poser_lien = base.PontV3RefuseNeGelePasLeBoardTests._poser_lien
    _cible_intacte = base.PontV3RefuseNeGelePasLeBoardTests._cible_intacte
    _drain_direct = base.PontV3RefuseNeGelePasLeBoardTests._drain_direct
    _amorcer_store = base.PontV3RefuseNeGelePasLeBoardTests._amorcer_store
    _racine_nue = base.PontV3RefuseNeGelePasLeBoardTests._racine_nue
    _main_sous = base.PontV3RefuseNeGelePasLeBoardTests._main_sous
    LIBELLE_DRAIN = "REFUSÉ (emplacement du store refusé — lien, second nom, non régulier ou autre)"

    def test_T20_verbe_refuse_sous_lien_dit_board_NON_ecrit_une_fois(self) -> None:
        """`start T-99999` sous lien : rc 2, UNE ligne de refus qui dit « verbe refusé — board NON écrit », AVANT
        le message du verbe. MUTATIONS : report retiré -> « board écrit » revient ; flush du `except BoardError`
        retiré -> « verbe interrompu » (le `finally`) au lieu de « verbe refusé »."""
        self._poser_lien()
        rc, _out, err = self._main("start", "T-99999")
        self.assertEqual(2, rc, err)
        self.assertIn("unknown task id", err)
        self.assertNotIn("board écrit", err)
        refus = self._lignes(err, "pont V3 REFUSÉ")
        self.assertEqual(1, len(refus), err)
        self.assertIn("verbe refusé — board NON écrit", refus[0])
        self.assertLess(err.index("pont V3 REFUSÉ"), err.index("unknown task id"), err)
        self._cible_intacte()

    def test_T21_l_annonce_part_APRES_le_verbe_qui_aboutit(self) -> None:
        """Une sonde autour de `new_task` relève stderr quand le verbe commence : aucune ligne `pont V3` ; après,
        UNE ligne qui dit « board écrit » (vrai désormais), AVANT la ligne `AU SEUIL` du drain d'après (seuil
        ramené à 0). MUTATIONS : report retiré -> la sonde voit la ligne ; flush de succès retiré -> « verbe
        interrompu » (le `finally`) ; flush posé APRÈS le drain d'après -> ordre inversé."""
        self._poser_lien()
        err, vu = io.StringIO(), {}
        original = tasks.new_task

        def sonde(*args: Any, **kwargs: Any) -> Any:
            vu["au_verbe"] = err.getvalue()
            return original(*args, **kwargs)

        with mock.patch.object(tasks, "new_task", side_effect=sonde), \
                mock.patch.object(tasks, "_SYNC_OUTBOX_SEUIL", 0), \
                mock.patch("sys.stdout", io.StringIO()), mock.patch("sys.stderr", err):
            rc = tasks.main(["--root", str(self.root), "new", "sonde"])
        self.assertEqual(0, rc, err.getvalue())
        self.assertIn("au_verbe", vu, "la sonde n'a pas été atteinte : témoin vide")
        self.assertNotIn("pont V3", vu["au_verbe"])
        refus = self._lignes(err.getvalue(), "pont V3 REFUSÉ")
        self.assertEqual(1, len(refus), err.getvalue())
        self.assertIn("board écrit sans relecture V3", refus[0])
        self.assertNotIn("verbe interrompu", err.getvalue())
        self.assertIn("AU SEUIL", err.getvalue(), "précondition : le drain d'après a déversé")
        self.assertLess(err.getvalue().index("pont V3 REFUSÉ"), err.getvalue().index("AU SEUIL"), err.getvalue())

    def test_T22_EmplacementRefuse_au_drain_reprend_le_libelle_REFUSE(self) -> None:
        """(h). (1) Drain direct, tout hôte : classe de COUTURE -> « REFUSÉ (emplacement du store refusé » ;
        homonyme LOCAL -> reste « echec inattendu du consumer » (MUTATION comparaison par NOM -> rougit). (2) VRAI
        CANAL : pont construit sur un store réel, store remplacé par un lien avant le drain d'après ->
        `get_db_connection` lève la classe de couture ; rc 0, intent gardé. MUTATIONS branche (h) retirée, ou queue du
        libellé tronquée ou changée (épinglé EN ENTIER) -> rougit."""
        classe = self.run_export._couture_ledger_store()[0].EmplacementRefuse

        class EmplacementRefuse(ValueError):
            """Homonyme local : même nom, AUTRE classe que celle de la couture."""

        for bras, exc, attendu, absent in (
                ("classe de couture", classe("lien au store (banc)"), self.LIBELLE_DRAIN, "echec inattendu"),
                ("homonyme local", EmplacementRefuse("homonyme"), "echec inattendu du consumer", "REFUSÉ")):
            with self.subTest(bras=bras):
                lignes = self._lignes(self._drain_direct(exc), "miroir V3")
                self.assertEqual(1, len(lignes), lignes)
                self.assertIn(f"miroir V3 — {attendu}", lignes[0])
                self.assertNotIn(absent, lignes[0])
        self._amorcer_store()
        construire, store, cible = self.board_bridge.BoardBridge, self.store, self.cible

        def construire_puis_lier(*args: Any, **kwargs: Any) -> Any:
            pont = construire(*args, **kwargs)
            for suffixe in ("", *base.ANNEXES):
                chemin = store.with_name(store.name + suffixe)
                if chemin.exists():
                    chemin.unlink()
            try:
                os.symlink(cible, store)
            except (OSError, NotImplementedError) as exc:
                raise unittest.SkipTest(f"lien symbolique impossible ici : {exc}") from exc
            return pont

        with mock.patch.object(self.board_bridge, "BoardBridge", side_effect=construire_puis_lier), \
                mock.patch.object(self.run_export, "_email_git", return_value="banc@test"):
            rc, _out, err = self._main("new", "sonde")
        self.assertEqual(0, rc, err)
        self.assertEqual(1, len(self._lignes(err, f"miroir V3 — {self.LIBELLE_DRAIN}")), err)
        self.assertNotIn("echec inattendu", err)
        self.assertGreaterEqual(len(self._board().get("sync_outbox", [])), 1)

    def test_T23_verbe_interrompu_hors_BoardError_le_refus_reste_dit(self) -> None:
        """Une levée hors `BoardError` pendant le verbe laisse UNE ligne « verbe interrompu — écriture du board NON
        confirmée », puis l'exception remonte. MUTATION `finally` retiré -> aucune ligne `pont V3`, rougit."""
        self._poser_lien()
        err = io.StringIO()
        with mock.patch.object(tasks, "new_task", side_effect=RuntimeError("banc : verbe interrompu")), \
                mock.patch("sys.stdout", io.StringIO()), mock.patch("sys.stderr", err):
            with self.assertRaises(RuntimeError):
                tasks.main(["--root", str(self.root), "new", "sonde"])
        refus = self._lignes(err.getvalue(), "pont V3 REFUSÉ")
        self.assertEqual(1, len(refus), err.getvalue())
        self.assertIn("verbe interrompu — écriture du board NON confirmée", refus[0])
        self.assertNotIn("board écrit", err.getvalue())

    def test_T24_EmplacementRefuse_renvoie_PAR_NOM_a_l_exception_mesuree(self) -> None:
        """(i) : le docstring d'`EmplacementRefuse`, lu dans la SOURCE de `ledger/store.py` du paquet `cadre` du dépôt,
        là où le résolveur le trouve (`.agents/vendor/cadre` ou l'ancien `src/cadre` ; jamais dans la classe de la
        couture : un paquet `cadre` installé plus ancien la ferait mentir), nomme
        `tasks_sync.py::replay_sync` ; `tasks_sync.py` ne renvoie plus à AUCUNE plage `store.py:N` (F9 : locator par
        nom ; `\\b` n'attrape pas `event_store.py:5`). MUTATIONS renvoi retiré, ou une plage remise -> rougit."""
        cadre = tasks._RESOLVEUR_V3.exiger(base.REPO, "cadre")  # S-01M5BXT85VP4JBBMXVXR9STP5F
        store = ast.parse((cadre / "ledger" / "store.py").read_text(encoding="utf-8"))
        classe = next(n for n in ast.walk(store) if isinstance(n, ast.ClassDef) and n.name == "EmplacementRefuse")
        self.assertIn("tasks_sync.py::replay_sync", ast.get_docstring(classe) or "")
        source = Path(base.__file__).with_name("tasks_sync.py").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"\bstore\.py:\d", source))

    def _store_futur(self, nue: Path) -> Path:
        """Emplacement du store de `nue` une fois `.agents/` créé : `DEFAULT_DB_PATH` (publique) sur la même racine."""
        from agentic_v3.db.schema import DEFAULT_DB_PATH

        marque = nue / ".agents"
        marque.mkdir()
        try:
            return DEFAULT_DB_PATH(nue)
        finally:
            marque.rmdir()

    def test_T25_refus_vu_au_seul_drain_d_apres_dit_board_ecrit_jamais_interrompu(self) -> None:
        """Racine nue : le 1er drain SAUTE (non mémorisé, S-00003321), le verbe crée `.agents/`, le drain d'après est
        le PREMIER à voir le store refusé (octets non SQLite posés à l'emplacement futur). rc 0, board écrit, UNE ligne `pont V3
        REFUSÉ` qui dit « board écrit sans relecture V3 », jamais « interrompu ». MUTATION fenêtre de report non close
        avant le drain d'après -> l'annonce se range, le `finally` la dit « interrompu » : rougit."""
        nue = self._racine_nue()
        futur = self._store_futur(nue)
        futur.parent.mkdir(parents=True, exist_ok=True)
        futur.write_bytes(b"pas du sqlite" * 100)  # store non SQLite : refus à la construction, sans privilège de lien
        rc, _out, err = self._main_sous(nue, "new", "sonde")
        self.assertEqual(0, rc, err)
        board = json.loads((nue / ".agents" / "state" / "board" / "TASKS.json").read_text(encoding="utf-8"))
        self.assertEqual(["sonde"], [t["task"] for t in board["tasks"]])
        refus = self._lignes(err, "pont V3 REFUSÉ")
        self.assertEqual(1, len(refus), err)
        self.assertIn("board écrit sans relecture V3", refus[0])
        self.assertNotIn("interrompu", err)

    def test_T26_statusline_combine_a_un_verbe_mutant_ne_draine_ni_n_annonce(self) -> None:
        """`--statusline new sonde` sous store refusé : le drapeau saute le verbe (rc 0, rien d'écrit), donc aucun drain et
        aucune ligne `pont V3` — « board écrit » serait faux. Le même verbe SANS `--statusline` refuse bien le pont
        (précondition : témoin non creux). MUTATION `and not args.statusline` retiré -> rougit."""
        self.store.write_bytes(b"pas du sqlite" * 100)  # store refusé sans privilège de lien
        rc, _out, err = self._main("--statusline", "new", "sonde")
        self.assertEqual(0, rc, err)
        self.assertEqual([], self._board()["tasks"], "le verbe a tourné malgré --statusline")
        self.assertNotIn("pont V3", err)
        self.assertNotIn("board écrit", err)
        rc, _out, err = self._main("new", "témoin")
        self.assertEqual(0, rc, err)
        self.assertEqual(1, len(self._lignes(err, "pont V3 REFUSÉ")), err)

    def test_T27_RecordIdError_au_new_dit_verbe_refuse_jamais_interrompu(self) -> None:
        """C6 (T-00000726, 7bis S5) : refus de pont EN ATTENTE puis `new` sans id frappable ⇒ rc 2,
        « verbe refusé — board NON écrit », jamais « verbe interrompu », aucune tâche au board. Le témoin
        CLI de `test_record_id.py` (`test_e_c2_cli…`) ne pose aucun refus de pont : il ne peut pas rougir ici.
        MUTANT M45pont : l'appel `_annoncer_refus_pont` retiré de la clause `RuntimeError` de `main` ⇒ le
        `finally` dit « verbe interrompu » : rouge."""
        self._poser_lien()
        rid = tasks.record_id_module()
        with mock.patch.object(rid, "_ids", side_effect=rid.RecordIdError("générateur ULID introuvable : banc")):
            rc, _out, err = self._main("new", "sonde")
        self.assertEqual(2, rc, err)
        self.assertIn("générateur ULID introuvable : banc", err)
        refus = self._lignes(err, "pont V3 REFUSÉ")
        self.assertEqual(1, len(refus), err)
        self.assertIn("verbe refusé — board NON écrit", refus[0])
        self.assertNotIn("verbe interrompu", err)
        self.assertEqual([], self._board()["tasks"], "un refus d'allocation a écrit une tâche")
        self._cible_intacte()


if __name__ == "__main__":
    unittest.main()
