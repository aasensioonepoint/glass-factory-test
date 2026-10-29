"""Banc T-00000835 : la clause RESTORE n'efface plus le travail d'une autre session.

La phrase S835 (« Dirty at the snapshot (T-00000835): … ») est lue sur la ligne de route des trois hôtes et
INTERPRÉTÉE telle qu'écrite : sa place (avant la première tête de geste, elle gouverne toutes les familles ; dans
le corps d'une famille, cette seule famille), sa portée (membre de la ligne ERROR, exécutable OUT, suivi ou non),
la liste d'arguments de son gabarit, les caractères jamais passés, ses issues, puis sa commande — `shlex.split` du
texte, jeton 0 remplacé par l'interpréteur du banc, aucun shell — jouée dans la racine d'un dépôt jetable où le
script tourne en forme blob (`python3 -I -S -`), comme la route. Un ORACLE lit en direct les clés des tables
`dirty`, `ignored_exec` et `gitignores` du fichier d'état (S-00004498 : tout chemin présent au snapshot est protégé).
Le geste de repli est celui du modèle RESTORE du banc de contrat, importé et jamais recopié.

Témoins W1-W23, W6b et W7b, structure S1, mutants M1-M24 en mémoire (plan rév. 1 ; réserves C1-C8 de plan-critic
S-00004448 : W7b/M7a/M7b, W10/M12, W9/M13, W11/M14 ; revue de sécurité S-00004460, liste BLANCHE : W12-W14/M15 ;
passe decies, binôme S-00004495/S-00004497 et décision S-00004498 : W15/M16 et W17/M18 un chemin IGNORÉ présent au
snapshot, W16/M17 un membre `replace:` seul, passé au test au lieu d'un STOP à cause fausse ; passe de correction,
revue S-00004527 F1 : W18/M19 ce que le grep du geste `info: / excludes:` imprime, repassé au test AVANT tout retrait,
W19 et W20 un membre `info:` ou `alternates:` seul, passé sans STOP ; 2e passe de correction, revue de sécurité
S-00004533 (HIGH, classe 1) : W21/M20 un fichier d'une autre session DÉJÀ ignoré au snapshot, clé d'aucune table, que
grep imprime — listé au pilote et STOP, jamais retiré par la procédure ; W22/M21/M22/M24 le retrait sur ordre du
pilote, `rm --` un chemin à la fois, jamais un chemin en `/` ni hors de la règle de caractères ; W23/M23 les deux
captures relatives à la racine depuis un sous-dossier).
Portée hachée AVANT T-835 (@7dc8a906, C8) : `restore_clause` sha256[:12] e22300f67696, 3154 caractères, identique ×3.

Bornes du modèle : le shell est modélisé par `typed` — entre apostrophes un chemin sans apostrophe est littéral ; nu,
un opérateur (`; | & < > ( ) $` backtick) exécute autre chose et la commande n'est JAMAIS jouée, des accolades à
virgule donnent un mot par alternative, `#` en tête est un commentaire, `shlex.split` fait le reste (motifs, tilde
et `!` NON modélisés : la liste blanche les refuse) ; une commande sans chemin à passer est jouée quand même, comme
W9 la joue en direct (S-00004497) : sortie non nulle → STOP.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_docs_only_route_contract as RC  # noqa: E402 — modèle RESTORE et lignes de route : importés, jamais recopiés

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".agents" / "bin" / "docs_only_scope.py"
GITIGNORE = ".agents/state/local/\n.agents/state/events/\n__pycache__/\n.venv/\nnode_modules/\n.claude/worktrees/\n"
# Variables d'hôte qui changeraient la mesure : jamais héritées par un sous-processus du banc (gabarit T-816).
_HOST_VARS = ("CLAUDE_PROJECT_DIR", "PYTEST_ADDOPTS", "PYTHONDONTWRITEBYTECODE", "PYTHONPYCACHEPREFIX")


class Repo:
    """Dépôt jetable (gabarit du banc T-816) : config git vide, aucun `GIT_*` ni variable d'hôte hérités."""

    def __init__(self, tmp: Path) -> None:
        self.tmp, self.root, self.state = tmp, tmp / "repo", tmp / "state.json"
        self.root.mkdir()
        gcfg = tmp / "gitconfig-empty"
        gcfg.write_text("", encoding="utf-8")
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_") and k not in _HOST_VARS}
        self.env.update(GIT_CONFIG_GLOBAL=str(gcfg), GIT_CONFIG_NOSYSTEM="1", XDG_CONFIG_HOME=str(tmp / "xdg"))
        for name in ("AGENTS_EVENTS_DIR", "CADRE_STATE_DIR"):
            (tmp / name).mkdir()
            self.env[name] = str(tmp / name)
        for args in (("init", "-q", "."), ("config", "user.email", "b@x.invalid"), ("config", "user.name", "b"),
                     ("config", "commit.gpgsign", "false"), ("config", "core.excludesFile", os.devnull)):
            self.git(*args)
        self.write(".gitignore", GITIGNORE)
        for rel in ("docs/a.md", "README.md", "src/m.py", ".agents/bin/tool.py"):
            self.write(rel)
        self.commit("init")

    def git(self, *args: str) -> str:
        cp = subprocess.run(["git", *args], cwd=self.root, env=self.env, capture_output=True,
                            encoding="utf-8", timeout=120, check=False)
        assert cp.returncode == 0, f"git {args}: {cp.stderr}"
        return cp.stdout

    def write(self, rel: str, text: str = "x = 1\n") -> Path:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def commit(self, msg: str) -> None:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", msg)

    def run(self, *args: str) -> tuple[int, str]:
        cp = subprocess.run([sys.executable, "-I", "-S", "-", *args], input=SCRIPT.read_bytes(), cwd=self.root,
                            env=self.env, capture_output=True, timeout=300, check=False)
        return cp.returncode, cp.stdout.decode("utf-8")

    def snap(self) -> str:
        rc, out = self.run("snapshot", "--state", str(self.state))
        m = re.fullmatch(r"SNAPSHOT ([0-9a-f]{64})\n", out)
        assert rc == 0 and m, out
        # Contrôle : le digest gardé en contexte EST le sha256 des octets du fichier d'état (W6, W6b en dépendent).
        assert m.group(1) == hashlib.sha256(self.state.read_bytes()).hexdigest()
        return m.group(1)

    def check(self, digest: str) -> RC.Out:
        rc, out = self.run("check", "--state", str(self.state), "--digest", digest)
        return RC._parse(out, rc)

    def protected(self) -> frozenset[str]:
        """L'ORACLE : les clés des tables `dirty`, `ignored_exec` et `gitignores`, lues en direct dans le fichier d'état."""
        state = json.loads(self.state.read_bytes())
        return frozenset(state["dirty"]) | frozenset(state["ignored_exec"]) | frozenset(state["gitignores"])


# --- la phrase S835, lue sur la ligne et interprétée -------------------------------------------------------
S835_HEAD = "Dirty at the snapshot (T-00000835): "
S835_TAIL = "restoring it still erases that work."
_HEAD_RULE = "is never restored nor removed — STOP before any gesture of this clause"
_CONTROL = (".gitignore", ".gitattributes", ".gitmodules", ".mailmap")
_NAMED = {"'": "'", "$": "$", "backtick": "`", '"': '"', "backslash": "\\"}


