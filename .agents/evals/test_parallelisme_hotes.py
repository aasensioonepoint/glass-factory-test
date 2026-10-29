"""Témoin de T-01M4VBZFB6KWTW22618C0VWB13, lot D2 : le parallélisme des devs, PAR HÔTE.

La table `.agents/ref/PARALLELISME_HOTES.md` dit, hôte par hôte, ce qui a été MESURÉ du
lancement de devs en parallèle, chacun dans son worktree. Ce banc tient P1-P7 de l'Annexe T
du plan, chaque témoin avec son mutant nommé :

P1 la table : six lignes `HOTE:`, chaque hôte une fois, sept champs ; statut comparé à
   l'ÉGALITÉ EXACTE au vocabulaire fermé (`pas-mesure` admis, `non-mesure` refusé ; le
   mutant « par préfixe » se juge sur la troncature `non-mesur`, voir son cas) ; date du
   statut ISO ; claude = mesure-parallele, source citée (un id `L-` du ledger) ; codex et
   copilot en `pas-mesure` portent la cause neutre `aucune session lancée au <date>` ; kimi
   en `hote-absent` porte ses quatre sondes et la cause fermée ; antigravity = non-mesurable,
   `présent … sans CLI headless`.
P2 chaque `mesure-parallele` hors claude porte date, os-arch, version, o >= 30 (M1 aux deux
   passages, ou M2) et M1-bis ok — vide sur l'arbre de la nuit (aucun P), d'où son mutant
   OBLIGATOIRE et son contrôle positif.
P3 la déf orchestrator de chaque hôte porte la ligne exacte de son statut (antigravity : déf
   gemini ; kimi : défs claude et kimi).
P4 la section README « Parallel devs per host » pointe une fois vers la table, sans copie.
P5 les hôtes nommés après « MESURÉ sur » (AGENTS.md) et après « measured on » (miroir
   copilot, kickoff SKILL, kickoff.md) = {claude} ∪ P.
P6 kickoff porte le pointeur de la table : la SKILL à sa phrase de portée ET à chaque ligne
   `COVERAGE DEGRADED — parallélisme des devs`, la commande à sa phrase de portée.
P7 la ligne gemini ouvre sa cause par `facturation`, porte `strict-open`, sa date et
   `darwin-arm64`.

Deux jeux, choisis par `-k` : les noms de fonction portent `synth` ou `vivant`, et aucun id
de mutant ne porte l'un ou l'autre.
- `synth` : un arbre synthétique sous `tempfile.mkdtemp` — les quatre surfaces de D2 (table,
  README, kickoff SKILL, kickoff.md) RECOPIÉES du dépôt, les surfaces des lots O et D1 (défs
  orchestrator x5, AGENTS.md, miroir copilot) FABRIQUÉES depuis la table. Base verte, puis
  chaque mutant écrit dans une copie neuve sous `mkdtemp`, relue, qui doit rougir LE témoin
  visé ; une mutation sans effet est un échec, jamais un vert (L-00000161).
- `vivant` : l'arbre réel du dépôt, base verte puis les mêmes mutants. EN ATTENTE DE FUSION
  PAR CONSTRUCTION : il lit les fichiers que les lots O et D1 écrivent en parallèle de D2 ;
  il rougit dans le worktree de D2 seul et se joue en entier après les quatre fusions
  (étape 6 du plan). Le dev de D2 joue `-k synth`.

Bornes, dites :
- P3 n'exige rien de la déf claude POUR claude : son statut `mesure-parallele` est la
  doctrine de base (un message, un worktree par dev), tenue par test_worktree_doctrine et
  test_fournee_doctrine.
- P5 couvre quatre surfaces SEULES (C48) : les défs indexer, roster/indexer.json et la
  task-board SKILL décrivent l'état du board, pas le lancement des devs. Il lit la fenêtre
  qui suit le jeton épinglé de chaque surface, jusqu'à la fin de son paragraphe (FENETRE
  caractères au plus) ; une ancre ailleurs dans le fichier n'est pas lue.
- Ce banc tient la COHÉRENCE des surfaces entre elles et avec le vocabulaire fermé, jamais
  la vérité d'une mesure : la table ne prouve pas le recouvrement qu'elle cite.
"""
from __future__ import annotations

