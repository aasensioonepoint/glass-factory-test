# Python conventions — canonical (shared by Claude Code, Codex, Copilot)

Precedence: a team convention ingested for this stack (`docs/tech/<stack>/`, listed in
`.agents/state/index/CUSTOM_DOCS.md`) wins over this sheet where the two contradict; where they do
not, both apply.

- Type hints mandatory on public functions; run the type checker if the project configures one.
- Prefer stdlib dataclasses over raw dicts across module boundaries. In the kit's own repository pydantic is not used since 2026-09-21 (`.agents/vendor/cadre/` is stdlib-only by contract; `agentic_v3/models/`, later `.agents/vendor/agentic_v3/models/`, ported to dataclasses) — do not reintroduce it there. An adopting project chooses its own.
- No bare `except:`; catch specific exceptions. Order branches most-specific FIRST — a broad
  tuple subsumes what precedes it (`FileNotFoundError` ⊂ `OSError`; `UnicodeDecodeError` and
  `json.JSONDecodeError` ⊂ `ValueError`), so a mis-ordered handler silently swallows the case
  you meant to name.
- A default argument is evaluated at IMPORT, not at call time. Anything that can change between
  import and call (a port, a resolved root, an identity) is resolved in the function body.
- `os.replace` is not enough for atomicity under a concurrent reader on Windows (measured 69-81 %
  failure): the write-then-replace recipe retries with a bounded backoff. `os.open(O_APPEND)` is
  not atomic across processes there either — one writer per file, or a lock.
- Use the test runner detected from `pyproject.toml`, `pytest.ini`, or existing tests. Run it
  bare, the way CI does: a hand-picked directory list is a different scope than the gate.
- A test that injects a clock stamps EVERY temporal fact it fabricates on that same clock
  (mtimes, file dates, timestamps). Mixing an injected clock with `time.time()` produces a
  verdict that depends on the hour of the day.
- A test must be able to fail: assert only the property under test, never the layout around it,
  and on data that CAN match. Check non-vacuity by mutating the code and watching it go red.
- On Windows, temp-fixture teardown can fail on handles still held (git, antivirus): tolerate
  cleanup errors, and never let an assertion depend on cleanup having succeeded.
- A test that patches state on a shared module (e.g. `subprocess.run`) does it via
  `mock.patch.object(...)` or `monkeypatch.setattr(...)`, never a bare assignment
  (`mod.subprocess.run = ...`): a bare assignment mutates the process-wide singleton and
  poisons every test collected afterward. The root conftest's autouse net catches leaks — its
  "restore" side is cited as CURRENT behavior rather than a guarantee: whether the net should
  keep repairing or only detect is still undecided.
- Check `.agents/state/index/CUSTOM_DOCS.md` for ingested team conventions on this stack.

## File size — 1600 lines per `.py`

