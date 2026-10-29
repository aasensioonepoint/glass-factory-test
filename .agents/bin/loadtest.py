#!/usr/bin/env python3
"""RUNNER DÉTERMINISTE DE TESTS DE CHARGE k6 (T-01M4JC50S6CTJ5HJ697929E6N7, D1a « load-tester »).

POURQUOI CE FICHIER. Un test de charge lancé à la main laisse trois portes
ouvertes : des seuils choisis APRÈS avoir vu la mesure, une cible de production
visée sans décision du pilote, et un verdict lu dans la sortie de k6 sans
recalcul. Ce runner en ferme par CODE ce qui suit, et NOMME le reste : les
seuils se lisent d'un fichier SUIVI par git et PROPRE (jamais d'un argument), une
cible `env: prod` exige une décision pilote tracée qui NOMME la cible, et le
verdict est recalculé en Python sur la synthèse `--summary-export` de k6 puis
confronté au code retour de k6. Mode d'emploi : skill `load-test`. Bibliothèque
standard seule.

La garde prod mord sur l'ÉTIQUETTE `env` d'une configuration que rien ne vérifie
(ni suivie ni propre, `--config` libre) et sur l'URL passée par `-e TARGET_URL` ;
le script n'est inspecté que pour la présence du texte `__ENV.TARGET_URL`. Une
URL de production étiquetée `staging`, ou codée en dur dans le script, part sans
décision pilote (mesuré le 2026-10-08). C'est dit, pas fermé.

CLI (contrat figé) :
  loadtest.py probe [--config F]
  loadtest.py check-config [--config F]
  loadtest.py run --target NOM --profil smoke|charge|stress|endurance
      --script F.js --seuils-de FICHIER [--executor auto|local|cloud]
      [--force-local "<pourquoi>"] [--config F] [--dry-run]
`--seuils` est DÉCLARÉ pour être REFUSÉ (motif `seuils_libres`) : non déclaré,
argparse le rabattrait sur `--seuils-de` par abréviation. Chaque analyseur
porte en plus `allow_abbrev=False`. Une erreur d'arguments est un REFUS (2)
au format JSON, jamais l'usage argparse seul.

CODES DE SORTIE — 0 GO · 1 NO_GO · 2 REFUS · 3 DEGRADED · `--dry-run` admis :
DRY_RUN -> 0, aucun verdict (rien n'est lancé ni tracé). Une ligne JSON sur
stdout ; en DEGRADED, une ligne `COVERAGE DEGRADED — <outil> absent, verdict
absent` sur stderr. Garde de tête (`main`) : toute exception non prévue rend 3
avec `"motif": "erreur interne: <Type>"`, JAMAIS 1 — le 1 d'un Python non
capturé se confondrait avec un NO_GO. Un SIGINT (`KeyboardInterrupt`), SIGTERM ou
SIGHUP (`Interrompu`, gestionnaires posés par `main` sous POSIX, rendus à la
sortie) rend 3 avec `"motif": "interrompu: <SIG>"`, tracé pendant un `run`.

VERDICT (`juger`) — GO exige les trois : rc k6 0, synthèse complète, recalcul
dans les seuils.
  rc k6 hors {0, 99} (97, 105, 107, signal, délai)  -> DEGRADED
  rc k6 0, synthèse absente / illisible / incomplète -> DEGRADED
  rc k6 0, recalcul dans les seuils                  -> GO
  rc k6 0, recalcul hors seuils                      -> NO_GO, `desaccord` nommé
  rc k6 99, recalcul hors seuils                     -> NO_GO
  rc k6 99, recalcul dans les seuils                 -> NO_GO, `desaccord` nommé
  rc k6 99, synthèse inexploitable                   -> NO_GO, `recalcul` dit
     « impossible » — INTERPRÉTATION : k6 a mesuré un franchissement de ses
     propres seuils ; c'est un échec constaté, pas un verdict absent.

SYNTHÈSE k6 — clés lues : `metrics.http_req_duration["p(95)"]` (ms),
`metrics.http_req_failed.value` (ratio 0..1), `metrics.http_reqs.rate`. Une clé
manquante ou non numérique rend DEGRADED, jamais GO : un changement de format
se VOIT, il ne verdit pas. MESURÉ le 2026-10-08 sur k6 v2.3.0 (darwin/arm64) :
forme PLATE ci-dessus (`http_req_duration` = {avg, min, med, max, p(90), p(95)},
`http_req_failed` = {passes, fails, value}, `http_reqs` = {count, rate}) ;
d'autres versions NON MESURÉES. `--summary-export` est « découragée, pas encore
dépréciée » dans la doc k6 latest consultée le 2026-10-08. Un script qui
restreint `summaryTrendStats` sans `p(95)` rend DEGRADED.

SEUILS — `--seuils-de <fichier>` : le fichier existe, est SUIVI par git
(`ls-files` non vide) et PROPRE : les octets LUS (ceux qui sont ensuite parsés
et hachés) ont l'oid du blob de HEAD (`git hash-object --no-filters --stdin`
contre `git rev-parse --verify HEAD:<chemin>`). Ni `--skip-worktree`, ni
`--assume-unchanged`, ni un filtre `clean` ne font passer un fichier modifié
pour propre. Revers fermé : un dépôt qui convertit les fins de ligne
(`core.autocrlf`, `eol=crlf`) ou applique un filtre `smudge` à ce fichier fait
différer les octets du blob — REFUS `seuils_modifie` ; marquez-le `-text -filter`. Hors
dépôt git, REFUS. Il porte EXACTEMENT UNE ligne commençant en colonne 0 par
`SEUILS: p95<=500ms,err<=1%[,rps>=50]`, hors bloc de code clôturé (``` ou ~~~) ;
p95 (`ms`/`s`) et err (`%`) obligatoires. Appels git : `-c core.fsmonitor=false
-c core.hooksPath=/dev/null -C <racine>`, environnement épuré des variables
`GIT_*` sauf GIT_CONFIG_GLOBAL/SYSTEM/NOSYSTEM (précédent : `_garde_env` de
`test_repo_walk_census.py`), borné à 60 s.

PRODUCTION — une cible `env: prod` exige `decision_pilote: S-<8 chiffres>`,
présente comme entrée `kind == "decision"` du journal SPECS (lecture seule, par
l'interface `etat_lecture.py`, qui délègue à `specs.load` : `SPECS.jsonl` OU
`SPECS.json`, les deux refusées ; surcharge
`AGENTS_SPECS_PATH`, prévue pour les bancs et TRACÉE, lue dans la forme de son
suffixe — `.jsonl` ⇒ journal), dont `text` ou
`title` NOMME la cible : l'HÔTE de l'URL en mot entier (témoin de référence),
ou son `name` s'il fait au moins 6 caractères, hors lexique générique, ET porte
au moins un `-`, `_`, `.` ou un chiffre (un mot nu comme « production » se lit
dans toute décision). La frontière de mot est PLUS STRICTE que `\\b` : `.` et
`-` y comptent comme des lettres, pour qu'une décision qui nomme
`staging.shop.exemple` ne vaille pas pour `shop.exemple`. `AGENTS_SPECS_PATH`
est une surcharge de banc : posée, elle est tracée `specs_surcharge` et vaut
pour une cible prod — elle protège contre l'oubli, pas contre une injection.

ADRESSE — une cible `env: local` vise le loopback : hôte `localhost`, `::1` ou
une IPv4 de `127.0.0.0/8`, sinon REFUS `url_invalide` (une adresse interne
étiquetée `local` échapperait à la garde prod). En local, k6 refuse toute IP hors
boucle locale (`--blacklist-ip`) : un script qui code une URL externe en dur
échoue en connexion, jamais en tir. La liste couvre IPv4 hors `127.0.0.0/8` et
IPv6 hors `::1/128` (136 réseaux, `reseaux_hors_boucle`) ; mesuré sur k6 v2.3.0
pour `k6/http` (`0.0.0.0` et `10.255.255.1` rejetées « IP is in a blacklisted
range », 127.0.0.1 servie) ; `k6/ws` et `k6/net/grpc` rejetés aussi (mesuré
v2.3.0) ; `k6/browser`, `k6/websockets` et tout autre module réseau NON MESURÉS.
La résolution DNS d'un nom externe codé en dur part vers le résolveur système
avant que la liste noire juge l'IP : ce trafic DNS n'est pas borné (NON MESURÉ).
Variables de proxy retirées en local (`VARIABLES_PROXY`, toutes casses) :
`--blacklist-ip` ne juge que l'IP composée,
celle d'un proxy en boucle locale (mesuré k6 v2.3.0 : `HTTP_PROXY` sur 127.0.0.1
fait servir par le proxy un GET vers 10.255.255.1, blacklist comprise). Les cibles
`staging`, `preprod` et `prod` ne sont PAS blacklistées et y CONSERVENT le proxy
de l'appelant : rien n'y borne l'adresse que vise le script.

EXÉCUTEUR — `smoke` : local. `charge` : cloud, ou local sous `--force-local`
(`fidelite: "non representative"`). `stress`/`endurance` : cloud seul, le local
est refusé pour FIDÉLITÉ DE CHARGE. Le local est refusé si la charge 1 min
dépasse `max_load1` (config `local.max_load1`, sinon ceil(2/3 × cœurs) ;
`os.cpu_count()` et `getloadavg` lisent l'HÔTE, pas le quota cgroup d'un
conteneur), ou si le verrou de la porte `verify.sh`
(`${VERIFY_WORKTREE_DIR:-<parent>/<dépôt>-verify}.lock/owner`, ligne `pid=`)
porte un pid vivant, ou si le répertoire `.lock` existe SANS `owner` (verify.sh
le tient alors pour tenu). Sans `VERIFY_WORKTREE_DIR`, le verrou est lu pour le
dépôt du runner ET pour chaque worktree que liste `git worktree list --porcelain
-z` (principal compris) : une porte lancée du principal ou d'un AUTRE worktree lié
se voit ; `-z` exige git ≥ 2.36 — en échec, repli sur le seul dépôt principal
(parent du `git rev-parse --git-common-dir` quand il se nomme `.git`).
`VERIFY_WORKTREE_DIR` posée remplace tout. k6
est lancé en liste d'arguments, jamais par un shell, l'URL passée par
`-e TARGET_URL=` (le script DOIT lire `__ENV.TARGET_URL`), sous un délai dur par
profil (`DELAI_PAR_PROFIL`) au-delà duquel son groupe de processus est tué. Un
SIGINT, SIGTERM ou SIGHUP du runner tue ce groupe et rend DEGRADED ; un SIGINT
hérité ignoré (lancement `&` d'un shell non interactif ; `signal.getsignal` =
SIG_IGN, mesuré) reste ignoré : seuls SIGTERM et SIGHUP interrompent alors ;
SIGINT, SIGTERM et SIGHUP sont ensuite IGNORÉS le temps d'écrire la trace (un
second signal reçu PENDANT l'écriture ne la perd plus et le motif garde le
PREMIER ; reçu PLUS TÔT — pendant l'arrêt de k6, `_tuer` attendant jusqu'à
10 s — il REMPLACE le nom au motif, k6 tué et trace écrite (mesuré 2026-10-09) ;
les quelques instructions qui précèdent `_ignorer_signaux` restent sans garde
(non mesuré)) ; `Popen` est DANS le `try` qui tue k6, mais une fenêtre
subsiste à l'intérieur même de `Popen` (k6 démarré, objet pas encore rendu) ; un SIGKILL
du runner ou du groupe de l'appelant laisse k6 aller au bout du script (mesuré) :
seul SIGINT/SIGTERM/SIGHUP ferme la charge. k6 LOCAL hérite de l'environnement
ÉPURÉ des variables de jeton cloud (`VARIABLES_JETON_CLOUD` et tout nom
commençant par un préfixe de `PREFIXES_JETON_CLOUD`) : son script les lirait par
`__ENV` ; et de toute variable dont le nom en majuscules commence par `K6_`
(`K6_CLOUD_*` compris) — options K6_* retirées : k6 les fait primer sur le
script (mesuré v2.3.0 : `K6_NO_THRESHOLDS=true` change un rc 99 en 0,
`K6_VUS`/`K6_ITERATIONS` changent le volume tiré) ; et, pour une cible `env:
local` seulement, des variables de proxy (`VARIABLES_PROXY`, voir ADRESSE). Les
AUTRES variables d'environnement restent visibles du script — n'y lancez qu'un
script de confiance.

ADAPTATEUR CLOUD — CONTRAT du module frère `loadtest_cloud` (livré à part),
importé paresseusement ; absent, le verdict est DEGRADED « adaptateur cloud
absent ». Il expose :
  argv_dry_run(ctx: ContexteRun) -> list[str]   commande qu'il lancerait
  run(ctx: ContexteRun) -> {"rc": int, "summary": dict | None, "logs": str}
      `rc` suit la sémantique k6 (0 / 99 / autre), `summary` la forme de
      `--summary-export` ; il respecte `ctx.delai_s` et écrit sous `ctx.travail`.
  temoin_fin(ctx: ContexteRun) -> bool         True SEULEMENT si le test cloud
      est prouvé terminé côté fournisseur ; tout autre retour rend DEGRADED.
  VARIABLES_JETON (optionnel) : tuple des variables d'environnement dont la
      PRÉSENCE est tracée (`jeton_cloud_present`), jamais la valeur. Défaut :
      `VARIABLES_JETON_CLOUD`.

TRACE — une ligne JSONL par `run` (hors `--dry-run`) dans
`.agents/state/local/loadtest/runs.jsonl` (répertoire : `AGENTS_LOADTEST_STATE`).
Elle porte cible (nom, env, hôte — jamais l'URL complète), profil, exécuteur,
sha256 du script et du fichier de seuils, ligne SEUILS lue, mesures, `volume`
réellement tiré — `null` quand la synthèse manque (absente ou illisible ; de même
sur refus, délai dépassé, interruption : la clé est toujours présente) ; synthèse
présente, `{"http_reqs": http_reqs.count, "vus_max": vus_max.max}` où une clé
absente vaut null (`vus_max` manque d'un court run à `iterations`, mesuré
v2.3.0) —, rc k6,
motif de `--force-local` et `jeton_cloud_present` ; JAMAIS un secret ni une
valeur d'environnement. Une trace impossible à écrire transforme un GO en
DEGRADED : un GO sans trace n'est pas auditable. La fin du journal k6
(`logs_fin`, rc k6 hors {0, 99}) n'entre QUE dans la ligne JSON de stdout, après
rédaction `[REDACTED]` de toute valeur non vide de `VARIABLES_JETON_CLOUD` et de
`VARIABLES_JETON` de l'adaptateur, et de toute valeur d'au moins
`REDACTION_PREFIXE_MIN` (8) caractères d'un nom à préfixe de
`PREFIXES_JETON_CLOUD` : un secret AZURE_* de moins de 8 caractères n'est pas
masqué. Rédaction par valeur EXACTE, sur les `JOURNAL_FIN_OCTETS` derniers
octets du journal : une valeur coupée par le bord de cette fenêtre n'y est pas
reconnue.

PORTÉE OS (L-00000079) : mesuré sous macOS ; Linux ASSUMÉ (mêmes primitives
POSIX) ; Windows NON MESURÉ — sans `os.getloadavg` le local y est refusé sauf
`--force-local`, un pid de verrou y est tenu pour vivant (`os.kill(pid, 0)`
TERMINE le processus sous Windows, et le pid écrit par Git Bash est un pid
MSYS), et `core.hooksPath=/dev/null` n'y a pas été mesuré.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import ipaddress
import json
import math
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone, tzinfo
from pathlib import Path
from types import ModuleType
from typing import Any, NoReturn
from urllib.parse import urlsplit

RC_GO, RC_NO_GO, RC_REFUS, RC_DEGRADED = 0, 1, 2, 3
RC_K6_OK, RC_K6_SEUILS = 0, 99

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DEFAUT = Path(".agents") / "loadtest" / "targets.json"
SPECS_DEFAUT = Path(".agents") / "state" / "specs" / "SPECS.json"
SPECS_JOURNAL_DEFAUT = SPECS_DEFAUT.with_name("SPECS.jsonl")  # T-01M4KKMY43ZKCW1YD2Y8JX9MKH
ETAT_DEFAUT = Path(".agents") / "state" / "local" / "loadtest"
FICHIER_TRACE = "runs.jsonl"

PROFILS = ("smoke", "charge", "stress", "endurance")
ENVS = ("local", "staging", "preprod", "prod")
EXECUTEURS = ("auto", "local", "cloud")
# Délai DUR par profil, en secondes : un PLAFOND de sécurité, jamais la durée du
# test (le script fixe la sienne). Dépassé, k6 est tué et le verdict est DEGRADED.
DELAI_PAR_PROFIL = {"smoke": 15 * 60, "charge": 90 * 60, "stress": 2 * 3600,
                    "endurance": 8 * 3600}

# Les mots nus sont aussi écartés par la règle de forme (`NOM_FORME_RE`) ; les
# formes à séparateur ne le sont QUE par ce lexique — ce sont elles qui le font mordre.
LEXIQUE_NOM_GENERIQUE = frozenset({"prod", "api", "web", "app", "local", "staging", "preprod",
                                   "pre-prod", "pre_prod", "non-prod", "front-end", "back-end"})
NOM_CIBLE_MIN = 6
NOM_FORME_RE = re.compile(r"[-_.0-9]")
BOUCLE_LOCALE = ipaddress.ip_network("127.0.0.0/8")
BOUCLE_LOCALE_V6 = ipaddress.ip_network("::1/128")
DECISION_RE = re.compile(r"S-\d{8}")
HEURE_RE = re.compile(r"([01]\d|2[0-3]):([0-5]\d)")
FIN_DE_JOURNEE = "24:00"
MARQUEUR_SCRIPT = "__ENV.TARGET_URL"
PREFIXE_SEUILS = "SEUILS:"
CLOTURE_RE = re.compile(r"(`{3,}|~{3,})(.*)")
CLES_SYNTHESE = (("http_req_duration", "p(95)"), ("http_req_failed", "value"),
                 ("http_reqs", "rate"))
VARIABLES_JETON_CLOUD = ("K6_CLOUD_TOKEN", "K6_CLOUD_STACK_ID")
PREFIXES_JETON_CLOUD = ("AZURE_",)
VARIABLES_PROXY = frozenset({"http_proxy", "https_proxy", "all_proxy", "no_proxy"})  # comparées en minuscules
REDACTION = "[REDACTED]"
REDACTION_PREFIXE_MIN = 8  # en deçà, une valeur AZURE_* (« 1 », « json ») n'est pas un secret plausible
PREFIXE_OPTIONS_K6 = "K6_"
SIGNAUX_INTERRUPTION = ("SIGTERM", "SIGHUP")  # SIGINT : KeyboardInterrupt, natif
GIT_DELAI_S = 60
_GIT_CONSERVE = ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM")
_HORS_DEPOT = "not a git repository"
_POSIX = os.name == "posix"
JOURNAL_FIN_OCTETS = 4096

_CLES_RACINE = {"local", "targets"}
_CLES_LOCAL = {"max_load1"}
_CLES_CIBLE = {"name", "url", "env", "allowed_profiles", "fenetre", "decision_pilote"}
_CLES_FENETRE = {"debut", "fin", "tz"}


class Refus(Exception):
    """La demande est refusée (exit 2) ; `motif` est un code stable, `detail` le dit."""

    def __init__(self, motif: str, detail: str) -> None:
        super().__init__(f"{motif}: {detail}")
        self.motif = motif
        self.detail = detail


class Degrade(Exception):
    """Le verdict est absent (exit 3) : `outil` nomme ce qui manque."""

    def __init__(self, outil: str, motif: str, **extra: object) -> None:
        super().__init__(f"{outil}: {motif}")
        self.outil = outil
        self.motif = motif
        self.extra = extra


class Interrompu(BaseException):
    """SIGTERM ou SIGHUP reçu : levée dans le fil principal, comme KeyboardInterrupt
    pour SIGINT, pour que `executer_local` tue le groupe k6 avant de rendre 3."""


def _sur_signal(signum: int, _frame: object) -> NoReturn:
    raise Interrompu(signal.Signals(signum).name)


def _nom_interruption(e: BaseException) -> str:
    return "SIGINT" if isinstance(e, KeyboardInterrupt) else str(e)


@dataclass(frozen=True)
class Fenetre:
    debut_min: int
    fin_min: int
    tz: str
    debut: str
    fin: str


@dataclass(frozen=True)
class Cible:
    nom: str
    url: str
    env: str
    hote: str
    profils: tuple[str, ...]
    fenetre: Fenetre
    decision_pilote: str | None


@dataclass(frozen=True)
class Config:
    chemin: Path
    max_load1: float | int | None
    cibles: tuple[Cible, ...]

    def cible(self, nom: str) -> Cible:
        for c in self.cibles:
            if c.nom == nom:
                return c
        connues = ", ".join(c.nom for c in self.cibles)
        raise Refus("cible_inconnue", f"cible « {nom} » absente de {self.chemin} (connues : {connues})")


@dataclass(frozen=True)
class Seuils:
    p95_ms: float
    err_ratio: float
    rps_min: float | None

    def en_dict(self) -> dict:
        return {"p95_ms": self.p95_ms, "err_ratio": self.err_ratio, "rps_min": self.rps_min}


@dataclass(frozen=True)
class SourceSeuils:
    chemin: str
    sha256: str
    ligne: str

    def en_dict(self) -> dict:
        return {"chemin": self.chemin, "sha256": self.sha256, "ligne": self.ligne}


@dataclass(frozen=True)
class Mesures:
    p95_ms: float
    err_ratio: float
    rps: float

    def en_dict(self) -> dict:
        return {"p95_ms": self.p95_ms, "err_ratio": self.err_ratio, "rps": self.rps}


@dataclass
class ContexteRun:
    """Ce que reçoit un exécuteur (local ou adaptateur cloud)."""

    cible: Cible
    profil: str
    script: Path
    script_sha256: str
    seuils: Seuils
    delai_s: int
    executeur: str
    fidelite: str | None
    force_local: str | None
    travail: Path | None = None
    extra: dict = field(default_factory=dict)

    @property
    def url(self) -> str:
        return self.cible.url

    @property
    def summary_path(self) -> Path:
        return (self.travail or Path("<tmp>")) / "summary.json"


# --- configuration -------------------------------------------------------------

def chemin_config(arg: str | None) -> Path:
    """`--config` sinon `.agents/loadtest/targets.json` (absent du kit)."""
    return Path(arg) if arg else ROOT / CONFIG_DEFAUT


def _cles_connues(brut: dict, connues: set[str], ou: str) -> None:
    inconnues = sorted(k for k in brut if k not in connues and not str(k).startswith("_"))
    if inconnues:
        raise Refus("config_invalide", f"{ou} : clé(s) inconnue(s) {inconnues} (admises : {sorted(connues)})")


def _nombre_positif(v: object, ou: str) -> float | int:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
        raise Refus("config_invalide", f"{ou} : nombre strictement positif attendu, lu {v!r}")
    return v


def charger_config(chemin: Path) -> Config:
    """Lit et valide la config ; toute faute de schéma est un REFUS nommé."""
    if not chemin.is_file():
        raise Refus("config_absente", f"fichier de config introuvable : {chemin}")
    try:
        brut = json.loads(chemin.read_text(encoding="utf-8"))
    except ValueError as e:
        raise Refus("config_invalide", f"{chemin} : JSON illisible ({type(e).__name__})") from e
    except OSError as e:
        raise Refus("config_invalide", f"{chemin} : illisible ({type(e).__name__})") from e
    if not isinstance(brut, dict):
        raise Refus("config_invalide", f"{chemin} : un objet JSON est attendu à la racine")
    _cles_connues(brut, _CLES_RACINE, "racine")
    local = brut.get("local", {})
    if not isinstance(local, dict):
        raise Refus("config_invalide", "`local` : objet attendu")
    _cles_connues(local, _CLES_LOCAL, "local")
    plafond = local.get("max_load1")
    plafond = None if plafond is None else _nombre_positif(plafond, "local.max_load1")
    cibles_brutes = brut.get("targets")
    if not isinstance(cibles_brutes, list) or not cibles_brutes:
        raise Refus("config_invalide", "`targets` : liste non vide attendue")
    cibles = tuple(_cible(c, i) for i, c in enumerate(cibles_brutes))
    noms = [c.nom for c in cibles]
    doublons = sorted({n for n in noms if noms.count(n) > 1})
    if doublons:
        raise Refus("config_invalide", f"noms de cible en double : {doublons}")
    return Config(chemin=chemin, max_load1=plafond, cibles=cibles)


def _cible(brut: object, i: int) -> Cible:
    ou = f"targets[{i}]"
    if not isinstance(brut, dict):
        raise Refus("config_invalide", f"{ou} : objet attendu")
    _cles_connues(brut, _CLES_CIBLE, ou)
    nom = brut.get("name")
    if not isinstance(nom, str) or not nom.strip() or nom != nom.strip():
        raise Refus("config_invalide", f"{ou}.name : chaîne non vide sans espace de bord attendue")
    env = brut.get("env")
    if env not in ENVS:
        raise Refus("config_invalide", f"cible « {nom} » : env {env!r} hors de {list(ENVS)}")
    profils = brut.get("allowed_profiles")
    if (not isinstance(profils, list) or not profils
            or any(p not in PROFILS for p in profils) or len(set(profils)) != len(profils)):
        raise Refus("config_invalide",
                    f"cible « {nom} » : allowed_profiles doit lister sans doublon des profils de {list(PROFILS)}")
    decision = brut.get("decision_pilote")
    if decision is not None and not isinstance(decision, str):
        raise Refus("config_invalide", f"cible « {nom} » : decision_pilote doit être une chaîne")
    url = brut.get("url")
    return Cible(nom=nom, url=url, env=env, hote=valider_url(url, nom, env), profils=tuple(profils),
                 fenetre=_fenetre(brut.get("fenetre"), nom), decision_pilote=decision or None)


def valider_url(url: object, nom: str, env: str) -> str:
    """http(s) seulement, sans userinfo, query ni fragment ; rend l'hôte.
    `env == "local"` exige le loopback (`hote_boucle_locale`) ; les autres envs
    ne sont pas filtrés par l'adresse."""
    if not isinstance(url, str) or not url:
        raise Refus("url_invalide", f"cible « {nom} » : url absente")
    if any(c.isspace() or ord(c) < 0x20 or ord(c) == 0x7F or c == "\\" for c in url):
        raise Refus("url_invalide", f"cible « {nom} » : url porteuse d'espace, de caractère de contrôle ou d'antislash")
    try:
        parts = urlsplit(url)
    except ValueError as e:
        raise Refus("url_invalide", f"cible « {nom} » : url mal formée ({e})") from e
    if parts.scheme.lower() not in ("http", "https"):
        raise Refus("url_invalide", f"cible « {nom} » : schéma {parts.scheme!r} refusé (http ou https)")
    if "@" in parts.netloc:
        raise Refus("url_invalide", f"cible « {nom} » : url porteuse d'identifiants (userinfo) refusée")
    if "?" in url or parts.query:
        raise Refus("url_invalide", f"cible « {nom} » : url porteuse d'une query refusée")
    if "#" in url:
        raise Refus("url_invalide", f"cible « {nom} » : url porteuse d'un fragment refusée")
    try:
        _ = parts.port
    except ValueError as e:
        raise Refus("url_invalide", f"cible « {nom} » : port invalide") from e
    if not parts.hostname:
        raise Refus("url_invalide", f"cible « {nom} » : hôte absent")
    if env == "local" and not hote_boucle_locale(parts.hostname):
        raise Refus("url_invalide", f"cible « {nom} » : env local hors loopback (hôte {parts.hostname!r}) — "
                                    "localhost, ::1 ou 127.0.0.0/8 seulement")
    return parts.hostname


