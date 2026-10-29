"""Le lanceur des fournées du kit et les prompts de session partent sous le verdict de charge du poste
(T-01M4XZWZ9C0ZFVXN3MFSFY1G5V, lot W ; décisions pilote S-01M4Y10HZ6Y0TAXNNK0S1VRFC1,
S-01M4Y2Q1QK4AGNCSPMQ7ES126Y, S-01M537VBGG5RVBCF3KHFV3JMN5 ; annexe A4 du plan). Base du repli à
cinq : T-01M54B1SXM557Z86N1TXEJSRDE, lot D (décision pilote S-01M54B1KQ6SVNCA9ZSRPWHCCFP).

Ce qu'il tient :
  (a) TEXTE — chaque surface du lot porte ses jetons, et en retirer un fait manquer CE jeton seul ;
      aucune forme périmée des plafonds fixes 8/12/9 ou « au plus 3 », ni du repli à trois de la base
      d'avant, ne survit (témoins d'absence) ; toute phrase qui cite `--attendre` porte `timeout: 600000`
      dans la MÊME phrase (C33).
  (b) NODE — `workflow-fournee.js` rejoué sous node avec un `agent()` simulé : 12 grappes et
      PEUT_AJOUTER=3 ⇒ 3 devs ; `max_devs=2` ⇒ 2 ; 0,0,0 ⇒ `charge` ; zéro, retour, zéro, zéro ⇒ pas
      `charge` ; zéro, zéro, départ, zéro ⇒ pas `charge` (M12) ; illisible avec 5 en vol ⇒ 0 et avec 1 en
      vol ⇒ 4 (C33, base à cinq), puis un retour attendu sans contrôle relancé, et trois zéros de REPLI
      avec 5 en vol (contrôles morts E3a, sorties illisibles E3b) ne rendent jamais `charge` ; PEUT_AJOUTER
      négatif ou non entier ⇒ illisible (C45) ; contrôle mort ⇒ illisible, jamais un zéro mesuré ;
      repos simulé (18 cœurs, 3/3 ; lot D de T-01M56Q23NHTEXES5CAT0A03TFJ) : BASE=9 ⇒ première vague 9,
      puis LIBRE=3 à 9 en vol ⇒ 3, sans « cinq d'emblée » ni « +2 » recalculés par le lanceur.
      Chaque cas rougit sur un mutant du script.
  (c) CONTRAT — la sortie RÉELLE de `charge_poste.py verdict` (HOME, XDG et CADRE_STATE_DIR jetables,
      jamais l'état du poste) est lue par le lecteur du script, sans repli.
  (d) VOYAGE (T-01M57JS1GFPVQ93BGEFGX08FDB, lot A et intégration) — `test_workflow_contexte` :
      ARGS fautifs (bancs absents, clôture ``` ouverte, base non hexadécimale, writeset à « .. », branche
      à « - » initial, tests hors pytest ou à métacaractère, session hors https://) ⇒ aucun agent ; base
      SHA-256 admise ; `tests` absent admis, donné hors d'un pytest sur fichiers de test (autre script,
      -p, traversée) refusé (S-01M5APP7E5) ; write-set à `$(`, `;` ou apostrophe refusé ; tout arrêt
      avant dev DIT au premier niveau (`arret`), args sans grappe compris (F1) ; contexte mort, racine
      relative ou différente de `repo`, branche de grappe déjà présente ou non lue ⇒ aucun dev (F6) ;
      chaque dev vérifie son worktree LIÉ avant toute autre commande git (F4) ; agent de fusion mort ⇒
      grappe DOUTEUSE dite et revue (F3) ; `merge_sha` non hexadécimal hors des prompts ; revue de
      sécurité morte ⇒ bloquant « REVUE DE SÉCURITÉ ABSENTE », jamais un rapport perdu (F2) ;
      contexte lu ⇒ les devs partent, et l'agent de contexte ne fait que deux lectures, racine et
      branches — aucune route de dev locale lue (décision S-01M5PCD282N11RGE73BMQK7M70) ; session absente ⇒ ligne Claude-Session omise et dite ; quota ABSENT ou INCONNU ⇒ la vague
      part, `quota: NON MESURÉ` et COVERAGE DEGRADED dits ; branche ou tip rendus par le dev non
      conformes ⇒ aucune fusion ; SAST `--at HEAD` au prompt de fusion et « SAST À RELIRE » journalisé ;
      revue `security-code-review` lancée après fusion, sur les seuls fichiers du write-set. Chaque cas
      rougit sur un mutant du script. Les formes propres à un poste (mandat local, coauteur figé, avis
      local de revue, serveur LM Studio, banc `strip:`) sont des témoins d'absence (a).
  (e) CONTRAT ↔ CODE (D3) — les faits lus dans le code du lanceur (statuts rendus, champs obligatoires,
      session passée par l'appelant, `repo` facultatif) sont dits, dans les deux
      sens, par la SKILL kickoff, kickoff.md, orchestrator.md, PARALLELISME_HOTES.md et README-CLAUDE.md
      — la session passée par l'appelant, dans la PHRASE même qui cite `session`, et l'arrêt `contexte`
      sur une branche de grappe déjà présente ; la résolution de `scriptPath` n'y est jamais redite non
      mesurée (S-01M5APQ7VF) ; un mutant du contrat ou du code fait apparaître l'écart. Il lit des CHAÎNES : il ne prouve pas que la prose
      est juste au-delà de ces faits.
  (f) EXEC AU FIL DE L'EAU (T-01M5SEWAAX2VQQAFBVWSGA1HJ4) — rejoué sous node : après chaque fusion, un
      `exec:<lot>` de type exec-critic part sur `git diff <merge>^1 <merge>`, avec sa ligne `BANCS:`, avant
      la dernière fusion de la fournée ; `exec_par_lot: false` ⇒ aucun ; exec mort ⇒ `ABSENT — relancer
      exec-critic sur <merge>` ; NO_GO journalisé ; un exec en vol compte dans `--actifs` ; son mandat rendu
      passe au juge `jugeMandat` avant tout agent ; `plan` validé (CHEMIN, sans « .. ») et cité au prompt ;
      la revue de sécurité porte `semgrep-scan.sh --since <base>`. Passe de correction : un exec parti
      PENDANT un contrôle rend son verdict périmé et fait remesurer (`[0, 1, 0, 1]`), sans compter parmi les
      nuls ; le `rapport` de l'exec est rendu ; un merge_sha illisible ne lance aucun exec (`ABSENT —
      merge_sha illisible`) ; la sécurité part après le RETOUR de chaque exec. Chaque cas rougit sur un mutant.
Bornes : (b), (c) et (d) sont SAUTÉS NOMMÉMENT sans node ou sans le lanceur ; le lanceur vit sous
`.claude/workflows/` et VOYAGE, donc ils jouent aussi chez l'adoptant ; (a) se tait, en le disant, sur
une surface absente. Le rejeu node simule l'API Workflow (`agent`, `phase`, `log`) : il prouve la logique
des vagues et des arrêts, jamais le runtime, ni qu'un hook mord sur un `agent()` de Workflow.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
JS = ".claude/workflows/workflow-fournee.js"
DIRECT = "docs/tasks/PROMPT-SESSION-DIRECT.md"
DEV = "docs/tasks/PROMPT-SESSION-DEV.md"
PLANS = "docs/tasks/PROMPT-SESSION-PLANS.md"
SURFACES = (JS, DIRECT, DEV, PLANS)
OUTIL = ".agents/bin/charge_poste.py"
TIMEOUT = "timeout: 600000"
ATTENDRE = "--attendre"

COMMANDE_PROMPT = "charge_poste.py verdict --actifs <"
REPLI_PROMPT = "cinq moins les"
JETONS: dict[str, tuple[str, ...]] = {
    JS: ("charge_poste.py verdict --actifs ${enVol} --attendre 540", TIMEOUT, "Math.max(0, 5 - enVol)",
         "ZEROS_MAX = 3", "statut `charge`", "plafond DUR facultatif", "cinq moins tes agents en vol"),
    DIRECT: (COMMANDE_PROMPT, "--attendre 540", TIMEOUT, "PEUT_AJOUTER", REPLI_PROMPT, "statut `charge`",
             "max(0, 5 − devs en vol)",
             # Lot D de T-01M56Q23NHTEXES5CAT0A03TFJ (décision pilote S-01M59PGM83GXXV8ZNGQ8NZFH9T) : BASE
             # d'emblée — min(BASE, LIBRE) à ACTIFS=0, étape 1 du plan —, seuil de repos C/4, puis LIBRE
             # sans délai sous 2C/3, TENU entre appelants.
             "la première vague vaut min(BASE, LIBRE)", "neuf sur 18 cœurs au repos quand rien n'est tenu",
             "charges 1 et 5 min sous C/4", "LIBRE = PLAFOND − ACTIFS − TENU",
             "sous 2C/3 (strict), sans délai entre accords ni limite de deux",
             "accords de moins de 300 s entre appelants",
             # Clôture de T-01M56Q23NH (S-01M5BSJ7PBQD79HMY19BSSBGH2) : l'accord d'une autre session n'est
             # tenu que 300 s, une heure s'il fut donné à ACTIFS = 0 ; les accords propres sont déduits.
             "une heure pour un accord donné à ACTIFS = 0",
             "et ses propres accords de moins de 300 s pas encore en vol",
             # Intégration de T-01M57JS1GFPVQ93BGEFGX08FDB : l'appel vise le lanceur voyageur, jamais l'archive.
             'scriptPath: ".claude/workflows/workflow-fournee.js"'),
    DEV: (COMMANDE_PROMPT, "PEUT_AJOUTER", REPLI_PROMPT),
    PLANS: (COMMANDE_PROMPT, "PEUT_AJOUTER", REPLI_PROMPT),
}
_PERIMES_8_12_9 = ("au-delà de 8", "sous 9", "repli à 8", "8 par défaut", "12 au plus")
#: Le repli et la première vague à TROIS de la base d'avant (T-01M54B1SXM557Z86N1TXEJSRDE) : aiguilles
#: deux à deux disjointes (le moins ASCII du code n'est pas le U+2212 de la prose).
_PERIMES_BASE_3 = ("trois moins les", "max(0, 3 − ")
ABSENTS: dict[str, tuple[str, ...]] = {
    JS: _PERIMES_8_12_9 + ("plafondInitial", "plafondApresCharge", "vm.loadavg", "load1", "MAX_DEVS",
                           "Math.max(0, 3 - enVol)", "max(0, 3 − ", "trois moins tes agents",
                           "jamais trois de plus", "au moins trois devs en vol",
                           # Lot A de T-01M57JS1GFPVQ93BGEFGX08FDB : le lanceur voyage, rien de propre à un poste.
                           "mandat-dev-direct", "~/.local/state/cadre", "Co-Authored-By: Claude",
                           "mcp__local-llm__review_diff", "refonte-packaging", "/Users/", "127.0.0.1:1234",
                           "lms server", "test_python_file_length", "BANCS_DEFAUT", "Jamf",
                           # T-01M5PCCHMWXTRCM5QJT8J5KNEH, lot C : la route de dev locale est retirée (décision
                           # S-01M5PCD282N11RGE73BMQK7M70) ; termes concaténés, aucun ne s'écrit d'un tenant ici.
                           "q" "wen", "Q" "WEN", "dev-" "route", "summarize" "_files", "ask" "_local"),
    DIRECT: _PERIMES_8_12_9 + ("Au plus 8 devs", "au plus 8 agents", "première vague au plus trois")
            + _PERIMES_BASE_3
            # L'ancienne cadence (lot D de T-01M56Q23NHTEXES5CAT0A03TFJ) : cinq d'emblée, +2, 5 min, C/2.
            + ("première vague au plus cinq", "au plus deux de plus par mesure",
               "une mesure accordée au plus toutes les 5 min", "moitié des cœurs",
               # Première vague à BASE nue, sans le TENU (passe de correction du lot D).
               "la première vague vaut BASE")
            + ("passe par le script versionné `docs/interne/chantier/lots/workflow-fournee.js`",
               "<chemin absolu de ce fichier>", "Le script de fournée le fait lui-même en préflight"),
    DEV: ("au plus 3 agents",) + _PERIMES_BASE_3,
    PLANS: ("AU PLUS 3 agents", "au plus 3 agents", "lots de 3") + _PERIMES_BASE_3,
}
#: Un élément de liste ouvre un nouveau paragraphe : deux puces ne font jamais une phrase.
DEBUT_ITEM = re.compile(r"^(?:[-*] |\(\d+\) |\d+\. )")
FIN_PHRASE = re.compile(r"(?<=[.!?])\s+")


def _texte(rel: str) -> str:
    chemin = ROOT / rel
    if not chemin.is_file():
        pytest.skip(f"{rel} absent : surface du kit, banc du lot W non joué")
    return chemin.read_text(encoding="utf-8")


def manquants(texte: str, jetons: tuple[str, ...]) -> list[str]:
    return [j for j in jetons if j not in texte]


def phrases(texte: str) -> list[str]:
    """Les phrases du texte : lignes jointes (préfixe `//` ôté), coupées aux puces, aux lignes vides
    et aux fins de phrase."""
    paragraphes: list[str] = []
    courant: list[str] = []
    for brut in texte.splitlines():
        ligne = brut.strip()
        if ligne.startswith("//"):
            ligne = ligne[2:].strip()
        if (not ligne or DEBUT_ITEM.match(ligne)) and courant:
            paragraphes.append(" ".join(courant))
            courant = []
        if ligne:
            courant.append(ligne)
    if courant:
        paragraphes.append(" ".join(courant))
    return [p for par in paragraphes for p in FIN_PHRASE.split(par) if p.strip()]


def attentes_sans_timeout(texte: str) -> list[str]:
    """Les phrases qui citent `--attendre` sans `timeout: 600000` (C33). `[]` si la règle tient."""
    return [p for p in phrases(texte) if ATTENDRE in p and TIMEOUT not in p]


# --- (a) texte ------------------------------------------------------------------------------------

@pytest.mark.parametrize("surface", SURFACES)
def test_a_chaque_jeton_present_et_seul_a_manquer_quand_on_le_retire(surface: str) -> None:
    texte = _texte(surface)
    assert manquants(texte, JETONS[surface]) == [], surface
    for jeton in JETONS[surface]:
        mute = texte.replace(jeton, "")
        assert manquants(mute, JETONS[surface]) == [jeton], f"{surface} privé de {jeton!r}"


@pytest.mark.parametrize("surface", SURFACES)
def test_a_aucune_forme_perimee_et_chacune_reinjectee_rougit_seule(surface: str) -> None:
    texte = _texte(surface)
    assert manquants(texte, ABSENTS[surface]) == list(ABSENTS[surface]), f"{surface} : forme périmée"
    for forme in ABSENTS[surface]:
        reste = [f for f in ABSENTS[surface] if f != forme]
        assert manquants(texte + "\n" + forme + "\n", ABSENTS[surface]) == reste, forme


@pytest.mark.parametrize("surface", SURFACES)
def test_a_toute_phrase_qui_cite_attendre_porte_le_timeout(surface: str) -> None:
    texte = _texte(surface)
    assert attentes_sans_timeout(texte) == [], surface
    phrase = "Lance `charge_poste.py verdict --actifs 0 --attendre 540`."
    mute = texte + "\n\n" + phrase + " Pose `" + TIMEOUT + "` au Bash.\n"
    assert attentes_sans_timeout(mute) == [phrase], "timeout dans la phrase SUIVANTE : doit rougir"


@pytest.mark.parametrize("surface", (JS, DIRECT))
def test_a_non_vacuite_le_lanceur_cite_attendre_et_le_retrait_du_timeout_rougit(surface: str) -> None:
    texte = _texte(surface)
    citantes = [p for p in phrases(texte) if ATTENDRE in p]
    assert citantes, f"{surface} ne cite plus `--attendre`"
    assert attentes_sans_timeout(texte.replace(TIMEOUT, "timeout")) != [], surface


def test_a_le_decoupage_ne_fond_pas_deux_puces() -> None:
    texte = f"- lance `verdict {ATTENDRE} 540`\n- puis `{TIMEOUT}`\n"
    assert attentes_sans_timeout(texte) == [f"- lance `verdict {ATTENDRE} 540`"]


def test_a_membres_epingles() -> None:
    assert set(JETONS) == set(ABSENTS) == set(SURFACES)
    assert all(TIMEOUT in JETONS[s] for s in (JS, DIRECT))


# --- (b) rejeu node du lanceur ----------------------------------------------------------------------

HARNAIS = r"""
import { readFileSync } from 'node:fs'
const [, , cheminJs, cheminScenario] = process.argv
const sc = JSON.parse(readFileSync(cheminScenario, 'utf8'))
const source = readFileSync(cheminJs, 'utf8').replace('export const meta =', 'const meta =')
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor
const script = new AsyncFunction('args', 'agent', 'pipeline', 'phase', 'log', source)
const j = { controles: [], vagues: [], devs: [], logs: [], max_en_vol: 0, agents: [], prompts: [], types: [] }
const enVol = []
// Exec-critics TENUS (sc.exec_tenus premiers) : rendus seulement par un contrôle `exec_retours`.
// Fusions TENUES (sc.fusion_tenues premières) : rendues seulement par un contrôle `fusion_retours`.
// sc.exec_delai (ms) : chaque exec-critic rend après ce délai et journalise `exec-ret:<lot>` à son retour.
const execEnVol = []
let execTenus = 0
const fusionEnVol = []
let fusionTenues = 0
let nEnVol = 0
let controleEnCours = false
let iVerdict = 0
const tick = () => new Promise(r => setImmediate(r))
const relacher = n => { for (let i = 0; i < n && enVol.length; i++) enVol.shift()() }
const sortieDe = ev => ev.sortie !== undefined ? ev.sortie
  : `PLAFOND=12 BASE=5 SOURCE=defaut\nPEUT_AJOUTER=${ev.peut} DOIT_REDESCENDRE_A=- ACTIFS=0\n` +
    'CHARGE=1.00/1.00/1.00 C=18 PRESSION=1 EDR_CPU=inconnu\nCALIBRATION=stable RELEVES=1 ETAT=ok'
