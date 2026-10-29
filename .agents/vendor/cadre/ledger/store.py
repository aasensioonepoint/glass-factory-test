"""L'UNIQUE OUVERTURE DE CONNEXION SQLITE DU SERVICE — et rien d'autre.

Phase 2 de T-012. Ce module est le SEUL autorisé à appeler `sqlite3.connect`
dans le service ledger, et le banc local `test_cadre_ledger_purete` le tient : il
REFUSE `connect` partout dans `ledger/**` SAUF `ledger/store.py` (reconnu par
chemin relatif). Ce module n'a PLUS besoin d'être exempté du filet GLOBAL
`check_orchestration_purity` (`test_cadre_package`) : mesuré, `_fautifs_purete`
le rend `[]` sans exemption, parce que `sqlite3.connect` n'est ni un import impur
ni un verbe d'E/S de son jeu — l'exemption `ledger/store.py` y a donc été RETIRÉE
(elle retirait store.py de `IMPORTS_IMPURS`, ce qui était inutile). Tout le reste
du service opère sur la connexion qu'il rend. Ses seules autres E/S passent par
le `Workspace` REÇU (`identite`, `creer_fichier_exclusif`) ; il n'importe aucun
module `cadre` — chargeable par chemin (T-00000770). Il ne crée pas de
répertoire (le banc de discipline `test_cadre_ledger_purete` couvre store.py pour
tout `IO_PAR_METHODE ∪ {is_dir, exists, is_file, stat}`) : le répertoire cible
est supposé exister, sa création relève de l'appelant (`Workspace.creer_repertoire`
dans `stores.py`, `mkdir` du parent chez les producteurs hors paquet).

OUVERTURE NON SUIVIE (T-00000770). `ouvrir_sans_suivre` et `refuser_les_liens`
sont la primitive d'ouverture des ouvreurs par nom EN ÉCRITURE des stores
SQLite — ceux qui créent ou écrivent, énumérés, pas « tous » : `stores.py` (la
wheel) et les producteurs hors paquet `event_store.py::open_store`,
`agentic_v3/db/schema.py` (`create_tables`, `get_db_connection`) et
`run_export.py::_ouvrir_base_sqlite`, `migrate_index_to_db.py::connect`, `cadre
lessons promote`. HORS de ce périmètre, nommées : les ouvertures en LECTURE
SEULE `mode=ro` — `symbols.py` (sa connexion de lecture de l'index),
`migrate_index_to_db.py` (sa sonde `mode=ro` de l'index) et
`event_store.py::store_footprint` —, qui ne créent ni n'écrivent, et suivent
donc encore un lien à l'emplacement (lecture d'une base tierce possible,
écriture impossible). Ce module reste STDLIB-SEUL pour qu'un producteur qui ne trouve
pas le paquet `cadre` installé le charge PAR CHEMIN depuis `src/cadre/ledger/`
(couture S-00001655) : aucun `cadre.*` importé, ni au niveau module ni sous
`TYPE_CHECKING` (témoin U0). Le `Workspace` est REÇU, jamais importé : les
`Identite` viennent de ses méthodes, donc d'UNE seule copie de classe par appel,
même quand paquet et copie par chemin coexistent dans un processus. Le refus lève
`EmplacementRefuse`, fille de `ValueError` : un site hors paquet attrape
`ValueError`, jamais cette classe (celle d'une AUTRE copie ne l'attraperait pas) ;
`stores.py` la traduit en `StoreRefuse` en gardant la chaîne d'exceptions. Un
store à l'emplacement INCHANGÉ que SQLite ne peut pas ouvrir (droits) n'est PAS
un refus d'emplacement : `OuvertureImpossible`, fille de
`sqlite3.OperationalError` — une panne d'accès (décision de l'orchestrateur,
délégation pilote). Les messages sont ceux de T-00000759, déplacés verbatim de
`stores.py`.

EMPLACEMENT DU MAGASIN — CONFLIT NON TRANCHÉ, POSÉ À LA PORTE 2 (R-A12) : la spec
écrit « Ledger d'état : dans STATE_HOME » tandis que la table des racines range
les leçons locales en ETAT_EQUIPE (`.agents/state/`, suivi par git) — deux
emplacements incompatibles. CE MODULE NE TRANCHE PAS : le chemin du store est un
PARAMÈTRE (`chemin`), résolu par l'appelant ; l'arbitrage est une décision pilote
de la PORTE 2.

LECTURE SEULE VÉRIFIABLE : `lecture_seule=True` ouvre en
`file:…?mode=ro&immutable=1`, ce qui LIT un store en `chmod 444` et REFUSE toute
écriture (`sqlite3.OperationalError`). Elle EXIGE un chemin ABSOLU : un relatif
est refusé par un `ValueError` NOMMÉ (« chemin relatif refusé »), jamais résolu
en silence contre le cwd — la résolution appartient à l'appelant, pas à cette
couche. C'est la plomberie du référentiel embarqué ; son CONTENU n'est pas
préempté ici. `Path.as_uri` percent-encode le chemin : pas d'`urllib` importé
ici, qui est un interdit réseau du noyau (`check_no_network` scanne AUSSI
store.py). La branche NORMALE (écriture) accepte toujours un relatif, ouvert
relatif au cwd comme avant.

OUVERTURE SANS CRÉATION (T-00000759) : `sans_creation=True` ouvre en
`file:…?mode=rw` — lecture ET écriture, mais SQLite ne CRÉE rien : un fichier
absent, ou un lien PENDANT planté à sa place, fait lever
`sqlite3.OperationalError` (« unable to open ») au lieu de naître au bout du
lien (mesuré, SQLite 3.53.4). Même exigence d'un chemin ABSOLU que la lecture
seule, même `PRAGMA foreign_keys = ON` que la branche normale. C'est la moitié
« ouverture » de la création des stores de `stores.py` : le fichier y naît par
`Workspace.creer_fichier_exclusif`, puis s'ouvre ici sans création. Ce drapeau
ne SUIT pas moins un lien vers un fichier EXISTANT : c'est à l'appelant de
vérifier ce qu'il a ouvert (`PRAGMA database_list`). `lecture_seule=True` ne
crée rien non plus et PRIME s'il est passé avec lui.

BORNE WINDOWS (l'hôte de développement nommé par `workspace.py`) : `Path.is_absolute()`
y rend False sur un chemin POSIX-absolu (`/x/y.db`), qui est donc REFUSÉ en
lecture seule — DÉLIBÉRÉMENT : `as_uri()` y lèverait de toute façon, et l'ancien
`.resolve()` l'attachait SILENCIEUSEMENT au lecteur courant. `":memory:"` tombe
sous le même refus (lexicalement relatif). Un appelant Windows en lecture seule
passe un chemin absolu de la plateforme (avec lettre de lecteur). Un chemin UNC
(`\\\\serveur\\partage\\…`) sort de `as_uri` en `file://serveur/…`, serveur en
AUTORITÉ, que SQLite refuse (« invalid uri authority ») : `_uri_absolue` le
réécrit `file:////serveur/…` (T-00000759, binôme F2). CE QUI EST MESURÉ, sur
darwin seul : la forme rendue par `PureWindowsPath.as_uri`, le refus de
l'autorité par SQLite 3.53.4, et l'ACCEPTATION syntaxique de `file:////…`
(témoin `UriAbsolueTests`). L'OUVERTURE WINDOWS elle-même — lecteur comme
partage UNC, en lecture seule comme sans création — n'est PAS mesurée.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

__all__ = ["connect", "ouvrir_sans_suivre", "refuser_les_liens", "EmplacementRefuse",
           "OuvertureImpossible"]

#: Les annexes qu'SQLite ouvre À CÔTÉ d'un store : un lien à l'un de ces noms est
#: refusé comme un lien sur le store lui-même, et un annexe présent qui n'est pas
#: un fichier régulier, ou qui porte plus d'un lien physique, l'est aussi
#: (T-00000759, `_juger_l_annexe` ; déplacé de `stores.py` par T-00000770).
_ANNEXES = ("-wal", "-shm", "-journal")


class EmplacementRefuse(ValueError):
    """L'emplacement d'un store est refusé : un lien (symbolique ou physique),
    un non-régulier, un annexe douteux, `":memory:"`, un nom qui a changé entre
    le jugement et l'ouverture. Rien n'a été suivi ni supprimé (T-00000770).

    Fille de `ValueError`, comme `HorsRacine` : les sites hors paquet attrapent
    `ValueError`, JAMAIS cette classe — deux copies de ce module (le paquet
    installé et un chargement par chemin) peuvent coexister dans un processus,
    chacune avec SA classe. `stores.py` la traduit en `StoreRefuse`. Exception
    MESURÉE, hors paquet : `.agents/bin/tasks_sync.py::replay_sync` et
    `drain_sync_outbox` (T-00000782, T-00001007) la prennent PAR LA COUTURE
    `agentic_v3/db/run_export.py::_couture_ledger_store`, qui rend le même
    objet-classe que celui que lèvent `create_tables` et `get_db_connection`."""


class OuvertureImpossible(sqlite3.OperationalError):
    """SQLite ne peut pas ouvrir un store dont l'emplacement est INCHANGÉ — le
    nom désigne encore le fichier régulier jugé, identité égale champ pour
    champ (droits, CANTOPEN) : une PANNE D'ACCÈS, pas un refus d'emplacement
    (décision de l'orchestrateur, délégation pilote, T-00000770). Levée `from`
    l'erreur de SQLite, avec le message d'un refus d'ouverture (« le nom désigne
    le même fichier »).

    Fille de `sqlite3.OperationalError` et NON de `ValueError`, délibérément :
    les sites hors paquet la rangent avec les erreurs SQLite (`event_store` :
    `unavailable` ; `run_export`, `migrate_index_to_db`, `schema` : elle sort
    telle quelle, comme avant T-00000770) — jamais sous le refus d'emplacement
    qu'ils attrapent par `ValueError`. `sqlite3` étant UN module du processus,
    l'attraper par `sqlite3.Error` vaut quelle que soit la copie de ce module.
    `stores.py` la traduit en `StoreRefuse` comme un refus (chaîne gardée)."""


def _uri_absolue(chemin: Path, usage: str, parametres: str) -> str:
    """`file:` + chemin ABSOLU percent-encodé (`as_uri`) + `parametres`. Un
    chemin UNC (`\\\\serveur\\partage\\…`) sort de `as_uri` avec le SERVEUR en
    autorité (`file://serveur/…`), que SQLite refuse (« invalid uri
    authority », mesuré 3.53.4) : il est réécrit `file:////serveur/…`, serveur
    dans le CHEMIN (T-00000759, binôme F2). Voir § BORNE WINDOWS."""
    if not chemin.is_absolute():
        raise ValueError(
            f"store {usage} : chemin relatif refusé — résolu par "
            f"l'appelant : {chemin}"
        )
    uri = chemin.as_uri()
    if not uri.startswith("file:///"):
        uri = "file:////" + uri[len("file://"):]
    return uri + parametres


def _uri_lecture_seule(chemin: Path) -> str:
    return _uri_absolue(chemin, "en lecture seule", "?mode=ro&immutable=1")


def connect(chemin, *, lecture_seule: bool = False,
            sans_creation: bool = False) -> sqlite3.Connection:
    """Ouvre le store à `chemin`. `lecture_seule` ⇒ `mode=ro&immutable=1` ;
    `sans_creation` ⇒ `mode=rw` (écriture, mais un fichier absent ou un lien
    pendant LÈVE au lieu d'être créé — T-00000759).

    `lecture_seule=True` comme `sans_creation=True` EXIGENT un chemin ABSOLU —
    un relatif lève `ValueError` (« chemin relatif refusé ») au lieu d'être
    résolu contre le cwd ; la branche normale accepte toujours un relatif,
    ouvert relatif au cwd. Les deux ensemble valent `lecture_seule`.

    Active `row_factory = sqlite3.Row` (accès par nom de colonne) et, en écriture
    seulement, `PRAGMA foreign_keys = ON` — le lien `ref_forme_generalisee` en
    dépend, et le pragma ne s'applique qu'aux écritures.
    """
    p = Path(chemin)
    if lecture_seule:
        conn = sqlite3.connect(_uri_lecture_seule(p), uri=True)
    elif sans_creation:
        conn = sqlite3.connect(
            _uri_absolue(p, "sans création", "?mode=rw"), uri=True)
        conn.execute("PRAGMA foreign_keys = ON")
    else:
        conn = sqlite3.connect(str(p))
        conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


# --- Le jugement d'un emplacement (T-00000759, déplacé par T-00000770) --------
# Les six aides ci-dessous sont celles de `stores.py`, messages VERBATIM ; seule
# la classe levée change (`EmplacementRefuse`). Leurs paramètres `ident`/`apres`
# sont des `Identite` rendues par le `Workspace` reçu — non annotées : ce module
# n'importe pas `cadre.workspace`.


def _refuser_memoire(rel) -> None:
    """`EmplacementRefuse` si `rel` est `":memory:"` : SQLite l'ouvre EN
    MÉMOIRE, le système de fichiers y voit un NOM — la création exclusive en
    ferait naître un fichier de ce nom dans le répertoire du `Workspace`, et
    aucun jugement d'identité ne couvre une base en mémoire."""
    if str(rel) == ":memory:":
        raise EmplacementRefuse(
            "':memory:' refusé : ce nom désigne une base EN MÉMOIRE pour SQLite et "
            "un FICHIER pour le système de fichiers — un store s'ouvre par un chemin "
            "de fichier. Rien n'est créé")


def _lien_refuse(ident) -> str:
    return (f"{ident.chemin} est un lien symbolique à l'emplacement d'un store : "
            f"un store ne se crée ni ne s'ouvre à travers un lien, qui le ferait "
            f"écrire ailleurs. Rien n'est suivi ni supprimé — retirez le lien")


def _juger_la_feuille(ident) -> None:
    """`EmplacementRefuse` si la feuille d'un store est un lien symbolique,
    n'est pas un fichier régulier (répertoire, tube, socket), ou porte PLUS D'UN
    lien physique : un autre nom désigne alors le même inode, et écrire le store
    réécrirait le fichier de cet autre nom (binôme F1 — mesuré : un
    `pkg/__init__.py` vide devenait une base SQLite). Rien n'est touché."""
    if ident.est_lien:
        raise EmplacementRefuse(_lien_refuse(ident))
    if not ident.est_regulier:
        raise EmplacementRefuse(
            f"{ident.chemin} n'est pas un fichier régulier : ce n'est pas un "
            f"store. Rien n'est touché")
    if ident.nliens > 1:
        raise EmplacementRefuse(
            f"{ident.chemin} porte {ident.nliens} liens physiques : un autre nom "
            f"désigne le même fichier, qu'écrire ce store réécrirait. Rien n'est "
            f"touché — retirez l'autre nom")


def _juger_l_annexe(annexe, suffixe: str) -> None:
    """`EmplacementRefuse` si l'annexe `suffixe` d'un store existe et n'est pas
    un fichier régulier : un lien (`_lien_refuse`), ou un répertoire, un tube,
    une socket — que SQLite ne pourrait ni ouvrir ni remplacer, et sur lequel il
    échouait APRÈS avoir créé le store (binôme fable, mesuré : « disk I/O
    error » sur un `-wal` répertoire) ; ou s'il porte PLUS D'UN lien physique,
    comme la feuille (`_juger_la_feuille`) : un autre nom désigne ce fichier,
    et SQLite RETIRAIT ce nom-ci (mesuré, darwin, 3.53.4 : `-wal` second nom
    d'un fichier tiers, store neuf comme existant — octets intacts, nom d'un
    tiers supprimé). Rien n'est touché."""
    if annexe.est_lien:
        raise EmplacementRefuse(_lien_refuse(annexe))
    if not annexe.est_regulier:
        raise EmplacementRefuse(
            f"{annexe.chemin} n'est pas un fichier régulier à l'emplacement d'un "
            f"annexe de store ({suffixe}) : SQLite ne pourrait ni l'ouvrir ni le "
            f"remplacer. Rien n'est touché — retirez-le")
    if annexe.nliens > 1:
        raise EmplacementRefuse(
            f"{annexe.chemin} porte {annexe.nliens} liens physiques à l'emplacement "
            f"d'un annexe de store ({suffixe}) : un autre nom désigne le même "
            f"fichier, que SQLite prendrait pour son annexe. Rien n'est touché — "
            f"retirez l'autre nom")


def _designe_encore(ident, apres) -> bool:
    """Vrai si le nom désigne ENCORE le fichier `ident` : un fichier RÉGULIER,
    pas un lien, de même `(dev, ino)`.

    `est_regulier` est EXIGÉ (T-00001179, S-00004110) : le store est un fichier
    régulier — né exclusif, ou jugé tel par `_juger_la_feuille` —, donc un nom
    qui désigne un NON-régulier (répertoire, tube, socket) ne le désigne
    JAMAIS, même quand le noyau a RECYCLÉ son inode. Mesuré sous Linux
    (python:3.12-slim) : `unlink` puis `mkdir` au même nom rend le MÊME
    `(dev, ino)`, avec `st_nlink=2` ; sans cette exigence, le répertoire neuf
    passait pour « le même fichier, qui porte désormais 2 liens physiques »,
    et `_ce_qui_reste` affirmait que le fichier vide créé « reste en place ».
    Sur darwin (APFS) l'inode n'est pas réutilisé : le défaut n'y paraît pas.

    RÉSIDU NOMMÉ, NON RÉSOLU ICI (borne L-00000074 d'`Identite`) : un fichier
    RÉGULIER recréé par un tiers sur un inode recyclé reste INDISCERNABLE par
    `(dev, ino)` — il passe pour « le même fichier ». Le distinguer demanderait
    `ctime`/`birthtime` : décision pilote, pas un correctif de ce module."""
    return (apres is not None and not apres.est_lien and apres.est_regulier
            and (apres.dev, apres.ino) == (ident.dev, ident.ino))


def _ce_que_le_nom_designe(ident, apres) -> str:
    """Ce que le nom du store désigne APRÈS coup, rapporté à `ident` : rien,
    un lien symbolique, un autre fichier, ou le même fichier (dont le nombre
    de liens physiques est dit s'il a changé). « Un autre fichier » couvre
    aussi un NON-régulier (répertoire, tube, socket), même s'il a repris le
    `(dev, ino)` de `ident` : `_designe_encore` l'exclut (T-00001179)."""
    if apres is None:
        return "rien"
    if apres.est_lien:
        return "un lien symbolique"
    if not _designe_encore(ident, apres):
        return "un autre fichier"
    if apres.nliens != ident.nliens:
        return f"le même fichier, qui porte désormais {apres.nliens} liens physiques"
    return "le même fichier"


def _ce_qui_reste(cree: bool, ident, apres) -> str:
    """La fin d'un refus d'ouverture : sur le chemin de VÉRIFICATION rien
    n'a été écrit ; sur le chemin de CRÉATION le fichier vide né exclusif
    « reste en place » SEULEMENT si le nom le désigne encore — sinon un tiers
    l'a retiré ou remplacé, et rien n'est supprimé (binôme F5)."""
    if not cree:
        return "rien écrit"
    if _designe_encore(ident, apres):
        return "aucune écriture de schéma ; le fichier vide créé reste en place"
    return ("aucune écriture de schéma ; le fichier vide créé a été retiré ou "
            "remplacé par un tiers — rien n'est supprimé, retirez ce qui occupe "
            "le nom puis relancez")


def refuser_les_liens(ws, rel) -> None:
    """Refuse un LIEN à l'emplacement du store `rel` ou de l'un de ses annexes
    (`_ANNEXES`), pendant ou non, une feuille `rel` présente qui n'est pas un
    fichier régulier ou qui porte plus d'un lien physique, et un annexe présent
    qui n'est pas un fichier régulier ou qui porte plus d'un lien physique —
    par `ws.identite`, qui ne suit pas la feuille : `exists` la suit, donc
    dirait « absent » d'un lien pendant, que SQLite suivrait pour CRÉER sa cible
    (mesuré, M6/M1). Rien n'est supprimé ni remplacé : ni le lien, ni sa cible
    (« aucune suppression sans trace »). `":memory:"` est refusé d'abord.

    `ws` est un `cadre.workspace.Workspace` (celui du paquet ou d'une copie
    chargée par chemin) enraciné au répertoire du store. `HorsRacine` si un
    PARENT sort de sa racine ; toute autre `OSError` de `identite` (un parent
    qui est un fichier) est levée telle quelle."""
    _refuser_memoire(rel)
    principal = ws.identite(rel)
    if principal is not None:
        _juger_la_feuille(principal)
    for suffixe in _ANNEXES:
        annexe = ws.identite(str(rel) + suffixe)
        if annexe is not None:
            _juger_l_annexe(annexe, suffixe)


def ouvrir_sans_suivre(ws, rel, *, creer: bool, mode: int = 0o600, connecter=None):
    """Ouvre le store `rel` du `Workspace` `ws` SANS SUIVRE de lien, et rend
    `(connexion, identite, cree)` — AUCUN octet écrit au-delà du fichier vide
    que la création exclusive fait naître. `":memory:"` est refusé d'abord.

    (1) L'identité : `creer` ⇒ le fichier naît VIDE par
    `ws.creer_fichier_exclusif` (`O_CREAT|O_EXCL|O_NOFOLLOW`, `mode`) ; nom déjà
    pris (créateur concurrent, store apparu depuis la sonde) ou `creer=False` ⇒
    l'identité EXISTANTE est relue et jugée (`_juger_la_feuille` : ni lien, ni
    non régulier, ni plusieurs liens physiques) AVANT toute ouverture ; absente,
    c'est un refus (« a disparu entre la sonde et l'ouverture »). (2)
    L'ouverture SANS création, en `mode=rw` : `connecter is None` ⇒
    `connect(chemin, sans_creation=True)` de ce module (nom global : un banc le
    remplace) ; sinon `connecter(<uri file:…?mode=rw>)`, la connexion NUE de
    l'appelant (`uri=True` à sa charge, avec son `timeout`/`isolation_level`).
    Un lien PENDANT planté entre-temps fait lever SQLite au lieu d'écrire au
    bout ; sa levée est traduite en `EmplacementRefuse` qui dit ce que le nom
    désigne désormais — SAUF si l'identité relue ÉGALE la première (le nom
    désigne encore le même fichier régulier) : SQLite ne peut pas l'ouvrir
    (droits), c'est une panne d'accès, `OuvertureImpossible` (fille de
    `sqlite3.OperationalError`, pas de `ValueError`). (3) L'identité APRÈS
    ouverture, en DEUX moitiés
    témoignées séparément : `PRAGMA database_list` — lu PAR POSITION, valable
    `Row` comme tuple — doit rendre, LEXICALEMENT, le chemin créé ou vérifié
    (SQLite résout un lien de feuille vers sa cible : seule cette moitié voit un
    lien planté puis retiré pendant l'ouverture), et une seconde `ws.identite`
    doit ÉGALER la première (seule cette moitié voit une base étrangère RENOMMÉE
    sur le nom, que `database_list` rend sous le nom attendu) ; sinon la
    connexion est refermée AVANT de rendre la main.

    Ne juge PAS les annexes : chaque appelant appelle `refuser_les_liens`
    d'abord (comme `stores._sonder`) — sur un lien PENDANT, `exists` rend faux
    et un appelant qui en dépend rentrerait avant toute ouverture. Aucun
    `.stat()` ici — le banc de pureté le refuserait —, et aucun
    `os.lstat`/`os.fstat` non plus, que ce banc ne VOIT pas : l'identité vient
    de `ws`, par discipline tenue à la revue."""
    _refuser_memoire(rel)
    ident = ws.creer_fichier_exclusif(rel, mode=mode) if creer else None
    cree = ident is not None
    if ident is None:
        ident = ws.identite(rel)
        if ident is None:
            raise EmplacementRefuse(
                f"{rel} a disparu entre la sonde et l'ouverture : rien écrit, "
                f"relancez")
        _juger_la_feuille(ident)
    try:
        if connecter is None:
            conn = connect(ident.chemin, sans_creation=True)
        else:
            conn = connecter(_uri_absolue(ident.chemin, "sans création", "?mode=rw"))
    except sqlite3.OperationalError as exc:
        apres = ws.identite(rel)
        message = (
            f"SQLite refuse d'ouvrir {ident.chemin} sans le créer ({exc}) : le nom "
            f"désigne {_ce_que_le_nom_designe(ident, apres)} — "
            f"{_ce_qui_reste(cree, ident, apres)}")
        if apres == ident:
            # Emplacement INCHANGÉ (même fichier régulier, même identité) : une
            # panne d'accès, pas un refus d'emplacement.
            raise OuvertureImpossible(message) from exc
        raise EmplacementRefuse(message) from exc
    try:
        ouvert = [Path(ligne[2]) for ligne in conn.execute("PRAGMA database_list")
                  if ligne[1] == "main"]
        apres = ws.identite(rel)
        if ouvert != [ident.chemin] or apres != ident:
            moment = "création" if cree else "vérification"
            raise EmplacementRefuse(
                f"emplacement changé entre {moment} et ouverture : {ident.chemin} "
                f"attendu, SQLite a ouvert {ouvert[0] if ouvert else '?'} et le nom "
                f"désigne {_ce_que_le_nom_designe(ident, apres)}. Connexion "
                f"refermée avant toute sonde ou garantie — "
                f"{_ce_qui_reste(cree, ident, apres)}")
    except BaseException:
        conn.close()
        raise
    return conn, ident, cree
