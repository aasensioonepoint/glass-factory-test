"""La nuit relit le plan COMMITÉ : la condition 3 du contrat porte S4.

ZERO LLM CALLS. Un plan dont le sha256 tient mais qui n'est pas dans HEAD (non
suivi, indexé, modifié, ignoré) ne doit pas ouvrir de nuit : la condition 3 du
contrat d'éligibilité de `/night` y ajoute une relecture git SANS redirection —
`git status --porcelain --ignored --untracked-files=all -- <chemin>`, rc 0 et
sortie vide — que `Bash(git status:*)` de l'allowlist headless couvre déjà.

D1 : la condition 3 (entre « 3. » et « 4. » de la section du contrat) de
`.claude/commands/night.md` porte la phrase ; D2 : idem `.agents/skills/night/SKILL.md`.
La source `commands/night.md` est tenue aussi : un rendu non rejoué rougit D1.
D3 : la commande EXTRAITE de chaque surface est JOUÉE dans un dépôt jetable, sur
chaque état du plan, avec et sans `status.showUntrackedFiles=no` : seule la
sortie d'un plan commité propre est vide. D4 : le paragraphe des relectures de
la nuit (SKILL.md, « Nothing enters the night ») nomme la condition.
Borne : `assume-unchanged` / `skip-worktree` et l'attribut `ident` ne sont pas vus par
`git status` (dit dans la phrase ; `night_approve.py` compare les octets).
D5 (clôture F3, puis n°2 F2) : la condition 3 porte S5, le refus d'un lien symbolique
sur le chemin ou l'un de ses répertoires, et sa commande EXTRAITE est jouée sur un
lien (rc 1), sous un répertoire lié (rc 1) et sur un fichier (rc 0).
"""

import os
import re
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
S4 = (
    "**et le plan est commité, identique à HEAD** (condition 8 de `night_approve.py`) — "
    "`git status --porcelain --ignored --untracked-files=all -- <chemin>` rend 0 et n'imprime "
    "RIEN ; une ligne imprimée (`??` non suivi, `A ` indexé, ` M`, `M ` ou `MM` modifié, `!!` "
    "ignoré) ou un autre rc : la tâche est REFUSÉE (borne : un fichier `assume-unchanged` ou "
    "`skip-worktree`, ou des octets que l'attribut `ident` ramène au blob, ne sont pas vus ici ; "
    "`night_approve.py` compare les octets au blob de HEAD) ;"
)
S5 = (
    "**et ni `<chemin>` ni l'un de ses répertoires n'est un lien symbolique** (un lien commité "
    "n'imprime rien à git status ; `night_approve.py` le refuse) — `bash .agents/pyrun.sh -c "
    "\"import os,sys;p=sys.argv[1];sys.exit(0 if os.path.realpath(p)==os.path.join("
    "os.path.realpath('.'),os.path.normpath(p)) else 1)\" <chemin>`, joué depuis la racine, rend 0 ; "
    "sinon la tâche est REFUSÉE ;"
)
_LINK_CMD = re.compile(r"`(bash \.agents/pyrun\.sh -c \"[^`]*realpath[^`]*)`")
RECHECK = "plan committed and identical to HEAD (condition 8 of `night_approve.py`)"
SKILL = ROOT / ".agents" / "skills" / "night" / "SKILL.md"
SURFACES = {
    "D1": ROOT / ".claude" / "commands" / "night.md",
    "D2": SKILL,
    "source": ROOT / "commands" / "night.md",
}
_SECTION = re.compile(r"^### (?:Le contrat|Contrat) d'éligibilité.*?(?=^#{1,3} )", re.DOTALL | re.MULTILINE)
_CONDITION_3 = re.compile(r"^3\. .*?(?=^4\. )", re.DOTALL | re.MULTILINE)
_STATUS_CMD = re.compile(r"`(git status [^`]*)`")
# Identité et environnement du banc : aucune variable GIT_* héritée, sauf la config.
_KEEP = {"GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM"}
_IDENT = ("-c", "user.name=banc", "-c", "user.email=banc@local", "-c", "commit.gpgsign=false")
PLAN = "plan.md"


