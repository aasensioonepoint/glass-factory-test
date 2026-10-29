"""LES DEUX PREMIERES SURFACES QUE `cadre init` GENERE CHEZ L'ADOPTANT.

Le noyau s'installe une fois par poste ; `cadre init --host X` s'invoque une fois
par projet. Ce module rend le TEXTE de deux fichiers que ce second geste depose
dans le depot de l'adoptant : son `pytest.ini` et son `.gitignore`. Il rend une
chaine et n'ecrit rien — l'ecriture appartient a `Workspace`, comme partout
ailleurs dans ce paquet.

TROIS CONTRAINTES, ET AUCUNE N'EST NEGOCIABLE.

`STDLIB SEULE, DONC `str.format` ET AUCUN MOTEUR DE GABARIT.` La table
`dependencies` de `pyproject.toml` est VIDE et le reste : c'est elle qui rend
vraie l'affirmation « rien ne part de la machine », et c'est elle qu'un scan de
dependances verifie en une ligne. Ajouter Jinja ici couterait cette propriete
pour substituer trois trous. Consequence a connaitre avant d'editer un gabarit :
une accolade LITTERALE devrait y etre doublee. Les deux gabarits livres n'en
portent aucune, et c'est la raison pour laquelle ils n'en portent aucune.

`LES GABARITS SONT ATTEINTS PAR `pkg_root()` SEUL.` Ni `__file__` — le check
`no_hardcoded_paths` n'autorise le seul `__file__` du noyau que dans `paths.py`,
faute de quoi le paquet cesse d'etre deplacable — ni une racine git, parce qu'il
n'y a AUCUN depot garanti chez l'adoptant : `cadre init` peut tres bien tourner
sur un repertoire qui n'a pas encore vu `git init`.

`LA LECTURE PASSE PAR `Workspace`.` Ce module DECIDE, il n'est donc pas une des
trois primitives et `check_orchestration_purity` le couvre : une lecture sur un
`Path` nu y serait refusee. `Workspace(pkg_root())` confine en prime la lecture
sous le paquet, ce qui rend un gabarit hors racine impossible plutot
qu'improbable.

LA COUTURE D'E/S PASSE ENTIEREMENT PAR `Workspace`. Ce module ne fait AUCUNE E/S
hors couture — et cet absolu est BORNE : il est tenu par `check_orchestration_purity`,
dont le jeu de verbes surveilles n'est PAS clos. Il manque SEIZE noms au jeu
GLOBAL, en DEUX familles : les TROIS (`exists`, `is_file`, `stat`) que seul le
banc LOCAL du service ledger couvre, et les TREIZE (plan §1.1) jamais enumeres
NULLE PART — auxquels s'ajoutent, hors compte, un alias d'import ou un `getattr`
dynamique qui echappent au controle par attribut. Donc « aucune » signifie
« aucun verbe SURVEILLE » et non une preuve d'exhaustivite ; la borne vit dans le
`resume` du manifeste. La decouverte des repertoires de bancs passe par
`Workspace.walk` (parcours ELAGUE, confine sous la racine) et le refus d'une
racine inexistante par `Workspace.est_repertoire`. `check_orchestration_purity`
les COUVRE donc sans exemption — l'E/S se fait derriere un `Workspace` declare
(`atelier = Workspace(racine)`), et un appel sur un `Path` nu y serait refuse.

C'est ce que T-00000633 a livre. AVANT elle, ce module faisait trois E/S HORS
couture — `os.walk` (decouverte), `Path.resolve()` (ancrage de la racine) et
`Path.is_dir()` (refus d'une racine inexistante) — faute d'une primitive de
parcours ELAGUE. L'alternative d'alors, un `Workspace.iter_files("**/*")`, etait
PIRE et c'est mesure : elle n'elague rien, donc elle descend dans `.git`,
`node_modules` et `.venv` EN ENTIER, echangeant trois E/S hors couture contre un
parcours qui ramasse les bancs de quelqu'un d'autre. `Workspace.walk` prend un
PREDICAT d'elagage (`ELAGAGE.__contains__`) et LEVE sur un repertoire illisible
au lieu de l'avaler : la politique d'elagage reste ICI, le parcours confine est
dans le noyau.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from cadre.paths import pkg_root
from cadre.workspace import HorsRacine, Workspace

__all__ = [
    "GABARITS",
    "ELAGAGE",
    "JETABLE",
    "Store",
    "STORES",
    "repertoires_de_test",
    "rendre_pytest_ini",
    "rendre_gitignore",
]

#: Sous-repertoire des gabarits, RELATIF au paquet. Un repertoire neuf sous
#: `src/cadre/data/` entre dans la wheel sans aucune declaration `package-data` —
#: `[tool.hatch.build.targets.wheel] packages = ["src/cadre"]` prend l'arbre. La
#: propriete est MESUREE par un banc plutot que supposee ici, parce qu'une
#: ressource absente de la wheel ne se manifeste qu'a l'installation.
GABARITS = "data/gabarits"

#: Repertoires ELAGUES pendant la decouverte des bancs.
#:
#: COPIE DE `SKIP_DIRS` (`.agents/bin/build_index.py`), ET LA DUPLICATION EST LE
#: COUT ASSUME D'UNE CONTRAINTE, PAS UNE NEGLIGENCE. L'original vit dans
#: l'outillage du depot, HORS de la wheel : le noyau ne peut pas l'importer sans
#: cesser d'etre installable seul. Les deux listes peuvent donc diverger.
#:
#: « ET RIEN NE LE SIGNALERA » — c'est ce que disait cette ligne, et le binome de
#: cloture l'a INFIRMEE : un banc de `.agents/evals/` vit HORS de la wheel, donc
#: il peut importer les DEUX et comparer. La contrainte porte sur le NOYAU, pas
#: sur l'outillage qui le verifie. Le filet existe desormais —
#: `test_cadre_init_surfaces.py::test_l_elagage_couvre_au_moins_SKIP_DIRS`.
#:
#: IL COMPARE DANS UN SEUL SENS — `SKIP_DIRS - ELAGAGE` doit etre VIDE — et le
#: sens compte. L'egalite naitrait rouge, parce que cette liste-ci porte
#: legitimement DIX entrees de plus (ci-dessous) ; c'est l'inclusion qui dit la
#: propriete voulue : « `SKIP_DIRS` a grossi et `ELAGAGE` ne l'a pas suivi ».
#:
#: L'ELAGAGE N'EST PAS COSMETIQUE, IL EST LA LEÇON PAYEE. Un parcours SANS
#: elagage a deja compte 32 suites la ou il y en avait 16
#: (`core-scripts/run-bash-tests.sh`) : les copies vendorisees, les caches et les
#: arbres de dependances portent des fichiers qui RESSEMBLENT a des bancs, et un
#: `testpaths` qui les nomme fait tourner les bancs de quelqu'un d'autre.
#: DIX ENTREES QUI NE VIENNENT PAS DE `SKIP_DIRS`, et c'est l'ecart le plus utile
#: de cette liste — trouve par le binome de cloture, MESURE, pas raisonne.
#:
#: LA CAUSE RACINE EST UN CHANGEMENT DE CANAL, et sans elle l'ecart se lit comme
#: une lubie. `SKIP_DIRS` protege un parcours qui part de `git ls-files` : y
#: entrent les seuls fichiers SUIVIS, donc `build/`, `dist/` ou `.venv/` sont
#: absents de sa population PAR LE CANAL et non par la liste. Recopiee sous
#: `os.walk`, qui part du DISQUE, la liste perd cette protection-la : tout ce que
#: git ignorait silencieusement redevient visible. Les entrees ci-dessous sont
#: ce que ce changement de canal reclame, pas un gout.
#:
#: `build/`, `dist/`, `.eggs/`, `htmlcov/` sont les ARTEFACTS DE BUILD PYTHON ;
#: `.nox/`, `.ruff_cache/`, `.direnv/`, `.cache/`, `.pixi/` et `target/` sont les
#: caches et arbres d'outils que le monde reel depose a cote (`target/` vaut pour
#: Rust comme pour Maven, dont le `target/` porte des copies de bancs).
#:
#: CE QUE CET ELAGAGE COUTE, DIT PLUTOT QUE DECOUVERT : il mord PAR NOM et A
#: TOUTE PROFONDEUR, comme `SKIP_DIRS`. Un projet dont le code de production vit
#: reellement dans un repertoire nomme `target/` ou `.cache/` verra ses bancs
#: NON decouverts. C'est le meme arbitrage que `migrations/` et `coverage/`, deja
#: pris en amont ; le remede reste de nommer le chemin a la main.
#:
#: LE SCENARIO EXACT, et il rend ROUGE un projet qui etait VERT : un projet
#: portant `pkg/tests/test_x.py` et sa copie `build/lib/pkg/tests/test_x.py`
#: (artefact setuptools parfaitement banal) recevrait les DEUX repertoires dans
#: `testpaths`, et pytest rendrait `ERROR … import file mismatch`. Sans le
#: fichier genere, le meme projet collecte 1 banc et passe. Un gabarit qui casse
#: la porte de celui qui l'installe est le contraire de ce que `cadre init` doit
#: faire. Ce n'est PAS couvert par le `norecursedirs` par defaut de pytest : un
#: `testpaths` explicite outrepasse cet elagage.
ELAGAGE = frozenset({
    "build", "dist", ".eggs", "htmlcov",
    ".nox", ".ruff_cache", ".direnv", "target", ".cache", ".pixi",
    ".git", "node_modules", "vendor",
    "venv", ".venv", "__pycache__", ".sca-reports", "coverage",
    ".next", ".nuxt", ".svelte-kit", ".output", ".gradle", ".terraform",
    ".tox", ".mypy_cache", ".pytest_cache", ".idea", ".vscode",
    "Pods", "DerivedData", "bower_components", "third_party",
    "site-packages", "migrations", "__snapshots__",
})

#: Le seul bucket jetable du kit, ignore EN BLOC. Tout ce qu'il contient se
#: reconstruit, lateraux SQLite compris : une regle de repertoire les couvre,
#: donc ils n'ont pas a etre nommes un par un.
JETABLE = ".agents/state/local/"


@dataclass(frozen=True)
class Store:
    """Un store SQLite du kit, et les deux faits qui decident de sa regle.

    `chemin` est RELATIF a la racine du projet et SANS `/` initial : l'ancrage
    est ajoute au rendu, une seule fois, plutot que reecrit sur chaque ligne.
    """

    chemin: str
    suivi: bool
    wal: bool


#: LE STORE QUI VIT ENCORE SOUS LA RACINE, RELEVE SUR LE DEPOT PLUTOT QUE SUPPOSE
#: (2026-09-16). DEUX SORTIES, chacune avec sa desindexation : T-00000677 pour le
#: store V3 fige `.agents/state/v3_event_store.db` — sa base VIVANTE vit hors
#: depot, son historique est versionne par les exports `runs/` — et T-00000668
#: pour `.agents/state/index/index.db`, qui vit desormais sous la partition
#: machine (`cadre.paths.index_db()`), hors depot, et se reconstruit depuis les
#: `SYMBOLS*.md` versionnes. `suivi` vient de `git ls-files` ; `wal` vient d'un
#: `PRAGMA journal_mode` lu sur la base elle-meme, pas du code qui l'ouvre — ce
#: sont deux choses differentes, et c'est la base qui fait foi.
#:
#:   .agents/state/local/events.db     non suivi journal_mode = wal
#:
#: PLUS AUCUN STORE SUIVI (T-00000668). Les regimes 2 et 3 du gabarit sont donc
#: VIDES, et le rendu le DIT plutot que de laisser deux titres sans ligne.
#:
#: CE RELEVE EST UN LITTERAL, DONC IL PEUT GELER — et le binome de cloture a
#: nomme ce que ça couterait. Le jour ou un store change de mode journal ou de
#: statut de suivi chez son proprietaire, cette table dira toujours l'ancien
#: etat, et le rendu du `.gitignore` emettra — ou n'emettra pas — des regles sur
#: la foi d'un champ faux.
#: `test_cadre_init_surfaces.py::test_le_releve_des_stores_est_rejoue_sur_le_depot`
#: REJOUE le relevé sur les stores presents et rougit a la place.
STORES = (
    Store(".agents/state/local/events.db", suivi=False, wal=True),
)


def _est_un_banc(nom: str) -> bool:
    """Les deux seuls motifs, et ils sont les MEMES que ceux que le `pytest.ini`
    rendu declare a pytest. Deux listes divergentes feraient lister un
    repertoire dont le fichier serait ensuite ignore a la collecte."""
    return nom.endswith("_test.py") or (nom.startswith("test_") and nom.endswith(".py"))


def _checkout_imbrique(atelier: Workspace, rel: str) -> bool:
    """Vrai si le sous-repertoire `rel` est un AUTRE checkout que le projet.

    PAR MARQUEUR, JAMAIS PAR NOM : son `.git` est un REPERTOIRE (clone), ou un
    FICHIER dont la ligne `gitdir:` finit en `/worktrees/<nom>` (worktree lie).
    Tout le reste est garde — le sous-module absorbe (`gitdir: .../modules/...`),
    un `.git` absent, vide, illisible, ou qui n'est pas un fichier regulier.

    LA SEMANTIQUE EST CELLE DU PREDICAT DU RECENSEMENT DES PARCOURS
    (`.agents/evals/test_repo_walk_census.py`), PORTEE ET NON PARTAGEE : le noyau
    voyage seul dans la wheel et n'importe pas `.agents/`. La parite est epinglee
    par `test_cadre_init_worktrees.py` (W5), qui rejoue les deux predicats sur
    les memes contenus de `.git`.

    TROIS ECARTS, VOULUS ET ECRITS. (1) Le `.git` n'est LU que s'il est un
    fichier REGULIER (`identite`, feuille non suivie) : une FIFO bloquerait la
    lecture, et un LIEN n'est jamais suivi — la ou le recensement suit un lien
    vers un fichier. (2) `Workspace.read_bytes` lit le fichier EN ENTIER (la
    couture n'offre pas de lecture bornee) ; seuls ses 4096 premiers octets,
    decodes avec remplacement, sont juges, premiere ligne coupee aux fins de
    ligne universelles comme une lecture en mode texte. (3) `RuntimeError` rend
    FAUX : `Path.resolve()` la leve sur une boucle de liens sous Python 3.11 et
    3.12.

    AUCUN `str.replace` ICI : le filet de purete juge le NOM de la methode, pas
    son recepteur. Les antislashs d'un `gitdir:` Windows passent par `re.sub`.
    """
    marqueur = f"{rel}/.git"
    try:
        if atelier.est_repertoire(marqueur):
            return True
        feuille = atelier.identite(marqueur)
        if feuille is None or not feuille.est_regulier:
            return False
        tete = atelier.read_bytes(marqueur)[:4096]
    except (HorsRacine, OSError, RuntimeError):
        return False
    ligne = re.split(r"\r\n?|\n", tete.decode("utf-8", "replace"), maxsplit=1)[0]
    m = re.match(r"gitdir:\s*(.+?)\s*$", ligne)
    return bool(m and re.search(r"/worktrees/[^/]+/?$", re.sub(r"\\", "/", m.group(1))))


#: Octets du `.gitmodules` parses au plus (64 Ko) ; au-dela, rien n'est exempte.
_GITMODULES_MAX = 65_536


def _sous_modules_declares(atelier: Workspace) -> frozenset[str]:
    """Les chemins `path =` du `.gitmodules` de la RACINE, sans appel a `git`.

    EXISTE PARCE QUE LE MARQUEUR NE SUFFIT PAS A RECONNAITRE UN SOUS-MODULE.
    `git submodule add` d'un clone DEJA present laisse un `.git` REPERTOIRE, jamais
    absorbe (MESURE, git 2.55) : par son seul marqueur, ce sous-module declare
    serait pris pour un clone et perdu du `testpaths` selon la FACON dont il a
    ete ajoute. Ces chemins sont donc EXEMPTES de l'elagage — hors du predicat,
    dont la parite avec le recensement reste ainsi intacte.

    BORNES. Seul le `.gitmodules` de la RACINE est lu : un sous-module imbrique
    dans un sous-module ET non absorbe est elague (`git submodule absorbgitdirs`
    le range). La forme lue est celle que `git` ECRIT (`path = a/b`, cle
    insensible a la casse, guillemets englobants retires) ; une valeur commentee
    en ligne ou echappee n'est pas exemptee et retombe sur le marqueur. Un
    `.gitmodules` qui n'est pas un fichier regulier, ou illisible, n'exempte
    rien. Decodage AVEC REMPLACEMENT : un octet invalide n'efface que sa ligne.
    `_GITMODULES_MAX` octets PARSES au plus (la ligne que la borne coupe est
    ecartee), LIGNE A LIGNE et en temps LINEAIRE : une regex multi-ligne sur le
    texte entier etait quadratique sur des lignes vides (S-00003900). Le
    fichier, lui, est encore lu en entier (`Workspace.read_bytes` n'a pas de
    borne).
    """
    try:
        feuille = atelier.identite(".gitmodules")
        if feuille is None or not feuille.est_regulier:
            return frozenset()
        brut = atelier.read_bytes(".gitmodules")
    except (HorsRacine, OSError, RuntimeError):
        return frozenset()
    if len(brut) > _GITMODULES_MAX:
        brut = brut[:_GITMODULES_MAX].rpartition(b"\n")[0]
    chemins: set[str] = set()
    for ligne in re.split(r"\r\n?|\n", brut.decode("utf-8", "replace")):
        cle = re.match(r"[ \t]*path[ \t]*=", ligne, re.IGNORECASE)
        valeur = ligne[cle.end():].strip() if cle else ""
        if valeur:
            chemins.add(re.sub(r'^"(.*)"$', r"\1", valeur).rstrip("/"))
    return frozenset(chemins)


def _lire_gabarit(nom: str) -> str:
    """Le texte d'un gabarit, atteint par `pkg_root()` et lu par `Workspace`."""
    atelier = Workspace(pkg_root())
    return atelier.read_text(f"{GABARITS}/{nom}")


def repertoires_de_test(racine: Path) -> list[str]:
    """Les repertoires du projet CIBLE portant au moins un banc, tries.

    Chemins POSIX relatifs a `racine` ; la racine elle-meme, si elle porte un
    banc, sort comme `"."` — c'est ce que `testpaths` attend, et un `""` y serait
    lu comme une entree vide.

    L'ELAGAGE PASSE PAR LE PREDICAT `ELAGAGE.__contains__` DONNE A
    `Workspace.walk`, qui mord EN PLACE dans le parcours (`sous_reps[:] = ...`,
    seule forme qui empeche `os.walk` de descendre) : la POLITIQUE d'elagage
    reste ICI, le parcours confine est dans le noyau.

    UN REPERTOIRE ILLISIBLE EST UN REFUS, JAMAIS UNE OMISSION. `Workspace.walk`
    LEVE par defaut au lieu d'avaler comme `os.walk` ; ici on lui passe le
    collecteur `illisibles.append`, donc un repertoire en `chmod 000` portant des
    bancs est CAPTURE plutot que perdu (MESURE — un arbre portant `tests/` et un
    `secret/` illisible rendait `['tests']`, aucune erreur, aucune trace). Le
    `testpaths` produit serait alors AMPUTE, et la porte de l'adoptant passerait
    au VERT sur un sous-ensemble de ses bancs — ce qui est pire qu'un rouge,
    puisqu'un rouge se regarde. On leve donc, en NOMMANT les chemins.

    LES ERREURS SONT COLLECTEES PUIS LEVEES EN BLOC, et pas au fil de l'eau : le
    collecteur accumule pendant le parcours et cette fonction leve APRES, en
    NOMMANT les chemins — lever au PREMIER fautif ferait corriger l'adoptant un
    repertoire a la fois.

    SECONDE BORNE, ASSUMEE ET ECRITE : `Workspace.walk` passe `followlinks=False`.
    Un arbre de bancs atteint par un LIEN SYMBOLIQUE (motif monorepo, ou un
    `packages/x/tests` lie depuis la racine) n'est donc PAS decouvert, et ne
    produit ni erreur ni trace. Suivre les liens rouvrirait les BOUCLES et les
    SORTIES D'ARBRE — un lien vers `/` fait sortir le parcours du projet — que la
    primitive n'a aucun moyen de borner sans tenir un jeu d'inodes visites. Le
    remede est de nommer le chemin a la main dans le `pytest.ini` produit.

    TROISIEME BORNE : UN AUTRE CHECKOUT N'EST PAS DESCENDU, ET IL EST RECONNU PAR
    SON MARQUEUR, JAMAIS PAR SON NOM. Un worktree lie (un agent en pose sous
    `.claude/worktrees/`) ou un clone depose dans l'arbre porte une copie ENTIERE
    de bancs ; les lister ferait juger a la porte de l'adoptant le code d'une
    AUTRE branche (MESURE : `.claude/worktrees/agent-x/tests` et
    `third/clone/tests` sortaient dans le `testpaths`). `_checkout_imbrique` les
    reconnait a leur `.git` — un nom comme `.claude` laisserait passer un
    worktree pose ailleurs et perdrait un repertoire ordinaire nomme `worktrees`.
    SONT GARDES : le sous-module absorbe (`gitdir: .../modules/...`) et tout
    chemin `path =` du `.gitmodules` de la racine, meme non absorbe
    (`_sous_modules_declares`). EST ELAGUE, et c'est le cas a connaitre : un
    clone NON declare, ou un sous-module imbrique non absorbe — le remede est
    `git submodule absorbgitdirs`, ou nommer le chemin a la main. COUT : au plus
    deux resolutions de chemin et deux `stat` par sous-repertoire, une lecture de
    plus quand `.git` est un fichier ; un sous-repertoire declare n'en coute
    aucune ; une lecture du `.gitmodules` de la racine par appel. L'elagage
    mord sur la liste VIVANTE que `Workspace.walk` rend, la meme que celle ou
    `os.walk` descend.

    CONTRAT D'EXCEPTIONS : racine absente, fichier ou lien (pendant, ou vers
    un fichier), nom trop long (ENAMETOOLONG) -> `NotADirectoryError`, AVANT
    le parcours ; racine dont un PARENT refuse la traversee ->
    `PermissionError`, celle du `stat` d'`est_repertoire`, sur tout
    interpreteur (T-00000682, T-00001232) ; une autre erreur d'E/S sur la
    racine (EIO...) -> `OSError` brute, propagee.
    Une racine BOUCLE de liens -> `NotADirectoryError` a partir de 3.13, mais
    `RuntimeError` du `resolve` de `Workspace` en 3.11/3.12. Pendant le
    parcours : si TOUTES les erreurs collectees sont des `PermissionError`,
    `PermissionError` ; SINON `OSError` — seul un `FileNotFoundError`
    (repertoire disparu pendant le parcours) se regle en relancant. Chaque
    type est NOMME dans le message.
    """
    atelier = Workspace(racine)
    if not atelier.est_repertoire("."):
        # est_repertoire LEVE PermissionError sur EACCES (T-00001232) ; faux = absent,
        # fichier, nom trop long, boucle (3.13 et plus ; RuntimeError de resolve en 3.11/3.12)
        raise NotADirectoryError(
            f"racine de projet introuvable ou non repertoire : {atelier.racine}"
        )
    declares = _sous_modules_declares(atelier)
    trouves: set[str] = set()
    illisibles: list[OSError] = []
    for rel, sous_reps, fichiers in atelier.walk(
        elaguer=ELAGAGE.__contains__, sur_erreur=illisibles.append
    ):
        base = "" if rel == "." else f"{rel}/"
        # EN PLACE (`[:]`), AVANT le test de bancs : reaffecter le nom laisserait
        # `os.walk` descendre dans le checkout imbrique.
        sous_reps[:] = [
            nom for nom in sous_reps
            if f"{base}{nom}" in declares
            or not _checkout_imbrique(atelier, f"{base}{nom}")
        ]
        if any(_est_un_banc(f) for f in fichiers):
            trouves.add(rel)
    if illisibles:
        # LE TYPE DE LA LEVEE DEPEND DES TYPES COLLECTES.
        # `sur_erreur` recoit tout `OSError`. Si TOUTES sont des
        # `PermissionError`, on leve `PermissionError` ; SINON, OSError.
        detail = ", ".join(
            f"{e.filename} ({type(e).__name__})" for e in illisibles
        )
        if all(isinstance(e, PermissionError) for e in illisibles):
            raise PermissionError(
                f"{len(illisibles)} repertoire(s) illisible(s) sous {atelier.racine} : "
                f"{detail}. La decouverte des bancs s'arrete ici plutot que de "
                "rendre un `testpaths` AMPUTE : une porte verte sur un "
                "sous-ensemble des bancs est pire qu'un echec, parce qu'elle ne se "
                "regarde pas."
            )
        indice = (
            " Un repertoire disparu pendant le parcours (FileNotFoundError) se "
            "regle en relancant ; les autres types, non."
            if any(isinstance(e, FileNotFoundError) for e in illisibles) else ""
        )
        raise OSError(
            f"{len(illisibles)} erreur(s) de parcours sous {atelier.racine} : "
            f"{detail}. La decouverte des bancs s'arrete ici plutot que de "
            "rendre un `testpaths` AMPUTE : une porte verte sur un sous-ensemble "
            "des bancs est pire qu'un echec, parce qu'elle ne se regarde pas."
            f"{indice}"
        )
    return sorted(trouves)


def rendre_pytest_ini(racine: Path) -> str:
    """Le texte du `pytest.ini` a deposer a la racine du projet CIBLE.

    SANS AUCUN BANC, LA CLE `testpaths` EST OMISE — pas rendue vide. Omise pour
    LISIBILITE — une cle vide se lit comme une configuration oubliee ; les deux
    formes sont EQUIVALENTES pour pytest (`rc=5` dans les deux cas, MESURE),
    aucune ne rend la porte verte.

    CE CHOIX NE CORRIGE DONC RIEN, et l'ecrire ici evite qu'on le prenne pour un
    correctif : c'est l'appelant qui transforme un code de retour non nul en
    echec, jamais le contenu de ce fichier. Le remede a « aucun banc » est
    d'ecrire un banc.

    Racine absente, fichier, lien pendant ou vers un fichier, nom trop long
    -> `NotADirectoryError` ; parent non traversable -> `PermissionError` ;
    autre erreur d'E/S (EIO...) -> `OSError` brute ; boucle de liens ->
    `NotADirectoryError` a partir de 3.13, `RuntimeError` du constructeur de
    `Workspace` en 3.11/3.12 (T-00000682, T-00001232).
    """
    # MEME REFUS QUE `rendre_gitignore` et `repertoires_de_test` : une racine
    # absente ou fichier donne `NotADirectoryError` NOMME, un parent non
    # traversable `PermissionError` (T-00000682). La garde est REDONDANTE avec
    # celle de `repertoires_de_test` et le reste : elle refuse AVANT tout calcul.
    atelier = Workspace(racine)
    if not atelier.est_repertoire("."):
        # est_repertoire LEVE PermissionError sur EACCES (T-00001232) ; faux = absent,
        # fichier, nom trop long, boucle (3.13 et plus ; RuntimeError de resolve en 3.11/3.12)
        raise NotADirectoryError(
            f"racine de projet introuvable ou non repertoire : {atelier.racine}"
        )
    reps = repertoires_de_test(racine)
    # UN NOM DE REPERTOIRE PEUT RENDRE LE FICHIER ILLISIBLE, ET DE DEUX FAÇONS
    # DISTINCTES — c'est pour cela que le predicat a deux moitiés. `testpaths`
    # est une valeur MULTILIGNE : le SAUT DE LIGNE y est le separateur, et un
    # nom de repertoire qui en contient un se scinde en deux entrees.
    #
    # MESURE DU 2026-09-16, sur `[pytest]\ntestpaths =\n    <nom>\n` :
    #
    #   'a\nb'   -> configparser : ParsingError
    #              pytest        : rc=4, « unexpected line: 'b' »
    #   '#c'     -> configparser lit ''  (le chemin DISPARAIT en silence)
    #              pytest        : rc=0, et il COLLECTE `#c/test_c.py`
    #   'tests'  -> configparser lit '\ntests'   (le cas sain)
    #
    # Le premier mecanisme CASSE le fichier ; le second l'AMPUTE sans bruit — un
    # `#` ou un `;` en tete de valeur ouvre un commentaire INLINE. Les deux
    # meritent un refus, mais pas pour la meme raison, et le message le dit.
    #
    # ON REFUSE PLUTOT QUE D'ECHAPPER : aucune citation ne rend un saut de ligne
    # licite dans une valeur INI, donc « rendre quand meme » ne peut produire
    # qu'un fichier casse ou ampute. Le refus nomme le repertoire fautif, ce qui
    # est actionnable ; un rendu silencieux ne l'est pas.
    fautifs = [r for r in reps if not r.isprintable() or r.lstrip()[:1] in "#;"]
    if fautifs:
        raise ValueError(
            "nom(s) de repertoire impossibles a ecrire dans un `pytest.ini` : "
            f"{fautifs}. Un caractere NON IMPRIMABLE (saut de ligne, tabulation) "
            "CASSE le fichier — `testpaths` est multiligne, le saut de ligne y "
            "est le separateur, et configparser rend une `ParsingError` la ou "
            "pytest rend `rc=4 unexpected line`. Un `#` ou un `;` en tete AMPUTE "
            "le fichier en silence — la valeur devient un commentaire inline et "
            "le chemin DISPARAIT. Renomme le repertoire, ou nomme-le a la main "
            "dans un `pytest.ini` ecrit par toi."
        )
    bloc = "testpaths =\n" + "".join(f"    {r}\n" for r in reps) if reps else ""
    return _lire_gabarit("pytest.ini.tmpl").format(testpaths=bloc)


def rendre_gitignore(racine: Path) -> str:
    """Le texte du `.gitignore` a deposer a la racine du projet CIBLE.

    `racine` VALIDE, ELLE NE FAIT PAS VARIER LE RENDU, et le dire evite qu'un
    lecteur cherche une variation qui n'existe pas. Les trois regimes portent sur
    des chemins de CONTRAT — `.agents/` est un nom de contrat, les stores y sont
    a une place fixe — et ils s'ecrivent identiquement sur tout projet. Ils
    s'ecrivent aussi pour des stores qui n'existent pas ENCORE : les trois sont
    provisionnes paresseusement par leurs proprietaires, donc une regle
    conditionnee a leur presence au moment de l'init serait absente precisement
    le jour ou elle doit servir.

    Racine absente, fichier, lien pendant ou vers un fichier, nom trop long
    -> `NotADirectoryError` ; parent non traversable -> `PermissionError` ;
    autre erreur d'E/S (EIO...) -> `OSError` brute ; boucle de liens ->
    `NotADirectoryError` a partir de 3.13, `RuntimeError` du constructeur de
    `Workspace` en 3.11/3.12 (T-00000682, T-00001232).
    """
    atelier = Workspace(racine)
    if not atelier.est_repertoire("."):
        # est_repertoire LEVE PermissionError sur EACCES (T-00001232) ; faux = absent,
        # fichier, nom trop long, boucle (3.13 et plus ; RuntimeError de resolve en 3.11/3.12)
        raise NotADirectoryError(
            f"racine de projet introuvable : {atelier.racine}. `cadre init` genere "
            "un `.gitignore` DANS un projet ; il n'invente pas son repertoire."
        )
    # UN REGIME VIDE SE DIT (T-00000668) : plus aucun store n'est suivi, et deux
    # titres sans ligne laisseraient croire a un rendu tronque.
    suivis = "\n".join(
        f"# SUIVI, jamais ignore : /{s.chemin}" for s in STORES if s.suivi
    ) or "# (aucun store SQLite suivi)"
    # LA CONDITION EST `wal ET suivi`, ET LES DEUX MOITIES COMPTENT. Un store en
    # WAL qui vit SOUS le bucket jetable a deja ses lateraux couverts par la
    # regle de repertoire ; les renommer ici serait du bruit qui ferait douter de
    # la premiere regle.
    lateraux = "\n".join(
        f"/{s.chemin}-wal\n/{s.chemin}-shm" for s in STORES if s.wal and s.suivi
    ) or "# (aucun lateral a nommer : aucun store suivi)"
    return _lire_gabarit("gitignore.tmpl").format(
        jetable=f"/{JETABLE}", suivis=suivis, lateraux=lateraux,
    )
