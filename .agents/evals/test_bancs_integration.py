"""Intégration de la liste des bancs (T-01M576S8956DA9FMXY384P7EYF, après fusion des six lots).

CE QU'IL JUGE, ZÉRO LLM, sur l'arbre RÉEL :
  (I1) le VRAI hook `.claude/hooks/bancs-mandat.sh` × la VRAIE déf `.claude/agents/dev-mono.md` : un
       mandat sans ligne `BANCS:` est refusé (rc 2, `BLOCKED`), le même avec une ligne valide passe
       (rc 0) ; `Explore` (déf hors ensemble) passe sans ligne ; un mandat d'exec-critic qui recopie
       THE BENCH LIST et THE EXEC-CRITIC MANDATE de la SKILL kickoff, plus `BANCS: aucun | …`, passe
       (la doctrine recopiée ne fabrique aucune ligne `BANCS:`) ; une charge cassée passe sous
       `COVERAGE DEGRADED` ;
  (I2) l'ensemble des défs ancrées `BANCS-BORNES (T-01M576S8956DA9FMXY384P7EYF)` sous `.claude/agents`
       est EXACTEMENT les sept noms, et THE BENCH LIST cite exactement ces sept-là ;
  (I3) VOYAGE : `sync_template.match_rule` rend None (TAKE) pour chaque chemin des six `LOT:` et de
       l'intégration, SAUF `docs/interne/chantier/lots/workflow-fournee.js`, `strip:` par construction
       (archive du lanceur historique, kit seul) et attendu tel ; TAKE aussi pour le lanceur voyageur
       `.claude/workflows/workflow-fournee.js`, les cinq défs d'hôte de l'orchestrateur et `AGENTS.md`
       (T-01M57JS1GFPVQ93BGEFGX08FDB) — des CHAÎNES, jamais le contenu du lanceur ; la copie réelle
       par `--apply` est le témoin `test_apply_workflow_travels_to_adopter` de `test_sync_template.py` ;
  (I4) un mutant par volet, appliqué en mémoire ou dans une racine `mktemp -d`, jamais dans l'arbre :
       ancre ôtée d'une copie de dev-mono.md, 8e nom ajouté à THE BENCH LIST, `strip:` du hook puis
       `strip: .claude/workflows/` ajoutés à une copie de `.template-exclude` — chacun rougit ;
  (I5) l'ENREGISTREMENT : une seule jambe `bancs-mandat.sh`, en PreToolUse, matcher `Agent|Task`,
       seule ou première de son entrée, par le même lanceur durci que `safe-bash.sh` sur Bash ; cinq
       mutants en mémoire (jambe retirée, jambe intercalée devant, matcher réduit, lanceur nu, jambe
       déplacée) rougissent ;
  (I6) la règle écrite à `guardrails/SKILL.md` et `README-OTHER-HOSTS.md` (deux lignes `BANCS:`
       refusées, la première sortie décide, sortie à côté d'une liste `ambigu`, horizon de 500,
       fail-open dit, nom de def absent dit, racine de session, noms de bancs de la liste fermée)
       est portée, et le VRAI hook tient les deux premières, l'ambiguïté et le nom absent.
Les valeurs attendues sont ÉCRITES ICI, jamais extraites d'une surface (L-00000261) : le plan vit sous
`docs/tasks/`, qui ne voyage pas, et n'est jamais lu.
CE QU'IL NE PROUVE PAS : que l'hôte déclenche le hook sur un appel Agent réel (NON MESURÉ, sondes
dans `.agents/skills/guardrails/SKILL.md`), ni que la liste d'un mandat couvre le dû.
SAUTS ANNONCÉS : sans `bash`, les volets du hook sautent avec leur raison. Aucun volet ne dépend de
`.agents/IS_THE_KIT` ni de `docs/interne/` : le banc voyage et joue chez l'adoptant.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HOOK = ".claude/hooks/bancs-mandat.sh"
SKILL = ".agents/skills/kickoff/SKILL.md"
ANCRE = "BANCS-BORNES (T-01M576S8956DA9FMXY384P7EYF)"
TITRE = "**THE BENCH LIST (T-01M576S8956DA9FMXY384P7EYF).**"
TITRE_MANDAT = "**THE EXEC-CRITIC MANDATE"
NOMS = ("dev-mono", "dev-multi", "frontend-fidelity", "exec-critic", "critic-opus", "critic-fable",
        "critic-sonnet-max")
# Banc qui existe partout où ce fichier tourne : lui-même.
BANC = ".agents/evals/test_bancs_integration.py"
MANDAT_DEV = "Tu es le dev du lot X. Write-set : a.py. Lance la suite complète et les bancs voisins."

KIT_SEUL = "docs/interne/chantier/lots/workflow-fournee.js"


def _vendor_paths():
    """`vendor_paths.py` chargé PAR CHEMIN (patron v3prep) : `sys.path` n'est pas touché."""
    spec = importlib.util.spec_from_file_location(
        "_bancs_integration_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


VP = _vendor_paths()


def cadre_rel(racine: Path = ROOT) -> str:
    """Le paquet `cadre` relatif à `racine`, où qu'il vive (le neuf gagne) ; absent : l'ancien lieu."""
    dossier = VP.dossier_paquet(racine, "cadre")
    return (dossier.relative_to(Path(racine).resolve()) if dossier else VP.ANCIENS["cadre"]).as_posix()


# Le roster est jugé là où le paquet vit : un `strip:` du lieu neuf rougit le voyage.
_HOTES = (".claude/agents/{}.md", ".codex/agents/{}.toml", ".github/agents/{}.agent.md",
          ".gemini/agents/{}.md", ".kimi-code/agents/{}.md", cadre_rel() + "/data/roster/{}.json")
WRITE_SET = (
    # A
    ".claude/hooks/bancs-mandat.sh", ".claude/hooks/bancs-mandat.test.sh", ".claude/settings.json",
    ".agents/evals/test_python_hook_launchers.py", ".agents/skills/guardrails/SKILL.md", "README-OTHER-HOSTS.md",
    # D
    *(h.format(n) for n in ("dev-mono", "dev-multi", "frontend-fidelity") for h in _HOTES),
    ".agents/evals/test_bancs_bornes_devs.py",
    # J
    *(h.format(n) for n in ("exec-critic", "critic-opus", "critic-fable", "critic-sonnet-max") for h in _HOTES),
    ".agents/evals/test_bancs_bornes_juges.py",
    # K
    ".claude/commands/kickoff.md", ".agents/skills/kickoff/SKILL.md", ".claude/commands/night.md",
    ".agents/skills/night/SKILL.md", KIT_SEUL, ".agents/evals/test_bancs_mandat_lanceurs.py",
    # P
    ".claude/commands/planning.md", ".agents/skills/planning/SKILL.md", ".agents/evals/test_bancs_plan_tests.py",
    # INTÉGRATION
    BANC,
)
# Le lanceur voyageur (T-01M57JS1GFPVQ93BGEFGX08FDB) : chemins écrits ici, le fichier n'est jamais lu.
LANCEUR = ".claude/workflows/workflow-fournee.js"
VOYAGE_LANCEUR = (LANCEUR, *(h.format("orchestrator") for h in _HOTES[:5]), "AGENTS.md")


def lire(chemin: str, racine: Path = ROOT) -> str:
    return (racine / chemin).read_text(encoding="utf-8")


def paragraphe(t: str, titre: str) -> str:
    i = t.index(titre)
    j = t.find("\n\n", i)
    return t[i:(len(t) if j < 0 else j)]


def _bash() -> str:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash absent : volet du hook bancs-mandat non joué")
    return bash


def hook(charge: bytes, racine: Path = ROOT) -> subprocess.CompletedProcess:
    """Le hook réel (`ROOT`), jugeant les défs de `racine`, événements dans un `mktemp -d`."""
    with tempfile.TemporaryDirectory(prefix="bancs-integ-") as ev:
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(racine), "AGENTS_EVENTS_DIR": ev}
        return subprocess.run([_bash(), str(ROOT / HOOK)], input=charge, capture_output=True, env=env,
                              cwd=str(racine), timeout=60)