def s835_of(line: str) -> str | None:
    """La phrase par ses deux ancres ; None si absente (la ligne d'avant T-835)."""
    i = line.find(S835_HEAD)
    j = line.find(S835_TAIL, i) if i >= 0 else -1
    return None if j < 0 else line[i : j + len(S835_TAIL)]


def governed(line: str, s835: str) -> set[str] | None:
    """None : S835 précède la première tête de geste et gouverne TOUTES les familles ; sinon les familles de la
    tête dont le corps la porte."""
    clause = RC.restore_clause(line)
    at = clause.find(s835)
    assert at >= 0, "S835 is outside the RESTORE clause"
    heads = list(RC._GESTURE_HEAD.finditer(clause))
    if not heads or at + len(s835) <= heads[0].start():
        return None
    head = [m for m in heads if m.end() <= at][-1].group(1)
    return {"executable"} if head.startswith("An executable") else set(re.findall(r"(?:^|/ )([a-z]+):", head))


@dataclass(frozen=True)
class Scope:
    error: bool
    executable: bool
    control: frozenset[str]
    tracking: frozenset[str]


def scope_of(s835: str) -> Scope:
    subject = s835[len(S835_HEAD) : s835.index(' whose path is a key of the "dirty"')]
    words = frozenset(re.findall(r"\b(?:un)?tracked\b", subject)) or frozenset({"tracked", "untracked"})
    return Scope("a member of the ERROR line" in subject, "an executable OUT or DECLARED-OUT path" in subject,
                 frozenset(c for c in _CONTROL if c in subject), words)


@dataclass(frozen=True)
class Spec:
    out_paths: bool
    via: bool
    after: frozenset[str]
    config_file: bool


def spec_of(s835: str) -> Spec:
    """Ce que le gabarit `<state file> <digest> <…>` dit de passer."""
    m = re.search(r"<state file> <digest> <([^>]*)>", s835)
    assert m, "S835: argument template not found"
    tpl = m.group(1)
    after = re.search(r"the path after ((?:[a-z]+: or )*[a-z]+:)", tpl)
    return Spec("every OUT or DECLARED-OUT path" in tpl, "its via= value" in tpl,
                frozenset(re.findall(r"([a-z]+):", after.group(1))) if after else frozenset(),
                "the file after config: (before its [)" in tpl)


def _class_chars(spec: str) -> frozenset[str]:
    """Les caractères d'une classe écrite `A-Za-z0-9._/-` : plages entre alphanumériques, le reste littéral."""
    out: set[str] = set()
    i = 0
    while i < len(spec):
        if i + 2 < len(spec) and spec[i + 1] == "-" and spec[i].isalnum() and spec[i + 2].isalnum():
            out |= {chr(c) for c in range(ord(spec[i]), ord(spec[i + 2]) + 1)}
            i += 3
        else:
            out.add(spec[i])
            i += 1
    return frozenset(out)


def passable_of(s835: str) -> Callable[[str], bool] | None:
    """« Ce chemin peut être passé » : la liste BLANCHE `outside […]` (S-00004460), ou l'ancienne liste noire (M15) ;
    None si aucune règle « never passed » n'est écrite."""
    m = re.search(r"a path carrying any character outside \[([^\]]+)\] is never passed: STOP", s835)
    if m is not None:
        allowed = _class_chars(m.group(1))
        return lambda p: all(c in allowed for c in p)
    m = re.search(r"a path carrying (.+?) is never passed: STOP", s835)
    if m is None:
        return None
    toks = m.group(1).split()
    banned, ws = frozenset(_NAMED[t] for t in toks if t in _NAMED), "whitespace" in toks
    return lambda p: not any(c in banned for c in p) and not (ws and any(c.isspace() for c in p))


def command_of(s835: str) -> list[str]:
    """La commande telle qu'écrite : jeton 0 → l'interpréteur du banc, tout autre jeton VERBATIM."""
    i = s835.index("python3 ")
    toks = shlex.split(s835[i : s835.index("' <state file>", i) + 1])
    assert toks[0] == "python3", toks
    return [sys.executable, *toks[1:]]


_OPERATORS = frozenset(";|&<>()$`")  # nu, ouvre une AUTRE commande (séparateur, tube, redirection, substitution)
_BRACES = re.compile(r"\{([^{}]*,[^{}]*)\}")


def typed(p: str, quoted: bool) -> list[str] | str:
    """Ce que le shell fait d'un chemin tapé : les mots reçus par la commande, ou « injected » / « refused ».
    Entre apostrophes, un chemin qui n'en porte pas est littéral ; nu, un opérateur exécute autre chose
    (S-00004460), des accolades donnent un mot par alternative (jamais la clé), `#` en tête est un commentaire,
    `shlex.split` fait le reste."""
    if quoted and "'" not in p:
        return [p]
    if any(c in _OPERATORS for c in p):
        return "injected"
    m = _BRACES.search(p)
    if m is not None:
        return [p[: m.start()] + alt + p[m.end() :] for alt in m.group(1).split(",")]
    if p.startswith("#"):
        return []
    try:
        return shlex.split(p)
    except ValueError:
        return "refused"  # guillemet non fermé : le shell refuse la ligne


def run_test(s835: str, repo: Repo, digest: str, paths: list[str]) -> tuple[list[str], int | None]:
    """La commande jouée dans la racine du dépôt, chaque chemin tapé comme S835 le dit ; rc None : la ligne aurait
    exécuté une autre commande, que le banc ne joue jamais."""
    argv = [*command_of(s835), str(repo.state), digest]
    quoted = "each path passed is single-quoted" in s835
    for p in paths:
        words = typed(p, quoted)
        if words == "injected":
            return [], None
        if words == "refused":
            return [], 2
        argv += words
    cp = subprocess.run(argv, cwd=repo.root, env=repo.env, capture_output=True, timeout=60, check=False)
    return [ln for ln in cp.stdout.decode("utf-8", "replace").splitlines() if ln], cp.returncode


def outcome(s835: str, printed: list[str], rc: int | None) -> str:
    if rc is None:
        return ""
    if printed and "a path printed → STOP" in s835:
        return "printed"
    if rc != 0 and "a non-zero exit → STOP as rc 2" in s835:
        return "nonzero"
    return ""


@dataclass
class Verdict:
    stop: bool
    reason: str = ""
    passed: list[str] = field(default_factory=list)
    printed: list[str] = field(default_factory=list)
    rc: int | None = None
    gestures: list[tuple[str, str | None]] = field(default_factory=list)


def _via_map(out: RC.Out) -> dict[str, str]:
    via: dict[str, str] = {}
    for ln in out.lines:
        parts = ln.split("\t")
        for p in parts[2:]:
            if p.startswith("via="):
                via[parts[1]] = p[len("via="):]
    return via


