"""Contrat du régime ATTERRISSAGE — câblage, cadrage, et bornes DITES (T-00000534).

POURQUOI CE FICHIER EXISTE. `context-retro.test.sh` mesure le COMPORTEMENT des
trois jambes sur charge synthétique. Il ne peut rien dire du CÂBLAGE : un hook
parfait qui n'est enregistré nulle part ne s'exécute jamais, et le banc bash
resterait vert. C'est le défaut que `test_semgrep_hook_registration.py` existe
pour attraper sur un autre hook, et le modèle suivi ici est le sien : les faits
sont liés SUR LA MÊME ENTRÉE de settings.json, jamais constatés séparément.

Ce fichier asserte aussi que les BORNES sont écrites. Un mécanisme qui ne
garantit pas ce qu'il a l'air de garantir est pire que pas de mécanisme, et
celui-ci en a trois : la statusline ne tourne pas en headless, le seuil est un
nombre du pilote, et le filet ne voit que `Bash`.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SETTINGS = ROOT / ".claude" / "settings.json"
HOOK = ROOT / ".claude" / "hooks" / "context-retro.sh"
BENCH = ROOT / ".claude" / "hooks" / "context-retro.test.sh"
SKILL = ROOT / ".agents" / "skills" / "context-retro" / "SKILL.md"
STATUSLINE = ROOT / ".claude" / "statusline.sh"

HOOK_REF = ".claude/hooks/context-retro.sh"

# Périmètre du témoin palier2 (T-00001113) : extrait du test pour être éprouvé par FiltrePalier2Tests.
BACKLOG_P2 = "docs/interne/chantier/backlog/"
TASKS_P2 = "docs/tasks/"
LOTS_P2 = "docs/interne/chantier/lots/"
DESIGN_P2 = "docs/design/"
PROSE_P2 = (BACKLOG_P2, TASKS_P2, LOTS_P2, DESIGN_P2)
EXCLUS_P2 = (".agents/state/", "runs/", "docs/tasks/critiques/")
# .js/.mjs/.cjs/.ts (T-00001165) : un script de workflow se lance par son chemin, sans shebang.
SCRIPTS_P2 = (".py", ".pyw", ".sh", ".bash", ".zsh", ".ksh", ".js", ".mjs", ".cjs", ".ts")


def _chemins_z(sortie: str) -> list[str]:
    """Les chemins d'une sortie `git … -z` : séparés par NUL, jamais par un saut de ligne."""
    return [f for f in sortie.split("\0") if f]


def _surface_balayee(f: str, racine: Path = ROOT) -> bool:
    """Vrai si le chemin suivi `f` reste au périmètre du témoin palier2.

    EXCLUS_P2 sort en entier. Sous une racine de prose (PROSE_P2), restent balayés tout tools/
    (toute casse), tout suffixe de SCRIPTS_P2 (toute casse) et tout fichier qui ouvre
    par #! ; le reste de la prose sort. Partout ailleurs, tout est balayé."""
    if f.startswith(EXCLUS_P2):
        return False
    prose = next((p for p in PROSE_P2 if f.startswith(p)), None)
    if prose is None:
        return True
    reste = f[len(prose):].casefold()
    if reste.startswith("tools/") or reste.endswith(SCRIPTS_P2):
        return True
    try:
        with open(racine / f, "rb") as h:
            return h.read(2) == b"#!"
    except OSError:
        return True  # illisible : balayé, jamais exclu en silence


def consommateurs_palier2(racine: Path = ROOT) -> list[str]:
    """Les chemins suivis qui citent le marqueur et restent au périmètre, triés. Décodage UTF-8 en
    `surrogateescape` : un nom non UTF-8 traverse sans lever, et `open` le ré-encode à l'identique."""
    sortie = subprocess.run(
        ["git", "-c", "core.quotePath=false", "grep", "-l", "-z", "palier2"],
        cwd=racine, encoding="utf-8", errors="surrogateescape", capture_output=True,
    ).stdout
    return sorted(f for f in _chemins_z(sortie) if _surface_balayee(f, racine))


def entries_for(event: str) -> list[dict]:
    data = json.loads(SETTINGS.read_text(encoding="utf-8"))
    return [
        e
        for e in data.get("hooks", {}).get(event, [])
        if any(HOOK_REF in h.get("command", "") for h in e.get("hooks", []))
    ]


class RegistrationTests(unittest.TestCase):
    """Le câblage — mesuré sur settings.json, pas supposé."""

    def test_the_three_legs_are_registered_on_their_three_events(self) -> None:
        for event in ("PostToolUse", "PreToolUse", "Stop"):
            self.assertEqual(
                len(entries_for(event)),
                1,
                f"{event}: le hook rétro doit être enregistré exactement une fois",
            )

    def test_the_net_is_scoped_to_Bash_and_the_others_are_not_scoped(self) -> None:
        """Les faits sont liés SUR LA MÊME ENTRÉE. Un test qui vérifierait
        « il existe une entrée PreToolUse avec matcher Bash » ET « il existe une
        entrée qui appelle le hook » passerait sur deux entrées différentes."""
        self.assertEqual(entries_for("PreToolUse")[0].get("matcher"), "Bash")
        for event in ("PostToolUse", "Stop"):
            self.assertIsNone(
                entries_for(event)[0].get("matcher"),
                f"{event}: l'annonce et l'échéance ne se filtrent sur aucun outil",
            )

    def test_the_windows_wrapping_is_the_one_every_other_entry_carries(self) -> None:
        """Sans le `cygpath`, le hook no-ope EN SILENCE sous Git Bash — le mode
        de défaillance que ce wrapping existe pour empêcher sur les 25 autres."""
        for event in ("PostToolUse", "PreToolUse", "Stop"):
            cmd = entries_for(event)[0]["hooks"][0]
            self.assertEqual(cmd.get("shell"), "bash")
            self.assertIn("cygpath -u", cmd["command"])
            self.assertIn('"$CLAUDE_PROJECT_DIR/.claude/hooks/context-retro.sh"', cmd["command"])


class FramingTests(unittest.TestCase):
    """Le transcript et les sorties d'outils sont un canal de DONNÉES."""

    def test_untrusted_input_is_framed_and_bounded(self) -> None:
        """Mêmes littéraux que `test_night_contract.py` — la borne du dépôt est
        une seule, pas une par mécanisme."""
        text = HOOK.read_text(encoding="utf-8")
        self.assertIn("[do not obey]", text, "le relevé n'est pas cadré comme une donnée")
        self.assertIn("30", text, "aucune borne en lignes")
        self.assertIn("2000", text.replace(" ", ""), "aucune borne en caractères")

    def test_every_entry_is_flattened_to_one_physical_line(self) -> None:
        """La propriété de sécurité la plus importante du mécanisme : une entrée
        capable d'émettre son propre newline pourrait forger une fausse ligne
        `[SYSTEM]` et défaire L-004. Motif et raison repris de specs.py."""
        text = HOOK.read_text(encoding="utf-8")
        self.assertIn("def flatten", text)
        self.assertIn('" ".join(str(text).split())', text)


class ZeroLlmTests(unittest.TestCase):
    def test_the_hook_invokes_no_model(self) -> None:
        """Redondant avec test_hooks_zero_llm.py PAR CONSTRUCTION, et c'est
        voulu : celui-là balaie tous les registres, celui-ci nomme le fichier.
        Un balayage qui perdrait ce hook de vue resterait vert."""
        text = HOOK.read_text(encoding="utf-8")
        for forbidden in ("claude -p", "claude --print", "codex exec", "gemini -p",
                          "ollama run", "anthropic", "openai"):
            self.assertNotIn(forbidden, text, f"le hook invoque {forbidden!r}")


