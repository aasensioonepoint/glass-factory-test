#!/usr/bin/env python3
"""Banc de `setup_projet.py` — la commande setup d'un projet adoptant.

T-01M534ZNXKKP91XZRV5M5WBAYX (plan r3, annexe § 4). UN arbre adoptant jetable,
bâti en `setUpClass` comme `test_adopting_gate` : `git ls-files` du kit filtré
par `sync_template.parse_exclude` + `match_rule(p) is None`, plus le canal SEED
(`seed_targets` : les 5 portes semées), copié depuis l'ARBRE DE TRAVAIL (une
mutation non commitée atteint donc la fixture), plus les fichiers `own:` lus
sur la template livrée (`.agents/protected-paths.local` : sans lui, l'index
couvrait le code du kit — constat de l'exec-critic). Puis `git init`,
environnement isolé (HOME, CADRE_STATE_DIR, XDG_*, AGENTS_EVENTS_DIR,
GIT_CONFIG_GLOBAL, PYTHONDONTWRITEBYTECODE sauf aux dry-runs) et un
`sitecustomize` qui REFUSE le réseau.

Les passages du setup sont joués UNE fois, en séquence, dans `setUpClass` ;
chaque test lit le passage qui le concerne :
  0. `--dry-run` sur l'arbre VIERGE : rien à publier, aucune spec (dry_run_vierge) ;
  1. amorce : `tasks.py new` + `specs.py add` + une spec suivie, une spec dans
     un sous-répertoire de `specs/`, un module de l'adoptant (`app/`) ;
  2. marqueur du kit posé DANS LA FIXTURE -> refus rc 2 (kit_refuse), puis les
     trois autres refus (refus_avant_toute_jambe) ;
  3. `--dry-run` avec `user.name` vide -> arrêt (dry_run_user_name_vide) ;
  4. `user.name` vide -> identité dégradée, rc 1, arrêt (user_name_vide) ; puis
     `--dry-run` sur l'arbre amorcé (dry_run_muet) ;
  5. premier setup (neuf_cree, consommateurs_verts, absente) ;
  6. rejeu (rejeu_deja_la), puis `--dry-run` sur l'arbre installé (dry_run_installe) ;
  7. ancienne base synthétique en WAL, 3 `file_path` (ancienne_base_lavande) ;
  8. la même avec un `-wal` non vide à côté (ancienne_base_wal) ;
  9. base V3 du poste en lecture seule, 1er fichier modifié (arret_au_premier_rc_345) ;
 10. `--commit` sous `.git/BISECT_LOG` (jeton busy:), puis réel (commit_exige).

Mutations et le témoin qui les rougit (toutes MESURÉES) : M1 étape 3 retirée ->
consommateurs_verts (symbols.py REFUSED) · M2 `--ensure-stores` remplacé par un
2e init -> rejeu_deja_la · M3 « créé » sans `build_index` -> consommateurs_verts
(symbole de l'adoptant introuvable), neuf_cree, rejeu_deja_la · M4 `urlopen` ->
hors_ligne et le témoin AST · M5 marqueur ignoré -> kit_refuse · M6 `generate`
retiré -> consommateurs_verts (SPECS_GRAPH.json absent sur fixture AMORCÉE) ·
M7 `replay-sync` : mesuré sans effet sur un clone (total_tasks reconstruit
depuis runs/), la jambe est SORTIE · M8 `--dry-run` ignoré à l'étape 4 ->
dry_run_muet · M9 union des chemins anciens retirée -> ancienne_base_lavande ·
M10 ouverture `mode=ro` sans `immutable` -> ancienne_base_lavande (annexes
apparus) · M11 filtre `git ls-files` retiré -> ancienne_base_lavande · M12
`break` du rc 3/4/5 retiré -> arret_au_premier_rc_345 · M13 `--exiger` retiré
-> commit_exige · D1 index.db toujours « à créer » au dry-run, D2 specs V3
toujours « à créer » -> dry_run_installe · D3 « rien à publier » ignoré au
dry-run -> dry_run_vierge · D4 `user.name` non sondé au dry-run ->
dry_run_user_name_vide · D5 bytecode non coupé au dry-run -> dry_run_vierge
(`__pycache__/` apparu) · D6 bilan de l'ancienne base non calculé au dry-run ->
dry_run_ancienne_base · C16 sous-répertoires de `specs/` non comptés -> neuf_cree ·
B1 appel de `_bilan` retiré -> bilan_verifie · B3 `bilan: contrat non écrit` (stderr)
non relayé ou jugé `déjà là` -> bilan_verifie_par_branche · B2 le setup réécrit un autre fichier
que le contrat du bilan (`setup-bilan.json`, SEUL exclu du rejeu, exclusion non
vide épinglée) -> rejeu_deja_la (T-01M54GEA4BNFC7QDJVK6P53Y4B).

BORNES : le filet réseau est un `sitecustomize` ; un enfant lancé en `-I` (ou
`-S`) y échappe, d'où le témoin AST des imports et des producteurs. Hors du kit
(marqueur `.agents/IS_THE_KIT` absent), les classes qui bâtissent la fixture
SAUTENT, par décorateur : chez l'adoptant `ls-files` ne lit pas l'arbre du kit,
et `test_adopting_gate.py` ne voyage pas (`sync_template.py`, lui, voyage —
mesuré, contre la prémisse de C13). `lavande_reelle` ne tourne que sous
`CADRE_SETUP_LAVANDE` (une COPIE, jamais un adoptant réel) ; sinon saut annoncé.
"""

from __future__ import annotations

import ast
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SETUP = Path(__file__).resolve().parent / "setup_projet.py"
GIT = shutil.which("git")
#: Marqueurs d'agent retirés de l'env des bancs à terminal (recopie de
#: `setup_projet._MARQUEURS_AGENT`) : un banc lancé par un agent pose la question quand même.
_MARQUEURS_AGENT = ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "AGENTS_HOOK_HOST",
                    "COPILOT_AGENT_SESSION_ID", "COPILOT_CLI")
# adopting-tree: le marqueur du kit ne voyage pas ; son ABSENCE fait SAUTER les
# classes qui bâtissent la fixture (sync_template.py, lui, voyage : mesuré).
DANS_LE_KIT = (ROOT / ".agents" / "IS_THE_KIT").is_file()

_LIGNE = re.compile(r"^setup: (?P<jambe>.+?) : (?P<etat>créé|déjà là|sans objet|dégradé|à créer)"
                    r"(?: — (?P<detail>.*))?$")

#: Un symbole que SEUL le code de l'adoptant porte : l'index d'un kit VENDU
#: (`.agents/protected-paths.local`) ne couvre pas le code du kit.
_SYMBOLE_ADOPTANT = "total_des_commandes_de_l_adoptant"

#: Les 5 portes que le canal SEED pose chez l'adoptant (graines du kit).
_PORTES = ("BINOME_REQUIRED", "CHRONO_REQUIRED", "CONFIG_QUALITE_PROTEGE", "PLAN_CHAIN_REQUIRED",
           "PLAN_CIBLE_REQUIRED")

#: Le contrat du bilan vérifié : le SEUL fichier qu'un rejeu du setup réécrit.
_CONTRAT_BILAN = Path(".agents") / "state" / "local" / "setup-bilan.json"
_LIGNE_BILAN = re.compile(r"^bilan: (?P<jambe>\S+) : (?:OK|KO|SANS OBJET) — ")

_SITECUSTOMIZE = '''\
import os, socket
_JOURNAL = os.environ.get("SETUP_BANC_RESEAU")
if _JOURNAL:
    with open(os.environ["SETUP_BANC_ACTIF"], "a", encoding="utf-8") as _f:
        _f.write(str(os.getpid()) + "\\n")
    def _refus(*args, **kwargs):
        with open(_JOURNAL, "a", encoding="utf-8") as f:
            f.write(repr(args[1:3]) + "\\n")
        raise OSError("reseau interdit par le banc setup")
    socket.socket.connect = _refus
    socket.socket.connect_ex = _refus
    socket.getaddrinfo = _refus
    socket.create_connection = _refus
'''

_SONDE_SNAPSHOT = r'''
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]) / ".agents" / "bin"))
import dashboard
s = dashboard.build_snapshot(Path(sys.argv[1]))
out = {}
for k, v in s.items():
    if isinstance(v, dict) and "status" in v:
        out[k] = v["status"]
for k, v in s.get("views", {}).items():
    if isinstance(v, dict) and "status" in v:
        out["views." + k] = v["status"]
print(json.dumps(out))
'''


def _lignes(sortie: str) -> dict[str, tuple[str, str]]:
    vus: dict[str, tuple[str, str]] = {}
    for ligne in sortie.splitlines():
        m = _LIGNE.match(ligne)
        if m:
            vus[m["jambe"]] = (m["etat"], m["detail"] or "")
    return vus


def _empreintes(*racines: Path) -> dict[str, str]:
    """sha256 de chaque fichier sous `racines`, `.git/` exclu."""
    vus: dict[str, str] = {}
    for racine in racines:
        if not racine.exists():
            continue
        for p in sorted(racine.rglob("*")):
            if ".git" in p.relative_to(racine).parts or not p.is_file():
                continue
            vus[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    return vus


def _ref_template(st) -> str | None:
    """La template livrée : branche locale PUIS suivi distant (le clone de la
    porte n'a que le second), comme `test_ignores_livres._ref_template`."""
    for ref in (st.TEMPLATE_REF, f"origin/{st.TEMPLATE_REF}"):
        if subprocess.run([GIT, "-C", str(ROOT), "rev-parse", "--verify", "-q",
                           f"{ref}^{{commit}}"], capture_output=True).returncode == 0:
            return ref
    return None


def _poser_own(dest: Path, st, regles) -> int:
    """Les fichiers `own:` — ils n'existent QUE sur la template, qui les livre à
    l'adoptant (dont `.agents/protected-paths.local`, le marqueur d'un kit
    VENDU que lit `build_index.py`). Lus sur la template, posés s'ils sont
    absents (chez l'adoptant ils sont à lui) ; sans template, saut ANNONCÉ."""
    ref = _ref_template(st)
    if ref is None:
        raise unittest.SkipTest(f"SAUT ANNONCÉ — ni {st.TEMPLATE_REF} ni origin/{st.TEMPLATE_REF} "
                                "dans ce clone : les fichiers own: de l'adoptant sont introuvables")
    n = 0
    for regle in regles:
        if regle.polarity != "own":
            continue
        listes = subprocess.run([GIT, "-C", str(ROOT), "ls-tree", "-r", "-z", "--name-only", ref,
                                 "--", regle.prefix], capture_output=True, text=True, check=True)
        for rel in (p for p in listes.stdout.split("\0") if p):
            if (dest / rel).exists():
                continue
            blob = subprocess.run([GIT, "-C", str(ROOT), "show", f"{ref}:{rel}"],
                                  capture_output=True, check=True).stdout
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            (dest / rel).write_bytes(blob)
            n += 1
    return n


def _batir_arbre(dest: Path) -> int:
    """L'arbre TAKE + SEED + OWN, depuis l'arbre de travail du kit (prédicats
    APPELÉS) ; les `own:` viennent de la template livrée (`_poser_own`)."""
    sys.path.insert(0, str(SETUP.parent))
    import sync_template as st  # noqa: PLC0415 — import du kit, banc seul

    regles = st.parse_exclude((ROOT / ".template-exclude").read_text(encoding="utf-8"))
    out = subprocess.run([GIT, "-C", str(ROOT), "ls-files", "-z"], capture_output=True,
                         text=True, check=True)
    suivis = [p for p in out.stdout.split("\0") if p]
    n = 0
    for rel in suivis:
        if st.match_rule(rel, regles) is not None or not (ROOT / rel).is_file():
            continue
        (dest / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dest / rel)
        n += 1
    for cible, source in st.seed_targets(suivis).items():
        (dest / cible).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / source, dest / cible)
        n += 1
    return n + _poser_own(dest, st, regles)


