import os
import subprocess
import sys
from pathlib import Path

from _common import INDEX, ROOT, emit_event, read_payload, system_message


# Union des deux copies d'avant la source unique (T-01M4V7R5H0), plus `.agents/vendor`
# (cadre et agentic_v3 y vivent depuis T-01M5BXTRP8GKS7DMDQCTKK88DZ, S-01M5CP0WAG).
WATCH_DIRS = ("src", "lib", "app", "packages", "services", ".agents/bin", ".agents/ref", ".agents/vendor", ".codex/agents", ".github/agents", ".gemini/agents")


def newest_source_mtime():
    newest = 0.0
    for rel in WATCH_DIRS:
        base = ROOT / rel
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file() and not any(part in {".git", "node_modules", "dist", "build", "__pycache__"} for part in path.parts):
                try:
                    newest = max(newest, path.stat().st_mtime)
                except OSError:
                    pass
    return newest


# --- sonde DB, ADVISORY et INDEPENDANTE du controle mtime ci-dessus ----------
# T-00000120. Deux perémptions coexistent dans ce depot et leur divergence est
# VOULUE (voir le commentaire de main()) : le controle mtime dit « des sources
# ont bouge depuis SYMBOLS.md », la sonde dit « la base SQLite (store MACHINE,
# hors depot depuis T-00000668) est d'une generation anterieure aux fichiers
# d'index ». La seconde etait dite sur
# Claude et NULLE PART ailleurs, alors que les quatre hotes lisent le meme
# depot ; c'est le trou que ce code ferme.
#
# ON N'IMPORTE PAS migrate_index_to_db : la comparaison n'est pas a nous. Le
# probe la possede deja, AVEC sa semantique de degradation (base absente,
# illisible, sans meta -> silence, jamais un faux STALE), et la reimplementer
# ici ferait diverger deux definitions de plus.
#
# TOUTE defaillance degrade en SILENCE — builder absent, rc non nul, timeout,
# exception. C'est un rappel consultatif, jamais une barriere : un hook qui
# bloque parce qu'un sous-processus a echoue bloque la session pour un defaut
# qui n'est pas le sien.
DB_STALE_PREFIX = "DB STALE @ "
PROBE_TIMEOUT_SECONDS = 8


def db_stale_lines():
    """Les lignes `DB STALE @ ...` du probe, ou [] — jamais une exception.

    Le timeout est borne a 8 s et non a 30 : ce hook tourne devant l'utilisateur,
    et une sonde consultative qui fait attendre une demi-minute a deja coute plus
    qu'elle ne rapporte.
    """
    builder = ROOT / ".agents" / "bin" / "build_index.py"
    if not builder.exists():
        return []
    try:
        done = subprocess.run(
            [sys.executable, str(builder), "--stale-check"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if done.returncode != 0:
        return []
    return [line.strip() for line in (done.stdout or "").splitlines()
            if line.strip().startswith(DB_STALE_PREFIX)]


def main():
    read_payload()
    symbols = INDEX / "SYMBOLS.md"
    if not symbols.exists():
        system_message("Index reminder: .agents/state/index/SYMBOLS.md is missing. Run $index.")
        # index.stale{reason} — same kind and same field as the Claude homologue
        # (stop-reindex.sh). The reason TEXT differs across hosts because the
        # staleness DEFINITION does: Claude asks build_index.py --stale-check so
        # the nudge can never disagree with the refresh it recommends, while this
        # host compares mtimes over WATCH_DIRS. Naming the real cause beats
        # copying a string that would misdescribe this check. Note this branch
        # has no Claude counterpart at all (that hook exits silently when there
        # is no index) — it is not suppressed for symmetry: the hook really did
        # fire, and the Coverage view should see it.
        emit_event("index.stale", reason="SYMBOLS.md missing")
        return
    newest = newest_source_mtime()
    if newest and newest > symbols.stat().st_mtime:
        system_message("Index reminder: source or agent files are newer than .agents/state/index/SYMBOLS.md. Run $index if structure changed.")
        emit_event("index.stale", reason="source or agent files newer than SYMBOLS.md")

    for line in db_stale_lines():
        # Message et evenement SEPARES du rappel mtime ci-dessus : les deux
        # peuvent tomber au meme tour et disent des choses differentes ; les
        # fondre ferait croire a une seule cause.
        system_message(
            "Index reminder: the SQLite index store (machine, hors dépôt) is a generation "
            f"behind ({line}). Run: python .agents/bin/migrate_index_to_db.py --resync"
        )
        emit_event("index.stale", reason=line)


if __name__ == "__main__":
    main()
