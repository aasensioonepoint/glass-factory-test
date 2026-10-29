"""LE CARDINAL DU ROSTER EST JUGÉ CONTRE LE ROSTER DÉRIVÉ — T-00000565 (BK-539), plan rév. 3.

CE QU'IL JUGE. Toute phrase de COMPTAGE du roster, dans tout fichier SUIVI du dépôt (`git ls-files`),
vaut le roster DÉRIVÉ de `.claude/agents/*.md` : aucun cardinal de roster n'est écrit dans ce fichier. Un
nombre qui ne le vaut pas est un écart, et TOUS les écarts sont listés en un seul run (« fichier:ligne —
phrase »). Un fichier NEUF est jugé par défaut : on SOUSTRAIT des exemptions nommées, on n'ÉNUMÈRE pas des
surfaces. Ce filet JUGE des copies écrites à la main ; il ne les DÉRIVE pas : la génération reste à faire.
BORNE : un fichier suivi ILLISIBLE (non UTF-8, absent du disque) est sauté SANS SIGNAL — au 2026-10-03,
10 `.woff2` et 1 `.pdf` ; un `.md` mal encodé le serait aussi, et aucun témoin ne le dit.

OÙ IL JUGE. Le dépôt du KIT seul (marqueur `.agents/IS_THE_KIT`) : chez l'adoptant il jugerait SA prose.
Le filet qui VOYAGE reste `core-scripts/host_sync.test.sh` section 5 (liste de surfaces, motif plus étroit).

UN TOTAL NE PROUVE RIEN SUR SES MEMBRES (L-00000232, précédent T-00000580 `SURFACE MUETTE`) : en plus du
plancher global (R5), chaque surface NOMMÉE dans `PLANCHERS` doit rendre AU MOINS le nombre de phrases
mesuré le jour de la livraison. Ce sont des TÉMOINS ; la population jugée reste l'arbre entier.

LES FORMES QU'IL LIT (liste BORNÉE, L-00000187) : le texte est NORMALISÉ d'abord (balises HTML -> espace,
`**` retirés, espace insécable écrit en entité -> espace) — c'est ce qui lui fait lire une tuile
`<b>N</b><span>agents</span>` comme « N agents ». Puis : `N` + (agents, subagents, sous-agents, defs,
défs, rôles) avec échappement des qualifiants POSTPOSÉS (une sous-population juste) ; `zéro déf sur N` ;
`N/N loaded` ; la cellule de tableau `| a sur N |` ; `N au roster` ; `roster reste à N` et ses quatre
variantes ; `N − a − b =` (premier opérande) ; un cardinal en LETTRES (R2 : « écris le chiffre, ou rien »).

CE QU'IL NE LIT PAS, et la liste n'est pas close : les formes ci-dessous sont assertées non vues par un
témoin, les autres ne le sont pas. Un nombre et son nom sur DEUX lignes ; les multiples (155 = roster x 5) ;
la répartition d'un total (« 20 core + 8 security + 3 »), dont seul le total est jugé ; `N <adjectif>
agent defs` ; `N définitions` ; `N au relevé du <date>` ; les opérandes d'une soustraction après le
premier ; un nombre collé à un caractère de mot, un point, une virgule, une barre, un signe de
multiplication, une étoile seule ou un tiret ; un nombre dans un ATTRIBUT de balise (la balise entière
est retirée avant lecture).

EXEMPTIONS NOMMÉES, chacune avec sa raison, et chacune doit couvrir AU MOINS UNE phrase (R4) : une
exemption qui n'exempte rien est décorative. R4 est jugée sur un corpus qui plante une phrase par entrée,
et sur l'arbre réel pour toutes les classes SAUF HISTORIQUE, dont le contenu est réécrit par le pipeline
(board, exports, reprises, journal) et non par l'auteur d'une exemption ; l'étendue de chaque préfixe
HISTORIQUE est tenue par ses voisins jugés (W19).
"""
from __future__ import annotations

import functools
import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
# Marqueur d'identité du kit, retiré par `sync_template.py` (strip: .agents/IS_THE_KIT).
# adopting-tree: son absence EST le signal « projet adoptant » : ce filet y saute EN ENTIER.
EST_LE_KIT = (ROOT / ".agents" / "IS_THE_KIT").is_file()
pytestmark = pytest.mark.skipif(
    not EST_LE_KIT,
    reason="SAUT ANNONCE : marqueur `.agents/IS_THE_KIT` absent (projet adoptant) — rien n'est jugé ici",
)

