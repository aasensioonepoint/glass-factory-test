"""The SAST scanner is REGISTERED as a host hook on five registries — this suite
proves the CABLING, never the runtime firing.

DEFECT this closes. Until Lot B (T-00000476) `grep -l semgrep` over the five hook
registries returned nothing: the ruleset (T-00000317), the `--hook --event=post|stop`
mode (T-00000459 Lot A), the bash-3.2 parse (T-00000477) and the per-event
degradation (T-00000479) were all in place, and NOTHING invoked them. Worse, a
registry that cited `--hook` against a script that did not know the option would
hand the host an exit-2 USAGE error on EVERY edit (the order condition — closed,
and re-checked here as a textual guard before any registry assertion).

DECISION. Five registries cite `.agents/security/semgrep-scan.sh --hook` — on the
post-edit event with `--event=post`, on the end-of-turn event with `--event=stop`.
TWO shapes: four hosts nest `matcher` -> `hooks[]` blocks with a `timeout`; GitHub
Copilot is FLAT (`{version, hooks}`, camelCase events, `timeoutSec`, and NO matcher
of its own). The event is carried by the FLAG, never guessed from a payload graphy.

WHAT THIS SUITE PROVES: the CABLING — that each registry cites the script with the
right flag, the right event, the right host marker, the right Windows leg, the
right budget — and that the coverage legend is CALCULATED from the host table, not
typed, so it cannot drift out of sync with the wiring (L-00000111/L-00000187).

WHAT IT DOES NOT PROVE: that any host actually FIRES the hook at runtime (never
measured off Claude/Codex — L-00000187), and it is a STATIC read: no stub, no
execution of the script (that charge stays with `semgrep-scan.test.sh` and its half `semgrep-scan-git.test.sh`).

LEGEND SURFACES COVERED HERE: the script header, and — because seven doc surfaces
carried a TYPED legend that nothing verified — `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`
(English) and `AGENTS.md`, `docs/usage.html` (French). NOT covered by the legend
assertion, and named so rather than left to look covered: `README-SECURITY-SCAN-SETUP.md`
and the two `SKILL.md` (guardrails, security-gate) — they carry prose about the hook
but not the calculated legend string.

THE SECOND LEGEND (alignement des hôtes, 2026-10-12, réserve C4) — the KICKOFF refusal
channel. `HOSTS_K` is the status column of the table `_HOST_EXIT_CONTRACT` in
`.agents/bin/kickoff_guard.py`, re-read from that file so the two cannot drift apart;
its legend is CALCULATED like the SAST one and asserted on its echoes: `kickoff_guard.py`
(twice, ASCII French), `guardrails/SKILL.md` and `README-CLAUDE.md` (English),
`CADRE/index.html` (French, « aucun » for zero). A word for « hosts » after the first
number is tolerated (« 3 hôtes mesurés »).

THE WHOLE-TREE JUDGE (réserve C2) — every status legend of the TRACKED tree (dated history
excluded, `_HISTORIQUE`) is read, whatever its file: its statuses must come in the order
measured / inherited / assumed / inert-measured, and its values must be the SAST legend or
the kickoff one — the line decides when it names `semgrep`/`SAST` or `kickoff`/`refus`.
No file is exempted whole; a legend that is neither is admitted only by its EXACT extract
(`_EXTRAITS_ADMIS`, empty today). BOUND, written: a legend on a line that names neither
family may carry EITHER value; a legend in a word form `_TERME` does not read is not seen;
the tree is `git ls-files` (one `git` subprocess) — an UNTRACKED file is not judged.

THE WORD-FORM JUDGE (exec-critic L4, MAJEUR 1) — a legend in WORDS, with no count, escaped
both judges above. Two shapes are read: a status then « sur|on » and a host list, or a host
list then a status in CAPITALS; each (host, status) must be that host's SAST or kickoff
status (`HOSTS`, `HOSTS_K`). A trace-family legend is admitted by (file, EXACT extract) only
(`_MOTS_ADMIS`). BOUNDS, written: another turn of phrase (« pour », « for », a parenthesis,
a lower-case status after the host) is not read; `docs/usage.html` is skipped here by the
pilot's decision of 2026-09-09 — a word legend there is seen by the plan's census
(`align-L4-census.py --perime`), not by the gate.

ADOPTING TREE. `CADRE/` never travels (`strip:`): its echo is judged in the kit only
(`.agents/IS_THE_KIT`), where its absence is a failure. The whole-tree judge is KIT-ONLY
too — an adopter's tree carries its own code, not the kit's legends; the surfaces that
travel (AGENTS/CLAUDE/GEMINI, guardrails, README-CLAUDE, kickoff_guard.py) stay judged.
"""

from __future__ import annotations

import copy
import json
import re
import shlex
import subprocess
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# --- The host table. Columns are CLOSED; values are the coverage table of the plan.
#     (host, registry, shape, post_event, post_matcher, stop_event, marker,
#      windows_leg, status)
#     shape        in {nested, flat}
#     post_matcher in {"Edit|Write", "Edit|Write|apply_patch", None}
#     marker       in {absent, codex, gemini, copilot, kimi}
#     windows_leg  in {none, commandWindows, powershell}
#     status       in {MESURÉ, HÉRITÉ, SUPPOSÉ, INERTE-MESURÉ}
HOSTS = [
    ("Claude Code", ".claude/settings.json", "nested",
     "PostToolUse", "Edit|Write", "Stop", "absent", "none", "MESURÉ"),
    ("Codex", ".codex/hooks.json", "nested",
     "PostToolUse", "Edit|Write|apply_patch", "Stop", "codex", "commandWindows", "MESURÉ"),
    ("GitHub Copilot", ".github/hooks/agent-guardrails.json", "flat",
     "postToolUse", None, "agentStop", "copilot", "powershell", "MESURÉ"),
    ("Gemini CLI", ".agents/hooks.json", "nested",
     "PostToolUse", "Edit|Write|apply_patch", "Stop", "gemini", "commandWindows", "INERTE-MESURÉ"),
    ("Antigravity", ".agents/hooks.json", "nested",
     "PostToolUse", "Edit|Write|apply_patch", "Stop", "gemini", "commandWindows", "INERTE-MESURÉ"),
    ("Kimi Code", ".kimi-code/hooks.json", "nested",
     "PostToolUse", "Edit|Write|apply_patch", "Stop", "kimi", "commandWindows", "SUPPOSÉ"),
]

