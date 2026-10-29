#!/usr/bin/env python3
"""Témoin de `.agents/bin/rea_run.py` (T-01M5HEJYSJEYA8K3834FZVT60N, annexe § C).

Un FAUX `npx` (et un faux `node`) posé SEUL sur `PATH` enregistre, à chaque appel, argv, env, cwd et la
nature de son stdin dans `appels.jsonl`, à côté de lui ; sa conduite se lit dans `conf.json`, au même endroit,
parce que le runner lui retire toute variable hors liste blanche. Aucun réseau, aucun vrai rea. Le journal
specs est une surcharge `AGENTS_SPECS_PATH` (forme `.json`, clé `entries`) ; l'état du runner une surcharge
`AGENTS_REA_STATE` sous `tmp_path` — rien n'est écrit dans le dépôt.

Chaque cas asserte le code de sortie ET le motif ; chaque porte a son mutant (annexe § C), rejoué à la main
dans un clone jetable. POSIX seul : le faux `npx` est un script à shebang ; Windows NON MESURÉ, saut annoncé.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".agents" / "bin" / "rea_run.py"
POSIX = os.name == "posix"

pytestmark = pytest.mark.skipif(
    not POSIX or " " in sys.executable,
    reason="SAUT ANNONCE : faux npx en script a shebang POSIX (interpreteur sans espace) ; Windows non mesure")


def _charger() -> ModuleType:
    spec = importlib.util.spec_from_file_location("rea_run", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["rea_run"] = mod  # enregistré AVANT l'exécution (T-00000134)
    spec.loader.exec_module(mod)
    return mod


rea_run = _charger()

FAUX_NPX = r'''
import json, os, subprocess, sys, time
ICI = os.path.dirname(os.path.realpath(__file__))
with open(os.path.join(ICI, "conf.json"), encoding="utf-8") as fh:
    conf = json.load(fh)
argv = sys.argv[1:]
st, nul = os.fstat(0), os.stat(os.devnull)
appel = {"argv": argv, "env": dict(os.environ), "cwd": os.getcwd(),
         "stdin_devnull": (st.st_dev, st.st_ino) == (nul.st_dev, nul.st_ino),
         "npmrc_dans_cwd": os.path.exists(".npmrc"), "cwd_vide": os.listdir(".") == []}
with open(os.path.join(ICI, "appels.jsonl"), "a", encoding="utf-8") as fh:
    fh.write(json.dumps(appel) + "\n")
if conf.get("petit_enfant"):
    enfant = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
    with open(conf["petit_enfant"], "w", encoding="utf-8") as fh:
        fh.write(str(enfant.pid))
if conf.get("ecrit_avant"):
    sys.stdout.write(conf["ecrit_avant"])
    sys.stdout.flush()
time.sleep(float(conf.get("dort", 0)))
rea = argv[2:] if argv[:2] == ["-y", "rea-agents@6.7.0"] else argv
if rea[:1] == ["--version"]:
    print(conf.get("version", "6.7.0"))
    sys.exit(0)
if rea[:1] == ["doctor"] and "doctor" in conf:
    print(json.dumps(conf["doctor"]))
    sys.exit(int(conf.get("doctor_rc", 1)))
print(json.dumps(conf.get("sortie", {"provider": {"id": "faux"}})))
sys.stderr.write("progression\n")
sys.exit(int(conf.get("rc", 0)))
'''

FAUX_NODE = r'''
import json, os, time
ICI = os.path.dirname(os.path.realpath(__file__))
with open(os.path.join(ICI, "conf.json"), encoding="utf-8") as fh:
    conf = json.load(fh)
time.sleep(float(conf.get("node_dort", 0)))
print(conf.get("node", "v24.11.0"))
'''

CANARIS = {"ZZ_CANARY": "fuite", "REA_KUNA_COMMAND": "/x/kuna", "NODE_OPTIONS": "--require /x/mal.js",
           "npm_config_registry": "http://127.0.0.1:9/"}
D8 = "S-12345678"
ULID = "S-01M5HG8ZF5VY9T8DTV9TS86DT0"
KOLY = 512  # le trailer UDIF ouvre 512 octets avant la fin


class Atelier:
    def __init__(self, racine: Path, capsys: pytest.CaptureFixture) -> None:
        self.racine = racine
        self.capsys = capsys
        self.bin = racine / "bin"
        self.appelant = racine / "appelant"
        self.etat = racine / "etat"
        self.specs = racine / "specs.json"
        for rep in (self.bin, self.appelant):
            rep.mkdir()
        for nom, corps in (("npx", FAUX_NPX), ("node", FAUX_NODE)):
            chemin = self.bin / nom
            chemin.write_text(f"#!{sys.executable}\n{corps}", encoding="utf-8")
            chemin.chmod(0o755)
        self.conf()
        self.specs.write_text(json.dumps({"entries": []}), encoding="utf-8")

    def conf(self, **valeurs: object) -> None:
        (self.bin / "conf.json").write_text(json.dumps(valeurs), encoding="utf-8")

    def appels(self) -> list[dict]:
        journal = self.bin / "appels.jsonl"
        if not journal.exists():
            return []
        return [json.loads(l) for l in journal.read_text(encoding="utf-8").splitlines() if l.strip()]

    def argv_rea(self) -> list[str]:
        appels = self.appels()
        assert len(appels) == 1, appels
        argv = appels[0]["argv"]
        assert argv[:2] == ["-y", "rea-agents@6.7.0"], argv
        return argv[2:]

    def decision(self, ident: str, texte: str, kind: str = "decision") -> None:
        data = json.loads(self.specs.read_text(encoding="utf-8"))
        data["entries"].append({"id": ident, "kind": kind, "title": "decision pilote rea", "text": texte})
        self.specs.write_text(json.dumps(data), encoding="utf-8")

    def fichier(self, rel: str, contenu: bytes = b"\x7fELF ordinaire") -> Path:
        chemin = self.appelant / rel
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_bytes(contenu)
        return chemin

    def run(self, *args: str) -> tuple[int, dict]:
        rc = rea_run.main(list(args))
        lu = self.capsys.readouterr()
        sortie, self.erreurs = lu.out, lu.err
        lignes = [l for l in sortie.splitlines() if l.strip()]
        assert len(lignes) == 1, f"stdout doit porter UNE ligne JSON : {sortie!r}"
        return rc, json.loads(lignes[0])

    def refus(self, motif: str, *args: str) -> dict:
        rc, sortie = self.run(*args)
        assert (rc, sortie.get("motif")) == (2, motif), sortie
        assert self.appels() == [], "un REFUS ne lance jamais npx"
        return sortie

    def ok(self, *args: str) -> dict:
        rc, sortie = self.run(*args)
        assert (rc, sortie.get("motif")) == (0, None), sortie
        return sortie


@pytest.fixture
def atelier(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> Atelier:
    a = Atelier(tmp_path.resolve(), capsys)
    monkeypatch.setenv("PATH", str(a.bin))
    monkeypatch.setenv("AGENTS_REA_STATE", str(a.etat))
    monkeypatch.setenv("AGENTS_SPECS_PATH", str(a.specs))
    for nom, valeur in CANARIS.items():
        monkeypatch.setenv(nom, valeur)
    monkeypatch.chdir(a.appelant)
    return a


def _koly(taille: int = 4096) -> bytes:
    b = bytearray(taille)
    b[-KOLY:-KOLY + 4] = b"koly"
    return bytes(b)


# --- commandes et séparateur ------------------------------------------------------------------------
@pytest.mark.parametrize("cmd", ["setup", "update", "uninstall", "mcp", "environment-x", "environment-serve",
                                 "environment-export", "inspect-elf-notes", "inspect-il", "inspect-model-artifact",
                                 "inspect-macho@latest", "completions", "skills"])
def test_commande_refusee_sans_condition(atelier: Atelier, cmd: str) -> None:
    atelier.decision(D8, f"{cmd} autorise sur f.bin")
    atelier.refus("commande_refusee", "run", "--decision", D8, "--cible", "f.bin", cmd, "--", "f.bin")


def test_latest_en_argument_refuse(atelier: Atelier) -> None:
    atelier.refus("commande_refusee", "run", "inspect-macho", "--", "rea-agents@latest")


def test_separateur_absent(atelier: Atelier) -> None:
    atelier.refus("separateur_absent", "run", "inspect-macho", str(atelier.fichier("f.bin")))


def test_trente_deux_commandes_et_version_epinglee() -> None:
    assert len(rea_run.COMMANDES) == 32
    assert rea_run.REA_VERSION == "6.7.0"


# --- options : builtins, liste fermée, valeurs à tiret ------------------------------------------------
def test_doctor_mcp_refuse_et_absent_de_argv(atelier: Atelier) -> None:
    atelier.refus("option_refusee", "run", "doctor", "--", "--mcp")


@pytest.mark.parametrize("jeton", ["--llms", "--schema", "--json", "--version", "-h", "--token-limit=5",
                                   "--format=yaml", "--tokenLimit=5", "--no-json", "--", "--help"])
def test_builtins_et_tiret_simple_refuses(atelier: Atelier, jeton: str) -> None:
    atelier.refus("option_refusee", "run", "inspect-macho", "--", str(atelier.fichier("f.bin")), jeton)


def test_option_hors_liste_refusee(atelier: Atelier) -> None:
    atelier.refus("option_refusee", "run", "inspect-macho", "--", str(atelier.fichier("f.bin")), "--foo=1")


def test_valeur_espacee_a_tiret_refusee(atelier: Atelier) -> None:
    atelier.refus("valeur_a_tiret", "run", "inspect-artifact", "--", "--integrity-policy", "--format", "/abs/f")
    atelier.refus("valeur_a_tiret", "run", "inspect-artifact", "--", "--integrity-policy", "--format", "json",
                  "fail", "/x.dmg")


@pytest.mark.parametrize("builtin", ["--mcp", "--incur-update-check"])
def test_doctor_target_suivi_d_un_builtin(atelier: Atelier, builtin: str) -> None:
    atelier.refus("valeur_a_tiret", "run", "doctor", "--", "--target", builtin)


def test_valeur_a_tiret_admise_sous_la_forme_egal(atelier: Atelier) -> None:
    f = str(atelier.fichier("f.bin"))
    atelier.ok("run", "decompile", "--", f, "--procedure=-x")
    assert atelier.argv_rea() == ["decompile", f, "--procedure=-x", "--format", "json"]


def test_valeur_manquante(atelier: Atelier) -> None:
    atelier.refus("valeur_manquante", "run", "decompile", "--", str(atelier.fichier("f.bin")), "--procedure")


def test_booleen_et_sa_negation_admis(atelier: Atelier) -> None:
    f = str(atelier.fichier("f.bin"))
    atelier.ok("run", "search", "--", f, "--case-sensitive")
    atelier.ok("run", "search", "--", f, "--no-case-sensitive")


def test_alias_camel_admis_et_normalise(atelier: Atelier) -> None:
    d = atelier.appelant / "app"
    d.mkdir()
    atelier.ok("run", "analyze-javascript-application", "--", str(d), "--sourcePath=main.js")
    assert "--source-path=main.js" in atelier.argv_rea()


def test_argv_finit_par_format_json(atelier: Atelier) -> None:
    atelier.ok("run", "inspect-macho", "--", str(atelier.fichier("f.bin")))
    assert atelier.argv_rea()[-2:] == ["--format", "json"]


# --- arité ----------------------------------------------------------------------------------------------
def test_positionnel_en_trop(atelier: Atelier) -> None:
    atelier.refus("positionnel_en_trop", "run", "inspect-macho", "--", "/a", "/b")


def test_positionnel_manquant(atelier: Atelier) -> None:
    atelier.refus("positionnel_manquant", "run", "read-bytes", "--", "/a")


def test_variadique_non_plafonne(atelier: Atelier) -> None:
    p = str(atelier.fichier("p.bin"))
    atelier.ok("run", "demangle-swift", "--", p, "s1", "s2", "s3")
    assert atelier.argv_rea() == ["demangle-swift", p, "s1", "s2", "s3", "--format", "json"]


# --- C31 : `..` refusé, jointure sans normalisation (portage de callerPathSymlinkParentCli.test.ts) ----
@pytest.fixture
def frontiere(atelier: Atelier, monkeypatch: pytest.MonkeyPatch) -> Path:
    racine = atelier.racine / "frontiere"
    (racine / "target" / "child").mkdir(parents=True)
    (racine / "target" / "sample").write_bytes(b"cible")
    (racine / "sample").write_bytes(b"autre")
    (racine / "link").symlink_to("target/child")
    monkeypatch.chdir(racine)
    return racine


def test_lien_puis_parent_relatif_refuse(atelier: Atelier, frontiere: Path) -> None:
    atelier.refus("segment_parent", "run", "inspect-artifact", "--", "link/../sample")


def test_lien_puis_parent_absolu_refuse(atelier: Atelier, frontiere: Path) -> None:
    atelier.refus("segment_parent", "run", "inspect-artifact", "--", f"{frontiere}/link/../sample")


@pytest.mark.parametrize("rel", ["sub/f.bin", "./sub//f.bin"])
def test_jointure_au_cwd_appelant_sans_normalisation(atelier: Atelier, rel: str) -> None:
    atelier.fichier("sub/f.bin")
    atelier.ok("run", "inspect-macho", "--", rel)
    attendu = os.path.join(os.getcwd(), rel)
    assert atelier.argv_rea() == ["inspect-macho", attendu, "--format", "json"]
    appel = atelier.appels()[0]
    assert appel["cwd"] not in (os.path.realpath(atelier.etat), os.getcwd()) and appel["cwd_vide"] is True


def test_decompile_relatif_joint_au_cwd_appelant(atelier: Atelier) -> None:
    atelier.fichier("rel/f.bin")
    atelier.ok("run", "decompile", "--", "rel/f.bin")
    assert atelier.argv_rea()[1] == os.path.join(os.getcwd(), "rel/f.bin")


def test_out_a_segment_parent(atelier: Atelier) -> None:
    atelier.refus("segment_parent", "run", "--out=a/../b", "inspect-macho", "--", str(atelier.fichier("f.bin")))


def test_glue_paths_a_segment_parent(atelier: Atelier) -> None:
    atelier.refus("segment_parent", "run", "inspect-wasm-artifact", "--", str(atelier.fichier("f.wasm")),
                  "--glue_paths=../x")


def test_source_path_a_segment_parent(atelier: Atelier) -> None:
    atelier.refus("segment_parent", "run", "analyze", "--", str(atelier.fichier("f.bin")), "--source-path=../x")


def test_vue_a_segment_parent(atelier: Atelier) -> None:
    atelier.refus("segment_parent", "vue", "a/../e.json")


def test_aucun_abspath_ni_normpath_dans_le_runner() -> None:
    arbre = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    appels = {n.attr for n in ast.walk(arbre) if isinstance(n, ast.Attribute)}
    assert not appels & {"abspath", "normpath"}


# --- C26/C32/C33 : DMG et PKG, par nom, realpath, contenu et parcours confiné de `.app` ----------------
def test_lien_vers_dmg_sans_koly(atelier: Atelier) -> None:
    atelier.fichier("x.dmg", b"aucune signature")
    (atelier.appelant / "t.bin").symlink_to("x.dmg")
    sortie = atelier.refus("decision_requise", "run", "inspect-artifact", "--", "t.bin")
    assert "realpath" in sortie["detail"], sortie


def test_suffixe_en_capitales(atelier: Atelier) -> None:
    atelier.fichier("T.DMG", b"aucune signature")
    atelier.refus("decision_requise", "run", "inspect-artifact", "--", "T.DMG")


def test_koly_au_trailer_sans_suffixe(atelier: Atelier) -> None:
    atelier.fichier("y.bin", _koly())
    sortie = atelier.refus("decision_requise", "run", "inspect-artifact", "--", "y.bin")
    assert "contenu" in sortie["detail"], sortie


def test_xar_en_tete_sans_suffixe(atelier: Atelier) -> None:
    atelier.fichier("z.bin", b"xar!" + bytes(64))
    atelier.refus("decision_requise", "run", "inspect-artifact", "--", "z.bin")


def test_dmg_en_second_positionnel(atelier: Atelier) -> None:
    a, b = atelier.fichier("a.json", b"{}"), atelier.fichier("b.dmg", b"rien")
    atelier.refus("decision_requise", "run", "compare", "--", str(a), str(b))


def test_pkg_au_fond_d_un_app(atelier: Atelier) -> None:
    atelier.fichier("A.app/Contents/n/x.pkg", b"rien")
    atelier.refus("decision_requise", "run", "inspect-artifact", "--", "A.app")


def test_lien_en_cycle_dans_un_app_termine(atelier: Atelier) -> None:
    atelier.fichier("A.app/Contents/MacOS/A")
    (atelier.appelant / "A.app" / "Contents" / "boucle").symlink_to("..")
    atelier.ok("run", "inspect-artifact", "--", "A.app")


def test_lien_sortant_d_un_app_ignore(atelier: Atelier) -> None:
    """C33/C36 : `h` pointe un répertoire CONTRÔLÉ hors du bundle qui porte un `x.dmg` sans koly."""
    dehors = atelier.racine / "dehors"
    dehors.mkdir()
    (dehors / "x.dmg").write_bytes(b"rien")
    atelier.fichier("A.app/Contents/MacOS/A")
    (atelier.appelant / "A.app" / "Contents" / "h").symlink_to(dehors)
    atelier.ok("run", "inspect-artifact", "--", "A.app")


def test_app_au_dela_de_la_borne(atelier: Atelier, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rea_run, "BORNE_INVENTAIRE", 5)
    for i in range(6):
        atelier.fichier(f"A.app/f{i}")
    atelier.refus("inventaire_trop_grand", "run", "inspect-artifact", "--", "A.app")


def test_repertoire_hors_app_non_parcouru(atelier: Atelier) -> None:
    atelier.fichier("plat/x.dmg", b"rien")
    atelier.ok("run", "inspect-artifact", "--", "plat")


def test_dmg_admis_sous_decision_qui_nomme_le_lien_ou_sa_cible(atelier: Atelier) -> None:
    atelier.fichier("x.dmg", b"aucune signature")
    (atelier.appelant / "t.bin").symlink_to("x.dmg")
    atelier.decision(D8, "inspect-artifact sur t.bin, possede par le pilote")
    atelier.ok("run", "--decision", D8, "inspect-artifact", "--", "t.bin")
    atelier.decision(ULID, "inspect-artifact sur x.dmg, possede par le pilote")
    atelier.ok("run", "--decision", ULID, "inspect-artifact", "--", "t.bin")


# --- C28 : jeton vide, `{` réservé à inputJson -------------------------------------------------------
def test_jeton_vide(atelier: Atelier) -> None:
    atelier.refus("jeton_vide", "run", "inspect-macho", "--", "")


def test_accolade_sur_path_est_un_chemin(atelier: Atelier) -> None:
    atelier.ok("run", "inspect-macho", "--", "{x")
    assert atelier.argv_rea()[1] == os.path.join(os.getcwd(), "{x")


def test_json_en_ligne_sur_input_json_laisse_tel_quel(atelier: Atelier) -> None:
    requete = '{"source":{"kind":"inline","evidence":{}},"view":{"kind":"summary"}}'
    atelier.ok("run", "inspect-analysis-view", "--", requete)
    assert atelier.argv_rea()[1] == requete


# --- options sous décision, out_suivi, cible --------------------------------------------------------------
@pytest.mark.parametrize("opts", [["--snapshot", "snap"], ["--snapshot=snap"], ["--provider=ghidra"]])
def test_option_sous_decision_sans_decision(atelier: Atelier, opts: list[str]) -> None:
    atelier.refus("decision_requise", "run", "decompile", "--", str(atelier.fichier("f.bin")), *opts)


def test_snapshot_dans_le_depot_espace(atelier: Atelier) -> None:
    atelier.decision(D8, "decompile de f.bin avec --snapshot")
    atelier.refus("out_suivi", "run", "--decision", D8, "decompile", "--", str(atelier.fichier("f.bin")),
                  "--snapshot", str(ROOT / "src" / "x"))


def test_snapshot_a_segment_parent_avant_out_suivi(atelier: Atelier) -> None:
    atelier.decision(D8, "decompile de f.bin avec --snapshot")
    atelier.refus("segment_parent", "run", "--decision", D8, "decompile", "--", str(atelier.fichier("f.bin")),
                  "--snapshot=../../src/x")


def test_snapshot_admis_sous_decision(atelier: Atelier) -> None:
    atelier.decision(D8, "decompile de f.bin avec --snapshot")
    atelier.ok("run", "--decision", D8, "decompile", "--", str(atelier.fichier("f.bin")), "--snapshot=snap")
    assert f"--snapshot={os.path.join(os.getcwd(), 'snap')}" in atelier.argv_rea()


def test_out_dans_le_depot(atelier: Atelier) -> None:
    out = ROOT / "src" / "zz-rea-out"
    atelier.refus("out_suivi", "run", "--out", str(out), "inspect-macho", "--", str(atelier.fichier("f.bin")))
    assert not out.exists()


def test_cible_apres_la_valeur_d_une_option(atelier: Atelier) -> None:
    sortie = atelier.ok("run", "decompile", "--", "--procedure", "main", "/abs/bin")
    assert sortie["cible"] == "bin"


def test_hors_liste_sans_decision(atelier: Atelier) -> None:
    atelier.refus("decision_requise", "run", "analyze-web-bundle", "--", str(atelier.fichier("f.bin")))


def test_hors_liste_decision_qui_ne_nomme_pas_l_option(atelier: Atelier) -> None:
    atelier.decision(D8, "analyze-web-bundle sur f.bin")
    atelier.refus("decision_ne_nomme_pas_l_option", "run", "--decision", D8, "--cible", "f.bin",
                  "analyze-web-bundle", "--", str(atelier.fichier("f.bin")), "--foo=1")


def test_hors_liste_decision_complete(atelier: Atelier) -> None:
    atelier.decision(D8, "analyze-web-bundle sur f.bin avec --foo")
    f = str(atelier.fichier("f.bin"))
    atelier.ok("run", "--decision", D8, "--cible", "f.bin", "analyze-web-bundle", "--", f, "--foo=1")
    assert atelier.argv_rea() == ["analyze-web-bundle", f, "--foo=1", "--format", "json"]


def test_hors_liste_builtin_refuse_meme_sous_decision(atelier: Atelier) -> None:
    atelier.decision(D8, "analyze-web-bundle sur f.bin avec --mcp")
    atelier.refus("option_refusee", "run", "--decision", D8, "--cible", "f.bin", "analyze-web-bundle", "--",
                  str(atelier.fichier("f.bin")), "--mcp")


# --- décisions --------------------------------------------------------------------------------------------
def _dmg(atelier: Atelier) -> None:
    atelier.fichier("x.dmg", b"rien")


def test_decision_forme(atelier: Atelier) -> None:
    _dmg(atelier)
    atelier.refus("decision_forme", "run", "--decision", "S-123", "inspect-artifact", "--", "x.dmg")


def test_decision_introuvable(atelier: Atelier) -> None:
    _dmg(atelier)
    atelier.refus("decision_introuvable", "run", "--decision", "S-99999999", "inspect-artifact", "--", "x.dmg")


def test_decision_pas_une_decision(atelier: Atelier) -> None:
    _dmg(atelier)
    atelier.decision(D8, "inspect-artifact sur x.dmg", kind="note")
    atelier.refus("decision_pas_une_decision", "run", "--decision", D8, "inspect-artifact", "--", "x.dmg")


def test_decision_sans_cible(atelier: Atelier) -> None:
    _dmg(atelier)
    atelier.decision(D8, "inspect-artifact sur un autre fichier")
    atelier.refus("decision_ne_nomme_pas_la_cible", "run", "--decision", D8, "inspect-artifact", "--", "x.dmg")


def test_decision_sans_operation(atelier: Atelier) -> None:
    _dmg(atelier)
    atelier.decision(D8, "analyse de x.dmg")
    atelier.refus("decision_ne_nomme_pas_l_operation", "run", "--decision", D8, "inspect-artifact", "--",
                  "x.dmg")


@pytest.mark.parametrize("ident", [D8, ULID])
def test_decision_huit_chiffres_ou_ulid(atelier: Atelier, ident: str) -> None:
    _dmg(atelier)
    atelier.decision(ident, "inspect-artifact sur x.dmg")
    atelier.ok("run", "--decision", ident, "inspect-artifact", "--", "x.dmg")


# --- stdin, env, cwd -----------------------------------------------------------------------------------------
def test_stdin_ferme(atelier: Atelier) -> None:
    f = str(atelier.fichier("f.bin"))
    proc = subprocess.run([sys.executable, str(SCRIPT), "run", "inspect-macho", "--", f], input="SECRET\n",
                          capture_output=True, text=True, timeout=120, cwd=atelier.appelant, check=False)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert atelier.appels()[0]["stdin_devnull"] is True


def test_env_par_liste_blanche(atelier: Atelier) -> None:
    atelier.ok("run", "inspect-macho", "--", str(atelier.fichier("f.bin")))
    env = atelier.appels()[0]["env"]
    assert not set(CANARIS) & set(env), sorted(env)
    assert (env.get("npm_config_omit"), env.get("npm_config_prefer_offline")) == ("optional", "true")


def test_moteurs_sans_decision(atelier: Atelier) -> None:
    atelier.refus("decision_requise", "run", "--moteurs", "inspect-macho", "--", str(atelier.fichier("f.bin")))


def test_with_optional_sans_decision(atelier: Atelier) -> None:
    atelier.refus("decision_requise", "run", "--with-optional", "inspect-macho", "--",
                  str(atelier.fichier("f.bin")))


def test_moteurs_par_defaut_neutralises(atelier: Atelier, monkeypatch: pytest.MonkeyPatch) -> None:
    """Revue de clôture F1 : sans `--moteurs`, Hopper et Ghidra pointent sur un chemin absent — rea ne les
    découvre pas seul dans l'environnement du poste."""
    monkeypatch.setenv("HOPPER_LAUNCHER_PATH", "/x/hopper")
    monkeypatch.setenv("GHIDRA_INSTALL_DIR", "/x/ghidra")
    atelier.ok("run", "inspect-macho", "--", str(atelier.fichier("f.bin")))
    env = atelier.appels()[0]["env"]
    assert env.get("HOPPER_LAUNCHER_PATH") == rea_run.SENTINELLE_MOTEURS + "/hopper", env
    assert env.get("GHIDRA_INSTALL_DIR") == rea_run.SENTINELLE_MOTEURS, env
    assert not os.path.exists(rea_run.SENTINELLE_MOTEURS)


