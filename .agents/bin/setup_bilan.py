#!/usr/bin/env python3
"""setup_bilan.py — le BILAN VÉRIFIÉ du poste : sept jambes jugées, rejouable.

T-01M54GEA4BNFC7QDJVK6P53Y4B (F1, lot B) ; jambes version et scanners :
T-01M5VYNMZPG8G0JZG48HV4K0PN (lot B). Kit ET adoptant, à tout moment :

    python3 .agents/bin/setup_bilan.py [--root R] [--sans-ecrire]

Sept jambes, dans l'ordre, chacune `OK` | `KO` | `SANS OBJET`, chaque KO avec
son remède ÉCRIT, une ligne par jambe imprimée AU MOMENT où elle est jugée :

    bilan: <jambe> : OK|KO|SANS OBJET — <détail>[ ; remède : <cmd>]
    bilan: OK=<n> KO=<k> SANS OBJET=<s> — exit <rc>

  version       dans le kit (`.agents/IS_THE_KIT`) : SANS OBJET ; sinon, SEULEMENT
                si `CHANGELOG.md` ouvre sur le titre du journal du kit
                (`TITRE_JOURNAL_KIT` ; le CHANGELOG propre d'un adoptant : SANS
                OBJET, git non lancé), sa 1re tête `## ` (`x.y.z[.devN] — date`,
                sinon SANS OBJET ; BORNE : un fichier fusionné qui garde ce titre
                mais met SA version en tête est lu comme le journal du kit) contre
                `git ls-remote --tags --refs -- <dépôt du kit>
                'refs/tags/template/v*'` (forme `TAG_RE` de sync_template_docs,
                nombres de 9 chiffres au plus, 15 s au plus ; URL affichée sans
                `user[:mdp]@`, git compris). Le dépôt de distribution est PRIVÉ :
                l'assistant d'identifiants du poste répond, JAMAIS une invite
                (GIT_TERMINAL_PROMPT=0, GIT_ASKPASS et SSH_ASKPASS vides,
                GCM_INTERACTIVE=never ; hors https/http/file/chemin,
                GIT_SSH_COMMAND=`ssh -o BatchMode=yes`) ; `-c credential.helper=`
                SEULEMENT sous BILAN_KIT_REMOTE (banc, URL tierce). Tri NUMÉRIQUE
                (0.1.0.dev9 < 0.1.0.dev11 < 0.1.0) : copie plus vieille que le
                dernier tag -> KO, remède « usage.html § Monter de version du kit
                (#monter-version) » ; « could not read Username|Password » :
                SANS OBJET « dépôt du kit privé : identifiants du poste absents,
                version non comparée » ; injoignable ou illisible : SANS OBJET ;
  outils        `core-scripts/doctor.sh` : KO si sa section
                « Classe B » dit ABSENT ou MAUVAISE VERSION, ou sans ligne
                `doctor:` de compte (« doctor illisible ») ; remède `bash
                core-scripts/setup.sh`, sur la plateforme windows du doctor
                `REMEDE_OUTILS_WINDOWS` (setup.ps1) ;
  scanners      la MÊME sortie du doctor (joué une fois par passage) : gitleaks,
                semgrep (sa version, SEMGREP_ENABLE_VERSION_CHECK=0, 15 s au plus,
                et le pin CI de tool-inventory.tsv dits),
                puis l'outil de chaque famille de `doctor: modules :` (python ->
                pip-audit, npm -> npm, java|swift -> dependency-check, iac ->
                trivy) ; ligne absente ou `illisible` -> KO ; NVD_API_KEY dite
                posée|absente, JAMAIS sa valeur, exigée avec java|swift. Remède
                par plateforme du doctor : darwin hors du kit `bash
                core-scripts/setup.sh` (il installe `PAQUET_DARWIN`) ; darwin
                dans le kit (setup.sh n'y planifie aucun scanner) `brew install
                -- <paquet>` ; linux et windows la commande propre de l'outil ou
                README-SECURITY-SCAN-SETUP.md § <section> ;
  interpréteur  `bash .agents/pyrun.sh -c <version, exécutable>` : < 3.11 ou
                rc ≠ 0 -> KO qui nomme l'exécutable ;
  hooks         `.claude/settings.json` porte `hooks` et `protect-paths`, chaque
                `$CLAUDE_PROJECT_DIR/<rel>` cité existe, ni `settings.json` ni
                `settings.local.json` ne posent `disableAllHooks: true`, ET
                `core.hooksPath` vaut `.githooks` (ou désigne `.githooks` de
                CETTE racine), dossier présent. BORNE : « déclaré et présent »,
                jamais « tiré par l'hôte » ; Claude Code seul — Codex, Gemini,
                Copilot, Kimi non jugés ; Windows : Git Bash requis, `pyrun.ps1`
                non jugé. Remède `git config core.hooksPath .githooks` SEULEMENT
                `.githooks/` présent, sans valeur étrangère ni hook actif (hors
                `*.sample`, sous `--git-path hooks` résolu contre la racine) ;
                sinon les voies d'intégration, jamais la commande qui contourne ;
  portes        hors du kit, les graines BINOME_REQUIRED, CHRONO_REQUIRED,
                CONFIG_QUALITE_PROTEGE, PLAN_CHAIN_REQUIRED, PLAN_CIBLE_REQUIRED
                sous `.agents/state/gates/`
                (absente = KO : désarmée délibérément ou jamais posée,
                indiscernable ici) ; dans le kit (`.agents/IS_THE_KIT`) : SANS OBJET ;
  dashboard     `pyrun.sh .agents/bin/dashboard_daemon.py --root R --status`, LU
                seulement (jamais `--ensure`) : `alive` sans `code: "stale"` -> OK.

Code de sortie : 0 sans KO, 1 au moindre KO, 2 usage (argument, racine absente).
Racine par défaut : l'arbre qui PORTE ce fichier (jamais le répertoire courant).
Chaque enfant : argv en liste, jamais de shell, stdin fermé, délai `--delai`
(120 s, option cachée) -> KO « délai dépassé », groupe de processus tué ; le
même groupe est tué sur SIGINT et sur SIGTERM (converti en SystemExit 143).

LE CONTRAT, écrit atomiquement (fichier temporaire du même répertoire, puis
`os.replace`) sauf sous `--sans-ecrire`, qui n'écrit RIEN :
`.agents/state/local/setup-bilan.json` (gitignoré) =
`{"schema": 1, "genere_le": <ISO UTC>, "rc": 0|1, "jambes": [{"jambe", "etat",
"detail", "remede"|null}], "commande": "python3 .agents/bin/setup_bilan.py"}`.
Un contrat non écrit est DIT sur stderr ; le code de sortie reste le verdict.

VARIABLES RÉSERVÉES AUX BANCS — ne les posez pas à la main, ne les laissez pas
dans un profil (même règle que `SETUP_PROBE_PATH` / `SETUP_DOCTOR` de
`core-scripts/setup.sh`) :
  BILAN_PROBE_PATH=<PATH>  le PATH des enfants (les `python3` que sonde
                           `pyrun.sh`, les outils que cherche le doctor) ;
  BILAN_DOCTOR=<chemin>    un autre doctor.sh, exécuté par bash ;
  BILAN_KIT_REMOTE=<url>   un autre dépôt du kit pour la jambe version (un
                           dépôt local au banc : AUCUN banc ne touche le
                           réseau) ; une valeur qui commence par `-` est
                           REFUSÉE, git n'est pas lancé.
Elles sont honorées sans autre condition, comme leurs modèles de setup.sh :
posées par un tiers, elles FAUSSENT LE VERDICT, puisque le bilan juge (et
exécute) autre chose que les outils du poste. Quand l'une est posée, la ligne
qu'elle touche le DIT : « BILAN_DOCTOR posé (banc) » sur `outils` et
`scanners`, « BILAN_PROBE_PATH posé (banc) » sur `outils`, `scanners`,
`interpréteur` et `dashboard`, « BILAN_KIT_REMOTE posé (banc) » sur `version`,
en plus du doctor lu et de l'exécutable retenu.

Le contrat n'est JAMAIS écrit à travers un lien symbolique : si `.agents`,
`.agents/state` ou `.agents/state/local` sous la racine en est un, l'écriture est
refusée et la ligne stderr `bilan: contrat non écrit` le dit.

stdlib seule, imports en liste FERMÉE (témoin AST du banc), aucune construction
qui exige Python ≥ 3.10 : le bilan doit DIRE un interpréteur trop vieux, pas
planter dessus (témoin sous un 3.9 réel au banc).
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

OK, KO, SANS_OBJET = "OK", "KO", "SANS OBJET"
COMMANDE = "python3 .agents/bin/setup_bilan.py"
CONTRAT = Path(".agents") / "state" / "local" / "setup-bilan.json"
GRAINES = ("BINOME_REQUIRED", "CHRONO_REQUIRED", "CONFIG_QUALITE_PROTEGE", "PLAN_CHAIN_REQUIRED",
           "PLAN_CIBLE_REQUIRED")
VERSION_MIN = (3, 11)
_DELAI_S = 120

REMEDE_OUTILS = "bash core-scripts/setup.sh"
#: Le même remède sur la plateforme windows du doctor : la commande de docs/usage.html.
REMEDE_OUTILS_WINDOWS = r"powershell -NoProfile -ExecutionPolicy Bypass -File core-scripts\setup.ps1"
REMEDE_INTERPRETEUR = "installer Python ≥ 3.11 et le placer avant dans le PATH"
#: L'activation directe : proposée SEULEMENT quand elle ne contourne rien (`_remede_hooks`).
REMEDE_HOOKS = "bloc hooks du kit ; git config core.hooksPath .githooks"
REMEDE_HOOKS_SANS_DOSSIER = ("bloc hooks du kit ; .githooks/ absent : resynchroniser le kit "
                             "avant toute activation")
REMEDE_HOOKS_LECTURE = "bloc hooks du kit ; lecture git échouée : la corriger avant toute activation"
REMEDE_HOOKS_HORS_RACINE = ("bloc hooks du kit ; .githooks/ hors de cette racine : le remplacer par un "
                            "dossier du dépôt avant toute activation")
REMEDE_PORTES = "rétablir par la sync du template si non voulu"
REMEDE_DASH = "/dash ($dash hors Claude Code)"
REMEDE_DASH_PERIME = ("bash .agents/pyrun.sh .agents/bin/dashboard_daemon.py --stop, puis "
                      + REMEDE_DASH)

#: Le dépôt de distribution du kit (PRIVÉ), lu par la jambe version avec les identifiants
#: que l'assistant du poste détient déjà — jamais une invite.
KIT_REMOTE = "https://gitlab.groupeonepoint.com/glass-factory/glass-factory-kit.git"
REMEDE_VERSION = "usage.html § Monter de version du kit (#monter-version)"
_DELAI_REMOTE_S = 15
#: Le titre (H1) du journal que le kit livre (.agents/adopter-docs/CHANGELOG.md:1) : un
#: CHANGELOG.md qui n'ouvre pas sur lui est celui de l'adoptant, jamais comparé aux tags du kit.
TITRE_JOURNAL_KIT = "# Journal des versions — Cadre"
#: Lecture bornée du CHANGELOG (caractères) : la tête cherchée est en haut du fichier.
_BORNE_CHANGELOG = 65536
#: `sync_template_docs.TAG_RE`, recopiée (imports en liste fermée), chaque nombre BORNÉ à 9
#: chiffres : `int()` d'un nombre de plus de 4300 chiffres lève (Python ≥ 3.11).
_TAG_RE = re.compile(r"template/v(?P<version>[0-9]{1,9}\.[0-9]{1,9}\.[0-9]{1,9}"
                     r"(?:\.dev[0-9]{1,9})?)-(?P<date>[0-9]{4}-[0-9]{2}-[0-9]{2})\Z")
_TETE_CHANGELOG = re.compile(r"## (?P<version>[0-9]{1,9}\.[0-9]{1,9}\.[0-9]{1,9}"
                             r"(?:\.dev[0-9]{1,9})?)(?:\s|\Z)")
#: L'userinfo (`user[:mot de passe]@`) d'une URL, retirée avant tout affichage ; gourmande
#: jusqu'au DERNIER `@` avant le chemin : un `@` dans le mot de passe n'en laisse rien.
_USERINFO = re.compile(r"\A((?:[A-Za-z][A-Za-z0-9+.-]*://)?)[^/\s]*@")
#: La même, n'importe où dans une ligne d'erreur de git (`'https://user:mdp@hôte/…'`).
_USERINFO_DANS = re.compile(r"(://)[^/\s'\"]*@")
#: git sans identifiant ni invite permise (GIT_TERMINAL_PROMPT=0) devant un dépôt privé.
_SANS_IDENTIFIANTS = re.compile(r"could not read (?:Username|Password)", re.IGNORECASE)

#: Famille de la ligne `doctor: modules :` -> l'outil qui la scanne (porte adoptant, sca-scan.sh).
_OUTIL_DE_FAMILLE = {"python": "pip-audit", "npm": "npm", "java": "dependency-check",
                     "swift": "dependency-check", "iac": "trivy"}
#: Ce que `core-scripts/setup.sh` installe sur darwin HORS du kit, outil -> paquet brew ; les
#: paquets == `SP_SCANNERS_DARWIN` de setup.sh (témoin de parité du banc).
PAQUET_DARWIN = {"gitleaks": "gitleaks", "semgrep": "semgrep", "pip-audit": "pip-audit",
                 "npm": "node", "dependency-check": "dependency-check", "trivy": "trivy"}
_DOC_SCAN = "README-SECURITY-SCAN-SETUP.md § "
#: La commande PROPRE de chaque outil (linux, windows) ; semgrep reçoit `==<pin CI>` s'il est lu.
_REMEDE_PROPRE = {
    "gitleaks": (_DOC_SCAN + "Secrets scan (gitleaks)", "winget install gitleaks"),
    "semgrep": ("pipx install semgrep", "pipx install semgrep"),
    "pip-audit": ("pipx install pip-audit", "pipx install pip-audit"),
    "npm": ("sudo apt-get install npm", _DOC_SCAN + "Per-ecosystem requirements"),
    "dependency-check": (_DOC_SCAN + "Per-ecosystem requirements",
                         _DOC_SCAN + "Per-ecosystem requirements"),
    "trivy": (_DOC_SCAN + "IaC misconfiguration scan (trivy)", "choco install trivy"),
}
REMEDE_NVD = _DOC_SCAN + "The NVD API key"
REMEDE_MODULES = ("resynchroniser core-scripts/doctor.sh et .agents/security/module_discovery.py "
                  "(ligne doctor: modules)")

_SONDE_VERSION = ("import sys; print('%d.%d.%d' % tuple(sys.version_info[:3])); "
                  "print(sys.executable)")
_LIGNE_DOCTOR = re.compile(r"^doctor: \d+/\d+ présents")
_LIGNE_MODULES = re.compile(r"^doctor: modules : (?P<familles>\S+)\s*$")
_VERSION_OUTIL = re.compile(r"[0-9][0-9A-Za-z.+-]{0,63}")
_CHEMIN_CITE = re.compile(r"\$\{?CLAUDE_PROJECT_DIR\}?/([A-Za-z0-9_./-]+)")
_BORNE_HOOKS = ("déclarés et présents, jamais « tirés par l'hôte » ; Claude Code seul — "
                "Codex, Gemini, Copilot, Kimi non jugés")


class Sortie:
    """Ce qu'un enfant a rendu ; `rc` None = délai dépassé."""

    def __init__(self, rc: int | None, stdout: str, stderr: str) -> None:
        self.rc = rc
        self.stdout = stdout
        self.stderr = stderr

    def derniere(self) -> str:
        texte = (self.stderr.strip() or self.stdout.strip()).splitlines()
        return texte[-1].strip() if texte else f"rc {self.rc}"


