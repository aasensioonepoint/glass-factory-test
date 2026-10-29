"""LA TABLE ÉVÉNEMENT CANONIQUE → GRAPHIE NATIVE, PAR HÔTE.

Un événement CANONIQUE est un élément `type: evenement` de `contract.lock.json`,
privé de son préfixe `hook:` — `hook:Stop` donne `Stop`. Le verrou en déclare
dix, tous `public`. Pour chacun, et pour chacun des cinq hôtes de la liste
fermée `HOTES` (`cadre.config`), la table dit sous quel NOM l'hôte le déclare.

CE QUE « GRAPHIE NATIVE » VEUT DIRE ICI, ET RIEN DE PLUS. C'est la CLÉ que le
kit ÉCRIT sous `hooks` dans le registre natif de l'hôte (`REGISTRES`), relevée
au sha `RELEVE_SHA`. Ce n'est PAS un nom mesuré au déclenchement : le verrou dit
lui-même que c'est la DÉCLARATION qui est relevée, et que la couverture réelle
au runtime est 3 mesurés / 0 hérité / 1 supposé / 2 inertes-mesurés. La table
sert à TRADUIRE (répartiteur, injection native) ; elle ne prouve pas qu'un hôte
déclenche quoi que ce soit.

UNE ABSENCE SE DIT, ELLE NE S'OMET PAS. Quand le registre d'un hôte ne déclare
pas un événement, la cellule existe quand même : `Graphie(None, raison=…)`. La
raison dit ce qui est relevé — le registre n'en porte pas de clé, et le verrou
dit l'événement « DECLARE par Claude Code SEUL » — et ce qui ne l'est pas : la
documentation de l'hôte n'est pas relevée ici, donc la table n'affirme ni qu'un
équivalent natif existe, ni qu'il manque.

ANTIGRAVITY N'EST PAS UNE COLONNE (décision pilote S-00001606). Il n'a aucune
surface livrée à lui et HÉRITE du registre de gemini (`.agents/hooks.json`) :
une sixième valeur ferait mesurer deux fois la même chose. `HERITIERS` le dit
en donnée. Mais la ligne gemini porte les graphies d'OUTIL que le registre
déclare pour les deux hôtes — `Bash|run_command` et `Edit|Write|apply_patch` —
et `GRAPHIES_ANTIGRAVITY` les expose : un rendu du registre qui les omettrait
les ferait disparaître à la régénération, et les gardes shell deviendraient
muettes sur cet hôte sans aucun rouge. La garde d'édition y est déjà inerte par
déduction (relevé R13, `docs/tasks/T-00000791-releve.md:46`), `apply_patch`
n'étant pas un outil documenté de cet hôte.

DEUX DIVERGENCES DE NOMS (événement, outil) ENTRE LA DÉCLARATION ET LA
DOCUMENTATION — bornées aux relevés R11/R13/R14 ; la lecture du registre
(R10 : gemini, kimi) et la graphie VS Code de Copilot ne sont pas portées par
la table. La table porte la graphie DÉCLARÉE ; ces deux écarts, consignés et
non résolus, sont relevés dans `.agents/ref/DOCS_REGISTRY.md` et dans
`docs/tasks/T-00000791-releve.md`, et restent ouverts :

* gemini — la référence des hooks de Gemini CLI nomme `BeforeTool`,
  `AfterTool`, `AfterAgent`, `PreCompress`…, sans alias aux noms de Claude, et
  ne lit que `settings.json` → `hooks` ; `.agents/hooks.json` n'y est jamais
  nommé. La documentation d'Antigravity nomme ce registre et les événements
  `PreToolUse`, `PostToolUse`, `PreInvocation`, `PostInvocation`, `Stop`.
  Quatre des six clés de la ligne gemini sont nommées par la documentation
  d'au moins un des deux hôtes (`SessionStart` chez Gemini CLI — relevé R11,
  `docs/tasks/T-00000791-releve.md:44`, et `data/capacites_hotes.json`,
  gemini → contexte_session ; `PreToolUse`, `PostToolUse`, `Stop` chez
  Antigravity) ; `PreCompact` et `SubagentStop` par aucune, et la table les
  porte telles que le registre les déclare — `NON_DOCUMENTEES` les nomme en
  donnée. La divergence est à trancher par T-00000817 (P0, ouverte au
  relevé) ; si Gemini CLI ne lit pas ce registre, la colonne ne sert plus
  qu'Antigravity — et c'est MESURÉ depuis (G0, 2026-10-12, Gemini CLI
  0.63.0 : `.agents/hooks.json` n'est pas lu, le hook ne part jamais).
* antigravity — sa documentation nomme l'outil shell `run_command` (relevé
  R14, `docs/tasks/T-00000791-releve.md:47`), et pour
  l'édition `write_to_file`, `replace_file_content`,
  `multi_replace_file_content` : `apply_patch` n'y figure pas. La table porte
  `apply_patch` parce que le registre le déclare et que la décision le nomme ;
  ce n'est pas une mesure que l'outil existe chez cet hôte.

LES NUMÉROS DE LIGNE DES COMMENTAIRES valent au sha `RELEVE_SHA`, comme ceux de
`data/capacites_hotes.json`. Le banc `test_cadre_hook_table.py` vérifie la CLÉ
dans le registre, jamais la ligne : un registre qui gagne une entrée ne fait
pas mentir la table, une clé renommée la fait rougir.

Pureté : ce module est une DONNÉE. Il ne lit ni n'écrit rien, ne lance rien, et
n'importe que `cadre.config` : `HOTES`, `HERITIERS` (source Python unique) et
`HoteInconnu`.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from cadre.config import HERITIERS, HOTES, HoteInconnu

__all__ = [
    "RELEVE_SHA",
    "REGISTRES",
    "Graphie",
    "TABLE",
    "EVENEMENTS",
    "EvenementInconnu",
    "HERITIERS",
    "NON_DOCUMENTEES",
    "GraphiesAntigravity",
    "GRAPHIES_ANTIGRAVITY",
    "natif",
]

#: Le sha auquel les clés et les numéros de ligne cités ont été relevés.
RELEVE_SHA = "80cc84b8"

#: Le registre natif que le kit LIVRE pour chaque hôte, chemin relatif à la
#: racine du projet. Copilot est le seul registre PLAT (`version` + `hooks`,
#: sans `matcher`) ; les quatre autres imbriquent `matcher` et `hooks`.
REGISTRES: Mapping[str, str] = MappingProxyType({
    "claude": ".claude/settings.json",
    "codex": ".codex/hooks.json",
    "gemini": ".agents/hooks.json",
    "copilot": ".github/hooks/agent-guardrails.json",
    "kimi": ".kimi-code/hooks.json",
})


class EvenementInconnu(ValueError):
    """Le nom n'est pas un événement canonique de la table."""


