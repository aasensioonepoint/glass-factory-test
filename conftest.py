"""Filet d'isolation pytest à l'échelle du dépôt — T-00000265.

Certains tests remplacent un attribut du module partagé ``subprocess`` par une
assignation NUE (``mod.subprocess.run = explode``) et ne le restaurent jamais :
comme ``mod.subprocess`` est le singleton du processus, la mutation empoisonne
TOUS les tests collectés ensuite dans la même invocation pytest. La fuite
mesurée faisait rendre ``False`` à ``git_tracked`` par la branche de
dégradation ``except Exception``, verdissant à tort — ou rougissant à tort —
des suites entières sans que rien ne le signale.

Ce filet ``autouse`` épingle l'IDENTITÉ des quatre attributs mesurés de
``subprocess`` (``run``, ``Popen``, ``check_output``, ``call``) avant chaque
test et la vérifie après ``yield``. Il fait DEUX choses au teardown :

1. il RESTAURE l'attribut fuité sur le singleton, pour couper la cascade
   d'empoisonnement des tests suivants — un filet qui détecte sans réparer
   laisserait la contamination se propager ;
2. il FAIT ÉCHOUER le test fautif par une assertion dont le message nomme
   l'attribut fuité et le remède (``mock.patch.object`` / ``monkeypatch``).

Il n'épingle que ``subprocess`` — la forme MESURÉE — pas ``os`` / ``shutil`` /
``sys`` ni d'autres objets partagés : une sentinelle plus large s'ajoutera avec
sa propre preuve de non-vacuité.
"""

import fnmatch
import glob
import importlib.util
import os
import shlex
import shutil
import subprocess
import tempfile

import pytest

_WATCHED = ("run", "Popen", "check_output", "call")


def _amorcer_vendor():
    """T-01M5BXTGX5YN8XEXTG1PP7A5ZX (phase D) : les parents de `cadre` et `agentic_v3`
    de CET arbre (résolveur `.agents/bin/vendor_paths.py`, chargé par chemin) AJOUTÉS
    EN QUEUE de `sys.path` s'ils manquent (`amorcer_conftest`), jamais en tête : le
    paquet de l'adoptant, plus haut, garde la priorité. Résolveur absent ou illisible,
    ou texte exécuté sans `__file__` : rien n'est ajouté, l'état d'avant. BORNE (C15) :
    le rootdir que pytest place en tête précède `.agents/vendor` — dans un arbre « les
    deux », l'ancien `agentic_v3` est celui qu'un banc importe par son nom
    (`test_vendor_bridge.py` B7). Témoin : `.agents/bin/test_vendor_setup.py`. L'ajout EN
    QUEUE rend le `src/` de l'adoptant (ancienne disposition) importable par son nom dans
    ses tests, là où `charger_paquet` le tient hors de `sys.path`."""
    try:
        racine = os.path.dirname(os.path.abspath(__file__))
        chemin = os.path.join(racine, ".agents", "bin", "vendor_paths.py")
        spec = importlib.util.spec_from_file_location("_conftest_racine_vendor_paths", chemin)
        resolveur = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(resolveur)
        resolveur.amorcer_conftest(racine)
    except Exception:  # noqa: BLE001 — résolveur absent ou illisible : aucun amorçage
        return


_amorcer_vendor()


