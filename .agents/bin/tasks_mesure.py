# tasks_mesure.py — PARTIE de `tasks.py` (T-00001128) : LA GARDE DE MESURE de
# `new` — « un défaut se mesure avant de devenir une tâche » (AGENTS.md § Golden
# rules) : la forme des valeurs, le motif FERMÉ et le refus LEXICAL.
# Exécutée dans l'espace de noms de `tasks` par `_charger_parties()`,
# jamais importée seule : ses noms libres viennent de la façade et des parties amont.

from __future__ import annotations

# LES MOTIFS, LISTE FERMÉE (ordre du pilote, S-00003957) : pourquoi CE défaut ne
# se corrige pas sur place. « mineur » n'y est pas, et c'est le point : un défaut
# mineur n'ouvre pas de tâche, il se corrige là où on l'a trouvé.
MOTIFS = ("garde", "securite", "decision-pilote", "gros", "sans-fournee")
MOTIFS_SENS = {
    "garde": "it touches a guard or a hook",
    "securite": "class 0 or 1",
    "decision-pilote": "it needs a pilot decision",
    "gros": "the fix touches 6 files or more, or needs a plan",
    "sans-fournee": "found outside any dev in flight, so no correction pass to send it to",
}
MINEUR_SUR_PLACE = (
    "un défaut mineur se corrige sur place avec un témoin s'il est dans le write-set "
    "du dev, sinon il va à la passe de correction de la fournée"
)
# LE LEXIQUE D'UN DÉFAUT, en OUVERTURE de titre seulement — après un préfixe
# `[BK-nnn][P1]` ou `scope:`, accents repliés, casse repliée. MESURÉ le 2026-10-03
# sur les 1120 titres du board : « n'importe où dans le titre » classait 265
# titres (`défaut` attrape « par défaut », `rougit` « faire rougir sa porte »,
# `casse` la CASSE des lettres) ; en ouverture, 21, tous des défauts à la
# lecture. Retirés du lexique de départ : `rougit`, `plante`, `échoue`,
# `cassé`/`casse`, `lève <Exception>` — aucun titre n'OUVRE par eux, et en
# milieu de titre ils étaient la source principale des faux positifs.
LEXIQUE_DEFAUT = (
    "fix", "bug", "bogue", "defaut", "regression", "crash", "traceback",
    "faux positif", "faux negatif",
)
_TITRE_DEFAUT = re.compile(
    r"^(?:\s*\[[^\]]*\])*\s*(?:[a-z0-9_./-]+\s*:\s*)?"
    r"(?:" + "|".join(re.escape(m) for m in LEXIQUE_DEFAUT) + r")s?\b"
)
# Cc (contrôle : saut de ligne, tabulation, ESC) et Cf (format : U+200B, BOM…) —
# un côté de `=>` fait de ces seuls caractères « a du texte » pour `.strip()`
# et n'en a pour personne ; un saut de ligne dans la valeur fabrique une
# fausse ligne `state : done` dans `list --task` (rejoué par critic-opus,
# S-00003956), et Zl/Zp (U+2028/2029) aussi (S-00003960). Refusés NOMMÉMENT.
_INVISIBLES = ("Cc", "Cf", "Zl", "Zp")


def _caractere_invisible(valeur: str) -> str | None:
    """Le premier caractère d'une catégorie de ``_INVISIBLES`` dans ``valeur``, ou ``None``."""
    for c in valeur:
        if unicodedata.category(c) in _INVISIBLES:
            return c
    return None


def _texte_visible(valeur: str) -> bool:
    """Au moins un caractère qui n'est ni un blanc ni un invisible : ce qu'un lecteur
    VOIT. ``.strip()`` seul laissait passer U+200B et U+00A0 comme du texte."""
    return any(not c.isspace() and unicodedata.category(c) not in _INVISIBLES for c in valeur)


def _normaliser_titre(titre: str) -> str:
    sans_accents = "".join(
        c for c in unicodedata.normalize("NFKD", titre) if not unicodedata.combining(c)
    )
    return sans_accents.casefold()


def titre_defaut(titre: str) -> str | None:
    """Le jeton de ``LEXIQUE_DEFAUT`` sur lequel le titre OUVRE, ou ``None``."""
    m = _TITRE_DEFAUT.match(_normaliser_titre(titre))
    return m.group(0).strip() if m else None


