#!/usr/bin/env python3
"""HOOKS JUMEAUX — les hooks Python gemini sont la copie A L'OCTET de la source codex (T-01M4V7R5H0HE0Z5TPJ4Q64VMPF, lot G).

Décision pilote S-01M4V83NB2EQ500YHQEX0NXZ4H ; plan `docs/tasks/T-01M4V7R5H0HE0Z5TPJ4Q64VMPF-plan.md`, étape 6.

Usage : `python3 .agents/bin/hooks_jumeaux.py [--check | --ecrire] [--racine R]`

Source `.codex/hooks`, cible `.gemini/hooks` : un tuple FERMÉ (`JUMEAUX`), qu'aucune option ne change. Fichiers jugés :
les `*.py` de chaque dossier, listage NON récursif, hors `test_*.py` (chaque hôte garde ses propres bancs). Tout autre
nom (`fixtures/`, `__pycache__/`, un `.tmp`) est ignoré.

`--check` (par défaut) : lecture seule. Compare chaque paire à l'octet (jamais la seule taille) et imprime sur stdout,
triée par nom, une ligne par écart :
  `absent: <nom>`     présent à la source, absent de la cible ;
  `different: <nom>`  présent des deux côtés, octets différents ;
  `orphelin: <nom>`   présent à la cible seulement — jamais supprimé : à retirer à la main, ou à créer à la source.
`--ecrire` : le MÊME constat d'abord, en entier, sans l'imprimer ; puis il réécrit les seuls `absent` et `different`,
chacun par un temporaire du dossier cible au nom hors `*.py` (`.hooks_jumeaux-*.tmp`), au mode du fichier source, puis
`os.replace` (reprise bornée sur `PermissionError` : un lecteur concurrent sous Windows). Il imprime `ecrit: <nom>`
pour chacun, puis le constat d'après, le seul imprimé : un `absent` ou `different` réécrit n'y paraît que par sa ligne
`ecrit:`. Un fichier déjà identique n'est pas touché. Il ne SUPPRIME jamais et ne crée aucun dossier.

Codes de sortie :
  0  les deux arbres concordent (après écriture, sous `--ecrire`) ;
  1  écart(s) listés sur stdout ; sous `--ecrire`, seuls des `orphelin` peuvent rester ;
  2  refus, sur stderr : source absente ou VIDE (aucun `*.py` hors `test_*.py`) ; erreur d'E/S (lecture, écriture,
     dossier cible absent sous `--ecrire`) ; entrée `*.py` qui n'est pas un fichier régulier ; LIEN SYMBOLIQUE sur un
     maillon entre `--racine` (exclue) et un fichier jugé, source ou cible (dossier d'hôte, dossier `hooks`, fichier) ;
     realpath d'un de ces maillons hors du realpath de `--racine`. Tout le constat précède toute écriture : un refus
     du constat n'écrit rien. Une erreur d'E/S PENDANT l'écriture laisse remplacés les fichiers déjà remplacés —
     chaque fichier est atomique, le lot ne l'est pas ; relancer `--ecrire` reprend où il s'est arrêté.
  Un usage invalide (`--check` avec `--ecrire`, option inconnue) sort aussi en 2, par argparse.

`--racine` par défaut : la racine de l'arbre qui porte CE fichier (deux niveaux au-dessus de `.agents/bin/`), jamais
`CLAUDE_PROJECT_DIR` ni le dossier courant — depuis un worktree, `CLAUDE_PROJECT_DIR` vise le checkout principal.

RÉSIDUS NOMMÉS :
  * `--ecrire` écrit dans `.gemini/hooks/`, un chemin de garde, HORS Edit/Write : la garde de chemins ne voit pas ces
    écritures. Borne : copies seules, aucun lien suivi, realpath vérifié, aucune suppression, `--check` par défaut.
    L'inscription de ce fichier à `CHEMINS_GARDE` est la suite S5 du plan.
  * Ce fichier VOYAGE (réserve K5 de plan-critic it.2, S-01M4VBNT6EXAMN9M8W3HYNCEN4) : `.template-exclude` ne retire
    pas `.agents/bin/`. Chez un adoptant, rien ne l'appelle d'office ; un adoptant qui a retouché ses hooks gemini à la
    main lit rc 1 et choisit le sens — `--ecrire` rend la source codex, jamais l'inverse.
  * Entre le constat et l'écriture, un lien posé par un tiers n'est pas revu (fenêtre de course, non fermée ici).

Stdlib seule.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import stat
import sys
import tempfile
import time
from pathlib import Path

JUMEAUX: tuple[str, str] = (".codex/hooks", ".gemini/hooks")
PREFIXE_TEMP = ".hooks_jumeaux-"
SUFFIXE_TEMP = ".tmp"
REPRISES_REMPLACEMENT = 5
ATTENTE_INITIALE_S = 0.05
REMEDE = "regenerer : python3 .agents/bin/hooks_jumeaux.py --ecrire (un orphelin se retire a la main)"


class Refus(Exception):
    """rc 2 : le constat ne se fait pas, rien n'est écrit."""


def racine_par_defaut() -> Path:
    """La racine de l'arbre qui porte ce fichier, résolue à l'appel (jamais à l'import)."""
    return Path(__file__).resolve().parents[2]


def eligibles(dossier: Path) -> list[str]:
    """Noms `*.py` hors `test_*.py` de `dossier`, listage NON récursif, triés ; dossier absent → []."""
    try:
        noms = [p.name for p in dossier.iterdir()]
    except FileNotFoundError:
        return []
    except OSError as exc:
        raise Refus(f"listage impossible : {dossier} ({exc})") from exc
    return sorted(n for n in noms if n.endswith(".py") and not n.startswith("test_"))


