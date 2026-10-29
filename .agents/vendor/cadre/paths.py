"""LE SEUL MODULE AUTORISÉ À RÉSOUDRE UN CHEMIN. Phase 1 de T-012.

Quatre racines, et rien d'autre ne les calcule. Tout le reste du noyau les
reçoit — c'est ce qui rend le paquet déplaçable, testable sous répertoire
temporaire, et installable ailleurs que dans le dépôt qui l'a produit.

    PKG_ROOT      le paquet lui-même, résolu par `importlib.resources`
    CONFIG_HOME   la configuration de l'utilisateur      ($CADRE_CONFIG_HOME)
    STATE_HOME    l'état MACHINE, hors dépôt             ($CADRE_STATE_DIR)
    PROJECT_ROOT  le dépôt de travail, qui contient `.agents/`

DEUX CHEMINS DÉRIVÉS, ET LA TABLE RESTE À QUATRE LIGNES. ``AGENTS_DIR`` se
dérive de ``PROJECT_ROOT`` ; ``STATE_PROJECT`` de ``STATE_HOME`` et de
``PROJECT_ROOT``. Ce sont des chemins RENDUS, calculés ici à partir des quatre
racines ci-dessus, et non des racines de plus : la table n'en porte donc aucun,
parce qu'elle énumère ce que ce module résout depuis l'ENVIRONNEMENT — et rien
de neuf n'y est résolu. ``index_db`` (T-00000668) est un troisième chemin rendu,
dérivé de ``STATE_PROJECT`` : l'emplacement UNIQUE du store SQLite de l'index,
hors dépôt.

POURQUOI UN SEUL MODULE. Le relevé du 2026-09-12, rejoué et ÉLARGI À SA
TROISIÈME FAMILLE, donne 35 fichiers Python hors bancs qui décident seuls d'où
est la racine : par ``__file__``, par ``git rev-parse``, ou par un ``--root``
dont le défaut vaut ``CLAUDE_PROJECT_DIR`` ou le répertoire courant.
Chacun réimplémente une politique de chemin légèrement différente, et aucune
n'est déplaçable : c'est ce qui empêche aujourd'hui d'installer le kit ailleurs
que là où il a été écrit. Le check ``no_hardcoded_paths`` refuse désormais ces
deux formes partout dans ``src/cadre/`` sauf ici.

PROJECT_ROOT GARDE LA SÉMANTIQUE DE ``git rev-parse --show-toplevel``, et c'est
une décision (D2) plutôt qu'une commodité. Le kit avait DEUX façons de trouver
sa racine — la remontée de marqueur et la racine git — qui divergent dès qu'un
sous-module ou un worktree entre en jeu. Une seule survit, et c'est la racine
git, parce que c'est celle que 36 sites du dépôt utilisaient déjà.

CE MODULE NE CRÉE ET N'ÉCRIT RIEN. La résolution LIT désormais le disque —
``project_root`` canonicalise chaque composant par ``os.scandir``/``os.lstat``
pour rendre la graphie que le système de fichiers porte (T-00000674) — mais elle
ne crée aucun répertoire et n'écrit aucun fichier : les écritures sont le travail
de ``Workspace``, l'exécution celui d'``Executor``. La frontière est explicite
parce qu'elle est ce qui rendra le déport possible plus tard — `paths` résout et
LIT pour résoudre, `Workspace` ÉCRIT, jamais l'inverse.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import unicodedata
from functools import lru_cache
from pathlib import Path

__all__ = [
    "CadrePathError",
    "pkg_root",
    "config_home",
    "state_home",
    "state_project",
    "index_db",
    "project_root",
    "nom_projet",
    "agents_dir",
    "canonique_disque",
    "vider_cache_racine",
]

# Le nom du répertoire projet est un NOM DE CONTRAT (décision D2) : aucun
# renommage, et il est écrit UNE fois ici plutôt que répété.
AGENTS_DIRNAME = ".agents"

_ENV_CONFIG = "CADRE_CONFIG_HOME"
_ENV_STATE = "CADRE_STATE_DIR"
_ENV_PROJECT = "CADRE_PROJECT_ROOT"


class CadrePathError(RuntimeError):
    """Une racine n'a pas pu être résolue, et le message dit laquelle et pourquoi.

    Jamais un ``None`` silencieux : un chemin absent qui se propage se manifeste
    plusieurs appels plus loin, sous une forme qui ne nomme plus sa cause.
    """


def pkg_root() -> Path:
    """La racine du paquet installé — là où vivent les référentiels embarqués.

    Résolue par le module lui-même plutôt que par ``importlib.resources.files``,
    et c'est délibéré : ce module EST dans le paquet, donc son propre
    emplacement est la réponse. ``importlib`` sert quand on doit atteindre une
    RESSOURCE ; ici on veut le répertoire, et il n'y a pas plus direct.

    C'est le SEUL ``__file__`` du noyau, et le check ``no_hardcoded_paths`` ne
    l'autorise qu'ici.
    """
    return Path(__file__).resolve().parent


def _from_env(nom: str) -> Path | None:
    brut = os.environ.get(nom, "").strip()
    return Path(brut).expanduser().resolve() if brut else None


def config_home() -> Path:
    """La configuration de l'utilisateur. ``$CADRE_CONFIG_HOME``, sinon XDG.

    Le repli suit la convention XDG plutôt qu'un chemin inventé : sur un poste
    qui la respecte déjà, la configuration du kit se range avec les autres.
    """
    force = _from_env(_ENV_CONFIG)
    if force is not None:
        return force
    xdg = _from_env("XDG_CONFIG_HOME")
    base = xdg if xdg is not None else Path.home() / ".config"
    return (base / "cadre").resolve()


def state_home() -> Path:
    """L'état MACHINE — caches, index, artefacts de run, journaux.

    CE QUI VIT ICI NE VIT PAS DANS LE DÉPÔT, et c'est la décision D3. Tout ce
    qui s'y trouve se reconstruit ; rien ne s'y perd qu'un rebuild ne rende.
    L'état d'ÉQUIPE — board, registre, specs — reste dans `.agents/state/`,
    partagé par git, et ne passe jamais par ici.
    """
    force = _from_env(_ENV_STATE)
    if force is not None:
        return force
    xdg = _from_env("XDG_STATE_HOME")
    base = xdg if xdg is not None else Path.home() / ".local" / "state"
    return (base / "cadre").resolve()


def _empreinte_de_racine(racine: Path) -> str:
    """L'empreinte d'une racine : ``as_posix()`` puis ``sha256``, tronquée à 16.

    Extraite pour être mesurable sur une racine FABRIQUÉE. Tant que le calcul
    était en ligne dans ``state_project``, la moitié « séparateur normalisé » de
    ``S-00001598`` n'était tenue par aucun témoin : sur POSIX ``str(Path)`` et
    ``as_posix()`` rendent les mêmes octets, donc retirer ``as_posix()`` passait
    au VERT sur les deux jambes de la porte (mesuré le 2026-09-20, par les DEUX
    critiques du binôme, indépendamment).

    Le ``surrogateescape`` rend la fonction utilisable par tout appelant de
    bibliothèque même sur un chemin non décodable : sans lui, ``state_project``
    levait ``UnicodeEncodeError`` là où le module promet ``CadrePathError``.
    """
    return hashlib.sha256(
        racine.as_posix().encode("utf-8", "surrogateescape")).hexdigest()[:16]


def state_project(depuis: str | os.PathLike[str] | None = None) -> Path:
    """La partition d'état MACHINE propre à UN projet, sous ``state_home()``.

    NORMALISATION, décision pilote (S-00001598, T-00000674) : le chemin canonique
    de la racine est ``resolve()``, canonicalisé par ``canonique_disque`` puis
    ``as_posix()`` — séparateur normalisé.

    - Pour une racine INEXISTANTE, la graphie tapée est conservée
      (canonicalisation NON STRICTE) : deux écritures d'un même répertoire absent
      du disque donnent encore DEUX partitions. La variable de forçage sur un
      chemin jamais créé n'est donc pas repliée.
    - Pour une racine EXISTANTE, la graphie est celle que le SYSTÈME DE FICHIERS
      rend par IDENTITÉ ``(st_dev, st_ino)``, la MÊME quelle que soit la branche
      de ``project_root`` (variable, git, ou remontée d'ancêtres) — la branche git
      canonicalise AUSSI la sortie de ``git rev-parse``, y compris quand celle-ci
      rend une autre graphie sous ``GIT_WORK_TREE`` (tenu par les cinq témoins
      d'accord ET par
      ``test_la_branche_git_canonicalise_AUSSI_quand_git_rend_une_autre_graphie``).
      ``/a/Projet`` et ``/a/projet``, UN SEUL répertoire sur un FS insensible,
      donnent désormais UNE partition (mesuré 2026-09-20, S-00001650).

    INSTABILITÉ QUI EN DÉCOULE, MESURÉE LE 2026-09-21 : la partition d'une MÊME
    valeur de ``$CADRE_PROJECT_ROOT`` CHANGE au moment où le répertoire naît sous
    une autre graphie (clone, archive, ``git worktree add``) — avant
    ``64a6add4a22ec3d1``, après ``3b174b8d4573e90d`` ; et une partition écrite
    AVANT ce lot sous la graphie tapée (``projet``, ou une variable en casse
    différente) devient ORPHELINE — mesuré ``9cfaa83337b1eff7`` →
    ``4d4bad781982a47f``. AUCUNE MIGRATION n'est faite. ``STATE_PROJECT`` est
    une sortie machine publique (``cli.py``, ``contract.lock``), et son contrat
    ne bouge pas.

    TRANCHÉ (décision pilote S-00002199, options C+D, T-00000692) : la clé RESTE
    la graphie canonique du disque — ce module ne change ni ne migre rien. Une
    partition orpheline est désormais SIGNALÉE par son marqueur, jamais migrée :
    chaque partition porte un ``racine.json`` qui nomme sa racine, posé par
    ``agentic_v3.db.run_export.assurer_marqueur_partition`` (hors de ce module,
    qui n'écrit rien), et ``EventStore.__init__`` relève (à la naissance, puis à
    chaque apparition d'une sœur) et signale sur stderr, à chaque construction
    et jusqu'à acquittement ou disparition, les partitions apparentées (même
    répertoire par ``(st_dev, st_ino)``, même historique git, exports présents
    sous ``runs/``). Aucune suppression sans trace.

    LE DÉSÉQUILIBRE DE COÛTS RESTE VRAI, ET IL JUSTIFIE LE CONTRÔLE D'INODE. Sur
    un FS sensible, ``/a/Projet`` et ``/a/projet`` sont DEUX dépôts RÉELS : les
    confondre serait une PERTE DE DONNÉES, les séparer ne coûte qu'un doublon de
    disque. C'est pourquoi ``canonique_disque`` ne substitue JAMAIS une graphie
    sans inode partagé — deux dépôts réels (deux inodes) ne sont jamais fusionnés,
    seule une IDENTITÉ prouvée par le FS l'est.
    BORNE WINDOWS, NON MESURÉE (recopiée telle quelle) : ``resolve()`` y rend la
    casse du disque pour un chemin existant, donc le repli y a peut-être lieu de
    fait.

    Même paramètre ``depuis`` que ``project_root`` et même ``CadrePathError``
    propagée hors dépôt. NE CRÉE RIEN sur le disque — elle le LIT désormais pour
    canonicaliser (listage d'entrées), mais les écritures restent le travail de
    ``Workspace``.
    """
    return state_home() / "projets" / _empreinte_de_racine(project_root(depuis).resolve())


def index_db(depuis: str | os.PathLike[str] | None = None) -> Path:
    """L'emplacement UNIQUE du store SQLite de l'index : ``state_project()/index/index.db``.

    T-00000668 : ``index.db`` quitte le dépôt. C'est un doublon ADVISORY des
    fichiers ``SYMBOLS*.md`` — qui restent l'autorité versionnée — et il se
    reconstruit par ``migrate_index_to_db.py --apply`` (ou ``--resync``) : il est
    donc de l'état MACHINE (décision D3), et vit sous la partition du projet, à
    côté du store V3. UN SEUL POINT DE RÉSOLUTION : ``cadre.ledger.stores`` et
    ``.agents/bin/migrate_index_to_db.py::db_path`` y délèguent tous les deux.

    Même paramètre ``depuis`` et même ``CadrePathError`` que ``state_project``.
    NE CRÉE RIEN : ni le répertoire ``index/`` ni le fichier — c'est le travail
    de l'écrivain du store.
    """
    return state_project(depuis) / "index" / "index.db"


@lru_cache(maxsize=8)
def _git_toplevel(depuis: str) -> str | None:
    """Racine git, mise en cache par répertoire de départ.

    Le cache existe parce que ce module est appelé par des hooks à durée de vie
    très courte, où un sous-processus git par appel se voit. Il est borné et
    porte le répertoire de départ dans sa clé : deux dépôts dans une même
    session ne se contaminent pas.
    """
    try:
        r = subprocess.run(
            ["git", "-C", depuis, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=False, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    sortie = r.stdout.strip()
    return sortie if r.returncode == 0 and sortie else None


def vider_cache_racine() -> None:
    """Oublie les racines git mémorisées. À appeler après un ``git init`` ou un
    ``cadre init`` DANS LE MÊME PROCESSUS.

    Le cache ci-dessus mémorise aussi les ``None`` : sans cette sortie, un
    processus long qui a demandé la racine avant la création du dépôt continue de
    répondre « pas de dépôt » après. C'est le seul régime où le cache nuit, et il
    est le régime des bancs plutôt que celui des hooks.
    """
    _git_toplevel.cache_clear()


def canonique_disque(p: Path) -> Path:
    """Rend la graphie que le SYSTÈME DE FICHIERS porte pour ``p``, composant par
    composant, en raisonnant par IDENTITÉ ``(st_dev, st_ino)`` et jamais par
    comparaison de chaînes.

    PRÉCONDITION : ``p`` est déjà ``resolve()``. Cette fonction ne suit AUCUN
    lien symbolique et ne résout AUCUN ``..`` ; les trois sites d'appel tiennent
    la précondition (``force`` et ``depart`` sont ``resolve()`` dans
    ``project_root``, ``stores.py`` ``resolve()`` explicitement avant l'appel).

    POURQUOI L'IDENTITÉ, PAS LA CHAÎNE. Chaque table de repli que Python ne
    partage pas avec le FS — casse pleine (``casefold``), NFC/NFD, ß/ss, table
    d'upcase NTFS d'une autre version d'Unicode — est une partition de plus.
    Seule l'identité que le FS rend lui-même, le couple ``(st_dev, st_ino)``,
    n'en crée aucune. La comparaison de chaînes ne sert donc qu'à PRÉ-FILTRER les
    candidates (coût), jamais à DÉCIDER. Sur un FS SENSIBLE, ``straße`` et
    ``strasse`` (casefold-égaux) portent deux inodes et restent DEUX répertoires ;
    ``Projé`` sur disque, tapé ``Projé``, partage l'inode et la forme du DISQUE
    est substituée.

    NON STRICTE : un composant qui n'existe pas est conservé tel que tapé et la
    boucle s'arrête (un ancêtre inexistant n'a pas de descendants à apparier),
    donc deux graphies d'une racine INEXISTANTE donnent encore deux partitions.
    Sur une levée en cours d'appariement (ancêtre traversable mais NON listable —
    ``/home`` en ``711`` —, entrée disparue entre ``scandir`` et ``lstat``,
    chemin non encodable), le composant courant est conservé et la boucle
    CONTINUE : un chemin partiellement canonicalisé désigne le même répertoire,
    chaque substitution étant prouvée par inode. Jamais de traceback ; jamais une
    canonicalisation rendue INERTE en silence par une clause autour de la boucle
    entière. ``OSError`` couvre ``PermissionError`` et ``FileNotFoundError``,
    ``ValueError`` couvre ``UnicodeEncodeError`` (borne Windows, non mesurée).

    L-00000074 : ``(st_dev, st_ino)`` est ici une CEINTURE, pas une preuve
    absolue — sa fenêtre est deux ``lstat`` quasi simultanés sur un inode recyclé
    entre les deux, bornée par le pré-filtre ``casefold`` (seule une entrée
    casefold-égale est candidate). Dite, non fermée.
    """
    parts = p.parts
    if not parts:
        return p
    result = Path(parts[0])
    composants = parts[1:]
    for i, composant in enumerate(composants):
        parent = result
        try:
            st = os.lstat(parent / composant)                       # (0)
        except (OSError, ValueError):
            # (iii) : composant absent — aucun descendant à apparier. On conserve
            # CE composant ET tout le reste tels que tapés, puis on s'arrête.
            for reste in composants[i:]:
                result = result / reste
            return result
        try:
            with os.scandir(parent) as entrees:
                noms = [entree.name for entree in entrees]
            if composant in noms:                                   # (i) octets identiques
                result = parent / composant
                continue
            cible = unicodedata.normalize("NFC", composant).casefold()  # (ii) pré-filtre
            appariees = []
            for nom in noms:
                if unicodedata.normalize("NFC", nom).casefold() != cible:
                    continue
                st_entree = os.lstat(parent / nom)
                if (st_entree.st_dev, st_entree.st_ino) == (st.st_dev, st.st_ino):
                    appariees.append(nom)
            result = parent / (appariees[0] if len(appariees) == 1 else composant)
        except (OSError, ValueError):
            result = parent / composant                             # levée : garder, CONTINUER
    return result


def project_root(depuis: str | os.PathLike[str] | None = None) -> Path:
    """La racine du dépôt de travail, au sens de ``git rev-parse --show-toplevel``.

    **ELLE NE CONTIENT PAS NÉCESSAIREMENT** ``.agents/``, et cette ligne est une
    correction : la première rédaction promettait « celle qui contient
    ``.agents/`` », ce que la décision D2 ne tient pas. Mesuré sur un monorepo
    dont le ``.agents/`` vit sous ``apps/foo/`` — ``project_root`` rend la racine
    git, et ``agents_dir()`` pointe alors un répertoire qui n'existe pas, donc la
    couche projet de la configuration est ignorée EN SILENCE. C'est cohérent avec
    D2 tel qu'écrit en tête de module ; ce qui ne l'était pas, c'est de promettre
    ici l'autre sémantique. Le même écart vaut pour un sous-module git, où
    ``rev-parse`` répond la racine du SOUS-MODULE.

    Trois sources, dans cet ordre, et **la première qui répond gagne** :

    1. ``$CADRE_PROJECT_ROOT`` — la porte de sortie des bancs, qui doivent
       pouvoir pointer un arbre temporaire sans dépendre du répertoire courant.
    2. ``git rev-parse --show-toplevel`` — la sémantique historique (D2).
    3. La remontée d'ancêtres jusqu'à un répertoire portant ``.agents/``, pour
       le cas où git est absent : une wheel installée sur un poste sans git
       reste utilisable, et une archive dézippée aussi.

    LEVER ``CadrePathError`` PLUTÔT QUE RENDRE LE RÉPERTOIRE COURANT. Un repli
    silencieux sur ``Path.cwd()`` ferait écrire le kit à côté du dépôt, ce qui
    est précisément le défaut que cette couche existe pour rendre impossible.
    """
    force = _from_env(_ENV_PROJECT)
    if force is not None:
        return canonique_disque(force)

    depart = Path(depuis).resolve() if depuis is not None else Path.cwd().resolve()
    if depart.is_file():
        depart = depart.parent
    depart = canonique_disque(depart)

    racine = _git_toplevel(str(depart))
    if racine:
        # La SORTIE de git est canonicalisée AUSSI : sous GIT_WORK_TREE,
        # `git rev-parse --show-toplevel` rend la graphie TAPÉE, pas celle du
        # disque, et la branche git divergerait des branches 1 et 3 (T-00000674).
        return canonique_disque(Path(racine).resolve())

    for candidat in (depart, *depart.parents):
        if (candidat / AGENTS_DIRNAME).is_dir():
            return candidat

    raise CadrePathError(
        f"racine de projet introuvable depuis {depart} : ni ${_ENV_PROJECT}, ni "
        "un dépôt git, ni un ancêtre portant un répertoire "
        f"{AGENTS_DIRNAME}/. Placez-vous dans le projet, ou nommez sa racine "
        f"par ${_ENV_PROJECT}."
    )


def nom_projet(depuis: str | os.PathLike[str] | None = None) -> str:
    """Le nom d'affichage du projet : le BASENAME de ``project_root(depuis)``.

    UNE règle, zéro branche, zéro E/S propre (S-00001541) : le nom se dérive de
    la racine et hérite de ses TROIS sources — ``$CADRE_PROJECT_ROOT``, puis
    ``git rev-parse --show-toplevel``, puis la remontée d'ancêtres — sans en
    ajouter une quatrième. ``project.json:name`` cesse d'être une source ; il
    reste ÉCRIT (le fichier porte encore ``project_id``) mais n'est plus LU pour
    l'affichage.

    SE RE-DÉRIVE À CHAQUE LECTURE (S-00001542) : aucun ``@lru_cache`` ici, aucun
    gel à l'init. La SEULE rémanence est le cache ``_git_toplevel``, clé par
    répertoire de DÉPART et vidable par ``vider_cache_racine()`` — donc, sous la
    source git, ``nom_projet(depuis=<ancien chemin>)`` après un renommage rend
    l'ancien nom tant que ce cache n'est pas vidé. Sous ``$CADRE_PROJECT_ROOT``
    la source est l'ENV (``_from_env``, ``expanduser().resolve()``), jamais le
    disque : le nom suit la VALEUR de la variable, pas l'état du disque, et un
    renommage disque n'y est donc pas suivi non plus.

    CONTRAT D'ERREUR (A-C4) : PROPAGE ``CadrePathError`` exactement comme
    ``state_project`` — AUCUN retour dégradé, jamais ``None``. Un appelant qui
    veut un affichage dégradé (le badge du dashboard) gère l'absence de racine
    LUI-MÊME ; ce module ne l'invente pas.

    REPLI ``"projet"`` sur basename vide : ``Path("/").name == ""``. Littéral
    NOUVEAU et DISTINCT de ``project_init.slugify`` (``return slug or "project"``)
    — le slug est une CLÉ, le nom un AFFICHAGE, et l'écart de repli est assumé
    (A-C2 de la paire 3).

    COUTURE DE CASSE (T-00000674, done). ``nom_projet`` ne canonicalise JAMAIS
    pour son compte : il hérite de la graphie que ``project_root()`` rend, et
    ``project_root()`` canonicalise déjà chaque composant par identité
    ``(st_dev, st_ino)`` — ses trois branches convergent sur la graphie du DISQUE
    pour une racine EXISTANTE. Cohérent avec le § INSTABILITÉ de
    ``state_project`` : le nom affiché, comme la partition d'état, BOUGE au moment
    où un répertoire naît sous une autre graphie (clone, archive,
    ``git worktree add``) ; AUCUNE migration n'est faite.

    ÉCART DE CANONICALISATION D'ENTRÉE, NON FERMÉ (A-C8). Le démon du dashboard
    normalise SA racine par ``normalize_root`` (``dashboard_daemon.py`` :
    ``Path(text)`` SANS ``resolve()``), tandis que ``project_root()`` passe
    ``$CADRE_PROJECT_ROOT`` par ``expanduser().resolve()`` puis
    ``canonique_disque``. Deux chemins désignant le MÊME répertoire par un
    symlink ou une casse différente donnent donc deux basenames selon le côté qui
    dérive. Le témoin d'équivalence (``test_dashboard.py``) nourrit les DEUX
    fonctions du MÊME ``Path`` et ne couvre donc PAS cet écart : il est porté par
    ``T-00000685`` — PAS par ``T-00000674``, qui est ``done`` : celui-là a
    canonicalisé ``project_root()``, jamais ``normalize_root``.
    """
    return project_root(depuis).name or "projet"


def agents_dir(depuis: str | os.PathLike[str] | None = None) -> Path:
    """``<racine projet>/.agents`` — le répertoire de contrat (D2).

    Ne vérifie PAS son existence : un ``cadre init`` sur un projet neuf le crée,
    et refuser ici rendrait l'initialisation impossible.
    """
    return project_root(depuis) / AGENTS_DIRNAME