# status -> word, per language. The legend is BUILT from these, never typed twice.
_STATUS_ORDER = ["MESURÉ", "HÉRITÉ", "SUPPOSÉ", "INERTE-MESURÉ"]
_EN = {"MESURÉ": "measured", "HÉRITÉ": "inherited",
       "SUPPOSÉ": "assumed", "INERTE-MESURÉ": "inert-measured"}
# FR : (singulier, pluriel) — le pluriel se CALCULE sur le compte (un mot figé ferait lire
# « 2 inerte-mesuré » dès que le compte change, alignement des hôtes 2026-10-12).
_FR = {"MESURÉ": ("mesuré", "mesurés"), "HÉRITÉ": ("hérité", "hérités"),
       "SUPPOSÉ": ("supposé", "supposés"), "INERTE-MESURÉ": ("inerte-mesuré", "inertes-mesurés")}

SCRIPT = ROOT / ".agents" / "security" / "semgrep-scan.sh"

# --- The KICKOFF refusal-channel table (C4). Same closed status vocabulary; the values are
#     the status column of `_HOST_EXIT_CONTRACT` in kickoff_guard.py (re-read by a test).
HOSTS_K = [
    ("Claude Code", "MESURÉ"),
    ("Codex", "MESURÉ"),
    ("GitHub Copilot", "MESURÉ"),
    ("Gemini CLI", "INERTE-MESURÉ"),
    ("Antigravity", "INERTE-MESURÉ"),
    ("Kimi Code", "SUPPOSÉ"),
]
KICKOFF_GUARD = ROOT / ".agents" / "bin" / "kickoff_guard.py"
# kickoff_guard.py writes French WITHOUT accents: its own spelling, calculated the same way.
_FR_ASCII = {"MESURÉ": ("mesure", "mesures"), "HÉRITÉ": ("herite", "herites"),
             "SUPPOSÉ": ("suppose", "supposes"), "INERTE-MESURÉ": ("inerte-mesure", "inertes-mesures")}
EST_LE_KIT = (ROOT / ".agents" / "IS_THE_KIT").is_file()  # adopting-tree: le marqueur du kit ne voyage pas (strip: .agents/IS_THE_KIT)
# Echoes that never travel (`strip: CADRE/`, la vitrine du kit) : judged in the kit, where their
# absence is a FAILURE, and skipped by name in an adopting tree.
_ECHOS_KIT_SEUL = frozenset({"CADRE/index.html"})
# echo surface -> (words, separator, word for zero, minimum occurrences)
K_ECHOES = {
    ".agents/bin/kickoff_guard.py": (_FR_ASCII, ", ", None, 2),
    ".agents/skills/guardrails/SKILL.md": (_EN, " / ", None, 1),
    "README-CLAUDE.md": (_EN, " / ", None, 1),
    "CADRE/index.html": (_FR, ", ", "aucun", 1),
}


def _legend(words: dict, statuses=None, sep: str = " / ", zero: str | None = None) -> str:
    """The one legend string, CALCULATED from the host statuses (never typed).
    Default: the SAST table `HOSTS`; `statuses` lets the kickoff table use the same rule."""
    counts = Counter(statuses if statuses is not None else (row[8] for row in HOSTS))

    def _terme(s):
        n, w = counts[s], words[s]
        w = (w[1] if n > 1 else w[0]) if isinstance(w, tuple) else w
        return f"{zero if (zero and n == 0) else n} {w}"
    return sep.join(_terme(s) for s in _STATUS_ORDER)


def _k_statuses(rows=None) -> list:
    return [s for _h, s in (rows if rows is not None else HOSTS_K)]


def _sans_mot_hote(text: str) -> str:
    """Whitespace folded, and the optional word for « hosts » after a count dropped."""
    text = re.sub(r"\s+", " ", text)
    return re.sub(r"\b(\d+|aucun) (?:hosts?|h[ôo]tes?) ", r"\1 ", text)


def _k_echoes_judged() -> list:
    # adopting-tree: `CADRE/` est strippé (la vitrine ne voyage pas) ; jugé dans le kit seulement
    return [rel for rel in K_ECHOES if EST_LE_KIT or rel not in _ECHOS_KIT_SEUL]


def _k_echo_violations(rows=None) -> list:
    """The kickoff legend rule, replayable on a mutated table for the negative control."""
    v = []
    for rel in _k_echoes_judged():
        words, sep, zero, minimum = K_ECHOES[rel]
        legend = _legend(words, _k_statuses(rows), sep, zero)
        found = _sans_mot_hote((ROOT / rel).read_text(encoding="utf-8")).count(legend)
        if found < minimum:
            v.append(f"{rel}: kickoff legend {legend!r} found {found}x, expected >= {minimum}")
    return v


