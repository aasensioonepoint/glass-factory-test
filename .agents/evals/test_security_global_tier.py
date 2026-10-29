"""Témoin — `security-code-review-global` en Opus max, plafond de lecture levé.

Décision pilote S-01M51GNKV9FM9WWXSKXEJQSEQY (2026-10-16) : la revue applicative du
dépôt entier, lancée par `/audit -global` seul, passe en `claude-opus-5-5` / `max`, et
le plafond de lecture (~12 fichiers par module, ~150 au total) est LEVÉ. La méthode
devient : une passe de recensement (`census`, `files_candidate`, `units_untriaged`,
aucune lecture complète), puis une passe par lot de code d'au plus 350 Ko, lots
découpés par l'exécuteur (`audit_report.py --lots`).

CE QUE CE FILET TIENT, sur une liste LITTÉRALE de six chemins (cinq défs + le roster
embarqué), chaque chemin LU — un chemin absent est un échec, jamais un saut :
  (a) aucun résidu du plafond retiré (`~12`, `~150`, `12 files`, `150 flagged files`) ;
  (b) chaque déf, FICHIER PAR FICHIER, nomme la méthode par ses clés et sa borne de
      lot (`files_candidate`, `census`, `units_untriaged`, `files_read_paths`, `350`) ;
  (b') chaque déf porte les DEUX exemples de sortie, `stats` ouvrant sur
      `modules_total` (passe 1) et sur `files_read_paths` (passe k) — revue de clôture
      critic-opus F4 : la déf github n'en avait aucun, et « every count in `stats` »
      laissait `files_read_paths` au niveau haut (passe jugée mal formée, 0 lu) ;
  (c) `sonnet` absent des défs claude et kimi et du roster ;
  (d) les épingles de tier par hôte : claude (`claude-opus-5-5`, `max`), codex
      (`gpt-6-astra`, `max`), gemini (`gemini-3.1-pro`, `max_turns` 100,
      `timeout_mins` 60), aucune clé de tier sur github et kimi ;
  (e) les LOCALISATEURS que les défs `orchestrator` citent (`audit.md:16,20`,
      `SKILL.md:12,16` et sa ligne 29) : une édition de `/audit` qui décale ces lignes
      rend ces citations fausses, ce filet rougit alors.

CHAQUE CONTRÔLE EST UNE FONCTION PURE (chemin, texte) -> fautes. Les mutants la
rejouent EN MÉMOIRE sur le texte vivant muté, et chacun DOIT rougir — un contrôle
qu'aucun mutant ne fait rougir ne contrôle rien.

BORNE, dite pour ne pas être relue comme une garantie : ce filet juge le TEXTE des
défs, jamais le comportement de l'agent. Le protocole en passes n'a jamais été joué
en vrai ; sa première mesure sera le premier `/audit -global`. La fusion des passes
et le taux de couverture vivent dans `audit_report.py`, que ce filet n'importe pas.
"""
from __future__ import annotations

import importlib.util
import re
import sys
import tomllib
from collections.abc import Callable
from pathlib import Path

import pytest

Controle = Callable[[str, str], list[str]]
Mutation = Callable[[str], str]

ROOT = Path(__file__).resolve().parents[2]

