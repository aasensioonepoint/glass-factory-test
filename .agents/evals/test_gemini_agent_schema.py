"""Filet du frontmatter des défs `.gemini/agents/*.md` DU KIT — T-00000779.

gemini-cli 0.57.0 refusait les 31 défs du kit (0/31 chargées, S-00002854) : clé
`effort:` inconnue de son schéma `.strict()`, `tools:` en chaîne au lieu d'une
liste, noms d'outils Claude, et un YAML invalide (`communicator`, `: ` dans la
description). ZÉRO appel de modèle, STDLIB seule : ce banc ne lance ni node ni gemini.

OÙ IL JUGE : dans le SEUL dépôt du kit (marqueur `.agents/IS_THE_KIT`). PORTÉE du
marqueur, bornée au canal : `sync_template.py` le retire (règle `strip:`) ; une copie
BRUTE de l'arbre l'emporte — il faut alors le supprimer (QUICK-SETUP.md § 3), sinon ce
filet juge les défs du kit chez l'adoptant. Marqueur absent, il SAUTE en le disant et
ne juge RIEN — ni une déf ajoutée par l'adoptant, ni une déf du kit qu'il a modifiée
(décisions S-00002966 et S-00003009) : c'est la porte du kit qui garde les défs qu'il
livre.

CE QU'IL JUGE : les défs LIVRÉES PAR LE KIT, et elles seules, désignées par leur
NOM (`KIT_ROSTER`, liste littérale, parité avec `.claude/agents/*.md` testée),
STRICTEMENT — plus strictement que l'hôte, exprès : exactement
`name/description/tools/model` dans cet ordre, `name` == stem, `description` en
scalaire nu sûr ou en chaîne JSON, `tools` en tableau JSON non vide de noms parmi
les 27 builtins de 0.57.0 (ni joker, ni `mcp_`), aucune autre ligne que les
commentaires `# ` du marqueur `cadre.managed` que `poser` écrit. Toute autre déf
présente sous `.gemini/agents/` n'est jamais lue.

La vérification d'une déf hors de ce périmètre se fait à la main, au vrai chargeur
de gemini-cli : la commande, sa précondition et sa lecture sont dans `GEMINI.md`.

BORNES, écrites : copie DATÉE (0.57.0) des 27 noms — une montée de gemini-cli qui
les change n'est pas vue ici. Plus strict que l'hôte ne veut pas dire « chargé par
l'hôte » : le témoin du chargement reste le chargeur réel. Charger ≠ enregistrer.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GEMINI = ROOT / ".gemini" / "agents"

# Les défs livrées par le kit, par NOM — littéral et non un glob : un adoptant
# qui ajoute `.claude/agents/x.md` ET `.gemini/agents/x.md` n'entre pas ici.
KIT_ROSTER = frozenset((
    "analyzer", "board-reporter", "communicator", "critic-fable", "critic-opus",
    "critic-sonnet-max", "custom-docs-curator", "design-review", "dev-mono", "dev-multi",
    "documenter", "exec-critic", "frontend-fidelity", "indexer", "language-detector",
    "load-tester", "modeler", "optimizer", "orchestrator", "plan-critic", "plan-critic-sonnet-max",
    "planner", "planner-sonnet", "sca-java", "sca-mobile", "sca-npm",
    "security-code-review", "security-code-review-global", "security-orchestrator",
    "security-remediation", "security-sca", "skills-resolver",
    # T-01M52X1W3WPKCWX1DC36NMKJB6 (2026-10-19) — 33e déf, livrée sur les 5 hôtes.
    "terraform-deployer",
    # T-01M5BZC1Y0T36EHTZY9AKZ650F (2026-10-21) — 34e déf de la branche reprise/2026-10-20, livrée sur les 5 hôtes.
    "seo-specialist",
    # T-01M5HEJZ9XVXWQ61XMZYGA3YT0 (2026-10-22) — 34e déf de develop, livrée sur les 5 hôtes ; 35 à la fusion.
    "reverse-engineer",
))

# Marqueur d'identité du kit, retiré par `sync_template.py` (strip: .agents/IS_THE_KIT) ;
# une copie BRUTE l'emporte : le supprimer alors (QUICK-SETUP.md § 3).
# adopting-tree: son absence EST le signal « projet adoptant » : ce filet y saute EN ENTIER (S-00003009).
EST_LE_KIT = (ROOT / ".agents" / "IS_THE_KIT").is_file()
SAUT_ADOPTANT = ("SAUT ANNONCE : marqueur `.agents/IS_THE_KIT` absent (projet adoptant, "
                 "pas le kit) — rien n'est juge ici ; les defs Gemini de ce projet se "
                 "verifient au vrai chargeur, commande dans GEMINI.md")
pytestmark = pytest.mark.skipif(not EST_LE_KIT, reason=SAUT_ADOPTANT)

# chunk-7HKQGPWB.js:282478 — ALL_BUILTIN_TOOL_NAMES, 27 noms, gemini-cli 0.57.0.
BUILTIN_TOOLS_0_57_0 = frozenset((
    "glob", "write_todos", "write_file", "google_web_search", "web_fetch", "replace",
    "run_shell_command", "grep_search", "read_many_files", "read_file", "list_directory",
    "activate_skill", "ask_user", "tracker_create_task", "tracker_update_task",
    "tracker_get_task", "tracker_list_tasks", "tracker_add_dependency", "tracker_visualize",
    "get_internal_docs", "enter_plan_mode", "exit_plan_mode", "update_topic", "complete_task",
    "invoke_agent", "read_mcp_resource", "list_mcp_resources",
))
KIT_KEYS = ("name", "description", "tools", "model")
# Paire FACULTATIVE, ORDRE FIXE, valeurs ENTIERES positives (alignement des hotes, L-E, H-08) : le chargeur
# Gemini 0.63.0 coupe un sous-agent a 30 tours / 10 min par defaut (M7 : DEFAULT_MAX_TURNS,
# DEFAULT_MAX_TIME_MINUTES) ; le schema de def `.strict()` accepte `max_turns` et `timeout_mins`.
LIMIT_KEYS = ("max_turns", "timeout_mins")
_LINE_RX = re.compile(r"([a-z_]+): (\S.*)")
_MARKER_PREFIX = "# "  # cadre.managed._FRONTMATTER : `poser` écrit « # » + ligne


def _plain_scalar_safe(value: str) -> bool:
    return bool(value) and value[0] not in "-?:,[]{}#&*!|>'\"%@`" and ": " not in value \
        and " #" not in value and "\t" not in value and value == value.strip() \
        and value.lower() not in ("true", "false", "null", "yes", "no", "on", "off", "~") \
        and not re.fullmatch(r"[-+]?(\d[\d_]*)?\.?\d*([eE][-+]?\d+)?", value)


def kit_def_errors(stem: str, text: str) -> list:
    """Toutes les fautes de la forme KIT, sans retour anticipé après l'ouverture :
    une clé dupliquée n'en masque aucune autre (et aucune clé n'en court-circuite)."""
    lines = text.replace("\r\n", "\n").split("\n")
    if lines[0] != "---":
        return ["ligne 1 : `---` d'ouverture absent"]
    try:
        end = lines.index("---", 1)
    except ValueError:
        return ["`---` de fermeture absent"]
    errs, keys, fm = [], [], {}
    for n, line in enumerate(lines[1:end], start=2):
        if line.startswith(_MARKER_PREFIX):
            continue
        m = _LINE_RX.fullmatch(line)
        if not m:
            errs.append(f"ligne {n} hors de la forme `clé: valeur` : {line!r}")
            continue
        keys.append(m.group(1))
        fm.setdefault(m.group(1), m.group(2))
    errs += [f"clé dupliquée : {k}" for k in sorted({k for k in keys if keys.count(k) > 1})]
    if tuple(keys) not in (KIT_KEYS, KIT_KEYS + LIMIT_KEYS):
        errs.append(f"clés {tuple(keys)} != {KIT_KEYS} (+ {LIMIT_KEYS} facultatives, dans cet ordre)")
    for k in LIMIT_KEYS:
        if k in fm and not re.fullmatch(r"[1-9][0-9]*", fm[k]):
            errs.append(f"{k} : entier positif exigé, lu {fm[k]!r}")
    if fm.get("name") != stem:
        errs.append(f"name {fm.get('name')!r} != stem {stem!r}")
    desc = fm.get("description", "")
    if desc.startswith('"'):
        try:
            ok = isinstance(json.loads(desc), str) and bool(json.loads(desc))
        except ValueError:
            ok = False
        if not ok:
            errs.append("description : chaîne JSON invalide ou vide")
    elif not _plain_scalar_safe(desc):
        errs.append("description : scalaire nu non sûr (citer en chaîne JSON)")
    try:
        tools = json.loads(fm.get("tools", ""))
    except ValueError:
        tools = None
    if not isinstance(tools, list) or not tools:
        errs.append("tools : tableau JSON non vide exigé")
    else:
        errs += [f"tools : {t!r} hors des 27 builtins" for t in tools if t not in BUILTIN_TOOLS_0_57_0]
    if not _plain_scalar_safe(fm.get("model", "")):
        errs.append("model : scalaire nu sûr exigé")
    return errs


def judged_paths(gemini_dir: Path) -> list:
    """Les chemins que ce filet JUGE : un par nom du roster, jamais un glob du dossier."""
    return [gemini_dir / f"{stem}.md" for stem in sorted(KIT_ROSTER)]


@pytest.mark.parametrize("path", judged_paths(GEMINI), ids=lambda p: p.stem)
def test_every_kit_def_has_the_kit_form(path):
    assert path.is_file(), f"déf du kit absente : {path.name}"
    assert kit_def_errors(path.stem, path.read_text(encoding="utf-8")) == []


def test_kit_roster_is_the_claude_roster_on_the_kit():
    claude = {p.stem for p in (ROOT / ".claude" / "agents").glob("*.md")}
    assert KIT_ROSTER == claude


# Texte de RÉFÉRENCE FIGÉ : les négatifs mutent CE texte, jamais le `planner.md` vivant ;
# sa parité avec le frontmatter vivant est un test à part.
REF_PLANNER = (
    "---\n"
    "name: planner\n"
    "description: Produces an approval-ready implementation plan for a scoped task. Use after "
    "language-detector and before any dev-* agent. Never edits code.\n"
    'tools: ["read_file", "grep_search", "glob", "run_shell_command"]\n'
    "model: gemini-3.1-pro\n"
    "---\n"
)


def _planner():
    return REF_PLANNER


def test_limit_pair_is_optional_ordered_and_integer():
    """Alignement des hôtes, L-E (H-08) : la paire `max_turns`/`timeout_mins` est FACULTATIVE, dans
    CET ordre, et ses valeurs sont des ENTIERS positifs — quatre fautes, quatre rouges."""
    base = _planner()
    paire = "model: gemini-3.1-pro\nmax_turns: 100\ntimeout_mins: 60\n"
    ok = base.replace("model: gemini-3.1-pro\n", paire)
    assert kit_def_errors("planner", base) == []
    assert kit_def_errors("planner", ok) == []
    for faute in (
        ok.replace("max_turns", "max_turnz"),
        ok.replace("max_turns: 100", "max_turns: cent"),
        ok.replace("max_turns: 100\ntimeout_mins: 60\n", "timeout_mins: 60\nmax_turns: 100\n"),
        base.replace("model: gemini-3.1-pro\n", "model: gemini-3.1-pro\nmax_turns: 100\n"),
    ):
        assert kit_def_errors("planner", faute) != [], faute


_TAMPON_POSER = re.compile(r"# cadre\.(managed|version|checksum): ")


def _sans_tampon_poser(text: str) -> str:
    """Retire du FRONTMATTER les seules lignes des TROIS clés que `poser` écrit
    (`managed`, `version`, `checksum`) : un `planner.md` tamponné n'a pas dérivé, la
    parité ne doit pas rougir pour ça. Toute autre ligne `# cadre.` (`# cadre.hote: …`)
    reste, et la parité la voit."""
    lines = text.replace("\r\n", "\n").split("\n")
    try:
        end = lines.index("---", 1)
    except ValueError:
        return text
    head = [ln for ln in lines[1:end] if not _TAMPON_POSER.match(ln)]
    return "\n".join(lines[:1] + head + lines[end:])


def test_frozen_reference_is_the_live_planner_frontmatter():
    live = (GEMINI / "planner.md").read_text(encoding="utf-8")
    assert _sans_tampon_poser(live).startswith(REF_PLANNER)


def _swap(text: str, old_rx: str, new: str) -> str:
    out, n = re.subn(old_rx, new, text, count=1, flags=re.M)
    assert n == 1 and out != text, old_rx  # une mutation qui ne change rien rougit
    return out


NEGATIVES = (
    ("effort: ajoutée", r"^model:.*$", "\\g<0>\neffort: high"),
    ("tools liste nue", r"^tools:.*$", "tools: read_file, grep_search"),
    ("tools nom Claude", r"^tools:.*$", 'tools: ["Read", "grep_search"]'),
    ("tools array Python", r"^tools:.*$", "tools: ['read_file', 'grep_search']"),
    ("description ': '", r"^description:.*$", "description: a: b"),
    ("description ' #'", r"^description:.*$", "description: a #b"),
    ("description '*'", r"^description:.*$", "description: *a"),
    ("clé dupliquée", r"^model:.*$", "\\g<0>\nmodel: gemini-3.1-pro"),
    ("name capitalisé", r"^name:.*$", "name: Planner"),
    ("clé inconnue", r"^model:.*$", "\\g<0>\ncolor: blue"),
    ("tools retiré", r"^tools:.*\n", ""),
    ("mcp sans outil", r"^tools:.*$", 'tools: ["mcp_x"]'),
    ("kind: remote", r"^name:.*$", "kind: remote\n\\g<0>"),
)


@pytest.mark.parametrize("label,rx,new", NEGATIVES, ids=[n[0] for n in NEGATIVES])
def test_negative_controls_on_the_frozen_reference(label, rx, new):
    assert kit_def_errors("planner", _planner()) == []
    assert kit_def_errors("planner", _swap(_planner(), rx, new)), label


def test_duplicate_key_is_not_masked_by_another_fault():
    """Une clé dupliquée reste NOMMÉE à côté d'une autre faute : aucun court-circuit."""
    mutated = _swap(_planner(), r"^name:.*$", "kind: remote\n\\g<0>\nname: planner")
    errs = kit_def_errors("planner", mutated)
    assert "clé dupliquée : name" in errs and any(e.startswith("clés ") for e in errs)


