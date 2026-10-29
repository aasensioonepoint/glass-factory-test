"""T-00000134 — `sys.modules[spec.name] = module` AVANT `exec_module`, partout.

LE DEFAUT, ET POURQUOI IL EST INVISIBLE. Le motif
`module_from_spec` -> `exec_module` sans enregistrement prealable marche la
plupart du temps. Il casse quand le module charge porte des ANNOTATIONS EN
CHAINE (`from __future__ import annotations`, ou des annotations citees) ET que
`typing` est deja dans `sys.modules` : `dataclasses` resout alors ses annotations
en interrogeant `sys.modules[cls.__module__]`, qui n existe pas encore. Mesure
sur Python 3.14.6 (L-00000142). Ce depot charge des modules par chemin explicite
dans les hooks de ses QUATRE hotes — c est-a-dire sur le chemin chaud d une
session — et un seul `from __future__ import annotations` ajoute plus tard a
`tasks.py`, `ledger.py` ou `events.py` armerait le defaut d un coup, partout.

TROIS ARMS, ET LE TROISIEME EST CELUI QUI TIENT DANS LE TEMPS :
  1. le motif NON enregistre casse sur la fixture — la precondition existe bien
     sur cette plateforme, sinon les deux autres arms ne mesureraient rien ;
  2. le motif enregistre charge — le correctif est le bon ;
  3. FILET REPO-WIDE : chaque `exec_module` de l arbre porte un enregistrement en
     amont proche, OU un marqueur explicite disant pourquoi il n en a pas.

LE PERIMETRE DU FILET EST CELUI DE SON NOM. Il balaye `.claude/`, `.codex/`,
`.gemini/`, `.github/`, `.kimi-code/`, `.agents/` ET `agentic_v3/`. Ce dernier avait ete oublie
d une premiere redaction, alors que le plan revendiquait couvrir un site qui y
vit (`board_bridge.py`) : une garde plus etroite que son nom est exactement le
perimetre-retreci-en-silence que ce depot nomme comme le pire mode de defaillance
d une garde.

UN COMMENTAIRE N EST PAS UN ENREGISTREMENT (T-00000778). La preuve
d enregistrement ne se lit que sur des lignes de CODE : un commentaire qui cite
`sys.modules[cls.__module__]` dans la fenetre satisfaisait le filet, et retirer
la vraie ligne restait vert (mesure par le binome de cloture). Le marqueur
d exemption, lui, EST un commentaire et se lit sur toutes les lignes.

UN CHECKOUT IMBRIQUE NON ENREGISTRE N EST PAS CE DEPOT (T-00001073). Un dev qui
travaille en worktree pose une copie ENTIERE du depot sous `.claude/worktrees/` :
le filet y lisait les fichiers d une autre branche et rougissait la porte sur
un code qui n est pas celui qu elle juge (mesure sur un clone a worktree vivant :
rouge). Le balayage descend donc par `os.walk` et n entre pas dans un enfant
qui porte son propre `.git` (bloc `_checkout_imbrique`) ET que rien n enregistre
(garde `_elague`, qui interroge l index du checkout qui CONTIENT le candidat).
Un sous-module, un gitlink, tout dossier portant des fichiers SUIVIS restent lus :
seul du contenu NON SUIVI peut etre ecarte. Les bornes sont dites au bloc ; la
table des bras qui les tient est `NestedCheckoutPruneTests`.
"""
from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import typing  # noqa: F401 - PRECONDITION: `typing` doit etre dans sys.modules
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "dataclass_probe.py"

SCAN_DIRS = (".claude", ".codex", ".gemini", ".github", ".kimi-code", ".agents", "agentic_v3")
SKIP_PARTS = {".git", "node_modules", "__pycache__", ".worktrees", "dist", "build"}
# `.agents/state/local/` est git-ignore : sondes jetables, vues generees. Y
# exiger le motif ferait rougir le filet sur des fichiers qui ne sont pas du
# code du depot et que personne ne peut corriger durablement.
SKIP_PREFIXES = (".agents/state/local/",)

EXEC_RE = re.compile(r"\.exec_module\s*\(")
REG_RE = re.compile(r"sys\.modules\s*\[")
EXEMPT_RE = re.compile(r"#\s*unregistered on purpose:")

# Fenetre amont, en lignes. Un enregistrement vit juste apres `module_from_spec`,
# donc a quelques lignes de l `exec_module` ; une fenetre large accepterait un
# `sys.modules[` sans rapport situe ailleurs dans la fonction et rendrait le
# filet complaisant.
LOOKBACK = 8


def _is_comment(line: str) -> bool:
    """Ligne dont la forme strippee ouvre sur `#` : elle ne prouve rien."""
    return line.lstrip().startswith("#")


def _unregistered_exec_lines(lines: list[str]) -> list[int]:
    """Numeros (base 1) des `exec_module` sans enregistrement en amont proche
    ni marqueur d exemption. REG_RE ne compte que sur les lignes de CODE ;
    EXEMPT_RE compte sur toutes, puisque le marqueur est un commentaire."""
    flagged = []
    for i, line in enumerate(lines):
        if not EXEC_RE.search(line):
            continue
        window = lines[max(0, i - LOOKBACK):i + 1]
        if any(REG_RE.search(w) for w in window if not _is_comment(w)):
            continue
        if any(EXEMPT_RE.search(w) for w in window):
            continue
        flagged.append(i + 1)
    return flagged


def _load(name: str, path: Path, register: bool):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    if register:
        sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(spec.name, None)
        raise
    return module


def _precondition_reproduces() -> bool:
    """La plateforme reproduit-elle le defaut ? Mesure, jamais supposee."""
    try:
        _load("dataclass_probe_precheck", FIXTURE, register=False)
    except Exception:
        return True
    finally:
        sys.modules.pop("dataclass_probe_precheck", None)
    return False


