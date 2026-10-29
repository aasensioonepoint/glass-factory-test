"""La revue de clôture (UN critique, S-00004500) est MÉCANIQUE (T-00000586).

POURQUOI CE FICHIER EXISTE. « Aucune tâche n'est marquée terminée sans une revue critique » (à UN critique
depuis S-00004500) est la règle la plus lourde du dépôt, et la seule que RIEN ne tenait :
`.agents/skills/task-board/SKILL.md` l'écrivait lui-même — « le refus est DOCTRINAL et non mécanique ». Une
règle tenue par la mémoire d'un orchestrateur est une règle qu'on oublie, et le pilote devait la réclamer à
chaque clôture (demande du 2026-09-13, formulée comme un agacement).

CE QUE CE BANC LIE, ET C'EST SON OBJET. Le contrat a DEUX moitiés dans deux fichiers : le hook qui ÉCRIT la
trace (`.claude/hooks/binome-trace.sh`) et la garde qui la LIT (`tasks.py`). Un vocabulaire de noms qui
divergerait entre les deux produirait une preuve invisible — donc une clôture refusée sans raison
compréhensible. Les deux listes sont donc comparées ici, pas supposées égales."""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]


def il_y_a(heures: float) -> str:
    """Un `at` RELATIF à maintenant, au format exact du traceur. Les bras qui empruntent SANS historique de portes
    tombent sous la borne d'âge (T-00000846) : une date FIXE y vieillirait d'elle-même et ferait rougir le banc
    un jour donné, pour une raison qui n'a rien à voir avec le code."""
    return (datetime.now(timezone.utc) - timedelta(hours=heures)).strftime("%Y-%m-%dT%H:%M:%SZ")
TASKS = ROOT / ".agents" / "bin" / "tasks.py"
HOOK = ROOT / ".claude" / "hooks" / "binome-trace.sh"
#: LES TROIS ÉCRIVAINS DE LA TRACE. Le vocabulaire clos vit dans chacun, et il
#: doit être le MÊME que celui du lecteur (`tasks.py`) : un banc qui n'en lie
#: qu'un laisse les autres diverger en silence (`T-00000589`).
ECRIVAINS = (HOOK, ROOT / ".codex" / "hooks" / "binome_trace.py", ROOT / ".gemini" / "hooks" / "binome_trace.py")
# L'ARMEMENT DE CE DÉPÔT NE VOYAGE PAS, et c'est voulu : CE marqueur vit sous `.agents/state/`, que `strip:`
# retient. L'adoptant naît pourtant ARMÉ — la sync template lui SÈME une copie de
# `.agents/adopter-seed/gates/BINOME_REQUIRED` (`T-00001093`), dont l'en-tête dit le coût cross-hôte et la
# sortie ; et son pilote peut la retirer, d'où le saut ci-dessous hors du kit. Les seules assertions qui
# touchent ce chemin sont dans `ArmingTests`, dont le `setUp` saute hors du dépôt du kit. Référence au niveau
# MODULE, hors de toute fonction : c'est exactement le cas que la forme (d) du localisateur existe pour
# couvrir, et dont la dette annonçait qu'elle trouverait un jour son premier utilisateur réel — la voici.
# adopting-tree: armement retenu par `strip: .agents/state/`, sauté par ArmingTests.setUp
GATE = ROOT / ".agents" / "state" / "gates" / "BINOME_REQUIRED"
SETTINGS = ROOT / ".claude" / "settings.json"
SKILL = ROOT / ".agents" / "skills" / "task-board" / "SKILL.md"


def _depot_du_kit() -> bool:
    """Ce dépôt est-il celui du kit, ou un projet adoptant ?

    Même sonde que `test_template_hygiene.py` : le marqueur `.agents/IS_THE_KIT` (`strip:`). L'ancienne,
    `main:.agents/ui-src`, rendait 128 partout (T-00000803). Le mécanisme entier VOYAGE (le hook, la garde, la
    skill) ; seul l'ARMEMENT reste ici, donc seules les assertions qui portent sur l'armement sautent ailleurs."""
    # adopting-tree: le marqueur du kit ne voyage pas, son absence EST l'adoptant
    return (ROOT / ".agents" / "IS_THE_KIT").is_file()


def tasks(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TASKS), "--root", str(root), *args],
        capture_output=True, text=True,
    )


def poser_portee(root: Path, focus: str, membres: list[str], declaree: str = "2026-01-01T00:00:00.000Z",
                 clone: str = "", consommes: tuple[str, ...] = ()) -> None:
    """Focus (`clone`, défaut `focus`) et portée POSÉS à la main (T-01M5F728FGJ43QJX1RJKTWWKRB) ; `declaree`
    ANCIENNE pour que les traces datées du banc la suivent."""
    (local := root / ".agents" / "state" / "local").mkdir(parents=True, exist_ok=True)
    (local / "focus.json").write_text(json.dumps({"task_id": clone or focus, "updated_at": declaree}), encoding="utf-8")
    (local / "review-scope.json").write_text(json.dumps(
        {"focus": focus, "members": membres, "consumed": list(consommes), "declared_at": declaree}), encoding="utf-8")


def nouvelle(root: Path, *args: str) -> str:
    """`new`, puis l'id RENDU (« TASKS: <id> → pending ») — jamais un id prédit :
    sous l'allocateur `P-<ULID>` (T-00000726, C2) aucune valeur n'est devinable
    (règle R-BANCS (i)). Un `new` refusé fait échouer le montage, en le disant."""
    p = tasks(root, "new", *args)
    trouve = re.search(r"^TASKS: (\S+) → pending$", p.stdout, re.M)
    if p.returncode != 0 or trouve is None:
        raise AssertionError(f"`new {' '.join(args)}` n'a pas rendu d'id : {p.stdout}{p.stderr}")
    return trouve.group(1)


class ArmingTests(unittest.TestCase):
    """L'ARMEMENT EST UN FAIT DU DÉPÔT, pas une intention.

    LA SEULE CLASSE QUI NE VOYAGE PAS, et c'est la bonne frontière : le mécanisme entier voyage, l'armement de
    CE dépôt non. Chez un adoptant, l'armement vient de la GRAINE semée par la sync template, et c'est une
    décision de SON pilote, qui peut la retirer : ces assertions n'y diraient rien de vrai — d'où le saut. Tout
    le reste de ce banc tourne partout."""

    def setUp(self) -> None:
        if not _depot_du_kit():
            self.skipTest("pas le dépôt du kit — l'armement d'un adoptant vient de sa graine, "
                          "et son pilote en décide")

    def test_the_gate_is_armed_on_this_repository(self) -> None:
        """Décision pilote du 2026-09-13 : armé PAR DÉFAUT, en connaissance du
        coût cross-hôte, dont le réalignement est porté par `T-00000589`."""
        self.assertTrue(GATE.is_file(), "la garde du binôme n'est plus armée")

    def test_the_arming_file_says_what_it_costs(self) -> None:
        """Une garde armée dont le coût n'est pas écrit se lit comme gratuite."""
        texte = GATE.read_text(encoding="utf-8")
        self.assertIn("SubagentStop", texte)
        self.assertIn("T-00000589", texte, "le ticket de réalignement n'est pas nommé")

    def test_the_arming_file_cannot_be_removed_by_an_agent(self) -> None:
        """LES TROIS COPIES OU AUCUNE — correctif du binôme de clôture.

        Un désarmement d'un geste est exactement ce que la garde empêche, et cette règle vit en TROIS copies
        depuis `T-00000604` : `protect-paths.sh` pour Claude, et les deux jumeaux Python pour les cinq autres
        hôtes. Ce banc n'en liait qu'UNE. C'est mot pour mot le défaut que `T-00000604` a corrigé — un marqueur
        protégé sur un hôte et nu sur cinq — et ce banc l'aurait laissé revenir sans rougir. Même forme que
        `VocabularyTests` ci-dessous, qui existe parce qu'un vocabulaire en quatre copies n'était lié qu'en
        deux.

        LES TROIS MARQUEURS, pas seulement celui du binôme : `AFFIRMATION_REQUIRED` avait déjà été oublié une
        fois, et c'est ce qui a valu d'être traité dans le même geste."""
        # T-00000698 (repli de T-00000706) : le marqueur de la chaîne de plan et
        # la PAIRE de la branche par défaut (armement + sortie pilote-seule)
        # rejoignent la liste — c'est ce témoin qui lie la parité sh/jumeaux.
        # T-00000723/750/763 : les trois fichiers pilote-seuls et la paire du
        # code du kit (armement + octroi) les rejoignent, sur les TROIS copies.
        _py = ("KICKOFF_ARMING_SUFFIX", "BINOME_ARMING_SUFFIX", "AFFIRMATION_ARMING_SUFFIX", "PLAN_CIBLE_ARMING_SUFFIX",
               "PLAN_CHAIN_ARMING_SUFFIX", "PUSH_DEFAUT_ARMING_SUFFIX", "PUSH_DEFAUT_SORTIE_SUFFIX",
               "NIGHT_HEADLESS_SUFFIX", "MCP_ALLOWLIST_SUFFIX", "CLAUDE_SETTINGS_LOCAL_SUFFIX",
               "KIT_CODE_ARMING_SUFFIX", "KIT_CODE_SORTIE_SUFFIX", "CONFIG_QUALITE_ARMING_SUFFIX", "CONFIG_QUALITE_SORTIE_SUFFIX")
        for surface, marqueurs in (
            (ROOT / ".claude" / "hooks" / "protect-paths.sh",
             ("kickoff_required", "binome_required", "affirmation_required", "plan_cible_required",
              "plan_chain_required", "push_defaut_protege", "push_defaut_autorise", "night_headless.allow",
              "mcp_allowlist.md", "settings.local.json", "kit_code_protege", "kit_code_autorise", "config_qualite_protege", "config_qualite_autorise")),
            (ROOT / ".codex" / "hooks" / "protect_paths.py", _py),
            (ROOT / ".gemini" / "hooks" / "protect_paths.py", _py),
        ):
            texte = surface.read_text(encoding="utf-8")
            for marqueur in marqueurs:
                with self.subTest(surface=surface.name, marqueur=marqueur):
                    self.assertIn(marqueur, texte,
                                  f"{surface.name} ne protège pas {marqueur}")
        # LES JUMEAUX SONT BYTE-IDENTIQUES : c'est la seule façon de garantir
        # qu'une règle ajoutée d'un côté arrive de l'autre, et le seul contrôle
        # qui survivrait à quelqu'un qui n'aurait pas lu ce commentaire.
        self.assertEqual((ROOT / ".codex" / "hooks" / "protect_paths.py").read_bytes(),
                         (ROOT / ".gemini" / "hooks" / "protect_paths.py").read_bytes(),
                         "les jumeaux protect_paths ont divergé")


class RegleDuNomTests(unittest.TestCase):
    """LA RÈGLE DU NOM N'A PAS DE TROISIÈME COPIE (correction T-00000698, B#1 du binôme de clôture). Classe À PART,
    et qui VOYAGE : les trois fichiers qu'elle lie atteignent l'adoptant, donc ce témoin tourne partout — dans
    `ArmingTests` il aurait été SAUTÉ hors du dépôt du kit (mesuré dans un clone `--shared` : `1 skipped`, la
    mutation invisible)."""

    def test_la_regle_du_nom_derive_sa_liste_du_garde_canonique(self) -> None:
        """La garde de redirection refuse désormais un marqueur d'armement par son NOM seul —
        `cd .agents/state/gates && printf y > PUSH_DEFAUT_AUTORISE` et la même cible entre guillemets passaient
        toutes deux, mesuré sur les hooks vivants. Sa liste est DÉRIVÉE, par famille, du garde canonique que
        `ArmingTests` lie déjà : les globs extraits du bloc `case` de `protect-paths.sh` côté sh, les constantes
        `*_SUFFIX` de `protect_paths.py` côté Python (`arming_marker_names()`). Ce témoin LIT la dérivation dans
        le sh et EXÉCUTE celle des jumeaux, puis compare leur résultat au bloc `case` lui-même — jamais à une
        liste écrite ici. MUTANT : la dérivation remplacée par une liste à la main dans l'un des trois, ou un
        marqueur ajouté au `case` sans son `_SUFFIX` → rouge ici."""
        sh = (ROOT / ".claude" / "hooks" / "safe-bash.sh").read_text(encoding="utf-8")
        self.assertIn(
            'for g in GLOBS if g.startswith("*.agents/state/gates/")', sh,
            "le snippet sh ne dérive plus ses noms de marqueurs des globs extraits")
        # `[a-z_.]+` et non `[a-z_]+` (T-00000723) : `night_headless.allow` et `mcp_allowlist.md` portent un
        # point. Mesuré : l'ancienne classe rendait 9 noms quand les jumeaux en dérivent 11 — ce témoin
        # rougissait sur la BONNE liste parce que sa propre regex était trop étroite.
        canon = set(re.findall(
            r"^\s*\*\.agents/state/gates/([a-z_.]+)\)",
            (ROOT / ".claude" / "hooks" / "protect-paths.sh").read_text(encoding="utf-8"),
            re.M))
        self.assertIn("kickoff_required", canon,
                      "le bloc case de protect-paths.sh ne nomme plus le premier marqueur")
        for twin in (".codex", ".gemini"):
            with self.subTest(twin=twin):
                sortie = subprocess.run(
                    [sys.executable, "-B", "-c",
                     "import json, safe_bash; "
                     "print(json.dumps(sorted(safe_bash.arming_marker_names())))"],
                    cwd=str(ROOT / twin / "hooks"), capture_output=True, text=True,
                )
                self.assertEqual(sortie.returncode, 0, sortie.stderr)
                self.assertEqual(set(json.loads(sortie.stdout)), canon, twin)


