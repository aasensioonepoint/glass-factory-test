"""`surface_kit.py` dit-il ce que le kit LIVRE ? (T-01M54MWW5GHRTW3404GK376359)

Les bancs voyageurs qui l'importent (décision S-01M54ZQ6WCJJ10C692TTXZE6RK) ne
jugent plus, hors du kit, que ses sources : un prédicat faux les rendrait verts
sur un défaut du kit, en silence. Ce banc tient donc chaque source À L'ARBRE.

  * DANS LE KIT, chaque source ÉGALE l'arbre suivi (agents sur les cinq hôtes,
    commandes, skills de profondeur 1, titre du README, racines des
    `*.test.sh`), et la règle `jambe_du_kit` SEULE classe kit TOUTES les jambes
    des cinq registres (185 mesurées le 2026-10-17, 0 adoptant).
  * HORS DU KIT, chaque source est INCLUSE dans l'arbre (l'adoptant ajoute), et
    chaque registre garde au moins une jambe du kit (non-vacuité après filtre).
  * PARTOUT, un script de l'adoptant est classé adoptant sous les cinq formes de
    préfixe relevées chez un adoptant réel, une jambe du kit où il est chaîné
    reste du kit, `scripts_adoptant` ne retire que ce que seules ses jambes
    citent, et une source absente LÈVE.

Énumération par `git ls-files` et écritures explicites dans un répertoire
temporaire : aucun parcours d'arbre.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

EVALS = Path(__file__).resolve().parent
if str(EVALS) not in sys.path:
    sys.path.insert(0, str(EVALS))

import surface_kit as sk  # noqa: E402

ROOT = sk.ROOT

# (registre, forme) : `nested` = event -> blocs -> hooks (command / commandWindows),
# `flat` = Copilot (bash / powershell).
REGISTRES = {
    ".claude/settings.json": "nested",
    ".codex/hooks.json": "nested",
    ".agents/hooks.json": "nested",
    ".kimi-code/hooks.json": "nested",
    ".github/hooks/agent-guardrails.json": "flat",
}

# (répertoire, suffixe) des defs d'agent sur les cinq hôtes.
HOTES_AGENTS = {
    ".claude/agents/": ".md",
    ".codex/agents/": ".toml",
    ".gemini/agents/": ".md",
    ".github/agents/": ".agent.md",
    ".kimi-code/agents/": ".md",
}

# Les cinq formes de préfixe d'un script de l'adoptant, RELEVÉES chez lui.
FORMES = (
    'python3 "$CLAUDE_PROJECT_DIR/{s}" pre',
    'AGENTS_HOOK_HOST=codex python "$(git rev-parse --show-toplevel)/{s}" pre',
    "python -c \"import subprocess,sys; r=subprocess.check_output(['git','rev-parse',"
    "'--show-toplevel'],text=True).strip(); sys.exit(subprocess.run([sys.executable, "
    "r+'/{s}']).returncode)\"",
    "$r=(& git rev-parse --show-toplevel); & ($r+'/.agents/pyrun.ps1') 'module' $r '{s}'",
    "AGENTS_HOOK_HOST=copilot bash .agents/pyrun.sh {s} pre",
)


def suivis() -> list[str]:
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"],
                         capture_output=True, text=True, check=True)
    return [p for p in out.stdout.split("\0") if p]


def _enfants(chemins, prefixe: str, suffixe: str) -> set[str]:
    """Noms des fichiers SUIVIS directement sous `prefixe` (profondeur 1)."""
    return {p[len(prefixe):-len(suffixe)] for p in chemins
            if p.startswith(prefixe) and p.endswith(suffixe) and "/" not in p[len(prefixe):]}


def jambes(registre: str) -> list[str]:
    doc = json.loads((ROOT / registre).read_text(encoding="utf-8"))
    if REGISTRES[registre] == "flat":
        return [str(h[k]) for v in doc["hooks"].values() for h in v
                for k in ("bash", "powershell") if k in h]
    out = [str(h[k]) for v in doc["hooks"].values() for b in v for h in b.get("hooks", [])
           for k in ("command", "commandWindows") if k in h]
    if "statusLine" in doc:
        out.append(str(doc["statusLine"].get("command", "")))
    return out


def _juger(source, arbre, quoi):
    if sk.EST_LE_KIT:
        assert source == arbre, (
            f"{quoi} : la source du kit ne colle pas à l'arbre — en source seule "
            f"{sorted(source - arbre)}, dans l'arbre seul {sorted(arbre - source)}")
    else:
        assert source <= arbre, f"{quoi} : livré par le kit et absent : {sorted(source - arbre)}"


def test_chaque_source_egale_l_arbre_dans_le_kit_et_y_est_incluse_ailleurs():
    t = suivis()
    agents = sk.agents_du_kit()
    for rep, suf in HOTES_AGENTS.items():
        _juger(agents, _enfants(t, rep, suf), f"agents {rep}")
    _juger(sk.workflows_du_kit(), _enfants(t, ".claude/commands/", ".md"), "commandes")
    skills = {p.split("/")[2] for p in t
              if p.startswith(".agents/skills/") and p.count("/") == 3 and p.endswith("/SKILL.md")}
    _juger(set(sk.SKILLS_DU_KIT), skills, "skills de profondeur 1")
    # T-01M52X1W3WPKCWX1DC36NMKJB6 (2026-10-19) : 37 -> 38, la skill terraform-deploy.
    # T-01M5FQ7F3TDYQAMKQQ8Q30DDSG (2026-10-23) : 38 -> 39, la skill jira.
    # T-01M5HEJZ9XVXWQ61XMZYGA3YT0 (2026-10-22, lot A) : 39 -> 40 à la fusion, la skill reverse-engineering.
    # T-01M5N5FMA6DGVZVQSH6073A58A (2026-10-23) : 40 -> 41, la skill setup.
    # T-01M5PCCHMWXTRCM5QJT8J5KNEH (2026-10-24, lot G) : 41 -> 40, la skill de routage local retirée.
    # Fusion de reprise/2026-10-20 (2026-10-25) : T-01M5C1P67FN2YR9T3R0BHV7M3M, neuf miroirs
    # source-command-* (40 -> 49) ; T-01M5BZC1Y0T36EHTZY9AKZ650F, la skill seo (49 -> 50).
    assert len(sk.SKILLS_DU_KIT) == 50, len(sk.SKILLS_DU_KIT)
    if sk.EST_LE_KIT:
        assert sk.readme_du_kit(), f"README.md du kit sans le titre {sk.TITRE_README_KIT!r}"
    bancs_sh = [p for p in t if p.endswith(".test.sh")]
    sous = [p for p in bancs_sh if p.startswith(sk.RACINES_DU_KIT)]
    assert sous, "aucun `*.test.sh` sous une racine du kit : le filtre serait vide"
    if sk.EST_LE_KIT:
        assert sous == bancs_sh, f"`*.test.sh` du kit hors RACINES_DU_KIT : {sorted(set(bancs_sh) - set(sous))}"
    assert "src/" not in sk.RACINES_DU_KIT and "src/cadre/" in sk.RACINES_DU_KIT


def test_la_regle_seule_classe_kit_les_jambes_du_kit_registre_par_registre():
    vus = {}
    for registre in REGISTRES:
        toutes = jambes(registre)
        du_kit = [j for j in toutes if sk.jambe_du_kit(j)]
        vus[registre] = (len(toutes), len(du_kit))
        assert du_kit, f"{registre} : aucune jambe du kit — le filtre des bancs serait vide"
        if sk.EST_LE_KIT:
            assert len(du_kit) == len(toutes), (
                f"{registre} : la règle classe adoptant une jambe du kit : "
                f"{[sk.scripts_cites(j) for j in toutes if not sk.jambe_du_kit(j)]}")
    print(f"[surface_kit] jambes (toutes, du kit) : {vus}")


@pytest.mark.parametrize("forme", FORMES)
def test_un_script_de_l_adoptant_est_classe_adoptant_sous_chaque_forme(forme):
    adoptant = forme.format(s="scripts/zz.py")
    du_kit = forme.format(s=".codex/hooks/session_context.py")
    assert "scripts/zz.py" in sk.scripts_cites(adoptant), sk.scripts_cites(adoptant)
    assert not sk.jambe_du_kit(adoptant), adoptant
    assert sk.jambe_du_kit(du_kit), (du_kit, sk.scripts_cites(du_kit))
    assert sk.jambe_jugee(adoptant) is sk.EST_LE_KIT


def test_borne_c20_une_jambe_sans_script_reconnaissable_reste_jugee():
    for nue in ("npx --yes lint-staged", "true", ""):
        assert sk.scripts_cites(nue) == []
        assert sk.jambe_du_kit(nue), nue


def test_une_jambe_du_kit_ou_l_adoptant_chaine_son_script_reste_du_kit():
    """F3 (critic-opus S-01M55R2D79) : un script du kit autre qu'un lanceur suffit."""
    assert sk.jambe_du_kit('bash "$CLAUDE_PROJECT_DIR/.claude/hooks/safe-bash.sh" && python3 "$CLAUDE_PROJECT_DIR/scripts/audit.py"')


