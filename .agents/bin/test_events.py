"""Tests for events.py — canal-A event emission (T-00000018 shard 1).

Style: explicit-path module load (matching the import contract events.py
itself mandates for shard 2/3 call sites — dogfooding it here catches a
regression in the contract as fast as a regression in the emitter). Every
test that writes redirects via AGENTS_EVENTS_DIR (monkeypatch.setenv), never
the real .agents/state/events/.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import textwrap
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("events", HERE / "events.py")
events = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = events
_spec.loader.exec_module(events)


def _lines(events_dir: Path) -> list[str]:
    """Option C (L-00000041): a day is N files, one per writer (host+pid).
    These tests each run everything in ONE pytest process, so in practice
    they still produce a single file per test — but the helper globs and
    aggregates rather than assuming that, per the reader-aggregates contract
    (design doc §C), so it stays correct if a test ever emits under more than
    one `host` value."""
    files = sorted(events_dir.glob("*.jsonl"))
    out: list[str] = []
    for f in files:
        text = f.read_bytes().decode("utf-8")
        assert "\r\n" not in text, f"CRLF leaked into {f.name} (L-003)"
        out.extend(ln for ln in text.split("\n") if ln)
    return out


def _records(events_dir: Path) -> list[dict]:
    return [json.loads(ln) for ln in _lines(events_dir)]


@pytest.fixture(autouse=True)
def _redirect(tmp_path, monkeypatch):
    events_dir = tmp_path / "events"
    monkeypatch.setenv("AGENTS_EVENTS_DIR", str(events_dir))
    # Diagnostics are process-global; isolate each test's deltas rather than
    # asserting on the raw counter (tests run in one interpreter).
    before = events.get_diagnostics()
    yield events_dir
    # nothing to restore: tests assert on (after - before) deltas explicitly.
    del before


# ---------------------------------------------------------------------------
# Envelope
# ---------------------------------------------------------------------------

def test_envelope_shape_and_pid_is_prompt_id(_redirect):
    events_dir = _redirect
    for _ in range(2):
        events.emit(
            "hook.deny",
            host="claude", sid="sess-1", pid="prompt-abc-123", aid="agent-1",
            task="T-999", agent="dev-multi", effort="high",
            guard="protect-paths", rule="deny-src-legacy", path="src/legacy/x.py",
        )
    recs = _records(events_dir)
    assert len(recs) == 2
    base_keys = {
        "ts", "kind", "host", "sid", "pid", "aid", "task", "agent", "effort",
        "user", "data",
    }
    # T-00000641 (S-00001597): the FIRST record of a fresh day-file carries the
    # append-only bound as an extra `borne` envelope key; every LATER record does
    # not. The steady-state envelope shape is otherwise unchanged — no key added,
    # and (step 5) the degraded-mode neutralisation replaces VALUES, never keys.
    assert set(recs[0].keys()) == base_keys | {"borne"}
    assert recs[0]["borne"].startswith("append-only")
    assert set(recs[1].keys()) == base_keys
    rec = recs[0]
    assert rec["kind"] == "hook.deny"
    assert rec["pid"] == "prompt-abc-123"
    # Regression guard: pid must be prompt_id, never os.getpid(). A future
    # edit that "fixes" this to os.getpid() would still pass a naive
    # "pid is present" test — assert the actual value, and that it cannot
    # coincidentally equal the interpreter's real pid.
    assert rec["pid"] != os.getpid()
    assert rec["ts"].endswith("Z")


# ---------------------------------------------------------------------------
# Envelope `user` cap (T-00000032) — `user` lives in the envelope, so the
# data-scoped caps and the 4 KiB recovery rewrite never touch it; the bound
# must exist at the resolution point itself.
# ---------------------------------------------------------------------------

class _FakeGit:
    def __init__(self, stdout: str):
        self.stdout = stdout


def _fake_git_name(monkeypatch, name: str) -> None:
    monkeypatch.setattr(events, "_cached_user", events._USER_UNSET)
    monkeypatch.setattr(
        events.subprocess, "run", lambda *a, **k: _FakeGit(name + "\n")
    )


def test_user_is_capped_with_visible_marker_and_counter(_redirect, monkeypatch):
    events_dir = _redirect
    before = events.get_diagnostics()["truncated_fields"]
    _fake_git_name(monkeypatch, "x" * 5000)
    events.emit("hook.deny", guard="g", rule="r", path="p")
    line = _lines(events_dir)[0]
    rec = json.loads(line)
    assert rec["user"] == "x" * events._USER_LEN_CAP + events._TRUNCATE_MARKER
    assert events.get_diagnostics()["truncated_fields"] == before + 1
    # The point of the cap: even a pathological git config can no longer
    # push the WHOLE line over the budget the data-rewrite cannot recover.
    assert len(line.encode("utf-8")) <= events._DATA_CAP_BYTES


def test_user_normal_name_passes_untouched(_redirect, monkeypatch):
    events_dir = _redirect
    before = events.get_diagnostics()["truncated_fields"]
    _fake_git_name(monkeypatch, "Prénom Nom")
    events.emit("hook.deny", guard="g", rule="r", path="p")
    assert _records(events_dir)[0]["user"] == "Prénom Nom"
    assert events.get_diagnostics()["truncated_fields"] == before


# ---------------------------------------------------------------------------
# T-00000641 — RÉDACTION DES SECRETS À L'ÉCRITURE (spool JSONL)
#
# FAUX SECRETS par CONCATÉNATION (comme test_cadre_ledger_redaction) : à
# l'exécution la valeur a la FORME d'un secret, mais dans le TEXTE du source les
# jetons sont coupés, pour que le gitleaks du dépôt ne bloque pas CE fichier.
# ---------------------------------------------------------------------------

_FAUX_AWS = "AKIA" + "Z3XYQ7WNRT4KLMND"                       # aws-access-token
_FAUX_GHP = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"   # github-pat (40)


def _raw(events_dir: Path) -> bytes:
    """Octets BRUTS de tous les day-files — la preuve est lue sur le fichier."""
    return b"".join(f.read_bytes() for f in sorted(events_dir.glob("*.jsonl")))


def _raise_module_not_found(*_a, **_k):
    raise ModuleNotFoundError("cadre introuvable (témoin S-00001655)")


def _degrade_module_absent(monkeypatch, tmp_path) -> None:
    """Force le fail-open `redaction_unavailable` en DÉFAISANT LES DEUX BRANCHES
    (S-00001655) : branche (1) (paquet) mockée pour lever — sinon, en run complet,
    `cadre` posé sur `sys.path` par un autre module de test la ferait réussir et la
    dégradation ne se produirait jamais — ET branche (2) (chemin) sur un fichier
    ABSENT, mémo remis à None. monkeypatch RESTAURE les trois (B-C2/A-R4)."""
    monkeypatch.setattr(events, "_importer_redaction_paquet", _raise_module_not_found)
    monkeypatch.setattr(events, "_CHEMIN_REDACTION", tmp_path / "no_such_redaction.py")
    monkeypatch.setattr(events, "_REDACTION", None)


def _raise_type_error(*_a, **_k):
    raise TypeError("rediger_arbre boom (témoin)")


def test_la_branche_2_par_chemin_prend_le_relais_quand_le_paquet_est_introuvable(
    _redirect, monkeypatch
):
    """S-00001655 — quand la branche (1) (paquet installé) est introuvable, la
    résolution TOMBE sur la branche (2) (chargeur PAR CHEMIN) et rédige quand même.
    Preuve directe du repli. (La branche (1) elle-même n'est pas exerçable ICI : ce
    banc n'a pas `cadre` sur `sys.path` ; elle l'est dans test_cadre_ledger_redaction.)"""
    monkeypatch.setattr(events, "_REDACTION", None)
    monkeypatch.setattr(events, "_importer_redaction_paquet", _raise_module_not_found)
    red = events._redaction()
    assert red is not None, "la branche (2) par chemin n'a pas pris le relais"
    assert red.__name__ == "_cadre_redaction_events", "ce n'est pas le module chargé PAR CHEMIN"
    assert red.rediger(_FAUX_AWS) != _FAUX_AWS, "la branche (2) ne rédige pas"


def test_le_cap_ne_tronque_pas_un_secret_en_clair(_redirect):
    """T7 — cap `hook.deny/path` = 300 ; jeton à cheval sur l'octet 300. Rédiger
    AVANT le cap (C5) : (a) `b"AKIA"` absent des octets ; (b) `data["path"]` finit
    par le marqueur de troncature (preuve que le cap a joué)."""
    events_dir = _redirect
    events.emit("hook.deny", guard="g", rule="r", path="x" * 290 + _FAUX_AWS)
    assert b"AKIA" not in _raw(events_dir)                          # (a)
    rec = _records(events_dir)[0]
    assert rec["data"]["path"].endswith(events._TRUNCATE_MARKER)    # (b)


def test_le_cap_user_ne_tronque_pas_un_secret(_redirect, monkeypatch):
    """T8 — même forme que T7 sur `user`, que l'ALLOWLIST ne borne pas : 95 car.
    (dont l'espace qui donne au motif `github_token` — ancré `\\b`, contrairement à
    l'AWS de T7 en lookaround — sa frontière de mot) + jeton GitHub (40) → à cheval
    sur le cap 100. Rédiger avant le cap : (a) `b"ghp_"` absent ; (b) `user` finit
    par le marqueur de troncature."""
    events_dir = _redirect
    _fake_git_name(monkeypatch, "n" * 94 + " " + _FAUX_GHP)
    events.emit("hook.deny", guard="g", rule="r", path="p")
    assert b"ghp_" not in _raw(events_dir)                          # (a)
    rec = _records(events_dir)[0]
    assert rec["user"].endswith(events._TRUNCATE_MARKER)           # (b)


def test_sans_module_de_redaction_emit_ecrit_sans_data(_redirect, monkeypatch, tmp_path):
    """T10 — fail-open côté spool : sans module de rédaction, la ligne est écrite
    mais `data` neutralisé APRÈS `_build_record`, compteur bumpé, OCTETS absents."""
    events_dir = _redirect
    _degrade_module_absent(monkeypatch, tmp_path)
    before = events.get_diagnostics()["redaction_unavailable"]
    events.emit("hook.deny", guard="g", rule="r", path=_FAUX_AWS)
    assert _FAUX_AWS.encode("utf-8") not in _raw(events_dir)            # (a)
    recs = _records(events_dir)
    assert len(recs) == 1                                                # (d)
    assert recs[0]["data"] == {"redaction_unavailable": True}           # (b)
    assert events.get_diagnostics()["redaction_unavailable"] == before + 1  # (c)


def test_sans_module_de_redaction_l_ENVELOPPE_ne_fuit_pas(_redirect, monkeypatch, tmp_path):
    """T10b — bloquant B : secret dans un champ d'ENVELOPPE. En dégradé,
    l'enveloppe ET `user` sont NEUTRALISÉS par le littéral ; aucun octet
    d'appelant, l'ensemble des CLÉS inchangé (SYM-1860)."""
    events_dir = _redirect
    _degrade_module_absent(monkeypatch, tmp_path)
    events.emit("hook.deny", task=_FAUX_AWS, path="x")
    assert _FAUX_AWS.encode("utf-8") not in _raw(events_dir)            # (a) porteuse
    rec = _records(events_dir)[0]
    for cle in events._ENVELOPE_KEYS | {"user"}:                        # (b) itère la CONSTANTE
        assert rec[cle] == events._MARQUEUR_DEGRADE, cle
    base = {"ts", "kind", "host", "sid", "pid", "aid", "task", "agent", "effort", "user", "data"}
    assert set(rec.keys()) == base | {"borne"}                          # (c) clés inchangées


def test_une_exception_de_redaction_ne_perd_pas_la_ligne(_redirect, monkeypatch):
    """T14 — `rediger_arbre` lève : la ligne n'est PAS perdue (try/except autour
    de la rédaction DISTINCT de celui d'emit), `data == {"redaction_failed":
    True}`, compteur, octets ABSENTS. Mémoïsation FORCÉE avant le patch."""
    events_dir = _redirect
    red = events._redaction()          # FORCER la mémoïsation avant de patcher
    assert red is not None
    monkeypatch.setattr(red, "rediger_arbre", _raise_type_error)
    before = events.get_diagnostics()["redaction_failed"]
    events.emit("hook.deny", guard="g", rule="r", path=_FAUX_AWS)
    assert _FAUX_AWS.encode("utf-8") not in _raw(events_dir)            # (a)
    recs = _records(events_dir)
    assert len(recs) == 1                                                # (d)
    assert recs[0]["data"] == {"redaction_failed": True}               # (b)
    assert events.get_diagnostics()["redaction_failed"] == before + 1  # (c)


def test_une_exception_de_redaction_ne_laisse_pas_fuir_l_ENVELOPPE(_redirect, monkeypatch):
    """T14b — même racine que T10b sur l'autre mode dégradé : `rediger_arbre`
    ayant levé, `fields` sont bruts pour l'enveloppe AUSSI ; la boucle
    `_CLES_DEGRADEES` la neutralise. Mémoïsation FORCÉE avant le patch."""
    events_dir = _redirect
    red = events._redaction()
    assert red is not None
    monkeypatch.setattr(red, "rediger_arbre", _raise_type_error)
    events.emit("hook.deny", task=_FAUX_AWS, path="x")
    assert _FAUX_AWS.encode("utf-8") not in _raw(events_dir)            # (a) porteuse
    rec = _records(events_dir)[0]
    for cle in events._ENVELOPE_KEYS | {"user"}:                        # (b)
        assert rec[cle] == events._MARQUEUR_DEGRADE, cle
    base = {"ts", "kind", "host", "sid", "pid", "aid", "task", "agent", "effort", "user", "data"}
    assert set(rec.keys()) == base | {"borne"}                          # (c)


def test_sans_module_de_redaction_le_NOM_du_day_file_ne_fuit_pas(_redirect, monkeypatch, tmp_path):
    """T17 — le canal du NOM : secret dans `host`. En dégradé, `host` est
    neutralisé AVANT que `_day_file` ne le reçoive (capture après la boucle) ; ni
    le CONTENU ni les NOMS DE FICHIERS ne portent le secret."""
    events_dir = _redirect
    _degrade_module_absent(monkeypatch, tmp_path)
    events.emit("hook.deny", host=_FAUX_AWS, path="x")
    names = [p.name for p in events_dir.glob("*")]
    assert all(_FAUX_AWS not in n for n in names), names               # porteuse (NOMS)
    assert _FAUX_AWS.encode("utf-8") not in _raw(events_dir)           # et contenu
    # secondaire : le marqueur a traversé l'assainisseur → jeton inoffensif, non vide.
    assert any("_REDACTION_INDISPONIBLE_" in n for n in names), names


def test_en_mode_NOMINAL_l_ENVELOPPE_est_REDIGEE(_redirect):
    """T18 — mode NOMINAL, aucun patch : le secret dans `task` est RÉDIGÉ (pas
    neutralisé) ; les AUTRES clés d'enveloppe gardent leurs valeurs d'appelant.
    La forme du marqueur est DÉRIVÉE de `redaction.py`, jamais recopiée du plan."""
    events_dir = _redirect
    events.emit(
        "hook.deny", task=_FAUX_AWS, sid="sess-x", pid="prompt-x", aid="agent-x", path="p"
    )
    assert _FAUX_AWS.encode("utf-8") not in _raw(events_dir)           # (a) porteuse
    rec = _records(events_dir)[0]
    attendu = events._redaction().rediger(_FAUX_AWS)                   # marqueur dérivé
    assert "[SECRET" in attendu and _FAUX_AWS not in attendu
    assert rec["task"] == attendu                                      # (b) RÉDIGÉ, pas neutralisé
    assert rec["task"] != events._MARQUEUR_DEGRADE
    assert rec["sid"] == "sess-x"                                      # (c) autres clés INTACTES
    assert rec["pid"] == "prompt-x"
    assert rec["aid"] == "agent-x"


def test_la_primeur_du_day_file_est_decidee_DANS_la_section_critique(_redirect, monkeypatch):
    """T15 — DÉTERMINISTE, MONO-FIL : la sonde de primeur (`stat().st_size`, A-T1)
    DOIT tomber DANS la section critique. Journal `["acquire", "stat", "write",
    "release"]` — sans dépendre d'un entrelacement ni d'une horloge."""
    import pathlib

    events_dir = _redirect
    events._redaction()          # mémoïsation hors de la fenêtre observée
    events._resolve_user()       # idem : pas de subprocess dans la fenêtre
    journal: list[str] = []
    real_lock = events._write_lock

    class _RecordingLock:
        def __enter__(self):
            journal.append("acquire")
            return real_lock.__enter__()

        def __exit__(self, *a):
            result = real_lock.__exit__(*a)
            journal.append("release")
            return result

    real_stat = pathlib.Path.stat

    def _spy_stat(self, *a, **k):
        # A-T1 : la primeur se décide par `stat().st_size`, plus par `.exists()`.
        # On filtre sur le day-file (`.jsonl`) — un `stat` de `mkdir` sur le
        # répertoire ne doit pas polluer le journal.
        if str(self).endswith(".jsonl"):
            journal.append("stat")
        return real_stat(self, *a, **k)

    real_write = os.write

    def _spy_write(fd, data):
        journal.append("write")
        return real_write(fd, data)

    monkeypatch.setattr(events, "_write_lock", _RecordingLock())
    monkeypatch.setattr(pathlib.Path, "stat", _spy_stat)
    monkeypatch.setattr(events.os, "write", _spy_write)
    events.emit("hook.deny", guard="g", rule="r", path="p")
    assert journal == ["acquire", "stat", "write", "release"], journal


def test_deux_emit_concurrents_ne_dechirent_aucune_ligne(_redirect):
    """T15 bis — filet d'intégrité SANS charge de preuve (sa mutation peut ne pas
    rougir : `os.write` sous O_APPEND atomique pour de petits buffers selon la
    plateforme). Deux threads, un processus, un day-file : le fichier se relit
    ligne par ligne en JSON valide et porte deux enregistrements."""
    import threading

    events_dir = _redirect
    events._redaction()
    events._resolve_user()

    def _worker():
        events.emit("hook.deny", guard="g", rule="r", path="p")

    threads = [threading.Thread(target=_worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    recs = _records(events_dir)
    assert len(recs) == 2
    assert all(r["kind"] == "hook.deny" for r in recs)


def test_un_day_file_VIDE_recoit_quand_meme_la_borne(_redirect, monkeypatch):
    """A-T1 (S-00001597) — la borne porte sur le CONTENU, pas la présence : un
    day-file préexistant VIDE (0 octet — ex. os.open réussi puis os.write échoué au
    tour précédent) doit ENCORE recevoir la borne en tête. La mutation `created =
    not target.exists()` (présence) le raterait DÉFINITIVEMENT."""
    events_dir = _redirect
    events._redaction()
    events_dir.mkdir(parents=True, exist_ok=True)
    shared = events_dir / "2026-09-20.probe.42.jsonl"
    shared.write_bytes(b"")  # day-file préexistant, 0 octet
    monkeypatch.setattr(events, "_day_file", lambda now, host: shared)
    events.emit("hook.deny", guard="g", rule="r", path="p")
    recs = _records(events_dir)
    assert len(recs) == 1
    assert recs[0].get("borne", "").startswith("append-only"), recs[0]


def test_en_mode_NOMINAL_le_NOM_du_day_file_ne_fuit_pas(_redirect):
    """T17, pied NOMINAL (B-3) — mesuré CAPABLE d'échouer, contrairement à ce
    qu'affirmait le plan : en mode nominal `host` est RÉDIGÉ au point de capture,
    donc le NOM du day-file porte la famille rédigée, jamais le secret. Capturer
    `host` AVANT la rédaction de `fields` rendrait le nom `<date>.AKIA….<pid>.jsonl`
    (mutation jouée)."""
    events_dir = _redirect
    events.emit("hook.deny", host=_FAUX_AWS, path="x")
    names = [p.name for p in events_dir.glob("*")]
    assert all(_FAUX_AWS not in n for n in names), names        # porteuse (NOMS)
    assert _FAUX_AWS.encode("utf-8") not in _raw(events_dir)
    # le nom porte la FAMILLE rédigée (assainie) — preuve que la rédaction a traversé.
    assert any("SECRET" in n for n in names), names


# ---------------------------------------------------------------------------
# Fail-open (design doc §B.1, task constraint)
# ---------------------------------------------------------------------------

def test_fail_open_on_unwritable_path(_redirect, monkeypatch):
    events_dir = _redirect

    def _boom(*a, **k):
        raise OSError("simulated disk full")

    monkeypatch.setattr(events.os, "open", _boom)
    result = events.emit("hook.deny", guard="g", rule="r", path="p")
    assert result is None
    assert not events_dir.exists() or not list(events_dir.glob("*.jsonl"))


def test_fail_open_on_unserializable_data(_redirect):
    events_dir = _redirect

    class Unserializable:
        pass

    result = events.emit("hook.deny", guard="g", rule="r", path=Unserializable())
    assert result is None
    assert _lines(events_dir) == []


def test_fail_open_never_raises_on_missing_kind_argument_types(_redirect):
    # kind must be a str per the public contract; a caller mistake here must
    # still fail open rather than raising into a hook.
    result = events.emit(None)  # type: ignore[arg-type]
    assert result is None


# ---------------------------------------------------------------------------
# Closed kind vocabulary
# ---------------------------------------------------------------------------

def test_unknown_kind_is_dropped_and_counted(_redirect):
    events_dir = _redirect
    before = events.get_diagnostics()["unknown_kind"]
    events.emit("totally.unknown", guard="g")
    after = events.get_diagnostics()["unknown_kind"]
    assert after - before == 1
    assert _lines(events_dir) == []


# ---------------------------------------------------------------------------
# C13 — out-of-allowlist field dropped + counted; load-bearing fields present
# ---------------------------------------------------------------------------

def test_redaction_drops_out_of_allowlist_field_and_counts_it(_redirect):
    events_dir = _redirect
    before = events.get_diagnostics()["dropped_fields"]
    events.emit(
        "scan.mcp_call",
        server="npm:@figma/mcp", tool="get_design_context",
        audit_state="audited", duration_ms=120,
        tool_input="SHOULD-NEVER-BE-WRITTEN",
        tool_response="SHOULD-NEVER-BE-WRITTEN-EITHER",
    )
    after = events.get_diagnostics()["dropped_fields"]
    assert after - before == 2

    rec = _records(events_dir)[0]
    assert "tool_input" not in rec["data"]
    assert "tool_response" not in rec["data"]
    raw_text = "\n".join(_lines(events_dir))
    assert "SHOULD-NEVER-BE-WRITTEN" not in raw_text


def test_session_notify_is_a_valid_kind_whose_data_stays_EMPTY(_redirect):
    """T-00000090 — the marker exists; its prose does not.

    `session.notify` carries an EMPTY allowlist, and that is the decision, not
    an oversight: the day-file is TRACKED, so anything landing under `data` gets
    committed. The badge this feeds only needs the event to EXIST — the envelope
    already carries host/sid/ts. The question the agent asked stays in the
    transcript.

    Same argument that kept `message` out of `session.compact`, and the arm is
    written the same way: a caller that tries to attach the question must see it
    dropped AND counted, never silently written.
    """
    events_dir = _redirect
    before = events.get_diagnostics()["dropped_fields"]
    events.emit("session.notify", sid="s-1",
                message="Puis-je supprimer ce fichier ?")
    after = events.get_diagnostics()["dropped_fields"]
    assert after - before == 1

    rec = _records(events_dir)[0]
    assert rec["kind"] == "session.notify"
    assert rec.get("data", {}) == {}
    # The envelope half — what the badge actually reads — must survive.
    assert rec["sid"] == "s-1"
    raw_text = "\n".join(_lines(events_dir))
    assert "supprimer ce fichier" not in raw_text


@pytest.mark.parametrize("kind", ["scan.secrets", "scan.sast", "scan.iac"])
def test_load_bearing_status_present_and_non_null(_redirect, kind):
    events_dir = _redirect
    events.emit(kind, status="scanned", counters={"high": 0, "critical": 0})
    rec = _records(events_dir)[0]
    assert "status" in rec["data"]
    assert rec["data"]["status"] is not None


def test_load_bearing_mcp_call_identity_and_audit_state(_redirect):
    events_dir = _redirect
    events.emit(
        "scan.mcp_call",
        server="npm:@figma/mcp", tool="get_screenshot",
        audit_state="unaudited", duration_ms=42,
    )
    rec = _records(events_dir)[0]
    assert rec["data"]["server"] is not None
    assert rec["data"]["audit_state"] is not None


def test_load_bearing_hook_deny_guard_rule_path(_redirect):
    events_dir = _redirect
    events.emit("hook.deny", guard="safe-bash", rule="rm-tracked", path="src/foo.py")
    rec = _records(events_dir)[0]
    for key in ("guard", "rule", "path"):
        assert rec["data"][key] is not None


# ---------------------------------------------------------------------------
# T-00000018 addendum — per-field length cap (defense in depth, independent
# of any call site). A HIGH finding, confirmed 3x by independent review:
# safe-bash.sh's `path` field once carried the ENTIRE, model-controlled shell
# command (potentially containing a live credential) — the 4 KiB whole-`data`
# cap did not catch it (the leaked record was 1171 bytes). Fixing the call
# site stops today's leak; this cap is the second, independent layer that
# stops a FUTURE emitter from reproducing it through the same field.
# ---------------------------------------------------------------------------

def test_hook_deny_path_over_cap_is_truncated_with_visible_marker_and_counted(_redirect):
    events_dir = _redirect
    before = events.get_diagnostics()["truncated_fields"]
    long_path = "A" * 1000
    events.emit("hook.deny", guard="some-guard", rule="some-rule", path=long_path)
    after = events.get_diagnostics()["truncated_fields"]
    assert after - before == 1

    rec = _records(events_dir)[0]
    written = rec["data"]["path"]
    assert written != long_path                # actually shortened, not passed through
    assert written.endswith("...<truncated>")   # visible marker, never a silent cut
    assert len(written) < len(long_path)


def test_hook_deny_path_under_cap_is_not_touched(_redirect):
    events_dir = _redirect
    before = events.get_diagnostics()["truncated_fields"]
    events.emit("hook.deny", guard="protect-paths", rule="deny-src-legacy", path="src/legacy/x.py")
    after = events.get_diagnostics()["truncated_fields"]
    assert after == before  # a normal, short file path must never be touched

    rec = _records(events_dir)[0]
    assert rec["data"]["path"] == "src/legacy/x.py"


def test_hook_deny_cmd_sha256_and_cmd_len_are_allowlisted_fields(_redirect):
    # safe-bash.sh's own fix: a non-reversible fingerprint + length, never
    # the command itself, is a first-class part of hook.deny's contract now.
    events_dir = _redirect
    events.emit(
        "hook.deny", guard="safe-bash", rule="rm-rf-root",
        cmd_sha256="a" * 64, cmd_len=42,
    )
    rec = _records(events_dir)[0]
    assert rec["data"]["cmd_sha256"] == "a" * 64
    # T-00000042: an int, not a decimal string — a count that reads as a
    # string is a small lie every consumer has to undo.
    assert rec["data"]["cmd_len"] == 42
    assert isinstance(rec["data"]["cmd_len"], int)
    assert "path" not in rec["data"]  # this call site never sends path anymore


# ---------------------------------------------------------------------------
# C14 — scan.sca carries a per-ecosystem status MAP, never one tri-state
# ---------------------------------------------------------------------------

def test_scan_sca_status_is_a_per_ecosystem_map_not_a_scalar(_redirect):
    events_dir = _redirect
    status_map = {"npm": "scanned", "java": "degraded", "swift": "skipped"}
    events.emit("scan.sca", status=status_map, counters={"total": 3})
    rec = _records(events_dir)[0]
    assert isinstance(rec["data"]["status"], dict)
    assert rec["data"]["status"] == status_map


# ---------------------------------------------------------------------------
# C15 — unresolved is a normal mcp audit_state, not a degradation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("state", ["audited", "unaudited", "unresolved"])
def test_mcp_audit_state_three_states_all_accepted_plainly(_redirect, state):
    events_dir = _redirect
    events.emit("scan.mcp_call", server="npm:@x/y", tool="t", audit_state=state)
    rec = _records(events_dir)[0]
    assert rec["data"]["audit_state"] == state
    # No coverage_degraded side effect is emitted for `unresolved` — this
    # module never emits a second event per call, so the absence is
    # structural, not merely untested.
    assert len(_lines(events_dir)) == 1


# ---------------------------------------------------------------------------
# Line-size cap / truncation
# ---------------------------------------------------------------------------

def test_oversized_line_is_truncated_not_dropped(_redirect):
    # kind is `hook.check_fail`, NOT `hook.deny`: `hook.deny`'s own `path` now
    # carries an INDEPENDENT per-field cap (T-00000018 addendum) that would
    # shrink `huge` down to ~314 bytes before this whole-line 4 KiB cap ever
    # gets a chance to engage — `hook.check_fail` shares the same
    # {guard,rule,path} shape but has no per-field cap of its own, so it
    # still exercises the GENERIC whole-line fallback this test is for.
    events_dir = _redirect
    huge = "x" * 8192
    events.emit("hook.check_fail", guard="g", rule="r", path=huge)
    lines = _lines(events_dir)
    assert len(lines) == 1
    # A-T6/B-6 : ancrer le dépassement au SEUL surcoût de la clé `borne` (le
    # fragment JSON `, "borne": "<phrase>"`, mesuré +79 octets), au lieu d'une
    # marge arbitraire de 512 — la PREMIÈRE ligne d'un day-file peut dépasser le
    # cap EXACTEMENT de ce fragment, jamais plus.
    borne_overhead = len(
        json.dumps({"borne": events._BORNE_APPEND_ONLY}, ensure_ascii=False).encode("utf-8")
    )
    assert len(lines[0].encode("utf-8")) <= events._DATA_CAP_BYTES + borne_overhead
    rec = json.loads(lines[0])
    assert rec["data"] == {"truncated": True}


# ---------------------------------------------------------------------------
# GATE A — R1 probe, REWORKED after the pilot's option-C decision.
#
# Original finding (shard 1, first cut — one shared day-file): PIPE_BUF-class
# O_APPEND atomicity is a POSIX guarantee, NOT a Windows one. Spawning
# concurrent OS processes writing to one shared file lost data on 4/4 runs
# (428/480, 450/480, 376/480, 406/480 lines survived — never corrupted JSON,
# always fewer lines: a lost update, not a torn write). Reproduced
# independently by the coordinator (432/480, same shape) and recorded as
# constraint **L-00000041**. Isolated to rule out a harness bug: a single
# process alone, no contention, lost 0/2000.
#
# Pilot decision: option C, one file per writer (see events.py module
# docstring for full rationale and the two rejected alternatives). The two
# tests below now cover BOTH sides of that decision:
#   1. Per-writer isolation — N concurrent processes, N files, ZERO loss.
#      This is the property option C is supposed to buy; if it regresses,
#      this is the test that should catch it.
#   2. The original shared-file loss, kept and marked xfail rather than
#      deleted — it is the only EXECUTABLE record of why the design is
#      shaped this way (L-00000041). Deleting it would delete the evidence,
#      not just the noise.
#
# L-00000035 discipline (same in both): a PermissionError at
# TemporaryDirectory teardown on Windows is a known flake, not a probe
# failure — all assertions run BEFORE cleanup(), and a teardown-only
# exception is treated as infra flake (swallowed), never as evidence either
# way. Only a run whose assertions actually executed counts as clean.
# ---------------------------------------------------------------------------

_WORKER_TEMPLATE = textwrap.dedent(
    """
    import importlib.util, os, sys
    spec = importlib.util.spec_from_file_location("events", r"{events_py}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    tag = sys.argv[1]
    for i in range({n_events}):
        mod.emit(
            "hook.deny",
            host="probe", sid="s", pid="p", aid="a", task="T-probe",
            agent="probe", effort="high",
            guard=f"probe-{{tag}}", rule=str(i), path="p" * 300,
        )
    """
)

# Same template, but the worker forces every writer onto ONE shared filename
# by monkeypatching `_day_file` before emitting — i.e. it deliberately
# recreates shard-1's original (rejected) shared-file scheme through the
# real write path (same os.open flags, same single write() call), so the
# xfail test below is genuine evidence, not a stale description of one.
_SHARED_FILE_WORKER_TEMPLATE = textwrap.dedent(
    """
    import importlib.util, sys
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("events", r"{events_py}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    _shared = Path(r"{shared_path}")
    mod._day_file = lambda now, host: _shared
    tag = sys.argv[1]
    for i in range({n_events}):
        mod.emit(
            "hook.deny",
            host="probe", sid="s", pid="p", aid="a", task="T-probe",
            agent="probe", effort="high",
            guard=f"probe-{{tag}}", rule=str(i), path="p" * 300,
        )
    """
)

N_WORKERS = 8
N_EVENTS_PER_WORKER = 60


def _spawn_workers(code: str, env: dict) -> list[subprocess.Popen]:
    procs = []
    for w in range(N_WORKERS):
        p = subprocess.Popen(
            [sys.executable, "-", str(w)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env, text=True,
        )
        p.stdin.write(code)
        p.stdin.close()
        procs.append(p)
    return procs


def _wait_all(procs: list[subprocess.Popen]) -> None:
    for p in procs:
        rc = p.wait(timeout=60)
        err = p.stderr.read()
        assert rc == 0, f"worker failed rc={rc} stderr={err}"


def test_atomicity_probe_per_writer_isolation_zero_loss():
    """The property option C is supposed to buy: N concurrent processes, each
    writing its own day-file (distinct pid => distinct filename => no
    cross-process contention), lose NOTHING."""
    tmpdir = tempfile.TemporaryDirectory()
    try:
        events_dir = Path(tmpdir.name) / "events"
        events_dir.mkdir(parents=True)

        events_py = str(HERE / "events.py")
        env = dict(os.environ)
        env["AGENTS_EVENTS_DIR"] = str(events_dir)
        code = _WORKER_TEMPLATE.format(events_py=events_py, n_events=N_EVENTS_PER_WORKER)

        _wait_all(_spawn_workers(code, env))

        files = sorted(events_dir.glob("*.jsonl"))  # glob — never assume one file
        assert len(files) == N_WORKERS, (
            f"expected one file per writer ({N_WORKERS}), got {len(files)}: {files}"
        )

        total_lines = 0
        seen_pids = set()
        for f in files:
            text = f.read_bytes().decode("utf-8")
            assert "\r\n" not in text, f"CRLF leaked into {f.name} (L-003)"
            lines = [ln for ln in text.split("\n") if ln]
            assert len(lines) == N_EVENTS_PER_WORKER, (
                f"{f.name}: expected {N_EVENTS_PER_WORKER} lines, got {len(lines)} — "
                "a per-writer file should never lose a line (no cross-process contention)"
            )
            for ln in lines:
                rec = json.loads(ln)
                assert rec["kind"] == "hook.deny"
            total_lines += len(lines)
            parts = f.name.split(".")  # YYYY-MM-DD.<host>.<pid>.jsonl
            assert parts[-1] == "jsonl"
            seen_pids.add(parts[-2])

        assert total_lines == N_WORKERS * N_EVENTS_PER_WORKER
        assert len(seen_pids) == N_WORKERS, "expected N distinct pids in filenames"
    finally:
        try:
            tmpdir.cleanup()
        except PermissionError:
            # L-00000035: known Windows flake at TemporaryDirectory teardown.
            # All assertions above already executed against captured content;
            # this is infrastructure noise, not a probe failure.
            pass


@pytest.mark.xfail(
    reason=(
        "L-00000041: shared-file O_APPEND is not atomic across concurrent "
        "processes on this platform. Kept as EXECUTABLE evidence for why "
        "option C (per-writer files) was chosen over options A/B — deleting "
        "this test would delete the only record of the finding, not just "
        "the noise. strict=False: the exact loss count is inherently racy "
        "(observed 30-104 of 480 lines lost across runs); an occasional "
        "clean run shows as XPASS, not a suite failure, and does not by "
        "itself overturn L-00000041."
    ),
    strict=False,
)
def test_shared_file_concurrent_writes_still_lose_data_L00000041():
    tmpdir = tempfile.TemporaryDirectory()
    try:
        events_dir = Path(tmpdir.name) / "events"
        events_dir.mkdir(parents=True)
        shared_path = events_dir / "shared-probe.jsonl"

        events_py = str(HERE / "events.py")
        env = dict(os.environ)
        env["AGENTS_EVENTS_DIR"] = str(events_dir)
        code = _SHARED_FILE_WORKER_TEMPLATE.format(
            events_py=events_py, shared_path=str(shared_path), n_events=N_EVENTS_PER_WORKER,
        )

        _wait_all(_spawn_workers(code, env))

        expected_total = N_WORKERS * N_EVENTS_PER_WORKER
        assert shared_path.exists(), "worker(s) failed to create the shared file at all"
        raw = shared_path.read_bytes().decode("utf-8")
        lines = [ln for ln in raw.split("\n") if ln]
        assert len(lines) == expected_total, (
            f"expected {expected_total} lines on the shared file, got {len(lines)} — "
            "this assertion is EXPECTED to fail (xfail): see L-00000041"
        )
    finally:
        try:
            tmpdir.cleanup()
        except PermissionError:
            pass


# ---------------------------------------------------------------------------
# --compact — PLAN_DRIFT resolved: docs/tasks/T-00000018.md's shard-1 section
# is authoritative for this bullet (coordinator decision). Option C makes
# folding more necessary, not less: a day is now N per-writer files.
# ---------------------------------------------------------------------------

def _write_day_file(events_dir: Path, day: str, host: str, pid: int, records: list[dict]) -> Path:
    events_dir.mkdir(parents=True, exist_ok=True)
    path = events_dir / f"{day}.{host}.{pid}.jsonl"
    text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)
    path.write_bytes(text.encode("utf-8"))
    return path


def test_compact_folds_old_files_and_leaves_recent_ones(_redirect):
    events_dir = _redirect
    now = datetime.now(timezone.utc)
    old_day = (now - timedelta(days=45)).strftime("%Y-%m-%d")
    recent_day = (now - timedelta(days=2)).strftime("%Y-%m-%d")

    old_file = _write_day_file(events_dir, old_day, "claude", 111, [
        {"kind": "hook.deny", "agent": "dev-multi", "task": "T-001"},
        {"kind": "hook.deny", "agent": "dev-multi", "task": "T-001"},
        {"kind": "scan.sast", "agent": None, "task": "T-002"},
    ])
    recent_file = _write_day_file(events_dir, recent_day, "claude", 222, [
        {"kind": "hook.deny", "agent": "dev-multi", "task": "T-003"},
    ])

    report = events.compact(retention_days=30, now=now)

    assert not old_file.exists(), "folded day-file should be removed after digest publish"
    assert recent_file.exists(), "a day-file inside retention must be left alone"
    assert report["folded_files"] == 1
    assert report["skipped"] == []

    month = old_day[:7]
    assert month in report["months_updated"]
    digest_path = events_dir / "digest" / f"{month}.json"
    digest = json.loads(digest_path.read_text(encoding="utf-8"))
    assert digest["total_events"] == 3
    assert digest["by_kind"] == {"hook.deny": 2, "scan.sast": 1}
    assert digest["by_agent"] == {"dev-multi": 2}
    assert digest["by_task"] == {"T-001": 2, "T-002": 1}
    assert old_day in digest["days_folded"]
    assert digest["generated_at"].endswith("Z")

    raw = digest_path.read_bytes().decode("utf-8")
    assert "\r\n" not in raw, "CRLF leaked into the digest (L-003)"


def test_compact_is_idempotent_on_rerun(_redirect):
    events_dir = _redirect
    now = datetime.now(timezone.utc)
    old_day = (now - timedelta(days=40)).strftime("%Y-%m-%d")
    _write_day_file(events_dir, old_day, "codex", 333, [
        {"kind": "hook.deny", "agent": "dev-mono", "task": "T-010"},
    ])

    first = events.compact(retention_days=30, now=now)
    assert first["folded_files"] == 1

    month = old_day[:7]
    digest_path = events_dir / "digest" / f"{month}.json"
    after_first = json.loads(digest_path.read_text(encoding="utf-8"))

    # Re-run with nothing new to fold — must not double-count or error.
    second = events.compact(retention_days=30, now=now)
    assert second["folded_files"] == 0
    after_second = json.loads(digest_path.read_text(encoding="utf-8"))
    assert after_second["total_events"] == after_first["total_events"] == 1
    assert after_second["by_kind"] == {"hook.deny": 1}


def test_compact_skips_unparseable_filenames_without_raising(_redirect):
    events_dir = _redirect
    (events_dir).mkdir(parents=True, exist_ok=True)
    junk = events_dir / "not-a-day-file.jsonl"
    junk.write_text('{"kind": "hook.deny"}\n', encoding="utf-8")

    report = events.compact(retention_days=30)
    assert junk.exists()  # untouched — not recognized as a day-file at all
    assert "not-a-day-file.jsonl" in report["skipped"]
    assert report["folded_files"] == 0


# ---------------------------------------------------------------------------
# T-00000038 — granularity: compact() multi-writer-day regression, and
# merge_day_files() (past days folded to one file per day).
# ---------------------------------------------------------------------------

def _writer_file(events_dir: Path, day: str, host: str, pid: int, recs: list[dict]) -> Path:
    events_dir.mkdir(parents=True, exist_ok=True)
    path = events_dir / f"{day}.{host}.{pid}.jsonl"
    body = "\n".join(json.dumps(r) for r in recs) + "\n"
    path.write_bytes(body.encode("utf-8"))
    return path


def _rec(ts: str, kind: str = "hook.deny") -> dict:
    return {"ts": ts, "kind": kind, "host": "claude", "sid": None, "pid": None,
            "aid": None, "task": None, "agent": None, "effort": None,
            "user": None, "data": {}}


def test_compact_counts_every_writer_file_of_the_same_day(_redirect):
    """Regression: the per-file fold marked the day folded on the FIRST
    writer file, then unlinked every sibling uncounted — option C makes
    N files per day the NORM, so the digest silently lost records."""
    events_dir = _redirect
    day = "2020-01-05"
    _writer_file(events_dir, day, "claude", 1, [_rec("2020-01-05T10:00:00Z")])
    _writer_file(events_dir, day, "claude", 2, [_rec("2020-01-05T11:00:00Z"),
                                                _rec("2020-01-05T12:00:00Z")])
    report = events.compact(retention_days=30)
    assert report["folded_files"] == 2
    digest = json.loads((events_dir / "digest" / "2020-01.json").read_text(encoding="utf-8"))
    assert digest["total_events"] == 3, "every writer file of the day must be counted"
    assert digest["days_folded"] == [day]
    assert not list(events_dir.glob(f"{day}.*.jsonl"))


def test_merge_folds_past_days_sorted_and_leaves_today_alone(_redirect):
    events_dir = _redirect
    now = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)
    _writer_file(events_dir, "2026-07-27", "claude", 20, [_rec("2026-07-27T09:00:00Z")])
    _writer_file(events_dir, "2026-07-27", "gemini", 10, [_rec("2026-07-27T08:00:00Z")])
    today = _writer_file(events_dir, "2026-07-28", "claude", 30, [_rec("2026-07-28T01:00:00Z")])

    report = events.merge_day_files(now=now)
    assert report == {"days_merged": ["2026-07-27"], "files_folded": 2}
    merged = events_dir / "2026-07-27.merged.jsonl"
    recs = [json.loads(ln) for ln in merged.read_text(encoding="utf-8").splitlines() if ln]
    assert [r["ts"] for r in recs] == ["2026-07-27T08:00:00Z", "2026-07-27T09:00:00Z"]
    assert not list(events_dir.glob("2026-07-27.*.*.jsonl")), "sources must be gone"
    assert today.exists(), "today's writers may still be live — never touched"


def test_merge_is_idempotent_and_deduplicates_crash_residue(_redirect):
    events_dir = _redirect
    now = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)
    src_recs = [_rec("2026-07-27T09:00:00Z")]
    _writer_file(events_dir, "2026-07-27", "claude", 20, src_recs)
    events.merge_day_files(now=now)
    merged = events_dir / "2026-07-27.merged.jsonl"
    first_content = merged.read_bytes()

    # Second run with nothing to do: byte-identical, nothing reported merged.
    report = events.merge_day_files(now=now)
    assert report == {"days_merged": [], "files_folded": 0}
    assert merged.read_bytes() == first_content

    # Crash residue: the SAME source reappears (publish landed, unlink did
    # not) — every line already in the merged file -> removed, not re-folded.
    residue = _writer_file(events_dir, "2026-07-27", "claude", 20, src_recs)
    report = events.merge_day_files(now=now)
    assert report["files_folded"] == 1
    assert not residue.exists()
    assert merged.read_bytes() == first_content, "no duplicate records after residue cleanup"


def test_merge_carries_malformed_lines_verbatim(_redirect):
    events_dir = _redirect
    now = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)
    path = _writer_file(events_dir, "2026-07-27", "claude", 20, [_rec("2026-07-27T09:00:00Z")])
    with open(path, "ab") as fh:
        fh.write(b"{this is not json\n")
    events.merge_day_files(now=now)
    lines = (events_dir / "2026-07-27.merged.jsonl").read_text(encoding="utf-8").splitlines()
    assert "{this is not json" in lines, "a merge is a relocation, not a summary — nothing dropped"
    assert lines[-1] == "{this is not json", "malformed lines sort last, after every timestamped record"


def test_compact_cli_runs_merge_first(_redirect, capsys):
    events_dir = _redirect
    _writer_file(events_dir, "2026-07-20", "claude", 1, [_rec("2026-07-20T10:00:00Z")])
    _writer_file(events_dir, "2026-07-20", "claude", 2, [_rec("2026-07-20T11:00:00Z")])
    code = events.main(["--merge-days"])
    assert code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["merge"]["files_folded"] == 2
    assert "compact" not in out
    assert (events_dir / "2026-07-20.merged.jsonl").exists()


def test_maintenance_cli_is_single_holder_and_reclaims_stale_lock(_redirect, capsys):
    events_dir = _redirect
    _writer_file(events_dir, "2026-07-20", "claude", 1, [_rec("2026-07-20T10:00:00Z")])
    events_dir.mkdir(parents=True, exist_ok=True)
    lock = events_dir / ".maintenance.lock"

    # A FRESH lock (live rival run) makes the CLI skip without touching data.
    lock.write_text("", encoding="utf-8")
    code = events.main(["--merge-days"])
    assert code == 0
    assert json.loads(capsys.readouterr().out) == {"skipped": "maintenance already running"}
    assert list(events_dir.glob("2026-07-20.claude.1.jsonl")), "a skipped run must not touch sources"

    # A STALE lock (holder died >10min ago) is reclaimed and the run proceeds.
    stale = datetime.now(timezone.utc).timestamp() - 3600
    os.utime(lock, (stale, stale))
    code = events.main(["--merge-days"])
    assert code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["merge"]["files_folded"] == 1
    assert not lock.exists(), "the lock must be released after the run"


def test_merge_residue_skip_is_observable_in_diagnostics(_redirect):
    events_dir = _redirect
    now = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)
    before = events.get_diagnostics()["merge_residue_files"]
    recs = [_rec("2026-07-27T09:00:00Z")]
    _writer_file(events_dir, "2026-07-27", "claude", 20, recs)
    events.merge_day_files(now=now)
    _writer_file(events_dir, "2026-07-27", "claude", 20, recs)  # crash residue
    events.merge_day_files(now=now)
    assert events.get_diagnostics()["merge_residue_files"] == before + 1
