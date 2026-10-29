"""Temoin du lot J de T-01M576S8956DA9FMXY384P7EYF : la clause BANCS-BORNES des juges.

CE QU'IL JUGE. Les 20 defs exec-critic, critic-opus, critic-fable et
critic-sonnet-max sur les cinq hotes (.claude, .codex, .github, .gemini,
.kimi-code) portent la clause des juges (annexe du plan, § 4b et § 4b-bis,
reserves C20, C25 et C27) :
  (a) l'ancre `BANCS-BORNES (T-01M576S8956DA9FMXY384P7EYF).` UNE fois par def ;
  (b) la clause tient sur la ligne de l'ancre, en paragraphe propre (ligne vide
      avant ; ligne vide, puce `- ` ou fin de bloc apres) ;
  (c) ses atomes, DANS cette ligne : liste EXHAUSTIVE, temoins du `PROOFS:`,
      mutant propre, la porte joue le reste, criteres d'acceptation toujours
      rejoues (C25), banc EXISTANT d'un critere dans `BANCS:` et banc cree par
      `PROOFS:` (C27), commandes non-bancs telles qu'ecrites, phrase SANS ligne
      avec `BANCS: absente` (C20), jamais un balayage, un banc du et absent est
      une trouvaille ;
  (d) exec-critic x5 : l'ancienne queue « Replay the plan's criteria, not the
      whole suite, unless the plan names it » est ABSENTE, sa remplacante
      (« Replay only the bounded benches and non-bench criteria as stated
      above ») presente, et APRES la clause (« above » doit dire vrai).
Le texte est compare APLATI : accents replies (la def Codex est en ASCII),
backticks et ** retires, apostrophes lues comme un blanc, tirets cadratins
lus comme `-`, blancs reduits — la forme de test_dev_avant_de_rendre.py.
Mutants EN MEMOIRE, jamais sur disque : chaque atome de chaque def, retire,
fait rougir (c) ; chaque mutation doit CHANGER le texte, sinon c'est un
controle vide, donc un echec. Plus les mutants nommes au plan (§ 5) : copie de
.github/agents/exec-critic.agent.md sans « acceptance criteria stay
replayed », copie de .codex/agents/critic-fable.toml sans la clause.
CHEZ L'ADOPTANT CE BANC JUGE (aucun saut) : les defs juges voyagent
(.template-exclude ne retire aucun des cinq repertoires de defs).
CE QU'IL NE PROUVE PAS. Une clause presente n'est pas une regle obeie ; les
rosters data/roster/ du paquet cadre (ou qu'il vive) sont tenus egaux aux defs par
test_cadre_roster.py (T2), pas ici.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
JUGES = ("exec-critic", "critic-opus", "critic-fable", "critic-sonnet-max")
HOTES = {
    ".claude": "agents/{n}.md",
    ".codex": "agents/{n}.toml",
    ".github": "agents/{n}.agent.md",
    ".gemini": "agents/{n}.md",
    ".kimi-code": "agents/{n}.md",
}
DEFS = {f"{h}/{n}": ROOT / h / patron.format(n=n) for h, patron in HOTES.items() for n in JUGES}

ANCRE = "BANCS-BORNES (T-01M576S8956DA9FMXY384P7EYF)."
ATOMES_EN = (
    "BANCS: line is EXHAUSTIVE",
    "replay ONLY its benches",
    "your mandate s PROOFS: witnesses and a witness for your own mutant",
    "the gate runs every other bench",
    "acceptance criteria stay replayed",
    "an EXISTING bench named by a criterion must be in BANCS:",
    "the bench created by the lot comes through PROOFS:",
    "non-bench criterion commands are replayed as written",
    "Without a BANCS: line, replay only those criteria and PROOFS: witnesses",
    "write BANCS: absente under BLIND SPOT",
    "never sweep neighbours",
    "absent from the list is a finding, never a run",
)
# T-01M5S9338BJP1B5RM3TG14AMYT (defs en anglais) : les critiques de cloture portent la clause en
# anglais, avec LEUR atome C20 (« in your findings ») — jamais celui d'exec-critic (« under BLIND
# SPOT », son propre bloc de sortie). L'ancienne clause francaise est gardee comme MUTANT (rouge).
ATOMES_CRITIQUES = tuple(
    "write BANCS: absente in your findings" if a == "write BANCS: absente under BLIND SPOT" else a
    for a in ATOMES_EN
)
CLAUSE_FR_D_AVANT = (
    "**BANCS-BORNES (T-01M576S8956DA9FMXY384P7EYF).** La ligne `BANCS:` de ton mandat est EXHAUSTIVE : "
    "tu ne rejoues QUE ses bancs, les témoins du `PROOFS:` de ton mandat et le témoin d'un mutant à toi ; "
    "la porte joue tout autre banc. Les critères d'acceptation du plan restent rejoués : un banc EXISTANT "
    "nommé par un critère doit figurer dans `BANCS:` ; le banc créé par le lot passe par `PROOFS:` ; les "
    "commandes de critères qui ne sont pas des bancs se rejouent telles qu'écrites. Sans ligne `BANCS:`, "
    "tu ne rejoues que ces critères et les témoins du `PROOFS:`, tu écris `BANCS: absente` dans tes "
    "trouvailles et tu ne balaies jamais les voisins. Un banc dû mais absent de la liste est une "
    "trouvaille, jamais un lancement."
)
VIEILLE_QUEUE = re.compile(r"replay the plan s criteria, not the whole suite", re.I)
NOUVELLE_QUEUE = re.compile(r"replay only the bounded benches and non-bench criteria as stated above", re.I)
# Controle positif de (d) : l'ancienne phrase, LITTERALE (exec-critic.md avant le lot J).
VIEILLE_PHRASE = "Replay the plan's criteria, not the whole suite, unless the plan names it."


def aplatir(texte: str) -> str:
    """Forme comparable sur les cinq hotes ; idempotente (aplatir(aplatir(x)) == aplatir(x))."""
    nfkd = unicodedata.normalize("NFKD", texte)
    sans_accent = "".join(c for c in nfkd if not unicodedata.combining(c))
    t = sans_accent.replace("**", "").replace("`", "")
    t = t.replace("—", "-").replace("–", "-").replace("'", " ").replace("’", " ")
    return re.sub(r"\s+", " ", t).strip()


def atomes_de(nom: str) -> tuple[str, ...]:
    return ATOMES_EN if nom == "exec-critic" else ATOMES_CRITIQUES


def constats(texte: str, nom: str) -> list[str]:
    """Liste des manquements ; vide = la def tient le contrat de la clause."""
    plat = aplatir(texte)
    n_ancre = plat.count(ANCRE)
    if n_ancre != 1:
        return [f"ancre x{n_ancre}, attendu x1"]
    manques: list[str] = []
    lignes = texte.replace("\r\n", "\n").split("\n")
    idx = [i for i, ligne in enumerate(lignes) if ANCRE in aplatir(ligne)]
    if len(idx) != 1:
        return [f"ancre sur {len(idx)} lignes physiques, attendu 1"]
    i = idx[0]
    avant = lignes[i - 1].strip() if i > 0 else ""
    apres = lignes[i + 1].strip() if i + 1 < len(lignes) else ""
    if avant != "":
        manques.append("paragraphe : ligne non vide avant la clause")
    if not (apres == "" or apres.startswith("- ") or apres == '"""'):
        manques.append("paragraphe : la clause se fond dans la ligne suivante")
    clause = aplatir(lignes[i])
    manques += [f"atome absent : {a}" for a in atomes_de(nom) if a not in clause]
    if nom == "exec-critic":
        if VIEILLE_QUEUE.search(plat):
            manques.append("ancienne queue presente")
        nouvelle = NOUVELLE_QUEUE.search(plat)
        if not nouvelle:
            manques.append("nouvelle queue absente")
        elif nouvelle.start() < plat.index(ANCRE):
            manques.append("nouvelle queue avant la clause (« above » faux)")
    return manques


