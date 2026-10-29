"""L'entry point console `cadre`. Phase 1 de T-012.

CE QUI EXISTE AUJOURD'HUI ET CE QUI EST RÉSERVÉ. Le contrat a réservé douze noms
en Phase 0bis — `init`, `hook`, `hosts`, `doctor`, `dashboard`, `uninstall`,
`config explain`, `disarm`, plus les espaces de noms `lessons` et `remote`. En
Phase 3 s'y ajoutent trois points d'entrée adoptants, `tasks`, `ledger`, `specs`,
apportés en Phase 4. Un nom réservé qui n'est pas implémenté **le dit et sort
en 2**, avec la phase qui l'apporte. Il ne dit jamais « commande inconnue » : la
différence entre « ce nom n'existe pas » et « ce nom est pris, il arrive » est
exactement ce que le statut `reserve` promet à un adoptant. DEUX EXCEPTIONS, et
aucune ne bouge le verrou :
`cadre lessons promote` est RÉELLE et publique — elle promeut une forme
généralisée en fichier —, tandis que l'ESPACE `cadre lessons` reste réservé. Ses
autres feuilles `push`, `pull`, `list`, `review` disent encore « NOM RÉSERVÉ » et
sortent en 2, et `cadre lessons` nu rappelle l'usage de `promote` puis sort en 2.
`cadre init [--host H]` est CÂBLÉE EN PARTIE (T-00000968, premier tiers de
T-00000756) : elle crée ou monte les trois stores par `cadre.init.initialiser`,
et le DIT à chaque appel — surfaces adoptant, réglages natifs par hôte et
`kit.lock` ne sont pas posés. Le nom reste dans `RESERVEES` et `reserve` au
verrou, dont la note promet ce câblage complet : la bascule publique le suit, et
elle est portée par T-00000756 (`contract.lock.json` est dans SON write-set).
`cadre init --upgrade`, élément distinct au verrou (phase 3bis), dit encore
« NOM RÉSERVÉ » et sort en 2, AVANT toute écriture.
`cadre tasks …` est CÂBLÉE (T-00000962) : elle délègue au moteur du board du
kit (`cadre.commandes_adoptant`), arguments transmis tels quels, codes 0/1/2 de
l'interface décidée. Comme `init`, le nom RESTE dans `RESERVEES` et `reserve`
au verrou : la bascule réservé→public est portée par T-00000797.
`cadre hook <evenement> --host H` a QUITTÉ les réservés (T-00000862) : c'est le
point d'entrée des gardes. Elle lit le payload sur l'entrée standard et écrit la
`Reponse` du répartiteur pur `cadre.hook` — un refus sort par le canal de
l'hôte (stderr et 2 pour claude, enveloppe `deny` et 0 ailleurs). Sa table de
gardes est VIDE dans cette version (aucune garde n'y est encore branchée) : un
payload valide est laissé passer.

`--version`, `paths`, `config explain`, `cadre lessons promote` et `cadre hook`
sont les CINQ commandes réelles ET publiques — `config explain` est passée de
`reserve` à `public` en `66d15fd`, le jour où elle a fait quelque chose,
`cadre lessons promote` s'ajoute avec la base de leçons globale, et `cadre hook`
avec son répartiteur, dans le commit qui bascule le verrou. Le critère de
sortie de la Phase 1 est que `cadre --version` réponde en editable comme en
installé, et que les racines soient déplaçables. `paths` est ce qui rend cette
seconde moitié observable — sans elle, « les racines sont déplaçables » ne serait
qu'une affirmation.

LES CODES DE SORTIE SONT UN CONTRAT : `0` réussi, `2` refusé — nom réservé,
option inconnue, hôte hors liste, configuration illisible. `1` est réservé au cas
« la commande a répondu mais une racine manque », et il n'y a pas de traceback :
une trace Python remontée à l'adoptant est un code de sortie non déclaré et une
réponse qu'il ne peut pas lire.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from cadre import __version__
# `HOTES` et `expliquer` VIENNENT D'ICI, EN HAUT, et l'ancien « import tardif :
# la CLI reste legere » a disparu avec eux plutôt que d'être conservé à mentir.
# La liste fermée des hôtes doit être connue à la CONSTRUCTION du parseur pour
# devenir un `choices`, donc `cadre.config` est chargé de toute façon : garder
# l'import de `expliquer` dans le corps n'aurait plus rien allégé, et un
# commentaire qui affirme une propriété que le code ne tient pas empêche de voir
# le défaut. `hote_cli` est le `type=` des deux options d'hôte : il oriente un
# héritier (antigravity -> gemini) AVANT que `choices` ne refuse.
from cadre.config import HERITIERS, HOTES, expliquer, hote_cli
# Le MODULE, pas la fonction : `commandes_adoptant.cadre_tasks` est lu à l'appel.
from cadre import commandes_adoptant
# Même règle : `repartiteur.resoudre` est lu à l'appel, un banc la remplace.
from cadre import hook as repartiteur
from cadre.init import initialiser
from cadre.ledger import promotion, store
from cadre.paths import CadrePathError, agents_dir, config_home, pkg_root, project_root, state_home, state_project
from cadre.workspace import Workspace

# Le remède d'un héritier dans l'AIDE des deux options d'hôte est TIRÉ de
# `HERITIERS` (T-00000861), comme le refus de `hote_cli` : un littéral ne
# nommerait pas le prochain héritier.
_AIDE_HERITIERS = "".join(f" ({h.capitalize()} : utiliser {p})" for h, p in HERITIERS.items())

# Les commandes RÉELLES. `contract_diff` les lit à partir de la Phase 1 : une
# commande promise au verrou doit apparaître dans l'une des deux tables, et un
# nom de l'une des deux tables doit être promis au verrou.
IMPLEMENTEES = {"paths", "config", "hook"}

# Nom réservé -> phase qui l'apporte. Un nom quitte cette table pour
# `IMPLEMENTEES` le jour où il fait ce que le verrou promet, et son statut au
# verrou passe de `reserve` à `public` dans le MÊME commit — sinon le contrat
# ment, dans un sens ou dans l'autre. EXCEPTION NOMMÉE, `init` : câblé en partie
# (stores seuls, T-00000968), il RESTE ici, parce que sa note au verrou promet un
# câblage complet que ce tiers ne livre pas ; le sortir sans basculer le verrou
# ferait rougir `test_contract_diff`, le basculer ferait mentir la note. Sa
# sortie et la bascule partent ENSEMBLE avec T-00000756. Le verrou est
# réconcilié par T-00000756 : le statut `reserve` de `cadre init` au
# `contract.lock.json` y est une obligation posée par l'orchestrateur.
RESERVEES = {
    "init": "3",
    "hosts": "3",
    "doctor": "6",
    "dashboard": "5",
    "uninstall": "6",
    "disarm": "3",
    # Ici la phase qui les APPORTE (4, la wheel) ; au verrou `introduit_en: "3"`, le
    # moment de l'ÉDITION du verrou (LOT-3) — deux dates distinctes, S-00001601.
    # SECONDE EXCEPTION NOMMÉE, `tasks` : câblé (T-00000962, délégation au moteur
    # du board), il RESTE ici comme `init` ; sa sortie de la table et la bascule
    # au verrou partent ENSEMBLE avec T-00000797.
    "tasks": "4",
    "ledger": "4",
    "specs": "4",
    "lessons": "non planifiée — espace de noms réservé",
    "remote": "non planifiée — espace de noms réservé",
}


def _maintenant() -> str:
    """L'horodatage de revue, en UTC ISO 8601. LA CLI EST LA COUTURE D'E/S : c'est
    ici que vit l'horloge, jamais dans `promotion.promouvoir` (module de décision,
    qui exige l'horodatage en paramètre)."""
    return datetime.now(timezone.utc).isoformat()