def greffe_email_git_franchissable(monkeypatch, request, module_run_export) -> bool:
    """Greffe `_email_git` SAUF opt-in (marqueur `email_git_reel` ou
    AGENTS_BANC_EMAIL_GIT_REEL). L-00000500 : une fixture d'amont qui greffe SANS
    PORTE éteint tout témoin d'aval du vrai git — c'est ce qui a laissé passer la
    régression `rc=1` de `git config`. Rend True si la greffe a été POSÉE.

    PORTE UNIQUE appelée par les fixtures que liste la première commande ci-dessous
    (8 au 2026-10-10) ; HORS porte, relevé : `test_journal_attente_orphelin.py`
    setUp (:73-74, un `mock.patch` DÉMARRÉ, non borné à un `with`) — le cas que la
    BORNE ci-dessous dit invisible à ces deux commandes. Une greffe de
    `_email_git` dupliquée dont une seule est franchissable donne
    l'ILLUSION d'avoir fermé la classe. CETTE PHRASE DISAIT « toutes » ALORS QUE LA
    PORTE EN COUVRAIT QUATRE (T-00000695/696) : `test_v3_pipeline.py` greffait par
    un `setattr` NU — non franchissable — et `test_board_bridge.py` par une COPIE de
    cette logique. Les deux passent désormais par ici. Le compte n'est pas à
    croire, il se RECOMPTE — deux commandes, à rejouer telles quelles. TOUTES DEUX
    EXCLUENT CE FICHIER (`':!conftest.py'`) : il CITE les motifs qu'elles cherchent,
    et la version précédente se comptait elle-même — « 1 ligne » annoncée, 3 rendues
    (sa propre citation, plus une ligne de ce paragraphe prise par le `-A2`) :

      LC_ALL=C git grep -n 'greffe_email_git_franchissable(monkeypatch' -- '*.py' ':!conftest.py'
          -> 8 lignes (relevé du 2026-10-10) : une par fixture qui passe par la porte ;
      LC_ALL=C git grep -n -A2 'setattr(' -- '*.py' ':!conftest.py' | LC_ALL=C grep '_email_git'
          -> 0 ligne ; la greffe de la porte est le `monkeypatch.setattr` de cette
             fonction (`conftest.py:83` au 2026-10-10). Toute ligne rendue
             est une greffe hors porte (le `-A2` attrape un `setattr(` coupé sur deux
             lignes).

    BORNE DU BALAYAGE, écrite : il voit `setattr(`, pas un `mock.patch.object(…,
    "_email_git", …)`. Ceux-là (29 relevés le 2026-09-23 : 25 dans
    `test_run_export.py`, 3 dans `test_tasks.py`, 1 dans `test_board_bridge.py`,
    par `LC_ALL=C git grep -cF '"_email_git", return_value=' -- '*.py' ':!conftest.py'`)
    sont posés PAR TEST et bornés à leur
    `with` : ils n'éteignent aucun témoin d'aval, donc hors de la classe
    L-00000500 — mais une fixture qui en poserait un y entrerait sans que ces deux
    commandes la voient.

    `module_run_export` est l'objet module `agentic_v3.db.run_export` (importé sous
    ce nom OU sous un alias par l'appelant) ; la greffe porte sur SON attribut
    `_email_git`, cible unique des fixtures. L'opt-in se lit par `request` (marqueur)
    et non par un env posé dans le corps du test : une fixture `autouse` tourne AVANT
    lui, un env arriverait trop tard."""
    veut_git_reel = os.environ.get("AGENTS_BANC_EMAIL_GIT_REEL") or (
        request.node.get_closest_marker("email_git_reel") is not None
    )
    if veut_git_reel:
        return False
    monkeypatch.setattr(module_run_export, "_email_git", lambda depuis=None: "banc@test")
    return True


@pytest.fixture(scope="session", autouse=True)
def _isolation_state_dir_session():
    """T-00000650, BLOQUANT 3 (binôme de clôture) — depuis la bascule « état machine
    hors dépôt », tout banc qui résout une racine temporaire crée une partition SOUS
    la VRAIE `state_home()` de la machine (`…/.local/state/cadre/projets/<empreinte>`)
    et rien ne la nettoie. MESURÉ sur ce poste : plus de 1000 partitions et des
    milliers de journaux d'attente orphelins, régression directe de cette tâche.

    On pose `CADRE_STATE_DIR` vers un répertoire temporaire DE SESSION quand
    l'appelant ne l'a PAS déjà posé, et on le retire ensuite. Une valeur déjà posée
    par l'appelant (banc qui gère sa propre isolation) est RESPECTÉE — on ne
    l'écrase pas. Les bancs qui posent leur propre `CADRE_STATE_DIR` par test
    l'emportent, ce garde-fou ne captant que les bancs qui n'en posent AUCUN."""
    if os.environ.get("CADRE_STATE_DIR"):
        yield
        return
    tmp = tempfile.mkdtemp(prefix="cadre_state_session_")
    os.environ["CADRE_STATE_DIR"] = tmp
    try:
        yield
    finally:
        os.environ.pop("CADRE_STATE_DIR", None)
        shutil.rmtree(tmp, ignore_errors=True)


#: Les variables par lesquelles git se laisse DÉSIGNER un autre dépôt que celui de
#: son `-C` ou de son cwd. `GIT_PREFIX` et `GIT_NAMESPACE` ne redirigent pas un
#: commit, mais `GIT_PREFIX` décale les chemins relatifs et `GIT_NAMESPACE` les
#: références : un banc qui hérite de l'un ou de l'autre ne mesure plus son dépôt.
#: DEUX INJECTIONS DE CONFIGURATION s'y ajoutent (exec-critic, passes post-binôme) :
#: `git -c` exporte `GIT_CONFIG_PARAMETERS` à ses hooks, et `GIT_CONFIG_COUNT` +
#: `GIT_CONFIG_KEY_<n>`/`GIT_CONFIG_VALUE_<n>` posent une clé — mesuré (git
#: 2.55.0) : l'une comme l'autre font répondre `git config user.email` par la
#: valeur injectée, au-dessus de la config LOCALE du dépôt jetable. Les deux
#: dernières se retirent par PRÉFIXE (`GIT_CONFIG_PREFIXES`), jamais
#: `GIT_CONFIG_GLOBAL`/`SYSTEM`/`NOSYSTEM`, que les bancs posent eux-mêmes.
GIT_REDIRECTIONS = (
    "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
    "GIT_COMMON_DIR", "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE",
    "GIT_PREFIX", "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT",
)
GIT_CONFIG_PREFIXES = ("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")