# --- lancer --------------------------------------------------------------------

def _tuer(p: subprocess.Popen) -> None:
    """Le GROUPE de l'enfant (POSIX) : un petit-enfant qui tient le tube ne
    bloque pas la lecture après le délai."""
    try:
        if hasattr(os, "killpg"):
            os.killpg(p.pid, signal.SIGKILL)
        else:
            p.kill()
    except OSError:
        pass


def _vider(p: subprocess.Popen) -> None:
    """Après un kill, la lecture des tubes reste BORNÉE (5 s)."""
    try:
        p.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def _executer(argv: list[str], racine: Path, delai: int,
              env_en_plus: dict[str, str] | None = None) -> Sortie:
    """Le SEUL site `subprocess` : argv en liste, stdin fermé, cwd = racine,
    PATH des enfants = BILAN_PROBE_PATH s'il est posé (bancs seulement) ;
    `env_en_plus` posé par-dessus (GIT_TERMINAL_PROMPT=0 de la jambe version)."""
    env = dict(os.environ)
    sonde = os.environ.get("BILAN_PROBE_PATH")
    if sonde is not None:
        env["PATH"] = sonde
    env.update(env_en_plus or {})
    try:
        p = subprocess.Popen(argv, cwd=str(racine), env=env, stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             start_new_session=hasattr(os, "killpg"))
    except OSError as exc:
        return Sortie(127, "", f"{type(exc).__name__}: {exc}")
    try:
        out, err = p.communicate(timeout=delai)
    except subprocess.TimeoutExpired:
        _tuer(p)
        _vider(p)
        return Sortie(None, "", "")
    except BaseException:
        # SIGINT, SIGTERM (SystemExit, `_sur_sigterm`), toute exception : l'enfant vit dans sa propre
        # session, il ne reçoit pas le signal du terminal — on tue son groupe.
        _tuer(p)
        _vider(p)
        raise
    return Sortie(p.returncode, out.decode("utf-8", "replace"), err.decode("utf-8", "replace"))