class PlanCibleArmingTests(unittest.TestCase):
    """LA CINQUIÈME GARDE (T-00000654) EST PROTÉGÉE DEUX FOIS, comme ses aînées.

    `PLAN_CIBLE_REQUIRED` arme le refus de clore / démarrer (avec trace) / enregistrer un verdict `plan-critic`
    sans que le plan annote chaque étape. Ces témoins VOYAGENT — `protect-paths.sh`, `settings.json` et
    `CLAUDE.md` atteignent l'adoptant — donc ils tournent PARTOUT, pas seulement sur le kit."""

    PROTECT_SH = ROOT / ".claude" / "hooks" / "protect-paths.sh"
    CLAUDE_MD = ROOT / "CLAUDE.md"

    def _protect(self, file_path: str) -> int:
        payload = json.dumps({"tool_input": {"file_path": file_path}})
        return subprocess.run(
            ["bash", str(self.PROTECT_SH)], input=payload,
            capture_output=True, text=True).returncode

    def test_protect_paths_sh_refuse_les_deux_casses_et_l_antislash(self) -> None:
        """MUTANT : branche `plan_cible_required` retirée du `case` casse-replié.
        Le marqueur est refusé (exit 2) en MAJUSCULES, en minuscules et avec des
        antislash NTFS — le pli `\\`→`/` du hook les ramène au même fichier."""
        for chemin in (
            ".agents/state/gates/PLAN_CIBLE_REQUIRED",
            ".agents/state/gates/plan_cible_required",
            ".agents\\state\\gates\\PLAN_CIBLE_REQUIRED",
        ):
            self.assertEqual(self._protect(chemin), 2, f"non refusé : {chemin!r}")

    def test_CONTROLE_NEGATIF_un_voisin_de_la_cible_reste_editable(self) -> None:
        """Sans lui, le témoin ci-dessus passerait avec une garde qui refuse TOUT — et une garde qui refuse tout se
        fait retirer en une semaine. Le suffixe se compare en FIN de chemin, jamais en sous-chaîne."""
        self.assertEqual(
            self._protect(".agents/state/gates/PLAN_CIBLE_REQUIRED.md"), 0,
            "un voisin du marqueur a été refusé à tort")

    def test_ligne_deny_exacte_dans_settings(self) -> None:
        """MUTANT : ligne deny retirée de `settings.json`. `permissions.deny` porte la ligne EXACTE `Edit(...)` —
        jamais `Write(...)`, qui serait inerte (L-00000051, `Edit(path)` couvre déjà tout outil d'édition)."""
        texte = SETTINGS.read_text(encoding="utf-8")
        self.assertIn('"Edit(./.agents/state/gates/PLAN_CIBLE_REQUIRED)"', texte)
        self.assertNotIn('"Write(./.agents/state/gates/PLAN_CIBLE_REQUIRED)"', texte)

    def test_claude_md_enumere_la_garde(self) -> None:
        """MUTANT : paragraphe retiré de `CLAUDE.md`. L'énumération des gardes protégées deux fois NOMME
        `PLAN_CIBLE_REQUIRED`, `protect-paths.sh` ET `permissions.deny` — sans elle, l'énumération devient
        fausse par omission, et sa sortie tracée `--sans-cible` disparaît."""
        texte = self.CLAUDE_MD.read_text(encoding="utf-8")
        self.assertIn("PLAN_CIBLE_REQUIRED", texte)
        self.assertIn("protect-paths.sh", texte)
        self.assertIn("permissions.deny", texte)
        self.assertIn("--sans-cible", texte)

    def test_les_jumeaux_portent_le_suffixe_de_cible(self) -> None:
        """MUTANT : suffixe retiré d'un SEUL jumeau. Les deux impls Python portent `PLAN_CIBLE_ARMING_SUFFIX` (la
        byte-identité voisine, dans `ArmingTests`, interdit qu'un seul l'ait)."""
        for twin in (ROOT / ".codex" / "hooks" / "protect_paths.py",
                     ROOT / ".gemini" / "hooks" / "protect_paths.py"):
            self.assertIn("PLAN_CIBLE_ARMING_SUFFIX",
                          twin.read_text(encoding="utf-8"), twin.name)


class VocabularyTests(unittest.TestCase):
    """LES DEUX MOITIÉS DU CONTRAT NE DOIVENT PAS DIVERGER."""

    def test_the_writer_and_the_reader_name_the_SAME_critics(self) -> None:
        """TOUS LES ÉCRIVAINS, pas seulement celui de Claude — correctif du binôme de clôture. Le vocabulaire clos
        vit en QUATRE copies depuis `T-00000589` et ce banc n'en liait que DEUX : renommer un critique — ce
        dépôt l'a déjà fait, `critic-sonnet-max` — rougissait sur Claude et PASSAIT sur les quatre autres hôtes,
        donc la trace y serait écrite sous un nom que `set_state` ne reconnaît pas, et la clôture refusée sans
        raison compréhensible. C'est exactement ce que ce banc existe pour empêcher."""
        lu = re.search(r'BINOME_CRITIQUES = \((.*?)\)', TASKS.read_text(encoding="utf-8"), re.S)
        self.assertIsNotNone(lu, "la garde ne déclare plus son vocabulaire")
        noms = lambda m: sorted(re.findall(r'"([^"]+)"', m.group(1)))
        for ecrivain in ECRIVAINS:
            with self.subTest(ecrivain=ecrivain.name):
                self.assertTrue(ecrivain.exists(), f"{ecrivain} absent")
                ecrit = re.search(
                    r'CRITIQUES = \((.*?)\)', ecrivain.read_text(encoding="utf-8"), re.S
                )
                self.assertIsNotNone(
                    ecrit, f"{ecrivain.name} ne déclare plus son vocabulaire"
                )
                self.assertEqual(
                    noms(ecrit), noms(lu),
                    f"{ecrivain.name} écrit sous des noms que la garde ne reconnaît "
                    "pas : la preuve serait invisible et la clôture refusée sans "
                    "raison compréhensible",
                )

    def test_les_deux_ports_python_sont_octet_pour_octet_identiques(self) -> None:
        """TWIN VERBATIM. `.codex/hooks/` et `.gemini/hooks/` servent CINQ hôtes à eux deux, donc aucune des deux
        copies ne peut nommer un hôte — et une correction appliquée à une seule diverge EN SILENCE. La première
        rédaction du port avait exactement ce défaut : les deux fichiers étaient identiques mais leur docstring
        nommait trois hôtes et renvoyait « son miroir » à elle-même."""
        self.assertEqual(
            ECRIVAINS[1].read_bytes(), ECRIVAINS[2].read_bytes(),
            "les deux ports Python ont divergé — une correction n'a touché qu'une copie",
        )

    def test_aucun_port_ne_NOMME_un_hote(self) -> None:
        """Un jumeau verbatim qui nomme un hôte est faux la moitié du temps.
        Règle déjà écrite dans le fichier voisin `audit_gate.py`."""
        for ecrivain in ECRIVAINS[1:]:
            with self.subTest(ecrivain=ecrivain.name):
                texte = ecrivain.read_text(encoding="utf-8")
                for interdit in ("Codex, Kimi Code et GitHub Copilot",
                                 "Gemini a son miroir"):
                    self.assertNotIn(
                        interdit, texte,
                        f"{ecrivain.name} nomme un hôte : faux dans l'autre copie",
                    )

    def test_the_pair_and_its_fallback_are_all_three_there(self) -> None:
        lu = re.search(r'BINOME_CRITIQUES = \((.*?)\)', TASKS.read_text(encoding="utf-8"), re.S)
        self.assertEqual(
            sorted(re.findall(r'"([^"]+)"', lu.group(1))),
            ["critic-fable", "critic-opus", "critic-sonnet-max"],
        )


#: Stub de `tasks.py` piloté par `BT_STUB`. `dort` dépasse le `timeout=4` des
#: ports Python : c'est un VRAI `TimeoutExpired`, pas un `exit 124` qui ne
#: rejouerait que le bras « rc non nul », déjà tenu par `rc1`.
_STUB_TASKS = '''\
import json, os, sys, time
mode = os.environ.get("BT_STUB", "")
if mode == "rc1":
    sys.exit(1)
if mode == "dort":
    time.sleep(6)
    print("[]")
elif mode == "dict":
    print("{}")
elif mode == "vide":
    print("[]")
elif mode == "running":
    print(json.dumps([{"id": "T-00000009", "state": "running"}]))
elif mode == "utf8":
    sys.stdout.buffer.write(json.dumps(
        [{"id": "T-00000009", "state": "running", "task": "\\u2190"}],
        ensure_ascii=False).encode("utf-8"))
elif mode == "sans_id":
    print(json.dumps([{"id": "T-00000009", "state": "running"},
                      {"state": "running"}, {"id": "", "state": "running"}]))
'''


class PortsBoardIllisibleTests(unittest.TestCase):
    """UN BOARD QUI NE RÉPOND PAS N'EST PAS UN BOARD VIDE (T-00000845).

    Les ports Python n'écrivent RIEN sans tâche `running` — ce contrat d'écriture ne change pas, ils n'ont pas
    le nom réservé `_sans-slot` du traceur Claude. Mais leur `run()` rendait `""` sur rc non nul, timeout ou
    exception, complété en `"[]"` : un board illisible se taisait EXACTEMENT comme le cas nominal « aucune
    running ». Désormais il le dit sur stderr.

    Ces cas n'existaient nulle part : ce banc ne faisait que LIRE les ports (vocabulaire, jumeaux). Chaque port
    tourne ici dans un arbre jetable, avec SON `_common.py` (les deux copies diffèrent) et un `tasks.py` factice
    — `_common` tente `git rev-parse` puis retombe sur l'emplacement du script ; le plafond git
    (`GIT_CEILING_DIRECTORIES`) force ce repli, donc le stub est le seul `tasks.py` que le port puisse voir. Les
    deux témoins `vide` et `running` tournent sur le MÊME stub : sans eux, un stub cassé rendrait « illisible »
    partout et les bras incident passeraient pour la mauvaise raison."""

    CHARGE = json.dumps({"hook_event_name": "SubagentStop", "agent_type": "critic-opus"})

    #: LOCALE HOSTILE du témoin `utf8` (T-00000845). Sous Windows, `text=True`
    #: sans `encoding` décode en cp1252 (0x90 n'y est pas défini) ; macOS ne
    #: donne pas cp1252, mais une locale C non coercée et le mode UTF-8 coupé
    #: font décoder en US-ASCII — même `UnicodeDecodeError` sur les octets de
    #: `←`, mesuré rouge sur l'ancien `run()`.
    LOCALE_HOSTILE = {"LC_ALL": "C", "PYTHONCOERCECLOCALE": "0", "PYTHONUTF8": "0"}

    def _lance(self, port: Path, mode: str, env_sup: dict[str, str] | None = None, portee: str = "ok",
               ) -> tuple[subprocess.CompletedProcess[str], list[str]]:
        with tempfile.TemporaryDirectory() as t:
            arbre = Path(t)
            hooks = arbre / port.parent.parent.name / "hooks"
            hooks.mkdir(parents=True)
            shutil.copy(port, hooks / port.name)
            shutil.copy(port.parent / "_common.py", hooks / "_common.py")
            (arbre / ".agents" / "bin").mkdir(parents=True)
            (arbre / ".agents" / "bin" / "tasks.py").write_text(_STUB_TASKS, encoding="utf-8")
            if portee != "aucune":  # sans portée, hors focus ou consommée : rien (T-01M5F728FGJ43QJX1RJKTWWKRB)
                poser_portee(arbre, "T-00000009", ["T-00000009"], clone="T-00000008" if portee == "hors-focus" else "",
                             consommes=("T-00000009",) if portee == "consommee" else ())
            env = {k: v for k, v in os.environ.items()
                   if k not in ("CLAUDE_PROJECT_DIR", "CADRE_PROJECT_ROOT")}
            env["BT_STUB"] = mode
            # PLAFOND GIT : sans lui, un TMPDIR logé dans un dépôt git fait
            # résoudre ROOT à CE dépôt — stub ignoré, faux rouge, voire vraie
            # trace écrite hors du bac à sable. Mesuré rouge sans (10 sous-cas).
            env["GIT_CEILING_DIRECTORIES"] = str(arbre.resolve().parent)
            env.update(env_sup or {})
            p = subprocess.run(
                [sys.executable, str(hooks / port.name)],
                input=self.CHARGE, text=True, capture_output=True,
                cwd=str(arbre), env=env, timeout=30,
            )
            binome = arbre / ".agents" / "state" / "local" / "binome"
            ecrits = sorted(f.name for f in binome.glob("*.json")) if binome.is_dir() else []
        return p, ecrits

    def test_un_board_ILLISIBLE_est_DIT_sur_stderr_et_rien_n_est_ecrit(self) -> None:
        for port in ECRIVAINS[1:]:
            for mode in ("rc1", "dort", "dict"):
                with self.subTest(port=str(port.relative_to(ROOT)), mode=mode):
                    p, ecrits = self._lance(port, mode)
                    self.assertEqual(p.returncode, 0, "le port doit rester advisory")
                    self.assertEqual(ecrits, [], "contrat d'écriture : rien sans running")
                    self.assertIn(
                        "board illisible", p.stderr,
                        f"tasks.py {mode} : le port se tait comme sur un board vide",
                    )

    def test_TEMOIN_board_sain_sans_running_reste_SILENCIEUX(self) -> None:
        for port in ECRIVAINS[1:]:
            with self.subTest(port=str(port.relative_to(ROOT))):
                p, ecrits = self._lance(port, "vide")
                self.assertEqual((p.returncode, ecrits), (0, []))
                self.assertNotIn("board illisible", p.stderr)

    def test_TEMOIN_board_avec_running_trace_normalement(self) -> None:
        for port in ECRIVAINS[1:]:
            for portee, attendu, avis in (("ok", ["T-00000009.critic-opus.json"], ""), ("aucune", [], "aucune portee"),
                                          ("hors-focus", [], "portee hors focus"), ("consommee", [], "portee consommee")):
                with self.subTest(port=str(port.relative_to(ROOT)), portee=portee):
                    p, ecrits = self._lance(port, "running", portee=portee)
                    self.assertEqual(p.returncode, 0)
                    self.assertEqual(ecrits, attendu, f"portée {portee} : la running ne doit pas être tracée")
                    self.assertEqual(("review-scope" in p.stderr, avis in p.stderr), (bool(avis), True), p.stderr)
                    self.assertNotIn("board illisible", p.stderr)

    def test_un_board_UTF8_se_lit_meme_sous_une_locale_NON_UTF8(self) -> None:
        # `tasks.py` écrit de l'UTF-8 (`ensure_ascii=False`) et le vrai board
        # contient `←`. Décodé selon la locale, il levait `UnicodeDecodeError`,
        # donc « board illisible » À TORT, donc aucune trace, donc `done` refusé.
        for port in ECRIVAINS[1:]:
            with self.subTest(port=str(port.relative_to(ROOT))):
                p, ecrits = self._lance(port, "utf8", self.LOCALE_HOSTILE)
                self.assertEqual(p.returncode, 0)
                self.assertNotIn("board illisible", p.stderr)
                self.assertEqual(ecrits, ["T-00000009.critic-opus.json"])

    def test_une_ligne_running_SANS_id_ne_perd_pas_la_ligne_saine(self) -> None:
        # Une ligne `running` sans `id` ou à `id` vide ne doit ni faire perdre
        # la trace de la ligne saine, ni écrire `.critic-opus.json` — nom que
        # la garde d'affirmation compterait (elle lit le dernier segment).
        for port in ECRIVAINS[1:]:
            with self.subTest(port=str(port.relative_to(ROOT))):
                p, ecrits = self._lance(port, "sans_id")
                self.assertEqual(p.returncode, 0)
                self.assertEqual(ecrits, ["T-00000009.critic-opus.json"])

    def test_les_trois_run_decodent_EXPLICITEMENT_en_utf8(self) -> None:
        # Complément STATIQUE : le témoin ci-dessus ne rejoue pas cp1252 sur un
        # poste non-Windows ; ceci tient la forme du correctif dans les trois.
        for ecrivain in ECRIVAINS:
            with self.subTest(ecrivain=str(ecrivain.relative_to(ROOT))):
                texte = ecrivain.read_text(encoding="utf-8")
                # Borné à `return p.stdout` : le `write_text(encoding="utf-8")`
                # plus bas satisferait sinon l'assertion sans que run() change.
                corps = re.search(r"def run\(.*?return p\.stdout", texte, re.S)
                self.assertIsNotNone(corps, "run() introuvable")
                self.assertIn('encoding="utf-8"', corps.group(0))
                self.assertIn('errors="replace"', corps.group(0))


class RegistrationTests(unittest.TestCase):
    """Un hook parfait qui n'est enregistré nulle part ne s'exécute jamais.

    Les faits sont liés SUR LA MÊME ENTRÉE, gabarit de
    `test_context_retro_contract.py` : vérifier séparément « il existe une entrée
    SubagentStop » et « une entrée appelle le hook » passerait sur deux entrées
    différentes."""

    def _entries(self) -> list[dict]:
        d = json.loads(SETTINGS.read_text(encoding="utf-8"))
        return [
            h
            for e in d.get("hooks", {}).get("SubagentStop", [])
            for h in e.get("hooks", [])
            if "binome-trace.sh" in h.get("command", "")
        ]

    def test_the_tracer_is_registered_once_on_SubagentStop(self) -> None:
        self.assertEqual(len(self._entries()), 1)

    def test_it_carries_the_windows_wrapping_every_other_entry_carries(self) -> None:
        """Sans le `cygpath`, le hook no-ope EN SILENCE sous Git Bash."""
        cmd = self._entries()[0]
        self.assertEqual(cmd.get("shell"), "bash")
        self.assertIn("cygpath -u", cmd["command"])

    def test_the_tracer_invokes_no_model(self) -> None:
        """Redondant avec `test_hooks_zero_llm.py` PAR CONSTRUCTION, et c'est
        voulu : celui-là balaie les registres, celui-ci nomme le fichier."""
        texte = HOOK.read_text(encoding="utf-8")
        for interdit in ("claude -p", "claude --print", "codex exec", "gemini -p",
                         "ollama run", "anthropic", "openai"):
            self.assertNotIn(interdit, texte, f"le hook invoque {interdit!r}")


