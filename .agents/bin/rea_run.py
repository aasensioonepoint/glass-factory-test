#!/usr/bin/env python3
"""RUNNER DÉTERMINISTE DE rea (T-01M5HEJYSJEYA8K3834FZVT60N, déf `reverse-engineer`).

POURQUOI CE FICHIER. La CLI externe rea (`npm rea-agents`, ÉPINGLÉE à `REA_VERSION`) porte, à côté de ses
inspections statiques, des commandes qui installent (`setup`, `update`), enregistrent un serveur MCP, montent
une image disque (`.dmg` par `hdiutil`), lancent des moteurs externes (Ghidra, IDA, Hopper, frida…) ou lisent
stdin. Un agent qui appelle `npx rea-agents …` à la main n'a aucune de ces portes. Ce runner en ferme par CODE
ce qui suit, et NOMME le reste. Bibliothèque standard seule.

CLI (contrat figé) :
  rea_run.py probe [--moteurs]
  rea_run.py run [--decision S-<id>] [--cible <mot>] [--out <dir>] [--moteurs] [--with-optional]
                 [--timeout <s>] <commande> -- [args rea…]
  rea_run.py vue <evidence> [--kind summary]

Code de sortie : 0 OK · 1 rea a rendu non-zéro (Evidence écrite quand même) · 2 REFUS · 3 DEGRADED (verdict
absent : node ou npx absents, node hors `PLAGE_NODE` — porte commune à `probe`, `run` et `vue`, jouée avant
tout lancement de npx —, rea hors version (`probe` seul : `run` et `vue` passent `rea-agents@<REA_VERSION>`
épinglé), délai, interruption, trace non écrite, erreur interne).
stdout : UNE ligne JSON (ASCII) `{rc, chemin, sha256, taille, motif}` — plus `detail` sur un refus (pour
`decision_requise`, la règle qui a mordu : nom, `realpath`, contenu ou bundle), `rc_rea` quand rea a tourné,
`cible` et `commande` quand ils sont connus, `specs_surcharge` quand une décision a été lue (vrai : lue sous
`AGENTS_SPECS_PATH`, et une note le dit aussi sur stderr) ; `probe` y ajoute `node`, `rea`, `doctor_rc`, `moteurs_presents`
et `moteurs_absents_env_retiree` (ou `moteurs_absents` sous `--moteurs`). stderr, en DEGRADED :
`COVERAGE DEGRADED — <cause>`.

CE QUI EST FERMÉ PAR CODE.
* Liste blanche de 32 commandes (`COMMANDES`), chacune avec sa liste FERMÉE d'options, leur genre (booléenne,
  à valeur, chemin) et l'arité de ses positionnels, relevées sur `--help`/`--schema` 6.7.0. Refus sans
  condition : `setup`, `update`, `uninstall`, `mcp`, `environment-*`, tout `@latest`, `inspect-elf-notes`,
  `inspect-il`, `inspect-model-artifact`, les builtins d'incur `completions`, `skills` et son alias `skill`, et
  `rea` lui-même (qu'incur lit comme préfixe de ses builtins : `rea mcp add`, `rea skills add`). Toute autre
  commande du dist exige une décision (`--decision`).
* Lecture jeton par jeton : jeton vide refusé (`jeton_vide`), jeton à un seul tiret et `--` seul refusés,
  builtins incur refusés partout (`--mcp`, `--update`, `--format`… : `option_refusee`), nom camel ramené en
  kebab puis cherché dans la liste de la commande, `--x=v` = valeur (tiret admis), `--x v` = valeur refusée si
  elle commence par `-` (`valeur_a_tiret`), positionnels comptés contre l'arité (`positionnel_en_trop`,
  `positionnel_manquant`). Les arguments sont NORMALISÉS (`--nom=valeur`) avant d'être passés.
* Chemins : tout segment `..` d'un jeton chemin est refusé (`segment_parent`) ; un chemin relatif est JOINT au
  répertoire de l'appelant par `os.path.join`, SANS normalisation (ni `abspath` ni `normpath`, que ce fichier
  n'appelle pas) : la chaîne jointe est celle qu'on juge et celle qu'on passe. rea, au tag, ne retire que `.`
  et `//` d'un chemin sans `..` (`callerPath.js`) : il nomme alors le même fichier.
* Règle DMG/PKG ⇒ décision, quelle que soit la commande, pour tout chemin dont la chaîne jointe OU son
  `realpath` finit par `.dmg`/`.pkg` (casse ignorée), OU dont le fichier régulier atteint porte `xar!` en
  tête ou `koly` 512 octets avant la fin, OU qui est un bundle `.app` contenant un tel fichier. Le parcours
  d'un `.app` suit les liens avec garde de cycle mais reste CONFINÉ : une entrée dont `realpath` sort de
  `realpath(bundle)` n'est ni lue ni comptée ; au-delà de `BORNE_INVENTAIRE` entrées, `inventaire_trop_grand`.
  L'appartenance au bundle se juge par IDENTITÉ D'INODE des ancêtres, jamais par comparaison de chaînes (un
  volume insensible à la casse, APFS par défaut, nomme le même dossier sous deux casses). Une valeur ʳ
  RELATIVE (`--source-path`, `--relative-path`) est passée telle quelle mais jugée jointe à la racine de
  l'application (le 1er positionnel chemin, d'où rea la résout ; à défaut, le cwd appelant).
* Décision : `S-<8 chiffres>` ou `S-<ULID>` (`decision_forme`), entrée `kind == "decision"` du journal specs
  (lu par l'interface `etat_lecture.py`, ou la surcharge `AGENTS_SPECS_PATH` prévue pour les bancs — qu'un
  appelant qui tient Bash peut aussi poser sur un faux journal : elle n'est pas refusée, elle est TRACÉE,
  `decision_lue.specs_surcharge` dans `runs.jsonl`) qui NOMME
  en mot entier la cible (nom de base de la chaîne jointe ou de son `realpath`), la commande, et chaque
  option sous décision passée (`--snapshot`, `--provider`, toute option d'une commande hors liste,
  `--moteurs`, `--with-optional`). La cible est le 1er positionnel chemin ; sans lui, ou hors liste,
  `--cible <mot>` est exigé et doit égaler le nom de base d'un jeton rea.
* `--out`, `--snapshot` et l'état : un chemin DANS le dépôt hors de `.agents/state/local/` est refusé
  (`out_suivi`). « Dans le dépôt » se juge sur le `realpath` du chemin, par IDENTITÉ D'INODE de ses ancêtres
  existants (le dossier peut ne pas exister encore), contre la racine de CE checkout ET celle du checkout
  principal quand ce fichier tourne dans un worktree lié — LU dans `.git`, `gitdir` et `commondir`, validé,
  sans lancer `git` (un `git` posé sur le PATH ne peut rien y dire) ; illisible ou incohérent : seule la
  racine de ce checkout est jugée, et une note le dit sur stderr. Un autre clone sans lien git avec celui-ci
  n'est pas vu. `--snapshot` vers un fichier EXISTANT à plusieurs liens durs est refusé (`out_suivi`) : un
  lien dur vers un fichier suivi n'a pas d'ancêtre dans le dépôt.
* Exécution : `npx -y rea-agents@<REA_VERSION> <commande> <args normalisés> --format json`, en liste, jamais
  de shell ; `stdin` fermé (`/dev/null`) ; `cwd` = un répertoire temporaire VIDE, supprimé après (un `.npmrc`
  ou un `node_modules` posé dans `--out` ou chez l'appelant n'est donc pas lu comme configuration de projet ;
  si un ancêtre de ce répertoire porte `package.json`, `node_modules` ou `.npmrc` — un `TMPDIR` posé sous un
  projet —, il est recréé sous `/tmp`, une note le dit, et à défaut DEGRADED `cwd_npm_hostile` ; tous les
  chemins passés sont absolus, l'Evidence est le stdout de rea) ; environnement par LISTE BLANCHE
  (`ENV_LISTE_BLANCHE`) plus `npm_config_omit=optional` (sauf `--with-optional` sous décision) et
  `npm_config_prefer_offline=true` — `npm_config_registry`, `NODE_OPTIONS` et tout le reste sont retirés ;
  les cinq variables de moteurs (`ENV_MOTEURS`) ne passent que sous `run --moteurs --decision` ou
  `probe --moteurs` ; sans `--moteurs`, `HOPPER_LAUNCHER_PATH` et `GHIDRA_INSTALL_DIR` reçoivent un chemin
  absent (`SENTINELLE_MOTEURS`), que rea découvrirait sinon seul. Délai dur `DELAI_DEFAUT_S` (ou
  `--timeout`) compté depuis le DÉBUT de la commande : porte node et préparation comprises, rea reçoit ce qui reste (au moins 1 s) ; POSIX : nouvelle session, `os.killpg` au délai et sur
  SIGTERM/SIGHUP (`delai`, `interrompu: <SIG>`) ; hors POSIX : `proc.kill()` du seul processus
  (`delai_hors_posix` : un petit-enfant peut survivre).
* Sortie : stdout de rea dans `<état>/<UTC>-<commande>.json` (ou sous `--out <dir>`), stderr dans
  `….stderr.log` à côté ; un run tué (délai, signal, erreur) renomme l'Evidence tronquée en `….json.partiel`,
  tracée `evidence_partielle` ; trace `<état>/runs.jsonl` pour chaque `run` et `vue`, refus compris (jamais une
  valeur d'environnement) ; `<état>` = `.agents/state/local/rea/`, surcharge `AGENTS_REA_STATE`.
* `vue <evidence>` : requête `{"source":{"kind":"inline","evidence":…},"view":{"kind":…}}` écrite dans le
  répertoire de sortie, puis `inspect-analysis-view <requête>` ; une Evidence de plus de `BORNE_VUE` octets
  est refusée avant lecture (`vue_trop_grande`), comme tout chemin qui n'est pas un fichier régulier
  (`evidence_irreguliere` : `/dev/zero`, FIFO, dossier). La sortie de `node --version` est lue sur au plus
  `SORTIE_NODE_MAX` octets.
* `probe` : node, `--version` puis `doctor` partagent UN budget de `DELAI_DEFAUT_S` (540 s), sous le plafond
  de 600 s de l'outil Bash de Claude Code.

ÉCARTS AU CONTRAT APPROUVÉ (plan r7, annexe § A/§ B), dans le sens sûr, à lire à la porte de clôture :
`completions`, `skills`, `skill` et `rea` sont refusées sans condition là où § A:68 laissait `completions` et
`skills` sous décision — `skills add` installe des skills chez les agents, `rea mcp add` enregistre un serveur
MCP global ; `completions` n'imprime qu'un script, refusée par simplicité (perte dite) ; le cwd de npx est un
répertoire temporaire vide là où § B:73 disait « cwd = répertoire de sortie » (un `.npmrc` posé dans `--out`
détournait le registre).

PERTES DE CAPACITÉ, DITES (sens sûr) : un `.app` qui porte une ressource `.pkg`/`koly` légitime, ou plus de
`BORNE_INVENTAIRE` entrées, est refusé sans décision alors qu'aucun montage n'y est atteignable ; une valeur
qui commence par `-` ne passe que sous la forme `--opt=<v>` ; un chemin qui contient `..` est refusé (passer
son `realpath`) ; une option que `--help` 6.7.0 ne liste pas reste refusée ; `completions` est refusée ; un
fichier que rea écrirait de lui-même dans son cwd (relatif) disparaît avec le répertoire temporaire. Sous une
commande HORS LISTE (donc
sous décision), l'arité n'est pas connue : tout positionnel et toute valeur `=` sont traités en chemin (`..`
refusé, joint au cwd appelant s'il y existe, jugé DMG/PKG).

LIMITE DE CONTRÔLE, à part : un répertoire hors `.app` n'est PAS parcouru (au tag, rea n'y monte rien : il
classe). NON FERMÉ ICI, DIT : la déf tient Bash, le runner ne ferme que pour qui l'appelle ; le contenu jugé
puis ouvert par rea peut changer entre les deux (TOCTOU, non mesuré) ; un cache npx existant porte déjà les
dépendances optionnelles (frida) malgré `omit=optional` ; `~/.npmrc` (configuration utilisateur) et la
configuration globale de npm sont honorés, seul le `.npmrc` de PROJET est écarté par le cwd vide ; sans cache,
npx joint le registre ; une autre version de rea exige de rejouer l'audit de `callerPath.js` et `classify.js`. macOS
mesuré ; Linux supposé ; Windows non mesuré (séparateur `\\` aussi traité en segment).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any, NoReturn

REA_VERSION = "6.7.0"
PAQUET = f"rea-agents@{REA_VERSION}"
RC_OK, RC_REA, RC_REFUS, RC_DEGRADED = 0, 1, 2, 3

ROOT = Path(__file__).resolve().parents[2]
LOCAL_DEFAUT = Path(".agents") / "state" / "local"
ETAT_DEFAUT = LOCAL_DEFAUT / "rea"
FICHIER_TRACE = "runs.jsonl"
DELAI_DEFAUT_S = 540
DELAI_PROBE_S = 300
DELAI_NODE_S = 30
LECTURE_GIT_MAX = 4096
SORTIE_NODE_MAX = 256
MARQUEURS_PROJET_NPM = ("package.json", "node_modules", ".npmrc")
BORNE_INVENTAIRE = 100_000
BORNE_VUE = 64 * 1024 * 1024
_POSIX = os.name == "posix"
SIGNAUX_INTERRUPTION = ("SIGTERM", "SIGHUP")  # SIGINT : KeyboardInterrupt, natif

DECISION_RE = re.compile(r"S-(?:\d{8}|[0-9A-HJKMNP-TV-Z]{26})")
COMMANDE_RE = re.compile(r"[a-z][a-z0-9-]*")
NODE_RE = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")
KIND_VUE_RE = re.compile(r"[a-z][a-z0-9_-]*")
PLAGE_NODE = "^22.19.0 || ^24.11.0 || >=26.0.0"

ENV_LISTE_BLANCHE = ("PATH", "HOME", "TMPDIR", "TMP", "TEMP", "LANG", "LC_ALL", "LC_CTYPE", "USER", "LOGNAME",
                     "SYSTEMROOT", "COMSPEC", "APPDATA", "LOCALAPPDATA", "USERPROFILE", "HTTP_PROXY",
                     "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy", "NODE_EXTRA_CA_CERTS")
ENV_MOTEURS = ("HOPPER_LAUNCHER_PATH", "GHIDRA_INSTALL_DIR", "REA_IDA_MCP_CONFIG", "REA_JADX_MCP_JAR",
               "REA_KUNA_COMMAND")
SENTINELLE_MOTEURS = "/nonexistent/rea_run-moteurs-retires"
MOTEURS_DOCTOR = ("hopper", "ghidra", "ida-registration", "jadx", "kuna-installation")

# Aiguillage d'incur vers ses builtins (`incur/dist/Cli.js` builtinIdx, `internal/command.js` builtinCommands) :
# 1er jeton = nom ou alias d'un builtin (`completions`, `mcp`, `skills`, `skill`), OU 1er jeton = nom du CLI
# (`rea`, `rea-agents/dist/identity.js` cliBinary) suivi d'un builtin (`rea mcp add`). Comparaisons exactes, casse
# comprise ; `COMMANDE_RE` impose déjà les minuscules. Refuser ces cinq noms en tête ferme les deux voies.
REFUSEES = frozenset({"setup", "update", "uninstall", "mcp", "environment-serve", "environment-export",
                      "inspect-elf-notes", "inspect-il", "inspect-model-artifact", "completions", "skills", "skill",
                      "rea"})
PREFIXES_REFUSES = ("environment-",)
BUILTINS = frozenset({"mcp", "update", "incur-update-check", "llms", "llms-full", "schema", "json", "version",
                      "help", "format", "filter-output", "full-output", "token-count", "token-limit",
                      "token-offset"})
SUFFIXES_SENSIBLES = (".dmg", ".pkg")
SUFFIXE_BUNDLE = ".app"
SIGNATURE_XAR = b"xar!"
SIGNATURE_KOLY = b"koly"
TRAILER_KOLY = 512


@dataclass(frozen=True)
class Commande:
    """Arité des positionnels, rôle des positionnels chemins (dans l'ordre), options admises et options sous
    décision : nom -> genre (`b` booléenne, `v` valeur, `c` chemin joint au cwd appelant, `r` chemin relatif à
    la racine de l'application)."""
    mini: int
    maxi: int | None
    chemins: tuple[str, ...]
    admises: dict[str, str]
    sous_decision: dict[str, str]


def _options(spec: str) -> dict[str, str]:
    table = {}
    for mot in spec.split():
        nom, _, genre = mot.partition("=")
        table[nom] = genre or "b"
    return table


def _cmd(mini: int, maxi: int | None, admises: str = "", decision: str = "", chemins: str = "path") -> Commande:
    return Commande(mini, maxi, tuple(chemins.split()), _options(admises), _options(decision))


_CIBLE = "target-format=v architecture=v entry-point=v"
_SNAP = "snapshot=c provider=v"

COMMANDES: dict[str, Commande] = {
    "doctor": _cmd(0, 0, "target=c client=v skill", "provider=v", chemins=""),
    "providers": _cmd(0, 0, chemins=""),
    "capabilities": _cmd(0, 0, chemins=""),
    "instructions": _cmd(1, 2, f"procedure=v {_CIBLE}", _SNAP),
    "analyze": _cmd(1, 1, f"{_CIBLE} integrity-policy=v source-path=r", _SNAP),
    "analyze-javascript-application": _cmd(1, 1, "max-semantic-nodes=v max-semantic-nodes-per-file=v "
                                                 "max-semantic-unknowns=v max-semantic-unknowns-per-file=v "
                                                 "source-path=r max-heap-mb=v analysis-timeout-ms=v "
                                                 "artifact-format=v integrity-policy=v"),
    "inspect-artifact": _cmd(1, 1, "integrity-policy=v"),
    "inspect-binary-layout": _cmd(1, 1),
    "inspect-macho": _cmd(1, 1),
    "inspect-plist": _cmd(1, 1, "relative-path=r"),
    "inspect-signature": _cmd(1, 1),
    "list-architectures": _cmd(1, 1),
    "demangle-swift": _cmd(2, None),
    "inspect-go-binary": _cmd(1, 1),
    "inspect-rust-binary": _cmd(1, 1),
    "inspect-wasm-artifact": _cmd(1, 1, "glue_paths=c candidate_paths=c"),
    "inspect-pe-resources": _cmd(1, 1, "max-file-bytes=v max-entries=v"),
    "inspect-electron-fuses": _cmd(1, 1),
    "inspect-android-package": _cmd(1, 1),
    "inspect-firmware-regions": _cmd(1, 1),
    "inspect-sqlite-database": _cmd(1, 1, "table=v column=v schema-scope=v row-limit=v"),
    "inspect-managed-artifact": _cmd(1, 1),
    "inspect-managed-members": _cmd(1, 1, "type=v"),
    "inspect-evidence-bundle": _cmd(1, 1, chemins="inputJson"),
    "inspect-analysis-view": _cmd(1, 1, chemins="inputJson"),
    "decompile": _cmd(1, 2, f"procedure=v file-offset=v {_CIBLE}", _SNAP),
    "function": _cmd(1, 2, f"procedure=v {_CIBLE}", _SNAP),
    "search": _cmd(1, 2, f"pattern=v kind=v mode=v case-sensitive {_CIBLE}", _SNAP),
    "search-bytes": _cmd(2, 2, f"mask=v start=v end=v cursor=v limit=v {_CIBLE}", "provider=v"),
    "read-bytes": _cmd(2, 2, f"length=v {_CIBLE}", "provider=v"),
    "xrefs": _cmd(1, 2, f"address=v {_CIBLE}", _SNAP),
    "compare": _cmd(2, 2, chemins="left right"),
}


# --- refus, dégradation, interruption ------------------------------------------------------------------
class Refus(Exception):
    """La demande est refusée (exit 2) ; `motif` est un code stable, `detail` le dit."""

    def __init__(self, motif: str, detail: str) -> None:
        super().__init__(f"{motif}: {detail}")
        self.motif = motif
        self.detail = detail


class Degrade(Exception):
    """Le verdict est absent (exit 3) ; `motif` le nomme."""

    def __init__(self, motif: str, detail: str = "") -> None:
        super().__init__(motif)
        self.motif = motif
        self.detail = detail or motif


class Interrompu(BaseException):
    """SIGTERM ou SIGHUP reçu : levée dans le fil principal pour que le groupe de rea soit tué avant de rendre 3."""


def _sur_signal(signum: int, _frame: object) -> NoReturn:
    raise Interrompu(signal.Signals(signum).name)


# --- journal specs : décision pilote ------------------------------------------------------------------
_ETAT_MOD: ModuleType | None = None


def _etat_module() -> ModuleType:
    """L'interface `etat_lecture.py`, sœur de CE fichier, chargée par chemin sous un nom privé, enregistrée
    AVANT son exécution (T-00000134) et retirée si elle échoue. Absente ⇒ `OSError`."""
    global _ETAT_MOD
    if _ETAT_MOD is None:
        import importlib.util

        chemin = Path(__file__).resolve().with_name("etat_lecture.py")
        spec = importlib.util.spec_from_file_location("_rea_run_etat_lecture", chemin) if chemin.is_file() else None
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


def chemin_specs() -> Path:
    """La surcharge `AGENTS_SPECS_PATH`, sinon le chemin que trace l'interface `etat_lecture` (journal s'il
    existe, sinon monolithe) — comme `loadtest.chemin_specs`, sans nommer un chemin de magasin ici."""
    surcharge = os.environ.get("AGENTS_SPECS_PATH")
    if surcharge:
        return Path(surcharge)
    try:
        return _etat_module().chemin_trace(ROOT)
    except (OSError, ImportError) as e:
        raise Refus("specs_illisible", f"interface etat_lecture.py inchargeable ({type(e).__name__})") from e


def _entrees_specs(chemin: Path) -> list:
    """Comme `loadtest._entrees_specs` : l'interface `etat_lecture` sans surcharge ou sous une surcharge
    `.jsonl` ; lecture brute d'une surcharge `.json` (clé `entries`), prévue pour les bancs."""
    surcharge = bool(os.environ.get("AGENTS_SPECS_PATH"))
    if surcharge and not chemin.is_file():
        raise Refus("specs_absent", f"journal specs introuvable ({chemin}) : la décision est invérifiable")
    if not surcharge or chemin.suffix == ".jsonl":
        try:
            el = _etat_module()
        except (OSError, ImportError) as e:
            raise Refus("specs_illisible", f"module etat_lecture.py inchargeable ({type(e).__name__})") from e
        try:
            erreurs = el.erreurs_de_lecture("specs")
        except (OSError, ImportError) as e:
            raise Refus("specs_illisible", f"module specs.py inchargeable ({type(e).__name__})") from e
        try:
            absent = not surcharge and not el.present(ROOT, "specs")
            entrees = [] if absent else (el.entrees_journal_specs(chemin) if surcharge else el.entrees_specs(ROOT))
        except (*erreurs, OSError, ValueError) as e:
            raise Refus("specs_illisible", f"{chemin} : journal illisible ou en deux formes ({e})") from e
        if absent:
            raise Refus("specs_absent", f"journal specs introuvable ({chemin}) : la décision est invérifiable")
        return entrees
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
    """`terme` en MOT ENTIER, casse repliée ; `.` et `-` comptent comme des lettres (un suffixe ne vaut pas
    mention), un point final de phrase non — la règle de `loadtest.nomme`."""
    motif = r"(?<![\w.-])" + re.escape(terme.casefold()) + r"(?![\w-]|\.[\w-])"
    return re.search(motif, texte.casefold()) is not None


def verifier_decision(ident: str, commande: str, groupes_cible: list[set[str]], options: list[str]) -> dict:
    """Forme, présence, `kind`, puis la cible (chaque groupe : un de ses noms), la commande, chaque option."""
    if not DECISION_RE.fullmatch(ident):
        raise Refus("decision_forme", f"{ident!r} hors forme S-<8 chiffres> ou S-<ULID>")
    chemin = chemin_specs()
    entrees = [e for e in _entrees_specs(chemin) if isinstance(e, dict) and e.get("id") == ident]
    if not entrees:
        raise Refus("decision_introuvable", f"{ident} absente de {chemin}")
    decision = next((e for e in entrees if e.get("kind") == "decision"), None)
    if decision is None:
        raise Refus("decision_pas_une_decision", f"{ident} présente dans {chemin} mais pas de kind decision")
    texte = "\n".join(str(decision.get(k) or "") for k in ("text", "title"))
    for groupe in groupes_cible:
        if not any(nomme(texte, nom) for nom in groupe):
            raise Refus("decision_ne_nomme_pas_la_cible", f"{ident} ne nomme aucun de {sorted(groupe)}")
    if not nomme(texte, commande):
        raise Refus("decision_ne_nomme_pas_l_operation", f"{ident} ne nomme pas la commande « {commande} »")
    for option in options:
        if not nomme(texte, option):
            raise Refus("decision_ne_nomme_pas_l_option", f"{ident} ne nomme pas l'option « {option} »")
    return {"id": ident, "specs": str(chemin), "specs_surcharge": bool(os.environ.get("AGENTS_SPECS_PATH"))}


# --- lecture des arguments rea -------------------------------------------------------------------------
@dataclass
class Jeton:
    genre: str  # "positionnel" ou "option"
    brut: str
    nom: str = ""
    valeur: str | None = None
    type_option: str = ""
    negation: bool = False
    rang: int = -1


def _kebab(nom: str) -> str:
    return re.sub(r"(?<=[a-z0-9])([A-Z])", lambda m: "-" + m.group(1).lower(), nom)


def _est_builtin(nom: str) -> bool:
    nu = nom[3:] if nom.startswith("no-") else nom
    return nom.lower() in BUILTINS or nu.lower() in BUILTINS


def analyser_args(spec: Commande | None, args: list[str]) -> list[Jeton]:
    """Les arguments rea, jeton par jeton (§ B). `spec` None : commande hors liste, sous décision."""
    jetons: list[Jeton] = []
    rang = 0
    i = 0
    while i < len(args):
        brut = args[i]
        i += 1
        if brut == "":
            raise Refus("jeton_vide", f"jeton vide en position {i} des arguments rea")
        if brut == "--" or (brut.startswith("-") and not brut.startswith("--")):
            raise Refus("option_refusee", f"{brut!r} : jeton à un seul tiret ou `--` seul")
        if not brut.startswith("--"):
            jetons.append(Jeton("positionnel", brut, rang=rang))
            rang += 1
            continue
        nom_brut, egal, valeur = brut[2:].partition("=")
        nom = _kebab(nom_brut)
        if _est_builtin(nom):
            raise Refus("option_refusee", f"{brut} : option intégrée d'incur, refusée")
        if egal and valeur == "":
            raise Refus("jeton_vide", f"{brut} : valeur vide")
        if spec is None:
            jetons.append(Jeton("option", brut, nom, valeur if egal else None, "x"))
            continue
        table = {**spec.admises, **spec.sous_decision}
        negation = False
        if nom not in table and nom.startswith("no-") and table.get(nom[3:]) == "b":
            nom, negation = nom[3:], True
        type_option = table.get(nom)
        if type_option is None:
            raise Refus("option_refusee", f"{brut} : hors de la liste fermée de la commande")
        if type_option == "b":
            if egal:
                raise Refus("option_refusee", f"{brut} : option booléenne, sans valeur")
            jetons.append(Jeton("option", brut, nom, None, "b", negation))
            continue
        if not egal:
            if i >= len(args):
                raise Refus("valeur_manquante", f"{brut} : valeur attendue")
            valeur = args[i]
            i += 1
            if valeur == "":
                raise Refus("jeton_vide", f"{brut} : valeur vide")
            if valeur.startswith("-"):
                raise Refus("valeur_a_tiret", f"{brut} {valeur} : une valeur à tiret ne passe qu'en {brut}=<v>")
        jetons.append(Jeton("option", brut, nom, valeur, type_option))
    if spec is not None:
        if rang < spec.mini:
            raise Refus("positionnel_manquant", f"{rang} positionnel(s), au moins {spec.mini} attendu(s)")
        if spec.maxi is not None and rang > spec.maxi:
            raise Refus("positionnel_en_trop", f"{rang} positionnel(s), au plus {spec.maxi} admis")
    return jetons


# --- chemins : `..`, jointure, DMG/PKG, parcours confiné -------------------------------------------------
def _segment_parent(chaine: str) -> bool:
    return ".." in re.split(r"[/\\]", chaine)


def joindre(brut: str, cwd: str, quoi: str) -> str:
    """`..` refusé ; un chemin relatif joint au cwd appelant SANS normalisation ; un absolu tel quel."""
    if _segment_parent(brut):
        raise Refus("segment_parent", f"{quoi} {brut!r} : segment `..` refusé (passer son realpath)")
    return brut if os.path.isabs(brut) else os.path.join(cwd, brut)


def _nom_de_base(chaine: str) -> str:
    return os.path.basename(chaine.rstrip("/\\")) or chaine


def _nom_sensible(chaine: str) -> bool:
    return chaine.rstrip("/\\").lower().endswith(SUFFIXES_SENSIBLES)


def _est_bundle(chaine: str) -> bool:
    return chaine.rstrip("/\\").lower().endswith(SUFFIXE_BUNDLE)


def _identite(chemin: str) -> tuple[int, int]:
    st = os.stat(chemin)
    return st.st_dev, st.st_ino


def _dans(chemin: str, cibles: set[tuple[int, int]], memo: dict[str, bool]) -> bool:
    """`chemin` (un `realpath`) est-il l'une des `cibles` ou sous elle ? Par IDENTITÉ D'INODE de ses ancêtres,
    jamais par chaîne : sur un volume insensible à la casse, deux chaînes nomment le même dossier."""
    parcourus = []
    courant = chemin
    resultat = False
    while True:
        if courant in memo:
            resultat = memo[courant]
            break
        try:
            if _identite(courant) in cibles:
                resultat = True
                break
        except OSError:
            pass
        parcourus.append(courant)
        parent = os.path.dirname(courant)
        if parent == courant:
            break
        courant = parent
    for vu in parcourus:
        memo[vu] = resultat
    return resultat


def _contenu_sensible(reel: str) -> bool:
    """`xar!` en tête ou `koly` au trailer UDIF (512 octets avant la fin) d'un fichier RÉGULIER."""
    try:
        with open(reel, "rb") as fh:
            if fh.read(4) == SIGNATURE_XAR:
                return True
            taille = os.fstat(fh.fileno()).st_size
            if taille < TRAILER_KOLY:
                return False
            fh.seek(taille - TRAILER_KOLY)
            return fh.read(4) == SIGNATURE_KOLY
    except OSError as e:
        raise Refus("contenu_illisible", f"{reel} : contenu illisible ({type(e).__name__}), non jugeable") from e


def parcourir_app(racine: str) -> str | None:
    """Le bundle `racine` (déjà `realpath`) : rend la 1re entrée sensible, sinon None. Liens suivis, garde de
    cycle, CONFINÉ sous `racine` ; au-delà de `BORNE_INVENTAIRE` entrées comptées, `inventaire_trop_grand`."""
    try:
        bundle = {_identite(racine)}
    except OSError as e:
        raise Refus("contenu_illisible", f"{racine} : illisible ({type(e).__name__}), non jugeable") from e
    memo: dict[str, bool] = {}
    vus = set(bundle)
    pile = [racine]
    compte = 0
    while pile:
        dossier = pile.pop()
        try:
            entrees = list(os.scandir(dossier))
        except OSError as e:
            raise Refus("contenu_illisible", f"{dossier} : illisible ({type(e).__name__}), non jugeable") from e
        for entree in entrees:
            reel = os.path.realpath(entree.path)
            if not _dans(reel, bundle, memo):
                continue
            compte += 1
            if compte > BORNE_INVENTAIRE:
                raise Refus("inventaire_trop_grand", f"{racine} : plus de {BORNE_INVENTAIRE} entrées")
            if _nom_sensible(entree.name) or _nom_sensible(reel):
                return entree.path
            try:
                st = os.stat(reel)
            except OSError:
                continue
            mode = st.st_mode
            if stat.S_ISDIR(mode):
                if (st.st_dev, st.st_ino) not in vus:
                    vus.add((st.st_dev, st.st_ino))
                    pile.append(reel)
            elif stat.S_ISREG(mode) and _contenu_sensible(reel):
                return entree.path
    return None


def juger_chemin(chaine: str) -> str | None:
    """La raison qui exige une décision pour `chaine` (chaîne jointe), sinon None."""
    if _nom_sensible(chaine):
        return f"{chaine} : nom en .dmg/.pkg"
    reel = os.path.realpath(chaine)
    if _nom_sensible(reel):
        return f"{chaine} : realpath {reel} en .dmg/.pkg"
    try:
        mode = os.stat(reel).st_mode
    except OSError:
        return None
    if stat.S_ISREG(mode):
        return f"{chaine} : contenu xar!/koly" if _contenu_sensible(reel) else None
    if stat.S_ISDIR(mode) and (_est_bundle(chaine) or _est_bundle(reel)):
        trouve = parcourir_app(reel)
        return f"{chaine} : bundle .app portant {trouve}" if trouve else None
    return None


_NOTES_DITES: set[str] = set()
_RACINES: list[Path] | None = None


def _noter(note: str) -> None:
    """Une note sur stderr, une seule fois par invocation (`main` vide le registre)."""
    if note in _NOTES_DITES:
        return
    _NOTES_DITES.add(note)
    try:
        print(f"note: {note}", file=sys.stderr)
    except (OSError, ValueError):
        pass


def _lire_court(chemin: Path) -> str:
    with open(chemin, "rb") as fh:
        return fh.read(LECTURE_GIT_MAX).decode("utf-8", errors="replace").strip()


def racine_principale(racine: Path) -> Path | None:
    """Le checkout principal du dépôt de `racine`, LU dans les fichiers de git, sans lancer `git` (un `git` posé
    sur le PATH ne peut rien y dire) : `.git` dossier ⇒ `racine` ; `.git` fichier `gitdir: X` d'un worktree lié
    ⇒ parent du répertoire commun (`X/commondir`), VALIDÉ — il porte `HEAD` et `X` est sous `<commun>/worktrees/`.
    `.git` fichier sans `commondir` (sous-module) ⇒ `racine`. Absent, illisible ou incohérent : None."""
    point = racine / ".git"
    try:
        if point.is_dir():
            return racine
        if not point.is_file():
            return None
        contenu = _lire_court(point)
        if not contenu.startswith("gitdir:"):
            return None
        gitdir = Path(contenu[len("gitdir:"):].strip())
        gitdir = Path(os.path.realpath(gitdir if gitdir.is_absolute() else racine / gitdir))
        fichier_commun = gitdir / "commondir"
        if not fichier_commun.is_file():
            return racine if (gitdir / "HEAD").is_file() else None
        commun = Path(_lire_court(fichier_commun))
        commun = Path(os.path.realpath(commun if commun.is_absolute() else gitdir / commun))
    except OSError:
        return None
    if not (commun / "HEAD").is_file() or not _dans(str(gitdir), {_identite(str(commun / "worktrees"))}
                                                     if (commun / "worktrees").is_dir() else set(), {}):
        return None
    return commun.parent


def racines_depot() -> list[Path]:
    """ROOT, et le checkout principal quand ce fichier tourne dans un worktree lié ; calculé UNE fois par
    invocation (`main` vide la mémoire)."""
    global _RACINES
    if _RACINES is None:
        racines = [ROOT]
        principale = racine_principale(ROOT)
        if principale is None:
            _noter("checkout principal non déterminé (.git absent, illisible ou incohérent) : seule la racine de "
                   "ce checkout est jugée par out_suivi")
        elif principale.is_dir():
            racines.append(principale)
        _RACINES = racines
    return _RACINES


def verifier_hors_suivi(chemin: str, quoi: str) -> None:
    """`out_suivi` : `chemin` (par `realpath`) dans un dépôt de `racines_depot()` hors de `.agents/state/local/`.
    Les ancêtres EXISTANTS se comparent par identité d'inode ; la partie qui n'existe pas encore, par ses noms."""
    racines: dict[tuple[int, int], Path] = {}
    locaux: set[tuple[int, int]] = set()
    for racine in racines_depot():
        try:
            racines[_identite(str(racine))] = racine
        except OSError:
            continue
        try:
            locaux.add(_identite(str(racine / LOCAL_DEFAUT)))
        except OSError:
            pass
    courant = os.path.realpath(chemin)
    dessous: list[str] = []
    while True:
        try:
            ident = _identite(courant)
        except OSError:
            ident = None
        if ident is not None and ident in locaux:
            return
        if ident is not None and ident in racines:
            if tuple(dessous[:len(LOCAL_DEFAUT.parts)]) == LOCAL_DEFAUT.parts:
                return
            raise Refus("out_suivi", f"{quoi} {chemin} : dans le dépôt {racines[ident]} hors de "
                                     f"{LOCAL_DEFAUT.as_posix()}/")
        parent = os.path.dirname(courant)
        if parent == courant:
            return
        dessous.insert(0, os.path.basename(courant))
        courant = parent


@dataclass
class Preparation:
    argv: list[str] = field(default_factory=list)
    a_juger: list[str] = field(default_factory=list)
    cible: str | None = None
    snapshots: list[str] = field(default_factory=list)
    options_sous_decision: list[str] = field(default_factory=list)
    noms: set[str] = field(default_factory=set)


def _candidat(brut: str, cwd: str) -> str:
    """Hors liste : tout jeton peut être un chemin ; joint au cwd appelant s'il y existe."""
    joint = joindre(brut, cwd, "jeton")
    return joint if os.path.isabs(brut) or os.path.lexists(joint) else brut


def preparer(spec: Commande | None, jetons: list[Jeton], cwd: str) -> Preparation:
    """Jointure et normalisation des jetons, dans leur ordre ; liste des chemins à juger et de la cible."""
    prep = Preparation()
    relatifs_r: list[str] = []
    for j in jetons:
        prep.noms.add(_nom_de_base(j.brut))
        if j.genre == "positionnel":
            role = None if spec is None else (spec.chemins[j.rang] if j.rang < len(spec.chemins) else "")
            if role is None:
                chaine = _candidat(j.brut, cwd)
            elif role == "inputJson" and j.brut.startswith("{"):
                prep.argv.append(j.brut)
                continue
            elif role:
                chaine = joindre(j.brut, cwd, "positionnel")
                if prep.cible is None:
                    prep.cible = chaine
            else:
                prep.argv.append(j.brut)
                continue
            prep.a_juger.append(chaine)
            prep.noms.add(_nom_de_base(chaine))
            prep.argv.append(chaine)
            continue
        if spec is None or j.nom in spec.sous_decision:
            prep.options_sous_decision.append(f"--{j.nom}")
        if j.type_option == "b":
            prep.argv.append(f"--no-{j.nom}" if j.negation else f"--{j.nom}")
            continue
        if j.valeur is None:
            prep.argv.append(f"--{j.nom}")
            continue
        valeur = j.valeur
        if j.type_option == "c":
            valeur = joindre(j.valeur, cwd, f"--{j.nom}")
            prep.a_juger.append(valeur)
            if j.nom == "snapshot":
                prep.snapshots.append(valeur)
        elif j.type_option == "r":
            if _segment_parent(j.valeur):
                raise Refus("segment_parent", f"--{j.nom}={j.valeur} : segment `..` refusé")
            # Passée telle quelle ; rea la résout depuis la racine de l'application (1er positionnel chemin) :
            # jugée jointe à elle, une fois la cible connue (fin de boucle).
            if os.path.isabs(j.valeur):
                prep.a_juger.append(j.valeur)
            else:
                relatifs_r.append(j.valeur)
        elif j.type_option == "x":
            valeur = _candidat(j.valeur, cwd)
            prep.a_juger.append(valeur)
        prep.noms.add(_nom_de_base(valeur))
        prep.argv.append(f"--{j.nom}={valeur}")
    prep.a_juger += [os.path.join(prep.cible or cwd, valeur) for valeur in relatifs_r]
    return prep


# --- environnement et exécution ---------------------------------------------------------------------------
def env_rea(moteurs: bool, optionnels: bool) -> dict[str, str]:
    """Liste blanche, plus les deux réglages npm ; les moteurs seulement quand ils sont demandés, sinon Hopper
    et Ghidra pointés sur un chemin absent (rea les découvrirait seul dans l'environnement du poste)."""
    env = {nom: os.environ[nom] for nom in ENV_LISTE_BLANCHE if nom in os.environ}
    if moteurs:
        env.update({nom: os.environ[nom] for nom in ENV_MOTEURS if nom in os.environ})
    else:
        env["HOPPER_LAUNCHER_PATH"] = f"{SENTINELLE_MOTEURS}/hopper"
        env["GHIDRA_INSTALL_DIR"] = SENTINELLE_MOTEURS
    if not optionnels:
        env["npm_config_omit"] = "optional"
    env["npm_config_prefer_offline"] = "true"
    return env


def _tuer(proc: subprocess.Popen) -> None:
    """Tue rea (ou `node --version`) ET son groupe de processus (POSIX) ; ailleurs le processus seul."""
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


def _ancetre_projet_npm(dossier: str) -> str | None:
    """Le 1er ancêtre de `dossier` (lui compris) qui porte un marqueur de projet npm, sinon None : npm y
    remonterait pour fixer son `localPrefix` et y lirait un `.npmrc` de projet."""
    courant = os.path.realpath(dossier)
    while True:
        for marqueur in MARQUEURS_PROJET_NPM:
            if os.path.lexists(os.path.join(courant, marqueur)):
                return os.path.join(courant, marqueur)
        parent = os.path.dirname(courant)
        if parent == courant:
            return None
        courant = parent


def cwd_neutre() -> str:
    """Un répertoire temporaire VIDE dont aucun ancêtre n'est un projet npm : sous le `TMPDIR` de l'appelant,
    sinon sous `/tmp` (une note le dit), sinon DEGRADED `cwd_npm_hostile`."""
    trouves = []
    for base in (None, "/tmp"):
        if base is not None and not os.path.isdir(base):
            continue
        neutre = tempfile.mkdtemp(prefix="rea-cwd-", dir=base)
        marqueur = _ancetre_projet_npm(neutre)
        if marqueur is None:
            if trouves:
                _noter(f"répertoire temporaire sous un projet npm ({trouves[0]}) : npx lancé depuis {neutre}")
            return neutre
        shutil.rmtree(neutre, ignore_errors=True)
        trouves.append(marqueur)
    raise Degrade("cwd_npm_hostile", f"aucun répertoire temporaire hors d'un projet npm ({', '.join(trouves)})")


def executer(args_rea: list[str], env: dict[str, str], delai: float, sortie: Path, erreurs: Path) -> int:
    """`npx -y rea-agents@<version> <args>` sous délai dur ; délai, signal ou exception tuent son groupe.
    `cwd` : un répertoire temporaire VIDE, supprimé en sortie — npx n'y trouve ni `.npmrc` ni `node_modules` de
    projet. `Popen` est DANS le `try` : une fenêtre subsiste à l'intérieur même de `Popen`."""
    npx = shutil.which("npx", path=env.get("PATH"))
    if npx is None:
        raise Degrade("npx absent du PATH")
    proc: subprocess.Popen | None = None
    neutre = cwd_neutre()
    try:
        with open(sortie, "wb") as fo, open(erreurs, "wb") as fe:
            try:
                proc = subprocess.Popen([npx, "-y", PAQUET, *args_rea], stdin=subprocess.DEVNULL, stdout=fo,
                                        stderr=fe, cwd=neutre, env=env, start_new_session=_POSIX)
                return proc.wait(timeout=delai)
            except subprocess.TimeoutExpired as e:
                if proc is not None:
                    _tuer(proc)
                motif = "delai" if _POSIX else "delai_hors_posix"
                raise Degrade(motif, f"rea sans réponse en {delai:.0f} s : tué") from e
            except BaseException:
                if proc is not None:
                    _tuer(proc)
                raise
    finally:
        shutil.rmtree(neutre, ignore_errors=True)


def chemin_etat() -> Path:
    surcharge = os.environ.get("AGENTS_REA_STATE")
    return Path(surcharge) if surcharge else ROOT / ETAT_DEFAUT


def _horodatage() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _fichier_neuf(dossier: Path, base: str, suffixe: str) -> Path:
    """Un fichier CRÉÉ en exclusivité sous `dossier` (jamais l'écrasement d'un autre run)."""
    for n in range(1000):
        chemin = dossier / f"{base}{'' if n == 0 else f'-{n}'}{suffixe}"
        try:
            with open(chemin, "xb"):
                return chemin
        except FileExistsError:
            continue
    raise Degrade("sortie_impossible", f"{dossier} : aucun nom libre pour {base}")


def _restant(debut: float, delai: float) -> float:
    """Ce qui reste de `delai` depuis `debut` (horloge monotone), au moins 1 s."""
    return max(1.0, delai - (time.monotonic() - debut))


def lancer_rea(commande: str, args_rea: list[str], dossier: Path, env: dict[str, str], delai: int,
               journal: dict, debut: float) -> dict:
    """Exécute rea, écrit son stdout (Evidence) et son stderr, rend la charge utile de stdout. `delai` court
    depuis `debut` (début de la commande) : la porte node et la préparation le consomment, rea reçoit le reste."""
    argv = [commande, *args_rea, "--format", "json"]
    journal["argv"] = argv
    verifier_node(env, min(DELAI_NODE_S, _restant(debut, delai)))
    if shutil.which("npx", path=env.get("PATH")) is None:
        raise Degrade("npx absent du PATH")
    dossier.mkdir(parents=True, exist_ok=True)
    base = f"{_horodatage()}-{commande}"
    sortie = _fichier_neuf(dossier, base, ".json")
    erreurs = sortie.with_name(sortie.name[:-len(".json")] + ".stderr.log")
    try:
        rc_rea = executer(argv, env, _restant(debut, delai), sortie, erreurs)
    except BaseException:
        # Délai, signal ou erreur : l'Evidence est TRONQUÉE ; renommée `.partiel`, jamais lue comme complète.
        partiel = sortie.with_name(sortie.name + ".partiel")
        try:
            if sortie.exists():
                sortie.rename(partiel)
                journal["evidence_partielle"] = str(partiel)
        except OSError:
            pass
        raise
    octets = sortie.read_bytes()
    charge = {"chemin": str(sortie), "sha256": hashlib.sha256(octets).hexdigest(), "taille": len(octets),
              "rc_rea": rc_rea}
    if rc_rea != 0:
        return {**charge, "rc": RC_REA, "motif": "rea_non_zero"}
    return {**charge, "rc": RC_OK, "motif": None}


# --- sous-commandes -----------------------------------------------------------------------------------------
def _lire_options(jetons: list[str], valeurs: set[str], booleens: set[str]) -> tuple[dict[str, Any], list[str]]:
    """Options du RUNNER (pas de rea) : `--x v`, `--x=v` ou `--x` ; tout autre jeton à tiret est refusé."""
    options: dict[str, Any] = {}
    positionnels: list[str] = []
    i = 0
    while i < len(jetons):
        jeton = jetons[i]
        i += 1
        if not jeton.startswith("--"):
            positionnels.append(jeton)
            continue
        nom, egal, valeur = jeton[2:].partition("=")
        if nom in booleens and not egal:
            options[nom] = True
            continue
        if nom not in valeurs:
            raise Refus("arguments", f"{jeton} : option inconnue du runner")
        if not egal:
            if i >= len(jetons):
                raise Refus("arguments", f"{jeton} : valeur attendue")
            valeur = jetons[i]
            i += 1
        if valeur == "":
            raise Refus("jeton_vide", f"{jeton} : valeur vide")
        options[nom] = valeur
    return options, positionnels


def _delai(options: dict[str, Any]) -> int:
    brut = options.get("timeout")
    if brut is None:
        return DELAI_DEFAUT_S
    if not str(brut).isdigit() or not 1 <= int(brut) <= DELAI_DEFAUT_S:
        raise Refus("arguments", f"--timeout {brut!r} : entier de 1 à {DELAI_DEFAUT_S} secondes")
    return int(brut)


def _commande_refusee(commande: str) -> bool:
    return (commande in REFUSEES or commande.startswith(PREFIXES_REFUSES) or "@" in commande
            or COMMANDE_RE.fullmatch(commande) is None)


def _dossier_sortie(options: dict[str, Any], cwd: str) -> Path:
    if "out" in options:
        dossier = joindre(options["out"], cwd, "--out")
        verifier_hors_suivi(dossier, "--out")
        return Path(dossier)
    dossier = chemin_etat()
    verifier_hors_suivi(str(dossier), "état")
    return dossier


def _verifier_lien_dur(chemin: str, quoi: str) -> None:
    """Un fichier EXISTANT à plusieurs liens durs peut être un fichier suivi vu d'ailleurs : refusé."""
    try:
        st = os.stat(chemin)
    except OSError:
        return
    if stat.S_ISREG(st.st_mode) and st.st_nlink > 1:
        raise Refus("out_suivi", f"{quoi} {chemin} : fichier à {st.st_nlink} liens durs, peut-être suivi ailleurs")


def cmd_run(reste: list[str], journal: dict) -> dict:
    debut = time.monotonic()
    if "--" not in reste:
        raise Refus("separateur_absent", "`run <commande> -- <args rea>` : le séparateur `--` est obligatoire")
    coupure = reste.index("--")
    avant, apres = reste[:coupure], reste[coupure + 1:]
    if any("@latest" in jeton for jeton in reste):
        raise Refus("commande_refusee", "`@latest` refusé : rea est épinglé à " + REA_VERSION)
    options, positionnels = _lire_options(avant, {"decision", "cible", "out", "timeout"},
                                          {"moteurs", "with-optional"})
    if len(positionnels) != 1:
        raise Refus("arguments", f"une commande rea attendue avant `--`, reçu {positionnels}")
    commande = positionnels[0]
    journal.update(commande=commande, decision=options.get("decision"))
    if _commande_refusee(commande):
        raise Refus("commande_refusee", f"« {commande} » refusée sans condition (liste REFUSEES : installe, "
                                        "enregistre, monte ou aiguille vers un builtin d'incur)")
    delai = _delai(options)
    cwd = os.getcwd()
    spec = COMMANDES.get(commande)
    prep = preparer(spec, analyser_args(spec, apres), cwd)
    dossier = _dossier_sortie(options, cwd)
    for snapshot in prep.snapshots:
        verifier_hors_suivi(snapshot, "--snapshot")
        _verifier_lien_dur(snapshot, "--snapshot")
    dues = [] if spec is not None else [f"commande hors liste blanche « {commande} »"]
    raisons = [(chaine, raison) for chaine in prep.a_juger if (raison := juger_chemin(chaine))]
    sensibles = [chaine for chaine, _ in raisons]
    dues += [raison for _, raison in raisons]
    dues += [f"option {o} sous décision" for o in prep.options_sous_decision]
    a_nommer = list(prep.options_sous_decision)
    for drapeau in ("moteurs", "with-optional"):
        if options.get(drapeau):
            dues.append(f"--{drapeau}")
            a_nommer.append(f"--{drapeau}")
    journal["cible"] = _nom_de_base(prep.cible) if prep.cible else options.get("cible")
    if dues and not options.get("decision"):
        raise Refus("decision_requise", "décision pilote tracée exigée : " + " ; ".join(dues))
    groupes = _groupes_cible(prep, options, bool(dues or options.get("decision")))
    groupes += [{_nom_de_base(c), _nom_de_base(os.path.realpath(c))} for c in sensibles]
    if options.get("decision"):
        journal["decision_lue"] = lue = verifier_decision(options["decision"], commande, groupes, a_nommer)
        if lue["specs_surcharge"]:
            _noter(f"décision {lue['id']} lue sous la surcharge AGENTS_SPECS_PATH ({lue['specs']}), pas dans le "
                   "journal specs du dépôt : tracée dans runs.jsonl")
    env = env_rea(moteurs=bool(options.get("moteurs")), optionnels=bool(options.get("with-optional")))
    journal.update(moteurs=bool(options.get("moteurs")), with_optional=bool(options.get("with-optional")))
    return lancer_rea(commande, prep.argv, dossier, env, delai, journal, debut)


def _groupes_cible(prep: Preparation, options: dict[str, Any], exigee: bool) -> list[set[str]]:
    """La cible : le 1er positionnel chemin ; sinon `--cible`, égal au nom de base d'un jeton rea."""
    mot = options.get("cible")
    if mot is not None and mot not in prep.noms:
        raise Refus("cible_inconnue", f"--cible {mot!r} n'est le nom de base d'aucun jeton rea")
    if prep.cible is not None:
        return [{_nom_de_base(prep.cible), _nom_de_base(os.path.realpath(prep.cible))}]
    if mot is not None:
        return [{mot}]
    if exigee:
        raise Refus("cible_absente", "aucun positionnel chemin : `--cible <mot>` exigé sous décision")
    return []


def cmd_vue(reste: list[str], journal: dict) -> dict:
    debut = time.monotonic()
    options, positionnels = _lire_options(reste, {"kind"}, set())
    if len(positionnels) != 1:
        raise Refus("arguments", "`vue <evidence> [--kind summary]` : une Evidence attendue")
    if positionnels[0] == "":
        raise Refus("jeton_vide", "chemin d'Evidence vide")
    kind = options.get("kind", "summary")
    if KIND_VUE_RE.fullmatch(kind) is None:
        raise Refus("arguments", f"--kind {kind!r} hors forme")
    cwd = os.getcwd()
    chemin = joindre(positionnels[0], cwd, "Evidence")
    journal.update(commande="inspect-analysis-view", cible=_nom_de_base(chemin))
    try:
        st = os.stat(chemin)
    except OSError as e:
        raise Refus("evidence_illisible", f"{chemin} : Evidence illisible ({type(e).__name__})") from e
    if not stat.S_ISREG(st.st_mode):
        raise Refus("evidence_irreguliere", f"{chemin} : pas un fichier régulier (périphérique, FIFO, dossier)")
    taille = st.st_size
    if taille > BORNE_VUE:
        raise Refus("vue_trop_grande", f"{chemin} : {taille} octets, au-delà de {BORNE_VUE}")
    try:
        evidence = json.loads(Path(chemin).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise Refus("evidence_illisible", f"{chemin} : Evidence illisible ({type(e).__name__})") from e
    if not isinstance(evidence, dict):
        raise Refus("evidence_illisible", f"{chemin} : l'Evidence n'est pas un objet JSON")
    dossier = _dossier_sortie({}, cwd)
    dossier.mkdir(parents=True, exist_ok=True)
    requete = _fichier_neuf(dossier, f"{_horodatage()}-vue-requete", ".json")
    corps = {"source": {"kind": "inline", "evidence": evidence}, "view": {"kind": kind}}
    requete.write_text(json.dumps(corps, ensure_ascii=False), encoding="utf-8")
    return lancer_rea("inspect-analysis-view", [str(requete)], dossier, env_rea(False, False), DELAI_DEFAUT_S,
                      journal, debut)


def node_admis(version: str) -> bool:
    m = NODE_RE.fullmatch(version.strip())
    if m is None:
        return False
    majeure, mineure, correctif = (int(x) for x in m.groups())
    return ((majeure == 22 and (mineure, correctif) >= (19, 0))
            or (majeure == 24 and (mineure, correctif) >= (11, 0)) or majeure >= 26)


def verifier_node(env: dict[str, str], delai: float) -> str:
    """La porte node, commune à `probe`, `run` et `vue`, AVANT tout lancement de npx : node présent sur le PATH
    de rea et dans `PLAGE_NODE`, sinon DEGRADED (3). Rend la version lue."""
    node = shutil.which("node", path=env.get("PATH"))
    if node is None:
        raise Degrade("node absent du PATH")
    lu: list[bytes] = []
    try:
        proc = subprocess.Popen([node, "--version"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, env=env, start_new_session=_POSIX)
    except OSError as e:
        raise Degrade(f"node --version en échec ({type(e).__name__})") from e
    # Le délai se juge sur le LECTEUR, pas sur `lu` (à l'EOF il ajoute b"") ; à l'expiration on tue le GROUPE :
    # un petit-enfant qui hérite du tube le lâche, le `read()` rend. `close()` jamais sous un `read()` en cours
    # (il attendrait son verrou, donc la mort de qui tient le tube).
    lecteur = threading.Thread(target=lambda: lu.append(proc.stdout.read(SORTIE_NODE_MAX + 1)), daemon=True)
    try:
        lecteur.start()
        lecteur.join(delai)
        expire = lecteur.is_alive()
        trop = not expire and bool(lu) and len(lu[0]) > SORTIE_NODE_MAX
        if expire or trop:
            _tuer(proc)
            lecteur.join(5)
        else:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                _tuer(proc)
    except BaseException:
        _tuer(proc)
        raise
    finally:
        if not lecteur.is_alive():
            proc.stdout.close()
    if expire:
        raise Degrade(f"node --version en échec (sans réponse en {delai:.0f} s)")
    if trop:
        raise Degrade(f"node --version : sortie de plus de {SORTIE_NODE_MAX} octets, refusée")
    version = lu[0].decode("utf-8", errors="replace").strip() if lu else ""
    if not node_admis(version):
        raise Degrade(f"node {version or '?'} hors plage {PLAGE_NODE}")
    return version


def _reste(echeance: float, plafond: float) -> float:
    """Le délai d'une étape de `probe` : son plafond, borné par ce qui reste du budget partagé."""
    reste = echeance - time.monotonic()
    if reste <= 0:
        raise Degrade("delai", f"probe au-delà de son budget de {DELAI_DEFAUT_S} s")
    return min(plafond, reste)


def _rea_capture(args_rea: list[str], dossier: Path, env: dict[str, str], delai: float) -> tuple[int, str]:
    sortie, erreurs = dossier / "sortie.json", dossier / "erreurs.log"
    rc = executer(args_rea, env, delai, sortie, erreurs)
    return rc, sortie.read_text(encoding="utf-8", errors="replace")


def cmd_probe(reste: list[str]) -> dict:
    options, positionnels = _lire_options(reste, set(), {"moteurs"})
    if positionnels:
        raise Refus("arguments", "`probe [--moteurs]` : aucun positionnel")
    moteurs = bool(options.get("moteurs"))
    echeance = time.monotonic() + DELAI_DEFAUT_S
    env = env_rea(moteurs=moteurs, optionnels=False)
    version_node = verifier_node(env, _reste(echeance, DELAI_NODE_S))
    with tempfile.TemporaryDirectory(prefix="rea-probe-") as tmp:
        _rc, sortie = _rea_capture(["--version"], Path(tmp), env, _reste(echeance, DELAI_PROBE_S))
        version = sortie.strip()
        if version != REA_VERSION:
            raise Degrade(f"rea {version or '?'} au lieu de {REA_VERSION}")
        rc_doctor, sortie = _rea_capture(["doctor", "--format", "json"], Path(tmp), env,
                                         _reste(echeance, DELAI_PROBE_S))
    try:
        doctor = json.loads(sortie)
    except ValueError as e:
        raise Degrade(f"doctor illisible (rc {rc_doctor})") from e
    checks = doctor.get("checks") if isinstance(doctor, dict) else None
    if not isinstance(checks, list):
        raise Degrade(f"doctor sans liste `checks` (rc {rc_doctor})")
    moteurs_vus = [c for c in checks if isinstance(c, dict) and c.get("name") in MOTEURS_DOCTOR]
    presents = [c["name"] for c in moteurs_vus if c.get("ok") is True]
    absents = [c["name"] for c in moteurs_vus if c.get("ok") is not True]
    cle = "moteurs_absents" if moteurs else "moteurs_absents_env_retiree"
    return {"rc": RC_OK, "motif": None, "node": version_node, "rea": version, "doctor_rc": rc_doctor,
            "moteurs_presents": presents, cle: absents}


# --- sortie, trace, signaux, garde de tête ------------------------------------------------------------------
def _emettre(charge: dict) -> None:
    try:
        print(json.dumps(charge, ensure_ascii=True, sort_keys=True, default=str))
        sys.stdout.flush()
    except (OSError, ValueError):
        pass


def _tracer(journal: dict, charge: dict) -> dict:
    """Une ligne `runs.jsonl` par `run`/`vue`, refus compris ; jamais une valeur d'environnement. Une trace
    non écrite change un rc 0 ou 1 en DEGRADED."""
    enreg = {"date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             **{k: journal.get(k) for k in ("sous_commande", "commande", "argv", "cible", "decision",
                                            "decision_lue", "moteurs", "with_optional", "evidence_partielle")},
             **{k: charge.get(k) for k in ("rc", "motif", "chemin", "sha256", "taille", "rc_rea")}}
    base = chemin_etat()
    try:
        verifier_hors_suivi(str(base), "état")
        base.mkdir(parents=True, exist_ok=True)
        with open(base / FICHIER_TRACE, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(enreg, ensure_ascii=False, sort_keys=True, default=str) + "\n")
    except (OSError, Refus) as e:
        if charge.get("rc") in (RC_OK, RC_REA):
            return {**charge, "rc": RC_DEGRADED, "motif": "trace_non_ecrite", "detail": f"{base} ({e})"}
    return charge


def _installer_signaux() -> dict[int, Any]:
    """SIGTERM et SIGHUP lèvent `Interrompu` (POSIX, fil principal seul) ; rend les gestionnaires remplacés."""
    anciens: dict[int, Any] = {}
    if not _POSIX:
        return anciens
    for nom in SIGNAUX_INTERRUPTION:
        sig = getattr(signal, nom, None)
        if sig is None:
            continue
        try:
            anciens[sig] = signal.signal(sig, _sur_signal)
        except ValueError:  # hors du fil principal : aucun gestionnaire possible
            break
    return anciens


def _rendre_signaux(anciens: dict[int, Any]) -> None:
    for sig, gestionnaire in anciens.items():
        try:
            signal.signal(sig, gestionnaire if gestionnaire is not None else signal.SIG_DFL)
        except (ValueError, TypeError):
            pass


def _principal(argv: list[str], journal: dict) -> dict:
    if not argv:
        raise Refus("arguments", "sous-commande attendue : probe | run | vue")
    sous, reste = argv[0], argv[1:]
    if sous == "probe":
        return cmd_probe(reste)
    if sous in ("run", "vue"):
        journal["sous_commande"] = sous
        return cmd_run(reste, journal) if sous == "run" else cmd_vue(reste, journal)
    raise Refus("arguments", f"sous-commande {sous!r} inconnue : probe | run | vue")


def _garde_de_tete(argv: list[str]) -> int:
    """REFUS 2, DEGRADED 3, interruption 3, toute exception non prévue 3 — jamais le rc 1 d'un Python nu."""
    journal: dict = {}
    try:
        charge = _principal(argv, journal)
    except Refus as r:
        charge = {"rc": RC_REFUS, "motif": r.motif, "detail": r.detail}
    except Degrade as d:
        charge = {"rc": RC_DEGRADED, "motif": d.motif, "detail": d.detail}
    except (KeyboardInterrupt, Interrompu) as e:
        nom = "SIGINT" if isinstance(e, KeyboardInterrupt) else str(e)
        charge = {"rc": RC_DEGRADED, "motif": f"interrompu: {nom}", "detail": f"runner interrompu ({nom}), rea tué"}
    except Exception as e:  # noqa: BLE001 — garde de tête
        charge = {"rc": RC_DEGRADED, "motif": f"erreur interne: {type(e).__name__}", "detail": str(e)}
    if journal.get("sous_commande"):
        charge = _tracer(journal, charge)
    for cle in ("chemin", "sha256", "taille", "motif"):
        charge.setdefault(cle, None)
    if journal.get("cible") is not None:
        charge.setdefault("cible", journal["cible"])
    if journal.get("commande") is not None:
        charge.setdefault("commande", journal["commande"])
    if journal.get("decision_lue"):
        charge.setdefault("specs_surcharge", journal["decision_lue"]["specs_surcharge"])
    _emettre(charge)
    if charge["rc"] == RC_DEGRADED:
        try:
            print(f"COVERAGE DEGRADED — {charge.get('detail') or charge['motif']}", file=sys.stderr)
        except (OSError, ValueError):
            pass
    return charge["rc"]


def main(argv: list[str] | None = None) -> int:
    """Gestionnaires SIGTERM/SIGHUP posés le temps de la commande, puis la garde de tête ; rendus à la sortie."""
    global _RACINES
    anciens = _installer_signaux()
    _NOTES_DITES.clear()
    _RACINES = None
    try:
        return _garde_de_tete(sys.argv[1:] if argv is None else list(argv))
    finally:
        _rendre_signaux(anciens)


if __name__ == "__main__":
    sys.exit(main())
