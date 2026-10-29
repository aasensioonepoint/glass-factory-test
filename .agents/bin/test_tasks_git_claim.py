"""Revendication Git : dépôts jetables, appels Git bornés à --root.

Les scénarios de transition écrivent des commits réels ; les autres sondent le
précontrôle avec le même moteur que la CLI. Aucun remote de l'hôte n'est lu.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

import pytest

BIN = Path(__file__).resolve().parent
TASKS = BIN / "tasks.py"
TID = "T-012"
ALICE = {"auteur": {"nom": "Alice", "email": "alice@example.test"}, "copie": "aaaaaaaaaaaaaaaa"}
BOB = {"auteur": {"nom": "Bob", "email": "bob@example.test"}, "copie": "bbbbbbbbbbbbbbbb"}


def _module():
    spec = importlib.util.spec_from_file_location("tasks_git_claim_test", TASKS)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


tasks = _module()


def _marqueurs_agent() -> tuple[str, ...]:
    """Le tuple que `tasks._valider_reprise` lit (via `tracabilite_jira.agent_appelant`) : un banc
    qui l'écrit en dur oublierait un marqueur ajouté (Copilot, T-01M5MCXKHQS4BME9Z9VVSWD6VT)."""
    spec = importlib.util.spec_from_file_location("tasks_git_claim_tracabilite", BIN / "tracabilite_jira.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return tuple(module.AGENT_CALLER_MARKERS)


MARQUEURS_AGENT = _marqueurs_agent()


class Repo:
    def __init__(self, tmp_path: Path, *, monolith: bool = False) -> None:
        self.base = tmp_path
        self.root = tmp_path / "root"
        self.remote = tmp_path / "remote.git"
        self.root.mkdir()
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.env.update(HOME=str(tmp_path / "home"), CADRE_STATE_DIR=str(tmp_path / "cadre"),
                        AGENTS_EVENTS_DIR=str(tmp_path / "events"), GIT_CONFIG_NOSYSTEM="1",
                        GIT_CEILING_DIRECTORIES=str(tmp_path))
        for marker in MARQUEURS_AGENT:
            self.env.pop(marker, None)
        self.git(self.root, "init", "-q", "-b", "develop")
        self.git(self.root, "config", "user.name", "Bob")
        self.git(self.root, "config", "user.email", "bob@example.test")
        self.monolith = monolith
        self.record(self.root, "pending")
        self.commit(self.root, "base")
        self.git(tmp_path, "clone", "-q", "--bare", str(self.root), str(self.remote))
        self.git(self.root, "remote", "add", "origin", str(self.remote))
        self.git(self.root, "push", "-q", "-u", "origin", "develop")
        self.peer = tmp_path / "peer"
        self.git(tmp_path, "clone", "-q", str(self.remote), str(self.peer))
        self.git(self.peer, "config", "user.name", "Alice")
        self.git(self.peer, "config", "user.email", "alice@example.test")

    def git(self, where: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", "-C", str(where), *args], env=self.env,
                              text=True, capture_output=True, timeout=15, check=check)

    def record(self, where: Path, state: str, actor: dict | None = None,
               *, both: bool = False, hostile: bool = False) -> None:
        row = {"id": TID, "task": "claim", "owner": "dev-multi", "stage": "",
               "state": state, "updated": "2026-10-21"}
        if actor is not None:
            row["start_actor"] = actor
        path = where / ".agents/state/board/tasks" / f"{TID}.json"
        monolith = where / ".agents/state/board/TASKS.json"
        if not self.monolith or both:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{" if hostile else json.dumps({"format": 1, "id": TID, "record": row,
                                                          "sync_operations": []}), encoding="utf-8")
        if self.monolith or both:
            monolith.parent.mkdir(parents=True, exist_ok=True)
            monolith.write_text(json.dumps({"tasks": [row]}), encoding="utf-8")

    def commit(self, where: Path, message: str) -> str:
        self.git(where, "add", ".agents/state/board")
        self.git(where, "commit", "-qm", message)
        return self.git(where, "rev-parse", "HEAD").stdout.strip()

    def publish(self, branch: str = "develop") -> None:
        self.git(self.peer, "push", "-q", "origin", branch)

    def claim(self, *, branch: str = "develop", actor: dict = ALICE) -> str:
        if branch != "develop":
            self.git(self.peer, "checkout", "-qb", branch)
        self.record(self.peer, "running", actor)
        commit = self.commit(self.peer, "claim")
        self.publish(branch)
        return commit

    def check(self, actor: dict = BOB, *, fetch: bool = True) -> tuple[list[str], list[str]]:
        return tasks.precontrole_revendication(str(self.root), TID, actor, fetch=fetch)

    def cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, "-B", str(TASKS), "--root", str(self.root), *args],
                              env=self.env, text=True, capture_output=True, timeout=45)

    def cli_tty(self, response: str, *args: str) -> tuple[int, str]:
        import pty  # POSIX only: never imported while collecting on Windows
        master, slave = pty.openpty()
        try:
            proc = subprocess.Popen([sys.executable, "-B", str(TASKS), "--root", str(self.root), *args],
                                    env=self.env, stdin=slave, stderr=slave, stdout=subprocess.PIPE,
                                    text=True)
            os.close(slave)
            os.write(master, response.encode("utf-8"))
            proc.communicate(timeout=45)
            return proc.returncode, os.read(master, 8192).decode("utf-8", "replace")
        finally:
            os.close(master)