def _member_path(fam: str, member: str, via: str | None) -> str | None:
    if fam == "executable":
        return via or member
    rest = member.split(":", 1)[1]
    return rest.split("[", 1)[0] if fam == "config" else (rest if fam in ("hooks", "excludes") else None)


def _args_of(spec: Spec, fam: str, member: str, via: str | None) -> list[str]:
    if fam == "executable":
        return ([member] if spec.out_paths else []) + ([via] if spec.via and via else [])
    rest = member.split(":", 1)[1]
    if fam in spec.after:
        return [rest]
    return [rest.split("[", 1)[0]] if fam == "config" and spec.config_file else []


def verdict(line: str, out: RC.Out, repo: Repo, digest: str) -> Verdict:
    """S835 appliquée à la sortie RÉELLE d'un check, puis le geste de repli du modèle RESTORE."""
    s835 = s835_of(line)
    assert s835 is not None, "S835 is absent from the route line"
    pairs = RC.apply_restore(line, out, repo)
    assert pairs, f"the RESTORE clause did not trigger on {out.lines}"
    gov, sc, spec, via_of = governed(line, s835), scope_of(s835), spec_of(s835), _via_map(out)
    paths: list[str] = []
    for member, _g in pairs:
        fam = "executable" if out.rc == 1 else member.split(":", 1)[0]
        if gov is not None and fam not in gov:
            continue
        kind = (sc.executable or member.rsplit("/", 1)[-1] in sc.control) if fam == "executable" else sc.error
        path = _member_path(fam, member, via_of.get(member))
        tracked = path is not None and RC._is_tracked(repo, path)
        if kind and ("tracked" if tracked else "untracked") in sc.tracking:
            paths += _args_of(spec, fam, member, via_of.get(member))
    if _HEAD_RULE not in s835:  # sans chemin, la commande est jouée quand même (S-00004497) : rc 3 → STOP, comme W9
        return Verdict(False, gestures=pairs)
    passable = passable_of(s835)
    if passable is not None and not all(passable(p) for p in paths):
        return Verdict(True, "never-passed", paths, gestures=pairs)
    printed, rc = run_test(s835, repo, digest, paths)
    if rc is None:
        return Verdict(False, "injected", paths, gestures=pairs)
    why = outcome(s835, printed, rc)
    return Verdict(bool(why), why, paths, printed, rc, pairs)


# --- scénarios : un dépôt jetable, un snapshot, une fenêtre, un check -------------------------------------
@dataclass
class Ctx:
    out: RC.Out
    digest: str
    protected: frozenset[str]
    hid: list[str] = field(default_factory=list)  # W18 : ce que le grep de P3 a imprimé
    p3: tuple[str, ...] = ()  # W18 : les trois commandes P3 jouées
    replay: Callable[..., list[str]] | None = None  # W21-W23 : P3 lue sur une ligne, rejouée depuis un sous-dossier


_KIT, _OTHER, _PLANTED = "print('kit')\n", "print('another session')\n", "import os\nos.system('planted')\n"


def _rewritten(rel: str, *, commit: bool = True, dirty: str | None = _OTHER, window: str = _PLANTED):
    """`rel` (commité ou non), sale au snapshot si `dirty`, réécrit pendant la fenêtre."""
    def go(r: Repo) -> Ctx:
        if commit:
            r.write(rel, _KIT)
            r.commit(f"kit {rel}")
        if dirty is not None:
            r.write(rel, dirty)
        d = r.snap()
        oracle = r.protected()
        r.write(rel, window)
        return Ctx(r.check(d), d, oracle)
    return go


def _hook_dirty(r: Repo) -> Ctx:
    r.write(".githooks/commit-msg", "#!/bin/sh\nexit 0\n").chmod(0o755)
    r.commit("hooks")
    r.git("config", "core.hooksPath", ".githooks")
    r.write(".githooks/commit-msg", "#!/bin/sh\n# another session\nexit 0\n")
    d = r.snap()
    oracle = r.protected()
    r.write(".githooks/commit-msg", "#!/bin/sh\ntouch planted\nexit 0\n")
    return Ctx(r.check(d), d, oracle)


def _link_dirty(r: Repo) -> Ctx:
    link = r.root / ".agents" / "bin" / "l.py"
    try:
        os.symlink("tool.py", link)
    except OSError as exc:
        pytest.skip(f"no symbolic link on this host: {exc}")
    r.commit("link")
    link.unlink()
    os.symlink("other.py", link)
    d = r.snap()
    oracle = r.protected()
    link.unlink()
    os.symlink("../../evil.py", link)
    return Ctx(r.check(d), d, oracle)


def _config_include_dirty(r: Repo) -> Ctx:
    """C7 : une origine `config:` DANS le dépôt (cible d'`include.path`) peut être une clé de `dirty`."""
    r.write("cfg/extra.gitconfig", "[user]\n\tname = b\n")
    r.commit("cfg")
    r.git("config", "include.path", "../cfg/extra.gitconfig")
    r.write("cfg/extra.gitconfig", "[user]\n\tname = b\n[alias]\n\tst = status\n")
    d = r.snap()
    oracle = r.protected()
    r.write("cfg/extra.gitconfig", "[user]\n\tname = b\n[alias]\n\tst = status\n[core]\n\tfsmonitor = false\n")
    return Ctx(r.check(d), d, oracle)


_TASKS = ".agents/bin/tasks.py"
_W1 = _rewritten(_TASKS)


def _state_one_byte(r: Repo) -> Ctx:
    """W6 : un processus resté vivant réécrit l'état APRÈS le check (un octet de la clé)."""
    ctx = _W1(r)
    data = r.state.read_bytes()
    old = json.dumps(_TASKS).encode() + b":"
    assert data.count(old) == 1, data
    r.state.write_bytes(data.replace(old, old[:-3] + b'z":'))
    return ctx


def _state_no_dirty(r: Repo) -> Ctx:
    """W6b : la clé `dirty` retirée, le digest RECALCULÉ — seule la lecture stricte refuse."""
    ctx = _W1(r)
    state = json.loads(r.state.read_bytes())
    del state["dirty"]
    r.state.write_bytes(json.dumps(state).encode())
    return Ctx(ctx.out, hashlib.sha256(r.state.read_bytes()).hexdigest(), ctx.protected)


_MARKER = "planted-ran"


def _planted_modules(r: Repo) -> Ctx:
    """W10 (C2) : `json.py` et `hashlib.py` plantés à la racine, où la commande est jouée."""
    ctx = _W1(r)
    stub = f"import pathlib\npathlib.Path({_MARKER!r}).touch()\nprint('PAYLOAD')\n"
    r.write("json.py", stub + "def loads(b):\n    return {'dirty': {}}\n")
    r.write("hashlib.py", stub + "import sys\nclass _H:\n    def hexdigest(self):\n        return sys.argv[2]\n"
            "def sha256(b):\n    return _H()\n")
    return ctx


# Passe decies (S-00004498) : deux chemins IGNORÉS, invisibles à `git status`, présents au snapshot.
_WIP = ".claude/worktrees/w/wip.py"  # sous `.claude/worktrees/` (GITIGNORE) : une clé d'`ignored_exec`
_SELF_IGNORED = ".claude/commands/.gitignore"  # `*` : il s'ignore lui-même, une clé de `gitignores`


