"""Témoin de la skill de nuit — règle de SAUT et mémoire des SAUTÉES (T-00000799).

`.agents/skills/night/SKILL.md` VOYAGE vers les hôtes non-Claude ; `.claude/commands/night.md`
est sa source canonique. Le lot T-00000765 a porté dans la commande seule (écart relevé
au journal, S-00002828) :

  * la RÈGLE DE SAUT — quand la jambe des arêtes refuse le `start` (une `ARÊTE:` du plan
    approuvé manque au board), la nuit SAUTE la tâche, qui reste `pending`, et ne rejoue
    JAMAIS avec `--sans-dependances` (décision de l'orchestrateur S-00002785) ;
  * la MÉMOIRE DES SAUTÉES — `.agents/state/local/night/sautees`, relue avant le choix de
    chaque tour, vidée à l'ouverture de la nuit suivante.

Ce banc lit la SKILL et exige les deux, ancrés sur des phrases que la base ne portait pas :
`SAUTE` seul y figure déjà, pour le saut à l'APPROBATION (`night_approve.py`), et une ancre
sur lui serait verte sur la base. `test_night_contract.py` n'est pas touché ;
`test_plan_depends_mirror.py` tient la même règle côté commande, mais ne voyage pas.
Chaque test nomme sa mutation. ZÉRO appel LLM, aucune énumération de l'arbre.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / ".agents" / "skills" / "night" / "SKILL.md"
NIGHT = ROOT / ".claude" / "commands" / "night.md"

# Ancres ÉPINGLÉES EN DUR — jamais relues depuis une surface.
SAUT = "**Règle de SAUT — arête manquante"  # marqueur du paragraphe de la règle
MEMOIRE = "**Mémoire des sautées"  # marqueur du paragraphe de la mémoire
SAUTEES = "`.agents/state/local/night/sautees`"  # même chaîne que test_plan_depends_mirror.py
ARETE = "`<aval> <- <amont>`"
RELU = "RELU avant le choix de CHAQUE tour"
VIDE = "VIDÉ à l'ouverture de la nuit suivante"
VERDICT_SAUTEE = "`sautée : <aval> <- <amont>`"
FORMAT = "## Format de sortie de chaque tour"
NIGHT_CIBLE = "### Si `PLAN_CIBLE_REQUIRED` est armé"
RENVOI = "`.claude/commands/night.md` § « Si `PLAN_CIBLE_REQUIRED` est armé »"
DRAPEAU = "--sans-dependances"

# Borne du détecteur de prescription : une négation doit précéder le drapeau dans les
# 30 caractères (« JAMAIS `--sans-dependances` », « ne rejoue jamais avec `--sans-dependances` »).
_NEGATIONS = ("jamais", "ne rejoue pas")
_FENETRE = 30
_FENCE = re.compile(r"```[A-Za-z]*\n(.*?)```", re.DOTALL)
_CODE = re.compile(r"`([^`]+)`")


def _lire(chemin: Path) -> str:
    return chemin.read_text(encoding="utf-8")


def _plat(texte: str) -> str:
    """Espaces repliés : la prose se re-coupe au reflow, les ancres ne doivent pas en dépendre."""
    return " ".join(texte.split())


def _paragraphe(texte: str, marqueur: str) -> str | None:
    """Le paragraphe (bloc sans ligne vide) qui s'ouvre sur `marqueur`, aplati ; None s'il manque."""
    for bloc in re.split(r"\n[ \t]*\n", texte):
        if bloc.lstrip().startswith(marqueur):
            return _plat(bloc)
    return None


def _section(texte: str, titre: str) -> str | None:
    debut = texte.find(titre)
    if debut < 0:
        return None
    fin = texte.find("\n## ", debut + len(titre))
    return texte[debut:fin if fin >= 0 else len(texte)]


def _prescriptions(texte: str) -> list[str]:
    """Les sites où `texte` PRESCRIT `--sans-dependances` au lieu de l'interdire : dans un bloc
    clôturé (à recopier), dans une commande `tasks.py` en ligne, ou sans négation devant."""
    fautes = [f"bloc clôturé : {b.strip()[:120]!r}" for b in _FENCE.findall(texte) if DRAPEAU in b]
    prose = _plat(_FENCE.sub(" ", texte))
    fautes += [f"commande : {s!r}" for s in _CODE.findall(prose) if DRAPEAU in s and "tasks.py" in s]
    for m in re.finditer(re.escape(DRAPEAU), prose):
        avant = prose[max(0, m.start() - _FENETRE):m.start()].casefold()
        if not any(n in avant for n in _NEGATIONS):
            fautes.append(f"sans négation : {prose[max(0, m.start() - 60):m.end() + 1]!r}")
    return fautes


def test_la_skill_porte_la_regle_de_saut():
    """← paragraphe de la règle retiré de la skill ; ← « SAUTE la tâche », « reste `pending` »,
    l'`ARÊTE:` ou la décision S-00002785 retirés ; ← `--sans-dependances` plus dit geste MANUEL."""
    sub = _paragraphe(_lire(SKILL), SAUT)
    assert sub is not None, f"la skill ne porte pas le paragraphe {SAUT!r} — la règle de saut ne voyage pas"
    for ancre in ("`ARÊTE:`", "SAUTE la tâche", "reste `pending`", "S-00002785", DRAPEAU, "geste MANUEL"):
        assert ancre in sub, f"règle de saut sans {ancre!r} : {sub[:300]!r}"


