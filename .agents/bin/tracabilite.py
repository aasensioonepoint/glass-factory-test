#!/usr/bin/env python3
"""RELIER TÂCHE, COMMITS ET PR — et dire le palier du numéro de tâche (T-01M5A113DGRQB2F0RX6ECX73HN, plan D3).

TROIS VERBES.
  * `bilan [-n N | --depuis <ref>]` — les commits de HEAD (les N derniers, défaut 200, fusions comprises ; ou
    `<ref>..HEAD`) rangés en `avec T-id`, `Sans-tache`, `fusions`, `chore(state|runs)`, `ni l'un ni l'autre` (liste :
    sha court, sujet) ; puis la ligne `palier: avertissement|refus (K/N, seuil 95 %)`, calculée par la RÈGLE DE
    `.githooks/commit-msg`, À L'IDENTIQUE et sur SA fenêtre, quels que soient `-n` et `--depuis` : la commande du
    hook (`git -c log.showSignature=false log --no-merges -n 200 --format=%x01%B HEAD`), le même découpage (un
    message s'ouvre à chaque ligne qui commence par l'octet 0x01), les messages dont la 1re ligne ouvre par
    `chore(state): ` ou `chore(runs): ` exclus (N = les autres), K = ceux qui satisfont LE prédicat unitaire
    (`porte`, le même qui range les commits). N < 20 ou K×100 < N×95 → avertissement, sinon refus.
  * `tache <T-id> [--pr]` — le T-id est VALIDÉ (forme entière du numéro du hook) avant tout appel, sinon rc 2 ; les
    commits de TOUTES les branches qui citent l'id ou un préfixe de 10 caractères au moins (ou dont l'id cité
    commence par celui demandé) ; `--pr` : `gh pr list --state all --search <id> --json number,title,url,state
    --limit 50` (argv liste, stdin fermé, délai 30 s). gh absent → `pr : gh absent — lien non vérifié`, rc 0 ; gh en
    échec → `pr : gh a échoué (rc N) : <dernière ligne>`, rc 1.
  * `pr-corps --base <ref>` — le corps Markdown d'une PR : `## Tâches`, les ids cités par `<ref>..HEAD` résolus au
    board (titre, état ; `inconnue au board` ; un préfixe porté par plusieurs tâches → `ambiguë`), puis
    `## Sans tâche`, les commits qui portent une sortie `Sans-tache:` et leur raison.

LA RÈGLE DU NUMÉRO (celle du hook, sous `LC_ALL=C` : octets, classes ASCII) : lignes lues jusqu'à la première qui
FINIT par ` ------------------------ >8 ------------------------`, lignes `#` sautées ; un numéro
`(^|[^A-Za-z0-9_-])T-([0-9]{3,15}|[0-9A-HJKMNP-TV-Z]{10,26})([^A-Za-z0-9]|$)`, sinon une ligne qui COMMENCE par
`Sans-tache:` suivie d'au moins 10 caractères non blancs. Forme jugée, jamais l'existence au board (sauf
`pr-corps`, qui résout).

SÛRETÉ. git en argv liste, sous `-c core.hooksPath=/dev/null -c core.fsmonitor=false`, à la racine `--root` ;
toute ref fournie passe APRÈS `--end-of-options` (une ref `--output=<chemin>` ne devient jamais une option de git,
CWE-88). LE BOARD est lu par `etat_lecture.taches` seul ; illisible (y compris sous un interpréteur trop ancien
pour ses propriétaires) il est DIT, `board illisible (Python X.Y : <Exc>)`, rc 1, jamais un Traceback. Syntaxe
lisible par Python 3.9. Rien n'est écrit.

BORNES NOMMÉES. Le palier lit l'historique de HEAD, pas celui du clone ; il juge la forme, jamais l'existence ; la
recherche `gh` porte sur l'id tel que donné (une PR qui ne cite que le préfixe n'est pas vue par `gh`).

rc : 0 succès · 1 échec (git ou gh en échec, board illisible) · 2 usage (T-id refusé, base illisible).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, NamedTuple

RC_OK, RC_ECHEC, RC_USAGE = 0, 1, 2
RACINE_DEFAUT = Path(__file__).resolve().parents[2]
GIT_SUR = ("-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false")
DELAI_GIT_S = 120
DELAI_GH_S = 30
DETAIL_MAX = 200

# --- LA RÈGLE DU HOOK (.githooks/commit-msg), recopiée À L'IDENTIQUE -------------------------------------------
FENETRE_HOOK = 200
ELIGIBLES_MIN = 20
SEUIL_PCT = 95
DEBUT = b"\x01"
COUPE = b" ------------------------ >8 ------------------------"
PREFIXES_ETAT = (b"chore(state): ", b"chore(runs): ")
# `(^|[^A-Za-z0-9_-])…([^A-Za-z0-9]|$)` du hook, en regards : MÊME existence, et l'id s'extrait seul.
NUMERO = re.compile(rb"(?<![A-Za-z0-9_-])T-(?:[0-9]{3,15}|[0-9A-HJKMNP-TV-Z]{10,26})(?![A-Za-z0-9])")
SANS_TACHE = re.compile(rb"^Sans-tache:(?:[ \t]*[^ \t]){10}")
ID_DEMANDE = re.compile(r"T-(?:[0-9]{3,15}|[0-9A-HJKMNP-TV-Z]{10,26})", re.ASCII)
PREFIXE_MIN = 10
NUMERO_, SANS_TACHE_ = "numero", "sans-tache"


class Echec(Exception):
    """Échec dit : rc porté, message déjà formé (jamais un Traceback)."""

    def __init__(self, message: str, rc: int = RC_ECHEC) -> None:
        super().__init__(message)
        self.rc = rc


class Palier(NamedTuple):
    k: int
    n: int

    @property
    def verdict(self) -> str:
        if self.n < ELIGIBLES_MIN or self.k * 100 < self.n * SEUIL_PCT:
            return "avertissement"
        return "refus"


class Commit(NamedTuple):
    sha: str
    court: str
    parents: int
    lignes: list  # list[bytes] — les lignes de %B


# --------------------------------------------------------------------------- le prédicat unitaire
def lignes_lues(lignes: Iterable[bytes]) -> Iterable[bytes]:
    """Les lignes que le hook LIT : arrêt à la 1re qui finit par la ligne de coupe, lignes `#` sautées."""
    for ligne in lignes:
        if ligne.endswith(COUPE):
            return
        if ligne.startswith(b"#"):
            continue
        yield ligne


def porte(lignes: Iterable[bytes]) -> str | None:
    """LE prédicat d'acceptation du hook : `numero`, sinon `sans-tache`, sinon None."""
    sans = False
    for ligne in lignes_lues(lignes):
        if NUMERO.search(ligne):
            return NUMERO_
        if SANS_TACHE.search(ligne):
            sans = True
    return SANS_TACHE_ if sans else None