def test_moteurs_sous_decision_passent_les_variables(atelier: Atelier) -> None:
    atelier.decision(D8, "inspect-macho de f.bin avec --moteurs")
    atelier.ok("run", "--decision", D8, "--moteurs", "inspect-macho", "--", str(atelier.fichier("f.bin")))
    env = atelier.appels()[0]["env"]
    assert env.get("REA_KUNA_COMMAND") == "/x/kuna" and "ZZ_CANARY" not in env


# --- sortie, trace, rc 1 -------------------------------------------------------------------------------------
def test_une_ligne_json_evidence_et_trace(atelier: Atelier) -> None:
    sortie = atelier.ok("run", "inspect-macho", "--", str(atelier.fichier("f.bin")))
    assert set(sortie) == {"rc", "chemin", "sha256", "taille", "motif", "rc_rea", "cible", "commande"}, sortie
    evidence = Path(sortie["chemin"])
    octets = evidence.read_bytes()
    assert json.loads(octets) == {"provider": {"id": "faux"}}
    assert (sortie["sha256"], sortie["taille"]) == (hashlib.sha256(octets).hexdigest(), len(octets))
    assert evidence.parent == atelier.etat
    trace = [json.loads(l) for l in (atelier.etat / "runs.jsonl").read_text(encoding="utf-8").splitlines()]
    assert (trace[-1]["rc"], trace[-1]["chemin"]) == (0, sortie["chemin"])
    assert "fuite" not in (atelier.etat / "runs.jsonl").read_text(encoding="utf-8")


