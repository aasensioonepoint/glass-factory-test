import os
import re
import subprocess
import sys

from _common import GATES, command_from_payload, deny, emit_event, read_payload

# T-00000461: `skills_github_fallback.py … install <id>` in command position.
# Verbatim twin (.codex and .gemini) serving five hosts, so a hostname would be
# false — the marker default below is the neutral "hook". Options WITHOUT a value
# are admitted before `install` (a `--root <val> install` escapes — a stated
# bound, like the runner patterns above).
FALLBACK_INSTALL_RE = re.compile(
    r"\bskills_github_fallback\.py\s+(?:-\S+\s+)*install\s+(\S+)", re.IGNORECASE
)


# Runner options are admitted BETWEEN the runner and the verb (`npx --yes skills
# add`, `bunx --bun skills add`): without `_OPTS` an option is enough to walk
# past the gate, which is the cheapest bypass a pattern-anchored guard can have.
# It was already on npx/npm exec and MISSING on pnpm dlx — hence its addition
# below rather than a new line for it.
_OPTS = r"(?:-\S+\s+)*"

# One line per invocation FORM, mirroring .claude/hooks/audit-gate.sh l.90-101.
# `yarn dlx` and `bunx` are the two runners the Claude homologue gates and this
# host did not: a project on yarn 2+ or bun installed skills through an
# unguarded path, on this host only, which is a parity hole rather than a
# policy choice.
INSTALL_PATTERNS = (
    re.compile(r"\b(?:npx|npx\.cmd)\s+" + _OPTS + r"skills\s+add\s+([^\s]+)", re.IGNORECASE),
    re.compile(r"\b(?:npm|npm\.cmd)\s+exec\s+" + _OPTS + r"skills\s+add\s+([^\s]+)", re.IGNORECASE),
    re.compile(r"\b(?:pnpm|yarn)(?:\.cmd)?\s+dlx\s+" + _OPTS + r"skills\s+add\s+([^\s]+)", re.IGNORECASE),
    re.compile(r"\bbunx(?:\.cmd)?\s+" + _OPTS + r"skills\s+add\s+([^\s]+)", re.IGNORECASE),
    re.compile(r"\b(?:codex|codex\.exe|codex\.cmd)\s+skill(?:s)?\s+(?:install|add)\s+([^\s]+)", re.IGNORECASE),
    re.compile(r"\bgh(?:\.exe|\.cmd)?\s+skill\s+install\s+([^\s]+)(?:\s+([^\s]+))?", re.IGNORECASE),
    # The `skills` CLI installed GLOBALLY has no runner in front of it, so the
    # only anchor left is the POSITION OF COMMAND — start of the payload or just
    # after a shell separator. Without that anchor `… discuss skills add later`
    # would be read as an installation; with it, `echo hi && skills add x` still
    # is one. `\n` joins the separator class because this host's scrub crosses
    # newlines while the Claude homologue's sed works per LINE (its `^` is a line
    # start): including it is what keeps the two hosts deciding alike on a
    # multi-line payload. T-00000256 WIDENS that position of command past a
    # bare `skills`: an ASSIGNMENT prefix (`FOO=1 skills add x`, `FOO=@@ ...`
    # once a quoted value was scrubbed) is admitted between the anchor and the
    # CLI as a run of `NAME=value` words and `@@` tokens, because an assignment
    # does not close the command position. And a QUOTED path is scrubbed to
    # ` @@ ` BEFORE this stage, so the CLI itself can be invisible: `@@ add x`
    # (the whole `.../skills` was quoted) and `@@ skills add x` (only the path
    # prefix quoted) are installs too, hence the `@@` command-word alternative.
    # An `@@` in command position may cover a citation that is NOT a path
    # (`; "data" add y` -> DENY when the ref is unaudited): a bounded, SAFE-SIDE
    # false positive -- degrade to refused, never fail-open -- and the audited
    # ref still passes (P11). Non-capturing groups, deliberately: main() reads
    # `match.groups()` as the ref, so a capturing anchor would inject a
    # separator character into it.
    re.compile(r"(?:^|[;&|(`{\n])\s*(?:(?:[A-Za-z_]\w*=[^ \t;&|(`{\n]*|@@)\s+)*(?:(?:[^ \t;&|(`{\n]*[/\\])?skills(?:\.cmd)?|@@)\s+add\s+([^\s]+)", re.IGNORECASE),
)

