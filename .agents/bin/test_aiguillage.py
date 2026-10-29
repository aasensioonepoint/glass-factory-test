"""BANC de `.agents/bin/aiguillage.py` (T-01M54GE7B18G5A1BCG7YBY0ZAN) — témoins T1 à T21.

Chaque témoin rougit si sa règle tombe. Les racines sont JETABLES (`tmp_path`) : jamais le board réel. Les témoins
« purs » injectent le pool (codes que le vrai `plan_pool` ne rend pas, T18) ; T1, T7, T8 et T15 passent par la CLI,
et T15 appelle le VRAI `core-scripts/plan_pool.py` sur une racine git bâtie comme `plan_pool.test.sh`.

T12, T13 et T17 lisent `README.md`, `docs/usage.html` et `.claude/commands/` DU KIT : ils SAUTENT nommément sans
`.agents/IS_THE_KIT` (chez l'adoptant ces surfaces sont les siennes).
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".agents" / "bin" / "aiguillage.py"
POOL = ROOT / "core-scripts" / "plan_pool.py"
# adopting-tree: marque du kit (strip: .agents/IS_THE_KIT), seule son EXISTENCE est lue ; T12, T13, T17 sautent sans elle
IS_KIT = (ROOT / ".agents" / "IS_THE_KIT").exists()
KIT_SEUL = pytest.mark.skipif(not IS_KIT, reason="KIT SEUL : .agents/IS_THE_KIT absent — README.md, docs/usage.html "
                                                 "et .claude/commands/ sont ceux de l'adoptant")

_SPEC = importlib.util.spec_from_file_location("aiguillage_banc", SCRIPT)
A = importlib.util.module_from_spec(_SPEC)
sys.modules["aiguillage_banc"] = A  # enregistré AVANT exec_module (test_modload_registration.py)
_SPEC.loader.exec_module(A)


def _t(n, state="pending", **kw):
    t = {"id": f"T-{n:08d}", "state": state, "task": f"tache {n}", "owner": "dev-mono"}
    t.update(kw)
    return t


def _board(root, taches):
    d = root / ".agents" / "state" / "board"
    d.mkdir(parents=True, exist_ok=True)
    (d / "TASKS.json").write_text(json.dumps({"next_id": len(taches) + 1, "tasks": taches}), encoding="utf-8")


def _relever(root, taches, codes, **kw):
    """Relevé EN PROCESSUS, pool injecté (`codes` à None : pool illisible)."""
    _board(root, taches)
    etat_lecture, api = A._charger_api()
    pool = None if codes is None else {f"T-{n:08d}": {"task": f"T-{n:08d}", "code": c} for n, c in codes.items()}
    rel = A.aiguiller(str(root), etat_lecture.taches(str(root)), pool, api, pool_raison="banc", **kw)
    return rel, A.rendre(rel, kw.get("max_", A.MAX_DEFAUT))


def _ligne(lignes, prefixe):
    return [ligne for ligne in lignes if ligne.startswith(prefixe)]


def _suivante(lignes):
    (s,) = _ligne(lignes, "SUIVANTE:")
    return s


def _cli(root, *args):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run([sys.executable, str(SCRIPT), "--root", str(root), *args], capture_output=True,
                          text=True, encoding="utf-8", env=env, timeout=300)


# --- T1 · board vide, board illisible, usage ---------------------------------------------------------------------
def test_t1_board_vide_propose_kickoff_demande(tmp_path):
    _board(tmp_path, [])
    p = _cli(tmp_path)
    assert p.returncode == 0, p.stderr
    lignes = p.stdout.splitlines()
    assert _suivante(lignes).startswith('SUIVANTE: /kickoff "<ta demande>"')
    assert lignes[-1].startswith("RELEVÉ INDICATIF, NON-AUTORITATIF")


def test_t1_board_illisible_rc1_et_usage_rc2(tmp_path):
    d = tmp_path / ".agents" / "state" / "board"
    d.mkdir(parents=True)
    (d / "TASKS.json").write_text("pas du json", encoding="utf-8")
    p = _cli(tmp_path)
    assert p.returncode == 1 and "board illisible" in p.stderr and p.stdout == ""
    assert _cli(tmp_path, "--max", "0").returncode == 2


# --- T2, T3, T11, T19 · la table ---------------------------------------------------------------------------------
def test_t2_ready_propose_kickoff(tmp_path):
    _, lignes = _relever(tmp_path, [_t(1)], {1: "READY"})
    assert _suivante(lignes).startswith("SUIVANTE: /kickoff T-00000001 — READY")


def test_t3_no_plan_deux_planning_une_kickoff(tmp_path):
    _, lignes = _relever(tmp_path / "deux", [_t(1), _t(2)], {1: "NO_PLAN", 2: "NO_PLAN"})
    assert _suivante(lignes).startswith("SUIVANTE: /planning — NO_PLAN : 2 tâches")
    _, lignes = _relever(tmp_path / "une", [_t(1)], {1: "NO_PLAN"})
    assert _suivante(lignes).startswith("SUIVANTE: /kickoff T-00000001 — NO_PLAN")


def test_t3b_no_plan_coupe_dit_au_moins_et_sa_vraie_borne(tmp_path):
    """Trois NO_PLAN : la boucle s'arrête au 2e (règle des deux NO_PLAN) — le compte est un
    PLANCHER (« au moins 2 »), et le TRONQUÉ nomme cette règle, jamais un `--max` qui n'a pas joué."""
    _, lignes = _relever(tmp_path, [_t(1), _t(2), _t(3)], {1: "NO_PLAN", 2: "NO_PLAN", 3: "NO_PLAN"})
    assert _suivante(lignes).startswith("SUIVANTE: /planning — NO_PLAN : au moins 2 tâches"), lignes
    (tronque,) = _ligne(lignes, "TRONQUÉ:")
    assert "2 candidates examinées sur 3" in tronque and "2e tâche sans plan" in tronque, tronque
    assert "--max" not in tronque, tronque


