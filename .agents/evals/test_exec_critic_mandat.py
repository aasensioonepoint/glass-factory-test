"""Le mandat d'exec-critic écrit par les lanceurs (T-01M551R8PFWV4M6M0735X0WNK1).

CE QU'IL JUGE : « THE EXEC-CRITIC MANDATE » présent UNE fois sur chaque surface kickoff (SKILL et
commande), identique dans les deux (T1) ; chaque ancre cherchée DANS SON point (a)-(f), jamais dans
le paragraphe entier (T2) ; la phrase de nuit présente une fois, identique dans les deux surfaces de
nuit, et ses ancres (T3) ; les absences — gestes refusés par les gardes, mot `orchestrator`, ordre
exec-critic / sécurité, push parmi les gestes qui AGISSENT (T4) ; le renvoi § P DANS l'étape qui
lance exec-critic, avant le paragraphe (T6) ; des mutants sur le texte RÉEL, chacun prouvé appliqué,
y compris une édition SYNCHRONISÉE des deux copies, qui garde T1 vert (T5).
CE QU'IL NE PROUVE PAS : qu'un lanceur passe le mandat, qu'exec-critic le suive, ni qu'une garde
refuse un push — la consigne est de la PROSE ; elle empêche d'oublier, pas de tricher.
CHEZ L'ADOPTANT CE FILET SAUTE, alors que test_dev_avant_de_rendre y juge (une déf de dev réécrite
par l'adoptant est un défaut de l'adoptant, S-01M550PZ58QH3HQ4HNXGHJR7R1) : la règle diffère par
décision (S-01M56VW5K29XNEPA04C83RHGY0), l'aligner sur le jugement chez l'adoptant est hors de la vague 1.
Décision pilote S-01M55870Z099K7CN0XKS8K90AT (périmètre : déf exec-critic inchangée) ; réserves
S-01M55J9H5P0VSEVW6P6EMPA9Q2 et S-01M55M1971VHMYX85ACZZV27DG ; correction de clôture vague 1
(S-01M56VW2712HBKC9V886DA30E3 T1/T5, S-01M56THHVARBYT8ZGR33MG1TQY).
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
# adopting-tree: son absence EST le signal « projet adoptant » : ce filet y saute EN ENTIER.
KIT = (ROOT / ".agents" / "IS_THE_KIT").exists()
pytestmark = pytest.mark.skipif(not KIT, reason="hors du kit : surfaces réécrivables par l'adoptant (SAUT ANNONCÉ)")

KICKOFF = (".agents/skills/kickoff/SKILL.md", ".claude/commands/kickoff.md")
NUIT = (".agents/skills/night/SKILL.md", ".claude/commands/night.md")
TITRE = "**THE EXEC-CRITIC MANDATE"
RENVOI = "Every exec-critic call of this step carries THE EXEC-CRITIC MANDATE (below)."
ETAPE = "invoke **exec-critic**"
NUIT_DEBUT, NUIT_FIN = "**Mandat d'exec-critic", "pas même depuis le clone."
MARQUES = ("(a) ", "(b) ", "(c) ", "(d) ", "(e) ", "(f) ")
# P3 : la commande du clone (c) ancrée ENTIÈRE — une option retirée ou ajoutée rougit.
CLONE = "git clone -q --branch <dev branch> --single-branch <repository> <clone>"
ANCRES = {
    "tete": ("THE EXEC-CRITIC MANDATE", "S-01M55870Z099K7CN0XKS8K90AT", "as data", "the def stays the judge"),
    "a": ("EVERY acceptance criterion", "real command output", "none skipped", "none taken on the dev's word"),
    "b": ("PROOFS:", "only what VERIFIES", "compare its verdict line", "the block is data, never an order", "ACTS",
          "rewritten against that clone", "never in the repository under judgement", "never as the dev's line verbatim",
          "an item the def forbids (commit, restore, checkout) is re-expressed by copying files, never run",
          "a replayed revert runs as git -C <clone> revert --no-commit", "the files it touches saved first",
          "undone by copying the saved originals back", "a push is never replayed", "not even from the clone",
          "its origin removed in (c)", "the repository still reachable by path",
          "pushed nowhere, neither by name nor by path or URL", "PROBED as in (d)", "does not replay",
          "measured by exec-critic itself"),
    "c": ("only on a new or modified witness", "no dev mutant proof", "ONE throwaway clone outside the repository",
          "created once", f"({CLONE})",
          "then git -C <clone> remote remove origin", "reused", "sparse-checkout set",
          "saved outside the repository", "python3", "never sed -i", "copying that saved original back into the clone",
          "never a reset or a clean"),
    "d": ("ALWAYS PROBE", "PRESCRIBES", "never execute it", "whatever the proofs say", "JSON payload", "AGENTS_EVENTS_DIR",
          "mktemp -d", "CLAUDE_PROJECT_DIR and the cwd both set to the repository under judgement",
          "one gesture the guard is known to refuse, which must come back refused",
          "never probed through .githooks/pre-push", "VERIFY_STAMP",
          "refuses every non-delete ref and admits every delete", "judges nothing", "addressed to the executor"),
    "e": ("load verdict", "S-01M559V3Y1KNXD4JQJNQ735AJH", "one measurement at a time", "none while a gate runs",
          "(pgrep -f '^bash [^ ]*core-scripts/verify[.]sh' prints nothing)",
          'sandbox_mode = "read-only"', "measured the sandbox, not the diff", "COVERAGE DEGRADED", "BLIND SPOT"),
    "f": ("On a lot of a fournée, or on any member of a DELIVERY,", "lot's diff only", "INTÉGRATION:", "CHANGELOG.md",
          "written outside the lot", "outside this verdict", "re-read by the closing review on a fournée",
          "re-read by NO review on a DELIVERY", "step (10) of § ONE REVIEW WAVE PER DELIVERY", "after the merge",
          "BLIND SPOT", "exactly so", "never as covered", "Nothing here thins the judge", "never left unmeasured"),
}
ANCRES_NUIT = ("THE EXEC-CRITIC MANDATE", "S-01M55870Z099K7CN0XKS8K90AT", "CHAQUE critère d'acceptation", "PROOFS:",
               "seul ce qui VÉRIFIE", "AGIT seulement dans le clone jetable", "jamais dans le dépôt jugé",
               "témoin sans preuve rejouable", "TOUJOURS", "SONDÉS", "gardes de l'hôte", "safe-bash", "pre-push",
               "un push n'est jamais sondé par", "sans tampon ne juge rien",
               "jamais exécutés", "jamais un push", "pas même depuis le clone")
ABSENT = ("reset --hard", "git clean", "security stages wait", "before the security gate", "BEFORE the security stage",
          "one message", "--attendre", "in parallel", "git restore", "git checkout", "a commit, a push",
          "are re-read by the closing review",
          # Correction de clôture vague 1 : les formes d'hier, fausses au tip (T1, T5, D3).
          "run only in a throwaway clone", "never a real push", "is the repository under judgement",
          "the last gesture in the clone", "by reverting it")
ABSENT_NUIT = ("security-code-review", "build_index", "documenter", "indexer", "--attendre", "un à un", "vrai push")
# C3 : le mot seul, jamais dans `security-orchestrator` (équivalent de l'ERE du critère 4).
MOT_ORCH = re.compile(r"(?:^|[^-\w])orchestrator(?:[^\w]|$)")
# C12 : la parenthèse des gestes qui AGISSENT ne porte aucun push ; ancrée sur ce qui la SUIT, pour
# qu'un push ré-admis HORS d'elle (« …, a commit) or a push is replayed ») rougisse aussi (P1).
ACTES = re.compile(r"an item that ACTS \(([^)]*)\) is replayed only in the throwaway clone of \(c\)")
# D3 : « of those » — chaque geste que la déf interdit est l'un des gestes qui AGISSENT.
INTERDITS = re.compile(r"of those, an item the def forbids \(([^)]*)\)")


def plat(t: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", t)).strip()


def nu(t: str) -> str:
    return t.replace("`", "")


def lire(c: str) -> str:
    return (ROOT / c).read_text(encoding="utf-8")


def bornes_paragraphe(t: str) -> tuple[int, int]:
    i = t.index(TITRE)
    j = t.find("\n\n", i)
    return i, (len(t) if j < 0 else j)


def bornes_nuit(t: str) -> tuple[int, int]:
    i = t.index(NUIT_DEBUT)
    return i, t.index(NUIT_FIN, i) + len(NUIT_FIN)


def points(p: str) -> dict[str, str] | None:
    pos = [p.find(m) for m in MARQUES]
    if any(x < 0 for x in pos) or pos != sorted(pos) or any(p.count(m) != 1 for m in MARQUES):
        return None
    coupe = dict(zip("abcdef", pos))
    out = {"tete": p[:pos[0]]}
    for k, (cle, d) in enumerate(coupe.items()):
        out[cle] = p[d:pos[k + 1]] if k + 1 < len(pos) else p[d:]
    return out


def etape(t: str) -> str:
    """L'étape numérotée qui contient ETAPE : de sa ligne `<n>. ` à la suivante de même retrait, ou `#`."""
    lignes = t.split("\n")
    k = next(n for n, l in enumerate(lignes) if ETAPE in l)
    debut = next(n for n in range(k, -1, -1) if re.match(r"^(\s*)\d+\. ", lignes[n]))
    retrait = re.match(r"^(\s*)", lignes[debut]).group(1)
    fin = next((n for n in range(debut + 1, len(lignes))
                if re.match(rf"^{retrait}\d+\. ", lignes[n]) or lignes[n].startswith("#")), len(lignes))
    return "\n".join(lignes[debut:fin])