def git_herite(nom: str) -> bool:
    """Vrai si la variable `nom` redirige git ou lui injecte une configuration."""
    return nom in GIT_REDIRECTIONS or nom.startswith(GIT_CONFIG_PREFIXES)


# --- T-00001188 : LA PORTE REFUSE UN FICHIER GIT-IGNORÉ NON SUIVI QUE PYTEST CHARGERAIT ---
# Code de MODULE, exécuté à l'import de CE conftest — le premier que pytest charge
# (`_loadconftestmodules` descend de la racine). Aucune fixture : un refus ici sort
# rc 4 AVANT tout autre conftest et tout module de test. Banc :
# .agents/evals/test_runner_ignored_exec_1188.py ; contrat et bornes : la docstring de `_garde_1188`.
_RACINE_1188 = os.path.dirname(os.path.abspath(__file__))
_DELAI = 30
#: Plafond d'entrées git-ignorées parcourues par UNE garde, toutes marches confondues : au-delà, refus
#: fail-closed (un lien vers `/`, un dossier de données géant non élagué). Mesuré le 2026-10-11 (macOS, sous
#: charge) : ≈ 1,0 s / 100 000 entrées, et 322 entrées parcourues sur le dépôt principal vivant du kit (85 sur
#: un worktree) — le plafond borne la garde à ≈ 2 s, à 600 fois le besoin du kit.
_PLAFOND = 200000
#: `norecursedirs` PAR DÉFAUT de pytest 9.1.1 (_pytest/main.py) : ils valent quand `pytest.ini` racine n'en porte pas.
_NORECURSE_1188 = ("*.egg", ".*", "_darcs", "build", "CVS", "dist", "node_modules", "venv", "{arch}")
#: `norecursedirs` de `pytest.ini` racine, lu par `_portee` (N5, revue de clôture F5) : présent, il REMPLACE les
#: défauts, comme dans pytest (type `args`, `shlex.split`) ; absent, ini illisible ou iniconfig absent : `None`.
_NORECURSE_INI = None


def _portee():
    """Départs de la garde : la racine (pytest nu sans `testpaths`, `pytest .`, passe adoptant sous
    un ini généré SANS `testpaths`), puis chaque `testpaths` de `pytest.ini` racine qui désigne un
    dossier de l'arbre — lu par `iniconfig` (dépendance de pytest, import paresseux), découpé par
    `shlex.split` comme le type `args`, globbé comme pytest. Un départ n'est jamais élagué : c'est
    un initpath, et c'est ce qui garde `.agents/` (dossier point) dans la portée. Lit AUSSI
    `norecursedirs` du même ini (`_NORECURSE_INI`, que `_elague` applique)."""
    global _NORECURSE_INI
    departs = [()]
    try:
        import iniconfig  # paresseux : absent -> racine seule (borne m)
    except ImportError:
        return departs
    try:
        ini = iniconfig.IniConfig(os.path.join(_RACINE_1188, "pytest.ini"))
        section = ini["pytest"] if "pytest" in ini else None
        motifs = shlex.split(section.get("testpaths", "")) if section is not None else []
        brut = section.get("norecursedirs") if section is not None else None
        _NORECURSE_INI = tuple(shlex.split(brut)) if brut is not None else None
    except (OSError, ValueError, iniconfig.ParseError):  # ini absent ou illisible -> racine seule
        motifs = []
    for motif in motifs:
        for trouve in sorted(glob.glob(motif, root_dir=_RACINE_1188, recursive=True)):
            absolu = os.path.join(_RACINE_1188, trouve)
            rel = os.path.relpath(absolu, _RACINE_1188).replace(os.sep, "/")
            if os.path.isdir(absolu) and rel != "." and rel != ".." and not rel.startswith("../"):
                departs.append(tuple(rel.split("/")))
    return departs


def _apparie(chemin, nom, motif):
    """`fnmatch_ex` de pytest 9.1.1 (_pytest/pathlib.py), posix : un motif SANS séparateur se compare au NOM, un
    motif AVEC au chemin absolu (préfixé `*/` s'il est relatif) ; `fnmatch` sensible à la casse sous posix."""
    if os.sep not in motif:
        return fnmatch.fnmatch(nom, motif)
    return fnmatch.fnmatch(chemin, motif if os.path.isabs(motif) else "*" + os.sep + motif)


