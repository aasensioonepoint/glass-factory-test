"""Banc du générateur `hooks_jumeaux.py` (T-01M4V7R5H0HE0Z5TPJ4Q64VMPF, lot G, étape 7 du plan).

Arbres SYNTHÉTIQUES sous `tmp_path` seulement : aucun témoin ne lit `.codex/hooks` ni `.gemini/hooks` du dépôt, l'état
des hooks réels ne change aucun verdict. Les chemins `.codex/hooks` et `.gemini/hooks` sont écrits EN DUR ici, jamais
lus de `JUMEAUX` : un tuple déplacé rougit.

Chaque témoin nomme dans sa docstring le mutant qu'il tue (M1-M16, table « Tests » du plan pour M1-M6) :
  M1 comparaison par taille ; M2 `--ecrire` qui supprime un orphelin ; M3 exclusion `test_*` retirée ; M4 source vide
  qui rend rc 0 ; M5 lien symbolique accepté ; M6 passe qui réécrit un fichier identique ; M7 `--ecrire` par défaut ;
  M8 écriture sans temporaire ; M9 écriture avant le constat ; M10 aucune reprise sur `PermissionError` ; M11 mode
  source non recopié ; M12 listage récursif ; M13 racine par défaut tirée du dossier courant ; M14 temporaire laissé
  après un échec ; M15 contrôle de realpath retiré ; M16 point d'entrée sans `sys.exit(main())`.
BORNE de M15 : un lien qui sort de la racine est AUSSI refusé par le contrôle des liens ; le témoin de M15 fixe la
RAISON du refus (`hors de la racine`), pas un refus que seul le realpath porterait — avec le tuple fermé, il n'en
existe pas.
"""

from __future__ import annotations

import importlib.util
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ICI = Path(__file__).resolve().parent
_SPEC = importlib.util.spec_from_file_location("hooks_jumeaux", ICI / "hooks_jumeaux.py")
assert _SPEC is not None and _SPEC.loader is not None
HJ = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = HJ
_SPEC.loader.exec_module(HJ)

SOURCE = ".codex/hooks"
CIBLE = ".gemini/hooks"
PASSE_NS = 1_000_000_000 * 1_000_000_000  # 2001-09-09 : un mtime qu'aucune réécriture ne reproduit


@pytest.fixture
def racine(tmp_path: Path) -> Path:
    depot = tmp_path / "depot"
    depot.mkdir()
    return depot


def poser(racine: Path, relatif: str, fichiers: dict[str, bytes]) -> Path:
    dossier = racine / relatif
    dossier.mkdir(parents=True, exist_ok=True)
    for nom, octets in fichiers.items():
        (dossier / nom).write_bytes(octets)
    return dossier


def jouer(capsys: pytest.CaptureFixture[str], racine: Path, *options: str) -> tuple[int, list[str], str]:
    rc = HJ.main([*options, "--racine", str(racine)])
    sortie = capsys.readouterr()
    return rc, sortie.out.splitlines(), sortie.err


def lier(cible: Path | str, lien: Path, *, dossier: bool = False) -> None:
    try:
        os.symlink(cible, lien, target_is_directory=dossier)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"lien symbolique indisponible ici : {exc}")


def empreinte(dossier: Path) -> dict[str, tuple[bytes, int, int]]:
    """Nom -> (octets, inode, mtime_ns) des entrées de `dossier`, liens NON suivis pour l'inode et le mtime."""
    vu = {}
    for p in sorted(dossier.iterdir()):
        st = os.lstat(p)
        vu[p.name] = (p.read_bytes() if stat.S_ISREG(st.st_mode) else b"", st.st_ino, st.st_mtime_ns)
    return vu


def vieillir(dossier: Path) -> None:
    for p in dossier.iterdir():
        os.utime(p, ns=(PASSE_NS, PASSE_NS))


# --- constat -------------------------------------------------------------------------------------------------------

