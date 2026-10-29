#!/usr/bin/env python3
"""dev_shard_reindex — rebuild the codebase index when a DEV shard ends.

T-00000593, candidate (g). THE WINDOW THIS CLOSES, and it was named in
`AGENTS.md` long before anything covered it: index freshness had two
deterministic touchpoints — the post-gate rebuild and a guarded refresh at
SessionStart — and *neither covers the mid-task window between two dev shards*.
Shard A moves a symbol, shard B starts and reads an index that predates it.

MEASURED BEFORE BEING BUILT (2026-09-14, this repo): the staleness probe costs
0,29 s and the incremental rebuild 0,43 s for 11 changed files. That is what
decides REBUILD over NUDGE — a notice would leave the next shard reading the
same stale index, and the fix is cheaper than the notice is useful.

WHY `SubagentStop` IS THE RIGHT EVENT, in this kit's own terms: the design rule
of T-00000593 is "what DETERMINISTIC ARTEFACT would exist if the rule had been
followed, and who can OBSERVE it". Here the host itself reports which def just
finished, in the payload's `agent_type`. Nothing is self-declared by the agent
being watched, so the usual objection — a marker an agent posts about itself
proves nothing — does not apply.

FIVE BOUNDS, WRITTEN BECAUSE A GUARD WHOSE LIMITS ARE UNWRITTEN READS AS
COVERING MORE THAN IT DOES. (The first draft said "four" and listed five — a
count that does not match its own list is the smallest version of the same
defect this file exists to avoid.)

1. IT IS ADVISORY AND ALWAYS EXITS 0. It refuses nothing. The kit has never
   made indexing a blocking condition and this does not change that.
2. THE SET OF DEV AGENTS IS CLOSED AND NAMED BELOW. `frontend-fidelity` is in
   it because `AGENTS.md` says the dev slot on a UI task IS that agent —
   leaving it out would keep the window wide open on exactly the tasks that
   move component files around.
3. ONLY CLAUDE'S `SubagentStop` IS MEASURED. Four other host registries declare
   the event and none has been observed emitting it (the same honesty the
   binôme trace carries). This file lives in `.agents/bin/` rather than
   `.claude/hooks/` so those hosts can register it without a second copy — but
   registering it is not the same as measuring it, and nothing here claims they
   do.
4. IT REBUILDS THE INDEX FILES, NOT `index.db`. That store is advisory and its
   resync is a deliberate manual gesture (`migrate_index_to_db.py --resync`).
   Doing it silently here would cross the line the index doctrine draws.
5. IT ONLY FIXES THE STALENESS A REBUILD CAN FIX, and that is narrower than
   "stale". A shard that creates files without tracking them leaves the probe
   saying `INDEX STALE — N fichier(s) NON SUIVI(S)` whatever gets rebuilt: an
   incremental build ADDS them to the index, a `--full` (built from
   `git ls-files` alone) REMOVES them, and the STALE survives both
   (T-00000230, T-00000608). `--if-stale` therefore answers `INDEX CURRENT` on
   that motive alone, and this hook stays silent, correctly: it has nothing to
   do. The remedy there is `git add` THEN a commit, then a rebuild
   (`--if-stale`, a bare build or `--full`) — or removing or ignoring the
   file — and no hook is going to take that decision for anyone. A `git add`
   ALONE does not end it, measured (T-00000608): the probe stays STALE and
   `--if-stale` rebuilds on every call. Removing or ignoring makes the PROBE
   current, but a file an incremental build already ABSORBED keeps its symbols
   ACTIVE in the index: `--full` drops them at once; without it, a removed
   file's rows go at the next bare build (`--if-stale` answers CURRENT and
   builds nothing), an ignored file's survive incremental builds — measured,
   `test_build_index_non_suivi.py`.

AND IT SPEAKS WHEN IT ACTS — WHICH THE FIRST DRAFT DID NOT DO. It keyed on
`out.startswith("INDEX BUILT")`, and `build_index.py` prints up to five LOCK
lines on stdout BEFORE its result line, including the one it writes when it
STEALS a leaked lock. Measured: in that case the rebuild HAPPENS and the hook
said nothing — the exact contradiction of this paragraph, sitting two
paragraphs below it. It now scans the lines, and it names the two silences that
used to pass for success: a build skipped behind a lock, and a builder that
exits non-zero.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

# CLOSED SET. Adding to it is a decision, not a convenience: every name here
# buys a rebuild on every one of that agent's returns.
#
# DELIBERATELY OUT, AND NAMED RATHER THAN FORGOTTEN: `security-remediation`
# carries Edit+Write, so it is among the defs that PRODUCE. It is left out because its edits land on dependency manifests
# far more often than on indexed sources, and the post-gate rebuild catches
# those. Revisit the day a remediation shard is MEASURED moving a symbol —
# until then this is a judgement, and it is written down as one.
#
# `terraform-deployer` IS DELIBERATELY OUT TOO (T-01M52X1W3WPKCWX1DC36NMKJB6):
# it is the dev slot of an IaC task and carries Edit+Write, but what it writes
# is `.tf` / `.tfvars`, and no such suffix is in `build_index.py`'s `SRC_EXT`:
# a rebuild after its return would find no symbol to move and only pay the cost.
# Revisit the day `SRC_EXT` indexes Terraform.
DEV_AGENTS = ("dev-mono", "dev-multi", "frontend-fidelity")

# The SessionStart refresh uses the same ceiling. A cold tree is far slower than
# the 0,43 s measured incrementally, and a hook that outlives its turn is worse
# than a stale index.
TIMEOUT_SECONDS = 5


def _payload() -> dict:
    """The hook payload, or an empty mapping. Never raises: a hook that dies on
    a shape it did not expect is a hook that takes the turn with it."""
    try:
        raw = sys.stdin.read()
    except Exception:  # noqa: BLE001 - no stdin is a normal invocation here
        return {}
    if not raw.strip():
        return {}
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _agent(payload: dict) -> str:
    """BOTH SPELLINGS, and that is not defensive programming. `binome-trace`
    read only `agent_type` for a while; on a host that sends camelCase it fell
    silent WITHOUT SAYING SO, so no trace was written and the closure fell back
    on its traced escape. One measured silence is enough to accept both."""
    raw = payload.get("agent_type") or payload.get("agentType") or ""
    return str(raw).strip()


def _root() -> Path:
    # `AGENTS_PROJECT_DIR` N'EST POSÉ PAR RIEN AUJOURD'HUI — `git grep` n'en
    # rend que cette occurrence. Il est là pour le jour où un autre hôte
    # enregistre ce fichier, puisqu'il ne connaîtra pas `CLAUDE_PROJECT_DIR` ;
    # c'est la même décision que la ligne de couverture d'AGENTS.md, qui dit
    # aujourd'hui « 1 mesuré, 0 câblé ». Dit ici plutôt que laissé à deviner.
    env = os.environ.get("CLAUDE_PROJECT_DIR") or os.environ.get("AGENTS_PROJECT_DIR")
    if env:
        candidate = Path(env)
        if candidate.is_dir():
            return candidate
    return Path.cwd()


def main() -> int:
    agent = _agent(_payload())
    if agent not in DEV_AGENTS:
        # ZERO BYTES on every other def, which is most of them. A hook that
        # narrates its own non-participation is noise on every single return.
        return 0

    root = _root()
    builder = root / ".agents" / "bin" / "build_index.py"
    if not builder.is_file():
        return 0

    try:
        done = subprocess.run(
            [sys.executable, str(builder), "--root", str(root), "--if-stale"],
            capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
            cwd=str(root), check=False,
        )
    except subprocess.TimeoutExpired:
        # LE KILL NE LIBÈRE PAS LE VERROU. `subprocess.run(timeout=…)` envoie un
        # SIGKILL, donc le `finally: release_lock` de `build_index.py` ne tourne
        # pas — et le verrou orphelin éteint alors TOUTE reconstruction pendant
        # ses 300 s de péremption : celle-ci, le rafraîchissement SessionStart,
        # la reconstruction post-porte du pipeline et `/index`. Mesuré. Un hook
        # posé pour fermer UNE fenêtre en ouvrait TROIS.
        #
        # On ne retire que le verrou que NOUS venons de faire fuir : sa date est
        # dans la fenêtre du plafond. Risque assumé et borné — si un AUTRE build
        # l'a pris dans ces quelques secondes, le pire est du travail refait,
        # exactement ce que `acquire_lock` accepte déjà en volant un verrou
        # périmé, le publish étant atomique.
        try:
            lock = root / ".agents" / "state" / "local" / ".build_index.lock"
            if lock.is_file() and (time.time() - lock.stat().st_mtime) <= TIMEOUT_SECONDS + 5:
                lock.unlink()
        except OSError:
            pass
        print(json.dumps({"systemMessage": (
            f"COVERAGE DEGRADED - index refresh after the '{agent}' shard hit its "
            f"{TIMEOUT_SECONDS}s ceiling and was abandoned. The index may be stale "
            f"for the next shard: run python .agents/bin/build_index.py --if-stale "
            f"(0 LLM)."
        )}))
        return 0
    except Exception as exc:  # noqa: BLE001 - advisory, never fatal
        print(json.dumps({"systemMessage": (
            f"COVERAGE DEGRADED - index refresh after the '{agent}' shard could not "
            f"run ({type(exc).__name__}). Run python .agents/bin/build_index.py "
            f"--if-stale (0 LLM) if the next shard needs it."
        )}))
        return 0

    out = (done.stdout or "").strip()
    lines = out.splitlines()
    # SCANNÉ, JAMAIS `startswith`. `build_index.py` imprime jusqu'à cinq lignes
    # de VERROU sur stdout AVANT sa ligne de résultat, dont celle qu'il écrit
    # quand il VOLE un verrou fuité. Mesuré : dans ce cas la reconstruction A
    # LIEU et le hook se taisait — ce que son propre docstring interdit en
    # toutes lettres deux paragraphes plus haut.
    built = next((l for l in lines if l.startswith("INDEX BUILT")), None)
    in_flight = any(l.startswith("INDEX BUILD IN FLIGHT") for l in lines)
    remede = "run python .agents/bin/build_index.py --if-stale (0 LLM)"

    if done.returncode == 0 and built:
        print(json.dumps({"systemMessage": (
            f"Index rebuilt after the '{agent}' shard (deterministic, 0 LLM) - "
            f"{built}. The next shard reads a current index; symbol purposes and "
            f"module roles are a separate, deliberate step (the 'indexer' agent)."
        )}))
    elif in_flight:
        # Deux shards d'un groupe parallèle qui rendent la main à 0,1 s, ou un
        # build tué qui a fui son verrou. Se taire ici laisse le shard suivant
        # lire un index périmé sans que personne le sache.
        print(json.dumps({"systemMessage": (
            f"COVERAGE DEGRADED - index refresh after the '{agent}' shard was "
            f"SKIPPED: another build holds the index lock. A parallel shard, or a "
            f"build killed without releasing it. {remede}."
        )}))
    elif done.returncode != 0:
        # Le cas qui APPELLE le plus une action humaine — un publish de
        # générations mêlées ne converge que sur un re-run — et c'était le seul
        # qui sortait muet.
        print(json.dumps({"systemMessage": (
            f"COVERAGE DEGRADED - index refresh after the '{agent}' shard exited "
            f"{done.returncode} (marker line: {lines[0] if lines else 'none'}). "
            f"{remede}."
        )}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
