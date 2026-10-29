"""C4.1 — the skill `terraform-deploy`, its runner, its guard and its routing sites
(T-01M52X1W3WPKCWX1DC36NMKJB6, lot D).

WHY. The skill is DERIVED from the runner `.agents/bin/tfdeploy.py` (its docstring, its
`CATALOGUE`, its motif tuples) and the guard `.codex/hooks/iac_guard.py` keeps its OWN
list of secret-returning CLI verbs. Prose and two lists in two modules drift in silence:
an agent asks a question the runner does not know, cites an option the runner refuses,
or the guard admits outside the runner what the runner refuses inside it. Each arm
below measures one of those drifts, and each has a negative control that applies the
SAME comparison to a mutated input and must go red (a net that cannot fail measures
nothing).

THE ARMS OF C4.1 (annex, step 4):
  (1) catalogue ids of the skill == output of `tfdeploy.py catalogue`, both ways (and
      champ, question and provider condition per id); no `Q-` id elsewhere in the skill;
  (2) every option cited in a runner invocation of the skill exists in `<sub> --help`;
  (3) the WHOLE body of each of the 5 orchestrator defs names `terraform-deployer`;
  (4) the kickoff skill names it;
  (5) on a common set (>= 40 fixed commands plus one command per entry of EITHER list),
      the runner's `verbe_secret` and the guard's rule `iac-cli-secret` give the SAME
      VERDICT — modules loaded BY PATH, verdicts compared, never the constants;
  (6) the rule « On an IaC task… » at the 9 sites;
  (7) the dev enumerations of the orchestrator defs (Claude, Gemini, Kimi, Codex).
Plus the lot's own surfaces: skill form, sourced best practices, the motif table and the
VERBES_SECRETS copy against the runner, the `## terraform / hcl` registry section, the
« Terraform: » bullets of CONVENTIONS_infra.md.

CROSSED REDS: (6) reads `AGENTS.md`, which receives the rule at integration (step 8);
(5) needs the guard of lot B on disk — its absence is reported as a crossed red, never
skipped. Verdicts are compared, not lists: an entry one side hard-codes outside its
constant changes no verdict.

Every runner subprocess gets a throwaway HOME: the runner sweeps
`~/.cache/cadre-tfdeploy` at every call, and a bench never touches the real one.
Python 3.9 compatible (no `match`, no runtime `X | Y`, no tomllib).
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import pytest

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / ".agents" / "skills" / "terraform-deploy" / "SKILL.md"
RUNNER = ROOT / ".agents" / "bin" / "tfdeploy.py"
HOOKS = ROOT / ".codex" / "hooks"
GARDE = HOOKS / "iac_guard.py"
REGISTRY = ROOT / ".agents" / "ref" / "DOCS_REGISTRY.md"
CONVENTIONS = ROOT / ".agents" / "ref" / "CONVENTIONS_infra.md"

ORCHESTRATEURS = (
    ".claude/agents/orchestrator.md",
    ".codex/agents/orchestrator.toml",
    ".gemini/agents/orchestrator.md",
    ".github/agents/orchestrator.agent.md",
    ".kimi-code/agents/orchestrator.md",
)
KICKOFF_SKILL = ".agents/skills/kickoff/SKILL.md"
SITES_REGLE = (
    "AGENTS.md",
    ".github/copilot-instructions.md",
    ".claude/commands/kickoff.md",
    KICKOFF_SKILL,
) + ORCHESTRATEURS
# Two stable fragments of the rule (annex § Q2): the slot, and the half that forbids
# the apply in the same task. Matched on whitespace-flattened text, bold markers removed.
# 2026-10-19, T-01M52X1W3WPKCWX1DC36NMKJB6 (CORR-4, m8): the enumeration is the IaC part
# of `MOTIFS_GARDE` in `.agents/bin/tasks_direct.py` (`*.tf.json`, `*.tfvars.json` added).
REGLE = (
    "On an IaC task (`*.tf`, `*.tf.json`, `*.tfvars`, `*.tfvars.json`, "
    "`.agents/deploy/targets.json`) the dev slot is `terraform-deployer`",
    "it never applies in the same task",
)
# 2026-10-19, T-01M52X1W3WPKCWX1DC36NMKJB6 (CORR-5b) : 10th site, the CADRE page, in French —
# its IaC enumeration is the same five-path list as REGLE, written without backticks.
SITE_CADRE = "CADRE/index.html"
ENUM_CADRE = "(*.tf, *.tf.json, *.tfvars, *.tfvars.json, .agents/deploy/targets.json)"
REGLE_CADRE = (
    f"Sur une tâche IaC {ENUM_CADRE}, le slot dev est terraform-deployer",
    "il n'applique jamais dans la même tâche",
)
FRAGMENTS_REGLE = {**{s: REGLE for s in SITES_REGLE}, SITE_CADRE: REGLE_CADRE}
# The dev enumerations the annex names (C4.1 (7)), located by CONTENT, never by line.
ENUMERATIONS = (
    ".claude/agents/orchestrator.md",
    ".gemini/agents/orchestrator.md",
    ".kimi-code/agents/orchestrator.md",
    ".codex/agents/orchestrator.toml",
)
ENUM_MD = re.compile(r"^\s*\d+\.\s*<(dev-mono \| dev-multi \| frontend-fidelity[^>]*)>", re.M)
ENUM_CODEX = "dev agent of step 5 — dev-mono, dev-multi or frontend-fidelity"

# (5) THE FIXED SET, with the verdict both sides must give (True = refused as a secret).
# None of them carries a deleting verb: `iac-cli-destructif` would mask `iac-cli-secret`.
JEU_FIXE: Tuple[Tuple[str, bool], ...] = (
    # named cases of the annex
    ("az redis list-keys --name r --resource-group g", True),
    ("az cosmosdb list-keys --name c --resource-group g", True),
    ("az appconfig credential list --name a", True),
    ("aws kms list-keys", False),
    ("gcloud kms keys list --location global --keyring k", False),
    # refused: one per family of the runner's list
    ("az storage account keys list --account-name s", True),
    ("az storage account generate-sas --account-name s", True),
    ("az keyvault secret show --vault-name v --name n", True),
    ("az keyvault secret download --vault-name v --name n --file f", True),
    ("az keyvault secret list --vault-name v --show-values", True),
    ("az acr login --name r --expose-token", True),
    ("az acr credential show --name r", True),
    ("az account get-access-token", True),
    ("az webapp config appsettings list --name w --resource-group g", True),
    ("az webapp deployment list-publishing-credentials --name w --resource-group g", True),
    ("az webapp deployment list-publishing-profiles --name w --resource-group g", True),
    ("az cosmosdb keys list --name c --resource-group g", True),
    ("az cosmosdb list-connection-strings --name c --resource-group g", True),
    ("az sql db show-connection-string --client ado.net --name d --server s", True),
    ("az search admin-key show --service-name s --resource-group g", True),
    ("aws secretsmanager get-secret-value --secret-id s", True),
    ("aws secretsmanager batch-get-secret-value --secret-id-list s", True),
    ("aws sts get-session-token", True),
    ("aws sts get-federation-token --name n", True),
    ("aws sts assume-role --role-arn demo-role --role-session-name s", True),
    ("aws sts assume-role-with-web-identity --role-arn demo-role", True),
    ("aws sso get-role-credentials --role-name r", True),
    ("aws configure export-credentials --profile p", True),
    ("aws ecr get-login-password", True),
    ("aws ecr get-authorization-token", True),
    ("aws rds generate-db-auth-token --hostname h --port 5432 --username u", True),
    ("aws eks get-token --cluster-name c", True),
    ("aws ssm get-parameter --name p --with-decryption", True),
    ("aws ssm get-parameters --names p --with-decryption", True),
    ("aws ssm get-parameters-by-path --path /p --with-decryption", True),
    ("aws ssm get-parameter-history --name p --with-decryption", True),
    ("aws configure get aws_secret_access_key", True),
    ("aws configure get aws_session_token", True),
    ("aws kms decrypt --ciphertext-blob fileb://c", True),
    ("gcloud auth print-access-token", True),
    ("gcloud auth print-identity-token", True),
    ("gcloud config config-helper --format json", True),
    ("gcloud secrets versions access latest --secret s", True),
    ("gcloud container clusters get-credentials c --region r", True),
    # T-01M52X1W3WPKCWX1DC36NMKJB6 (2026-10-19, CORR-3): m11 `connection-string list`, and (15) the kms
    # exception holds only for kms as the SERVICE (first word) — never for `kms` as an option value.
    ("az webapp config connection-string list --name w --resource-group g", True),
    ("az storage account keys list --account-name kms", True),
    # admitted: reads, conditionals without their option, the named borne
    ("az keyvault secret list --vault-name v", False),
    ("az acr login --name r", False),
    ("aws ssm get-parameter --name p", False),
    ("aws configure get region", False),
    ("aws sts get-caller-identity", False),
    ("az account show --subscription 00000000-0000-0000-0000-000000000000", False),
    ("gcloud projects describe demo-project", False),
    ("gcloud secrets versions list --secret s", False),
    ("az group show --name g", False),
    ("aws s3api list-buckets", False),
    ("gcloud compute instances list", False),
    ("aws ec2 describe-instances", False),
    ("az storage account show --name s", False),
    # BORNE of both sides, named in the runner's docstring: an option value between the
    # two words breaks the couple (`verify` still refuses it, by its own whitelist).
    ("az keyvault secret --vault-name v show", False),
)
NOMMES = (
    "az redis list-keys --name r --resource-group g",
    "az cosmosdb list-keys --name c --resource-group g",
    "az appconfig credential list --name a",
    "aws kms list-keys",
)


# --------------------------------------------------------------------------- helpers
def lire(chemin) -> str:
    p = chemin if isinstance(chemin, Path) else ROOT / chemin
    return p.read_text(encoding="utf-8")


def a_plat(texte: str) -> str:
    return re.sub(r"\s+", " ", texte.replace("**", ""))


def section(texte: str, debut: str) -> str:
    """The lines under the heading that starts with `debut`, up to the next heading of the
    same or a higher level."""
    niveau = len(debut) - len(debut.lstrip("#"))
    lignes = texte.splitlines()
    for i, ligne in enumerate(lignes):
        if ligne.startswith(debut):
            fin = len(lignes)
            for j in range(i + 1, len(lignes)):
                m = re.match(r"^(#+) ", lignes[j])
                if m and len(m.group(1)) <= niveau:
                    fin = j
                    break
            return "\n".join(lignes[i + 1:fin])
    raise AssertionError(f"section `{debut}` absente")


def lignes_tableau(texte: str) -> List[List[str]]:
    """The body rows of the first Markdown table of `texte` (header and rule dropped)."""
    rangs = []
    for ligne in texte.splitlines():
        ligne = ligne.strip()
        if not (ligne.startswith("|") and ligne.endswith("|")):
            if rangs:
                break
            continue
        cellules = [c.strip() for c in ligne[1:-1].split("|")]
        if all(re.fullmatch(r":?-{3,}:?", c) for c in cellules):
            continue
        rangs.append(cellules)
    return rangs[1:]


def nu(cellule: str) -> str:
    return cellule.strip().strip("`")


def puces(texte: str) -> List[str]:
    """Each `- ` bullet of `texte`, joined with its indented continuation lines."""
    out: List[str] = []
    for ligne in texte.splitlines():
        if ligne.startswith("- "):
            out.append(ligne)
        elif out and ligne.startswith("  ") and ligne.strip():
            out[-1] += " " + ligne.strip()
    return out


def lancer_runner(runner: Path, *args: str, home: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["HOME"] = str(home)
    return subprocess.run([sys.executable, "-B", str(runner), *args], capture_output=True,
                          text=True, encoding="utf-8", timeout=120, env=env, check=False)


def charger(nom: str, chemin: Path):
    spec = importlib.util.spec_from_file_location(nom, chemin)
    assert spec is not None and spec.loader is not None, f"{chemin} : non chargeable"
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module
    spec.loader.exec_module(module)
    return module


def corps(rel: str) -> str:
    """The BODY of a def or skill: after the frontmatter, or the Codex prompt string."""
    texte = lire(rel)
    if rel.endswith(".toml"):
        m = re.search(r'developer_instructions\s*=\s*"""(.*?)"""', texte, re.S)
        assert m, f"{rel} : `developer_instructions` introuvable"
        return m.group(1)
    if texte.startswith("---\n"):
        fin = texte.find("\n---", 4)
        assert fin > 0, f"{rel} : frontmatter jamais fermé"
        return texte[fin + 4:]
    return texte


# --------------------------------------------------------------------------- fixtures
@pytest.fixture(scope="module")
def maison(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("home-tfdeploy")


@pytest.fixture(scope="module")
def catalogue_runner(maison) -> dict:
    p = lancer_runner(RUNNER, "catalogue", home=maison)
    assert p.returncode == 0, f"`tfdeploy.py catalogue` rc {p.returncode} : {p.stderr[-400:]}"
    return json.loads(p.stdout)


@pytest.fixture(scope="module")
def aide(maison) -> Callable[[str], Tuple[int, str]]:
    cache: Dict[str, Tuple[int, str]] = {}

    def lire_aide(sous: str) -> Tuple[int, str]:
        if sous not in cache:
            p = lancer_runner(RUNNER, sous, "--help", home=maison)
            cache[sous] = (p.returncode, p.stdout)
        return cache[sous]

    return lire_aide


@pytest.fixture(scope="module")
def runner_mod():
    return charger("_tfdeploy_parite_c41", RUNNER)


@pytest.fixture(scope="module")
def garde_mod():
    if not GARDE.is_file():
        pytest.fail(f"ROUGE CROISÉ : {GARDE.relative_to(ROOT)} (lot B) absent — la parité "
                    "des verdicts ne se juge pas sans la garde")
    if str(HOOKS) not in sys.path:
        sys.path.insert(0, str(HOOKS))
    return charger("_iac_guard_parite_c41", GARDE)


# --------------------------------------------------------------------------- (1)
def catalogue_skill(texte: str) -> List[Tuple[str, str, str, str]]:
    return [(nu(r[0]), r[1], nu(r[2]), r[3]) for r in lignes_tableau(section(texte, "## CATALOGUE"))]


def ecarts_catalogue(rangs: Sequence[Tuple[str, str, str, str]], runner_json: dict) -> List[str]:
    ecarts = []
    ids_skill = [r[0] for r in rangs]
    ids_runner = list(runner_json["ids"])
    doublons = sorted({i for i in ids_skill if ids_skill.count(i) > 1})
    if doublons:
        ecarts.append(f"id(s) en double dans la skill : {doublons}")
    for i in sorted(set(ids_runner) - set(ids_skill)):
        ecarts.append(f"{i} : rendu par `tfdeploy.py catalogue`, ABSENT du catalogue de la skill")
    for i in sorted(set(ids_skill) - set(ids_runner)):
        ecarts.append(f"{i} : dans le catalogue de la skill, INCONNU du runner")
    par_id = {q["id"]: q for q in runner_json["questions"]}
    for ident, question, champ, quand in rangs:
        q = par_id.get(ident)
        if q is None:
            continue
        if champ != q["champ"]:
            ecarts.append(f"{ident} : champ `{champ}` dans la skill, `{q['champ']}` au runner")
        if question != q["question"]:
            ecarts.append(f"{ident} : la question diffère de celle du runner ({q['question']!r})")
        if list(q["fournisseurs"]) == ["*"]:
            if not quand.startswith("toujours"):
                ecarts.append(f"{ident} : commune au runner, la skill ne dit pas « toujours »")
        else:
            for f in q["fournisseurs"]:
                if f"provider = {f}" not in quand:
                    ecarts.append(f"{ident} : propre à {f} au runner, la skill ne dit pas « provider = {f} »")
    return ecarts


def test_C41_1_catalogue_skill_et_runner_dans_les_deux_sens(catalogue_runner):
    rangs = catalogue_skill(lire(SKILL))
    # THE FLOOR BEFORE THE DIFF: two empty sets agree.
    assert len(rangs) >= 3, "catalogue de la skill vide ou illisible"
    assert len(catalogue_runner["ids"]) >= 3, "`tfdeploy.py catalogue` ne rend presque rien"
    assert ecarts_catalogue(rangs, catalogue_runner) == []


def test_C41_1_aucun_id_Q_hors_du_runner_dans_toute_la_skill(catalogue_runner):
    trouves = set(re.findall(r"(?<![A-Za-z0-9])Q-[A-Z][A-Z0-9-]*[A-Z0-9]", lire(SKILL)))
    assert trouves, "aucun id `Q-` dans la skill : le motif ne mesure rien"
    assert sorted(trouves - set(catalogue_runner["ids"])) == []


def test_C41_1_les_questions_d_auteur_restent_a_part():
    ids = [nu(r[0]) for r in lignes_tableau(section(lire(SKILL), "## Questions d'auteur"))]
    assert ids, "tableau des questions d'auteur vide"
    assert [i for i in ids if not re.fullmatch(r"A-[A-Z0-9-]+", i)] == []
    assert len(ids) == len(set(ids)), "id d'auteur en double"


def test_C41_1_mutation_retirer_un_id_de_la_skill_rougit(catalogue_runner):
    rangs = catalogue_skill(lire(SKILL))
    retire = rangs[-1][0]
    assert any(retire in e for e in ecarts_catalogue(rangs[:-1], catalogue_runner))


def test_C41_1_mutation_ajouter_un_id_au_runner_seul_rougit(tmp_path, maison):
    """A REAL mutation of the runner, on a copy: one more CATALOGUE entry, then the
    copy's own `catalogue` output is compared with the unchanged skill."""
    dossier = tmp_path / ".agents" / "bin"
    dossier.mkdir(parents=True)
    for nom in ("tfdeploy.py", "tfdeploy_plan.py"):
        (dossier / nom).write_bytes((RUNNER.parent / nom).read_bytes())
    source = (dossier / "tfdeploy.py").read_text(encoding="utf-8")
    ancre = "CATALOGUE: tuple[dict[str, Any], ...] = (\n"
    assert source.count(ancre) == 1, "ancre de mutation introuvable : la forme de CATALOGUE a changé"
    entree = '    {"id": "Q-MUTANT", "champ": "mutant", "fournisseurs": ("*",), "question": "?"},\n'
    (dossier / "tfdeploy.py").write_text(source.replace(ancre, ancre + entree), encoding="utf-8")
    p = lancer_runner(dossier / "tfdeploy.py", "catalogue", home=maison)
    assert p.returncode == 0, p.stderr[-400:]
    mute = json.loads(p.stdout)
    assert "Q-MUTANT" in mute["ids"], "la mutation n'a pas pris"
    assert any("Q-MUTANT" in e for e in ecarts_catalogue(catalogue_skill(lire(SKILL)), mute))


