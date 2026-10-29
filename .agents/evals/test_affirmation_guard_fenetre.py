"""Banc de la FENÊTRE de `affirmation-guard.sh` — recul d'un cran (T-00000602, 22/09).

POURQUOI CE FICHIER EXISTE. La garde `Stop` refuse une fin de tour quand ce
cycle a écrit sur une surface durable sans que `BINOME_MIN` critique(s) distinct(s)
(UN depuis S-00004500) ait tourné. Sa fenêtre était « depuis la DERNIÈRE porte verte » — et c'était FAUX
sur un cycle CONFORME : la doctrine impose l'ordre travail → binôme → correction
→ porte → `done`, donc le binôme tourne TOUJOURS avant la porte (relevé du
2026-09-22 : traces à 18:19:03 et 18:24:42, tampon de porte à 18:28:36). La
fenêtre était donc VIDE PAR CONSTRUCTION juste après chaque porte, et la sortie
tracée devenait le régime nominal — elle a servi DEUX fois dans la même journée.
La décision pilote du 22/09 (option A) recule la fenêtre des CRITIQUES d'un cran
(avant-dernier vert) et LAISSE l'ancrage du DIFF sur le DERNIER vert : les deux
bornes ne viennent plus du même verdict, délibérément.

DÉCISION PILOTE DU 23/09 (S-00001884), DEUX VOLETS, CHACUN AVEC SES TÉMOINS ICI.
  D1 = A — la fenêtre est ALIGNÉE sur sa jumelle `tasks.py::cycle_precedent` :
      même lecture (le JOURNAL seul), mêmes filtres (`mode=frozen`, `at` connu,
      un même sha consécutif = UN cycle), et moins de DEUX cycles = PAS de borne,
      jamais « ce vert-là ». Classe `FenetreTests`. Sur cette absence de borne
      la garde retombe sur 12 h, et `done` borne l'EMPRUNT à 24 h depuis
      T-00000846 (avant : aucune fenêtre) — deux fenêtres différentes :
      DIVERGENCE CONNUE ET ASSUMÉE (décision pilote par défaut du 23/09),
      épinglée comme telle par `PariteJumellesTests`.
  BORNE ASSUMÉE (décision pilote par défaut du 23/09, critic-opus T2) — le
      binôme du cycle k couvre les écritures du cycle k+1, tâches AJOUTÉES au
      board comprises : `FenetreTests.test_8_…` l'épingle.
  D2 = B — une garde ARMÉE qui ne peut pas lire sa propre infrastructure
      (tampon, journal, traces) REFUSE en nommant le fichier et le remède ; elle
      ne se tait plus. Classe `InfraIllisibleTests`.

CE QU'IL EXERCE, ET PAR QUEL CANAL. En SOUS-PROCESSUS, `CLAUDE_PROJECT_DIR`
pointé sur un dépôt FABRIQUÉ sous `tempfile`, charge JSON sur stdin. On n'importe
JAMAIS le python embarqué dans le `.sh` : ce serait tester autre chose que ce que
l'hôte exécute. Rien n'est lu ni écrit dans le dépôt courant — tout est fabriqué.

LES SURFACES DU CONTRAT, fabriquées à chaque cas (« ce dont la garde a besoin
pour ne pas se taire ») :
  - `.agents/state/gates/AFFIRMATION_REQUIRED` — l'ARMEMENT. Absent → 0 octet.
  - `.agents/state/local/VERIFY_STAMP` (courant) et `VERIFY_STAMP.log` (journal
    append-only), TOUS DEUX git-ignorés. `porte()` les écrit ENSEMBLE, comme
    `core-scripts/verify.sh::stamp_write` : un tampon courant ABSENT du journal
    est un état que la production ne fabrique pas, et trois témoins de la
    version précédente de ce banc en dépendaient sans le dire. La borne de temps
    vient de l'avant-dernier CYCLE du journal, l'ancrage du diff du `sha` du
    dernier vert frozen.
  - `.agents/state/local/binome/<tâche>.<def>.json`, contenu `{"at": …}` — la
    trace d'un critique qui a tourné.
  - une surface DURABLE modifiée dans l'arbre : `AGENTS.md` (∈ SURFACES_DOCTRINE).

LE VOCABULAIRE DES TRACES EST CLOS, et repris VERBATIM du hook
(`.claude/hooks/affirmation-guard.sh`, `critiques_depuis`) : seuls `critic-opus`,
`critic-fable` et `critic-sonnet-max` comptent. Un banc qui inventerait un nom de
critique testerait un chemin mort.

LE CANAL DE REFUS EST MESURÉ, PAS SUPPOSÉ : sur `Stop`, le refus est
`{"decision":"block"}` sur STDOUT avec exit 0 — jamais un `exit 2`. Le PASS est
un stdout VIDE, exit 0. Les deux assertions vérifient le code de sortie.

UN PASS N'EST UN TÉMOIN QUE S'IL A SON CONTRÔLE ARMÉ (constat du binôme, 22/09).
Chaque test qui asserte un PASS sur un état « refusable » établit D'ABORD, sur le
MÊME état, que la garde armée le REFUSE : sans ce contrôle, une garde qui ne
refuserait plus rien laisserait ces témoins verts.

PASSE DE CORRECTION exec-critic (T-00000695/696) — ce qu'elle ajoute ici :
  · `PariteJumellesTests` : le MÊME journal lu par `tasks.py::cycle_precedent`
    (importé) et par la garde (sous-processus), même borne exigée — rien ne
    reliait les deux jumelles, et la mutation « dernière borne » restait verte
    des deux côtés ;
  · la sortie ponctuelle NON HONORÉE quand elle ne peut pas être journalisée
    ou retirée, sur les deux chemins (ordinaire et panne D2) ;
  · le coût D2 épinglé sur arbre PROPRE (`test_cout_D2_…`) ;
  · une surface forgée (`\\n`, `\\t`, `\\r`) ne forge plus de ligne au journal ;
  · une charge trop imbriquée reste ADVISORY sans planter.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / ".claude" / "hooks" / "affirmation-guard.sh"
TASKS_PY = ROOT / ".agents" / "bin" / "tasks.py"

#: `chmod` ne lie pas root, et n'a pas ce sens sous Windows : les témoins qui
#: rendent un fichier NON INSCRIPTIBLE par les droits s'y sautent, en le disant.
#: La variante « le journal est un RÉPERTOIRE » ne dépend pas de l'uid.
DROITS_SANS_EFFET = os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0)

#: Les variables par lesquelles git se laisse DÉSIGNER un autre dépôt que celui de
#: son `-C` — RECOPIÉES de `conftest.py::GIT_REDIRECTIONS`, et non importées : ce
#: fichier se lance aussi par `unittest.main()`, où aucun conftest n'est chargé.
#: critic-opus T1 (GRAVE), MESURÉ : lancé avec `GIT_DIR` pointé sur un dépôt hôte
#: jetable, `_Depot()` a créé un commit DANS L'HÔTE, écrasé son `HEAD:AGENTS.md`
#: et remplacé son `user.email` — et le test est sorti « OK ». Git exporte
#: `GIT_DIR` à ses hooks, et `verify.sh` est appelable depuis un hook.
#: Plus les deux INJECTIONS de configuration (`git -c` → `GIT_CONFIG_PARAMETERS`,
#: `GIT_CONFIG_COUNT` + `GIT_CONFIG_KEY_<n>`/`GIT_CONFIG_VALUE_<n>`, par préfixe) :
#: elles passent AU-DESSUS de la config locale du dépôt jetable.
GIT_REDIRECTIONS = (
    "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
    "GIT_COMMON_DIR", "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE",
    "GIT_PREFIX", "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT",
)
GIT_CONFIG_PREFIXES = ("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")


def _env(**en_plus: str) -> dict:
    """L'environnement du processus SANS `GIT_REDIRECTIONS` ni les variables
    `GIT_CONFIG_PREFIXES`, plus `en_plus` : le SEUL environnement que ce banc
    passe à un sous-processus (git ou la garde)."""
    env = {k: v for k, v in os.environ.items()
           if k not in GIT_REDIRECTIONS and not k.startswith(GIT_CONFIG_PREFIXES)}
    env.update(en_plus)
    return env


#: Le LECTEUR du journal des sorties : c'est lui qui les COMPTE et les réinjecte.
SESSION_START = ROOT / ".claude" / "hooks" / "session-start.sh"


def _sorties_comptees_par_session_start(journal: Path) -> int:
    """Le nombre de sorties franchies que `session-start.sh` annoncerait pour ce
    journal : son test `[ -s ]` puis `grep -c` sur son MOTIF EXACT, lu dans le
    fichier du lecteur — une dérive du motif fait rougir ici au lieu de laisser
    ce banc compter avec un motif périmé."""
    m = re.search(r"^\s*_SO_MOTIF='([^']+)'", SESSION_START.read_text(encoding="utf-8"),
                  re.M)
    assert m is not None, f"motif du compteur introuvable dans {SESSION_START}"
    if not journal.is_file() or journal.stat().st_size == 0:
        return 0
    r = subprocess.run(["grep", "-c", m.group(1), str(journal)],
                       capture_output=True, text=True, env=_env())
    return int(r.stdout.strip() or "0")


def _charger_tasks():
    """`tasks.py` chargé par CHEMIN, sous un nom propre à ce banc — comme
    `.agents/bin/test_tasks.py` le fait sous le sien."""
    spec = importlib.util.spec_from_file_location("tasks_parite_garde", TASKS_PY)
    assert spec is not None and spec.loader is not None, TASKS_PY
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

#: Vocabulaire CLOS des critiques, repris de `critiques_depuis` dans le hook.
#: Ré-écrit ici pour qu'un banc qui dériverait du hook rougisse plutôt que de
#: tester en silence un nom hors vocabulaire.
CRITIQUES = ("critic-opus", "critic-fable", "critic-sonnet-max")

#: Une surface durable qui VOYAGE (∈ SURFACES_DOCTRINE du hook) : la modifier
#: dans l'arbre fait mordre la garde.
SURFACE_DURABLE = "AGENTS.md"

#: Un octet qui n'ouvre AUCUNE séquence UTF-8 valide : `open(…, encoding="utf-8")`
#: lève `UnicodeDecodeError` à sa lecture. C'est l'instance mesurée de D2.
OCTET_NON_UTF8 = b"\xff"


def _iso(dt: datetime) -> str:
    """Le SEUL format que le hook parse : `%Y-%m-%dT%H:%M:%SZ`, littéral `Z`."""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


#: Les points d'INTERRUPTION de `consommer_sortie`, repris VERBATIM de la garde :
#: un `os._exit(9)` posé juste avant le temps nommé simule un kill de l'hôte
#: (le python meurt, le `exit 0` terminal du `.sh` rend un stdout VIDE — ce que
#: l'hôte reçoit d'un tour tué). Une ancre disparue fait ROUGIR le banc au lieu
#: de le laisser tester une copie qui ne s'interrompt plus.
TUER_AVANT_JOURNAL = ("    # TEMPS 2 — journaliser.\n",
                      "    os._exit(9)\n    # TEMPS 2 — journaliser.\n")
TUER_AVANT_EFFACEMENT = ("    # TEMPS 3 — effacer.\n",
                         "    os._exit(9)\n    # TEMPS 3 — effacer.\n")
#: Le journal RE-STRICT : l'écriture d'un surrogate lève `UnicodeEncodeError`,
#: une exception qui n'est PAS une `OSError` — le témoin du temps 2 seul.
JOURNAL_STRICT = ('open(JOURNAL, "a", encoding="utf-8", errors="backslashreplace")',
                  'open(JOURNAL, "a", encoding="utf-8", errors="strict")')


def _garde_variante(dossier: Path, ancre: str, remplacement: str) -> Path:
    """Une COPIE de la garde, hors du dépôt jetable, où `ancre` — présente UNE
    fois exactement, sinon le banc rougit — est remplacée. Dérivée du hook RÉEL
    à chaque appel : une mutation du hook se retrouve dans la variante."""
    texte = HOOK.read_text(encoding="utf-8")
    assert texte.count(ancre) == 1, (
        f"ancre de variante introuvable ou ambiguë dans {HOOK} : {ancre!r} "
        f"({texte.count(ancre)} occurrence(s))")
    copie = dossier / "garde-variante.sh"
    copie.write_text(texte.replace(ancre, remplacement), encoding="utf-8")
    return copie


class _Depot:
    """Un dépôt jetable, avec les seules surfaces que la garde lit.

    On ne dépend JAMAIS de l'état du dépôt courant : `VERIFY_STAMP(.log)` et les
    traces de binôme y sont git-ignorés, donc absents ou pollués — tout est
    fabriqué ici, sous `tempfile`, et détruit au `cleanup`.
    """

    def __init__(self) -> None:
        self.now = datetime.now(timezone.utc)
        self.dir = Path(tempfile.mkdtemp(prefix="affguard-banc-"))
        self._git("init", "-q")
        self._git("config", "user.email", "banc@example.invalid")
        self._git("config", "user.name", "Banc")
        self._git("config", "commit.gpgsign", "false")
        surface = self.dir / SURFACE_DURABLE
        surface.write_text("doctrine initiale\n", encoding="utf-8")
        self._git("add", SURFACE_DURABLE)
        self._git("commit", "-q", "-m", "init")
        self.head = self._git("rev-parse", "HEAD").strip()
        # La surface durable est MODIFIÉE dans l'arbre (non commitée) : `git diff`
        # depuis le tampon la voit, donc la garde a une raison de mordre.
        surface.write_text("doctrine initiale\nligne neuve du cycle\n", encoding="utf-8")
        self.armer()

    # ---- git & arborescence -------------------------------------------------
    def _git(self, *args: str) -> str:
        r = subprocess.run(
            ["git", "-C", str(self.dir), *args],
            capture_output=True, text=True, check=False, env=_env(),
        )
        return r.stdout

    def _sous(self, *parts: str) -> Path:
        p = self.dir.joinpath(*parts)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def log_path(self) -> Path:
        return self._sous(".agents", "state", "local", "VERIFY_STAMP.log")

    @property
    def stamp_path(self) -> Path:
        return self._sous(".agents", "state", "local", "VERIFY_STAMP")

    # ---- surfaces du contrat ------------------------------------------------
    def armer(self) -> None:
        self._sous(".agents", "state", "gates", "AFFIRMATION_REQUIRED").write_text(
            "banc\n", encoding="utf-8")

    def desarmer(self) -> None:
        (self.dir / ".agents/state/gates/AFFIRMATION_REQUIRED").unlink(missing_ok=True)

    def arbre_propre(self) -> None:
        """Annule la modification de la surface durable : l'arbre suivi redevient
        IDENTIQUE à HEAD — un tour de pure lecture, rien d'écrit."""
        self._git("checkout", "--", SURFACE_DURABLE)

    def arbre_suivi_est_propre(self) -> bool:
        return self._git("status", "--porcelain", "--untracked-files=no").strip() == ""

    def valider(self, fichiers: dict, en_plus: dict | None = None) -> None:
        """Écrit `fichiers` (chemin → texte, par Python), les indexe et COMMITE,
        puis met `self.head` à jour (T-00001064).

        `git add` porte `-c core.excludesFile=<os.devnull>` : sous un ignore
        PERSONNEL (`~/.config/git/ignore` qui porte `LOT-*`), un `git add` sans
        lui n'indexe RIEN — rc 0 sans pathspec, en silence (M21). D'où les deux
        ASSERTIONS : HEAD a avancé, et chaque fixture est suivie. `en_plus` :
        l'environnement du scénario (HOME et XDG jetables de R3')."""
        env = _env(**(en_plus or {}))

        def g(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run(["git", "-C", str(self.dir), *args],
                                  capture_output=True, text=True, check=False, env=env)

        avant = g("rev-parse", "HEAD").stdout.strip()
        for chemin, texte in fichiers.items():
            self._sous(*chemin.split("/")).write_text(texte, encoding="utf-8")
        g("-c", "core.excludesFile=" + os.devnull, "add", "-A", "--", *fichiers)
        g("commit", "-q", "-m", "fixtures")
        apres = g("rev-parse", "HEAD").stdout.strip()
        if not apres or apres == avant:
            raise AssertionError(
                f"valider : HEAD n'a pas avancé ({avant} → {apres}) — un ignore "
                f"personnel a-t-il écarté {sorted(fichiers)} ?")
        for chemin in fichiers:
            if g("ls-files", "--error-unmatch", "--", chemin).returncode != 0:
                raise AssertionError(f"valider : {chemin} n'est pas suivi après le commit")
        self.head = apres

    @property
    def journal_sorties(self) -> Path:
        return self._sous(".agents", "state", "local", "affirmation-sorties.log")

    @property
    def sortie_path(self) -> Path:
        return self.dir / ".agents/state/gates/AFFIRMATION_SANS_BINOME"

    def sortie_tracee(self, raison: str) -> None:
        self._sous(".agents", "state", "gates", "AFFIRMATION_SANS_BINOME").write_text(
            raison, encoding="utf-8")

    def stamp(self, mode: str, sha: str, at: datetime) -> None:
        """`VERIFY_STAMP` courant SEUL — une clé par ligne, comme `verify.sh`
        l'écrit. N'écrit PAS le journal : réservé aux cas qui éprouvent
        précisément ce découplage (`porte()` est la forme fidèle)."""
        self.stamp_path.write_text(
            f"mode={mode}\nsha={sha}\nat={_iso(at)}\n", encoding="utf-8")

    def stamp_log(self, lignes) -> None:
        """`VERIFY_STAMP.log` append-only, RÉÉCRIT en entier — champs séparés par
        TAB, du plus ANCIEN au plus RÉCENT. `lignes` = itérable de
        (mode, sha, datetime | str) ; une chaîne est écrite telle quelle dans
        `at=` (pour fabriquer `unknown`)."""
        def at(a):
            return a if isinstance(a, str) else _iso(a)
        contenu = "".join(
            f"at={at(a)}\tsha={s}\tmode={m}\n" for (m, s, a) in lignes)
        self.log_path.write_text(contenu, encoding="utf-8")

    def portes(self, lignes) -> None:
        """Une SUITE de portes, écrites comme `verify.sh::stamp_write` les écrit :
        CHAQUE porte ajoute sa ligne au journal ET réécrit le tampon courant.
        L'état final est donc « journal = toutes les portes, tampon = la
        dernière » — le seul que la production fabrique."""
        lignes = list(lignes)
        self.stamp_log(lignes)
        if lignes:
            mode, sha, at = lignes[-1]
            self.stamp(mode, sha, at)

    def trace(self, agent: str, at: datetime, tache: str = "T-00000602") -> None:
        """Une trace de binôme : `<tâche>.<def>.json`, contenu `{"at": …}`."""
        self._sous(".agents", "state", "local", "binome",
                   f"{tache}.{agent}.json").write_text(
            json.dumps({"at": _iso(at), "sha": "deadbee"}), encoding="utf-8")

    def vider_traces(self) -> None:
        shutil.rmtree(self.dir / ".agents/state/local/binome", ignore_errors=True)

    # ---- exécution par le canal RÉEL ---------------------------------------
    def run(self, payload=None, hook: Path | None = None,
            en_plus: dict | None = None) -> subprocess.CompletedProcess:
        """`hook` : une VARIANTE de la garde (`_garde_variante`), pour les seuls
        témoins qui ont besoin d'interrompre un tour à un point précis.
        `en_plus` : variables ajoutées à l'environnement de la garde (R3')."""
        if payload is None:
            payload = {"hook_event_name": "Stop", "stop_hook_active": False}
        env = _env(CLAUDE_PROJECT_DIR=str(self.dir), **(en_plus or {}))
        # PAS de premier argument : la racine vient de CLAUDE_PROJECT_DIR, le
        # canal de production. Charge JSON sur STDIN, comme l'hôte l'envoie.
        return subprocess.run(
            ["bash", str(hook or HOOK)],
            input=json.dumps(payload),
            capture_output=True, text=True, env=env, cwd=str(self.dir),
        )

    def cleanup(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        self.assertTrue(HOOK.is_file(), f"hook introuvable : {HOOK}")
        self.d = _Depot()
        now = self.d.now
        self.m = lambda n: now - timedelta(minutes=n)
        self.h = lambda n: now - timedelta(hours=n)

    def tearDown(self) -> None:
        self.d.cleanup()

    # LE CANAL EST MESURÉ ICI, une fois, pour tout le banc.
    def assert_block(self, r: subprocess.CompletedProcess) -> dict:
        self.assertEqual(
            r.returncode, 0,
            f"canal `Stop` = `decision:block` sur STDOUT, PAS un exit 2 "
            f"(rc={r.returncode}, stderr={r.stderr!r})")
        out = r.stdout.strip()
        self.assertTrue(
            out, f"attendu un REFUS sur stdout, rien reçu (stderr={r.stderr!r})")
        data = json.loads(out)
        self.assertEqual(data.get("decision"), "block", out)
        return data

    def assert_pass(self, r: subprocess.CompletedProcess) -> None:
        self.assertEqual(
            r.returncode, 0, f"rc={r.returncode}, stderr={r.stderr!r}")
        self.assertEqual(
            r.stdout.strip(), "",
            f"attendu AUCUN refus (stdout vide), reçu : {r.stdout!r}")


class FenetreTests(_Base):
    """Les propriétés de la fenêtre, chacune avec son témoin non vacant."""

    def test_1_deux_verts_fenetre_part_de_lavant_dernier(self) -> None:
        """PROPRIÉTÉ 1. Deux cycles → la fenêtre part de l'AVANT-DERNIER, donc une
        revue faite ENTRE les deux verts compte : c'est le cas NOMINAL qui
        échouait avant le recul d'un cran.

        DISCRIMINANT DANS LE TEST : une TROISIÈME porte tombée APRÈS les deux
        traces devient l'avant-dernier cycle — la fenêtre avance avec lui, les
        deux traces en sortent, il ne reste AUCUN critique (S-00004500 : un seul
        suffirait), et la garde refuse. Sans borne (12 h), ce bras passerait."""
        self.d.portes([
            ("frozen", "prev0000", self.m(40)),   # avant-dernier
            ("frozen", self.d.head, self.m(20)),  # dernier vert
        ])
        self.d.trace("critic-opus", self.m(30))   # ENTRE les deux
        self.d.trace("critic-fable", self.m(25))  # ENTRE les deux
        self.assert_pass(self.d.run())

        self.d.portes([
            ("frozen", "prev0000", self.m(40)),
            ("frozen", "mid00000", self.m(22)),   # nouvel avant-dernier
            ("frozen", self.d.head, self.m(20)),
        ])
        data = self.assert_block(self.d.run())
        self.assertIn("0 critique(s)", data["reason"], data["reason"])

    def test_2_traces_avant_lavant_dernier_refusees(self) -> None:
        """PROPRIÉTÉ 2. Même dispositif à DEUX cycles, mais les traces sont
        ANTÉRIEURES à l'avant-dernier vert → refus. Sans ce bras, la propriété 1
        prouverait seulement que la fenêtre est LARGE, jamais qu'elle a un bord.

        Et les traces sont DANS les 12 h : ce refus prouve que la borne est le
        cycle précédent, pas la fenêtre d'adoptant."""
        self.d.portes([
            ("frozen", "prev0000", self.m(40)),   # avant-dernier
            ("frozen", self.d.head, self.m(20)),  # dernier vert
        ])
        self.d.trace("critic-opus", self.m(55))   # AVANT l'avant-dernier
        self.d.trace("critic-fable", self.m(50))  # AVANT l'avant-dernier
        self.assert_block(self.d.run())

    def test_3_un_seul_vert_pas_de_borne_fenetre_12h(self) -> None:
        """D1 (b) — UN SEUL cycle → PAS de borne : la fenêtre de 12 h reprend,
        comme `cycle_precedent` rend None. C'est la PREMIÈRE porte d'un adoptant,
        et la version précédente refusait ici un cycle CONFORME (binôme tourné
        AVANT la porte, comme la doctrine l'impose).

        MUTATION QUI LE FAIT ROUGIR : rétablir « un seul vert rend CE vert »
        (`verts[-1]`) — les traces à -90/-85, antérieures au vert de -30, sont
        alors hors fenêtre et la garde REFUSE.

        CONTRÔLE : la fenêtre de 12 h n'est pas une garde muette — deux traces
        de plus de 12 h, sous le même vert unique, sont REFUSÉES."""
        self.d.portes([("frozen", self.d.head, self.m(30))])
        self.d.trace("critic-opus", self.m(90))
        self.d.trace("critic-fable", self.m(85))
        self.assert_pass(self.d.run())

        self.d.vider_traces()
        self.d.trace("critic-opus", self.h(14))
        self.d.trace("critic-fable", self.h(13))
        self.assert_block(self.d.run())

    def test_3bis_porte_rejouee_meme_sha_un_seul_cycle(self) -> None:
        """D1 (a) — une porte REJOUÉE sur le MÊME sha (après un flake, ou parce
        que le hook post-`done` a commité l'état) est UN cycle, pas deux :
        l'avant-dernier cycle reste le vert d'AVANT, et le binôme tourné entre
        les deux vrais cycles COMPTE.

        MUTATION QUI LE FAIT ROUGIR : retirer la déduplication — le rejeu
        (-10) devient le dernier vert, la PREMIÈRE porte sur `head` (-20) devient
        l'avant-dernier, les traces (-30/-25) tombent avant, et la garde REFUSE
        un cycle conforme."""
        self.d.portes([
            ("frozen", "prev0000", self.m(40)),
            ("frozen", self.d.head, self.m(20)),
            ("frozen", self.d.head, self.m(10)),  # la MÊME porte, rejouée
        ])
        self.d.trace("critic-opus", self.m(30))
        self.d.trace("critic-fable", self.m(25))
        self.assert_pass(self.d.run())

    def test_3ter_premiere_porte_rejouee_aucune_borne(self) -> None:
        """D1 — « aucun avant-dernier APRÈS déduplication » ⇒ pas de borne. La
        toute première porte d'un adoptant, rejouée une fois, reste UN cycle :
        la fenêtre de 12 h reprend, et le binôme de -90/-85 compte.

        MUTATION QUI LE FAIT ROUGIR : retirer la déduplication — deux lignes
        deviennent deux cycles, l'avant-dernier (-40) borne la fenêtre et les
        traces (-90/-85) en sortent : REFUS."""
        self.d.portes([
            ("frozen", self.d.head, self.m(40)),
            ("frozen", self.d.head, self.m(20)),  # rejeu du même sha
        ])
        self.d.trace("critic-opus", self.m(90))
        self.d.trace("critic-fable", self.m(85))
        self.assert_pass(self.d.run())

    def test_3quater_critique_avant_lavant_dernier_DISTINCT_refuse(self) -> None:
        """D1 (c) — LA GARDE RESTE UNE GARDE. Une porte rejouée dans l'historique
        ne fait pas reculer la fenêtre au-delà du cycle précédent : un critique
        tracé AVANT l'avant-dernier vert DISTINCT ne compte pas.

        Cycles distincts : -60, -40 (rejoué à -35), -20. Avant-dernier distinct
        = -40. `critic-opus` à -50 et `critic-fable` à -55 sont AVANT : aucun
        critique ne compte → REFUS (une fenêtre reculée à -60 les compterait)."""
        self.d.portes([
            ("frozen", "green001", self.m(60)),
            ("frozen", "green002", self.m(40)),
            ("frozen", "green002", self.m(35)),   # rejeu
            ("frozen", self.d.head, self.m(20)),
        ])
        self.d.trace("critic-opus", self.m(50))   # AVANT l'avant-dernier distinct
        self.d.trace("critic-fable", self.m(55))  # AVANT aussi
        data = self.assert_block(self.d.run())
        self.assertIn("0 critique(s)", data["reason"], data["reason"])

    def test_3quinquies_rejeu_on_garde_la_PREMIERE_borne(self) -> None:
        """D1 — « même sha = même cycle ; on garde la PREMIÈRE borne ». Cette règle
        n'avait AUCUN témoin (exec-critic, T-00000695/696) : la mutation « dernière
        borne » restait verte ici ET chez la jumelle.

        Cycles A(-60) B(-40) B(-35, rejeu) C(-20). Première borne : l'avant-dernier
        cycle distinct commence à -40, et le binôme tourné ENTRE la porte B et son
        rejeu (-38, -37) COMPTE → PASS. MUTATION QUI LE FAIT ROUGIR : garder la
        DERNIÈRE borne du rejeu (`cycles[-1] = (at, sha)`) — l'avant-dernier cycle
        devient -35, les deux traces tombent avant, REFUS.

        CONTRÔLE ARMÉ : même journal, binôme à -45/-44 (avant la porte B) → REFUS.
        Sans lui, une garde qui accepterait tout laisserait ce PASS vert."""
        self.d.portes([
            ("frozen", "green001", self.m(60)),
            ("frozen", "green002", self.m(40)),
            ("frozen", "green002", self.m(35)),   # rejeu de la porte B
            ("frozen", self.d.head, self.m(20)),
        ])
        self.d.trace("critic-opus", self.m(45))
        self.d.trace("critic-fable", self.m(44))
        self.assert_block(self.d.run())           # contrôle armé

        self.d.vider_traces()
        self.d.trace("critic-opus", self.m(38))   # entre B et son rejeu
        self.d.trace("critic-fable", self.m(37))
        self.assert_pass(self.d.run())

    def test_4_aucun_vert_fenetre_12h_adoptant(self) -> None:
        """PROPRIÉTÉ 4. AUCUN vert (ni `VERIFY_STAMP` ni `.log`) = le régime de
        l'ADOPTANT, où ces fichiers git-ignorés sont absents. La fenêtre de 12 h
        reprend. Deux témoins : une trace VIEILLE (> 12 h) ne satisfait PAS la
        garde (elle ne devient pas aveugle) ; deux traces RÉCENTES la satisfont
        (la fenêtre est vivante, le refus vient de l'âge et non d'un refus
        systématique)."""
        # aucun stamp fabriqué — état par défaut de l'adoptant.
        self.d.trace("critic-opus", self.h(24))   # VIEILLE
        self.d.trace("critic-fable", self.h(23))  # VIEILLE
        self.assert_block(self.d.run())

        self.d.vider_traces()
        self.d.trace("critic-opus", self.h(1))     # RÉCENTE (< 12 h)
        self.d.trace("critic-fable", self.m(30))   # RÉCENTE (< 12 h)
        self.assert_pass(self.d.run())

    def test_5_mode_live_nest_pas_un_vert(self) -> None:
        """PROPRIÉTÉ 5. Une ligne `mode=live` ne compte PAS comme un cycle — c'est
        un faux vert déjà payé une fois ici. Journal : deux FROZEN (-60, -40) puis
        une forme NUE (-5, `live`), tampon courant `live` — exactement ce que
        `stamp_write` laisse après une forme nue. Traces à -50/-48 : APRÈS le
        premier frozen, AVANT le second.

        Correct (live IGNORÉ) : l'avant-dernier cycle est -60 → PASS. Discriminant
        (la même porte de -5 jouée `--at`, donc `frozen`) : elle devient un 3ᵉ
        cycle, l'avant-dernier passe à -40, les traces tombent avant → REFUS."""
        self.d.portes([
            ("frozen", "green001", self.m(60)),
            ("frozen", "green002", self.m(40)),
            ("live", "livesha0", self.m(5)),
        ])
        self.d.trace("critic-opus", self.m(50))
        self.d.trace("critic-fable", self.m(48))
        self.assert_pass(self.d.run())

        self.d.portes([
            ("frozen", "green001", self.m(60)),
            ("frozen", "green002", self.m(40)),
            ("frozen", self.d.head, self.m(5)),
        ])
        self.assert_block(self.d.run())

    def test_6_at_inconnu_est_ecarte_comme_chez_la_jumelle(self) -> None:
        """D1, TROISIÈME FILTRE RECOPIÉ — `cycle_precedent` ÉCARTE une ligne dont
        l'`at` est vide ou `unknown` (le repli de `date` dans `stamp_write`). La
        version précédente la gardait comme un cycle SANS date ; tombée en
        avant-dernière position, elle rendait la borne `None`, donc la fenêtre de
        12 h — plus LARGE que celle de la jumelle.

        Cycles lus comme la jumelle : -40, -20 (l'`unknown` est sauté). Traces à
        -90/-85, dans les 12 h mais avant -40 → REFUS. MUTATION QUI LE FAIT
        ROUGIR : garder la ligne `unknown` comme cycle → avant-dernier sans date
        → 12 h → PASS."""
        self.d.portes([
            ("frozen", "green001", self.m(40)),
            ("frozen", "green002", "unknown"),
            ("frozen", self.d.head, self.m(20)),
        ])
        self.d.trace("critic-opus", self.m(90))
        self.d.trace("critic-fable", self.m(85))
        self.assert_block(self.d.run())

    def test_7_le_tampon_courant_ne_fait_pas_un_cycle_hors_journal(self) -> None:
        """D1, QUATRIÈME POINT RECOPIÉ — `cycle_precedent` lit le JOURNAL SEUL. La
        version précédente ajoutait le tampon courant quand il manquait au
        journal ; les deux moitiés du même design comptaient alors des cycles
        différents. `stamp_write` les écrit ENSEMBLE ; seul un ajout au journal
        ÉCHOUÉ (il est `|| true`) les découple, et la jumelle ne le voit pas
        davantage — une seule définition, avec son angle mort ÉCRIT.

        Journal : -40, -20. Tampon courant frozen à -5, sur un sha ABSENT du
        journal. Traces -30/-25. Lecture de la jumelle : avant-dernier = -40 →
        PASS. MUTATION QUI LE FAIT ROUGIR : ré-ajouter le tampon courant comme
        cycle → avant-dernier = -20 → REFUS."""
        self.d.stamp_log([
            ("frozen", "green001", self.m(40)),
            ("frozen", "green002", self.m(20)),
        ])
        self.d.stamp("frozen", self.d.head, self.m(5))
        self.d.trace("critic-opus", self.m(30))
        self.d.trace("critic-fable", self.m(25))
        self.assert_pass(self.d.run())

    def test_8_borne_assumee_le_binome_du_cycle_k_couvre_le_cycle_k_plus_1(self) -> None:
        """BORNE ASSUMÉE — décision pilote par défaut du 23/09 (critic-opus T2,
        mesuré). Ce témoin ÉPINGLE le comportement pour qu'un changement futur de
        cette sémantique soit un rouge DÉLIBÉRÉ, jamais une dérive muette. Il ne
        dit pas que c'est souhaitable : il dit que c'est CE QUI EST, et accepté.

        Le diff part de la DERNIÈRE porte P_k, les critiques comptent depuis
        P_(k-1) : le binôme du cycle k couvre donc tout le cycle k+1, jusqu'à
        P_(k+1). CE N'EST PAS BORNÉ COMME CHEZ LA JUMELLE — `done` ferme le lot
        relu sous P_k, cette garde juge ce qui est écrit APRÈS P_k. Sur un flux
        conforme elle ne mord que sur un cycle SANS AUCUN binôme, y compris pour
        des tâches ajoutées au board.

        Dispositif : P1 à t-60, critique à t-49, P2 à t-40 sur un board à UNE
        tâche ; TROIS tâches ajoutées APRÈS P2, seule écriture du cycle (la
        surface doctrinale est remise à HEAD) → PASS.

        CONTRÔLE ARMÉ : même état, seul un critique d'AVANT P1 (t-70) → REFUS qui
        nomme les trois tâches ajoutées, et elles seules. Sans lui, ce PASS
        pourrait venir d'une garde qui ne voit plus le board.

        MUTATION QUI LE FAIT ROUGIR (jouée le 23/09, puis restaurée) : ancrer la
        fenêtre des critiques sur le DERNIER vert (`cycles[-1][0]` dans
        `horodatage_stamp`). Le critique de t-49 tombe alors avant P2 : le bras
        PASS compte 0 critique au lieu de 1, et rougit (S-00004500 : un suffit)."""
        self.d.arbre_propre()
        board = self.d._sous(".agents", "state", "board", "TASKS.json")

        def ecrire(ids) -> None:
            board.write_text(json.dumps(
                {"tasks": [{"id": i, "state": "pending"} for i in ids]}),
                encoding="utf-8")

        ecrire(["T-00000001"])
        self.d._git("add", ".agents/state/board/TASKS.json")
        self.d._git("commit", "-q", "-m", "board sous P2")
        p2 = self.d._git("rev-parse", "HEAD").strip()
        self.assertNotEqual(p2, self.d.head, "le commit du board sous P2 a échoué")
        self.d.portes([
            ("frozen", self.d.head, self.m(60)),  # P1 = P_(k-1)
            ("frozen", p2, self.m(40)),           # P2 = P_k, ancre du diff
        ])
        ecrire(["T-00000001", "T-00000002", "T-00000003", "T-00000004"])
        self.d.trace("critic-opus", self.m(70))   # AVANT P1 : hors fenêtre

        data = self.assert_block(self.d.run())    # contrôle armé
        self.assertIn("board : 3 tâche(s) ajoutée(s)", data["reason"], data["reason"])
        self.assertIn("0 critique(s)", data["reason"], data["reason"])
        self.assertNotIn(SURFACE_DURABLE, data["reason"], data["reason"])

        self.d.trace("critic-fable", self.m(49))  # critique du cycle k, AVANT P2
        self.assert_pass(self.d.run())


class ContratTests(_Base):
    """Les surfaces du contrat qui font que la garde MORD ou se TAIT.

    CONSTAT DU BINÔME (22/09) : les quatre premiers témoins ci-dessous
    assertaient un PASS sur `_fixture_refus` sans jamais établir que cet état
    était REFUSÉ par la garde armée — une garde qui ne refuserait plus rien les
    laissait verts. Et la fixture elle-même en dépendait sans le dire : « un vert,
    traces trop vieilles pour lui » n'est plus refusable depuis D1 (un seul cycle
    = fenêtre de 12 h). Chacun porte désormais son CONTRÔLE ARMÉ, et la fixture
    refuse par le motif le plus stable de la garde : il manque un critique."""

    def _fixture_refus(self) -> None:
        """Un état que la garde ARMÉE refuse, quelle que soit la fenêtre : deux
        cycles, AUCUN critique dans la fenêtre. Chaque utilisateur de cette
        fixture le PROUVE avant d'asserter un PASS (`_controle_arme`)."""
        self.d.portes([
            ("frozen", "prev0000", self.m(40)),
            ("frozen", self.d.head, self.m(20)),
        ])
        # AUCUNE trace : un seul critique suffirait depuis S-00004500 (T-00001225).

    def _controle_arme(self) -> None:
        """Le contrôle positif apparié : MÊME état, garde armée, charge normale,
        critique absent ⇒ REFUS. Sans lui, le PASS qui suit ne prouve rien."""
        data = self.assert_block(self.d.run())
        self.assertIn(SURFACE_DURABLE, data["reason"], data["reason"])

    def test_desarme_par_defaut_zero_octet(self) -> None:
        """Sans `AFFIRMATION_REQUIRED`, la garde rend 0 octet même sur un état
        refusable : l'ABSENCE du marqueur est le régime de référence."""
        self._fixture_refus()
        self._controle_arme()
        self.d.desarmer()
        r = self.d.run()
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout, "", f"désarmée = 0 octet, reçu : {r.stdout!r}")

    def test_stop_hook_active_echappe(self) -> None:
        """L'hôte REJOUE un `Stop` déjà bloqué : `stop_hook_active=true` échappe,
        sinon la garde bouclerait à l'infini."""
        self._fixture_refus()
        self._controle_arme()
        r = self.d.run({"hook_event_name": "Stop", "stop_hook_active": True})
        self.assert_pass(r)

    def test_stdin_vide_est_advisory(self) -> None:
        """Charge vide sur stdin → exit 0, 0 octet : on ne bloque jamais sur une
        entrée qu'on n'a pas."""
        self._fixture_refus()
        self._controle_arme()
        env = _env(CLAUDE_PROJECT_DIR=str(self.d.dir))
        r = subprocess.run(["bash", str(HOOK)], input="", capture_output=True,
                           text=True, env=env, cwd=str(self.d.dir))
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout, "")

    def test_sortie_tracee_consomme_et_journalise(self) -> None:
        """La sortie tracée `AFFIRMATION_SANS_BINOME` fait PASSER un état
        refusable, est CONSOMMÉE une fois et JOURNALISÉE (elle reste visible)."""
        self._fixture_refus()
        self._controle_arme()
        self.d.sortie_tracee("renommage sans objet de revue\n")
        self.assert_pass(self.d.run())
        self.assertFalse(
            (self.d.dir / ".agents/state/gates/AFFIRMATION_SANS_BINOME").exists(),
            "la sortie tracée doit être CONSOMMÉE (retirée) après usage")
        journal = self.d.dir / ".agents/state/local/affirmation-sorties.log"
        self.assertTrue(journal.is_file(), "la sortie doit être JOURNALISÉE")
        self.assertIn("renommage sans objet", journal.read_text(encoding="utf-8"))
        # … et elle ne vaut qu'UNE fois.
        self._controle_arme()

    def test_vocabulaire_de_critique_est_clos(self) -> None:
        """Un nom HORS vocabulaire (`critic-maison`) ne satisfait PAS la garde,
        même à deux traces bien datées : `critiques_depuis` filtre sur la liste
        close. Preuve que le banc reprend le BON vocabulaire — un critique inventé
        testerait un chemin mort."""
        self.d.portes([
            ("frozen", "prev0000", self.m(40)),
            ("frozen", self.d.head, self.m(20)),
        ])
        self.d.trace("critic-maison", self.m(30))   # hors vocabulaire
        self.d.trace("critic-autre", self.m(25))    # hors vocabulaire
        self.assert_block(self.d.run())

    # ---- sortie NON HONORÉE (exec-critic, T-00000695/696) --------------------
    def _journal_non_inscriptible(self, depot: _Depot, variante: str):
        """Rend le journal des sorties NON INSCRIPTIBLE ; rend la fonction qui le
        répare. « lecture seule » = le scénario mesuré par le critique (chmod 444) ;
        « répertoire » = la même panne sans dépendre de l'uid (root compris)."""
        journal = depot.journal_sorties
        if variante == "répertoire":
            journal.mkdir()
            return journal.rmdir
        journal.write_text("", encoding="utf-8")
        journal.chmod(0o444)
        return lambda: journal.chmod(0o644)

    def test_journal_non_inscriptible_la_sortie_nest_pas_honoree(self) -> None:
        """CHEMIN ORDINAIRE. Journal non inscriptible + sortie posée ⇒ REFUS qui
        NOMME le journal, sortie ENCORE PRÉSENTE, et au tour suivant toujours
        REFUS. Avant : l'écriture et le retrait partageaient un `except OSError:
        pass`, la fonction rendait True, et UNE sortie désarmait la garde POUR
        TOUJOURS, sans un mot (mesuré par le critique, chmod 444).

        CONTRÔLE (chemin normal inchangé) : journal réparé ⇒ la MÊME sortie passe,
        est consommée et journalisée. MUTATION QUI LE FAIT ROUGIR : rétablir le
        `try` unique — le premier tour PASSE au lieu de refuser."""
        for variante in ("lecture seule", "répertoire"):
            with self.subTest(variante=variante):
                if variante == "lecture seule" and DROITS_SANS_EFFET:
                    self.skipTest("chmod sans effet (root ou Windows) — variante répertoire seule")
                d = _Depot()
                try:
                    self.d, garde = d, self.d
                    self._fixture_refus()
                    self._controle_arme()
                    reparer = self._journal_non_inscriptible(d, variante)
                    d.sortie_tracee("revue sans objet\n")
                    for tour in (1, 2):
                        data = self.assert_block(d.run())
                        self.assertIn("NON HONORÉE", data["reason"], f"tour {tour}")
                        self.assertIn("affirmation-sorties.log", data["reason"],
                                      "le journal en cause est NOMMÉ")
                        self.assertIn(SURFACE_DURABLE, data["reason"],
                                      "c'est bien le refus ORDINAIRE qui le dit")
                        self.assertTrue(d.sortie_path.exists(),
                                        f"tour {tour} : la sortie n'est PAS consommée")
                        self.assertFalse(
                            (d.dir / ".agents/state/gates/"
                             "AFFIRMATION_SANS_BINOME.en-cours").exists(),
                            f"tour {tour} : retirée puis REMISE EN PLACE, rien derrière")
                    reparer()
                    self.assert_pass(d.run())
                    self.assertFalse(d.sortie_path.exists(), "réparé : consommée")
                    self.assertIn("revue sans objet",
                                  d.journal_sorties.read_text(encoding="utf-8"))
                finally:
                    self.d = garde
                    d.cleanup()

    @unittest.skipIf(DROITS_SANS_EFFET, "chmod d'un dossier sans effet (root ou Windows)")
    def test_retrait_impossible_la_sortie_nest_pas_honoree(self) -> None:
        """PREMIER TEMPS : la sortie ne peut pas être RETIRÉE (dossier des
        marqueurs en lecture seule). Honorée sans retrait, elle vaudrait pour TOUS
        les tours suivants : elle ne l'est donc pas, et le refus le dit.

        RETIRER D'ABORD, JOURNALISER ENSUITE (critic-opus T4, exec-critic). La
        version précédente journalisait, puis, le retrait échoué, ajoutait une
        ligne `NON HONORÉE` : DEUX lignes horodatées par tour, que le LECTEUR du
        journal (`session-start.sh`) compte comme deux sorties FRANCHIES — mesuré,
        6 pour 0 honorée après 3 tours, et l'alarme « DEUX OU PLUS SOUS LA MÊME
        PORTE ». Un retrait impossible ne laisse désormais RIEN au journal, et le
        compte est pris par le motif EXACT du lecteur. MUTATIONS : journaliser
        avant de retirer — le lecteur compte des lignes, rouge ; `pass` + `return
        True` sur l'échec du retrait — le tour PASSE, rouge.

        CONTRÔLE : réparé, la MÊME sortie passe, est consommée, et le lecteur en
        compte UNE — le compteur n'est pas aveugle."""
        self._fixture_refus()
        self._controle_arme()
        self.d.sortie_tracee("revue sans objet\n")
        journal = self.d.journal_sorties
        gates = self.d.dir / ".agents/state/gates"
        gates.chmod(0o555)
        try:
            for tour in (1, 2, 3):
                data = self.assert_block(self.d.run())
                self.assertIn("NON HONORÉE", data["reason"], f"tour {tour}")
                self.assertIn("RETIRÉE", data["reason"], data["reason"])
                self.assertTrue(self.d.sortie_path.exists(), f"tour {tour}")
            self.assertEqual(
                0, _sorties_comptees_par_session_start(journal),
                "trois tours bloqués, ZÉRO sortie franchie : le lecteur n'en voit "
                "aucune — " + (journal.read_text(encoding="utf-8")
                               if journal.is_file() else "(journal absent)"))
        finally:
            gates.chmod(0o755)
        self.assert_pass(self.d.run())                    # réparé : honorée
        self.assertFalse(self.d.sortie_path.exists())
        self.assertFalse((gates / "AFFIRMATION_SANS_BINOME.en-cours").exists(),
                         "le fichier de retrait en cours ne reste pas derrière")
        self.assertEqual(1, _sorties_comptees_par_session_start(journal),
                         "UNE sortie honorée, UNE comptée")

    def test_surface_forgee_ne_forge_pas_de_ligne_au_journal(self) -> None:
        """ADVISORY S-00001891. Le journal est ligne à ligne, champs à TAB : un id
        de tâche AJOUTÉE portant `\\n`/`\\t`/`\\r` forgeait une seconde ligne,
        horodatage compris (mesuré sur la garde d'avant : UNE sortie, DEUX lignes).
        MUTATION QUI LE FAIT ROUGIR : retirer `_echapper` — 2 lignes au lieu d'une.
        CONTRÔLE ARMÉ : le même état, sans sortie, est REFUSÉ."""
        board = self.d._sous(".agents", "state", "board", "TASKS.json")
        board.write_text('{"tasks":[{"id":"T-001"}]}\n', encoding="utf-8")
        self.d._git("add", ".agents/state/board/TASKS.json")
        self.d._git("commit", "-q", "-m", "board")
        self.d.portes([
            ("frozen", "prev0000", self.m(40)),
            ("frozen", "green002", self.m(20)),
        ])
        forge = "T-2\n2026-01-01T00:00:00Z\tsurfaces=FORGEE\r"
        board.write_text(json.dumps({"tasks": [{"id": "T-001"}, {"id": forge}]}),
                         encoding="utf-8")
        self.d.trace("critic-opus", self.m(50))       # AVANT la fenêtre (-40) : 0 critique
        self._controle_arme()
        self.d.sortie_tracee("revue sans objet\n")
        self.assert_pass(self.d.run())
        lignes = self.d.journal_sorties.read_text(encoding="utf-8").splitlines()
        self.assertEqual(1, len(lignes), f"UNE sortie = UNE ligne : {lignes!r}")
        self.assertIn("T-2\\n2026-01-01T00:00:00Z\\tsurfaces=FORGEE\\r", lignes[0])

    def test_nom_de_trace_forge_natteint_pas_le_journal(self) -> None:
        """LE VECTEUR NOMMÉ PAR L'ADVISORY, MESURÉ INATTEIGNABLE EN SÉQUENCE : la
        sortie est consommée par le chemin ordinaire AVANT toute lecture de trace,
        donc un nom de trace (lu par `os.listdir`) n'arrive jamais au journal.
        Épinglé pour que la phrase de `_echapper` ne devienne pas fausse en
        silence : réordonner la garde (traces lues AVANT la sortie) ferait entrer
        le nom au journal, et ce test rougirait."""
        self._fixture_refus()
        self._controle_arme()
        self.d._sous(".agents", "state", "local", "binome",
                     "T-1\nFORGEE\tx.critic-fable.json").write_bytes(OCTET_NON_UTF8)
        self.d.sortie_tracee("revue sans objet\n")
        self.assert_pass(self.d.run())
        texte = self.d.journal_sorties.read_text(encoding="utf-8")
        self.assertEqual(1, len(texte.splitlines()), texte)
        self.assertNotIn("FORGEE", texte, "le nom de trace n'atteint pas le journal")
        self.assertIn(f"surfaces={SURFACE_DURABLE}", texte)

    # ---- ORPHELIN `.en-cours` (exec-critic, passes post-binôme T-00000695/696) ----
    # Un kill entre le retrait et le journal laissait la raison du pilote dans
    # `AFFIRMATION_SANS_BINOME.en-cours`, que PERSONNE ne relisait : le tour
    # suivant refusait sans un mot, et une nouvelle sortie écrasait l'orpheline.
    def _variante(self, ancre: str, remplacement: str) -> Path:
        dossier = Path(tempfile.mkdtemp(prefix="affguard-variante-"))
        self.addCleanup(shutil.rmtree, dossier, True)
        return _garde_variante(dossier, ancre, remplacement)

    @property
    def _en_cours(self) -> Path:
        return self.d.dir / ".agents/state/gates/AFFIRMATION_SANS_BINOME.en-cours"

    def _tour_tue(self, point) -> None:
        """Un tour INTERROMPU au point nommé : l'hôte n'en reçoit RIEN."""
        r = self.d.run(hook=self._variante(*point))
        self.assertEqual((r.returncode, r.stdout), (0, ""), r.stderr)

    def test_orphelin_seul_est_repris_et_consomme_au_tour_suivant(self) -> None:
        """Kill entre le retrait et le journal ⇒ orphelin. Le tour SUIVANT le
        reprend, le consomme et le journalise : UNE ligne, UNE sortie comptée
        par le lecteur, plus rien derrière — puis il ne vaut plus. MUTATION :
        retirer la reprise (temps 0) — l'orphelin reste, le tour est REFUSÉ, rouge."""
        self._fixture_refus()
        self._controle_arme()
        self.d.sortie_tracee("raison PILOTE orpheline\n")
        self._tour_tue(TUER_AVANT_JOURNAL)
        self.assertTrue(self._en_cours.is_file(), "précondition : l'orphelin existe")
        self.assertFalse(self.d.sortie_path.exists(), "précondition : retirée")
        self.assertEqual(0, _sorties_comptees_par_session_start(self.d.journal_sorties))
        self.assert_pass(self.d.run())
        self.assertFalse(self._en_cours.exists(), "l'orphelin est CONSOMMÉ")
        self.assertFalse(self.d.sortie_path.exists())
        texte = self.d.journal_sorties.read_text(encoding="utf-8")
        self.assertEqual(1, len(texte.splitlines()), texte)
        self.assertIn("raison PILOTE orpheline", texte)
        self.assertEqual(1, _sorties_comptees_par_session_start(self.d.journal_sorties))
        self._controle_arme()                              # … et elle ne vaut qu'UNE fois

    def test_orphelin_et_nouvelle_sortie_refus_nomme_les_deux_rien_ecrase(self) -> None:
        """Orphelin + nouvelle sortie : RIEN n'est écrasé ni consommé, le refus
        NOMME les deux fichiers, deux tours de suite. CONTRÔLE : l'orphelin effacé
        par le pilote, la nouvelle passe. MUTATION : retirer le cas « deux
        présentes » — le retrait écrase l'orpheline et le tour PASSE, rouge."""
        self._fixture_refus()
        self._controle_arme()
        self.d.sortie_tracee("raison A orpheline\n")
        self._tour_tue(TUER_AVANT_JOURNAL)
        self.d.sortie_tracee("raison B nouvelle\n")
        for tour in (1, 2):
            data = self.assert_block(self.d.run())
            self.assertIn("NON HONORÉE", data["reason"], f"tour {tour}")
            self.assertIn("DEUX sorties se font face", data["reason"])
            self.assertIn("  .agents/state/gates/AFFIRMATION_SANS_BINOME\n", data["reason"])
            self.assertIn("  .agents/state/gates/AFFIRMATION_SANS_BINOME.en-cours\n",
                          data["reason"])
            self.assertIn(SURFACE_DURABLE, data["reason"], "le refus ORDINAIRE le dit")
            self.assertEqual("raison B nouvelle\n",
                             self.d.sortie_path.read_text(encoding="utf-8"), f"tour {tour}")
            self.assertEqual("raison A orpheline\n",
                             self._en_cours.read_text(encoding="utf-8"), f"tour {tour}")
            self.assertEqual(0, _sorties_comptees_par_session_start(self.d.journal_sorties))
        self._en_cours.unlink()                            # le geste du pilote
        self.assert_pass(self.d.run())
        texte = self.d.journal_sorties.read_text(encoding="utf-8")
        self.assertEqual(1, len(texte.splitlines()), texte)
        self.assertIn("raison B nouvelle", texte)

    def test_orphelin_deja_journalise_n_est_pas_honore_deux_fois(self) -> None:
        """Kill entre le journal et l'effacement : la sortie A ÉTÉ honorée (le
        tour tué n'a rien refusé) et journalisée. Le tour suivant reconnaît son
        `id=` au journal, efface l'orphelin et NE l'honore PAS une seconde fois :
        refus ordinaire, toujours UNE ligne. MUTATION : retirer le dédoublonnage
        — l'orphelin est repris, le tour PASSE et le journal porte 2 lignes, rouge."""
        self._fixture_refus()
        self._controle_arme()
        self.d.sortie_tracee("raison A deja journalisee\n")
        self._tour_tue(TUER_AVANT_EFFACEMENT)
        self.assertTrue(self._en_cours.is_file(), "précondition : l'orphelin existe")
        self.assertEqual(1, _sorties_comptees_par_session_start(self.d.journal_sorties),
                         "précondition : elle est journalisée")
        data = self.assert_block(self.d.run())
        self.assertNotIn("NON HONORÉE", data["reason"], "rien n'attendait d'être honoré")
        self.assertFalse(self._en_cours.exists(), "l'orphelin journalisé est effacé")
        self.assertEqual(1, _sorties_comptees_par_session_start(self.d.journal_sorties))

    def _board_a_id_surrogate(self) -> None:
        """Un board qui AJOUTE l'id `"T-2\\ud800"` — échappement JSON d'un
        surrogate isolé, fichier 100 % ASCII : `json.loads` rend une chaîne que
        l'UTF-8 strict refuse d'encoder."""
        board = self.d._sous(".agents", "state", "board", "TASKS.json")
        board.write_text('{"tasks": [{"id": "T-1"}]}\n', encoding="utf-8")
        self.d._git("add", ".agents/state/board/TASKS.json")
        self.d._git("commit", "-q", "-m", "board")
        self.d.arbre_propre()
        self.d.portes([
            ("frozen", "prev0000", self.m(40)),
            ("frozen", self.d._git("rev-parse", "HEAD").strip(), self.m(20)),
        ])
        self.d.trace("critic-opus", self.m(50))       # AVANT la fenêtre (-40) : 0 critique
        board.write_text('{"tasks": [{"id": "T-1"}, {"id": "T-2\\ud800"}]}\n',
                         encoding="ascii")
        data = self.assert_block(self.d.run())        # contrôle armé
        self.assertIn("1 tâche(s) ajoutée(s)", data["reason"], data["reason"])

    def test_id_surrogate_est_journalise_jamais_muet(self) -> None:
        """Le journal s'écrit en `backslashreplace` : un surrogate isolé y devient
        le texte `\\ud800`, la sortie est honorée et comptée UNE fois, le journal
        reste de l'UTF-8 valide. Avant : `UnicodeEncodeError` au journal, sortie
        coincée dans `.en-cours`, refus de panne SANS un mot sur elle. MUTATION :
        `errors="strict"` — sortie NON HONORÉE (dite, grâce au temps 2), rouge."""
        self._board_a_id_surrogate()
        self.d.sortie_tracee("revue sans objet\n")
        self.assert_pass(self.d.run())
        self.assertFalse(self.d.sortie_path.exists())
        self.assertFalse(self._en_cours.exists())
        brut = self.d.journal_sorties.read_bytes()
        texte = brut.decode("utf-8")                   # strict : UTF-8 VALIDE
        self.assertEqual(1, len(texte.splitlines()), texte)
        self.assertIn("T-2\\ud800", texte)
        self.assertEqual(1, _sorties_comptees_par_session_start(self.d.journal_sorties))

    def test_journal_qui_leve_hors_OSError_remet_la_sortie_et_le_dit(self) -> None:
        """LE TEMPS 2 SEUL, sur une variante au journal RE-STRICT : le surrogate
        lève `UnicodeEncodeError` — pas une `OSError`. La sortie est REMISE EN
        PLACE et le refus le DIT, en nommant l'exception ; rien derrière, rien
        au journal. MUTATION : `except OSError` rétabli — l'exception s'échappe
        vers le chemin de panne, qui REPREND l'orphelin (temps 0) et l'honore
        sous `surfaces=garde en panne — UnicodeEncodeError` : le tour PASSE au
        lieu d'être refusé, et le journal nomme la panne au lieu de la surface
        écrite (mesuré), rouge. Sans le temps 0, la sortie restait coincée dans
        `.en-cours` — le défaut d'origine."""
        self._board_a_id_surrogate()
        self.d.sortie_tracee("revue sans objet\n")
        data = self.assert_block(self.d.run(hook=self._variante(*JOURNAL_STRICT)))
        self.assertIn("NON HONORÉE", data["reason"], data["reason"])
        self.assertIn("UnicodeEncodeError", data["reason"])
        self.assertTrue(self.d.sortie_path.is_file(), "remise en place")
        self.assertFalse(self._en_cours.exists(), "rien derrière")
        self.assertEqual(0, _sorties_comptees_par_session_start(self.d.journal_sorties))

    def test_charge_trop_imbriquee_reste_advisory_sans_planter(self) -> None:
        """Une charge imbriquée assez profond lève `RecursionError` au `json.loads`
        — AVANT le crochet, donc hors de D2. Elle plantait : trace sur stderr,
        stdout vide. Même traitement qu'un JSON invalide désormais : ADVISORY,
        sans plantage. `'['*200000` = 200 Ko, sous ARG_MAX (mesuré 1 048 576 ici).
        MUTATION : retirer `RecursionError` du `except` — la trace revient, rouge."""
        self._fixture_refus()
        self._controle_arme()
        env = _env(CLAUDE_PROJECT_DIR=str(self.d.dir))
        r = subprocess.run(["bash", str(HOOK)], input="[" * 200000,
                           capture_output=True, text=True, env=env, cwd=str(self.d.dir))
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout, "", "une charge illisible reste ADVISORY")
        self.assertNotIn("Traceback", r.stderr, "elle ne PLANTE plus")

    #: Une locale NON UTF-8 que Python ne convertit pas d'office. `C` et `POSIX`
    #: ne conviennent PAS, et c'est mesuré ici (Python 3.14) : PEP 540 y active le
    #: mode UTF-8 (`sys.flags.utf8_mode == 1`), donc elles ne reproduisent rien.
    LOCALE_ASCII = "en_US.US-ASCII"

    def test_locale_non_utf8_ne_fait_pas_refuser_un_arbre_propre(self) -> None:
        """critic-opus T3. `git()` décodait la sortie de git dans la LOCALE : sous
        `LC_ALL=en_US.US-ASCII`, `git show BASE:TASKS.json` sur un board portant
        un caractère non ASCII levait `UnicodeDecodeError`, que D2 transformait en
        REFUS — sur un arbre PROPRE, tour de pure lecture, avec un remède faux
        (« un fichier corrompu qu'elle lit »). MUTATION : `text=True` rétabli dans
        `git()` — REFUS, rouge. CONTRÔLE : le même état sans locale imposée
        PASSE aussi, donc seul l'encodage est mesuré.

        SAUTÉ, EN LE DISANT, là où la locale n'existe pas (image Linux minimale :
        Python retombe sur `C`, donc sur UTF-8) — la précondition est mesurée dans
        l'environnement même que reçoit la garde, jamais supposée."""
        env_ascii = {"LC_ALL": self.LOCALE_ASCII, "LANG": self.LOCALE_ASCII}
        sonde = subprocess.run(
            ["python3", "-c", "import locale; print(locale.getpreferredencoding(False))"],
            capture_output=True, text=True,
            env={k: v for k, v in _env(**env_ascii).items()
                 if k not in ("PYTHONUTF8", "PYTHONIOENCODING")},
        )
        if sonde.returncode != 0 or "utf" in sonde.stdout.lower().replace("-", ""):
            self.skipTest(f"locale {self.LOCALE_ASCII} indisponible ici "
                          f"(encodage préféré : {sonde.stdout.strip() or sonde.stderr!r})")
        board = self.d._sous(".agents", "state", "board", "TASKS.json")
        board.write_text(
            json.dumps({"tasks": [{"id": "T-001", "task": "réparer l'été"}]},
                       ensure_ascii=False) + "\n", encoding="utf-8")
        self.d._git("add", ".agents/state/board/TASKS.json")
        self.d.arbre_propre()
        self.d._git("commit", "-q", "-m", "board accentue")
        head = self.d._git("rev-parse", "HEAD").strip()
        self.d.portes([("frozen", "prev0000", self.m(40)), ("frozen", head, self.m(20))])
        self.assertTrue(self.d.arbre_suivi_est_propre(), "précondition : arbre PROPRE")
        self.assertIn("é".encode("utf-8"),
                      subprocess.run(["git", "-C", str(self.d.dir), "show",
                                      head + ":.agents/state/board/TASKS.json"],
                                     capture_output=True, env=_env()).stdout,
                      "précondition : `git show` rend bien un octet non ASCII")
        self.assert_pass(self.d.run())                     # contrôle : locale héritée
        env_garde = {k: v for k, v in _env().items()
                     if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}
        env_garde.update(env_ascii, CLAUDE_PROJECT_DIR=str(self.d.dir))
        r = subprocess.run(
            ["bash", str(HOOK)],
            input=json.dumps({"hook_event_name": "Stop", "stop_hook_active": False}),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=env_garde, cwd=str(self.d.dir),
        )
        self.assert_pass(r)


