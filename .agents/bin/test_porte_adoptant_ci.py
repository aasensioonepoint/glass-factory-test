"""The CI wiring of the ADOPTANT gate is a signal whose producer is witnessed.

T-00001183 (pilot decision S-00004119: « c'est le build du projet et sous
modules qui doivent faire foi »). `.github/workflows/ci.yml` carries three jobs:
`porte` decides the mode and EXPORTS it, `tests` (the kit's suite) runs unless
that export says `adoptant`, `adoptant` runs the project's gate only then. Every
link of that chain is read here, by a bounded stdlib scanner, because each one
fails SILENTLY when it breaks:

  * `jobs.porte.outputs.porte` must be `${{ steps.<id>.outputs.porte }}` with
    `<id>` the `id:` of the ONE step that writes `porte=` into "$GITHUB_OUTPUT".
    Rename one side, drop `outputs:`, or `echo` to stdout, and the output is
    EMPTY: `tests` then runs (fail-closed) but `adoptant` NEVER does — an
    adopting project would be gated by nothing (a mechanism whose return channel
    is discarded does not exist, L-00000136);
  * `tests.needs == [porte]` and `adoptant.needs == [porte]`, and their two
    `if:` byte for byte — `tests` added to `adoptant`'s needs would skip the
    adoptant gate exactly where `tests` is skipped, i.e. always where it matters;
  * no `continue-on-error` under `porte` nor `adoptant`;
  * the FIRST `python-version:` and the FIRST `apt-get install -y` of the file
    are the `tests` job's: `core-scripts/verify.sh` derives its docker image and
    its apt list from them;
  * the `run:` of `porte` is EXECUTED on three throwaway trees — kit, adoptant,
    no marker at all — script on STDIN, `GITHUB_OUTPUT` a FILE, the runner's
    `GITHUB_*` purged; then on six git histories under `pull_request`
    (binôme c4f3, opus F2): a PR that takes an ADOPTANT base out of adoptant
    mode, by the marker or by the discovery, is RED, named, with NO `porte=`
    written; so is a PR whose base (HEAD^1) cannot be read;
  * `porte` checks out with `fetch-depth: 2` (it reads HEAD^1), `adoptant` with
    `fetch-depth: 0` (semgrep's baseline is a merge-base), and `adoptant` runs
    `corepack enable` before the gate (pnpm, yarn);
  * the `outils` step executes on adopting trees: only root version declarations
    select Java or Node. Pinned setup actions read those output filenames after
    corepack and before the gate; absent declarations leave the runner image;
  * `adoptant` passes semgrep's base to the gate through `env:` ONLY
    (`CADRE_SEMGREP_BASE`, binôme c4f3 bis, S-00004276), and its expression is
    EVALUATED here on three events: a `push` gives `github.event.before` (every
    pushed commit judged), a branch creation its 0000…0 (the gate falls back,
    said), a `pull_request` the PR's base — never `before`, the previous head.
    No `${{ }}` in any `run:` of the job;
  * before the gate, a step points `origin/HEAD` at the default branch, its name
    by `env:` (fable F3) — and that step is EXECUTED on a throwaway repository
    for a default branch `trunk`.

THIS SUITE TRAVELS, SO IT SKIPS — IT IS NEVER STRIPPED. In an adopting project the
`ci.yml` is the project's to rewrite, and the kit-only arms SKIP, announced. The
skip keys on the kit's MARKER (`.agents/IS_THE_KIT`, which does not travel), never
on the pyproject's name: an adopting project received `name = "cadre-kit"` once
(measured on ec-crm-multi), and a skip keyed on that name would run kit-only arms
there and fail them. The arm that proves it is the one arm WITHOUT a skip, at the
end of this file. The POSITIVE assertion of the marker (the kit HAS it, and `porte`
answers `kit` on the real tree) lives in `.agents/evals/test_forge_ruleset_model.py`,
which is `strip:` — a suite that travels cannot assert a file that does not.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CI = ROOT / ".github" / "workflows" / "ci.yml"
# adopting-tree: le marqueur d'identité du kit ne voyage pas (strip: .agents/IS_THE_KIT) ;
# son absence EST le signal « arbre adoptant ». Jamais le nom du pyproject (T-00001183).
EST_LE_KIT = (ROOT / ".agents" / "IS_THE_KIT").is_file()
SAUT = (
    "SAUT ANNONCE : arbre adoptant (marqueur .agents/IS_THE_KIT absent) — ce bras lit le "
    "câblage du ci.yml DU KIT ; un projet adoptant réécrit le sien"
)
# Set in the nested pytest run of the last arm, so that run does not recurse.
IMBRIQUE = "CADRE_TEMOIN_PORTE_CI_IMBRIQUE"

IF_TESTS = "${{ !cancelled() && needs.porte.outputs.porte != 'adoptant' }}"
IF_ADOPTANT = "${{ needs.porte.outputs.porte == 'adoptant' }}"
JOBS = ("porte", "tests", "adoptant")

_JOB_RE = re.compile(r"^  ([A-Za-z_][A-Za-z0-9_-]*):\s*$")
_STEP_KEY_RE = r"^      (?:- |  )"
_ECRIT_PORTE_RE = re.compile(r"""porte=.*>>\s*"?\$GITHUB_OUTPUT"?""")


# ---------------------------------------------------------------------------
# THE READER — bounded line scanning over the TEXT (so the mutants below run
# through the very same code). A shape it does not know yields a DEFECT, never
# an empty "nothing to report".
# ---------------------------------------------------------------------------


def _lignes(texte: str) -> list[str]:
    """Full-line comments blanked FIRST: ci.yml spells out in prose what it avoids."""
    return ["" if re.match(r"^\s*#", l) else l for l in texte.splitlines()]


def _blocs(texte: str) -> dict[str, tuple[int, list[str]]]:
    """`{job id: (index of its first line, its lines)}`."""
    lignes = _lignes(texte)
    try:
        debut = next(i for i, l in enumerate(lignes) if l.rstrip() == "jobs:")
    except StopIteration:
        return {}
    blocs: dict[str, tuple[int, list[str]]] = {}
    courant = None
    for i in range(debut + 1, len(lignes)):
        l = lignes[i]
        if l and not l.startswith(" ") and l.rstrip().endswith(":"):
            break
        m = _JOB_RE.match(l)
        if m:
            courant = m.group(1)
            blocs[courant] = (i, [])
            continue
        if courant is not None:
            blocs[courant][1].append(l)
    return blocs


def _cle(bloc: list[str], cle: str) -> str | None:
    for l in bloc:
        m = re.match(rf"^    {cle}:\s*(.*?)\s*$", l)
        if m:
            return m.group(1)
    return None


def _needs(bloc: list[str]) -> list[str]:
    for i, l in enumerate(bloc):
        m = re.match(r"^    needs:\s*(.*?)\s*$", l)
        if not m:
            continue
        v = m.group(1)
        if v.startswith("["):
            return [x.strip().strip("'\"") for x in v.strip("[]").split(",") if x.strip()]
        if v:
            return [v.strip("'\"")]
        out = []
        for l2 in bloc[i + 1:]:
            m2 = re.match(r"^      -\s*(\S+)\s*$", l2)
            if not m2:
                break
            out.append(m2.group(1).strip("'\""))
        return out
    return []


def _outputs(bloc: list[str], cle: str = "outputs", retrait: int = 4) -> dict[str, str]:
    """The mapping `cle:` at `retrait` spaces — a job's `outputs:` by default, a
    job's `env:` (4), a step's `env:` (8)."""
    out: dict[str, str] = {}
    dedans = False
    for l in bloc:
        if re.match(rf"^ {{{retrait}}}{cle}:\s*$", l):
            dedans = True
            continue
        if dedans:
            m = re.match(rf"^ {{{retrait + 2}}}([A-Za-z0-9_-]+):\s*(.+?)\s*$", l)
            if m:
                out[m.group(1)] = m.group(2)
                continue
            if l.strip():
                break
    return out


def _steps(bloc: list[str]) -> list[list[str]]:
    steps: list[list[str]] = []
    courant = None
    dedans = False
    for l in bloc:
        if re.match(r"^    steps:\s*$", l):
            dedans = True
            continue
        if not dedans:
            continue
        if l.strip() and len(l) - len(l.lstrip()) <= 4:
            break
        if l.startswith("      - "):
            courant = [l]
            steps.append(courant)
        elif courant is not None:
            courant.append(l)
    return steps


def _id(step: list[str]) -> str | None:
    for l in step:
        m = re.match(_STEP_KEY_RE + r"id:\s*(\S+)\s*$", l)
        if m:
            return m.group(1)
    return None


def _run(step: list[str]) -> str | None:
    for i, l in enumerate(step):
        m = re.match(_STEP_KEY_RE + r"run:\s*(.*?)\s*$", l)
        if not m:
            continue
        v = m.group(1)
        if v not in ("|", "|-", "|+", ">", ">-", ">+"):
            return v + "\n"
        corps = [x for x in step[i + 1:]]
        while corps and not corps[-1].strip():
            corps.pop()
        if not corps:
            return ""
        coupe = min(len(x) - len(x.lstrip()) for x in corps if x.strip())
        return "\n".join(x[coupe:] for x in corps) + "\n"
    return None


def evaluer(expression: str | None, contexte: dict[str, str]) -> str | None:
    """The `${{ a || b || … }}` form only, over dotted context paths: the first
    non-empty operand, as GitHub evaluates `||`. Any other form gives None — a
    DEFECT, never a guess."""
    m = re.fullmatch(r"\$\{\{\s*(.+?)\s*\}\}", expression or "")
    if not m:
        return None
    for operande in m.group(1).split("||"):
        chemin = operande.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", chemin):
            return None
        if contexte.get(chemin):
            return contexte[chemin]
    return ""


# The value `CADRE_SEMGREP_BASE` must take, per event (S-00004276).
_AVANT, _BASE_PR, _NUL = "b" * 40, "a" * 40, "0" * 40
BASES_PAR_EVENEMENT = (
    ("push", {"github.event.before": _AVANT}, _AVANT),
    ("push creating a branch", {"github.event.before": _NUL}, _NUL),
    ("pull_request (synchronize)", {"github.event.pull_request.base.sha": _BASE_PR,
                                    "github.event.before": "c" * 40}, _BASE_PR),
)
# The step that points origin/HEAD at the default branch (binôme c4f3 bis, fable F3),
# before the gate, the branch name by `env:` — evaluated for a default branch `trunk`.
SYMREF = "git symbolic-ref refs/remotes/origin/HEAD"
DEFAUT_CONTEXTE = {"github.event.repository.default_branch": "trunk"}
BLOC_SYMREF = ("      - name: Point origin/HEAD at the default branch\n"
               "        env:\n"
               "          DEFAUT: ${{ github.event.repository.default_branch }}\n"
               "        run: |\n"
               "          git symbolic-ref refs/remotes/origin/HEAD \"refs/remotes/origin/$DEFAUT\"\n\n")
JAVA_ACTION = "actions/setup-java@b843ebf9b913146b38da2eaa7aeddf76074ae1ad"
NODE_ACTION = "actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1"
JAVA_IF = "${{ steps.outils.outputs.java_file != '' }}"
NODE_IF = "${{ steps.outils.outputs.node_file != '' }}"


def _step_value(step: list[str], key: str) -> str | None:
    for line in step:
        match = re.match(rf"^      (?:- |  ){re.escape(key)}:\s*(.*?)\s*$", line)
        if match:
            return match.group(1)
    return None


def _outils_step(texte: str) -> list[str] | None:
    steps = _steps(_blocs(texte).get("adoptant", (0, []))[1])
    found = [step for step in steps if _id(step) == "outils"]
    return found[0] if len(found) == 1 else None


def versions_sur(texte: str, arbre: Path, sortie: Path) -> tuple[int, dict[str, str], str]:
    """Execute the real `outils` run on an adopting tree, with output as a file."""
    step = _outils_step(texte)
    if step is None or _run(step) is None:
        return 1, {}, "outils step absent or unreadable"
    sortie.write_text("", encoding="utf-8")
    env = {key: value for key, value in os.environ.items() if not key.startswith("GITHUB_")}
    env["GITHUB_OUTPUT"] = str(sortie)
    proc = subprocess.run(["bash", "-s"], input=_run(step), cwd=arbre, env=env,
                          capture_output=True, text=True, timeout=60, check=False)
    values = dict(line.split("=", 1) for line in sortie.read_text(encoding="utf-8").splitlines()
                  if "=" in line)
    return proc.returncode, values, proc.stdout + proc.stderr


def origin_head_par_le_step(texte: str, depot: Path) -> str:
    """EXECUTE the adoptant step that sets origin/HEAD on a throwaway repository,
    with DEFAUT evaluated from its `env:` for a default branch `trunk`, the way
    the runner does (script on STDIN). The symref's target, or ""."""
    blocs = _blocs(texte)
    pas = [s for s in _steps(blocs.get("adoptant", (0, []))[1]) if SYMREF in (_run(s) or "")]
    if len(pas) != 1:
        return ""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "GITHUB_"))}
    env["DEFAUT"] = evaluer(_outputs(pas[0], "env", 8).get("DEFAUT"), DEFAUT_CONTEXTE) or ""
    depot.mkdir(parents=True)
    subprocess.run(["git", *_ID_GIT, "init", "-q", str(depot)], env=env, check=True,
                   capture_output=True, timeout=60)
    subprocess.run(["bash", "-s"], input=_run(pas[0]), cwd=str(depot), env=env,
                   capture_output=True, text=True, timeout=60)
    p = subprocess.run(["git", "-C", str(depot), "symbolic-ref", "-q", "refs/remotes/origin/HEAD"],
                       env=env, capture_output=True, text=True, timeout=60)
    return p.stdout.strip()