def test_arbres_concordants_rc0_et_autres_noms_ignores(racine, capsys):
    """Base : `*.py` identiques, `fixtures/`, `__pycache__/` et un `.txt` d'un seul côté ne sont pas jugés."""
    poser(racine, SOURCE, {"a.py": b"A\n", "_common.py": b"C\n", "notes.txt": b"x"})
    poser(racine, f"{SOURCE}/fixtures", {"transcript.jsonl": b"{}"})
    poser(racine, f"{SOURCE}/__pycache__", {"a.cpython-311.pyc": b"\0"})
    poser(racine, CIBLE, {"a.py": b"A\n", "_common.py": b"C\n"})
    assert jouer(capsys, racine) == (0, [], "")


def test_comparaison_a_l_octet_jamais_a_la_taille(racine, capsys):
    """M1 : deux fichiers de MÊME taille, un octet différent → `different`, rc 1."""
    poser(racine, SOURCE, {"a.py": b"DRIFT = 0\n"})
    poser(racine, CIBLE, {"a.py": b"DRIFT = 1\n"})
    rc, lignes, err = jouer(capsys, racine, "--check")
    assert (rc, lignes) == (1, ["different: a.py"])
    assert "--ecrire" in err


def test_absent_orphelin_different_listes_tries_par_nom(racine, capsys):
    """Les trois étiquettes, une ligne par écart, triées par nom ; un fichier identique n'est pas listé."""
    poser(racine, SOURCE, {"a.py": b"a", "c.py": b"c", "d.py": b"d-codex"})
    poser(racine, CIBLE, {"b.py": b"b", "c.py": b"c", "d.py": b"d-gemini"})
    rc, lignes, _ = jouer(capsys, racine)
    assert (rc, lignes) == (1, ["absent: a.py", "orphelin: b.py", "different: d.py"])


def test_check_est_le_defaut_et_n_ecrit_rien(racine, capsys):
    """M7 : sans option comme avec `--check`, la cible reste à l'octet, à l'inode et au mtime près."""
    poser(racine, SOURCE, {"a.py": b"neuf", "b.py": b"neuf"})
    cible = poser(racine, CIBLE, {"b.py": b"vieux"})
    avant = empreinte(cible)
    for options in ((), ("--check",)):
        rc, lignes, _ = jouer(capsys, racine, *options)
        assert (rc, lignes) == (1, ["absent: a.py", "different: b.py"])
        assert empreinte(cible) == avant


def test_bancs_test_star_exclus_des_deux_cotes(racine, capsys):
    """M3 : `test_*.py` d'un seul côté n'est ni absent ni orphelin, et `--ecrire` ne le copie pas."""
    poser(racine, SOURCE, {"a.py": b"a", "test_codex.py": b"t"})
    cible = poser(racine, CIBLE, {"a.py": b"a", "test_gemini.py": b"g"})
    assert jouer(capsys, racine, "--check") == (0, [], "")
    assert jouer(capsys, racine, "--ecrire") == (0, [], "")
    assert sorted(p.name for p in cible.iterdir()) == ["a.py", "test_gemini.py"]


def test_listage_non_recursif(racine, capsys):
    """M12 : un `*.py` d'un sous-dossier de la source n'est pas jugé."""
    poser(racine, SOURCE, {"a.py": b"a"})
    poser(racine, f"{SOURCE}/sous", {"b.py": b"b"})
    poser(racine, CIBLE, {"a.py": b"a"})
    assert jouer(capsys, racine) == (0, [], "")


@pytest.mark.parametrize("cas", ["bancs-seuls", "source-absente", "deux-absentes"])
def test_source_vide_ou_absente_rc2(racine, capsys, cas):
    """M4 : une source sans `*.py` hors `test_*.py`, ou absente, est un refus — jamais une concordance."""
    if cas == "bancs-seuls":
        poser(racine, SOURCE, {"test_x.py": b"t", "LISEZMOI.txt": b"x"})
    if cas != "deux-absentes":
        poser(racine, CIBLE, {})
    for options in (("--check",), ("--ecrire",)):
        rc, lignes, err = jouer(capsys, racine, *options)
        assert (rc, lignes) == (2, [])
        assert "source vide ou absente" in err


def test_racine_absente_rc2(tmp_path, capsys):
    assert jouer(capsys, tmp_path / "nulle-part")[0] == 2


def test_entree_py_non_reguliere_rc2(racine, capsys):
    """Un dossier nommé `x.py` dans la source n'est pas un fichier jugeable : refus."""
    poser(racine, SOURCE, {"a.py": b"a"})
    (racine / SOURCE / "x.py").mkdir()
    poser(racine, CIBLE, {"a.py": b"a"})
    rc, _, err = jouer(capsys, racine)
    assert rc == 2 and "pas un fichier regulier" in err