class MotifTests(unittest.TestCase):
    def test_the_fixture_exists_and_carries_the_precondition(self):
        """NON-VACUITE des deux arms suivants : sans la fixture, ils passeraient
        ou echoueraient pour une raison qui n a rien a voir."""
        self.assertTrue(FIXTURE.is_file(), f"{FIXTURE} manquante")
        text = FIXTURE.read_text(encoding="utf-8")
        self.assertIn("from __future__ import annotations", text)
        self.assertIn("@dataclass", text)

    @unittest.skipUnless(_precondition_reproduces(),
                         "cette plateforme ne reproduit pas le defaut (L-00000142) — "
                         "l arm est SAUTE, jamais affaibli")
    def test_unregistered_motif_breaks_dataclass_probe(self):
        """Le motif fautif, sur la precondition exacte, LEVE."""
        with self.assertRaises(Exception):
            _load("dataclass_probe_unregistered", FIXTURE, register=False)
        sys.modules.pop("dataclass_probe_unregistered", None)

    def test_registered_motif_loads_dataclass_probe(self):
        """Le motif corrige charge, et le module est utilisable — resoudre les
        annotations est justement ce qui levait."""
        try:
            mod = _load("dataclass_probe_registered", FIXTURE, register=True)
            self.assertEqual(["name", "count"], mod.probe_fields())
        finally:
            sys.modules.pop("dataclass_probe_registered", None)


# --- CHECKOUTS IMBRIQUES (T-00001073) ----------------------------------------
# Le BLOC ci-dessous est TEXTUELLEMENT identique dans les quatre fichiers qui
# parcourent l arbre avec lui (check-stale-justification.sh, ce fichier,
# test_automode_doctrine.py, test_repo_walk_census.py) : epingle par empreinte
# dans le recensement. Il dit « ce dossier porte son propre `.git` » — DOSSIER
# (clone, sous-module embarque, lien vers un dossier ; vide compris) ou gitfile de
# WORKTREE (`gitdir: .../worktrees/<n>`, absolu ou relatif, perime compris).
# checkout imbrique : debut (T-00001073)
def _checkout_imbrique(chemin):
    marqueur = os.path.join(chemin, ".git")
    if os.path.isdir(marqueur):
        return True
    if not os.path.isfile(marqueur):
        return False
    try:
        with open(marqueur, encoding="utf-8", errors="replace") as fh:
            ligne = fh.readline(4096)
    except OSError:
        return False
    m = re.match(r"gitdir:\s*(.+?)\s*$", ligne)
    return bool(m and re.search(r"/worktrees/[^/]+/?$", m.group(1).replace("\\", "/")))
# checkout imbrique : fin (T-00001073)


# LA GARDE (texte M, identique dans test_repo_walk_census.py) : un candidat du bloc
# n est elague que si RIEN ne l enregistre dans l index du checkout qui le CONTIENT
# directement (`git -C <parent> ls-files -s -- ":(literal)<nom>"` ; git remonte
# lui-meme au premier `.git`, donc un sous-module de sous-module est vu).
# ENREGISTRE <=> rc 0 ET sortie non vide : gitlink, sous-module, ou tout dossier
# portant des fichiers SUIVIS. Bornes, dites parce qu un banc qui ne les dit pas
# les fait passer pour universelles :
#   * mode decide UNE fois a la racine, paresseusement (0 appel git sans
#     candidat) : depot -> l index fait foi ; « hors depot » -> mode `none`, tout
#     candidat est elague SANS appel (aucun index n existe) ; tout autre echec
#     LEVE — racine illisible, propriete douteuse, `.git` bidon ;
#   * dans un depot, un enfant que git declare « hors depot » est une DECOUVERTE
#     BLOQUEE (plafond, point de montage), jamais une absence : LEVE ; tout autre
#     rc sur un enfant (gitfile invalide, index corrompu) : LEVE ; git absent :
#     `OSError` remonte — un banc qui ne peut pas juger ne conclut pas ;
#   * environnement PURGE PAR PREFIXE : tout GIT_* est retire sauf
#     GIT_CONFIG_GLOBAL, GIT_CONFIG_SYSTEM, GIT_CONFIG_NOSYSTEM ; locale C, sinon
#     le message « hors depot » est traduit ;
#   * la requete d index NEUTRALISE la config du depot interroge (`-c
#     core.fsmonitor=false -c core.hooksPath=/dev/null` avant `-C`) : un clone
#     embarque issu d une archive non fiable executait son `core.fsmonitor` a
#     chaque `ls-files -s` (mesure git 2.55, S-00003664) ;
#   * chaque appel git est borne a 60 s : passe ce delai,
#     `subprocess.TimeoutExpired` REMONTE — ni elague ni balaye en silence ;
#   * racine non git SOUS un depot ancetre : l index de l ancetre fait foi.
# garde d'index (T-00001073) : debut
_GARDE_CONSERVE = ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM")
_GARDE_HORS_DEPOT = "not a git repository (or any"


def _garde_env():
    e = {k: v for k, v in os.environ.items() if not k.startswith("GIT_") or k in _GARDE_CONSERVE}
    e["LC_ALL"] = "C"
    e["LANGUAGE"] = ""
    return e


def _garde_mode(racine):
    p = subprocess.run(["git", "-C", racine, "rev-parse", "--is-inside-work-tree"],
                       capture_output=True, text=True, env=_garde_env(), timeout=60)
    if p.returncode == 0 and p.stdout.strip() == "true":
        return "git"
    if p.returncode == 128 and _GARDE_HORS_DEPOT in p.stderr.lower():
        return "none"
    raise RuntimeError(
        f"garde d'index : git ne sait pas dire si {racine} est un depot (rc={p.returncode}, "
        f"stdout={p.stdout.strip()!r}, stderr={p.stderr.strip()!r}) — ce n est PAS lu comme "
        "« hors depot » : un checkout imbrique y serait elague en silence")