def appel(nom: str, prompt: str) -> bytes:
    return json.dumps({"tool_name": "Agent", "tool_input": {"subagent_type": nom, "prompt": prompt}}).encode()


def mandat_exec_critic(skill: str) -> str:
    return "\n\n".join((paragraphe(skill, TITRE_MANDAT), paragraphe(skill, TITRE),
                        "BANCS: aucun | relecture de doctrine"))


# --- (I1) vrai hook × vraie déf --------------------------------------------------------------
def test_dev_mono_sans_bancs_refuse() -> None:
    r = hook(appel("dev-mono", MANDAT_DEV))
    assert r.returncode == 2 and b"BLOCKED by hook: sans-liste" in r.stderr, (r.returncode, r.stderr)


def test_dev_mono_avec_bancs_passe() -> None:
    r = hook(appel("dev-mono", MANDAT_DEV + "\nBANCS: " + BANC))
    assert r.returncode == 0 and b"BLOCKED" not in r.stderr, (r.returncode, r.stderr)


def test_explore_sans_bancs_passe() -> None:
    r = hook(appel("Explore", MANDAT_DEV))
    assert r.returncode == 0 and r.stderr == b"", (r.returncode, r.stderr)


def test_exec_critic_doctrine_recopiee_passe() -> None:
    prompt = mandat_exec_critic(lire(SKILL))
    lignes = [ligne for ligne in prompt.split("\n") if ligne.startswith("BANCS: ")]
    assert lignes == ["BANCS: aucun | relecture de doctrine"], lignes
    r = hook(appel("exec-critic", prompt))
    assert r.returncode == 0 and b"BLOCKED" not in r.stderr, (r.returncode, r.stderr)