def _elague(chemin, nom):
    """Vrai si pytest 9.1.1 ne DESCEND pas dans ce dossier (`pytest_ignore_collect`) :
    `__pycache__`, venv (`pyvenv.cfg` ou `conda-meta/history`, lus sur disque), ou dossier apparié
    par `norecursedirs` — celui de `pytest.ini` racine s'il en porte un, qui REMPLACE les défauts
    comme dans pytest (N5), sinon les défauts (`_apparie` = `fnmatch_ex`)."""
    if nom == "__pycache__":
        return True
    if os.path.isfile(os.path.join(chemin, "pyvenv.cfg")) or os.path.isfile(
            os.path.join(chemin, "conda-meta", "history")):
        return True
    motifs = _NORECURSE_1188 if _NORECURSE_INI is None else _NORECURSE_INI
    return any(_apparie(chemin, nom, motif) for motif in motifs)


def _nomme(nom):
    """Un nom de fichier que pytest charge sans argument : conftest ou module de test par défaut. `conftest.py`
    se compare SANS la casse (avis sécu A2) : sur un FS insensible à la casse (APFS, NTFS), pytest charge
    `Conftest.py` par `is_file()` ; sur un FS sensible, ce refus est un faux rouge déclaré."""
    return (nom.casefold() == "conftest.py" or fnmatch.fnmatch(nom, "test_*.py")
            or fnmatch.fnmatch(nom, "*_test.py"))


def _amorce(chemin, nom):
    """(e1) Vrai si `chemin` est un dossier `test*` (casse posix, comme `Path.glob`) qui porte un
    `conftest.py` : pytest le charge à l'AMORCE pour tout parent ancre, ÉLAGUÉ OU NON
    (_pytest/config/__init__.py:654-659)."""
    return fnmatch.fnmatchcase(nom, "test*") and os.path.isfile(os.path.join(chemin, "conftest.py"))


def _illisible(rel, cause, strict):
    """Un dossier ignoré illisible, un lien ignoré cassé ou à cible illisible : sous un départ de pytest nu
    (`strict`), refus nommé, fail-closed ; ailleurs, sauté — pytest nu n'y descend pas."""
    if strict:
        raise pytest.UsageError("T-00001188 : porte REFUSÉE — %s dans la portée de pytest nu : %s ; remède : le"
                                " supprimer ou le sortir de l'arbre" % (cause, rel or ".")) from None


def _marcher(depart, sortie, inits, strict, vus, compte):
    """(c) Parcours itératif à pied d'un dossier ignoré, mêmes élagages que pytest ; un dépôt
    imbriqué ou un worktree enregistré y est parcouru comme le reste. Remplit `sortie` (refusés)
    et `inits` (`__init__.py` ignorés, jugés par (d)). (b) Un lien vers un dossier non élagué est
    SUIVI comme pytest le suit (décision pilote `decision/T-00001188/04`) ; seul son contenu est
    jugé. `vus` ((dev, ino) -> strict), PARTAGÉ par toutes les marches d'une garde, dossiers réels
    compris : un dossier n'est parcouru qu'UNE fois — une seconde seulement si la première était
    hors départ et celle-ci sous un départ —, donc une boucle de liens termine et un sous-arbre
    atteint par deux chemins n'est pas reparcouru. Le `stat` se fait au DÉPILEMENT, protégé : un
    lien qui disparaît ne fait sauter aucune entrée voisine. `compte` : entrées parcourues, borné
    par `_PLAFOND`. Dossier illisible, lien cassé ou cible illisible : `_illisible` (`strict` =
    parcours sous un départ de pytest nu)."""
    pile = [depart]
    while pile:
        d = pile.pop()
        chemin = os.path.join(_RACINE_1188, d) if d else _RACINE_1188
        try:
            st = os.stat(chemin)
        except FileNotFoundError:
            if os.path.islink(chemin):
                _illisible(d, "lien git-ignoré cassé", strict)
            continue  # dossier disparu entre le listage git et le parcours
        except OSError as exc:
            _illisible(d, "cible git-ignorée illisible (%s)" % (exc.strerror or exc), strict)
            continue
        # Sans inode stable (st_ino == 0 : FAT/exFAT, certains montages réseau), tous les dossiers auraient la même
        # clé et la garde ne parcourrait plus rien (fail-open) : pas de déduplication, `_PLAFOND` borne la marche.
        cle = (st.st_dev, st.st_ino) if st.st_ino else None
        if vus.get(cle) or (cle in vus and not strict):
            continue  # déjà parcouru : boucle de liens, ou sous-arbre atteint par un autre chemin
        if cle is not None:
            vus[cle] = strict
        try:
            entrees = os.scandir(chemin)
        except FileNotFoundError:
            continue  # dossier disparu entre le stat et l'ouverture
        except OSError as exc:
            _illisible(d, "dossier git-ignoré illisible (%s)" % (exc.strerror or exc), strict)
            continue
        try:
            with entrees:
                for e in entrees:
                    compte[0] += 1
                    if compte[0] > _PLAFOND:
                        raise pytest.UsageError(
                            "T-00001188 : porte REFUSÉE — plus de %d entrées git-ignorées à parcourir (en cours :"
                            " %s) ; remède : sortir ce dossier, ou le lien qui y mène, de l'arbre, ou le faire élaguer"
                            " par pytest (venv, dossier point, nom de norecursedirs par défaut)" % (_PLAFOND, d or "."))
                    rel = d + "/" + e.name if d else e.name
                    if e.is_symlink() and not os.path.exists(e.path):
                        _illisible(rel, "lien git-ignoré cassé", strict)
                    elif e.is_dir():
                        if not _elague(e.path, e.name):
                            pile.append(rel)  # dossier réel, ou lien SUIVI (b) : jugé au dépilement
                        elif _amorce(e.path, e.name):
                            sortie.add(rel + "/conftest.py")
                    elif _nomme(e.name):
                        sortie.add(rel)
                    elif e.name == "__init__.py":
                        inits.add(rel)
        except OSError as exc:  # une erreur en cours de lecture n'est jamais un `continue` muet
            _illisible(d, "lecture d'un dossier git-ignoré interrompue (%s)" % (exc.strerror or exc), strict)