import re
import tempfile
import unicodedata
from collections.abc import Callable
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TABLE = ".agents/ref/PARALLELISME_HOTES.md"
README = "README-OTHER-HOSTS.md"
KICKOFF_SKILL = ".agents/skills/kickoff/SKILL.md"
KICKOFF_CMD = ".claude/commands/kickoff.md"
AGENTS = "AGENTS.md"
COPILOT = ".github/copilot-instructions.md"
DEFS = {  # la déf orchestrator de chaque hôte qui en a une
    "claude": ".claude/agents/orchestrator.md",
    "codex": ".codex/agents/orchestrator.toml",
    "copilot": ".github/agents/orchestrator.agent.md",
    "gemini": ".gemini/agents/orchestrator.md",
    "kimi": ".kimi-code/agents/orchestrator.md",
}
SURFACES_D2 = (TABLE, README, KICKOFF_SKILL, KICKOFF_CMD)
SURFACES_AUTRES = (AGENTS, COPILOT, *DEFS.values())

HOTES = ("claude", "codex", "copilot", "gemini", "kimi", "antigravity")
STATUTS = ("mesure-parallele", "mesure-serie", "pas-mesure", "non-mesurable", "hote-absent")
NOMS = {"claude": "Claude Code", "codex": "Codex", "copilot": "GitHub Copilot",
        "gemini": "Gemini CLI", "kimi": "Kimi Code", "antigravity": "Antigravity"}
PORTEUSES = {  # P3 : les défs qui portent la ligne de chaque hôte (claude : borne dite)
    "claude": (), "codex": ("codex",), "copilot": ("copilot",), "gemini": ("gemini",),
    "kimi": ("claude", "kimi"), "antigravity": ("gemini",),
}
MOTIFS_HOTES = {"claude": r"\bClaude Code\b", "codex": r"\bCodex\b", "copilot": r"\bCopilot\b",
                "gemini": r"\bGemini\b", "kimi": r"\bKimi\b", "antigravity": r"\bAntigravity\b"}
PREFIXE = "COVERAGE DEGRADED — parallélisme des devs"
CAUSE_NEUTRE = "aucune session lancée au {date}"
CAUSE_KIMI = "hôte absent du poste de mesure (which, /Applications, ~/.kimi*, fnm et npm)"
TITRE_README = "\n## Parallel devs per host\n"
PORTEE = (  # (surface, jeton épinglé qui ouvre la fenêtre, ancre de portée, casse)
    (AGENTS, "Les devs tournent EN PARALLÈLE", "MESURÉ sur", True),
    (COPILOT, "devs run in parallel, in git worktrees", "measured on", False),
    (KICKOFF_SKILL, "devs run in parallel, in git worktrees", "measured on", False),
    (KICKOFF_CMD, "Devs run in parallel, in git worktrees", "measured on", False),
)
FENETRE = 4000
FENETRE_POINTEUR = 300
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
OSARCH = re.compile(r"[a-z0-9]+-[a-z0-9_]+")
VERSION = re.compile(r"\d+(?:\.\d+)+")
MESURES = re.compile(r"M1 (—|-?\d+,-?\d+) ; M2 (—|-?\d+) ; M1-bis (ok|ko|—)")
FIN_CLAUSE = re.compile(r"[;(.:—]")
FIN_PARAGRAPHE = re.compile(r"\n[ \t]*\n|\n(?=[ \t]*(?:[-*] |\d+[a-z]*\. |#))")

Arbre = dict[str, "str | None"]
Violation = tuple[str, str]