def _lire(cle: str) -> str:
    chemin = DEFS[cle]
    assert chemin.is_file(), f"{chemin.relative_to(ROOT)} absente : une def juge manque sur son hote"
    return chemin.read_text(encoding="utf-8")


def _nom(cle: str) -> str:
    return cle.split("/", 1)[1]


def test_population_vingt_defs():
    assert len(DEFS) == 20
    manquantes = [c for c, p in DEFS.items() if not p.is_file()]
    assert not manquantes, f"defs juges absentes : {manquantes}"


@pytest.mark.parametrize("cle", sorted(DEFS))
def test_la_def_porte_la_clause(cle):
    assert constats(_lire(cle), _nom(cle)) == [], cle


def test_aplatir_est_idempotent_et_replie_la_forme_codex():
    brut = "**BANCS-BORNES (T-01M576S8956DA9FMXY384P7EYF).** Les critères d'acceptation — `BANCS:`"
    assert aplatir(aplatir(brut)) == aplatir(brut)
    assert aplatir(brut) == "BANCS-BORNES (T-01M576S8956DA9FMXY384P7EYF). Les criteres d acceptation - BANCS:"


def test_controle_positif_la_vieille_queue_est_reconnue():
    assert VIEILLE_QUEUE.search(aplatir(VIEILLE_PHRASE))
    assert VIEILLE_QUEUE.search(aplatir(VIEILLE_PHRASE.lower()))