@pytest.mark.parametrize("charge", [b"", b"{pas du json", b"\xff\xfe"], ids=["vide", "cassee", "non-utf8"])
def test_charge_illisible_degradee(charge: bytes) -> None:
    r = hook(charge)
    assert r.returncode == 0 and "COVERAGE DEGRADED — bancs-mandat".encode() in r.stderr, (r.returncode, r.stderr)


def test_mutant_ancre_otee_de_dev_mono() -> None:
    """← l'ancre ôtée d'une COPIE de dev-mono.md (racine `mktemp -d`) : le même mandat passe, donc le
    refus de (I1) tient bien à l'ancre de la vraie déf."""
    vraie = lire(".claude/agents/dev-mono.md")
    assert vraie.count(ANCRE) == 1, "dev-mono.md : ancre absente ou doublée"
    with tempfile.TemporaryDirectory(prefix="bancs-mutant-") as d:
        racine = Path(d)
        (racine / ".claude/agents").mkdir(parents=True)
        (racine / ".claude/agents/dev-mono.md").write_text(vraie.replace(ANCRE, "BANCS-BORNES"), encoding="utf-8")
        r = hook(appel("dev-mono", MANDAT_DEV), racine)
    assert r.returncode == 0, "mutant SURVIVANT : la déf sans ancre est encore gardée"


# --- (I2) l'ensemble ancré ---------------------------------------------------------------------
def fautes_ensemble(defs: dict[str, str], skill: str) -> list[str]:
    f: list[str] = []
    ancrees = {nom for nom, t in defs.items() if ANCRE in t}
    if ancrees != set(NOMS):
        f.append(f"défs ancrées {sorted(ancrees)} ≠ les sept")
    para = paragraphe(skill, TITRE)
    cites = {nom for nom in defs if re.search(rf"(?<![\w-]){re.escape(nom)}(?![\w-])", para)}
    if cites != set(NOMS):
        f.append(f"THE BENCH LIST cite {sorted(cites)} ≠ les sept")
    return f


