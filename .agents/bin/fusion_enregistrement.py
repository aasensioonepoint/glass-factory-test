"""Pilote de fusion git PAR CHAMP « cadre-enregistrement » (T-01M4JN4ZSWAX5MGSGQNPPYZG68, E-26).

Fusionne À TROIS VOIES, champ par champ, UN fichier d'enveloppe canonique des magasins « un fichier par
enregistrement » — `board/tasks/*.json`, `board/epics/*.json`, `memory/entries/*.json` : `{format, id, record[,
sync_operations]}`, indent 2, clés triées, UTF-8 brut, LF. Un champ changé d'un seul côté est pris ; le même champ
changé des deux côtés vers deux valeurs est un CONFLIT. Deux règles nommées : `record.updated` (deux dates AAAA-MM-JJ)
→ la plus récente ; `sync_operations` (trois listes d'ids distincts) → fusion d'ensemble à trois voies. Les GROUPES
COUPLÉS (`COUPLES` : aujourd'hui `depends_on` + `depends_motif`) sont jugés chacun comme UNE valeur — leurs champs
changés chacun d'un côté conflictent, voulu. Une tombe (`record: null`) contre un `record` modifié conflicte. Les
ACTEURS `start_actor` et `stage_actor` sont des ATOMES jugés avant la descente : deux acteurs distincts conflictent,
`start_actor` sous le nom « double démarrage », message caviardé (`ACTEURS`). La PROPRIÉTÉ (`start_actor`) et son
intention Jira (tout champ `jira_claim_*`), avec les prises levées par sa reprise (`reprise_levee`), forment UN
ensemble (`cles_propriete`) : changé des deux côtés, conflit.

Tout conflit (même champ, groupe couplé, tombe contre modification, ids différents) est un REFUS, et un refus rend
TOUJOURS un conflit, code 3, jamais 0 ni 4 : %A reçoit la fusion TEXTE de git (`git merge-file --diff-algorithm=
histogram`, labels de git, style de conflit de l'utilisateur), avec ses marqueurs quand les lignes changées se
touchent ; quand elles ne se touchent pas, merge-file rend 0, %A porte sa fusion SANS marqueur et le chemin reste en
conflit — là où git sans pilote aurait fusionné ; quand merge-file ÉCHOUE (rc au-delà de 127, délai, lancement
impossible), %A est remis à « nous ». stderr dit chacun des deux cas. Une entrée que le pilote ne sait pas juger (hors
forme canonique, plus de 1 Mio, JSON invalide, NaN, imbrication profonde, `format` autre que l'entier 1, base vide
hors import Jira) rend la même fusion texte, CODE COMPRIS (0 si elle est propre). Une base VIDE (ajout/ajout) entre
deux imports d'un MÊME ticket Jira est remplacée par l'enregistrement d'import (`base_import_jira`) : la liste fermée
`CHAMPS_JIRA` doit concorder et l'opération d'import être des deux côtés, sinon conflit nommé.
Quand git sans pilote conflicte aussi, c'est le même conflit, à une BORNE MESURÉE près (au plus 0,5 % des
conflits aléatoires mesurés diffèrent par la découpe des blocs de marqueurs) — jamais une promesse d'identité à
l'octet. Codes : 0 = fusion écrite ; 3 = conflit écrit dans %A (avec marqueurs ; sur un refus, aussi la fusion texte
sans marqueur, ou « nous ») ; jamais 1 ; 4 = fusion texte en échec HORS refus, que la commande rejoue ; tout autre
code (2, usage) = rien d'écrit dans %A.

INDEX (`merge=cadre-index`, T-01M5X9143QVEGWMBYANB6MB4TD) : `--index %O %A %B %P` garde « nous » ; `INDEX_DELTA.json`
y prend `max_sym_id` = max(O, A, B) et DIT sur stderr les ids alloués des deux côtés ; les `:: but` des `SYMBOLS*.md`
et les cellules Role/Owner de `CODEBASE_INDEX.md` que « eux » a écrits sont REPORTÉS sur la même clé à identité égale,
sinon (identité autre, clé absente, changée des deux côtés) rc 4 : %A intact, la fusion texte de git. L'index reste à
reconstruire après la fusion (`build_index.py --if-stale`).

Usage :
  pilote git (posé par --installer) : <python> -I -B <copie> %O %A %B %L %S %X %Y
  pilote de l'index (posé par --installer) : <python> -I -B <copie> --index %O %A %B %P
  python3 .agents/bin/fusion_enregistrement.py --installer [--depuis <ref>]
      geste du PILOTE, depuis un terminal, une fois par clone : sonde git (≥ 2.44 requis, par trois sondes de
      capacité), copie le pilote lu d'un COMMIT sous <git-common-dir>/cadre/ (0o400), écrit quatre clés de config
      LOCALE (board puis index, `.driver` avant `.name`). Hors de la branche par défaut : --depuis <ref>.
  python3 .agents/bin/fusion_enregistrement.py --verifier
      lecture seule : installé / absent / périmé / altérée / forme inconnue, contre le pilote de HEAD ; la ligne
      `index : …` est imprimée AVANT la dernière et n'entre pas dans le rc.

Sans --installer, git garde sa fusion texte, en silence. La commande armée porte son PROPRE repli : pilote absent,
cassé, ou interpréteur absent ⇒ la fusion texte de git : marqueurs si les lignes se touchent, sinon fusion propre
(rc 0). Un pilote qui TOURNE n'y renvoie jamais un refus (code 3). Stdlib seule (la copie tourne sous -I, hors de
l'arbre).
"""

import contextlib
import datetime
import hashlib
import json
import os
import re
import shlex
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

PLAFOND = 1 << 20  # 1 Mio par côté ; au-delà, repli texte
CHEMIN_SUIVI = ".agents/bin/fusion_enregistrement.py"
NOM_PILOTE = "cadre-enregistrement"
CLE_NOM = f"merge.{NOM_PILOTE}.name"
CLE_DRIVER = f"merge.{NOM_PILOTE}.driver"
LIBELLE = "fusion par champ (cadre)"
NOM_INDEX = "cadre-index"
CLE_INDEX_NOM = f"merge.{NOM_INDEX}.name"
CLE_INDEX_DRIVER = f"merge.{NOM_INDEX}.driver"
LIBELLE_INDEX = "fusion de l'index (cadre)"
DIVERGENCE = "fusion par champ : le fichier du worktree diffère de la copie installée"
_PREFIXE_COPIE = "fusion_enregistrement-"
_DELAI = 120
# Les variables qui feraient viser à git un AUTRE dépôt que celui de la racine (C8) : retirées de l'environnement de
# tout sous-processus de --installer / --verifier ; chaque appel passe en plus par `git -C <toplevel>`.
_GIT_LIEU = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY",
             "GIT_ALTERNATE_OBJECT_DIRECTORIES")
