#!/usr/bin/env python3
"""LE CADRAGE AVANT LE PLANNER — le bloc que la console affiche EN PREMIER (lecture seule, sans LLM).

Usage : `bash .agents/pyrun.sh .agents/bin/cadrage_plan.py --task T --file "<chemin>" [--file …]
         [--part "NOM=<chemin>,<chemin>" …] [--chantier NOM] [--root R]` — chaque chemin entre guillemets doubles
(une apostrophe de chemin casse les apostrophes). Joué UNE fois par tâche, avant son PREMIER planner : ni sur
la voie directe, une reprise, une révision ou un enfant d'une découpe (arbitrage S-01M5BFKA2D).

Ce qu'il fait : il MESURE l'inventaire qu'on lui donne et imprime un bloc `CADRAGE <T>` … `FIN CADRAGE`,
toujours en tête de sa sortie — tâche, taille, surfaces et hôtes, verdict `planifier` ou `découper`, découpe
proposée et ordre de lancement, clôture prévue, estimation, suite. Il n'écrit RIEN : ni board, ni SPECS, ni
fichier ; il lit le titre par `tasks.py list --task T --json` et l'estimation par `specs.py chrono --json`.

L'INVENTAIRE EST DÉCLARÉ, jamais deviné : `--file` nomme chaque chemin exact que la tâche écrira (ni glob, ni
répertoire, ni chemin absolu, ni `..`) ; `--part NOM=…` propose un enfant et ses chemins. Les parties doivent
COUVRIR l'inventaire et n'y rien ajouter ; un chemin partagé par deux enfants est permis et DIT : il impose la
série. L'outil est aussi aveugle que l'inventaire qu'on lui passe — un fichier oublié n'est pas compté.

LES SEUILS SONT HEURISTIQUES, NON CALIBRÉS (le bloc le dit) : `découper` si la tâche écrit 11 chemins ou plus ;
ou 6 ou plus sur 3 surfaces ou plus ; ou 8 ou plus mêlant code et prose. Sinon `planifier`. Une surface est une
case d'une table FERMÉE (`SURFACES` ci-dessous : un hôte, le routeur, les skills, les outils, les bancs…) ;
un hôte est une surface d'hôte (Claude Code, Codex, Gemini CLI, Copilot, Kimi Code, Antigravity).

L'ORDRE (décisions pilote S-01M5AQMWW0077BDFZMJAAXJP7S, S-01M5ATNMNBYQGYF65SNNZ5JHBN ; arbitrage
S-01M5AS2CZZMN712C7SWMKPMVG6) : le premier enfant part par `tasks.py fournee` ; un enfant qui ne recouvre aucun
enfant précédent (tous restent `running` jusqu'à la clôture) part aussi par `fournee` ; sinon `tasks.py start
<enfant>` APRÈS LA FUSION de chaque enfant précédent qu'il recouvre, suivi de `tasks.py fournee <enfant>` si son
plan porte des `LOT:`. Ce `start` ne repasse AUCUNE `running` en `pending` (T-01M5F7286N1EYGXAXA5244X86B) : la
ligne `Ordre :` NOMME les `running` lues au cadrage (`tasks.py list --state running --json`), `aucune` ou
`illisible` ; une `running` étrangère qui recouvre l'enfant est fusionnée avant son `start`.
Aucune arête `depends_on` entre enfants : une arête impose l'amont `done`, donc une porte de plus par arête.
Chaque enfant hérite des amonts DÉCLARÉS du parent, créé seulement si `tasks.py deps-ready <parent>` rend
`AMONT_CLOS` (L'AMONT D'ABORD, S-01M4Z5VMP5E9YN8T6EMDTBAF0T) : la ligne `Suite :` le dit.
LA CLÔTURE (S-01M5E50ABADJA72966YQF4J285) : pendant que le DERNIER enfant est `running` (focus du clone), la
portée déclarée AVANT la revue de clôture globale — `tasks.py review-scope <parent> <lots> <enfants>`, liste
EXPLICITE —, puis la revue, corrections, porte unique, puis `done` des lots, des autres enfants (toujours
`running`), du dernier, et du parent par `done --sans-binome "parent de coordination sans code"` (chez
l'adoptant, avec `--sans-cible "parent de découpe sans plan (cadrage)"` : le parent n'a pas de plan) ; l'emprunt
passe par la portée, plus par le chantier (le traceur écrit sur chaque membre nommé) ; aucune autre porte entre
la porte et ces `done` (une trace empruntée périme à la porte verte suivante).

L'ESTIMATION (arbitrage S-01M5BFKA2D) : la fourchette médiane–p90 PAR TÂCHE de `specs.py chrono` (durée et
jetons cumulés de tous les tours planner + critique d'une tâche, tâches mesurées de ce dépôt), multipliée par
le nombre de plans ; sans tâche mesurée, ou chrono illisible, la mesure du kit du 18/10 (22–79 min et
250–470 k jetons par plan), étiquetée comme telle. Jamais une borne.

Code de sortie : 0 dès que le bloc est imprimé ; 2 sur un refus — racine absente, id non conforme, tâche
inconnue ou sans titre, board illisible (sous-processus `tasks.py` en échec, hors délai ou introuvable), aucun
`--file`, chemin non exact, partie vide, mal formée, en double, réduite à une seule, chemin de partie hors
inventaire, chemin d'inventaire non couvert — TOUTES les causes sur stderr, rien sur stdout. Un `specs.py
chrono` hors délai rend le repli étiqueté, jamais une trace. `--root` par défaut : `CLAUDE_PROJECT_DIR`,
sinon `.`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

HERE = Path(__file__).resolve().parent
TASKS = HERE / "tasks.py"
SPECS = HERE / "specs.py"

# Les seuils — heuristiques, NON CALIBRÉS (C7 du critique 1) : changer l'un d'eux change le verdict imprimé.
SEUIL_CHEMINS = 11
SEUIL_SURFACES_CHEMINS = 6
SEUIL_SURFACES = 3
SEUIL_MIXTE = 8

# La mesure du kit (vague 2 du 18/10, planner Claude) : le repli quand ce dépôt n'a aucun tour mesuré.
MESURE_KIT = "mesure du kit, 18/10 : 22–79 min et 250–470 k jetons par plan"

MOTIF_PARENT = "parent de coordination sans code"
# Chez l'adoptant (`PLAN_CIBLE_REQUIRED` `chantier=*`), le parent sans plan se clôt aussi par cette sortie tracée.
MOTIF_CIBLE_PARENT = "parent de découpe sans plan (cadrage)"
# Le code rendu par `_executer` quand le sous-processus n'a pas abouti (délai, binaire introuvable).
RC_SOUS_PROCESSUS = 124

_ID_TACHE = re.compile(r"T-[0-9A-HJKMNP-TV-Z]{26}|[Tt]-0*[0-9]{1,15}")
_NOM_PARTIE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,15}")
_CHANTIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")

# Table FERMÉE, premier préfixe qui s'applique. Un chemin hors table tombe dans `autre:<1er segment>`.
HOTES = (
    (".claude/", "Claude Code"),
    (".codex/", "Codex"),
    (".gemini/", "Gemini CLI"),
    (".github/", "Copilot"),
    (".kimi-code/", "Kimi Code"),
    (".agent/", "Antigravity"),
)
SURFACES = (
    (".agents/skills/", "skills"),
    (".agents/bin/", "outils"),
    ("core-scripts/", "outils"),
    (".agents/evals/", "bancs"),
    (".agents/", "noyau"),
    ("src/", "code produit"),
    ("docs/", "docs"),
)
ROUTEUR = {"AGENTS.md", "CLAUDE.md", "GEMINI.md"}
CODE = {".py", ".sh", ".bash", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".go", ".java", ".kt", ".rs",
        ".rb", ".php", ".cs", ".c", ".h", ".cpp", ".swift", ".vue", ".svelte"}
PROSE = {".md", ".mdx", ".txt", ".rst", ".adoc"}


class Refus(Exception):
    """Une ou plusieurs causes : rien n'est imprimé sur stdout."""

    def __init__(self, causes: list[str]):
        super().__init__("; ".join(causes))
        self.causes = causes