def defs_reelles() -> dict[str, str]:
    return {p.stem: p.read_text(encoding="utf-8") for p in sorted((ROOT / ".claude/agents").glob("*.md"))}


def test_ensemble_ancre_egal_aux_sept_noms() -> None:
    assert fautes_ensemble(defs_reelles(), lire(SKILL)) == []


def test_mutants_ensemble() -> None:
    defs, skill = defs_reelles(), lire(SKILL)
    assert "planner" in defs, "déf planner absente : le mutant du 8e nom n'a rien à citer"
    mutants = {
        "ancre_otee_dev_mono": ({**defs, "dev-mono": defs["dev-mono"].replace(ANCRE, "")}, skill),
        "huitieme_nom": (defs, skill.replace("critic-fable or critic-sonnet-max",
                                             "critic-fable, planner or critic-sonnet-max", 1)),
    }
    for nom, (d, s) in mutants.items():
        assert (d, s) != (defs, skill), f"mutant {nom} sans effet"
        assert fautes_ensemble(d, s), f"mutant SURVIVANT : {nom}"


# --- (I3) voyage -------------------------------------------------------------------------------
def _sync_template():
    chemin = str(ROOT / ".agents" / "bin")
    if chemin not in sys.path:
        sys.path.insert(0, chemin)
    import sync_template as st  # même import que `test_plan_depends_mirror.py` (module inscrit)
    return st


def fautes_voyage(exclude: str) -> list[str]:
    st = _sync_template()
    regles = st.parse_exclude(exclude)
    f: list[str] = []
    for chemin in (*WRITE_SET, *VOYAGE_LANCEUR):
        regle = st.match_rule(chemin, regles)
        if chemin == KIT_SEUL:
            if regle is None or regle.polarity != "strip":
                f.append(f"{chemin} : attendu `strip:` (kit seul), vu {regle}")
        elif regle is not None:
            f.append(f"{chemin} ne voyage pas : {regle.raw.strip()}")
    return f


def test_write_set_complet() -> None:
    # 63 -> 60 (T-01M5PCCHMWXTRCM5QJT8J5KNEH) : le lot Q (commande, skill et banc de la route de
    # dev locale) est parti avec elle.
    assert len(WRITE_SET) == len(set(WRITE_SET)) == 60, len(WRITE_SET)


def test_voyage() -> None:
    assert fautes_voyage(lire(".template-exclude")) == []


def test_mutant_voyage_strip_du_hook() -> None:
    exclude = lire(".template-exclude")
    assert fautes_voyage(exclude + "\nstrip: .claude/hooks/bancs-mandat.sh\n"), (
        "mutant SURVIVANT : le hook ne voyagerait plus")


def test_voyage_lanceur_sept_chemins() -> None:
    assert len(VOYAGE_LANCEUR) == len(set(VOYAGE_LANCEUR) - set(WRITE_SET)) == 7, VOYAGE_LANCEUR


def test_mutant_voyage_strip_du_lanceur() -> None:
    fautes = fautes_voyage(lire(".template-exclude") + "\nstrip: .claude/workflows/\n")
    assert [f for f in fautes if f.startswith(LANCEUR + " ")], (
        "mutant SURVIVANT : le lanceur ne voyagerait plus")


# --- (I5) l'ENREGISTREMENT du hook --------------------------------------------------------------
# Un banc de comportement reste vert quand la jambe disparaît du registre : on épingle l'événement,
# le matcher, la commande et la place (seul ou premier de son entrée, même lanceur durci que
# safe-bash.sh sur Bash).
#: T-01M4JRFRSMSA57ZT7D099G9F3H (S-01M5WG8ZJT) : la jambe tourne sous le lanceur qui échoue FERMÉ ;
#: l'exit 2 de « python absent » ou d'une erreur interne y bloque nu et passe tel quel par garde-fermee.
QUEUE_FERMEE = ('AGENTS_HOOK_HOST=claude exec bash -p "$CLAUDE_PROJECT_DIR/.agents/security/garde-fermee.sh" '
                '--echeance=7 "$CLAUDE_PROJECT_DIR/.claude/hooks/bancs-mandat.sh"')


