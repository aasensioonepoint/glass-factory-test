#!/usr/bin/env python3
"""Durcissement du passage par kickoff — le garde qui relie une ECRITURE a un MANDAT.

T-00000243. Conception : ``docs/design/2026-08-20-durcissement-kickoff.md``.

LE DEFAUT QU'IL FERME. Les six hotes enregistrent un ``PreToolUse Edit|Write``,
mais ce hook ne repond qu'a une question — *ce chemin est-il interdit ?* — jamais
*cette ecriture a-t-elle un mandat ?*. Le pipeline obligatoire d'``AGENTS.md``
n'etait donc que de la prose : rien ne reliait une ecriture a une tache approuvee.

POLARITE — ETEINT PAR DEFAUT, ARME PAR LA CLASSE DE LA TACHE (spec section 2,
amendee par la DECISION L du pilote, 2026-09-13). **Un depot qui n'a rien arme ne
voit strictement aucun changement de comportement** : pas un refus, pas un
avertissement, pas une ligne de journal.

CE QUE LA DECISION L A CHANGE, ET IL FAUT LE LIRE AVANT LE TABLEAU. L'armement
etait OPT-IN PAR TACHE : sur un depot livre, ce garde produisait ZERO OCTET, donc
« aucune edition avant un plan approuve » se lisait comme tenu alors qu'il ne
l'etait que la ou quelqu'un l'avait arme A LA MAIN. Desormais c'est la PRESENCE du
fichier de porte qui est l'interrupteur, et l'armement se DERIVE de la classe de
chaque tache `running` — voir ``armed_by_class``. Les ids ecrits a la main
restent lus, et s'AJOUTENT.

**UNE BRANCHE DU CONTRAT A DONC ETE RETIREE** : « porte VIDE -> passe en
silence » n'est plus vraie, parce qu'un fichier vide veut maintenant dire
« armement par classe actif, aucun ajout manuel ». La polarite qui compte pour un
ADOPTANT — fichier ABSENT -> silence total — est INTACTE, et c'est
``test_gate_absent_allows_in_silence`` qui la tient.
C'est la condition pour que le mecanisme voyage vers la branche template sans
casser le premier jour de chaque projet adoptant, et c'est epingle par un test
nomme (``test_disarmed_repo_is_byte_silent``). L'armement vit dans
``.agents/state/gates/KICKOFF_REQUIRED`` — un id de tache par ligne, ``#`` en
commentaire — que ``.agents/state/`` fait deja ``strip:``-er par
``.template-exclude``, donc le fichier de porte ne peut pas atteindre un projet
adoptant, meme par accident.

LA REGLE (spec section 4, amendee par C5). Sur une ecriture de chemin ``P`` :

===================================================== =========================
situation                                             ce qui se passe
===================================================== =========================
porte ABSENTE (ou illisible au point d'etre muette)   passe, en silence
porte presente, aucune tache `running` que la classe  passe, en silence
  arme et aucun id ecrit
``P`` couvert par le writeset d'aucune tache armee    passe, en silence
tache `running` sans writeset declare                 REFUS — declare-le
tache `running` a writeset > 5 chemins exacts         ARMEE par sa CLASSE
tache `running` a writeset portant un glob/repertoire ARMEE, fail-closed
tache `running` a chemin de garde, estampillee        ARMEE, quel que soit le compte
  `direct` ou non
tache `running` a writeset de 5 chemins exacts ou -   NON armee : triviale
tache armee couvrante, ``running`` + plan dans SPECS  passe
tache armee couvrante qui n'est pas ``running``       REFUS — kickoff d'abord
tache armee couvrante sans ``kind=plan`` dans SPECS   REFUS — pas de plan
tache conforme ETRANGERE a la fournee focalisee       REFUS — ``foreign-running``
  (``focus.json`` present)
tache conforme, ``focus.json`` illisible              REFUS — ``focus-unreadable``
  ou ``task_id`` vide
tache conforme, SANS ``focus.json``, running de       REFUS — ``focus-missing``
  PLUSIEURS familles au board
===================================================== =========================

LE FOCUS DU CLONE (T-01M5F728WZ89DF8PV79SDWEFE4, lot F de T-01M5DBFPWC). Plusieurs
taches peuvent etre ``running`` a la fois (une par session, une session par clone) :
sans borne, le ``running`` d'un COLLEGUE couvrirait les ecritures de CE clone. Quand
``focus.json`` existe (lu par ``tasks.lire_focus`` sous le depot PRINCIPAL, trouve
sur le disque par ``tasks.racine_principale`` — aucun sous-processus, repli sur la
racine hors Git), seules les taches de la FOURNEE FOCALISEE donnent mandat : le
focus, son parent de fournee s'il est un lot, et les lots de ce parent. SANS
``focus.json``, l'ancienne regle ne vaut que pour UNE SEULE famille de ``running``.
La borne est la condition meme de ``familles_running`` : UNE famille si RACINE
UNIQUE (toutes les running ont la meme racine — parent de fournee d'un lot, sinon
son id) OU GROUPE UNANIME NON VIDE (toutes portent le meme ``parallel_group``, et
il n'est pas vide) ; sinon, autant de familles que de racines. Cette condition
contient les boards que le code d'avant le focus savait lire
(``running_group_refusal``, 7407b2fee : plusieurs running seulement dans UN groupe
declare) et y ajoute une seule fournee dont un lot a perdu ou change de groupe, que
7407b2fee refusait en entier. Des running de PLUSIEURS familles sans focus :
personne ne sait a quelle session appartient l'ecriture, la couverture conforme est
refusee sous ``focus-missing`` (remede ``tasks.py focus <T>``). Le focus ne fait
QUE retirer des mandats : il n'en ajoute aucun, ne desarme rien et ne change
aucun autre refus.

La sixieme ligne de la spec — « hors perimetre declare » — a ete **SUPPRIMEE**
(amendement C5) : elle est inatteignable par construction, puisque la COUVERTURE
*est* l'appartenance au writeset. Un message de refus qu'aucune entree ne peut
produire est une promesse creuse.

Quand PLUSIEURS taches armees couvrent le meme chemin, l'ecriture passe s'il en
existe **au moins une** conforme ; sinon elle est refusee et le refus nomme
chacune des taches couvrantes avec la condition qui lui manque.

NON-VACUITE. Armer une tache sans writeset declare est REFUSE, jamais admis :
sans cette regle on armerait une garde qui ne garde rien. Le refus est prononce
au RELEVE, a chaque ecriture, pas a l'ecriture du fichier de porte — ce fichier
est ecrit a la main par le pilote, donc rien ne garantit qu'un writeset existait
a ce moment-la. Une tache armee sans writeset fait refuser TOUTES les ecritures
du depot (gel a l'echelle du depot, dit plutot que cache), et le refus nomme la
reparation.

LA BRANCHE STRICTE SUR L'IMPOSSIBLE, ET ELLE A DEUX COTES. ``tasks.py`` porte
deja « une preuve impossible vaut comme un chevauchement ».

* **Cote ENTREES de writeset** : un chemin de writeset inadmissible compte comme
  COUVRANT, donc mene au refus. L'admissibilite est exigee de CHAQUE entree
  (amendement C4) — une entree admissible ne sauve pas un writeset qui en porte
  aussi une inadmissible.
* **Cote CHEMIN ECRIT** : un chemin ecrit qu'on ne sait pas etablir compte comme
  COUVRANT lui aussi, et mene au refus (``path-not-establishable``).

**Ce second cote a d'abord manque, et c'etait une ASYMETRIE plutot qu'un oubli
mineur — corrige apres un constat de securite classe 1 (HIGH, non waivable).**
``relative_to_root`` ne normalisait que les chemins ABSOLUS, par effet de bord
de ``resolve()``. Un chemin RELATIF gardait son ``..`` litteral, donc
``src/other/../allowed/secret.py`` se comparait segment par segment contre
``src/allowed`` sans jamais correspondre : ``decide()`` concluait « aucune tache
armee ne couvre ce chemin -> passe, en silence », alors que l'ecriture
atterrissait REELLEMENT dans le perimetre protege et que le mandat (``running``
+ ``kind=plan``) n'etait JAMAIS verifie. La meme regle — un ``..`` rend la
preuve impossible — donnait le REFUS d'un cote et le PASSAGE SILENCIEUX de
l'autre. Le cas relatif etait le plus probable en pratique : ``apply_patch``
(``*** Add File: <path>``) et les champs ``target_file`` / ``path`` des autres
hotes transportent des chemins relatifs. Le correctif a deux moities —
normalisation LEXICALE (jamais un ``resolve()`` sur du relatif, qui toucherait
le disque et dependrait du cwd) ET branche stricte en PLUS, jamais a la place.

CE QUI RESTE DECOUVERT, DIT PLUTOT QUE CACHE.

* **Les ecritures par le shell contournent le garde** (``sed -i``, ``> fichier``,
  ``tee``, ``python -c``, ``git checkout --``). C'est exactement le trou deja
  nomme dans ``AGENTS.md`` pour ``safe-bash``. La tache **T-00000244** le porte.
* **LE PLAFOND, ECRIT PLUTOT QUE TU.** Les trois conditions sont ECRIVABLES par
  l'agent contraint lui-meme, via un ``Bash`` que ce garde ne hooke jamais :
  ``tasks.py start``, ``tasks.py writeset``, ``specs.py add --kind plan``. Le
  garde **RENCHERIT LE COUT** d'une ecriture sans mandat ; il ne la rend pas
  impossible. Rien dans cette tache ne releve ce plafond. Une option a ete
  chiffree puis DIFFEREE en **T-00000246** : une ligne ``T-NNN sha256=<plan>``
  dans le fichier de porte, sur le patron prouve par ``/night``, ferait passer la
  falsification de « lancer les outils normaux » a « forger une ligne dans un
  fichier du pilote ». Differee parce qu'elle change le format d'un fichier que
  le pilote ecrit A LA MAIN, et parce qu'elle ne ferme pas le plafond Bash.
* **Writesets DECLARES, jamais ecritures OBSERVEES** — meme honnetete que
  ``tasks.py parallel``. Un writeset menteur donne un garde menteur.

COUVERTURE ANNONCEE : **3 hotes mesures, 0 herite, 1 suppose, 2 inertes-mesures** — jamais « six
hotes couverts ». Voir ``_HOST_EXIT_CONTRACT`` plus bas pour le tableau et pour
la legende qui dit ce que « mesure » veut dire exactement ici.

Le module est un LECTEUR du board et du journal, et n'ecrit rien (hors la ligne
d'audit ``hook.deny``, fail-open absolu). Ce n'est pas une sous-commande de
``tasks.py`` : greffer une lecture de ``SPECS.json`` sur l'outil qui possede le
board melangerait deux proprietaires de store (spec section 5).
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import specs  # noqa: E402  (same-directory sibling, after the path insertion)
import tasks  # noqa: E402

# events.py is OPTIONAL to this guard and loaded with the same fail-open posture
# as .codex/hooks/_common.emit_event(): a telemetry line may never decide whether
# an edit is allowed, nor crash the hook.
try:  # pragma: no cover - exercised by test_event_channel_broken_still_refuses
    import events as _events  # noqa: E402
except Exception:  # pragma: no cover
    _events = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# L'ARMEMENT
# ---------------------------------------------------------------------------

GATE_RELPATH = Path(".agents") / "state" / "gates" / "KICKOFF_REQUIRED"

#: Le repertoire ``.agents/state/gates/`` est deja le domicile etabli des « le
#: pilote a explicitement autorise » : ``NIGHT_HEADLESS.allow``, ``AUDIT_LOG``,
#: ``MCP_ALLOWLIST.md``. Aucune convention nouvelle a retenir.
GATE_DISPLAY = GATE_RELPATH.as_posix()


def repo_root() -> Path:
    """La racine du depot, DEPUIS L'EMPLACEMENT DE CE FICHIER — ``parents[2]``.

    ``.agents/bin/kickoff_guard.py`` -> ``parents[2]`` est la racine, a la
    profondeur du kit comme a celle du vendoring. Deliberement pas ``cwd`` (un
    hook tourne depuis n'importe ou) et deliberement PAS ``git rev-parse``
    (amendement C8) : ce garde tire sur CHAQUE ecriture, et faire tourner un
    sous-processus avant le court-circuit « rien n'est arme » couterait un fork
    par edition sur un depot qui n'a rien demande.
    """
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class GateReading:
    """Ce que la porte dit — et si elle a pu etre lue du tout."""

    present: bool
    ids: tuple[str, ...] = ()
    error: str = ""


def read_gate(root: str | os.PathLike[str]) -> GateReading:
    """Lit le fichier de porte. AUCUN sous-processus, aucune lecture de store.

    Trois issues, et la premiere est celle qui garantit la polarite :

    * fichier ABSENT -> ``present=False`` : le depot n'a rien arme, l'appelant
      sort 0 sans ecrire un octet.
    * fichier PRESENT et lisible -> les ids, commentaires et lignes vides otes.
    * fichier PRESENT et ILLISIBLE -> ``error`` : la porte EXISTE, donc le depot
      a arme quelque chose, donc la branche stricte s'applique. Un garde qui ne
      peut pas etablir son perimetre refuse ; il ne rassure pas.
    """
    path = Path(root) / GATE_RELPATH
    try:
        if not path.exists():
            return GateReading(present=False)
    except OSError as exc:  # pragma: no cover - pathological FS
        return GateReading(present=True, error=f"{GATE_DISPLAY} cannot be stat'ed: {exc}")
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return GateReading(present=True, error=f"{GATE_DISPLAY} cannot be read: {exc}")
    ids: list[str] = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if line and line not in ids:
            ids.append(line)
    return GateReading(present=True, ids=tuple(ids))


# ---------------------------------------------------------------------------
# LE PREDICAT DE COUVERTURE — DIRECTIONNEL, ET LOCAL A CE MODULE
# ---------------------------------------------------------------------------


def writeset_covers(entry: str, path: str) -> bool:
    """L'entree de writeset ``entry`` COUVRE-T-ELLE le chemin ecrit ``path`` ?

    ``tasks.writeset_paths_overlap`` existe mais est **SYMETRIQUE** : elle
    signale un chevauchement si l'un des deux chemins prefixe l'autre. Le garde
    a besoin d'une containment **DIRECTIONNELLE** — les segments de l'entree de
    writeset prefixent-ils ceux du chemin ecrit. D'ou ce predicat, LOCAL a ce
    module (``tasks.py`` est hors du writeset de la tache qui l'ecrit) ; il
    reutilise ``canonical_writeset_path`` et le test de prefixe **A LA FRONTIERE
    DE SEGMENT**, ce qui est exactement ce qui rend ``src/a`` et ``src/ab``
    disjoints tout en faisant couvrir ``src/a/b.py`` par ``src/a/``.

    Un test de prefixe au niveau de la CHAINE fusionnerait la premiere paire —
    c'est la faute que le predicat de ``tasks.py`` a paye six tours de critique.

    Il ne pretend jamais que deux formes canoniques egales nomment un fichier :
    c'est precisement ce qu'une preuve textuelle ne peut pas dire.
    """
    entry_segments = _segments(entry)
    path_segments = _written_segments(path)
    if not entry_segments or not path_segments:
        return False
    if len(entry_segments) > len(path_segments):
        return False
    return path_segments[: len(entry_segments)] == entry_segments


def _segments(value: str) -> list[str]:
    """Les segments canoniques d'une ENTREE de writeset."""
    canonical = tasks.canonical_writeset_path(value)
    return canonical.split("/") if canonical else []


def _written_segments(value: str) -> list[str]:
    """Les segments canoniques d'un CHEMIN ECRIT — normalise d'abord.

    Le cote ecrit passe par ``normalise_relative`` avant la canonicalisation,
    pour que ``src/other/../allowed/x.py`` compare comme ``src/allowed/x.py``.
    Idempotent : ``relative_to_root`` a deja normalise, refaire ne change rien,
    et un appelant direct du predicat ne peut pas reintroduire le defaut.
    """
    return _segments(normalise_relative(value))


#: Les segments qu'une normalisation LEXICALE ne peut pas resoudre : seul un
#: ``..`` de tete survit a ``normalise_relative``, et il signifie que le chemin
#: sort AU-DESSUS de la racine.
UNESTABLISHABLE_SEGMENTS = frozenset({".", ".."})


def normalise_relative(value: str) -> str:
    """Replie ``\\`` -> ``/``, puis ``.`` et ``..``, **PUREMENT LEXICALEMENT**.

    PAS de ``resolve()`` sur du relatif : cela toucherait le disque et
    dependrait du cwd, alors qu'un hook tourne depuis n'importe ou. La preuve
    reste TEXTUELLE, comme celle de ``tasks.py``.

    Un ``..`` qui n'a plus rien a depiler est CONSERVE plutot qu'absorbe : c'est
    ce qui rend visible, en aval, un chemin qui s'echappe au-dessus de la racine
    — ``written_path_refusal`` le refuse au lieu de le laisser passer.

    Les segments vides sont ecartes (``src//a`` nomme ``src/a``). L'asymetrie
    avec la clause ``non-empty-segment`` que ``tasks.py`` applique aux ENTREES
    est deliberee et va dans le bon sens : une entree est une DECLARATION que le
    pilote peut corriger, un chemin ecrit est un FAIT a etablir — et ecarter les
    vides ELARGIT la couverture, jamais l'inverse.
    """
    out: list[str] = []
    for segment in (value or "").replace("\\", "/").split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            if out and out[-1] != "..":
                out.pop()
            else:
                out.append("..")
            continue
        out.append(segment)
    return "/".join(out)


def written_path_refusal(path: str) -> str | None:
    """``None`` quand le chemin ecrit est ETABLI, sinon le DIAGNOSTIC.

    LA BRANCHE STRICTE, cote chemin ecrit — la moitie qui manquait, et qui est
    la SYMETRIQUE de celle que le module applique deja aux entrees de writeset.
    Cote entrees, ``tasks.writeset_path_refusal`` refuse ``.`` et ``..`` et une
    entree inadmissible compte comme COUVRANTE, donc mene au refus. Cote chemin
    ecrit, un ``..`` produisait exactement l'effet INVERSE — non-couverture,
    donc passage silencieux — alors que l'ecriture atterrissait reellement dans
    le perimetre protege. **La meme regle doit valoir dans les deux sens.**

    Apres ``normalise_relative``, seul un ``..`` de tete peut subsister : le
    chemin sort au-dessus de la racine, donc le garde ne peut pas l'etablir. Un
    garde qui ne peut pas etablir le chemin REFUSE ; il ne rassure pas.

    A NE PAS CONFONDRE avec un chemin ABSOLU hors du depot, que
    ``relative_to_root`` rend comme ``""`` : celui-la est ETABLI, et etabli
    dehors, donc aucun writeset relatif ne peut le couvrir et il passe.
    """
    if not path:
        return None
    segments = normalise_relative(path).split("/")
    offending = [s for s in segments if s in UNESTABLISHABLE_SEGMENTS]
    if offending:
        return (
            f"{path!r} still carries a {offending[0]!r} segment after lexical "
            f"normalisation, so it escapes above the repository root and this guard "
            f"cannot establish WHERE it lands"
        )
    return None


def relative_to_root(root: str | os.PathLike[str], value: str) -> str:
    """Le chemin ecrit, ramene a une forme relative au depot, separateurs ``/``.

    Un writeset est relatif par construction (clause ``non-empty-segment`` de
    ``tasks.writeset_path_refusal`` refuse un chemin absolu), donc un chemin
    ABSOLU qu'on ne sait pas ramener sous la racine n'est couvert par rien et
    passe — il est etabli, et etabli dehors.

    UN CHEMIN RELATIF EST NORMALISE LEXICALEMENT, et cette ligne est le coeur du
    correctif de securite : sans elle, seul le cas absolu etait defendu, et
    seulement PAR EFFET DE BORD de ``resolve()``. Le cas relatif est pourtant le
    plus probable en pratique — ``apply_patch`` (``*** Add File: <path>``) et les
    champs ``target_file`` / ``path`` des autres hotes transportent des chemins
    relatifs.

    Aucune resolution de lien : la preuve reste TEXTUELLE, comme celle de
    ``tasks.py`` — liens symboliques, jonctions Windows, alias 8.3 et liens durs
    sont hors de sa portee, et c'est ecrit plutot que masque.
    """
    text = (value or "").replace("\\", "/").strip()
    if not text:
        return ""
    candidate = Path(text)
    if candidate.is_absolute():
        try:
            return candidate.resolve(strict=False).relative_to(Path(root).resolve()).as_posix()
        except (ValueError, OSError):
            return ""
    return normalise_relative(text)


# ---------------------------------------------------------------------------
# LA DECISION — PURE, SANS ENTREE/SORTIE
# ---------------------------------------------------------------------------

#: Vocabulaire CLOS des regles de refus, en ORDRE D'EVALUATION. Un refus nomme
#: toujours l'une d'elles : un garde qui bloque sans nommer sa clause bloque son
#: propre diagnostic (meme discipline que ``tasks.WRITESET_CLAUSES``).
REFUSAL_RULES = (
    "gate-unreadable",
    "path-not-establishable",
    "board-unreadable",
    "journal-unreadable",
    "armed-unknown-task",
    "armed-without-writeset",
    "armed-writeset-inadmissible",
    "not-running",
    "no-plan",
    "foreign-running",
    "focus-unreadable",
    "focus-missing",
    "kickoff-required",
)

#: La route de desarmement, citee dans CHAQUE refus. Elle doit etre ATTEIGNABLE
#: par celui qui lit le refus, sinon le garde bloque son propre diagnostic (C6,
#: C14) : editer le fichier de porte passe par ``Edit``, que ``protect-paths``
#: refuse — donc la route nommee est celle du PILOTE, a la main, hors agent.
DISARM_HINT = (
    f"To disarm: remove the task id from {GATE_DISPLAY} (a human edit — agents are "
    f"denied Edit/Write on that path by protect-paths)."
)


@dataclass(frozen=True)
class Decision:
    """``allowed`` decide ; ``rule`` et ``reason`` ne valent que sur un refus."""

    allowed: bool
    rule: str = ""
    reason: str = ""

    @property
    def refused(self) -> bool:
        return not self.allowed


ALLOW = Decision(allowed=True)


@dataclass(frozen=True)
class BoardReading:
    """Le board tel que le garde a pu le lire — ou l'echec de cette lecture.

    ``focus`` : l'id de ``focus.json`` (``""`` = fichier ABSENT) ; ``focus_error`` :
    le fichier existe mais ne se lit pas — jamais un focus devine."""

    tasks_by_id: dict[str, dict[str, Any]] = field(default_factory=dict)
    error: str = ""
    focus: str = ""
    focus_error: str = ""


@dataclass(frozen=True)
class JournalReading:
    """Les taches portant au moins une entree ``kind=plan`` dans SPECS.json."""

    planned: frozenset[str] = frozenset()
    error: str = ""


#: Seuil de CLASSE, LU et jamais réécrit (T-00001178, S-00004135) : c'est la
#: constante UNIQUE de la voie directe, `tasks.MAX_FICHIERS_DIRECT` — 5 chemins
#: exacts ou moins passent sans plan, le plan est requis à partir de 6. Une
#: seconde valeur écrite ici dériverait de la première sans qu'un banc le voie.
SEUIL_CLASSE = tasks.MAX_FICHIERS_DIRECT


def armed_by_class(board: BoardReading) -> tuple[str, ...]:
    """Les tâches `running` que leur CLASSE arme, sans geste humain.

    DÉCISION PILOTE L DU 2026-09-13, option 3 sur trois. Avant elle, l'armement
    était OPT-IN PAR TÂCHE : sur un dépôt livré, ce garde produisait ZÉRO OCTET
    sur chaque édition, donc « aucune édition avant un plan approuvé » se lisait
    comme tenu alors qu'il ne l'était que là où quelqu'un l'avait armé à la main.

    QUATRE BRANCHES ; les trois premières viennent d'une MESURE, la quatrième
    d'une objection de critique de plan (R5-2), pas d'une intuition :

    * **aucun write-set déclaré → ARMÉE.** La tâche n'a pas de classe, donc on
      ne peut pas dire qu'elle est triviale. Elle couvre alors TOUT et le refus
      existant ``armed-without-writeset`` nomme le remède, qui est une seule
      commande. Relevé du 2026-09-13 : 187 des 215 tâches `pending` sont dans ce
      cas — ce n'est PAS un coût mais un HÉRITAGE, ces tâches étant antérieures
      à l'obligation, et le pilote a tranché que « à chaque prise de tâche sans
      write-set, la tâche la crée ». Déclarer fait partie du geste de PRISE.
    * **write-set en chemins exacts, plus de SEUIL_CLASSE → ARMÉE.** C'est le
      seuil de la voie directe, lu dans ``tasks.MAX_FICHIERS_DIRECT``.
    * **write-set portant un glob ou un répertoire → ARMÉE, fail-closed.** Un
      glob veut dire « je ne sais pas combien » : mesuré, ``src/cadre/**`` vaut
      8 fichiers quand ``docs/tasks/**`` en vaut 216, et cette portée BOUGE. Sans
      cette branche, déclarer ``**`` deviendrait LA façon d'échapper au plan —
      une garde contournable d'un seul caractère.
    * **tâche dont un chemin est un chemin de garde → ARMÉE, quel que soit son
      compte, ESTAMPILLÉE OU NON** (T-00001178, R5-2 ; binôme ter, décision (a)
      de S-00004190) : aucune estampille ``direct`` n'exempte, même celle dont
      l'instantané couvre le write-set courant — la liste de garde GRANDIT, et
      un instantané validé hier peut porter un chemin de garde d'aujourd'hui.
      La liste est celle de la voie directe, lue par
      ``tasks.est_chemin_de_garde`` — jamais dupliquée ici : une petite tâche
      qui touche une garde n'est pas triviale.

    ET RIEN D'AUTRE N'EST ARMÉ : une tâche de cinq fichiers ou moins, hors
    garde, passe sans plan, ce qui est exactement ce que l'option 3 existait
    pour protéger.

    **SEULES LES TÂCHES `running` SONT CONCERNÉES.** Armer une tâche `pending`
    la ferait refuser sous ``not-running``, c'est-à-dire bloquer le dépôt entier
    au nom d'une tâche que personne n'a prise — un refus que son lecteur ne
    pourrait pas relier à son geste.

    LA POLARITÉ N'EST PAS TOUCHÉE : cette fonction ne s'applique que si le
    fichier de porte EXISTE. Un adoptant qui ne l'a pas ne voit toujours rien.
    """
    armees: list[str] = []
    for tid, task in sorted(board.tasks_by_id.items()):
        if task.get("state") != "running":
            continue
        writeset = tasks.writeset_of(task)
        if not writeset:
            armees.append(tid)
            continue
        if any("*" in e or str(e).endswith("/") for e in writeset):
            armees.append(tid)
            continue
        # UN CHEMIN DE GARDE ARME, ESTAMPILLÉE OU NON : aucune exemption par
        # l'instantané de `direct` (la liste de garde grandit après l'estampille).
        if any(tasks.est_chemin_de_garde(e) for e in writeset):
            armees.append(tid)
            continue
        if len(writeset) > SEUIL_CLASSE:
            armees.append(tid)
    return tuple(armees)


def fournee_du_focus(board: BoardReading) -> frozenset[str]:
    """Les taches qui peuvent donner mandat a CE clone quand ``focus.json`` existe.

    Le focus lui-meme ; s'il est un LOT (lien ``fournee`` = {parent, lot}), son
    parent ; puis chaque lot de ce parent, retrouve par le lien que la fournee
    pose (``tasks.fournee_lots_existants``, jamais une seconde copie de la regle).
    Rien d'autre : un ``running`` hors de cet ensemble est celui d'une autre
    session. Pure, aucune lecture de fichier."""
    lien = (board.tasks_by_id.get(board.focus) or {}).get("fournee")
    parent = board.focus
    if isinstance(lien, dict) and isinstance(lien.get("parent"), str) and isinstance(lien.get("lot"), str):
        parent = lien["parent"]
    lots = tasks.fournee_lots_existants({"tasks": list(board.tasks_by_id.values())}, parent)
    return frozenset({board.focus, parent, *(t["id"] for t in lots.values())})


def familles_running(board: BoardReading) -> int:
    """Le nombre de FAMILLES parmi les taches ``running`` du board. Racine d'une
    tache : le parent de sa fournee si elle est un lot, sinon son id. UNE famille
    si toutes les running ont la meme racine, OU si toutes portent le meme
    ``parallel_group`` non vide ; sinon, le nombre de racines. JAMAIS d'union
    transitive : un lot regroupe avec une tache etrangere (``tasks.py parallel``)
    ne doit pas relier deux groupes qu'aucune declaration ne lie. Pure."""
    racines: set[str] = set()
    groupes: set[str] = set()
    for tid, task in board.tasks_by_id.items():
        if task.get("state") != "running":
            continue
        lien = task.get("fournee")
        racine = tid
        if isinstance(lien, dict) and isinstance(lien.get("parent"), str) and isinstance(lien.get("lot"), str):
            racine = lien["parent"]
        racines.add(racine)
        groupes.add(tasks.parallel_group_of(task))
    if len(racines) <= 1 or (len(groupes) == 1 and "" not in groupes):
        return 1
    return len(racines)


def decide(
    path: str,
    gate: GateReading,
    board: BoardReading,
    journal: JournalReading,
) -> Decision:
    """La regle, PURE : aucune lecture de fichier, aucun sous-processus.

    ``path`` est deja relatif au depot (cf. ``relative_to_root``). Toutes les
    entrees viennent des trois lectures faites par ``collect()``, ce qui rend la
    regle testable sans hote, sans board et sans journal.
    """
    if not gate.present:
        # LA POLARITE. Rien n'est arme : pas un refus, pas un avertissement,
        # pas une ligne de journal.
        return ALLOW
    if gate.error:
        return Decision(
            False,
            "gate-unreadable",
            f"kickoff guard: {gate.error}. The gate file EXISTS, so this repository "
            f"armed something, and a guard that cannot establish its perimeter refuses "
            f"rather than reassures. {DISARM_HINT}",
        )
    # L'ARMEMENT EFFECTIF = CE QUE LE PILOTE A ÉCRIT, PLUS CE QUE LA CLASSE ARME
    # (décision L). L'ordre préserve la priorité du fichier, et `dict.fromkeys`
    # dédoublonne sans changer l'ordre — une tâche armée des DEUX façons ne doit
    # pas produire deux entrées, sinon les refus la nomment deux fois.
    #
    # SI LE BOARD EST ILLISIBLE, `armed_by_class` rend un tuple VIDE : on retombe
    # alors exactement sur `gate.ids`, donc sur le comportement d'avant cette
    # décision. C'est voulu — on n'invente pas un armement à partir d'une lecture
    # ratée, et la branche `board-unreadable` ci-dessous garde son sens.
    ids_effectifs = tuple(dict.fromkeys(gate.ids + armed_by_class(board)))
    if not ids_effectifs:
        # Fichier vide, ou ne portant que des commentaires, ET aucune tâche
        # `running` que sa classe arme : rien n'est ouvert.
        return ALLOW

    # LA BRANCHE STRICTE COTE CHEMIN ECRIT, symetrique de celle qui s'applique
    # deja aux entrees de writeset. Placee AVANT la boucle de couverture, parce
    # qu'un chemin qu'on ne sait pas etablir ne peut pas etre declare « couvert
    # par aucune tache armee » — c'est precisement cette conclusion-la qui
    # laissait passer une traversee. Placee APRES les portes de polarite, donc
    # un depot desarme ne la voit jamais.
    path_refusal = written_path_refusal(path)
    if path_refusal is not None:
        return Decision(
            False,
            "path-not-establishable",
            f"BLOCKED by kickoff guard: {path_refusal}. A guard that cannot establish "
            f"the path REFUSES rather than reassures — the same strict branch this "
            f"module already applies to an inadmissible writeset entry. Write the path "
            f"without '..' segments. {DISARM_HINT}",
        )

    if board.error:
        return Decision(
            False,
            "board-unreadable",
            f"kickoff guard: {len(ids_effectifs)} task(s) armed in {GATE_DISPLAY}, but the "
            f"board cannot be read — {board.error}. Repair with "
            # T-00001058 : le dossier ENTIER, fichiers d'intent non suivis compris — un `git restore`
            # du seul TASKS.json laisserait des intents orphelins (décision pilote).
            f"`git stash push -u -- .agents/state/board/`, or {DISARM_HINT}",
        )
    if journal.error:
        return Decision(
            False,
            "journal-unreadable",
            f"kickoff guard: {len(ids_effectifs)} task(s) armed in {GATE_DISPLAY}, but the "
            f"journal cannot be read — {journal.error}. Repair with "
            # T-01M4KKMY43ZKCW1YD2Y8JX9MKH : le DOSSIER — le journal `SPECS.jsonl` ou le monolithe, selon la forme.
            f"`git restore .agents/state/specs/`, or {DISARM_HINT}",
        )

    # LE FOCUS NE FAIT QUE RETIRER DES MANDATS (lot F) : calcule une fois, consulte
    # seulement au point ou une tache conforme donnerait le passage.
    famille = fournee_du_focus(board) if board.focus else frozenset()
    sans_focus_ambigu = not board.focus and not board.focus_error and familles_running(board) > 1
    covering: list[tuple[str, str, str]] = []  # (task id, rule, why)
    for tid in ids_effectifs:
        task = board.tasks_by_id.get(tid)
        if task is None:
            # NON-VACUITE, cas limite : un id que le board ne connait pas n'a par
            # construction aucun writeset, donc il COUVRE TOUT. Nomme, jamais
            # silencieux (spec section 8).
            covering.append(
                (
                    tid,
                    "armed-unknown-task",
                    f"{tid} is armed but the board carries no such task, so no perimeter "
                    f"can be established for it and every write is refused",
                )
            )
            continue
        writeset = tasks.writeset_of(task)
        if not writeset:
            # NON-VACUITE. Le gel est A L'ECHELLE DU DEPOT, et le remede est
            # ATTEIGNABLE : `tasks.py writeset` passe par Bash, que ce garde ne
            # hooke jamais.
            covering.append(
                (
                    tid,
                    "armed-without-writeset",
                    f"{tid} is armed with NO declared writeset, so it covers nothing and "
                    f"would guard nothing — every write in the repository is refused "
                    f"instead. Declare it with `python .agents/bin/tasks.py writeset {tid} "
                    f"<paths...>`, or {DISARM_HINT}",
                )
            )
            continue
        inadmissible = [e for e in writeset if tasks.writeset_path_refusal(e) is not None]
        if inadmissible:
            # LA BRANCHE STRICTE SUR L'IMPOSSIBLE, dans son sens. L'admissibilite
            # est exigee de CHAQUE entree (C4) : une entree admissible ne sauve
            # pas un writeset qui en porte aussi une inadmissible.
            covering.append(
                (
                    tid,
                    "armed-writeset-inadmissible",
                    f"{tid} carries an inadmissible writeset entry ({inadmissible[0]!r}) — "
                    f"{tasks.writeset_path_refusal(inadmissible[0])} An impossible proof "
                    f"COUNTS AS COVERING, so every write is refused until the entry is "
                    f"rewritten with `python .agents/bin/tasks.py writeset {tid} <paths...>`",
                )
            )
            continue
        if not any(writeset_covers(entry, path) for entry in writeset):
            continue
        state = task.get("state", "")
        if state != "running":
            covering.append(
                (
                    tid,
                    "not-running",
                    f"{tid} covers this path but is {state!r}, not 'running' — go through "
                    f"kickoff first (`python .agents/bin/tasks.py start {tid}`)",
                )
            )
            continue
        if tid not in journal.planned:
            covering.append(
                (
                    tid,
                    "no-plan",
                    f"{tid} covers this path and is running, but carries NO kind=plan entry "
                    f"in SPECS.json — no approved plan snapshot, no mandate",
                )
            )
            continue
        if board.focus_error:
            # Le focus EXISTE mais ne se lit pas : le perimetre du clone n'est pas
            # etabli, donc refus — le remede passe par Bash, jamais par ce garde.
            covering.append(
                (
                    tid,
                    "focus-unreadable",
                    f"{tid} covers this path, is running and planned, but this clone's focus "
                    f"cannot be read — {board.focus_error}. Rewrite it with "
                    f"`python .agents/bin/tasks.py focus <running task>`",
                )
            )
            continue
        if sans_focus_ambigu:
            # PLUSIEURS FAMILLES EN VOL, AUCUN FOCUS : la couverture ne peut pas etre
            # rattachee a CE clone — refus, jamais l'ancienne regle « au moins une ».
            covering.append(
                (
                    tid,
                    "focus-missing",
                    f"{tid} covers this path, is running and planned, but running tasks of "
                    f"{familles_running(board)} different families are on the board and this "
                    f"clone has NO focus — nothing ties this write to one session. Set it "
                    f"with `python .agents/bin/tasks.py focus <T>` (here: "
                    f"`python .agents/bin/tasks.py focus {tid}` if this session works on {tid})",
                )
            )
            continue
        if board.focus and tid not in famille:
            # UN RUNNING ETRANGER NE COUVRE PAS : c'est le mandat d'une autre session.
            covering.append(
                (
                    tid,
                    "foreign-running",
                    f"{tid} covers this path, is running and planned, but is FOREIGN to this "
                    f"clone's focused fournée ({', '.join(sorted(famille))}) — another "
                    f"session's mandate never covers this clone's writes. If this session "
                    f"works on {tid}: `python .agents/bin/tasks.py focus {tid}`",
                )
            )
            continue
        # AU MOINS UNE tache couvrante satisfait les conditions -> l'ecriture
        # passe. Le quantificateur est un CHOIX : exiger que TOUTES les taches
        # couvrantes soient conformes rendrait impossible d'armer deux taches aux
        # perimetres imbriques, ce que rien n'interdit.
        return ALLOW

    if not covering:
        # Aucune tache armee ne couvre ce chemin : passe, en silence.
        return ALLOW

    rules = {rule for _, rule, _ in covering}
    # La regle rapportee a la piste d'audit est celle des taches couvrantes SI
    # ELLES S'ACCORDENT ; sinon l'agregat `kickoff-required`, parce qu'une ligne
    # d'audit porte un seul motif et qu'en choisir un arbitrairement parmi
    # plusieurs serait un fait invente. La PROSE, elle, les nomme toutes.
    rule = rules.pop() if len(rules) == 1 else "kickoff-required"
    detail = "; ".join(why for _, _, why in covering)
    return Decision(
        False,
        rule,
        f"BLOCKED by kickoff guard: {path!r} is covered by armed task(s) "
        f"{', '.join(tid for tid, _, _ in covering)} and none of them satisfies the three "
        f"conditions (running + kind=plan snapshot in SPECS + path in the declared "
        f"writeset, within this clone's focused fournée when a focus is set). "
        f"{detail}. {DISARM_HINT}",
    )


def collect(root: str | os.PathLike[str], gate: GateReading) -> tuple[BoardReading, JournalReading]:
    """Les deux lectures de store — faites SEULEMENT sur le chemin arme.

    Court-circuit deliberé : sur un depot DESARME — fichier de porte ABSENT, ou
    illisible — ni le board ni le journal ne sont ouverts, donc le garde ne coute
    rien du tout a un depot qui n'a rien demande. C'est la polarite, et elle est
    intacte.

    CE QUI A CHANGE AVEC LA DECISION L, et c'etait un DEFAUT de son premier jet :
    le court-circuit portait aussi sur ``not gate.ids``, donc un fichier de porte
    PRESENT mais VIDE n'ouvrait pas le board — et ``armed_by_class`` recevait
    alors un board vide, ce qui rendait l'armement par classe INERTE sur
    exactement les depots ou il devait mordre. La semantique annoncee etait « la
    PRESENCE du fichier est l'interrupteur » ; elle ne l'etait pas. Une porte
    presente ouvre donc desormais le board, meme sans aucun id ecrit.
    """
    if not gate.present or gate.error:
        return BoardReading(), JournalReading()
    try:
        data = tasks.load(root)
        by_id = {t["id"]: t for t in data.get("tasks", []) if isinstance(t, dict) and t.get("id")}
        # LE FOCUS, APRES LE COURT-CIRCUIT : un depot desarme ne l'ouvre jamais.
        # `lire_focus` le cherche sous le depot PRINCIPAL par `racine_principale`,
        # qui lit `.git` sur le disque (aucun fork) et retombe sur `root` hors Git.
        focus, focus_error = "", ""
        try:
            lu = tasks.lire_focus(root)
            focus = lu["task_id"].strip() if lu else ""
            if lu is not None and not focus:
                # PRESENT mais vide : jamais lu comme ABSENT (fail-open), refuse.
                focus_error = "focus.json: task_id vide"
        except Exception as exc:
            focus_error = str(exc) or type(exc).__name__
        board = BoardReading(tasks_by_id=by_id, focus=focus, focus_error=focus_error)
    except Exception as exc:
        board = BoardReading(error=str(exc))
    try:
        entries = specs.load(root).get("entries", [])
        planned = frozenset(
            e["task"] for e in entries if isinstance(e, dict) and e.get("kind") == "plan"
        )
        journal = JournalReading(planned=planned)
    except Exception as exc:
        journal = JournalReading(error=str(exc))
    return board, journal


# ---------------------------------------------------------------------------
# LE FILTRE DE FORME D'ECRITURE (C2, C11, C18, C22)
# ---------------------------------------------------------------------------
#
# POURQUOI CE FILTRE EXISTE. Copilot's `preToolUse` takes NO matcher, so a hook
# registered there fires on EVERY tool — a READ included. A guard that refuses an
# action it has no mandate over is exactly the defect this filter closes: it is
# the guard itself that bounds the matcher-less registration.

#: Noms d'outils d'ECRITURE PURE, replies (minuscules, ``-`` -> ``_``). Le
#: repliement n'ELARGIT que l'ensemble d'ecriture et ne peut donc pas faire
#: passer une ecriture pour une lecture.
#:
#: ``create`` EST L'OUTIL D'ECRITURE DE COPILOT CLI, RELEVE SUR UNE CHARGE REELLE
#: (canari P1, Copilot CLI 1.0.95, 2026-10-12 : ``toolName: "create"``,
#: ``toolArgs: {path, file_text}``, ``path`` absolu). Sans lui, ``main()``
#: sortait a rc 0 AVANT la porte sur chaque ecriture Copilot et le refus a la
#: racine n'etait jamais atteint (delta S-01M4RWVN2K). ``create`` EST RECONNU
#: SOUS TOUS LES HOTES, pas seulement sous Copilot : cet ensemble est PLAT et
#: ``is_write_form`` ignore le marqueur d'hote. Elargissement vers le refus
#: seulement (depot arme, outil nomme exactement ``create``, qu'aucun autre hote
#: mesure n'emet) ; le « identique a l'octet hors Copilot » ne vaut donc que pour
#: les charges qui ne sont pas ``create`` (exec-critic du delta L1). Epingle :
#: ``test_hook_envelope_by_host.py::test_kickoff_charge_reelle_create_refusee_a_la_racine``,
#: la charge P1 rejouee STATIQUEMENT dans le module — le kickoff n'a JAMAIS ete
#: rejoue au runtime sous Copilot.
#:
#: LES CINQ AUTRES GRAPHIES COPILOT (``create_file``, ``insert_edit_into_file``,
#: ``replace_string_in_file``, ``edit_file``, et ``str_replace_editor`` traite
#: plus bas) viennent de la DOCUMENTATION des outils : leur exactitude n'est
#: **PAS MESUREE ICI**. Une graphie fausse rend le garde silencieusement inerte
#: chez Copilot — dit plutot que cache.
WRITE_TOOL_NAMES = frozenset(
    {
        # Claude Code / Codex / Gemini
        "edit",
        "multiedit",
        "write",
        "notebookedit",
        "apply_patch",
        "applypatch",
        # Copilot CLI : MESURE sur charge reelle (P1, 2026-10-12)
        "create",
        # Copilot (documentation, non mesure sur ce depot)
        "create_file",
        "insert_edit_into_file",
        "replace_string_in_file",
        "edit_file",
    }
)

#: ``str_replace_editor`` est un outil **MULTIPLEXE** : sa sous-commande ``view``
#: est une LECTURE. Le cler sur son NOM NU ferait refuser une lecture legitime la
#: ou la graphie est juste — exactement le defaut sans-mandat que le filtre
#: existe pour eviter. Il passe donc au marqueur de PAYLOAD (champ ``command``),
#: meme discipline que celle deja appliquee a ``apply_patch``.
MULTIPLEXED_WRITE_TOOLS: dict[str, frozenset[str]] = {
    "str_replace_editor": frozenset({"create", "str_replace", "insert", "undo_edit"}),
}

#: LE DEFAUT NOMME (C22), parce qu'un defaut NON NOMME dans un garde est
#: exactement la facon dont un trou arrive : **``str_replace_editor`` sans champ
#: ``command``, ou avec une sous-commande INCONNUE, PASSE.** La liste ci-dessus
#: est POSITIVE et close, donc tout ce qu'elle ne nomme pas tombe du cote
#: « laisser passer ». C'est la BONNE POLARITE et c'est un choix, pas un oubli :
#: refuser sur une sous-commande illisible recreerait le defaut sans-mandat que
#: C2 et C18 ont ferme — le garde refuserait une action dont il ne sait pas
#: qu'elle ecrit. Le prix est ecrit : une future sous-commande d'ecriture,
#: ajoutee en amont et pas ici, echappe au garde jusqu'a ce qu'on l'ajoute.
UNKNOWN_SUBCOMMAND_PASSES = True

#: Marqueurs de payload ``apply_patch`` : quand ils sont la, la forme est une
#: ecriture quel que soit le nom de l'outil.
APPLY_PATCH_MARKERS = ("*** Add File:", "*** Update File:", "*** Delete File:")


def fold_tool_name(raw: Any) -> str:
    """Le nom d'outil replie — minuscules, espaces otes, ``-`` -> ``_``."""
    return str(raw or "").strip().lower().replace("-", "_")


def tool_name(payload: dict[str, Any]) -> str:
    """Le nom d'outil, dans les quatre graphies que les hotes emettent — meme
    liste et meme ordre que ``.codex/hooks/_common.tool_name``."""
    for key in ("toolName", "tool_name", "tool", "name"):
        value = payload.get(key)
        if value:
            return str(value)
    return ""


def tool_args(payload: dict[str, Any]) -> dict[str, Any]:
    """Les arguments d'outil — meme liste et meme ordre que
    ``.codex/hooks/_common.tool_args``, y compris la forme chaine."""
    args: Any = None
    for key in ("toolArgs", "tool_args", "toolInput", "tool_input", "input", "arguments"):
        if payload.get(key):
            args = payload[key]
            break
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            return {"command": args, "raw": args}
    return args if isinstance(args, dict) else {}


def is_write_form(payload: dict[str, Any]) -> bool:
    """La forme de l'appel est-elle une ECRITURE de fichier ?

    Trois portes, dans cet ordre : le nom replie appartient a l'ensemble
    d'ecriture pure ; le payload porte un marqueur ``apply_patch`` ; l'outil est
    multiplexe ET sa sous-commande est une sous-commande d'ecriture connue. Tout
    le reste PASSE — voir ``UNKNOWN_SUBCOMMAND_PASSES``.
    """
    name = fold_tool_name(tool_name(payload))
    if name in WRITE_TOOL_NAMES:
        return True
    args = tool_args(payload)
    for candidate in (args.get("command"), args.get("patch"), args.get("input"),
                      args.get("raw"), payload.get("_raw")):
        if isinstance(candidate, str) and any(m in candidate for m in APPLY_PATCH_MARKERS):
            return True
    subcommands = MULTIPLEXED_WRITE_TOOLS.get(name)
    if subcommands is not None:
        command = args.get("command")
        if isinstance(command, str) and command.strip().lower() in subcommands:
            return True
        # C22, NOMME : champ absent ou sous-commande inconnue -> PASSE.
        return False
    return False


def paths_from_payload(payload: dict[str, Any]) -> list[str]:
    """Les chemins que l'appel veut ecrire — meme jeu de cles, dans le meme
    ordre, que ``.codex/hooks/_common.paths_from_payload``, sans la
    normalisation absolue (faite ici par ``relative_to_root``, qui a besoin de
    la racine). ``filePath`` est la graphie du harness Local de VS Code
    (T-01M4RWCAGQZKYQ9JS4C1JPBFVQ, S-01M4RWM3TC4JWE5FDC8YB819Z4)."""
    args = tool_args(payload)
    values: list[Any] = []
    for key in ("file_path", "filePath", "path", "target_file", "target", "filename"):
        if args.get(key):
            values.append(args[key])
    for candidate in (args.get("command"), args.get("patch"), args.get("input"),
                      args.get("raw"), payload.get("_raw")):
        if not isinstance(candidate, str):
            continue
        for line in candidate.splitlines():
            for marker in APPLY_PATCH_MARKERS:
                if line.startswith(marker):
                    values.append(line[len(marker):].strip())
    out: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in out:
            out.append(text)
    return out


# ---------------------------------------------------------------------------
# LE CONTRAT DE SORTIE, PAR HOTE (C3, C10, C17)
# ---------------------------------------------------------------------------
#
# CE QUI A ETE MESURE, ET CE QUI NE L'A PAS ETE — la legende d'abord, aux mots du
# pilote, pour qu'aucune cellule du tableau ne se lise « l'hote bloque, c'est
# connu » :
#
#   « ce qui est mesure est ce que les hooks EMETTENT, jamais ce que l'hote en
#     FAIT ; si l'enveloppe est indicative quelque part, protect-paths y est
#     fail-open depuis T-00000031 et ce garde herite du trou — pas pire que la
#     base livree, pas meilleur. »
#
# ============ ================================= ==========================
# hote         canal de refus                    statut
# ============ ================================= ==========================
# Claude Code  stderr + exit 2                   MESURE de bout en bout
# Codex        enveloppe `deny` + exit 0         MESURE (protect_paths.py:154-167)
# Copilot      enveloppe `deny` RACINE +         MESURE (P1v, 2026-10-12 : refus
#              imbriquee + exit 0                honore, `denied`) ; L-006 est
#                                                REFUTEE (l'imbriquee seule est
#                                                ignoree, P1) ; l'outil `create`
#                                                est RECONNU (charge reelle P1
#                                                rejouee STATIQUEMENT dans le
#                                                module ; le kickoff n'a jamais
#                                                ete rejoue au runtime sous
#                                                Copilot) ; autres graphies NON
#                                                MESUREES
# Gemini CLI   enveloppe `deny` + exit 0         INERTE-MESURE (G0/G1 : le registre
#                                                `.agents/hooks.json` n'est pas lu,
#                                                `permissionDecision` inconnu de
#                                                l'hote)
# Antigravity  enveloppe `deny` + exit 0         INERTE-MESURE — sa charge porte
#                                                `toolCall`, que ni tool_name ni
#                                                tool_args ne lisent : jamais une
#                                                ecriture (mesure sur le module,
#                                                2026-10-12 ; hote jamais lance)
# Kimi Code    2 canaux + exit 2 (fallback)      SUPPOSE — .kimi-code/hooks.json
#                                                cable .codex/hooks, mais aucun run
#                                                CLI kimi ne prouve le declenchement
#                                                ni l'honneur d'AGENTS_HOOK_HOST=kimi
#                                                (T-00000395) ; HORS ENVELOPE_HOSTS,
#                                                tombe au fallback marqueur-inconnu
#                                                (risque fail-open runtime)
# ============ ================================= ==========================
#
# Soit **3 mesures, 0 herite, 1 suppose, 2 inertes-mesures**. Jamais « six hotes couverts ».
#
# POURQUOI EXIT 0 SUR TROIS HOTES, ET POURQUOI CE N'EST PAS UN ECHEC-OUVERT PAR
# CONCEPTION. AUCUN hook Codex/Copilot/Gemini de ce depot n'a JAMAIS sorti un
# code non nul — zero `sys.exit` dans tout `.codex/hooks/`. Le seul canal que ces
# hotes aient jamais execute est l'enveloppe `permissionDecision: deny` a rc 0
# implicite. Un hook a rc 2 pourrait donc s'y lire comme un PLANTAGE et echouer
# OUVERT. Copier le contrat mesure de chaque hote est donc le choix strict, pas
# le laxiste.

_HOST_ENV = "AGENTS_HOOK_HOST"

#: Les hotes dont le canal de refus MESURE est l'enveloppe a rc 0. La cle morte
#: `antigravity` a ete SUPPRIMEE : Antigravity execute `.agents/hooks.json`, donc
#: arrive etiquete `gemini` — aucun enregistrement specifique n'existe.
ENVELOPE_HOSTS = frozenset({"codex", "copilot", "gemini"})

#: Le seul hote dont le canal de refus MESURE est stderr + code de sortie.
STDERR_HOSTS = frozenset({"claude"})

EXIT_ALLOW = 0
EXIT_BLOCK = 2


def host_marker(environ: dict[str, str] | None = None) -> str:
    """Le marqueur d'hote, replie ; ``""`` quand il est absent ou inconnu."""
    env = os.environ if environ is None else environ
    value = (env.get(_HOST_ENV) or "").strip().lower()
    return value if value in (ENVELOPE_HOSTS | STDERR_HOSTS) else ""


def deny_envelope(reason: str, host: str = "") -> str:
    """L'enveloppe de refus, **A LA LETTRE** de ``.codex/hooks/_common.deny``.

    PARITE CITEE, pas approchee — ``_common.deny`` :

        obj = {"hookSpecificOutput": {"hookEventName": event_name,
               "permissionDecision": "deny", "permissionDecisionReason": reason}}
        if _copilot():
            obj["permissionDecision"] = "deny"
            obj["permissionDecisionReason"] = reason

    et `emit()` serialise avec ``separators=(",", ":")``. Sous ``copilot``
    (T-01M4RWC0DBM6XC1PDQGEG4P79C), la decision est AJOUTEE au premier niveau,
    apres l'imbriquee, dans le meme ordre de cles ; tout autre ``host`` (vide
    compris) garde l'imbriquee seule, a l'octet. Deux epingles INDEPENDANTES
    portent ces literaux, sous codex ET sous copilot :
    ``test_deny_envelope_literal`` (le texte exact, ici) et
    ``test_deny_envelope_matches_common_py`` (charge ``_common.py`` PAR CHEMIN
    et compare les deux sorties). Une modification COORDONNEE de `_common.deny`
    et de sa seule epingle laisserait cette copie perimee et VERTE ; c'est la
    seconde epingle qui l'empeche.
    """
    body: dict[str, Any] = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    if host == "copilot":
        body["permissionDecision"] = "deny"
        body["permissionDecisionReason"] = reason
    return json.dumps(body, separators=(",", ":"))


def emit_refusal(
    decision: Decision,
    host: str,
    out: Any = None,
    err: Any = None,
) -> int:
    """Ecrit le refus dans le canal de l'hote et rend le code de sortie.

    * ``claude`` -> stderr + exit 2 (contrat mesure de bout en bout).
    * ``codex`` / ``copilot`` / ``gemini`` -> enveloppe sur stdout + **exit 0**,
      le seul canal que ces hotes aient jamais execute ; l'hote est passe a
      ``deny_envelope``, qui ajoute la decision de premier niveau sous
      ``copilot`` seulement (T-01M4RWC0DBM6XC1PDQGEG4P79C).
    * marqueur ABSENT ou INCONNU -> **LES DEUX** canaux, puis exit 2. Ce defaut
      ne gouverne plus que les invocations manuelles et les provisionnements
      anterieurs a ce changement : apres le cablage de T-00000243, aucun chemin
      ENREGISTRE n'y tombe (epingle par ``test_every_registration_sets_host``).
      Un projet provisionne AVANT ce changement ne porte de toute facon aucun
      enregistrement invoquant ce module, donc le garde n'y tourne pas du tout.
    """
    out = sys.stdout if out is None else out
    err = sys.stderr if err is None else err
    if host in STDERR_HOSTS:
        print(decision.reason, file=err)
        return EXIT_BLOCK
    if host in ENVELOPE_HOSTS:
        print(deny_envelope(decision.reason, host), file=out)
        return EXIT_ALLOW
    print(deny_envelope(decision.reason), file=out)
    print(decision.reason, file=err)
    return EXIT_BLOCK


def _emit_event(decision: Decision, path: str) -> None:
    """``hook.deny{guard,rule,path}`` — meme kind, memes champs, meme ordre que
    l'homologue ``protect-paths``. FAIL-OPEN ABSOLU : une ligne de telemetrie ne
    decide jamais d'une ecriture et ne change jamais un code de sortie. La PROSE
    du refus n'est jamais envoyee : elle n'a pas sa place dans une ligne lue par
    une machine."""
    if _events is None:
        return
    try:
        _events.emit("hook.deny", guard="kickoff", rule=decision.rule, path=path)
    except (Exception, SystemExit):
        return


def main(argv: list[str] | None = None) -> int:
    """Lit le payload sur stdin, decide, ecrit dans le canal de l'hote.

    L'ORDRE EST LA GARANTIE DE POLARITE : le filtre de forme (aucune E/S) puis le
    stat de la porte (aucun sous-processus) precedent toute lecture de store. Un
    depot desarme sort 0 sans avoir ouvert le board, le journal, ni un fork.
    """
    del argv
    try:
        raw = sys.stdin.read()
    except Exception:
        # « stdin illisible ne doit jamais coincer un tour » : sans payload il n'y
        # a pas de forme d'ecriture etablie, donc rien a garder.
        return EXIT_ALLOW
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {"_raw": raw}
    if not isinstance(payload, dict):
        return EXIT_ALLOW

    if not is_write_form(payload):
        return EXIT_ALLOW

    root = repo_root()
    gate = read_gate(root)
    if not gate.present:
        return EXIT_ALLOW

    host = host_marker()
    try:
        board, journal = collect(root, gate)
        written = paths_from_payload(payload)
        for raw_path in written:
            path = relative_to_root(root, raw_path)
            if not path:
                continue
            decision = decide(path, gate, board, journal)
            if decision.refused:
                _emit_event(decision, path)
                return emit_refusal(decision, host)
        if not written:
            # Aucune cible lisible sur une forme d'ecriture ARMEE : la branche
            # stricte s'applique au releve, pas a l'intention.
            decision = decide("", gate, board, journal)
            if decision.refused and decision.rule in (
                "gate-unreadable",
                "board-unreadable",
                "journal-unreadable",
                "armed-unknown-task",
                "armed-without-writeset",
                "armed-writeset-inadmissible",
            ):
                _emit_event(decision, "")
                return emit_refusal(decision, host)
    except Exception as exc:  # pragma: no cover - filet, jamais un chemin nominal
        decision = Decision(
            False,
            "gate-unreadable",
            f"kickoff guard failed while reading its own inputs ({exc}). The gate file "
            f"exists, so the strict branch applies. {DISARM_HINT}",
        )
        _emit_event(decision, "")
        return emit_refusal(decision, host)
    return EXIT_ALLOW


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
