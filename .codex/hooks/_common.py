import contextlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def project_root():
    fallback = Path(__file__).resolve().parents[2]
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=fallback,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return fallback
    if result.returncode != 0 or not result.stdout.strip():
        return fallback
    return Path(result.stdout.strip()).resolve()


ROOT = project_root()
# Kit layout: bin = tooling, ref = fixed reference data, state = everything the kit
# generates (index artefacts, board, memory, gates, and the throw-away local bucket).
BIN = ROOT / ".agents" / "bin"
REF = ROOT / ".agents" / "ref"
STATE = ROOT / ".agents" / "state"
INDEX = STATE / "index"
BOARD = STATE / "board"
MEMORY = STATE / "memory"
GATES = STATE / "gates"
LOCAL = STATE / "local"


def read_payload():
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"_raw": raw}


def emit(obj):
    if obj:
        print(json.dumps(obj, separators=(",", ":")))


def _copilot():
    return (os.environ.get("AGENTS_HOOK_HOST") or "").strip().lower() == "copilot"


def deny(reason, event_name="PreToolUse"):
    obj = {
        "hookSpecificOutput": {
            "hookEventName": event_name,
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    if _copilot():
        obj["permissionDecision"] = "deny"
        obj["permissionDecisionReason"] = reason
    emit(obj)


def additional_context(message, event_name="SessionStart"):
    obj = {
        "hookSpecificOutput": {
            "hookEventName": event_name,
            "additionalContext": message,
        }
    }
    if _copilot():
        obj["additionalContext"] = message
    emit(obj)


def system_message(message):
    emit({"systemMessage": message})


def tool_name(payload):
    return (
        payload.get("toolName")
        or payload.get("tool_name")
        or payload.get("tool")
        or payload.get("name")
        or ""
    )


def tool_args(payload):
    args = (
        payload.get("toolArgs")
        or payload.get("tool_args")
        or payload.get("toolInput")
        or payload.get("tool_input")
        or payload.get("input")
        or payload.get("arguments")
        or {}
    )
    if isinstance(args, str):
        try:
            return json.loads(args)
        except json.JSONDecodeError:
            return {"command": args, "raw": args}
    return args if isinstance(args, dict) else {}


def normalize_path_checked(value):
    """`(text, resolved)`: normalize_path()'s text, and whether its RESOLUTION
    succeeded (T-00000785). ONE body for both, so the flag cannot drift from
    the text and a candidate costs one resolution.

    On failure the UNRESOLVED text comes back with resolved=False, and a caller
    that JUDGES must refuse it before any comparison — judge_targets and
    judge_redirect do, on this flag. The failure is a CLASS, never a list:
    ANY exception the resolution raises (`except Exception`). Known members,
    none of them the limit: OSError; ValueError (UnicodeEncodeError included)
    on a NUL or a lone surrogate, measured py3.14.7; RuntimeError on a symlink
    loop under CPython ≤3.12 (measured 3.9.6, 3.11.16, 3.12.14; pyrun.sh
    accepts any Python 3), whose Path.resolve(strict=False) turns ELOOP into
    it; 3.13+ no longer raises there (measured 3.13.15 and 3.14.7). The
    consequence, said rather than found: a symlink loop under tmp/ resolves
    (ALLOW) on 3.13+ and is refused (DENY) on ≤3.12 — an interpreter-dependent
    verdict, accepted because it only ever errs on the closed side.
    Naming two of them and promising "any" is what let the third through
    (S-00002882). A target that resolves fine OUTSIDE the root is NOT a
    failure (the inner branch: `> /tmp/x` is the doctrine idiom).
    resolve(strict=False) swallows most OSErrors itself on 3.13+, so that arm
    rarely fires; Windows is not measured. .agents/bin/kickoff_guard.py:357
    catches ValueError and OSError only and returns "" instead (its gap is
    T-00000793, outside this function). The other readers of a payload path,
    pre_compact_backup.py:25-26 and log_agent_usage.py::transcript_total (both
    hosts), degrade silently — Path.exists() -> False on a NUL and on a lone
    surrogate, measured py3.14.7 — and gate nothing.
    """
    if not value:
        return "", True
    text = str(value).replace("\\", "/")
    resolved_ok = True
    try:
        p = Path(text)
        candidate = p if p.is_absolute() else ROOT / p
        resolved = candidate.resolve(strict=False)
        try:
            text = resolved.relative_to(ROOT.resolve()).as_posix()
        except ValueError:
            text = resolved.as_posix()
    except Exception:  # noqa: BLE001 - the CLASS: OSError, ValueError, RuntimeError (loop, py<3.13), ...
        resolved_ok = False
    while text.startswith("./"):
        text = text[2:]
    return text, resolved_ok


def normalize_path(value):
    """normalize_path_checked() without its flag, for callers that LOCATE a
    path and never judge an unresolved one (protect_paths re-resolves it and
    refuses an unstable form on its own)."""
    return normalize_path_checked(value)[0]


# >>> OUTILS_LECTURE_COPILOT (bloc jumeau, 5 copies : test_copilot_early_exit.py)
# Outils de LECTURE LOCALE sous Copilot : leurs arguments ne sortent pas du
# processus local. Liste POSITIVE et close, comparee au nom de premier niveau
# replie (minuscules, espaces otes, tiret vers souligne) ; tout autre nom est
# juge. Les noms exclus, et leur motif : EXCLUS_DE_LA_LISTE du filet.
OUTILS_LECTURE_COPILOT = (
    "view",  # Copilot CLI, mesure (M-P9) : path, view_range
    "grep",  # Copilot CLI, mesure (M-P9) : pattern, paths, output_mode
    "read_agent",  # Copilot CLI, mesure (M-P9) : agent_id, since_turn
    "list_agents",  # Copilot CLI, mesure (M-P9) : include_completed
    "read_file",  # Chat Local, documente, non mesure (U8)
    "file_search",  # Chat Local, documente, non mesure (U8)
    "grep_search",  # Chat Local, documente, non mesure (U8)
    "list_dir",  # Chat Local, documente, non mesure (U8)
)
# <<< OUTILS_LECTURE_COPILOT


def lecture_copilot(payload):
    """Vrai si ET SEULEMENT SI l'hôte qui tourne est copilot, la charge est un
    dict SANS forme groupée (ni `toolCalls` ni `tool_calls`), et toutes les
    graphies de tool_name qui y portent une valeur donnent, repliées comme
    kickoff_guard.fold_tool_name, UN SEUL nom, présent dans
    OUTILS_LECTURE_COPILOT (T-01M4RWC6VHHN479J2A9RRY1BE3). Le hook appelant
    sort alors avant toute E/S propre au garde (le `git rev-parse` d'import de
    `_common.ROOT` a déjà tourné).

    Forme groupée ou HYBRIDE (`toolCalls`/`tool_calls` à côté d'un nom listé :
    un second outil), graphies du nom en désaccord, nom vide, nom
    inconnu ou charge qui n'est pas un dict : faux, donc chemin entier, donc
    JUGÉ — un outil identifié POSITIVEMENT, jamais un trou
    (S-01M4RWM6VG0M0THSNDRJFV1090). JUGÉ ne veut pas dire LU : gitleaks-scan.sh
    --content scanne le texte brut, donc le secret d'un second outil (classe 0,
    gitleaks-scan.test.sh (vii)) ; paths_from_payload ne déplie pas `toolCalls`,
    donc protect_paths.py ne voit pas les chemins d'un lot (trou préexistant).
    Les deux clés de forme groupée forment une
    liste CLOSE, comme les outils : une clé de lot que le dépôt ne connaît pas
    encore n'est pas vue ici. Le jumeau Gemini porte ce même texte, à l'octet,
    et y reste inerte : sous `.gemini/`, event_host() rend « gemini » par la
    table par répertoire, avant toute lecture d'AGENTS_HOOK_HOST. Les trois
    scripts shell à bloc décident en Python sur la même liste, les mêmes clés
    et les mêmes graphies ; le filet .agents/evals/test_copilot_early_exit.py
    les compare à cette fonction.
    """
    if event_host() != "copilot" or not isinstance(payload, dict):
        return False
    if "toolCalls" in payload or "tool_calls" in payload:
        return False
    noms = [
        str(payload[cle]).strip().lower().replace("-", "_")
        for cle in ("toolName", "tool_name", "tool", "name")
        if payload.get(cle)
    ]
    return len(set(noms)) == 1 and noms[0] in OUTILS_LECTURE_COPILOT


def command_from_payload(payload):
    args = tool_args(payload)
    for key in ("command", "cmd", "script", "raw"):
        if key in args:
            return str(args[key])
    if isinstance(payload.get("_raw"), str):
        return payload["_raw"]
    return ""


def paths_from_payload(payload):
    args = tool_args(payload)
    values = []
    # `filePath` : graphie du harness Local de VS Code (T-01M4RWCAGQZKYQ9JS4C1JPBFVQ,
    # S-01M4RWM3TC4JWE5FDC8YB819Z4). Meme jeu, meme ordre que kickoff_guard.
    for key in ("file_path", "filePath", "path", "target_file", "target", "filename"):
        if key in args:
            values.append(args[key])
    patch_sources = [
        args.get("command"),
        args.get("patch"),
        args.get("input"),
        args.get("raw"),
        payload.get("_raw"),
    ]
    for patch in patch_sources:
        if not isinstance(patch, str):
            continue
        for match in re.finditer(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$", patch, re.M):
            values.append(match.group(1).strip())
    return [normalize_path(v) for v in values if normalize_path(v)]


def git_tracked(path):
    try:
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", path],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Canal-A emission (T-00000027) — the Python twin of .claude/hooks/emit-event.sh.
# Three non-negotiables, identical to that script's:
#
# 1. events.py is loaded by EXPLICIT PATH. `from events import emit` is BANNED
#    by that module's own IMPORT CONTRACT: a hook runs from an arbitrary cwd,
#    so sys.path[0] is never .agents/bin and a bare name-import resolves to
#    nothing — or worse, to some unrelated events.py that happens to be
#    importable. The path is read from BIN at CALL time, not bound at import,
#    so a test can repoint that constant the way point_hook_at() already
#    repoints INDEX/BOARD/MEMORY in .agents/evals/test_ledger_parity.py.
#
# 2. FAIL-OPEN, ABSOLUTELY. Module absent, events.py broken, a value json
#    refuses to serialize — nothing is written, nothing propagates, and NOT ONE
#    BYTE reaches the hook's stdout or stderr. stdout here is a PROTOCOL
#    channel (the host parses it as one JSON object), so a stray character is
#    not noise, it is a malformed hook response; hence the redirect below, the
#    in-process equivalent of emit-event.sh's `>/dev/null 2>&1` on its python
#    child. The caller's exit code is never touched either — SystemExit is
#    caught alongside Exception because a telemetry line may not end a hook.
#
# 3. `host` names the host that IS RUNNING, never the file a payload points
#    at — see event_host() below.
#
# C12 (events.py): a module that never loads has, by construction, no later
# successful emit to piggyback a "I was missing" report on. Permanent absence
# is unreportable in-band; the reader infers it. No self-report is attempted.
# ---------------------------------------------------------------------------

# ONE FILE, TWO DIRECTORIES. This file lives byte for byte in `.codex/hooks/`
# (the source) and `.gemini/hooks/` (its copy, regenerated by
# `.agents/bin/hooks_jumeaux.py --ecrire` and held equal by
# .agents/evals/test_guard_decision_parity.py), so it cannot hard-code a host.
# It reads the running host in TWO steps, and the first one that answers wins:
#
# 1. THE DIRECTORY, through the CLOSED table _HOOK_DIR_HOSTS. `.gemini/hooks/`
#    is only ever executed through .agents/hooks.json (Gemini CLI /
#    Antigravity): one directory, one host, so the label is the directory's
#    and no environment variable can move it — an AGENTS_HOOK_HOST set for
#    another host must not relabel Gemini's whole trail. The directory is read
#    from os.path.abspath, never resolve(): a symlinked hooks directory keeps
#    the name its host calls it by.
# 2. THE REGISTRATION, for a directory that serves several hosts. Copilot and
#    Kimi execute the Codex hooks (L-006: .github/hooks/agent-guardrails.json
#    and .kimi-code/hooks.json point their events at .codex/hooks/*.py), so
#    `.codex` answers nothing and is NOT in the table. Neither can the payload:
#    the dialects do differ — that is why tool_name()/tool_args() above try
#    several spellings — but no field names its host, and deducing one from key
#    casing would be a guess dressed as a fact (the
#    enumerate-instead-of-normalize mistake, L-00000042). The only discriminant
#    that exists at runtime is the one the REGISTRATION supplies:
#    AGENTS_HOOK_HOST, set to "codex" in .codex/hooks.json, to "copilot" in
#    .github/hooks/agent-guardrails.json and to "kimi" in .kimi-code/hooks.json.
#
# DOCUMENTED LIMIT, not a silent default: outside the table, when that
# variable is absent — a project provisioned before T-00000027, a hand-run
# hook, a host that grew a new event nobody registered — this process
# genuinely cannot tell the hosts apart, so it labels NOTHING. `host` is left
# out of the envelope (it lands as null and events.py files the line under
# `.unknown.`) rather than defaulting to "codex" and attributing every Copilot
# denial to Codex. A visible hole in the dashboard's Coverage view is data; a
# plausible wrong label is not.
_HOOK_HOST_ENV = "AGENTS_HOOK_HOST"
_HOOK_HOSTS = ("codex", "copilot", "kimi")
_HOOK_DIR_HOSTS = {".gemini": "gemini"}


def hook_dir(path=__file__):
    """The host directory (`.codex`, `.gemini`) that carries `path`, whose
    `hooks/` is the parent of `path`. One reader for the three things that
    follow the directory — the host label here, the RUN_LOG lock prefix of
    log_agent_usage.py and the `backups` folder of pre_compact_backup.py — so
    they cannot drift apart. abspath, not resolve(): see the note above."""
    return os.path.basename(os.path.dirname(os.path.dirname(os.path.abspath(path))))


def event_host():
    """The running host, or None when this shared file cannot tell.

    The directory table answers first; then AGENTS_HOOK_HOST. A value outside
    the closed set above is treated as absent rather than forwarded: `host`
    decides a filename under .agents/state/events/, so an arbitrary string out
    of the environment has no business reaching it.
    """
    by_dir = _HOOK_DIR_HOSTS.get(hook_dir())
    if by_dir:
        return by_dir
    value = (os.environ.get(_HOOK_HOST_ENV) or "").strip().lower()
    return value if value in _HOOK_HOSTS else None


def emit_event(kind, **fields):
    """Append one canal-A event. Never raises, never prints, never changes the
    exit code (see the contract block above). Returns None always — there is no
    success signal, by design, exactly as in events.py's own emit()."""
    sink = io.StringIO()
    try:
        with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            spec = importlib.util.spec_from_file_location("events", BIN / "events.py")
            if spec is None or spec.loader is None:
                return None
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            host = event_host()
            if host:
                fields.setdefault("host", host)
            module.emit(kind, **fields)
    except (Exception, SystemExit):
        # Un module a moitie execute reste enregistre et serait REUTILISE casse
        # par le prochain chargement du meme nom dans ce processus.
        sys.modules.pop("events", None)
        pass
    return None