async function agent(prompt, opts) {
  const label = (opts && opts.label) || ''
  j.agents.push(label)
  j.prompts.push([label, prompt])
  j.types.push([label, (opts && opts.agentType) || ''])
  if (label === 'contexte') {
    if (sc.contexte === 'mort') throw new Error('contexte tué')
    return { racine: '/depot', rc_racine: 0, branches: '', ...(sc.contexte || {}) }
  }
  if (label.startsWith('controle')) {
    controleEnCours = true
    try {
      const m = /--actifs (\d+) --attendre 540/.exec(prompt)
      j.controles.push({ actifs: m ? Number(m[1]) : null, timeout: prompt.includes('timeout: 600000') })
      const ev = iVerdict < sc.verdicts.length ? sc.verdicts[iVerdict++] : sc.defaut
      if (ev.retours) {
        relacher(ev.retours === 'tous' ? enVol.length : ev.retours)
        for (let i = 0; i < 8; i++) await tick()
      }
      if (ev.fusion_retours) {
        for (let i = 0; i < 8; i++) await tick()
        for (const r of fusionEnVol.splice(0)) r()
        for (let i = 0; i < 8; i++) await tick()
      }
      if (ev.exec_retours) {
        for (const r of execEnVol.splice(0)) r()
        for (let i = 0; i < 8; i++) await tick()
      }
      j.vagues.push(0)
      if (ev.mort) throw new Error('contrôle tué')
      return { verdict: ev.quota || 'OK', ligne: ev.quota || 'OK', sortie_verdict: sortieDe(ev),
               rc_verdict: ev.rc === undefined ? 0 : ev.rc }
    } finally {
      controleEnCours = false
    }
  }
  if (label.startsWith('dev:')) {
    j.devs.push(label.slice(4))
    j.vagues[j.vagues.length - 1]++
    nEnVol++
    j.max_en_vol = Math.max(j.max_en_vol, nEnVol)
    // sc.dev_delai (ms) : le dev rend après ce délai, hors du relâchement par les contrôles.
    await new Promise(r => (sc.dev_delai ? setTimeout(r, sc.dev_delai) : enVol.push(r)))
    nEnVol--
    return { statut: 'livre', branche: 'wt/' + label.slice(4), head: '0123abc', fichiers: ['f'], temoins: 't', rapport: 'r',
             ...(sc.dev || {}) }
  }
  if (label.startsWith('fusion:')) {
    if (sc.fusion_morte) throw new Error('fusion tuée')
    if (sc.fusion_delai) await new Promise(r => setTimeout(r, sc.fusion_delai))
    if (fusionTenues < (sc.fusion_tenues || 0)) {
      fusionTenues++
      await new Promise(r => fusionEnVol.push(r))
    }
    return { fusionne: true, merge_sha: '0123abcd', controles: 'ok', sast_ok: true, sast: 'clean', ...(sc.fusion || {}) }
  }
  if (label.startsWith('exec:')) {
    if (sc.exec_mort) throw new Error('exec tué')
    if (execTenus < (sc.exec_tenus || 0)) {
      execTenus++
      await new Promise(r => execEnVol.push(r))
    }
    if (sc.exec_delai) {
      nEnVol++  // un exec lent compte parmi les agents en vol (max_en_vol), comme un dev
      j.max_en_vol = Math.max(j.max_en_vol, nEnVol)
      await new Promise(r => setTimeout(r, sc.exec_delai))
      nEnVol--
      j.agents.push('exec-ret:' + label.slice(5))
    }
    return { verdict: 'GO', constats: [], rapport: 'r', ...(sc.exec || {}) }
  }
  if (label === 'securite') {
    if (sc.securite_morte) throw new Error('securite tuée')
    return { bloquants: [], avis: [], rapport: 'ok' }
  }
  return null
}
const garde = setTimeout(() => { console.error('HARNAIS: délai dépassé'); process.exit(3) }, 20000)
const poll = setInterval(() => { if (!controleEnCours && enVol.length) relacher(1) }, 2)
const args = { repo: '/depot', base: 'b0b0b0b', session: 'https://claude.ai/code/session_banc', borne: 1600, label: 'BANC',
               grappes: [], ...sc.args }
