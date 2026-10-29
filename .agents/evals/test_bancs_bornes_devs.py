"""The dev defs bound their benches to the mandate's `BANCS:` line (T-01M576S8956DA9FMXY384P7EYF, lot D).

CE QU'IL JUGE. Les 15 defs dev-mono, dev-multi, frontend-fidelity (5 hotes) portent la
clause BANCS-BORNES (plan, annexe § 4a et § 4a-bis ; reserve C27) : l'ancre UNE fois, dans
la section Rules de la forme d'hote (`## Rules` en Markdown, `Rules:` en Codex), chacun de
ses atomes, la phrase « sans ligne » UNE fois, et le renvoi aux points 1 et 6 VRAI : « below »
quand la clause precede la checklist, « above » quand elle suit son point 6 (les `Rules:` de
dev-mono et dev-multi Codex suivent la checklist). Le texte de la clause est le MEME sur les
15 defs, au mot de direction pres ; la def Codex est en ASCII ; les 3 defs Kimi sont la def
Claude a l'octet, lignes `model:`/`effort:` exceptees (P15). Le texte est compare APLATI :
backticks et ** retires, tiret cadratin lu comme un tiret ASCII, blancs reduits sur une ligne
(les sauts de ligne restent : les marqueurs de checklist s'y ancrent).
CHAQUE ATOME A SON MUTANT, joue EN MEMOIRE sur les 15 defs : l'atome retire, la direction
inversee, l'ancre doublee, la phrase « sans ligne » doublee, la clause sortie de Rules, un
octet non ASCII en Codex, une ligne de Kimi changee — chacun rougit.
CHEZ L'ADOPTANT CE BANC JUGE (aucun saut) : les defs voyagent ; une def de dev reecrite par
l'adoptant est un defaut de l'adoptant (S-01M550PZ58QH3HQ4HNXGHJR7R1), comme pour
test_dev_avant_de_rendre.
CE QU'IL NE PROUVE PAS. Une clause presente n'est pas une regle obeie : un dev peut lancer un
banc hors de sa ligne. Le hook `bancs-mandat` (lot A) juge le MANDAT, jamais le dev ; la porte
joue le reste.
"""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
NOMS = ("dev-mono", "dev-multi", "frontend-fidelity")
DEFS = {
    **{f"{h}/{n}": (ROOT / h / "agents" / f"{n}.md", "md") for h in (".claude", ".gemini", ".kimi-code") for n in NOMS},
    **{f".codex/{n}": (ROOT / ".codex" / "agents" / f"{n}.toml", "codex") for n in NOMS},
    **{f".github/{n}": (ROOT / ".github" / "agents" / f"{n}.agent.md", "copilot") for n in NOMS},
}
ANCRE = "BANCS-BORNES (T-01M576S8956DA9FMXY384P7EYF)."
CHECKLIST = "play the judge's checklist yourself"
MARK = {"md": r"(?m)^{n}\. ", "codex": r"(?m)^{n}\. ", "copilot": r"\({n}\) "}
DIRECTION = re.compile(r"items 1 and 6 (below|above) play only these same benches")
SANS_LIGNE = "No BANCS: line in your mandate"
FIN = "BANCS: absente under FOLLOW-UPS - never a sweep."
ATOMES = (
    "Your mandate's BANCS: line is EXHAUSTIVE",
    "you run ONLY its benches",
    "plus the bench you create and its mutants",
    "Every other bench is run by the gate",
    "never a sweep of the neighbours",
    "never a git grep -l turned into a run list",
    "whatever the prose of the mandate says",
    "BANCS: aucun | <why> means none but yours",
    # C27 : un banc EXISTANT qu'un critere lance est dans BANCS: ; le banc que le lot cree passe par PROOFS:.
    "An EXISTING bench named by an acceptance criterion belongs in BANCS:",
    "the new bench you create goes through PROOFS:",
    "A bench you believe owed and not listed is NAMED under FOLLOW-UPS, never run",
    # § 4a-bis (C20) : sans ligne, ni balayage ni silence.
    SANS_LIGNE,
    "you run only the commands of the plan's acceptance criteria and the bench you create with its mutants",
    FIN,
)


def aplatir(texte: str) -> str:
    texte = texte.replace("`", "").replace("**", "").replace("—", "-")
    return "\n".join(re.sub(r"[ \t]+", " ", ligne).strip() for ligne in texte.splitlines())


def corps(chemin: Path, forme: str) -> str:
    if forme == "codex":
        return tomllib.loads(chemin.read_text(encoding="utf-8"))["developer_instructions"]
    return chemin.read_text(encoding="utf-8")


def segment(texte: str) -> str:
    """La clause aplatie, de l'ancre a la fin de la phrase « sans ligne », puces Codex et blancs normalises."""
    debut = texte.find(ANCRE)
    fin = texte.find(FIN, debut)
    if debut < 0 or fin < 0:
        return ""
    brut = re.sub(r"(?m)^- ", "", texte[debut:fin + len(FIN)])
    return DIRECTION.sub("items 1 and 6 <dir> play only these same benches", " ".join(brut.split()))