# Forme EXACTE écrite par `cadre.managed.poser` (`managed.py` du paquet, où qu'il vive) au frontmatter :
# trois lignes « # » juste avant le `---` fermant — relevé sur `planner.md`, T-00000779 C13.
POSER_LINES = (
    "# cadre.managed: true",
    '# cadre.version: "0.1.0.dev0"',
    '# cadre.checksum: "sha256:a142bc8e363858e4bbf59235213451c29203d149fcb727fba04f63a39100b30f"',
)


def test_positive_cadre_managed_marker_is_admitted():
    mutated = _swap(_planner(), r"^model:.*$", "\\g<0>\n" + "\n".join(POSER_LINES))
    assert kit_def_errors("planner", mutated) == []


@pytest.mark.parametrize("source", ("figée", "vivante"))
def test_parity_ignores_the_poser_stamp_and_still_sees_a_real_mutation(source):
    """Planner TAMPONNÉ par `poser` → parité verte ; mutation RÉELLE → rouge."""
    base = REF_PLANNER + "corps\n" if source == "figée" else \
        (GEMINI / "planner.md").read_text(encoding="utf-8")
    stamped = _swap(base, r"^model:.*$", "\\g<0>\n" + "\n".join(POSER_LINES))
    assert not stamped.startswith(REF_PLANNER)  # sans le filtre, la parité rougirait
    assert _sans_tampon_poser(stamped).startswith(REF_PLANNER)
    for rx, new in ((r"^model:.*$", "model: gemini-3.1-flash"),
                    (r"^tools:.*$", 'tools: ["read_file"]'),
                    (r"^model:.*$", "\\g<0>\ntemperature: 0.2"),
                    # une ligne `# cadre.` qui N'EST PAS une des trois clés de `poser`
                    (r"^model:.*$", "\\g<0>\n# cadre.hote: claude")):
        assert not _sans_tampon_poser(_swap(stamped, rx, new)).startswith(REF_PLANNER), new


