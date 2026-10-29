#!/usr/bin/env python3
"""CIBLES DE PLAN — verrou B de T-00000654 (STDLIB SEULE au chargement ; `specs` et `tasks` paresseux).

Ce module décide si un plan porte, à chaque étape, au moins une CIBLE parmi
trois : un nom d'invariant de la spec (`cible: « … »`), une question au pilote
(`angle mort: …`), ou une décision pilote existante et PERTINENTE — tracée sur la
tâche, son chantier, une tâche que le plan enrôle, ou la tâche dont la trace
`plan approuvé` a élu le plan (`décision pilote: S-…`). Il
sert les trois points de morsure — `start`, `done`, verdict `plan-critic` — mais
il n'écrit JAMAIS rien et ne prend JAMAIS de verrou.

*** ISOLATION (D6). *** N'importe QUE la stdlib AU CHARGEMENT. Ne prend NI
`board_lock` NI `store_lock`. Sur le chemin `tasks.py` il reçoit le `data` du board
déjà chargé et relit le journal SPECS LUI-MÊME ; sur le chemin `specs.py` la greffe
l'appelle AVANT `store_lock` et il relit le journal LUI-MÊME. DEUX FORMES PAR
MAGASIN (T-01M4KKMY43ZKCW1YD2Y8JX9MKH) : le monolithe SEUL garde sa lecture directe,
inchangée ; dès que la forme enregistrement existe, le journal se lit par `specs.load`,
le board brut par `lire_board_brut` — leurs modules PROPRIÉTAIRES, chargés PARESSEUSEMENT au
premier besoin (`_specs_module`, `_tasks_module` : une instance déjà chargée d'abord,
sinon le frère du dossier de CE fichier, PAR CHEMIN, sous un nom privé), jamais au
chargement : `kickoff_guard` importe ce module à chaque Edit/Write. Ni l'un ni l'autre
n'est pris sous verrou : `specs.load` n'en prend aucun, et la façade `tasks` réutilisée
sous `python3 tasks.py` est `__main__`, dont le compteur de verrou est celui du
processus (D4). La licéité de la lecture hors verrou est MESURÉE dans les écrivains :
remplacement atomique du monolithe et du journal, lot validé du dossier — un lecteur
voit l'état d'avant ou d'après, jamais un état déchiré.

Pourquoi la grammaire de verdict est RECOPIÉE de `night_approve` et jamais
importée (D4) : `night_approve` importe `specs` ET `tasks`, et sous
`python3 tasks.py` cela crée un SECOND module `tasks` dont `_BOARD_LOCK_DEPTH`
ignore le verrou déjà tenu — donc un blocage jusqu'au timeout. La parité est
donc tenue par un TÉMOIN (`parite_grammaire_night_approve`), pas par un import.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any


class CibleError(Exception):
    """Marqueur malformé, ou toute condition fail-closed du verrou de cible."""


# ---------------------------------------------------------------------------
# Emplacements (relatifs à la racine DÉJÀ normalisée que l'appelant fournit).
# ---------------------------------------------------------------------------
MARQUEUR = Path(".agents") / "state" / "gates" / "PLAN_CIBLE_REQUIRED"
# Le DOMICILE du journal (S-01M4KR9W2NSCD5E4T18MW2BESN) : présent, il se lit par `specs.load`, jamais en brut. Sa
# VALEUR est lue par `specs._lecteurs_hors_specs` : nommer le journal lève le refus de `specs.py migrate --apply`
# (T-00001011, réserve C1). Le NOM reste (filets texte : test_direct_mode). Le monolithe SEUL garde sa lecture.
SPECS_REL = Path(".agents") / "state" / "specs" / "SPECS.jsonl"
SPECS_MONOLITHE_REL = Path(".agents") / "state" / "specs" / "SPECS.json"
# La constante du MONOLITHE du board : lu en brut tant qu'aucun dossier d'enregistrements n'existe (`_board_brut`).
BOARD_REL = Path(".agents") / "state" / "board" / "TASKS.json"


# ---------------------------------------------------------------------------
# GRAMMAIRE DE VERDICT — RECOPIÉE VERBATIM de `night_approve` (D4), jamais
# importée. Toute divergence est refusée par le témoin `parite_grammaire_night_approve`.
# ---------------------------------------------------------------------------
PLAN_CRITIC_TITLE = re.compile(r"^\s*plan-critic(?![\w-])", re.IGNORECASE)

NO_GO_PATTERN = r"\bNON?[^A-Z0-9]{0,3}GO\b"
VERDICT_PROBES = (
    ("NO_GO", NO_GO_PATTERN),
    ("FAIL", r"\bFAIL\b"),
    ("GO_AVEC_RESERVES", r"\bGO[\s_-]*AVEC[\s_-]*R[EÉ]SERVES\b"),
    ("CONCERNS", r"\bCONCERNS\b"),
    ("GO", r"\bGO\b"),
    ("PASS", r"\bPASS\b"),
)
ELIGIBLE_STATUSES = ("GO", "GO_AVEC_RESERVES", "PASS", "CONCERNS")

ANCHORED_VERDICT = re.compile(
    r"^\s*PLAN-CRITIC\s*[:\-–—]?\s*"
    r"(?:(?:IT\.?|ITERATION|ITER\.?)\s*\d+(?:\s*/\s*\d+)?|\d+\s*/\s*\d+)?"
    r"\s*[:\-–—]?\s*"
    r"(?P<verdict>"
    r"NON?[^A-Z0-9]{0,3}GO|FAIL|GO[\s_-]*AVEC[\s_-]*R[EÉ]SERVES|CONCERNS|GO|PASS"
    r")(?![\w-])"
)


def verdict_status(title: str) -> str | None:
    """Le verdict lu dans le TITRE, ancré, le PLUS CONSERVATEUR d'abord."""
    upper = unicodedata.normalize("NFC", (title or "").upper())
    m = ANCHORED_VERDICT.match(upper)
    if not m:
        return None
    token = m.group("verdict")
    for status, pattern in VERDICT_PROBES:
        if re.fullmatch(pattern.replace(r"", ""), token):
            return status
    return None


def is_plan_critic_verdict(entry: dict[str, Any]) -> bool:
    return bool(PLAN_CRITIC_TITLE.match(entry.get("title") or ""))


PLAN_FIELD = re.compile(r"plan=(\S+)")
SHA256_FIELD = re.compile(r"(?<![A-Za-z0-9])sha256=([0-9a-fA-F]{64})(?![0-9a-fA-F])")


# ---------------------------------------------------------------------------
# NORMALISATIONS. D9 pour les NOMS d'invariant, D9 bis pour les TITRES de trace.
# ---------------------------------------------------------------------------
def normalise_nom(texte: str) -> str:
    """D9 — espaces repliés, retours à la ligne joints, backticks retirés, des
    deux côtés."""
    return " ".join(texte.replace("`", "").split())


def normalise_titre(titre: str) -> str:
    """D9 bis — `unicodedata.normalize("NFD")`, retrait des combinants,
    `casefold()`, espaces repliés, des deux côtés. Sert à l'appariement EXACT
    d'un titre de trace, jamais à une sous-chaîne.

    Divergence ASSUMÉE et UNIDIRECTIONNELLE avec `night_approve` (qui ne replie
    pas les accents) : `plan_cible` est toujours plus PERMISSIF, jamais plus
    strict. Elle est EXCLUE du périmètre du témoin de parité de grammaire.
    """
    decompose = unicodedata.normalize("NFD", titre or "")
    sans_accent = "".join(c for c in decompose if not unicodedata.combining(c))
    return " ".join(sans_accent.casefold().split())


# ---------------------------------------------------------------------------
# BLOCS DE CODE. Une clôture ``` (ou plus de backticks) ouvre puis ferme un bloc
# ignoré, aussi bien pour le REGISTRE que pour la GRAMMAIRE d'étapes.
# ---------------------------------------------------------------------------
_FENCE = re.compile(r"^\s*(`{3,}|~{3,})")


def lignes_hors_code(texte: str) -> list[str]:
    """Les lignes HORS bloc de code. La clôture se ferme sur une barrière du
    MÊME caractère et d'AU MOINS autant de marques — sinon un ```` de 4 backticks
    se fermerait à tort sur un ``` de 3 imbriqué."""
    lignes = texte.split("\n")
    dehors: list[str] = []
    fence: tuple[str, int] | None = None
    for ligne in lignes:
        m = _FENCE.match(ligne)
        if fence is None:
            if m:
                fence = (m.group(1)[0], len(m.group(1)))
                continue
            dehors.append(ligne)
        else:
            car, longueur = fence
            if m and m.group(1)[0] == car and len(m.group(1)) >= longueur:
                fence = None
            # ligne dans un bloc de code : jamais retenue
    return dehors


# ---------------------------------------------------------------------------
# REGISTRE DES NOMS — chaque `**«` de TOUTE la spec, chaînage `+ « … »`, noms sur
# plusieurs lignes, blocs de code exclus.
# ---------------------------------------------------------------------------
_OUVERTURE = re.compile(r"\*\*«")
_CHAINAGE = re.compile(r"\s*\+\s*«")


def registre_des_noms(spec_text: str) -> list[str]:
    """La liste des noms d'invariant, dans l'ordre du document."""
    texte = "\n".join(lignes_hors_code(spec_text))
    noms: list[str] = []
    for m in _OUVERTURE.finditer(texte):
        debut = m.end()
        fin = texte.find("»", debut)
        if fin == -1:
            continue
        noms.append(normalise_nom(texte[debut:fin]))
        # CHAÎNAGE : `**« A » + « B » + « C »` — chaque maillon est un nom.
        curseur = fin + 1
        while True:
            mc = _CHAINAGE.match(texte, curseur)
            if not mc:
                break
            debut2 = mc.end()
            fin2 = texte.find("»", debut2)
            if fin2 == -1:
                break
            noms.append(normalise_nom(texte[debut2:fin2]))
            curseur = fin2 + 1
    return noms


