#!/usr/bin/env python3
"""CHARGE DU POSTE — le verdict de parallélisme, CALIBRÉ SEUL à chaque vague (T-01M4XZWZ9C0ZFVXN3MFSFY1G5V,
lot T ; décisions pilote S-01M4Y10HZ6Y0TAXNNK0S1VRFC1, S-01M4Y2Q1QK4AGNCSPMQ7ES126Y, S-01M537VBGG5RVBCF3KHFV3JMN5 ;
base à cinq : S-01M54B1KQ6SVNCA9ZSRPWHCCFP, livrée par T-01M54B1SXM557Z86N1TXEJSRDE).

Usage : `bash .agents/pyrun.sh .agents/bin/charge_poste.py verdict --actifs N [--attendre S≤540] [--poste H]`
        `… releve [--poste H]` (diagnostic, n'écrit rien)
        `… declarer --max M --motif <décision> [--poste H]` (geste du pilote, facultatif)

SORTIE DE `verdict` (rc 0 dès que les lignes sont imprimées, dégradées comprises ; rc 2 usage) :
  l.1 `PLAFOND=<n> BASE=<b> SOURCE=<appris|defaut|declare|illisible|non-mesurable>`
  l.2 `PEUT_AJOUTER=<k> DOIT_REDESCENDRE_A=<d|-> ACTIFS=<n>`
  l.3 `CHARGE=<1m>/<5m>/<15m> C=<c> PRESSION=<1|2|4|inconnu> EDR_CPU=<x|inconnu>`
  l.4 `CALIBRATION=<monte|descend|relache|stable|non-inscriptible> RELEVES=<k> ETAT=<ok|non-inscriptible>`
  puis, seulement quand elles s'appliquent, des lignes `COVERAGE DEGRADED — …` ; les avertissements vont sur stderr.

RÈGLES (annexe A3 du plan, texte exact là-bas ; contrat lisible : `.agents/ref/CHARGE_POSTE.md` ; première
vague et accord rapide : T-01M56Q23NHTEXES5CAT0A03TFJ, décision pilote S-01M59PGM83GXXV8ZNGQ8NZFH9T) :
  * M = plafond déclaré (`declarer`, clé poste + C) sinon ⌊2C/3⌋ ; UNE règle : DUR = min(C, max(1, M)) (C46) ;
    PLAFOND = min(DUR, PLAFOND_APPRIS). BASE = max(min(5, PLAFOND), min(PLAFOND, ⌊C/2⌋)) au REPOS (charges
    1 min ET 5 min < C/4, strict ; S-01M56T0DBKR9Q20XRXVJBMP619), ailleurs min(5, PLAFOND) ; BASE ≥ 1 — sous
    cinq quand le plafond l'est, jamais un plancher (S-01M54NGJ3S0NHR7BEFZY94PF7W).
  * En priorité, 1 min > 2C/3 (strict) ou PRESSION ≥ 2 ⇒ PEUT_AJOUTER = 0, DOIT_REDESCENDRE_A = BASE ;
    surcharge SÉVÈRE (1 min > C ou PRESSION 4) ⇒ min(3, BASE) (S-01M54W6K0CMZRZM3EJKBHBX7A8) — la charge
    l'emporte sur tout le reste.
  * LIBRE = PLAFOND − ACTIFS − TENU. ACTIFS = 0 ⇒ max(0, min(BASE, LIBRE)) (accord HORODATÉ, C45) ;
    ACTIFS > 0 et charges 1 min ET 5 min < 2C/3 (strict) ⇒ max(0, LIBRE), sans délai entre accords ni limite
    de deux ; sinon 0 (à l'égalité 2C/3 : 0).
  * TENU, le plafond PARTAGÉ PAR POSTE entre appelants (décisions de l'orchestrateur S-01M56VTWNDV9VYGTS94E81GWZH
    puis S-01M56Z5GT8VR9QSGGJYNYTPS2Z, qui l'affine ; S-01M5BSJ7PBQD79HMY19BSSBGH2 révise sa retenue). Chaque
    relevé porte le CLAUDE_PID de son appelant, vérifié vivant (sinon l'appelant est ANONYME), et son `tenu`.
    Appelant identifié : TENU = Σ(autres sessions identifiées, PID vivant, dernier relevé < 1 h : actifs
    + garde) + accords anonymes < 300 s + max(0, accords propres < 300 s − ACTIFS). Appelant anonyme : TENU =
    Σ(sessions identifiées, PID vivant, dernier relevé < 1 h : actifs + garde) + max(0, accords anonymes < 300 s
    − ACTIFS). garde = accordés si ce relevé a moins de 300 s ou est à ACTIFS = 0, sinon 0. L'ACTIFS d'une
    session identifiée n'est jamais déduit des accords anonymes. Surcompte PRUDENT nommé : PID réutilisé,
    relevé remplacé, sous-agent au PID du principal ; PID invérifiable (Windows) ⇒ supposé vivant.
  * État non inscriptible (bac à sable, verrou tenu, état dans un dépôt) ⇒ 1 à ACTIFS = 0, 0 sinon (C31).
  * Charge non mesurable ⇒ PLAFOND = BASE = min(5, DUR) (C inconnu : DUR = 5, sans borne de cœurs), aucune
    calibration ; PRESSION ≥ 2 ⇒ 0 d'abord, état inscriptible ou non (PRESSION 4 ⇒ DOIT_REDESCENDRE_A =
    min(3, BASE), PRESSION 2 ⇒ BASE) ; sinon PEUT_AJOUTER = max(0, BASE − ACTIFS), TENU non retenu.
  * PRESSION ∈ {1, 2, 4, inconnu} (C38) : 1 = Mac normal, aucune retenue ; `inconnu` ne retient pas et ne vaut
    jamais un relevé « sain » pour la montée.

CALIBRATION AUTOMATIQUE (S-01M537VBGG, aucune commande) : chaque `verdict` ajoute un relevé à
state_home()/charge_poste/releves.jsonl (500 derniers) et ajuste plafond.json, sous un verrou O_EXCL (repris au-delà
de 30 s). Relevé PROBANT : ACTIFS ≥ 1 et au moins FENETRE_PROBANTE_S = 300 s après le dernier accord (sans
accord : non probant, aucune vague n'est mesurée) — fenêtre distincte de la RETENUE de 300 s des accords dans
TENU. Probant saturé ⇒ max(1, min(PLAFOND_APPRIS, a − 1)), a = ACTIFS + accordés + tenu du DERNIER ACCORD (C44 ;
un ancien relevé sans `tenu` vaut 0) ; probant sain (1 min ET 5 min < C/2) à ACTIFS ≥ PLAFOND_APPRIS ⇒ +1 ;
24 h sans relevé saturé ⇒ +1, au plus une fois par 24 h (`relache_le`, C43) ; jamais au-dessus de DUR, jamais
sous 1 — la borne DUR s'applique à l'USAGE, jamais recopiée sur disque : plafond.json ne se réécrit que s'il
change (descente, montée, relâche, relevé saturé, réparation). plafond.json illisible ⇒ DUR, dit.

L'état vit sous state_home() et la déclaration sous config_home() (`cadre.paths`), JAMAIS dans un dépôt : un
emplacement sous un `.git` est refusé. Stdlib seule. Ce que l'outil ne fait pas (V1) : aucune redescente active
— à la surcharge, aucun départ, les agents en vol finissent ; ACTIFS est celui d'UNE session, déclaratif ; la
charge 1 min réagit en retard : un dépassement transitoire est accepté, la coupure > 2C/3 retient la suite.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import math
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager, suppress
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- constantes
ATTENTE_MAX_S = 540          # `--attendre` : sous le `timeout: 600000` du Bash appelant (C33)
FENETRE_PROBANTE_S = 300     # un relevé n'est probant qu'au moins 300 s après le dernier accord (calibration)
RETENUE_S = 300              # un accord anonyme ou propre reste TENU 300 s (distinct de la fenêtre probante)
VIE_SESSION_S = 3600         # le dernier relevé d'une autre session vivante tient ses actifs au plus 1 h
RELACHE_S = 24 * 3600        # 24 h sans saturation ⇒ +1, au plus une fois par 24 h (C43)
VERROU_PERIME_S = 30         # un verrou plus vieux est repris (A4 : 31 s repris, 29 s refusé)
ATTENTE_VERROU_S = 5.0       # le verrou n'est tenu que le temps d'une lecture et de deux écritures
PAS_ATTENTE_S = 30.0         # pas de re-mesure sous `--attendre`
MAX_RELEVES = 500
BASE_MAX = 5                 # BASE hors repos : min(5, PLAFOND) (S-01M54B1KQ6SVNCA9ZSRPWHCCFP)
REPLI_SEVERE = 3             # surcharge sévère : redescendre à min(3, BASE) (S-01M54W6K0CMZRZM3EJKBHBX7A8)

NOM_DOSSIER_ETAT = "charge_poste"
NOM_RELEVES = "releves.jsonl"
NOM_PLAFOND = "plafond.json"
NOM_VERROU = "verrou"
NOM_CONFIG = "parallelisme.json"

# EDR, liste FERMÉE, comparée au DÉBUT du nom de l'exécutable (dernier segment du chemin `comm`).
EDR_MESURES = ("com.jamf.protect", "JamfProtectAgent", "JamfDaemon", "zdp")   # mesurés (darwin-arm64)
EDR_NON_MESURES = ("falcond", "sentineld", "wdavdaemon")                        # NON MESURÉS
EDR_NOMS = EDR_MESURES + EDR_NON_MESURES

TEXTE_NON_INSCRIPTIBLE = "COVERAGE DEGRADED — état de charge non inscriptible : agents un à un"
TEXTE_NON_MESURABLE = "COVERAGE DEGRADED — charge du poste non mesurable sur {plateforme}"


# --------------------------------------------------------------------------- couture `cadre.paths`
# Patron recopié de `migrate_index_to_db.py::_cadre_paths` (S-00001655) : (1) le PAQUET installé, (2) à défaut
# SEULEMENT le chargeur PAR CHEMIN depuis `paths.py` du clone (qui voyage chez l'adoptant). Un succès
# est mémoïsé, un échec ne l'est pas. Toute exception de la couture est attrapée par `Exception` : deux copies
# de `cadre.paths` peuvent coexister dans un processus, chacune avec SA classe d'erreur.
# T-01M5BXTGX5YN8XEXTG1PP7A5ZX (phase E) : le dossier du repli vient du RÉSOLVEUR `vendor_paths.py` (frère chargé
# PAR CHEMIN, jamais par `sys.path`) — `.agents/vendor/cadre` s'il porte le paquet, sinon `src/cadre` ; résolveur
# absent, illisible ou paquet introuvable : `src/cadre`, le lieu d'avant (son absence reste dite par le refus).
# Illisible (son exécution lève) : le repli le DIT en une ligne sur stderr, comme `event_store` (S-01M5CN1KBT).
# Incomplet (un nom de `_API_RESOLVEUR` manque) : ABSENT, repli muet, comme `event_store` et `record_id`.
_API_RESOLVEUR = ("resoudre", "exiger", "dossier_paquet", "amorcer_cli", "verifier_charge", "ProvenanceRefusee")


def _dossier_cadre(racine: Path) -> Path:
    chemin = Path(__file__).resolve().with_name("vendor_paths.py")
    if not chemin.is_file():  # résolveur absent (copie partielle de `.agents/bin`) : le repli d'avant, muet
        return racine / "src" / "cadre"
    nom = "_vendor_paths_charge_poste"
    try:
        spec = importlib.util.spec_from_file_location(nom, chemin)
        if spec is None or spec.loader is None:  # pragma: no cover - défensif
            raise ImportError("vendor_paths.py sans chargeur")
        resolveur = importlib.util.module_from_spec(spec)
        existant = sys.modules.get(nom)
        sys.modules[nom] = resolveur  # enregistré AVANT `exec_module` (T-00000134) ; s'il lève, l'entrée d'avant
        try:
            spec.loader.exec_module(resolveur)
        except BaseException:
            if existant is not None:
                sys.modules[nom] = existant
            else:
                sys.modules.pop(nom, None)
            raise
    except Exception as exc:  # noqa: BLE001 — illisible = ABSENT, et le repli le DIT
        print(f"charge_poste: résolveur {chemin} illisible ({type(exc).__name__}: "
              f"{' '.join(str(exc).split())}) — repli sur src/cadre", file=sys.stderr)
        return racine / "src" / "cadre"
    if not all(hasattr(resolveur, n) for n in _API_RESOLVEUR):  # incomplet = ABSENT, comme les 4 autres
        return racine / "src" / "cadre"
    try:
        dossier = resolveur.dossier_paquet(racine, "cadre")
    except Exception:  # noqa: BLE001 — `dossier_paquet` qui lève = repli d'avant
        dossier = None
    return dossier if dossier is not None else racine / "src" / "cadre"


_CHEMIN_CADRE_PATHS = _dossier_cadre(Path(__file__).resolve().parents[2]) / "paths.py"
_NOM_CADRE_PATHS_PAR_CHEMIN = "_cadre_paths_charge_poste"
_CADRE_PATHS: Any = None


class CadrePathsIntrouvable(RuntimeError):
    """Ni le paquet `cadre` ni `paths.py` (`.agents/vendor/cadre` ou `src/cadre`) : l'état ne s'écrit pas."""


def _importer_cadre_paths_paquet() -> Any:
    """Branche (1) : `cadre.paths` par le paquet installé (point de test)."""
    module = importlib.import_module("cadre.paths")
    if not (callable(getattr(module, "state_home", None)) and callable(getattr(module, "config_home", None))):
        raise ImportError("le paquet `cadre` installé ne porte pas `state_home`/`config_home`")
    return module


def _cadre_paths() -> Any:
    global _CADRE_PATHS
    if _CADRE_PATHS is not None:
        return _CADRE_PATHS
    try:
        module = _importer_cadre_paths_paquet()
    except Exception as paquet_exc:  # noqa: BLE001 — couture : classe d'erreur non importable (docstring)
        try:
            spec = importlib.util.spec_from_file_location(_NOM_CADRE_PATHS_PAR_CHEMIN, _CHEMIN_CADRE_PATHS)
            if spec is None or spec.loader is None:
                raise ImportError(f"aucun chargeur pour {_CHEMIN_CADRE_PATHS}")
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
        except Exception as chemin_exc:  # noqa: BLE001 — idem
            sys.modules.pop(_NOM_CADRE_PATHS_PAR_CHEMIN, None)
            raise CadrePathsIntrouvable(
                f"cadre.paths introuvable (paquet : {type(paquet_exc).__name__}: {paquet_exc} ; chemin "
                f"{_CHEMIN_CADRE_PATHS} : {type(chemin_exc).__name__}: {chemin_exc})") from chemin_exc
    _CADRE_PATHS = module
    return module


def depot_englobant(chemin: Path) -> Path | None:
    """Le premier ancêtre de `chemin` (lui compris) qui porte un `.git`, sinon None."""
    resolu = chemin.expanduser().resolve()
    for ancetre in (resolu, *resolu.parents):
        if (ancetre / ".git").exists():
            return ancetre
    return None


def emplacements() -> tuple[Path | None, Path | None, list[str]]:
    """(dossier d'état, fichier de déclaration, avertissements). None = refusé ou introuvable, dit."""
    avert: list[str] = []
    try:
        module = _cadre_paths()
    except CadrePathsIntrouvable as exc:
        return None, None, [f"{exc} : état non inscriptible, plafond déclaré ignoré"]
    resolus: list[Path | None] = []
    cibles = (("état", "state_home", NOM_DOSSIER_ETAT), ("configuration", "config_home", NOM_CONFIG))
    for nom, racine, feuille in cibles:
        try:
            chemin = Path(getattr(module, racine)()) / feuille
        except Exception as exc:  # noqa: BLE001 — `CadrePathError` de l'une ou l'autre copie (couture)
            avert.append(f"{racine}() introuvable ({exc}) : {nom} ignoré")
            resolus.append(None)
            continue
        depot = depot_englobant(chemin)
        if depot is not None:
            avert.append(f"{nom} {chemin} sous un dépôt git ({depot}) : refusé, jamais dans un dépôt — posez "
                         f"CADRE_STATE_DIR / CADRE_CONFIG_HOME hors de lui")
            resolus.append(None)
            continue
        resolus.append(chemin)
    return resolus[0], resolus[1], avert


# --------------------------------------------------------------------------- mesure
@dataclass(frozen=True)
class Sources:
    """Ce que la mesure lit du poste ; injecté par les bancs."""
    cpu_count: Callable[[], object]
    getloadavg: Callable[[], object] | None
    lire: Callable[[str], str | None]
    executer: Callable[[Sequence[str]], str | None]
    plateforme: str


@dataclass(frozen=True)
class Mesure:
    c: int | None
    charge: tuple[float, float, float] | None
    source_charge: str
    pression: int | None
    edr_cpu: float | None
    edr_noms: tuple[str, ...]
    plateforme: str

    @property
    def mesurable(self) -> bool:
        return self.c is not None and self.charge is not None


def _lire_texte(chemin: str) -> str | None:
    try:
        return Path(chemin).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _executer(argv: Sequence[str]) -> str | None:
    """stdout d'une commande sous LC_ALL=C, None si elle manque, échoue ou dépasse 5 s."""
    try:
        sortie = subprocess.run(list(argv), capture_output=True, text=True, encoding="utf-8", errors="replace",
                                timeout=5, check=False, env={**os.environ, "LC_ALL": "C"})
    except (OSError, subprocess.SubprocessError):
        return None
    return sortie.stdout if sortie.returncode == 0 else None


def sources_du_poste() -> Sources:
    """Les sources réelles, résolues À L'APPEL (un banc qui retire `os.getloadavg` est vu)."""
    return Sources(os.cpu_count, getattr(os, "getloadavg", None), _lire_texte, _executer, sys.platform)


def nombre(brut: object) -> float | None:
    """Un nombre fini et ≥ 0, sinon None (`-1`, `nan`, `1e400`, `abc`, vide ⇒ None ; virgule décimale tolérée)."""
    if isinstance(brut, bool):
        return None
    if isinstance(brut, (int, float)):
        try:
            valeur = float(brut)
        except OverflowError:  # entier JSON géant (≥ 10^309) : illisible, jamais un traceback
            return None
    elif isinstance(brut, str):
        try:
            valeur = float(brut.strip().replace(",", "."))
        except ValueError:
            return None
    else:
        return None
    return valeur if math.isfinite(valeur) and valeur >= 0 else None


def _trois(valeurs: object) -> tuple[float, float, float] | None:
    if not isinstance(valeurs, (list, tuple)) or len(valeurs) < 3:
        return None
    lus = [nombre(v) for v in valeurs[:3]]
    if any(v is None for v in lus):
        return None
    return (lus[0], lus[1], lus[2])  # type: ignore[return-value]


def _entier_positif(brut: object) -> int | None:
    return brut if isinstance(brut, int) and not isinstance(brut, bool) and brut >= 1 else None


def lire_charge(sources: Sources) -> tuple[tuple[float, float, float] | None, str]:
    """getloadavg, puis `/proc/loadavg`, puis `sysctl -n vm.loadavg` (virgule OU point) ; sinon `aucune`."""
    if sources.getloadavg is not None:
        try:
            valeurs = _trois(sources.getloadavg())
        except OSError:
            valeurs = None
        if valeurs is not None:
            return valeurs, "getloadavg"
    texte = sources.lire("/proc/loadavg")
    if texte:
        valeurs = _trois(texte.split())
        if valeurs is not None:
            return valeurs, "/proc/loadavg"
    sortie = sources.executer(["sysctl", "-n", "vm.loadavg"])
    if sortie:
        valeurs = _trois(sortie.replace("{", " ").replace("}", " ").split())
        if valeurs is not None:
            return valeurs, "sysctl"
    return None, "aucune"


def _pression_psi(texte: str) -> int | None:
    """`/proc/pressure/memory` (Linux, ASSUMÉ) : full avg10 ≥ 10 ⇒ 4, some avg10 ≥ 10 ⇒ 2, sinon 1."""
    moyennes: dict[str, float | None] = {}
    for ligne in texte.splitlines():
        morceaux = ligne.split()
        if not morceaux:
            continue
        for morceau in morceaux[1:]:
            if morceau.startswith("avg10="):
                moyennes[morceaux[0]] = nombre(morceau[len("avg10="):])
    some = moyennes.get("some")
    if some is None:
        return None
    full = moyennes.get("full")
    if full is not None and full >= 10:
        return 4
    return 2 if some >= 10 else 1


def _pression_meminfo(texte: str) -> int | None:
    """Repli Linux : MemAvailable < 5 % ⇒ 4, < 10 % ⇒ 2, sinon 1."""
    champs: dict[str, float | None] = {}
    for ligne in texte.splitlines():
        cle, _, reste = ligne.partition(":")
        morceaux = reste.split()
        if morceaux:
            champs[cle.strip()] = nombre(morceaux[0])
    total, dispo = champs.get("MemTotal"), champs.get("MemAvailable")
    if not total or dispo is None:
        return None
    part = dispo / total
    return 4 if part < 0.05 else 2 if part < 0.10 else 1


def lire_pression(sources: Sources) -> int | None:
    """PRESSION ∈ {1, 2, 4} ou None (`inconnu`) — C38."""
    if sources.plateforme == "darwin":
        sortie = sources.executer(["sysctl", "-n", "kern.memorystatus_vm_pressure_level"])
        valeur = nombre(sortie) if sortie else None
        return int(valeur) if valeur in (1.0, 2.0, 4.0) else None
    if sources.plateforme.startswith("linux"):
        texte = sources.lire("/proc/pressure/memory")
        if texte:
            lu = _pression_psi(texte)
            if lu is not None:
                return lu
        texte = sources.lire("/proc/meminfo")
        return _pression_meminfo(texte) if texte else None
    return None


def analyser_ps(sortie: str) -> tuple[float | None, tuple[str, ...]]:
    """Somme du %CPU des EDR de la liste fermée. UN seul split par ligne : le chemin `comm` porte des espaces."""
    total, noms, trouve = 0.0, [], False
    for ligne in sortie.splitlines():
        morceaux = ligne.strip().split(None, 1)
        if len(morceaux) != 2:
            continue
        pcpu = nombre(morceaux[0])
        if pcpu is None:
            continue
        nom = morceaux[1].strip().rsplit("/", 1)[-1]
        if nom.startswith(EDR_NOMS):
            trouve = True
            total += pcpu
            noms.append(nom)
    return (round(total, 1) if trouve else None), tuple(dict.fromkeys(noms))


def mesurer(sources: Sources) -> Mesure:
    charge, source_charge = lire_charge(sources)
    edr_cpu, edr_noms = analyser_ps(sources.executer(["ps", "-Ao", "pcpu=,comm="]) or "")
    return Mesure(_entier_positif(sources.cpu_count()), charge, source_charge, lire_pression(sources),
                  edr_cpu, edr_noms, sources.plateforme)


# --------------------------------------------------------------------------- règles (pures)
def dur_de(c: int, m_declare: int | None) -> int:
    """C46, UNE règle : DUR = min(C, max(1, M)), M = déclaré sinon ⌊2C/3⌋."""
    m = m_declare if m_declare is not None else (2 * c) // 3
    return min(c, max(1, m))


def sature(l1: float, pression: int | None, c: int) -> bool:
    """1 min > 2C/3 (strict) ou PRESSION ≥ 2. En entiers : pas d'arrondi de 2C/3."""
    return l1 * 3 > 2 * c or pression in (2, 4)


def sous_moitie(l1: float, l5: float, c: int) -> bool:
    """1 min ET 5 min < C/2 (strict) — seuil de la MONTÉE saine du calibrateur, jamais celui d'un départ."""
    return l1 * 2 < c and l5 * 2 < c


def au_repos(l1: float, l5: float, c: int) -> bool:
    """1 min ET 5 min < C/4 (strict) : le poste est au repos, la première vague monte à BASE au repos."""
    return l1 * 4 < c and l5 * 4 < c


def sous_deux_tiers(l1: float, l5: float, c: int) -> bool:
    """1 min ET 5 min < 2C/3 (strict) : l'accord rapide à ACTIFS > 0. À l'égalité 2C/3 : non."""
    return l1 * 3 < 2 * c and l5 * 3 < 2 * c


def base_de(c: int | None, charge: tuple[float, float, float] | None, plafond: int) -> int:
    """BASE = max(min(5, P), min(P, ⌊C/2⌋)) au repos (S-01M56T0DBKR9Q20XRXVJBMP619), ailleurs — charge non
    mesurable comprise — min(5, P) (S-01M54B1KQ6). Jamais un plancher : sous cinq quand le plafond l'est."""
    hors_repos = min(BASE_MAX, plafond)
    if c is None or charge is None or not au_repos(charge[0], charge[1], c):
        return hors_repos
    return max(hors_repos, min(plafond, c // 2))


def repli(base: int, severe: bool) -> int:
    """DOIT_REDESCENDRE_A d'une surcharge présente : BASE si modérée, min(3, BASE) si sévère (S-01M54W6K0C)."""
    return min(REPLI_SEVERE, base) if severe else base


def decider(*, c: int | None, charge: tuple[float, float, float] | None, pression: int | None, actifs: int,
            plafond: int, tenu: int, inscriptible: bool) -> tuple[int, int | None]:
    """(PEUT_AJOUTER, DOIT_REDESCENDRE_A) — annexe A3, VERDICT (S-01M59PGM83GXXV8ZNGQ8NZFH9T) : LIBRE =
    PLAFOND − ACTIFS − TENU ; ACTIFS = 0 ⇒ max(0, min(BASE, LIBRE)) ; ACTIFS > 0 sous 2C/3 ⇒ max(0, LIBRE),
    sans délai ni limite de deux ; sinon 0."""
    base = base_de(c, charge, plafond)
    if c is None or charge is None:
        # Charge illisible, pression lisible : PRESSION ≥ 2 retient AVANT tout le reste, état inscriptible ou
        # non — sans cette garde, une base à cinq partirait sous une pression mémoire mesurée. Repli conservé :
        # max(0, BASE − ACTIFS), TENU non retenu (CHARGE_POSTE.md § 3, replis non mesurable/non inscriptible).
        if pression in (2, 4):
            return 0, repli(base, pression == 4)
        if not inscriptible:
            return (1 if actifs == 0 else 0), None
        return max(0, base - actifs), None
    l1, l5 = charge[0], charge[1]
    if sature(l1, pression, c):
        # Modérée (1 min > 2C/3 ou PRESSION 2) ⇒ BASE ; sévère (1 min > C, strict, ou PRESSION 4) ⇒ min(3, BASE).
        return 0, repli(base, l1 > c or pression == 4)
    if not inscriptible:
        return (1 if actifs == 0 else 0), None
    libre = plafond - actifs - tenu
    if actifs == 0:
        return max(0, min(base, libre)), None
    if sous_deux_tiers(l1, l5, c):
        return max(0, libre), None
    return 0, None


@dataclass(frozen=True)
class Entree:
    """Une ligne de plafond.json, clé poste + C. `plafond` None = rien d'appris : vaut le DUR du moment.
    La borne DUR s'applique à l'USAGE, jamais sur disque : un plafond déclaré abaissé puis relevé ne laisse
    aucune trace dans la valeur apprise."""
    plafond: int | None
    cree_le: float
    dernier_sature: float | None = None
    relache_le: float | None = None

    def en_json(self, maintenant: float) -> dict[str, object]:
        return {"plafond": self.plafond, "cree_le": self.cree_le, "dernier_sature": self.dernier_sature,
                "relache_le": self.relache_le, "maj": maintenant}


@dataclass(frozen=True)
class Accord:
    ts: float
    actifs: int
    peut_ajouter: int
    tenu: int = 0     # TENU au moment de l'accord ; un ancien relevé sans `tenu` (ou invalide) vaut 0


def calibrer(entree: Entree, *, actifs: int, charge: tuple[float, float, float], pression: int | None, c: int,
             dur: int, accord: Accord | None, maintenant: float) -> tuple[Entree, str]:
    """Un pas de calibration (A3) ; rend l'entrée suivante et `descend|monte|relache|stable`."""
    l1, l5 = charge[0], charge[1]
    appris = entree.plafond if entree.plafond is not None else dur   # PLAFOND_APPRIS, jamais borné sur disque
    est_sature = sature(l1, pression, c)
    # PROBANT : la charge reflète une VAGUE — il faut donc un accord, vieux d'au moins 300 s. Sans accord, aucune
    # vague n'est mesurée : un premier verdict saturé ne fait pas tomber le plafond à 1 (a = ACTIFS − 1 = 0).
    probant = actifs >= 1 and accord is not None and maintenant >= accord.ts + FENETRE_PROBANTE_S
    suivante = replace(entree, dernier_sature=maintenant) if est_sature else entree
    if probant and est_sature and accord is not None:
        # C44 : l'accord, accordés ET tenu compris — le poste entier, jamais l'ACTIFS du relevé (C50).
        a = accord.actifs + accord.peut_ajouter + accord.tenu
        descendu = max(1, min(appris, a - 1))
        return (replace(suivante, plafond=descendu), "descend") if descendu < appris else (suivante, "stable")
    if appris >= dur:
        return suivante, "stable"
    if probant and pression == 1 and sous_moitie(l1, l5, c) and actifs >= appris:
        return replace(suivante, plafond=appris + 1), "monte"
    reference = max(t for t in (suivante.cree_le, suivante.dernier_sature, suivante.relache_le) if t is not None)
    if maintenant - reference >= RELACHE_S:
        return replace(suivante, plafond=appris + 1, relache_le=maintenant), "relache"
    return suivante, "stable"


# --------------------------------------------------------------------------- état (sous verrou)
class VerrouOccupe(Exception):
    """Le verrou est tenu depuis moins de VERROU_PERIME_S et ne s'est pas libéré à temps."""


@contextmanager
def verrou(dossier: Path, horloge: Callable[[], float], attente: float) -> Iterator[None]:
    """Verrou O_EXCL ; un verrou de plus de 30 s (horloge − mtime) est repris. BORNE : deux reprises simultanées
    du même verrou périmé ne sont pas départagées (fenêtre étroite, nommée dans CHARGE_POSTE.md)."""
    chemin = dossier / NOM_VERROU
    fin = time.monotonic() + attente
    for _ in range(100_000):
        try:
            fd = os.open(chemin, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            try:
                age = horloge() - chemin.stat().st_mtime
            except FileNotFoundError:
                continue
            if age > VERROU_PERIME_S:
                with suppress(FileNotFoundError):
                    chemin.unlink()
                continue
            if time.monotonic() >= fin:
                raise VerrouOccupe(f"verrou {chemin} tenu depuis {age:.0f} s") from None
            time.sleep(0.02)
            continue
        break
    else:
        raise VerrouOccupe(f"verrou {chemin} jamais obtenu")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as flux:
            flux.write(f"{os.getpid()} {horloge():.3f}\n")
        yield
    finally:
        with suppress(FileNotFoundError):
            chemin.unlink()


def _remplacer(source: Path, cible: Path) -> None:
    """`os.replace` avec reprise bornée (Windows sous lecteur concurrent : CONVENTIONS_python)."""
    for essai in range(8):
        try:
            os.replace(source, cible)
            return
        except PermissionError:
            if essai == 7:
                raise
            time.sleep(min(0.2, 0.01 * 2 ** essai))


def ecrire_atomique(chemin: Path, texte: str) -> None:
    fd, tmp = tempfile.mkstemp(prefix=chemin.name + ".", suffix=".tmp", dir=chemin.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as flux:
            flux.write(texte)
        _remplacer(Path(tmp), chemin)
    except BaseException:
        with suppress(OSError):
            os.unlink(tmp)
        raise


def _horodatage(brut: object) -> float | None:
    """Un horodatage fini, sinon None — un entier JSON géant (≥ 10^309) compris : OverflowError ⇒ illisible."""
    if not isinstance(brut, (int, float)) or isinstance(brut, bool):
        return None
    try:
        valeur = float(brut)
    except OverflowError:
        return None
    return valeur if math.isfinite(valeur) else None


def _releve_valide(brut: object) -> dict[str, Any] | None:
    if not isinstance(brut, dict):
        return None
    if _horodatage(brut.get("ts")) is None or not isinstance(brut.get("cle"), str):
        return None
    for champ in ("actifs", "peut_ajouter"):
        valeur = brut.get(champ)
        if not isinstance(valeur, int) or isinstance(valeur, bool) or valeur < 0:
            return None
    return brut


def lire_releves(chemin: Path) -> list[dict[str, Any]]:
    """Les relevés lisibles, dans l'ordre du fichier ; une ligne illisible est sautée (et tombe à la réécriture)."""
    try:
        texte = chemin.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return []
    lus = []
    for ligne in texte.splitlines():
        try:
            releve = _releve_valide(json.loads(ligne))
        except (ValueError, RecursionError):  # RecursionError : JSON imbriqué sans fond
            continue
        if releve is not None:
            lus.append(releve)
    return lus


def _entier_naturel(brut: object) -> int:
    """Un entier ≥ 0 hors booléen, sinon 0 (champ `tenu` absent, invalide, ou d'un ancien relevé)."""
    return brut if isinstance(brut, int) and not isinstance(brut, bool) and brut >= 0 else 0


def dernier_accord(releves: Sequence[dict[str, Any]], cle: str) -> Accord | None:
    """Le dernier accord du POSTE (clé poste + C), quelle que soit la session, `tenu` compris (C44, C50)."""
    for releve in reversed(releves):
        ts = _horodatage(releve["ts"])   # jamais `float()` nu : un entier géant lèverait OverflowError
        if releve["cle"] == cle and releve["peut_ajouter"] >= 1 and ts is not None:
            return Accord(ts, releve["actifs"], releve["peut_ajouter"], _entier_naturel(releve.get("tenu")))
    return None


# --------------------------------------------------------------------------- sessions (plafond partagé)
def pid_vivant(pid: int) -> bool:
    """Le processus `pid` existe-t-il ? Signal 0 POSIX (PermissionError : il existe). Sous Windows, `os.kill`
    TERMINERAIT le processus : le PID y est invérifiable, donc SUPPOSÉ vivant (surcompte prudent, borné à 1 h)."""
    if sys.platform.startswith("win"):
        return True
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except (OSError, OverflowError, ValueError):
        return False
    return True


def _pid(brut: object) -> int | None:
    """Un PID lisible (entier ≥ 1, ou chaîne de 1 à 10 chiffres ASCII), sinon None."""
    if isinstance(brut, str) and re.fullmatch(r"[0-9]{1,10}", brut):
        brut = int(brut)
    return brut if isinstance(brut, int) and not isinstance(brut, bool) and brut >= 1 else None


def session_appelante() -> int | None:
    """Le CLAUDE_PID de l'appelant, VÉRIFIÉ vivant (S-01M56Z5GT8, décision de l'orchestrateur) ; sinon None :
    l'appelant est ANONYME (Codex, script, `claude -p` sans la variable — non mesuré)."""
    pid = _pid(os.environ.get("CLAUDE_PID"))
    return pid if pid is not None and pid_vivant(pid) else None


def tenu_de(releves: Sequence[dict[str, Any]], cle: str, session: int | None, actifs: int,
            maintenant: float) -> int:
    """TENU du poste pour cet appelant (étape 2 du plan T-01M56Q23NH, formules ENTIÈRES) :
    identifié — Σ(autres sessions, PID vivant, dernier relevé < 1 h : actifs + garde) + accords anonymes
    < 300 s + max(0, accords propres < 300 s − ACTIFS) ;
    anonyme — Σ(sessions, PID vivant, dernier relevé < 1 h : actifs + garde) + max(0, accords anonymes
    < 300 s − ACTIFS). garde = accordés si le relevé a moins de 300 s OU est à ACTIFS = 0, sinon 0
    (S-01M5BSJ7PB). L'ACTIFS d'une session identifiée n'est jamais déduit des accords anonymes."""
    propres = anonymes = 0
    sessions: dict[int, int] = {}          # dernier relevé (ordre du fichier) de chaque autre session
    for releve in releves:
        ts = _horodatage(releve["ts"])
        if releve["cle"] != cle or ts is None:
            continue
        age = abs(maintenant - ts)
        auteur = _pid(releve.get("claude_pid"))
        if auteur is None:
            if age < RETENUE_S:
                anonymes += releve["peut_ajouter"]
        elif auteur == session:
            if age < RETENUE_S:
                propres += releve["peut_ajouter"]
        elif age < VIE_SESSION_S:
            # S-01M5BSJ7PB (révise S-01M56Z5GT8) : les accordés d'une autre session sont tenus 300 s ; au-delà,
            # seul un accord à ACTIFS = 0 (lanceur à vague bloquante, borné par BASE) reste tenu jusqu'à 1 h —
            # un accord de tout LIBRE à ACTIFS ≥ 1 ne bloque plus le poste une heure.
            garde = releve["peut_ajouter"] if (age < RETENUE_S or releve["actifs"] == 0) else 0
            sessions[auteur] = releve["actifs"] + garde
        else:
            sessions.pop(auteur, None)
    autres = sum(v for pid, v in sessions.items() if pid_vivant(pid))
    if session is None:
        return autres + max(0, anonymes - actifs)
    return autres + anonymes + max(0, propres - actifs)


def lire_plafonds(chemin: Path) -> tuple[dict[str, Any], bool]:
    """(entrées brutes, illisible). Absent ⇒ ({}, False) ; JSON cassé ou forme inattendue ⇒ ({}, True)."""
    try:
        texte = chemin.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}, False
    except (OSError, ValueError):
        return {}, True
    try:
        donnees = json.loads(texte)
    except (ValueError, RecursionError):
        return {}, True
    postes = donnees.get("postes") if isinstance(donnees, dict) else None
    return (postes, False) if isinstance(postes, dict) else ({}, True)


def entree_de(brut: object) -> Entree | None:
    """Une entrée valide, sinon None (illisible ⇒ DUR)."""
    if not isinstance(brut, dict):
        return None
    plafond, cree_le = brut.get("plafond"), _horodatage(brut.get("cree_le"))
    if cree_le is None:
        return None
    if plafond is not None and (not isinstance(plafond, int) or isinstance(plafond, bool) or plafond < 1):
        return None
    dates = []
    for champ in ("dernier_sature", "relache_le"):
        valeur = brut.get(champ)
        if valeur is not None and _horodatage(valeur) is None:
            return None
        dates.append(_horodatage(valeur))
    return Entree(plafond, cree_le, dates[0], dates[1])


# --------------------------------------------------------------------------- déclaration (config_home)
def normaliser_poste(brut: str) -> str:
    """Nom court, minuscules, avant le premier point (`MacBook-Pro.local` ⇒ `macbook-pro`)."""
    court = brut.strip().lower().split(".", 1)[0]
    return re.sub(r"[^a-z0-9_-]", "-", court) or "poste"


def lire_declaration(fichier: Path | None, cle: str) -> tuple[int | None, list[str]]:
    """Le M déclaré pour `cle` (entier quelconque, borné par `dur_de`), sinon None ; illisible ⇒ ignoré, dit."""
    if fichier is None:
        return None, []
    try:
        donnees = json.loads(fichier.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, []
    except (OSError, ValueError, RecursionError) as exc:
        return None, [f"{fichier} illisible ({type(exc).__name__}) : plafond déclaré ignoré"]
    postes = donnees.get("postes") if isinstance(donnees, dict) else None
    if not isinstance(postes, dict):
        return None, [f"{fichier} sans table `postes` : plafond déclaré ignoré"]
    entree = postes.get(cle)
    if entree is None:
        return None, []
    m = entree.get("max") if isinstance(entree, dict) else None
    if not isinstance(m, int) or isinstance(m, bool):
        return None, [f"{fichier} : `max` de {cle} n'est pas un entier — plafond déclaré ignoré"]
    return m, []


# --------------------------------------------------------------------------- le verdict
def ligne_mesure(m: Mesure) -> str:
    """La l.3 : `CHARGE=<1m>/<5m>/<15m> C=<c> PRESSION=<1|2|4|inconnu> EDR_CPU=<x|inconnu>`."""
    charge = "/".join(f"{v:.2f}" for v in m.charge) if m.charge is not None else "inconnu"
    pression = str(m.pression) if m.pression is not None else "inconnu"
    edr = f"{m.edr_cpu:.1f}" if m.edr_cpu is not None else "inconnu"
    return f"CHARGE={charge} C={m.c if m.c is not None else 'inconnu'} PRESSION={pression} EDR_CPU={edr}"


@dataclass(frozen=True)
class Verdict:
    plafond: int
    base: int
    source: str
    peut_ajouter: int
    doit_redescendre_a: int | None
    actifs: int
    mesure: Mesure
    calibration: str
    releves: int
    etat: str
    avertissements: tuple[str, ...] = ()

    def lignes(self) -> list[str]:
        m = self.mesure
        doit = str(self.doit_redescendre_a) if self.doit_redescendre_a is not None else "-"
        sortie = [f"PLAFOND={self.plafond} BASE={self.base} SOURCE={self.source}",
                  f"PEUT_AJOUTER={self.peut_ajouter} DOIT_REDESCENDRE_A={doit} ACTIFS={self.actifs}",
                  ligne_mesure(m),
                  f"CALIBRATION={self.calibration} RELEVES={self.releves} ETAT={self.etat}"]
        if not m.mesurable:
            nom = "Windows" if m.plateforme.startswith("win") else m.plateforme
            sortie.append(TEXTE_NON_MESURABLE.format(plateforme=nom))
        if self.etat != "ok":
            sortie.append(TEXTE_NON_INSCRIPTIBLE)
        return sortie


def _source(mesure: Mesure, illisible: bool, entree: Entree | None, dur: int, m_declare: int | None) -> str:
    """La borne qui LIE : non-mesurable > illisible > appris (< DUR) > declare > defaut."""
    if not mesure.mesurable:
        return "non-mesurable"
    if illisible:
        return "illisible"
    if entree is not None and entree.plafond is not None and entree.plafond < dur:
        return "appris"
    return "declare" if m_declare is not None else "defaut"


def _plafond_sans_mesure(mesure: Mesure, entree: Entree | None, dur: int) -> int:
    """Charge illisible : min(5, DUR), et un plafond APPRIS sous cinq le TIENT — jamais un plancher
    (S-01M54NGJ3S0NHR7BEFZY94PF7W ; revue de clôture commune : PLAFOND=5 rendu sur un appris de 2). À C inconnu,
    la règle ne change pas : la clé `<poste>|inconnu` n'est jamais calibrée, aucun appris n'y est lu."""
    if mesure.c is not None and entree is not None and entree.plafond is not None:
        return min(BASE_MAX, dur, entree.plafond)
    return min(BASE_MAX, dur)


def _verdict_inscrit(actifs: int, mesure: Mesure, maintenant: float, dossier: Path, cle: str, dur: int,
                     m_declare: int | None, avert: list[str]) -> Verdict:
    """Sous le verrou : lire, calibrer, décider, écrire plafond.json s'il change, puis le relevé (l'accord)."""
    chemin_releves, chemin_plafond = dossier / NOM_RELEVES, dossier / NOM_PLAFOND
    releves = lire_releves(chemin_releves)
    postes, fichier_illisible = lire_plafonds(chemin_plafond)
    lue = entree_de(postes[cle]) if cle in postes else None
    illisible = fichier_illisible or (cle in postes and lue is None)
    if illisible:
        avert.append(f"{chemin_plafond} illisible : plafond appris remis à DUR={dur}")
    entree = lue if lue is not None else Entree(None, maintenant)
    accord = dernier_accord(releves, cle)
    suivante, calibration = entree, "stable"
    if mesure.mesurable and mesure.c is not None and mesure.charge is not None:
        suivante, calibration = calibrer(entree, actifs=actifs, charge=mesure.charge, pression=mesure.pression,
                                         c=mesure.c, dur=dur, accord=accord, maintenant=maintenant)
        plafond = min(dur, suivante.plafond) if suivante.plafond is not None else dur   # la borne, à l'USAGE
    else:
        plafond = _plafond_sans_mesure(mesure, entree, dur)
    session = session_appelante()
    tenu = tenu_de(releves, cle, session, actifs, maintenant)
    peut, doit = decider(c=mesure.c, charge=mesure.charge, pression=mesure.pression, actifs=actifs,
                         plafond=plafond, tenu=tenu, inscriptible=True)
    # plafond.json ne se réécrit que s'il CHANGE : descente, montée, relâche, relevé saturé (fenêtre de 24 h de
    # C43) ou réparation d'un fichier illisible — jamais pour y recopier une borne.
    if illisible or calibration != "stable" or suivante.dernier_sature != entree.dernier_sature:
        if fichier_illisible and chemin_plafond.exists():
            _remplacer(chemin_plafond, chemin_plafond.with_name(NOM_PLAFOND + ".illisible"))
        postes = {k: v for k, v in postes.items() if entree_de(v) is not None}
        postes[cle] = suivante.en_json(maintenant)
        ecrire_atomique(chemin_plafond, json.dumps({"version": 1, "postes": postes}, ensure_ascii=False,
                                                   indent=1, sort_keys=True) + "\n")
    charge = mesure.charge
    releves.append({"ts": maintenant, "cle": cle, "actifs": actifs, "peut_ajouter": peut,
                    "charge1": charge[0] if charge else None, "charge5": charge[1] if charge else None,
                    "pression": mesure.pression, "edr_cpu": mesure.edr_cpu, "claude_pid": session, "tenu": tenu})
    releves = releves[-MAX_RELEVES:]
    ecrire_atomique(chemin_releves, "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n"
                                            for r in releves))
    return Verdict(plafond, base_de(mesure.c, mesure.charge, plafond),
                   _source(mesure, illisible, suivante, dur, m_declare), peut, doit, actifs, mesure, calibration,
                   len(releves), "ok", tuple(avert))


def _verdict_non_inscrit(actifs: int, mesure: Mesure, dossier: Path | None, cle: str, dur: int,
                         m_declare: int | None, avert: list[str]) -> Verdict:
    """C31 : rien ne s'écrit ; plafond appris LU s'il se lit (jamais plus haut que DUR), aucune calibration."""
    entree, illisible, nb = None, False, 0
    if dossier is not None:
        try:
            postes, illisible = lire_plafonds(dossier / NOM_PLAFOND)
            entree = entree_de(postes.get(cle))
            illisible = illisible or (cle in postes and entree is None)
            nb = len(lire_releves(dossier / NOM_RELEVES))
        except (OSError, ValueError):
            entree, illisible, nb = None, True, 0
    if mesure.mesurable:
        plafond = min(dur, entree.plafond) if entree is not None and entree.plafond is not None else dur
    else:
        plafond = _plafond_sans_mesure(mesure, entree, dur)
    peut, doit = decider(c=mesure.c, charge=mesure.charge, pression=mesure.pression, actifs=actifs,
                         plafond=plafond, tenu=0, inscriptible=False)
    return Verdict(plafond, base_de(mesure.c, mesure.charge, plafond),
                   _source(mesure, illisible, entree, dur, m_declare), peut, doit, actifs, mesure,
                   "non-inscriptible", nb, "non-inscriptible", tuple(avert))


def executer_verdict(actifs: int, *, mesure: Mesure, horloge: Callable[[], float], dossier: Path | None,
                     fichier_config: Path | None, poste: str, attente_verrou: float = ATTENTE_VERROU_S,
                     avertissements: Sequence[str] = ()) -> Verdict:
    """UN verdict : déclaration, plafond, calibration, accord. Toute impossibilité d'écrire ⇒ C31, jamais un arrêt."""
    avert = list(avertissements)
    cle = f"{poste}|{mesure.c if mesure.c is not None else 'inconnu'}"
    m_declare, dits = lire_declaration(fichier_config, cle) if mesure.c is not None else (None, [])
    avert += dits
    dur = dur_de(mesure.c, m_declare) if mesure.c is not None else BASE_MAX
    if m_declare is not None and mesure.c is not None and not 1 <= m_declare <= mesure.c:
        avert.append(f"plafond déclaré M={m_declare} hors 1..{mesure.c} : borné, DUR={dur}")
    if dossier is not None:
        try:
            dossier.mkdir(parents=True, exist_ok=True, mode=0o700)
            with verrou(dossier, horloge, attente_verrou):
                return _verdict_inscrit(actifs, mesure, horloge(), dossier, cle, dur, m_declare, list(avert))
        except VerrouOccupe as exc:
            avert.append(f"{exc} : verdict non inscrit")
        except OSError as exc:
            avert.append(f"état {dossier} non inscriptible ({type(exc).__name__}: {exc})")
    return _verdict_non_inscrit(actifs, mesure, dossier, cle, dur, m_declare, avert)


# --------------------------------------------------------------------------- CLI
def _poste(brut: str | None) -> str:
    return normaliser_poste(brut if brut is not None else socket.gethostname())


def _cmd_verdict(args: argparse.Namespace, sources: Sources, horloge: Callable[[], float],
                 dormir: Callable[[float], None]) -> int:
    dossier, config, avert = emplacements()
    poste = _poste(args.poste)
    fin = horloge() + args.attendre
    while True:
        verdict = executer_verdict(args.actifs, mesure=mesurer(sources), horloge=horloge, dossier=dossier,
                                   fichier_config=config, poste=poste, avertissements=avert)
        reste = fin - horloge()
        # Non inscriptible SANS surcharge présente : le verdict ne peut plus changer (1 à ACTIFS=0, 0 sinon).
        # Une surcharge présente, elle, peut retomber : on attend, même non inscriptible.
        fige = verdict.etat != "ok" and verdict.doit_redescendre_a is None
        if verdict.peut_ajouter > 0 or reste <= 0 or fige:
            break
        dormir(min(PAS_ATTENTE_S, reste))
    for ligne in verdict.avertissements:
        print(f"AVERTISSEMENT: {ligne}", file=sys.stderr)
    print("\n".join(verdict.lignes()))
    return 0


def _etat_lecture(dossier: Path | None) -> str:
    if dossier is None:
        return "non-inscriptible"
    if dossier.exists():
        return "ok" if os.access(dossier, os.W_OK | os.X_OK) else "non-inscriptible"
    parent = next((p for p in dossier.parents if p.exists()), None)
    return "absent" if parent is not None and os.access(parent, os.W_OK | os.X_OK) else "non-inscriptible"


def _cmd_releve(args: argparse.Namespace, sources: Sources) -> int:
    """Diagnostic : la mesure et l'état tels quels. N'écrit rien, ne prend aucun verrou."""
    dossier, config, avert = emplacements()
    mesure = mesurer(sources)
    cle = f"{_poste(args.poste)}|{mesure.c if mesure.c is not None else 'inconnu'}"
    m_declare, dits = lire_declaration(config, cle) if mesure.c is not None else (None, [])
    dur = dur_de(mesure.c, m_declare) if mesure.c is not None else BASE_MAX
    appris, nb, accord = "-", 0, None
    if dossier is not None:
        postes, illisible = lire_plafonds(dossier / NOM_PLAFOND)
        entree = entree_de(postes.get(cle))
        appris = "illisible" if illisible or (cle in postes and entree is None) else (
            str(entree.plafond) if entree is not None and entree.plafond is not None else "-")
        try:
            releves = lire_releves(dossier / NOM_RELEVES)
        except OSError as exc:
            releves = []
            dits.append(f"{dossier / NOM_RELEVES} illisible ({type(exc).__name__})")
        nb, accord = len(releves), dernier_accord(releves, cle)
    for ligne in avert + dits:
        print(f"AVERTISSEMENT: {ligne}", file=sys.stderr)
    print(ligne_mesure(mesure))
    print(f"SOURCE_CHARGE={mesure.source_charge} EDR={','.join(mesure.edr_noms) or 'inconnu'} "
          f"PLATEFORME={mesure.plateforme}")
    print(f"POSTE={cle} M={m_declare if m_declare is not None else '-'} DUR={dur} PLAFOND_APPRIS={appris} "
          f"RELEVES={nb} DERNIER_ACCORD={f'{accord.ts:.0f}' if accord is not None else '-'}")
    print(f"ETAT={_etat_lecture(dossier)} DOSSIER={dossier if dossier is not None else 'inconnu'}")
    return 0


def _cmd_declarer(args: argparse.Namespace, sources: Sources, horloge: Callable[[], float]) -> int:
    """Geste du pilote : le plafond dur M du poste, hors dépôt (config_home()/parallelisme.json)."""
    _, config, avert = emplacements()
    if config is None:
        for ligne in avert:
            print(f"REFUS: {ligne}", file=sys.stderr)
        print("REFUS: emplacement de la déclaration introuvable ou dans un dépôt — rien n'est écrit",
              file=sys.stderr)
        return 1
    c = _entier_positif(sources.cpu_count())
    if c is None:
        print("REFUS: nombre de cœurs inconnu — la clé poste + C ne se forme pas, rien n'est écrit",
              file=sys.stderr)
        return 1
    cle = f"{_poste(args.poste)}|{c}"
    try:
        donnees = json.loads(config.read_text(encoding="utf-8"))
    except FileNotFoundError:
        donnees = {}
    except (OSError, ValueError, RecursionError) as exc:
        print(f"REFUS: {config} illisible ({type(exc).__name__}) — corrigez-le ou retirez-le", file=sys.stderr)
        return 1
    if not isinstance(donnees, dict) or not isinstance(donnees.get("postes", {}), dict):
        print(f"REFUS: {config} n'a pas la forme attendue — rien n'est écrit", file=sys.stderr)
        return 1
    postes = dict(donnees.get("postes", {}))
    postes[cle] = {"max": args.max, "motif": args.motif,
                   "le": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(horloge()))}
    try:
        config.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        ecrire_atomique(config, json.dumps({**donnees, "version": 1, "postes": postes}, ensure_ascii=False,
                                           indent=1, sort_keys=True) + "\n")
    except OSError as exc:
        print(f"REFUS: {config} non inscriptible ({type(exc).__name__}: {exc})", file=sys.stderr)
        return 1
    dur = dur_de(c, args.max)
    if not 1 <= args.max <= c:
        print(f"AVERTISSEMENT: M={args.max} hors 1..{c} : borné, DUR={dur}", file=sys.stderr)
    print(f"DECLARE POSTE={cle} MAX={args.max} DUR={dur} MOTIF={args.motif}")
    return 0


def _non_negatif(brut: str) -> int:
    try:
        valeur = int(brut)
    except ValueError:
        raise argparse.ArgumentTypeError(f"entier attendu : {brut!r}") from None
    if valeur < 0:
        raise argparse.ArgumentTypeError(f"≥ 0 attendu : {valeur}")
    return valeur


def _attente(brut: str) -> float:
    valeur = nombre(brut)
    if valeur is None or valeur > ATTENTE_MAX_S:
        raise argparse.ArgumentTypeError(f"0..{ATTENTE_MAX_S} secondes attendues : {brut!r}")
    return valeur


def _parseur() -> argparse.ArgumentParser:
    # T-01M5QC86XN, lot P : nom anglais EN TETE, ancien nom francais garde en alias, `dest` ancien explicite,
    # verbe aliase normalise par `set_defaults(commande=<ancien>)` (argparse pose sinon le nom TAPE).
    parseur = argparse.ArgumentParser(
        prog="charge_poste.py",
        description="Station load: the parallelism verdict, self-calibrated at each wave.")
    sous = parseur.add_subparsers(dest="commande", required=True)
    verdict = sous.add_parser("verdict", help="the verdict of ONE wave, self-calibrated")
    verdict.add_argument("--active", "--actifs", dest="actifs", type=_non_negatif, required=True,
                         metavar="N", help="agents of THIS session in flight")
    verdict.add_argument("--wait", "--attendre", dest="attendre", type=_attente, default=0.0, metavar="SECONDS",
                         help=f"wait for a grant up to SECONDS seconds (<= {ATTENTE_MAX_S}; Bash timeout 600000)")
    verdict.add_argument("--station", "--poste", dest="poste", metavar="KEY", help="station key (default: short host name)")
    verdict.set_defaults(commande="verdict")
    releve = sous.add_parser("reading", aliases=["releve"],
                             help="diagnostic: the measurement and the state, writes nothing")
    releve.add_argument("--station", "--poste", dest="poste", metavar="KEY", help="station key (default: short host name)")
    releve.set_defaults(commande="releve")
    declarer = sous.add_parser("declare", aliases=["declarer"],
                               help="pilot gesture: hard cap of the station, outside the repository")
    declarer.add_argument("--max", type=_non_negatif, required=True, help="hard cap (agents)")
    declarer.add_argument("--motive", "--motif", dest="motif", required=True, metavar="S-ID",
                          help="the decision that grounds it (S-...)")
    declarer.add_argument("--station", "--poste", dest="poste", metavar="KEY", help="station key (default: short host name)")
    declarer.set_defaults(commande="declarer")
    return parseur


def main(argv: Sequence[str] | None = None, *, sources: Sources | None = None,
         horloge: Callable[[], float] | None = None, dormir: Callable[[float], None] | None = None) -> int:
    args = _parseur().parse_args(argv)
    sources = sources if sources is not None else sources_du_poste()
    horloge = horloge if horloge is not None else time.time
    dormir = dormir if dormir is not None else time.sleep
    if args.commande == "verdict":
        return _cmd_verdict(args, sources, horloge, dormir)
    if args.commande == "releve":
        return _cmd_releve(args, sources)
    if args.commande != "declarer":  # un verbe non normalise ne tombe jamais dans `declarer` (T-01M5QC86XN)
        print(f"REFUS: commande non reconnue : {args.commande}", file=sys.stderr)
        return 2
    if not args.motif.strip():
        print("REFUS: --motif vide", file=sys.stderr)
        return 2
    return _cmd_declarer(args, sources, horloge)


if __name__ == "__main__":
    sys.exit(main())