# --------------------------------------------------------------------------- (2)
_SPAN = re.compile(r"`([^`]+)`")
_INVOCATION = re.compile(r"tfdeploy\.py\s+([a-z][a-z-]*)([^`]*)")
_OPTION = re.compile(r"(?<![\w-])--[a-z][a-z0-9-]*")


def invocations(texte: str) -> List[Tuple[str, Tuple[str, ...]]]:
    """(subcommand, options) of every runner invocation written as code: fenced lines,
    and inline code spans (which may cross a line break)."""
    bloc, prose, dans_bloc = [], [], False
    for ligne in texte.splitlines():
        if ligne.lstrip().startswith("```"):
            dans_bloc = not dans_bloc
            continue
        (bloc if dans_bloc else prose).append(ligne)
    morceaux = bloc + _SPAN.findall("\n".join(prose))
    out = []
    for m in morceaux:
        for inv in _INVOCATION.finditer(m):
            out.append((inv.group(1), tuple(sorted(set(_OPTION.findall(inv.group(2)))))))
    return out


def options_absentes(invs: Sequence[Tuple[str, Tuple[str, ...]]], aide) -> List[str]:
    fautes = []
    for sous, options in invs:
        rc, texte = aide(sous)
        if rc != 0:
            fautes.append(f"`tfdeploy.py {sous}` : sous-commande inconnue du runner (--help rc {rc})")
            continue
        for o in options:
            if not re.search(r"(?<![\w-])" + re.escape(o) + r"(?![\w-])", texte):
                fautes.append(f"`tfdeploy.py {sous} {o}` : option absente de `{sous} --help`")
    return fautes


