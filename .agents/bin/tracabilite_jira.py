#!/usr/bin/env python3
"""EXPORT DES TÂCHES DU BOARD VERS JIRA — aperçu, CSV hors ligne, REST v3 Jira Cloud (T-01M5A113J9NF1BQ9KSTJHNWT9H).

DÉCISION PILOTE S-01M54GFZQTEYDGWZSE3Q3FECTF : l'URL, la clé de projet et le jeton sont demandés AU MOMENT et ne
sont JAMAIS écrits dans le dépôt. Cet outil n'écrit rien, nulle part, sauf le fichier CSV que l'on nomme soi-même
(`--csv <fichier>`), qui ne porte ni URL, ni clé de projet, ni jeton.

TROIS SORTIES.
  * défaut — APERÇU : le JSON des charges qui SERAIENT envoyées, sur stdout. Aucun réseau, aucun jeton demandé.
  * `--csv <fichier|->` — import CSV de Jira : colonnes `Summary`, `Issue Type`, `Description`, puis UNE colonne
    `Labels` par label (c'est ainsi que l'import de Jira lit plusieurs labels). Hors ligne, sans jeton.
  * `--envoyer` — REST v3 de Jira Cloud, authentification Basic (e-mail du compte + jeton d'API). Jira Data
    Center (API v2, jeton personnel) est HORS PÉRIMÈTRE.

SÉLECTION : `--task <T-id>` (répétable), `--epic E-NN`, `--chantier <nom>`, `--etat <état>` — combinés en ET —, ou
`--tout`. Aucune sélection : rc 2. `--limite N` borne le nombre de tâches, et le dit sur stderr (premier envoi réel
conseillé : `--envoyer --limite 1`).

LE JETON. Par la variable `JIRA_API_TOKEN`, sinon par une saisie masquée (`getpass`, terminal seul), sinon rc 2.
Il ne se passe JAMAIS en argument : tout élément d'argv qui commence par `--tok` ou `--jet`, avec ou sans `=`, est
refusé (rc 2) AVANT l'analyse des arguments, et sa valeur n'est jamais réimprimée. `ArgumentParser.error` est
surchargée : une erreur d'usage ne fait jamais écho d'argv. Ni le jeton, ni l'en-tête `Authorization`, ni leur
base64 ne sont imprimés : toute réponse du serveur est caviardée avant d'être citée. Un jeton EXPORTÉ dans un
profil de shell est hérité par chaque shell d'agent : le passer en ligne de commande pour un seul lancement
(`JIRA_API_TOKEN=… python3 …`) ou par la saisie masquée.

L'ENVOI.
  * `https` exigé ; `http` admis pour les hôtes `127.0.0.1` et `localhost` SEULS, par égalité EXACTE du nom
    d'hôte (`localhost.example.invalid` est refusé) — pour le banc. Refus AVANT tout appel et avant le jeton.
  * Redirections JAMAIS suivies (un 30x est un échec), réponse bornée à 1 Mio, délai 20 s.
  * Idempotence par label : avant chaque création, `GET /rest/api/3/search/jql` sur
    `project = "<CLÉ>" AND labels = "<T-id>"` ; trouvé → `déjà là`, sinon `POST /rest/api/3/issue` (résumé
    `[<T-id>] <titre>` tronqué à 255, labels = T-id puis épopée, description au format ADF version 1).
  * Une ligne par tâche, `jira: <T-id> → <CLÉ-N> (créée|déjà là)` ou `jira: <T-id> → échec <code>` ; rc 1 au
    moindre échec ; un 429 arrête l'envoi et dit combien de tâches n'ont pas été tentées.
  * Sous un contexte d'agent (`AGENT_CALLER_MARKERS`, même tuple que `skills_github_fallback.py`), `--envoyer`
    est REFUSÉ : l'envoi est un geste du pilote, depuis SON terminal. Garde de LISIBILITÉ, pas une frontière : un
    terminal ouvert depuis un agent hérite du marqueur (faux positif voulu) ; un hôte dont le shell ne pose aucun
    marqueur mesuré n'est pas vu (faux négatif nommé). Aperçu et CSV restent ouverts aux agents.

LE BOARD est lu par `etat_lecture.taches` seul. Illisible — y compris sous un interpréteur trop ancien pour ses
propriétaires — il est DIT, `board illisible (Python X.Y : <Exc>)`, rc 1, jamais un Traceback.

BORNE NOMMÉE : le contrat REST n'est mesuré que contre un serveur bouchon (banc `test_tracabilite_jira.py`),
jamais contre un vrai Jira.

rc : 0 succès · 1 échec (board illisible, envoi en échec, tâche inconnue) · 2 usage (sélection absente, argument
refusé, URL refusée, jeton absent, contexte d'agent).
"""