# --- The whole-tree judge (C2). Status terms, in figures or in words, EN/FR, with or
#     without accents; a legend is a run of >= 2 terms separated by / , et and.
_HISTORIQUE = ("runs/", ".agents/state/", "docs/interne/", "docs/tasks/", "docs/design/",
               "retro/", "docs/HISTORIQUE-0.1.0.md", "PLAN-ETAT")
_BINAIRES = (".png", ".svg", ".ico", ".jpg", ".jpeg", ".gif", ".woff", ".woff2", ".db", ".pyc")
_EXTRAITS_ADMIS: frozenset = frozenset()  # exact extracts only, never a whole file
_NB_MOTS = {"aucun": 0, "aucune": 0, "zero": 0, "zéro": 0, "un": 1, "une": 1, "one": 1,
            "deux": 2, "two": 2, "trois": 3, "three": 3, "quatre": 4, "four": 4,
            "cinq": 5, "five": 5, "six": 6}
_TERME = re.compile(
    r"(?i)\b([0-9]+|aucune?|z[ée]ro|une?|one|deux|two|trois|three|quatre|four|cinq|five|six)\s+"
    r"(?:hosts?\s+|h[ôo]tes?\s+)?\**"
    r"(inert(?:e|es)?[- ](?:measured|mesur[ée]+s?)|measured|mesur[ée]*s?|inherited|"
    r"h[ée]rit[ée]*s?|assumed|suppos[ée]*s?|wired|c[âa]bl[ée]*s?)")
_SEP = re.compile(r"(?i)^\**\s*(?:\([^)]*\))?\s*\**\s*(?:/|,|\bet\b|\band\b)\s*\**\s*$")


def _statut(mot: str):
    m = mot.lower()
    if m.startswith("inert"):
        return 3
    if m.startswith(("measured", "mesur")):
        return 0
    if m.startswith(("inherit", "hérit", "herit")):
        return 1
    if m.startswith(("assum", "suppos")):
        return 2
    return None  # wired / câblé: a trace count, another family, not judged here


def _legends(text: str) -> list:
    """[(line, values, extract, canonical_order)] of the status legends of a text."""
    terms = list(_TERME.finditer(text))
    out, i = [], 0
    while i < len(terms):
        j = i
        while j + 1 < len(terms) and _SEP.match(text[terms[j].end():terms[j + 1].start()]):
            j += 1
        grp, i = terms[i:j + 1], j + 1
        st = [_statut(m.group(2)) for m in grp]
        if len(grp) < 2 or None in st:
            continue
        vals = [None] * 4
        for m, s in zip(grp, st):
            n = m.group(1).lower()
            vals[s] = int(n) if n.isdigit() else _NB_MOTS[n]
        out.append((text.count("\n", 0, grp[0].start()) + 1, tuple(vals),
                    re.sub(r"\s+", " ", text[grp[0].start():grp[-1].end()]),
                    st == sorted(st) and len(set(st)) == len(st)))
    return out


def _expected_values() -> dict:
    s = Counter(row[8] for row in HOSTS)
    k = Counter(_k_statuses())
    return {"S": tuple(s[x] for x in _STATUS_ORDER), "K": tuple(k[x] for x in _STATUS_ORDER)}


def _legend_faults(rel: str, text: str) -> list:
    """Faults of ONE file under the whole-tree rule (order, then values)."""
    expected, faults = _expected_values(), []
    lines = text.split("\n")
    for n, vals, extract, canon in _legends(text):
        if extract in _EXTRAITS_ADMIS:
            continue
        line = lines[n - 1].lower()
        if "semgrep" in line or "sast" in line:
            allowed = {"S"}
        elif "kickoff" in line or "refus" in line:
            allowed = {"K"}
        else:
            allowed = {"S", "K"}
        if not canon:
            faults.append(f"{rel}:{n}: {extract!r} — statuses out of the order "
                          "measured / inherited / assumed / inert-measured")
        elif vals not in {expected[f] for f in allowed}:
            faults.append(f"{rel}:{n}: {extract!r} = {vals}, expected "
                          + " or ".join(f"{f}={expected[f]}" for f in sorted(allowed)))
    return faults


def _tracked_text_files() -> list:
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"],
                         capture_output=True, text=True, check=True).stdout
    return [f for f in out.split("\0")
            if f and not f.startswith(_HISTORIQUE) and not f.endswith(_BINAIRES)]


# --- The WORD-FORM judge (exec-critic L4, MAJEUR 1). A legend written in words, with no count,
#     escapes `_legends`: « <status> sur|on <hosts> » (form A) or « <hosts> <STATUS> », status in
#     capitals (form B). Each (host, status) must be that host's SAST or kickoff status.
_HOTE_RX = r"(?:claude(?: code)?|codex|(?:github )?copilot|gemini(?: cli)?|antigravity|kimi(?: code)?)(?![\w-])"
_LISTE_RX = rf"{_HOTE_RX}(?:\s*(?:,|\bet\b|\band\b)\s*{_HOTE_RX})*"
# A NEGATED legend (« non mesuré sur … », « not measured on … », FB6's per-host line) states no
# status and is not judged — bound: « NON MESURÉ » is outside this vocabulary (T-01M4VBZFB6, exec-critic).
_FORME_A = re.compile(
    r"(?i)(?<!\bnon\s)(?<!\bnot\s)\b(mesur[ée]+s?\s+inertes?|inert(?:e|es)?[- ]mesur[ée]+s?|inert[- ]measured|inert(?:e|es)?|"
    r"mesur[ée]+s?|measured|h[ée]rit[ée]+s?|inherited|suppos[ée]+s?|assumed)"
    rf"\s+(?:sur|on)\s+({_LISTE_RX})")