def section_de(texte: str, pos: int, forme: str) -> str:
    motif = r"(?m)^[A-Z][^\n]*:$" if forme == "codex" else r"(?m)^## .*$"
    titres = [m.group(0) for m in re.finditer(motif, texte[:pos])]
    return titres[-1] if titres else ""


def verifier(texte: str, forme: str) -> list[str]:
    """Constats de la clause sur un texte APLATI ; liste vide = clause tenue."""
    constats = []
    if texte.count(ANCRE) != 1:
        return [f"ancre x{texte.count(ANCRE)}"]
    pos = texte.find(ANCRE)
    seg = texte[pos:texte.find(FIN, pos) + len(FIN)] if texte.find(FIN, pos) >= 0 else texte[pos:]
    constats += [f"atome absent : {a}" for a in ATOMES if a not in seg]
    if texte.count(SANS_LIGNE) != 1:
        constats.append(f"phrase sans ligne x{texte.count(SANS_LIGNE)}")
    titre = section_de(texte, pos, forme)
    if titre not in ("## Rules", "Rules:"):
        constats.append(f"clause hors Rules : {titre!r}")
    debut = texte.find(CHECKLIST)
    sens = DIRECTION.search(seg)
    un = re.search(MARK[forme].format(n=1), texte[debut:]) if debut >= 0 else None
    six = re.search(MARK[forme].format(n=6), texte[debut:]) if debut >= 0 else None
    if sens is None or un is None or six is None:
        constats.append("renvoi aux points 1 et 6 introuvable")
    elif sens.group(1) == "below" and not pos < debut + un.start():
        constats.append("« below » faux : la clause suit le point 1")
    elif sens.group(1) == "above" and not pos > debut + six.start():
        constats.append("« above » faux : la clause precede le point 6")
    return constats


def kimi_egale_claude(kimi: str, claude: str) -> bool:
    return kimi == re.sub(r"(?m)^(?:model|effort): .*\n", "", claude, count=2)


TEXTES = {cle: aplatir(corps(chemin, forme)) for cle, (chemin, forme) in DEFS.items()}


@pytest.mark.parametrize("cle", sorted(DEFS))
def test_la_clause_est_tenue(cle):
    assert verifier(TEXTES[cle], DEFS[cle][1]) == [], cle


def test_la_clause_est_la_meme_sur_les_15_defs():
    segments = {cle: segment(texte) for cle, texte in TEXTES.items()}
    assert len(set(segments.values())) == 1, segments


def codex_en_ascii(octets: bytes) -> bool:
    return octets.isascii()


def test_la_def_codex_est_en_ascii():
    for n in NOMS:
        assert codex_en_ascii((ROOT / ".codex" / "agents" / f"{n}.toml").read_bytes()), n


@pytest.mark.parametrize("nom", NOMS)
def test_kimi_est_claude_a_l_octet(nom):
    claude = (ROOT / ".claude" / "agents" / f"{nom}.md").read_text(encoding="utf-8")
    kimi = (ROOT / ".kimi-code" / "agents" / f"{nom}.md").read_text(encoding="utf-8")
    assert kimi_egale_claude(kimi, claude), nom


@pytest.mark.parametrize("atome", ATOMES)
@pytest.mark.parametrize("cle", sorted(DEFS))
def test_mutant_atome_retire_rougit(cle, atome):
    assert verifier(TEXTES[cle].replace(atome, "", 1), DEFS[cle][1]), (cle, atome)


@pytest.mark.parametrize("cle", sorted(DEFS))
def test_mutants_de_forme_rougissent(cle):
    texte, forme = TEXTES[cle], DEFS[cle][1]
    sens = DIRECTION.search(texte).group(1)
    inverse = texte.replace(f"items 1 and 6 {sens}", f"items 1 and 6 {'above' if sens == 'below' else 'below'}")
    titre = "Other:" if forme == "codex" else "## Other"
    ligne = texte.rfind("\n", 0, texte.find(ANCRE)) + 1
    mutants = {
        "direction inversee": inverse,
        "ancre doublee": texte + "\n" + ANCRE,
        "sans ligne doublee": texte + "\n" + SANS_LIGNE,
        "hors Rules": f"{texte[:ligne]}{titre}\n{texte[ligne:]}",
    }
    for nom, mutant in mutants.items():
        assert verifier(mutant, forme), (cle, nom)


def test_mutants_ascii_et_kimi_rougissent():
    octets = (ROOT / ".codex" / "agents" / "dev-mono.toml").read_bytes()
    assert not codex_en_ascii(octets.replace(b"gate - never", "gate — never".encode("utf-8"), 1))
    claude = (ROOT / ".claude" / "agents" / "dev-multi.md").read_text(encoding="utf-8")
    kimi = (ROOT / ".kimi-code" / "agents" / "dev-multi.md").read_text(encoding="utf-8")
    assert not kimi_egale_claude(kimi.replace(SANS_LIGNE.replace("BANCS:", "`BANCS:`"), "", 1), claude)
    assert not kimi_egale_claude(kimi.replace("EXHAUSTIVE", "exhaustive", 1), claude)
