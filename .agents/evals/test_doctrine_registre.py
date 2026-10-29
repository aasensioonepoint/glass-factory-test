"""Le registre de doctrine des bancs tient sans se lire lui-même (T-01M4V7R89VZ5SP3NXZ32SNNDZ2).

`doctrine_registre.py` est la source unique des jetons et des surfaces des règles qu'il
déclare ; ce banc prouve qu'il est bien formé, qu'il ne lit rien, que ses bancs le lisent
VRAIMENT et ne recopient pas ses valeurs, et que chacun de ses jetons peut rougir :
  4a `valider(REGLES) == []` ;
  4b chaque surface existe, est suivie (`git ls-files -z`) et n'est pas vide ;
  4c AST du registre : aucune RÉFÉRENCE — appel, alias ou indice — à un nom d'E/S (`open`,
     `read_text`, `read_bytes`, `write_text`, `write_bytes`) ni à une porte qui contournerait
     la liste blanche (`__import__`, `exec`, `eval`, `compile`, `getattr`, `vars`, `globals`,
     `locals`, `__builtins__`, `builtins`), aucun nom dunder lu, aucun attribut dunder,
     aucun import hors liste blanche — contrôle STATIQUE : une fonction morte compte aussi ;
     un témoin synthétique fait rougir chaque contournement ;
  4d AST de chaque banc déclaré : il importe `doctrine_registre`, porte l'id de sa règle en
     constante de MODULE, et ne contient AUCUNE constante str égale à un jeton de sa règle ;
  4e chaque jeton est présent sur chaque surface de son groupe, et le retirer fait manquer
     CE jeton et lui seul (égalité exacte : un jeton contenu dans un frère ne peut pas rougir) ;
  4f sur un registre SYNTHÉTIQUE (jamais les clés vivantes, tenues par 4d), `valider` refuse
     chaque forme fautive, une faute par cas ;
  4g `git grep -w` : les fichiers qui nomment `doctrine_registre` forment un SOUS-ENSEMBLE de
     {registre, ce banc, bancs déclarés}, et chaque banc déclaré y figure (plancher,
     L-00000232). Les `.md`, `.agents/state/`, `runs/` et `docs/*.json` n'y comptent pas ;
     seuls `*.py *.sh *.ps1 *.toml *.json *.yml *.yaml` sont lus (témoin : un dépôt jetable
     où un workflow `.yml`/`.yaml` est vu) — un script SANS extension ne l'est pas.

Git inutilisable : ROUGE, jamais une liste vide. Un fichier non suivi n'est vu qu'après
`git add`. Les bornes du registre (présence seulement, nom calculé, pathspec de 4g, 4c
statique, paraphrase) sont écrites dans sa docstring.
"""
from __future__ import annotations

import ast
import copy
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EVALS = Path(__file__).resolve().parent
if str(EVALS) not in sys.path:
    sys.path.insert(0, str(EVALS))

import doctrine_registre as R  # noqa: E402
from surface_kit import EST_LE_KIT  # noqa: E402

MODULE = "doctrine_registre"
REGISTRE = ".agents/evals/doctrine_registre.py"
CE_BANC = ".agents/evals/test_doctrine_registre.py"
#: 4c refuse toute RÉFÉRENCE à ces noms (appel, alias, indice), pas seulement leur appel :
#: l'E/S, puis les portes qui rendent une fonction par un nom CALCULÉ ou un espace de noms.
NOMS_INTERDITS = frozenset({
    "open", "__import__", "exec", "eval", "compile",
    "getattr", "globals", "vars", "locals", "__builtins__", "builtins",
})
#: ... et toute référence à ces attributs, plus tout attribut dunder (`__class__`, `__dict__`).
ATTRIBUTS_INTERDITS = frozenset({"open", "read_text", "read_bytes", "write_text", "write_bytes"})
IMPORTS_ADMIS = frozenset({"__future__", "typing", "dataclasses", "types"})
#: Pathspec de 4g : les types qui peuvent IMPORTER ou LANCER le module (workflows CI compris) ;
#: l'état, les exports de run et le JSON documentaire nomment le module sans le consommer.
#: BORNE : un script SANS extension (`.githooks/*`, lanceurs), un `Makefile`, un `Dockerfile`
#: ou toute autre extension n'y sont pas vus ; un `.md` ne l'est pas, par conception.
PATHSPEC_4G = (
    "*.py", "*.sh", "*.ps1", "*.toml", "*.json", "*.yml", "*.yaml",
    ":(exclude).agents/state/", ":(exclude)runs/", ":(exclude)docs/*.json",
)

