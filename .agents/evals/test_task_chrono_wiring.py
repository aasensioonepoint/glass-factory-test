"""Témoin du lot B : la chronologie voyage dans kickoff et la fournée.

CHRONO_WIRING_ROOT permet de rejouer ce témoin sur une copie mutante sous TMPDIR.
"""

import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

import pytest


ROOT = Path(os.environ.get("CHRONO_WIRING_ROOT", Path(__file__).resolve().parents[2]))
KIT_ROOT = Path(__file__).resolve().parents[2]
SKILL = ".agents/skills/kickoff/SKILL.md"
BOARD = ".agents/skills/task-board/SKILL.md"
CMD = ".claude/commands/kickoff.md"
GUARDRAILS = ".agents/skills/guardrails/SKILL.md"
WORKFLOW = ".claude/workflows/workflow-fournee.js"


def source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def moteur():
    """Le moteur `task_chrono.py` de ROOT : sa liste fermée ETAPES est la source des noms."""
    nom = "_banc_wiring_task_chrono"
    spec = importlib.util.spec_from_file_location(nom, ROOT / ".agents" / "bin" / "task_chrono.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module
    spec.loader.exec_module(module)
    return module


def entre(texte: str, debut: str, fin: str) -> str:
    return texte.split(debut, 1)[1].split(fin, 1)[0]


@pytest.mark.parametrize("chemin", (SKILL, CMD))
def test_kickoff_estime_et_affiche_chaque_etape(chemin: str) -> None:
    texte = source(chemin)
    passage = entre(texte, "**CHRONO DE LA TÂCHE" if chemin == SKILL else "**Chrono,", "Pour un dev")
    assert "chrono T-NNN begin" in texte
    assert "chrono T-NNN estimate --etape <étape>" in texte
    assert "chrono T-NNN step --etape <étape> --phase begin" in texte
    assert "chrono T-NNN step --etape <étape> --phase end" in texte
    assert "chrono T-NNN show" in texte
    assert "Un rc non nul" in texte and "ne bloque jamais" in texte
    assert "après identification ou création" in passage
    assert "attente-pilote --phase begin" in passage and "sans `estimate`" in passage
    for etape in moteur().ETAPES:  # la correspondance nomme CHAQUE étape de la liste fermée, telle quelle
        assert f"`{etape}`" in passage, (chemin, etape)
    assert "`tasks.py done` abouti pose le jalon `done`" in passage
    assert "clôt le cycle" in passage


@pytest.mark.parametrize("chemin", (SKILL, CMD))
def test_kickoff_reprend_sans_second_debut(chemin: str) -> None:
    texte = source(chemin)
    assert "/planning" in texte and "/planning-all" in texte
    assert "sans second début" in texte
    assert "`tasks.py start` et `tasks.py fournee` ouvrent ou reprennent le cycle" in texte


@pytest.mark.parametrize("chemin", (SKILL, CMD))
def test_devs_hors_workflow_ne_doublent_pas_les_jalons(chemin: str) -> None:
    texte = source(chemin)
    passage = entre(texte, "HORS `", "Dans le workflow" if chemin == CMD else "Le journal")
    for commande in (
        "chrono <lot> estimate --etape dev", "chrono <lot> step --etape dev --phase end",
        "chrono <lot> show",
        "chrono <lot> estimate --etape fusion", "chrono <lot> step --etape fusion --phase end",
    ):
        assert commande in passage, (chemin, commande)
    assert "chrono <lot> step --etape dev --phase begin" not in passage
    assert "chrono <lot> step --etape fusion --phase begin" not in passage
    assert "`retour` abouti ouvre la fusion" in passage
    assert "au retour de l'agent, même en échec" in passage
    assert "`retour` ne termine qu'un dev resté ouvert" in passage


@pytest.mark.parametrize("chemin", (SKILL, CMD, BOARD))
def test_w10_jalons_tasks_et_attente_de_place(chemin: str) -> None:
    texte = source(chemin)
    assert "`tasks.py start` et `tasks.py fournee` ouvrent ou reprennent" in texte
    assert "et le dev de chaque lot, ou de la tâche sans lot" in texte
    borne = ("l'attente d'une place de charge y est comptée" if chemin == BOARD else
             "le dev ouvert par `fournee` compte aussi l'attente d'une place de charge")
    assert borne in texte
    assert "`tasks.py retour` abouti termine" in texte
    assert "et ouvre la fusion" in texte
    assert "le lanceur termine la fusion" not in texte and "le lanceur la termine" not in texte
    assert "`retour`, `review-scope` et `done` aboutis ferment la fusion à l'heure du commit" in texte
    assert "une fin du lanceur posée avant l'emporte" in texte
    assert "`tasks.py review-scope` abouti relève `juges`" in texte
    assert "le `done` complète `cloture`, `correction` et `porte`" in texte
    assert "`juges` est une fenêtre, jamais une mesure d'exec-critic" in texte
    assert "une porte commune d'une fournée" in texte and "compte pour chacune" in texte
    assert "ni porte ni correction, avis" in texte
    assert "`tasks.py done` abouti pose le jalon" in texte
    assert "un lot n'a pas son propre jalon done" in texte
    assert "`done` dit sur stderr `CHRONO: avis …` (cycle absent, étapes sans fin), sans jamais refuser" in texte
    assert "dans un cycle clos, `show` borne toute étape restée sans fin à la fin du jalon done" in texte
    assert "statut « incomplète », sans écrire de fin" in texte
    assert "planner et plan-critic" in texte.lower()
    assert "Le suffixe `⏱` suit l'id de la tâche focale, AVANT le détail de stage" in texte
    if chemin in (SKILL, CMD):
        assert "Le lanceur ne double pas les jalons déjà posés par `tasks.py`" in texte


def test_w11_copilot_statusline_depuis_racine_et_hors_kit(tmp_path: Path) -> None:
    texte = source(GUARDRAILS)
    commande = re.search(r"la commande est `([^`]+)`", texte)
    assert commande is not None
    attendu_commande = (
        'if [ "$(pwd -P)" = "/chemin/absolu/du/depot" ] && [ -f .agents/pyrun.sh ]; '
        'then bash .agents/pyrun.sh .agents/bin/tasks.py --statusline; fi'
    )
    assert "Une ligne d'état configurée au niveau utilisateur s'exécute dans tout dépôt ouvert" in texte
    assert "Le suffixe `⏱` suit l'id de la tâche focale, AVANT le détail de stage" in texte
    commande_kit = commande.group(1).replace("/chemin/absolu/du/depot", str(KIT_ROOT.resolve()))
    depuis_kit = subprocess.run(["/bin/sh", "-c", commande_kit], cwd=KIT_ROOT,
                                capture_output=True, text=True, check=False, timeout=30)
    attendu = subprocess.run(["bash", ".agents/pyrun.sh", ".agents/bin/tasks.py", "--root",
                             str(KIT_ROOT), "--statusline"], cwd=KIT_ROOT,
                            capture_output=True, text=True, check=False, timeout=30)
    n = re.compile(r" · ⏱ [a-z-]+ \S+(?: \+[1-9])?")
    assert (depuis_kit.returncode, n.sub("", depuis_kit.stdout), depuis_kit.stderr) == (
        attendu.returncode, n.sub("", attendu.stdout), attendu.stderr)
    script_etranger = tmp_path / ".agents" / "pyrun.sh"
    script_etranger.parent.mkdir()
    script_etranger.write_text("printf 'SCRIPT_NON_FIABLE\\n'\n", encoding="utf-8")
    hors_kit = subprocess.run(["/bin/sh", "-c", commande_kit], cwd=tmp_path,
                              capture_output=True, text=True, check=False, timeout=30)
    assert (hors_kit.returncode, hors_kit.stdout, hors_kit.stderr) == (0, "", "")
    assert commande.group(1) == attendu_commande


@pytest.mark.parametrize("nom,chemin,avant,apres,temoin", (
    ("M3 fusion", BOARD, "et ouvre la fusion", "et ferme la fusion", "w10"),
    ("M4 dev", BOARD, "et le dev de chaque lot, ou de la tâche sans lot", "mais jamais le dev de chaque lot, ou de la tâche sans lot", "w10"),
    ("M5 done", BOARD, "un lot n'a pas son propre jalon done", "chaque lot pose son propre jalon done", "w10"),
    ("M6 double", CMD, "Le lanceur ne double pas les jalons", "Le lanceur rejoue aussi les jalons", "w10"),
    ("M7 suffixe", GUARDRAILS, "AVANT le détail de stage", "APRÈS le détail de stage", "w11"),
    ("M8 avis done", BOARD, "`CHRONO: avis …`", "`CHRONO: refus …`", "w10"),
    ("M9 borne show", BOARD, "`show` borne toute étape restée sans fin", "`show` laisse toute étape restée sans fin", "w10"),
    ("M10 fin dev", CMD, "chrono <lot> step --etape dev --phase end", "chrono <lot> step --etape dev --phase begin", "dev"),
    ("M11 racine fiable", GUARDRAILS, '[ "$(pwd -P)" = "/chemin/absolu/du/depot" ] && ', "", "w11"),
    ("M12 suffixe commande", CMD, "AVANT le détail de stage", "APRÈS le détail de stage", "w10"),
    ("M13 retour du dev", SKILL, "`retour` ne termine qu'un dev resté ouvert", "`retour` termine chaque dev", "dev"),
    ("M14 fin non écrite", BOARD, "statut « incomplète », sans écrire de fin", "statut « finie », avec une fin écrite", "w10"),
    ("A6 juges", SKILL, "`tasks.py review-scope` abouti relève `juges`", "le lanceur relève `juges`", "w10"),
    ("A6 queue du done", BOARD, "le `done` complète `cloture`, `correction` et `porte`", "le lanceur complète `cloture`, `correction` et `porte`", "w10"),
    ("A6 fin de fusion", CMD, "ferment la fusion à l'heure du commit", "laissent la fusion au lanceur", "w10"),
    ("A6 porte commune", SKILL, "une porte commune d'une fournée", "une porte d'une fournée", "w10"),
))
def test_mutant_phrase_rougit(
    nom: str, chemin: str, avant: str, apres: str, temoin: str,
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Chaque phrase normative ajoutée fait rougir son témoin, sans édition du dépôt."""
    original = source
    texte_original = original(chemin)
    assert avant in texte_original, (nom, avant)
    texte_mutant = texte_original.replace(avant, apres, 1)

    def source_mutante(path: str) -> str:
        if path == chemin:
            return texte_mutant
        return original(path)

    monkeypatch.setattr(sys.modules[__name__], "source", source_mutante)
    with pytest.raises(AssertionError) as erreur:
        if temoin == "w10":
            test_w10_jalons_tasks_et_attente_de_place(chemin)
        elif temoin == "w11":
            test_w11_copilot_statusline_depuis_racine_et_hors_kit(tmp_path)
        else:
            test_devs_hors_workflow_ne_doublent_pas_les_jalons(chemin)
    print(f"{nom}: rouge {type(erreur.value).__name__}: {erreur.value}")


def test_commande_garde_la_ligne_179_et_la_borne() -> None:
    lignes = source(CMD).splitlines()
    assert lignes[178] == "   Record the FINAL verdict: `python .agents/bin/specs.py add --task T-NNN"
    texte = " ".join(source(CMD).split())
    assert "specs.py add --kind delta" in texte
    assert "bounded in the CHANGELOG" not in texte


def test_contrat_voyageur_distingue_journal_et_board() -> None:
    texte = source(BOARD)
    passage = entre(texte, "**Durées de pipeline", "**PROPRIÉTÉ DES TÂCHES")
    for attendu in (
        "chrono <T> begin", "chrono <T> estimate --etape <nom>", "chrono <T> step",
        "chrono <T> show", "racine commune locale", "rc non nul", "jamais bloquant",
        "sans additionner les durées de lots parallèles",
    ):
        assert attendu in passage, attendu


def prompts_workflow() -> dict[str, str]:
    """Évalue les vraies fonctions de rendu du workflow, sans lancer d'agent."""
    js = source(WORKFLOW)
    dev = js[js.index("function promptDev("):js.index("function promptFusion(")]
    fusion = js[js.index("function promptFusion("):js.index("// FILE PAR VAGUES")]
    script = "\n".join((
        "const A = {label:'F',base:'abcdef0',session:null,borne:null};",
        "const RACINE = '/tmp/repo';",
        "const bancsDe = () => 'aucun | témoin';",
        "const piedSession = () => '';",
        "const ECONOMIE = '';",
        dev, fusion,
        "const g = {id:'T-123',taches:['T-123'],branche:'wt/T-123',agentType:'dev-multi',writeset:['a.py'],consigne:'faire',tests:null};",
        "process.stdout.write(JSON.stringify({dev:promptDev(g),fusion:promptFusion(g,{head:'abcdef0'})}));",
    ))
    node = shutil.which("node")
    assert node is not None, "node absent : rendu du Workflow impossible à vérifier"
    rendu = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=10, check=False)
    assert rendu.returncode == 0, rendu.stderr
    return json.loads(rendu.stdout)


def test_workflow_dev_encadre_sa_tentative() -> None:
    dev = prompts_workflow()["dev"]
    for commande in (
        "chrono T-123 begin", "chrono T-123 estimate --etape dev",
        "chrono T-123 step --etape dev --phase begin",
        "chrono T-123 step --etape dev --phase end", "chrono T-123 show",
    ):
        assert commande in dev, commande
    assert "rc non nul" in dev and "jamais bloquant" in dev


def test_workflow_fusion_autorise_chrono_et_encadre_refus() -> None:
    fusion = prompts_workflow()["fusion"]
    for commande in (
        "chrono T-123 estimate --etape fusion", "chrono T-123 step --etape fusion --phase begin",
        "chrono T-123 step --etape fusion --phase end", "chrono T-123 show",
    ):
        assert commande in fusion, commande
    assert "même si l'un refuse ou échoue" in fusion
    assert "toute écriture au journal SAUF `tasks.py chrono`" in fusion
    assert "rc non nul" in fusion and "sans bloquer la fusion" in fusion


def test_workflow_appelle_tasks_par_pyrun() -> None:
    """F3 de la clôture : `python` manque souvent (pyrun.sh l'écrit) ; les mandats dev et fusion passent par
    `bash .agents/pyrun.sh`. MUTANT qui le rougit : un appel `python .agents/bin/tasks.py chrono` remis."""
    prompts = prompts_workflow()
    for role in ("dev", "fusion"):
        assert "python .agents/bin/tasks.py" not in prompts[role], role
        assert "`bash .agents/pyrun.sh .agents/bin/tasks.py chrono T-123 " in prompts[role], role


# LE TROU QUI A LAISSÉ PASSER TROIS BLOQUANTS : les témoins ci-dessus ne lisaient que des chaînes. Celui-ci
# EXTRAIT chaque commande chrono des surfaces câblées et l'EXÉCUTE contre la vraie CLI de ROOT.
CITATION = re.compile(
    r"`(?:(?:python|bash \.agents/pyrun\.sh) \.agents/bin/tasks\.py )?(chrono [^`]+|step --etape [^`]+)`")
ORDRE_ACTION = {"begin": 0, "estimate": 1, "step-begin": 2, "step-end": 3, "show": 4}
LISTE_BLANCHE = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "SYSTEMROOT", "WINDIR", "PATHEXT")


