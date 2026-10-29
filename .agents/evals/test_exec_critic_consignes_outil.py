"""LES CINQ DÉFS EXEC-CRITIC PORTENT LEUR BLOC « Tool hygiene » — T-01M5PY2DZ8W7744BMDNVHB3FZ6, lot B (témoin B).

POURQUOI. R4 de l'audit 2026-10-24 : sous `isolation: "worktree"`, un sous-agent Claude Code voit refusée
toute commande composée ou opaque, et une lecture de plus de 25000 jetons. Le juge d'exécution reçoit
donc, sur chaque hôte, cinq lignes de gestes d'outil JUSTE AVANT l'ancre Rules, au vocabulaire de l'hôte,
avec la portée de chaque refus dite par hôte (L-00000079) : « measured » chez Claude Code seul,
« assumed » chez Kimi seul, « hygiene here » ailleurs.

CE QUE CE BANC TIENT, sur les cinq chemins NOMMÉS de `DEFS` (aucun glob ; un absent est une faute) :
* le titre du bloc existe et précède la PREMIÈRE occurrence de l'ancre Rules de l'hôte ; le bloc
  (du titre à l'ancre) porte exactement cinq puces ;
* les atomes a1-a5 sont lus DANS LE BLOC extrait, jamais dans le fichier (critic-2 K1 : « assumed »
  figure déjà hors bloc dans quatre défs de base) ;
* portée : « refused by Claude Code (measured) » dans le bloc Claude seul ; « assumed » dans le bloc
  Kimi seul ; « Read before Edit » absent de chaque déf (exec-critic n'édite pas) ; bloc Codex ASCII.

Racine : `CONSIGNES_OUTIL_ROOT` (défaut : la racine du dépôt), pour rejouer les mutants sur une copie.

CE QU'IL NE PROUVE PAS : la présence d'un atome n'est pas l'obéissance de l'hôte ; aucun hôte n'est lancé ;
le reste des défs n'est pas comparé.
"""
from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

import pytest

DEPOT = Path(__file__).resolve().parents[2]

# hôte -> (chemin, titre du bloc, ancre Rules)
DEFS: dict[str, tuple[str, str, str]] = {
    "claude": (".claude/agents/exec-critic.md", "\n## Tool hygiene\n", "\n## Rules\n"),
    "codex": (".codex/agents/exec-critic.toml", "\nTool hygiene:\n", "\nRules:\n"),
    "gemini": (".gemini/agents/exec-critic.md", "\n## Tool hygiene\n", "\n## Rules\n"),
    "copilot": (".github/agents/exec-critic.agent.md", "\n**Tool hygiene.**\n", "\nRules. "),
    "kimi": (".kimi-code/agents/exec-critic.md", "\n## Tool hygiene\n", "\n## Rules\n"),
}

COMMUNS = ("one plain command per call", '`isolation: "worktree"`', "`git -C /tmp/cadre-",
           "quote every glob", "`*.tfstate`", "iac_guard", "never route around")
ECONOMIE = "AGENTS.md § ÉCONOMIE (1)"
ECONOMIE_ASCII = "ECONOMIE (1)"
PORTEE_CLAUDE = "refused by Claude Code (measured)"
PORTEE_AILLEURS = "hygiene here; the refusal is Claude Code's, not measured on this host"
A5: dict[str, tuple[str, ...]] = {
    "claude": ("offset/limit", "25000 tokens"),
    "kimi": ("offset/limit", "assumed"),
    "codex": ("bounded read",),
    "gemini": ("bounded read",),
    "copilot": ("bounded read",),
}


def racine() -> Path:
    env = os.environ.get("CONSIGNES_OUTIL_ROOT")
    return Path(env) if env else DEPOT


def lire(root: Path) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for hote, (rel, _, _) in DEFS.items():
        p = root / rel
        out[hote] = p.read_text(encoding="utf-8") if p.is_file() else None
    return out


def bloc(hote: str, texte: str) -> str | None:
    """Le bloc du titre à la première ancre Rules, ou None si le titre manque ou suit l'ancre."""
    _, titre, ancre = DEFS[hote]
    i, j = texte.find(titre), texte.find(ancre)
    if i < 0 or j < 0 or i > j:
        return None
    return texte[i + len(titre):j]