# ---------------------------------------------------------------------------
# Fonctions pures — les mutants rejouent CES fonctions
# ---------------------------------------------------------------------------
def plat(texte: str) -> str:
    """NFC, blancs pliés : une phrase coupée sur deux lignes compte."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", texte))


def motif_souple(jeton: str) -> str:
    return r"\s+".join(re.escape(mot) for mot in unicodedata.normalize("NFC", jeton).split())


def statut_admis(statut: str) -> bool:
    """ÉGALITÉ EXACTE au vocabulaire fermé, jamais un préfixe."""
    return statut in STATUTS


def lignes_table(texte: str) -> list[list[str]]:
    return [[c.strip() for c in brute[len("HOTE:"):].split(" | ")]
            for brute in texte.splitlines() if brute.startswith("HOTE:")]


def par_hote(lignes: list[list[str]]) -> dict[str, list[str]]:
    return {ligne[0]: ligne for ligne in lignes if len(ligne) == 7}


def lignes_readme(texte: str) -> list[str] | None:
    """Les lignes de la section, ou None si la section manque ou est ambiguë."""
    if texte.count(TITRE_README) != 1:
        return None
    section = texte[texte.find(TITRE_README) + len(TITRE_README):]
    fin = section.find("\n## ")
    section = section if fin == -1 else section[:fin]
    return [ligne.strip() for ligne in section.splitlines()]


def ligne_attendue(hote: str, ligne: list[str]) -> str | None:
    """La ligne que la déf de `hote` porte pour son statut (None : claude, ou statut inconnu)."""
    if hote == "claude":
        return None
    _, statut, date, osarch, version, _, _ = ligne
    nom = NOMS[hote]
    return {
        "pas-mesure": f"{PREFIXE} non mesuré sur {nom} : lots joués en série",
        "hote-absent": f"{PREFIXE} non mesuré sur {nom} (hôte absent du poste de mesure, {date}) : lots joués en série",
        "non-mesurable": f"{PREFIXE} non mesuré sur {nom} (présent sans CLI headless, {date}) : lots joués en série",
        "mesure-serie": f"{PREFIXE} mesuré en série sur {nom} : lots joués en série",
        "mesure-parallele": f"**{nom}** — PARALLÈLE MESURÉ ({date}, {osarch}, {version}, `{TABLE}`)",
    }.get(statut)


def hotes_paralleles(par: dict[str, list[str]]) -> list[str]:
    return [h for h in HOTES if h != "claude" and h in par and par[h][1] == "mesure-parallele"]


def fenetre(texte: str, jeton: str) -> tuple[int, int] | None:
    """[début, fin) du paragraphe qui suit le jeton épinglé, FENETRE au plus ; None sans jeton."""
    debut = texte.find(jeton)
    if debut == -1:
        return None
    reste = texte[debut:]
    m = FIN_PARAGRAPHE.search(reste)
    return debut, debut + min(m.start() if m else len(reste), FENETRE)


def hotes_nommes(clause: str) -> set[str]:
    coupe = FIN_CLAUSE.search(clause)
    clause = clause[:coupe.start()] if coupe else clause
    return {h for h, motif in MOTIFS_HOTES.items() if re.search(motif, clause)}


def temoin_p1(lignes: list[list[str]], admis: Callable[[str], bool]) -> list[str]:
    v = []
    if len(lignes) != 6:
        v.append(f"{len(lignes)} lignes HOTE:, 6 attendues")
    noms = [ligne[0] for ligne in lignes]
    v += [f"hôte {h} présent {noms.count(h)} fois" for h in HOTES if noms.count(h) != 1]
    v += [f"hôte inconnu {h!r}" for h in noms if h not in HOTES]
    for ligne in lignes:
        if len(ligne) != 7:
            v.append(f"{ligne[0]} : {len(ligne)} champs, 7 attendus")
            continue
        hote, statut, date, osarch, version, cause, mesures = ligne
        if not admis(statut):
            v.append(f"{hote} : statut hors vocabulaire fermé : {statut!r}")
        if not DATE.fullmatch(date):
            v.append(f"{hote} : date du statut illisible : {date!r}")
        if osarch != "—" and not OSARCH.fullmatch(osarch):
            v.append(f"{hote} : os-arch illisible : {osarch!r}")
        if version != "—" and not VERSION.fullmatch(version):
            v.append(f"{hote} : version illisible : {version!r}")
        if cause in ("", "—"):
            v.append(f"{hote} : source ou cause vide")
        if not MESURES.fullmatch(mesures):
            v.append(f"{hote} : champ des mesures illisible : {mesures!r}")
    par = par_hote(lignes)
    if "claude" in par:
        if par["claude"][1] != "mesure-parallele":
            v.append(f"claude : {par['claude'][1]!r}, mesure-parallele attendu")
        if not re.search(r"\bL-\d{8}\b", par["claude"][5]):
            v.append("claude : source non citée (aucun id L- du ledger)")
    for hote in ("codex", "copilot"):
        if hote in par and par[hote][1] == "pas-mesure" and par[hote][5] != CAUSE_NEUTRE.format(date=par[hote][2]):
            v.append(f"{hote} : cause {par[hote][5]!r}, la cause neutre attendue")
    if "kimi" in par and par["kimi"][1] == "hote-absent" and par["kimi"][5] != CAUSE_KIMI:
        v.append(f"kimi : cause {par['kimi'][5]!r}, la cause fermée et ses quatre sondes attendues")
    if "antigravity" in par:
        if par["antigravity"][1] != "non-mesurable":
            v.append(f"antigravity : {par['antigravity'][1]!r}, non-mesurable attendu")
        if not re.fullmatch(r"présent\b.*\bsans CLI headless", par["antigravity"][5]):
            v.append("antigravity : cause sans « présent … sans CLI headless »")
    return v


def temoin_p2(par: dict[str, list[str]]) -> list[str]:
    v = []
    for hote in hotes_paralleles(par):
        _, _, date, osarch, version, _, mesures = par[hote]
        if not DATE.fullmatch(date) or osarch == "—" or version == "—":
            v.append(f"{hote} : P sans date, os-arch ou version")
        m = MESURES.fullmatch(mesures)
        if not m:
            v.append(f"{hote} : P sans mesures lisibles")
            continue
        m1, m2, bis = m.groups()
        m1_ok = m1 != "—" and all(int(o) >= 30 for o in m1.split(","))
        m2_ok = m2 != "—" and int(m2) >= 30
        if not (m1_ok or m2_ok):
            v.append(f"{hote} : P sans recouvrement >= 30 s (M1 deux fois, ou M2)")
        if bis != "ok":
            v.append(f"{hote} : P sans M1-bis ok")
    return v


def temoin_p3(arbre: Arbre, par: dict[str, list[str]]) -> list[str]:
    v = []
    for hote, porteuses in PORTEUSES.items():
        attendue = ligne_attendue(hote, par[hote]) if hote in par else None
        if attendue is None:
            continue
        for porteuse in porteuses:
            texte = arbre.get(DEFS[porteuse]) or ""
            if plat(attendue) not in plat(texte):
                v.append(f"{DEFS[porteuse]} : ligne de {hote} absente : {attendue}")
    return v


def temoin_p4(arbre: Arbre) -> list[str]:
    readme = lignes_readme(arbre.get(README) or "")
    if readme is None:
        return [f"{README} : section « Parallel devs per host » absente ou ambiguë"]
    renvoi = f"]({TABLE})"
    if sum(ligne.count(renvoi) for ligne in readme) != 1:
        return [f"{README} : renvoi vers la table absent ou ambigu"]
    if any(ligne.startswith("|") and ligne.endswith("|") for ligne in readme):
        return [f"{README} : table recopiée dans la section"]
    return []


def temoin_p5(arbre: Arbre, par: dict[str, list[str]]) -> list[str]:
    v = []
    attendus = {"claude", *hotes_paralleles(par)}
    for chemin, jeton, ancre, casse in PORTEE:
        texte = arbre.get(chemin) or ""
        bornes = fenetre(texte, jeton)
        if bornes is None:
            v.append(f"{chemin} : jeton épinglé absent : {jeton}")
            continue
        zone = plat(texte[bornes[0]:bornes[1]])
        trouves = list(re.finditer(re.escape(ancre), zone, flags=0 if casse else re.IGNORECASE))
        if not trouves:
            v.append(f"{chemin} : phrase de portée absente (« {ancre} »)")
        for m in trouves:
            nommes = hotes_nommes(zone[m.end():])
            if nommes != attendus:
                v.append(f"{chemin} : « {ancre} » nomme {sorted(nommes)}, attendu {sorted(attendus)}")
    return v


def temoin_p6(arbre: Arbre) -> list[str]:
    v = []
    for chemin, jeton, _, _ in PORTEE:
        if chemin not in (KICKOFF_SKILL, KICKOFF_CMD):
            continue
        texte = arbre.get(chemin) or ""
        bornes = fenetre(texte, jeton)
        if bornes is None or TABLE not in texte[bornes[0]:bornes[1]]:
            v.append(f"{chemin} : pointeur de la table absent de la phrase de portée")
    skill = plat(arbre.get(KICKOFF_SKILL) or "")
    sites = [m.start() for m in re.finditer(re.escape(PREFIXE), skill)]
    if not sites:
        v.append(f"{KICKOFF_SKILL} : préfixe « {PREFIXE} » absent")
    for site in sites:
        if TABLE not in skill[site:site + FENETRE_POINTEUR]:
            v.append(f"{KICKOFF_SKILL} : ligne « {PREFIXE} » sans pointeur de la table")
    return v


def temoin_p7(par: dict[str, list[str]]) -> list[str]:
    if "gemini" not in par:
        return ["gemini : ligne absente"]
    _, _, date, osarch, _, cause, _ = par["gemini"]
    v = []
    if not cause.startswith("facturation"):
        v.append("gemini : la cause n'ouvre pas par la facturation")
    if "strict-open" not in cause:
        v.append("gemini : la cause ne porte pas strict-open")
    if not DATE.fullmatch(date):
        v.append("gemini : date absente")
    if osarch != "darwin-arm64":
        v.append(f"gemini : os-arch {osarch!r}, darwin-arm64 attendu")
    return v


def violations(arbre: Arbre, admis: Callable[[str], bool] = statut_admis) -> list[Violation]:
    """Toutes les violations de P1-P7 ; une surface absente en est une (P0), jamais un vert."""
    v: list[Violation] = [("P0", f"surface absente : {c}") for c, t in arbre.items() if not t]
    lignes = lignes_table(arbre.get(TABLE) or "")
    par = par_hote(lignes)
    v += [("P1", m) for m in temoin_p1(lignes, admis)]
    v += [("P2", m) for m in temoin_p2(par)]
    v += [("P3", m) for m in temoin_p3(arbre, par)]
    v += [("P4", m) for m in temoin_p4(arbre)]
    v += [("P5", m) for m in temoin_p5(arbre, par)]
    v += [("P6", m) for m in temoin_p6(arbre)]
    v += [("P7", m) for m in temoin_p7(par)]
    return v


# ---------------------------------------------------------------------------
# Arbres : chargement, copies sous mkdtemp, arbre synthétique
# ---------------------------------------------------------------------------
def charger(racine: Path) -> Arbre:
    arbre: Arbre = {}
    for chemin in (*SURFACES_D2, *SURFACES_AUTRES):
        fichier = racine / chemin
        arbre[chemin] = fichier.read_text(encoding="utf-8") if fichier.is_file() else None
    return arbre


def relire(arbre: Arbre) -> Arbre:
    """L'arbre écrit dans un dossier neuf sous mkdtemp, puis relu par `charger`."""
    with tempfile.TemporaryDirectory(prefix="parallelisme-hotes-", ignore_cleanup_errors=True) as dossier:
        racine = Path(dossier)
        for chemin, texte in arbre.items():
            if texte is None:
                continue
            fichier = racine / chemin
            fichier.parent.mkdir(parents=True, exist_ok=True)
            fichier.write_bytes(texte.encode("utf-8"))
        return charger(racine)


