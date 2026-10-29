#!/usr/bin/env python3
"""LA GARDE DE MESURE SUR `new` — T-00001128 : « un défaut se mesure avant de
devenir une tâche » (AGENTS.md § Golden rules), tenu par `tasks.py new` et non
plus par la seule mémoire de l'orchestrateur. Deux sorties, jamais les deux :
`--mesure "<commande qui reproduit> => <résultat observé>" --motif <M>` pour un
défaut, `--pas-un-defaut "<pourquoi>"` pour une fonctionnalité, une décision, un
chantier. Armée par la PRÉSENCE de `.agents/state/gates/MESURE_REQUIRED`
(même forme que `BINOME_REQUIRED`) ; absente, l'OBLIGATION est inerte et un
`new` sans drapeau passe comme avant ; la FORME d'une valeur donnée est tenue
partout.

DEUX RÈGLES RENDUES MÉCANIQUES par la passe de correction (S-00003957), logique
isolée dans `tasks_mesure.py` : L1, `--mesure` EXIGE `--motif` pris dans la liste
FERMÉE `MOTIFS` (garde, securite, decision-pilote, gros, sans-fournee) — « mineur »
et tout motif hors liste sont refusés avec la phrase « un défaut mineur se
corrige sur place… » ; `--motif` sans `--mesure`, ou avec `--pas-un-defaut`, est
refusé. L2, `--pas-un-defaut` est REFUSÉ quand le TITRE OUVRE par le lexique d'un
défaut (`LEXIQUE_DEFAUT`, mesuré sur le board : 21/1120 titres, aucun faux
positif à la lecture). Et la forme refuse un caractère de contrôle ou invisible
(Cc/Cf) sur les trois drapeaux, et un côté de `=>` sans texte VISIBLE (rejoués
par critic-opus : `'​=>​'` passait, `'x => y\\nstate : done'` forgeait une ligne).

ZÉRO APPEL LLM. `tasks.py` chargé par chemin (comme `test_tasks_epics.py`) ;
board et marqueur posés sous une racine JETABLE. `replay_sync` est patché sur
le module (le pont V3 n'est pas l'objet de ce banc — mais le snapshot de
l'outbox EST contrôlé : ses clés sont gelées, `mesure` n'y entre pas) et
l'environnement V3 (`CADRE_STATE_DIR`, `AGENTS_EVENTS_DIR`, `CADRE_PROJECT_ROOT`)
pointe la racine jetable. Fixtures SYNTHÉTIQUES, jamais les données du dépôt.

*** CHAQUE TÉMOIN NOMME SON MUTANT *** (joué sur une COPIE jetable, L-00000487).
Mutant de référence, « garde désactivée » : `mesure_refusal` qui rend `None`
d'emblée ⇒ tous les témoins de refus rougissent. « L1 désactivée » : le `if
motif is None` de `mesure_refusal` retiré ⇒ `MotifTests` rougit. « L2
désactivée » : `titre_defaut` qui rend `None` ⇒ `LexiqueTests` rougit.
« dispatch sans relais » : `tasks.py` qui ne passe plus `mesure=` /
`pas_un_defaut=` / `motif=` à `new_task` ⇒ les témoins CLI rougissent.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
TASKS = HERE / "tasks.py"

if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


def _charger(nom: str, chemin: Path):
    spec = importlib.util.spec_from_file_location(nom, chemin)
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module
    spec.loader.exec_module(module)
    return module


tasks = _charger("tasks_mesure_banc", TASKS)

MESURE = "python3 .agents/bin/x.py => rc 1, KeyError: 'owner'"
MOTIF = "garde"
MESURE_ARGS = ("--mesure", MESURE, "--motif", MOTIF)
PAS_UN_DEFAUT = "fonctionnalite demandee par le pilote (S-00003949)"
MESURE_RE, PAS_UN_DEFAUT_RE = re.escape(MESURE), re.escape(PAS_UN_DEFAUT)
REFUS_DOCTRINE = ("--mesure", "--pas-un-defaut", "--motif", "AGENTS.md", "Golden rules", "MESURE_REQUIRED")
# Le lexique LIVRÉ est celui MESURÉ (2026-10-03, board vivant, 1120 titres) : un
# élargissement silencieux se verrait ici, pas au prochain faux positif.
LEXIQUE_MESURE = ("fix", "bug", "bogue", "defaut", "regression", "crash", "traceback",
                  "faux positif", "faux negatif")
TITRES_DEFAUT = (
    "Fix: os.replace nu dans ledger.py:189",
    "fix(binome) emprunt de slot sans expiration",
    "BUG: build_index indexe les ressources VENDORISEES",
    "DÉFAUT du constructeur d index",
    "Défauts PRÉ-EXISTANTS du shell dashboard",
    "RÉGRESSION Linux: le re-bind du port 4318",
    "Regression: le changement de paliers",
    "[BK-317][P1] Faux positif fail-closed (planner de T-00000780)",
    "audit-gate.sh: faux positif par sous-chaine",
    "  Bogue d affichage",
    "Crash de la reconstruction V3",
    "Traceback dans ledger.py add",
    "faux négatif de la garde M",
)
TITRES_SAINS = (
    "Gardes ARMÉES PAR DÉFAUT chez l adoptant (décision pilote)",
    "[BK-752] Instruire l armement par défaut des gardes de pipeline",
    "Remesurer et épingler par un banc le taux de faux positifs de safe_bash.py",
    "Durcissement kickoff, surface SHELL : faux positif connu, à mesurer",
    "Fixer la doc du board",
    "Fixture jetable pour le banc V3",
    "Écrire le banc qui rougit si la porte casse",
    "Rétracter le marqueur § Golden rules (L-00000001)",
    "import du backlog : Bugs connus, à trier",
    "Debug du daemon dashboard",
)


class _Banc(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.d = Path(self._tmp.name)
        for sub in ("board", "gates"):
            (self.d / ".agents" / "state" / sub).mkdir(parents=True, exist_ok=True)
        self.root = str(self.d)
        for patcher in (
            mock.patch.dict(os.environ, {"CADRE_STATE_DIR": self.root, "AGENTS_EVENTS_DIR": self.root,
                                         "CADRE_PROJECT_ROOT": self.root}),
            mock.patch.object(tasks, "replay_sync", return_value=0),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    # -- outillage ------------------------------------------------------------
    @property
    def store_path(self) -> Path:
        return self.d / ".agents" / "state" / "board" / "TASKS.json"

    @property
    def marqueur(self) -> Path:
        return self.d / tasks.MESURE_GATE

    def armer(self) -> None:
        self.marqueur.touch()

    def store(self) -> dict:
        return json.loads(self.store_path.read_text(encoding="utf-8"))

    def task(self, tid: str) -> dict:
        return next(t for t in self.store()["tasks"] if t["id"] == tid)

    def cli(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                rc = tasks.main(["--root", self.root, *args])
            except SystemExit as exc:  # `ap.error` : usage, rc 2 ; `--help` : rc 0
                rc = exc.code
        return rc, out.getvalue(), err.getvalue()

    def new_ok(self, *args: str) -> str:
        rc, out, err = self.cli("new", *args)
        self.assertEqual(rc, 0, err)
        self.assertIn("→ pending", out)
        return out.split()[1]

    def magasin_inchange(self, avant: dict, apres: dict) -> None:
        """« Le refus n'a rien alloué », dit SANS lire la valeur du compteur (R-BANCS
        (iii), plan de T-00000726) — vrai avant ET après la bascule C2, qui retire
        `next_id` : aucune tâche ajoutée, le magasin MOINS la clé `next_id` identique,
        et `next_id` identique quand il existe (`.get` : absent des deux côtés après C2)."""
        self.assertEqual(len(apres["tasks"]), len(avant["tasks"]), "un refus a ajouté une tâche")
        self.assertEqual({k: v for k, v in apres.items() if k != "next_id"},
                         {k: v for k, v in avant.items() if k != "next_id"})
        self.assertEqual(apres.get("next_id"), avant.get("next_id"), "un refus a avancé le compteur")

    def new_refuse(self, *args: str) -> str:
        """Un refus : rc 2, message sur stderr, et le STORE n'a pas bougé
        (ni tâche, ni compteur) — un refus qui allouerait un id serait un trou."""
        avant = self.store() if self.store_path.exists() else None
        rc, out, err = self.cli("new", *args)
        self.assertEqual(rc, 2, (out, err))
        self.assertIn("tasks.py: new", err)
        apres = self.store() if self.store_path.exists() else None
        if avant is None:
            self.assertIsNone(apres, "un refus a créé le store")
        else:
            self.magasin_inchange(avant, apres)
        return err


# ===========================================================================
# Sans marqueur — l'OBLIGATION est inerte ; la FORME reste tenue.
# ===========================================================================
class InerteTests(_Banc):
    def test_sans_marqueur_new_nu_cree_et_ne_pose_aucune_cle(self):
        """MUTANT : `exists()` inversé dans `mesure_refusal` ⇒ refus ici, rouge."""
        self.assertFalse(self.marqueur.exists())
        tid = self.new_ok("tache de banc")
        tache = self.task(tid)
        for cle in ("mesure", "pas_un_defaut", "motif"):
            self.assertNotIn(cle, tache)

    def test_sans_marqueur_l_api_directe_des_appelants_existants_reste_valide(self):
        """Signature POSITIONNELLE des appelants d'avant T-00001128 (banc d'epics,
        scripts) : aucun n'a à changer. MUTANT : `mesure` positionnel sans défaut
        ⇒ TypeError, rouge. L'id rendu est CAPTURÉ, jamais prédit (R-BANCS (i)) :
        sous l'allocateur `P-<ULID>` (C2) aucune valeur n'est devinable."""
        rendus = [tasks.new_task(self.root, "t", "", "refonte"),
                  tasks.new_task(self.root, "t2", "", "", epic=None)]
        ids = []
        for rendu in rendus:
            m = re.fullmatch(r"TASKS: (\S+) → pending", rendu)
            self.assertIsNotNone(m, rendu)
            ids.append(m.group(1))
        self.assertNotEqual(ids[0], ids[1])
        self.assertEqual([t["id"] for t in self.store()["tasks"]], ids)
        self.assertNotIn("mesure", self.task(ids[0]))

    def test_sans_marqueur_une_mesure_valide_est_stockee_quand_meme(self):
        """Le marqueur arme l'obligation, pas le STOCKAGE : une mesure donnée sur
        un board désarmé se garde, son motif avec. MUTANT : `if armé:` autour de
        l'écriture de la clé ⇒ perdue, rouge."""
        tid = self.new_ok("t", *MESURE_ARGS)
        self.assertEqual(self.task(tid)["mesure"], MESURE)
        self.assertEqual(self.task(tid)["motif"], MOTIF)

    def test_sans_marqueur_la_forme_est_tenue(self):
        """Une valeur MALFORMÉE est refusée même désarmé — stockée, personne ne la
        relirait le jour où le marqueur est posé. MUTANT : `if not armé: return
        None` en tête de `mesure_refusal` ⇒ acceptée, rouge."""
        self.new_refuse("t", "--mesure", "python3 x.py rc 1", "--motif", MOTIF)
        self.new_refuse("t", *MESURE_ARGS, "--pas-un-defaut", PAS_UN_DEFAUT)
        self.new_refuse("t", "--pas-un-defaut", "")
        # L1 et L2 sont de la FORME : tenues désarmé aussi.
        self.new_refuse("t", "--mesure", MESURE)
        self.new_refuse("t", "--mesure", MESURE, "--motif", "mineur")
        self.new_refuse("t", "--motif", MOTIF)
        self.new_refuse("Fix: x", "--pas-un-defaut", PAS_UN_DEFAUT)


