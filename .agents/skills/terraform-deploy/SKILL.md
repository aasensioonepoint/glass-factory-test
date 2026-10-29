---
name: terraform-deploy
description: Écrire et déployer l'IaC Terraform du projet sur Azure, GCP et AWS — contrat du runner déterministe .agents/bin/tfdeploy.py, catalogue FERMÉ des questions (ids de tfdeploy.py catalogue), questions d'auteur, authentification sans secret par cloud, bonnes pratiques sourcées. À lire avant d'invoquer terraform-deployer, d'écrire du Terraform ou de lire un verdict du runner.
---

# terraform-deploy — écrire et déployer l'IaC Terraform (Azure, GCP, AWS)

## LIRE QUAND

- Une tâche IaC du board — son write-set porte `*.tf`, `*.tf.json`, `*.tfvars`,
  `*.tfvars.json` ou `.agents/deploy/targets.json` (les motifs IaC de
  `MOTIFS_GARDE`, `tasks_direct.py`) : son slot dev est `terraform-deployer`, en mode
  AUTEUR (règle « On an IaC task… » d'AGENTS.md, décision pilote
  S-01M55NC83Z3ZWMWKDP5F6FFDDG). La voie directe lui est refusée (`tasks_direct.py`).
- Un déploiement est demandé (tâche du board, spec ou pilote) APRÈS le `done` d'une
  tâche IaC et une porte verte gelée sur ce SHA : `terraform-deployer` seul, en mode
  DÉPLOIEMENT, HORS de la chaîne, jamais sous `/night`.
- Avant de restituer un verdict de `tfdeploy.py`, ou quand il rend
  `COVERAGE DEGRADED — <outil> absent, verdict absent`.
- Avant de poser une question au pilote sur une cible : § CATALOGUE, puis § Questions
  d'auteur.

Ce n'est pas une étape par défaut du pipeline, et il n'existe pas de commande slash.

## Qui décide

- Le verdict vient d'un runner **sans LLM**, `.agents/bin/tfdeploy.py`. **Source de
  vérité** : son docstring de module, ses tuples `MOTIFS_REFUS` et `MOTIFS_NO_GO`,
  sa constante `CATALOGUE`. Cette page en est DÉRIVÉE ; un écart entre elle et le code
  est un défaut de cette page, à signaler — jamais à arbitrer en lisant un verdict.
- La garde `iac_guard` (`.codex/hooks/iac_guard.py`, copiée octet pour octet dans
  `.gemini/hooks/`) borne la CLI de l'agent hors du runner ; son docstring fait foi
  sur ses règles. Sa couverture par hôte est celle de la skill `guardrails` — jamais
  « six hôtes couverts ».
- La décision d'apply s'écrit par la session appelante (`specs.py add --kind
  decision`), jamais par l'agent. Elle est AUTO-DÉCLARATIVE, comme le tampon de porte
  `VERIFY_STAMP.log` : ça empêche d'OUBLIER, pas de TRICHER.
- Les règles d'écriture du code sont `.agents/ref/CONVENTIONS_infra.md` (puces
  « Terraform: ») ; la doc se lit à la demande par `.agents/ref/DOCS_REGISTRY.md`
  § terraform / hcl (la page précise, jamais recopiée).

## Le contrat du runner (figé)

```text
bash .agents/pyrun.sh .agents/bin/tfdeploy.py probe [--config F]
bash .agents/pyrun.sh .agents/bin/tfdeploy.py catalogue
bash .agents/pyrun.sh .agents/bin/tfdeploy.py intake --target N [--config F]
bash .agents/pyrun.sh .agents/bin/tfdeploy.py check-config [--target N] [--config F]
bash .agents/pyrun.sh .agents/bin/tfdeploy.py identity --target N [--config F]
bash .agents/pyrun.sh .agents/bin/tfdeploy.py plan --target N [--config F]
bash .agents/pyrun.sh .agents/bin/tfdeploy.py apply --target N --task T-<id> --plan-sha <64 hex> [--config F]
bash .agents/pyrun.sh .agents/bin/tfdeploy.py verify --target N [--config F]
bash .agents/pyrun.sh .agents/bin/tfdeploy.py drift --target N [--config F]
```