def fabriquer_autres(par: dict[str, list[str]]) -> dict[str, str]:
    """Les surfaces de O et D1, fabriquées depuis la table : ce que leurs lots doivent porter."""
    autres = {}
    for hote_def, chemin in DEFS.items():
        lignes = [ligne_attendue(h, par[h]) for h, porteuses in PORTEUSES.items()
                  if hote_def in porteuses and h in par]
        autres[chemin] = ("# orchestrator — déf SYNTHÉTIQUE (banc test_parallelisme_hotes)\n\n"
                          + "".join(f"- {ligne}.\n" for ligne in lignes if ligne))
    paralleles = hotes_paralleles(par)
    fr = "Claude Code" + ("".join(f" et sur {NOMS[h]}" for h in paralleles) if paralleles else " seul")
    en = "Claude Code" + ("".join(f" and on {NOMS[h]}" for h in paralleles) if paralleles else " only")
    autres[AGENTS] = (f"- **Task tracking** — Les devs tournent EN PARALLÈLE, chacun dans un worktree git. "
                      f"Mécanisme MESURÉ sur {fr} (`isolation: \"worktree\"`) ; ailleurs série sous "
                      f"COVERAGE DEGRADED (`{TABLE}`).\n- **Suite** — rien.\n")
    autres[COPILOT] = (f"- devs run in parallel, in git worktrees, as soon as proven disjoint; measured on {en}; "
                       f"elsewhere series under COVERAGE DEGRADED (`{TABLE}`).\n- next.\n")
    return autres


