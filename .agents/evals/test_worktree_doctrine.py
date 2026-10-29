"""Filet de la doctrine « devs parallèles en worktrees » (T-00001067, S-00003449, S-00003502).

Fonctions pures sur le TEXTE (racine injectable). Les deux côtés d'une comparaison passent par
`norm` (NFKC, apostrophe typographique, casefold, espaces) : la casse, un blanc insécable ou une
phrase pliée sur deux lignes ne contournent pas l'absence. Les ancres « (n) » des points et « (x) »
des clauses sont SÉQUENTIELLES : la première après la précédente — « le contrôle (c) » cité dans
la clause (e) du point 4, ou « (a)-(e) » au point 8, ne sont pas des ancres. Chaque mutant vérifie
d'abord muté != original.

BORNE (L-00000187), dite plutôt que découverte : ce filet épingle le VOCABULAIRE, l'ORDRE (31
transpositions de clauses, et l'ordre RELATIF des 9 jetons de ROUTEUR sur la ligne « Pipeline
mandatory » d'AGENTS.md — jamais son exhaustivité : un pas AJOUTÉ au routeur entre deux jetons, ou
retiré s'il n'en est pas un, passe) et un jeu FERMÉ de jetons de SENS (les gestes, les remèdes et les
négations de POINTS ; les 14 MOTIFS d'ABSENT, moins les sites gardés, plus les reformulations de
EN_PLUS). Les lignes SENS sont des RETRAITS de jeton à remplacement inversé, pas une lecture du sens.
Passent : une reformulation de l'ancienne règle hors de ces motifs, une inversion qui GARDE tous les
jetons épinglés (une négation ou une échappatoire AJOUTÉE à côté d'un jeton), un paragraphe déplacé
ou dupliqué, une copie de la règle hors des cinq fichiers et des sept SURFACES : le filet ne lit pas
le sens, il en épingle les marqueurs. Les sept SURFACES qui voyagent (README, skills `codebase-indexing`
et `index`, les quatre défs `indexer`) ne portent que l'ABSENCE (ABSENT_SURFACES, sans les deux gardes
larges) : une surface VIDÉE ou réécrite sans la nouvelle règle passe ; une surface manquante lève."""
import itertools
import re
import unicodedata
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FILES = {
    "agents": "AGENTS.md",
    "skill": ".agents/skills/task-board/SKILL.md",
    "kickoff_skill": ".agents/skills/kickoff/SKILL.md",
    "kickoff_cmd": ".claude/commands/kickoff.md",
    "copilot": ".github/copilot-instructions.md",
}
NBSP, APOS = chr(0xA0), chr(0x2019)  # sans séquence d'échappement : aucune couche d'outil ne les décode en route
MOTIFS = [  # l'ancienne règle, en regex sur le texte normalisé : les 12 motifs du balayage + deux gardes larges
    r"au plus une t[âa]che `?running`?", r"au plus une `?running`?", r"at most one `?running`?",
    r"at most one task is `?running`?", r"une seule t[âa]che `?running`?", r"one task at a time",
    r"un dev [aà] la fois", r"un seul [aà] la fois", r"une t[âa]che [aà] la fois", r"single.running",
    r"mono-t[âa]che", r"one .?running", r"au plus une?\b", r"at most one\b",
]
GARDES = {  # sites GARDÉS, mesurés (D1) : la phrase y DÉCRIT le store ou sérialise la clôture du matin
    "kickoff_skill": [r"one task at a time"], "kickoff_cmd": [r"one task at a time"],
    "skill": [r"single.running", r"one .?running"],
}
EN_PLUS = {  # reformulations mesurées (T-1067 it. 3, critique B) et la phrase fausse « seul un recouvrement » (it. 4, B-C2)
    "agents": [r"un (?:seul )?dev [aà] la fois", r"seul un recouvrement"],
    "skill": [r"only one (?:dev|task|`?running`?)", r"no more than one (?:dev|task)"],
    "kickoff_skill": [r"only one (?:dev|task|`?running`?)", r"no more than one (?:dev|task)", r"only an overlap"],
    "kickoff_cmd": [r"only one (?:dev|task|`?running`?)", r"no more than one (?:dev|task)", r"only an overlap"],
    "copilot": [r"only one (?:dev|task|`?running`?)", r"no more than one (?:dev|task)", r"only an overlap"],
}
ABSENT = {nom: [m for m in MOTIFS if m not in GARDES.get(nom, [])] + EN_PLUS.get(nom, []) for nom in FILES}
SURFACES = {  # surfaces qui VOYAGENT et décrivent le board (binôme de fin de la fournée 3, critic-fable) : ABSENCE seule,
    # aucun jeton PRESENT ; préfixe « surf_ » pour qu'aucune clé ne commence par une clé de FILES (`rouge` lit `startswith`)
    "surf_readme": "README.md",
    "surf_codebase_indexing": ".agents/skills/codebase-indexing/SKILL.md",
    "surf_index": ".agents/skills/index/SKILL.md",
    "surf_indexer_claude": ".claude/agents/indexer.md",
    "surf_indexer_gemini": ".gemini/agents/indexer.md",
    "surf_indexer_kimi": ".kimi-code/agents/indexer.md",
    "surf_indexer_copilot": ".github/agents/indexer.agent.md",
}
ABSENT_SURFACES = [  # MOTIFS sans les deux gardes LARGES (README dit, à bon droit, « installs at most one skill ») + EN_PLUS
    m for m in MOTIFS if m not in (r"au plus une?\b", r"at most one\b")
] + [r"only one (?:dev|task|`?running`?)", r"no more than one (?:dev|task)"]
POINTEUR = "(worktree mode: `.agents/skills/task-board/SKILL.md`)"
TABLE_HOTES = ".agents/ref/PARALLELISME_HOTES.md"  # FB6 (lot D1) : la portée par hôte renvoie à la table ; épinglé sous
# `agents`, `copilot` et le point 3 de la skill SEULS — `kickoff_skill` et `kickoff_cmd` relèvent d'un autre lot (C41)
PRESENT = {  # jetons PORTEURS de la phrase neuve — absents du fichier ENTIER à la base
    "agents": ["Les devs tournent EN PARALLÈLE", "chacun dans un worktree git", "S-00003475",
               "L'état reste au dépôt principal", 'isolation: "worktree"', "MESURÉ sur Claude Code seul",
               "dès que leurs write-sets DÉCLARÉS sont PROUVÉS disjoints",
               "`tasks.py parallel`, qui refuse notamment un recouvrement de write-set",
               "un refus = SÉRIALISER ou compléter la déclaration", TABLE_HOTES],
    "kickoff_skill": ["devs run in parallel, in git worktrees", POINTEUR, "any `parallel` refusal serialises (an overlap",
                      "an undeclared writeset is declared first"],
    "kickoff_cmd": ["Devs run in parallel, in git worktrees", POINTEUR, "any `parallel` refusal serialises (an overlap",
                    "an undeclared writeset is declared first"],
    "copilot": ["devs run in parallel, in git worktrees", POINTEUR, "any `parallel` refusal serialises (an overlap",
                "an undeclared file set is declared first", TABLE_HOTES],
}
POINTS = {  # jetons PORTEURS, cherchés dans LE point nommé du paragraphe ; absents de la skill ENTIÈRE à la base
    1: ["S-00003475", "S-00003484", "T-00001068", "T-00001069", "[exclusive]", "a LABEL, never a lock",
        "stores jetables", "seul écrivain"],
    2: ["un refus = SÉRIALISER", "git worktree list", "avec TOUS les membres en vol", "git status --porcelain",
        "fichiers COMMUNS au write-set du nouveau dev", "Le write-set ENTIER n'est jamais lu", "s'ATTRIBUE avant le lancement",
        "fait ATTENDRE, jamais présumer", "jamais en vol ni membre de `parallel`", "en forme générale `save()` le refuse"],
    3: ['isolation: "worktree"', "origin/HEAD", "git switch -c wt/<T>", "git reset --keep <base>", "INCONDITIONNEL",
        "merge-base --is-ancestor", "git worktree add -b wt/<T>", "COMMITE par `git add` PAR NOM",
        "n'appelle jamais `tasks.py`", "jamais `-A`", TABLE_HOTES],
    4: ["merge-base --is-ancestor", "rev-list --count", "--no-renames", "À LA FRONTIÈRE DE SEGMENT", "Index vide",
        "merge --no-ff", "jamais rebase puis fast-forward", "passe à VIDE", "LU avant que la fusion soit émise",
        "ne refuse JAMAIS", "REFUS, jamais un passage", "sinon branche REFUSÉE (base fausse)",
        "sinon branche REFUSÉE ; un diff VIDE est REFUSÉ", "sinon branche REFUSÉE (livraison partielle)"],
    5: ["Delta specs", "branches fusionnées, worktrees retirés", "security-code-review", "security-orchestrator", "build_index.py --if-stale", "documenter", "se tient PAR FOURNÉE (S-00003502)",
        "DEPUIS le principal", "APRÈS la dernière fusion",
        "AUCUNE fusion pendant qu'il tourne — le sha tracé est HEAD à son ARRÊT", "verdict PAR TÂCHE",
        "<dernière fusion>", "pour CHACUN des deux", "sinon un binôme bis de fournée", "L-00000553",
        "ne compte ni ne rassure", "Corrections de ses constats", "puis commit", "clone frère", "l'immunité vient du clone frère", "ne la fait PAS attendre",
        "verify.sh --at HEAD", "--at HEAD --linux", "T-00001083"],
    6: ["Cycle de vie : c'est l'ORCHESTRATEUR qui retire les worktrees", "L'outil ne retire PAS le worktree",
        "git worktree unlock", "git worktree remove",
        "APRÈS le `done`", "jamais ne se contourne"],
    7: ["Parapluie", "PRÉFÉRÉE", "portée de revue déclarée AVANT le critique", "le chantier ne prête plus rien",
        "SYM-11067"],
    8: ["tenu À LA MAIN", "crédit croisé", "du MÊME critique ÉCRASE", "n'expire JAMAIS", "la jambe reprise `binome_reprise_refusal`",
        "est la SEULE à comparer le sha tracé", "comparé à AUCUNE fusion", "@0f154858", "la machine ne prouve ni",
        "aucune garde ne refuse une branche qui déborde", "ne se juge que sur la trace EMPRUNTÉE au slot (parapluie)",
        "une trace DIRECTE (forme générale) n'expire JAMAIS", "(hors emprunt sans borne)",
        "`done` ne vérifie ni que `wt/<T>` a été fusionnée"],
}
SKILL_AILLEURS = ["sauf la ligne Task tracking", "Several tasks run at once", "Les devs tournent EN PARALLÈLE",
                  "parallel devs in git worktrees"]