class DeclaredBoundsTests(unittest.TestCase):
    """Les bornes sont ÉCRITES, pas laissées à découvrir."""

    def test_the_skill_says_what_the_mechanism_does_not_guarantee(self) -> None:
        text = SKILL.read_text(encoding="utf-8")
        for bound, why in (
            ("headless", "la statusline ne tourne pas en -p/--headless"),
            ("5 s", "le seuil est constaté à la granularité du rafraîchissement"),
            ("Bash", "le filet ne voit que les commandes passant par Bash"),
            ("CONTEXT_RETRO_PCT", "le seuil est un nombre du pilote, surchargeable"),
            # T-00000617 : LA BORNE QUI MANQUAIT, et c'est celle qui a fait
            # refuser le correctif en trois lignes. La skill VOYAGE chez les
            # adoptants et disait que consolider pouvait « refermer ta propre
            # sortie », quand la docstring d'`ecart_capitalisation()` tranche
            # « CE N'EST PAS UN GEL » — deux surfaces voyageant ensemble et se
            # contredisant sur un point ARBITRÉ. La règle du dépôt vise
            # exactement ça : une doc qui affirme une garantie que le code ne
            # tient pas empêche de voir le défaut.
            ("elle ne se REFERME pas",
             "le sas n'est PAS un gel : `compte_lecons()` n'a aucun plafond, donc "
             "toute croissance suffisante le rouvre — mesuré par fixture"),
            ("UNE SEULE ÉCRITURE NE SUFFIT PAS TOUJOURS",
             "consolidate plafonne à 50 et purge existe : un compteur peut "
             "redescendre, et le refus chiffre alors ce qu'il reste"),
        ):
            self.assertIn(bound, text, f"borne non déclarée : {why}")

    def test_the_hook_and_the_skill_agree_that_the_sas_is_not_a_freeze(self) -> None:
        """LES DEUX SURFACES VOYAGENT ENSEMBLE — elles ne peuvent pas diverger.

        La skill part chez l'adoptant ; le hook, lui, est le seul à PARLER au
        moment du refus. Que l'une dise « une leçon de plus suffit » pendant que
        l'autre chiffre un écart est le défaut que `T-00000617` a nommé, et le
        relevé d'origine en avait trouvé QUATRE sites — dont un dans `PLAN-ETAT`,
        corrigé à part. Ce test pince les deux qui restent, par leur AFFIRMATION
        et non par leur tournure.
        """
        hook = HOOK.read_text(encoding="utf-8")
        skill = SKILL.read_text(encoding="utf-8")

        # LA MOITIÉ POSITIVE PORTE SUR LES PHRASES CORRIGÉES, PAS SUR UN MOT.
        # Première rédaction : `assertIn("CROISSANCE", text.upper())`. Mesurée
        # contre `git show HEAD:` par les DEUX critiques de clôture — le mot
        # `croissance` existait déjà 11 fois dans le hook (`croissance = {}`,
        # docstrings) et 1 fois dans la skill, donc l'assertion était VERTE SUR
        # L'ARBRE DÉFECTUEUX. Un témoin qui ne peut pas échouer est décoratif, et
        # celui-ci survivait au mutant qui remettait la formulation au singulier.
        for surface, aiguille, text in (
            ("le hook (jambe A)", "CROISSANCE de L'UNE des deux routes", hook),
            ("le hook (jambe C)", "CROISSANCE de L'UNE des deux routes", hook),
            ("la skill", "CROISSANCE de L'UNE des deux routes", skill),
        ):
            self.assertIn(
                aiguille, text,
                f"{surface} ne dit plus que la mesure porte sur la CROISSANCE de "
                f"L'UNE des deux routes — « une leçon de plus » se lit comme un "
                f"geste à poser, et « des deux stores » sur-estime ce que le "
                f"mécanisme exige (`a_capitalise()` libère sur la PREMIÈRE route "
                f"qui grossit)",
            )

        # LE CONTRÔLE NÉGATIF, ÉLARGI AUX AFFIRMATIONS ET PLUS SEULEMENT À UNE
        # TOURNURE. Le relevé d'origine avait cherché la formulation « l'un des
        # deux suffit » et manqué la borne 8, qui disait la MÊME chose autrement
        # — seize lignes plus bas dans le fichier que le lot corrigeait. Chercher
        # la tournure et non l'affirmation est la faute que ce test existe pour
        # ne pas répéter.
        for surface, text in (("le hook", hook), ("la skill", skill)):
            for interdit in (
                "une leçon ou une divergence de plus est",
                "Une seule leçon ouvre le sas",
                "creuse suffit**",
                "CROISSANCE des deux stores",
            ):
                self.assertNotIn(
                    interdit, text,
                    f"{surface} : {interdit!r} est revenu — cette affirmation fait "
                    f"relire le sas comme un gel, ou sur-estime ce qu'il exige",
                )

    def test_the_skill_declares_its_host_scope_like_night(self) -> None:
        text = SKILL.read_text(encoding="utf-8")
        self.assertIn("COVERAGE DEGRADED", text)
        for host in ("Codex", "Copilot", "Gemini", "Kimi"):
            self.assertIn(host, text, f"{host} n'est pas nommé dans la contrainte d'hôte")

    def test_the_statusline_sensor_stays_eval_free(self) -> None:
        """T-00000490 : la statusline a déjà payé un `eval` sur des valeurs
        interpolées crues. Le capteur ne le rouvre pas."""
        text = STATUSLINE.read_text(encoding="utf-8")
        self.assertIn("CONTEXT_RETRO_PCT", text, "le capteur n'est pas dans la statusline")
        # Mesuré sur les lignes EXÉCUTABLES : le mot `eval` est partout dans les
        # commentaires de ce fichier, qui racontent précisément pourquoi il n'y
        # en a plus. Une recherche en sous-chaîne mesurerait la prose.
        code = [
            l for l in text.splitlines()
            if l.strip() and not l.lstrip().startswith("#")
        ]
        offending = [l for l in code if re.search(r"(^|[;&|(\s])eval\s", l)]
        self.assertEqual(
            offending, [], f"un eval est réapparu dans une ligne exécutable : {offending}"
        )


class SensorThresholdTests(unittest.TestCase):
    """LE CAPTEUR LUI-MÊME N'AVAIT AUCUN TÉMOIN. Le banc bash pose `.armed` à la
    main ; la statusline — la seule surface qui CONNAÎT le seuil — n'était
    exercée nulle part. Le seuil est passé de 80 à 90 le 2026-09-13 et rien
    n'aurait rougi s'il était resté à 80 dans l'une des DEUX déclarations du
    défaut (shell ligne 29, python ligne 70) : le défaut divergent a vécu jusqu'à
    ce que le binôme le mesure."""

    def _arme(self, pct: int, env: dict[str, str]) -> bool:
        import os
        import subprocess
        import tempfile

        with tempfile.TemporaryDirectory() as root:
            payload = json.dumps(
                {"session_id": "x", "context_window": {"used_percentage": pct}}
            )
            # L'environnement AMBIANT ne doit pas décider du seuil : un pilote qui
            # a réglé CONTEXT_RETRO_PCT dans ses settings (mesuré le 2026-09-29,
            # valeur 50) faisait rougir « arme à 90, pas à 85 ». Seule la
            # surcharge que le test passe dans `env` compte.
            propre = {k: v for k, v in os.environ.items() if k != "CONTEXT_RETRO_PCT"}
            subprocess.run(
                ["bash", str(STATUSLINE)],
                input=payload, text=True, capture_output=True,
                env={**propre, **env, "CLAUDE_PROJECT_DIR": root},
            )
            marqueurs = Path(root, ".agents/state/local/context-retro")
            return bool(list(marqueurs.glob("*.armed"))) if marqueurs.exists() else False

    def test_the_sensor_arms_at_90_and_not_at_85(self) -> None:
        self.assertFalse(self._arme(85, {}), "armé sous le seuil : 85 < 90")
        self.assertTrue(self._arme(90, {}), "n'arme pas AU seuil — 90 est inclusif")

    def test_the_pilot_override_still_wins(self) -> None:
        """Le seuil reste un nombre du pilote : la surcharge prime sur le défaut."""
        self.assertTrue(self._arme(85, {"CONTEXT_RETRO_PCT": "80"}))

    def test_a_non_numeric_override_falls_back_instead_of_disarming(self) -> None:
        """UN DÉSARMEMENT SILENCIEUX MESURÉ le 2026-09-13 : une valeur non
        numérique levait `ValueError`, avalée par le `except` qui protège
        l'écriture — le régime le plus critique du dépôt était désarmé par une
        faute de frappe, sans un octet de trace. Elle retombe sur le défaut."""
        self.assertTrue(self._arme(95, {"CONTEXT_RETRO_PCT": "quatre-vingt-dix"}))
        self.assertFalse(self._arme(85, {"CONTEXT_RETRO_PCT": " "}))