for (const cle of sc.sans || []) delete args[cle]
// Un script qui lève rend `resultat: null` et l'erreur : un mutant qui fait planter le lanceur rougit son témoin.
// Un rejet d'un dev en vol, avant que Promise.all ne l'écoute, ne tue pas le harnais : le script le relève.
process.on('unhandledRejection', () => {})
let resultat = null
let erreur = null
try {
  resultat = await script(args, agent, null, () => {}, m => j.logs.push(String(m)))
} catch (e) {
  erreur = String(e && e.message ? e.message : e)
}
clearInterval(poll)
clearTimeout(garde)
process.stdout.write(JSON.stringify({ resultat, erreur, journal: j }))
"""

LECTEUR = r"""
import { readFileSync } from 'node:fs'
const [, , cheminFonction, cheminCas] = process.argv
const lire = new Function(readFileSync(cheminFonction, 'utf8') + '\nreturn lirePeutAjouter')()
const cas = JSON.parse(readFileSync(cheminCas, 'utf8'))
process.stdout.write(JSON.stringify(cas.map(([sortie, rc]) => lire(sortie, rc))))
"""


def _node() -> str:
    # Le lanceur VOYAGE (lot A de T-01M57JS1GFPVQ93BGEFGX08FDB) : le rejeu joue aussi chez l'adoptant.
    if not (ROOT / JS).is_file():
        pytest.skip(f"{JS} absent : rejeu node du lot W non joué")
    node = shutil.which("node")
    if node is None:
        pytest.skip(f"node absent : rejeu node de {JS} non joué")
    return node


def _grappes(n: int) -> list[dict[str, object]]:
    return [{"id": f"T-{i}", "branche": f"wt/T-{i}", "agentType": "dev-mono", "taches": [f"T-{i}"],
             "writeset": ["f"], "consigne": "c", "tests": "python3 -m pytest -q a/test_x.py", "bancs": "a/test_x.py"}
            for i in range(n)]


def muter(source: str, ancre: str, remplacement: str) -> str:
    assert source.count(ancre) == 1, f"ancre de mutant absente ou ambiguë : {ancre!r}"
    return source.replace(ancre, remplacement)


def rejouer(tmp_path: Path, scenario: dict[str, object], source: str | None = None) -> dict[str, object]:
    node = _node()
    js = tmp_path / "workflow-fournee.js"
    js.write_text(source if source is not None else (ROOT / JS).read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "harnais.mjs").write_text(HARNAIS, encoding="utf-8")
    (tmp_path / "scenario.json").write_text(json.dumps(scenario), encoding="utf-8")
    sortie = subprocess.run([node, str(tmp_path / "harnais.mjs"), str(js), str(tmp_path / "scenario.json")],
                            capture_output=True, text=True, timeout=60, check=False)
    assert sortie.returncode == 0, f"harnais node rc={sortie.returncode} : {sortie.stderr[-800:]}"
    return json.loads(sortie.stdout)


def _source() -> str:
    _node()
    return (ROOT / JS).read_text(encoding="utf-8")


TOUS = {"peut": 3, "retours": "tous"}
S_DOUZE = {"args": {"grappes": _grappes(12)}, "verdicts": [], "defaut": TOUS}
S_DUR2 = {"args": {"grappes": _grappes(12), "max_devs": 2}, "verdicts": [], "defaut": TOUS}
S_DUR2_SANS_RETOUR = {"args": {"grappes": _grappes(6), "max_devs": 2}, "verdicts": [], "defaut": {"peut": 3}}
S_TROIS_NULS = {"args": {"grappes": _grappes(12)}, "verdicts": [{"peut": 0}] * 3, "defaut": TOUS}
S_NUL_RETOUR = {"args": {"grappes": _grappes(4)},
                "verdicts": [{"peut": 1}, {"peut": 0}, {"peut": 0, "retours": 1}, {"peut": 0}], "defaut": TOUS}
S_ILLISIBLE_5 = {"args": {"grappes": _grappes(12)}, "verdicts": [{"peut": 5}, {"sortie": "illisible"}],
                 "defaut": {"peut": 0}}


def _vagues(r: dict) -> list[int]:
    return r["journal"]["vagues"]


def test_b_douze_grappes_peut_ajouter_3_part_par_vagues_de_3(tmp_path: Path) -> None:
    r = rejouer(tmp_path, S_DOUZE)
    assert _vagues(r) == [3, 3, 3, 3] and r["journal"]["max_en_vol"] == 3
    assert [c["actifs"] for c in r["journal"]["controles"]] == [0, 3, 3, 3], "--actifs = devs en vol"
    assert all(c["timeout"] for c in r["journal"]["controles"]), "prompt de contrôle sans timeout"
    assert len(r["resultat"]["fusions"]) == 12 and r["resultat"]["charge"] == "sous le verdict de charge"
    mutant = muter(_source(), "Math.min(brut, dur - enVol, restantes)", "Math.min(dur - enVol, restantes)")
    assert _vagues(rejouer(tmp_path, S_DOUZE, mutant))[0] == 12, "mutant verdict ignoré SURVIVANT"


def test_b_max_devs_2_borne_les_devs_en_vol_a_2(tmp_path: Path) -> None:
    r = rejouer(tmp_path, S_DUR2)
    assert r["journal"]["max_en_vol"] == 2 and _vagues(r)[0] == 2 and r["resultat"]["max_devs"] == 2
    r2 = rejouer(tmp_path, S_DUR2_SANS_RETOUR)
    assert r2["journal"]["max_en_vol"] == 2, "plafond dur franchi sans retour"
    assert [c["actifs"] for c in r2["journal"]["controles"]][1:] == [1] * (len(r2["journal"]["controles"]) - 1), (
        "au plafond dur, un retour est attendu AVANT la mesure")
    mutant = muter(_source(), "return Math.min(n, DUR_MAX)", "return DUR_MAX")
    assert rejouer(tmp_path, S_DUR2, mutant)["journal"]["max_en_vol"] == 3, "mutant max_devs ignoré SURVIVANT"


#: Repos simulé (lot D de T-01M56Q23NHTEXES5CAT0A03TFJ, décision pilote S-01M59PGM83GXXV8ZNGQ8NZFH9T) : la
#: sortie du verdict sur 18 cœurs à 3/3 — BASE=9 d'emblée, puis LIBRE=3 (TENU d'un autre appelant), relayé sans
#: délai ni +2. Quatre retours AVANT la 2e vague : place dure 12 − 5 = 7 et 5 grappes restantes, donc aucune
#: autre borne ne rend 3 — seul LIBRE le fait (M3/M4 de l'exec-critic, passe de correction du lot D).
_REPOS_9 = ("PLAFOND=12 BASE=9 SOURCE=defaut\nPEUT_AJOUTER=9 DOIT_REDESCENDRE_A=- ACTIFS=0\n"
            "CHARGE=3.00/3.00/3.00 C=18 PRESSION=1 EDR_CPU=inconnu\nCALIBRATION=stable RELEVES=1 ETAT=ok")
_LIBRE_3 = _REPOS_9.replace("PEUT_AJOUTER=9 DOIT_REDESCENDRE_A=- ACTIFS=0",
                            "PEUT_AJOUTER=3 DOIT_REDESCENDRE_A=- ACTIFS=9")
S_REPOS_9 = {"args": {"grappes": _grappes(14)},
             "verdicts": [{"sortie": _REPOS_9}, {"sortie": _LIBRE_3, "retours": 4}], "defaut": TOUS}
_ANCRE_BRUT = "const brut = peut === null ? Math.max(0, 5 - enVol) : peut"
_ANCRE_BORNE = "Math.min(brut, dur - enVol, restantes)"


def test_b_repos_simule_base_9_puis_libre_sans_plus_deux(tmp_path: Path) -> None:
    """Le lanceur relaie BASE=9 puis LIBRE tels quels : il ne recalcule ni « cinq d'emblée », ni « +2 », ni
    PLAFOND − en vol, et n'ignore pas LIBRE quand un agent tourne."""
    r = rejouer(tmp_path, S_REPOS_9)
    assert _vagues(r)[0] == 9 and r["journal"]["controles"][0]["actifs"] == 0, _vagues(r)
    assert _vagues(r)[1] == 3 and r["journal"]["controles"][1]["actifs"] == 9, _vagues(r)
    assert len(r["resultat"]["fusions"]) == 14 and r["resultat"]["charge"] == "sous le verdict de charge"
    ignore = muter(_source(), _ANCRE_BRUT, _ANCRE_BRUT.replace(": peut", ": (enVol > 0 && peut > 0 ? 99 : peut)"))
    assert _vagues(rejouer(tmp_path, S_REPOS_9, ignore))[1] != 3, "mutant « LIBRE ignoré en vol » SURVIVANT"
    recalcule = muter(_source(), _ANCRE_BRUT,
                      _ANCRE_BRUT.replace(": peut", ": (enVol > 0 && peut > 0 ? 12 - enVol : peut)"))
    assert _vagues(rejouer(tmp_path, S_REPOS_9, recalcule))[1] != 3, "mutant « PLAFOND − en vol » SURVIVANT"
    cinq = muter(_source(), _ANCRE_BORNE, "Math.min(brut, 5, dur - enVol, restantes)")
    assert _vagues(rejouer(tmp_path, S_REPOS_9, cinq))[:2] == [5, 3], "mutant « première vague au plus cinq » SURVIVANT"
    plus_deux = muter(_source(), _ANCRE_BORNE, "Math.min(brut, enVol > 0 ? 2 : brut, dur - enVol, restantes)")
    assert _vagues(rejouer(tmp_path, S_REPOS_9, plus_deux))[:2] == [9, 2], "mutant « +2 par mesure » SURVIVANT"


def test_b_trois_verdicts_nuls_de_suite_rendent_le_statut_charge(tmp_path: Path) -> None:
    r = rejouer(tmp_path, S_TROIS_NULS)
    assert len(r["journal"]["controles"]) == 3 and r["journal"]["devs"] == []
    assert r["resultat"]["charge"].startswith("ARRÊT CHARGE")
    assert [x["statut"] for x in r["resultat"]["refus"]] == ["charge"] * 12
    mutant = muter(_source(), "const ZEROS_MAX = 3", "const ZEROS_MAX = 4")
    assert len(rejouer(tmp_path, S_TROIS_NULS, mutant)["journal"]["devs"]) == 12, "mutant 4 nuls SURVIVANT"


