#!/usr/bin/env python3
"""jira_setup.py — configuration guidée du connecteur Jira du board (T-01M5FQ7F3TDYQAMKQQ8Q30DDSG).

Trois verbes (décision pilote S-01M5FQ7YS37N3HV9BQ1B32S0HQ) :

  etat                       lit `~/.config/cadre/jira.json` SEUL (jamais le trousseau) et nomme la
                             source du jeton ; `JIRA_API_TOKEN` d'environnement est prioritaire ;
  verifier                   lecture seule : `/myself`, `/project/<CLÉ>` et `/mypermissions`, trois
                             GET par `tasks.jira_request`, une ligne par droit ;
  configurer [--changer-jeton]
                             AU TERMINAL DU PILOTE SEUL : refusé (rc 2, rien écrit) sous un marqueur
                             d'agent, avec un argv qui annonce un jeton, ou quand stdin n'est pas un
                             terminal — la commande à taper est alors imprimée. Ordre FIXE : contrôles,
                             puis invites site / projet / e-mail, puis validation, puis écriture de
                             jira.json (0600, os.replace), et SEULEMENT ENSUITE le trousseau et le
                             presse-papiers.

Le jeton ne passe JAMAIS par argv, un fichier, un log ou la sortie : sur macOS il est lu au
presse-papiers (`pbpaste`, capturé), borné, puis écrit au trousseau par `security -i` dont la ligne
arrive sur stdin ; la sortie de `security` est caviardée et le presse-papiers vidé. Hors macOS, le
seul canal est `JIRA_API_TOKEN` dans l'environnement du processus (borne dite).

Le connecteur est réutilisé par `import tasks` (jamais la partie tasks_jira importée seule, qui ne
se charge pas hors de tasks.py) ; aucun transport réseau n'est écrit ici.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tasks  # noqa: E402 — le connecteur Jira vit dans les parties de tasks.py
import tracabilite_jira  # noqa: E402

RC_OK, RC_ECHEC, RC_USAGE = 0, 1, 2
SERVICE = "cadre-jira"
SECURITY = "/usr/bin/security"
PBPASTE = "/usr/bin/pbpaste"
PBCOPY = "/usr/bin/pbcopy"
DELAI_S = 30
EMAIL_MAX = 254
#: Pas d'espace, de guillemet ni d'antislash : la ligne de `security -i` se découpe sur les blancs.
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+")
JETON = re.compile(r"[A-Za-z0-9_=+/.-]{16,1024}")
#: `security -i` coupe une ligne vers 4095 caractères (critique C7) : on reste loin dessous.
LIGNE_MAX = 4000
DROITS = ("BROWSE_PROJECTS", "CREATE_ISSUES", "EDIT_ISSUES", "TRANSITION_ISSUES", "ASSIGN_ISSUES")
VARIABLES = ("CADRE_JIRA_SITE", "CADRE_JIRA_EMAIL", "JIRA_API_TOKEN")
SENTINELLE = "jeton-sentinelle-de-validation"
COMMANDE = "python3 .agents/bin/jira_setup.py configurer"
AU_TERMINAL = f"à taper par le pilote dans son terminal : {COMMANDE}"
BORNE_HORS_MACOS = ("hors macOS : aucun trousseau n'est écrit ; le seul canal du jeton est "
                    "JIRA_API_TOKEN dans l'environnement du processus")


class Refus(Exception):
    """Refus d'usage, message déjà sans secret."""