# OÙ VIT LE PAQUET `cadre` (T-01M5BXTPQE3JZV3KZA6WD9P5XC, lot L) : le résolveur `vendor_paths.py`, chargé PAR
# CHEMIN, désigne `.agents/vendor/cadre` ou `src/cadre` ; ses données se jugent là où il vit. Les deux présents :
# le neuf gagne, et l'ancien, OMBRE jamais exécutée, n'est pas une surface vivante (sautée comme l'HISTORIQUE).
_SPEC_VENDOR = importlib.util.spec_from_file_location(
    "_roster_cardinal_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
assert _SPEC_VENDOR is not None and _SPEC_VENDOR.loader is not None
_VENDOR = importlib.util.module_from_spec(_SPEC_VENDOR)
sys.modules[_SPEC_VENDOR.name] = _VENDOR
_SPEC_VENDOR.loader.exec_module(_VENDOR)


def paquet_cadre(racine: Path) -> str:
    """Le dossier du paquet `cadre` que la règle désigne, relatif à `racine` (l'ancien s'il manque)."""
    dossier = _VENDOR.dossier_paquet(racine, "cadre")
    if dossier is None:
        return _VENDOR.ANCIENS["cadre"].as_posix()
    return dossier.relative_to(Path(racine).resolve()).as_posix()


def ombre_cadre(racine: Path):
    """Le préfixe de l'ANCIEN `cadre` quand le neuf le masque (les deux présents), sinon `None`."""
    if _VENDOR.provenance(racine, "cadre") != _VENDOR.NEUF:
        return None
    ancien = _VENDOR.ANCIENS["cadre"]
    return ancien.as_posix() + "/" if (Path(racine) / ancien / "__init__.py").is_file() else None


# --- LES EXEMPTIONS NOMMÉES ----------------------------------------------------------------------
# HISTORIQUE : des rappels datés, jamais des affirmations vivantes (relevé de T-00000565, plans rév. 2-3).
# `docs/HISTORIQUE-0.1.0.md` : le journal d'avant la coupe de 0.1.0, figé par empreinte (T-01M4ZWNEDCJCNFF4HWQEWZX1J0).
HISTORIQUE = (".agents/state/", "runs/", "docs/tasks/", "docs/interne/", "retro/",
              "docs/design/20", "PLAN-ETAT-DETAIL.md", "docs/HISTORIQUE-0.1.0.md")
# COUVERT AILLEURS : un autre banc dérive déjà le compte du disque pour cette page.
COUVERT = {"CADRE/index.html": "core-scripts/cadre.test.sh section 2"}
# DÉCISION PILOTE du 2026-09-09 (host_sync.test.sh : « NE PAS REMETTRE sans arbitrage du pilote ») :
# `docs/usage.html`, « page de présentation, retirée du balayage par le pilote ». Entrée LEVÉE le
# 2026-10-13 : page refaite (876353b9), plus aucune phrase de comptage, l'exemption n'exemptait plus rien.
# La classe reste : une entrée qui n'exempte rien rougit R4 (test_aucune_exemption_decorative_…).
DECISION_PILOTE: dict = {}
# CODE : commentaires d'histoire et témoins synthétiques (« 99 agents ») ; seul C1 juge ces fichiers.
EXT_CODE = (".py", ".sh")
TITRE_INSTANTANE = "## Détail déplacé d'AGENTS.md"  # instantané MOT POUR MOT d'une section de routeur
# R4 sur l'arbre RÉEL : toutes les classes SAUF HISTORIQUE (voir la docstring) ; tenu par W10b, et par W10c pour DECISION PILOTE.
R4_REEL = ("COUVERT", "DECISION PILOTE", "CODE", "INSTANTANE")

# --- LES TÉMOINS DE PRÉSENCE : nombre de phrases lues par surface, MESURÉ à la livraison ------------
# Un plancher qui baisse est un cardinal retiré ou devenu illisible : si c'est voulu, baisse le plancher
# dans le même commit, en le disant ; sinon le motif ou la normalisation a perdu une forme.
# BORNE : la LISTE est tenue (une surface vivante hors liste rougit), les VALEURS ne le sont pas — chaque
# témoin est un `>=`, un plancher ABAISSÉ ne rougit rien ; seul le diff de la livraison les a vérifiées.
PLANCHERS = {
    ".agents/adopter-docs/README.md": 1,  # « Les 35 agents et les commandes ont chacun une seule source »
    ".agents/ref/MODEL_MODES.md": 13,
    "AGENTS.md": 1,  # « .claude/agents/ (35 agents) », reposée quand la phrase de l'ancienne commande de route est partie (host_sync.test.sh § 5-surfaces)
    "CADRE/architecture.html": 2,
    "GEMINI.md": 3,
    "QUICK-SETUP.md": 2,
    "README-CLAUDE.md": 2,
    "README-OTHER-HOSTS.md": 1,
    "README.md": 2,  # 3 → 2 : la phrase « the roster stays at 34 » est partie avec la ligne de commande retirée par T-01M5PCCHMWXTRCM5QJT8J5KNEH
    "contract.lock.json": 1,  # note de `format:def-agent`, tenue À LA MAIN (aucun outil ne l'écrit)
    f"{paquet_cadre(ROOT)}/data/capacites_hotes.json": 1,  # note gemini « le roster compte 35 depuis seo-specialist et reverse-engineer » (T-01M5BZC1Y0T36EHTZY9AKZ650F, T-01M5HEJYSJEYA8K3834FZVT60N ; 31 mesurées sous T-00000866)
}

# --- LES MOTIFS (liste bornée) -------------------------------------------------------------------
NOMS = r"(?:agents|subagents|sous-agents|defs|d[ée]fs|r[ôo]les|roles)"
POST = r"(?: (?:(?:Codex |Claude |Gemini |Copilot |Kimi )?pilot[ée]e?s|de s[ée]curit[ée]|d[ée]di[ée]e?s|de cl[ôo]ture))"
M1 = re.compile(r"(?<![\w.,/×*-])(\d+) (?:specialized |role-scoped |sp[ée]cialis[ée]s? )?" + NOMS
                + r"\b(" + POST + r")?", re.I)
M2A = re.compile(r"(?:z[ée]ro|aucune?|\d+) d[ée]fs? sur (\d+)\b", re.I)
M2B = re.compile(r"(?<![\w./])(\d+)/(\d+) (?:charg|loaded|d[ée]fs|defs)", re.I)
M2C = re.compile(r"\|\s*\d+ sur (\d+)\s*\|")
M4 = re.compile(r"(\d+) au roster|roster (?:reste à|stays at|is at|compte|counts) (\d+)", re.I)
M5 = re.compile(r"(?<![\d.])(\d+)(?: − \d+)+ = ")
M3 = re.compile(r"\b(?:vingt|trente|quarante|twenty|thirty|forty)[\w-]*(?: et[ -]une?)? " + NOMS + r"\b", re.I)
C1 = re.compile(
    r"len\(\s*(?:\w+\.)?(?:KIT_ROSTER|EXPECTED_MODELS|ROSTER|roster|claude|codex|gemini|agents|defs)\b[^)]*\)"
    r"\s*(?:==\s*len\([^)]*\)\s*)?==\s*(\d+)"
    r"|assertEqual\(\s*len\(\s*(?:\w+\.)?(?:KIT_ROSTER|EXPECTED_MODELS|ROSTER|roster|claude|codex|gemini|agents|defs)\b[^)]*\)\s*,\s*(\d+)")
TAG = re.compile(r"<[^>]*>")
NBSP = re.compile(r"&nbsp;|&#160;|&#xa0;", re.I)


def normalise(ligne: str) -> str:
    sans_balise = TAG.sub(" ", ligne)
    sans_gras = sans_balise.replace("**", "")
    return re.sub(r"\s+", " ", NBSP.sub(" ", sans_gras)).strip()


def phrases(texte: str, saute=frozenset()):
    """(ligne, motif, valeur ou None) pour chaque phrase de comptage ; `saute` = lignes ignorées."""
    trouvees = []
    for i, brut in enumerate(texte.splitlines(), 1):
        if i in saute:
            continue
        ligne = normalise(brut)
        for m in M1.finditer(ligne):
            if not m.group(2):
                trouvees.append((i, "M1", int(m.group(1)), m.group(0)))
        for motif, nom, g in ((M2A, "M2a", 1), (M2B, "M2b", 2), (M2C, "M2c", 1), (M5, "M5", 1)):
            for m in motif.finditer(ligne):
                trouvees.append((i, nom, int(m.group(g)), m.group(0)))
        for m in M4.finditer(ligne):
            trouvees.append((i, "M4", int(m.group(1) or m.group(2)), m.group(0)))
        for m in M3.finditer(ligne):
            trouvees.append((i, "M3", None, m.group(0)))
    return trouvees


def lignes_instantane(texte: str) -> frozenset:
    dedans, res = False, set()
    for i, ligne in enumerate(texte.splitlines(), 1):
        if ligne.startswith("## "):
            dedans = ligne.startswith(TITRE_INSTANTANE)
        elif dedans:
            res.add(i)
    return frozenset(res)


# --- LE CORPUS : les fichiers SUIVIS, sous un environnement git PURGÉ -----------------------------
def env_git() -> dict:
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def roster(racine: Path) -> list:
    return sorted(p.stem for p in (racine / ".claude" / "agents").glob("*.md"))


def suivis(racine: Path) -> list:
    sortie = subprocess.run(["git", "-C", str(racine), "ls-files", "-z"], capture_output=True,
                            check=True, env=env_git()).stdout
    return [p for p in sortie.decode("utf-8", "surrogateescape").split("\0") if p]


def lire(racine: Path, chemin: str):
    try:
        return (racine / chemin).read_text(encoding="utf-8")
    except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError):
        return None