def arbre_synthetique() -> Arbre:
    reel = charger(ROOT)
    arbre: Arbre = {chemin: reel[chemin] for chemin in SURFACES_D2}
    arbre.update(fabriquer_autres(par_hote(lignes_table(reel[TABLE] or ""))))
    return relire(arbre)


# ---------------------------------------------------------------------------
# Mutants — chacun rend une copie ; l'appelant exige qu'elle diffère
# ---------------------------------------------------------------------------
def _avec(arbre: Arbre, chemin: str, texte: str) -> Arbre:
    copie = dict(arbre)
    copie[chemin] = texte
    return copie


def muter_champ(arbre: Arbre, hote: str, index: int, valeur: str) -> Arbre:
    sortie = []
    for brute in (arbre[TABLE] or "").splitlines(keepends=True):
        champs = [c.strip() for c in brute.rstrip("\n")[len("HOTE:"):].split(" | ")]
        if brute.startswith("HOTE:") and champs[0] == hote:
            champs[index] = valeur
            brute = "HOTE: " + " | ".join(champs) + "\n"
        sortie.append(brute)
    return _avec(arbre, TABLE, "".join(sortie))


def retirer_ligne_table(arbre: Arbre, hote: str) -> Arbre:
    texte = "".join(b for b in (arbre[TABLE] or "").splitlines(keepends=True)
                    if not b.startswith(f"HOTE: {hote} |"))
    return _avec(arbre, TABLE, texte)