def test_lecture_impossible_rc2_sans_trace(racine, capsys):
    """Erreur d'E/S à la lecture d'une source : rc 2, message, aucune exception qui s'échappe."""
    if os.name == "nt" or os.geteuid() == 0:
        pytest.skip("chmod 000 ne retire pas la lecture ici")
    poser(racine, SOURCE, {"a.py": b"a"})
    poser(racine, CIBLE, {"a.py": b"b"})
    illisible = racine / SOURCE / "a.py"
    illisible.chmod(0)
    try:
        rc, _, err = jouer(capsys, racine)
    finally:
        illisible.chmod(0o644)
    assert rc == 2 and "erreur d'E/S" in err


# --- liens symboliques et racine ------------------------------------------------------------------------------------

@pytest.mark.parametrize("maillon", ["dossier-hooks", "dossier-hote", "fichier-cible", "fichier-source"])
def test_lien_symbolique_dans_la_racine_refuse(racine, capsys, maillon):
    """M5 : un lien sur un maillon source ou cible est refusé, même quand il pointe DANS la racine — le cas que le
    contrôle de realpath seul laisserait passer (`.gemini/hooks` -> `.codex/hooks` concorderait avec lui-même)."""
    poser(racine, SOURCE, {"a.py": b"a"})
    if maillon == "dossier-hooks":
        (racine / ".gemini").mkdir()
        lier(Path("..") / ".codex" / "hooks", racine / CIBLE, dossier=True)
    elif maillon == "dossier-hote":
        poser(racine, "autre/hooks", {"a.py": b"a"})
        lier("autre", racine / ".gemini", dossier=True)
    elif maillon == "fichier-cible":
        poser(racine, CIBLE, {})
        lier(Path("..") / ".." / ".codex" / "hooks" / "a.py", racine / CIBLE / "a.py")
    else:
        poser(racine, "ailleurs", {"b.py": b"b"})
        lier(Path("..") / ".." / "ailleurs" / "b.py", racine / SOURCE / "b.py")
        poser(racine, CIBLE, {"a.py": b"a", "b.py": b"b"})
    for options in (("--check",), ("--ecrire",)):
        rc, lignes, err = jouer(capsys, racine, *options)
        assert (rc, lignes) == (2, [])
        assert "lien symbolique" in err


def test_realpath_hors_racine_refuse(racine, tmp_path, capsys):
    """M15 (voir la BORNE du module) : `.gemini/hooks` lié hors de la racine → refus nommé `hors de la racine`."""
    poser(racine, SOURCE, {"a.py": b"a"})
    dehors = poser(tmp_path, "dehors/hooks", {"a.py": b"a"})
    (racine / ".gemini").mkdir()
    lier(dehors, racine / CIBLE, dossier=True)
    rc, lignes, err = jouer(capsys, racine, "--ecrire")
    assert (rc, lignes) == (2, [])
    assert "hors de la racine" in err


def test_refus_du_constat_n_ecrit_rien(racine, capsys):
    """M9 : `a.py` diffère, `b.py` (trié APRÈS) est un lien → `--ecrire` refuse sans avoir touché `a.py`."""
    poser(racine, SOURCE, {"a.py": b"neuf", "b.py": b"b"})
    poser(racine, "ailleurs", {"b.py": b"b"})
    cible = poser(racine, CIBLE, {"a.py": b"vieux"})
    lier(Path("..") / ".." / "ailleurs" / "b.py", cible / "b.py")
    avant = empreinte(cible)
    rc, lignes, _ = jouer(capsys, racine, "--ecrire")
    assert (rc, lignes) == (2, [])
    assert empreinte(cible) == avant


# --- écriture --------------------------------------------------------------------------------------------------------