# CHAMPS COUPLÉS (C4, D2) — table CLOSE, (parent, champs). RÈGLE DE CLASSE : tout ensemble de champs qu'un prédicat
# de `load` (ou de `save`) lit ENSEMBLE dans UN enregistrement, et qui n'est pas une conjonction de prédicats à un
# champ, est un groupe ici. Un groupe est un ATOME : le résultat est toujours le tuple d'UN côté, donc la part
# intra-enregistrement de l'invariant tient si elle tenait de ce côté. L'inter-fichiers reste à `load`.
COUPLES: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    # Source : `_valider_board` (tasks_stockage.py) — `depends_motif` ⊆ `depends_on`.
    (("record",), ("depends_on", "depends_motif")),
    # RETIRÉ (T-01M5F728B4CS1ZDZTH9YWJ0AZ1, C42) : le couple `(parallel_group, state)` avait pour seule source
    # `running_group_refusal`, retiré du `load` et du `save` (plusieurs `running` sont légitimes) ; plus aucun
    # prédicat de `load`/`save` ne lit ces deux champs ENSEMBLE (`_valider_board` juge le TYPE de
    # `parallel_group` seul) : chacun se fusionne comme un champ simple.
)
# LES ACTEURS SONT DES ATOMES (T-01M5DBFK3XKKM2VHQM5RE4TP6K, lot C). `start_actor` et `stage_actor`
# (`{auteur: {nom, email}, copie}`, posés par `tasks_etats.py`) se comparent ENTIERS, AVANT toute descente dans
# `record` : changés des deux côtés vers deux valeurs ⇒ conflit, même quand `stage` et `state` sont égaux ; jamais
# l'auteur d'un côté avec la copie de l'autre (la chimère). L'ordre de la table est celui du diagnostic : un double
# démarrage est nommé même quand `stage` conflicte aussi. `stage` et `stage_actor` forment en plus un COUPLE
# (`STAGE_SIGNE`, la règle de `tasks_etats.poser_acteur_stage` : l'acteur signe le stage qu'il a écrit) : un stage
# repris d'un côté sous la signature de l'autre conflicte. Hors de `COUPLES` : deux stages différents
# gardent `record/stage` tant que `stage_actor` n'a pas changé des deux côtés ; signés par deux acteurs, ils
# sortent sous `record/stage_actor`. Un %O VIDE (le fichier né des deux côtés) n'est pas une
# « base vide » au sens de cette règle : il reste une entrée hors forme, repli texte, rc 3 sans ce diagnostic —
# SAUF entre deux imports d'un même ticket Jira, où la base synthétique (`base_import_jira`) n'a aucun acteur.
ACTEURS: tuple[tuple[str, str], ...] = (
    ("start_actor", "double démarrage"),
    ("stage_actor", "stage signé par deux acteurs"),
)
STAGE_SIGNE = ("stage", "stage_actor")
# LA PROPRIÉTÉ ET SON INTENTION JIRA SONT UN ENSEMBLE (T-01M5G7RTQ9RY3WGZ8T9W6ZX9RS, lot D ; décision pilote
# S-01M5HH8QMC4E7SYN4K6AP2SMKE). `start_actor` est le pilote courant ; les champs `jira_claim_*` sont l'intention de
# son label (posée par `tasks_jira.jira_prepare_claim`, acquittée par `jira_claim_retry`, qui relit label et acteur
# ENSEMBLE). Champ par champ, un transfert d'un côté et l'accusé de l'ancien pilote de l'autre donneraient le label
# du nouveau marqué acquitté sans aucun PUT — l'intention panachée. Le groupe se lit au PRÉFIXE : un champ
# `jira_claim_` ajouté plus tard y entre sans retouche. Changé des deux côtés vers deux valeurs ⇒ `ConflitActeur`
# (%A remis à « nous » sur une fusion texte propre), jugé APRÈS les `ACTEURS` (un double démarrage reste nommé tel) ;
# changé d'un seul côté, la descente champ par champ le prend déjà ENTIER de ce côté, sans table de plus.
PROPRIETE = "start_actor"
PREFIXE_INTENTION = "jira_claim_"
#: Les prises levées par la reprise qui a posé ce `start_actor` (`tasks_etats.set_state`) : du même ensemble —
#: le pilote d'un côté et la levée d'une autre reprise de l'autre feraient avertir une prise jamais levée.
REPRISE_LEVEE = "reprise_levee"
#: Caviardage du message de conflit (stdlib seule : la copie tourne sous -I, hors de l'arbre, sans le module de
#: rédaction des écrivains). BORNES, dans les deux sens : tout jeton de 20 caractères ou plus de l'alphabet des clés
#: devient `[caviardé]`, y compris un NOM légitime sans espace de 20 caractères ou plus (masqué en entier) ; un secret
#: de moins de 20 caractères, ou coupé par un point, une espace ou un caractère non ASCII, passe EN CLAIR. Caviardé
#: PUIS plafonné par champ, le marqueur des écrivains (`tasks.ACTEUR_MARQUE`).
_JETON_SECRET = re.compile(r"[A-Za-z0-9+/=_-]{20,}", re.ASCII)
ACTEUR_PLAFOND = 100
ACTEUR_MARQUE = "...<truncated>"
_DATE = re.compile(r"\A[0-9]{4}-[0-9]{2}-[0-9]{2}\Z", re.ASCII)
_SHA = re.compile(r"\A(?:[0-9a-f]{40}|[0-9a-f]{64})\Z", re.ASCII)
_COURT = re.compile(r"\A[0-9a-f]{4,64}\Z", re.ASCII)
# La sonde des labels (étape 4 (h)) : un pilote `printf` qui écrit `%S|%X|%Y` développés dans @SORTIE@, puis rend 1.
_GABARIT_SONDE = 'printf "%%s|%%s|%%s" %S %X %Y > @SORTIE@; exit 1'
#: La branche « eux » de la sonde des labels : un nom HOSTILE (apostrophe, `;`, `$`, accolades — valide pour git), relu
#: OCTET POUR OCTET par `_labels_lus` (avis sécurité de la fusion, passe de correction F5) : un git qui ne citerait pas
#: `%Y` le découperait ou l'exécuterait, la capacité serait dite absente — jamais armée.
_BRANCHE_SONDE = "b';touch${IFS}PWNSONDE;'"
#: Un temporaire `.copie-*` de `_poser_copie` plus vieux que ce délai est l'orphelin d'un arrêt (SIGKILL) : retiré.
_AGE_ORPHELIN = 600
CAP_HISTOGRAM = "merge-file --diff-algorithm=histogram"
CAP_LABELS = "%S %X %Y"
CAP_CHEMINS = "--path-format"
_ABSENT = object()


class Conflit(Exception):
    """Le même champ (ou le même groupe couplé) changé des deux côtés : la fusion par champ décline."""


class ConflitActeur(Conflit):
    """Un refus des ACTEURS (`_juger_acteurs`) : sa fusion texte ne reste dans %A que si elle porte des marqueurs ;
    propre, elle pourrait figer la chimère refusée (auteur d'un côté, copie de l'autre) — %A est remis à « nous »."""


class HorsForme(Exception):
    """Une entrée que le pilote ne sait pas juger : repli texte, jamais une exception vers git."""


class Refus(Exception):
    """Un refus NOMMÉ de --installer / --verifier : rien n'est écrit."""


# ---------------------------------------------------------------- fusion par champ (pure, sans E/S)