LETTRES = {4: "abcde", 5: "abcdefg"}
ORDRE = {  # sous-suite ordonnée, lue dans LE SEUL point nommé (« le binôme » figure aussi au point 1)
    4: ["merge-base --is-ancestor", "rev-list --count", "--no-renames", "index vide", "merge --no-ff"],
    5: ["delta specs", "security-code-review", "build_index.py --if-stale", "documenter", "indexer", "le binôme",
        "corrections", "verify.sh --at HEAD", "`done` dans l'ordre"],
}
ROUTEUR = ["security-code-review", "security-orchestrator", "build_index.py --if-stale", "documenter", "indexer", "critic-opus",
           "correction", "verify.sh", "done"]  # AGENTS.md § Golden rules, « Pipeline mandatory » : lu, jamais recopié à l'aveugle
PERMUTATIONS = tuple((n, a, b) for n, lettres in LETTRES.items()  # TOUTES les transpositions : 10 + 21
                     for a, b in itertools.combinations(lettres, 2))


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).replace(APOS, "'")
    return re.sub(r"\s+", " ", s.casefold()).strip()


def lire(root: Path = ROOT) -> dict[str, str]:
    return {k: (root / v).read_text(encoding="utf-8") for k, v in {**FILES, **SURFACES}.items()}