def _delai_depasse(delai: int, quoi: str) -> str:
    return f"délai dépassé ({delai} s) : {quoi}"


# --- les jambes ----------------------------------------------------------------

def cle_version(version: str) -> tuple[int, int, int, int, int]:
    """Clé de tri NUMÉRIQUE d'une version `x.y.z[.devN]` : (x, y, z, 0 si dev sinon 1, N) —
    0.1.0.dev9 < 0.1.0.dev11 < 0.1.0 (un tri lexical les inverserait)."""
    base, _, dev = version.partition(".dev")
    x, y, z = (int(p) for p in base.split("."))
    return (x, y, z, 0, int(dev)) if dev else (x, y, z, 1, 0)


def _version_copie(racine: Path) -> tuple[str | None, str]:
    """(version, raison) : la version de la 1re tête `## ` de CHANGELOG.md, ou None et pourquoi.
    Lue SEULEMENT si la 1re ligne non vide est `TITRE_JOURNAL_KIT` : le CHANGELOG propre d'un
    adoptant (fusion, jamais écrasement ; copie `cp -Rn`) n'est jamais comparé aux tags du kit.
    BORNE : un fichier fusionné qui garde ce titre mais met SA version en tête est lu comme le
    journal du kit — indiscernable ici. Lecture bornée à `_BORNE_CHANGELOG` caractères ; un BOM
    UTF-8 en tête (éditeur Windows) est retiré avant la comparaison du titre."""
    try:
        with (racine / "CHANGELOG.md").open(encoding="utf-8-sig") as flux:
            texte = flux.read(_BORNE_CHANGELOG)
    except FileNotFoundError:
        return None, "CHANGELOG.md absent"
    except (OSError, ValueError) as exc:
        return None, f"CHANGELOG.md illisible : {type(exc).__name__}"
    lignes = texte.splitlines()
    titre = next((ligne.rstrip() for ligne in lignes if ligne.strip()), "")
    if titre != TITRE_JOURNAL_KIT:
        return None, (f"CHANGELOG.md n'est pas le journal du kit (1re ligne « "
                      f"{_sans_controle(titre[:60])} », attendue « {TITRE_JOURNAL_KIT} »)")
    for ligne in lignes:
        if ligne.startswith("## "):
            m = _TETE_CHANGELOG.match(ligne)
            if m:
                return m["version"], ""
            return None, (f"1re tête de CHANGELOG.md « {_sans_controle(ligne.strip()[:60])} » "
                          "sans version x.y.z[.devN]")
    return None, f"CHANGELOG.md sans tête « ## » dans ses {_BORNE_CHANGELOG} premiers caractères"


