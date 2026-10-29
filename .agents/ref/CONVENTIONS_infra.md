# Infrastructure conventions — canonical (shared by Claude Code, Codex, Copilot, Gemini/Antigravity)

- Never hardcode secrets, tokens, or internal hostnames; reference env/secret managers.
- Kubernetes: resource requests/limits mandatory on any new Deployment.
- Any change under terraform/ or .github/workflows/ requires explicit user approval first.
- Validate syntax with the local tool when available.
- Before pushing, run EXACTLY what CI runs — same commands, same scope. When the change touches
  process spawning, file locking, sockets or path handling, also replay it on the CI operating
  system: those are the failures a single-platform run cannot see.
- A verification gate must itself be verified. Its replay environment declares its dependencies
  by EFFECTIVE comparison with the target runner (an image missing a tool the runner ships makes
  the gate red where CI is green), and independent legs all run, each keeping its own exit code —
  under `set -e` the first failure hides every later one.
- A constraint measured on ONE platform names that platform in its own statement, and the code
  applying it is conditional. Read as universal, it becomes a defect elsewhere: `SO_REUSEADDR`
  lets a second live bind steal a port on Windows, while on POSIX it only shortens `TIME_WAIT`
  and is REQUIRED to reclaim a port after a peer dies.
- GitHub Actions: `secrets` is not an available context in a job-level `if` (the workflow fails
  to start, with no logs). Map the secret to job `env` and gate the step on `env.X != ''`.
- GitHub Actions: pin every third-party action by its FULL 40-character commit SHA, with the tag
  as an end-of-line comment (`uses: actions/checkout@<sha40>  # v4.2.2`). A tag is a moving
  pointer the publisher can repoint at any commit, so `@v4` is a promise made by someone else;
  the SHA is the only form that names what will actually run. The comment is LOAD-BEARING, not
  decoration — it is the part a human reads at audit time, so a version bump rewrites BOTH the
  SHA and the comment, or the file lies about what it pins.
- Shell: pass externally-derived file lists after `--` so a filename cannot pose as an option,
  and create temp files with `mktemp`, never a predictable PID-based name.
- Terraform: these bullets are the code rules of the `terraform-deployer` AUTHOR mode; the runner
  `.agents/bin/tfdeploy.py` (contract in its docstring) and the skill `terraform-deploy` hold the
  deploy side. Every doc root cited here is listed in `.agents/ref/DOCS_REGISTRY.md` § terraform.