MUTANTS_ATOMES = [(cle, a) for cle in sorted(DEFS) for a in atomes_de(_nom(cle))]


@pytest.mark.parametrize(("cle", "atome"), MUTANTS_ATOMES)
def test_mutant_chaque_atome_retire_rougit(cle, atome):
    plat = aplatir(_lire(cle))
    mute = plat.replace(atome, "<MUTE>", 1)
    assert mute != plat, f"mutation sans effet : {atome!r} introuvable dans {cle}"
    assert f"atome absent : {atome}" in constats(mute, _nom(cle))


def _ligne_clause(texte: str) -> str:
    return next(ligne for ligne in texte.split("\n") if ANCRE in aplatir(ligne))


def _sans_atome_copilot(t: str) -> str:
    return t.replace("acceptance criteria stay replayed", "acceptance criteria are optional", 1)


def _sans_clause(t: str) -> str:
    return t.replace(_ligne_clause(t) + "\n", "", 1)


def _ancre_doublee(t: str) -> str:
    return t + "\n" + _ligne_clause(t) + "\n"


def _clause_fondue(t: str) -> str:
    return t.replace(_ligne_clause(t) + "\n\n", _ligne_clause(t) + "\n", 1)


def _vieille_queue_restauree(t: str) -> str:
    return t.replace("Replay only the bounded benches and non-bench criteria as stated above.", VIEILLE_PHRASE, 1)


def _clause_apres_la_queue(t: str) -> str:
    return _sans_clause(t) + "\n" + _ligne_clause(t) + "\n"


def _clause_francaise_restauree(t: str) -> str:
    return t.replace(_ligne_clause(t), CLAUSE_FR_D_AVANT, 1)


def _atome_d_exec_critic(t: str) -> str:
    return t.replace("write `BANCS: absente` in your findings", "write `BANCS: absente` under `BLIND SPOT`", 1)


MUTANTS_NOMMES = [
    ("copilot-sans-atome-C25", ".github/exec-critic", _sans_atome_copilot,
     "atome absent : acceptance criteria stay replayed"),
    ("codex-sans-clause", ".codex/critic-fable", _sans_clause, "ancre x0, attendu x1"),
    ("ancre-doublee", ".kimi-code/critic-sonnet-max", _ancre_doublee, "ancre x2, attendu x1"),
    ("clause-fondue", ".gemini/critic-opus", _clause_fondue,
     "paragraphe : la clause se fond dans la ligne suivante"),
    ("vieille-queue-codex", ".codex/exec-critic", _vieille_queue_restauree, "ancienne queue presente"),
    ("clause-apres-queue", ".claude/exec-critic", _clause_apres_la_queue,
     "nouvelle queue avant la clause (« above » faux)"),
    ("critique-clause-francaise", ".claude/critic-opus", _clause_francaise_restauree,
     "atome absent : BANCS: line is EXHAUSTIVE"),
    ("critique-atome-d-exec-critic", ".gemini/critic-fable", _atome_d_exec_critic,
     "atome absent : write BANCS: absente in your findings"),
]


@pytest.mark.parametrize(("etiquette", "cle", "muter", "attendu"), MUTANTS_NOMMES,
                         ids=[m[0] for m in MUTANTS_NOMMES])
def test_mutant_nomme_rougit(etiquette, cle, muter, attendu):
    texte = _lire(cle)
    assert constats(texte, _nom(cle)) == [], f"{cle} doit etre vert avant mutation"
    mute = muter(texte)
    assert mute != texte, f"{etiquette} : mutation sans effet"
    assert attendu in constats(mute, _nom(cle)), (etiquette, constats(mute, _nom(cle)))