def _replace_only(r: Repo) -> Ctx:
    """W16 (S-00004497) : une ref de remplacement posée dans la fenêtre — une ligne ERROR à membre `replace:` seul."""
    d = r.snap()
    oracle = r.protected()
    r.git("update-ref", "refs/replace/x", r.git("rev-parse", "HEAD").strip())
    return Ctx(r.check(d), d, oracle)


# Passe de correction (revue S-00004527 F1) : un chemin `.git/…` n'est jamais une clé, le test S835 le passe (rc 0) ;
# ce que le geste `info: / excludes:` retire ensuite, c'est ce que `grep -Fxf` imprime.
_DRAFT, _EXCLUDE, _ALTERNATES = "notes/draft.md", ".git/info/exclude", ".git/objects/info/alternates"


def _info_hides_dirty(r: Repo) -> Ctx:
    """W18 : un brouillon non suivi d'une autre session, sale au snapshot, caché par `notes/` écrit dans
    `.git/info/exclude` pendant la fenêtre. Le check, puis P3 jouée UNE fois (le contrôle et la ligne mutée relisent le
    même résultat) : capture `before`, geste du pilote (la règle non reconnue retirée), capture `after`, grep."""
    r.write(_DRAFT, "another session's draft\n")
    d = r.snap()
    oracle = r.protected()
    exclude = r.root / _EXCLUDE
    kept = exclude.read_text(encoding="utf-8")
    exclude.write_text(kept + "notes/\n", encoding="utf-8")
    out = r.check(d)
    # P3 lue sur la ligne .claude, égale sur les trois hôtes (test_restore_procedure_equal_on_route_hosts_811) ; chaque
    # contrôle vérifie que celle de SA ligne est celle jouée ici. `T` passe par l'environnement, jamais interpolé.
    p3 = RC.restore_procedure_811(RC._route_line(RC.ROUTE_HOSTS[0]))
    t = r.tmp / "p3"
    t.mkdir()
    env = dict(r.env, T=str(t))

    def sh(cmd: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["bash", "-c", cmd], cwd=r.root, env=env, capture_output=True, text=True, timeout=120,
                              check=False)

    before, after, grep = p3
    assert sh(before).returncode == 0, "P3 before capture failed"
    exclude.write_text(kept, encoding="utf-8")  # « remove what the pilot does not recognise »
    assert sh(after).returncode == 0, "P3 after capture failed"
    cp = sh(grep)
    assert cp.returncode in (0, 1), f"grep: rc={cp.returncode} {cp.stderr}"  # 1 : rien d'imprimé
    return Ctx(out, d, oracle, [ln for ln in cp.stdout.splitlines() if ln], p3)


def _control_written(rel: str) -> Callable[[Repo], Ctx]:
    """W19, W20 : un fichier de contrôle sous `.git/` écrit seul dans la fenêtre — une ligne ERROR à un membre."""
    def go(r: Repo) -> Ctx:
        d = r.snap()
        oracle = r.protected()
        p = r.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text((p.read_text(encoding="utf-8") if p.exists() else "") + "# window\n", encoding="utf-8")
        return Ctx(r.check(d), d, oracle)
    return go


# 2e passe de correction (revue de sécurité S-00004533, HIGH classe 1) : un fichier non suivi d'une autre session, DÉJÀ
# ignoré au snapshot par une règle existante, n'est clé d'aucune table de l'état — le test S835 le passe (rc 0, rien).
_NOTES, _DASH, _NESTED = "notes.md", "-n.md", "nested/"
_QUOTED = "x';touch planted-rm;'.md"  # hors de la règle de caractères : tapé entre apostrophes, il ouvrirait `touch`


def _p3_play(r: Repo, line: str, cwd: Path, window: str, blind: str) -> list[str]:
    """P3 lue sur `line`, rejouable depuis `cwd` : la fenêtre remise dans `.git/info/exclude`, capture `before`, geste
    du pilote AVEUGLE (l'état ne garde du fichier que son sha256 : il le remet à `blind`, l'ancienne règle part avec),
    capture `after`, grep. Un `T` neuf à chaque partie, passé par l'environnement, jamais interpolé."""
    before, after, grep = RC.restore_procedure_811(line)
    exclude = r.root / _EXCLUDE
    env = dict(r.env, T=tempfile.mkdtemp(dir=r.tmp))

    def sh(cmd: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["bash", "-c", cmd], cwd=cwd, env=env, capture_output=True, text=True, timeout=120,
                              check=False)

    exclude.write_text(window, encoding="utf-8")
    assert sh(before).returncode == 0, "P3 before capture failed"
    exclude.write_text(blind, encoding="utf-8")
    assert sh(after).returncode == 0, "P3 after capture failed"
    cp = sh(grep)
    assert cp.returncode in (0, 1), f"grep: rc={cp.returncode} {cp.stderr}"  # 1 : rien d'imprimé
    return [ln for ln in cp.stdout.splitlines() if ln]


def _old_rule_hides(*files: str, nested: bool = False) -> Callable[[Repo], Ctx]:
    """W21-W23 : `*.md` (et `nested/`) déjà dans `.git/info/exclude` AU SNAPSHOT cachent des fichiers non suivis d'une
    autre session ; une règle ajoutée dans la fenêtre fait le membre `info:` ; le contrôle rejoue P3 (`replay`)."""
    rules = "*.md\n" + ("nested/\n" if nested else "")

    def go(r: Repo) -> Ctx:
        exclude = r.root / _EXCLUDE
        kept = exclude.read_text(encoding="utf-8")
        exclude.write_text(kept + rules, encoding="utf-8")
        try:
            for rel in files:
                r.write(rel, "another session's work\n")
        except OSError as exc:
            pytest.skip(f"no such file name on this host: {exc}")
        if nested:
            r.git("init", "-q", _NESTED)
            r.write(_NESTED + "work.txt", "another session's nested work\n")
        d = r.snap()
        oracle = r.protected()
        window = kept + rules + "x/\n"
        exclude.write_text(window, encoding="utf-8")
        return Ctx(r.check(d), d, oracle, replay=lambda line, sub="": _p3_play(r, line, r.root / sub, window, kept))
    return go


# --- témoins : (scénario, contrôle sur une ligne) ----------------------------------------------------------
def _stops_printing(*keys: str):
    def ok(line: str, ctx: Ctx, repo: Repo) -> None:
        v = verdict(line, ctx.out, repo, ctx.digest)
        assert v.stop and v.reason == "printed", f"no STOP: {v}"
        assert v.printed == list(keys) and set(keys) <= ctx.protected, f"printed {v.printed}, oracle {sorted(ctx.protected)}"
    return ok


def _w4(line: str, ctx: Ctx, repo: Repo) -> None:
    v = verdict(line, ctx.out, repo, ctx.digest)
    assert _TASKS not in ctx.protected and not v.stop and v.printed == [] and v.rc == 0, v
    assert [m for m, _g in v.gestures] == [_TASKS] and "git restore" in (v.gestures[0][1] or ""), v.gestures