def _url_dite(url: str) -> str:
    """L'URL telle qu'affichée : sans userinfo (`user[:mot de passe]@`), sans contrôle."""
    return _sans_controle(_USERINFO.sub(r"\1", url))


def _ligne_utile(sortie: Sortie) -> str:
    """La 1re ligne qui dit la cause (`fatal:`, `error:`, sinon la 1re non vide), bornée, sans
    l'userinfo d'aucune URL qu'elle cite."""
    lignes = [ligne.strip() for ligne in (sortie.stderr or sortie.stdout).splitlines()
              if ligne.strip()]
    ligne = next((x for x in lignes if x.startswith(("fatal:", "error:"))),
                 lignes[0] if lignes else f"rc {sortie.rc}")
    return _sans_controle(_USERINFO_DANS.sub(r"\1", ligne)[:160])


def jambe_version(racine: Path, bash: str | None, delai: int) -> tuple[str, str, str | None]:
    del bash
    if (racine / ".agents" / "IS_THE_KIT").exists():
        return SANS_OBJET, "kit (.agents/IS_THE_KIT) : la version se publie d'ici", None
    locale, raison = _version_copie(racine)
    if locale is None:
        return SANS_OBJET, f"{raison} : version de la copie non comparée", None
    url = os.environ.get("BILAN_KIT_REMOTE")
    url = KIT_REMOTE if url is None else url
    if url.startswith("-"):
        return SANS_OBJET, (f"copie {locale} ; BILAN_KIT_REMOTE refusé (commence par « - ») : "
                            "git non lancé"), None
    git = shutil.which("git")
    if git is None:
        return SANS_OBJET, f"copie {locale} ; git absent du PATH : dépôt du kit non lu", None
    borne = min(delai, _DELAI_REMOTE_S)
    # Dépôt de distribution PRIVÉ : l'assistant d'identifiants du poste répond, jamais une
    # invite. `-c credential.helper=` seulement sous BILAN_KIT_REMOTE (banc, URL tierce : aucun
    # identifiant du poste ne lui est présenté).
    banc = os.environ.get("BILAN_KIT_REMOTE") is not None
    argv = ([git] + (["-c", "credential.helper="] if banc else [])
            + ["ls-remote", "--tags", "--refs", "--", url, "refs/tags/template/v*"])
    env = {"GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "", "SSH_ASKPASS": "",
           "GCM_INTERACTIVE": "never"}
    if not url.startswith(("https://", "http://", "file://", "/")):
        env["GIT_SSH_COMMAND"] = "ssh -o BatchMode=yes"
    sortie = _executer(argv, racine, borne, env)
    dit = _url_dite(url)
    if sortie.rc is None:
        return SANS_OBJET, (f"copie {locale} ; dépôt du kit injoignable : "
                            f"{_delai_depasse(borne, 'git ls-remote ' + dit)}"), None
    if sortie.rc != 0 and _SANS_IDENTIFIANTS.search(sortie.stderr):
        return SANS_OBJET, (f"copie {locale} ; dépôt du kit privé : identifiants du poste "
                            f"absents, version non comparée ({dit}, git ls-remote rc {sortie.rc} : "
                            f"{_ligne_utile(sortie)})"), None
    if sortie.rc != 0:
        return SANS_OBJET, (f"copie {locale} ; dépôt du kit injoignable ({dit}, git ls-remote "
                            f"rc {sortie.rc} : {_ligne_utile(sortie)})"), None
    publiees = []
    for ligne in sortie.stdout.splitlines():
        ref = ligne.partition("\t")[2].strip()
        m = _TAG_RE.match(ref[len("refs/tags/"):]) if ref.startswith("refs/tags/") else None
        if m:
            publiees.append(m["version"])
    if not publiees:
        return SANS_OBJET, f"copie {locale} ; aucun tag template/v* lisible sur {dit}", None
    derniere = max(publiees, key=cle_version)
    if cle_version(locale) < cle_version(derniere):
        return KO, (f"copie {locale} plus vieille que la dernière publiée {derniere} ({dit})"), \
            REMEDE_VERSION
    return OK, f"copie {locale}, dernière publiée {derniere} ({dit})", None


def _classe_b(texte: str) -> list[tuple[str, str]] | None:
    """(état, outil) de chaque ligne de la section « Classe B » du doctor qui
    n'est pas PRESENT ; None si la section manque."""
    lignes = texte.splitlines()
    debut = next((i for i, ligne in enumerate(lignes) if ligne.startswith("Classe B")), None)
    if debut is None:
        return None
    section = []
    for ligne in lignes[debut + 1:]:
        if not ligne.strip():
            break
        section.append(ligne.split(" — ")[0].strip())
    etats = [tete.rpartition(" ")[0].strip() for tete in section]
    outils = [tete.rpartition(" ")[2] for tete in section]
    return [(etat, outil) for etat, outil in zip(etats, outils)
            if etat.startswith(("ABSENT", "MAUVAISE VERSION"))]