REPRISE = (  # T-01M5G7RTQ9 lot G (S-01M5HH8QMC, S-01M5HPRHV3) : interdiction, hôtes couverts et non couverts, friction
    "jamais `--reprise` automatiquement", "un agent ne reprend jamais une tâche", "Claude Code",
    "les hooks du kit qui posent `AGENTS_HOOK_HOST` (Codex, Kimi, Copilot)",
    "Codex, Gemini et Kimi sans marqueur", "TTY + saisie", "friction",
    "franchissable en une commande", "faux négatif nommé",
    # T-01M5MWZ6TD lot E (S-01M5MCXYH5) : Copilot CLI marque le shell de l'agent ; faux positif du `!` nommé
    "Copilot CLI pose `COPILOT_AGENT_SESSION_ID` et `COPILOT_CLI` dans le shell de l'agent (mesuré, 1.0.96) :"
    " ce marqueur refuse la reprise",
    "faux positif nommé : `COPILOT_CLI` est hérité", "l'échappement `!` de Copilot CLI",
)
FAUX = (  # une couverture PRÉTENDUE au-delà de la borne mesurée : rouge, dans la section seule
    r"codex[^.]{0,40}\bcouvert", r"claude code(?: et|,) codex", r"tous les h[ôo]tes", r"partout",
    r"jamais franchissable", r"infranchissable",
)
ANCIENNE = (  # l'affirmation réfutée par mesure (Copilot CLI 1.0.96 marque le shell) : rouge si elle revient
    r"sans marqueur\s*:\s*codex,\s*gemini,\s*copilot", r"copilot\s+et\s+kimi\s+hors",
)
REVENDICATION_SITES = {
    "retro": (
        ".agents/skills/context-retro/SKILL.md", "## Ce que le régime change", "## Le partage du travail",
        ("`tasks.py start`", "rc 2 `REVENDICATION`", "saute cette tâche",
         "rapporte le refus au pilote", "`--sans-revendication` est refusé (rc 2)",
         "seule la `--reprise` du pilote, dans son terminal, transfère la tâche") + REPRISE,
    ),
    "planning": (
        ".agents/skills/planning/SKILL.md", "## Garde-fous — PRÉPARATION SEULEMENT", "## Le cadrage",
        ("`tasks.py start`", "`tasks.py fournee`", "rc 2 `REVENDICATION`",
         "saute la tâche concernée", "rapporte le refus au pilote",
         "`--sans-revendication` est refusé (rc 2)",
         "seule la `--reprise` du pilote, dans son terminal, transfère la tâche",
         "`/planning` reste en préparation") + REPRISE,
    ),
}