class RefusalTests(unittest.TestCase):
    """LE COMPORTEMENT, exercé sur un board jetable et un vrai `tasks.py`."""

    def _trace(self, root: Path, tid: str, noms: list[str], at: str | None = None) -> str:
        """Pose une trace pour chaque critique nommé, à la forme RÉELLE, et rend son `at`. Daté d'IL Y A UNE HEURE
        par défaut : ces bras empruntent sans historique de portes, donc sous la borne d'âge de T-00000846."""
        at = at or il_y_a(1)
        dd = root / ".agents" / "state" / "local" / "binome"
        dd.mkdir(parents=True, exist_ok=True)
        for nom in noms:
            (dd / f"{tid}.{nom}.json").write_text(json.dumps({"sha": "abc1234", "at": at}), encoding="utf-8")
        return at

    def _prepare(self, critiques: dict | None = None, armer: bool = True, chantier: str = "") -> Path:
        d = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        # `self.t1` : la tâche à clore, id CAPTURÉ (T-00000726), relu par chaque témoin.
        self.t1 = nouvelle(d, "une tache a clore", *(("--chantier", chantier) if chantier else ()))
        if armer:
            g = d / ".agents" / "state" / "gates" / "BINOME_REQUIRED"
            g.parent.mkdir(parents=True, exist_ok=True)
            g.write_text("arme", encoding="utf-8")
        if critiques is not None:
            # UN FICHIER PAR CRITIQUE : c'est ce qui supprime la course entre un
            # critique et son repli arrêtés ensemble. La fixture suit la forme
            # réelle, jamais une forme inventée pour le banc.
            dd = d / ".agents" / "state" / "local" / "binome"
            dd.mkdir(parents=True, exist_ok=True)
            for nom, info in critiques.items():
                (dd / f"{self.t1}.{nom}.json").write_text(json.dumps(info), encoding="utf-8")
        return d

    def test_closing_without_any_review_is_REFUSED(self) -> None:
        d = self._prepare()
        p = tasks(d, "done", self.t1, "--raison", "fini")
        self.assertNotEqual(p.returncode, 0, "la clôture sans revue est passée")
        self.assertIn("REVUE CRITIQUE", p.stdout + p.stderr)

    def test_a_SINGLE_critic_closes_the_task(self) -> None:
        """S-00004500 (T-00001226) : UN critique de clôture suffit, et il porte seul l'union des angles A et B ; le
        refus à ZÉRO critique reste tenu par `test_closing_without_any_review_is_REFUSED`. SANS FOCUS au clone
        (ancien régime) ; avec un focus, la trace non estampillée exige la portée (`..._with_focus_needs_scope`)."""
        d = self._prepare({"critic-opus": {"sha": "abc1234", "at": "2026-09-13T10:00:00Z"}})
        p = tasks(d, "done", self.t1, "--raison", "fini")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("→ done", p.stdout + p.stderr, "la clôture à un critique n'est pas annoncée")

    def test_unstamped_trace_with_focus_needs_scope(self) -> None:
        """L'ANCIEN TRACEUR écrivait la même trace, non estampillée, sur CHAQUE `running` : focus au clone et
        aucune portée → refus qui nomme `review-scope` ; datée AVANT la déclaration, ou à `at` illisible sous
        la portée, elle ne crédite pas davantage (exec-critic du lot C, T-01M5F728FGJ43QJX1RJKTWWKRB)."""
        d = self._prepare({"critic-opus": {"sha": "abc1234", "at": il_y_a(1)}})
        tasks(d, "start", self.t1)
        p = tasks(d, "done", self.t1, "--raison", "fini")
        self.assertNotEqual(p.returncode, 0, "la trace de l'ancien traceur a crédité malgré le focus")
        self.assertIn(f"`tasks.py review-scope {self.t1} [<T>…]`", p.stdout + p.stderr)
        tasks(d, "review-scope", self.t1)
        self.assertNotEqual(tasks(d, "done", self.t1, "--raison", "x").returncode, 0, "trace d'AVANT la portée")
        self._trace(d, self.t1, ["critic-opus"], at="x")
        self.assertNotEqual(tasks(d, "done", self.t1, "--raison", "x").returncode, 0, "`at` illisible crédité")

    def test_two_DISTINCT_critics_let_the_closure_through(self) -> None:
        d = self._prepare({
            "critic-opus": {"sha": "abc1234", "at": "2026-09-13T10:00:00Z"},
            "critic-fable": {"sha": "abc1234", "at": "2026-09-13T10:01:00Z"},
        })
        p = tasks(d, "done", self.t1, "--raison", "revue faite")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_the_FALLBACK_pair_is_accepted_too(self) -> None:
        """Le repli `critic-sonnet-max` (effort maximal) compte comme les autres,
        ici à côté de `critic-opus`. Une garde qui ne connaîtrait que le critique
        nominal forcerait la dérogation sur une revue LÉGITIME (S-00004500)."""
        d = self._prepare({
            "critic-opus": {"sha": "abc1234", "at": "2026-09-13T10:00:00Z"},
            "critic-sonnet-max": {"sha": "abc1234", "at": "2026-09-13T10:01:00Z"},
        })
        p = tasks(d, "done", self.t1, "--raison", "repli")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_an_unknown_name_does_not_count_as_a_critic(self) -> None:
        """Sinon une entrée quelconque dans le fichier suffirait."""
        d = self._prepare({
            "critic-maison": {"sha": "abc1234", "at": "x"},
            "dev-mono": {"sha": "abc1234", "at": "x"},
        })
        p = tasks(d, "done", self.t1, "--raison", "fini")
        self.assertNotEqual(p.returncode, 0)

    def test_the_traced_escape_closes_AND_stays_visible_on_the_board(self) -> None:
        """La sortie existe parce qu'un doublon ou un ticket caduc n'a rien à
        faire relire. Ce qui la rend acceptable est qu'elle ne s'évapore pas :
        la raison reste dans `stage`, que `list --task` rend en ENTIER."""
        d = self._prepare()
        p = tasks(d, "done", self.t1, "--raison", "doublon de T-2",
                  "--sans-binome", "rien a relire, aucun code touche")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        vue = tasks(d, "list", "--task", self.t1).stdout
        self.assertIn("SANS BINÔME", vue, "la dérogation a disparu du board")
        self.assertIn("rien a relire", vue, "la raison de la dérogation a disparu")

    def test_a_DISARMED_repository_closes_as_before(self) -> None:
        """Le kit doit rester utilisable là où la trace n'existe pas. L'absence
        du fichier d'armement EST le régime de référence."""
        d = self._prepare(armer=False)
        p = tasks(d, "done", self.t1, "--raison", "fini")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_a_corrupt_trace_does_not_let_the_closure_through(self) -> None:
        """Un fichier illisible n'est pas une preuve. Le refus est la seule
        garde de ce lot qui échoue FERMÉ, et c'est délibéré."""
        d = self._prepare()
        t = d / ".agents" / "state" / "local" / "binome" / f"{self.t1}.json"
        t.parent.mkdir(parents=True, exist_ok=True)
        t.write_text("{pas du json", encoding="utf-8")
        p = tasks(d, "done", self.t1, "--raison", "fini")
        self.assertNotEqual(p.returncode, 0)

    def test_the_refusal_names_a_remedy_the_agent_can_actually_run(self) -> None:
        d = self._prepare()
        sortie = tasks(d, "done", self.t1, "--raison", "fini")
        texte = sortie.stdout + sortie.stderr
        self.assertIn("--sans-binome", texte)
        self.assertIn("critic-opus", texte)
        self.assertIn("critic-fable", texte)

    def test_the_escape_does_NOT_disarm_the_reason_guard(self) -> None:
        """RÉGRESSION MESURÉE PAR LE BINÔME DE CLÔTURE, et introduite par ce lot. La dérogation était composée dans
        la CLI, donc `stage` arrivait non vide à `set_state` : `done --raison "" --sans-binome "doublon"`
        passait avec rc=0, rouvrant la garde du 2026-09-12 dont toute la raison d'être est qu'une clôture dise
        au nom de quoi. Le témoin précédent jouait `--raison "   "` SANS la dérogation — il passait donc pour
        une bonne raison et manquait exactement ce chemin."""
        d = self._prepare()
        p = tasks(d, "done", self.t1, "--raison", "", "--sans-binome", "doublon")
        self.assertNotEqual(p.returncode, 0, "une clôture SANS MOTIF est passée")
        self.assertIn("exige un motif", p.stdout + p.stderr)

    def test_the_escape_APPENDS_to_the_reason_it_does_not_replace_it(self) -> None:
        d = self._prepare()
        tasks(d, "done", self.t1, "--raison", "doublon de T-2",
              "--sans-binome", "rien a relire")
        vue = tasks(d, "list", "--task", self.t1).stdout
        self.assertIn("doublon de T-2", vue, "le motif a été remplacé")
        self.assertIn("SANS BINÔME", vue)

    def test_reopen_EXPIRES_the_proof(self) -> None:
        """SANS ÇA, LA REVUE D'HIER VAUT PREUVE POUR LA CLÔTURE DE DEMAIN. La trace est indexée par tâche et
        n'était invalidée nulle part : `done` → `reopen` → `done` refermait sans une seule revue neuve, sur un
        SHA que plus personne n'avait relu. C'est la fraîcheur que `T-00000586` exigeait et qui avait disparu à
        l'implémentation. `reopen` est le seul retour en arrière du board, donc c'est là que la preuve se périme
        d'office ; l'autre purgeur est le verbe explicite `binome-purge` (T-00000842)."""
        d = self._prepare({
            "critic-opus": {"sha": "aaaaaaa", "at": "x"},
            "critic-fable": {"sha": "aaaaaaa", "at": "x"},
        })
        self.assertEqual(tasks(d, "done", self.t1, "--raison", "revue").returncode, 0)
        self.assertEqual(tasks(d, "reopen", self.t1, "--raison", "clôture prononcée à tort").returncode, 0)
        p = tasks(d, "done", self.t1, "--raison", "refermée")
        self.assertNotEqual(p.returncode, 0, "la revue d'avant la réouverture a resservi")
        self.assertIn("REVUE CRITIQUE", p.stdout + p.stderr)

    def test_two_critics_stopping_CONCURRENTLY_both_survive(self) -> None:
        """LA DOCTRINE LES LANÇAIT EN PARALLÈLE avant S-00004500, et un critique et son repli peuvent encore
        s'arrêter dans la même fenêtre. Avec un fichier unique lu-modifié-réécrit, les deux lisaient l'état vide
        et le second écrasait le premier : UNE entrée — le mécanisme échouait sur le cas qu'il existe pour
        servir, et l'échec avait l'air d'un oubli. Le témoin garde la course : chaque critique écrit son propre
        fichier."""
        import concurrent.futures
        import os

        d = self._prepare()
        tasks(d, "start", self.t1)
        tasks(d, "review-scope", self.t1)
        marque = d / ".agents" / "state" / "local" / "binome"

        def frappe(nom: str) -> None:
            subprocess.run(["bash", str(HOOK)], text=True, capture_output=True,
                           input=json.dumps({"hook_event_name": "SubagentStop", "agent_type": nom}),
                           env={**os.environ, "CLAUDE_PROJECT_DIR": str(d)})

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            list(ex.map(frappe, ["critic-opus", "critic-fable"]))

        restants = sorted(p.name for p in marque.glob(f"{self.t1}.*.json"))
        self.assertEqual(len(restants), 2, f"un critique a écrasé l'autre — vu : {restants}")
        self.assertEqual(tasks(d, "done", self.t1, "--raison", "revue faite").returncode, 0)

    def test_the_proof_of_the_RUNNING_SLOT_covers_a_pending_subtask(self) -> None:
        """LE DÉFAUT QUI RENDAIT LA GARDE DÉCORATIVE, mesuré par le binôme. La trace est écrite sur les tâches
        `running` ; or un chantier au mandat d'écriture armé garde UNE tâche au slot et ferme ses sous-tâches
        depuis `pending` (règle 1bis). Aucune sous-tâche n'avait donc jamais de trace : toute clôture tombait
        sur le refus, et la seule issue était la dérogation. Une garde qu'on ne peut franchir que par son
        échappatoire n'est pas une garde. L'emprunt passe depuis par la PORTÉE déclarée (T-01M5F728FGJ43QJX1RJKTWWKRB)."""
        d = self._prepare(chantier="ch")
        self.t2 = nouvelle(d, "le slot du chantier", "--chantier", "ch")
        tasks(d, "start", self.t2)
        poser_portee(d, self.t2, [self.t2, self.t1])
        at = self._trace(d, self.t2, ["critic-opus", "critic-fable"])
        p = tasks(d, "done", self.t1, "--raison", "fini")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        vue = tasks(d, "list", "--task", self.t1).stdout
        self.assertIn(f"binôme relevé sur {self.t2}", vue,
                      "l'emprunt n'est pas écrit : une preuve indirecte se lit comme directe")
        # L'ÂGE DE L'EMPRUNT EST ÉCRIT LUI AUSSI : l'emprunt expire (à
        # l'avant-dernier vert depuis T-00000592, à 24 h sans historique depuis
        # T-00000846), mais un binôme couvre tout le LOT fermé sous sa fenêtre —
        # le board dit donc quand et sur quel SHA, pour qu'on voie ce périmètre.
        self.assertIn("abc1234", vue, "l'emprunt ne dit pas sur quel SHA la revue a eu lieu")
        self.assertIn(at, vue, "l'emprunt ne dit pas QUAND")

    def test_a_DIFFERENT_chantier_does_not_lend_its_proof(self) -> None:
        """LE CONTRÔLE NÉGATIF DE L'EMPRUNT. Sans lui, n'importe quelle tâche
        hériterait de la revue de n'importe quelle autre."""
        d = self._prepare(chantier="ch-a")
        self.t2 = nouvelle(d, "un autre chantier", "--chantier", "ch-b")
        tasks(d, "start", self.t2)
        self._trace(d, self.t2, ["critic-opus", "critic-fable"])
        self.assertNotEqual(tasks(d, "done", self.t1, "--raison", "fini").returncode, 0)

    def test_a_task_with_NO_chantier_borrows_nothing(self) -> None:
        d = self._prepare(chantier="")
        self.t2 = nouvelle(d, "le slot", "--chantier", "ch")
        tasks(d, "start", self.t2)
        self._trace(d, self.t2, ["critic-opus", "critic-fable"])
        self.assertNotEqual(tasks(d, "done", self.t1, "--raison", "fini").returncode, 0)

    def test_scope_required_consumed_and_focus_bound(self) -> None:
        """LA PORTÉE BORNE LA PREUVE (T-01M5F728FGJ43QJX1RJKTWWKRB) : sans portée rien n'est crédité ; la revue de
        A1 ne crédite pas A2, `running` du même chantier ; hors focus la portée est ignorée ; une nouvelle
        déclaration invalide les anciennes traces ; un membre consommé (puis rouvert) n'emprunte plus."""
        d = self._prepare(chantier="ch")
        a2, a3 = nouvelle(d, "A2", "--chantier", "ch"), nouvelle(d, "A3", "--chantier", "ch")
        charge = '{"hook_event_name":"SubagentStop","agent_type":"critic-opus"}'
        # (gestes AVANT le critique, gestes APRÈS, tâche close, passe ?, ce que l'échec voudrait dire)
        for avant, apres, t, passe, quoi in (
                ([("start", self.t1), ("start", a2), ("focus", self.t1)], [], self.t1, False, "revue SANS portée créditée"),
                ([("review-scope", self.t1)], [], a2, False, "la revue de A1 a crédité A2"),
                ([], [], self.t1, True, "la revue sous portée ne crédite pas son membre"),
                ([("start", a3), ("focus", a2), ("review-scope", a2, a3), ("focus", a3)], [], a2, False, "HORS FOCUS"),
                ([("focus", a2)], [("review-scope", a2, a3)], a2, False, "trace d'avant la nouvelle déclaration créditée"),
                ([], [], a2, True, "la trace sous la nouvelle déclaration ne crédite pas"),
                ([("reopen", a2, "--raison", "rouverte")], [], a2, False, "un membre CONSOMMÉ a emprunté à A3")):
            for geste in avant:
                tasks(d, *geste)
            subprocess.run(["bash", str(HOOK)], input=charge, text=True, capture_output=True,
                           env={**os.environ, "CLAUDE_PROJECT_DIR": str(d)})
            for geste in apres:
                tasks(d, *geste)
            self.assertEqual(tasks(d, "done", t, "--raison", "fini").returncode == 0, passe, quoi)

    def test_focus_without_scope_names_review_scope(self) -> None:
        """Focus présent, aucune portée : le refus du `done` NOMME `review-scope` et sa liste (C44)."""
        d = self._prepare()
        tasks(d, "start", self.t1)
        p = tasks(d, "done", self.t1, "--raison", "fini")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn(f"`tasks.py review-scope {self.t1} [<T>…]`", p.stdout + p.stderr)

    def test_scope_out_of_focus_names_focus_first(self) -> None:
        """F1 de la clôture (scénario du critique) : revue faite sous la portée P L, puis `start E` : le refus du
        `done L` nomme D'ABORD `tasks.py focus P`, avant `review-scope` ; `focus P` le rend vert sans critique."""
        d = self._prepare()
        p, l1, e = self.t1, nouvelle(d, "L"), nouvelle(d, "E")
        for geste in (("start", p), ("start", l1), ("focus", p), ("review-scope", p, l1)):
            tasks(d, *geste)
        subprocess.run(["bash", str(HOOK)], input='{"hook_event_name":"SubagentStop","agent_type":"critic-opus"}',
                       text=True, capture_output=True, env={**os.environ, "CLAUDE_PROJECT_DIR": str(d)})
        tasks(d, "start", e)
        sortie = (r := tasks(d, "done", l1, "--raison", "fini")).stdout + r.stderr
        self.assertNotEqual(r.returncode, 0, sortie)
        remede = sortie[sortie.index("PORTÉE DE REVUE : "):]
        self.assertIn(f"`tasks.py focus {p}`", remede)
        self.assertLess(remede.index(f"`tasks.py focus {p}`"), remede.index("review-scope"), remede)
        tasks(d, "focus", p)
        self.assertEqual(tasks(d, "done", l1, "--raison", "fini").returncode, 0)

    def test_focus_rule_binds_group_and_delivery_legs(self) -> None:
        """C-K2 : focus au clone, aucune portée qui couvre la tâche — la trace NON estampillée d'un membre du
        GROUPE parallèle ou de la LIVRAISON ne crédite pas, et le refus NOMME `review-scope` ; sans `focus.json`,
        l'ancien régime la laisse passer (mutants M1c et M1d de la passe de correction de T-01M5DBFPWC)."""
        for jambe in ("groupe", "livraison"):
            d = self._prepare()
            t2 = nouvelle(d, "le membre")
            if jambe == "livraison":
                tasks(d, "livraison", self.t1, t2, "--branche", "integ/l")
            else:
                b = d / ".agents" / "state" / "board" / "TASKS.json"
                data = json.loads(b.read_text(encoding="utf-8"))
                for t in data["tasks"]:
                    t.update(parallel_group="g", state="running" if t["id"] == t2 else t["state"])
                b.write_text(json.dumps(data), encoding="utf-8")
            self._trace(d, t2, ["critic-opus"], at=il_y_a(0))
            poser_portee(d, "T-AILLEURS", ["T-AILLEURS"], clone=self.t1)
            p = tasks(d, "done", self.t1, "--raison", "fini")
            self.assertNotEqual(p.returncode, 0, f"{jambe} : trace non estampillée créditée sous focus")
            self.assertIn(f"`tasks.py review-scope {self.t1} [<T>…]`", p.stdout + p.stderr, jambe)
            (d / ".agents" / "state" / "local" / "focus.json").unlink()
            self.assertEqual(tasks(d, "done", self.t1, "--raison", "fini").returncode, 0, f"{jambe} sans focus")

    def test_the_OTHER_guard_still_bites_first(self) -> None:
        """La garde du motif existait avant celle-ci ; l'ajouter ne doit pas
        l'avoir décalée. Une clôture sans raison reste refusée pour SA raison."""
        d = self._prepare({
            "critic-opus": {"sha": "a", "at": "x"}, "critic-fable": {"sha": "a", "at": "x"},
        })
        p = tasks(d, "done", self.t1, "--raison", "   ")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("exige un motif", p.stdout + p.stderr)