def test_refus_trace(atelier: Atelier) -> None:
    atelier.refus("positionnel_en_trop", "run", "inspect-macho", "--", "/a", "/b")
    trace = [json.loads(l) for l in (atelier.etat / "runs.jsonl").read_text(encoding="utf-8").splitlines()]
    assert (trace[-1]["rc"], trace[-1]["motif"]) == (2, "positionnel_en_trop")


def test_rea_non_zero_rend_un(atelier: Atelier) -> None:
    atelier.conf(rc=3)
    rc, sortie = atelier.run("run", "inspect-macho", "--", str(atelier.fichier("f.bin")))
    assert (rc, sortie["motif"]) == (1, "rea_non_zero")


# --- vue ---------------------------------------------------------------------------------------------------
def test_vue_ecrit_une_requete_inline(atelier: Atelier) -> None:
    ev = {"provider": {"id": "rea-javascript-application"}}
    atelier.fichier("e.json", json.dumps(ev).encode())
    atelier.ok("vue", "e.json")
    argv = atelier.argv_rea()
    assert argv[0] == "inspect-analysis-view" and argv[-2:] == ["--format", "json"]
    requete = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    assert requete == {"source": {"kind": "inline", "evidence": ev}, "view": {"kind": "summary"}}


def test_vue_evidence_illisible(atelier: Atelier) -> None:
    atelier.fichier("e.json", b"{pas du json")
    atelier.refus("evidence_illisible", "vue", "e.json")