def eligible(lignes: list) -> bool:
    """Hors `chore(state): ` / `chore(runs): ` — jugé sur la 1re ligne du message, comme l'awk du hook."""
    return not (lignes and lignes[0].startswith(PREFIXES_ETAT))


def ids_cites(lignes: Iterable[bytes]) -> list[str]:
    vus: list[str] = []
    for ligne in lignes_lues(lignes):
        for m in NUMERO.finditer(ligne):
            tid = m.group(0).decode("ascii")
            if tid not in vus:
                vus.append(tid)
    return vus


def raison_sans_tache(lignes: Iterable[bytes]) -> str:
    for ligne in lignes_lues(lignes):
        if SANS_TACHE.search(ligne):
            return texte(ligne[len(b"Sans-tache:"):]).strip()
    return ""


# Sujets, raisons `Sans-tache:`, titres de PR et du board sont des DONNÉES : avant impression, tout caractère
# de contrôle (C0 hors tabulation et saut de ligne, DEL, C1) sort en `?` — jamais une séquence ESC au terminal.
CONTROLE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def imprimable(s: str) -> str:
    return CONTROLE.sub("?", s)


def texte(octets: bytes) -> str:
    return imprimable(octets.decode("utf-8", errors="replace"))


# --------------------------------------------------------------------------- git
def git(root: str, *argv: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git", "-C", root, *GIT_SUR, *argv], capture_output=True, timeout=DELAI_GIT_S,
                              stdin=subprocess.DEVNULL, check=False)
    except FileNotFoundError:
        raise Echec("git absent du PATH") from None
    except subprocess.TimeoutExpired:
        raise Echec(f"git n'a pas répondu en {DELAI_GIT_S} s") from None