def exemption(chemin: str):
    for prefixe in HISTORIQUE:
        if chemin.startswith(prefixe):
            return ("HISTORIQUE", prefixe)
    if chemin in COUVERT:
        return ("COUVERT", chemin)
    if chemin in DECISION_PILOTE:
        return ("DECISION PILOTE", chemin)
    if chemin.endswith(EXT_CODE):
        return ("CODE", chemin[chemin.rindex("."):])
    return None


def juger(racine: Path, soi: str = "", compte=None):
    """(ecarts, vivantes) : les écarts sont des lignes prêtes à afficher, TOUS à la fois.
    `compte`, s'il est donné, reçoit le nombre de phrases vivantes PAR FICHIER (témoins de présence)."""
    n = len(roster(racine))
    ecarts, vivantes = [], 0
    ombre = ombre_cadre(racine)
    for chemin in suivis(racine):
        if ombre and chemin.startswith(ombre):
            continue                      # l'ancien `cadre` masqué par le neuf : jamais exécuté, non jugé
        ex = exemption(chemin)
        if ex and ex[0] != "CODE":
            continue                      # HISTORIQUE sauté AVANT lecture ; COUVERT / PILOTE non jugés
        if chemin == soi:
            continue                      # le filet ne se juge pas lui-même (sa prose paraphrase)
        texte = lire(racine, chemin)
        if texte is None:
            continue
        if ex:                            # CODE : seul C1 juge, et seulement un `.py`
            if chemin.endswith(".py") and "len(" in texte:
                for i, ligne in enumerate(texte.splitlines(), 1):
                    for m in C1.finditer(ligne):
                        if int(m.group(1) or m.group(2)) == n:
                            ecarts.append(f"{chemin}:{i} — littéral « {m.group(0)} » : le roster en compte {n}, "
                                          "dérive-le (len(...) == len(...)), ne l'écris pas")
            continue
        saute = lignes_instantane(texte) if chemin.endswith("SKILL.md") else frozenset()
        for ligne, motif, valeur, extrait in phrases(texte, saute):
            vivantes += 1
            if compte is not None:
                compte[chemin] = compte.get(chemin, 0) + 1
            if valeur is None:
                ecarts.append(f"{chemin}:{ligne} — « {extrait} » : cardinal en LETTRES, écris le chiffre ou rien")
            elif valeur != n:
                ecarts.append(f"{chemin}:{ligne} — « {extrait} », le roster en compte {n}")
    return sorted(ecarts), vivantes