def hote_boucle_locale(hote: str) -> bool:
    """`localhost`, `::1` ou une IPv4 de 127.0.0.0/8 ; toute autre forme (nom, IPv4
    abrégée ou décimale, IPv6 mappée, zone) est hors loopback."""
    if hote == "localhost":
        return True
    try:
        adresse = ipaddress.ip_address(hote)
    except ValueError:
        return False
    if isinstance(adresse, ipaddress.IPv4Address):
        return adresse in BOUCLE_LOCALE
    return adresse == ipaddress.IPv6Address("::1")


def _minutes(valeur: object, nom: str, cle: str) -> int:
    if cle == "fin" and valeur == FIN_DE_JOURNEE:
        return 24 * 60
    m = HEURE_RE.fullmatch(valeur) if isinstance(valeur, str) else None
    if not m:
        raise Refus("config_invalide", f"cible « {nom} » : fenetre.{cle} {valeur!r} hors format HH:MM")
    return int(m.group(1)) * 60 + int(m.group(2))


def _fenetre(brut: object, nom: str) -> Fenetre:
    if not isinstance(brut, dict):
        raise Refus("config_invalide", f"cible « {nom} » : fenetre {{debut, fin, tz}} obligatoire")
    _cles_connues(brut, _CLES_FENETRE, f"cible « {nom} ».fenetre")
    debut = _minutes(brut.get("debut"), nom, "debut")
    fin = _minutes(brut.get("fin"), nom, "fin")
    if debut == fin:
        raise Refus("config_invalide", f"cible « {nom} » : fenêtre vide (debut == fin) ; journée entière : 00:00-24:00")
    tz = brut.get("tz")
    if not isinstance(tz, str) or not tz:
        raise Refus("config_invalide", f"cible « {nom} » : fenetre.tz obligatoire (ex. Europe/Paris)")
    return Fenetre(debut_min=debut, fin_min=fin, tz=tz, debut=brut["debut"], fin=brut["fin"])