def lire_revendication(root: Path = ROOT) -> dict[str, str]:
    return {nom: (root / path).read_text(encoding="utf-8") for nom, (path, *_r) in REVENDICATION_SITES.items()}


def revendication_verdict(root: Path = ROOT, textes: dict[str, str] | None = None) -> list[str]:
    textes = lire_revendication(root) if textes is None else textes
    bad = []
    for nom, (_path, debut, fin, jetons) in REVENDICATION_SITES.items():
        texte = textes[nom]
        section = norm(texte.partition(debut)[2].partition(fin)[0]) if debut in texte else ""
        bad.extend(f"{nom}: jeton absent ({jeton})" for jeton in jetons if norm(jeton) not in section)
        bad.extend(f"{nom}: couverture prétendue ({r})" for r in FAUX if re.search(r, section))
        bad.extend(f"{nom}: ancienne affirmation ({r})" for r in ANCIENNE if re.search(r, section))
    return bad


def paragraphe(skill: str) -> str | None:
    for bloc in re.split(r"\n\s*\n", skill):
        if "le mode worktree" in norm(bloc)[:60]:
            return bloc
    return None


def pipeline(agents: str) -> str | None:
    for ligne in agents.splitlines():
        if "pipeline mandatory" in ligne.casefold():
            return ligne
    return None