# Déf hors roster, invalide pour l'hôte (pas même de `---`) : jamais collectée.
ADOPTER_INVALID = "tools: Read\neffort: high\nname: Mon Agent\n"
# Clé ACCEPTÉE par l'hôte (schéma local 0.57.0) mais hors de la forme du kit.
HOST_OK_KIT_KO = "temperature: 0.2\n"


def test_adopting_tree_skips_and_kit_tree_judges(tmp_path):
    """Même arbre, deux régimes : sans `.agents/IS_THE_KIT` le filet SAUTE (rien jugé,
    même une déf du kit éditée) ; avec, il juge — et ne collecte toujours pas la déf
    hors roster."""
    for sub in (".gemini/agents", ".claude/agents", ".agents/evals"):
        (tmp_path / sub).mkdir(parents=True)
    for stem in KIT_ROSTER:
        shutil.copy(GEMINI / f"{stem}.md", tmp_path / ".gemini/agents" / f"{stem}.md")
        shutil.copy(ROOT / ".claude/agents" / f"{stem}.md", tmp_path / ".claude/agents" / f"{stem}.md")
    planner = tmp_path / ".gemini/agents/planner.md"
    planner.write_text(_swap(planner.read_text(encoding="utf-8"), r"^model:.*$",
                             "\\g<0>\n" + HOST_OK_KIT_KO.rstrip("\n")), encoding="utf-8")
    (tmp_path / ".gemini/agents/mon-agent.md").write_text(ADOPTER_INVALID, encoding="utf-8")
    (tmp_path / ".claude/agents/mon-agent.md").write_text(ADOPTER_INVALID, encoding="utf-8")
    net = tmp_path / ".agents/evals" / Path(__file__).name
    shutil.copy(__file__, net)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    cmd = [sys.executable, "-m", "pytest", "-q", "-rs", "-p", "no:cacheprovider", str(net),
           "-k", "not adopting_tree_skips and not pre_gate"]
    adopting = subprocess.run(cmd, capture_output=True, text=True, cwd=tmp_path, env=env)
    assert adopting.returncode == 0, adopting.stdout[-2000:]
    assert "passed" not in adopting.stdout and "SAUT ANNONCE" in adopting.stdout, adopting.stdout[-2000:]
    (tmp_path / ".agents/IS_THE_KIT").write_text("kit\n", encoding="utf-8")
    collected = subprocess.run(cmd + ["--collect-only"], capture_output=True, text=True,
                               cwd=tmp_path, env=env)
    assert collected.returncode == 0 and "mon-agent" not in collected.stdout, collected.stdout
    kit = subprocess.run(cmd, capture_output=True, text=True, cwd=tmp_path, env=env)
    assert kit.returncode == 1 and "[planner]" in kit.stdout, kit.stdout[-2000:]


# Cross-témoin (piège 1, PLANNING_TRAPS) : le filet frère juge la déclaration Gemini
# en vocabulaire NATIF — un écrivain `replace` ajouté à un critique de plan doit rougir.
@pytest.mark.parametrize("writer", ("replace", "write_file"))
def test_pre_gate_net_sees_native_gemini_writers(writer):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from test_plan_critic_contract import _erreurs_shell_pre_gate
    text = (GEMINI / "plan-critic.md").read_text(encoding="utf-8")
    assert _erreurs_shell_pre_gate("gemini", text) == []
    mutated = _swap(text, r'^tools: \[', f'tools: ["{writer}", ')
    assert _erreurs_shell_pre_gate("gemini", mutated)