# --- fenêtre horaire -------------------------------------------------------------

def zone(tz: str) -> tzinfo:
    """ZoneInfo(tz) ; module ou fuseau indisponible = REFUS (jamais l'heure locale)."""
    try:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    except ImportError as e:
        raise Refus("fuseau_indisponible", "module zoneinfo indisponible") from e
    try:
        return ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError, OSError) as e:
        raise Refus("fuseau_indisponible", f"fuseau {tz!r} indisponible ({type(e).__name__})") from e


def horloge(fuseau: tzinfo) -> datetime:
    """Heure courante dans `fuseau` — point d'injection des bancs."""
    return datetime.now(fuseau)


def dans_fenetre(fenetre: Fenetre, maintenant: datetime) -> bool:
    """[debut, fin) à la minute ; debut > fin passe minuit ; fin 24:00 = fin de journée."""
    m = maintenant.hour * 60 + maintenant.minute
    if fenetre.debut_min < fenetre.fin_min:
        return fenetre.debut_min <= m < fenetre.fin_min
    return m >= fenetre.debut_min or m < fenetre.fin_min


def verifier_fenetre(cible: Cible) -> None:
    maintenant = horloge(zone(cible.fenetre.tz))
    if not dans_fenetre(cible.fenetre, maintenant):
        f = cible.fenetre
        raise Refus("hors_fenetre", f"cible « {cible.nom} » : {maintenant:%H:%M} ({f.tz}) hors de la "
                                    f"fenêtre {f.debut}-{f.fin}")