def _env_isole(tmp: Path) -> dict[str, str]:
    """HOME, état machine, XDG, spool d'événements et config git sous `tmp` ;
    `sitecustomize` réseau en tête de PYTHONPATH ; aucun bytecode écrit."""
    site = tmp / "site"
    for d in (tmp / "etat", site, tmp / "home"):
        d.mkdir(exist_ok=True)
    (site / "sitecustomize.py").write_text(_SITECUSTOMIZE, encoding="utf-8")
    (tmp / "gitconfig").write_text("", encoding="utf-8")
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("CADRE_", "XDG_", "GIT_", "OTEL_"))
           and k not in ("PYTHONPATH", "CLAUDE_PROJECT_DIR", "AGENTS_EVENTS_DIR")}
    env.update({
        "HOME": str(tmp / "home"), "CADRE_STATE_DIR": str(tmp / "etat"),
        "XDG_STATE_HOME": str(tmp / "xdg" / "state"),
        "XDG_CONFIG_HOME": str(tmp / "xdg" / "config"),
        "XDG_CACHE_HOME": str(tmp / "xdg" / "cache"),
        "AGENTS_EVENTS_DIR": str(tmp / "events"),
        "GIT_CONFIG_GLOBAL": str(tmp / "gitconfig"), "GIT_CONFIG_NOSYSTEM": "1",
        "PYTHONPATH": str(site), "PYTHONDONTWRITEBYTECODE": "1",
        "SETUP_BANC_RESEAU": str(tmp / "reseau.log"), "SETUP_BANC_ACTIF": str(tmp / "actifs.log"),
        # La jambe version du bilan : un dépôt LOCAL absent, jamais l'URL de distribution —
        # aucun `git ls-remote` réseau, même le jour où le CHANGELOG du kit porte une version.
        "BILAN_KIT_REMOTE": str(tmp / "kit-distant-absent"),
    })
    return env


def _ancienne_base(chemin: Path, lignes) -> None:
    """Une ancienne base V3 (clé (req_id, version)), en WAL, fermée proprement."""
    conn = sqlite3.connect(str(chemin))
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE spec_requirements (req_id TEXT NOT NULL, version "
                     "INTEGER NOT NULL DEFAULT 1, file_path TEXT NOT NULL, section_title "
                     "TEXT NOT NULL, content_markdown TEXT NOT NULL, tags_json TEXT NOT "
                     "NULL, PRIMARY KEY (req_id, version))")
        conn.executemany("INSERT INTO spec_requirements VALUES (?, ?, ?, ?, ?, '[]')", lignes)
        conn.commit()
    finally:
        conn.close()


@unittest.skipIf(not DANS_LE_KIT or GIT is None,
                 "hors du kit (marqueur IS_THE_KIT absent) : l'arbre adoptant ne "
                 "peut pas être bâti depuis l'arbre du kit (ou git absent)")
class SetupSurArbreAdoptantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = Path(tempfile.mkdtemp(prefix="setup-projet-")).resolve()
        if ROOT == cls._tmp or ROOT in cls._tmp.parents:
            raise AssertionError(f"fixture {cls._tmp} SOUS le kit {ROOT}")
        cls.arbre = cls._tmp / "adoptant"
        cls.etat = cls._tmp / "etat"
        cls.arbre.mkdir()
        cls.env = _env_isole(cls._tmp)
        cls.journal_reseau = Path(cls.env["SETUP_BANC_RESEAU"])
        cls.actifs = Path(cls.env["SETUP_BANC_ACTIF"])
        cls.copies = _batir_arbre(cls.arbre)
        cls._git("init", "-q")
        cls._git("add", "-A")
        cls._commit("adoption")
        # 0. dry-run sur l'arbre VIERGE (user.name par l'environnement, rien en config) :
        #    rien à publier, aucune spec -> « sans objet », jamais « à créer »
        cls.dry_vierge, cls.dry_vierge_diff = cls._a_blanc(
            GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="user.name", GIT_CONFIG_VALUE_0="Vierge")
        # 1. amorce — une tâche, une entrée de journal, une spec suivie
        cls._lancer([sys.executable, ".agents/bin/tasks.py", "--root", str(cls.arbre), "new",
                     "amorce du banc setup", "--pas-un-defaut", "amorce du banc"])
        tid = json.loads(cls._lancer([sys.executable, ".agents/bin/tasks.py", "--root",
                                      str(cls.arbre), "list", "--json"])[1] or "[]")
        cls.tid = tid[0]["id"] if isinstance(tid, list) and tid else None
        if cls.tid:
            cls._lancer([sys.executable, ".agents/bin/specs.py", "--root", str(cls.arbre), "add",
                         "--task", cls.tid, "--kind", "decision", "amorce du banc"])
        spec = cls.arbre / "docs" / "specs" / "exemple.md"
        spec.parent.mkdir(parents=True, exist_ok=True)
        spec.write_text("# Exemple\n\n## Exigence un\n\nA.\n\n## Exigence deux\n\nB.\n",
                        encoding="utf-8")
        profonde = cls.arbre / "specs" / "module" / "profonde.md"
        profonde.parent.mkdir(parents=True)
        profonde.write_text("# Profonde\n\n## Rangée plus bas\n\nC.\n", encoding="utf-8")
        code = cls.arbre / "app" / "commandes.py"
        code.parent.mkdir()
        code.write_text(f"def {_SYMBOLE_ADOPTANT}(lignes):\n    return sum(lignes)\n",
                        encoding="utf-8")
        # Un nom qui commence par `-` : sans `--`, sync-spec le lirait comme une option.
        (spec.parent / "-tiret.md").write_text("# Tiret\n\n## Option\n\nD.\n", encoding="utf-8")
        cls._git("add", "docs/specs/exemple.md", "docs/specs/-tiret.md",
                 "specs/module/profonde.md", "app/commandes.py")
        cls._commit("spec et code de l'adoptant")
        # 2. kit_refuse — le marqueur posé DANS LA FIXTURE, jamais à la racine réelle
        marqueur = cls.arbre / ".agents" / "IS_THE_KIT"
        marqueur.write_text("kit\n", encoding="utf-8")
        try:
            cls.kit = cls._setup()
        finally:
            marqueur.unlink()
        # 2 bis. les trois autres refus avant toute jambe
        setup = str(cls.arbre / ".agents" / "bin" / "setup_projet.py")
        cls.refus = {
            "sous-répertoire": cls._lancer([sys.executable, setup, "--root",
                                            str(cls.arbre / "docs")]),
            "dépôt git": cls._lancer([sys.executable, setup, "--root", str(cls.etat)]),
            "CADRE_PROJECT_ROOT": cls._lancer([sys.executable, setup, "--root", str(cls.arbre)],
                                              env=dict(cls.env, CADRE_PROJECT_ROOT=str(cls.etat))),
        }
        # 3. dry-run, user.name vide : le passage réel s'arrêterait à l'identité
        cls.dry_sans_nom = cls._setup("--dry-run")
        # 4. user.name vide
        cls.sans_nom = cls._setup()
        cls.identite_apres_sans_nom = (cls.arbre / ".agents" / "state" / "project.json").exists()
        cls._git("config", "user.name", "Adoptant")
        cls._git("config", "user.email", "adoptant@example.invalid")
        # 4 bis. dry-run sur l'arbre amorcé, SANS PYTHONDONTWRITEBYTECODE hérité
        cls.dry, cls.dry_diff = cls._a_blanc()
        # 5. premier setup, puis les consommateurs
        cls.neuf = cls._setup()
        cls.symbols = cls._symbole(_SYMBOLE_ADOPTANT)
        cls.symbols_kit = cls._symbole("build_snapshot")
        cls.snapshot = cls._lancer([sys.executable, "-c", _SONDE_SNAPSHOT, str(cls.arbre)])
        cls.graphe = (cls.arbre / ".agents" / "state" / "index" / "SPECS_GRAPH.json").exists()
        cls.bilan_neuf = cls._contrat_bilan()
        # 6. rejeu — le bilan vérifié (T-01M54GEA4BNFC7QDJVK6P53Y4B) réécrit EXACTEMENT
        #    son contrat ; toute autre écriture reste dans `rejeu_diff`
        avant = _empreintes(cls.arbre)
        cls.rejeu = cls._setup()
        diff = sorted(set(avant.items()) ^ set(_empreintes(cls.arbre).items()))
        contrat = str(cls.arbre / _CONTRAT_BILAN)
        cls.rejeu_diff = [e for e in diff if e[0] != contrat]
        cls.rejeu_diff_bilan = [e for e in diff if e[0] == contrat]
        cls.bilan_rejeu = cls._contrat_bilan()
        # 6 bis. dry-run sur l'arbre INSTALLÉ : rien « à créer »
        cls.dry_installe, cls.dry_installe_diff = cls._a_blanc()
        # 7. ancienne base synthétique : 1 présente suivie sous specs/ (sous-répertoire :
        #    atteinte par l'union seule, M9), 1 absente en `\`, 1 sous specs/ hors ls-files
        #    (M11), et 3 REFUSÉES (avis sécurité LOW 1) : un .md suivi hors de specs/,
        #    un code suivi, un lien symbolique suivi `specs/lien.md` -> code
        legacy = cls.arbre / "specs" / "legacy" / "ancienne.md"
        legacy.parent.mkdir(parents=True)
        legacy.write_text("# Ancienne\n\n## Section ancienne\n\nTexte.\n", encoding="utf-8")
        hors_specs = cls.arbre / "docs" / "legacy" / "hors_specs.md"
        hors_specs.parent.mkdir(parents=True)
        hors_specs.write_text("# Hors specs\n\n## Ailleurs\n\nSuivi.\n", encoding="utf-8")
        (cls.arbre / "specs" / "lien.md").symlink_to(Path("..") / "app" / "commandes.py")
        cls._git("add", "specs/legacy/ancienne.md", "docs/legacy/hors_specs.md", "specs/lien.md")
        cls._commit("ancienne spec, un md hors specs, un lien")
        hors = cls.arbre / "specs" / "notes" / "hors.md"
        hors.parent.mkdir()
        hors.write_text("# Hors\n\n## Hors depot\n\nNon suivi.\n", encoding="utf-8")
        cls.base = cls.arbre / ".agents" / "state" / "v3_event_store.db"
        _ancienne_base(cls.base, [
            ("REQ-ANCIENNE", 1, "specs/legacy/ancienne.md", "Ancienne", "Texte v1."),
            ("REQ-ANCIENNE", 2, "specs/legacy/ancienne.md", "Ancienne", "Texte."),
            ("REQ-DISPARU", 1, "specs\\disparu.md", "Disparu", "Rien."),
            ("REQ-HORS", 1, "specs/notes/hors.md", "Hors", "Non suivi."),
            ("REQ-AILLEURS", 1, "docs/legacy/hors_specs.md", "Ailleurs", "Suivi."),
            ("REQ-CODE", 1, "app/commandes.py", "Code", "def"),
            ("REQ-LIEN", 1, "specs/lien.md", "Lien", "def"),
        ])
        cls.base_avant = (hashlib.sha256(cls.base.read_bytes()).hexdigest(),
                          sorted(p.name for p in cls.base.parent.iterdir()
                                 if p.name.startswith(cls.base.name)))
        cls.ancienne = cls._setup()
        cls.base_apres = (hashlib.sha256(cls.base.read_bytes()).hexdigest(),
                          sorted(p.name for p in cls.base.parent.iterdir()
                                 if p.name.startswith(cls.base.name)))
        cls.chemins_du_poste = cls._chemins_du_poste()
        # 7 bis. dry-run avec l'ancienne base déjà rejouée : même verdict que le réel
        cls.dry_ancienne, cls.dry_ancienne_diff = cls._a_blanc()
        # 8. un -wal non vide à côté de l'ancienne base
        wal = cls.base.with_name(cls.base.name + "-wal")
        wal.write_bytes(b"\0" * 64)
        try:
            cls.wal = cls._setup()
        finally:
            wal.unlink()
        # 9. M12 — base V3 du poste en lecture seule ET le 1er fichier trié modifié
        #    (sans écriture due, sync-spec ne lève pas : mesuré) -> rc 4, ARRÊT
        (base_v3,) = cls.etat.rglob("v3_event_store.db")
        premier = cls.arbre / "docs" / "specs" / "exemple.md"  # 1er des 2 candidats triés
        texte = premier.read_text(encoding="utf-8")
        premier.write_text(texte + "\n## Section ajoutée\n\nNeuve.\n", encoding="utf-8")
        base_v3.chmod(0o444)
        try:
            cls.lecture_seule = cls._setup()
        finally:
            base_v3.chmod(0o600)
            premier.write_text(texte, encoding="utf-8")
        # 10. M13 — --commit : une opération git en cours (jeton busy:) puis le commit
        bisect = cls.arbre / ".git" / "BISECT_LOG"
        bisect.write_text("# banc setup\n", encoding="utf-8")
        try:
            cls.commit_occupe = cls._setup("--commit")
        finally:
            bisect.unlink()
        cls.commits_avant = cls._compter_commits()
        cls.commit = cls._setup("--commit")
        cls.commits_apres = cls._compter_commits()
        cls.board_suivi = subprocess.run([GIT, "-C", str(cls.arbre), "ls-files", "--",
                                          ".agents/state/board"], env=cls.env, capture_output=True,
                                         text=True, check=True).stdout.strip()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmp, ignore_errors=True)

    # -- outils ---------------------------------------------------------------

    @classmethod
    def _lancer(cls, argv, *, cwd=None, env=None) -> tuple[int, str, str]:
        p = subprocess.run(argv, cwd=str(cwd or cls.arbre), env=env or cls.env, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=900,
                           stdin=subprocess.DEVNULL, check=False)
        return p.returncode, p.stdout, p.stderr

    @classmethod
    def _git(cls, *args):
        subprocess.run([GIT, "-C", str(cls.arbre), *args], env=cls.env, check=True,
                       capture_output=True, text=True)

    @classmethod
    def _commit(cls, message):
        cls._git("-c", "user.name=Banc", "-c", "user.email=banc@example.invalid",
                 "-c", "commit.gpgsign=false", "commit", "-qm", message)

    @classmethod
    def _setup(cls, *args) -> tuple[int, str, str]:
        return cls._lancer([sys.executable, str(cls.arbre / ".agents" / "bin" / "setup_projet.py"),
                            "--root", str(cls.arbre), *args])

    @classmethod
    def _a_blanc(cls, **extra: str):
        """Un `--dry-run` SANS PYTHONDONTWRITEBYTECODE hérité (le setup doit le
        poser lui-même), et la différence d'empreintes de l'arbre et de l'état."""
        env = {k: v for k, v in cls.env.items() if k != "PYTHONDONTWRITEBYTECODE"}
        env.update(extra)
        avant = _empreintes(cls.arbre, cls.etat)
        passage = cls._lancer([sys.executable, str(cls.arbre / ".agents" / "bin" / "setup_projet.py"),
                               "--root", str(cls.arbre), "--dry-run"], env=env)
        apres = _empreintes(cls.arbre, cls.etat)
        return passage, sorted(set(avant.items()) ^ set(apres.items()))

    @classmethod
    def _symbole(cls, nom: str) -> tuple[int, str, str]:
        return cls._lancer([sys.executable, ".agents/bin/symbols.py", "query", "--root",
                            str(cls.arbre), "--name", nom, "--no-refresh", "--limit", "1"])

    @classmethod
    def _contrat_bilan(cls):
        try:
            return json.loads((cls.arbre / _CONTRAT_BILAN).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    @classmethod
    def _compter_commits(cls) -> int:
        return int(subprocess.run([GIT, "-C", str(cls.arbre), "rev-list", "--count", "HEAD"],
                                  env=cls.env, capture_output=True, text=True,
                                  check=True).stdout.strip())

    @classmethod
    def _chemins_du_poste(cls) -> list[str]:
        # Le paquet `cadre` EXACT de l'arbre (`.agents/vendor/cadre`, sinon `src/cadre`), par son
        # `vendor_paths` chargé par chemin : `sys.path` n'est pas touché (T-01M5BXTPQE3JZV3KZA6WD9P5XC lot Q).
        code = ("import sys, importlib.util as u;"
                "s = u.spec_from_file_location('_vp_banc', sys.argv[1] + '/.agents/bin/vendor_paths.py');"
                "vp = sys.modules[s.name] = u.module_from_spec(s); s.loader.exec_module(vp); vp.charger_paquet(sys.argv[1], 'cadre');"
                "from cadre.ledger.stores import chemins_des_stores;"
                "from cadre.ledger import store, anciennes_bases as ab;"
                "c = store.connect(chemins_des_stores(sys.argv[1]).v3_event_store, lecture_seule=True);"
                "print('\\n'.join(sorted({x.file_path for x in ab.lire_specs(c) or []})))")
        return cls._lancer([sys.executable, "-c", code, str(cls.arbre)])[1].split()

    def _etat(self, passage, jambe) -> str:
        return _lignes(passage[1]).get(jambe, ("absente", ""))[0]

    # -- témoins --------------------------------------------------------------

    def test_la_fixture_est_un_arbre_adoptant_arme(self):
        self.assertGreater(self.copies, 400, "fixture trop maigre : les témoins passeraient à vide")
        for porte in _PORTES:
            self.assertTrue((self.arbre / ".agents" / "state" / "gates" / porte).is_file(), porte)
        self.assertTrue(self.tid, "l'amorce n'a pas créé de tâche : M6 ne rougirait pas")
        self.assertTrue((self.arbre / ".agents" / "protected-paths.local").is_file(),
                        "fichier own: absent : l'index couvrirait le code du kit")

    def test_kit_refuse(self):
        rc, out, err = self.kit
        self.assertEqual(rc, 2, out + err)
        self.assertIn("IS_THE_KIT", err)
        self.assertEqual(_lignes(out), {}, "aucune jambe ne doit être jouée sous le marqueur du kit")

    def test_refus_avant_toute_jambe(self):
        for morceau, (rc, out, err) in self.refus.items():
            with self.subTest(refus=morceau):
                self.assertEqual(rc, 2, out + err)
                self.assertIn(morceau, err)
                self.assertEqual(_lignes(out), {})

    def test_dry_run_muet(self):
        rc, out, err = self.dry
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(self.dry_diff, [], "--dry-run a écrit : " + str(self.dry_diff[:6]))
        etats = {e for e, _ in _lignes(out).values()}
        self.assertNotIn("créé", etats, "--dry-run ne crée rien, il ne dit jamais « créé »")
        attendus = {"identité": "à créer", "index (fichiers)": "à créer", "index.db": "à créer",
                    "specs V3": "à créer", "graphe des specs": "à créer"}
        vus = _lignes(out)
        self.assertEqual({k: vus.get(k, ("absente",))[0] for k in attendus}, attendus, out)

    def test_dry_run_installe(self):
        """Sur l'arbre INSTALLÉ, le dry-run ne promet rien qu'un passage réel ne
        ferait : aucune jambe « à créer », et toujours rien d'écrit."""
        rc, out, err = self.dry_installe
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(self.dry_installe_diff, [], str(self.dry_installe_diff[:6]))
        vus = _lignes(out)
        self.assertEqual([k for k, (e, _) in vus.items() if e == "à créer"], [], out)
        for jambe in ("identité", "board", "index (fichiers)", "index.db", "specs V3",
                      "graphe des specs"):
            with self.subTest(jambe=jambe):
                self.assertEqual(vus.get(jambe, ("absente",))[0], "déjà là", out)

    def test_dry_run_vierge(self):
        rc, out, err = self.dry_vierge
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(self.dry_vierge_diff, [], str(self.dry_vierge_diff[:6]))
        vus = _lignes(out)
        self.assertEqual(vus.get("graphe des specs", ("absente",))[0], "sans objet", out)
        self.assertEqual(vus.get("specs V3", ("absente",))[0], "sans objet", out)
        self.assertEqual(vus.get("identité", ("absente",))[0], "à créer", out)

    def test_dry_run_user_name_vide(self):
        rc, out, err = self.dry_sans_nom
        self.assertEqual(rc, 1, out + err)
        etat, detail = _lignes(out)["identité"]
        self.assertEqual((etat, "git config user.name" in detail), ("dégradé", True), detail)
        self.assertIn("arrêt", out)
        self.assertNotIn("store index", _lignes(out))

    def test_user_name_vide(self):
        rc, out, err = self.sans_nom
        self.assertEqual(rc, 1, out + err)
        etat, detail = _lignes(out)["identité"]
        self.assertEqual(etat, "dégradé")
        self.assertIn("git config user.name", detail)
        self.assertIn("arrêt", out)
        self.assertNotIn("store index", _lignes(out), "après l'identité dégradée, rien d'autre ne joue")
        self.assertFalse(self.identite_apres_sans_nom)

    def test_neuf_cree(self):
        rc, out, err = self.neuf
        self.assertEqual(rc, 0, out + err)
        # C18 : l'amorce (tasks.py new) a déjà créé le board et la base V3 du poste.
        attendus = {"identité": "créé", "board": "déjà là", "store v3": "déjà là",
                    "store events": "créé", "store index": "créé", "index (fichiers)": "créé",
                    "index.db": "créé", "specs V3": "créé", "graphe des specs": "créé",
                    "ancienne base": "sans objet", "commit des stores": "sans objet"}
        vus = _lignes(out)
        self.assertEqual({k: vus.get(k, ("absente",))[0] for k in attendus}, attendus, out)
        self.assertIn("docs/*.md non scanné", vus["specs V3"][1])
        self.assertIn("0 non suivi", vus["specs V3"][1])
        self.assertIn("sous-répertoires de specs/ non scannés : 1", vus["specs V3"][1])

    def test_consommateurs_verts(self):
        self.assertEqual(self.symbols[0], 0, self.symbols[1] + self.symbols[2])
        self.assertRegex(self.symbols[1], rf"(?m)^SYM-\S+\s+\w+\s+app/commandes\.py:\S+\s+"
                                          rf"{_SYMBOLE_ADOPTANT}\b",
                         "index.db sans le code de l'adoptant : symbols.py ne le trouve pas")
        # La sortie recopie le motif cherché dans son en-tête : on lit le COMPTE.
        self.assertIn("-- 0 match(es)", self.symbols_kit[1],
                      "l'index couvre le code du kit : la fixture n'est pas un kit VENDU")
        self.assertTrue(self.graphe, "SPECS_GRAPH.json absent après setup sur fixture amorcée")
        sections = json.loads(self.snapshot[1] or "{}")
        # `setup` : le contrat du bilan écrit par CE passage, lu de bout en bout par le snapshot.
        ok = ("project", "board", "ledger", "specs", "index", "views.memory", "views.index",
              "views.mcp", "views.coverage", "views.security", "views.specs_graph", "setup")
        self.assertEqual({k: sections.get(k) for k in ok}, {k: "ok" for k in ok}, self.snapshot)
        degradees = {"security": "degraded", "canal_b": "degraded",
                     "views.governance": "trail_absent"}
        self.assertEqual({k: sections.get(k) for k in degradees}, degradees,
                         "écart avec l'annexe § 4 : à DIRE, jamais à ajuster en silence")
        out = self.neuf[1]
        self.assertIn("/audit", out)
        self.assertIn("--print-otel-env", out)
        self.assertIn("le dashboard ne lit aucune table V3 (F2)", out)

    def test_rejeu_deja_la(self):
        rc, out, err = self.rejeu
        self.assertEqual(rc, 0, out + err)
        vus = _lignes(out)
        for jambe in ("identité", "board", "store v3", "store events", "store index",
                      "index (fichiers)", "index.db", "specs V3", "graphe des specs"):
            with self.subTest(jambe=jambe):
                self.assertEqual(vus.get(jambe, ("absente",))[0], "déjà là", out)
        self.assertEqual(self.rejeu_diff, [], "le rejeu a modifié l'arbre : " + str(self.rejeu_diff[:6]))
        self.assertEqual(len(self.rejeu_diff_bilan), 2, "exclusion vide : le contrat du bilan "
                         "n'a pas été réécrit au rejeu " + str(self.rejeu_diff_bilan))

    def test_bilan_verifie(self):
        """Jambe de LECTURE : `déjà là` ou `dégradé`, jamais `créé` ; les lignes
        `bilan:` relayées ; le rejeu rend les mêmes jambes et le même rc, plus tard."""
        for nom, passage in (("neuf", self.neuf), ("rejeu", self.rejeu), ("dry", self.dry),
                             ("dry_installe", self.dry_installe)):
            with self.subTest(passage=nom):
                rc, out, err = passage
                etat, detail = _lignes(out).get("bilan vérifié", ("absente", out + err))
                self.assertIn(etat, ("déjà là", "dégradé"), detail)
                self.assertRegex(detail, r"OK=\d+ KO=\d+ SANS OBJET=\d+ — exit [01]")
                relayees = [m["jambe"] for m in map(_LIGNE_BILAN.match, out.splitlines()) if m]
                self.assertEqual(relayees, ["version", "outils", "scanners", "interpréteur",
                                            "hooks", "portes", "dashboard"], out)
        neuf, rejeu = self.bilan_neuf, self.bilan_rejeu
        self.assertTrue(neuf and rejeu, "contrat du bilan absent après le setup")
        # Aucun banc réseau : BILAN_KIT_REMOTE (`_env_isole`) atteint le bilan À TRAVERS le setup,
        # la jambe version rend SANS OBJET sans jamais lire l'URL de distribution.
        version = neuf["jambes"][0]
        self.assertEqual((version["jambe"], version["etat"]), ("version", "SANS OBJET"), version)
        self.assertIn("BILAN_KIT_REMOTE posé (banc)", version["detail"])
        self.assertNotIn("gitlab", version["detail"], "l'URL de distribution a été interrogée")
        self.assertEqual((neuf["jambes"], neuf["rc"]), (rejeu["jambes"], rejeu["rc"]))
        self.assertGreater(rejeu["genere_le"], neuf["genere_le"])

    def test_absente(self):
        etat, detail = _lignes(self.neuf[1])["ancienne base"]
        self.assertEqual((etat, "aucune" in detail), ("sans objet", True), detail)

    def test_ancienne_base_lavande(self):
        rc, out, err = self.ancienne
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(self.base_avant, self.base_apres,
                         "l'ancienne base a bougé ou un annexe est apparu (M10)")
        self.assertEqual(self.base_apres[1], ["v3_event_store.db"])
        self.assertIn("specs/legacy/ancienne.md", self.chemins_du_poste,
                      "le chemin de l'ancienne base n'a pas été rejoué (M9)")
        self.assertNotIn("specs/notes/hors.md", self.chemins_du_poste,
                         "un fichier hors git ls-files a été synchronisé (M11)")
        for refuse in ("docs/legacy/hors_specs.md", "app/commandes.py", "specs/lien.md"):
            with self.subTest(refuse=refuse):
                self.assertNotIn(refuse, self.chemins_du_poste,
                                 "chemin d'une base suivie admis hors de « .md sous specs/ »")
        etat, detail = _lignes(out)["ancienne base"]
        self.assertEqual(etat, "dégradé", detail)
        for morceau in ("7 lignes", "retrouvées 1", "sans source 5", "versions perdues 1",
                        "suivie : non", "jamais copiée"):
            self.assertIn(morceau, detail)
        specs = _lignes(out)["specs V3"][1]
        self.assertIn("1 non suivi", specs)
        self.assertIn("3 refusé(s)", specs)

    def test_chemin_en_tiret_et_demons_comptes(self):
        """Avis sécurité LOW 2 et 3 : une spec nommée `-tiret.md` est synchronisée ;
        la ligne démon ne porte que des COMPTES. BORNE MESURÉE : aucun candidat ne
        commence par `-` (tous sous `docs/specs/` ou `specs/`), donc retirer le `--`
        de sync-spec laisse ce témoin VERT — le `--`, défense en profondeur, est tenu
        par `test_sync_spec_ferme_les_options` (AST)."""
        self.assertIn("docs/specs/-tiret.md", self.chemins_du_poste)
        etat, detail = _lignes(self.neuf[1])["démon"]
        self.assertRegex(detail, r"^démon de cette racine : \S+ ; \d+ démon\(s\) d'autres "
                                 r"racines sur le poste$", "racines d'autres projets affichées")

    def test_dry_run_ancienne_base(self):
        """Ancienne base déjà rejouée : le dry-run rend le verdict du passage réel,
        bilan dit « avant rejeu », sans rien écrire (ni la base ni un annexe)."""
        rc, out, err = self.dry_ancienne
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(self.dry_ancienne_diff, [], str(self.dry_ancienne_diff[:6]))
        etat, detail = _lignes(out)["ancienne base"]
        self.assertEqual(etat, _lignes(self.ancienne[1])["ancienne base"][0], detail)
        for morceau in ("retrouvées 1", "sans source 5", "AVANT rejeu"):
            self.assertIn(morceau, detail)

    def test_ancienne_base_wal(self):
        rc, out, err = self.wal
        self.assertEqual(rc, 0, out + err)
        etat, detail = _lignes(out)["ancienne base"]
        self.assertEqual(etat, "dégradé")
        self.assertIn("lecture peut-être incomplète", detail)

    def test_arret_au_premier_rc_345(self):
        """M12 : base V3 du poste en lecture seule -> sync-spec rc 4 au premier
        fichier ; le setup s'ARRÊTE et compte ce qu'il n'a pas joué."""
        rc, out, err = self.lecture_seule
        self.assertEqual(rc, 1, out + err)
        etat, detail = _lignes(out)["specs V3"]
        self.assertEqual(etat, "dégradé", detail)
        self.assertIn("rc 4", detail)
        self.assertIn("ARRÊT, 1 fichier(s) non joué(s)", detail)
        self.assertEqual(detail.count(" rc "), 1, "un seul fichier joué avant l'arrêt")

    def test_commit_exige(self):
        """M13 : `--commit` relaie `commit-stores --exiger`. Opération git en
        cours -> jeton `busy:`, rc ≠ 0 grâce à --exiger -> dégradé, rc 1 ;
        sinon un commit réel, board suivi."""
        rc, out, err = self.commit_occupe
        self.assertEqual(rc, 1, out + err)
        etat, detail = _lignes(out)["commit des stores"]
        self.assertEqual((etat, "busy:BISECT_LOG" in detail), ("dégradé", True), detail)
        rc, out, err = self.commit
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(_lignes(out)["commit des stores"], ("créé", "committed"), out)
        self.assertEqual(self.commits_apres, self.commits_avant + 1)
        self.assertTrue(self.board_suivi, "le board n'a pas été committé")

    def test_hors_ligne(self):
        self.assertTrue(self.actifs.exists() and self.actifs.read_text(encoding="utf-8").strip(),
                        "le sitecustomize réseau n'a jamais été chargé : le témoin serait vide")
        journal = self.journal_reseau.read_text(encoding="utf-8") if self.journal_reseau.exists() else ""
        self.assertEqual(journal, "", "une tentative réseau a eu lieu : " + journal[:300])


class BilanVerifieUnitaireTests(unittest.TestCase):
    """La jambe `bilan vérifié` sur un `_script` bouchonné, joué partout : la
    fixture adoptante ne voit que `dégradé` (ni démon ni `core.hooksPath`), la
    branche `déjà là` est tenue ici (mutant DEJA -> CREE : rouge)."""

    RESUME_OK = "bilan: OK=5 KO=0 SANS OBJET=0 — exit 0"
    RESUME_KO = "bilan: OK=3 KO=2 SANS OBJET=0 — exit 1"

    def _jouer(self, sortie, dry_run=False):
        with mock.patch.object(sys, "path", [str(SETUP.parent), *sys.path]):
            import setup_projet  # noqa: PLC0415 — module du kit, en processus
        self.assertEqual(Path(setup_projet.__file__).resolve(), SETUP)
        appels = []

        def _script(racine, nom, *args):
            appels.append((nom, args))
            return setup_projet.Sortie(*sortie)

        rapport = setup_projet.Rapport(dry_run)
        flux = io.StringIO()
        with mock.patch.object(setup_projet, "_script", _script), \
                contextlib.redirect_stdout(flux):
            setup_projet._bilan(Path("/racine"), rapport)
        return rapport, appels, _lignes(flux.getvalue()), flux.getvalue()

    def test_bilan_verifie_par_branche(self):
        cas = {
            "sans KO": ((0, "bilan: outils : OK — x\n" + self.RESUME_OK + "\n", ""), "déjà là",
                        "OK=5 KO=0"),
            "un KO": ((1, self.RESUME_KO + "\n", ""), "dégradé", "OK=3 KO=2"),
            "plantage": ((1, "", "Traceback\nAttributeError: boum"), "dégradé",
                         "AttributeError: boum"),
            "contrat non écrit": ((0, self.RESUME_OK + "\n", "bilan: contrat non écrit (x) — "
                                   "OSError: y"), "dégradé", "contrat non écrit (x)"),
        }
        for nom, (sortie, etat, morceau) in cas.items():
            with self.subTest(cas=nom):
                rapport, appels, vus, out = self._jouer(sortie)
                self.assertEqual(vus["bilan vérifié"][0], etat, out)
                self.assertIn(morceau, vus["bilan vérifié"][1])
                self.assertEqual(rapport.rc, 0, "jambe de LECTURE : jamais le code de sortie")
                self.assertEqual(appels, [("setup_bilan.py", ("--root", "/racine"))])
                if nom == "sans KO":
                    self.assertIn("bilan: outils : OK — x", out, "lignes bilan: relayées")
                if nom == "contrat non écrit":
                    self.assertIn("\nbilan: contrat non écrit (x) — OSError: y\n", out,
                                  "la ligne stderr du bilan est relayée")
        rapport, appels, vus, out = self._jouer((0, self.RESUME_OK + "\n", ""), dry_run=True)
        self.assertEqual(appels[0][1][-1], "--sans-ecrire")
        self.assertEqual(vus["bilan vérifié"][0], "déjà là", out)


class SondesUnitaireTests(unittest.TestCase):
    """F-B (S-01M5D1R2PK) : ce que le bilan juge KO, les sondes ne le disent jamais `sans objet` —
    démon non vivant, `core.hooksPath` non posé à côté d'un `.githooks/` : `dégradé`, rc intact.
    Mutants : l'un ou l'autre rendu à SANS_OBJET -> rouge ; libellé `bilan rc=` rétabli -> rouge."""

    def _jouer(self, statut_demon: str, hooks_path: str, githooks: bool):
        with mock.patch.object(sys, "path", [str(SETUP.parent), *sys.path]):
            import setup_projet  # noqa: PLC0415 — module du kit, en processus
        self.assertEqual(Path(setup_projet.__file__).resolve(), SETUP)
        racine = Path(tempfile.mkdtemp(prefix="setup-sondes-")).resolve()
        self.addCleanup(shutil.rmtree, racine, True)
        if githooks:
            (racine / ".githooks").mkdir()

        def _script(_racine, nom, *_args):
            if nom == "dashboard_daemon.py":
                return setup_projet.Sortie(0, json.dumps({"status": statut_demon}), "")
            return setup_projet.Sortie(0, "fusion par champ : ok\n", "")

        rapport = setup_projet.Rapport(True)
        flux = io.StringIO()
        with mock.patch.object(setup_projet, "_script", _script), \
                mock.patch.object(setup_projet, "_git",
                                  lambda *_a: setup_projet.Sortie(0, hooks_path + "\n", "")), \
                contextlib.redirect_stdout(flux):
            setup_projet._sondes(racine, rapport)
            rapport.bilan()
        return rapport, _lignes(flux.getvalue()), flux.getvalue()

    def test_ko_du_bilan_jamais_sans_objet(self):
        cas = {
            "démon absent, hooks non posé": ("absent", "", True, "dégradé", "dégradé"),
            "démon vivant, hooks posé": ("alive", ".githooks", True, "déjà là", "déjà là"),
            "sans .githooks/": ("alive", "", False, "déjà là", "sans objet"),
        }
        for nom, (statut, hooks, githooks, demon, chemin) in cas.items():
            with self.subTest(cas=nom):
                rapport, vus, out = self._jouer(statut, hooks, githooks)
                self.assertEqual((vus["démon"][0], vus["core.hooksPath"][0]), (demon, chemin), out)
                self.assertEqual(rapport.rc, 0, "sondes de LECTURE : jamais le code de sortie")
                self.assertRegex(out.splitlines()[-1], r"^setup: résumé rc=0 — ",
                                 "la ligne de fin se confond avec le verdict du bilan vérifié")
                self.assertNotIn("setup: bilan rc=", out)


#: L'enfant joué sous pty : `_pilote_fusion` du setup du KIT sur une racine jetable.
_ENFANT_PILOTE = r'''
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import setup_projet as s
r = s.Rapport(sys.argv[3] == "1")
s._pilote_fusion(Path(sys.argv[2]), r)
print("RC=%d" % r.rc, flush=True)
'''
_QUESTION = "Installer le pilote de fusion dans ce clone ? [o/N]"
_CLE_DRIVER = "merge.cadre-enregistrement.driver"


@unittest.skipIf(os.name != "posix" or GIT is None or sys.version_info < (3, 11),
                 "SAUT ANNONCÉ — pty POSIX, git et python ≥ 3.11 requis pour la matrice du pilote")
class PiloteFusionTests(unittest.TestCase):
    """T-01M5F354TSM1S816112DGWNFZN (étape 3) : l'opt-in du pilote de fusion, joué sous un VRAI
    pty sur une racine mktemp (un dépôt `main` qui porte `fusion_enregistrement.py`), le vrai
    `--installer` et le vrai `--verifier`. Matrice o / Non / vide / EOF / non-TTY / --dry-run /
    CLAUDECODE / COPILOT_CLI ; témoin K : la config locale du dépôt du kit ne bouge pas. Mutants : sans
    `--installer` -> test_pilote_oui ; sans test de version -> test_pilote_python_39.
    BORNE : `_pilote_fusion` est appelée directement, pas au bout d'un `main` complet (qui exige
    l'arbre adoptant entier de `SetupSurArbreAdoptantTests`, joué, lui, sans terminal)."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = Path(tempfile.mkdtemp(prefix="setup-pilote-")).resolve()
        (cls._tmp / "home").mkdir()
        (cls._tmp / "gitconfig").write_text("", encoding="utf-8")
        cls.env = {k: v for k, v in os.environ.items()
                   if not k.startswith(("GIT_", "CADRE_")) and k not in (*_MARQUEURS_AGENT, "PYTHONPATH")}
        cls.env.update(HOME=str(cls._tmp / "home"), GIT_CONFIG_GLOBAL=str(cls._tmp / "gitconfig"),
                       GIT_CONFIG_NOSYSTEM="1", PYTHONDONTWRITEBYTECODE="1")
        cls.k_avant = cls._config_kit()
        cls.n = 0

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmp, True)

    @staticmethod
    def _config_kit() -> str:
        return subprocess.run([GIT, "-C", str(ROOT), "config", "--local", "--list"],
                              capture_output=True, text=True, check=False).stdout

    def _racine(self, *, pilote_suivi: bool = True) -> Path:
        type(self).n += 1
        racine = self._tmp / f"r{self.n}"
        (racine / ".agents" / "bin").mkdir(parents=True)
        (racine / "README").write_text("banc\n", encoding="utf-8")
        pilote = racine / ".agents" / "bin" / "fusion_enregistrement.py"
        if pilote_suivi:
            shutil.copy2(SETUP.parent / "fusion_enregistrement.py", pilote)
        for argv in (["init", "-q", "-b", "main"], ["config", "user.name", "Banc"],
                     ["config", "user.email", "banc@example.invalid"],
                     ["config", "commit.gpgsign", "false"], ["add", "-A"],
                     ["commit", "-qm", "pilote"]):
            subprocess.run([GIT, "-C", str(racine), *argv], env=self.env, check=True,
                           capture_output=True)
        if not pilote_suivi:  # copié APRÈS le commit : non suivi, l'installeur refuse
            shutil.copy2(SETUP.parent / "fusion_enregistrement.py", pilote)
        return racine

    def _git(self, racine: Path, *args: str) -> str:
        return subprocess.run([GIT, "-C", str(racine), *args], env=self.env, capture_output=True,
                              text=True, check=False).stdout.strip()

    def _jouer(self, racine: Path, saisie: bytes | None, *, tty: bool = True, dry: bool = False,
               env_plus: dict[str, str] | None = None) -> str:
        import pty  # noqa: PLC0415 — POSIX seul, sauté ailleurs
        import select  # noqa: PLC0415
        argv = [sys.executable, "-B", "-c", _ENFANT_PILOTE, str(SETUP.parent), str(racine),
                "1" if dry else "0"]
        env = {**self.env, **(env_plus or {})}
        if not tty:
            p = subprocess.run(argv, env=env, cwd=str(racine), stdin=subprocess.DEVNULL,
                               capture_output=True, text=True, timeout=300, check=False)
            return p.stdout + p.stderr
        maitre, esclave = pty.openpty()
        p = subprocess.Popen(argv, env=env, cwd=str(racine), stdin=esclave, stdout=esclave,
                             stderr=esclave, close_fds=True)
        os.close(esclave)
        sortie = b""
        try:
            while True:
                # La réponse part quand la question est AFFICHÉE, comme au clavier.
                if saisie is not None and _QUESTION.encode("utf-8") in sortie:
                    os.write(maitre, saisie)
                    saisie = None
                prets, _, _ = select.select([maitre], [], [], 300)
                if not prets:
                    p.kill()
                    break
                try:
                    bloc = os.read(maitre, 4096)
                except OSError:
                    break
                if not bloc:
                    break
                sortie += bloc
        finally:
            p.wait(timeout=60)
            os.close(maitre)
        return sortie.decode("utf-8", "replace").replace("\r\n", "\n")

    def _non_arme(self, racine: Path, out: str, *, question: bool, detail: str) -> None:
        self.assertEqual(_QUESTION in out, question, out)
        self.assertEqual(_lignes(out)["fusion par champ"][0], "sans objet", out)
        self.assertIn(detail, _lignes(out)["fusion par champ"][1], out)
        self.assertEqual(self._git(racine, "config", "--local", "--get", _CLE_DRIVER), "", out)
        self.assertIn("RC=0", out)

    def tearDown(self):
        self.assertEqual(self._config_kit(), self.k_avant,
                         "témoin K : la config locale du dépôt du kit a bougé")

    def test_pilote_oui(self):
        with mock.patch.object(sys, "path", [str(SETUP.parent), *sys.path]):
            import fusion_enregistrement as fe  # noqa: PLC0415 — module du kit, banc seul
        raison = fe.raison_sonde(fe.sonder_git(str(self._tmp)))
        if raison is not None:
            self.skipTest(f"SAUT ANNONCÉ — git sans les capacités du pilote : {raison}")
        racine = self._racine()
        hooks_avant = sorted(p.name for p in (racine / ".git" / "hooks").iterdir())
        out = self._jouer(racine, b"o\n")
        self.assertIn(_QUESTION, out)
        self.assertEqual(_lignes(out)["fusion par champ"][0], "créé", out)
        self.assertIn("installé : ", _lignes(out)["fusion par champ"][1], out)
        self.assertIn(f"fusion par champ : {_CLE_DRIVER} = ", out, "K6 : stdout de l'installeur relayé")
        self.assertNotEqual(self._git(racine, "config", "--local", "--get", _CLE_DRIVER), "", out)
        self.assertEqual(self._git(racine, "config", "--get", "core.hooksPath"), "",
                         "le setup a écrit core.hooksPath")
        self.assertEqual(sorted(p.name for p in (racine / ".git" / "hooks").iterdir()),
                         hooks_avant, "le setup a écrit sous .git/hooks")
        self.assertIn("RC=0", out)
        out2 = self._jouer(racine, None)  # B2 : le rejeu voit le pilote installé
        self.assertEqual(_lignes(out2)["fusion par champ"][0], "déjà là", out2)
        self.assertNotIn(_QUESTION, out2)
        self.assertIn("RC=0", out2)

    def test_pilote_index_non_arme_dit_degrade(self):
        """Revue de clôture T-01M54GECXD (T1) : board installé mais clé d'index retirée -> la jambe
        `fusion de l'index` est DITE dégradée (à moitié armé, puis absent), le board reste `déjà là`, rc 0.
        Mutant : bloc `index` retiré de `_pilote_fusion` -> aucune ligne `fusion de l'index`, rouge."""
        with mock.patch.object(sys, "path", [str(SETUP.parent), *sys.path]):
            import fusion_enregistrement as fe  # noqa: PLC0415 — module du kit, banc seul
        raison = fe.raison_sonde(fe.sonder_git(str(self._tmp)))
        if raison is not None:
            self.skipTest(f"SAUT ANNONCÉ — git sans les capacités du pilote : {raison}")
        racine = self._racine()
        out = self._jouer(racine, b"o\n")
        self.assertEqual(_lignes(out)["fusion par champ"][0], "créé", out)
        self.assertNotIn("setup: fusion de l'index", out.split(_QUESTION, 1)[1], "index installé : rien à dire")
        for cle, attendu in (("merge.cadre-index.driver", "index : à moitié armé"),
                             ("merge.cadre-index.name", "index : absent")):
            self._git(racine, "config", "--local", "--unset", cle)
            out = self._jouer(racine, None)
            self.assertIn(f"fusion de l'index : dégradé — {attendu}", out)
            self.assertEqual(_lignes(out)["fusion par champ"][0], "déjà là", out)
            self.assertIn("RC=0", out, "jambe de lecture : jamais le code de sortie")

    def test_pilote_installeur_refuse(self):
        """B3 : `o` puis un installeur qui REFUSE (pilote non suivi) -> dégradé dit, rc 0."""
        racine = self._racine(pilote_suivi=False)
        out = self._jouer(racine, b"o\n")
        self.assertIn(_QUESTION, out)
        self.assertEqual(_lignes(out)["fusion par champ"][0], "dégradé", out)
        self.assertIn("REFUS", out)
        self.assertEqual(self._git(racine, "config", "--local", "--get", _CLE_DRIVER), "", out)
        self.assertIn("RC=0", out, "jambe de lecture : jamais le code de sortie")

    def test_pilote_refus(self):
        for nom, saisie in (("Non", b"Non\n"), ("vide", b"\n"), ("EOF", b"\x04"),
                            ("Oui", b"Oui\n"), ("OUI", b"OUI\n"), ("blancs", b" o \n")):
            with self.subTest(cas=nom):
                racine = self._racine()
                out = self._jouer(racine, saisie)
                self._non_arme(racine, out, question=True, detail="réponse : non")
                self.assertIn("git config core.hooksPath .githooks", out,
                              "C42 : le « non » dit l'absence d'alerte et son geste")
                self.assertNotIn("T-01M5DJHCNK", out, "id du board du kit, inconnu de l'adoptant")
                self.assertIn("vérificateur rc=1", out, "le rc du vérificateur est annoncé")

    def test_pilote_sans_question(self):
        cas = {"non-TTY": dict(tty=False), "--dry-run": dict(dry=True),
               "CLAUDECODE": dict(env_plus={"CLAUDECODE": "1"}),
               "COPILOT_CLI": dict(env_plus={"COPILOT_CLI": "1"})}
        attendu = {"non-TTY": "pas un terminal", "--dry-run": "--dry-run",
                   "CLAUDECODE": "pas un terminal", "COPILOT_CLI": "(ou agent)"}
        for nom, options in cas.items():
            with self.subTest(cas=nom):
                racine = self._racine()
                out = self._jouer(racine, b"o\n", **options)
                self._non_arme(racine, out, question=False, detail=attendu[nom])

    def test_pilote_claudecode_blanc(self):
        """F2 : CLAUDECODE vide ou fait de blancs vaut ABSENT -> la question est posée."""
        for nom, valeur in (("vide", ""), ("espace", " ")):
            with self.subTest(cas=nom):
                racine = self._racine()
                out = self._jouer(racine, b"Non\n", env_plus={"CLAUDECODE": valeur})
                self._non_arme(racine, out, question=True, detail="réponse : non")


class PiloteFusionEnProcessusTests(unittest.TestCase):
    """B5 : les branches du pilote qui n'ont besoin ni de pty ni de git, hors du saut de
    `PiloteFusionTests` : python < 3.11 (mutant : sans test de version -> rouge) et le
    remède cité entre guillemets shell (B1, mutant : sans `shlex.quote` -> rouge)."""

    @staticmethod
    def _module():
        with mock.patch.object(sys, "path", [str(SETUP.parent), *sys.path]):
            import setup_projet  # noqa: PLC0415 — module du kit, en processus
        return setup_projet

    def test_remede_cite_entre_guillemets(self):
        setup_projet = self._module()
        rapport = setup_projet.Rapport(False)
        flux = io.StringIO()
        with mock.patch.object(sys, "executable", "/chemin avec espace/python3"), \
                mock.patch.object(sys, "version_info", (3, 11, 0)), \
                mock.patch.object(setup_projet, "_script",
                                  lambda *a, **k: setup_projet.Sortie(1, "absent : x", "")), \
                mock.patch.object(sys, "stdin", io.StringIO("")), \
                contextlib.redirect_stdout(flux):
            setup_projet._pilote_fusion(Path("."), rapport)
        out = flux.getvalue()
        self.assertIn("remède : '/chemin avec espace/python3' .agents/bin/fusion_enregistrement.py"
                      " --installer", out)

    def test_pilote_python_39(self):
        setup_projet = self._module()
        appels: list[tuple] = []
        rapport = setup_projet.Rapport(False)
        flux = io.StringIO()
        with mock.patch.object(sys, "version_info", (3, 9, 6)), \
                mock.patch.object(setup_projet, "_script",
                                  lambda *a, **k: appels.append(a) or setup_projet.Sortie(1, "", "x")), \
                contextlib.redirect_stdout(flux):
            setup_projet._pilote_fusion(Path("."), rapport)
        out = flux.getvalue()
        self.assertEqual(appels, [], "sous 3.9 le pilote ne s'importe pas : rien lancé")
        self.assertNotIn(_QUESTION, out)
        self.assertEqual(_lignes(out)["fusion par champ"][0], "dégradé", out)
        self.assertIn("python ≥ 3.11 absent", out)
        self.assertEqual(rapport.rc, 0, "jambe de lecture : jamais le code de sortie")

    def test_pilote_hooks_deja_actifs_ne_conseille_pas_activation(self):
        setup_projet = self._module()
        rapport = setup_projet.Rapport(False)
        flux = io.StringIO()
        with mock.patch.object(setup_projet, "_script",
                               return_value=setup_projet.Sortie(1, "absent", "")), \
                mock.patch.object(sys, "stdin", _Tty("Non\n")), \
                contextlib.redirect_stdout(flux):
            setup_projet._pilote_fusion(Path("."), rapport, setup_projet.ACTIF)
        out = flux.getvalue()
        self.assertIn("core.hooksPath → .githooks : alertes de fusion actives", out)
        self.assertNotIn("sans core.hooksPath", out)
        self.assertNotIn("git config core.hooksPath .githooks", out)


#: La question FIGÉE de l'annexe de T-01M5DJHCNK6ZX1XEG8XY0A8JR3, recopiée ici (jamais lue du
#: module) : la même chaîne que `core-scripts/setup.sh` et `setup.ps1`.
_QUESTION_HOOKS = ("Activer les hooks de ce dépôt (tous ses worktrees liés partagent ce réglage) "
                   "dans .githooks ? core.hooksPath remplace les hooks "
                   "de .git/hooks ; pre-push refuse un push sans tampon de porte vert ; commit-msg "
                   "refuse certains sujets ; Git exécute les hooks de l’arbre courant. [o/N]")
_ACTIVER = "git config core.hooksPath .githooks"


class _Tty(io.StringIO):
    """Le stdin du pilote : sa réponse, et `isatty()` choisi."""

    def __init__(self, texte: str, tty: bool = True) -> None:
        super().__init__(texte)
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


def _module_bilan():
    spec = importlib.util.spec_from_file_location("_banc_setup_bilan_hooks",
                                                  SETUP.parent / "setup_bilan.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # T-00000134 : enregistré avant exec_module
    spec.loader.exec_module(module)
    return module


@unittest.skipIf(GIT is None or os.name != "posix",
                 "SAUT ANNONCÉ — git et POSIX requis (liens, chmod) pour la jambe hooks git")
class HooksGitTests(unittest.TestCase):
    """T-01M5DJHCNK6ZX1XEG8XY0A8JR3, lot A : la jambe `hooks git` jouée en processus sur un dépôt
    jetable, git réel, config globale isolée, depuis un cwd EXTÉRIEUR au dépôt. Mutants et le
    témoin qui les rougit : `--git-path hooks` résolu contre le cwd -> test_hooks_actifs_preserves,
    test_hooks_bilan_meme_passage ; entrée vide acceptée -> test_hooks_reponses ; contrôle de
    `.githooks/` retiré -> test_githooks_absent ; vérification `--dry-run` retirée ->
    test_hooks_sans_question ; remède du bilan inconditionnel, issue non passée à `_sondes` ou
    `_SANS_ALERTE` inconditionnelle -> test_hooks_bilan_meme_passage."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="setup-hooks-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        (self.tmp / "gitconfig").write_text("", encoding="utf-8")
        (self.tmp / "ailleurs").mkdir()
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("GIT_", "CADRE_")) and k not in _MARQUEURS_AGENT}
        env.update(GIT_CONFIG_GLOBAL=str(self.tmp / "gitconfig"), GIT_CONFIG_NOSYSTEM="1",
                   PYTHONDONTWRITEBYTECODE="1")
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(self.tmp / "ailleurs")  # le cwd n'est JAMAIS le dépôt
        self.s = PiloteFusionEnProcessusTests._module()
        self.n = 0

    def _racine(self, *, githooks: bool = True, hooks: tuple[str, ...] = ()) -> Path:
        self.n += 1
        racine = self.tmp / f"r{self.n}"
        subprocess.run([GIT, "init", "-q", str(racine)], check=True, capture_output=True)
        if githooks:
            (racine / ".githooks").mkdir()
        for nom in hooks:
            (racine / ".git" / "hooks" / nom).write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            (racine / ".git" / "hooks" / nom).chmod(0o755)
        return racine

    def _git(self, racine: Path, *args: str) -> str:
        return subprocess.run([GIT, "-C", str(racine), *args], capture_output=True, text=True,
                              check=False).stdout.strip()

    def _noms(self, racine: Path) -> list[str]:
        return sorted(p.name for p in (racine / ".git" / "hooks").iterdir())

    def _jouer(self, racine: Path, saisie: str = "o\n", *, tty: bool = True, dry: bool = False,
               env_plus: dict[str, str] | None = None):
        rapport = self.s.Rapport(dry)
        flux = io.StringIO()
        with mock.patch.object(sys, "stdin", _Tty(saisie, tty)), \
                mock.patch.dict(os.environ, env_plus or {}), contextlib.redirect_stdout(flux):
            issue = self.s._hooks_git(racine, rapport)
        # Un terminal fait l'écho du retour à la ligne de la réponse ; ce faux stdin non.
        out = flux.getvalue().replace(_QUESTION_HOOKS + " ", _QUESTION_HOOKS + " \n")
        self.assertEqual(rapport.rc, 0, "jambe de LECTURE : jamais le code de sortie")
        return issue, out, _lignes(out).get("hooks git", ("absente", out))

    def test_hooks_actifs_preserves(self):
        bilan = _module_bilan()
        for nom, hooks, lien, chainer in (("pre-push et pre-commit", ("pre-push", "pre-commit"),
                                           True, True), ("pre-commit seul", ("pre-commit",),
                                                         False, False)):
            for dry in (False, True):
                with self.subTest(cas=nom, dry=dry):
                    racine = self._racine(hooks=hooks)
                    if lien:  # un lien est un hook actif
                        (racine / ".git" / "hooks" / "post-merge").symlink_to("pre-push")
                    (racine / ".git" / "hooks" / "pre-push.sample").write_text("x", encoding="utf-8")
                    avant = self._noms(racine)
                    issue, out, (etat, detail) = self._jouer(racine, dry=dry)
                    self.assertEqual((issue, etat), (self.s.HOOKS_ACTIFS, "dégradé"), out)
                    noms = sorted(set(hooks) | ({"post-merge"} if lien else set()))
                    repertoire = str(racine / ".git" / "hooks")
                    self.assertIn(f"hooks actifs dans {repertoire} ({', '.join(noms)})", detail)
                    self.assertIn(bilan.remede_hooks_actifs(noms, repertoire), detail,
                                  "le setup et le bilan disent le même remède")
                    self.assertNotIn(_QUESTION_HOOKS, out)
                    self.assertNotIn(_ACTIVER, out, "la commande contournerait le refus")
                    self.assertNotIn("cp ", out, "conseil de copie par-dessus")
                    self.assertEqual("chaîner les deux pre-push, jamais copier celui du kit "
                                     "par-dessus" in detail, chainer, detail)
                    self.assertEqual(self._git(racine, "config", "--local", "--get",
                                               "core.hooksPath"), "", out)
                    self.assertEqual(self._noms(racine), avant, "un hook a été écrit ou retiré")

    def test_hooks_reponses(self):
        for nom, saisie in (("vide", "\n"), ("EOF", ""), ("Non", "Non\n"), ("Oui", "Oui\n"),
                            ("OUI", "OUI\n"), ("blancs", " o \n"), ("ok", "ok\n"),
                            ("ouii", "ouii\n")):
            with self.subTest(cas=nom):
                racine = self._racine()
                issue, out, (etat, detail) = self._jouer(racine, saisie)
                self.assertIn(_QUESTION_HOOKS, out)
                self.assertEqual((issue, etat, detail), (self.s.NON_POSE, "sans objet",
                                 "Hooks non activés dans ce clone ; configuration inchangée."), out)
                self.assertEqual(self._git(racine, "config", "--local", "--get",
                                           "core.hooksPath"), "", out)

    def test_hooks_oui(self):
        for saisie in ("o\n", "oui\n"):
            with self.subTest(saisie=saisie):
                racine = self._racine()
                avant = self._noms(racine)
                issue, out, (etat, detail) = self._jouer(racine, saisie)
                self.assertIn(_QUESTION_HOOKS, out)
                self.assertEqual((issue, etat, detail), (self.s.ACTIF, "créé",
                                 "Hooks activés dans ce dépôt (worktrees liés compris) : core.hooksPath=.githooks."), out)
                self.assertEqual(self._git(racine, "config", "--local", "--get",
                                           "core.hooksPath"), ".githooks")
                self.assertEqual(self._noms(racine), avant, "aucun hook copié ni retiré")
                issue, out, (etat, detail) = self._jouer(racine, "o\n")  # rejeu
                self.assertNotIn(_QUESTION_HOOKS, out)
                self.assertEqual((issue, etat, detail), (self.s.ACTIF, "déjà là",
                                 "Hooks déjà activés dans ce clone ; configuration inchangée."))

    def test_hooks_conflit(self):
        cas = (("locale", "/ailleurs/hooks", "/ailleurs/hooks"), ("vide", "", "(vide)"),
               ("globale", None, "/global/hooks"))
        for nom, locale, dite in cas:
            with self.subTest(cas=nom):
                racine = self._racine()
                if locale is None:  # la valeur EFFECTIVE, pas seulement la locale
                    (self.tmp / "gitconfig").write_text("[core]\n\thooksPath = /global/hooks\n",
                                                        encoding="utf-8")
                else:
                    self._git(racine, "config", "core.hooksPath", locale)
                issue, out, (etat, detail) = self._jouer(racine)
                self.assertEqual((issue, etat), (self.s.ETRANGER, "dégradé"), out)
                self.assertIn(f"core.hooksPath = {dite}, valeur étrangère conservée", detail)
                self.assertNotIn(_QUESTION_HOOKS, out)
                self.assertNotIn(_ACTIVER, out)
                self.assertEqual(self._git(racine, "config", "--local", "--get", "core.hooksPath"),
                                 "" if locale is None else locale)
                (self.tmp / "gitconfig").write_text("", encoding="utf-8")

    def test_hooks_git_echec(self):
        racine = self._racine()
        config = racine / ".git" / "config"
        config.write_text(config.read_text(encoding="utf-8") + "[core\n", encoding="utf-8")
        octets = config.read_bytes()
        issue, out, (etat, detail) = self._jouer(racine)
        self.assertEqual((issue, etat), (self.s.ECHEC, "dégradé"), out)
        self.assertIn("lecture git échouée", detail)
        self.assertNotIn(_QUESTION_HOOKS, out)
        self.assertNotIn(_ACTIVER, out)
        self.assertEqual(config.read_bytes(), octets, "configuration réécrite")
        if os.geteuid() == 0:
            self.skipTest("SAUT ANNONCÉ — root lit un répertoire 000 : inventaire illisible non joué")
        racine = self._racine()
        hooks = racine / ".git" / "hooks"
        hooks.chmod(0)
        try:
            issue, out, (etat, detail) = self._jouer(racine)
        finally:
            hooks.chmod(0o755)
        self.assertEqual((issue, etat), (self.s.ECHEC, "dégradé"), out)
        self.assertIn(f"inventaire de {hooks} échoué (PermissionError)", detail)
        self.assertNotIn(_QUESTION_HOOKS, out)
        self.assertNotIn(_ACTIVER, out)
        self.assertEqual(self._git(racine, "config", "--local", "--get", "core.hooksPath"), "")

    def test_githooks_absent(self):
        racine = self._racine(githooks=False)
        issue, out, (etat, detail) = self._jouer(racine)
        self.assertEqual((issue, etat, detail), (self.s.ABSENT, "sans objet", ".githooks/ absent : "
                         "hooks non proposés ; configuration inchangée."), out)
        self.assertNotIn(_QUESTION_HOOKS, out)
        self.assertEqual(self._git(racine, "config", "--local", "--get", "core.hooksPath"), "")
        self.assertFalse((racine / ".githooks").exists())

    def test_githooks_lien_hors_racine_refuse(self):
        racine = self._racine(githooks=False)
        cible = self.tmp / "ailleurs" / "hooks"
        cible.mkdir()
        (racine / ".githooks").symlink_to(cible, target_is_directory=True)
        issue, out, (etat, detail) = self._jouer(racine)
        self.assertEqual((issue, etat), (self.s.ETRANGER, "dégradé"), out)
        self.assertIn(".githooks/ hors de cette racine", detail)
        self.assertNotIn(_QUESTION_HOOKS, out)
        self.assertNotIn(_ACTIVER, out)
        self.assertEqual(self._git(racine, "config", "--local", "--get", "core.hooksPath"), "")

    def test_diagnostics_ne_laissent_pas_passer_controles(self):
        racine = self._racine(hooks=("pre-push\x1b[31m",))
        issue, out, _ = self._jouer(racine)
        self.assertEqual(issue, self.s.HOOKS_ACTIFS, out)
        self.assertNotIn("\x1b", out)
        racine = self._racine()
        self._git(racine, "config", "core.hooksPath", "hors\x1b[31m")
        issue, out, _ = self._jouer(racine)
        self.assertEqual(issue, self.s.ETRANGER, out)
        self.assertNotIn("\x1b", out)

    def test_hooks_sans_question(self):
        """C17 : le chemin par défaut — ni question ni valeur locale — sous --dry-run, sans
        terminal et sous un marqueur d'agent (CLAUDECODE, COPILOT_CLI sur un vrai terminal),
        « o » pourtant prêt sur stdin."""
        cas = {"--dry-run": (dict(dry=True), "--dry-run"),
               "sans TTY": (dict(tty=False), "pas un terminal"),
               "CLAUDECODE": (dict(env_plus={"CLAUDECODE": "1"}), "pas un terminal"),
               "COPILOT_CLI": (dict(env_plus={"COPILOT_CLI": "1"}), "(ou agent)")}
        for nom, (options, morceau) in cas.items():
            with self.subTest(cas=nom):
                racine = self._racine()
                issue, out, (etat, detail) = self._jouer(racine, "o\n", **options)
                self.assertNotIn(_QUESTION_HOOKS, out)
                self.assertEqual((issue, etat), (self.s.NON_POSE, "sans objet"), out)
                self.assertIn(morceau, detail)
                self.assertEqual(self._git(racine, "config", "--local", "--get",
                                           "core.hooksPath"), "", out)

    def test_hooks_bilan_meme_passage(self):
        """C15 : un `main` entier (jambes 1 à 6 bouchonnées, aucune ne dépend de `cadre` ; bilan
        RÉEL en sous-processus) avec
        hooks actifs et un terminal : la SORTIE ENTIÈRE ne propose jamais la commande
        d'activation ; le bilan, joué après la jambe, voit les hooks actifs du même passage."""
        for valeur in ("hooks actifs", "valeur étrangère", "échec git", "lien externe"):
            with self.subTest(cas=valeur):
                self._verifier_bilan_meme_passage(valeur)

    def _verifier_bilan_meme_passage(self, valeur: str):
        racine = self._racine(hooks=("pre-push", "pre-commit") if valeur == "hooks actifs" else (),
                              githooks=valeur != "lien externe")
        if valeur == "lien externe":  # refusé par le setup : le bilan ne propose pas l'activation
            externe = self.tmp / f"externe{self.n}"
            externe.mkdir()
            (racine / ".githooks").symlink_to(externe, target_is_directory=True)
        if valeur == "valeur étrangère":
            self._git(racine, "config", "core.hooksPath", "autre-dossier")
        if valeur == "échec git":
            bin_dir = racine / "bin"
            bin_dir.mkdir()
            faux_git = bin_dir / "git"
            faux_git.write_text("#!/bin/sh\ncase \" $* \" in\n"
                                "  *\" config core.hooksPath \"*) exit 2 ;;\n"
                                "esac\nexec " + shlex.quote(GIT) + " \"$@\"\n", encoding="utf-8")
            faux_git.chmod(0o755)
        (racine / ".agents" / "bin").mkdir(parents=True)
        shutil.copy2(SETUP.parent / "setup_bilan.py", racine / ".agents" / "bin" / "setup_bilan.py")
        shutil.copy2(ROOT / ".agents" / "pyrun.sh", racine / ".agents" / "pyrun.sh")
        avant = self._noms(racine)
        s = self.s
        flux = io.StringIO()
        with mock.patch.object(s, "_racine", lambda _r: racine), \
                mock.patch.object(s, "_charger", lambda _r: None), \
                mock.patch.object(s, "_identite_et_board", lambda *_a: True), \
                mock.patch.object(s, "_stores", lambda *_a: None), \
                mock.patch.object(s, "_index", lambda *_a: None), \
                mock.patch.object(s, "_lire_ancienne", lambda *_a: s.Ancienne(s.SANS_OBJET, "banc")), \
                mock.patch.object(s, "_specs", lambda *_a: None), \
                mock.patch.object(s, "_dire_ancienne", lambda *_a: None), \
                mock.patch.object(s, "_graphe", lambda *_a: None), \
                mock.patch.object(sys, "stdin", _Tty("")), \
                mock.patch.dict(os.environ, {"PATH": str(racine / "bin") + os.pathsep
                                     + os.environ["PATH"]} if valeur == "échec git" else {}), \
                contextlib.redirect_stdout(flux):
            rc = s.main(["--root", str(racine)])
        out = flux.getvalue()
        self.assertEqual(rc, 0, "refus et dégradés de lecture ne changent pas le rc")
        self.assertNotIn(_ACTIVER, out, "une ligne du passage contourne le refus")
        self.assertNotIn(_QUESTION_HOOKS, out)
        lignes = out.splitlines()
        jambe = next(i for i, x in enumerate(lignes) if x.startswith("setup: hooks git : dégradé"))
        premier_bilan = next(i for i, x in enumerate(lignes) if x.startswith("bilan: "))
        self.assertLess(jambe, premier_bilan, "la jambe hooks git joue AVANT le bilan")
        hooks_bilan = next(x for x in lignes if x.startswith("bilan: hooks : KO"))
        if valeur == "hooks actifs":
            self.assertIn(f"hooks actifs dans {racine / '.git' / 'hooks'} (pre-commit, pre-push)",
                          hooks_bilan)
        if valeur != "valeur étrangère":
            self.assertIn("voir la jambe hooks git", _lignes(out)["core.hooksPath"][1], out)
        if valeur != "échec git":
            self.assertEqual(self._git(racine, "config", "--local", "--get", "core.hooksPath"),
                             "autre-dossier" if valeur == "valeur étrangère" else "")
        self.assertEqual(self._noms(racine), avant)