# ===========================================================================
# Armé — refus sans sortie ; chaque sortie acceptée, stockée, visible.
# ===========================================================================
class ArmeTests(_Banc):
    def setUp(self):
        super().setUp()
        self.armer()

    def test_sans_rien_refuse_et_next_id_ne_bouge_pas(self):
        """MUTANT de référence : `mesure_refusal` rend `None` d'emblée ⇒ créée, rouge.
        « `next_id` ne bouge pas » se dit en PROPRIÉTÉ (R-BANCS (iii)) : vrai avant
        et après la bascule C2, qui retire la clé."""
        amorce = self.new_ok("amorce", *MESURE_ARGS)  # un store existe : il est observable
        avant = self.store()
        err = self.new_refuse("un defaut non mesure")
        for jeton in REFUS_DOCTRINE:
            self.assertIn(jeton, err)
        self.magasin_inchange(avant, self.store())
        self.assertEqual([t["id"] for t in self.store()["tasks"]], [amorce])

    def test_le_refus_precede_l_allocation_et_vit_dans_le_verrou(self):
        """MUTANT : l'id frappé (`record_id_module()`) AVANT `mesure_refusal` ⇒ l'allocateur
        tourne sur un refus, rouge. MUTANT : refus évalué hors du `with
        board_lock` ⇒ `tenu` vaut False, rouge."""
        tenu: list[bool] = []
        verrou_actif = {"on": False}
        original_lock, original_refus = tasks.board_lock, tasks.mesure_refusal

        @contextlib.contextmanager
        def lock_observe(root):
            verrou_actif["on"] = True
            try:
                with original_lock(root):
                    yield
            finally:
                verrou_actif["on"] = False

        def refus_observe(root, mesure, pas_un_defaut, motif=None, titre=""):
            tenu.append(verrou_actif["on"])
            return original_refus(root, mesure, pas_un_defaut, motif=motif, titre=titre)

        with mock.patch.object(tasks, "board_lock", lock_observe), \
                mock.patch.object(tasks, "mesure_refusal", refus_observe), \
                mock.patch.object(tasks, "record_id_module", wraps=tasks.record_id_module) as alloc:
            with self.assertRaises(tasks.BoardError):
                tasks.new_task(self.root, "t", "")
            alloc.assert_not_called()
            tasks.new_task(self.root, "t", "", mesure=MESURE, motif=MOTIF)
            alloc.assert_called_once()
        self.assertEqual(tenu, [True, True])

    def test_mesure_valide_acceptee_et_stockee_telle_quelle(self):
        """MUTANT : clé `mesure` jamais écrite ⇒ absente, rouge."""
        tid = self.new_ok("t", *MESURE_ARGS)
        tache = self.task(tid)
        self.assertEqual(tache["mesure"], MESURE)
        self.assertEqual(tache["motif"], MOTIF)
        self.assertNotIn("pas_un_defaut", tache)
        self.assertEqual(tache["state"], "pending")

    def test_mesure_sans_separateur_refusee(self):
        err = self.new_refuse("t", "--mesure", "python3 x.py rc 1", "--motif", MOTIF)
        self.assertIn("=>", err)
        self.assertIn("BOTH sides", err)

    def test_mesure_a_un_cote_vide_refusee(self):
        """Le séparateur seul ne mesure rien : les deux côtés portent du texte
        VISIBLE. MUTANT : `_texte_visible` retiré d'un côté ⇒ `" => rc 1"`
        accepté, rouge. `"\\t=>\\n"` tombe sur le refus Cc, qui cite la valeur."""
        for valeur in (" => rc 1", "python3 x.py =>", "=>", " => ", "\t=>\n", ""):
            with self.subTest(valeur=valeur):
                err = self.new_refuse("t", "--mesure", valeur, "--motif", MOTIF)
                self.assertIn(repr(valeur), err)

    def test_pas_un_defaut_vide_refuse(self):
        """MUTANT : `if pas_un_defaut is not None: return None` sans `_texte_visible`
        ⇒ accepté, rouge. (Le saut de ligne seul est un Cc : `InvisiblesTests`.)"""
        for valeur in ("", "   "):
            with self.subTest(valeur=valeur):
                err = self.new_refuse("t", "--pas-un-defaut", valeur)
                self.assertIn("reason is empty", err)

    def test_pas_un_defaut_valide_accepte_et_stocke(self):
        tid = self.new_ok("une fonctionnalite", "--pas-un-defaut", PAS_UN_DEFAUT)
        tache = self.task(tid)
        self.assertEqual(tache["pas_un_defaut"], PAS_UN_DEFAUT)
        self.assertNotIn("mesure", tache)
        self.assertNotIn("motif", tache)

    def test_les_deux_a_la_fois_refuses_meme_valides(self):
        """MUTANT : exclusivité retirée ⇒ les deux clés stockées, rouge."""
        err = self.new_refuse("t", *MESURE_ARGS, "--pas-un-defaut", PAS_UN_DEFAUT)
        self.assertIn("exclusive", err)

    def test_la_valeur_est_visible_dans_list_task(self):
        """`format_detail` imprime TOUTE clé : la mesure et son motif se relisent
        SANS toucher le rendu. MUTANT : la clé stockée sous un autre nom ⇒ ligne
        absente, rouge."""
        t1 = self.new_ok("defaut", *MESURE_ARGS)
        t2 = self.new_ok("feature", "--pas-un-defaut", PAS_UN_DEFAUT)
        rc, out, _ = self.cli("list", "--task", t1)
        self.assertEqual(rc, 0)
        self.assertRegex(out, rf"(?m)^mesure\s*: {MESURE_RE}$")
        self.assertRegex(out, rf"(?m)^motif\s*: {MOTIF}$")
        self.assertNotIn("pas_un_defaut", out)
        rc, out, _ = self.cli("list", "--task", t2)
        self.assertEqual(rc, 0)
        self.assertRegex(out, rf"(?m)^pas_un_defaut\s*: {PAS_UN_DEFAUT_RE}$")
        self.assertNotIn("mesure ", out)
        self.assertNotIn("motif", out)

    def test_le_snapshot_v3_ignore_les_trois_cles_et_le_store_se_recharge(self):
        """`SYNC_SNAPSHOT_FIELDS` est GELÉ et `load` refuse un snapshot d'une autre
        forme : la clé neuve n'y entre pas, et le store écrit se recharge.
        MUTANT : `mesure` ajouté au snapshot ⇒ `load` refuse, rouge."""
        self.new_ok("defaut", *MESURE_ARGS)
        self.new_ok("feature", "--pas-un-defaut", PAS_UN_DEFAUT)
        data = tasks.load(self.root)  # la validation du snapshot est ici
        snapshots = [item["after"] for item in data["sync_outbox"]]  # `before` est None sur un `new`
        self.assertEqual(len(snapshots), 2)
        for snapshot in snapshots:
            self.assertEqual(set(snapshot), set(tasks.SYNC_SNAPSHOT_FIELDS))
            for cle in ("mesure", "pas_un_defaut", "motif"):
                self.assertNotIn(cle, snapshot)

    def test_l_aide_de_new_est_ascii_et_nomme_les_trois_drapeaux(self):
        """`--help` sort DANS `parse_args`, avant `force_utf8_stdio` : un accent y
        lèverait sur une console cp1252. MUTANT : `OBSERVÉ` accentué dans le
        metavar ⇒ octet > 127, rouge."""
        rc, out, _ = self.cli("new", "--help")
        self.assertEqual(rc, 0)
        self.assertTrue(all(ord(c) < 128 for c in out), [c for c in out if ord(c) > 127])
        for jeton in ("--mesure", "--pas-un-defaut", "--motif", "MESURE_REQUIRED", "=>", *tasks.MOTIFS):
            self.assertIn(jeton, out)


