"""Tests du garde de kickoff (T-00000243) — section 8 de la conception.

Chaque cas de la section 8 y est, plus ceux que les quatre iterations
planner/plan-critic ont ajoutes (C4, C5, C10, C11, C13, C14, C17, C18, C22, C25).

DEUX EPINGLES PORTEUSES, NOMMEES (amendement C25) — elles n'avaient pas d'id de
test dans le dossier, ce qui les rendait impossibles a citer dans une revue :

* ``test_deny_envelope_literal`` — le texte exact de l'enveloppe de refus.
* ``test_deny_envelope_matches_common_py`` — la MEME enveloppe, comparee a celle
  que ``.codex/hooks/_common.deny`` produit reellement, le module charge PAR
  CHEMIN. C'est cette seconde epingle qui empeche qu'une modification coordonnee
  de ``_common.deny`` et de sa propre epingle laisse la copie du garde perimee et
  VERTE (C13).

Une troisieme epingle nommee couvre la forme de la regle Claude Code :
``test_permissions_deny_uses_edit_form`` — ``Edit(path)`` couvre TOUS les outils
d'edition, ``Write(path)`` est INERTE et n'ajoute rien (L-00000051).
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import kickoff_guard as kg  # noqa: E402

REPO = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Fixtures — un depot minuscule, ecrit a la main, jamais le depot reel.
# ---------------------------------------------------------------------------


def build_repo(
    tmp: Path,
    *,
    gate: str | None = None,
    tasks_json: object | str | None = None,
    specs_json: object | str | None = None,
) -> Path:
    """Un faux depot. ``gate=None`` = fichier de porte ABSENT (depot desarme)."""
    (tmp / ".agents" / "state" / "board").mkdir(parents=True, exist_ok=True)
    (tmp / ".agents" / "state" / "specs").mkdir(parents=True, exist_ok=True)
    (tmp / ".agents" / "state" / "gates").mkdir(parents=True, exist_ok=True)
    if gate is not None:
        (tmp / kg.GATE_RELPATH).write_text(gate, encoding="utf-8")
    if tasks_json is not None:
        body = tasks_json if isinstance(tasks_json, str) else json.dumps(tasks_json)
        (tmp / ".agents" / "state" / "board" / "TASKS.json").write_text(body, encoding="utf-8")
    if specs_json is not None:
        body = specs_json if isinstance(specs_json, str) else json.dumps(specs_json)
        (tmp / ".agents" / "state" / "specs" / "SPECS.json").write_text(body, encoding="utf-8")
    return tmp


def board(*tasks_: dict) -> dict:
    return {"next_id": len(tasks_) + 1, "tasks": list(tasks_)}


def task(tid: str, state: str = "running", writeset: list[str] | None = None, **extra) -> dict:
    out = {"id": tid, "state": state, "task": f"title of {tid}"}
    if writeset is not None:
        out["writeset"] = writeset
    out.update(extra)
    return out


def journal(*plan_task_ids: str) -> dict:
    entries = [
        {
            "id": f"S-{i + 1:08d}",
            "task": tid,
            "kind": "plan",
            "title": f"plan for {tid}",
            "text": "",
            "files": [],
            "date": "2026-08-20",
        }
        for i, tid in enumerate(plan_task_ids)
    ]
    return {"next_id": len(entries) + 1, "entries": entries}


def verdict(root: Path, path: str) -> kg.Decision:
    """Le releve complet — porte, board, journal — puis la decision."""
    gate = kg.read_gate(root)
    b, j = kg.collect(root, gate)
    return kg.decide(path, gate, b, j)


# ---------------------------------------------------------------------------
# LA POLARITE — un depot qui n'a rien arme ne change pas de comportement
# ---------------------------------------------------------------------------


class PolarityTests(unittest.TestCase):
    def test_gate_absent_allows_in_silence(self):
        with _tmp() as tmp:
            root = build_repo(tmp, tasks_json=board(task("T-1", writeset=["src/"])))
            self.assertTrue(verdict(root, "src/a.py").allowed)

    def test_gate_empty_still_arms_BY_CLASS(self):
        """CONTRAT CHANGÉ PAR LA DÉCISION L DU 2026-09-13, et il faut le dire.

        Avant : « porte absente, VIDE, ou n'ouvrant aucune tâche → passe, en
        silence ». La branche VIDE est retirée : l'armement est désormais dérivé
        de la CLASSE de la tâche `running`, donc la PRÉSENCE du fichier est
        l'interrupteur, pas son contenu. Un fichier vide veut maintenant dire
        « armement par classe actif, aucun ajout manuel ».

        CE QUI N'A PAS CHANGÉ, et c'est la seule polarité qui compte pour un
        adoptant : fichier ABSENT → silence total. C'est
        `test_gate_absent_allows_in_silence`, juste au-dessus, qui la tient.

        Ici `T-1` est `running` avec un writeset `["src/"]` — un RÉPERTOIRE,
        donc une classe indécidable, donc armée fail-closed."""
        with _tmp() as tmp:
            root = build_repo(tmp, gate="", tasks_json=board(task("T-1", writeset=["src/"])))
            self.assertFalse(verdict(root, "src/a.py").allowed)

    def test_gate_empty_leaves_a_TRIVIAL_task_alone(self):
        """LE CONTRÔLE NÉGATIF DU PRÉCÉDENT, et la raison d'être de l'option 3.

        Trois chemins exacts ou moins : la tâche est triviale, elle n'est PAS
        armée, et elle écrit sans plan. Sans ce test, l'armement par classe
        serait indistinguable d'un armement systématique — c'est-à-dire du
        « armer sec » que le pilote a écarté."""
        with _tmp() as tmp:
            root = build_repo(
                tmp,
                gate="",
                tasks_json=board(task("T-1", writeset=["src/a.py", "src/b.py"])),
            )
            self.assertTrue(verdict(root, "src/a.py").allowed)

    def test_gate_comments_only_arms_by_class_too(self):
        """Un fichier de commentaires est un fichier PRÉSENT : même régime."""
        with _tmp() as tmp:
            root = build_repo(
                tmp,
                gate="# armed tasks, one id per line\n\n   # nothing yet\n",
                tasks_json=board(task("T-1", writeset=["src/"])),
            )
            self.assertFalse(verdict(root, "src/a.py").allowed)

    def test_a_PENDING_task_is_never_armed_by_its_class(self):
        """Armer une tâche non prise ferait refuser TOUT le dépôt au nom d'un
        travail que personne n'a commencé — un refus que son lecteur ne pourrait
        pas relier à son geste."""
        with _tmp() as tmp:
            root = build_repo(
                tmp,
                gate="",
                tasks_json=board(task("T-1", state="pending", writeset=["src/"])),
            )
            self.assertTrue(verdict(root, "src/a.py").allowed)

    def test_a_RUNNING_task_WITHOUT_writeset_is_armed_fail_closed(self):
        """BRANCHE (1) DE LA DÉCISION L, confirmée par le pilote : « à chaque
        prise de tâche sans write-set, il faut que la tâche la crée ».

        Mesuré le 2026-09-13 : 187 des 215 tâches `pending` sont dans ce cas.
        Ce n'est pas un coût mais un HÉRITAGE — elles sont antérieures à
        l'obligation. Le refus existant nomme la commande qui répare."""
        with _tmp() as tmp:
            root = build_repo(tmp, gate="", tasks_json=board(task("T-1")))
            d = verdict(root, "src/a.py")
            self.assertFalse(d.allowed)
            self.assertEqual(d.rule, "armed-without-writeset")

    def test_gate_absent_never_opens_the_board(self):
        """Le court-circuit est MESURE, pas affirme : sur un depot desarme, ni le
        board ni le journal ne sont lus (donc un board pourri ne bloque rien)."""
        with _tmp() as tmp:
            root = build_repo(tmp, tasks_json="{ not json at all")
            self.assertTrue(verdict(root, "src/a.py").allowed)

    def test_disarmed_repo_is_byte_silent(self):
        """LE TEST QUI PROUVE LA LIVRAISON DESARMEE. Le depot REEL ne LIVRE aucun
        fichier de porte, donc une edition ordinaire doit produire exit 0 et
        ZERO octet — pas un refus, pas un avertissement, pas une ligne.

        LA PROPRIETE MESUREE EST « JAMAIS COMMITTE », PAS « ABSENT DU DISQUE »
        (T-012). C'etait la meme chose tant qu'armer voulait dire committer ;
        depuis que l'armement est un geste de POSTE — `.gitignore` sur ce
        marqueur, comme `UI_GATE.local`, et `kickoff_arm.py` qui trace avant
        d'agir — les deux ont divergé. Tester la presence sur disque rendait ce
        banc ROUGE chez tout mainteneur qui arme legitimement, et VERT en CI :
        le pire des deux, un filet qu'on finit par desarmer.

        Ce que le message d'origine disait deja est donc ce qui est asserte :
        le fichier ne doit JAMAIS etre suivi par git. Quand un poste l'a arme,
        la seconde moitie du banc — le silence a l'octet — n'a plus de sujet et
        le banc le DIT plutot que de passer en silence.
        """
        suivi = subprocess.run(
            ["git", "ls-files", "--error-unmatch", str(kg.GATE_RELPATH)],
            cwd=str(REPO), capture_output=True, text=True,
        ).returncode == 0
        self.assertFalse(
            suivi,
            f"{kg.GATE_DISPLAY} must NEVER be committed: the kit ships DISARMED. "
            "Remede : `git rm --cached` sur ce chemin ; il est deja git-ignore.",
        )
        if (REPO / kg.GATE_RELPATH).exists():
            self.skipTest(
                f"{kg.GATE_DISPLAY} present sur CE POSTE (armement local, non "
                "suivi par git) — le silence a l'octet n'a pas de sujet ici. "
                "La moitie qui compte, « jamais committe », vient de passer."
            )
        payload = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": "README.md"}})
        proc = subprocess.run(
            [sys.executable, str(REPO / ".agents" / "bin" / "kickoff_guard.py")],
            input=payload,
            capture_output=True,
            text=True,
            cwd=str(REPO),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "")
        self.assertEqual(proc.stderr, "")