def condition_3(text):
    """Texte de la condition 3 du contrat d'éligibilité, ou None si la borne manque."""
    section = _SECTION.search(text)
    if not section:
        return None
    cond = _CONDITION_3.search(section.group(0))
    return re.sub(r"\s+", " ", cond.group(0)) if cond else None


def _env(global_cfg):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_") or k in _KEEP}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=str(global_cfg))
    return env


def _git(repo, env, *args):
    return subprocess.run(["git", "-C", str(repo), *args], env=env, check=True,
                          capture_output=True, text=True)


def _build(repo, env, state):
    """Pose le plan dans l'état nommé ; `.gitignore` commité ignore `ign.md`."""
    _git(repo, env, "init", "-q")
    (repo / ".gitignore").write_text("ign.md\n", encoding="utf-8")
    _git(repo, env, "add", "--", ".gitignore")
    _git(repo, env, *_IDENT, "commit", "-q", "-m", "init")
    name = "ign.md" if state == "ignored" else PLAN
    (repo / name).write_text("a\n", encoding="utf-8")
    if state in ("untracked", "ignored"):
        return name
    _git(repo, env, "add", "--", PLAN)
    if state == "indexed":
        return PLAN
    _git(repo, env, *_IDENT, "commit", "-q", "-m", "plan")
    if state in ("modified", "staged", "mm"):
        (repo / PLAN).write_text("b\n", encoding="utf-8")
    if state in ("staged", "mm"):
        _git(repo, env, "add", "--", PLAN)
    if state == "mm":
        (repo / PLAN).write_text("a\n", encoding="utf-8")
    return PLAN


STATES = ("untracked", "ignored", "indexed", "modified", "staged", "mm", "clean")


