"""T-00001058 (BK-771, E-26) : la `sync_outbox` du board en UN FICHIER PAR INTENT, versionné (O2), et le refus
NOMMÉ d'une résurrection (F5).

Témoins W1-W13 du plan `docs/tasks/T-00001058-plan.md` rév. 1.1, plus les réserves du mandat : C1 (bail posé par
`claim` vu d'un autre processus), C2 (fichier d'intent DÉTACHÉ de son TASKS.json par `git stash` sans -u, variante
de W8), C3 (lot dont la mutation est rejouée à la main, variante de W5(a)) et D4 (f) (intent hors forme dans un
fichier définitif : validé comme `load`, exclu de la vue, mis en quarantaine). Chaque témoin est ROUGE sur la BASE
(fusion de T-00001053) pour la raison nommée dans sa docstring, sauf W4 et le témoin de lecture, garde-fous VERTS
avant ; les mutants qui doivent les tuer sont nommés dans la même docstring. Passe de correction de la clôture :
W2c et W2b (quarantaine EN PLACE), W8d/W8e (F5 à deux ids), W14 (plafonds de lecture), W15a-d (sondes de
l'exec-critic : rang des lots, C3 positif, suspension « déversement seul », jamais « dossier − liste ») et W16
(contrôles du lecteur tolérant).

Montage : une racine jetable par témoin sous `tempfile`, `CADRE_STATE_DIR` / `AGENTS_EVENTS_DIR` / `TMPDIR`
posés. Bancs à deux clones = git réel, `.agents/state/board` commité ENTIER (S-00003917 (4)), identité git en
config LOCALE, hooks git coupés ; les ids sont LUS à la création, jamais écrits en dur ; un `operation_id` n'est
forcé (`uuid4` remplacé) que là où le témoin a besoin de clés adjacentes ou éloignées. Un crash DUR (`os._exit`)
se joue dans un sous-processus qui charge `tasks.py` par chemin et remplace UNE couture par son nom. Le pont V3,
quand un verbe passe par `main`, construit son store sous `CADRE_STATE_DIR` et son consumer est remplacé par un
enregistreur (`BoardBridge.consume_board_intent`). Aucun parcours récursif (filet `test_repo_walk_census.py`) :
`Path.glob("*.json")` non récursif seul.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
import uuid
from pathlib import Path
from typing import Any
from unittest import mock

TASKS_PATH = Path(__file__).with_name("tasks.py")
HOOK = Path(__file__).with_name("post-task-done-index.sh")
REPO = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("tasks_outbox_o2_under_test", TASKS_PATH)
assert SPEC is not None and SPEC.loader is not None
tasks = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = tasks
SPEC.loader.exec_module(tasks)
tasks._RESOLVEUR_V3.charger_paquet(REPO, "agentic_v3")

BOARD_REL = Path(".agents") / "state" / "board"
TASKS_REL = BOARD_REL / "TASKS.json"
DOSSIER_REL = BOARD_REL / "sync_outbox"
LOTS_REL = Path(".agents") / "state" / "local" / "sync_outbox_lots"
QUARANTAINE_REL = Path(".agents") / "state" / "local" / "sync_outbox_quarantaine"
NOM_DEFINITIF = re.compile(r"\A(\d{20})-(.+)\.json\Z")
CRASH = 17
JOUR = "2026-10-10"

#: Préambule de tout sous-processus de crash : `tasks.py` chargé par chemin, la racine en `racine`.
_PREAMBULE = (
    "import importlib.util, json, os, sys\n"
    "s = importlib.util.spec_from_file_location('t1058_crash', sys.argv[1])\n"
    "m = importlib.util.module_from_spec(s)\n"
    "sys.modules[s.name] = m\n"
    "s.loader.exec_module(m)\n"
    "racine = sys.argv[2]\n"
)
#: Crash DUR à la publication de TASKS.json : le lot est écrit, le `replace` n'a pas lieu.
CRASH_AVANT_REPLACE = """
vrai = m._replace_with_retry
def coupe(src, cible):
    if os.path.basename(str(cible)) == "TASKS.json":
        os._exit(17)
    return vrai(src, cible)
m._replace_with_retry = coupe
"""
#: Crash DUR après le `replace`, avant l'éclatement du lot (couture `_eclater_lot`, absente de la BASE).
CRASH_AVANT_ECLATEMENT = """
def coupe(*_a, **_k):
    os._exit(17)
m._eclater_lot = coupe
"""
#: Crash DUR au DEUXIÈME fichier définitif posé pendant l'éclatement.
CRASH_AU_DEUXIEME_DEFINITIF = """
vrai, vus = os.replace, []
def coupe(src, cible):
    if os.path.basename(os.path.dirname(str(cible))) == "sync_outbox":
        vus.append(cible)
        if len(vus) == 2:
            os._exit(17)
    return vrai(src, cible)
m.os.replace = coupe
"""


def _uuid(tete: str, n: int) -> uuid.UUID:
    """Un uuid4 de forme valide dont les 8 premiers chiffres sont `tete` : il se TRIE où le témoin l'exige."""
    return uuid.UUID(f"{tete}-0000-4000-8000-{n:012x}")


def _vrai(_intent: dict[str, Any]) -> bool:
    return True


def _tache(tid: str, titre: str, state: str = "pending") -> dict[str, Any]:
    return {"id": tid, "state": state, "task": titre, "owner": "", "stage": "", "updated": JOUR}


def _git(depot: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in ("GIT_DIR", "GIT_WORK_TREE")}
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    p = subprocess.run(["git", "-C", str(depot), "-c", "core.hooksPath=/dev/null", *args],
                       capture_output=True, text=True, env=env)
    if check and p.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} : rc={p.returncode} {p.stderr[-400:]}")
    return p


def _identite(depot: Path) -> None:
    for cle, valeur in (("user.email", "banc@example.invalid"), ("user.name", "banc"), ("commit.gpgsign", "false")):
        _git(depot, "config", cle, valeur)


def _commit(depot: Path, message: str) -> None:
    """`.agents/state/board` commité ENTIER — TASKS.json ET le dossier des intents (S-00003917 (4))."""
    _git(depot, "add", "-A", "--", str(BOARD_REL))
    _git(depot, "commit", "-q", "--allow-empty", "-m", message)


def _brut(racine: Path) -> dict[str, Any]:
    return json.loads((racine / TASKS_REL).read_text(encoding="utf-8"))


def _ecrire_brut(racine: Path, data: dict[str, Any]) -> None:
    (racine / TASKS_REL).parent.mkdir(parents=True, exist_ok=True)
    (racine / TASKS_REL).write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                                    encoding="utf-8")


def _vue(racine: Path) -> list[str]:
    return [intent["operation_id"] for intent in tasks.load(str(racine)).get("sync_outbox", [])]


def _noms(dossier: Path) -> list[str]:
    return sorted(p.name for p in dossier.glob("*.json")) if dossier.is_dir() else []


def _definitifs(racine: Path) -> list[str]:
    return _noms(racine / DOSSIER_REL)


def _lots(racine: Path) -> list[str]:
    return _noms(racine / LOTS_REL)


def _quarantaine(racine: Path) -> list[str]:
    return sorted(p.name for p in (racine / QUARANTAINE_REL).glob("*")) if (racine / QUARANTAINE_REL).is_dir() else []


def _cle(racine: Path, op: str) -> int:
    (cle,) = [int(m.group(1)) for m in map(NOM_DEFINITIF.match, _definitifs(racine)) if m and m.group(2) == op]
    return cle


def _nouvelle(racine: Path, titre: str) -> str:
    return tasks.new_task(str(racine), titre, "banc").split()[1]


def _drainer(racine: Path) -> list[str]:
    livres: list[str] = []

    def consumer(intent: dict[str, Any]) -> bool:
        livres.append(intent["operation_id"])
        return True

    tasks.drain_sync_outbox(str(racine), consumer)
    return livres


def _crash(racine: Path, couture: str, appel: str) -> subprocess.CompletedProcess:
    code = _PREAMBULE + textwrap.dedent(couture) + appel + "\n"
    return subprocess.run([sys.executable, "-c", code, str(TASKS_PATH), str(racine)],
                          capture_output=True, text=True, env=dict(os.environ))


