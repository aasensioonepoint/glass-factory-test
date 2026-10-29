"""T-01M4MC28CAKFE8YZ2W4WN7DV2C (E-26) : trois durcissements de sécurité de l'Outbox O2.

M1 : le remède F5 (`resurrection_refusal`) imprime chaque id QUOTÉ (`shlex.quote`, POSIX seul) dans la commande qu'il
propose ; la liste descriptive en tête de phrase reste brute. M2 : le dossier VERSIONNÉ `sync_outbox/` — et, avant
une écriture, les dossiers LOCAUX des lots et de la quarantaine — refusé s'il est un lien, par `_refus_liens` (le
mécanisme de T-00001009, étendu). M3 : plafonds cumulés — au plus 10 000 fichiers d'intent et 128 Mio lus par
lecture (fenêtre tolérante : les premiers par clé d'ordre, le reste laissé en place hors vue, une ligne stderr,
`suppressions_en_vol` fail-closed), au plus 100 copies par nom, 1 000 entrées et 256 Mio dans la quarantaine (bilan
du dossier évalué paresseusement, une fois par appelant, jamais pour une copie déjà présente).

Témoins H1-H8 du plan `docs/tasks/T-01M4M175MY8RRRVFN7QRV48566-plan.md` rév. 1. Chacun est ROUGE à la BASE (ffcb5247)
pour la raison dite dans sa docstring ; les plafonds sont patchés avec `create=True`, pour qu'à la BASE le témoin joue
le comportement d'avant au lieu de lever `AttributeError` au patch. H7b (phrases du README) ne se joue qu'au KIT ;
H7a (épingles de constantes) partout.

Montage : `tasks.py` chargé par chemin, une racine `tempfile` par témoin, `CADRE_STATE_DIR` / `AGENTS_EVENTS_DIR`
jetables, board monolithe vide, fichiers d'intent posés directement. Aucun parcours récursif.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import shlex
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

TASKS_PATH = Path(__file__).with_name("tasks.py")
REPO = Path(__file__).resolve().parents[2]
MARQUEUR_KIT = Path(".agents") / "IS_THE_KIT"
SPEC = importlib.util.spec_from_file_location("tasks_outbox_durcissement_under_test", TASKS_PATH)
assert SPEC is not None and SPEC.loader is not None
tasks = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = tasks
SPEC.loader.exec_module(tasks)

#: Phrases du README posées par ce plan, au KIT seul (H7b) : A et C après la phrase épinglée de D14, B au paragraphe O2.
PHRASE_A = ("Beyond 50 spilled intents, the sentence above holds per slice of 50: the file is rewritten with the rest, "
            "not renamed, and a slice already delivered stays delivered if the next put-back fails.")
PHRASE_C = ("A slice in flight is recorded in the local file `sync_outbox_deverse.tranche`, next to the spill file, "
            "git-ignored like it.")
PHRASE_B = (
    "The `sync_outbox/` folder itself, when it is a symbolic link, is refused by `tasks.py` (nothing read, nothing "
    "written outside the board), like `board/tasks/`; so are the local lots and quarantine folders before any write. "
    "Caps: at most 10 000 intent files and 128 MiB are read per load — beyond them only the first files by order key "
    "are read, one stderr line says so at every read, and intents queued after that window are not delivered until the "
    "folder is back under the cap —, at most 100 copies per name, 1 000 entries and 256 MiB in the quarantine. What "
    "remains: a versioned intent file whose order key is below the number of spilled intents put back ahead of it (at "
    "most 50, one slice), next to that spill, makes every mutating command fail (rc 2) until it is removed, and one "
    "whose key is the largest hides the intents queued after it (both tracked by "
    "T-01M4PKKA35TDTHWKVG1SB4D5X9); a parent folder that is a link is still traversed; a junction on Windows is not "
    "seen before Python 3.12 (not measured); the local lots folder, when it is a link, is still read by `load`."
)
HOSTILE = "T-$(touch PWN);1"
HORS_D_ATTEINTE = 10**12


class DurcissementOutboxTests(unittest.TestCase):
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
        self.root = self.base / "repo"
        board = self.root / ".agents" / "state" / "board"
        board.mkdir(parents=True)
        self.tasks_json = board / "TASKS.json"
        self.tasks_json.write_text(json.dumps({"tasks": [], "sync_correlations": {}}), encoding="utf-8")
        self.racine = str(self.root)

    # -- outillage --------------------------------------------------------------
    def _dehors(self, nom: str) -> Path:
        dehors = self.base / nom
        dehors.mkdir()
        return dehors

    @staticmethod
    def _listage(dossier: Path) -> dict[str, bytes]:
        return {p.name: p.read_bytes() for p in sorted(dossier.iterdir())}

    def _enveloppe(self, op: str) -> bytes:
        scratch: dict[str, Any] = {"tasks": []}
        tasks.enqueue_sync_intent(scratch, f"banc-{op}", None, None, operation_id=op)
        return tasks._octets_enveloppe({"correlation": scratch["sync_correlations"][op],
                                        "intent": scratch["sync_outbox"][0]})

    def _intents_valides(self, nombre: int) -> list[Path]:
        """`nombre` fichiers d'intent valides de MÊME taille, clés 1..nombre, leurs corrélations au board."""
        data = tasks.load(self.racine)
        dossier = tasks._dossier_outbox(self.racine)
        dossier.mkdir(parents=True, exist_ok=True)
        chemins = []
        for cle in range(1, nombre + 1):
            op = f"op{cle}"
            data["sync_correlations"][op] = {"board_task_id": f"banc-{op}", "tombstoned": True}
            chemin = dossier / f"{cle:020d}-{op}.json"
            chemin.write_bytes(self._enveloppe(op))
            chemins.append(chemin)
        tasks.save(self.racine, data)
        return chemins

    def _illisibles(self, nombre: int, taille: int = 0) -> list[Path]:
        dossier = tasks._dossier_outbox(self.racine)
        dossier.mkdir(parents=True, exist_ok=True)
        chemins = []
        for cle in range(1, nombre + 1):
            chemin = dossier / f"{cle:020d}-bad{cle}.json"
            contenu = b"{bad %d " % cle
            chemin.write_bytes(contenu + b"x" * max(0, taille - len(contenu)))
            chemins.append(chemin)
        return chemins

    def _quarantaine(self) -> list[str]:
        dossier = tasks._dossier_quarantaine(self.racine)
        return sorted(p.name for p in dossier.iterdir()) if dossier.is_dir() else []

    def _save_lu(self) -> str:
        """Un `save` du board tel que `load` le rend ; rend le stderr."""
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            tasks.save(self.racine, tasks.load(self.racine))
        return err.getvalue()

    @staticmethod
    def _plafonds(**valeurs: int) -> contextlib.ExitStack:
        pile = contextlib.ExitStack()
        for nom, valeur in valeurs.items():
            pile.enter_context(mock.patch.object(tasks, nom, valeur, create=True))
        return pile

    @staticmethod
    def _lignes_de(err: str, nom: str) -> list[str]:
        return [ligne for ligne in err.splitlines() if f" {nom} : " in ligne]

    # -- H1 / H8 : M1 -------------------------------------------------------------------
    @staticmethod
    def _remede(ids: list[str]) -> str:
        data = {"tasks": [{"id": tid} for tid in ids],
                "sync_correlations": {f"o{rang}": {"board_task_id": tid, "tombstoned": True}
                                      for rang, tid in enumerate(ids)}}
        message = tasks.resurrection_refusal(data)
        debut = message.index("one command per id (")
        return message[debut:message.index("`)", debut) + 2]  # l'id hostile porte lui-même « ); »

    def test_H1_le_remede_F5_quote_un_id_hostile_dans_la_commande_imprimee(self) -> None:
        """H1 : id `T-$(touch PWN);1` (il passe `numeric_id`, MS1) ⇒ la commande imprimée, passée à `shlex.split`, rend
        EXACTEMENT `["tasks.py", "delete", id]`. BASE : quatre éléments (id non quoté). Mutant : quotage retiré."""
        segment = self._remede([HOSTILE])
        commande = segment[segment.index("`") + 1:segment.rindex("`")]
        self.assertEqual(["tasks.py", "delete", HOSTILE], shlex.split(commande))

    def test_H8_un_id_sur_reste_tel_quel_et_la_liste_descriptive_reste_brute(self) -> None:
        """H8 : un id sûr est imprimé tel quel (`shlex.quote` ne le change pas), un id hostile à côté de lui est quoté,
        et la liste descriptive en tête de phrase reste brute (prose, pas une commande). BASE : l'id hostile non quoté."""
        sur = "T-00000001"
        message = tasks.resurrection_refusal({"tasks": [{"id": sur}, {"id": HOSTILE}], "sync_correlations": {
            "o1": {"board_task_id": sur, "tombstoned": True}, "o2": {"board_task_id": HOSTILE, "tombstoned": True}}})
        self.assertTrue(message.startswith(f"{', '.join(sorted([sur, HOSTILE]))} are on the board"), message[:80])
        attendu = "; ".join(f"`tasks.py delete {shlex.quote(tid)}`" for tid in sorted([sur, HOSTILE]))
        self.assertIn(f"one command per id ({attendu})", message)
        self.assertIn(f"`tasks.py delete {sur}`", message)

    # -- H2 / H3 : M2 -------------------------------------------------------------------
    def test_H2_un_dossier_sync_outbox_en_lien_est_refuse_sans_rien_lire_ni_ecrire_dehors(self) -> None:
        """H2 : `sync_outbox/` remplacé par un lien vers un dossier extérieur portant un intent valide ⇒ `load` et `save`
        lèvent en nommant le lien, le dossier extérieur est intact (listage égal), `suppressions_en_vol` lève
        `DeverseIllisible`. BASE : `load` LIT l'intent du dehors et `save` ÉCRIT dehors (MS2). Mutant : dossier
        retiré de `_refus_liens`."""
        dehors = self._dehors("dehors")
        (dehors / f"{1:020d}-opX.json").write_bytes(self._enveloppe("opX"))
        avant = self._listage(dehors)
        lien = tasks._dossier_outbox(self.racine)
        os.symlink(dehors, lien)
        with self.assertRaises(tasks.BoardError) as leve:
            tasks.load(self.racine)
        self.assertIn(str(lien), str(leve.exception))
        data: dict[str, Any] = {"tasks": [], "sync_correlations": {}}
        tasks.enqueue_sync_intent(data, "banc-neuf", None, None)
        with self.assertRaises(tasks.BoardError), contextlib.redirect_stderr(io.StringIO()):
            tasks.save(self.racine, data)
        with self.assertRaises(tasks.DeverseIllisible), contextlib.redirect_stderr(io.StringIO()):
            tasks.suppressions_en_vol({"sync_outbox": []}, self.racine)
        self.assertEqual(avant, self._listage(dehors))

    def test_H3_lots_ou_quarantaine_en_lien_refuses_avant_toute_ecriture(self) -> None:
        """H3 : dossier des lots en lien ⇒ `_reprendre_lots` lève, `victime.json` toujours au dehors ; quarantaine en
        lien ⇒ le `save` d'un board portant un intent illisible lève AVANT publication (TASKS.json intact), rien écrit
        dehors. BASE : `_reprendre_lots` DÉPLACE `victime.json` en quarantaine, la copie de l'illisible est écrite
        dehors (MS4)."""
        dehors = self._dehors("dehors-lots")
        (dehors / "victime.json").write_bytes(b"pas un lot")
        lots = tasks._dossier_lots(self.racine)
        lots.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(dehors, lots)
        with self.assertRaises(tasks.BoardError) as leve, contextlib.redirect_stderr(io.StringIO()):
            tasks._reprendre_lots(self.racine)
        self.assertIn(str(lots), str(leve.exception))
        self.assertEqual(["victime.json"], sorted(p.name for p in dehors.iterdir()))
        lots.unlink()
        self._illisibles(1)
        dehors_q = self._dehors("dehors-quarantaine")
        os.symlink(dehors_q, tasks._dossier_quarantaine(self.racine))
        octets = self.tasks_json.read_bytes()
        with self.assertRaises(tasks.BoardError):
            self._save_lu()
        self.assertEqual(octets, self.tasks_json.read_bytes())
        self.assertEqual([], sorted(dehors_q.iterdir()))

    # -- H4 / H5 : M3, fenêtre de lecture -----------------------------------------------
    def _fenetre(self, chemins: list[Path], **plafonds: int) -> None:
        octets = {chemin: chemin.read_bytes() for chemin in chemins}
        err = io.StringIO()
        with self._plafonds(**plafonds), contextlib.redirect_stderr(err):
            vue = [intent["operation_id"] for intent in tasks.load(self.racine)["sync_outbox"]]
        self.assertEqual([f"op{cle}" for cle in range(1, 6)], vue)
        self.assertEqual(1, len([ligne for ligne in err.getvalue().splitlines() if "plafond de lecture" in ligne]),
                         err.getvalue())
        with self._plafonds(**plafonds):
            self._save_lu()
            with self.assertRaises(tasks.DeverseIllisible), contextlib.redirect_stderr(io.StringIO()):
                tasks.suppressions_en_vol({"sync_outbox": []}, self.racine)
        self.assertEqual(octets, {chemin: chemin.read_bytes() for chemin in chemins if chemin.exists()})
        self.assertEqual([], self._quarantaine())

    def test_H4_au_dela_du_plafond_de_nombre_la_vue_est_une_fenetre_et_rien_n_est_touche(self) -> None:
        """H4 : plafond de nombre patché à 5, 8 fichiers valides ⇒ vue des 5 premiers par clé, UNE ligne stderr, les 3
        autres intacts sur disque après un `save`, aucun copié en quarantaine, `suppressions_en_vol` lève. BASE : vue de
        8. Mutants : plafond retiré (vue de 8) ; `_relire` non borné (les 3 hors vue passent « unreadable » et sont
        copiés en quarantaine)."""
        self._fenetre(self._intents_valides(8), _PLAFOND_INTENTS_NOMBRE=5,
                      _PLAFOND_INTENTS_OCTETS_CUMULES=HORS_D_ATTEINTE)

    def test_H5_au_dela_du_plafond_d_octets_cumules_meme_fenetre(self) -> None:
        """H5 : plafond d'octets cumulés patché à 5 fichiers et demi (fichiers de même taille) ⇒ même attendu que H4.
        BASE : vue de 8. Mutant : plafond d'octets retiré."""
        chemins = self._intents_valides(8)
        taille = chemins[0].stat().st_size
        self.assertEqual({taille}, {chemin.stat().st_size for chemin in chemins})
        self._fenetre(chemins, _PLAFOND_INTENTS_NOMBRE=HORS_D_ATTEINTE,
                      _PLAFOND_INTENTS_OCTETS_CUMULES=5 * taille + taille // 2)

    # -- H6 : M3, quarantaine -------------------------------------------------------------
    def test_H6a_au_plus_N_copies_par_nom(self) -> None:
        """H6a : copies par nom patchées à 3 (les deux autres plafonds hors d'atteinte), 5 contenus d'un même nom ⇒ 3
        copies et deux lignes « IMPOSSIBLE ». BASE : 5 copies (300 pour 300 contenus, MS3). Mutant m13 : plafond par nom
        retiré."""
        (chemin,) = self._illisibles(1)
        err = io.StringIO()
        with self._plafonds(_PLAFOND_QUARANTAINE_COPIES=3, _PLAFOND_QUARANTAINE_ENTREES=HORS_D_ATTEINTE,
                            _PLAFOND_QUARANTAINE_OCTETS=HORS_D_ATTEINTE), contextlib.redirect_stderr(err):
            for rang in range(5):
                chemin.write_bytes(b"{bad contenu %d" % rang)
                tasks._mettre_en_quarantaine(self.racine, chemin, "banc")
        self.assertEqual(3, len(self._quarantaine()), self._quarantaine())
        self.assertEqual(2, err.getvalue().count("IMPOSSIBLE"), err.getvalue())

    def test_H6b_au_plus_N_entrees_et_une_copie_deja_presente_n_est_jamais_refusee(self) -> None:
        """H6b : entrées patchées à 4, 6 fichiers illisibles ⇒ un `save` en copie 4 et dit « IMPOSSIBLE » pour les 2
        autres ; un second `save` du même board (dossier plein) ⇒ fichier par fichier, les 4 déjà copiés disent « copie
        déjà en quarantaine » sans « IMPOSSIBLE », les 2 autres « IMPOSSIBLE ». BASE : 6 copies, aucun refus. Mutants
        m14 (plafond d'entrées retiré) et m16 (plafond évalué avant le test `deja` ⇒ « IMPOSSIBLE » sur les 4)."""
        chemins = self._illisibles(6)
        noms = [chemin.name for chemin in chemins]
        with self._plafonds(_PLAFOND_QUARANTAINE_COPIES=HORS_D_ATTEINTE, _PLAFOND_QUARANTAINE_ENTREES=4,
                            _PLAFOND_QUARANTAINE_OCTETS=HORS_D_ATTEINTE):
            premier = self._save_lu()
            self.assertEqual(noms[:4], self._quarantaine())
            for nom in noms[:4]:
                (ligne,) = self._lignes_de(premier, nom)
                self.assertNotIn("IMPOSSIBLE", ligne)
            for nom in noms[4:]:
                (ligne,) = self._lignes_de(premier, nom)
                self.assertIn("IMPOSSIBLE", ligne)
            second = self._save_lu()
        for nom in noms[:4]:
            (ligne,) = self._lignes_de(second, nom)
            self.assertIn("copie déjà en quarantaine", ligne)
            self.assertNotIn("IMPOSSIBLE", ligne)
        for nom in noms[4:]:
            (ligne,) = self._lignes_de(second, nom)
            self.assertIn("IMPOSSIBLE", ligne)
        self.assertEqual(noms[:4], self._quarantaine())

    def test_H6c_au_plus_N_octets_dans_la_quarantaine(self) -> None:
        """H6c : octets patchés à 3 Kio, 6 fichiers illisibles de 1 Kio ⇒ 3 entrées et « IMPOSSIBLE » pour les 3
        autres. BASE : 6 copies. Mutant m15 : plafond d'octets retiré."""
        chemins = self._illisibles(6, taille=1024)
        with self._plafonds(_PLAFOND_QUARANTAINE_COPIES=HORS_D_ATTEINTE, _PLAFOND_QUARANTAINE_ENTREES=HORS_D_ATTEINTE,
                            _PLAFOND_QUARANTAINE_OCTETS=3 * 1024):
            err = self._save_lu()
        self.assertEqual([chemin.name for chemin in chemins[:3]], self._quarantaine())
        self.assertEqual(3, err.count("IMPOSSIBLE"), err)

    def test_H6d_le_dossier_de_quarantaine_est_evalue_une_seule_fois_par_save(self) -> None:
        """H6d sonde : un `save` qui copie 5 fichiers illisibles appelle EXACTEMENT UNE fois l'évaluateur nommé du
        dossier (`_bilan_quarantaine`, un seul `scandir`) ; 5 copies créées. BASE : 0 appel (aucun bilan). Mutant m16
        (une évaluation par entrée créée) : 5 appels."""
        self._illisibles(5)
        evaluateur = mock.patch.object(tasks, "_bilan_quarantaine", create=True,
                                       wraps=getattr(tasks, "_bilan_quarantaine", None))
        with evaluateur as sonde:
            self._save_lu()
        self.assertEqual(5, len(self._quarantaine()))
        self.assertEqual(1, sonde.call_count)

    # -- H7 : épingles --------------------------------------------------------------------
    def test_H7a_les_plafonds_de_production(self) -> None:
        """H7a épingles des valeurs de production, inconditionnelles. BASE : `AttributeError`."""
        self.assertEqual(
            (10_000, 128 * 1024 * 1024, 100, 1_000, 256 * 1024 * 1024),
            (tasks._PLAFOND_INTENTS_NOMBRE, tasks._PLAFOND_INTENTS_OCTETS_CUMULES, tasks._PLAFOND_QUARANTAINE_COPIES,
             tasks._PLAFOND_QUARANTAINE_ENTREES, tasks._PLAFOND_QUARANTAINE_OCTETS),
        )

    def test_H7b_le_readme_du_kit_dit_les_trois_phrases(self) -> None:
        """H7b phrases A, C et B du README, AU KIT SEULEMENT (un README d'adoptant est le sien). BASE au kit : rouge.
        Mutant : garde retirée ⇒ rouge sur une copie jetable sans `.agents/IS_THE_KIT` ; avec la garde, saut."""
        if not (REPO / MARQUEUR_KIT).is_file():
            self.skipTest("dépôt-kit seul (.agents/IS_THE_KIT absent) : un README d'adoptant n'est pas tenu ici")
        texte = " ".join((REPO / "README.md").read_text(encoding="utf-8").split())
        for phrase in (PHRASE_A, PHRASE_C, PHRASE_B):
            self.assertIn(" ".join(phrase.split()), texte)

    def test_H7c_la_phrase_B_mesuree_cle_de_tete_contre_les_intents_remis(self) -> None:
        """Passe de correction F5 (exec-critic de l'Outbox, phrase B trop large) : le refus « no order key is left
        before the head » ne mord que si la clé de tête est INFÉRIEURE au nombre d'intents déversés remis devant elle
        (`_cles_d_ordre`), jamais pour toute clé < 50. 3 déversés : clé 2 ⇒ refus nommé ; clé 3 ⇒ remis (clés 0..2).
        La phrase d'avant (« below 50 ») prédisait le refus de la clé 3."""
        for cle, refus in ((2, True), (3, False)):
            with self.subTest(cle=cle):
                racine = self.base / f"h7c-{cle}"
                (racine / ".agents" / "state" / "board").mkdir(parents=True)
                (racine / ".agents" / "state" / "board" / "TASKS.json").write_text(
                    json.dumps({"tasks": [], "sync_correlations": {}}), encoding="utf-8")
                data = tasks.load(str(racine))
                for rang in range(4):
                    tasks.enqueue_sync_intent(data, f"banc-{rang}", None, None)
                intents = list(data["sync_outbox"])
                data["sync_outbox"] = intents[3:]
                tasks.save(str(racine), data)
                (versionne,) = list(tasks._dossier_outbox(str(racine)).glob("*.json"))
                versionne.rename(versionne.with_name(f"{cle:020d}-{intents[3]['operation_id']}.json"))
                deverse = tasks._chemin_deverse(str(racine))
                deverse.parent.mkdir(parents=True, exist_ok=True)
                deverse.write_bytes(b"".join(json.dumps(i, sort_keys=True).encode("utf-8") + b"\n" for i in intents[:3]))
                with contextlib.redirect_stderr(io.StringIO()):
                    if refus:
                        with self.assertRaisesRegex(tasks.BoardError, "no order key is left before the head"):
                            tasks._reinjecter_deverses(str(racine))
                    else:
                        self.assertEqual(3, tasks._reinjecter_deverses(str(racine)))
                        self.assertEqual([i["operation_id"] for i in intents],
                                         [i["operation_id"] for i in tasks.load(str(racine))["sync_outbox"]])

    # -- H8 : avis de sécurité de l'Outbox (S-01M4PY57X3E1SXP1Y88HVYN9GQ), passe de correction F5 ---------------
    def test_H8a_un_nom_de_trace_a_controle_nul_ou_espace_rend_le_marqueur_hors_forme(self) -> None:
        """`_NOM_TRACE` acceptait `\\n`, NUL (un `open` levait alors `ValueError` en trace Python) et tout caractère
        de contrôle. MUTANT : `_NOM_TRACE` ramené à `[^/\\\\]+` ⇒ les noms hostiles passent. POLARITÉ : le nom frappé
        par `_reinjecter_deverses` reste lu."""
        marqueur = tasks._chemin_tranche(self.racine)
        marqueur.parent.mkdir(parents=True, exist_ok=True)

        def poser(nom: str) -> None:
            marqueur.write_text(json.dumps({"etat": "actif", "ops": ["op1"], "trace": nom}), encoding="utf-8")

        for nom in ("x\n.rejoue-1", "a\x00b.rejoue-1", "a b.rejoue-1", "a\x1b[31m.rejoue-1", "é.rejoue-1"):
            with self.subTest(nom=repr(nom)):
                poser(nom)
                with self.assertRaisesRegex(tasks.DeverseIllisible, "hors forme"):
                    tasks._lire_tranche(self.racine)
        poser("sync_outbox_deverse.jsonl.rejoue-1760000000000000000")
        self.assertEqual("actif", tasks._lire_tranche(self.racine)["etat"])

    def test_H8b_la_lecture_du_deversement_et_des_traces_est_plafonnee(self) -> None:
        """Lecture non plafonnée (même avis) : plafond abaissé à 16 octets, un déversement de 3 intents ⇒
        `DeverseIllisible` nommée par la remise en file, les suppressions en vol et la lecture d'une trace — jamais
        une lecture sans borne, jamais une trace Python. MUTANT : `_lire_deverse` sans plafond (`fichier.read()`)."""
        data = tasks.load(self.racine)
        for rang in range(3):
            tasks.enqueue_sync_intent(data, f"banc-{rang}", None, None)
        intents = list(data["sync_outbox"])
        data["sync_outbox"] = []
        tasks.save(self.racine, data)
        deverse = tasks._chemin_deverse(self.racine)
        deverse.parent.mkdir(parents=True, exist_ok=True)
        deverse.write_bytes(b"".join(json.dumps(i, sort_keys=True).encode("utf-8") + b"\n" for i in intents))
        with mock.patch.object(tasks, "_PLAFOND_DEVERSE_OCTETS", 16), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaisesRegex(tasks.DeverseIllisible, "16-byte cap"):
                tasks._reinjecter_deverses(self.racine)
            with self.assertRaisesRegex(tasks.DeverseIllisible, "16-byte cap"):
                tasks.suppressions_en_vol(tasks.load(self.racine), self.racine)
            with self.assertRaisesRegex(tasks.DeverseIllisible, "16-byte cap"):
                tasks._lignes_du_fichier(deverse)
        self.assertEqual(3, len(tasks._lignes_du_fichier(deverse)[0]), "POLARITÉ : plafond de production, lu")


if __name__ == "__main__":
    unittest.main()