def fautes(textes: dict[str, str | None]) -> list[str]:
    out: list[str] = []
    for hote, (rel, _, _) in DEFS.items():
        texte = textes.get(hote)
        if texte is None:
            out.append(f"{hote}: {rel} absent")
            continue
        if "read before edit" in texte.lower():
            out.append(f"{hote}: « Read before Edit » dans une déf qui n'édite pas")
        b = bloc(hote, texte)
        if b is None:
            out.append(f"{hote}: bloc absent ou après l'ancre Rules")
            continue
        puces = [ln for ln in b.split("\n") if ln.startswith("- ")]
        if len(puces) != 5 or b.strip().count("\n") != 4:
            out.append(f"{hote}: bloc de {len(puces)} puces, 5 attendues")
        bas = b.lower()
        for a in COMMUNS:
            if a.lower() not in bas:
                out.append(f"{hote}: atome absent {a!r}")
        if hote == "codex":
            if ECONOMIE_ASCII not in b:
                out.append("codex: atome absent 'ECONOMIE (1)'")
            if not b.isascii():
                out.append("codex: bloc non ASCII")
        elif ECONOMIE not in b:
            out.append(f"{hote}: atome absent {ECONOMIE!r}")
        if hote == "claude":
            if PORTEE_CLAUDE not in b:
                out.append("claude: portée Claude absente")
        else:
            if PORTEE_AILLEURS not in b:
                out.append(f"{hote}: portée d'hôte absente")
            if "(measured)" in b:
                out.append(f"{hote}: portée Claude hors Claude")
        if ("assumed" in bas) != (hote == "kimi"):
            out.append(f"{hote}: « assumed » {'absent' if hote == 'kimi' else 'hors Kimi'}")
        for a in A5[hote]:
            if a not in b:
                out.append(f"{hote}: a5 absent {a!r}")
    return out


def test_les_cinq_exec_critic_portent_le_bloc():
    assert fautes(lire(racine())) == []


def _deplacer_apres_rules(t: str) -> str:
    _, titre, ancre = DEFS["claude"]
    i, j = t.find(titre), t.find(ancre)
    b = t[i:j]
    reste = t[:i] + t[j:]
    k = reste.find(ancre) + len(ancre)
    return reste[:k] + b.lstrip("\n") + "\n" + reste[k:]


Mutant = tuple[str, str, Callable[[str], str], str]
MUTANTS: list[Mutant] = [
    ("B-m1", "claude", _deplacer_apres_rules, "après l'ancre Rules"),
    ("B-m2", "copilot", lambda t: t.replace("bounded read", "short read", 1), "a5 absent"),
    ("B-m3", "gemini", lambda t: t.replace("## Rules\n", "## Rules\n\nRead before Edit.\n", 1),
     "Read before Edit"),
    ("B-m4", "kimi", lambda t: t.replace("(assumed to hold)", "", 1).replace("is assumed here", "is unknown here", 1),
     "« assumed » absent"),
    ("B-m5", "gemini", lambda t: t.replace("not measured on this host.", "refused by Claude Code (measured).", 1),
     "portée"),
    ("B-m6", "codex", lambda t: t.replace("ECONOMIE (1)", "ÉCONOMIE (1)", 1), "codex"),
    ("B-m7", "claude", lambda t: t.replace("- A refused command", "A refused command", 1), "puces"),
    ("B-m8", "copilot", lambda t: t.replace("never route around the guard", "never skip the guard", 1),
     "never route around"),
]


@pytest.mark.parametrize("nom,hote,muter,attendu", MUTANTS, ids=[m[0] for m in MUTANTS])
def test_chaque_mutant_rougit(nom: str, hote: str, muter: Callable[[str], str], attendu: str):
    textes = lire(DEPOT)
    vivant = textes[hote]
    assert vivant is not None
    mute = muter(vivant)
    assert mute != vivant, f"{nom} : le mutant ne change rien, il ne prouve rien"
    textes[hote] = mute
    f = fautes(textes)
    assert any(attendu in x for x in f), f"{nom} survit : {f}"


def test_racine_vide_rougit(tmp_path: Path):
    f = fautes(lire(tmp_path))
    assert len(f) == len(DEFS) and all("absent" in x for x in f), f