- **Codes** : `0` GO (OK pour `probe`, `catalogue`, `intake`, `check-config`) ·
  `1` NO_GO · `2` REFUS · `3` DEGRADED. Une ligne JSON ASCII sur stdout ; en DEGRADED,
  `COVERAGE DEGRADED — <outil> absent, verdict absent` sur stderr. Toute exception
  imprévue ou une interruption rend `3`, jamais `1`. Le `--help` du runner fait foi sur
  les options ; chaque analyseur porte `allow_abbrev=False`.
- **Configuration** : `.agents/deploy/targets.json`, propre au projet, COMMITÉ, sans
  aucun secret ; gabarit `.agents/ref/deploy-targets.example.json`. Sa présence arme
  aussi les règles CLI d'`iac_guard` (décision pilote S-01M55NC8SD9WSKNNGSE36GVJ5P).
  Les champs d'une cible sont ceux du § CATALOGUE, plus `workspace` (défaut `default`),
  `profile` aws et `verify[]` (optionnels, jamais demandés).
- **Arbre** : `arbre_sale` si le workdir ou la configuration ne sont pas commités et
  propres ; `head_non_relu` (plan, apply) sans une porte verte GELÉE dont l'arbre est
  identique à `HEAD` hors `.agents/state/` et `runs/` ; `etat_non_ignore` si l'état
  local n'est pas ignoré.