#: La sortie du doctor, jouée UNE fois par passage : `outils` et `scanners` lisent la même.
_DOCTOR_LU: dict[tuple[str, str, str, int], Sortie] = {}


def _jouer_doctor(racine: Path, bash: str | None,
                  delai: int) -> tuple[str, Sortie | None, str]:
    """(doctor, sortie, refus) : sortie None quand le doctor n'a pas rendu (refus dit)."""
    doctor = os.environ.get("BILAN_DOCTOR")
    if doctor is None:  # posée, même vide, elle est honorée — et dite (`_VARIABLES_DE_BANC`)
        doctor = str(racine / "core-scripts" / "doctor.sh")
    if bash is None:
        return doctor, None, "bash absent du PATH (Git Bash requis sous Windows)"
    if not Path(doctor).is_file():
        return doctor, None, f"doctor illisible : {doctor} absent"
    cle = (str(racine), doctor, bash, delai)
    if cle not in _DOCTOR_LU:
        _DOCTOR_LU[cle] = _executer([bash, doctor], racine, delai)
    sortie = _DOCTOR_LU[cle]
    if sortie.rc is None:
        return doctor, None, _delai_depasse(delai, doctor)
    return doctor, sortie, ""


def remede_outils(plateforme: str) -> str:
    """setup.ps1 sur la plateforme windows (du doctor, sinon `sys.platform`), setup.sh ailleurs."""
    return REMEDE_OUTILS_WINDOWS if plateforme == "windows" else REMEDE_OUTILS


def jambe_outils(racine: Path, bash: str | None, delai: int) -> tuple[str, str, str | None]:
    doctor, sortie, refus = _jouer_doctor(racine, bash, delai)
    if sortie is None:
        return KO, refus, remede_outils(_plateforme(""))
    remede = remede_outils(_plateforme(sortie.stdout))
    compte = next((ligne for ligne in sortie.stdout.splitlines()
                   if _LIGNE_DOCTOR.match(ligne)), None)
    manques = _classe_b(sortie.stdout)
    if compte is None or manques is None:
        quoi = "aucune ligne doctor:" if compte is None else "aucune section Classe B"
        return KO, f"doctor illisible ({quoi}, rc {sortie.rc}) : {doctor}", remede
    if manques:
        dits = ", ".join(f"{outil} {etat}" for etat, outil in manques)
        return KO, f"Classe B : {dits} — {doctor}", remede
    return OK, f"{compte} — {doctor}", None


def _etats_outils(texte: str) -> dict[str, tuple[str, str]]:
    """outil -> (état, 2e champ) de chaque ligne des sections « Classe A » et « Classe B » du
    doctor (`  <ÉTAT> <outil> — <chemin> — …`)."""
    etats: dict[str, tuple[str, str]] = {}
    dans = False
    for ligne in texte.splitlines():
        if ligne.startswith(("Classe A", "Classe B")):
            dans = True
        elif not ligne.strip():
            dans = False
        elif dans and ligne.startswith("  "):
            champs = ligne.split(" — ")
            etat, _, outil = champs[0].strip().rpartition(" ")
            etats.setdefault(outil, (etat.strip(), champs[1].strip() if len(champs) > 1 else ""))
    return etats


def _familles(texte: str) -> list[str] | None:
    """Familles de `doctor: modules :` ; [] pour `aucun` ; None si absente ou `illisible`."""
    m = next((m for m in map(_LIGNE_MODULES.match, texte.splitlines()) if m), None)
    if m is None or m["familles"] == "illisible":
        return None
    return [] if m["familles"] == "aucun" else [f for f in m["familles"].split(",") if f]


def _plateforme(texte: str) -> str:
    """darwin | linux | windows : la section « Plateforme » du doctor, sinon `sys.platform`."""
    lignes = texte.splitlines()
    i = next((i for i, ligne in enumerate(lignes) if ligne.strip() == "Plateforme"), None)
    mots = lignes[i + 1].split() if i is not None and i + 1 < len(lignes) else []
    if mots and mots[0] in ("darwin", "linux", "windows"):
        return mots[0]
    if sys.platform == "darwin":
        return "darwin"
    return "windows" if sys.platform.startswith(("win", "cygwin", "msys")) else "linux"


def _pin_semgrep(racine: Path) -> str | None:
    """Le pin CI de semgrep (colonne 7 de core-scripts/tool-inventory.tsv, avant `@`)."""
    try:
        lignes = (racine / "core-scripts" / "tool-inventory.tsv").read_text(
            encoding="utf-8").splitlines()
    except (OSError, ValueError):
        return None
    for ligne in lignes:
        champs = ligne.split("\t")
        if champs[0] == "semgrep" and len(champs) > 6:
            pin = champs[6].partition("@")[0].strip()
            return pin if _VERSION_OUTIL.fullmatch(pin) else None
    return None


def _version_semgrep(racine: Path, chemin: str, delai: int) -> str:
    """`<chemin> --version` du semgrep que le doctor a trouvé (jamais un autre), SANS sa
    vérification de version en ligne (mesuré : 97 s avec, 1 s sans). Un binaire DANS l'arbre
    du projet n'est jamais exécuté : le bilan ne lance que ce qui est hors du dépôt jugé."""
    p = Path(chemin)
    if not p.is_absolute() or p.name not in ("semgrep", "semgrep.exe") or not p.is_file():
        return f"version non lue ({_sans_controle(chemin) or 'chemin non dit'})"
    if p.resolve().is_relative_to(racine.resolve()):
        return f"version non lue ({_sans_controle(chemin)} dans l'arbre du projet : non exécuté)"
    sortie = _executer([str(p), "--version"], racine, min(delai, _DELAI_REMOTE_S),
                       {"SEMGREP_ENABLE_VERSION_CHECK": "0"})
    lignes = sortie.stdout.strip().splitlines()
    if sortie.rc == 0 and lignes and _VERSION_OUTIL.fullmatch(lignes[-1].strip()):
        return lignes[-1].strip()
    return f"version non lue (--version rc {sortie.rc})"