def _git_1188(env, *args):
    """Un appel git sans fsmonitor, sans cache des non-suivis, sans hook ; FAIL-CLOSED nommé."""
    try:
        cp = subprocess.run(
            ["git", "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false",
             "-c", "core.hooksPath=" + os.devnull, *args],
            cwd=_RACINE_1188, env=env, capture_output=True, timeout=_DELAI, check=False)
    except subprocess.TimeoutExpired:
        raise pytest.UsageError("T-00001188 : porte REFUSÉE — `git %s` a dépassé %d s (fail-closed)"
                                % (args[0], _DELAI)) from None
    if cp.returncode:
        lignes = cp.stderr.decode("utf-8", "replace").strip().splitlines()
        raise pytest.UsageError(
            "T-00001188 : porte REFUSÉE — `git %s` rc=%d (fail-closed) : %s ; remèdes : déclarer la racine"
            " dans `safe.directory`, ou un `.git` fichier de worktree qui pointe hors du conteneur"
            % (args[0], cp.returncode, lignes[0] if lignes else "(stderr vide)"))
    return cp.stdout


def _refuses(env):
    """Les fichiers ignorés NON SUIVIS que pytest chargerait (règle (a)-(e), docstring de
    `_garde_1188`), triés. `ls-files -o -i --directory` SANS pathspec : git ne descend pas dans un
    dossier ignoré, la garde le parcourt à pied ; `--exclude-standard` lit aussi `.git/info/exclude`."""
    brut = _git_1188(env, "ls-files", "-o", "-i", "--exclude-standard", "--directory", "-z")
    entrees = sorted(os.fsdecode(x) for x in brut.split(b"\0") if x)
    departs = _portee()
    ancres = set(departs[1:]) or {()}  # départs de pytest NU : ses testpaths, sinon la racine
    sortie, inits, parcourus = set(), set(), []
    vus, compte = {}, [0]  # partagés par TOUTES les marches de cette garde (voir `_marcher`)
    for e in entrees:
        if any(e.startswith(p) for p in parcourus):
            continue
        dossier = e.endswith("/")
        comps = tuple(c for c in e.split("/") if c)
        for dep in sorted(departs, key=lambda x: x not in ancres):  # sous un départ d'abord : marche stricte
            if comps[:len(dep)] == dep:
                cur, elague = list(dep), False
                for c in (comps[len(dep):] if dossier else comps[len(dep):-1]):
                    cur.append(c)
                    if _elague(os.path.join(_RACINE_1188, *cur), c):
                        elague = True
                        break
                if elague:
                    # (e1) dossier élagué de nom test* : son conftest.py est chargé à l'amorce.
                    if (tuple(cur) == comps or (not dossier and tuple(cur) + ("conftest.py",) == comps)) \
                            and _amorce(os.path.join(_RACINE_1188, *cur), cur[-1]):
                        sortie.add("/".join(cur) + "/conftest.py")
                    continue
                if dossier:
                    parcourus.append(e)
                    _marcher("/".join(comps), sortie, inits, dep in ancres, vus, compte)
                else:
                    absolu = os.path.join(_RACINE_1188, *comps)
                    if os.path.islink(absolu) and not os.path.exists(absolu):
                        _illisible(e, "lien git-ignoré cassé", dep in ancres)
                    elif os.path.islink(absolu) and os.path.isdir(absolu):
                        if not _elague(absolu, comps[-1]):
                            _marcher(e, sortie, inits, dep in ancres, vus, compte)  # (b) décision /04 : suivi
                        elif _amorce(absolu, comps[-1]):
                            sortie.add(e + "/conftest.py")
                    elif _nomme(comps[-1]):
                        sortie.add(e)
                    elif comps[-1] == "__init__.py":
                        inits.add(e)
            elif dossier and len(dep) > len(comps) and dep[:len(comps)] == comps:
                _marcher("/".join(dep), sortie, inits, dep in ancres, vus, compte)  # un testpath SOUS un dossier ignoré
    # (e2) conftest.py ignoré d'un dossier ANCÊTRE d'un testpath, entre la racine et lui.
    fichiers = {x.rstrip("/") for x in entrees}
    dossiers = [x for x in entrees if x.endswith("/")]
    for dep in departs:
        for i in range(1, len(dep)):
            cand = "/".join(dep[:i]) + "/conftest.py"
            if os.path.isfile(os.path.join(_RACINE_1188, cand)) and (
                    cand in fichiers or any(cand.startswith(x) for x in dossiers)):
                sortie.add(cand)
    # (d) __init__.py ignoré, ancêtre d'un module de test SUIVI — ignoré OU NON (P12 : info/exclude).
    if inits:
        suivis = _git_1188(env, "ls-files", "-c", "-z")
        tests = [x for x in (os.fsdecode(y) for y in suivis.split(b"\0") if y) if _nomme(os.path.basename(x))]
        for i in inits:
            d = os.path.dirname(i)
            if any(x.startswith(d + "/" if d else "") for x in tests):
                sortie.add(i)
    return sorted(sortie)