def test_C41_2_chaque_option_citee_existe_dans_le_help(aide):
    invs = invocations(lire(SKILL))
    assert ("apply", ("--config", "--plan-sha", "--target", "--task")) in invs, (
        "la forme complète d'apply n'est plus citée : l'arme ne mesure plus l'essentiel")
    assert options_absentes(invs, aide) == []


def test_C41_2_mutation_une_option_ou_une_sous_commande_inventee_rougit(aide):
    assert options_absentes(invocations("`tfdeploy.py plan --target N --force`"), aide)
    assert options_absentes(invocations("```\ntfdeploy.py deploy --target N\n```"), aide)


# --------------------------------------------------------------------------- (3), (4)
def sites_muets(corps_par_site: Dict[str, str]) -> List[str]:
    return [s for s, t in corps_par_site.items() if "terraform-deployer" not in t]


def test_C41_3_le_corps_entier_des_5_orchestrateurs_nomme_terraform_deployer():
    corpus = {rel: corps(rel) for rel in ORCHESTRATEURS}
    assert all(t.strip() for t in corpus.values()), "un corps d'orchestrateur est vide"
    assert sites_muets(corpus) == []


def test_C41_4_la_skill_kickoff_nomme_terraform_deployer():
    assert sites_muets({KICKOFF_SKILL: corps(KICKOFF_SKILL)}) == []