def remede_scanner(outil: str, plateforme: str, dans_le_kit: bool, pin: str | None) -> str:
    """darwin hors du kit : setup.sh (il installe `PAQUET_DARWIN`) ; darwin dans le kit, où
    setup.sh n'en planifie aucun : `brew install -- <paquet>` ; ailleurs : la commande propre."""
    if plateforme == "darwin":
        return f"brew install -- {PAQUET_DARWIN[outil]}" if dans_le_kit else REMEDE_OUTILS
    linux, windows = _REMEDE_PROPRE[outil]
    remede = windows if plateforme == "windows" else linux
    return f"{remede}=={pin}" if outil == "semgrep" and pin else remede


def jambe_scanners(racine: Path, bash: str | None, delai: int) -> tuple[str, str, str | None]:
    doctor, sortie, refus = _jouer_doctor(racine, bash, delai)
    if sortie is None:
        return KO, f"scanners non jugés : {refus}", remede_outils(_plateforme(""))
    etats = _etats_outils(sortie.stdout)
    if not etats:
        return KO, f"doctor illisible (aucune section Classe A/B, rc {sortie.rc}) : {doctor}", \
            remede_outils(_plateforme(sortie.stdout))
    familles = _familles(sortie.stdout)
    voulus = ["gitleaks", "semgrep"]
    for famille in familles or []:
        outil = _OUTIL_DE_FAMILLE.get(famille)
        if outil and outil not in voulus:
            voulus.append(outil)
    plateforme = _plateforme(sortie.stdout)
    dans_le_kit = (racine / ".agents" / "IS_THE_KIT").exists()
    pin = _pin_semgrep(racine)
    dits, remedes = [], []
    for outil in voulus:
        etat, champ = etats.get(outil, ("NON SONDÉ par le doctor", ""))
        if etat.startswith("PRESENT"):
            if outil == "semgrep":
                dits.append(f"semgrep {_version_semgrep(racine, champ, delai)} "
                            f"(pin CI {pin or 'illisible'})")
            else:
                dits.append(f"{outil} {etat}")
            continue
        dits.append(f"{outil} {etat}")
        remede = remede_scanner(outil, plateforme, dans_le_kit, pin)
        if remede not in remedes:
            remedes.append(remede)
    exige_nvd = "dependency-check" in voulus
    nvd = "posée" if os.environ.get("NVD_API_KEY", "").strip() else "absente"  # jamais la valeur
    if exige_nvd and nvd == "absente":
        remedes.append(REMEDE_NVD)
    if familles is None:
        remedes.append(REMEDE_MODULES)
    modules = ("illisibles (ligne doctor: modules absente ou illisible) : familles non jugées"
               if familles is None else ",".join(familles) or "aucun")
    detail = _sans_controle(f"{', '.join(dits)} ; modules : {modules} ; NVD_API_KEY {nvd}"
                            + ("" if exige_nvd else " (non exigée : ni java ni swift)")
                            + f" ; plateforme {plateforme} — {doctor}")
    if remedes:
        return KO, detail, " ; ".join(remedes)
    return OK, detail, None


def jambe_interpreteur(racine: Path, bash: str | None, delai: int) -> tuple[str, str, str | None]:
    pyrun = racine / ".agents" / "pyrun.sh"
    if bash is None:
        return KO, "bash absent du PATH : pyrun.sh non joué", REMEDE_INTERPRETEUR
    if not pyrun.is_file():
        return KO, f"{pyrun} absent : resynchroniser le kit", REMEDE_INTERPRETEUR
    sortie = _executer([bash, str(pyrun), "-c", _SONDE_VERSION], racine, delai)
    if sortie.rc is None:
        return KO, _delai_depasse(delai, "pyrun.sh"), REMEDE_INTERPRETEUR
    lignes = sortie.stdout.strip().splitlines()
    if sortie.rc != 0 or len(lignes) != 2:
        return KO, f"pyrun.sh rc {sortie.rc} : {sortie.derniere()}", REMEDE_INTERPRETEUR
    version, executable = lignes[0].strip(), lignes[1].strip()
    try:
        numeros = tuple(int(x) for x in version.split("."))
    except ValueError:
        return KO, f"version illisible « {version} » : {executable}", REMEDE_INTERPRETEUR
    if numeros[:2] < VERSION_MIN:
        return KO, (f"Python {version} < 3.11 : {executable} (le dashboard et les bancs "
                    "l'exigent)"), REMEDE_INTERPRETEUR
    return OK, f"Python {version} : {executable}", None


def _chaines(valeur) -> list[str]:
    if isinstance(valeur, str):
        return [valeur]
    if isinstance(valeur, dict):
        valeur = list(valeur.values())
    if isinstance(valeur, list):
        return [s for v in valeur for s in _chaines(v)]
    return []


def _lire_json(chemin: Path):
    """Le JSON de `chemin`, ou None s'il est absent ou illisible."""
    try:
        return json.loads(chemin.read_text(encoding="utf-8")) if chemin.is_file() else None
    except (OSError, ValueError):
        return None


def remede_hooks_actifs(noms: list[str], repertoire: str) -> str:
    """Les deux voies d'intégration, sans jamais la commande qui contournerait le refus ;
    `pre-push` déjà là : chaîner les deux, jamais une copie par-dessus."""
    chaine = ("pre-push y existe déjà : chaîner les deux pre-push, jamais copier celui du kit "
              "par-dessus" if "pre-push" in noms else "chaîner les noms communs")
    repertoire = _sans_controle(repertoire)
    return (f"hooks actifs dans {repertoire} "
            f"({', '.join(_sans_controle(n) for n in noms)}) : intégrer ces hooks dans "
            f".githooks/ en chaînant les noms communs, ou intégrer les hooks du kit dans "
            f"{repertoire} sans changer core.hooksPath — {chaine}")


def _hooks_actifs(racine: Path, git: str, delai: int) -> tuple[list[str] | None, str]:
    """Les entrées hors `*.sample` (liens compris) du répertoire que Git lit sans
    `core.hooksPath` : `--git-path hooks`, un chemin relatif joint à la RACINE, jamais
    au cwd. (None, raison) quand l'inventaire échoue."""
    sortie = _executer([git, "-C", str(racine), "rev-parse", "--git-path", "hooks"], racine, delai)
    if sortie.rc != 0 or not sortie.stdout.strip():
        return None, f"git rev-parse --git-path hooks rc {sortie.rc}"
    repertoire = Path(sortie.stdout.strip())
    if not repertoire.is_absolute():
        repertoire = racine / repertoire
    try:
        noms = sorted(p.name for p in repertoire.iterdir() if not p.name.endswith(".sample"))
    except FileNotFoundError:
        noms = []
    except OSError as exc:
        return None, f"inventaire de {repertoire} : {type(exc).__name__}"
    return noms, str(repertoire)