_FORME_B = re.compile(
    rf"(?i:({_LISTE_RX}))\s+(INERT(?:E|ES)?(?:-MEASURED|-MESUR[ÉE]+S?)?|MEASURED|MESUR[ÉE]+S?|ASSUMED|"
    r"SUPPOS[ÉE]+S?|INHERITED|H[ÉE]RIT[ÉE]+S?)(?![\w-])")
_SAUT = re.compile(r"\n[ \t]*(?:#+|//)?[ \t]*")  # a wrapped comment line reads as one line
_HOTE_CANON = {"claude": "Claude Code", "codex": "Codex", "copilot": "GitHub Copilot",
               "gemini": "Gemini CLI", "antigravity": "Antigravity", "kimi": "Kimi Code"}
# Another family's word legend (trace T, residual R-T), admitted by (file, EXACT extract) only.
_MOTS_ADMIS = frozenset({
    # closing-review trace: 1 inherited (built, never typed: this file is judged too)
    (".agents/skills/task-board/SKILL.md", "Antigravity " + "HÉRITÉ"),
})


def _status_of_word(word: str) -> str:
    w = word.lower()
    if "inert" in w:
        return "INERTE-MESURÉ"
    if w.startswith(("mesur", "measured")):
        return "MESURÉ"
    if w.startswith(("hérit", "herit", "inherit")):
        return "HÉRITÉ"
    return "SUPPOSÉ"


def _word_legends(text: str) -> list:
    """[(line, [(host, status)], extract)] of the word-form legends of a text."""
    parts, origin, pos = [], [], 0
    for m in _SAUT.finditer(text):
        parts.append(text[pos:m.start()])
        origin.extend(range(pos, m.start()))
        parts.append(" ")
        origin.append(m.start())
        pos = m.end()
    parts.append(text[pos:])
    origin.extend(range(pos, len(text)))
    flat = "".join(parts)

    def hosts(liste):
        return [_HOTE_CANON[h.lower().replace("github ", "").split()[0]]
                for h in re.findall(_HOTE_RX, liste, re.I)]
    out = []
    for m, si, hi in [(m, 1, 2) for m in _FORME_A.finditer(flat)] + [(m, 2, 1) for m in _FORME_B.finditer(flat)]:
        line = text.count("\n", 0, origin[m.start()]) + 1
        status = _status_of_word(m.group(si))
        out.append((line, [(h, status) for h in hosts(m.group(hi))], m.group(0)))
    return out


def _word_faults(rel: str, text: str) -> list:
    tables = {"S": {row[0]: row[8] for row in HOSTS}, "K": dict(HOSTS_K)}
    lines, faults = text.split("\n"), []
    for n, pairs, extract in _word_legends(text):
        if (rel, extract) in _MOTS_ADMIS:
            continue
        line = lines[n - 1].lower()
        allowed = {"S"} if ("semgrep" in line or "sast" in line) else ({"K"} if "kickoff" in line else {"S", "K"})
        wrong = [f"{h} {s}" for h, s in pairs if s not in {tables[f][h] for f in allowed}]
        if wrong:
            faults.append(f"{rel}:{n}: {extract!r} — " + ", ".join(wrong)
                          + f" (expected the {'/'.join(sorted(allowed))} status)")
    return faults


def _load(registry: str) -> dict:
    return json.loads((ROOT / registry).read_text(encoding="utf-8"))


def _matcher_covers(matcher: str, tool: str) -> bool:
    """Split on `|`, never a substring (L-00000143)."""
    return tool in [a.strip() for a in (matcher or "").split("|")]


def _nested_blocks(obj: dict, event: str, matcher):
    blocks = obj.get("hooks", {}).get(event, [])
    if matcher is None:  # a Stop event carries no matcher — take every block
        return blocks
    return [b for b in blocks if _matcher_covers(b.get("matcher", ""), "Edit")]


def _semgrep_entries(obj: dict, shape: str, event: str, matcher) -> list:
    """The two loaders behind one signature. `nested` walks matcher->hooks[]
    blocks whose matcher covers Edit (or every block, for a matcher-less Stop);
    `flat` walks hooks[event] directly. An eval that knew only the nested shape
    would declare Copilot conformant without ever reading it."""
    if shape == "nested":
        out = []
        for block in _nested_blocks(obj, event, matcher):
            for hook in block.get("hooks", []):
                if "semgrep-scan.sh" in str(hook.get("command", "")):
                    out.append(hook)
        return out
    out = []
    for hook in obj.get("hooks", {}).get(event, []):
        if "semgrep-scan.sh" in str(hook.get("bash", "")):
            out.append(hook)
    return out


def _primary(entry: dict, shape: str) -> str:
    return entry.get("command", "") if shape == "nested" else entry.get("bash", "")


def _legs(entry: dict, shape: str) -> list:
    if shape == "nested":
        return [str(entry.get("command", "")), str(entry.get("commandWindows", ""))]
    return [str(entry.get("bash", "")), str(entry.get("powershell", ""))]


