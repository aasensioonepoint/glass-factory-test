"""Les critiques de clôture tiennent un SHELL sous Copilot et Gemini CLI (alignement des hotes, lot L-E ; H-51, H-64, H-08).

POURQUOI. Le corps d'un critique exige « aucune affirmation sans sortie de commande » (S-00004500, la
detection ACTIVE est la garde de cloture). Mesure du 2026-10-12 : `critic-sonnet-max` sous Copilot n'avait
que `read` et `search` (S5) ; les trois critiques Gemini n'avaient ni `run_shell_command`. Sans shell, la
revue d'un hote n'est qu'une relecture.

CE QUE CE BANC TIENT : (1) les trois critiques Copilot portent `shell`, les trois Gemini
`run_shell_command` ; (2) le corps dit que ce shell MESURE et n'ecrit jamais ; (3) la banniere de fin
n'est pas echappee (`&lt;n&gt;` rendait un texte litteral, H-64) ; (4) les limites Gemini de H-08
(`max_turns`, `timeout_mins`) sont posees sur les critiques ET sur dev-mono, dev-multi, indexer.

ET LA CONSIGNE TIENT SUR L'OUTIL (exec-critic du lot L3, NO_GO B1/B2, 2026-10-12) : une def qui prescrit
de lire le board « par la CLI » sans porter de shell donne une consigne INEXECUTABLE ; une def qui la
prescrit puis l'interdit (« not even `list` ») s'annule. Tous les bancs etaient verts. D'ou : (5) aucune
def SANS outil shell (Claude sans `Bash`, Gemini sans `run_shell_command`, Copilot sans
`shell`/`execute`/`bash`/`powershell`), NI aucune def qui interdit `tasks.py` ENTIER (« never invoke
`tasks.py`, … », les 4 `documenter`), ne porte la forme EXECUTABLE d'une lecture du board — l'interpreteur
(`python … tasks.py list`), un verbe imperatif (run/invoke/call/execute) ou la prescription d'un canal
(« through the CLI », « with ») devant `tasks.py list` ;
(6) les trois `orchestrator` et les quatre `documenter` lisent la VUE generee `.agents/state/local/TASKS.md`
(outil de LECTURE, jamais le magasin a la main) et disent `board illisible` quand elle manque (option (ii),
delta S-01M4RSQKKN : l'interdit du documenter reste mot pour mot, epingle `cli-ban` de
`test_documenter_shell_contract.py`) ; (8) aucune def des hotes du fix ne lit
`.agents/state/board/TASKS.json` a la main (meme motif que `grep_tasksjson.sh` du plan, borne aux defs).

CE QU'IL NE PROUVE PAS : que l'hote honore ces limites a l'execution (coupe reelle non observee, hors
balayage) ni que l'alias `shell` de Copilot soit le seul nom valide (alias documente, deja tenu par
`documenter.agent.md`). Aucun hote n'est lance. BORNES NOMMEES de (5)-(8) : une simple MENTION de
`tasks.py list` (sans interpreteur ni verbe imperatif devant, ex. le motif `board illisible` du hook)
n'est pas jugee, ni une consigne CONDITIONNELLE (« if `tasks.py list --json` answers now » : corrigee a la
main dans les orchestrateurs, jamais vue par (5)) ; Codex n'a pas de liste d'outils (toute def y porte le
shell) : (5) n'y juge que l'interdit total, (6) et (8) le jugent ; `.kimi-code/agents/` (hote hors fix, S-01M4QWD5WD) n'est pas juge.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CRITIQUES = ("critic-opus", "critic-fable", "critic-sonnet-max")
LONGUES_GEMINI = CRITIQUES + ("dev-mono", "dev-multi", "indexer")
# T-01M5S9338BJP1B5RM3TG14AMYT : la PROSE des critiques est en anglais ; (2) est épinglé dans sa forme
# anglaise, et la forme française d'avant ne le satisfait plus (témoin dédié). (3) la bannière de fin est
# une ligne `▸` que l'agent IMPRIME au pilote : elle reste en français à l'octet (décision pilote
# S-01M5VCGTEBC76MKR63HJ2K67CE, `.agents/ref/WORKING_LANGUAGE.md`) ; sa traduction anglaise d'avant
# ne la satisfait plus (témoin dédié).
MESURE = ("serves to MEASURE", "never to write")
MESURE_FR = ("sert à MESURER", "jamais à écrire")
BANNIERE_FIN = "<n> trous, <n> trouvailles, <n> correctifs"
BANNIERE_FIN_EN = "<n> gaps, <n> findings, <n> fixes"


def _dit_que_le_shell_mesure(corps: str) -> bool:
    return all(m in corps for m in MESURE)


def _entete(path: Path) -> dict:
    texte = path.read_text(encoding="utf-8")
    assert texte.startswith("---\n"), path
    bloc = texte.split("\n---\n", 1)[0].splitlines()[1:]
    out = {}
    for ligne in bloc:
        m = re.fullmatch(r"([a-z_]+): (.*)", ligne)
        if m:
            out[m.group(1)] = m.group(2)
    return out


@pytest.mark.parametrize("nom", CRITIQUES)
def test_critique_copilot_tient_shell(nom):
    p = ROOT / ".github" / "agents" / f"{nom}.agent.md"
    assert "shell" in json.loads(_entete(p)["tools"])
    corps = p.read_text(encoding="utf-8")
    assert _dit_que_le_shell_mesure(corps)


@pytest.mark.parametrize("nom", CRITIQUES)
def test_critique_gemini_tient_run_shell_command(nom):
    p = ROOT / ".gemini" / "agents" / f"{nom}.md"
    assert "run_shell_command" in json.loads(_entete(p)["tools"])
    corps = p.read_text(encoding="utf-8")
    assert "&lt;" not in corps and "&gt;" not in corps
    assert BANNIERE_FIN in corps
    assert _dit_que_le_shell_mesure(corps)


@pytest.mark.parametrize("hote", (".github/agents/{}.agent.md", ".gemini/agents/{}.md"))
@pytest.mark.parametrize("nom", CRITIQUES)
def test_la_forme_francaise_d_avant_ne_satisfait_plus(nom, hote):
    """Force des épingles : la phrase française d'avant, mise à la place de l'anglaise, rougit (2) ;
    la bannière de fin traduite en anglais ne satisfait pas (3)."""
    corps = (ROOT / hote.format(nom)).read_text(encoding="utf-8")
    assert _dit_que_le_shell_mesure(corps), "base rouge"
    mute = corps
    for en, fr in zip(MESURE, MESURE_FR):
        mute = mute.replace(en, fr)
    assert mute != corps and not _dit_que_le_shell_mesure(mute)
    if hote.startswith(".gemini"):
        mute = corps.replace(BANNIERE_FIN, BANNIERE_FIN_EN)
        assert mute != corps and BANNIERE_FIN not in mute


@pytest.mark.parametrize("nom", LONGUES_GEMINI)
def test_limites_gemini_des_defs_longues(nom):
    e = _entete(ROOT / ".gemini" / "agents" / f"{nom}.md")
    assert (e.get("max_turns"), e.get("timeout_mins")) == ("100", "60")


# --- (5)-(8) : la consigne de lecture du board tient sur l'outil que la def porte ---
DEFS_A_LISTE = {  # hote -> motif ; Codex n'a pas de liste d'outils, Kimi est hors fix
    "claude": ".claude/agents/*.md",
    "gemini": ".gemini/agents/*.md",
    "copilot": ".github/agents/*.agent.md",
}
DEFS_DU_FIX = tuple(DEFS_A_LISTE.values()) + (".codex/agents/*.toml",)
SHELL_COPILOT = {"shell", "execute", "bash", "powershell"}  # `execute` et ses alias documentes
ORCHESTRATEURS = (".claude/agents/orchestrator.md", ".gemini/agents/orchestrator.md",
                  ".github/agents/orchestrator.agent.md")
DOCUMENTERS = (".claude/agents/documenter.md", ".gemini/agents/documenter.md",
               ".github/agents/documenter.agent.md", ".codex/agents/documenter.toml")
VUE = ".agents/state/local/TASKS.md"
# La forme EXECUTABLE d'une lecture du board : l'interpreteur, un verbe imperatif, ou la prescription d'un
# canal (« THROUGH THE CLI », « with ») devant `tasks.py list` — la formulation du defaut B1 SANS interpreteur
# (sonde E1 de l'exec-critic du delta L3) est une prescription, pas une simple MENTION.
LECTURE_CLI = re.compile(
    r"python3?\s+\S*tasks\.py\s+list|\b(?:run|invoke|call|execute)\b[^.\n]{0,40}?tasks\.py\s+list"
    r"|\b(?:through\s+the\s+cli|with)\b[^.\n]{0,40}?tasks\.py\s+list", re.I)
# Un interdit de `tasks.py` ENTIER (« never invoke `tasks.py`, `specs.py`… »), pas d'une liste de verbes
# (« never run `tasks.py new/start/…` » du communicator laisse `list` permis par construction).
INTERDIT_TOTAL = re.compile(r"never\s+(?:invoke|run|call)\s+`?tasks\.py`?,")
# Le motif de `grep_tasksjson.sh` (plan T-01M4NWRAZ4M5VTD7W27J9Z1PH4, H-53), borne aux defs.
LECTURE_TASKS_JSON = re.compile(r"(?m)(?:Read|read|reads|opening|from|^[0-9]+\.) `?\.agents/state/board/TASKS\.json")


def _a_un_shell(hote: str, entete: dict) -> bool:
    if "tools" not in entete:
        return True  # sans liste, l'hote donne tous ses outils
    if hote == "claude":
        return "Bash" in [t.strip() for t in entete["tools"].split(",")]
    noms = {t.lower() for t in json.loads(entete["tools"])}
    return bool(noms & ({"run_shell_command"} if hote == "gemini" else SHELL_COPILOT))


def _defs_sans_shell() -> list[str]:
    return sorted(p.relative_to(ROOT).as_posix()
                  for hote, motif in DEFS_A_LISTE.items() for p in ROOT.glob(motif)
                  if not _a_un_shell(hote, _entete(p)))


def _defs_du_fix() -> list[Path]:
    return sorted(p for motif in DEFS_DU_FIX for p in ROOT.glob(motif))


def _interdisent_tasks_py() -> list[str]:
    return sorted(p.relative_to(ROOT).as_posix() for p in _defs_du_fix()
                  if INTERDIT_TOTAL.search(" ".join(p.read_text(encoding="utf-8").split())))


def test_une_def_sans_shell_ou_qui_interdit_tasks_py_ne_prescrit_aucune_lecture_du_board_par_commande():
    sans_shell = _defs_sans_shell()
    interdisent = _interdisent_tasks_py()
    assert set(ORCHESTRATEURS) <= set(sans_shell), "population : les orchestrateurs n'ont pas de shell"
    assert set(DOCUMENTERS) <= set(interdisent), "population : les documenters interdisent tasks.py entier"
    fautes = {rel: [m.group(0) for m in LECTURE_CLI.finditer(" ".join((ROOT / rel).read_text(encoding="utf-8").split()))]
              for rel in sorted(set(sans_shell) | set(interdisent))}
    assert {k: v for k, v in fautes.items() if v} == {}


@pytest.mark.parametrize("rel", ORCHESTRATEURS + DOCUMENTERS)
def test_la_def_lit_la_vue_generee_et_dit_board_illisible(rel):
    # Blancs replies : la def Codex (TOML) coupe ses phrases a ~88 colonnes.
    texte = " ".join((ROOT / rel).read_text(encoding="utf-8").split())
    i = texte.find(VUE)
    assert i >= 0, f"{rel} : la vue {VUE} n'est pas nommee"
    fenetre = texte[i:i + 400]
    assert "board illisible" in fenetre and "never hand-parse" in fenetre, fenetre


def test_aucune_def_du_fix_ne_lit_tasks_json_a_la_main():
    defs = _defs_du_fix()
    assert len(defs) > 100, "population vide ou tronquee"
    fautes = [f"{p.relative_to(ROOT).as_posix()}:{texte.count(chr(10), 0, m.start()) + 1}"
              for p in defs for texte in [p.read_text(encoding="utf-8")]
              for m in LECTURE_TASKS_JSON.finditer(texte)]
    assert fautes == []


def test_les_motifs_mordent_et_se_taisent_ou_il_faut():
    assert LECTURE_CLI.search("read it with `python .agents/bin/tasks.py list --json`")
    assert LECTURE_CLI.search("Run `tasks.py list --task T-1` first")
    # E1 (exec-critic delta L3) : la prescription SANS interpreteur rougit aussi.
    assert LECTURE_CLI.search("Read the board THROUGH THE CLI (`tasks.py list --json`), else write board illisible")
    assert LECTURE_CLI.search("read the board with `tasks.py list --json`")
    assert not LECTURE_CLI.search("`motif=board illisible` (`tasks.py list` non-zero, timed out)")
    assert not LECTURE_CLI.search("if `tasks.py list --json`, run by the calling session, answers now")
    assert not LECTURE_CLI.search("the calling session runs `tasks.py writeset <T>`")
    assert INTERDIT_TOTAL.search("never invoke `tasks.py`, `specs.py`, `ledger.py` or `retro.py`")
    assert INTERDIT_TOTAL.search("never invoke tasks.py, specs.py, ledger.py or retro.py")
    assert not INTERDIT_TOTAL.search("never run `tasks.py new/start/stage/block/unblock/done`")
    assert LECTURE_TASKS_JSON.search("1. `.agents/state/board/TASKS.json` — is this task tracked?")
    assert not LECTURE_TASKS_JSON.search("the store is `TASKS.json` OR record files")