ACTIONS = ("begin", "estimate", "step", "show")
# Plus long d'abord : `T-NNN` remplacé avant `T-NNNNNNNN` laisserait `<id>NNNNN`.
MARQUEURS_TACHE = (("T-NNNNNNNN", "parent"), ("T-NNN", "parent"), ("<T>", "parent"), ("<lot>", "lot"),
                   ("T-123", "lot"))


def surfaces_citantes() -> list[str]:
    """Les surfaces de doctrine lues = celles où la MÊME expression trouve une citation, jamais une liste à la main.

    `git grep` sur ROOT (un rejeu sur copie mutante exige donc un clone git) : chaque `.md` suivi, et le workflow
    dont on rend les prompts. L'expression est CITATION elle-même, groupes non capturants rendus en ERE.
    """
    motif = CITATION.pattern.replace("(?:", "(")
    # docs/tasks/ porte des PLANS : ils citent des étapes qui n'existent pas encore, jamais de la doctrine.
    r = subprocess.run(["git", "-C", str(ROOT), "grep", "-lE", motif, "--", "*.md", WORKFLOW, ":!docs/tasks/"],
                       capture_output=True, text=True, encoding="utf-8", timeout=60, check=False)
    assert r.returncode in (0, 1), f"git grep rc {r.returncode} : {r.stderr}"
    return sorted(r.stdout.split())


