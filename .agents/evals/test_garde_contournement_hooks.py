"""T-01M5C1AF6GB3ZRX5QF9SF6R80Y — la garde `git-hooks-bypass`, jugée par UNE matrice sur les trois hôtes.

LA GARDE. Une commande git qui SAUTE les hooks du dépôt (pre-commit, commit-msg, pre-push) est refusée
par `.claude/hooks/safe-bash.sh` (decide_git, garde 8) et par `.codex/hooks/safe_bash.py` /
`.gemini/hooks/safe_bash.py` (judge_git de safe_bash_git.py, hooks_refusal de safe_bash_hooks.py) : `--no-verify` et ses
abréviations, `-n` en grappe sur commit et am, une expansion non citée en option, `-c`/`--config-env`
sur core.hooksPath, un préfixe d'environnement (`HUSKY=`, `GIT_CONFIG_*`…), et un `git config` qui
écrit, édite ou retire core.hooksPath, core.worktree, un alias ou un include — sauf lecture pure. La
règle de `git config` est celle du plan (annexe § 3), prototypée hors dépôt sur 47 cas.

ELLE EMPÊCHE D'OUBLIER, PAS DE TRICHER (décision pilote S-01M5CZ8SYGNDWC7BZN8DTZ1NN7) : chaque borne
nommée par le message a ici une ligne ALLOW « borne nommée », qui rougira le jour où un durcissement la
ferme — exprès, pour que la doc suive.

CE QUE CE BANC REJOUE, et comment :
  1. la matrice (DENY, ALLOW, bornes, DIVERGENCES nommées) sur les trois hôtes, par le `verdict()` du
     banc de parité — son module est chargé par CHEMIN sous un nom privé et jamais lié au niveau du
     module (lié, pytest collecterait GuardDecisionParityTests ici et rejouerait sa matrice entière) ;
  2. le MÊME texte de refus sur les trois hôtes (HOOKS_REASON contre l'echo de safe-bash.sh) ;
  3. les mutants Claude M6c (ERE d'environnement retirée), M7 (note GITHOOKS retirée), M12 (lecture à
     travers qword retirée), B1a (option après `$(…)` de nouveau non lue) et B2a (valeur `.githooks`
     de nouveau repliée), chacun sur une COPIE mutée du hook, dans son propre sous-processus
     (CLAUDE_PROJECT_DIR = la fixture) : le `verdict()` du banc de parité lance le hook du dépôt ;
  4. la ligne DEGRADED : awk en panne (cale sur PATH), `git commit --no-verify` passe rc 0 et le
     `COVERAGE DEGRADED` nomme « git hooks bypass » (posture S-00002848 inchangée).
Les mutants Python (M1-M5, M6, M6b, M9-M11, M15-M22, B1, B2) ne sont PAS rejoués par ce banc : ils se
mesurent à la main sur une copie jetable, et la trace de cette mesure est celle du rapport qui l'a faite
(revue de clôture et passe de correction de T-01M5C1AF6GB3ZRX5QF9SF6R80Y), jamais ce fichier ; la matrice
porte seulement la ligne que chacun fait rougir. M14c : non défini au plan, non joué.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PARITE = Path(__file__).resolve().with_name("test_guard_decision_parity.py")
HOOK_CLAUDE = ROOT / ".claude" / "hooks" / "safe-bash.sh"
BASH = shutil.which("bash")
HOSTS = ("claude", "codex", "gemini")
MOTIF = "skips the repository's git hooks"
MOTIF_REDIRECTION = "redirects a write"

DENY = {"claude": True, "codex": True, "gemini": True}
ALLOW = {"claude": False, "codex": False, "gemini": False}
PY_PLUS_STRICT = {"claude": False, "codex": True, "gemini": True}
CLAUDE_PLUS_STRICT = {"claude": True, "codex": False, "gemini": False}


def _charger(nom, chemin):
    """Un module chargé par CHEMIN sous un nom PRIVÉ (jamais `safe_bash_git` : les bancs gemini importent
    leur propre copie sous ce nom), rendu sans être lié au niveau du module."""
    if nom in sys.modules:
        return sys.modules[nom]
    spec = importlib.util.spec_from_file_location(nom, chemin)
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module
    spec.loader.exec_module(module)
    return module


def _parite():
    """Le banc de parité ; son import `guard_parity_gitenv_rows` vit à côté de lui."""
    if str(PARITE.parent) not in sys.path:
        sys.path.insert(0, str(PARITE.parent))
    return _charger("_parite_garde_contournement_hooks", PARITE)


def ligne(label, command, expected, note, motive=MOTIF):
    return {"label": label, "guard": "safe_bash", "command": command, "expected": expected,
            "note": note, "motive": motive, "env": {}}


# -- DENY ×3 (annexe § 3) -----------------------------------------------------------------------
_DENY = (
    # Après la fusion de develop (T-01M5D6XS2S) : la substitution citée est UN mot, la lecture reprend après elle.
    ("subst-citee-puis-option", 'git commit -m "$(echo x)" --no-verify'),
    ("backtick-cite-puis-option", 'git commit -m "a `date` b" --no-verify'),
    # Fermée sur une autre ligne (heredoc, retour à la ligne) : la lecture reprend après sa fermeture.
    ("heredoc-cite-puis-option", "git commit -m \"$(cat <<'EOF'\nx\nEOF\n)\" --no-verify"),
    ("retour-ligne-cite-puis-n", 'git commit -m "$(\necho a)" -n'),
    # Le guillemet qui REFERME une substitution citée n'en ouvre pas une autre (revue de clôture, B1).
    ("subst-nue-apres-citee", 'git push origin "$(git branch --show-current)"$(printf \' --no-verify\')""'),
    ("no-verify", "git commit --no-verify -m x"),
    ("no-verify-abrege", "git commit --no-veri -m x"),
    ("n-seul", "git commit -n -m x"),
    ("n-en-grappe", "git commit -an -m x"),
    ("am-n", "git am -n x.patch"),
    ("push-no-verify", "git push --no-verify"),
    ("merge-no-verify", "git merge --no-verify topic"),
    ("rebase-no-verify", "git rebase --no-verify main"),
    ("pull-no-verify", "git pull --no-verify"),
    ("c-hookspath", "git -c core.hooksPath=/dev/null commit -m x"),
    ("c-hookspath-casse", "git -c CORE.HOOKSPATH=x push"),
    ("config-env-egal", "git --config-env=core.hooksPath=HP commit -m x"),
    ("config-env-separe", "git --config-env core.hooksPath=HP commit -m x"),
    ("c-include", "git -c include.path=/x commit -m x"),
    ("expansion-en-option", "git commit $FLAGS -m x"),
    # B1 (revue de clôture) : une option écrite APRÈS une substitution n'était jamais lue.
    ("subst-push-puis-option", "git push -u origin $(git branch --show-current) --no-verify"),
    ("subst-commit-puis-option", "git commit $(true) --no-verify -m x"),
    ("subst-merge-puis-option", "git merge $(git rev-parse HEAD) --no-verify"),
    ("backtick-puis-option", "git commit `true` --no-verify -m x"),
    # B2 : la CLÉ se replie, la VALEUR `.githooks` est exacte (`.GITHOOKS` est un autre répertoire).
    ("config-githooks-casse-valeur", "git config core.hooksPath .GITHOOKS"),
    ("c-githooks-casse-valeur", "git -c core.hooksPath=.GITHOOKS commit -m x"),
    ("config-fil", "git config --fil .git/config core.hooksPath /dev/null"),
    ("config-ty", "git config --ty path core.hooksPath /dev/null"),
    ("config-typ-egal", "git config --typ=path core.hooksPath /dev/null"),
    ("config-comm", "git config --comm c core.hooksPath /dev/null"),
    ("config-set-comm", "git config set --comm c core.hooksPath /dev/null"),
    ("config-set-val", "git config set --val hk core.hooksPath /dev/null"),
    ("config-set-val-egal", "git config set --val=hk core.hooksPath /dev/null"),
    ("config-unset-sous-commande", "git config unset core.hooksPath"),
    ("config-remove-section", "git config remove-section core"),
    ("config-rename-section", "git config rename-section core zz"),
    ("config-rem", "git config --rem core"),
    ("config-unset-option", "git config --unset core.hooksPath"),
    ("config-casse-haute", "git config CORE.HOOKSPATH /dev/null"),
    ("config-casse-mixte", "git config Core.HooksPath /dev/null"),
    ("config-t-colle", "git config -tpath core.hooksPath /dev/null"),
    ("config-comment-get", "git config --comment --get core.hooksPath /x"),
    ("config-f-l", "git config -f -l core.hooksPath /x"),
    ("config-get-en-valeur", "git config core.hooksPath get"),
    ("config-e", "git config -e"),
    ("config-edit", "git config edit"),
    ("config-alias", "git config alias.ci 'commit -n'"),
    ("config-include", "git config include.path /x"),
    ("env-git-config", "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null git commit -m x"),
    ("env-husky", "HUSKY=0 git commit -m x"),
    ("env-husky-skip-hooks", "HUSKY_SKIP_HOOKS=1 git commit -m x"),
    ("env-lefthook", "LEFTHOOK=0 git push"),
    ("env-skip", "SKIP=lint git commit -m x"),
    ("sudo", "sudo git commit --no-verify -m x"),
    ("option-citee", 'git commit "--no-verify" -m x'),
    ("sous-commande-citee", 'git "commit" -n -m x'),
    ("cle-citee", 'git config "core.hooksPath" /x'),
    ("lecture-apres-cle", "git config core.hooksPath --get"),
    ("lecture-apres-valeur", "git config core.hooksPath /dev/null --get"),
    ("l-apres-cle", "git config core.hooksPath -l"),
    ("list-apres-cle", "git config core.hooksPath --list"),
    ("zl-apres-cle", "git config core.hooksPath -zl"),
    ("worktree", "git config core.worktree /tmp/x"),
    ("worktree-casse", "git config Core.WorkTree /tmp/x"),
)
# Faux positifs NOMMÉS au message : refusés exprès, sur les trois hôtes.
_FAUX_POSITIFS = (
    ("fp-verify-apres", "git commit --no-verify --verify -m x"),
    ("fp-push-expansion", "git push origin $b"),
    ("fp-merge-expansion", "git merge $b"),
    ("fp-push-substitution", "git push origin $(git branch --show-current)"),
    ("fp-deux-substitutions-citees", 'git commit -m "$(date)$(whoami)"'),
    ("fp-valeur-alias", "git config user.name alias.x"),
    ("fp-lecture-implicite", "git config core.hooksPath"),
    ("fp-f-separe", "git config -f x --get core.hooksPath"),
)
# -- ALLOW ×3 ----------------------------------------------------------------------------------
_ALLOW = (
    ("commit", "git commit -m x"),
    ("commit-message-option", 'git commit -m "--no-verify"'),
    ("commit-uno", "git commit -uno -m x"),
    ("push-n", "git push -n"),
    ("rebase-n", "git rebase -n main"),
    ("cherry-pick-n", "git cherry-pick -n x"),
    ("cherry-pick-expansion", "git cherry-pick $c"),
    ("c-hookspath-status", "git -c core.hooksPath=/dev/null status"),
    ("c-githooks", "git -c core.hooksPath=.githooks commit -m x"),
    ("c-githooks-casse-cle", "git -c Core.HooksPath=.githooks commit -m x"),
    ("config-githooks-casse-cle", "git config Core.HooksPath .githooks"),
    ("push-substitution-citee", 'git push origin "$(git branch --show-current)"'),
    ("commit-substitution-citee-texte", 'git commit -m "wip $(date)"'),
    ("merge-deux-substitutions-citees", 'git merge --no-ff wt/x -m "m: $(git rev-parse --short wt/x) dans $(git branch --show-current)"'),
    ("commit-deux-heredocs", "git commit -m \"$(cat <<'A'\nx\nA\n)\" -m \"$(cat <<'B'\ny\nB\n)\""),
    ("commit-substitution-heredoc", "git commit -m \"$(cat <<'EOF'\nfix: x\n\nCo-Authored-By: y\nEOF\n)\""),
    ("substitution-apres-tirets", "git commit -m x -- $(true)"),
    ("config-get-sous-commande", "git config get core.hooksPath"),
    ("config-get", "git config --get core.hooksPath"),
    ("config-f-colle-get", "git config -f.git/config --get core.hooksPath"),
    ("config-list", "git config --list"),
    ("config-get-a", "git config --get-a core.hooksPath"),
    ("config-githooks", "git config core.hooksPath .githooks"),
    ("config-set-githooks", "git config set core.hooksPath .githooks"),
    ("config-user-email", "git config user.email a@b"),
    ("config-safe-directory", "git config --global --add safe.directory /x"),
    ("config-unset-autre", "git config --unset cadre.signStateCommits"),
    ("husky-sans-verbe", "HUSKY=0 npm test"),
    ("skip-sans-verbe", "SKIP=1 git status"),
    ("foo-skip", "FOO_SKIP=1 git commit -m x"),
    ("nohusky", "NOHUSKY=1 git commit -m x"),
    ("git-config-nosystem", "GIT_CONFIG_NOSYSTEM=1 git commit -m x"),
    ("config-get-worktree", "git config --get core.worktree"),
)
# BORNES NOMMÉES au message, NON refusées (décision pilote S-01M5CZ8SYGNDWC7BZN8DTZ1NN7) : un
# durcissement les fera rougir exprès.
_BORNES = (
    ("borne-work-tree-egal", "git --work-tree=/tmp/x commit -m x"),
    ("borne-work-tree-separe", "git --work-tree /tmp/x commit -m x"),
    ("borne-git-work-tree", "GIT_WORK_TREE=/tmp/x git commit -m x"),
    ("borne-git-dir-egal", "git --git-dir=/tmp/r/.git commit -m x"),
    ("borne-git-dir-separe", "git --git-dir /tmp/r/.git commit -m x"),
    ("borne-env-git-dir", "GIT_DIR=/tmp/r/.git git commit -m x"),
    ("borne-home", "HOME=/tmp/h git commit -m x"),
    ("borne-xdg", "XDG_CONFIG_HOME=/tmp/x git commit -m x"),
    ("borne-alias-defini", "git ci -m x"),
    ("borne-commit-tree", "git commit-tree HEAD^{tree} -m x"),
    ("borne-update-ref", "git update-ref HEAD 0123456789abcdef0123456789abcdef01234567"),
    ("borne-expansion-citee", 'F=--no-verify; git commit "$F" -m x'),
    # B3 (revue de clôture) : bornes jusque-là NON nommées, désormais dites au message.
    ("borne-send-pack", "git send-pack ../remote.git HEAD:refs/heads/main"),
    ("borne-config-cle-expansion-citee", 'git config "$K" v'),
    ("borne-option-apres-arobase-accolade", "git rebase @{u} --no-verify"),
    ("borne-substitution-processus", "git commit -F <(printf x) --no-verify"),
)
# DIVERGENCES nommées au message (claude allow, python deny ; puis l'inverse).
_DIVERGENCES_PY = (
    ("div-span-colle-option", 'git commit --no-"verify" -m x',
     "span cité COLLÉ, sauté par decide_git (borne T-00001202)"),
    ("div-span-colle-c", 'git -c core.hooks"Path"=/dev/null commit -m x',
     "span cité COLLÉ dans la valeur de -c (T-00001202)"),
    ("div-span-colle-verbe", 'git co"mmit" -n -m x',
     "span cité COLLÉ dans la sous-commande (T-00001202)"),
    ("div-heredoc", "cat <<'EOF'\nHUSKY=0\nEOF\ngit commit -m x",
     "préfixe d'environnement dans un corps de heredoc à délimiteur cité : lu par Python seul"),
)
_DIVERGENCES_CLAUDE = (
    ("div-arobase-litteral", 'git commit -m x "--amend" # @@',
     "un @@ littéral rend la correspondance des segments cités non prouvée : un mot cité d'un verbe de V se lit EXP"),
)
# Le `>>` vers .git/config n'est PAS de cette garde : la règle de redirection le refuse (segment .git).
_REDIRECTION = (("printf-git-config", "printf x >> .git/config"),)
# Un alias défini pour ce git : refusé par le bras alias de develop (T-01M5D6XV3J), qui parle AVANT cette garde.
MOTIF_ALIAS = "a git ALIAS is defined"
_ALIAS = (("c-alias", "git -c alias.ci='commit -n' ci -m x"),)


def construire_matrice():
    rows = [ligne(f"deny-{l}", c, DENY, "annexe § 3, DENY ×3") for l, c in _DENY]
    rows += [ligne(l, c, DENY, "faux positif NOMMÉ au message") for l, c in _FAUX_POSITIFS]
    rows += [ligne(f"allow-{l}", c, ALLOW, "annexe § 3, ALLOW ×3") for l, c in _ALLOW]
    rows += [ligne(l, c, ALLOW, "borne nommée au message, non refusée") for l, c in _BORNES]
    rows += [ligne(l, c, PY_PLUS_STRICT, n) for l, c, n in _DIVERGENCES_PY]
    rows += [ligne(l, c, CLAUDE_PLUS_STRICT, n) for l, c, n in _DIVERGENCES_CLAUDE]
    rows += [ligne(l, c, DENY, "règle redirect-write-guarded (segment .git), pas cette garde",
                   motive=MOTIF_REDIRECTION) for l, c in _REDIRECTION]
    rows += [ligne(f"deny-{l}", c, DENY, "bras alias (T-01M5D6XV3J), avant cette garde", motive=MOTIF_ALIAS)
             for l, c in _ALIAS]
    return rows


MATRICE = construire_matrice()
PAR_LABEL = {r["label"]: r for r in MATRICE}

# Mutants Claude : (nom, [(texte d'origine, remplacement, occurrences attendues)], lignes qui doivent PASSER).
MUTANTS_CLAUDE = (
    ("M6c ERE d'environnement retirée",
     [('      if ((" " rl) ~ /[^A-Za-z0-9_](GIT_CONFIG_(PARAMETERS|COUNT|KEY_[0-9]+|VALUE_[0-9]+|GLOBAL|SYSTEM)'
       '|HUSKY|HUSKY_SKIP_HOOKS|LEFTHOOK|SKIP)=/) envp = 1\n', "", 1)],
     ("deny-env-husky", "deny-env-git-config", "deny-env-husky-skip-hooks")),
    # `deny-c-alias` n'y est plus : depuis la fusion de develop, le bras alias (T-01M5D6XV3J, note GITALIAS)
    # le refuse aussi, garde 8 retirée ou non — un recouvrement, pas une perte.
    ("M7 note GITHOOKS retirée", [('note("GITHOOKS")', "HV = HV", 5)],
     ("deny-no-verify", "deny-config-fil", "deny-env-husky")),
    ("M12 lecture à travers qword retirée",
     [("hcmd = tolower(qword(j))", "hcmd = tolower(tok)", 1), ("CW[++cn] = qword(j)", "CW[++cn] = tok", 1),
      ("hw = qword(j)", "hw = tok", 2)],
     ("deny-option-citee", "deny-sous-commande-citee", "deny-cle-citee")),
    ("B1a option après une substitution de nouveau non lue",
     [(" if (gotsub && !dd && (hcmd in hverify)) hb = 1;", "", 1)],
     ("deny-subst-push-puis-option", "deny-subst-commit-puis-option", "deny-backtick-puis-option")),
    ("B2a valeur .githooks de nouveau repliée",
     [('substr(v, eq + 1) == ".githooks"', 'tolower(substr(v, eq + 1)) == ".githooks"', 1),
      ('CV[2] == ".githooks" && lo', 'tolower(CV[2]) == ".githooks" && lo', 1)],
     ("deny-config-githooks-casse-valeur", "deny-c-githooks-casse-valeur")),
)


@unittest.skipIf(BASH is None, "no bash on PATH — the Claude host cannot be exercised")
class GardeContournementHooks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parite = _parite()
        cls._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.tmp = Path(cls._tmp.name)
        juge = cls.parite.GuardDecisionParityTests("test_negative_control_the_runner_can_report_both_verdicts")
        juge.fixture = cls.parite.build_fixture(cls.tmp / "project")
        juge.events = cls.tmp / "events"
        juge.events.mkdir()
        juge.rg_shim = cls.parite.build_rg_shim(cls.tmp / "rgbin")
        cls.juge = juge

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def hook_copie(self, texte, path_extra=None):
        """Lance une COPIE de safe-bash.sh posée dans `<fixture>/.claude/hooks/` avec ses deux voisins."""
        hooks = self.juge.fixture / ".claude" / "hooks"
        for voisin in ("protect-paths.sh", "emit-event.sh"):
            shutil.copy2(ROOT / ".claude" / "hooks" / voisin, hooks / voisin)
        (hooks / "safe-bash.sh").write_text(texte, encoding="utf-8")
        env = self.juge.env_for({}, project_dir=self.juge.fixture)
        if path_extra:
            env["PATH"] = path_extra + os.pathsep + env["PATH"]

        def lancer(command):
            payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
            return subprocess.run([BASH, str(hooks / "safe-bash.sh")], input=payload.encode("utf-8"),
                                  capture_output=True, cwd=str(self.juge.fixture), env=env, timeout=120)
        return lancer

    def test_matrice_sur_les_trois_hotes(self):
        for entry in MATRICE:
            for host in HOSTS:
                with self.subTest(row=entry["label"], host=host):
                    self.juge.check(host, entry)

    def test_matrice_peuplee_et_divergences_motivees(self):
        refus = [r for r in MATRICE if r["expected"] == DENY and r["motive"] == MOTIF]
        passes = [r for r in MATRICE if r["expected"] == ALLOW]
        self.assertGreaterEqual(len(refus), 55)
        self.assertGreaterEqual(len(passes), 30)
        self.assertEqual(len(PAR_LABEL), len(MATRICE), "deux lignes portent le même label")
        for r in MATRICE:
            if r["expected"] not in (DENY, ALLOW):
                self.assertGreater(len(r["note"]), 20, r["label"])

    def test_le_meme_texte_sur_les_trois_hotes(self):
        entry = PAR_LABEL["deny-no-verify"]
        _, claude = self.juge.verdict("claude", entry)
        corps = claude.strip().removeprefix("BLOCKED: ")
        for host in ("codex", "gemini"):
            with self.subTest(host=host):
                _, raison = self.juge.verdict(host, entry)
                self.assertEqual(raison.removeprefix("BLOCKED by shell guard: "), corps)
        source = _charger("_garde_hooks_safe_bash_hooks", ROOT / ".codex" / "hooks" / "safe_bash_hooks.py")
        self.assertEqual(source.HOOKS_REASON, corps)
        for borne in ("--git-dir=<d>", "HUSKY_SKIP_HOOKS=", "HOME=", "XDG_CONFIG_HOME=", "T-00001202",
                      "`send-pack`", "`git config \"$K\" v`", "`git rebase @{u} --no-verify`", "`<(…)` before an option",
                      "`.GITHOOKS` refused", "an option after one is unread", "bounded, not closed"):
            self.assertIn(borne, corps)

    def test_les_mutants_claude_rougissent(self):
        source = HOOK_CLAUDE.read_text(encoding="utf-8")
        for nom, sites, lignes in MUTANTS_CLAUDE:
            with self.subTest(mutant=nom):
                mute = source
                for avant, apres, occurrences in sites:
                    self.assertEqual(source.count(avant), occurrences, f"{nom} : le site muté a bougé")
                    mute = mute.replace(avant, apres)
                lancer = self.hook_copie(mute)
                for label in lignes:
                    resultat = lancer(PAR_LABEL[label]["command"])
                    err = resultat.stderr.decode("utf-8", "replace")
                    self.assertNotIn("COVERAGE DEGRADED", err, f"{nom}/{label} : le hook muté a dégradé")
                    self.assertEqual(resultat.returncode, 0, f"{nom} : {label} aurait dû PASSER sous le mutant")
        temoin = self.hook_copie(source)(PAR_LABEL["deny-no-verify"]["command"])
        self.assertEqual(temoin.returncode, 2, "la copie NON mutée doit refuser : sinon le mutant ne prouve rien")

    def test_awk_en_panne_degrade_et_nomme_la_garde(self):
        cale = self.tmp / "awk-en-panne"
        cale.mkdir(exist_ok=True)
        awk = cale / "awk"
        awk.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        awk.chmod(awk.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        lancer = self.hook_copie(HOOK_CLAUDE.read_text(encoding="utf-8"), path_extra=str(cale))
        resultat = lancer("git commit --no-verify -m x")
        err = resultat.stderr.decode("utf-8", "replace")
        self.assertEqual(resultat.returncode, 0, err[:300])
        self.assertIn("COVERAGE DEGRADED: safe-bash —", err)
        self.assertIn("the recognition stage (awk) failed", err)
        self.assertIn("git hooks bypass", err)
        self.assertIn("git hooks bypass", resultat.stdout.decode("utf-8", "replace"))

    def test_controle_negatif_le_juge_rend_les_deux_verdicts(self):
        for host in HOSTS:
            with self.subTest(host=host):
                self.assertTrue(self.juge.verdict(host, PAR_LABEL["deny-no-verify"])[0])
                self.assertFalse(self.juge.verdict(host, PAR_LABEL["allow-commit"])[0])


if __name__ == "__main__":
    unittest.main()