def verifier_chemin(racine: Path, relatif: str, *, fichier: bool = False) -> None:
    """Refus si un maillon de `racine/relatif` (racine exclue) sort du realpath de la racine ou est un lien symbolique.

    Un maillon absent arrête la vérification : rien n'existe au-delà. Avec `fichier`, le dernier maillon, s'il existe,
    doit être un fichier régulier.
    """
    reel_racine = os.path.realpath(racine)
    parties = Path(relatif).parts
    courant = racine
    for rang, partie in enumerate(parties):
        courant = courant / partie
        reel = os.path.realpath(courant)
        if os.path.commonpath([reel_racine, reel]) != reel_racine:
            raise Refus(f"hors de la racine : {courant} -> {reel}")
        try:
            mode = os.lstat(courant).st_mode
        except FileNotFoundError:
            return
        except OSError as exc:
            raise Refus(f"lecture impossible : {courant} ({exc})") from exc
        if stat.S_ISLNK(mode):
            raise Refus(f"lien symbolique : {courant}")
        if fichier and rang == len(parties) - 1 and not stat.S_ISREG(mode):
            raise Refus(f"pas un fichier regulier : {courant}")


def constater(racine: Path) -> list[tuple[str, str]]:
    """Les écarts `(etiquette, nom)` triés par nom ; lève `Refus` (rc 2) AVANT toute comparaison."""
    source_rel, cible_rel = JUMEAUX
    for relatif in JUMEAUX:
        verifier_chemin(racine, relatif)
    noms_source = eligibles(racine / source_rel)
    if not noms_source:
        raise Refus(f"source vide ou absente : {racine / source_rel} (aucun *.py hors test_*.py)")
    noms_cible = eligibles(racine / cible_rel)
    tous = sorted(set(noms_source) | set(noms_cible))
    for nom in tous:
        if nom in noms_source:
            verifier_chemin(racine, f"{source_rel}/{nom}", fichier=True)
        verifier_chemin(racine, f"{cible_rel}/{nom}", fichier=True)
    ecarts: list[tuple[str, str]] = []
    for nom in tous:
        if nom not in noms_source:
            ecarts.append(("orphelin", nom))
        elif nom not in noms_cible:
            ecarts.append(("absent", nom))
        elif (racine / source_rel / nom).read_bytes() != (racine / cible_rel / nom).read_bytes():
            ecarts.append(("different", nom))
    return ecarts


def remplacer(temporaire: str, destination: Path) -> None:
    """`os.replace` avec une reprise bornée sur `PermissionError` (lecteur concurrent sous Windows)."""
    for essai in range(REPRISES_REMPLACEMENT):
        try:
            os.replace(temporaire, destination)
            return
        except PermissionError:
            if essai == REPRISES_REMPLACEMENT - 1:
                raise
            time.sleep(ATTENTE_INITIALE_S * (2 ** essai))


def ecrire(racine: Path, nom: str) -> None:
    """Copie atomique de `source/nom` vers `cible/nom` : temporaire hors `*.py` du dossier cible, mode source."""
    source = racine / JUMEAUX[0] / nom
    dossier_cible = racine / JUMEAUX[1]
    donnees = source.read_bytes()
    mode = stat.S_IMODE(os.stat(source).st_mode)
    descripteur, temporaire = tempfile.mkstemp(prefix=PREFIXE_TEMP, suffix=SUFFIXE_TEMP, dir=dossier_cible)
    try:
        with os.fdopen(descripteur, "wb") as flux:
            flux.write(donnees)
            flux.flush()
            os.fsync(flux.fileno())
        os.chmod(temporaire, mode)
        remplacer(temporaire, dossier_cible / nom)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporaire)
        raise


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="hooks_jumeaux.py",
        description="Twin hooks: the gemini Python hooks are a byte-exact copy of the codex source.")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="read only (default)")
    # T-01M5QC86XN : nom anglais en tete, ancien nom garde en alias, `dest` ancien explicite.
    mode.add_argument("--write", "--ecrire", dest="ecrire", action="store_true",
                      help="rewrite the absent and different files, never delete (alias: --ecrire)")
    ap.add_argument("--root", "--racine", dest="racine", type=Path, default=None, metavar="ROOT",
                    help="repository root (default: the one holding this file) (alias: --racine)")
    args = ap.parse_args(argv)
    racine = args.racine if args.racine is not None else racine_par_defaut()
    if not racine.is_dir():
        print(f"hooks_jumeaux : REFUS (rc 2) - racine absente : {racine}", file=sys.stderr)
        return 2
    try:
        ecarts = constater(racine)
        if args.ecrire:
            for etiquette, nom in ecarts:
                if etiquette in ("absent", "different"):
                    ecrire(racine, nom)
                    print(f"ecrit: {nom}")
            ecarts = constater(racine)
    except Refus as exc:
        print(f"hooks_jumeaux : REFUS (rc 2) - {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"hooks_jumeaux : erreur d'E/S (rc 2) - {exc}", file=sys.stderr)
        return 2
    for etiquette, nom in ecarts:
        print(f"{etiquette}: {nom}")
    if ecarts:
        print(f"hooks_jumeaux : {len(ecarts)} ecart(s) entre {JUMEAUX[0]} et {JUMEAUX[1]} ; {REMEDE}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