# ===========================================================================
# L1 — `--mesure` EXIGE `--motif`, liste FERMÉE ; « mineur » n'ouvre pas de tâche.
# ===========================================================================
class MotifTests(_Banc):
    def setUp(self):
        super().setUp()
        self.armer()

    def test_la_liste_est_celle_du_pilote(self):
        """MUTANT : un motif ajouté ou retiré ⇒ rouge — la liste est FERMÉE."""
        self.assertEqual(tasks.MOTIFS, ("garde", "securite", "decision-pilote", "gros", "sans-fournee"))
        self.assertEqual(set(tasks.MOTIFS_SENS), set(tasks.MOTIFS))

    def test_mesure_sans_motif_refusee_nomme_la_liste_et_la_phrase(self):
        """MUTANT « L1 désactivée » : le `if motif is None` retiré ⇒ créée, rouge."""
        err = self.new_refuse("un defaut", "--mesure", MESURE)
        self.assertIn("--motif", err)
        self.assertIn("REQUIRED", err)
        for m in tasks.MOTIFS:
            self.assertIn(m, err)
        self.assertIn(tasks.MINEUR_SUR_PLACE, err)

    def test_motif_mineur_et_hors_liste_refuses_avec_la_phrase(self):
        """MUTANT : `motif not in MOTIFS` ⇒ `motif in MOTIFS` ⇒ `mineur` stocké, rouge."""
        for valeur in ("mineur", "MINEUR", "Garde", "garde ", "autre", "", "securite,gros"):
            with self.subTest(motif=valeur):
                err = self.new_refuse("un defaut", "--mesure", MESURE, "--motif", valeur)
                self.assertIn(repr(valeur), err)
                self.assertIn("closed list", err)
                self.assertIn(tasks.MINEUR_SUR_PLACE, err)

    def test_chaque_motif_de_la_liste_accepte_et_stocke(self):
        """MUTANT : clé `motif` jamais écrite ⇒ absente, rouge."""
        for m in tasks.MOTIFS:
            with self.subTest(motif=m):
                tid = self.new_ok(f"defaut {m}", "--mesure", MESURE, "--motif", m)
                self.assertEqual(self.task(tid)["motif"], m)
                self.assertEqual(self.task(tid)["mesure"], MESURE)

    def test_motif_sans_mesure_refuse_seul_et_avec_pas_un_defaut(self):
        """MUTANT : `motif is not None and mesure is None` retiré ⇒ un motif
        orphelin passe (et, désarmé, serait stocké sans mesure), rouge."""
        for args in (("--motif", MOTIF), ("--motif", MOTIF, "--pas-un-defaut", PAS_UN_DEFAUT)):
            with self.subTest(args=args):
                err = self.new_refuse("une fonctionnalite", *args)
                self.assertIn("--motif", err)
                self.assertIn("accompanies --mesure only", err)

    def test_motif_sans_mesure_refuse_aussi_desarme(self):
        """La FORME est tenue désarmé : un motif orphelin ne se stocke jamais.
        MUTANT : refus de L1 derrière `exists()` ⇒ stocké désarmé, rouge."""
        self.marqueur.unlink()
        self.new_refuse("t", "--motif", MOTIF)
        self.new_refuse("t", "--mesure", MESURE)
        self.new_refuse("t", "--mesure", MESURE, "--motif", "mineur")

    def test_le_refus_de_motif_precede_l_allocation(self):
        """Même propriété que le refus de doctrine : aucun id alloué sur un motif
        refusé. MUTANT : L1 évaluée après l'écriture ⇒ une tâche est ajoutée, rouge ;
        sans compteur, une frappe sans écriture ne laisse aucune trace au magasin :
        « refus AVANT frappe » est tenu par le témoin `record_id_module` plus haut
        (dit en PROPRIÉTÉ, R-BANCS (iii) : vrai avant et après la bascule C2)."""
        amorce = self.new_ok("amorce", *MESURE_ARGS)
        avant = self.store()
        self.new_refuse("un defaut", "--mesure", MESURE, "--motif", "mineur")
        self.new_refuse("un defaut", "--mesure", MESURE)
        self.magasin_inchange(avant, self.store())
        self.assertEqual([t["id"] for t in self.store()["tasks"]], [amorce])