def test_b_zero_retour_zero_zero_ne_rend_pas_charge(tmp_path: Path) -> None:
    r = rejouer(tmp_path, S_NUL_RETOUR)
    assert r["resultat"]["charge"] == "sous le verdict de charge" and len(r["resultat"]["fusions"]) == 4
    assert _vagues(r)[:4] == [1, 0, 0, 0]
    mutant = muter(_source(), "  actifs--\n  zeros = 0\n", "  actifs--\n")
    assert rejouer(tmp_path, S_NUL_RETOUR, mutant)["resultat"]["charge"].startswith("ARRÊT CHARGE"), (
        "mutant sans remise à zéro au retour SURVIVANT")


def test_b_zero_zero_depart_zero_ne_rend_pas_charge(tmp_path: Path) -> None:
    """M12 : une vague partie remet le compte des nuls à zéro."""
    scenario = {"args": {"grappes": _grappes(4)}, "verdicts": [{"peut": 0}, {"peut": 0}, {"peut": 1}, {"peut": 0}],
                "defaut": TOUS}
    r = rejouer(tmp_path, scenario)
    assert _vagues(r)[:4] == [0, 0, 1, 0] and r["resultat"]["charge"] == "sous le verdict de charge"
    mutant = muter(_source(), "  zeros = 0\n  log(`vague ${vague} : ${k}", "  log(`vague ${vague} : ${k}")
    assert rejouer(tmp_path, scenario, mutant)["resultat"]["charge"].startswith("ARRÊT CHARGE"), (
        "mutant M12 sans remise à zéro après une vague partie SURVIVANT")


#: E3a / E3b (passe exec-critic) : trois zéros de REPLI avec 5 devs en vol ne sont pas une charge mesurée
#: (base à cinq : sous cinq en vol, le repli accorde un départ et ne rend pas zéro — réserve C25).
E3 = [
    ("E3a trois contrôles morts", [{"mort": True}] * 3),
    ("E3b trois sorties illisibles", [{"sortie": "Traceback"}, {"sortie": ""}, {"sortie": "x", "rc": 1}]),
]


@pytest.mark.parametrize("nom,repli", E3, ids=[e[0] for e in E3])
def test_b_e3_trois_zeros_de_repli_ne_rendent_jamais_charge(tmp_path: Path, nom: str, repli: list) -> None:
    scenario = {"args": {"grappes": _grappes(12)}, "verdicts": [{"peut": 5}, *repli], "defaut": TOUS}
    r = rejouer(tmp_path, scenario)
    assert _vagues(r)[:2] == [5, 0], f"{nom} : 5 en vol, zéro de repli attendu"
    assert r["resultat"]["charge"] == "sous le verdict de charge", f"{nom} : `charge` sans charge mesurée"
    assert len(r["journal"]["devs"]) == 12 and [x["statut"] for x in r["resultat"]["refus"]] == []
    assert r["resultat"]["verdict_illisible"].startswith("OUTIL ILLISIBLE : 3 "), "l'outil illisible doit être dit"
    assert r["journal"]["controles"][2]["actifs"] == 4, "après un zéro de repli : un retour attendu AVANT le contrôle"
    mutant = muter(_source(), "if (k === 0 && c.peut === null) {", "if (false) {")
    assert rejouer(tmp_path, scenario, mutant)["resultat"]["charge"].startswith("ARRÊT CHARGE"), (
        f"mutant {nom} (zéro de repli compté) SURVIVANT")


def test_b_illisible_avec_5_en_vol_vaut_0_jamais_5_de_plus(tmp_path: Path) -> None:
    r = rejouer(tmp_path, S_ILLISIBLE_5)
    assert _vagues(r)[:2] == [5, 0], "illisible avec 5 en vol : 0"
    assert r["journal"]["controles"][2]["actifs"] == 4, "illisible : aucun contrôle relancé avant un retour"
    un = {"args": {"grappes": _grappes(12)}, "verdicts": [{"peut": 1}, {"sortie": "illisible"}],
          "defaut": {"peut": 0}}
    assert _vagues(rejouer(tmp_path, un))[:2] == [1, 4], "illisible avec 1 en vol : 4"
    mutant = muter(_source(), "Math.max(0, 5 - enVol)", "5")
    assert _vagues(rejouer(tmp_path, S_ILLISIBLE_5, mutant))[1] == 5, "mutant « illisible ⇒ 5 » SURVIVANT"
    base_trois = muter(_source(), "Math.max(0, 5 - enVol)", "Math.max(0, 3 - enVol)")
    assert _vagues(rejouer(tmp_path, un, base_trois))[:2] != [1, 4], "mutant « base à trois » SURVIVANT"


_VALIDE_1 = ("PLAFOND=12 BASE=5 SOURCE=defaut\nPEUT_AJOUTER=1 DOIT_REDESCENDRE_A=- ACTIFS=1\n"
             "CHARGE=1.00/1.00/1.00 C=18 PRESSION=1 EDR_CPU=inconnu\nCALIBRATION=stable RELEVES=1 ETAT=ok")
#: (nom, événement du second verdict, mutant qui doit faire rougir CE cas). Avec 1 dev en vol, un
#: verdict illisible vaut max(0, 5 − 1) = 4 ; lu tel quel il vaudrait 0 ou 1.
C45 = [
    ("négatif", {"sortie": _VALIDE_1.replace("PEUT_AJOUTER=1", "PEUT_AJOUTER=-2")},
     ("!/^\\d+$/.test(m[1])", "m[1] === ''")),
    ("non entier", {"sortie": _VALIDE_1.replace("PEUT_AJOUTER=1", "PEUT_AJOUTER=1.5")},
     ("!/^\\d+$/.test(m[1])", "m[1] === ''")),
    ("sans ligne PLAFOND=", {"sortie": _VALIDE_1.replace("PLAFOND=12 ", "PLAFOND:12 ")},
     ("if (!/^[ \\t]*PLAFOND=\\d+\\s/m.test(sortie)) return null\n", "")),
    ("commande tuée", {"sortie": _VALIDE_1, "rc": -1}, ("rc !== 0 || ", "")),
]


@pytest.mark.parametrize("nom,evenement,mutation", C45, ids=[c[0] for c in C45])
def test_b_c45_peut_ajouter_negatif_non_entier_ou_sans_plafond_vaut_illisible(
        tmp_path: Path, nom: str, evenement: dict, mutation: tuple[str, str]) -> None:
    scenario = {"args": {"grappes": _grappes(8)}, "verdicts": [{"peut": 1}, evenement], "defaut": {"peut": 0}}
    assert _vagues(rejouer(tmp_path, scenario))[:2] == [1, 4], f"{nom} : illisible ⇒ max(0, 5 − 1)"
    mutant = muter(_source(), *mutation)
    assert _vagues(rejouer(tmp_path, scenario, mutant))[1] != 4, f"mutant {nom} SURVIVANT"


def test_b_controle_mort_vaut_illisible_et_quota_arrete(tmp_path: Path) -> None:
    # Réserve C25 : recalé à 5 devs en vol (zéro de repli, un retour attendu AVANT le contrôle suivant),
    # et le cas à 1 en vol garde la mesure de la base (max(0, 5 − 1) = 4).
    mort = {"args": {"grappes": _grappes(8)}, "verdicts": [{"peut": 5}, {"mort": True}], "defaut": {"peut": 0}}
    r = rejouer(tmp_path, mort)
    assert _vagues(r)[:2] == [5, 0], "contrôle mort avec 5 en vol : max(0, 5 − 5) = 0"
    assert r["journal"]["controles"][2]["actifs"] == 4, "contrôle mort : zéro de repli, un retour attendu AVANT"
    un = {"args": {"grappes": _grappes(8)}, "verdicts": [{"peut": 1}, {"mort": True}], "defaut": {"peut": 0}}
    assert _vagues(rejouer(tmp_path, un))[:2] == [1, 4], "contrôle mort avec 1 en vol : max(0, 5 − 1) = 4"
    zero = muter(_source(), "lirePeutAjouter(sortie, c.rc_verdict) : null", "lirePeutAjouter(sortie, c.rc_verdict) : 0")
    assert rejouer(tmp_path, mort, zero)["journal"]["controles"][2]["actifs"] != 4, (
        "mutant « contrôle mort ⇒ zéro mesuré » SURVIVANT")
    assert _vagues(rejouer(tmp_path, un, zero))[:2] != [1, 4], "mutant « contrôle mort ⇒ 0 » SURVIVANT (1 en vol)"
    quota = {"args": {"grappes": _grappes(5)}, "verdicts": [{"peut": 3, "quota": "ATTERRIR"}], "defaut": TOUS}
    r = rejouer(tmp_path, quota)
    assert r["journal"]["devs"] == [] and r["resultat"]["quota"].startswith("ARRÊT QUOTA")
    assert [x["statut"] for x in r["resultat"]["refus"]] == ["quota"] * 5


# --- (c) contrat avec la sortie réelle de l'outil ---------------------------------------------------

def _fonction(source: str, nom: str) -> str:
    debut = source.find(f"function {nom}(")
    assert debut >= 0, f"{nom} absente de {JS}"
    return source[debut:source.index("\n}\n", debut) + 2]


def _lire(tmp_path: Path, cas: list[tuple[str, int]]) -> list[int | None]:
    node = _node()
    (tmp_path / "lire.js").write_text(_fonction(_source(), "lirePeutAjouter"), encoding="utf-8")
    (tmp_path / "lecteur.mjs").write_text(LECTEUR, encoding="utf-8")
    (tmp_path / "cas.json").write_text(json.dumps(cas), encoding="utf-8")
    commande = [node, str(tmp_path / "lecteur.mjs"), str(tmp_path / "lire.js"), str(tmp_path / "cas.json")]
    sortie = subprocess.run(commande, capture_output=True, text=True, timeout=60, check=False)
    assert sortie.returncode == 0, sortie.stderr[-800:]
    return json.loads(sortie.stdout)