def derniere_ligne(octets: bytes) -> str:
    lignes = [l for l in texte(octets).splitlines() if l.strip()]
    return lignes[-1][:DETAIL_MAX] if lignes else ""


def messages_du_flux(flux: bytes) -> list[list[bytes]]:
    """Le découpage de l'awk du hook : un message s'ouvre à chaque ligne qui commence par 0x01."""
    messages: list[list[bytes]] = []
    for ligne in flux.split(b"\n"):
        if ligne.startswith(DEBUT):
            messages.append([ligne[1:]])
        elif messages:
            messages[-1].append(ligne)
    return messages


def palier(root: str) -> Palier:
    """K/N par la commande et la règle du hook (sortie lue même en échec, comme son `2>/dev/null`)."""
    r = git(root, "-c", "log.showSignature=false", "log", "--no-merges", "-n", str(FENETRE_HOOK),
            "--format=%x01%B", "HEAD")
    retenus = [m for m in messages_du_flux(r.stdout) if eligible(m)]
    return Palier(k=sum(1 for m in retenus if porte(m) is not None), n=len(retenus))


def commits(root: str, options: list[str], refs: list[str], rc_echec: int = RC_ECHEC) -> list[Commit]:
    """Les commits (fusions comprises) : options de git, puis les refs APRÈS `--end-of-options` (CWE-88)."""
    r = git(root, "-c", "log.showSignature=false", "log", "-z", "--format=%H%x1f%h%x1f%P%x1f%B", *options,
            "--end-of-options", *refs)
    if r.returncode != 0:
        raise Echec(f"git log a échoué (rc {r.returncode}) : {derniere_ligne(r.stderr)}", rc_echec)
    sortie: list[Commit] = []
    for bloc in r.stdout.split(b"\x00"):
        if not bloc.strip():
            continue
        champs = bloc.lstrip(b"\n").split(b"\x1f", 3)
        if len(champs) != 4:
            continue
        sha, court, parents, corps = champs
        sortie.append(Commit(texte(sha), texte(court), len(parents.split()), corps.split(b"\n")))
    return sortie


def sujet(c: Commit) -> str:
    return texte(c.lignes[0]) if c.lignes else ""


# --------------------------------------------------------------------------- board
def lire_taches(root: str) -> list[dict[str, Any]]:
    """Les tâches par `etat_lecture.taches` ; toute défaillance devient une `Echec` qui la NOMME."""
    bin_dir = str(Path(__file__).resolve().parent)
    if bin_dir not in sys.path:
        sys.path.insert(0, bin_dir)
    version = f"{sys.version_info[0]}.{sys.version_info[1]}"
    try:
        import etat_lecture  # noqa: E402 — chargé à l'appel : un échec d'import est dit, pas levé
        return list(etat_lecture.taches(root))
    except Exception as exc:  # noqa: BLE001 — tout échec de lecture est NOMMÉ, jamais un Traceback
        detail = str(exc).splitlines()[0][:DETAIL_MAX] if str(exc) else ""
        raise Echec(f"board illisible (Python {version} : {type(exc).__name__}"
                    f"{' — ' + detail if detail else ''})") from None