def canonique(objet: Any) -> bytes:
    """La forme des écrivains (`tasks._octets_enveloppe`, `ledger.record_bytes`) : indent 2, clés triées, LF."""
    return (json.dumps(objet, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def _cle(valeur: Any) -> str:
    """Égalité TYPÉE (`1`, `1.0` et `true` diffèrent, comme dans le fichier) ; un champ absent est une valeur."""
    return "\x00absent" if valeur is _ABSENT else json.dumps(valeur, sort_keys=True, ensure_ascii=False)


def _egal(x: Any, y: Any) -> bool:
    return _cle(x) == _cle(y)


def _date(valeur: Any) -> bool:
    """Expression ancrée ASCII PUIS `fromisoformat` — seul, il accepte aussi `20261012` (Python ≥ 3.11)."""
    if not (isinstance(valeur, str) and _DATE.match(valeur)):
        return False
    try:
        datetime.date.fromisoformat(valeur)
    except ValueError:
        return False
    return True


def _operations(valeur: Any) -> bool:
    return (isinstance(valeur, list) and all(isinstance(op, str) and op for op in valeur)
            and len(set(valeur)) == len(valeur))


def _fusion(base: Any, nous: Any, eux: Any, chemin: tuple[str, ...]) -> Any:
    if _egal(nous, eux):
        return nous
    if chemin == ("sync_operations",):
        # Règle d'ensemble à trois voies, seulement sur TROIS listes d'ids distincts ; sinon conflit.
        if not all(_operations(x) for x in (base, nous, eux)):
            raise Conflit("sync_operations")
        b, n, e = set(base), set(nous), set(eux)
        return sorted((b & n & e) | (n - b) | (e - b))
    if chemin == ("record",) and (nous is None or eux is None):
        # TOMBE, écrite pour qu'un refactor ne la perde pas : une tombe contre un `record` modifié est un CONFLIT
        # (la « rétention des enregistrements ») ; contre un `record` inchangé, la tombe est prise.
        autre = eux if nous is None else nous
        if not _egal(autre, base):
            raise Conflit("record (tombe contre modification)")
        return None
    if _egal(nous, base):
        return eux
    if _egal(eux, base):
        return nous
    if chemin == ("record", "updated") and _date(nous) and _date(eux):
        return max(nous, eux)
    if isinstance(base, dict) and isinstance(nous, dict) and isinstance(eux, dict):
        return _fusion_objets(base, nous, eux, chemin)
    raise Conflit("/".join(chemin) or "enveloppe")


def _caviarder(texte: str) -> str:
    """Caviardé PUIS plafonné (l'ordre des écrivains) ; la neutralisation des contrôles reste à `_stderr`."""
    texte = _JETON_SECRET.sub("[caviardé]", texte)
    return texte[:ACTEUR_PLAFOND] + ACTEUR_MARQUE if len(texte) > ACTEUR_PLAFOND else texte


def _dire_acteur(valeur: Any) -> str:
    """Un acteur pour le message : `nom <email> copie c`, chaque champ caviardé ; hors forme, son JSON caviardé."""
    if valeur is _ABSENT or valeur is None:
        return "(aucun)"
    auteur = valeur.get("auteur") if isinstance(valeur, dict) else None
    if isinstance(auteur, dict) and set(valeur) == {"auteur", "copie"} and set(auteur) == {"nom", "email"}:
        nom, email, copie = (_caviarder(str(v)) if v is not None else "?"
                             for v in (auteur["nom"], auteur["email"], valeur["copie"]))
        return f"{nom} <{email}> copie {copie}"
    return "forme inconnue " + _caviarder(_cle(valeur))


def cles_propriete(*cotes: dict) -> tuple[str, ...]:
    """Le groupe de la propriété : `start_actor` PUIS chaque champ `jira_claim_*` et `reprise_levee` présent d'un
    côté au moins, trié."""
    return (PROPRIETE, *sorted({c for cote in cotes for c in cote
                                if c.startswith(PREFIXE_INTENTION) or c == REPRISE_LEVEE}))


def _dire_propriete(cles: tuple[str, ...], valeurs: tuple[Any, ...]) -> str:
    """Un côté du groupe pour le message : l'acteur, puis chaque champ d'intention présent, caviardé."""
    intention = [f"{c}={_caviarder(_cle(v))}" for c, v in zip(cles[1:], valeurs[1:]) if v is not _ABSENT]
    return _dire_acteur(valeurs[0]) + (" ; " + ", ".join(intention) if intention else "")


def _juger_acteurs(base: dict, nous: dict, eux: dict) -> None:
    """Chaque acteur de `ACTEURS` jugé ENTIER avant la descente : changé des deux côtés vers deux valeurs ⇒ `Conflit`
    qui nomme le diagnostic et les deux versions caviardées ; sinon la descente le prend par ses raccourcis de base."""
    def change_des_deux_cotes(cles: tuple[str, ...]) -> tuple[Any, Any] | None:
        b, n, e = (tuple(_cle(cote.get(c, _ABSENT)) for c in cles) for cote in (base, nous, eux))
        if n == e or n == b or e == b:
            return None
        return tuple(nous.get(c, _ABSENT) for c in cles), tuple(eux.get(c, _ABSENT) for c in cles)

    for cle, diagnostic in ACTEURS:
        cotes = change_des_deux_cotes((cle,))
        if cotes is not None:
            n, e = (c[0] for c in cotes)
            raise ConflitActeur(f"record/{cle} ({diagnostic} : nous {_dire_acteur(n)} ; eux {_dire_acteur(e)})")
    cles = cles_propriete(base, nous, eux)
    cotes = change_des_deux_cotes(cles)
    if cotes is not None:
        raise ConflitActeur(f"record/{PROPRIETE}+{PREFIXE_INTENTION}* (propriété et intention Jira changées des "
                            f"deux côtés : nous {_dire_propriete(cles, cotes[0])} | eux "
                            f"{_dire_propriete(cles, cotes[1])})")
    # Le couple : jugé seulement quand `stage` seul ne conflicte pas (sinon `record/stage`, nom historique).
    cotes = change_des_deux_cotes(STAGE_SIGNE)
    if cotes is not None and change_des_deux_cotes(("stage",)) is None:
        (sn, an), (se, ae) = cotes
        raise ConflitActeur(f"record/{'+'.join(STAGE_SIGNE)} (stage repris sous une autre signature : nous "
                            f"{_caviarder(_cle(sn))} signé {_dire_acteur(an)} ; eux {_caviarder(_cle(se))} "
                            f"signé {_dire_acteur(ae)})")


def _fusion_objets(base: dict, nous: dict, eux: dict, chemin: tuple[str, ...]) -> dict:
    if chemin == ("record",):
        _juger_acteurs(base, nous, eux)
    sortie: dict[str, Any] = {}
    groupes = [cles for parent, cles in COUPLES if parent == chemin]
    for cles in groupes:
        tb, tn, te = (tuple(_cle(cote.get(c, _ABSENT)) for c in cles) for cote in (base, nous, eux))
        if tn == te or te == tb:
            source = nous
        elif tn == tb:
            source = eux
        else:
            raise Conflit("/".join(chemin + ("+".join(cles),)))
        sortie.update((c, source[c]) for c in cles if c in source)
    groupes_cles = {c for cles in groupes for c in cles}
    for cle in sorted((set(base) | set(nous) | set(eux)) - groupes_cles):
        valeur = _fusion(base.get(cle, _ABSENT), nous.get(cle, _ABSENT), eux.get(cle, _ABSENT), chemin + (cle,))
        if valeur is not _ABSENT:
            sortie[cle] = valeur
    return sortie


def fusionner(base: dict, nous: dict, eux: dict) -> dict:
    """Fusion à trois voies d'une enveloppe ; `Conflit` nommé par son chemin de champ. Pure, sans E/S."""
    if not all(isinstance(x, dict) for x in (base, nous, eux)):
        raise Conflit("enveloppe")
    if not (_egal(base.get("id", _ABSENT), nous.get("id", _ABSENT))
            and _egal(nous.get("id", _ABSENT), eux.get("id", _ABSENT))):
        raise Conflit("id")
    # L'enveloppe est TOUJOURS descendue champ par champ : un raccourci « un côté inchangé ⇒ l'autre » à ce niveau
    # sauterait la règle de `sync_operations` (trois listes, sinon conflit).
    resultat = _fusion_objets(base, nous, eux, ())
    record = resultat.get("record", _ABSENT)
    # POST-CONDITION (couple `id` ↔ `record.id`) : `record` est nul ou porte l'id de l'enveloppe.
    if record is not None and not (isinstance(record, dict)
                                   and _egal(record.get("id", _ABSENT), resultat.get("id", _ABSENT))):
        raise Conflit("id/record.id")
    return resultat


# DEUX IMPORTS D'UN MÊME TICKET JIRA (T-01M5GZ4VBPCJD3S2NPWQTB3XGP, arbitrage S-01M5HAKRWKB2N5NBPASPWN3R4Y). Deux clones
# qui importent le même ticket créent le même fichier : git appelle le pilote sur un ajout/ajout, %O VIDE. Au même
# résumé et sans geste local, les octets sont égaux et git ne l'appelle pas. Sinon la base est l'enregistrement
# d'import (`_jira_record`, tasks_jira.py), reconstruit ici. LISTE FERMÉE : ces champs, provenance du ticket, doivent
# concorder des deux côtés (absent = une valeur) ; deux résumés différents (`task`) restent un CONFLIT — rien de
# persisté n'ordonne deux dates Jira. Tout autre champ se fusionne à trois voies contre cette base.
CHAMPS_JIRA: tuple[str, ...] = ("task", "jira_updated", "jira_site", "jira_issue_id", "jira_created", "jira_key",
                                "jira_url", "jira_type", "jira_parent_key")
#: Ce que la base exige en chaîne (provenance complète) ; un manque est un conflit nommé, jamais une base devinée.
_PROVENANCE_JIRA = ("task", "jira_site", "jira_issue_id", "jira_created", "jira_key", "jira_url", "jira_type")
#: Les valeurs par défaut de `_jira_record`, RECOPIÉES (la copie tourne sous -I, sans `tasks`) ; le témoin
#: `test_tasks_jira.py` compare la base au producteur réel, jamais à cette copie.
IMPORT_JIRA_DEFAUTS: dict[str, str] = {"state": "pending", "owner": "", "stage": "",
                                       "pas_un_defaut": "ticket Jira importé, sans mesure locale"}


def operation_import_jira(site: str, issue_id: str) -> str:
    """L'opération d'import de `_jira_record` : `uuid5(NAMESPACE_URL, "jira:<site>|<id>")`."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"jira:{site}|{issue_id}"))


def base_import_jira(nous: dict, eux: dict) -> dict:
    """La base d'un ajout/ajout : l'enveloppe d'import du ticket commun. Aucun côté ne porte de champ `jira_*` ⇒
    `HorsForme` (le repli d'une base vide, inchangé) ; champ de `CHAMPS_JIRA` divergent, provenance incomplète ou
    opération d'import absente d'un côté ⇒ `Conflit` nommé."""
    records = [cote.get("record") for cote in (nous, eux)]
    if not any(isinstance(r, dict) and any(c.startswith("jira_") and c in r for c in CHAMPS_JIRA) for r in records):
        raise HorsForme("base vide hors import Jira")
    n, e = records
    if not (isinstance(n, dict) and isinstance(e, dict)):
        raise Conflit("record (import Jira contre un enregistrement absent)")
    for champ in CHAMPS_JIRA:
        if not _egal(n.get(champ, _ABSENT), e.get(champ, _ABSENT)):
            raise Conflit(f"record/{champ} (deux imports Jira divergents)")
    for champ in _PROVENANCE_JIRA:
        if not isinstance(n.get(champ), str):
            raise Conflit(f"record/{champ} (provenance Jira incomplète)")
    if not _date(n["jira_created"][:10]):
        raise Conflit("record/jira_created (provenance Jira incomplète)")
    operation = operation_import_jira(n["jira_site"], n["jira_issue_id"])
    for nom, cote in (("nous", nous), ("eux", eux)):
        ops = cote.get("sync_operations")
        if not (_operations(ops) and operation in ops):
            raise Conflit(f"sync_operations (opération d'import Jira absente : {nom})")
    record = {"id": n.get("id"), **IMPORT_JIRA_DEFAUTS, "updated": n["jira_created"][:10]}
    record.update((champ, n[champ]) for champ in CHAMPS_JIRA if champ in n)
    return {"format": 1, "id": nous.get("id"), "record": record, "sync_operations": [operation]}


# ---------------------------------------------------------------- lecture, écriture, repli

def _refus_constante(nom: str) -> Any:
    raise HorsForme(f"constante {nom} refusée")


def lire(chemin: str | os.PathLike[str]) -> dict:
    """Un côté : ≤ 1 Mio, UTF-8 strict, JSON strict (NaN / Infinity refusés), objet, octets == forme canonique,
    `format` == l'entier 1 ; sinon `HorsForme`."""
    with open(chemin, "rb") as fh:
        octets = fh.read(PLAFOND + 1)
    if len(octets) > PLAFOND:
        raise HorsForme("au-dessus du plafond de 1 Mio")
    try:
        objet = json.loads(octets.decode("utf-8"), parse_constant=_refus_constante)
        if not isinstance(objet, dict):
            raise HorsForme("la racine n'est pas un objet")
        if canonique(objet) != octets:
            raise HorsForme("hors forme canonique")
    except RecursionError:
        raise HorsForme("imbrication trop profonde") from None
    except UnicodeDecodeError:
        raise HorsForme("UTF-8 invalide") from None
    except json.JSONDecodeError as exc:
        raise HorsForme(f"JSON invalide ({exc.msg})") from None
    except ValueError as exc:  # une surrogate isolée n'a pas de forme UTF-8
        raise HorsForme(f"JSON non sérialisable ({exc})") from None
    if type(objet.get("format")) is not int or objet["format"] != 1:
        raise HorsForme(f"format {objet.get('format')!r} : seul l'entier 1 est jugé")
    return objet


def ecrire_atomique(chemin: str | os.PathLike[str], octets: bytes) -> None:
    """Temporaire dans le dossier de %A puis `os.replace` : %A reste « nous » intact ou devient la fusion complète,
    jamais un fichier à moitié écrit ; le temporaire est supprimé sur échec."""
    cible = Path(chemin)
    fd, tmp = tempfile.mkstemp(dir=cible.resolve().parent, prefix=".fusion-par-champ-")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(octets)
        os.replace(tmp, cible)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def fusion_par_champ(o: str, a: str, b: str) -> None:
    """Lit les trois côtés, fusionne, écrit %A — après la fusion complète seulement. %O VIDE : `base_import_jira`."""
    with open(o, "rb") as fh:
        vide = fh.read(1) == b""
    base = None if vide else lire(o)
    nous, eux = lire(a), lire(b)
    if base is None:
        base = base_import_jira(nous, eux)
    ecrire_atomique(a, canonique(fusionner(base, nous, eux)))


def argv_repli(o: str, a: str, b: str, taille: str, ls: str, lx: str, ly: str) -> list[str]:
    """La fusion TEXTE de git, en LISTE (jamais un shell) ; labels %X / %S / %Y de git, dans l'ordre de merge-file."""
    return ["git", "merge-file", "--diff-algorithm=histogram", f"--marker-size={taille}",
            "-L", lx, "-L", ls, "-L", ly, a, o, b]


def _instantane(chemin: str) -> bytes | None:
    """%A AVANT la fusion texte d'un refus, pour le remettre si merge-file échoue : au plus `PLAFOND` octets (le
    pilote vient de le lire sous cette borne) ; None s'il est illisible ou au-delà."""
    try:
        with open(chemin, "rb") as fh:
            octets = fh.read(PLAFOND + 1)
    except OSError:
        return None
    return octets if len(octets) <= PLAFOND else None


def _remettre(chemin: str, octets: bytes | None) -> bool:
    """Réécrit %A à l'identique de `octets`, atomiquement ; False si rien à remettre ou si l'écriture échoue."""
    if octets is None:
        return False
    try:
        ecrire_atomique(chemin, octets)
    except OSError:
        return False
    return True


def repli(o: str, a: str, b: str, taille: str, ls: str, lx: str, ly: str) -> int:
    """rc de merge-file 0 ⇒ 0 ; 1 à 127 (conflits écrits) ⇒ 3 ; autre rc, délai ou lancement impossible ⇒ 4. `main`
    rend 3 sur un REFUS (0 ou 4 compris) ; hors refus, sur 4, la commande rejoue la fusion texte."""
    try:
        p = subprocess.run(argv_repli(o, a, b, taille, ls, lx, ly), check=False, timeout=_DELAI)
    except (OSError, subprocess.SubprocessError):
        return 4
    if p.returncode == 0:
        return 0
    return 3 if 0 < p.returncode <= 127 else 4


def ligne_copie_divergente(racine: Path, soi: Path) -> str | None:
    """Informative (S8) : le fichier suivi du worktree (cwd = racine du worktree) ≠ la copie qui tourne. Elle ne
    prescrit aucun remède — le worktree n'est pas l'autorité, `--verifier` juge la copie contre HEAD.
    BORNÉE (avis sécurité de la fusion, passe de correction F5) : tailles différentes ⇒ divergente sans rien lire ;
    au-delà de `PLAFOND` octets, rien n'est lu ni dit ; sinon deux lectures d'au plus `PLAFOND` + 1 octets."""
    try:
        suivi = racine / CHEMIN_SUIVI
        if not suivi.is_file():
            return None
        taille = suivi.stat().st_size
        if taille != soi.stat().st_size:
            return DIVERGENCE
        if taille > PLAFOND:
            return None
        with open(suivi, "rb") as a, open(soi, "rb") as b:
            if a.read(PLAFOND + 1) == b.read(PLAFOND + 1):
                return None
    except OSError:
        return None
    return DIVERGENCE


def _neutraliser(texte: str) -> str:
    """Tout caractère NON IMPRIMABLE — ESC, BEL, CR, LF, contrôles Unicode — sort ÉCHAPPÉ (`\\x1b`, `\\n`…) : une
    clé du fichier fusionné, citée par un `Conflit`, ne pilote jamais le terminal ni ne forge une ligne (avis sécu
    de F1)."""
    return "".join(c if c.isprintable() else c.encode("unicode_escape").decode("ascii") for c in texte)


def _stderr(texte: str) -> None:
    """L'UNIQUE écrivain de stderr du chemin de fusion : une ligne, neutralisée."""
    with contextlib.suppress(OSError, ValueError):
        sys.stderr.write(_neutraliser(texte) + "\n")


# ---------------------------------------------------------------- la commande `driver`, repli sur la fusion texte

def _citer(valeur: str) -> str:
    """`shlex.quote` PUIS `%` doublés : git développe `%A`… même dans un chemin (M15)."""
    return shlex.quote(valeur).replace("%", "%%")


def commande_driver(py: str, copie: str) -> str:
    """L'UNIQUE source de la valeur `driver`. Repli : la fusion texte de git, comme sans pilote — PAS fail-closed :
    copie absente ou cassée, interpréteur absent, une paire que le pilote refuserait peut fusionner sans conflit ;
    `--verifier` le dit (`absent`, `altérée`, `interpréteur absent`). rc 0 ⇒ fusion ; rc 3 ⇒ conflit écrit (TOUT
    refus d'un pilote qui tourne, même quand sa fusion texte est propre ou échoue) ; tout autre rc ⇒ la fusion texte
    de git : marqueurs si les lignes se touchent, sinon fusion propre (rc 0). Aucune autre interpolation que `py` et
    `copie` ; les labels %X %S %Y sont quotés par git."""
    return (f"{_citer(py)} -I -B {_citer(copie)} %O %A %B %L %S %X %Y; rc=$?; "
            "if [ $rc -eq 0 ]; then exit 0; fi; if [ $rc -eq 3 ]; then exit 1; fi; "
            "git merge-file --diff-algorithm=histogram --marker-size=%L -L %X -L %S -L %Y %A %O %B")


def commande_driver_index(py: str, copie: str) -> str:
    """L'UNIQUE source de la valeur `merge.cadre-index.driver` (T-01M5X9143QVEGWMBYANB6MB4TD) : rc 0 du pilote ⇒
    fusion écrite ; tout autre rc (REPLI dit, pilote absent ou cassé, interpréteur absent) ⇒ la fusion texte de git
    sur %A INTACT — le conflit d'aujourd'hui, jamais pire."""
    return (f"{_citer(py)} -I -B {_citer(copie)} --index %O %A %B %P; rc=$?; "
            "if [ $rc -eq 0 ]; then exit 0; fi; "
            "git merge-file --diff-algorithm=histogram --marker-size=%L -L %X -L %S -L %Y %A %O %B")


# ---------------------------------------------------------------- fusion de l'index (`--index %O %A %B %P`)
#: Miroirs de `build_index.ACTIVE_RE` et `build_index.ROW_RE` (la copie tourne sous -I, sans import du kit) ; leur
#: égalité est tenue par `test_fusion_index.py`. LIGNE_MODULE est LINÉAIRE (cellules 2-4 brutes, coupées aux `|`,
#: nettoyées par l'appelant) : l'ancien motif à cellules paresseuses `\s*(.*?)\s*` était cubique (ReDoS, 400 `| ` ≈ 80 s).
#: Une 1re cellule VIDE n'est plus reconnue (jamais produite par build_index, qui écrit toujours le chemin).
LIGNE_SYM = re.compile(r"^(SYM-\d+)\s+(\S+):(\d+)-(\d+)\s+(\S+)\s+(\S+)\s+uses\[([^\]]*)\]\s*(?:::\s*(.*))?$")
LIGNE_MODULE = re.compile(r"^\|\s*(?:`\s*)?([^|`\s](?:[^|`]*[^|`\s])?)(?:\s*`)?\s*\|([^|]*)\|([^|]*)\|(.*)\|\s*$")
#: La ligne de débordement que `build_index` GÉNÈRE (`| (N more) | K symbols — see shards |`) : un compte, jamais un
#: rôle écrit — l'ignorer, la reconstruction `--if-stale` la récrit.
DEBORDEMENT = re.compile(r"\(\d+ more\)")
DELTA_INDEX = "INDEX_DELTA.json"
PLAFOND_INDEX = 1 << 26  # 64 Mio par côté ; au-delà, repli texte
_VIDE = ("", "—", "-")


class Repli(Exception):
    """Ce que « eux » a écrit ne se reporte pas sur « nous » sans perte : %A intact, la commande rejoue la fusion
    texte de git (C3 du plan-critic : un `:: but` ou une cellule Role/Owner ne disparaît jamais en silence)."""


def _texte_index(chemin: str) -> str:
    with open(chemin, "rb") as fh:
        octets = fh.read(PLAFOND_INDEX + 1)
    if len(octets) > PLAFOND_INDEX:
        raise Repli("au-dessus du plafond de 64 Mio")
    try:
        return octets.decode("utf-8")
    except UnicodeDecodeError:
        raise Repli("UTF-8 invalide") from None


def _entrees(texte: str, module: bool) -> dict[Any, tuple[str, int, Any, str]]:
    """clé ⇒ (identité, n° de ligne, match, valeur). Symboles : clé = id, identité = (chemin, nom, sorte), valeur = le
    `:: but`. Modules (CODEBASE_INDEX.md) : clé = (chemin, cellule), identité = chemin, valeur = Role ou Owner. Une
    clé vue deux fois dans un même côté est ambiguë : `Repli`."""
    vus: dict[Any, tuple[Any, int, Any, str]] = {}
    for n, ligne in enumerate(texte.splitlines()):
        m = (LIGNE_MODULE if module else LIGNE_SYM).match(ligne)
        if m is None or (module and DEBORDEMENT.fullmatch(m.group(1))):
            continue
        if module:
            items = [((m.group(1), g), m.group(1), m.group(g).strip()) for g in (2, 4)]
        else:
            items = [(m.group(1), (m.group(2), m.group(5), m.group(6)), (m.group(8) or "").rstrip())]
        for cle, ident, valeur in items:
            if cle in vus:
                raise Repli(f"{cle} vu deux fois dans un même côté")
            vus[cle] = (ident, n, m, "" if valeur.strip() in _VIDE else valeur.strip())
    return vus


def _a_reporter(base: dict, nous: dict, eux: dict) -> dict[Any, str]:
    """Les valeurs NON vides que « eux » a changées depuis la base : reportées sur la même clé de « nous » quand
    l'identité est la même et que « nous » ne l'a pas changée ; sinon `Repli` (jamais une perte muette)."""
    pose: dict[Any, str] = {}
    for cle, (ident, _n, _m, valeur) in eux.items():
        b = base.get(cle)
        avant = b[3] if b is not None and b[0] == ident else ""
        if not valeur or valeur == avant:
            continue
        n = nous.get(cle)
        if n is None or n[0] != ident:
            raise Repli(f"{cle} : absent de « nous » sous la même identité")
        if n[3] == valeur:
            continue
        if n[3] != avant:
            raise Repli(f"{cle} : changé des deux côtés")
        pose[cle] = valeur
    return pose


def _reporter(o: str, a: str, b: str, module: bool) -> int:
    """Garde « nous » et y reporte les valeurs de « eux » ; rend le nombre de valeurs reprises."""
    texte = _texte_index(a)
    vide = os.path.getsize(o) == 0
    nous = _entrees(texte, module)
    pose = _a_reporter({} if vide else _entrees(_texte_index(o), module), nous, _entrees(_texte_index(b), module))
    if not pose:
        return 0
    lignes = texte.splitlines(keepends=True)
    par_ligne: dict[int, tuple[Any, dict[int, str]]] = {}
    for cle, valeur in pose.items():
        _ident, n, m, _v = nous[cle]
        par_ligne.setdefault(n, (m, {}))[1][cle[1] if module else 8] = valeur
    for n, (m, valeurs) in par_ligne.items():
        fin = lignes[n][len(m.string):]
        if module:
            cellules = [m.group(i).strip() for i in (1, 2, 3, 4)]
            for groupe, valeur in valeurs.items():
                cellules[groupe - 1] = valeur
            lignes[n] = "| " + " | ".join(cellules) + " |" + fin
        else:
            lignes[n] = m.string[:m.end(7) + 1] + f"  :: {valeurs[8]}" + fin
    ecrire_atomique(a, "".join(lignes).encode("utf-8"))
    return len(pose)


def _plafond_delta(chemin: str, vide_permis: bool) -> tuple[dict | None, int]:
    if vide_permis and os.path.getsize(chemin) == 0:
        return None, 0
    try:
        objet = json.loads(_texte_index(chemin))
    except (json.JSONDecodeError, RecursionError) as exc:
        raise Repli(f"{DELTA_INDEX} illisible ({type(exc).__name__})") from None
    plafond = objet.get("max_sym_id") if isinstance(objet, dict) else None
    if type(plafond) is not int or plafond < 0:
        raise Repli(f"{DELTA_INDEX} : max_sym_id absent ou non entier")
    return objet, plafond


def _fusion_delta(o: str, a: str, b: str) -> None:
    """« nous » avec max_sym_id = max(O, A, B) : un id alloué d'un seul côté n'est jamais réattribué à un autre
    symbole (M4 V2) ; le recouvrement alloué des deux côtés est DIT, jamais résolu (inévitable)."""
    _vb, vo = _plafond_delta(o, True)
    nous, va = _plafond_delta(a, False)
    _ve, vb = _plafond_delta(b, False)
    plafond = max(vo, va, vb)
    if va > vo and vb > vo:
        largeur = max(3, len(str(plafond)))
        _stderr(f"fusion de l'index : SYM-{vo + 1:0{largeur}d}..SYM-{min(va, vb):0{largeur}d} alloués des deux côtés "
                "— relocaliser par NOM, relire annotations_log.jsonl pour ces ids, reconstruire l'index")
    if plafond != va and nous is not None:
        nous["max_sym_id"] = plafond
        ecrire_atomique(a, (json.dumps(nous, indent=2) + "\n").encode("utf-8"))


def fusion_index(o: str, a: str, b: str, chemin: str) -> int:
    """`--index %O %A %B %P` : 0 = %A écrit (« nous », plafond d'ids et valeurs de « eux » reportés) ; 4 = REPLI dit
    sur stderr, %A intact, la commande rejoue la fusion texte de git. `INDEX_DELTA.json` : `_fusion_delta` ;
    `SYMBOLS*.md` : `:: but` reportés ; `CODEBASE_INDEX.md` : cellules Role/Owner reportées ; tout autre fichier
    d'index : « nous ». L'index reste à RECONSTRUIRE après la fusion (`build_index.py --if-stale`)."""
    nom = os.path.basename(chemin)
    try:
        if nom == DELTA_INDEX:
            _fusion_delta(o, a, b)
            return 0
        if nom == "CODEBASE_INDEX.md" or (nom.startswith("SYMBOLS") and nom.endswith(".md")):
            n = _reporter(o, a, b, module=nom == "CODEBASE_INDEX.md")
            if n:
                _stderr(f"fusion de l'index : {chemin} — « nous » gardé, {n} valeur(s) de « eux » reprise(s)")
        return 0
    except Repli as exc:
        cause = str(exc)
    except Exception as exc:  # noqa: BLE001 — aucune exception ne remonte à git : le repli texte la remplace
        cause = f"{type(exc).__name__} ({exc})"
    _stderr(f"fusion de l'index : {chemin} — {cause} — fusion texte de git")
    return 4


# ---------------------------------------------------------------- sonde de capacité git (jamais un numéro)

def _env_sonde() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    return env


def _lancer(argv: list[str], env: dict[str, str]) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(argv, env=env, capture_output=True, text=True, timeout=_DELAI, check=False)
    except (OSError, subprocess.SubprocessError):
        return None


def _motif(nom: str, p: subprocess.CompletedProcess | None) -> str:
    if p is None:
        return f"{nom} : git introuvable ou délai dépassé"
    premiere = ((p.stderr or "") + (p.stdout or "")).strip().splitlines()[:1]
    return f"{nom} rc={p.returncode}" + (f" : {premiere[0]}" if premiere else "")


def _preparer_sonde(depot: Path, env: dict[str, str]) -> str | None:
    """Le dépôt jetable de la sonde des labels ; rend l'étape en défaut, ou None. Identité LOCALE (E1) : sans elle,
    `git commit` rend 128 sur un poste sans identité, et la sonde dirait absente une capacité présente."""
    g = ["git", "-C", str(depot)]
    etapes: tuple[tuple[str, list[str], tuple[tuple[str, bytes], ...]], ...] = (
        ("init", ["git", "-c", "init.defaultBranch=main", "init", "-q", str(depot)], ()),
        ("config core.hooksPath", [*g, "config", "core.hooksPath", os.devnull], ()),
        ("config user.name", [*g, "config", "user.name", "sonde"], ()),
        ("config user.email", [*g, "config", "user.email", "sonde@example.invalid"], ()),
        ("config commit.gpgsign", [*g, "config", "commit.gpgsign", "false"], ()),
        ("add", [*g, "add", "-A"], ((".gitattributes", b"f merge=sonde\n"), ("f", b"1\n2\n3\n"))),
        ("commit base", [*g, "commit", "-qm", "base"], ()),
        ("branch b", [*g, "branch", _BRANCHE_SONDE], ()),
        ("commit A", [*g, "commit", "-qam", "A"], (("f", b"1\n2\nX\n"),)),
        ("checkout b", [*g, "checkout", "-q", _BRANCHE_SONDE], ()),
        ("commit B", [*g, "commit", "-qam", "B"], (("f", b"Y\n2\n3\n"),)),
        ("checkout main", [*g, "checkout", "-q", "main"], ()),
    )
    for nom, argv, fichiers in etapes:
        for chemin, octets in fichiers:
            (depot / chemin).write_bytes(octets)
        p = _lancer(argv, env)
        if p is None or p.returncode != 0:
            return _motif(nom, p)
    return None


def _labels_lus(lu: str | None) -> bool:
    """Les trois labels relus OCTET POUR OCTET, la branche hostile comprise (`_BRANCHE_SONDE`)."""
    parties = (lu or "").split("|")
    return len(parties) == 3 and parties[1:] == ["HEAD", _BRANCHE_SONDE] and _COURT.match(parties[0]) is not None


def sonder_git(dossier: str | None = None) -> dict[str, str]:
    """Trois sondes de CAPACITÉ (git ≥ 2.44), dans un dossier jetable (sous `dossier` s'il est donné) : (1)
    merge-file histogram, (2) labels %S %X %Y développés pour un pilote, (3) --path-format. Chaque valeur :
    « présent », « absent (…) » ou « impossible (…) » (préparation ratée, jamais dite capacité absente) ; « verdict »
    vaut « tout présent », « absent » ou « impossible ». Décide le refus de --installer ET le saut du banc."""
    env = _env_sonde()
    res: dict[str, str] = {}
    with tempfile.TemporaryDirectory(dir=dossier, prefix="sonde-", ignore_cleanup_errors=True) as tmp:
        d = Path(tmp)
        for nom, octets in (("o", b"a\nb\nc\n"), ("a", b"A\nb\nc\n"), ("b", b"a\nb\nC\n")):
            (d / nom).write_bytes(octets)
        p = _lancer(["git", "merge-file", "-p", "--diff-algorithm=histogram", str(d / "a"), str(d / "o"),
                     str(d / "b")], env)
        res[CAP_HISTOGRAM] = "présent" if p is not None and p.returncode == 0 else f"absent ({_motif('merge-file', p)})"
        depot, sortie = d / "depot", d / "lu"
        prepa = _preparer_sonde(depot, env)
        if prepa is None:
            gabarit = _GABARIT_SONDE.replace("@SORTIE@", _citer(str(sortie)))
            p = _lancer(["git", "-C", str(depot), "config", "merge.sonde.driver", gabarit], env)
            if p is None or p.returncode != 0:
                prepa = _motif("config merge.sonde.driver", p)
        if prepa is not None:
            res[CAP_LABELS] = f"impossible ({prepa})"
        else:
            _lancer(["git", "-C", str(depot), "merge", "-q", "--no-edit", _BRANCHE_SONDE], env)  # le pilote rend 1 : voulu
            lu = sortie.read_text(encoding="utf-8") if sortie.is_file() else None
            res[CAP_LABELS] = "présent" if _labels_lus(lu) else f"absent (lu={lu!r})"
        if (depot / ".git").is_dir():
            p = _lancer(["git", "-C", str(depot), "rev-parse", "--path-format=absolute", "--git-common-dir"], env)
            ok = p is not None and p.returncode == 0 and Path(p.stdout.strip()).is_absolute()
            res[CAP_CHEMINS] = "présent" if ok else f"absent ({_motif('rev-parse', p)})"
        else:
            res[CAP_CHEMINS] = f"impossible ({prepa or 'dépôt de sonde absent'})"
    valeurs = list(res.values())
    res["verdict"] = ("tout présent" if all(v == "présent" for v in valeurs)
                      else "absent" if any(v.startswith("absent") for v in valeurs) else "impossible")
    return res


def raison_sonde(res: dict[str, str]) -> str | None:
    """La raison NOMMÉE d'un verdict autre que « tout présent » ; None sinon."""
    absentes = [f"{k} — {v}" for k, v in res.items() if k != "verdict" and v.startswith("absent")]
    impossibles = [f"{k} — {v}" for k, v in res.items() if k != "verdict" and v.startswith("impossible")]
    morceaux = []
    if absentes:
        morceaux.append("git ≥ 2.44 requis (capacité absente : " + " ; ".join(absentes) + ")")
    if impossibles:
        morceaux.append("sonde impossible (préparation : " + " ; ".join(impossibles) + ")")
    return " ; ".join(morceaux) or None


# ---------------------------------------------------------------- installation et vérification

def _env_git() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in _GIT_LIEU}


def _git(depot: str, *args: str, texte: bool = True) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git", "-C", depot, *args], capture_output=True, text=texte, env=_env_git(),
                              timeout=_DELAI, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise Refus(f"git {args[0]} : {exc}") from None


def _toplevel(racine: str | None) -> str:
    depart = racine if racine is not None else str(Path(__file__).resolve().parent)
    p = _git(depart, "rev-parse", "--show-toplevel")
    top = p.stdout.strip() if p.returncode == 0 else ""
    if not top:
        raise Refus(f"aucun arbre de travail sous {depart} (dépôt nu, ou hors d'un dépôt) : rien d'armé")
    return top


def _refus_ref(ref: str) -> str | None:
    if not ref or ref.startswith("-"):
        return f"ref {ref!r} refusé avant tout appel à git : vide, ou commence par un tiret (une option, jamais un ref)"
    return None


def resoudre_commit(ref: str, depot: str) -> str:
    """Le sha COMPLET du commit nommé par `ref`, sinon `Refus` : garde du tiret AVANT tout sous-processus, puis
    `rev-parse --verify --end-of-options <ref>^{commit}` ; seul ce sha passe ensuite à `git show` (K3)."""
    refus = _refus_ref(ref)
    if refus is not None:
        raise Refus(refus)
    p = _git(depot, "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}")
    sha = p.stdout.strip() if p.returncode == 0 else ""
    if not _SHA.match(sha):
        raise Refus(f"ref {ref!r} : aucun commit (rev-parse rc={p.returncode})")
    return sha


def _blob(top: str, sha: str) -> bytes | None:
    p = _git(top, "show", f"{sha}:{CHEMIN_SUIVI}", texte=False)
    return p.stdout if p.returncode == 0 else None


def _sous_racine(chemin: str, top: str) -> bool:
    """`chemin` apparent (dossier résolu, dernier composant gardé : un lien posé SOUS la racine) ou résolu vit sous
    la racine, sous l'une ou l'autre de ses graphies."""
    absolu = Path(os.path.abspath(chemin))
    candidats = {absolu, Path(os.path.realpath(absolu.parent)) / absolu.name, Path(os.path.realpath(chemin))}
    racines = {Path(os.path.abspath(top)), Path(os.path.realpath(top))}
    return any(c.is_relative_to(r) for c in candidats for r in racines)


def _racines_du_depot(top: str) -> list[str]:
    """La racine courante PUIS celle de CHAQUE worktree du dépôt (`git worktree list --porcelain -z`) : une branche
    extraite dans n'importe lequel réécrit ce qu'il porte (avis sécurité de la fusion, passe de correction F5)."""
    racines = [top]
    p = _git(top, "worktree", "list", "--porcelain", "-z")
    if p.returncode == 0:
        racines += [champ[len("worktree "):] for champ in p.stdout.split("\0") if champ.startswith("worktree ")]
    return racines


def _garde_interpreteur(top: str, depuis: str | None) -> None:
    """Un interpréteur sous la racine du worktree courant OU d'un autre worktree du même dépôt pourrait être réécrit
    par une branche : refus. Le remède NOMME l'interpréteur de BASE, sans jamais le substituer (la valeur figée
    reste le `sys.executable` de l'appel)."""
    exe = sys.executable or ""
    if not exe:
        raise Refus("sys.executable est vide : aucun interpréteur à figer, rien d'armé")
    racines = _racines_du_depot(top)
    sous = next((r for r in racines if _sous_racine(exe, r)), None)
    if sous is None:
        return
    top = sous
    base = getattr(sys, "_base_executable", "") or ""
    if base and not any(_sous_racine(base, r) for r in racines):
        commande = [shlex.quote(base), shlex.quote(CHEMIN_SUIVI), "--installer"]
        commande += ["--depuis", shlex.quote(depuis)] if depuis is not None else []
        raise Refus(f"l'interpréteur {exe} vit sous la racine du dépôt {top} : une branche pourrait le réécrire. "
                    f"Remède : l'interpréteur de BASE, hors du dépôt (sys._base_executable = {base}) ; depuis la "
                    f"racine : {' '.join(commande)}")
    raise Refus(f"l'interpréteur {exe} vit sous la racine du dépôt {top}, et sys._base_executable "
                f"({base or 'vide'}) aussi ou vide : aucune commande proposée, il faut un Python hors du dépôt")


def _branche_defaut(top: str) -> str:
    p = _git(top, "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD")
    nom = p.stdout.strip() if p.returncode == 0 else ""
    if nom:
        return nom.removeprefix("origin/")
    for candidat in ("main", "master"):
        if _git(top, "rev-parse", "--verify", "-q", "--end-of-options", f"refs/heads/{candidat}").returncode == 0:
            return candidat
    return "main"


def _poser_copie(dossier: Path, octets: bytes) -> tuple[Path, str]:
    """Copie adressée par son contenu, 0o400 dans un dossier 0o700, par temporaire + `os.replace` ; jamais réécrite
    si elle a déjà le contenu de son nom ; présente avec un autre contenu ⇒ remplacée, et DITE."""
    empreinte = hashlib.sha256(octets).hexdigest()
    dossier.mkdir(mode=0o700, exist_ok=True)
    os.chmod(dossier, 0o700)
    # Avis sécurité de la fusion (passe de correction F5) : un arrêt brutal (SIGKILL) entre `mkstemp` et `os.replace`
    # laisse un `.copie-*` ; plus vieux que `_AGE_ORPHELIN`, c'est un orphelin (jamais un appel concurrent vivant).
    limite = time.time() - _AGE_ORPHELIN
    for orphelin in dossier.glob(".copie-*"):
        with contextlib.suppress(OSError):
            st = orphelin.lstat()
            if stat.S_ISREG(st.st_mode) and st.st_mtime < limite:
                orphelin.unlink()
    copie = dossier / f"{_PREFIXE_COPIE}{empreinte[:16]}.py"
    # UN LIEN SYMBOLIQUE N'EST PAS UNE COPIE (S-01M5F950RA) : `.githooks/post-merge` le refuse, même vers un
    # contenu identique ; `os.replace` remplace le LIEN (jamais sa cible) par une vraie copie.
    if copie.is_symlink():
        etat = "lien symbolique : remplacé par une copie"
    elif copie.is_file():
        if hashlib.sha256(copie.read_bytes()).hexdigest() == empreinte:
            os.chmod(copie, 0o400)
            return copie, "déjà en place"
        etat = "altérée : remplacée"
    else:
        etat = "posée"
    fd, tmp = tempfile.mkstemp(dir=dossier, prefix=".copie-")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(octets)
        os.chmod(tmp, 0o400)
        os.replace(tmp, copie)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
    return copie, etat


def _installer(racine: str | None, depuis: str | None) -> int:
    if sys.stdin is None or not sys.stdin.isatty():
        raise Refus("geste du pilote : arme une commande dans .git/config (T-00000763) ; à lancer depuis un terminal")
    top = _toplevel(racine)
    _garde_interpreteur(top, depuis)
    sha = resoudre_commit(depuis if depuis is not None else "HEAD", top)
    p = _git(top, "symbolic-ref", "-q", "--short", "HEAD")
    branche = p.stdout.strip() if p.returncode == 0 else ""
    print(f"branche={branche or '(détachée)'} sha={sha[:8]}" + (f" depuis={depuis}" if depuis is not None else ""))
    if depuis is None:
        defaut = _branche_defaut(top)
        if branche != defaut:
            raise Refus(f"le pilote d'une branche non fusionnée arme SON code : HEAD est sur "
                        f"{branche or '(détachée)'}, la branche par défaut est {defaut} — --depuis <ref> pour l'assumer")
        # Avis sécurité de la fusion (passe de correction F5) : sur la branche par défaut, un commit LOCAL non poussé
        # armerait un code que personne n'a relu. BORNE : sans `refs/remotes/origin/<défaut>`, rien à comparer.
        amont = f"refs/remotes/origin/{defaut}"
        if _git(top, "rev-parse", "--verify", "-q", "--end-of-options", amont).returncode == 0 and \
                _git(top, "merge-base", "--is-ancestor", sha, amont).returncode != 0:
            raise Refus(f"HEAD ({sha[:8]}) porte des commits locaux NON poussés sur origin/{defaut} : ils armeraient "
                        f"un code que personne n'a relu — pousse d'abord, ou --depuis <ref> pour l'assumer")
    octets = _blob(top, sha)
    if octets is None:
        raise Refus(f"le commit {sha[:8]} n'a pas {CHEMIN_SUIVI}")
    raison = raison_sonde(sonder_git())
    if raison is not None:
        raise Refus(raison)
    p = _git(top, "rev-parse", "--path-format=absolute", "--git-common-dir")
    commun = Path(p.stdout.strip()) if p.returncode == 0 else Path()
    if not commun.is_absolute() or not commun.is_dir():
        raise Refus(f"git-common-dir illisible (rc={p.returncode})")
    copie, etat = _poser_copie(commun / "cadre", octets)
    print(f"copie {etat} : {copie}")
    # Board PUIS index (T-01M5X9143QVEGWMBYANB6MB4TD), chacun `.driver` D'ABORD (N4, revue de clôture F5) : `.name`
    # seul fait échouer TOUT `git merge` qui touche un chemin de ce pilote (rc 128, « custom merge driver … lacks
    # command line », mesuré git 2.55) ; `.driver` seul fusionne (le nom n'est qu'un libellé). Un `.name` en échec
    # AVERTIT sans sauter les clés suivantes (C4) ; seul le `.driver` du board refuse.
    for cle_driver, valeur, cle_nom, libelle, quoi in (
            (CLE_DRIVER, commande_driver(sys.executable, str(copie)), CLE_NOM, LIBELLE, "fusion par champ"),
            (CLE_INDEX_DRIVER, commande_driver_index(sys.executable, str(copie)), CLE_INDEX_NOM, LIBELLE_INDEX,
             "fusion de l'index")):
        p = _git(top, "config", "--local", cle_driver, valeur)
        if p.returncode != 0 and cle_driver == CLE_DRIVER:
            raise Refus(f"git config --local {cle_driver} : rc={p.returncode} {p.stderr.strip()}")
        if p.returncode != 0:
            _stderr(f"{quoi}, installation : AVERTISSEMENT — git config --local {cle_driver} : rc={p.returncode} "
                    f"{p.stderr.strip()} ; ce pilote n'est PAS armé (`--verifier` le dit)")
            continue
        print(f"{cle_driver} = {valeur}")
        p = _git(top, "config", "--local", cle_nom, libelle)
        if p.returncode != 0:
            _stderr(f"{quoi}, installation : AVERTISSEMENT — git config --local {cle_nom} : rc={p.returncode} "
                    f"{p.stderr.strip()} ; le pilote est armé (`.driver` posé), seul son libellé manque")
            continue
        print(f"{cle_nom} = {libelle}")
    return 0


def installer(racine: str | None = None, depuis: str | None = None) -> int:
    """`--installer [--depuis <ref>]` : geste du PILOTE. 0 = installé ; 2 = refus nommé, rien d'armé."""
    try:
        return _installer(racine, depuis)
    except (Refus, OSError) as exc:
        print(f"fusion par champ, installation : REFUS — {exc}", file=sys.stderr)
        return 2


_REMEDE_INSTALLER = f"python3 {CHEMIN_SUIVI} --installer [--depuis <ref>] (geste du pilote, depuis un terminal)"


def _dire(statut: str, detail: str, remede: str = _REMEDE_INSTALLER) -> int:
    print(f"{statut} : {detail} — remède : {remede}")
    return 1


def _ligne_index(top: str) -> str:
    """L'état de `merge.cadre-index` en UNE ligne, imprimée AVANT la dernière (que le setup lit) : installé /
    absent / à moitié armé / forme inconnue, puis les contrôles de copie du board (`_controler_copie` : interpréteur
    absent / altérée / périmé). N'entre jamais dans le rc (celui du board, que post-merge lit)."""
    remede = f"remède : {_REMEDE_INSTALLER}"
    p = _git(top, "config", "--local", "--get", CLE_INDEX_DRIVER)
    valeur = p.stdout.rstrip("\n") if p.returncode == 0 else ""
    if not valeur:
        nom = _git(top, "config", "--local", "--get", CLE_INDEX_NOM)
        if nom.returncode == 0 and nom.stdout.strip():
            return (f"index : à moitié armé — {CLE_INDEX_NOM} présent sans {CLE_INDEX_DRIVER} : tout `git merge` qui "
                    f"touche un chemin merge={NOM_INDEX} échoue (rc 128) — remède : git config --local --unset "
                    f"{CLE_INDEX_NOM}, ou {_REMEDE_INSTALLER}")
        return f"index : absent — aucune clé {CLE_INDEX_DRIVER} en config locale — {remede}"
    try:
        jetons = shlex.split(valeur)
    except ValueError:
        jetons = []
    if len(jetons) < 4 or valeur != commande_driver_index(jetons[0].replace("%%", "%"), jetons[3].replace("%%", "%")):
        return f"index : forme inconnue — {CLE_INDEX_DRIVER} n'a pas la forme canonique de ce pilote — {remede}"
    try:
        statut, detail = _controler_copie(top, jetons[0].replace("%%", "%"), jetons[3].replace("%%", "%"))
    except (Refus, OSError) as exc:
        return f"index : invérifiable — {exc} — {remede}"
    if statut != "installé":
        return f"index : {statut} — {detail} — {remede}"
    return f"index : installé — {detail}"


def _controler_copie(top: str, py: str, copie: str) -> tuple[str, str]:
    """Les contrôles d'interpréteur et de copie, COMMUNS aux lignes du board et de l'index (revue T-01M54GECXD, M5) :
    (statut, détail) du premier qui échoue — `interpréteur absent`, `altérée`, `absent`, `périmé` —, sinon
    (`installé`, `<copie> == <suivi> @ <sha>`). `Refus` si HEAD n'est pas un commit."""
    if not (os.path.isabs(py) and os.path.isfile(py) and os.access(py, os.X_OK)):
        # Réserve MAJEURE de l'exec-critic de T-01M4JN4ZSWAX5MGSGQNPPYZG68 (bras I3) : l'interpréteur FIGÉ introuvable
        # ⇒ chaque fusion retombe en silence sur la fusion texte, et --verifier disait « installé ».
        return "interpréteur absent", (f"l'interpréteur figé {py} est introuvable, relatif ou non exécutable : "
                                       "chaque fusion retomberait sur la fusion texte")
    chemin = Path(copie)
    if chemin.is_symlink():
        # Même règle que `.githooks/post-merge` (S-01M5F950RA) : un lien, même vers un contenu identique, n'est pas
        # la copie installée — sinon `--verifier` dirait « installé » sous une alerte inextinguible du hook.
        return "altérée", f"la copie {copie} est un lien symbolique, pas une copie"
    if not chemin.is_file():
        return "absent", f"copie absente : {copie}"
    empreinte = hashlib.sha256(chemin.read_bytes()).hexdigest()
    nom = chemin.name
    annonce = nom[len(_PREFIXE_COPIE):-3] if nom.startswith(_PREFIXE_COPIE) and nom.endswith(".py") else ""
    if empreinte[:16] != annonce:
        return "altérée", f"le contenu de {copie} n'a pas l'empreinte de son nom"
    sha = resoudre_commit("HEAD", top)
    blob = _blob(top, sha)
    if blob is None:
        return "absent", f"HEAD ({sha[:8]}) n'a pas {CHEMIN_SUIVI}"
    if hashlib.sha256(blob).hexdigest() != empreinte:
        return "périmé", (f"la copie diffère du pilote de HEAD ({sha[:8]}) : un commit l'a changé depuis "
                          "l'installation, ou la copie vient d'un --depuis autre que HEAD")
    return "installé", f"{copie} == {CHEMIN_SUIVI} @ {sha[:8]}"


def _verifier(racine: str | None) -> int:
    top = _toplevel(racine)
    index = _ligne_index(top)

    def dire(*a: str) -> int:
        # La ligne `index : …` n'est imprimée qu'à l'issue : une exception en route laisse stdout vide, comme avant.
        print(index)
        return _dire(*a)

    p = _git(top, "config", "--local", "--get", CLE_DRIVER)
    valeur = p.stdout.rstrip("\n") if p.returncode == 0 else ""
    if not valeur:
        nom = _git(top, "config", "--local", "--get", CLE_NOM)
        if nom.returncode == 0 and nom.stdout.strip():
            # N4 : `.name` sans `.driver` n'est pas « absent » — c'est l'état qui CASSE `git merge` (rc 128).
            return dire("à moitié armé", f"{CLE_NOM} présent sans {CLE_DRIVER} : tout `git merge` qui touche un "
                                         f"chemin merge={NOM_PILOTE} échoue (rc 128)",
                        f"git config --local --unset {CLE_NOM}, ou {_REMEDE_INSTALLER}")
        return dire("absent", f"aucune clé {CLE_DRIVER} en config locale")
    try:
        jetons = shlex.split(valeur)
    except ValueError:
        jetons = []
    if len(jetons) < 4:
        return dire("forme inconnue", f"{CLE_DRIVER} n'est pas une commande de ce pilote")
    py, copie = jetons[0].replace("%%", "%"), jetons[3].replace("%%", "%")
    if valeur != commande_driver(py, copie):
        return dire("forme inconnue", f"{CLE_DRIVER} n'a pas la forme canonique de ce pilote")
    statut, detail = _controler_copie(top, py, copie)
    if statut != "installé":
        return dire(statut, detail)
    print(index)
    print(f"installé : {detail}")
    return 0


def verifier(racine: str | None = None) -> int:
    """`--verifier`, lecture seule, contre le blob de HEAD (jamais le worktree) : 0 = installé, 1 sinon (dit)."""
    try:
        return _verifier(racine)
    except (Refus, OSError) as exc:
        print(f"fusion par champ, vérification : impossible — {exc}", file=sys.stderr)
        return 1


# ---------------------------------------------------------------- point d'entrée

def main(argv: list[str]) -> int:
    args = argv[1:]
    if args[:1] in (["-h"], ["--help"]):
        print(__doc__)
        return 0
    if args[:1] == ["--installer"]:
        reste = args[1:]
        if not reste:
            return installer()
        if len(reste) == 2 and reste[0] == "--depuis":
            return installer(depuis=reste[1])
        if len(reste) == 1 and reste[0].startswith("--depuis="):
            return installer(depuis=reste[0].removeprefix("--depuis="))
        _stderr("usage : fusion_enregistrement.py --installer [--depuis <ref>]")
        return 2
    if args == ["--verifier"]:
        return verifier()
    if args[:1] == ["--index"] and len(args) == 5:
        return fusion_index(*args[1:])
    if len(args) != 7:
        _stderr("usage : fusion_enregistrement.py %O %A %B %L %S %X %Y | --index %O %A %B %P | --installer "
                "[--depuis <ref>] | --verifier")
        return 2
    o, a, b, taille, ls, lx, ly = args
    refus: str | None = None
    acteurs = False
    try:
        ligne = ligne_copie_divergente(Path.cwd(), Path(__file__))
        if ligne is not None:
            _stderr(ligne)
        fusion_par_champ(o, a, b)
        return 0
    except Conflit as exc:
        refus = str(exc)
        acteurs = isinstance(exc, ConflitActeur)
        cause = f"conflit sur {refus}"
    except HorsForme as exc:
        cause = f"entrée hors forme ({exc})"
    except Exception as exc:  # noqa: BLE001 — SEUL niveau qui attrape tout : aucune exception ne remonte à git
        # (rc 1 dirait « pilote en panne ») ; ValueError, RecursionError, OSError… rendent la fusion texte.
        cause = f"{type(exc).__name__} ({exc})"
    _stderr(f"fusion par champ : {cause} — fusion texte")
    nous = _instantane(a) if refus is not None else None
    rc = repli(o, a, b, taille, ls, lx, ly)
    if refus is None or rc == 3:
        return rc
    # F1 (S-01M4R8Y48QVARQT92YW6ACD9RG) : un REFUS rend TOUJOURS 3. merge-file à 0 (lignes changées qui ne se touchent
    # pas) : rendu tel quel, le champ ou le groupe refusé serait combiné en silence (`depends_on` +
    # `depends_motif` : un enregistrement que `load` refuse) — %A garde la fusion texte, SANS marqueur. merge-file
    # en ÉCHEC (4) : rendu tel quel, le repli shell de `commande_driver` rejouerait merge-file et pourrait
    # fusionner (NO_GO de l'exec-critic, option a) — %A est remis à « nous ». Un refus des ACTEURS (`ConflitActeur`) à merge-file 0 : la
    # combinaison sans marqueur serait la chimère refusée, qu'un `git add` figerait — %A est remis à « nous » aussi.
    if rc == 0 and acteurs and _remettre(a, nous):
        etat = ("n'a posé aucun marqueur, rendue en CONFLIT quand même : %A garde « nous » ENTIER (jamais un acteur "
                "recomposé), à fusionner à la main avant `git add`")
    elif rc == 0 and acteurs:
        etat = ("n'a posé aucun marqueur, rendue en CONFLIT quand même : %A n'a pas pu être remis à « nous » et "
                "porte la combinaison refusée (acteur recomposé possible), à relire avant `git add`")
    elif rc == 0:
        etat = ("n'a posé aucun marqueur, rendue en CONFLIT quand même : %A porte la combinaison refusée, à relire "
                "avant `git add`")
    elif _remettre(a, nous):
        etat = "a échoué, rendue en CONFLIT quand même : %A garde « nous », intact"
    else:
        etat = "a échoué, rendue en CONFLIT quand même : %A n'a pas pu être remis à « nous », à relire"
    _stderr(f"fusion par champ : conflit sur {refus} — la fusion texte {etat}")
    return 3


if __name__ == "__main__":
    sys.exit(main(sys.argv))
