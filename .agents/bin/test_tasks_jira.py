#!/usr/bin/env python3
"""Jira Cloud simulé : aucune requête ne quitte 127.0.0.1."""
from __future__ import annotations

import base64
import contextlib
import datetime
import hashlib
import http.client
import importlib.util
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tasks  # noqa: E402


def _charger_pilote():
    """Le pilote de fusion, chargé par chemin (il tourne sous -I, hors de `tasks`)."""
    spec = importlib.util.spec_from_file_location("fusion_enregistrement_banc_jira",
                                                  Path(__file__).resolve().parent / "fusion_enregistrement.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


P = _charger_pilote()
SITE = "https://x.atlassian.net"


def issue(key: str, number: str, summary: str = "Travail") -> dict:
    return {"key": key, "id": number, "fields": {
        "summary": summary, "created": "2026-10-20T10:11:12.000+0000",
        "updated": "2026-10-21T10:11:12.000+0000", "parent": None,
        "issuetype": {"name": "Task"}}}


class FauxJira:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str, bytes]] = []
        self.issues = [issue("PROJ-1", "101", "Titre | hostile\x00\u2028suite"),
                       issue("PROJ-2", "102")]
        self.put_status = 204
        self.search_status = 200
        self.endless = False
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, _format: str, *_args: object) -> None:
                pass

            def _respond(self, code: int, body: dict | None = None) -> None:
                payload = json.dumps(body or {}).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self) -> None:
                owner.calls.append(("GET", self.path, self.headers.get("Authorization", ""), b""))
                parsed = urlsplit(self.path)
                if parsed.path != "/rest/api/3/search/jql":
                    self._respond(404)
                    return
                if owner.search_status == 302:
                    self.send_response(302)
                    self.send_header("Location", owner.url + "/redirected")
                    self.end_headers()
                    return
                if self.headers.get("Authorization") != "Basic " + base64.b64encode(b"agent@example.test:jeton-test").decode():
                    self._respond(401)
                    return
                query = parse_qs(parsed.query)
                if query.get("fields") != ["summary,created,updated,parent,issuetype"]:
                    self._respond(400)
                    return
                if owner.endless:
                    self._respond(200, {"issues": [], "isLast": False,
                                        "nextPageToken": str(len(owner.calls))})
                    return
                if 'key = "PROJ-1"' in query.get("jql", [""])[0]:
                    self._respond(200, {"issues": [owner.issues[0]], "isLast": True})
                    return
                if "nextPageToken" not in query:
                    self._respond(200, {"issues": [owner.issues[0]], "isLast": False,
                                        "nextPageToken": "page-2"})
                else:
                    self._respond(200, {"issues": [owner.issues[1]], "isLast": True})

            def do_PUT(self) -> None:
                size = int(self.headers.get("Content-Length", "0"))
                data = self.rfile.read(size)
                owner.calls.append(("PUT", self.path, self.headers.get("Authorization", ""), data))
                if self.headers.get("Authorization") != "Basic " + base64.b64encode(b"agent@example.test:jeton-test").decode():
                    self._respond(401)
                    return
                self._respond(owner.put_status)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> "FauxJira":
        self.thread.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


class JiraTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="tasks-jira-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "board"
        self.root.mkdir()
        self.server = FauxJira()
        self.server.__enter__()
        self.addCleanup(self.server.__exit__)
        self.env = {"CADRE_JIRA_SITE": self.server.url, "CADRE_JIRA_EMAIL": "agent@example.test",
                    "JIRA_API_TOKEN": "jeton-test", "HOME": self.tmp.name,
                    "NO_PROXY": "127.0.0.1,localhost", "PYTHONDONTWRITEBYTECODE": "1"}

    def main(self, *argv: str, env: dict[str, str] | None = None) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, self.env if env is None else env, clear=True), \
                mock.patch.object(tasks, "replay_sync", return_value=0), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = tasks.main(["--root", str(self.root), *argv])
        return rc, out.getvalue(), err.getvalue()

    def imported(self) -> dict:
        self.assertEqual(self.main("jira-import", "--project", "PROJ")[0], 0)
        return tasks.load(str(self.root))["tasks"][0]

    def test_import_pagine_identique_et_resume_session_borne(self) -> None:
        rc, out, err = self.main("jira-import", "--project", "PROJ")
        self.assertEqual((rc, err), (0, ""))
        self.assertEqual(len(tasks.load(str(self.root))["tasks"]), 2)
        self.assertEqual(len(self.server.calls), 2)
        self.assertTrue(all("statusCategory != Done" in parse_qs(urlsplit(c[1]).query)["jql"][0]
                            for c in self.server.calls))
        before = tasks.load(str(self.root))["tasks"]
        rc, out2, _ = self.main("jira-import", "--project", "PROJ")
        self.assertEqual(rc, 0)
        self.assertEqual(tasks.load(str(self.root))["tasks"], before)
        self.assertEqual(out2.count("deja-importe"), 2)
        self.assertIn("Jira PROJ-1", tasks.render_session_board(str(self.root)))
        self.assertNotIn("\u2028", tasks.render_session_board(str(self.root)))
        self.assertIn("\\|", before[0]["task"])
        self.assertNotIn("\x00", before[0]["task"])
        rc, session, _ = self.main("list", "--session")
        self.assertEqual(rc, 0)
        self.assertIn("Jira PROJ-1", session)
        self.assertNotIn("\u2028", session)

    def test_resume_long_reste_borne_dans_session(self) -> None:
        self.server.issues[0]["fields"]["summary"] = "X" * 600
        self.assertEqual(self.main("jira-import", "--project", "PROJ")[0], 0)
        title = tasks.load(str(self.root))["tasks"][0]["task"]
        self.assertEqual(len(title), len("Jira PROJ-1 — ") + 180)
        self.assertIn("Jira PROJ-1 — ", tasks.render_session_board(str(self.root)))
        self.assertNotIn("X" * 181, tasks.render_session_board(str(self.root)))

    def test_pages_bornees_avant_toute_ecriture(self) -> None:
        self.server.endless = True
        rc, _, err = self.main("jira-import", "--project", "PROJ")
        self.assertEqual(rc, 2)
        self.assertIn("50 pages", err)
        self.assertEqual(len(self.server.calls), 50)
        self.assertEqual(tasks.load(str(self.root))["tasks"], [])

    def test_meme_pages_deux_horloges_vrai_git_merge(self) -> None:
        base = Path(self.tmp.name) / "base"
        base.mkdir()

        def git(where: Path, *args: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run(["git", "-c", "user.name=banc", "-c", "user.email=banc@example.test",
                                   "-c", "commit.gpgsign=false", "-c", f"core.hooksPath={os.devnull}",
                                   *args], cwd=where, capture_output=True, text=True, timeout=20)

        self.assertEqual(git(base, "init", "-q", "-b", "main").returncode, 0)
        (base / ".gitignore").write_text(".agents/state/local/\n", encoding="utf-8")
        self.assertEqual(git(base, "add", ".gitignore").returncode, 0)
        self.assertEqual(git(base, "commit", "-qm", "base").returncode, 0)
        clones = [Path(self.tmp.name) / name for name in ("clone-a", "clone-b")]
        for clone in clones:
            self.assertEqual(git(base, "clone", "-q", str(base), str(clone)).returncode, 0)
        original = self.root
        records = []
        try:
            # C1 (S-01M5HAKRWKB2N5NBPASPWN3R4Y) : le second import voit un `fields.updated` Jira plus récent ; au
            # même résumé, les octets restent égaux et le merge NU (sans pilote) reste propre.
            for clone, day, zone, jira_updated in zip(
                    clones, ("2026-10-21", "2026-10-23"), ("Pacific/Honolulu", "Pacific/Auckland"),
                    ("2026-10-21T10:11:12.000+0000", "2026-10-23T08:00:00.000+0000")):
                class Clock(datetime.date):
                    @classmethod
                    def today(cls) -> datetime.date:
                        return datetime.date.fromisoformat(day)

                for item in self.server.issues:
                    item["fields"]["updated"] = jira_updated
                self.root = clone
                with mock.patch.object(tasks, "date", Clock):
                    rc, _, err = self.main("jira-import", "--project", "PROJ", env=dict(self.env, TZ=zone))
                self.assertEqual(rc, 0, err)
                records.append(tasks.load(str(clone))["tasks"])
                self.assertEqual(git(clone, "add", "-A").returncode, 0)
                self.assertEqual(git(clone, "commit", "-qm", "import").returncode, 0)
        finally:
            self.root = original
        self.assertEqual(records[0], records[1])
        self.assertEqual(records[0][0]["updated"], "2026-10-20")
        self.assertEqual(git(clones[0], "remote", "add", "other", str(clones[1])).returncode, 0)
        self.assertEqual(git(clones[0], "fetch", "-q", "other").returncode, 0)
        merged = git(clones[0], "merge", "--no-edit", "other/main")
        self.assertEqual(merged.returncode, 0, merged.stdout + merged.stderr)
        self.assertEqual(git(clones[0], "ls-files", "-u").stdout, "")

    def test_collision_seule_et_ticket_suivant_importé(self) -> None:
        with mock.patch.dict(os.environ, self.env, clear=True):
            first, _ = tasks._jira_record(self.server.issues[0], self.server.url, "PROJ")
        self.assertEqual(self.main("new", "Occupant", "--pas-un-defaut", "banc")[0], 0)
        with tasks.board_lock(str(self.root)):
            data = tasks.load(str(self.root))
            data["tasks"][0]["id"] = first["id"]
            tasks.save(str(self.root), data)
        rc, out, _ = self.main("jira-import", "--project", "PROJ")
        self.assertEqual(rc, 2)
        self.assertIn("PROJ-1 collision d'identifiant", out)
        self.assertIn("PROJ-2 importe", out)
        self.assertEqual([t.get("jira_key") for t in tasks.load(str(self.root))["tasks"]],
                         [None, "PROJ-2"])

    def test_tombe_delete_et_purge_refusent_reimport(self) -> None:
        first = self.imported()
        tasks.delete_task(str(self.root), first["id"])
        rc, out, _ = self.main("jira-import", "--project", "PROJ", "--issue", "PROJ-1")
        self.assertEqual(rc, 0)
        self.assertIn("deja-supprime", out)
        self.assertFalse(any(t["id"] == first["id"] for t in tasks.load(str(self.root))["tasks"]))
        second = next(t for t in tasks.load(str(self.root))["tasks"] if t["jira_key"] == "PROJ-2")
        tasks.set_state(str(self.root), second["id"], "done", stage="clos", sans_binome="banc",
                        sans_cible="banc")
        tasks.purge_tasks(str(self.root))
        rc, out, _ = self.main("jira-import", "--project", "PROJ")
        self.assertEqual(rc, 0)
        self.assertEqual(out.count("deja-supprime"), 2)

    def test_configuration_absente_refuse_avant_reseau_et_trousseau(self) -> None:
        env = {"HOME": self.tmp.name, "PYTHONDONTWRITEBYTECODE": "1"}
        with mock.patch("subprocess.run", side_effect=AssertionError("trousseau consulté")):
            rc, out, err = self.main("jira-import", "--project", "PROJ", env=env)
        self.assertEqual(rc, 2)
        self.assertEqual(out, "")
        self.assertIn("site et e-mail absents", err)
        self.assertEqual(self.server.calls, [])

    def test_claim_put_exact_retry_et_dry_run(self) -> None:
        task = self.imported()
        actor = {"auteur": {"nom": "Émilie", "email": "emilie@example.test"}, "copie": "abc"}
        with mock.patch.dict(os.environ, self.env, clear=True):
            tasks.set_state(str(self.root), task["id"], "running", acteur=actor)
            rc, text, _ = self.main("jira-claim", "--retry", task["id"], "--dry-run")
            self.assertEqual(rc, 0)
            self.assertIn("aucun PUT", text)
            self.assertEqual(len([c for c in self.server.calls if c[0] == "PUT"]), 0)
            self.server.put_status = 429
            self.assertIn("HTTP 429", tasks.jira_claim_after_start(str(self.root), task["id"]))
            self.assertEqual(tasks.find(tasks.load(str(self.root)), task["id"])["jira_claim_status"], "attente")
            self.server.put_status = 204
            self.assertIn("acquittee", tasks.jira_claim_retry(str(self.root), task["id"]))
        puts = [c for c in self.server.calls if c[0] == "PUT"]
        self.assertEqual(len(puts), 2)
        self.assertEqual(puts[-1][1], "/rest/api/3/issue/PROJ-1")
        self.assertEqual(json.loads(puts[-1][3]), {"update": {"labels": [{"add":
            tasks.find(tasks.load(str(self.root)), task["id"])["jira_claim_label"]}]}})

    def test_retry_done_ne_fait_aucun_put(self) -> None:
        task = self.imported()
        with tasks.board_lock(str(self.root)):
            data = tasks.load(str(self.root))
            current = tasks.find(data, task["id"])
            current.update(state="done", jira_claim_label="pris-par-banc-0123456789",
                           jira_claim_status="attente")
            tasks.save(str(self.root), data)
        before = len(self.server.calls)
        rc, out, err = self.main("jira-claim", "--retry", task["id"])
        self.assertEqual((rc, err), (0, ""))
        self.assertIn("non running, aucun PUT", out)
        self.assertEqual(len(self.server.calls), before)

    def test_acquitte_absent_ou_ancien_relance_le_put(self) -> None:
        task = self.imported()
        actor = {"auteur": {"nom": "Banc", "email": "banc@example.test"}}
        with mock.patch.dict(os.environ, self.env, clear=True):
            tasks.set_state(str(self.root), task["id"], "running", acteur=actor)
            for stale in (None, "pris-par-ancien-0123456789"):
                with self.subTest(stale=stale), tasks.board_lock(str(self.root)):
                    data = tasks.load(str(self.root))
                    current = tasks.find(data, task["id"])
                    current["jira_claim_status"] = "acquitte"
                    if stale is None:
                        current.pop("jira_claim_acquitte", None)
                    else:
                        current["jira_claim_acquitte"] = stale
                    tasks.jira_prepare_claim(current, actor)
                    self.assertEqual(current["jira_claim_status"], "attente")
                    tasks.save(str(self.root), data)
                before = len([call for call in self.server.calls if call[0] == "PUT"])
                self.assertIn("acquittee", tasks.jira_claim_after_start(str(self.root), task["id"]))
                self.assertEqual(len([call for call in self.server.calls if call[0] == "PUT"]), before + 1)
                current = tasks.find(tasks.load(str(self.root)), task["id"])
                self.assertEqual(current["jira_claim_acquitte"], current["jira_claim_label"])

    def test_verrou_apres_put_garde_start_focus_et_marque(self) -> None:
        task = self.imported()
        actor = {"auteur": {"nom": "Banc", "email": "banc@example.test"}}
        real_request = tasks.jira_request
        ready, release = threading.Event(), threading.Event()
        holder: threading.Thread | None = None

        def hold_lock() -> None:
            with tasks.board_lock(str(self.root)):
                ready.set()
                release.wait(5)

        def put_then_lock(*args: object, **kwargs: object) -> tuple[int, bytes]:
            nonlocal holder
            result = real_request(*args, **kwargs)
            holder = threading.Thread(target=hold_lock, daemon=True)
            holder.start()
            self.assertTrue(ready.wait(2), "verrou non acquis par le second fil")
            return result

        try:
            with mock.patch.object(tasks, "precontrole_revendication", return_value=([], [])), \
                    mock.patch.object(tasks, "acteur_de_la_commande", return_value=actor), \
                    mock.patch.object(tasks, "_LOCK_TIMEOUT_SECONDS", 0.05), \
                    mock.patch.object(tasks, "jira_request", side_effect=put_then_lock):
                rc, out, err = self.main("start", task["id"], "--stage", "banc")
        finally:
            release.set()
            if holder is not None:
                holder.join(timeout=5)
        self.assertEqual(rc, 0, err)
        self.assertIn("label posé, accusé non écrit (verrou)", out)
        self.assertEqual(tasks.find(tasks.load(str(self.root)), task["id"])["stage"], "banc")
        self.assertEqual(tasks.find(tasks.load(str(self.root)), task["id"])["state"], "running")
        self.assertEqual(tasks.lire_focus(str(self.root))["task_id"], task["id"])
        self.assertEqual([call[0] for call in self.server.calls].count("PUT"), 1)

    def test_avis_jira_refuse_ne_casse_ni_start_ni_fournee(self) -> None:
        task = self.imported()
        actor = {"auteur": {"nom": "Banc", "email": "banc@example.test"}}
        with mock.patch.object(tasks, "precontrole_revendication", return_value=([], [])), \
                mock.patch.object(tasks, "acteur_de_la_commande", return_value=actor), \
                mock.patch.object(tasks, "jira_claim_after_start",
                                  side_effect=tasks.BoardError("verrou occupé")):
            rc, out, err = self.main("start", task["id"])
            self.assertEqual(rc, 0, err)
            self.assertIn("prise en attente (verrou occupé)", out)
            self.assertEqual(tasks.lire_focus(str(self.root))["task_id"], task["id"])
            with mock.patch.object(tasks, "fournee", return_value="FOURNEE"):
                rc, out, err = self.main("fournee", task["id"])
        self.assertEqual(rc, 0, err)
        self.assertIn("prise en attente (verrou occupé)", out)
        self.assertEqual(tasks.lire_focus(str(self.root))["task_id"], task["id"])
        self.assertEqual(tasks.find(tasks.load(str(self.root)), task["id"])["state"], "running")

    def test_site_hostile_et_optout(self) -> None:
        task = self.imported()
        env = dict(self.env, CADRE_JIRA_SITE="https://localhost.example.invalid")
        rc, _, err = self.main("jira-import", "--project", "PROJ", env=env)
        self.assertEqual(rc, 2)
        self.assertIn("site Jira Cloud refusé", err)
        with mock.patch.dict(os.environ, dict(self.env, JIRA_AGENT_CLAIM="0"), clear=True):
            tasks.set_state(str(self.root), task["id"], "running", acteur={"auteur": {"nom": "Banc"}})
            self.assertIn("desactive", tasks.jira_claim_after_start(str(self.root), task["id"]))
        self.assertFalse(any(c[0] == "PUT" for c in self.server.calls))

    def test_deux_clones_memes_identites_et_issue_ciblee(self) -> None:
        first = self.imported()
        records = tasks.load(str(self.root))["tasks"]
        other = Path(self.tmp.name) / "autre"
        other.mkdir()
        previous = self.root
        self.root = other
        try:
            rc, _, _ = self.main("jira-import", "--project", "PROJ")
            self.assertEqual(rc, 0)
            self.assertEqual(tasks.load(str(other))["tasks"], records)
        finally:
            self.root = previous
        self.assertTrue(first["id"].startswith("T-"))
        before = len(self.server.calls)
        rc, text, _ = self.main("jira-import", "--project", "PROJ", "--issue", "PROJ-1")
        self.assertEqual(rc, 0)
        self.assertIn("deja-importe", text)
        self.assertEqual(len(self.server.calls), before + 1)

    def test_updated_jira_seul_ne_change_pas_le_record(self) -> None:
        """C5 (S-01M5HAKRWKB2N5NBPASPWN3R4Y) : deux dates Jira seules différentes ⇒ mêmes octets, `updated` = la
        création ; deux résumés différents ⇒ deux enregistrements distincts par `task` SEUL."""
        original = issue("PROJ-1", "101")
        changed = issue("PROJ-1", "101")
        changed["fields"]["updated"] = "2026-10-22T10:11:12.000+0000"
        renamed = issue("PROJ-1", "101", "Autre résumé")
        renamed["fields"]["updated"] = "2026-10-22T10:11:12.000+0000"
        records = [tasks._jira_record(item, SITE, "PROJ")[0] for item in (original, changed, renamed)]
        self.assertEqual(P.canonique(records[0]), P.canonique(records[1]))
        self.assertNotIn("jira_updated", records[0])
        self.assertEqual(records[0]["updated"], "2026-10-20")
        self.assertNotEqual(records[0]["task"], records[2]["task"])
        self.assertEqual({k: v for k, v in records[0].items() if k != "task"},
                         {k: v for k, v in records[2].items() if k != "task"})

    def test_site_canonique_identite_et_dedoublonnage(self) -> None:
        sites = ("https://X.atlassian.net", "https://x.atlassian.net:443/",
                 "https://x.atlassian.net")
        ids = []
        with mock.patch.object(tasks._jira_transport(), "appel", return_value=(200, json.dumps({
                "issues": [issue("PROJ-1", "101")], "isLast": True}).encode())):
            for index, site in enumerate(sites):
                with mock.patch.dict(os.environ, dict(self.env, CADRE_JIRA_SITE=site), clear=True):
                    base, local, _ = tasks._jira_config()
                    report, collision = tasks.jira_import(str(self.root), "PROJ")
                self.assertFalse(local)
                self.assertEqual(base, "https://x.atlassian.net")
                self.assertFalse(collision)
                self.assertIn("importe" if index == 0 else "deja-importe", report)
                ids.append(tasks._jira_record(issue("PROJ-1", "101"), base, "PROJ")[0]["id"])
        self.assertEqual(len(set(ids)), 1)
        self.assertEqual(len(tasks.load(str(self.root))["tasks"]), 1)
        with mock.patch.dict(os.environ, dict(self.env, CADRE_JIRA_SITE="https://x.atlassian.net:8443"),
                             clear=True):
            with self.assertRaisesRegex(tasks.BoardError, "port refusé"):
                tasks._jira_config()

    def test_refus_302_cles_et_pages_hostiles(self) -> None:
        self.assertEqual(self.main("jira-import", "--project", "PROJ", "--issue", "X-1")[0], 2)
        self.assertEqual(self.server.calls, [])
        self.server.search_status = 302
        rc, _, err = self.main("jira-import", "--project", "PROJ")
        self.assertEqual(rc, 2)
        self.assertIn("HTTP 302", err)
        self.assertEqual(len(self.server.calls), 1, "une redirection ne doit jamais être suivie")
        self.server.search_status = 200
        self.server.calls.clear()
        bad = issue("PROJ-1", "101")
        bad["fields"]["updated"] = "\x00secret"
        self.server.issues[0] = bad
        rc, _, err = self.main("jira-import", "--project", "PROJ")
        self.assertEqual(rc, 2)
        self.assertIn("date illisible", err)
        self.assertNotIn("secret", err)
        self.assertEqual(tasks.load(str(self.root))["tasks"], [])

    def test_jeton_trousseau_et_codes_http_sans_secret(self) -> None:
        env = dict(self.env)
        env.pop("JIRA_API_TOKEN")
        env.pop("CADRE_JIRA_SITE")
        env.pop("CADRE_JIRA_EMAIL")
        config = Path(self.tmp.name) / ".config" / "cadre" / "jira.json"
        config.parent.mkdir(parents=True)
        config.write_text(json.dumps({"site": "https://example.atlassian.net",
                                      "email": "agent@example.test"}),
                          encoding="utf-8")
        result = mock.Mock(returncode=0, stdout="jeton-test\n")
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch("subprocess.run", return_value=result) as keychain:
            site, local, auth = tasks._jira_config()
        self.assertEqual((site, local), ("https://example.atlassian.net", False))
        self.assertEqual(auth, "Basic " + base64.b64encode(b"agent@example.test:jeton-test").decode())
        self.assertEqual(keychain.call_args.args[0][:3],
                         ["/usr/bin/security", "find-generic-password", "-s"])
        task = self.imported()
        actor = {"auteur": {"nom": "Banc", "email": "banc@example.test"}}
        with mock.patch.dict(os.environ, self.env, clear=True):
            tasks.set_state(str(self.root), task["id"], "running", acteur=actor)
            for code in (401, 403, 429):
                self.server.put_status = code
                text = tasks.jira_claim_retry(str(self.root), task["id"])
                self.assertIn(f"HTTP {code}", text)
                self.assertNotIn("jeton-test", text)
                self.assertEqual(tasks.find(tasks.load(str(self.root)), task["id"])["jira_claim_status"], "attente")

    def test_trousseau_distant_sert_import_et_prise(self) -> None:
        config = Path(self.tmp.name) / ".config" / "cadre" / "jira.json"
        config.parent.mkdir(parents=True)
        config.write_text(json.dumps({"site": "https://x.atlassian.net",
                                      "email": "agent@example.test"}), encoding="utf-8")
        env = {key: value for key, value in self.env.items()
               if key not in {"CADRE_JIRA_SITE", "CADRE_JIRA_EMAIL", "JIRA_API_TOKEN"}}
        calls: list[str] = []

        def transport(method: str, _url: str, _auth: str, _local: bool,
                      _body: object) -> tuple[int, bytes]:
            calls.append(method)
            if method == "GET":
                return 200, json.dumps({"issues": [issue("PROJ-1", "101")], "isLast": True}).encode()
            return 204, b""

        actor = {"auteur": {"nom": "Banc", "email": "banc@example.test"}}
        keychain_result = mock.Mock(returncode=0, stdout="jeton-test\n")
        # Le chrono de `start` (T-01M5KKFBCXXEVYR8GJPYFEH3C8) appelle git par subprocess.run : coupé ici,
        # pour que le compte ne voie que le trousseau.
        with mock.patch("subprocess.run", return_value=keychain_result) as keychain, \
                mock.patch.object(tasks, "_chrono_apres", return_value=None), \
                mock.patch.object(tasks._jira_transport(), "appel", side_effect=transport), \
                mock.patch.object(tasks, "precontrole_revendication", return_value=([], [])), \
                mock.patch.object(tasks, "acteur_de_la_commande", return_value=actor):
            rc, _, err = self.main("jira-import", "--project", "PROJ", env=env)
            self.assertEqual(rc, 0, err)
            task = tasks.load(str(self.root))["tasks"][0]
            rc, out, err = self.main("start", task["id"], env=env)
        self.assertEqual(rc, 0, err)
        self.assertIn("prise acquittee", out)
        self.assertEqual(calls, ["GET", "PUT"])
        self.assertEqual(keychain.call_count, 2)
        self.assertEqual(tasks.find(tasks.load(str(self.root)), task["id"])["jira_claim_acquitte"],
                         tasks.find(tasks.load(str(self.root)), task["id"])["jira_claim_label"])

    def test_site_local_sans_jeton_refuse_trousseau_et_garde_attente_au_start(self) -> None:
        task = self.imported()
        config = Path(self.tmp.name) / ".config" / "cadre" / "jira.json"
        config.parent.mkdir(parents=True)
        config.write_text(json.dumps({"site": self.server.url, "email": "agent@example.test"}),
                          encoding="utf-8")
        env = {key: value for key, value in self.env.items()
               if key not in {"CADRE_JIRA_SITE", "CADRE_JIRA_EMAIL", "JIRA_API_TOKEN"}}
        actor = {"auteur": {"nom": "Banc", "email": "banc@example.test"}}
        with mock.patch("subprocess.run", side_effect=AssertionError("trousseau lu")) as keychain_call, \
                mock.patch.object(tasks, "_chrono_apres", return_value=None), \
                mock.patch.object(tasks, "precontrole_revendication", return_value=([], [])), \
                mock.patch.object(tasks, "acteur_de_la_commande", return_value=actor):
            with mock.patch.dict(os.environ, env, clear=True):
                with self.assertRaisesRegex(tasks.BoardError, "trousseau refusé pour site local"):
                    tasks._jira_config()
            rc, out, err = self.main("start", task["id"], env=env)
        self.assertEqual(rc, 0, err)
        self.assertIn("prise en attente", out)
        self.assertEqual(tasks.find(tasks.load(str(self.root)), task["id"])["jira_claim_status"], "attente")
        self.assertEqual([call[0] for call in self.server.calls].count("PUT"), 0)
        keychain_call.assert_not_called()

    def test_override_site_ou_email_refuse_trousseau_avant_lecture(self) -> None:
        config = Path(self.tmp.name) / ".config" / "cadre" / "jira.json"
        config.parent.mkdir(parents=True)
        config.write_text(json.dumps({"site": "https://example.atlassian.net",
                                      "email": "agent@example.test"}), encoding="utf-8")
        for override in ({"CADRE_JIRA_SITE": "https://other.atlassian.net"},
                         {"CADRE_JIRA_EMAIL": "other@example.test"}):
            env = {"HOME": self.tmp.name, **override}
            with self.subTest(override=override), mock.patch.dict(os.environ, env, clear=True), \
                    mock.patch("subprocess.run", side_effect=AssertionError("trousseau lu")) as keychain:
                with self.assertRaisesRegex(tasks.BoardError, "trousseau réservé"):
                    tasks._jira_config()
                keychain.assert_not_called()

    def test_agent_refuse_override_avant_trousseau_et_ecriture_arbitraire(self) -> None:
        task = self.imported()
        config = Path(self.tmp.name) / ".config" / "cadre" / "jira.json"
        config.parent.mkdir(parents=True)
        config.write_text(json.dumps({"site": self.server.url, "email": "agent@example.test"}),
                          encoding="utf-8")
        env = dict(self.env, CLAUDECODE="1")
        env.pop("JIRA_API_TOKEN")
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch("subprocess.run", side_effect=AssertionError("trousseau lu")):
            with self.assertRaisesRegex(tasks.BoardError, "configuration d'environnement refusée"):
                tasks._jira_config()
        self.assertEqual([call for call in self.server.calls if call[0] == "PUT"], [])
        env.pop("CADRE_JIRA_SITE")
        env.pop("CADRE_JIRA_EMAIL")
        env["JIRA_API_TOKEN"] = "jeton-test"
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(tasks.BoardError, "écriture refusée sous agent"):
                tasks.jira_request("PUT", "/rest/api/3/issue/PROJ-1",
                                   body={"fields": {"summary": "x"}})
            label = "pris-par-banc-0123456789"
            for method in ("POST", "PATCH"):
                with self.subTest(method=method):
                    with self.assertRaisesRegex(tasks.BoardError, "écriture refusée sous agent"):
                        tasks.jira_request(method, "/rest/api/3/issue/PROJ-1",
                                           body={"update": {"labels": [{"add": label}]}})
            code, _ = tasks.jira_request("PUT", "/rest/api/3/issue/PROJ-1",
                                         body={"update": {"labels": [{"add": label}]}})
        self.assertEqual(code, 204)
        self.assertEqual([call[0] for call in self.server.calls].count("PUT"), 1)
        self.assertEqual(json.loads(self.server.calls[-1][3]), {"update": {"labels": [{"add": label}]}})
        self.assertEqual(task["jira_key"], "PROJ-1")

    def test_optout_trousseau_seul_ne_fait_pas_de_put(self) -> None:
        task = self.imported()
        env = dict(self.env, JIRA_AGENT_CLAIM="0")
        env.pop("JIRA_API_TOKEN")
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch("subprocess.run", side_effect=AssertionError("trousseau lu")):
            tasks.set_state(str(self.root), task["id"], "running", acteur={"auteur": {"nom": "Banc"}})
            self.assertIn("desactive", tasks.jira_claim_after_start(str(self.root), task["id"]))
            self.assertIn("desactive", tasks.jira_claim_retry(str(self.root), task["id"]))
        self.assertEqual([call for call in self.server.calls if call[0] == "PUT"], [])

    def test_issue_id_ascii_seul_et_http_exception_apres_start(self) -> None:
        bad = issue("PROJ-1", "١٠١")
        with self.assertRaisesRegex(tasks.BoardError, "id de ticket refusé"):
            tasks._jira_record(bad, self.server.url, "PROJ")
        task = self.imported()
        with mock.patch.dict(os.environ, self.env, clear=True):
            tasks.set_state(str(self.root), task["id"], "running", acteur={"auteur": {"nom": "Banc"}})
            with mock.patch.object(tasks._jira_transport(), "appel", side_effect=http.client.HTTPException()):
                self.assertIn("prise en attente", tasks.jira_claim_after_start(str(self.root), task["id"]))
        self.assertEqual(tasks.find(tasks.load(str(self.root)), task["id"])["state"], "running")

    def test_fournee_parent_envoie_un_seul_put(self) -> None:
        rc, out, err = self.main("new", "parent de banc", "--pas-un-defaut", "banc")
        self.assertEqual(rc, 0, err)
        tid = re.search(r"T-[0-9A-Z]+", out).group()
        plan_rel = "docs/tasks/plan.md"
        plan = self.root / plan_rel
        plan.parent.mkdir(parents=True)
        plan.write_text(f"# PLAN — {tid}\n\n## Étapes\n1. faire — angle mort: banc ?\n\n## Lots\n"
                        "LOT: A | dev-multi | moteur | src/a.py, src/b.py\n"
                        "LOT: B | dev-mono | doc | docs/b.md\n"
                        "INTÉGRATION: CHANGELOG.md\n", encoding="utf-8")
        specs = self.root / ".agents" / "state" / "specs" / "SPECS.json"
        specs.parent.mkdir(parents=True, exist_ok=True)
        specs.write_text(json.dumps({"entries": [{"id": "S-00000001", "task": tid, "kind": "decision",
                                                "title": "plan approuvé", "date": "2026-10-20",
                                                "text": f"plan={plan_rel} sha256={hashlib.sha256(plan.read_bytes()).hexdigest()}",
                                                "files": []}]}), encoding="utf-8")
        with tasks.board_lock(str(self.root)):
            data = tasks.load(str(self.root))
            parent = tasks.find(data, tid)
            parent.update(jira_site=self.server.url, jira_key="PROJ-1", jira_issue_id="101")
            tasks.save(str(self.root), data)
        actor = {"auteur": {"nom": "Banc", "email": "banc@example.test"}}
        with mock.patch.object(tasks, "precontrole_revendication", return_value=([], [])), \
                mock.patch.object(tasks, "acteur_de_la_commande", return_value=actor):
            rc, text, err = self.main("fournee", tid)
        self.assertEqual(rc, 0, err)
        self.assertIn("prise acquittee", text)
        lots = [t for t in tasks.load(str(self.root))["tasks"] if (t.get("fournee") or {}).get("parent") == tid]
        self.assertEqual(len(lots), 2)
        self.assertTrue(all("jira_key" not in lot for lot in lots))
        self.assertEqual([c[1] for c in self.server.calls if c[0] == "PUT"], ["/rest/api/3/issue/PROJ-1"])

    def test_accuse_ignore_si_acteur_change_pendant_put(self) -> None:
        task = self.imported()
        actor = {"auteur": {"nom": "Banc", "email": "banc@example.test"}}
        with mock.patch.dict(os.environ, self.env, clear=True):
            tasks.set_state(str(self.root), task["id"], "running", acteur=actor)

            def changer(_method: str, _path: str, **_kwargs: object) -> tuple[int, bytes]:
                with tasks.board_lock(str(self.root)):
                    data = tasks.load(str(self.root))
                    tasks.find(data, task["id"])["jira_claim_actor"] = {"auteur": {"nom": "Autre"}}
                    tasks.save(str(self.root), data)
                return 204, b""

            with mock.patch.object(tasks, "jira_request", side_effect=changer):
                text = tasks.jira_claim_retry(str(self.root), task["id"])
        self.assertIn("accusé ignoré", text)
        self.assertNotEqual(tasks.find(tasks.load(str(self.root)), task["id"])["jira_claim_status"], "acquitte")

    def test_accuse_ignore_si_retrait_change_pendant_put(self) -> None:
        task, alice, _bob = self.transfere()

        def changer(_method: str, _path: str, **_kwargs: object) -> tuple[int, bytes]:
            with tasks.board_lock(str(self.root)):
                data = tasks.load(str(self.root))
                tasks.find(data, task["id"])["jira_claim_retrait"] = [alice, "pris-par-tiers-0123456789"]
                tasks.save(str(self.root), data)
            return 204, b""

        with mock.patch.dict(os.environ, self.env, clear=True), \
                mock.patch.object(tasks, "jira_request", side_effect=changer):
            text = tasks.jira_claim_retry(str(self.root), task["id"])
        self.assertIn("accusé ignoré", text)
        self.assertEqual(tasks.find(tasks.load(str(self.root)), task["id"])["jira_claim_status"], "attente")

    # T-01M5HSV30ME8Z55K27T7ZPECGF (lot B) — transfert du label de prise (S-01M5HH8QMC, S-01M5HN38ES).
    ALICE = {"auteur": {"nom": "Alice", "email": "alice@example.test"}}
    BOB = {"auteur": {"nom": "Bob", "email": "bob@example.test"}}

    def transfere(self, env: dict[str, str] | None = None) -> tuple[dict, str, str]:
        """Alice prend et pose son label, puis la propriété passe à Bob (décidé par le lot A, simulé ici)."""
        task = self.imported()
        with mock.patch.dict(os.environ, self.env, clear=True):
            tasks.set_state(str(self.root), task["id"], "running", acteur=self.ALICE)
            self.assertIn("acquittee", tasks.jira_claim_retry(str(self.root), task["id"]))
        alice = tasks.find(tasks.load(str(self.root)), task["id"])["jira_claim_label"]
        with mock.patch.dict(os.environ, self.env if env is None else env, clear=True), \
                tasks.board_lock(str(self.root)):
            data = tasks.load(str(self.root))
            tasks.jira_prepare_claim(tasks.find(data, task["id"]), self.BOB)
            tasks.save(str(self.root), data)
        current = tasks.find(tasks.load(str(self.root)), task["id"])
        return current, alice, current["jira_claim_label"]

    def puts(self) -> list[tuple[str, dict]]:
        return [(c[1], json.loads(c[3])) for c in self.server.calls if c[0] == "PUT"]

    def test_transfert_un_put_retrait_ajout_attente_puis_retry(self) -> None:
        task, alice, bob = self.transfere()
        self.assertNotEqual(alice, bob)
        self.assertEqual((task["jira_claim_retrait"], task["jira_claim_status"]), ([alice], "attente"))
        with mock.patch.dict(os.environ, self.env, clear=True):
            self.server.put_status = 503
            self.assertIn("HTTP 503", tasks.jira_claim_after_start(str(self.root), task["id"]))
            pending = tasks.find(tasks.load(str(self.root)), task["id"])
            self.assertEqual((pending["jira_claim_retrait"], pending["jira_claim_status"]), ([alice], "attente"))
            self.server.put_status = 204
            rc, out, err = self.main("jira-claim", "--retry", task["id"])
        self.assertEqual((rc, err), (0, ""))
        self.assertIn("acquittee", out)
        attendu = ("/rest/api/3/issue/PROJ-1", {"update": {"labels": [{"remove": alice}, {"add": bob}]}})
        self.assertEqual(self.puts()[1:], [attendu, attendu], "un seul PUT par tentative, retrait + ajout")
        final = tasks.find(tasks.load(str(self.root)), task["id"])
        self.assertEqual((final["jira_claim_acquitte"], final["jira_claim_status"]), (bob, "acquitte"))
        self.assertNotIn("jira_claim_retrait", final)

    def test_retrait_sous_agent_refuse_requete_et_retry(self) -> None:
        task, alice, bob = self.transfere()
        agent = dict(self.env, CLAUDECODE="1")
        auth = "Basic " + base64.b64encode(b"agent@example.test:jeton-test").decode()
        before = len(self.puts())
        with mock.patch.dict(os.environ, agent, clear=True):
            with self.assertRaisesRegex(tasks.BoardError, "retrait de label refusé sous agent"):
                tasks.jira_request("PUT", "/rest/api/3/issue/PROJ-1", transfert=task,
                                   config=(self.server.url, True, auth),
                                   body={"update": {"labels": [{"remove": alice}, {"add": bob}]}})
        rc, out, err = self.main("jira-claim", "--retry", task["id"], env=agent)
        self.assertEqual((rc, err), (0, ""))
        self.assertIn("retrait de label réservé au pilote", out)
        self.assertEqual(len(self.puts()), before)
        self.assertEqual(tasks.find(tasks.load(str(self.root)), task["id"]), task)

    def test_retrait_arbitraire_ou_cle_etrangere_refuses_hors_agent(self) -> None:
        task, alice, bob = self.transfere()
        auth = "Basic " + base64.b64encode(b"agent@example.test:jeton-test").decode()
        config = (self.server.url, True, auth)
        hostiles = [
            ("PROJ-1", [{"remove": "pris-par-autre-0123456789"}, {"add": bob}], task, "hors transfert"),
            ("PROJ-2", [{"remove": alice}, {"add": bob}], task, "hors transfert"),
            ("PROJ-1", [{"remove": alice}, {"add": bob}], None, "hors transfert"),
            ("PROJ-1", [{"remove": alice}, {"add": "pris-par-autre-0123456789"}], task, "hors transfert"),
            ("PROJ-1", [{"set": [bob]}], task, "illisibles"),
        ]
        before = len(self.puts())
        with mock.patch.dict(os.environ, self.env, clear=True):
            for key, ops, transfert, motif in hostiles:
                with self.subTest(key=key, ops=ops, transfert=transfert is not None), \
                        self.assertRaisesRegex(tasks.BoardError, motif):
                    tasks.jira_request("PUT", f"/rest/api/3/issue/{key}", config=config, transfert=transfert,
                                       body={"update": {"labels": ops}})
            with self.assertRaisesRegex(tasks.BoardError, "labels remplacés"):
                tasks.jira_request("PUT", "/rest/api/3/issue/PROJ-1", config=config, transfert=task,
                                   body={"fields": {"labels": [bob]}})
            self.assertEqual(len(self.puts()), before)
            code, _ = tasks.jira_request("PUT", "/rest/api/3/issue/PROJ-1", config=config, transfert=task,
                                         body={"update": {"labels": [{"remove": alice}, {"add": bob}]}})
        self.assertEqual(code, 204)
        self.assertEqual(len(self.puts()), before + 1)

    def test_retrait_fusionne_hors_format_refuse_sans_put(self) -> None:
        """Une intention `jira_claim_retrait` FUSIONNÉE d'une autre copie est une donnée : chaque label
        retiré et le label ajouté repassent `_JIRA_LABEL.fullmatch` avant tout PUT, et la préparation ne
        reporte jamais un label hors format. MUTANTS : retirer la revalidation de `jira_request` (le PUT
        part), ou le filtre de `jira_prepare_claim` (le label hostile reste dans l'intention)."""
        task, alice, bob = self.transfere()
        auth = "Basic " + base64.b64encode(b"agent@example.test:jeton-test").decode()
        hostile = "PRIS-PAR-autre/../x"
        fusion = dict(task, jira_claim_retrait=[alice, hostile])
        before = len(self.puts())
        with mock.patch.dict(os.environ, self.env, clear=True):
            for ops, transfert in (([{"remove": hostile}, {"add": bob}], fusion),
                                   ([{"remove": alice}, {"add": hostile}],
                                    dict(fusion, jira_claim_label=hostile))):
                with self.subTest(ops=ops), self.assertRaisesRegex(tasks.BoardError, "hors transfert"):
                    tasks.jira_request("PUT", "/rest/api/3/issue/PROJ-1", config=(self.server.url, True, auth),
                                       transfert=transfert, body={"update": {"labels": ops}})
        self.assertEqual(len(self.puts()), before, "aucun PUT")
        tache = dict(task, jira_claim_retrait=[alice, hostile])
        with mock.patch.dict(os.environ, self.env, clear=True):
            tasks.jira_prepare_claim(tache, self.ALICE)
        self.assertEqual(tache.get("jira_claim_retrait"), [bob], "le label hostile n'est jamais reporté")

    def test_transfert_sans_jira_garde_la_propriete_locale(self) -> None:
        task, alice, _bob = self.transfere()
        nu = {"HOME": self.tmp.name, "PYTHONDONTWRITEBYTECODE": "1"}
        before = len(self.server.calls)
        with mock.patch.dict(os.environ, nu, clear=True), \
                mock.patch("subprocess.run", side_effect=AssertionError("trousseau lu")):
            self.assertIn("prise en attente", tasks.jira_claim_after_start(str(self.root), task["id"]))
        self.assertEqual(len(self.server.calls), before)
        kept = tasks.find(tasks.load(str(self.root)), task["id"])
        self.assertEqual(kept, task)
        self.assertEqual((kept["state"], kept["jira_claim_actor"], kept["jira_claim_retrait"]),
                         ("running", self.BOB, [alice]))

    def test_import_projete_par_le_resolveur_v3(self) -> None:
        repo = Path(__file__).resolve().parents[2]
        if str(repo) not in sys.path:
            sys.path.insert(0, str(repo))
            self.addCleanup(sys.path.remove, str(repo))
        from agentic_v3.db import run_export
        from agentic_v3.db.schema import DEFAULT_DB_PATH

        env = dict(self.env, CADRE_STATE_DIR=str(Path(self.tmp.name) / "state"),
                   AGENTS_EVENTS_DIR=str(Path(self.tmp.name) / "events"))
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(run_export, "_email_git", return_value="banc@example.test"), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as err:
            rc = tasks.main(["--root", str(self.root), "jira-import", "--project", "PROJ"])
            db = DEFAULT_DB_PATH(self.root)
        self.assertEqual(rc, 0, err.getvalue())
        self.assertTrue(db.is_file(), err.getvalue())
        ids = {t["id"] for t in tasks.load(str(self.root))["tasks"]}
        with sqlite3.connect(db) as conn:
            rows = conn.execute("SELECT req_id, status FROM task_projections WHERE req_id IN (?, ?)",
                                tuple(sorted(ids))).fetchall()
            failures = conn.execute("SELECT COUNT(*) FROM events_ledger WHERE event_type='BOARD_COMMAND_FAILED'").fetchone()[0]
        self.assertEqual(sorted(rows), [(tid, "PENDING") for tid in sorted(ids)])
        self.assertEqual(failures, 0)


# T-01M5GZ4VBPCJD3S2NPWQTB3XGP — deux imports d'un même ticket : la base d'un ajout/ajout (%O vide) est l'import.
CHAMPS_JIRA = ("task", "jira_updated", "jira_site", "jira_issue_id", "jira_created", "jira_key", "jira_url",
               "jira_type", "jira_parent_key")
ATTRIBUT = "/.agents/state/board/tasks/*.json merge=cadre-enregistrement\n"
DIVERGENT = r"^record/{} \(deux imports Jira divergents\)$"


def issue_parent() -> dict:
    item = issue("PROJ-7", "107", "Sous-tâche")
    item["fields"].update(parent={"key": "PROJ-1"}, issuetype={"name": "Sub-task"})
    return item


def enveloppe(record: dict, ops: list[str]) -> dict:
    return {"format": 1, "id": record["id"], "record": record, "sync_operations": sorted(ops)}


class BaseImportJiraTests(unittest.TestCase):
    def test_C9_base_synthetique_egale_l_import_reel(self) -> None:
        """C9 : la base reconstruite par le pilote (sous -I, sans `tasks`) == `_jira_record` du producteur réel."""
        for item in (issue("PROJ-1", "101"), issue_parent()):
            with self.subTest(cle=item["key"]):
                record, op = tasks._jira_record(item, SITE, "PROJ")
                nous = enveloppe(dict(record, state="running", stage="dev"), [op, "op-locale"])
                eux = enveloppe(dict(record, owner="banc", pas_un_defaut="relu"), [op])
                self.assertEqual(P.base_import_jira(nous, eux), enveloppe(record, [op]))
                self.assertEqual(op, P.operation_import_jira(SITE, item["id"]))
                self.assertEqual("jira_parent_key" in record, item["key"] == "PROJ-7")

    def test_C10_chaque_champ_de_la_liste_fermee_diverge_en_conflit_nomme(self) -> None:
        """C10 : chacun des 9 champs, modifié, retiré ou ajouté d'UN côté ⇒ conflit nommé, dans les deux sens."""
        self.assertEqual(P.CHAMPS_JIRA, CHAMPS_JIRA)
        record, op = tasks._jira_record(issue_parent(), SITE, "PROJ")
        for champ in CHAMPS_JIRA:
            autres = [dict(record, **{champ: f"{record.get(champ, '')}-diverge"})]
            autres.append({k: v for k, v in record.items() if k != champ} if champ in record
                          else dict(record, **{champ: "ajout"}))
            for autre in autres:
                for sens in ("nous", "eux"):
                    cotes = [enveloppe(record, [op]), enveloppe(autre, [op])]
                    if sens == "eux":
                        cotes.reverse()
                    with self.subTest(champ=champ, sens=sens, absent=champ not in autre), \
                            self.assertRaisesRegex(P.Conflit, DIVERGENT.format(champ)):
                        P.base_import_jira(*cotes)

    def test_C3_operation_d_import_exigee_des_deux_cotes_puis_union(self) -> None:
        record, op = tasks._jira_record(issue("PROJ-1", "101"), SITE, "PROJ")
        for ops in ([], ["op-locale"], [P.operation_import_jira(SITE, "999")]):
            for sens in ("nous", "eux"):
                cotes = [enveloppe(record, [op]), enveloppe(record, ops)]
                if sens == "nous":
                    cotes.reverse()
                with self.subTest(ops=ops, sens=sens), self.assertRaisesRegex(
                        P.Conflit, rf"^sync_operations \(opération d'import Jira absente : {sens}\)$"):
                    P.base_import_jira(*cotes)
        nous = enveloppe(dict(record, state="running", stage="dev"), [op, "op-a"])
        eux = enveloppe(dict(record, owner="banc"), [op, "op-b"])
        fusion = P.fusionner(P.base_import_jira(nous, eux), nous, eux)
        self.assertEqual(fusion["sync_operations"], sorted([op, "op-a", "op-b"]))
        self.assertEqual([fusion["record"][k] for k in ("state", "stage", "owner")], ["running", "dev", "banc"])

    def test_provenance_incomplete_conflicte_et_hors_jira_reste_hors_forme(self) -> None:
        record, op = tasks._jira_record(issue("PROJ-1", "101"), SITE, "PROJ")
        sans_url = {k: v for k, v in record.items() if k != "jira_url"}
        with self.assertRaisesRegex(P.Conflit, r"^record/jira_url \(provenance Jira incomplète\)$"):
            P.base_import_jira(enveloppe(sans_url, [op]), enveloppe(sans_url, [op]))
        with self.assertRaisesRegex(P.Conflit, r"^record \(import Jira contre un enregistrement absent\)$"):
            P.base_import_jira(enveloppe(record, [op]), {"format": 1, "id": record["id"], "record": None})
        local = {"id": "T-3", "owner": "", "stage": "", "state": "pending", "task": "t", "updated": "2026-10-20"}
        with self.assertRaisesRegex(P.HorsForme, "base vide hors import Jira"):
            P.base_import_jira(enveloppe(local, []), enveloppe(dict(local, stage="x"), []))
        for champ, valeur in (("jira_created", "pas-une-date"), ("jira_type", 7)):
            m = dict(record, **{champ: valeur})
            with self.subTest(champ=champ), self.assertRaisesRegex(
                    P.Conflit, rf"^record/{champ} \(provenance Jira incomplète\)$"):
                P.base_import_jira(enveloppe(m, [op]), enveloppe(m, [op]))

    def test_acteurs_sur_base_d_import_conflictent(self) -> None:
        """Deux `start` (ou deux `stage`) signés par deux acteurs, un par clone, sur la base d'import ⇒ conflit
        d'acteurs nommé : la base synthétique ne court-circuite pas `_juger_acteurs`."""
        record, op = tasks._jira_record(issue("PROJ-1", "101"), SITE, "PROJ")
        a = {"auteur": {"nom": "A", "email": "a@example.test"}, "copie": "c1"}
        b = {"auteur": {"nom": "B", "email": "b@example.test"}, "copie": "c2"}
        for cle, motif in (("start_actor", "double démarrage"), ("stage_actor", "stage signé par deux acteurs")):
            with self.subTest(cle=cle):
                nous = enveloppe(dict(record, state="running", stage="s", **{cle: a}), [op, "op-a"])
                eux = enveloppe(dict(record, state="running", stage="s", **{cle: b}), [op, "op-b"])
                with self.assertRaisesRegex(P.ConflitActeur, rf"^record/{cle} \({motif} :"):
                    P.fusionner(P.base_import_jira(nous, eux), nous, eux)

    def test_canal_reel_main_sur_base_vide(self) -> None:
        """Le pilote par son point d'entrée (%O vide) : compatible ⇒ rc 0 ; résumé divergent ⇒ rc 3 nommé ; hors
        Jira ⇒ repli texte, rc 3, « hors forme »."""
        record, op = tasks._jira_record(issue("PROJ-1", "101"), SITE, "PROJ")
        autre = tasks._jira_record(issue("PROJ-1", "101", "Autre"), SITE, "PROJ")[0]
        local = {"id": "T-3", "owner": "", "stage": "", "state": "pending", "task": "t", "updated": "2026-10-20"}
        cas = (("compatible", enveloppe(dict(record, stage="dev"), [op]), enveloppe(record, [op]), 0, ""),
               ("résumé", enveloppe(record, [op]), enveloppe(autre, [op]), 3,
                "conflit sur record/task (deux imports Jira divergents)"),
               ("hors jira", enveloppe(local, []), enveloppe(dict(local, stage="x"), []), 3,
                "entrée hors forme (base vide hors import Jira)"))
        with tempfile.TemporaryDirectory(prefix="jira-canal-") as tmp:
            for nom, nous, eux, attendu, message in cas:
                with self.subTest(cas=nom):
                    chemins = [Path(tmp) / n for n in ("o", "a", "b")]
                    for chemin, octets in zip(chemins, (b"", P.canonique(nous), P.canonique(eux))):
                        chemin.write_bytes(octets)
                    err = io.StringIO()
                    with contextlib.redirect_stderr(err):
                        rc = P.main(["pilote", *map(str, chemins), "7", "base", "nous", "eux"])
                    self.assertEqual(rc, attendu, err.getvalue())
                    self.assertIn(message, err.getvalue())
                    if attendu == 0:
                        self.assertEqual(json.loads(chemins[1].read_bytes())["record"]["stage"], "dev")


class FusionImportJiraGitTests(unittest.TestCase):
    """Vrais `git merge` sur le magasin en dossier : nu (C1), puis pilote posé par le VRAI `--installer` (C8)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.sonde = P.sonder_git()

    def setUp(self) -> None:
        tmp =tempfile.TemporaryDirectory(prefix="jira-fusion-", ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.genv = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.genv.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        self.env = {"CADRE_JIRA_SITE": SITE, "CADRE_JIRA_EMAIL": "agent@example.test", "JIRA_API_TOKEN": "jeton-test",
                    "HOME": str(self.tmp), "PYTHONDONTWRITEBYTECODE": "1", "PATH": os.environ.get("PATH", ""),
                    "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}

    def git(self, where: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", "-C", str(where), "-c", "user.name=banc", "-c", "user.email=banc@example.test",
                               "-c", "commit.gpgsign=false", "-c", f"core.hooksPath={os.devnull}", *args],
                              capture_output=True, text=True, timeout=120, env=self.genv)

    def ok(self, where: Path, *args: str) -> str:
        p = self.git(where, *args)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return p.stdout

    def socle(self) -> Path:
        """C8 : `.gitattributes` ET le pilote committés AVANT de cloner ; magasin en dossier, une tâche d'ancrage."""
        base = self.tmp / "base"
        (base / ".agents" / "bin").mkdir(parents=True)
        self.ok(base, "init", "-q", "-b", "main")
        (base / ".gitignore").write_text("/.agents/state/local/\n", encoding="utf-8")
        (base / ".gitattributes").write_text(ATTRIBUT, encoding="utf-8")
        (base / ".agents" / "bin" / "fusion_enregistrement.py").write_bytes(Path(P.__file__).read_bytes())
        board = base / ".agents" / "state" / "board"
        board.mkdir(parents=True)
        (board / "TASKS.json").write_bytes(P.canonique({"tasks": [
            {"id": "T-1", "owner": "", "stage": "", "state": "pending", "task": "ancre", "updated": "2026-10-01"}]}))
        tasks.migrate_store(str(base))
        self.ok(base, "add", "-A")
        self.ok(base, "commit", "-qm", "socle")
        return base

    def installer(self, clone: Path, depuis: str | None = None) -> None:
        class Terminal(io.StringIO):
            def isatty(self) -> bool:
                return True

        out = io.StringIO()
        with mock.patch.object(sys, "stdin", Terminal()), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(out):
            self.assertEqual(P.installer(racine=str(clone), depuis=depuis), 0, out.getvalue())
        self.assertEqual(self.verifier(clone), (0, "installé"))

    def verifier(self, clone: Path) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            rc = P.verifier(racine=str(clone))
        # Contrat de `--verifier` : la DERNIÈRE ligne est celle du board (la ligne `index : …` la précède).
        lignes = out.getvalue().strip().splitlines()
        return rc, (lignes[-1] if lignes else "").split(" :", 1)[0]

    def clones(self, base: Path, *, armer: bool) -> tuple[Path, Path]:
        if armer and self.sonde.get("verdict") != "tout présent":
            self.skipTest(f"pilote de fusion non installable ici : {P.raison_sonde(self.sonde)}")
        paire =(self.tmp / "a", self.tmp / "b")
        for clone in paire:
            self.ok(self.tmp, "clone", "-q", str(base), str(clone))
            if armer:
                self.installer(clone)
            else:
                self.assertEqual(self.git(clone, "config", "--get-regexp", r"^merge\.").stdout, "")
        return paire

    def verbe(self, root: Path, item: dict, *argv: str) -> None:
        out, err = io.StringIO(), io.StringIO()
        acteur = {"auteur": {"nom": "Banc", "email": "banc@example.test"}, "copie": root.name}
        page = json.dumps({"issues": [item], "isLast": True}).encode()
        with mock.patch.dict(os.environ, self.env, clear=True), \
                mock.patch.object(tasks, "replay_sync", return_value=0), \
                mock.patch.object(tasks._jira_transport(), "appel", return_value=(200, page)), \
                mock.patch.object(tasks, "precontrole_revendication", return_value=([], [])), \
                mock.patch.object(tasks, "acteur_de_la_commande", return_value=acteur), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = tasks.main(["--root", str(root), *argv])
        self.assertEqual(rc, 0, err.getvalue())

    def importer(self, root: Path, item: dict, *, editer: bool = False) -> str:
        self.verbe(root, item, "jira-import", "--project", "PROJ")
        tid = next(t["id"] for t in tasks.load(str(root))["tasks"] if t.get("jira_key") == item["key"])
        if editer:
            self.verbe(root, item, "start", tid)
            self.verbe(root, item, "stage", tid, "en cours")
        self.ok(root, "add", "-A")
        self.ok(root, "commit", "-qm", f"import {root.name}")
        return tid

    def croiser(self, a: Path, b: Path) -> None:
        for ici, la in ((a, b), (b, a)):
            self.ok(ici, "remote", "add", "autre", str(la))
            self.ok(ici, "fetch", "-q", "autre")

    @staticmethod
    def fichier(root: Path, tid: str) -> Path:
        return root / ".agents" / "state" / "board" / "tasks" / f"{tid}.json"

    def projection_v3(self, root: Path, tid: str) -> tuple[str, int]:
        repo = Path(__file__).resolve().parents[2]
        if str(repo) not in sys.path:
            sys.path.insert(0, str(repo))
            self.addCleanup(sys.path.remove, str(repo))
        from agentic_v3.db import run_export
        from agentic_v3.db.schema import DEFAULT_DB_PATH

        env = dict(self.env, CADRE_STATE_DIR=str(self.tmp / "state"), AGENTS_EVENTS_DIR=str(self.tmp / "events"))
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(run_export, "_email_git", return_value="banc@example.test"), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as err:
            rc = tasks.main(["--root", str(root), "replay-sync"])
            db = DEFAULT_DB_PATH(root)
        self.assertEqual(rc, 0, err.getvalue())
        with sqlite3.connect(db) as conn:
            statut = conn.execute("SELECT status FROM task_projections WHERE req_id = ?", (tid,)).fetchone()
            echecs = conn.execute("SELECT COUNT(*) FROM events_ledger "
                                  "WHERE event_type='BOARD_COMMAND_FAILED'").fetchone()[0]
        return (statut or ("absent",))[0], echecs

    def test_C1_merge_nu_meme_resume_dates_jira_differentes(self) -> None:
        """C1 (S-01M5HAKRWKB2N5NBPASPWN3R4Y) : aucune config `merge.*`, même résumé, `fields.updated` différent ⇒
        mêmes octets, `git merge` rc 0, aucun fichier en conflit."""
        a, b = self.clones(self.socle(), armer=False)
        plus_tard = issue("PROJ-1", "101")
        plus_tard["fields"]["updated"] = "2026-10-23T08:00:00.000+0000"
        tid = self.importer(a, issue("PROJ-1", "101"))
        self.assertEqual(self.importer(b, plus_tard), tid)
        self.assertEqual(self.fichier(a, tid).read_bytes(), self.fichier(b, tid).read_bytes())
        self.croiser(a, b)
        m = self.git(a, "merge", "--no-edit", "autre/main")
        self.assertEqual(m.returncode, 0, m.stdout + m.stderr)
        self.assertEqual(self.ok(a, "ls-files", "-u"), "")

    def test_C2_C7_C8_ajouts_compatibles_fusionnes_dans_les_deux_sens(self) -> None:
        """C2/C7/C8 : `start` + `stage` sur UN clone avant son commit, import seul sur l'autre ; chaque clone fusionne
        l'autre ⇒ rc 0, éditions locales gardées, mêmes octets ; `tasks.load` : une intention par opération, celle
        de l'import avec son `after` ; la projection V3 suit la fusion."""
        a, b = self.clones(self.socle(), armer=True)
        tid = self.importer(a, issue("PROJ-1", "101"), editer=True)
        plus_tard = issue("PROJ-1", "101")
        plus_tard["fields"]["updated"] = "2026-10-23T08:00:00.000+0000"
        self.assertEqual(self.importer(b, plus_tard), tid)
        edite = json.loads(self.fichier(a, tid).read_bytes())
        importe = json.loads(self.fichier(b, tid).read_bytes())
        operation = P.operation_import_jira(SITE, "101")
        self.croiser(a, b)
        octets = {}
        for ici in (a, b):
            with self.subTest(clone=ici.name):
                m = self.git(ici, "merge", "--no-edit", "autre/main")
                self.assertEqual(m.returncode, 0, m.stdout + m.stderr)
                self.assertEqual(self.ok(ici, "ls-files", "-u"), "")
                octets[ici.name] = self.fichier(ici, tid).read_bytes()
                fusion = json.loads(octets[ici.name])
                self.assertEqual(fusion["record"], edite["record"])
                self.assertEqual(fusion["sync_operations"],
                                 sorted(set(edite["sync_operations"]) | set(importe["sync_operations"])))
                data = tasks.load(str(ici))
                t = tasks.find(data, tid)
                self.assertEqual((t["state"], t["stage"], t["start_actor"], t["jira_claim_status"]),
                                 ("running", "en cours", edite["record"]["start_actor"], "attente"))
                vue = [intent["operation_id"] for intent in data["sync_outbox"]]
                outbox = ici / ".agents" / "state" / "board" / "sync_outbox"
                self.assertEqual(len(list(outbox.glob(f"*-{operation}.json"))), 2)
                self.assertLessEqual(set(fusion["sync_operations"]), set(vue))
                visible = next(i for i in data["sync_outbox"] if i["operation_id"] == operation)
                self.assertEqual((visible["after"]["task"], visible["after"]["state"]),
                                 (importe["record"]["task"], "pending"))
        self.assertEqual(octets["a"], octets["b"])
        self.assertEqual(self.projection_v3(a, tid), ("IN_DEV", 0))

    def test_C8_resumes_differents_conflit_nomme_dans_les_deux_sens(self) -> None:
        a, b = self.clones(self.socle(), armer=True)
        tid = self.importer(a, issue("PROJ-1", "101", "Résumé ancien"))
        self.assertEqual(self.importer(b, issue("PROJ-1", "101", "Résumé nouveau")), tid)
        self.croiser(a, b)
        for ici in (a, b):
            with self.subTest(clone=ici.name):
                m = self.git(ici, "merge", "--no-edit", "autre/main")
                self.assertEqual(m.returncode, 1, m.stdout + m.stderr)
                self.assertIn("conflit sur record/task (deux imports Jira divergents)", m.stdout + m.stderr)
                self.assertIn(f"{tid}.json", self.ok(ici, "ls-files", "-u"))
                self.ok(ici, "merge", "--abort")

    def test_C6_rollback_verifier_dit_perime_puis_installe(self) -> None:
        """C6 : le pilote rétabli par un commit ⇒ `--verifier` dit la copie périmée ; réinstallée ⇒ installée."""
        a, _ = self.clones(self.socle(), armer=True)
        pilote = a / ".agents" / "bin" / "fusion_enregistrement.py"
        pilote.write_bytes(pilote.read_bytes() + b"# retour arriere\n")
        self.ok(a, "commit", "-qam", "retour arriere du pilote")
        self.assertEqual(self.verifier(a), (1, "périmé"))
        self.installer(a, depuis="HEAD")


if __name__ == "__main__":
    unittest.main()