class ExpirationDeLEmpruntTests(unittest.TestCase):
    """L'EMPRUNT DE PREUVE EXPIRE AVEC SON CYCLE (T-00000592).

    LE DÉFAUT QUE ÇA FERME, mesuré le jour même où la garde a été posée : la trace n'était purgée que par
    `reopen`, et l'emprunt ne comparait NI sha NI date. Dès qu'un chantier avait son premier binôme tracé, toute
    sous-tâche se fermait sur lui indéfiniment — avec au board une mention qui avait l'apparence d'une revue.
    Une garde qui semble mordre et ne mord plus après son premier passage est PIRE qu'une garde absente.

    LA BORNE N'EST PAS LE SHA DU TAMPON COURANT, et c'est le cœur de la correction. Le ticket le recommandait ;
    le contre-exemple mesuré à la clôture de `T-00000591` l'a invalidé : le binôme passe AVANT la porte, donc la
    trace naît TOUJOURS avec le sha précédent — trace `@ e5beb66` pendant que le tampon portait `97ab48d`. Cette
    règle-là aurait refusé le cas NOMINAL, et les aurait refusés TOUS. La borne est donc l'AVANT-DERNIER verdict
    vert."""

    def _depot(self, chantier: str = "c1") -> Path:
        d = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        g = d / ".agents" / "state" / "gates" / "BINOME_REQUIRED"
        g.parent.mkdir(parents=True, exist_ok=True)
        g.write_text("arme", encoding="utf-8")
        # Le PORTEUR `self.t1` : la tâche au slot `running`, qui portera les traces.
        # Ids CAPTURÉS, jamais prédits (T-00000726, R-BANCS (i)).
        self.t1 = nouvelle(d, "le chantier", "--chantier", chantier)
        tasks(d, "start", self.t1)
        # L'EMPRUNTEUSE `self.t2` : une sous-tâche du MÊME chantier, fermée depuis pending.
        self.t2 = nouvelle(d, "une sous-tache", "--chantier", chantier)
        poser_portee(d, self.t1, [self.t1, self.t2])
        return d

    def _tracer(self, d: Path, tid: str, at: str) -> None:
        dd = d / ".agents" / "state" / "local" / "binome"
        dd.mkdir(parents=True, exist_ok=True)
        for nom in ("critic-opus", "critic-fable"):
            (dd / f"{tid}.{nom}.json").write_text(
                json.dumps({"sha": "abc1234", "at": at}), encoding="utf-8"
            )

    def _historique(self, d: Path, horodatages: list[str]) -> None:
        """UN SHA DISTINCT PAR LIGNE, et c'est le banc qui a dû l'apprendre.

        La première rédaction écrivait `sha=deadbee` partout : depuis que deux verts sur le MÊME sha comptent
        pour UN cycle (correctif du binôme), ce helper produisait un historique d'un seul cycle et le témoin
        d'expiration passait au vert sans rien prouver. Une fixture qui ne ressemble pas au réel rend un banc
        vert sur une propriété qu'il ne teste plus."""
        p = d / ".agents" / "state" / "local" / "VERIFY_STAMP.log"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            "".join(
                f"at={a}\tsha=c0ffee{i}\tmode=frozen\n"
                for i, a in enumerate(horodatages)
            ),
            encoding="utf-8",
        )

    def test_une_trace_du_cycle_COURANT_laisse_passer(self) -> None:
        """CONTRÔLE NÉGATIF, et c'est le cas NOMINAL : la revue tombe entre la
        porte précédente et celle-ci, donc elle couvre bien ce qu'on ferme."""
        d = self._depot()
        self._historique(d, ["2026-09-13T10:00:00Z", "2026-09-13T12:00:00Z"])
        self._tracer(d, self.t1, "2026-09-13T11:00:00Z")
        p = tasks(d, "done", self.t2, "--raison", "revue du cycle courant")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_une_trace_d_un_cycle_PASSE_est_REFUSEE(self) -> None:
        """LE TÉMOIN. La même trace, vieillie d'un cycle, ne couvre plus rien."""
        d = self._depot()
        self._historique(d, ["2026-09-13T10:00:00Z", "2026-09-13T12:00:00Z"])
        self._tracer(d, self.t1, "2026-09-13T09:00:00Z")
        p = tasks(d, "done", self.t2, "--raison", "trace d hier")
        sortie = p.stdout + p.stderr
        self.assertNotEqual(p.returncode, 0, "un emprunt périmé est passé")
        self.assertIn("PÉRIMÉE", sortie, "le refus ne nomme pas l'expiration")
        self.assertIn("2026-09-13T09:00:00Z", sortie,
                      "le refus ne dit pas de QUAND date la trace")

    def test_le_LOT_legitime_passe_ENTIER_sous_la_meme_porte(self) -> None:
        """LA CONTRAINTE QUI INTERDISAIT L'ISSUE 1. Une revue couvre un LOT : exiger un binôme par sous-tâche
        serait du gaspillage, et c'est ce qui aurait fait désarmer la garde."""
        d = self._depot()
        t3 = nouvelle(d, "une autre sous-tache", "--chantier", "c1")
        poser_portee(d, self.t1, [self.t1, self.t2, t3])
        self._historique(d, ["2026-09-13T10:00:00Z", "2026-09-13T12:00:00Z"])
        self._tracer(d, self.t1, "2026-09-13T11:00:00Z")
        p1 = tasks(d, "done", self.t2, "--raison", "lot 1/2")
        p2 = tasks(d, "done", t3, "--raison", "lot 2/2")
        self.assertEqual(p1.returncode, 0, p1.stdout + p1.stderr)
        self.assertEqual(p2.returncode, 0,
                         "la seconde clôture du MÊME lot a été refusée")

    def test_sans_historique_une_trace_d_UNE_HEURE_passe(self) -> None:
        """« None » veut dire PAS MESURABLE, jamais PÉRIMÉ — mais plus « jamais d'expiration » (T-00000846). Un
        dépôt neuf n'a pas d'avant-dernière porte ; la borne d'âge de 24 h prend alors le relais, et une trace
        d'une heure est dedans : l'emprunt passe, ET il est écrit au board."""
        d = self._depot()
        at = il_y_a(1)
        self._tracer(d, self.t1, at)
        p = tasks(d, "done", self.t2, "--raison", "pas d historique")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        vue = tasks(d, "list", "--task", self.t2).stdout
        self.assertIn(f"[binôme relevé sur {self.t1} @ abc1234, {at}]", vue,
                      "l'emprunt sans borne de porte n'est pas écrit au board")

    def test_sans_historique_une_trace_de_25_H_est_REFUSEE(self) -> None:
        """LE TÉMOIN DE T-00000846, et il ROUGIT sur l'ancien code. Sans `VERIFY_STAMP.log` (clone neuf chez un
        adoptant), `cycle_precedent` rendait None et le contrôle d'expiration était SAUTÉ : un binôme de la
        semaine dernière couvrait toutes les sous-tâches du chantier. Fail-open exactement là où la garde voyage."""
        d = self._depot()
        at = il_y_a(25)
        self._tracer(d, self.t1, at)
        p = tasks(d, "done", self.t2, "--raison", "trace de 25 h")
        sortie = p.stdout + p.stderr
        self.assertNotEqual(p.returncode, 0, "un emprunt de 25 h sans borne est passé")
        self.assertIn(
            "preuve empruntée PÉRIMÉE : pas deux portes vertes frozen dans "
            "VERIFY_STAMP.log, et trace de plus de 24 h — relance le binôme",
            sortie, "le refus ne nomme pas sa raison")
        self.assertIn(at, sortie, "le refus ne dit pas de QUAND date la trace")
        self.assertIn("critic-opus", sortie, "le refus ne nomme pas le remède")
        self.assertIn("--sans-binome", sortie, "le refus ne nomme pas la sortie tracée")

    def test_un_seul_cycle_connu_laisse_la_borne_d_age_mordre(self) -> None:
        """Une seule ligne d'historique n'a pas d'AVANT-dernière : même régime
        que l'absence d'historique — la borne d'âge, dans les deux sens."""
        for heures, attendu in ((1, 0), (25, 1)):
            with self.subTest(heures=heures):
                d = self._depot()
                self._historique(d, [il_y_a(0.5)])
                self._tracer(d, self.t1, il_y_a(heures))
                p = tasks(d, "done", self.t2, "--raison", "un seul cycle")
                self.assertEqual(bool(p.returncode), bool(attendu), p.stdout + p.stderr)

    def test_sans_historique_un_at_MALFORME_est_REFUSE(self) -> None:
        """`at` illisible = REFUS, jamais accepté par défaut, et jamais remplacé
        par le mtime du fichier (T-00000846). Trois formes : sans `Z` (qu'une
        comparaison de CHAÎNES rangerait comme valide), du texte, et absent."""
        for at in (il_y_a(1)[:-1], "hier soir", None):
            with self.subTest(at=at):
                d = self._depot()
                dd = d / ".agents" / "state" / "local" / "binome"
                dd.mkdir(parents=True, exist_ok=True)
                for nom in ("critic-opus", "critic-fable"):
                    charge = {"sha": "abc1234"} if at is None else {"sha": "abc1234", "at": at}
                    (dd / f"{self.t1}.{nom}.json").write_text(
                        json.dumps(charge), encoding="utf-8")
                p = tasks(d, "done", self.t2, "--raison", "at malforme")
                sortie = p.stdout + p.stderr
                self.assertNotEqual(p.returncode, 0, f"un `at` illisible ({at!r}) est passé")
                self.assertIn("preuve empruntée PÉRIMÉE", sortie)
                self.assertIn("sans date lisible", sortie)

    def _paire(self, d: Path, ats: dict[str, str], shas: dict[str, str] | None = None) -> None:
        dd = d / ".agents" / "state" / "local" / "binome"
        dd.mkdir(parents=True, exist_ok=True)
        for nom, at in ats.items():
            sha = (shas or {}).get(nom, "abc1234")
            (dd / f"{self.t1}.{nom}.json").write_text(
                json.dumps({"sha": sha, "at": at}), encoding="utf-8")

    def test_sans_historique_un_at_FUTUR_au_dela_de_5_min_est_REFUSE(self) -> None:
        """Un `at` d'une heure dans le futur rendrait l'emprunt frais pour toujours. Le refus le NOMME comme tel
        (horloge décalée), pas comme un `at` malformé : le remède à lire n'est pas le même."""
        d = self._depot()
        self._paire(d, {"critic-opus": il_y_a(-1), "critic-fable": il_y_a(-1)})
        p = tasks(d, "done", self.t2, "--raison", "at futur")
        sortie = p.stdout + p.stderr
        self.assertNotEqual(p.returncode, 0, "un `at` futur d'une heure est passé")
        self.assertIn("FUTUR", sortie, "le refus ne nomme pas la date future")
        # PAS `assertIn("critic-opus", …)` nu : la ligne REMÈDE nomme toujours
        # `critic-opus`, l'assertion serait vraie sans rien prouver.
        self.assertIn("FUTUR pour critic-fable, critic-opus", sortie,
                      "le refus ne dit pas QUELS critiques sont datés dans le futur")

    def test_sans_historique_un_at_de_36_s_d_AVANCE_passe(self) -> None:
        """TOLÉRANCE de 5 min : recul NTP, horloge WSL/VM. Une trace écrite par
        un hôte à l'horloge un peu en avance n'est pas une trace forgée."""
        d = self._depot()
        self._paire(d, {"critic-opus": il_y_a(-0.01), "critic-fable": il_y_a(-0.01)})
        p = tasks(d, "done", self.t2, "--raison", "horloge en avance")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_sans_historique_le_refus_nomme_TOUTES_les_causes(self) -> None:
        """Opus illisible, fable de 30 h, sonnet-max de 26 h : AUCUN critique frais. Le refus nomme l'`at`
        illisible ET la trace trop vieille — pas seulement la première cause trouvée."""
        d = self._depot()
        self._paire(d, {"critic-opus": "x", "critic-fable": il_y_a(30),
                        "critic-sonnet-max": il_y_a(26)})
        p = tasks(d, "done", self.t2, "--raison", "causes multiples")
        sortie = p.stdout + p.stderr
        self.assertNotEqual(p.returncode, 0, sortie)
        self.assertIn("sans date lisible", sortie)
        self.assertIn("malformé pour critic-opus)", sortie,
                      "le refus ne dit pas QUEL critique a un `at` illisible")
        self.assertIn("plus de 24 h pour critic-fable", sortie,
                      "le refus tait la cause « trop vieille »")

    def test_sans_historique_la_ligne_TRACE_marque_chaque_critique(self) -> None:
        """Quand l'âge est la SEULE cause, le refus garde la phrase pilote sans noms : c'est la ligne « Trace du
        slot » qui dit l'état de CHAQUE critique (S-00004500 : un frais suffirait, donc tous sont périmés)."""
        d = self._depot()
        self._paire(d, {"critic-opus": il_y_a(26), "critic-fable": il_y_a(25)})
        p = tasks(d, "done", self.t2, "--raison", "tout perime")
        sortie = p.stdout + p.stderr
        self.assertNotEqual(p.returncode, 0, sortie)
        ligne = next((l for l in sortie.splitlines() if l.startswith("Trace du slot")), "")
        self.assertRegex(ligne, r"critic-fable @ \S+ \(périmée\)", ligne)
        self.assertRegex(ligne, r"critic-opus @ \S+ \(périmée\)", ligne)

    def test_les_BORNES_d_age_et_d_avance(self) -> None:
        """Les deux bords, avec une marge pour la durée du test : 24 h − 2 s passe, 24 h + 2 s est refusé ;
        5 min − 10 s d'avance passe, 5 min + 10 s est refusé. Sans eux, un `<` changé en `<=` ou une tolérance
        doublée resterait vert."""
        # L'ÂGE EN HEURES, pas la date : la date se calcule APRÈS `_depot`
        # (plusieurs sous-processus), sinon le montage mange la marge de 2 s.
        cas = (
            ("24 h - 2 s", 24 - 2 / 3600, True),
            ("24 h + 2 s", 24 + 2 / 3600, False),
            ("avance 5 min - 10 s", -(300 - 10) / 3600, True),
            ("avance 5 min + 10 s", -(300 + 10) / 3600, False),
        )
        for nom, heures, passe in cas:
            with self.subTest(borne=nom):
                d = self._depot()
                at = il_y_a(heures)
                self._paire(d, {"critic-opus": at, "critic-fable": at})
                p = tasks(d, "done", self.t2, "--raison", f"borne {nom}")
                self.assertEqual(p.returncode == 0, passe, f"{nom} : {p.stdout + p.stderr}")

    def test_UN_SEUL_calcul_de_preuve_fonde_le_refus_ET_la_mention(self) -> None:
        """`set_state` appelait `binome_preuve` DEUX fois — une pour le refus, une pour la mention au board — à
        deux `now` indépendants : à 24 h pile, le refus était franchi puis la mention calculée VIDE, donc un
        emprunt clos sans que le board le dise. Le témoin rend une preuve valide au premier appel et PÉRIMÉE au
        second : il ne doit y avoir qu'un appel, et la mention doit être écrite."""
        import importlib.util
        from unittest import mock

        d = self._depot()
        self._paire(d, {"critic-opus": il_y_a(1), "critic-fable": il_y_a(1)})
        spec = importlib.util.spec_from_file_location("tasks_binome_unique", TASKS)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        self.addCleanup(sys.modules.pop, spec.name, None)
        spec.loader.exec_module(module)
        vraie = module.binome_preuve
        appels: list[int] = []

        def preuve(root, tid, data=None):
            appels.append(1)
            if len(appels) == 1:
                return vraie(root, tid, data)
            return {}, tid, {"porteur": self.t1, "borne": None, "at": "?",
                             "illisibles": [], "futurs": [], "vieux": ["critic-opus"]}

        with mock.patch.object(module, "binome_preuve", preuve):
            module.set_state(str(d), self.t2, "done", "calcul unique")
        self.assertEqual(len(appels), 1, f"binome_preuve appelée {len(appels)} fois")
        vue = tasks(d, "list", "--task", self.t2).stdout
        self.assertIn(f"[binôme relevé sur {self.t1}", vue,
                      "le refus a été franchi mais la mention au board est vide")

    def test_sans_historique_la_paire_FRAICHE_passe_et_la_perimee_est_TUE(self) -> None:
        """Trois traces : opus 1 h, fable 25 h, sonnet-max 2 h. Des critiques frais (un suffit, S-00004500) —
        l'emprunt passe ; la mention ne cite QUE ce qui l'a fondé, jamais la trace périmée de fable. La mention
        porte des SHA et une date, pas des noms : fable relit donc un SHA À ELLE (`fab1e25`), et c'est ce SHA
        qui doit être absent de la mention."""
        d = self._depot()
        self._paire(d, {"critic-opus": il_y_a(1), "critic-fable": il_y_a(25),
                        "critic-sonnet-max": il_y_a(2)},
                    shas={"critic-fable": "fab1e25"})
        p = tasks(d, "done", self.t2, "--raison", "paire fraiche")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        vue = tasks(d, "list", "--task", self.t2).stdout
        self.assertIn(f"[binôme relevé sur {self.t1} @ abc1234,", vue, vue)
        self.assertNotIn("fab1e25", vue,
                         "la trace périmée de critic-fable fonde la mention au board")

    def test_sans_historique_un_SEUL_critique_frais_suffit(self) -> None:
        """La borne d'âge compte des critiques DISTINCTS frais (`BINOME_MIN`, UN
        depuis S-00004500) : un critique frais suffit à côté d'une trace de 25 h,
        et la mention au board ne cite que lui (le SHA périmé en est absent)."""
        d = self._depot()
        dd = d / ".agents" / "state" / "local" / "binome"
        dd.mkdir(parents=True, exist_ok=True)
        for nom, h in (("critic-opus", 1), ("critic-fable", 25)):
            (dd / f"{self.t1}.{nom}.json").write_text(
                json.dumps({"sha": "abc1234" if h == 1 else "fab1e25", "at": il_y_a(h)}), encoding="utf-8")
        p = tasks(d, "done", self.t2, "--raison", "une moitie perimee")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertNotIn("fab1e25", tasks(d, "list", "--task", self.t2).stdout)

    def test_sans_historique_la_trace_DIRECTE_ancienne_passe_toujours(self) -> None:
        """La borne d'âge porte sur l'EMPRUNT seul : la preuve DIRECTE ne
        change pas (T-00000846), même vieille de trois jours et sans historique."""
        d = self._depot()
        self._tracer(d, self.t2, il_y_a(72))
        p = tasks(d, "done", self.t2, "--raison", "trace propre ancienne")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def _historique_brut(self, d: Path, lignes: list[str]) -> None:
        p = d / ".agents" / "state" / "local" / "VERIFY_STAMP.log"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("".join(lignes), encoding="utf-8")

    def test_un_verdict_LIVE_ne_deplace_PAS_la_borne(self) -> None:
        """Trouvé par le binôme. La forme NUE de `verify.sh` écrit `mode=live`, et `.githooks/pre-push` la REFUSE
        au push : un verdict qui ne vaut rien ne doit pas périmer une revue valide. Sans ce filtre — mesuré :
        binôme 11:00, forme nue 11:30, `--at` 12:00 — la clôture était refusée."""
        d = self._depot()
        self._historique_brut(d, [
            "at=2026-09-13T10:00:00Z\tsha=aaa\tmode=frozen\n",
            "at=2026-09-13T11:30:00Z\tsha=bbb\tmode=live\n",
            "at=2026-09-13T12:00:00Z\tsha=ccc\tmode=frozen\n",
        ])
        self._tracer(d, self.t1, "2026-09-13T11:00:00Z")
        p = tasks(d, "done", self.t2, "--raison", "live ne borne rien")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_une_porte_REJOUEE_ne_perime_pas_le_lot(self) -> None:
        """Deux verts sur le MÊME sha sont UN cycle. Rejouer une porte — après un flake, ou parce que le hook
        post-`done` a commité l'état — comptait pour deux cycles et périmait la revue du lot qu'on est en train
        de fermer. C'est `test_le_LOT_legitime_passe_ENTIER` qui devenait faux hors du banc."""
        d = self._depot()
        self._historique_brut(d, [
            "at=2026-09-13T10:00:00Z\tsha=aaa\tmode=frozen\n",
            "at=2026-09-13T12:00:00Z\tsha=ccc\tmode=frozen\n",
            "at=2026-09-13T12:05:00Z\tsha=ccc\tmode=frozen\n",
        ])
        self._tracer(d, self.t1, "2026-09-13T11:00:00Z")
        p = tasks(d, "done", self.t2, "--raison", "porte rejouee")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_une_trace_SANS_DATE_ne_passe_pas_pour_fraiche(self) -> None:
        """Fail-closed sur ce qu'on ne sait pas dater. Sans le `not recent`, une trace malformée rendait `""`, qui
        n'est jamais `<= borne` : elle passait donc pour éternellement fraîche. Comparés en CHAÎNES, « zzzz » et un
        `at` FUTUR passaient aussi (C-K1), sur le slot comme sur la LIVRAISON (`livraison_fraiches`, même règle)."""
        for at, livree in ((None, 0), ("zzzz", 0), ("2099-01-01T00:00:00Z", 0), ("2099-01-01T00:00:00Z", 1)):
            with self.subTest(at=at, livree=livree):
                d = self._depot()
                if livree:
                    tasks(d, "livraison", self.t1, self.t2, "--branche", "integ/l")
                self._historique(d, ["2026-09-13T10:00:00Z", "2026-09-13T12:00:00Z"])
                (dd := d / ".agents" / "state" / "local" / "binome").mkdir(parents=True, exist_ok=True)
                for nom in ("critic-opus", "critic-fable"):
                    charge = {"sha": "abc1234"} if at is None else {"sha": "abc1234", "at": at}
                    (dd / f"{self.t1}.{nom}.json").write_text(json.dumps(charge), encoding="utf-8")
                p = tasks(d, "done", self.t2, "--raison", "trace sans date")
                self.assertNotEqual(p.returncode, 0, f"une trace à `at` {at!r} est passée pour fraîche")
                self.assertIn("PÉRIMÉE", p.stdout + p.stderr)

    def test_la_trace_PROPRE_a_la_tache_n_expire_pas(self) -> None:
        """L'expiration porte sur l'EMPRUNT, pas sur la preuve directe : une tâche qui a SA trace n'emprunte rien,
        et rien ne justifie de la périmer sur la borne d'un cycle."""
        d = self._depot()
        self._historique(d, ["2026-09-13T10:00:00Z", "2026-09-13T12:00:00Z"])
        self._tracer(d, self.t2, "2026-09-13T09:00:00Z")
        p = tasks(d, "done", self.t2, "--raison", "trace propre")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)