def test_C41_3_mutation_le_retirer_d_un_hote_rougit_en_le_nommant():
    corpus = {rel: corps(rel) for rel in ORCHESTRATEURS}
    cible = ".github/agents/orchestrator.agent.md"
    corpus[cible] = corpus[cible].replace("terraform-deployer", "un dev")
    assert sites_muets(corpus) == [cible]


# --------------------------------------------------------------------------- (5)
def secret_runner(r, commande: str) -> bool:
    return r.verbe_secret(shlex.split(commande)) is not None


def secret_garde(g, commande: str) -> bool:
    return "iac-cli-secret" in g.verdicts(commande, True)


def jeu_genere(r, g) -> List[str]:
    """One command per entry of EITHER list, so a verb added to one side only is in the
    set. The constants only GENERATE commands; what is compared is the verdict."""
    for nom in ("VERBES_SECRETS", "PREFIXES_SECRETS", "COUPLES_SECRETS", "VERBES_DECHIFFRES"):
        assert hasattr(g, nom), f"ROUGE CROISÉ : la garde n'expose plus `{nom}` — jeu à re-dériver"
    vs = r.VERBES_SECRETS
    cmds = [f"aws demo {m}" for m in vs["mots"]]
    cmds += [f"aws demo {p}-x" for p in vs["prefixes"]]
    cmds += [f"az demo {c}" for c in vs["couples"]]
    for entree, drapeau in vs["conditionnels"]:
        cmds += [f"aws demo {entree} {drapeau}", f"aws demo {entree}"]
    cmds += [f"aws configure get x_{s}_y" for s in vs["aws_configure_get"]]
    for entree, outil, mot in vs["exceptions"]:
        cmds.append(f"{'gcloud' if outil == '*' else outil} {mot} {entree}")
    cmds += [f"aws demo {m}" for m in g.VERBES_SECRETS]
    cmds += [f"aws demo {p}-x" for p in g.PREFIXES_SECRETS]
    cmds += [f"az demo {a} {b}" for a, b in g.COUPLES_SECRETS]
    for v in g.VERBES_DECHIFFRES:
        cmds += [f"aws demo {v} --with-decryption", f"aws demo {v}"]
    return sorted(set(cmds))


def desaccords(r, g, commandes: Sequence[str]) -> List[str]:
    out = []
    for c in commandes:
        a, b = secret_runner(r, c), secret_garde(g, c)
        if a != b:
            out.append(f"{c!r} : runner {'REFUSE' if a else 'admet'} (verbe_secret), "
                       f"garde {'REFUSE' if b else 'admet'} (iac-cli-secret)")
    return out


def jeu_commun(r, g) -> List[str]:
    return sorted({c for c, _ in JEU_FIXE} | set(jeu_genere(r, g)))


def test_C41_5_jeu_fixe_plancher_et_verdicts_attendus(runner_mod, garde_mod):
    assert len({c for c, _ in JEU_FIXE}) >= 40, "jeu fixe sous 40 commandes distinctes"
    assert set(NOMMES) <= {c for c, _ in JEU_FIXE}, "un cas nommé par l'annexe a disparu"
    faux = [f"{c!r} attendu {'REFUS' if v else 'admis'} : runner {secret_runner(runner_mod, c)}, "
            f"garde {secret_garde(garde_mod, c)}"
            for c, v in JEU_FIXE
            if secret_runner(runner_mod, c) != v or secret_garde(garde_mod, c) != v]
    assert faux == []


def test_C41_5_runner_et_garde_rendent_le_meme_verdict(runner_mod, garde_mod):
    commandes = jeu_commun(runner_mod, garde_mod)
    assert len(commandes) > len(JEU_FIXE), "le jeu généré depuis les deux listes est vide"
    masquees = [c for c in commandes
                if {"iac-cli-destructif", "iac-illisible"} & set(garde_mod.verdicts(c, True))]
    assert masquees == [], "une règle de la garde masque iac-cli-secret : la comparaison mentirait"
    assert desaccords(runner_mod, garde_mod, commandes) == []


def test_C41_5_mutation_un_verbe_ajoute_au_runner_seul_rougit(runner_mod, garde_mod, monkeypatch):
    monkeypatch.setitem(runner_mod.VERBES_SECRETS, "mots",
                        tuple(runner_mod.VERBES_SECRETS["mots"]) + ("frobnicate-secret",))
    ecarts = desaccords(runner_mod, garde_mod, jeu_commun(runner_mod, garde_mod))
    assert any("frobnicate-secret" in e for e in ecarts)


def test_C41_5_mutation_un_verbe_ajoute_a_la_garde_seule_rougit(runner_mod, garde_mod, monkeypatch):
    monkeypatch.setattr(garde_mod, "VERBES_SECRETS",
                        frozenset(garde_mod.VERBES_SECRETS) | {"frobnicate-secret"})
    ecarts = desaccords(runner_mod, garde_mod, jeu_commun(runner_mod, garde_mod))
    assert any("frobnicate-secret" in e for e in ecarts)


# --------------------------------------------------------------------------- (6)
def sites_sans_regle(textes: Dict[str, str]) -> List[str]:
    return [s for s, t in textes.items() if not all(f in a_plat(t) for f in FRAGMENTS_REGLE[s])]


def test_C41_6_la_regle_IaC_aux_9_sites():
    textes = {s: lire(s) for s in SITES_REGLE}
    assert len(textes) == 9
    manquants = sites_sans_regle(textes)
    assert manquants == [], f"la règle « On an IaC task… » manque à : {manquants}"


def test_C41_6_mutation_la_retirer_d_un_seul_site_le_nomme():
    textes = {s: lire(s) for s in SITES_REGLE}
    avant = set(sites_sans_regle(textes))
    porteurs = [s for s in SITES_REGLE if s not in avant]
    assert porteurs, "aucun site ne porte la règle : le contrôle ne mesure rien"
    cible = porteurs[0]
    textes[cible] = a_plat(textes[cible]).replace(REGLE[0], "")
    assert set(sites_sans_regle(textes)) - avant == {cible}


# La vitrine ne voyage pas (strip: CADRE/). Le saut s'ancre sur le MARQUEUR du kit, jamais sur
# l'absence de la page : dans le kit, une page absente ou renommée rougit (FileNotFoundError).
EST_LE_KIT = (ROOT / ".agents" / "IS_THE_KIT").is_file()  # adopting-tree: marqueur strip:, son absence EST l'adoptant
CADRE_DANS_LE_KIT = pytest.mark.skipif(
    not EST_LE_KIT,
    reason="SAUT ANNONCE : marqueur `.agents/IS_THE_KIT` absent (projet adoptant) — "
           "la page CADRE (strip: CADRE/) n'y voyage pas",
)