# ---------------------------------------------------------------------------
# LA REGLE — couverture, non-vacuite, branche stricte
# ---------------------------------------------------------------------------


class RuleTests(unittest.TestCase):
    def test_path_outside_every_armed_writeset_passes(self):
        with _tmp() as tmp:
            root = build_repo(
                tmp,
                gate="T-1\n",
                tasks_json=board(task("T-1", "running", ["src/"])),
                specs_json=journal("T-1"),
            )
            self.assertTrue(verdict(root, "docs/readme.md").allowed)

    def test_three_conditions_met_passes(self):
        with _tmp() as tmp:
            root = build_repo(
                tmp,
                gate="T-1\n",
                tasks_json=board(task("T-1", "running", ["src/"])),
                specs_json=journal("T-1"),
            )
            self.assertTrue(verdict(root, "src/a.py").allowed)

    def test_armed_task_not_running_refuses(self):
        with _tmp() as tmp:
            root = build_repo(
                tmp,
                gate="T-1\n",
                tasks_json=board(task("T-1", "pending", ["src/"])),
                specs_json=journal("T-1"),
            )
            d = verdict(root, "src/a.py")
            self.assertTrue(d.refused)
            self.assertEqual(d.rule, "not-running")
            self.assertIn("T-1", d.reason)

    def test_armed_running_without_plan_refuses(self):
        with _tmp() as tmp:
            root = build_repo(
                tmp,
                gate="T-1\n",
                tasks_json=board(task("T-1", "running", ["src/"])),
                specs_json=journal(),
            )
            d = verdict(root, "src/a.py")
            self.assertTrue(d.refused)
            self.assertEqual(d.rule, "no-plan")
            self.assertIn("kind=plan", d.reason)

    def test_third_condition_is_coverage_itself(self):
        """AMENDEMENT C5 : « hors perimetre declare » a ete SUPPRIME du tableau
        de la spec parce qu'il est INATTEIGNABLE — la couverture EST
        l'appartenance au writeset. Une tache conforme mais dont le writeset ne
        couvre pas le chemin ne refuse pas : elle ne couvre simplement pas."""
        with _tmp() as tmp:
            root = build_repo(
                tmp,
                gate="T-1\n",
                tasks_json=board(task("T-1", "running", ["src/"])),
                specs_json=journal("T-1"),
            )
            self.assertTrue(verdict(root, "tests/a.py").allowed)
        self.assertNotIn("out-of-writeset", kg.REFUSAL_RULES)

    def test_unknown_armed_id_refuses_by_name_never_in_silence(self):
        with _tmp() as tmp:
            root = build_repo(
                tmp,
                gate="T-999\n",
                tasks_json=board(task("T-1", "running", ["src/"])),
                specs_json=journal("T-1"),
            )
            d = verdict(root, "anything/at/all.txt")
            self.assertTrue(d.refused)
            self.assertEqual(d.rule, "armed-unknown-task")
            self.assertIn("T-999", d.reason)

    def test_armed_without_writeset_refuses_every_write(self):
        """NON-VACUITE. Le gel est A L'ECHELLE DU DEPOT et le refus le dit, en
        nommant un remede ATTEIGNABLE (`tasks.py writeset` passe par Bash, que ce
        garde ne hooke jamais)."""
        with _tmp() as tmp:
            root = build_repo(
                tmp,
                gate="T-1\n",
                tasks_json=board(task("T-1", "running")),
                specs_json=journal("T-1"),
            )
            for path in ("src/a.py", "docs/x.md", "anything.txt"):
                d = verdict(root, path)
                self.assertTrue(d.refused, path)
                self.assertEqual(d.rule, "armed-without-writeset")
            self.assertIn("tasks.py writeset T-1", d.reason)

    def test_armed_with_empty_writeset_list_refuses_too(self):
        with _tmp() as tmp:
            root = build_repo(
                tmp,
                gate="T-1\n",
                tasks_json=board(task("T-1", "running", [])),
                specs_json=journal("T-1"),
            )
            self.assertEqual(verdict(root, "src/a.py").rule, "armed-without-writeset")

    def test_inadmissible_stored_writeset_path_counts_as_covering(self):
        """LA BRANCHE STRICTE SUR L'IMPOSSIBLE, dans son sens : un chemin de
        writeset inadmissible (ici absolu, refuse par la clause
        `non-empty-segment`) compte comme COUVRANT, donc mene au refus."""
        with _tmp() as tmp:
            root = build_repo(
                tmp,
                gate="T-1\n",
                tasks_json=board(task("T-1", "running", ["/etc/passwd"])),
                specs_json=journal("T-1"),
            )
            d = verdict(root, "totally/unrelated.txt")
            self.assertTrue(d.refused)
            self.assertEqual(d.rule, "armed-writeset-inadmissible")

    def test_admissibility_is_universal_not_existential(self):
        """AMENDEMENT C4 : une entree ADMISSIBLE ne sauve pas un writeset qui en
        porte aussi une INADMISSIBLE — sinon la branche stricte serait
        contredite par la premiere bonne entree venue."""
        with _tmp() as tmp:
            root = build_repo(
                tmp,
                gate="T-1\n",
                tasks_json=board(task("T-1", "running", ["src/", "C:/repo/x.py"])),
                specs_json=journal("T-1"),
            )
            d = verdict(root, "src/a.py")
            self.assertTrue(d.refused)
            self.assertEqual(d.rule, "armed-writeset-inadmissible")

    def test_at_least_one_conformant_covering_task_lets_the_write_through(self):
        """Le quantificateur EXISTENTIEL : deux taches armees aux perimetres
        imbriques, une seule conforme -> l'ecriture passe."""
        with _tmp() as tmp:
            root = build_repo(
                tmp,
                gate="T-1\nT-2\n",
                tasks_json=board(
                    task("T-1", "pending", ["src/"]),
                    task("T-2", "running", ["src/auth/"]),
                ),
                specs_json=journal("T-2"),
            )
            self.assertTrue(verdict(root, "src/auth/login.py").allowed)

    def test_refusal_names_every_covering_task_with_its_missing_condition(self):
        with _tmp() as tmp:
            root = build_repo(
                tmp,
                gate="T-1\nT-2\n",
                tasks_json=board(
                    task("T-1", "pending", ["src/"]),
                    task("T-2", "blocked", ["src/auth/"]),
                ),
                specs_json=journal("T-1", "T-2"),
            )
            d = verdict(root, "src/auth/login.py")
            self.assertTrue(d.refused)
            self.assertIn("T-1", d.reason)
            self.assertIn("T-2", d.reason)
            self.assertEqual(d.rule, "not-running")

    def test_disagreeing_rules_aggregate_to_kickoff_required(self):
        with _tmp() as tmp:
            root = build_repo(
                tmp,
                gate="T-1\nT-2\n",
                tasks_json=board(
                    task("T-1", "pending", ["src/"]),
                    task("T-2", "running", ["src/auth/"], parallel_group=""),
                ),
                specs_json=journal("T-1"),
            )
            d = verdict(root, "src/auth/login.py")
            self.assertTrue(d.refused)
            self.assertEqual(d.rule, "kickoff-required")

    def test_gate_ignores_comments_and_duplicates(self):
        with _tmp() as tmp:
            root = build_repo(tmp, gate="T-1  # the one\n\nT-1\n# T-9\n T-2 \n")
            self.assertEqual(kg.read_gate(root).ids, ("T-1", "T-2"))