def test_ecrire_ne_supprime_jamais_un_orphelin(racine, capsys):
    """M2 : l'orphelin reste à l'octet près, il est listé, rc 1 ; l'absent est écrit."""
    poser(racine, SOURCE, {"a.py": b"a"})
    cible = poser(racine, CIBLE, {"orphelin.py": b"o"})
    rc, lignes, _ = jouer(capsys, racine, "--ecrire")
    assert (rc, lignes) == (1, ["ecrit: a.py", "orphelin: orphelin.py"])
    assert (cible / "orphelin.py").read_bytes() == b"o"
    assert (cible / "a.py").read_bytes() == b"a"


def test_ecrire_rend_la_concordance_et_ne_touche_pas_l_identique(racine, capsys):
    """M6 (premier passage) : seuls `absent` et `different` sont écrits ; l'identique garde inode et mtime."""
    poser(racine, SOURCE, {"a.py": b"a", "b.py": b"b-neuf", "c.py": b"c"})
    cible = poser(racine, CIBLE, {"a.py": b"a", "b.py": b"b-vieux"})
    vieillir(cible)
    identique = empreinte(cible)["a.py"]
    rc, lignes, _ = jouer(capsys, racine, "--ecrire")
    assert (rc, lignes) == (0, ["ecrit: b.py", "ecrit: c.py"])
    assert empreinte(cible)["a.py"] == identique
    for nom in ("a.py", "b.py", "c.py"):
        assert (cible / nom).read_bytes() == (racine / SOURCE / nom).read_bytes()
    assert jouer(capsys, racine, "--check") == (0, [], "")


def test_seconde_passe_ne_reecrit_rien(racine, capsys):
    """M6 : après un `--ecrire`, un second ne touche aucun fichier — inode (remplacement) ET mtime posé dans le passé
    (réécriture en place) inchangés."""
    poser(racine, SOURCE, {"a.py": b"a", "b.py": b"b"})
    cible = poser(racine, CIBLE, {"a.py": b"vieux"})
    assert jouer(capsys, racine, "--ecrire")[0] == 0
    vieillir(cible)
    avant = empreinte(cible)
    assert jouer(capsys, racine, "--ecrire") == (0, [], "")
    assert empreinte(cible) == avant


def test_ecriture_par_temporaire_hors_py_du_dossier_cible(racine, capsys, monkeypatch):
    """M8 : chaque écriture passe par `os.replace` d'un temporaire du dossier cible dont le nom n'est pas `*.py`."""
    poser(racine, SOURCE, {"a.py": b"a"})
    cible = poser(racine, CIBLE, {})
    appels: list[tuple[str, str]] = []
    vrai_replace = os.replace

    def espion(src, dst):
        appels.append((os.fspath(src), os.fspath(dst)))
        vrai_replace(src, dst)

    monkeypatch.setattr(os, "replace", espion)
    assert jouer(capsys, racine, "--ecrire") == (0, ["ecrit: a.py"], "")
    assert len(appels) == 1
    temporaire, destination = appels[0]
    assert not temporaire.endswith(".py")
    assert Path(temporaire).parent.resolve() == cible.resolve()
    assert Path(destination).resolve() == (cible / "a.py").resolve()
    assert sorted(p.name for p in cible.iterdir()) == ["a.py"]


def test_echec_du_remplacement_rc2_sans_residu(racine, capsys, monkeypatch):
    """M14 : `os.replace` en échec → rc 2, la cible garde ses octets, aucun temporaire ne reste."""
    poser(racine, SOURCE, {"a.py": b"neuf"})
    cible = poser(racine, CIBLE, {"a.py": b"vieux"})

    def panne(src, dst):
        raise OSError(28, "disque plein (simule)")

    monkeypatch.setattr(os, "replace", panne)
    rc, lignes, err = jouer(capsys, racine, "--ecrire")
    assert (rc, lignes) == (2, [])
    assert "erreur d'E/S" in err
    assert sorted(p.name for p in cible.iterdir()) == ["a.py"]
    assert (cible / "a.py").read_bytes() == b"vieux"


