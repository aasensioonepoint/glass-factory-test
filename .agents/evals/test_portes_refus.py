"""The gate refusal sheet `.agents/ref/PORTES_REFUS.md` cites what the code says (A6).

WHY. Retex of the 16/10 hackathon: « the models fight the gates ». The sheet gives,
per gate, the refusal text, its cause, its remedy and its traced exit. A sheet that
quotes a refusal the code no longer prints is worse than no sheet (L-00000111): the
reader trusts it and stops reading the code. So every `refus:` is checked here as a
LITERAL substring of the source it cites — the code changes, this suite goes red and
names the section.

WHAT IS PROVEN, AND WHAT IS NOT.
  (a) the 21 gate titles are WRITTEN here (never globbed) and equal the sheet's
      sections, both ways, beside the two header sections (the bound, C5);
  (b) each gate section carries the six keys, nothing else, and its `où:` names
      the arming marker (C5);
  (c) each `refus:` is a segment of ONE literal of its `source:` (C4: a substring
      check cannot cross a closing quote and a line break), of at least
      `PLANCHER` characters, and each source is a file TRACKED by git; a cited
      function or constant exists in a cited source. A `.py` source is compared
      by its string CONSTANTS read by `ast` — docstrings and bare string
      statements excluded, fixed parts of f-strings included — so a refusal kept
      alive by a docstring alone goes red; a shell source, by its text minus its
      `#` lines;
  (d) each `--sans-…` / `--pas-un-defaut` the sheet cites is declared by the CLI
      (`tasks_cli.py` or `specs.py`) as a quoted flag;
  (e) the Claude Code pointer opens on `---` at line 1, its `name:` is its
      directory, and it cites the sheet, which exists;
  (f) the two cross-references cite the sheet, BEFORE the « Détail déplacé »
      section (C1).
It does NOT prove a cause or a remedy is right: the closing review re-reads them
against the code. Nor that Claude Code DISCOVERS the pointer — only a fresh session
listing `portes-refus-pointer` proves that (measure of T-00000402).

THE WITNESSES ARE PERMANENT. Each check is a pure function over text; the
`test_temoin_*` tests feed it a mutant (a refusal changed by one character, a
section removed, a missing or untracked source, a diverging `name:`, a missing
key, an invented exit, a moved cross-reference, a refusal under the floor) and
require a fault — a check that cannot go red is not a check (L-00000186).

TRAVELS: its sources travel too (`.template-exclude` strips none of them); a source
stripped later would turn this red at the adopter's — named, not hidden.
"""

from __future__ import annotations

import ast
import re
import subprocess
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FICHE_REL = ".agents/ref/PORTES_REFUS.md"
POINTEUR_REL = ".claude/skills/portes-refus-pointer/SKILL.md"
RENVOIS = (
    ".agents/skills/task-board/SKILL.md",
    ".agents/skills/verification-discipline/SKILL.md",
)
CLIS = (".agents/bin/tasks_cli.py", ".agents/bin/specs.py")
DETAIL_DEPLACE = "## Détail déplacé d'AGENTS.md"

# WRITTEN here, never derived from the sheet (L-00000261).
EN_TETE = (
    "Avant de rejouer : trois réflexes",
    "BORNE — ce que cette fiche ne dit pas",
)
PORTES = (
    "revendication",
    "porte et push",
    "commit-msg",
    "SAST",
    "SCA",
    "secrets",
    "chemins protégés",
    "safe-bash",
    "audit des skills",
    "affirmation",
    "mesure",
    "chaîne de plan",
    "amont d'abord",
    "critique de clôture",
    "cible",
    "chrono",
    "voie directe",
    "fournée",
    "lots",
    "garde de kickoff",
    "limite de tâche",
)
CLES = ("où", "refus", "source", "cause", "remède", "sortie tracée")
PLANCHER = 20
MARQUEUR = "marqueur d'armement"

