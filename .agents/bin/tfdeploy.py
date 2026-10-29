#!/usr/bin/env python3
"""RUNNER DÉTERMINISTE DE DÉPLOIEMENT TERRAFORM — `tfdeploy` (T-01M52X1W3WPKCWX1DC36NMKJB6, lot A).

CE DOCSTRING EST LA SOURCE DE VÉRITÉ DU CONTRAT. La skill `terraform-deploy`, la garde `iac_guard` et les défs
`terraform-deployer` le CITENT, sans le redéfinir. La mécanique (export, empreinte, environnement, plan JSON,
scanners) vit dans le module frère `tfdeploy_plan.py`, chargé PAR CHEMIN. Sans LLM, bibliothèque standard seule,
Python 3.9 (`from __future__ import annotations`), macOS/Linux SEULEMENT (la liste blanche d'environnement ne porte
aucune variable Windows ; mesure Windows : tâche de suite).

POURQUOI. « Un `terraform apply` sans confirmation est refusé » est tenu par CODE, dans ces bornes : le runner
n'applique qu'un plan GO qu'il a TRACÉ, pour une cible non prod, sur un arbre IDENTIQUE (hors `.agents/state/` et
`runs/`) à celui d'une porte verte gelée, extrait hors dépôt et CONSERVÉ du plan à l'apply au même chemin, sous un
environnement en LISTE BLANCHE où la portée est POSÉE depuis la cible, après qu'`identity` a vérifié que l'identité
ATTEINT cette portée, et sur une décision tracée qui nomme la cible, le sha256 du planfile et le HEAD et porte le
jeton `apply approuvé`. Il empêche d'OUBLIER, pas de TRICHER : la décision (`specs.py add --kind decision`), le
tampon `VERIFY_STAMP.log` et la trace `runs.jsonl` sont auto-déclaratifs et NON authentifiés ; une porte prouve des
tests, pas une revue. La RÉGION n'est jamais vérifiée ; hors aws elle vient du code ou de l'environnement ambiant
(`GOOGLE_*`, `CLOUDSDK_*` passent). Ce qui n'est pas tenu non plus : checkov ne bloque JAMAIS — ses constats sont
relayés, jamais bloquants (appelé en `--skip-download` dans un environnement sans clé d'API, il rend une sévérité
nulle) ; seul trivy HIGH/CRITICAL fait un NO_GO `scanner` (rendre checkov bloquant : décision pilote).

CLI (contrat figé ; `--config F` partout sauf `catalogue`, défaut `.agents/deploy/targets.json` sous la racine) :
  tfdeploy.py probe                      outils présents ; terraform, trivy ou checkov absent → DEGRADED (checkov
                                         n'en reste pas moins non bloquant au plan)
  tfdeploy.py catalogue                  ids et questions du catalogue FERMÉ (`CATALOGUE`), rc 0
  tfdeploy.py intake --target N          ids des questions dont le champ MANQUE à la cible (Q7), rc 0
  tfdeploy.py check-config [--target N]  configuration ; avec N : arbre propre et état ignoré
  tfdeploy.py identity --target N        l'identité atteint-elle la portée de la cible ?
  tfdeploy.py plan --target N            plan dans un export de HEAD, scanners, empreinte, trace
  tfdeploy.py apply --target N --task T-<id> --plan-sha <64 hex>
  tfdeploy.py verify --target N          sorties terraform (nom, type, drapeau) et vérifications CLI EN LECTURE
  tfdeploy.py drift --target N           `plan -refresh-only` ; une dérive → NO_GO `derive`
Chaque analyseur porte `allow_abbrev=False` ; une erreur d'arguments est un REFUS `arguments` en JSON.

CODES DE SORTIE — 0 GO (OK pour probe, catalogue, intake, check-config) · 1 NO_GO · 2 REFUS · 3 DEGRADED. Une
ligne JSON ASCII sur stdout ; pour chaque outil qui manque, `COVERAGE DEGRADED — <outil> absent, verdict absent`
sur stderr. Garde de tête : toute exception imprévue rend 3 (`erreur interne: <Type>`), jamais 1 ; SIGINT,
SIGTERM, SIGHUP rendent 3 (`interrompu: <SIG>`) après l'arrêt de l'enfant (SIGINT puis, passé `GRACE_S`, SIGKILL) ;
pendant identity, plan, apply, verify ou drift, l'interruption est TRACÉE (ligne DEGRADED de `runs.jsonl`, motif
`interrompu: <SIG>`) : un apply interrompu laisse sa trace, dont le détail dit « apply interrompu : infrastructure
possiblement partielle, verrou du backend possiblement tenu — drift puis nouveau plan ». BORNE (décision pilote
ouverte, à trancher après mesure avec un vrai terraform) : la gestion des signaux reste telle quelle — l'enfant
partage le groupe de processus du runner (aucun `start_new_session`) et reçoit SIGKILL passé `GRACE_S` (60 s).
`MOTIFS_REFUS` et `MOTIFS_NO_GO` les nomment tous : un motif hors de ces tuples est un défaut.

CONFIGURATION — `.agents/deploy/targets.json`, propre au projet, ABSENT du kit, COMMITÉ (il ne porte aucun
secret) ; gabarit `.agents/ref/deploy-targets.example.json`. `{"targets": [cible…]}`, clés `_…` ignorées, toute
autre clé inconnue → `config_invalide`. Une cible : `name` (`NOM_CIBLE_RE`, unique), `provider` (azure|gcp|aws),
`env` (dev|staging|preprod|prod), `workdir` (sous-dossier relatif, sans `..`), `workspace` (défaut `default`),
`region`, `backend` (`type` + identifiants NON secrets, passés en `-backend-config=<clé>=<valeur>` à `init`, jamais
lus d'un fichier), `auth_mode` (étiquette libre, non lue) ; azure `tenant_id`, `subscription_id` (GUID),
`resource_group` ; gcp `project_id` ; aws `account_id` (12 chiffres) et `profile` (optionnel) ; `verify` (optionnel) :
`[{"argv": [outil, …], "expect": {"<chemin.json>": <valeur>}} | {"output": "<nom>", "expect": {...}}]` (chemin
pointé, index de liste en chiffres, `""` = la valeur entière). Fichier absent → `config_absente` (`intake` le lit
comme une cible absente) ; JSON illisible, clé inconnue ou forme fausse → `config_invalide` ; `--target` hors du
fichier → `cible_inconnue` ; un champ manquant → `config_incomplete`, qui porte les ids du catalogue. Refus de
configuration : `config_secret` (clé ou valeur à forme de secret, n'importe où dans
le fichier : `_cle_secrete`, `VALEURS_SECRETES` — un ÉCHANTILLON), `workdir_racine` (workdir `.` ou portant
`.agents` : la décision écrite par `specs.py` salirait l'arbre surveillé), `backend_local` (l'export est jetable,
un état local s'y perdrait ; distant exigé, `dev` compris ; seul le `type` DÉCLARÉ est lu, jamais le bloc backend du
code — nommé).

CONTRÔLES D'ARBRE. `arbre_sale` (check-config avec cible, plan, apply, verify, drift) : `git status --porcelain --
<workdir> <config>` non vide, OU config non suivie / hors du dépôt — l'étiquette `env` n'est lue que sur un
`targets.json` COMMITÉ et propre. `head_non_relu` (plan, apply) : il faut, dans `.agents/state/local/
VERIFY_STAMP.log` (la ligne `FORMAT_TAMPON` que la porte écrit sur un vert `--at`), une ligne `mode=frozen` à `at`
lisible et de sha S tel que `git merge-base --is-ancestor S HEAD` et `git diff --quiet S HEAD -- . ':(exclude).agents/
state' ':(exclude)runs'` (l'ARBRE ENTIER : un module imbriqué ou un fichier lu par `templatefile()` compte) ; au
plus `TAMPONS_MAX` shas essayés, du plus récent au plus ancien ; journal absent ou illisible → refus. HEAD est lu
UNE fois (`head_courant`) et ce sha, jamais le nom `HEAD`, sert au contrôle, à la trace et à l'export. Le refus
liste `git log --oneline S..<head>` et nomme son remède, `REMEDE_RELU`. `etat_non_ignore` (check-config avec
cible, plan) : `git check-ignore -q` de `<workdir>/terraform.tfstate` et `<workdir>/.terraform/x` ≠ 0 (un état
SUIVI compris ; hors dépôt : refus).

PLAN, dans l'ordre : configuration ; `arbre_sale` ; `head_non_relu` ; `etat_non_ignore` ; terraform présent (sinon
DEGRADED) ; `identity` sous l'environnement EXACT de terraform ; EXPORT du sha de HEAD relu dans
`~/.cache/cadre-tfdeploy/<empreinte du dépôt>/<cible>/<id de plan>/export/` (refus `sous_module`, `lfs`,
`filtre_git`, `workdir_absent`) ; dans `<export>/<workdir>` : `fmt -check`, `init -input=false -lockfile=readonly
-backend-config=…`, `validate`, `tflint` s'il est présent (tout rc ≠ 0 → NO_GO de l'étape ; le runner ne relaie
AUCUNE sortie de terraform : relancer l'étape dans le workdir pour le diagnostic) ; `plan -input=false -lock=true
-detailed-exitcode -out=<…/<id>/plan.tfplan>` (rc 0 et 2 = succès, autre → NO_GO `plan`), planfile 0600 À CÔTÉ de
l'export ; `show -json` lu en mémoire, contrôles `portee_code_ecart` / `portee_non_fixee`, comptes (create,
update, delete, replace, destroy) et adresses ; JSON écrit en 0600 le temps des scanners puis effacé ; trivy config
HIGH ou CRITICAL → NO_GO `scanner` ; checkov : constats relayés, jamais bloquants (sévérité nulle sans clé d'API ;
le code bloquerait sur une sévérité HIGH/CRITICAL rendue, que checkov ne rend pas ici) ; scanner absent, en erreur
ou trivy `TRIVY_ECARTEES` → DEGRADED (jamais GO) — un NO_GO l'emporte sur un DEGRADED ; empreinte de l'export ;
trace. Un plan non GO voit son dossier
effacé aussitôt ; un plan GO le CONSERVE jusqu'à l'apply.

APPLY — ordre des contrôles, le PREMIER refus gagne : (1) `prod_poste` si la cible est `env: prod` (décision Q9 :
la prod admet plan, drift, verify — jamais apply ; contrôle lu sur l'étiquette brute, avant tout autre) ; puis la
configuration stricte ; (2) `arbre_sale` ; (3) `head_non_relu` ; (4) le DERNIER plan tracé de ce sha : absent →
`plan_inconnu`, non GO → `plan_non_go`, autre cible ou autre workspace → `plan_autre_cible` ; (5) `plan_expire` si
le plan a plus de `PLAN_EXPIRE_S` (23 h ; mandat S-01M5833323F2RT4S6QV4AF1FS1 : une heure de marge avant le
balayage) ; (6) `head_change` si HEAD a bougé depuis le plan ; (7) `export_altere` : dossier, planfile (sha256 ≠
`--plan-sha`) ou empreinte de l'export différents de ceux du plan ; terraform présent (sinon DEGRADED) ; (8)
`identity` rejouée → `identite_ecart` ; (9) `apply_sans_decision` sauf si la PLUS RÉCENTE entrée `kind=decision`
de la tâche `--task` dont le titre ou le texte nomme la cible (mot entier), le sha256 du planfile (64 hex) ET le
HEAD (40 hex) porte aussi le jeton `apply approuvé` (`APPROUVE_RE`, casse et accent indifférents) : le jeton
doit OUVRIR une ligne de la décision (`apply approuvé` en tête de ligne, espaces permis) et cette ligne ne porte
aucun mot de négation ou de retrait (`non`, `pas`, `refus…`, `report…`, `annul…`, `retir…`, `rejet…`,
`suspend…`, mots entiers) — une décision qui nomme le triplet pour le REFUSER ou le REPORTER n'autorise rien.
Faux positif nommé (fail-closed) : une cible dont le nom porte un de ces mots (`app-non-prod`) sur la ligne du
jeton est refusée ; remède, le triplet sur une autre ligne. BORNES : une négation écrite sur une AUTRE ligne que
celle du jeton n'est pas lue ; une révocation qui ne recopie pas le triplet n'annule rien (la plus récente qui
NOMME le triplet fait foi — décision pilote ouverte) ;
(10) `destroy_non_approuve` si le plan détruit (`destroy` > 0) sans `destroy approuvé: <n>` égal au compte dans
cette décision, ou si elle en approuve un autre nombre. Puis, AU MÊME CHEMIN que le plan, et seulement là :
`terraform apply -input=false -lock=true <planfile>` ; puis le dossier du plan est effacé, succès OU échec. SPECS
n'est lu que par l'interface `etat_lecture.py` (illisible ou en deux formes → `specs_illisible`). Le runner
n'appelle que `terraform` (Q8), jamais `tofu`.

IDENTITY (plan, apply, identity, verify, drift), sous l'environnement EXACT de terraform : azure `az account show
--subscription <subscription_id>` doit rendre ce `id` ET ce `tenantId` ; gcp `gcloud projects describe <project_id>`
doit réussir et rendre ce `projectId` ; aws `aws sts get-caller-identity` doit rendre `Account` = `account_id`. Un
écart, un rc ≠ 0 ou une sortie illisible → `identite_ecart` ; la CLI absente → DEGRADED. La sortie de la CLI n'est
jamais relayée. aws sans `profile` dans la cible : l'`AWS_PROFILE` ambiant est ÉCARTÉ par la liste blanche (un
pilote sur SSO boucle sinon sur `identite_ecart`) ; le détail du refus le dit et nomme le remède, déclarer `profile`. La portée que terraform UTILISE vient de l'environnement posé, SAUF les paramètres du bloc
provider, qui priment : d'où `portee_code_ecart` et, pour aws, `allowed_account_ids` EXIGÉ (`portee_non_fixee`) —
un montage hub-and-spoke ou multi-comptes est donc refusé (fail-closed, nommé).

VERIFY. `terraform output -json` (dans un export jetable, après `init`) est lu en MÉMOIRE ; toute sortie
`"sensitive": true` voit sa valeur remplacée par `MASQUE` AVANT tout traitement (doc HashiCorp : `-json` rend les
valeurs sensibles en clair) ; le runner ne rend que le nom, le type et le drapeau de chaque sortie, et ok/ko de
chaque `expect` (comparé à la valeur MASQUÉE : un `expect` sur une sortie sensible est ko). Chaque `argv` déclaré
est jugé AVANT tout lancement : `verbe_secret(argv)` d'abord (`VERBES_SECRETS`, un ÉCHANTILLON, pas une couverture
— c'est pourquoi aucune sortie de CLI n'est jamais relayée), puis la liste blanche (`juger_argv_verify`) : outil
`az`, `gcloud` ou `aws` en nom nu, commande AVANT toute option ; az : dernier mot de commande `show`, `list` ou
`get-*` ; aws : opération `describe-*`, `list-*`, `get-*`, hors `AWS_OPS_FICHIER` (opérations qui ÉCRIVENT un
fichier local : `get-object`, `get-export`… — échantillon), et aucun mot POSITIONNEL après la première option (un
mot qui ne suit pas directement une option écrite sans `=` : l'`outfile` d'aws est positionnel ; faux positif
nommé, une option de liste à plusieurs valeurs séparées — remède : la liste en JSON, un seul jeton) ; gcloud :
premier `describe`/`list` après au moins un groupe, sans mot de `MOTS_MUTATION_GCLOUD` (échantillon) avant lui.
Tout autre → `verbe_non_lecture`. Une vérification CLI ne rend que rc et ok/ko ; un ko → NO_GO `verify`.

`VERBES_SECRETS` (constante importable, RECOPIÉE dans la garde `iac_guard` — jamais lue par elle — ; verdicts tenus
égaux par `.agents/evals/test_terraform_deploy_skill.py`) et
`verbe_secret(argv) -> str | None` : `argv[0]` est l'outil (son nom de base), casse repliée ; les MOTS sont les jetons
suivants qui ne commencent pas par `-` (valeurs d'option comprises), les OPTIONS les noms des autres (tirets ôtés,
coupés au `=` : `--x=false` POSE `x`) — le modèle de la règle `iac-cli-secret` de `iac_guard`, pour la parité de
C4.1. `mots` : un mot égal ; `prefixes` : un mot qui commence ainsi (`assume-role*`) ; `couples` : deux MOTS
consécutifs (BORNE : une valeur d'option intercalée, `secret --vault-name v show`, rompt le couple ; `verify` le
refuse quand même, le verbe az étant le dernier mot avant la première option) ; `conditionnels` : le mot ou le couple ET l'option ; `aws_configure_get` : `aws … configure get <clé>`
dont la clé contient l'un de ces mots ;
`exceptions` : `(entrée, outil ou "*", mot)` — l'entrée n'est pas un secret quand l'outil correspond et que le mot
est le SERVICE, c'est-à-dire le PREMIER mot (`aws kms list-keys`, `gcloud kms keys list` : des noms de clés) ; le
mot ailleurs (une valeur d'option : `keys list --account-name kms`) n'exempte rien, et une option à valeur posée
avant le service (`aws --region r kms list-keys`, `gcloud beta kms …`) perd l'exception (faux positif nommé, même
modèle que la garde). Rend l'entrée reconnue, ou None.

DRIFT. `plan -refresh-only -input=false -lock=true -detailed-exitcode` dans un export jetable : rc 0 → GO, rc 2 →
NO_GO `derive`, autre → DEGRADED.

CACHE, BALAYAGE, EXPIRATION. À CHAQUE appel, tout dossier de plan de plus de `BALAYAGE_S` (24 h) est effacé,
pour tout dépôt et toute cible ; un apply sur un plan de plus de `PLAN_EXPIRE_S` (23 h) est refusé. Aucun verrou :
deux appels concurrents ne sont pas pris en charge (tâche de suite T-01M56T8DM4Y2B77ZKRCE0KT1H6). Le cache des
providers est partagé et « not guaranteed to be concurrency safe » (doc cli-config).

TRACE. Une ligne JSONL par identity, plan, apply, verify, drift dans `.agents/state/local/tfdeploy/runs.jsonl`
(ignoré) : cible, workspace, portée posée, HEAD, sha S du vert gelé, id et chemin de l'export, empreinte, comptes,
adresses, sha256 du planfile, verdict ; JAMAIS une valeur du plan, de l'état, d'une sortie ni d'un scanner. Un GO
dont la trace ne s'écrit pas devient DEGRADED (un plan GO non tracé ne pourrait pas être appliqué).

EXÉCUTION. Toujours des argv, jamais de shell ; stdout et stderr des enfants capturés ou jetés, jamais hérités ;
délais bornés (`DELAIS`). Chaque `.py` au plus 1600 lignes.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Mapping, NoReturn, Sequence


def _charger_frere(nom: str, fichier: str) -> ModuleType:
    """Le frère `fichier` du dossier de CE fichier, chargé PAR CHEMIN sous `nom` (réutilisé s'il est déjà ce
    fichier), enregistré dans `sys.modules` AVANT son exécution et retiré s'il échoue."""
    chemin = Path(__file__).resolve().with_name(fichier)
    existant = sys.modules.get(nom)
    if existant is not None and getattr(existant, "__file__", None) and Path(existant.__file__).resolve() == chemin:
        return existant
    spec = importlib.util.spec_from_file_location(nom, chemin) if chemin.is_file() else None
    if spec is None or spec.loader is None:
        raise ImportError(f"{chemin} : module frère absent")
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(nom, None)
        raise
    return module