def cause_de_chemin(brut: str) -> str | None:
    """`None` si `brut` est un chemin EXACT relatif à la racine, sinon la cause."""
    if not brut or brut != brut.strip():
        return f"chemin vide ou entouré d'espaces : {brut!r}"
    if any(ord(c) < 32 for c in brut) or "\\" in brut:
        return f"chemin à caractère de contrôle ou antislash : {brut!r}"
    if brut.startswith("/") or re.match(r"[A-Za-z]:", brut):
        return f"chemin absolu : {brut}"
    if brut.endswith("/"):
        return f"répertoire, pas un chemin exact : {brut}"
    if any(c in brut for c in "*?["):
        return f"motif glob, pas un chemin exact : {brut}"
    if ".." in PurePosixPath(brut).parts:
        return f"chemin qui remonte (`..`) : {brut}"
    return None


def canonique(brut: str) -> str:
    return str(PurePosixPath(brut))


def surface_de(chemin: str) -> tuple[str, bool]:
    """`(surface, est_un_hote)` — table fermée, premier préfixe qui s'applique."""
    for prefixe, nom in HOTES:
        if chemin.startswith(prefixe):
            return nom, True
    if chemin in ROUTEUR:
        return "routeur", False
    for prefixe, nom in SURFACES:
        if chemin.startswith(prefixe):
            return nom, False
    tete = chemin.split("/", 1)
    return ("racine" if len(tete) == 1 else f"autre:{tete[0]}"), False