def _garde_1188():
    """T-00001188 — pytest nu REFUSE (rc 4, `pytest.UsageError`) un fichier non suivi sous un chemin
    git-ignoré qu'il CHARGERAIT ; rend la cause d'une inactivité (annoncée en fin de run), ou None.
    Décision pilote S-01M4N7Q58FJ1SJ9W6TKYY446Y2 : aucun intérêt légitime à des tests sous un dossier
    ignoré — un test qui doit vivre là se SUIT (`git add -f` : joué, jamais refusé).

    RÈGLE = ce que pytest 9.1.1 CHARGE, AMORCE des conftests comprise. PORTÉE = la racine ∪ chaque
    `testpaths` de `pytest.ini` racine. ÉLAGUÉ (jamais descendu) : `__pycache__`, venv, `norecursedirs`
    de `pytest.ini` racine, sinon par défaut. REFUSÉS, parmi les fichiers ignorés non suivis : (a) `conftest.py`, `test_*.py`,
    `*_test.py` dans la portée non élaguée ; (b) lien ignoré vers un dossier non élagué : SUIVI comme
    pytest le suit, une fois par (dev, ino) — une boucle de liens termine —, et jugé par son SEUL
    contenu (décision pilote `decision/T-00001188/04`, qui remplace « refusé, jamais suivi » du plan
    rév. 7 : un lien vers un dossier de données n'est plus refusé) ; (c) contenu d'un dossier ignoré
    parcouru à pied, dépôt imbriqué et worktree enregistré compris ; (d) `__init__.py` ancêtre d'un
    module de test SUIVI ; (e1) `D/test*/conftest.py`, élagué ou non, pour tout D parcouru ; (e2)
    `conftest.py` d'un ancêtre d'un testpath. Un dossier ignoré illisible, un lien ignoré cassé ou à
    cible illisible, SOUS un départ de pytest nu (ses `testpaths`, sinon la racine), arrête la garde
    (fail-closed nommé) ; ailleurs il est sauté : pytest nu n'y descend pas. Un lien CASSÉ est ainsi
    refusé alors que pytest l'ignore (`_pytest/pathlib.py` scandir) : faux rouge voulu, fail-closed.
    Toutes les marches d'une garde partagent un seul ensemble (dev, ino), dossiers réels compris : un
    sous-arbre n'est jamais reparcouru (sauf pour passer de « hors départ » à « sous un départ ») ; et
    elles sont BORNÉES à `_PLAFOND` entrées : au-delà, refus fail-closed qui nomme le dossier en cours
    — faux rouge pour un dossier ignoré NON élagué de plus de `_PLAFOND` entrées dans la portée.

    BORNES (L-00000187 : inventaire MESURÉ, NON clos — un chemin hors liste est une borne non
    déclarée, jamais une couverture), rangées par chemin de chargement de pytest 9.1.1 :
    (a) conftest racine jamais chargé : `--noconftest`, `-c`/`--rootdir`/`--confcutdir` qui déplacent
        la racine, fichier de config ignoré planté dans le dossier visé OU à la racine à un rang
        supérieur (`pytest.toml`/`.pytest.toml` priment sur `pytest.ini` : findpaths.py:167-173 ; au
        kit aucun de ces noms n'est ignoré, mesuré). « Chemin explicite compris » est tenu pour tout
        dossier NON élagué de la portée (`pytest .agents/state/local` rc 4, mesuré) HORS borne (a) :
        un fichier de config planté dans le dossier visé déplace rootdir et confcutdir, la garde ne se
        charge pas (mesuré : `pytest.ini` vide ou `tox.ini [pytest]` dans `.agents/state/local` ->
        rc 0 + 2 canaris) ; ni l'option A ni l'option B ne ferment (a).
    (b) chargé AVANT la garde : `-p`, `PYTEST_PLUGINS`, `addopts`/`PYTEST_ADDOPTS`, entry points
        `pytest11` (dont un `*.egg-info`/`*.dist-info` ignoré sur `sys.path`), `.pyc` forgé de ce
        conftest, `.pth`/`sitecustomize` d'un venv du dépôt ; `__init__.py` ignoré À LA RACINE quand
        le nom du dossier racine est un identifiant python : ce conftest s'importe alors comme
        `<racine>.conftest` et ce `__init__.py` s'exécute AVANT la garde (prepend, importlib ; mesuré
        rc 0 + canaris sous charge utile) — le kit n'est pas concerné (`kit-couloir-b`).
    (c) `.pyc` forgé d'un module SUIVI.
    (d) `.py` ignoré importé par du code SUIVI (`_version.py`, `pytest_plugins`) ou qui masque un
        module par son nom (cwd en tête de `sys.path`, `pythonpath` d'ini) — non mesuré ; lien
        VERSIONNÉ (suivi par git, hors des ignorés parcourus) de la portée vers un dossier ignoré
        ÉLAGUÉ : pytest le parcourt, la garde non (mesuré rc 0 + 2 canaris ; 0 lien versionné au
        kit) — la décision /04 ne vaut que pour un lien IGNORÉ. Un `__init__.py` ignoré ancêtre
        d'un test suivi est REFUSÉ.
    (e) `python_files` d'adoptant, `--doctest-modules`, fichier de nom quelconque passé en argument.
    (f) argument EXPLICITE vers un dossier ÉLAGUÉ — point, venv, `norecursedirs` —, à la racine ou
        sous un testpath (mesuré : `pytest .hid/` rc 0 + canari) ; `pytest` lancé depuis un
        sous-dossier (pytest ignore alors `testpaths`) ; `--collect-in-virtualenv` ; `--keepduplicates`
        avec un testpath imbriqué sous un dossier élagué d'un autre testpath (mesuré rc 0 + canari ;
        sans l'option pytest normalise les arguments) ; `collect_ignore*` d'un conftest suivi (la
        garde refuse PLUS que pytest). Un dossier NON élagué ignoré est REFUSÉ même nommé.
    (g) fichier VISIBLE non suivi : `git status` le montre.
    (h) worktree enregistré HORS portée : non parcouru, pytest n'y descend pas.
    (i) adoptant : la garde ne tourne qu'au module python RACINE de `porte_adoptant.py`, joué en
        premier ; ses sous-modules sont joués après, sans elle ; sans module racine, jamais.
    (j) fichier planté APRÈS l'import, ou 2e `pytest.main` dans le même processus.
    (k) bash : un `.sh` ignoré SOURCÉ ou exécuté par une suite suivie (run-bash-tests.sh).
    (l) sous-module git : ses ignorés ne sont pas listés par le superprojet.
    (m) config hors `pytest.ini` racine (pyproject, tox.ini, setup.cfg, `-c`) : ni `testpaths` (racine
        seule) ni `norecursedirs` (défauts de pytest 9.1.1) NON lus ; ceux de `pytest.ini` racine le sont
        (N5 : son `norecursedirs` REMPLACE les défauts, comme dans pytest).
    (n) INACTIVE annoncée, jamais muette : `.git` absent À CÔTÉ de ce conftest (projet sous-dossier d'un
        dépôt). `.git` présent et git absent du PATH : REFUS fail-closed (avis sécu A1), jamais inactive.
        `Conftest.py` de casse quelconque est refusé (A2) : faux rouge sur un FS sensible à la casse.
        Non mesurés : Windows, Python < 3.14, pytest autre que 9.1.1."""
    if not os.path.lexists(os.path.join(_RACINE_1188, ".git")):
        return "pas de .git à côté du conftest racine"
    sans_git = ("T-00001188 : porte REFUSÉE — `.git` présent mais git absent du PATH : la garde ne peut pas lister"
                " les fichiers ignorés (fail-closed) ; remède : installer git ou le mettre au PATH")
    if shutil.which("git") is None:
        raise pytest.UsageError(sans_git)
    env = {k: v for k, v in os.environ.items() if not git_herite(k)}
    env["LC_ALL"] = "C"
    try:
        refuses = _refuses(env)
    except FileNotFoundError:
        raise pytest.UsageError(sans_git) from None
    if refuses:
        raise pytest.UsageError(
            "T-00001188 : porte REFUSÉE — %d fichier(s) non suivi(s) sous un chemin git-ignoré que pytest"
            " chargerait : %s ; remède : supprimer le fichier (ou le lien ignoré qui y mène) ou le sortir de"
            " l'arbre ; un __init__.py nommé est le paquet d'un test SUIVI : le suivre (git add -f) ou retirer"
            " sa règle d'ignore"
            % (len(refuses), ", ".join(refuses[:50]) + (" (+%d)" % (len(refuses) - 50) if len(refuses) > 50 else "")))
    return None