def ancres(texte: str, etiquettes) -> list[tuple[str, int, int]]:
    """Ancres SÉQUENTIELLES : la première « (e) » APRÈS la précédente ; s'arrête au premier manque."""
    out, pos = [], 0
    for e in etiquettes:
        m = re.compile(rf"\({re.escape(str(e))}\)").search(texte, pos)
        if not m:
            break
        out.append((str(e), m.start(), m.end()))
        pos = m.end()
    return out


def point(par: str, n: int) -> str | None:
    a = ancres(par, range(1, n + 2))
    if len(a) < n:
        return None
    return par[a[n - 1][2]: a[n][1]] if len(a) > n else par[a[n - 1][2]:]


def clauses(p: str, lettres: str) -> dict[str, tuple[int, int]]:
    a = ancres(p, lettres)
    return {e: (s, a[i + 1][1] if i + 1 < len(a) else len(p)) for i, (e, s, _) in enumerate(a)}


def en_ordre(texte: str, jetons: list[str]) -> bool:
    t, pos = norm(texte), -1
    for j in jetons:
        i = t.find(norm(j), pos + 1)
        if i < 0:
            return False
        pos = i
    return True


def verdict(textes: dict[str, str]) -> list[str]:
    bad = []
    for nom, regs in ABSENT.items():
        t = norm(textes[nom])
        bad += [f"{nom}: ancienne règle présente ({r})" for r in regs if re.search(r, t)]
    for nom in SURFACES:
        t = norm(textes[nom])
        bad += [f"{nom}: ancienne règle présente ({r})" for r in ABSENT_SURFACES if re.search(r, t)]
    for nom, jetons in PRESENT.items():
        t = norm(textes[nom])
        bad += [f"{nom}: jeton absent ({j})" for j in jetons if norm(j) not in t]
    pl = pipeline(textes["agents"])
    if pl is None:
        bad.append("agents: la ligne « Pipeline mandatory » est introuvable (ordre du routeur)")
    elif not en_ordre(pl, ROUTEUR):
        bad.append(f"agents: l'ordre du routeur {' < '.join(ROUTEUR)} n'est plus tenu — remettre d'accord AGENTS.md § Golden rules, ROUTEUR du filet et le point 5 de la skill")
    par = paragraphe(textes["skill"])
    if par is None:
        return bad + ["skill: paragraphe LE MODE WORKTREE absent"]
    for n, jetons in POINTS.items():
        pn = norm(point(par, n) or "")
        bad += [f"skill §worktree ({n}): jeton absent ({j})" for j in jetons if norm(j) not in pn]
    ts = norm(textes["skill"])
    bad += [f"skill: jeton absent ({j})" for j in SKILL_AILLEURS if norm(j) not in ts]
    if point(par, 8) is None:
        bad.append("skill §worktree: les huit points (1)..(8) ne sont pas tous là")
    for n, lettres in LETTRES.items():
        if len(clauses(point(par, n) or "", lettres)) != len(lettres):
            bad.append(f"skill §worktree ({n}): clauses lettrées incomplètes, attendu {lettres}")
    for n, jetons in ORDRE.items():
        if not en_ordre(point(par, n) or "", jetons):
            bad.append(f"skill §worktree ({n}): l'ordre {' < '.join(jetons)} n'est pas tenu")
    if not en_ordre(point(par, 5) or "", ROUTEUR):
        bad.append(f"skill §worktree (5): l'ordre du routeur {' < '.join(ROUTEUR)} n'est pas tenu — remettre d'accord AGENTS.md § Golden rules, ROUTEUR du filet et le point 5 de la skill")
    return bad


def retire(raw: str, jeton: str) -> str:
    """TOUTES les occurrences dans la portée donnée, casse ignorée : un jeton répété ne masque pas son mutant."""
    rx = r"\s+".join(re.escape(w) for w in jeton.split())
    return re.sub(rx, "", raw, flags=re.IGNORECASE)