def test_upstream_equal_claim_after_fetch(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    repo.claim()
    result = repo.cli("start", TID)
    assert result.returncode == 2 and "REVENDICATION" in result.stderr
    assert repo.git(repo.root, "rev-parse", "origin/develop").stdout.strip() == repo.git(repo.peer, "rev-parse", "HEAD").stdout.strip()


def test_t012_stale_refs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = Repo(tmp_path)
    assert repo.check() == ([], [])
    repo.claim(branch="ancienne")
    repo.git(repo.peer, "checkout", "develop")
    repo.git(repo.peer, "merge", "--no-ff", "-qm", "merge ancienne", "ancienne")
    repo.record(repo.peer, "done")
    repo.commit(repo.peer, "ancienne close")
    repo.publish()
    # L'ancienne ref est un ancêtre strict de l'upstream : elle ne prévient plus.
    vues: list[str] = []
    original = tasks._rev_record
    def suivre(git, ref: str, tid: str):
        vues.append(ref)
        return original(git, ref, tid)
    monkeypatch.setattr(tasks, "_rev_record", suivre)
    refus, avis = repo.check()
    ancienne = repo.git(repo.peer, "rev-parse", "ancienne").stdout.strip()
    assert not refus and not any("ancienne" in a for a in avis) and ancienne not in vues
    repo.claim(branch="feature")
    repo.record(repo.peer, "running")
    repo.commit(repo.peer, "missing actor")
    repo.publish("feature")
    refus, avis = repo.check()
    assert not refus and any("auteur inconnu" in a for a in avis)


def test_merged_ref_filter_does_not_spawn_merge_base_per_ref(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = Repo(tmp_path)
    for number in range(12):
        repo.git(repo.peer, "commit", "--allow-empty", "-qm", f"ancestor {number}")
        repo.git(repo.peer, "push", "-q", "origin", f"HEAD:refs/heads/ancestor{number}")
    repo.publish()
    calls: list[tuple[str, ...]] = []
    original = tasks._RevGit.run
    def count(git, *args: str, **kwargs):
        calls.append(args)
        return original(git, *args, **kwargs)
    monkeypatch.setattr(tasks._RevGit, "run", count)
    assert repo.check() == ([], [])
    assert sum(call[0] == "merge-base" for call in calls) <= 1, calls


def test_same_author_other_copy_warns(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    repo.claim()
    refus, avis = repo.check({**ALICE, "copie": "cccccccccccccccc"})
    assert not refus and any("PRISE GIT (avis):" in a and "même auteur, autre copie" in a
                             and "aaaaaaaaaaaaaaaa / cccccccccccccccc" in a for a in avis)


def test_illformed_copy_warns(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    repo.claim(actor={**ALICE, "copie": {"bad": "copy"}})
    refus, avis = repo.check(ALICE)
    assert not refus and any("PRISE GIT (avis):" in a and "copie illisible ; même auteur" in a
                             for a in avis)


def test_same_email_distinct_name(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    repo.claim()
    refus, _ = repo.check({"auteur": {"nom": "Alicia", "email": "alice@example.test"}, "copie": None})
    assert refus


def test_monolith_remote_claim(tmp_path: Path) -> None:
    repo = Repo(tmp_path, monolith=True)
    repo.claim()
    assert repo.check()[0]


def test_coexisting_stores_agree(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    repo.record(repo.peer, "running", ALICE, both=True)
    repo.commit(repo.peer, "both")
    repo.publish()
    assert repo.check()[0]


def test_coexisting_stores_warn(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    repo.record(repo.peer, "running", ALICE, both=True)
    monolith = repo.peer / ".agents/state/board/TASKS.json"
    value = json.loads(monolith.read_text(encoding="utf-8"))
    value["tasks"][0]["state"] = "done"
    monolith.write_text(json.dumps(value), encoding="utf-8")
    repo.commit(repo.peer, "divergent")
    repo.publish()
    assert any(a.startswith("PRISE GIT (avis):") and "prise illisible" in a
               and "divergentes" in a for a in repo.check()[1])


def test_hostile_json_warns(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    repo.record(repo.peer, "running", ALICE, hostile=True)
    repo.commit(repo.peer, "hostile")
    repo.publish()
    assert any("illisible" in a for a in repo.check()[1])
    # Un acteur JSON valide mais hors forme ne devient pas un auteur humain.
    repo.record(repo.peer, "running", {"auteur": {"nom": {"imbrique": "Alice"},
                                                     "email": "alice@example.test"},
                                       "copie": {"imbrique": "copie"}})
    repo.commit(repo.peer, "hostile actor")
    repo.publish()
    refus, avis = repo.check()
    assert not refus and any("auteur inconnu" in a for a in avis)


@pytest.mark.parametrize("monolith, hostile", [
    (False, b"[]"), (False, b"{}"), (False, b"{"), (False, b"\xff"),
    (True, b"[]"), (True, b"{}"),
])
def test_hostile_history_warns(tmp_path: Path, monolith: bool, hostile: bytes) -> None:
    repo = Repo(tmp_path, monolith=monolith)
    repo.git(repo.peer, "checkout", "-qb", "feature")
    chemin = (repo.peer / ".agents/state/board/TASKS.json" if monolith else
              repo.peer / ".agents/state/board/tasks" / f"{TID}.json")
    chemin.write_bytes(hostile)
    repo.commit(repo.peer, "hostile middle commit")
    repo.record(repo.peer, "running", ALICE)
    repo.commit(repo.peer, "claim after hostile middle commit")
    repo.publish("feature")
    refus = repo.cli("start", TID)
    assert refus.returncode == 2 and "REVENDICATION:" in refus.stderr
    assert "PRISE GIT (avis):" in refus.stderr and "prise conservée" in refus.stderr
    assert "record historique illisible" in refus.stderr and "Traceback" not in refus.stderr
    levee = repo.cli("start", TID, "--sans-revendication", "historique hostile")
    assert levee.returncode == 2 and "--reprise" in levee.stderr


def test_oversize_blob_warns(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    repo.record(repo.peer, "running", ALICE)
    path = repo.peer / ".agents/state/board/tasks" / f"{TID}.json"
    path.write_bytes(path.read_bytes() + b" " * (tasks.REVENDICATION_BLOB_MAX + 1))
    repo.commit(repo.peer, "oversize")
    repo.publish()
    assert any("4 Mio" in a for a in repo.check()[1])


def test_v3_bridge_warns(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    repo.claim(actor={"auteur": {"nom": None, "email": None}, "copie": None})
    assert any(a.startswith("PRISE GIT (avis):") and "auteur inconnu ou pont V3" in a
               for a in repo.check()[1])


def test_upstream_metadata_edit_keeps_claim(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    repo.claim()
    path = repo.peer / ".agents/state/board/tasks" / f"{TID}.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value["record"]["updated"] = "2026-10-22"
    path.write_text(json.dumps(value), encoding="utf-8")
    repo.commit(repo.peer, "metadata")
    repo.publish()
    assert repo.check()[0]


def test_upstream_stale_done_keeps_claim(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    repo.record(repo.peer, "running", ALICE)
    repo.commit(repo.peer, "ancien cycle")
    repo.record(repo.peer, "done")
    repo.commit(repo.peer, "ancien done")
    repo.publish()
    repo.claim(branch="feature")
    assert repo.check()[0]


def test_upstream_exit_before_claim_keeps_claim(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    repo.record(repo.peer, "running", ALICE)
    repo.commit(repo.peer, "old running")
    repo.record(repo.peer, "pending")
    repo.commit(repo.peer, "old exit")
    repo.publish()
    repo.claim(branch="feature")
    assert repo.check()[0]


def test_upstream_explicit_exit_supersedes(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    repo.claim(branch="feature")
    repo.git(repo.peer, "checkout", "develop")
    repo.git(repo.peer, "merge", "--no-ff", "-qm", "merge claim", "feature")
    repo.record(repo.peer, "pending")
    repo.commit(repo.peer, "exit")
    repo.publish()
    repo.git(repo.peer, "checkout", "feature")
    path = repo.peer / ".agents/state/board/tasks" / f"{TID}.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value["record"]["updated"] = "2026-10-22"
    path.write_text(json.dumps(value), encoding="utf-8")
    repo.commit(repo.peer, "feature metadata after merge")
    repo.publish("feature")
    assert not repo.check()[0]


def test_upstream_done_supersedes(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    repo.claim(branch="feature")
    repo.git(repo.peer, "checkout", "develop")
    repo.git(repo.peer, "merge", "--no-ff", "-qm", "merge claim", "feature")
    repo.record(repo.peer, "done")
    repo.commit(repo.peer, "done")
    repo.publish()
    repo.git(repo.peer, "checkout", "feature")
    path = repo.peer / ".agents/state/board/tasks" / f"{TID}.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value["record"]["updated"] = "2026-10-22"
    path.write_text(json.dumps(value), encoding="utf-8")
    repo.commit(repo.peer, "feature metadata after merge")
    repo.publish("feature")
    assert not repo.check()[0]


def test_upstream_done_through_no_ff_merge_supersedes(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    repo.claim()
    repo.git(repo.peer, "checkout", "-qb", "alice/extra")
    (repo.peer / "extra.txt").write_text("extra\n", encoding="utf-8")
    repo.git(repo.peer, "add", "extra.txt")
    repo.git(repo.peer, "commit", "-qm", "extra")
    repo.publish("alice/extra")
    repo.git(repo.peer, "checkout", "develop")
    repo.git(repo.peer, "checkout", "-qb", "alice/done")
    repo.record(repo.peer, "done")
    repo.commit(repo.peer, "done")
    repo.git(repo.peer, "checkout", "develop")
    repo.git(repo.peer, "merge", "--no-ff", "-qm", "merge done", "alice/done")
    repo.publish()
    assert repo.check() == ([], [])


def test_unknown_author_skips_history_with_bounded_git_calls(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = Repo(tmp_path)
    repo.claim(branch="feature", actor={"auteur": {"nom": None, "email": None}, "copie": None})
    path = repo.peer / ".agents/state/board/tasks" / f"{TID}.json"
    for number in range(16):
        value = json.loads(path.read_text(encoding="utf-8"))
        value["sync_operations"] = [number]
        path.write_text(json.dumps(value), encoding="utf-8")
        repo.commit(repo.peer, f"metadata {number}")
    repo.publish("feature")
    calls: list[tuple[str, ...]] = []
    original = tasks._RevGit.run
    def count(git, *args: str, **kwargs):
        calls.append(args)
        return original(git, *args, **kwargs)
    monkeypatch.setattr(tasks._RevGit, "run", count)
    refus, avis = repo.check()
    assert not refus and any("PRISE GIT (avis):" in a and "auteur inconnu" in a for a in avis)
    assert len(calls) <= 20, calls
    assert not any(call[0] in {"log", "rev-list"} for call in calls)


def test_latest_running_transition_keeps_claim(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    repo.record(repo.peer, "running", ALICE)
    repo.commit(repo.peer, "first running")
    repo.record(repo.peer, "done")
    repo.commit(repo.peer, "first done")
    repo.publish()
    repo.claim(branch="feature")
    assert repo.check()[0], "le done du premier cycle ne libère pas la seconde prise"


def test_local_foreign_actor_offline(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    repo.record(repo.root, "running", ALICE)
    assert repo.check(fetch=False)[0]


def test_same_actor_resume(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    repo.record(repo.root, "running", BOB)
    assert repo.check(fetch=False) == ([], [])


def test_timeout_term_no_kill(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = Repo(tmp_path)
    signaux: list[int] = []
    original = subprocess.Popen.send_signal
    def capture(proc, sig):
        signaux.append(sig)
        return original(proc, sig)
    monkeypatch.setattr(subprocess.Popen, "send_signal", capture)
    git = tasks._RevGit(str(repo.root))
    with pytest.raises(TimeoutError):
        git.run("-c", "alias.pause=!sleep 1", "pause", timeout=0.01)
    assert signaux == [tasks.signal.SIGTERM]


def test_persistent_git_stops_later_fetches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = Repo(tmp_path)
    appels: list[str] = []
    class GitBloque:
        def __init__(self, root: str) -> None:
            self.root, self.persistant = root, False
            self.env = {}
        def run(self, *args: str, **_kw) -> tuple[int, bytes]:
            if args[0] == "rev-parse":
                return 0, (str(repo.root) + "\n").encode()
            if args[0] == "remote":
                return 0, b"premier\nsecond\n"
            if args[0] == "config":
                return 0, b"ssh\n"
            if "fetch" in args:
                appels.append(args[-1])
                self.persistant = True
                raise TimeoutError("Git persistant")
            raise AssertionError(args)
    monkeypatch.setattr(tasks, "_RevGit", GitBloque)
    refus, avis = repo.check()
    assert not refus and appels == ["premier"]
    assert any(a.startswith("PRISE GIT (avis): fetch premier :") and "Git persistant" in a
               for a in avis)


def test_alias_deduplicated(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    repo.claim()
    repo.git(repo.root, "fetch", "-q", "origin")
    repo.git(repo.root, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/develop")
    refus, _ = repo.check()
    assert len(refus) == 1 and "refs/remotes/origin/develop" in refus[0]
    assert "origin/HEAD" not in refus[0]


def test_git_environment_is_confined(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = Repo(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    repo.git(other, "init", "-q")
    inherited = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
                 "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_COMMON_DIR", "GIT_NAMESPACE", "GIT_PREFIX")
    for key in inherited:
        monkeypatch.setenv(key, str(other / ".git"))
    git = tasks._RevGit(str(repo.root))
    assert all(key not in git.env for key in inherited)
    assert git.env["GIT_CEILING_DIRECTORIES"] == str(tmp_path)
    assert git.env["GIT_TERMINAL_PROMPT"] == "0"
    repo.claim()
    assert repo.check()[0], "GIT_DIR hérité ne doit pas détourner le fetch du dépôt --root"
    assert repo.git(repo.root, "rev-parse", "origin/develop").stdout.strip() == repo.git(repo.peer, "rev-parse", "HEAD").stdout.strip()


def test_foreign_toplevel_stops_before_fetch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = Repo(tmp_path)
    appels: list[str] = []
    class GitHorsRoot:
        def __init__(self, root: str) -> None:
            self.persistant = False
        def run(self, *args: str, **_kw) -> tuple[int, bytes]:
            appels.append(args[0])
            return 0, (str(repo.base) + "\n").encode()
    monkeypatch.setattr(tasks, "_RevGit", GitHorsRoot)
    assert repo.check() == ([], [])
    assert appels == ["rev-parse"]


@pytest.mark.parametrize("inherited", [False, True])
def test_ssh_batchmode_and_prompt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, inherited: bool) -> None:
    repo = Repo(tmp_path)
    repo.git(repo.root, "config", "core.sshCommand", "ssh -F custom-config")
    if inherited:
        monkeypatch.setenv("GIT_SSH_COMMAND", "ssh -F inherited-config")
    original = tasks._RevGit
    instances = []
    commandes: list[list[str]] = []
    original_popen = subprocess.Popen
    def suivre_commande(argv, *args, **kwargs):
        commandes.append(argv)
        return original_popen(argv, *args, **kwargs)
    monkeypatch.setattr(tasks.subprocess, "Popen", suivre_commande)
    def capture(root: str):
        git = original(root)
        instances.append(git)
        return git
    monkeypatch.setattr(tasks, "_RevGit", capture)
    repo.check()
    env = instances[0].env
    assert env["GIT_SSH_COMMAND"] == ("ssh -F inherited-config" if inherited else "ssh -F custom-config") + " -oBatchMode=yes"
    assert env["GIT_TERMINAL_PROMPT"] == "0" and env["GCM_INTERACTIVE"] == "never"
    fetches = [argv for argv in commandes if "fetch" in argv]
    assert fetches and all(argv[-2:] == ["--", "origin"] for argv in fetches)


def test_inherited_git_ssh_keeps_priority(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = Repo(tmp_path)
    repo.git(repo.root, "config", "core.sshCommand", "ssh -F custom-config")
    monkeypatch.setenv("GIT_SSH", "inherited-ssh")
    monkeypatch.setenv("GIT_SSH_COMMAND", "ssh -F should-not-override")
    instances = []
    original = tasks._RevGit
    def capture(root: str):
        git = original(root)
        instances.append(git)
        return git
    monkeypatch.setattr(tasks, "_RevGit", capture)
    repo.check()
    assert instances[0].env["GIT_SSH"] == "inherited-ssh"
    assert "GIT_SSH_COMMAND" not in instances[0].env


def test_default_ssh_batchmode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = Repo(tmp_path)
    monkeypatch.delenv("GIT_SSH", raising=False)
    monkeypatch.delenv("GIT_SSH_COMMAND", raising=False)
    instances = []
    original = tasks._RevGit
    def capture(root: str):
        git = original(root)
        instances.append(git)
        return git
    monkeypatch.setattr(tasks, "_RevGit", capture)
    repo.check()
    assert instances[0].env["GIT_SSH_COMMAND"] == "ssh -oBatchMode=yes"


def test_programming_keyerror_is_not_git_unavailable(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = Repo(tmp_path)
    def broken(_git, *_args, **_kwargs):
        raise KeyError("programming error")
    monkeypatch.setattr(tasks._RevGit, "run", broken)
    with pytest.raises(KeyError, match="programming error"):
        repo.check()


def test_budget_expiry_is_visible(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = Repo(tmp_path)
    repo.claim()
    original = tasks._rev_transition
    def expire(git, *args):
        result = original(git, *args)
        git.fin = tasks.time.monotonic() - 1
        return result
    monkeypatch.setattr(tasks, "_rev_transition", expire)
    refus, avis = repo.check()
    assert refus and any("PRISE GIT (avis): budget Git épuisé" in line for line in avis)


def test_history_budget_keeps_claim(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = Repo(tmp_path)
    repo.claim()
    monkeypatch.setattr(tasks, "REVENDICATION_HISTOIRE_MAX", 0)
    refus, avis = repo.check()
    assert refus and any("budget historique" in a for a in avis)


def test_control_chars_escaped(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    repo.claim(actor={"auteur": {"nom": "Alice\nX", "email": "alice@example.test"}, "copie": None})
    refus, _ = repo.check()
    assert refus and "\\u000a" in refus[0] and "Alice\nX" not in refus[0]


def test_refusal_is_pure(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    repo.record(repo.root, "running", ALICE)
    path = repo.root / ".agents/state/board/tasks" / f"{TID}.json"
    before = path.read_bytes()
    result = repo.cli("start", TID)
    assert result.returncode == 2 and "REVENDICATION" in result.stderr
    assert path.read_bytes() == before
    assert not (repo.root / ".agents/state/local/focus.json").exists()
    assert not (repo.root / ".agents/state/local/sessions").exists()


def test_warning_rc2_is_not_a_claim_refusal(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    repo.git(repo.root, "remote", "remove", "origin")  # démarrage hors ligne : l'avis Git précède AMONT_OUVERT
    path = repo.root / ".agents/state/board/tasks" / f"{TID}.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["record"]["depends_on"] = ["T-013"]
    path.write_text(json.dumps(doc), encoding="utf-8")
    other = {"id": "T-013", "task": "amont", "owner": "dev-multi", "stage": "",
             "state": "pending", "updated": "2026-10-21"}
    (path.parent / "T-013.json").write_text(json.dumps({"format": 1, "id": "T-013",
                                                      "record": other, "sync_operations": []}), encoding="utf-8")
    result = repo.cli("start", TID)
    assert result.returncode == 2 and "AMONT_OUVERT" in result.stderr
    assert "PRISE GIT (avis): sans upstream" not in result.stderr
    assert "REVENDICATION" not in result.stderr
    usage = repo.cli("start", TID, "--sans-revendication", " ")
    assert usage.returncode == 2 and "--sans-revendication est retiré" in usage.stderr


def test_warning_labels_for_remote_limits_and_failures(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    for number in range(6):
        repo.git(repo.root, "remote", "add", f"other{number}", str(repo.remote))
    assert any(a.startswith("PRISE GIT (avis): plus de six remotes") for a in repo.check()[1])
    repo.git(repo.root, "remote", "set-url", "origin", str(tmp_path / "absent.git"))
    assert any(a.startswith("PRISE GIT (avis): fetch origin échoué") for a in repo.check()[1])


def test_warning_labels_for_upstream_and_git_unavailable(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = Repo(tmp_path)
    repo.git(repo.root, "branch", "--unset-upstream")
    assert any(a.startswith("PRISE GIT (avis): sans upstream") for a in repo.check()[1])
    def unavailable(_git, *_args, **_kwargs):
        raise OSError("missing git")
    monkeypatch.setattr(tasks._RevGit, "run", unavailable)
    assert any(a.startswith("PRISE GIT (avis): Git indisponible") for a in repo.check()[1])


def test_override_retired_for_start_and_fournee(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    repo.record(repo.root, "running", ALICE)
    result = repo.cli("start", TID, "--sans-revendication", "décision pilote")
    assert result.returncode == 2 and "--reprise" in result.stderr
    result = repo.cli("fournee", TID, "--sans-revendication", "décision pilote")
    assert result.returncode == 2 and "--reprise" in result.stderr
    assert tasks.find(tasks.load(str(repo.root)), TID)["start_actor"] == ALICE


def test_published_transfer_supersedes_stale_alice_claim(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    repo.record(repo.root, "running", ALICE)
    repo.claim(branch="alice")
    repo.git(repo.peer, "checkout", "develop")
    repo.git(repo.peer, "merge", "--no-ff", "-qm", "merge alice", "alice")
    repo.record(repo.peer, "running", BOB)
    repo.commit(repo.peer, "transfer to Bob")
    repo.publish()
    repo.git(repo.peer, "checkout", "alice")
    path = repo.peer / ".agents/state/board/tasks" / f"{TID}.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value["record"]["updated"] = "2026-10-22"
    path.write_text(json.dumps(value), encoding="utf-8")
    repo.commit(repo.peer, "old pilot pushed after transfer")
    repo.publish("alice")
    result = repo.cli("start", TID)
    assert result.returncode == 0, result.stderr
    # MUTANT : avis fixe « prise levée » sur le chemin de transfert ⇒ rouge.
    assert "REVENDICATION: ancien pilote a poussé après reprise" in result.stderr
    assert tasks.find(tasks.load(str(repo.root)), TID)["start_actor"]["auteur"] == BOB["auteur"]


def test_no_owner_and_no_identity_starts_without_property(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    repo.git(repo.root, "config", "--unset", "user.name")
    repo.git(repo.root, "config", "--unset", "user.email")
    result = repo.cli("start", TID)
    assert result.returncode == 0, result.stderr
    assert "auteur inconnu" in result.stderr
    assert "start_actor" not in tasks.find(tasks.load(str(repo.root)), TID)


def test_reprise_without_tty_is_pure_and_names_windows_remedy(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    repo.record(repo.root, "running", ALICE)
    chemin = repo.root / ".agents/state/board/tasks" / f"{TID}.json"
    avant = chemin.read_bytes()
    result = repo.cli("start", TID, "--reprise", "transfert approuvé")
    assert result.returncode == 2 and "REVENDICATION" in result.stderr
    assert "winpty bash .agents/pyrun.sh .agents/bin/tasks.py" in result.stderr
    assert chemin.read_bytes() == avant
    fournee = repo.cli("fournee", TID, "--reprise", "transfert approuvé")
    assert fournee.returncode == 2
    assert f".agents/bin/tasks.py fournee {TID} --reprise" in fournee.stderr
    assert chemin.read_bytes() == avant


@pytest.mark.skipif(os.name == "nt", reason="pty POSIX seulement")
def test_reprise_tty_confirmation_and_agent_marker(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    repo.record(repo.root, "running", ALICE)
    chemin = repo.root / ".agents/state/board/tasks" / f"{TID}.json"
    avant = chemin.read_bytes()
    rc, _ = repo.cli_tty("T-incorrect\n", "start", TID, "--reprise", "passation")
    assert rc == 2 and chemin.read_bytes() == avant
    repo.env["AGENTS_HOOK_HOST"] = "codex"
    rc, _ = repo.cli_tty(TID + "\n", "start", TID, "--reprise", "passation")
    assert rc == 2 and chemin.read_bytes() == avant
    repo.env.pop("AGENTS_HOOK_HOST")
    rc, sortie = repo.cli_tty(TID + "\n", "start", TID, "--reprise", "passation")
    assert rc == 0, sortie
    row = tasks.find(tasks.load(str(repo.root)), TID)
    assert row["start_actor"]["auteur"] == BOB["auteur"]
    assert "[REPRISE : passation]" in row["stage"]


@pytest.mark.parametrize("marqueur", ["COPILOT_CLI", "COPILOT_AGENT_SESSION_ID"])
def test_reprise_refusee_sous_marqueur_copilot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                               marqueur: str) -> None:
    """Copilot CLI pose COPILOT_CLI=1 et COPILOT_AGENT_SESSION_ID dans le shell de l'agent (mesuré,
    1.0.96) : la reprise y est refusée comme sous Claude Code, TTY et saisie exacte pourtant franchis,
    board intact, le marqueur NOMMÉ. MUTANT : marqueur retiré du tuple de tracabilite_jira ⇒ reprise
    ACCEPTÉE (M8)."""
    import io
    assert marqueur in MARQUEURS_AGENT
    repo = Repo(tmp_path)
    repo.record(repo.root, "running", ALICE)
    chemin = repo.root / ".agents/state/board/tasks" / f"{TID}.json"
    avant = chemin.read_bytes()

    class Terminal(io.StringIO):
        def isatty(self) -> bool:
            return True

    for nom in (*MARQUEURS_AGENT, "CODEX_SANDBOX", "CODEX_THREAD_ID"):
        monkeypatch.delenv(nom, raising=False)
    monkeypatch.setenv(marqueur, "1")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setattr(tasks.sys, "stdin", Terminal(TID + "\n"))
    stderr = Terminal()
    monkeypatch.setattr(tasks.sys, "stderr", stderr)
    monkeypatch.setattr(tasks.sys, "stdout", io.StringIO())
    assert tasks.main(["--root", str(repo.root), "start", TID, "--reprise", "passation"]) == 2, stderr.getvalue()
    assert f"marqueur {marqueur}" in stderr.getvalue(), stderr.getvalue()
    assert chemin.read_bytes() == avant


def test_reprise_import_failure_is_named(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib.util
    import io
    repo = Repo(tmp_path)
    repo.record(repo.root, "running", ALICE)
    chemin = repo.root / ".agents/state/board/tasks" / f"{TID}.json"
    avant = chemin.read_bytes()
    class Terminal(io.StringIO):
        def isatty(self) -> bool:
            return True
    def broken(*_args, **_kwargs):
        raise ImportError("broken")
    monkeypatch.setattr(tasks.sys, "stdin", Terminal(TID + "\n"))
    stderr = Terminal()
    monkeypatch.setattr(tasks.sys, "stderr", stderr)
    monkeypatch.setattr(importlib.util, "spec_from_file_location", broken)
    assert tasks.main(["--root", str(repo.root), "start", TID, "--reprise", "passation"]) == 2
    assert "REVENDICATION" in stderr.getvalue() and "ImportError" in stderr.getvalue()
    assert chemin.read_bytes() == avant


def test_stale_pilot_cannot_take_back_published_transfer(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    repo.record(repo.root, "running", ALICE)
    repo.claim(branch="alice")
    repo.git(repo.peer, "checkout", "develop")
    repo.git(repo.peer, "merge", "--no-ff", "-qm", "merge alice", "alice")
    repo.record(repo.peer, "running", BOB)
    repo.commit(repo.peer, "transfer to Bob")
    repo.publish()
    repo.git(repo.root, "config", "user.name", "Alice")
    repo.git(repo.root, "config", "user.email", "alice@example.test")
    chemin = repo.root / ".agents/state/board/tasks" / f"{TID}.json"
    avant = chemin.read_bytes()
    result = repo.cli("start", TID)
    assert result.returncode == 2 and "REVENDICATION" in result.stderr
    assert chemin.read_bytes() == avant


def test_transfer_proof_revalidated_under_lock(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    repo.record(repo.root, "running", ALICE)
    chemin = repo.root / ".agents/state/board/tasks" / f"{TID}.json"
    avant = chemin.read_bytes()
    with pytest.raises(tasks.BoardError, match="REVENDICATION.*changée"):
        tasks.set_state(str(repo.root), TID, "running", acteur=BOB,
                        preuve_reprise={"ancien": {"auteur": {"nom": "Eve", "email": "eve@example.test"}},
                                        "nouveau": BOB})
    assert chemin.read_bytes() == avant


def test_old_cycle_transfer_does_not_unlock_new_claim(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    repo.record(repo.root, "running", ALICE)
    repo.record(repo.peer, "running", ALICE)
    repo.commit(repo.peer, "first Alice cycle")
    repo.record(repo.peer, "running", BOB)
    repo.commit(repo.peer, "first transfer")
    repo.record(repo.peer, "done")
    repo.commit(repo.peer, "first done")
    repo.record(repo.peer, "pending")
    repo.commit(repo.peer, "next pending")
    repo.record(repo.peer, "running", BOB)
    repo.commit(repo.peer, "new Bob claim")
    repo.publish()
    result = repo.cli("start", TID)
    assert result.returncode == 2 and "REVENDICATION" in result.stderr
    assert tasks.find(tasks.load(str(repo.root)), TID)["start_actor"] == ALICE


def test_pending_task_keeps_its_pilot_until_confirmed_transfer(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    repo.record(repo.root, "pending", ALICE)
    chemin = repo.root / ".agents/state/board/tasks" / f"{TID}.json"
    avant = chemin.read_bytes()
    denied = repo.cli("start", TID)
    assert denied.returncode == 2 and "REVENDICATION" in denied.stderr
    assert chemin.read_bytes() == avant
    no_tty = repo.cli("start", TID, "--reprise", "passation")
    assert no_tty.returncode == 2 and chemin.read_bytes() == avant
    if os.name != "nt":
        rc, sortie = repo.cli_tty(TID + "\n", "start", TID, "--reprise", "passation")
        assert rc == 0, sortie
        assert tasks.find(tasks.load(str(repo.root)), TID)["start_actor"]["auteur"] == BOB["auteur"]


def test_old_pilot_pushing_after_reprise_only_warns(tmp_path: Path) -> None:
    """Bob reprend sur SA copie, puis Alice pousse encore sur sa branche : le transfert porté par HEAD
    reconnaît la prise ancienne — avertissement, rc 0, jamais un refus de Bob sur sa propre tâche.
    MUTANT : ne chercher le transfert que sur les refs distantes ⇒ rc 2."""
    if os.name == "nt":
        pytest.skip("pty POSIX seul")
    repo = Repo(tmp_path)
    repo.claim(branch="alice")
    repo.git(repo.root, "fetch", "-q", "origin")
    repo.git(repo.root, "merge", "-q", "--no-ff", "-m", "merge alice", "origin/alice")
    rc, sortie = repo.cli_tty(TID + "\n", "start", TID, "--reprise", "passation")
    assert rc == 0, sortie
    assert tasks.find(tasks.load(str(repo.root)), TID)["start_actor"]["auteur"] == BOB["auteur"]
    repo.commit(repo.root, "Bob takes over")
    repo.git(repo.root, "push", "-q", "origin", "develop")
    repo.git(repo.peer, "checkout", "alice")
    chemin = repo.peer / ".agents/state/board/tasks" / f"{TID}.json"
    valeur = json.loads(chemin.read_text(encoding="utf-8"))
    valeur["record"]["updated"] = "2026-10-22"
    chemin.write_text(json.dumps(valeur), encoding="utf-8")
    repo.commit(repo.peer, "old pilot pushed after transfer")
    repo.publish("alice")
    again = repo.cli("start", TID)
    assert again.returncode == 0, again.stderr
    # Sans pointe constatée (branche fusionnée avant la reprise) : MUTANT « jamais poussé » ⇒ rouge.
    assert "REVENDICATION: ancien pilote a poussé après reprise" in again.stderr


def test_reprise_names_current_owner_before_confirmation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """La question NOMME le propriétaire courant, et chaque refus levé est dit avant la saisie.
    MUTANTS : invite sans propriétaire, refus levés tus."""
    import io
    repo = Repo(tmp_path)
    repo.record(repo.root, "running", ALICE)

    class Terminal(io.StringIO):
        def isatty(self) -> bool:
            return True

    for nom in (*MARQUEURS_AGENT, "CODEX_SANDBOX", "CODEX_THREAD_ID"):
        monkeypatch.delenv(nom, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setattr(tasks.sys, "stdin", Terminal(TID + "\n"))
    stderr = Terminal()
    monkeypatch.setattr(tasks.sys, "stderr", stderr)
    monkeypatch.setattr(tasks.sys, "stdout", io.StringIO())
    assert tasks.main(["--root", str(repo.root), "start", TID, "--reprise", "passation"]) == 0
    texte = stderr.getvalue()
    invite = texte[texte.index("REVENDICATION : reprise de"):]
    assert "propriétaire courant {nom: Alice, email: alice@example.test}" in invite, texte
    assert "sur board local" in texte[:texte.index(invite)] and "levée par --reprise" in texte, texte


def _alice_pousse_encore(repo: Repo) -> None:
    """L'ancien pilote pousse un commit de plus sur sa branche publiée : même cycle, même transition."""
    repo.git(repo.peer, "checkout", "-q", "alice")
    chemin = repo.peer / ".agents/state/board/tasks" / f"{TID}.json"
    valeur = json.loads(chemin.read_text(encoding="utf-8"))
    valeur["record"]["updated"] = "2026-10-22"
    chemin.write_text(json.dumps(valeur), encoding="utf-8")
    repo.commit(repo.peer, "old pilot pushed after transfer")
    repo.publish("alice")


def _merge_mixte_chez_alice(repo: Repo) -> None:
    """Alice fusionne un develop pending dans sa branche running, avant ou après reprise."""
    repo.git(repo.peer, "checkout", "-q", "develop")
    chemin = repo.peer / ".agents/state/board/tasks" / f"{TID}.json"
    valeur = json.loads(chemin.read_text(encoding="utf-8"))
    valeur["record"]["stage"] = "cadrage"
    chemin.write_text(json.dumps(valeur), encoding="utf-8")
    repo.commit(repo.peer, "stage edit on develop")
    repo.publish("develop")
    repo.git(repo.peer, "checkout", "-q", "alice")
    repo.git(repo.peer, "merge", "--no-commit", "--no-ff", "develop", check=False)
    repo.record(repo.peer, "running", ALICE)
    valeur = json.loads(chemin.read_text(encoding="utf-8"))
    valeur["record"]["stage"] = "cadrage"
    chemin.write_text(json.dumps(valeur), encoding="utf-8")
    repo.git(repo.peer, "add", ".agents/state/board")
    repo.git(repo.peer, "commit", "-qm", "merge develop into alice")
    repo.publish("alice")


def _reprise_tty(repo: Repo) -> None:
    rc, sortie = repo.cli_tty(TID + "\n", "start", TID, "--reprise", "passation")
    assert rc == 0, sortie
    row = tasks.find(tasks.load(str(repo.root)), TID)
    assert row["start_actor"]["auteur"] == BOB["auteur"]
    assert row["reprise_levee"] and row["reprise_levee"][0]["auteur"] == ALICE["auteur"], row
    if "pointe" in row["reprise_levee"][0]:
        assert row["reprise_levee"][0]["pointe"] == repo.git(
            repo.root, "rev-parse", "refs/remotes/origin/alice").stdout.strip(), row


@pytest.mark.skipif(os.name == "nt", reason="pty POSIX seulement")
@pytest.mark.parametrize("cas", ["fusionnee-non-commitee", "distante-non-commitee", "distante-commitee",
                                 "merge-mixte-avant", "merge-mixte-apres"])
def test_reprise_levee_gardee_au_board_avertit_seulement(tmp_path: Path, cas: str) -> None:
    """S-01M5HH8QMC (sondes exec-critic P2c, P2e, P2f) : après une reprise LÉGITIME, la prise levée
    d'Alice, encore poussée, n'est qu'un avis pour Bob — reprise non commitée, prise publiée non
    fusionnée, ou reprise commitée et poussée. La preuve est `reprise_levee` au board, pas HEAD.
    MUTANT : `deja_levee` ignorée dans `conclure` ⇒ rc 2."""
    repo = Repo(tmp_path)
    repo.claim(branch="alice")
    if cas == "merge-mixte-avant":
        _merge_mixte_chez_alice(repo)
    if cas == "fusionnee-non-commitee":
        repo.git(repo.root, "fetch", "-q", "origin")
        repo.git(repo.root, "merge", "-q", "--no-ff", "-m", "merge alice", "origin/alice")
    _reprise_tty(repo)
    if cas == "merge-mixte-apres":
        _merge_mixte_chez_alice(repo)
    if cas == "distante-commitee":
        repo.commit(repo.root, "Bob takes over")
        repo.git(repo.root, "push", "-q", "origin", "develop")
    if cas not in ("merge-mixte-avant", "merge-mixte-apres"):
        _alice_pousse_encore(repo)
    again = repo.cli("start", TID)
    assert again.returncode == 0, again.stderr
    message = ("prise levée par reprise encore publiée" if cas == "merge-mixte-avant"
               else "ancien pilote a poussé après reprise")
    assert f"REVENDICATION: {message} ({TID}, refs/remotes/origin/alice)" in again.stderr


@pytest.mark.skipif(os.name == "nt", reason="pty POSIX seulement")
@pytest.mark.parametrize("miroir", ["alice-old", "aaa-old", "fork"])
def test_miroir_perime_de_la_meme_prise_ne_dit_pas_poussee(tmp_path: Path, miroir: str) -> None:
    """Une seconde ref plus ancienne porte la même prise (miroir périmé, triée APRÈS `origin/alice`,
    AVANT elle, ou sur un second remote) ; aucune poussée après la reprise : jamais « a poussé », et la
    pointe gardée est la plus avancée par filiation (`_reprise_tty`). MUTANTS : comparer les pointes par
    égalité seule, ou garder la première pointe dans l'ordre des refnames ⇒ rouge (aaa-old, fork)."""
    repo = Repo(tmp_path)
    repo.claim(branch="alice")
    if miroir == "fork":
        repo.git(tmp_path, "clone", "-q", "--bare", str(repo.remote), str(tmp_path / "fork.git"))
        repo.git(repo.root, "remote", "add", "fork", str(tmp_path / "fork.git"))
        nom = "refs/remotes/fork/alice"
    else:
        repo.git(repo.peer, "push", "-q", "origin", f"alice:{miroir}")
        nom = f"refs/remotes/origin/{miroir}"
    _alice_pousse_encore(repo)
    _reprise_tty(repo)
    assert "pointe" in tasks.find(tasks.load(str(repo.root)), TID)["reprise_levee"][0]
    again = repo.cli("start", TID)
    assert again.returncode == 0, again.stderr
    assert "ancien pilote a poussé après reprise" not in again.stderr, again.stderr
    assert f"REVENDICATION: prise levée par reprise encore publiée ({TID}, {nom})" in again.stderr


@pytest.mark.skipif(os.name == "nt", reason="pty POSIX seulement")
def test_second_clone_compare_a_la_pointe_gardee_par_le_transfert(tmp_path: Path) -> None:
    """Un second clone de Bob, au board périmé (Alice), voit le transfert T publié : la référence est
    la pointe gardée dans le `reprise_levee` de T, pas T lui-même — Alice n'a rien poussé depuis la
    reprise, jamais « a poussé ». MUTANT : comparer au commit T ⇒ rouge."""
    repo = Repo(tmp_path)
    repo.claim(branch="alice")
    repo.git(repo.peer, "checkout", "-q", "develop")
    repo.git(repo.peer, "merge", "-q", "--no-ff", "-m", "merge alice", "alice")
    repo.publish("develop")
    _alice_pousse_encore(repo)
    repo.git(repo.root, "pull", "-q", "origin", "develop")
    bob2 = tmp_path / "bob2"
    repo.git(tmp_path, "clone", "-q", str(repo.remote), str(bob2))
    repo.git(bob2, "config", "user.name", "Bob")
    repo.git(bob2, "config", "user.email", "bob@example.test")
    _reprise_tty(repo)
    repo.commit(repo.root, "Bob takes over")
    repo.git(repo.root, "push", "-q", "origin", "develop")
    resultat = subprocess.run([sys.executable, "-B", str(TASKS), "--root", str(bob2), "start", TID],
                              env=repo.env, text=True, capture_output=True, timeout=45)
    assert "ancien pilote a poussé après reprise" not in resultat.stderr, resultat.stderr
    assert "REVENDICATION: prise levée par reprise encore publiée" in resultat.stderr, resultat.stderr


@pytest.mark.skipif(os.name == "nt", reason="pty POSIX seulement")
@pytest.mark.parametrize("nom", ["fork", "zfork"])
def test_C_pointes_divergentes(tmp_path: Path, nom: str) -> None:
    """À la reprise, deux refs portent la même prise à des pointes DIVERGENTES (origin/alice = A2,
    <nom>/alice = A2') ; personne ne pousse ensuite : jamais « a poussé », dans les deux ordres de tri.
    Puis Alice pousse A3 sur origin : « a poussé ». MUTANT : ne garder qu'une pointe ⇒ rouge."""
    repo = Repo(tmp_path)
    repo.claim(branch="alice")
    repo.git(tmp_path, "clone", "-q", "--bare", str(repo.remote), str(tmp_path / f"{nom}.git"))
    repo.git(repo.root, "remote", "add", nom, str(tmp_path / f"{nom}.git"))
    repo.git(repo.peer, "remote", "add", nom, str(tmp_path / f"{nom}.git"))
    repo.git(repo.peer, "checkout", "-q", "alice")
    chemin = repo.peer / ".agents/state/board/tasks" / f"{TID}.json"
    valeur = json.loads(chemin.read_text(encoding="utf-8"))
    valeur["record"]["updated"] = "2026-10-24"
    chemin.write_text(json.dumps(valeur), encoding="utf-8")
    repo.commit(repo.peer, "A2' on second remote only")
    repo.git(repo.peer, "push", "-q", nom, "alice")
    repo.git(repo.peer, "reset", "-q", "--hard", "HEAD~1")
    _alice_pousse_encore(repo)
    rc, sortie = repo.cli_tty(TID + "\n", "start", TID, "--reprise", "passation")
    assert rc == 0, sortie
    levee = tasks.find(tasks.load(str(repo.root)), TID)["reprise_levee"][0]
    vues = {repo.git(repo.root, "rev-parse", f"refs/remotes/{r}/alice").stdout.strip() for r in ("origin", nom)}
    assert set(levee["pointes"]) == vues and levee["pointe"] in vues, levee
    again = repo.cli("start", TID)
    assert again.returncode == 0, again.stderr
    assert "ancien pilote a poussé après reprise" not in again.stderr, again.stderr
    valeur = json.loads(chemin.read_text(encoding="utf-8"))
    valeur["record"]["updated"] = "2026-10-25"
    chemin.write_text(json.dumps(valeur), encoding="utf-8")
    repo.commit(repo.peer, "A3 after takeover")
    repo.publish("alice")
    apres = repo.cli("start", TID)
    assert f"REVENDICATION: ancien pilote a poussé après reprise ({TID}, refs/remotes/origin/alice)" in apres.stderr


@pytest.mark.skipif(os.name == "nt", reason="pty POSIX seulement")
def test_D_transfert_filiation_illisible(tmp_path: Path) -> None:
    """Alice force-pousse après la reprise : le clone de Bob qui porte la reprise dit « a poussé » ; un
    second clone, à qui la pointe gardée A2 manque, compare au commit de transfert T et dit de même.
    MUTANT : pointe gardée absente ⇒ « contenue » sans repli sur T ⇒ « encore publiée » ⇒ rouge."""
    repo = Repo(tmp_path)
    repo.claim(branch="alice")
    repo.git(repo.peer, "checkout", "-q", "develop")
    repo.git(repo.peer, "merge", "-q", "--no-ff", "-m", "merge alice", "alice")
    repo.publish("develop")
    bob2 = tmp_path / "bob2"
    repo.git(tmp_path, "clone", "-q", str(repo.remote), str(bob2))
    repo.git(bob2, "config", "user.name", "Bob")
    repo.git(bob2, "config", "user.email", "bob@example.test")
    _alice_pousse_encore(repo)
    repo.git(repo.root, "pull", "-q", "origin", "develop")
    _reprise_tty(repo)
    repo.commit(repo.root, "Bob takes over")
    repo.git(repo.root, "push", "-q", "origin", "develop")
    repo.git(repo.peer, "checkout", "-q", "alice")
    repo.git(repo.peer, "commit", "-q", "--amend", "-m", "A2 rewritten after takeover")
    repo.git(repo.peer, "push", "-q", "-f", "origin", "alice")
    pointe = tasks.find(tasks.load(str(repo.root)), TID)["reprise_levee"][0]["pointe"]
    assert repo.git(bob2, "cat-file", "-e", f"{pointe}^{{commit}}", check=False).returncode != 0
    message = f"REVENDICATION: ancien pilote a poussé après reprise ({TID}, refs/remotes/origin/alice)"
    assert message in repo.cli("start", TID).stderr
    resultat = subprocess.run([sys.executable, "-B", str(TASKS), "--root", str(bob2), "start", TID],
                              env=repo.env, text=True, capture_output=True, timeout=45)
    assert message in resultat.stderr, resultat.stderr


def test_merge_mixte_sans_reprise_conserve_la_prise(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    repo.claim(branch="alice")
    _merge_mixte_chez_alice(repo)
    resultat = repo.cli("start", TID)
    assert resultat.returncode == 2 and "prise conservée" in resultat.stderr, resultat.stderr
    assert "pris par {nom: Alice" in resultat.stderr


@pytest.mark.skipif(os.name == "nt", reason="pty POSIX seulement")
def test_reprise_sans_nouvelle_poussee_dit_encore_publiee(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    repo.claim(branch="alice")
    _reprise_tty(repo)
    row = tasks.find(tasks.load(str(repo.root)), TID)
    assert row["reprise_levee"][0]["pointe"] == repo.git(
        repo.root, "rev-parse", "refs/remotes/origin/alice").stdout.strip()
    resultat = repo.cli("start", TID)
    assert resultat.returncode == 0, resultat.stderr
    assert "REVENDICATION: prise levée par reprise encore publiée" in resultat.stderr
    assert "ancien pilote a poussé après reprise" not in resultat.stderr


@pytest.mark.skipif(os.name == "nt", reason="pty POSIX seulement")
def test_pointe_gardee_non_sha_jamais_passee_a_git(tmp_path: Path) -> None:
    """Une pointe gardée au board est une donnée : `HEAD` n'est pas un SHA, elle compte comme absente.
    MUTANT : passer la valeur brute à git ⇒ « a poussé » (origin/alice hors de HEAD) ⇒ rouge."""
    repo = Repo(tmp_path)
    repo.claim(branch="alice")
    _reprise_tty(repo)
    chemin = repo.root / ".agents/state/board/tasks" / f"{TID}.json"
    valeur = json.loads(chemin.read_text(encoding="utf-8"))
    valeur["record"]["reprise_levee"][0]["pointe"] = "HEAD"
    valeur["record"]["reprise_levee"][0]["pointes"] = ["HEAD"]
    chemin.write_text(json.dumps(valeur), encoding="utf-8")
    resultat = repo.cli("start", TID)
    assert resultat.returncode == 0, resultat.stderr
    assert "REVENDICATION: prise levée par reprise encore publiée" in resultat.stderr, resultat.stderr


def _levee_editee(repo: Repo, edition) -> dict:
    """Réécrit la première entrée `reprise_levee` du board de Bob ; rend l'entrée écrite."""
    chemin = repo.root / ".agents/state/board/tasks" / f"{TID}.json"
    valeur = json.loads(chemin.read_text(encoding="utf-8"))
    edition(valeur["record"]["reprise_levee"][0])
    chemin.write_text(json.dumps(valeur), encoding="utf-8")
    return valeur["record"]["reprise_levee"][0]


@pytest.mark.skipif(os.name == "nt", reason="pty POSIX seulement")
@pytest.mark.parametrize("pousse", [False, True])
def test_record_d_avant_ne_porte_que_pointe(tmp_path: Path, pousse: bool) -> None:
    """Un record d'avant n'a que `pointe` (pas `pointes`) : elle reste la référence.
    MUTANT : `pointes_de` ignore `pointe` ⇒ sans pointe gardée, la poussée d'Alice n'est pas vue ⇒ rouge."""
    repo = Repo(tmp_path)
    repo.claim(branch="alice")
    _reprise_tty(repo)
    entree = _levee_editee(repo, lambda e: e.pop("pointes", None))
    assert "pointes" not in entree and "pointe" in entree, entree
    if pousse:
        _alice_pousse_encore(repo)
    resultat = repo.cli("start", TID)
    attendu = "ancien pilote a poussé après reprise" if pousse else "prise levée par reprise encore publiée"
    assert f"REVENDICATION: {attendu} ({TID}, refs/remotes/origin/alice)" in resultat.stderr, resultat.stderr


@pytest.mark.skipif(os.name == "nt", reason="pty POSIX seulement")
def test_borne_de_lecture_des_pointes_gardees(tmp_path: Path) -> None:
    """Au-delà de REVENDICATION_POINTES_MAX, une pointe gardée n'est pas lue : la vraie pointe, 17e,
    ne contient rien ⇒ « a poussé ». MUTANT : lecture non bornée ⇒ « encore publiée » ⇒ rouge."""
    repo = Repo(tmp_path)
    repo.claim(branch="alice")
    _reprise_tty(repo)
    racine = repo.git(repo.root, "rev-list", "--max-parents=0", "HEAD").stdout.split()[0]
    vraie = repo.git(repo.root, "rev-parse", "refs/remotes/origin/alice").stdout.strip()
    def edition(e: dict) -> None:
        e["pointes"] = [racine] * tasks.REVENDICATION_POINTES_MAX + [vraie]
        e["pointe"] = racine
    _levee_editee(repo, edition)
    resultat = repo.cli("start", TID)
    assert (f"REVENDICATION: ancien pilote a poussé après reprise ({TID}, refs/remotes/origin/alice)"
            in resultat.stderr), resultat.stderr


@pytest.mark.skipif(os.name == "nt", reason="pty POSIX seulement")
def test_borne_d_ecriture_des_pointes_gardees(tmp_path: Path) -> None:
    """Une entrée pleine (16 pointes) et une 17e pointe distincte : `levees` n'en garde que 16.
    MUTANT : écriture non bornée ⇒ 17 ⇒ rouge."""
    repo = Repo(tmp_path)
    repo.claim(branch="alice")
    _reprise_tty(repo)
    arbre = repo.git(repo.root, "rev-parse", "HEAD^{tree}").stdout.strip()
    borne = tasks.REVENDICATION_POINTES_MAX
    shas = [repo.git(repo.root, "commit-tree", arbre, "-m", f"c{i}").stdout.strip() for i in range(borne + 1)]
    def edition(e: dict) -> None:
        e["pointes"] = shas[:borne]
        e["pointe"] = shas[borne]
    _levee_editee(repo, edition)
    levees: dict = {}
    tasks.precontrole_revendication(str(repo.root), TID, BOB, levees=levees)
    assert len(levees[TID][0]["pointes"]) == borne, levees


@pytest.mark.skipif(os.name == "nt", reason="pty POSIX seulement")
@pytest.mark.parametrize("erreur", [OSError("EMFILE simulé"), subprocess.SubprocessError("git simulé")])
def test_record_du_transfert_illisible_rend_un_avis(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                    erreur: Exception) -> None:
    """Second clone au board périmé, transfert T publié ; lire le record de T lève : un avis, jamais une
    exception, et filiation illisible ⇒ « encore publiée » (Alice n'a rien poussé depuis la reprise).
    MUTANTS : OSError/SubprocessError hors de l'except ⇒ exception ; record illisible jugé contre T ⇒
    « a poussé » ⇒ rouge."""
    repo = Repo(tmp_path)
    repo.claim(branch="alice")
    repo.git(repo.peer, "checkout", "-q", "develop")
    repo.git(repo.peer, "merge", "-q", "--no-ff", "-m", "merge alice", "alice")
    repo.publish("develop")
    _alice_pousse_encore(repo)
    repo.git(repo.root, "pull", "-q", "origin", "develop")
    bob2 = tmp_path / "bob2"
    repo.git(tmp_path, "clone", "-q", str(repo.remote), str(bob2))
    repo.git(bob2, "config", "user.name", "Bob")
    repo.git(bob2, "config", "user.email", "bob@example.test")
    _reprise_tty(repo)
    repo.commit(repo.root, "Bob takes over")
    repo.git(repo.root, "push", "-q", "origin", "develop")
    portee = tasks.precontrole_revendication.__globals__
    vrai, vus = portee["_rev_record"], []
    def piege(git, ref, tid):
        if sys._getframe(1).f_code.co_name == "conclure":
            vus.append(ref)
            raise erreur
        return vrai(git, ref, tid)
    monkeypatch.setitem(portee, "_rev_record", piege)
    refus, avis = tasks.precontrole_revendication(str(bob2), TID, BOB)
    assert vus and not refus, (vus, refus, avis)
    assert f"REVENDICATION: prise levée par reprise encore publiée ({TID}, refs/remotes/origin/alice)" in avis, avis
    assert not any("a poussé" in a for a in avis), avis


def test_precontrole_borne_les_ids_avant_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ids = [f"T-{n:05d}" for n in range(tasks.REVENDICATION_IDS_MAX + 1)]
    monkeypatch.setattr(tasks, "load", lambda _root: {"tasks": [{"id": tid} for tid in ids]})
    def git_interdit(_root):
        raise AssertionError("Git ne doit pas être lu au-delà de la borne")
    monkeypatch.setattr(tasks, "_RevGit", git_interdit)
    refus, avis = tasks.precontrole_revendication(str(tmp_path), ids, BOB)
    assert refus == [f"REVENDICATION: {len(ids)} tâches dans le précontrôle ; maximum 32"]
    assert avis == []


def test_borne_rebase_documentee_sur_les_trois_surfaces() -> None:
    racine = Path(__file__).resolve().parents[2]
    phrase = "après un rebase de la branche de l'ancien pilote, la reprise se redemande une fois"
    for chemin in ("AGENTS.md", ".agents/skills/task-board/SKILL.md",
                   ".agents/ref/TASKS_CLI_CONTRACT.md"):
        assert phrase in (racine / chemin).read_text(encoding="utf-8"), chemin
    night = (racine / ".claude/commands/night.md").read_text(encoding="utf-8")
    assert "Kimi, Copilot) — Kimi : supposé, non mesuré —" in night


@pytest.mark.skipif(os.name == "nt", reason="pty POSIX seulement")
def test_reprise_levee_relance_par_fournee(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Sonde P2g : la relance `fournee` du nouveau propriétaire passe le précontrôle (rc 0, avis)."""
    import io
    repo = Repo(tmp_path)
    repo.claim(branch="alice")
    _reprise_tty(repo)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    for nom in MARQUEURS_AGENT:
        monkeypatch.delenv(nom, raising=False)
    for cle, valeur in repo.env.items():
        if cle.startswith("GIT_") or cle in ("CADRE_STATE_DIR", "AGENTS_EVENTS_DIR"):
            monkeypatch.setenv(cle, valeur)
    vu: dict = {}
    monkeypatch.setattr(tasks, "fournee", lambda *_a, **kw: vu.update(kw) or "FOURNEE: ok (banc)")
    stderr = io.StringIO()
    monkeypatch.setattr(tasks.sys, "stderr", stderr)
    monkeypatch.setattr(tasks.sys, "stdout", io.StringIO())
    assert tasks.main(["--root", str(repo.root), "fournee", TID]) == 0, stderr.getvalue()
    assert "REVENDICATION: prise levée par reprise encore publiée" in stderr.getvalue()
    assert vu["preuves_reprise"] == {}  # aucune nouvelle reprise : la propriété ne bouge pas


def _lot(repo: Repo, tid: str, etat: str, cle: str, acteur: dict | None = ALICE) -> None:
    row = {"id": tid, "task": f"lot {cle}", "owner": "dev-multi", "stage": "", "state": etat,
           "updated": "2026-10-22", "fournee": {"parent": TID, "lot": cle}}
    if acteur is not None:
        row["start_actor"] = acteur
    (repo.root / ".agents/state/board/tasks" / f"{tid}.json").write_text(
        json.dumps({"format": 1, "id": tid, "record": row, "sync_operations": []}), encoding="utf-8")


def _fournee_en_process(repo: Repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[int, str]:
    import io
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    for nom in MARQUEURS_AGENT:
        monkeypatch.delenv(nom, raising=False)
    for cle, valeur in repo.env.items():
        if cle.startswith("GIT_") or cle in ("CADRE_STATE_DIR", "AGENTS_EVENTS_DIR"):
            monkeypatch.setenv(cle, valeur)
    monkeypatch.setattr(tasks, "fournee", lambda *_a, **_kw: "FOURNEE: ok (banc)")
    stderr = io.StringIO()
    monkeypatch.setattr(tasks.sys, "stderr", stderr)
    monkeypatch.setattr(tasks.sys, "stdout", io.StringIO())
    return tasks.main(["--root", str(repo.root), "fournee", TID]), stderr.getvalue()


@pytest.mark.parametrize("etat, rc_attendu", [("done", 0), ("blocked", 0), ("running", 2)])
def test_relance_fournee_ignore_les_lots_clos_ou_bloques(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                         etat: str, rc_attendu: int) -> None:
    """Un lot `done` ou `blocked` d'un autre pilote n'est jamais relancé par `fournee` : il ne
    bloque pas la relance du propriétaire du parent ; un lot `running` d'autrui refuse toujours.
    MUTANT : précontrôler tous les lots (sans filtre d'état) ⇒ done/blocked rc 2."""
    repo = Repo(tmp_path)
    repo.record(repo.root, "running", BOB)
    _lot(repo, "T-013", etat, "A")
    rc, err = _fournee_en_process(repo, tmp_path, monkeypatch)
    assert rc == rc_attendu, err
    assert ("REVENDICATION" in err) is (rc_attendu == 2)


def test_borne_des_ids_de_fournee_sans_remede_reprise(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Au-delà de REVENDICATION_IDS_MAX ids, `fournee` refuse en disant de découper — jamais
    « --reprise » comme remède. MUTANT : retirer la borne de tasks.py ⇒ remède --reprise proposé."""
    repo = Repo(tmp_path)
    repo.record(repo.root, "running", BOB)
    for n in range(tasks.REVENDICATION_IDS_MAX):
        _lot(repo, f"T-{100 + n}", "pending", f"L{n:02d}", acteur=None)
    rc, err = _fournee_en_process(repo, tmp_path, monkeypatch)
    assert rc == 2, err
    assert f"REVENDICATION: {tasks.REVENDICATION_IDS_MAX + 1} tâches ; maximum 32" in err
    assert "--reprise ne lève pas cette borne" in err
    assert "reprise par le pilote avec --reprise" not in err


def test_reprise_ne_leve_pas_la_borne_des_ids(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Friction TTY neutralisée : même avec --reprise, la borne refuse AVANT la confirmation."""
    import io
    repo = Repo(tmp_path)
    repo.record(repo.root, "running", BOB)
    for n in range(tasks.REVENDICATION_IDS_MAX):
        _lot(repo, f"T-{100 + n}", "pending", f"L{n:02d}", acteur=None)
    confirme: list[str] = []
    monkeypatch.setattr(tasks, "_valider_reprise", lambda *_a: None)
    monkeypatch.setattr(tasks, "_confirmer_reprise", lambda tid, *_a: confirme.append(tid))
    monkeypatch.setattr(tasks, "acteur_de_la_commande", lambda _root: BOB)
    monkeypatch.setattr(tasks, "fournee", lambda *_a, **_kw: "FOURNEE: ok (banc)")
    stderr = io.StringIO()
    monkeypatch.setattr(tasks.sys, "stderr", stderr)
    monkeypatch.setattr(tasks.sys, "stdout", io.StringIO())
    rc = tasks.main(["--root", str(repo.root), "fournee", TID, "--reprise", "passation"])
    assert rc == 2, stderr.getvalue()
    assert "--reprise ne lève pas cette borne" in stderr.getvalue()
    assert confirme == []


@pytest.mark.parametrize("etat", ["blocked", "pending"])
def test_transfert_publie_depuis_une_tache_non_running(tmp_path: Path, etat: str) -> None:
    """La reprise publiée d'une tâche `blocked`/`pending` d'Alice est un transfert : le second clone de
    Bob, board encore à Alice, démarre sans --reprise. MUTANT : exiger un parent `running` ⇒ rc 2."""
    repo = Repo(tmp_path)
    repo.record(repo.peer, etat, ALICE)
    repo.commit(repo.peer, "alice")
    repo.publish()
    repo.git(repo.root, "pull", "-q", "origin", "develop")
    repo.git(repo.peer, "config", "user.name", "Bob")
    repo.git(repo.peer, "config", "user.email", "bob@example.test")
    repo.record(repo.peer, "running", BOB)
    repo.commit(repo.peer, "reprise par Bob")
    repo.publish()
    resultat = repo.cli("start", TID)
    assert resultat.returncode == 0, resultat.stderr


@pytest.mark.skipif(os.name == "nt", reason="pty POSIX seulement")
def test_nouveau_cycle_de_l_ancien_pilote_refuse_toujours(tmp_path: Path) -> None:
    """NÉGATIF : Alice clôt puis reprend SUR SA BRANCHE (autre transition d'entrée) : la levée ne la
    couvre pas, Bob est refusé rc 2 et rien n'est écrit."""
    repo = Repo(tmp_path)
    repo.claim(branch="alice")
    _reprise_tty(repo)
    repo.record(repo.peer, "done", ALICE)
    repo.commit(repo.peer, "alice done")
    repo.record(repo.peer, "running", ALICE)
    repo.commit(repo.peer, "alice new cycle")
    repo.publish("alice")
    chemin = repo.root / ".agents/state/board/tasks" / f"{TID}.json"
    avant = chemin.read_bytes()
    again = repo.cli("start", TID)
    assert again.returncode == 2 and "pris par {nom: Alice" in again.stderr, again.stderr
    assert chemin.read_bytes() == avant


@pytest.mark.skipif(os.name == "nt", reason="pty POSIX seulement")
def test_budget_head_separe_du_budget_distant(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Avis S-01M5HYRYRF : la lecture de HEAD a son budget propre. Reprise commitée, Alice pousse
    encore : 5 commits suffisent à chaque lecture (seuil mesuré) ; partagé, HEAD épuiserait la
    lecture distante. MUTANT : HEAD sur `restant` partagé ⇒ « budget historique » dit."""
    repo = Repo(tmp_path)
    repo.claim(branch="alice")
    repo.git(repo.root, "fetch", "-q", "origin")
    repo.git(repo.root, "merge", "-q", "--no-ff", "-m", "merge alice", "origin/alice")
    _reprise_tty(repo)
    repo.commit(repo.root, "Bob takes over")
    _alice_pousse_encore(repo)
    monkeypatch.setattr(tasks, "REVENDICATION_HISTOIRE_MAX", 5)
    refus, avis = repo.check()
    assert not refus, (refus, avis)
    assert not any("budget historique" in a for a in avis), avis


def test_dry_run_no_fetch(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    repo.claim()
    old = repo.git(repo.root, "rev-parse", "origin/develop").stdout.strip()
    repo.cli("fournee", TID, "--dry-run")
    assert repo.git(repo.root, "rev-parse", "origin/develop").stdout.strip() == old


if __name__ == "__main__":
    class DirectPytestSuite(unittest.TestCase):
        def test_pytest_suite(self) -> None:
            self.assertEqual(pytest.main(["-q", str(Path(__file__).resolve())]), 0)

    unittest.main()