- Terraform: pin versions — `required_version` and every provider of `required_providers` carry a
  version constraint, every module a version (registry) or a ref (git); « use version pinning »
  (https://developer.hashicorp.com/terraform/language/style). An unpinned remote module is named in
  the AUTHOR report.
- Terraform: commit `.terraform.lock.hcl` (« You should include this file in your version control
  repository », https://developer.hashicorp.com/terraform/language/files/dependency-lock) with the
  hashes of EVERY platform that runs terraform: `terraform providers lock -platform=linux_amd64
  -platform=darwin_arm64 …`. The runner initialises with `-lockfile=readonly`.
- Terraform: a REMOTE backend with state locking, one state per environment (« use a directory for
  each environment so that each one has a separate state file », style guide above). azurerm: Entra
  ID (`use_azuread_auth`), never an access key or a SAS (« we do not recommend it for new
  workloads », https://developer.hashicorp.com/terraform/language/backend/azurerm); gcs: Object
  Versioning (https://developer.hashicorp.com/terraform/language/backend/gcs); s3: `use_lockfile =
  true` and Bucket Versioning, `dynamodb_table` is deprecated
  (https://developer.hashicorp.com/terraform/language/backend/s3). The runner refuses a local
  backend (`backend_local`).
- Terraform: `plan -out` then `apply <planfile>` — never an apply that plans again. A saved plan is
  a « potentially-sensitive artifact » (https://developer.hashicorp.com/terraform/cli/commands/plan):
  it holds the configuration, the state and the variables. Only `tfdeploy.py` writes and applies a
  planfile; `-auto-approve` is refused in every project by the `iac_guard` hook.
- Terraform: no secret in `*.tf`, `*.tfvars` or `.agents/deploy/targets.json`. A `sensitive` value is
  still stored in state and plan files; pass a secret through an `ephemeral` variable or resource
  (Terraform 1.10 or later) or a write-only argument (1.11 or later), both omitted from state and
  plan (https://developer.hashicorp.com/terraform/language/manage-sensitive-data).
- Terraform: default tags and labels at the provider — aws `default_tags`, google `default_labels`;
  azurerm has no provider-level default, so `tags` on each resource from one shared local (source: à
  vérifier).
- Terraform: aws only — EVERY resource that supports `tags` is tagged: `Project = <project name>`
  and `Env` = `POC`, `DEV` or `PROD` (exactly these three values, upper case). Set them in
  `default_tags { tags = { Project = …, Env = … } }` on EVERY aws provider block, aliases included,
  from one shared local; a resource's or module's own `tags` never sets the `Project` or `Env` keys
  (the provider: « Provider tags can be overridden with new values »). The provider says « This
  functionality is supported in all resources that implement `tags`, with the exception of the
  `aws_autoscaling_group` resource »
  (https://github.com/hashicorp/terraform-provider-aws/blob/main/website/docs/index.html.markdown).
  So `aws_autoscaling_group` carries them explicitly from the same local, through `tag` blocks with
  `propagate_at_launch = true`, and so do the instances launched from an `aws_launch_template`,
  through its `tag_specifications` (« Default tags [are currently not propagated to ASG created
  resources](https://github.com/hashicorp/terraform-provider-aws/issues/32328) »,
  https://github.com/hashicorp/terraform-provider-aws/blob/main/website/docs/r/launch_template.html.markdown).
  `awscc` resources (no provider-level default tags: the awscc provider schema has no such
  argument, https://github.com/hashicorp/terraform-provider-awscc/blob/main/docs/index.md) carry
  `tags = [{ key = "Project", value = local.project }, { key = "Env", value = local.env }]`.
  `default_tags` reaches only the « resources handled by this provider »: a resource AWS creates by
  itself (a log group a service creates on its own) is declared explicitly where a Terraform
  resource exists (`aws_cloudwatch_log_group`), or tagged through its parent where the provider
  allows (`tag_specifications`); the rest is named in the AUTEUR report.
  Values are never invented: `Project` comes from the specs, the plan, the existing IaC or the
  answer to `A-TAGS`; `Env = POC` when the specs, the plan, the existing IaC or `A-TAGS` say POC,
  whatever the target env; otherwise target env `dev` → `DEV`, `prod` → `PROD`; `staging` or
  `preprod` → the pilot names one of the three values through `A-TAGS`. The shared local reads
  `var.project` and `var.env`, declared without default and set in the workdir's committed
  `terraform.tfvars`; `var.env` carries
  `validation { condition = contains(["POC", "DEV", "PROD"], var.env) }`; `var.project` carries a
  `validation` limiting it to the characters AWS accepts in a tag value (letters, digits, spaces and
  `_ . : / = + - @`, 1 to 256 — « In general, the allowed characters are letters, numbers, spaces
  representable in UTF-8, and the following characters: _ . : / = + - @ »,
  https://docs.aws.amazon.com/tag-editor/latest/userguide/best-practices-and-strats.html). A value
  nobody gave stays unset and the plan fails — never invented. No secret, personal data or
  confidential codename in a tag value (« Tags are accessible to many AWS services, including
  billing », same page). The value set is held by the `validation` of `var.env` at plan; presence
  on each resource is held by the author alone — no reviewer def re-reads this sheet, and no guard
  checks the tags.
- Terraform: the scope is written in the code. aws: `allowed_account_ids = [<account_id>]` on EVERY
  aws provider block, aliases included — the runner refuses `portee_non_fixee` otherwise, so a
  hub-and-spoke or multi-account root is refused (fail-closed). azurerm: an explicit
  `subscription_id` equal to the target's — azurerm 4 requires the subscription « by specifying the
  `subscription_id` provider property, or by exporting the `ARM_SUBSCRIPTION_ID` environment
  variable » (4.0 upgrade guide,
  https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/guides/4.0-upgrade-guide);
  a contrary constant is refused (`portee_code_ecart`).
- Terraform: the region and the data residency are fixed in the reviewed IaC code (provider block
  or resource): the runner does not guarantee them. It never verifies a region; outside aws the
  region comes from the code or from the ambient environment.
- Terraform: `.terraform/`, `*.tfstate`, `*.tfstate.*` and `*.tfplan` are git-ignored (the runner
  refuses `etat_non_ignore`); `.terraform.lock.hcl` stays tracked.
- Terraform: `terraform test` creates real infrastructure (« By default, tests within Terraform
  create real infrastructure », https://developer.hashicorp.com/terraform/language/tests): never
  outside the runner — `iac_guard` refuses it (pilot decision S-01M55NC9PBEKVMHAGHDB6D16WK). IaC is
  tested with `terraform fmt -check`, `terraform validate` and `terraform plan` without `-out`.
- Check `.agents/state/index/CUSTOM_DOCS.md` for ingested infrastructure conventions.