def citations() -> dict[str, list[str]]:
    textes = {}
    for chemin in surfaces_citantes():
        if chemin == WORKFLOW:
            rendus = prompts_workflow()
            textes.update({"workflow:dev": rendus["dev"], "workflow:fusion": rendus["fusion"]})
        else:
            textes[chemin] = source(chemin)
    assert "workflow:dev" in textes, f"{WORKFLOW} absent des surfaces citantes : {sorted(textes)}"
    return {nom: CITATION.findall(texte) for nom, texte in textes.items()}


def concretiser(gabarit: str, parent: str, lot: str, etapes: tuple[str, ...]) -> list[list[str]]:
    """Un gabarit cité → les argv concrets ; un marqueur inconnu rougit, jamais ignoré.

    Une mention sans tâche (`chrono show`, `step --etape …`) se joue sur le parent, comme une commande.
    """
    texte = gabarit if gabarit.startswith("chrono ") else "chrono T-NNN " + gabarit
    mots = texte.split()
    if len(mots) >= 2 and mots[1] in ACTIONS:
        texte = " ".join(["chrono", "T-NNN", *mots[1:]])
    valeurs = {"parent": parent, "lot": lot}
    for marque, role in sorted(MARQUEURS_TACHE, key=lambda m: -len(m[0])):
        texte = texte.replace(marque, valeurs[role])
    formes = [texte]
    for marque, valeurs in (("<étape>", etapes), ("<nom>", etapes), ("begin|end", ("begin", "end"))):
        formes = [f.replace(marque, v) for f in formes for v in valeurs] if marque in texte else formes
    for f in formes:
        assert not re.search(r"[<>|…]", f), f"marqueur non résolu dans {gabarit!r} : {f!r}"
        assert len(f.split()) >= 3, f"commande sans tâche ou sans action : {gabarit!r}"
    return [f.split() for f in formes]