# --- probe -------------------------------------------------------------------------------------------------
DOCTOR = {"checks": [{"name": "hopper", "ok": True, "classification": "healthy"},
                     {"name": "ghidra", "ok": False, "classification": "missing_analysis_engine"}]}


def test_probe_doctor_rc_un_avec_json(atelier: Atelier) -> None:
    atelier.conf(doctor=DOCTOR, doctor_rc=1)
    rc, sortie = atelier.run("probe")
    assert rc == 0, sortie
    assert (sortie["rea"], sortie["doctor_rc"], sortie["moteurs_presents"], sortie["moteurs_absents_env_retiree"]) == (
        "6.7.0", 1, ["hopper"], ["ghidra"])


def test_probe_moteurs(atelier: Atelier) -> None:
    atelier.conf(doctor=DOCTOR, doctor_rc=1)
    rc, sortie = atelier.run("probe", "--moteurs")
    assert (rc, sortie["moteurs_absents"]) == (0, ["ghidra"])
    assert atelier.appels()[-1]["env"].get("REA_KUNA_COMMAND") == "/x/kuna"


@pytest.mark.parametrize("conf,cause", [({"node": "v20.0.0"}, "node"), ({"version": "6.6.0"}, "6.6.0")])
def test_probe_degrade(atelier: Atelier, conf: dict, cause: str) -> None:
    atelier.conf(doctor=DOCTOR, **conf)
    rc, sortie = atelier.run("probe")
    assert rc == 3 and cause in sortie["motif"], sortie