def _job_de_la_premiere(texte: str, motif: str) -> str | None:
    """The job holding the FIRST line (comments blanked) that matches `motif`."""
    blocs = _blocs(texte)
    lignes = _lignes(texte)
    for i, l in enumerate(lignes):
        if re.match(motif, l):
            proprio = None
            for job, (debut, _) in blocs.items():
                if debut <= i:
                    proprio = job
            return proprio
    return None


def ecrivain_de_porte(texte: str) -> tuple[list[list[str]], str | None]:
    """The steps of job `porte` that write `porte=` to $GITHUB_OUTPUT, and the
    step id `jobs.porte.outputs.porte` reads (None when absent or unreadable)."""
    blocs = _blocs(texte)
    if "porte" not in blocs:
        return [], None
    bloc = blocs["porte"][1]
    sortie = _outputs(bloc).get("porte", "")
    m = re.fullmatch(r"\$\{\{\s*steps\.([A-Za-z0-9_-]+)\.outputs\.porte\s*\}\}", sortie)
    ecrivains = [s for s in _steps(bloc) if any(_ECRIT_PORTE_RE.search(l) for l in (_run(s) or "").splitlines())]
    return ecrivains, (m.group(1) if m else None)


def defauts_du_cablage(texte: str) -> list[str]:
    """Every broken link of the chain, named. Empty = the wiring holds."""
    d: list[str] = []
    blocs = _blocs(texte)
    for job in JOBS:
        if job not in blocs:
            d.append(f"job `{job}` absent of ci.yml")
    if d:
        return d
    ecrivains, lu = ecrivain_de_porte(texte)
    if lu is None:
        d.append("jobs.porte.outputs.porte is absent or not `${{ steps.<id>.outputs.porte }}`")
    if len(ecrivains) != 1:
        d.append(f"{len(ecrivains)} step(s) of job `porte` write porte= to $GITHUB_OUTPUT (expected exactly 1)")
    elif lu is not None and _id(ecrivains[0]) != lu:
        d.append(f"outputs reads steps.{lu} but the writing step has id {_id(ecrivains[0])!r}")
    for job, condition in (("tests", IF_TESTS), ("adoptant", IF_ADOPTANT)):
        bloc = blocs[job][1]
        if _needs(bloc) != ["porte"]:
            d.append(f"{job}.needs is {_needs(bloc)}, expected ['porte']")
        if _cle(bloc, "if") != condition:
            d.append(f"{job}.if is {_cle(bloc, 'if')!r}, expected {condition!r}")
    for job in ("porte", "adoptant"):
        if any(re.match(r"^\s*continue-on-error:", l) for l in blocs[job][1]):
            d.append(f"job `{job}` carries continue-on-error — its red would not block")
    # `porte` reads the PR's base (HEAD^1), `adoptant` needs the merge-base of semgrep's baseline.
    for job, attendu in (("porte", "2"), ("adoptant", "0")):
        vu = [m.group(1) for m in (re.match(r"^\s*fetch-depth:\s*(\S+)\s*$", l) for l in blocs[job][1]) if m]
        if vu != [attendu]:
            d.append(f"job `{job}` checks out with fetch-depth {vu or 'default (1)'}, expected [{attendu!r}]")
    runs = [_run(s) or "" for s in _steps(blocs["adoptant"][1])]
    i_core = next((i for i, r in enumerate(runs) if re.search(r"(?m)^corepack enable\b", r)), None)
    i_porte = next((i for i, r in enumerate(runs) if "porte_adoptant.py" in r), None)
    if i_core is None or i_porte is None or i_core > i_porte:
        d.append("job `adoptant` does not run `corepack enable` before the gate — pnpm/yarn absent from PATH")
    steps = _steps(blocs["adoptant"][1])
    outils = [(i, step) for i, step in enumerate(steps) if _id(step) == "outils"]
    if len(outils) != 1 or _step_value(outils[0][1], "shell") != "bash" or not _run(outils[0][1]):
        d.append("job `adoptant` needs one bash `outils` step that writes project version filenames")
    else:
        i_outils, step = outils[0]
        script = _run(step) or ""
        if (i_core is None or i_core >= i_outils or i_porte is None or i_outils >= i_porte):
            d.append("job `adoptant`: `outils` must run after corepack and before the gate")
        if not re.search(r"printf 'java_file=%s\\nnode_file=%s\\n'.*>> \"\$GITHUB_OUTPUT\"", script):
            d.append("job `adoptant`: `outils` does not write both filenames to $GITHUB_OUTPUT")
    for label, action, condition, expected in (
        ("setup-java", JAVA_ACTION, JAVA_IF,
         {"distribution": "temurin", "java-version-file": "${{ steps.outils.outputs.java_file }}"}),
        ("setup-node", NODE_ACTION, NODE_IF,
         {"node-version-file": "${{ steps.outils.outputs.node_file }}", "package-manager-cache": "false"}),
    ):
        matches = [(i, step) for i, step in enumerate(steps)
                   if (_step_value(step, "uses") or "").startswith(f"actions/{label}@")]
        if len(matches) != 1:
            d.append(f"job `adoptant` needs exactly one actions/{label} step")
            continue
        index, step = matches[0]
        if (_step_value(step, "uses") or "").split(" #", 1)[0] != action:
            d.append(f"job `adoptant` {label} must use pinned SHA {action}")
        if _step_value(step, "if") != condition:
            d.append(f"job `adoptant` {label} must skip when its version file is absent")
        values = _outputs(step, "with", 8)
        for key, value in expected.items():
            if values.get(key) != value:
                d.append(f"job `adoptant` {label} needs {key}: {value}")
        # M2 : a literal version beside the file WINS over it (setup-java, setup-node)
        literal = next(key[:-len("-file")] for key in expected if key.endswith("-version-file"))
        if literal in values:
            d.append(f"job `adoptant` {label} must not set {literal} beside {literal}-file "
                     "(the literal wins over the project's version file)")
        if len(outils) == 1 and (index <= outils[0][0] or i_porte is None or index >= i_porte):
            d.append(f"job `adoptant` {label} must run after `outils` and before the gate")
    # semgrep's base, BY ENV only (binôme c4f3 bis, S-00004276), evaluated per event.
    expression = _outputs(blocs["adoptant"][1], "env").get("CADRE_SEMGREP_BASE")
    for evenement, contexte, attendu in BASES_PAR_EVENEMENT:
        vu = evaluer(expression, contexte)
        if vu != attendu:
            d.append(f"job `adoptant`: CADRE_SEMGREP_BASE on {evenement} gives {vu!r}, expected "
                     f"{attendu!r} (env: {expression!r})")
    if any("${{" in r for r in runs):
        d.append("job `adoptant` interpolates `${{ }}` inside a run: — values go through env:")
    # fable F3: origin/HEAD pointed at the default branch BEFORE the gate, by env:.
    i_sym = next((i for i, r in enumerate(runs) if SYMREF in r), None)
    if i_sym is None or i_porte is None or i_sym > i_porte:
        d.append("job `adoptant` does not point origin/HEAD at the default branch before the gate — a "
                 "default branch outside main/master falls to a FULL scan when the base is refused")
    elif evaluer(_outputs(_steps(blocs["adoptant"][1])[i_sym], "env", 8).get("DEFAUT"),
                 DEFAUT_CONTEXTE) != "trunk":
        d.append("the origin/HEAD step of job `adoptant` does not take DEFAUT from "
                 "github.event.repository.default_branch through its env:")
    for motif, nom in ((r"^\s*python-version:", "python-version"),
                       (r"^\s*(?:sudo\s+)?apt-get\s+install\s+-y\s", "apt-get install -y")):
        proprio = _job_de_la_premiere(texte, motif)
        if proprio != "tests":
            d.append(f"the FIRST `{nom}` of ci.yml belongs to {proprio!r}, not `tests` — verify.sh would replay it")
    return d