def test_t3d_sha_absent_boucle_par_lot_dit_sans_commande(tmp_path):
    """SHA_ABSENT dont le dernier plan est `lot K : Plan @…` : boucle de plan par lot EN COURS, état attendu —
    dit en dégradé, jamais `/planning-all <T>` ; le même code sur un autre titre reste à replanifier."""
    _board(tmp_path, [_t(1)])
    etat_lecture, api = A._charger_api()

    def lignes_pour(detail):
        pool = {"T-00000001": {"task": "T-00000001", "code": "SHA_ABSENT", "detail": detail}}
        return A.rendre(A.aiguiller(str(tmp_path), etat_lecture.taches(str(tmp_path)), pool, api, pool_raison="banc"))

    lignes = lignes_pour("titre du plan non canonique : lot B2 : Plan @ 1a2b3c4 - lot B")
    assert not any("/planning-all T-00000001" in l for l in lignes), lignes
    assert "T-00000001 : boucle de plan par lot en cours — attendre la consolidation du maître" in lignes, lignes
    assert _suivante(lignes_pour("titre du plan non canonique : Plan v2")).startswith(
        "SUIVANTE: /planning-all T-00000001")


def test_t3c_titre_du_board_sans_caractere_de_controle(tmp_path):
    titre = "titre \x1b[31mrouge\x1b[0m\r\x07 fin"
    _, lignes = _relever(tmp_path, [_t(1, state="running", writeset=["src/x"], task=titre)], {})
    (en_cours,) = _ligne(lignes, "EN COURS:")
    assert "titre [31mrouge[0m fin" in en_cours, en_cours
    assert not any(not c.isprintable() for c in en_cours), repr(en_cours)


def test_t11_stale_propose_planning_all(tmp_path):
    _, lignes = _relever(tmp_path, [_t(1)], {1: "STALE"})
    assert _suivante(lignes).startswith("SUIVANTE: /planning-all T-00000001 — STALE")


def test_t19_ready_precede_no_plan(tmp_path):
    _, lignes = _relever(tmp_path, [_t(1), _t(2)], {1: "NO_PLAN", 2: "READY"})
    assert _suivante(lignes).startswith("SUIVANTE: /kickoff T-00000002 — READY")