def registre_depuis_fichier(spec_path: Path) -> set[str]:
    return set(registre_des_noms(spec_path.read_text(encoding="utf-8")))


# ---------------------------------------------------------------------------
# GRAMMAIRE D'ÉTAPES — titre `### Étape X` prioritaire, sinon items numérotés de
# `## Steps`. Blocs de code ignorés.
# ---------------------------------------------------------------------------
_ETAPE_TITRE = re.compile(r"^###\s+Étape\b")
_SECTION_2 = re.compile(r"^##\s")
_STEPS_HEAD = re.compile(r"^##\s+(?:\d+\.\s*)?Steps\b")
_ITEM_NUM = re.compile(r"^(\d+)\.\s")
_SEP_TITRE = re.compile(r"\s+[—–-]\s+")


def _nom_du_titre_etape(ligne: str) -> str:
    """`### Étape A — citations…` → `Étape A`."""
    corps = ligne.lstrip("#").strip()
    return _SEP_TITRE.split(corps, 1)[0].strip()


def etapes_du_plan(plan_text: str) -> list[tuple[str, str]]:
    """Liste de `(nom, corps)`. `### Étape X` prioritaire ; sinon items
    numérotés de `## Steps`. `[]` si le plan n'a AUCUNE étape (refusé en amont,
    jamais admis par `all([])`)."""
    lignes = lignes_hors_code(plan_text)
    titres = [i for i, l in enumerate(lignes) if _ETAPE_TITRE.match(l)]
    if titres:
        etapes: list[tuple[str, str]] = []
        for k, i in enumerate(titres):
            suivant = titres[k + 1] if k + 1 < len(titres) else len(lignes)
            # une section `##` referme aussi une étape
            for j in range(i + 1, suivant):
                if _SECTION_2.match(lignes[j]):
                    suivant = j
                    break
            nom = _nom_du_titre_etape(lignes[i])
            corps = "\n".join(lignes[i + 1:suivant])
            etapes.append((nom, corps))
        return etapes

    # Repli : items numérotés de `## Steps`.
    debut = next((i for i, l in enumerate(lignes) if _STEPS_HEAD.match(l)), None)
    if debut is None:
        return []
    fin_section = next(
        (i for i in range(debut + 1, len(lignes)) if _SECTION_2.match(lignes[i])),
        len(lignes),
    )
    items = [i for i in range(debut + 1, fin_section) if _ITEM_NUM.match(lignes[i])]
    etapes = []
    for k, i in enumerate(items):
        fin = items[k + 1] if k + 1 < len(items) else fin_section
        num = _ITEM_NUM.match(lignes[i]).group(1)
        resume = lignes[i][len(num) + 1:].strip()
        nom = f"étape {num} : {resume}" if resume else f"étape {num}"
        corps = "\n".join(lignes[i:fin])
        etapes.append((nom, corps))
    return etapes


# ---------------------------------------------------------------------------
# VALEURS D'ÉTAPE — au moins une des trois.
# ---------------------------------------------------------------------------
# BORNÉ (revue sécurité T-00000654, finding HIGH) : `.+?` rendait le motif
# QUADRATIQUE — mesuré 3,5 s sur 60 Ko de `cible : «` non fermés, et plus de
# 20 s sur 500 Ko, le tout sous `board_lock`. Ce qui rend le parcours LINÉAIRE
# est la LONGUEUR bornée `{1,300}?`, PAS l'exclusion du saut de ligne : la classe
# exclut `»` seul, jamais `\n`, pour qu'un nom d'invariant écrit sur DEUX lignes
# vaille cible (D9 replie déjà les retours à la ligne « des deux côtés »).
# Mesuré : `[^»]{1,300}?` = 0,315 s contre 0,452 s pour `[^»\n]{1,300}?` sur
# 488 Ko. Mutation qui rougit le témoin anti-ReDoS : rendre la classe générique
# (`(.+?)`), la borne étant retirée.
_CIBLE = re.compile(r"cible\s*:\s*«\s*([^»]{1,300}?)\s*»")
_ANGLE = re.compile(r"angle mort\s*:\s*(\S.*)")
# La S-id citée : `S-<ULID>` EN PREMIER, bornée à droite, puis l'ancienne
# `S-<chiffres>` (T-00001040 ; témoins : test_plan_cible_ulid.py). Ses lecteurs —
# `_etape_valide`, `decisions_pertinentes`, `decisions_ecartees`, `cible_check` —
# comparent la chaîne EXACTE à l'id de l'entrée SPECS.
_DECISION = re.compile(r"décision pilote\s*:\s*(S-(?:[0-9A-HJKMNP-TV-Z]{26}(?![0-9A-Za-z])|\d+))")


def _etape_valide(corps: str, registre: set[str], decisions: set[str]) -> bool:
    """Une étape est valide si elle porte AU MOINS une valeur valide."""
    for m in _CIBLE.finditer(corps):
        if normalise_nom(m.group(1)) in registre:
            return True
    for m in _ANGLE.finditer(corps):
        if m.group(1).strip():
            return True
    for m in _DECISION.finditer(corps):
        if m.group(1) in decisions:
            return True
    return False


def etapes_fautives(
    plan_text: str, registre: set[str], decisions: set[str]
) -> list[str]:
    """Les NOMS des étapes sans cible valide. Un plan SANS étape est fautif en
    bloc — `all([])` ne l'admet jamais."""
    etapes = etapes_du_plan(plan_text)
    if not etapes:
        return ["(aucune étape détectée — le plan doit porter des titres "
                "`### Étape X`, ou à défaut une section `## Steps` à items "
                "numérotés `1.`, `2.`…)"]
    return [nom for nom, corps in etapes if not _etape_valide(corps, registre, decisions)]


# ---------------------------------------------------------------------------
# LES MODULES PROPRIÉTAIRES, chargés PARESSEUSEMENT (T-01M4KKMY43ZKCW1YD2Y8JX9MKH,
# réserves R1 et R2 au mandat) — rien au chargement de CE module.
# ---------------------------------------------------------------------------
_SPECS_MOD: Any = None
_TASKS_MOD: Any = None
_SPECS_NOM = "_cadre_specs_plan_cible"
_TASKS_NOM = "_cadre_tasks_plan_cible"


def _charger_frere(nom: str, fichier: str) -> Any:
    """Le frère `fichier` du dossier de CE fichier, chargé PAR CHEMIN sous le nom privé `nom`, enregistré dans
    `sys.modules` AVANT son exécution (T-00000134) et retiré s'il échoue. Absent ⇒ `FileNotFoundError`."""
    import importlib.util

    chemin = Path(__file__).resolve().with_name(fichier)
    if not chemin.is_file():
        raise FileNotFoundError(f"{chemin} : module frère ABSENT")
    spec = importlib.util.spec_from_file_location(nom, chemin)
    if spec is None or spec.loader is None:
        raise FileNotFoundError(f"{chemin} : module frère illisible")
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(nom, None)
        raise
    return module


def _specs_module() -> Any:
    """`specs` (R1) : `sys.modules["specs"]` s'il existe et porte `load` — l'instance de `kickoff_guard`, de
    `night_approve` ou d'un banc —, sinon `specs.py` du dossier de CE fichier, par chemin. Cache au niveau module."""
    global _SPECS_MOD
    if _SPECS_MOD is None:
        existant = sys.modules.get("specs")
        if existant is not None and callable(getattr(existant, "load", None)) \
                and isinstance(getattr(existant, "SpecsError", None), type):
            _SPECS_MOD = existant
        else:
            _SPECS_MOD = _charger_frere(_SPECS_NOM, "specs.py")
    return _SPECS_MOD


def _tasks_module() -> Any:
    """La façade `tasks` (R2) : une instance DÉJÀ chargée qui porte `lire_board_brut` — `__main__` d'abord (sous
    `python3 tasks.py` c'est ELLE qui tient le verrou du processus, D4), puis `sys.modules["tasks"]` —, sinon
    `tasks.py` du dossier de CE fichier, par chemin. Cache au niveau module."""
    global _TASKS_MOD
    if _TASKS_MOD is None:
        for nom in ("__main__", "tasks"):
            existant = sys.modules.get(nom)
            if existant is not None and callable(getattr(existant, "lire_board_brut", None)):
                _TASKS_MOD = existant
                break
        else:
            _TASKS_MOD = _charger_frere(_TASKS_NOM, "tasks.py")
    return _TASKS_MOD


