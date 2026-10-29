"""Bench of iac_guard.py (T-01M52X1W3WPKCWX1DC36NMKJB6, criterion C2.1).

Three layers, each able to fail:
  1. VERDICTS, in process, on the closed tables below — the cases of C2.1 (refused and
     admitted, without and with `.agents/deploy/targets.json`), the official terraform
     whitelist row by row, and the tofu decision of the pilot (S-01M583Q4DE5GZB2BHDPC0DVPHY).
     Every rule of REGLES has at least one refusal witness (non-vacuity).
  2. CONTRACT PER HOST, as a REAL subprocess (rc, stdout, stderr as bytes): claude ->
     stderr + 2, codex/copilot/gemini -> envelope + 0, kimi and unknown -> both + 2;
     the event line carries `host: "claude"` under claude and never the command text.
  3. THE ARMING by `.agents/deploy/targets.json`, read under `_common.project_root()`,
     replayed in a throwaway git project that carries a copy of the hook.

Python 3.9 compatible on purpose: C2.1 is replayed under /usr/bin/python3 (3.9.6).
Every event goes to a throwaway AGENTS_EVENTS_DIR, never to `.agents/state/events/`.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

HOOKS = Path(__file__).resolve().parent
ROOT = HOOKS.parents[1]
GARDE = HOOKS / "iac_guard.py"
# T-01M52X1W3WPKCWX1DC36NMKJB6 (2026-10-19, CORR-3 (17)) : les options RÉELLES du runner (tfdeploy.py, analyseur
# `apply` : --target, --task, --plan-sha), jamais `--cible`/`--plan`, qui n'existent pas.
RUNNER_CANONIQUE = ("bash .agents/pyrun.sh .agents/bin/tfdeploy.py apply --target app-staging --task T-00000042 "
                    "--plan-sha " + "a" * 64)


def _charger():
    if str(HOOKS) not in sys.path:
        sys.path.insert(0, str(HOOKS))
    spec = importlib.util.spec_from_file_location("_iac_guard_sous_test", GARDE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


garde = _charger()

# (command, expected FIRST rule) — no `.agents/deploy/targets.json`.
REFUSEES_SANS_CIBLE = [
    ("terraform apply", "iac-apply-hors-runner"),
    ("terraform destroy", "iac-apply-hors-runner"),
    ("terraform test", "iac-apply-hors-runner"),
    ("terraform refresh", "iac-apply-hors-runner"),
    ("terraform import aws_s3_bucket.b b", "iac-state"),
    ("terraform taint aws_instance.x", "iac-state"),
    ("terraform untaint aws_instance.x", "iac-state"),
    ("terraform force-unlock 1234", "iac-state"),
    ("terraform state rm aws_instance.x", "iac-state"),
    ("terraform state pull", "iac-state"),
    ("terraform workspace select prod", "iac-state"),
    ("terraform console", "iac-sortie-sensible"),
    ("terraform login", "iac-identifiants"),
    ("terraform logout", "iac-identifiants"),
    ("terraform frobnicate", "iac-sous-commande-inconnue"),
    ("terraform -v", "iac-sous-commande-inconnue"),
    ("terraform --version", "iac-sous-commande-inconnue"),
    ("terragrunt run --all apply", "iac-apply-hors-runner"),
    ("terragrunt apply-all", "iac-apply-hors-runner"),
    ("terragrunt hclfmt", "iac-sous-commande-inconnue"),
    ("terraform init -migrate-state -force-copy", "iac-auto-approve"),
    ("terraform init -migrate-state", "iac-state"),
    ("terraform apply -auto-approve", "iac-auto-approve"),
    ("terraform plan --auto-approve", "iac-auto-approve"),
    ("terraform plan -out=plan.tfplan", "iac-sortie-sensible"),
    ("terraform plan -out p", "iac-sortie-sensible"),
    ("terraform plan --out=p", "iac-sortie-sensible"),
    ("terraform plan -show-sensitive", "iac-sortie-sensible"),
    ("terraform plan --show-sensitive", "iac-sortie-sensible"),
    ("terraform output -raw db", "iac-sortie-sensible"),
    ("terraform show -json", "iac-sortie-sensible"),
    # « Terraform does not redact `sensitive` values when you specify the output by name »
    # (/terraform/cli/commands/output, relu le 2026-10-18).
    ("terraform output db_password", "iac-sortie-sensible"),
    ("terraform -chdir=infra output db", "iac-sortie-sensible"),
    ("terraform output -no-color db", "iac-sortie-sensible"),
    ("terragrunt output db", "iac-sortie-sensible"),
    # position of command, hidden
    ("(terraform apply)", "iac-apply-hors-runner"),
    ("(cd infra && terraform apply)", "iac-apply-hors-runner"),
    ("echo $(terraform output -raw db)", "iac-sortie-sensible"),
    ("x=`terraform output -raw db`", "iac-sortie-sensible"),
    ('echo "$(terraform output -raw db)"', "iac-sortie-sensible"),
    ("sudo -u bob terraform apply", "iac-apply-hors-runner"),
    ("env X=1 terraform apply", "iac-apply-hors-runner"),
    ("X=1 terraform apply", "iac-apply-hors-runner"),
    ("timeout 600 terraform apply", "iac-apply-hors-runner"),
    ("nice -n 10 terraform apply", "iac-apply-hors-runner"),
    ("{ terraform apply ; }", "iac-apply-hors-runner"),
    ("if true ; then terraform apply ; fi", "iac-apply-hors-runner"),
    ('t"e"rraform apply', "iac-apply-hors-runner"),
    ("cd infra && terraform -chdir=x apply", "iac-apply-hors-runner"),
    ("terraform $(echo apply)", "iac-sous-commande-inconnue"),
    # state and planfile reads, in ANY command
    ("grep -n terraform.tfstate .gitignore", "iac-etat-lecture"),
    ("cat infra/terraform.tfstate", "iac-etat-lecture"),
    ("cat terraform.tfstate.backup", "iac-etat-lecture"),
    # the runner outside its canonical form
    ("python3 -B .agents/bin/tfdeploy.py apply --target app-staging", "iac-runner-forme"),
    ("cd x && " + RUNNER_CANONIQUE, "iac-runner-forme"),
    (RUNNER_CANONIQUE + " > journal.txt", "iac-runner-forme"),
    # CORR-3 (2026-10-19) — (2) a glob that can expand to a state or a planfile
    ("cat infra/*.tfstate", "iac-etat-lecture"),
    ("cat infra/terraform.tfst*", "iac-etat-lecture"),
    ("cat infra/terraform.t[f]state", "iac-etat-lecture"),
    ("cat infra/plan.tf?lan", "iac-etat-lecture"),
    ("cat $(ls infra/*state)", "iac-etat-lecture"),
    ("cat infra/terraform.*", "iac-etat-lecture"),
    ("cat terraform.tfstate.*", "iac-etat-lecture"),
    # (3) versioned tool names and launchers read as envelopes
    ("terraform-1.5 apply", "iac-apply-hors-runner"),
    ("terraform_1.5.7 apply", "iac-apply-hors-runner"),
    ("flock /tmp/l terraform apply", "iac-apply-hors-runner"),
    ("builtin command terraform apply", "iac-apply-hors-runner"),
    # (14) credential launchers
    ("aws-vault exec dev -- terraform apply", "iac-apply-hors-runner"),
    ("op run -- terraform apply", "iac-apply-hors-runner"),
    ("doppler run -- terraform destroy", "iac-apply-hors-runner"),
    ("mise exec -- terraform apply", "iac-apply-hors-runner"),
    ("direnv exec . terraform apply", "iac-apply-hors-runner"),
    ("granted terraform apply", "iac-apply-hors-runner"),
    ("assume dev terraform apply", "iac-apply-hors-runner"),
    ("aws-vault exec dev -- " + RUNNER_CANONIQUE, "iac-runner-forme"),
    # (4) cloud credential files, in ANY project (the shell side of the Claude deny, wider: sso, cli)
    ("cat ~/.aws/credentials", "iac-identifiants"),
    ("cat ~/.azure/accessTokens.json", "iac-identifiants"),
    ("cat ~/.config/gcloud/application_default_credentials.json", "iac-identifiants"),
    ("cat $HOME/.aws/credentials", "iac-identifiants"),
    ('cat "${HOME}/.aws/sso/cache/x.json"', "iac-identifiants"),
    ("base64 < /Users/example/.aws/credentials", "iac-identifiants"),
    # CORR-5a T3 (2026-10-19): segments normalised, Windows anchors, a prefix under .aws.
    ("cat ~/.aws//credentials", "iac-identifiants"),
    ("cat ~/.aws/./credentials", "iac-identifiants"),
    ("cat ~/.config/./gcloud/x", "iac-identifiants"),
    ("cat $USERPROFILE/.aws/credentials", "iac-identifiants"),
    ("cat C:/Users/example/.aws/credentials", "iac-identifiants"),
    ("cat ~/.aws/credentials.bak", "iac-identifiants"),
    # (18) $IFS in a command word
    ("terraform${IFS}apply", "iac-illisible"),
    ("terraform$IFS apply", "iac-illisible"),
    # CORR-5a T2 (2026-10-19): $IFS in an ARGUMENT, read on the whole command.
    ("terraform -chdir=infra${IFS}destroy${IFS}-auto-approve", "iac-illisible"),
    ("terraform show -no-color${IFS}-json", "iac-illisible"),
    ("terraform init -input=false${IFS}-force-copy", "iac-illisible"),
    ("terraform output -no-color${IFS}db_password", "iac-illisible"),
    # CORR-5a T4 (2026-10-19): asdf / mise open the window under a subcommand that runs.
    ("asdf exec terraform apply", "iac-apply-hors-runner"),
    ("asdf --verbose exec terraform apply", "iac-apply-hors-runner"),
    ("mise x terraform@1.5 -- terraform apply", "iac-apply-hors-runner"),
    # TF_CLI_ARGS
    ("export TF_CLI_ARGS_apply=-auto-approve", "iac-tf-cli-args"),
    ("TF_CLI_ARGS=-auto-approve make deploy", "iac-tf-cli-args"),
    # tofu, decision S-01M583Q4DE5GZB2BHDPC0DVPHY: refused in EVERY project
    ("tofu apply", "iac-apply-hors-runner"),
    ("tofu destroy", "iac-apply-hors-runner"),
    ("tofu plan -auto-approve", "iac-auto-approve"),
    ("tofu init --force-copy", "iac-auto-approve"),
    ("tofu -chdir=infra apply", "iac-apply-hors-runner"),
    ("sudo tofu destroy", "iac-apply-hors-runner"),
    ("(cd infra && tofu apply)", "iac-apply-hors-runner"),
]

ADMISES_SANS_CIBLE = [
    "terraform fmt -check", "terraform validate", "terraform init -input=false", "terraform plan",
    "terraform state list", "terraform state show aws_instance.x", "terraform workspace list",
    "terraform output", "terraform output -no-color", "terraform show", "terraform -version",
    "terraform -help",
    "terraform --help", "terraform version", "terraform providers lock", "tofu version",
    "cd terraform", "which terraform", "command -v terraform", "brew install terraform",
    "chmod +x bin/terraform", "echo terraform apply", 'echo "terraform apply"',
    'git commit -m "terraform destroy"', "git check-ignore -v x.tfplan",
    "git rm --cached infra/terraform.tfstate", "printf '%s\\n' '*.tfstate'",
    "grep -n tfstate .gitignore", RUNNER_CANONIQUE,
    "bash .agents/pyrun.sh .agents/bin/tfdeploy.py plan --target app-staging",
    # CORR-3 (2026-10-19): globs that cannot reach a state, quoted patterns, names that are not the tool,
    # and what the credential rule leaves open.
    "ls *.tf", "cat infra/*.tfvars", "wc -l modules/*/main.tf", "ls docs/tasks/*-plan.md", 'cat "*.tfstate"',
    "terraform-ls serve", "ls ~/.aws", "az login", "cat ~/.aws/config", "aws sts get-caller-identity",
    # Q6 (b), Q8: without a target, the CLI rules and tofu (apart from the pilot's
    # decision) are not armed.
    "aws s3 rm s3://b/k", "az redis list-keys", "tofu plan", "tofu validate",
    "ls -la src", "terraform-docs markdown .",
    # CORR-5a T4 (2026-10-19): installing a version runs nothing.
    "asdf install terraform 1.5.7", "mise install terraform", "mise use terraform@1.5.7",
]

REFUSEES_AVEC_CIBLE = [
    ("aws s3 rm s3://b/k", "iac-cli-destructif"),
    ("gsutil rm gs://b/k", "iac-cli-destructif"),
    ("bq rm -f ds.t", "iac-cli-destructif"),
    ("az group delete --name rg", "iac-cli-destructif"),
    ("aws ec2 terminate-instances --instance-ids i-0", "iac-cli-destructif"),
    ("aws s3 sync . s3://b --delete", "iac-cli-destructif"),
    ("aws configure export-credentials", "iac-cli-secret"),
    ("az redis list-keys", "iac-cli-secret"),
    ("az cosmosdb list-keys", "iac-cli-secret"),
    # T-01M52X1W3WPKCWX1DC36NMKJB6 (2026-10-19) : le couple `keys list` hors kms, lu dans COUPLES_SECRETS.
    ("az storage account keys list --account-name s", "iac-cli-secret"),
    ("az appconfig credential list", "iac-cli-secret"),
    ("aws secretsmanager get-secret-value --secret-id x", "iac-cli-secret"),
    ("aws ssm get-parameter --name p --with-decryption", "iac-cli-secret"),
    ("aws configure get aws_secret_access_key", "iac-cli-secret"),
    ("az acr login --name r --expose-token", "iac-cli-secret"),
    ("sudo aws sts assume-role --role-arn x", "iac-cli-secret"),
    # CORR-3 (2026-10-19): m11 `connection-string list`; (15) kms exempts only as the SERVICE; (14) a launcher.
    ("az webapp config connection-string list --name w --resource-group g", "iac-cli-secret"),
    ("az storage account keys list --account-name kms", "iac-cli-secret"),
    ("az redis list-keys --name kms", "iac-cli-secret"),
    ("aws-vault exec dev -- aws s3 rm s3://b/k", "iac-cli-destructif"),
    ("tofu test", "iac-tofu"),
    ("tofu plan", "iac-tofu"),
    ("tofu", "iac-tofu"),
    ("tofu output db", "iac-tofu"),
    ("tofu apply", "iac-apply-hors-runner"),
    # CORR-5a T2 (2026-10-19): with a target, $IFS next to a cloud CLI.
    ("aws s3${IFS}rm s3://b/k", "iac-illisible"),
]

ADMISES_AVEC_CIBLE = [
    "aws kms list-keys", "gcloud kms keys list", "az group list", "aws ssm get-parameter --name p",
    "aws configure get region", "tofu version", "tofu -help", "terraform plan",
]

# The official list (/terraform/cli/commands, v1.16.x, plus `test`): verdict of the bare
# subcommand, None = admitted outside the runner.
TABLE_OFFICIELLE = {
    "fmt": None, "validate": None, "version": None, "get": None, "graph": None,
    "modules": None, "metadata": None, "providers": None, "init": None, "plan": None,
    "show": None, "output": None,
    "state": "iac-state", "workspace": "iac-state",
    "apply": "iac-apply-hors-runner", "destroy": "iac-apply-hors-runner",
    "refresh": "iac-apply-hors-runner", "test": "iac-apply-hors-runner",
    "console": "iac-sortie-sensible", "login": "iac-identifiants", "logout": "iac-identifiants",
    "import": "iac-state", "taint": "iac-state", "untaint": "iac-state", "force-unlock": "iac-state",
}
SOUS_SOUS = {
    "terraform state list": None, "terraform state show x": None, "terraform state mv a b": "iac-state",
    "terraform state rm a": "iac-state", "terraform state push f": "iac-state",
    "terraform state pull": "iac-state", "terraform state replace-provider a b": "iac-state",
    "terraform workspace list": None, "terraform workspace show": None,
    "terraform workspace new x": "iac-state", "terraform workspace select x": "iac-state",
    "terraform workspace delete x": "iac-state", "terraform providers lock": None,
    "terraform providers mirror d": None, "terraform providers schema -json": None,
}


def _ecarts(cas, cible):
    """`[(command, expected, obtained)]` for every case whose FIRST rule differs."""
    ecarts = []
    for commande, attendue in cas:
        obtenues = garde.verdicts(commande, cible)
        premiere = obtenues[0] if obtenues else None
        if premiere != attendue:
            ecarts.append((commande, attendue, obtenues))
    return ecarts


class VerdictTests(unittest.TestCase):
    def test_refusees_sans_cible(self):
        self.assertEqual(_ecarts(REFUSEES_SANS_CIBLE, False), [])

    def test_admises_sans_cible(self):
        self.assertEqual(_ecarts([(c, None) for c in ADMISES_SANS_CIBLE], False), [])

    def test_refusees_avec_cible(self):
        self.assertEqual(_ecarts(REFUSEES_AVEC_CIBLE, True), [])

    def test_admises_avec_cible(self):
        self.assertEqual(_ecarts([(c, None) for c in ADMISES_AVEC_CIBLE], True), [])

    def test_tofu_decision_pilote(self):
        # S-01M583Q4DE5GZB2BHDPC0DVPHY: apply/destroy/auto-approve refused in EVERY
        # project; the rest judged only where targets.json exists.
        self.assertEqual(_ecarts([
            ("tofu apply", "iac-apply-hors-runner"), ("tofu destroy", "iac-apply-hors-runner"),
            ("tofu plan -auto-approve", "iac-auto-approve"), ("tofu plan", None),
            ("tofu validate", None),
        ], False), [])
        self.assertEqual(_ecarts([("tofu plan", "iac-tofu"), ("tofu version", None)], True), [])

    def test_liste_blanche_officielle_ligne_par_ligne(self):
        cas = [("terraform " + sous, attendu) for sous, attendu in TABLE_OFFICIELLE.items()]
        cas += list(SOUS_SOUS.items())
        self.assertEqual(_ecarts(cas, False), [])
        self.assertEqual(sorted(garde.SOUS_TERRAFORM), sorted(TABLE_OFFICIELLE))

    def test_chaque_regle_a_un_temoin_de_refus(self):
        vues = {r for _c, r in REFUSEES_SANS_CIBLE} | {r for _c, r in REFUSEES_AVEC_CIBLE}
        self.assertEqual(sorted(set(garde.REGLES) - vues - {"iac-illisible"}), [])

    def test_redos_un_mot_qui_repete_tfstate_reste_sous_la_borne(self):
        # CORR-3 (1): measured 10.0 s (hook timeout 10 s) on the whole word; the last segment is linear.
        mot = ".tfstate" * 21000 + "/"
        debut = time.monotonic()
        verdict = garde.verdicts("echo " + mot + " ; terraform apply", False)
        duree = time.monotonic() - debut
        self.assertEqual(verdict, ["iac-apply-hors-runner"])
        self.assertLess(duree, 3.0, "state pattern quadratic again: %.2f s" % duree)

    def test_glob_trop_long_refuse_ferme(self):
        self.assertEqual(garde.verdicts("cat *" + "a" * (garde.GLOB_MAX + 1), False), ["iac-etat-lecture"])

    def test_aucun_nom_legitime_dans_la_forme_versionnee(self):
        for nom in ("terraform-docs", "terraform-ls", "terraformer", "tofuenv", "terragrunt-atlantis-config"):
            self.assertIsNone(garde._OUTIL_VERSIONNE.fullmatch(nom), nom)

    def test_une_garde_qui_echoue_refuse_ce_qui_nomme_un_outil(self):
        with mock.patch.object(garde, "juger", side_effect=RuntimeError("sonde")):
            self.assertEqual(garde.verdicts("terraform plan", False), ["iac-illisible"])
            self.assertEqual(garde.verdicts("ls -la src", False), [])
            # CORR-5a T7 (2026-10-19): the net also covers a command that only names credentials.
            for commande in ("cat ~/.aws/credentials", "cat ~/.azure/x.json", "cat ~/.config/gcloud/x"):
                self.assertEqual(garde.verdicts(commande, False), ["iac-illisible"], commande)

    def test_le_refus_nomme_regle_et_remede(self):
        texte = garde.raison(["iac-apply-hors-runner", "iac-etat-lecture"])
        self.assertTrue(texte.startswith("BLOCKED by iac guard (iac-apply-hors-runner): "))
        self.assertIn("Remedy: ", texte)
        self.assertIn("iac-etat-lecture", texte)


def _env(hote, evenements):
    env = dict(os.environ)
    for cle in ("AGENTS_HOOK_HOST", "CLAUDE_PROJECT_DIR"):
        env.pop(cle, None)
    env["AGENTS_EVENTS_DIR"] = str(evenements)
    if hote:
        env["AGENTS_HOOK_HOST"] = hote
    return env


def _jouer(commande, hote, evenements, garde_path=GARDE, cwd=ROOT, copilot=False):
    if copilot:
        charge = {"toolName": "bash", "toolArgs": {"command": commande}}
    else:
        charge = {"tool_input": {"command": commande}}
    return subprocess.run(
        [sys.executable, "-B", str(garde_path)],
        input=json.dumps(charge).encode("utf-8"),
        capture_output=True, cwd=str(cwd), env=_env(hote, evenements), timeout=60,
    )


def _fichiers_evenements(dossier):
    # events.py writes FLAT into AGENTS_EVENTS_DIR (`_day_file`): no tree walk needed.
    return sorted(Path(dossier).glob("*.jsonl"))


def _evenements(dossier):
    lignes = []
    for chemin in _fichiers_evenements(dossier):
        lignes.extend(json.loads(l) for l in chemin.read_text(encoding="utf-8").splitlines() if l.strip())
    return lignes


class ContratTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="iac-guard-"))

    def tearDown(self):
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    def _dossier(self, nom):
        chemin = self.tmp / nom
        chemin.mkdir()
        return chemin

    def test_claude_stderr_et_sortie_2(self):
        fini = _jouer("terraform apply", "claude", self._dossier("ev"))
        self.assertEqual(fini.returncode, 2)
        self.assertEqual(fini.stdout, b"")
        self.assertTrue(fini.stderr.startswith(b"BLOCKED by iac guard (iac-apply-hors-runner): "))

    def test_hotes_a_enveloppe_sortie_0(self):
        for hote in ("codex", "copilot", "gemini"):
            fini = _jouer("terraform apply", hote, self._dossier("ev-" + hote), copilot=hote == "copilot")
            self.assertEqual(fini.returncode, 0, hote)
            self.assertEqual(fini.stderr, b"", hote)
            corps = json.loads(fini.stdout.decode("utf-8"))
            self.assertEqual(corps["hookSpecificOutput"]["permissionDecision"], "deny", hote)
            self.assertIn("iac-apply-hors-runner", corps["hookSpecificOutput"]["permissionDecisionReason"])
            self.assertEqual("permissionDecision" in corps, hote == "copilot", hote)

    def test_kimi_et_marqueur_inconnu_les_deux_canaux_et_2(self):
        for hote in ("kimi", "", "autre"):
            fini = _jouer("terraform apply", hote, self._dossier("ev-k" + hote))
            self.assertEqual(fini.returncode, 2, hote)
            self.assertIn(b'"permissionDecision":"deny"', fini.stdout, hote)
            self.assertTrue(fini.stderr.startswith(b"BLOCKED by iac guard"), hote)

    def test_admis_aucune_sortie(self):
        for hote in ("claude", "codex", "kimi"):
            fini = _jouer("terraform plan", hote, self._dossier("ev-a" + hote))
            self.assertEqual((fini.returncode, fini.stdout, fini.stderr), (0, b"", b""), hote)

    def test_evenement_sous_claude_porte_host_claude(self):
        dossier = self._dossier("ev-claude")
        commande = "terraform output -raw secret_sonde_9f8e"
        _jouer(commande, "claude", dossier)
        lignes = [l for l in _evenements(dossier) if l.get("kind") == "hook.deny"]
        self.assertEqual(len(lignes), 1)
        self.assertEqual(lignes[0].get("host"), "claude")
        self.assertEqual(lignes[0]["data"].get("guard"), "iac")
        self.assertEqual(lignes[0]["data"].get("rule"), "iac-sortie-sensible")
        brut = "".join(p.read_text(encoding="utf-8") for p in _fichiers_evenements(dossier))
        self.assertNotIn("secret_sonde_9f8e", brut)

    def test_evenement_sous_codex_porte_host_codex(self):
        dossier = self._dossier("ev-codex")
        _jouer("terraform apply", "codex", dossier)
        lignes = [l for l in _evenements(dossier) if l.get("kind") == "hook.deny"]
        self.assertEqual([l.get("host") for l in lignes], ["codex"])


class CibleTests(unittest.TestCase):
    """`.agents/deploy/targets.json` under `_common.project_root()` arms the CLI rules
    and the tofu rule (Q6 (b), Q8) — replayed in a throwaway git project."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="iac-guard-cible-"))
        self.projet = self.tmp / "projet"
        hooks = self.projet / ".codex" / "hooks"
        hooks.mkdir(parents=True)
        for nom in ("_common.py", "safe_bash.py", "safe_bash_git.py", "safe_bash_hooks.py", "iac_guard.py"):
            shutil.copy2(str(HOOKS / nom), str(hooks / nom))
        subprocess.run(["git", "init", "-q", str(self.projet)], check=True, capture_output=True, timeout=60)
        self.evenements = self.tmp / "ev"
        self.evenements.mkdir()

    def tearDown(self):
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    def _verdict(self, commande):
        fini = _jouer(commande, "codex", self.evenements,
                      garde_path=self.projet / ".codex" / "hooks" / "iac_guard.py", cwd=self.projet)
        self.assertEqual(fini.returncode, 0)
        if not fini.stdout:
            return None
        raison = json.loads(fini.stdout.decode("utf-8"))["hookSpecificOutput"]["permissionDecisionReason"]
        return raison.split("(", 1)[1].split(")", 1)[0]

    def test_sans_puis_avec_cible(self):
        sans = {c: self._verdict(c) for c in ("aws s3 rm s3://b/k", "tofu plan", "tofu apply")}
        self.assertEqual(sans, {"aws s3 rm s3://b/k": None, "tofu plan": None,
                                "tofu apply": "iac-apply-hors-runner"})
        cible = self.projet / ".agents" / "deploy" / "targets.json"
        cible.parent.mkdir(parents=True)
        cible.write_text('{"cibles": []}\n', encoding="utf-8")
        avec = {c: self._verdict(c) for c in ("aws s3 rm s3://b/k", "tofu plan", "tofu version")}
        self.assertEqual(avec, {"aws s3 rm s3://b/k": "iac-cli-destructif", "tofu plan": "iac-tofu",
                                "tofu version": None})


if __name__ == "__main__":
    unittest.main()