def _lessons_promote(args: argparse.Namespace) -> int:
    """`cadre lessons promote <ulid> --revue-par <nom> --magasin <chemin>`.

    Le FICHIER fait foi (`spec:260-262`) : on écrit `.agents/state/lessons/<ulid>.json`
    AVANT de commiter. Si l'écriture échoue → `rollback`, rien n'a bougé ; si le
    commit échoue après le fichier → le fichier fait foi et une reconstruction
    répare (portée par un lot successeur, ce lot ne la livre pas).

    TOUS LES REFUS SORTENT EN 2, avec leur cause sur `stderr` et JAMAIS un
    traceback. Les causes forment une énumération CLOSE PAR CONSTRUCTION — ce sont
    les blocs `except` ci-dessous, SIX causes : `ValueError` (précondition de
    `promouvoir`, relecteur/horodatage vide, ou promotion concurrente — et, sixième
    cause, attrapée par le MÊME bloc sans branche neuve : un lien, un second nom
    ou un non-régulier à l'emplacement du magasin, ou un magasin disparu entre la
    garde `is_file()` et l'ouverture, refusés par `store.refuser_les_liens` /
    `store.ouvrir_sans_suivre` en `EmplacementRefuse`, fille de `ValueError` —
    TOCTOU T-00000770),
    `CadrePathError` (racine de projet hors dépôt), `OSError` (écriture du fichier
    de leçon impossible — disque plein, `.agents/` en lecture seule, chemin occupé),
    `sqlite3.IntegrityError` (`CHECK` du schéma refusé) puis `sqlite3.DatabaseError`
    (magasin illisible, absent ou non-SQLite ; et, quand c'est une `OperationalError`
    « locked »/« busy », le magasin VERROUILLÉ par un autre processus, distingué par
    `isinstance` À L'INTÉRIEUR du bloc). L'ORDRE des deux `sqlite3` est PRESCRIT et
    non prouvé : `IntegrityError` et `OperationalError` sont sœurs, filles de
    `DatabaseError`, donc la mère `DatabaseError` vient APRÈS `IntegrityError` — sans
    quoi un `CHECK` refusé serait étiqueté « magasin illisible ». `except
    sqlite3.OperationalError` SÉPARÉ reste PROSCRIT : un fichier non-SQLite lève
    `DatabaseError`, que `OperationalError` n'attrape pas — la contention est donc
    distinguée DANS le bloc `DatabaseError`. `OSError` est attrapé AVANT les
    `sqlite3` (il n'est parent d'aucune) : une faute d'écriture de FICHIER ne se
    confond pas avec une faute de MAGASIN.
    """
    try:
        # A-C5 : `sqlite3.connect` CRÉE le fichier. Un `--magasin` introuvable (une
        # faute de frappe) forgerait sinon une base de 0 octet qu'un
        # `garantir_schema` ultérieur initialiserait VIDE — la base globale
        # paraîtrait exister et ne porterait plus rien. On refuse AVANT d'ouvrir.
        if not Path(args.magasin).is_file():
            print(f"cadre lessons promote : magasin introuvable : {args.magasin}",
                  file=sys.stderr)
            return 2
        # T-00000770 : `is_file()` SUIT un lien, et le nom peut changer entre elle
        # et l'ouverture. Le magasin s'ouvre donc SANS SUIVRE ni créer : un lien, un
        # second nom, un non-régulier ou un magasin disparu lèvent `EmplacementRefuse`
        # (une `ValueError`, bloc ci-dessous) — l'ouverture par défaut reste
        # `store.connect` (`foreign_keys`, `Row`), en `mode=rw`.
        chemin_magasin = Path(args.magasin).absolute()
        atelier_magasin = Workspace(chemin_magasin.parent)
        store.refuser_les_liens(atelier_magasin, chemin_magasin.name)
        conn, _ident, _cree = store.ouvrir_sans_suivre(
            atelier_magasin, chemin_magasin.name, creer=False)
        try:
            ligne, octets = promotion.promouvoir(
                conn, args.ulid, revue_par=args.revue_par, horodatage=_maintenant())
            atelier = Workspace(project_root())
            atelier.write_bytes(".agents/state/lessons/" + ligne["ulid"] + ".json", octets)
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()
    except ValueError as exc:
        print(f"cadre lessons promote : {exc}", file=sys.stderr)
        return 2
    except CadrePathError as exc:
        print(f"cadre lessons promote : {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        # A-C1 : écriture du fichier de leçon impossible (disque plein, `.agents/`
        # en lecture seule, chemin occupé). `OSError` n'est parent d'aucune
        # exception `sqlite3`, et il est attrapé AVANT elles : une faute d'écriture
        # de FICHIER ne doit pas se confondre avec une faute de MAGASIN.
        print(f"cadre lessons promote : écriture du fichier de leçon impossible ({exc})",
              file=sys.stderr)
        return 2
    except sqlite3.IntegrityError as exc:
        print(f"cadre lessons promote : le magasin a refusé l'écriture ({exc})",
              file=sys.stderr)
        return 2
    except sqlite3.DatabaseError as exc:
        # A-C4 : la contention (`OperationalError` « locked »/« busy ») est distinguée
        # DANS ce bloc par `isinstance`, jamais par un `except OperationalError` frère
        # (qui ne couvrirait pas un fichier non-SQLite). Sur une base GLOBALE, le
        # remède « recrée le magasin » du message générique détruirait les leçons de
        # tout le monde ; la contention appelle « réessayez ».
        if isinstance(exc, sqlite3.OperationalError) and (
                "locked" in str(exc) or "busy" in str(exc)):
            print("cadre lessons promote : magasin VERROUILLÉ par un autre processus "
                  f"— rien n'a été promu, réessayez ({exc})", file=sys.stderr)
        else:
            print(f"cadre lessons promote : magasin illisible, absent ou non-SQLite ({exc})",
                  file=sys.stderr)
        return 2
    return 0


def _init(args: argparse.Namespace) -> int:
    """`cadre init [--host H]` — câblage PARTIEL (T-00000968) : les trois stores.

    `--upgrade` EST REFUSÉ EN PREMIER, avant toute résolution de racine : c'est
    un élément DISTINCT au verrou (phase 3bis), encore réservé, et il doit le
    dire sans rien écrire — `test_cadre_package` le joue depuis la racine du KIT,
    où une création de stores toucherait le vrai dépôt.

    TOUS LES REFUS SORTENT EN 2, cause sur `stderr`, JAMAIS un traceback. Trois
    blocs, une énumération close : `CadrePathError` (racine introuvable, racine
    divergente, store refusé — `creer_les_stores` traduit ses propres refus) ;
    `ValueError` (`HoteInconnu` par l'API — `type=hote_cli` puis `choices` le
    refusent avant ici —, ou `HorsRacine`) ; `OSError` (une racine que
    `Workspace` ne peut résoudre).
    `CadrePathError` dérive de `RuntimeError` : aucun des trois n'en recouvre un
    autre.

    LE SUCCÈS DIT SA PORTÉE. La sortie nomme les stores créés ou montés, puis ce
    qui n'est PAS posé : une sortie 0 muette laisserait croire qu'`init` a fait
    ce que la note du verrou promet.
    """
    if args.upgrade:
        print(
            "cadre init --upgrade : NOM RÉSERVÉ, pas encore implémenté (phase "
            "3bis). Le nom est pris au contrat et ne servira pas à autre chose ; "
            "voir docs/contrat/CONTRAT-v0.md. Rien n'a été écrit.",
            file=sys.stderr,
        )
        return 2
    try:
        faite = initialiser(hote=args.host)
    except CadrePathError as exc:
        print(f"cadre init : {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"cadre init : {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"cadre init : racine ou store inaccessible ({exc})", file=sys.stderr)
        return 2
    print(f"cadre init : stores créés ou montés sous {faite.racine}")
    print(f"  v3_event_store  {faite.stores.v3_event_store}")
    print(f"  events          {faite.stores.events}")
    print(f"  index           {faite.stores.index}")
    if faite.hote is not None:
        print(f"cadre init : hôte {faite.hote} validé ; ses réglages natifs ne sont "
              "pas posés par cette version.")
    print("cadre init : câblage PARTIEL — surfaces adoptant, réglages natifs par "
          "hôte et kit.lock non posés ; `cadre init` reste réservé au contrat.")
    return 0


def _verdict_du_hook(evenement: str, hote: str) -> repartiteur.Reponse:
    """La `Reponse` de `cadre hook` : lire l'entrée, résoudre la table, répartir.

    Chaque étape qui touche au monde est protégée, et sa faute rendue en refus
    par le canal de l'hôte — jamais un traceback, qui serait un échec OUVERT.
    """
    flux = sys.stdin
    try:
        brut = b"" if flux is None else flux.buffer.read()
    except Exception as exc:  # noqa: BLE001 — toute faute de lecture refuse
        return repartiteur.refus_d_entree(evenement, hote, exc)
    try:
        table = repartiteur.resoudre()
    except BaseException as exc:  # noqa: BLE001 — toute faute de table refuse
        return repartiteur.refus_de_table(evenement, hote, exc)
    return repartiteur.repartir(evenement, hote, brut, table)


def _hook(args: argparse.Namespace) -> int:
    """`cadre hook <evenement> --host <hote>` — LA COUTURE D'E/S du répartiteur.

    C'est ICI, et nulle part dans `cadre.hook`, que le payload est lu — les
    OCTETS bruts, `sys.stdin.buffer` : le décodage UTF-8 strict appartient au
    répartiteur, et un flux texte aurait déjà décodé, BOM et erreurs compris —
    et que la `Reponse` est écrite. Une entrée standard FERMÉE (`sys.stdin` vaut
    `None`) se lit comme un payload vide : le répartiteur le refuse par le canal
    de l'hôte, jamais un traceback. Une LECTURE qui échoue — toute `Exception` :
    `OSError`, `ValueError` d'un flux clos, `AttributeError` d'un flux sans
    `.buffer` — est refusée par le même canal, `repartiteur.refus_d_entree`
    formant la raison — le nom du type seul ; une table de production que
    `resoudre()` ne sait pas rendre (toute `BaseException`) aussi, par
    `repartiteur.refus_de_table`.
    L'hôte est déjà dans `HOTES` (`choices`), donc `HoteInconnu` ne peut pas
    remonter jusqu'ici. Une faute à l'ÉCRITURE (`BrokenPipeError`) n'est pas
    traitée : hors périmètre de T-00000862.
    """
    reponse = _verdict_du_hook(args.evenement, args.host)
    if reponse.stdout:
        sys.stdout.write(reponse.stdout)
        sys.stdout.flush()
    if reponse.stderr:
        sys.stderr.write(reponse.stderr)
        sys.stderr.flush()
    return reponse.code


def _racines() -> dict[str, str | None]:
    """Les racines résolues. `PROJECT_ROOT` peut légitimement manquer — hors
    d'un dépôt, une wheel installée reste utilisable pour tout le reste — donc
    son absence est RENDUE, jamais levée jusqu'à l'appelant.

    LE SCHÉMA EST FIXE, TOUJOURS LES SEPT CLÉS, et c'est une correction. La
    première rédaction affectait `AGENTS_DIR` APRÈS `PROJECT_ROOT` dans le même
    `try` : hors dépôt la clé n'était donc jamais posée, et `PROJECT_ROOT`
    recevait la PHRASE D'ERREUR française comme valeur, avec un code de sortie 0
    qui disait à l'appelant de la croire. C'est la seule sortie machine du
    paquet ; un `jq -r .AGENTS_DIR` qui rend `null` ou un chemin selon le
    répertoire courant n'est pas une sortie machine.
    """
    out: dict[str, str | None] = {
        "PKG_ROOT": str(pkg_root()),
        "CONFIG_HOME": str(config_home()),
        "STATE_HOME": str(state_home()),
        "PROJECT_ROOT": None,
        "AGENTS_DIR": None,
        "STATE_PROJECT": None,
        "erreur": None,
    }
    try:
        out["PROJECT_ROOT"] = str(project_root())
        out["AGENTS_DIR"] = str(agents_dir())
        out["STATE_PROJECT"] = str(state_project())
    except CadrePathError as exc:
        out["erreur"] = str(exc)
    return out


def main(argv: list[str] | None = None) -> int:
    # `cadre tasks …` est acheminée AVANT argparse : la délégation promet « mêmes
    # arguments » que le moteur, et les jetons qui suivent `tasks` partent donc
    # verbatim, sans dépendre de ce que `parse_known_args` range dans ses extras
    # — sa documentation ne le garantit pas. Mesuré de 3.11.16 à 3.14.7 sur quatre
    # formes (`--` nu, `--` après le verbe, option et valeur, `--help`) : extras
    # intacts ; l'acheminement ne corrige donc aucun défaut mesuré, il retire la
    # dépendance. Le nom garde son parseur (`add_help=False`, boucle ci-dessous)
    # pour l'aide de `cadre`.
    brut = sys.argv[1:] if argv is None else list(argv)
    if brut[:1] == ["tasks"]:
        return commandes_adoptant.cadre_tasks(brut[1:])

    p = argparse.ArgumentParser(prog="cadre", description="Le kit Cadre.")
    p.add_argument("--version", action="store_true", help="affiche la version et sort")
    sub = p.add_subparsers(dest="commande")

    pp = sub.add_parser("paths", help="affiche les racines résolues et le répertoire de contrat")
    pp.add_argument("--json", action="store_true", help="sortie machine, schéma fixe")

    pc = sub.add_parser("config", help="lire la configuration effective")
    sc = pc.add_subparsers(dest="sous")
    pe = sc.add_parser("explain", help="d'où sort la valeur d'une clé, et ce qu'elle recouvre")
    pe.add_argument("cle", help="clé pointée, par exemple `securite.seuil`")
    # `choices` PLUTÔT QU'UNE AIDE QUI ÉNUMÈRE : l'énumération était déjà écrite
    # ici et rien ne l'appliquait, donc `--hote ../../x` lisait un JSON
    # quelconque du disque comme une couche de configuration. `type=hote_cli`
    # passe AVANT `choices` (T-00000861) : un héritier y est refusé AVEC son
    # remède, tout autre nom en sort inchangé et `choices` en décide seul.
    pe.add_argument("--hote", default=None, type=hote_cli, choices=HOTES,
                    help="l'hôte dont on lit la couche : " + " | ".join(HOTES)
                    + _AIDE_HERITIERS)

    # `hook` est PUBLIC (T-00000862) : un vrai parseur, hors de `RESERVEES`, donc
    # une option en trop y fait `p.error()` comme sur toute commande réelle.
    # `evenement` reste une CHAÎNE LIBRE, jamais un `choices` : un événement
    # inconnu est un refus du RÉPARTITEUR, rendu par le canal de l'hôte
    # (S-01M54WTQTHB14SH0W0KZTHNCYB) — un `choices` le ferait sortir en 2 par
    # argparse, que les hôtes à enveloppe lisent comme un plantage. `--host` est
    # REQUIS (le canal du refus en dépend), FERMÉ par `choices` et ORIENTÉ par
    # `type=hote_cli` (patron de `config explain --hote`).
    ph = sub.add_parser("hook", help="le point d'entrée des gardes : payload JSON sur "
                        "stdin, refus par le canal de l'hôte")
    ph.add_argument("evenement", help="l'événement canonique du verrou, par exemple "
                    "`PreToolUse`")
    ph.add_argument("--host", required=True, type=hote_cli, choices=HOTES,
                    help="l'hôte qui appelle, dont le canal porte le refus : "
                    + " | ".join(HOTES) + _AIDE_HERITIERS)

    # `lessons` est un espace RÉSERVÉ dont UNE feuille est réelle (`promote`) : on
    # le construit explicitement — les frères réservés n'ont pas de parseur — et on
    # le SAUTE dans la boucle pour ne pas rejouer `add_parser` sur le même nom. Le
    # parseur `lessons` porte `add_help=False`, EXACTEMENT comme ses frères de la
    # boucle : sinon `cadre lessons --help` serait intercepté par l'action `-h`
    # d'argparse et sortirait en 0, contredisant « un nom réservé le dit et sort en
    # 2 ». `--help` devient alors un token inconnu, retombe dans `extra`, et
    # `sous_lessons` reste `None` : traité comme `cadre lessons` nu (usage + 2). Le
    # sous-parseur `promote`, lui, garde `add_help=True` : c'est une commande
    # PUBLIQUE, `--help` y est légitime.
    pl = sub.add_parser("lessons", add_help=False)
    sl = pl.add_subparsers(dest="sous_lessons")
    plp = sl.add_parser("promote", help="promeut une forme généralisée en fichier d'équipe")
    plp.add_argument("ulid", help="l'ulid de la forme généralisée à promouvoir")
    plp.add_argument("--revue-par", required=True, help="le relecteur qui a fait l'acte de revue")
    plp.add_argument("--magasin", required=True, help="le magasin de leçons à ouvrir")
    for feuille in ("push", "pull", "list", "review"):
        sl.add_parser(feuille, add_help=False)

    # `init` est RÉSERVÉ au verrou mais câblé en partie (T-00000968) : il reçoit
    # un VRAI parseur, construit ici, à sa place dans l'ordre de `RESERVEES` (juste
    # après `lessons`, comme avant), et SAUTÉ dans la boucle. `add_help` reste
    # vrai : la commande fait quelque chose, `--help` y est légitime. `--host` est
    # FERMÉ par `choices` et ORIENTÉ par `type=hote_cli` (patron de `config
    # explain --hote`) ; `--upgrade` est DÉCLARÉ pour être refusé comme réservé
    # (« RÉSERVÉ »), jamais comme option inconnue — son comportement appartient à
    # un autre élément du verrou.
    pi = sub.add_parser("init", help="crée ou monte les stores du projet (câblage partiel)")
    pi.add_argument("--host", default=None, type=hote_cli, choices=HOTES,
                    help="l'hôte à activer : " + " | ".join(HOTES)
                    + _AIDE_HERITIERS
                    + " — validé ; ses réglages natifs ne sont pas encore posés")
    pi.add_argument("--upgrade", action="store_true",
                    help="RÉSERVÉ (phase 3bis) : refusé, rien n'est écrit")

    for nom in RESERVEES:
        if nom in ("lessons", "init"):
            continue
        sub.add_parser(nom, add_help=False)

    # `parse_known_args` EST NÉCESSAIRE pour laisser passer les arguments des noms
    # RÉSERVÉS qui n'ont pas encore de parseur (`cadre hosts add codex`) —
    # `cadre init --upgrade` en a un depuis T-00000968, et
    # `cadre hook <evenement> --host H` est public depuis T-00000862. Mais il
    # avalait du même geste les fautes de frappe des commandes RÉELLES :
    # `config explain modele --hotte claude` rendait la valeur d'une AUTRE couche
    # en l'étiquetant « posee par : hote », avec un code 0. Un outil de
    # diagnostic qui répond faux et avec aplomb est pire que pas d'outil. La feuille
    # `lessons promote` étant devenue RÉELLE, une option surnuméraire sur elle doit
    # AUSSI faire `p.error()` (qui LÈVE `SystemExit(2)`), sans quoi elle serait
    # avalée comme celle d'un nom réservé. MÊME RÈGLE pour `init`, câblé en
    # partie : `cadre init --hots claude` créerait sinon les stores SANS l'hôte
    # demandé, code 0 — la réponse fausse et confiante que ce filet existe pour
    # empêcher.
    args, extra = p.parse_known_args(argv)
    if extra and (args.commande not in RESERVEES
                  or args.commande == "init"
                  or (args.commande == "lessons"
                      and getattr(args, "sous_lessons", None) == "promote")):
        p.error(f"option(s) inconnue(s) : {' '.join(extra)}")

    if args.version:
        print(__version__)
        return 0

    if args.commande == "paths":
        racines = _racines()
        if args.json:
            print(json.dumps(racines, ensure_ascii=False, indent=2))
        else:
            for cle, valeur in racines.items():
                if cle == "erreur":
                    continue
                print(f"{cle:13s} {valeur if valeur is not None else '<non résolu>'}")
            if racines["erreur"]:
                print(f"\ncadre: {racines['erreur']}", file=sys.stderr)
        return 0 if racines["erreur"] is None else 1

    if args.commande == "config":
        if args.sous != "explain":
            print("usage : cadre config explain <cle>", file=sys.stderr)
            return 2
        try:
            print(expliquer(args.cle, args.hote).rendu())
        except ValueError as exc:
            # `HoteInconnu` DÉRIVE DE `ValueError`, donc un seul filet couvre les
            # deux refus. Un `cadre.json` mal tapé dans N'IMPORTE LAQUELLE des
            # quatre couches remontait jusqu'ici en traceback, avec un code 1 que
            # le contrat ne connaît pas : l'adoptant doit VOIR son erreur, pas la
            # pile d'appels du kit.
            print(f"cadre config explain : {exc}", file=sys.stderr)
            return 2
        return 0

    # `lessons` est branché AVANT `if args.commande in RESERVEES:`, qui sinon
    # l'intercepterait et rendrait 2 avec le message générique « NOM RÉSERVÉ » —
    # faux pour sa feuille réelle `promote` et pour le rappel d'usage.
    if args.commande == "lessons":
        sous = getattr(args, "sous_lessons", None)
        if sous == "promote":
            return _lessons_promote(args)
        if sous in {"push", "pull", "list", "review"}:
            print(
                f"cadre lessons {sous} : NOM RÉSERVÉ, pas encore implémenté. Le nom "
                "est pris au contrat et ne servira pas à autre chose ; voir "
                "docs/contrat/CONTRAT-v0.md.",
                file=sys.stderr,
            )
            return 2
        # `cadre lessons` nu (ou `--help` retombé dans `extra`) : on RAPPELLE l'usage
        # de la seule feuille réelle et on sort en 2 — jamais une aide en 0.
        print(
            "usage : cadre lessons promote <ulid> --revue-par <nom> --magasin <chemin>\n"
            "les feuilles push, pull, list, review de `cadre lessons` restent réservées.",
            file=sys.stderr,
        )
        return 2

    # `init` est branché AVANT `if args.commande in RESERVEES:`, pour la même
    # raison que `lessons` : il y reste inscrit (voir la table) mais fait quelque
    # chose, et le message générique « NOM RÉSERVÉ » serait faux.
    if args.commande == "init":
        return _init(args)

    # `hook` est branché AVANT `if args.commande in RESERVEES:` : il n'y figure
    # plus, mais l'ordre garde lisible que rien de réservé ne l'intercepte.
    if args.commande == "hook":
        return _hook(args)

    if args.commande in RESERVEES:
        phase = RESERVEES[args.commande]
        print(
            f"cadre {args.commande} : NOM RÉSERVÉ, pas encore implémenté "
            f"(phase {phase}). Le nom est pris au contrat et ne servira pas à "
            "autre chose ; voir docs/contrat/CONTRAT-v0.md.",
            file=sys.stderr,
        )
        return 2

    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
