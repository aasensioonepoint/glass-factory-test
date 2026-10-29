"""T-01M4M175MY8RRRVFN7QRV48566 (E-26) : la remise en file du déversement par TRANCHES bornées (Outbox O2).

Au-delà de `_TRANCHE_REINJECTION` (50) intents au fichier de déversement, le drain ne remet EN FILE qu'une tranche à
la tête du board ; le reste attend au fichier ; la tranche livrée, la suivante est remise en file dans le même drain ;
un drain en échec ne restitue que la tranche. Un marqueur LOCAL à trois états (`prepare`, `actif`, `rendu`),
`.agents/state/local/sync_outbox_deverse.tranche`, tient la FIFO entre processus et la reprise après un arrêt.

Témoins TR1-TR11 du plan `docs/tasks/T-01M4M175MY8RRRVFN7QRV48566-plan.md` rév. 1. Chacun est ROUGE à la BASE
(ffcb5247) pour la raison dite dans sa docstring ; la taille de tranche est patchée avec `create=True`, pour qu'à la
BASE le témoin joue le comportement d'avant au lieu de lever `AttributeError` au patch. TR10b (phrases du README) ne
se joue qu'au KIT : `skipTest` sans `.agents/IS_THE_KIT`, son épingle de constante (TR10a) partout.

Montage du modèle `test_tasks_deversement_durcissement.py` : `tasks.py` chargé par chemin, une racine `tempfile` par
témoin, `CADRE_STATE_DIR` / `AGENTS_EVENTS_DIR` jetables, board et déversement posés directement, consumer lambda,
aucun pont V3. Aucun parcours récursif : `Path.glob` non récursif seul.
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
from typing import Any, Callable, Iterator
from unittest import mock

TASKS_PATH = Path(__file__).with_name("tasks.py")
REPO = Path(__file__).resolve().parents[2]
MARQUEUR_KIT = Path(".agents") / "IS_THE_KIT"
SPEC = importlib.util.spec_from_file_location("tasks_outbox_tranche_under_test", TASKS_PATH)
assert SPEC is not None and SPEC.loader is not None
tasks = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = tasks
SPEC.loader.exec_module(tasks)

#: Phrases du README posées par ce plan (texte A puis C, après la phrase épinglée de D14), au KIT seul (TR10b).
PHRASE_A = ("Beyond 50 spilled intents, the sentence above holds per slice of 50: the file is rewritten with the rest, "
            "not renamed, and a slice already delivered stays delivered if the next put-back fails.")
PHRASE_C = ("A slice in flight is recorded in the local file `sync_outbox_deverse.tranche`, next to the spill file, "
            "git-ignored like it.")
NOM_MARQUEUR = "sync_outbox_deverse.tranche"


class Arret(Exception):
    """Un arrêt simulé du processus au point nommé (TR7) : rien ne le rattrape entre lui et le banc."""


class TrancheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        env = mock.patch.dict(os.environ, {
            "CADRE_STATE_DIR": str(self.base / "state"),
            "AGENTS_EVENTS_DIR": str(self.base / "events"),
        })
        env.start()
        self.addCleanup(env.stop)
        self.racine = self._racine("repo")

    # -- outillage --------------------------------------------------------------
    def _racine(self, nom: str) -> str:
        racine = self.base / nom
        board = racine / ".agents" / "state" / "board"
        board.mkdir(parents=True)
        (board / "TASKS.json").write_text(json.dumps({"tasks": [], "sync_correlations": {}}), encoding="utf-8")
        return str(racine)

    def _poser(self, root: str, au_fichier: int, au_board: int) -> list[str]:
        """`au_fichier + au_board` intents dans l'ordre d'écriture : les `au_fichier` plus ANCIENS au fichier de
        déversement (l'état qu'un déversement laisse), les autres au board. Rend leurs `operation_id`, dans l'ordre."""
        data = tasks.load(root)
        for rang in range(au_fichier + au_board):
            tasks.enqueue_sync_intent(data, f"banc-{rang}", None, None)
        intents = list(data["sync_outbox"])
        data["sync_outbox"] = intents[au_fichier:]
        tasks.save(root, data)
        fichier = tasks._chemin_deverse(root)
        fichier.parent.mkdir(parents=True, exist_ok=True)
        fichier.write_bytes(b"".join(json.dumps(i, ensure_ascii=False, sort_keys=True).encode("utf-8") + b"\n"
                                     for i in intents[:au_fichier]))
        return [intent["operation_id"] for intent in intents]

    @staticmethod
    def _ops_de(chemin: Path) -> list[str]:
        if not chemin.exists():
            return []
        return [json.loads(ligne)["operation_id"] for ligne in chemin.read_bytes().split(b"\n")[:-1]]

    def _fichier(self, root: str) -> list[str]:
        return self._ops_de(tasks._chemin_deverse(root))

    def _intent_au_fichier(self, root: str, op: str) -> dict[str, Any]:
        lignes = tasks._chemin_deverse(root).read_bytes().split(b"\n")[:-1]
        return next(json.loads(ligne) for ligne in lignes if json.loads(ligne)["operation_id"] == op)

    @staticmethod
    def _board(root: str) -> list[str]:
        return [intent["operation_id"] for intent in tasks.load(root)["sync_outbox"]]

    @staticmethod
    def _marqueur(root: str) -> Path:
        return tasks.lock_path(root).with_name(NOM_MARQUEUR)

    def _etat(self, root: str) -> str | None:
        marqueur = self._marqueur(root)
        return json.loads(marqueur.read_bytes())["etat"] if marqueur.exists() else None

    @staticmethod
    def _traces(root: str) -> list[Path]:
        fichier = tasks._chemin_deverse(root)
        return sorted(fichier.parent.glob(f"{fichier.name}.rejoue-*"), key=lambda p: int(p.name.rsplit("-", 1)[1]))

    @staticmethod
    def _k(valeur: int) -> Any:
        return mock.patch.object(tasks, "_TRANCHE_REINJECTION", valeur, create=True)

    @staticmethod
    def _drain(root: str, consumer: Callable[[dict[str, Any]], bool], **options: Any) -> int:
        with contextlib.redirect_stderr(io.StringIO()):
            return tasks.drain_sync_outbox(root, consumer, **options)

    @staticmethod
    def _reinjecter(root: str, rendu: dict[str, Any]) -> int:
        with contextlib.redirect_stderr(io.StringIO()):
            return tasks._reinjecter_deverses(root, rendu=rendu)

    @staticmethod
    def _livreur(livres: list[str], echoue_sur: str | None = None) -> Callable[[dict[str, Any]], bool]:
        def consumer(intent: dict[str, Any]) -> bool:
            if intent["operation_id"] == echoue_sur:
                return False
            livres.append(intent["operation_id"])
            return True

        return consumer

    # -- TR1 -----------------------------------------------------------------------
    def test_TR1_un_drain_en_echec_ne_fait_entrer_et_sortir_du_dossier_versionne_qu_une_tranche(self) -> None:
        """TR1 coût : 250 intents au fichier, consumer `False` ⇒ au plus K + 2 = 52 fichiers créés et 50 enlevés dans
        `sync_outbox/` (compteur de MT1), le fichier = les 250 dans l'ordre, board vide, ni marqueur ni trace. BASE :
        252 créés / 250 enlevés (tout le fichier entre au dossier versionné puis en ressort). Mutant m1
        `_TRANCHE_REINJECTION = 10**9` : 252 / 250."""
        ops = self._poser(self.racine, 250, 0)
        compte = {"crees": 0, "enleves": 0}
        vrai_poser, vrai_unlink = tasks._poser_definitif, Path.unlink

        def poser(*args: Any, **kwargs: Any) -> None:
            if kwargs.get("dossier") is None and (len(args) < 4 or args[3] is None):
                compte["crees"] += 1
            return vrai_poser(*args, **kwargs)

        def unlink(chemin: Path, *args: Any, **kwargs: Any) -> None:
            if chemin.parent.name == "sync_outbox":
                compte["enleves"] += 1
            return vrai_unlink(chemin, *args, **kwargs)

        echec: dict[str, Any] = {}
        with mock.patch.object(tasks, "_poser_definitif", poser), mock.patch.object(Path, "unlink", unlink):
            self._drain(self.racine, lambda _intent: False, echec=echec)
        self.assertEqual("confirmation refusee par le consumer", echec.get("cause"))
        self.assertGreater(compte["crees"], 0, "rien n'est entré au dossier versionné : le banc ne mesure rien")
        self.assertLessEqual(compte["crees"], 52, compte)
        self.assertLessEqual(compte["enleves"], 50, compte)
        self.assertEqual(ops, self._fichier(self.racine))
        self.assertEqual([], self._board(self.racine))
        self.assertFalse(os.path.lexists(self._marqueur(self.racine)))
        self.assertEqual([], self._traces(self.racine))

    # -- TR2 -----------------------------------------------------------------------
    def test_TR2_un_drain_sain_livre_tranche_apres_tranche_dans_l_ordre_d_origine(self) -> None:
        """TR2 drain sain, K = 3 : 7 au fichier + 2 au board ⇒ livrés = les 7 puis les 2, fichier et marqueur absents,
        trois traces (deux tranches et le reste) dont l'union est l'ordre d'origine. BASE : une seule trace (le fichier
        entier remis en file). Mutants m2 (réservation sans exception de tranche ⇒ 0 livré) et m3 (exception sans
        « tête dans le marqueur `actif` » ⇒ un intent du board passe avant le reste du fichier)."""
        ops = self._poser(self.racine, 7, 2)
        livres: list[str] = []
        with self._k(3):
            rendu = self._drain(self.racine, self._livreur(livres))
        self.assertEqual(ops, livres)
        self.assertEqual(9, rendu)
        self.assertFalse(os.path.lexists(tasks._chemin_deverse(self.racine)))
        self.assertFalse(os.path.lexists(self._marqueur(self.racine)))
        traces = self._traces(self.racine)
        self.assertEqual(3, len(traces), [t.name for t in traces])
        self.assertEqual(ops[:7], [op for trace in traces for op in self._ops_de(trace)])

    # -- TR3 -----------------------------------------------------------------------
    def test_TR3_un_echec_en_tranche_ne_restitue_que_la_tranche_en_tete_du_fichier(self) -> None:
        """TR3 : K = 3, 7 au fichier ; pendant la livraison le fichier garde 4 lignes et le board la tranche de 3 ;
        1 livré puis `False` ⇒ fichier = la tranche restante (`attempt` + 1) PUIS le reste, board sans elle, marqueur
        absent ; un drain sain ensuite livre tout dans l'ordre. BASE : à la première livraison le fichier est déjà
        renommé et le board porte les 7. Mutant m6 (restitution en QUEUE du fichier)."""
        ops = self._poser(self.racine, 7, 0)
        livres: list[str] = []
        vus: list[tuple[int, int]] = []
        livreur = self._livreur(livres, echoue_sur=ops[1])

        def consumer(intent: dict[str, Any]) -> bool:
            vus.append((len(self._fichier(self.racine)), len(self._board(self.racine))))
            return livreur(intent)

        with self._k(3):
            self._drain(self.racine, consumer, echec={})
        self.assertEqual((4, 3), vus[0])
        self.assertEqual([ops[0]], livres)
        self.assertEqual(ops[1:], self._fichier(self.racine))
        self.assertEqual(1, self._intent_au_fichier(self.racine, ops[1])["attempt"])
        self.assertEqual([], self._board(self.racine))
        self.assertFalse(os.path.lexists(self._marqueur(self.racine)))
        with self._k(3):
            self._drain(self.racine, self._livreur(livres))
        self.assertEqual(ops, livres)

    # -- TR4 -----------------------------------------------------------------------
    def test_TR4_a_chaque_save_substitution_et_fsync_chaque_intent_est_au_fichier_ou_au_board(self) -> None:
        """TR4 sonde (forme de W5) à chaque `save`, avant et après, à chaque substitution (`_replace_with_retry`), avant
        et après, et à chaque `fsync`, pendant la remise en file des tranches, la restitution d'un échec puis le drain
        sain : chaque intent non livré est au fichier OU au board. Non-vacuité : la sonde a vu les trois états du
        marqueur — BASE : aucun (rouge). Mutant m7 (`save` du board AVANT l'écriture du fichier en restitution)."""
        ops = self._poser(self.racine, 7, 2)
        livres: list[str] = []
        etats: set[str] = set()
        ecarts: list[tuple[str, list[str]]] = []
        arme = [False]

        def sonder(lieu: str) -> None:
            if not arme[0]:
                return
            arme[0] = False
            try:
                etat = self._etat(self.racine)
                if etat is not None:
                    etats.add(etat)
                presents = set(self._fichier(self.racine)) | set(self._board(self.racine))
                manquants = [op for op in ops if op not in livres and op not in presents]
                if manquants:
                    ecarts.append((lieu, manquants))
            finally:
                arme[0] = True

        vrai_save, vrai_remplacer, vrai_fsync = tasks.save, tasks._replace_with_retry, os.fsync

        def save(root: Any, data: Any) -> None:
            sonder("avant save")
            vrai_save(root, data)
            sonder("après save")

        def remplacer(src: Any, cible: Any) -> None:
            sonder(f"avant substitution de {Path(cible).name}")
            vrai_remplacer(src, cible)
            sonder(f"après substitution de {Path(cible).name}")

        def fsync(fd: int) -> None:
            sonder("fsync")
            vrai_fsync(fd)

        with self._k(3), mock.patch.object(tasks, "save", save), \
                mock.patch.object(tasks, "_replace_with_retry", remplacer), mock.patch.object(tasks.os, "fsync", fsync):
            arme[0] = True
            self._drain(self.racine, self._livreur(livres, echoue_sur=ops[1]), echec={})
            self._drain(self.racine, self._livreur(livres))
            arme[0] = False
        self.assertEqual([], ecarts)
        self.assertEqual({"prepare", "actif", "rendu"}, etats, "la sonde n'a pas vu le protocole de tranche")
        self.assertEqual(ops, livres)

    # -- TR5 -----------------------------------------------------------------------
    def test_TR5_une_seconde_remise_en_file_pendant_une_tranche_en_vol_ne_remet_rien(self) -> None:
        """TR5 : K = 3, 7 au fichier ; la première remise en file rend 3 (la tranche), la seconde 0, `rendu` vide,
        fichier et board inchangés. BASE : la première rend 7. Mutant m4 (marqueur ignoré) : la seconde rend 3."""
        ops = self._poser(self.racine, 7, 0)
        premier: dict[str, Any] = {}
        second: dict[str, Any] = {"perime": True}
        with self._k(3):
            self.assertEqual(3, self._reinjecter(self.racine, premier))
            avant = (self._fichier(self.racine), self._board(self.racine))
            self.assertEqual(0, self._reinjecter(self.racine, second))
        self.assertEqual({}, second)
        self.assertEqual((ops[3:], ops[:3]), avant)
        self.assertEqual(avant, (self._fichier(self.racine), self._board(self.racine)))
        self.assertEqual("actif", self._etat(self.racine))

    # -- TR6 -----------------------------------------------------------------------
    def test_TR6_un_deversement_pendant_une_tranche_en_vol_l_enjambe(self) -> None:
        """TR6 : seuil 4, K = 3, tranche en vol, board au-delà du seuil ⇒ l'excédent part APRÈS la tranche (il
        l'enjambe), la tranche reste en tête du board, l'ordre final est FIFO. BASE : la remise en file prend les 7.
        Mutant m5 (pas d'enjambement : la tranche elle-même repart au fichier, derrière le reste)."""
        ops = self._poser(self.racine, 7, 2)
        with self._k(3):
            self.assertEqual(3, self._reinjecter(self.racine, {}))
        data = tasks.load(self.racine)
        for rang in range(3):
            tasks.enqueue_sync_intent(data, f"neuf-{rang}", None, None)
        tasks.save(self.racine, data)
        ops += [intent["operation_id"] for intent in data["sync_outbox"][-3:]]
        self.assertEqual(ops[:3] + ops[7:], self._board(self.racine))
        with self._k(3), mock.patch.object(tasks, "_SYNC_OUTBOX_SEUIL", 4), \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual((4, 8, 4), tasks._deverser_excedent(self.racine))
        self.assertEqual(ops[3:11], self._fichier(self.racine))
        self.assertEqual(ops[:3] + ops[11:], self._board(self.racine))
        livres: list[str] = []
        with self._k(3):
            self._drain(self.racine, self._livreur(livres))
        self.assertEqual(ops, livres)

    # -- TR7 -----------------------------------------------------------------------
    @contextlib.contextmanager
    def _arret(self, root: str, point: str) -> Iterator[dict[str, int]]:
        """Lève `Arret` AVANT l'événement nommé par `point` : substitution du marqueur (M), du fichier de déversement
        (F) ou de TASKS.json (T), ou création exclusive d'une trace `.rejoue-` (point `apres_2`)."""
        marqueur, fichier, board = self._marqueur(root), tasks._chemin_deverse(root), tasks.store_path(root)
        vu = {"M": 0, "F": 0, "T": 0, "arrets": 0}
        vrai_remplacer, vrai_ouvrir = tasks._replace_with_retry, tasks._ouvrir_sans_lien
        regles = {
            "apres_1": lambda e: e == "T" and vu["M"] >= 1,      # (2) le save, après (1) le marqueur prepare
            "apres_3": lambda e: e == "F" and vu["F"] == 1 and vu["M"] == 1,  # (4) le fichier réécrit, après (3)
            "apres_4": lambda e: e == "M" and vu["M"] == 2,      # (5) le marqueur actif, après (4)
            "apres_r0": lambda e: e == "F" and vu["F"] == 2,     # (r1) le fichier réécrit, après (r0) rendu
            "apres_r1": lambda e: e == "T" and vu["F"] >= 2,     # (r2) le save, après (r1)
        }

        def remplacer(src: Any, cible: Any) -> None:
            chemin = Path(cible)
            evenement = "M" if chemin == marqueur else "F" if chemin == fichier else "T" if chemin == board else None
            if evenement is not None:
                vu[evenement] += 1
                if not vu["arrets"] and point in regles and regles[point](evenement):
                    vu["arrets"] += 1
                    raise Arret(point)
            vrai_remplacer(src, cible)

        def ouvrir(chemin: Any, drapeaux: int) -> int:
            if point == "apres_2" and not vu["arrets"] and ".rejoue-" in str(chemin) and drapeaux & os.O_EXCL:
                vu["arrets"] += 1
                raise Arret(point)
            return vrai_ouvrir(chemin, drapeaux)

        with mock.patch.object(tasks, "_replace_with_retry", remplacer), mock.patch.object(tasks, "_ouvrir_sans_lien",
                                                                                            ouvrir):
            yield vu

    def test_TR7_un_arret_a_chaque_etape_se_reprend_chaque_op_livre_une_fois_dans_l_ordre(self) -> None:
        """TR7 reprise, K = 3, 7 au fichier + 2 au board : arrêt simulé après (1) (`prepare`, tranche absente du board :
        le fichier N'EST PAS touché), après (2), après (4), après (r0) (`rendu`, fichier pas encore réécrit : (r1)
        refaite) et après (r1) ⇒ le drain sain qui suit livre chaque op EXACTEMENT une fois, ordre FIFO. Non-vacuité :
        l'arrêt est tombé et le marqueur est dans l'état attendu — BASE : aucun marqueur (rouge). Mutants m8 (reprise
        `prepare`, tranche au board, qui abandonne au lieu d'achever), m10 (reprise `prepare`, tranche ABSENTE, qui
        achève : la tranche quitte le fichier et se perd), m11 (reprise `rendu` qui saute (r1) : la tranche se perd).
        Passe de correction F5 (exec-critic de l'Outbox) : l'arrêt ENTRE (3) la trace et (4) la réécriture (`apres_3`,
        trace posée, fichier intact) ; mutant « recréer la trace à la reprise `prepare` » (`xb` sur une trace présente :
        FileExistsError, drain bloqué pour de bon) : rouge."""
        attendus = {"apres_1": "prepare", "apres_2": "prepare", "apres_3": "prepare", "apres_4": "prepare",
                    "apres_r0": "rendu", "apres_r1": "rendu"}
        for point, etat in attendus.items():
            with self.subTest(point=point):
                root = self._racine(point)
                ops = self._poser(root, 7, 2)
                livres: list[str] = []
                echoue_sur = ops[1] if point.startswith("apres_r") else None
                with self._k(3):
                    with self._arret(root, point) as vu, self.assertRaises(Arret):
                        self._drain(root, self._livreur(livres, echoue_sur=echoue_sur), echec={})
                    self.assertEqual(1, vu["arrets"])
                    self.assertEqual(etat, self._etat(root))
                    if point == "apres_1":
                        self.assertEqual(ops[:7], self._fichier(root), "(1) seule : le fichier est intact")
                    if point == "apres_3":
                        self.assertEqual((ops[:7], 1), (self._fichier(root), len(self._traces(root))),
                                         "(3) faite, (4) non : trace posée, fichier intact")
                    self._drain(root, self._livreur(livres))
                self.assertEqual(ops, livres)
                self.assertFalse(os.path.lexists(self._marqueur(root)))
                self.assertFalse(os.path.lexists(tasks._chemin_deverse(root)))

    # -- TR8 -----------------------------------------------------------------------
    def test_TR8_un_drain_borne_en_tranche_laisse_le_suivant_poursuivre_la_meme_tranche(self) -> None:
        """TR8 : K = 3, `limit=1` ⇒ 1 livré, la tranche en vol (2 au board, 4 au fichier, marqueur présent) ; le drain
        suivant poursuit la MÊME tranche, sans nouvelle remise en file en tête (elle rend 0), et livre tout dans l'ordre.
        BASE : après `limit=1`, le fichier est déjà renommé et les 6 autres sont au board."""
        ops = self._poser(self.racine, 7, 0)
        livres: list[str] = []
        with self._k(3):
            self.assertEqual(1, self._drain(self.racine, self._livreur(livres), limit=1))
        self.assertEqual(ops[3:], self._fichier(self.racine))
        self.assertEqual(ops[1:3], self._board(self.racine))
        self.assertTrue(os.path.lexists(self._marqueur(self.racine)))
        rendus: list[int] = []
        vrai = tasks._reinjecter_deverses

        def espion(*args: Any, **kwargs: Any) -> int:
            rendus.append(vrai(*args, **kwargs))
            return rendus[-1]

        with self._k(3), mock.patch.object(tasks, "_reinjecter_deverses", espion):
            self._drain(self.racine, self._livreur(livres))
        self.assertEqual(ops, livres)
        self.assertEqual(0, rendus[0], "la tête du second drain a remis une tranche en file")

    # -- TR9 -----------------------------------------------------------------------
    def test_TR9_un_marqueur_illisible_ne_laisse_ni_reserver_ni_remettre_ni_deverser(self) -> None:
        """TR9 : marqueur illisible ⇒ réservation `None`, remise en file `DeverseIllisible` nommant le marqueur, drain qui
        lève, déversement IMPOSSIBLE dit sur stderr ; fichier, board et marqueur intacts. BASE : la remise en file ignore
        le marqueur et prend tout le fichier."""
        self._poser(self.racine, 7, 2)
        marqueur = self._marqueur(self.racine)
        marqueur.write_bytes(b"pas du json")
        avant = (tasks._chemin_deverse(self.racine).read_bytes(), self._board(self.racine), marqueur.read_bytes())
        self.assertIsNone(tasks.claim_sync_event(self.racine, "banc"))
        with self.assertRaises(tasks.DeverseIllisible) as leve:
            self._reinjecter(self.racine, {})
        self.assertIn(str(marqueur), str(leve.exception))
        with self.assertRaises(tasks.DeverseIllisible):
            self._drain(self.racine, lambda _intent: True)
        err = io.StringIO()
        with mock.patch.object(tasks, "_SYNC_OUTBOX_SEUIL", 1), contextlib.redirect_stderr(err):
            self.assertIsNone(tasks._deverser_excedent(self.racine))
        self.assertIn("IMPOSSIBLE", err.getvalue())
        self.assertEqual(avant, (tasks._chemin_deverse(self.racine).read_bytes(), self._board(self.racine),
                                 marqueur.read_bytes()))

    # -- TR10 ----------------------------------------------------------------------
    def test_TR10a_la_taille_de_tranche_vaut_50(self) -> None:
        """TR10a épingle de constante, inconditionnelle. BASE : `AttributeError`."""
        self.assertEqual(50, tasks._TRANCHE_REINJECTION)

    def test_TR10b_le_readme_du_kit_dit_la_tranche_et_son_marqueur(self) -> None:
        """TR10b phrases A et C du README, AU KIT SEULEMENT (un README d'adoptant est le sien). BASE au kit : rouge.
        Mutant : garde retirée ⇒ rouge sur une copie jetable sans `.agents/IS_THE_KIT` ; avec la garde, saut."""
        if not (REPO / MARQUEUR_KIT).is_file():
            self.skipTest("dépôt-kit seul (.agents/IS_THE_KIT absent) : un README d'adoptant n'est pas tenu ici")
        texte = " ".join((REPO / "README.md").read_text(encoding="utf-8").split())
        for phrase in (PHRASE_A, PHRASE_C):
            self.assertIn(" ".join(phrase.split()), texte)

    # -- TR11 ----------------------------------------------------------------------
    def test_TR11_le_reste_final_d_un_deversement_passe_par_des_tranches_est_rendu_par_le_protocole_de_base(
            self) -> None:
        """TR11 : K = 3, 7 au fichier ; le consumer échoue sur le 7e (le reste final, au plus K lignes : chemin de la
        BASE) ⇒ 6 livrés, fichier = ce reste (copie du board, `attempt` + 1), board sans lui, AUCUN marqueur, et les deux
        traces des tranches livrées seules restent (celle du reste, rendue entière, est enlevée). BASE : une seule trace.
        Mutant m12 (ni `rendu.clear()` ni `tranche=False` : le reste final hérite du protocole de tranche, qui refuse
        sans marqueur ⇒ rien n'est rendu au fichier)."""
        ops = self._poser(self.racine, 7, 0)
        livres: list[str] = []
        with self._k(3):
            self._drain(self.racine, self._livreur(livres, echoue_sur=ops[6]), echec={})
        self.assertEqual(ops[:6], livres)
        self.assertEqual([ops[6]], self._fichier(self.racine))
        self.assertEqual(1, self._intent_au_fichier(self.racine, ops[6])["attempt"])
        self.assertEqual([], self._board(self.racine))
        self.assertFalse(os.path.lexists(self._marqueur(self.racine)))
        traces = self._traces(self.racine)
        self.assertEqual(2, len(traces), [t.name for t in traces])
        self.assertEqual(ops[:6], [op for trace in traces for op in self._ops_de(trace)])


if __name__ == "__main__":
    unittest.main()