class NightPlanCommiteTests(unittest.TestCase):
    def test_condition_3_reads_the_committed_plan(self):
        for name, path in SURFACES.items():
            with self.subTest(name):
                cond = condition_3(path.read_text(encoding="utf-8"))
                self.assertIsNotNone(cond, f"{path}: condition 3 du contrat introuvable (borne « 3. » .. « 4. »)")
                self.assertIn(S4, cond, f"{path}: la condition 3 ne relit pas le plan commité")
                self.assertIn("sha256", cond, f"{path}: la condition 3 a perdu son empreinte")

    def test_no_redirect_in_the_committed_check(self):
        """C10 : aucune redirection, dont l'appariement headless n'est pas mesuré."""
        for name, path in SURFACES.items():
            with self.subTest(name):
                cond = condition_3(path.read_text(encoding="utf-8")) or ""
                self.assertNotIn(">/dev/null", cond, f"{path}: redirection dans la condition 3")

    def test_extracted_command_refuses_every_state_but_clean(self):
        """D3 : la commande ÉCRITE est jouée ; vide seulement sur un plan commité propre,
        même sous `status.showUntrackedFiles=no` (local ou GIT_CONFIG_GLOBAL)."""
        for name, path in SURFACES.items():
            cond = condition_3(path.read_text(encoding="utf-8")) or ""
            found = _STATUS_CMD.findall(cond)
            self.assertEqual(len(found), 1, f"{path}: une seule commande git status attendue, lu {found}")
            for cfg in ("aucune", "globale", "locale"):
                for state in STATES:
                    with self.subTest(surface=name, config=cfg, state=state), \
                            tempfile.TemporaryDirectory() as tmp:
                        tmp = Path(tmp)
                        glob_cfg = tmp / "gitconfig"
                        glob_cfg.write_text(
                            "[status]\n\tshowUntrackedFiles = no\n" if cfg == "globale" else "",
                            encoding="utf-8")
                        repo = tmp / "r"
                        repo.mkdir()
                        env = _env(glob_cfg)
                        target = _build(repo, env, state)
                        if cfg == "locale":
                            _git(repo, env, "config", "status.showUntrackedFiles", "no")
                        argv = shlex.split(found[0].replace("<chemin>", target))
                        r = subprocess.run(argv, cwd=repo, env=env, capture_output=True, text=True)
                        self.assertEqual(r.returncode, 0, r.stderr)
                        if state == "clean":
                            self.assertEqual(r.stdout, "", f"plan commité propre refusé : {r.stdout!r}")
                        else:
                            self.assertNotEqual(r.stdout.strip(), "", f"état {state} admis (sortie vide)")

    def test_s5_symlink_check_is_written_and_refuses_a_link(self):
        """D5 (clôture F3) : un lien commité n'imprime rien à `git status` ; la condition 3
        porte S5, et la commande EXTRAITE, jouée depuis la racine sur un chemin relatif, rend 1
        sur un lien, 1 sous un RÉPERTOIRE lié (revue de clôture n°2 F2 : `is_symlink` ne lisait
        que le dernier composant) et 0 sur un fichier. `pyrun.sh` est appelé par son chemin
        absolu, la racine jouée est le dossier jetable."""
        pyrun = str(ROOT / ".agents" / "pyrun.sh")
        for name, path in SURFACES.items():
            cond = condition_3(path.read_text(encoding="utf-8")) or ""
            with self.subTest(surface=name, check="S5"):
                self.assertIn(S5, cond, f"{path}: la condition 3 ne refuse pas un lien symbolique")
            found = _LINK_CMD.findall(cond)
            with self.subTest(surface=name, check="une commande"):
                self.assertEqual(len(found), 1, f"{path}: une seule commande realpath attendue, lu {found}")
            for kind, expected in (("lien", 1), ("repertoire lie", 1), ("fichier", 0)):
                with self.subTest(surface=name, kind=kind), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp) / "racine"
                    (root / "docs").mkdir(parents=True)
                    ailleurs = Path(tmp) / "ailleurs"
                    ailleurs.mkdir()
                    (ailleurs / "plan.md").write_text("a\n", encoding="utf-8")
                    if kind == "lien":
                        (root / "docs" / "tasks").mkdir()
                        os.symlink(ailleurs / "plan.md", root / "docs" / "tasks" / "plan.md")
                    elif kind == "repertoire lie":
                        os.symlink(ailleurs, root / "docs" / "tasks")
                    else:
                        (root / "docs" / "tasks").mkdir()
                        (root / "docs" / "tasks" / "plan.md").write_text("a\n", encoding="utf-8")
                    argv = shlex.split((found or ["false <chemin>"])[0].replace("<chemin>", "docs/tasks/plan.md"))
                    if argv[:2] == ["bash", ".agents/pyrun.sh"]:
                        argv[1] = pyrun
                    r = subprocess.run(argv, cwd=root, capture_output=True, text=True)
                    self.assertEqual(r.returncode, expected, f"{kind} : rc {r.returncode} {r.stderr}")

    def test_night_rechecks_name_the_committed_plan(self):
        """D4 : le paragraphe des relectures nocturnes nomme la condition."""
        para = next((p for p in SKILL.read_text(encoding="utf-8").split("\n\n")
                     if p.startswith("**Nothing enters the night")), None)
        self.assertIsNotNone(para, "paragraphe « Nothing enters the night » introuvable")
        self.assertIn(RECHECK, para)

    def test_bound_finds_condition_3(self):
        """Témoin du témoin : la borne isole bien la condition 3, pas la 4."""
        cond = condition_3("### Contrat d'éligibilité\n\n3. a\n   b ;\n4. c\n\n## x\n")
        self.assertEqual(cond, "3. a b ; ")


if __name__ == "__main__":
    unittest.main()
