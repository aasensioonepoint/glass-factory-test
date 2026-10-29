import importlib.util
import subprocess
import sys

from _common import BIN, BOARD, INDEX, LOCAL, MEMORY, ROOT, STATE, additional_context, emit_event


MAX_INDEX_CHARS = 12000
MAX_TASK_LINES = 40


def refresh_index_if_stale():
    """Best-effort, 0-LLM deterministic index freshness refresh (reader-side,
    no new hook registration) — mirrors the Claude Code session-start.sh guard.

    Only runs on already-indexed repos (SYMBOLS.md must already exist): this
    refresh never does a first full scan. An adopter's first scan comes from
    the bootstrap that main() LAUNCHES, detached (amorcage_auto.py ->
    setup_projet.py, index leg, T-00001103) ; in the kit, or on a repo the
    bootstrap skips, it stays an explicit /index decision. A failed or slow
    refresh must NEVER cost the agent its index/board/ledger, so every failure
    (including a timeout) is swallowed.
    """
    builder = BIN / "build_index.py"
    if not (builder.exists() and (INDEX / "SYMBOLS.md").exists()):
        return
    try:
        subprocess.run(
            [sys.executable, str(builder), "--root", str(ROOT), "--if-stale"],
            capture_output=True,
            timeout=5,
        )
    except Exception:
        pass


def read_text(path, limit=None):
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    if limit and len(text) > limit:
        return text[:limit] + "\n...[truncated]\n"
    return text


def _forme_presente(monolithe, dossier):
    """A store is PRESENT when its monolith is a file OR its record folder holds
    one regular, non-dotted `*.json` — the exact parity of `_ss_forme_presente`
    in .claude/hooks/session-start.sh (T-01M4KKMY43ZKCW1YD2Y8JX9MKH). Presence
    only: the content always comes from the CLI module, which reads both forms."""
    if monolithe.is_file():
        return True
    try:
        return any(p.is_file() for p in dossier.glob("*.json") if not p.name.startswith("."))
    except OSError:
        return False


def read_board():
    """The task board, SORTED (running -> blocked -> pending -> recent done) so
    the active task is the first thing the agent sees.

    TASKS.json (or the record folder board/tasks/) is the source of truth;
    TASKS.md is its generated view. Falls back to that view when tasks.py is
    missing or the store is malformed: a broken board must never cost the agent
    its whole index.
    """
    if not _forme_presente(BOARD / "TASKS.json", BOARD / "tasks"):
        return ""
    tasks_path = LOCAL / "TASKS.md"
    try:
        spec = importlib.util.spec_from_file_location("tasks", BIN / "tasks.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        # The bounded SessionStart view (T-00000834); a tasks.py that predates
        # it keeps the bare list rather than losing the board. BOUND NOT
        # MEASURED: this host's additionalContext ceiling is unknown and this
        # hook has no total budget (Claude's session-start.sh has one).
        rendu = getattr(mod, "render_session_board", None) or mod.render_list
        return rendu(str(ROOT))
    except Exception:
        # Un module a moitie execute reste enregistre et serait REUTILISE casse
        # par le prochain chargement du meme nom dans ce processus.
        sys.modules.pop("tasks", None)
        if not tasks_path.exists():
            return ""
        lines = tasks_path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "## TASK BOARD\n" + "\n".join(lines[:MAX_TASK_LINES])


def read_ledger():
    """Institutional memory ledger, single source of truth: ledger.py's context().

    LEDGER.json (or the record folder memory/entries/) holds lessons/decisions/
    constraints; context() selects every active constraint plus the 5 most
    recent active lesson/decision entries, capped ~2500 chars. Same fallback
    discipline as the board: a broken ledger must never cost the agent its index
    or its board.
    """
    if not _forme_presente(MEMORY / "LEDGER.json", MEMORY / "entries"):
        return ""
    try:
        spec = importlib.util.spec_from_file_location("ledger", BIN / "ledger.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        return mod.context(str(ROOT))
    except Exception:
        # Un module a moitie execute reste enregistre et serait REUTILISE casse
        # par le prochain chargement du meme nom dans ce processus.
        sys.modules.pop("ledger", None)
        return ""


def main():
    parts = []
    # session.start — emitted FIRST, before the index refresh and before the
    # empty-context return at the bottom, so an un-indexed or empty repo still
    # shows a session on the dashboard. Same placement and same (empty) payload
    # as .claude/hooks/session-start.sh, whose own comment records why:
    # T-00000018 item 4, "it must fire even on an un-indexed repo".
    emit_event("session.start")
    refresh_index_if_stale()
    index = read_text(INDEX / "CODEBASE_INDEX.md", MAX_INDEX_CHARS)
    if index:
        parts.append("## CODEBASE_INDEX.md\n" + index)
    board = read_board()
    if board:
        parts.append(board)
    ledger = read_ledger()
    if ledger:
        parts.append(ledger)
    # Bootstrap LAUNCHED, detached (T-00001103, pilot decision S-01M5WBHK9H):
    # one STATUS line (launched / running / failed + log + remedy / not
    # launched: cause) or nothing. Fail-open: a failure never costs the context.
    ligne = None
    try:
        amorceur = BIN / "amorcage_auto.py"
        if amorceur.is_file():
            spec = importlib.util.spec_from_file_location("amorcage_auto", amorceur)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = mod  # T-00000134: registered before exec_module
            spec.loader.exec_module(mod)
            ligne = mod.amorcer(str(ROOT), str(STATE))
    except Exception:
        ligne = None
    # Project-identity nudge (T-00000048, V1-a). STATUS line in the data frame
    # — never an imperative to the agent (doctrine L-004). Silent while the
    # bootstrap is launched or running: it writes project.json itself (R7).
    # Fail-open: any failure is swallowed so the injected context is never lost.
    en_vol = ("[PROJECT STATUS] amorçage lancé", "[PROJECT STATUS] amorçage en cours")
    try:
        if not (STATE / "project.json").exists() and not (ligne or "").startswith(en_vol):
            parts.append(
                "[PROJECT STATUS] projet sans nom — project.json absent ; "
                "commande d'init à proposer au pilote : "
                "python .agents/bin/project_init.py"
            )
    except Exception:
        pass
    if ligne:
        parts.append(ligne)
    if parts:
        additional_context("\n\n".join(parts), event_name="SessionStart")


if __name__ == "__main__":
    main()