def porte_sur(script: str, arbre: Path, sortie: Path) -> str:
    """Run the `run:` of `porte` in `arbre` the way the runner does: script on
    STDIN, GITHUB_OUTPUT a FILE. The value written for `porte`, or ""."""
    rc, texte, valeur = porte_en_evenement(script, arbre, sortie, None)
    return valeur if rc == 0 else f"<rc {rc}: {texte.strip()[:200]}>"


def porte_en_evenement(script: str, arbre: Path, sortie: Path, evenement: str | None) -> tuple[int, str, str]:
    """`(rc, stdout + stderr, valeur écrite pour porte ou "")`. The runner's own
    `GITHUB_*` never leaks in (this suite runs IN CI, on pull requests too):
    `GITHUB_EVENT_NAME` is the one given, or absent."""
    sortie.write_text("", encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "GITHUB_"))}
    env["GITHUB_OUTPUT"] = sortie.as_posix()
    if evenement is not None:
        env["GITHUB_EVENT_NAME"] = evenement
    proc = subprocess.run(["bash", "-s"], input=script, cwd=str(arbre), env=env,
                          capture_output=True, text=True, timeout=60)
    valeurs = [l.split("=", 1)[1] for l in sortie.read_text(encoding="utf-8").splitlines() if l.startswith("porte=")]
    return proc.returncode, proc.stdout + proc.stderr, (valeurs[-1] if valeurs else "")