@dataclass(frozen=True)
class Graphie:
    """Une cellule : la clé native déclarée, ou son absence et sa raison.

    L'invariant est tenu à la construction : `natif` vaut `None` SI ET
    SEULEMENT SI `raison` est une phrase non vide. Une cellule vide sans
    raison n'est pas constructible — c'est l'omission silencieuse que la table
    refuse.
    """

    natif: str | None
    raison: str | None = None

    def __post_init__(self) -> None:
        if self.natif is None:
            if not (self.raison and self.raison.strip()):
                raise ValueError("une graphie absente porte sa raison")
        elif not self.natif.strip():
            raise ValueError("une graphie native n'est jamais vide")
        elif self.raison is not None:
            raise ValueError("une graphie déclarée ne porte pas de raison d'absence")


def _absent(hote: str) -> Graphie:
    """La cellule d'un événement que le registre de `hote` ne déclare pas."""
    return Graphie(
        None,
        raison=(
            f"aucune cle declaree sous `hooks` dans {REGISTRES[hote]} ; "
            "contract.lock.json dit cet evenement DECLARE par Claude Code SEUL. "
            "La documentation de l'hote n'est pas relevee ici : la table "
            "n'affirme ni l'existence ni l'absence d'un equivalent natif."
        ),
    )


def _figer(table: dict[str, dict[str, Graphie]]) -> Mapping[str, Mapping[str, Graphie]]:
    return MappingProxyType({ev: MappingProxyType(dict(c)) for ev, c in table.items()})


