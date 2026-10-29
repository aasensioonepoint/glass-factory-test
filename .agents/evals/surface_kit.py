"""CE QUE LE KIT LIVRE — la surface qu'un banc VOYAGEUR a le droit de juger.

Décision pilote S-01M54ZQ6WCJJ10C692TTXZE6RK (T-01M54MWW5GHRTW3404GK376359) : un
banc du kit qui voyage tolère les AJOUTS de l'adoptant et ne juge que ce que le
kit livre. Mesuré chez un adoptant réel : 40 rouges de `pytest .agents/evals`,
dont 26 levés par un agent, une skill, une commande, un README, une jambe de
hook ou un `*.test.sh` AJOUTÉS — des ajouts légitimes, que ces bancs prenaient
pour des défauts du kit.

FORME COMMUNE DES BANCS QUI L'IMPORTENT : dans le kit (`EST_LE_KIT`), la branche
STRICTE est inchangée — c'est elle qui garde le pouvoir de rougir ; hors du kit,
le banc restreint son objet à ce module et garde une assertion de non-vacuité
APRÈS le filtre. Chaque source vide ou absente LÈVE (AssertionError), jamais un
ensemble vide qui rendrait le filtre vert par vacuité.

BORNES, écrites pour ne pas être relues comme des garanties :
  * `SKILLS_DU_KIT` est un LITTÉRAL : une skill ajoutée au kit doit y entrer,
    `test_surface_kit.py` rougit sinon (dans le kit).
  * `readme_du_kit()` repose sur le titre du README du kit, épinglé dans le kit.
  * `jambe_du_kit()` n'attribue une jambe à l'adoptant que si elle cite un script
    hors `in_kit_code` ET aucun script du kit autre qu'un lanceur
    (`LANCEURS_DU_KIT`). Restent donc JUGÉES (sens sûr : l'exempter sans preuve
    tairait aussi une jambe du kit) une jambe qui ne cite AUCUN script
    reconnaissable (`npx …`, binaire nu, `.js`), un script de l'adoptant posé SOUS
    une racine du kit, et une jambe du kit où l'adoptant chaîne son script
    (`… safe-bash.sh && python3 scripts/audit.py`). Borne inverse : un lanceur du
    kit absent de `LANCEURS_DU_KIT` ferait juger la jambe de l'adoptant qu'il porte.
  * `scripts_adoptant()` ne lit que les jambes sous `hooks` (une `statusLine`
    réécrite reste jugée) et garde jugé un script qu'une jambe jugée cite aussi.
  * Capacité perdue NOMMÉE (S-01M550PYWS4F3JWXPF19K12QHY) : hors du kit, une
    jambe ajoutée par l'adoptant n'est plus jugée — préfixe durci, lanceur et
    zéro-LLM restent à sa charge.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# adopting-tree: le marqueur du kit ne voyage pas (strip: .agents/IS_THE_KIT), son absence EST l'adoptant
EST_LE_KIT = (ROOT / ".agents" / "IS_THE_KIT").is_file()  # adopting-tree: idem

TITRE_README_KIT = "# Multi-Agent Dev Starter Kit"

# Les 50 skills de profondeur 1 que le kit livre (AGENTS.md § Skills index).
# 2026-10-19, T-01M52X1W3WPKCWX1DC36NMKJB6 (CORR-5b) : `terraform-deploy` ajouté (37 -> 38).
# 2026-10-23, T-01M5M66MH1GDW8JRHKEXXN3JPA (lot B) : `jira` ajouté (38 -> 39).
# 2026-10-22, T-01M5HEJZ9XVXWQ61XMZYGA3YT0 (lot A) : `reverse-engineering` ajouté (39 -> 40, à la fusion).
# 2026-10-23, T-01M5N5FMA6DGVZVQSH6073A58A : `setup` ajouté (40 -> 41).
# 2026-10-24, T-01M5PCCHMWXTRCM5QJT8J5KNEH (lot G) : la skill de routage local retirée (41 -> 40).
# Branche reprise/2026-10-20, réunie le 2026-10-25 : T-01M5C1P67FN2YR9T3R0BHV7M3M rend un miroir
# `source-command-*` par commande hors Claude Code seul depuis `commands/` — neuf de plus que les
# trois d'avant, `jira` et `setup` compris (40 -> 49) ; T-01M5BZC1Y0T36EHTZY9AKZ650F : `seo` (49 -> 50).
SKILLS_DU_KIT = frozenset({
    "agentic-code-review", "angular-modern", "audit", "codebase-indexing",
    "composition-patterns", "context-retro", "custom-docs-curation", "dash",
    "docs-sync", "frontend-fidelity", "go-idiomatic", "guardrails", "index",
    "institutional-memory", "java-hexagonal-spring", "jira", "kickoff", "lang",
    "lessons-seed", "load-test", "night", "planning", "planning-all",
    "playwright-best-practices", "react-best-practices",
    "restitution-pilote", "retro-lessons", "reverse-engineering",
    "security-gate", "seo", "setup", "skills-sync",
    "source-command-audit", "source-command-dash", "source-command-docs-sync",
    "source-command-index", "source-command-jira", "source-command-kickoff",
    "source-command-lang", "source-command-planning", "source-command-planning-all",
    "source-command-setup", "source-command-skills-sync", "source-command-specs-sync",
    "specs-sync", "task-board",
    "terraform-deploy", "verification-discipline", "vue-modern", "web-interface-guidelines",
})

# Les racines de code du kit. `.agents/` couvre aussi `.agents/vendor/agentic_v3/`
# et `.agents/vendor/cadre/` ; `agentic_v3/` et `src/cadre/` couvrent les anciens
# emplacements. `src/cadre/` et non `src/` : un `src/` d'adoptant est courant.
# Borne : un `*.test.sh` de l'adoptant posé SOUS une racine reste jugé (sens sûr).
# `.cursor/` (T-01M5BZCDMCEQXKA2RKTB2EMW8M) : cible dérivée de `render_hosts.py` qui
# voyage comme `.kimi-code/` ; aucun code n'y vit aujourd'hui, elle est nommée pour
# le même sens sûr.
RACINES_DU_KIT = (".agents/", ".claude/", ".codex/", ".cursor/", ".gemini/", ".githooks/",
                  ".github/", ".kimi-code/", "agentic_v3/", "core-scripts/", "src/cadre/")

# Préfixe racine d'un chemin dans une jambe de hook, retiré AVANT l'extraction :
# `$CLAUDE_PROJECT_DIR/`, `$(git rev-parse --show-toplevel)/`, `$r+'/` (PowerShell)
# et `r+'/` (python -c). Sans ce retrait, `CLAUDE_PROJECT_DIR/.claude/…` serait lu
# comme un seul chemin, hors du kit.
_PREFIXE_RACINE = re.compile(
    r"\$\{?CLAUDE_PROJECT_DIR\}?/|\$\(git rev-parse --show-toplevel\)/|(?<!\w)\$?r\+'/")
_SCRIPT = re.compile(r"(?:[.\w-]+/)*[\w-]+\.(?:py|sh|ps1)(?!\w)")


def _verrou(root: Path) -> dict:
    lock = root / "contract.lock.json"
    assert lock.is_file(), f"source absente : {lock}"
    return json.loads(lock.read_text(encoding="utf-8"))


_VP = None


def _vendor_paths():
    """`.agents/bin/vendor_paths.py` du kit, CHARGÉ par chemin (patron v3prep)."""
    global _VP
    if _VP is None:
        chemin = ROOT / ".agents" / "bin" / "vendor_paths.py"
        spec = importlib.util.spec_from_file_location("surface_kit_vendor_paths", chemin)
        assert spec and spec.loader, f"source absente : {chemin}"
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        _VP = module
    return _VP


def agents_du_kit(root: Path = ROOT) -> frozenset[str]:
    """Les noms des defs du roster EMBARQUÉ (`cadre.roster.charger()`), jamais
    les fichiers posés sous `.claude/agents/` — un agent de l'adoptant y vit aussi.
    Le paquet `cadre` est celui que `vendor_paths` désigne sous `root`
    (`.agents/vendor/cadre`, sinon `src/cadre`), chargé par chemin sans toucher
    `sys.path` ; module asserté sous ce dossier : un `cadre` installé ailleurs
    ne répond pas à sa place."""
    vp = _vendor_paths()
    dossier = vp.dossier_paquet(root, "cadre")
    assert dossier is not None and (dossier / "roster.py").is_file(), (
        f"source absente : ni {root / vp.VENDOR / 'cadre'} ni {root / 'src' / 'cadre'} "
        "ne portent roster.py")
    vp.charger_paquet(root, "cadre")
    import cadre.roster as roster

    assert Path(roster.__file__).resolve().is_relative_to(dossier), (
        f"cadre.roster chargé hors de {dossier} : {roster.__file__}")
    noms = frozenset(d.nom for d in roster.charger().definitions)
    assert noms, "roster du kit vide"
    return noms


def workflows_du_kit(root: Path = ROOT) -> frozenset[str]:
    """Les commandes promises par `contract.lock.json` (`workflow:<nom>`)."""
    noms = frozenset(e["element"].split(":", 1)[1] for e in _verrou(root).get("elements", [])
                     if str(e.get("element", "")).startswith("workflow:"))
    assert noms, "aucun workflow au verrou du kit"
    return noms


def readme_du_kit(root: Path = ROOT) -> bool:
    """`README.md` est-il celui du kit (titre épinglé) ? Absent ou réécrit : non."""
    p = root / "README.md"
    if not p.is_file():
        return False
    return p.read_text(encoding="utf-8").splitlines()[:1] == [TITRE_README_KIT]


_KCG = None


def in_kit_code(rel: str) -> bool:
    """`kit_code_guard.in_kit_code` (SYM-10418), CHARGÉ, jamais paraphrasé."""
    global _KCG
    if _KCG is None:
        chemin = ROOT / ".agents" / "bin" / "kit_code_guard.py"
        spec = importlib.util.spec_from_file_location("surface_kit_kit_code_guard", chemin)
        assert spec and spec.loader, f"source absente : {chemin}"
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        _KCG = module
    return _KCG.in_kit_code(rel)


def scripts_cites(cmd: str) -> list[str]:
    """Les scripts (`.py`, `.sh`, `.ps1`) cités par une jambe, préfixe racine retiré."""
    out = []
    for m in _SCRIPT.finditer(_PREFIXE_RACINE.sub("", cmd)):
        s = m.group(0)
        while s.startswith("./"):
            s = s[2:]
        out.append(s)
    return out


# Les lanceurs du kit : ils portent le script de l'adoptant sans rendre la jambe du kit.
# `garde-fermee.sh` (T-01M5CH9FA8BDDM33QKDBAZG42S) enveloppe une garde comme `pyrun.sh`
# porte un script : une jambe de l'adoptant qu'il enveloppe reste la sienne.
LANCEURS_DU_KIT = frozenset({".agents/pyrun.sh", ".agents/pyrun.ps1",
                             ".agents/security/garde-fermee.sh"})

# Les clés qui portent une jambe : `command` / `commandWindows` (forme imbriquée),
# `bash` / `powershell` (Copilot).
_CLES_JAMBE = frozenset({"command", "commandWindows", "bash", "powershell"})


def jambe_du_kit(cmd: str) -> bool:
    """LA RÈGLE : une jambe est du kit si chaque script cité est `in_kit_code`, ou
    si l'un d'eux est un script du kit autre qu'un lanceur — une jambe du kit où
    l'adoptant chaîne son script reste jugée. Aucun script reconnaissable → du kit
    (borne C20, sens sûr : jugée)."""
    s = scripts_cites(cmd)
    return all(in_kit_code(x) for x in s) or any(in_kit_code(x) and x not in LANCEURS_DU_KIT for x in s)


def jambe_jugee(cmd: str) -> bool:
    """Le filtre des bancs de jambes : dans le kit, TOUTES sont jugées (la
    branche stricte garde son pouvoir de rougir) ; hors du kit, celles du kit."""
    return EST_LE_KIT or jambe_du_kit(cmd)


def scripts_adoptant(doc: dict) -> set[str]:
    """Hors du kit, les scripts hors `in_kit_code` que SEULES les jambes de
    l'adoptant citent dans un registre de hooks (`doc`, son JSON) : ce qu'un banc
    qui extrait les scripts du TEXTE du registre retire de ce qu'il juge. Dans le
    kit : vide, la branche stricte juge tout."""
    if EST_LE_KIT:
        return set()
    adoptant: set[str] = set()
    juges: set[str] = set()
    pile: list = [doc.get("hooks", {})]
    while pile:
        x = pile.pop()
        if isinstance(x, list):
            pile.extend(x)
        elif isinstance(x, dict):
            for cle, v in x.items():
                if cle in _CLES_JAMBE and isinstance(v, str):
                    (juges if jambe_du_kit(v) else adoptant).update(scripts_cites(v))
                else:
                    pile.append(v)
    return {s for s in adoptant - juges if not in_kit_code(s)}
