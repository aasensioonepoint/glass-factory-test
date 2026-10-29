"""T-00000753 — refus de la NAISSANCE d'une partition d'état MACHINE pour une racine
JETABLE, quand rien n'isole l'état (`CADRE_STATE_DIR` absent).

Le canal MESURÉ (mesure C du plan T-00000753, S-00003815) : neuf créateurs du paquet
naissaient `~/.local/state/cadre/projets/<empreinte>/` pour une racine posée sous un
dossier temporaire — les partitions parasites d'un poste de développement en sont nées.
Ce module ne supprime rien et ne déplace rien : il décide, À LA NAISSANCE seulement, si
la partition d'une racine jetable peut naître sous l'état par défaut. Une partition qui
EXISTE est adoptée comme avant, jamais refusée.

OUVERT-ÉCHEC, assumé et dit : un filet n'est jamais une cause de panne. Toute levée
du prédicat rend « pas de refus » et la naissance suit le chemin d'avant ; la
comparaison de zones ne lève JAMAIS par construction (`PurePath.is_relative_to`, pas
`os.path.commonpath`, qui lève `ValueError` entre deux lecteurs Windows). Un défaut du
prédicat se VOIT : ses témoins (`test_partition_naissance_jetable.py`) rougissent.

BORNES, écrites : la liste des zones est FINIE (ci-dessous), jamais « toute racine
jetable » ; la comparaison porte sur des chaînes après `realpath`, donc sur un système
de fichiers insensible à la casse (macOS par défaut, Windows) une racine tapée dans une
autre casse que sa zone n'est PAS refusée ; mesuré sous macOS seul — Linux non mesuré,
Windows simulé par `PureWindowsPath` (inter-lecteurs, casse), `realpath` Windows non
mesuré.

T-00001069 — SECONDE JAMBE, après les zones : hors isolation, la partition d'un worktree
LIÉ ne naît pas (`principal_du_worktree`) ; l'état machine reste à celle du principal
(S-00003449), le pont V3 du worktree est refusé et annoncé, ses intents board restent dans
l'outbox de SA branche et ne rejoignent le principal que si ce board est fusionné. La clé
de partition ne change pas. BORNES, écrites :
  * isolation : `CADRE_STATE_DIR` est PUBLIQUE (CONTRAT-v0 § 3.4) et toute valeur non
    blanche vaut isolation ; sous elle, un worktree lié fait encore naître sa partition,
    isolée — un adoptant qui prend `CADRE_STATE_DIR` pour son état RÉEL garde le défaut.
    Le message de refus ne la propose plus comme issue (décision pilote
    S-01M4N0NGM16BYEYYB3VT7X69WJ, T-01M4MC28WDHJ301H9C4P3JC8WP) : il dit
    qu'un checkout de travail qui est un worktree lié n'a pas de pont V3 — « travaille depuis
    un clone ». L'option opt-in (b), un pont V3 dans un worktree lié, n'est PAS livrée : elle
    ne s'ajoutera que si un adoptant réel en a besoin ;
  * une partition de worktree DÉJÀ née est adoptée, jamais refusée (contrat T-00000753) ;
  * dans ces deux cas le worktree DRAINE : un intent drainé quitte le `sync_outbox/` suivi
    de SA branche et aucune autre partition ne le reçoit jamais (delta
    S-01M4M2E7DWB4SWDR02GPSSQ0JV) — seul un pont REFUSÉ garde l'intent pour le principal ;
  * outbox au-delà de 200 intents (`_SYNC_OUTBOX_SEUIL`) : sous pont refusé, l'excédent part
    sous `.agents/state/local/`, NON suivi — il ne voyage pas à la fusion, et le pont qui le
    rejouerait ne se construit jamais dans un worktree lié : perdu au retrait du worktree ;
  * créateurs HORS de ce module (`migrate_index_to_db.py`, `symbols.py`, `project_init.py`,
    `cadre init` — T-00001125) : ils font naître la partition d'un worktree lié sans passer
    ici, et elle est ensuite ADOPTÉE ;
  * sous-module, même sous un worktree lié du super-projet : `--git-dir` = `--git-common-dir`
    → partition par chemin, comme avant (mesuré, git 2.55) ;
  * un worktree lié dont la branche ne revient jamais au principal (historique indépendant,
    branche de gabarit) est refusé comme un worktree de dev : le message y nomme un principal
    qui ne porte pas son état ;
  * dépôt NU : chacun de ses checkouts est lié, aucun n'est principal → partition par chemin,
    comme avant ;
  * git < 2.31 (sans `--path-format`), git absent, délai dépassé, principal supprimé ou
    `gitdir` cassé : `rev-parse` échoue → aucun principal, la naissance suit son chemin
    d'avant (ouvert-échec) ;
  * `GIT_*` hérités (hook git, `git -c` d'un appelant — T-01M4MC2949AVM2X2HEK92DDVSG) : les
    huit REDIRECTIONS du dépôt (`GIT_DIR`, `GIT_WORK_TREE`, `GIT_COMMON_DIR`,
    `GIT_INDEX_FILE`, `GIT_OBJECT_DIRECTORY`, `GIT_ALTERNATE_OBJECT_DIRECTORIES`,
    `GIT_NAMESPACE`, `GIT_PREFIX`) et les INJECTIONS de configuration (`GIT_CONFIG_PARAMETERS`,
    `GIT_CONFIG_COUNT`, `GIT_CONFIG_KEY_*`/`GIT_CONFIG_VALUE_*` — un `core.bare=true` injecté
    rendait `None`, réserve C1 S-01M4NQ9K1VQ92GF8F7E68Y46EV) sont retirées de l'environnement
    des deux sous-processus, comme `juger_worktree_lie` (S-00004089) : le prédicat juge la
    RACINE, jamais le dépôt qu'un `GIT_DIR` hérité désigne. Liste FINIE : passent les
    EMPLACEMENTS de configuration (`GIT_CONFIG_GLOBAL`/`SYSTEM`/`NOSYSTEM` — mesuré, git 2.55
    sous macOS : un `core.bare=true` posé par `GIT_CONFIG_GLOBAL` ou `~/.gitconfig` ne renverse
    pas le verdict), `GIT_CEILING_DIRECTORIES`, `GIT_DISCOVERY_ACROSS_FILESYSTEM` et toute
    autre `GIT_*`. Pas d'union de refus à la manière d'une garde FERMÉE-échec : ici une union GARDERAIT le refus du principal sous
    `GIT_DIR=<k>/.git/worktrees/w`, le défaut même ; ce module reste ouvert-échec ;
  * coût : au plus deux sous-processus git, seulement quand la partition n'existe pas ;
    mesuré sous macOS seul.

Stdlib seule ; `run_export` n'est importé que PARESSEUSEMENT (cycle : `schema` importe
ce module, `run_export` importe `schema`).
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path, PurePath
from typing import Any, Callable, List, Mapping, Optional

#: La SEULE isolation reconnue : celle que `conftest.py`, `run-bash-tests.sh` et la
#: consigne des agents posent déjà. `XDG_STATE_HOME` n'isole pas : c'est l'état RÉEL
#: d'un poste XDG. Lue `.strip()`, comme `cadre.paths._from_env` : « blanche » = absente.
ISOLATION = "CADRE_STATE_DIR"

#: Zones LITTÉRALES, ajoutées à `gettempdir()` et à `$TMPDIR`/`$TEMP`/`$TMP` : un
#: processus à environnement vidé, ou une racine créée par un AUTRE processus, n'a pas le
#: même `$TMPDIR` (macOS : /var/folders ; scratchpads des agents : /tmp ; Linux :
#: /var/tmp). Liste BORNÉE, dite : jamais « toute racine jetable ».
ZONES_LITTERALES = ("/tmp", "/var/tmp", "/var/folders")
VARIABLES_TEMPORAIRES = ("TMPDIR", "TEMP", "TMP")


def isole(environ: Optional[Mapping[str, str]] = None) -> bool:
    """`CADRE_STATE_DIR` posé ET non blanc — `.strip()`, comme `cadre.paths._from_env` : une
    valeur blanche n'isole rien, `state_home()` retombe alors sur le vrai état."""
    env = os.environ if environ is None else environ
    return bool(str(env.get(ISOLATION, "")).strip())