def test_run_node_hors_plage_degrade_avant_npx(atelier: Atelier) -> None:
    """E7 : la porte node de `probe` vaut aussi pour `run`, avant tout lancement de npx."""
    atelier.conf(node="v20.0.0")
    rc, sortie = atelier.run("run", "inspect-macho", "--", str(atelier.fichier("f.bin")))
    assert rc == 3 and "node v20.0.0 hors plage" in sortie["motif"], sortie
    assert atelier.appels() == [], "npx lancé malgré node hors plage"


def test_run_node_absent_degrade(atelier: Atelier) -> None:
    (atelier.bin / "node").unlink()
    rc, sortie = atelier.run("run", "inspect-macho", "--", str(atelier.fichier("f.bin")))
    assert (rc, sortie["motif"]) == (3, "node absent du PATH"), sortie
    assert atelier.appels() == []


def test_vue_node_hors_plage_degrade(atelier: Atelier) -> None:
    atelier.conf(node="v20.0.0")
    atelier.fichier("e.json", b'{"provider": {"id": "x"}}')
    rc, sortie = atelier.run("vue", "e.json")
    assert rc == 3 and "hors plage" in sortie["motif"] and atelier.appels() == [], sortie


def test_probe_npx_absent(atelier: Atelier) -> None:
    (atelier.bin / "npx").unlink()
    rc, sortie = atelier.run("probe")
    assert rc == 3 and "npx" in sortie["motif"], sortie


@pytest.mark.parametrize("version,admis", [("v22.19.0", True), ("v22.18.9", False), ("v24.11.0", True),
                                           ("v24.10.9", False), ("v25.9.0", False), ("v26.0.0", True),
                                           ("v23.0.0", False), ("pas une version", False)])
def test_plage_node(version: str, admis: bool) -> None:
    assert rea_run.node_admis(version) is admis


# --- délai et signaux : le groupe entier meurt ------------------------------------------------------------
def _mort(pid: int, delai: float = 10.0) -> bool:
    fin = time.monotonic() + delai
    while time.monotonic() < fin:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.1)
    return False


