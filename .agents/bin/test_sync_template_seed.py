#!/usr/bin/env python3
"""THE SEED CHANNEL OF sync_template.py — its witnesses, hermetic.

Run: python -m pytest .agents/bin/test_sync_template_seed.py -q

`.agents/state/` is `strip:`, so the kit's own state never reaches the template.
Four gate markers must reach an adopter ARMED all the same: the source carries
their SEEDS under `.agents/adopter-seed/gates/`, and the sync writes each one to
`.agents/state/gates/` on the template — from the source's blob, never from the
kit's own markers, staged by name, verified in the index as well as on disk.

A NEW MODULE, NOT AN AMENDMENT: `test_sync_template.py` is left untouched, and its
fixtures (a source with no seed, a template with no marker) are the witness that
the channel changes nothing for a project that does not use it (W8).

Every case builds its own throw-away repo through `make_repo` (imported, never
re-written): nothing here reads or writes the real repository, so the module
travels and passes in an adopting tree as well.

Each witness names, in its comment, the mutant it was written to kill; every
mutant was replayed on a throw-away copy of the script and turned it red.
"""
from __future__ import annotations

import io
import os
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import test_sync_template as T  # noqa: E402 — needs the path inserted above

st = T.st
_git, make_repo = T._git, T.make_repo
_APPLY_OK = T._APPLY_OK

SRC = ".agents/adopter-seed/gates/"
DST = ".agents/state/gates/"
# THE LITERAL SET: four seeds, never derived from the script under test.
SEEDS = {
    SRC + "BINOME_REQUIRED": "# seed binome\n",
    SRC + "CHRONO_REQUIRED": "# seed chrono\n",
    SRC + "PLAN_CHAIN_REQUIRED": "# seed chain\n",
    SRC + "PLAN_CIBLE_REQUIRED": "# seed cible\nspec=docs/PROMPT-projet.md\nchantier=*\n",
}
DESTS = sorted(DST + k[len(SRC):] for k in SEEDS)
EXC = "strip: .agents/state/\nstrip: .agents/adopter-seed/\nown: TEMPLATE.md\n"


def _count(report: str, header: str) -> str:
    """The `<n>` of `<header> — <n> path(s)` in a report."""
    return report.split(f"{header} —")[1].split("path(s)")[0].strip()