def nature_de(chemin: str) -> str | None:
    suffixe = PurePosixPath(chemin).suffix.lower()
    if suffixe in CODE:
        return "code"
    if suffixe in PROSE:
        return "prose"
    return None


def mesurer(chemins: list[str]) -> dict[str, object]:
    surfaces: list[str] = []
    hotes: list[str] = []
    natures = set()
    for c in chemins:
        nom, hote = surface_de(c)
        if nom not in surfaces:
            surfaces.append(nom)
        if hote and nom not in hotes:
            hotes.append(nom)
        nature = nature_de(c)
        if nature:
            natures.add(nature)
    return {"n": len(chemins), "surfaces": surfaces, "hotes": hotes, "mixte": natures == {"code", "prose"}}


def verdict(mesure: dict[str, object]) -> tuple[str, str]:
    """`(verdict, règle)` — le premier seuil franchi, dans l'ordre de la doctrine."""
    n, s, mixte = int(mesure["n"]), len(mesure["surfaces"]), bool(mesure["mixte"])  # type: ignore[arg-type]
    if n >= SEUIL_CHEMINS:
        return "découper", f"{n} chemins ≥ {SEUIL_CHEMINS}"
    if n >= SEUIL_SURFACES_CHEMINS and s >= SEUIL_SURFACES:
        return "découper", f"{n} chemins ≥ {SEUIL_SURFACES_CHEMINS} sur {s} surfaces ≥ {SEUIL_SURFACES}"
    if n >= SEUIL_MIXTE and mixte:
        return "découper", f"{n} chemins ≥ {SEUIL_MIXTE} mêlant code et prose"
    return "planifier", (f"sous les seuils (≥ {SEUIL_CHEMINS} chemins ; ≥ {SEUIL_SURFACES_CHEMINS} sur "
                         f"≥ {SEUIL_SURFACES} surfaces ; ≥ {SEUIL_MIXTE} mêlant code et prose)")


def lire_parties(bruts: list[str], inventaire: list[str]) -> tuple[list[tuple[str, list[str]]], list[str]]:
    """Les parties dans l'ordre donné, et TOUTES les causes de refus (couverture comprise)."""
    causes: list[str] = []
    parties: list[tuple[str, list[str]]] = []
    vus: set[str] = set()
    for brut in bruts:
        nom, egal, liste = brut.partition("=")
        nom = nom.strip()
        if not egal or not _NOM_PARTIE.fullmatch(nom):
            causes.append(f"partie mal formée (attendu `NOM=chemin,chemin`, NOM `[A-Za-z][A-Za-z0-9_-]*`) : {brut!r}")
            continue
        if nom in vus:
            causes.append(f"partie en double : {nom}")
            continue
        vus.add(nom)
        chemins: list[str] = []
        for morceau in liste.split(","):
            cause = cause_de_chemin(morceau)
            if cause:
                causes.append(f"partie {nom} : {cause}")
                continue
            c = canonique(morceau)
            if c not in chemins:
                chemins.append(c)
        if not chemins and not any(x.startswith(f"partie {nom} :") for x in causes):
            causes.append(f"partie vide : {nom}")
        parties.append((nom, chemins))
    if bruts and len(parties) == 1 and not causes:
        causes.append("une seule partie : une découpe compte au moins deux enfants")
    if parties:
        couverts = {c for _n, cs in parties for c in cs}
        for nom, cs in parties:
            for c in cs:
                if c not in inventaire:
                    causes.append(f"partie {nom} : `{c}` n'est pas dans l'inventaire (`--file`)")
        for c in inventaire:
            if c not in couverts:
                causes.append(f"`{c}` n'est couvert par aucune partie")
    return parties, causes