#: Les huit surfaces du témoin C de l'annexe (C19) et ses trois promesses.
_SURFACES_JOINTES = (".agents/bin/setup_projet.py", "core-scripts/setup.sh",
                     "core-scripts/setup.ps1", ".githooks/post-merge", "QUICK-SETUP.md",
                     "README.md", "docs/usage.html",
                     ".agents/skills/verification-discipline/SKILL.md")
_PROMESSES = re.compile(r"ne l.arme pas|does not arm it|never installs it for you")


def _compte_joint(texte: str) -> int:
    """La recherche de l'annexe en Python : `tr '\\n' ' '`, `sed 's/"  *"//g'`,
    `sed 's/ *# */ /g'`, `tr -s ' '`, puis `grep -c` (0 ou 1 : une seule ligne)."""
    texte = re.sub(r" +", " ", re.sub(r" *# *", " ", re.sub(r'" +"', "", texte.replace("\n", " "))))
    return 1 if _PROMESSES.search(texte) else 0


class TemoinTexteJointTests(unittest.TestCase):
    """C19 : le témoin C de l'annexe de T-01M5DJHCNK6ZX1XEG8XY0A8JR3, sur le texte JOINT (une
    promesse coupée par un retour à la ligne, une concaténation de chaînes ou un `#` reste vue).
    FENÊTRE ROUGE nommée : six des huit surfaces appartiennent aux lots B et C ; ce témoin ne
    passe au vert qu'après leur fusion. Mutant : l'ancienne `_SANS_ALERTE` rétablie -> rouge."""

    @unittest.skipIf(not DANS_LE_KIT, "SAUT ANNONCÉ — hors du kit, les huit surfaces "
                     "(README.md, docs/usage.html…) sont celles de l'adoptant")
    def test_temoin_texte_joint_huit_surfaces(self):
        comptes = {rel: _compte_joint((ROOT / rel).read_text(encoding="utf-8"))
                   for rel in _SURFACES_JOINTES}
        self.assertEqual(comptes, dict.fromkeys(_SURFACES_JOINTES, 0),
                         "une surface promet encore que le setup n'arme jamais les hooks")

    def test_temoin_joint_non_vide(self):
        ancienne = ('_SANS_ALERTE = ("sans core.hooksPath → .githooks, aucune alerte de fusion '
                    '(le setup ne l\'arme "\n                "pas : `git config core.hooksPath '
                    '.githooks`)")\n')
        self.assertEqual(_compte_joint(ancienne), 1, "le témoin passerait à vide")
        self.assertEqual(_compte_joint("# setup.sh does\n# not arm it\n"), 1)