class SasTests(unittest.TestCase):
    """LE GEL EST UN SAS, PAS UN MUR (T-00000587, demande pilote du 2026-09-13).

    Avant ce lot, `.armed` gelait l'agenda pour le RESTE de la session et rien ne
    le retirait : le message du hook renvoyait le lecteur à un `rm` du pilote, et
    la skill écrivait « le régime tient jusqu'à la fin de la session ». Le défaut
    de fond était ailleurs, et plus grave : `.retro-done` ne prouve PAS que la
    rétro a eu lieu — `claim()` le pose quand elle est RÉCLAMÉE. Rien, nulle
    part, ne mesurait la capitalisation.

    Ces témoins exercent le hook RÉEL sur un arbre jetable. Ils ne lisent pas la
    prose du script : un banc qui `assertIn` un commentaire resterait vert le
    jour où le code cesse de faire ce que le commentaire annonce.
    """

    CMD = "python3 .agents/bin/tasks.py start T-00000999"

    def _hook(self, root: Path, cmd: str) -> int:
        import os
        import subprocess

        payload = json.dumps({
            "hook_event_name": "PreToolUse",
            "session_id": "sas-temoin",
            "tool_input": {"command": cmd},
        })
        p = subprocess.run(
            ["bash", str(ROOT / ".claude" / "hooks" / "context-retro.sh")],
            input=payload, text=True, capture_output=True,
            env={**os.environ, "CLAUDE_PROJECT_DIR": str(root)},
        )
        return p.returncode

    def _marks(self, root: Path) -> Path:
        import hashlib

        cle = "s-" + hashlib.sha256(b"sas-temoin").hexdigest()[:16]
        d = root / ".agents" / "state" / "local" / "context-retro"
        d.mkdir(parents=True, exist_ok=True)
        return d / cle

    def _arme(
        self,
        root: Path,
        lecons: int = 0,
        baseline: dict | None = None,
        reclamee: bool = True,
        journal: bool = True,
    ) -> Path:
        """Un arbre jetable ARMÉ, agenda gelé sur une tâche qui n'est pas la
        cible.

        `reclamee` pose `.retro-done`. Il est VRAI par défaut parce que c'est
        l'état normal au moment où le filet refuse : la rétro est réclamée en fin
        de tour, et le sas ne compte que ce qui vient après elle."""
        m = self._marks(root)
        m.with_suffix(".armed").write_text(json.dumps({"pct": 91}), encoding="utf-8")
        m.with_suffix(".agenda").write_text(json.dumps(["T-012"]), encoding="utf-8")
        if reclamee:
            m.with_suffix(".retro-done").touch()
        if journal:
            j = root / "retro" / "LESSONS.md"
            j.parent.mkdir(parents=True, exist_ok=True)
            j.write_text(
                "## Journal\n" + "".join(
                    f"- 2026-09-13 [AUTRE] [portée:locale] l{i} (source: verdict)\n"
                    for i in range(lecons)
                ),
                encoding="utf-8",
            )
        if baseline is not None:
            m.with_suffix(".baseline").write_text(json.dumps(baseline), encoding="utf-8")
        return m

    def _board(self, root: Path, titres: list[str]) -> None:
        """Un VRAI board, écrit par `tasks.py` lui-même.

        Le premier jet de ces témoins simulait la croissance du board avec une
        ligne de base à `-1`, et le binôme a montré que ça passait avec
        `board_json() ≡ []` : AUCUN témoin ne prouvait que le board est lu.
        Celui-ci le prouve, au prix d'un sous-processus."""
        import subprocess
        import sys as _sys

        for t in titres:
            subprocess.run(
                [_sys.executable, str(ROOT / ".agents" / "bin" / "tasks.py"),
                 "--root", str(root), "new", t],
                check=True, capture_output=True,
            )

    def test_armed_and_nothing_capitalised_still_refuses(self) -> None:
        """Le régime n'est pas désarmé par ce lot : sans capitalisation, il
        refuse exactement comme avant."""
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._arme(root, lecons=2, baseline={"lecons": 2, "taches": 0})
            self.assertEqual(self._hook(root, self.CMD), 2)

    def test_one_more_lesson_opens_the_sas(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            m = self._arme(root, lecons=3, baseline={"lecons": 2, "taches": 0})
            self.assertEqual(self._hook(root, self.CMD), 0, "une leçon de plus doit libérer")
            self.assertTrue(m.with_suffix(".libere").exists(), "la libération n'est pas tracée")
            preuve = json.loads(m.with_suffix(".libere").read_text(encoding="utf-8"))
            self.assertEqual(preuve["lecons"], [2, 3], "la preuve n'est pas consignée")

    def test_a_REAL_task_on_a_REAL_board_opens_the_sas(self) -> None:
        """L'autre destination du protocole : une DIVERGENCE va au board. Écrite
        par `tasks.py`, pas simulée par une ligne de base négative."""
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._arme(root, lecons=2, baseline={"lecons": 2, "taches": 0})
            self._board(root, ["une divergence capitalisée"])
            self.assertEqual(self._hook(root, self.CMD), 0)

    def test_a_baseline_taken_on_an_UNREADABLE_board_does_not_open_the_sas(self) -> None:
        """LE FILET SERAIT LA SEULE GARDE FAIL-OPEN DU FICHIER, et dans le
        mauvais sens. `board_json()` rend `[]` aussi bien sur un board vide que
        sur un timeout ou un board corrompu (mesuré : `rc=2`, stdout vide). Une
        ligne de base prise PENDANT un incident vaudrait donc 0, et la première
        lecture réussie deviendrait une « croissance » de 0 à N — libération sans
        qu'une seule leçon ait été écrite.

        LE SCÉNARIO DOIT PRENDRE LA LIGNE DE BASE SUR LE BOARD CASSÉ : le
        premier jet de ce témoin cassait le board APRÈS coup, et la mutation
        `compte_taches()` → `len(board_json())` passait au travers. Un témoin qui
        passe pour une mauvaise raison est pire que pas de témoin."""
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            m = self._arme(root, lecons=2, baseline=None)
            board = root / ".agents" / "state" / "board" / "TASKS.json"
            board.parent.mkdir(parents=True, exist_ok=True)
            board.write_text("{ceci n'est pas du json", encoding="utf-8")
            # 1. la ligne de base est prise ICI, board illisible
            self.assertEqual(self._hook(root, self.CMD), 2)
            base = json.loads(m.with_suffix(".baseline").read_text(encoding="utf-8"))
            # LA CLÉ EST ABSENTE, PAS FIGÉE À `None` : la figer tuerait la route
            # board pour TOUTE la session, alors que le refus en promet le
            # remède. Elle sera remplie au prochain passage, au compte COURANT,
            # donc sans créer de croissance.
            self.assertNotIn("taches", base, "un board illisible a été compté, ou figé")
            # 2. le board redevient lisible et porte de VRAIES tâches
            board.unlink()
            self._board(root, ["une tache", "une autre"])
            # 3. ce n'est PAS une capitalisation : rien n'a été écrit par la rétro
            self.assertEqual(
                self._hook(root, self.CMD), 2,
                "une lecture réparée s'est fait compter comme une croissance",
            )

    def test_a_ROUTINE_ticket_before_the_retro_claim_does_NOT_open(self) -> None:
        """LA RÉGRESSION QUE LE BINÔME A TROUVÉE, et le cœur de la demande
        pilote — « gelé le temps que retro FINISSE la capitalisation ».
        `tasks.py new` reste OUVERT sous le régime, donc c'est aussi le geste le
        moins cher qui fasse grossir un store. Sans cette garde, un ticket de
        travail courant écrit avant que la rétro soit seulement réclamée ouvrait
        le sas, et la compaction tombait sur un chantier neuf."""
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._arme(root, lecons=2, baseline={"lecons": 2, "taches": 0},
                       reclamee=False)
            self._board(root, ["un ticket de travail courant"])
            self.assertEqual(self._hook(root, self.CMD), 2)

    def test_a_journal_that_does_not_exist_yet_counts_as_zero(self) -> None:
        """`retro.py add` crée le journal à la première écriture. Traiter
        l'absence comme « illisible » (`None`) ferait que la PREMIÈRE leçon d'un
        dépôt adoptant — `None → 1`, donc pas deux entiers — n'ouvrirait jamais
        le sas. Le cas de tout adoptant neuf."""
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            m = self._arme(root, baseline=None, journal=False)
            self.assertEqual(self._hook(root, self.CMD), 2)  # pose la ligne de base
            base = json.loads(m.with_suffix(".baseline").read_text(encoding="utf-8"))
            self.assertEqual(base["lecons"], 0, "journal absent ≠ journal illisible")
            j = root / "retro" / "LESSONS.md"
            j.parent.mkdir(parents=True, exist_ok=True)
            j.write_text(
                "## Journal\n- 2026-09-13 [AUTRE] [portée:locale] première (source: verdict)\n",
                encoding="utf-8",
            )
            self.assertEqual(self._hook(root, self.CMD), 0)

    def test_the_release_is_irreversible_within_the_session(self) -> None:
        """Sans cette propriété, une purge de `consolidate` — qui purge à 90
        jours ET évince au plafond de 50 — ferait REDESCENDRE un compte et
        RE-gèlerait un agenda déjà libéré. Une garde qui se referme seule après
        s'être ouverte est pire qu'une garde restée ouverte : personne ne la
        relierait à sa cause."""
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            m = self._arme(root, lecons=3, baseline={"lecons": 2, "taches": 0})
            self.assertEqual(self._hook(root, self.CMD), 0)
            # le journal REDESCEND sous la ligne de base
            (root / "retro" / "LESSONS.md").write_text("## Journal\n", encoding="utf-8")
            self.assertTrue(m.with_suffix(".libere").exists())
            self.assertEqual(self._hook(root, self.CMD), 0, "le sas s'est refermé tout seul")

    def test_a_missing_baseline_fails_CLOSED_then_lays_it(self) -> None:
        """La doctrine du fichier est fail-open PARTOUT SAUF sur le filet. Une
        ligne de base absente ne libère pas — et le RATTRAPAGE la pose au
        passage, sans quoi les sessions armées avant ce correctif resteraient
        gelées pour toujours (mesuré : 3 sur disque, 0 ligne de base) pendant
        que le refus leur promet une sortie."""
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            m = self._arme(root, lecons=5, baseline=None)
            self.assertEqual(self._hook(root, self.CMD), 2)
            self.assertTrue(m.with_suffix(".baseline").exists(), "pas de rattrapage")
            base = json.loads(m.with_suffix(".baseline").read_text(encoding="utf-8"))
            self.assertEqual(base["lecons"], 5, "le rattrapage part du compte COURANT")

    def test_a_corrupt_baseline_fails_CLOSED(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            m = self._arme(root, lecons=5, baseline=None)
            m.with_suffix(".baseline").write_text("{pas du json", encoding="utf-8")
            self.assertEqual(self._hook(root, self.CMD), 2)

    def test_the_negative_control_still_passes_frozen(self) -> None:
        """`tasks.py new` reste ouvert même gelé — c'est la moitié de la raison
        d'être de la rétro, et le sas ne doit pas l'avoir cassée."""
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._arme(root, lecons=2, baseline={"lecons": 2, "taches": 0})
            self.assertEqual(
                self._hook(root, 'python3 .agents/bin/tasks.py new "un ticket"'), 0
            )

    def test_the_deadline_leg_lays_the_baseline_at_the_CLAIM(self) -> None:
        """Et PAS à l'annonce. Entre les deux, l'agent finit sa tâche et peut
        écrire un ticket, geste que le régime laisse délibérément ouvert : une
        ligne de base prise à l'annonce ferait compter ce ticket de routine
        comme une preuve de capitalisation."""
        import os
        import subprocess
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            m = self._arme(root, lecons=4, baseline=None, reclamee=False)
            # l'ANNONCE ne doit RIEN poser
            for event in ("PostToolUse", "Stop"):
                subprocess.run(
                    ["bash", str(ROOT / ".claude" / "hooks" / "context-retro.sh")],
                    input=json.dumps({"hook_event_name": event, "session_id": "sas-temoin"}),
                    text=True, capture_output=True,
                    env={**os.environ, "CLAUDE_PROJECT_DIR": str(root)},
                )
                if event == "PostToolUse":
                    self.assertFalse(
                        m.with_suffix(".baseline").exists(),
                        "l'annonce pose une ligne de base : le sas comptera du travail courant",
                    )
            self.assertTrue(m.with_suffix(".retro-done").exists(), "la rétro n'est pas réclamée")
            base = json.loads(m.with_suffix(".baseline").read_text(encoding="utf-8"))
            self.assertEqual(base["lecons"], 4, "le journal n'est pas compté")
            self.assertIsInstance(base["taches"], int, "le board n'est pas compté")

    def test_the_deadline_leg_says_that_capitalising_lifts_the_freeze(self) -> None:
        """C'est le SEUL texte que l'agent lit PENDANT qu'il capitalise. S'il ne
        dit pas que ce qu'il écrit lève le gel, le mécanisme garde son secret au
        moment précis où il compte."""
        import os
        import subprocess
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._arme(root, lecons=2, baseline=None, reclamee=False)
            p = subprocess.run(
                ["bash", str(ROOT / ".claude" / "hooks" / "context-retro.sh")],
                input=json.dumps({"hook_event_name": "Stop", "session_id": "sas-temoin"}),
                text=True, capture_output=True,
                env={**os.environ, "CLAUDE_PROJECT_DIR": str(root)},
            )
            reason = json.loads(p.stdout)["reason"]
            self.assertIn("LÈVE LE GEL", reason)

    def test_the_refusal_names_the_remedy_the_agent_can_actually_run(self) -> None:
        """Un refus qui renvoie à un geste du PILOTE bloque l'agent sans lui
        donner de sortie — c'est exactement ce que ce lot répare."""
        import os
        import subprocess
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._arme(root, lecons=2, baseline={"lecons": 2, "taches": 0})
            p = subprocess.run(
                ["bash", str(ROOT / ".claude" / "hooks" / "context-retro.sh")],
                input=json.dumps({
                    "hook_event_name": "PreToolUse", "session_id": "sas-temoin",
                    "tool_input": {"command": self.CMD},
                }),
                text=True, capture_output=True,
                env={**os.environ, "CLAUDE_PROJECT_DIR": str(root)},
            )
            self.assertEqual(p.returncode, 2)
            self.assertIn("SAS", p.stderr)
            self.assertIn("retro.py add", p.stderr)

    def test_the_opening_is_SAID_not_merely_done(self) -> None:
        """« Le désarmement est TOUJOURS dit » — un sas qui s'ouvre en silence
        est un désarmement qu'on constate au lieu de le lire."""
        import os
        import subprocess
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._arme(root, lecons=3, baseline={"lecons": 2, "taches": 0})
            p = subprocess.run(
                ["bash", str(ROOT / ".claude" / "hooks" / "context-retro.sh")],
                input=json.dumps({
                    "hook_event_name": "PreToolUse", "session_id": "sas-temoin",
                    "tool_input": {"command": self.CMD},
                }),
                text=True, capture_output=True,
                env={**os.environ, "CLAUDE_PROJECT_DIR": str(root)},
            )
            self.assertEqual(p.returncode, 0)
            self.assertIn("SAS OUVERT", p.stderr)

    # LE FILET QUI NE PEUT PAS JUGER REFUSE (décision pilote S-01M5YZ6VJN,
    # S-01M5WG8ZJT). Avant, python absent ou planté rendait 0 : un `start` hors
    # agenda gelé passait sans avoir été lu. PostToolUse et Stop, eux, ne
    # refusent jamais — un Stop qui échoue fermé gèle l'hôte.

    def _outils_sans_python(self, d: Path) -> Path:
        """Un PATH de LIENS vers les seuls outils du hook, sans aucun python*.
        `/usr/bin/python3` existe sur macOS : un PATH `/usr/bin:/bin` brut ne
        retirerait pas python."""
        import os
        import shutil

        bindir = d / "bin-sans-python"
        bindir.mkdir()
        for outil in ("bash", "cat", "sed", "head", "cut", "sha256sum", "shasum",
                      "perl", "uname", "dirname"):
            vrai = shutil.which(outil)
            if vrai:
                os.symlink(vrai, bindir / outil)
        return bindir

    def _jambe(self, root: Path, path: str, event: str, cmd: str | None,
               session: bool = True, extra: dict | None = None):
        import os
        import shutil
        import subprocess

        charge: dict = {"hook_event_name": event}
        if session:
            charge["session_id"] = "sas-temoin"
        if cmd is not None:
            charge["tool_input"] = {"command": cmd}
        charge.update(extra or {})
        env = {k: v for k, v in os.environ.items() if k != "OS"}
        env.update({"CLAUDE_PROJECT_DIR": str(root), "PATH": path})
        return subprocess.run(
            [shutil.which("bash") or "/bin/bash", str(HOOK)],
            input=json.dumps(charge), text=True, capture_output=True, env=env,
        )

    def test_sans_python_le_filet_refuse(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            racine = Path(d)
            path = str(self._outils_sans_python(racine))
            # Contrôle C1 : session NON armée — la sortie rapide rend 0 AVANT
            # toute sonde python, même sur un `start`.
            vierge = racine / "vierge"
            vierge.mkdir()
            p = self._jambe(vierge, path, "PreToolUse", self.CMD)
            self.assertEqual(p.returncode, 0, f"non armée doit rendre 0 : {p.stderr}")
            self.assertNotIn("filet non lu", p.stderr)
            root = racine / "arme"
            root.mkdir()
            self._arme(root, lecons=2, baseline={"lecons": 2, "taches": 0})
            p = self._jambe(root, path, "PreToolUse", self.CMD)
            self.assertEqual(p.returncode, 2, f"armée, sans python, start : {p.stderr}")
            self.assertIn("aucun interpréteur python, filet non lu", p.stderr)
            self.assertIn("installer python 3 (python3, python ou py -3)", p.stderr)
            self.assertEqual(self._jambe(root, path, "PreToolUse", "ls -la").returncode, 0,
                             "une commande sans tasks.py start est refusée")
            for event in ("PostToolUse", "Stop"):
                p = self._jambe(root, path, event, self.CMD)
                self.assertEqual(p.returncode, 0, f"{event} refuse : gel de l'hôte")
            # Une charge PostToolUse dont le CONTENU porte la chaîne
            # "PreToolUse" (ici une valeur de tool_response) n'est pas un
            # PreToolUse : seule la clé `"hook_event_name":"PreToolUse"` compte.
            p = self._jambe(root, path, "PostToolUse", self.CMD,
                            extra={"tool_response": {"hook": "PreToolUse"}})
            self.assertEqual(p.returncode, 0,
                             f"PostToolUse jugé sur son contenu « PreToolUse » : {p.stderr}")

    def test_un_filet_qui_plante_refuse(self) -> None:
        import os
        import sys as _sys
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            racine = Path(d)
            bindir = racine / "bin-qui-plante"
            bindir.mkdir()
            # Un python qui passe les sondes (`-c`) mais plante sur le filet
            # (`-`, le heredoc) : rc 1, comme une trace python.
            faux = bindir / "python3"
            faux.write_text(
                "#!/bin/sh\n"
                f'[ "$1" = "-c" ] && exec "{_sys.executable}" "$@"\n'
                'echo "Traceback: plantage simulé" >&2\n'
                "exit 1\n",
                encoding="utf-8",
            )
            faux.chmod(0o755)
            path = f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}"
            root = racine / "arme"
            root.mkdir()
            self._arme(root, lecons=2, baseline={"lecons": 2, "taches": 0})
            p = self._jambe(root, path, "PreToolUse", self.CMD)
            self.assertEqual(p.returncode, 2, f"un filet planté laisse passer : {p.stderr}")
            self.assertIn("erreur interne du filet (rc=1)", p.stderr)
            self.assertIn("installer python 3 (python3, python ou py -3)", p.stderr)
            # La VALEUR de `command` est jugée, pas la charge brute.
            self.assertEqual(self._jambe(root, path, "PreToolUse", "ls -la").returncode, 0)
            p = self._jambe(root, path, "PreToolUse", None)
            self.assertEqual(p.returncode, 0, "charge sans command refusée")
            # Le départage VALEUR / CHARGE BRUTE : la charge brute nomme
            # `tasks.py start` (dans la description), la valeur de `command`
            # non. Juger la charge brute, ou ne jamais réussir l'extraction,
            # refuserait ici.
            p = self._jambe(root, path, "PreToolUse", None, extra={"tool_input": {
                "command": "ls -la", "description": "avant tasks.py start T-1"}})
            self.assertEqual(p.returncode, 0,
                             f"la charge brute est jugée au lieu de la valeur : {p.stderr}")
            for event in ("PostToolUse", "Stop"):
                p = self._jambe(root, path, event, self.CMD)
                self.assertEqual(p.returncode, 0, f"{event} refuse : gel de l'hôte")

    def test_extraction_en_echec_juge_la_charge_brute(self) -> None:
        """Python plante sur le filet ET sur la relecture de `command` : le
        repli juge la charge BRUTE, comme sans python, et refuse un start."""
        import os
        import sys as _sys
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            racine = Path(d)
            bindir = racine / "bin-tout-plante"
            bindir.mkdir()
            # Les sondes (`-c 'import sys; …'`) passent ; la relecture
            # (`-c 'import json, …'`) et le filet (`-`) plantent.
            faux = bindir / "python3"
            faux.write_text(
                "#!/bin/sh\n"
                'case "$2" in "import json"*) exit 1 ;; esac\n'
                f'[ "$1" = "-c" ] && exec "{_sys.executable}" "$@"\n'
                'echo "Traceback: plantage simulé" >&2\n'
                "exit 1\n",
                encoding="utf-8",
            )
            faux.chmod(0o755)
            path = f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}"
            root = racine / "arme"
            root.mkdir()
            self._arme(root, lecons=2, baseline={"lecons": 2, "taches": 0})
            p = self._jambe(root, path, "PreToolUse", self.CMD)
            self.assertEqual(p.returncode, 2, f"extraction en échec laisse passer : {p.stderr}")
            self.assertIn("charge illisible", p.stderr)
            self.assertEqual(self._jambe(root, path, "PreToolUse", "ls -la").returncode, 0)
            p = self._jambe(root, path, "PostToolUse", self.CMD)
            self.assertEqual(p.returncode, 0, f"PostToolUse refuse : {p.stderr}")


class NuitVivanteTests(SasTests):
    """UNE NUIT `/night` VIVANTE TAIT LA JAMBE B, ET ELLE SEULE (T-00000581).

    LE DÉFAUT. `/night` dépile un lot APPROUVÉ sans surveillance, donc il
    consomme du contexte et finit par franchir le seuil du régime
    d'atterrissage. La jambe B refusait alors tout `tasks.py start` hors agenda
    gelé — elle fermait l'agenda AU MILIEU DE LA NUIT, tuant précisément ce que
    `/night` existe pour faire. Le seuil porté de 80 à 90 % atténuait la
    FRÉQUENCE du gel ; il ne touchait pas la cause.

    LE SIGNAL EXISTE DÉJÀ et n'est pas déclaratif : `/night` écrit
    `.agents/state/local/night/keepawake.pid`. On le relit par `kill -0`, JAMAIS
    par la seule présence du fichier — un pid mort laisse le marqueur derrière
    lui et désarmerait le régime POUR TOUJOURS sur cette machine.
    """

    def _pose_nuit(self, root: Path, pid: int) -> None:
        d = root / ".agents" / "state" / "local" / "night"
        d.mkdir(parents=True, exist_ok=True)
        (d / "keepawake.pid").write_text(str(pid), encoding="utf-8")

    def _jambe_b(self, root: Path):
        import os
        import subprocess

        return subprocess.run(
            ["bash", str(ROOT / ".claude" / "hooks" / "context-retro.sh")],
            # `sas-temoin` et PAS autre chose : `_marks()` indexe les marqueurs
            # par `sha256(session_id)`, donc une session differente regarde un
            # regime NON arme et sort 0 sans rien prouver. Mes trois premiers
            # temoins sont tombes exactement la-dessus.
            input=json.dumps({
                "hook_event_name": "PreToolUse", "session_id": "sas-temoin",
                "tool_input": {"command": self.CMD},
            }),
            text=True, capture_output=True,
            env={**os.environ, "CLAUDE_PROJECT_DIR": str(root)},
        )

    def test_nuit_VIVANTE_laisse_passer_un_start_hors_agenda(self) -> None:
        """TÉMOIN 1. Le pid de CE processus est vivant par construction."""
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._arme(root, lecons=2, baseline={"lecons": 2, "taches": 0})
            self._pose_nuit(root, os.getpid())
            p = self._jambe_b(root)
            self.assertEqual(p.returncode, 0,
                             f"la nuit s'est fait fermer l'agenda : {p.stderr}")

    def test_un_pid_MORT_laisse_le_refus_revenir(self) -> None:
        """TÉMOIN 2, et c'est le CONTRÔLE NÉGATIF du précédent. Sans lui, la
        correction serait indistinguable d'un désarmement pur et simple du
        régime — le marqueur survit à la nuit qui l'a posé."""
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._arme(root, lecons=2, baseline={"lecons": 2, "taches": 0})
            # PID 2^31-1 : jamais attribué en pratique, et la branche
            # ProcessLookupError est celle qu'on veut éprouver.
            self._pose_nuit(root, 2147483647)
            p = self._jambe_b(root)
            self.assertEqual(p.returncode, 2, "un pid mort a désarmé le régime")
            self.assertIn("SAS", p.stderr)

    def test_un_marqueur_ILLISIBLE_ne_desarme_rien(self) -> None:
        """Fail-closed sur ce qu'on ne sait pas établir : un contenu non
        numérique n'est pas une nuit, c'est une absence de preuve."""
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._arme(root, lecons=2, baseline={"lecons": 2, "taches": 0})
            nd = root / ".agents" / "state" / "local" / "night"
            nd.mkdir(parents=True, exist_ok=True)
            (nd / "keepawake.pid").write_text("pas-un-pid\n", encoding="utf-8")
            self.assertEqual(self._jambe_b(root).returncode, 2)

    def test_l_ANNONCE_tombe_meme_en_nuit_vivante(self) -> None:
        """TÉMOIN 3. Ce qui ne se tait PAS, et c'est délibéré : une nuit non
        surveillée est justement le cas où la capitalisation avant compaction
        vaut le plus cher. Le pilote a dit que la COMPACTION était acceptable,
        jamais que la PERTE l'était."""
        import os
        import subprocess
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._arme(root, lecons=2, baseline={"lecons": 2, "taches": 0})
            self._pose_nuit(root, os.getpid())
            p = subprocess.run(
                ["bash", str(ROOT / ".claude" / "hooks" / "context-retro.sh")],
                input=json.dumps({
                    "hook_event_name": "PostToolUse", "session_id": "sas-temoin",
                    "tool_input": {"command": "echo ok"},
                }),
                text=True, capture_output=True,
                env={**os.environ, "CLAUDE_PROJECT_DIR": str(root)},
            )
            self.assertEqual(p.returncode, 0)
            self.assertNotEqual(
                p.stdout.strip(), "",
                "la jambe A s'est tue pendant la nuit — la capitalisation est perdue",
            )


class QuotedArgumentTests(unittest.TestCase):
    """UNE CHAÎNE CITÉE N'EST PAS UNE COMMANDE (T-00000579).

    MESURÉ TROIS FOIS LE 2026-09-13, et la troisième est la plus parlante : la
    garde a refusé un `tasks.py new` dont le TITRE citait la séquence littérale
    du verbe de démarrage — pour DÉCRIRE le défaut du régime. Elle a extrait le
    mot suivant comme identifiant de tâche et a bloqué. Le ticket ainsi refusé
    était celui qui réparait le régime. Une passe rétro qui documente ses propres
    blocages était donc structurellement empêchée, alors que `new` est justement
    le geste que ce régime déclare OUVERT.

    ET DEPUIS LE SAS, LE TORT A CHANGÉ DE NATURE. Avant, une extraction fautive
    produisait un refus bruyant et sans effet d'état. Depuis `T-00000587`, ce
    chemin peut ÉCRIRE une libération irréversible — donc CONSOMMER le sas, le
    refus disparaissant sans qu'aucune trace ne relie la cause à l'effet.

    Ces témoins exercent le hook RÉEL, gelé, avec `.retro-done` posé mais sans
    ligne de base : dans cet état un vrai démarrage hors agenda DOIT être refusé
    (rc 2) et tout le reste DOIT passer (rc 0). Le contraste est donc net et ne
    dépend d'aucune prose."""

    def _gele(self, root: Path):
        m = SasTests._marks(self, root)
        m.with_suffix(".armed").write_text(json.dumps({"pct": 91}), encoding="utf-8")
        m.with_suffix(".agenda").write_text(json.dumps(["T-012"]), encoding="utf-8")
        m.with_suffix(".retro-done").touch()
        return m

    def _rc(self, cmd: str) -> int:
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._gele(root)
            return SasTests._hook(self, root, cmd)

    def test_a_real_start_outside_the_agenda_is_still_refused(self) -> None:
        """LE CONTRÔLE QUI REND LES AUTRES NON VACUANTS. Sans lui, un filet
        cassé rendrait 0 partout et tous les cas ci-dessous seraient verts."""
        for cmd in (
            "python3 .agents/bin/tasks.py start T-00000999",
            'python3 .agents/bin/tasks.py start "T-00000999"',
            # Après un séparateur. Le `--root` a quitté ce cas : il désigne
            # désormais un AUTRE board et exempte légitimement — c'est le cas
            # `test_a_start_on_ANOTHER_board_is_not_a_new_chantier_here`, et son
            # contrôle de non-vacuité vérifie qu'un `--root` sur la racine
            # COURANTE refuse toujours.
            "cd /x && python3 .agents/bin/tasks.py start T-999",
        ):
            self.assertEqual(self._rc(cmd), 2, f"le filet a laissé passer : {cmd}")

    def test_the_MEASURED_false_positive_no_longer_refuses(self) -> None:
        """Le cas exact du 2026-09-13, verbatim dans sa forme."""
        self.assertEqual(
            self._rc('python3 .agents/bin/tasks.py new "refuse tasks.py start hors agenda"'),
            0,
        )

    def test_a_lesson_that_QUOTES_the_pattern_is_not_refused(self) -> None:
        """LA CIRCULARITÉ QUE CE LOT FERME : le refus du filet dit d'écrire une
        leçon avec `retro.py add`, et un `retro.py add` dont le texte citait le
        motif se faisait refuser par ce même filet. C'est précisément le cas qui
        se présente quand la rétro documente ses propres blocages."""
        self.assertEqual(
            self._rc("python3 .agents/bin/retro.py add --cause AUTRE "
                     "--text 'la garde lit tasks.py start comme une commande'"),
            0,
        )

    def test_quoting_forms_that_must_all_be_inert(self) -> None:
        for cmd in (
            'python3 .agents/bin/specs.py add "x" --text "tasks.py start T-9 refuse"',
            'python3 .agents/bin/tasks.py new "un titre \\" avec tasks.py start T-9"',
            'echo "tasks.py start T-9',  # guillemet JAMAIS refermé
        ):
            self.assertEqual(self._rc(cmd), 0, f"refusé à tort : {cmd}")

    def test_a_HEREDOC_body_is_data_too(self) -> None:
        """LA QUATRIÈME OCCURRENCE, ET C'EST CELLE QUI A COÛTÉ LE PLUS CHER À
        ADMETTRE : le message de commit qui livrait le correctif des guillemets
        a été refusé par la garde qu'il corrigeait, parce qu'il CITAIT un exemple
        de commande entre accents graves dans sa prose. Les accents graves ne
        sont pas des guillemets — mais le texte voyageait dans un heredoc, et un
        corps de heredoc est une DONNÉE que le shell transmet, jamais du shell
        qu'il exécute. C'est le canal par lequel passent tous les messages de
        commit de ce dépôt, donc de la prose qui cite volontiers des commandes."""
        for cmd in (
            "git commit -F - <<'EOF'\nborne : `VAR=1 python tasks.py start T-1`, mesuré\nEOF",
            "cat <<-FIN\n\tpython tasks.py start T-9\n\tFIN",
            "cat <<'EOF'\npython tasks.py start T-9",  # jamais refermé
        ):
            self.assertEqual(self._rc(cmd), 0, f"refusé à tort : {cmd!r}")

    def test_a_REAL_start_after_a_heredoc_is_still_seen(self) -> None:
        """LE CONTRÔLE DE NON-VACUITÉ DU CAS PRÉCÉDENT. Un retrait trop large
        avalerait la suite de la commande et rendrait le filet aveugle — une
        fuite serait pire que le faux positif qu'on vient de fermer."""
        self.assertEqual(
            self._rc("cat <<EOF\nun exemple : python tasks.py start T-9\nEOF\n"
                     "python3 .agents/bin/tasks.py start T-00000042"),
            2,
        )

    def test_a_start_on_ANOTHER_board_is_not_a_new_chantier_here(self) -> None:
        """CINQUIÈME FORME DU MÊME DÉFAUT, et celle qui mord les BANCS : le
        filet refusait `tasks.py --root <arbre jetable> start T-1`, qui fabrique
        un board de test et ne prend rien du chantier de cette session. Le
        régime gouverne le board de CE projet ; refuser une mesure faite
        ailleurs ne protège aucune capitalisation et empêche seulement de
        mesurer. Rencontré en voulant mesurer la garde du binôme."""
        import tempfile

        with tempfile.TemporaryDirectory() as autre:
            self.assertEqual(
                self._rc(f"python3 .agents/bin/tasks.py --root {autre} start T-00000999"),
                0,
            )
            self.assertEqual(
                self._rc(f'python3 .agents/bin/tasks.py --root="{autre}" start T-00000999'),
                0,
                "la forme `--root=<chemin>` n'est pas reconnue",
            )

    def test_a_start_on_THIS_board_is_still_refused(self) -> None:
        """LE CONTRÔLE DE NON-VACUITÉ DU CAS PRÉCÉDENT : un `--root` qui DÉSIGNE
        la racine courante ne doit rien exempter, sinon le filet est aveugle dès
        qu'une commande porte l'option."""
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._gele(root)
            self.assertEqual(
                SasTests._hook(
                    self, root, f"python3 .agents/bin/tasks.py --root {root} start T-00000999"
                ),
                2,
            )

    def test_a_dubious_extraction_never_consumes_the_sas(self) -> None:
        """LA CONTRAINTE POSÉE PAR LE BINÔME. Si l'identifiant extrait ne
        ressemble à rien, le filet ne doit ni refuser NI toucher au sas : sans
        ça, une extraction fautive écrivait une libération irréversible."""
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            m = self._gele(root)
            # `start` suivi d'un mot sans chiffre : extraction non concluante
            self.assertEqual(
                SasTests._hook(self, root, "python3 .agents/bin/tasks.py start toto"), 0
            )
            self.assertFalse(
                m.with_suffix(".libere").exists(),
                "une extraction douteuse a CONSOMMÉ le sas",
            )
            self.assertFalse(
                m.with_suffix(".baseline").exists(),
                "une extraction douteuse a posé une ligne de base",
            )


class SecondPalierTests(unittest.TestCase):
    """L'INSTRUMENT DE T-00000588, et il est né d'une mesure FAUSSE.

    Le régime d'atterrissage ne se réarme jamais — `.armed` sous `O_EXCL`,
    `.libere` irréversible — donc une session qui franchit le seuil, capitalise,
    repart et monte à 97 % ne verra plus aucune seconde passe réclamée. Ma
    première mesure comptait les `.libere` : zéro, donc « ferme sans geste ».
    Elle était TAUTOLOGIQUE — `.libere` n'existe que depuis le 13/09 11:32 et le
    seuil est passé de 80 à 90 le même jour à 09:52, or TROIS des QUATRE sessions
    armées sur disque précèdent les deux et portent `pct=80` ; la quatrième
    (22:57, `pct=90`) est la première qu'un instrument pouvait observer.
    Population VIDE, pas nulle.

    Le marqueur `.palier2` rend la question CONSTATABLE. Ce qui est éprouvé ici
    est exactement ce qui rendrait le relevé menteur : qu'il se pose sans qu'une
    session ait POURSUIVI, qu'il se pose sous le palier, ou qu'il confonde les
    deux populations que sa charge est censée séparer."""

    def _passes(
        self, pcts: list[int], env: dict[str, str] | None = None,
        libere_avant: int | None = None, script: Path | None = None,
    ) -> dict | None:
        """Rejoue N rafraîchissements de statusline sur le MÊME répertoire.

        Le `_arme` voisin jette sa racine à chaque appel, donc il ne peut rien
        dire d'un mécanisme dont toute la substance est « la sentinelle
        était-elle DÉJÀ là ». `libere_avant` pose `.libere` avant la passe
        d'indice donné, pour distinguer les deux populations."""
        import os
        import subprocess
        import tempfile

        # LA SURCHARGE DU POSTE EST NEUTRALISÉE, sinon le banc rougit chez qui a
        # exporté `CONTEXT_RETRO_PCT` — un faux rouge de porte, mesuré par le
        # binôme : à 80 exporté, deux témoins tombaient.
        propre = {k: v for k, v in os.environ.items() if k != "CONTEXT_RETRO_PCT"}
        with tempfile.TemporaryDirectory() as root:
            marqueurs = Path(root, ".agents/state/local/context-retro")
            for i, pct in enumerate(pcts):
                if libere_avant == i:
                    marqueurs.mkdir(parents=True, exist_ok=True)
                    for arme in marqueurs.glob("*.armed"):
                        arme.with_suffix(".libere").write_text("{}", encoding="utf-8")
                subprocess.run(
                    ["bash", str(script or STATUSLINE)],
                    input=json.dumps(
                        {"session_id": "x", "context_window": {"used_percentage": pct}}
                    ),
                    text=True, capture_output=True,
                    env={**propre, **(env or {}), "CLAUDE_PROJECT_DIR": root},
                )
            # NON-VACUITÉ DU HARNAIS LUI-MÊME. Sans cette ligne, un capteur cassé
            # rendrait TOUS les témoins négatifs verts — ils mesureraient
            # l'absence d'armement, pas l'absence de palier.
            self.assertTrue(
                marqueurs.is_dir() and list(marqueurs.glob("*.armed")),
                "aucun .armed : le banc mesure l'absence de CAPTEUR, pas l'absence de PALIER",
            )
            trouves = sorted(marqueurs.glob("*.palier2"))
            if not trouves:
                return None
            self.assertEqual(len(trouves), 1, "une session, un seul relevé")
            return json.loads(trouves[0].read_text(encoding="utf-8"))

    def test_a_session_that_STAYS_high_is_not_a_session_that_continued(self) -> None:
        """LE FAUX POSITIF QUE CET INSTRUMENT A RÉELLEMENT PRODUIT, et qu'une
        seule passe ne voyait pas. Ma première rédaction testait « la sentinelle
        était-elle déjà là » — or la ligne d'état repasse toutes les 5 s, donc
        elle l'est à la passe suivante sans qu'un point ait monté. Le binôme l'a
        mesuré : deux passes à 95 posaient le marqueur. Et une session reprise
        (`--resume`, l'après-compaction) DÉMARRE haute. Le témoin de poursuite
        est le pct d'ARMEMENT, qui doit être sous le palier."""
        self.assertIsNone(self._passes([95]), "armée et relevée dans la même passe")
        self.assertIsNone(self._passes([95, 95]), "5 s plus tard n'est pas une poursuite")
        self.assertIsNone(self._passes([96, 95, 97]), "une session qui redescend puis remonte")

    def test_a_session_that_CONTINUES_past_the_palier_is_recorded(self) -> None:
        releve = self._passes([90, 95])
        self.assertIsNotNone(releve, "le cas même du ticket n'est pas relevé")
        self.assertEqual(releve["pct"], 95)
        self.assertEqual(releve["seuil"], 90)
        self.assertEqual(releve["ticket"], "T-00000588")

    def test_under_the_palier_nothing_is_laid(self) -> None:
        """94 n'est pas 95, et un instrument qui arrondit ne mesure plus rien."""
        self.assertIsNone(self._passes([90, 94]))

    def test_the_embedded_python_carries_no_shell_metacharacter(self) -> None:
        """UN COMMENTAIRE EST DU CODE ICI, et c'est la faute que ce filet gèle.

        Le capteur vit dans la chaîne DOUBLE-QUOTÉE de `"$PY" -c "…"` : le shell
        y fait une substitution de commande AVANT que python ne voie un octet.
        Mesuré le 2026-09-13 — dix « commande introuvable » par passe, toutes les
        5 s — et le `2>/dev/null` de l'appel ne les masque PAS, l'expansion
        précédant la redirection. Pire, chaque ligne portait un nombre PAIR
        d'accents : un seul ajouté fait qu'une paire enjambe le saut de ligne et
        avale la ligne de CODE suivante dans le commentaire, capteur mort en
        silence. La classe, pas l'instance : `bash -n` accepte tout cela."""
        lignes = STATUSLINE.read_text(encoding="utf-8").splitlines()
        debut = next(i for i, l in enumerate(lignes) if '"$PY" -c "' in l)
        fin = next(i for i, l in enumerate(lignes) if i > debut
                   and l.startswith('" 2>/dev/null'))
        fautifs = [(debut + 2 + i, l)
                   for i, l in enumerate(lignes[debut + 1:fin]) if "`" in l]
        self.assertEqual(fautifs, [], f"le shell interprète ces lignes : {fautifs}")

    def test_the_positive_witness_DIES_without_the_continuation_guard(self) -> None:
        """LE CONTRÔLE DE MUTATION VOYAGE AVEC LE BANC, au lieu de vivre dans un
        bac à sable que l'adoptant n'aura jamais. Sans `deja_arme`, le témoin
        négatif ci-dessus doit TOMBER — sinon il est vert sur rien."""
        import tempfile

        mute = STATUSLINE.read_text(encoding="utf-8").replace(
            "deja_arme and pct >= seuil + 5", "pct >= seuil + 5")
        self.assertNotEqual(mute, STATUSLINE.read_text(encoding="utf-8"),
                            "l'ancrage de la mutation n'existe plus")
        with tempfile.TemporaryDirectory() as bac:
            copie = Path(bac, "statusline_mute.sh")
            copie.write_text(mute, encoding="utf-8")
            self.assertIsNotNone(
                self._passes([95], script=copie),
                "la garde de poursuite retirée, le banc reste vert : il est vacant")

    def test_the_payload_separates_the_two_populations(self) -> None:
        """C'EST LA NON-VACUITÉ DU RELEVÉ. Les deux passes sont identiques à
        l'octet près ; seule la présence de `.libere` change. Si la charge ne
        bougeait pas, le fichier ne dirait pas laquelle des deux moitiés il
        mesure — le sas rouvert (le ticket tel qu'il est écrit) ou le gel qui a
        duré jusqu'au palier sans capitalisation."""
        gele = self._passes([90, 95])
        libere = self._passes([90, 95], libere_avant=1)
        self.assertEqual(gele["libere"], False)
        self.assertEqual(libere["libere"], True)

    def test_the_palier_follows_the_pilot_threshold(self) -> None:
        """Le palier est SEUIL + 5, pas 95 en dur : le seuil reste un nombre du
        pilote et la graduation le suit."""
        self.assertIsNotNone(self._passes([80, 85], {"CONTEXT_RETRO_PCT": "80"}))
        self.assertIsNone(self._passes([80, 84], {"CONTEXT_RETRO_PCT": "80"}))

    def test_the_reading_is_laid_ONCE_and_keeps_the_first_crossing(self) -> None:
        """La statusline repasse toutes les 5 s. Sans `O_EXCL` le relevé
        raconterait la dernière mesure au lieu du franchissement."""
        releve = self._passes([90, 95, 97, 99])
        self.assertEqual(releve["pct"], 95)

    def test_the_payload_carries_the_FACTS_of_capitalisation_not_just_the_sas(self) -> None:
        """`.libere` NE MESURE PAS LA CAPITALISATION — trouvaille du binôme.

        Ce marqueur n'est écrit qu'au SITE DE REFUS : il faut qu'un démarrage
        hors agenda ait été TENTÉ pour que le sas soit seulement consulté. Une
        session qui capitalise puis continue SUR son agenda n'en a jamais, et
        c'est le cas NOMINAL. Lire `libere=false` comme « gelée sans
        capitaliser » rangeait donc le cas nominal du côté qui FERME le ticket.
        La charge porte les faits eux-mêmes."""
        releve = self._passes([90, 95])
        self.assertIn("retro_done", releve)
        self.assertIn("baseline", releve)
        self.assertIn("context_window", releve,
                      "sans la fenêtre, +5 POINTS ne se lit pas d'une machine à l'autre")

    def test_the_instrument_reads_no_hook_and_arms_nothing(self) -> None:
        """BORNE DITE : `.palier2` est un INSTRUMENT, pas un régime. Le jour où
        un hook le lit, il refuse du travail sans que personne l'ait décidé.

        LA BORNE PORTE SUR L'ARBRE ENTIER, pas sur deux fichiers choisis : le
        binôme a relevé qu'un témoin qui gèle deux surfaces nommées ne dit rien
        de la troisième qu'on ajoutera.

        LES STORES D'ÉTAT SONT HORS PÉRIMÈTRE, ET LA PORTE ME L'A APPRIS. La
        première rédaction balayait l'arbre entier ; elle a rougi dès que le
        board a porté la prose de ce ticket — `TASKS.json` et l'event store
        citaient `palier2` sans rien en consommer. C'est la faute déjà payée ici
        une fois : **citer un nom attire la surface dans son propre périmètre de
        balayage**. `.agents/state/` est du récit d'équipe, pas du code qui
        s'exécute ; ce qui doit rester vide, c'est l'ensemble des surfaces qui
        TOURNENT.

        **`runs/` EXCLU LE 2026-09-22, MÊME RAISON, PAS UN RELÂCHEMENT.**
        `T-00000677` a fait entrer les exports « run par auteur » dans les
        fichiers SUIVIS (`1129030`, premiers `runs/**/*.jsonl` commités). Ces
        fichiers sérialisent des observations de board, donc ils citent la prose
        des tâches — dont celle qui porte ce marqueur. C'est le MÊME cas que
        `.agents/state/` : du récit d'équipe versionné, jamais du code qui
        s'exécute. L'assertion n'est pas affaiblie — ce qu'elle mesure reste
        « aucune surface EXÉCUTABLE ne consomme le marqueur ».

        **`docs/interne/chantier/backlog/` EXCLU LE 2026-10-02 (T-00001043), MÊME RAISON.**
        `T-00001043` (fusion `7db54055`) a fait entrer les sources du backlog dans les
        fichiers SUIVIS ; ses données et sa prose (`BACKLOG.md`, `backlog.yaml`, `annexes/`)
        recopient la prose du board, donc citent ce marqueur : du récit d'équipe versionné,
        comme `.agents/state/`. **RESTENT BALAYÉS, LES FILTRES CUMULÉS (T-00001113)** : tout
        tools/ (toute casse), tout suffixe de `SCRIPTS_P2` — .py/.pyw/.sh/.bash/.zsh/.ksh, et
        .js/.mjs/.cjs/.ts depuis T-00001165 (un script de workflow se lance par son chemin, sans
        #!) — toute casse, et tout fichier qui ouvre par #!. Un seul ne suffit pas, faux verts mesurés : le dossier seul laisse passer un
        `annexes/*.py`, l'extension seule un script `tools/` sans suffixe, les deux un script à
        shebang sans suffixe hors `tools/`. Les chemins se lisent en `-z` sous `core.quotePath=false`
        et se décodent en `surrogateescape` : un chemin accentué n'est jamais cité entre guillemets
        (faux rouge mesuré). Le filtre vit au niveau du module (`_surface_balayee`, `_chemins_z`) ;
        sa table de vérité est `FiltrePalier2Tests`, sur des fichiers écrits : l'arbre réel ne
        contient aucun de ces cas, il laissait vert un mutant qui annule à la fois `-z` et la casse.
        L'assertion n'est pas affaiblie.

        **`docs/tasks/critiques/` EXCLU LE 2026-10-02 (T-00001043), MÊME RAISON.**
        Les rapports du binôme bis de la fournée 4 (`8413ba4b`) relatent ce
        témoin, donc ils citent le marqueur. Ce sont des rapports de critique
        commités VERBATIM, jamais réécrits : du récit d'équipe, jamais du code
        qui s'exécute. L'assertion n'est pas affaiblie.

        **LA PROSE DE `docs/tasks/` SORT LE 2026-10-04, MÊME RÈGLE QUE LE BACKLOG.** Le prompt
        de reprise de la fin de fournée 5 (`1ed256a0`, `PROMPT-SESSION-DIRECT.md`) recopie la
        réserve de ce témoin, donc cite le marqueur : le témoin était rouge sur l'arbre réel à
        `cdbc89dd`. Plans, prompts et états de reprise sont du récit d'équipe ; restent balayés,
        comme sous le backlog, tout tools/, tout script par extension et tout fichier à shebang.

        **LA PROSE DE `docs/interne/chantier/lots/` SORT LE 2026-10-04 (T-00001165), MÊME RÈGLE.**
        L'état de reprise du dev direct (`fd2ea9e6`, `LOT-DIRECT-REPRISE.md`) et le plan de lot
        de la fournée 7 (`163e5c5f`, `LOT-F7-plan.md`) recopient la prose de ce témoin : il était
        rouge sur l'arbre réel à `e0b9d62b`. Ce dossier porte aussi un VRAI script,
        `workflow-fournee.js`, lancé par son chemin : il reste balayé par son extension. L'assertion
        n'est pas affaiblie.

        **LA PROSE DE `docs/design/` SORT LE 2026-10-23 (T-01M5M8EEX8PEEA6Z5RHF4QM6TQ), MÊME RÈGLE.**
        Les maquettes de la frise GLASS v2 citées par cette tâche (`2026-10-23-glass-frise/`,
        `Board.dc.html`) recopient en DONNÉES d'exemple du texte de board qui cite le marqueur,
        jamais exécuté : le témoin était rouge sur l'arbre réel à `49e03b15`. Restent balayés, comme
        ailleurs, tout tools/, tout script par extension et tout fichier à shebang. L'assertion
        n'est pas affaiblie."""
        self.assertEqual(
            consommateurs_palier2(),
            [".agents/evals/test_context_retro_contract.py", ".claude/statusline.sh"],
            "une surface consomme le marqueur — l'instrument est devenu une garde",
        )


class FiltrePalier2Tests(unittest.TestCase):
    """Table de vérité du périmètre palier2 (T-00001113) sur des fichiers ÉCRITS sous un répertoire
    jetable. L'arbre réel ne porte aucun de ces cas : un mutant qui retire la casse, une extension,
    le shebang, la prose de `docs/tasks/` ou le découpage NUL y restait vert. Ici il rougit."""

    EXCLUS = (".agents/state/board/TASKS.json", "runs/a/b.jsonl", "docs/tasks/critiques/é.md",
              BACKLOG_P2 + "BACKLOG.md", BACKLOG_P2 + "annexes/x.md",
              TASKS_P2 + "PROMPT-SESSION-DIRECT.md", TASKS_P2 + "T-1-plan.md",
              LOTS_P2 + "LOT-F7-plan.md", LOTS_P2 + "LOT-DIRECT-REPRISE.md",
              DESIGN_P2 + "2026-10-23-glass-frise/Board.dc.html")
    BALAYES = (BACKLOG_P2 + "annexes/x.py", BACKLOG_P2 + "x.PY", BACKLOG_P2 + "x.pyw",
               BACKLOG_P2 + "x.sh", BACKLOG_P2 + "x.bash", BACKLOG_P2 + "x.zsh", BACKLOG_P2 + "x.ksh",
               BACKLOG_P2 + "tools/run", BACKLOG_P2 + "Tools/run", ".claude/statusline.sh",
               TASKS_P2 + "tools/run", TASKS_P2 + "x.sh",
               # T-00001165 : un script de workflow (lancé par son chemin, sans #!) reste balayé.
               TASKS_P2 + "lot.js", BACKLOG_P2 + "x.MJS", TASKS_P2 + "x.cjs", BACKLOG_P2 + "x.ts",
               LOTS_P2 + "workflow-fournee.js", LOTS_P2 + "tools/run",
               # T-01M5M8EEX8PEEA6Z5RHF4QM6TQ : sous docs/design/, un script reste balayé.
               DESIGN_P2 + "2026-10-23-glass-frise/frise.js", DESIGN_P2 + "tools/run")

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.racine = Path(tmp.name)

    def _ecrire(self, rel: str, contenu: bytes = b"palier2\n") -> str:
        p = self.racine / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(contenu)
        return rel

    def test_la_prose_et_les_stores_sortent(self) -> None:
        for rel in self.EXCLUS:
            with self.subTest(rel=rel):
                self.assertFalse(_surface_balayee(self._ecrire(rel), self.racine))

    def test_tools_et_scripts_restent_toute_casse(self) -> None:
        for rel in self.BALAYES:
            with self.subTest(rel=rel):
                self.assertTrue(_surface_balayee(self._ecrire(rel), self.racine))

    def test_un_shebang_sans_suffixe_reste_balaye(self) -> None:
        for prose in PROSE_P2:
            with self.subTest(prose=prose):
                self.assertTrue(_surface_balayee(
                    self._ecrire(prose + "annexes/run", b"#!/bin/sh\necho palier2\n"), self.racine))
                self.assertFalse(_surface_balayee(
                    self._ecrire(prose + "annexes/note", b"# palier2\n"), self.racine))

    def test_un_fichier_illisible_reste_balaye(self) -> None:
        self.assertTrue(_surface_balayee(BACKLOG_P2 + "annexes/absent", self.racine))

    def test_les_chemins_se_decoupent_au_nul(self) -> None:
        self.assertEqual(_chemins_z("a b.md\0é.md\0"), ["a b.md", "é.md"])
        self.assertEqual(_chemins_z(""), [])

    def test_le_decodage_est_utf8_surrogateescape(self) -> None:
        vide = subprocess.CompletedProcess([], 0, stdout="")
        with mock.patch.object(subprocess, "run", return_value=vide) as run:
            self.assertEqual(consommateurs_palier2(self.racine), [])
        appel = run.call_args
        self.assertIn("-z", appel.args[0])
        self.assertEqual((appel.kwargs.get("encoding"), appel.kwargs.get("errors")),
                         ("utf-8", "surrogateescape"))


class NonVacuityTests(unittest.TestCase):
    def test_the_bench_exists_and_covers_the_negative_control(self) -> None:
        """Le contrôle négatif qui compte : `tasks.py new` doit TOUJOURS passer.
        Sans lui le filet fermerait ce que la rétro est censée rendre possible."""
        self.assertTrue(BENCH.is_file())
        text = BENCH.read_text(encoding="utf-8")
        self.assertIn("tasks.py new", text)
        self.assertIn("contrôle NÉGATIF", text)


if __name__ == "__main__":
    unittest.main()