#: RECOPIÉES de `shim_grammar.py::GIT_REDIRECTIONS`, pas importées : lancé depuis un hook git,
#: `GIT_DIR` est exporté, et git lirait alors un AUTRE dépôt que ROOT.
GIT_REDIRECTIONS = (
    "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
    "GIT_COMMON_DIR", "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE",
    "GIT_PREFIX", "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT",
)
GIT_CONFIG_PREFIXES = ("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")

#: Hors du kit, chaque groupe est RESTREINT à ses surfaces livrées (`R.livrees`, qui lève si
#: rien ne reste) : les prompts de session du kit (`R.HORS_VOYAGE`) ne voyagent pas, et 4b/4e
#: n'y sont pas tenus chez l'adoptant ; AGENTS.md, qui voyage, reste jugé partout.
def surfaces_jugees(nom: str, groupe: str, surfaces: tuple[str, ...]) -> tuple[str, ...]:
    """Les surfaces de registre livrées ; CHANGELOG est le canal adoptant d'E5."""
    if not EST_LE_KIT and nom == "plafond-poste" and groupe == "changelog":
        assert surfaces == ("CHANGELOG.md",), "groupe CHANGELOG inattendu"
        return ()  # E3 : destination réécrite à E5, seule exclusion du registre.
    return R.livrees(surfaces, EST_LE_KIT)


TRIPLETS = [
    (nom, groupe, surface)
    for nom, r in R.REGLES.items()
    for groupe, g in r["groupes"].items()
    for surface in surfaces_jugees(nom, groupe, g["surfaces"])
]
assert TRIPLETS and any(surface == "AGENTS.md" for _, _, surface in TRIPLETS), (
    "aucune surface de registre livrée")
BANCS = sorted({b for r in R.REGLES.values() for b in r["bancs"]})


def _git(*args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[bytes]:
    """git dans `cwd` (ROOT), environnement purgé de ses redirections ; git absent = ROUGE."""
    env = {
        k: v for k, v in os.environ.items()
        if k not in GIT_REDIRECTIONS and not k.startswith(GIT_CONFIG_PREFIXES)
    }
    try:
        return subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, check=False)
    except OSError as exc:  # git introuvable : jamais un vert sur liste vide
        pytest.fail(f"git inutilisable ({exc}) : 4b/4g ne peuvent pas lister les fichiers suivis")


def _liste_z(sortie: bytes) -> set[str]:
    return {x for x in sortie.decode("utf-8").split("\0") if x}