def _enregistre(chemin, mode):
    if mode == "none":
        return False
    p = subprocess.run(["git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null",
                        "-C", os.path.dirname(chemin), "ls-files", "-s", "--",
                        ":(literal)" + os.path.basename(chemin)],
                       capture_output=True, text=True, env=_garde_env(), timeout=60)
    if p.returncode == 0:
        return bool(p.stdout.strip())
    if p.returncode == 128 and _GARDE_HORS_DEPOT in p.stderr.lower():
        raise RuntimeError(
            f"garde d'index : decouverte BLOQUEE sur {chemin} sous une racine git "
            f"({p.stderr.strip()!r}) — plafond ou point de montage, jamais « non enregistre »")
    raise RuntimeError(
        f"garde d'index : git ne sait pas dire si {chemin} est enregistre (rc={p.returncode}, "
        f"stderr={p.stderr.strip()!r}) — ni elague ni balaye en silence")


def _elague(chemin, racine, etat):
    if not _checkout_imbrique(chemin):
        return False
    if "mode" not in etat:
        etat["mode"] = _garde_mode(racine)
    return not _enregistre(chemin, etat["mode"])
# garde d'index (T-00001073) : fin


def _python_sources(root=ROOT):
    """Les `.py` et les `.sh` (les hooks portent du python en heredoc : le meme
    defaut y vit) sous les SCAN_DIRS de `root`.

    UN SEUL `os.walk` PAR SCAN_DIR, ET L ELAGAGE EST RELATIF A `root`.
    `SKIP_PARTS` juge le NOM de chaque enfant — l ancienne forme testait les
    parties du chemin ABSOLU, donc un depot clone sous un dossier `build/` ou
    `.worktrees/` perdait TOUT son balayage et le filet passait vert sur un
    corpus vide. `SKIP_PREFIXES` passe AVANT la garde, pour qu un dossier deja
    ecarte ne coute jamais un appel git."""
    racine = os.fspath(root)
    etat = {}
    for base in SCAN_DIRS:
        top = os.path.join(racine, base)
        if not os.path.isdir(top):
            continue
        for dirpath, dirnames, filenames in os.walk(top):
            rel_dir = os.path.relpath(dirpath, racine).replace(os.sep, "/") + "/"
            if rel_dir.startswith(SKIP_PREFIXES):
                dirnames[:] = []
                continue
            dirnames[:] = [d for d in dirnames if d not in SKIP_PARTS
                           and not _elague(os.path.join(dirpath, d), racine, etat)]
            for nom in filenames:
                if nom.endswith((".py", ".sh")):
                    yield Path(dirpath) / nom


class RepoWideNetTests(unittest.TestCase):
    def test_vendor_seul_reste_dans_le_balayage(self):
        with tempfile.TemporaryDirectory(prefix="modload-vendor-") as tmp:
            racine = Path(tmp)
            source = racine / ".agents/vendor/agentic_v3/probe.py"
            source.parent.mkdir(parents=True)
            source.write_text("spec.loader.exec_" + "module(module)\n", encoding="utf-8")
            self.assertIn(source, set(_python_sources(racine)))
            self.assertEqual([1], _unregistered_exec_lines(source.read_text().splitlines()))

    def test_the_scan_is_not_empty(self):
        """NON-VACUITE du filet : un balayage qui ne trouve aucun `exec_module`
        serait vert en ne mesurant rien — le mode de defaillance exact qu une
        garde ne doit jamais avoir."""
        hits = [p for p in _python_sources()
                if EXEC_RE.search(p.read_text(encoding="utf-8", errors="replace"))]
        self.assertGreaterEqual(
            len(hits), 20,
            f"le balayage n a trouve que {len(hits)} fichiers portant exec_module — "
            "perimetre casse plutot qu arbre propre")

    def test_no_exec_module_without_registration_repo_wide(self):
        offenders = []
        for path in _python_sources():
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            rel = path.relative_to(ROOT).as_posix()
            offenders.extend(f"{rel}:{n}" for n in _unregistered_exec_lines(lines))
        self.assertEqual(
            [], offenders,
            "exec_module sans sys.modules[...] (ligne de CODE) en amont proche, et "
            "sans marqueur `# unregistered on purpose: <raison>` :\n  "
            + "\n  ".join(offenders))


class CommentIsNotRegistrationTests(unittest.TestCase):
    """Temoin T-00000778 : la meme logique que le filet, sur une source
    synthetique. Le premier arm rougit si le filtre `_is_comment` saute."""

    HEAD = [
        "import importlib.util, sys",
        "def load(path):",
        "    spec = importlib.util.spec_from_file_location('m', path)",
        "    module = importlib.util.module_from_spec(spec)",
    ]
    COMMENT = "    # dataclasses lit sys.modules[cls.__module__] : a enregistrer"
    EXEC = "    spec.loader.exec_module(module)"

    def test_registration_cited_only_in_a_comment_is_flagged(self):
        lines = self.HEAD + [self.COMMENT, self.EXEC]
        self.assertEqual([len(lines)], _unregistered_exec_lines(lines))

    def test_real_registration_is_not_flagged(self):
        lines = self.HEAD + [self.COMMENT, "    sys.modules[spec.name] = module", self.EXEC]
        self.assertEqual([], _unregistered_exec_lines(lines))

    def test_exemption_marker_comment_is_not_flagged(self):
        lines = self.HEAD + ["    # unregistered on purpose: module jetable", self.EXEC]
        self.assertEqual([], _unregistered_exec_lines(lines))