def test_C41_6_le_saut_CADRE_ne_s_applique_jamais_dans_le_kit():
    assert CADRE_DANS_LE_KIT.args[0] is (not EST_LE_KIT), "saut C41_6 désancré du marqueur du kit"
    if EST_LE_KIT:
        assert (ROOT / SITE_CADRE).is_file(), f"{SITE_CADRE} absent DU KIT : SITE_CADRE à suivre"


@CADRE_DANS_LE_KIT
def test_C41_6_la_regle_IaC_au_10e_site_la_page_CADRE():
    textes = {s: lire(s) for s in (*SITES_REGLE, SITE_CADRE)}
    assert len(textes) == 10
    assert sites_sans_regle(textes) == [], "la règle IaC manque à un des 10 sites"


@CADRE_DANS_LE_KIT
def test_C41_6_mutation_l_ancienne_enumeration_CADRE_rougit_en_nommant_le_site():
    textes = {s: lire(s) for s in (*SITES_REGLE, SITE_CADRE)}
    assert ENUM_CADRE in textes[SITE_CADRE], "énumération IaC de la page CADRE introuvable"
    textes[SITE_CADRE] = textes[SITE_CADRE].replace(ENUM_CADRE, "(*.tf, *.tfvars, targets.json)")
    assert sites_sans_regle(textes) == [SITE_CADRE]


# ------------------------------------------------- the approval token (CORR-5b, exec-critic B)
# The accord form each surface writes must be ACCEPTED by the runner's own `APPROUVE_RE`, and
# the four refusal forms of the runner's bench must NOT be: a surface that teaches a form the
# runner refuses, or a runner that admits a refusal, both go red here. The regex is imported,
# never copied. CROSSED RED until CORR-5a lands the line-anchored `APPROUVE_RE` (with the old
# unanchored `apply\s+approuv(?:é|e)\b`, the refusal arm is red by construction).
DEFS_DEPLOYER = (
    ".claude/agents/terraform-deployer.md",
    ".codex/agents/terraform-deployer.toml",
    ".gemini/agents/terraform-deployer.md",
    ".github/agents/terraform-deployer.agent.md",
    ".kimi-code/agents/terraform-deployer.md",
)
FORME_ACCORD = re.compile(r"(?:forme d'accord :|accord form:) `([^`]+)`")
NEGATIONS_ECRITES = "(non, pas, refus…, report…, annul…, retir…, rejet…, suspend…"
# The five defs are English (T-01M5S9338BJP1B5RM3TG14AMYT): they cite the runner's French roots as
# code, each in backticks; the skill keeps the bare list. Each surface is held to ITS form.
NEGATIONS_ECRITES_DEFS = "(`non`, `pas`, `refus…`, `report…`, `annul…`, `retir…`, `rejet…`, `suspend…`"


def negations_attendues(rel: str) -> str:
    return NEGATIONS_ECRITES_DEFS if rel in DEFS_DEPLOYER else NEGATIONS_ECRITES
RACINES_NEGATION = ("non", "pas", "refus", "report", "annul", "retir", "rejet", "suspend")
TRIPLET = "app-staging : planfile " + "a" * 64 + " sur HEAD " + "b" * 40
FORMES_REFUS = (
    "apply approuvé ? non — {t}",
    "pas d'apply approuvé pour {t}",
    "le pilote refuse : apply approuvé retiré, {t}",
    "apply approuvé : REFUSÉ {t}",
)
ANCIEN_APPROUVE_RE = re.compile(r"apply\s+approuv(?:é|e)\b", re.IGNORECASE)


def textes_jeton() -> Dict[str, str]:
    textes = {".agents/skills/terraform-deploy/SKILL.md": lire(SKILL)}
    textes.update({rel: corps(rel) for rel in DEFS_DEPLOYER})
    return textes


def fautes_accord(textes: Dict[str, str], motif) -> List[str]:
    fautes = []
    for rel, texte in textes.items():
        plat = a_plat(texte)
        formes = FORME_ACCORD.findall(plat)
        if len(formes) != 1:
            fautes.append(f"{rel} : {len(formes)} forme(s) d'accord, une attendue")
        for forme in formes:
            # alone, then as the last line of a decision that names the triplet first
            for decision in (forme, f"{TRIPLET}\n{forme}"):
                if not motif.search(decision):
                    fautes.append(f"{rel} : forme d'accord « {forme} » refusée par APPROUVE_RE")
        if negations_attendues(rel) not in plat:
            fautes.append(f"{rel} : la liste des mots de négation n'est pas écrite")
    return fautes


def refus_admis(motif) -> List[str]:
    return [f for f in (g.format(t=TRIPLET) for g in FORMES_REFUS) if motif.search(f)]


def test_jeton_la_forme_d_accord_de_la_skill_et_des_5_defs_passe_APPROUVE_RE(runner_mod):
    textes = textes_jeton()
    assert len(textes) == 6
    assert fautes_accord(textes, runner_mod.APPROUVE_RE) == []


def test_jeton_les_quatre_formes_de_refus_sont_refusees_par_APPROUVE_RE(runner_mod):
    assert refus_admis(runner_mod.APPROUVE_RE) == [], (
        "ROUGE CROISÉ tant que CORR-5a n'a pas livré l'APPROUVE_RE ancré en tête de ligne")


def test_jeton_les_racines_de_negation_ecrites_sont_celles_du_runner(runner_mod):
    motif = runner_mod.APPROUVE_RE.pattern
    assert [r for r in RACINES_NEGATION if r not in motif] == []
    assert [r for r in RACINES_NEGATION if r not in NEGATIONS_ECRITES] == []
    assert [r for r in RACINES_NEGATION if f"`{r}" not in NEGATIONS_ECRITES_DEFS] == []


def test_jeton_mutation_changer_le_jeton_dans_la_skill_rougit(runner_mod):
    textes = textes_jeton()
    rel = ".agents/skills/terraform-deploy/SKILL.md"
    vieux = "forme d'accord :\n  `apply approuvé :"
    assert vieux in textes[rel], "forme d'accord de la skill introuvable"
    textes[rel] = textes[rel].replace(vieux, "forme d'accord :\n  `apply validé :")
    fautes = fautes_accord(textes, runner_mod.APPROUVE_RE)
    assert fautes and all(f.startswith(rel) for f in fautes)


def test_jeton_mutation_une_negation_dans_la_forme_d_une_def_rougit(runner_mod):
    textes = textes_jeton()
    rel = DEFS_DEPLOYER[3]
    vieux = "`apply approuvé : <cible>"
    assert vieux in textes[rel], "forme d'accord de la déf introuvable"
    textes[rel] = textes[rel].replace(vieux, "`apply approuvé, pas encore : <cible>", 1)
    fautes = fautes_accord(textes, runner_mod.APPROUVE_RE)
    assert fautes and all(f.startswith(rel) for f in fautes)


def test_jeton_mutation_chaque_surface_tenue_par_sa_liste_de_negations(runner_mod):
    """T-01M5S9338BJP1B5RM3TG14AMYT: a def carrying the skill's bare list (the French form it had
    before the translation), or the skill carrying the defs' backticked list, goes red."""
    textes = textes_jeton()
    assert fautes_accord(textes, runner_mod.APPROUVE_RE) == []
    for rel in textes:
        propre = NEGATIONS_ECRITES_DEFS if rel in DEFS_DEPLOYER else NEGATIONS_ECRITES
        autre = NEGATIONS_ECRITES if rel in DEFS_DEPLOYER else NEGATIONS_ECRITES_DEFS
        mute = dict(textes)
        mute[rel] = a_plat(textes[rel]).replace(propre, autre)
        assert mute[rel] != a_plat(textes[rel]), f"{rel} : mutant sans effet"
        fautes = fautes_accord(mute, runner_mod.APPROUVE_RE)
        assert fautes and all(f.startswith(rel) for f in fautes), rel