def _ops_du_lot(racine: Path, nom: str, sous: Path = LOTS_REL) -> list[str]:
    lot = json.loads((racine / sous / nom).read_text(encoding="utf-8"))
    return [entree["enveloppe"]["intent"]["operation_id"] for entree in lot["intents"]]


class _Racine(unittest.TestCase):
    """Une racine jetable, un environnement d'état isolé, et le pont V3 importable pour `main`."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "repo"
        (self.root / BOARD_REL).mkdir(parents=True)
        (self.base / "tmp").mkdir()
        env = mock.patch.dict(os.environ, {
            "CADRE_STATE_DIR": str(self.base / "state"),
            "AGENTS_EVENTS_DIR": str(self.base / "events"),
            "TMPDIR": str(self.base / "tmp"),
        })
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("CADRE_PROJECT_ROOT", None)
        # REPO en tête inoffensif : agentic_v3 déjà fixé par charger_paquet (ligne 49).
        if str(REPO) not in sys.path:
            sys.path.insert(0, str(REPO))
            self.addCleanup(sys.path.remove, str(REPO))
        self.livres: list[str] = []

    def main(self, racine: Path, *args: str) -> tuple[int, str, str]:
        """`tasks.main` sur `racine`, le consumer du pont remplacé par un enregistreur (`self.livres`), sous un
        `CADRE_STATE_DIR` PROPRE à `racine` (un rôle par clone : garde T-753 des partitions apparentées)."""
        from agentic_v3.reconciliation import board_bridge

        def consumer(_pont: Any, intent: dict[str, Any]) -> bool:
            self.livres.append(intent["operation_id"])
            return True

        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(board_bridge.BoardBridge, "consume_board_intent", consumer), \
                mock.patch.dict(os.environ, {"CADRE_STATE_DIR": str(self.base / f"state-{racine.name}")}), \
                mock.patch("sys.stdout", out), mock.patch("sys.stderr", err):
            rc = tasks.main(["--root", str(racine), *args])
        return rc, out.getvalue(), err.getvalue()

    def depot(self, nom: str, titres: list[str], ops: list[uuid.UUID] | None = None) -> tuple[Path, list[str]]:
        """Un dépôt git dont le board porte `titres` (création sous `ops` si donnés), intents drainés,
        `.agents/state/board` commité."""
        depot = self.base / nom
        (depot / BOARD_REL).mkdir(parents=True)
        _git(depot, "-c", "init.defaultBranch=main", "init", "-q")
        _identite(depot)
        ids = []
        for rang, titre in enumerate(titres):
            with mock.patch.object(tasks.uuid, "uuid4", return_value=ops[rang]) if ops else mock.patch.dict({}):
                ids.append(_nouvelle(depot, titre))
        _drainer(depot)
        _commit(depot, "base")
        return depot, ids

    def clones(self, depot: Path, nom: str) -> tuple[Path, Path]:
        paire = []
        for cote in ("A", "B"):
            clone = self.base / f"{nom}-{cote}"
            subprocess.run(["git", "clone", "-q", "--no-local", str(depot), str(clone)], check=True,
                           capture_output=True)
            _identite(clone)
            paire.append(clone)
        return paire[0], paire[1]

    def fusionner(self, ca: Path, cb: Path, strategie: str) -> int:
        _git(ca, "fetch", "-q", str(cb), "HEAD")
        if strategie == "union":
            attributs = Path(_git(ca, "rev-parse", "--git-path", "info/attributes").stdout.strip())
            attributs = attributs if attributs.is_absolute() else ca / attributs
            attributs.parent.mkdir(parents=True, exist_ok=True)
            attributs.write_text(f"{TASKS_REL.as_posix()} merge=union\n", encoding="utf-8")
        options = {"ours": ["-X", "ours"], "theirs": ["-X", "theirs"]}.get(strategie, [])
        return _git(ca, "merge", "-q", "--no-edit", *options, "FETCH_HEAD", check=False).returncode


class OutboxO2Tests(_Racine):
    # -- W1 : F3, deux clones -----------------------------------------------------------------------------------
    def test_W1_F3_deux_clones_ours_theirs_aucune_perte(self) -> None:
        """A et B posent chacun un intent non drainé, B est fusionné dans A sous `-X ours` puis `-X theirs`, uuid4
        FORCÉ en deux bras (S-00003917 (2)) : clés ADJACENTES (même point d'insertion dans `sync_correlations`) ⇒
        une clé tombe au texte, l'orphelin est RÉ-INDEXÉ depuis son fichier, 0 refus de lecture ; clés NON
        adjacentes ⇒ les deux clés sont gardées. Dans les deux, la vue de A porte A ∪ B et le drain livre chacun UNE
        fois. ROUGE sur la BASE : les deux intents s'insèrent dans la même liste `sync_outbox` de TASKS.json, la
        stratégie en garde un, `load` accepte (M2u). Mutants : M-drop (orphelin écarté de la vue)."""
        depot, ids = self.depot("w1-base", ["F3-1", "F3-2", "F3-3"])
        bras = {"adjacentes": (_uuid("00000000", 1), _uuid("00000000", 2)),
                "non-adjacentes": (_uuid("00000000", 1), _uuid("ffffffff", 2))}
        for nom, (op_a, op_b) in bras.items():
            for strategie in ("ours", "theirs"):
                with self.subTest(bras=nom, strategie=strategie):
                    ca, cb = self.clones(depot, f"w1-{nom}-{strategie}")
                    with mock.patch.object(tasks.uuid, "uuid4", return_value=op_a):
                        tasks.stage_task(str(ca), ids[0], "F3-A")
                    with mock.patch.object(tasks.uuid, "uuid4", return_value=op_b):
                        tasks.stage_task(str(cb), ids[2], "F3-B")
                    _commit(ca, "A")
                    _commit(cb, "B")
                    self.assertEqual(0, self.fusionner(ca, cb, strategie))
                    attendus = sorted([str(op_a), str(op_b)])
                    err = io.StringIO()
                    with mock.patch("sys.stderr", err):
                        self.assertEqual(attendus, sorted(_vue(ca)), "la vue de A doit porter A ∪ B")
                    cles = set(_brut(ca)["sync_correlations"])
                    tombees = {op for op in attendus if op not in cles}
                    self.assertEqual(1 if nom == "adjacentes" else 0, len(tombees), (nom, strategie, tombees))
                    livres = _drainer(ca)
                    self.assertEqual(attendus, sorted(livres), "chaque intent livré UNE fois")
                    self.assertEqual([], _vue(ca))

    # -- W2 : orphelin ----------------------------------------------------------------------------------------
    def test_W2_orphelin_re_indexe_depuis_son_fichier(self) -> None:
        """Un fichier définitif dont la clé est retirée de TASKS.json : `load` ne lève pas, la vue le porte avec la
        corrélation de son enveloppe, le `save()` suivant remet la clé au texte et le dit en UNE ligne stderr.
        ROUGE sur la BASE : l'intent est dans TASKS.json, la clé retirée ⇒ « no valid correlation ». Mutants :
        M-strict (levée au load), M-drop (orphelin écarté)."""
        _nouvelle(self.root, "orphelin")
        (op,) = _vue(self.root)
        brut = _brut(self.root)
        correlation = brut["sync_correlations"].pop(op)
        _ecrire_brut(self.root, brut)
        data = tasks.load(str(self.root))
        self.assertEqual([op], [intent["operation_id"] for intent in data["sync_outbox"]])
        self.assertEqual(correlation, data["sync_correlations"][op])
        err = io.StringIO()
        with mock.patch("sys.stderr", err):
            tasks.save(str(self.root), data)
        self.assertEqual(correlation, _brut(self.root)["sync_correlations"].get(op))
        self.assertEqual(1, len([ligne for ligne in err.getvalue().splitlines() if op in ligne]), err.getvalue())

    def test_W2b_D4f_un_intent_hors_forme_dans_un_definitif_est_valide_comme_load(self) -> None:
        """D4 (f), clôture de T-1053 : un fichier définitif dont le bail porte `expires_at: "x"` est VALIDÉ comme
        `load` valide une entrée en ligne (tasks_stockage.py `_validate_sync_extensions`) : exclu de la vue sans
        levée (lecture TOLÉRANTE), `claim` ne lève pas `float("x")`, le `save()` suivant le LAISSE EN PLACE (dossier
        versionné, décision pilote de clôture) et en pose UNE COPIE en quarantaine locale, avec UNE ligne stderr par
        save — jamais un `unlink`, jamais une deuxième copie du même contenu. ROUGE sur la BASE : aucun fichier
        définitif n'existe ; avant la décision, le fichier était DÉPLACÉ. Mutants : M-sans-validation (intent de
        fichier non validé ⇒ `claim` lève), M-déplace (fichier versionné déplacé), M-recopie (`.1` au save suivant)."""
        _nouvelle(self.root, "hors-forme")
        (nom,) = _definitifs(self.root)
        chemin = self.root / DOSSIER_REL / nom
        enveloppe = json.loads(chemin.read_text(encoding="utf-8"))
        enveloppe["intent"]["lease"] = {"owner": "autre", "token": "t", "expires_at": "x"}
        chemin.write_text(json.dumps(enveloppe, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        octets = chemin.read_bytes()
        self.assertEqual([], _vue(self.root))
        self.assertIsNone(tasks.claim_sync_event(str(self.root), "banc"))
        for passe in (1, 2):
            err = io.StringIO()
            with mock.patch("sys.stderr", err):
                tasks.save(str(self.root), tasks.load(str(self.root)))
            self.assertEqual(([nom], [nom]), (_definitifs(self.root), _quarantaine(self.root)), passe)
            self.assertEqual(octets, chemin.read_bytes())
            self.assertEqual(octets, (self.root / QUARANTAINE_REL / nom).read_bytes())
            self.assertEqual(1, len([ligne for ligne in err.getvalue().splitlines() if "quarantaine" in ligne]),
                             err.getvalue())
        self.assertEqual([], _vue(self.root))

    def test_W2c_un_definitif_suivi_illisible_reste_suivi_aucun_retrait_au_status(self) -> None:
        """Clôture (critic-opus T4, décision pilote « laisser en place ») : un définitif COMMITÉ puis corrompu, puis un
        `stage` : `git status` ne montre AUCUN retrait (` D`) sous le board — le prochain commit des magasins
        n'efface rien chez les autres clones — et une copie est en quarantaine. ROUGE avant : le fichier était
        DÉPLACÉ, ` D .agents/state/board/sync_outbox/…` (mesuré quar1). Mutant : M-déplace."""
        depot, (tid,) = self.depot("w2c", ["W2c"])
        tasks.stage_task(str(depot), tid, "en attente")
        (nom,) = _definitifs(depot)
        _commit(depot, "intent suivi")
        (depot / DOSSIER_REL / nom).write_text("{", encoding="utf-8")
        with mock.patch("sys.stderr", io.StringIO()):
            tasks.stage_task(str(depot), tid, "suivant")
        statut = _git(depot, "status", "--porcelain", "--untracked-files=all", "--", BOARD_REL.as_posix()).stdout
        self.assertNotIn(" D ", f" {statut}", statut)
        self.assertIn(f" M {(DOSSIER_REL / nom).as_posix()}", statut)
        self.assertEqual([nom], _quarantaine(depot))

    # -- W3 : stage non drainé -----------------------------------------------------------------------------------
    def test_W3_un_stage_non_draine_vit_dans_un_fichier_hors_de_TASKS_json(self) -> None:
        """`stage` sans drain : les octets de TASKS.json ne portent plus `sync_outbox`, et
        `sync_outbox/<ordre:20 chiffres>-<operation_id>.json` porte l'intent (objet JSON trié, indenté, LF).
        ROUGE sur la BASE : l'intent est dans TASKS.json. Mutant : M-O1 (`publie` garde `sync_outbox`)."""
        tid = _nouvelle(self.root, "w3")
        _drainer(self.root)
        tasks.stage_task(str(self.root), tid, "w3")
        self.assertNotIn("sync_outbox", _brut(self.root))
        (op,) = _vue(self.root)
        (nom,) = _definitifs(self.root)
        match = NOM_DEFINITIF.match(nom)
        self.assertIsNotNone(match, nom)
        self.assertEqual(op, match.group(2))
        texte = (self.root / DOSSIER_REL / nom).read_text(encoding="utf-8")
        enveloppe = json.loads(texte)
        self.assertEqual(op, enveloppe["intent"]["operation_id"])
        self.assertEqual(json.dumps(enveloppe, indent=2, ensure_ascii=False, sort_keys=True) + "\n", texte)

    # -- W4 : garde de commit -------------------------------------------------------------------------------------
    def test_W4_garde_de_commit_qui_refuse_ne_laisse_ni_fichier_ni_lot(self) -> None:
        """La garde de commit refuse le `save()` d'un `retitle` : aucun fichier définitif ni lot ne reste, le board est
        intact, le verbe suivant passe. VERT sur la BASE (garde-fou) ; son rouge est celui de M-naïf (fichiers
        définitifs posés AVANT le `replace`, jamais retirés) — DÉDUIT au plan, joué ici en mutant."""
        tid = _nouvelle(self.root, "w4")
        avant, octets = _definitifs(self.root), (self.root / TASKS_REL).read_bytes()
        with self.assertRaises(tasks.BoardError):
            with tasks.guard_board_commit(lambda: False):
                tasks.retitle_task(str(self.root), tid, "refusé")
        self.assertEqual((avant, [], octets), (_definitifs(self.root), _lots(self.root),
                                               (self.root / TASKS_REL).read_bytes()))
        tasks.stage_task(str(self.root), tid, "ensuite")
        self.assertEqual(2, len(_vue(self.root)))

    def test_W4b_fsync_du_lot_en_echec_le_verbe_echoue_et_ne_laisse_aucun_lot(self) -> None:
        """Disque plein à l'écriture du lot (`fsync` qui lève) : le verbe échoue AVANT la publication, le board est
        intact et AUCUN lot ne reste (sinon le save suivant le mettrait en quarantaine pour rien). Écrit à la reprise
        (le banc de déversement D5 l'a montré) ; ROUGE sur la BASE : aucun lot n'existe, la levée n'a pas lieu.
        Mutant : M-lot-orphelin (nettoyage de `_ecrire_lot` retiré)."""
        tid = _nouvelle(self.root, "w4b")
        avant, octets = _definitifs(self.root), (self.root / TASKS_REL).read_bytes()
        with mock.patch.object(tasks.os, "fsync", side_effect=OSError("banc : disque plein")):
            with self.assertRaises(OSError):
                tasks.stage_task(str(self.root), tid, "disque plein")
        self.assertEqual((avant, [], octets), (_definitifs(self.root), _lots(self.root),
                                               (self.root / TASKS_REL).read_bytes()))

    # -- W5 : crash dur ------------------------------------------------------------------------------------------
    def _lot_avant_replace(self, tid: str, etape: str) -> tuple[str, str]:
        """Crash DUR au `replace` de TASKS.json pendant `stage` : rend (nom du lot, son operation_id)."""
        p = _crash(self.root, CRASH_AVANT_REPLACE, f"m.stage_task(racine, {tid!r}, {etape!r})")
        lots = _lots(self.root)
        self.assertEqual(1, len(lots), f"un lot attendu sous {LOTS_REL} : rc={p.returncode} {p.stderr[-300:]}")
        self.assertEqual(CRASH, p.returncode, p.stderr[-300:])
        (op,) = _ops_du_lot(self.root, lots[0])
        return lots[0], op

    def test_W5a_crash_avant_replace_quarantaine_rien_n_est_livre(self) -> None:
        """Crash DUR (`os._exit`) lot écrit, AVANT le `replace` : le lot est hors de la vue ; la MÊME mutation rejouée
        (C3) le met en QUARANTAINE avec UNE ligne stderr — pas d'éclatement, jamais un `unlink` ; seul l'intent du
        rejeu est livré. ROUGE sur la BASE : aucun lot (chemins absents). Mutants : M-sans-reprise (le lot reste et
        rien n'est dit), M-unlink (le lot est effacé)."""
        tid = _nouvelle(self.root, "w5a")
        _drainer(self.root)
        lot, op_crash = self._lot_avant_replace(tid, "w5a")
        self.assertNotIn(op_crash, _vue(self.root))
        err = io.StringIO()
        with mock.patch("sys.stderr", err):
            tasks.stage_task(str(self.root), tid, "w5a")
        self.assertEqual([], _lots(self.root))
        self.assertEqual([lot], _quarantaine(self.root))
        self.assertEqual(1, len([ligne for ligne in err.getvalue().splitlines() if "quarantaine" in ligne]),
                         err.getvalue())
        livres = _drainer(self.root)
        self.assertEqual(1, len(livres), livres)
        self.assertNotIn(op_crash, livres)

    def test_W5a_C3_lot_dont_la_mutation_est_rejouee_a_la_main_n_est_pas_valide(self) -> None:
        """C3 : après le crash avant `replace`, un écrivain tiers applique la MÊME mutation à TASKS.json (la tâche
        porte l'`after` de l'intent du lot) sans sa clé : le lot n'est PAS validé — ni par l'empreinte de TASKS.json,
        ni par ses `operation_id` dans `sync_correlations` — donc hors de la vue. ROUGE sur la BASE : aucun lot.
        Mutant : M-critère-after (critère « la tâche porte l'after » de la rév. 1, qui validerait ce lot)."""
        tid = _nouvelle(self.root, "w5a-c3")
        _drainer(self.root)
        _lot, op_crash = self._lot_avant_replace(tid, "rejouée")
        brut = _brut(self.root)
        (tache,) = [t for t in brut["tasks"] if t["id"] == tid]
        tache["stage"] = "rejouée"
        _ecrire_brut(self.root, brut)
        self.assertNotIn(op_crash, _vue(self.root))

    def test_W5b_crash_apres_replace_l_intent_est_vu_a_son_rang_puis_livre_une_fois(self) -> None:
        """Crash DUR APRÈS le `replace`, avant l'éclatement : `tasks.load` voit l'intent À SON RANG par le lot validé
        avant toute reprise ; `replay-sync` (verbe suivant) rend « replayed 1 » et le livre UNE fois. ROUGE sur la
        BASE : aucun lot (chemins absents). Mutant : M-lot-invisible (lot validé hors de la vue)."""
        tid = _nouvelle(self.root, "w5b")
        _drainer(self.root)
        p = _crash(self.root, CRASH_AVANT_ECLATEMENT, f"m.stage_task(racine, {tid!r}, 'w5b')")
        (lot,) = _lots(self.root) or [None]
        self.assertIsNotNone(lot, f"un lot attendu : rc={p.returncode} {p.stderr[-300:]}")
        self.assertEqual(CRASH, p.returncode, p.stderr[-300:])
        self.assertEqual([], _definitifs(self.root))
        (op,) = _ops_du_lot(self.root, lot)
        self.assertEqual([op], _vue(self.root))
        rc, out, err = self.main(self.root, "replay-sync")
        self.assertEqual(0, rc, err)
        self.assertIn("replayed 1 sync intent(s)", out)
        self.assertEqual([op], self.livres)
        self.assertEqual(([], []), (_lots(self.root), _vue(self.root)))

    def test_W5c_crash_au_milieu_de_l_eclatement_rejeu_idempotent(self) -> None:
        """Crash DUR au DEUXIÈME fichier posé par l'éclatement d'un lot de trois : le lot reste (retiré EN DERNIER),
        la vue porte les trois dans l'ordre ; le `save()` suivant rejoue l'éclatement, IDEMPOTENT : trois fichiers,
        aucun doublon, lot retiré. ROUGE sur la BASE : aucun lot. Mutant : M-lot-premier (lot retiré avant
        l'éclatement ⇒ deux intents perdus)."""
        ops = self._herite(3)
        p = _crash(self.root, CRASH_AU_DEUXIEME_DEFINITIF, "m.save(racine, m.load(racine))")
        self.assertEqual(1, len(_lots(self.root)), f"rc={p.returncode} {p.stderr[-300:]}")
        self.assertEqual(CRASH, p.returncode, p.stderr[-300:])
        self.assertEqual(1, len(_definitifs(self.root)))
        self.assertEqual(ops, _vue(self.root))
        tasks.save(str(self.root), tasks.load(str(self.root)))
        self.assertEqual([], _lots(self.root))
        self.assertEqual(ops, [NOM_DEFINITIF.match(n).group(2) for n in _definitifs(self.root)])
        self.assertEqual(ops, _vue(self.root))

    # -- W6 : FIFO ----------------------------------------------------------------------------------------------
    def test_W6_fifo_meme_nanoseconde_et_uuid_decroissant(self) -> None:
        """Trois intents enfilés sous la MÊME nanoseconde, `uuid4` DÉCROISSANT : clés `ns`, `ns+1`, `ns+2`, et
        `claim` les livre dans l'ordre d'enfilage. ROUGE sur la BASE : aucun fichier, aucune clé d'ordre. Mutant :
        M-uuid (tri par operation_id)."""
        compte = iter(range(1, 1000))
        enfiles: list[str] = []
        with mock.patch.object(tasks.time, "time_ns", return_value=10**18), \
                mock.patch.object(tasks.uuid, "uuid4", side_effect=lambda: _uuid(f"{0xf0000000 - next(compte):08x}", 0)):
            for k in range(3):
                vus = set(_vue(self.root))
                _nouvelle(self.root, f"fifo-{k}")
                (op,) = set(_vue(self.root)) - vus
                enfiles.append(op)
        self.assertEqual(sorted(enfiles, reverse=True), enfiles, "les operation_id doivent DÉCROÎTRE")
        noms = [NOM_DEFINITIF.match(n) for n in _definitifs(self.root)]
        self.assertEqual([(10**18 + k, op) for k, op in enumerate(enfiles)],
                         [(int(m.group(1)), m.group(2)) for m in noms])
        self.assertEqual(enfiles, _drainer(self.root))

    def test_W6b_la_cle_d_ordre_ne_vient_jamais_du_frere_record_id(self) -> None:
        """PIÈGE § 2 (d) : une copie de `tasks*.py` SANS `record_id.py` enfile encore à `start` et `done` — la clé
        d'ordre ne vient jamais de `record_id.mint`. ROUGE sur la BASE : aucun fichier. Mutant : M-mint."""
        tid = _nouvelle(self.root, "sans-frere")
        _drainer(self.root)
        copie = self.base / "kit" / ".agents" / "bin"
        copie.mkdir(parents=True)
        for partie in TASKS_PATH.parent.glob("tasks*.py"):
            shutil.copy2(partie, copie / partie.name)
        self.assertFalse((copie / "record_id.py").exists())
        for verbe in (["start", tid], ["done", tid, "--raison", "banc O2"]):
            p = subprocess.run([sys.executable, str(copie / "tasks.py"), "--root", str(self.root), *verbe],
                               capture_output=True, text=True, env=dict(os.environ))
            self.assertEqual(0, p.returncode, p.stderr[-400:])
        self.assertEqual(2, len(_definitifs(self.root)))

    # -- W7 : TASKS.json hérité ------------------------------------------------------------------------------------
    def _herite(self, n: int) -> list[str]:
        """Un TASKS.json HÉRITÉ (écrit par un code d'avant O2) portant `n` intents EN LIGNE ; rend leurs ids."""
        data: dict[str, Any] = {"tasks": [], "sync_outbox": [], "sync_correlations": {}}
        for k in range(1, n + 1):
            tache = _tache(f"T-00{k}", f"hérité-{k}")
            data["tasks"].append(tache)
            tasks.enqueue_sync_intent(data, tache["id"], None, tache)
        _ecrire_brut(self.root, data)
        return [intent["operation_id"] for intent in data["sync_outbox"]]

    def test_W7_un_tasks_json_herite_part_en_fichiers_au_premier_save(self) -> None:
        """Un TASKS.json hérité portant 2 intents en ligne : vue = 2 ; premier `save()` ⇒ 2 fichiers dans l'ordre,
        `sync_outbox` retirée de TASKS.json, 0 doublon. ROUGE sur la BASE : pas de dossier. Mutant :
        M-hérité-ignoré (intents en ligne hors de la vue)."""
        ops = self._herite(2)
        self.assertEqual(ops, _vue(self.root))
        self.assertEqual([], _definitifs(self.root))
        tasks.save(str(self.root), tasks.load(str(self.root)))
        self.assertNotIn("sync_outbox", _brut(self.root))
        self.assertEqual(ops, [NOM_DEFINITIF.match(n).group(2) for n in _definitifs(self.root)])
        self.assertEqual(ops, _vue(self.root))

    # -- W8 : F5 -------------------------------------------------------------------------------------------------
    def test_W8_F5_resurrection_refusee_nommement(self) -> None:
        """A supprime T-2 (drainé), B la modifie (drainé) ; fusion de B dans A sous `-X theirs` et `union` : la tâche
        revient vivante avec une clé tombée. `stage` post-fusion rend ≠ 0 et nomme l'id, la cause et
        `tasks.py delete`, rien n'est écrit ; (b) `list` rend 0 ; `delete` puis `list` rendent 0. ROUGE sur la BASE :
        `stage` rend 0, stderr muet (M2u). Mutants : M-F5-off ; M-F5-load ((b) rouge)."""
        depot, ids = self.depot("w8-base", ["F5-1", "F5-2", "F5-3"])
        for strategie in ("theirs", "union"):
            with self.subTest(strategie=strategie):
                ca, cb = self.clones(depot, f"w8-{strategie}")
                tasks.delete_task(str(ca), ids[1])
                _drainer(ca)
                _commit(ca, "A supprime")
                tasks.stage_task(str(cb), ids[1], "F5-B")
                _drainer(cb)
                _commit(cb, "B modifie")
                self.assertEqual(0, self.fusionner(ca, cb, strategie))
                self.assertIn(ids[1], [t["id"] for t in _brut(ca)["tasks"]], "la fusion doit ressusciter T-2")
                octets = (ca / TASKS_REL).read_bytes()
                rc, _out, err = self.main(ca, "stage", ids[1], "post-fusion")
                self.assertNotEqual(0, rc, err)
                for attendu in (ids[1], "tasks.py delete", "nothing was written"):
                    self.assertIn(attendu, err)
                self.assertEqual(octets, (ca / TASKS_REL).read_bytes())
                self.assertEqual(0, self.main(ca, "list")[0])
                rc, _out, err = self.main(ca, "delete", ids[1])
                self.assertEqual(0, rc, err)
                self.assertEqual(0, self.main(ca, "list")[0])

    def test_W8c_deux_ulid_distincts_ne_sont_jamais_une_resurrection(self) -> None:
        """(c) A supprime T-X, B crée T-Y (deux `T-<ULID>` frappés à quelques ms, même préfixe) : la fusion `theirs`
        passe sans refus. T-X est au MILIEU de la base et toutes les clés sont placées (uuid4 forcé), pour que la
        suppression de A et la création de B tombent dans des blocs DISJOINTS — sinon `theirs` ressuscite T-X pour
        de bon et le refus est juste (mesuré à la première rédaction). VERT attendu sur la BASE comme après (aucun
        refus n'existe) ; il tue M-F5-préfixe (comparaison sur un préfixe d'id)."""
        depot, ids = self.depot("w8c-base", ["W", "X", "Z"],
                                [_uuid("11111111", 1), _uuid("22222222", 2), _uuid("33333333", 3)])
        ca, cb = self.clones(depot, "w8c")
        with mock.patch.object(tasks.uuid, "uuid4", return_value=_uuid("00000000", 4)):
            tasks.delete_task(str(ca), ids[1])
        _drainer(ca)
        _commit(ca, "A supprime T-X")
        with mock.patch.object(tasks.uuid, "uuid4", return_value=_uuid("ffffffff", 5)):
            ty = _nouvelle(cb, "Y")
        _drainer(cb)
        _commit(cb, "B crée T-Y")
        self.assertEqual(ids[1][:8], ty[:8], "deux ULID frappés à la suite partagent leur préfixe")
        self.assertEqual(0, self.fusionner(ca, cb, "theirs"))
        self.assertEqual([ids[0], ids[2], ty], [t["id"] for t in _brut(ca)["tasks"]], "T-X reste supprimée")
        rc, _out, err = self.main(ca, "stage", ty, "post-fusion")
        self.assertEqual(0, rc, err)

    def test_W8_C2_un_stash_sans_u_detache_l_intent_et_le_refus_nomme_stash_pop(self) -> None:
        """C2 : `delete` non drainé (intent en fichier NON SUIVI), puis `git stash` SANS -u : TASKS.json revient, la
        tâche est vivante, le fichier d'intent reste ⇒ orphelin ré-indexé, vivant ∧ tombé. Le refus nomme
        `git stash pop` AVANT `tasks.py delete` ; le drain d'avant le verbe est SUSPENDU (un drain refusé au `save`
        rendrait tout verbe, `delete` compris, rc 2) ; après `git stash pop`, `list` et le verbe suivant rendent 0
        et la suppression est livrée. ROUGE sur la BASE : l'intent part avec TASKS.json, `stage` rend 0."""
        depot, ids = self.depot("w8-stash", ["S-1", "S-2"])
        tasks.delete_task(str(depot), ids[0])
        (op,) = _vue(depot)
        _git(depot, "stash", "-q")
        self.assertIn(ids[0], [t["id"] for t in _brut(depot)["tasks"]])
        rc, _out, err = self.main(depot, "stage", ids[0], "après-stash")
        self.assertEqual(2, rc, err)
        for attendu in (ids[0], "git stash pop", "tasks.py delete", "nothing was written"):
            self.assertIn(attendu, err)
        self.assertLess(err.index("git stash pop"), err.index("tasks.py delete"))
        self.assertEqual([], self.livres, "rien n'est livré tant que le board porte une tâche tombée vivante")
        _git(depot, "stash", "pop", "-q")
        self.assertEqual(0, self.main(depot, "list")[0])
        rc, _out, err = self.main(depot, "stage", ids[1], "ensuite")
        self.assertEqual(0, rc, err)
        self.assertIn(op, self.livres)

    def test_W8_C2b_le_remede_delete_passe_sur_un_board_ressuscite_dont_la_vue_n_est_pas_vide(self) -> None:
        """Dérive 2 tranchée (S-01M4KHGGH0BTZF3M0YQ9A9KKAE) : même board qu'en C2 (vue NON vide : l'intent orphelin de
        la suppression), le remède `tasks.py delete <id>` — sans `git stash pop` — rend 0. Le drain d'avant le verbe
        est SUSPENDU (UNE ligne, rien livré) au lieu d'être refusé au `save` de son `claim`, qui rendrait rc 2 au
        remède lui-même ; le drain d'après livre les deux suppressions. ROUGE sur la BASE : `delete` passe mais sans
        suspension, la ligne manque. Mutant : M-suspension (garde du drain retirée ⇒ `delete` rc 2)."""
        depot, ids = self.depot("w8-stash-delete", ["S-1", "S-2"])
        tasks.delete_task(str(depot), ids[0])
        (orphelin,) = _vue(depot)
        _git(depot, "stash", "-q")
        rc, _out, err = self.main(depot, "delete", ids[0])
        self.assertEqual(0, rc, err)
        self.assertEqual(1, len([ligne for ligne in err.splitlines() if "drain SUSPENDU" in ligne]), err)
        self.assertNotIn(ids[0], [t["id"] for t in _brut(depot)["tasks"]])
        self.assertIn(orphelin, self.livres)
        self.assertEqual(2, len(self.livres), "les deux suppressions livrées au drain d'après le verbe")

    def test_W8d_deux_ids_ressuscites_chaque_delete_passe_et_new_reste_refuse(self) -> None:
        """Clôture (critic-opus T1) : DEUX tâches vivantes sous une clé tombée (deux `delete` non drainés puis
        `git stash` sans -u, ou une fusion `theirs` qui croise deux suppressions). `stage` et `new` sont refusés, le
        message nomme UN `tasks.py delete` PAR id puis `tasks.py new` (garder un contenu : `delete` D'ABORD) ;
        `delete A` puis `delete B` rendent 0 : un save qui RETIRE une résurrection passe (sous-ensemble STRICT de
        celles vues au `load`). ROUGE sur la BASE : `delete A` refusé à cause de B, `delete B` à cause de A — board
        gelé, remède compris. Mutants : M-gel (refus sur l'ensemble courant seul), M-non-strict (`<=` : `stage`
        passe)."""
        a, b = "T-001", "T-002"
        _ecrire_brut(self.root, {
            "tasks": [_tache(a, "ressuscitée A"), _tache(b, "ressuscitée B"), _tache("T-003", "vivante")],
            "sync_correlations": {str(_uuid("0000000a", 1)): {"board_task_id": a, "tombstoned": True},
                                  str(_uuid("0000000b", 2)): {"board_task_id": b, "tombstoned": True}}})
        octets = (self.root / TASKS_REL).read_bytes()
        for verbe in (["stage", a, "refusé"], ["delete", "T-003"], ["new", "garder le contenu de A"]):
            rc, _out, err = self.main(self.root, *verbe)
            self.assertEqual(2, rc, (verbe, err))
            self.assertEqual(octets, (self.root / TASKS_REL).read_bytes(), verbe)
        for attendu in (f"`tasks.py delete {a}`", f"`tasks.py delete {b}`", "nothing was written"):
            self.assertIn(attendu, err)
        self.assertLess(err.rindex("tasks.py delete"), err.index("tasks.py new"), "delete D'ABORD, new ENSUITE")
        for tid, reste in ((a, [b, "T-003"]), (b, ["T-003"])):
            rc, _out, err = self.main(self.root, "delete", tid)
            self.assertEqual(0, rc, (tid, err))
            self.assertEqual(reste, [t["id"] for t in _brut(self.root)["tasks"]])
        rc, _out, err = self.main(self.root, "new", "garder le contenu de A")
        self.assertEqual(0, rc, err)

    def test_W8e_deux_delete_non_draines_puis_stash_sans_u_chaque_delete_passe(self) -> None:
        """Le cas réel de T1 : deux `delete` non drainés puis `git stash` SANS -u — les deux clés tombées ne vivent
        QUE dans les fichiers d'intent (orphelins ré-indexés au `load`). `delete A` puis `delete B` rendent 0. Tue
        M-avant-vue (ensemble du `load` pris AVANT la ré-indexation : vide, donc `delete A` refusé à cause de B)."""
        depot, ids = self.depot("w8e-stash", ["E-1", "E-2", "E-3"])
        for tid in ids[:2]:
            tasks.delete_task(str(depot), tid)
        _git(depot, "stash", "-q")
        self.assertEqual(ids, [t["id"] for t in _brut(depot)["tasks"]])
        for tid, reste in ((ids[0], ids[1:]), (ids[1], ids[2:])):
            rc, _out, err = self.main(depot, "delete", tid)
            self.assertEqual(0, rc, (tid, err))
            self.assertEqual(reste, [t["id"] for t in _brut(depot)["tasks"]])

    # -- W9 : clé de suppression gardée ----------------------------------------------------------------------------
    def test_W9_une_suppression_sans_correlation_garde_sa_cle(self) -> None:
        """`delete` d'une tâche SANS corrélation (comme les 115 du board réel), puis drain : sa clé reste,
        `tombstoned=True` (F5L). ROUGE sur la BASE : l'ACK l'élague (tasks_sync.py `ack_sync_event`). Mutant :
        M-ack (condition d'élagage rétablie)."""
        _ecrire_brut(self.root, {"tasks": [_tache("T-001", "legacy")], "sync_correlations": {}})
        tasks.delete_task(str(self.root), "T-001")
        (op,) = _vue(self.root)
        self.assertEqual([op], _drainer(self.root))
        self.assertEqual({"board_task_id": "T-001", "tombstoned": True},
                         _brut(self.root)["sync_correlations"].get(op))

    def test_W9b_F5L_a_N_500_est_detecte(self) -> None:
        """F5L à N = 500 : une tâche legacy SANS clé, supprimée par A, modifiée par B, fusion `theirs`. Les deux
        clés neuves sont FORCÉES aux deux bouts des 500 clés de la base (M7 : à N = 500 la perte est rare mais
        aléatoire ; ici elle est exclue par construction, le témoin ne peut pas battre) : la clé de suppression de A
        survit, la résurrection est REFUSÉE au `save()`. ROUGE sur la BASE : l'ACK de A élague sa clé, rien ne
        détecte. Mutant : M-ack."""
        depot = self.base / "w9b-base"
        (depot / BOARD_REL).mkdir(parents=True)
        _git(depot, "-c", "init.defaultBranch=main", "init", "-q")
        _identite(depot)
        data: dict[str, Any] = {"tasks": [], "sync_correlations": {}}
        for k in range(1, 501):
            data["tasks"].append(_tache(f"T-{k:08d}", f"n-{k}"))
            data["sync_correlations"][str(_uuid(f"{0x10000000 + k * 0x7ffff:08x}", k))] = {
                "board_task_id": f"T-{k:08d}", "tombstoned": False}
        legacy = "T-00000501"
        data["tasks"].append(_tache(legacy, "legacy sans clé"))
        _ecrire_brut(depot, data)
        _commit(depot, "base 500")
        ca, cb = self.clones(depot, "w9b")
        with mock.patch.object(tasks.uuid, "uuid4", return_value=_uuid("00000000", 1)):
            tasks.delete_task(str(ca), legacy)
        _drainer(ca)
        _commit(ca, "A supprime")
        with mock.patch.object(tasks.uuid, "uuid4", return_value=_uuid("ffffffff", 2)):
            tasks.stage_task(str(cb), legacy, "F5L-B")
        _drainer(cb)
        _commit(cb, "B modifie")
        self.assertEqual(0, self.fusionner(ca, cb, "theirs"))
        self.assertIn(legacy, [t["id"] for t in _brut(ca)["tasks"]])
        with self.assertRaises(tasks.BoardError) as refus:
            tasks.stage_task(str(ca), legacy, "post-fusion")
        self.assertIn(legacy, str(refus.exception))

    # -- W10 : domiciles -------------------------------------------------------------------------------------------
    def test_W10_definitifs_suivis_lots_et_quarantaine_ignores(self) -> None:
        """Les fichiers que le code POSE : un définitif n'est PAS ignoré par git (il voyage avec TASKS.json), un lot
        et une quarantaine le sont (`.agents/state/local/`, S-00003918). ROUGE sur la BASE : aucun de ces fichiers
        n'existe. Mutant : M-domicile (lots sous le dossier suivi)."""
        tid = _nouvelle(self.root, "w10")
        (definitif,) = _definitifs(self.root)
        lot, _op = self._lot_avant_replace(tid, "w10")
        with mock.patch("sys.stderr", io.StringIO()):
            tasks.stage_task(str(self.root), tid, "w10")
        (quarantaine,) = _quarantaine(self.root)

        def ignore(rel: Path) -> bool:
            return _git(REPO, "check-ignore", "-q", "--no-index", rel.as_posix(), check=False).returncode == 0

        self.assertFalse(ignore(DOSSIER_REL / definitif))
        self.assertTrue(ignore(LOTS_REL / lot))
        self.assertTrue(ignore(QUARANTAINE_REL / quarantaine))

    # -- W11 : réinjection en tête ---------------------------------------------------------------------------------
    def test_W11_D2_k2_reinjectes_en_tete_cles_min_moins_2_et_min_moins_1(self) -> None:
        """Deux intents déversés puis réinjectés EN TÊTE (`_reinjecter_deverses`) prennent les clés `min−2`, `min−1`
        dans leur ordre ; après le `save()`, l'ordre trié du dossier EST l'ordre de la liste (S-00003917 (3)). ROUGE
        sur la BASE : aucun fichier. Mutant : M-ordre-tête (réinjection en queue)."""
        ops = []
        for k in range(3):
            vus = set(_vue(self.root))
            _nouvelle(self.root, f"d2-{k}")
            ops += sorted(set(_vue(self.root)) - vus)
        with mock.patch.object(tasks, "_SYNC_OUTBOX_SEUIL", 1), mock.patch("sys.stderr", io.StringIO()):
            self.assertIsNotNone(tasks._deverser_excedent(str(self.root)))
            self.assertEqual(ops[2:], _vue(self.root))
            minimum = _cle(self.root, ops[2])
            self.assertEqual(2, tasks._reinjecter_deverses(str(self.root)))
        self.assertEqual([(minimum - 2, ops[0]), (minimum - 1, ops[1]), (minimum, ops[2])],
                         [(int(m.group(1)), m.group(2)) for m in map(NOM_DEFINITIF.match, _definitifs(self.root))])
        self.assertEqual(ops, _vue(self.root))

    # -- W12 : commit des magasins ---------------------------------------------------------------------------------
    def test_W12_le_commit_des_magasins_emporte_l_ajout_et_le_retrait_des_intents(self) -> None:
        """`post-task-done-index.sh --commit-section` sur un dépôt jetable : (a) intent en attente ⇒ commité avec
        TASKS.json ; (b) intent acquitté ⇒ son retrait est commité ; (c) aucun intent ⇒ `committed` pour TASKS.json
        seul. ROUGE sur la BASE : (a) le dossier reste vide au commit. Mutants : M-trois-chemins (pathspec absent,
        (a)(b) rouges) ; M-inconditionnel (pathspec ajouté sans fichier ⇒ (c) `failed`, M8)."""
        depot, (tid,) = self.depot("w12", ["W12"])
        env = {k: v for k, v in os.environ.items() if not k.startswith(("_CADRE_GIT", "GIT_DIR", "GIT_WORK_TREE"))}

        def section() -> str:
            p = subprocess.run(["bash", str(HOOK), "--commit-section", str(depot)], capture_output=True, text=True,
                               env=env)
            return p.stdout.strip().splitlines()[-1] if p.stdout.strip() else f"rc={p.returncode} {p.stderr[-200:]}"

        def suivis() -> list[str]:
            return _git(depot, "ls-files", "--", DOSSIER_REL.as_posix()).stdout.split()

        def propre() -> str:
            return _git(depot, "status", "--porcelain", "--untracked-files=all", "--", BOARD_REL.as_posix()).stdout

        with self.subTest("a : intent en attente"):
            tasks.stage_task(str(depot), tid, "w12a")
            self.assertEqual("committed", section())
            self.assertEqual([(DOSSIER_REL / n).as_posix() for n in _definitifs(depot)], suivis())
            self.assertEqual(1, len(suivis()))
            self.assertEqual("", propre())
        with self.subTest("b : intent acquitté"):
            self.assertEqual(1, len(_drainer(depot)))
            self.assertEqual("committed", section())
            self.assertEqual([], suivis())
            self.assertEqual("", propre())
        with self.subTest("c : aucun intent"):
            data = tasks.load(str(depot))
            data["tasks"][0]["stage"] = "sans intent"
            tasks.save(str(depot), data)
            self.assertEqual([], _definitifs(depot))
            self.assertEqual("committed", section())
            self.assertEqual([TASKS_REL.as_posix()],
                             _git(depot, "show", "--name-only", "--format=", "HEAD").stdout.split())

    # -- W13 : suppressions en vol ---------------------------------------------------------------------------------
    def test_W13_suppressions_en_vol_lit_le_dossier_et_ferme_sur_l_illisible(self) -> None:
        """`suppressions_en_vol(data_brut, root)` (T-1060), sur un TASKS.json BRUT sans `sync_outbox` : une
        suppression en définitif seul ⇒ id rendu ; orphelin (clé absente) ⇒ rendu ; lot NON validé portant une
        suppression ⇒ rendu ; définitif illisible ⇒ LÈVE (la commande V3 est relâchée). ROUGE sur la BASE : le
        dossier n'est pas lu. Mutants : M-vol-brut (lecture de `data` seule), M-vol-filtré (filtre sur
        `sync_correlations`), M-vol-tolérant (illisible ignoré)."""
        tid = _nouvelle(self.root, "w13")
        _drainer(self.root)
        tasks.delete_task(str(self.root), tid)
        (op,) = _vue(self.root)

        def brut() -> dict[str, Any]:
            data = _brut(self.root)
            data.pop("sync_outbox", None)
            return data

        with self.subTest("définitif seul"):
            self.assertIn(tid, tasks.suppressions_en_vol(brut(), str(self.root)))
        with self.subTest("lot non validé"):
            autre = _nouvelle(self.root, "w13-lot")
            p = _crash(self.root, CRASH_AVANT_REPLACE, f"m.delete_task(racine, {autre!r})")
            self.assertEqual(1, len(_lots(self.root)), p.stderr[-300:])
            self.assertIn(autre, tasks.suppressions_en_vol(brut(), str(self.root)))
        with self.subTest("orphelin"):
            data = _brut(self.root)
            data["sync_correlations"].pop(op, None)
            _ecrire_brut(self.root, data)
            self.assertIn(tid, tasks.suppressions_en_vol(brut(), str(self.root)))
        with self.subTest("définitif illisible"):
            (self.root / DOSSIER_REL).mkdir(parents=True, exist_ok=True)
            (self.root / DOSSIER_REL / f"{1:020d}-illisible.json").write_text("{", encoding="utf-8")
            with self.assertRaises(tasks.BoardError):
                tasks.suppressions_en_vol(brut(), str(self.root))

    # -- W15 : invariants que les témoins à UN élément laissaient muets (exec-critic, sondes P-a…P-d) ----------------
    def test_W15a_lot_de_reinjection_en_tete_vu_a_son_rang_et_livre_FIFO(self) -> None:
        """Deux intents déversés réinjectés EN TÊTE (clés min−2, min−1, sous un définitif existant), crash DUR après le
        `replace` : le lot validé est vu À SON RANG — la vue est [0, 1, 2] — et le drain livre [0, 1, 2]. Tue M09
        (lots validés ajoutés en QUEUE : la vue serait [2, 0, 1])."""
        ops = []
        for k in range(3):
            vus = set(_vue(self.root))
            _nouvelle(self.root, f"pa-{k}")
            ops += sorted(set(_vue(self.root)) - vus)
        with mock.patch.object(tasks, "_SYNC_OUTBOX_SEUIL", 1), mock.patch("sys.stderr", io.StringIO()):
            self.assertIsNotNone(tasks._deverser_excedent(str(self.root)))
        self.assertEqual(ops[2:], _vue(self.root))
        p = _crash(self.root, CRASH_AVANT_ECLATEMENT, "m._reinjecter_deverses(racine)")
        self.assertEqual(CRASH, p.returncode, p.stderr[-300:])
        self.assertEqual(1, len(_lots(self.root)))
        self.assertEqual(ops, _vue(self.root), "lot de tête vu à son rang")
        with mock.patch("sys.stderr", io.StringIO()):
            self.assertEqual(ops, _drainer(self.root))

    def test_W15b_lot_valide_par_ses_correlations_quand_un_tiers_reecrit_TASKS_json(self) -> None:
        """Crash DUR après le `replace`, puis TASKS.json réécrit par un tiers (mêmes données, autres octets) : la cible
        du lot ne correspond plus, mais ses `operation_id` sont dans `sync_correlations` (même `replace`) — le lot
        reste VALIDÉ, le save l'éclate, la quarantaine reste vide. Tue M10 (critère C3 positif retiré : le lot
        partirait en quarantaine, un intent publié jamais livré)."""
        tid = _nouvelle(self.root, "pb")
        _drainer(self.root)
        p = _crash(self.root, CRASH_AVANT_ECLATEMENT, f"m.stage_task(racine, {tid!r}, 'pb')")
        self.assertEqual(CRASH, p.returncode, p.stderr[-300:])
        (lot,) = _lots(self.root)
        (op,) = _ops_du_lot(self.root, lot)
        (self.root / TASKS_REL).write_text(json.dumps(_brut(self.root)) + "\n", encoding="utf-8")
        self.assertEqual([op], _vue(self.root))
        with mock.patch("sys.stderr", io.StringIO()):
            tasks.save(str(self.root), tasks.load(str(self.root)))
        self.assertEqual([], _quarantaine(self.root))
        self.assertEqual([op], [NOM_DEFINITIF.match(n).group(2) for n in _definitifs(self.root)])

    def test_W15c_resurrection_avec_deverse_seul_delete_passe_et_replay_sync_rend_1(self) -> None:
        """Résurrection (fusion `theirs`) alors que la vue est VIDE et que le seul intent en attente est DÉVERSÉ :
        `replay-sync` rend 1 (drain SUSPENDU, `echec` posé), le remède `delete` rend 0. Tue M06 (suspension sans la
        branche « déversement seul » : le drain réinjecte, son `save` est refusé, `delete` rc 2) et M07 (suspension
        sans `echec` : `replay-sync` rendrait 0)."""
        depot, ids = self.depot("w15c-base", ["C-1", "C-2", "C-3"])
        ca, cb = self.clones(depot, "w15c")
        tasks.delete_task(str(ca), ids[1])
        _drainer(ca)
        _commit(ca, "A supprime")
        tasks.stage_task(str(cb), ids[1], "B")
        _drainer(cb)
        _commit(cb, "B modifie")
        tasks.stage_task(str(ca), ids[0], "A en attente")
        with mock.patch.object(tasks, "_SYNC_OUTBOX_SEUIL", 0), mock.patch("sys.stderr", io.StringIO()):
            self.assertIsNotNone(tasks._deverser_excedent(str(ca)))
        self.assertTrue(tasks._chemin_deverse(str(ca)).exists())
        self.assertEqual([], _vue(ca))
        _commit(ca, "A déverse")
        self.assertEqual(0, self.fusionner(ca, cb, "theirs"))
        self.assertIsNotNone(tasks.resurrection_refusal(tasks.load(str(ca))))
        rc, _out, err = self.main(ca, "replay-sync")
        self.assertEqual(1, rc, err)
        self.assertEqual(1, len([ligne for ligne in err.splitlines() if "drain SUSPENDU" in ligne]), err)
        rc, _out, err = self.main(ca, "delete", ids[1])
        self.assertEqual(0, rc, err)

    def test_W15d_save_d_un_dict_neuf_ne_retire_aucun_fichier(self) -> None:
        """`save()` d'un dict NEUF (aucune `vue_o2`) portant deux intents en fichiers hors de sa liste : les deux
        fichiers RESTENT — jamais « dossier − liste ». Tue M14 (retrait sans le critère `op in vus`)."""
        for k in range(2):
            _nouvelle(self.root, f"pd-{k}")
        avant = _definitifs(self.root)
        self.assertEqual(2, len(avant))
        data = tasks.load(str(self.root))
        tasks.save(str(self.root), {"tasks": data["tasks"], "sync_correlations": dict(data["sync_correlations"])})
        self.assertEqual(avant, _definitifs(self.root))

    def test_W16_la_vue_ecarte_nom_menteur_correlation_hors_forme_et_lot_a_entree_invalide(self) -> None:
        """Trois contrôles du lecteur TOLÉRANT, chacun sans témoin jusqu'ici : (a) un définitif dont le NOM annonce un
        autre `operation_id` (M02), (b) une enveloppe dont la corrélation n'a pas `tombstoned` (M03), (c) un lot
        VALIDÉ dont une entrée porte un intent hors forme (M04) — chacun hors de la vue, sans levée."""
        _nouvelle(self.root, "w16")
        (nom,) = _definitifs(self.root)
        chemin = self.root / DOSSIER_REL / nom
        with self.subTest("a : nom menteur"):
            menteur = chemin.with_name(f"{nom[:20]}-autre-operation.json")
            chemin.rename(menteur)
            try:
                self.assertEqual([], _vue(self.root))
            finally:
                menteur.rename(chemin)
        with self.subTest("b : corrélation hors forme"):
            octets = chemin.read_bytes()
            enveloppe = json.loads(octets)
            del enveloppe["correlation"]["tombstoned"]
            chemin.write_text(json.dumps(enveloppe, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            try:
                self.assertEqual([], _vue(self.root))
            finally:
                chemin.write_bytes(octets)
        with self.subTest("c : lot à entrée invalide"):
            tid = tasks.load(str(self.root))["tasks"][0]["id"]
            _drainer(self.root)
            p = _crash(self.root, CRASH_AVANT_ECLATEMENT, f"m.stage_task(racine, {tid!r}, 'w16')")
            (lot,) = _lots(self.root) or [None]
            self.assertIsNotNone(lot, p.stderr[-300:])
            self.assertEqual(1, len(_vue(self.root)))
            contenu = json.loads((self.root / LOTS_REL / lot).read_text(encoding="utf-8"))
            contenu["intents"][0]["enveloppe"]["intent"]["lease"] = {"owner": "x", "token": "t", "expires_at": "x"}
            (self.root / LOTS_REL / lot).write_text(json.dumps(contenu, sort_keys=True) + "\n", encoding="utf-8")
            self.assertEqual([], _vue(self.root))

    # -- W14 : plafond de taille à la lecture (sécurité, advisory de clôture) -------------------------------------
    def test_W14_un_definitif_ou_un_lot_au_dela_du_plafond_n_est_pas_lu(self) -> None:
        """Un fichier d'intent au-delà de `_PLAFOND_INTENT_OCTETS` (il arrive par `git pull` d'un autre clone), ou un
        lot au-delà de `_PLAFOND_LOT_OCTETS`, n'est lu qu'à plafond + 1 octets : refus NOMMÉ, hors de la vue, jamais
        une levée au `load`. Le plafond RÉEL laisse passer l'intent d'une tâche de 30 000 caractères (la plus grosse
        du board réel : 29 634 octets). ROUGE avant : aucun plafond (constantes absentes). Mutants : M-sans-plafond,
        M-plafond-bas (1 Kio : la grosse tâche sort de la vue)."""
        tid = _nouvelle(self.root, "x" * 30000)
        (nom,) = _definitifs(self.root)
        taille = (self.root / DOSSIER_REL / nom).stat().st_size
        self.assertEqual(1, len(_vue(self.root)), "le plafond réel tient la plus grosse tâche")
        with mock.patch.object(tasks, "_PLAFOND_INTENT_OCTETS", taille - 1):
            self.assertEqual([], _vue(self.root))
            (lu,) = tasks._lire_definitifs(str(self.root))
            self.assertIn(f"above the {taille - 1}-byte cap", lu[4])
        _drainer(self.root)
        p = _crash(self.root, CRASH_AVANT_ECLATEMENT, f"m.stage_task(racine, {tid!r}, 'lot')")
        (lot,) = _lots(self.root) or [None]
        self.assertIsNotNone(lot, p.stderr[-300:])
        self.assertEqual(1, len(_vue(self.root)), "lot validé : vu à son rang")
        with mock.patch.object(tasks, "_PLAFOND_LOT_OCTETS", (self.root / LOTS_REL / lot).stat().st_size - 1):
            self.assertEqual([], _vue(self.root))

    # -- C1 : bail vu d'un autre processus -------------------------------------------------------------------------
    def test_C1_le_bail_pose_par_claim_est_vu_d_un_autre_processus(self) -> None:
        """C1 : un intent MODIFIÉ (bail posé par `claim`) est réécrit dans SON fichier : un autre processus le lit par
        `load()`. ROUGE sur la BASE : le bail est dans TASKS.json, aucun fichier. Mutant : M-bail-mémoire (intent
        modifié jamais réécrit)."""
        _nouvelle(self.root, "c1")
        p = _crash(self.root, "", "print(json.dumps(m.claim_sync_event(racine, 'autre-processus')['lease']))")
        self.assertEqual(0, p.returncode, p.stderr[-300:])
        bail = json.loads(p.stdout)
        (nom,) = _definitifs(self.root) or [None]
        self.assertIsNotNone(nom, "un fichier définitif attendu")
        self.assertEqual(bail, json.loads((self.root / DOSSIER_REL / nom).read_text(encoding="utf-8"))["intent"]["lease"])
        self.assertEqual(bail, tasks.load(str(self.root))["sync_outbox"][0]["lease"])

    # -- S-00003917 (5) : lecture seule ------------------------------------------------------------------------------
    def test_list_et_epic_list_n_appellent_jamais_save(self) -> None:
        """S-00003917 (5) : `list` et `epic-list` (et `list --json`) n'appellent JAMAIS `save()` — l'orphelin et la
        quarantaine attendent un verbe d'écriture. VERT avant comme après (garde-fou)."""
        _nouvelle(self.root, "lecture")

        def interdit(*_a: Any, **_k: Any) -> None:
            raise AssertionError("save() appelé par un verbe de lecture")

        with mock.patch.object(tasks, "save", interdit):
            for verbe in (["list"], ["list", "--json"], ["epic-list"]):
                rc, _out, err = self.main(self.root, *verbe)
                self.assertEqual(0, rc, (verbe, err))


if __name__ == "__main__":
    unittest.main()