# --- BANC DES CHECKOUTS IMBRIQUES (T-00001073) ---------------------------------
# UN VRAI arbre git par famille de bras, construit sous un repertoire temporaire
# HORS du depot. Regles de construction, parce que ce banc VOYAGE et tourne dans
# `python:3.14-slim` (git 2.47, aucune identite) : environnement git purge par
# prefixe et configuration globale/systeme NEUTRE ; identite LOCALE par depot qui
# commite (jamais GIT_AUTHOR_*) ; `-c protocol.file.allow=always` sur tout
# sous-module ; gitfile relatif de W8 ECRIT ; fichiers SUIVIS de W7/W12 commites
# AVANT le gitfile ou le `git init` (sinon le dossier devient un gitlink, et le
# bras mesure autre chose), precondition 100644 assertee ; voisin de LIT et hote
# de W3d tires d une source SANS offenseur ; options git >= 2.40 seulement.
# unregistered on purpose: texte d offenseur PLANTE dans les bancs temporaires, jamais execute
_OFFENSEUR_PY = "def f(spec, module):\n    spec.loader.exec_module(module)\n"
_OFFENSEUR_SH = "python3 - <<X\n    spec.loader.exec_module(module)\nX\n"
_WINDOWS = os.name == "nt"

# Bras de la racine git K : (dossier du candidat, verdict). P = elague (ses
# offenseurs ne sont PAS vus), S = balaye (ils le sont).
_BRAS_K = {
    "W1": (".claude/worktrees/w1", "P"),      # worktree lie, gitfile absolu
    "W8": (".claude/worktrees/w8", "P"),      # worktree lie, gitfile relatif ECRIT
    "W9": (".claude/w9", "P"),                # worktree perime (gitdir disparu)
    "W2": (".claude/w2", "P"),                # clone non enregistre
    "W10": (".claude/w10", "P"),              # `.git` lien vers un dossier
    "W11": (".claude/w11p/w11", "P"),         # clone dont le PARENT porte un fichier suivi
    "LIT": (".claude/lit/[y]", "P"),          # clone a cote du sous-module `y` (glob)
    "DEREG": (".claude/dereg", "P"),          # ex-sous-module retire de l index ET de .gitmodules
    "DEREG2": (".claude/dereg2", "P"),        # retire de l index, `path =` perime : Py ne lit pas .gitmodules
    "W5e": (".claude/w5e", "P"),              # DOSSIER `.git` VIDE, rien de suivi dessous : borne nommee
    "W3": (".claude/w3", "S"),                # sous-module absorbe
    "W3b": (".claude/w3b", "S"),              # sous-module EMBARQUE (`.git` dossier)
    "W3c": (".claude/w3c", "S"),              # gitlink sans .gitmodules
    "W3d": (".claude/w3dh/inner", "S"),       # embarque DANS un sous-module
    "W3g": (".claude/w3g", "S"),              # sous-module embarque CORROMPU (HEAD retire)
    "R": (".claude/r/worktrees/foo", "S"),    # sous-module dont le chemin finit en worktrees/<n>
    "W4": (".claude/w4", "S"),                # texte de gitfile « sous-module dans un worktree »
    "W5": (".claude/w5", "S"),                # `.git` FICHIER vide
    "W5b": (".claude/w5b", "S"),              # gitdir bidon
    "W10b": (".claude/w10b", "S"),            # lien pendant
    "W6": (".claude/w6", "S"),                # temoin sans `.git`
    "W7": (".claude/w7", "S"),                # fichiers SUIVIS sous un gitfile de worktree
    "W12": (".claude/w12", "S"),              # fichiers SUIVIS sous un `git init` parasite
}
_LIENS = ("W10", "W10b")


def _env_construction(base):
    vide = os.path.join(base, "vide.gitconfig")
    if not os.path.exists(vide):
        with open(vide, "w", encoding="utf-8"):
            pass
    e = {k: v for k, v in os.environ.items() if not k.startswith("GIT_") or k in _GARDE_CONSERVE}
    e.update(GIT_CONFIG_GLOBAL=vide, GIT_CONFIG_SYSTEM=vide, HOME=base, XDG_CONFIG_HOME=base,
             LC_ALL="C", LANGUAGE="")
    return e


class _Chantier:
    """Les commandes de construction d un banc : un environnement, des appels
    qui LEVENT au premier echec (un banc mal construit mesure autre chose)."""

    def __init__(self, base):
        self.base = base
        self.env = _env_construction(base)

    def git(self, *args, cwd=None):
        argv = ["git"] + (["-C", cwd] if cwd else []) + ["-c", "protocol.file.allow=always", *args]
        return subprocess.run(argv, check=True, capture_output=True, text=True, env=self.env).stdout

    def depot(self, chemin):
        os.makedirs(chemin, exist_ok=True)
        self.git("init", "-q", "-b", "main", chemin)
        self.git("config", "user.email", "t@t", cwd=chemin)
        self.git("config", "user.name", "t", cwd=chemin)

    def commit(self, chemin, message):
        self.git("add", "-A", cwd=chemin)
        self.git("commit", "-q", "-m", message, cwd=chemin)

    @staticmethod
    def planter(dossier):
        os.makedirs(os.path.join(dossier, "x"), exist_ok=True)
        with open(os.path.join(dossier, "x", "p.py"), "w", encoding="utf-8") as fh:
            fh.write(_OFFENSEUR_PY)
        with open(os.path.join(dossier, "x", "p.sh"), "w", encoding="utf-8") as fh:
            fh.write(_OFFENSEUR_SH)

    @staticmethod
    def ecrire(chemin, texte):
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        with open(chemin, "w", encoding="utf-8") as fh:
            fh.write(texte)

    def sources(self):
        """src1 PORTE les offenseurs (x/p.py, x/p.sh) ; src2 n en porte aucun."""
        s1, s2 = os.path.join(self.base, "src1"), os.path.join(self.base, "src2")
        self.depot(s1)
        self.planter(s1)
        self.ecrire(os.path.join(s1, "README"), "ok\n")
        self.commit(s1, "s1")
        self.depot(s2)
        self.ecrire(os.path.join(s2, "README"), "ok\n")
        self.commit(s2, "s2")
        return s1, s2

    def mode_suivi(self, racine, rel):
        return self.git("ls-files", "-s", "--", rel, cwd=racine)[:6]


