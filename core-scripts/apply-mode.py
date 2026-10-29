#!/usr/bin/env python3
"""apply-mode — monte d'un cran le tier de modèle / l'effort des defs d'agents.

    python core-scripts/apply-mode.py {expert|restore|status} [--recapture] [--quiet]

Ce script tourne sous **python3** (stdlib uniquement, aucune dépendance).

UPGRADE SEULEMENT. Il n'existe qu'un mode : `expert`, qui monte d'un cran. Il
n'y a pas de mode descendant, et il n'y en aura pas : `AGENTS.md` § Full power
interdit d'abaisser un tier pour économiser des jetons. `restore` n'est donc pas
un mode : c'est le retour EXACT à la colonne de référence capturée sur l'arbre
committé, et l'absence de `.agents/state/local/MODEL_MODE` EST l'état de
référence.

La doctrine, le périmètre, les exclusions et la grille complète vivent dans
`.agents/ref/MODEL_MODES.md` — ce fichier-ci n'est que le moteur. La grille y est
LUE (bloc `GRID:BEGIN`/`GRID:END`), jamais dupliquée ici : un seul endroit fait
autorité.

Trois hôtes portent un levier réel (claude, gemini, codex) ; deux n'en portent
aucun (github, kimi) et reçoivent un jeton strictement indicatif, jamais présenté
comme appliqué.

T-00000393 — importé et RÉDUIT depuis op-agentic-builder-kit.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / ".agents" / "ref" / "MODEL_MODES.md"
MODE_FILE = ROOT / ".agents" / "state" / "local" / "MODEL_MODE"

# Colonnes de la grille. `BASELINE` n'est PAS un mode enregistrable : c'est la
# capture de l'arbre committé, et son marqueur d'état est l'ABSENCE de fichier.
BASELINE = "défaut"
EXPERT = "expert"
COLUMNS = (BASELINE, EXPERT)
# Valeurs acceptées dans `.agents/state/local/MODEL_MODE`. Fichier absent = BASELINE.
MODES = (EXPERT,)

GRID_BEGIN = "<!-- GRID:BEGIN"
GRID_END = "<!-- GRID:END"

# --------------------------------------------------------------------------
# Périmètre — voir .agents/ref/MODEL_MODES.md § 2 et § 3.
# --------------------------------------------------------------------------

# Hôtes à levier : (répertoire, motif de nom de fichier, axes portés).
LEVER_HOSTS = {
    "claude": (".claude/agents", "{agent}.md", ("model", "effort")),
    "gemini": (".gemini/agents", "{agent}.md", ("model",)),
    "codex": (".codex/agents", "{agent}.toml", ("effort",)),
}

# Hôtes sans levier : jeton indicatif uniquement.
INDICATIVE_HOSTS = {
    "github": (".github/agents", "{agent}.agent.md"),
    "kimi": (".kimi-code/agents", "{agent}.md"),
}

# Exclu à demeure : l'hôte Claude Code réécrit seul ce frontmatter en cours de
# session (LEDGER op-agentic L-00000068). PORTÉE NON RE-MESURÉE SUR CE DÉPÔT :
# c'est un héritage prudent, pas une mesure locale — doctrine § 3.1.
#
# T-012 — LE BINOME DE CLOTURE EST EXCLU SUR LES CINQ HOTES, et ce n'est pas un
# contournement : c'est le bon regime. Ce levier ECHANGE LES MODELES entre le
# mode `expert` et le mode `pro`. Trois agents dont le modele EST l'identite —
# Opus pour l'audit structurel, Fable pour la logique metier, Sonnet a effort
# maximal pour le repli au ras du code — perdraient leur raison d'etre si un
# levier les echangeait. Le pilote a fixe le binome le 2026-09-12 : Opus + Fable
# en nominal, Opus + Sonnet-max en repli. Le levier n'a rien a dire la-dessus.
#
# CONSEQUENCE SUR LES COMPTES, VERIFIEE AVANT D'ECRIRE : le roster passe de 26 a
# 29 et les cinq nombres d'EXPECTED_TOUCHED restent IDENTIQUES, puisque les trois
# ajouts sont exclus partout. claude 29-1-3=25, gemini 29-3=26, codex 29-3=26,
# github et kimi 29-1-3=25. C'est ce qui a fait choisir cette forme plutot que
# quinze lignes de grille dans MODEL_MODES.md.
# T-00000624 : la PAIRE DE PLAN rejoint le binome de cloture dans cette
# exclusion, et pour la raison IDENTIQUE — `plan-critic-sonnet-max` et
# `planner-sonnet` sont nommes d apres le modele qu ils portent sur Claude Code.
# Echanger ce modele detruirait exactement la propriete qu ils existent pour
# porter : deux modeles ne se trompent pas de la meme facon. Un `plan-critic-
# sonnet-max` promu en opus par le mode `expert` serait un DOUBLON de Critique A,
# c est-a-dire le mode d echec que la paire ferme.
#
# CONSEQUENCE SUR LES COMPTES, VERIFIEE AVANT D ECRIRE : le roster passe de 29 a
# 31 et les cinq nombres d EXPECTED_TOUCHED restent IDENTIQUES, puisque les deux
# ajouts sont exclus partout. claude 31-1-3-2=25, gemini 31-3-2=26, codex
# 31-3-2=26, github et kimi 31-1-3-2=25.
# T-01M4JC50S6CTJ5HJ697929E6N8 : `load-tester` porte le roster de 31 a 32 et N'EST PAS exclu — son
# modele n'est pas son identite, il produit du code (le scenario k6) au tier des
# defs dev (decision pilote Q8, 2026-10-08). Les cinq nombres d EXPECTED_TOUCHED
# prennent donc +1 chacun, verifie avant d ecrire : claude 32-1-3-2=26, gemini
# 32-3-2=27, codex 32-3-2=27, github et kimi 32-1-3-2=26.
# T-01M52X1W3WPKCWX1DC36NMKJB6 : `terraform-deployer` porte le roster de 32 a 33 et N'EST PAS
# exclu, pour la raison de `load-tester` — son modele n'est pas son identite, il produit
# du code (l'IaC Terraform du projet) au tier des defs dev. Les cinq nombres
# d EXPECTED_TOUCHED prennent +1 chacun, mesure avant d ecrire (2026-10-18) : claude
# 33-1-3-2=27, gemini 33-3-2=28, codex 33-3-2=28, github et kimi 33-1-3-2=27.
# T-01M5BZC1Y0T36EHTZY9AKZ650F : `seo-specialist` porte le roster de 33 a 34 et N'EST PAS
# exclu — il n'est pas nomme d'apres son modele, et le mode `expert` ne le
# confond avec aucun autre juge (2026-10-21, branche reprise/2026-10-20).
# T-01M5HEJZ9XVXWQ61XMZYGA3YT0 (2026-10-22) : `reverse-engineer` porte le roster de 33 a 34
# et N'EST PAS exclu — son modele n'est pas son identite : il fait du raisonnement sur
# du code decompile hostile et ne produit pas de code. Il entre au levier dans la
# meme livraison que sa def (parent T-01M5HEBP3C3R9DCZ6G5XYH8J9Q, enfants DEFS
# T-01M5HEJYSJEYA8K3834FZVT60N et DOCTRINE T-01M5HEJZ9XVXWQ61XMZYGA3YT0, porte unique).
# Les deux réunis par la fusion de develop dans reprise/2026-10-20 (2026-10-25) : le
# roster compte 35, les cinq nombres d EXPECTED_TOUCHED prennent +2 sur 33 : claude
# 35-1-3-2=29, gemini 35-3-2=30, codex 35-3-2=30, github et kimi 35-1-3-2=29.
EXCLUDED = {("claude", "orchestrator")} | {
    (hote, critique)
    for hote in ("claude", "gemini", "codex", "github", "kimi")
    for critique in (
        "critic-opus", "critic-fable", "critic-sonnet-max",
        "plan-critic-sonnet-max", "planner-sonnet",
    )
}

# Gelé sur tous les hôtes : sa valeur `expert` est sa valeur de référence.
FROZEN = {"communicator"}

# Vocabulaires CLOS, MESURÉS SUR CET ARBRE (T-00000393), et non repris de la
# source : nos defs claude committent `xhigh` et `max` à HEAD (`fable` reste DANS
# l'échelle sans être écrit par aucune def — voir MODEL_MODES.md § 3.3). Les
# ordres sont ceux de `CLAUDE_MODEL_RANK` / `EFFORT_RANK` de
# `.agents/evals/test_golden_transcripts.py`, du plus faible au plus fort.
# `max` est entré dans l'échelle codex le 2026-10-11 (décision pilote
# S-01M4N2VNE3FP8YT1QH028ZQYJY) ; `plan-critic` codex l'a écrit jusqu'à S-01M57F0BHB
# (2026-10-18), qui le passe en `high` et `planner` en `medium`. L'écrivent
# aujourd'hui `security-code-review-global`, pilotée, et des défs EXCLUDED ;
# `expert` y monte les défs codex pilotées qui portent `xhigh`.
# Les ids gemini sont des littéraux complets, jamais composés par préfixe ou
# suffixe (`gemini-3.5-pro` n'existe pas).
SCALES = {
    ("claude", "model"): ("haiku", "sonnet", "opus", "fable"),
    ("claude", "effort"): ("low", "medium", "high", "xhigh", "max"),
    ("gemini", "model"): ("gemini-3.5-flash", "gemini-3.1-pro"),
    ("codex", "effort"): ("low", "medium", "high", "xhigh", "max"),
}

# Comptes attendus de fichiers traités par hôte — ÉCHEC BRUYANT si divergence
# (code 3, et le fichier d'état n'est pas écrit).
#
# C'est le SEUL littéral de comptage du mécanisme, et il est assumé : une def
# qui disparaît d'un hôte est exactement ce qu'il doit voir. Mesuré sur cet
# arbre le 2026-09-12 : 29 defs par hote. claude = 29 - `orchestrator` - 3
# critiques = 25 ; gemini/codex = 29 - 3 = 26 ; github/kimi = 29 -
# `communicator` - 3 = 25. Les cinq nombres n'ont pas bouge ; c'est leur
# DERIVATION ecrite qui etait perimee.
#
# REMESURÉ le 2026-09-05 (T-00000471) : claude passe de 24 à 25. `communicator`
# y portait 24 parce qu'il n'avait AUCUNE clé de tier et n'était donc pas
# pilotable ; le pilote lui en a donné (`haiku`/`medium`), il devient pilotable
# et entre dans le compte. Il reste GELÉ — `derive()` lui rend sa valeur de
# référence — donc `expert` == `défaut` sur ses deux lignes de grille : il est
# COMPTÉ, jamais AGITÉ. Rien d'autre n'a bougé : `managed_agents()` le prend
# désormais par la branche « a des clés », sans qu'aucune règle change.
#
# REMÈDE quand le roster bouge légitimement : remesurer ces cinq nombres ici,
# le banc les re-dérive de son côté et dira lequel a bougé.
#
# REMESURÉ le 2026-10-08 (T-01M4JC50S6CTJ5HJ697929E6N8) : +1 sur chaque hôte, `load-tester`,
# pilotable et hors `EXCLUDED` — `managed_agents()` rend 26/27/27/26/26.
#
# REMESURÉ le 2026-10-18 (T-01M52X1W3WPKCWX1DC36NMKJB6) : +1 sur chaque hôte, `terraform-deployer`,
# pilotable et hors `EXCLUDED` — `managed_agents()` rend 27/28/28/27/27, 33 defs par
# hôte, `.agents/state/local/MODEL_MODE` absent.
#
# REMESURÉ le 2026-10-21 (T-01M5BZC1Y0T36EHTZY9AKZ650F) : +1 sur chaque hôte, `seo-specialist`,
# pilotable et hors `EXCLUDED` — `managed_agents()` rend 28/29/29/28/28, 34 defs par
# hôte, `.agents/state/local/MODEL_MODE` absent (branche reprise/2026-10-20).
# REMESURÉ le 2026-10-22 (T-01M5HEJZ9XVXWQ61XMZYGA3YT0) : +1 sur chaque hôte, `reverse-engineer`,
# pilotable et hors `EXCLUDED` — `managed_agents()` rend 28/29/29/28/28, 34 defs par
# hôte, dans la même livraison que sa def (parent T-01M5HEBP3C3R9DCZ6G5XYH8J9Q, enfants DEFS
# T-01M5HEJYSJEYA8K3834FZVT60N et DOCTRINE T-01M5HEJZ9XVXWQ61XMZYGA3YT0, porte unique ; develop).
# REMESURÉ le 2026-10-25, fusion de develop dans reprise/2026-10-20 : les deux défs réunies,
# `managed_agents()` rend 29/30/30/29/29, 35 defs par hôte, `.agents/state/local/MODEL_MODE` absent.
EXPECTED_TOUCHED = {"claude": 29, "gemini": 30, "codex": 30, "github": 29, "kimi": 29}

TOKEN_TEMPLATE = (
    "<!-- MODEL-MODE: {mode} — non appliqué sur cet hôte "
    "(aucune clé de tier) ; voir .agents/ref/MODEL_MODES.md -->"
)
TOKEN_RE = re.compile(r"^<!-- MODEL-MODE:.*-->\s*$")

# Garde défensive : aucune ligne insérée ne doit ressembler à une clé de tier.
FORBIDDEN_IN_TOKEN = re.compile(r"^(model:|effort:|model_reasoning_effort)")


class Fail(Exception):
    """Erreur fatale, remontée proprement avec un message et un code non nul."""


def _force_utf8_output() -> None:
    """Sorties en UTF-8, quelle que soit la page de code de la console.

    Sans ceci, sur Windows, un message contenant un caractère absent de la page
    de code locale lève `UnicodeEncodeError` DANS LA GARDE — c'est-à-dire que le
    refus le mieux écrit se transforme en trace d'erreur au moment précis où le
    lecteur en a besoin. Le mécanisme ne doit jamais dépendre de la console.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):  # flux remplacé ou non reconfigurable
            pass