LIGNE_CLE = re.compile(r"^- (où|refus|source|cause|remède|sortie tracée): (.+)$")
REFUS = re.compile(r"^« (.+) »$")
CHEMIN = re.compile(r"`([^`\s]+/[^`\s]+)`")
IDENT = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)`")
SORTIE = re.compile(r"--(?:sans-[a-z]+(?:-[a-z]+)*|pas-un-defaut)\b")


def lire(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def sections(texte: str) -> tuple[list[str], dict[str, list[str]]]:
    """`(titres dans l'ordre, {titre: lignes du corps})` — `## ` seulement."""
    titres: list[str] = []
    corps: dict[str, list[str]] = {}
    courant: str | None = None
    for ligne in texte.splitlines():
        if ligne.startswith("## "):
            courant = ligne[3:].strip()
            titres.append(courant)
            corps.setdefault(courant, [])
        elif courant is not None:
            corps[courant].append(ligne)
    return titres, corps


def cles(lignes: list[str]) -> tuple[list[tuple[str, str]], list[str]]:
    """`(paires (clé, valeur), lignes non vides hors grammaire)`."""
    paires: list[tuple[str, str]] = []
    hors: list[str] = []
    for ligne in lignes:
        if not ligne.strip():
            continue
        m = LIGNE_CLE.match(ligne)
        if m:
            paires.append((m.group(1), m.group(2)))
        else:
            hors.append(ligne)
    return paires, hors


def fautes_titres(texte: str) -> list[str]:
    titres, _ = sections(texte)
    fautes = [f"section en double : {t!r}" for t in sorted({t for t in titres if titres.count(t) > 1})]
    fautes += [f"en-tête absent : {t!r}" for t in EN_TETE if t not in titres]
    lues = set(titres) - set(EN_TETE)
    fautes += [f"porte absente de la fiche : {t!r}" for t in PORTES if t not in lues]
    fautes += [f"section hors de PORTES : {t!r}" for t in sorted(lues - set(PORTES))]
    return fautes


def fautes_cles(texte: str) -> list[str]:
    _, corps = sections(texte)
    fautes: list[str] = []
    for titre in PORTES:
        if titre not in corps:
            continue
        paires, hors = cles(corps[titre])
        fautes += [f"{titre} : ligne hors grammaire {h!r}" for h in hors]
        noms = [c for c, _ in paires]
        for cle in CLES:
            n = noms.count(cle)
            if cle == "refus" and n < 1:
                fautes.append(f"{titre} : aucune clé refus:")
            elif cle != "refus" and n != 1:
                fautes.append(f"{titre} : clé {cle}: présente {n} fois, attendu 1")
        if not any(c == "où" and MARQUEUR in v for c, v in paires):
            fautes.append(f"{titre} : où: ne nomme pas le {MARQUEUR}")
    return fautes


def litteraux(chemin: str, source: str) -> list[str]:
    """Ce qu'une source peut IMPRIMER, à comparer au `refus:` (C4) : pour un `.py`,
    ses constantes de chaîne lues par `ast` — une chaîne posée seule en instruction
    (docstring comprise) n'en est pas, les parties fixes d'une f-string en sont ; pour
    une source shell, son texte privé de ses lignes `#`. Lève `SyntaxError`."""
    if chemin.endswith(".py"):
        arbre = ast.parse(source)
        muettes = {id(n.value) for n in ast.walk(arbre)
                   if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
                   and isinstance(n.value.value, str)}
        return [n.value for n in ast.walk(arbre)
                if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in muettes]
    return ["\n".join(l for l in source.splitlines() if not l.lstrip().startswith("#"))]


def fautes_refus(texte: str, lire_source: Callable[[str], str], suivis: set[str]) -> list[str]:
    _, corps = sections(texte)
    fautes: list[str] = []
    for titre in PORTES:
        if titre not in corps:
            continue
        paires, _ = cles(corps[titre])
        chemins = [c for cle, v in paires if cle == "source" for c in CHEMIN.findall(v)]
        idents = [i for cle, v in paires if cle == "source" for i in IDENT.findall(v)]
        if not chemins:
            fautes.append(f"{titre} : source: ne cite aucun chemin")
        textes: list[str] = []
        imprimes: list[str] = []
        for chemin in chemins:
            if chemin not in suivis:
                fautes.append(f"{titre} : source {chemin} non suivie par git")
            try:
                textes.append(lire_source(chemin))
                imprimes += litteraux(chemin, textes[-1])
            except (OSError, SyntaxError) as exc:
                fautes.append(f"{titre} : source {chemin} illisible ({type(exc).__name__})")
        for ident in idents:
            if not any(re.search(rf"^\s*(?:def {ident}\(|{ident} = )", t, re.MULTILINE) for t in textes):
                fautes.append(f"{titre} : {ident} n'est défini dans aucune source citée")
        for cle, valeur in paires:
            if cle != "refus":
                continue
            m = REFUS.match(valeur)
            if not m:
                fautes.append(f"{titre} : refus: hors de la forme « … » : {valeur!r}")
                continue
            refus = m.group(1)
            if len(refus) < PLANCHER:
                fautes.append(f"{titre} : refus de {len(refus)} caractère(s), plancher {PLANCHER} : {refus!r}")
            if not any(refus in t for t in imprimes):
                fautes.append(f"{titre} : refus absent de ses sources, au littéral : {refus!r}")
    return fautes


def fautes_sorties(texte: str, texte_clis: str) -> list[str]:
    citees = sorted(set(SORTIE.findall(texte)))
    return [f"sortie tracée {s} citée, absente des CLI" for s in citees if f'"{s}"' not in texte_clis]


def fautes_pointeur(texte: str, repertoire: str, fiche_existe: bool) -> list[str]:
    lignes = texte.splitlines()
    fautes: list[str] = []
    if not lignes or lignes[0] != "---":
        fautes.append("le pointeur n'ouvre pas sur `---` en ligne 1")
    fin = next((i for i, l in enumerate(lignes[1:], 1) if l == "---"), None)
    entete = lignes[1:fin] if fin else []
    noms = [l.split(":", 1)[1].strip() for l in entete if l.startswith("name:")]
    if noms != [repertoire]:
        fautes.append(f"name: {noms!r} ≠ répertoire {repertoire!r}")
    if FICHE_REL not in texte:
        fautes.append(f"le pointeur ne cite pas {FICHE_REL}")
    if not fiche_existe:
        fautes.append(f"{FICHE_REL} n'existe pas")
    return fautes


def fautes_renvoi(texte: str, rel: str) -> list[str]:
    pos = texte.find(FICHE_REL)
    if pos < 0:
        return [f"{rel} ne cite pas {FICHE_REL}"]
    detail = texte.find(DETAIL_DEPLACE)
    if detail >= 0 and pos > detail:
        return [f"{rel} cite {FICHE_REL} APRÈS « {DETAIL_DEPLACE} » (C1)"]
    return []


def suivis_par_git(chemins: list[str]) -> set[str]:
    sortie = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z", "--", *chemins],
        capture_output=True, check=True,
    ).stdout.decode("utf-8")
    return {c for c in sortie.split("\0") if c}