def test_la_skill_porte_la_memoire_des_sautees():
    """← fichier `night/sautees` plus nommé ; ← plus RELU avant chaque tour (la boucle re-choisirait
    la tâche sautée à chaque tour) ; ← plus VIDÉ à la nuit suivante ; ← format de ligne perdu."""
    sub = _paragraphe(_lire(SKILL), MEMOIRE)
    assert sub is not None, f"la skill ne porte pas le paragraphe {MEMOIRE!r} — la mémoire ne voyage pas"
    for ancre in (SAUTEES, ARETE, RELU, VIDE, "git-ignoré", "`--dry-run`"):
        assert ancre in sub, f"mémoire des sautées sans {ancre!r} : {sub[:300]!r}"


def test_le_verdict_de_tour_nomme_la_tache_sautee():
    """← `VERDICT` du format de sortie sans la valeur `sautée : <aval> <- <amont>` (night.md la porte)."""
    sec = _section(_lire(SKILL), FORMAT)
    assert sec is not None, f"section {FORMAT!r} absente de la skill"
    assert VERDICT_SAUTEE in _plat(sec), "le VERDICT de tour ne nomme pas la tâche sautée"


def test_la_skill_ne_prescrit_jamais_sans_dependances():
    """← un bloc clôturé, une commande `tasks.py … --sans-dependances` en ligne, ou une phrase
    sans négation glissés dans la skill. Le drapeau doit être NOMMÉ (pour l'interdire) : sinon
    ce filet serait vacant, vert sur une skill qui n'en dit rien."""
    texte = _lire(SKILL)
    assert DRAPEAU in texte, "la skill ne nomme pas --sans-dependances — l'interdiction ne voyage pas"
    fautes = _prescriptions(texte)
    assert not fautes, f"la skill prescrit {DRAPEAU} : {fautes}"


def test_le_detecteur_rougit_sur_une_prescription():
    """Le détecteur doit pouvoir rougir : trois prescriptions synthétiques, une interdiction."""
    assert _prescriptions("Sinon, la nuit rejoue avec `--sans-dependances`.")
    assert _prescriptions("```sh\nbash .agents/pyrun.sh .agents/bin/tasks.py start T-1 --sans-dependances\n```\n")
    assert _prescriptions("passe `tasks.py start T-NNN --sans-dependances` au tour suivant")
    assert not _prescriptions("ni nouveau `start`, et **JAMAIS `--sans-dependances`**, geste MANUEL")