def test_jeton_mutation_l_ancien_APPROUVE_RE_admet_les_refus():
    assert len(refus_admis(ANCIEN_APPROUVE_RE)) == len(FORMES_REFUS)


# ------------------------------------------------- the NO_GO motifs of the 5 defs (CORR-5b)
# L-00000187: the defs enumerate ALL of the runner's `MOTIFS_NO_GO`, never a subset.
NO_GO_DEFS = re.compile(r"its 9 motives \(the runner's `MOTIFS_NO_GO`, detail in the skill\):(.*?)\. checkov")


def defs_no_go_ecartees(textes: Dict[str, str], attendus: Sequence[str]) -> List[str]:
    fautes = []
    for rel, texte in textes.items():
        m = NO_GO_DEFS.search(a_plat(texte))
        if m is None:
            fautes.append(f"{rel} : énumération des motifs de NO_GO introuvable")
            continue
        ecrits = sorted(re.findall(r"`([a-z_]+)`", re.sub(r"\([^)]*\)", "", m.group(1))))
        if ecrits != sorted(attendus):
            fautes.append(f"{rel} : motifs de NO_GO {ecrits} != {sorted(attendus)}")
    return fautes


def test_les_5_defs_enumerent_les_9_motifs_NO_GO_du_runner(runner_mod):
    assert len(runner_mod.MOTIFS_NO_GO) == 9
    assert defs_no_go_ecartees({rel: corps(rel) for rel in DEFS_DEPLOYER}, runner_mod.MOTIFS_NO_GO) == []


def test_mutation_un_motif_NO_GO_retire_d_une_def_rougit_en_la_nommant(runner_mod):
    textes = {rel: corps(rel) for rel in DEFS_DEPLOYER}
    rel = DEFS_DEPLOYER[1]
    textes[rel] = textes[rel].replace("`apply`, `derive`", "`derive`", 1)
    fautes = defs_no_go_ecartees(textes, runner_mod.MOTIFS_NO_GO)
    assert len(fautes) == 1 and fautes[0].startswith(rel)


# --------------------------------------------------------------------------- (7)
def enumeration(rel: str, texte: str) -> Optional[str]:
    if rel.endswith(".toml"):
        plat = a_plat(texte)
        i = plat.find(ENUM_CODEX)
        if i < 0:
            return None
        j = plat.find(")", i)
        return plat[i:j if j > 0 else len(plat)]
    m = ENUM_MD.search(texte)
    return m.group(1) if m else None


def enumerations_muettes(textes: Dict[str, str]) -> List[str]:
    fautes = []
    for rel, texte in textes.items():
        e = enumeration(rel, texte)
        if e is None:
            fautes.append(f"{rel} : énumération des devs introuvable")
        elif "terraform-deployer" not in e:
            fautes.append(f"{rel} : l'énumération des devs ne nomme pas terraform-deployer")
    return fautes


def test_C41_7_les_enumerations_de_devs_nomment_terraform_deployer():
    assert enumerations_muettes({rel: lire(rel) for rel in ENUMERATIONS}) == []


def test_C41_7_mutation_la_retirer_d_une_seule_rougit():
    textes = {rel: lire(rel) for rel in ENUMERATIONS}
    cible = ".claude/agents/orchestrator.md"
    textes[cible] = textes[cible].replace(" | terraform-deployer>", ">", 1)
    fautes = enumerations_muettes(textes)
    assert len(fautes) == 1 and fautes[0].startswith(cible)


# --------------------------------------------------------------------------- the lot's surfaces
def test_skill_forme_frontmatter_en_ligne_1_profondeur_1():
    lignes = lire(SKILL).split("\n")
    assert lignes[0] == "---", "le frontmatter doit ouvrir en LIGNE 1 (sinon la skill est cachée)"
    fin = lignes.index("---", 1)
    entete = lignes[1:fin]
    assert "name: terraform-deploy" in entete
    description = [ligne for ligne in entete if ligne.startswith("description: ")]
    assert description and len(description[0]) > 60, "description absente ou vide"
    assert SKILL.parent.parent == ROOT / ".agents" / "skills", "la skill n'est plus à profondeur 1"
    assert "## LIRE QUAND" in lire(SKILL)


def sans_source(texte: str) -> List[str]:
    return [p[:90] for p in puces(texte) if "https://" not in p and "à vérifier" not in p]


def test_skill_chaque_bonne_pratique_porte_sa_source():
    sec = section(lire(SKILL), "## Bonnes pratiques")
    assert len(puces(sec)) >= 8, "section des bonnes pratiques vide ou tronquée"
    assert sans_source(sec) == []
    assert sans_source("- une pratique affirmée de mémoire\n  sur deux lignes"), "la règle ne mord pas"


def test_skill_table_des_motifs_egale_les_tuples_du_runner(runner_mod):
    rangs = lignes_tableau(section(lire(SKILL), "### Motifs"))
    refus = sorted(nu(r[1]) for r in rangs if r[0] == "REFUS")
    no_go = sorted(nu(r[1]) for r in rangs if r[0] == "NO_GO")
    assert refus == sorted(runner_mod.MOTIFS_REFUS)
    assert no_go == sorted(runner_mod.MOTIFS_NO_GO)


def bloc_verbes(texte: str) -> Dict[str, List[str]]:
    m = re.search(r"```text\n(.*?)\n```", section(texte, "### VERBES_SECRETS"), re.S)
    assert m, "bloc VERBES_SECRETS de la skill introuvable"
    familles: Dict[str, List[str]] = {}
    for ligne in m.group(1).splitlines():
        cle, _, reste = ligne.partition(": ")
        familles[cle.strip()] = [e.strip() for e in reste.split(" · ") if e.strip()]
    return familles


def test_skill_recopie_de_VERBES_SECRETS_egale_le_runner(runner_mod):
    vs = runner_mod.VERBES_SECRETS
    attendu = {
        "mots": sorted(vs["mots"]),
        "prefixes": sorted(vs["prefixes"]),
        "couples": sorted(vs["couples"]),
        "conditionnels": sorted(f"{e} + {d}" for e, d in vs["conditionnels"]),
        "aws_configure_get": sorted(vs["aws_configure_get"]),
        "exceptions": sorted(f"{e} + {o} + {m}" for e, o, m in vs["exceptions"]),
    }
    obtenu = {k: sorted(v) for k, v in bloc_verbes(lire(SKILL)).items()}
    assert obtenu == attendu