def entrees_nommees(classes=None) -> list:
    tout = ([("HISTORIQUE", p) for p in HISTORIQUE] + [("COUVERT", c) for c in COUVERT]
            + [("DECISION PILOTE", d) for d in DECISION_PILOTE] + [("CODE", e) for e in EXT_CODE]
            + [("INSTANTANE", TITRE_INSTANTANE)])
    return [e for e in tout if classes is None or e[0] in classes]


def exemptions_vides(racine: Path, classes=None) -> list:
    """R4 : chaque exemption NOMMÉE (des `classes` données, toutes par défaut) couvre au moins une phrase
    (sonde à sortie anticipée)."""
    par_entree = {}
    for chemin in suivis(racine):
        ex = exemption(chemin)
        if ex:
            par_entree.setdefault(ex, []).append(chemin)
    vides = []
    for ex in entrees_nommees(classes):
        if ex[0] == "INSTANTANE":
            textes = (lire(racine, c) or "" for c in suivis(racine) if c.endswith("SKILL.md"))
            if not any(l in lignes_instantane(t) for t in textes for l, *_ in phrases(t)):
                vides.append(f"{ex[0]} {ex[1]}")
        elif not any(phrases(lire(racine, c) or "") for c in par_entree.get(ex, [])):
            vides.append(f"{ex[0]} {ex[1]}")
    return vides


def verifier(racine: Path, soi: str = ""):
    """Les deux exigences de l'arbre : un corpus NON muet (R5), puis aucun écart. Tous les écarts, d'un coup."""
    ecarts, vivantes = juger(racine, soi)
    assert vivantes > 0, "aucune phrase de comptage vivante : un corpus muet ne prouve rien (vacuité)"
    assert ecarts == [], "phrases de comptage qui ne valent pas le roster dérivé :\n" + "\n".join(ecarts)


