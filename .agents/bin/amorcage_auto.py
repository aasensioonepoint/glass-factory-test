#!/usr/bin/env python3
"""amorcage_auto.py — l'amorçage d'un adoptant LANCÉ par les hooks SessionStart (T-00001103, lot C).

Décision pilote S-01M5WBHK9H374YBEMAY51ES754 : le hook LANCE l'amorçage (identité, stores, index,
sync-spec : `setup_projet.py`) au lieu de l'annoncer — DÉTACHÉ, sous le budget du SessionStart,
échec non bloquant et DIT. Ce module rend UNE ligne de statut (`[PROJECT STATUS] amorçage …`) ou
rien ; c'est une donnée de statut, jamais un ordre à l'agent (L-004).

LA RÈGLE porte sur le `rc` d'`.agents/state/local/amorcage.json`, écrit par le run lui-même :
  - rc 0 -> rien (l'amorçage a abouti une fois sur ce clone), sauf si le run détaché a laissé des
    lignes `secrets: proposé` dans amorcage.log : leur nombre (`secrets`) est dit à chaque session
    (un `--rejouer` les montre au terminal, il ne les compte pas) ;
  - rc ≠ 0 -> `échec rc=N` à CHAQUE session, jamais de relance ; seul `--rejouer` réécrit rc
    (un `setup_projet.py` manuel ne l'efface pas : dit dans la ligne) ;
  - rc absent et verrou libre (run tué) -> relance ; verrou tenu -> `en cours` ;
  - pas d'amorcage.json -> lancé ; écart C8 ACCEPTÉ (décision S-01M5X0C4PQ) : l'amorçage se
    relance UNE fois si project.json existe sans amorcage.json (un adoptant qui a joué
    `project_init.py` à la main avant sa 1re session a project.json sans index ni sync-spec ; un
    setup rejoué sur un adoptant amorcé est idempotent, mesuré rc 0, « 7 déjà là »). Coût : UN
    setup détaché par clone qui n'a jamais eu d'amorcage.json.

LE VERROU : `flock(LOCK_EX|LOCK_NB)` sur `amorcage.lock`, descripteur transmis (`pass_fds`) à
l'exécuteur DÉTACHÉ (`start_new_session`, stdin DEVNULL, sorties -> `amorcage.log`) ; le noyau le
libère à la mort de l'exécuteur. `setup_projet.py` ne le reçoit PAS (close_fds) : un petit-enfant
détaché qu'il laisserait ne tient pas le verrou après la fin du run (mesuré, critic-3 C4).

L'INTERPRÉTEUR (réserve C9, décision S-01M5X0C4CK) : setup ne tourne JAMAIS sous celui du hook
(3.9.6 sur un macOS nu : setup y finit rc 0 mais DÉGRADÉ — specs_graph exige 3.11, mesuré à la
revue de clôture de T-00001103 ; un rc 0 y éteindrait la ligne sur un amorçage incomplet). On
sonde dans l'ordre python3.14, python3.13, python3.12, python3.11, python3, python
(`sys.version_info >= (3, 11)`, en liste d'arguments, sans shell — motif de core-scripts/setup.sh)
et setup tourne sous le PREMIER admis, nommé dans la ligne `lancé` et dans amorcage.json. Aucun
admis : setup n'est pas lancé, rc 127 écrit avec sa cause, et la ligne dit d'installer
Python ≥ 3.11 puis `--rejouer`. Une sonde qui dépasse le délai (DELAI_SONDE, au total) n'est pas
une absence : sans autre admis, la ligne dit `trop lent à répondre`, AUCUN rc n'est écrit et la
session suivante resonde (`--rejouer` : rc 124, rc du fichier inchangé).

NON LANCÉ, cause dite : `CADRE_AMORCAGE=0`, `CI` posé, racine hors dépôt git (`.git` absent :
`git init` d'abord, jamais un échec écrit), `.git` fichier hors worktree (sous-module), pas de
`fcntl` (Windows), `setup_projet.py` absent, toute exception. Mais si project.json existe déjà,
une cause de non-lancement rend le SILENCE, `CADRE_AMORCAGE=0` compris : c'est la sortie choisie
par l'adoptant, jamais une ligne perpétuelle (décision du mandat de clôture T-00001103 D1).
SILENCE aussi (aucun adoptant concerné) : dépôt du kit (`.agents/IS_THE_KIT`), worktree lié
(`.git` fichier qui pointe sous `/worktrees/` : le clone principal amorce), état hors de la racine
(bancs qui repointent STATE).

BORNES : la fenêtre d'écriture du run (quelques secondes) n'est pas verrouillée contre un setup
manuel ou l'agent ; un run tué à chaque fois est relancé une fois par session ; Windows : non lancé.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

try:
    import fcntl
except ImportError:  # Windows : pas de flock, amorçage non lancé (dit)
    fcntl = None  # type: ignore[assignment]

PREFIXE = "[PROJECT STATUS] amorçage"
JOURNAL = ".agents/state/local/amorcage.log"
REMEDE = "python3 .agents/bin/amorcage_auto.py --rejouer"
CANDIDATS = ("python3.14", "python3.13", "python3.12", "python3.11", "python3", "python")
SONDE = "import sys; print('.'.join(map(str, sys.version_info[:3]))); sys.exit(sys.version_info < (3, 11))"
RC_SANS_PYTHON = 127
CAUSE_SANS_PYTHON = "python ≥ 3.11 absent du PATH"
REMEDE_PYTHON = f"installer Python ≥ 3.11 puis {REMEDE}"
DELAI_SONDE = 3.0
RC_SONDE_LENTE = 124
CAUSE_SONDE_LENTE = f"python ≥ 3.11 trop lent à répondre (sonde > {DELAI_SONDE:g}s)"
MARQUE_SECRET = "secrets: proposé"
# Un lien symbolique posé à la place d'un fichier d'état n'est jamais suivi (ELOOP -> non lancé).
NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


def _local(root: Path) -> Path:
    return root / ".agents" / "state" / "local"


def _lire(local: Path) -> dict | None:
    try:
        rec = json.loads((local / "amorcage.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return rec if isinstance(rec, dict) else None


def _ouvrir_ecriture(chemin: Path):
    fd = os.open(str(chemin), os.O_WRONLY | os.O_CREAT | os.O_TRUNC | NOFOLLOW, 0o600)
    return os.fdopen(fd, "w", encoding="utf-8")


def _ecrire(local: Path, rec: dict) -> None:
    cible = local / "amorcage.json"
    tmp = local / f"amorcage.json.{os.getpid()}.tmp"
    with _ouvrir_ecriture(tmp) as f:
        f.write(json.dumps(rec, ensure_ascii=False))
    os.replace(tmp, cible)


def _python_admis() -> tuple[tuple[str, str] | None, bool]:
    """((chemin, version) du premier candidat ≥ 3.11 du PATH ou None, lent). Liste d'arguments, sans
    shell ; DELAI_SONDE au total, sous le `timeout 5` du hook Claude (un candidat qui pend n'emporte
    pas la ligne). `lent` : un candidat présent a dépassé le délai, ou n'a pas pu être sondé faute
    de temps — ce n'est pas une absence."""
    fin = time.monotonic() + DELAI_SONDE
    lent = False
    for nom in CANDIDATS:
        chemin = shutil.which(nom)
        if not chemin:
            continue
        reste = fin - time.monotonic()
        if reste <= 0:
            lent = True
            continue
        try:
            sonde = subprocess.run([chemin, "-c", SONDE], stdin=subprocess.DEVNULL, capture_output=True,
                                   text=True, timeout=reste, check=False)
        except subprocess.TimeoutExpired:
            lent = True
            continue
        except (OSError, subprocess.SubprocessError):
            continue
        if sonde.returncode == 0:
            return (chemin, sonde.stdout.strip()), False
    return None, lent