def test_registre_section_terraform_hcl():
    texte = lire(REGISTRY)
    titres = [ligne[3:].strip() for ligne in texte.splitlines() if ligne.startswith("## ")]
    porteurs = [t for t in titres if "terraform" in {s.strip().casefold() for s in t.split(" / ")}]
    assert len(porteurs) == 1, f"section terraform absente ou en double : {porteurs}"
    assert "hcl" in {s.strip().casefold() for s in porteurs[0].split(" / ")}, (
        "le détecteur émet primary_language hcl : le titre doit porter ce segment")
    sec = section(texte, "## " + porteurs[0])
    assert "kit_skill: .agents/skills/terraform-deploy/SKILL.md" in sec
    assert re.search(r"^llms_txt: absent \(404 mesuré 2026-10-16", sec, re.M)
    assert "https://developer.hashicorp.com/terraform/docs" in sec
    assert "https://registry.terraform.io/v1/" in sec, "API du registre absente"
    assert titres[-1] == "installed", "le bloc géré par skills-resolver doit rester le dernier"


# Tags aws obligatoires (T-01M5S94YRFBGADG4Q7HBCTJFNT, demande pilote du 2026-10-25) : la puce
# « - Terraform: aws only — … » de CONVENTIONS_infra.md, ancre par ancre. Chaque ancre est UNIQUE dans
# le fichier aplati (test_ancres_tags_uniques) : une autre puce ne peut pas la satisfaire, et un mutant
# qui en ôte UNE occurrence l'ôte du fichier.
ANCRES_TAGS_AWS = (
    "aws only — EVERY resource that supports `tags` is tagged",
    "`Project = <project name>`",
    "`POC`, `DEV` or `PROD` (exactly these three values, upper case)",
    # propre à cette puce : « on EVERY aws provider block, aliases included » seul est aussi dans
    # celle d'`allowed_account_ids`, qui satisferait l'ancre si on l'ôtait d'ici.
    "`default_tags { tags = { Project = …, Env = … } }` on EVERY aws provider block, aliases included",
    "a resource's or module's own `tags` never sets the `Project` or `Env` keys",
    "« Provider tags can be overridden with new values »",
    "This functionality is supported in all resources that implement `tags`, with the exception of "
    "the `aws_autoscaling_group` resource",
    "`propagate_at_launch = true`",
    "through its `tag_specifications`",
    "`awscc` resources (no provider-level default tags",
    '`tags = [{ key = "Project", value = local.project }, { key = "Env", value = local.env }]`',
    "declared explicitly where a Terraform resource exists (`aws_cloudwatch_log_group`)",
    "the rest is named in the AUTEUR report",
    "Values are never invented",
    "`Project` comes from the specs, the plan, the existing IaC or the answer to `A-TAGS`",
    "`Env = POC` when the specs, the plan, the existing IaC or `A-TAGS` say POC, whatever the target env",
    "`dev` → `DEV`",
    "`prod` → `PROD`",
    "`staging` or `preprod` → the pilot names one of the three values through `A-TAGS`",
    "declared without default and set in the workdir's committed `terraform.tfvars`",
    '`validation { condition = contains(["POC", "DEV", "PROD"], var.env) }`',
    "letters, digits, spaces and `_ . : / = + - @`, 1 to 256",
    "A value nobody gave stays unset and the plan fails — never invented",
    "No secret, personal data or confidential codename in a tag value",
    "The value set is held by the `validation` of `var.env` at plan",
    "presence on each resource is held by the author alone — no reviewer def re-reads this sheet, and "
    "no guard checks the tags",
)
CONVENTIONS_ANCRES = (
    "allowed_account_ids = [<account_id>]",
    "`subscription_id`",
    "`ARM_SUBSCRIPTION_ID`",
    ".terraform.lock.hcl",
    "-platform=",
    "`use_lockfile",
    "`plan -out` then `apply <planfile>`",
    "`ephemeral`",
    "write-only",
    "`default_tags`",
    "`default_labels`",
    "the region and the data residency are fixed in the reviewed IaC code",
    "`terraform test` creates real infrastructure",
    "`*.tfstate`",
    *ANCRES_TAGS_AWS,
)


def ancres_absentes(brut: str) -> List[str]:
    plat = a_plat(brut)
    return [a for a in CONVENTIONS_ANCRES if a not in plat]


def test_conventions_infra_puces_terraform():
    brut = lire(CONVENTIONS)
    assert len([ligne for ligne in brut.splitlines() if ligne.startswith("- Terraform:")]) >= 10
    assert ancres_absentes(brut) == []


def test_ancres_tags_uniques():
    plat_conv, plat_skill = a_plat(lire(CONVENTIONS)), a_plat(lire(SKILL))
    assert {a: plat_conv.count(a) for a in ANCRES_TAGS_AWS if plat_conv.count(a) != 1} == {}
    rang = rang_a_tags(lire(SKILL))
    assert {m: rang.count(m) for m in MOTS_A_TAGS if rang.count(m) != 1} == {}
    mots_skill = MOTS_A_TAGS + MOTS_PUCE_AWS + (NON_TENU_TAGS,)
    assert {m: plat_skill.count(m) for m in mots_skill if plat_skill.count(m) != 1} == {}


@pytest.mark.parametrize("ancre", ANCRES_TAGS_AWS)
def test_conventions_infra_mutation_retirer_la_regle_des_tags_aws_rougit(ancre):
    plat = a_plat(lire(CONVENTIONS))
    assert ancre in plat, "ancre absente du vrai fichier : le mutant ne muterait rien"
    assert ancre in ancres_absentes(plat.replace(ancre, "", 1))


def test_conventions_infra_la_puce_tags_aws_ne_promet_pas_toute_ressource():
    puce = [p for p in puces(lire(CONVENTIONS)) if p.startswith("- Terraform: aws only")]
    assert len(puce) == 1, "puce des tags aws absente ou en double"
    assert "no exception" not in puce[0], "sur-promesse : l'exception `aws_autoscaling_group` existe"


# La ligne `A-TAGS` des questions d'auteur dit sa portée aws, les deux tags obligatoires et leurs trois
# valeurs, la priorité de `Env = POC`, la correspondance des environnements, et ne se nie jamais.
# Chaque phrase y est UNIQUE (test_ancres_tags_uniques).
MOTS_A_TAGS = (
    "Sur aws,",
    "`Project` et `Env` (`POC`, `DEV` ou `PROD`) sont OBLIGATOIRES sur chaque ressource qui accepte des `tags`",
    "la question demande leurs valeurs et les éventuels tags supplémentaires",
    "`Env = POC` si les specs, le plan, l'IaC existante ou la réponse disent POC, quel que soit "
    "l'environnement cible",
    "sinon `dev` → `DEV`",
    "`prod` → `PROD`",
    "`staging` ou `preprod` → valeur parmi les trois nommée par le pilote",
)
NEGATIONS_A_TAGS = ("pas OBLIGATOIRES", "optional", "facultati", "n'en demande que")


def rang_a_tags(texte: str) -> str:
    rangs = [r for r in lignes_tableau(section(texte, "## Questions d'auteur")) if nu(r[0]) == "A-TAGS"]
    assert len(rangs) == 1, "ligne `A-TAGS` absente ou en double"
    return " | ".join(rangs[0])


def manques_a_tags(texte: str) -> List[str]:
    rang = rang_a_tags(texte)
    return ([m for m in MOTS_A_TAGS if m not in rang]
            + [f"négation : {n}" for n in NEGATIONS_A_TAGS if n in rang])


