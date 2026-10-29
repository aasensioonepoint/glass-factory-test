"""Witnesses for the closed DOCS channel and its separate report section."""

from __future__ import annotations

import argparse
import io
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

import test_sync_template as fixtures
import sync_template_docs as docs

st = fixtures.st

RULES = st.parse_exclude("strip: .agents/adopter-docs/\nstrip: .agents/state/\n")
SOURCE = ".agents/adopter-docs/README.md"
DEST = "README.md"


def test_build_plan_ecrit_les_docs():
    plan = st.build_plan({SOURCE: "source", DEST: "kit"}, {DEST: "ancien"}, RULES)
    assert plan.docs == [(DEST, SOURCE, "overwrite")]
    assert plan.take_overwrite == []
    out = io.StringIO()
    # The report's diff reader needs a repository only when TAKE overwrites.
    st.print_report(None, plan, out)
    assert "SEED — 0 path(s)" in out.getvalue()
    assert "DOCS — 1 path(s)" in out.getvalue()


@pytest.mark.parametrize("main,rules", [
    ({SOURCE: "source"}, st.parse_exclude("")),
    ({SOURCE: "source"}, st.parse_exclude("strip: .agents/adopter-docs/\nstrip: README.md\n")),
    ({".agents/adopter-docs/AUTRE.md": "source"}, RULES),
])
def test_canal_docs_refuse_les_mauvaises_regles(main, rules):
    with pytest.raises(st.ConfigError):
        st.build_plan(main, {}, rules)


def test_docs_ne_levent_pas_le_refus_des_graines():
    marker = ".agents/state/gates/BINOME_REQUIRED"
    plan = st.build_plan({SOURCE: "source"}, {marker: "old"}, RULES)
    assert plan.docs and not plan.seed
    with pytest.raises(st.Refusal) as error:
        st._refuse_if_unseeding(plan, argparse.Namespace(allow_unseeding=False))
    assert error.value.code == st.EXIT_REFUSED_UNSEEDING


class DocsApplyTests(fixtures.SyncTemplateTestCase):
    def test_apply_ecrit_et_stage_la_source(self):
        fixtures.make_repo(
            self.root,
            main_files={SOURCE: "adoptant\n", DEST: "kit\n"},
            template_files={DEST: "ancien\n"},
            exclude_text="strip: .agents/adopter-docs/\n",
        )
        fixtures._git(self.root, "checkout", "-q", "template/starter-kit")
        code, out, err = self.run_main(["--apply", "--source", "main",
                                        "--allow-stale-source", "--allow-stale-template",
                                        "--allow-foreign-source"])
        assert code == 0, err + out
        assert (self.root / DEST).read_text(encoding="utf-8") == "adoptant\n"
        staged = fixtures._git(self.root, "show", ":README.md").stdout
        assert staged == "adoptant\n"

    def test_fraicheur_apres_vrai_apply_avec_sources_strip(self):
        sources = {
            "README.md": "# Adoptant\n",
            "CHANGELOG.md": "## 1.0.0 — 2026-10-23\n",
            "docs/usage.html": "<html>usage</html>\n",
        }
        main_files = {docs.SOURCE + destination: content
                      for destination, content in sources.items()}
        fixtures.make_repo(
            self.root, main_files=main_files,
            template_files={destination: "ancien\n" for destination in sources},
            exclude_text="strip: .agents/adopter-docs/\n",
        )
        source_sha = fixtures._git(self.root, "rev-parse", "main").stdout.strip()
        fixtures._git(self.root, "checkout", "-q", "template/starter-kit")
        code, out, err = self.run_main([
            "--apply", "--source", "main", "--allow-stale-source",
            "--allow-stale-template", "--allow-foreign-source",
        ])
        assert code == 0, err + out
        fixtures._commit_all(self.root, st.sync_subject("main", source_sha))
        published = fixtures._git(self.root, "rev-parse", "HEAD").stdout.strip()
        assert fixtures._git(self.root, "ls-tree", "-r", "--name-only", published,
                             "--", docs.SOURCE).stdout == ""
        tag = "template/v1.0.0-2026-10-23"
        code, message = docs.fraicheur(self.root, published, tag, "main")
        assert code == 0, message

        fixtures._git(self.root, "checkout", "-q", "main")
        (self.root / docs.SOURCE / "README.md").write_text(
            "# Source modifiée\n", encoding="utf-8")
        fixtures._commit_all(self.root, "source après ancre")
        code, message = docs.fraicheur(self.root, published, tag, "main")
        assert code == 1 and "sources adoptant modifiées" in message


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                            text=True, encoding="utf-8", check=True, timeout=20)
    return result.stdout.strip()