def test_t19b_ready_precede_un_plan_a_reprendre(tmp_path):
    _, lignes = _relever(tmp_path, [_t(1), _t(2)], {1: "STALE", 2: "READY"})
    assert _suivante(lignes).startswith("SUIVANTE: /kickoff T-00000002 — READY")


# --- T4, T5, T6 · amont, R1, recouvrement -------------------------------------------------------------------------
def test_t4_amont_ouvert_jamais_proposee(tmp_path):
    taches = [_t(1, state="blocked"), _t(2, depends_on=["T-00000001"])]
    _, lignes = _relever(tmp_path, taches, {2: "READY"})
    assert not any("/kickoff T-00000002" in ligne for ligne in lignes)
    assert any("T-00000002 attend T-00000001" in ligne for ligne in _ligne(lignes, "BLOQUÉES:"))
    assert _suivante(lignes).startswith("SUIVANTE: aucune")


def test_t5_running_en_tete_avec_r1(tmp_path):
    _, lignes = _relever(tmp_path, [_t(1, state="running", writeset=["src/x"]), _t(2, writeset=["src/y"])],
                         {2: "READY"})
    assert lignes[0].startswith("EN COURS: T-00000001") and "R1 FERMER AVANT D'OUVRIR" in lignes[0]
    assert _suivante(lignes).startswith("SUIVANTE: /kickoff T-00000002")


def test_t6_recouvrement_exclu_et_non_declare(tmp_path):
    taches = [_t(1, state="running", writeset=["src/a"]), _t(2, writeset=["src/a/x.py"]), _t(3)]
    _, lignes = _relever(tmp_path, taches, {2: "READY", 3: "READY"})
    assert _suivante(lignes).startswith("SUIVANTE: aucune")
    assert any("T-00000002 recoupe T-00000001" in ligne for ligne in _ligne(lignes, "BLOQUÉES:"))
    (declarer,) = _ligne(lignes, "À DÉCLARER:")
    assert "T-00000003" in declarer and "T-00000002" not in declarer
    assert not any(ligne.startswith("EN PARALLÈLE: /kickoff") for ligne in lignes)


# --- T7, T8, T15 · CLI sur racines jetables -----------------------------------------------------------------------
def test_t7_pool_absent_coverage_degraded(tmp_path):
    _board(tmp_path, [_t(1)])
    p = _cli(tmp_path)
    assert p.returncode == 0, p.stderr
    assert any(ligne.startswith("COVERAGE DEGRADED — plan_pool illisible") for ligne in p.stdout.splitlines())
    assert "/kickoff T-00000001" not in p.stdout and "READY" not in _suivante(p.stdout.splitlines())


def _git_env():
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    return env


def _git(root, *args):
    return subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "-C", str(root),
                           *args], capture_output=True, text=True, check=True, env=_git_env()).stdout.strip()


def _depot_pool(root):
    """Le mini-dépôt de `plan_pool.test.sh` : deux commits réels, puis un plan sur `b.txt` approuvé par GO."""
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "banc@local")
    _git(root, "config", "user.name", "banc")
    (root / "a.txt").write_text("v1\n", encoding="utf-8")
    (root / "b.txt").write_text("stable\n", encoding="utf-8")
    _git(root, "add", "a.txt", "b.txt")
    _git(root, "commit", "-q", "-m", "c1")
    sha = _git(root, "rev-parse", "--short", "HEAD")
    _board(root, [_t(1)])
    d = root / ".agents" / "state" / "specs"
    d.mkdir(parents=True)
    entrees = [
        {"id": "S-00000001", "task": "T-00000001", "kind": "plan", "title": f"Plan @ {sha} - banc", "text": "",
         "files": ["b.txt"], "date": "2026-10-19"},
        {"id": "S-00000002", "task": "T-00000001", "kind": "verdict", "title": "plan-critic GO", "text": "",
         "files": [], "date": "2026-10-19"},
    ]
    (d / "SPECS.json").write_text(json.dumps({"next_id": 3, "entries": entrees}), encoding="utf-8")