# ---------------------------------------------------------------------------
# LE PREDICAT DE COUVERTURE — directionnel, a la frontiere de segment
# ---------------------------------------------------------------------------


class CoveragePredicateTests(unittest.TestCase):
    def test_directory_entry_covers_its_children(self):
        self.assertTrue(kg.writeset_covers("src/a/", "src/a/b.py"))
        self.assertTrue(kg.writeset_covers("src/a", "src/a/b.py"))
        self.assertTrue(kg.writeset_covers("src/a/b.py", "src/a/b.py"))

    def test_segment_boundary_keeps_sibling_prefixes_apart(self):
        """`src/a` et `src/ab` sont disjoints — un test de prefixe au niveau de
        la CHAINE les fusionnerait."""
        self.assertFalse(kg.writeset_covers("src/a", "src/ab.py"))
        self.assertFalse(kg.writeset_covers("src/a/", "src/ab/c.py"))

    def test_containment_is_directional_not_symmetric(self):
        """La difference d'avec `tasks.writeset_paths_overlap`, qui est
        SYMETRIQUE et signale un chevauchement dans les deux sens."""
        self.assertTrue(kg.writeset_covers("src/", "src/a/b.py"))
        self.assertFalse(kg.writeset_covers("src/a/b.py", "src/"))
        import tasks as _tasks

        self.assertIsNotNone(_tasks.writeset_paths_overlap(["src/a/b.py"], ["src/"]))

    def test_windows_separators_and_case_fold(self):
        self.assertTrue(kg.writeset_covers("src\\a\\", "src/a/b.py"))
        self.assertTrue(kg.writeset_covers("SRC/A/", "src/a/b.py"))
        self.assertTrue(kg.writeset_covers("src/a/", "SRC\\A\\B.py"))

    def test_degenerate_inputs_cover_nothing(self):
        self.assertFalse(kg.writeset_covers("", "src/a.py"))
        self.assertFalse(kg.writeset_covers("/", "src/a.py"))
        self.assertFalse(kg.writeset_covers("src/", ""))

    def test_windows_written_path_is_matched_against_a_posix_writeset(self):
        with _tmp() as tmp:
            root = build_repo(
                tmp,
                gate="T-1\n",
                tasks_json=board(task("T-1", "pending", ["src/auth/"])),
                specs_json=journal("T-1"),
            )
            d = verdict(root, kg.relative_to_root(root, "src\\auth\\Login.py"))
            self.assertTrue(d.refused)
            self.assertEqual(d.rule, "not-running")

    def test_absolute_path_is_brought_back_under_the_root(self):
        with _tmp() as tmp:
            root = build_repo(tmp)
            self.assertEqual(kg.relative_to_root(root, str(root / "src" / "a.py")), "src/a.py")

    def test_path_outside_the_root_is_covered_by_nothing(self):
        with _tmp() as tmp:
            root = build_repo(tmp)
            outside = (root.parent / "elsewhere" / "x.py").resolve()
            self.assertEqual(kg.relative_to_root(root, str(outside)), "")


# ---------------------------------------------------------------------------
# LE FILTRE DE FORME D'ECRITURE (C2, C11, C18, C22)
# ---------------------------------------------------------------------------


class WriteFormTests(unittest.TestCase):
    def test_pure_write_tool_names(self):
        for name in ("Edit", "MultiEdit", "Write", "NotebookEdit", "apply_patch"):
            self.assertTrue(kg.is_write_form({"tool_name": name}), name)

    def test_copilot_spellings(self):
        for name in (
            "create_file",
            "insert_edit_into_file",
            "replace_string_in_file",
            "edit_file",
            # MESURE, pas documente (M-P9) : la CLI Copilot cree par `create`
            # {path, file_text} (T-01M4RWCAGQZKYQ9JS4C1JPBFVQ,
            # S-01M4RWM3TC4JWE5FDC8YB819Z4).
            "create",
        ):
            self.assertTrue(kg.is_write_form({"toolName": name}), name)

    def test_reads_and_unknown_tools_pass(self):
        """Le garde n'a pas mandat sur une LECTURE — et Copilot enregistre son
        preToolUse SANS matcher, donc c'est ce filtre qui borne le hook. `view`
        est la lecture de la CLI Copilot (M-P9)."""
        for name in ("Read", "Grep", "Glob", "Bash", "WebFetch", "", "read_file", "view"):
            self.assertFalse(kg.is_write_form({"tool_name": name}), name)

    def test_apply_patch_payload_marker_wins_over_the_name(self):
        payload = {"tool_name": "shell", "tool_input": {"command": "*** Update File: src/a.py\n"}}
        self.assertTrue(kg.is_write_form(payload))

    def test_str_replace_editor_view_is_a_read_and_passes(self):
        """C18 : outil MULTIPLEXE. `view` est une LECTURE — le cler sur le nom nu
        ferait refuser une lecture legitime."""
        payload = {"tool_name": "str_replace_editor", "tool_input": {"command": "view"}}
        self.assertFalse(kg.is_write_form(payload))

    def test_str_replace_editor_write_subcommands_are_writes(self):
        for sub in ("create", "str_replace", "insert", "undo_edit"):
            payload = {"tool_name": "str_replace_editor", "tool_input": {"command": sub}}
            self.assertTrue(kg.is_write_form(payload), sub)

    def test_str_replace_editor_without_command_field_passes_and_is_named(self):
        """C22, LE DEFAUT NOMME. Champ `command` absent -> PASSE. C'est la bonne
        polarite (refuser sur une sous-commande illisible recreerait le defaut
        sans-mandat de C2/C18), et le module le NOMME au lieu de le taire."""
        self.assertFalse(kg.is_write_form({"tool_name": "str_replace_editor"}))
        self.assertTrue(kg.UNKNOWN_SUBCOMMAND_PASSES)

    def test_str_replace_editor_unknown_subcommand_passes(self):
        payload = {"tool_name": "str_replace_editor", "tool_input": {"command": "teleport"}}
        self.assertFalse(kg.is_write_form(payload))

    def test_c22_defect_is_named_in_the_module_source(self):
        """Un defaut NON NOMME dans un garde est exactement la facon dont C17 est
        arrive. Celui-ci est ecrit dans le source, pas seulement connu."""
        source = (REPO / ".agents" / "bin" / "kickoff_guard.py").read_text(encoding="utf-8")
        self.assertIn("UNKNOWN_SUBCOMMAND_PASSES", source)
        self.assertIn("C22", source)

    def test_paths_are_read_from_every_host_spelling(self):
        self.assertEqual(
            kg.paths_from_payload({"tool_name": "Edit", "tool_input": {"file_path": "a.py"}}),
            ["a.py"],
        )
        # `filePath` est LU : le harness Local de VS Code passe `filePath`
        # (S-01M4RWM3TC4JWE5FDC8YB819Z4, T-01M4RWCAGQZKYQ9JS4C1JPBFVQ). L'ancienne
        # epingle `["b.py"]` gravait l'oubli de cette cle.
        self.assertEqual(
            kg.paths_from_payload({"toolName": "create_file", "toolArgs": {"filePath": "a.py",
                                                                           "path": "b.py"}}),
            ["a.py", "b.py"],
        )
        self.assertEqual(
            kg.paths_from_payload({"toolName": "replace_string_in_file",
                                   "toolArgs": {"filePath": "a.py"}}),
            ["a.py"],
        )
        self.assertEqual(
            kg.paths_from_payload(
                {"tool_name": "shell", "tool_input": {"command": "*** Add File: src/x.py\nbody"}}
            ),
            ["src/x.py"],
        )