# --- production : décision pilote qui nomme la cible ------------------------------

def chemin_specs() -> Path:
    """La surcharge `AGENTS_SPECS_PATH`, sinon le journal `SPECS.jsonl` s'il existe, sinon `SPECS.json` — le chemin
    TRACÉ ; la lecture sans surcharge passe par l'interface `etat_lecture`, qui voit aussi les deux formes."""
    surcharge = os.environ.get("AGENTS_SPECS_PATH")
    if surcharge:
        return Path(surcharge)
    journal = ROOT / SPECS_JOURNAL_DEFAUT
    return journal if journal.exists() else ROOT / SPECS_DEFAUT


_ETAT_MOD: ModuleType | None = None


def _etat_module() -> ModuleType:
    """L'interface `etat_lecture.py`, frère de CE fichier, chargée PARESSEUSEMENT PAR CHEMIN sous le nom privé
    `_loadtest_etat_lecture` — jamais par un `import` nu, qu'un `python3 -I` (dossier du script hors de `sys.path`)
    refuserait —, enregistrée AVANT son exécution (T-00000134) et retirée si elle échoue. MISE EN CACHE au niveau
    module : UNE instance de l'interface par processus, celle qu'un banc patche. La réutilisation du PROPRIÉTAIRE
    `specs` vit dans l'interface : ce sont deux niveaux distincts. Absente ⇒ `OSError`."""
    global _ETAT_MOD
    if _ETAT_MOD is None:
        import importlib.util

        chemin = Path(__file__).resolve().with_name("etat_lecture.py")
        spec = importlib.util.spec_from_file_location("_loadtest_etat_lecture", chemin) if chemin.is_file() else None
        if spec is None or spec.loader is None:
            raise FileNotFoundError(f"{chemin} : module frère absent")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(spec.name, None)
            raise
        _ETAT_MOD = module
    return _ETAT_MOD


def _entrees_specs(chemin: Path) -> list:
    surcharge = bool(os.environ.get("AGENTS_SPECS_PATH"))
    if surcharge and not chemin.is_file():
        raise Refus("specs_absent", f"SPECS introuvable ({chemin}) : la décision pilote est invérifiable")
    if not surcharge or chemin.suffix == ".jsonl":
        # SANS SURCHARGE : l'interface lit SA racine (`ROOT` lu à l'appel), quelle que soit la forme — `chemin` n'est
        # que le chemin TRACÉ ; « absent » ssi aucune forme (`.exists()`) ; les deux formes refusées. Surcharge
        # `.jsonl` : `entrees_journal_specs` de ce fichier. TROIS SITES DE REFUS, dans cet ordre, chacun nomme le
        # module en échec : (a) l'interface inchargeable ; (b) `erreurs_de_lecture("specs")`, appelé AVANT le `try`
        # de lecture — c'est lui qui charge le propriétaire, sans quoi un `specs.py` absent serait rapporté par (c) ;
        # (c) `present` puis la lecture, sous le tuple pris en (b).
        try:
            el = _etat_module()
        except (OSError, ImportError) as e:
            raise Refus("specs_illisible",
                        f"{chemin} : module etat_lecture.py inchargeable ({type(e).__name__})") from e
        try:
            erreurs = el.erreurs_de_lecture("specs")
        except (OSError, ImportError) as e:
            raise Refus("specs_illisible", f"{chemin} : module specs.py inchargeable ({type(e).__name__})") from e
        try:
            absent = not surcharge and not el.present(ROOT, "specs")
            entrees = [] if absent else (el.entrees_journal_specs(chemin) if surcharge else el.entrees_specs(ROOT))
        except (*erreurs, OSError, ValueError) as e:
            raise Refus("specs_illisible", f"{chemin} : journal illisible ou en deux formes ({e})") from e
        if absent:
            raise Refus("specs_absent", f"SPECS introuvable ({chemin}) : la décision pilote est invérifiable")
        return entrees
    # Surcharge `.json` : lecture BRUTE de ce fichier (résidu inscrit au cliquet `test_lecture_etat_cliquet.py`).
    try:
        data = json.loads(chemin.read_text(encoding="utf-8"))
    except ValueError as e:
        raise Refus("specs_illisible", f"{chemin} : JSON illisible ({type(e).__name__})") from e
    except OSError as e:
        raise Refus("specs_illisible", f"{chemin} : illisible ({type(e).__name__})") from e
    entrees = data.get("entries") if isinstance(data, dict) else None
    if not isinstance(entrees, list):
        raise Refus("specs_illisible", f"{chemin} : clé `entries` (liste) absente")
    return entrees


def nomme(texte: str, terme: str) -> bool:
    """`terme` en MOT ENTIER, casse repliée ; `.` et `-` comptent comme des lettres
    (un sous-domaine ou un suffixe ne vaut pas mention), un point final de phrase non."""
    motif = r"(?<![\w.-])" + re.escape(terme.casefold()) + r"(?![\w-]|\.[\w-])"
    return re.search(motif, texte.casefold()) is not None


def verifier_prod(cible: Cible) -> dict:
    """REFUS sauf décision pilote tracée qui nomme l'hôte (ou un nom spécifique :
    >= 6 caractères, hors lexique, porteur d'un `-`, `_`, `.` ou d'un chiffre)."""
    dp = cible.decision_pilote
    if not dp:
        raise Refus("prod_sans_decision", f"cible prod « {cible.nom} » sans decision_pilote "
                                          "(S-<8 chiffres>, kind decision dans SPECS.json)")
    if not DECISION_RE.fullmatch(dp):
        raise Refus("prod_decision_forme", f"cible prod « {cible.nom} » : decision_pilote {dp!r} hors forme S-<8 chiffres>")
    chemin = chemin_specs()
    entrees = [e for e in _entrees_specs(chemin) if isinstance(e, dict) and e.get("id") == dp]
    decision = next((e for e in entrees if e.get("kind") == "decision"), None)
    if decision is None:
        etat = "absente" if not entrees else "présente mais pas de kind decision"
        raise Refus("prod_decision_introuvable", f"{dp} {etat} dans {chemin}")
    texte = "\n".join(str(decision.get(k) or "") for k in ("text", "title"))
    trace = {"id": dp, "specs": str(chemin), "specs_surcharge": bool(os.environ.get("AGENTS_SPECS_PATH"))}
    if nomme(texte, cible.hote):
        return {**trace, "temoin": "hote"}
    nom_admis = (len(cible.nom) >= NOM_CIBLE_MIN and cible.nom.casefold() not in LEXIQUE_NOM_GENERIQUE
                 and NOM_FORME_RE.search(cible.nom) is not None)
    if nom_admis and nomme(texte, cible.nom):
        return {**trace, "temoin": "nom"}
    ecart = f"la décision {dp} ne nomme pas l'hôte « {cible.hote} »"
    if nom_admis:
        ecart += f" ni la cible « {cible.nom} »"
    else:
        ecart += (f" ; le nom « {cible.nom} » n'est pas un témoin admis (moins de {NOM_CIBLE_MIN} "
                  f"caractères, sans `-`, `_`, `.` ni chiffre, ou générique : "
                  f"{sorted(LEXIQUE_NOM_GENERIQUE)})")
    raise Refus("prod_decision_ne_nomme_pas_la_cible", ecart)