def _stops_nonzero(rc: int | None):
    def ok(line: str, ctx: Ctx, repo: Repo) -> None:
        v = verdict(line, ctx.out, repo, ctx.digest)
        assert v.stop and v.reason == "nonzero" and v.printed == [] and (rc is None or v.rc == rc), v
    return ok


def _never_passed(key: str, shown: str):
    def ok(line: str, ctx: Ctx, repo: Repo) -> None:
        assert key in ctx.protected and f"OUT\t{shown}" in ctx.out.lines, (sorted(ctx.protected), ctx.out.lines)
        v = verdict(line, ctx.out, repo, ctx.digest)
        assert v.stop and v.reason == "never-passed" and v.rc is None, v
    return ok


def _posix_name(rel: str) -> Callable[[Repo], Ctx]:
    """S-00004460 : un exécutable dont le NOM porte un opérateur du shell, sale au snapshot, réécrit."""
    go = _rewritten(rel)

    def wrapped(r: Repo) -> Ctx:
        try:
            return go(r)
        except OSError as exc:
            pytest.skip(f"no such file name on this host: {exc}")
    return wrapped


def _w9(line: str, ctx: Ctx, repo: Repo) -> None:
    """C3 : la commande tapée sans chemin sort non nulle — donc STOP, jamais « rien de sale »."""
    s835 = s835_of(line)
    assert s835 is not None, "S835 is absent from the route line"
    printed, rc = run_test(s835, repo, ctx.digest, [])
    assert printed == [] and rc != 0 and outcome(s835, printed, rc) == "nonzero", (printed, rc)


def _w10(line: str, ctx: Ctx, repo: Repo) -> None:
    v = verdict(line, ctx.out, repo, ctx.digest)
    assert v.printed == [_TASKS] and v.rc == 0, f"the payload ran or the key was not printed: {v}"
    assert not (repo.root / _MARKER).exists(), "a module planted in the repository root was imported"


def _stops_printing_from(table: str, key: str):
    """W15, W17 (S-00004495) : la clé n'est que dans `table`, jamais dans `dirty` ; sans STOP, le geste « remove it »
    effaçait le travail d'une autre session."""
    def ok(line: str, ctx: Ctx, repo: Repo) -> None:
        state = json.loads(repo.state.read_bytes())
        assert key in state[table] and key not in state["dirty"], f"{key} is not a key of {table!r} alone"
        v = verdict(line, ctx.out, repo, ctx.digest)
        assert [m for m, _g in v.gestures] == [key] and "remove it" in (v.gestures[0][1] or ""), v.gestures
        assert v.stop and v.reason == "printed" and v.printed == [key], f"no STOP: {v}"
    return ok


def _w16(line: str, ctx: Ctx, repo: Repo) -> None:
    """S-00004497 : le membre `replace:` est PASSÉ — rien d'imprimé, rc 0, aucun STOP à cause fausse, et le geste
    `update-ref -d` reste jouable."""
    v = verdict(line, ctx.out, repo, ctx.digest)
    assert ctx.out.rc == 2 and [m for m, _g in v.gestures] == ["replace:refs/replace/x"], (ctx.out.lines, v.gestures)
    assert "git update-ref -d" in (v.gestures[0][1] or ""), v.gestures
    assert not v.stop and v.passed == ["refs/replace/x"] and v.printed == [] and v.rc == 0, v


# --- le pas grep du geste `info: / excludes:`, lu sur la ligne et interprété (S-00004527 F1, S-00004533) -------
_HID = 'grep -Fxf "$T/before" "$T/after" — every path printed is what the file hid: '
_REPASS = re.compile(r"first pass every printed path to the Dirty-at-the-snapshot test above \(([^)]*)\) — (.+?) → STOP, "
                     r"ask the pilot; ")
_LISTED = "LIST every path grep printed to the pilot and STOP"  # S-00004533 : le pas s'arrête, quoi que le test imprime
_REMOVED = "remove it"  # la ligne d'avant S-00004533 : ce que le test passe en silence est retiré par la procédure
_ORDER = "on the pilot's order only, one path at a time, from the repository root: "
_NO_DIR = ", and a path ending in / (a directory, possibly a nested repository) is never removed by the procedure"
_CHAR_RULE = ", never a path the character rule refuses"


@dataclass(frozen=True)
class Gate:
    same: frozenset[str]  # « same state file, same digest, same character rule »
    stops: frozenset[str]  # « a path it prints, or a non-zero exit »


def grep_step_of(line: str) -> tuple[Gate | None, str]:
    """Le pas grep du geste `info:` : la repasse au test S835 qui doit l'ouvrir (None si absente — la ligne d'avant
    S-00004527) et le texte qui la suit."""
    body = RC.restore_gestures(RC.restore_clause(line)).get("info", "")
    assert body.count(_HID) == 1, "the grep step of the info: gesture is not present exactly once"
    step = body[body.index(_HID) + len(_HID) :]
    m = _REPASS.match(step)
    if m is None:
        return None, step
    return Gate(frozenset(s.strip().removeprefix("same ") for s in m.group(1).split(",")),
                frozenset(s.strip() for s in m.group(2).split(", or "))), step[m.end() :]


def grep_gate_of(line: str) -> Gate | None:
    return grep_step_of(line)[0]


def disposal_of(rest: str) -> str:
    """Ce que le pas fait d'un chemin imprimé par grep que la repasse n'a pas arrêté : la PREMIÈRE consigne lue
    l'emporte — « listed » (listé au pilote, STOP) ou « removed » (« remove it », retiré par la procédure)."""
    found = {k: rest.find(s) for k, s in (("listed", _LISTED), ("removed", _REMOVED)) if s in rest}
    assert found, f"the grep step says neither {_LISTED!r} nor {_REMOVED!r}"
    return min(found, key=found.__getitem__)


def removal_of(line: str) -> tuple[str, bool, bool]:
    """Le retrait sur ordre du pilote, lu sur la ligne : la commande telle qu'écrite (`<path>` en place du chemin),
    un chemin en `/` exclu, la règle de caractères appliquée."""
    rest = grep_step_of(line)[1]
    assert rest.count(_ORDER) == 1, "the grep step does not say how a removal the pilot orders is typed"
    m = re.match(r".*?<path>'?", rest[rest.index(_ORDER) + len(_ORDER) :])
    assert m is not None, "no <path> in the removal command"
    return m.group(0), _NO_DIR in rest, _CHAR_RULE in rest