def permute(par: str, n: int, a: str, b: str) -> str:
    """Échange les clauses (a) et (b) du point n, jetons INTACTS : seul l'ordre change."""
    p = point(par, n)
    i = par.index(p)
    c = clauses(p, LETTRES[n])
    (sa, ea), (sb, eb) = sorted((c[a], c[b]))
    q = p[:sa] + p[sb:eb] + p[ea:sb] + p[sa:ea] + p[eb:]
    return par[:i] + q + par[i + len(p):]


REFORMULATIONS = (  # l'ancienne règle PARAPHRASÉE, injectée dans le fichier : chaque ligne doit rougir
    ("agents", "Un seul dev à la fois."), ("agents", "Au plus un dev `running`, jamais deux."),
    ("skill", "Only one `running` task at a time."), ("skill", "At most one `running` task, unless declared."),
    ("kickoff_skill", "No more than one task is `running`."), ("kickoff_skill", "Only one dev runs at a time."),
    ("kickoff_cmd", "Only one dev runs at a time."), ("kickoff_cmd", "At most one `running` task."),
    ("copilot", "(only one `running` task at a time)"), ("copilot", "At most one task is running."),
)
SENS = (  # (fichier, ancre comptée UNE fois, remplacement, attendu) : des RETRAITS de jeton à remplacement inversé, sauf la ligne
    # DIRECTE<->EMPRUNTÉE, vraie inversion à mots constants, rouge par la CONTIGUÏTÉ des deux jetons de POINTS[8]
    ("agents", "dès que leurs write-sets DÉCLARÉS sont PROUVÉS disjoints", "", "jeton absent"),
    ("agents", "qui refuse notamment un recouvrement de write-set", "qui n'accepte qu'un recouvrement de write-set", "jeton absent"),
    ("agents", "un refus = SÉRIALISER ou compléter la déclaration", "un refus = passer outre", "jeton absent"),
    ("skill", "jamais en vol ni membre de `parallel`", "toujours en vol et membre de `parallel`", "jeton absent"),
    ("skill", "ne se juge que sur la trace EMPRUNTÉE au slot (parapluie), et une trace DIRECTE (forme générale) n'expire JAMAIS",
     "ne se juge que sur la trace DIRECTE (forme générale), et une trace EMPRUNTÉE au slot (parapluie) n'expire JAMAIS", "jeton absent"),
    ("skill", "sinon branche REFUSÉE (base fausse)", "sinon branche ACCEPTÉE (base fausse)", "jeton absent"),
    ("skill", "REFUS, jamais un passage", "passage admis", "jeton absent"),
    ("skill", "sinon branche REFUSÉE ; un diff VIDE est REFUSÉ", "sinon signalée ; un diff VIDE est admis", "jeton absent"),
    ("skill", "sinon branche REFUSÉE (livraison partielle)", "sinon branche ACCEPTÉE (livraison partielle)", "jeton absent"),
    ("skill", "ne refuse JAMAIS", "refuse toujours", "jeton absent"),
    ("skill", "n'appelle jamais `tasks.py`", "appelle `tasks.py`", "jeton absent"),
    ("skill", "jamais `-A`", "avec `-A`", "jeton absent"),
    ("skill", "l'orchestrateur en est seul écrivain", "l'orchestrateur en est écrivain parmi d'autres", "jeton absent"),
    ("skill", "se tient PAR FOURNÉE (S-00003502)", "se tient PAR TÂCHE, jamais PAR FOURNÉE (S-00003502)", "jeton absent"),
    ("skill", "AUCUNE fusion pendant qu'il tourne — le sha", "AUCUNE fusion pendant qu'il tourne n'est requise — le sha", "jeton absent"),
    ("skill", "avant tout `done`, pour CHACUN des deux", "avant tout `done`, pour UN des deux", "jeton absent"),
    ("skill", "sinon un binôme bis de fournée", "sinon on passe", "jeton absent"),
    ("skill", "ne la fait PAS attendre", "la fait attendre", "jeton absent"),
    ("skill", "n'expire JAMAIS", "expire à 24 h", "jeton absent"),
    ("skill", "la machine ne prouve ni", "la machine prouve", "jeton absent"),
    ("skill", "aucune garde ne refuse une branche qui déborde", "la garde du done refuse une branche qui déborde", "jeton absent"),
    ("skill", "Cycle de vie : c'est l'ORCHESTRATEUR qui retire les worktrees", "Cycle de vie : le dev retire ses worktrees", "jeton absent"),
    ("agents", "→ `documenter` → `indexer` if structure changed", "→ `indexer` if structure changed → `documenter`", "routeur"),
)