def _tuer_survivant(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def test_delai_tue_le_petit_enfant(atelier: Atelier) -> None:
    pidf = atelier.racine / "petit.pid"
    atelier.conf(dort=60, petit_enfant=str(pidf), ecrit_avant='{"partial": ')
    rc, sortie = atelier.run("run", "--timeout", "2", "inspect-macho", "--", str(atelier.fichier("f.bin")))
    pid = int(pidf.read_text(encoding="utf-8"))
    try:
        assert (rc, sortie["motif"]) == (3, "delai"), sortie
        assert _mort(pid), "petit-enfant survivant au délai"
        # Revue de clôture F3 : l'Evidence tronquée ne garde jamais le nom d'une Evidence complète.
        assert list(atelier.etat.glob("*-inspect-macho.json")) == [], "Evidence tronquée sous un nom complet"
        partiels = list(atelier.etat.glob("*-inspect-macho.json.partiel"))
        assert len(partiels) == 1 and partiels[0].read_bytes() == b'{"partial": ', partiels
        assert _trace(atelier)[-1]["evidence_partielle"] == str(partiels[0])
    finally:
        _tuer_survivant(pid)


def test_sigterm_rend_trois_et_tue_le_groupe(atelier: Atelier) -> None:
    pidf = atelier.racine / "petit.pid"
    atelier.conf(dort=60, petit_enfant=str(pidf))
    proc = subprocess.Popen([sys.executable, str(SCRIPT), "run", "inspect-macho", "--",
                             str(atelier.fichier("f.bin"))], cwd=atelier.appelant, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True)
    fin = time.monotonic() + 30
    while not pidf.exists() and time.monotonic() < fin:
        time.sleep(0.1)
    time.sleep(0.3)
    pid = int(pidf.read_text(encoding="utf-8"))
    try:
        proc.send_signal(signal.SIGTERM)
        out, _err = proc.communicate(timeout=60)
        sortie = json.loads(out.strip().splitlines()[-1])
        assert (proc.returncode, sortie["motif"]) == (3, "interrompu: SIGTERM"), sortie
        assert _mort(pid), "petit-enfant survivant au SIGTERM"
    finally:
        proc.kill()
        _tuer_survivant(pid)


# --- passe de correction : S1, S2, E1, E2, E3, valeur ʳ relative, vue bornée, budget de probe ---------------
def _nettoyer(chemin: Path) -> None:
    """Retire ce qu'un MUTANT aurait écrit dans le dépôt ; vert, le témoin n'y crée rien."""
    if chemin.exists():
        shutil.rmtree(chemin, ignore_errors=True)


RACINE_EN_CASSE = ROOT.parent / ROOT.name.swapcase()
CASSE_INSENSIBLE = ROOT.name.swapcase() != ROOT.name and RACINE_EN_CASSE.exists()


@pytest.mark.skipif(not CASSE_INSENSIBLE, reason=f"SAUT ANNONCE : volume sensible à la casse (mesuré : "
                                                 f"{RACINE_EN_CASSE} absent) — S1 non jugeable ici")
def test_out_dans_le_depot_en_casse_alteree(atelier: Atelier) -> None:
    """S1 : APFS insensible à la casse — la même racine sous une autre casse est le dépôt."""
    temoin = ROOT / "src" / "zz-rea-casse"
    try:
        atelier.refus("out_suivi", "run", "--out", str(RACINE_EN_CASSE / "src" / "zz-rea-casse"), "inspect-macho",
                      "--", str(atelier.fichier("f.bin")))
        assert not temoin.exists()
    finally:
        _nettoyer(temoin)


def test_out_par_un_lien_vers_le_depot(atelier: Atelier) -> None:
    """E2 (M11) : `lien -> <dépôt>/src`, `--out lien/zz` ⇒ `out_suivi`."""
    (atelier.appelant / "lien").symlink_to(ROOT / "src")
    temoin = ROOT / "src" / "zz-rea-lien"
    try:
        atelier.refus("out_suivi", "run", "--out", "lien/zz-rea-lien", "inspect-macho", "--",
                      str(atelier.fichier("f.bin")))
    finally:
        _nettoyer(temoin)


def test_out_dans_le_checkout_principal(atelier: Atelier, monkeypatch: pytest.MonkeyPatch) -> None:
    """E3 : depuis un worktree lié, le checkout principal (`--git-common-dir`) est aussi le dépôt."""
    principal = atelier.racine / "principal"
    (principal / "src").mkdir(parents=True)
    monkeypatch.setattr(rea_run, "racine_principale", lambda _racine: principal)
    atelier.refus("out_suivi", "run", "--out", str(principal / "src" / "zz"), "inspect-macho", "--",
                  str(atelier.fichier("f.bin")))
    assert not (principal / "src" / "zz").exists()


@pytest.mark.skipif(shutil.which("git") is None, reason="SAUT ANNONCE : git absent du PATH")
def test_racine_principale_d_un_worktree_lie(tmp_path: Path) -> None:
    principal, lie = tmp_path / "principal", tmp_path / "lie"
    git = ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", "-c", "user.name=t",
           "-c", "user.email=t@t.invalid"]
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    for args in (["init", "-q", str(principal)], ["-C", str(principal), "commit", "-q", "--allow-empty", "-m", "x"],
                 ["-C", str(principal), "worktree", "add", "-q", str(lie)]):
        subprocess.run([*git, *args], check=True, capture_output=True, timeout=60, env=env)
    assert os.path.samefile(rea_run.racine_principale(lie), principal)
    assert os.path.samefile(rea_run.racine_principale(principal), principal)


def test_npmrc_de_la_sortie_non_lu(atelier: Atelier) -> None:
    """S2 : npx tourne dans un cwd temporaire VIDE, jamais dans `--out` ; l'Evidence reste dans `--out`."""
    sortie_dir = atelier.racine / "sortie"
    sortie_dir.mkdir()
    (sortie_dir / ".npmrc").write_text("registry=http://127.0.0.1:9/\n", encoding="utf-8")
    (sortie_dir / "node_modules").mkdir()
    sortie = atelier.ok("run", "--out", str(sortie_dir), "inspect-macho", "--", str(atelier.fichier("f.bin")))
    appel = atelier.appels()[0]
    assert appel["cwd"] != os.path.realpath(sortie_dir), appel["cwd"]
    assert (appel["npmrc_dans_cwd"], appel["cwd_vide"]) == (False, True)
    assert not os.path.exists(appel["cwd"]), "le cwd temporaire doit être supprimé"
    assert Path(sortie["chemin"]).parent == sortie_dir


def _trace(atelier: Atelier) -> list[dict]:
    return [json.loads(l) for l in (atelier.etat / "runs.jsonl").read_text(encoding="utf-8").splitlines()]


