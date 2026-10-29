"""Témoin de T-01M4N0268HZVKXC7VFZGYKDJM8 : plus aucun juge Claude sur `fable`.

Décision pilote S-01M4N02D2KFYQVV92ZXGSXBG2G (2026-10-11) : `plan-critic` et
`critic-fable` passent de `fable` / `xhigh` à `claude-opus-5-5` / `max`,
`critic-opus` reste en `xhigh`, et la doctrine écrit que le repli qui SURVIT à
un quota Opus épuisé est `critic-sonnet-max` — `critic-fable` partageant
désormais le modèle de `critic-opus` sur Claude Code.

(a) Aucune déf `.claude/agents/*.md` ne porte le jeton `fable` dans le
    `model:` de son frontmatter. Jetons découpés sur `[-_.]`, jamais une
    sous-chaîne (L-00000143). La population vient du glob, et elle doit égaler,
    NOM pour NOM, le roster embarqué `<paquet cadre>/data/roster/*.json`
    (paquet désigné par `vendor_paths`, `.agents/vendor/cadre` sinon `src/cadre`) : un glob
    vide ou amputé rendrait (a) vrai sans rien juger.
(b) Les valeurs de la décision, écrites en LITTÉRAL ici et jamais extraites
    d'un hôte (L-00000261). Amendée par S-01M57F0BHB (2026-10-18, vitesse,
    jamais coût) : `plan-critic` passe de `max` à `high`, `planner` à `medium`.
(g) Le routeur dit les MÊMES efforts que les frontmatters : chaque mention
    « `planner` (claude-opus-5-5, <effort>) » ou « `plan-critic` (…) »
    d'AGENTS.md porte l'`effort:` de la déf Claude du même nom ; au moins une
    mention par rôle, sinon le contrôle est vide.
(c) La phrase du repli survivant : « sur Claude Code », puis « quota Opus
    épuisé », puis le NOM `critic-sonnet-max` ANCRÉ par jeton, dans la même
    phrase, blancs normalisés. L'ancre `(?<![\\w-])` est la raison d'être de
    (c) : sans elle, une phrase qui nomme `plan-critic-sonnet-max` la
    satisferait seule. AGENTS.md portait une telle phrase voisine (le repli du
    critique de PLAN) jusqu'à S-01M4TZZ13Y (2026-10-13, planification sur Opus
    seul) ; depuis, le contrôle de l'ancre la remplace par un LEURRE
    SYNTHÉTIQUE, pour ne plus dépendre d'un texte retiré. Surfaces :
    AGENTS.md et les trois défs Claude de clôture.
(d) Contrôles positifs, sur le texte RÉEL de chaque surface : chaque mutation
    doit CHANGER le texte (une mutation sans effet est un contrôle vide, donc
    un échec) et faire rougir son prédicat.
(e) La conformité ne lit que le frontmatter : `fable` dans le CORPS d'une déf
    — le nom `critic-fable`, ou même une ligne `model: fable` citée — ne fait
    jamais rougir (a).

(h) Les graines `.agents/adopter-seed/` (T-01M4ND27N28XX2Z7W2D95MR076) : aucune
    ne porte le jeton `fable`, insensible à la casse, `(?<!\\w)fable(?!\\w)`, une
    fois retiré le NOM `critic-fable` — toute clé (`Model:`, `model :`,
    `"model":`) et la forme nue `plan-critic (fable, xhigh)` rougissent.
    Population : les fichiers du dossier, sous-dossiers compris, moins ceux que
    git IGNORE (un `.DS_Store` posé par le Finder ne rougit pas), et elle doit
    égaler `git ls-files -- .agents/adopter-seed`, non vide — la source même de
    `sync_template.py` `seed_targets`. Saut : hors du kit ET dossier absent
    seulement ; dans le kit, un dossier absent rougit. Bornes : `model:
    critic-fable` n'est pas vu ; un jeton collé à `_` ou à un chiffre
    (`claude_fable_5`, `fable5`, `critic_fable`) et les formes non ASCII
    (pleine chasse, U+200B, U+00AD) ne sont pas vus ; toute prose future qui
    cite `fable` hors `critic-fable` rougit, par choix.

Borne : ce banc lit l'arbre de travail, pas HEAD, et il ne dit rien du modèle
que l'hôte SERT à l'exécution (`.agents/ref/MODEL_MODES.md` § 8).
"""
from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