from __future__ import annotations

import argparse
import base64
import csv
import getpass
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

RC_OK, RC_ECHEC, RC_USAGE = 0, 1, 2
DELAI_S = 20
REPONSE_MAX = 1 << 20
RESUME_MAX = 255
DETAIL_MAX = 200
HOTES_LOCAUX = ("127.0.0.1", "localhost")
PREFIXES_REFUSES = ("--tok", "--jet")
CAVIARDE = "<caviardé>"
RACINE_DEFAUT = Path(__file__).resolve().parents[2]

# Même tuple que `skills_github_fallback.AGENT_CALLER_MARKERS` — le banc tient l'égalité (J6).
# Copilot CLI pose `COPILOT_AGENT_SESSION_ID` et `COPILOT_CLI=1` dans le shell de l'agent
# (mesuré, Copilot CLI 1.0.96, T-01M5MCXKHQS4BME9Z9VVSWD6VT M7). FAUX POSITIF voulu, comme
# CLAUDECODE sous Claude Code : `COPILOT_CLI` est hérité par tout shell lancé depuis Copilot CLI,
# échappement `!` du pilote compris — ce shell est refusé ; le pilote joue le geste depuis son
# PROPRE terminal, jamais un terminal ouvert par un agent.
AGENT_CALLER_MARKERS = (
    "CLAUDECODE",
    "CLAUDE_CODE_ENTRYPOINT",
    "AGENTS_HOOK_HOST",
    "COPILOT_AGENT_SESSION_ID",
    "COPILOT_CLI",
)

T_ID = re.compile(r"T-(?:[0-9]{3,15}|[0-9A-HJKMNP-TV-Z]{10,26})")
CLE_PROJET = re.compile(r"[A-Z][A-Z0-9_]{1,9}")
EPIC_ID = re.compile(r"E-[0-9]{1,6}")


class Refus(Exception):
    """Refus d'usage : rc 2, message déjà sans secret."""