def chemins_sources(texte: str) -> list[str]:
    return sorted({c for l in texte.splitlines() if l.startswith("- source: ") for c in CHEMIN.findall(l)})


FICHE = lire(FICHE_REL)


# --- les contrôles sur l'arbre réel ---------------------------------------------------

def test_portes_ecrites_et_closes() -> None:
    assert len(PORTES) == 21 and len(set(PORTES)) == 21
    assert fautes_titres(FICHE) == []


def test_six_cles_par_section() -> None:
    assert fautes_cles(FICHE) == []


def test_chaque_refus_est_un_litteral_de_sa_source() -> None:
    nb = sum(1 for l in FICHE.splitlines() if l.startswith("- refus: "))
    assert nb >= len(PORTES), f"{nb} refus: pour {len(PORTES)} portes — plancher non tenu"
    sources = chemins_sources(FICHE)
    assert sources, "aucune source: lue — le parseur est cassé"
    assert fautes_refus(FICHE, lire, suivis_par_git(sources)) == []


def test_revendication_transfert_et_borne_des_hotes() -> None:
    _, corps = sections(FICHE)
    texte = " ".join(corps["revendication"])
    for attendu in ("REVENDICATION : reprise réservée au terminal du pilote, non lancé par un agent",
                    "REVENDICATION: ancien pilote a poussé après reprise", "clone non fusionné",
                    "REVENDICATION: prise levée par reprise encore publiée", "Deux avis, jamais un refus",
                    "stdin et stderr TTY", "saisie exacte de l'identifiant", "jamais de `--reprise` automatique",
                    "`--sans-revendication` (option refusée)", "winpty bash .agents/pyrun.sh .agents/bin/tasks.py",
                    "les hooks du kit qui posent `AGENTS_HOOK_HOST` (Codex, Kimi, Copilot)",
                    "Codex, Gemini et Kimi sans marqueur", "TTY + saisie en une commande"):
        assert attendu in texte, attendu
    assert "--sans-revendication \"<pourquoi>\"" not in texte


COPILOT_MARQUEUR = ("Copilot CLI pose `COPILOT_AGENT_SESSION_ID` et `COPILOT_CLI` dans le shell de l'agent "
                    "(mesuré, 1.0.96) : ce marqueur refuse la reprise")
COPILOT_FAUX_POSITIF = "`COPILOT_CLI` est hérité par un shell que le pilote lance depuis Copilot CLI (échappement `!` compris)"
ANCIENNES_BORNES = ("Codex, Gemini, Copilot et Kimi sans marqueur", "Codex, Gemini, Copilot, Kimi sans marqueur")