# ---------------------------------------------------------------------------
# LE CONTRAT DE SORTIE, PAR HOTE (C3, C10, C17)
# ---------------------------------------------------------------------------

REFUSAL = kg.Decision(False, "not-running", "BLOCKED by kickoff guard: because.")


class HostContractTests(unittest.TestCase):
    def _emit(self, host: str):
        out, err = io.StringIO(), io.StringIO()
        rc = kg.emit_refusal(REFUSAL, host, out=out, err=err)
        return rc, out.getvalue(), err.getvalue()

    def test_claude_gets_stderr_and_exit_2(self):
        rc, out, err = self._emit("claude")
        self.assertEqual(rc, 2)
        self.assertEqual(out, "")
        self.assertIn("BLOCKED by kickoff guard", err)

    def test_envelope_hosts_get_the_envelope_and_exit_0(self):
        """Le SEUL canal que Codex / Copilot / Gemini aient jamais execute. Un
        hook a rc 2 pourrait s'y lire comme un PLANTAGE et echouer OUVERT.
        Depuis T-01M4RWC0DBM6XC1PDQGEG4P79C, copilot recoit EN PLUS la decision
        au premier niveau, egale a l'imbriquee ; les deux autres, l'imbriquee seule."""
        for host in ("codex", "copilot", "gemini"):
            rc, out, err = self._emit(host)
            self.assertEqual(rc, 0, host)
            self.assertEqual(err, "", host)
            body = json.loads(out)
            nested = body["hookSpecificOutput"]
            self.assertEqual(nested["permissionDecision"], "deny", host)
            if host == "copilot":
                self.assertEqual(
                    (body.get("permissionDecision"), body.get("permissionDecisionReason")),
                    (nested["permissionDecision"], nested["permissionDecisionReason"]),
                    host,
                )
            else:
                self.assertEqual(set(body), {"hookSpecificOutput"}, host)

    def test_absent_or_unknown_marker_uses_both_channels_then_exit_2(self):
        for host in ("", "antigravity", "nonsense"):
            rc, out, err = self._emit(kg.host_marker({"AGENTS_HOOK_HOST": host}))
            self.assertEqual(rc, 2, host)
            self.assertIn("permissionDecision", out, host)
            self.assertIn("BLOCKED by kickoff guard", err, host)

    def test_antigravity_is_not_a_key_it_arrives_labelled_gemini(self):
        """La cle morte `antigravity` est SUPPRIMEE : Antigravity execute
        `.agents/hooks.json`, donc arrive etiquete `gemini`."""
        self.assertNotIn("antigravity", kg.ENVELOPE_HOSTS)
        self.assertEqual(kg.host_marker({"AGENTS_HOOK_HOST": "gemini"}), "gemini")

    def test_host_marker_folds_case_and_whitespace(self):
        self.assertEqual(kg.host_marker({"AGENTS_HOOK_HOST": " Codex "}), "codex")

    #: Les deux textes exacts, par hote (T-01M4RWC0DBM6XC1PDQGEG4P79C, piege 1 du
    #: plan) : la forme imbriquee seule hors copilot ; sous copilot, la MEME, puis
    #: la decision au premier niveau, dans cet ordre de cles (celui de `_common`).
    LITERAL_NESTED = (
        '{"hookSpecificOutput":{"hookEventName":"PreToolUse",'
        '"permissionDecision":"deny","permissionDecisionReason":"why"}}'
    )
    LITERAL_COPILOT = (
        '{"hookSpecificOutput":{"hookEventName":"PreToolUse",'
        '"permissionDecision":"deny","permissionDecisionReason":"why"},'
        '"permissionDecision":"deny","permissionDecisionReason":"why"}'
    )

    def test_deny_envelope_literal(self):
        """EPINGLE PORTEUSE 1/2 (C25) — le texte exact, sous codex ET sous copilot."""
        self.assertEqual(kg.deny_envelope("why"), self.LITERAL_NESTED)
        for host, literal in (("codex", self.LITERAL_NESTED), ("copilot", self.LITERAL_COPILOT)):
            with self.subTest(host=host):
                self.assertEqual(kg.deny_envelope("why", host), literal)

    @unittest.skipUnless(
        (REPO / ".codex" / "hooks" / "_common.py").exists(),
        "the Codex hook library is absent from this checkout",
    )
    def test_deny_envelope_matches_common_py(self):
        """EPINGLE PORTEUSE 2/2 (C25, ferme C13) — la parite est MESUREE contre
        `.codex/hooks/_common.deny`, charge PAR CHEMIN (une LECTURE : le writeset
        de cette tache interdit d'EDITER ce fichier, jamais de le lire), sous
        codex ET sous copilot : une copie mise a jour d'un seul cote rougit."""
        spec = importlib.util.spec_from_file_location(
            "_kg_common_probe", REPO / ".codex" / "hooks" / "_common.py"
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
            for host in ("codex", "copilot"):
                with self.subTest(host=host), mock.patch.dict(
                    os.environ, {"AGENTS_HOOK_HOST": host}
                ):
                    buffer = io.StringIO()
                    with contextlib.redirect_stdout(buffer):
                        module.deny("why")
                    self.assertEqual(buffer.getvalue().strip(), kg.deny_envelope("why", host))
        finally:
            sys.modules.pop("_kg_common_probe", None)


# ---------------------------------------------------------------------------
# LE CABLAGE DU MARQUEUR (C17) et LA FORME DE permissions.deny (C25)
# ---------------------------------------------------------------------------


def _json_strings(node, out: list[str]) -> list[str]:
    if isinstance(node, str):
        out.append(node)
    elif isinstance(node, dict):
        for value in node.values():
            _json_strings(value, out)
    elif isinstance(node, list):
        for value in node:
            _json_strings(value, out)
    return out


REGISTRATIONS = (
    ".claude/settings.json",
    ".codex/hooks.json",
    ".agents/hooks.json",
    ".github/hooks/agent-guardrails.json",
)


class WiringTests(unittest.TestCase):
    def test_every_registration_invokes_the_guard(self):
        for rel in REGISTRATIONS:
            data = json.loads((REPO / rel).read_text(encoding="utf-8"))
            hits = [s for s in _json_strings(data, []) if "kickoff_guard.py" in s]
            self.assertTrue(hits, f"{rel} does not invoke kickoff_guard.py")

    def test_every_registration_sets_host(self):
        """C17 clos PAR CABLAGE, pas par prose : apres ce changement, aucun
        chemin ENREGISTRE ne tombe dans le defaut marqueur-absent. Le defaut ne
        gouverne plus que les invocations manuelles."""
        for rel in REGISTRATIONS:
            data = json.loads((REPO / rel).read_text(encoding="utf-8"))
            for command in [s for s in _json_strings(data, []) if "kickoff_guard.py" in s]:
                self.assertIn(
                    "AGENTS_HOOK_HOST",
                    command,
                    f"{rel}: a kickoff_guard invocation carries no host marker: {command}",
                )

    def test_permissions_deny_uses_edit_form(self):
        """EPINGLE NOMMEE (C25) — la forme de la regle est `Edit(path)`.

        Dans une deny-list Claude Code, `Edit(path)` couvre TOUS les outils
        d'edition, Write inclus ; une regle `Write(path)` est INERTE et n'ajoute
        rien (L-00000051). La regle est donc UNE ligne par chemin, jamais deux.
        """
        data = json.loads((REPO / ".claude" / "settings.json").read_text(encoding="utf-8"))
        deny = data["permissions"]["deny"]
        self.assertIn("Edit(./.agents/state/gates/KICKOFF_REQUIRED)", deny)
        self.assertNotIn("Write(./.agents/state/gates/KICKOFF_REQUIRED)", deny)
        self.assertFalse(
            [rule for rule in deny if rule.startswith("Write(")],
            "Write() rules are inert in a Claude Code deny list (L-00000051)",
        )

    def test_gate_file_is_self_protected_on_the_python_twins(self):
        for rel in (".codex/hooks/protect_paths.py", ".gemini/hooks/protect_paths.py"):
            source = (REPO / rel).read_text(encoding="utf-8")
            self.assertIn("kickoff_required", source.lower(), rel)

    def test_gate_file_is_self_protected_on_the_shell_guard(self):
        source = (REPO / ".claude" / "hooks" / "protect-paths.sh").read_text(encoding="utf-8")
        self.assertIn("kickoff_required", source.lower())
        # BLOCKED_PATTERNS reste INTOUCHE (L-013) : la protection nouvelle passe
        # par un bloc case-folded PROPRE, jamais par un ajout au motif brut.
        self.assertIn('BLOCKED_PATTERNS="src/legacy/ generated/ .env"', source)


# ---------------------------------------------------------------------------
# LES STORES ILLISIBLES — le garde refuse avec un motif, il ne coince jamais
# ---------------------------------------------------------------------------


class DegradedInputTests(unittest.TestCase):
    def test_malformed_board_with_an_armed_gate_refuses_with_a_runnable_remedy(self):
        """C6 : le refus ne nomme JAMAIS `tasks.py list`, qui relit le board —
        un garde ne doit pas bloquer son propre diagnostic."""
        with _tmp() as tmp:
            root = build_repo(tmp, gate="T-1\n", tasks_json="{ not json")
            d = verdict(root, "src/a.py")
            self.assertTrue(d.refused)
            self.assertEqual(d.rule, "board-unreadable")
            # T-1058 (décision pilote) : `git restore` du seul TASKS.json détacherait ses fichiers d'intent.
            self.assertIn("`git stash push -u -- .agents/state/board/`", d.reason)
            self.assertNotIn("tasks.py list", d.reason)

    def test_malformed_journal_with_an_armed_gate_refuses(self):
        with _tmp() as tmp:
            root = build_repo(
                tmp,
                gate="T-1\n",
                tasks_json=board(task("T-1", "running", ["src/"])),
                specs_json="{ not json",
            )
            d = verdict(root, "src/a.py")
            self.assertTrue(d.refused)
            self.assertEqual(d.rule, "journal-unreadable")
            self.assertIn("git restore", d.reason)

    def test_unreadable_gate_refuses_because_the_repo_armed_something(self):
        gate = kg.GateReading(present=True, error="KICKOFF_REQUIRED cannot be read: boom")
        d = kg.decide("src/a.py", gate, kg.BoardReading(), kg.JournalReading())
        self.assertTrue(d.refused)
        self.assertEqual(d.rule, "gate-unreadable")

    def test_every_refusal_names_a_rule_from_the_closed_vocabulary(self):
        cases = [
            kg.decide("s/a", kg.GateReading(True, error="x"), kg.BoardReading(), kg.JournalReading()),
            kg.decide("s/a", kg.GateReading(True, ("T-1",)), kg.BoardReading(error="x"),
                      kg.JournalReading()),
            kg.decide("s/a", kg.GateReading(True, ("T-1",)), kg.BoardReading({}),
                      kg.JournalReading(error="x")),
            kg.decide("s/a", kg.GateReading(True, ("T-1",)), kg.BoardReading({}),
                      kg.JournalReading()),
        ]
        for d in cases:
            self.assertTrue(d.refused)
            self.assertIn(d.rule, kg.REFUSAL_RULES, d.reason)

    def test_unreadable_stdin_never_wedges_a_turn(self):
        class Exploding(io.StringIO):
            def read(self, *a, **k):
                raise OSError("stdin is gone")

        stdin, sys.stdin = sys.stdin, Exploding()
        try:
            self.assertEqual(kg.main(), 0)
        finally:
            sys.stdin = stdin

    def test_non_json_stdin_never_wedges_a_turn(self):
        self.assertEqual(_run_main("not json at all"), (0, "", ""))

    def test_empty_stdin_never_wedges_a_turn(self):
        self.assertEqual(_run_main(""), (0, "", ""))


# ---------------------------------------------------------------------------
# LA PISTE D'AUDIT — hook.deny, fail-open absolu
# ---------------------------------------------------------------------------


class AuditTrailTests(unittest.TestCase):
    def test_a_refusal_emits_one_hook_deny(self):
        seen: list[tuple] = []

        class Fake:
            @staticmethod
            def emit(kind, **fields):
                seen.append((kind, fields))

        real, kg._events = kg._events, Fake()
        try:
            kg._emit_event(REFUSAL, "src/a.py")
        finally:
            kg._events = real
        self.assertEqual(seen, [("hook.deny", {"guard": "kickoff", "rule": "not-running",
                                               "path": "src/a.py"})])

    def test_a_broken_event_channel_still_delivers_the_refusal(self):
        class Broken:
            @staticmethod
            def emit(kind, **fields):
                raise RuntimeError("the journal is on fire")

        real, kg._events = kg._events, Broken()
        try:
            kg._emit_event(REFUSAL, "src/a.py")  # must not raise
        finally:
            kg._events = real
        o, e = io.StringIO(), io.StringIO()
        rc = kg.emit_refusal(REFUSAL, "claude", out=o, err=e)
        out, err = o.getvalue(), e.getvalue()
        self.assertEqual(rc, 2)
        self.assertIn("BLOCKED by kickoff guard", err)

    def test_the_refusal_prose_never_reaches_the_audit_line(self):
        seen: list[tuple] = []

        class Fake:
            @staticmethod
            def emit(kind, **fields):
                seen.append((kind, fields))

        real, kg._events = kg._events, Fake()
        try:
            kg._emit_event(REFUSAL, "src/a.py")
        finally:
            kg._events = real
        self.assertNotIn("reason", seen[0][1])


# ---------------------------------------------------------------------------
# main() de bout en bout, avec une racine detournee
# ---------------------------------------------------------------------------


class MainTests(unittest.TestCase):
    def test_main_refuses_an_armed_write_on_claude(self):
        with _tmp() as tmp:
            root = build_repo(
                tmp,
                gate="T-1\n",
                tasks_json=board(task("T-1", "pending", ["src/"])),
                specs_json=journal("T-1"),
            )
            payload = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": "src/a.py"}})
            rc, out, err = _run_main(payload, root=root, host="claude")
            self.assertEqual(rc, 2)
            self.assertEqual(out, "")
            self.assertIn("BLOCKED by kickoff guard", err)

    def test_main_refuses_an_armed_write_on_codex_through_the_envelope(self):
        with _tmp() as tmp:
            root = build_repo(
                tmp,
                gate="T-1\n",
                tasks_json=board(task("T-1", "pending", ["src/"])),
                specs_json=journal("T-1"),
            )
            payload = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": "src/a.py"}})
            rc, out, err = _run_main(payload, root=root, host="codex")
            self.assertEqual(rc, 0)
            self.assertEqual(err, "")
            self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"], "deny")
            self.assertEqual(set(json.loads(out)), {"hookSpecificOutput"})

    def test_main_refuses_an_armed_write_on_copilot_in_both_forms(self):
        """T-01M4RWC0DBM6XC1PDQGEG4P79C : `main()` passe l'hote a l'enveloppe ;
        sous copilot, la decision de premier niveau egale l'imbriquee, rc 0."""
        with _tmp() as tmp:
            root = build_repo(
                tmp,
                gate="T-1\n",
                tasks_json=board(task("T-1", "pending", ["src/"])),
                specs_json=journal("T-1"),
            )
            payload = json.dumps({"toolName": "create", "toolArgs": {"path": "src/a.py"}})
            rc, out, err = _run_main(payload, root=root, host="copilot")
            self.assertEqual((rc, err), (0, ""))
            body = json.loads(out)
            nested = body["hookSpecificOutput"]
            self.assertEqual(nested["permissionDecision"], "deny")
            self.assertEqual(body.get("permissionDecision"), "deny")
            self.assertEqual(body.get("permissionDecisionReason"), nested["permissionDecisionReason"])
            self.assertEqual(out.strip(), kg.deny_envelope(nested["permissionDecisionReason"], "copilot"))

    def test_main_lets_a_read_through_even_on_an_armed_repo(self):
        with _tmp() as tmp:
            root = build_repo(
                tmp,
                gate="T-1\n",
                tasks_json=board(task("T-1", "pending", ["src/"])),
                specs_json=journal("T-1"),
            )
            payload = json.dumps({"tool_name": "Read", "tool_input": {"file_path": "src/a.py"}})
            self.assertEqual(_run_main(payload, root=root, host="claude"), (0, "", ""))

    def test_main_lets_a_conformant_write_through(self):
        with _tmp() as tmp:
            root = build_repo(
                tmp,
                gate="T-1\n",
                tasks_json=board(task("T-1", "running", ["src/"])),
                specs_json=journal("T-1"),
            )
            payload = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": "src/a.py"}})
            self.assertEqual(_run_main(payload, root=root, host="claude"), (0, "", ""))


# ---------------------------------------------------------------------------
# LA TRAVERSEE DE REPERTOIRE — securite classe 1, HIGH, non waivable
# ---------------------------------------------------------------------------
#
# LE DEFAUT, ET POURQUOI C'ETAIT UNE ASYMETRIE PLUTOT QU'UN OUBLI. Du cote des
# ENTREES de writeset, la discipline etait deja juste :
# `tasks.writeset_path_refusal` refuse `.` et `..`, et une entree inadmissible
# compte comme COUVRANTE, donc mene au refus (branche stricte, section 4). Du
# cote du CHEMIN ECRIT, un `..` produisait exactement l'effet INVERSE :
# `relative_to_root` ne normalisait que les chemins ABSOLUS (par effet de bord
# de `resolve()`), donc un chemin relatif gardait son `..` litteral,
# `writeset_covers` comparait des segments litteraux, ne couvrait rien, et
# `decide()` concluait « aucune tache armee ne couvre ce chemin -> passe, en
# silence » — alors que l'ecriture atterrissait REELLEMENT dans le perimetre
# protege, sans que le mandat (`running` + `kind=plan`) soit jamais verifie.
#
# La meme regle doit valoir DANS LES DEUX SENS, et c'est ce que ces tests
# epinglent. Le cas RELATIF est le plus probable en pratique : `apply_patch`
# (`*** Add File: <path>`) et les champs `target_file` / `path` des autres hotes
# transportent des chemins relatifs.


class TraversalTests(unittest.TestCase):
    """Le writeset `src/allowed/` d'une tache armee NON-`running` : toute
    ecriture qui atterrit dedans doit etre REFUSEE, quelle que soit la forme du
    chemin qui l'y mene."""

    def _armed_not_running(self, tmp: Path) -> Path:
        return build_repo(
            tmp,
            gate="T-1\n",
            tasks_json=board(task("T-1", "pending", ["src/allowed/"])),
            specs_json=journal("T-1"),
        )

    def test_relative_traversal_into_the_writeset_is_refused(self):
        """LE SCENARIO EXACT du constat de securite. Ce test ECHOUAIT sur le
        code d'avant le correctif : `src/other/../allowed/secret.py` passait en
        silence alors qu'il ecrit dans `src/allowed/`."""
        with _tmp() as tmp:
            root = self._armed_not_running(tmp)
            path = kg.relative_to_root(root, "src/other/../allowed/secret.py")
            self.assertEqual(path, "src/allowed/secret.py")
            d = verdict(root, path)
            self.assertTrue(d.refused, "a `..` must not smuggle a write past the mandate check")
            self.assertEqual(d.rule, "not-running")

    def test_absolute_twin_stays_refused(self):
        """Le jumeau absolu etait deja defendu — mais PAR ACCIDENT, par effet de
        bord de `resolve()`. Il doit le rester, maintenant par la regle."""
        with _tmp() as tmp:
            root = self._armed_not_running(tmp)
            absolute = str(root / "src" / "other" / ".." / "allowed" / "secret.py")
            path = kg.relative_to_root(root, absolute)
            self.assertEqual(path, "src/allowed/secret.py")
            d = verdict(root, path)
            self.assertTrue(d.refused)
            self.assertEqual(d.rule, "not-running")

    def test_windows_form_of_the_same_bypass_is_refused(self):
        with _tmp() as tmp:
            root = self._armed_not_running(tmp)
            path = kg.relative_to_root(root, r"src\other\..\allowed\secret.py")
            self.assertEqual(path, "src/allowed/secret.py")
            d = verdict(root, path)
            self.assertTrue(d.refused)
            self.assertEqual(d.rule, "not-running")

    def test_traversal_is_refused_end_to_end_through_main(self):
        with _tmp() as tmp:
            root = self._armed_not_running(tmp)
            payload = json.dumps(
                {"tool_name": "Edit",
                 "tool_input": {"file_path": "src/other/../allowed/secret.py"}}
            )
            rc, out, err = _run_main(payload, root=root, host="claude")
            self.assertEqual(rc, 2)
            self.assertIn("BLOCKED by kickoff guard", err)

    def test_apply_patch_marker_carries_the_same_traversal(self):
        """La forme la PLUS probable en pratique : `*** Add File:` porte un
        chemin relatif, donc c'est par la que la traversee arrive."""
        with _tmp() as tmp:
            root = self._armed_not_running(tmp)
            payload = json.dumps(
                {"tool_name": "apply_patch",
                 "tool_input": {"command": "*** Add File: src/other/../allowed/secret.py\n"}}
            )
            rc, out, err = _run_main(payload, root=root, host="claude")
            self.assertEqual(rc, 2)
            self.assertIn("BLOCKED by kickoff guard", err)

    def test_lexical_normalisation_folds_dot_and_double_dot(self):
        """PUREMENT LEXICAL : aucun `resolve()` sur du relatif, qui toucherait le
        disque et dependrait du cwd."""
        with _tmp() as tmp:
            root = build_repo(tmp)
            for raw, want in [
                ("src/other/../allowed/x.py", "src/allowed/x.py"),
                ("./src/allowed/x.py", "src/allowed/x.py"),
                ("src/./allowed/x.py", "src/allowed/x.py"),
                ("src//allowed/x.py", "src/allowed/x.py"),
                ("src/a/b/../../allowed/x.py", "src/allowed/x.py"),
                ("src/allowed/", "src/allowed"),
            ]:
                self.assertEqual(kg.relative_to_root(root, raw), want, raw)

    def test_normalised_traversal_is_covered_by_the_predicate(self):
        self.assertTrue(
            kg.writeset_covers("src/allowed/", "src/other/../allowed/secret.py")
        )
        self.assertTrue(
            kg.writeset_covers("src/allowed/", r"src\other\..\allowed\secret.py")
        )
        # La frontiere de segment survit a la normalisation.
        self.assertFalse(kg.writeset_covers("src/a", "src/x/../ab.py"))

    # --- LA BRANCHE STRICTE : ce qui s'echappe au-dessus de la racine --------

    def test_path_escaping_above_the_root_is_refused_never_silent(self):
        """Un garde qui ne peut pas ETABLIR le chemin refuse ; il ne rassure
        pas. Meme regle que la branche stricte deja appliquee aux entrees de
        writeset inadmissibles."""
        with _tmp() as tmp:
            root = self._armed_not_running(tmp)
            for raw in ("../outside.py", "../../etc/passwd", r"..\outside.py",
                        "src/../../escape.py"):
                path = kg.relative_to_root(root, raw)
                d = verdict(root, path)
                self.assertTrue(d.refused, raw)
                self.assertEqual(d.rule, "path-not-establishable", raw)

    def test_the_strict_path_rule_is_in_the_closed_vocabulary(self):
        self.assertIn("path-not-establishable", kg.REFUSAL_RULES)

    def test_escaping_path_is_refused_end_to_end_through_main(self):
        with _tmp() as tmp:
            root = self._armed_not_running(tmp)
            payload = json.dumps(
                {"tool_name": "Edit", "tool_input": {"file_path": "../../etc/passwd"}}
            )
            rc, out, err = _run_main(payload, root=root, host="claude")
            self.assertEqual(rc, 2)
            # La PROSE dit ce qui s'est passe ; l'id de regle vit dans la ligne
            # d'audit `hook.deny`, jamais dans le message lu par un humain.
            self.assertIn("BLOCKED by kickoff guard", err)
            self.assertIn("escapes above the repository root", err)

    def test_the_escaping_path_refusal_carries_its_rule_to_the_audit_line(self):
        seen: list[tuple] = []

        class Fake:
            @staticmethod
            def emit(kind, **fields):
                seen.append((kind, fields))

        with _tmp() as tmp:
            root = self._armed_not_running(tmp)
            payload = json.dumps(
                {"tool_name": "Edit", "tool_input": {"file_path": "../../etc/passwd"}}
            )
            real, kg._events = kg._events, Fake()
            try:
                _run_main(payload, root=root, host="claude")
            finally:
                kg._events = real
        self.assertEqual(seen[0][0], "hook.deny")
        self.assertEqual(seen[0][1]["guard"], "kickoff")
        self.assertEqual(seen[0][1]["rule"], "path-not-establishable")

    def test_absolute_path_outside_the_root_still_passes(self):
        """Il n'est pas « inetablissable » : il est ETABLI, et etabli HORS du
        depot, donc aucun writeset relatif ne peut le couvrir. Le distinguer du
        cas precedent est ce qui evite de refuser une ecriture legitime dans un
        repertoire temporaire."""
        with _tmp() as tmp:
            root = self._armed_not_running(tmp)
            outside = str((root.parent / "elsewhere" / "x.py").resolve())
            self.assertEqual(kg.relative_to_root(root, outside), "")
            payload = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": outside}})
            self.assertEqual(_run_main(payload, root=root, host="claude"), (0, "", ""))

    # --- NON-REGRESSION : le correctif ne change RIEN pour un depot desarme --

    def test_disarmed_repo_stays_silent_on_every_traversal_form(self):
        """LE TEST QUI GARANTIT QU'ON N'A PAS TRANSFORME LA CORRECTION EN
        CHANGEMENT DE COMPORTEMENT POUR TOUT LE MONDE. Un depot qui n'a rien
        arme reste a rc 0 et zero octet, y compris sur ces chemins-la."""
        with _tmp() as tmp:
            root = build_repo(tmp, tasks_json=board(task("T-1", "pending", ["src/allowed/"])))
            for raw in ("src/other/../allowed/secret.py", "../../etc/passwd",
                        r"src\other\..\allowed\secret.py", "../outside.py"):
                payload = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": raw}})
                self.assertEqual(_run_main(payload, root=root, host="claude"), (0, "", ""), raw)
                self.assertEqual(_run_main(payload, root=root, host="codex"), (0, "", ""), raw)

    def test_armed_but_uncovered_traversal_still_passes(self):
        """La normalisation ne doit pas ELARGIR le refus : un chemin qui, une
        fois normalise, tombe hors de tout writeset arme passe toujours."""
        with _tmp() as tmp:
            root = self._armed_not_running(tmp)
            path = kg.relative_to_root(root, "docs/sub/../x.md")
            self.assertEqual(path, "docs/x.md")
            self.assertTrue(verdict(root, path).allowed)


# ---------------------------------------------------------------------------
# LE FOCUS DU CLONE (T-01M5F728WZ89DF8PV79SDWEFE4) — un running etranger ne couvre pas
# ---------------------------------------------------------------------------

PLAN_P = "docs/tasks/T-10-plan.md"


def fournee_board() -> dict:
    """Parent T-10, deux lots (T-11 sur src/, T-12 sur lib/), un running ETRANGER T-20 sur docs/."""
    return board(
        task("T-10", "running", [PLAN_P], fournee={"lots": ["T-11", "T-12"], "plan": PLAN_P}),
        task("T-11", "running", ["src/"], fournee={"parent": "T-10", "lot": "A", "plan": PLAN_P}),
        task("T-12", "running", ["lib/"], fournee={"parent": "T-10", "lot": "B", "plan": PLAN_P}),
        task("T-20", "running", ["docs/"]),
    )


def poser_focus(root: Path, tid: str | None, brut: str | None = None) -> None:
    local = root / ".agents" / "state" / "local"
    local.mkdir(parents=True, exist_ok=True)
    body = brut if brut is not None else json.dumps({"task_id": tid, "updated_at": "2026-10-21T00:00:00Z"})
    (local / "focus.json").write_text(body, encoding="utf-8")


def fournee_repo(tmp: Path) -> Path:
    return build_repo(
        tmp,
        gate="T-10\nT-11\nT-12\nT-20\n",
        tasks_json=fournee_board(),
        specs_json=journal("T-10", "T-11", "T-12", "T-20"),
    )


class FocusTests(unittest.TestCase):
    def test_foreign_running_cannot_cover_path(self):
        """Le running d'un COLLEGUE (T-20, conforme : running + plan + couvrant) ne
        donne pas mandat a CE clone, dont le focus est la fournee T-10."""
        with _tmp() as tmp:
            root = fournee_repo(tmp)
            # Sans focus.json, DEUX familles en vol (T-10 et T-20) : refus focus-missing,
            # comme 7407b2fee refusait ce board (board-unreadable), jamais un passage.
            d = verdict(root, "docs/x.md")
            self.assertEqual(d.rule, "focus-missing", d)
            self.assertIn("tasks.py focus T-20", d.reason)
            poser_focus(root, "T-10")
            d = verdict(root, "docs/x.md")
            self.assertTrue(d.refused, d)
            self.assertEqual(d.rule, "foreign-running")
            self.assertIn("T-20", d.reason)
            self.assertIn("tasks.py focus T-20", d.reason)
            # Le parent focalise et ses lots gardent leur mandat.
            for path in (PLAN_P, "src/a.py", "lib/b.py"):
                self.assertTrue(verdict(root, path).allowed, path)

    def test_focused_lot_admits_its_parent_and_sibling_lots(self):
        with _tmp() as tmp:
            root = fournee_repo(tmp)
            poser_focus(root, "T-11")
            for path in (PLAN_P, "src/a.py", "lib/b.py"):
                self.assertTrue(verdict(root, path).allowed, path)
            self.assertEqual(verdict(root, "docs/x.md").rule, "foreign-running")
            self.assertEqual(kg.fournee_du_focus(kg.collect(root, kg.read_gate(root))[0]),
                             frozenset({"T-10", "T-11", "T-12"}))

    def test_focus_never_widens_and_other_refusals_stand(self):
        """Le focus RETIRE des mandats, jamais n'en ajoute : un focus non planifie
        reste `no-plan`, un focus `pending` reste `not-running`."""
        with _tmp() as tmp:
            root = build_repo(
                tmp,
                gate="T-1\n",
                tasks_json=board(task("T-1", "running", ["src/"])),
                specs_json=journal(),
            )
            poser_focus(root, "T-1")
            self.assertEqual(verdict(root, "src/a.py").rule, "no-plan")
            build_repo(tmp, tasks_json=board(task("T-1", "pending", ["src/"])), specs_json=journal("T-1"))
            self.assertEqual(verdict(root, "src/a.py").rule, "not-running")
            self.assertTrue(verdict(root, "docs/x.md").allowed)

    def test_single_family_without_focus_keeps_the_old_rule(self):
        """Ancien adoptant : sans focus.json, UNE seule famille en vol — une running
        seule, une fournee (parent + lots), ou un parallel_group partage — passe."""
        with _tmp() as tmp:
            seule = board(task("T-1", "running", ["src/"]))
            fournee = board(*[t for t in fournee_board()["tasks"] if t["id"] != "T-20"])
            groupe = board(task("T-1", "running", ["src/"], parallel_group="G-1"),
                           task("T-2", "running", ["lib/"], parallel_group="G-1"))
            for b in (seule, fournee, groupe):
                root = build_repo(tmp, gate="T-1\nT-2\nT-10\nT-11\nT-12\n", tasks_json=b,
                                  specs_json=journal("T-1", "T-2", "T-10", "T-11", "T-12"))
                path = "src/a.py"
                self.assertTrue(verdict(root, path).allowed, b)
                self.assertEqual(kg.familles_running(kg.collect(root, kg.read_gate(root))[0]), 1)

    def test_two_families_without_focus_refuse_focus_missing(self):
        """Deux running sans groupe commun (ou deux groupes) et aucun focus : refus."""
        with _tmp() as tmp:
            for extra in ({}, {"parallel_group": "G-2"}):
                root = build_repo(
                    tmp,
                    gate="T-1\n",
                    tasks_json=board(task("T-1", "running", ["src/"], parallel_group="G-1"),
                                     task("T-2", "running", ["lib/"], **extra)),
                    specs_json=journal("T-1", "T-2"),
                )
                d = verdict(root, "src/a.py")
                self.assertEqual(d.rule, "focus-missing", d)
                self.assertIn(d.rule, kg.REFUSAL_RULES)
                # Hors de toute couverture : le passage silencieux est inchange.
                self.assertTrue(verdict(root, "docs/x.md").allowed)

    def test_lot_regrouped_with_a_foreign_task_bridges_nothing(self):
        """S3 : fournee T-100 (PG-0001), son lot T-101 regroupe en PG-0002 avec un
        etranger T-200 par `tasks.py parallel`. Sans focus, le chemin de T-200 rend
        focus-missing — aucune union transitive entre deux groupes non lies. S5 : un
        lot qui a PERDU son groupe, seule fournee en vol, reste admis."""
        plan = "docs/tasks/T-100-plan.md"
        lien = {"plan": plan}
        with _tmp() as tmp:
            s3 = board(
                task("T-100", "running", [plan], parallel_group="PG-0001", fournee={"lots": ["T-101", "T-102"], **lien}),
                task("T-101", "running", ["src/a.py"], parallel_group="PG-0002",
                     fournee={"parent": "T-100", "lot": "A", **lien}),
                task("T-102", "running", ["lib/b.py"], parallel_group="PG-0001",
                     fournee={"parent": "T-100", "lot": "B", **lien}),
                task("T-200", "running", ["tools/g.py"], parallel_group="PG-0002"),
            )
            root = build_repo(tmp, gate="T-100\nT-200\n", tasks_json=s3,
                              specs_json=journal("T-100", "T-101", "T-102", "T-200"))
            self.assertEqual(verdict(root, "tools/g.py").rule, "focus-missing")
            s5 = board(*[t for t in s3["tasks"] if t["id"] != "T-200"])
            del s5["tasks"][1]["parallel_group"]
            root = build_repo(tmp, gate="T-100\nT-101\n", tasks_json=s5,
                              specs_json=journal("T-100", "T-101", "T-102"))
            self.assertTrue(verdict(root, "src/a.py").allowed)

    def test_empty_focus_task_id_is_never_read_as_absent(self):
        with _tmp() as tmp:
            root = build_repo(tmp, gate="T-1\n", tasks_json=board(task("T-1", "running", ["src/"])),
                              specs_json=journal("T-1"))
            poser_focus(root, "  ")
            d = verdict(root, "src/a.py")
            self.assertEqual(d.rule, "focus-unreadable", d)
            self.assertIn("task_id vide", d.reason)

    def test_unreadable_focus_refuses_a_conforming_cover(self):
        with _tmp() as tmp:
            root = fournee_repo(tmp)
            poser_focus(root, None, brut="{not json")
            d = verdict(root, "src/a.py")
            self.assertEqual(d.rule, "focus-unreadable")
            self.assertIn("tasks.py focus", d.reason)
            self.assertIn(d.rule, kg.REFUSAL_RULES)

    def test_focus_read_from_main_repo_without_fork(self):
        """Un worktree (``.git`` FICHIER -> ``commondir``, lien retour ``gitdir``) lit le
        focus du depot PRINCIPAL, sans sous-processus ; hors Git, il retombe sur sa racine."""
        with _tmp() as tmp:
            main_repo, wt = tmp / "main", tmp / "wt"
            gitdir = main_repo / ".git" / "worktrees" / "wt"
            gitdir.mkdir(parents=True)
            (gitdir / "commondir").write_text("../..\n", encoding="utf-8")
            root = fournee_repo(wt)
            (root / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")
            (gitdir / "gitdir").write_text(f"{root / '.git'}\n", encoding="utf-8")  # lien retour d'un VRAI worktree
            poser_focus(main_repo, "T-10")
            with mock.patch.object(subprocess, "Popen", side_effect=AssertionError("fork")):
                self.assertEqual(verdict(root, "docs/x.md").rule, "foreign-running")
            self.assertEqual(kg.repo_root(), REPO)

    def test_disarmed_repo_never_reads_the_focus(self):
        with _tmp() as tmp:
            root = build_repo(tmp, tasks_json=fournee_board(), specs_json=journal())
            poser_focus(root, None, brut="{not json")
            with mock.patch.object(kg.tasks, "lire_focus") as lecture:
                b, _ = kg.collect(root, kg.read_gate(root))
                self.assertEqual((b.focus, b.focus_error), ("", ""))
                self.assertTrue(verdict(root, "src/a.py").allowed)
            lecture.assert_not_called()


# ---------------------------------------------------------------------------
# Petits utilitaires de test
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def _tmp():
    with tempfile.TemporaryDirectory() as name:
        yield Path(name).resolve()


def _run_main(payload: str, root: Path | None = None, host: str | None = None):
    """`main()` en processus, racine et marqueur d'hote detournes."""
    out, err = io.StringIO(), io.StringIO()
    saved = (sys.stdin, sys.stdout, sys.stderr, kg.repo_root, os.environ.get("AGENTS_HOOK_HOST"))
    sys.stdin, sys.stdout, sys.stderr = io.StringIO(payload), out, err
    if root is not None:
        kg.repo_root = lambda: root  # type: ignore[assignment]
    if host is not None:
        os.environ["AGENTS_HOOK_HOST"] = host
    else:
        os.environ.pop("AGENTS_HOOK_HOST", None)
    try:
        rc = kg.main()
    finally:
        sys.stdin, sys.stdout, sys.stderr, kg.repo_root = saved[0], saved[1], saved[2], saved[3]
        if saved[4] is None:
            os.environ.pop("AGENTS_HOOK_HOST", None)
        else:
            os.environ["AGENTS_HOOK_HOST"] = saved[4]
    return rc, out.getvalue(), err.getvalue()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