def test_scripts_adoptant_ne_retire_que_ce_que_seules_les_jambes_de_l_adoptant_citent(monkeypatch):
    """F1 (critic-opus S-01M55R2D79), aux deux formes de registre. Une `statusLine`
    n'est pas lue ; un script qu'une jambe du kit cite aussi reste jugé."""
    doc = {"statusLine": {"type": "command", "command": "bash src/zz/status.sh"}, "hooks": {
        "PreToolUse": [
            {"hooks": [{"type": "command", "command": 'python3 "$CLAUDE_PROJECT_DIR/src/zz/hook.py" pre',
                        "commandWindows": "python src/zz/win.py pre"}]},
            {"hooks": [{"type": "command", "command":
                        'bash "$CLAUDE_PROJECT_DIR/.claude/hooks/safe-bash.sh" && python3 src/zz/chaine.py'}]},
            {"hooks": [{"type": "command", "command": "bash .agents/pyrun.sh src/zz/chaine.py"}]}],
        "preToolUse": [{"type": "command", "bash": "AGENTS_HOOK_HOST=copilot bash .agents/pyrun.sh src/zz/flat.py",
                        "powershell": "& src/zz/flat.ps1"}]}}
    monkeypatch.setattr(sk, "EST_LE_KIT", True)
    assert sk.scripts_adoptant(doc) == set()
    monkeypatch.setattr(sk, "EST_LE_KIT", False)
    assert sk.scripts_adoptant(doc) == {"src/zz/hook.py", "src/zz/win.py", "src/zz/flat.py", "src/zz/flat.ps1"}