CLAUDE = ".claude/agents/security-code-review-global.md"
CODEX = ".codex/agents/security-code-review-global.toml"
GEMINI = ".gemini/agents/security-code-review-global.md"
GITHUB = ".github/agents/security-code-review-global.agent.md"
KIMI = ".kimi-code/agents/security-code-review-global.md"
_SPEC_VENDOR = importlib.util.spec_from_file_location(
    "_security_global_tier_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
assert _SPEC_VENDOR is not None and _SPEC_VENDOR.loader is not None
_VENDOR = importlib.util.module_from_spec(_SPEC_VENDOR)
sys.modules[_SPEC_VENDOR.name] = _VENDOR
_SPEC_VENDOR.loader.exec_module(_VENDOR)
# Le paquet `cadre` OÙ QU'IL VIVE (`.agents/vendor/cadre`, sinon `src/cadre`), relatif à ROOT.
PAQUET = _VENDOR.exiger(ROOT, "cadre").relative_to(ROOT).as_posix()
ROSTER = f"{PAQUET}/data/roster/security-code-review-global.json"

DEFS = (CLAUDE, CODEX, GEMINI, GITHUB, KIMI)
CHEMINS = (CLAUDE, CODEX, GEMINI, GITHUB, KIMI, ROSTER)
SANS_SONNET = (CLAUDE, KIMI, ROSTER)

AUDIT_CMD = ".claude/commands/audit.md"
AUDIT_SKILL = ".agents/skills/audit/SKILL.md"

# (chemin, ligne 1-based, texte attendu sur CETTE ligne) — cités par les défs
# orchestrator des cinq hôtes et par leur rendu au roster.
LOCALISATEURS = (
    (AUDIT_CMD, 16, "security-orchestrator"),
    (AUDIT_CMD, 20, "security-code-review-global"),
    (AUDIT_SKILL, 12, "security-orchestrator"),
    (AUDIT_SKILL, 16, "security-code-review-global"),
    (AUDIT_SKILL, 29, "security-remediation"),
)

RESIDUS = (
    re.compile(r"~\s*(?:12|150)\b"),
    re.compile(r"\b(?:12|150)\s+(?:flagged\s+)?files\b"),
)
CLES = (
    ("files_candidate", re.compile(r"files_candidate")),
    ("census", re.compile(r"\bcensus\b")),
    ("units_untriaged", re.compile(r"units_untriaged")),
    ("files_read_paths", re.compile(r"files_read_paths")),
    ("350", re.compile(r"\b350\b")),
)
# Les deux exemples de § Output, tels que `audit_report.py` les lit : chaque clé sous `stats`.
EXEMPLES = (
    ("passe 1", re.compile(r'"stats":\s*\{\s*"modules_total"')),
    ("passe k", re.compile(r'"stats":\s*\{\s*"files_read_paths"')),
)
CLES_DE_TIER = ("model", "effort", "max_turns", "timeout_mins")

# Les trois clés que `cadre poser` insère dans un frontmatter (`managed.py` du paquet) :
# retirées avant de juger, comme `test_gemini_agent_schema._sans_tampon_poser`, sinon
# un fichier tamponné décalerait les localisateurs de trois lignes sans avoir dérivé.
_TAMPON = re.compile(r"^# cadre\.(?:managed|version|checksum): ")


# ---------------------------------------------------------------------------
# lecture
# ---------------------------------------------------------------------------
def sans_tampon(texte: str) -> str:
    lignes = texte.replace("\r\n", "\n").split("\n")
    return "\n".join(ln for ln in lignes if not _TAMPON.match(ln))


def lire(rel: str) -> str:
    chemin = ROOT / rel
    if not chemin.is_file():
        raise AssertionError(f"{rel} absent : ce filet lit chaque chemin, un absent est un échec")
    return sans_tampon(chemin.read_text(encoding="utf-8"))


def frontmatter(texte: str) -> list[str] | None:
    lignes = texte.split("\n")
    if not lignes or lignes[0] != "---":
        return None
    try:
        fin = lignes.index("---", 1)
    except ValueError:
        return None
    return lignes[1:fin]


def valeurs(fm: list[str], cle: str) -> list[str]:
    return [ln.split(":", 1)[1].strip() for ln in fm if re.match(rf"^{cle}:", ln)]


# ---------------------------------------------------------------------------
# contrôles — fonctions pures (chemin, texte) -> fautes
# ---------------------------------------------------------------------------
def fautes_residus(rel: str, texte: str) -> list[str]:
    return [f"{rel}: résidu du plafond retiré « {m.group(0)} »"
            for rx in RESIDUS for m in rx.finditer(texte)]


def fautes_cles(rel: str, texte: str) -> list[str]:
    return [f"{rel}: « {nom} » absent — la méthode en passes n'y est pas nommée"
            for nom, rx in CLES if not rx.search(texte)]


def fautes_exemples(rel: str, texte: str) -> list[str]:
    return [f"{rel}: exemple de sortie « {nom} » absent — `stats` doit porter ses clés"
            for nom, rx in EXEMPLES if not rx.search(texte)]


def fautes_sonnet(rel: str, texte: str) -> list[str]:
    return [f"{rel}: « sonnet » présent"] if re.search(r"sonnet", texte, re.I) else []


def _entier(rel: str, fm: list[str], cle: str, attendu: int) -> list[str]:
    vals = valeurs(fm, cle)
    if len(vals) != 1:
        return [f"{rel}: `{cle}:` attendu une fois, trouvé {len(vals)}"]
    try:
        valeur = int(vals[0])
    except ValueError:
        return [f"{rel}: `{cle}: {vals[0]}` n'est pas un entier"]
    return [] if valeur == attendu else [f"{rel}: `{cle}: {valeur}`, attendu {attendu}"]


def _exact(rel: str, fm: list[str], cle: str, attendu: str) -> list[str]:
    vals = valeurs(fm, cle)
    return [] if vals == [attendu] else [f"{rel}: `{cle}:` vaut {vals}, attendu [{attendu!r}]"]


def fautes_tier(rel: str, texte: str) -> list[str]:
    if rel == CODEX:
        try:
            cfg = tomllib.loads(texte)
        except tomllib.TOMLDecodeError as exc:
            return [f"{rel}: TOML illisible ({exc})"]
        fautes = []
        for cle, attendu in (("model", "gpt-6-astra"), ("model_reasoning_effort", "max")):
            if cfg.get(cle) != attendu:
                fautes.append(f"{rel}: `{cle}` vaut {cfg.get(cle)!r}, attendu {attendu!r}")
        return fautes
    fm = frontmatter(texte)
    if fm is None:
        return [f"{rel}: frontmatter introuvable"]
    fautes: list[str] = []
    if rel == CLAUDE:
        fautes += _exact(rel, fm, "model", "claude-opus-5-5")
        fautes += _exact(rel, fm, "effort", "max")
    elif rel == GEMINI:
        fautes += _exact(rel, fm, "model", "gemini-3.1-pro")
        fautes += _entier(rel, fm, "max_turns", 100)
        fautes += _entier(rel, fm, "timeout_mins", 60)
        if valeurs(fm, "effort"):
            fautes.append(f"{rel}: `effort:` présent (gemini-cli 0.57.0 refuse la clé)")
    elif rel in (GITHUB, KIMI):
        for cle in CLES_DE_TIER:
            if valeurs(fm, cle):
                fautes.append(f"{rel}: clé de tier `{cle}:` présente, cet hôte n'en porte aucune")
    if rel in (CLAUDE, KIMI):
        for ln in fm:
            if ln.startswith("#") and re.search(r"bounded|sonnet", ln, re.I):
                fautes.append(f"{rel}: commentaire de tier périmé « {ln} »")
    return fautes


def fautes_localisateur(rel: str, texte: str, ligne: int, attendu: str) -> list[str]:
    lignes = texte.split("\n")
    if len(lignes) >= ligne and attendu in lignes[ligne - 1]:
        return []
    return [f"{rel}:{ligne}: « {attendu} » n'y est plus — les défs orchestrator citent "
            "audit.md:16,20 et SKILL.md:12,16 (et sa ligne 29) : éditer EN PLACE"]


# ---------------------------------------------------------------------------
# l'arbre réel
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("rel", CHEMINS)
def test_chacun_des_six_chemins_est_lu(rel: str) -> None:
    assert lire(rel).strip(), f"{rel} vide"


@pytest.mark.parametrize("rel", CHEMINS)
def test_aucun_residu_du_plafond(rel: str) -> None:
    assert fautes_residus(rel, lire(rel)) == []


@pytest.mark.parametrize("rel", DEFS)
def test_la_methode_en_passes_est_nommee_dans_chaque_def(rel: str) -> None:
    assert fautes_cles(rel, lire(rel)) == []


@pytest.mark.parametrize("rel", DEFS)
def test_les_deux_exemples_de_sortie_dans_chaque_def(rel: str) -> None:
    assert fautes_exemples(rel, lire(rel)) == []


@pytest.mark.parametrize("rel", SANS_SONNET)
def test_sonnet_absent(rel: str) -> None:
    assert fautes_sonnet(rel, lire(rel)) == []


@pytest.mark.parametrize("rel", DEFS)
def test_epingles_de_tier(rel: str) -> None:
    assert fautes_tier(rel, lire(rel)) == []


@pytest.mark.parametrize("rel,ligne,attendu", LOCALISATEURS)
def test_localisateurs_de_audit(rel: str, ligne: int, attendu: str) -> None:
    assert fautes_localisateur(rel, lire(rel), ligne, attendu) == []


# ---------------------------------------------------------------------------
# mutants — en mémoire, sur le texte vivant ; chacun DOIT rougir
# ---------------------------------------------------------------------------
def _ajoute(phrase: str) -> Mutation:
    return lambda t: t + "\n" + phrase + "\n"


def _retire_ligne(motif: str) -> Mutation:
    rx = re.compile(motif, re.M)
    return lambda t: rx.sub("", t, count=1)


def _remplace(avant: str, apres: str) -> Mutation:
    return lambda t: t.replace(avant, apres)


def _decale(t: str) -> str:
    """Une ligne insérée juste après la première : tout ce qui suit descend d'un cran."""
    tete, _, reste = t.partition("\n")
    return tete + "\n\n" + reste


MUTANTS = (
    # un résidu par hôte, phrase exacte du plafond retiré
    ("residu-claude", CLAUDE, fautes_residus, _ajoute("READ up to ~12")),
    ("residu-codex", CODEX, fautes_residus, _ajoute("READ up to ~12")),
    ("residu-kimi", KIMI, fautes_residus, _ajoute("READ up to ~12")),
    ("residu-gemini", GEMINI, fautes_residus, _ajoute("(~12/module, ~150 overall)")),
    ("residu-github-module", GITHUB, fautes_residus, _ajoute("(~12/module)")),
    ("residu-github-flagged", GITHUB, fautes_residus, _ajoute("read up to ~12 flagged files")),
    ("residu-roster", ROSTER, fautes_residus, _ajoute("(~12/module)")),
    # une clé de tier retirée par hôte qui en porte
    ("tier-effort-claude", CLAUDE, fautes_tier, _retire_ligne(r"^effort: .*\n")),
    ("tier-effort-codex", CODEX, fautes_tier, _retire_ligne(r"^model_reasoning_effort = .*\n")),
    ("tier-model-gemini", GEMINI, fautes_tier, _retire_ligne(r"^model: .*\n")),
    ("tier-max-turns-gemini", GEMINI, fautes_tier, _remplace("max_turns: 100", "max_turns: 1")),
    ("tier-sonnet-claude", CLAUDE, fautes_tier, _remplace("model: claude-opus-5-5", "model: sonnet")),
    ("tier-cle-kimi", KIMI, fautes_tier, _remplace("tools: Read", "effort: max\ntools: Read")),
    # sonnet réinjecté
    ("sonnet-kimi", KIMI, fautes_sonnet, _ajoute("# sonnet/high")),
    ("sonnet-roster", ROSTER, fautes_sonnet, _remplace('"model: claude-opus-5-5"', '"model: sonnet"')),
    # méthode retirée
    ("census-github", GITHUB, fautes_cles, _remplace("census", "inventory")),
    ("lot-350-claude", CLAUDE, fautes_cles, _remplace("350", "999")),
    ("files-read-paths-github", GITHUB, fautes_cles, _remplace("files_read_paths", "files_read")),
    # exemple de sortie retiré, ou clé sortie de `stats` (la faute que F4 mesurait)
    ("exemple-passe-1-github", GITHUB, fautes_exemples,
     _remplace('"stats": {"modules_total"', '"modules_total"')),
    ("exemple-passe-k-github", GITHUB, fautes_exemples,
     _remplace('"stats": {"files_read_paths"', '"files_read_paths"')),
)

MUTANTS_LOCALISATEURS = (
    ("audit-l20-decalee", AUDIT_CMD, 20, "security-code-review-global"),
    ("skill-l29-decalee", AUDIT_SKILL, 29, "security-remediation"),
)


@pytest.mark.parametrize("nom,rel,controle,mutation", MUTANTS, ids=[m[0] for m in MUTANTS])
def test_chaque_mutant_rougit(nom: str, rel: str, controle: Controle, mutation: Mutation) -> None:
    vivant = lire(rel)
    mute = mutation(vivant)
    assert mute != vivant, f"{nom} : mutation sans effet — elle ne prouverait rien"
    assert controle(rel, vivant) == [], f"{nom} : le texte vivant doit être vert"
    assert controle(rel, mute) != [], f"{nom} : le mutant n'a pas rougi"


@pytest.mark.parametrize("nom,rel,ligne,attendu", MUTANTS_LOCALISATEURS,
                         ids=[m[0] for m in MUTANTS_LOCALISATEURS])
def test_chaque_localisateur_decale_rougit(nom: str, rel: str, ligne: int, attendu: str) -> None:
    vivant = lire(rel)
    assert fautes_localisateur(rel, vivant, ligne, attendu) == []
    assert fautes_localisateur(rel, _decale(vivant), ligne, attendu) != [], nom


def test_un_tampon_poser_ne_decale_rien() -> None:
    """Un frontmatter tamponné par `cadre poser` (trois lignes avant le `---` fermant)
    reste vert : le tampon n'est pas une dérive."""
    vivant = (ROOT / AUDIT_CMD).read_text(encoding="utf-8")
    tampon = ('# cadre.managed: true\n# cadre.version: "0"\n'
              '# cadre.checksum: "sha256:' + "0" * 64 + '"\n')
    lignes = vivant.split("\n")
    fin = lignes.index("---", 1)
    tamponne = "\n".join(lignes[:fin]) + "\n" + tampon + "\n".join(lignes[fin:])
    assert fautes_localisateur(AUDIT_CMD, tamponne, 20, "security-code-review-global") != []
    assert fautes_localisateur(AUDIT_CMD, sans_tampon(tamponne), 20,
                               "security-code-review-global") == []