def repass(line: str, ctx: Ctx, repo: Repo) -> Verdict:
    """Le pas grep appliqué aux chemins que P3 a imprimés : la repasse lue sur la ligne, puis la commande S835 telle
    qu'écrite, sur le même fichier d'état et le même digest ; la règle de caractères de S835 si la repasse la cite ;
    enfin ce que le pas fait des chemins que la repasse n'a pas arrêtés (`disposal_of`)."""
    s835, (gate, rest) = s835_of(line), grep_step_of(line)
    assert s835 is not None, "S835 is absent from the route line"
    disposal = disposal_of(rest)
    if gate is None:
        return Verdict(disposal == "listed", disposal, ctx.hid)
    passable = passable_of(s835) if "character rule" in gate.same else None
    if passable is not None and not all(passable(p) for p in ctx.hid):
        return Verdict(True, "never-passed", ctx.hid)
    printed, rc = run_test(s835, repo, ctx.digest, ctx.hid)
    if rc is None:
        return Verdict(False, "injected", ctx.hid)
    why = ("printed" if printed and "a path it prints" in gate.stops
           else "nonzero" if rc != 0 and "a non-zero exit" in gate.stops else "")
    if why:
        return Verdict(True, why, ctx.hid, printed, rc)
    return Verdict(disposal == "listed", disposal, ctx.hid, printed, rc)


def _w18(line: str, ctx: Ctx, repo: Repo) -> None:
    """S-00004527 F1 : S835 passe `.git/info/exclude` (jamais une clé : rc 0, pas de STOP) ; P3 imprime le brouillon
    caché, clé de `dirty` ; la repasse le NOMME (imprimé, protégé) et STOP — sans elle, rien ne le désigne au pilote
    comme le travail non commité d'une autre session (S-00004533 : le pas s'arrête de toute façon, W21)."""
    assert RC.restore_procedure_811(line) == ctx.p3, "the P3 procedure of this host is not the one played"
    v = verdict(line, ctx.out, repo, ctx.digest)
    assert [m for m, _g in v.gestures] == ["info:" + _EXCLUDE], (ctx.out.lines, v.gestures)
    assert not v.stop and v.passed == [_EXCLUDE] and v.printed == [] and v.rc == 0, v
    assert ctx.hid == [_DRAFT] and _DRAFT in ctx.protected, (ctx.hid, sorted(ctx.protected))
    g = repass(line, ctx, repo)
    assert g.reason != "removed", "the paths grep printed are removed without the Dirty-at-the-snapshot test"
    assert grep_gate_of(line) == Gate(frozenset({"state file", "digest", "character rule"}),
                                      frozenset({"a path it prints", "a non-zero exit"})), grep_gate_of(line)
    assert g.stop and g.reason == "printed" and g.printed == [_DRAFT] and g.rc == 0, f"no STOP: {g}"


def _passed_alone(member: str, gesture: str) -> Check:
    """W19, W20 (S-00004527) : le membre est PASSÉ au test S835 — rien d'imprimé, rc 0, aucun STOP à cause fausse —
    et son geste reste jouable."""
    def ok(line: str, ctx: Ctx, repo: Repo) -> None:
        v = verdict(line, ctx.out, repo, ctx.digest)
        assert ctx.out.rc == 2 and [m for m, _g in v.gestures] == [member], (ctx.out.lines, v.gestures)
        assert gesture in (v.gestures[0][1] or ""), v.gestures
        assert not v.stop and v.passed == [member.split(":", 1)[1]] and v.printed == [] and v.rc == 0, v
    return ok


def _w21(line: str, ctx: Ctx, repo: Repo) -> None:
    """S-00004533 : `notes.md`, ignoré au snapshot par `*.md`, n'est clé d'aucune table ; le pilote aveugle retire
    l'ancienne règle avec celle de la fenêtre, grep l'imprime, le test S835 le passe en silence (rc 0) — la procédure
    doit le LISTER au pilote et STOP, jamais « remove it »."""
    assert ctx.replay is not None
    v = verdict(line, ctx.out, repo, ctx.digest)
    assert [m for m, _g in v.gestures] == ["info:" + _EXCLUDE] and not v.stop, (ctx.out.lines, v)
    hid = ctx.replay(line)
    assert hid == [_NOTES] and _NOTES not in ctx.protected, (hid, sorted(ctx.protected))
    s835 = s835_of(line)
    assert s835 is not None and run_test(s835, repo, ctx.digest, hid) == ([], 0), "S835 now protects it: re-measure"
    g = repass(line, replace(ctx, hid=hid), repo)
    assert g.reason != "removed", "a path grep printed is removed by the procedure: another session's file is lost"
    assert g.stop and g.reason == "listed" and g.printed == [], f"no STOP: {g}"
    assert (repo.root / _NOTES).exists(), "notes.md was removed"


def _w22(line: str, ctx: Ctx, repo: Repo) -> None:
    """S-00004533 : sur ordre du pilote seul, un chemin à la fois, la commande lue sur la ligne — `-n.md` retiré (le
    `--` l'empêche d'être lu comme une option), `nested/` (dépôt imbriqué) jamais retiré, un nom hors de la règle de
    caractères jamais tapé (entre apostrophes, il ouvrait `touch`)."""
    assert ctx.replay is not None
    repo.write(_DASH, "another session's work\n")  # rejouable : le contrôle sur la ligne non mutée l'a retiré
    hid = ctx.replay(line)
    # Mesuré : un dépôt imbriqué ignoré est une clé d'`ignored_exec` et de `gitignores` — la repasse le nomme ; les deux
    # fichiers ne sont clés de rien. Le pire cas reste joué : le pilote ordonne quand même le retrait de tout.
    assert sorted(hid) == sorted([_DASH, _NESTED, _QUOTED]), hid
    assert _NESTED in ctx.protected and not {_DASH, _QUOTED} & ctx.protected, sorted(ctx.protected)
    assert repass(line, replace(ctx, hid=hid), repo).stop, "the procedure does not stop on what grep printed"
    s835, (cmd, no_dir, char_rule) = s835_of(line), removal_of(line)
    passable = passable_of(s835) if s835 is not None else None
    typed_argv: list[list[str]] = []
    for p in hid:  # le pilote ordonne le retrait de CHAQUE chemin listé
        if (no_dir and p.endswith("/")) or (char_rule and passable is not None and not passable(p)):
            continue
        words = typed(p, cmd.endswith("'<path>'"))
        assert isinstance(words, list), f"{p!r} typed into {cmd!r}: {words}"
        argv = [w for t in shlex.split(cmd) for w in (words if t == "<path>" else [t])]
        cp = subprocess.run(argv, cwd=repo.root, env=repo.env, capture_output=True, text=True, timeout=60, check=False)
        assert cp.returncode == 0, f"{argv}: rc={cp.returncode} {cp.stderr}"
        typed_argv.append(argv)
    assert typed_argv == [["rm", "--", _DASH]], typed_argv
    assert not (repo.root / _DASH).exists(), "the ordered removal left the file"
    assert (repo.root / _NESTED / "work.txt").exists() and (repo.root / _QUOTED).exists(), "removed beyond the order"


def _w23(line: str, ctx: Ctx, repo: Repo) -> None:
    """S-00004533 : P3 jouée depuis un sous-dossier (`docs/`) imprime `notes.md` relatif à la RACINE, comme les clés
    de l'état — sans `--full-name -- :/`, rien hors du dossier courant n'est listé."""
    assert ctx.replay is not None
    hid = ctx.replay(line, "docs")
    assert hid == [_NOTES], f"from docs/: {hid}"