def test_a_tags_nomme_project_env_et_leurs_trois_valeurs_aws():
    assert manques_a_tags(lire(SKILL)) == []


def _ligne_a_tags(texte: str) -> str:
    return next(ligne for ligne in texte.splitlines() if ligne.startswith("| `A-TAGS` |"))


@pytest.mark.parametrize("mot", MOTS_A_TAGS)
def test_a_tags_mutation_retirer_un_mot_rougit_en_le_nommant(mot):
    texte = lire(SKILL)
    ligne = _ligne_a_tags(texte)
    assert mot in ligne, "mot absent de la vraie ligne : le mutant ne muterait rien"
    assert mot in manques_a_tags(texte.replace(ligne, ligne.replace(mot, "", 1)))


@pytest.mark.parametrize("negation", NEGATIONS_A_TAGS)
def test_a_tags_mutation_une_negation_ajoutee_rougit(negation):
    texte = lire(SKILL)
    ligne = _ligne_a_tags(texte)
    assert negation not in ligne
    assert ligne.endswith("| toujours |"), "dernière cellule de `A-TAGS` changée : le mutant ne muterait rien"
    mute = ligne[: -len("| toujours |")] + f"{negation} | toujours |"
    assert f"négation : {negation}" in manques_a_tags(texte.replace(ligne, mute))


# La puce « aws seul » des bonnes pratiques et l'item de « Ce qui n'est pas tenu ».
MOTS_PUCE_AWS = (
    "CHAQUE ressource qui accepte des `tags` porte `Project = <nom du projet>`",
    "`Env` = `POC`, `DEV` ou `PROD`, posés dans `default_tags`",
    "(alias compris)",
    "ne posent jamais les clés `Project` ni `Env`",
    "with the exception of the `aws_autoscaling_group` resource",
    "`propagate_at_launch = true`",
    "dans ses `tag_specifications`",
    "une ressource `awscc` (pas de tags par défaut au provider)",
    '`tags = [{ key = "Project", value = local.project }, { key = "Env", value = local.env }]`',
    "se déclare (`aws_cloudwatch_log_group`)",
    "le reste est nommé au rapport AUTEUR",
    "`terraform.tfvars` commité du workdir",
    '`validation { condition = contains(["POC", "DEV", "PROD"], var.env) }`',
    "une valeur que personne n'a donnée reste vide et le plan échoue",
    "aucun secret, donnée personnelle ou nom de code confidentiel",
)
NON_TENU_TAGS = (
    "Les tags aws `Project`/`Env` : leur jeu de valeurs est tenu par la `validation` de `var.env` au "
    "plan ; leur présence sur chaque ressource, par l'auteur seul — aucune déf de relecteur ne relit "
    "la fiche, aucune garde ne lit les tags."
)


def retirer_une(texte: str, phrase: str, par: str = "") -> Tuple[str, int]:
    """`texte` où la PREMIÈRE occurrence de `phrase` (espaces et retours à la ligne indifférents) devient
    `par`, et le nombre d'occurrences de `phrase` dans `texte`."""
    motif = re.compile(r"\s+".join(re.escape(m) for m in phrase.split(" ")))
    return motif.sub(lambda _m: par, texte, count=1), len(motif.findall(texte))


def manques_skill_tags(texte: str) -> List[str]:
    aws = [a_plat(p) for p in puces(section(texte, "## Bonnes pratiques")) if p.startswith("- aws seul :")]
    manques = ["puce « aws seul » absente ou en double"] if len(aws) != 1 else [
        m for m in MOTS_PUCE_AWS if m not in aws[0]]
    if NON_TENU_TAGS not in a_plat(section(texte, "## Ce qui n'est pas tenu")):
        manques.append("item des tags absent de « Ce qui n'est pas tenu »")
    return manques


def test_skill_puce_aws_seul_et_item_non_tenu():
    assert manques_skill_tags(lire(SKILL)) == []


@pytest.mark.parametrize("mot", MOTS_PUCE_AWS + (NON_TENU_TAGS,))
def test_skill_mutation_retirer_un_mot_des_tags_rougit(mot):
    mute, n = retirer_une(lire(SKILL), mot)
    assert n == 1, "mot absent du vrai fichier ou en double : le mutant ne muterait rien de sûr"
    assert manques_skill_tags(mute) != []


def test_skill_mutation_supprimer_la_puce_aws_seul_rougit():
    lignes = lire(SKILL).splitlines()
    debut = next(i for i, ligne in enumerate(lignes) if ligne.startswith("- aws seul :"))
    fin = next(i for i in range(debut + 1, len(lignes)) if not lignes[i].startswith("  "))
    mute = "\n".join(lignes[:debut] + lignes[fin:])
    assert "puce « aws seul » absente ou en double" in manques_skill_tags(mute)


# Mutants NOMMÉS (exec-critic, passe de clôture) : chacun change UNE occurrence et doit rougir.
MUTANTS_TAGS = (
    ("conv", "`dev` → `DEV`, `prod` → `PROD`", "`dev` → `PROD`, `prod` → `DEV`"),
    ("conv", "`staging` or `preprod` → the pilot names one of the three values through `A-TAGS`",
     "`staging` or `preprod` → `DEV`"),
    ("conv", "whatever the target env", "for a POC target only"),
    ("conv", "Values are never invented", "Values are guessed"),
    ("conv", "(exactly these three values, upper case)", "(for example)"),
    ("conv", 'contains(["POC", "DEV", "PROD"], var.env)', 'contains(["POC", "DEV", "PROD", "STAGING"], var.env)'),
    ("conv", "never sets the `Project` or `Env` keys", "may set the `Project` or `Env` keys"),
    ("conv", '`tags = [{ key = "Project", value = local.project }, { key = "Env", value = local.env }]`', "`tags`"),
    ("conv", "Env = … } }` on EVERY aws provider block, aliases included", "Env = … } }` on EVERY aws provider block"),
    ("conv", "the existing IaC or the answer", "or the answer"),
    ("skill", "Sur aws,", "Partout,"),
    ("skill", "sinon `dev` → `DEV`, `prod` → `PROD`", "sinon `dev` → `PROD`, `prod` → `DEV`"),
    ("skill", "→ valeur parmi les trois nommée par le pilote", "→ `DEV`"),
    ("skill", "quel que soit l'environnement cible", "pour une cible POC seulement"),
    ("skill", "sur chaque ressource qui accepte des `tags`", "sur certaines ressources"),
    ("skill", "l'IaC existante ou la réponse", "ou la réponse"),
    ("skill", "(alias compris)", ""),
    ("skill", "ne posent jamais les clés", "posent parfois les clés"),
)


def fautes_tags(cible: str, texte: str) -> List[str]:
    if cible == "conv":
        return ancres_absentes(texte)
    return manques_a_tags(texte) + manques_skill_tags(texte)


@pytest.mark.parametrize("cible,avant,apres", MUTANTS_TAGS)
def test_tags_mutant_nomme_rougit(cible, avant, apres):
    texte = lire(CONVENTIONS if cible == "conv" else SKILL)
    assert fautes_tags(cible, texte) == []
    mute, n = retirer_une(texte, avant, apres)
    assert n == 1, f"`{avant}` absent ou en double : le mutant ne muterait rien de sûr"
    assert fautes_tags(cible, mute) != []


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
