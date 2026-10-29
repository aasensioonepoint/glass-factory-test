"""T-00000996 — a hook.deny carrying a lone surrogate is journaled, and every
reader of the day-file can still read it back.

Sibling of `test_events.py` (that file sits at its ratchet ceiling, so the
witness lives here). Defect measured on BASE 1400c645: `emit()` serializes with
`ensure_ascii=False`, then calls `.encode("utf-8")` twice — the cap measure in
`emit` and the payload in `_write_line`. A lone surrogate (U+D800..U+DFFF: a
`json.loads` of a `\\udXXX` escape, an `os.fsdecode` of a non-UTF-8 path)
makes both raise `UnicodeEncodeError`, the fail-open `except` swallows it, and
the event is LOST with no diagnostic: 0 lines for 3 emits.

The handler was chosen against the REAL readers, all four forms measured on a
disposable bench (write three surrogate events, then read them back):

* `surrogatepass` writes invalid UTF-8 bytes; the strict reader
  `dashboard_readers_base.read_new_records` counts every such line as malformed
  (records=0 malformed=3), so the dashboard loses them.
* `backslashreplace` (an ASCII JSON `\\udXXX` escape) is valid UTF-8 on disk,
  but `json.loads` turns it back into a lone surrogate. Then the dashboard's
  HTTP answer (`json.dumps(..., ensure_ascii=False).encode("utf-8")`) raises,
  and `event_store.ingest_once` RAISES `UnicodeEncodeError` on an envelope
  column (not a `sqlite3.Error`). The whole batch rolls back, so the line
  poisons every tick.
* `replace` (kept, as a belt) and `xmlcharrefreplace` both pass every reader.

But `replace` alone acts AFTER the redaction: a token cut by a surrogate no
longer matches its pattern, and the `?` stitched it back, 35 of 36 characters in
clear (critic-fable, batch 1). So `emit` first replaces WHOLE every `str` leaf
or dict key carrying a lone surrogate with `[SURROGATE NEUTRALISE]`, then
redacts: the line keeps its event, guard and rule; only the poisoned value goes.

So the witnesses below hold the property every reader needs: one line per emit,
strict UTF-8 on disk, parsed back with no surrogate left in any value, and no
cut token left in clear.
"""
from __future__ import annotations

import dataclasses
import errno
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

HERE = Path(__file__).resolve().parent


def _load(name: str, filename: str) -> Any:
    """Explicit-path load (events.py's import contract), under a name of its
    own so this file never replaces `test_events.py`'s `events` module."""
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


events = _load("_surrogate_events", "events.py")
readers_base = _load("_surrogate_readers_base", "dashboard_readers_base.py")

# Three placements: a low surrogate (the `surrogateescape` range) and a high one
# in `data`, and one in an ENVELOPE field — the column the store binds to SQLite.
_CASES = (
    {"guard": "protect-paths", "rule": "deny-low", "path": "a\udc80b"},
    {"guard": "protect-paths", "rule": "deny-high", "path": "x\ud800y"},
    {"guard": "protect-paths", "rule": "deny-envelope", "path": "p", "task": "T-\udcff"},
)
_MARQUEUR = "[SURROGATE NEUTRALISE]"  # the on-disk contract, spelled out
_COUPE = "ghp_" + "A" * 18 + "\udcff" + "A" * 18  # a GitHub token cut by a surrogate


@pytest.fixture()
def events_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    target = tmp_path / "events"
    monkeypatch.setenv("AGENTS_EVENTS_DIR", str(target))
    return target


def _day_bytes(events_dir: Path) -> bytes:
    return b"".join(f.read_bytes() for f in sorted(events_dir.glob("*.jsonl")))


def _has_surrogate(value: Any) -> bool:
    if isinstance(value, str):
        return any(0xD800 <= ord(char) <= 0xDFFF for char in value)
    if isinstance(value, dict):
        return any(_has_surrogate(k) or _has_surrogate(v) for k, v in value.items())
    if isinstance(value, list):
        return any(_has_surrogate(item) for item in value)
    return False


def _emit_cases() -> None:
    for fields in _CASES:
        events.emit("hook.deny", host="claude", **fields)