def fautes_cablage(reglages: dict) -> list[str]:
    jambes = [(evt, i, j) for evt, entrees in reglages.get("hooks", {}).items()
              for i, e in enumerate(entrees) for j, h in enumerate(e.get("hooks", []))
              if "bancs-mandat.sh" in h.get("command", "")]
    if len(jambes) != 1:
        return [f"bancs-mandat.sh enregistré {len(jambes)} fois : {jambes}"]
    evt, i, j = jambes[0]
    f: list[str] = []
    if evt != "PreToolUse":
        f.append(f"bancs-mandat.sh sur {evt}, attendu PreToolUse")
    entree = reglages["hooks"][evt][i]
    if not {"Agent", "Task"} <= set(entree.get("matcher", "").split("|")):
        f.append(f"matcher {entree.get('matcher')!r} sans Agent|Task")
    jambe = entree["hooks"][j]
    if not jambe.get("command", "").endswith(QUEUE_FERMEE):
        f.append("commande hors forme fermée (garde-fermee.sh --echeance=7) sur .claude/hooks/bancs-mandat.sh")
    if j != 0:
        f.append(f"bancs-mandat.sh ni seul ni premier de son entrée {entree.get('matcher')!r} : place {j}")
    gardes = [h for e in reglages["hooks"].get("PreToolUse", []) if e.get("matcher") == "Bash"
              for h in e.get("hooks", []) if "/.claude/hooks/safe-bash.sh" in h.get("command", "")]
    if len(gardes) != 1:
        f.append(f"lanceur durci de référence introuvable : safe-bash.sh vu {len(gardes)} fois sur Bash")
    else:
        sien = {**jambe, "command": jambe["command"].replace("bancs-mandat.sh", "X")}
        frere = gardes[0]
        if sien != {**frere, "command": frere["command"].replace("safe-bash.sh", "X")}:
            f.append("lanceur de bancs-mandat.sh ≠ celui de safe-bash.sh")
    return f


def test_cablage() -> None:
    assert fautes_cablage(json.loads(lire(".claude/settings.json"))) == []


def _entree_bancs(s: dict) -> dict:
    return next(e for e in s["hooks"]["PreToolUse"]
                if any("bancs-mandat.sh" in h.get("command", "") for h in e.get("hooks", [])))


def _sans_jambe(s: dict) -> None:
    e = _entree_bancs(s)
    e["hooks"] = [h for h in e["hooks"] if "bancs-mandat.sh" not in h["command"]]


def _ordre_inverse(s: dict) -> None:
    """Une jambe intercalée AVANT bancs-mandat.sh : il n'est plus premier."""
    e = _entree_bancs(s)
    e["hooks"].insert(0, {"type": "command", "command": 'bash "$CLAUDE_PROJECT_DIR/.claude/hooks/x.sh"'})


def _matcher_reduit(s: dict) -> None:
    _entree_bancs(s)["matcher"] = "Agent"


def _lanceur_nu(s: dict) -> None:
    for h in _entree_bancs(s)["hooks"]:
        if "bancs-mandat.sh" in h["command"]:
            h["command"] = 'bash "$CLAUDE_PROJECT_DIR/.claude/hooks/bancs-mandat.sh"'


def _enveloppe_retiree(s: dict) -> None:
    """Préfixe gardé, lanceur fermé retiré : la queue redevient `exec bash -p …/bancs-mandat.sh`."""
    for h in _entree_bancs(s)["hooks"]:
        if "bancs-mandat.sh" in h["command"]:
            h["command"] = h["command"].replace(
                QUEUE_FERMEE, 'exec bash -p "$CLAUDE_PROJECT_DIR/.claude/hooks/bancs-mandat.sh"', 1)


