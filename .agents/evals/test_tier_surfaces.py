"""Tier surfaces vs committed frontmatter — the docs must agree with HEAD.

WHY THIS EXISTS. A role's tier (model + default effort) is declared ONCE, in the
agent's frontmatter, and re-stated in four human-facing surfaces: the README
table, the README-CLAUDE mirror, the `tier` column of `.agents/ref/TOKEN_BUDGETS.md`,
and the roster table of `docs/usage.html`. Nothing kept those four honest with the
definitions, and they had drifted: orchestrator/planner/plan-critic shown `opus`
where HEAD carries `fable`, the two dev agents shown `sonnet` where HEAD carries
`claude-opus-4-8`, efforts stale in several cells (T-00000381, arbitrage
S-00000897). A doc that asserts a tier the definition does not hold hides the real
configuration from anyone reading it.

SOURCE OF TRUTH = the frontmatter COMMITTED AT HEAD, never the working tree
(L-00000297). The pilot tunes tiers on disk between commits, so the disk is a
moving target; only what is committed travels and only what is committed is what
the docs must describe. Definitions are therefore read with `git show HEAD:...`
(same subprocess-git precedent as .agents/evals/test_template_hygiene.py:48), and
the four doc surfaces are read from the WORKING TREE — that asymmetry is the whole
point.

WHERE THIS LIVES, AND WHY IT COMPARES TEXT. Neither `.agents/evals/` nor `docs/`
is covered by CODEBASE_INDEX, and `docs/usage.html` carries no indexed symbol, so
this net cannot ask the index for a `path:line` — it parses the four surfaces as
text and compares tokens. That is a feature: the surfaces it polices are exactly
the ones an index does not see.

MODEL COMPARED BY TOKEN, effort compared literally. A Claude `model:` field is
either a bare tier (`fable`) or a full model id carrying the tier as a
dash-separated token (`claude-opus-4-8`); both are live. Splitting on `[-_.]`
makes `opus` == `claude-opus-4-8` while never matching a substring like
`opusculum` (L-00000143, precedent TierRelationTests._model_rank in
test_golden_transcripts.py). Effort is a plain word and is compared as written,
only on the surfaces that carry it (the README tables always; usage.html only
where a cell shows `· <effort>`; TOKEN_BUDGETS never — it has no effort column).

TWO DELIBERATE EDGES.
  * communicator carries NO `model:` and NO `effort:` at HEAD — vacuity PINNED on
    purpose (S-00000897): it runs at the session model, so a pinned tier would
    forecast one nobody configured and would DOWNGRADE a session already at opus.
    The four surfaces must therefore show `session`/`—`, not a tier. Asserted by
    its own test rather than folded into the general sweep.
  * The `Per-agent defaults` table in the BODY of `.claude/agents/orchestrator.md`
    (mirrored on five hosts) diverges too, but is OUT OF SCOPE here — it is the
    definition of the agent that pilots the session, a five-file change the pilot
    opens as its own debt. This net does NOT cover it and does not pretend to.

WHAT THIS NET ACTUALLY EXERCISES — stated because it once claimed more than it
measured (T-00000415). Its only bite-proof replayed ONE parser out of four on
three synthetic lines; the mismatch loop, `parse_budget`, `parse_usage` and the
usage slice had no witness at all, so a stray `continue` in either branch of the
loop would have stayed green. Three guarantees now hold, each with a mutation
that reddens it:
  * REPLAY ON A TEMPORARY TREE. `load_surfaces(root)` takes a root, so the four
    parsers and the loop run again on a copy of the four files under a
    `TemporaryDirectory`. One mutation per surface must yield exactly five named
    lines, and the un-mutated copy must be silent. Nothing outside those four
    files is created — this net travels, so it assumes no state that does not.
  * `parse_budget` BOUNDED TO ITS SECTION. It swept the whole file: any
    `| name | token |` pipe line under the prose overwrote an agent's tier with
    no error, and the contradiction was reported as agreement. The `| agent |
    tier |` header now opens the table and the first non-row line closes it.
  * ROSTER, BOTH DIRECTIONS. Every agent committed at HEAD is named on all four
    surfaces and no surface names an agent HEAD does not carry (26/26 today),
    derived on both sides — never a pinned count, which would age into a lie.
Every mutated value is derived from HEAD rather than written as `opus`/`xhigh`,
so a retune of the witness moves its mutation with it.

THE CONTRACT, STATED SO IT IS NOT MISREAD LATER. This net follows HEAD. The day
the pilot commits a hand-set effort onto planner/plan-critic/exec-critic without
updating the docs in the same commit, this net reddens — that is the contract
working, not a false alarm; the remedy is to move the doc edit into that commit.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
from surface_kit import EST_LE_KIT, agents_du_kit, readme_du_kit  # noqa: E402

# .agents/evals/test_tier_surfaces.py -> repo root is parents[2]
ROOT = Path(__file__).resolve().parents[2]

# T-01M54MWW5GH (S-01M54ZQ6WC) : hors du kit, `README.md` est celui de l'adoptant
# sauf preuve du contraire (titre du kit) ; il n'est alors ni LU ni jugé — les
# arbres temporaires de ce banc ne le copient pas. Dans le kit : toujours jugé.
_SANS_README = not EST_LE_KIT and not readme_du_kit()

# Ordered weakest -> strongest, same map as TierRelationTests.CLAUDE_MODEL_RANK.
CLAUDE_MODEL_RANK = {"haiku": 0, "sonnet": 1, "opus": 2, "fable": 3}

# The three witnesses that must appear on every surface, so a sweep over an
# emptied parse cannot pass in silence (L-00000232): a chain poste, the pinned
# vacuity, and a dev agent. This is the FLOOR, not the coverage: since
# T-00000415 the population is checked in both directions, agent by agent, by
# test_every_head_agent_on_every_surface — these three stay as the cheap
# non-vacuity guard the other tests lean on. `dev-multi` is also the agent every
# mutation arm targets: it is present on all four surfaces and carries both a
# model and an effort, so one witness exercises both branches of the loop.
WITNESSES = ("orchestrator", "communicator", "dev-multi")

# Sentinel: this surface does not carry an effort for this agent (distinct from an
# effort whose value is None).
ABSENT = object()

MIDDOT = "·"  # the `·` separating model and effort in usage.html cells


# ---------------------------------------------------------------------------
# git — definitions are read from HEAD, never the disk (L-00000297)
# ---------------------------------------------------------------------------
def _git_available() -> bool:
    try:
        subprocess.run(["git", "--version"], capture_output=True)
        return True
    except (OSError, FileNotFoundError):
        return False


def git_show_head(path_in_repo: str) -> str:
    """`git show HEAD:<path>`. A non-zero rc (dubious ownership, missing ref, a
    path absent at HEAD) is a HARD FAILURE, never a skip — a skip here would read
    as 'the docs match' when in fact nothing was compared."""
    proc = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"HEAD:{path_in_repo}"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"git show HEAD:{path_in_repo} failed (rc={proc.returncode}): "
            f"{proc.stderr.strip()!r} — this net cannot certify tiers against an "
            "unreadable HEAD"
        )
    return proc.stdout


def head_roster() -> list[str]:
    """Agent population DERIVED from the tree at HEAD (never a literal 26)."""
    proc = subprocess.run(
        ["git", "-C", str(ROOT), "ls-tree", "HEAD", "--name-only", ".claude/agents/"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"git ls-tree HEAD .claude/agents/ failed (rc={proc.returncode}): "
            f"{proc.stderr.strip()!r}"
        )
    names = [Path(line).stem for line in proc.stdout.split() if line.endswith(".md")]
    return sorted(names)


def head_frontmatter(agent: str) -> tuple[str | None, str | None]:
    """(model, effort) as committed; either may be None (e.g. communicator)."""
    text = git_show_head(f".claude/agents/{agent}.md")
    m = re.search(r"^model:\s*(\S+)", text, re.MULTILINE)
    e = re.search(r"^effort:\s*(\S+)", text, re.MULTILINE)
    return (m.group(1) if m else None, e.group(1) if e else None)


# ---------------------------------------------------------------------------
# tier tokens — model matched on a TOKEN, never a substring (L-00000143)
# ---------------------------------------------------------------------------
def tier_token(value: str) -> str:
    """The single tier name inside a model field, so `opus` == `claude-opus-4-8`.
    An unresolvable value (e.g. `session`) returns a marker that equals nothing,
    so it never spuriously matches in a comparison."""
    tokens = set(re.split(r"[-_.]", value.strip()))
    hits = [name for name in CLAUDE_MODEL_RANK if name in tokens]
    return hits[0] if len(hits) == 1 else f"?unresolved:{value.strip()}?"


def tier_disagrees(head_model: str, surface_model: str) -> bool:
    return tier_token(head_model) != tier_token(surface_model)


# ---------------------------------------------------------------------------
# surface parsers — each takes raw text so it can be replayed on synthetic input
# ---------------------------------------------------------------------------
_HEADER_RE = re.compile(r"^\|\s*Agent\s*\|\s*Model\s*\|\s*Effort\s*\|\s*Role\s*\|")
_SEP_RE = re.compile(r"^\|\s*-+\s*\|")
_BACKTICK_NAME = re.compile(r"`([a-z][a-z0-9-]*)`")


def parse_readme_table(text: str) -> dict[str, tuple[str, str]]:
    """Rows of a `| Agent | Model | Effort | Role |` table -> {agent: (model,
    effort)}. A grouped agent cell (`sca-npm` / `sca-java` / `sca-mobile` in the
    README-CLAUDE mirror) is EXPLODED, each name sharing the row's tier."""
    result: dict[str, tuple[str, str]] = {}
    in_table = False
    for line in text.splitlines():
        if _HEADER_RE.match(line):
            in_table = True
            continue
        if not in_table:
            continue
        if not line.startswith("|"):
            break  # first line past the table ends it
        if _SEP_RE.match(line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        agent_cell, model, effort = cells[0], cells[1], cells[2]
        for name in _BACKTICK_NAME.findall(agent_cell):
            result[name] = (model, effort)
    return result


_BUDGET_ROW = re.compile(r"^\|\s*([a-z][a-z0-9-]+)\s*\|\s*(\S+)\s*\|")
_BUDGET_HEADER_RE = re.compile(r"^\|\s*agent\s*\|\s*tier\s*\|", re.IGNORECASE)


def parse_budget(text: str) -> dict[str, str]:
    """The `tier` column of TOKEN_BUDGETS.md -> {agent: tier}. No effort column.

    BOUNDED TO ITS SECTION, same shape as `parse_readme_table`: the `| agent |
    tier |` header opens it and the first line that is not a table row closes it.
    It used to sweep the whole file, so any `| name | token |` pipe line written
    under the prose — a future table, an example — overwrote an agent's tier
    with no error and no warning, and this net would have certified the result
    (T-00000415). The header is CONSUMED as the opening rather than filtered out
    by its literal name afterwards."""
    result: dict[str, str] = {}
    in_table = False
    for line in text.splitlines():
        if not in_table:
            if _BUDGET_HEADER_RE.match(line):
                in_table = True
            continue
        if not line.startswith("|"):
            break  # first line past the table ends it
        if _SEP_RE.match(line):
            continue
        m = _BUDGET_ROW.match(line)
        if not m:
            continue
        result[m.group(1)] = m.group(2)
    return result


_USAGE_ROW = re.compile(
    r"<tr><td><code>([a-z][a-z0-9-]*)</code></td><td>(.*?)</td>"
)
_USAGE_PILL = re.compile(r'<span class="pill [^"]*">([^<]+)</span>')
_USAGE_EFFORT = re.compile(rf"{MIDDOT}\s*([A-Za-z]+)")


def _usage_roster_slice(html: str) -> str:
    """The single roster table (`<th>Agent</th>` .. `</table>`), so a `<code>`
    inside a role cell or an unrelated table cannot inject a phantom agent."""
    start = html.find("<th>Agent</th>")
    if start == -1:
        return ""
    end = html.find("</table>", start)
    return html[start:end if end != -1 else None]


def parse_usage(html: str) -> dict[str, tuple[str | None, object]]:
    """usage.html roster -> {agent: (model|None, effort|ABSENT)}. A `—` cell
    (communicator) yields (None, ABSENT); a pill without `· effort` yields
    (model, ABSENT)."""
    result: dict[str, tuple[str | None, object]] = {}
    for m in _USAGE_ROW.finditer(_usage_roster_slice(html)):
        agent, cell = m.group(1), m.group(2)
        pill = _USAGE_PILL.search(cell)
        model = pill.group(1).strip() if pill else None
        eff = _USAGE_EFFORT.search(cell)
        effort = eff.group(1).strip() if eff else ABSENT
        result[agent] = (model, effort)
    return result


# ---------------------------------------------------------------------------
# surfaces, loaded FROM A ROOT — the comparison is replayable on a copy
# ---------------------------------------------------------------------------
# Labels are the ones that appear in mismatch messages; the values are the real
# relative paths, so a temporary copy keeps the same shape as the repository.
# `docs/usage.html` EST SORTI DE CE FILET LE 2026-09-09, PAR DÉCISION DU PILOTE.
# NE PAS LE REMETTRE « PAR SYMÉTRIE ».
#
# La raison : c'est une page de PRÉSENTATION destinée aux projets adoptants, pas
# une surface de configuration. La faire épingler par la porte revenait à rougir
# la CI sur un tableau de doc — de la friction sans bénéfice, et une incitation à
# figer la page plutôt qu'à la retravailler.
#
# CE QUE ÇA COÛTE, ET C'EST DIT : le tableau des agents d'`usage.html` peut
# désormais PÉRIMER EN SILENCE. Aucun mécanisme ne le compare plus aux
# frontmatter. C'est un arbitrage assumé, pas un oubli — la vérité des tiers
# reste tenue par les trois surfaces ci-dessous, qui sont, elles, des surfaces de
# configuration.
SURFACE_FILES: dict[str, str] = {
    **({} if _SANS_README else {"README.md": "README.md"}),
    "README-CLAUDE.md": "README-CLAUDE.md",
    "TOKEN_BUDGETS.md": ".agents/ref/TOKEN_BUDGETS.md",
}


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def load_surfaces(root: Path) -> dict[str, dict]:
    """The four surfaces under `root` -> {label: {agent: (model|None,
    effort|ABSENT)}}. Taking a ROOT rather than reading ROOT directly is what
    makes the whole comparison replayable on a temporary tree — the four parsers
    and the mismatch loop then have a witness, instead of one parser out of four
    (T-00000415)."""
    def text(label: str) -> str:
        return (root / SURFACE_FILES[label]).read_text(encoding="utf-8")

    budget = parse_budget(text("TOKEN_BUDGETS.md"))
    return {
        **{label: dict(parse_readme_table(text(label)))
           for label in ("README.md", "README-CLAUDE.md") if label in SURFACE_FILES},
        "TOKEN_BUDGETS.md": {a: (m, ABSENT) for a, m in budget.items()},
    }


def collect_mismatches(
    roster: list[str],
    head: dict[str, tuple[str | None, str | None]],
    surfaces: dict[str, dict],
) -> list[str]:
    """Every (agent, surface) disagreement with HEAD, as human-readable lines.
    An EMPTY list is the healthy value — that contract is the whole net, so it is
    kept as an equality-to-empty at every call site rather than a truthiness
    check. communicator is NO LONGER excluded: it carries a committed tier since
    2026-09-05 (T-00000471), so it is swept like every other agent."""
    mismatches: list[str] = []
    for agent in roster:
        head_model, head_effort = head[agent]
        for label, data in surfaces.items():
            if agent not in data:
                continue
            s_model, s_effort = data[agent]
            if s_model is not None and head_model is not None and \
                    tier_disagrees(head_model, s_model):
                mismatches.append(
                    f"{agent} [{label}] model: HEAD {head_model!r} "
                    f"({tier_token(head_model)}) vs surface {s_model!r} "
                    f"({tier_token(s_model)})"
                )
            if s_effort is not ABSENT and head_effort is not None and \
                    s_effort != head_effort:
                mismatches.append(
                    f"{agent} [{label}] effort: HEAD {head_effort!r} vs "
                    f"surface {s_effort!r}"
                )
    return mismatches


def roster_gaps(
    roster: list[str], surfaces: dict[str, dict]
) -> dict[str, tuple[list[str], list[str]]]:
    """{label: (committed at HEAD but absent from the surface, named on the
    surface but absent at HEAD)}, both sorted. `([], [])` is the healthy value.
    Checked in BOTH directions: a surface that forgets an agent hides it from
    every reader, and a surface naming an agent HEAD does not carry advertises
    one that does not exist."""
    names = set(roster)
    return {
        label: (sorted(names - set(data)), sorted(set(data) - names))
        for label, data in surfaces.items()
    }


# ---------------------------------------------------------------------------
# mutation helpers — a mutation that does not APPLY is a false witness
# ---------------------------------------------------------------------------
def _locate_line(text: str, marker: str) -> tuple[list[str], int]:
    """(lines, index of the ONE line carrying `marker`). Zero or several matches
    is a hard failure: `dev-multi` alone appears on three lines of README.md and
    four of usage.html, so a loose marker would silently mutate the wrong row."""
    lines = text.splitlines(keepends=True)
    hits = [i for i, line in enumerate(lines) if marker in line]
    if len(hits) != 1:
        raise AssertionError(
            f"marker {marker!r} matched {len(hits)} lines, need exactly 1 — the "
            "mutation would not land where the test claims it does"
        )
    return lines, hits[0]


def _mutate_line(text: str, marker: str, old: str, new: str) -> str:
    """Replace `old` by `new` on the one line carrying `marker`. Refuses a no-op
    and refuses anything but a single occurrence: a mutation that silently fails
    to apply turns a bite-proof into a green that proves nothing, which is the
    exact defect this file exists to close."""
    if new == old:
        raise AssertionError(f"no-op mutation {old!r} -> {new!r} would prove nothing")
    lines, i = _locate_line(text, marker)
    count = lines[i].count(old)
    if count != 1:
        raise AssertionError(
            f"{old!r} occurs {count}x on the {marker!r} line, need exactly 1"
        )
    lines[i] = lines[i].replace(old, new)
    return "".join(lines)


def _drop_line(text: str, marker: str) -> str:
    """Remove the one line carrying `marker` — same uniqueness contract as
    `_mutate_line`, used to prove `roster_gaps` sees a deleted row."""
    lines, i = _locate_line(text, marker)
    del lines[i]
    return "".join(lines)


def _live_texts() -> dict[str, str]:
    """Raw text of the four live surfaces, keyed by label."""
    return {label: _read(rel) for label, rel in SURFACE_FILES.items()}


def _write_surfaces(root: Path, texts: dict[str, str]) -> Path:
    """Write the four surface texts under `root`, at their real relative paths.
    Nothing outside these four files is created — this net travels, so it never
    assumes any state that does not travel with it."""
    for label, text in texts.items():
        dest = root / SURFACE_FILES[label]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
    return root


# ---------------------------------------------------------------------------
# portée du repli immédiat vers critic-fable (T-01M4ND27WWWNV74J49381QMN4Z,
# décision pilote S-01M4N02D2KFYQVV92ZXGSXBG2G)
# ---------------------------------------------------------------------------
# « Repli immédiat vers critic-fable » est vrai contre la panne d'une DÉF, faux
# contre un quota épuisé quand critic-fable tourne sur le modèle de critic-opus :
# les deux tombent ensemble. Chaque site qui écrit ce repli porte donc la clause
# de portée, dans les FENETRE_PORTEE caractères qui le suivent — et seulement
# tant que le frontmatter COMMITÉ À HEAD les met sur le même modèle : le jour où
# ils divergent, la clause devient fausse et le témoin l'INTERDIT.
REPLI_SURFACES = (
    ".claude/commands/kickoff.md",
    ".agents/skills/kickoff/SKILL.md",
    ".claude/agents/orchestrator.md",
    ".kimi-code/agents/orchestrator.md",
    ".gemini/agents/orchestrator.md",
    ".github/agents/orchestrator.agent.md",
    ".codex/agents/orchestrator.toml",
    ".github/copilot-instructions.md",
)
REPLI_IMMEDIAT = re.compile(r"immediate fallback critic-fable|fallback is IMMEDIATE — critic-fable")
CLAUSE_PORTEE = (
    "on Claude Code, critic-fable shares critic-opus's model, so an exhausted Opus quota "
    "takes both down and the fallback that survives is critic-sonnet-max — go straight to it"
)
# AGENTS.md:22 porte DÉJÀ la clause, en français et avec un modèle écrit en dur :
# hors write-set de cette tâche, elle est CONTRÔLÉE ici en lecture seule (réserve C3).
REPLI_FR = re.compile(r"repli immédiat critic-fable")
CLAUSE_FR = re.compile(r"sur Claude Code, critic-fable partage le modèle de critic-opus(?: \(([^)]*)\))?")
FENETRE_PORTEE = 300
# Plancher de population : 15 sites relevés à 3b7a417d (14 par ligne, 15 une
# fois les blancs repliés — orchestrator.toml coupe « immediate⏎fallback »).
PLANCHER_REPLI = 15


def _replie(texte: str) -> str:
    """Backticks retirés, blancs repliés en une espace : un site coupé par une fin
    de ligne compte comme les autres, avec ou sans `code`."""
    return re.sub(r"\s+", " ", texte.replace("`", ""))


def fautes_de_portee(textes: dict[str, str], meme_modele: bool) -> tuple[int, list[str]]:
    """(nombre de sites, fautes) sur des textes {chemin: texte}. Un site PORTE sa
    portée quand la clause canonique tient ENTIÈRE dans la fenêtre qui le suit ;
    il le doit si `meme_modele`, il ne le doit PAS sinon."""
    sites = 0
    fautes: list[str] = []
    for rel, texte in textes.items():
        plat = _replie(texte)
        for rang, m in enumerate(REPLI_IMMEDIAT.finditer(plat), start=1):
            sites += 1
            porte = CLAUSE_PORTEE in plat[m.end(): m.end() + FENETRE_PORTEE]
            if porte != meme_modele:
                cause = ("clause de portée absente" if meme_modele else
                         "clause de portée INTERDITE : critic-fable et critic-opus ne partagent plus de modèle")
                fautes.append(f"{rel} site {rang} « {plat[m.start(): m.end() + 60]}… » : {cause}")
    return sites, fautes


def fautes_agents_md(texte: str, meme_modele: bool, modele_opus: str) -> list[str]:
    """AGENTS.md:22, même règle dans les deux sens ; et le modèle qu'il écrit en dur
    entre parenthèses, s'il en écrit un, est celui de critic-opus à HEAD."""
    plat = _replie(texte)
    m = REPLI_FR.search(plat)
    if m is None:
        return ["AGENTS.md : « repli immédiat critic-fable » introuvable — ce contrôle ne voit plus rien"]
    c = CLAUSE_FR.search(plat, m.end(), m.end() + FENETRE_PORTEE)
    if (c is not None) != meme_modele:
        return [("AGENTS.md : clause « sur Claude Code, critic-fable partage le modèle de "
                 "critic-opus » " + ("absente" if meme_modele else "INTERDITE : les modèles divergent"))]
    if c is not None and c.group(1) and c.group(1) != modele_opus:
        return [f"AGENTS.md : modèle écrit en dur ({c.group(1)}) ≠ critic-opus à HEAD ({modele_opus})"]
    return []


class TierSurfaceTests(unittest.TestCase):
    def setUp(self):
        if not _git_available():
            self.skipTest("git binary absent — cannot read committed frontmatter")
        self.roster = head_roster()
        # Agents de l'adoptant, présents à HEAD hors du roster embarqué (vide dans le kit).
        self.hors_objet: set[str] = set()
        if not EST_LE_KIT:
            # hors du kit : la population HEAD ∩ roster embarqué (un agent de l'adoptant n'est pas jugé,
            # ni absent des surfaces, ni documenté sur elles — mesuré chez un adoptant réel)
            kit = agents_du_kit()
            self.assertLessEqual(kit, set(self.roster), sorted(kit - set(self.roster)))
            self.hors_objet = set(self.roster) - kit
            self.roster = sorted(set(self.roster) & kit)
        self.head = {a: head_frontmatter(a) for a in self.roster}
        # surfaces that carry (model, effort|ABSENT), keyed by label
        self.surfaces = self._surfaces(ROOT)
        self.readme = self.surfaces.get("README.md")
        self.readme_claude = self.surfaces["README-CLAUDE.md"]
        self.budget = {a: m for a, (m, _) in self.surfaces["TOKEN_BUDGETS.md"].items()}

    def _surfaces(self, root: Path) -> dict[str, dict]:
        """`load_surfaces(root)`, sans les lignes des agents de l'adoptant (hors du kit
        seul) ; un nom qu'aucune déf de HEAD ne porte reste vu par `roster_gaps`."""
        return {label: {a: v for a, v in data.items() if a not in self.hors_objet}
                for label, data in load_surfaces(root).items()}

    def _alt(self) -> tuple[str, str, str, str]:
        """(head_model, head_effort, alt_tier, alt_effort) for the dev-multi
        witness — the values every mutation arm below is built from.

        Each is DERIVED from HEAD, never a literal: the day the pilot retunes
        dev-multi, its mutation moves with it instead of pinning `opus`/`xhigh`
        into this file, and an alt that happened to equal HEAD would mutate
        nothing while still reading as a bite-proof."""
        head_model, head_effort = self.head["dev-multi"]
        self.assertIsNotNone(head_model, "dev-multi lost its `model:` at HEAD")
        self.assertIsNotNone(head_effort, "dev-multi lost its `effort:` at HEAD")
        head_tier = tier_token(head_model)
        self.assertIn(head_tier, CLAUDE_MODEL_RANK,
                      f"dev-multi HEAD model {head_model!r} resolves to no known tier")
        alt_tier = next(n for n in CLAUDE_MODEL_RANK if n != head_tier)
        alt_effort = "low" if head_effort != "low" else "high"
        return head_model, head_effort, alt_tier, alt_effort

    def test_docs_match_committed_frontmatter(self):
        """Every surface that names an agent must state the agent's committed
        tier — communicator INCLUDED since T-00000471, it no longer has an
        exemption to hide in."""
        mismatches = collect_mismatches(self.roster, self.head, self.surfaces)
        self.assertEqual(
            mismatches, [],
            "doc surfaces disagree with the committed frontmatter (source of "
            "truth = HEAD, not the disk — L-00000297):\n  "
            + "\n  ".join(mismatches),
        )

    def test_communicator_tier_is_pinned(self):
        """communicator carries a tier at HEAD, and it is a PILOT DECISION taken by
        hand on 2026-09-05 (T-00000471) — not a value any rule of this repo derives.

        WHAT THIS REPLACES, and why the replacement is not weaker. Until then this
        def declared no `model:` and no `effort:`, and that vacuity was pinned
        (S-00000897) because a tier here forecasts one nobody configured and
        DOWNGRADES a session already at opus. The pilot set `haiku`/`medium`
        anyway. The net does not argue with him: it holds the NEW value just as
        tightly, so the next silent drift is caught exactly as the old one was.
        The general sweep now covers communicator too — it lost its exemption, so
        the four surfaces are checked by `test_docs_match_committed_frontmatter`
        like every other agent, and this arm only adds what that sweep cannot say:
        that the value is committed, non-empty, and deliberate.

        The day the pilot restores the vacuity, THIS test is what fails first, and
        its message says where to look."""
        self.assertIn("communicator", self.roster)
        model, effort = self.head["communicator"]
        self.assertEqual(
            (model, effort), ("haiku", "medium"),
            "communicator's committed tier moved. It is a hand-made pilot setting "
            "(T-00000471), not a derived value: if the pilot changed it, update "
            "this arm AND the four surfaces together; if nobody did, a drift just "
            "rewrote the def that translates everything to the pilot",
        )
        self.assertEqual(
            self.budget.get("communicator"), "haiku",
            "TOKEN_BUDGETS.md must carry communicator's committed model tier — a "
            "budget sheet naming a tier nobody runs makes the FORECAST wrong")
        # Le bras `usage.html` de cet arm a été RETIRÉ le 2026-09-09 avec le
        # reste de la page (décision du pilote). Les deux surfaces de
        # configuration qui restent — README.md et README-CLAUDE.md — sont
        # couvertes par le balayage général `test_docs_match_committed_frontmatter`.
        for label in ("README.md", "README-CLAUDE.md"):
            if label not in self.surfaces:
                self.assertTrue(_SANS_README and not readme_du_kit(), label)
                continue
            self.assertEqual(
                self.surfaces[label].get("communicator"), ("haiku", "medium"),
                f"{label} doit porter le tier COMMITÉ de communicator — une "
                "surface qui annonce un tier que la def ne tient pas cache la "
                "configuration réelle à qui la lit (L-00000111)",
            )

    def test_mutated_table_is_caught(self):
        """The net BITES: an opus->sonnet mutation in a table is detected, and the
        un-mutated control is silent — so the green above is not vacuous."""
        table = (
            "| Agent | Model | Effort | Role |\n"
            "|---|---|---|---|\n"
            "| `foo` | opus | high | x |\n"
        )
        parsed = parse_readme_table(table)
        self.assertEqual(parsed["foo"], ("opus", "high"))
        # control: HEAD `claude-opus-4-8` agrees with a surface `opus`
        self.assertFalse(tier_disagrees("claude-opus-4-8", parsed["foo"][0]),
                         "base not green: opus and claude-opus-4-8 must agree by token")
        # mutation: surface now says sonnet where HEAD is opus
        mutated = parse_readme_table(table.replace("opus", "sonnet"))
        self.assertTrue(
            tier_disagrees("claude-opus-4-8", mutated["foo"][0]),
            "the net does not bite: an opus->sonnet table mutation went unnoticed")

    def test_replay_on_temp_tree_bites_per_surface(self):
        """The WHOLE comparison — four parsers AND the mismatch loop — replayed
        on a temporary copy of the four surfaces.

        Before this, a single parser out of four had a witness and the loop had
        none: a stray `continue` in either branch, or a parser returning an empty
        dict, would have stayed green. Here the un-mutated arm must be silent and
        one mutation per surface must produce EXACTLY five named lines — an
        `assertEqual` on the list, never an `assertTrue` on its length, so a
        parser that stopped contributing is visible as a missing line."""
        head_model, head_effort, alt_tier, alt_effort = self._alt()
        head_tier = tier_token(head_model)
        texts = _live_texts()

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            control = _write_surfaces(Path(tmp) / "control", texts)
            self.assertEqual(
                collect_mismatches(self.roster, self.head, self._surfaces(control)), [],
                "control arm: an untouched copy of the four surfaces must be as "
                "silent as the live tree — if it is not, the replay is broken and "
                "the mutated arm below proves nothing")

            # `old` is the value PARSED from the live surface, never a literal.
            claude_effort = self.surfaces["README-CLAUDE.md"]["dev-multi"][1]
            budget_tier = self.surfaces["TOKEN_BUDGETS.md"]["dev-multi"][0]

            muted = dict(texts)
            if not _SANS_README:
                readme_model = self.surfaces["README.md"]["dev-multi"][0]
                muted["README.md"] = _mutate_line(
                    muted["README.md"], "| `dev-multi` |", readme_model, alt_tier)
            muted["README-CLAUDE.md"] = _mutate_line(
                muted["README-CLAUDE.md"], "| `dev-multi` |", claude_effort, alt_effort)
            muted["TOKEN_BUDGETS.md"] = _mutate_line(
                muted["TOKEN_BUDGETS.md"], "| dev-multi ", budget_tier, alt_tier)

            mutated = _write_surfaces(Path(tmp) / "mutated", muted)
            found = collect_mismatches(self.roster, self.head, self._surfaces(mutated))

        model_line = (
            f"dev-multi [{{label}}] model: HEAD {head_model!r} ({head_tier}) vs "
            f"surface {alt_tier!r} ({alt_tier})"
        )
        effort_line = (
            f"dev-multi [{{label}}] effort: HEAD {head_effort!r} vs "
            f"surface {alt_effort!r}"
        )
        expected = ([] if _SANS_README else [model_line.format(label="README.md")]) + [
            effort_line.format(label="README-CLAUDE.md"),
            model_line.format(label="TOKEN_BUDGETS.md"),
        ]
        self.assertEqual(
            found, expected,
            "one mutation per surface must yield exactly these three lines, in "
            "surface order, model before effort — a short list means a parser or "
            "a branch of the loop is not exercised by this net")

    def test_every_head_agent_on_every_surface(self):
        """Every agent committed at HEAD is named on all four surfaces, and no
        surface names an agent HEAD does not carry.

        All four surfaces in ONE assertion, so the report is the full list of
        holes rather than the first one. The population is DERIVED on both sides
        (26/26 today), never a pinned count: add an agent without documenting it,
        or delete one without cleaning the tables, and this reddens."""
        gaps = {label: g
                for label, g in roster_gaps(self.roster, self.surfaces).items()
                if g != ([], [])}
        self.assertEqual(
            gaps, {},
            "surface/HEAD roster disagreement, per surface, as (committed at HEAD "
            f"but undocumented, documented but absent at HEAD): {gaps}")

        # and it BITES: a row removed from a copy is reported as a hole.
        holed = dict(_live_texts())
        # Le témoin TROUÉ était `usage.html` avant son retrait du filet
        # (2026-09-09) ; c'est `README-CLAUDE.md` qui le remplace. `README.md`
        # reste le témoin PROPRE — les deux rôles ne peuvent pas tenir sur la
        # même surface, sinon le trou et le contrôle se contredisent.
        holed["README-CLAUDE.md"] = _drop_line(
            holed["README-CLAUDE.md"], "| `dev-multi` |")
        holed["TOKEN_BUDGETS.md"] = _drop_line(holed["TOKEN_BUDGETS.md"], "| dev-multi ")
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            after = roster_gaps(
                self.roster, self._surfaces(_write_surfaces(Path(tmp), holed)))
        self.assertEqual(
            after["README-CLAUDE.md"], (["dev-multi"], []),
            "roster_gaps ne mord pas : une ligne retirée de README-CLAUDE.md est "
            "passée inaperçue")
        self.assertEqual(
            after["TOKEN_BUDGETS.md"], (["dev-multi"], []),
            "roster_gaps does not bite: a row removed from TOKEN_BUDGETS went unseen")
        if _SANS_README:
            # hors du kit sans le README du kit : aucune surface propre ne reste à témoin
            self.assertNotIn("README.md", after)
            return
        self.assertEqual(
            after["README.md"], ([], []),
            "the untouched surfaces must stay clean in the holed arm — otherwise "
            "the two holes above are not attributable to the removals")

    def test_budget_parse_is_bounded_to_tier_table(self):
        """`parse_budget` reads the tier table ONLY. It used to sweep the whole
        file, so any `| name | token |` line added under the prose silently
        overwrote a tier — a doc could contradict HEAD and this net would have
        reported the contradiction as agreement."""
        _, _, alt_tier, _ = self._alt()
        live = _read(SURFACE_FILES["TOKEN_BUDGETS.md"])
        parsed = parse_budget(live)
        # non-vacuity FIRST: two empty dicts compare equal, so the equality below
        # would be satisfied by a parser that reads nothing at all.
        for w in WITNESSES:
            self.assertIn(w, parsed,
                          f"witness {w!r} absent from the parsed tier table — the "
                          "bounded parse found nothing, its green would say nothing")
        strayed = live + (
            "\n## stray\n"
            f"| dev-multi | {alt_tier} | 0k | flat |\n"
            "| foo | bar |\n"
        )
        self.assertEqual(
            parse_budget(strayed), parsed,
            "a pipe table added BELOW the tier table changed the parse — "
            "parse_budget is not bounded to its section, so a stray row can "
            "overwrite an agent's tier in silence")
        self.assertNotIn(
            "foo", parse_budget(strayed),
            "a name from outside the tier table entered the parse")
        self.assertNotIn(
            "agent", parsed,
            "the `| agent | tier |` header leaked in as a row — it must be "
            "consumed as the table's opening, not filtered by name afterwards")

    def test_population_derived_from_head_and_witnesses_present(self):
        """The roster is derived from HEAD, not a literal, and each surface is
        non-vacuous — the three witnesses appear on all four."""
        self.assertGreater(
            len(self.roster), 20,
            "roster looks empty — the population must be derived from "
            "`git ls-tree HEAD .claude/agents/`, not asserted")
        for w in WITNESSES:
            self.assertIn(w, self.roster, f"witness {w!r} missing from HEAD roster")
        for label, data in self.surfaces.items():
            for w in WITNESSES:
                self.assertIn(
                    w, data,
                    f"witness {w!r} absent from {label} — the parse found an "
                    "empty or malformed surface, its green would say nothing")

    def test_repli_immediat_critic_fable_porte_sa_portee(self):
        """T-01M4ND27WWWNV74J49381QMN4Z. Chaque « repli immédiat vers critic-fable »
        des huit surfaces porte la clause de portée si critic-fable et critic-opus
        partagent leur `model:` À HEAD, et ne la porte pas sinon ; AGENTS.md:22
        suit la même règle. Rouge à la base (15/15 sites sans clause), rouge si une
        clause tombe, rouge si un modèle bascule, rouge si la population fond."""
        fable, _ = head_frontmatter("critic-fable")
        opus, _ = head_frontmatter("critic-opus")
        self.assertIsNotNone(fable, "critic-fable lost its `model:` at HEAD")
        self.assertIsNotNone(opus, "critic-opus lost its `model:` at HEAD")
        meme = fable == opus
        sites, fautes = fautes_de_portee({rel: _read(rel) for rel in REPLI_SURFACES}, meme)
        fautes += fautes_agents_md(_read("AGENTS.md"), meme, opus)
        self.assertGreaterEqual(
            sites, PLANCHER_REPLI,
            f"{sites} sites « repli immédiat critic-fable » relevés, plancher {PLANCHER_REPLI} — "
            "une surface a perdu le motif, ce vert ne couvrirait plus rien")
        self.assertEqual(
            fautes, [],
            f"critic-fable={fable!r}, critic-opus={opus!r} à HEAD — la portée du repli ment :\n  "
            + "\n  ".join(fautes))

    def test_portee_du_repli_mord_dans_les_deux_sens(self):
        """Preuve de morsure du témoin ci-dessus, indépendante de HEAD : sur des
        textes synthétiques, la clause est exigée sous un même modèle et interdite
        sous deux modèles ; un site coupé par une fin de ligne compte ; une clause
        hors fenêtre ne compte pas ; un modèle écrit en dur périmé est vu."""
        porteur = "the fallback is IMMEDIATE — `critic-fable`, then\n`critic-sonnet-max` (" + CLAUSE_PORTEE + ")"
        nu = "immediate\n    fallback critic-fable, then critic-sonnet-max; angles A and B"
        loin = "immediate fallback critic-fable, " + "x" * FENETRE_PORTEE + CLAUSE_PORTEE
        self.assertEqual(fautes_de_portee({"s": porteur}, True), (1, []))
        self.assertEqual(len(fautes_de_portee({"s": porteur}, False)[1]), 1)
        self.assertEqual(fautes_de_portee({"s": nu}, False), (1, []))
        self.assertEqual(len(fautes_de_portee({"s": nu}, True)[1]), 1)
        self.assertEqual(len(fautes_de_portee({"s": loin}, True)[1]), 1)
        fr = ("repli immédiat `critic-fable` puis `critic-sonnet-max` ; sur Claude Code, "
              "`critic-fable` partage le modèle de `critic-opus` ({}) : un quota épuisé")
        self.assertEqual(fautes_agents_md(fr.format("m-1"), True, "m-1"), [])
        self.assertEqual(len(fautes_agents_md(fr.format("m-0"), True, "m-1")), 1)
        self.assertEqual(len(fautes_agents_md(fr.format("m-1"), False, "m-1")), 1)
        self.assertEqual(len(fautes_agents_md("repli immédiat `critic-fable` seul", True, "m-1")), 1)


if __name__ == "__main__":
    unittest.main()