# ===========================================================================
# L2 — `--pas-un-defaut` est REFUSÉ quand le TITRE ouvre par le lexique d'un défaut.
# ===========================================================================
class LexiqueTests(_Banc):
    def setUp(self):
        super().setUp()
        self.armer()

    def test_le_lexique_livre_est_celui_mesure(self):
        """MUTANT : un mot ajouté (`rougit`, `casse`…) ou retiré ⇒ rouge. Le
        lexique a été MESURÉ sur le board avant d'être figé (2026-10-03)."""
        self.assertEqual(tasks.LEXIQUE_DEFAUT, LEXIQUE_MESURE)

    def test_titre_defaut_lit_l_ouverture_casse_et_accents_replies(self):
        """Fonction pure. MUTANT « L2 désactivée » : `titre_defaut` rend `None` ⇒ rouge."""
        for titre in TITRES_DEFAUT:
            with self.subTest(titre=titre):
                self.assertIsNotNone(tasks.titre_defaut(titre), titre)
        for titre in TITRES_SAINS:
            with self.subTest(titre=titre):
                self.assertIsNone(tasks.titre_defaut(titre), titre)
        self.assertEqual(tasks.titre_defaut("[BK-317][P1] Faux positif fail-closed"), "[bk-317][p1] faux positif")
        self.assertEqual(tasks.titre_defaut("fix(night) x"), "fix")

    def test_titre_de_defaut_refuse_pas_un_defaut_et_nomme_le_remede(self):
        """MUTANT « L2 désactivée » ⇒ `--pas-un-defaut` passe sur « Fix: … », rouge."""
        for titre in TITRES_DEFAUT:
            with self.subTest(titre=titre):
                err = self.new_refuse(titre, "--pas-un-defaut", PAS_UN_DEFAUT)
                self.assertIn("lexicon of a DEFECT", err)
                self.assertIn('--mesure "<command that reproduces> => <observed result>" --motif <M>', err)

    def test_titre_sain_accepte_pas_un_defaut(self):
        """CONTRÔLE NÉGATIF : sans lui, un lexique qui refuse TOUT serait vert.
        « par défaut », « faux positifs » en milieu de titre, « Fixer », « Fixture »,
        « Debug » ne sont pas des ouvertures de défaut."""
        for titre in TITRES_SAINS:
            with self.subTest(titre=titre):
                tid = self.new_ok(titre, "--pas-un-defaut", PAS_UN_DEFAUT)
                self.assertEqual(self.task(tid)["pas_un_defaut"], PAS_UN_DEFAUT)

    def test_un_titre_de_defaut_passe_par_mesure_et_motif(self):
        """Le remède nommé fonctionne : le même titre, mesuré, est créé.
        MUTANT : L2 appliquée aussi à `--mesure` ⇒ refus, rouge."""
        tid = self.new_ok(TITRES_DEFAUT[0], *MESURE_ARGS)
        self.assertEqual(self.task(tid)["task"], TITRES_DEFAUT[0])

    def test_le_refus_lexical_est_tenu_desarme(self):
        """MUTANT : L2 derrière `exists()` ⇒ stocké désarmé, rouge."""
        self.marqueur.unlink()
        err = self.new_refuse("Fix: x", "--pas-un-defaut", PAS_UN_DEFAUT)
        self.assertIn("lexicon of a DEFECT", err)
        self.new_ok("Fixer la doc", "--pas-un-defaut", PAS_UN_DEFAUT)