def fautes_marqueur_copilot(texte: str) -> list[str]:
    """Le marqueur Copilot mesuré est dit, son faux positif aussi, et l'ancienne borne « Copilot sans marqueur » a disparu."""
    fautes = [f"absent : {p}" for p in (COPILOT_MARQUEUR, COPILOT_FAUX_POSITIF, "Gemini et Kimi sans marqueur")
              if p not in texte]
    fautes += [f"ancienne borne : {p}" for p in ANCIENNES_BORNES if p in texte]
    fautes += [f"lexique interdit : {m}" for m in ("couvert", "covered", "partout", "tous les hôtes") if m in texte]
    return fautes


def test_marqueur_copilot_mesure_dans_la_fiche_et_le_contrat() -> None:
    _, corps = sections(FICHE)
    assert fautes_marqueur_copilot(" ".join(corps["revendication"])) == []
    contrat = lire(".agents/ref/TASKS_CLI_CONTRACT.md")
    section = contrat.split("- **Propriété et revendication Git** :", 1)[1].split("\n\n", 1)[0]
    assert fautes_marqueur_copilot(section) == []


def test_temoin_marqueur_copilot_rougit_sur_l_ancienne_phrase() -> None:
    _, corps = sections(FICHE)
    texte = " ".join(corps["revendication"])
    mutant = texte.replace("Codex, Gemini et Kimi sans marqueur", "Codex, Gemini, Copilot et Kimi sans marqueur")
    assert mutant != texte
    assert "ancienne borne : Codex, Gemini, Copilot et Kimi sans marqueur" in fautes_marqueur_copilot(mutant)
    assert fautes_marqueur_copilot(texte.replace(COPILOT_MARQUEUR, "")) != []


def test_sorties_tracees_declarees_par_les_cli() -> None:
    citees = set(SORTIE.findall(FICHE))
    assert {"--sans-chaine", "--sans-binome", "--sans-cible", "--pas-un-defaut"} <= citees
    assert fautes_sorties(FICHE, "".join(lire(c) for c in CLIS)) == []


def test_pointeur_claude_code() -> None:
    assert fautes_pointeur(lire(POINTEUR_REL), Path(POINTEUR_REL).parent.name,
                           (ROOT / FICHE_REL).is_file()) == []


def test_renvois_citent_la_fiche() -> None:
    for rel in RENVOIS:
        assert fautes_renvoi(lire(rel), rel) == []


# --- les témoins : chaque contrôle rougit sur un mutant -------------------------------

def _premier_refus(texte: str) -> str:
    m = re.search(r"^- refus: « (.+) »$", texte, re.MULTILINE)
    assert m
    return m.group(1)


def _sources_reelles() -> tuple[Callable[[str], str], set[str]]:
    return lire, suivis_par_git(chemins_sources(FICHE))


def test_temoin_refus_mute_d_un_caractere() -> None:
    refus = _premier_refus(FICHE)
    mutant = FICHE.replace(f"« {refus} »", f"« {refus[:-1]}{'Y' if refus[-1] == 'Z' else 'Z'} »", 1)
    fautes = fautes_refus(mutant, *_sources_reelles())
    assert any("absent de ses sources" in f and f.startswith("porte et push") for f in fautes), fautes


def test_temoin_refus_sous_le_plancher() -> None:
    refus = _premier_refus(FICHE)
    mutant = FICHE.replace(f"« {refus} »", f"« {refus[:PLANCHER - 1]} »", 1)
    assert any("plancher" in f for f in fautes_refus(mutant, *_sources_reelles()))


def test_temoin_section_retiree() -> None:
    debut = FICHE.index("## chrono\n")
    fin = FICHE.index("\n## ", debut + 1) + 1
    mutant = FICHE[:debut] + FICHE[fin:]
    assert "porte absente de la fiche : 'chrono'" in fautes_titres(mutant)


def test_temoin_section_inconnue() -> None:
    assert any("hors de PORTES" in f for f in fautes_titres(FICHE + "\n## porte inventée\n"))


def test_temoin_source_inexistante() -> None:
    mutant = FICHE.replace("- source: `.agents/bin/plan_lots.py`", "- source: `.agents/bin/nexiste_pas.py`", 1)
    assert mutant != FICHE
    fautes = fautes_refus(mutant, *_sources_reelles())
    assert any(f.startswith("lots : source .agents/bin/nexiste_pas.py") for f in fautes), fautes


def test_temoin_source_non_suivie() -> None:
    lecture, suivis = _sources_reelles()
    fautes = fautes_refus(FICHE, lecture, suivis - {".agents/bin/plan_lots.py"})
    assert "lots : source .agents/bin/plan_lots.py non suivie par git" in fautes