SORTIE_DU_MODE = "cette PR fait sortir une base adoptant du mode adoptant ; le job adoptant serait sauté"
BASE_ILLISIBLE = "the base of this pull request (HEAD^1) cannot be read"
_ID_GIT = ("-c", "user.name=banc", "-c", "user.email=banc@banc.invalid", "-c", "init.defaultBranch=main",
           "-c", "commit.gpgsign=false")


def _etat(arbre: Path, marqueur: bool, decouverte: bool) -> None:
    for chemin, present in ((arbre / ".agents" / "IS_THE_KIT", marqueur),
                            (arbre / ".agents" / "security" / "module_discovery.py", decouverte)):
        if present:
            chemin.parent.mkdir(parents=True, exist_ok=True)
            chemin.write_text("x\n", encoding="utf-8")
        elif chemin.exists():
            chemin.unlink()


def arbres_pr(base: Path) -> dict[str, tuple[Path, str | None]]:
    """Pull requests as git histories, base commit then head commit (HEAD^1 = the
    base, as in the merge commit the checkout makes). Value: the mode expected,
    or the RED message expected (None for the mode = red)."""
    cas = {
        "sortie-par-marqueur": ((False, True), (True, True), SORTIE_DU_MODE),
        "sortie-par-decouverte": ((False, True), (False, False), SORTIE_DU_MODE),
        "kit-reste-kit": ((True, True), (True, True), "kit"),
        "adoptant-reste-adoptant": ((False, True), (False, True), "adoptant"),
        "entree-en-adoptant": ((True, True), (False, True), "adoptant"),
        "base-illisible": (None, (True, True), BASE_ILLISIBLE),
    }
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "GITHUB_"))}

    def g(arbre: Path, *args: str) -> None:
        subprocess.run(["git", *_ID_GIT, "-C", str(arbre), *args], env=env, check=True,
                       capture_output=True, timeout=60)

    arbres: dict[str, tuple[Path, str | None]] = {}
    for nom, (avant, apres, attendu) in cas.items():
        a = base / f"pr-{nom}"
        a.mkdir(parents=True)
        g(a, "init", "-q")
        for i, etat in enumerate(e for e in (avant, apres) if e is not None):
            _etat(a, *etat)
            (a / "commit.txt").write_text(f"{i}\n", encoding="utf-8")
            g(a, "add", "-A")
            g(a, "commit", "-q", "-m", f"commit {i}")
        arbres[nom] = (a, attendu)
    return arbres