def _construire_K(ch, s1, s2):
    """La racine git K qui porte tous les bras de `_BRAS_K`."""
    K = os.path.join(ch.base, "K")
    ch.depot(K)
    ch.ecrire(os.path.join(K, "README"), "k\n")
    ch.ecrire(os.path.join(K, ".claude", "w11p", "README"), "suivi\n")
    for rel in (".claude/w7", ".claude/w12"):
        ch.planter(os.path.join(K, rel))
    ch.commit(K, "k0")
    c = lambda rel: os.path.join(K, *rel.split("/"))  # noqa: E731 - chemin d un bras
    ch.git("submodule", "add", "-q", s1, ".claude/w3", cwd=K)
    ch.git("clone", "-q", s1, c(".claude/w3b"))
    ch.git("submodule", "add", "-q", s1, ".claude/w3b", cwd=K)
    ch.git("clone", "-q", s1, c(".claude/w3c"))
    ch.git("add", ".claude/w3c", cwd=K)
    ch.git("submodule", "add", "-q", s2, ".claude/w3dh", cwd=K)
    ch.git("clone", "-q", s1, c(".claude/w3g"))
    ch.git("submodule", "add", "-q", s1, ".claude/w3g", cwd=K)
    ch.git("submodule", "add", "-q", s1, ".claude/r/worktrees/foo", cwd=K)
    ch.git("submodule", "add", "-q", s2, ".claude/lit/y", cwd=K)
    for rel in (".claude/dereg", ".claude/dereg2"):
        ch.git("clone", "-q", s1, c(rel))
        ch.git("submodule", "add", "-q", s1, rel, cwd=K)
    ch.git("commit", "-q", "-m", "subs", cwd=K)
    ch.git("rm", "-q", "--cached", "-f", ".claude/dereg", ".claude/dereg2", cwd=K)
    ch.git("config", "-f", ".gitmodules", "--remove-section", "submodule..claude/dereg", cwd=K)
    # `.gitmodules` SEUL : un `add -A` re-enregistrerait les deux clones en gitlinks.
    ch.git("add", ".gitmodules", cwd=K)
    ch.git("commit", "-q", "-m", "dereg", cwd=K)
    # W3d : embarque DANS le sous-module w3dh, enregistre dans SON index seulement.
    ch.git("clone", "-q", s1, c(".claude/w3dh/inner"))
    ch.git("submodule", "add", "-q", s1, "inner", cwd=c(".claude/w3dh"))
    # W3g : HEAD retire APRES l enregistrement — un depot embarque illisible.
    os.remove(c(".claude/w3g/.git/HEAD"))
    ch.git("clone", "-q", s1, c(".claude/lit/[y]"))
    ch.git("worktree", "add", "-q", "--detach", ".claude/worktrees/w1", "HEAD", cwd=K)
    ch.planter(c(".claude/worktrees/w1"))
    ch.git("worktree", "add", "-q", "--detach", ".claude/worktrees/w8", "HEAD", cwd=K)
    ch.ecrire(c(".claude/worktrees/w8/.git"), "gitdir: ../../../.git/worktrees/w8\n")
    ch.planter(c(".claude/worktrees/w8"))
    ch.planter(c(".claude/w9"))
    ch.ecrire(c(".claude/w9/.git"), f"gitdir: {K}/.git/worktrees/gone\n")
    ch.git("clone", "-q", s1, c(".claude/w2"))
    ch.git("clone", "-q", s1, c(".claude/w11p/w11"))
    ch.planter(c(".claude/w5e"))
    os.makedirs(c(".claude/w5e/.git"))
    ch.planter(c(".claude/w4"))
    ch.ecrire(c(".claude/w4/.git"), "gitdir: ../../.git/worktrees/agent-x/modules/.claude/w4\n")
    ch.planter(c(".claude/w5"))
    ch.ecrire(c(".claude/w5/.git"), "")
    ch.planter(c(".claude/w5b"))
    ch.ecrire(c(".claude/w5b/.git"), "gitdir: /nonexistent\n")
    ch.planter(c(".claude/w6"))
    ch.ecrire(c(".claude/w7/.git"), f"gitdir: {K}/.git/worktrees/agent-x\n")
    ch.git("init", "-q", c(".claude/w12"))
    if not _WINDOWS:
        reel = os.path.join(ch.base, "w10reel")
        ch.git("clone", "-q", s1, reel)
        ch.planter(c(".claude/w10"))
        os.symlink(os.path.join(reel, ".git"), c(".claude/w10/.git"))
        ch.planter(c(".claude/w10b"))
        os.symlink(os.path.join(ch.base, "nulle-part", ".git"), c(".claude/w10b/.git"))
    return K


def _verdicts(racine, bras):
    """{bras: verdict} lu par le VRAI balayage : S si le `.py` ET le `.sh` du
    bras sont vus comme offenseurs, P si aucun, `?` si un seul (banc casse)."""
    vus = set()
    for path in _python_sources(racine):
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        if _unregistered_exec_lines(lines):
            vus.add(path.relative_to(racine).as_posix())
    out = {}
    for nom, (rel, _attendu) in bras.items():
        n = (f"{rel}/x/p.py" in vus) + (f"{rel}/x/p.sh" in vus)
        out[nom] = {2: "S", 0: "P"}.get(n, "?")
    return out


def _ecarts(obtenus, bras):
    return {b: (attendu, obtenus.get(b)) for b, (_rel, attendu) in bras.items() if obtenus.get(b) != attendu}