def _entry_violations(host, entry, shape, event_kind, marker, windows_leg):
    """THE RULE for one entry, as a list of `host/column: msg` strings, so the
    negative controls replay THIS rule rather than a re-implementation (L-00000349:
    pin the exact named assertion, never "something failed")."""
    v = []
    ev = f"--event={event_kind}"
    toks = shlex.split(_primary(entry, shape))

    # (b)/(c): flag + event as TOKENS (equality, not substring)
    if "--hook" not in toks:
        v.append(f"{host}/{event_kind}: primary leg lacks the --hook token")
    if ev not in toks:
        v.append(f"{host}/{event_kind}: primary leg lacks the {ev} token")

    # (d): host marker
    legs = _legs(entry, shape)
    if marker == "absent":
        if any("AGENTS_HOOK_HOST" in leg for leg in legs):
            v.append(f"{host}/marker: AGENTS_HOOK_HOST must be ABSENT (absent->claude)")
    else:
        bash_leg = legs[0]
        if f"AGENTS_HOOK_HOST={marker}" not in bash_leg:
            v.append(f"{host}/marker: bash leg lacks AGENTS_HOOK_HOST={marker}")
        win = legs[1]
        if win:
            ok = (f"AGENTS_HOOK_HOST='{marker}'" in win) or (f"AGENTS_HOOK_HOST={marker}" in win)
            if not ok:
                v.append(f"{host}/marker: windows leg lacks AGENTS_HOOK_HOST for {marker}")

    # (e): windows leg BY COLUMN VALUE
    if windows_leg == "commandWindows":
        cw = str(entry.get("commandWindows", ""))
        if "commandWindows" not in entry:
            v.append(f"{host}/windows: commandWindows key missing")
        else:
            if not cw.startswith('powershell -NoProfile -NonInteractive -Command "'):
                v.append(f"{host}/windows: commandWindows must be clear PowerShell")
            for needle in (
                "$r=(& git rev-parse --show-toplevel)",
                "& ($r+'/.agents/pyrun.ps1') 'bash' $r "
                "'.agents/security/semgrep-scan.sh'",
                "'--hook'",
                f"'{ev}'",
            ):
                if needle not in cw:
                    v.append(f"{host}/windows: commandWindows lacks {needle}")
            if "$(git rev-parse" in cw:
                v.append(f"{host}/windows: commandWindows must NOT carry $(git rev-parse")
            if "EncodedCommand" in cw or "Invoke-Expression" in cw:
                v.append(f"{host}/windows: commandWindows must stay inspectable")
    elif windows_leg == "powershell":
        ps = str(entry.get("powershell", ""))
        if "powershell" not in entry:
            v.append(f"{host}/windows: powershell key missing")
        else:
            for needle in (
                "$r=(& git rev-parse --show-toplevel)",
                "& bash ($r+'/.agents/security/semgrep-scan.sh')",
                "'--hook'",
                f"'{ev}'",
                "$childExitCode=$LASTEXITCODE; exit $childExitCode",
            ):
                if needle not in ps:
                    v.append(f"{host}/windows: powershell lacks {needle}")
            if re.search(
                r"python|pyrun\.ps1|subprocess|encodedcommand|invoke-expression",
                ps,
                re.IGNORECASE,
            ):
                v.append(f"{host}/windows: native Bash leg gained an opaque bootstrap")
    else:  # none
        if "commandWindows" in entry or "powershell" in entry:
            v.append(f"{host}/windows: no Windows leg expected on {host}")

    # (f): budget
    if shape == "nested":
        if host != "Claude Code":
            if int(entry.get("timeout", 0)) < 60:
                v.append(f"{host}/budget: nested timeout must be >= 60")
    else:
        if "timeout" in entry:
            v.append(f"{host}/budget: a flat entry must carry timeoutSec, not timeout")
        if int(entry.get("timeoutSec", 0)) < 60:
            v.append(f"{host}/budget: flat timeoutSec must be >= 60")
        if "matcher" in entry:
            v.append(f"{host}/matcher: a flat entry carries no matcher")
    return v


def _violations(row, obj):
    """All violations for one host row against its (possibly mutated) registry obj."""
    (host, registry, shape, post_event, post_matcher,
     stop_event, marker, windows_leg, status) = row
    v = []

    posts = _semgrep_entries(obj, shape, post_event, post_matcher)
    if len(posts) != 1:
        v.append(f"{host}/post: expected exactly 1 semgrep post entry, found {len(posts)}")
    stops = _semgrep_entries(obj, shape, stop_event, None)
    if len(stops) != 1:
        v.append(f"{host}/stop: expected exactly 1 semgrep stop entry, found {len(stops)}")

    for entry in posts:
        v += _entry_violations(host, entry, shape, "post", marker, windows_leg)
    for entry in stops:
        v += _entry_violations(host, entry, shape, "stop", marker, windows_leg)

    # (g): Claude alone carries the two permissions.allow lines
    if host == "Claude Code":
        allow = obj.get("permissions", {}).get("allow", [])
        for needed in ("Bash(.agents/security/semgrep-scan.sh:*)",
                       "Bash(bash .agents/security/semgrep-scan.sh:*)"):
            if needed not in allow:
                v.append(f"{host}/permissions: permissions.allow lacks {needed!r}")
    return v


def _header_text() -> str:
    """Header = the text of semgrep-scan.sh before the first `^set -` line."""
    lines = SCRIPT.read_text(encoding="utf-8").splitlines()
    out = []
    for line in lines:
        if re.match(r"^set -", line):
            break
        out.append(line)
    return "\n".join(out)


def _legend_violations(text: str) -> list:
    """The legend rule, replayable on a mutated string copy for control (8)."""
    v = []
    if _legend(_EN) not in text:
        v.append("header: calculated English legend absent")
    if "NO HOST INVOKES IT YET" in text:
        v.append("header: still carries the pre-Lot-B 'NO HOST INVOKES IT YET'")
    if re.search(r"[0-9]+ (rules|règles|regles)", text):
        v.append("header: a number is followed by rules/règles/regles (h8)")
    return v