def _texte(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _dunder(nom: str) -> bool:
    return len(nom) > 4 and nom.startswith("__") and nom.endswith("__")


def _reference_interdite(n: ast.AST) -> str | None:
    """Le nom ou l'attribut refusé que ce nœud RÉFÉRENCE, sinon None ; un nom dunder n'est
    refusé qu'en lecture (`__all__ = ...` reste possible)."""
    if isinstance(n, ast.Name) and (
        n.id in NOMS_INTERDITS or (_dunder(n.id) and isinstance(n.ctx, ast.Load))
    ):
        return n.id
    if isinstance(n, ast.Attribute) and (n.attr in ATTRIBUTS_INTERDITS or _dunder(n.attr)):
        return f".{n.attr}"
    return None


def test_4a_le_registre_vivant_est_bien_forme() -> None:
    assert R.valider(R.REGLES) == []


def test_4a_plancher_le_registre_n_est_pas_vide() -> None:
    """Non-vacuité des balayages paramétrés ci-dessous (L-00000232) : un plancher, jamais un
    compte — les MEMBRES des surfaces sont épinglés dans les bancs pilotes."""
    assert len(R.REGLES) >= 2 and len(BANCS) >= 2
    assert {nom for nom, _, _ in TRIPLETS} == set(R.REGLES), "une règle sans surface"


def test_4a_changelog_adoptant_restreint_sans_vider_le_registre() -> None:
    """Le groupe CHANGELOG est jugé dans le kit, jamais sur le texte réécrit."""
    assert TRIPLETS and any(surface == "AGENTS.md" for _, _, surface in TRIPLETS)
    assert (("plafond-poste", "changelog", "CHANGELOG.md") in TRIPLETS) == EST_LE_KIT


@pytest.mark.parametrize("nom,groupe,surface", TRIPLETS)
def test_4b_chaque_surface_existe_est_suivie_et_non_vide(nom: str, groupe: str, surface: str) -> None:
    p = _git("ls-files", "-z", "--", surface)
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    assert surface in _liste_z(p.stdout), f"{nom}.{groupe} : {surface} n'est pas suivi"
    assert (ROOT / surface).is_file(), f"{nom}.{groupe} : {surface} absent"
    assert _texte(surface).strip(), f"{nom}.{groupe} : {surface} vide"


def _fautes_oracle(source: str) -> list[str]:
    """Les fautes 4c d'un source : E/S, contournement de la liste blanche, import hors liste."""
    fautes: list[str] = []
    for n in ast.walk(ast.parse(source)):
        if (ref := _reference_interdite(n)) is not None:
            fautes.append(f"ligne {n.lineno} : référence {ref}")
        elif isinstance(n, ast.Import):
            fautes += [
                f"ligne {n.lineno} : import {a.name}"
                for a in n.names if a.name.split(".")[0] not in IMPORTS_ADMIS
            ]
        elif isinstance(n, ast.ImportFrom):
            module = n.module or ""
            if n.level or module.split(".")[0] not in IMPORTS_ADMIS:
                fautes.append(f"ligne {n.lineno} : from {'.' * n.level}{module} import")
    return fautes


def test_4c_le_registre_ne_lit_rien_et_n_importe_que_la_liste_blanche() -> None:
    fautes = _fautes_oracle(_texte(REGISTRE))
    assert fautes == [], f"le registre doit rester un oracle pur : {fautes}"


@pytest.mark.parametrize("cas,source", [
    ("appel direct", 'open("AGENTS.md")'),
    ("méthode de Path", 'P("AGENTS.md").read_text()'),
    ("import hors liste", "import os"),
    ("nom calculé par getattr", 'getattr(__builtins__, "op" + "en")("AGENTS.md")'),
    ("alias", 'o = open\no("AGENTS.md")'),
    ("alias de méthode", 'lire = P("AGENTS.md").read_text\nlire()'),
    ("indice sur __builtins__", '__builtins__["open"]("AGENTS.md")'),
    ("vars()", 'vars()["__builtins__"]'),
    ("chaîne dunder", "().__class__.__base__.__subclasses__()"),
    ("nom dunder lu", "x = __name__"),
])
def test_4c_temoin_chaque_contournement_rougit(cas: str, source: str) -> None:
    """Témoin de non-vacuité : chaque forme, posée dans une fonction MORTE, est une faute."""
    corps = "\n".join(f"    {ligne}" for ligne in source.splitlines())
    assert _fautes_oracle(f"def _morte() -> None:\n{corps}\n") != [], cas


def test_4c_temoin_les_noms_en_chaine_restent_admis() -> None:
    """Témoin vert : un nom interdit écrit en CONSTANTE (un jeton) n'est pas une référence."""
    assert _fautes_oracle('X = {"open": ("read_text", "__builtins__", "getattr")}\n') == []


def _constantes_de_module(arbre: ast.Module) -> set[str]:
    """Les str affectées au niveau MODULE, seules ou en tuple."""
    valeurs: set[str] = set()
    for n in arbre.body:
        valeur = n.value if isinstance(n, (ast.Assign, ast.AnnAssign)) else None
        membres = valeur.elts if isinstance(valeur, ast.Tuple) else [valeur]
        valeurs |= {m.value for m in membres if isinstance(m, ast.Constant) and isinstance(m.value, str)}
    return valeurs


@pytest.mark.parametrize("nom", list(R.REGLES))
def test_4d_chaque_banc_lit_le_registre_et_ne_recopie_aucun_jeton(nom: str) -> None:
    toks = {j for g in R.regle(nom)["groupes"].values() for j in g["jetons"]}
    for banc in R.regle(nom)["bancs"]:
        arbre = ast.parse(_texte(banc))
        importe = any(
            (isinstance(n, ast.Import) and any(a.name == MODULE for a in n.names))
            or (isinstance(n, ast.ImportFrom) and n.module == MODULE)
            for n in ast.walk(arbre)
        )
        assert importe, f"{banc} n'importe pas {MODULE}"
        assert nom in _constantes_de_module(arbre), (
            f"{banc} ne porte pas l'id {nom!r} en constante de module (REGLE = {nom!r}) — "
            "un id renommé au registre doit rougir ici"
        )
        recopies = sorted(
            n.value for n in ast.walk(arbre)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value in toks
        )
        assert recopies == [], f"{banc} recopie en dur des jetons du registre : {recopies}"


@pytest.mark.parametrize("nom,groupe,surface", TRIPLETS)
def test_4e_chaque_jeton_present_et_seul_a_manquer_quand_on_le_retire(
    nom: str, groupe: str, surface: str
) -> None:
    texte = _texte(surface)
    attendus = R.jetons(nom, groupe)
    assert R.manquants(texte, attendus) == [], f"{surface} ({nom}.{groupe})"
    for j in attendus:
        mute = texte.replace(j, "")
        assert mute != texte, f"{j!r} absent de {surface}"
        assert R.manquants(mute, attendus) == [j], (
            f"{surface} privé de {j!r} : manquants={R.manquants(mute, attendus)} — "
            "un jeton qui ne peut pas manquer SEUL ne peut pas rougir"
        )


SYNTHETIQUE: dict[str, dict[str, object]] = {
    "regle-synthetique": {
        "groupes": {
            "groupe": {
                "surfaces": ("dossier/un.md", "dossier/deux.md"),
                "jetons": ("jeton-un", "jeton-deux"),
            },
        },
        "bancs": (".agents/evals/test_synthetique.py",),
        "limite": "borne synthétique",
    },
}


def _mute(f: Callable[[dict], None]) -> dict:
    r = copy.deepcopy(SYNTHETIQUE)
    f(r["regle-synthetique"])
    return r


def _groupe(champ: str, valeur: object) -> Callable[[dict], None]:
    return lambda r: r["groupes"]["groupe"].__setitem__(champ, valeur)


def test_4f_le_registre_synthetique_est_valide() -> None:
    """Témoin : chaque refus ci-dessous vient de SA mutation, pas d'un défaut du synthétique."""
    assert R.valider(SYNTHETIQUE) == []


@pytest.mark.parametrize("cas,mutation,motif", [
    ("groupe vide", _groupe("jetons", ()), "groupe vide"),
    ("jeton court", _groupe("jetons", ("court", "jeton-deux")), "jeton court"),
    ("doublon", _groupe("jetons", ("jeton-un", "jeton-un")), "doublon"),
    ("sous-chaîne", _groupe("jetons", ("jeton-un", "jeton-un-bis")), "sous-chaîne"),
    ("absolu", _groupe("surfaces", ("/etc/passwd",)), "absolu"),
    ("absolu windows", _groupe("surfaces", ("C:/x.md",)), "absolu"),
    ("remontant", _groupe("surfaces", ("dossier/../../x.md",)), "remontant"),
    ("jetons non tuple", _groupe("jetons", "jeton-un"), "tuples de textes"),
    ("bancs vide", lambda r: r.__setitem__("bancs", ()), "bancs vide"),
    ("limite vide", lambda r: r.__setitem__("limite", "  "), "limite vide"),
])
def test_4f_valider_refuse_chaque_forme_fautive(
    cas: str, mutation: Callable[[dict], None], motif: str
) -> None:
    fautes = R.valider(_mute(mutation))
    assert len(fautes) == 1 and motif in fautes[0], f"{cas} : {fautes}"


def _grep_4g(cwd: Path = ROOT) -> set[str]:
    p = _git("grep", "-l", "-z", "-w", "-F", "-e", MODULE, "--", *PATHSPEC_4G, cwd=cwd)
    assert p.returncode in (0, 1), p.stderr.decode("utf-8", "replace")
    return _liste_z(p.stdout)


def test_4g_temoin_le_pathspec_voit_un_workflow_yaml(tmp_path: Path) -> None:
    """Témoin dans un dépôt JETABLE : un workflow CI qui lance le module est vu, `.yml` comme
    `.yaml` ; le `.md` témoin, qui le nomme sans le consommer, ne l'est pas (L-00000232)."""
    assert _git("init", "-q", cwd=tmp_path).returncode == 0
    poses = {".github/workflows/ci.yml", ".github/workflows/nuit.yaml", "notes.md"}
    for rel in poses:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(f"run: python -m {MODULE}\n", encoding="utf-8")
    assert _git("add", "--", *sorted(poses), cwd=tmp_path).returncode == 0
    assert _grep_4g(tmp_path) == poses - {"notes.md"}


def test_4g_aucun_importeur_hors_registre_et_bancs_declares() -> None:
    trouves = _grep_4g()
    admis = {REGISTRE, CE_BANC, *BANCS}
    assert trouves <= admis, (
        f"fichiers qui nomment {MODULE} hors registre et bancs déclarés : "
        f"{sorted(trouves - admis)} — déclare-les en `bancs` d'une règle, ou retire la lecture"
    )
    assert set(BANCS) <= trouves, (
        f"bancs déclarés que git grep ne voit pas nommer {MODULE} : {sorted(set(BANCS) - trouves)}"
    )