def test_c_la_sortie_reelle_du_verdict_est_lue_sans_repli(tmp_path: Path) -> None:
    _node()
    jetable = tmp_path / "poste"
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CADRE_", "XDG_", "CLAUDE_PROJECT_DIR"))}
    env.update(HOME=str(jetable / "home"), XDG_STATE_HOME=str(jetable / "xdg-state"),
               XDG_CONFIG_HOME=str(jetable / "xdg-config"), CADRE_STATE_DIR=str(jetable / "state"),
               CADRE_CONFIG_HOME=str(jetable / "config"), LC_ALL="C")
    for cle in ("HOME", "XDG_STATE_HOME", "XDG_CONFIG_HOME"):
        Path(env[cle]).mkdir(parents=True, exist_ok=True)
    reel = subprocess.run([sys.executable, str(ROOT / OUTIL), "verdict", "--actifs", "0"], cwd=str(ROOT), env=env,
                          capture_output=True, text=True, timeout=60, check=False)
    assert reel.returncode == 0, reel.stderr[-800:]
    attendu = re.search(r"^PEUT_AJOUTER=(\d+) ", reel.stdout, re.MULTILINE)
    assert attendu is not None, reel.stdout
    sans_plafond = reel.stdout.replace("PLAFOND=", "PLAFOND:", 1)
    lus = _lire(tmp_path, [(reel.stdout, 0), (reel.stdout, 1), (sans_plafond, 0)])
    assert lus == [int(attendu.group(1)), None, None], "sortie réelle lue avec repli, ou rc/PLAFOND= ignorés"


# --- (d) voyage : contexte dérivé, quota absent (lot A de T-01M57JS1GFPVQ93BGEFGX08FDB) -----------------

_G4 = _grappes(4)


def _scenario(**extra: object) -> dict[str, object]:
    return {"args": {"grappes": _G4}, "verdicts": [], "defaut": TOUS, **extra}


def _arret(r: dict, statut: str) -> bool:
    """Aucun dev parti, chaque grappe rendue au statut `statut`, et l'arrêt dit au premier niveau du retour."""
    return (r["resultat"] is not None and r["journal"]["devs"] == []
            and [x["statut"] for x in r["resultat"]["refus"]] == [statut] * len(_G4)
            and (r["resultat"]["arret"] or {}).get("statut") == statut)


def _motif_arret(r: dict, aiguille: str) -> bool:
    return r["resultat"] is not None and aiguille in (r["resultat"]["arret"] or {}).get("motif", "")


def _logs(r: dict, aiguille: str) -> bool:
    return any(aiguille in ligne for ligne in r["journal"]["logs"])


def _prompts(r: dict, aiguille: str) -> bool:
    return any(aiguille in prompt for _, prompt in r["journal"]["prompts"])


def _quota_dit(r: dict) -> bool:
    return (len(r["journal"]["devs"]) == 4 and r["resultat"]["quota"].startswith("NON MESURÉ")
            and _logs(r, "COVERAGE DEGRADED — quota non mesuré"))


def _fusion_prompts(r: dict, aiguille: str) -> bool:
    return any(label.startswith("fusion:") and aiguille in prompt for label, prompt in r["journal"]["prompts"])


def _sans_fusion(r: dict, motif: str) -> bool:
    """Les quatre devs rendent, AUCUN agent de fusion ne part, chaque refus porte `motif`."""
    return (len(r["journal"]["devs"]) == 4 and not any(a.startswith("fusion:") for a in r["journal"]["agents"])
            and len(r["resultat"]["refus"]) == 4 and all(motif in x["motif"] for x in r["resultat"]["refus"]))


def _args(**champs: object) -> dict[str, object]:
    """Un scénario dont les ARGS sont surchargés ; `grappe` remplace des champs de la grappe 1."""
    grappe = champs.pop("grappe", None)
    grappes = [{**g, **grappe} if grappe and i == 1 else g for i, g in enumerate(_G4)]
    return {**_scenario(), "args": {"grappes": grappes, **champs}}


def _args_refuses(motif: str):
    return lambda r: r["journal"]["agents"] == [] and _arret(r, "args") and motif in r["resultat"]["refus"][0]["rapport"]


def _exec_au_fil(r: dict) -> bool:
    """(f) Un `exec:<lot>` de type exec-critic par fusion, APRÈS elle et AVANT la fin de la fournée (le premier
    part avant la dernière fusion), sur le diff de son merge, avec sa ligne `BANCS:` ; son verdict est rendu."""
    agents = r["journal"]["agents"]
    execs = [p for label, p in r["journal"]["prompts"] if label.startswith("exec:")]
    return (len(execs) == 4
            and all([f"exec:T-{i}", "exec-critic"] in r["journal"]["types"] for i in range(4))
            and all("git diff 0123abcd^1 0123abcd -- f" in p and "\nBANCS: a/test_x.py\n" in p for p in execs)
            and all(agents.index(f"fusion:T-{i}") < agents.index(f"exec:T-{i}") for i in range(4))
            and agents.index("exec:T-0") < agents.index("fusion:T-3")
            and all(x["exec"] == {"verdict": "GO", "constats": [], "rapport": "r"} for x in r["resultat"]["fusions"]))