class InfraIllisibleTests(_Base):
    """D2 — une garde ARMÉE qui ne peut pas lire SA PROPRE infrastructure REFUSE
    en nommant le fichier et le remède (décision pilote S-00001884).

    LE DÉFAUT FERMÉ, MESURÉ AVANT CORRECTION : un `VERIFY_STAMP.log` portant un
    octet non UTF-8 faisait lever `UnicodeDecodeError`, non attrapée ; le
    `exit 0` terminal du `.sh` rendait alors la main SANS UN OCTET sur stdout ;
    et sur `Stop`, stderr n'est pas lu. Succès MUET — la garde désarmée par un
    octet. `errors="replace"` a été écarté : il fermait l'instance, pas la classe.

    Chaque cas porte son CONTRÔLE « journal sain » : même état, fichier réparé,
    la garde retrouve son comportement nominal (refus ORDINAIRE, sans la phrase
    d'infrastructure ; ou PASS avec le binôme)."""

    PHRASE_INFRA = "INCAPABLE DE MESURER"

    def _etat_nominal(self) -> None:
        """Deux cycles, binôme complet dans la fenêtre : la garde PASSE."""
        self.d.portes([
            ("frozen", "prev0000", self.m(40)),
            ("frozen", self.d.head, self.m(20)),
        ])
        self.d.trace("critic-opus", self.m(30))
        self.d.trace("critic-fable", self.m(25))

    def _corrompre(self, chemin: Path) -> bytes:
        sain = chemin.read_bytes()
        chemin.write_bytes(sain + OCTET_NON_UTF8 + b"\n")
        return sain

    def _assert_refus_infra(self, r, nom: str) -> dict:
        data = self.assert_block(r)
        self.assertIn(self.PHRASE_INFRA, data["reason"], data["reason"])
        self.assertIn(nom, data["reason"], "le fichier illisible doit être NOMMÉ")
        self.assertIn("AFFIRMATION_SANS_BINOME", data["reason"],
                      "le remède doit nommer la sortie ponctuelle")
        return data

    def test_journal_non_utf8_refuse_en_nommant_le_fichier(self) -> None:
        """Tampon courant FROZEN (l'ancrage du diff ne lit pas le journal) : c'est
        la lecture de la FENÊTRE qui rencontre l'octet — le cas mesuré."""
        self._etat_nominal()
        self.assert_pass(self.d.run())                     # contrôle : sain → PASS
        sain = self._corrompre(self.d.log_path)
        data = self._assert_refus_infra(self.d.run(), "VERIFY_STAMP.log")
        # critic-fable T2 : le journal est APPEND-ONLY (`>>` dans `stamp_write`),
        # rejouer la porte n'efface pas l'octet — le remède le dit, pour LUI seul
        # (le tampon courant, réécrit par `mv -f`, ne le porte pas : voir
        # `test_tampon_courant_non_utf8_refuse_en_le_nommant`).
        self.assertIn("APPEND-ONLY, retire la ligne fautive à la main", data["reason"])
        self.assertIn("CE REFUS VAUT POUR CE TOUR", data["reason"])
        self.d.log_path.write_bytes(sain)                  # réparé → PASS de nouveau
        self.assert_pass(self.d.run())

    def test_journal_non_utf8_refuse_aussi_quand_il_ancre_le_diff(self) -> None:
        """Tampon courant `live` : le journal sert AUSSI à l'ancrage du DIFF, lu en
        premier. Même refus, même fichier nommé.

        CE TEST NE PROUVE PAS LE COÛT D2 « même un tour qui n'a rien écrit »,
        qu'il affirmait : il tourne avec `AGENTS.md` MODIFIÉ, donc un tour qui A
        écrit (exec-critic, T-00000695/696). Ce coût est épinglé sur arbre PROPRE
        par `test_cout_D2_journal_illisible_ancre_le_diff_refuse_sur_arbre_propre`."""
        self.d.portes([
            ("frozen", "prev0000", self.m(40)),
            ("frozen", self.d.head, self.m(20)),
            ("live", "livesha0", self.m(5)),
        ])
        self.d.trace("critic-opus", self.m(30))
        self.d.trace("critic-fable", self.m(25))
        self.assert_pass(self.d.run())
        self._corrompre(self.d.log_path)
        self._assert_refus_infra(self.d.run(), "VERIFY_STAMP.log")

    # ---- LE COÛT D2, FAIT TESTÉ ET NON PHRASE ----
    # Arbre suivi PROPRE, AUCUN critique : sain, la garde n'a rien à refuser
    # (contrôle) ; ancrage du diff illisible, elle refuse QUAND MÊME. Les deux cas
    # du commentaire « CE QUE ÇA COÛTE » de la garde, un témoin chacun. Le coût est
    # BORNÉ à UN refus par tour : la relance de l'hôte porte `stop_hook_active` et
    # sort avant toute mesure (`ContratTests.test_stop_hook_active_echappe`).
    # MUTATION QUI LES FAIT ROUGIR : rendre l'ancrage paresseux ou avaler son
    # `Illisible` (retomber sur HEAD) — le tour propre PASSE.

    def test_cout_D2_journal_illisible_ancre_le_diff_refuse_sur_arbre_propre(self) -> None:
        self.d.portes([
            ("frozen", "prev0000", self.m(40)),
            ("frozen", self.d.head, self.m(20)),
            ("live", "livesha0", self.m(5)),       # le journal ANCRE le diff
        ])
        self.d.arbre_propre()
        self.assertTrue(self.d.arbre_suivi_est_propre())
        self.assert_pass(self.d.run())             # contrôle : rien d'écrit, rien à refuser
        self._corrompre(self.d.log_path)
        self._assert_refus_infra(self.d.run(), "VERIFY_STAMP.log")
        self.assertTrue(self.d.arbre_suivi_est_propre(), "toujours RIEN d'écrit")

    def test_cout_D2_tampon_courant_illisible_refuse_sur_arbre_propre(self) -> None:
        self.d.portes([
            ("frozen", "prev0000", self.m(40)),
            ("frozen", self.d.head, self.m(20)),   # tampon courant FROZEN, sain
        ])
        self.d.arbre_propre()
        self.assertTrue(self.d.arbre_suivi_est_propre())
        self.assert_pass(self.d.run())             # contrôle : rien d'écrit, rien à refuser
        self._corrompre(self.d.stamp_path)
        data = self._assert_refus_infra(self.d.run(), "VERIFY_STAMP")
        self.assertNotIn("VERIFY_STAMP.log", data["reason"],
                         "c'est le tampon COURANT qui manque, pas le journal")
        self.assertTrue(self.d.arbre_suivi_est_propre(), "toujours RIEN d'écrit")

    # ---- sortie NON HONORÉE, chemin de PANNE (exec-critic, T-00000695/696) ----
    def test_journal_non_inscriptible_sortie_non_honoree_en_panne(self) -> None:
        """Le même défaut que sur le chemin ordinaire, par `_refus_de_panne` : une
        sortie qui ne peut pas être journalisée n'est PAS honorée — REFUS
        d'infrastructure qui le dit et NOMME le journal des sorties, sortie encore
        présente, et au tour suivant toujours REFUS. Variante « répertoire » : ne
        dépend pas de l'uid. CONTRÔLE : journal réparé ⇒ la sortie franchit la
        panne, consommée et journalisée avec le fichier en cause. MUTATION : le
        `try` unique d'avant — le premier tour PASSE, rouge."""
        self.d.portes([
            ("frozen", "prev0000", self.m(40)),
            ("frozen", self.d.head, self.m(20)),
            ("live", "livesha0", self.m(5)),
        ])
        self._corrompre(self.d.log_path)
        self._assert_refus_infra(self.d.run(), "VERIFY_STAMP.log")    # contrôle armé
        self.d.journal_sorties.mkdir()
        self.d.sortie_tracee("journal corrompu, reparation en cours\n")
        for tour in (1, 2):
            data = self._assert_refus_infra(self.d.run(), "VERIFY_STAMP.log")
            self.assertIn("NON HONORÉE", data["reason"], f"tour {tour}")
            self.assertIn("affirmation-sorties.log", data["reason"],
                          "le journal des sorties est NOMMÉ")
            self.assertTrue(self.d.sortie_path.exists(), f"tour {tour} : non consommée")
        self.d.journal_sorties.rmdir()
        self.assert_pass(self.d.run())
        self.assertFalse(self.d.sortie_path.exists())
        self.assertIn("VERIFY_STAMP.log",
                      self.d.journal_sorties.read_text(encoding="utf-8"))

    def test_tampon_courant_non_utf8_refuse_en_le_nommant(self) -> None:
        self._etat_nominal()
        self.assert_pass(self.d.run())
        self._corrompre(self.d.stamp_path)
        data = self._assert_refus_infra(self.d.run(), "VERIFY_STAMP")
        self.assertIn("  .agents/state/local/VERIFY_STAMP\n", data["reason"],
                      "le chemin RELATIF du tampon courant, sur sa propre ligne")
        self.assertNotIn("VERIFY_STAMP.log", data["reason"],
                         "c'est le tampon COURANT qui est nommé, pas le journal")
        self.assertNotIn("APPEND-ONLY", data["reason"],
                         "le tampon courant est RÉÉCRIT par la porte : pas ce remède-là")

    def test_trace_non_utf8_refuse_en_nommant_la_trace(self) -> None:
        self._etat_nominal()
        self.assert_pass(self.d.run())
        trace = self.d.dir / ".agents/state/local/binome/T-00000602.critic-fable.json"
        self._corrompre(trace)
        self._assert_refus_infra(self.d.run(), "T-00000602.critic-fable.json")

    def test_desarmee_ne_lit_rien_et_ne_refuse_rien(self) -> None:
        """LA BORNE DE D2, écrite pour ne pas être relue comme universelle : ce
        refus n'existe que garde ARMÉE. Désarmée, elle ne lit ni tampon, ni
        journal, ni trace — 0 octet, même sur une infrastructure illisible."""
        self._etat_nominal()
        self._corrompre(self.d.log_path)
        self._assert_refus_infra(self.d.run(), "VERIFY_STAMP.log")   # contrôle armé
        self.d.desarmer()
        r = self.d.run()
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout, "", f"désarmée = 0 octet, reçu : {r.stdout!r}")

    def test_la_sortie_tracee_franchit_une_infra_illisible(self) -> None:
        """LE REMÈDE NOMMÉ DOIT ÊTRE VRAI. Le refus d'infrastructure cite
        `AFFIRMATION_SANS_BINOME` ; elle doit donc FRANCHIR ce refus, être
        consommée une fois et journalisée avec le fichier en cause — sans quoi
        le message promettrait une sortie qui n'existe pas (L-00000111)."""
        self.d.portes([
            ("frozen", "prev0000", self.m(40)),
            ("frozen", self.d.head, self.m(20)),
            ("live", "livesha0", self.m(5)),
        ])
        self._corrompre(self.d.log_path)
        self._assert_refus_infra(self.d.run(), "VERIFY_STAMP.log")
        self.d.sortie_tracee("journal corrompu, reparation en cours\n")
        self.assert_pass(self.d.run())
        self.assertFalse(
            (self.d.dir / ".agents/state/gates/AFFIRMATION_SANS_BINOME").exists(),
            "la sortie doit être CONSOMMÉE")
        journal = (self.d.dir / ".agents/state/local/affirmation-sorties.log"
                   ).read_text(encoding="utf-8")
        self.assertIn("VERIFY_STAMP.log", journal)
        self.assertIn("reparation en cours", journal)
        self._assert_refus_infra(self.d.run(), "VERIFY_STAMP.log")   # une fois

    def test_un_plantage_hors_infrastructure_refuse_aussi(self) -> None:
        """LA CLASSE, PAS L'INSTANCE : n'importe quel plantage de la garde armée
        rendait exit 0 et un stdout vide. Ici, le board COMMITÉ au sha du tampon
        porte un `id` NON HACHABLE (une liste) : `git show` le rend, et
        `taches_ajoutees` lève `TypeError` en le rangeant dans un ensemble — hors
        de toute lecture d'infrastructure. Refus générique : la garde dit qu'elle
        n'a pas pu mesurer et nomme l'exception. CONTRÔLE : board commité sain →
        comportement nominal (PASS). MUTATION : retirer `sys.excepthook =
        _refus_de_panne` — stdout vide, rouge.

        L'INSTANCE A CHANGÉ, ET C'EST UN CORRECTIF QUI L'A RETIRÉE (critic-opus T3,
        T-00000695/696). Ce témoin plantait sur un octet non UTF-8 du board commité,
        décodé par `git()` dans la locale ; `git()` décode désormais en UTF-8 avec
        remplacement, donc cette instance ne plante PLUS — elle PASSE, et c'est
        épinglé ci-dessous. Sans nouvelle instance, la branche générique de
        `_refus_de_panne` n'avait plus un seul témoin."""
        board = self.d._sous(".agents", "state", "board", "TASKS.json")

        def committer(contenu: bytes) -> str:
            board.write_bytes(contenu)
            self.d._git("add", ".agents/state/board/TASKS.json")
            self.d._git("commit", "-q", "-m", "board")
            return self.d._git("rev-parse", "HEAD").strip()

        def armer_cycle(sha: str) -> None:
            self.d.portes([
                ("frozen", "prev0000", self.m(40)),
                ("frozen", sha, self.m(20)),
            ])
            # Le board vivant est SAIN et n'ajoute rien : seule la lecture de la
            # version COMMITÉE peut planter.
            board.write_bytes(b'{"tasks":[{"id":"T-001"}]}\n')

        self.d.trace("critic-opus", self.m(30))
        self.d.trace("critic-fable", self.m(25))
        armer_cycle(committer(b'{"tasks":[{"id":"T-001"}]}\n'))
        self.assert_pass(self.d.run())                       # contrôle sain

        # L'ancienne instance : un octet non UTF-8 dans la version commitée ne
        # fait plus planter la mesure (U+FFFD), la garde PASSE.
        armer_cycle(committer(b'{"tasks":[{"id":"T-001","t":"' + OCTET_NON_UTF8 + b'"}]}\n'))
        self.assert_pass(self.d.run())

        armer_cycle(committer(b'{"tasks":[{"id":["T-001"]}]}\n'))
        data = self.assert_block(self.d.run())
        self.assertIn(self.PHRASE_INFRA, data["reason"], data["reason"])
        self.assertIn("Elle a planté pendant sa mesure", data["reason"], data["reason"])
        self.assertIn("TypeError", data["reason"], data["reason"])