def exclus_codex(racine: Path) -> set:
    """Les défs exclues du levier sur codex, lues dans `EXCLUDED` de `core-scripts/apply-mode.py`."""
    spec = importlib.util.spec_from_file_location("roster_cardinal_mode", racine / "core-scripts" / "apply-mode.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return {nom for hote, nom in module.EXCLUDED if hote == "codex"}


def tableau_codex(racine: Path) -> list:
    """Les MEMBRES du tableau de répartition Codex de MODEL_MODES.md : chaque nom du roster y est, chaque nom
    est sur la ligne du modèle que porte son `.codex/agents/<nom>.toml`, et le GRAS = les exclus du levier."""
    texte = lire(racine, ".agents/ref/MODEL_MODES.md") or ""
    vus, gras, fautes = set(), set(), []
    for ligne in texte.splitlines():
        if not ligne.startswith("| `gpt-"):
            continue
        cellules = ligne.split("|")
        modele = cellules[1].strip().strip("`")
        for m in re.finditer(r"(\*\*)?`([a-z0-9-]+)`", cellules[2]):
            nom = m.group(2)
            vus.add(nom)
            if m.group(1):
                gras.add(nom)
            porte = re.search(r'^model\s*=\s*"([^"]+)"', lire(racine, f".codex/agents/{nom}.toml") or "", re.M)
            if porte is None or porte.group(1) != modele:
                fautes.append(f"MODELE {nom} : ligne `{modele}`, .toml {porte.group(1) if porte else 'absent'}")
    fautes += [f"ABSENT {nom}" for nom in sorted(set(roster(racine)) - vus)]
    exclus = exclus_codex(racine)
    if gras != exclus:
        fautes.append(f"GRAS {sorted(gras)} != EXCLUDED codex {sorted(exclus)}")
    return fautes


# =====================================================================================================
# L'ARBRE RÉEL
# =====================================================================================================
SOI = Path(__file__).resolve().relative_to(ROOT).as_posix()


def test_le_roster_est_derive_et_non_vide():
    assert len(roster(ROOT)) > 0, "un roster vide rendrait toute comparaison vide"


def test_toute_phrase_de_comptage_vivante_vaut_le_roster_derive():
    verifier(ROOT, SOI)


@functools.lru_cache(maxsize=None)
def compte_reel() -> dict:
    """Phrases vivantes PAR FICHIER sur l'arbre réel, calculées UNE fois pour les dix témoins."""
    compte = {}
    juger(ROOT, SOI, compte)
    return compte


@pytest.mark.parametrize("surface", sorted(PLANCHERS))
def test_une_surface_nommee_ne_se_tait_pas(surface):
    compte = compte_reel()
    assert PLANCHERS[surface] > 0
    assert compte.get(surface, 0) >= PLANCHERS[surface], (
        f"{surface} rend {compte.get(surface, 0)} phrase(s) de comptage, plancher {PLANCHERS[surface]} : "
        "un cardinal a été retiré, reformulé ou exempté — si c'est voulu, baisse le plancher en le disant")


def test_aucune_surface_vivante_hors_planchers():
    assert set(compte_reel()) <= set(PLANCHERS), sorted(set(compte_reel()) - set(PLANCHERS))


def test_aucune_exemption_decorative_sur_l_arbre_reel():
    assert exemptions_vides(ROOT, classes=R4_REEL) == []


def test_le_tableau_codex_de_model_modes_tient_ses_membres():
    assert tableau_codex(ROOT) == []


# =====================================================================================================
# LES TÉMOINS : des dépôts git jetables ; chacun est ROUGE contre le mutant qui le tue (voir l'annexe)
# =====================================================================================================
def ecrire(racine: Path, chemin: str, texte: str):
    cible = racine / chemin
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_text(texte, encoding="utf-8")


def plantes() -> dict:
    """Une occurrence « 99 agents » par exemption nommée : R4 est jugé sur ce corpus ET sur l'arbre réel."""
    out = {}
    for p in HISTORIQUE:
        out[p if p.endswith(".md") else p + ("26-x.md" if not p.endswith("/") else "x.md")] = "99 agents\n"
    for c in list(COUVERT) + list(DECISION_PILOTE):
        out[c] = "<p>99 agents</p>\n"
    out["x.py"] = "# 99 agents\n"
    out["x.sh"] = "# 99 agents\n"
    out[".agents/skills/s/SKILL.md"] = TITRE_INSTANTANE + "\n99 agents\n"
    return out


def depot(tmp_path: Path, defs: int, fichiers: dict, avec_plants: bool = True, ajoute: bool = True) -> Path:
    for i in range(defs):
        ecrire(tmp_path, f".claude/agents/a{i}.md", "---\nname: a\n---\n")
    for chemin, texte in {**(plantes() if avec_plants else {}), **fichiers}.items():
        ecrire(tmp_path, chemin, texte)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, env=env_git())
    if ajoute:
        subprocess.run(["git", "-C", str(tmp_path), "add", "-A", "-f"], check=True, env=env_git())
    return tmp_path


def noms_d_ecarts(ecarts) -> set:
    return {e.split(":")[0] for e in ecarts}


def test_w1_un_depot_juste_est_vert_et_chaque_exemption_exempte_quelque_chose(tmp_path):
    d = depot(tmp_path, 3, {"README.md": "3 agents\n", ".agents/ref/MODEL_MODES.md": "3 au roster\n"})
    ecarts, vivantes = juger(d)
    assert ecarts == [] and vivantes == 2
    assert exemptions_vides(d) == []


def test_w1b_un_agent_de_plus_rougit_les_deux_fichiers_en_un_run(tmp_path):
    d = depot(tmp_path, 4, {"README.md": "3 agents\n", ".agents/ref/MODEL_MODES.md": "3 au roster\n"})
    ecarts, _ = juger(d)
    assert noms_d_ecarts(ecarts) == {"README.md", ".agents/ref/MODEL_MODES.md"}