def trois_arbres(base: Path) -> dict[str, tuple[Path, str]]:
    """kit (marker + discovery), adoptant (discovery only), none (neither) — and
    the mode each one must get. No marker AND no discovery is the KIT's path:
    the frozen fixtures of verify.test.sh / pre-push.test.sh carry neither."""
    arbres = {}
    for nom, marqueur, decouverte, attendu in (("kit", True, True, "kit"),
                                               ("adoptant", False, True, "adoptant"),
                                               ("aucun", False, False, "kit")):
        a = base / nom
        (a / ".agents" / "security").mkdir(parents=True, exist_ok=True)
        if marqueur:
            (a / ".agents" / "IS_THE_KIT").write_text("x\n", encoding="utf-8")
        if decouverte:
            (a / ".agents" / "security" / "module_discovery.py").write_text("# stand-in\n", encoding="utf-8")
        arbres[nom] = (a, attendu)
    return arbres


def defauts(texte: str, base: Path) -> list[str]:
    """Structure, then EXECUTION of the writing step on the three trees."""
    d = defauts_du_cablage(texte)
    ecrivains, _ = ecrivain_de_porte(texte)
    if len(ecrivains) != 1:
        return d or ["no single writing step to execute"]
    script = _run(ecrivains[0]) or ""
    for nom, (arbre, attendu) in trois_arbres(base).items():
        rendu = porte_sur(script, arbre, base / f"output-{nom}")
        if rendu != attendu:
            d.append(f"the run of porte on the {nom} tree gives {rendu!r}, expected {attendu!r}")
    cible = origin_head_par_le_step(texte, base / "symref")
    if cible != "refs/remotes/origin/trunk":
        d.append(f"the origin/HEAD step of job `adoptant`, executed for a default branch `trunk`, "
                 f"points origin/HEAD at {cible!r}")
    # binôme c4f3 (opus F2): on `pull_request`, a PR that takes an ADOPTANT base
    # out of adoptant mode is RED, named, and writes NO `porte=`.
    for nom, (arbre, attendu) in arbres_pr(base).items():
        rc, texte, rendu = porte_en_evenement(script, arbre, base / f"output-pr-{nom}", "pull_request")
        if attendu in ("kit", "adoptant"):
            if (rc, rendu) != (0, attendu):
                d.append(f"the run of porte on PR {nom} gives rc {rc}, porte={rendu!r}, expected {attendu!r}")
        elif rc == 0 or rendu or attendu not in texte:
            d.append(f"the run of porte on PR {nom} gives rc {rc}, porte={rendu!r} — expected RED, no output, "
                     f"and {attendu!r}")
    return d