def cle(argv: list[str]) -> int:
    action = argv[2]
    if action == "step":
        action += "-" + argv[argv.index("--phase") + 1]
    return ORDRE_ACTION[action]


def test_chaque_commande_chrono_citee_passe_la_vraie_cli() -> None:
    etapes = tuple(moteur().ETAPES)
    par_surface = citations()
    for nom, gabarits in par_surface.items():
        assert gabarits, f"{nom} : aucune commande chrono extraite"
    base = Path(tempfile.mkdtemp(prefix="chrono-wiring-")).resolve()
    try:
        maison = base / "maison"
        maison.mkdir()
        env = {k: os.environ[k] for k in LISTE_BLANCHE if k in os.environ}
        env.update(HOME=str(maison), USERPROFILE=str(maison), XDG_CONFIG_HOME=str(maison / "xdg"),
                   GIT_CONFIG_NOSYSTEM="1", GIT_CEILING_DIRECTORIES=str(base), CADRE_STATE_DIR=str(base / "etat"),
                   AGENTS_EVENTS_DIR=str(base / "evenements"), PYTHONDONTWRITEBYTECODE="1",
                   PYTHONIOENCODING="utf-8")
        racine = base / "r"
        racine.mkdir()
        tasks_py = ROOT / ".agents" / "bin" / "tasks.py"

        def cli(*argv: str, **extra: str) -> subprocess.CompletedProcess:
            return subprocess.run([sys.executable, "-B", str(tasks_py), "--root", str(racine), *argv],
                                  cwd=str(racine), env=dict(env, **extra), capture_output=True, text=True,
                                  encoding="utf-8", timeout=120, check=False)

        ids = []
        for titre in ("parent", "lot"):
            r = cli("new", titre, "--pas-un-defaut", "banc", CADRE_PROJECT_ROOT=str(racine))
            assert r.returncode == 0, r.stderr
            ids.append(next(m for m in r.stdout.split() if m.startswith("T-")))
        parent, lot = ids
        board = racine / ".agents" / "state" / "board" / "TASKS.json"
        donnees = json.loads(board.read_text(encoding="utf-8"))
        next(t for t in donnees["tasks"] if t["id"] == lot)["fournee"] = {"parent": parent, "lot": "A"}
        board.write_text(json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8")
        concrets = {tuple(a) for g in sum(par_surface.values(), []) for a in concretiser(g, parent, lot, etapes)}
        jouees = {a[a.index("--etape") + 1] for a in concrets if a[2] == "step" and "--etape" in a}
        assert jouees == set(etapes), f"étapes jamais jouées par une surface : {set(etapes) - jouees}"
        echecs = []
        for argv in sorted(concrets, key=lambda a: (cle(list(a)), a)):
            r = cli(*argv)
            if r.returncode != 0:
                echecs.append((" ".join(argv), r.returncode, r.stderr.strip()))
        assert not echecs, echecs
        show = cli("chrono", parent, "show", "--json")
        assert json.loads(show.stdout)["clos"] is True, show.stdout
    finally:
        shutil.rmtree(base, ignore_errors=True)