import pytest

EVALS = Path(__file__).resolve().parent
if str(EVALS) not in sys.path:
    sys.path.insert(0, str(EVALS))

from surface_kit import EST_LE_KIT, agents_du_kit  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = ROOT / ".claude" / "agents"
_SPEC_VENDOR = importlib.util.spec_from_file_location(
    "_juges_sans_fable_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
assert _SPEC_VENDOR is not None and _SPEC_VENDOR.loader is not None
_VENDOR = importlib.util.module_from_spec(_SPEC_VENDOR)
sys.modules[_SPEC_VENDOR.name] = _VENDOR
_SPEC_VENDOR.loader.exec_module(_VENDOR)
ROSTER_DIR = _VENDOR.exiger(ROOT, "cadre") / "data" / "roster"

# (b) — LITTÉRAUX de la décision S-01M4N02D2KFYQVV92ZXGSXBG2G : (model, effort) ;
# l'effort de `plan-critic` amendé par S-01M57F0BHB (max -> high).
JUGES = {
    "plan-critic": ("claude-opus-5-5", "high"),
    "critic-fable": ("claude-opus-5-5", "max"),
    "critic-opus": ("claude-opus-5-5", "xhigh"),
    "critic-sonnet-max": ("sonnet", "max"),
}

# (c) — les surfaces qui portent la phrase du repli survivant, et la LANGUE de chacune :
# T-01M5S9338BJP1B5RM3TG14AMYT, les défs sont en anglais, AGENTS.md reste en français — un motif
# par surface, jamais « l'une ou l'autre langue » sur une même surface.
SURFACES_REPLI = {
    "AGENTS.md": "fr",
    ".claude/agents/critic-opus.md": "en",
    ".claude/agents/critic-fable.md": "en",
    ".claude/agents/critic-sonnet-max.md": "en",
}
# (portée, quota épuisé) dans la langue de la surface ; le quota MUTÉ de (d) suit.
_MOTS_REPLI = {"fr": (r"[Ss]ur Claude Code", "quota Opus épuisé"),
               "en": (r"On Claude Code", "exhausted Opus quota")}
_QUOTA_MUTE = {"fr": "quota épuisé", "en": "exhausted quota"}

_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---[ \t]*\n", re.S)
# Une phrase s'arrête à `.` ou à `;` : la portée, le quota et le repli tiennent
# dans la MÊME phrase. `claude-opus-5-5` ne porte ni l'un ni l'autre.
_ANCRE = r"(?<![\w-])"


def _motif_repli(langue: str) -> str:
    portee, quota = _MOTS_REPLI[langue]
    return portee + r"[^.;]*?" + quota + r"[^.;]*?" + _ANCRE + r"critic-sonnet-max(?![\w-])"


_REPLI = {langue: re.compile(_motif_repli(langue)) for langue in _MOTS_REPLI}
_REPLI_SANS_ANCRE = {langue: re.compile(_motif_repli(langue).replace(_ANCRE, "", 1)) for langue in _MOTS_REPLI}


def frontmatter(texte: str) -> str:
    """Le bloc entre les deux `---` d'ouverture, ou "" s'il n'y en a pas."""
    m = _FRONTMATTER.match(texte)
    return m.group(1) if m else ""


def cle(texte: str, nom: str) -> str | None:
    """Valeur de la clé `nom:` du FRONTMATTER seul, guillemets retirés — la VALEUR seule
    (`[^\\s#]+`), jamais « jusqu'à la fin de ligne » : `model: fable  # x`, YAML valide,
    se lit `fable` (exec-critic T-01M4N…, M4 ; passe de clôture E-26)."""
    m = re.search(rf"^{re.escape(nom)}:[ \t]*([^\s#]+)", frontmatter(texte), re.M)
    return m.group(1).strip("\"'") if m else None


def jetons(valeur: str) -> set[str]:
    return {j.lower() for j in re.split(r"[-_.]", valeur.strip()) if j}


def porte_fable(texte: str) -> bool:
    modele = cle(texte, "model")
    return modele is not None and "fable" in jetons(modele)


def _plat(texte: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", texte))


def porte_repli_survivant(texte: str, langue: str = "fr") -> bool:
    return _REPLI[langue].search(_plat(texte)) is not None


def _lire(chemin: Path) -> str:
    return chemin.read_text(encoding="utf-8")


def _defs(tout: bool = False) -> dict[str, Path]:
    """Les défs jugées. Hors du kit (T-01M54MWW5GH, S-01M54ZQ6WC), celles du roster
    embarqué seules : un agent AJOUTÉ par l'adoptant n'est pas jugé ; `tout` rend le glob."""
    defs = {p.stem: p for p in sorted(AGENTS_DIR.glob("*.md"))}
    if tout or EST_LE_KIT:
        return defs
    kit = agents_du_kit()
    return {n: p for n, p in defs.items() if n in kit}


def _muter(texte: str, avant: str, apres: str) -> str:
    """Remplace la PREMIÈRE occurrence ; un contrôle sans effet est un échec."""
    assert avant in texte, f"contrôle vide : {avant!r} absent du texte réel"
    mute = texte.replace(avant, apres, 1)
    assert mute != texte, f"contrôle vide : {avant!r} -> {apres!r} ne change rien"
    return mute


def _muter_la_phrase(plat: str, avant: str, apres: str, langue: str = "fr") -> str:
    """Mute `avant` DANS la phrase du repli survivant, jamais ailleurs."""
    m = _REPLI[langue].search(plat)
    assert m is not None, "contrôle vide : la phrase du repli survivant est absente"
    span = m.group(0)
    assert avant in span, f"contrôle vide : {avant!r} absent de la phrase"
    nouveau = span.replace(avant, apres, 1)
    assert nouveau != span, f"contrôle vide : {avant!r} -> {apres!r} ne change rien"
    return plat[: m.start()] + nouveau + plat[m.end():]


# --- (a) --------------------------------------------------------------------


def test_a_la_population_est_le_roster_embarque() -> None:
    defs = set(_defs(tout=True))
    roster = {p.stem for p in ROSTER_DIR.glob("*.json")}
    assert defs, "glob vide : (a) ne jugerait rien"
    if EST_LE_KIT:
        assert defs == roster, f"glob et roster embarqué divergent : {sorted(defs ^ roster)}"
    else:
        assert roster and agents_du_kit() == roster, sorted(agents_du_kit() ^ roster)
        assert roster <= defs, f"déf du roster embarqué absente : {sorted(roster - defs)}"
        assert set(_defs()) == roster, "jugement filtré ≠ roster"
    assert set(JUGES) <= defs, f"juge absent du glob : {sorted(set(JUGES) - defs)}"


def test_a_aucune_def_ne_porte_fable_dans_son_model() -> None:
    fautives = sorted(nom for nom, p in _defs().items() if porte_fable(_lire(p)))
    assert fautives == [], f"`model:` sur le jeton fable : {fautives}"


# --- (b) --------------------------------------------------------------------


@pytest.mark.parametrize(("nom", "attendu"), sorted(JUGES.items()))
def test_b_les_valeurs_de_la_decision(nom: str, attendu: tuple[str, str]) -> None:
    texte = _lire(AGENTS_DIR / f"{nom}.md")
    assert (cle(texte, "model"), cle(texte, "effort")) == attendu, nom


# --- (c) --------------------------------------------------------------------


@pytest.mark.parametrize("rel", SURFACES_REPLI)
def test_c_la_phrase_du_repli_survivant(rel: str) -> None:
    langue = SURFACES_REPLI[rel]
    assert porte_repli_survivant(_lire(ROOT / rel), langue), (
        f"{rel} : « {_MOTS_REPLI[langue][0]} … {_MOTS_REPLI[langue][1]} … critic-sonnet-max » absente"
    )


@pytest.mark.parametrize("rel", [r for r, langue in SURFACES_REPLI.items() if langue == "en"])
def test_c_la_phrase_francaise_d_avant_ne_satisfait_pas_une_def(rel: str) -> None:
    """La re-épingle anglaise des défs (T-01M5S9338BJP1B5RM3TG14AMYT) garde sa force : la phrase
    française d'avant, mise à la place de l'anglaise, laisse la déf rouge."""
    plat = _plat(_lire(ROOT / rel))
    m = _REPLI["en"].search(plat)
    assert m is not None, f"{rel} : contrôle vide, phrase absente"
    mute = plat[: m.start()] + "Sur Claude Code, un quota Opus épuisé rend les deux indisponibles, et le repli " \
        "qui survit est `critic-sonnet-max`" + plat[m.end():]
    assert not porte_repli_survivant(mute, "en"), f"{rel} : la phrase française satisfait encore la déf"


# --- (d) contrôles positifs --------------------------------------------------


def test_d_une_mutation_sans_effet_est_un_echec() -> None:
    with pytest.raises(AssertionError):
        _muter("model: x", "model: y", "model: z")
    with pytest.raises(AssertionError):
        _muter("model: x", "x", "x")


# `fable  # x` : un commentaire YAML derrière la valeur (exec-critic T-01M4N…, M4) —
# une lecture « jusqu'à la fin de ligne » la rendait None et (a) restait vert.
@pytest.mark.parametrize("valeur", ["fable", "claude-fable-5", '"fable"', "fable  # x", '"fable" # x'])
def test_d_model_fable_injecte_dans_plan_critic_rougit_a(valeur: str) -> None:
    texte = _lire(AGENTS_DIR / "plan-critic.md")
    mute = _muter(texte, "model: claude-opus-5-5", f"model: {valeur}")
    assert porte_fable(mute), f"`model: {valeur}` non vu par (a)"


@pytest.mark.parametrize("nom", ["plan-critic", "critic-fable"])
def test_d_effort_xhigh_rougit_b(nom: str) -> None:
    texte = _lire(AGENTS_DIR / f"{nom}.md")
    mute = _muter(texte, f"effort: {JUGES[nom][1]}", "effort: xhigh")
    assert (cle(mute, "model"), cle(mute, "effort")) != JUGES[nom], nom


@pytest.mark.parametrize("rel", SURFACES_REPLI)
def test_d_la_phrase_retiree_rougit_c(rel: str) -> None:
    langue = SURFACES_REPLI[rel]
    plat = _plat(_lire(ROOT / rel))
    m = _REPLI[langue].search(plat)
    assert m is not None, f"{rel} : contrôle vide, phrase absente"
    mute = plat[: m.start()] + plat[m.end():]
    assert mute != plat
    assert not porte_repli_survivant(mute, langue), f"{rel} : une seconde phrase la satisfait encore"


@pytest.mark.parametrize("rel", SURFACES_REPLI)
@pytest.mark.parametrize(
    ("avant", "apres"),
    [
        ("Claude Code", "Codex"),  # la portée retirée (L-00000079)
        ("<quota>", None),  # le quota de la langue de la surface, muté (_QUOTA_MUTE)
        ("critic-sonnet-max", "plan-critic-sonnet-max"),  # l'ancre de C2
    ],
)
def test_d_chaque_morceau_de_la_phrase_compte(rel: str, avant: str, apres: str | None) -> None:
    langue = SURFACES_REPLI[rel]
    if avant == "<quota>":
        avant, apres = _MOTS_REPLI[langue][1], _QUOTA_MUTE[langue]
    plat = _plat(_lire(ROOT / rel))
    mute = _muter_la_phrase(plat, avant, apres, langue)
    assert not porte_repli_survivant(mute, langue), f"{rel} : {avant!r} -> {apres!r} reste vert"


# Le leurre de C2, SYNTHÉTIQUE depuis S-01M4TZZ13Y : la phrase d'AGENTS.md qui
# le fournissait (le repli du critique de PLAN) a quitté la doctrine avec lui.
# Même forme — portée, quota, puis un nom qui FINIT par `critic-sonnet-max` sans
# l'être — et aucun `.` ni `;` avant le nom, pour rester dans une seule phrase.
_LEURRE_PLAN = (
    "Sur Claude Code, un quota Opus épuisé emporte aussi le critique de plan, "
    "et `plan-critic-sonnet-max` reste hors chaîne."
)


def test_d_l_ancre_porte_la_charge_sur_agents_md() -> None:
    """C2 : AGENTS.md sans la phrase de clôture, plus le LEURRE synthétique
    (« … quota Opus épuisé … `plan-critic-sonnet-max` … »). Le motif SANS ancre
    le prend pour la phrase du repli survivant ; le motif ancré le refuse."""
    plat = _plat(_lire(ROOT / "AGENTS.md"))
    m = _REPLI["fr"].search(plat)
    assert m is not None, "contrôle vide : phrase de clôture absente d'AGENTS.md"
    sans_cloture = plat[: m.start()] + plat[m.end():]
    assert not porte_repli_survivant(sans_cloture), "une seconde phrase de clôture reste"
    leurre = sans_cloture + " " + _LEURRE_PLAN
    assert leurre != sans_cloture
    assert _REPLI_SANS_ANCRE["fr"].search(leurre) is not None, (
        "contrôle vide : le leurre ne tromperait même pas le motif sans ancre"
    )
    assert not porte_repli_survivant(leurre), "l'ancre ne refuse plus le leurre"


# --- (e) --------------------------------------------------------------------


def test_e_fable_dans_le_corps_ne_rougit_jamais() -> None:
    texte = _lire(AGENTS_DIR / "critic-fable.md")
    corps = texte[len(_FRONTMATTER.match(texte).group(0)):]
    assert "critic-fable" in corps, "contrôle vide : le corps ne cite pas critic-fable"
    assert not porte_fable(texte)
    # Clé `model:` RETIRÉE du frontmatter, puis citée dans le corps : une
    # lecture du texte entier la trouverait, la lecture du frontmatter jamais.
    sans_cle = _muter(texte, "model: claude-opus-5-5\n", "")
    mute = sans_cle + "\nmodel: fable\n"
    assert cle(mute, "model") is None
    assert not porte_fable(mute), "une ligne `model: fable` du CORPS a fait rougir (a)"


# --- (f) MODEL_MODES.md § 8 ---------------------------------------------------

MODEL_MODES = ROOT / ".agents" / "ref" / "MODEL_MODES.md"
_GRILLE = re.compile(r"<!-- GRID:BEGIN.*?<!-- GRID:END", re.S)
_LIGNE_MODELE = re.compile(r"^\| `claude` \| `[^`]+` \| model \| `([^`]+)` \| `([^`]+)` \|[ \t]*$", re.M)


def test_f_le_paragraphe_8_nomme_chaque_modele_ecrit_que_rien_ne_committe() -> None:
    """§ 8 disait « Toutes les valeurs que le mécanisme peut écrire sont déjà committées
    quelque part à HEAD » : faux pour `opus`, que la colonne expert ÉCRIT et qu'aucune
    déf ne porte (exec-critic T-01M4N…, passe de clôture E-26). Les exceptions NOMMÉES
    au § 8 (« SAUF `x` ») égalent les modèles Claude de la grille qu'aucune déf ne
    committe — dans les deux sens : une exception tue ou une exception oubliée rougit."""
    texte = _lire(MODEL_MODES)
    grille = _GRILLE.search(texte)
    assert grille is not None, "contrôle vide : grille introuvable (marqueurs GRID)"
    ecrits = {valeur for m in _LIGNE_MODELE.finditer(grille.group(0)) for valeur in m.groups()}
    assert {"sonnet", "claude-opus-5-5"} <= ecrits, f"contrôle vide : lignes model non lues ({sorted(ecrits)})"
    committes = {cle(_lire(p), "model") for p in _defs().values()}
    section = texte.split("\n## 8.", 1)[1].split("\n## ", 1)[0]
    nommes = set(re.findall(r"SAUF `([^`]+)`", section))
    assert nommes == ecrits - committes, (
        f"§ 8 nomme {sorted(nommes)}, la grille écrit sans commit {sorted(ecrits - committes)}"
    )


# --- (g) le routeur contre les frontmatters (S-01M57F0BHB) --------------------

ROLES_ROUTEUR = ("planner", "plan-critic")
# Le nom ferme son backtick : `planner-sonnet` et `plan-critic-sonnet-max` n'y entrent pas.
_MENTION_ROUTEUR = re.compile(r"`(planner|plan-critic)` \((claude-opus-5-5), (\w+)\)")


def ecarts_routeur(routeur: str, defs: dict[str, str]) -> list[str]:
    """Chaque mention (rôle, modèle, effort) du routeur contre la déf Claude du rôle ;
    un rôle sans mention est un écart (contrôle vide)."""
    mentions = _MENTION_ROUTEUR.findall(_plat(routeur))
    ecarts = [f"{role} : aucune mention « `{role}` (claude-opus-5-5, <effort>) »"
              for role in ROLES_ROUTEUR if role not in {r for r, _, _ in mentions}]
    for role, modele, effort in mentions:
        attendu = (cle(defs[role], "model"), cle(defs[role], "effort"))
        if (modele, effort) != attendu:
            ecarts.append(f"{role} : routeur ({modele}, {effort}) ≠ frontmatter {attendu}")
    return ecarts


def _defs_routeur() -> dict[str, str]:
    return {role: _lire(AGENTS_DIR / f"{role}.md") for role in ROLES_ROUTEUR}


def test_g_routeur_effort_contre_frontmatters() -> None:
    assert ecarts_routeur(_lire(ROOT / "AGENTS.md"), _defs_routeur()) == []


@pytest.mark.parametrize("role", ROLES_ROUTEUR)
def test_g_mutant_effort_du_routeur_rougit(role: str) -> None:
    """L'effort de la déf remis à l'ancienne valeur dans le routeur (`plan-critic` -> `max`,
    `planner` -> `high` : le retour à S-01M4N02D2) ; puis la mention du rôle retirée."""
    routeur, defs = _plat(_lire(ROOT / "AGENTS.md")), _defs_routeur()
    effort = cle(defs[role], "effort")
    ancien = {"plan-critic": "max", "planner": "high"}[role]
    assert effort != ancien, f"{role} : la déf porte encore {ancien!r}, le mutant ne prouverait rien"
    mention = f"`{role}` (claude-opus-5-5, {effort})"
    assert ecarts_routeur(_muter(routeur, mention, mention.replace(effort, ancien)), defs), role
    assert ecarts_routeur(routeur.replace(mention, f"`{role}`"), defs), role


# --- (h) graines adopter-seed (T-01M4ND27N28XX2Z7W2D95MR076) -----------------

# adopting-tree: lu sous _SANS_GRAINES (skipif hors du kit), .agents/adopter-seed/ ne voyage pas
GRAINES_DIR = ROOT / ".agents" / "adopter-seed"
GRAINES_NOMMEES = ("gates/PLAN_CHAIN_REQUIRED", "gates/PLAN_CIBLE_REQUIRED")
_FABLE_NU = re.compile(r"(?i)(?<!\w)fable(?!\w)")
_NOM_CRITIC_FABLE = re.compile(r"(?i)\bcritic-fable\b")
_SANS_GRAINES = pytest.mark.skipif(
    not EST_LE_KIT and not GRAINES_DIR.is_dir(),
    reason="graines strippées hors du kit (.agents/adopter-seed/ ne voyage pas)")


def graine_porte_fable(texte: str) -> bool:
    return _FABLE_NU.search(_NOM_CRITIC_FABLE.sub("", texte)) is not None


def _git_z(depot: Path, *args: str) -> list[str]:
    out = subprocess.run(["git", "-C", str(depot), *args], capture_output=True,
                         text=True, check=True).stdout
    return [s for s in out.split("\0") if s]


def _graines(racine: Path = GRAINES_DIR, depot: Path = ROOT) -> dict[str, Path]:
    """Fichiers sous `racine`, sous-dossiers compris, MOINS ceux que git ignore (C5)."""
    rel = racine.relative_to(depot).as_posix()
    ignores = {depot / p for p in _git_z(depot, "ls-files", "-z", "-o", "-i",
                                         "--exclude-standard", "--", rel)}
    return {p.relative_to(racine).as_posix(): p
            for p in sorted(racine.rglob("*")) if p.is_file() and p not in ignores}


@_SANS_GRAINES
def test_h_la_population_est_celle_suivie_par_git() -> None:
    prefixe = ".agents/adopter-seed/"
    suivies = {s.removeprefix(prefixe)
               for s in _git_z(ROOT, "ls-files", "-z", "--", prefixe)}
    graines = _graines()
    assert graines, f"population vide sous {GRAINES_DIR} : (h) ne jugerait rien"
    assert set(graines) == suivies, sorted(set(graines) ^ suivies)
    assert set(GRAINES_NOMMEES) <= set(graines), sorted(set(GRAINES_NOMMEES) - set(graines))


def _depot_jouet(tmp_path: Path) -> Path:
    """Un dépôt git jouet ; rend le dossier des graines, un niveau sous la racine.

    Isolé des exclusions du poste par deux voies (un `.DS_Store` exclu, réglage
    macOS courant, ferait rougir à tort le contrôle vide de C5) : un gabarit vide
    (`git init --template=`, donc aucun `info/exclude` copié d'un `init.templateDir`
    global) et un `core.excludesFile` local pointé sur un fichier vide.
    """
    subprocess.run(["git", "init", "-q", "--template=", str(tmp_path)], check=True,
                   capture_output=True)
    vide = tmp_path / ".git" / "aucune-exclusion"
    vide.write_text("", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "config", "core.excludesFile", str(vide)],
                   check=True, capture_output=True)
    racine = tmp_path / "seed"
    for rel in ("gates/A", "board/x.json"):
        (racine / rel).parent.mkdir(parents=True, exist_ok=True)
        (racine / rel).write_text("x", encoding="utf-8")
    return racine


def test_h_la_population_descend_les_sous_dossiers(tmp_path: Path) -> None:
    racine = _depot_jouet(tmp_path)
    assert set(_graines(racine, tmp_path)) == {"gates/A", "board/x.json"}


def test_h_un_fichier_ignore_par_git_n_entre_pas(tmp_path: Path) -> None:
    """C5 : un `.DS_Store` binaire, ignoré par git, ni compté ni lu ; non ignoré, compté."""
    racine = _depot_jouet(tmp_path)
    (racine / "gates" / ".DS_Store").write_bytes(b"\xff\x00fable")
    assert "gates/.DS_Store" in _graines(racine, tmp_path), "contrôle vide : rglob ne le voit pas"
    (tmp_path / ".gitignore").write_text(".DS_Store\n", encoding="utf-8")
    assert set(_graines(racine, tmp_path)) == {"gates/A", "board/x.json"}


def test_h_le_depot_jouet_ignore_les_exclusions_du_poste(tmp_path: Path, monkeypatch) -> None:
    """Un poste qui exclut `.DS_Store` par `init.templateDir` ET `core.excludesFile` globaux
    ne fait pas rougir le contrôle vide de C5 : le dépôt jouet s'isole des deux."""
    poste = tmp_path / "poste"
    (poste / "tpl" / "info").mkdir(parents=True)
    (poste / "tpl" / "info" / "exclude").write_text(".DS_Store\n", encoding="utf-8")
    (poste / "ignore").write_text(".DS_Store\n", encoding="utf-8")
    cfg = poste / "gitconfig"
    cfg.write_text(f"[core]\n\texcludesFile = {(poste / 'ignore').as_posix()}\n"
                   f"[init]\n\ttemplateDir = {(poste / 'tpl').as_posix()}\n", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(cfg))
    racine = _depot_jouet(tmp_path / "d")
    (racine / "gates" / ".DS_Store").write_bytes(b"\xff\x00fable")
    assert "gates/.DS_Store" in _graines(racine, tmp_path / "d"), "exclusion du poste héritée"


@_SANS_GRAINES
def test_h_aucune_graine_ne_cite_model_fable() -> None:
    fautives = sorted(n for n, p in _graines().items() if graine_porte_fable(_lire(p)))
    assert fautives == [], f"graine `model:` sur le jeton fable : {fautives}"


@_SANS_GRAINES
@pytest.mark.parametrize("rel", GRAINES_NOMMEES)
@pytest.mark.parametrize("apres", [
    "model: fable", "model: claude-fable-5", "model: `fable`", "Model: fable",
    "model : fable", "MODEL: CLAUDE-FABLE-5", '"model": "fable"', "plan-critic (fable, xhigh)"])
def test_h_mutant_fable_dans_une_graine_rougit(rel: str, apres: str) -> None:
    mute = _muter(_lire(GRAINES_DIR / rel), "model: claude-opus-5-5", apres)
    assert graine_porte_fable(mute), f"{apres!r} non vu par (h) dans {rel}"


@_SANS_GRAINES
def test_h_le_nom_critic_fable_ne_rougit_jamais() -> None:
    texte = _lire(GRAINES_DIR / "gates" / "BINOME_REQUIRED")
    assert "critic-fable" in texte, "contrôle vide : BINOME_REQUIRED ne cite plus critic-fable"
    assert not graine_porte_fable(texte)
    for nu in ("Critic-Fable", "CRITIC-FABLE", "affable", "fables", "fabled"):
        assert not graine_porte_fable(nu), f"{nu!r} rougit à tort (frontières de mot)"