def _adoptant_avant_tests(t: str) -> str:
    lignes = t.splitlines(keepends=True)
    a = lignes.index("  adoptant:\n")
    ti = lignes.index("  tests:\n")
    return "".join(lignes[:ti] + lignes[a:] + lignes[ti:a])


# Each one breaks ONE link; each must be named by `defauts`. The text edits are
# exact: a mutation that changes nothing is itself a failure (non-vacuity).
MUTANTS = (
    ("outputs: removed", lambda t: t.replace("    outputs:\n      porte: ${{ steps.porte.outputs.porte }}\n", "")),
    ("id renamed on the step side", lambda t: t.replace("      - id: porte\n", "      - id: gate\n")),
    ("id renamed on the outputs side", lambda t: t.replace("${{ steps.porte.outputs.porte }}", "${{ steps.gate.outputs.porte }}")),
    ("written to stdout, not $GITHUB_OUTPUT", lambda t: t.replace('echo "porte=$porte" >> "$GITHUB_OUTPUT"', 'echo "porte=$porte"')),
    ("tests added to adoptant's needs", lambda t: t.replace("  adoptant:\n    needs: porte\n", "  adoptant:\n    needs: [porte, tests]\n")),
    ("tests.if == 'kit'", lambda t: t.replace(IF_TESTS, "${{ needs.porte.outputs.porte == 'kit' }}")),
    ("!cancelled() dropped from tests.if", lambda t: t.replace(IF_TESTS, "${{ needs.porte.outputs.porte != 'adoptant' }}")),
    ("continue-on-error on adoptant", lambda t: t.replace("  adoptant:\n    needs: porte\n", "  adoptant:\n    continue-on-error: true\n    needs: porte\n")),
    ("operand IS_THE_KIT dropped", lambda t: t.replace("if [ ! -f .agents/IS_THE_KIT ] && [ -f .agents/security/module_discovery.py ]; then", "if [ -f .agents/security/module_discovery.py ]; then")),
    ("operand module_discovery dropped", lambda t: t.replace("if [ ! -f .agents/IS_THE_KIT ] && [ -f .agents/security/module_discovery.py ]; then", "if [ ! -f .agents/IS_THE_KIT ]; then")),
    ("adoptant placed before tests", _adoptant_avant_tests),
    ("PR exit check removed", lambda t: t.replace(
        'if [ "${GITHUB_EVENT_NAME:-}" = "pull_request" ] && [ "$porte" = "kit" ]; then', "if false; then")),
    ("PR base read on HEAD, not HEAD^1", lambda t: t.replace(
        "git cat-file -e 'HEAD^1:.agents/security/module_discovery.py'",
        "git cat-file -e 'HEAD:.agents/security/module_discovery.py'")),
    ("unreadable PR base passes", lambda t: t.replace(
        "cannot be read (fetch-depth: 2 expected)\"\n              exit 1\n",
        "cannot be read (fetch-depth: 2 expected)\"\n")),
    ("PR exit writes porte= first", lambda t: t.replace(
        '          if [ "${GITHUB_EVENT_NAME:-}" = "pull_request" ]',
        '          echo "porte=$porte" >> "$GITHUB_OUTPUT"\n'
        '          if [ "${GITHUB_EVENT_NAME:-}" = "pull_request" ]')),
    ("fetch-depth: 2 removed from porte", lambda t: t.replace(
        "          persist-credentials: false\n          fetch-depth: 2\n", "          persist-credentials: false\n")),
    ("fetch-depth: 0 removed from adoptant", lambda t: t.replace(
        "          submodules: recursive\n          fetch-depth: 0\n", "          submodules: recursive\n")),
    ("corepack enable removed", lambda t: t.replace(
        '          corepack enable --install-directory "$RUNNER_TEMP/corepack"\n', "")),
    ("semgrep base removed from adoptant's env", lambda t: t.replace(
        "      CADRE_SEMGREP_BASE: ${{ github.event.pull_request.base.sha || github.event.before }}\n", "")),
    ("push base dropped: PR base only (HEAD^1 judged on a push)", lambda t: t.replace(
        "${{ github.event.pull_request.base.sha || github.event.before }}",
        "${{ github.event.pull_request.base.sha }}")),
    ("before read first: a PR judged from its previous head", lambda t: t.replace(
        "${{ github.event.pull_request.base.sha || github.event.before }}",
        "${{ github.event.before || github.event.pull_request.base.sha }}")),
    ("origin/HEAD step removed", lambda t: t.replace(BLOC_SYMREF, "")),
    ("origin/HEAD step placed after the gate", lambda t: t.replace(BLOC_SYMREF, "").replace(
        "        run: python .agents/bin/porte_adoptant.py\n",
        "        run: python .agents/bin/porte_adoptant.py\n\n" + BLOC_SYMREF.rstrip("\n") + "\n")),
    ("default branch hardcoded to main", lambda t: t.replace(
        '"refs/remotes/origin/$DEFAUT"', '"refs/remotes/origin/main"')),
    ("default branch interpolated into the run:", lambda t: t.replace(
        '"refs/remotes/origin/$DEFAUT"', '"refs/remotes/origin/${{ github.event.repository.default_branch }}"')),
    ("DEFAUT read from the wrong context", lambda t: t.replace(
        "          DEFAUT: ${{ github.event.repository.default_branch }}\n",
        "          DEFAUT: ${{ github.base_ref }}\n")),
    ("semgrep base interpolated into the gate's run:", lambda t: t.replace(
        "        run: python .agents/bin/porte_adoptant.py\n",
        '        run: CADRE_SEMGREP_BASE="${{ github.event.pull_request.base.sha || github.event.before }}" '
        "python .agents/bin/porte_adoptant.py\n")),
)