# --- seuils : un fichier suivi et propre -------------------------------------------

def _git_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_") or k in _GIT_CONSERVE}
    env["LC_ALL"] = "C"
    env["LANGUAGE"] = ""
    return env


def _argv_git(racine: Path, *args: str) -> list[str]:
    return ["git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null",
            "-C", str(racine), *args]


def _lancer_git(argv: list[str], **options: Any) -> subprocess.CompletedProcess:
    """Environnement épuré, borné ; git absent ou muet = verdict absent (Degrade)."""
    try:
        return subprocess.run(argv, capture_output=True, env=_git_env(), timeout=GIT_DELAI_S,
                              check=False, **options)
    except FileNotFoundError as e:
        raise Degrade("git", "git absent : provenance des seuils invérifiable") from e
    except subprocess.TimeoutExpired as e:
        raise Degrade("git", f"git sans réponse en {GIT_DELAI_S} s : provenance des seuils invérifiable") from e


def _git(racine: Path, *args: str) -> subprocess.CompletedProcess:
    return _lancer_git(_argv_git(racine, *args), text=True, encoding="utf-8", errors="replace")


def _oid_des_octets(racine: Path, data: bytes) -> str:
    """Oid du blob que formeraient `data` TELS QUELS (`--no-filters` : aucun filtre
    clean ni conversion de fin de ligne) — octets en entrée, jamais un chemin."""
    p = _lancer_git(_argv_git(racine, "hash-object", "--no-filters", "--stdin"), input=data)
    if p.returncode != 0:
        raise Refus("seuils_git", f"git hash-object rc={p.returncode} : "
                                  f"{p.stderr.decode('utf-8', errors='replace').strip()}")
    return p.stdout.decode("ascii", errors="replace").strip()


def _provenance(absolu: Path, data: bytes) -> None:
    """REFUS sauf fichier suivi dont les octets `data` — ceux qui seront parsés —
    ont l'oid de son blob dans HEAD. L'index n'est pas consulté pour l'égalité :
    `--skip-worktree`, `--assume-unchanged` et un filtre clean n'y changent rien."""
    p = _git(absolu.parent, "rev-parse", "--show-toplevel")
    if p.returncode != 0:
        if _HORS_DEPOT in p.stderr.lower():
            raise Refus("seuils_hors_depot", f"{absolu} n'est dans aucun dépôt git : seuils non traçables")
        raise Refus("seuils_git", f"git rev-parse rc={p.returncode} : {p.stderr.strip()}")
    racine = Path(p.stdout.strip()).resolve()
    try:
        rel = absolu.relative_to(racine).as_posix()
    except ValueError as e:
        raise Refus("seuils_hors_depot", f"{absolu} hors de la racine git {racine}") from e
    spec = ":(literal)" + rel
    p = _git(racine, "ls-files", "--", spec)
    if p.returncode != 0:
        raise Refus("seuils_git", f"git ls-files rc={p.returncode} : {p.stderr.strip()}")
    if not p.stdout.strip():
        raise Refus("seuils_non_suivi", f"{rel} n'est pas suivi par git : des seuils non commités se réécrivent après la mesure")
    p = _git(racine, "rev-parse", "--verify", "--quiet", f"HEAD:{rel}")
    if p.returncode != 0:
        if _git(racine, "rev-parse", "--verify", "--quiet", "HEAD^{commit}").returncode != 0:
            raise Refus("seuils_git", f"dépôt sans commit HEAD : {rel} ne peut être comparé à HEAD")
        raise Refus("seuils_modifie", f"{rel} absent de HEAD (indexé non commité) : commitez les seuils AVANT la mesure")
    if _oid_des_octets(racine, data) != p.stdout.strip():
        raise Refus("seuils_modifie", f"{rel} diffère de son blob dans HEAD (modifié, indexé non commité, ou "
                                      "masqué par --skip-worktree / --assume-unchanged) : commitez les seuils "
                                      "AVANT la mesure")


def ligne_seuils(texte: str) -> str:
    """L'UNIQUE ligne `SEUILS:` en colonne 0 hors bloc de code clôturé."""
    trouvees: list[str] = []
    ouverte: str | None = None
    for ligne in texte.splitlines():
        m = CLOTURE_RE.match(ligne.strip())
        if ouverte is None:
            if m:
                ouverte = m.group(1)
            elif ligne.startswith(PREFIXE_SEUILS):
                trouvees.append(ligne.strip())
        elif m and m.group(1)[0] == ouverte[0] and len(m.group(1)) >= len(ouverte) and not m.group(2).strip():
            ouverte = None
    if len(trouvees) != 1:
        raise Refus("seuils_lignes", f"{len(trouvees)} ligne(s) `{PREFIXE_SEUILS}` hors bloc de code : exactement une attendue")
    return trouvees[0]


def parser_seuils(ligne: str) -> Seuils:
    """`SEUILS: p95<=500ms,err<=1%[,rps>=50]` -> Seuils ; p95 ET err obligatoires."""
    lus: dict[str, float] = {}
    for brut in ligne[len(PREFIXE_SEUILS):].split(","):
        item = "".join(brut.split())
        cle, valeur = _item_seuil(item)
        if cle in lus:
            raise Refus("seuils_syntaxe", f"seuil `{cle}` en double")
        lus[cle] = valeur
    manquants = [c for c in ("p95", "err") if c not in lus]
    if manquants:
        raise Refus("seuils_incomplets", f"seuil(s) obligatoire(s) absent(s) : {manquants} (p95 ET err)")
    return Seuils(p95_ms=lus["p95"], err_ratio=lus["err"], rps_min=lus.get("rps"))


def _item_seuil(item: str) -> tuple[str, float]:
    m = re.fullmatch(r"p95<=(\d+(?:\.\d+)?)(ms|s)", item)
    if m:
        return "p95", float(m.group(1)) * (1000.0 if m.group(2) == "s" else 1.0)
    m = re.fullmatch(r"err<=(\d+(?:\.\d+)?)%", item)
    if m:
        pourcent = float(m.group(1))
        if pourcent > 100:
            raise Refus("seuils_syntaxe", f"err {pourcent} % > 100 %")
        return "err", pourcent / 100.0
    m = re.fullmatch(r"rps>=(\d+(?:\.\d+)?)", item)
    if m:
        return "rps", float(m.group(1))
    raise Refus("seuils_syntaxe", f"élément de seuil non reconnu : {item!r} (p95<=Nms|Ns, err<=N%, rps>=N)")


def lire_seuils(arg: str) -> tuple[Seuils, SourceSeuils]:
    chemin = Path(arg)
    if not chemin.is_file():
        raise Refus("seuils_fichier", f"fichier de seuils introuvable : {arg}")
    absolu = chemin.resolve()
    try:
        data = absolu.read_bytes()
    except OSError as e:
        raise Refus("seuils_fichier", f"{absolu} illisible ({type(e).__name__})") from e
    _provenance(absolu, data)  # les octets comparés à HEAD sont ceux qui sont parsés et hachés
    try:
        texte = data.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise Refus("seuils_fichier", f"{absolu} n'est pas de l'UTF-8") from e
    ligne = ligne_seuils(texte)
    source = SourceSeuils(chemin=str(absolu), sha256=hashlib.sha256(data).hexdigest(), ligne=ligne)
    return parser_seuils(ligne), source


def lire_script(arg: str) -> tuple[Path, str]:
    chemin = Path(arg)
    try:
        data = chemin.read_bytes()
    except OSError as e:
        raise Refus("script", f"script k6 illisible : {arg} ({type(e).__name__})") from e
    if MARQUEUR_SCRIPT not in data.decode("utf-8", errors="replace"):
        raise Refus("script", f"{arg} ne lit pas {MARQUEUR_SCRIPT} : l'URL cible passe par -e, jamais en dur")
    return chemin.resolve(), hashlib.sha256(data).hexdigest()


# --- exécuteur et gardes locales ----------------------------------------------------

def choisir_executeur(profil: str, demande: str, force_local: str | None) -> tuple[str, str | None]:
    """(exécuteur, fidélité) ; le refus du local se motive par la FIDÉLITÉ de charge."""
    if force_local is not None and not force_local.strip():
        raise Refus("arguments", "--force-local exige un pourquoi non vide")
    if demande == "cloud":
        if force_local:
            raise Refus("arguments", "--executor cloud et --force-local se contredisent")
        return "cloud", None
    if profil in ("stress", "endurance"):
        if demande == "local" or force_local:
            raise Refus("fidelite_de_charge", f"profil {profil} : exécution locale refusée — un poste de "
                                              "développement ne reproduit pas la charge visée (fidélité de charge) ; cloud seul")
        return "cloud", None
    if profil == "charge":
        if force_local:
            return "local", "non representative"
        if demande == "local":
            raise Refus("fidelite_de_charge", "profil charge en local : fidélité de charge non représentative, "
                                              "exige --force-local \"<pourquoi>\"")
        return "cloud", None
    return "local", None


