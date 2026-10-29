"""LES HUIT JUGES COPILOT TIENNENT LES CLAUSES DE LEUR DÉF CLAUDE — T-01M5MCXMQVHZ231CW0K2JR76MD, lot A.

POURQUOI. Décision pilote S-01M5MCXYV352ZNNW7ZC75T8DJH : les défs de juge Copilot étaient condensées
au point de perdre des clauses que la déf Claude porte (bannière, lecture seule, BANCS-BORNES, trois
blocs) et la borne du palier : Copilot n'épingle ni modèle ni effort, donc aucune relation de palier
n'y est tenue par la machine. Mesure sur la base 3b119448e, `fautes()` rejouée sur les textes de
ce commit : 27 fautes (les quatre sections de `security-code-review` comprises), toutes dans sept défs.

CE QUE CE BANC TIENT, pour chacun des huit juges de `JUGES` :
* (1) Claude ⇒ Copilot : une clause présente dans `.claude/agents/<n>.md` l'est aussi dans
  `.github/agents/<n>.agent.md` — bannière `▸ <n> ⚙` et `▸ <n> ✓`, lecture seule, `BANCS-BORNES`,
  les trois blocs (TROUS REPÉRÉS, TROUVAILLES, CORRECTIFS CONCRETS).
* (2) Copilot seul : « pins no model » et « strongest available tier » ; la borne « a tier relation
  cannot be enforced here » ; une borne doctrinale de la lecture seule nommée ; AUCUNE ligne
  `model:` au frontmatter (l'hôte n'en porte pas).
* (3) `security-code-review` porte les sections de sa déf Claude (Scope, What you hunt, Rules, Output).
* (4) Contrôles négatifs : chaque mutant de `MUTANTS`, appliqué à une copie en mémoire du texte
  vivant, fait apparaître une faute ; une déf Copilot sans frontmatter est une faute (fail-closed).

CE QU'IL NE PROUVE PAS (bornes nommées) : la présence d'un MOT n'est pas la présence d'une RÈGLE — une
clause peut garder son mot-clé et perdre sa portée ; le reste des corps n'est pas comparé ; que
Copilot honore ces consignes à l'exécution n'est pas observé (aucun hôte n'est lancé). Le conflit
avec la tâche du board T-01M4RWCGVMQ3 (« Étagement des modèles des défs Copilot ») est tranché par
la décision pilote S-01M5N1WS79 : juges Copilot SANS `model:`, T-01M4RWCGVMQ3 close caduque.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

JUGES = ("plan-critic", "exec-critic", "design-review", "critic-opus", "critic-fable",
         "critic-sonnet-max", "security-code-review", "security-code-review-global")

Clause = Callable[[str, str], bool]

CLAUSES_CLAUDE: dict[str, Clause] = {
    # English only since T-01M5S9338BJP1B5RM3TG14AMYT (defs in English): the French forms of before
    # no longer satisfy the clause — `MUTANTS` holds a French-form mutant for each.
    "lecture-seule": lambda n, t: bool(re.search(r"(?i)read-only", t)),
    "bancs": lambda n, t: "BANCS-BORNES" in t,
    "trois-blocs": lambda n, t: all(k in t for k in ("TROUS REPÉRÉS", "TROUVAILLES", "CORRECTIFS CONCRETS")),
    "banniere": lambda n, t: f"▸ {n} ⚙" in t and f"▸ {n} ✓" in t,
}

BORNE_DOCTRINALE = re.compile(
    r"ENFORCES here is PARTIAL|How read-only is enforced here|[Rr]ead-only by doctrine")


def _frontmatter(texte: str) -> str | None:
    lignes = texte.replace("\r\n", "\n").split("\n")
    if not lignes or lignes[0] != "---":
        return None
    try:
        fin = lignes.index("---", 1)
    except ValueError:
        return None
    return "\n".join(lignes[1:fin])


def _sans_model(n: str, t: str) -> bool:
    fm = _frontmatter(t)
    return fm is not None and not re.search(r"(?m)^model:", fm)


CLAUSES_COPILOT: dict[str, Clause] = {
    "palier": lambda n, t: "strongest available tier" in t and "pins no model" in t,
    "borne-doctrinale": lambda n, t: bool(BORNE_DOCTRINALE.search(t)),
    "borne-palier": lambda n, t: "a tier relation cannot be enforced here" in t,
    "sans-model": _sans_model,
}

SECTIONS_SCR = ("## Scope (hard)", "## What you hunt", "## Rules", "## Output")


def fautes(defs: dict[str, tuple[str, str]]) -> list[tuple[str, str]]:
    """`defs` : nom -> (texte Claude, texte Copilot). Rend la liste (nom, clause) des fautes."""
    out: list[tuple[str, str]] = []
    for n, (claude, copilot) in defs.items():
        for k, f in CLAUSES_CLAUDE.items():
            if f(n, claude) and not f(n, copilot):
                out.append((n, k))
        for k, f in CLAUSES_COPILOT.items():
            if not f(n, copilot):
                out.append((n, k))
        if n == "security-code-review":
            for s in SECTIONS_SCR:
                if s in claude and s not in copilot:
                    out.append((n, f"section {s}"))
    return out


def _lire(rel: str) -> str:
    p = ROOT / rel
    assert p.is_file(), f"{rel} absent : ce banc lit chaque déf, un absent est un échec"
    return p.read_text(encoding="utf-8")


def _vivant() -> dict[str, tuple[str, str]]:
    return {n: (_lire(f".claude/agents/{n}.md"), _lire(f".github/agents/{n}.agent.md")) for n in JUGES}


def test_les_huit_juges_copilot_sont_en_parite():
    trouvees = fautes(_vivant())
    assert trouvees == [], "\n".join(f"{n}: {k}" for n, k in trouvees)


def test_les_sections_claude_de_security_code_review_existent():
    # Témoin : le contrôle (3) ne compare rien si la déf Claude perd ses sections.
    claude = _lire(".claude/agents/security-code-review.md")
    assert [s for s in SECTIONS_SCR if s not in claude] == []


def _retirer(nom: str, motif: str) -> Callable[[dict[str, tuple[str, str]]], None]:
    def muter(defs: dict[str, tuple[str, str]]) -> None:
        claude, copilot = defs[nom]
        assert motif in copilot, f"mutant sans prise : « {motif} » absent de {nom}"
        defs[nom] = (claude, copilot.replace(motif, ""))
    return muter


def _franciser(nom: str, motif: str, francais: str) -> Callable[[dict[str, tuple[str, str]]], None]:
    """Remet, dans la déf Copilot, la forme FRANÇAISE d'avant à la place de chaque occurrence
    (casse ignorée) de la forme anglaise : la re-épingle anglaise doit rougir."""
    def muter(defs: dict[str, tuple[str, str]]) -> None:
        claude, copilot = defs[nom]
        francise = re.sub(re.escape(motif), francais, copilot, flags=re.IGNORECASE)
        assert francise != copilot, f"mutant sans prise : « {motif} » absent de {nom}"
        defs[nom] = (claude, francise)
    return muter


def _inserer_model(nom: str) -> Callable[[dict[str, tuple[str, str]]], None]:
    def muter(defs: dict[str, tuple[str, str]]) -> None:
        claude, copilot = defs[nom]
        assert copilot.startswith("---\n")
        defs[nom] = (claude, "---\nmodel: x\n" + copilot[4:])
    return muter


def _sans_frontmatter(nom: str) -> Callable[[dict[str, tuple[str, str]]], None]:
    def muter(defs: dict[str, tuple[str, str]]) -> None:
        claude, copilot = defs[nom]
        defs[nom] = (claude, copilot.replace("---", "", 2))
    return muter


MUTANTS = (
    ("banniere-critic-opus", _retirer("critic-opus", "▸ critic-opus ✓"), ("critic-opus", "banniere")),
    ("borne-palier-exec-critic", _retirer("exec-critic", "a tier relation cannot be enforced here"),
     ("exec-critic", "borne-palier")),
    ("trois-blocs-critic-fable", _retirer("critic-fable", "CORRECTIFS CONCRETS"), ("critic-fable", "trois-blocs")),
    ("model-security-code-review", _inserer_model("security-code-review"), ("security-code-review", "sans-model")),
    ("doctrine-critic-sonnet-max", _retirer("critic-sonnet-max", "Read-only by doctrine"),
     ("critic-sonnet-max", "borne-doctrinale")),
    ("rules-security-code-review", _retirer("security-code-review", "## Rules"),
     ("security-code-review", "section ## Rules")),
    ("palier-design-review", _retirer("design-review", "strongest available tier"), ("design-review", "palier")),
    ("sans-frontmatter-plan-critic", _sans_frontmatter("plan-critic"), ("plan-critic", "sans-model")),
    # T-01M5S9338BJP1B5RM3TG14AMYT : les formes FRANÇAISES d'avant ne satisfont plus les clauses.
    ("doctrine-fr-critic-sonnet-max", _franciser("critic-sonnet-max", "Read-only by doctrine",
                                                  "Lecture seule par doctrine"),
     ("critic-sonnet-max", "borne-doctrinale")),
    ("lecture-seule-fr-exec-critic", _franciser("exec-critic", "read-only", "lecture seule"),
     ("exec-critic", "lecture-seule")),
)


@pytest.mark.parametrize("nom,muter,attendue", MUTANTS, ids=[m[0] for m in MUTANTS])
def test_chaque_mutant_fait_une_faute(nom, muter, attendue):
    defs = _vivant()
    muter(defs)
    assert attendue in fautes(defs), f"mutant {nom} non vu"