def _empreinte(root):
    """HEAD, l'arbre de travail (`status` avec les ignorés et chaque non-suivi) et l'octet de chaque non-suivi."""
    statut = _git(root, "status", "--porcelain=v1", "--untracked-files=all", "--ignored")
    octets = {}
    for ligne in statut.splitlines():
        chemin = root / ligne[3:]
        if chemin.is_file():
            octets[ligne[3:]] = hashlib.sha256(chemin.read_bytes()).hexdigest()
    return _git(root, "rev-parse", "HEAD"), statut, _git(root, "diff", "HEAD"), octets


@pytest.mark.skipif(not POOL.is_file(), reason="core-scripts/plan_pool.py absent")
def test_t15_bout_en_bout_vrai_plan_pool(tmp_path):
    root = tmp_path / "depot"
    _depot_pool(root)
    p = _cli(root)
    assert p.returncode == 0, p.stderr
    assert _suivante(p.stdout.splitlines()).startswith("SUIVANTE: /kickoff T-00000001 — READY"), p.stdout
    (root / "b.txt").write_text("bougé\n", encoding="utf-8")
    _git(root, "commit", "-q", "-am", "c2")
    p = _cli(root)
    assert _suivante(p.stdout.splitlines()).startswith("SUIVANTE: /planning-all T-00000001 — STALE"), p.stdout


@pytest.mark.skipif(not POOL.is_file(), reason="core-scripts/plan_pool.py absent")
def test_t8_lecture_seule_empreinte_identique(tmp_path):
    root = tmp_path / "depot"
    _depot_pool(root)
    avant = _empreinte(root)
    for args in ((), ("--json",), ("--epic", "E-01"), ("--max", "1")):
        assert _cli(root, *args).returncode == 0
    assert _empreinte(root) == avant


# --- T9, T10, T20 · bornes et filtres ---------------------------------------------------------------------------
def test_t9_borne_dit_tronque(tmp_path):
    taches = [_t(n, writeset=[f"src/p{n}"]) for n in range(1, 5)]
    _, lignes = _relever(tmp_path, taches, {n: "READY" for n in range(1, 5)}, max_=1)
    assert len(_ligne(lignes, "EN PARALLÈLE: /kickoff")) == 1
    (tronque,) = _ligne(lignes, "TRONQUÉ:")
    assert "2 candidates examinées sur 4" in tronque


def test_t10_epic_filtre(tmp_path):
    taches = [_t(1, epic="E-01"), _t(2, epic="E-02")]
    _, lignes = _relever(tmp_path, taches, {1: "READY", 2: "READY"}, epic="E-02")
    assert _suivante(lignes).startswith("SUIVANTE: /kickoff T-00000002")
    assert not any("T-00000001" in ligne for ligne in lignes)


def test_t20_chantier_propose_planning_all_chantier(tmp_path):
    taches = [_t(1, chantier="x"), _t(2, chantier="x"), _t(3, chantier="y")]
    codes = {1: "NO_PLAN", 2: "NO_PLAN", 3: "READY"}
    _, lignes = _relever(tmp_path / "x", taches, codes, chantier="x")
    assert _suivante(lignes).startswith("SUIVANTE: /planning-all --chantier x — NO_PLAN : 2 tâches")
    assert not any("T-00000003" in ligne for ligne in lignes)
    _, lignes = _relever(tmp_path / "tous", taches, codes)
    assert _suivante(lignes).startswith("SUIVANTE: /kickoff T-00000003")


# --- T14, T16, T18, T21 · table totale, disjonction, code inconnu, voie directe --------------------------------
def test_t14_table_totale_sur_exit_de_plan_pool():
    arbre = ast.parse(POOL.read_text(encoding="utf-8"))
    exits = [n.value for n in arbre.body if isinstance(n, ast.Assign)
             and any(isinstance(c, ast.Name) and c.id == "EXIT" for c in n.targets)]
    assert len(exits) == 1 and isinstance(exits[0], ast.Dict)
    cles = {k.value for k in exits[0].keys}
    assert cles and cles == set(A.TABLE_POOL)