def _vise_githooks(racine: Path, valeur: str) -> bool:
    return valeur == ".githooks" or (racine / valeur).resolve() == (racine / ".githooks").resolve()


def _githooks_hors_racine(racine: Path) -> bool:
    """Le refus du setup (`setup_projet._hooks_git`) : `.githooks` lien qui sort de la racine."""
    lien = racine / ".githooks"
    return lien.is_symlink() and not lien.resolve().is_relative_to(racine.resolve())


def _sans_controle(valeur: str) -> str:
    return "".join(c if c.isprintable() else f"\\u{ord(c):04x}" for c in valeur)


def _remede_hooks(racine: Path, git: str | None, delai: int) -> str:
    """Le remède de la jambe : `git config core.hooksPath .githooks` seulement avec
    `.githooks/` présent, aucune valeur étrangère et aucun hook actif (réinspectés ici :
    appelé seul, le bilan donne le même conseil prudent que le setup)."""
    if not (racine / ".githooks").is_dir():
        return REMEDE_HOOKS_SANS_DOSSIER
    if _githooks_hors_racine(racine):
        return REMEDE_HOOKS_HORS_RACINE
    if git is None:
        return REMEDE_HOOKS_LECTURE
    lu = _executer([git, "-C", str(racine), "config", "core.hooksPath"], racine, delai)
    if lu.rc not in (0, 1):
        return REMEDE_HOOKS_LECTURE
    if lu.rc == 0:  # posée, même vide (Git lit alors `./` : mesuré 2.55) — jamais écrasée
        valeur = lu.stdout.strip()
        if valeur and _vise_githooks(racine, valeur):
            return REMEDE_HOOKS
        return (f"bloc hooks du kit ; core.hooksPath = {_sans_controle(valeur) or '(vide)'} conservé : y "
                "intégrer les hooks du kit, en chaînant les noms communs")
    noms, repertoire = _hooks_actifs(racine, git, delai)
    if noms is None:
        return f"{REMEDE_HOOKS_LECTURE} ({repertoire})"
    return "bloc hooks du kit ; " + remede_hooks_actifs(noms, repertoire) if noms else REMEDE_HOOKS