def test_surrogate_hook_deny_is_journaled(events_dir: Path) -> None:
    _emit_cases()
    lines = _day_bytes(events_dir).splitlines()
    assert len(lines) == len(_CASES), f"events lost: {len(lines)} line(s) for {len(_CASES)} emits"


def test_surrogate_line_is_strict_utf8_on_disk(events_dir: Path) -> None:
    _emit_cases()
    raw = _day_bytes(events_dir)
    assert raw, "nothing written"
    raw.decode("utf-8")  # strict: an invalid byte (surrogatepass) raises here


def test_strict_reader_parses_surrogate_free_records(events_dir: Path) -> None:
    """The dashboard's own reader (strict UTF-8), then its HTTP encoding."""
    _emit_cases()
    files = sorted(events_dir.glob("*.jsonl"))
    assert files, "nothing written"
    records: list[dict[str, Any]] = []
    for path in files:
        parsed, malformed = readers_base.read_new_records(path, 0)
        assert malformed == 0, f"{path.name}: {malformed} line(s) unreadable"
        records.extend(record for _offset, record in parsed)
    assert len(records) == len(_CASES)
    assert not _has_surrogate(records), "a lone surrogate survives the round trip"
    json.dumps(records, ensure_ascii=False).encode("utf-8")  # dashboard `_send_json`
    by_rule = {record["data"]["rule"]: record for record in records}
    assert by_rule["deny-low"]["data"]["path"] == _MARQUEUR
    assert by_rule["deny-high"]["data"]["path"] == _MARQUEUR
    assert by_rule["deny-envelope"]["task"] == _MARQUEUR
    assert {record["data"]["guard"] for record in records} == {"protect-paths"}


def test_compaction_reader_sees_surrogate_free_records(events_dir: Path) -> None:
    _emit_cases()
    files = sorted(events_dir.glob("*.jsonl"))
    records = [record for path in files for record in events._read_jsonl_records(path)]
    assert len(records) == len(_CASES)
    assert not _has_surrogate(records)


def test_valid_non_ascii_stays_raw_utf8(events_dir: Path) -> None:
    """The handler only touches what UTF-8 cannot encode: a valid accent is
    still written raw (`ensure_ascii=False` kept), never escaped or replaced."""
    events.emit("hook.deny", host="claude", guard="protect-paths", rule="r", path="café")
    raw = _day_bytes(events_dir)
    assert "café".encode("utf-8") in raw


def test_cut_token_is_never_written_in_clear(events_dir: Path) -> None:
    """The leaf is replaced WHOLE before the redaction, so no `?` can stitch the
    token back — and the event itself is still journaled."""
    events.emit("hook.deny", host="claude", guard="g", rule="r", path="insere " + _COUPE)
    raw = _day_bytes(events_dir)
    assert len(raw.splitlines()) == 1, "event lost"
    assert b"ghp_AAAA" not in raw, raw
    assert json.loads(raw)["data"]["path"] == _MARQUEUR


def test_cut_token_in_host_never_names_the_day_file(events_dir: Path) -> None:
    """F2 (critic-opus, binôme bis): `host` is an ENVELOPE key AND names the
    day-file, so `_sans_surrogates` must run over the whole `fields`. On 3b0d4cd4
    the cut token passed the redaction and `_sanitize_host` only swapped the
    surrogate for `_`: 36/36 token characters in a tracked file NAME."""
    events.emit("hook.deny", host=_COUPE, guard="g", rule="r", path="p")
    assert len(_day_bytes(events_dir).splitlines()) == 1, "event lost"
    names = [path.name for path in events_dir.iterdir()]
    assert not any("ghp_" in name for name in names), names


def test_sane_sibling_leaf_is_still_redacted(events_dir: Path) -> None:
    """Only the surrogate leaf becomes the marker: a sibling token is redacted."""
    events.emit("hook.deny", host="claude", guard="ghp_" + "C" * 36, rule="r", path=_COUPE)
    record = json.loads(_day_bytes(events_dir))
    assert record["data"]["guard"] == "[SECRET RÉDIGÉ:github_token]"
    assert record["data"]["path"] == _MARQUEUR