# A ref STOPS at the first shell metacharacter: `skills add owner/pkg&&echo x`
# installs `owner/pkg`, and a ref carrying `&&echo` matches no AUDIT_LOG line, so
# an ALREADY AUDITED skill would be refused — the gate would block exactly the
# install it is supposed to let through. Same cut as audit-gate.sh l.112, and
# applied to the JOINED ref so the two-token `gh skill install` form behaves
# identically. Written as a scan rather than a regex: `.*$` without re.DOTALL
# stops at the first newline and would leave the tail attached.
_REF_METACHARS = ";&|)`"

# --- PORT NOTE (T-00000225) -------------------------------------------------
# EVERYTHING from the `--- Stage 0.5` banner below down to the end of
# strip_heredoc_bodies() is a VERBATIM copy of .codex/hooks/safe_bash.py: the
# python transcription of .claude/hooks/safe-bash.sh stage 0.5 whose fidelity was
# already established by functional diff under T-00000211. Copying the PYTHON
# rather than re-transcribing the BASH is deliberate — a second transcription
# reopens work already reviewed, and a plain `diff` between these two files is
# what keeps the two guards from drifting. Do NOT "adapt" it here: change
# safe_bash.py and re-copy.
#
# TWO REFERENCES IN THAT PROSE READ DIFFERENTLY IN THIS FILE. Said rather than
# silently edited, because the FIDELITY OF A TRANSCRIPTION IS NOT THE SOUNDNESS
# OF ITS COMPOSITION: the stage was proven faithful at ONE caller, and this
# caller's environment is not that one.
#   - "stage 1" here is quoted_spans()/scrub_quoted() below, which is NOT
#     isometric: it replaces a quoted run by the 4-character ` @@ `. That costs
#     nothing, because this file never indexes the RAW payload with an offset
#     computed on the scrubbed copy — it reads `match.groups()`, never a slice.
#     safe_bash.py does the opposite and pays for isometry; both are correct for
#     their own reader, which is exactly why this line is written down.
#   - "stage 2's cut on `\n`" has no counterpart here, but the LINE COUNT this
#     stage preserves matters for the same reason: the last INSTALL_PATTERNS
#     entry anchors a bare `skills add` on a separator class that INCLUDES `\n`,
#     so a body blanked to FEWER lines would move that anchor. Blanking to EMPTY
#     lines keeps every `\n` in place, and the arms measure it here too.
# --- Stage 0.5: a heredoc BODY is redirected DATA, never code ---------------
# PORT of .claude/hooks/safe-bash.sh stage 0.5 (T-00000210's PIECE PARSER, not
# the `OPEN_RE` regex it replaced), rule for rule. It runs BEFORE stage 1
# because a heredoc body is not QUOTED — it is REDIRECTED — so quoted_spans()
# can do nothing about it. The founding incident is the third of its kind: a
# `git commit -F -` whose message DESCRIBED a guarded command was refused.
#
# THE THREE LOAD-BEARING PROPERTIES, each of which a "simplification" would
# break in a direction the guard cannot afford:
#
#  1. POLARITY. A body is blanked ONLY IF AT LEAST ONE PIECE OF THE DELIMITER
#     IS QUOTED. Bash builds the delimiter word by CONCATENATING pieces and then
#     removing the quotes, so `<<'A'B` -> `AB`, `<<\EOF` -> `EOF`, `<<E"O"F` ->
#     `EOF`, and each of those bodies is 100% literal. A fully NAKED delimiter
#     (`<<EOF`) is the opposite case: bash EXPANDS `$(…)` inside that body, so
#     the body really can execute a command and it stays ANALYSED. Blanking it
#     would be a fail-open.
#  2. FAIL-CLOSED ON EVERY NON-RECOGNITION. An unknown piece, a character
#     outside `[A-Za-z0-9_]`, an unclosed quote, a missing word boundary, no
#     quoted piece at all: the parser returns "" and the body is KEPT, hence
#     analysed. That is the parser's ONLY error exit, by design.
#  3. THE TRAILING WORD BOUNDARY IS PART OF RECOGNITION. After the last piece
#     there must be end-of-line or a separator; without it the parser would keep
#     a PREFIX of the delimiter, never find its closing line, and blank to the
#     end of the payload — a measured fail-open.
#
# The scan of the introduction line is anchored on the FIRST `<<` candidate with
# NO retry (a retry reopens the herestring hole `<<<`), refuses to open a body
# when the line does not end in a NEUTRAL state (unpaired quote, trailing `\`,
# open `(`/`[`/`{`/backtick — bash opens the body after the LOGICAL line), and
# stops at an unquoted `#` in word-initial position.
#
# NOT COVERED, enumerated rather than universally claimed — same list as the
# Claude homologue: `<<'W'` in a lexical position where `<<` is not a redirection
# operator (`${v#<<'X'}`, `((x<<'A'))`) still opens a false body; a delimiter
# carrying a space, a `$` or a dot stays outside `[A-Za-z0-9_]`, so its body is
# ANALYSED (bounded FALSE POSITIVE, never a fail-open). The COMMENT-BOUNDARY
# clause of stage 1 used to be listed here as NOT ported and live — T-00000225
# closed it, and stage 1 now REUSES the `#`/`head` clause below rather than
# owning a second copy of it; the line is corrected instead of left standing,
# because a comment that describes a hole already shut is the next reader's bug.
_HD_SQ = "'"
_HD_DQ = '"'
_HD_BS = "\\"
_HD_BT = "`"
_HD_SEP = " \t;&|()" + _HD_BT
_HD_TAIL = _HD_SEP + "<>"
# The SAME class, extended by the ONE character stage 0.5 cannot see: it scans a
# PHYSICAL line at a time, so a newline never reaches it, while stage 1 scans the
# WHOLE payload and must treat a line start as a word start. DERIVED, never a
# second literal — two spellings of one frontier diverge at the first change
# (D1), and the Claude homologue writes exactly this pair (safe-bash.sh l.309 vs
# l.540). Read by quoted_spans() above: a module global is resolved at CALL time,
# so the constant may be defined after the function that uses it, and it is kept
# HERE, beside the clause it is shared with, rather than beside its second reader.
_STAGE1_SEP = _HD_SEP + "\n"
_HD_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_"