def test_le_renvoi_vers_la_source_se_resout():
    """← la skill ne pointe plus sa source ; ← night.md renomme la sous-section ou y perd la règle :
    le pointeur mènerait à un texte qui ne dit plus ce que la skill résume."""
    sub = _paragraphe(_lire(SKILL), MEMOIRE)
    assert sub is not None and RENVOI in sub, f"la skill ne renvoie pas à {RENVOI!r}"
    source = _lire(NIGHT)
    assert NIGHT_CIBLE in source, f"night.md n'a plus la sous-section {NIGHT_CIBLE!r}"
    plat = _plat(_section(source, NIGHT_CIBLE) or "")
    for ancre in ("SAUTE la tâche", SAUTEES, ARETE, RELU, VIDE, "S-00002785"):
        assert ancre in plat, f"night.md § cible ne porte plus {ancre!r} — la skill résume un texte disparu"


# --- UsageAnglais (T-01M5QC86XNEJ5NEX6DGZJ0AJZ5, lot C3, décision pilote S-01M5S9NJN15HT7KVHZHZYM8DM8) ---
# La description (et son Usage) de `/night` et de `$night` parle anglais ; `/dash` n'a plus de
# résidu français. Le CORPS de night.md reste en français (allowlist headless = gate pilote) :
# seul le frontmatter `description:` des deux surfaces de nuit est jugé. Marqueurs FERMÉS,
# cherchés hors code (`…`) et hors tiret cadratin (« Usage — », convention des commandes).
DASH_CMD = ROOT / ".claude" / "commands" / "dash.md"
DASH_SKILL = ROOT / ".agents" / "skills" / "dash" / "SKILL.md"
USAGE_NIGHT = "Usage — /night [--end HH:MM] [--target HH:MM] [--headless] [--dry-run]"
_MOTS_FR = frozenset(
    "le la les des du un une et ou nuit dont sauf alors sans jusqu jusqu'au "
    "petit matin chantiers dépile lire correction démon verrou peut "
    "de au aux pour avec chaque avant tache taches".split()
)
_ACCENTS = re.compile(r"[àâäçéèêëîïôöùûüÿœæ]", re.IGNORECASE)


def _description(texte: str) -> str | None:
    m = re.match(r"---\n(.*?)\n---\n", texte, re.DOTALL)
    if m is None:
        return None
    for ligne in m.group(1).splitlines():
        if ligne.startswith("description:"):
            return ligne[len("description:"):].strip()
    return None


def _marqueurs_fr(texte: str) -> list[str]:
    """Les marqueurs français de `texte`, hors code en ligne et hors tiret cadratin."""
    prose = _CODE.sub(" ", texte).replace("—", " ")
    fautes = [f"accent : {m.group(0)!r}" for m in _ACCENTS.finditer(prose)]
    mots = re.findall(r"[A-Za-zÀ-ÿ']+", prose)
    fautes += [f"mot : {w!r}" for w in mots if w.casefold().strip("'") in _MOTS_FR]
    return fautes


def test_usage_anglais_night():
    """UsageAnglais ← description de night.md ou de la skill remise en français ; ← Usage perdu."""
    for chemin in (NIGHT, SKILL):
        desc = _description(_lire(chemin))
        assert desc is not None, f"{chemin.name} : frontmatter sans `description:`"
        assert USAGE_NIGHT in desc, f"{chemin}: Usage de /night absent de la description : {desc!r}"
        fautes = _marqueurs_fr(desc)
        assert not fautes, f"{chemin}: description de /night encore en français : {fautes}"


def test_usage_anglais_dash():
    """UsageAnglais ← résidu français (« sauf un démon… ») remis dans dash.md ou sa skill."""
    for chemin in (DASH_CMD, DASH_SKILL):
        fautes = _marqueurs_fr(_lire(chemin))
        assert not fautes, f"{chemin}: résidu français dans /dash : {fautes}"


def test_le_detecteur_fr_rougit():
    """Le détecteur doit pouvoir rougir : l'ancienne description et l'ancien résidu de /dash."""
    assert _marqueurs_fr("Mode nuit autonome — dépile les chantiers jusqu'au petit matin.")
    assert _marqueurs_fr("sauf un démon dont le ping s'est tu : `--stop` répond alors")
    # Sans accent ni mot de la première liste : seuls `de`, `chaque`, `tache` le trahissent.
    assert _marqueurs_fr("Mode autonome de travail nocturne : traite chaque tache approuvee.")
    assert not _marqueurs_fr("Autonomous night mode — works through the approved agenda. `démon`")