class HistoriqueDuTamponTests(unittest.TestCase):
    """`verify.sh` doit TENIR l'historique, sinon la borne ci-dessus est vide."""

    def test_verify_ecrit_un_historique_append_only(self) -> None:
        texte = (ROOT / "core-scripts" / "verify.sh").read_text(encoding="utf-8")
        self.assertIn('>> "$STAMP.log"', texte,
                      "stamp_write n'alimente pas l'historique append-only")
        self.assertIn("T-00000592", texte,
                      "l'historique ne dit pas POURQUOI il existe")

    def test_l_historique_ne_fait_JAMAIS_rougir_une_porte_verte(self) -> None:
        """Un historique qui échoue est une perte de traçabilité, jamais un
        rouge : `stamp_write` rend 0 quoi qu'il arrive."""
        texte = (ROOT / "core-scripts" / "verify.sh").read_text(encoding="utf-8")
        bloc = texte.split("stamp_write() {", 1)[1].split("\nstamp_clear()", 1)[0]
        self.assertIn("|| true", bloc,
                      "l'écriture de l'historique n'est pas rendue inoffensive")

    def test_stamp_write_EXECUTE_ecrit_bien_deux_lignes(self) -> None:
        """LES DEUX TESTS CI-DESSUS SONT DES GREPS, et le binôme l'a dit : une ligne COMMENTÉE les satisferait.
        Celui-ci EXÉCUTE la fonction extraite de `verify.sh` et regarde le fichier produit — c'est la différence
        entre tenir la doc et tenir le comportement."""
        import shutil
        import subprocess as sp
        if shutil.which("bash") is None:
            self.skipTest("pas de bash sur cet hôte")
        texte = (ROOT / "core-scripts" / "verify.sh").read_text(encoding="utf-8")
        corps = "stamp_write() {" + texte.split("stamp_write() {", 1)[1].split(
            "\nstamp_clear()", 1)[0]
        d = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        script = (
            'STAMP="%s/VERIFY_STAMP"\nVERIFY_INNER=0\n%s\n'
            'stamp_write aaaaaaa frozen 1\nstamp_write aaaaaaa frozen 1\n'
        ) % (d, corps)
        r = sp.run(["bash", "-c", script], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        log = (d / "VERIFY_STAMP.log").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(log), 2, f"historique attendu à 2 lignes : {log}")
        for ligne in log:
            self.assertIn("sha=aaaaaaa", ligne)
            self.assertIn("mode=frozen", ligne)
            self.assertTrue(ligne.startswith("at="), ligne)


class DoctrineTests(unittest.TestCase):
    def test_the_skill_no_longer_calls_the_refusal_DOCTRINAL(self) -> None:
        """C'est la phrase que ce lot rend fausse. La laisser enseignerait le contraire de ce que le code tient —
        et une doc qui affirme une garantie que le code ne tient pas empêche de voir le défaut ; ici c'est
        l'inverse, et une doc qui NIE une garantie tenue fait qu'on ne s'y fie pas."""
        texte = SKILL.read_text(encoding="utf-8")
        self.assertNotIn("DOCTRINAL et non mécanique", texte)
        self.assertIn("BINOME_REQUIRED", texte, "la skill ne nomme pas la garde")