def _secrets_proposes(local: Path) -> int:
    """Nombre de lignes `secrets: proposé` du journal (0 s'il est illisible)."""
    try:
        lignes = (local / "amorcage.log").read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return 0
    return sum(1 for x in lignes if x.startswith(MARQUE_SECRET))


def _propre(valeur: object, borne: int = 120) -> str:
    """Texte d'amorcage.json avant injection au contexte : caractères de contrôle retirés, borné."""
    return "".join(c for c in str(valeur) if c.isprintable())[:borne]


def _echec(rec: dict) -> str:
    rc = rec.get("rc")
    rc = rc if isinstance(rc, int) and not isinstance(rc, bool) else "?"
    if rec.get("cause"):
        return (f"{PREFIXE} : échec rc={rc} ({_propre(rec['cause'])}) — setup_projet.py non lancé ; "
                f"{REMEDE_PYTHON}")
    return (f"{PREFIXE} : échec rc={rc} (setup_projet.py sous "
            f"{_propre(rec.get('interpreteur', '?'))}) — journal {JOURNAL} ; seul remède qui efface "
            f"cette ligne : {REMEDE} (un setup_projet.py manuel ne la lève pas)")


def _fait(rec: dict) -> str | None:
    """rc 0 : rien, sauf des secrets proposés par le run détaché, comptés dans `secrets`."""
    n = rec.get("secrets")
    if not isinstance(n, int) or isinstance(n, bool) or n <= 0:
        return None
    return (f"{PREFIXE} : fait — {n} fichier(s) au nom de secret sans refus Read(…) : lignes "
            f"« {MARQUE_SECRET} » dans {JOURNAL}, à poser dans .claude/settings.local.json")