def _sous(racine: str, zone: str, plat: type = PurePath) -> bool:
    """`racine` est-elle `zone` ou dessous ? Par COMPOSANTS, sans E/S, et sans jamais
    lever : entre deux lecteurs Windows la réponse est `False`, pas une `ValueError`."""
    return plat(racine).is_relative_to(plat(zone))


def zones_temporaires(
    environ: Mapping[str, str], *, temporaire: Callable[[], str] = tempfile.gettempdir
) -> List[str]:
    """Les zones temporaires du processus, `realpath` chacune (macOS : /tmp est
    /private/tmp), sans doublon : `gettempdir()`, puis `$TMPDIR`/`$TEMP`/`$TMP`, puis les
    littéraux. Une source qui lève ou qui est vide est sautée, jamais fatale."""
    brut: List[Any] = []
    try:
        gt = temporaire()
        # repli de `gettempdir()` sur le cwd quand aucun dossier n'est inscriptible : le
        # cwd n'est pas une zone jetable ($TMPDIR et les littéraux restent lus plus bas)
        if os.path.realpath(gt) != os.path.realpath(os.getcwd()):
            brut.append(gt)
    except Exception:  # `gettempdir()` lève si aucun dossier n'est utilisable
        pass
    brut.extend(environ.get(nom, "") for nom in VARIABLES_TEMPORAIRES)
    brut.extend(ZONES_LITTERALES)
    zones: List[str] = []
    for z in brut:
        try:
            z = str(z).strip()
            r = os.path.realpath(z) if z else ""
        except Exception:
            continue
        if r and r not in zones:
            zones.append(r)
    return zones