_SANS_BANCS = [{k: v for k, v in g.items() if k != "bancs"} if i == 2 else g for i, g in enumerate(_G4)]
_CLOTURE = [{**g, "consigne": "```sh\nmake"} if i == 1 else g for i, g in enumerate(_G4)]
_SESSION = "Claude-Session: https://claude.ai/code/session_banc"
#: (nom, scénario, témoin qui doit tenir sur le vrai script, mutation (ancre, remplacement) qui le fait tomber).
#: Ce que l'agent de contexte ne lit plus (T-01M5PCCHMWXTRCM5QJT8J5KNEH, lot C) : aucune route de dev locale.
_ROUTE_LOCALE = ("--status", "q" "wen")
CONTEXTE = [
    ("contexte_lu_les_devs_partent", _scenario(),
     lambda r: (len(r["journal"]["devs"]) == 4 and "q" "wen" not in r["resultat"]
                and _prompts(r, _SESSION)),
     ("log(`contexte : ${contexte}`)", "return arretAvantDev('contexte', 'mutant')")),
    # Lot C de T-01M5PCCHMWXTRCM5QJT8J5KNEH : deux lectures au contexte, racine et branches, rien d'autre.
    ("contexte_sans_route_locale", _scenario(),
     lambda r: (len(r["journal"]["devs"]) == 4
                and any(l == "contexte" and p.startswith("Deux lectures") for l, p in r["journal"]["prompts"])
                and not any(l == "contexte" and any(a in p for a in _ROUTE_LOCALE)
                            for l, p in r["journal"]["prompts"])),
     ("(2) Depuis cette racine,", "(2) Depuis cette racine, \\`bash .agents/bin/" "q" "wen-dev.sh --status\\`, puis")),
    ("contexte_mort", _scenario(contexte="mort"),
     lambda r: _arret(r, "contexte") and r["journal"]["agents"] == ["contexte"],
     ("const lu = lireRacine(ctx, A.repo)", "ctx = ctx || { racine: '/depot', rc_racine: 0, "
      "branches: '' }\nconst lu = lireRacine(ctx, A.repo)")),
    ("racine_relative", _scenario(contexte={"racine": "depot"}, sans=["repo"]), lambda r: _arret(r, "contexte"),
     (r"if (!UNE_LIGNE.test(r) || !/^(\/|[A-Za-z]:[\\/])/.test(r)) return", "if (!UNE_LIGNE.test(r)) return")),
    ("repo_different", {**_scenario(), "args": {"grappes": _G4, "repo": "/autre"}}, lambda r: _arret(r, "contexte"),
     ("if (attendu !== undefined && r !== attendu)", "if (false)")),
    ("args_sans_bancs", {**_scenario(), "args": {"grappes": _SANS_BANCS}},
     lambda r: (r["journal"]["agents"] == [] and _arret(r, "args")
                and "bancs OBLIGATOIRE" in r["resultat"]["refus"][0]["rapport"]),
     ("if (bancsDe(g) === null) f.push(", "if (false) f.push(")),
    ("consigne_cloture_ouverte", {**_scenario(), "args": {"grappes": _CLOTURE}},
     lambda r: (r["journal"]["agents"] == [] and _arret(r, "args")
                and "cloture-ouverte" in r["resultat"]["refus"][0]["rapport"]),
     ("  if (cloture) return `cloture-ouverte : ligne-${ouverte}`\n", "")),
    ("base_non_hexadecimale", _args(base="HEAD;rm"), _args_refuses("base : sha"),
     ("typeof a.base !== 'string' || !SHA.test(a.base)", "typeof a.base !== 'string'")),
    ("base_sha256_admise", _args(base="a" * 64), lambda r: len(r["journal"]["devs"]) == 4,
     ("const SHA = /^[0-9a-f]{7,64}$/", "const SHA = /^[0-9a-f]{7,40}$/")),
    ("writeset_point_point", _args(grappe={"writeset": ["../x"]}), _args_refuses("writeset"),
     ("&& !p.startsWith('/') && !p.split('/').includes('..'))", "&& !p.startsWith('/'))")),
    ("branche_tiret_initial", _args(grappe={"branche": "-x"}), _args_refuses("branche"),
     ("const BRANCHE = /^\\w[\\w./-]*$/", "const BRANCHE = /^[\\w./-]+$/")),
    ("tests_metacaractere", _args(grappe={"tests": "python3 -m pytest x; rm -rf ."}), _args_refuses("tests"),
     ("(?: ${FICHIER_TEST})+$`)", "(?: .*)?$`)")),
    ("tests_hors_pytest", _args(grappe={"tests": "make test"}), _args_refuses("tests"),
     ("|| !TESTS.test(g.tests)", "|| !UNE_LIGNE.test(g.tests)")),
    # Décision S-01M5APP7E5 : `tests` FACULTATIF ; donné, un pytest sur des fichiers de test, rien d'autre.
    ("tests_autre_script", _args(grappe={"tests": "bash .agents/pyrun.sh .agents/bin/tasks.py done T-1"}),
     _args_refuses("tests"),
     ("const TESTS = new RegExp(`^(?:bash \\\\.agents/pyrun\\\\.sh -m pytest|python3? -m pytest|pytest)"
      "(?: -[qxvs]+)*(?: ${FICHIER_TEST})+$`)",
      "const TESTS = /^(?:bash \\.agents\\/pyrun\\.sh|python3?(?: -[A-Za-z]+)* -m pytest|pytest)"
      "(?: [^;&|$<>`\\r\\n]*)?$/")),
    ("tests_option_p", _args(grappe={"tests": "python3 -m pytest -p a/test_x.py"}), _args_refuses("tests"),
     ("(?: -[qxvs]+)*", "(?: -[a-z]+)*")),
    ("tests_traversee", _args(grappe={"tests": "pytest ../x/test_a.py"}), _args_refuses("tests"),
     (r"const SEGMENT = '\\.?\\w[\\w.@+-]*'", r"const SEGMENT = '[\\w.@+-]+'")),
    ("tests_absent_admis", {**_scenario(), "args": {"grappes": [{k: v for k, v in g.items() if k != "tests"}
                                                               for g in _G4]}},
     lambda r: (r["resultat"] is not None and len(r["journal"]["devs"]) == 4
                and _fusion_prompts(r, "aucun test ciblé donné par la grappe")
                and _prompts(r, "Témoin : aucun test ciblé")),
     ("if (g.tests !== undefined && (", "if ((")),
    ("writeset_substitution", _args(grappe={"writeset": ["a$(id)"]}), _args_refuses("writeset"),
     (r"const CHEMIN = /^[\w.@+/-]+$/", r"const CHEMIN = /^[^\r\n`\s]+$/")),
    ("writeset_apostrophe", _args(grappe={"writeset": ["a'b;c"]}), _args_refuses("writeset"),
     (r"const CHEMIN = /^[\w.@+/-]+$/", r"const CHEMIN = /^[^\r\n`\s]+$/")),
    # F1 : un arrêt avant tout dev est DIT au premier niveau du retour, même sans grappe lisible.
    ("args_sans_grappes", {**_scenario(), "args": {"grappes": []}},
     lambda r: (r["resultat"] is not None and r["journal"]["agents"] == []
                and (r["resultat"]["arret"] or {}).get("statut") == "args" and _motif_arret(r, "grappes")),
     ("  arret = { statut, motif }\n", "")),
    # F4 : le dev vérifie son worktree LIÉ AVANT toute autre commande git.
    ("dev_verifie_son_worktree", _scenario(),
     lambda r: all("isolation worktree absente" in p and 0 <= p.find("--git-common-dir") < p.find("git switch -c")
                   for label, p in r["journal"]["prompts"] if label.startswith("dev:")) and len(r["journal"]["devs"]) == 4,
     (r"\`git rev-parse --path-format=absolute --git-dir --git-common-dir\`", r"\`git rev-parse --git-dir\`")),
    # F6 : une branche de grappe déjà présente (course interrompue) arrête tout avant le premier dev.
    ("branches_lues_au_contexte", _scenario(),
     lambda r: (len(r["journal"]["devs"]) == 4
                and any(l == "contexte" and "git branch --list -- wt/T-0 wt/T-1 wt/T-2 wt/T-3" in p
                        for l, p in r["journal"]["prompts"])),
     ("\\`git branch --list -- ${A.grappes.map(g => g.branche).join(' ')}\\`", "\\`git branch --list\\`")),
    ("branches_presentes", _scenario(contexte={"branches": "  wt/T-1\n+ wt/T-2\n"}),
     lambda r: (_arret(r, "contexte") and r["journal"]["agents"] == ["contexte"]
                and _motif_arret(r, "branches déjà présentes : wt/T-1 wt/T-2 —")),
     ("if (ctx.branches.trim()) {", "if (false) {")),
    ("branches_non_lues", _scenario(contexte={"branches": None}),
     lambda r: _arret(r, "contexte") and _motif_arret(r, "branches des grappes non lues"),
     ("if (typeof ctx.branches !== 'string') return arretAvantDev(", "if (false) return arretAvantDev(")),
    # F3 : agent de fusion mort ⇒ grappe DOUTEUSE, dite, et son write-set dans la revue de sécurité.
    ("fusion_morte_douteuse", _scenario(fusion_morte=True),
     lambda r: (r["resultat"] is not None and r["resultat"]["fusions"] == [] and len(r["resultat"]["refus"]) == 4
                and all("état INCONNU" in x["motif"] for x in r["resultat"]["refus"])
                and r["resultat"]["securite"] is not None
                and any(l == "securite" and "-- f`" in p and "DOUTEUSES" in p for l, p in r["journal"]["prompts"])),
     ("    if (!f) {\n      f = { fusionne: null", "    if (false) {\n      f = { fusionne: null")),
    ("fusion_morte_revue_lancee", _scenario(fusion_morte=True),
     lambda r: r["resultat"] is not None and "securite" in r["journal"]["agents"],
     ("if (fusions.length || douteuses.length) {", "if (fusions.length) {")),
    # Constat connu c : le sha rendu par l'agent de fusion n'entre dans aucun prompt sans contrôle.
    ("merge_sha_controle", _scenario(fusion={"merge_sha": "x$(id)"}),
     lambda r: (r["resultat"] is not None and len(r["resultat"]["fusions"]) == 4 and not _prompts(r, "$(id)")
                and _logs(r, "merge_sha rendu")),
     ("|| !SHA.test(f.merge_sha))", "|| false)")),
    # F2 : revue de sécurité morte ⇒ bloquant « REVUE DE SÉCURITÉ ABSENTE », rapport rendu, fusions dites.
    ("securite_morte_bloquant", _scenario(securite_morte=True),
     lambda r: (r["resultat"] is not None and len(r["resultat"]["fusions"]) == 4
                and "REVUE DE SÉCURITÉ ABSENTE" in " ".join((r["resultat"]["securite"] or {}).get("bloquants", []))
                and _logs(r, "revue de sécurité morte")),
     ("  if (!securite) {\n    securite = {", "  if (false) {\n    securite = {")),
    ("securite_morte_rapport_rendu", _scenario(securite_morte=True),
     lambda r: r["resultat"] is not None and r["erreur"] is None,
     ("  } catch (e) {\n    log(`revue de sécurité morte", "  } catch (e) {\n    throw e\n    log(`revue de sécurité morte")),
    ("session_hors_https", _args(session="s$(id)"), _args_refuses("session"),
     ("typeof a.session !== 'string' || !SESSION.test(a.session)", "typeof a.session !== 'string'")),
    ("dev_branche_autre", _scenario(dev={"branche": "wt/autre"}), lambda r: _sans_fusion(r, "≠ branche de la grappe"),
     ("const ecart = d.branche !== g.branche ?", "const ecart = false ?")),
    ("dev_tip_non_sha", _scenario(dev={"head": "x; y"}), lambda r: _sans_fusion(r, "sha hexadécimal attendu"),
     ("(typeof d.head !== 'string' || !SHA.test(d.head)) ?", "false ?")),
    ("sast_au_prompt_de_fusion", _scenario(), lambda r: _fusion_prompts(r, "semgrep-scan.sh --at HEAD"),
     (r"3. SAST : \`bash .agents/security/semgrep-scan.sh --at HEAD\`.", "3. (rien).")),
    ("sast_non_propre_journalise", _scenario(fusion={"sast_ok": False, "sast": "1 finding"}),
     lambda r: _logs(r, "SAST À RELIRE : T-0 — 1 finding"),
     ("for (const r of fusions) if (!r.fusion.sast_ok)", "for (const r of []) if (!r.fusion.sast_ok)")),
    ("revue_securite_apres_fusion", _scenario(dev={"fichiers": ["f", "../../etc/passwd", "g h"]}),
     lambda r: (["securite", "security-code-review"] in r["journal"]["types"] and r["resultat"]["securite"] is not None
                and any(l == "securite" and "-- f`" in p and "passwd" not in p for l, p in r["journal"]["prompts"])),
     ("if (fusions.length || douteuses.length) {", "if (false) {")),
    ("revue_securite_filtre_le_writeset", _scenario(dev={"fichiers": ["f", "../../etc/passwd"]}),
     lambda r: not _prompts(r, "passwd"),
     (".filter(p => r.writeset.includes(p))", "")),
    ("session_absente", _scenario(sans=["session"]),
     lambda r: (len(r["journal"]["devs"]) == 4 and not _prompts(r, "Claude-Session:")
                and _logs(r, "ligne Claude-Session omise") and "absente" in r["resultat"]["contexte"]),
     ("const piedSession = () => (A.session ? `\\n   Claude-Session: ${A.session}` : '')",
      "const piedSession = () => `\\n   Claude-Session: ${A.session}`")),
    ("quota_absent", _scenario(defaut={**TOUS, "quota": "ABSENT"}), _quota_dit,
     ("if (!c || c.verdict !== 'OK') {", "if (!c) {")),
    ("quota_inconnu", _scenario(defaut={**TOUS, "quota": "INCONNU"}), _quota_dit,
     ("if (!c || c.verdict !== 'OK') {", "if (!c || c.verdict === 'ABSENT') {")),
    # T-01M5SEWAAX2VQQAFBVWSGA1HJ4 : un exec-critic par lot dès SA fusion, au fil de l'eau (f).
    ("exec_au_fil_des_fusions", _scenario(), _exec_au_fil,
     ("execs.push(lancerExec(g, f, d).then(v => { res.exec = v }))", "void 0")),
    ("exec_par_lot_false_aucun_exec", _args(exec_par_lot=False),
     lambda r: (len(r["resultat"]["fusions"]) == 4 and not any(a.startswith("exec:") for a in r["journal"]["agents"])
                and all(x["exec"] is None for x in r["resultat"]["fusions"])),
     ("if (A.exec_par_lot !== false && f.fusionne === true) {", "if (f.fusionne === true) {")),
    ("exec_mort_absent", _scenario(exec_mort=True),
     lambda r: (r["erreur"] is None and len(r["resultat"]["fusions"]) == 4 and _logs(r, "exec-critic mort")
                and all((x["exec"] or {}).get("verdict") == "ABSENT — relancer exec-critic sur 0123abcd"
                        for x in r["resultat"]["fusions"])),
     ("return { verdict: `ABSENT — relancer exec-critic sur ${f.merge_sha}`, constats: [], rapport: '' }", "return null")),
    ("exec_no_go_journalise", _scenario(exec={"verdict": "NO_GO", "constats": ["f:1 casse"]}),
     lambda r: (_logs(r, "EXEC NO_GO : T-0 — f:1 casse")
                and all(x["exec"] == {"verdict": "NO_GO", "constats": ["f:1 casse"], "rapport": "r"}
                        for x in r["resultat"]["fusions"])),
     ("if (e.verdict === 'NO_GO') log(", "if (false) log(")),
    # Passe de correction : le rapport de l'exec-critic (un COVERAGE DEGRADED compris) est rendu au retour.
    ("exec_rapport_rendu", _scenario(exec={"rapport": "COVERAGE DEGRADED — banc refusé"}),
     lambda r: all((x["exec"] or {}).get("rapport") == "COVERAGE DEGRADED — banc refusé"
                   for x in r["resultat"]["fusions"]) and len(r["resultat"]["fusions"]) == 4,
     ("return { verdict: e.verdict, constats, rapport: typeof e.rapport === 'string' ? e.rapport : '' }",
      "return { verdict: e.verdict, constats }")),
    ("exec_ne_peut_trancher_dit_au_prompt", _scenario(),
     lambda r: sum(1 for l, p in r["journal"]["prompts"] if l.startswith("exec:")
                   and "verdict NO_GO, 1er constat « COVERAGE DEGRADED — exec-critic indisponible : <quoi> »" in p) == 4,
     (" Si tu ne peux pas trancher : verdict NO_GO, 1er constat « COVERAGE DEGRADED — exec-critic indisponible : "
      "<quoi> ».`", "`")),
    # Un merge_sha illisible ne part à aucun exec-critic : le verdict ABSENT le dit.
    ("exec_merge_sha_illisible", _scenario(fusion={"merge_sha": "zz"}),
     lambda r: (not any(a.startswith("exec:") for a in r["journal"]["agents"]) and len(r["resultat"]["fusions"]) == 4
                and all((x["exec"] or {}).get("verdict", "").startswith("ABSENT — merge_sha illisible")
                        for x in r["resultat"]["fusions"])),
     ("      if (SHA.test(f.merge_sha)) {\n", "      if (true) {\n")),
    ("securite_sast_since_base", _scenario(),
     lambda r: any(l == "securite" and "`bash .agents/security/semgrep-scan.sh --since b0b0b0b`" in p
                   for l, p in r["journal"]["prompts"]),
     (r"\`bash .agents/security/semgrep-scan.sh --since ${A.base}\`", r"\`bash .agents/security/semgrep-scan.sh\`")),
    ("plan_traversee_refuse", _args(plan="../p.md"), _args_refuses("plan"),
     ("if (a.plan !== undefined && !chemins([a.plan]))", "if (a.plan !== undefined && typeof a.plan !== 'string')")),
    ("plan_au_prompt_exec", _args(plan="docs/p.md"),
     lambda r: sum(1 for l, p in r["journal"]["prompts"] if l.startswith("exec:") and "du plan `docs/p.md`" in p) == 4,
     (r", et ceux du plan \`${A.plan}\` pour ce lot", ", et ceux du plan pour ce lot")),
    ("exec_par_lot_non_booleen", _args(exec_par_lot="non"), _args_refuses("exec_par_lot"),
     ("typeof a.exec_par_lot !== 'boolean'", "false")),
]