def _heredoc_delimiter(line, at):
    """The delimiter word of the `<<` at offset `at`, or "" (fail-closed).

    Pieces are ENUMERATED AND CLOSED — `'X'`, `"X"`, `\\c`, or a NAKED run — each
    bounded to `[A-Za-z0-9_]`; the delimiter is their concatenation with the
    quotes removed. "" whenever at least one piece is not quoted, or anything at
    all is unrecognised: the caller then keeps the body and it stays analysed.
    """
    n = len(line)
    i = at + 2
    if i < n and line[i] == "-":
        i += 1
    while i < n and line[i] in " \t":
        i += 1
    parts = []
    quoted = False
    while i < n:
        ch = line[i]
        if ch == _HD_SQ or ch == _HD_DQ:
            end = line.find(ch, i + 1)
            if end < 0:
                return ""
            inner = line[i + 1:end]
            for c in inner:
                if c not in _HD_CHARS:
                    return ""
            parts.append(inner)
            quoted = True
            i = end + 1
            continue
        if ch == _HD_BS:
            if i + 1 >= n or line[i + 1] not in _HD_CHARS:
                return ""
            parts.append(line[i + 1])
            quoted = True
            i += 2
            continue
        if ch in _HD_CHARS:
            parts.append(ch)
            i += 1
            continue
        break
    if not quoted:
        return ""                       # POLARITY: a naked delimiter EXPANDS
    if i < n and line[i] not in _HD_TAIL:
        return ""                       # a prefix would over-blank to the end
    return "".join(parts)