_INACTIVE_1188 = _garde_1188()


def pytest_terminal_summary(terminalreporter):
    """T-00001188 : une garde INACTIVE est dite, jamais muette."""
    if _INACTIVE_1188:
        terminalreporter.write_line("T-00001188 : garde fichiers ignorés INACTIVE (%s)" % _INACTIVE_1188)


@pytest.fixture(scope="session", autouse=True)
def _isolation_git_session():
    """T-00000695/696, critic-opus T1 (GRAVE) — un banc lancé DEPUIS UN HOOK GIT
    hérite de `GIT_DIR`, que git exporte à ses hooks, et `verify.sh` est appelable
    depuis un hook. Mesuré : avec `GIT_DIR` pointé sur un dépôt hôte jetable, le
    `_Depot()` de `test_affirmation_guard_fenetre.py` a créé un commit DANS
    L'HÔTE, écrasé son `HEAD:AGENTS.md` et remplacé son `user.email` — `git -C`
    ne corrige rien, `GIT_DIR` l'emporte. Classe déjà nommée par
    `.githooks/commit-msg.test.sh:23-30`, qui `unset` les siennes.

    On RETIRE ces variables (`git_herite`) de l'environnement du processus pour
    toute la session, et on RESTAURE les valeurs d'origine à la fin. Ce filet ne
    couvre QUE ce qui passe par pytest. HORS pytest, ce fichier n'est pas chargé,
    et la couverture est celle-ci, fichier par fichier — rien au-delà :
      · `python3 -B agentic_v3/tests/test_run_export.py` : son bloc `__main__`
        retire les mêmes variables avant `unittest.main()`, et `_base_env`
        filtre les siennes ;
      · `python3 -B .agents/evals/test_affirmation_guard_fenetre.py` : chaque
        sous-processus reçoit `_env()`, filtré ;
      · `.agents/bin/test_tasks.py` : ne filtre QUE dans la classe qui déclare
        la liste (mesuré : lancé avec `GIT_DIR` sur un hôte jetable, l'hôte
        reste identique) ;
      · NON COUVERTS : `agentic_v3/tests/test_board_bridge.py` lancé hors
        pytest (ses fixtures d'isolation sont des fixtures pytest : il écrit
        alors dans l'arbre de `GIT_WORK_TREE`, ou, sans lui, dans le `runs/` du
        dépôt COURANT — mesuré, et laissé à une décision) ; et toute forme
        `python -m unittest <module>`, qui ne charge ni ce fichier ni les blocs
        `__main__` — seuls les sites qui filtrent leur propre `env` y tiennent.
    ET UNE BORNE : un `git -c safe.directory=…` hérité par la session est retiré
    avec le reste ; un banc qui lirait le dépôt RÉEL sous un propriétaire
    douteux (conteneur) le perdrait. `verify.sh` ne transmet pas l'env de l'hôte
    à `docker run`, donc sa jambe conteneur n'en hérite pas."""
    sauvees = {k: os.environ.pop(k) for k in list(os.environ) if git_herite(k)}
    try:
        yield
    finally:
        for k in [k for k in os.environ if git_herite(k)]:
            os.environ.pop(k, None)
        os.environ.update(sauvees)


@pytest.fixture(autouse=True)
def _subprocess_isolation_net():
    before = {name: getattr(subprocess, name) for name in _WATCHED}
    yield
    leaked = [name for name in _WATCHED if getattr(subprocess, name) is not before[name]]
    # Réparer d'abord : couper la cascade même si l'assertion ci-dessous échoue.
    for name in leaked:
        setattr(subprocess, name, before[name])
    assert not leaked, (
        "fuite d'isolation pytest : l'attribut "
        + ", ".join("subprocess." + name for name in leaked)
        + " a été remplacé sur le module partagé du processus et non restauré. "
        "Une assignation nue (subprocess." + leaked[0] + " = ...) empoisonne tous "
        "les tests collectés ensuite. Remède : encadre la mutation par "
        "mock.patch.object(mod.subprocess, \"" + leaked[0] + "\", ...) ou "
        "monkeypatch.setattr(subprocess, \"" + leaked[0] + "\", ...), qui "
        "restaurent l'attribut d'origine à la sortie."
    )