# ---------------------------------------------------------------------------
# T-00001064 — la jambe « reprise » de `done` (S-00003393)
# ---------------------------------------------------------------------------
AFFIRMATION_GUARD = ROOT / ".claude" / "hooks" / "affirmation-guard.sh"
TASKS_ETATS = ROOT / ".agents" / "bin" / "tasks_etats.py"
LOT_E1 = "docs/interne/chantier/lots/LOT-E1-REPRISE.md"
LOT_E2 = "docs/interne/chantier/lots/LOT-E2-REPRISE.md"
PROMPT_VIVANT = "docs/interne/chantier/reprises/prompt_de_reprise_et_planification.md"
ARCHIVE_P10 = "docs/interne/chantier/reprises/REPRISE-P10.md"
PLAN_T1 = "docs/tasks/T-00000001-plan.md"
LOT_E97 = "docs/tasks/LOT-E97-REPRISE.md"
#: Les fixtures COMMITÉES de chaque dépôt jetable de `BinomeRepriseTests`.
FIXTURES = {
    "PLAN-ETAT.md": "routeur\n", "PLAN-ETAT-DETAIL.md": "historique\n",
    LOT_E1: "reprise du lot\n", PROMPT_VIVANT: "prompt vivant\n",
    ARCHIVE_P10: "archive\n", PLAN_T1: "plan\n", LOT_E97: "reprise qui voyage\n",
}
#: Les variables par lesquelles git se laisse désigner un AUTRE dépôt : le banc
#: les retire de chaque git qu'il lance. C'est le NOYAU de la liste de la jambe ;
#: la jambe purge EN PLUS `GIT_CONFIG_GLOBAL`/`_SYSTEM`, `GIT_EXEC_PATH`,
#: `GIT_NO_REPLACE_OBJECTS` et `GIT_*_PATHSPECS`, que le banc garde (il pose
#: lui-même `GIT_CONFIG_GLOBAL` : `_ignore_personnel`, `_b19`).
_REDIRECTIONS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
                 "GIT_COMMON_DIR", "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE",
                 "GIT_PREFIX", "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT")


def _env_banc(**en_plus: str) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in _REDIRECTIONS
           and not k.startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_"))}
    env.update(en_plus)
    return env


def _motifs(texte: str, nom: str) -> tuple:
    """Le tuple `nom = (...)` de `texte`, par `ast.literal_eval` ; () s'il manque."""
    m = re.search(rf"^{nom} = (\([^)]*\))", texte, re.M)
    return ast.literal_eval(m.group(1)) if m else ()


#: Les mutants de la jambe : (ancres de `tasks_etats.py` → remplacements). Chaque
#: ancre est un FRAGMENT DE LITTÉRAL présent une fois exactement (jamais un
#: commentaire) ; `_variante` l'asserte.
_SUIVIS_DIFF = '"--no-renames", sha, "--", *spec).split("\\0")'
MUTANTS_JAMBE = {
    "MUT-B1": [('    return ("ok", sorted({c for c in changes + neufs if c and surveille(c)}))',
                '    return ("ok", [])')],
    "MUT-B2": [('"--no-renames", sha, "--", *spec)', '"--no-renames", "HEAD", "--", *spec)')],
    "MUT-B3": [("changes + neufs", "changes")],
    "MUT-B4": [('        if issue == "inerte":\n            return None',
                '        if issue in ("inerte", "non-mesuré"):\n            return None')],
    "MUT-B5": [('    "docs/tasks/LOT-*-REPRISE.md",\n    "PLAN-ETAT.md",\n',
                '    "docs/tasks/*",\n    "PLAN-ETAT.md",\n')],
    "MUT-B6": [('    "PLAN-ETAT.md",\n)', ")")],
    "MUT-B7": [("    if len(a_jour) >= exige:\n        return None",
                "    if len(a_jour) >= 0:\n        return None")],
    "MUT-B8": [('        if state == "done" and not sans_binome:\n', '        if state == "done":\n')],
    "MUT-B9": [("    if preuve is None:\n        return None\n",
                "    if preuve is None:\n        preuve = binome_preuve(root, tid, data)\n")],
    "MUT-B11": [("            refus = binome_refusal(root, tid, preuve) or binome_reprise_refusal(\n"
                 "                root, tid, preuve, data, exige=exige)\n", "            refus = binome_refusal(root, tid, preuve)\n")],
    "MUT-B12": [('    if not os.path.lexists(os.path.join(racine, ".git")):\n'
                 '        return ("inerte", "pas de .git à la racine")\n', "")],
    "MUT-B13": [('"-c", "core.quotePath=false", "diff", "-z", "--name-only",',
                 '"diff", "--name-only",'),
                (_SUIVIS_DIFF, _SUIVIS_DIFF.replace('.split("\\0")', ".splitlines()"))],
    "MUT-B13z": [('"diff", "-z", "--name-only",', '"diff", "--name-only",'),
                 (_SUIVIS_DIFF, _SUIVIS_DIFF.replace('.split("\\0")', ".splitlines()"))],
    "MUT-B13'": [("    vus, porteur, _perime = preuve\n",
                  "    _v, porteur, _perime = preuve\n    vus = binome_trace(root, tid)\n")],
    "MUT-B14": [('    if not present():\n        return ("ok", [])\n', "")],
    "MUT-B15": [("        + purge\n", "")],
    "MUT-B16": [('    except RuntimeError as exc:\n        return ("non-mesuré", str(exc))\n',
                 '    except RuntimeError as exc:\n        return ("inerte" if str(exc).'
                 'startswith("rev-parse") else "non-mesuré", str(exc))\n')],
    "MUT-B17": [("os.path.samefile(haut, racine)", "haut == racine")],
    "MUT-B17r": [("os.path.samefile(haut, racine)",
                  "os.path.realpath(haut) == os.path.realpath(racine)")],
    "MUT-B18": [('"-c", "core.excludesFile=" + os.devnull, ', "")],
    "MUT-B19": [('"--no-renames", sha, "--", *spec)', '"--no-renames", sha)')],
    "MUT-B20": [('"--no-renames", ', "")],
    "MUT-B21": [("    env = {k: v for k, v in os.environ.items() if k not in redirections\n"
                 '           and not k.startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_"))}\n',
                 "    env = dict(os.environ)\n")],
    "MUT-B22": [("        if r.returncode != 0:\n",
                 '        if r.returncode != 0 and verbe != "diff":\n')],
    "MUT-B23": [('    except Exception as exc:\n        return ("non-mesuré", '
                 'f"{type(exc).__name__} : {exc}")\n', "")],
    "MUT-B24": [("timeout=delai, check=False", "check=False")],
    "MUT-B25": [("        if not os.path.samefile(haut, racine):\n            return "
                 '("non-mesuré", f"toplevel git {haut} différent de la racine {racine}")\n', "")],
    "MUT-B26": [("for p in REPRISES_BINOME})",
                 'for p in REPRISES_BINOME if "prompt_" not in p})')],
    "MUT-B27": [('sha = t.get("sha") if isinstance(t, dict) else None', 'sha = t.get("sha")')],
    "MUT-B28": [('"GIT_CONFIG_GLOBAL", ', "")],
    # Le sha court relu comme un NOM : `diff <court>` suit un tag homonyme.
    "MUT-B29": [("        sha = commits[0]\n", "")],
}