def muter_readme(arbre: Arbre, remplacement: str) -> Arbre:
    renvoi = f"]({TABLE})"
    return _avec(arbre, README, (arbre[README] or "").replace(renvoi, remplacement, 1))


def recopier_table_readme(arbre: Arbre) -> Arbre:
    titre = "\n## Safety\n"
    copie = "\n| Host | Status |\n|---|---|\n| codex | pas-mesure |\n"
    return _avec(arbre, README, (arbre[README] or "").replace(titre, copie + titre, 1))


def retirer_de_def(arbre: Arbre, hote: str, porteuse: str) -> Arbre:
    attendue = ligne_attendue(hote, par_hote(lignes_table(arbre[TABLE] or ""))[hote]) or ""
    return _avec(arbre, DEFS[porteuse], re.sub(motif_souple(attendue), "", arbre[DEFS[porteuse]] or ""))


def dans_fenetre(arbre: Arbre, chemin: str, jeton: str, motif: str, remplacement: str) -> Arbre:
    texte = arbre[chemin] or ""
    bornes = fenetre(texte, jeton)
    if bornes is None:
        return arbre
    debut, fin = bornes
    zone = re.sub(motif, remplacement, texte[debut:fin], flags=re.IGNORECASE)
    return _avec(arbre, chemin, texte[:debut] + zone + texte[fin:])


def pointeur_coverage_retire(arbre: Arbre) -> Arbre:
    texte = arbre[KICKOFF_SKILL] or ""
    for m in reversed(list(re.finditer(motif_souple(PREFIXE), texte))):
        fin = m.end() + 2 * FENETRE_POINTEUR
        texte = texte[:m.end()] + texte[m.end():fin].replace(TABLE, "") + texte[fin:]
    return _avec(arbre, KICKOFF_SKILL, texte)


def gemini_cause_profil_d_abord(arbre: Arbre) -> Arbre:
    cause = par_hote(lignes_table(arbre[TABLE] or ""))["gemini"][5]
    return muter_champ(arbre, "gemini", 5, " ; ".join(reversed(cause.split(" ; "))))


def hote_non_p(arbre: Arbre) -> str:
    paralleles = hotes_paralleles(par_hote(lignes_table(arbre[TABLE] or "")))
    return next(NOMS[h] for h in HOTES if h != "claude" and h not in paralleles)


def _ajout_non_p(chemin: str, jeton: str, ancre: str, liaison: str) -> Callable[[Arbre], Arbre]:
    return lambda a: dans_fenetre(a, chemin, jeton, motif_souple(ancre), f"{ancre} {hote_non_p(a)} {liaison}")