@pytest.mark.parametrize("phrase", ["trente et un defs", "trente et une défs", "vingt-neuf defs",
                                    "twenty-nine agents"])
def test_w2_un_cardinal_en_lettres_est_refuse(tmp_path, phrase):
    ecarts, _ = juger(depot(tmp_path, 3, {"README.md": "3 agents\n", "a.md": phrase + "\n"}))
    assert noms_d_ecarts(ecarts) == {"a.md"}


@pytest.mark.parametrize("phrase", ["3 agents pilotés", "3 defs Codex pilotées", "3 defs Claude pilotées",
                                    "3 defs Gemini pilotées", "3 defs Copilot pilotées", "3 defs Kimi pilotées",
                                    "3 agents de sécurité", "3 agents dédiés", "3 agents dédiées", "3 agents de clôture"])
def test_w3_un_qualifiant_postpose_est_une_sous_population_juste(tmp_path, phrase):
    # roster 4 : la sous-population (3) DIFFÈRE du roster, sinon le témoin serait muet même sans l'échappement
    assert juger(depot(tmp_path, 4, {"README.md": "4 agents\n", "a.md": phrase + "\n"}))[0] == []


def test_w3b_sans_qualifiant_la_meme_valeur_rougit(tmp_path):
    d = depot(tmp_path, 4, {"README.md": "4 agents\n", "a.md": "3 agents de sécurité et 3 agents\n"})
    assert noms_d_ecarts(juger(d)[0]) == {"a.md"}


def test_w4_un_rappel_historique_est_muet_la_meme_ligne_vivante_rougit(tmp_path):
    d = depot(tmp_path, 3, {"README.md": "3 agents\n", "docs/tasks/T-1-plan.md": "29 agents\n"})
    assert juger(d)[0] == []
    d2 = depot(tmp_path / "b", 3, {"README.md": "29 agents\n"})
    assert noms_d_ecarts(juger(d2)[0]) == {"README.md"}


def test_w5_la_section_instantane_est_muette_apres_elle_la_phrase_rougit(tmp_path):
    dans = TITRE_INSTANTANE + "\n29 agents\n### Sous-titre de l'instantané\n29 agents\n"
    apres = TITRE_INSTANTANE + "\nrien\n## Autre\n29 agents\n"
    d = depot(tmp_path, 3, {"README.md": "3 agents\n", ".agents/skills/s/SKILL.md": dans})
    assert juger(d)[0] == []
    d2 = depot(tmp_path / "b", 3, {"README.md": "3 agents\n", ".agents/skills/s/SKILL.md": apres})
    assert noms_d_ecarts(juger(d2)[0]) == {".agents/skills/s/SKILL.md"}
    d3 = depot(tmp_path / "c", 3, {"README.md": "3 agents\n" + dans})     # la section n'exempte que dans un SKILL.md
    assert noms_d_ecarts(juger(d3)[0]) == {"README.md"}


@pytest.mark.parametrize("nom", ["KIT_ROSTER", "EXPECTED_MODELS", "ROSTER", "roster", "claude", "codex",
                                 "gemini", "agents", "defs"])
def test_w6_c1_un_litteral_egal_au_roster_rougit_une_autre_valeur_est_une_sous_population(tmp_path, nom):
    juste = f"assert len({nom}) == 3 and ok\nself.assertEqual(len(self.{nom}), 3)\n"
    autre = f"assert len({nom}) == 4\nself.assertEqual(len({nom}), 7)\n"
    ecarts = juger(depot(tmp_path, 3, {"README.md": "3 agents\n", "t.py": juste}))[0]
    assert noms_d_ecarts(ecarts) == {"t.py"} and len(ecarts) == 2
    assert juger(depot(tmp_path / "b", 3, {"README.md": "3 agents\n", "t.py": autre}))[0] == []


def test_w8_un_fichier_non_suivi_n_est_pas_juge_borne_dite(tmp_path):
    d = depot(tmp_path, 3, {"README.md": "3 agents\n"})
    ecrire(d, "nouveau.md", "9 agents\n")        # jamais `git add`
    assert juger(d)[0] == []