Check = Callable[[str, Ctx, Repo], None]
WITNESSES: dict[str, tuple[Callable[[Repo], Ctx], Check]] = {
    "W1": (_W1, _stops_printing(_TASKS)),
    "W2": (_hook_dirty, _stops_printing(".githooks/commit-msg")),
    "W3": (_rewritten(".agents/bin/new_other.py", commit=False), _stops_printing(".agents/bin/new_other.py")),
    "W4": (_rewritten(_TASKS, dirty=None), _w4),
    "W5": (_rewritten(".gitignore", commit=False, dirty=GITIGNORE + "# another session\n", window=GITIGNORE + "*.x\n"),
           _stops_printing(".gitignore")),
    "W6": (_state_one_byte, _stops_nonzero(3)),
    "W6b": (_state_no_dirty, _stops_nonzero(None)),
    "W7": (_rewritten(".agents/bin/a b.py"), _never_passed(".agents/bin/a b.py", ".agents/bin/a b.py")),
    "W7b": (_rewritten(".agents/bin/é.py"), _never_passed(".agents/bin/é.py", ".agents/bin/\\xe9.py")),
    "W8": (_link_dirty, _stops_printing(".agents/bin/l.py")),
    "W9": (_W1, _w9),
    "W10": (_planted_modules, _w10),
    "W11": (_config_include_dirty, _stops_printing("cfg/extra.gitconfig")),
    # S-00004460 : hors de la liste blanche, jamais tapé — `;` et `|` ouvriraient une autre commande, `{` réécrit le mot.
    "W12": (_posix_name(".agents/bin/a;sh"), _never_passed(".agents/bin/a;sh", ".agents/bin/a;sh")),
    "W13": (_posix_name(".agents/bin/b|sh"), _never_passed(".agents/bin/b|sh", ".agents/bin/b|sh")),
    "W14": (_posix_name(".agents/bin/{c,d}.py"), _never_passed(".agents/bin/{c,d}.py", ".agents/bin/{c,d}.py")),
    # Passe decies : un chemin ignoré présent au snapshot puis réécrit (W15, W17), un membre `replace:` seul (W16).
    "W15": (_rewritten(_WIP, commit=False), _stops_printing_from("ignored_exec", _WIP)),
    "W16": (_replace_only, _w16),
    "W17": (_rewritten(_SELF_IGNORED, commit=False, dirty="*\n# another session\n", window="*\n!evil.py\n"),
            _stops_printing_from("gitignores", _SELF_IGNORED)),
    # Passe de correction (S-00004527 F1) : ce que grep imprime, repassé au test (W18) ; `info:` et `alternates:` seuls,
    # passés sans STOP (W19, W20) — le comportement, pas seulement le texte.
    "W18": (_info_hides_dirty, _w18),
    "W19": (_control_written(_EXCLUDE), _passed_alone("info:" + _EXCLUDE, "ls-files -o -i --exclude-standard")),
    "W20": (_control_written(_ALTERNATES), _passed_alone("alternates:" + _ALTERNATES, "remove the named file")),
    # 2e passe de correction (S-00004533) : déjà ignoré au snapshot, clé d'aucune table — listé et STOP (W21) ; retrait
    # sur ordre seul, `rm --` un chemin à la fois (W22) ; captures relatives à la racine depuis un sous-dossier (W23).
    "W21": (_old_rule_hides(_NOTES), _w21),
    "W22": (_old_rule_hides(_DASH, _QUOTED, nested=True), _w22),
    "W23": (_old_rule_hides(_NOTES), _w23),
}
_W_PARAMS = [(h, w) for h in RC.ROUTE_HOSTS for w in WITNESSES]


@pytest.mark.parametrize(("host", "witness"), _W_PARAMS, ids=[f"{h}-{w}" for h, w in _W_PARAMS])
def test_witness_on_route_host(tmp_path: Path, host: str, witness: str) -> None:
    scenario, ok = WITNESSES[witness]
    repo = Repo(tmp_path)
    ok(RC._route_line(host), scenario(repo), repo)


def s1(line: str) -> None:
    """S1 : une fois, entre « prints nothing. » et « hooks: — », avant la première tête ; l'ancienne
    sous-règle (le seul fichier de contrôle suivi) a disparu."""
    s835 = s835_of(line)
    assert s835 is not None and line.count(S835_HEAD) == 1, "S835 is not present exactly once"
    assert f"prints nothing. {s835} hooks: — " in line, "S835 is not between « prints nothing. » and « hooks: — »"
    assert governed(line, s835) is None, "S835 does not precede the first gesture head"
    assert "another session's hunk" not in line, "the old control-file-only sub-rule is still there"


@pytest.mark.parametrize("host", RC.ROUTE_HOSTS)
def test_s1_structure_and_identity(host: str) -> None:
    line = RC._route_line(host)
    s1(line)
    assert s835_of(line) == s835_of(RC._route_line("claude")), f"{host}: S835 bytes differ from .claude"


# --- mutants : la ligne d'un hôte mutée EN MÉMOIRE ; chacun rougit ses témoins, les « restés verts » le bornent -----
_OLD_SUBRULE = (' one already dirty at the snapshot (its path is a key of the "dirty" map in the state file): STOP, ask the'
                " pilot — git restore would erase another session's hunk;")
_ALLOWED = "outside [A-Za-z0-9._/-]"
_WHITELIST_RULE = f"a path carrying any character {_ALLOWED} is never passed: STOP, and each path passed is single-quoted;"
_BLACKLIST_RULE = "a path carrying ' $ backtick \" whitespace or a backslash is never passed: STOP;"


def _in_s835(old: str, new: str) -> Callable[[str], str]:
    def go(line: str) -> str:
        s835 = s835_of(line)
        assert s835 is not None and s835.count(old) == 1, f"anchor missing or repeated in S835: {old!r}"
        return line.replace(s835, s835.replace(old, new), 1)
    return go


def _m1_head_line(line: str) -> str:
    """La ligne d'avant T-835 : S835 retirée, l'ancienne sous-règle (fichier de contrôle suivi seul) remise."""
    s835 = s835_of(line)
    assert s835 is not None
    out, at = line.replace(" " + s835, "", 1), "procedure above first, before restoring it;"
    assert out.count(at) == 1, at
    return out.replace(at, at + _OLD_SUBRULE, 1)


def _m4_restore_instead_of_stop(line: str) -> str:
    s835 = s835_of(line)
    assert s835 is not None and "STOP" in s835
    return line.replace(s835, s835.replace("STOP", "the pilot restores it by git restore"), 1)


def _m8_into_hooks_body(line: str) -> str:
    s835 = s835_of(line)
    assert s835 is not None
    out, head = line.replace(" " + s835, "", 1), "prints nothing. hooks: — "
    assert out.count(head) == 1, head
    return out.replace(head, f"{head}{s835} ", 1)


_REPASS_TEXT = ("first pass every printed path to the Dirty-at-the-snapshot test above (same state file, same digest, same "
                "character rule) — a path it prints, or a non-zero exit → STOP, ask the pilot; ")
_LISTED_TEXT = ("then, whatever it printed, LIST every path grep printed to the pilot and STOP: the procedure never removes a "
                "path grep printed, the pilot decides path by path")