MUTANTS: list[tuple[str, str, Callable[[Arbre], Arbre]]] = [
    ("P1", "antigravity-ecrit-hote-absent", lambda a: muter_champ(a, "antigravity", 1, "hote-absent")),
    ("P1", "claude-source-retiree", lambda a: muter_champ(a, "claude", 5, "—")),
    ("P1", "ligne-kimi-retiree", lambda a: retirer_ligne_table(a, "kimi")),
    ("P1", "codex-cause-non-neutre", lambda a: muter_champ(a, "codex", 5, "aucune session")),
    ("P1", "kimi-sonde-retiree", lambda a: muter_champ(a, "kimi", 5, "hôte absent du poste de mesure (which)")),
    ("P2", "codex-p-sans-chiffres", lambda a: muter_champ(a, "codex", 1, "mesure-parallele")),
    *[("P3", f"ligne-{h}-retiree-def-{d}", (lambda a, h=h, d=d: retirer_de_def(a, h, d)))
      for h, porteuses in PORTEUSES.items() for d in porteuses],
    ("P4", "readme-renvoi-retire", lambda a: muter_readme(a, "]()")),
    ("P4", "readme-renvoi-double", lambda a: muter_readme(a, f"]({TABLE}) and [table]({TABLE})")),
    ("P4", "readme-table-recopiee", recopier_table_readme),
    *[("P5", f"hote-non-p-ajoute-{Path(c).parent.name or 'racine'}-{Path(c).stem}",
       _ajout_non_p(c, j, ancre, "et sur" if casse else "and on")) for c, j, ancre, casse in PORTEE],
    *[("P5", f"portee-retiree-{Path(c).parent.name or 'racine'}-{Path(c).stem}",
       (lambda a, c=c, j=j, ancre=ancre: dans_fenetre(a, c, j, motif_souple(ancre), "")))
      for c, j, ancre, _ in PORTEE],
    ("P6", "kickoff-skill-pointeur-portee-retire",
     lambda a: dans_fenetre(a, KICKOFF_SKILL, PORTEE[2][1], re.escape(TABLE), "")),
    ("P6", "kickoff-skill-pointeur-coverage-retire", pointeur_coverage_retire),
    ("P6", "kickoff-cmd-pointeur-retire",
     lambda a: dans_fenetre(a, KICKOFF_CMD, PORTEE[3][1], re.escape(TABLE), "")),
    ("P7", "gemini-sans-os-arch", lambda a: muter_champ(a, "gemini", 3, "—")),
    ("P7", "gemini-cause-ouvre-par-le-profil", gemini_cause_profil_d_abord),
]
IDS = [f"{code}-{nom}" for code, nom, _ in MUTANTS]
assert not any("synth" in i or "vivant" in i for i in IDS), "un id de mutant ne choisit jamais un jeu"


def codes(arbre: Arbre, admis: Callable[[str], bool] = statut_admis) -> set[str]:
    return {code for code, _ in violations(arbre, admis)}


def _rougit(base: Arbre, code: str, muter: Callable[[Arbre], Arbre]) -> None:
    assert violations(base) == [], "base rouge : un mutant ne se juge que sur une base verte"
    mute = relire(muter(base))
    assert mute != base, "mutation sans effet : un échec, jamais un vert (L-00000161)"
    assert code in codes(mute), f"{code} reste vert sous le mutant : {violations(mute)}"


# ---------------------------------------------------------------------------
# Jeu `synth` — joué par le dev de D2
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def synth() -> Arbre:
    return arbre_synthetique()


def test_synth_non_vide(synth: Arbre) -> None:
    assert all(synth[c] for c in (*SURFACES_D2, *SURFACES_AUTRES)), [c for c, t in synth.items() if not t]
    assert len(lignes_table(synth[TABLE] or "")) == 6
    assert sum(ligne.count(f"]({TABLE})") for ligne in lignes_readme(synth[README] or "") or []) == 1
    assert all(fenetre(synth[c] or "", j) for c, j, _, _ in PORTEE)


def test_synth_base_verte(synth: Arbre) -> None:
    assert violations(synth) == []


@pytest.mark.parametrize(("code", "nom", "muter"), MUTANTS, ids=IDS)
def test_synth_mutant_rougit(synth: Arbre, code: str, nom: str, muter: Callable[[Arbre], Arbre]) -> None:
    _rougit(synth, code, muter)


def test_synth_vocabulaire_sans_prefixe() -> None:
    assert not [(a, b) for a in STATUTS for b in STATUTS if a != b and b.startswith(a)]
    assert not statut_admis("non-mesure") and statut_admis("pas-mesure")


def _hors_vocabulaire(arbre: Arbre, admis: Callable[[str], bool] = statut_admis) -> list[str]:
    return [m for code, m in violations(arbre, admis) if code == "P1" and "hors vocabulaire" in m]