class CablageCiTests(unittest.TestCase):
    """Kit-only arms: they read the KIT's ci.yml."""

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    @unittest.skipUnless(EST_LE_KIT, SAUT)
    def test_the_real_wiring_holds(self):
        texte = CI.read_text(encoding="utf-8")
        self.assertEqual(defauts_du_cablage(texte), [])

    @unittest.skipUnless(EST_LE_KIT, SAUT)
    def test_outils_reads_each_root_declaration_and_image_fallback(self):
        texte = CI.read_text(encoding="utf-8")
        cases = (
            ("none", {}, "", ""),
            ("java-version", {".java-version": "21\n"}, ".java-version", ""),
            ("sdkman", {".sdkmanrc": "java=21.0.2-tem\n"}, ".sdkmanrc", ""),
            ("sdkman-empty", {".sdkmanrc": "maven=3.9\n"}, "", ""),
            ("java-tool-versions", {".tool-versions": "java temurin-21\n"}, ".tool-versions", ""),
            ("nvmrc", {".nvmrc": "24\n"}, "", ".nvmrc"),
            ("node-version", {".node-version": "24\n"}, "", ".node-version"),
            ("node-tool-versions", {".tool-versions": "nodejs 24.1.0\n"}, "", ".tool-versions"),
            ("engines", {"package.json": '{"engines":{"node":">=22"}}\n'}, "", "package.json"),
            ("engines-empty", {"package.json": '{"engines":{}}\n'}, "", ""),
            ("both-tool-versions", {".tool-versions": "java temurin-21\nnodejs 24.1.0\n"},
             ".tool-versions", ".tool-versions"),
        )
        for name, files, java, node in cases:
            with self.subTest(case=name):
                tree = self.base / name
                tree.mkdir()
                for path, content in files.items():
                    (tree / path).write_text(content, encoding="utf-8")
                rc, values, output = versions_sur(texte, tree, self.base / f"{name}.output")
                self.assertEqual(rc, 0, output)
                self.assertEqual(values, {"java_file": java, "node_file": node})

    @unittest.skipUnless(EST_LE_KIT, SAUT)
    def test_setup_actions_are_conditional_pinned_and_ordered(self):
        texte = CI.read_text(encoding="utf-8")
        mutations = (
            ("literal Java", "java-version-file: ${{ steps.outils.outputs.java_file }}", "java-version: '25'"),
            ("Java condition", f"if: {JAVA_IF}", "if: true"),
            ("Node condition", f"if: {NODE_IF}", "if: true"),
            ("Node cache", "package-manager-cache: false", "package-manager-cache: true"),
            ("Node SHA", NODE_ACTION, "actions/setup-node@v7"),
            ("Java SHA", JAVA_ACTION, "actions/setup-java@v6"),
            # EC-B1, EC-B2 : a literal version ADDED beside the file wins over it
            ("Java version added", "          java-version-file: ${{ steps.outils.outputs.java_file }}\n",
             "          java-version-file: ${{ steps.outils.outputs.java_file }}\n          java-version: '25'\n"),
            ("Node version added", "          node-version-file: ${{ steps.outils.outputs.node_file }}\n",
             "          node-version-file: ${{ steps.outils.outputs.node_file }}\n          node-version: '24'\n"),
        )
        self.assertEqual(defauts_du_cablage(texte), [])
        for name, old, new in mutations:
            with self.subTest(mutant=name):
                self.assertIn(old, texte)
                faults = defauts_du_cablage(texte.replace(old, new, 1))
                self.assertTrue(any(name.split()[0].lower() in fault.lower() or
                                    name.split()[-1].lower() in fault.lower() for fault in faults),
                                f"{name} escaped: {faults}")
        core = "      - name: Enable corepack (pnpm, yarn)\n"
        node = f"      - uses: {NODE_ACTION} # v7.1.0\n"
        self.assertIn(core, texte)
        self.assertIn(node, texte)
        faults = defauts_du_cablage(texte.replace(node, core + node, 1).replace(core, "", 1))
        self.assertTrue(any("corepack" in fault for fault in faults), faults)

    @unittest.skipUnless(EST_LE_KIT, SAUT)
    def test_the_producer_of_the_signal_is_one_step_and_outputs_reads_it(self):
        texte = CI.read_text(encoding="utf-8")
        ecrivains, lu = ecrivain_de_porte(texte)
        self.assertEqual(len(ecrivains), 1, "exactly one step writes porte= to $GITHUB_OUTPUT")
        self.assertIsNotNone(lu, "jobs.porte.outputs.porte reads no step")
        self.assertEqual(_id(ecrivains[0]), lu)

    @unittest.skipUnless(EST_LE_KIT, SAUT)
    def test_the_run_of_porte_decides_right_on_three_trees(self):
        texte = CI.read_text(encoding="utf-8")
        self.assertEqual(defauts(texte, self.base), [])

    @unittest.skipUnless(EST_LE_KIT, SAUT)
    def test_every_mutant_of_the_wiring_is_named(self):
        texte = CI.read_text(encoding="utf-8")
        for nom, muter in MUTANTS:
            with self.subTest(mutant=nom):
                mute = muter(texte)
                self.assertNotEqual(mute, texte, f"mutant `{nom}` changed nothing — the arm would be vacuous")
                sous = self.base / re.sub(r"\W+", "_", nom)
                sous.mkdir()
                self.assertTrue(defauts(mute, sous), f"mutant `{nom}` is NOT detected")