def test_t16_disjonction_au_segment(tmp_path):
    taches = [_t(1, writeset=["src/a"]), _t(2, writeset=["src/a/b.py"]), _t(3, writeset=["src/ab"])]
    _, lignes = _relever(tmp_path, taches, {1: "READY", 2: "READY", 3: "READY"})
    assert _suivante(lignes).startswith("SUIVANTE: /kickoff T-00000001")
    paralleles = _ligne(lignes, "EN PARALLÈLE: /kickoff")
    assert any("/kickoff T-00000003" in ligne for ligne in paralleles)
    assert not any("/kickoff T-00000002" in ligne for ligne in paralleles)


def test_t18_code_inconnu_coverage_degraded_sans_commande(tmp_path):
    _, lignes = _relever(tmp_path, [_t(1)], {1: "CODE_MYSTERE"})
    degrade = _ligne(lignes, "COVERAGE DEGRADED")
    assert degrade and "CODE_MYSTERE" in degrade[0] and "aucune commande" in degrade[0]
    assert _suivante(lignes).startswith("SUIVANTE: aucune")
    assert not any(re.search(r"/(kickoff|planning)\S* T-00000001", ligne) for ligne in lignes)
    assert A.commande_pour("CODE_MYSTERE", "T-00000001")[0] is None


def test_t21_parallel_seulement_en_voie_directe_et_etiquete(tmp_path):
    estampe = {"writeset": ["src/p"], "le": "2026-10-19"}
    taches = [_t(1, writeset=["src/p1"], direct=estampe), _t(2, writeset=["src/p2"], direct=estampe)]
    _, lignes = _relever(tmp_path / "directe", taches, {1: "READY", 2: "READY"})
    assert any(ligne.startswith("EN PARALLÈLE: /kickoff T-00000002") for ligne in lignes)
    (geste,) = [ligne for ligne in _ligne(lignes, "EN PARALLÈLE:") if "tasks.py parallel" in ligne]
    assert "tasks.py parallel T-00000001 T-00000002" in geste and "ÉCRIT le groupe au board" in geste
    taches = [_t(1, writeset=["src/p1"]), _t(2, writeset=["src/p2"])]
    _, lignes = _relever(tmp_path / "planifiee", taches, {1: "READY", 2: "READY"})
    assert any(ligne.startswith("EN PARALLÈLE: /kickoff T-00000002") for ligne in lignes)
    assert not any("tasks.py parallel" in ligne for ligne in _ligne(lignes, "EN PARALLÈLE:"))


# --- T12, T13, T17 · surfaces du kit ------------------------------------------------------------------------------
COMPTE_EN_CHIFFRES = re.compile(r"\b\d+\s+(?:commandes?|commands?)\b", re.IGNORECASE)


def _commandes():
    return {"/" + p.stem for p in (ROOT / ".claude" / "commands").glob("*.md")}


def _table_readme():
    texte = (ROOT / "README.md").read_text(encoding="utf-8")
    debut = texte.index("## Command reference")
    return texte[debut:texte.index("\n---", debut)]


def _section(html, ouvrant, fins):
    debut = html.index(ouvrant)
    suite = [html.find(f, debut + len(ouvrant)) for f in fins]
    return html[debut:min(i for i in suite if i != -1)]


def _usage():
    return (ROOT / "docs" / "usage.html").read_text(encoding="utf-8")


def _quelle_commande():
    # La carte « Quelle commande lancer ensuite ? » de l'onglet Avancé ; le préfixe d'hôte `<span class="pfx">/</span>`
    # est ramené à `/` pour lire la commande telle que l'aiguilleur la rend.
    section = _section(_usage(), '<details class="mc" id="quelle-commande">', ("</details>",))
    return section.replace('<span class="pfx">/</span>', "/")


@KIT_SEUL
def test_t12_table_readme_egale_les_commandes():
    lignes = set(re.findall(r"^\| `(/[a-z][a-z-]*)", _table_readme(), re.MULTILINE))
    assert lignes == _commandes()