def jambe_hooks(racine: Path, bash: str | None, delai: int) -> tuple[str, str, str | None]:
    del bash
    git = shutil.which("git")
    remede = _remede_hooks(racine, git, delai)  # conditionnel : jamais un contournement
    reglages = racine / ".claude" / "settings.json"
    try:
        donnees = json.loads(reglages.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return KO, ".claude/settings.json absent", remede
    except (OSError, ValueError) as exc:
        return KO, f".claude/settings.json illisible : {type(exc).__name__}", remede
    bloc = donnees.get("hooks") if isinstance(donnees, dict) else None
    commandes = _chaines(bloc)
    if not isinstance(bloc, dict) or not bloc:
        return KO, ".claude/settings.json sans bloc hooks", remede
    for nom, lu in ((".claude/settings.json", donnees),
                    (".claude/settings.local.json",
                     _lire_json(racine / ".claude" / "settings.local.json"))):
        if isinstance(lu, dict) and lu.get("disableAllHooks") is True:
            return KO, f"{nom} : disableAllHooks = true — aucun hook ne joue", remede
    if not any("protect-paths" in c for c in commandes):
        return KO, ".claude/settings.json : aucun hook protect-paths", remede
    cites = sorted({m.group(1) for c in commandes for m in _CHEMIN_CITE.finditer(c)} - {""})
    hors = [rel for rel in cites if ".." in rel.split("/")]
    absents = [rel for rel in cites if rel not in hors and not (racine / rel).exists()]
    if hors or absents:
        dits = ", ".join(absents + [f"{rel} (hors racine)" for rel in hors])
        return KO, f"chemin(s) cité(s) par les hooks absent(s) : {dits}", remede
    valeur = ""
    if git is not None:
        sortie = _executer([git, "-C", str(racine), "config", "core.hooksPath"], racine, delai)
        valeur = sortie.stdout.strip() if sortie.rc == 0 else ""
    attendu = (racine / ".githooks").resolve()
    if git is not None and sortie.rc == 0 and not valeur:
        return KO, "core.hooksPath posé vide (Git lit ./) : les hooks git du kit ne jouent pas", remede
    if not valeur:
        return KO, "core.hooksPath non posé : les hooks git du kit ne jouent pas", remede
    if not _vise_githooks(racine, valeur):
        return KO, f"core.hooksPath = {_sans_controle(valeur)}, pas .githooks de cette racine", remede
    if _githooks_hors_racine(racine):
        return KO, ".githooks/ hors de cette racine : les hooks git joués ne sont pas ceux du dépôt", remede
    if not attendu.is_dir():
        return KO, (f"core.hooksPath = {_sans_controle(valeur)}, mais {attendu} absent : aucun hook git ne "
                    "joue"), remede
    return OK, (f".claude/settings.json : {len(cites)} chemin(s) cité(s) présent(s), "
                f"protect-paths ; core.hooksPath = {_sans_controle(valeur)} — {_BORNE_HOOKS}"), None


def jambe_portes(racine: Path, bash: str | None, delai: int) -> tuple[str, str, str | None]:
    del bash, delai
    liste = ", ".join(GRAINES)
    if (racine / ".agents" / "IS_THE_KIT").exists():
        return SANS_OBJET, f"kit (.agents/IS_THE_KIT) : graines de l'adoptant {liste}", None
    gates = racine / ".agents" / "state" / "gates"
    absentes = [g for g in GRAINES if not (gates / g).is_file()]
    if absentes:
        return KO, (", ".join(absentes) + " absente(s) sous .agents/state/gates/ : désarmée "
                    "délibérément ou jamais posée : indiscernable ici"), REMEDE_PORTES
    return OK, f"{liste} posées sous .agents/state/gates/", None


def jambe_dashboard(racine: Path, bash: str | None, delai: int) -> tuple[str, str, str | None]:
    pyrun = racine / ".agents" / "pyrun.sh"
    demon = racine / ".agents" / "bin" / "dashboard_daemon.py"
    if bash is None:
        return KO, "sonde illisible : bash absent du PATH", REMEDE_INTERPRETEUR
    sortie = _executer([bash, str(pyrun), str(demon), "--root", str(racine), "--status"],
                       racine, delai)
    if sortie.rc is None:
        return KO, _delai_depasse(delai, "dashboard_daemon.py --status"), REMEDE_DASH
    try:
        etat = json.loads(sortie.stdout) if sortie.rc == 0 else None
    except ValueError:
        etat = None
    if not isinstance(etat, dict):
        return KO, f"sonde illisible : {sortie.derniere()}", REMEDE_INTERPRETEUR
    statut = etat.get("status")
    if statut == "alive" and etat.get("code") == "stale":
        return KO, "démon vivant mais code périmé (code: stale)", REMEDE_DASH_PERIME
    if statut == "alive":
        return OK, f"démon vivant, code {etat.get('code')}", None
    if statut == "stale":
        return KO, "verrou sans démon joignable (status: stale)", REMEDE_DASH
    return KO, f"aucun démon joignable (status: {statut})", REMEDE_DASH


JAMBES = (("version", jambe_version), ("outils", jambe_outils), ("scanners", jambe_scanners),
          ("interpréteur", jambe_interpreteur), ("hooks", jambe_hooks), ("portes", jambe_portes),
          ("dashboard", jambe_dashboard))
#: Les variables de banc qui, posées, faussent la jambe — dites dans son détail.
_VARIABLES_DE_BANC = {"version": ("BILAN_KIT_REMOTE",),
                      "outils": ("BILAN_DOCTOR", "BILAN_PROBE_PATH"),
                      "scanners": ("BILAN_DOCTOR", "BILAN_PROBE_PATH"),
                      "interpréteur": ("BILAN_PROBE_PATH",), "dashboard": ("BILAN_PROBE_PATH",)}


# --- contrat -------------------------------------------------------------------

def _ecrire(racine: Path, contrat: dict) -> None:
    """Fichier temporaire du même répertoire, puis `os.replace` — réessayé,
    borné, sur PermissionError (lecteur concurrent sous Windows)."""
    cible = racine / CONTRAT
    courant = racine
    for partie in CONTRAT.parent.parts:
        courant = courant / partie
        if courant.is_symlink():
            raise OSError(f"{courant} est un lien symbolique : écriture refusée")
    cible.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".setup-bilan.", suffix=".tmp", dir=str(cible.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as flux:
            json.dump(contrat, flux, ensure_ascii=False, indent=2)
            flux.write("\n")
            flux.flush()
            os.fsync(flux.fileno())
        for essai in range(5):
            try:
                os.replace(tmp, str(cible))
                return
            except PermissionError:
                if essai == 4:
                    raise
                time.sleep(0.05 * (2 ** essai))
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _ligne(nom: str, etat: str, detail: str, remede: str | None) -> str:
    texte = f"bilan: {nom} : {etat} — {detail}" + (f" ; remède : {remede}" if remede else "")
    return " ".join(texte.split("\n"))


# --- entrée --------------------------------------------------------------------

def _analyseur() -> argparse.ArgumentParser:
    a = argparse.ArgumentParser(
        prog="setup_bilan.py",
        description="Verified station check: kit version, tools, security scanners, "
                    "interpreter >= 3.11, hooks, gates, dashboard - OK | KO | SANS OBJET, each KO "
                    "with its written remedy. "
                    "Exit 0 without KO, 1 on any KO, 2 on usage error.")
    a.add_argument("--root", help="project root (default: the tree that carries this file)")
    # T-01M5QC86XN, lot P : nom anglais en tete, ancien nom garde en alias, `dest` ancien explicite.
    a.add_argument("--no-write", "--sans-ecrire", dest="sans_ecrire", action="store_true",
                   help="write nothing (no .agents/state/local/setup-bilan.json)")
    a.add_argument("--timeout", "--delai", dest="delai", type=int, default=_DELAI_S, help=argparse.SUPPRESS)
    return a


def _sur_sigterm(signum: int, frame) -> None:
    """SIGTERM -> SystemExit (un BaseException) : `_executer` tue le groupe de l'enfant en vol."""
    del frame
    raise SystemExit(128 + signum)


def main(argv: list[str] | None = None) -> int:
    args = _analyseur().parse_args(argv)
    try:
        signal.signal(signal.SIGTERM, _sur_sigterm)
    except ValueError:  # hors du fil principal : le signal reste celui de l'hôte
        pass
    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    racine = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[2]
    if not racine.is_dir() or args.delai < 1:
        quoi = (f"racine {racine} absente ou pas un répertoire" if not racine.is_dir()
                else "--delai < 1")
        print(f"bilan: REFUS — {quoi}", file=sys.stderr)
        return 2
    bash = shutil.which("bash")
    _DOCTOR_LU.clear()  # un passage = un doctor, même rappelé en processus
    jambes = []
    for nom, juge in JAMBES:
        etat, detail, remede = juge(racine, bash, args.delai)
        for variable in _VARIABLES_DE_BANC.get(nom, ()):
            if os.environ.get(variable) is not None:
                detail += f" — {variable} posé (banc)"
        jambes.append({"jambe": nom, "etat": etat, "detail": detail, "remede": remede})
        print(_ligne(nom, etat, detail, remede), flush=True)
    compte = {e: sum(1 for j in jambes if j["etat"] == e) for e in (OK, KO, SANS_OBJET)}
    rc = 1 if compte[KO] else 0
    if not args.sans_ecrire:
        contrat = {"schema": 1,
                   "genere_le": datetime.datetime.now(datetime.timezone.utc).isoformat(
                       timespec="microseconds"),
                   "rc": rc, "jambes": jambes, "commande": COMMANDE}
        try:
            _ecrire(racine, contrat)
        except OSError as exc:
            print(f"bilan: contrat non écrit ({racine / CONTRAT}) — {type(exc).__name__}: {exc}",
                  file=sys.stderr)
    print(f"bilan: OK={compte[OK]} KO={compte[KO]} SANS OBJET={compte[SANS_OBJET]} — exit {rc}",
          flush=True)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