#: TABLE[evenement][hote] -> Graphie. L'ordre des événements est celui du
#: verrou ; chaque ligne cite l'élément du verrou, chaque cellule sa clé.
TABLE: Mapping[str, Mapping[str, Graphie]] = _figer({
    # contract.lock.json:166 — hook:SessionStart
    "SessionStart": {
        "claude": Graphie("SessionStart"),   # .claude/settings.json:167
        "codex": Graphie("SessionStart"),    # .codex/hooks.json:3
        "gemini": Graphie("SessionStart"),   # .agents/hooks.json:3
        "copilot": Graphie("sessionStart"),  # .github/hooks/agent-guardrails.json:4
        "kimi": Graphie("SessionStart"),     # .kimi-code/hooks.json:3
    },
    # contract.lock.json:173 — hook:PreToolUse
    "PreToolUse": {
        "claude": Graphie("PreToolUse"),     # .claude/settings.json:3
        "codex": Graphie("PreToolUse"),      # .codex/hooks.json:17
        "gemini": Graphie("PreToolUse"),     # .agents/hooks.json:17
        "copilot": Graphie("preToolUse"),    # .github/hooks/agent-guardrails.json:13
        "kimi": Graphie("PreToolUse"),       # .kimi-code/hooks.json:17
    },
    # contract.lock.json:180 — hook:PostToolUse
    "PostToolUse": {
        "claude": Graphie("PostToolUse"),    # .claude/settings.json:75
        "codex": Graphie("PostToolUse"),     # .codex/hooks.json:71
        "gemini": Graphie("PostToolUse"),    # .agents/hooks.json:71
        "copilot": Graphie("postToolUse"),   # .github/hooks/agent-guardrails.json:57
        "kimi": Graphie("PostToolUse"),      # .kimi-code/hooks.json:71
    },
    # contract.lock.json:187 — hook:Stop ; « Copilot l'epelle `agentStop` »
    "Stop": {
        "claude": Graphie("Stop"),           # .claude/settings.json:199
        "codex": Graphie("Stop"),            # .codex/hooks.json:160
        "gemini": Graphie("Stop"),           # .agents/hooks.json:137
        "copilot": Graphie("agentStop"),     # .github/hooks/agent-guardrails.json:119
        "kimi": Graphie("Stop"),             # .kimi-code/hooks.json:149
    },
    # contract.lock.json:194 — hook:SubagentStop
    "SubagentStop": {
        "claude": Graphie("SubagentStop"),   # .claude/settings.json:141
        "codex": Graphie("SubagentStop"),    # .codex/hooks.json:125
        "gemini": Graphie("SubagentStop"),   # .agents/hooks.json:113
        "copilot": Graphie("subagentStop"),  # .github/hooks/agent-guardrails.json:96
        "kimi": Graphie("SubagentStop"),     # .kimi-code/hooks.json:125
    },
    # contract.lock.json:201 — hook:PreCompact
    "PreCompact": {
        "claude": Graphie("PreCompact"),     # .claude/settings.json:188
        "codex": Graphie("PreCompact"),      # .codex/hooks.json:111
        "gemini": Graphie("PreCompact"),     # .agents/hooks.json:99
        "copilot": Graphie("preCompact"),    # .github/hooks/agent-guardrails.json:87
        "kimi": Graphie("PreCompact"),       # .kimi-code/hooks.json:111
    },
    # contract.lock.json:208 — hook:SessionEnd, « DECLARE par Claude Code SEUL »
    "SessionEnd": {
        "claude": Graphie("SessionEnd"),     # .claude/settings.json:259
        "codex": _absent("codex"),           # .codex/hooks.json : aucune cle
        "gemini": _absent("gemini"),         # .agents/hooks.json : aucune cle
        "copilot": _absent("copilot"),       # .github/hooks/agent-guardrails.json : aucune cle
        "kimi": _absent("kimi"),             # .kimi-code/hooks.json : aucune cle
    },
    # contract.lock.json:215 — hook:PostCompact, « DECLARE par Claude Code SEUL »
    "PostCompact": {
        "claude": Graphie("PostCompact"),    # .claude/settings.json:270
        "codex": _absent("codex"),           # .codex/hooks.json : aucune cle
        "gemini": _absent("gemini"),         # .agents/hooks.json : aucune cle
        "copilot": _absent("copilot"),       # .github/hooks/agent-guardrails.json : aucune cle
        "kimi": _absent("kimi"),             # .kimi-code/hooks.json : aucune cle
    },
    # contract.lock.json:222 — hook:SubagentStart, « DECLARE par Claude Code SEUL »
    "SubagentStart": {
        "claude": Graphie("SubagentStart"),  # .claude/settings.json:248
        "codex": _absent("codex"),           # .codex/hooks.json : aucune cle
        "gemini": _absent("gemini"),         # .agents/hooks.json : aucune cle
        "copilot": _absent("copilot"),       # .github/hooks/agent-guardrails.json : aucune cle
        "kimi": _absent("kimi"),             # .kimi-code/hooks.json : aucune cle
    },
    # contract.lock.json:229 — hook:Notification, « DECLARE par Claude Code SEUL »
    "Notification": {
        "claude": Graphie("Notification"),   # .claude/settings.json:281
        "codex": _absent("codex"),           # .codex/hooks.json : aucune cle
        "gemini": _absent("gemini"),         # .agents/hooks.json : aucune cle
        "copilot": _absent("copilot"),       # .github/hooks/agent-guardrails.json : aucune cle
        "kimi": _absent("kimi"),             # .kimi-code/hooks.json : aucune cle
    },
})

#: Les événements canoniques, dans l'ordre du verrou.
EVENEMENTS: tuple[str, ...] = tuple(TABLE)