def _heredoc_scan(line):
    """`(loose, cont, cands)` for one PHYSICAL line.

    `loose` is the offset of the first unpaired quote, `cont` says the line does
    not end in a neutral state, and `cands` holds the offsets of every `<<`
    written outside quotes and before any comment. A `\\<` never forms `<<`, and
    a `#` in word-initial position ends the line for recognition purposes.
    """
    n = len(line)
    i = 0
    loose = -1
    par = 0
    brk = 0
    brc = 0
    tick = 0
    cont = False
    cands = []
    head = True
    while i < n:
        ch = line[i]
        if ch == _HD_BS:
            if i + 1 >= n:
                cont = True
            i += 2
            head = False
            continue
        if ch == _HD_SQ or ch == _HD_DQ:
            end = i + 1
            while end < n:
                if ch == _HD_DQ and line[end] == _HD_BS:
                    end += 2
                    continue
                if line[end] == ch:
                    break
                end += 1
            if end >= n:
                if loose < 0:
                    loose = i
                i += 1
            else:
                i = end + 1
            head = False
            continue
        if ch == "#" and head:
            break
        if ch == "<" and i + 1 < n and line[i + 1] == "<":
            cands.append(i)
            i += 2
            head = True
            continue
        if ch == "(":
            par += 1
        elif ch == ")":
            if par > 0:
                par -= 1
        elif ch == "[":
            brk += 1
        elif ch == "]":
            if brk > 0:
                brk -= 1
        elif ch == "{":
            brc += 1
        elif ch == "}":
            if brc > 0:
                brc -= 1
        elif ch == _HD_BT:
            tick = 1 - tick
        i += 1
        head = ch in _HD_SEP
    if tick or par > 0 or brk > 0 or brc > 0:
        cont = True
    return loose, cont, cands


def _heredoc_opener(line, base, spans):
    """The delimiter this line opens a body with, or "".

    ANCHORED on the FIRST candidate with no retry — retrying at the next offset
    is exactly what let a herestring `<<<` be read as a heredoc — and refusing
    outright when the line carries an unpaired quote or does not end neutral,
    because bash opens the body after the LOGICAL line, not this physical one.

    AND REFUSING when the candidate sits INSIDE a quoted segment opened on an
    EARLIER line (T-00000235, the ROOT critical). `loose` only ever saw a quote
    left open on THIS physical line; the state that matters — "are we already
    inside a string?" — exists only at whole-TEXT level, and stage 1 computes it
    AFTER this stage by construction. Without the veto, `echo "a` / `cat <<X`
    made this stage believe in an opener, blank to the end for want of a
    delimiter, and erase the REAL closing quote together with the guarded command
    that followed it, outside any quoting. Stage 1 never saw that command: it had
    disappeared before its turn. FAIL-OPEN, in CODE territory.

    The veto CALLS `quoted_spans()` rather than restating its rule — on this host
    that function is shared by both stages, so there is no second copy to keep in
    step (the bash homologues must copy it, and pin the copy with an arm). Note
    what the shared rule buys: an UNPAIRED quote opens nothing, so a stray
    apostrophe cannot veto every later heredoc — which is exactly the regression a
    hand-rolled cumulative automaton would have introduced.
    """
    loose, cont, cands = _heredoc_scan(line)
    if not cands:
        return ""
    if loose >= 0 or cont:
        return ""
    at = cands[0]
    for lo, hi in spans:
        if lo <= base + at < hi:
            return ""
    return _heredoc_delimiter(line, at)


def strip_heredoc_bodies(command):
    """The command with every QUOTED-delimiter heredoc body replaced by empty
    lines; naked-delimiter bodies are left untouched (property 1 above).

    The line COUNT is preserved, so stage 2's cut on `\\n` sees the same number of
    segments and the introduction line stays code. `\\r` is stripped from EVERY
    line at storage, not from body lines alone: otherwise `EOF\\r` != `EOF`, the
    body never closes and everything after it is blanked. The closing line is
    reprinted VERBATIM; a body opened and never closed blanks to the end, which
    is safe because an unterminated heredoc is a bash parse error — nothing runs.
    (The Claude homologue drops one trailing newline here; that is undoing its
    own `printf '%s\\n'`, and there is no such addition on this side.)
    """
    src = []
    for raw in command.split("\n"):
        if raw.endswith("\r"):
            raw = raw[:-1]
        src.append(raw)
    # Offsets computed on the RECONSTRUCTED text, never on the original: `\r` is
    # stripped from every line above, so spans taken from the raw command would
    # drift by one character per CRLF line and the veto would aim beside its
    # target — on a Windows checkout, that is every line.
    spans = quoted_spans("\n".join(src))
    bases = []
    pos = 0
    for line in src:
        bases.append(pos)
        pos += len(line) + 1
    out = []
    total = len(src)
    i = 0
    while i < total:
        out.append(src[i])
        delim = _heredoc_opener(src[i], bases[i], spans)
        if delim:
            i += 1
            while i < total and src[i].strip(" \t") != delim:
                out.append("")
                i += 1
            if i < total:
                out.append(src[i])
        i += 1
    return "\n".join(out)