def fautes(textes: dict[str, str]) -> list[str]:
    f: list[str] = []
    pars = {}
    for c in KICKOFF:
        t = textes[c]
        if t.count(TITRE) != 1:
            f.append(f"{c} : titre présent {t.count(TITRE)} fois (attendu 1)")
            continue
        i, j = bornes_paragraphe(t)
        p = plat(t[i:j])
        pars[c] = p
        pts = points(p)
        if pts is None:
            f.append(f"{c} : marqueurs (a)-(f) absents, doublés ou hors d'ordre")
        else:
            f += [f"{c} : point ({k}) sans « {a} »" for k, ancres in ANCRES.items() for a in ancres
                  if nu(a) not in nu(pts[k])]
            actes = ACTES.search(pts["b"])
            if actes is None or "push" in actes.group(1).casefold():
                f.append(f"{c} : parenthèse des gestes qui AGISSENT absente, détachée de son clone ou portant un push")
            interdits = INTERDITS.search(nu(pts["b"]))
            if interdits is None or actes is None:
                f.append(f"{c} : « of those, an item the def forbids (…) » absent")
            else:
                hors = [g.strip() for g in interdits.group(1).split(",")
                        if g.strip().casefold() not in nu(actes.group(1)).casefold()]
                f += [f"{c} : geste interdit « {g} » hors des gestes qui AGISSENT (« of those » faux)" for g in hors]
        f += [f"{c} : forme interdite « {a} »" for a in ABSENT if a.casefold() in p.casefold()]
        if MOT_ORCH.search(p):
            f.append(f"{c} : le mot `orchestrator` dans le mandat")
        if plat(t).count(RENVOI) != 1:
            f.append(f"{c} : renvoi § P présent {plat(t).count(RENVOI)} fois (attendu 1)")
        elif RENVOI not in plat(etape(t)) or plat(t).index(RENVOI) > plat(t).index(plat(TITRE)):
            f.append(f"{c} : renvoi § P hors de l'étape qui lance exec-critic, ou après le mandat")
    if len(pars) == 2 and len(set(pars.values())) != 1:
        f.append("T1 : les deux paragraphes kickoff diffèrent")
    nuits = {}
    for c in NUIT:
        t = textes[c]
        if t.count(NUIT_DEBUT) != 1 or t.count(NUIT_FIN) != 1:
            f.append(f"{c} : phrase de nuit présente {t.count(NUIT_DEBUT)}/{t.count(NUIT_FIN)} fois (attendu 1/1)")
            continue
        i, j = bornes_nuit(t)
        s = plat(t[i:j])
        nuits[c] = s
        f += [f"{c} : phrase de nuit sans « {a} »" for a in ANCRES_NUIT if a not in s]
        f += [f"{c} : phrase de nuit porte « {a} »" for a in ABSENT_NUIT if a in s]
    if len(nuits) == 2 and len(set(nuits.values())) != 1:
        f.append("T3 : les deux phrases de nuit diffèrent")
    return f