class TemoinAstHorsLigneTests(unittest.TestCase):
    """Le setup n'importe que des modules d'une liste FERMÉE et ne lance que des
    producteurs d'une liste FERMÉE, par un seul site `subprocess.run`."""

    IMPORTS = {"__future__", "argparse", "importlib.util", "json", "os", "shlex", "subprocess", "sys",
               "dataclasses",
               "pathlib", "sqlite3", "cadre.init", "cadre.ledger", "cadre.ledger.stores",
               "cadre.paths", "dashboard", "etat_lecture", "specs_graph"}
    PRODUCTEURS = {"project_init.py", "build_index.py", "migrate_index_to_db.py",
                   "specs_graph.py", "tasks.py", "dashboard_daemon.py",
                   "fusion_enregistrement.py", "setup_bilan.py", "jira_setup.py"}

    def test_imports_et_producteurs_en_liste_fermee(self):
        arbre = ast.parse(SETUP.read_text(encoding="utf-8"))
        imports = set()
        for n in ast.walk(arbre):
            if isinstance(n, ast.Import):
                imports |= {a.name for a in n.names}
            elif isinstance(n, ast.ImportFrom):
                imports.add(n.module or "")
        self.assertEqual(imports - self.IMPORTS, set(), "import hors liste fermée (M4)")
        sites = [n for n in ast.walk(arbre) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name)
                 and n.func.value.id == "subprocess"]
        self.assertEqual(len(sites), 1, "un seul site subprocess.run, celui de `_executer`")
        noms = {n.args[1].value for n in ast.walk(arbre) if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name) and n.func.id == "_script"
                and len(n.args) > 1 and isinstance(n.args[1], ast.Constant)}
        self.assertTrue(noms, "aucun producteur relevé : le témoin passerait à vide")
        self.assertEqual(noms - self.PRODUCTEURS, set())
        for nom in noms:
            self.assertTrue((SETUP.parent / nom).is_file(), nom)

    def test_sync_spec_ferme_les_options(self):
        """Avis sécurité LOW 2 : `--` IMMÉDIATEMENT avant le chemin dans l'argv de
        sync-spec (accepté par son argparse : mesuré 3.14.7, 3.9.6 en isolé)."""
        arbre = ast.parse(SETUP.read_text(encoding="utf-8"))
        fonction = next(n for n in ast.walk(arbre)
                        if isinstance(n, ast.FunctionDef) and n.name == "_sync_spec")
        listes = [n for n in ast.walk(fonction) if isinstance(n, ast.List)]
        self.assertEqual(len(listes), 1, "un seul argv dans _sync_spec")
        elts = listes[0].elts
        self.assertEqual((type(elts[-1]).__name__, getattr(elts[-2], "value", None)),
                         ("Name", "--"), "le chemin doit suivre `--`")