# Stage 1, run BEFORE any pattern match: a command that TALKS about an
# installation is DATA, not an execution. A `tasks.py new "… npx skills add …"`
# title, a commit message or a ledger entry quoting the install line was refused
# here — measured in session on the Claude homologue, whose stage-1 fix this
# ports verbatim in semantics (.claude/hooks/audit-gate.sh, commit e30551e).
# These patterns were already ANCHORED on the command form and the AUDIT_LOG was
# already compared BY FIELDS, so the quoted-segment blind spot was the only one
# left on this host.
#
# ONE left-to-right pass, so the LEFTMOST OPENING quote wins: `"… '…' …"` is a
# single double-quoted segment, not something cut at the apostrophe inside it. An
# unpaired quote (the apostrophe of `l'index`) closes nothing and leaves the
# remainder analysable rather than swallowing it.
#
# DOCUMENTED LIMIT, deliberately not closed: an installation hidden inside a
# quoted argument — `bash -c "npx skills add owner/pkg"` — sits in a neutralized
# segment and is therefore NOT seen. It used to be caught, by substring luck
# rather than by design; recognizing it properly requires parsing `-c`'s
# argument as a nested command, which is a different guard, not a wider regex.
# The Claude homologue makes the same trade, so the hosts stay in parity.


def quoted_spans(text):
    r"""`[(start, end)]` of every quoted segment, BACKSLASH-AWARE.

    A quote preceded by an ODD number of backslashes is an ESCAPED quote: bash
    hands it to the command as a literal character and it opens NOTHING.
    Reading it as an opening quote is a class-1 bypass, and it was a LIVE one
    here — reproduced by the security review of T-00000151, which is why this
    scanner replaced a `'[^']*'|"[^"]*"` regex. In
    `echo \" && npx skills add unaudited/pkg \"` the two escaped quotes made the
    whole interval between them look like one quoted string, so the runner
    patterns below never saw the install at all: bash really ran it, and the
    AUDIT_LOG gate was bypassed without a word.

    The scan follows bash's rules rather than approximating them:
      - outside quotes a backslash escapes the NEXT character, so `\"`, `\'` and
        `\\` are literal — and an EVEN run of backslashes therefore leaves a
        following quote free to open a real segment (`echo \\" && npx skills add
        x \\"` IS a genuine quoted string in bash, and must keep being read as
        data);
      - a single-quoted segment ends at the next `'`, with NO escapes inside:
        `'a\'` really is the two characters `a\` in bash;
      - a double-quoted segment ends at the next UNESCAPED `"`.

    An unpaired quote closes nothing and leaves the remainder analysable, which
    is what keeps `echo l'index && npx skills add other/pkg` refused.

    THE COMMENT BOUNDARY (T-00000225), and the LIVE bypass it closes. An unpaired
    quote living in a `#` COMMENT used to pair with a real quote further on and
    neutralise the whole interval — including a line of REAL CODE, on another
    physical line, that bash genuinely runs. Measured against this very hook
    before the fix: `# don't install this` ⏎ `npx skills add other/pkg && echo
    'ok'` came back ALLOW — an UNAUDITED install walked straight past the gate —
    while the same line without the comment came back DENY (the negative control,
    which is what makes the measurement mean something).

    THE CLAUSE IS REUSED, NOT REWRITTEN (D1) — it is the one stage 0.5 above
    already carries (`_heredoc_scan`, `if ch == "#" and head`), same separator
    constant via `_STAGE1_SEP`, same `head` tracking, same exceptions: never after
    `$` nor `{`, so `$#` and `${#v}` stay expansions. That reuse is also WHY the
    heredoc stage had to be ported into this file FIRST: without it there was no
    clause here to reuse, and writing the frontier a second time is the drift D1
    forbids. The cut is applied DURING the quote scan, so a quote sitting after
    such a `#` can never take part in a pairing that crosses the end of that line.

    WHAT THE CUT DOES NOT DO, DELIBERATELY (D2): it ERASES nothing. The comment's
    text is not blanked, only excluded from quote pairing, so it flows on to the
    INSTALL_PATTERNS unchanged and is ANALYSED there — an install written after a
    `#` on the same line is still refused. Blanking would match bash more closely,
    but a faulty recognition would then erase CODE, and the `#` lines of a
    NAKED-delimiter heredoc body (whose `$(…)` bash expands) would vanish:
    fail-open. In error this clause can only produce a FALSE POSITIVE.

    STILL A HOLE, reduced but NOT closed: the body of a NAKED-delimiter heredoc
    stays out of reach (stage 0.5 rightly does not blank it), so an apostrophe
    living there can still pair with code further on. Tracked as T-00000224.

    NOTE, and a follow-up rather than a hidden duplication: safe_bash.py needs
    the identical scanner and carries a byte-identical copy, because the shared
    module both import (`_common.py`) was outside this task's authorised file
    list. It belongs there.
    """
    spans = []
    index, length = 0, len(text)
    head = True
    while index < length:
        char = text[index]
        if char == "\\":
            index += 2                      # escaped: never a delimiter
            head = False
            continue
        if char == "#" and head:
            stop = text.find("\n", index)   # EXCLUDED from pairing, never erased
            if stop < 0:
                break
            index = stop + 1
            head = True
            continue
        if char not in "'\"":
            index += 1
            head = char in _STAGE1_SEP
            continue
        end = index + 1
        while end < length:
            if char == '"' and text[end] == "\\":
                end += 2                    # escapes apply inside "" only
                continue
            if text[end] == char:
                break
            end += 1
        if end >= length:
            index += 1                      # unpaired: closes nothing
            head = False
            continue
        spans.append((index, end + 1))
        index = end + 1
        head = False
    return spans