class SemgrepHookRegistrationTests:
    """Five registries cite the SAST scanner; the legend is calculated; the rule bites."""

    # ---- order condition, re-checked BEFORE any registry assertion ----
    def test_order_condition_script_knows_the_flags(self):
        text = SCRIPT.read_text(encoding="utf-8")
        assert "--hook)" in text and "--event=" in text, (
            "a registry cites --hook but the script in the tree does not know it "
            "-> exit 2 USAGE error on every edit"
        )

    # ---- every registry parses ----
    def test_each_registry_parses_as_json(self):
        for row in HOSTS:
            assert isinstance(_load(row[1]), dict), f"{row[0]}: {row[1]} is not valid JSON"

    # ---- the positive rule, per host ----
    def test_every_host_row_is_conformant(self):
        for row in HOSTS:
            obj = _load(row[1])
            offenders = _violations(row, obj)
            assert not offenders, "conformance violations: " + "; ".join(offenders)

    # ---- non-vacuity ----
    def test_non_vacuity_population_is_the_one_announced(self):
        assert len(HOSTS) == 6, "the host table lost a row"
        assert len({row[1] for row in HOSTS}) == 5, (
            "exactly five registry files back six hosts (Gemini/Antigravity share one)"
        )
        for row in HOSTS:
            obj = _load(row[1])
            posts = _semgrep_entries(obj, row[2], row[3], row[4])
            stops = _semgrep_entries(obj, row[2], row[5], None)
            assert (len(posts) + len(stops)) >= 1, (
                f"{row[0]}: registry rendered no semgrep entry — population is empty"
            )

    def test_legend_is_calculated_from_the_host_table(self):
        # renamed 2026-10-12 (was `…_two_over_one_over_two_over_one`, a value its body no longer pins)
        assert _legend(_EN) == "3 measured / 0 inherited / 1 assumed / 2 inert-measured"
        assert _legend(_FR) == "3 mesurés / 0 hérité / 1 supposé / 2 inertes-mesurés"

    # ---- vacuity pin (piège 2): the phantom sixth registry ----
    def test_gemini_hooks_json_absent_or_add_a_row(self):
        assert not (ROOT / ".gemini" / "hooks.json").exists(), (
            ".gemini/hooks.json now EXISTS — add a line to HOSTS or it is scanned by no test"
        )

    # ---- header legend ----
    def test_header_carries_the_calculated_legend_and_drops_the_old_line(self):
        assert not _legend_violations(_header_text())

    # ---- legend asserted on the docs too (C5) ----
    def test_docs_carry_the_calculated_legend(self):
        en = _legend(_EN)
        fr = _legend(_FR)
        for rel in ("AGENTS.md", "CLAUDE.md", "GEMINI.md"):
            assert en in (ROOT / rel).read_text(encoding="utf-8"), (
                f"{rel}: English calculated legend {en!r} absent"
            )
        # `docs/usage.html` RETIRÉ le 2026-09-09, décision du pilote : page de
        # présentation pour les adoptants, pas une surface de doctrine. Elle
        # VOYAGE toujours ; elle ne fait plus rougir la porte sur son contenu.
        # NE PAS REMETTRE « par symétrie » avec la liste anglaise ci-dessus.
        for rel in ("AGENTS.md",):
            assert fr in (ROOT / rel).read_text(encoding="utf-8"), (
                f"{rel}: French calculated legend {fr!r} absent"
            )

    # ---- the kickoff legend (C4) ----
    def test_kickoff_table_is_the_one_kickoff_guard_states(self):
        rows = re.findall(
            r"^# (Claude Code|Codex|Copilot|Gemini CLI|Antigravity|Kimi Code)\s{2,}.+?\s{2,}"
            r"(INERTE-MESURE|MESURE|SUPPOSE|HERITE)\b",
            KICKOFF_GUARD.read_text(encoding="utf-8"), re.M)
        accents = {"MESURE": "MESURÉ", "HERITE": "HÉRITÉ", "SUPPOSE": "SUPPOSÉ",
                   "INERTE-MESURE": "INERTE-MESURÉ"}
        stated = {("GitHub Copilot" if h == "Copilot" else h): accents[s] for h, s in rows}
        assert len(rows) == 6 and stated == dict(HOSTS_K), (
            f"kickoff_guard.py _HOST_EXIT_CONTRACT says {stated}, HOSTS_K says {dict(HOSTS_K)}")

    def test_kickoff_legend_is_calculated_and_carried_by_its_echoes(self):
        kickoff_legend = "3 measured / 0 inherited / 1 assumed / 2 inert-measured"  # the line names kickoff
        assert _legend(_EN, _k_statuses()) == kickoff_legend
        assert not _k_echo_violations()

    def test_neg_k_flipping_one_status_reddens_the_echoes(self):
        mutated = [(h, "MESURÉ" if h == "Kimi Code" else s) for h, s in HOSTS_K]
        assert mutated != HOSTS_K, "the negative control mutated nothing"
        assert len(_k_echo_violations(mutated)) == len(_k_echoes_judged())

    # ---- the whole-tree judge (C2) ----
    def test_every_status_legend_of_the_tree_is_s_or_k_in_canonical_order(self):
        if not EST_LE_KIT:  # adopting-tree: le juge porte sur les légendes du KIT ; l'arbre d'un adoptant porte son code
            pytest.skip("arbre adoptant : juge de l'arbre entier kit-only (ses surfaces qui voyagent restent jugées plus haut)")
        files, faults = _tracked_text_files(), []
        assert len(files) > 100, "the tracked tree read as nearly empty"
        for rel in files:
            # `docs/usage.html`: page de présentation, retirée des assertions de contenu par
            # décision du pilote (2026-09-09, ci-dessus) — elle ne fait pas rougir la porte.
            if rel == "docs/usage.html":
                continue
            try:
                text = (ROOT / rel).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            faults += _legend_faults(rel, text)
        assert not faults, "status legends neither SAST nor kickoff: " + "; ".join(faults)

    def test_neg_c2_a_variant_legend_in_any_file_reddens(self):
        # MX1: a legend no stale string knows, in a file no table ranges. Built, never typed:
        # this file is itself judged by the whole-tree rule.
        variant = _legend(_EN, ["MESURÉ", "MESURÉ", "HÉRITÉ", "SUPPOSÉ", "SUPPOSÉ", "INERTE-MESURÉ"], ", ")
        assert _legends(variant)[0][1] == (2, 1, 2, 1), "the negative control mutated nothing"
        assert _legend_faults(".github/copilot-instructions.md", f"Coverage: {variant}.\n")

    def test_neg_c2_reordered_statuses_redden(self):
        # MX4: the right values, the order broken (first term inert-measured). Built, never typed.
        terms = _legend(_EN).split(" / ")
        reordered = " / ".join(terms[-1:] + terms[:-1])
        assert _legends(reordered)[0][1] == _expected_values()["S"], "values must stay right"
        assert not _legends(reordered)[0][3], "the negative control did not break the order"
        assert _legend_faults("GEMINI.md", f"Host coverage overall: {reordered}.\n")

    # ---- the word-form judge (exec-critic L4, MAJEUR 1) ----
    def test_every_word_legend_of_the_tree_gives_each_host_its_status(self):
        if not EST_LE_KIT:  # adopting-tree: même borne que le juge chiffré — l'arbre d'un adoptant porte son code
            pytest.skip("arbre adoptant : juge des légendes en mots kit-only")
        faults, judged = [], 0
        for rel in _tracked_text_files():
            if rel == "docs/usage.html":  # décision du pilote 2026-09-09 (ci-dessus) : borne écrite, MY6 n'y est pas vu ici
                continue
            try:
                text = (ROOT / rel).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            judged += len(_word_legends(text))
            faults += _word_faults(rel, text)
        assert judged >= 10, f"only {judged} word legend(s) read — the judge went blind"
        assert not faults, "word legends with a wrong host status: " + "; ".join(faults)

    def test_neg_words_the_old_phrase_reddens_anywhere_it_is_judged(self):
        # MY6, built (never typed: this file is judged too) — the phrase docs/usage.html carried.
        old = ("Parité câblée, mesurée sur Claude et Codex, " + "hérit" + "ée sur Copilot, "
               + "suppos" + "ée sur Gemini CLI et Kimi Code, pour le SAST post-édition.\n")
        faults = _word_faults("README-SECURITY-SCAN-SETUP.md", old)
        assert len(faults) == 2, faults  # Copilot hérité, Gemini CLI supposé
        assert _word_faults("x.sh", "# claude and codex MEASURED, copilot " + "INHERITED (old)\n")

    def test_neg_words_a_negated_legend_is_not_judged_an_affirmed_one_still_is(self):
        # Built, never typed (this file is judged too). FB6 writes « non mesuré sur <hôte> » per host.
        mot = "mesur" + "é sur Gemini CLI"
        assert _word_faults("x.md", "COVERAGE DEGRADED — parallélisme non " + mot + " : lots\n") == []
        assert _word_faults("x.md", "devs not " + "measur" + "ed on Gemini CLI\n") == []
        assert _word_faults("x.md", "le hook est " + mot + "\n"), "an affirmed legend must still be judged"

    # =========================================================================
    # NEGATIVE CONTROLS — one mutation per cell class, on copy.deepcopy in
    # MEMORY, never on disk. Each asserts the mutation LANDED (touched) before it
    # asserts the rule reddens, and the reddening names <host>/<column>.
    # =========================================================================

    def _row(self, host):
        return next(r for r in HOSTS if r[0] == host)

    def test_neg_1_removing_the_stop_entry_reddens(self):
        row = self._row("Codex")
        obj = copy.deepcopy(_load(row[1]))
        before = len(_semgrep_entries(obj, row[2], row[5], None))
        for block in obj["hooks"][row[5]]:
            block["hooks"] = [h for h in block.get("hooks", [])
                              if "semgrep-scan.sh" not in str(h.get("command", ""))]
        after = len(_semgrep_entries(obj, row[2], row[5], None))
        assert before == 1 and after == 0, "mutation did not remove the Stop entry"
        assert any("Codex/stop" in m for m in _violations(row, obj))

    def test_neg_2_removing_marker_on_a_nonclaude_post_leg_reddens(self):
        row = self._row("Codex")
        obj = copy.deepcopy(_load(row[1]))
        touched = 0
        for block in _nested_blocks(obj, row[3], row[4]):
            for h in block.get("hooks", []):
                if "semgrep-scan.sh" in str(h.get("command", "")):
                    h["command"] = h["command"].replace("AGENTS_HOOK_HOST=codex ", "")
                    touched += 1
        assert touched, "the negative control mutated nothing"
        assert any("Codex/marker" in m for m in _violations(row, obj))

    def test_neg_3_adding_marker_on_claude_reddens_the_absent_cell(self):
        row = self._row("Claude Code")
        obj = copy.deepcopy(_load(row[1]))
        touched = 0
        for block in _nested_blocks(obj, row[3], row[4]):
            for h in block.get("hooks", []):
                if "semgrep-scan.sh" in str(h.get("command", "")):
                    h["command"] = "AGENTS_HOOK_HOST=claude " + h["command"]
                    touched += 1
        assert touched, "the negative control mutated nothing"
        assert any("Claude Code/marker" in m for m in _violations(row, obj))

    def test_neg_4_removing_the_windows_key_reddens(self):
        row = self._row("Codex")
        obj = copy.deepcopy(_load(row[1]))
        touched = 0
        for block in _nested_blocks(obj, row[3], row[4]):
            for h in block.get("hooks", []):
                if "semgrep-scan.sh" in str(h.get("command", "")) and "commandWindows" in h:
                    del h["commandWindows"]
                    touched += 1
        assert touched, "the negative control mutated nothing"
        assert any("Codex/windows" in m for m in _violations(row, obj))

    def test_neg_5_removing_the_hook_token_reddens(self):
        row = self._row("Codex")
        obj = copy.deepcopy(_load(row[1]))
        touched = 0
        for block in _nested_blocks(obj, row[3], row[4]):
            for h in block.get("hooks", []):
                if "semgrep-scan.sh" in str(h.get("command", "")):
                    h["command"] = h["command"].replace(" --hook", "")
                    touched += 1
        assert touched, "the negative control mutated nothing"
        assert any("Codex/post" in m for m in _violations(row, obj))

    def test_neg_6_stop_entry_citing_event_post_reddens(self):
        row = self._row("Codex")
        obj = copy.deepcopy(_load(row[1]))
        touched = 0
        for block in obj["hooks"][row[5]]:
            for h in block.get("hooks", []):
                if "semgrep-scan.sh" in str(h.get("command", "")):
                    h["command"] = h["command"].replace("--event=stop", "--event=post")
                    if "commandWindows" in h:
                        h["commandWindows"] = h["commandWindows"].replace("'--event=stop'", "'--event=post'")
                    touched += 1
        assert touched, "the negative control mutated nothing"
        assert any("Codex/stop" in m for m in _violations(row, obj))

    def test_neg_7_flat_entry_named_timeout_reddens(self):
        row = self._row("GitHub Copilot")
        obj = copy.deepcopy(_load(row[1]))
        touched = 0
        for h in obj["hooks"][row[3]]:
            if "semgrep-scan.sh" in str(h.get("bash", "")) and "timeoutSec" in h:
                h["timeout"] = h.pop("timeoutSec")
                touched += 1
        assert touched, "the negative control mutated nothing"
        assert any("GitHub Copilot/budget" in m for m in _violations(row, obj))

    def test_neg_8_reinjecting_the_old_line_reddens_the_legend(self):
        mutated = _header_text() + "\n# AS OF THIS COMMIT NO HOST INVOKES IT YET\n"
        assert "NO HOST INVOKES IT YET" in mutated, "the negative control mutated nothing"
        assert _legend_violations(mutated)

    def test_neg_9_removing_a_permissions_allow_line_reddens(self):
        row = self._row("Claude Code")
        obj = copy.deepcopy(_load(row[1]))
        allow = obj["permissions"]["allow"]
        target = "Bash(bash .agents/security/semgrep-scan.sh:*)"
        assert target in allow
        allow.remove(target)
        assert target not in obj["permissions"]["allow"], "the negative control mutated nothing"
        assert any("Claude Code/permissions" in m for m in _violations(row, obj))

    def test_neg_10_reducing_the_matcher_to_write_reddens(self):
        row = self._row("Claude Code")
        obj = copy.deepcopy(_load(row[1]))
        touched = 0
        for block in obj["hooks"][row[3]]:
            if _matcher_covers(block.get("matcher", ""), "Edit") and any(
                "semgrep-scan.sh" in str(h.get("command", "")) for h in block.get("hooks", [])
            ):
                block["matcher"] = "Write"
                touched += 1
        assert touched, "the negative control mutated nothing"
        assert not _matcher_covers("Write", "Edit"), "split must not cover Edit"
        assert any("Claude Code/post" in m for m in _violations(row, obj))

    def test_neg_11_duplicating_an_entry_reddens(self):
        row = self._row("Codex")
        obj = copy.deepcopy(_load(row[1]))
        touched = 0
        for block in _nested_blocks(obj, row[3], row[4]):
            for h in list(block.get("hooks", [])):
                if "semgrep-scan.sh" in str(h.get("command", "")):
                    block["hooks"].append(copy.deepcopy(h))
                    touched += 1
                    break
            if touched:
                break
        assert touched, "the negative control mutated nothing"
        assert len(_semgrep_entries(obj, row[2], row[3], row[4])) == 2
        assert any("Codex/post" in m for m in _violations(row, obj))


def test_le_changelog_vivant_est_juge_et_l_historique_fige_ne_l_est_pas():
    """T-01M4ZWNEDCJCNFF4HWQEWZX1J0 (r6) : l'exemption du juge d'arbre passe de CHANGELOG.md,
    devenu le journal VIVANT, a docs/HISTORIQUE-0.1.0.md, fige par empreinte (test_changelog_format) :
    une legende qui y vieillit est un rappel date, et rougirait un fichier interdit d'edition.
    C'est une protection contre le vieillissement, pas la correction d'un rouge mesure sur la copie."""
    assert not "CHANGELOG.md".startswith(_HISTORIQUE)
    assert "docs/HISTORIQUE-0.1.0.md".startswith(_HISTORIQUE)


if __name__ == "__main__":  # pragma: no cover - manual run convenience
    raise SystemExit(pytest.main([__file__, "-v"]))