@KIT_SEUL
def test_t13_commandes_rendues_existent_et_sont_citees():
    rendues = {A.DEMANDE_LIBRE.split()[0], "/kickoff"}
    for code in list(A.TABLE_POOL) + ["CODE_MYSTERE"]:
        for n in (1, 2):
            for chantier in ("", "x"):
                cmd = A.commande_pour(code, "T-00000001", n, chantier)[0]
                if cmd:
                    rendues.add(cmd.split()[0])
    assert rendues == set(A.COMMANDES_PROPOSEES)
    section = _quelle_commande()
    for cmd in rendues:
        assert cmd in _commandes()
        assert re.search(r"<code>" + re.escape(cmd) + r"(?![\w-])", section), cmd


@KIT_SEUL
def test_t17_aucun_compte_de_commandes():
    # La page d'usage n'a plus de section « pendant » (remplacée par le guide de démarrage) : seul le refus d'un
    # compte de commandes en chiffres reste épinglé, sur la carte de l'aiguilleur et la table du README.
    quelle = _quelle_commande()
    assert "aiguillage.py" in quelle
    assert not COMPTE_EN_CHIFFRES.search(re.sub(r"<[^>]+>", "", quelle))
    assert not COMPTE_EN_CHIFFRES.search(_table_readme())


# --- AliasAnglais · lot W de T-01M5QC86XNEJ5NEX6DGZJ0AJZ5 : `--workstream` en tête, `--chantier` gardé ------------
def _charger(nom, chemin):
    spec = importlib.util.spec_from_file_location(nom, chemin)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[nom] = mod  # enregistré AVANT exec_module (test_modload_registration.py)
    spec.loader.exec_module(mod)
    return mod


_PW = ROOT / "core-scripts" / "plan_waves.py"
_ALIAS = {"PW": ("plan_waves_banc_alias", _PW, ()),  # (nom, fichier, frères dont il dépend au chargement)
          "FDR": ("feuille_de_route_banc_alias", ROOT / "core-scripts" / "feuille_de_route.py", (_PW,)),
          "POOL": ("plan_pool_banc_alias", POOL, ())}
_CHARGES: dict = {}


def _alias(cle):
    """Chargé À L'APPEL, jamais à la collecte : un fichier absent saute ses tests, pas le banc entier."""
    if cle == "A":
        return A
    if cle not in _CHARGES:
        nom, chemin, freres = _ALIAS[cle]
        for requis in (chemin, *freres):
            if not requis.is_file():
                pytest.skip(f"{requis.relative_to(ROOT)} absent")
        try:
            _CHARGES[cle] = _charger(nom, chemin)
        except BaseException:
            sys.modules.pop(nom, None)  # jamais un module à moitié chargé pour le test suivant
            raise
    return _CHARGES[cle]


class _Capte(Exception):
    pass


def _capteur(vu):
    def capter(*args, **kwargs):
        vu.append((args, kwargs))
        raise _Capte
    return capter