def scrub_quoted(command):
    """Replace each quoted segment with a neutral token.

    Applied to quoted segments ONLY: the bare command is never rewritten, so
    this can never make the guard ALLOW a naked installation it used to refuse.
    WHAT COUNTS AS QUOTED is decided by quoted_spans() — read its docstring
    before touching this: an escaped quote opens nothing.
    """
    out, last = [], 0
    for start, end in quoted_spans(command):
        out.append(command[last:start])
        out.append(" @@ ")
        last = end
    out.append(command[last:])
    return "".join(out)


def install_ref(match):
    """The skill ref carried by one INSTALL_PATTERNS match, cut at the first
    shell metacharacter (see _REF_METACHARS). Empty when nothing survives the
    cut — the caller then keeps looking, exactly as the awk homologue's loop
    does on an empty ref instead of denying an unnamed install."""
    ref = " ".join(part for part in match.groups() if part)
    for index, char in enumerate(ref):
        if char in _REF_METACHARS:
            return ref[:index].strip()
    return ref.strip()


def audited(ref):
    log = GATES / "AUDIT_LOG"
    if not log.exists():
        return False
    expected = ref.split()
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        fields = line.split()
        if fields[: len(expected)] == expected and "audit=pass" in fields[len(expected) :]:
            return True
    return False


def _cut_ref(ref):
    """Cut a captured id at the first shell metacharacter (parity with
    install_ref)."""
    for index, char in enumerate(ref):
        if char in _REF_METACHARS:
            return ref[:index].strip()
    return ref.strip()


def _confirmed_by(scrubbed):
    """The value after `--confirmed-by`, or "" (the gate only needs its presence)."""
    toks = scrubbed.split()
    for i in range(len(toks) - 1):
        if toks[i] == "--confirmed-by":
            return toks[i + 1]
    return ""