class DoctrineSurLesFichiersTests(unittest.TestCase):
    def test_les_fichiers_portent_la_doctrine(self):
        self.assertEqual(verdict(lire()), [])

    def test_claim_refusal_in_retro_and_planning(self):
        self.assertEqual(revendication_verdict(), [])


class RevendicationMutantsTests(unittest.TestCase):
    """Chaque jeton retiré de SA section, chaque hôte retiré de la liste sans marqueur, chaque couverture prétendue : rouge."""

    @classmethod
    def setUpClass(cls):
        cls.t = lire_revendication()

    def section(self, nom: str) -> str:
        _path, debut, fin, _j = REVENDICATION_SITES[nom]
        return self.t[nom].partition(debut)[2].partition(fin)[0]

    def rouge(self, nom: str, sec_mute: str, attendu: str):
        sec = self.section(nom)
        self.assertNotEqual(sec_mute, sec, "le mutant doit différer de l'original")
        mute = self.t[nom].replace(sec, sec_mute, 1)
        bad = revendication_verdict(textes={**self.t, nom: mute})
        self.assertTrue(any(b.startswith(nom) and attendu in b for b in bad), bad)

    def test_un_mutant_par_jeton(self):
        for nom, (_p, _d, _f, jetons) in REVENDICATION_SITES.items():
            for j in jetons:
                with self.subTest(fichier=nom, jeton=j):
                    self.rouge(nom, retire(self.section(nom), j), "jeton absent")

    def test_un_hote_retire_de_la_liste_sans_marqueur(self):
        liste = "Codex, Gemini et Kimi"
        for nom in REVENDICATION_SITES:
            sec = self.section(nom)
            ancre = re.search(r"\s+".join(re.escape(w) for w in liste.split()), sec)
            self.assertIsNotNone(ancre, nom)
            for hote in ("Codex", "Gemini", "Kimi"):
                reste = " et ".join(h for h in ("Codex", "Gemini", "Kimi") if h != hote)
                with self.subTest(fichier=nom, hote=hote):
                    self.rouge(nom, sec[:ancre.start()] + reste + sec[ancre.end():], "jeton absent")

    def test_ancienne_affirmation_copilot_sans_marqueur_remise(self):
        """L'ancienne phrase (Copilot sans marqueur) remise À CÔTÉ de la neuve : rouge, sous ses deux coupes."""
        for nom in REVENDICATION_SITES:
            for phrase in ("sans marqueur : Codex, Gemini, Copilot et Kimi hors de ces hooks.",
                           "sans marqueur : Codex,\nGemini, Copilot et Kimi hors\nde ces hooks."):
                with self.subTest(fichier=nom, phrase=phrase):
                    self.rouge(nom, self.section(nom) + "\n" + phrase + "\n", "ancienne affirmation")

    def test_codex_pretendu_couvert(self):
        for nom in REVENDICATION_SITES:
            for phrase in ("Codex est couvert par le marqueur d'agent.",
                           "Sous Claude Code et Codex, le marqueur d'agent refuse la reprise.",
                           "Le marqueur d'agent refuse la reprise sur tous les hôtes.",
                           "Le contrôle TTY + saisie est infranchissable."):
                with self.subTest(fichier=nom, phrase=phrase):
                    self.rouge(nom, self.section(nom) + "\n" + phrase + "\n", "couverture prétendue")


class MutantsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t = lire()

    def rouge(self, nom: str, mute: str, attendu: str):
        self.assertNotEqual(mute, self.t[nom], "le mutant doit différer de l'original")
        bad = verdict({**self.t, nom: mute})
        self.assertTrue(any(attendu in b and b.startswith(nom) for b in bad), bad)

    def test_ancienne_regle_remise_sous_quatre_formes(self):
        anciens = {"agents": "**Au plus UNE tâche `running`**", "skill": "At most one `running` task, UNLESS",
                   "kickoff_skill": "at most one task is `running`", "kickoff_cmd": "At most one task is `running`",
                   "copilot": "at most one `running` unless"}
        for nom, phrase in anciens.items():
            for forme in (phrase, phrase.upper(), phrase.replace(" ", NBSP), phrase.replace(" ", "\n", 2)):
                with self.subTest(fichier=nom, forme=forme):
                    self.rouge(nom, self.t[nom] + "\n" + forme + "\n", "ancienne règle")

    def test_ancienne_regle_remise_sur_les_surfaces_qui_voyagent(self):
        anciens = {  # la phrase EXACTE retirée de chaque surface (base d97733b5), remise telle quelle
            "surf_readme": "with at most one `running` — several only inside a parallel group `tasks.py parallel`",
            "surf_codebase_indexing": "at most one `running` — several only inside a declared parallel group",
            "surf_index": "at most one `running` task — several only inside a parallel group `parallel`",
            "surf_indexer_claude": "**At most one `running` task.**", "surf_indexer_gemini": "**At most one `running` task.**",
            "surf_indexer_kimi": "**At most one `running` task.**",
            "surf_indexer_copilot": "with at most one `running`, or several inside a declared parallel group",
        }
        self.assertEqual(set(anciens), set(SURFACES), "une phrase ancienne par surface, ni plus ni moins")
        for nom, phrase in anciens.items():
            for forme in (phrase, phrase.upper(), phrase.replace(" ", NBSP), phrase.replace(" ", "\n", 2)):
                with self.subTest(fichier=nom, forme=forme):
                    self.rouge(nom, self.t[nom] + "\n" + forme + "\n", "ancienne règle")

    def test_ancienne_regle_reformulee(self):
        for nom, phrase in REFORMULATIONS:
            with self.subTest(fichier=nom, phrase=phrase):
                self.rouge(nom, self.t[nom] + "\n" + phrase + "\n", "ancienne règle")

    def test_un_mutant_par_jeton_porteur(self):
        for nom, jetons in PRESENT.items():
            for j in jetons:
                with self.subTest(fichier=nom, jeton=j):
                    self.rouge(nom, retire(self.t[nom], j), "jeton absent")
        par = paragraphe(self.t["skill"])
        for n, jetons in POINTS.items():
            pn = point(par, n)
            for j in jetons:
                with self.subTest(fichier="skill", point=n, jeton=j):
                    self.rouge("skill", self.t["skill"].replace(pn, retire(pn, j)), "jeton absent")
        for j in SKILL_AILLEURS:
            with self.subTest(fichier="skill", jeton=j):
                self.rouge("skill", retire(self.t["skill"], j), "jeton absent")

    def test_le_mutant_de_sens_garde_les_jetons_voisins(self):
        for nom, ancre, remplace, attendu in SENS:
            with self.subTest(fichier=nom, ancre=ancre):
                self.assertEqual(self.t[nom].count(ancre), 1, "l'ancre doit exister UNE fois")
                self.rouge(nom, self.t[nom].replace(ancre, remplace), attendu)

    def test_le_mutant_d_ordre_jetons_intacts(self):
        par = paragraphe(self.t["skill"])
        for n, a, b in PERMUTATIONS:
            mute = permute(par, n, a, b)
            self.assertEqual(sorted(norm(mute).split()), sorted(norm(par).split()), "mêmes mots, autre ordre")
            with self.subTest(point=n, permutation=(a, b)):
                self.rouge("skill", self.t["skill"].replace(par, mute), "l'ordre")

    def test_fichiers_vides_global_seulement(self):
        for nom in FILES:
            self.assertTrue(verdict({**self.t, nom: ""}), nom)


if __name__ == "__main__":
    unittest.main()