def test_synth_p1_egalite_exacte(synth: Arbre) -> None:
    """Mutant de CODE : la comparaison par préfixe. MESURÉ (2026-10-14) : `non-mesure` n'est PAS
    un préfixe de `non-mesurable` (les deux partagent `non-mesur`) — la prémisse C40 du plan est
    fausse à la lettre ; le mutant se juge donc sur une troncature réelle, `non-mesur`, que la
    comparaison par préfixe admet et que l'égalité exacte refuse, et `non-mesure` reste refusé."""
    def par_prefixe(statut: str) -> bool:
        return any(v.startswith(statut) for v in STATUTS)

    assert not "non-mesurable".startswith("non-mesure")
    assert _hors_vocabulaire(relire(muter_champ(synth, "codex", 1, "non-mesure"))), "`non-mesure` doit être refusé"
    tronque = relire(muter_champ(synth, "codex", 1, "non-mesur"))
    assert _hors_vocabulaire(tronque), "l'égalité exacte doit refuser une troncature"
    assert not _hors_vocabulaire(tronque, par_prefixe), "le mutant par préfixe doit l'admettre : sinon ce cas ne prouve rien"


def test_synth_p2_admet_un_p_complet_et_refuse_un_seuil_manque(synth: Arbre) -> None:
    """Contrôle positif de P2 (il peut être vert) et son seuil (29 s n'est pas un P)."""
    complet = muter_champ(muter_champ(synth, "codex", 1, "mesure-parallele"), "codex", 6, "M1 45,52 ; M2 — ; M1-bis ok")
    assert "P2" not in codes(relire(complet))
    court = muter_champ(complet, "codex", 6, "M1 45,29 ; M2 — ; M1-bis ok")
    assert "P2" in codes(relire(court))
    sans_bis = muter_champ(complet, "codex", 6, "M1 45,52 ; M2 — ; M1-bis ko")
    assert "P2" in codes(relire(sans_bis))


def test_synth_p5_admet_un_hote_p_nomme(synth: Arbre) -> None:
    """Un hôte passé P et nommé sur les quatre surfaces : P5 reste vert (le témoin n'est pas figé sur claude)."""
    avec_p = muter_champ(muter_champ(synth, "codex", 1, "mesure-parallele"), "codex", 6, "M1 45,52 ; M2 — ; M1-bis ok")
    for chemin, jeton, ancre, casse in PORTEE:
        avec_p = dans_fenetre(avec_p, chemin, jeton, motif_souple(ancre) + r"\s+Claude\s+Code(\s+(?:seul|only))?",
                              f"{ancre} Claude Code {'et sur' if casse else 'and on'} Codex")
    assert "P5" not in codes(relire(avec_p)), violations(relire(avec_p))


def test_synth_surface_absente_rougit(synth: Arbre) -> None:
    assert "P0" in codes(_avec(synth, DEFS["gemini"], None))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Jeu `vivant` — l'arbre réel ; vert après les quatre fusions seulement (étape 6)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def vivant() -> Arbre:
    return charger(ROOT)


def test_vivant_non_vide(vivant: Arbre) -> None:
    assert all(vivant[c] for c in (*SURFACES_D2, *SURFACES_AUTRES)), [c for c, t in vivant.items() if not t]
    assert len(lignes_table(vivant[TABLE] or "")) == 6


def test_vivant_base_verte(vivant: Arbre) -> None:
    assert violations(vivant) == []


@pytest.mark.parametrize(("code", "nom", "muter"), MUTANTS, ids=IDS)
def test_vivant_mutant_rougit(vivant: Arbre, code: str, nom: str, muter: Callable[[Arbre], Arbre]) -> None:
    _rougit(vivant, code, muter)


def test_readme_bancs_mandat_renvoie_a_l_ancre_entiere() -> None:
    readme = (ROOT / README).read_text(encoding="utf-8")
    hook = (ROOT / ".claude/hooks/bancs-mandat.sh").read_text(encoding="utf-8")
    assert re.search(r'^anchor = "BANCS-BORNES \([^"\n]+\)"$', hook, re.MULTILINE)
    phrase = readme.split("`bancs-mandat` judges", 1)[1].split(": the mandate", 1)[0]
    assert "the exact value of `anchor` defined in `.claude/hooks/bancs-mandat.sh`" in phrase
    assert "the full string, not merely `BANCS-BORNES`" in phrase