@pytest.fixture
def coupe(tmp_path: Path) -> tuple[Path, str, str]:
    root = tmp_path / "depot"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.name", "Banc")
    _git(root, "config", "user.email", "banc@example.invalid")
    _git(root, "checkout", "-q", "-b", "develop")
    sources = {
        "README.md": "# Adoptant\n",
        "CHANGELOG.md": "# Journal adoptant\n\n## 1.0.0 — 2026-10-23\n\n**Livré.**\nCe que ça change pour vous : livré.\n",
        "docs/usage.html": "<html>usage</html>\n",
    }
    for destination, content in sources.items():
        path = root / docs.SOURCE / destination
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "sources adoptant")
    source_sha = _git(root, "rev-parse", "HEAD")
    _git(root, "checkout", "-q", "-b", "template/starter-kit")
    for destination, content in sources.items():
        path = root / destination
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", f"chore(template): sync from develop @ {source_sha}")
    published = _git(root, "rev-parse", "HEAD")
    return root, published, source_sha


def test_fraicheur_et_tag_date(coupe: tuple[Path, str, str], monkeypatch: pytest.MonkeyPatch):
    root, published, _ = coupe
    tag = "template/v1.0.0-2026-10-23"
    monkeypatch.setenv("GIT_COMMITTER_DATE", "2026-10-23T12:00:00+0200")
    _git(root, "tag", "-a", tag, "-m", "coupe")
    tag_object = _git(root, "rev-parse", f"refs/tags/{tag}")
    assert tag_object != published
    assert docs.fraicheur(root, published, tag, "develop", tag_object)[0] == 0
    monkeypatch.setenv("GIT_COMMITTER_DATE", "2026-10-22T12:00:00+0200")
    _git(root, "tag", "-a", "autre", "-m", "date discordante")
    wrong_object = _git(root, "rev-parse", "refs/tags/autre")
    assert "taggerdate" in docs.fraicheur(root, published, tag, "develop", wrong_object)[1]
    assert docs.fraicheur(root, published, tag, "develop", wrong_object)[0] == 1
    assert docs.fraicheur(root, published, "template/v1.0.0-2026-10-22", "develop")[0] == 1


def _publier_journal(root: Path, journal: str) -> str:
    """Write the adopter journal on develop, sync it to the template, return the published sha."""
    _git(root, "checkout", "-q", "develop")
    (root / docs.SOURCE / "CHANGELOG.md").write_text(journal, encoding="utf-8")
    _git(root, "commit", "-qam", "journal adoptant")
    source_sha = _git(root, "rev-parse", "HEAD")
    _git(root, "checkout", "-q", "template/starter-kit")
    (root / "CHANGELOG.md").write_text(journal, encoding="utf-8")
    _git(root, "commit", "-qam", f"chore(template): sync from develop @ {source_sha}")
    return _git(root, "rev-parse", "HEAD")


def test_fraicheur_tete_d_une_version_dev(coupe: tuple[Path, str, str]):
    # The template tags are `.devN` until 0.1.0: the dated head must carry them.
    root, _, _ = coupe
    tag = "template/v0.1.0.dev9-2026-10-24"
    entry = "\n**Livré.**\nCe que ça change pour vous : livré.\n"
    published = _publier_journal(root, f"# Journal\n\n## 0.1.0.dev9 — 2026-10-24\n{entry}")
    assert docs.fraicheur(root, published, tag, "develop")[0] == 0
    assert docs.fraicheur(root, published, "template/v0.1.0.dev8-2026-10-24", "develop")[0] == 1
    pending = _publier_journal(root, f"# Journal\n\n## 0.1.0 — à paraître\n{entry}")
    code, message = docs.fraicheur(root, pending, tag, "develop")
    assert code == 1 and "tête attendue" in message