def test_le_roster_se_lit_dans_un_arbre_vendor_seul():
    """Le paquet `cadre` vit sous `.agents/vendor/cadre` seul : `agents_du_kit`
    le lit là, dans un processus neuf (un `cadre` déjà chargé ailleurs y serait
    refusé par provenance). MUTATION : rétablir `root / "src" / "cadre"` comme
    seule source → AssertionError « source absente » → rouge."""
    source = sk._vendor_paths().exiger(ROOT, "cadre")
    with tempfile.TemporaryDirectory(prefix="surface-kit-") as d:
        arbre = Path(d)
        shutil.copytree(source, arbre / ".agents" / "vendor" / "cadre",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        sonde = ("import sys; sys.path.insert(0, sys.argv[1]); import surface_kit as sk; "
                 "from pathlib import Path; print('\\n'.join(sorted(sk.agents_du_kit(Path(sys.argv[2])))))")
        r = subprocess.run([sys.executable, "-B", "-c", sonde, str(EVALS), str(arbre)],
                           capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    noms = set(r.stdout.split())
    assert noms and noms == set(sk.agents_du_kit()), sorted(noms ^ set(sk.agents_du_kit()))


def test_une_source_absente_leve_et_un_readme_etranger_n_est_pas_celui_du_kit():
    with tempfile.TemporaryDirectory(prefix="surface-kit-") as d:
        arbre = Path(d)
        with pytest.raises(AssertionError):
            sk.agents_du_kit(arbre)
        with pytest.raises(AssertionError):
            sk.workflows_du_kit(arbre)
        (arbre / "contract.lock.json").write_text(
            json.dumps({"elements": [{"element": "cli:x"}]}), encoding="utf-8")
        with pytest.raises(AssertionError):
            sk.workflows_du_kit(arbre)
        assert not sk.readme_du_kit(arbre)
        (arbre / "README.md").write_text("# Projet Zz\n", encoding="utf-8")
        assert not sk.readme_du_kit(arbre)
        (arbre / "README.md").write_text(sk.TITRE_README_KIT + "\n\ncorps\n", encoding="utf-8")
        assert sk.readme_du_kit(arbre)
