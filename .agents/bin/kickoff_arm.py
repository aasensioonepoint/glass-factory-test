#!/usr/bin/env python3
"""kickoff_arm.py — ARMER ET DESARMER LE MANDAT D'ECRITURE, EN LAISSANT UNE TRACE.

CE QUE LA GARDE FAIT — ET CE QU'ELLE NE FAIT PAS
------------------------------------------------
La premiere redaction de cette docstring disait que la presence du marqueur
« fait refuser toute ecriture hors du write-set declare ». **C'est l'inverse de
la regle**, et la revue de cloture l'a MESURE : garde armee sur ``T-012``, six
chemins hors de son write-set — ``.gitignore``, ``CHANGELOG.md``,
``README-CLAUDE.md``, ``QUICK-SETUP.md``, ``CADRE/index.html``,
``README-OTHER-HOSTS.md`` — sont passes avec ``rc=0`` et zero octet.

LA REGLE EXACTE, telle que ``kickoff_guard.py`` la porte : le marqueur soumet
toute ecriture **DANS** le write-set d'une tache armee a trois conditions —
tache ``running``, instantane ``kind=plan`` dans ``SPECS.json``, chemin couvert.
Une ecriture **HORS** de tout write-set arme **passe en silence**. Cette garde
CONDITIONNE un perimetre declare ; elle ne cloture PAS le depot.

La confondre coute cher dans les deux sens : on se croit protege ou l'on ne
l'est pas, et l'on s'etonne d'un refus la ou l'on avait justement declare
travailler.

POURQUOI CE SCRIPT EXISTE
-------------------------
Le fichier est refuse aux agents par DEUX couches — le blocage dedie de
``protect-paths.sh`` et une ligne ``permissions.deny`` — et la raison est ecrite
dans le hook : **un agent qui peut s'armer peut aussi se desarmer**, donc le
mandat cesserait d'etre un mandat.

Le pilote a demande le 2026-09-12 que l'orchestrateur puisse lancer ``/kickoff``
sans son geste manuel. Lever les deux couches aurait rendu la garde decorative.
Ce script est la troisieme voie : **le fichier brut reste refuse en edition
directe**, et l'armement passe par UN geste nomme qui ECRIT AU REGISTRE avant
d'agir. On ne retire pas la garde, on rend son franchissement visible.

CE QUE CA CHANGE, DIT PLUTOT QUE MASQUE. Un agent peut desormais se desarmer,
et ``--disarm`` existe precisement pour que ce soit un geste explicite plutot
qu'un contournement. Ce qui reste vrai, et qui est tout l'interet : il ne peut
plus le faire EN SILENCE. Chaque armement et chaque desarmement laisse une
entree datee au registre institutionnel, que le pilote relit. L'invariant
« rien n'est supprime sans trace » couvre maintenant aussi l'armement.

LE TROU QUE CE SCRIPT EMPRUNTE, NOMME. Il ecrit par Python, donc il passe a cote
des gardes de chemin, qui ne couvrent que ``Edit``/``Write`` — c'est le trou
que ``T-00000244`` porte deja. La difference avec un contournement est qu'il y a
ici UN SEUL site, nomme, teste, et qui trace. Si ce trou se ferme un jour, ce
script devra etre re-autorise explicitement.

USAGE
-----
    python3 .agents/bin/kickoff_arm.py --status
    python3 .agents/bin/kickoff_arm.py --arm T-012 [T-013 ...] [--raison "..."]
    python3 .agents/bin/kickoff_arm.py --disarm --raison "..."

``--arm`` REMPLACE la liste : c'est un mandat, pas un cumul. Une tache qui n'est
plus nommee n'est plus armee, et l'entree de registre le dit.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

GATE_RELPATH = Path(".agents") / "state" / "gates" / "KICKOFF_REQUIRED"
LEDGER_RELPATH = Path(".agents") / "bin" / "ledger.py"
# `T-<ULID>` (T-00000726, ULID EN PREMIER) ou l'ancien `T-NNN` (3 chiffres au
# moins), ancré aux DEUX bouts (`\Z` : un `\n` final est refusé). RECOPIÉ, jamais
# importé ; témoins : `IdGrammaireTests` de test_kickoff_arm.py (T-00001040).
ID_RE = re.compile(r"\AT-(?:[0-9A-HJKMNP-TV-Z]{26}|[0-9]{3,})\Z")

EN_TETE = (
    "# Mandat d'ecriture — kickoff_guard (T-00000243).\n"
    "# ECRIT PAR .agents/bin/kickoff_arm.py, jamais a la main par un agent :\n"
    "# le fichier reste refuse en edition directe par protect-paths.sh et par\n"
    "# permissions.deny. Chaque geste est trace au registre institutionnel.\n"
    "# Un id de tache par ligne ; l'ABSENCE du fichier est le regime de reference.\n"
)


def repo_root() -> Path:
    """Racine git. Meme semantique que partout ailleurs dans le kit."""
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        sys.exit("kickoff_arm: pas dans un depot git")
    return Path(out.stdout.strip())


def lire(gate: Path) -> list[str]:
    if not gate.exists():
        return []
    ids = []
    for brute in gate.read_text(encoding="utf-8").splitlines():
        ligne = brute.split("#", 1)[0].strip()
        if ligne:
            ids.append(ligne)
    return ids


def _ecrire_atomiquement(cible: Path, contenu: str) -> None:
    """Ecriture TOUT-OU-RIEN du marqueur de porte, et ce n'est pas cosmetique.

    LE DEFAUT CORRIGE EST UN FAIL-OPEN, sur le mecanisme meme qui existe pour
    REFUSER. `kickoff_guard` traite une porte « absente, vide, ou n ouvrant
    aucune tache » comme un laissez-passer SILENCIEUX — c'est le bon regime, le
    kit etant livre desarme. Mais l'ecriture etait un `write_text` nu : une
    interruption entre la troncature et la fin de l'ecriture laissait le fichier
    avec son EN-TETE et AUCUN identifiant, donc une porte qui n ouvre aucune
    tache, donc TOUTES les ecritures du depot autorisees sans un mot. Un
    armement a demi ecrit se lisait exactement comme un desarmement voulu.

    Constat 4a de la revue de cloture 0bis (T-00000564), et le meme geste que
    `cadre.workspace.write_bytes` : temporaire a nom unique dans le repertoire
    cible, `fsync`, puis `os.replace`. Le temporaire est dans le MEME repertoire
    parce que `os.replace` n'est atomique qu'a l'interieur d'un systeme de
    fichiers.
    """
    fd, brut = tempfile.mkstemp(dir=str(cible.parent),
                                prefix=cible.name + ".", suffix=".tmp")
    tmp = Path(brut)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(contenu)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, cible)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def tracer(root: Path, titre: str, texte: str) -> bool:
    """Ecrit au registre AVANT d'agir. Retourne False si la trace a echoue —
    et l'appelant REFUSE alors d'agir : un armement non trace est exactement ce
    que ce script existe pour empecher."""
    ledger = root / LEDGER_RELPATH
    if not ledger.exists():
        print(f"kickoff_arm: {LEDGER_RELPATH} introuvable — trace impossible", file=sys.stderr)
        return False
    out = subprocess.run(
        [sys.executable, str(ledger), "add", "--category", "decision",
         "--title", titre, "--text", texte],
        capture_output=True, text=True, check=False,
    )
    if out.returncode != 0:
        print(f"kickoff_arm: le registre a refuse la trace : {out.stderr.strip()}", file=sys.stderr)
        return False
    print(out.stdout.strip())
    return True


def main() -> int:
    p = argparse.ArgumentParser(
        description="kickoff_arm.py - arm and disarm the write mandate, leaving a trace.")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--status", action="store_true", help="report the state, write nothing")
    g.add_argument("--arm", nargs="+", metavar="T-NNN", help="arm these tasks, REPLACING the list")
    g.add_argument("--disarm", action="store_true", help="delete the file: back to the reference regime")
    # T-01M5QC86XN : nom anglais en tete, ancien nom garde en alias, `dest` ancien explicite.
    p.add_argument("--reason", "--raison", dest="raison", default="", metavar="REASON",
                   help="motive, copied verbatim into the trace (alias: --raison)")
    args = p.parse_args()

    root = repo_root()
    gate = root / GATE_RELPATH
    actuels = lire(gate)

    if args.status:
        if not gate.exists():
            print("kickoff_guard : DESARME (le fichier n'existe pas — regime de reference)")
        elif not actuels:
            print("kickoff_guard : fichier PRESENT mais VIDE — aucune tache armee")
        else:
            print(f"kickoff_guard : ARME sur {len(actuels)} tache(s) : {', '.join(actuels)}")
        return 0

    if args.arm:
        mauvais = [t for t in args.arm if not ID_RE.match(t)]
        if mauvais:
            print(f"kickoff_arm: identifiants mal formes (attendu T-NNN ou T-<ULID>) : {mauvais}", file=sys.stderr)
            return 2
        if sorted(actuels) == sorted(args.arm):
            print(f"kickoff_guard : deja arme exactement sur {', '.join(args.arm)} — rien ecrit")
            return 0
        titre = f"Mandat d ecriture ARME sur {', '.join(args.arm)}"
        texte = (
            f"kickoff_arm.py --arm le {date.today().isoformat()}. Avant : "
            f"{', '.join(actuels) if actuels else 'DESARME'}. Apres : {', '.join(args.arm)}. "
            f"Raison : {args.raison or 'non precisee'}. "
            "Le fichier brut reste refuse en edition directe ; ce script est le seul "
            "site autorise, et il trace avant d agir."
        )
        if not tracer(root, titre, texte):
            print("kickoff_arm: REFUS — pas de trace, donc pas d armement", file=sys.stderr)
            return 3
        gate.parent.mkdir(parents=True, exist_ok=True)
        _ecrire_atomiquement(gate, EN_TETE + "\n".join(args.arm) + "\n")
        print(f"kickoff_guard : ARME sur {', '.join(args.arm)}")
        return 0

    # --disarm
    if not gate.exists():
        print("kickoff_guard : deja desarme — rien ecrit")
        return 0
    titre = "Mandat d ecriture DESARME"
    texte = (
        f"kickoff_arm.py --disarm le {date.today().isoformat()}. Etait arme sur : "
        f"{', '.join(actuels) if actuels else 'aucune tache'}. "
        f"Raison : {args.raison or 'non precisee'}. "
        "Un desarmement par un agent est VISIBLE par construction : c est tout l objet "
        "de ce script, puisque la garde ne peut plus etre levee en silence."
    )
    if not tracer(root, titre, texte):
        print("kickoff_arm: REFUS — pas de trace, donc pas de desarmement", file=sys.stderr)
        return 3
    # `missing_ok=True` — constat 4b de la meme revue : le `gate.exists()` plus
    # haut et cette suppression sont deux instants, donc deux desarmements
    # concurrents faisaient lever un `FileNotFoundError` non rattrape au second.
    # L'etat vise est « le fichier n existe pas » ; il est atteint dans les deux
    # cas, donc le second n a rien a signaler.
    gate.unlink(missing_ok=True)
    print("kickoff_guard : DESARME (fichier supprime — regime de reference)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