tp = _charger_frere("_cadre_tfdeploy_plan", "tfdeploy_plan.py")
Refus = tp.Refus
Degrade = tp.Degrade
RC_GO, RC_NO_GO, RC_REFUS, RC_DEGRADED = tp.RC_GO, tp.RC_NO_GO, tp.RC_REFUS, tp.RC_DEGRADED

MOTIFS_REFUS = (
    "arguments", "config_absente", "config_invalide", "config_incomplete", "config_secret", "cible_inconnue",
    "workdir_racine", "workdir_absent", "backend_local", "arbre_sale", "head_non_relu", "etat_non_ignore",
    "sous_module", "lfs", "filtre_git", "identite_ecart", "portee_code_ecart", "portee_non_fixee", "prod_poste",
    "plan_inconnu", "plan_non_go", "plan_autre_cible", "plan_expire", "head_change", "export_altere",
    "apply_sans_decision", "destroy_non_approuve", "specs_illisible", "verbe_secret", "verbe_non_lecture",
)
MOTIFS_NO_GO = ("fmt", "init", "validate", "tflint", "plan", "scanner", "apply", "derive", "verify")
SOUS_COMMANDES = ("probe", "catalogue", "intake", "check-config", "identity", "plan", "apply", "verify", "drift")

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DEFAUT = Path(".agents") / "deploy" / "targets.json"
ETAT_REL = Path(".agents") / "state" / "local" / "tfdeploy"
TAMPON_REL = Path(".agents") / "state" / "local" / "VERIFY_STAMP.log"
FICHIER_TRACE = "runs.jsonl"
FORMAT_TAMPON = "at=%s\tsha=%s\tmode=%s\n"  # la ligne que la porte écrit sur un vert `--at` ; W29 l'épingle
PATHSPEC_RELU = (".", ":(exclude).agents/state", ":(exclude)runs")
REMEDE_RELU = ("une porte verte gelée sur HEAD, jouée par l'orchestrateur ; une tâche IaC si le diff depuis S touche "
               "l'IaC")
TAMPONS_MAX = 50
PLAN_EXPIRE_S = 23 * 3600
BALAYAGE_S = 24 * 3600
GRACE_S = 60
APPLY_INTERROMPU = ("apply interrompu : infrastructure possiblement partielle, verrou du backend possiblement tenu — "
                    "drift puis nouveau plan")
DELAIS = {"fmt": 120, "init": 900, "validate": 300, "tflint": 300, "plan": 3600, "show": 300, "apply": 3 * 3600,
          "output": 300, "drift": 3600, "identity": 120, "verify": 120, "scanner": 900, "version": 60}
TRIVY_ECARTEES = ("0.69.4",)
MASQUE = "<sensitive>"
SIGNAUX_INTERRUPTION = ("SIGTERM", "SIGHUP")