#: Plafond de CHAQUE appel git du prédicat, en secondes : au-delà, « aucun principal ».
DELAI_GIT = 5

#: T-01M4MC2949AVM2X2HEK92DDVSG — ce que les deux appels git du prédicat n'héritent JAMAIS :
#: les REDIRECTIONS du dépôt (liste autonome, S-00004089) et les deux INJECTIONS de
#: configuration par nom (réserve C1, S-01M4NQ9K1VQ92GF8F7E68Y46EV : un `core.bare=true` hérité
#: rendait `None`) ; les clés `GIT_CONFIG_KEY_<n>`/`GIT_CONFIG_VALUE_<n>` partent par PRÉFIXE.
#: Même partage que `conftest.py` (`GIT_REDIRECTIONS`) : les EMPLACEMENTS de configuration
#: (`GIT_CONFIG_GLOBAL`/`SYSTEM`/`NOSYSTEM`) et `GIT_CEILING_DIRECTORIES` passent.
VARIABLES_GIT_HERITEES = (
    "GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE", "GIT_PREFIX",
    "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT",
)
PREFIXES_GIT_HERITES = ("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")


def principal_du_worktree(racine: Any) -> Optional[str]:
    """Le chemin du dépôt PRINCIPAL si `racine` est un worktree LIÉ (ou dessous), `None` sinon.

    `git rev-parse --path-format=absolute --git-dir --git-common-dir` : deux lignes ÉGALES =
    pas un worktree lié (principal, sous-dossier, `--separate-git-dir`, sous-module) ; sinon
    le PREMIER bloc de `git worktree list --porcelain`, celui du principal — une ligne `bare`
    y rend `None` (un dépôt nu n'a pas de checkout principal). Sans `--path-format=absolute`,
    depuis un sous-dossier, les deux lignes sont deux graphies du même dossier (mesure m6).
    Le chemin rendu est celui que git a enregistré, sans `realpath`. OUVERT-ÉCHEC : toute
    levée (git absent, délai, racine illisible) et tout code de retour non nul rendent `None`.

    Les deux sous-processus reçoivent une COPIE de `os.environ` sans `VARIABLES_GIT_HERITEES` ni
    les clés `PREFIXES_GIT_HERITES` (T-01M4MC2949AVM2X2HEK92DDVSG) : c'est `racine` qui est
    jugée, jamais le dépôt qu'un `GIT_DIR` hérité désigne ; `os.environ` n'est jamais muté."""
    try:
        dossier = os.fspath(racine)
        env = {k: v for k, v in os.environ.items()
               if k not in VARIABLES_GIT_HERITEES and not k.startswith(PREFIXES_GIT_HERITES)}
        sonde = subprocess.run(
            ["git", "-C", dossier, "rev-parse", "--path-format=absolute", "--git-dir", "--git-common-dir"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=DELAI_GIT, check=False,
            env=env,
        )
        lignes = sonde.stdout.splitlines()
        if sonde.returncode != 0 or len(lignes) != 2 or lignes[0] == lignes[1]:
            return None
        liste = subprocess.run(
            ["git", "-C", dossier, "worktree", "list", "--porcelain"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=DELAI_GIT, check=False,
            env=env,
        )
        if liste.returncode != 0:
            return None
        bloc = liste.stdout.split("\n\n", 1)[0].splitlines()
    except Exception:  # git absent, délai, racine illisible : un filet n'est jamais une cause de panne
        return None
    if not bloc or not bloc[0].startswith("worktree ") or "bare" in bloc:
        return None
    return bloc[0][len("worktree "):] or None


def refus_naissance(
    racine: Any,
    *,
    environ: Optional[Mapping[str, str]] = None,
    zones: Optional[List[str]] = None,
    domicile: Optional[str] = None,
    temporaire: Callable[[], str] = tempfile.gettempdir,
    principal: Callable[[Any], Optional[str]] = principal_du_worktree,
) -> Optional[str]:
    """Une ligne de refus si `racine` est sous une zone temporaire ET qu'aucune
    isolation n'est posée ; puis (T-00001069), hors isolation toujours, si `racine` est un
    worktree LIÉ — `principal(racine résolue)` rend son principal ; `None` sinon. Les zones
    passent d'abord : leur message (T-00000753) garde la priorité. Ne crée rien, ne lève rien.
    `principal` est lié à la DÉFINITION (valeur par défaut) : un banc l'injecte, il ne le
    remplace pas dans le module.

    Une zone qui CONTIENT le domicile de l'utilisateur n'est pas retenue (`$TMPDIR=/`,
    `$TMPDIR=/home`, ou un domicile sous /tmp : c'est SON espace, pas un dossier jetable ;
    sans cette borne tout projet réel serait refusé). Bornée à ce critère : une zone qui est
    la racine d'un AUTRE lecteur Windows que le domicile n'est pas écartée — NON MESURÉ."""
    try:
        env = os.environ if environ is None else environ
        if isole(env):
            return None
        r = os.path.realpath(os.fspath(racine))
        home = os.path.realpath(domicile if domicile is not None else os.path.expanduser("~"))
        liste = zones_temporaires(env, temporaire=temporaire) if zones is None else list(zones)
    except Exception:
        return None
    for zone in liste:
        try:
            z = os.path.realpath(zone)
            if _sous(home, z) or not _sous(r, z):
                continue
        except Exception:  # une zone illisible ne masque jamais les autres
            continue
        return (
            f"naissance de partition d'état REFUSÉE : la racine {r} est sous la zone "
            f"temporaire {z} et CADRE_STATE_DIR est absent — l'état machine par défaut "
            "n'accueille pas une racine jetable (T-00000753) ; pose "
            "CADRE_STATE_DIR=<dossier jetable> pour l'isoler"
        )
    try:
        p = principal(r)
    except Exception:  # une sonde qui lève ne refuse rien : ouvert-échec
        return None
    if p:
        return (
            f"naissance de partition d'état REFUSÉE : la racine {r} est un worktree LIÉ du dépôt "
            f"{p} — un checkout de travail qui est un worktree lié n'a pas de pont V3 — travaille "
            "depuis un clone ; l'état machine reste à la partition du principal (S-00003449) ; les "
            "intents board restent dans l'outbox de la branche et ne la rejoignent que si son board "
            "est fusionné (T-00001069)"
        )
    return None


def refuser_naissance(racine: Any = None) -> None:
    """Lève `EmplacementRefuse` (prise PAR LA COUTURE, même objet-classe que celui que
    lève `create_tables` : `tasks_sync` et `refus_nomme` le classent déjà) si la
    partition de `project_root(racine)` ne peut pas naître. La racine est celle que
    `state_project(racine)` clé, où `$CADRE_PROJECT_ROOT` gagne sur `racine`."""
    try:
        from agentic_v3.db import run_export

        refus = refus_naissance(run_export.project_root(racine))
    except Exception:  # racine non résoluble, couture absente : la naissance suit son chemin
        return
    if refus:
        raise run_export._couture_ledger_store()[0].EmplacementRefuse(refus)


def sonder_partition(partition: Any, depuis: Any = None) -> bool:
    """`partition.is_dir()` — la SONDE d'avant le `mkdir` — ET le refus d'une naissance
    pour une racine jetable. Rend `existait` ; lève `EmplacementRefuse` avant que
    rien ne soit créé."""
    existait = Path(partition).is_dir()
    if not existait:
        refuser_naissance(depuis)
    return existait


def garder_store(db_path: Any, racine: Any = None) -> None:
    """Le garde des créateurs de STORE (`create_tables`, `get_db_connection`), avant leur
    `mkdir`. `racine` `None` = `project_root()` du cwd. Deux filtres, chacun son témoin :

    * NOM — seul le chemin PAR DÉFAUT d'une racine, `<partition>/run/v3_event_store.db`,
      est jugé ; tout autre chemin sort AVANT la moindre résolution (chemin chaud de
      `get_db_connection`). Borne de portée, dite : une base d'un autre nom n'est jamais
      jugée, même sous une partition — les créateurs du paquet n'ouvrent que le chemin
      par défaut, et les autres naissances passent par les sondes de `run_export` ;
    * AUTRE RACINE — une base de cette forme hors de la partition de SA racine
      (`state_project(racine)`) n'est pas jugée. BORNE : si c'est la partition par
      défaut d'une AUTRE racine (`DEFAULT_DB_PATH(R)` ouvert sans `racine=R` depuis un
      autre cwd), son `mkdir` la fait naître NUE, même jetable — seul `racine=` la juge.

    Une partition qui EXISTE est adoptée, jamais refusée."""
    if isole():  # chemin chaud : la sortie d'isolation d'abord
        return
    try:
        chemin = Path(db_path)
        if chemin.name != "v3_event_store.db" or chemin.parent.name != "run":
            return
        partition = chemin.parent.parent
        if partition.is_dir():
            return
        from agentic_v3.db import run_export

        attendue = Path(run_export.state_project(racine))
        if partition != attendue and partition.resolve() != attendue.resolve():
            return  # la partition d'une AUTRE racine : pas celle que cette racine ouvrirait
    except Exception:
        return
    refuser_naissance(racine)