def test_temoin_identifiant_inconnu() -> None:
    mutant = FICHE.replace("`mesure_refusal`", "`mesure_refusal_disparue`", 1)
    assert any("mesure_refusal_disparue" in f for f in fautes_refus(mutant, *_sources_reelles()))


def test_temoin_cle_retiree_et_marqueur_tu() -> None:
    _, corps = sections(FICHE)
    cause = next(l for l in corps["cible"] if l.startswith("- cause: "))
    assert "cible : clé cause: présente 0 fois, attendu 1" in fautes_cles(FICHE.replace(cause + "\n", "", 1))
    ou = next(l for l in corps["cible"] if l.startswith("- où: "))
    tu = FICHE.replace(ou, ou.replace(MARQUEUR, "armement"), 1)
    assert f"cible : où: ne nomme pas le {MARQUEUR}" in fautes_cles(tu)


def test_temoin_sortie_inventee() -> None:
    clis = "".join(lire(c) for c in CLIS)
    assert fautes_sorties(FICHE + "\n--sans-inventee\n", clis) == ["sortie tracée --sans-inventee citée, absente des CLI"]


def test_temoin_name_divergent() -> None:
    texte = lire(POINTEUR_REL)
    mutant = texte.replace("name: portes-refus-pointer", "name: portes-refus", 1)
    assert mutant != texte
    assert any(f.startswith("name:") for f in fautes_pointeur(mutant, "portes-refus-pointer", True))
    assert any("ligne 1" in f for f in fautes_pointeur("\n" + texte, "portes-refus-pointer", True))


def test_temoin_renvoi_absent_ou_deplace() -> None:
    rel = RENVOIS[0]
    texte = lire(rel)
    assert fautes_renvoi(texte.replace(FICHE_REL, ".agents/ref/AILLEURS.md"), rel)
    ligne = next(l for l in texte.splitlines() if FICHE_REL in l)
    deplace = texte.replace(ligne + "\n", "", 1) + "\n" + ligne + "\n"
    assert any("(C1)" in f for f in fautes_renvoi(deplace, rel))


def _lecture_mutee(cible: str, avant: str, apres: str) -> Callable[[str], str]:
    def lecture(rel: str) -> str:
        texte = lire(rel)
        if rel == cible:
            assert avant in texte, f"site du mutant introuvable dans {cible} : {avant!r}"
            return texte.replace(avant, apres)
        return texte
    return lecture


def test_temoin_refus_qui_ne_survit_que_dans_une_docstring() -> None:
    """Mutant `tasks_etats.py` « COURANT » → « ACTUEL » : le refus ne vit plus que
    dans la docstring de `tasks_gardes.py` — le code ne l'imprime plus, (c) rougit."""
    _, suivis = _sources_reelles()
    lecture = _lecture_mutee(".agents/bin/tasks_etats.py",
                             "l'état COURANT des fichiers de reprise", "l'état ACTUEL des fichiers de reprise")
    assert "l'état COURANT des fichiers de reprise" in lire(".agents/bin/tasks_gardes.py")
    fautes = fautes_refus(FICHE, lecture, suivis)
    assert any(f.startswith("critique de clôture : refus absent") and "COURANT" in f for f in fautes), fautes


def test_temoin_limite_litteral_change_d_un_caractere() -> None:
    """T-01M54GEMCH3JWA95G61N2J70KS : `LIMITE_REFUS` changé d'un caractère dans `tasks_requetes.py`
    — la fiche cite un refus que le code n'imprime plus, (c) rougit sur « limite de tâche »."""
    _, suivis = _sources_reelles()
    lecture = _lecture_mutee(".agents/bin/tasks_requetes.py",
                             'LIMITE_REFUS = "dépasse sa limite et LIMITE_ARRET est armé"',
                             'LIMITE_REFUS = "dépasse sa limite et LIMITE_ARRET est arme"')
    fautes = fautes_refus(FICHE, lecture, suivis)
    assert any(f.startswith("limite de tâche : refus absent") for f in fautes), fautes


def test_temoin_refus_shell_qui_ne_survit_que_dans_un_commentaire() -> None:
    _, suivis = _sources_reelles()
    refus = "AFFIRMATION DURABLE SANS REVUE CRITIQUE — refus de fin de tour."
    lecture = _lecture_mutee(".claude/hooks/affirmation-guard.sh", f'    "{refus}', f'    # "{refus}')
    fautes = fautes_refus(FICHE, lecture, suivis)
    assert any(f.startswith("affirmation : refus absent") for f in fautes), fautes