def test_cut_token_in_a_nested_key_is_neutralised(events_dir: Path) -> None:
    """`scan.sca` carries a per-ecosystem MAP: its caller-chosen keys reach the line."""
    events.emit("scan.sca", host="claude", status={_COUPE: "x", "npm": ("ok", 1)})
    raw = _day_bytes(events_dir)
    assert b"ghp_AAAA" not in raw, raw
    assert json.loads(raw)["data"]["status"] == {_MARQUEUR: "x", "npm": ["ok", 1]}


def test_sans_surrogates_keeps_container_types_and_non_str() -> None:
    """A tuple stays a tuple (as `rediger_arbre` keeps it), so a tuple KEY stays
    hashable; a KEY keeps its type: a `bytes` key is never decoded, so `json.dumps`
    refuses the line and counts it (T-00001133), while a `str` key is redacted by
    `rediger_arbre` (T-00001131). Only a `bytes` leaf becomes text (an invalid byte:
    the marker) and a `frozenset` a list; any other leaf (`1`, `None`, `...`) is untouched."""
    tree = {"k": ("a\udc80", 1, None), 7: ["ok", "b\ud800"], ("t\udc80",): 0,
            b"c": frozenset({b"\xff"}), "o": ...}
    want = {"k": (_MARQUEUR, 1, None), 7: ["ok", _MARQUEUR], (_MARQUEUR,): 0,
            b"c": [_MARQUEUR], "o": ...}
    assert events._sans_surrogates(tree) == want


class _Texte:
    """A non-`str` object whose text is reached only through `__str__`."""

    def __init__(self, texte: str) -> None:
        self.texte = texte

    def __str__(self) -> str:
        return self.texte


@dataclasses.dataclass
class _Repr:
    """Its `str()` is a repr: a lone surrogate comes out as six ASCII characters."""

    p: str


_LONG = "y" * 400  # past the 300 cap, so 645846e8 coerces the leaf in `_build_record`


@pytest.mark.parametrize("leaf", [
    pytest.param(("ghp_" + "C" * 36 + _LONG).encode(), id="bytes"),
    pytest.param(bytearray(("ghp_" + "C" * 36 + _LONG).encode()), id="bytearray"),
    pytest.param(b"ghp_" + b"E" * 18 + b"\xff" + b"E" * 18 + _LONG.encode(), id="bytes-cut"),
    pytest.param(frozenset({_COUPE + _LONG}), id="frozenset-cut"),
])
def test_bytes_and_sets_are_written_redacted(events_dir: Path, leaf: Any) -> None:
    """T-00001132: on 645846e8 `_build_record` coerced a capped non-`str` by `str()`
    and cut it AFTER the redaction, which leaves non-`str` leaves alone: the repr
    (`b'..'`, `{'..'}`) carried the token in clear. A `bytes` is now decoded and a
    set listed BEFORE the neutralisation, then redacted: a valid token is redacted,
    one cut by an invalid byte or a lone surrogate becomes the marker WHOLE."""
    events.emit("hook.deny", host="claude", guard="g", rule="r", path=leaf)
    raw = _day_bytes(events_dir)
    assert len(raw.splitlines()) == 1, "event lost"
    assert b"ghp_" not in raw, raw[:200]


@pytest.mark.parametrize("leaf", [
    pytest.param(_Texte("ghp_" + "B" * 36 + "y" * 5000), id="object"),
    pytest.param(_Texte(_COUPE + _LONG), id="object-cut"),
    pytest.param(_Repr(_COUPE + _LONG), id="dataclass-cut"),
    pytest.param([_Repr("ghp_" + "B" * 36 + _LONG)], id="nested-in-list"),
    pytest.param({"p": _Repr("ghp_" + "B" * 36 + _LONG)}, id="nested-in-dict"),
    pytest.param({("ghp_" + "K" * 36,): _LONG}, id="tuple-key-under-cap"),
])
def test_other_objects_are_never_made_text(events_dir: Path, leaf: Any) -> None:
    """T-00001132: an arbitrary object is REFUSED, never coerced by `str()`. On
    645846e8 its text was cut past the redaction (the token in clear), and a
    generic `str()` before it is no fix: a repr re-escapes a lone surrogate into
    ASCII `\\udcff`, past the neutralisation (measured: 36/36 in clear). Same at
    any depth: on 2bc025a0 the cap's `str()` of a list or dict reprised a nested
    object, or a tuple key, past the redaction."""
    events.emit("hook.deny", host="claude", guard="g", rule="r", path=leaf)
    raw = _day_bytes(events_dir)
    assert b"ghp_" not in raw, raw[:200]
    assert raw == b"", "an object was made text"