def test_reprise_bornee_sur_permissionerror(racine, capsys, monkeypatch):
    """M10 : deux `PermissionError` puis succès → écrit, rc 0 ; `PermissionError` permanente → rc 2 après un nombre
    BORNÉ d'essais (plus d'un), sans temporaire laissé."""
    poser(racine, SOURCE, {"a.py": b"neuf"})
    cible = poser(racine, CIBLE, {"a.py": b"vieux"})
    monkeypatch.setattr(HJ, "ATTENTE_INITIALE_S", 0.0)
    vrai_replace = os.replace
    essais = {"n": 0, "pannes": 2}

    def verrouille(src, dst):
        essais["n"] += 1
        if essais["n"] <= essais["pannes"]:
            raise PermissionError(13, "lecteur concurrent (simule)")
        vrai_replace(src, dst)

    monkeypatch.setattr(os, "replace", verrouille)
    assert jouer(capsys, racine, "--ecrire") == (0, ["ecrit: a.py"], "")
    assert (cible / "a.py").read_bytes() == b"neuf"
    (cible / "a.py").write_bytes(b"vieux")
    essais.update(n=0, pannes=10_000)
    rc, _, err = jouer(capsys, racine, "--ecrire")
    assert rc == 2 and "erreur d'E/S" in err
    assert 1 < essais["n"] == HJ.REPRISES_REMPLACEMENT
    assert sorted(p.name for p in cible.iterdir()) == ["a.py"]


def test_mode_du_fichier_source_recopie(racine, capsys):
    """M11 : le fichier écrit porte le mode du source (le temporaire naît en 0o600)."""
    if os.name == "nt":
        pytest.skip("bits de mode POSIX")
    source = poser(racine, SOURCE, {"a.py": b"a"})
    (source / "a.py").chmod(0o754)
    cible = poser(racine, CIBLE, {})
    assert jouer(capsys, racine, "--ecrire")[0] == 0
    assert stat.S_IMODE((cible / "a.py").stat().st_mode) == 0o754


def test_cible_absente_check_liste_ecrire_ne_cree_rien(racine, capsys):
    """`--check` liste tout en absent (rc 1) ; `--ecrire` ne crée pas le dossier cible (rc 2)."""
    poser(racine, SOURCE, {"a.py": b"a"})
    assert jouer(capsys, racine, "--check")[:2] == (1, ["absent: a.py"])
    rc, _, err = jouer(capsys, racine, "--ecrire")
    assert rc == 2 and "erreur d'E/S" in err
    assert not (racine / ".gemini").exists()


# --- interface ------------------------------------------------------------------------------------------------------

def test_check_et_ecrire_exclusifs(racine):
    with pytest.raises(SystemExit) as sortie:
        HJ.main(["--check", "--ecrire", "--racine", str(racine)])
    assert sortie.value.code == 2


def test_racine_par_defaut_est_l_arbre_du_script(tmp_path, monkeypatch):
    """M13 : ni le dossier courant ni `CLAUDE_PROJECT_DIR` — la racine qui porte `.agents/bin/hooks_jumeaux.py`."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    assert HJ.racine_par_defaut() == ICI.parents[1]
    assert (HJ.racine_par_defaut() / ".agents" / "bin" / "hooks_jumeaux.py").is_file()


def test_main_sans_racine_lit_la_racine_par_defaut(racine, tmp_path, capsys, monkeypatch):
    """M13 : `main([])` juge l'arbre de `racine_par_defaut()`, pas le dossier courant ni `CLAUDE_PROJECT_DIR`."""
    poser(racine, SOURCE, {"a.py": b"a"})
    poser(racine, CIBLE, {"a.py": b"a"})
    ailleurs = tmp_path / "ailleurs"
    ailleurs.mkdir()
    monkeypatch.chdir(ailleurs)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(ailleurs))
    monkeypatch.setattr(HJ, "racine_par_defaut", lambda: racine)
    assert HJ.main([]) == 0
    assert capsys.readouterr().out == ""


def test_point_d_entree_rend_les_trois_codes(racine):
    """M16 : le script lancé seul (`python -I`) rend 0, 1 puis 2 selon l'arbre."""
    poser(racine, SOURCE, {"a.py": b"a"})
    cible = poser(racine, CIBLE, {"a.py": b"a"})

    def lancer() -> int:
        return subprocess.run([sys.executable, "-I", str(ICI / "hooks_jumeaux.py"), "--racine", str(racine)],
                              capture_output=True, text=True, timeout=60, check=False).returncode

    assert lancer() == 0
    (cible / "a.py").write_bytes(b"b")
    assert lancer() == 1
    (racine / SOURCE / "a.py").unlink()
    assert lancer() == 2