def _vers_post(s: dict) -> None:
    e = _entree_bancs(s)
    jambe = [h for h in e["hooks"] if "bancs-mandat.sh" in h["command"]]
    e["hooks"] = [h for h in e["hooks"] if "bancs-mandat.sh" not in h["command"]]
    s["hooks"].setdefault("PostToolUse", []).append({"matcher": "Agent|Task", "hooks": jambe})


@pytest.mark.parametrize("mutant", [_sans_jambe, _ordre_inverse, _matcher_reduit, _lanceur_nu, _vers_post,
                                    _enveloppe_retiree],
                         ids=["jambe-retiree", "ordre-inverse", "matcher-reduit", "lanceur-nu", "vers-post",
                              "enveloppe-retiree"])
def test_mutants_cablage(mutant) -> None:
    s = json.loads(lire(".claude/settings.json"))
    mutant(s)
    assert s != json.loads(lire(".claude/settings.json")), f"mutant {mutant.__name__} sans effet"
    assert fautes_cablage(s), f"mutant SURVIVANT : {mutant.__name__}"


# --- (I6) la règle écrite = la règle du hook --------------------------------------------------
# Deux lignes `BANCS:` refusées, la première `BANCS-SANS-BORNE:` qui décide, l'horizon de 500 et le
# fail-open dit : chaque surface les porte, et le VRAI hook les tient.
DOCTRINE = {
    ".agents/skills/guardrails/SKILL.md": ("- **`bancs-mandat` (T-01M576S8956DA9FMXY384P7EYF)**", (
        "deux lignes `BANCS:` sont refusées (`sans-liste`)", "à plusieurs, la première décide",
        "recopié dans ses 500 premiers caractères est refusé",
        # S-01M5YZ6VJN : python absent ou erreur interne = REFUS, plus jamais DEGRADED.
        "python absent ou erreur interne (exception, interpréteur qui ne démarre pas) : refus rc 2, "
        "sans hook.deny", "remède : installer python 3 (python3, python ou py -3)",
        "refusée `ambigu` à côté d'une ligne `BANCS:`", "aucun nom de def dans la charge",
        "racine de session `$CLAUDE_PROJECT_DIR`, jamais le worktree jugé",
        "`*_test.{py,go}`", "`*_spec.rb`", "`*{Test,Tests,IT}.{java,kt,cs}`", "un `.rs` sous un répertoire `tests/`",
        # T-01M57X2MMT : le refus de clôture ouverte, son remède, son ordre, et le résidu NON VU.
        "est refusée (`cloture-ouverte`, remède : « referme la clôture »)",
        "AVANT que la ligne `BANCS:` ou `BANCS-SANS-BORNE:` soit choisie",
        "deux hunks ` ```sh ` APPARIÉS (un nombre pair de clôtures) masquent encore la liste",
        "toute ligne qui commence par ``` ou ~~~ (blancs de tête retirés, quels qu'ils soient")),
    "README-OTHER-HOSTS.md": ("**Hooks registered in Claude Code only**", (
        "two `BANCS:` lines being refused (`sans-liste`)", "when several, the first decides",
        "copied within its first 500 characters refused",
        "missing python or an internal error (an exception, an interpreter that does not start): refused at rc 2, "
        "no hook.deny", "remedy: install python 3 (python3, python or py -3)",
        "refused `ambigu` next to a `BANCS:` line", "no def name in the payload",
        "session root `$CLAUDE_PROJECT_DIR`, never the judged worktree",
        "`*_test.{py,go}`", "`*_spec.rb`", "`*{Test,Tests,IT}.{java,kt,cs}`", "a `.rs` under a `tests/` directory",
        "is refused (`cloture-ouverte`, remedy « referme la clôture »)",
        "before the `BANCS:` or `BANCS-SANS-BORNE:` line is chosen",
        "NOT SEEN: two paired ```sh hunks still hide the list between them, and an excerpt `BANCS:` line left "
        "visible outside them then decides (rc 0; with nothing outside, refused `sans-liste`)",
        "A line inside a ``` or ~~~ block does not count")),
}