def _m19_grep_not_repassed(line: str) -> str:
    """La repasse retirée du pas grep (la liste au pilote gardée) : le chemin protégé n'est plus NOMMÉ comme tel."""
    assert line.count(_REPASS_TEXT) == 1, "the repass clause is missing or repeated"
    return line.replace(_REPASS_TEXT, "", 1)


def _m20_remove_it_back(line: str) -> str:
    """« remove it » remis après la repasse (le texte de 14b9701e) : ce que le test passe en silence est retiré."""
    assert line.count(_LISTED_TEXT) == 1, "the LIST-and-STOP clause is missing or repeated"
    return line.replace(_LISTED_TEXT, "only then inspect each remaining path and remove it", 1)


def _on_line(old: str, new: str, n: int = 1) -> Callable[[str], str]:
    def go(line: str) -> str:
        assert line.count(old) == n, f"anchor not present exactly {n} time(s): {old!r}"
        return line.replace(old, new)
    return go


_ALL = ("S1", *WITNESSES)
MUTANTS: dict[str, tuple[Callable[[str], str], tuple[str, ...], tuple[str, ...]]] = {  # nom -> (mutation, rougis, verts)
    # W23 ne lit que les captures de P3, jamais S835 : il reste vert, il borne M1.
    "M1_head_line": (_m1_head_line, tuple(w for w in _ALL if w != "W23"), ("W23",)),
    "M2_control_files_only": (_in_s835("a member of the ERROR line or an executable OUT or DECLARED-OUT path,",
                                       "a .gitignore, .gitattributes, .gitmodules or .mailmap,"), ("W1", "W2", "W3", "W8", "W15"),
                              ("W5",)),
    "M3_tracked_only": (_in_s835("tracked or untracked,", "tracked,"), ("W3",), ("W1",)),
    "M4_restore_instead_of_stop": (_m4_restore_instead_of_stop, ("W1", "W2", "W3", "W5", "W8", "W15"), ()),
    "M5_no_digest_test": (_in_s835(" or hashlib.sha256(b).hexdigest()!=sys.argv[2]", ""), ("W6",), ("W1",)),
    "M6_watched_map": (_in_s835('j["dirty"]', 'j["watched"]'), ("W1",), ()),
    # C1 : la liste blanche élargie, un caractère à la fois — le blanc (W7), puis l'antislash d'une forme échappée (W7b).
    "M7a_whitespace_passed": (_in_s835(_ALLOWED, "outside [A-Za-z0-9._/ -]"), ("W7",), ("W7b",)),
    "M7b_backslash_passed": (_in_s835(_ALLOWED, "outside [A-Za-z0-9._/\\-]"), ("W7b",), ("W7",)),
    "M8_moved_into_hooks": (_m8_into_hooks_body, ("S1", "W1"), ("W2",)),
    "M9_nonzero_not_a_stop": (_in_s835("; a non-zero exit → STOP as rc 2", ""), ("W6",), ()),
    "M10_dirty_defaulted": (_in_s835('j["dirty"]', 'j.get("dirty", {})'), ("W6b",), ("W1",)),
    "M11_via_not_passed": (_in_s835(" its via= value,", ""), ("W8",), ("W1",)),
    # C2 : `-I` retiré — un `json.py` planté à la racine s'exécute.
    "M12_no_isolation": (_in_s835("python3 -I -S -c", "python3 -S -c"), ("W10",), ("W1",)),
    # C3 et C7, au-delà de la table du plan : leurs témoins doivent pouvoir rougir.
    "M13_no_argv_guard": (_in_s835("len(sys.argv)<4 or ", ""), ("W9",), ("W6",)),
    "M14_config_file_not_passed": (_in_s835(", and the file after config: (before its [)", ""), ("W11",), ("W2",)),
    # S-00004460 : la liste blanche (et les apostrophes) remplacée par l'ancienne liste noire — W7/W7b restent STOP.
    "M15_blacklist_back": (_in_s835(_WHITELIST_RULE, _BLACKLIST_RULE), ("W12", "W13", "W14"), ("W7", "W7b")),
    # Passe decies (S-00004495, S-00004497) : une table retirée du test, ou `replace:` retiré du gabarit.
    "M16_ignored_exec_not_read": (_in_s835(' or p in j["ignored_exec"]', ""), ("W15",), ("W1", "W17")),
    "M17_replace_not_passed": (_in_s835(" or replace:", ""), ("W16",), ("W2",)),
    "M18_gitignores_not_read": (_in_s835(' or p in j["gitignores"]', ""), ("W17",), ("W1", "W15")),
    # Passe de correction (S-00004527 F1) : la repasse retirée du pas grep — hors S835, d'où une mutation de la ligne.
    "M19_grep_not_repassed": (_m19_grep_not_repassed, ("W18",), ("W19", "W20", "W1", "W21")),
    # 2e passe de correction (S-00004533) : « remove it » remis (M20), le retrait sans `--` (M21), un chemin en `/`
    # admis (M22), les captures relatives au dossier courant (M23), la règle de caractères retirée du retrait (M24).
    "M20_remove_it_back": (_m20_remove_it_back, ("W21",), ("W18", "W1", "W23")),
    "M21_rm_without_dashdash": (_on_line("rm -- '<path>'", "rm '<path>'"), ("W22",), ("W21",)),
    "M22_directory_removed": (_on_line(_NO_DIR, ""), ("W22",), ("W21",)),
    "M23_relative_to_cwd": (_on_line('--exclude-standard --full-name -- :/ > "$T/', '--exclude-standard > "$T/', 2),
                            ("W23",), ("W21",)),
    "M24_char_rule_dropped": (_on_line(_CHAR_RULE, ""), ("W22",), ("W21",)),
}
_M_PARAMS = [(m, w, True) for m, (_f, reds, _g) in MUTANTS.items() for w in reds] + [
    (m, w, False) for m, (_f, _r, greens) in MUTANTS.items() for w in greens]


def _runner(witness: str, tmp_path: Path) -> Callable[[str], None]:
    """Le scénario joué UNE fois ; le contrôle, rejouable sur toute ligne."""
    if witness == "S1":
        return s1
    scenario, ok = WITNESSES[witness]
    repo = Repo(tmp_path)
    ctx = scenario(repo)
    return lambda line: ok(line, ctx, repo)


@pytest.mark.parametrize(("mut", "witness", "red"), _M_PARAMS,
                         ids=[f"{m}-{w}-{'red' if r else 'green'}" for m, w, r in _M_PARAMS])
def test_mutant_turns_its_witness_red(tmp_path: Path, mut: str, witness: str, red: bool) -> None:
    mutate = MUTANTS[mut][0]
    line = RC._route_line(RC.ROUTE_HOSTS[list(MUTANTS).index(mut) % len(RC.ROUTE_HOSTS)])
    mutated = mutate(line)
    assert mutated != line, f"{mut}: the mutation did not apply"
    check = _runner(witness, tmp_path)
    check(line)  # contrôle : vert sur la ligne non mutée
    if red:
        with pytest.raises(AssertionError):
            check(mutated)
    else:
        check(mutated)