# `HERITIERS` — un hôte qui n'est PAS une colonne et hérite du registre d'un
# hôte qui l'est (décision pilote S-00001606 ;
# docs/PROMPT-refonte-packaging-cadre.md:493) — est IMPORTÉ de `cadre.config`,
# sa SOURCE PYTHON UNIQUE (S-00004509), et RÉEXPORTÉ ici par `__all__` : aucune
# copie Python ; `herite_de` de `data/capacites_hotes.json` en est une seconde
# déclaration, liée par égalité
# (`test_registres_et_heritiers_egalent_capacites_hotes`) : une divergence y
# rougit.

#: Cellules DÉCLARÉES qu'aucune documentation des hôtes lecteurs ne nomme
#: (relevé R11, docs/tasks/T-00000791-releve.md:44 ; T-00000817 ouverte).
#: Une cellule porte UNE graphie, la déclarée : cet ensemble dit lesquelles
#: ne sont adossées à aucune documentation, sans en écrire une seconde.
NON_DOCUMENTEES: frozenset[tuple[str, str]] = frozenset({
    ("PreCompact", "gemini"), ("SubagentStop", "gemini")})


@dataclass(frozen=True)
class GraphiesAntigravity:
    """Les graphies d'OUTIL d'Antigravity, portées par les matchers de la ligne
    de son hôte porteur, et les événements dont le matcher les porte.

    `shell` est le nom documenté d'Antigravity ; `edition` est la graphie
    DÉCLARÉE au registre et nommée par S-00001606, non documentée chez cet
    hôte. `matcher_shell` et `matcher_edition` sont les alternances EXACTES
    écrites dans le registre, qui les combinent aux noms déjà portés par la
    ligne. Un rendu du registre écrit ces deux chaînes telles quelles.
    """

    porteur: str
    shell: str
    edition: str
    matcher_shell: str
    matcher_edition: str
    evenements_shell: tuple[str, ...]
    evenements_edition: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.porteur not in HOTES:
            raise ValueError(f"porteur hors de HOTES : {self.porteur!r}")
        if self.shell not in self.matcher_shell.split("|"):
            raise ValueError("le matcher shell ne porte pas la graphie shell")
        if self.edition not in self.matcher_edition.split("|"):
            raise ValueError("le matcher d'edition ne porte pas la graphie d'edition")
        for ev in self.evenements_shell + self.evenements_edition:
            if ev not in TABLE or TABLE[ev][self.porteur].natif is None:
                raise ValueError(f"evenement sans graphie chez le porteur : {ev!r}")


#: .agents/hooks.json:45 — PreToolUse, matcher "Bash|run_command" ;
#: .agents/hooks.json:19 — PreToolUse, matcher "Edit|Write|apply_patch" ;
#: .agents/hooks.json:73 — PostToolUse, matcher "Edit|Write|apply_patch".
GRAPHIES_ANTIGRAVITY = GraphiesAntigravity(
    porteur=HERITIERS["antigravity"],
    shell="run_command",
    edition="apply_patch",
    matcher_shell="Bash|run_command",
    matcher_edition="Edit|Write|apply_patch",
    evenements_shell=("PreToolUse",),
    evenements_edition=("PreToolUse", "PostToolUse"),
)


def natif(evenement: str, hote: str) -> str | None:
    """La graphie native déclarée de `evenement` chez `hote`, ou `None` quand
    le registre de l'hôte ne le déclare pas (la raison est dans `TABLE`).

    Un hôte hors de `HOTES` lève `HoteInconnu` — et, quand c'est un héritier
    (`HERITIERS`), le message nomme l'hôte dont il hérite et le `--host` à
    taper ; un nom hors de la table lève `EvenementInconnu`. Un argument qui
    n'est pas une chaîne est refusé par le même type, jamais par un
    `TypeError`. Le refus est un type, jamais une valeur par défaut.
    """
    if not isinstance(hote, str):
        raise HoteInconnu(f"hote inconnu : {hote!r}.")
    if not isinstance(evenement, str):
        raise EvenementInconnu(f"evenement canonique inconnu : {evenement!r}.")
    if hote not in HOTES:
        if hote in HERITIERS:
            raise HoteInconnu(
                f"{hote!r} herite de {HERITIERS[hote]!r} : utiliser --host {HERITIERS[hote]}"
            )
        raise HoteInconnu(
            f"hote inconnu : {hote!r}. Valeurs admises : {', '.join(HOTES)}."
        )
    try:
        ligne = TABLE[evenement]
    except KeyError:
        raise EvenementInconnu(
            f"evenement canonique inconnu : {evenement!r}. "
            f"Valeurs admises : {', '.join(EVENEMENTS)}."
        ) from None
    return ligne[hote].natif