def _run_fallback_gate(ref, confirmed):
    """Run `skills_github_fallback.py gate` in command position, POSING the agent
    marker — a hook IS an agent context by construction, and `.agents/hooks.json`
    (Gemini AND Antigravity → this file) passes NO AGENTS_HOOK_HOST, so without
    the neutral "hook" default a `--confirmed-by x` would TRAVERSE on those two
    hosts, and on them alone (C10). Returns the gate's rc, or None on a launch
    failure (announced, degraded — a broken instrument never decides)."""
    root = GATES.parents[2]
    script = root / ".agents" / "bin" / "skills_github_fallback.py"
    if not script.exists():
        sys.stderr.write(
            "COVERAGE DEGRADED: audit-gate — skills_github_fallback.py missing; "
            "fallback-install not gated.\n"
        )
        return None
    env = dict(os.environ)
    if not env.get("AGENTS_HOOK_HOST", "").strip():
        env["AGENTS_HOOK_HOST"] = "hook"
    cmd = [sys.executable, str(script), "--root", str(root), "gate", ref]
    if confirmed:
        cmd += ["--confirmed-by", confirmed]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    except Exception as exc:  # pragma: no cover - defensive
        sys.stderr.write(
            f"COVERAGE DEGRADED: audit-gate — cannot launch fallback gate ({exc}); "
            "not gated.\n"
        )
        return None
    if proc.stderr:
        sys.stderr.write(proc.stderr)
    return proc.returncode


def main():
    payload = read_payload()
    command = command_from_payload(payload)
    if not command:
        return

    # Stage 0.5 BEFORE the quote scan, and the order is the whole point: a
    # heredoc body is not QUOTED, it is REDIRECTED, so quoted_spans() can do
    # nothing about it. Measured on this file before the port: a `git commit -F -`
    # whose message carried an apostrophe (`it's fine`) inside a QUOTED-delimiter
    # body let that apostrophe pair with a real quote further down and whitened a
    # genuine `npx skills add other/pkg` — the gate said nothing about an
    # unaudited install. This is CRITICAL n°2, closed on the Claude host by
    # T-00000208 and on safe_bash.py by T-00000211; audit_gate.py never had it.
    heredoc_free = strip_heredoc_bodies(command)

    scrubbed = scrub_quoted(heredoc_free)

    # Stage 2-bis (T-00000461): the local skills fallback's own `install`, gated in
    # COMMAND POSITION by its `gate` subcommand. rc 0 falls through (nothing below
    # matches this form); rc != 0 denies; a launch failure degrades (announced).
    fb = FALLBACK_INSTALL_RE.search(scrubbed)
    if fb:
        fb_id = _cut_ref(fb.group(1))
        if fb_id:
            rc = _run_fallback_gate(fb_id, _confirmed_by(scrubbed))
            if rc is None:
                return
            if rc != 0:
                deny(
                    "BLOCKED by audit gate: skills_github_fallback install refused "
                    f"by its confirm gate (rc {rc})"
                )
                emit_event(
                    "hook.deny", guard="audit-gate",
                    rule="skills-fallback-install-unconfirmed", path=fb_id,
                )
                return

    for pattern in INSTALL_PATTERNS:
        match = pattern.search(scrubbed)
        if not match:
            continue
        ref = install_ref(match)
        if not ref:
            continue
        if not audited(ref):
            # The remedy (T-00001192) is the Claude homologue's, word for word
            # from "log it with" on: the kit appender with the id UNQUOTED.
            deny(
                "BLOCKED by audit gate: no audit=pass entry for "
                f"'{ref}' in .agents/state/gates/AUDIT_LOG. Run the security audit "
                "and log it with the kit appender, never a shell redirect (refused "
                "where AUDIT_LOG is git-tracked) nor an Edit/Write rewrite (it drops "
                "the lock): python3 .agents/bin/skills_github_fallback.py audit-log "
                "<owner>/<repo>#<skill>@<sha> --pass — it covers a ref of the form "
                "<owner>/<repo>#<skill>; any other ref has no documented writer: "
                "report it to the pilot. Then retry."
            )
            # hook.deny{guard,rule,path} — `path` carries the SKILL REF, not the
            # command: the ref is a short, bounded identifier extracted by the
            # patterns above, which is exactly what the Claude homologue sends
            # in that field. The surrounding command line never leaves this
            # process (the safe-bash reasoning in L-00000043 applies here too:
            # `npx skills add` can sit in the same line as a token-bearing one).
            emit_event(
                "hook.deny", guard="audit-gate", rule="skills-add-unaudited", path=ref
            )
        return


if __name__ == "__main__":
    main()