def mesure_refusal(
    root: str,
    mesure: str | None,
    pas_un_defaut: str | None,
    motif: str | None = None,
    titre: str = "",
) -> str | None:
    """THE MEASURE GUARD of ``new`` (T-00001128) — ``None`` means "create".

    Doctrine (AGENTS.md § Golden rules): a defect is MEASURED before it becomes
    a task. Two exits, never both: ``--mesure "<command that reproduces> =>
    <observed result>" --motif <M>`` for a defect, or ``--pas-un-defaut
    "<why>"`` for a feature, a decision or a chantier — nothing to reproduce.

    TWO RULES MADE MECHANICAL (S-00003957). ``--mesure`` REQUIRES ``--motif``,
    taken from the CLOSED list ``MOTIFS``: it says why this defect is not fixed
    on the spot. « mineur », and any motif off the list, is refused with the
    doctrine sentence — a minor defect never opens a task. ``--motif`` without
    ``--mesure``, or with ``--pas-un-defaut``, is refused: it qualifies a
    MEASURED defect and nothing else. And ``--pas-un-defaut`` is refused when
    the TITLE opens on the lexicon of a defect (``titre_defaut``): the remedy
    named is ``--mesure … --motif …``.

    WHAT THE MARKER ARMS, AND WHAT IT DOES NOT. ``MESURE_GATE`` (same shape as
    ``BINOME_GATE``) arms the OBLIGATION only: without it, a ``new`` carrying
    no flag goes through exactly as before — every existing caller, script and
    test stays valid, which is the regime of reference of a repository that
    never posed the marker. The FORM of a value given explicitly is held
    everywhere, marker or not: a ``--mesure`` without ``=>`` or with a side
    that carries no VISIBLE text, an empty ``--pas-un-defaut``, a control or
    invisible character (Cc/Cf/Zl/Zp) in any of the three values, a missing or
    off-list motif, the two exits together — all refused on an unarmed board
    too. Evaluated by ``new_task`` INSIDE the lock and BEFORE the id is minted
    (``record_id_module().mint``), like the epic refusal, so a refusal creates
    no task and allocates no id.

    It prevents FORGETTING, not CHEATING: the measure and the motif are typed
    by whoever opens the task, never replayed here — a false motif passes."""
    if mesure is not None and pas_un_defaut is not None:
        return (
            "new: --mesure and --pas-un-defaut are exclusive — a task is a MEASURED "
            "defect or something that is not a defect, never both"
        )
    if motif is not None and mesure is None:
        return (
            "new --motif: it accompanies --mesure only — a motif says why a MEASURED "
            "defect is not fixed on the spot; alone, or with --pas-un-defaut, there is "
            "nothing it qualifies"
        )
    for drapeau, valeur in (("--mesure", mesure), ("--pas-un-defaut", pas_un_defaut), ("--motif", motif)):
        if valeur is None:
            continue
        c = _caractere_invisible(valeur)
        if c is not None:
            return (
                f"new {drapeau}: refused — a control or invisible character "
                f"({c!r}, unicode {unicodedata.category(c)}) in {valeur!r}; it would forge "
                "a line in `list --task` or pass an empty side as text"
            )
    if mesure is not None:
        gauche, sep, droite = mesure.partition(MESURE_SEPARATEUR)
        if not sep or not _texte_visible(gauche) or not _texte_visible(droite):
            return (
                f'new --mesure: expected "<command that reproduces> {MESURE_SEPARATEUR} '
                f"<observed result>\", with VISIBLE text on BOTH sides of {MESURE_SEPARATEUR}; got {mesure!r}"
            )
        liste = "; ".join(f"{m}: {MOTIFS_SENS[m]}" for m in MOTIFS)
        if motif is None:
            return (
                "new --mesure: --motif <M> is REQUIRED — why is this defect not fixed on the "
                f"spot? M is one of {', '.join(MOTIFS)} ({liste}). {MINEUR_SUR_PLACE}"
            )
        if motif not in MOTIFS:
            return (
                f"new --motif {motif!r}: refused — not in the closed list ({liste}); « mineur » "
                f"is not a motif: {MINEUR_SUR_PLACE}"
            )
        return None
    if pas_un_defaut is not None:
        if not _texte_visible(pas_un_defaut):
            return (
                'new --pas-un-defaut: the reason is empty — say why this is not a defect '
                "(a feature, a decision, a chantier)"
            )
        jeton = titre_defaut(titre)
        if jeton is not None:
            return (
                f"new --pas-un-defaut: refused — the title opens on the lexicon of a DEFECT "
                f'({jeton!r}); a defect is MEASURED: --mesure "<command that reproduces> '
                f'{MESURE_SEPARATEUR} <observed result>" --motif <M> (M in {", ".join(MOTIFS)})'
            )
        return None
    if not (Path(normalize_root(root)) / MESURE_GATE).exists():
        return None
    return (
        "new: refused — a defect is MEASURED before it becomes a task (AGENTS.md § Golden "
        f"rules; armed by {MESURE_GATE.as_posix()}). Two exits: "
        f'--mesure "<command that reproduces> {MESURE_SEPARATEUR} <observed result>" --motif <M> '
        f"(M in {', '.join(MOTIFS)}) for a defect, "
        'or --pas-un-defaut "<why>" for a feature, a decision or a chantier'
    )