class BinomeRepriseTests(unittest.TestCase):
    """LA REVUE DE `done` DOIT AVOIR VU L'ÉTAT COURANT DES FICHIERS DE REPRISE (T-00001064, S-00003393) —
    `binome_reprise_refusal` et `reprise_changee_depuis`, dans `tasks_etats.py`.

    Dépôt jetable INITIALISÉ SOUS GIT, `BINOME_REQUIRED` armé, `FIXTURES` commitées par
    `git -c core.excludesFile=<os.devnull> add -A` (HEAD avancé et fixtures suivies ASSERTÉS : sous un ignore
    personnel, un `git add` nu n'indexe rien en silence), traces à la forme RÉELLE
    `{"sha": <HEAD court>, "at": il_y_a(1)}`. `set_state` EN PROCESSUS, sur le module réel et sur des VARIANTES
    (copie de `tasks*.py`, `plan_cible.py`, `plan_depends.py`, une ancre de `tasks_etats.py` remplacée,
    chargement par `spec_from_file_location`) ; la variante NON mutée rend le verdict du réel sur B1 et B2.
    Chaque mutant de `MUTANTS_JAMBE` rend l'AUTRE issue sur ses scénarios (`test_mutants_rendent_l_autre_issue`).
    Mutant du BANC (MUT-F, joué sur une copie hors de ce fichier) : retirer `-c core.excludesFile` de `_depot`
    fait rougir B4'. Le git FACTICE (`_git_factice`) est un script `sh` : sauté sous `nt`, dit."""

    def setUp(self) -> None:
        self.reel = self._charger(TASKS, "tasks_binome_reprise_reel")

    # ---- chargement : le réel et les variantes --------------------------------
    @staticmethod
    def _charger(chemin: Path, nom: str):
        spec = importlib.util.spec_from_file_location(nom, chemin)
        assert spec is not None and spec.loader is not None, chemin
        module = importlib.util.module_from_spec(spec)
        sys.modules[nom] = module
        spec.loader.exec_module(module)
        return module

    def _variante(self, *paires: tuple[str, str], fichier: str = "tasks_etats.py"):
        dossier = Path(tempfile.mkdtemp(prefix="binome-variante-"))
        self.addCleanup(shutil.rmtree, dossier, True)
        bin_ = ROOT / ".agents" / "bin"
        for f in [*bin_.glob("tasks*.py"), bin_ / "plan_cible.py", bin_ / "plan_depends.py"]:
            shutil.copy2(f, dossier / f.name)
        cible = dossier / fichier
        texte = cible.read_text(encoding="utf-8")
        for ancre, remplacement in paires:
            self.assertEqual(texte.count(ancre), 1, f"ancre de variante ambiguë ou absente : {ancre!r}")
            texte = texte.replace(ancre, remplacement)
        cible.write_text(texte, encoding="utf-8")
        return self._charger(dossier / "tasks.py", f"tasks_variante_{dossier.name}")

    # ---- dépôt, traces, clôture ---------------------------------------------
    @staticmethod
    def _git(d: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(d), *args], capture_output=True, text=True,
                              check=False, env=env or _env_banc())

    def _head(self, d: Path) -> str:
        return self._git(d, "rev-parse", "--short", "HEAD").stdout.strip()

    def _commit(self, d: Path, fichiers: dict, env: dict | None = None) -> None:
        avant = self._head(d)
        for chemin, texte in fichiers.items():
            p = d / chemin
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(texte, encoding="utf-8")
        self._git(d, "-c", "core.excludesFile=" + os.devnull, "add", "-A", "--", *fichiers, env=env)
        self._git(d, "commit", "-q", "-m", "fixtures", env=env)
        self.assertNotEqual(self._head(d), avant, f"HEAD n'a pas avancé : {sorted(fichiers)}")
        for chemin in fichiers:
            self.assertEqual(self._git(d, "ls-files", "--error-unmatch", "--", chemin,
                                       env=env).returncode, 0, f"{chemin} n'est pas suivi")

    def _depot(self, en_plus: dict | None = None, base: Path | None = None,
               fixtures: dict | None = None) -> Path:
        d = base or Path(tempfile.mkdtemp(prefix="binome-reprise-"))
        if base is None:
            self.addCleanup(shutil.rmtree, d, True)
        env = _env_banc(**(en_plus or {}))
        self._git(d, "init", "-q", env=env)
        for cle, val in (("user.email", "banc@example.invalid"), ("user.name", "Banc"),
                         ("commit.gpgsign", "false")):
            self._git(d, "config", cle, val, env=env)
        self._commit(d, FIXTURES if fixtures is None else fixtures, env)
        self._armer(d)
        # `self.t1` : la tâche à clore du DERNIER dépôt monté, id CAPTURÉ (T-00000726,
        # R-BANCS (i)) ; `_trace`, `_paire` et `_clore` la visent par défaut.
        self.t1 = nouvelle(d, "une tache a clore", "--chantier", "ch")
        return d

    @staticmethod
    def _armer(d: Path) -> None:
        g = d / ".agents" / "state" / "gates" / "BINOME_REQUIRED"
        g.parent.mkdir(parents=True, exist_ok=True)
        g.write_text("arme", encoding="utf-8")

    def _trace(self, d: Path, nom: str, sha: str, tid: str | None = None) -> None:
        tid = self.t1 if tid is None else tid
        dd = d / ".agents" / "state" / "local" / "binome"
        dd.mkdir(parents=True, exist_ok=True)
        (dd / f"{tid}.{nom}.json").write_text(json.dumps({"sha": sha, "at": il_y_a(1)}),
                                              encoding="utf-8")

    def _paire(self, d: Path, sha: str | None = None, tid: str | None = None) -> str:
        sha = self._head(d) if sha is None else sha
        for nom in ("critic-opus", "critic-fable"):
            self._trace(d, nom, sha, tid)
        return sha

    def _clore(self, mod, d, tid: str | None = None, sans_binome: str = "",
               env: dict | None = None) -> tuple[str, str]:
        tid = self.t1 if tid is None else tid
        try:
            with mock.patch.dict(os.environ, env or {}):
                sortie = mod.set_state(str(d), tid, "done", stage="fini", sans_binome=sans_binome)
        except mod.BoardError as exc:
            msg = str(exc)
            if "[REPRISE NON MESURÉE" in msg:
                return "refus-non-mesuré", msg
            return ("refus-périmé" if "périmé :" in msg else "refus-autre"), msg
        except Exception as exc:  # noqa: BLE001 — une exception est une issue nommée
            return f"exception:{type(exc).__name__}", repr(exc)
        return "passe", sortie

    def _ignore_personnel(self) -> dict:
        base = Path(tempfile.mkdtemp(prefix="binome-home-"))
        self.addCleanup(shutil.rmtree, base, True)
        (base / "home").mkdir()
        ignore = base / "xdg" / "git" / "ignore"
        ignore.parent.mkdir(parents=True)
        ignore.write_text("LOT-*\nlots/\n", encoding="utf-8")
        globale = base / "gitconfig"
        globale.write_text(f"[core]\n\texcludesFile = {ignore.as_posix()}\n", encoding="utf-8")
        return {"HOME": str(base / "home"), "XDG_CONFIG_HOME": str(base / "xdg"),
                "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": str(globale)}

    def _git_factice(self, mode: str) -> dict:
        """Un `git` FACTICE en tête de PATH : saute les `-c k=v`, échoue sur
        `rev-parse` (rc 128) ou sur `diff` (rc 3), ou PEND sur `diff`, et délègue
        sinon au vrai git."""
        reel = shutil.which("git")
        self.assertIsNotNone(reel, "git introuvable")
        dossier = Path(tempfile.mkdtemp(prefix="git-factice-"))
        self.addCleanup(shutil.rmtree, dossier, True)
        cas = {
            "rev-parse": 'if [ "$v" = rev-parse ]; then echo "fatal: detected dubious '
                         'ownership in repository" >&2; exit 128; fi\n',
            "diff": 'if [ "$v" = diff ]; then echo "fatal: diff factice" >&2; exit 3; fi\n',
            "pend": 'if [ "$v" = diff ]; then exec sleep 3; fi\n',
        }[mode]
        script = dossier / "git"
        script.write_text(
            "#!/bin/sh\nv=''\nsauter=0\n"
            'for a in "$@"; do\n'
            '  if [ "$sauter" = 1 ]; then sauter=0; continue; fi\n'
            '  if [ "$a" = -c ]; then sauter=1; continue; fi\n'
            '  v="$a"; break\ndone\n' + cas + f'exec "{reel}" "$@"\n', encoding="utf-8")
        script.chmod(0o755)
        return {"PATH": f"{dossier}{os.pathsep}{os.environ.get('PATH', '')}"}

    # ---- scénarios : chacun crée son dépôt et rend (issue, message) ------------
    def _b1(self, mod):
        d = self._depot()
        self._paire(d)
        return self._clore(mod, d)

    def _b2(self, mod):
        d = self._depot()
        self._paire(d)
        self._commit(d, {LOT_E1: "reprise du lot\nligne\n"})
        return self._clore(mod, d)

    def _b2b(self, mod):
        d = self._depot()
        self._paire(d)
        (d / "docs/interne/chantier/reprises").mkdir(parents=True, exist_ok=True)
        self._git(d, "mv", LOT_E1, "docs/interne/chantier/reprises/LOT-E1-REPRISE.md")
        self._git(d, "commit", "-q", "-m", "rangement")
        return self._clore(mod, d)

    def _b2c(self, mod):
        d = self._depot()
        self._paire(d)
        self._git(d, "mv", LOT_E97, "docs/tasks/E97-archive.md")
        self._git(d, "commit", "-q", "-m", "renommage hors motif")
        return self._clore(mod, d)

    def _b2d(self, mod):
        d = self._depot()
        self._paire(d)
        self._commit(d, {PROMPT_VIVANT: "prompt vivant\nligne\n"})
        return self._clore(mod, d)

    def _b3(self, mod):
        d = self._depot()
        self._paire(d)
        (d / LOT_E1).write_text("reprise du lot\nsale\n", encoding="utf-8")
        return self._clore(mod, d)

    def _b4(self, mod):
        d = self._depot()
        self._paire(d)
        (d / LOT_E2).write_text("reprise neuve\n", encoding="utf-8")
        return self._clore(mod, d)

    def _b4prime(self, mod):
        env = self._ignore_personnel()
        d = self._depot(en_plus=env)
        self._paire(d)
        (d / LOT_E2).write_text("reprise neuve\n", encoding="utf-8")
        sonde = self._git(d, "ls-files", "--others", "--exclude-standard", "--",
                          "docs/interne/chantier/lots", env=_env_banc(**env))
        self.assertNotIn("LOT-E2", sonde.stdout,
                         "SONDE : l'ignore personnel ne cache rien — B4' serait vacant")
        return self._clore(mod, d, env=env)

    def _b5(self, mod):
        d = self._depot()
        self._paire(d)
        self._commit(d, {PLAN_T1: "plan\nretouche\n", ARCHIVE_P10: "archive\nretouche\n",
                         "PLAN-ETAT-DETAIL.md": "historique\nligne\n"})
        return self._clore(mod, d)

    def _b6(self, mod):
        d = self._depot()
        self._paire(d)
        self._commit(d, {"PLAN-ETAT.md": "routeur\nligne\n"})
        return self._clore(mod, d)

    def _b7(self, mod):
        d = self._depot()
        self._paire(d)
        self._commit(d, {LOT_E1: "reprise du lot\nligne\n"})
        issue, msg = self._clore(mod, d, sans_binome="décision du pilote tracée")
        if issue == "passe":
            vue = tasks(d, "list", "--task", self.t1).stdout
            self.assertIn("SANS BINÔME", vue, "la sortie n'est pas VISIBLE au board")
        return issue, msg

    def _b8(self, mod, frais: int = 1):
        d = self._depot()
        ancien = self._head(d)
        self._commit(d, {"PLAN-ETAT.md": "routeur\nligne\n"})
        neuf = self._head(d)
        for i, nom in enumerate(("critic-opus", "critic-fable", "critic-sonnet-max")):
            self._trace(d, nom, neuf if i >= 3 - frais else ancien)
        return self._clore(mod, d)

    def _b9a(self, mod):
        base = Path(tempfile.mkdtemp(prefix="binome-englobant-"))
        self.addCleanup(shutil.rmtree, base, True)
        self._git(base, "init", "-q")
        d = base / "sous"
        for chemin in ("PLAN-ETAT.md", LOT_E1):
            (d / chemin).parent.mkdir(parents=True, exist_ok=True)
            (d / chemin).write_text("non suivi\n", encoding="utf-8")
        self._armer(d)
        self.t1 = nouvelle(d, "une tache a clore", "--chantier", "ch")
        self._paire(d, sha="abc1234")
        issue, msg = self._clore(mod, d)
        if issue == "passe":
            self.assertNotIn("REPRISE", tasks(d, "list", "--task", self.t1).stdout)
        return issue, msg

    def _b9_sha(self, mod, sha: str):
        d = self._depot()
        self._paire(d, sha=sha)
        return self._clore(mod, d)

    def _b9_factice(self, mod, mode: str):
        d = self._depot()
        self._paire(d)
        return self._clore(mod, d, env=self._git_factice(mode))

    def _b9e2(self, mod):
        d = self._depot()
        self._paire(d)
        env = {"GIT_TEST_ASSUME_DIFFERENT_OWNER": "1"}
        if self._git(d, "rev-parse", "--show-toplevel", env=_env_banc(**env)).returncode == 0:
            self.skipTest("ce git ignore GIT_TEST_ASSUME_DIFFERENT_OWNER (ou safe.directory le couvre)")
        return self._clore(mod, d, env=env)

    def _b9f(self, mod):
        d = self._depot()
        self._paire(d)
        vide = Path(tempfile.mkdtemp(prefix="path-vide-"))
        self.addCleanup(shutil.rmtree, vide, True)
        return self._clore(mod, d, env={"PATH": str(vide)})

    def _b9g(self, mod):
        base = Path(tempfile.mkdtemp(prefix="binome-englobant-"))
        self.addCleanup(shutil.rmtree, base, True)
        self._git(base, "init", "-q")
        for cle, val in (("user.email", "banc@example.invalid"), ("user.name", "Banc"),
                         ("commit.gpgsign", "false")):
            self._git(base, "config", cle, val)
        self._commit(base, {"sous/PLAN-ETAT.md": "routeur\n"})
        d = base / "sous"
        (d / ".git").mkdir()
        self._armer(d)
        self.t1 = nouvelle(d, "une tache a clore", "--chantier", "ch")
        self._paire(d, sha=self._head(base))
        return self._clore(mod, d)

    def _b9h(self, mod):
        d = Path(tempfile.mkdtemp(prefix="binome-gitfile-"))
        self.addCleanup(shutil.rmtree, d, True)
        (d / ".git").write_text("gitdir: /inexistant\n", encoding="utf-8")
        (d / "PLAN-ETAT.md").write_text("routeur\n", encoding="utf-8")
        self._armer(d)
        self.t1 = nouvelle(d, "une tache a clore", "--chantier", "ch")
        self._paire(d, sha="abc1234")
        return self._clore(mod, d)

    def _b9i(self, mod, forme: str):
        parent = Path(tempfile.mkdtemp(prefix="binome-formes-"))
        self.addCleanup(shutil.rmtree, parent, True)
        d = parent / "dépôt-x"
        d.mkdir()
        self._depot(base=d)
        self._paire(d)
        self._commit(d, {"PLAN-ETAT.md": "routeur\nligne\n"})
        if forme == "lien":
            racine = parent / "lien"
            try:
                os.symlink(d, racine)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"os.symlink refusé ici : {exc}")
        elif forme == "casse":
            racine = parent / "DÉPÔT-X"
            if not racine.exists():
                self.skipTest("FS sensible à la casse : la racine en autre casse n'existe pas")
        else:
            racine = Path(unicodedata.normalize("NFD", str(d)))
            if not racine.exists():
                self.skipTest("FS sensible à la normalisation : la forme NFD n'existe pas")
        return self._clore(mod, racine)

    def _b9j(self, mod):
        d = self._depot()
        self._paire(d)
        debut = time.monotonic()
        try:
            with mock.patch.dict(os.environ, self._git_factice("pend")):
                issue, detail = mod.reprise_changee_depuis(str(d), self._head(d), delai=0.5)
        except Exception as exc:  # noqa: BLE001
            return f"exception:{type(exc).__name__}", repr(exc)
        duree = time.monotonic() - debut
        return issue, f"{detail} ({duree:.2f} s)" if duree < 2.5 else f"LENT {duree:.2f} s"

    def _b10(self, mod):
        d = self._depot()
        (d / ".agents" / "state" / "gates" / "BINOME_REQUIRED").unlink()
        ancien = self._head(d)
        self._commit(d, {LOT_E1: "reprise du lot\nligne\n"})
        self._paire(d, sha=ancien)
        return self._clore(mod, d)

    def _emprunt(self) -> Path:
        """`self.t1` = le slot (démarré), `self.t2` = la sous-tache qui emprunte, ids CAPTURÉS."""
        d = self._depot()
        self.t2 = nouvelle(d, "la sous-tache", "--chantier", "ch")
        tasks(d, "start", self.t1)
        poser_portee(d, self.t1, [self.t1, self.t2])
        return d

    def _b11(self, mod):
        d = self._emprunt()
        self._paire(d, tid=self.t1)
        self._commit(d, {LOT_E1: "reprise du lot\nligne\n"})
        return self._clore(mod, d, tid=self.t2)

    def _b11bis(self, mod):
        d = self._emprunt()
        self._paire(d, tid=self.t2)
        self._commit(d, {LOT_E1: "reprise du lot\nligne\n"})
        self._paire(d, tid=self.t1)
        issue, msg = self._clore(mod, d, tid=self.t2)
        if f"tasks.py binome-purge {self.t2}" not in msg:
            return "refus-sans-purge" if issue.startswith("refus") else issue, msg
        p = tasks(d, "binome-purge", self.t2)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        apres, msg2 = self._clore(mod, d, tid=self.t2)
        if apres == "passe":
            self.assertIn(f"binôme relevé sur {self.t1}",
                          tasks(d, "list", "--task", self.t2).stdout)
        return f"{issue}+purge→{apres}", msg + "\n---\n" + msg2

    def _b13(self, mod, nom: str):
        d = self._depot()
        self._paire(d)
        self._commit(d, {f"docs/interne/chantier/lots/{nom}": "reprise\n"})
        return self._clore(mod, d)

    def _b14(self, mod, sonnet: bool = False):
        d = self._depot()
        if sonnet:
            self._paire(d)
            self._trace(d, "critic-sonnet-max", "?")
            return self._clore(mod, d)
        ancien = self._head(d)
        self._commit(d, {"PLAN-ETAT.md": "routeur\nligne\n"})
        self._trace(d, "critic-opus", ancien)
        self._trace(d, "critic-fable", "?")
        return self._clore(mod, d)

    def _b15(self, mod):
        d = self._depot(fixtures={"src/x.txt": "rien de surveillé\n"})
        self._paire(d, sha="?")
        return self._clore(mod, d)

    def _b16(self, mod, perime: bool):
        leurre = Path(tempfile.mkdtemp(prefix="binome-leurre-"))
        self.addCleanup(shutil.rmtree, leurre, True)
        self._git(leurre, "init", "-q")
        for cle, val in (("user.email", "banc@example.invalid"), ("user.name", "Banc"),
                         ("commit.gpgsign", "false")):
            self._git(leurre, "config", cle, val)
        self._commit(leurre, {"autre-histoire.txt": "leurre\n"})
        d = self._depot()
        self._paire(d)
        if perime:
            self._commit(d, {LOT_E1: "reprise du lot\nligne\n"})
        return self._clore(mod, d, env={"GIT_DIR": str(leurre / ".git")})

    def _b17(self, mod):
        d = self._depot(fixtures={**FIXTURES, "src/x.txt": "non surveillé\n"})
        self._paire(d)
        # Aucune entrée « racily clean » : les fixtures reculent de 100 s et l'index
        # est rafraîchi AVANT la mesure ; seul `src/x.txt` (non surveillé) a
        # ensuite un stat sali, par `os.utime` — jamais `sleep`.
        passe = time.time() - 100
        for chemin in [*FIXTURES, "src/x.txt"]:
            os.utime(d / chemin, (passe, passe))
        self._git(d, "update-index", "-q", "--refresh")
        t = time.time() + 100
        os.utime(d / "src/x.txt", (t, t))
        index = d / ".git" / "index"
        avant = hashlib.sha256(index.read_bytes()).hexdigest()
        issue, msg = self._clore(mod, d)
        apres = hashlib.sha256(index.read_bytes()).hexdigest()
        return ("index identique" if avant == apres else "index réécrit"), f"{issue} : {msg}"

    def _b18(self, mod):
        """Une trace JSON VALIDE mais pas un objet (une chaîne) : lue par
        `binome_trace`, elle atteint la jambe sous le verrou du board."""
        d = self._depot()
        self._trace(d, "critic-opus", "?")  # pas à jour non plus : UN suffirait (S-00004500)
        dd = d / ".agents" / "state" / "local" / "binome"
        (dd / f"{self.t1}.critic-fable.json").write_text(json.dumps("pas un objet"),
                                                          encoding="utf-8")
        return self._clore(mod, d)

    def _b19(self, mod):
        """Un `safe.directory = *` posé par un `GIT_CONFIG_GLOBAL` d'environnement,
        sous propriétaire douteux SIMULÉ : la jambe purge la variable, donc git
        reste refusé (HOME, XDG et système isolés : rien d'autre ne le couvre)."""
        d = self._depot()
        self._paire(d)
        base = Path(tempfile.mkdtemp(prefix="binome-cfg-"))
        self.addCleanup(shutil.rmtree, base, True)
        (base / "home").mkdir()
        (base / "xdg").mkdir()
        globale = base / "gitconfig"
        globale.write_text("[safe]\n\tdirectory = *\n", encoding="utf-8")
        env = {"GIT_TEST_ASSUME_DIFFERENT_OWNER": "1", "HOME": str(base / "home"),
               "XDG_CONFIG_HOME": str(base / "xdg"), "GIT_CONFIG_NOSYSTEM": "1"}
        if self._git(d, "rev-parse", "--show-toplevel", env=_env_banc(**env)).returncode == 0:
            self.skipTest("ce git ignore GIT_TEST_ASSUME_DIFFERENT_OWNER")
        couvert = _env_banc(**env, GIT_CONFIG_GLOBAL=str(globale))
        if self._git(d, "rev-parse", "--show-toplevel", env=couvert).returncode != 0:
            self.skipTest("ce git ne lit pas safe.directory dans GIT_CONFIG_GLOBAL")
        return self._clore(mod, d, env={**env, "GIT_CONFIG_GLOBAL": str(globale)})

    def _b29(self, mod):
        """Un TAG nommé comme le sha COURT tracé, posé sur le commit POSTÉRIEUR qui salit `PLAN-ETAT.md` (constat
        T2 du binôme de fin E-24) : lu comme un NOM, `diff <court>` partirait du tag, ne verrait rien, et la
        revue passerait « à jour » à tort. La sonde prouve que git, lui, préfère bien le tag."""
        d = self._depot()
        court = self._paire(d)
        self._commit(d, {"PLAN-ETAT.md": "routeur\nligne\n"})
        self._git(d, "tag", court, "HEAD")
        plein = self._git(d, "rev-parse", "HEAD").stdout.strip()
        self.assertEqual(self._git(d, "rev-parse", court).stdout.strip(), plein,
                         "SONDE : le tag homonyme ne passe pas devant l'objet — B29 serait vacant")
        return self._clore(mod, d)

    def _parite(self, texte_etats: str) -> list:
        hook = _motifs(AFFIRMATION_GUARD.read_text(encoding="utf-8"), "REPRISES")
        binome = _motifs(texte_etats, "REPRISES_BINOME")
        fautes = [] if hook else ["REPRISES introuvable dans la garde"]
        if tuple(binome) != tuple(hook) + ("PLAN-ETAT.md",):
            fautes.append(f"REPRISES_BINOME {binome!r} ≠ REPRISES {hook!r} + PLAN-ETAT.md")
        if "PLAN-ETAT-DETAIL.md" in binome:
            fautes.append("PLAN-ETAT-DETAIL.md ne doit pas être dans REPRISES_BINOME")
        return fautes

    # ---- le module réel ------------------------------------------------------
    def test_B1_nominal_passe(self) -> None:
        self.assertEqual(self._b1(self.reel)[0], "passe")

    def test_B2_reprise_commitee_apres_la_paire_refus_nomme(self) -> None:
        issue, msg = self._b2(self.reel)
        self.assertEqual(issue, "refus-périmé", msg)
        for attendu in (LOT_E1, "critic-opus @ ", "critic-fable @ ", "décision du pilote",
                        "n'entre dans AUCUN des trois"):
            self.assertIn(attendu, msg)

    def test_B2b_B2c_B2d_deplacements_et_prompt_vivant_refuses(self) -> None:
        self.assertEqual(self._b2b(self.reel)[0], "refus-périmé")
        self.assertEqual(self._b2c(self.reel)[0], "refus-périmé")
        issue, msg = self._b2d(self.reel)
        self.assertEqual(issue, "refus-périmé", msg)
        self.assertIn(PROMPT_VIVANT, msg)

    def test_B3_B4_sale_et_neuve_refusees(self) -> None:
        self.assertEqual(self._b3(self.reel)[0], "refus-périmé")
        issue, msg = self._b4(self.reel)
        self.assertEqual(issue, "refus-périmé", msg)
        self.assertIn(LOT_E2, msg)

    def test_B4prime_ignore_personnel_neutralise(self) -> None:
        issue, msg = self._b4prime(self.reel)
        self.assertEqual(issue, "refus-périmé", msg)
        self.assertIn(LOT_E2, msg)

    def test_B5_plan_archive_detail_passent(self) -> None:
        self.assertEqual(self._b5(self.reel)[0], "passe")

    def test_B6_plan_etat_refuse(self) -> None:
        issue, msg = self._b6(self.reel)
        self.assertEqual(issue, "refus-périmé", msg)
        self.assertIn("PLAN-ETAT.md", msg)

    def test_B7_sans_binome_passe_et_se_voit(self) -> None:
        self.assertEqual(self._b7(self.reel)[0], "passe")

    def test_B8_un_a_jour_exige(self) -> None:
        self.assertEqual(self._b8(self.reel, frais=0)[0], "refus-périmé")
        self.assertEqual(self._b8(self.reel, frais=1)[0], "passe")

    def test_B9a_hors_git_inerte_et_muet(self) -> None:
        self.assertEqual(self._b9a(self.reel)[0], "passe")

    def test_B9b_B9c_sha_illisible_ou_inconnu_refus_nomme(self) -> None:
        issue, msg = self._b9_sha(self.reel, "?")
        self.assertEqual(issue, "refus-non-mesuré", msg)
        self.assertIn("[REPRISE NON MESURÉE : sha tracé illisible", msg)
        self.assertIn("rends le dépôt lisible par git", msg)
        issue, msg = self._b9_sha(self.reel, "deadbeef")
        self.assertEqual(issue, "refus-non-mesuré", msg)
        # Lu en PRÉFIXE d'objet (constat T2 du binôme de fin E-24) : un sha
        # inconnu n'est plus un `cat-file` en échec, c'est zéro commit nommé.
        self.assertIn("sha tracé deadbeef : 0 commit(s) de ce préfixe", msg)

    @unittest.skipUnless(os.name != "nt", "le git factice est un script sh")
    def test_B9d_B9e_git_factice_en_echec_refus_nomme(self) -> None:
        issue, msg = self._b9_factice(self.reel, "diff")
        self.assertEqual(issue, "refus-non-mesuré", msg)
        self.assertIn("diff en échec", msg)
        issue, msg = self._b9_factice(self.reel, "rev-parse")
        self.assertEqual(issue, "refus-non-mesuré", msg)
        self.assertIn("rev-parse en échec", msg)

    def test_B9e2_proprietaire_douteux_reel(self) -> None:
        issue, msg = self._b9e2(self.reel)
        self.assertEqual(issue, "refus-non-mesuré", msg)
        self.assertIn("rev-parse en échec", msg)

    def test_B9f_git_absent_refus_nomme_sans_exception(self) -> None:
        issue, msg = self._b9f(self.reel)
        self.assertEqual(issue, "refus-non-mesuré", msg)
        self.assertIn("FileNotFoundError", msg)

    def test_B9g_git_vide_sous_un_depot_englobant(self) -> None:
        issue, msg = self._b9g(self.reel)
        self.assertEqual(issue, "refus-non-mesuré", msg)
        self.assertIn("différent de la racine", msg)

    def test_B9h_gitfile_casse(self) -> None:
        issue, msg = self._b9h(self.reel)
        self.assertEqual(issue, "refus-non-mesuré", msg)
        self.assertIn("rev-parse en échec", msg)

    def test_B9i_lien_casse_nfd_rendent_le_resultat_nominal(self) -> None:
        for forme in ("lien", "casse", "nfd"):
            with self.subTest(forme=forme):
                issue, msg = self._b9i(self.reel, forme)
                self.assertEqual(issue, "refus-périmé", msg)
                self.assertIn("périmé : PLAN-ETAT.md", msg)

    @unittest.skipUnless(os.name != "nt", "le git factice est un script sh")
    def test_B9j_git_qui_pend_borne_par_le_delai(self) -> None:
        issue, detail = self._b9j(self.reel)
        self.assertEqual(issue, "non-mesuré", detail)
        self.assertIn("TimeoutExpired", detail)

    def test_B10_desarme_passe(self) -> None:
        self.assertEqual(self._b10(self.reel)[0], "passe")

    def test_B11_preuve_empruntee_perimee_nomme_le_porteur(self) -> None:
        issue, msg = self._b11(self.reel)
        self.assertEqual(issue, "refus-périmé", msg)
        self.assertIn(f"preuve empruntée au slot `{self.t1}`", msg)

    def test_B11bis_la_paire_propre_masque_le_slot_binome_purge(self) -> None:
        issue, msg = self._b11bis(self.reel)
        self.assertEqual(issue, "refus-périmé+purge→passe", msg)

    def test_B12_parite_avec_la_garde(self) -> None:
        self.assertEqual(self._parite(TASKS_ETATS.read_text(encoding="utf-8")), [])

    def test_B13_noms_non_ascii_et_guillemets(self) -> None:
        self.assertEqual(self._b13(self.reel, "LOT-É25 REPRISE.md")[0], "refus-périmé")
        if os.name != "nt":  # le guillemet est interdit dans un nom NTFS
            self.assertEqual(self._b13(self.reel, 'LOT-E26 "x".md')[0], "refus-périmé")

    def test_B14_paire_mixte_nomme_les_deux_classements(self) -> None:
        issue, msg = self._b14(self.reel)
        self.assertEqual(issue, "refus-non-mesuré", msg)
        self.assertIn("— périmé : PLAN-ETAT.md", msg)
        self.assertIn("critic-fable @ ? — [REPRISE NON MESURÉE", msg)
        self.assertEqual(self._b14(self.reel, sonnet=True)[0], "passe")

    def test_B15_aucun_fichier_surveille_passe(self) -> None:
        self.assertEqual(self._b15(self.reel)[0], "passe")

    def test_B16_un_GIT_DIR_leurre_ne_designe_pas_le_depot(self) -> None:
        self.assertEqual(self._b16(self.reel, perime=False)[0], "passe")
        self.assertEqual(self._b16(self.reel, perime=True)[0], "refus-périmé")

    def test_B17_l_index_n_est_pas_reecrit(self) -> None:
        issue, msg = self._b17(self.reel)
        self.assertEqual(issue, "index identique", msg)
        self.assertTrue(msg.startswith("passe"), msg)

    def test_B18_trace_non_dict_refus_nomme_sans_exception(self) -> None:
        issue, msg = self._b18(self.reel)
        self.assertEqual(issue, "refus-non-mesuré", msg)
        self.assertIn("critic-fable @ None — [REPRISE NON MESURÉE : sha tracé illisible (None)]",
                      msg)

    def test_B19_safe_directory_par_GIT_CONFIG_GLOBAL_purge(self) -> None:
        issue, msg = self._b19(self.reel)
        self.assertEqual(issue, "refus-non-mesuré", msg)
        self.assertIn("rev-parse en échec", msg)

    def test_B29_un_tag_homonyme_du_sha_court_ne_masque_pas_la_reprise(self) -> None:
        issue, msg = self._b29(self.reel)
        self.assertEqual(issue, "refus-périmé", msg)
        self.assertIn("PLAN-ETAT.md", msg)

    def test_la_variante_non_mutee_rend_le_verdict_du_reel(self) -> None:
        temoin = self._variante()
        self.assertEqual(self._b1(temoin)[0], "passe")
        self.assertEqual(self._b2(temoin)[0], "refus-périmé")

    # ---- les mutants : chacun rend l'AUTRE issue -------------------------------
    def test_mutants_rendent_l_autre_issue(self) -> None:
        sh = os.name != "nt"
        cibles = {
            "MUT-B1": [(self._b2, {}, "passe"), (self._b2b, {}, "passe"), (self._b2c, {}, "passe"),
                       (self._b3, {}, "passe"), (self._b4, {}, "passe"), (self._b6, {}, "passe"),
                       (self._b13, {"nom": "LOT-É25 REPRISE.md"}, "passe")],
            "MUT-B2": [(self._b2, {}, "passe")],
            "MUT-B3": [(self._b4, {}, "passe")],
            "MUT-B4": [(self._b9_sha, {"sha": "?"}, "passe"), (self._b9_sha, {"sha": "deadbeef"}, "passe"),
                       (self._b14, {}, "passe")] + ([(self._b9_factice, {"mode": "diff"}, "passe")] if sh else []),
            "MUT-B5": [(self._b5, {}, "refus-périmé")],
            "MUT-B6": [(self._b6, {}, "passe")],
            "MUT-B7": [(self._b8, {"frais": 0}, "passe")],
            "MUT-B8": [(self._b7, {}, "refus-périmé")],
            "MUT-B9": [(self._b10, {}, "refus-périmé")],
            "MUT-B11": [(self._b2, {}, "passe")],
            "MUT-B12": [(self._b9a, {}, "refus-non-mesuré")],
            "MUT-B13": [(self._b13, {"nom": "LOT-É25 REPRISE.md"}, "passe")]
                       + ([(self._b13, {"nom": 'LOT-E26 "x".md'}, "passe")] if sh else []),
            "MUT-B13z": [(self._b13, {"nom": 'LOT-E26 "x".md'}, "passe")] if sh else [],
            "MUT-B13'": [(self._b11, {}, "passe")],
            "MUT-B14": [(self._b15, {}, "refus-non-mesuré")],
            "MUT-B15": [(self._b11bis, {}, "refus-sans-purge")],
            "MUT-B16": [(self._b9h, {}, "passe")]
                       + ([(self._b9_factice, {"mode": "rev-parse"}, "passe")] if sh else []),
            "MUT-B17": [(self._b9i, {"forme": f}, "refus-non-mesuré") for f in ("lien", "casse", "nfd")],
            "MUT-B17r": [(self._b9i, {"forme": f}, "refus-non-mesuré") for f in ("casse", "nfd")],
            "MUT-B18": [(self._b4prime, {}, "passe")],
            "MUT-B19": [(self._b17, {}, "index réécrit")],
            "MUT-B20": [(self._b2c, {}, "passe")],
            "MUT-B21": [(self._b16, {"perime": False}, "refus-non-mesuré")],
            "MUT-B22": [(self._b9_factice, {"mode": "diff"}, "passe")] if sh else [],
            "MUT-B23": [(self._b9f, {}, "exception:FileNotFoundError")]
                       + ([(self._b9j, {}, "exception:TimeoutExpired")] if sh else []),
            "MUT-B24": [(self._b9j, {}, "ok")] if sh else [],
            "MUT-B25": [(self._b9g, {}, "passe")],
            "MUT-B26": [(self._b2d, {}, "passe")],
            "MUT-B29": [(self._b29, {}, "passe")],
            # Jugés À PART (`test_MUT_B27_…`, `test_MUT_B28_…`) : un saut dans cette
            # boucle abandonne tous les mutants qui suivent, et `_b19` peut sauter.
            "MUT-B27": [],
            "MUT-B28": [],
        }
        self.assertEqual(sorted(cibles), sorted(MUTANTS_JAMBE), "chaque mutant a ses cibles")
        for nom, paires in MUTANTS_JAMBE.items():
            if not cibles[nom]:
                continue
            mod = self._variante(*paires)
            for scenario, kw, attendu in cibles[nom]:
                with self.subTest(mutant=nom, scenario=scenario.__name__, **kw):
                    try:
                        issue, msg = scenario(mod, **kw)
                    except unittest.SkipTest as saut:
                        # FS sensible (casse, NFD) ou variable de propriétaire ignorée :
                        # le mutant n'y est pas JUGÉ, et c'est dit.
                        self.skipTest(f"{nom} non jugé ici : {saut}")
                    self.assertEqual(issue, attendu, f"{nom} sur {scenario.__name__} : {msg}")

    def test_MUT_B16_proprietaire_douteux_reel(self) -> None:
        mod = self._variante(*MUTANTS_JAMBE["MUT-B16"])
        self.assertEqual(self._b9e2(mod)[0], "passe")

    def test_MUT_B27_trace_non_dict_leve_sous_le_verrou(self) -> None:
        mod = self._variante(*MUTANTS_JAMBE["MUT-B27"])
        self.assertEqual(self._b18(mod)[0], "exception:AttributeError")

    def test_MUT_B28_safe_directory_par_l_environnement_passe(self) -> None:
        mod = self._variante(*MUTANTS_JAMBE["MUT-B28"])
        self.assertEqual(self._b19(mod)[0], "passe")

    def test_MUT_B10_motif_d_un_seul_cote_rougit_la_parite(self) -> None:
        texte = TASKS_ETATS.read_text(encoding="utf-8")
        ancre = '    "PLAN-ETAT.md",\n)'
        self.assertEqual(texte.count(ancre), 1)
        mute = texte.replace(ancre, '    "PLAN-ETAT.md",\n    "docs/LOT-*-REPRISE.md",\n)')
        self.assertTrue(self._parite(mute), "MUT-B10 : la parité doit rougir")