def _etiquette(nom: str, chemins: list[str]) -> str:
    """`NOM (n chemins)` ; un enfant encore au-dessus du seuil le DIT, avec sa règle : il n'est pas re-cadré
    (arbitrage S-01M5BFKA2D), le pilote tranche sur ce bloc."""
    leve, regle = verdict(mesurer(chemins))
    base = f"{nom} ({len(chemins)} chemin{'s' if len(chemins) > 1 else ''}"
    return base + (f", encore au-dessus du seuil : {regle} — au pilote, jamais re-cadré)" if leve == "découper"
                   else ")")


def ordre(parties: list[tuple[str, list[str]]]) -> list[str]:
    """Le verbe de lancement de chaque enfant, dans l'ordre de fusion proposé."""
    phrases: list[str] = []
    for k, (nom, chemins) in enumerate(parties):
        if k == 0:
            phrases.append(f"{nom} part par `tasks.py fournee`")
            continue
        # Aucun `start` ne rétrograde (T-01M5F7286N1EYGXAXA5244X86B) : chaque enfant précédent reste `running`
        # jusqu'à la clôture, donc le recouvrement se lit contre TOUS, et `start` n'attend que ceux qu'il recouvre.
        recouvre = [(autre, sorted(set(chemins) & set(cs))) for autre, cs in parties[:k] if set(chemins) & set(cs)]
        if not recouvre:
            phrases.append(f"{nom}, disjoint des enfants `running`, part aussi par `tasks.py fournee`")
            continue
        detail = ", ".join(f"{autre} (`{'`, `'.join(cs)}`)" for autre, cs in recouvre)
        phrases.append(f"{nom} recouvre {detail} : `tasks.py start {nom}` APRÈS LA FUSION de "
                       f"{', '.join(a for a, _c in recouvre)} (aucune `running` ne repasse `pending`), puis "
                       f"`tasks.py fournee {nom}` si son plan porte des `LOT:`")
    return phrases


def duree(secondes: int) -> str:
    h, reste = divmod(int(secondes), 3600)
    m, s = divmod(reste, 60)
    return f"{h}h{m:02d}m{s:02d}s" if h else f"{m}m{s:02d}s"


def jetons(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f} M"
    return f"{n / 1000:.1f} k"