# ===========================================================================
# Forme — caractères de contrôle ou invisibles (Cc/Cf), côtés sans texte VISIBLE.
# ===========================================================================
class InvisiblesTests(_Banc):
    def setUp(self):
        super().setUp()
        self.armer()

    def test_zwsp_de_chaque_cote_du_separateur_refuse(self):
        """Contournement rejoué par critic-opus : `'\\u200b=>\\u200b'` passait
        `.strip()`. MUTANT : `_caractere_invisible` qui rend `None` ⇒ accepté, rouge."""
        err = self.new_refuse("t", "--mesure", "​=>​", "--motif", MOTIF)
        self.assertIn("invisible", err)
        self.assertIn("Cf", err)
        self.assertIn("--mesure", err)

    def test_saut_de_ligne_dans_la_mesure_refuse_aucune_ligne_forgee(self):
        """Contournement rejoué : `'x => y\\nstate      : done'` fabriquait une
        fausse ligne `state : done` dans `list --task`. MUTANT : `Cc` retiré de
        `_INVISIBLES` ⇒ créée, et la ligne forgée s'imprime, rouge."""
        amorce = self.new_ok("amorce", *MESURE_ARGS)
        err = self.new_refuse("t", "--mesure", "x => y\nstate      : done", "--motif", MOTIF)
        self.assertIn("Cc", err)
        self.assertIn("forge", err)
        rc, out, _ = self.cli("list", "--task", amorce)
        self.assertEqual(rc, 0)
        self.assertNotIn("state      : done", out)

    def test_esc_et_tabulation_refuses_sur_pas_un_defaut(self):
        """MUTANT : la boucle des trois drapeaux ne lit que `--mesure` ⇒ ESC stocké, rouge."""
        for valeur in ("\x1b[31mrouge\x1b[0m", "une raison\tavec tabulation", "\n", "raison\r"):
            with self.subTest(valeur=valeur):
                err = self.new_refuse("t", "--pas-un-defaut", valeur)
                self.assertIn("--pas-un-defaut", err)
                self.assertIn("Cc", err)

    def test_zwsp_et_bom_seuls_refuses_sur_pas_un_defaut(self):
        """`'\\u200b'` passait `.strip()` comme une raison. MUTANT : `Cf` retiré ⇒ rouge."""
        for valeur in ("​", "﻿", " ​ "):
            with self.subTest(valeur=valeur):
                err = self.new_refuse("t", "--pas-un-defaut", valeur)
                self.assertIn("Cf", err)

    def test_separateurs_de_ligne_unicode_refuses(self):
        """U+2028 (Zl) et U+2029 (Zp) coupent une ligne pour plus d'un afficheur :
        advisory de security-code-review (S-00003960). MUTANT : Zl/Zp retirés ⇒ rouge."""
        for valeur, cat in (("x => y state : done", "Zl"), ("raison ", "Zp")):
            with self.subTest(valeur=valeur):
                drapeau = ("--mesure", valeur, "--motif", MOTIF) if "=>" in valeur else ("--pas-un-defaut", valeur)
                self.assertIn(cat, self.new_refuse("t", *drapeau))

    def test_un_cote_fait_de_blancs_insecables_refuse(self):
        """U+00A0 est Zs, pas Cc/Cf : c'est `_texte_visible` qui le refuse, pas la
        boucle. MUTANT : `_texte_visible` remplacé par `.strip()` ⇒ accepté, rouge."""
        for valeur in (" => rc 1", "python3 x.py =>　", "  =>  "):
            with self.subTest(valeur=valeur):
                err = self.new_refuse("t", "--mesure", valeur, "--motif", MOTIF)
                self.assertIn("VISIBLE text on BOTH sides", err)

    def test_motif_avec_invisible_refuse_avant_la_liste(self):
        """`'garde\\u200b'` n'est PAS `garde` : refusé comme invisible, nommément,
        avant le refus de liste. MUTANT : `--motif` hors de la boucle ⇒ le refus
        est celui de la liste, rouge sur le jeton `Cf`."""
        err = self.new_refuse("t", "--mesure", MESURE, "--motif", "garde​")
        self.assertIn("--motif", err)
        self.assertIn("Cf", err)
        self.assertNotIn("closed list", err)

    def test_le_refus_invisible_ne_depend_pas_du_marqueur(self):
        """MUTANT : boucle Cc/Cf derrière `exists()` ⇒ stocké désarmé, rouge."""
        self.marqueur.unlink()
        self.new_refuse("t", "--mesure", "​=>​", "--motif", MOTIF)
        self.new_refuse("t", "--pas-un-defaut", "\x1b")

    def test_controle_negatif_accents_tirets_et_espaces_passent(self):
        """Sans lui, une boucle qui refuse tout caractère > 127 serait verte."""
        mesure = "python3 x.py — « é » => rc 1 ; KeyError: 'été'"
        tid = self.new_ok("t", "--mesure", mesure, "--motif", MOTIF)
        self.assertEqual(self.task(tid)["mesure"], mesure)
        tid = self.new_ok("t", "--pas-un-defaut", "décision pilote — S-00003957")
        self.assertEqual(self.task(tid)["pas_un_defaut"], "décision pilote — S-00003957")


if __name__ == "__main__":
    unittest.main()