@pytest.mark.parametrize("leaf, want", [
    pytest.param(b"x", "x", id="bytes"),
    pytest.param({"x"}, ["x"], id="set"),
    pytest.param(frozenset({"x"}), ["x"], id="frozenset"),
])
def test_bytes_and_set_leaves_are_journaled(events_dir: Path, leaf: Any, want: Any) -> None:
    """T-00001133: on 645846e8 such a leaf crossed `rediger_arbre` intact and died in
    `json.dumps`, under the outer `except`: 0 lines, diagnostics unchanged."""
    events.emit("hook.deny", host="claude", guard="g", rule="r", path=leaf)
    lines = _day_bytes(events_dir).splitlines()
    assert len(lines) == 1, "event lost"
    assert json.loads(lines[0])["data"]["path"] == want


def test_bytes_leaf_carrying_a_token_is_redacted(events_dir: Path) -> None:
    """T-00001133: the `bytes` is written as text, so it is redacted like a `str`."""
    events.emit("hook.deny", host="claude", guard="g", rule="r", path=b"ghp_" + b"C" * 36)
    raw = _day_bytes(events_dir)
    assert len(raw.splitlines()) == 1, "event lost"
    assert b"ghp_CCCC" not in raw, raw
    assert json.loads(raw)["data"]["path"] == "[SECRET RÉDIGÉ:github_token]"


def _lost() -> int:
    return events.get_diagnostics().get("lost_events", 0)


@pytest.mark.parametrize("kind, fields", [
    pytest.param("hook.deny", {"path": _Texte("p")}, id="object"),
    pytest.param("scan.sca", {"status": {("a",): 1}}, id="tuple-key"),
    pytest.param("scan.sca", {"status": {b"ghp_" + b"D" * 36: 1}}, id="bytes-key"),
    pytest.param("hook.deny", {"path": [_Repr("ghp_" + "B" * 36 + _LONG)]}, id="nested-under-cap"),
])
def test_a_refused_line_is_counted(events_dir: Path, kind: str, fields: dict[str, Any]) -> None:
    """T-00001133: what stays non-JSON is still refused by `json.dumps` (a `bytes`
    or tuple key is never made text; a `str` key is redacted, see below), but no
    longer in silence."""
    before = _lost()
    events.emit(kind, host="claude", **fields)
    raw = _day_bytes(events_dir)
    assert raw == b"" and b"ghp_" not in raw, raw
    assert _lost() == before + 1, "a line was lost without a diagnostic"