def ligne(t: str, titre: str) -> str:
    """La ligne (puce ou paragraphe d'une ligne) qui porte `titre`, jamais les puces voisines."""
    i = t.index(titre)
    j = t.find("\n", i)
    return t[i:(len(t) if j < 0 else j)]


def fautes_doctrine(textes: dict[str, str]) -> list[str]:
    f: list[str] = []
    for chemin, (titre, phrases) in DOCTRINE.items():
        porteuse = ligne(textes[chemin], titre)
        f += [f"{chemin} : « {p} » absent" for p in phrases if p not in porteuse]
    return f


def test_doctrine_des_surfaces() -> None:
    assert fautes_doctrine({c: lire(c) for c in DOCTRINE}) == []


def test_mutants_doctrine() -> None:
    textes = {c: lire(c) for c in DOCTRINE}
    for chemin, (_, phrases) in DOCTRINE.items():
        for p in phrases:
            assert fautes_doctrine({**textes, chemin: textes[chemin].replace(p, "")}), (
                f"mutant SURVIVANT : {chemin} sans « {p} »")


def test_deux_lignes_bancs_refusees() -> None:
    r = hook(appel("dev-mono", MANDAT_DEV + "\nBANCS: " + BANC + "\nBANCS: " + BANC))
    assert r.returncode == 2 and b"BLOCKED by hook: sans-liste" in r.stderr, (r.returncode, r.stderr)


@pytest.mark.parametrize("premiere, seconde, rc, attendu", [
    ("<pourquoi> exemple", "urgence pilote tracee", 2, b"BLOCKED by hook: raison-gabarit"),
    ("urgence pilote tracee", "<pourquoi> exemple", 0, "SORTIE TRACÉE".encode()),
], ids=["gabarit-d-abord", "raison-d-abord"])
def test_premiere_sortie_decide(premiere: str, seconde: str, rc: int, attendu: bytes) -> None:
    r = hook(appel("dev-mono", f"{MANDAT_DEV}\nBANCS-SANS-BORNE: {premiere}\nBANCS-SANS-BORNE: {seconde}"))
    assert r.returncode == rc and attendu in r.stderr, (r.returncode, r.stderr)


def test_sortie_a_cote_d_une_liste_ambigue() -> None:
    """Une sortie relayée d'un rapport à côté d'une liste valide ne désarme pas la garde."""
    r = hook(appel("dev-mono", f"{MANDAT_DEV}\nBANCS-SANS-BORNE: relayé depuis un rapport de dev\nBANCS: {BANC}"))
    assert r.returncode == 2 and b"BLOCKED by hook: ambigu" in r.stderr, (r.returncode, r.stderr)


def test_cloture_ouverte_refusee_avant_la_liste() -> None:
    """Le VRAI hook tient la doctrine : une liste valide AVANT un hunk ` ```sh ` non refermé ne
    décide pas ; refus `cloture-ouverte` qui nomme la ligne de la clôture, remède seul."""
    r = hook(appel("dev-mono", f"{MANDAT_DEV}\nBANCS: {BANC}\n ```sh\nBANCS: {BANC}"))
    assert r.returncode == 2, (r.returncode, r.stderr)
    assert r.stderr.decode("utf-8").splitlines() == [
        "BLOCKED by hook: cloture-ouverte : ligne-3", "referme la clôture"], r.stderr


def test_sans_nom_de_def_degrade_dit() -> None:
    charge = json.dumps({"tool_name": "Agent", "tool_input": {"prompt": MANDAT_DEV}}).encode()
    r = hook(charge)
    assert r.returncode == 0 and "COVERAGE DEGRADED — bancs-mandat: aucun nom de def".encode() in r.stderr, (
        r.returncode, r.stderr)
