"""The dev defs carry the judge's checklist, played before handing back.

CE QU'IL JUGE. Les 15 defs dev-mono, dev-multi, frontend-fidelity (5 hotes)
portent la section « Before you hand back » : neuf points NUMEROTES, chacun
ancre par son marqueur de forme d'hote et porteur de ses atomes DANS SA PORTEE,
les atomes de section (clone hors depot, etat COMMITE, clone `--no-checkout`
puis `remote remove origin` puis `sparse-checkout set` puis `checkout` du sha
livre DANS CET ORDRE, une mesure a la fois, aucune porte, aucun VERDICT,
jamais verify.sh, jamais | tail), le format rejouable de `PROOFS:` et l'ancre
`PROOFS:` propre a la forme ; sur les 3 defs Gemini, le point non atteint au
plafond de tours NOMME sous `PROOFS:` (C26, S-01M55ZZPKNHTQ2S2CX3VG13EDG).
CHEZ L'ADOPTANT CE BANC JUGE (aucun saut) : une def de dev reecrite par
l'adoptant est un defaut de l'adoptant (S-01M550PZ58QH3HQ4HNXGHJR7R1) ;
test_exec_securite_parallele et test_exec_critic_mandat y sautent, regle
differente par decision (S-01M56VW5K29XNEPA04C83RHGY0). Le texte est compare APLATI : blancs reduits, backticks et ** retires,
tiret cadratin lu comme un tiret ASCII (la def Codex est en ASCII).
LES INTERDITS NE MORDENT QUE SUR UNE PRESCRIPTION : le point 8 NOMME
`git -C <clone> reset --hard` comme CONTROLE de sonde (« came back refused ») ;
cette seule mention est retiree avant le controle des interdits, toute autre
occurrence de `reset --hard` rougit.
CE QU'IL NE PROUVE PAS. Un point present n'est pas une regle obeie ; un dev
peut ecrire `PROOFS:` sans l'avoir joue — exec-critic rejoue. Les clauses non
atomisees (survivors nommes au plan) ne sont pas tenues ici. Prototype : plan
r3 de T-01M551R7CP (sha256 f9486ece), amende par les reserves C19-C23 du
plan-critic.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DEFS = {
    **{f"{h}/{n}": (ROOT / h / "agents" / f"{n}.md", "md")
       for h in (".claude", ".gemini", ".kimi-code") for n in ("dev-mono", "dev-multi", "frontend-fidelity")},
    **{f".codex/{n}": (ROOT / ".codex" / "agents" / f"{n}.toml", "codex")
       for n in ("dev-mono", "dev-multi", "frontend-fidelity")},
    **{f".github/{n}": (ROOT / ".github" / "agents" / f"{n}.agent.md", "copilot")
       for n in ("dev-mono", "dev-multi", "frontend-fidelity")},
}
MARK = {"md": r"(?m)^{n}\. \*\*", "codex": r"(?m)^{n}\. ", "copilot": r"\({n}\) "}
CLOSE = re.compile(r"Capture (?:each output|outputs) whole")
CONTROL = "git -C <clone> reset --hard came back refused"
PROBE = ("Every command you prescribe is PROBED, never executed: fed to your host's Bash guard as the payload"
         ' {"tool_name":"Bash","tool_input":{"command":"<cmd>"}} with AGENTS_EVENTS_DIR on a mktemp -d directory'
         ' - refused means rc 2 and BLOCKED (Claude Code) or "permissionDecision":"deny" on stdout (the other hosts),'
         f" and an allowed counts only once {CONTROL} through the same payload;"
         " a push is never yours to run or judge: mark it addressed to the executor (.githooks/pre-push judges"
         " nothing: with no VERIFY_STAMP it refuses every non-delete ref and admits every delete);"
         " a command refused by the agent guard but addressed"
         " to the pilot or the executor is marked as such, not rewritten")
ITEMS = {
    1: ("acceptance criterion", "verdict line", "real output", "writes outside a temp dir or reaches the network",
        "do not run it, say so"),
    2: ("mutant", "per witness you added or changed", "no cap", "in the clone", "git -C <clone> restore -- <file>",
        "survivor under PROOFS:, or gets a test"),
    3: ("real channel", "stdin", "through the real entry point"),
    4: ("rollback", "in the clone", "git -C <clone> checkout -q <delivered sha>"),
    5: ("git grep", "whole tree", "write-set", "agree"),
    6: ("adopter", "in the clone", "git -C <clone> rm -q .agents/IS_THE_KIT",
        "git -C <clone> restore --staged --worktree -- .agents/IS_THE_KIT", "skips"),
    7: ("git diff --name-only <base> <delivered sha>", "git status --porcelain empty", "no secret",
        "no test weakened"),
    8: (PROBE, "rewritten, never prescribed"),
    9: ("Blind spot", "never empty"),
}
# S-01M55YBCZFVVCBDYH7QJ8X6XCC : `origin` retire JUSTE apres le clone — sinon un push depuis le clone
# atteint le depot juge (admis par les 5 gardes, mesure).
CLONE_ORDER = ("git clone -q --no-checkout <repo> <clone>", "git -C <clone> remote remove origin",
               "git -C <clone> sparse-checkout set <dirs>", "git -C <clone> checkout -q <delivered sha>")
SPARSE, CHECKOUT = CLONE_ORDER[2], CLONE_ORDER[3]
# C26 : Gemini coupe un sous-agent au plafond de tours ; ce qui n'est pas atteint est NOMME.
GEMINI_ATOMS = ("an item not reached before your turn cap (max_turns, or the loader's default) included",)
SECTION_ATOMS = (
    "throwaway clone outside the repository", "cloned from your COMMITTED delivery", *CLONE_ORDER,
    "created once and reused", "You PRODUCE the evidence", "anything skipped", "one measurement at a time",
    "none while a gate runs", "pgrep -f '^bash [^ ]*core-scripts/verify[.]sh' empty first", "no VERDICT",
    "exec-critic still replays whatever it chooses", "never | tail or | head", "never verify.sh",
)
FORMAT_ATOMS = ("mutant <file:line> <old", "<witness command>", "fault <command>")
FORBIDDEN = ("reset --hard", "clean -f", "at most three mutants", "inside the repository", "run verify.sh",
             "refuses every ref - no stamp")
PROOFS_LINES = ("- criterion", "- mutant", "- fault", "- rollback:", "- surfaces:", "- adopter:", "- probe:", "- scope:")
PROOFS_BLOCK = re.compile(r"(?m)^PROOFS:\n" + "".join(rf"{re.escape(x)}[^\n]*\n" for x in PROOFS_LINES))
PROOFS_ANCHOR = {
    "codex": "report under PROOFS:, one line per item",
    "copilot": "Under PROOFS: in your report, one line per item",
    "md-ff": "the PROOFS: block below",
}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("`", "").replace("**", "").replace("—", "-"))


def _loose(atom: str) -> str:
    """Regex matching the atom in RAW text, backticks and ** allowed anywhere, — read as -."""
    out = []
    for ch in atom:
        if ch == " ":
            out.append(r"[`*\s]+")
        elif ch == "-":
            out.append(r"[-—][`*]*")
        else:
            out.append(re.escape(ch) + r"[`*]*")
    return "".join(out)


def section(text: str) -> tuple[int, int, int] | None:
    start = text.find("Before you hand back")
    if start < 0:
        return None
    m = CLOSE.search(text, start)
    if not m:
        return None
    eol = text.find("\n", m.end())
    return (start, m.start(), eol if eol >= 0 else len(text))


def spans(text: str, form: str) -> dict[int, tuple[int, int]] | str:
    sec = section(text)
    if sec is None:
        return "section"
    lo, hi, _ = sec
    starts = {}
    for n in ITEMS:
        hits = [m.start() for m in re.finditer(MARK[form].format(n=n), text[lo:hi])]
        if len(hits) != 1:
            return f"point {n}"
        starts[n] = lo + hits[0]
    order = [starts[n] for n in sorted(ITEMS)]
    if order != sorted(order):
        return "order"
    ends = order[1:] + [hi]
    return {n: (starts[n], ends[i]) for i, n in enumerate(sorted(ITEMS))}


def clone_order_ok(intro: str) -> bool:
    """The intro clones WITHOUT checkout, narrows, THEN checks out the delivered sha."""
    at = -1
    for step in CLONE_ORDER:
        at = intro.find(step, at + 1)
        if at < 0:
            return False
    return True


def proofs_ok(text: str, key: str, form: str) -> bool:
    if form == "md":
        ok = bool(PROOFS_BLOCK.search(text))
        return ok and (PROOFS_ANCHOR["md-ff"] in _norm(text) if key.endswith("frontend-fidelity") else True)
    return PROOFS_ANCHOR[form] in _norm(text)


def prescriptions(flat: str) -> str:
    """The flat text minus the ONE named refusal control: what is left is prescribed."""
    return flat.replace(CONTROL, "")


def manquants(text: str, key: str, form: str) -> list[str]:
    out = []
    sp = spans(text, form)
    if isinstance(sp, str):
        out.append(sp)
    else:
        for n, (a, b) in sp.items():
            body = _norm(text[a:b])
            out += [f"point {n}: {atom[:40]}" for atom in ITEMS[n] if atom not in body]
        lo, _, end = section(text)
        sec = _norm(text[lo:end])
        out += [f"section: {atom}" for atom in SECTION_ATOMS if atom not in sec]
        if key.startswith(".gemini/"):
            out += [f"gemini: {atom}" for atom in GEMINI_ATOMS if atom not in _norm(text[lo:sp[1][0]])]
        if not clone_order_ok(_norm(text[lo:sp[1][0]])):
            out.append("section: clone order")
    flat = _norm(text)
    out += [f"format: {atom}" for atom in FORMAT_ATOMS if atom not in flat]
    if not proofs_ok(text, key, form):
        out.append("PROOFS")
    out += [f"forbidden: {f}" for f in FORBIDDEN if f in prescriptions(flat)]
    return out


def _read(key: str) -> tuple[str, str]:
    path, form = DEFS[key]
    return path.read_text(encoding="utf-8"), form


def test_population_is_the_fifteen_defs():
    assert len(DEFS) == 15
    forms = [f for _, f in DEFS.values()]
    assert (forms.count("md"), forms.count("codex"), forms.count("copilot")) == (9, 3, 3)
    for key, (path, _) in DEFS.items():
        assert path.is_file(), f"{key}: {path} missing"


@pytest.mark.parametrize("key", sorted(DEFS))
def test_def_carries_the_checklist(key):
    text, form = _read(key)
    assert manquants(text, key, form) == [], f"{key}: {manquants(text, key, form)}"


@pytest.mark.parametrize("n", sorted(ITEMS))
@pytest.mark.parametrize("key", sorted(DEFS))
def test_removing_a_whole_point_goes_red(key, n):
    text, form = _read(key)
    a, b = spans(text, form)[n]
    mutated = text[:a] + text[b:]
    assert mutated != text, "vacuous control"
    assert any(m.startswith(f"point {n}") for m in manquants(mutated, key, form)), f"{key}: point {n} removed, still green"


@pytest.mark.parametrize("key", sorted(DEFS))
def test_removing_the_proofs_anchor_goes_red(key):
    text, form = _read(key)
    if form == "md":
        mutated = PROOFS_BLOCK.sub("", text)
    else:
        mutated = re.sub(_loose(PROOFS_ANCHOR[form]), "", text)
    assert mutated != text, "vacuous control"
    assert "PROOFS" in manquants(mutated, key, form), f"{key}: PROOFS removed, still green"


@pytest.mark.parametrize("key", sorted(DEFS))
def test_an_atom_taken_out_of_its_place_goes_red(key):
    """The atom may survive ELSEWHERE in the def: only its point, its section or its def counts."""
    text, form = _read(key)
    sp = spans(text, form)
    lo, _, end = section(text)
    cases = [(f"point {n}: {atom[:40]}", a, b, atom) for n, (a, b) in sp.items() for atom in ITEMS[n]]
    cases += [(f"section: {atom}", lo, end, atom) for atom in SECTION_ATOMS]
    cases += [(f"format: {atom}", 0, len(text), atom) for atom in FORMAT_ATOMS]
    for label, a, b, atom in cases:
        moved = text[:a] + re.sub(_loose(atom), "X", text[a:b]) + text[b:]
        assert moved != text, f"{key}: vacuous control on {atom!r}"
        assert label in manquants(moved, key, form), f"{key}: {label!r} removed, still green"


@pytest.mark.parametrize("key", sorted(DEFS))
def test_checkout_before_narrowing_goes_red(key):
    """C23 — swap `sparse-checkout set` and the delivered-sha checkout in the intro."""
    text, form = _read(key)
    lo, intro_end = section(text)[0], spans(text, form)[1][0]
    intro = text[lo:intro_end]
    sparse, checkout = (re.search(_loose(x), intro) for x in (SPARSE, CHECKOUT))
    assert sparse and checkout and sparse.start() < checkout.start(), f"{key}: vacuous control"
    swapped = (intro[:sparse.start()] + checkout.group(0) + intro[sparse.end():checkout.start()]
               + sparse.group(0) + intro[checkout.end():])
    mutated = text[:lo] + swapped + text[intro_end:]
    assert mutated != text, "vacuous control"
    assert "section: clone order" in manquants(mutated, key, form), f"{key}: clone order swapped, still green"


@pytest.mark.parametrize("key", sorted(DEFS))
def test_origin_removed_late_goes_red(key):
    """S-01M55YBCZ — `remote remove origin` moved after the delivered-sha checkout: the clone keeps
    `origin` while measured, the order must go red."""
    text, form = _read(key)
    lo, intro_end = section(text)[0], spans(text, form)[1][0]
    intro = text[lo:intro_end]
    rm = re.search(_loose(CLONE_ORDER[1]) + r"[`*]*,\s+then\s+", intro)
    assert rm, f"{key}: vacuous control"
    moved = intro[:rm.start()] + intro[rm.end():]
    checkout = re.search(_loose(CHECKOUT), moved)
    assert checkout, f"{key}: vacuous control"
    moved = moved[:checkout.end()] + ", then git -C <clone> remote remove origin" + moved[checkout.end():]
    mutated = text[:lo] + moved + text[intro_end:]
    assert mutated != text and manquants(text, key, form) == [], "vacuous control"
    assert "section: clone order" in manquants(mutated, key, form), f"{key}: origin removed late, still green"


@pytest.mark.parametrize("key", sorted(k for k in DEFS if k.startswith(".gemini/")))
def test_gemini_turn_cap_taken_out_goes_red(key):
    """C26 — the turn-cap clause taken out of the Gemini intro goes red; present on no other host."""
    text, form = _read(key)
    mutated = re.sub(_loose(GEMINI_ATOMS[0]), "X", text)
    assert mutated != text, f"{key}: vacuous control"
    assert f"gemini: {GEMINI_ATOMS[0]}" in manquants(mutated, key, form), f"{key}: turn cap removed, still green"


def test_turn_cap_clause_is_gemini_only():
    """The clause names `max_turns`, a Gemini key: on another host it would be a false statement."""
    porteurs = sorted(k for k in DEFS if GEMINI_ATOMS[0] in _norm(_read(k)[0]))
    assert porteurs == sorted(k for k in DEFS if k.startswith(".gemini/")), porteurs


@pytest.mark.parametrize("bad", FORBIDDEN)
@pytest.mark.parametrize("key", sorted(DEFS))
def test_a_forbidden_phrase_goes_red(key, bad):
    text, form = _read(key)
    assert f"forbidden: {bad}" in manquants(text + f"\nx {bad} x\n", key, form)


@pytest.mark.parametrize("key", sorted(DEFS))
def test_the_refusal_control_is_named_not_prescribed(key):
    """C22 — the def NAMES `reset --hard` as the refused control (non-vacuity), which
    does not bite; the same verb prescribed anywhere else does."""
    text, form = _read(key)
    assert "reset --hard" in _norm(text), f"{key}: the control is absent, the exemption is untested"
    assert manquants(text + f"\n{CONTROL}\n", key, form) == []
    prescribed = text + "\nthen run git -C <clone> reset --hard before the next item\n"
    assert "forbidden: reset --hard" in manquants(prescribed, key, form)


def test_an_empty_population_goes_red():
    assert manquants("", "x", "md") != []