def _executer(script: Path, racine: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Le sous-processus en liste argv ; un délai dépassé ou un binaire introuvable rend rc 124 et sa cause sur
    stderr, jamais une trace : `lire_tache` en fait un refus rc 2, `estimation` le repli étiqueté."""
    env = dict(os.environ)
    env.pop("CLAUDE_PROJECT_DIR", None)
    cmd = [sys.executable, str(script), "--root", str(racine), *args]
    try:
        return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", env=env, timeout=120,
                              check=False)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return subprocess.CompletedProcess(cmd, RC_SOUS_PROCESSUS, "", f"{script.name} : {type(exc).__name__} ({exc})")


def lire_tache(racine: Path, tid: str) -> dict[str, object]:
    p = _executer(TASKS, racine, "list", "--task", tid, "--json")
    if p.returncode != 0:
        premiere = (p.stderr.strip().splitlines() or ["(sans message)"])[0]
        raise Refus([f"tâche illisible au board : {premiere}"])
    try:
        taches = json.loads(p.stdout)
        tache = taches[0]
    except (ValueError, IndexError, KeyError, TypeError):
        raise Refus([f"tâche illisible au board : sortie JSON inattendue de `tasks.py list --task {tid}`"]) from None
    if not isinstance(tache, dict) or not str(tache.get("task") or "").strip():
        raise Refus([f"tâche {tid} sans titre au board"])
    return tache


def _mediane(valeurs: list[int]) -> int:
    """La médiane basse d'une liste TRIÉE, jamais une interpolation."""
    return valeurs[(len(valeurs) - 1) // 2]


def _p90(valeurs: list[int]) -> int:
    """Rang le plus proche d'une liste TRIÉE, la valeur au rang ⌈0,9·n⌉ — la règle de `specs.py chrono`."""
    return valeurs[max(0, -(-9 * len(valeurs) // 10) - 1)]


def estimation(racine: Path, plans: int) -> str:
    """La fourchette médiane–p90 PAR TÂCHE (tous ses tours cumulés), multipliée par le nombre de plans."""
    p = _executer(SPECS, racine, "chrono", "--json")
    try:
        releve = json.loads(p.stdout) if p.returncode == 0 else {}
        taches = [t for t in releve["taches"].values() if int(t["mesures"]) > 0]
        durees = sorted(int(t["duree"]) for t in taches)
        jets = sorted(int(t["jetons"]) for t in taches)
    except (ValueError, KeyError, TypeError, AttributeError):
        return (f"aucune mesure locale lisible (`specs.py chrono`) — {MESURE_KIT} ; {plans} plan(s) ; hors "
                f"développement et porte ; pas une borne")
    if not durees or _p90(durees) <= 0:
        return (f"aucune tâche mesurée dans ce dépôt — {MESURE_KIT} ; {plans} plan(s) ; hors développement et "
                f"porte ; pas une borne")
    return (f"~{duree(_mediane(durees) * plans)} à ~{duree(_p90(durees) * plans)} et ~{jetons(_mediane(jets) * plans)}"
            f" à ~{jetons(_p90(jets) * plans)} jetons pour {plans} plan(s), médiane–p90 PAR TÂCHE de `specs.py "
            f"chrono` ({len(durees)} tâche(s) mesurée(s), tous ses tours planner + critique cumulés : "
            f"{duree(_mediane(durees))} à {duree(_p90(durees))} par tâche) ; hors développement et porte ; pas une "
            f"borne")


def lire_running(racine: Path) -> list[str] | None:
    """Les `running` du board, `id (chantier)` ; `None` si le board ne se lit pas (jamais « aucune » par défaut)."""
    p = _executer(TASKS, racine, "list", "--state", "running", "--json")
    try:
        taches = json.loads(p.stdout) if p.returncode == 0 else None
        return [f"{t['id']} ({t.get('chantier') or 'sans chantier'})" for t in taches]
    except (ValueError, KeyError, TypeError, AttributeError):
        return None


def cadrer(racine: Path, tid: str, fichiers: list[str], bruts_parties: list[str], chantier: str | None) -> str:
    causes: list[str] = []
    if not racine.is_dir():
        raise Refus([f"racine absente : {racine}"])
    if not _ID_TACHE.fullmatch(tid):
        causes.append(f"id de tâche non conforme : {tid!r}")
    if chantier is not None and not _CHANTIER.fullmatch(chantier):
        causes.append(f"chantier non conforme : {chantier!r}")
    inventaire: list[str] = []
    for brut in fichiers:
        cause = cause_de_chemin(brut)
        if cause:
            causes.append(cause)
        elif canonique(brut) not in inventaire:
            inventaire.append(canonique(brut))
    if not fichiers:
        causes.append("aucun `--file` : l'inventaire est déclaré, jamais deviné")
    parties, causes_parties = lire_parties(bruts_parties, inventaire)
    causes += causes_parties
    if causes:
        raise Refus(causes)
    tache = lire_tache(racine, tid)
    titre = " ".join(str(tache["task"]).split())
    if chantier is None:
        chantier = str(tache.get("chantier") or "").strip() or f"cadrage-{tid}"

    mesure = mesurer(inventaire)
    leve, regle = verdict(mesure)
    affectations = sum(len(cs) for _n, cs in parties)
    taille = f"{mesure['n']} chemins distincts"
    if parties:
        taille += f", {affectations} affectations entre {len(parties)} enfants"
    surfaces, hotes = list(mesure["surfaces"]), list(mesure["hotes"])  # type: ignore[call-overload]
    taille += f" ; {len(surfaces)} surface(s) : {', '.join(surfaces)}"
    taille += f" ; {len(hotes)} hôte(s) : {', '.join(hotes) if hotes else 'aucun'}"
    if mesure["mixte"]:
        taille += " ; code et prose mêlés"

    lignes = [f"CADRAGE {tid}", f"Titre : {titre}", f"Taille mesurée : {taille}.",
              f"Verdict : {leve} — {regle} ; seuil heuristique, non calibré."]
    if parties:
        partages = sorted({c for _n, cs in parties for c in cs
                           if sum(c in cs2 for _m, cs2 in parties) > 1})
        decoupe = ", ".join(_etiquette(nom, cs) for nom, cs in parties)
        if partages:
            decoupe += f" ; chemin(s) partagé(s), donc série : `{'`, `'.join(partages)}`"
        if leve == "planifier":
            decoupe = "proposée, non exigée par le seuil : " + decoupe
        dernier = parties[-1][0]
        autres = ", ".join(n for n, _c in parties[:-1])
        enfants = " ".join(n for n, _c in parties)
        running = lire_running(racine)
        vues = ", ".join(running) if running else ("aucune" if running == [] else "illisible")
        lignes += [
            f"Découpe : {decoupe}.",
            f"Ordre : {' ; '.join(ordre(parties))}. Tous les enfants portent `--chantier {chantier}` ; aucune "
            f"arête `depends_on` entre eux (une arête impose l'amont `done`, donc une porte de plus par arête) ; "
            f"l'ordre se trace en `SUGGESTION:`. `running` au board à ce cadrage : {vues} — un `start` d'enfant "
            f"ne repasse AUCUNE `running` en `pending`, d'un autre chantier comprise : relire `tasks.py list "
            f"--state running` avant chaque `start`, et attendre la fusion d'une `running` étrangère qui recouvre "
            f"l'enfant.",
            f"Clôture prévue : pendant que {dernier} est `running` (focus du clone), AVANT la revue de clôture "
            f"globale, `tasks.py review-scope {tid} <lots de fournée> {enfants}` (liste EXPLICITE parent, lots et "
            f"enfants, ids du board, jamais inférée), puis la revue, corrections, porte unique, puis `done` des "
            f"lots de fournée, puis {autres} (toujours `running` ; l'emprunt passe par la portée, plus par le "
            f"chantier), PUIS {dernier}, PUIS le parent par `done --sans-binome \"{MOTIF_PARENT}\"` (jamais un "
            f"enfant ; chez l'adoptant, avec `--sans-cible \"{MOTIF_CIBLE_PARENT}\"` : le parent n'a pas de plan) ; "
            f"aucune autre porte entre la porte et ces `done`.",
        ]
        plans = len(parties)
    else:
        if leve == "découper":
            lignes.append("Découpe : à proposer — relance avec une `--part NOM=chemin,…` par enfant ; aucun "
                          "enfant n'est créé sans elle.")
        else:
            lignes.append("Découpe : aucune — un seul plan.")
        lignes += ["Ordre : la tâche seule.", "Clôture prévue : la chaîne ordinaire — revue de clôture, "
                   "corrections, porte, `done`."]
        plans = 1
    lignes.append(f"Estimation : {estimation(racine, plans)}.")
    if leve == "découper":
        lignes.append(f"Suite : `$kickoff` lit `tasks.py deps-ready {tid}` — seul `AMONT_CLOS` crée les enfants —, "
                      f"puis les crée au board (`tasks.py new … --chantier {chantier}`, puis `tasks.py writeset`), "
                      f"chacun héritant des amonts déclarés du parent (`tasks.py depends`), sans arête entre eux ; "
                      f"la tâche cadrée ne va jamais au planner ; chaque enfant est planifié à son tour, sans "
                      f"nouveau cadrage, et lancé selon l'Ordre ci-dessus.")
    elif parties:
        lignes.append("Suite : le planner part sur cette tâche ; la découpe proposée, non exigée par le seuil, ne se "
                      "fait que sur décision du pilote.")
    else:
        lignes.append("Suite : le planner part sur cette tâche.")
    lignes.append("FIN CADRAGE")
    return "\n".join(lignes) + "\n"


def main(argv: list[str] | None = None) -> int:
    # T-01M5QC86XN, lot P : `--workstream` en tete, `--chantier` garde en alias, `dest` ancien explicite.
    parser = argparse.ArgumentParser(description="SCOPING block before the planner (read-only).")
    parser.add_argument("--root", default=os.environ.get("CLAUDE_PROJECT_DIR") or ".", help="project root")
    parser.add_argument("--task", required=True, help="task id")
    parser.add_argument("--file", action="append", default=[], dest="fichiers", metavar="FILE", help="target file (repeatable)")
    parser.add_argument("--part", action="append", default=[], dest="parties", metavar="PART", help="part (repeatable)")
    parser.add_argument("--workstream", "--chantier", dest="chantier", metavar="NAME", help="workstream (chantier) name")
    args = parser.parse_args(argv)
    try:
        bloc = cadrer(Path(args.root), args.task, args.fichiers, args.parties, args.chantier)
    except Refus as refus:
        print(f"cadrage_plan.py : REFUS — {len(refus.causes)} cause(s) :", file=sys.stderr)
        for cause in refus.causes:
            print(f"  - {cause}", file=sys.stderr)
        return 2
    sys.stdout.write(bloc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