class SequenceSTests(unittest.TestCase):
    """T-00001064 (D3) : la SÉQUENCE S vit en DEUX copies permanentes (la skill `task-board`,
    `PROMPT-SESSION-NUIT.md`), plus la reprise du lot qui, elle, est rangée sous `reprises/` en fin de lot. Les
    deux permanentes sont tenues identiques, au blanc près : une dérive d'une seule rendrait la consigne de la
    nuit différente de celle que `done` impose."""

    MOTIF = re.compile(r"\(1\) les écritures du lot.*?décision du pilote\.", re.S)
    COPIES = (".agents/skills/task-board/SKILL.md", "docs/interne/PROMPT-SESSION-NUIT.md")

    def test_les_copies_permanentes_de_la_sequence_S_sont_identiques(self) -> None:
        lues = {}
        for rel in self.COPIES:
            chemin = ROOT / rel
            if not chemin.is_file():  # arbre adoptant : `docs/interne/` ne voyage pas
                continue
            trouvees = self.MOTIF.findall(chemin.read_text(encoding="utf-8"))
            self.assertEqual(1, len(trouvees), f"{rel} : la séquence S doit y figurer UNE fois")
            lues[rel] = re.sub(r"\s+", " ", trouvees[0])
        self.assertTrue(lues, "aucune copie de la séquence S lue")
        self.assertEqual(1, len(set(lues.values())), {k: len(v) for k, v in lues.items()})


if __name__ == "__main__":
    unittest.main()