- A `.py` file holds at most **1600 lines**, counted the way `wc -l` counts them (newline characters). Past that, split it into modules the original file imports. Motive: a decision of the kit's pilot (2026-09-26), raised to 1600 on 2026-10-04; this sheet invents no other.
- Scope. In the kit's own repository the limit is held by a ratchet bench, `.agents/evals/test_python_file_length.py`, which is **not shipped**: an adopting project receives the limit as a convention and holds it however it chooses. The files already past 1600 lines on the day the limit was raised are listed in `python_file_length_cliquet.json` (written by the bench's own commands, `--initialiser` and `--resserrer`), each with its size as its ceiling.
- Pilot derogations. A file stays above 1600 lines only by a decision of the pilot that names it. A derogation is one entry of the bench's `DEROGATIONS` table — the file's path, the id of the pilot's decision, and the ceiling that decision grants (the file's size when it lands) — and nothing else grants one: being past 1600 when the list is generated makes a file listed debt, never a derogation, and a derogated file never enters the list, whether it or the bench lands first. The bench holds a derogated file to its ceiling in every mode; until the file exists or passes 1600, the entry waits.
- Until the bench's `MODE` is switched to `bloquer` (a commit, never a date the bench reads), a size fault on a file the bench names as tolerated (the files that plans approved before the bench were already writing) — past 1600, above or below its ceiling, back to 1600 or fewer — is reported as a pytest warning and does not fail; a damaged list (a dead entry, a changed origin, a ceiling above it) fails in every mode.
- What the bench holds once its `MODE` is `bloquer`: a file off the list never passes 1600 lines; a listed file never passes its ceiling, and when it shrinks the ceiling has to follow it down (`--resserrer`, which prints each ceiling it lowers and each entry it removes), so a gain is never given back silently; a listed file back to 1600 lines or fewer leaves the list for good; no file joins the list, and no ceiling exceeds the size recorded on the day the list was sealed, which a hash held in the bench seals.
- What it does not hold: raising a ceiling back up to that recorded size, listing a file that left, re-baselining the whole list (putting the seal marker back in the bench, running `--initialiser` again, pasting the new hash), adding a path to the bench's list of tolerated files, or adding or raising a derogation — each is a hand edit of the state file or of the bench, which the bench does not refuse; a reviewer reads it in the diff. The bench checks a derogation's form, never that the decision it cites exists.
- Being listed is a frozen debt, never an exemption: splitting stays the way out.

## Style, I/O and subprocess

These rules are applied at review; a linter or type checker is the adopting project's own choice, and nothing below claims that one runs.

- PEP 8 and its naming: `snake_case` for functions and variables, `PascalCase` for classes, `UPPER_CASE` for constants. Imports at the top of the file, grouped stdlib / third-party / local, no `from x import *`.
- `pathlib.Path` rather than `os.path` in new code.
- Every text I/O names its encoding: `open(..., encoding="utf-8")`, `read_text` / `write_text`, `subprocess` in text mode. A write that must stay LF-only on every platform uses `write_bytes` or `newline="\n"`: `write_text` alone turns LF into CRLF on Windows.
- `subprocess`: arguments as a list, never `shell=True`, no value interpolated into a shell string; `check=` stated or the return code read; `timeout=` on anything that can hang.
- Never `eval` or `exec` on data, never `pickle` on input you do not trust, `yaml.safe_load` only. One named exemption, bounded to the kit's own `tasks.py` and not a precedent: its `_charger_parties` runs the kit's own source parts with `exec`.
- Libraries log through `logging.getLogger(__name__)` with lazy arguments (`log.info("x %s", v)`), never an f-string in the call and never `print`; a command-line entry point may `print` its result. No secret or credential reaches a log call.

## Coverage measurement

- Measure the SAME scope the gate runs. CI runs `python -m pytest` bare, so a hand-picked
  directory list yields a figure about a different program than the one being gated:
  `python -m coverage run -m pytest`, then `python -m coverage report`.
- The figure is REPORTED, never gated. The dev agent carries it in its `CHECKS` line
  (`coverage=…`) or writes `unmeasured: <reason>` — no coverage tool installed, a scope the
  plan did not name, a run that did not complete. A figure silently omitted reads as a
  measurement that was taken and found unremarkable, which is the one thing it is not.
- **NO THRESHOLD IS SET HERE, AND THE ABSENCE IS THE DECISION.** A number written into this
  sheet would be a commitment made on a codebase nobody has measured — this kit has never seen
  the adopting project's test suite. A project that HAS measured its own floor writes that
  floor into its own tool configuration (`pyproject.toml`, `.coveragerc`), where the runner can
  enforce it and where it moves with the project. A threshold living in a shared convention
  sheet is either ignored or gamed, and in both cases it stops describing anything.
- Coverage is a LOCATOR, not a verdict: it shows lines nothing executed. It cannot show an
  executed line whose assertion proves nothing, which is the defect this repo keeps measuring.