def _worktree_lie(root: Path) -> bool:
    """`.git` FICHIER qui pointe sous `<dépôt>/.git/worktrees/` : un worktree lié, pas un sous-module."""
    try:
        txt = (root / ".git").read_text(encoding="utf-8", errors="replace")[:4096]
    except OSError:
        return False
    return "/worktrees/" in txt.replace("\\", "/")


def _cause_non_lancee(root: Path) -> str | None:
    if (os.environ.get("CADRE_AMORCAGE") or "").strip() == "0":
        return "CADRE_AMORCAGE=0"
    if (os.environ.get("CI") or "").strip():
        return "CI posé"
    if not (root / ".git").exists():
        return "hors dépôt git — git init d'abord"
    if (root / ".git").is_file():
        return ".git est un fichier (sous-module)"
    if fcntl is None:
        return "pas de fcntl sur ce poste (Windows)"
    if not (root / ".agents" / "bin" / "setup_projet.py").is_file():
        return ".agents/bin/setup_projet.py absent"
    return None


def amorcer(root: str, state: str) -> str | None:
    """La ligne de statut de CETTE session, ou None. Ne lève jamais : toute exception -> non lancé."""
    try:
        racine = Path(root).resolve()
        if Path(state).resolve() != racine / ".agents" / "state":
            return None
        if (racine / ".agents" / "IS_THE_KIT").exists():
            return None
        if (racine / ".git").is_file() and _worktree_lie(racine):
            return None
        local = _local(racine)
        rec0 = _lire(local)
        if rec0 is not None and rec0.get("rc") == 0:
            return _fait(rec0)
        cause = _cause_non_lancee(racine)
        if cause:
            if (racine / ".agents" / "state" / "project.json").exists():
                return None
            return f"{PREFIXE} non lancé : {cause} — à la main : python3 .agents/bin/setup_projet.py"
        local.mkdir(parents=True, exist_ok=True)
        return _sous_verrou(racine, local)
    except Exception as exc:  # fail-open : le hook ne perd jamais son contexte
        return f"{PREFIXE} non lancé : {_propre(f'{type(exc).__name__}: {exc}', 200)}"