# --------------------------------------------------------------------------
# E/S fidèles aux octets
# --------------------------------------------------------------------------
#
# `Path.read_text` / `Path.write_text` traduisent les fins de ligne. MESURÉ sur
# ce dépôt (Windows, `core.autocrlf=true`, arbre de travail en LF) : un simple
# aller-retour lecture/écriture réécrivait CHAQUE ligne en CRLF, donc tout le
# fichier en diff, donc un aller-retour `expert`→`restore` jamais vide. Avec
# `newline=""` la lecture conserve les `\r` et l'écriture n'en ajoute aucun.


def _read(path: Path) -> str:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return handle.read()


def _write(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def _eol_suffix(lines: list[str]) -> str:
    """`\\r` si le fichier lu est en CRLF — pour insérer une ligne homogène."""
    return "\r" if any(ln.endswith("\r") for ln in lines) else ""


# --------------------------------------------------------------------------
# Localisation des defs
# --------------------------------------------------------------------------


def host_agents(host: str) -> list[str]:
    """Noms d'agents présents pour un hôte, triés, dérivés du disque."""
    directory, pattern, *_ = (
        LEVER_HOSTS[host] if host in LEVER_HOSTS else INDICATIVE_HOSTS[host]
    )
    suffix = pattern.replace("{agent}", "")
    names = sorted(
        p.name[: -len(suffix)]
        for p in (ROOT / directory).iterdir()
        if p.is_file() and p.name.endswith(suffix)
    )
    if not names:
        raise Fail(f"aucune def trouvée pour l'hôte {host} sous {directory}/")
    return names


def def_path(host: str, agent: str) -> Path:
    directory, pattern = (
        LEVER_HOSTS[host][:2] if host in LEVER_HOSTS else INDICATIVE_HOSTS[host]
    )
    return ROOT / directory / pattern.format(agent=agent)


def managed_agents(host: str) -> list[str]:
    """Agents dont ce script pilote effectivement le frontmatter, pour un hôte."""
    out = []
    for agent in host_agents(host):
        if (host, agent) in EXCLUDED:
            continue
        if host in LEVER_HOSTS:
            # Une def sans aucune clé de tier n'est pas pilotable (claude/communicator).
            if not any(read_axis(host, agent, ax) for ax in LEVER_HOSTS[host][2]):
                continue
        elif agent in FROZEN:
            # Volet indicatif : communicator exclu par symétrie avec son gel.
            continue
        out.append(agent)
    return out


# --------------------------------------------------------------------------
# Lecture / écriture d'un axe, ancrées en tête de fichier
# --------------------------------------------------------------------------


def _frontmatter_end(lines: list[str], path: Path) -> int:
    """Index de la 2e ligne `---`. Localisé DYNAMIQUEMENT, jamais codé en dur
    (mesuré côté kimi : cette position varie d'une def à l'autre)."""
    seen = [i for i, ln in enumerate(lines) if ln.rstrip() == "---"]
    if len(seen) < 2:
        raise Fail(f"{path}: frontmatter non refermé (moins de deux lignes `---`)")
    return seen[1]


def _codex_anchor(text: str) -> int:
    """Borne haute des lignes exploitables d'un .toml : tout ce qui suit la
    première triple-quote appartient à `developer_instructions = \"\"\"…\"\"\"`
    et ne doit JAMAIS être réécrit."""
    idx = text.find('"""')
    return len(text) if idx == -1 else idx


def _axis_pattern(host: str, axis: str) -> re.Pattern[str]:
    if host == "codex":
        return re.compile(r'^(model_reasoning_effort\s*=\s*")(\S+?)(")', re.MULTILINE)
    # `\r` toléré en fin de groupe 3 : sans lui, la clé serait introuvable sur un
    # arbre de travail en CRLF (`$` en mode MULTILINE se pose avant le `\n`).
    return re.compile(rf"^({axis}:[ \t]*)(\S+)([ \t\r]*)$", re.MULTILINE)


def _search_region(host: str, text: str, path: Path) -> str:
    """Texte exploitable — la zone hors prose et hors triple-quotes."""
    if host == "codex":
        return text[: _codex_anchor(text)]
    lines = text.split("\n")
    end = _frontmatter_end(lines, path)
    return "\n".join(lines[: end + 1])


def read_axis(host: str, agent: str, axis: str) -> str | None:
    path = def_path(host, agent)
    region = _search_region(host, _read(path), path)
    m = _axis_pattern(host, axis).search(region)
    return m.group(2) if m else None


def write_axis(host: str, agent: str, axis: str, value: str) -> bool:
    """Réécrit un axe. Renvoie True si l'octet sur disque a changé."""
    path = def_path(host, agent)
    text = _read(path)
    region = _search_region(host, text, path)
    m = _axis_pattern(host, axis).search(region)
    if not m:
        raise Fail(f"{path}: aucune clé `{axis}` ancrée en tête de fichier")
    if m.group(2) == value:
        # NO-OP AVANT LA GARDE DE VOCABULAIRE, et l'ordre est le fond du sujet :
        # un AXE ÉPINGLÉ porte sur disque une valeur hors échelle fermée
        # (`claude-opus-5-5`) et sa cible `expert` est cette même valeur. Refuser
        # ici interdirait de traiter la def ; laisser passer une valeur hors
        # échelle plus bas écrirait ce que le mécanisme s'interdit d'écrire.
        return False
    scale = SCALES[(host, axis)]
    if value not in scale:
        raise Fail(
            f"{host}/{agent}: valeur {value!r} hors du vocabulaire clos {scale} "
            "— le script n'écrit jamais en dehors de cette échelle"
        )
    start, end = m.start(), m.end()
    _write(path, text[:start] + m.group(1) + value + m.group(3) + text[end:])
    return True


# --------------------------------------------------------------------------
# Jeton indicatif (hôtes sans levier)
# --------------------------------------------------------------------------


def render_token(mode: str) -> str:
    line = TOKEN_TEMPLATE.format(mode=mode)
    if FORBIDDEN_IN_TOKEN.match(line):
        raise Fail(
            "garde défensive : le jeton indicatif matcherait une clé de tier "
            f"({line!r}) — refus d'insérer une clé parasite sur un hôte sans levier"
        )
    return line


def read_token_mode(host: str, agent: str) -> str | None:
    for ln in _read(def_path(host, agent)).split("\n"):
        if TOKEN_RE.match(ln):
            m = re.search(r"MODEL-MODE:\s*(\S+)", ln)
            return m.group(1) if m else None
    return None


def write_token(host: str, agent: str, mode: str) -> bool:
    """Pose ou met à jour le jeton. Renvoie True si le fichier a changé."""
    line = render_token(mode)
    path = def_path(host, agent)
    text = _read(path)
    lines = text.split("\n")
    line += _eol_suffix(lines)
    hits = [i for i, ln in enumerate(lines) if TOKEN_RE.match(ln)]
    if hits:
        # Mise à jour en place : jamais de duplication, même après N applies.
        if len(hits) > 1:
            for i in reversed(hits[1:]):
                del lines[i]
        if lines[hits[0]] == line and len(hits) == 1:
            return False
        lines[hits[0]] = line
    else:
        lines.insert(_frontmatter_end(lines, path) + 1, line)
    _write(path, "\n".join(lines))
    return True


def remove_token(host: str, agent: str) -> bool:
    """Retire TOUT jeton. Renvoie True si le fichier a changé.

    Suppression de l'élément de liste, jamais mise à blanc : l'insertion et le
    retrait sont exactement inverses, donc l'aller-retour est fidèle à l'octet.
    """
    path = def_path(host, agent)
    text = _read(path)
    lines = text.split("\n")
    hits = [i for i, ln in enumerate(lines) if TOKEN_RE.match(ln)]
    if not hits:
        return False
    for i in reversed(hits):
        del lines[i]
    _write(path, "\n".join(lines))
    return True


# --------------------------------------------------------------------------
# Grille — lue dans MODEL_MODES.md, qui fait autorité
# --------------------------------------------------------------------------


def derive(host: str, agent: str, axis: str, baseline: str) -> str:
    """Valeur `expert` dérivée de la valeur de référence — MODEL_MODES.md § 4.

    Un cran au-dessus, PLAFONNÉ au sommet de l'échelle. Deux cas rendent la
    valeur inchangée, et ce sont des no-op DOCUMENTÉS, pas des erreurs :
      - agent gelé (`communicator`) ;
      - AXE ÉPINGLÉ : la valeur sur disque est hors de l'échelle fermée
        (`claude-opus-5-5`), donc non classable, donc jamais réécrite.
    """
    if agent in FROZEN:
        return baseline
    scale = SCALES[(host, axis)]
    if baseline not in scale:
        return baseline
    return scale[min(scale.index(baseline) + 1, len(scale) - 1)]


def capture_grid() -> dict[tuple[str, str, str], dict[str, str]]:
    """Construit la grille depuis les fichiers VIVANTS."""
    grid: dict[tuple[str, str, str], dict[str, str]] = {}
    for host, (_, _, axes) in LEVER_HOSTS.items():
        for agent in managed_agents(host):
            for axis in axes:
                baseline = read_axis(host, agent, axis)
                if baseline is None:
                    raise Fail(f"{host}/{agent}: axe `{axis}` introuvable")
                grid[(host, agent, axis)] = {
                    BASELINE: baseline,
                    EXPERT: derive(host, agent, axis, baseline),
                }
    return grid


def render_grid(grid: dict[tuple[str, str, str], dict[str, str]]) -> str:
    rows = [
        f"| hôte | agent | axe | {BASELINE} | {EXPERT} |",
        "|---|---|---|---|---|",
    ]
    for host, agent, axis in sorted(grid):
        v = grid[(host, agent, axis)]
        rows.append(
            f"| `{host}` | `{agent}` | {axis} | `{v[BASELINE]}` | `{v[EXPERT]}` |"
        )
    return "\n".join(rows)


ROW_RE = re.compile(
    r"^\|\s*`([^`]+)`\s*\|\s*`([^`]+)`\s*\|\s*(\w+)\s*\|"
    r"\s*`([^`]+)`\s*\|\s*`([^`]+)`\s*\|\s*$"
)


def _split_grid_block(text: str) -> tuple[str, str, str, str]:
    """(tête, texte du marqueur d'ouverture, corps, queue).

    ÉCHEC NOMMÉ, jamais une exception brute : le fichier ET les deux marqueurs
    attendus sont cités, parce que c'est un fichier édité à la main.
    """
    head, sep, rest = text.partition(GRID_BEGIN)
    if not sep:
        raise Fail(
            f"{DOC}: marqueur d'ouverture `{GRID_BEGIN}` introuvable — le bloc de "
            f"grille `{GRID_BEGIN}` … `{GRID_END}` doit exister dans ce fichier"
        )
    marker, gt, body_and_tail = rest.partition(">")
    if not gt or "\n" in marker:
        raise Fail(
            f"{DOC}: marqueur `{GRID_BEGIN}` malformé — sa ligne doit se refermer "
            "par `>` sur la MÊME ligne"
        )
    body, sep2, tail = body_and_tail.partition(GRID_END)
    if not sep2:
        raise Fail(
            f"{DOC}: marqueur de fermeture `{GRID_END}` introuvable après "
            f"`{GRID_BEGIN}` — bloc de grille non refermé"
        )
    return head, marker, body, tail


def load_grid() -> dict[tuple[str, str, str], dict[str, str]]:
    if not DOC.exists():
        raise Fail(f"capture absente : {DOC} n'existe pas")
    _, _, body, _ = _split_grid_block(_read(DOC))
    grid: dict[tuple[str, str, str], dict[str, str]] = {}
    for ln in body.split("\n"):
        m = ROW_RE.match(ln.strip())
        if m:
            host, agent, axis, baseline, expert = m.groups()
            grid[(host, agent, axis)] = {BASELINE: baseline, EXPERT: expert}
    return grid


def save_grid(grid: dict[tuple[str, str, str], dict[str, str]]) -> None:
    if not DOC.exists():
        raise Fail(f"capture absente : {DOC} n'existe pas")
    head, marker, _, tail = _split_grid_block(_read(DOC))
    _write(
        DOC,
        f"{head}{GRID_BEGIN}{marker}>\n\n{render_grid(grid)}\n\n{GRID_END}{tail}",
    )


# --------------------------------------------------------------------------
# État courant
# --------------------------------------------------------------------------


def current_mode() -> str:
    """Mode enregistré. Fichier ABSENT ⇒ état de référence (`défaut`)."""
    if not MODE_FILE.exists():
        return BASELINE
    value = _read(MODE_FILE).strip()
    if value not in MODES:
        raise Fail(
            f"{MODE_FILE}: mode {value!r} inconnu (attendu {MODES}, ou fichier "
            "absent pour l'état de référence)"
        )
    return value


def deviations(
    grid: dict[tuple[str, str, str], dict[str, str]], column: str
) -> list[str]:
    """Écarts entre le disque et la colonne `column` de la grille."""
    out = []
    for (host, agent, axis), values in sorted(grid.items()):
        actual = read_axis(host, agent, axis)
        if actual != values[column]:
            out.append(
                f"{host}/{agent}.{axis}: disque={actual!r} attendu={values[column]!r}"
            )
    return out


def token_deviations(mode: str) -> list[str]:
    """Jetons indicatifs désynchronisés du mode enregistré.

    En état de référence l'attendu est l'ABSENCE de jeton — `restore` les retire.
    """
    expected = EXPERT if mode == EXPERT else None
    out = []
    for host in INDICATIVE_HOSTS:
        for agent in managed_agents(host):
            seen = read_token_mode(host, agent)
            if seen != expected:
                out.append(f"{host}/{agent}: jeton={seen!r} attendu={expected!r}")
    return out


# --------------------------------------------------------------------------
# Commandes
# --------------------------------------------------------------------------


def cmd_status() -> int:
    mode = current_mode()
    origin = str(MODE_FILE) if MODE_FILE.exists() else "fichier absent"
    grid = load_grid()
    print(f"MODE ENREGISTRÉ : {mode}   [source : {origin}]")
    print(f"Grille          : {len(grid)} lignes (hôte, agent, axe) — {DOC}")

    devs = deviations(grid, mode)
    if devs:
        print(f"\nÉCARTS ({len(devs)}) — état sur disque != mode enregistré :")
        for d in devs[:10]:
            print(f"  - {d}")
        if len(devs) > 10:
            print(f"  … {len(devs) - 10} de plus (borne d'affichage)")
    else:
        print("\nAucun écart : l'état sur disque correspond au mode enregistré.")

    tdevs = token_deviations(mode)
    if tdevs:
        print(f"\nJETONS INDICATIFS DÉSYNCHRONISÉS ({len(tdevs)}) :")
        for d in tdevs[:10]:
            print(f"  - {d}")
        if len(tdevs) > 10:
            print(f"  … {len(tdevs) - 10} de plus (borne d'affichage)")

    print(
        "\nCe rapport CONSTATE un écart, il ne GARANTIT pas l'absence de dérive :\n"
        "l'hôte Claude Code réécrit seul certains frontmatters en cours de session\n"
        "(LEDGER op-agentic L-00000068, portée non re-mesurée ici). C'est de la\n"
        "transparence sur cette limite."
    )
    return 1 if (devs or tdevs) else 0


def cmd_apply(column: str, recapture: bool, quiet: bool) -> int:
    if recapture:
        # --- GARDE C3, AVANT TOUT OCTET ÉCRIT ---------------------------------
        # Ré-ancrer la colonne de référence sur un arbre qui n'est PAS à l'état
        # de référence graverait l'état monté comme nouvelle référence : le
        # retour en arrière deviendrait impossible, en silence. Le fichier
        # d'état présent est le seul témoin mécanique disponible.
        if MODE_FILE.exists():
            print(
                f"REFUS : {MODE_FILE} existe (mode enregistré : {_read(MODE_FILE).strip()!r}),\n"
                "l'arbre n'est donc PAS à l'état de référence. Ré-ancrer la colonne "
                f"`{BASELINE}` ici\ngraverait l'état monté comme nouvelle référence.\n"
                "AUCUN octet écrit.\n"
                "REMÈDE : `python core-scripts/apply-mode.py restore` (SANS --recapture) "
                "d'abord,\npuis relancez `restore --recapture` sur l'arbre revenu à sa "
                "référence.",
                file=sys.stderr,
            )
            return 2
        grid = capture_grid()
        save_grid(grid)
        print(f"RECAPTURE : colonne `{BASELINE}` ré-ancrée sur les fichiers vivants ({DOC})")
    else:
        grid = load_grid()
        if not grid:
            raise Fail(
                f"{DOC}: grille vide — amorcez-la avec "
                "`python core-scripts/apply-mode.py restore --recapture`"
            )

    # --- Garde de dérive, AVANT tout octet écrit --------------------------
    #
    # Elle protège `expert` et JAMAIS `restore` : `restore` EST la réparation,
    # une réparation qui se refuse ne répare rien.
    #
    # Elle est FERMANTE : dès qu'une seule def dérive, RIEN n'est écrit et les
    # defs fautives sont nommées. Un refus par fichier laisserait un arbre
    # MIXTE — mesuré chez la source pendant la mise au point : 76 fichiers
    # écrits avant l'abandon, avec un fichier d'état resté sur la référence,
    # c'est-à-dire exactement l'état que cette garde existe pour empêcher.
    if column == EXPERT:
        # Grille COMPLÈTE, vérifiée elle aussi AVANT tout octet écrit
        # (T-01M52X1W3WPKCWX1DC36NMKJB6, 2026-10-18). Le contrôle `grille incomplète`
        # de la boucle d'écriture ne mordait qu'APRÈS les defs triées avant la
        # ligne manquante — mesuré : une def neuve sans ligne de grille, et
        # `expert` écrivait 23 defs claude puis échouait, arbre MIXTE. Toutes les
        # lignes absentes sont nommées d'un coup.
        missing = [
            f"{host}/{agent}.{axis}"
            for host, (_, _, axes) in LEVER_HOSTS.items()
            for agent in managed_agents(host)
            for axis in axes
            if (host, agent, axis) not in grid
        ]
        if missing:
            raise Fail(
                f"grille incomplète : {', '.join(missing)} absent(s) — AUCUN octet "
                "écrit. REMÈDE : `python core-scripts/apply-mode.py restore "
                "--recapture` sur l'arbre revenu à sa référence"
            )
        prev = current_mode()
        refused: set[tuple[str, str]] = set()
        for dev in deviations(grid, prev):
            host, rest = dev.split("/", 1)
            refused.add((host, rest.split(".", 1)[0]))
            print(f"REFUS  {dev}  (mode enregistré : {prev}) — non modifié")
        if refused:
            print(
                f"\nÉCHEC : {len(refused)} def(s) en dérive — AUCUN octet écrit, "
                "et le mode enregistré est inchangé.\n"
                "Restaurez les defs (`git checkout --` ou "
                "`python core-scripts/apply-mode.py restore`)."
            )
            return 2

    touched = {h: 0 for h in list(LEVER_HOSTS) + list(INDICATIVE_HOSTS)}
    changed = {h: 0 for h in touched}

    # --- Hôtes à levier
    for host, (_, _, axes) in LEVER_HOSTS.items():
        for agent in managed_agents(host):
            for axis in axes:
                key = (host, agent, axis)
                if key not in grid:
                    raise Fail(f"grille incomplète : {host}/{agent}.{axis} absent")
                if write_axis(host, agent, axis, grid[key][column]):
                    changed[host] += 1
            touched[host] += 1

    # --- Hôtes sans levier : jeton posé en `expert`, RETIRÉ au retour.
    for host in INDICATIVE_HOSTS:
        for agent in managed_agents(host):
            hit = (
                write_token(host, agent, column)
                if column == EXPERT
                else remove_token(host, agent)
            )
            if hit:
                changed[host] += 1
            touched[host] += 1

    # --- Le fichier d'état s'écrit EN DERNIER : il ne doit jamais annoncer un
    # --- état qui n'a pas été atteint. Au retour il est SUPPRIMÉ — l'absence
    # --- de fichier EST l'état de référence, pas une valeur à écrire.
    ok = all(touched[h] == EXPECTED_TOUCHED[h] for h in EXPECTED_TOUCHED)
    if ok:
        if column == EXPERT:
            MODE_FILE.parent.mkdir(parents=True, exist_ok=True)
            _write(MODE_FILE, EXPERT + "\n")
        else:
            MODE_FILE.unlink(missing_ok=True)

    if not quiet:
        label = EXPERT if column == EXPERT else f"{BASELINE} (restore)"
        print(f"\nÉTAT APPLIQUÉ : {label}")
        for host in list(LEVER_HOSTS) + list(INDICATIVE_HOSTS):
            flag = "ok" if touched[host] == EXPECTED_TOUCHED[host] else "DIVERGENCE"
            kind = "levier" if host in LEVER_HOSTS else "indicatif"
            print(
                f"  {host:<7} {kind:<10} traités={touched[host]:>2}"
                f" attendus={EXPECTED_TOUCHED[host]:>2}"
                f"  modifiés={changed[host]:>2}  {flag}"
            )

    if not ok:
        print(
            "\nÉCHEC : compte de fichiers traités divergent de l'attendu — "
            "fichier d'état NON écrit.",
            file=sys.stderr,
        )
        return 3
    if not quiet:
        print(
            f"État écrit dans {MODE_FILE}"
            if column == EXPERT
            else f"Fichier d'état supprimé ({MODE_FILE}) — retour à la référence"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="apply-mode.py",
        description=(
            "Monte d'un cran le tier de modèle / l'effort des agents (`expert`), "
            "ou revient à la capture de référence (`restore`). UPGRADE SEULEMENT : "
            "aucun mode descendant n'existe, AGENTS.md § Full power l'interdit. "
            "Tourne sous python3 (stdlib seule). Doctrine et grille : "
            ".agents/ref/MODEL_MODES.md"
        ),
        epilog=(
            "Le dépôt ne se committe JAMAIS en `expert` : repassez par `restore` "
            "avant tout commit."
        ),
    )
    parser.add_argument(
        "command",
        choices=(EXPERT, "restore", "status"),
        help="expert = monte d'un cran ; restore = revient à la référence ; status = état",
    )
    parser.add_argument(
        "--recapture",
        action="store_true",
        help=(
            "RESTORE UNIQUEMENT : ré-ancre la colonne de référence de "
            "MODEL_MODES.md sur les fichiers vivants au lieu d'imposer "
            "l'ancienne capture. Refusé si un mode est enregistré."
        ),
    )
    parser.add_argument("--quiet", action="store_true", help="réduit la sortie")
    _force_utf8_output()
    args = parser.parse_args(argv)

    # `--recapture` n'a de sens que sur `restore` : il ré-ancre la colonne de
    # RÉFÉRENCE. argparse ne sait pas exprimer cette dépendance dans `choices`,
    # donc elle est refusée ici — `parser.error` sort en 2 sans écrire un octet.
    if args.recapture and args.command != "restore":
        parser.error(
            f"--recapture n'est accepté qu'avec `restore` (reçu : {args.command!r})"
        )

    try:
        if args.command == "status":
            return cmd_status()
        column = EXPERT if args.command == EXPERT else BASELINE
        return cmd_apply(column, args.recapture, args.quiet)
    except Fail as exc:
        print(f"apply-mode: {exc}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    sys.exit(main())