# Trois variables qui DÉTOURNENT `git ls-files` quand elles sont héritées (mesuré) ; `GIT_WORK_TREE` et
# `GIT_CONFIG_COUNT` (+ `core.worktree`, `core.bare`) ne le détournent pas : ils feraient des témoins morts.
@pytest.mark.parametrize("variable", ["GIT_DIR", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY"])
def test_w9_un_environnement_git_herite_ne_detourne_pas_le_corpus(tmp_path, monkeypatch, variable):
    autre = tmp_path / "autre"
    autre.mkdir()
    subprocess.run(["git", "init", "-q", str(autre)], check=True, env=env_git())
    d = depot(tmp_path / "juge", 3, {"README.md": "29 agents\n"})
    valeurs = {"GIT_DIR": str(autre / ".git"), "GIT_INDEX_FILE": str(autre / ".git" / "index-vide"),
               "GIT_OBJECT_DIRECTORY": str(tmp_path / "objets-absents")}
    monkeypatch.setenv(variable, valeurs[variable])
    assert noms_d_ecarts(juger(d)[0]) == {"README.md"}


def test_w10_chaque_exemption_nommee_sans_occurrence_est_decorative(tmp_path):
    d = depot(tmp_path, 3, {"README.md": "3 agents\n"}, avec_plants=False)
    assert sorted(exemptions_vides(d)) == sorted(f"{c} {e}" for c, e in entrees_nommees())
    assert len(entrees_nommees()) == len(HISTORIQUE) + len(COUVERT) + len(DECISION_PILOTE) + len(EXT_CODE) + 1


def test_w10b_r4_sur_l_arbre_reel_juge_toutes_les_classes_sauf_historique(tmp_path):
    d = depot(tmp_path, 3, {"README.md": "3 agents\n"}, avec_plants=False)
    attendu = sorted(f"{c} {e}" for c, e in entrees_nommees() if c != "HISTORIQUE")
    assert sorted(exemptions_vides(d, classes=R4_REEL)) == attendu


def test_w10c_une_entree_pilote_vide_est_decorative_sous_r4_reel(tmp_path, monkeypatch):
    # DECISION_PILOTE est vide depuis le 2026-10-13 : W10b ne voit plus la classe, ce témoin la tient.
    monkeypatch.setitem(DECISION_PILOTE, "p.html", "témoin")
    d = depot(tmp_path, 3, {"README.md": "3 agents\n"}, avec_plants=False)
    assert "DECISION PILOTE p.html" in exemptions_vides(d, classes=R4_REEL)


def test_w11_une_tuile_a_balisage_est_lue_comme_un_nombre_et_son_nom(tmp_path):
    tuile = '<div class="m"><b>3</b><span>agents</span></div>\n'
    assert juger(depot(tmp_path, 3, {"CADRE/architecture.html": tuile}))[0] == []
    ecarts, _ = juger(depot(tmp_path / "b", 4, {"CADRE/architecture.html": tuile}))
    assert noms_d_ecarts(ecarts) == {"CADRE/architecture.html"}


@pytest.mark.parametrize("phrase", ["zéro déf sur 3 porte model", "3/3 loaded", "| 2 sur 3 |",
                                    "3 au roster", "le roster reste à 3", "the roster stays at 3",
                                    "the roster is at 3", "le roster compte 3", "the roster counts 3",
                                    "3 − 1 − 1 = 1", "3 subagents", "3 sous-agents",
                                    "3 defs", "3 défs", "meta:'3 rôles spécialisés'", "3 roles",
                                    "3 specialized agents", "3 role-scoped subagents"])
def test_w12_les_formes_hors_m1_sont_jugees(tmp_path, phrase):
    juste = juger(depot(tmp_path, 3, {"a.md": phrase + "\n"}))[0]
    faux = juger(depot(tmp_path / "b", 4, {"a.md": phrase + "\n"}))[0]
    assert juste == [] and noms_d_ecarts(faux) == {"a.md"}


def test_w13_un_corpus_sans_aucune_phrase_n_est_pas_vert_par_vacuite(tmp_path):
    with pytest.raises(AssertionError, match="vacuité"):
        verifier(depot(tmp_path, 3, {"README.md": "rien a compter\n"}))


def test_w14_l_exemption_est_le_fichier_nomme_pas_son_dossier(tmp_path):
    d = depot(tmp_path, 3, {"README.md": "3 agents\n", "docs/autre.md": "99 agents\n",
                            "CADRE/architecture.html": "<b>99</b><span>agents</span>\n"})
    assert noms_d_ecarts(juger(d)[0]) == {"docs/autre.md", "CADRE/architecture.html"}


@pytest.mark.parametrize("phrase", ['<b>3</b>\n<span>agents</span>', "3 verbatim agent defs",
                                    "3 au relevé du 2026-09-12", "20 core + 8 security + 3 closure",
                                    "3 définitions natives", '<meta content="3 agents">',
                                    "v3 agents", "1.3 agents", "1,3 agents", "1/3 agents", "2×3 agents",
                                    "*3 agents", "-3 agents", "1.3 − 1 = 2", "v1/3 loaded"])
def test_w15_les_bornes_dites_sont_assertees_non_vues(tmp_path, phrase):
    assert juger(depot(tmp_path, 4, {"README.md": "4 agents\n", "a.md": phrase + "\n"}))[0] == []


def test_w17_le_filet_ne_se_juge_pas_lui_meme(tmp_path):
    d = depot(tmp_path, 3, {"README.md": "3 agents\n", "t.py": "assert len(KIT_ROSTER) == 3\n"})
    assert noms_d_ecarts(juger(d)[0]) == {"t.py"}
    assert juger(d, soi="t.py")[0] == []


MODE_STUB = 'EXCLUDED = {("claude", "a0")} | {("codex", "a2")}\n'


@pytest.mark.parametrize("cas,ligne,attendu", [
    ("juste", "| `gpt-x` | `a0`, `a1`, **`a2`** |\n", []),
    ("absent", "| `gpt-x` | `a0`, **`a2`** |\n", ["ABSENT a1"]),
    ("mauvaise-ligne", "| `gpt-x` | `a0`, **`a2`** |\n| `gpt-y` | `a1` |\n", ["MODELE a1 : ligne `gpt-y`, .toml gpt-x"]),
    ("gras-faux", "| `gpt-x` | **`a0`**, `a1`, **`a2`** |\n", ["GRAS ['a0', 'a2'] != EXCLUDED codex ['a2']"]),
])
def test_w16_le_tableau_codex_tient_noms_lignes_et_gras(tmp_path, cas, ligne, attendu):
    fichiers = {".agents/ref/MODEL_MODES.md": ligne, "core-scripts/apply-mode.py": MODE_STUB}
    fichiers.update({f".codex/agents/a{i}.toml": 'model = "gpt-x"\n' for i in range(3)})
    assert tableau_codex(depot(tmp_path, 3, fichiers)) == attendu


@pytest.mark.parametrize("phrase", ["**3** agents", "**3 agents**", "| **2** sur 3 |", "roster reste à **3**",
                                    "3&nbsp;agents", "3&#160;agents", "3&#xa0;agents", "3&NBSP;agents"])
def test_w18_le_gras_et_l_insecable_ne_cachent_pas_un_cardinal(tmp_path, phrase):
    assert juger(depot(tmp_path, 3, {"a.md": phrase + "\n"}))[0] == []
    assert noms_d_ecarts(juger(depot(tmp_path / "b", 4, {"a.md": phrase + "\n"}))[0]) == {"a.md"}


@pytest.mark.parametrize("voisin", ["PLAN-ETAT.md", "CHANGELOG.md", "docs/design/ADDING_AN_ECOSYSTEM.md",
                                    "docs/designs.md", "runs-x.md", "runbook.md", "docs/tasks-x.md",
                                    "docs/interne-x.md", ".agents/state-x.md", "retro-x.md",
                                    "retrospective.md"])
def test_w19_le_voisin_d_une_exemption_historique_est_juge(tmp_path, voisin):
    d = depot(tmp_path, 3, {"README.md": "3 agents\n", voisin: "99 agents\n"})
    assert noms_d_ecarts(juger(d)[0]) == {voisin}


def test_w19b_l_historique_fige_est_exempte_son_voisin_juge(tmp_path):
    d = depot(tmp_path, 3, {"README.md": "3 agents\n", "docs/HISTORIQUE-0.1.0.md": "99 agents\n",
                            "docs/HISTORIQUE-0.2.0.md": "99 agents\n"})
    assert noms_d_ecarts(juger(d)[0]) == {"docs/HISTORIQUE-0.2.0.md"}


def test_w20_le_compte_par_surface_est_celui_que_lisent_les_planchers(tmp_path):
    d = depot(tmp_path, 3, {"README.md": "3 agents\n3 au roster\n", "a.md": "rien\n",
                            ".agents/skills/s/SKILL.md": TITRE_INSTANTANE + "\n3 agents\n"})
    compte = {}
    juger(d, "", compte)
    assert compte.get("README.md") == 2 and "a.md" not in compte and ".agents/skills/s/SKILL.md" not in compte


@pytest.mark.parametrize("dispo", ["ancien", "vendor", "les-deux"])
def test_vendor_seul_l(tmp_path, dispo):
    """Lot L : la surface `capacites_hotes.json` est jugée là où vit le paquet ; l'ancien masqué est muet.
    MUTANTS : chemin `src/cadre` écrit en dur, ou ombre non sautée -> rouge."""
    lieux = {"ancien": ["src/cadre"], "vendor": [".agents/vendor/cadre"],
             "les-deux": [".agents/vendor/cadre", "src/cadre"]}[dispo]
    fichiers = {"README.md": "3 agents\n", f"{lieux[0]}/__init__.py": "",
                f"{lieux[0]}/data/capacites_hotes.json": '{"note": "le roster compte 3"}\n'}
    for ombre in lieux[1:]:
        fichiers.update({f"{ombre}/__init__.py": "", f"{ombre}/data/capacites_hotes.json": "99 agents\n"})
    d = depot(tmp_path, 3, fichiers)
    assert paquet_cadre(d) == lieux[0]
    compte = {}
    ecarts, _ = juger(d, "", compte)
    assert ecarts == [], ecarts
    assert compte.get(f"{lieux[0]}/data/capacites_hotes.json") == 1
    assert ombre_cadre(d) == ("src/cadre/" if dispo == "les-deux" else None)