def test_surcharge_specs_tracee(atelier: Atelier, monkeypatch: pytest.MonkeyPatch) -> None:
    """E1 : la décision lue sous `AGENTS_SPECS_PATH` porte sa marque dans `runs.jsonl` ; sans surcharge, non."""
    _dmg(atelier)
    atelier.decision(D8, "inspect-artifact sur x.dmg")
    sortie = atelier.ok("run", "--decision", D8, "inspect-artifact", "--", "x.dmg")
    assert _trace(atelier)[-1]["decision_lue"]["specs_surcharge"] is True
    assert sortie["specs_surcharge"] is True and "AGENTS_SPECS_PATH" in atelier.erreurs, (sortie, atelier.erreurs)
    monkeypatch.delenv("AGENTS_SPECS_PATH")
    entree = {"id": D8, "kind": "decision", "title": "t", "text": "inspect-artifact sur x.dmg"}
    monkeypatch.setattr(rea_run, "chemin_specs", lambda: Path("journal-du-depot"))
    monkeypatch.setattr(rea_run, "_entrees_specs", lambda _chemin: [entree])
    sortie = atelier.ok("run", "--decision", D8, "inspect-artifact", "--", "x.dmg")
    assert _trace(atelier)[-1]["decision_lue"]["specs_surcharge"] is False
    assert sortie["specs_surcharge"] is False and "AGENTS_SPECS_PATH" not in atelier.erreurs


def test_valeur_chemin_appelant_en_dmg(atelier: Atelier) -> None:
    """E2 (M26) : une valeur ᶜ en `.dmg` exige une décision."""
    atelier.fichier("x.dmg", b"rien")
    atelier.refus("decision_requise", "run", "doctor", "--", "--target=x.dmg")
    atelier.refus("decision_requise", "run", "inspect-wasm-artifact", "--", str(atelier.fichier("f.wasm")),
                  "--glue_paths=x.dmg")


def test_valeur_racine_absolue_en_dmg(atelier: Atelier) -> None:
    """E2 (M17) : une valeur ʳ absolue en `.dmg` exige une décision."""
    d = atelier.appelant / "app"
    d.mkdir()
    atelier.refus("decision_requise", "run", "analyze-javascript-application", "--", str(d),
                  f"--source-path={atelier.racine}/x.dmg")


def test_valeur_racine_relative_en_dmg(atelier: Atelier) -> None:
    """Lecture stricte du contrat : une valeur ʳ relative est jugée jointe au cwd appelant, passée telle quelle."""
    d = atelier.appelant / "app"
    d.mkdir()
    atelier.refus("decision_requise", "run", "analyze-javascript-application", "--", str(d), "--source-path=x.dmg")


def test_builtin_camel_refuse_sous_commande_hors_liste(atelier: Atelier) -> None:
    """E2 (M15) : `--tokenLimit=5` est `--token-limit`, builtin refusé même hors liste et sous décision."""
    atelier.decision(D8, "analyze-web-bundle sur f.bin avec --token-limit")
    atelier.refus("option_refusee", "run", "--decision", D8, "--cible", "f.bin", "analyze-web-bundle", "--",
                  str(atelier.fichier("f.bin")), "--tokenLimit=5")


def test_vue_trop_grande(atelier: Atelier, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rea_run, "BORNE_VUE", 16)
    atelier.fichier("e.json", json.dumps({"provider": {"id": "x" * 32}}).encode())
    atelier.refus("vue_trop_grande", "vue", "e.json")


def test_probe_budget_partage(atelier: Atelier, monkeypatch: pytest.MonkeyPatch) -> None:
    """E6/F2 : node, `--version` et `doctor` partagent UN budget (`DELAI_DEFAUT_S`) ; chaque étape est bornée
    par ce qui en RESTE — `--version` qui dort 8 s est tuée vers 2 s, jamais attendue."""
    monkeypatch.setattr(rea_run, "DELAI_DEFAUT_S", 2)
    atelier.conf(doctor=DOCTOR, dort=8)
    debut = time.monotonic()
    rc, sortie = atelier.run("probe")
    assert (rc, sortie["motif"]) == (3, "delai"), sortie
    assert time.monotonic() - debut < 6, "une étape de probe a dépassé le reste du budget"


# --- seconde passe de correction : F1, F3, F5, avis (a) à (f) ----------------------------------------------
@pytest.mark.parametrize("cmd,args", [("rea", ["mcp", "add"]), ("rea", ["skills", "add"]), ("rea", ["skill", "add"]),
                                      ("rea", ["completions", "zsh"]), ("skill", ["add"])])
def test_aiguillage_incur_vers_un_builtin_refuse_sous_decision_valide(atelier: Atelier, cmd: str,
                                                                     args: list[str]) -> None:
    """F1 : incur aiguille `rea <builtin>` et l'alias `skill` vers ses builtins ; refusés même sous décision."""
    atelier.decision(D8, f"{cmd} {' '.join(args)} autorise, cible {args[-1]}, options --mcp")
    atelier.refus("commande_refusee", "run", "--decision", D8, "--cible", args[-1], cmd, "--", *args)


def test_valeur_racine_relative_jugee_depuis_la_racine_de_l_application(atelier: Atelier) -> None:
    """F3 : rea résout `--source-path` depuis la racine de l'application, pas depuis le cwd appelant."""
    atelier.fichier("app/lib.js", _koly())
    atelier.refus("decision_requise", "run", "analyze-javascript-application", "--", "app", "--source-path=lib.js")


def test_valeur_racine_relative_sans_rapport_avec_le_cwd(atelier: Atelier) -> None:
    """F3 : un `main.js` koly du cwd appelant n'est pas celui que rea lira (faux positif d'avant)."""
    atelier.fichier("main.js", _koly())
    atelier.fichier("app/package.json", b"{}")
    atelier.ok("run", "analyze-javascript-application", "--", "app", "--source-path=main.js")


def test_porte_node_et_preparation_dans_le_delai(atelier: Atelier) -> None:
    """F5 : le délai court depuis le début de la commande ; la porte node le consomme, rea reçoit le reste."""
    pidf = atelier.racine / "petit.pid"
    atelier.conf(node_dort=4, dort=30, petit_enfant=str(pidf))
    debut = time.monotonic()
    rc, sortie = atelier.run("run", "--timeout", "6", "inspect-macho", "--", str(atelier.fichier("f.bin")))
    ecoule = time.monotonic() - debut
    try:
        assert (rc, sortie["motif"]) == (3, "delai"), sortie
        assert ecoule < 8.5, f"{ecoule:.1f} s : rea a reçu tout le délai en plus de la porte node"
    finally:
        if pidf.exists():
            _tuer_survivant(int(pidf.read_text(encoding="utf-8")))