class SautTests(unittest.TestCase):
    """The one arm WITHOUT a skip: it runs in the kit AND in an adopting tree."""

    def test_the_skip_keys_on_the_marker_not_on_the_pyproject_name(self):
        """A throwaway tree shaped like an adopting project that received the
        kit's manifest (`name = "cadre-kit"`) and the module discovery, WITHOUT
        the marker. This file is copied there and run by a nested pytest:
        rc 0, no FAILED, every kit-only arm SKIPPED. Then the SAME copy with its
        predicate keyed on the pyproject's name must go RED — the witness is
        proven able to fail.
        """
        if os.environ.get(IMBRIQUE) == "1":
            self.skipTest("SAUT ANNONCE : exécution imbriquée de ce témoin (pas de récursion)")
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            arbre = Path(d) / "adoptant"
            (arbre / ".agents" / "bin").mkdir(parents=True)
            (arbre / ".agents" / "security").mkdir(parents=True)
            (arbre / "pyproject.toml").write_text('[project]\nname = "cadre-kit"\ndependencies = []\n', encoding="utf-8")
            (arbre / ".agents" / "security" / "module_discovery.py").write_text("# stand-in\n", encoding="utf-8")
            ini = Path(d) / "pytest.ini"
            ini.write_text("[pytest]\npython_classes = *Tests Test*\n", encoding="utf-8")
            copie = arbre / ".agents" / "bin" / Path(__file__).name
            source = Path(__file__).read_text(encoding="utf-8")
            copie.write_text(source, encoding="utf-8")
            env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "PYTEST_"))}
            env[IMBRIQUE] = "1"

            def jouer() -> subprocess.CompletedProcess:
                return subprocess.run(
                    # `-rfs`: FAILED and SKIPPED lines both reach the summary read below.
                    [sys.executable, "-m", "pytest", "-q", "-rfs", "-p", "no:cacheprovider",
                     "-c", str(ini), "--rootdir", str(arbre), str(copie)],
                    cwd=str(arbre), env=env, capture_output=True, text=True, timeout=300)

            nominal = jouer()
            self.assertEqual(nominal.returncode, 0, nominal.stdout + nominal.stderr)
            self.assertNotIn("FAILED", nominal.stdout)
            saute = nominal.stdout.count("SAUT ANNONCE : arbre adoptant")
            self.assertGreaterEqual(saute, 4, f"expected the 4 kit-only arms SKIPPED, saw {saute}:\n{nominal.stdout}")

            # MUTANT: the predicate keyed on the pyproject's name. Written without
            # the real-root anchor, so this line names no path that does not travel.
            lignes = source.splitlines(keepends=True)
            i = next(k for k, l in enumerate(lignes) if l.startswith("EST_LE_KIT = "))
            lignes[i] = ("EST_LE_KIT = 'name = \"cadre-kit\"' in "
                         "Path(__file__).resolve().parents[2].joinpath('pyproject.toml').read_text(encoding='utf-8')\n")
            mute = "".join(lignes)
            self.assertNotEqual(mute, source)
            copie.write_text(mute, encoding="utf-8")
            mutant = jouer()
            self.assertNotEqual(mutant.returncode, 0, "the predicate keyed on the pyproject's name stayed GREEN")
            self.assertIn("FAILED", mutant.stdout)


if __name__ == "__main__":
    unittest.main()