class TestAliasAnglais:
    """Le nom anglais en tête, l'ancien accepté, une seule `dest` : `chantier`. Mutant : `dest="chantier"` retiré
    d'un `--workstream` => `args.chantier` absent, le filtre n'arrive plus au calcul — rouge."""

    @pytest.mark.parametrize("nom", ["--workstream", "--chantier"])
    def test_aiguillage_filtre_par_les_deux_noms(self, monkeypatch, capsys, tmp_path, nom):
        taches = [_t(1, chantier="x"), _t(2, chantier="x"), _t(3, chantier="y")]
        _board(tmp_path, taches)
        vu = []

        def relever(root, epic="", chantier="", max_=A.MAX_DEFAUT):
            vu.append(chantier)
            etat_lecture, api = A._charger_api()
            pool = {f"T-{n:08d}": {"task": f"T-{n:08d}", "code": c}
                    for n, c in {1: "NO_PLAN", 2: "NO_PLAN", 3: "READY"}.items()}
            return A.aiguiller(root, etat_lecture.taches(root), pool, api, epic=epic, chantier=chantier,
                               max_=max_, pool_raison="banc")

        monkeypatch.setattr(A, "relever", relever)
        assert A.main(["--root", str(tmp_path), nom, "x"]) == 0 and vu == ["x"]
        out = capsys.readouterr().out
        assert "SUIVANTE: /planning-all --chantier x" in out and "T-00000003" not in out, out

    @pytest.mark.parametrize("nom", ["--workstream", "--chantier"])
    def test_plan_waves_les_deux_noms_meme_dest(self, monkeypatch, tmp_path, nom):
        vu, pw = [], _alias("PW")
        monkeypatch.setattr(pw, "compute", _capteur(vu))
        with pytest.raises(_Capte):
            pw.main(["--root", str(tmp_path), "waves", nom, "x"])
        assert vu[0][0][2] == "x"

    @pytest.mark.parametrize("nom", ["--workstream", "--chantier"])
    def test_feuille_de_route_les_deux_noms_meme_dest(self, monkeypatch, tmp_path, nom):
        vu, fdr = [], _alias("FDR")
        monkeypatch.setattr(fdr, "compute", _capteur(vu))
        with pytest.raises(_Capte):
            fdr.main(["--root", str(tmp_path), nom, "x"])
        assert vu[0][0][1] == "x"

    def test_feuille_de_route_absent_nomme_les_deux(self, capsys):
        with pytest.raises(SystemExit) as exc:
            _alias("FDR").main([])
        err = capsys.readouterr().err
        assert exc.value.code == 2 and "--workstream/--chantier" in err

    @pytest.mark.parametrize("mod,argv,cite", [
        ("A", ["--help"], True), ("PW", ["--help"], False), ("PW", ["waves", "--help"], True),
        ("FDR", ["--help"], True), ("POOL", ["--help"], False),
        ("POOL", ["status", "--help"], False), ("POOL", ["check", "--help"], False)])
    def test_aides_en_anglais_ascii(self, monkeypatch, capsys, mod, argv, cite):
        monkeypatch.setenv("PYTHON_COLORS", "0")  # sous FORCE_COLOR=1, l'aide colorée porte des échappements
        with pytest.raises(SystemExit) as exc:
            _alias(mod).main(argv)
        out = capsys.readouterr().out
        assert exc.value.code == 0 and out.isascii(), out
        if cite:
            plat = " ".join(out.split())  # argparse replie l'aide à la largeur du terminal
            assert "--workstream, --chantier WORKSTREAM" in plat and "old name: --chantier" in plat, out


# T-01M5QC86XN, passe 2 : les metavars des aides sont en anglais. Un nom francais qui revient rougit ici.
_METAVARS_FR = re.compile(r"\b(POURQUOI|RAISON|NOM|GROUPE|CLE|AAAA-MM-JJ|ETAPE|TENTATIVE|MOTIF|OBSERVE)\b")


@pytest.mark.parametrize("script,argv,attendus", [
    ("tasks.py", ["done", "--help"], ("--without-review, --sans-binome WHY",)),
    ("tasks.py", ["new", "--help"], ("GROUP", "NAME", "WHY", "OBSERVED")),
    ("tasks.py", ["chrono", "--help"], ("STEP", "ATTEMPT")),
    ("tasks.py", ["depends", "--help"], ("MOTIVE",)),
    ("tasks.py", ["start", "--help"], ("REASON", "WHY")),
    ("tasks.py", ["fournee", "--help"], ("REASON", "WHY")),
    ("tasks.py", ["jira-import", "--help"], ("KEY",)),
    ("cadrage_plan.py", ["--help"], ("FILE", "PART", "NAME"))])
def test_metavars_en_anglais(script, argv, attendus):
    env = {**os.environ, "NO_COLOR": "1", "COLUMNS": "200"}
    cp = subprocess.run([sys.executable, "-I", str(ROOT / ".agents" / "bin" / script), *argv],
                        cwd=ROOT, capture_output=True, text=True, env=env, check=False)
    assert cp.returncode == 0, cp.stderr
    assert not _METAVARS_FR.search(cp.stdout), cp.stdout
    for attendu in attendus:
        assert attendu in cp.stdout, (attendu, cp.stdout)