class NestedCheckoutPruneTests(unittest.TestCase):
    """T-00001073 — colonne Py de la table des bras. Un checkout imbrique NON
    ENREGISTRE n est pas lu ; tout chemin ENREGISTRE dans l index du checkout qui
    le contient l est. Chaque arm porte ses bras dans son message d echec, pour
    que le mutant qui le rougit se lise sans relancer."""

    @classmethod
    def setUpClass(cls):
        cls.base = os.path.realpath(tempfile.mkdtemp(prefix="t1073-modload-"))
        cls.ch = _Chantier(cls.base)
        cls.s1, cls.s2 = cls.ch.sources()
        cls.K = _construire_K(cls.ch, cls.s1, cls.s2)
        cls.bras = {k: v for k, v in _BRAS_K.items() if not (_WINDOWS and k in _LIENS)}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.base, ignore_errors=True)

    def _racine(self, nom):
        r = os.path.join(self.base, nom)
        os.makedirs(r)
        return r

    def _hors_depot(self, racine):
        p = subprocess.run(["git", "-C", racine, "rev-parse", "--is-inside-work-tree"],
                           capture_output=True, text=True, env=_garde_env())
        return p.returncode == 128 and _GARDE_HORS_DEPOT in p.stderr.lower()

    def test_preconditions_du_banc(self):
        """Un bras mal construit juge pour une autre raison : W7 et W12 doivent
        porter des fichiers SUIVIS (100644, jamais un gitlink 160000) ; W8 doit
        etre un vrai worktree malgre son gitfile reecrit."""
        for rel in (".claude/w7/x/p.py", ".claude/w12/x/p.py"):
            self.assertEqual("100644", self.ch.mode_suivi(self.K, rel), f"{rel} n est pas SUIVI")
        w8 = os.path.join(self.K, ".claude", "worktrees", "w8")
        self.assertEqual(os.path.realpath(w8),
                         os.path.realpath(self.ch.git("rev-parse", "--show-toplevel", cwd=w8).strip()))

    def test_table_T_sur_une_racine_git(self):
        """ELAGUES : W1 W8 W9 W2 W10 W11 LIT DEREG DEREG2 W5e. BALAYES : W3 W3b W3c
        W3d W3g R W4 W5 W5b W10b W6 W7 W12. DEREG2 diverge VOLONTAIREMENT de
        check-stale (qui lit le `path =` perime de .gitmodules et le balaie)."""
        self.assertEqual({}, _ecarts(_verdicts(self.K, self.bras), self.bras),
                         "{bras: (attendu, obtenu)}")

    @unittest.skipIf(_WINDOWS, "SKIP : `.git` lien symbolique non mesure sous Windows (W10, W10b)")
    def test_liens_symboliques(self):
        sous = {k: self.bras[k] for k in _LIENS}
        self.assertEqual({}, _ecarts(_verdicts(self.K, sous), sous))

    def test_W8r_le_vrai_relative_paths(self):
        aide = subprocess.run(["git", "worktree", "add", "-h"], capture_output=True, text=True).stdout
        aide += subprocess.run(["git", "worktree", "add", "-h"], capture_output=True, text=True).stderr
        if "relative-paths" not in aide:
            self.skipTest("SKIP : ce git ne connait pas --relative-paths (W8 ECRIT couvre la forme)")
        R = self._racine("W8r")
        self.ch.depot(R)
        self.ch.ecrire(os.path.join(R, "README"), "r\n")
        self.ch.commit(R, "r")
        self.ch.git("worktree", "add", "-q", "--relative-paths", "--detach", ".claude/worktrees/w8r", "HEAD", cwd=R)
        self.ch.planter(os.path.join(R, ".claude", "worktrees", "w8r"))
        bras = {"W8r": (".claude/worktrees/w8r", "P")}
        self.assertEqual({}, _ecarts(_verdicts(R, bras), bras))

    def test_rc128_hors_du_signal_hors_depot_LEVE(self):
        """W5c (clone sous un `.git` FICHIER vide), W5d (sous un gitdir bidon),
        IDX (index corrompu) : git echoue sur l ENFANT ; RACBOGUS : la racine porte
        elle-meme un `.git` bidon. Aucun n est « hors depot » : la garde LEVE,
        jamais elaguer ni balayer en silence."""
        w5c = self._racine("W5c")
        self.ch.depot(w5c)
        self.ch.ecrire(os.path.join(w5c, ".claude", "w5", ".git"), "")
        self.ch.git("clone", "-q", self.s1, os.path.join(w5c, ".claude", "w5", "c"))
        w5d = self._racine("W5d")
        self.ch.depot(w5d)
        self.ch.ecrire(os.path.join(w5d, ".claude", "w5b", ".git"), "gitdir: /nonexistent\n")
        self.ch.git("clone", "-q", self.s1, os.path.join(w5d, ".claude", "w5b", "c"))
        idx = self._racine("IDX")
        self.ch.depot(idx)
        self.ch.ecrire(os.path.join(idx, "README"), "i\n")
        self.ch.commit(idx, "i")
        self.ch.git("clone", "-q", self.s1, os.path.join(idx, ".claude", "idx"))
        self.ch.ecrire(os.path.join(idx, ".git", "index"), "garbage")
        bogus = self._racine("RACBOGUS")
        self.ch.ecrire(os.path.join(bogus, ".git"), "gitdir: /nonexistent\n")
        self.ch.planter(os.path.join(bogus, ".claude", "emb"))
        os.makedirs(os.path.join(bogus, ".claude", "emb", ".git"))
        non_leves = []
        for nom, racine in (("W5c", w5c), ("W5d", w5d), ("IDX", idx), ("RACBOGUS", bogus)):
            try:
                list(_python_sources(racine))
            except RuntimeError:
                continue
            non_leves.append(nom)
        self.assertEqual([], non_leves, "bras qui n ont PAS leve")

    def test_racine_non_git_tout_dot_git_elague_sans_appel(self):
        """NGborne, NGmod, NGquote, NGsp : racine HORS DEPOT, `.git` dossier ->
        elague (mode `none`). Py ne lit pas .gitmodules : divergence VOULUE avec
        check-stale, qui balaie les trois derniers."""
        textes = {"NGborne": None,
                  "NGmod": '[submodule "e"]\n\tpath = .claude/emb\n\turl = x\n',
                  "NGquote": '[submodule "e"]\n\tpath = ".claude/emb"\n\turl = x\n',
                  "NGsp": '[submodule "e"]\n  path=.claude/emb   \n'}
        ecarts = {}
        for nom, gitmodules in textes.items():
            R = self._racine(nom)
            if not self._hors_depot(R):
                self.skipTest(f"SKIP : le repertoire temporaire est SOUS un depot ({R}) — racine non git non constructible")
            self.ch.planter(os.path.join(R, ".claude", "emb"))
            os.makedirs(os.path.join(R, ".claude", "emb", ".git"))
            if gitmodules:
                self.ch.ecrire(os.path.join(R, ".gitmodules"), gitmodules)
            bras = {nom: (".claude/emb", "P")}
            ecarts.update(_ecarts(_verdicts(R, bras), bras))
        self.assertEqual({}, ecarts)

    def test_W4r_racine_worktree_portant_un_vrai_sous_module(self):
        Q = self._racine("Q")
        self.ch.depot(Q)
        self.ch.ecrire(os.path.join(Q, "README"), "q\n")
        self.ch.commit(Q, "q0")
        self.ch.git("submodule", "add", "-q", self.s1, ".claude/sub", cwd=Q)
        self.ch.git("commit", "-q", "-m", "sub", cwd=Q)
        W4r = os.path.join(self.base, "W4r")
        self.ch.git("worktree", "add", "-q", "--detach", W4r, "HEAD", cwd=Q)
        self.ch.git("submodule", "update", "-q", "--init", cwd=W4r)
        bras = {"W4r": (".claude/sub", "S")}
        self.assertEqual({}, _ecarts(_verdicts(W4r, bras), bras))

    def test_racine_sous_un_dossier_build_est_balayee(self):
        """SKIP_PARTS juge les noms RELATIFS a la racine : un depot clone sous
        `build/` (ou `.worktrees/`) garde tout son balayage."""
        for ancetre in ("build", ".worktrees"):
            R = os.path.join(self.base, ancetre, "kit")
            self.ch.planter(os.path.join(R, ".claude", "a"))
            bras = {ancetre: (".claude/a", "S")}
            self.assertEqual({}, _ecarts(_verdicts(R, bras), bras))

    def test_espion_un_chemin_elague_n_est_jamais_ouvert(self):
        vus = []
        vrai = os.scandir

        def espion(chemin="."):
            vus.append(os.fspath(chemin).replace("\\", "/"))
            return vrai(chemin)

        with mock.patch.object(os, "scandir", espion):
            list(_python_sources(self.K))
        k = self.K.replace("\\", "/")
        self.assertIn(f"{k}/.claude/w6", vus, "CONTROLE POSITIF : l espion ne voit pas un dossier balaye")
        for rel in (".claude/worktrees/w1", ".claude/w2"):
            entrees = [v for v in vus if v == f"{k}/{rel}" or v.startswith(f"{k}/{rel}/")]
            self.assertEqual([], entrees, f"{rel} est OUVERT puis filtre au lieu d etre elague")

    @unittest.skipIf(_WINDOWS, "SKIP : shim `git` en script sh non mesure sous Windows")
    def test_shim_paresse_et_locale(self):
        """Chaque appel git est journalise : CLEAN (non git) et W6 (git, sans
        candidat) -> 0 appel ; NGborne -> 0 appel de GARDE ; K -> au moins un ;
        chaque appel voit LC_ALL=C et LANGUAGE vide malgre une locale francaise."""
        shim = self._racine("shim")
        journal = os.path.join(self.base, "journal-git")
        vrai_git = shutil.which("git")
        with open(os.path.join(shim, "git"), "w", encoding="utf-8") as fh:
            fh.write('#!/bin/sh\nprintf "%s|%s|%s\\n" "${LC_ALL-}" "${LANGUAGE-}" "$*" >> "$JOURNAL_SHIM"\n'
                     f'exec "{vrai_git}" "$@"\n')
        os.chmod(os.path.join(shim, "git"), 0o755)
        clean = self._racine("CLEAN")
        self.ch.planter(os.path.join(clean, ".claude", "a"))
        w6 = self._racine("W6")
        self.ch.depot(w6)
        self.ch.planter(os.path.join(w6, ".claude", "w6"))
        self.ch.commit(w6, "w6")
        ngb = self._racine("NGborne-shim")
        self.ch.planter(os.path.join(ngb, ".claude", "emb"))
        os.makedirs(os.path.join(ngb, ".claude", "emb", ".git"))
        cas = [("CLEAN", clean, "tous", 0), ("W6", w6, "tous", 0), ("K", self.K, "garde", None)]
        if self._hors_depot(ngb):
            cas.append(("NGborne", ngb, "garde", 0))
        env = {"PATH": shim + os.pathsep + os.environ.get("PATH", ""), "JOURNAL_SHIM": journal,
               "LC_ALL": "fr_FR.UTF-8", "LANGUAGE": "fr"}
        mesures = {}
        with mock.patch.dict(os.environ, env):
            for nom, racine, quoi, _n in cas:
                open(journal, "w", encoding="utf-8").close()
                list(_python_sources(racine))
                with open(journal, encoding="utf-8") as fh:
                    lignes = [l for l in fh.read().splitlines() if l]
                mesures[nom] = (len(lignes), sum("ls-files -s --" in l for l in lignes),
                                [l for l in lignes if not l.startswith("C||")])
        for nom, racine, quoi, attendu in cas:
            tous, garde, hors_c = mesures[nom]
            self.assertEqual([], hors_c, f"{nom} : appel(s) git hors locale C")
            n = tous if quoi == "tous" else garde
            if attendu is None:
                self.assertGreaterEqual(n, 1, f"{nom} : aucun appel de garde, le temoin ne mesure rien")
            else:
                self.assertEqual(attendu, n, f"{nom} : {n} appel(s) ({quoi}) — attendu {attendu}")

    def test_git_absent_OSError_remonte(self):
        vide = self._racine("sans-git")
        with mock.patch.dict(os.environ, {"PATH": vide}):
            with self.assertRaises(OSError):
                list(_python_sources(self.K))

    def _faux_git(self, rc_enfant, stderr_enfant):
        vrai = subprocess.run

        def faux(argv, *a, **kw):
            if "ls-files" in argv:
                return subprocess.CompletedProcess(argv, rc_enfant, "", stderr_enfant)
            if "rev-parse" in argv:
                return subprocess.CompletedProcess(argv, 0, "true\n", "")
            return vrai(argv, *a, **kw)
        return faux

    def test_un_enfant_hors_depot_sous_une_racine_git_LEVE(self):
        """Decouverte BLOQUEE (plafond, point de montage) : le message « hors
        depot » sur un ENFANT d une racine git n est jamais lu comme « non
        enregistre »."""
        faux = self._faux_git(128, "fatal: not a git repository (or any of the parent directories): .git\n")
        with mock.patch.object(subprocess, "run", faux):
            with self.assertRaises(RuntimeError) as leve:
                list(_python_sources(self.K))
        self.assertIn("BLOQUEE", str(leve.exception))

    def test_un_autre_rc128_sur_un_enfant_LEVE(self):
        faux = self._faux_git(128, "fatal: detected dubious ownership in repository at '/x'\n")
        with mock.patch.object(subprocess, "run", faux):
            with self.assertRaises(RuntimeError) as leve:
                list(_python_sources(self.K))
        self.assertIn("dubious ownership", str(leve.exception))

    @unittest.skipIf(_WINDOWS, "SKIP : script `core.fsmonitor` en sh non mesure sous Windows")
    def test_la_config_du_depot_interroge_n_est_jamais_executee(self):
        """S-00003664 : un depot interroge peut porter `core.fsmonitor=<cmd>` (clone
        embarque issu d une archive non fiable), que git execute a chaque
        `ls-files -s` (mesure git 2.55). CONTROLE POSITIF : le MEME argv sans les
        deux `-c`, sous le MEME environnement, fait naitre le marqueur — sinon le
        zero qui suit ne prouve rien. La config est posee APRES la construction."""
        R = self._racine("FSM")
        self.ch.depot(R)
        self.ch.ecrire(os.path.join(R, "README"), "r\n")
        self.ch.commit(R, "r")
        cand = os.path.join(R, ".claude", "fs")
        self.ch.git("clone", "-q", self.s1, cand)
        marque, script = os.path.join(self.base, "fsm.marque"), os.path.join(self.base, "fsm.sh")
        self.ch.ecrire(script, f'#!/bin/sh\necho "fsmonitor $*" >> "{marque}"\nexit 1\n')
        os.chmod(script, 0o755)
        self.ch.git("config", "core.fsmonitor", script, cwd=R)
        subprocess.run(["git", "-C", os.path.dirname(cand), "ls-files", "-s", "--",
                        ":(literal)" + os.path.basename(cand)],
                       capture_output=True, text=True, env=_garde_env(), timeout=60)
        self.assertTrue(os.path.exists(marque),
                        "CONTROLE POSITIF : un ls-files -s NU n execute pas core.fsmonitor — le temoin ne mesure rien")
        os.remove(marque)
        self.assertTrue(_elague(cand, R, {}), "PRECONDITION : le clone non enregistre doit etre elague")
        self.assertFalse(os.path.exists(marque), "la garde a EXECUTE le core.fsmonitor du depot interroge")

    def test_git_sans_reponse_LEVE_et_chaque_appel_porte_60_s(self):
        """S-00003664 : les DEUX appels git de la garde (mode, puis index) portent
        `timeout=60` ; passe ce delai, `subprocess.TimeoutExpired` REMONTE — un
        banc qui ne peut pas juger ne conclut pas."""
        delais = []

        def faux(argv, *a, **kw):
            delais.append(("ls-files" if "ls-files" in argv else "rev-parse", kw.get("timeout")))
            if "ls-files" in argv:
                raise subprocess.TimeoutExpired(argv, kw.get("timeout") or 0)
            return subprocess.CompletedProcess(argv, 0, "true\n", "")
        with mock.patch.object(subprocess, "run", faux):
            with self.assertRaises(subprocess.TimeoutExpired):
                list(_python_sources(self.K))
        self.assertEqual([("rev-parse", 60), ("ls-files", 60)], delais)

    def test_environnement_git_hostile(self):
        """Trois variables qui redirigent git (pathspec, index, depot) : la table
        reste IDENTIQUE — la garde ne les herite pas."""
        autre = self._racine("autre")
        self.ch.depot(autre)
        self.ch.ecrire(os.path.join(autre, "q"), "q\n")
        self.ch.commit(autre, "o")
        ecarts = {}
        for var, val in (("GIT_LITERAL_PATHSPECS", "1"),
                         ("GIT_INDEX_FILE", os.path.join(autre, ".git", "index")),
                         ("GIT_DIR", os.path.join(autre, ".git"))):
            with mock.patch.dict(os.environ, {var: val}):
                e = _ecarts(_verdicts(self.K, self.bras), self.bras)
            if e:
                ecarts[var] = e
        self.assertEqual({}, ecarts)

    def test_plafond_de_decouverte(self):
        """GIT_CEILING_DIRECTORIES=<racine> : la variable qu une purge par LISTE
        laissait passer, et sous laquelle un enfant ENREGISTRE repond « hors
        depot ». Purge par prefixe : table IDENTIQUE, rien ne leve. Controle : un
        plafond AU-DESSUS de la racine ne change rien non plus."""
        ecarts = {}
        for plafond in (self.K, os.path.dirname(self.K)):
            with mock.patch.dict(os.environ, {"GIT_CEILING_DIRECTORIES": plafond}):
                e = _ecarts(_verdicts(self.K, self.bras), self.bras)
            if e:
                ecarts[plafond] = e
        self.assertEqual({}, ecarts)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