@pytest.mark.parametrize("nom,scenario,temoin,mutation", CONTEXTE, ids=[c[0] for c in CONTEXTE])
def test_workflow_contexte(tmp_path: Path, nom: str, scenario: dict, temoin, mutation: tuple[str, str]) -> None:
    assert temoin(rejouer(tmp_path, scenario)), f"{nom} : le lanceur ne tient pas"
    mutant = muter(_source(), *mutation)
    assert not temoin(rejouer(tmp_path, scenario, mutant)), f"mutant {nom} SURVIVANT"


#: (f) Le premier exec-critic est TENU pendant le 3e contrôle : il y est compté dans `--actifs`.
S_EXEC_ACTIF = {"args": {"grappes": _grappes(2)}, "exec_tenus": 1, "defaut": TOUS,
                "verdicts": [{"peut": 1}, {"peut": 0, "retours": 1}, {"peut": 1, "exec_retours": "tous"}]}


def test_f_exec_critic_en_vol_compte_dans_actifs(tmp_path: Path) -> None:
    """Le dev T-0 rend au 2e contrôle, fusionne, son exec-critic part et reste en vol : le 3e contrôle voit
    `--actifs 1` (l'exec seul), puis la fournée va au bout."""
    r = rejouer(tmp_path, S_EXEC_ACTIF)
    assert [c["actifs"] for c in r["journal"]["controles"]] == [0, 1, 1], r["journal"]["controles"]
    assert len(r["resultat"]["fusions"]) == 2 and r["erreur"] is None
    mutant = muter(_source(), "await attendreRetour()\n  actifs++\n", "await attendreRetour()\n")
    assert [c["actifs"] for c in rejouer(tmp_path, S_EXEC_ACTIF, mutant)["journal"]["controles"]][2] == 0, (
        "mutant « exec-critic hors du verdict de charge » SURVIVANT")


_PERIME = "  if (actifs > avant) { log(`vague ${vague} : verdict périmé, remesure`); continue }\n"
#: (f) Course : la fusion de T-0 est TENUE jusqu'au 3e contrôle, son exec-critic part PENDANT cette mesure.
S_COURSE = {"args": {"grappes": _grappes(3)}, "exec_tenus": 1, "fusion_tenues": 1, "defaut": TOUS,
            "verdicts": [{"peut": 1}, {"peut": 0, "retours": 1}, {"peut": 1, "fusion_retours": True},
                         {"peut": 3, "retours": "tous", "exec_retours": "tous"}]}


def test_f_exec_parti_pendant_un_controle_rend_son_verdict_perime(tmp_path: Path) -> None:
    """Un exec-critic parti pendant la 3e mesure manque à son `--actifs` : ce PEUT_AJOUTER n'est pas appliqué,
    la 4e mesure voit l'exec (`[0, 1, 0, 1]`) ; sans la remesure, le dev T-1 partirait sur un verdict périmé et
    la 4e mesure verrait `--actifs 2`."""
    r = rejouer(tmp_path, S_COURSE)
    assert [c["actifs"] for c in r["journal"]["controles"]] == [0, 1, 0, 1], r["journal"]["controles"]
    assert _logs(r, "vague 3 : verdict périmé, remesure") and len(r["resultat"]["fusions"]) == 3
    mutant = muter(_source(), _PERIME, "")
    assert [c["actifs"] for c in rejouer(tmp_path, S_COURSE, mutant)["journal"]["controles"]] == [0, 1, 0, 2], (
        "mutant « remesure retirée » SURVIVANT")


#: Même course, exec-critic en vol 150 ms, puis deux verdicts nuls : le tour périmé ne compte pas parmi eux.
S_COURSE_NULS = {"args": {"grappes": _grappes(3)}, "fusion_tenues": 1, "exec_delai": 150, "defaut": TOUS,
                 "verdicts": [{"peut": 1}, {"peut": 0, "retours": 1}, {"peut": 1, "fusion_retours": True},
                              {"peut": 0}]}


def test_f_verdict_perime_ne_compte_pas_parmi_les_nuls(tmp_path: Path) -> None:
    def temoin(r: dict) -> bool:
        return (_logs(r, "vague 3 : verdict périmé") and _logs(r, "vague 4 : aucun départ")
                and _logs(r, "verdict nul 2/3") and r["resultat"]["charge"] == "sous le verdict de charge"
                and len(r["resultat"]["fusions"]) == 3)
    assert temoin(rejouer(tmp_path, S_COURSE_NULS)), "le tour périmé compte parmi les nuls"
    mutant = muter(_source(), _PERIME, _PERIME.replace("{ log(", "{ zeros++; log("))
    assert not temoin(rejouer(tmp_path, S_COURSE_NULS, mutant)), "mutant « périmé compté nul » SURVIVANT"


#: (f) Exec-critics lents (150 ms) : la sécurité tourne EN PARALLÈLE, chaque exec est relevé avant le retour.
S_EXEC_LENTS = {"args": {"grappes": _grappes(3)}, "exec_delai": 150, "verdicts": [], "defaut": TOUS}


def test_f_securite_en_parallele_et_chaque_exec_releve(tmp_path: Path) -> None:
    def temoin(r: dict) -> bool:
        ag = r["journal"]["agents"]
        return ("securite" in ag and all(f"exec-ret:T-{i}" in ag for i in range(3))
                and all(x["exec"] is not None for x in r["resultat"]["fusions"]))
    r = rejouer(tmp_path, S_EXEC_LENTS)
    assert temoin(r), "un exec non relevé au retour"
    ag = r["journal"]["agents"]
    assert ag.index("securite") < ag.index("exec-ret:T-2"), "la sécurité attend les exec (doctrine : en parallèle)"
    mutant = muter(_source(), "await Promise.all(execs)\n", "void 0\n")
    assert not temoin(rejouer(tmp_path, S_EXEC_LENTS, mutant)), "mutant « execs non attendus » SURVIVANT"


#: (f) max_devs 1, dev 100 ms, fusion 30 ms, exec 150 ms : le dev T-1 part PENDANT la fusion de T-0 (sa place
#: est rendue) ; l'exec-critic de T-0 ATTEND une place, la fournée reste série (1 agent en vol).
S_EXEC_SERIE = {"args": {"grappes": _grappes(2), "max_devs": 1}, "dev_delai": 100, "fusion_delai": 30,
                "exec_delai": 150, "verdicts": [], "defaut": TOUS}


def test_f_exec_attend_une_place_sous_max_devs(tmp_path: Path) -> None:
    assert rejouer(tmp_path, S_EXEC_SERIE)["journal"]["max_en_vol"] == 1
    mutant = muter(_source(), "  while (actifs >= DUR) await attendreRetour()\n", "")
    assert rejouer(tmp_path, S_EXEC_SERIE, mutant)["journal"]["max_en_vol"] == 2, (
        "mutant « exec sans attente de place » SURVIVANT")


def test_f_mandat_exec_juge_avant_tout_agent(tmp_path: Path) -> None:
    """`fautesArgs` juge le mandat RENDU de l'exec-critic comme celui du dev : un prompt d'exec à deux lignes
    `BANCS:` arrête tout avant le premier agent ; sans ce contrôle, il partirait."""
    casse = muter(_source(), "\nBANCS: ${bancsDe(g)}\nCritères d'acceptation du lot",
                  "\nBANCS: ${bancsDe(g)}\nBANCS: ${bancsDe(g)}\nCritères d'acceptation du lot")
    r = rejouer(tmp_path, _scenario(), casse)
    assert r["journal"]["agents"] == [] and _arret(r, "args")
    assert "mandat de l'exec-critic (sans-liste : 2 ligne(s) BANCS:)" in r["resultat"]["refus"][0]["rapport"]
    assert len(rejouer(tmp_path, _args(exec_par_lot=False), casse)["journal"]["devs"]) == 4, (
        "exec_par_lot: false ne juge aucun mandat d'exec")
    sans_juge = muter(casse, "    if (refusExec) f.push(", "    if (false) f.push(")
    assert len(rejouer(tmp_path, _scenario(), sans_juge)["journal"]["devs"]) == 4, "mutant « juge d'exec retiré » SURVIVANT"


# --- (e) CONTRAT ↔ CODE (intégration de T-01M57JS1GFPVQ93BGEFGX08FDB, D3 ; S-01M5AK9DP0) ---------------------
# Les FAITS sont lus dans le CODE du lanceur (statuts rendus, champs obligatoires, d'où vient la session,
# `repo` facultatif), et chaque surface du contrat doit les dire : un contrat écrit sur le plan
# plutôt que sur le code rougit, et un code qui change sans son contrat aussi.

CONTRAT_SKILL = ".agents/skills/kickoff/SKILL.md"
CONTRAT_CMD = ".claude/commands/kickoff.md"
CONTRAT_ORCH = ".claude/agents/orchestrator.md"
CONTRAT_REF = ".agents/ref/PARALLELISME_HOTES.md"
CONTRAT_README = "README-CLAUDE.md"
#: (surface, début, fin) : le segment du contrat ; fin None = fin de ligne, "## " = section suivante.
SEGMENTS = ((CONTRAT_SKILL, "THE BATCH LAUNCHER", "THE STATION VERDICT (S-01M4Y10HZ6Y0TAXNNK0S1VRFC1)"),
            (CONTRAT_CMD, "LE LANCEUR DE FOURNÉE", None), (CONTRAT_ORCH, "the batch launcher**", None),
            (CONTRAT_REF, "## Le lanceur de fournée", "\n## "),
            (CONTRAT_README, "Batch launcher, the kit's own and travelling", "\n- Subagents"))