class VoyageTests(unittest.TestCase):
    @unittest.skipIf(not DANS_LE_KIT, "hors du kit : test_adopting_gate.py ne voyage pas")
    def test_voyage(self):
        sys.path.insert(0, str(SETUP.parent))
        sys.path.insert(0, str(SETUP.parents[1] / "evals"))
        import sync_template as st  # noqa: PLC0415
        import test_adopting_gate as gate  # noqa: PLC0415

        regles = st.parse_exclude((ROOT / ".template-exclude").read_text(encoding="utf-8"))
        for rel in (".agents/bin/setup_projet.py", ".agents/bin/test_setup_projet.py",
                    "src/cadre/ledger/anciennes_bases.py", ".agents/vendor/cadre/ledger/anciennes_bases.py"):
            with self.subTest(rel=rel):
                self.assertIsNone(st.match_rule(rel, regles), f"{rel} ne voyage pas")
        sites = gate.sites_suspects(Path(__file__).read_text(encoding="utf-8"),
                                    gate.prefixes_strip(regles), "test_setup_projet.py")
        self.assertEqual([s for s in sites if s.forme is None], [],
                         "Étage A : un chemin `strip:` ancré sur la racine réelle, sans skip")


class LavandeReelleTests(unittest.TestCase):
    def test_lavande_reelle(self):
        source = os.environ.get("CADRE_SETUP_LAVANDE")
        if not source:
            self.skipTest("SAUT ANNONCÉ — CADRE_SETUP_LAVANDE absente : pointer une COPIE "
                          "(clone jetable) d'un adoptant porteur d'une ancienne base suivie")
        if GIT is None or not DANS_LE_KIT:
            self.skipTest("hors du kit ou git absent")
        tmp = Path(tempfile.mkdtemp(prefix="setup-lavande-")).resolve()
        self.addCleanup(shutil.rmtree, tmp, True)
        env = _env_isole(tmp)
        clone = tmp / "clone"
        # La source n'est que LUE (clone sans liens physiques) ; tout s'écrit dans `tmp`.
        subprocess.run([GIT, "clone", "-q", "--no-hardlinks", source, str(clone)], check=True,
                       capture_output=True, text=True, env=env)
        _batir_arbre(clone)  # le kit courant posé sur l'adoptant : une sync de template
        for cle, valeur in (("user.name", "Copie"), ("user.email", "copie@example.invalid")):
            subprocess.run([GIT, "-C", str(clone), "config", cle, valeur], check=True, env=env)
        base = clone / ".agents" / "state" / "v3_event_store.db"
        if not base.is_file():
            self.skipTest(f"SAUT ANNONCÉ — {source} ne porte pas d'ancienne base")
        avant = (hashlib.sha256(base.read_bytes()).hexdigest(),
                 sorted(p.name for p in base.parent.iterdir() if p.name.startswith(base.name)))
        p = subprocess.run([sys.executable, str(clone / ".agents" / "bin" / "setup_projet.py"),
                            "--root", str(clone), "--name", "copie"],
                           cwd=str(clone), env=env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=1800,
                           stdin=subprocess.DEVNULL, check=False)
        apres = (hashlib.sha256(base.read_bytes()).hexdigest(),
                 sorted(x.name for x in base.parent.iterdir() if x.name.startswith(base.name)))
        self.assertEqual(avant, apres, "l'ancienne base de la copie a bougé")
        self.assertEqual(avant[1], [base.name])
        etat, detail = _lignes(p.stdout).get("ancienne base", ("absente", p.stdout + p.stderr))
        self.assertIn(etat, ("dégradé", "déjà là"), detail)
        self.assertIn("retrouvées", detail)
        reseau = Path(env["SETUP_BANC_RESEAU"])
        self.assertFalse(reseau.exists() and reseau.read_text(encoding="utf-8").strip(),
                         "tentative réseau pendant le setup de la copie")


if __name__ == "__main__":
    unittest.main()