FOURNISSEURS = ("azure", "gcp", "aws")
ENVS = ("dev", "staging", "preprod", "prod")
NOM_CIBLE_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,62}\Z")
WORKSPACE_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9_-]{0,89}\Z")
REGION_RE = re.compile(r"\A[a-z0-9][a-z0-9-]{1,40}\Z")
GUID_RE = re.compile(r"\A[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\Z")
PROJET_GCP_RE = re.compile(r"\A[a-z][a-z0-9-]{4,28}[a-z0-9]\Z")
COMPTE_AWS_RE = re.compile(r"\A[0-9]{12}\Z")
PROFIL_RE = re.compile(r"\A[A-Za-z0-9_.@+=,-]{1,64}\Z")
RESOURCE_GROUP_RE = re.compile(r"\A[-\w.()]{1,90}\Z")
ETIQUETTE_RE = re.compile(r"\A[A-Za-z0-9_.-]{1,64}\Z")
CLE_BACKEND_RE = re.compile(r"\A[A-Za-z_][A-Za-z0-9_]{0,63}\Z")
TYPE_BACKEND_RE = re.compile(r"\A[a-z][a-z0-9_]{0,31}\Z")
SORTIE_RE = re.compile(r"\A[A-Za-z_][A-Za-z0-9_-]{0,127}\Z")
TACHE_RE = re.compile(r"\AT-(?:[0-9A-HJKMNP-TV-Z]{26}|[0-9]{1,15})\Z")
SHA256_RE = re.compile(r"\A[0-9a-f]{64}\Z")
SHA1_RE = re.compile(r"\A[0-9a-f]{40}\Z")
DESTROY_RE = re.compile(r"destroy\s+approuv(?:é|e)\s*:\s*([0-9]+)", re.IGNORECASE)
# Le jeton d'accord exigé dans la décision : en tête de ligne, sans mot de négation ni de retrait sur sa ligne.
APPROUVE_RE = re.compile(r"^[ \t]*apply[ \t]+approuv(?:é|e)\b(?![^\n]*\b(?:non|pas|refus\w*|report\w*|annul\w*|retir\w*"
                         r"|rejet\w*|suspend\w*)\b)", re.IGNORECASE | re.MULTILINE)

CHAMPS_COMMUNS = ("name", "provider", "env", "workdir", "workspace", "region", "backend", "auth_mode", "verify")
CHAMPS_FOURNISSEUR = {"azure": ("tenant_id", "subscription_id", "resource_group"), "gcp": ("project_id",),
                      "aws": ("account_id", "profile")}

# Le catalogue FERMÉ des questions (Q7) : `intake` ne rend que les ids dont le champ manque à la cible. Le
# workspace (défaut `default`), le profil aws et `verify` sont optionnels : jamais demandés.
CATALOGUE: tuple[dict[str, Any], ...] = (
    {"id": "Q-PROVIDER", "champ": "provider", "fournisseurs": ("*",),
     "question": "Quel fournisseur cloud porte cette cible : azure, gcp ou aws ?"},
    {"id": "Q-ENV", "champ": "env", "fournisseurs": ("*",),
     "question": "Quel environnement : dev, staging, preprod ou prod (la prod n'est jamais appliquée par le runner) ?"},
    {"id": "Q-WORKDIR", "champ": "workdir", "fournisseurs": ("*",),
     "question": "Quel sous-dossier du dépôt porte le module racine Terraform (jamais la racine) ?"},
    {"id": "Q-REGION", "champ": "region", "fournisseurs": ("*",), "question": "Quelle région de déploiement ?"},
    {"id": "Q-BACKEND", "champ": "backend", "fournisseurs": ("*",),
     "question": "Quel backend d'état DISTANT (type et identifiants non secrets : stockage, bucket, clé) ?"},
    {"id": "Q-AUTH-MODE", "champ": "auth_mode", "fournisseurs": ("*",),
     "question": "Comment l'identité s'authentifie-t-elle (CLI connectée, OIDC, identité managée, profil) ?"},
    {"id": "Q-AZ-TENANT", "champ": "tenant_id", "fournisseurs": ("azure",), "question": "Quel tenant Azure (tenant_id) ?"},
    {"id": "Q-AZ-SUBSCRIPTION", "champ": "subscription_id", "fournisseurs": ("azure",),
     "question": "Quelle souscription Azure (subscription_id) ?"},
    {"id": "Q-AZ-RESOURCE-GROUP", "champ": "resource_group", "fournisseurs": ("azure",),
     "question": "Quel resource group Azure ?"},
    {"id": "Q-GCP-PROJECT", "champ": "project_id", "fournisseurs": ("gcp",), "question": "Quel projet GCP (project_id) ?"},
    {"id": "Q-AWS-ACCOUNT", "champ": "account_id", "fournisseurs": ("aws",),
     "question": "Quel compte AWS (account_id, 12 chiffres) ?"},
)

# Clés et valeurs à forme de secret — un ÉCHANTILLON (une forme hors liste passe).
FRAGMENTS_CLE_SECRETE = ("secret", "password", "passwd", "token", "credential", "apikey", "api_key", "api-key",
                         "access_key", "accesskey", "account_key", "private_key", "privatekey", "connection_string",
                         "connectionstring", "sas_")
