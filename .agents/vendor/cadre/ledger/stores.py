"""CRÉATION DES TROIS STORES SQLITE DE L'ADOPTANT — par le code de la WHEEL.

T-00000646, décisions pilote S-00001590 (le chargement depuis la racine cible est
RETIRÉ), S-00001591 (l'init crée les TROIS stores) et S-00002138 (la spec et le
code bougent ensemble). Ce module est l'API que « création hybride des stores »
désigne, telle qu'amendée : les stores d'équipe (texte versionné) ET les stores
machine (SQLite) naissent à l'`init`, en un appel, par le code du paquet installé
(« init exécute la wheel »). Il n'a AUCUN appelant de production tant que
`cadre init` n'est pas ouvert (T-00000756 porte ce câblage).

LES SCHÉMAS VIVENT DANS LA WHEEL. `cadre.ledger.stores_schemas` porte le DDL, les
versions et les échelles de montée des trois stores ; ce module-ci résout les
chemins, ouvre les connexions par `cadre.ledger.store.ouvrir_sans_suivre` (la
primitive non suivie, qui appelle `store.connect`, l'unique ouverture du service)
et appelle `sonder_*` puis `garantir_*`. Aucun fichier `.py`
du dépôt de l'adoptant n'est chargé ni exécuté : un paquet copié SEUL, sans
`agentic_v3/` ni `.agents/bin/`, crée les trois stores (témoin `PaquetSeulTests`).
SECONDE DÉFINITION DES SCHÉMAS, ASSUMÉE (S-00001592) jusqu'à l'inversion portée
par T-00000660 : le banc `PariteDesSchemasTests` exige à chaque porte l'égalité
stricte avec les producteurs du kit (`create_tables`, `open_store`,
`migrate_index_to_db`).

  * `v3_event_store.db`  ->  sous la PARTITION MACHINE du projet
        (`state_project()/run/`, HORS dépôt, T-00000650) ;
  * `events.db`          ->  `.agents/state/local/` sous la racine ;
  * `index.db`           ->  sous la PARTITION MACHINE du projet
        (`cadre.paths.index_db()` = `state_project()/index/index.db`, HORS dépôt,
        T-00000668), créé VIDE (un `python .agents/bin/migrate_index_to_db.py
        --resync` le remplira) et jamais versionné. Présent, il est seulement
        MONTÉ de schéma : jamais `watermark` ni `built_at_sha` réécrits.

UN POINT UNIQUE POUR LES CHEMINS. `chemins_des_stores(racine)` est le seul site
qui résout les chemins absolus ; `init_surfaces.STORES` porte en relatif le seul
store qui vit encore sous la racine (`events.db`), tenu égal par
`test_STORES_egale_chemins_des_stores`. Il n'écrit rien. L'index y est résolu
par `cadre.paths.index_db`, le MÊME point que `migrate_index_to_db.db_path`
(T-00000668). Les parités avec les résolveurs des producteurs (`db_path`,
`events_db_path`, `DEFAULT_DB_PATH`) sont tenues par `PariteDesCheminsTests`.

LA RACINE EST CELLE DE L'APPELANT, PAS CELLE DE L'ENVIRONNEMENT.
`chemins_des_stores` — donc `creer_les_stores` — REFUSE si `$CADRE_PROJECT_ROOT`
(ou la racine git) fait diverger la racine résolue de l'argument : créer les stores
ailleurs que là où l'appelant l'a demandé serait une divergence silencieuse. Rien
n'est créé dans ce cas.

SONDER AVANT D'ÉCRIRE. `creer_les_stores` travaille en trois temps : les chemins,
puis la SONDE de chaque store DÉJÀ présent, puis la création. Un store du futur,
un `events.db` non versionné mais non vide, un `index.db` étranger, un fichier
qui n'est pas une base SQLite, ou une maintenance du spool en cours lève
`CadrePathError` AVANT toute écriture si le refus est visible à la sonde — de
même un LIEN à l'emplacement d'un store ou d'un de ses annexes, un second NOM
(lien physique) d'un store, ou un annexe qui n'est pas un fichier régulier
(T-00000759) ; un écrivain concurrent entre la sonde et la création fait
refuser la re-sonde de CE store, les précédents restent créés ou montés, un
rejeu reprend une fois la cause nommée levée (« aucune suppression sans
trace »). Toute `sqlite3.Error` (verrou tenu au-delà de
l'attente, fichier illisible), `OSError` (un répertoire attendu qui est un
fichier) ou `HorsRacine` (un lien qui sort de la racine) est traduite de même,
jamais levée brute ; le message dit si le refus est tombé à la sonde — aucun
store créé ni monté — ou après.

LE SPOOL N'EST NI LU NI TOUCHÉ. Créer `events.db` ici ne joue pas le repli
d'ouverture du démon — `merge_day_files` devient inatteignable pour ce store
(tête de `stores_schemas`, (a)) : le spool restant est ingéré par son tick
normal, dont le filtre « résidu » écarte un triangle déjà fusionné — jamais de
double comptage (témoin `SpoolTests`). Hors maintenance du spool concurrente :
un `.agents/state/events/.maintenance.lock` présent ET de moins de 10 min
(`_MAINTENANCE_PERIMEE_S`, le seuil d'`events.maintenance_lock`) fait REFUSER la
création d'`events.db` (course C2 d'`events.py`, bloc « V1-b (T-00000049) »
au-dessus de `maintenance_lock`), à la sonde puis juste avant la création. La
fenêtre est réduite, pas fermée (fermer = tenir le verrou pendant la création,
décision d'API à venir). BORNES : seul l'emplacement PAR DÉFAUT du verrou est lu
(la wheel ne lit pas `AGENTS_EVENTS_DIR`) ; un verrou plus vieux est celui d'un
détenteur mort, IGNORÉ et jamais supprimé — seul son producteur le reprend.

E/S TEXTUELLEMENT DANS CE FICHIER, DERRIÈRE DEUX RÉCEPTEURS NOMMÉS. Les chemins
passent par un `Workspace` annoté (existence, création du RÉPERTOIRE parent,
identité d'une feuille NON suivie, création EXCLUSIVE du fichier vide) — jamais
`write_bytes`, dont `os.replace` remplaçait l'inode d'un store apparu entre la
sonde et la création (T-00000646, F5). Les connexions passent par
`store.ouvrir_sans_suivre`, qui appelle `store.connect` DANS `store.py` : depuis
T-00000770 ce fichier n'appelle plus `.connect` du tout. L'exemption nommée du
banc local de pureté (`PRODUCTEUR_CHARGE = ("stores.py", "store")`) est donc
INUTILISÉE, et elle RESTE, délibérément : `test_cadre_ledger_purete.py` est hors
du write-set de T-00000770, et son témoin T6 exerce cette exemption sur des
sources SYNTHÉTIQUES — elle est testée-mais-inutilisée, pas morte ; la retirer
est un geste de ce banc-là, avec son propre témoin. Aucune E/S n'est déportée
ailleurs pour « la faire passer » : aucun `stat` nu ici, l'identité vient de
`Workspace.identite`. BORNE DU FILET, écrite (binôme F3) : ce banc refuse
`.stat()` hors `Workspace`, mais il est AVEUGLE à `os.lstat` et `os.fstat`,
absents de son jeu `IO_PAR_METHODE` — NON étendu, sa parité avec le filet
global le fixe. Qu'aucun `os.lstat` nu n'apparaisse ici tient par la revue.

LIENS ET COURSE À LA CRÉATION (T-00000759, S-00002298, S-00002320). Menace : un
lien COMMITÉ à l'emplacement d'un store dans un dépôt cloné (git stocke les
liens ; un `local/` ignoré n'empêche pas un fichier commité), ou un tiers ayant
l'écriture sur le répertoire parent pendant la fenêtre ; le même uid est hors
modèle (il écrit déjà tout). Ce qui est FERMÉ :
  * un lien PRÉ-PLANTÉ sur la feuille d'un store OU d'un annexe (`-wal`,
    `-shm`, `-journal`), pendant ou non, une feuille qui n'est pas un fichier
    régulier ou qui porte PLUS D'UN lien physique (un second nom : écrire le
    store réécrivait le fichier de l'autre nom, binôme F1), et un annexe
    présent qui n'est pas un fichier régulier (un `-wal` répertoire faisait
    échouer SQLite APRÈS la création du store) ou qui porte plus d'un lien
    physique (SQLite retirait ce second nom d'un tiers) : refus À LA SONDE
    (`_refuser_les_liens`, avant `exists` qui suit la feuille) — rien n'est
    suivi, rien n'est supprimé ;
  * la création ne suit pas : le fichier vide naît par
    `O_CREAT|O_EXCL|O_NOFOLLOW` (`Workspace.creer_fichier_exclusif`), plus par
    SQLite, qui suivait un lien et CRÉAIT sa cible ; un nom pris n'est pas
    écrasé, l'existant est re-JUGÉ comme à la sonde, avant toute ouverture ;
  * l'ouverture ne crée pas : `store.ouvrir_sans_suivre`, qui ouvre par
    `store.connect(…, sans_creation=True)` (`mode=rw`) — un lien pendant planté
    entre la création et l'ouverture fait
    LEVER SQLite au lieu d'écrire au bout, et cette levée devient un refus qui
    dit ce que le nom désigne désormais (rien, un lien symbolique, un autre
    fichier, le même fichier) ;
  * un échange est détecté AVANT toute écriture, par DEUX moitiés dont chacune
    voit ce que l'autre manque (témoins séparés) : `PRAGMA database_list` doit
    rendre, lexicalement, le chemin créé ou vérifié — SQLite résout un lien de
    feuille vers sa cible, donc seule cette moitié voit un lien planté PUIS
    RETIRÉ pendant l'ouverture —, puis une seconde `identite` doit égaler la
    première — seule elle voit une base étrangère RENOMMÉE sur le nom, que
    `database_list` rend sous le nom attendu. Sinon la connexion est refermée
    avant toute sonde ou `garantir_*`. Sur le chemin de création le message
    dit « le fichier vide créé reste en place » SEULEMENT si le nom le désigne
    encore ; sinon qu'un tiers l'a retiré ou remplacé, que rien n'est
    supprimé, et qu'il faut retirer ce qui occupe le nom avant de relancer ;
  * un lien d'annexe planté APRÈS la sonde et qui fait lever SQLite est NOMMÉ :
    une `sqlite3.OperationalError` de la sonde ou de la garantie re-juge les
    liens avant d'être relevée (`_nommer_un_lien_d_annexe`).
MODE : un store NEUF naît en `0o600` (`_MODE_STORE`, décision R1 du plan) —
données d'exécution privées d'un utilisateur, lues par des processus du même
uid ; ÉCART VOULU avec `0o666 & ~umask` de `Workspace.write_bytes` (avant
T-00000759 : 0o644 sous un umask 022). Un store déjà présent garde son mode.
BORNES, écrites plutôt que fermées (aucune tâche de suivi pour les deux
premières, décision R1 du plan) :
  * `(dev, ino)` réduit la fenêtre mais ne PROUVE pas l'identité : un inode
    RECYCLÉ (L-00000074) ; et un échange ABA de fichier RÉGULIER entre la
    résolution et l'`open` de SQLite, remis en place avant la seconde identité,
    n'est pas vu ;
  * un ANCÊTRE échangé : le fichier vide `O_EXCL` peut naître DEHORS (seule la
    feuille est gardée) ; SQLite, lui, est arrêté par `database_list` ;
  * un annexe RÉGULIER pré-planté (`-wal` forgé) à UN SEUL nom, à côté d'un
    store absent, n'est PAS refusé (un annexe à plusieurs liens physiques,
    lui, l'est à la sonde — `store._juger_l_annexe`) ; et un second nom planté sur
    un annexe APRÈS la sonde n'est pas revu — mesuré avant ce refus, darwin,
    SQLite 3.53.4, `-wal` second nom d'un fichier tiers, store neuf comme
    existant : SQLite RETIRE ce nom sans écrire le fichier, dont les octets
    restent intacts ;
  * un annexe planté en lien APRÈS la sonde n'est jamais SUIVI (cible intacte
    dans tous les cas mesurés), mais son sort dépend du moment — mesuré sur
    darwin, SQLite 3.53.4, CETTE version seule : (a) entre le jugement et la
    PREMIÈRE lecture d'un store existant (`-wal`, `-shm` ou `-journal`), ou
    `-shm` juste avant le passage en WAL d'un store neuf : SQLite lève
    (`unable to open database file`, CANTOPEN), le lien RESTE, le refus le
    nomme dans la passe et la sonde suivante le refuse ; (b) `-wal` ou
    `-journal` avant la première lecture d'un store neuf VIDE : SQLite le
    SUPPRIME sans lever (un store de zéro page écarte ses annexes) — le lien
    d'un tiers disparaît, sa cible non ; (c) après l'ouverture du WAL par
    SQLite (nom remplacé par un lien) : non suivi, le lien disparaît à la
    fermeture, quand SQLite retire le `-wal` ;
  * Windows : pas d'`O_NOFOLLOW` (repli : `O_EXCL`, soit `CREATE_NEW`, `lstat`
    et identité ; `st_ino` peut valoir 0 sur FAT) ; systèmes de fichiers réseau
    (NFS/SMB, atomicité d'`O_EXCL` faible sur les vieux NFS) : NON mesurés ;
  * Linux : NON mesuré — tous les chiffres ci-dessus sont relevés sur darwin ;
    la jambe `--linux` de la porte est sous dérogation pilote sur ce dépôt, et
    les témoins n'y tournent qu'en CI ubuntu (non bloquante) ;
  * LES AUTRES OUVREURS PAR NOM des mêmes stores passent, depuis T-00000770,
    par la MÊME primitive (`store.ouvrir_sans_suivre` + `refuser_les_liens`,
    chargée par chemin hors paquet) : `.agents/bin/event_store.py::open_store`
    (`events.db`), `agentic_v3/db/schema.py::create_tables`/`get_db_connection`
    et `agentic_v3/db/run_export.py::_ouvrir_base_sqlite` (le store V3),
    `.agents/bin/migrate_index_to_db.py::connect` (`index.db`), et `cadre lessons
    promote` (`cli.py`, le magasin de leçons). `.agents/bin/events.py`, que ce
    paragraphe nommait, n'ouvre AUCUNE base : il n'y avait rien à fermer. Restent
    HORS de ce périmètre, bornées : les ouvertures `mode=ro` (`event_store.py::
    store_footprint`, la sonde `mode=ro` de `migrate_index_to_db.py`,
    `symbols.py`), qui ne créent ni n'écrivent ; et les bornes ci-dessus
    (ancêtre échangé, ABA, inode recyclé, Windows, NFS/SMB) valent pour ces
    ouvreurs comme pour la wheel.

TRADUCTION DU REFUS (T-00000770). La primitive lève `store.EmplacementRefuse`
(ou `store.OuvertureImpossible`, fille de `sqlite3.OperationalError`, quand SQLite
ne peut ouvrir un store dont l'emplacement est inchangé — panne d'accès hors
paquet, refus nommé ici comme avant) ;
`_traduire` la relève en `StoreRefuse` HORS du bloc `except`, avec la CAUSE de
l'original (`from exc.__cause__` si elle existe) : la chaîne d'exceptions est
celle d'avant le déplacement — un `from exc` y intercalerait un maillon que les
témoins T-00000759 (`__cause__.__cause__`, `__cause__.__context__`) refusent. Le
tuple d'`except` de `creer_les_stores` reste donc inchangé et le message dit
toujours `StoreRefuse: …`.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from cadre.ledger import store, stores_schemas
from cadre.paths import (
    CadrePathError,
    canonique_disque,
    index_db,
    project_root,
    state_project,
)
from cadre.workspace import HorsRacine, Workspace

__all__ = ["StoresCrees", "chemins_des_stores", "creer_les_stores"]

#: Emplacement, RELATIF à la racine cible, du SEUL store qui vit encore SOUS elle
#: — LU par `chemins_des_stores` seul. Le store V3 (T-00000650) et l'index
#: (T-00000668) n'en ont plus : ils vivent sous la partition machine, chemins
#: calculés dans `chemins_des_stores` (l'index par `cadre.paths.index_db`).
_REL_DB_EVENTS = ".agents/state/local/events.db"
#: Le verrou de maintenance du spool, à l'emplacement PAR DÉFAUT d'`events.py`
#: (`_events_dir() / _MAINTENANCE_LOCK_NAME`) : présent et plus jeune que
#: `_MAINTENANCE_PERIMEE_S`, il fait refuser la CRÉATION d'`events.db`
#: (T-00000646, F4). Parité de chemin tenue par `VerrouDeMaintenanceTests`.
_REL_VERROU_MAINTENANCE = ".agents/state/events/.maintenance.lock"
#: Âge, en secondes, au-delà duquel ce verrou est celui d'un détenteur MORT —
#: `events._MAINTENANCE_STALE_SECONDS`, RECOPIÉ : `events.py` vit sous
#: `.agents/bin/`, hors de la wheel, qui ne charge aucun module du dépôt
#: (S-00001590). Parité tenue par `VerrouDeMaintenanceTests`, qui lit les deux
#: côtés (T-00000646, S-00002323).
_MAINTENANCE_PERIMEE_S = 600.0
#: Mode d'un store NEUF (T-00000759, décision R1 du plan) : données d'exécution
#: PRIVÉES d'un utilisateur, lues seulement par des processus du même uid. ÉCART
#: VOULU avec `0o666 & ~umask` de `Workspace.write_bytes` ; `-wal`/`-shm` en
#: héritent (SQLite, mesuré 3.53.4). Un store déjà présent garde le sien.
_MODE_STORE = 0o600


@dataclass(frozen=True)
class StoresCrees:
    """Les chemins ABSOLUS des trois stores, jamais `None`. `events` vit SOUS la
    racine cible ; `v3_event_store` (T-00000650) et `index`, comme lui
    (T-00000668), vivent sous la PARTITION MACHINE de la racine cible
    (`state_project()`), HORS dépôt."""

    v3_event_store: Path
    events: Path
    index: Path


def chemins_des_stores(racine) -> StoresCrees:
    """Les chemins des trois stores de `racine`, SANS RIEN ÉCRIRE.

    `racine` est CANONISÉE par `cadre.paths.project_root`. Si la racine résolue
    diverge de l'argument — `$CADRE_PROJECT_ROOT` ou la racine git prime — on
    REFUSE (`CadrePathError`) : créer les stores ailleurs que là où l'appelant
    l'a demandé serait une divergence silencieuse.
    """
    base = project_root(depuis=racine)
    demandee = canonique_disque(Workspace(racine).racine)
    if demandee != base:
        raise CadrePathError(
            f"racine demandée {demandee} ≠ racine résolue {base} : "
            f"$CADRE_PROJECT_ROOT ou la racine git prime sur l'argument. Créer les "
            f"stores ailleurs que là où l'appelant l'a demandé serait une divergence "
            f"silencieuse — aucun store n'est créé. Nommez la bonne racine, ou "
            f"retirez la variable d'environnement."
        )
    return StoresCrees(
        v3_event_store=state_project(depuis=base) / "run" / "v3_event_store.db",
        events=base / _REL_DB_EVENTS,
        index=index_db(depuis=base),
    )


def _traduire(appel):
    """`appel()`, un `store.EmplacementRefuse` — ou un `store.OuvertureImpossible`,
    la panne d'accès d'un store inchangé que SQLite ne peut ouvrir, refus de la
    wheel comme avant T-00000770 — relevé en `StoreRefuse` — même
    message, HORS du bloc `except`, `from` la CAUSE de l'original s'il en porte
    une (l'`OperationalError` de SQLite), sans `from` sinon. C'est la seule forme
    qui rend la chaîne d'avant le déplacement (T-00000770, mesuré) : un `from
    exc` intercale l'`EmplacementRefuse` entre `StoreRefuse` et sa cause, et sans
    `from` le `__context__` redevient l'exception que l'appelant traite (celle de
    `_nommer_un_lien_d_annexe`), ce que les témoins T-00000759 tiennent."""
    try:
        return appel()
    except (store.EmplacementRefuse, store.OuvertureImpossible) as exc:
        message, cause = str(exc), exc.__cause__
    if cause is not None:
        raise stores_schemas.StoreRefuse(message) from cause
    raise stores_schemas.StoreRefuse(message)


def _refuser_les_liens(ws: Workspace, rel: str) -> None:
    """`store.refuser_les_liens` (T-00000759, déplacé par T-00000770) :
    refuse un LIEN à l'emplacement du store `rel` ou de l'un de ses annexes,
    pendant ou non, une feuille ou un annexe présent qui n'est pas un fichier
    régulier ou qui porte plus d'un lien physique — rien n'est suivi, supprimé
    ni remplacé. Traduit en `StoreRefuse` (`_traduire`) ; `HorsRacine` si un
    PARENT sort de la racine. NON redondant avec `_ouvrir` : `_sonder` l'appelle
    AVANT `ws.exists`, qui suit la feuille et dirait « absent » d'un lien
    pendant — `_sonder` rentrerait avant toute ouverture."""
    _traduire(lambda: store.refuser_les_liens(ws, rel))


def _ouvrir(ws: Workspace, rel: str, *, creer: bool) -> tuple[sqlite3.Connection, Path]:
    """Ouvre le store `rel` et rend `(connexion, chemin)`, la connexion déjà
    `patienter`-ée, AUCUN octet écrit par cette fonction au-delà du fichier
    vide qu'elle crée.

    L'ouverture est `store.ouvrir_sans_suivre` (T-00000770 : la primitive
    commune à tous les ouvreurs de stores, déplacée d'ici) : identité créée
    exclusive (`_MODE_STORE`) ou relue et jugée avant toute ouverture,
    ouverture SANS création (`store.connect(…, sans_creation=True)`), puis
    l'identité APRÈS ouverture en deux moitiés (`PRAGMA database_list`, seconde
    identité) — voir sa docstring. Son refus est traduit en `StoreRefuse`
    (`_traduire`), qui dit ce que le nom désigne désormais. Seul le
    `patienter` reste ici ; une levée de `patienter` referme la connexion AVANT
    tout `garantir_*` ou sonde."""
    conn, ident, _cree = _traduire(
        lambda: store.ouvrir_sans_suivre(ws, rel, creer=creer, mode=_MODE_STORE))
    try:
        stores_schemas.patienter(conn)
    except BaseException:
        conn.close()
        raise
    return conn, ident.chemin


def _nommer_un_lien_d_annexe(ws: Workspace, rel: str, etape, conn) -> None:
    """`etape(conn)` — une sonde ou une garantie. Sur `sqlite3.OperationalError`,
    re-juge les liens (`_refuser_les_liens`) AVANT de relever l'erreur
    d'origine : un lien d'annexe planté APRÈS le jugement fait lever SQLite
    (`unable to open database file`, CANTOPEN, mesuré 3.53.4) sans le nommer ;
    le `StoreRefuse` qui en sort le NOMME, l'erreur de SQLite en contexte. Une
    autre levée (verrou tenu, fichier illisible) ne trouve rien et sort telle
    quelle."""
    try:
        etape(conn)
    except sqlite3.OperationalError:
        _refuser_les_liens(ws, rel)
        raise


def _sonder(ws: Workspace, rel: str, sonde) -> None:
    """Sonde un store DÉJÀ présent par une connexion nue en écriture, patron de
    `create_tables` : lit le WAL, n'écrit rien de son chef — aucun PRAGMA
    d'écriture, même sha, aucun annexe laissé. Elle attend un écrivain tenant
    autant que la création (`stores_schemas.patienter`, 30 s), jamais le défaut
    de 5 s de `sqlite3.connect`. `mode=ro&immutable=1` IGNORAIT le
    WAL (mesuré : `user_version` 0 là où la base en déclare 2), et `mode=ro`
    laisse `-wal`/`-shm` sur disque. BORNE, celle du producteur : un WAL
    ORPHELIN (aucun autre connecté) est rabattu dans la base à la fermeture —
    rien n'est perdu, mais ses octets bougent. Un store absent n'est pas sondé :
    il naîtra vide.

    T-00000759 : AVANT tout, `_refuser_les_liens` — un lien à l'emplacement du
    store ou d'un annexe est refusé même PENDANT, que `exists` dirait absent.
    L'ouverture passe par `_ouvrir` (sans création, identité vérifiée), et la
    sonde par `_nommer_un_lien_d_annexe` : un lien d'annexe planté entre ce
    jugement et la première lecture fait lever SQLite (CANTOPEN, le lien
    reste — mesuré 3.53.4, `-wal`, `-shm` et `-journal`) et le refus le
    nomme."""
    _refuser_les_liens(ws, rel)
    if not ws.exists(rel):
        return
    conn, _chemin = _ouvrir(ws, rel, creer=False)
    try:
        _nommer_un_lien_d_annexe(ws, rel, sonde, conn)
    finally:
        conn.close()


def _refuser_si_maintenance(ws: Workspace, rel_events: str) -> None:
    """Refuse de CRÉER `events.db` pendant qu'une maintenance du spool tient
    `.maintenance.lock` — le même jugement que `events.maintenance_lock` : la
    PRÉSENCE du fichier (`O_CREAT|O_EXCL`, pas un verrou de noyau) ET son ÂGE.
    Plus vieux que `_MAINTENANCE_PERIMEE_S`, c'est le verrou d'un détenteur
    mort : IGNORÉ, jamais supprimé (seul son producteur le reprend). Un âge
    illisible compte pour 0, donc frais, comme chez le producteur. Un
    `events.db` présent n'est que monté : aucune course C2, aucun refus."""
    if ws.exists(rel_events) or not ws.exists(_REL_VERROU_MAINTENANCE):
        return
    try:
        age = ws.age_secondes(_REL_VERROU_MAINTENANCE)
    except OSError:
        age = 0.0
    if age <= _MAINTENANCE_PERIMEE_S:
        raise stores_schemas.StoreRefuse(
            "une maintenance du spool tient .maintenance.lock : créer events.db "
            "rouvrirait la course C2 d'events.py. Relancez quand elle a fini. "
            f"Un verrou de plus de {_MAINTENANCE_PERIMEE_S / 60:g} min est "
            "ignoré (orphelin), jamais supprimé."
        )


def _creer_et_garantir(ws: Workspace, rel: str, garantir) -> Path:
    """Le répertoire parent, puis `_ouvrir(creer=True)` — fichier vide né
    EXCLUSIF et non suivi, ouverture sans création, identité vérifiée —, puis
    `garantir`, par `_nommer_un_lien_d_annexe` : une levée de SQLite pendant
    la garantie re-juge les liens et nomme un lien d'annexe planté depuis la
    sonde (mesuré : `-shm` avant le passage en WAL ⇒ CANTOPEN, le lien reste).
    Un store apparu entre la sonde et ici est ouvert TEL QUEL, jamais
    remplacé ; un lien planté entre-temps est refusé. Rend le chemin créé ou
    vérifié."""
    ws.creer_repertoire(Path(rel).parent)
    conn, chemin = _ouvrir(ws, rel, creer=True)
    try:
        _nommer_un_lien_d_annexe(ws, rel, garantir, conn)
    finally:
        conn.close()
    return chemin


def _creer_v3(ws: Workspace, rel: str) -> Path:
    """`v3_event_store.db`, sous la partition machine (`ws` y est enraciné).
    Le fichier naît VIDE par `Workspace.creer_fichier_exclusif` — jamais par
    SQLite, qui suivait un lien planté à sa place — puis s'ouvre sans création
    (`_creer_et_garantir`, T-00000759) ; un store apparu entre-temps n'est
    jamais remplacé."""
    return _creer_et_garantir(ws, rel, stores_schemas.garantir_v3)


def _creer_events(ws: Workspace, rel: str) -> Path:
    """`events.db`, sous la racine du dépôt. Le spool n'est ni lu ni touché ; la
    création est refusée sous une maintenance du spool (re-vérifiée ICI, au plus
    près de l'ouverture). Naissance exclusive puis ouverture sans création,
    comme `_creer_v3`."""
    _refuser_si_maintenance(ws, rel)
    return _creer_et_garantir(ws, rel, stores_schemas.garantir_events)


def _creer_index(ws: Workspace, rel: str) -> Path:
    """`index.db`, sous la partition machine (`ws` y est enraciné, le MÊME
    atelier que `_creer_v3` — T-00000668) — vide s'il naît, seulement monté de
    schéma s'il existe. Naissance exclusive puis ouverture sans création,
    comme `_creer_v3`."""
    return _creer_et_garantir(ws, rel, stores_schemas.garantir_index)


def creer_les_stores(racine) -> StoresCrees:
    """Crée (ou met à niveau, idempotent) les trois stores de l'adoptant sous
    `racine`, par le code de la wheel.

    Trois temps : (1) `chemins_des_stores(racine)`, qui refuse une racine
    divergente ; (2) la SONDE de chaque store déjà présent — et du verrou de
    maintenance du spool —, AVANT toute écriture ; (3) la création. Tout refus
    de `stores_schemas`, toute `sqlite3.Error`, `OSError` ou `HorsRacine` est
    traduit en `CadrePathError`, dont le message dit OÙ le refus est tombé :
    à la sonde, aucun store créé ni monté ; après, les stores déjà traités
    restent créés ou montés et un rejeu reprend UNE FOIS la cause nommée levée
    — un lien, un second nom ou un annexe non régulier persistent d'un rejeu à
    l'autre (binôme fable). Rend les chemins absolus des trois stores.
    """
    chemins = chemins_des_stores(racine)
    base = project_root(depuis=racine)
    machine = state_project(depuis=base)
    depot: Workspace = Workspace(base)
    partition: Workspace = Workspace(machine)
    rel_v3 = chemins.v3_event_store.relative_to(machine).as_posix()
    rel_events = chemins.events.relative_to(base).as_posix()
    # L'index vit sous la partition machine (T-00000668) : `rel` relatif à
    # `machine`, atelier `partition` — le même que le store V3.
    rel_index = chemins.index.relative_to(machine).as_posix()
    # Le premier ÉCRIT n'est pas le retour de `_creer_v3` mais son SEUIL :
    # `creer_repertoire`, puis la création EXCLUSIVE du fichier vide, puis le
    # passage en WAL. Une levée DANS `_creer_v3` laisse donc déjà un store touché.
    ecriture_commencee = False
    try:
        _sonder(partition, rel_v3, stores_schemas.sonder_v3)
        _sonder(depot, rel_events, stores_schemas.sonder_events)
        _refuser_si_maintenance(depot, rel_events)
        _sonder(partition, rel_index, stores_schemas.sonder_index)
        ecriture_commencee = True
        v3 = _creer_v3(partition, rel_v3)
        events = _creer_events(depot, rel_events)
        index = _creer_index(partition, rel_index)
    except (stores_schemas.StoreRefuse, sqlite3.Error, OSError, HorsRacine) as exc:
        suite = ("Les stores déjà traités restent créés ou montés ; relancer "
                 "reprend une fois la cause nommée ci-dessus levée."
                 if ecriture_commencee
                 else "Refus à la sonde : aucun store créé ni monté.")
        raise CadrePathError(
            f"création des stores refusée sous {base} : {type(exc).__name__}: "
            f"{str(exc).rstrip('.')}. {suite}"
        ) from exc
    return StoresCrees(v3_event_store=v3, events=events, index=index)