def loadavg() -> list[float] | None:
    fn = getattr(os, "getloadavg", None)
    if fn is None:
        return None
    try:
        return [float(x) for x in fn()]
    except OSError:
        return None


def max_load1(config: Config | None) -> float | int | None:
    """`local.max_load1` de la config, sinon ceil(2/3 × cœurs) ; None si inconnu."""
    if config is not None and config.max_load1 is not None:
        return config.max_load1
    coeurs = os.cpu_count()
    if not coeurs:
        return None
    return -(-2 * coeurs // 3)


def chemin_verrou_porte() -> Path:
    """`${VERIFY_WORKTREE_DIR:-<parent>/<dépôt>-verify}.lock/owner` (verify.sh)."""
    wt = os.environ.get("VERIFY_WORKTREE_DIR") or str(ROOT.parent / f"{ROOT.name}-verify")
    return Path(wt + ".lock") / "owner"


def depot_principal() -> Path | None:
    """Le dépôt principal : parent du `--git-common-dir` s'il se nomme `.git`.
    None hors dépôt, ou pour un sous-module ou un dépôt nu (common-dir autre)."""
    p = _git(ROOT, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if p.returncode != 0 or not p.stdout.strip():
        return None
    commun = Path(p.stdout.strip())
    return commun.parent if commun.name == ".git" else None


def worktrees_du_depot() -> list[Path] | None:
    """Chaque `worktree <chemin>` de `git worktree list --porcelain -z` (principal
    compris) ; None si la commande échoue (`-z` exige git ≥ 2.36, ou hors dépôt)."""
    p = _git(ROOT, "worktree", "list", "--porcelain", "-z")
    if p.returncode != 0:
        return None
    return [Path(champ[len("worktree "):]) for champ in p.stdout.split("\0") if champ.startswith("worktree ")]


def _verrou_de(depot: Path) -> Path:
    return Path(str(depot.parent / f"{depot.name}-verify") + ".lock") / "owner"


def chemins_verrou_porte() -> list[Path]:
    """Le verrou du dépôt du runner ET celui de chaque worktree du dépôt (dédoublonnés) :
    verify.sh pose le sien sous le worktree qui le lance. Repli si la liste échoue :
    le seul principal. `VERIFY_WORKTREE_DIR` posée : lui seul (banc scellé)."""
    chemins = [chemin_verrou_porte()]
    if os.environ.get("VERIFY_WORKTREE_DIR"):
        return chemins
    depots = worktrees_du_depot()
    if depots is None:
        principal = depot_principal()
        depots = [principal] if principal is not None else []
    chemins += [_verrou_de(d) for d in depots]
    return list(dict.fromkeys(chemins))


def _pid_du_verrou(texte: str) -> int | None:
    for ligne in texte.splitlines():
        m = re.fullmatch(r"\s*pid=(\d+)\s*", ligne)
        if m:
            pid = int(m.group(1))
            return pid if pid > 0 else None
    return None


def pid_vivant(pid: int) -> bool:
    """`os.kill(pid, 0)` sans erreur ; EPERM compte mort (parité verify.sh). POSIX seul."""
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def garde_verrou_porte() -> None:
    for owner in chemins_verrou_porte():
        _garde_un_verrou(owner)


def _garde_un_verrou(owner: Path) -> None:
    try:
        texte = owner.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        if owner.parent.is_dir():  # verify.sh : `.lock` sans owner = tenu (lock_refuse_unreadable)
            raise Refus("verrou_de_porte", f"verrou de porte {owner.parent} présent sans `owner` : "
                                           "une porte démarre ou a été abandonnée, indécidable") from None
        return
    except OSError as e:
        raise Refus("verrou_de_porte", f"verrou de porte illisible ({owner}) : {type(e).__name__}") from e
    pid = _pid_du_verrou(texte)
    if pid is None:
        raise Refus("verrou_de_porte", f"verrou de porte sans pid lisible ({owner}) : vivant ou abandonné indécidable")
    if not _POSIX:
        raise Refus("verrou_de_porte", f"verrou de porte pid {pid} : vivacité invérifiable hors POSIX")
    if pid_vivant(pid):
        raise Refus("verrou_de_porte", f"une porte verify.sh tourne (pid {pid}, {owner.parent}) : "
                                       "une mesure locale la fausserait et serait faussée par elle")


def garde_locale(config: Config, force_local: str | None) -> dict:
    garde_verrou_porte()
    charge = loadavg()
    if charge is None:
        if force_local:
            return {"load1": None, "max_load1": None, "charge": "non mesurée (getloadavg indisponible), --force-local"}
        raise Refus("charge_non_mesurable", "os.getloadavg indisponible : exécution locale refusée sans --force-local")
    plafond = max_load1(config)
    if plafond is None:
        raise Refus("charge_non_mesurable", "os.cpu_count() inconnu et local.max_load1 absent de la config")
    if charge[0] > plafond:
        raise Refus("machine_chargee", f"charge 1 min {charge[0]:.2f} > max_load1 {plafond} : mesure locale faussée")
    return {"load1": charge[0], "max_load1": plafond}


# --- exécution ----------------------------------------------------------------------

def reseaux_hors_boucle() -> str:
    """Valeur de `--blacklist-ip` : tout IPv4 hors 127.0.0.0/8, tout IPv6 hors ::1/128."""
    v4 = ipaddress.ip_network("0.0.0.0/0").address_exclude(BOUCLE_LOCALE)
    v6 = ipaddress.ip_network("::/0").address_exclude(BOUCLE_LOCALE_V6)
    return ",".join(str(n) for n in [*sorted(v4), *sorted(v6)])


def argv_local(ctx: ContexteRun, k6: str) -> list[str]:
    """`env: local` : `--blacklist-ip` hors boucle locale ; les autres envs n'en ont pas."""
    argv = [k6, "run", "-e", f"TARGET_URL={ctx.url}", "--summary-export", str(ctx.summary_path)]
    if ctx.cible.env == "local":
        argv += ["--blacklist-ip", reseaux_hors_boucle()]
    return [*argv, str(ctx.script)]


def est_variable_jeton(nom: str) -> bool:
    return nom in VARIABLES_JETON_CLOUD or nom.startswith(PREFIXES_JETON_CLOUD)


def est_option_k6(nom: str) -> bool:
    """`K6_*` (casse ignorée) : k6 la ferait primer sur les options du script."""
    return nom.upper().startswith(PREFIXE_OPTIONS_K6)


def est_variable_proxy(nom: str) -> bool:
    """`HTTP_PROXY`, `https_proxy`… (casse ignorée) : `VARIABLES_PROXY`."""
    return nom.lower() in VARIABLES_PROXY


def env_k6_local(env_cible: str) -> dict[str, str]:
    """L'environnement du runner SANS les variables de jeton cloud (k6 les exposerait
    par `__ENV`) NI les options `K6_*` (k6 les fait primer sur le script) ; et, pour
    `env_cible == "local"`, SANS les variables de proxy : `--blacklist-ip` ne juge
    que l'IP composée, celle d'un proxy en boucle locale (mesuré k6 v2.3.0). Hors
    local le proxy de l'appelant est CONSERVÉ (aucune blacklist n'y tient)."""
    return {k: v for k, v in os.environ.items()
            if not (est_variable_jeton(k) or est_option_k6(k) or (env_cible == "local" and est_variable_proxy(k)))}


def rediger(texte: str, module: ModuleType | None = None) -> str:
    """Remplace par REDACTION, la plus longue d'abord et par valeur exacte, toute
    valeur NON VIDE de `VARIABLES_JETON_CLOUD` et de `VARIABLES_JETON` de
    l'adaptateur, et toute valeur d'au moins `REDACTION_PREFIXE_MIN` caractères d'un
    nom à préfixe de `PREFIXES_JETON_CLOUD` : un secret AZURE_* de moins de 8
    caractères n'est pas masqué (« 1 » ou « json » ne mangent plus un journal)."""
    noms = set(VARIABLES_JETON_CLOUD) | set(getattr(module, "VARIABLES_JETON", None) or ())
    valeurs = {v for k, v in os.environ.items()
               if v and (k in noms or (k.startswith(PREFIXES_JETON_CLOUD) and len(v) >= REDACTION_PREFIXE_MIN))}
    for valeur in sorted(valeurs, key=len, reverse=True):
        texte = texte.replace(valeur, REDACTION)
    return texte


def _tuer(proc: subprocess.Popen) -> None:
    """Tue k6 ET son groupe de processus (POSIX) ; ailleurs le processus seul."""
    try:
        if _POSIX:
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            proc.kill()
    except OSError:
        pass
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass


def _fin_du_journal(chemin: Path) -> str:
    try:
        data = chemin.read_bytes()
    except OSError:
        return ""
    return data[-JOURNAL_FIN_OCTETS:].decode("utf-8", errors="replace")


def lire_synthese(chemin: Path) -> dict | None:
    try:
        data = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def executer_local(ctx: ContexteRun) -> dict:
    """k6 sous délai dur ; délai, signal ou exception tuent son groupe. `Popen` est
    DANS le `try` : un signal reçu entre son retour et l'attente ne laisse plus k6
    orphelin ; une fenêtre subsiste à l'intérieur même de `Popen`."""
    k6 = shutil.which("k6")
    if k6 is None:
        raise Degrade("k6", "k6 absent du PATH")
    journal = ctx.travail / "k6.log"
    proc: subprocess.Popen | None = None
    with open(journal, "wb") as fh:
        try:
            proc = subprocess.Popen(argv_local(ctx, k6), stdin=subprocess.DEVNULL, stdout=fh,
                                    stderr=subprocess.STDOUT, start_new_session=_POSIX,
                                    env=env_k6_local(ctx.cible.env))
            rc = proc.wait(timeout=ctx.delai_s)
        except subprocess.TimeoutExpired as e:
            if proc is not None:  # seul `wait` lève TimeoutExpired : proc est posé
                _tuer(proc)
            raise Degrade(f"k6 (délai dur {ctx.delai_s} s dépassé)",
                          f"délai dur du profil {ctx.profil} dépassé ({ctx.delai_s} s) : k6 tué") from e
        except BaseException:
            if proc is not None:
                _tuer(proc)
            raise
    return {"rc": rc, "summary": lire_synthese(ctx.summary_path), "logs": _fin_du_journal(journal)}


def adaptateur_cloud() -> ModuleType:
    try:
        return importlib.import_module("loadtest_cloud")
    except ImportError as e:
        raise Degrade("adaptateur cloud loadtest_cloud", f"adaptateur cloud absent ({type(e).__name__})") from e


def executer_cloud(ctx: ContexteRun, module: ModuleType) -> dict:
    res = module.run(ctx)
    if (not isinstance(res, dict) or isinstance(res.get("rc"), bool) or not isinstance(res.get("rc"), int)
            or not (res.get("summary") is None or isinstance(res.get("summary"), dict))):
        raise Degrade("adaptateur cloud (résultat hors protocole)", "run(ctx) hors protocole {rc, summary, logs}")
    if module.temoin_fin(ctx) is not True:
        raise Degrade("témoin de fin cloud", "l'adaptateur ne prouve pas la fin du test cloud")
    return {"rc": res["rc"], "summary": res.get("summary"), "logs": str(res.get("logs") or "")}


def jeton_cloud_present(module: ModuleType | None = None) -> bool:
    noms = getattr(module, "VARIABLES_JETON", None) or VARIABLES_JETON_CLOUD
    return any(os.environ.get(n) for n in noms)


# --- verdict ------------------------------------------------------------------------

def mesurer(summary: dict | None) -> Mesures | None:
    """Les trois clés attendues, numériques et finies ; sinon None (synthèse incomplète)."""
    metrics = summary.get("metrics") if isinstance(summary, dict) else None
    if not isinstance(metrics, dict):
        return None
    valeurs: list[float] = []
    for metrique, cle in CLES_SYNTHESE:
        bloc = metrics.get(metrique)
        v = bloc.get(cle) if isinstance(bloc, dict) else None
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            return None
        valeurs.append(float(v))
    p95, err, rps = valeurs
    if p95 < 0 or rps < 0 or not 0 <= err <= 1:
        return None
    return Mesures(p95_ms=p95, err_ratio=err, rps=rps)


def volume(summary: dict | None) -> dict | None:
    """Le volume RÉEL tiré : None si la synthèse manque (absente ou illisible) ;
    sinon `http_reqs.count` et `vus_max.max`, None pour une clé absente ou non
    numérique. Information, jamais un verdict."""
    if not isinstance(summary, dict):
        return None
    metrics = summary.get("metrics")

    def lire(metrique: str, cle: str) -> float | int | None:
        bloc = metrics.get(metrique) if isinstance(metrics, dict) else None
        v = bloc.get(cle) if isinstance(bloc, dict) else None
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            return None
        return v

    return {"http_reqs": lire("http_reqs", "count"), "vus_max": lire("vus_max", "max")}


def depassements(m: Mesures, s: Seuils) -> list[str]:
    out = []
    if m.p95_ms > s.p95_ms:
        out.append(f"p95 {m.p95_ms:g} ms > {s.p95_ms:g} ms")
    if m.err_ratio > s.err_ratio:
        out.append(f"err {m.err_ratio * 100:g} % > {s.err_ratio * 100:g} %")
    if s.rps_min is not None and m.rps < s.rps_min:
        out.append(f"rps {m.rps:g} < {s.rps_min:g}")
    return out


def juger(rc_k6: int, mesures: Mesures | None, seuils: Seuils) -> dict:
    """Table du docstring de module ; les cas sans verdict lèvent Degrade."""
    if rc_k6 not in (RC_K6_OK, RC_K6_SEUILS):
        raise Degrade(f"verdict k6 (rc {rc_k6})", f"rc k6 {rc_k6} hors de {{0, 99}} : exécution non conclusive")
    if mesures is None:
        if rc_k6 == RC_K6_SEUILS:
            return {"verdict": "NO_GO", "depassements": [], "desaccord": None,
                    "recalcul": "impossible : synthèse absente, illisible ou incomplète ; rc k6 99 seul"}
        raise Degrade("synthèse k6", "rc k6 0 mais synthèse --summary-export absente, illisible ou incomplète")
    dep = depassements(mesures, seuils)
    desaccord = None
    if rc_k6 == RC_K6_OK and dep:
        desaccord = "k6 rc 0 (seuils du script tenus) mais recalcul hors seuils du fichier : " + "; ".join(dep)
    elif rc_k6 == RC_K6_SEUILS and not dep:
        desaccord = "k6 rc 99 (seuils du script franchis) mais recalcul dans les seuils du fichier"
    verdict = "GO" if rc_k6 == RC_K6_OK and not dep else "NO_GO"
    return {"verdict": verdict, "depassements": dep, "desaccord": desaccord, "recalcul": "fait"}


# --- sorties et trace -----------------------------------------------------------------

def _emettre(payload: dict) -> None:
    try:
        print(json.dumps(payload, ensure_ascii=True, sort_keys=True, default=str))
        sys.stdout.flush()
    except (OSError, ValueError):
        pass


def _sortie_refus(r: Refus, extra: dict | None = None) -> int:
    _emettre({**(extra or {}), "verdict": "REFUS", "motif": r.motif, "detail": r.detail})
    return RC_REFUS


def _sortie_degrade(d: Degrade, extra: dict | None = None) -> int:
    _emettre({**(extra or {}), **d.extra, "verdict": "DEGRADED", "motif": d.motif})
    try:
        print(f"COVERAGE DEGRADED — {d.outil} absent, verdict absent", file=sys.stderr)
    except (OSError, ValueError):
        pass
    return RC_DEGRADED


def chemin_etat() -> Path:
    surcharge = os.environ.get("AGENTS_LOADTEST_STATE")
    return Path(surcharge) if surcharge else ROOT / ETAT_DEFAUT


def ecrire_trace(enreg: dict) -> Path:
    base = chemin_etat()
    base.mkdir(parents=True, exist_ok=True)
    chemin = base / FICHIER_TRACE
    with open(chemin, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(enreg, ensure_ascii=False, sort_keys=True, default=str) + "\n")
    return chemin


# --- commandes ------------------------------------------------------------------------

def cmd_probe(args: argparse.Namespace) -> int:
    chemin = chemin_config(args.config)
    config, etat = None, "absente"
    if chemin.is_file():
        try:
            config, etat = charger_config(chemin), "valide"
        except Refus as r:
            etat = f"invalide: {r.motif}"
    k6 = shutil.which("k6")
    payload = {"verdict": "OK", "k6": k6, "az": shutil.which("az"), "loadavg": loadavg(),
               "cpu_count": os.cpu_count(), "max_load1": max_load1(config), "os": platform.system(),
               "config": {"chemin": str(chemin), "etat": etat}}
    if k6 is None:
        return _sortie_degrade(Degrade("k6", "k6 absent du PATH"), payload)
    _emettre(payload)
    return RC_GO


def cmd_check_config(args: argparse.Namespace) -> int:
    config = charger_config(chemin_config(args.config))
    cibles = []
    for c in config.cibles:
        zone(c.fenetre.tz)
        cibles.append({"name": c.nom, "env": c.env, "hote": c.hote, "allowed_profiles": list(c.profils),
                       "fenetre": {"debut": c.fenetre.debut, "fin": c.fenetre.fin, "tz": c.fenetre.tz},
                       "decision_pilote": c.decision_pilote})
    _emettre({"verdict": "OK", "config": str(config.chemin), "max_load1": config.max_load1, "cibles": cibles})
    return RC_GO


def _preparer(args: argparse.Namespace, trace: dict) -> ContexteRun:
    """Toutes les gardes, dans l'ordre ; remplit `trace` au fil de l'eau."""
    if args.seuils is not None:
        raise Refus("seuils_libres", "--seuils est refusé : les seuils se lisent d'un fichier suivi et "
                                     "propre, --seuils-de <fichier>")
    manquants = [o for o, v in (("--target", args.target), ("--profil", args.profil),
                                ("--script", args.script), ("--seuils-de", args.seuils_de)) if not v]
    if manquants:
        raise Refus("arguments", f"argument(s) obligatoire(s) absent(s) : {', '.join(manquants)}")
    config = charger_config(chemin_config(args.config))
    cible = config.cible(args.target)
    trace["cible"] = {"nom": cible.nom, "env": cible.env, "hote": cible.hote}
    if args.profil not in cible.profils:
        raise Refus("profil_non_admis", f"profil {args.profil} hors des allowed_profiles de « {cible.nom} » "
                                        f"({list(cible.profils)})")
    verifier_fenetre(cible)
    if cible.env == "prod":
        trace["decision_pilote"] = verifier_prod(cible)
    script, script_sha = lire_script(args.script)
    trace["script"] = {"chemin": str(script), "sha256": script_sha}
    seuils, source = lire_seuils(args.seuils_de)
    trace["seuils_fichier"] = source.en_dict()
    trace["seuils"] = seuils.en_dict()
    executeur, fidelite = choisir_executeur(args.profil, args.executor, args.force_local)
    trace.update(executeur=executeur, fidelite=fidelite)
    if executeur == "local":
        trace["machine"] = garde_locale(config, args.force_local)
    return ContexteRun(cible=cible, profil=args.profil, script=script, script_sha256=script_sha,
                       seuils=seuils, delai_s=DELAI_PAR_PROFIL[args.profil], executeur=executeur,
                       fidelite=fidelite, force_local=args.force_local)


def _plan(ctx: ContexteRun, trace: dict) -> int:
    if ctx.executeur == "local":
        k6 = shutil.which("k6")
        argv = argv_local(ctx, k6 or "k6")
    else:
        k6 = None
        argv = adaptateur_cloud().argv_dry_run(ctx)
        if not isinstance(argv, list) or not all(isinstance(a, str) for a in argv):
            raise Degrade("adaptateur cloud (argv hors protocole)", "argv_dry_run(ctx) doit rendre list[str]")
    _emettre({**trace, "verdict": "DRY_RUN", "argv": argv, "k6": k6, "delai_s": ctx.delai_s})
    return RC_GO


def _executer(ctx: ContexteRun, trace: dict) -> int:
    module = adaptateur_cloud() if ctx.executeur == "cloud" else None
    trace["jeton_cloud_present"] = jeton_cloud_present(module)
    with tempfile.TemporaryDirectory(prefix="loadtest-") as tmp:
        ctx.travail = Path(tmp)
        res = executer_local(ctx) if module is None else executer_cloud(ctx, module)
        ctx.travail = None
    trace["rc_k6"] = res["rc"]
    if res["rc"] not in (RC_K6_OK, RC_K6_SEUILS):
        trace["logs_fin"] = rediger(res["logs"], module)[-1024:]  # rédiger AVANT de couper
    mesures = mesurer(res["summary"])
    trace["mesures"] = mesures.en_dict() if mesures else None
    trace["volume"] = volume(res["summary"])
    jugement = juger(res["rc"], mesures, ctx.seuils)
    trace.update(jugement)
    return RC_GO if jugement["verdict"] == "GO" else RC_NO_GO


def _trace_publique(trace: dict) -> dict:
    """La trace JSONL ne porte NI la fin du journal k6 (URL, en-têtes possibles)."""
    return {k: v for k, v in trace.items() if k != "logs_fin"}


def cmd_run(args: argparse.Namespace) -> int:
    trace: dict = {"horodatage": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "commande": "run", "profil": args.profil, "force_local_motif": args.force_local,
                   "jeton_cloud_present": jeton_cloud_present()}
    rc: int
    try:
        ctx = _preparer(args, trace)
        if args.dry_run:
            return _plan(ctx, trace)
        rc = _executer(ctx, trace)
    except Refus as r:
        trace.update(verdict="REFUS", motif=r.motif, detail=r.detail)
        rc = RC_REFUS
    except Degrade as d:
        trace.update(verdict="DEGRADED", motif=d.motif, outil=d.outil)
        rc = RC_DEGRADED
    except (KeyboardInterrupt, Interrompu) as e:  # le groupe k6 est déjà tué par executer_local
        nom = _nom_interruption(e)
        trace.update(verdict="DEGRADED", motif=f"interrompu: {nom}", outil=f"k6 (run interrompu : {nom})")
        rc = RC_DEGRADED
    if args.dry_run:
        return _sortie_trace(trace, rc)
    _ignorer_signaux()  # un second SIGINT/SIGTERM/SIGHUP ne perd plus la trace ; `main` rétablit
    trace.setdefault("volume", None)  # aucune synthèse lue (refus, délai, interruption) : forme stable
    trace["rc_sortie"] = rc
    try:
        trace["trace"] = str(ecrire_trace(_trace_publique(trace)))
    except OSError as e:
        trace["trace"] = f"non écrite : {type(e).__name__}"
        if rc == RC_GO:
            return _sortie_degrade(Degrade("trace loadtest", f"trace non écrite ({type(e).__name__}) : GO non auditable"), trace)
    return _sortie_trace(trace, rc)


def _sortie_trace(trace: dict, rc: int) -> int:
    if rc == RC_REFUS:
        return _sortie_refus(Refus(trace["motif"], trace["detail"]), trace)
    if rc == RC_DEGRADED:
        return _sortie_degrade(Degrade(trace["outil"], trace["motif"]), trace)
    _emettre(trace)
    return rc


class _Analyseur(argparse.ArgumentParser):
    """Une erreur d'arguments est un REFUS JSON (exit 2), jamais l'usage seul."""

    def error(self, message: str) -> NoReturn:
        raise Refus("arguments", message)


def construire_analyseur() -> argparse.ArgumentParser:
    p = _Analyseur(prog="loadtest.py", allow_abbrev=False,
                   description="Runner déterministe de tests de charge k6 (skill load-test).")
    sous = p.add_subparsers(dest="commande", metavar="{probe,check-config,run}")
    sous.required = True
    pr = sous.add_parser("probe", allow_abbrev=False, help="outils présents, charge machine")
    pr.add_argument("--config")
    cc = sous.add_parser("check-config", allow_abbrev=False, help="valide la config et liste les cibles")
    cc.add_argument("--config")
    r = sous.add_parser("run", allow_abbrev=False, help="lance (ou planifie) un test de charge")
    r.add_argument("--target")
    r.add_argument("--profil", choices=PROFILS)
    r.add_argument("--script")
    r.add_argument("--seuils-de", dest="seuils_de", metavar="FICHIER")
    r.add_argument("--seuils", nargs="?", const="", default=None,
                   help="REFUSÉ (seuils_libres) — utilisez --seuils-de")
    r.add_argument("--executor", choices=EXECUTEURS, default="auto")
    r.add_argument("--force-local", dest="force_local", metavar="POURQUOI")
    r.add_argument("--config")
    r.add_argument("--dry-run", dest="dry_run", action="store_true")
    return p


def _principal(argv: list[str] | None) -> int:
    args = construire_analyseur().parse_args(argv)
    if args.commande == "probe":
        return cmd_probe(args)
    if args.commande == "check-config":
        return cmd_check_config(args)
    return cmd_run(args)


def _installer_signaux() -> dict[int, Any]:
    """SIGTERM et SIGHUP lèvent `Interrompu` (POSIX, fil principal seul) ; rend les
    gestionnaires remplacés — celui de SIGINT compris, que `_ignorer_signaux` remplace
    le temps de la trace — pour que `main` appelé en processus les restitue."""
    anciens: dict[int, Any] = {}
    if not _POSIX:
        return anciens
    anciens[signal.SIGINT] = signal.getsignal(signal.SIGINT)
    for nom in SIGNAUX_INTERRUPTION:
        sig = getattr(signal, nom, None)
        if sig is None:
            continue
        try:
            anciens[sig] = signal.signal(sig, _sur_signal)
        except ValueError:  # hors du fil principal : aucun gestionnaire possible
            break
    return anciens


def _ignorer_signaux() -> None:
    """SIG_IGN sur SIGINT et `SIGNAUX_INTERRUPTION` le temps d'écrire la trace (POSIX,
    fil principal seul) ; `main` rétablit ensuite les gestionnaires d'origine."""
    if not _POSIX:
        return
    for nom in ("SIGINT", *SIGNAUX_INTERRUPTION):
        sig = getattr(signal, nom, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, signal.SIG_IGN)
        except ValueError:  # hors du fil principal
            return


def _rendre_signaux(anciens: dict[int, Any]) -> None:
    for sig, gestionnaire in anciens.items():
        try:
            signal.signal(sig, gestionnaire if gestionnaire is not None else signal.SIG_DFL)
        except (ValueError, TypeError):
            pass


def main(argv: list[str] | None = None) -> int:
    """Gestionnaires SIGTERM/SIGHUP posés (SIGINT noté) le temps de la commande, puis la
    garde de tête ; tous rendus à la sortie."""
    anciens = _installer_signaux()
    try:
        return _garde_de_tete(argv)
    finally:
        _rendre_signaux(anciens)


def _garde_de_tete(argv: list[str] | None) -> int:
    """REFUS 2, DEGRADED 3, interruption 3, et toute exception non prévue 3."""
    try:
        return _principal(argv)
    except Refus as r:
        return _sortie_refus(r)
    except Degrade as d:
        return _sortie_degrade(d)
    except (KeyboardInterrupt, Interrompu) as e:
        nom = _nom_interruption(e)
        return _sortie_degrade(Degrade(f"runner loadtest (interrompu : {nom})", f"interrompu: {nom}"))
    except SystemExit as e:
        if e.code in (0, None):
            raise
        nom = "SystemExit"
    except BaseException as e:  # noqa: BLE001 — garde de tête : jamais le rc 1 d'un Python non capturé
        nom = type(e).__name__
    return _sortie_degrade(Degrade(f"runner loadtest (erreur interne: {nom})", f"erreur interne: {nom}"))


if __name__ == "__main__":
    sys.exit(main())