VALEURS_SECRETES: tuple[tuple[str, Any], ...] = (
    ("cle_aws", re.compile(r"(?:AKIA|ASIA|AGPA|AIDA|AROA|ANPA|ANVA|AIPA)[0-9A-Z]{16}")),
    ("cle_privee", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("chaine_azure", re.compile(r"(?i)AccountKey=|SharedAccessKey=|SharedAccessSignature=|[?&]sig=[A-Za-z0-9%]")),
    ("cle_google", re.compile(r"AIza[0-9A-Za-z_-]{35}")),
    ("jeton_github", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}")),
    ("jeton_slack", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}")),
    ("affectation", re.compile(r"(?i)\b(?:password|passwd|pwd|secret|token)\s*[=:]\s*\S")),
)

# Verbes de CLI qui rendent un SECRET — ÉCHANTILLON (docstring, VERIFY). Recopiée dans `iac_guard` ; verdicts tenus
# égaux par `.agents/evals/test_terraform_deploy_skill.py`.
VERBES_SECRETS: dict[str, tuple[Any, ...]] = {
    "mots": ("get-secret-value", "batch-get-secret-value", "get-session-token", "get-federation-token",
             "get-role-credentials", "export-credentials", "get-login-password", "get-credentials", "get-token",
             "get-access-token", "get-authorization-token", "generate-db-auth-token", "generate-login-token",
             "get-auth-string", "print-access-token", "print-identity-token", "config-helper",
             "show-connection-string", "list-connection-strings", "list-publishing-credentials",
             "list-publishing-profiles", "generate-sas", "decrypt", "list-keys"),
    "prefixes": ("assume-role",),
    "couples": ("keys list", "key list", "credential list", "admin-key show", "connection-string show",
                "connection-string list", "secret show", "secret download", "credential show", "versions access",
                "appsettings list"),
    "conditionnels": (("get-parameter", "--with-decryption"), ("get-parameters", "--with-decryption"),
                      ("get-parameters-by-path", "--with-decryption"), ("get-parameter-history", "--with-decryption"),
                      ("secret list", "--show-values"), ("acr login", "--expose-token")),
    "aws_configure_get": ("secret", "token"),
    "exceptions": (("list-keys", "aws", "kms"), ("keys list", "*", "kms")),
}
VERIFY_OUTILS = ("az", "gcloud", "aws")
# Opérations aws admises par leur préfixe (`get-*`) mais qui ÉCRIVENT un fichier local (outfile) — ÉCHANTILLON ;
# le refus d'un mot positionnel après les options (`juger_argv_verify`) couvre la forme ordinaire des autres.
AWS_OPS_FICHIER = ("get-object", "get-object-torrent", "get-export", "get-sdk", "get-job-output", "get-snapshot-block",
                   "get-media", "get-clip", "get-package-version-asset", "get-work-unit-results",
                   # T-01M52X1W3WPKCWX1DC36NMKJB6 (2026-10-19, CORR-5a T5) : quatre outfile de plus.
                   "get-latest-configuration", "get-configuration", "get-raw-message-content",
                   "get-media-for-fragment-list")
# Options aws SANS valeur (drapeaux) — ÉCHANTILLON, plus toute `--no-*` : le mot qui les suit est un positionnel.
AWS_DRAPEAUX = ("--debug", "--dry-run", "--cli-auto-prompt", "--no-paginate")
MOTS_MUTATION_GCLOUD = ("create", "delete", "update", "set", "add", "remove", "deploy", "start", "stop", "restart",
                        "reset", "import", "export", "patch", "apply", "run", "ssh", "scp", "enable", "disable",
                        "attach", "detach", "resize", "move", "rename", "rollback", "cancel", "undelete", "replace",
                        "upload", "copy", "cp", "mv", "rm", "sign", "login", "activate", "revoke", "execute")
OUTILS_PROBE = ("terraform", "tflint", "trivy", "checkov", "az", "gcloud", "aws", "git")
OUTILS_REQUIS = ("terraform", "trivy", "checkov")


class Interrompu(BaseException):
    """SIGTERM ou SIGHUP reçu : levée dans le fil principal, comme KeyboardInterrupt pour SIGINT."""


def _sur_signal(signum: int, _frame: object) -> NoReturn:
    raise Interrompu(signal.Signals(signum).name)


def _maintenant() -> float:
    """L'horloge du runner — UNE seule, que les bancs remplacent (âge du plan, id, balayage)."""
    return time.time()


def _iso(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- exécution d'un outil ----------------------------------------------------------------------------------------

def _arreter(proc: subprocess.Popen) -> None:
    """SIGINT (terraform s'arrête proprement et rend son verrou), puis SIGKILL passé `GRACE_S`."""
    if proc.poll() is not None:
        return
    try:
        proc.send_signal(signal.SIGINT)
        proc.wait(timeout=GRACE_S)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    except OSError:
        pass


def executer(argv: Sequence[str], *, cwd: Path | None, env: Mapping[str, str], delai: int, outil: str,
             capturer: bool = False) -> tuple[int, bytes]:
    """`argv` sans shell, stdin fermé, stderr jeté, stdout capturé ou jeté ; absent ou hors délai = `Degrade`."""
    try:
        proc = subprocess.Popen(list(argv), cwd=None if cwd is None else str(cwd), env=dict(env),
                                stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                stdout=subprocess.PIPE if capturer else subprocess.DEVNULL)
    except FileNotFoundError as e:
        raise Degrade(outil, f"{outil} absent du PATH") from e
    except OSError as e:
        raise Degrade(f"{outil} (non lançable)", f"{outil} non lançable ({type(e).__name__})") from e
    try:
        sortie, _ = proc.communicate(timeout=delai)
    except subprocess.TimeoutExpired as e:
        _arreter(proc)
        raise Degrade(f"{outil} (délai {delai} s dépassé)", f"délai dépassé: {outil}") from e
    except BaseException:
        _arreter(proc)
        raise
    return proc.returncode, sortie or b""


def _present(outil: str, env: Mapping[str, str]) -> bool:
    return shutil.which(outil, path=env.get("PATH", "")) is not None


# --- configuration -----------------------------------------------------------------------------------------------

def chemin_config(arg: str | None) -> Path:
    return Path(os.path.abspath(arg)) if arg else ROOT / CONFIG_DEFAUT


def _cle_secrete(cle: str) -> bool:
    c = cle.casefold()
    return c == "sas" or any(f in c for f in FRAGMENTS_CLE_SECRETE)


def detecter_secret(valeur: Any, ou: str = "$") -> None:
    """`config_secret` sur la PREMIÈRE clé ou valeur à forme de secret ; la valeur n'est jamais recopiée."""
    if isinstance(valeur, dict):
        for cle, v in valeur.items():
            if isinstance(cle, str) and _cle_secrete(cle):
                raise Refus("config_secret", f"{ou}.{cle} : clé à forme de secret — un secret ne s'écrit jamais dans "
                                             "la configuration (variables d'authentification de l'environnement)")
            detecter_secret(v, f"{ou}.{cle}")
    elif isinstance(valeur, list):
        for i, v in enumerate(valeur):
            detecter_secret(v, f"{ou}[{i}]")
    elif isinstance(valeur, str):
        for nom, motif in VALEURS_SECRETES:
            if motif.search(valeur):
                raise Refus("config_secret", f"{ou} : valeur à forme de secret (motif {nom}) — retirez-la et faites "
                                             "tourner le secret")


def lire_config(chemin: Path) -> dict[str, Any]:
    """Le JSON de configuration, sans secret, à la structure de tête valide (noms uniques et bien formés)."""
    if not chemin.is_file():
        raise Refus("config_absente", f"{chemin} absent — gabarit : .agents/ref/deploy-targets.example.json")
    try:
        brut = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise Refus("config_invalide", f"{chemin} : JSON illisible ({type(e).__name__})") from e
    if not isinstance(brut, dict) or not isinstance(brut.get("targets"), list):
        raise Refus("config_invalide", f"{chemin} : objet portant une liste `targets` attendu")
    detecter_secret(brut)
    inconnues = sorted(k for k in brut if not str(k).startswith("_") and k != "targets")
    if inconnues:
        raise Refus("config_invalide", f"{chemin} : clé(s) inconnue(s) {inconnues}")
    vus: set[str] = set()
    for i, c in enumerate(brut["targets"]):
        nom = c.get("name") if isinstance(c, dict) else None
        if not isinstance(nom, str) or not NOM_CIBLE_RE.match(nom):
            raise Refus("config_invalide", f"targets[{i}] : `name` absent ou hors forme {NOM_CIBLE_RE.pattern}")
        if nom in vus:
            raise Refus("config_invalide", f"cible « {nom} » déclarée deux fois")
        vus.add(nom)
    return brut


def cible_brute(config: Mapping[str, Any], nom: str | None) -> dict[str, Any]:
    if not nom:
        raise Refus("arguments", "--target est obligatoire")
    for c in config["targets"]:
        if c.get("name") == nom:
            return c
    raise Refus("cible_inconnue", f"cible « {nom} » absente de la configuration ({[c['name'] for c in config['targets']]})")


def _vide(v: Any) -> bool:
    return v is None or v == "" or v == {} or v == []


def questions_absentes(brut: Mapping[str, Any]) -> list[str]:
    """Les ids du catalogue dont le champ manque — ceux du fournisseur seulement quand il est connu."""
    fournisseur = brut.get("provider") if brut.get("provider") in FOURNISSEURS else None
    return [q["id"] for q in CATALOGUE
            if (q["fournisseurs"] == ("*",) or fournisseur in q["fournisseurs"]) and _vide(brut.get(q["champ"]))]


def _forme(ok: bool, nom: str, champ: str, attendu: str) -> None:
    if not ok:
        raise Refus("config_invalide", f"cible « {nom} » : `{champ}` hors forme ({attendu})")


def _workdir(nom: str, brut: Any) -> str:
    _forme(isinstance(brut, str) and "\\" not in brut and not brut.startswith("/"), nom, "workdir",
           "chemin relatif POSIX")
    parties = [p for p in brut.split("/") if p not in ("", ".")]
    _forme(".." not in parties, nom, "workdir", "sans `..`")
    return "/".join(parties)


def _backend(nom: str, brut: Any) -> dict[str, str]:
    _forme(isinstance(brut, dict) and isinstance(brut.get("type"), str) and bool(TYPE_BACKEND_RE.match(brut["type"])),
           nom, "backend", "objet portant un `type`")
    sortie = {"type": brut["type"]}
    for cle, v in brut.items():
        if cle == "type":
            continue
        _forme(isinstance(cle, str) and bool(CLE_BACKEND_RE.match(cle)) and isinstance(v, (str, int, bool))
               and not isinstance(v, float), nom, f"backend.{cle}", "clé simple, valeur chaîne, entier ou booléen")
        sortie[cle] = ("true" if v else "false") if isinstance(v, bool) else str(v)
    return sortie


def _verify(nom: str, brut: Any) -> list[dict[str, Any]]:
    _forme(isinstance(brut, list), nom, "verify", "liste")
    items = []
    for i, item in enumerate(brut):
        ou = f"verify[{i}]"
        _forme(isinstance(item, dict) and (("argv" in item) != ("output" in item))
               and set(item) <= {"argv", "output", "expect"}, nom, ou, "{argv|output, expect}")
        expect = item.get("expect", {})
        _forme(isinstance(expect, dict) and all(isinstance(k, str) for k in expect), nom, f"{ou}.expect",
               "objet chemin -> valeur")
        if "argv" in item:
            argv = item["argv"]
            _forme(isinstance(argv, list) and bool(argv) and all(isinstance(a, str) and a for a in argv), nom,
                   f"{ou}.argv", "liste de chaînes non vide")
            items.append({"argv": list(argv), "expect": dict(expect)})
        else:
            _forme(isinstance(item["output"], str) and bool(SORTIE_RE.match(item["output"])), nom, f"{ou}.output",
                   "nom de sortie")
            items.append({"output": item["output"], "expect": dict(expect)})
    return items


def normaliser(brut: Mapping[str, Any], strict: bool = True) -> dict[str, Any]:
    """La cible validée (formes), complétée (`workspace`) ; `strict` : complète, workdir et backend admis."""
    nom = str(brut.get("name"))
    fournisseur = brut.get("provider")
    _forme(fournisseur is None or fournisseur in FOURNISSEURS, nom, "provider", "|".join(FOURNISSEURS))
    connus = set(CHAMPS_COMMUNS) | (set(CHAMPS_FOURNISSEUR[fournisseur]) if fournisseur else set())
    inconnues = sorted(k for k in brut if not str(k).startswith("_") and k not in connus)
    if inconnues:
        raise Refus("config_invalide", f"cible « {nom} » : champ(s) inconnu(s) ou d'un autre fournisseur {inconnues}")
    cible: dict[str, Any] = {"name": nom, "provider": fournisseur, "workspace": "default", "verify": []}
    formes = {"env": (lambda v: v in ENVS, "|".join(ENVS)), "region": (lambda v: bool(REGION_RE.match(v)), "région"),
              "tenant_id": (lambda v: bool(GUID_RE.match(v)), "GUID"),
              "subscription_id": (lambda v: bool(GUID_RE.match(v)), "GUID"),
              "resource_group": (lambda v: bool(RESOURCE_GROUP_RE.match(v)), "nom de resource group"),
              "project_id": (lambda v: bool(PROJET_GCP_RE.match(v)), "id de projet GCP"),
              "account_id": (lambda v: bool(COMPTE_AWS_RE.match(v)), "12 chiffres"),
              "profile": (lambda v: bool(PROFIL_RE.match(v)), "nom de profil"),
              "workspace": (lambda v: bool(WORKSPACE_RE.match(v)), "nom de workspace"),
              "auth_mode": (lambda v: bool(ETIQUETTE_RE.match(v)), "étiquette")}
    for champ, (test, attendu) in formes.items():
        if not _vide(brut.get(champ)):
            v = brut[champ]
            _forme(isinstance(v, str) and test(v), nom, champ, attendu)
            cible[champ] = v
    if not _vide(brut.get("workdir")):
        cible["workdir"] = _workdir(nom, brut["workdir"])
    if not _vide(brut.get("backend")):
        cible["backend"] = _backend(nom, brut["backend"])
    if brut.get("verify") is not None:
        cible["verify"] = _verify(nom, brut["verify"])
    if not strict:
        return cible
    manquantes = questions_absentes(brut)
    if manquantes:
        raise Refus("config_incomplete", f"cible « {nom} » incomplète ; questions du catalogue : {manquantes}")
    if cible["workdir"] == "" or ".agents" in cible["workdir"].split("/"):
        raise Refus("workdir_racine", f"cible « {nom} » : workdir « {brut['workdir']} » est la racine ou porte "
                                      "`.agents` — un sous-dossier dédié est exigé")
    if cible["backend"]["type"] == "local":
        raise Refus("backend_local", f"cible « {nom} » : backend local — le runner travaille dans un export jetable "
                                     "où l'état se perdrait ; un backend distant est exigé")
    return cible


def _resume_cible(cible: Mapping[str, Any]) -> dict[str, Any]:
    return {k: cible.get(k) for k in ("name", "provider", "env", "workdir", "workspace")}


# --- contrôles d'arbre ---------------------------------------------------------------------------------------------

def head_courant(racine: Path) -> str:
    p = tp.git(racine, "rev-parse", "--verify", "HEAD^{commit}")
    sha = p.stdout.decode("ascii", "replace").strip()
    if p.returncode != 0 or not SHA1_RE.match(sha):
        raise Refus("head_non_relu", "HEAD illisible : un dépôt git avec au moins un commit est exigé")
    return sha


def _relatif(racine: Path, chemin: Path) -> str | None:
    try:
        return Path(os.path.realpath(chemin)).relative_to(os.path.realpath(racine)).as_posix()
    except ValueError:
        return None


def verifier_arbre_propre(racine: Path, cible: Mapping[str, Any], config: Path) -> None:
    """`arbre_sale` : workdir ou config modifiés, config non suivie ou hors du dépôt."""
    rel = _relatif(racine, config)
    if rel is None:
        raise Refus("arbre_sale", f"{config} est hors du dépôt : la configuration doit être COMMITÉE")
    p = tp.git(racine, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--", cible["workdir"], rel)
    if p.returncode != 0:
        raise Refus("arbre_sale", f"git status rc={p.returncode} : état de l'arbre invérifiable (hors dépôt git ?)")
    sales = [e.decode("utf-8", "replace") for e in p.stdout.split(b"\0") if e]
    if sales:
        raise Refus("arbre_sale", f"{len(sales)} modification(s) non commitée(s) sous {cible['workdir']} ou {rel} : "
                                  f"{sales[:10]} — commitez (tâche IaC au board) ou annulez")
    suivi = tp.git(racine, "ls-files", "--error-unmatch", "--", rel)
    if suivi.returncode != 0:
        raise Refus("arbre_sale", f"{rel} n'est pas suivi par git : la configuration doit être COMMITÉE")


def lire_tampons(texte: str) -> list[str]:
    """Les shas des lignes `mode=frozen` à `at` lisible, dans l'ordre du journal (mêmes filtres que
    `tasks_gardes.cycle_precedent`, relus ici sans l'importer)."""
    shas = []
    for ligne in texte.splitlines():
        if not ligne.strip():
            continue
        champs = dict(c.split("=", 1) for c in ligne.split("\t") if "=" in c)
        if champs.get("mode", "").strip() != "frozen":
            continue
        at, sha = champs.get("at", "").strip(), champs.get("sha", "").strip().lower()
        if at and at != "unknown" and SHA1_RE.match(sha):
            shas.append(sha)
    return shas


def verifier_head_relu(racine: Path, head: str) -> str:
    """`head_non_relu` (docstring, CONTRÔLES D'ARBRE) ; rend le sha S du vert gelé qui couvre `head` — le sha de
    HEAD lu UNE fois par l'appelant, jamais le nom `HEAD`, qui peut bouger entre deux appels de git."""
    chemin = racine / TAMPON_REL
    try:
        texte = chemin.read_text(encoding="utf-8")
    except (OSError, ValueError) as e:
        raise Refus("head_non_relu", f"journal des verts gelés absent ou illisible ({type(e).__name__}) : aucun "
                                     f"arbre relu par une porte — remède : {REMEDE_RELU}") from e
    candidats: list[str] = []
    for sha in reversed(lire_tampons(texte)):
        if sha not in candidats:
            candidats.append(sha)
    candidats = candidats[:TAMPONS_MAX]
    if not candidats:
        raise Refus("head_non_relu", f"aucune ligne mode=frozen dans le journal des verts gelés — remède : "
                                     f"{REMEDE_RELU}")
    ancetres = []
    for s in candidats:
        if tp.git(racine, "merge-base", "--is-ancestor", s, head).returncode != 0:
            continue
        ancetres.append(s)
        if tp.git(racine, "diff", "--quiet", s, head, "--", *PATHSPEC_RELU).returncode == 0:
            return s
    if not ancetres:
        raise Refus("head_non_relu", f"aucun vert gelé du journal n'est un ancêtre de HEAD — remède : {REMEDE_RELU}")
    log = tp.git(racine, "log", "--oneline", "--no-decorate", "-n", "20", f"{ancetres[0]}..{head}", "--",
                 *PATHSPEC_RELU)
    commits = [ligne for ligne in log.stdout.decode("utf-8", "replace").splitlines() if ligne.strip()]
    raise Refus("head_non_relu", f"l'arbre de HEAD diffère du dernier vert gelé {ancetres[0][:12]} (S) ; commits "
                                 f"depuis : {commits} — remède : {REMEDE_RELU}")


def verifier_etat_ignore(racine: Path, cible: Mapping[str, Any]) -> None:
    for rel in (f"{cible['workdir']}/terraform.tfstate", f"{cible['workdir']}/.terraform/x"):
        p = tp.git(racine, "check-ignore", "-q", "--", rel)
        if p.returncode != 0:
            raise Refus("etat_non_ignore", f"{rel} n'est pas ignoré par git (rc={p.returncode}) : l'état et "
                                           "`.terraform/` doivent l'être — bloc Terraform du `.gitignore`")


# --- identité ------------------------------------------------------------------------------------------------------

def verifier_identite(cible: Mapping[str, Any], env: Mapping[str, str]) -> dict[str, Any]:
    """`identite_ecart` ou DEGRADED (CLI absente) ; ne relaie jamais la sortie de la CLI."""
    fournisseur = cible["provider"]
    if fournisseur == "azure":
        argv = ["az", "account", "show", "--subscription", cible["subscription_id"], "--output", "json"]
        attendus = (("id", cible["subscription_id"]), ("tenantId", cible["tenant_id"]))
    elif fournisseur == "gcp":
        argv = ["gcloud", "projects", "describe", cible["project_id"], "--format=json"]
        attendus = (("projectId", cible["project_id"]),)
    else:
        argv = ["aws", "sts", "get-caller-identity", "--output", "json"]
        attendus = (("Account", cible["account_id"]),)
    outil = argv[0]
    if not _present(outil, env):
        raise Degrade(outil, f"{outil} absent du PATH : identité invérifiable")
    rc, sortie = executer(argv, cwd=None, env=env, delai=DELAIS["identity"], outil=outil, capturer=True)
    commande = " ".join(argv[:3])
    # m6 : sans `profile`, la liste blanche écarte l'AWS_PROFILE ambiant (SSO) — le refus le dit, sinon on boucle.
    profil = (" ; AWS_PROFILE ambiant écarté : déclarer `profile` dans la cible"
              if fournisseur == "aws" and not cible.get("profile") else "")
    if rc != 0:
        raise Refus("identite_ecart", f"`{commande}` rc={rc} : l'identité courante n'atteint pas la portée de la "
                                      f"cible{profil}")
    try:
        data = json.loads(sortie.decode("utf-8"))
    except ValueError as e:
        raise Refus("identite_ecart", f"`{commande}` : sortie JSON illisible{profil}") from e
    for cle, attendu in attendus:
        rendu = data.get(cle) if isinstance(data, dict) else None
        if str(rendu).casefold() != str(attendu).casefold():
            raise Refus("identite_ecart", f"`{commande}` : `{cle}` rendu ≠ celui de la cible{profil}")
    return {"outil": outil, "verifie": [c for c, _a in attendus]}


# --- décision tracée (SPECS par l'interface etat_lecture) ------------------------------------------------------------

_ETAT_MOD: ModuleType | None = None


def _etat_module() -> ModuleType:
    """L'interface `etat_lecture.py`, frère de CE fichier, chargée par chemin sous un nom privé, mise en cache."""
    global _ETAT_MOD
    if _ETAT_MOD is None:
        _ETAT_MOD = _charger_frere("_tfdeploy_etat_lecture", "etat_lecture.py")
    return _ETAT_MOD


def _entrees_specs(racine: Path) -> list[Any]:
    try:
        el = _etat_module()
    except (OSError, ImportError) as e:
        raise Refus("specs_illisible", f"module etat_lecture.py inchargeable ({type(e).__name__})") from e
    try:
        erreurs = el.erreurs_de_lecture("specs")
    except (OSError, ImportError) as e:
        raise Refus("specs_illisible", f"module specs.py inchargeable ({type(e).__name__})") from e
    try:
        if not el.present(racine, "specs"):
            return []
        return el.entrees_specs(racine)
    except (*erreurs, OSError, ValueError) as e:
        raise Refus("specs_illisible", f"journal SPECS illisible ou en deux formes ({type(e).__name__})") from e


def nomme(texte: str, terme: str) -> bool:
    """`terme` en MOT ENTIER, casse repliée ; `.` et `-` comptent comme des lettres."""
    motif = r"(?<![\w.-])" + re.escape(terme.casefold()) + r"(?![\w-]|\.[\w-])"
    return re.search(motif, texte.casefold()) is not None


def _porte_hex(texte: str, valeur: str) -> bool:
    return re.search(r"(?<![0-9a-f])" + re.escape(valeur) + r"(?![0-9a-f])", texte) is not None


def verifier_decision(racine: Path, tache: str, cible: str, plan_sha: str, head: str, destroy: int) -> dict[str, Any]:
    """(9) `apply_sans_decision`, (10) `destroy_non_approuve` ; rend l'id de la décision retenue — la PLUS RÉCENTE
    qui nomme le triplet, qui doit porter le jeton `apply approuvé` EN TÊTE DE LIGNE, sans mot de négation ni de
    retrait sur cette ligne (`APPROUVE_RE` ; un refus ou un report n'autorise rien)."""
    entrees = [e for e in _entrees_specs(racine)
               if isinstance(e, dict) and e.get("task") == tache and e.get("kind") == "decision"]
    for e in reversed(entrees):
        texte = "\n".join(str(e.get(k) or "") for k in ("title", "text"))
        replie = texte.casefold()
        if not (nomme(texte, cible) and _porte_hex(replie, plan_sha) and _porte_hex(replie, head)):
            continue
        if not APPROUVE_RE.search(texte):
            raise Refus("apply_sans_decision", f"la décision {e.get('id')}, la plus récente de {tache} qui nomme la "
                                               f"cible « {cible} », le planfile et HEAD, ne porte pas le jeton `apply "
                                               "approuvé` en tête de ligne sans négation ni retrait sur sa ligne : un "
                                               "refus ou un report n'autorise rien — le pilote écrit `apply approuvé` "
                                               "en tête de ligne dans une nouvelle décision")
        approuves = DESTROY_RE.findall(texte)
        approuve = int(approuves[-1]) if approuves else None
        if destroy and approuve != destroy:
            raise Refus("destroy_non_approuve", f"le plan détruit {destroy} ressource(s) ; la décision {e.get('id')} "
                                                f"doit porter `destroy approuvé: {destroy}`")
        if not destroy and approuve not in (None, 0):
            raise Refus("destroy_non_approuve", f"la décision {e.get('id')} approuve {approuve} destruction(s), le "
                                                "plan n'en porte aucune")
        return {"id": e.get("id"), "destroy_approuve": approuve}
    raise Refus("apply_sans_decision", f"aucune entrée kind=decision de {tache} ne nomme à la fois la cible « {cible} », "
                                       f"le sha256 du planfile {plan_sha} et HEAD {head} avec le jeton `apply approuvé` "
                                       f"({len(entrees)} décision(s) lue(s)) — elle s'écrit par la session appelante, "
                                       "jamais par l'agent")


# --- verify : verbes secrets, liste blanche de lecture --------------------------------------------------------------

def verbe_secret(argv: Sequence[str]) -> str | None:
    """L'entrée de `VERBES_SECRETS` que porte `argv`, ou None (docstring : `VERBES_SECRETS`)."""
    if not argv:
        return None
    outil = os.path.basename(str(argv[0])).casefold()
    jetons = [str(a).casefold() for a in argv[1:]]
    mots = [j for j in jetons if not j.startswith("-")]
    options = {j.lstrip("-").split("=", 1)[0] for j in jetons if j.startswith("-")}
    couples = [f"{a} {b}" for a, b in zip(mots, mots[1:])]

    def exempte(entree: str) -> bool:
        # Le mot d'exception doit être le SERVICE (premier mot) : `keys list --account-name kms` n'est pas kms.
        return any(e == entree and o in ("*", outil) and mots[:1] == [mot]
                   for e, o, mot in VERBES_SECRETS["exceptions"])

    for m in mots:
        if m in VERBES_SECRETS["mots"] and not exempte(m):
            return m
        if m.startswith(VERBES_SECRETS["prefixes"]):
            return m
    for c in VERBES_SECRETS["couples"]:
        if c in couples and not exempte(c):
            return c
    for entree, drapeau in VERBES_SECRETS["conditionnels"]:
        if (entree in mots or entree in couples) and drapeau.lstrip("-") in options:
            return f"{entree} {drapeau}"
    if outil == "aws":
        for i, c in enumerate(couples):
            if c == "configure get" and i + 2 < len(mots):
                cle = mots[i + 2]
                if any(s in cle for s in VERBES_SECRETS["aws_configure_get"]):
                    return f"configure get {cle}"
    return None


def _positionnel_aws(options: Sequence[str]) -> str | None:
    """Le premier mot de `options` (la suite de l'argv aws dès sa première option) qui ne suit pas DIRECTEMENT une
    option écrite sans `=` — un positionnel, donc l'`outfile` d'aws ; None s'il n'y en a pas. Un drapeau sans
    valeur (`AWS_DRAPEAUX`, toute `--no-*`) n'attend rien : le mot qui le suit est un positionnel."""
    valeur_attendue = False
    for jeton in options:
        if jeton.startswith("-"):
            drapeau = jeton in AWS_DRAPEAUX or jeton.startswith("--no-")
            valeur_attendue = "=" not in jeton and not drapeau
            continue
        if not valeur_attendue:
            return jeton
        valeur_attendue = False
    return None


def juger_argv_verify(argv: Sequence[str]) -> tuple[str, str] | None:
    """(motif, détail) d'un argv de `verify` refusé, ou None s'il est admis (docstring, VERIFY)."""
    secret = verbe_secret(argv)
    if secret is not None:
        return "verbe_secret", f"`{secret}` rend un secret (VERBES_SECRETS) : jamais dans verify"
    if not argv or argv[0] not in VERIFY_OUTILS:
        return "verbe_non_lecture", f"outil {argv[0] if argv else '?'!r} hors de {list(VERIFY_OUTILS)} (nom nu exigé)"
    mots: list[str] = []
    for a in argv[1:]:
        if a.startswith("-"):
            break
        mots.append(a)
    outil = argv[0]
    if not mots:
        return "verbe_non_lecture", f"{outil} : commande absente ou option avant la commande (forme non lue)"
    if outil == "az":
        verbe = mots[-1]
        admis = verbe in ("show", "list") or verbe.startswith("get-")
    elif outil == "aws":
        verbe = mots[1] if len(mots) > 1 else mots[0]
        if verbe in AWS_OPS_FICHIER:
            return "verbe_non_lecture", f"aws : `{verbe}` écrit un fichier local (AWS_OPS_FICHIER) : jamais dans verify"
        positionnel = _positionnel_aws(argv[1 + len(mots):])
        if positionnel is not None:
            return "verbe_non_lecture", (f"aws : mot positionnel {positionnel!r} après les options — un fichier de sortie "
                                         "(outfile) ; une valeur par option, une liste en JSON (un seul jeton)")
        admis = len(mots) > 1 and verbe.startswith(("describe-", "list-", "get-"))
    else:
        rang = next((i for i, m in enumerate(mots) if m in ("describe", "list")), None)
        verbe = mots[rang] if rang is not None else mots[-1]
        admis = bool(rang) and not any(m in MOTS_MUTATION_GCLOUD for m in mots[:rang])
    if admis:
        return None
    return "verbe_non_lecture", f"{outil} : verbe `{verbe}` hors de la liste blanche de lecture"


def juger_verifications(items: Sequence[Mapping[str, Any]]) -> None:
    for i, item in enumerate(items):
        if "argv" in item:
            refus = juger_argv_verify(item["argv"])
            if refus is not None:
                raise Refus(refus[0], f"verify[{i}] : {refus[1]}")


_ABSENT = object()


def _lire_chemin(data: Any, chemin: str) -> Any:
    if chemin == "":
        return data
    for part in chemin.split("."):
        if isinstance(data, dict) and part in data:
            data = data[part]
        elif isinstance(data, list) and part.isdigit() and int(part) < len(data):
            data = data[int(part)]
        else:
            return _ABSENT
    return data


def masquer_sorties(brut: Any) -> dict[str, dict[str, Any]]:
    """`output -json` → {nom: {type, sensible, valeur}}, valeur remplacée par `MASQUE` si `sensitive` — AVANT tout
    traitement. Une forme inattendue lève `ValueError`."""
    if not isinstance(brut, dict):
        raise ValueError("output -json : objet attendu")
    sorties = {}
    for nom, entree in brut.items():
        if not isinstance(entree, dict):
            raise ValueError("output -json : entrée hors forme")
        sensible = entree.get("sensitive") is True
        type_ = entree.get("type")
        sorties[str(nom)] = {"type": type_ if isinstance(type_, (str, list)) else "?", "sensible": sensible,
                             "valeur": MASQUE if sensible else entree.get("value")}
    return sorties


def _resultat_expects(data: Any, expect: Mapping[str, Any]) -> dict[str, str]:
    return {chemin: ("ok" if _lire_chemin(data, chemin) == attendu else "ko") for chemin, attendu in expect.items()}


def _verifier_sortie(item: Mapping[str, Any], sorties: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    nom = item["output"]
    sortie = sorties.get(nom)
    if sortie is None:
        return {"type": "output", "output": nom, "present": False, "expects": {}, "ok": False}
    expects = _resultat_expects(sortie["valeur"], item["expect"])
    return {"type": "output", "output": nom, "present": True, "sensible": sortie["sensible"], "expects": expects,
            "ok": all(v == "ok" for v in expects.values())}


def _verifier_cli(item: Mapping[str, Any], env: Mapping[str, str]) -> dict[str, Any]:
    argv = item["argv"]
    if not _present(argv[0], env):
        raise Degrade(argv[0], f"{argv[0]} absent du PATH : vérification impossible")
    rc, sortie = executer(argv, cwd=None, env=env, delai=DELAIS["verify"], outil=argv[0], capturer=True)
    data: Any = _ABSENT
    if item["expect"]:
        try:
            data = json.loads(sortie.decode("utf-8"))
        except ValueError:
            data = _ABSENT
    expects = {c: ("ok" if rc == 0 and v == "ok" else "ko") for c, v in _resultat_expects(data, item["expect"]).items()}
    return {"type": "cli", "outil": argv[0], "rc": rc, "expects": expects,
            "ok": rc == 0 and all(v == "ok" for v in expects.values())}


# --- trace -----------------------------------------------------------------------------------------------------------

def chemin_trace(racine: Path) -> Path:
    return racine / ETAT_REL / FICHIER_TRACE


def ecrire_trace(racine: Path, enreg: Mapping[str, Any]) -> Path:
    chemin = chemin_trace(racine)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with open(chemin, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(enreg, ensure_ascii=True, sort_keys=True, default=str) + "\n")
    return chemin


def lire_traces(racine: Path) -> list[dict[str, Any]]:
    """Les lignes LISIBLES de la trace (une ligne illisible est sautée : trace non authentifiée, nommé)."""
    try:
        lignes = chemin_trace(racine).read_text(encoding="utf-8").splitlines()
    except (OSError, ValueError):
        return []
    enregs = []
    for ligne in lignes:
        try:
            e = json.loads(ligne)
        except ValueError:
            continue
        if isinstance(e, dict):
            enregs.append(e)
    return enregs


def trouver_plan(racine: Path, plan_sha: str) -> dict[str, Any] | None:
    for e in reversed(lire_traces(racine)):
        if e.get("commande") == "plan" and e.get("planfile_sha256") == plan_sha:
            return e
    return None


# --- étapes communes ---------------------------------------------------------------------------------------------

def _charger_cible(args: argparse.Namespace, trace: dict[str, Any], prod_interdite: bool = False,
                   strict: bool = True) -> tuple[dict[str, Any], Path]:
    chemin = chemin_config(args.config)
    brut = cible_brute(lire_config(chemin), args.target)
    trace["cible"] = {"name": brut.get("name"), "env": brut.get("env"), "provider": brut.get("provider")}
    if prod_interdite and brut.get("env") == "prod":
        raise Refus("prod_poste", f"cible « {brut.get('name')} » env prod : plan, drift et verify seulement ; l'apply "
                                  "prod n'a de chemin que par la CI (T-01M56T7S1AWZ3Z6TEP8MVPGFDA)")
    cible = normaliser(brut, strict=strict)
    trace["cible"] = _resume_cible(cible)
    return cible, chemin


def _env_cible(cible: Mapping[str, Any], trace: dict[str, Any], exiger_terraform: bool = True) -> dict[str, str]:
    if exiger_terraform and not _present("terraform", os.environ):
        raise Degrade("terraform", "terraform absent du PATH")
    plugin, tfrc = tp.preparer_cache()
    trace["portee"] = tp.portee_posee(cible)
    return tp.env_terraform(cible, os.environ, plugin, tfrc)


def _travail(racine: Path, dossier: Path, cible: Mapping[str, Any], head: str) -> Path:
    """L'export du sha `head` (HEAD relu UNE fois, tracé) puis `<export>/<workdir>`, qui doit exister DANS l'export
    (`workdir_absent`)."""
    export = tp.exporter(racine, dossier, head)
    travail = export / cible["workdir"]
    reel, base = os.path.realpath(travail), os.path.realpath(export)
    if not os.path.isdir(travail) or not reel.startswith(base + os.sep):
        raise Refus("workdir_absent", f"workdir « {cible['workdir']} » absent de HEAD ou hors de l'export")
    return travail


def _no_go(trace: dict[str, Any], motif: str, detail: str) -> int:
    trace.update(verdict="NO_GO", motif=motif, detail=detail)
    return RC_NO_GO


def _go(trace: dict[str, Any]) -> int:
    trace["verdict"] = "GO"
    return RC_GO


def _terraform(etape: str, suite: Sequence[str], travail: Path, env: Mapping[str, str],
               trace: dict[str, Any]) -> int:
    rc, _ = executer(["terraform", *suite], cwd=travail, env=env, delai=DELAIS[etape], outil="terraform")
    trace.setdefault("etapes", {})[etape] = rc
    return rc


def _init(cible: Mapping[str, Any], travail: Path, env: Mapping[str, str], trace: dict[str, Any]) -> int:
    configs = [f"-backend-config={k}={v}" for k, v in cible["backend"].items() if k != "type"]
    return _terraform("init", ["init", "-input=false", "-lockfile=readonly", *configs], travail, env, trace)


def _dossier_jetable(racine: Path, cible: Mapping[str, Any], ctx: dict[str, Any]) -> Path:
    tp.preparer_cache()
    dossier = tp.creer_dossier_plan(racine, cible["name"], tp.nouvel_id_plan(_maintenant()))
    ctx["effacer"] = dossier
    return dossier


# --- scanners --------------------------------------------------------------------------------------------------------

def _scanner(nom: str, argv: Sequence[str], lire: Callable[[bytes], list], env: Mapping[str, str],
             degrades: list[str], constats: list[dict[str, str]]) -> str:
    try:
        rc, sortie = executer(argv, cwd=None, env=env, delai=DELAIS["scanner"], outil=nom, capturer=True)
    except Degrade as d:
        degrades.append(d.outil)
        return d.motif
    if rc != 0:
        degrades.append(f"{nom} (rc={rc})")
        return f"rc={rc}"
    try:
        trouves = lire(sortie)
    except ValueError:
        degrades.append(f"{nom} (sortie illisible)")
        return "sortie illisible"
    constats.extend({**c, "scanner": nom} for c in trouves)
    return "ok"


def scanner_plan(chemin_json: Path, trace: dict[str, Any]) -> tuple[str, list[str]]:
    """trivy config et checkov sur le plan JSON ; rend ("GO"|"NO_GO"|"DEGRADED", outils dégradés)."""
    env = tp.env_scanner(os.environ)
    degrades: list[str] = []
    constats: list[dict[str, str]] = []
    etats: dict[str, str] = {}
    if not _present("trivy", env):
        degrades.append("trivy")
        etats["trivy"] = "absent"
    else:
        try:
            rc, version = executer(["trivy", "--version"], cwd=None, env=env, delai=DELAIS["version"], outil="trivy",
                                   capturer=True)
        except Degrade as d:
            rc, version = -1, d.motif.encode("utf-8")
        m = re.search(r"Version:\s*v?([0-9][0-9A-Za-z.+-]*)", version.decode("utf-8", "replace"))
        if rc != 0 or m is None:
            degrades.append("trivy (version illisible)")
            etats["trivy"] = "version illisible"
        elif m.group(1) in TRIVY_ECARTEES:
            degrades.append(f"trivy {m.group(1)} (version écartée)")
            etats["trivy"] = f"version écartée {m.group(1)}"
        else:
            etats["trivy"] = _scanner("trivy", ["trivy", "config", "--format", "json", "--quiet", "--exit-code", "0",
                                                str(chemin_json)], tp.constats_trivy, env, degrades, constats)
    if not _present("checkov", env):
        degrades.append("checkov")
        etats["checkov"] = "absent"
    else:
        etats["checkov"] = _scanner("checkov", ["checkov", "-f", str(chemin_json), "--framework", "terraform_plan",
                                                "-o", "json", "--soft-fail", "--compact", "--quiet", "--skip-download"],
                                    tp.constats_checkov, env, degrades, constats)
    bloquants = tp.bloquants(constats)
    trace["scanners"] = etats
    trace["constats"] = {"bloquants": [dict(c) for c in bloquants][:50], "total": len(constats),
                         "non_bloquants": len(constats) - len(bloquants)}
    if bloquants:
        return "NO_GO", degrades
    return ("DEGRADED" if degrades else "GO"), degrades


# --- sous-commandes d'information ----------------------------------------------------------------------------------

def cmd_probe(args: argparse.Namespace) -> int:
    chemin = chemin_config(args.config)
    etat = "absente"
    if chemin.is_file():
        try:
            lire_config(chemin)
            etat = "lisible"
        except Refus as r:
            etat = f"refusée: {r.motif}"
    outils = {o: shutil.which(o) for o in OUTILS_PROBE}
    absents = [o for o in OUTILS_REQUIS if outils[o] is None]
    payload = {"commande": "probe", "outils": outils, "os": platform.system(), "config": {"chemin": str(chemin),
               "etat": etat}, "cache": str(tp.racine_cache()), "verdict": "OK" if not absents else "DEGRADED"}
    if absents:
        payload.update(motif=f"absent(s) : {absents}", outil=absents[0], couverture_degradee=absents)
        return _sortie(payload, RC_DEGRADED)
    return _sortie(payload, RC_GO)


def cmd_catalogue(_args: argparse.Namespace) -> int:
    questions = [{"id": q["id"], "champ": q["champ"], "fournisseurs": list(q["fournisseurs"]),
                  "question": q["question"]} for q in CATALOGUE]
    return _sortie({"commande": "catalogue", "verdict": "OK", "ids": [q["id"] for q in CATALOGUE],
                    "questions": questions}, RC_GO)


def cmd_intake(args: argparse.Namespace) -> int:
    if not args.target:
        raise Refus("arguments", "--target est obligatoire")
    chemin = chemin_config(args.config)
    brut = None
    if chemin.is_file():
        brut = next((c for c in lire_config(chemin)["targets"] if c.get("name") == args.target), None)
    return _sortie({"commande": "intake", "verdict": "OK", "cible": args.target,
                    "etat": "presente" if brut is not None else "absente",
                    "questions": questions_absentes(brut or {})}, RC_GO)


def cmd_check_config(args: argparse.Namespace) -> int:
    chemin = chemin_config(args.config)
    config = lire_config(chemin)
    if args.target:
        cible = normaliser(cible_brute(config, args.target))
        verifier_arbre_propre(ROOT, cible, chemin)
        verifier_etat_ignore(ROOT, cible)
        cibles = [cible]
    else:
        cibles = [normaliser(c) for c in config["targets"]]
    return _sortie({"commande": "check-config", "verdict": "OK", "config": str(chemin),
                    "cibles": [_resume_cible(c) for c in cibles]}, RC_GO)


# --- sous-commandes tracées ----------------------------------------------------------------------------------------

def _corps_identity(args: argparse.Namespace, trace: dict[str, Any], _ctx: dict[str, Any]) -> int:
    cible, _chemin = _charger_cible(args, trace)
    trace["identite"] = verifier_identite(cible, _env_cible(cible, trace, exiger_terraform=False))
    return _go(trace)


def _corps_plan(args: argparse.Namespace, trace: dict[str, Any], ctx: dict[str, Any]) -> int:
    racine = ROOT
    cible, chemin = _charger_cible(args, trace)
    verifier_arbre_propre(racine, cible, chemin)
    trace["head"] = head_courant(racine)                                         # lu UNE fois (TOCTOU)
    trace["vert_gele"] = verifier_head_relu(racine, trace["head"])
    verifier_etat_ignore(racine, cible)
    env = _env_cible(cible, trace)
    trace["identite"] = verifier_identite(cible, env)
    id_plan = tp.nouvel_id_plan(trace["t"])
    dossier = tp.creer_dossier_plan(racine, cible["name"], id_plan)
    ctx["dossier_plan"] = dossier
    trace.update(plan_id=id_plan, export=str(dossier / tp.EXPORT_NOM))
    travail = _travail(racine, dossier, cible, trace["head"])
    for etape, suite in (("fmt", ["fmt", "-check"]), ("init", None), ("validate", ["validate"])):
        rc = _init(cible, travail, env, trace) if suite is None else _terraform(etape, suite, travail, env, trace)
        if rc != 0:
            return _no_go(trace, etape, f"terraform {etape} rc={rc} — relancer `terraform {etape}` dans le workdir "
                                        "pour le diagnostic (le runner ne relaie aucune sortie)")
    if _present("tflint", env):
        rc, _ = executer(["tflint"], cwd=travail, env=env, delai=DELAIS["tflint"], outil="tflint")
        trace["etapes"]["tflint"] = rc
        if rc != 0:
            return _no_go(trace, "tflint", f"tflint rc={rc} — relancer `tflint` dans le workdir pour le diagnostic")
    planfile = dossier / tp.PLANFILE_NOM
    rc = _terraform("plan", ["plan", "-input=false", "-lock=true", "-detailed-exitcode", f"-out={planfile}"],
                    travail, env, trace)
    if rc not in (0, 2):
        return _no_go(trace, "plan", f"terraform plan rc={rc} — relancer `terraform plan` dans le workdir")
    if not planfile.is_file() or planfile.is_symlink():
        raise Degrade("terraform", f"planfile absent après un plan rc={rc}")
    os.chmod(planfile, 0o600)
    trace["planfile_sha256"] = tp.sha256_fichier(planfile)
    trace["changements"] = rc == 2
    rc, sortie = executer(["terraform", "show", "-json", str(planfile)], cwd=travail, env=env, delai=DELAIS["show"],
                          outil="terraform", capturer=True)
    if rc != 0:
        raise Degrade("terraform show", f"terraform show -json rc={rc}")
    try:
        plan_json = json.loads(sortie.decode("utf-8"))
        analyse = tp.analyser_plan(plan_json)
    except ValueError as e:
        raise Degrade("terraform show", "plan JSON illisible ou hors forme") from e
    trace["portee_code"] = tp.verifier_portee_code(plan_json, cible)
    del plan_json
    trace.update(comptes=analyse["comptes"], adresses=analyse["adresses"], destructions=analyse["destructions"])
    chemin_json = dossier / tp.PLAN_JSON_NOM
    try:
        tp.ecrire_0600(chemin_json, sortie)
        del sortie
        verdict, degrades = scanner_plan(chemin_json, trace)
    finally:
        tp.effacer(chemin_json)
    trace["empreinte_export"] = tp.empreinte(dossier / tp.EXPORT_NOM)
    if degrades:
        trace["couverture_degradee"] = degrades
    if verdict == "NO_GO":
        return _no_go(trace, "scanner", f"{len(trace['constats']['bloquants'])} constat(s) HIGH/CRITICAL")
    if verdict == "DEGRADED":
        raise Degrade(", ".join(degrades), f"scanner(s) sans verdict : {degrades}")
    return _go(trace)


def _corps_apply(args: argparse.Namespace, trace: dict[str, Any], ctx: dict[str, Any]) -> int:
    racine = ROOT
    tache, plan_sha = args.task or "", (args.plan_sha or "").lower()
    if not TACHE_RE.match(tache) or not SHA256_RE.match(plan_sha):
        raise Refus("arguments", "--task T-<id> et --plan-sha <sha256 du planfile, 64 hex> sont obligatoires")
    trace.update(tache=tache, planfile_sha256=plan_sha)
    cible, chemin = _charger_cible(args, trace, prod_interdite=True)            # (1) prod_poste, puis config
    verifier_arbre_propre(racine, cible, chemin)                                 # (2)
    head = head_courant(racine)                                                  # lu UNE fois (TOCTOU)
    trace["head"] = head
    trace["vert_gele"] = verifier_head_relu(racine, head)                        # (3)
    plan = trouver_plan(racine, plan_sha)                                        # (4)
    if plan is None or not tp.PLAN_ID_RE.match(str(plan.get("plan_id"))):
        raise Refus("plan_inconnu", f"aucun plan tracé pour le planfile {plan_sha}")
    trace["plan_id"] = plan["plan_id"]
    if plan.get("verdict") != "GO":
        raise Refus("plan_non_go", f"le plan {plan['plan_id']} a rendu {plan.get('verdict')} : seul un plan GO s'applique")
    tracee = plan.get("cible") if isinstance(plan.get("cible"), dict) else {}
    if tracee.get("name") != cible["name"] or tracee.get("workspace") != cible["workspace"]:
        raise Refus("plan_autre_cible", f"le plan {plan['plan_id']} a été fait pour la cible « {tracee.get('name')} » "
                                        f"(workspace {tracee.get('workspace')}), pas pour « {cible['name']} »")
    try:
        age_trace = trace["t"] - float(plan.get("t"))
    except (TypeError, ValueError):
        age_trace = float("inf")                                                 # trace hors forme : expirée
    ages = [age_trace, tp.age_id_plan(plan["plan_id"], trace["t"]) or 0.0]
    if max(ages) > PLAN_EXPIRE_S:                                                # (5)
        raise Refus("plan_expire", f"le plan a {int(max(ages) // 60)} min, au-delà de {PLAN_EXPIRE_S // 3600} h : "
                                   "refaire le plan")
    if plan.get("head") != head:                                                 # (6)
        raise Refus("head_change", f"HEAD a bougé depuis le plan ({str(plan.get('head'))[:12]} → {head[:12]}) : "
                                   "refaire le plan")
    dossier = tp.dossier_plan(racine, cible["name"], plan["plan_id"])           # (7)
    planfile, export = dossier / tp.PLANFILE_NOM, dossier / tp.EXPORT_NOM
    if not planfile.is_file() or planfile.is_symlink() or tp.sha256_fichier(planfile) != plan_sha:
        raise Refus("export_altere", "planfile absent ou différent de --plan-sha (déjà appliqué, balayé ou modifié)")
    try:
        empreinte = tp.empreinte(export)
    except OSError as e:
        raise Refus("export_altere", f"export du plan illisible ou absent ({type(e).__name__})") from e
    if empreinte != plan.get("empreinte_export"):
        raise Refus("export_altere", "l'empreinte de l'export diffère de celle du plan : refaire le plan")
    env = _env_cible(cible, trace)
    trace["identite"] = verifier_identite(cible, env)                           # (8)
    comptes = plan.get("comptes") if isinstance(plan.get("comptes"), dict) else {}
    trace["comptes"] = comptes
    trace["decision"] = verifier_decision(racine, tache, cible["name"], plan_sha, head,
                                          int(comptes.get("destroy", 0)))        # (9), (10)
    ctx["effacer"] = dossier                                                     # succès OU échec
    rc = _terraform("apply", ["apply", "-input=false", "-lock=true", str(planfile)], export / cible["workdir"],
                    env, trace)
    if rc != 0:
        return _no_go(trace, "apply", f"terraform apply rc={rc} — infrastructure possiblement PARTIELLEMENT appliquée ; "
                                      "drift puis nouveau plan")
    return _go(trace)


def _corps_verify(args: argparse.Namespace, trace: dict[str, Any], ctx: dict[str, Any]) -> int:
    racine = ROOT
    cible, chemin = _charger_cible(args, trace)
    juger_verifications(cible["verify"])
    verifier_arbre_propre(racine, cible, chemin)
    trace["head"] = head_courant(racine)
    env = _env_cible(cible, trace)
    trace["identite"] = verifier_identite(cible, env)
    travail = _travail(racine, _dossier_jetable(racine, cible, ctx), cible, trace["head"])
    rc = _init(cible, travail, env, trace)
    if rc != 0:
        return _no_go(trace, "init", f"terraform init rc={rc}")
    rc, sortie = executer(["terraform", "output", "-json"], cwd=travail, env=env, delai=DELAIS["output"],
                          outil="terraform", capturer=True)
    if rc != 0:
        raise Degrade("terraform output", f"terraform output -json rc={rc}")
    try:
        sorties = masquer_sorties(json.loads(sortie.decode("utf-8")))
    except ValueError as e:
        raise Degrade("terraform output", "sortie de terraform output -json illisible") from e
    del sortie
    trace["sorties"] = [{"nom": n, "type": s["type"], "sensible": s["sensible"]} for n, s in sorted(sorties.items())]
    resultats = [_verifier_sortie(item, sorties) if "output" in item else _verifier_cli(item, env)
                 for item in cible["verify"]]
    trace["verifications"] = resultats
    echecs = [i for i, r in enumerate(resultats) if not r["ok"]]
    if echecs:
        return _no_go(trace, "verify", f"vérification(s) en échec : verify{echecs}")
    return _go(trace)


def _corps_drift(args: argparse.Namespace, trace: dict[str, Any], ctx: dict[str, Any]) -> int:
    racine = ROOT
    cible, chemin = _charger_cible(args, trace)
    verifier_arbre_propre(racine, cible, chemin)
    trace["head"] = head_courant(racine)
    env = _env_cible(cible, trace)
    trace["identite"] = verifier_identite(cible, env)
    travail = _travail(racine, _dossier_jetable(racine, cible, ctx), cible, trace["head"])
    rc = _init(cible, travail, env, trace)
    if rc != 0:
        return _no_go(trace, "init", f"terraform init rc={rc}")
    rc = _terraform("drift", ["plan", "-refresh-only", "-input=false", "-lock=true", "-detailed-exitcode"], travail,
                    env, trace)
    if rc == 2:
        return _no_go(trace, "derive", "l'infrastructure a dérivé de l'état : relire, puis nouveau plan")
    if rc != 0:
        raise Degrade("terraform", f"terraform plan -refresh-only rc={rc}")
    return _go(trace)


_CORPS: dict[str, Callable[[argparse.Namespace, dict[str, Any], dict[str, Any]], int]] = {
    "identity": _corps_identity, "plan": _corps_plan, "apply": _corps_apply, "verify": _corps_verify,
    "drift": _corps_drift,
}


def cmd_trace(args: argparse.Namespace) -> int:
    """identity, plan, apply, verify, drift : verdict, trace, puis effacement des dossiers à effacer."""
    t = _maintenant()
    trace: dict[str, Any] = {"horodatage": _iso(t), "t": int(t), "commande": args.commande}
    ctx: dict[str, Any] = {}
    rc = RC_DEGRADED
    try:
        try:
            rc = _CORPS[args.commande](args, trace, ctx)
        except Refus as r:
            trace.update(verdict="REFUS", motif=r.motif, detail=r.detail)
            rc = RC_REFUS
        except Degrade as d:
            trace.update(verdict="DEGRADED", motif=d.motif, outil=d.outil)
            rc = RC_DEGRADED
        except (KeyboardInterrupt, Interrompu) as e:
            # m1 : un apply interrompu (SIGINT, SIGTERM, SIGHUP) laisse sa ligne DEGRADED dans runs.jsonl.
            nom = "SIGINT" if isinstance(e, KeyboardInterrupt) else str(e)
            trace.update(verdict="DEGRADED", motif=f"interrompu: {nom}", outil=f"runner tfdeploy (interrompu : {nom})")
            if args.commande == "apply":
                trace["detail"] = APPLY_INTERROMPU
            rc = RC_DEGRADED
        trace["rc"] = rc
        try:
            trace["trace"] = str(ecrire_trace(ROOT, trace))
        except OSError as e:
            trace["trace"] = f"non écrite : {type(e).__name__}"
            if rc == RC_GO:
                trace.update(verdict="DEGRADED", motif=f"trace non écrite ({type(e).__name__}) : GO non auditable",
                             outil="trace tfdeploy", rc=RC_DEGRADED)
                rc = RC_DEGRADED
    finally:
        if "dossier_plan" in ctx and rc != RC_GO:
            tp.effacer(ctx["dossier_plan"])
        if "effacer" in ctx:
            tp.effacer(ctx["effacer"])
    return _sortie(trace, rc)


# --- sorties, CLI, garde de tête -----------------------------------------------------------------------------------

def _emettre(payload: Mapping[str, Any]) -> None:
    try:
        print(json.dumps(payload, ensure_ascii=True, sort_keys=True, default=str))
        sys.stdout.flush()
    except (OSError, ValueError):
        pass


def _sortie(payload: dict[str, Any], rc: int) -> int:
    outils = list(payload.get("couverture_degradee") or [])
    if rc == RC_DEGRADED and payload.get("outil") and not outils:
        outils.append(payload["outil"])
    for outil in outils:
        try:
            print(f"COVERAGE DEGRADED — {outil} absent, verdict absent", file=sys.stderr)
        except (OSError, ValueError):
            pass
    _emettre(payload)
    return rc


def _sortie_refus(r: Refus) -> int:
    return _sortie({"verdict": "REFUS", "motif": r.motif, "detail": r.detail}, RC_REFUS)


def _sortie_degrade(d: Degrade) -> int:
    return _sortie({"verdict": "DEGRADED", "motif": d.motif, "outil": d.outil}, RC_DEGRADED)


class _Analyseur(argparse.ArgumentParser):
    """Une erreur d'arguments est un REFUS JSON (exit 2), jamais l'usage seul."""

    def error(self, message: str) -> NoReturn:
        raise Refus("arguments", message)


SYNOPSIS = """\
  tfdeploy.py probe [--config F]
  tfdeploy.py catalogue
  tfdeploy.py intake --target N [--config F]
  tfdeploy.py check-config [--target N] [--config F]
  tfdeploy.py identity --target N [--config F]
  tfdeploy.py plan --target N [--config F]
  tfdeploy.py apply --target N --task T-<id> --plan-sha <64 hex> [--config F]
  tfdeploy.py verify --target N [--config F]
  tfdeploy.py drift --target N [--config F]
codes : 0 GO · 1 NO_GO · 2 REFUS · 3 DEGRADED ; contrat : docstring de .agents/bin/tfdeploy.py"""


def construire_analyseur() -> argparse.ArgumentParser:
    p = _Analyseur(prog="tfdeploy.py", allow_abbrev=False, epilog=SYNOPSIS,
                   formatter_class=argparse.RawDescriptionHelpFormatter,
                   description="Runner déterministe de déploiement Terraform (skill terraform-deploy).")
    sous = p.add_subparsers(dest="commande", metavar="{" + ",".join(SOUS_COMMANDES) + "}")
    sous.required = True
    aides = {"probe": "outils présents", "catalogue": "ids du catalogue de questions",
             "intake": "questions dont le champ manque à la cible", "check-config": "valide la configuration",
             "identity": "l'identité atteint-elle la portée de la cible", "plan": "plan dans un export de HEAD",
             "apply": "applique un plan GO tracé, sur décision", "verify": "sorties et vérifications en lecture",
             "drift": "dérive de l'infrastructure"}
    for nom in SOUS_COMMANDES:
        sp = sous.add_parser(nom, allow_abbrev=False, help=aides[nom])
        if nom == "catalogue":
            continue
        sp.add_argument("--config")
        if nom != "probe":
            sp.add_argument("--target")
        if nom == "apply":
            sp.add_argument("--task")
            sp.add_argument("--plan-sha", dest="plan_sha")
    return p


def _principal(argv: list[str] | None) -> int:
    args = construire_analyseur().parse_args(argv)
    try:
        tp.balayer(_maintenant(), BALAYAGE_S)
    except OSError:
        pass  # un balayage qui échoue ne bloque rien ; le prochain appel recommence
    if args.commande in _CORPS:
        if not args.target:
            raise Refus("arguments", "--target est obligatoire")
        return cmd_trace(args)
    return {"probe": cmd_probe, "catalogue": cmd_catalogue, "intake": cmd_intake,
            "check-config": cmd_check_config}[args.commande](args)


def _installer_signaux() -> dict[int, Any]:
    anciens: dict[int, Any] = {}
    if os.name != "posix":
        return anciens
    for nom in SIGNAUX_INTERRUPTION:
        sig = getattr(signal, nom, None)
        if sig is None:
            continue
        try:
            anciens[sig] = signal.signal(sig, _sur_signal)
        except ValueError:  # hors du fil principal
            break
    return anciens


def _rendre_signaux(anciens: Mapping[int, Any]) -> None:
    for sig, gestionnaire in anciens.items():
        try:
            signal.signal(sig, gestionnaire if gestionnaire is not None else signal.SIG_DFL)
        except (ValueError, TypeError):
            pass


def main(argv: list[str] | None = None) -> int:
    """Gestionnaires SIGTERM/SIGHUP posés le temps de la commande, puis la garde de tête ; rendus à la sortie."""
    anciens = _installer_signaux()
    try:
        return _garde_de_tete(argv)
    finally:
        _rendre_signaux(anciens)


def _garde_de_tete(argv: list[str] | None) -> int:
    """REFUS 2, DEGRADED 3, interruption 3, et toute exception non prévue 3 — jamais 1."""
    try:
        return _principal(argv)
    except Refus as r:
        return _sortie_refus(r)
    except Degrade as d:
        return _sortie_degrade(d)
    except (KeyboardInterrupt, Interrompu) as e:
        nom = "SIGINT" if isinstance(e, KeyboardInterrupt) else str(e)
        return _sortie_degrade(Degrade(f"runner tfdeploy (interrompu : {nom})", f"interrompu: {nom}"))
    except SystemExit as e:
        if e.code in (0, None):
            raise
        nom = "SystemExit"
    except BaseException as e:  # noqa: BLE001 — garde de tête : jamais le rc 1 d'un Python non capturé
        nom = type(e).__name__
    return _sortie_degrade(Degrade(f"runner tfdeploy (erreur interne: {nom})", f"erreur interne: {nom}"))


if __name__ == "__main__":
    sys.exit(main())