def meme_tache(cite: str, tid: str) -> bool:
    """`cite` désigne `tid` : égalité, ou préfixe d'au moins 10 caractères après `T-`."""
    if cite == tid:
        return True
    return len(cite) - 2 >= PREFIXE_MIN and tid.startswith(cite)


def resoudre(cite: str, taches: list[dict[str, Any]]) -> str:
    trouvees = [t for t in taches if meme_tache(cite, str(t.get("id", "")))]
    if not trouvees:
        return f"- {cite} — inconnue au board"
    if len(trouvees) > 1:
        return f"- {cite} — ambiguë : " + ", ".join(str(t.get("id")) for t in trouvees)
    t = trouvees[0]
    titre = imprimable(" ".join(str(t.get("task", "")).split()))
    return f"- {t.get('id')} — {titre} ({t.get('state') or '—'})"


# --------------------------------------------------------------------------- verbes
RANG_DU_PREDICAT = {NUMERO_: "avec T-id", SANS_TACHE_: "Sans-tache", None: "ni l'un ni l'autre"}


def cmd_bilan(root: str, n: int, depuis: str | None) -> int:
    if depuis is not None:
        lus, fenetre = commits(root, [], [f"{depuis}..HEAD"], RC_USAGE), f"{depuis}..HEAD"
    else:
        lus, fenetre = commits(root, ["-n", str(n)], ["HEAD"]), f"HEAD, {n} derniers"
    rangs: dict[str, list[Commit]] = {"avec T-id": [], "Sans-tache": [], "fusions": [], "chore(state|runs)": [],
                                      "ni l'un ni l'autre": []}
    for c in lus:
        if c.parents > 1:
            rangs["fusions"].append(c)
        elif not eligible(c.lignes):
            rangs["chore(state|runs)"].append(c)
        else:
            rangs[RANG_DU_PREDICAT[porte(c.lignes)]].append(c)
    print(f"bilan : {len(lus)} commits lus ({fenetre}, fusions comprises)")
    for nom, liste in rangs.items():
        print(f"  {nom} : {len(liste)}")
    for c in rangs["ni l'un ni l'autre"]:
        print(f"    {c.court} {sujet(c)}")
    p = palier(root)
    print(f"palier: {p.verdict} ({p.k}/{p.n}, seuil {SEUIL_PCT} %) — règle de .githooks/commit-msg : "
          f"{FENETRE_HOOK} derniers commits hors fusion de HEAD, hors chore(state|runs)")
    return RC_OK


def cmd_tache(root: str, tid: str, avec_pr: bool) -> int:
    if not ID_DEMANDE.fullmatch(tid):
        print("tache : T-id refusé (forme : T- puis 3 à 15 chiffres, ou 10 à 26 caractères d'un ULID)",
              file=sys.stderr)
        return RC_USAGE
    cites = [c for c in commits(root, ["--all"], []) if any(meme_tache(x, tid) or meme_tache(tid, x)
                                                           for x in ids_cites(c.lignes))]
    print(f"tâche {tid} : {len(cites)} commit(s) qui la citent (toutes branches)")
    for c in cites:
        print(f"  {c.court} {sujet(c)}")
    return cmd_pr(root, tid) if avec_pr else RC_OK