class _Parseur(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # noqa: D401 — surcharge voulue (C6)
        # argparse réimprimerait l'argv fautif (« unrecognized arguments: … ») : jamais d'écho ici.
        self.print_usage(sys.stderr)
        sys.stderr.write(f"{self.prog}: arguments refusés (détail non réimprimé : un argv peut porter un "
                         f"secret) — voir --help\n")
        sys.exit(RC_USAGE)


def _parseur() -> _Parseur:
    p = _Parseur(prog="tracabilite_jira.py", allow_abbrev=False,
                 description="Exports board tasks to Jira: preview (default), --csv, --send "
                             "(old French option names still accepted).")
    p.add_argument("--root", default=str(RACINE_DEFAUT), help="repository root (default: this script's)")
    p.add_argument("--task", action="append", default=[], help="T-id, repeatable")
    p.add_argument("--epic", help="E-NN")
    # Nom anglais en tete, ancien nom francais en alias, `dest` ancien : `selectionner` lit args.<ancien>.
    p.add_argument("--workstream", "--chantier", dest="chantier", metavar="WORKSTREAM")
    p.add_argument("--state", "--etat", dest="etat", metavar="STATE", help="pending, running, blocked or done")
    p.add_argument("--all", "--tout", dest="tout", action="store_true", help="every task")
    p.add_argument("--limit", "--limite", dest="limite", metavar="N", type=int, help="at most N tasks")
    p.add_argument("--type", default="Task", help="Jira issue type (default: Task)")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--csv", metavar="FILE", help="writes the CSV import to FILE (`-`: stdout)")
    mode.add_argument("--send", "--envoyer", dest="envoyer", action="store_true",
                      help="creates the issues through REST v3 (Jira Cloud)")
    p.add_argument("--url", help="Jira Cloud site URL, asked otherwise")
    p.add_argument("--project", "--projet", dest="projet", metavar="KEY", help="Jira project key, asked otherwise")
    p.add_argument("--email", help="Jira account e-mail, asked otherwise")
    return p


def argv_refuse(argv: list[str]) -> bool:
    """Vrai si un élément d'argv porte (ou annonce) un jeton : `--tok*` ou `--jet*`, avec ou sans `=`."""
    return any(a.lower().startswith(PREFIXES_REFUSES) for a in argv)


def agent_appelant(env: Any = None) -> str:
    """Le premier marqueur d'agent présent et non vide, sinon "" (même lecture que skills_github_fallback)."""
    env = os.environ if env is None else env
    for nom in AGENT_CALLER_MARKERS:
        if env.get(nom, "").strip():
            return nom
    return ""


# --------------------------------------------------------------------------- lecture et sélection
def lire_taches(root: str) -> list[dict[str, Any]]:
    """Les tâches par `etat_lecture.taches` ; toute défaillance devient une `RuntimeError` qui la NOMME."""
    bin_dir = str(Path(__file__).resolve().parent)
    if bin_dir not in sys.path:
        sys.path.insert(0, bin_dir)
    version = f"{sys.version_info[0]}.{sys.version_info[1]}"
    try:
        import etat_lecture  # noqa: E402 — chargé à l'appel : un échec d'import est dit, pas levé
        return list(etat_lecture.taches(root))
    except Exception as exc:  # noqa: BLE001 — tout échec de lecture est NOMMÉ, jamais un Traceback
        detail = str(exc).splitlines()[0][:DETAIL_MAX] if str(exc) else ""
        raise RuntimeError(f"board illisible (Python {version} : {type(exc).__name__}"
                           f"{' — ' + detail if detail else ''})") from None


def selectionner(taches: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    if not (args.tout or args.task or args.epic or args.chantier or args.etat):
        raise Refus("aucune sélection : --task, --epic, --chantier, --etat ou --tout")
    for tid in args.task:
        if not T_ID.fullmatch(tid):
            raise Refus("--task : identifiant mal formé (attendu T-<chiffres> ou T-<ULID>)")
    if args.epic and not EPIC_ID.fullmatch(args.epic):
        raise Refus("--epic : identifiant mal formé (attendu E-NN)")
    connus = {t.get("id") for t in taches}
    inconnues = [tid for tid in args.task if tid not in connus]
    if inconnues:
        raise LookupError("tâche(s) inconnue(s) au board : " + ", ".join(inconnues))
    retenues = [t for t in taches
                if (not args.task or t.get("id") in args.task)
                and (not args.epic or t.get("epic") == args.epic)
                and (not args.chantier or t.get("chantier") == args.chantier)
                and (not args.etat or t.get("state") == args.etat)]
    importees = sum(bool(t.get("jira_key")) for t in retenues)
    if importees:
        print(f"Jira : {importees} tâche(s) importée(s) exclue(s) de l'export", file=sys.stderr)
    retenues = [t for t in retenues if not t.get("jira_key")]
    if args.limite is not None:
        if args.limite < 1:
            raise Refus("--limite : un entier ≥ 1")
        if len(retenues) > args.limite:
            print(f"limite {args.limite} : {len(retenues) - args.limite} tâche(s) écartée(s) sur {len(retenues)}",
                  file=sys.stderr)
            retenues = retenues[:args.limite]
    return retenues


# --------------------------------------------------------------------------- charges
def labels(t: dict[str, Any]) -> list[str]:
    epic = t.get("epic") or ""
    return [t["id"]] + ([epic] if epic else [])


def resume(t: dict[str, Any]) -> str:
    return " ".join(f"[{t['id']}] {t.get('task', '')}".split())[:RESUME_MAX]


def lignes_description(t: dict[str, Any]) -> list[str]:
    deps = t.get("depends_on") or []
    return [
        f"Tâche : {t['id']}",
        f"Titre : {t.get('task', '')}",
        f"État : {t.get('state') or '—'}",
        f"Chantier : {t.get('chantier') or '—'}",
        f"Épopée : {t.get('epic') or '—'}",
        f"Stage : {t.get('stage') or '—'}",
        f"Dépendances : {', '.join(deps) if deps else 'aucune'}",
        "Exporté par tracabilite_jira.py",
    ]


def adf(t: dict[str, Any]) -> dict[str, Any]:
    """Description au format ADF version 1 : un paragraphe par ligne, un saut de ligne interne en `hardBreak`."""
    paragraphes = []
    for ligne in lignes_description(t):
        contenu: list[dict[str, Any]] = []
        for i, morceau in enumerate(ligne.split("\n")):
            if i:
                contenu.append({"type": "hardBreak"})
            if morceau:
                contenu.append({"type": "text", "text": morceau})
        paragraphes.append({"type": "paragraph", "content": contenu})
    return {"type": "doc", "version": 1, "content": paragraphes}


def charge(t: dict[str, Any], projet: str, type_ticket: str) -> dict[str, Any]:
    return {"fields": {
        "project": {"key": projet},
        "summary": resume(t),
        "issuetype": {"name": type_ticket},
        "labels": labels(t),
        "description": adf(t),
    }}


def ecrire_csv(taches: list[dict[str, Any]], type_ticket: str, flux: Any) -> None:
    n_labels = max([len(labels(t)) for t in taches] + [1])
    ecrivain = csv.writer(flux)
    ecrivain.writerow(["Summary", "Issue Type", "Description"] + ["Labels"] * n_labels)
    for t in taches:
        lab = labels(t)
        ecrivain.writerow([resume(t), type_ticket, "\n".join(lignes_description(t))]
                          + lab + [""] * (n_labels - len(lab)))


# --------------------------------------------------------------------------- HTTP
class _SansRedirection(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401, ANN001
        return None  # jamais suivie : le 30x remonte en HTTPError, donc en échec


def _opener(local: bool) -> urllib.request.OpenerDirector:
    gestionnaires: list[Any] = [_SansRedirection()]
    if local:
        gestionnaires.append(urllib.request.ProxyHandler({}))  # la boucle locale ne passe jamais par un proxy
    return urllib.request.build_opener(*gestionnaires)


def _ouvrir(requete: urllib.request.Request, local: bool) -> Any:
    return _opener(local).open(requete, timeout=DELAI_S)


def _lire_borne(flux: Any) -> bytes:
    corps = flux.read(REPONSE_MAX + 1)
    if len(corps) > REPONSE_MAX:
        raise ValueError("réponse au-delà de 1 Mio")
    return corps


def appel(methode: str, url: str, auth: str, local: bool, corps: Any = None) -> tuple[int, bytes]:
    """(code, corps). Un code HTTP d'erreur est RENDU ; une panne de transport lève `OSError` sans secret."""
    entetes = {"Accept": "application/json", "Authorization": auth, "User-Agent": "tracabilite_jira"}
    donnees = None
    if corps is not None:
        donnees = json.dumps(corps).encode("utf-8")
        entetes["Content-Type"] = "application/json"
    requete = urllib.request.Request(url, data=donnees, headers=entetes, method=methode)
    try:
        with _ouvrir(requete, local) as reponse:
            return reponse.status, _lire_borne(reponse)
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, _lire_borne(exc)
        except (OSError, ValueError):
            return exc.code, b""
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise OSError(f"transport : {type(exc).__name__}") from None


def caviarder(texte: str, secrets: list[str]) -> str:
    for s in sorted((s for s in secrets if s), key=len, reverse=True):
        texte = texte.replace(s, CAVIARDE)
    return texte


# Le détail renvoyé par le serveur, ses clés, et un id du board hors forme sont des DONNÉES : avant impression,
# tout caractère de contrôle (C0 hors tabulation et saut de ligne, DEL, C1) sort en `?`.
CONTROLE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def imprimable(texte: Any) -> str:
    return CONTROLE.sub("?", str(texte))


def detail_erreur(corps: bytes, secrets: list[str]) -> str:
    try:
        donnees = json.loads(corps.decode("utf-8"))
        morceaux = list(donnees.get("errorMessages") or []) + [f"{k}: {v}" for k, v in
                                                               (donnees.get("errors") or {}).items()]
        texte = " ; ".join(str(m) for m in morceaux)
    except (ValueError, AttributeError, UnicodeDecodeError):
        texte = corps.decode("utf-8", errors="replace")
    return imprimable(caviarder(" ".join(texte.split()), secrets)[:DETAIL_MAX])


def base_url(brute: str) -> tuple[str, bool]:
    """(base, locale). https exigé ; http pour 127.0.0.1 et localhost seuls, par ÉGALITÉ exacte du nom d'hôte."""
    try:
        p = urllib.parse.urlsplit(brute.strip())
        hote = p.hostname or ""
        p.port  # noqa: B018 — un port illisible lève ici, pas au premier appel
    except ValueError:
        raise Refus("URL refusée : illisible") from None
    if p.username or p.password:
        raise Refus("URL refusée : elle ne porte jamais d'identifiants")
    if p.query or p.fragment:
        raise Refus("URL refusée : ni requête ni fragment")
    local = hote in HOTES_LOCAUX
    if not hote or not (p.scheme == "https" or (p.scheme == "http" and local)):
        raise Refus("URL refusée : https exigé (http admis pour 127.0.0.1 et localhost seuls, nom d'hôte exact)")
    return f"{p.scheme}://{p.netloc}{p.path.rstrip('/')}", local


def _demander(valeur: str | None, invite: str, quoi: str) -> str:
    if valeur:
        return valeur.strip()
    if not sys.stdin.isatty():
        raise Refus(f"{quoi} absent(e) : option ou saisie dans un terminal")
    return input(invite).strip()


def envoyer(taches: list[dict[str, Any]], args: argparse.Namespace) -> int:
    marqueur = agent_appelant()
    if marqueur:
        raise Refus(f"--envoyer refusé : contexte d'agent ({marqueur}) — l'envoi vers Jira est un geste du "
                    f"pilote, depuis SON terminal ; aperçu et --csv restent ouverts")
    base, local = base_url(_demander(args.url, "URL Jira Cloud (https://<site>.atlassian.net) : ", "URL"))
    projet = _demander(args.projet, "Clé du projet Jira : ", "clé de projet")
    if not CLE_PROJET.fullmatch(projet):
        raise Refus("clé de projet refusée : majuscules, chiffres ou _, 2 à 10 signes, une lettre en tête")
    email = _demander(args.email, "E-mail du compte Jira : ", "e-mail")
    if "@" not in email or ":" in email or any(c.isspace() for c in email):
        raise Refus("e-mail refusé : une adresse, sans « : » ni blanc")
    jeton = os.environ.get("JIRA_API_TOKEN", "").strip()
    if not jeton and sys.stdin.isatty():
        jeton = getpass.getpass("Jeton d'API Jira (saisie masquée) : ").strip()
    if not jeton:
        raise Refus("jeton absent : JIRA_API_TOKEN ou saisie masquée dans un terminal")
    paire = f"{email}:{jeton}"
    b64 = base64.b64encode(paire.encode("utf-8")).decode("ascii")
    auth = f"Basic {b64}"
    secrets = [auth, b64, paire, jeton]
    rc = RC_OK
    for i, t in enumerate(taches):
        tid = t["id"]
        if not isinstance(tid, str) or not T_ID.fullmatch(tid):
            # `--tout`, `--epic`, `--chantier`, `--etat` prennent l'id du BOARD tel quel : un id hors forme
            # n'entre JAMAIS dans une requête JQL (guillemet, `OR`…). Sauté, dit, et l'envoi rend rc 1.
            print(f"jira: {imprimable(tid)[:DETAIL_MAX]} → sauté (id hors forme T-<chiffres> ou T-<ULID>, "
                  "jamais mis dans une requête JQL)")
            rc = RC_ECHEC
            continue
        jql = f'project = "{projet}" AND labels = "{tid}"'
        url = f"{base}/rest/api/3/search/jql?" + urllib.parse.urlencode({"jql": jql, "fields": "key",
                                                                        "maxResults": "1"})
        try:
            code, corps = appel("GET", url, auth, local)
            if code == 200:
                trouves = json.loads(corps.decode("utf-8")).get("issues") or []
                if trouves:
                    print(f"jira: {tid} → {imprimable(trouves[0].get('key', '?'))} (déjà là)")
                    continue
                code, corps = appel("POST", f"{base}/rest/api/3/issue", auth, local,
                                    charge(t, projet, args.type))
                if code in (200, 201):
                    print(f"jira: {tid} → {imprimable(json.loads(corps.decode('utf-8')).get('key', '?'))} (créée)")
                    continue
        except OSError as exc:
            print(f"jira: {tid} → échec ({caviarder(str(exc), secrets)})")
            return RC_ECHEC
        except (ValueError, AttributeError, UnicodeDecodeError):
            print(f"jira: {tid} → échec (réponse illisible)")
            rc = RC_ECHEC
            continue
        print(f"jira: {tid} → échec {code} : {detail_erreur(corps, secrets)}")
        rc = RC_ECHEC
        if code == 429:
            print(f"arrêt : 429 (limite de débit de Jira) — {len(taches) - i - 1} tâche(s) non tentée(s)",
                  file=sys.stderr)
            return RC_ECHEC
    return rc


# --------------------------------------------------------------------------- entrée
def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv_refuse(argv):
        print("tracabilite_jira.py : un jeton ne se passe JAMAIS en argument (élément --tok…/--jet… refusé, "
              "valeur non réimprimée) — JIRA_API_TOKEN ou saisie masquée", file=sys.stderr)
        return RC_USAGE
    args = _parseur().parse_args(argv)
    mode = "envoyer" if args.envoyer else ("csv" if args.csv else "apercu")
    try:
        taches = selectionner(lire_taches(args.root), args)
        if mode == "envoyer":
            return envoyer(taches, args)
        if mode == "csv":
            if args.csv == "-":
                ecrire_csv(taches, args.type, sys.stdout)
            else:
                with open(args.csv, "w", newline="", encoding="utf-8") as flux:
                    ecrire_csv(taches, args.type, flux)
            print(f"csv : {len(taches)} tâche(s)", file=sys.stderr)
            return RC_OK
        projet = args.projet or "<CLÉ demandée à l'envoi>"
        print(json.dumps([charge(t, projet, args.type) for t in taches], ensure_ascii=False, indent=2))
        print(f"aperçu : {len(taches)} tâche(s), rien envoyé (--csv ou --envoyer)", file=sys.stderr)
        return RC_OK
    except Refus as exc:
        print(f"tracabilite_jira.py : {exc}", file=sys.stderr)
        return RC_USAGE
    except (RuntimeError, LookupError, OSError) as exc:
        print(f"tracabilite_jira.py : {exc}", file=sys.stderr)
        return RC_ECHEC


if __name__ == "__main__":
    sys.exit(main())