def test_fraicheur_refuse_destination_et_source(coupe: tuple[Path, str, str]):
    root, published, _ = coupe
    tag = "template/v1.0.0-2026-10-23"
    assert docs.fraicheur(root, published, tag, "develop")[0] == 0
    (root / "README.md").write_text("périmé\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-qm", "doc périmée")
    stale = _git(root, "rev-parse", "HEAD")
    code, message = docs.fraicheur(root, stale, tag, "develop")
    assert code == 1 and "README.md" in message
    _git(root, "checkout", "-q", "develop")
    (root / docs.SOURCE / "README.md").write_text("nouvelle source\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "source après coupe")
    code, message = docs.fraicheur(root, published, tag, "develop")
    assert code == 1 and "sources adoptant" in message


def test_fraicheur_inconclusive(coupe: tuple[Path, str, str]):
    root, published, _ = coupe
    assert docs.fraicheur(root, published, "template/v1.0.0-2026-10-23", "inconnue")[0] == 2
    assert docs.fraicheur(root, "absent", "template/v1.0.0-2026-10-23", "develop")[0] == 2


def test_source_absente_a_l_ancre_refuse(coupe: tuple[Path, str, str]):
    root, _, _ = coupe
    _git(root, "checkout", "-q", "develop")
    _git(root, "rm", "-q", docs.SOURCE + "README.md")
    _git(root, "commit", "-qm", "source manquante")
    source_sha = _git(root, "rev-parse", "HEAD")
    _git(root, "checkout", "-q", "template/starter-kit")
    _git(root, "rm", "-q", docs.SOURCE + "README.md")
    _git(root, "commit", "-qm", f"chore(template): sync from develop @ {source_sha}")
    published = _git(root, "rev-parse", "HEAD")
    code, message = docs.fraicheur(root, published, "template/v1.0.0-2026-10-23", "develop")
    assert code == 1 and "source absente" in message


def test_changelog_coupe_toute_la_technique(tmp_path: Path):
    (tmp_path / "CHANGELOG.md").write_text(
        "## Non publié\n### Ajouté\n**Un titre.**\n"
        "Ce que ça change pour vous : du concret.\nTechnique : secret interne.\n"
        "## Pour les mainteneurs\n**Autre titre.**\n"
        "Ce que ça change pour vous : à exclure.\n", encoding="utf-8")
    output = docs.changelog_section(tmp_path, "Ajouté", "1.0.0", "2026-10-23")
    assert output.startswith("## 1.0.0 — 2026-10-23")
    assert "**Un titre.**" in output and "du concret" in output
    assert "Technique" not in output and "mainteneurs" not in output
    assert "à exclure" not in output


def test_changelog_coupe_une_version_entiere(tmp_path: Path):
    (tmp_path / "CHANGELOG.md").write_text(
        "## 0.1.0 — à paraître\n### Ajouté\n**Ajout.**\nCe que ça change pour vous : neuf.\n"
        "Technique : interne.\n### Changé\n**Change.**\nCe que ça change pour vous : autre.\n"
        "## 0.0.9\n### Ajouté\n**Ancien.**\nCe que ça change pour vous : à exclure.\n",
        encoding="utf-8")
    output = docs.changelog_section(tmp_path, "0.1.0 — à paraître", "0.1.0", "2026-10-23")
    assert "### Ajouté" in output and "### Changé" in output
    assert "neuf" in output and "autre" in output
    assert "Technique" not in output and "à exclure" not in output
    assert docs.changelog_section(tmp_path, "Ajouté", "0.1.0", "2026-10-23").count("**") == 2


def test_cli_changelog_et_fraicheur(coupe: tuple[Path, str, str]):
    root, published, _ = coupe
    scripts = root / ".agents/bin"
    scripts.mkdir(parents=True, exist_ok=True)
    for module in (docs.__file__, st.__file__, Path(st.__file__).with_name("sync_template_proc.py")):
        shutil.copy2(module, scripts / Path(module).name)
    (root / "CHANGELOG.md").write_text(
        "### Ajouté\n**Une entrée.**\nCe que ça change pour vous : utile.\n"
        "Technique : interne.\n", encoding="utf-8")
    result = subprocess.run([sys.executable, str(scripts / "sync_template_docs.py"),
                             "--changelog", "--section", "Ajouté", "--version", "1.0.0",
                             "--date", "2026-10-23"], capture_output=True, text=True,
                            encoding="utf-8", check=False, timeout=20)
    assert result.returncode == 0
    assert "**Une entrée.**" in result.stdout and "Technique" not in result.stdout
    result = subprocess.run([sys.executable, str(scripts / "sync_template_docs.py"),
                             "--fraicheur", "--ref", published, "--tag", "template/v1.0.0-2026-10-23",
                             "--source", "develop"], capture_output=True, text=True,
                            encoding="utf-8", check=False, timeout=20)
    assert result.returncode == 0 and "FRAICHEUR 0" in result.stdout