def _board_brut(root: str | Path) -> dict[str, Any] | None:
    """Le board BRUT, HORS verrou, quelle que soit sa forme, ou `None` s'il est ABSENT (aucune forme : rien à armer).
    Sans dossier d'enregistrements (`board/tasks/`, `board/epics/`) : `TASKS.json` lu en JSON, sans charger la façade
    (l'adoptant, nos copies partielles). Sinon `lire_board_brut` (SYM-17341) de la façade `tasks`.

    FAIL-CLOSED (avis sécurité medium 1 et 2 de T-01M4KKMY43ZKCW1YD2Y8JX9MKH, passe de correction F5) : DEUX FORMES
    (une vieille branche ramène `TASKS.json` à côté du dossier) ⇒ `CibleError` nommée, comme `tasks.load` et
    plan_pool ; un board PRÉSENT mais ILLISIBLE (JSON corrompu ou hors forme, enregistrement corrompu, lien, id
    décalé : `BoardError`, `OSError`, `ValueError`, façade introuvable) ⇒ `CibleError` nommée. Les lire « monolithe »
    ou « absent » rendait `chantier_de_tache` vide et la jambe INERTE en silence. Tous les appelants tournent sous un
    marqueur ARMÉ (`_arme_pour_tache` le lit d'abord ; `cible_check` n'y vient que sous un chantier nommé) ; `specs.py`
    convertit la `CibleError` en refus rc 2."""
    board = Path(root) / BOARD_REL.parent
    if not any((board / c).is_dir() or (board / c).is_symlink() for c in ("tasks", "epics")):
        chemin = Path(root) / BOARD_REL
        try:
            data = json.loads(chemin.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as exc:  # ValueError ⊃ JSONDecodeError, UnicodeDecodeError
            raise CibleError(f"{chemin} présent mais illisible ({exc}) — le lire « absent » désarmerait la garde de "
                             f"cible en silence. Refus fail-closed.") from exc
        if not isinstance(data, dict):
            raise CibleError(f"{chemin} hors forme (racine {type(data).__name__}, objet attendu). Refus fail-closed.")
        return data
    try:
        tasks = _tasks_module()
    except (OSError, ImportError) as exc:
        raise CibleError(f"{board} : dossier d'enregistrements présent, mais la façade `tasks.py` est introuvable "
                         f"({exc}). Refus fail-closed.") from exc
    try:
        forme = tasks.store_form(root)
        data = tasks.lire_board_brut(root) if forme in ("dossier", "monolithe") else None
    except (tasks.BoardError, OSError, ValueError) as exc:
        raise CibleError(f"{board} illisible ({exc}) — le lire « absent » désarmerait la garde de cible en silence. "
                         f"Refus fail-closed.") from exc
    if forme == "absent":
        return None
    if forme == "les deux":
        raise CibleError(f"{board} en DEUX FORMES ({BOARD_REL.name} à côté de `tasks/`) : une vieille branche a ramené "
                         f"le monolithe. Remède : le retirer après avoir vérifié qu'il ne porte rien de neuf. Refus "
                         f"fail-closed.")
    if not isinstance(data, dict):
        raise CibleError(f"{board} hors forme (racine {type(data).__name__}, objet attendu). Refus fail-closed.")
    return data


# ---------------------------------------------------------------------------
# LE JOURNAL SPECS — `SPECS.jsonl` par `specs.load` ; le monolithe seul, lu
# DIRECTEMENT comme avant la bascule. Hors verrou (écritures atomiques).
# ---------------------------------------------------------------------------
def entrees_specs(root: str | Path) -> list[dict[str, Any]]:
    """Les entrées du journal SPECS, ou `[]` si AUCUNE forme n'existe (un store frais n'a légitimement aucune
    trace). `SPECS.jsonl` PRÉSENT ⇒ `specs.load` (module chargé paresseusement, R1), qui refuse aussi les DEUX formes
    (une vieille branche a ramené `SPECS.json`) ; le monolithe SEUL ⇒ sa lecture d'avant la bascule, octet pour
    octet (`_entrees_monolithe` : contrat et messages de l'adoptant inchangés). Un journal PRÉSENT et illisible,
    CORROMPU ou en DEUX FORMES lève `CibleError` FAIL-CLOSED (fable C6) qui nomme le fichier : le rendre `[]`
    produirait au `done` un diagnostic FAUX « aucune trace » et invaliderait toute `décision pilote: S-…` citée en
    cible. Le `SpecsError` est CONVERTI, jamais avalé ; `OSError`, `ValueError` et un `specs.py` introuvable aussi."""
    journal = Path(root) / SPECS_REL
    if not journal.exists():
        return _entrees_monolithe(Path(root) / SPECS_MONOLITHE_REL)
    try:
        specs = _specs_module()
    except (OSError, ImportError) as exc:
        raise CibleError(
            f"{journal} présent mais illisible : son module `specs.py` est introuvable ({exc}) — lire « aucune "
            f"trace » invaliderait toute décision pilote citée. Refus fail-closed."
        ) from exc
    try:
        data = specs.load(root)
    except (specs.SpecsError, OSError, ValueError) as exc:
        raise CibleError(
            f"{journal} illisible, corrompu ou en deux formes ({exc}) — le rendre vide produirait au `done` un "
            f"diagnostic FAUX « aucune trace ». Refus fail-closed."
        ) from exc
    return list(data.get("entries") or [])


def _entrees_monolithe(chemin: Path) -> list[dict[str, Any]]:
    """`SPECS.json` lu DIRECTEMENT — le corps d'`entrees_specs` d'avant la bascule, inchangé. Absent ⇒ `[]`.

    Un fichier non UTF-8 lève `UnicodeDecodeError`, une `ValueError` que
    `except OSError` laissait filer : TRACE en rc 1 par `tasks.py cible-check`,
    lue « étapes sans cible » (critic-opus F4, T-00000814). Même refus nommé."""
    try:
        brut = chemin.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except (OSError, UnicodeDecodeError) as exc:
        raise CibleError(
            f"SPECS.json présent mais illisible ({exc}) — le rendre vide ferait "
            f"lire « aucune trace » et invaliderait toute décision pilote citée. "
            f"Refus fail-closed."
        ) from exc
    try:
        data = json.loads(brut)
    except ValueError as exc:
        raise CibleError(
            f"SPECS.json corrompu ({exc}) — un journal illisible rendu vide "
            f"produirait au `done` un diagnostic FAUX « aucune trace ». Refus "
            f"fail-closed."
        ) from exc
    if not isinstance(data, dict):
        raise CibleError(
            "SPECS.json corrompu — sa racine n'est pas un objet JSON. Refus "
            "fail-closed."
        )
    entrees = data.get("entries")
    if entrees is None:
        return []
    if not isinstance(entrees, list):
        raise CibleError(
            "SPECS.json corrompu — `entries` n'est pas une liste. Refus "
            "fail-closed."
        )
    for i, e in enumerate(entrees):
        if not isinstance(e, dict):
            raise CibleError(
                f"SPECS.json corrompu — l'entrée #{i} n'est pas un objet "
                f"(type {type(e).__name__}). Un `.get()` sur elle plus loin "
                f"lèverait un AttributeError muet : refus nommé fail-closed."
            )
    return entrees


def decisions_existantes(entrees: list[dict[str, Any]]) -> set[str]:
    """Les ids des entrées `kind=decision`. Un id de tâche `T-…` n'y figure
    jamais, et une entrée d'un autre `kind` non plus."""
    return {e["id"] for e in entrees if e.get("kind") == "decision" and e.get("id")}


# ---------------------------------------------------------------------------
# GRAPHIE DES IDS (T-00001160, décision pilote S-00004060). `specs.py add`
# accepte tout `T-\d+` : `T-012`, `T-12` et `T-00000012` désignent la MÊME tâche
# et cohabitent au journal (mesuré : 9 des 184 entrées de T-012 sont sous
# `T-00000012`). Comparés à l'égalité exacte, R1/R2 ignoraient une trace sous
# l'autre graphie et le refus disait FAUX « aucune trace d'approbation ». Toute
# comparaison d'un id de tâche venu de SPECS passe donc par `cle_de_tache`.
# CHIFFRES ASCII SEULS (avis sécurité S-00004067 n° 1) : `\d` acceptait les
# chiffres Unicode, et `int()` les convertit — `T-١٢` et `T-１２` valaient `T-12`.
# ---------------------------------------------------------------------------
_ID_ULID = re.compile(r"T-[0-9A-HJKMNP-TV-Z]{26}")
_ID_LEGACY = re.compile(r"[Tt]-0*([0-9]{1,15})")


def cle_de_tache(ref: Any) -> str | None:
    """La clé de comparaison d'un id de tâche : `T-<valeur>` pour un id legacy
    (`T-012` ≡ `T-00000012` ≡ `t-12`), l'id TEL QUEL pour un `T-<ULID>`, `None`
    pour tout le reste — une chaîne non conforme ne vaut AUCUNE tâche, pas même
    elle-même. RECOPIÉ de la tolérance en lecture de `tasks_requetes.resolve_id`
    (D6 : jamais importé), préfixe `T-` exigé. Le motif ULID passe EN PREMIER :
    `T-` + 24 zéros + `12` est un ULID, que le motif legacy lirait `T-12`. Le
    board refuse deux ids legacy de même valeur : l'équivalence ne confond
    jamais deux tâches."""
    brut = ref.strip() if isinstance(ref, str) else ""
    if _ID_ULID.fullmatch(brut):
        return brut
    m = _ID_LEGACY.fullmatch(brut)
    return f"T-{int(m.group(1))}" if m else None


def forme_longue(cle: str) -> str:
    """La graphie CANONIQUE d'une clé rendue par `cle_de_tache` : `T-` + 8
    chiffres au moins pour un id legacy (le format de `tasks.py new`), l'ULID
    tel quel. C'est sous elle qu'un roster nomme une tâche ABSENTE du board
    (S-00004059 : la forme courte n'enrôle pas), quelle que soit la graphie de
    sa trace. Le motif ULID passe EN PREMIER, comme dans `cle_de_tache`."""
    if _ID_ULID.fullmatch(cle):
        return cle
    m = _ID_LEGACY.fullmatch(cle)
    return f"T-{int(m.group(1)):08d}" if m else cle


def meme_tache(a: Any, b: Any) -> bool:
    """Vrai si `a` et `b` sont deux graphies de la MÊME tâche ; jamais pour deux
    valeurs non conformes (deux `None` ne relient rien)."""
    cle = cle_de_tache(a)
    return cle is not None and cle == cle_de_tache(b)


def index_par_tache(entrees: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Les entrées SPECS groupées par la clé de leur `task`, en UNE passe et dans
    l'ordre du journal ; une entrée à `task` non conforme n'est rangée nulle
    part. S'interroge par `entrees_de(index, tid)`."""
    index: dict[str, list[dict[str, Any]]] = {}
    for e in entrees:
        cle = cle_de_tache(e.get("task"))
        if cle is not None:
            index.setdefault(cle, []).append(e)
    return index


def entrees_de(index: dict[str, list[dict[str, Any]]], tid: Any) -> list[dict[str, Any]]:
    """Les entrées de `tid`, toutes graphies de son id confondues."""
    cle = cle_de_tache(tid)
    return index.get(cle, []) if cle is not None else []


def chantier_de_tache(root: str | Path, tid: str) -> str | None:
    """Le chantier de la tâche `tid`, lu dans le board BRUT HORS verrou
    (`_board_brut` : monolithe OU dossier), ou `None` si la tâche est ABSENTE du
    board ou le board absent (jamais une chaîne vide par erreur) ; un board en deux
    formes ou illisible lève `CibleError` (passe de correction F5). Lecture licite
    hors verrou : remplacement atomique du monolithe, lot validé du dossier — un
    lecteur voit l'ancien board ENTIER ou le nouveau, jamais un board déchiré.
    Sert la jambe verdict, appelée par `specs.py`, qui n'a pas le `data` du board
    sous la main : sans cette lecture, la garde ignorerait la portée `chantier=`
    et mordrait sur les verdicts d'AUTRES chantiers, ce que la phrase canonique
    (« tâche hors chantier : rien ne change ») interdit.

    `tid` vient ici de `specs.py add --task`, donc sous TOUTE graphie `T-\\d+` :
    comparé à l'égalité exacte, `--task T-814` rendait INERTE la jambe verdict
    de T-00000814 (T-00001160, trouvé au balayage) — d'où `meme_tache`."""
    data = _board_brut(root)
    if data is None:
        return None
    for t in data.get("tasks", []):
        if isinstance(t, dict) and meme_tache(t.get("id"), tid):
            return t.get("chantier") or ""
    return None


# ---------------------------------------------------------------------------
# CHEMIN SÛR — RECOPIÉ LIGNE À LIGNE de `plan_pool.py:411-449`, `resolved_root`
# compris. Absent ou hors racine = REFUS.
# ---------------------------------------------------------------------------
def chemin_de_plan_sur(root: str | Path, brut: str) -> Path | None:
    """Le chemin résolu si sûr, `None` sinon (absolu, `..`, mauvais suffixe,
    fichier absent ou hors racine)."""
    root = Path(root)
    relative_plan = Path(brut.rstrip(".,;:)»\"'"))
    if (relative_plan.is_absolute()
            or ".." in relative_plan.parts
            or relative_plan.suffix.lower() != ".md"):
        return None
    try:
        resolved_root = root.resolve()
        resolved_plan = (root / relative_plan).resolve(strict=True)
        resolved_plan.relative_to(resolved_root)
        # DIVERGENCE ASSUMÉE de `plan_pool.py` (fable C5, mesuré) : un `plan=`
        # qui résout sur un RÉPERTOIRE de suffixe `.md` passait les contrôles,
        # puis `read_bytes`/`read_text` levait un `IsADirectoryError` en
        # TRACEBACK. On le rejette ICI pour que tous les bras (verdict, done,
        # registre) retombent sur un refus NOMMÉ au lieu d'une trace Python.
        if not resolved_plan.is_file():
            return None
    except (OSError, ValueError):
        return None
    return resolved_plan


def _empreinte_unique(texte: str) -> str | None:
    """La sha256 citée, ou `None` si absente OU ambiguë (deux valeurs)."""
    trouvees = {m.lower() for m in SHA256_FIELD.findall(texte or "")}
    if len(trouvees) != 1:
        return None
    return trouvees.pop()


def _plan_de_trace(root: str | Path, texte: str) -> Path | None:
    """Le plan CITÉ par une trace, VALIDÉ : `plan=` sûr, fichier sous la racine,
    empreinte sha256 recalculée identique. `None` sinon (D8)."""
    mp = PLAN_FIELD.search(texte or "")
    empreinte = _empreinte_unique(texte or "")
    if not mp or not empreinte:
        return None
    chemin = chemin_de_plan_sur(root, mp.group(1))
    if chemin is None:
        return None
    if hashlib.sha256(chemin.read_bytes()).hexdigest() != empreinte:
        return None
    return chemin


# ---------------------------------------------------------------------------
# TRACES D'APPROBATION. (a) décisions `plan approuvé` / `night-eligible: approved`
# ; (b) accessoirement les verdicts plan-critic favorables portant `plan=` ET
# `sha256=`.
# ---------------------------------------------------------------------------
TITRES_APPROBATION = frozenset(
    {normalise_titre("plan approuvé"), normalise_titre("night-eligible: approved")}
)


_SID_ULID = re.compile(r"S-([0-9A-HJKMNP-TV-Z]{26})")


def _clef_sid(sid: str) -> tuple[int, int | str]:
    """Clé d'ÉLECTION à deux étages d'une S-id de trace (T-00001040, M10) :
    `(1, corps)` pour un `S-<ULID>` — APRÈS tout ancien, ordonné par le temps entre
    ULID (Crockford est monotone en ASCII) ; `(0, n)` pour l'ancienne forme (ses
    chiffres de queue, lecture d'avant) ; `(-1, 0)` pour une S-id illisible, jamais
    élue devant une lisible. Les deux étages ne comparent jamais un `int` à un `str`."""
    u = _SID_ULID.fullmatch(sid or "")
    if u:
        return (1, u.group(1))
    m = re.search(r"(\d+)\Z", sid or "")
    return (0, int(m.group(1))) if m else (-1, 0)


def _est_trace_dapprobation(entry: dict[str, Any]) -> bool:
    kind = entry.get("kind")
    if kind == "decision":
        return normalise_titre(entry.get("title") or "") in TITRES_APPROBATION
    if kind == "verdict":
        return (is_plan_critic_verdict(entry)
                and verdict_status(entry.get("title") or "") in ELIGIBLE_STATUSES)
    return False


def _meilleure_trace(
    root: str | Path,
    candidats: list[dict[str, Any]],
    garde: Any = None,
) -> tuple[Path, str] | None:
    """`(chemin, S-id)` de la plus grande S-id VALIDE parmi les candidats (traces
    d'approbation dont le plan cité est sûr, existant et d'empreinte identique),
    ou `None`. La S-id VOYAGE avec le chemin pour que l'emprunt écrit au board
    NOMME la trace qui l'a autorisé (`[cible relevée sur T-… : <plan> (S-…)]`).

    `garde` est un prédicat OPTIONNEL `(chemin) -> bool` appliqué JUSTE APRÈS la
    résolution du chemin : une trace dont le plan ne passe pas la garde est
    ÉCARTÉE DU VIVIER (`continue`), jamais post-contrôlée après l'élection (À
    CORRIGER 1, mesuré : sans ce filtre, un plan de lot RÉCENT non enrôlant
    masquait un plan plus ANCIEN qui enrôlait, produisant un faux refus)."""
    meilleure: tuple[tuple[int, int | str], Path, str] | None = None
    for e in candidats:
        if not _est_trace_dapprobation(e):
            continue
        chemin = _plan_de_trace(root, e.get("text", ""))
        if chemin is None:
            continue
        if garde is not None and not garde(chemin):
            continue
        n = _clef_sid(e.get("id", ""))
        if meilleure is None or n > meilleure[0]:
            meilleure = (n, chemin, e.get("id", ""))
    return (meilleure[1], meilleure[2]) if meilleure else None


# ---------------------------------------------------------------------------
# ENRÔLEMENT — RECOPIÉ de `night_approve.py:243-262` (jamais importé). Ligne 1 et
# la PREMIÈRE ligne `^Tâches\s*:`, rien d'autre.
# ---------------------------------------------------------------------------
_ROSTER_HEAD = re.compile(r"^\s*Tâches\s*:", re.IGNORECASE)
# `T-<ULID>` EN PREMIER, borné à droite, puis l'ancien `T-<chiffres>` (T-00001040) :
# chez l'adoptant (`chantier=*`) une tâche neuve s'enrôle dès sa première ligne.
_TASK_PATTERN = re.compile(r"T-(?:[0-9A-HJKMNP-TV-Z]{26}(?![0-9A-Za-z])|\d+)")


def enrolling_line(plan_text: str, task_id: str) -> bool:
    """Vrai si le plan ENRÔLE la tâche : son id en ligne 1 ou dans la PREMIÈRE
    ligne `^Tâches\\s*:`, jamais par une sous-chaîne sur tout le fichier."""
    lignes = plan_text.splitlines()
    a_lire: list[str] = []
    if lignes:
        a_lire.append(lignes[0])
    for ligne in lignes:
        if _ROSTER_HEAD.match(ligne):
            a_lire.append(ligne)
            break
    return any(task_id in _TASK_PATTERN.findall(ligne) for ligne in a_lire)


# ---------------------------------------------------------------------------
# PERTINENCE DE LA 3e VALEUR (T-00000909, décision pilote S-00004057, option B).
# Mesuré à la base : `décision pilote: S-…` validait l'étape dès que la décision
# EXISTAIT, même tracée sur une tâche d'un AUTRE chantier (sonde : rc 0). Elle ne
# vaut cible que si elle porte sur la tâche contrôlée, sur une tâche de son
# chantier NOMMÉ, ou sur une tâche que le plan ENRÔLE — `enrolling_line` TELLE
# QUELLE, donc roster en ids complets : la forme courte n'enrôle pas
# (S-00004059). Le roster est auto-déclaratif : la règle empêche d'OUBLIER, pas
# de TRICHER.
# EXTENSION A (décision pilote S-00004069, constat F3 de critic-opus) : vaut
# aussi la décision du PROPRIÉTAIRE de la trace `plan approuvé` qui a élu le
# plan — `tid` en R1, le slot en R2. Mesuré : sous `chantier=*`, aucune tâche
# n'a de chantier ; R2 tient "" pour un chantier commun quand la branche
# chantier exige un nom, et la décision du slot, pertinente à son `start`,
# refusait le `done` de la sous-tâche que son plan de lot enrôle (rc 2).
# ---------------------------------------------------------------------------
def taches_du_board(root: str | Path, data: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Les tâches du `data` fourni, sinon du board BRUT relu HORS verrou (`_board_brut`,
    même licéité que `chantier_de_tache`). Absent : `[]`, et la pertinence se
    replie sur les seules décisions de la tâche — plus strict, jamais plus large.
    Deux formes ou illisible : `CibleError` (passe de correction F5)."""
    if data is None:
        data = _board_brut(root)
        if data is None:
            return []
    taches = data.get("tasks", []) if isinstance(data, dict) else []
    return [t for t in taches if isinstance(t, dict)] if isinstance(taches, list) else []


def decisions_pertinentes(
    entrees: list[dict[str, Any]],
    taches: list[dict[str, Any]],
    plan_text: str,
    *,
    tid: str | None = None,
    chantier: str | None = None,
    proprietaire: str | None = None,
) -> set[str]:
    """Parmi les décisions que `plan_text` CITE (seules à compter pour
    `etapes_fautives`), les `kind=decision` dont la tâche, comparée par
    `cle_de_tache`, est `tid` ; OU `proprietaire`, la tâche dont la trace `plan
    approuvé` a élu le plan (S-00004069 ; `None` : ne relie rien) ; OU une tâche
    du board au chantier `chantier` (par défaut celui de `tid` ; vide ou
    inconnu : ne relie rien) ; OU une tâche que le plan ENRÔLE. Une tâche
    absente du board (close puis purgée) n'est d'aucun chantier mais reste
    ENRÔLABLE (critic-opus F5) : le roster la nomme sous sa `forme_longue`,
    jamais sous la graphie brute de sa trace — sinon une trace `T-500`
    enrôlerait par un roster `T-500`, la forme courte que S-00004059 refuse."""
    citees = set(_DECISION.findall(plan_text))
    par_cle: dict[str, dict[str, Any]] = {}
    for t in taches:
        cle = cle_de_tache(t.get("id"))
        if cle is not None:
            par_cle[cle] = t
    moi = cle_de_tache(tid)
    # `cle` n'est jamais `None` à la comparaison : un propriétaire absent ou non
    # conforme (`cle_de_tache` rend `None`) ne relie donc aucune décision.
    elu = cle_de_tache(proprietaire)
    if chantier is None:
        chantier = _chantier_de(par_cle[moi]) if moi in par_cle else ""
    enrolee: dict[str, bool] = {}
    pertinentes: set[str] = set()
    for e in entrees:
        sid, cle = e.get("id"), cle_de_tache(e.get("task"))
        if e.get("kind") != "decision" or sid not in citees or cle is None:
            continue
        tache = par_cle.get(cle)
        if cle == moi or cle == elu or (tache is not None and chantier
                                        and _chantier_de(tache) == chantier):
            pertinentes.add(sid)
            continue
        if cle not in enrolee:
            nom = (tache.get("id") or "") if tache is not None else forme_longue(cle)
            enrolee[cle] = enrolling_line(plan_text, nom)
        if enrolee.get(cle):
            pertinentes.add(sid)
    return pertinentes


def decisions_ecartees(
    entrees: list[dict[str, Any]], plan_text: str, pertinentes: set[str]
) -> list[str]:
    """Les décisions que le plan cite HORS code qui EXISTENT mais ne sont pas
    pertinentes — nommées au refus, sinon l'auteur lirait « ma décision existe ».
    Un seul calcul pour les quatre surfaces (start, done, verdict, cible-check)."""
    citees = set(_DECISION.findall("\n".join(lignes_hors_code(plan_text))))
    return sorted(citees & (decisions_existantes(entrees) - pertinentes))


def ligne_ecartees(ecartees: list[str] | None, porteurs: str) -> str:
    """La ligne qui nomme les décisions écartées (`""` s'il n'y en a pas) ;
    `porteurs` dit sur quoi elles auraient dû porter, avant l'enrôlement."""
    if not ecartees:
        return ""
    return (f"Décisions citées qui existent mais ne portent ni sur {porteurs}, "
            f"ni sur une tâche que le plan enrôle : {', '.join(ecartees)}.\n")


def controle_des_etapes(
    root: str | Path,
    tid: str,
    plan_text: str,
    registre: set[str],
    data: dict[str, Any] | None = None,
    *,
    proprietaire: str | None = None,
) -> tuple[list[str], list[str]]:
    """`(fautives, écartées)` pour `tid` : les étapes sans cible valide, et les
    décisions citées qui EXISTENT mais ne sont pas pertinentes — nommées au
    refus, sinon l'auteur lirait « ma décision existe ». `proprietaire` : la
    tâche dont la trace a élu le plan (rendue par `_resoudre`), `None` hors
    résolveur (jambe verdict)."""
    entrees = entrees_specs(root)
    pertinentes = decisions_pertinentes(
        entrees, taches_du_board(root, data), plan_text, tid=tid,
        proprietaire=proprietaire)
    fautives = etapes_fautives(plan_text, registre, pertinentes)
    if not fautives:
        return ([], [])
    return (fautives, decisions_ecartees(entrees, plan_text, pertinentes))


# ---------------------------------------------------------------------------
# RÉSOLVEUR D8 — R1 (tâche), R2 (slot, `done` seulement), R3 (refus).
# ---------------------------------------------------------------------------
def _chantier_de(task: dict[str, Any]) -> str:
    return task.get("chantier") or ""


def _chantiers_du_board(root: str | Path) -> set[str] | None:
    """Les chantiers NOMMÉS au board BRUT (`_board_brut`), ou `None` si le board est
    absent — on ne conclut alors rien. Deux formes ou illisible : `CibleError`
    (passe de correction F5), jamais un `None` qui tairait l'avertissement."""
    data = _board_brut(root)
    if data is None:
        return None
    return {
        t.get("chantier") or ""
        for t in data.get("tasks", [])
        if isinstance(t, dict)
    }


def avertissement_chantier(chantier: str, chantiers: set[str] | None) -> str | None:
    """UN `chantier=` QUI NE NOMME AUCUNE TÂCHE DU BOARD EST UN DÉSARMEMENT
    SILENCIEUX (revue de clôture T-00000654, T1). Mesuré avant d'être corrigé :
    `chantier=refonte-packaging # armé le 18/09` et `chantier=refonte-Packaging`
    laissaient `done T-00000529` passer rc 0, SANS marque `[SANS CIBLE]` — la
    comparaison `_chantier_de(tache) != chantier` était fausse pour TOUTES les
    tâches, donc la garde se taisait partout. Un commentaire en fin de ligne ou
    une majuscule suffisait, et le pilote croyait la garde armée.

    ON AVERTIT, ON NE REFUSE PAS — et cette borne est MESURÉE, pas choisie par
    prudence. Le refus fail-closed a été écrit d'abord, puis RETIRÉ : il rougit
    `test_tache_hors_chantier_inerte`, `test_done_hors_chantier_inerte` et
    `test_verdict_hors_chantier_inerte`, qui tiennent la clause canonique de la
    spec — « tâche hors chantier : rien ne change ». Refuser board-entier ferait
    qu'un marqueur mal orthographié bloquerait la clôture de TOUS les autres
    chantiers, exactement la garde sans échappatoire praticable que ce dépôt
    sait désarmée dans la semaine. L'avertissement porte sur le canal que le
    pilote lit (stderr, à chaque morsure).

    QUESTION FERMÉE — décision pilote du 2026-09-18, tracée `S-00001568` :
    avertir, jamais refuser. Ne pas la rouvrir.

    La comparaison reste EXACTE (pas de repli casse-repliée) : les chantiers du
    board portent des espaces et des majuscules, un rapprochement approximatif
    rendrait la portée floue.

    `chantier=*` N'APPELLE PAS cette fonction (T-00001093) : `*` désigne toute
    tâche du board, l'avertissement n'aurait rien de vrai à dire —
    `_arme_pour_tache` le court-circuite sur les DEUX chemins, `tasks.py` et
    `specs.py`.
    """
    if chantiers is None:
        return None
    if chantier in chantiers:
        return None
    connus = ", ".join(f"«{c}»" for c in sorted(c for c in chantiers if c))
    return (
        f"cible: AVERTISSEMENT — `chantier=«{chantier}»` du marqueur "
        f"PLAN_CIBLE_REQUIRED ne nomme AUCUNE tâche du board, la garde ne mordra "
        f"donc sur RIEN. Chantiers connus : {connus or '(aucun)'}. Un commentaire "
        f"en fin de ligne ou une majuscule suffit à produire cet état."
    )


def resoudre_plan(
    root: str | Path,
    tid: str,
    data: dict[str, Any],
    *,
    slot: bool,
) -> tuple[Path, str] | None:
    """Le plan à contrôler, ou `None` (R3). `(chemin, note d'emprunt)`.

    R1 : plus grande S-id valide parmi les traces d'approbation de la tâche.
    R2 (`slot=True`, `done` seulement) : même recherche sur les tâches `running`
    du même chantier, et le plan doit NOMMER la tâche (`enrolling_line`).
    Les traces se lisent sous TOUTE graphie de l'id (`entrees_de`, T-00001160).
    Signature INCHANGÉE pour `plan_depends` et `tasks_epics` : le propriétaire
    de la trace élue n'est rendu que par `_resoudre`, que lisent les jambes
    cible.
    """
    res = _resoudre(root, tid, data, slot=slot)
    return (res[0], res[1]) if res is not None else None


def _resoudre(
    root: str | Path,
    tid: str,
    data: dict[str, Any],
    *,
    slot: bool,
) -> tuple[Path, str, str] | None:
    """`resoudre_plan` plus le PROPRIÉTAIRE de la trace `plan approuvé` qui a
    élu le plan : `tid` en R1, l'id du slot `autre["id"]` en R2 (S-00004069).
    `(chemin, note d'emprunt, propriétaire)`, ou `None` (R3)."""
    index = index_par_tache(entrees_specs(root))
    # R1 — la tâche elle-même.
    a_moi = entrees_de(index, tid)
    res = _meilleure_trace(root, a_moi)
    if res is not None:
        chemin, _sid = res
        return (chemin, "", tid)

    # LE LIEN DE LOT (la fournée), APRÈS R1 et au `start` COMME au `done` : sans
    # enrôlement, sans parent `running` — le lien est écrit au board par le code seul.
    lien = _lien_de_lot(root, tid, data, index)
    if lien is not None:
        return lien

    if not slot:
        return None

    # R2 — le slot `running` du même chantier, si le plan NOMME la tâche.
    taches = {t["id"]: t for t in data.get("tasks", [])}
    la_tache = taches.get(tid)
    mon_chantier = _chantier_de(la_tache) if la_tache else ""
    for autre in data.get("tasks", []):
        if autre.get("state") != "running" or autre.get("id") == tid:
            continue
        if _chantier_de(autre) != mon_chantier:
            continue
        a_lui = entrees_de(index, autre["id"])
        # L'ENRÔLEMENT FILTRE LE VIVIER (garde=), il ne post-contrôle pas l'élu :
        # une trace du slot dont le plan ne NOMME pas la tâche est écartée AVANT
        # l'élection par S-id, pour qu'un plan de lot récent non enrôlant ne
        # masque pas un plan plus ancien qui enrôle (À CORRIGER 1).
        res = _meilleure_trace(
            root, a_lui,
            garde=lambda chemin: enrolling_line(
                chemin.read_text(encoding="utf-8"), tid),
        )
        if res is None:
            continue
        chemin, sid = res
        note = f"[cible relevée sur {autre['id']} : {chemin.name} ({sid})]"
        return (chemin, note, autre["id"])
    return None


# ---------------------------------------------------------------------------
# LE LIEN DE LOT — `fournee = {parent, lot, sha256, …}`, écrit par `tasks.py
# fournee` dans la MÊME sauvegarde que le lot. Le plan du lot est celui de la trace
# `plan approuvé` ÉLUE du parent, si son empreinte est celle de la découpe et qu'il
# porte encore `LOT: <clé>`. Auto-déclaratif comme la trace : empêche d'OUBLIER.
# ---------------------------------------------------------------------------
_TITRE_PLAN_APPROUVE = normalise_titre("plan approuvé")
#: `LOT: <clé> |` en tête de ligne, hors code : la PRÉSENCE seule. La grammaire
#: entière vit dans `plan_lots.py`, que ce module ne charge jamais.
_LOT_CLE = re.compile(r"^(?:- )?LOT:[ \t]*([A-Z][A-Z0-9]{0,3})[ \t]*\|")


def cles_de_lots(plan_text: str) -> set[str]:
    """Les clés des lignes `LOT:` du plan, hors bloc de code."""
    return {m.group(1) for ligne in lignes_hors_code(plan_text) if (m := _LOT_CLE.match(ligne))}


def trace_plan_approuve(
    root: str | Path, tid: str, index: dict[str, list[dict[str, Any]]] | None = None
) -> tuple[Path, str] | None:
    """La trace `plan approuvé` ÉLUE de `tid` : une décision à CE SEUL titre (jamais
    `night-eligible`, jamais un verdict), plan sûr d'empreinte recalculée identique,
    plus grande S-id (`_meilleure_trace`). `(chemin, S-id)` ou `None`. UNE élection,
    lue par le lien de lot ET par le prévol de `tasks.py fournee`."""
    if index is None:
        index = index_par_tache(entrees_specs(root))
    candidats = [e for e in entrees_de(index, tid) if e.get("kind") == "decision"
                 and normalise_titre(e.get("title") or "") == _TITRE_PLAN_APPROUVE]
    return _meilleure_trace(root, candidats)


def lien_de_lot(data: dict[str, Any], tid: str) -> dict[str, Any] | None:
    """Le champ `fournee` d'un LOT (`parent`, `lot`, `sha256` non vides), ou `None`."""
    tache = next((t for t in data.get("tasks", []) if isinstance(t, dict) and t.get("id") == tid), None)
    lien = tache.get("fournee") if tache is not None else None
    if isinstance(lien, dict) and all(isinstance(lien.get(k), str) and lien.get(k)
                                      for k in ("parent", "lot", "sha256")):
        return lien
    return None


def _lien_de_lot(root: str | Path, tid: str, data: dict[str, Any],
                 index: dict[str, list[dict[str, Any]]]) -> tuple[Path, str, str] | None:
    """`(chemin, note, parent)` si le lien de lot résout, sinon `None` (R2 puis R3)."""
    lien = lien_de_lot(data, tid)
    if lien is None:
        return None
    elue = trace_plan_approuve(root, lien["parent"], index)
    if elue is None:
        return None
    chemin, _sid = elue
    if hashlib.sha256(chemin.read_bytes()).hexdigest() != lien["sha256"].lower():
        return None
    if lien["lot"] not in cles_de_lots(chemin.read_text(encoding="utf-8")):
        return None
    return (chemin, f"[cible relevée sur {lien['parent']} — lot {lien['lot']}]", lien["parent"])


def _cause_lien(root: str | Path, tid: str, data: dict[str, Any],
                index: dict[str, list[dict[str, Any]]]) -> str | None:
    """La cause NOMMÉE d'un lien de lot qui ne résout pas, ou `None` sans lien."""
    lien = lien_de_lot(data, tid)
    if lien is None:
        return None
    tete = f"Cause : lot {lien['lot']} de {lien['parent']} — "
    elue = trace_plan_approuve(root, lien["parent"], index)
    if elue is None:
        return tete + "le parent n'a aucune trace `plan approuvé` valide (`plan=` sûr, `sha256=` identique)."
    chemin, sid = elue
    recalculee = hashlib.sha256(chemin.read_bytes()).hexdigest()
    if recalculee != lien["sha256"].lower():
        return (tete + f"le plan élu {chemin.name} ({sid}) a l'empreinte sha256={recalculee}, le lot porte "
                f"sha256={lien['sha256']} : le plan a changé depuis la découpe — re-découpe (`delete` des "
                f"lots ouverts, puis `tasks.py fournee {lien['parent']}`).")
    return tete + f"le plan élu {chemin.name} ({sid}) ne porte plus `LOT: {lien['lot']}`."


# ---------------------------------------------------------------------------
# LECTURE DU MARQUEUR. `spec=` et `chantier=` ; malformé = refus fail-closed.
# ---------------------------------------------------------------------------
def lire_marqueur(root: str | Path) -> tuple[str, str] | None:
    """`(spec_rel, chantier)` si le marqueur est armé, `None` s'il est absent.
    Un marqueur présent mais malformé lève `CibleError` (fail-closed) : sa
    présence dit « ce chantier est sous contrainte », ne pas savoir laquelle est
    la pire des lectures."""
    chemin = Path(root) / MARQUEUR
    if not chemin.exists():
        return None
    try:
        # `utf-8-sig` ET NON `utf-8` (revue de clôture T-00000654, T5) : un
        # marqueur posé sous Windows porte une BOM, la BOM se collait au `s` de
        # `spec=`, la ligne ne matchait plus et le refus annonçait « il doit
        # porter une ligne `spec=` » ALORS QU'ELLE Y ÉTAIT. Un diagnostic faux
        # coûte plus cher qu'un refus : `utf-8-sig` mange la BOM si elle est là
        # et se comporte comme `utf-8` sinon.
        texte = chemin.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise CibleError(
            f"marqueur PLAN_CIBLE_REQUIRED illisible ({exc}) — armé mais "
            f"inexploitable, on refuse plutôt que d'ignorer une contrainte armée."
        ) from exc
    # DOUBLON = REFUS, PAS « LE DERNIER GAGNE » (revue de clôture T-00000654,
    # C4). L'ancienne boucle écrasait : deux lignes `spec=` contradictoires
    # armaient la garde sur la SECONDE en silence, et le pilote qui relisait le
    # fichier voyait la première. Un marqueur qui dit deux choses ne dit rien.
    specs: list[str] = []
    chantiers: list[str] = []
    for ligne in texte.splitlines():
        ms = re.match(r"\s*spec\s*=\s*(\S.*?)\s*$", ligne)
        mc = re.match(r"\s*chantier\s*=\s*(\S.*?)\s*$", ligne)
        if ms:
            specs.append(ms.group(1).strip())
        if mc:
            chantiers.append(mc.group(1).strip())
    for cle, valeurs in (("spec", specs), ("chantier", chantiers)):
        if len(valeurs) > 1:
            rendu = ", ".join(f"«{v}»" for v in valeurs)
            raise CibleError(
                f"marqueur PLAN_CIBLE_REQUIRED ambigu — {len(valeurs)} lignes "
                f"`{cle}=` : {rendu}. Retire les surnuméraires : un marqueur qui "
                f"nomme deux {cle}s n'en nomme aucune, refus fail-closed."
            )
    spec = specs[0] if specs else None
    chantier = chantiers[0] if chantiers else None
    if not spec or not chantier:
        raise CibleError(
            "marqueur PLAN_CIBLE_REQUIRED malformé — il doit porter une ligne "
            "`spec=<chemin>` ET une ligne `chantier=<nom>`. Armé sans elles, on "
            "ne sait ni quelle spec lire ni quel chantier contraindre : refus "
            "fail-closed."
        )
    return (spec, chantier)


# ---------------------------------------------------------------------------
# POINTS DE MORSURE.
# ---------------------------------------------------------------------------
def _registre_pour(root: str | Path, spec_rel: str) -> set[str]:
    # LA SPEC DU MARQUEUR PASSE PAR `chemin_de_plan_sur` (À CORRIGER 2). L'ancien
    # repli `Path(root)/spec_rel` sans garde levait un traceback sur les trois
    # jambes quand la spec était absente du disque. On refuse désormais NOMMÉ.
    #
    # NOTE MESURÉE, REPRISE (T-00001093) : `strip: .agents/state/` retient le
    # marqueur du KIT, mais la sync template SÈME chez l'adoptant une copie de
    # `.agents/adopter-seed/gates/PLAN_CIBLE_REQUIRED` (`spec=docs/PROMPT-projet.md`,
    # `chantier=*`) : l'adoptant naît ARMÉ, et « marqueur présent + spec absente »
    # devient un scénario réel (gabarit retiré ou renommé). La garde refuse donc
    # proprement, jamais par un traceback, ici comme chez lui.
    spec_path = chemin_de_plan_sur(root, spec_rel)
    if spec_path is None:
        raise CibleError(
            f"spec du marqueur PLAN_CIBLE_REQUIRED inexploitable (`{spec_rel}`) : "
            f"chemin absolu, `..`, suffixe autre que `.md`, fichier absent du "
            f"disque, répertoire, ou hors racine. Le registre des noms ne peut "
            f"être bâti — refus fail-closed plutôt qu'un traceback."
        )
    return registre_depuis_fichier(spec_path)


def _message_refus(
    surface: str, tid_ou_plan: str, chemin: Path, fautives: list[str], note: str,
    ecartees: list[str] | None = None,
) -> str:
    # `surface` est `TASKS` (jambes start/done) ou `SPECS` (jambe verdict) — le
    # préfixe n'était pas codé en dur (NIT a), sinon un refus de verdict aurait
    # annoncé `TASKS:` alors qu'il vient de `specs.py`.
    liste = "\n".join(f"  - {f}" for f in fautives)
    emprunt = f" {note}" if note else ""
    hors = ligne_ecartees(ecartees, f"{tid_ou_plan}, ni sur une tâche de son chantier")
    return (
        f"{surface}: refus — le plan {chemin.name}{emprunt} n'annote pas toutes "
        f"ses étapes ({tid_ou_plan}).\n"
        f"Étapes sans cible :\n{liste}\n{hors}"
        f"Chaque étape porte AU MOINS une valeur : `cible: « <nom d'invariant> »`, "
        f"`angle mort: <question au pilote>`, ou `décision pilote: S-<id>` — une "
        f"décision EXISTANTE, tracée sur la tâche, sur une tâche de son chantier, "
        f"sur une tâche que le plan enrôle (ligne 1 ou `Tâches :`) ou sur la "
        f"tâche dont la trace `plan approuvé` a élu le plan.\n"
        f"Sortie tracée si la cible ne s'applique pas : "
        f"`--sans-cible \"<pourquoi>\"`. La raison reste VISIBLE au board."
    )


def _arme_pour_tache(
    root: str | Path,
    tid: str,
    data: dict[str, Any] | None = None,
    *,
    avertir: bool = True,
) -> tuple[str, str] | None:
    """LE SEUL LECTEUR DU RÉGIME (T-00000765) : `(spec_rel, chantier)` si le
    marqueur est armé ET que `tid` appartient au chantier nommé, `None` sinon.
    Trois lectures inline en disaient autant en trois copies ; une copie qui
    dérive désarme une jambe en silence — les CINQ jambes (cible ×3, arêtes ×2)
    passent ici, et W8c le force à `None` pour les voir se taire ensemble.
    `data` fourni : board déjà chargé (chemin `tasks.py`) ; absent : lecture HORS
    verrou (chemin de `specs.py`). Marqueur malformé ⇒ `CibleError`.
    `avertir=False` tait l'avertissement de chantier déjà émis par la cible.

    `chantier=*` (T-00001093, la graine de l'adoptant) = TOUTE tâche PRÉSENTE au
    board, AVEC OU SANS chantier ; une tâche absente du board reste inerte.
    C'est le SEUL joker : tout autre nom se compare à l'ÉGALITÉ EXACTE, jamais
    en préfixe (`a` n'arme pas `ab`, `a*` n'est pas un motif). Sous `*`
    l'avertissement de chantier fantôme se tait — sa prémisse (« ce nom ne
    désigne aucune tâche ») est fausse par construction, et S-00001568 reste
    tenu : on avertit, on ne refuse jamais sur ce motif.
    """
    marqueur = lire_marqueur(root)
    if marqueur is None:
        return None
    spec_rel, chantier = marqueur
    if data is not None:
        taches = [t for t in data.get("tasks", []) if isinstance(t, dict)]
        chantiers: set[str] | None = {_chantier_de(t) for t in taches}
        la_tache = next((t for t in taches if t.get("id") == tid), None)
        mien = _chantier_de(la_tache) if la_tache is not None else None
    else:
        chantiers = _chantiers_du_board(root)
        mien = chantier_de_tache(root, tid)
    if avertir and chantier != "*":
        _avert = avertissement_chantier(chantier, chantiers)
        if _avert:
            print(_avert, file=sys.stderr)
    if chantier == "*":
        # Toute tâche du board, avec ou sans chantier ; absente (`None`) : inerte.
        if mien is None:
            return None
    elif mien != chantier:
        # `None` (tâche absente du board) diffère toujours d'un nom : inerte.
        return None
    return (spec_rel, chantier)


def refus_au_start(root: str | Path, tid: str, data: dict[str, Any]) -> str | None:
    """La jambe `start` (R1 SEULE) : sans trace propre valide → PASSE ; avec
    trace valide → contrôle des étapes. `None` = inerte ou conforme ; message =
    refus.

    Inerte si le marqueur est absent ou si la tâche n'appartient pas au chantier
    nommé (`_arme_pour_tache`). Un marqueur malformé lève `CibleError`.
    """
    regime = _arme_pour_tache(root, tid, data)
    if regime is None:
        return None
    spec_rel, _chantier = regime
    resolu = _resoudre(root, tid, data, slot=False)
    if resolu is None:
        # Aucune trace d'approbation propre : le start PASSE. La cible mordra au
        # `done`, jamais avant qu'un plan ait été approuvé.
        return None
    chemin, note, proprietaire = resolu
    registre = _registre_pour(root, spec_rel)
    fautives, ecartees = controle_des_etapes(
        root, tid, chemin.read_text(encoding="utf-8"), registre, data,
        proprietaire=proprietaire)
    if fautives:
        return _message_refus("TASKS", tid, chemin, fautives, note, ecartees)
    return None


# ---------------------------------------------------------------------------
# DIAGNOSTIC R3 — quand aucun plan ne résout, NOMMER la cause la plus précise :
# aucune trace, empreinte divergente (les deux sha), plan non enrôlant (ligne 1).
# ---------------------------------------------------------------------------
def _diag_trace(root: str | Path, entry: dict[str, Any], tid: str | None) -> str | None:
    """La cause précise pour laquelle CETTE trace d'approbation ne résout aucun
    plan sûr, ou `None` si elle en résout un (auquel cas la faute est ailleurs).
    `tid` non `None` ⇒ candidat R2, dont le plan doit ENRÔLER la tâche."""
    sid = entry.get("id", "?")
    texte = entry.get("text", "")
    mp = PLAN_FIELD.search(texte or "")
    if not mp:
        return f"Cause : la trace {sid} ne cite aucun `plan=`."
    empreinte = _empreinte_unique(texte or "")
    if not empreinte:
        return f"Cause : la trace {sid} ne cite pas de `sha256=` unique."
    chemin = chemin_de_plan_sur(root, mp.group(1))
    if chemin is None:
        return (f"Cause : la trace {sid} cite un `plan=` non sûr "
                f"(absolu, `..`, mauvais suffixe, absent, répertoire ou hors "
                f"racine).")
    recalculee = hashlib.sha256(chemin.read_bytes()).hexdigest()
    if recalculee != empreinte:
        return (f"Cause : empreinte divergente pour {chemin.name} — "
                f"citée sha256={empreinte}, recalculée sha256={recalculee}.")
    if tid is not None:
        texte_plan = chemin.read_text(encoding="utf-8")
        if not enrolling_line(texte_plan, tid):
            premiere = (texte_plan.splitlines() or [""])[0]
            return (f"Cause : le plan {chemin.name} du slot n'enrôle pas {tid} — "
                    f"son id doit être en ligne 1 ou dans la première ligne "
                    f"`Tâches :`. Ligne 1 lue : {premiere!r}.")
    return None


def _plus_recentes_par_plan(entrees: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Les traces par S-id DÉCROISSANTE (`_clef_sid`), et pour un même `plan=` cité la SEULE plus récente : une trace
    SUPPLANTÉE par une S-id plus grande sur le même plan n'est jamais diagnostiquée (delta S-01M4QK902B8THSQG3KVBJ2PPK0,
    mesuré au done de MC28 : la cause affichée était l'empreinte périmée d'une rév. supplantée, pas l'enrôlement)."""
    vus: set[str] = set()
    garde: list[dict[str, Any]] = []
    for e in sorted(entrees, key=lambda x: _clef_sid(x.get("id", "")), reverse=True):
        mp = PLAN_FIELD.search(e.get("text") or "")
        if mp:
            plan = mp.group(1).rstrip(".,;:)»\"'")
            if plan in vus:
                continue
            vus.add(plan)
        garde.append(e)
    return garde


def _cause_r3(root: str | Path, tid: str, data: dict[str, Any]) -> str:
    """La cause NOMMÉE d'un refus R3, la plus précise disponible — sur la trace la plus RÉCENTE de chaque plan
    (`_plus_recentes_par_plan`), jamais sur une trace supplantée."""
    index = index_par_tache(entrees_specs(root))  # toutes graphies (T-00001160)
    a_moi = _plus_recentes_par_plan([e for e in entrees_de(index, tid) if _est_trace_dapprobation(e)])
    if not a_moi:
        cause_lien = _cause_lien(root, tid, data, index)
        if cause_lien:
            return cause_lien
    taches = {t["id"]: t for t in data.get("tasks", [])}
    la_tache = taches.get(tid)
    mon_chantier = _chantier_de(la_tache) if la_tache else ""
    a_slot: list[tuple[str, dict[str, Any]]] = []
    for autre in data.get("tasks", []):
        if autre.get("state") != "running" or autre.get("id") == tid:
            continue
        if _chantier_de(autre) != mon_chantier:
            continue
        a_slot += [(autre["id"], e) for e in _plus_recentes_par_plan(
            [e for e in entrees_de(index, autre.get("id")) if _est_trace_dapprobation(e)])]
    if not a_moi and not a_slot:
        return ("Cause : aucune trace d'approbation pour cette tâche, ni pour un "
                "slot `running` du même chantier.")
    for e in a_moi:
        diag = _diag_trace(root, e, tid=None)
        if diag:
            return diag
    for _slot_id, e in a_slot:
        diag = _diag_trace(root, e, tid=tid)
        if diag:
            return diag
    return ("Cause : les traces d'approbation présentes ne résolvent aucun plan "
            "sûr sous la racine.")


def _message_refus_r3(root: str | Path, tid: str, data: dict[str, Any]) -> str:
    return (
        f"TASKS: refus de clore {tid} — aucun plan approuvé ne porte de cible.\n"
        f"{_cause_r3(root, tid, data)}\n"
        f"Au `done`, le plan contrôlé est la dernière trace `plan approuvé` "
        f"(`plan=` et `sha256=`, empreinte identique) de la tâche, ou du slot "
        f"`running` du même chantier si ce plan NOMME la tâche.\n"
        # LE CHEMIN NOMINAL S'ÉCRIT, PAS SEULEMENT L'ÉCHAPPATOIRE (revue de
        # clôture T-00000654, trou 1). Le refus ne donnait que `--sans-cible` :
        # sur 53 tâches ouvertes du chantier, la seule commande exécutable
        # proposée était la sortie tracée — c'est ainsi qu'une garde se désarme
        # en une semaine. La ligne ci-dessous dit quoi faire pour PASSER, et
        # nomme les TROIS valeurs de `_CIBLE`/`_ANGLE`/`_DECISION` : un board
        # neuf sous `chantier=*` n'a encore aucune `S-…` (S-00004092). Elle dit
        # aussi les ARÊTES : sans elles, le `specs.py add` qu'elle propose
        # refuse (`plan_depends.refus_dependances_a_lapprobation`, S-00004102).
        f"Chemin nominal : annote le plan (chaque étape porte "
        f"`cible: « <nom de la spec> »`, `angle mort: <question au pilote>` "
        f"ou `décision pilote: S-…`, et le plan une ligne `ARÊTES: aucune` "
        f"ou une `ARÊTE:` par dépendance, hors bloc de code), puis trace "
        f"l'approbation — "
        f"`python .agents/bin/specs.py add --task {tid} --kind decision "
        f"\"plan approuvé\" --text \"plan=<docs/tasks/….md> sha256=<hex>\"` "
        f"(le sha256 se calcule APRÈS l'annotation, sinon l'empreinte diverge).\n"
        f"Sortie tracée : `--sans-cible \"<pourquoi>\"`, visible au board."
    )


def evaluer_done(
    root: str | Path, tid: str, data: dict[str, Any]
) -> tuple[str | None, str]:
    """La jambe `done` (R1 puis R2). Rend `(refus, note)` :

    - `refus` est un message de refus fail-closed, ou `None` (inerte/conforme) ;
    - `note` est la note d'emprunt `[cible relevée sur T-… : <plan> (S-…)]` quand
      la cible a été relevée sur le slot d'un AUTRE (R2), sinon `""`. La note se
      renvoie MÊME sur le chemin conforme, pour que l'appelant l'écrive au board
      comme l'emprunt de binôme — la taire ferait lire « cette tâche a eu sa
      cible », quand le vrai fait est « le slot sous lequel elle tourne l'a eue ».

    Câblée par l'étape 3 (`tasks.py set_state`) ; définie ici avec le résolveur.
    """
    regime = _arme_pour_tache(root, tid, data)
    if regime is None:
        return (None, "")
    spec_rel, _chantier = regime
    resolu = _resoudre(root, tid, data, slot=True)
    if resolu is None:
        return (_message_refus_r3(root, tid, data), "")
    chemin, note, proprietaire = resolu
    registre = _registre_pour(root, spec_rel)
    # Le slot élu en R2 prête sa décision avec son plan (S-00004069).
    fautives, ecartees = controle_des_etapes(
        root, tid, chemin.read_text(encoding="utf-8"), registre, data,
        proprietaire=proprietaire)
    if fautives:
        return (_message_refus("TASKS", tid, chemin, fautives, note, ecartees), "")
    return (None, note)


def refus_au_done(root: str | Path, tid: str, data: dict[str, Any]) -> str | None:
    """La jambe `done`, réduite à son verdict de refus. `evaluer_done` porte la
    note d'emprunt en plus ; ce raccourci sert les appelants qui n'en ont pas
    besoin, et garde une symétrie de nom avec `refus_au_start`/`refus_au_verdict`."""
    return evaluer_done(root, tid, data)[0]


def refus_au_verdict(
    root: str | Path, task: str, kind: str, title: str, text: str
) -> str | None:
    """La jambe verdict (D5) : mord SEULEMENT si `kind=verdict` ET titre
    plan-critic ET statut éligible ET `plan=` présent. Tout le reste passe SANS
    lecture. Câblée par l'étape 3 (`specs.py`) ; définie ici avec le résolveur.
    """
    if kind != "verdict":
        return None
    if not PLAN_CRITIC_TITLE.match(title or ""):
        return None
    if verdict_status(title or "") not in ELIGIBLE_STATUSES:
        return None
    mp = PLAN_FIELD.search(text or "")
    if not mp:
        return None
    # Pré-filtre passé : le marqueur peut être lu. *** LA PORTÉE `chantier=`
    # (BLOQUANT 1). *** La phrase canonique promet « tâche hors chantier : rien
    # ne change » ; `specs.py` n'a pas le `data` du board, donc `_arme_pour_tache`
    # relit `TASKS.json` hors verrou (tâche absente = `None` = inerte). Sous
    # `chantier=*` (graine de l'adoptant), toute tâche PRÉSENTE au board est armée.
    regime = _arme_pour_tache(root, task)
    if regime is None:
        return None
    spec_rel, _chantier = regime
    chemin = chemin_de_plan_sur(root, mp.group(1))
    if chemin is None:
        return (
            f"SPECS: refus — le verdict plan-critic de {task} cite un `plan=` non "
            f"sûr (absolu, `..`, mauvais suffixe, absent, répertoire ou hors "
            f"racine)."
        )
    registre = _registre_pour(root, spec_rel)
    fautives, ecartees = controle_des_etapes(
        root, task, chemin.read_text(encoding="utf-8"), registre)
    if fautives:
        return _message_refus("SPECS", task, chemin, fautives, "", ecartees)
    return None


# ---------------------------------------------------------------------------
# CLI — `cible-check <plan> [--spec]`, rc 0/1 listant les étapes fautives.
# ---------------------------------------------------------------------------
def cible_check(root: str | Path, plan_arg: str, spec_arg: str | None) -> tuple[int, str]:
    """Retourne `(rc, message)`. `rc=0` si toutes les étapes sont annotées,
    `rc=1` sinon, `rc=2` pour TOUTE erreur de configuration. `--spec` est
    utilisé TEL QUEL, sans marqueur ; à défaut, la spec est lue dans le marqueur
    armé.

    rc 1 veut dire « étapes sans cible » et rien d'autre (T-00000814, mesuré) :
    un marqueur malformé ou ambigu levait `CibleError` HORS `try`, et un plan ou
    une spec non UTF-8 levait `UnicodeDecodeError` (une `ValueError`, pas une
    `OSError`). Les deux sortaient en TRACE avec rc 1, ce qui se lisait comme une
    réponse du contrôle. Chaque erreur de configuration rend désormais un refus
    NOMMÉ en rc 2."""
    plan_path = Path(plan_arg)
    if not plan_path.is_absolute():
        plan_path = Path(root) / plan_path
    try:
        plan_text = plan_path.read_text(encoding="utf-8")
    except (OSError, ValueError) as exc:  # ValueError ⊃ UnicodeDecodeError
        return (2, f"cible-check: plan illisible ({exc})")

    chantier: str | None = None
    if spec_arg:
        spec_rel = spec_arg
    else:
        try:
            marqueur = lire_marqueur(root)
        except CibleError as exc:
            return (2, f"cible-check: {exc}")
        if marqueur is None:
            return (2, "cible-check: ni --spec ni marqueur PLAN_CIBLE_REQUIRED "
                       "armé — impossible de bâtir le registre des noms.")
        spec_rel, chantier = marqueur

    try:
        registre = _registre_pour(root, spec_rel)
    except (CibleError, OSError, ValueError) as exc:  # ⊃ UnicodeDecodeError
        return (2, f"cible-check: spec illisible ({exc})")

    try:
        entrees = entrees_specs(root)
    except CibleError as exc:
        return (2, f"cible-check: {exc}")
    # PERTINENCE (T-00000909). Sous un chantier NOMMÉ, toute tâche contrôlée en
    # est : l'ensemble des jambes est celui des décisions des tâches du chantier
    # et des tâches que le plan enrôle. Sous `--spec` ou `chantier=*`, la tâche
    # est inconnue de la CLI : existence seule, comme avant, et la sortie le DIT.
    borne = ""
    if chantier and chantier != "*":
        try:
            taches = taches_du_board(root, None)
        except CibleError as exc:  # board en deux formes ou illisible (passe de correction F5)
            return (2, f"cible-check: {exc}")
        decisions = decisions_pertinentes(
            entrees, taches, plan_text, chantier=chantier)
    else:
        decisions = decisions_existantes(entrees)
        if _DECISION.search("\n".join(lignes_hors_code(plan_text))):
            borne = ("\n(pertinence des `décision pilote:` NON contrôlée ici : "
                     "sans chantier nommé, la tâche est inconnue — `start`, "
                     "`done` et le verdict plan-critic la contrôlent.)")
    fautives = etapes_fautives(plan_text, registre, decisions)
    if not fautives:
        return (0, f"cible-check: {plan_path.name} — toutes les étapes portent "
                   f"une cible.{borne}")
    liste = "\n".join(f"  - {f}" for f in fautives)
    # Les décisions écartées sont NOMMÉES comme au start, au done et au verdict
    # (critic-fable n° 2) ; sous `--spec` ou `*`, `decisions` est l'existence
    # seule : aucune n'est écartée, la ligne reste vide.
    hors = ligne_ecartees(decisions_ecartees(entrees, plan_text, decisions),
                          f"une tâche du chantier `{chantier}`")
    corps = f"cible-check: {plan_path.name} — étapes sans cible :\n{liste}\n{hors}"
    return (1, corps.rstrip("\n") + borne)