def test_racines_du_depot_une_fois_par_invocation(atelier: Atelier, monkeypatch: pytest.MonkeyPatch) -> None:
    """F5 : `racines_depot` est mémorisé par invocation (sortie, snapshot et trace ne relisent pas)."""
    appels = []
    monkeypatch.setattr(rea_run, "racine_principale", lambda racine: appels.append(racine) or None)
    atelier.ok("run", "inspect-macho", "--", str(atelier.fichier("f.bin")))
    assert len(appels) == 1, appels
    atelier.ok("run", "inspect-macho", "--", str(atelier.fichier("f.bin")))
    assert len(appels) == 2, "la mémoire doit être vidée entre deux invocations"


def test_tmpdir_sous_un_projet_npm(atelier: Atelier, monkeypatch: pytest.MonkeyPatch) -> None:
    """(a) : un `TMPDIR` posé sous un projet npm ferait lire son `.npmrc` ; le cwd de npx en sort."""
    hostile = atelier.racine / "hostile"
    (hostile / "t").mkdir(parents=True)
    (hostile / "package.json").write_text("{}", encoding="utf-8")
    (hostile / ".npmrc").write_text("registry=http://127.0.0.1:9/\n", encoding="utf-8")
    monkeypatch.setattr(tempfile, "tempdir", str(hostile / "t"))
    atelier.ok("run", "inspect-macho", "--", str(atelier.fichier("f.bin")))
    cwd = atelier.appels()[0]["cwd"]
    assert not cwd.startswith(os.path.realpath(hostile)), cwd
    assert "projet npm" in atelier.erreurs


def test_vue_refuse_un_fichier_irregulier(atelier: Atelier) -> None:
    """(b) : `/dev/null` (ou `/dev/zero`, une FIFO) contournerait la borne par `st_size`."""
    atelier.refus("evidence_irreguliere", "vue", os.devnull)


def test_racine_principale_refuse_un_gitdir_incoherent(tmp_path: Path) -> None:
    """(c) : `.git` qui renvoie vers un répertoire commun sans `HEAD`, ou dont le gitdir n'est pas sous
    `<commun>/worktrees/`, ne désigne aucun checkout principal."""
    racine, gitdir = tmp_path / "racine", tmp_path / "g"
    racine.mkdir()
    gitdir.mkdir()
    (racine / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")
    (gitdir / "HEAD").write_text("ref: refs/heads/x\n", encoding="utf-8")
    (gitdir / "commondir").write_text("/etc\n", encoding="utf-8")
    assert rea_run.racine_principale(racine) is None
    autre = tmp_path / "autre" / ".git"
    (autre / "worktrees").mkdir(parents=True)
    (autre / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (gitdir / "commondir").write_text(f"{autre}\n", encoding="utf-8")
    assert rea_run.racine_principale(racine) is None


def test_node_version_bavarde_refusee(atelier: Atelier) -> None:
    """(e) : la sortie de `node --version` est lue sur 256 octets au plus."""
    atelier.conf(node="v24.11.0" + "x" * 300)
    rc, sortie = atelier.run("run", "inspect-macho", "--", str(atelier.fichier("f.bin")))
    assert rc == 3 and "256" in sortie["motif"], sortie


def test_porte_node_petit_enfant_qui_tient_le_tube(atelier: Atelier) -> None:
    """3e passe : un petit-enfant de `node --version` qui hérite du tube ne retient ni la porte ni le délai ;
    il meurt avec le groupe, et le motif dit « sans réponse », jamais « hors plage »."""
    pidf = atelier.racine / "petit-node.pid"
    (atelier.bin / "node").write_text(f"#!/bin/sh\n/bin/sleep 30 &\necho $! > '{pidf}'\nwait\n", encoding="utf-8")
    debut = time.monotonic()
    rc, sortie = atelier.run("run", "--timeout", "3", "inspect-macho", "--", str(atelier.fichier("f.bin")))
    ecoule = time.monotonic() - debut
    pid = int(pidf.read_text(encoding="utf-8"))
    try:
        assert rc == 3 and "sans réponse" in sortie["motif"], sortie
        assert ecoule < 8, f"{ecoule:.1f} s : la porte node a attendu le petit-enfant"
        assert _mort(pid), "petit-enfant de node survivant à la porte"
        assert atelier.appels() == [], "npx lancé malgré la porte node en échec"
    finally:
        _tuer_survivant(pid)


@pytest.mark.skipif(not os.access("/usr/bin/perl", os.X_OK), reason="SAUT ANNONCE : /usr/bin/perl absent")
def test_porte_node_petit_enfant_hors_du_groupe(atelier: Atelier) -> None:
    """Revue de clôture K3 : un petit-enfant SORTI du groupe (`setsid`) tient le tube, `killpg` ne l'atteint
    pas ; la porte rend « sans réponse » sans fermer le tube sous le `read()` en cours (sinon elle attend
    sa mort, ~30 s)."""
    pidf = atelier.racine / "hors-groupe.pid"
    perl = "use POSIX; setsid(); open(F, \">\", $ARGV[0]); print F \"$$ \", getpgrp(); close F; sleep 30"
    (atelier.bin / "node").write_text(f"#!/bin/sh\n/usr/bin/perl -e '{perl}' '{pidf}' &\nwait\n",
                                      encoding="utf-8")
    debut = time.monotonic()
    rc, sortie = atelier.run("run", "--timeout", "3", "inspect-macho", "--", str(atelier.fichier("f.bin")))
    ecoule = time.monotonic() - debut
    pid, groupe = (int(x) for x in pidf.read_text(encoding="utf-8").split())
    try:
        assert groupe == pid, "le petit-enfant n'est pas sorti du groupe : le témoin ne prouve rien"
        assert rc == 3 and "sans réponse" in sortie["motif"], sortie
        assert ecoule < 15, f"{ecoule:.1f} s : la porte node a attendu le petit-enfant hors du groupe"
        assert atelier.appels() == [], "npx lancé malgré la porte node en échec"
    finally:
        _tuer_survivant(pid)


def test_snapshot_vers_un_lien_dur(atelier: Atelier) -> None:
    """(f) : un fichier à plusieurs liens durs peut être un fichier suivi vu d'ailleurs."""
    suivi = ROOT / "AGENTS.md"
    lien = atelier.racine / "lien-dur"
    try:
        os.link(suivi, lien)
    except OSError as e:
        pytest.skip(f"SAUT ANNONCE : lien dur impossible vers {suivi} ({type(e).__name__})")
    atelier.decision(D8, "decompile de f.bin avec --snapshot")
    atelier.refus("out_suivi", "run", "--decision", D8, "decompile", "--", str(atelier.fichier("f.bin")),
                  f"--snapshot={lien}")


# --- forme du fichier ------------------------------------------------------------------------------------
def test_moins_de_1600_lignes() -> None:
    assert SCRIPT.read_bytes().count(b"\n") < 1600