class PariteJumellesTests(_Base):
    """D1 = A (S-00001884) — « UNE SEULE définition de "cycle précédent" dans le
    dépôt ». Le hook RECOPIE `tasks.py::cycle_precedent` ; jusqu'ici RIEN ne
    reliait les deux copies (exec-critic, T-00000695/696) : chaque filtre avait
    son témoin d'un seul côté, et la mutation « dernière borne » restait verte
    des DEUX côtés.

    CE QUE CE BANC FAIT : pour chaque journal, `cycle_precedent` est APPELÉE
    (module chargé par chemin) sur le dépôt fabriqué, et la garde est SONDÉE sur
    le MÊME `VERIFY_STAMP.log` — toujours en sous-processus, jamais par import
    de son python embarqué. Le hook ne publie pas sa borne ; on la lit par son
    COMPORTEMENT, à la seconde près (seule résolution du format) :
      · borne B de la jumelle ⇒ deux critiques À B sont REFUSÉS (`quand > borne`
        est strict) et deux critiques à B + 1 s PASSENT — donc la borne de la
        garde vaut EXACTEMENT B ;
      · pas de borne (None) ⇒ deux critiques une minute AVANT le plus ancien vert
        PASSENT (aucun vert ne borne la garde) et deux critiques à -13 h sont
        REFUSÉS (c'est la fenêtre de 12 h, pas une garde muette). CE BRAS N'EST
        PAS UNE PARITÉ : c'est une DIVERGENCE CONNUE ET ASSUMÉE entre les deux
        jumelles (décision pilote par défaut du 23/09). Sur None, la garde
        retombe sur 12 h ; `done` borne l'emprunt à 24 h depuis T-00000846
        (avant : aucune fenêtre, un emprunt n'y expirait pas) — deux fenêtres
        différentes. Le bras épingle le côté GARDE : qu'elle quitte ses 12 h sur
        None, il rougit. Le côté `done` lui échappe : il n'appelle que
        `cycle_precedent`, jamais `binome_preuve`, où `done` traite None.

    LES JOURNAUX COUVRENT LES QUATRE FILTRES — `mode`, `at`, sha consécutif
    (première borne), moins de deux cycles — plus le tampon courant hors journal
    (la jumelle ne lit que le journal). MUTATIONS QUI LE FONT ROUGIR, sur L'UNE
    OU L'AUTRE jumelle : « dernière borne », « `unknown` gardé », « un vert rend
    ce vert », tampon courant ré-ajouté.

    BORNE ÉCRITE (exec-critic) : ce banc est DIFFÉRENTIEL. Une dérive CONJOINTE
    des deux jumelles laisse ce test vert ; la règle PREMIÈRE borne n'a de témoin
    absolu que `test_3quinquies`, côté garde."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tasks = _charger_tasks()

    @staticmethod
    def _ligne(mode, sha, at) -> str:
        brut = at if isinstance(at, str) else _iso(at)
        return f"at={brut}\tsha={sha}\tmode={mode}\n"

    def _journaux(self):
        L, m, head = self._ligne, self.m, self.d.head
        return (
            ("nominal", L("frozen", "prev0000", m(40)) + L("frozen", head, m(20)),
             ("frozen", head, m(20))),
            ("mode : live écarté",
             L("frozen", "green001", m(60)) + L("frozen", "green002", m(40))
             + L("live", "livesha0", m(5)),
             ("live", "livesha0", m(5))),
            ("mode : champ absent écarté",
             L("frozen", "green001", m(60)) + f"at={_iso(m(50))}\tsha=nomode00\n"
             + L("frozen", head, m(20)),
             ("frozen", head, m(20))),
            ("at : unknown et vide écartés",
             L("frozen", "green001", m(40)) + L("frozen", "green002", "unknown")
             + L("frozen", "green003", "") + L("frozen", head, m(20)),
             ("frozen", head, m(20))),
            ("sha : rejeu, PREMIÈRE borne",
             L("frozen", "green001", m(60)) + L("frozen", "green002", m(40))
             + L("frozen", "green002", m(35)) + L("frozen", head, m(20)),
             ("frozen", head, m(20))),
            ("sha : rejeu de part et d'autre d'un live",
             L("frozen", "green001", m(60)) + L("frozen", "green002", m(40))
             + L("live", "livesha0", m(38)) + L("frozen", "green002", m(35))
             + L("frozen", head, m(20)),
             ("frozen", head, m(20))),
            ("sha : non consécutif = deux cycles",
             L("frozen", "green001", m(60)) + L("frozen", "green002", m(40))
             + L("frozen", "green001", m(30)) + L("frozen", head, m(20)),
             ("frozen", head, m(20))),
            ("moins de deux cycles : un seul vert", L("frozen", head, m(30)),
             ("frozen", head, m(30))),
            ("moins de deux cycles : première porte rejouée",
             L("frozen", head, m(40)) + L("frozen", head, m(20)),
             ("frozen", head, m(20))),
            ("journal de lignes blanches, sans tampon", "\n\n", None),
            ("tampon courant hors journal",
             L("frozen", "green001", m(40)) + L("frozen", "green002", m(20)),
             ("frozen", head, m(5))),
        )

    def _deux_critiques(self, at: datetime) -> None:
        self.d.vider_traces()
        self.d.trace("critic-opus", at)
        self.d.trace("critic-fable", at)

    def _verdict(self) -> str:
        r = self.d.run()
        self.assertEqual(r.returncode, 0, r.stderr)
        return "REFUS" if r.stdout.strip() else "PASS"

    def test_meme_journal_meme_borne(self) -> None:
        for nom, journal, courant in self._journaux():
            with self.subTest(journal=nom):
                self.d.log_path.write_text(journal, encoding="utf-8")
                if courant is None:
                    self.d.stamp_path.unlink(missing_ok=True)
                else:
                    self.d.stamp(*courant)
                borne = self.tasks.cycle_precedent(str(self.d.dir))
                if borne is None:
                    ats = [datetime.strptime(c[3:], "%Y-%m-%dT%H:%M:%SZ").replace(
                        tzinfo=timezone.utc)
                        for l in journal.splitlines() for c in l.split("\t")
                        if c.startswith("at=") and c[3:].endswith("Z")]
                    avant_tout = (min(ats) if ats else self.m(60)) - timedelta(minutes=1)
                    self._deux_critiques(avant_tout)
                    self.assertEqual(
                        "PASS", self._verdict(),
                        f"jumelle : PAS de borne ; la garde, elle, borne après {_iso(avant_tout)}")
                    # DIVERGENCE CONNUE ET ASSUMÉE, PAS UNE PARITÉ (décision pilote
                    # par défaut du 23/09) : la jumelle rend None et `done` borne
                    # alors l'emprunt à 24 h (T-00000846 ; avant, aucune fenêtre) ;
                    # la garde, elle, retombe sur 12 h. On épingle cet écart tel quel.
                    self._deux_critiques(self.h(13))
                    self.assertEqual(
                        "REFUS", self._verdict(),
                        "sans borne, la garde doit rester à 12 h — DIVERGENCE "
                        "CONNUE ET ASSUMÉE avec `done` (24 h sur l'emprunt sur None), "
                        "décision pilote par défaut du 23/09, pas une parité")
                    continue
                try:
                    b = datetime.strptime(borne, "%Y-%m-%dT%H:%M:%SZ").replace(
                        tzinfo=timezone.utc)
                except ValueError:
                    self.fail(f"cycle_precedent rend une borne NON DATÉE : {borne!r}")
                self._deux_critiques(b)
                self.assertEqual(
                    "REFUS", self._verdict(),
                    f"jumelle : borne {borne} ; la garde compte une trace À cette "
                    "borne, donc la sienne est plus ANCIENNE (ou absente)")
                self._deux_critiques(b + timedelta(seconds=1))
                self.assertEqual(
                    "PASS", self._verdict(),
                    f"jumelle : borne {borne} ; la garde refuse une trace UNE seconde "
                    "après, donc la sienne est plus RÉCENTE")


#: Les fichiers de reprise de lot des scénarios R (T-00001064).
LOTS_E99 = "docs/interne/chantier/lots/LOT-E99-REPRISE.md"
LOTS_E98 = "docs/interne/chantier/lots/LOT-E98-REPRISE.md"
LOTS_E97 = "docs/interne/chantier/lots/LOT-E97-REPRISE.md"
LOTS_E1_LEURRE = "docs/interne/chantier/lots/LOT-E1-REPRISE.md"
TASKS_E97 = "docs/tasks/LOT-E97-REPRISE.md"
PROMPT_VIVANT = "docs/interne/chantier/reprises/prompt_de_reprise_et_planification.md"
ARCHIVE_P10 = "docs/interne/chantier/reprises/REPRISE-P10.md"
PLAN_T1 = "docs/tasks/T-00000001-plan.md"
SYNC_TEMPLATE = ROOT / ".agents" / "bin" / "sync_template.py"

#: Les ANCRES des mutants de la jambe « reprise », copiées VERBATIM de la garde ;
#: `_garde_variante` exige chacune présente UNE fois exactement.
_M_LOTS = '    "docs/interne/chantier/lots/*",\n'
_M_PROMPT = '    "docs/interne/chantier/reprises/prompt_de_reprise_et_planification.md",\n'
_M_TASKS = '    "docs/tasks/LOT-*-REPRISE.md",\n'
_M_TUPLE = "REPRISES = (\n" + _M_LOTS + _M_PROMPT + _M_TASKS + ")\n"
_M_SUIVIS = (
    '    sortie = git("-c", "core.quotePath=false", "diff", "-z", "--name-only", BASE,\n'
    '                 "--", *SPEC)\n'
    '    if sortie is None and BASE != "HEAD":\n'
    '        sortie = git("-c", "core.quotePath=false", "diff", "-z", "--name-only",\n'
    '                     "HEAD", "--", *SPEC)\n'
    '    if sortie is None:\n'
    '        return set()\n'
    '    return {c for c in sortie.split("\\0") if c}\n')
_M_REPLI_SUIVIS = ('    if sortie is None:\n        return set()\n'
                   '    return {c for c in sortie.split("\\0") if c}\n\n\ndef non_suivis')


def _suivis_par_lignes(*options: str) -> str:
    """Le corps de `suivis_reprise` SANS `-z`, découpé sur les LIGNES, avec
    `options` en tête de l'appel git (MUT-10a : aucune ; MUT-10b : la seule
    `-c core.quotePath=false`)."""
    o = "".join(f'"{x}", ' for x in options)
    return (f'    sortie = git({o}"diff", "--name-only", BASE, "--", *SPEC)\n'
            '    if sortie is None and BASE != "HEAD":\n'
            f'        sortie = git({o}"diff", "--name-only", "HEAD", "--", *SPEC)\n'
            '    if sortie is None:\n'
            '        return set()\n'
            '    return {l.strip() for l in sortie.splitlines() if l.strip()}\n')


class RepriseTests(_Base):
    """La 4e surface de la garde : les FICHIERS DE REPRISE DE LOT (T-00001064,
    S-00003374) — motifs `REPRISES`, non suivis compris, lus par une jambe PROPRE
    (`suivis_reprise`, `non_suivis`), jamais par `modifies()`.

    Chaque scénario rend `block` ou `pass` pour un `hook=` donné ; le MÊME
    scénario joue la garde réelle puis ses mutants (`_garde_variante`, ancre
    présente UNE fois exactement), et chaque mutant rend l'AUTRE issue sur le
    scénario nommé (`test_mutants_rendent_l_autre_issue`) :
      MUT-1 `REPRISES = ()` → R1-R4, R3', R9, R11a, R11b ; MUT-2 `lots/*` →
      `docs/interne/chantier/*` → R5 ; MUT-3 `non_suivis()` → `set()` → R3, R3',
      R4 ; MUT-4 motif du prompt retiré → R2 ; MUT-5 motif `docs/LOT-*-REPRISE.md`
      ajouté → R7 ; MUT-6 filtre d'existence retiré → R8 ; MUT-7 sortie « deux
      critiques » court-circuitée → R6 ; MUT-8 `docs/tasks/LOT-*-REPRISE.md` →
      `docs/tasks/*` → R5 ; MUT-9 repli `None → set()` remplacé par l'advisory →
      R10 ; MUT-10a l'appel revient à `diff --name-only` (ni `-z` ni `-c`), découpé
      sur les lignes → R11a ET R11b ; MUT-10b `-z` seul retiré → R11b ; MUT-11
      `-c core.excludesFile` retiré de `non_suivis()` → R3'.
    MUTANT ÉQUIVALENT, DÉCLARÉ ET NON COMPTÉ (M13) : retirer le SEUL
    `-c core.quotePath=false` ne change rien, `-z` porte déjà la correction.
    Mutant du BANC (MUT-F, joué hors de ce fichier sur une copie) : retirer
    `-c core.excludesFile` de `_Depot.valider` fait rougir R3' (le leurre suivi
    n'est plus indexé sous l'ignore personnel).
    """

    # ---- outillage des scénarios ------------------------------------------
    def _depot(self) -> _Depot:
        d = _Depot()
        self.addCleanup(d.cleanup)
        d.arbre_propre()
        return d

    @staticmethod
    def _portes(d: _Depot) -> None:
        """Deux verts : la fenêtre des critiques part du premier, le diff de HEAD."""
        d.portes([("frozen", "prev0000", d.now - timedelta(minutes=40)),
                  ("frozen", d.head, d.now - timedelta(minutes=20))])

    @staticmethod
    def _ecrire(d: _Depot, chemin: str, texte: str) -> None:
        d._sous(*chemin.split("/")).write_text(texte, encoding="utf-8")

    def _verdict(self, d: _Depot, hook: Path | None,
                 en_plus: dict | None = None) -> tuple[str, str]:
        r = d.run(hook=hook, en_plus=en_plus)
        self.assertEqual(r.returncode, 0, f"rc={r.returncode}, stderr={r.stderr!r}")
        out = r.stdout.strip()
        if not out:
            return "pass", ""
        data = json.loads(out)
        self.assertEqual(data.get("decision"), "block", out)
        return "block", data["reason"]

    def _ignore_personnel(self) -> dict:
        """HOME et XDG_CONFIG_HOME JETABLES dont `git/ignore` porte `LOT-*` et
        `lots/`, une config globale jetable qui y pointe `core.excludesFile`, et
        la config système coupée : l'environnement de R3' (M21, B-C2)."""
        base = Path(tempfile.mkdtemp(prefix="affguard-home-"))
        self.addCleanup(shutil.rmtree, base, True)
        (base / "home").mkdir()
        ignore = base / "xdg" / "git" / "ignore"
        ignore.parent.mkdir(parents=True)
        ignore.write_text("LOT-*\nlots/\n", encoding="utf-8")
        globale = base / "gitconfig"
        globale.write_text(f"[core]\n\texcludesFile = {ignore.as_posix()}\n",
                           encoding="utf-8")
        return {"HOME": str(base / "home"), "XDG_CONFIG_HOME": str(base / "xdg"),
                "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": str(globale)}

    def _garde_mutee(self, *paires: tuple[str, str]) -> Path:
        """Une copie de la garde où CHAQUE ancre (présente une fois exactement)
        est remplacée : la première par `_garde_variante`, les suivantes sur la
        copie, sous la même exigence d'unicité."""
        dossier = Path(tempfile.mkdtemp(prefix="affguard-mutant-"))
        self.addCleanup(shutil.rmtree, dossier, True)
        copie = _garde_variante(dossier, *paires[0])
        texte = copie.read_text(encoding="utf-8")
        for ancre, remplacement in paires[1:]:
            self.assertEqual(texte.count(ancre), 1, f"ancre ambiguë ou absente : {ancre!r}")
            texte = texte.replace(ancre, remplacement)
        copie.write_text(texte, encoding="utf-8")
        return copie

    # ---- scénarios (chacun crée son dépôt) ----------------------------------
    def _r1(self, hook=None):
        """R1 — `lots/LOT-E99-REPRISE.md` commité, puis sali."""
        d = self._depot()
        d.valider({LOTS_E99: "reprise\n"})
        self._portes(d)
        self._ecrire(d, LOTS_E99, "reprise\nligne du lot\n")
        return self._verdict(d, hook)

    def _r2(self, hook=None):
        """R2 — le prompt VIVANT de `reprises/` commité, puis sali."""
        d = self._depot()
        d.valider({PROMPT_VIVANT: "prompt\n"})
        self._portes(d)
        self._ecrire(d, PROMPT_VIVANT, "prompt\nligne\n")
        return self._verdict(d, hook)

    def _r3(self, hook=None):
        """R3 — `lots/LOT-E98-REPRISE.md` NEUF, non suivi."""
        d = self._depot()
        self._portes(d)
        self._ecrire(d, LOTS_E98, "reprise neuve\n")
        return self._verdict(d, hook)

    def _r3prime(self, hook=None):
        """R3' — R3 sous un ignore PERSONNEL qui cache `LOT-*` et `lots/`, avec un
        leurre SUIVI commité par `valider` sous ce même environnement."""
        d = self._depot()
        env = self._ignore_personnel()
        d.valider({LOTS_E1_LEURRE: "leurre suivi\n"}, env)
        self._portes(d)
        self._ecrire(d, LOTS_E98, "reprise neuve\n")
        sonde = subprocess.run(
            ["git", "-C", str(d.dir), "ls-files", "--others", "--exclude-standard",
             "--", "docs/interne/chantier/lots"],
            capture_output=True, text=True, check=False, env=_env(**env))
        self.assertNotIn("LOT-E98", sonde.stdout,
                         "SONDE : l'ignore personnel ne cache rien — R3' serait vacant")
        return self._verdict(d, hook, env)

    def test_R12_le_repli_sur_HEAD_quand_le_sha_du_tampon_est_inatteignable(self) -> None:
        """R12 — le tampon pointe un sha ABSENT du dépôt (gc, clone, réécriture) :
        `git diff <sha>` rend 128 ; la jambe se replie sur HEAD, comme `modifies()`,
        et VOIT la reprise salie. Sans ce repli elle se tairait (borne 4) et aucun
        autre témoin de la classe ne le dirait."""
        d = self._depot()
        d.valider({LOTS_E99: "reprise\n"})
        d.portes([("frozen", "prev0000", d.now - timedelta(minutes=40)),
                  ("frozen", "f" * 40, d.now - timedelta(minutes=20))])
        self._ecrire(d, LOTS_E99, "reprise\nligne du lot\n")
        statut, raison = self._verdict(d, None)
        self.assertEqual("block", statut, raison)
        self.assertIn("LOT-E99-REPRISE.md", raison)

    def _r4(self, hook=None):
        """R4 — `docs/tasks/LOT-E97-REPRISE.md` NEUF, non suivi (le motif qui voyage)."""
        d = self._depot()
        self._portes(d)
        self._ecrire(d, TASKS_E97, "reprise neuve\n")
        return self._verdict(d, hook)

    def _r5(self, hook=None, sous_cas="archive", controle=False):
        """R5 — ce qui n'est PAS un fichier de reprise ne fait pas mordre : archive
        de `reprises/` salie, plan sali, plan NEUF (R5bis), note neuve sous
        `docs/interne/chantier/` hors `lots/`. `controle` : la même scène plus une
        reprise neuve — le refus prouve la garde ARMÉE sur cet état."""
        d = self._depot()
        d.valider({ARCHIVE_P10: "archive\n", PLAN_T1: "plan\n"})
        self._portes(d)
        cible, texte = {
            "archive": (ARCHIVE_P10, "archive\nretouche\n"),
            "plan_sale": (PLAN_T1, "plan\nretouche\n"),
            "plan_neuf": ("docs/tasks/T-00000002-plan.md", "plan neuf\n"),
            "note_chantier": ("docs/interne/chantier/NOTE.md", "note\n"),
        }[sous_cas]
        self._ecrire(d, cible, texte)
        if controle:
            self._ecrire(d, LOTS_E98, "reprise neuve\n")
        return self._verdict(d, hook)

    def _r6(self, hook=None):
        """R6 — R1 plus deux critiques frais : zéro octet."""
        d = self._depot()
        d.valider({LOTS_E99: "reprise\n"})
        self._portes(d)
        self._ecrire(d, LOTS_E99, "reprise\nligne du lot\n")
        d.trace("critic-opus", d.now - timedelta(minutes=30))
        d.trace("critic-fable", d.now - timedelta(minutes=30))
        return self._verdict(d, hook)

    def _r8(self, hook=None):
        """R8 — reprise commitée avant le tampon, puis `git rm` + commit : zéro octet."""
        d = self._depot()
        d.valider({LOTS_E99: "reprise\n"})
        self._portes(d)
        d._git("rm", "-q", "--", LOTS_E99)
        d._git("commit", "-q", "-m", "retrait")
        self.assertFalse((d.dir / LOTS_E99).exists())
        return self._verdict(d, hook)

    def _r9(self, hook=None):
        """R9 — `git mv` de `docs/tasks/LOT-E97-REPRISE.md` vers `lots/`, plus une
        ligne : le refus cite le NOUVEAU chemin seul."""
        d = self._depot()
        d.valider({TASKS_E97: "reprise\n"})
        self._portes(d)
        d._sous(*LOTS_E97.split("/"))
        d._git("mv", TASKS_E97, LOTS_E97)
        self._ecrire(d, LOTS_E97, "reprise\nligne\n")
        return self._verdict(d, hook)

    def _r10(self, hook=None):
        """R10 — `PLAN-ETAT.md` sali ET une reprise neuve ; joué sur une copie où le
        diff et le `ls-files` de la jambe sont INVALIDES (borne 4)."""
        d = self._depot()
        d.valider({"PLAN-ETAT.md": "routeur\n"})
        self._portes(d)
        self._ecrire(d, "PLAN-ETAT.md", "routeur\nligne\n")
        self._ecrire(d, LOTS_E98, "reprise neuve\n")
        return self._verdict(d, hook)

    def _r11(self, hook=None, nom="LOT-É25 REPRISE.md"):
        """R11a/R11b — une reprise au nom NON ASCII ou à GUILLEMETS, COMMITÉE après
        le tampon : git la CITE sans `-z`."""
        d = self._depot()
        self._portes(d)
        d.valider({f"docs/interne/chantier/lots/{nom}": "reprise\n"})
        return self._verdict(d, hook)

    def _r7(self, hook: Path) -> list:
        """R7 — les motifs extraits de la garde par `ast.literal_eval` : trois
        exactement ; chacun a une règle `.template-exclude` (jamais None) ; `strip`
        pour `docs/interne/`, `keep` pour `docs/tasks/`. MESURÉ sur le
        `.template-exclude` de la branche ; l'effet sur `main` est ASSUMÉ."""
        texte = hook.read_text(encoding="utf-8")
        m = re.search(r"^REPRISES = (\([^)]*\))", texte, re.M)
        motifs = ast.literal_eval(m.group(1)) if m else ()
        fautes = [] if len(motifs) == 3 else [f"{len(motifs)} motif(s), 3 attendus"]
        spec = importlib.util.spec_from_file_location("sync_template_r7", SYNC_TEMPLATE)
        assert spec is not None and spec.loader is not None, SYNC_TEMPLATE
        st = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = st
        spec.loader.exec_module(st)
        regles = st.parse_exclude((ROOT / ".template-exclude").read_text(encoding="utf-8"))
        for motif in motifs:
            regle = st.match_rule(motif.replace("*", "E99"), regles)
            attendu = "keep" if motif.startswith("docs/tasks/") else "strip"
            if regle is None or regle.polarity != attendu:
                fautes.append(f"{motif} → {regle and regle.raw!r}, attendu {attendu}")
        return fautes

    # ---- la garde réelle ------------------------------------------------------
    def test_R1_reprise_suivie_salie_bloque(self) -> None:
        v, raison = self._r1()
        self.assertEqual(v, "block")
        self.assertIn(LOTS_E99, raison)

    def test_R2_prompt_vivant_sali_bloque(self) -> None:
        v, raison = self._r2()
        self.assertEqual(v, "block")
        self.assertIn(PROMPT_VIVANT, raison)

    def test_R3_reprise_neuve_non_suivie_bloque(self) -> None:
        v, raison = self._r3()
        self.assertEqual(v, "block")
        self.assertIn(LOTS_E98, raison)

    def test_R3prime_ignore_personnel_neutralise(self) -> None:
        v, raison = self._r3prime()
        self.assertEqual(v, "block")
        self.assertIn(LOTS_E98, raison)

    def test_R4_reprise_neuve_sous_docs_tasks_bloque(self) -> None:
        v, raison = self._r4()
        self.assertEqual(v, "block")
        self.assertIn(TASKS_E97, raison)

    def test_R5_ce_qui_n_est_pas_une_reprise_ne_mord_pas(self) -> None:
        for sous_cas in ("archive", "plan_sale", "plan_neuf", "note_chantier"):
            with self.subTest(sous_cas=sous_cas):
                self.assertEqual(self._r5(sous_cas=sous_cas)[0], "pass")
                self.assertEqual(self._r5(sous_cas=sous_cas, controle=True)[0], "block",
                                 "contrôle armé : la même scène plus une reprise neuve")

    def test_R6_deux_critiques_frais_zero_octet(self) -> None:
        self.assertEqual(self._r6()[0], "pass")
        self.assertEqual(self._r1()[0], "block", "contrôle armé : R6 sans les critiques")

    def test_R7_motifs_portee_et_template_exclude(self) -> None:
        self.assertEqual(self._r7(HOOK), [])

    def test_R8_reprise_supprimee_n_est_pas_citee(self) -> None:
        self.assertEqual(self._r8()[0], "pass")

    def test_R9_renommage_cite_le_nouveau_chemin_seul(self) -> None:
        v, raison = self._r9()
        self.assertEqual(v, "block")
        self.assertIn(LOTS_E97, raison)
        self.assertNotIn(TASKS_E97, raison)

    def test_R10_jambe_muette_sur_git_en_echec_plan_etat_survit(self) -> None:
        v, raison = self._r10()
        self.assertEqual(v, "block")
        self.assertIn(LOTS_E98, raison, "garde réelle : la reprise neuve est citée")
        invalide = self._garde_mutee(
            ("for p in REPRISES})", 'for p in REPRISES} | {":(invalide)x"})'))
        v, raison = self._r10(invalide)
        self.assertEqual(v, "block", "la jambe PLAN-ETAT doit survivre à la panne")
        self.assertIn("PLAN-ETAT.md", raison)
        self.assertNotIn(LOTS_E98, raison, "BORNE 4 : la jambe reprise est MUETTE")

    def test_R11a_nom_non_ascii_commite_vu_tel_quel(self) -> None:
        v, raison = self._r11(nom="LOT-É25 REPRISE.md")
        self.assertEqual(v, "block")
        self.assertIn("docs/interne/chantier/lots/LOT-É25 REPRISE.md", raison)

    @unittest.skipUnless(os.name != "nt", "le guillemet est interdit dans un nom NTFS")
    def test_R11b_nom_a_guillemets_commite_vu(self) -> None:
        v, raison = self._r11(nom='LOT-E26 "x".md')
        self.assertEqual(v, "block")
        self.assertIn('LOT-E26 "x".md', raison)

    # ---- les mutants : chacun rend l'AUTRE issue sur son scénario --------------
    def test_mutants_rendent_l_autre_issue(self) -> None:
        guillemet = [] if os.name == "nt" else [(self._r11, {"nom": 'LOT-E26 "x".md'}, "pass")]
        r11a = [(self._r11, {"nom": "LOT-É25 REPRISE.md"}, "pass")]
        mutants = (
            ("MUT-1", [(_M_TUPLE, "REPRISES = ()\n")],
             [(self._r1, {}, "pass"), (self._r2, {}, "pass"), (self._r3, {}, "pass"),
              (self._r3prime, {}, "pass"), (self._r4, {}, "pass"), (self._r9, {}, "pass")]
             + r11a + guillemet),
            ("MUT-2", [(_M_LOTS, '    "docs/interne/chantier/*",\n')],
             [(self._r5, {"sous_cas": "archive"}, "block"),
              (self._r5, {"sous_cas": "note_chantier"}, "block")]),
            ("MUT-3", [("sorted(suivis_reprise() | non_suivis())",
                        "sorted(suivis_reprise() | set())")],
             [(self._r3, {}, "pass"), (self._r3prime, {}, "pass"), (self._r4, {}, "pass")]),
            ("MUT-4", [(_M_PROMPT, "")], [(self._r2, {}, "pass")]),
            ("MUT-6", [("            and os.path.isfile(os.path.join(RACINE, chemin))):",
                        "            and True):")],
             [(self._r8, {}, "block")]),
            ("MUT-7", [("if len(vus) >= BINOME_MIN:\n", "if False:\n")], [(self._r6, {}, "block")]),
            ("MUT-8", [(_M_TASKS, '    "docs/tasks/*",\n')],
             [(self._r5, {"sous_cas": "plan_sale"}, "block"),
              (self._r5, {"sous_cas": "plan_neuf"}, "block")]),
            ("MUT-9", [("for p in REPRISES})", 'for p in REPRISES} | {":(invalide)x"})'),
                       (_M_REPLI_SUIVIS, _M_REPLI_SUIVIS.replace("return set()", "sortir()"))],
             [(self._r10, {}, "pass")]),
            ("MUT-10a", [(_M_SUIVIS, _suivis_par_lignes())], r11a + guillemet),
            ("MUT-10b", [(_M_SUIVIS, _suivis_par_lignes("-c", "core.quotePath=false"))],
             guillemet),
            ("MUT-11", [('"-c", "core.excludesFile=" + os.devnull, ', "")],
             [(self._r3prime, {}, "pass")]),
        )
        for nom, paires, cibles in mutants:
            hook = self._garde_mutee(*paires)
            for scenario, kw, attendu in cibles:
                with self.subTest(mutant=nom, scenario=scenario.__name__, **kw):
                    self.assertEqual(scenario(hook, **kw)[0], attendu,
                                     f"{nom} doit rendre « {attendu} » sur {scenario.__name__}")

    def test_MUT5_motif_ajoute_rougit_R7(self) -> None:
        hook = self._garde_mutee(
            (_M_TASKS, _M_TASKS + '    "docs/LOT-*-REPRISE.md",\n'))
        self.assertTrue(self._r7(hook), "MUT-5 : un 4e motif doit faire échouer R7")


if __name__ == "__main__":
    unittest.main()