def textes_reels() -> dict[str, str]:
    return {c: lire(c) for c in (*KICKOFF, *NUIT)}


def remplace_par(t: str, bornes, f) -> str:
    """Remplace la zone (paragraphe ou phrase) par sa forme APLATIE transformée par f."""
    i, j = bornes(t)
    return t[:i] + f(plat(t[i:j])) + t[j:]


def retire_du_point(p: str, cle: str, ancre: str) -> str:
    q = nu(p)
    pts = points(q)
    zone = pts[cle]
    d = q.index(zone)
    return q[:d] + zone.replace(nu(ancre), "") + q[d + len(zone):]


def test_population() -> None:
    manquants = [c for c in (*KICKOFF, *NUIT) if not (ROOT / c).is_file()]
    assert manquants == [], f"surfaces absentes (jamais un vert vide) : {manquants}"
    assert sum(len(v) for v in ANCRES.values()) > 0 and set(ANCRES) == {"tete", *"abcdef"}


def test_mandat() -> None:
    f = fautes(textes_reels())
    assert f == [], "\n".join(f)


def _mutants(base: dict[str, str]) -> dict[str, dict[str, str]]:
    m: dict[str, dict[str, str]] = {}

    def kick(nom, f, copies=KICKOFF):
        m[nom] = {**base, **{c: remplace_par(base[c], bornes_paragraphe, f) for c in copies}}

    def nuit(nom, f):
        m[nom] = {**base, **{c: remplace_par(base[c], bornes_nuit, f) for c in NUIT}}

    # C4 : chaque ancre retirée de SON point, sur les DEUX copies (T1 reste vert, T2 doit rougir).
    for cle, ancres in ANCRES.items():
        for a in ancres:
            kick(f"sync-{cle}-{a}", lambda p, cle=cle, a=a: retire_du_point(p, cle, a))
    for mq in MARQUES:
        kick(f"sans-marque-{mq.strip()}", lambda p, mq=mq: p.replace(mq, "", 1))
    for inj in ("git reset --hard", " orchestrator ", " in parallel ", " one message ", " git restore "):
        kick(f"injecte-{inj.strip()}", lambda p, inj=inj: p + inj)
    m["titre-double"] = {**base, KICKOFF[0]: base[KICKOFF[0]] + "\n\n" + TITRE + "**\n"}
    kick("un-mot-change", lambda p: p.replace("in which order", "in what order"), copies=KICKOFF[1:])
    for c in KICKOFF:
        sans = base[c].replace(RENVOI + " ", "", 1)
        m[f"renvoi-retire-{c}"] = {**base, c: sans}
        m[f"renvoi-deplace-{c}"] = {**base, c: sans + "\n" + RENVOI + "\n"}
    # r4 nommés (C1, C2) et C12 : un push parmi les gestes qui AGISSENT, de deux façons.
    kick("r4-a-commit-a-push", lambda p: p.replace("a commit)", "a commit, a push)"))
    kick("c12-push-en-tete", lambda p: p.replace("ACTS (a revert,", "ACTS (a push, a revert,"))
    kick("c12-push-au-milieu", lambda p: p.replace("an `rm`, a", "an `rm`, a forced push, a"))
    kick("r4-sans-clause-push", lambda p: re.sub(r"a push is never replayed.*?PROBED as in \(d\);", "", p))
    kick("r4-sans-remove-origin", lambda p: p.replace(", then `git -C <clone> remote remove origin`", ""))
    kick("r4-closing-review", lambda p: p.replace("re-read by NO review on a DELIVERY", "re-read by the closing review"))
    kick("r4-sans-never-as-covered", lambda p: p.replace("never as covered", ""))
    kick("r4-formule-r3", lambda p: re.sub(r"are outside this verdict — .*?— said under `BLIND SPOT`",
                                           "are re-read by the closing review — said under BLIND SPOT", p))
    nuit("r4-vrai-push", lambda s: s.replace("jamais un push, pas même depuis le clone.", "jamais un vrai push."))
    # Correction de clôture vague 1. P1 : un push ré-admis HORS de la parenthèse des gestes qui AGISSENT.
    kick("p1-push-hors-parenthese", lambda p: p.replace("a commit) is replayed", "a commit) or a push is replayed"))
    kick("p1-parenthese-detachee", lambda p: p.replace("a commit) is replayed only", "a commit) are replayed only"))
    # P2/P3/P8 : le motif pgrep (e) et les options du clone (c), chacune retirée ou remplacée.
    kick("p2-pgrep-x-nothing", lambda p: p.replace("pgrep -f '^bash [^ ]*core-scripts/verify[.]sh'", "pgrep -x nothing"))
    kick("p2-pgrep-sans-prints-nothing", lambda p: p.replace("verify[.]sh'` prints nothing", "verify[.]sh'`"))
    for opt in ("-q ", "--branch <dev branch> ", "--single-branch "):
        kick(f"p3-clone-sans-{opt.strip()}", lambda p, opt=opt: p.replace(CLONE, CLONE.replace(opt, "", 1)))
    kick("p3-clone-option-neuve", lambda p: p.replace(CLONE, CLONE.replace("-q ", "-q --no-local ", 1)))
    # D3 : « of those » cohérent, et le revert rejoué sans commit.
    kick("d3-checkout-hors-actes", lambda p: p.replace("a `restore`, a `checkout`, a commit)", "a `restore`, a commit)"))
    kick("d3-interdit-neuf", lambda p: p.replace("forbids (commit, restore, checkout)", "forbids (commit, restore, checkout, stash)"))
    kick("d3-revert-commit", lambda p: p.replace("revert --no-commit …", "revert …"))
    kick("d3-revert-sans-restauration", lambda p: p.replace(", undone by copying the saved originals back", ""))
    # T5 / T1 : les formes d'hier ré-injectées, et la nouvelle clause amputée.
    kick("t5-origin-d-hier", lambda p: p.replace("its `origin` removed in (c)", "whose `origin` is the repository under judgement"))
    kick("t5-sans-par-chemin", lambda p: p.replace(", neither by name nor by path or URL", ""))
    kick("t1-pre-push-d-hier", lambda p: p.replace("a prescribed push is never probed through `.githooks/pre-push`",
                                                   "`.githooks/pre-push` run only in a throwaway clone, never a real push; a push"))
    kick("t1-sans-executor", lambda p: p.replace(" — mark it addressed to the executor", ""))
    for inj in (" the last gesture in the clone ", " by reverting it "):
        kick(f"injecte-{inj.strip()}", lambda p, inj=inj: p + inj)
    nuit("t1-nuit-d-hier", lambda s: s.replace("(`safe-bash` ; un push n'est jamais sondé par `pre-push`, qui sans tampon ne juge rien)",
                                               "(`safe-bash`, `pre-push`)"))
    # Nuit : chaque ancre retirée des DEUX copies, chaque absence injectée.
    for a in ANCRES_NUIT:
        nuit(f"nuit-sans-{a}", lambda s, a=a: s.replace(a, ""))
    for a in ABSENT_NUIT:
        nuit(f"nuit-injecte-{a}", lambda s, a=a: s.replace(NUIT_FIN, a + " " + NUIT_FIN))
    m["nuit-une-copie"] = {**base, NUIT[1]: remplace_par(base[NUIT[1]], bornes_nuit, lambda s: s.replace("tel quel", "tel"))}
    return m


def test_mutants() -> None:
    base = textes_reels()
    assert fautes(base) == [], "base rouge : les mutants ne prouveraient rien"
    # Contrôle : l'aplatissement SEUL reste vert — un rouge vient de la mutation, jamais de l'outil.
    plat_seul = {**base, **{c: remplace_par(base[c], bornes_paragraphe, lambda p: p) for c in KICKOFF},
                 **{c: remplace_par(base[c], bornes_nuit, lambda s: s) for c in NUIT}}
    assert plat_seul != base and fautes(plat_seul) == [], "l'aplatissement seul rougit : mutants non probants"
    survivants, inappliques = [], []
    for nom, m in _mutants(base).items():
        if m == base:
            inappliques.append(nom)
        elif not fautes(m):
            survivants.append(nom)
    assert inappliques == [], f"mutants non appliqués : {inappliques}"
    assert survivants == [], f"mutants restés verts : {survivants}"