def _sous_verrou(racine: Path, local: Path) -> str | None:
    fd = os.open(str(local / "amorcage.lock"), os.O_RDWR | os.O_CREAT | NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return f"{PREFIXE} en cours (setup_projet.py détaché) — journal {JOURNAL}"
        rec = _lire(local)
        if rec is not None and rec.get("rc") == 0:
            return _fait(rec)
        if rec is not None and rec.get("rc") is not None:
            return _echec(rec)
        admis, lent = _python_admis()
        if admis is None and lent:
            return f"{PREFIXE} non lancé : {CAUSE_SONDE_LENTE} — resondé à la session suivante, ou {REMEDE}"
        if admis is None:
            rec = {"pid": None, "debut": time.time(), "fin": time.time(), "rc": RC_SANS_PYTHON,
                   "cause": CAUSE_SANS_PYTHON}
            _ecrire(local, rec)
            return _echec(rec)
        rec = {"pid": None, "debut": time.time(), "rc": None, "interpreteur": " ".join(admis)}
        _ecrire(local, rec)
        with _ouvrir_ecriture(local / "amorcage.log") as journal:
            proc = subprocess.Popen(
                [sys.executable, str(Path(__file__).resolve()), "--executer", "--root", str(racine),
                 "--python", admis[0]],
                pass_fds=(fd,), start_new_session=True, stdin=subprocess.DEVNULL,
                stdout=journal, stderr=subprocess.STDOUT, cwd=str(racine))
        rec["pid"] = proc.pid
        _ecrire(local, rec)
        return (f"{PREFIXE} lancé en arrière-plan (setup_projet.py sous {rec['interpreteur']}) — "
                f"journal {JOURNAL}")
    finally:
        os.close(fd)


def executer(root: str, premier_plan: bool = False, python: str | None = None) -> int:
    """Joue setup_projet.py sous un python ≥ 3.11 et écrit son rc. Appelé sous le verrou (détaché,
    avec l'interpréteur sondé par le hook, ou par --rejouer, qui sonde lui-même)."""
    racine = Path(root).resolve()
    local = _local(racine)
    rec = _lire(local) or {}
    if premier_plan:
        rec.update(pid=os.getpid(), debut=time.time())
    admis, lent = ((python, rec.get("interpreteur") or python), False) if python else _python_admis()
    if admis is None and lent:
        print(f"amorçage : setup_projet.py non lancé — {CAUSE_SONDE_LENTE} ; rejoue {REMEDE}", flush=True)
        return RC_SONDE_LENTE
    if admis is None:
        rec.update(rc=RC_SANS_PYTHON, cause=CAUSE_SANS_PYTHON, fin=time.time())
        rec.pop("interpreteur", None)
        _ecrire(local, rec)
        print(f"amorçage : setup_projet.py non lancé — {CAUSE_SANS_PYTHON} ; {REMEDE_PYTHON}", flush=True)
        return RC_SANS_PYTHON
    chemin = admis[0]
    rec.pop("cause", None)
    rec.update(rc=None, interpreteur=admis[1] if python else " ".join(admis))
    _ecrire(local, rec)
    print(f"amorçage : setup_projet.py sous {rec['interpreteur']}", flush=True)
    kw = {} if premier_plan else {"stdin": subprocess.DEVNULL}
    try:
        rc = subprocess.run(
            [chemin, str(racine / ".agents" / "bin" / "setup_projet.py"), "--root", str(racine)],
            cwd=str(racine), check=False, **kw).returncode
    except OSError as exc:
        print(f"amorçage : setup_projet.py non lancé — {exc}", flush=True)
        rc = 125
    rec = _lire(local) or rec
    rec["rc"] = rc
    rec["fin"] = time.time()
    # Détaché, la sortie de setup est le journal : ses `secrets: proposé` y sont comptés. Au premier
    # plan (--rejouer), ils passent au terminal et le journal est celui d'un run ancien.
    rec["secrets"] = 0 if premier_plan else _secrets_proposes(local)
    _ecrire(local, rec)
    print(f"amorçage : fin rc={rc}", flush=True)
    return rc


def rejouer(root: str) -> int:
    """Seul remède qui réécrit rc : même verrou (tenu -> `en cours`, rc 3), setup au premier plan."""
    if fcntl is None:
        print("amorçage : pas de fcntl sur ce poste (Windows) — joue setup_projet.py à la main")
        return 2
    local = _local(Path(root).resolve())
    local.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(local / "amorcage.lock"), os.O_RDWR | os.O_CREAT | NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(f"amorçage en cours — journal {JOURNAL}")
            return 3
        return executer(root, premier_plan=True)
    finally:
        os.close(fd)


def main(argv: list[str] | None = None) -> int:
    a = argparse.ArgumentParser(prog="amorcage_auto.py", description=__doc__.splitlines()[0])
    a.add_argument("--root", default=os.getcwd(), help="racine du projet (défaut : le répertoire courant)")
    a.add_argument("--rejouer", action="store_true", help="rejouer setup_projet.py au premier plan, rc réécrit")
    a.add_argument("--executer", action="store_true", help=argparse.SUPPRESS)
    a.add_argument("--python", default=None, help=argparse.SUPPRESS)
    args = a.parse_args(argv)
    if args.executer:
        return executer(args.root, python=args.python)
    if args.rejouer:
        return rejouer(args.root)
    ligne = amorcer(args.root, str(Path(args.root) / ".agents" / "state"))
    if ligne:
        print(ligne)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