def test_a_failed_write_is_counted(events_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The counter is the outer `except` itself: an I/O failure counts too."""

    def _boom(*_a: Any, **_k: Any) -> int:
        raise OSError("simulated disk full")

    monkeypatch.setattr(events.os, "open", _boom)
    before = _lost()
    assert events.emit("hook.deny", host="claude", guard="g", rule="r", path="p") is None
    assert _lost() == before + 1


def test_a_str_key_carrying_a_token_is_redacted(events_dir: Path) -> None:
    """T-00001131 (pins the docstrings of `_sans_surrogates` and of the tests
    above): a `str` KEY is redacted by `rediger_arbre` and the line is written; a
    `bytes` key is the refused, counted case (`test_a_refused_line_is_counted`)."""
    before = _lost()
    events.emit("scan.sca", host="claude", status={"ghp_" + "K" * 36: 1})
    raw = _day_bytes(events_dir)
    assert len(raw.splitlines()) == 1, "event lost"
    assert b"ghp_" not in raw, raw
    assert json.loads(raw)["data"]["status"] == {"[SECRET RÉDIGÉ:github_token]": 1}
    assert _lost() == before


def test_a_short_write_resumes_at_the_remainder(
    events_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T-00001133: on 63f63f35 `_write_line` ignored `os.write`'s count — a short
    write left half a line (154/308 bytes, no newline), neither raised nor
    counted, and the next emit would append onto it. The rest is now written
    from the REMAINDER: one whole line, never the prefix twice."""
    real_write = os.write
    sizes: list[int] = []

    def _short_then_real(fd: int, data: Any) -> int:
        sizes.append(len(data))
        return real_write(fd, bytes(data)[: len(data) // 2] if len(sizes) == 1 else data)

    monkeypatch.setattr(events.os, "write", _short_then_real)
    before = _lost()
    events.emit("hook.deny", host="claude", guard="g", rule="r", path="p")
    raw = _day_bytes(events_dir)
    assert raw.endswith(b"\n"), f"half a line on disk: {len(raw)} bytes"
    assert len(raw.splitlines()) == 1 and raw.count(b'"kind"') == 1, raw
    assert json.loads(raw)["data"]["path"] == "p"
    assert sizes == [sizes[0], sizes[0] - sizes[0] // 2], sizes  # the remainder, never the prefix
    assert _lost() == before


@pytest.mark.parametrize("prior", [0, 1], ids=["empty-day-file", "after-a-line"])
def test_a_failed_write_leaves_no_half_line(
    events_dir: Path, monkeypatch: pytest.MonkeyPatch, prior: int
) -> None:
    """T-00001133 (binôme bis): on 231bda6d a short write then ENOSPC left half a
    line with no newline, and the next emit was welded onto it: 1 line on disk, 0
    readable, the second event lost WITHOUT being counted. `_write_line` now cuts
    its own bytes back to the size it found: every line whole, and the `borne`
    (A-T1) still rides the first line of the day-file, never a lost one."""
    for _ in range(prior):
        events.emit("hook.deny", host="claude", guard="g", rule="r0", path="p")
    real_write = os.write
    calls: list[int] = []

    def _half_then_enospc(fd: int, data: Any) -> int:
        calls.append(len(data))
        if len(calls) > 1:
            raise OSError(errno.ENOSPC, "simulated disk full")
        return real_write(fd, bytes(data)[: len(data) // 2])

    before = _lost()
    with mock.patch.object(events.os, "write", _half_then_enospc):
        events.emit("hook.deny", host="claude", guard="g", rule="r1", path="p")
    assert _lost() == before + 1 and len(calls) == 2, calls
    events.emit("hook.deny", host="claude", guard="g", rule="r2", path="p")
    raw = _day_bytes(events_dir)
    assert raw.endswith(b"\n") and raw.count(b'"kind"') == prior + 1, raw
    records = [json.loads(line) for line in raw.splitlines()]  # no half line
    assert [r["data"]["rule"] for r in records] == ["r0"] * prior + ["r2"]
    assert ["borne" in r for r in records] == [True] + [False] * prior, records


def test_an_interrupt_mid_line_leaves_no_half_line(events_dir: Path) -> None:
    """T-00001133 (binôme ter, critic-opus R3): on 95df5a87 `_write_line` cut its
    bytes back on `OSError` only — half a line then a `KeyboardInterrupt` stayed on
    disk and the next emit welded onto it (1 line, unreadable, `lost_events`
    unchanged). Any exception now cuts back; the interrupt still propagates, uncounted."""
    real_write = os.write
    calls: list[int] = []

    def _half_then_interrupt(fd: int, data: Any) -> int:
        calls.append(len(data))
        if len(calls) > 1:
            raise KeyboardInterrupt
        return real_write(fd, bytes(data)[: len(data) // 2])

    before = _lost()
    patch = mock.patch.object(events.os, "write", _half_then_interrupt)
    with patch, pytest.raises(KeyboardInterrupt):
        events.emit("hook.deny", host="claude", guard="g", rule="r1", path="p")
    assert _lost() == before and len(calls) == 2, calls
    events.emit("hook.deny", host="claude", guard="g", rule="r2", path="p")
    raw = _day_bytes(events_dir)
    records = [json.loads(line) for line in raw.splitlines()]  # no half line
    assert [r["data"]["rule"] for r in records] == ["r2"] and "borne" in records[0], raw


def test_an_interrupt_after_the_last_write_keeps_the_whole_line(events_dir: Path) -> None:
    """T-00001133 (security LOW-1, S-00004013): an interrupt delivered at the head of
    `while reste:` AFTER the last complete `os.write` — where CPython runs a signal
    handler — met a cut-back guard that holds for an EMPTY remainder: on c6aee28a the
    COMPLETE line was cut, uncounted. A remainder is now required: the line stays."""
    real_write = os.write

    class _Reste:  # `memoryview` stand-in: `while reste` raises ONCE, when nothing remains
        leve = False

        def __init__(self, b: Any) -> None:
            self.b = b

        def __getitem__(self, k: Any) -> "_Reste":
            return _Reste(self.b[k])

        def __len__(self) -> int:
            return len(self.b)

        def __bool__(self) -> bool:
            if not self.b and not _Reste.leve:  # once: the guard's own test reads it after
                _Reste.leve = True
                raise KeyboardInterrupt
            return bool(self.b)

    events.emit("hook.deny", host="claude", guard="g", rule="r0", path="p")
    before = _lost()
    vue = mock.patch.object(events, "memoryview", _Reste, create=True)
    ecrit = mock.patch.object(events.os, "write", lambda fd, d: real_write(fd, d.b))
    with vue, ecrit, pytest.raises(KeyboardInterrupt):
        events.emit("hook.deny", host="claude", guard="g", rule="r1", path="p")
    assert _Reste.leve and _lost() == before
    records = [json.loads(line) for line in _day_bytes(events_dir).splitlines()]
    assert [r["data"]["rule"] for r in records] == ["r0", "r1"], records


def test_a_failed_write_never_cuts_a_foreign_append(events_dir: Path) -> None:
    """T-00001133 (security M2): `_write_line` cuts back only when the size is its
    start plus ITS OWN bytes. On 95df5a87 a same-pid writer of another pid namespace
    (`_day_file`) appending between two partial writes had its bytes cut with ours.
    They are now kept, welded onto our half line: PRESERVED, not readable — the
    accepted bound, never to be "fixed" by cutting them."""
    real_write = os.write
    foreign = b'{"autre": "ecrivain"}\n'
    calls: list[int] = []

    def _partial_foreign_then_enospc(fd: int, data: Any) -> int:
        calls.append(len(data))
        if len(calls) == 3:
            raise OSError(errno.ENOSPC, "simulated disk full")
        if len(calls) == 2:  # its OWN O_APPEND descriptor: its bytes land at EOF
            with open(next(events_dir.iterdir()), "ab") as other:
                other.write(foreign)
        return real_write(fd, bytes(data)[: len(data) // 3])

    before = _lost()
    with mock.patch.object(events.os, "write", _partial_foreign_then_enospc):
        events.emit("hook.deny", host="claude", guard="g", rule="r1", path="p")
    assert _lost() == before + 1 and len(calls) == 3, calls
    assert foreign in _day_bytes(events_dir), "another writer's bytes were cut"


def test_a_zero_byte_write_raises_eio_without_looping(events_dir: Path) -> None:
    """T-00001133: `_write_line` itself, not through `emit` (whose `except`
    would swallow a looping fuse too): a write that returns 0 raises EIO at once."""
    fake = mock.Mock(side_effect=[0])  # a second call would raise StopIteration
    with mock.patch.object(events.os, "write", fake), pytest.raises(OSError) as raised:
        events._write_line({"kind": "hook.deny", "data": {}}, datetime.now(timezone.utc), "claude")
    assert raised.value.errno == errno.EIO
    assert fake.call_count == 1


def test_a_zero_byte_write_is_counted(events_dir: Path) -> None:
    """T-00001133: on 63f63f35 the same write lost the line with no diagnostic."""
    before = _lost()
    with mock.patch.object(events.os, "write", mock.Mock(side_effect=[0])):
        events.emit("hook.deny", host="claude", guard="g", rule="r", path="p")
    assert _lost() == before + 1