#: Surfaces qui portent les FAITS sans la liste des statuts ni des champs obligatoires.
CONTRAT_FAITS_SEULS = (CONTRAT_ORCH, CONTRAT_README)
#: Formes d'un contrat qui contredit ce code : session dérivée jamais passée, préflight qui décide, et
#: chargement de `scriptPath` dit non mesuré alors que S-01M5APQ7VF l'a mesuré.
CONTRAT_PERIMES = ("never passed by hand", "jamais passés à la main", "derived by the script, never passed",
                   "--preflight", "GREEN preflight", "préflight VERT", "a `bancs` field on EVERY lot",
                   "un champ `bancs` sur CHAQUE lot", "NOT MEASURED before the post-merge smoke",
                   "n'est PAS MESURÉE avant le smoke", "No run-time test has run yet",
                   "Aucun essai à l'exécution n'a encore tourné",
                   # Lot C de T-01M5PCCHMWXTRCM5QJT8J5KNEH : ni statut ni remède de la route de dev locale retirée.
                   "`q" "wen`", "q" "wen-dev.sh", "dev-" "route")
#: La branche d'une grappe déjà présente arrête au statut `contexte` (F6), dit dans chaque langue.
BRANCHE_PRESENTE = re.compile(r"branche d'une grappe déjà présente|branch (?:is )?already present")
#: Fin de phrase d'un segment de contrat (point ou point-virgule suivi d'un blanc).
PHRASE_CONTRAT = re.compile(r"(?<=[.;])\s+")


def segment(texte: str, debut: str, fin: str | None) -> str:
    i = texte.find(debut)
    if i < 0:
        return ""
    j = texte.find("\n" if fin is None else fin, i + len(debut))
    return re.sub(r"\s+", " ", texte[i:(len(texte) if j < 0 else j)])


def faits_du_code(js: str) -> dict[str, object]:
    corps = js[js.index("function fautesArgs("):js.index("\n}\n", js.index("function fautesArgs("))]
    contexte = js[js.index("const CONTEXTE_SCHEMA"):js.index("\n}\n", js.index("const CONTEXTE_SCHEMA"))]
    restants = re.search(r"stopQuota \? '(\w+)' : '(\w+)'", js)
    lus = set(re.findall(r"\ba\.(\w+)", corps))
    return {
        "statuts": sorted(set(re.findall(r"arretAvantDev\('(\w+)'", js)) | set(restants.groups() if restants else ())),
        "obligatoires": sorted((lus - set(re.findall(r"\ba\.(\w+) !== undefined", corps)))
                               | ({"bancs"} if "bancsDe(g) === null" in corps else set())),
        "session_appelant": "A.session" in js and "session" not in contexte,
        "repo_facultatif": "a.repo !== undefined" in corps,
        "branche_presente_arrete": "return arretAvantDev('contexte', `branches déjà présentes" in js,
    }


def fautes_contrat(js: str, textes: dict[str, str]) -> list[str]:
    faits = faits_du_code(js)
    f: list[str] = []
    for surface, debut, fin in SEGMENTS:
        seg = segment(textes[surface], debut, fin)
        if not seg:
            f.append(f"{surface} : segment du lanceur introuvable ({debut!r})")
            continue
        bas = seg.lower()
        # Ce que le contrat AFFIRME, comparé au fait du code dans les DEUX sens. La session vient de l'appelant
        # quand la PHRASE qui cite `session` nomme l'appelant : « la session appelante » ailleurs ne compte pas.
        affirme = {
            "session_appelant": any("`session`" in p and ("caller" in p.lower() or "appelant" in p.lower())
                                    for p in PHRASE_CONTRAT.split(seg)),
            # Même règle de phrase : « `tests`, optional » ailleurs ne dit rien de `repo`.
            "repo_facultatif": any("`repo`" in p and ("optional" in p.lower() or "facultatif" in p.lower())
                                   for p in PHRASE_CONTRAT.split(seg)),
            "branche_presente_arrete": "`contexte`" in seg and bool(BRANCHE_PRESENTE.search(bas)),
        }
        f += [f"{surface} : le contrat dit {k}={v}, le code {k}={faits[k]}" for k, v in affirme.items()
              if v != faits[k]]
        f += [f"{surface} : forme contraire au code : {p!r}" for p in CONTRAT_PERIMES if p in seg]
        if surface in CONTRAT_FAITS_SEULS:
            continue
        f += [f"{surface} : statut `{s}` rendu par le code, absent du contrat" for s in faits["statuts"]
              if f"`{s}`" not in seg]
        f += [f"{surface} : champ obligatoire `{c}` du code, absent du contrat" for c in faits["obligatoires"]
              if f"`{c}`" not in seg]
    return f


def _contrat() -> tuple[str, dict[str, str]]:
    textes = {}
    for surface in (JS, *(s for s, _, _ in SEGMENTS)):
        if not (ROOT / surface).is_file():
            pytest.skip(f"{surface} absent : contrat ↔ code du lanceur non jugé")
        textes[surface] = (ROOT / surface).read_text(encoding="utf-8")
    return textes.pop(JS), textes


def test_e_faits_du_code_non_vacants() -> None:
    js, _ = _contrat()
    faits = faits_du_code(js)
    assert faits["statuts"] == ["args", "charge", "contexte", "quota"], faits["statuts"]
    assert faits["obligatoires"] == ["bancs", "base", "grappes", "label"], faits["obligatoires"]
    assert faits["session_appelant"] and faits["repo_facultatif"]
    assert faits["branche_presente_arrete"]


def test_e_contrat_dit_le_code() -> None:
    js, textes = _contrat()
    assert fautes_contrat(js, textes) == []


#: (nom, côté, ancre, remplacement) : chaque mutant, du contrat OU du code, fait apparaître un écart.
MUTANTS_CONTRAT = [
    ("skill_session_derivee", CONTRAT_SKILL, "The CALLER passes `session`", "The Claude context gives the session"),
    # D3 : kickoff.md porte aussi « la session appelante » : seule la phrase qui cite `session` compte.
    ("cmd_session_derivee", CONTRAT_CMD, "L'APPELANT passe `session`", "Le contexte Claude donne `session`"),
    ("ref_session_derivee", CONTRAT_REF, "c'est l'APPELANT qui le\n  passe", "c'est le contexte qui le\n  donne"),
    ("cmd_statut_contexte_retire", CONTRAT_CMD, "`contexte` (racine illisible", "(racine illisible"),
    ("orch_repo_interdit", CONTRAT_ORCH, "`repo` is optional", "`repo` is never passed"),
    ("ref_charge_retire", CONTRAT_REF, "`charge` (trois verdicts", "(trois verdicts"),
    ("skill_preflight_restaure", CONTRAT_SKILL, "no route to a local model exists any more",
     "a red `--preflight` stops every dev"),
    # Lot C de T-01M5PCCHMWXTRCM5QJT8J5KNEH : la route de dev locale retirée ne revient dans aucun contrat.
    ("skill_route_locale_restauree", CONTRAT_SKILL, "no route to a local model exists any more",
     "an armed local route stops every dev (status `q" "wen`)"),
    ("cmd_remede_restaure", CONTRAT_CMD, "aucune route vers un modèle local n'existe plus",
     "route locale armée : remède `bash .agents/bin/q" "wen-dev.sh --off`"),
    ("orch_route_locale_restauree", CONTRAT_ORCH, "no route to a local model exists any more",
     "an armed local route launches NO dev (status `q" "wen`)"),
    ("code_statut_neuf", JS, "return arretAvantDev('contexte', lu.motif)", "return arretAvantDev('racine', lu.motif)"),
    ("code_session_derivee", JS, "racine: { type: 'string' }, rc_racine: { type: 'number' },",
     "racine: { type: 'string' }, rc_racine: { type: 'number' }, session: { type: 'string' },"),
    ("code_route_locale_restauree", JS, "log(`contexte : ${contexte}`)",
     "if (A.route) return arretAvantDev('q" "wen', 'route locale')\nlog(`contexte : ${contexte}`)"),
    # Réalignement du contrat (F6, F7, S-01M5APQ7VF) : README-CLAUDE porte les faits ; branche présente ;
    # chargement mesuré, jamais redit « non mesuré ».
    ("readme_session_derivee", CONTRAT_README, "The CALLER passes `session`", "The context gives `session`"),
    ("readme_repo_interdit", CONTRAT_README, "`repo` is optional", "`repo` is never passed"),
    ("cmd_branche_retiree", CONTRAT_CMD, ", ou branche d'une grappe déjà présente", ""),
    ("skill_branche_retiree", CONTRAT_SKILL, "or a grappe's branch already present", "or a grappe left over"),
    ("orch_branche_retiree", CONTRAT_ORCH, "a grappe whose branch is already present stops",
     "a grappe left over stops"),
    ("code_branche_admise", JS, "return arretAvantDev('contexte', `branches déjà présentes",
     "return log(`branches déjà présentes"),
    ("skill_smoke_perime", CONTRAT_SKILL, "Its `scriptPath` resolution is MEASURED",
     "Its own runtime is NOT MEASURED before the post-merge smoke of its task; its `scriptPath` resolution is"),
    ("readme_smoke_perime", CONTRAT_README,
     "Measured on 2026-10-19: the launcher resolves `scriptPath` and loads the script without starting an agent.",
     "No run-time test has run yet. The launcher resolves `scriptPath` and loads the script without starting an agent."),
]


@pytest.mark.parametrize("nom,cote,ancre,remplacement", MUTANTS_CONTRAT, ids=[m[0] for m in MUTANTS_CONTRAT])
def test_e_mutant_contrat_ou_code_rougit(nom: str, cote: str, ancre: str, remplacement: str) -> None:
    js, textes = _contrat()
    if cote == JS:
        js = muter(js, ancre, remplacement)
    else:
        textes = {**textes, cote: muter(textes[cote], ancre, remplacement)}
    assert fautes_contrat(js, textes) != [], f"mutant SURVIVANT : {nom}"


def test_readme_claude_garanties_restituees() -> None:
    texte = (ROOT / CONTRAT_README).read_text(encoding="utf-8")
    garanties = (
        "not kept up to date by a bench",
        "`git ls-tree -r origin/template/starter-kit -- .agents/state/`",
        "`SEED — 4 path(s)`",
        "from the tracked adopter seed",
        "or a `plan-critic` verdict",
        "`Edit(./.agents/state/gates/PLAN_CIBLE_REQUIRED)`",
        "`.agents/state/gates/AFFIRMATION_REQUIRED`",
        "closing critics that `BINOME_MIN` sets",
        "`scripts/index-refresh.sh`",
        "only when the stores token is `committed`/`nothing`/`failed`/`locked-out` — never on `busy:`",
        "business logic, regressions and unverified assumptions",
        "functional regressions, unverified assumptions",
    )
    assert not [garantie for garantie in garanties if garantie not in texte]