class SeedTests(T.SyncTemplateTestCase):

    # -- fixtures -------------------------------------------------------------

    def _repo(self, extra_main=None, template=None, exclude=EXC):
        main = {"README.md": "hello\n", "TEMPLATE.md": "t\n", **SEEDS, **(extra_main or {})}
        make_repo(self.root, main_files=main,
                  template_files={"README.md": "hello\n", "TEMPLATE.md": "t\n",
                                  **(template or {})},
                  exclude_text=exclude)
        _git(self.root, "checkout", "-q", "template/starter-kit")

    def _source_without(self, drop):
        """A template SEEDED with old bytes for the four markers, and a source
        from which `drop` (seed paths, or the whole mirror) was removed."""
        self._repo(template={d: "# old\n" for d in DESTS})
        _git(self.root, "checkout", "-q", "main")
        _git(self.root, "rm", "-rq", "--", *drop)
        _git(self.root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "retire")
        _git(self.root, "checkout", "-q", "template/starter-kit")

    def _staged(self):
        out = _git(self.root, "ls-files", "-s", "--", DST).stdout.splitlines()
        return {line.split("\t")[1]: line.split()[1] for line in out}

    def _plan(self):
        main_paths = st.list_tree(self.root, "main")
        tpl = st.list_tree(self.root, "refs/heads/template/starter-kit")
        rules = st.parse_exclude(st.read_exclude(self.root, "main"))
        return main_paths, st.build_plan(main_paths, tpl, rules, source_label="main")

    def _planned(self, src):
        return _git(self.root, "rev-parse", f"main:{src}").stdout.strip()

    # -- content and survival -------------------------------------------------

    def test_W1_seed_content_comes_from_the_mirror_never_from_the_kit_state(self):
        # kills M1 (seed read from the kit's own state) and M2 (read from disk)
        self._repo(extra_main={DST + "BINOME_REQUIRED": "# KIT STATE\n"})
        code, out, err = self.run_main(list(_APPLY_OK))
        self.assertEqual(code, 0, err + out)
        self.assertEqual((self.root / DST / "BINOME_REQUIRED").read_text(encoding="utf-8"),
                         "# seed binome\n")

    def test_W2_a_seeded_path_survives_the_strip(self):
        # kills M3 (the strip rule judged before the seed)
        self._repo(template={DST + k[len(SRC):]: v for k, v in SEEDS.items()})
        code, out, err = self.run_main(["--check"])
        self.assertEqual(code, 0, err)
        self.assertEqual(_count(out, "DELETE"), "0", out)
        self.assertEqual(_count(out, "SEED"), "4", out)
        for d in DESTS:
            self.assertIn(f"= {d}", out)

    def test_W3a_ONE_seed_removed_from_the_source_is_deleted_and_not_refused(self):
        # kills M4 (a seed destination shielded from DELETE)
        self._source_without([SRC + "PLAN_CHAIN_REQUIRED"])
        code, out, err = self.run_main(["--check"])
        self.assertEqual(code, 0, err)
        self.assertEqual(_count(out, "DELETE"), "1", out)
        self.assertIn(f"- {DST}PLAN_CHAIN_REQUIRED  (strip: .agents/state/)", out)
        self.assertEqual(_count(out, "SEED"), "3", out)

    def test_W3b_TWO_seeds_of_three_removed_pass_too_the_refusal_needs_zero(self):
        """« of three » in the name is historical (T-00001093): the seed set holds FOUR since
        T-01M55Z3ZCS34CDR2EQN1CEBHR7 — the name is kept, docs/tasks cite it."""
        # the refusal (23) bites on ZERO seed, never on fewer — two of the four removed here,
        # the N-1 case of the four-seed set is W3c
        self._source_without([SRC + "PLAN_CHAIN_REQUIRED", SRC + "BINOME_REQUIRED"])
        code, out, err = self.run_main(["--check"])
        self.assertEqual(code, 0, err)
        self.assertEqual(_count(out, "DELETE"), "2", out)
        self.assertEqual(_count(out, "SEED"), "2", out)
        self.assertNotIn("UNSEEDING", err)

    def test_W3c_THREE_seeds_of_four_removed_pass_too_the_refusal_needs_zero(self):
        # the N-1 rule, pinned on the four-seed set: ONE seed left is no refusal (23)
        self._source_without([SRC + "PLAN_CHAIN_REQUIRED", SRC + "BINOME_REQUIRED",
                              SRC + "CHRONO_REQUIRED"])
        code, out, err = self.run_main(["--check"])
        self.assertEqual(code, 0, err)
        self.assertEqual(_count(out, "DELETE"), "3", out)
        self.assertIn(f"- {DST}CHRONO_REQUIRED  (strip: .agents/state/)", out)
        self.assertEqual(_count(out, "SEED"), "1", out)
        self.assertNotIn("UNSEEDING", err)

    def test_W20_a_destination_on_neither_ref_is_not_dropped(self):
        # kills M20 (the plan loop over the two refs only): the kit carries
        # BINOME_REQUIRED, neither ref carries PLAN_CHAIN_REQUIRED — the real case
        self._repo(extra_main={DST + "BINOME_REQUIRED": "# KIT\n"})
        code, out, err = self.run_main(["--check"])
        self.assertEqual(code, 0, err)
        self.assertEqual(_count(out, "SEED"), "4", out)
        self.assertIn(f"+ {DST}PLAN_CHAIN_REQUIRED", out)
        self.assertIn(f"+ {DST}CHRONO_REQUIRED", out)

    # -- configuration errors (17) -------------------------------------------

    def test_W5_a_seed_source_outside_every_strip_rule_is_a_config_error(self):
        # kills M7 (the source clause removed)
        self._repo(exclude="strip: .agents/state/\nown: TEMPLATE.md\n")
        code, _out, err = self.run_main(["--check"])
        self.assertEqual(code, st.EXIT_CONFIG_ERROR, err)
        self.assertIn("seed source", err)

    def test_W6_a_destination_outside_the_closed_gates_root_is_a_config_error(self):
        # kills M8 (the closed root removed): a seed aimed at the board
        self._repo(extra_main={".agents/adopter-seed/board/TASKS.json": "{}\n"})
        code, _out, err = self.run_main(["--check"])
        self.assertEqual(code, st.EXIT_CONFIG_ERROR, err)
        self.assertIn("outside the closed root", err)

    def test_W6b_a_destination_outside_every_strip_rule_is_a_config_error(self):
        # kills MW6b (the destination clause removed)
        self._repo(exclude="strip: .agents/adopter-seed/\nown: TEMPLATE.md\n")
        code, _out, err = self.run_main(["--check"])
        self.assertEqual(code, st.EXIT_CONFIG_ERROR, err)
        self.assertIn("seed destination", err)

    def test_W25_a_seed_destination_with_a_parent_component_is_a_config_error(self):
        # kills MS5 (the `..` refusal removed): `gates/../board/TASKS.json` STARTS
        # with the closed root yet lands on the board (advisory 1, S-00003711).
        # Synthetic paths: a git tree never carries `..`, a crafted one could.
        rules, sha = st.parse_exclude(EXC), "0" * 40
        for rel in ("../board/TASKS.json", "../../../outside", "x/../../board/TASKS.json"):
            with self.subTest(rel=rel):
                with self.assertRaises(st.ConfigError) as cm:
                    st.build_plan({"TEMPLATE.md": sha, SRC + rel: sha}, {"TEMPLATE.md": sha}, rules)
                self.assertIn("'..'", str(cm.exception))
        st.build_plan({"TEMPLATE.md": sha, SRC + "BINOME_REQUIRED": sha}, {"TEMPLATE.md": sha}, rules)

    def _tracked_link(self, rel, target):
        """The template TRACKS `rel` as a symbolic link to `target`, committed."""
        (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
        try:
            os.symlink(target, self.root / rel)
        except (OSError, NotImplementedError) as exc:
            raise unittest.SkipTest(f"no symbolic link here: {exc}") from exc
        _git(self.root, "add", "--", rel)
        _git(self.root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "link")

    def test_W26a_apply_never_writes_a_seed_through_a_linked_parent(self):
        # kills MS6 (the link refusal removed): without it the seed lands in
        # `outside/` BEFORE `git add` refuses the path (advisory 2, S-00003711)
        outside = self.root.parent / "outside"
        outside.mkdir()
        self._repo()
        self._tracked_link(DST.rstrip("/"), outside)
        code, out, err = self.run_main(list(_APPLY_OK))
        self.assertNotEqual(code, 0, err + out)
        self.assertEqual(sorted(outside.iterdir()), [])
        self.assertIn("symbolic link", err)

    def test_W26b_apply_never_writes_a_seed_through_a_linked_leaf(self):
        # kills MS6b (the leaf left out of the walk): `write_bytes` follows a
        # link at the destination itself
        outside = self.root.parent / "outside.txt"
        outside.write_text("ORIGINAL\n", encoding="utf-8")
        self._repo()
        self._tracked_link(DST + "BINOME_REQUIRED", outside)
        code, out, err = self.run_main(list(_APPLY_OK))
        self.assertNotEqual(code, 0, err + out)
        self.assertEqual(outside.read_text(encoding="utf-8"), "ORIGINAL\n")
        self.assertIn("symbolic link", err)

    # -- the report -----------------------------------------------------------

    def test_W7_check_is_byte_identical_from_either_checkout_and_SEED_follows_FROZEN(self):
        # kills M9 (SEED printed before DELETE: callers slice on those headers)
        self._repo()
        code, on_template, err = self.run_main(["--check"])
        self.assertEqual(code, 0, err)
        _git(self.root, "checkout", "-q", "main")
        code2, on_main, err2 = self.run_main(["--check"])
        self.assertEqual(code2, 0, err2)
        self.assertEqual(on_template, on_main)
        self.assertLess(on_template.index("FROZEN/OWN"), on_template.index("SEED —"))
        self.assertLess(on_template.index("DELETE —"), on_template.index("SEED —"))
        self.assertNotIn("git add", on_template)

    def test_W23_check_writes_neither_a_file_nor_an_index_entry(self):
        # kills MS3 (`--check` writing the seeds)
        self._repo()
        code, _out, err = self.run_main(["--check"])
        self.assertEqual(code, 0, err)
        self.assertEqual(_git(self.root, "status", "--porcelain").stdout, "")
        for d in DESTS:
            self.assertFalse((self.root / d).exists(), d)

    # -- apply: index, disk, checkout back ------------------------------------

    def test_W17_apply_leaves_each_seed_tracked_with_the_planned_blob(self):
        # kills M18 (the `git add` gesture removed) and M18+M21
        self._repo()
        code, out, err = self.run_main(list(_APPLY_OK))
        self.assertEqual(code, 0, err + out)
        staged = self._staged()
        self.assertEqual(sorted(staged), DESTS)
        for src in SEEDS:
            self.assertEqual(staged[DST + src[len(SRC):]], self._planned(src))
        self.assertNotIn("?? .agents/state", _git(self.root, "status", "--porcelain").stdout)
        # what the operator's commit ships is the tree of the index
        tree = _git(self.root, "write-tree").stdout.strip()
        shipped = _git(self.root, "ls-tree", "-r", "--name-only", tree, "--",
                       ".agents/state/").stdout.split()
        self.assertEqual(sorted(shipped), DESTS)

    def test_W18_the_kit_is_never_armed_by_the_sync(self):
        # kills M18 and M18+M21: an untracked seed would REFUSE the checkout back
        self._repo(extra_main={DST + "BINOME_REQUIRED": "# KIT STATE\n"})
        code, out, err = self.run_main(list(_APPLY_OK))
        self.assertEqual(code, 0, err + out)
        _git(self.root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "sync")
        back = _git(self.root, "checkout", "main", check=False)
        self.assertEqual(back.returncode, 0, back.stderr)
        self.assertFalse((self.root / DST / "PLAN_CHAIN_REQUIRED").exists())
        self.assertEqual((self.root / DST / "BINOME_REQUIRED").read_text(encoding="utf-8"),
                         "# KIT STATE\n")
        self.assertEqual(_git(self.root, "status", "--porcelain").stdout, "")

    def test_W21_apply_rewrites_and_stages_a_seed_whose_bytes_changed(self):
        # kills MS1 (an `overwrite` seed left as it was)
        self._repo(template={d: "# OLD seed bytes\n" for d in DESTS})
        code, out, err = self.run_main(list(_APPLY_OK))
        self.assertEqual(code, 0, err + out)
        staged = self._staged()
        for src, text in SEEDS.items():
            dest = DST + src[len(SRC):]
            self.assertEqual((self.root / dest).read_text(encoding="utf-8"), text)
            self.assertEqual(staged[dest], self._planned(src))
        names = _git(self.root, "diff", "--cached", "--name-status", "--", ".agents/state/").stdout.split()
        self.assertEqual(names.count("M"), 4, names)

    def test_W4p_verify_manifest_demands_the_index_not_only_the_disk(self):
        # kills M21 (the seed branch of the verification reduced to the disk)
        self._repo()
        main_paths, plan = self._plan()
        for dest, src, _state in plan.seed:
            target = self.root / dest
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(st.read_blob(self.root, main_paths[src]))
        failures = st.verify_manifest(self.root, st.build_manifest(plan))
        self.assertEqual(len([f for f in failures if "seed expected staged blob" in f]), 4,
                         failures)

    def test_W22_recovery_names_each_NEW_seed_only_and_speaks_to_the_operator(self):
        # kills MS2 (the recovery forgetting the new seeds)
        self._repo(template={DESTS[0]: "# OLD\n"})  # one overwrite, three new
        _main_paths, plan = self._plan()
        buf = io.StringIO()
        st.print_recovery(plan, buf)
        text = buf.getvalue()
        for d in DESTS[1:]:
            self.assertIn(f"rm -- {d}", text)
        self.assertNotIn(f"rm -- {DESTS[0]}", text)
        self.assertIn("for the OPERATOR at a terminal", text)

    # -- the refusal 23 and its single exit ----------------------------------

    def test_W24a_a_source_without_mirror_on_a_seeded_template_is_REFUSED(self):
        # kills MU (the refusal call removed)
        self._source_without([".agents/adopter-seed"])
        before = _git(self.root, "status", "--porcelain").stdout
        for mode in (["--check"], list(_APPLY_OK)):
            with self.subTest(mode=mode[0]):
                code, out, err = self.run_main(mode)
                self.assertEqual(code, st.EXIT_REFUSED_UNSEEDING, err + out)
                self.assertIn("--allow-unseeding", err)
                self.assertNotIn("DELETE —", out)  # no report that reads as the truth
                self.assertEqual(_git(self.root, "status", "--porcelain").stdout, before)
                for d in DESTS:
                    self.assertEqual((self.root / d).read_text(encoding="utf-8"), "# old\n")

    def test_W24b_allow_unseeding_lifts_23_in_check(self):
        # kills MU2 (the flag ignored)
        self._source_without([".agents/adopter-seed"])
        code, out, err = self.run_main(["--check", "--allow-unseeding"])
        self.assertEqual(code, 0, err)
        self.assertEqual(_count(out, "DELETE"), "4", out)
        self.assertEqual(_count(out, "SEED"), "0", out)
        self.assertIn("UNSEEDING (--allow-unseeding)", err)

    def test_W24c_allow_unseeding_lifts_23_in_apply_and_the_markers_are_gone(self):
        # kills MU2b (the flag honoured in `--check` only): the exit is the
        # rollback path, so it is witnessed in the mode where it ACTS
        self._source_without([".agents/adopter-seed"])
        code, out, err = self.run_main([*_APPLY_OK, "--allow-unseeding"])
        self.assertEqual(code, 0, err + out)
        self.assertIn("UNSEEDING", err)
        for d in DESTS:
            self.assertFalse((self.root / d).exists(), d)
        self.assertEqual(_git(self.root, "ls-files", "--", ".agents/state").stdout, "")


if __name__ == "__main__":
    unittest.main()