- **Plan**, dans l'ordre : configuration ; arbre ; porte ; état ignoré ; terraform
  présent ; `identity` ; EXPORT de `HEAD` hors dépôt
  (`~/.cache/cadre-tfdeploy/…`) ; `fmt -check`, `init -input=false -lockfile=readonly`,
  `validate`, `tflint` s'il est présent ; `plan -input=false -lock=true
  -detailed-exitcode -out=…` ; `show -json` lu en mémoire (contrôles de portée, comptes
  create, update, delete, replace, destroy) ; trivy config (HIGH ou CRITICAL → NO_GO
  `scanner`) et checkov (constats relayés, jamais bloquants : sans clé d'API, appelé en
  `--skip-download`, `severity` est null) — un scanner absent → DEGRADED, jamais GO ;
  trace. Un plan GO garde son export et son planfile jusqu'à l'apply, au même chemin.
- **Apply** — le PREMIER refus gagne : `prod_poste` (décision pilote
  S-01M55NC9F3TZ7WFH0J77SWCZHP : la prod admet plan, drift, verify, jamais apply),
  configuration, `arbre_sale`, `head_non_relu`, plan tracé (`plan_inconnu`,
  `plan_non_go`, `plan_autre_cible`), `plan_expire` (plus de 23 h), `head_change`,
  `export_altere`, `identity` rejouée, `apply_sans_decision`, `destroy_non_approuve` ;
  puis `terraform apply -input=false -lock=true <planfile>` et l'effacement du dossier
  du plan, succès ou échec. Une seule forme admise par la garde, seule sur sa ligne :
  `bash .agents/pyrun.sh .agents/bin/tfdeploy.py apply --target <nom> --task T-<id> --plan-sha <sha256>`.
- **Décision** : une entrée `kind=decision` de la tâche `--task` qui nomme la cible
  (mot entier), le sha256 du planfile et le `HEAD` du plan, ET dont une ligne
  OUVRE par le jeton `apply approuvé` (en tête de ligne) sans aucun mot de
  négation ou de retrait sur cette ligne (non, pas, refus…, report…, annul…,
  retir…, rejet…, suspend… — `APPROUVE_RE` du runner) ; forme d'accord :
  `apply approuvé : <cible>, planfile <sha256>, HEAD <sha>` ; sinon
  `apply_sans_decision` — un refus, un report ou une négation tracé en décision
  n'autorise rien ; si le plan détruit, `destroy approuvé: <n>` égal au compte.
- **Identity** (plan, apply, identity, verify, drift) : azure `az account show
  --subscription <subscription_id>` (`id` ET `tenantId`) ; gcp `gcloud projects
  describe <project_id>` (`projectId`) ; aws `aws sts get-caller-identity` (`Account`).
  Sortie jamais relayée.
- **Verify** : `terraform output -json` lu en mémoire, sorties `sensitive` masquées
  AVANT tout traitement ; chaque `argv` déclaré passe `verbe_secret` (§ VERBES_SECRETS)
  puis la liste blanche de lecture (az `show`, `list`, `get-*` ; aws `describe-*`,
  `list-*`, `get-*` ; gcloud `describe`/`list`). Le runner ne rend que rc et ok/ko.
- **Drift** : `plan -refresh-only -detailed-exitcode` dans un export jetable — rc 0 GO,
  rc 2 NO_GO `derive`, autre DEGRADED.
- **Cache** : tout dossier de plan de plus de 24 h est balayé à CHAQUE appel ; aucun
  verrou — deux appels concurrents ne sont pas pris en charge (tâche de suite
  T-01M56T8DM4Y2B77ZKRCE0KT1H6). Runner macOS et Linux seulement.

### Motifs

| verdict | motif | ce qu'il dit | remède |
|---|---|---|---|
| REFUS | `arguments` | arguments invalides, `--target` absent | relire `--help` |
| REFUS | `config_absente` | `targets.json` absent | une tâche IaC qui l'écrit depuis le gabarit |
| REFUS | `config_invalide` | JSON illisible, clé inconnue, forme fausse | corriger le fichier dans une tâche IaC |
| REFUS | `config_incomplete` | un champ manque ; porte les ids du catalogue | `intake`, puis les questions |
| REFUS | `config_secret` | clé ou valeur à forme de secret | retirer ET faire tourner le secret |
| REFUS | `cible_inconnue` | `--target` absent du fichier | nommer une cible déclarée |
| REFUS | `workdir_racine` | workdir `.` ou sous `.agents` | un sous-dossier dédié |
| REFUS | `workdir_absent` | workdir absent de `HEAD` | commiter le module racine |
| REFUS | `backend_local` | backend non distant | un backend distant verrouillé |
| REFUS | `arbre_sale` | workdir ou configuration non commités | commit propre, par la tâche IaC |
| REFUS | `head_non_relu` | aucune porte verte gelée ne couvre l'arbre | une porte verte gelée sur HEAD, jouée par l'orchestrateur ; une tâche IaC si le diff depuis S touche l'IaC |
| REFUS | `etat_non_ignore` | tfstate ou `.terraform/` non ignorés | les ignorer (`.gitignore`) |
| REFUS | `sous_module` | un gitlink n'importe où dans le dépôt | aucun déploiement avant la tâche de suite |
| REFUS | `lfs` | un chemin LFS n'importe où dans le dépôt | aucun déploiement avant la tâche de suite |
| REFUS | `filtre_git` | un chemin porte un attribut `filter` | retirer le filtre |
| REFUS | `identite_ecart` | l'identité n'atteint pas la portée de la cible | geste du pilote : se connecter à la bonne portée |
| REFUS | `portee_code_ecart` | une constante du bloc provider contredit la cible | aligner le code sur la cible |
| REFUS | `portee_non_fixee` | aws sans `allowed_account_ids = [<account_id>]` | le poser sur chaque bloc aws |
| REFUS | `prod_poste` | apply d'une cible `env: prod` | jamais au poste (CI : tâche de suite) |
| REFUS | `plan_inconnu` | aucun plan tracé pour ce sha | rejouer `plan` |
| REFUS | `plan_non_go` | le dernier plan n'est pas GO | corriger, rejouer `plan` |
| REFUS | `plan_autre_cible` | plan d'une autre cible ou d'un autre workspace | rejouer `plan` sur la cible |
| REFUS | `plan_expire` | plan de plus de 23 h | rejouer `plan` |
| REFUS | `head_change` | `HEAD` a bougé depuis le plan | rejouer `plan` |
| REFUS | `export_altere` | export, planfile ou empreinte modifiés | rejouer `plan` |
| REFUS | `apply_sans_decision` | aucune décision ne nomme cible, sha256 et `HEAD` avec une ligne ouverte par `apply approuvé`, sans négation | la session appelante l'écrit |
| REFUS | `destroy_non_approuve` | destructions sans `destroy approuvé: <n>` égal | la décision porte le compte exact |
| REFUS | `specs_illisible` | SPECS illisible ou en deux formes | réparer le journal |
| REFUS | `verbe_secret` | un `argv` de `verify` rend un secret | le retirer de `verify` |
| REFUS | `verbe_non_lecture` | un `argv` de `verify` hors liste blanche | une lecture `show`/`list`/`describe`/`get` |
| NO_GO | `fmt` | `terraform fmt -check` en échec | `terraform fmt` dans le workdir |
| NO_GO | `init` | `init` en échec | relancer l'étape dans le workdir |
| NO_GO | `validate` | `validate` en échec | relancer l'étape dans le workdir |
| NO_GO | `tflint` | `tflint` en échec | relancer l'étape dans le workdir |
| NO_GO | `plan` | `terraform plan` en échec | relancer l'étape dans le workdir |
| NO_GO | `scanner` | trivy HIGH ou CRITICAL (checkov : relayé, jamais bloquant) | corriger l'IaC par une tâche IaC |
| NO_GO | `apply` | `terraform apply` en échec | diagnostic du pilote ; l'état peut être partiel |
| NO_GO | `derive` | l'infrastructure a dérivé du code | revue du pilote, puis tâche IaC |
| NO_GO | `verify` | une vérification `expect` est ko | lire la sortie et la cible |

Le runner ne relaie AUCUNE sortie de terraform : un NO_GO d'étape se diagnostique en
relançant l'étape dans le workdir.

## CATALOGUE — les questions fermées du runner

Les ids sont ceux de `tfdeploy.py catalogue`, dans les deux sens (banc
`.agents/evals/test_terraform_deploy_skill.py`). `tfdeploy.py intake` ne rend que les
ids dont le champ MANQUE à la cible ; ceux d'un fournisseur seulement quand il est
connu. On ne demande que ce que les specs (`docs/specs/`, `specs/`), le plan approuvé
et l'IaC taisent (décision pilote S-01M55NC90PB36QPJD37V627HWD). Les questions se
préparent au format décision de `communicator` ; une réponse qui change `targets.json`
ou l'IaC passe par une tâche IaC du board, jamais par le mode DÉPLOIEMENT.

| id | question | champ | quand |
|---|---|---|---|
| `Q-PROVIDER` | Quel fournisseur cloud porte cette cible : azure, gcp ou aws ? | `provider` | toujours, en premier : il ouvre les questions du fournisseur |
| `Q-ENV` | Quel environnement : dev, staging, preprod ou prod (la prod n'est jamais appliquée par le runner) ? | `env` | toujours ; `prod` = plan, drift, verify seulement |
| `Q-WORKDIR` | Quel sous-dossier du dépôt porte le module racine Terraform (jamais la racine) ? | `workdir` | toujours ; un dossier par environnement |
| `Q-REGION` | Quelle région de déploiement ? | `region` | toujours ; c'est aussi la `location` azure ; posée pour aws seul (`AWS_REGION`), jamais vérifiée |
| `Q-BACKEND` | Quel backend d'état DISTANT (type et identifiants non secrets : stockage, bucket, clé) ? | `backend` | toujours ; azure compte de stockage, container et clé ; gcp bucket ; aws bucket et `use_lockfile` |
| `Q-AUTH-MODE` | Comment l'identité s'authentifie-t-elle (CLI connectée, OIDC, identité managée, profil) ? | `auth_mode` | toujours ; étiquette non lue par le runner (§ Authentification) |
| `Q-AZ-TENANT` | Quel tenant Azure (tenant_id) ? | `tenant_id` | provider = azure |
| `Q-AZ-SUBSCRIPTION` | Quelle souscription Azure (subscription_id) ? | `subscription_id` | provider = azure ; égale au `subscription_id` du bloc provider |
| `Q-AZ-RESOURCE-GROUP` | Quel resource group Azure ? | `resource_group` | provider = azure ; existant ou créé par l'IaC |
| `Q-GCP-PROJECT` | Quel projet GCP (project_id) ? | `project_id` | provider = gcp |
| `Q-AWS-ACCOUNT` | Quel compte AWS (account_id, 12 chiffres) ? | `account_id` | provider = aws ; recopié dans `allowed_account_ids` |

## Questions d'auteur — hors catalogue du runner

Elles servent le mode AUTEUR : leur réponse atterrit où le dit la colonne « où » — code
IaC relu, rapport AUTEUR, décision, pipeline CI —, hors de `targets.json`, à UNE
exception : `A-AWS-PROFIL` → champ `profile` de la cible. `A-POSTE-CI` va au pipeline
CI ; `auth_mode` reste la réponse à `Q-AUTH-MODE`. `intake` ne les rend pas. Même règle :
seulement quand les specs, le plan et l'IaC existante se taisent. Leurs ids commencent par `A-` et ne se mêlent jamais
à ceux du runner.

| id | question | où la réponse atterrit | quand |
|---|---|---|---|
| `A-ARCHI` | Quels services et quelle architecture (calcul, données, files, cache) ? | ressources du module racine | toujours, si specs et plan ne les nomment pas |
| `A-RESIDENCE` | Où les données doivent-elles résider (pays, zone réglementaire) ? | `region`/`location` du bloc provider et des ressources, relues en revue | toujours ; le runner ne la garantit pas |
| `A-NOMMAGE` | Quelle convention de nommage des ressources ? | `locals` de nommage | toujours |
| `A-TAGS` | Quels tags ou labels obligatoires (coût, propriétaire, environnement) ? Sur aws, `Project` et `Env` (`POC`, `DEV` ou `PROD`) sont OBLIGATOIRES sur chaque ressource qui accepte des `tags` : la question demande leurs valeurs et les éventuels tags supplémentaires ; `Env = POC` si les specs, le plan, l'IaC existante ou la réponse disent POC, quel que soit l'environnement cible, sinon `dev` → `DEV`, `prod` → `PROD`, `staging` ou `preprod` → valeur parmi les trois nommée par le pilote | aws `default_tags`, google `default_labels`, azurerm `tags` | toujours |
| `A-RESEAU` | Quel réseau existant réutiliser (VNet, VPC, sous-réseaux), ou faut-il le créer ? | data sources ou ressources réseau | dès qu'une ressource se raccorde à un réseau |
| `A-EXPOSITION` | Quelle exposition publique : aucune, adresses filtrées, internet ? | règles réseau, points de terminaison privés ou publics | dès qu'un service écoute |
| `A-DNS-TLS` | Quel nom DNS et quel certificat TLS (géré ou importé) ? | zone et enregistrements DNS, certificat | dès qu'un service est exposé |
| `A-COUT` | Quel plafond de coût mensuel ? | rapport AUTEUR (le runner ne contrôle aucun coût) | toujours |
| `A-APPROBATEUR` | Qui approuve l'apply de cette cible ? | décision tracée par la session appelante | avant le premier apply d'une cible |
| `A-DESTRUCTION` | Quelle politique de destruction (`prevent_destroy`, données conservées) ? | `lifecycle` et protections de suppression | dès qu'une ressource porte des données |
| `A-POSTE-CI` | Déploiement depuis le poste ou par la CI (OIDC) ? | pipeline CI (`auth_mode` reste à `Q-AUTH-MODE`) | toujours ; la prod n'a pas d'apply au poste |
| `A-AZ-RP` | Quels resource providers Azure enregistrer ? | `resource_provider_registrations` du bloc azurerm | provider = azure |
| `A-GCP-SA` | Quel compte de service impersonner ? | `impersonate_service_account` du provider et du backend gcs | provider = gcp |
| `A-GCP-APIS` | Quelles APIs activer sur le projet ? | `google_project_service` | provider = gcp |
| `A-AWS-PROFIL` | Quel profil (IAM Identity Center) porte l'identité, DANS le compte cible ? | `profile` de la cible (optionnel) | provider = aws ; un rôle d'un autre compte (hub) est refusé |
| `A-AWS-KMS` | Quelle clé KMS chiffre l'état et les données ? | `kms_key_id` du backend s3 et des ressources | provider = aws |

Couverts par le catalogue du runner, donc jamais reposés ici : fournisseur,
environnement, région (et `location` azure), backend (stockage d'état azure, bucket gcs,
bucket s3 et `use_lockfile`), mode d'authentification, tenant, souscription, resource
group, projet et compte (→ `allowed_account_ids`).

## Authentification sans secret, par cloud

L'authentification est un geste du PILOTE ; l'agent ne la joue pas, ne demande aucun
secret et n'en écrit aucun. `tfdeploy.py identity` constate seulement que l'identité
ATTEINT la portée de la cible.

- **Azure** — poste : `az login`, le provider lit la session de la CLI « when running
  Terraform locally » ; hors interactif : « We recommend using either a Service
  Principal or Managed Service Identity »
  (https://github.com/hashicorp/terraform-provider-azurerm/blob/main/website/docs/guides/azure_cli.html.markdown) ;
  CI : OIDC, `use_oidc = true` avec `ARM_CLIENT_ID`, `ARM_TENANT_ID`,
  `ARM_SUBSCRIPTION_ID`, sans secret client
  (https://github.com/hashicorp/terraform-provider-azurerm/blob/main/website/docs/guides/service_principal_oidc.html.markdown).
  Backend azurerm : `use_azuread_auth = true` avec `use_cli`, `use_oidc` ou `use_msi` ;
  clé d'accès et SAS « we do not recommend it for new workloads »
  (https://developer.hashicorp.com/terraform/language/backend/azurerm).
- **GCP** — poste : `gcloud auth application-default login`
  (https://docs.cloud.google.com/docs/authentication/provide-credentials-adc) ;
  `impersonate_service_account` : « The service account to impersonate for all Google
  API Calls »
  (https://github.com/hashicorp/terraform-provider-google/blob/main/website/docs/guides/provider_reference.html.markdown),
  et dans le backend gcs ; CI : Workload Identity Federation — source: à vérifier.
  Jamais de clé de compte de service dans le dépôt.
- **AWS** — poste : IAM Identity Center, `aws sso login --profile <profil>`
  (https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso.html) ; le
  provider prend « the `profile` parameter or `AWS_PROFILE` environment variable » ;
  CI : `assume_role_with_web_identity` (un seul bloc) ; « Hard-coded credentials are
  not recommended in any Terraform configuration »
  (https://github.com/hashicorp/terraform-provider-aws/blob/main/website/docs/index.html.markdown).
  Le runner écarte `AWS_PROFILE` (et `AWS_DEFAULT_PROFILE`) ambiant : déclarez `profile`
  dans la cible, il le pose alors lui-même.
  Le compte des identifiants de base doit être `account_id` : un `assume_role` depuis un
  compte hub est refusé (`identite_ecart`, `portee_non_fixee`).

### VERBES_SECRETS — recopie de lecture

La liste qui fait foi est la constante `VERBES_SECRETS` du runner — un ÉCHANTILLON,
jamais une couverture : c'est pourquoi aucune sortie de CLI n'est relayée. La garde
`iac_guard` porte la sienne (règle `iac-cli-secret`, armée là où `targets.json`
existe) ; leurs VERDICTS sont tenus égaux par le banc de cette skill sur un jeu commun
de commandes. Recopie (une entrée par ` · `) :

```text
mots: get-secret-value · batch-get-secret-value · get-session-token · get-federation-token · get-role-credentials · export-credentials · get-login-password · get-credentials · get-token · get-access-token · get-authorization-token · generate-db-auth-token · generate-login-token · get-auth-string · print-access-token · print-identity-token · config-helper · show-connection-string · list-connection-strings · list-publishing-credentials · list-publishing-profiles · generate-sas · decrypt · list-keys
prefixes: assume-role
couples: keys list · key list · credential list · admin-key show · connection-string show · connection-string list · secret show · secret download · credential show · versions access · appsettings list
conditionnels: get-parameter + --with-decryption · get-parameters + --with-decryption · get-parameters-by-path + --with-decryption · get-parameter-history + --with-decryption · secret list + --show-values · acr login + --expose-token
aws_configure_get: secret · token
exceptions: list-keys + aws + kms · keys list + * + kms
```

Lecture : un MOT est un jeton qui ne commence pas par `-` (valeurs d'option comprises) ;
un couple est deux mots consécutifs (une valeur d'option intercalée le rompt :
`secret --vault-name v show` passe la règle, `verify` le refuse quand même) ;
`conditionnels` exige le mot ET l'option ; `exceptions` : `aws kms list-keys` et
`gcloud kms keys list` rendent des NOMS de clés, admis — seulement quand `kms` est le
SERVICE, le premier mot : `keys list --account-name kms` reste un secret, et une option
à valeur posée avant le service (`aws --region r kms list-keys`) perd l'exception.

## Garde `iac_guard` — ce qu'elle refuse hors du runner

Lue en POSITION DE COMMANDE ; le détail et les formes non lues sont dans son docstring.

- terraform : une LISTE BLANCHE (`fmt`, `validate`, `version`, `get`, `graph`, `modules`,
  `metadata`, `providers`, `init` sans `-migrate-state`, `plan` sans `-out`, `show` sans
  `-json`/`-raw`, `output` sans NOM ni `-json`/`-raw` — `terraform output <NOM>` ne masque
  pas une sortie `sensitive`, règle `iac-sortie-sensible` —, `state list|show`,
  `workspace list|show`) ; tout autre
  sous-commande, connue ou future, est refusée — `apply`, `destroy`, `refresh` et `test`
  compris (décision pilote S-01M55NC9PBEKVMHAGHDB6D16WK pour `test`).
- `-auto-approve`, `--auto-approve`, `-force-copy` : refusés dans TOUT projet ;
  `tofu apply` et `tofu destroy` aussi ; les autres sous-commandes `tofu` ne sont jugées
  (refus sauf `version` et `-help`) que là où `.agents/deploy/targets.json` existe
  (mandat S-01M583QEAS4PWYP4XPVHF9CEXQ, décision pilote S-01M583Q4DE5GZB2BHDPC0DVPHY).
- `TF_CLI_ARGS*` affecté ou exporté ; un mot en `.tfstate` ou `.tfplan`, ou un glob non
  cité qui peut y mener (`*.tfstate`, `terraform.tfst*`) ; un fichier d'identifiants cloud
  (`~/.aws/credentials`, `~/.azure/`, `~/.config/gcloud/`) ; un apply du runner hors de sa
  forme unique, derrière un lanceur d'identifiants compris (`aws-vault exec … --`).
- Là où `targets.json` existe : les verbes destructeurs d'`az`, `gcloud`, `aws`, `gsutil`,
  `bq` (ÉCHANTILLON) et les verbes de `VERBES_SECRETS`.
- NON LU, nommé : scripts (`make apply`), `bash -c`, `eval` cité, `find -exec`, `coproc`,
  alias, fonctions, une variable qui porte le nom de l'outil, une commande distante ou
  conteneurisée (`ssh`, `docker run`), le terminal du pilote. Une garde qui ne charge pas
  laisse passer (fail-open).

## Bonnes pratiques — sourcées

- Fichiers du module racine : `terraform.tf` (`required_version`, `required_providers`),
  `providers.tf`, `main.tf`, `variables.tf`, `outputs.tf`, `locals.tf`, `backend.tf`
  (https://developer.hashicorp.com/terraform/language/style).
- `terraform fmt` et `terraform validate` avant chaque commit ; versions des providers
  et des modules épinglées ; un dossier par environnement, donc un état par environnement
  (https://developer.hashicorp.com/terraform/language/style).
- `.terraform.lock.hcl` commité, empreintes de chaque plateforme par `terraform providers
  lock -platform=…` (https://developer.hashicorp.com/terraform/language/files/dependency-lock).
- Backend distant verrouillé et versionné : azurerm (Entra ID), gcs (Object Versioning),
  s3 (`use_lockfile = true`, Bucket Versioning ; `dynamodb_table` déprécié)
  (https://developer.hashicorp.com/terraform/language/backend/s3).
- En automatisation : `-input=false`, `TF_IN_AUTOMATION`, `plan -out` puis apply du
  planfile ; « The plan file contains a full copy of the configuration, the state that
  the plan applies to, and any variables »
  (https://developer.hashicorp.com/terraform/tutorials/automation/automate-terraform).
- `-detailed-exitcode` : 0 sans changement, 1 erreur, 2 changements ; `-refresh-only`
  pour la dérive ; un planfile est un artefact « potentially-sensitive »
  (https://developer.hashicorp.com/terraform/cli/commands/plan).
- `sensitive` reste dans l'état et le plan ; `ephemeral` (1.10 et plus) et les arguments
  write-only (1.11 et plus) n'y sont pas
  (https://developer.hashicorp.com/terraform/language/manage-sensitive-data).
- `terraform test` crée de la vraie infrastructure (un `run` vaut `command = apply` par
  défaut) : refusé ici, l'IaC se teste par `fmt`, `validate` et `plan` sans `-out`
  (https://developer.hashicorp.com/terraform/language/tests).
- aws : `allowed_account_ids` « to prevent you from mistakenly using an incorrect one »,
  `default_tags`
  (https://github.com/hashicorp/terraform-provider-aws/blob/main/website/docs/index.html.markdown).
- aws seul : CHAQUE ressource qui accepte des `tags` porte `Project = <nom du projet>` et
  `Env` = `POC`, `DEV` ou `PROD`, posés dans `default_tags` de chaque bloc provider aws
  (alias compris) depuis un seul local ; les `tags` propres d'une ressource ou d'un module
  ne posent jamais les clés `Project` ni `Env` (« Provider tags can be overridden with new
  values ») ; « This functionality is supported in all resources that implement `tags`, with
  the exception of the `aws_autoscaling_group` resource » : un `aws_autoscaling_group` les
  porte en blocs `tag` à `propagate_at_launch = true`, une `aws_launch_template` dans ses
  `tag_specifications` (« Default tags [are currently not propagated to ASG created
  resources](https://github.com/hashicorp/terraform-provider-aws/issues/32328) ») ; une
  ressource `awscc` (pas de tags par défaut au provider) porte `tags = [{ key = "Project",
  value = local.project }, { key = "Env", value = local.env }]` ; une ressource qu'AWS crée
  seul se déclare (`aws_cloudwatch_log_group`) ou se tague par son parent, le reste est nommé
  au rapport AUTEUR ; le local lit `var.project` et `var.env`, sans défaut, posées dans le
  `terraform.tfvars` commité du workdir, `var.env` sous
  `validation { condition = contains(["POC", "DEV", "PROD"], var.env) }`, `var.project`
  limitée aux caractères admis par AWS ; une valeur que personne n'a donnée reste vide et le
  plan échoue ; aucun secret, donnée personnelle ou nom de code confidentiel dans une valeur
  de tag
  (https://github.com/hashicorp/terraform-provider-aws/blob/main/website/docs/index.html.markdown,
  https://github.com/hashicorp/terraform-provider-aws/blob/main/website/docs/r/launch_template.html.markdown,
  https://github.com/hashicorp/terraform-provider-awscc/blob/main/docs/index.md,
  https://docs.aws.amazon.com/tag-editor/latest/userguide/best-practices-and-strats.html).
- google : `default_labels` sur toute ressource à `labels`
  (https://github.com/hashicorp/terraform-provider-google/blob/main/website/docs/guides/provider_reference.html.markdown).
- azurerm 4 : la souscription est OBLIGATOIRE (`subscription_id` ou
  `ARM_SUBSCRIPTION_ID`) ; `resource_provider_registrations` vaut `core`, `extended`,
  `all`, `none` ou `legacy`
  (https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/guides/4.0-upgrade-guide).
- Versions disponibles d'un module ou d'un provider : l'API du registre, jamais la
  mémoire (https://developer.hashicorp.com/terraform/registry/api-docs).
- Modules vérifiés (Azure Verified Modules, terraform-google-modules,
  terraform-aws-modules), toujours épinglés — source: à vérifier.

## Ce qui n'est pas tenu — nommé

- La RÉGION n'est jamais vérifiée ; hors aws elle vient du code ou de l'environnement
  ambiant. La résidence des données se fixe dans le code IaC relu (`A-RESIDENCE`).
- Dans le code, seules les constantes de bloc provider sont jugées (`subscription_id`,
  `project`, aws `allowed_account_ids`) ; une expression ou un alias non constants, le
  `project` ou le `scope` d'une ressource ne le sont pas.
- AWS hub-and-spoke et multi-comptes : refusés (fail-closed). Un sous-module ou un
  chemin LFS n'importe où : aucun déploiement.
- Décision et tampon de porte auto-déclaratifs ; une porte gelée après un commit IaC
  hors tâche le blanchit (une porte prouve des tests, pas une revue).
- La revue de sécurité n'a pas de lentille IaC et semgrep ne lit pas `.tf` : l'IaC est
  jugée par `trivy config` de `sca-scan.sh` et par trivy au plan (HIGH ou CRITICAL →
  NO_GO `scanner`), DEGRADED sans eux.
- checkov ne bloque JAMAIS : ses constats sont relayés, jamais bloquants (sans clé d'API,
  appelé en `--skip-download`, `severity` est null) ; absent, il rend quand même le plan
  DEGRADED.
- Les listes de verbes CLI (secrets, destructeurs) sont des ÉCHANTILLONS.
- Les tags aws `Project`/`Env` : leur jeu de valeurs est tenu par la `validation` de
  `var.env` au plan ; leur présence sur chaque ressource, par l'auteur seul — aucune déf de
  relecteur ne relit la fiche, aucune garde ne lit les tags.