class _Parseur(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # noqa: D401 — un argv peut porter un secret : jamais réimprimé
        self.print_usage(sys.stderr)
        sys.stderr.write(f"{self.prog}: arguments refusés (détail non réimprimé) — voir --help\n")
        sys.exit(RC_USAGE)


def _parseur() -> _Parseur:
    p = _Parseur(prog="jira_setup.py", allow_abbrev=False,
                 description="Guided setup of the Jira connector: status, verify, configure "
                             "(old French names etat, verifier, configurer still accepted).")
    verbes = p.add_subparsers(dest="verbe", required=True, parser_class=_Parseur)
    # Un alias pose `verbe` = nom TAPE : `set_defaults` le ramene a l'ancien nom, que `main` repartit.
    verbes.add_parser("status", aliases=["etat"],
                      help="jira.json and token source, keychain untouched").set_defaults(verbe="etat")
    verbes.add_parser("verify", aliases=["verifier"],
                      help="read only: /myself, project, permissions").set_defaults(verbe="verifier")
    conf = verbes.add_parser("configure", aliases=["configurer"], help="at the pilot's terminal only")
    conf.set_defaults(verbe="configurer")
    conf.add_argument("--change-token", "--changer-jeton", dest="changer_jeton", action="store_true",
                      help="replace the token stored in the keychain")
    return p


def _dire(ligne: str) -> None:
    print(f"jira: {ligne}", flush=True)


def _chemin_config() -> Path:
    return Path.home() / ".config" / "cadre" / "jira.json"


def _lire_config() -> dict[str, Any]:
    """jira.json, {} s'il est absent ; Refus s'il est illisible."""
    chemin = _chemin_config()
    if not chemin.is_file():
        return {}
    try:
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise Refus(f"configuration locale illisible : {chemin}") from None
    return donnees if isinstance(donnees, dict) else {}


def _ecrire_config(donnees: dict[str, str]) -> Path:
    """Écrit jira.json en 0600 (mkstemp) puis os.replace, réessayé avec recul borné."""
    chemin = _chemin_config()
    chemin.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(chemin.parent), prefix=".jira.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as flux:
            json.dump(donnees, flux, ensure_ascii=False, indent=2)
            flux.write("\n")
        for essai in range(5):
            try:
                os.replace(tmp, chemin)
                break
            except PermissionError:
                if essai == 4:
                    raise
                time.sleep(0.05 * 2 ** essai)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return chemin


def _lancer(argv: list[str], entree: str | None = None) -> subprocess.CompletedProcess:
    """Le SEUL site subprocess : liste d'arguments, jamais de shell, sortie capturée, délai borné.
    Le jeton n'y passe que par `entree` (stdin), jamais par `argv`."""
    flux: dict[str, Any] = {"input": entree} if entree is not None else {"stdin": subprocess.DEVNULL}
    try:
        return subprocess.run(argv, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=DELAI_S, check=False, **flux)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(argv, 124, "", "délai dépassé")
    except OSError as exc:
        return subprocess.CompletedProcess(argv, 127, "", type(exc).__name__)


def _demander(invite: str, actuelle: str = "") -> str:
    suffixe = f" [{tracabilite_jira.imprimable(actuelle)}]" if actuelle else ""
    try:
        reponse = input(f"{invite}{suffixe} : ").strip()
    except EOFError:
        raise Refus("saisie interrompue") from None
    return reponse or actuelle


# --- validation ----------------------------------------------------------------

def valider(site: str, projet: str, email: str) -> tuple[str, str, str]:
    """(site normalisé, projet, e-mail) ; Refus sinon. Site et e-mail passent par
    `tasks._jira_config(keychain=False)` sous un environnement TEMPORAIRE, restauré en `finally`."""
    if len(email) > EMAIL_MAX or not EMAIL.fullmatch(email):
        raise Refus(f"e-mail refusé (au plus {EMAIL_MAX} caractères, [A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+)")
    if not tasks._JIRA_PROJECT.fullmatch(projet):
        raise Refus("clé de projet refusée (majuscule, puis 1 à 9 majuscules, chiffres ou _)")
    if "://" not in site:
        site = "https://" + site
    sauve = {nom: os.environ.get(nom) for nom in VARIABLES}
    try:
        os.environ.update(CADRE_JIRA_SITE=site, CADRE_JIRA_EMAIL=email, JIRA_API_TOKEN=SENTINELLE)
        base, local, _ = tasks._jira_config(keychain=False)
    except tasks.BoardError as exc:
        raise Refus(str(exc)) from None
    finally:
        for nom, valeur in sauve.items():
            if valeur is None:
                os.environ.pop(nom, None)
            else:
                os.environ[nom] = valeur
    if local:
        raise Refus("site local refusé : réservé au faux Jira des bancs")
    return base, projet, email


# --- trousseau -----------------------------------------------------------------

def _present(email: str) -> bool | None:
    """Élément cadre-jira présent (rc 0), absent (rc 44), sinon None. Sans `-w` : rien n'est lu."""
    sortie = _lancer([SECURITY, "find-generic-password", "-s", SERVICE, "-a", email])
    return True if sortie.returncode == 0 else False if sortie.returncode == 44 else None


def _saisir_jeton(email: str) -> bool:
    """Presse-papiers -> trousseau. Le jeton ne sort jamais : ni argv, ni fichier, ni sortie."""
    print("Copiez le jeton API Atlassian (https://id.atlassian.com/manage-profile/security/"
          "api-tokens) dans le presse-papiers ; il ne sera jamais affiché.", flush=True)
    try:
        # getpass, jamais input : un jeton collé ici par erreur n'est pas affiché.
        getpass.getpass("Jeton copié ? Appuyez sur Entrée : ")
    except EOFError:
        raise Refus("saisie interrompue") from None
    try:
        lu = _lancer([PBPASTE])
        jeton = (lu.stdout or "").strip()
        if lu.returncode != 0 or not JETON.fullmatch(jeton):
            _dire("jeton : refusé — presse-papiers vide ou hors forme ([A-Za-z0-9_=+/.-], 16 à 1024 "
                  "caractères) ; rien écrit au trousseau")
            return False
        ligne = f"add-generic-password -U -s {SERVICE} -a {email} -w {jeton}\n"
        if len(ligne) >= LIGNE_MAX:
            _dire(f"jeton : refusé — ligne de {len(ligne)} caractères (borne {LIGNE_MAX})")
            return False
        ecrit = _lancer([SECURITY, "-i"], entree=ligne)
        bruit = tracabilite_jira.caviarder((ecrit.stdout or "") + (ecrit.stderr or ""), [jeton])
        # `security -i` rend le rc de la commande interne en échec (mesuré : 44, puis 1 sur
        # -25300 ou commande inconnue) : le rc décide. Le stderr d'un `add -U` réussi n'est pas
        # mesuré : non vide sous rc 0, il est DIT (caviardé), jamais compté comme un échec.
        if ecrit.returncode != 0 or not _present(email):
            _dire(f"jeton : écriture au trousseau échouée (rc {ecrit.returncode}) — "
                  f"{tracabilite_jira.imprimable(bruit.strip())[:200]}")
            return False
        if (ecrit.stderr or "").strip():
            _dire("jeton : security a écrit un message malgré le succès — vérifiez par "
                  f"`python3 .agents/bin/jira_setup.py verifier` : "
                  f"{tracabilite_jira.imprimable(bruit.strip())[:200]}")
        _dire(f"jeton : enregistré au trousseau (service {SERVICE}, compte {email})")
        return True
    finally:
        _lancer([PBCOPY], entree="")  # presse-papiers vidé, quoi qu'il arrive


# --- verbes --------------------------------------------------------------------

def _source_jeton(email: str) -> str:
    if os.environ.get("JIRA_API_TOKEN", "").strip():
        return "environnement (JIRA_API_TOKEN, prioritaire sur le trousseau)"
    if sys.platform == "darwin":
        return f"trousseau macOS, service {SERVICE}, compte {email or '?'} (non consulté par etat)"
    return f"absent — {BORNE_HORS_MACOS}"


def etat() -> int:
    try:
        config = _lire_config()
    except Refus as refus:
        _dire(str(refus))
        return RC_ECHEC
    if not config:
        _dire(f"configuration : absente ({_chemin_config()}) — {AU_TERMINAL}")
        _dire(f"jeton : {_source_jeton('')}")
        return RC_ECHEC
    site, email, projet = (tracabilite_jira.imprimable(config.get(k, "?")) for k in
                           ("site", "email", "project"))
    _dire(f"configuration : {_chemin_config()} — site {site}, e-mail {email}, projet {projet}")
    _dire(f"jeton : {_source_jeton(email)}")
    return RC_OK


def _verifier() -> tuple[int, int | None]:
    """(rc, statut HTTP de /myself) : trois GET, aucune écriture."""
    try:
        projet = str(_lire_config().get("project") or "")
        if not tasks._JIRA_PROJECT.fullmatch(projet):
            raise Refus(f"projet absent ou refusé dans jira.json — {AU_TERMINAL}")
        config = tasks._jira_config()
        moi, _ = tasks.jira_request("GET", "/rest/api/3/myself", config=config)
        _dire(f"compte (/myself) : {'ok' if moi == 200 else 'refusé'} — HTTP {moi}")
        if moi != 200:
            return RC_ECHEC, moi
        statut, _ = tasks.jira_request("GET", f"/rest/api/3/project/{projet}", config=config)
        _dire(f"projet {projet} : {'ok' if statut == 200 else 'refusé'} — HTTP {statut}")
        statut_p, corps = tasks.jira_request(
            "GET", f"/rest/api/3/mypermissions?projectKey={projet}&permissions={','.join(DROITS)}",
            config=config)
    except (Refus, tasks.BoardError) as exc:
        _dire(str(exc))
        return RC_ECHEC, None
    try:
        droits = json.loads(corps.decode("utf-8")).get("permissions", {}) if statut_p == 200 else {}
    except (ValueError, AttributeError):
        droits = {}
    tenus = 0
    for droit in DROITS:
        entree = droits.get(droit) if isinstance(droits, dict) else None
        oui = isinstance(entree, dict) and entree.get("havePermission") is True
        tenus += oui
        _dire(f"droit {droit} : {'oui' if oui else 'non'}" + ("" if statut_p == 200 else
                                                               f" — HTTP {statut_p}"))
    return (RC_OK if statut == 200 and tenus == len(DROITS) else RC_ECHEC), moi


def verifier() -> int:
    return _verifier()[0]


def _refus_contexte() -> str:
    agent = tracabilite_jira.agent_appelant()
    if agent:
        return f"configurer refusé sous agent ({agent}) : un agent n'écrit jamais le jeton"
    if sys.stdin is None or not sys.stdin.isatty():
        return "configurer refusé : stdin n'est pas un terminal"
    return ""


def configurer(changer_jeton: bool = False) -> int:
    raison = _refus_contexte()
    if raison:
        _dire(f"{raison} — {AU_TERMINAL}")
        return RC_USAGE
    try:
        actuelle = _lire_config()
        site = _demander("site Jira Cloud (https://<nom>.atlassian.net)", str(actuelle.get("site") or ""))
        projet = _demander("clé du projet Jira", str(actuelle.get("project") or "")).upper()
        email = _demander("e-mail du compte Jira", str(actuelle.get("email") or ""))
        site, projet, email = valider(site, projet, email)
        chemin = _ecrire_config({"site": site, "email": email, "project": projet})
        _dire(f"configuration : écrite ({chemin}, 0600) — site {site}, projet {projet}")
        if os.environ.get("JIRA_API_TOKEN", "").strip():
            _dire("jeton : JIRA_API_TOKEN est posé dans l'environnement, il prime sur le trousseau")
        if sys.platform != "darwin":
            _dire(f"jeton : {BORNE_HORS_MACOS}")
            return verifier() if os.environ.get("JIRA_API_TOKEN", "").strip() else RC_ECHEC
        present = _present(email)
        if present is None:
            _dire("jeton : trousseau illisible (security find-generic-password) — rien écrit")
            return RC_ECHEC
        if (not present or changer_jeton) and not _saisir_jeton(email):
            return RC_ECHEC
        rc, statut = _verifier()
        if statut in (401, 403):
            reponse = input(f"Jira refuse ce jeton (HTTP {statut}). Le remplacer ? [o/N] ").strip()
            if reponse in ("o", "O", "oui"):
                if not _saisir_jeton(email):
                    return RC_ECHEC
                rc, _ = _verifier()
        return rc
    except EOFError:
        _dire("saisie interrompue — rien d'autre n'est fait")
        return RC_USAGE
    except Refus as refus:
        _dire(f"{refus} — rien écrit au trousseau")
        return RC_USAGE


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if tracabilite_jira.argv_refuse(argv):
        sys.stderr.write("jira_setup.py: argument refusé — un jeton ne passe jamais par argv ; "
                         f"{AU_TERMINAL}\n")
        return RC_USAGE
    args = _parseur().parse_args(argv)
    if args.verbe == "etat":
        return etat()
    if args.verbe == "verifier":
        return verifier()
    if args.verbe != "configurer":  # un verbe non ramené à l'ancien nom ne tombe jamais dans le geste du pilote
        sys.stderr.write(f"jira_setup.py: verbe non reconnu : {args.verbe}\n")
        return RC_USAGE
    return configurer(args.changer_jeton)


if __name__ == "__main__":
    raise SystemExit(main())