def cmd_pr(root: str, tid: str) -> int:
    env = dict(os.environ)
    gh = shutil.which("gh", path=env.get("PATH", ""))
    if gh is None:
        print("pr : gh absent — lien non vérifié")
        return RC_OK
    env.update(GH_PROMPT_DISABLED="1", GH_NO_UPDATE_NOTIFIER="1")
    argv = [gh, "pr", "list", "--state", "all", "--search", tid, "--json", "number,title,url,state",
            "--limit", "50"]
    try:
        r = subprocess.run(argv, capture_output=True, stdin=subprocess.DEVNULL, timeout=DELAI_GH_S, cwd=root,
                           env=env, check=False)
    except FileNotFoundError:
        print("pr : gh absent — lien non vérifié")
        return RC_OK
    except subprocess.TimeoutExpired:
        print(f"pr : gh n'a pas répondu en {DELAI_GH_S} s")
        return RC_ECHEC
    if r.returncode != 0:
        print(f"pr : gh a échoué (rc {r.returncode}) : {derniere_ligne(r.stderr) or derniere_ligne(r.stdout)}")
        return RC_ECHEC
    try:
        prs = json.loads(r.stdout.decode("utf-8", errors="replace"))
        lignes = [imprimable(f"pr : #{p['number']} {p['state']} {p['title']} — {p['url']}") for p in prs]
    except (ValueError, TypeError, KeyError):
        print("pr : réponse de gh illisible")
        return RC_ECHEC
    print("\n".join(lignes) if lignes else f"pr : aucune PR ne cite {tid}")
    return RC_OK


def cmd_pr_corps(root: str, base: str) -> int:
    lus = list(reversed(commits(root, [], [f"{base}..HEAD"], RC_USAGE)))
    ids: list[str] = []
    sans: list[Commit] = []
    for c in lus:
        for x in ids_cites(c.lignes):
            if x not in ids:
                ids.append(x)
        if porte(c.lignes) == SANS_TACHE_:
            sans.append(c)
    taches = lire_taches(root) if ids else []
    sortie = ["## Tâches", ""] + ([resoudre(x, taches) for x in ids] or ["(aucune tâche citée)"])
    if sans:
        sortie += ["", "## Sans tâche", ""] + [f"- {c.court} {sujet(c)} — {raison_sans_tache(c.lignes)}"
                                               for c in sans]
    print("\n".join(sortie))
    return RC_OK


# --------------------------------------------------------------------------- entrée
def _positif(brut: str) -> int:
    try:
        v = int(brut)
    except ValueError:
        raise argparse.ArgumentTypeError("entier attendu") from None
    if v < 1:
        raise argparse.ArgumentTypeError("au moins 1")
    return v


def _parseur() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tracabilite.py", allow_abbrev=False,
                                description="Links task, commits and PR; tells the tier of the task number "
                                            "(old French names bilan, tache, pr-corps, --depuis still accepted).")
    p.add_argument("--root", default=None, help="repository root (default: this script's)")
    sous = p.add_subparsers(dest="verbe", required=True)
    # Un alias pose `verbe` = nom TAPE : `set_defaults` le ramene a l'ancien nom, que `main` repartit.
    b = sous.add_parser("summary", aliases=["bilan"], allow_abbrev=False,
                        help="commit counts and hook tier")
    b.set_defaults(verbe="bilan")
    fen = b.add_mutually_exclusive_group()
    fen.add_argument("-n", type=_positif, default=FENETRE_HOOK, help=f"last N commits (default {FENETRE_HOOK})")
    fen.add_argument("--since", "--depuis", dest="depuis", metavar="REF", help="the commits of REF..HEAD")
    t = sous.add_parser("task", aliases=["tache"], allow_abbrev=False,
                        help="commits (and PRs) citing a task")
    t.set_defaults(verbe="tache")
    t.add_argument("tid", metavar="T-ID")
    t.add_argument("--pr", action="store_true", help="read the PRs through gh")
    c = sous.add_parser("pr-body", aliases=["pr-corps"], allow_abbrev=False,
                        help="PR body: tasks of BASE..HEAD")
    c.set_defaults(verbe="pr-corps")
    c.add_argument("--base", required=True, metavar="REF")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parseur().parse_args(argv)
    root = str(args.root) if args.root else str(RACINE_DEFAUT)
    try:
        if args.verbe == "bilan":
            return cmd_bilan(root, args.n, args.depuis)
        if args.verbe == "tache":
            return cmd_tache(root, args.tid, args.pr)
        return cmd_pr_corps(root, args.base)
    except Echec as exc:
        print(f"{args.verbe} : {exc}", file=sys.stderr)
        return exc.rc


if __name__ == "__main__":
    sys.exit(main())
