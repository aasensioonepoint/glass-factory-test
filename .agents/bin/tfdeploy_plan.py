#!/usr/bin/env python3
"""ANALYSE DU PLAN, EXPORT, EMPREINTE ET ENVIRONNEMENT DU RUNNER `tfdeploy` (T-01M52X1W3WPKCWX1DC36NMKJB6, lot A).

Module FRÈRE de `tfdeploy.py`, qui le charge PAR CHEMIN sous un nom privé ; il n'a aucune entrée en ligne de
commande. LE CONTRAT DU RUNNER — sous-commandes, codes de sortie, motifs de refus — EST LE DOCSTRING DE
`tfdeploy.py`, qui fait foi. Ce module en porte la MÉCANIQUE et ne rend aucun verdict : il lève `Refus` (motif
nommé du contrat) ou `Degrade` (outil absent, muet ou hors délai), ou rend des comptes. Bibliothèque standard seule,
Python 3.9 (`from __future__ import annotations`, aucune syntaxe postérieure).

ENVIRONNEMENT — LISTE BLANCHE (`env_terraform`). terraform et les CLI d'`identity` reçoivent SEULEMENT les noms de
`ENV_NOMS_ADMIS` et ceux qui commencent par `ENV_PREFIXES_ADMIS` ; tout le reste est ABSENT (dont `TF_VAR_*`,
`TF_CLI_ARGS*`, `TF_LOG*`, `TF_REATTACH_PROVIDERS`, `TF_DATA_DIR`, `TF_WORKSPACE` ambiant, `AWS_PROFILE`,
`AWS_DEFAULT_PROFILE`). Puis la PORTÉE est POSÉE depuis la cible, en écrasant l'ambiant (`PORTEE_PAR_FOURNISSEUR`,
plus `AWS_PROFILE` si la cible aws porte `profile`), et le runner pose `TF_WORKSPACE`, `TF_INPUT=0`,
`TF_IN_AUTOMATION=1`, `TF_PLUGIN_CACHE_DIR` (absolu, 0700) et `TF_CLI_CONFIG_FILE` (un `tfdeploy.tfrc` du runner qui
ne porte que `plugin_cache_dir` : `dev_overrides`, `provider_installation` et `credentials` de `~/.terraformrc` sont
ÉCARTÉS — perte nommée ; `TF_TOKEN_*` reste). Les scanners reçoivent `env_scanner` : réseau et locale, AUCUNE
authentification cloud. Pas de variable Windows : runner macOS/Linux SEULEMENT.

CACHE ET BALAYAGE. Racine `~/.cache/cadre-tfdeploy/` (HOME lu À L'APPEL), 0700 ; un dossier de plan vit sous
`<empreinte du dépôt>/<cible>/<id de plan>/` (empreinte = sha256 du chemin absolu de la racine ; id = `<epoch sur 10
chiffres>-<16 hex>`, l'âge se lit dans le NOM, jamais dans un mtime). `balayer(t, seuil)` efface tout dossier de plan
dont l'âge dépasse le seuil, pour TOUS les dépôts et toutes les cibles du cache ; un nom hors forme et un lien
symbolique ne sont jamais touchés. Aucun verrou : le runner n'est pas conçu pour des appels concurrents (nommé).

EXPORT (`exporter`). Un index JETABLE (`GIT_INDEX_FILE` dans le dossier du plan) reçoit `git read-tree <sha>` — le
sha de HEAD RELU UNE FOIS par l'appelant (40 hex, validé ; jamais le nom symbolique `HEAD`, qui peut avoir bougé
entre la lecture tracée et l'export : TOCTOU fermé) —, perd
`.agents/state/` et `runs/` (`git rm -r --cached`), puis `git checkout-index -a --prefix=<export>/` l'extrait —
jamais `git archive` : `export-ignore` n'écarte rien, `export-subst` ne réécrit rien. Refusés AVANT l'extraction,
faute de les exporter fidèlement : une entrée gitlink (mode 160000) → `sous_module` ; un attribut `filter=lfs` →
`lfs` ; tout AUTRE attribut `filter` posé (pilote local de `smudge`, git-crypt…) → `filtre_git`. Attributs lus deux
fois, depuis l'index jetable (`--cached`) et depuis l'arbre. Bornes nommées : `ident` et les conversions `text`/`eol`
s'appliquent à l'extraction (`core.autocrlf=false` posé) ; l'index et l'arbre du dépôt ne bougent pas.

EMPREINTE (`empreinte`). sha256 d'un relevé TRIÉ de l'export entier, `.terraform/` compris, sans suivre aucun lien :
chemin relatif, type, mode, sha256 du contenu d'un fichier, CIBLE d'un lien (un lien de `.terraform/providers` vers
le cache compte par sa cible, pas par le contenu du provider). Coût : l'export est haché deux fois (plan, apply).

PLAN JSON (`analyser_plan`, `verifier_portee_code`). Lit `resource_changes[].change.actions` et `.address` :
comptes `create`, `update`, `delete`, `replace` (`["delete","create"]` ET `["create","delete"]`), et `destroy` =
toute action qui CONTIENT `delete` (un remplacement détruit). `no-op`, `read` et toute autre action ne comptent pas,
sauf leur `delete`. Portée écrite dans le code : `configuration.provider_config.<clé>.expressions.<clé>.constant_value`
— azure (`azurerm`) `subscription_id` et `tenant_id`, gcp (`google`, `google-beta`) `project` : une constante qui
contredit la cible → `portee_code_ecart` ; une expression non constante, un `null`, un alias non constant, le
`project` ou le `scope` d'une ressource ne sont PAS jugés (nommé). aws : CHAQUE bloc provider `aws` (alias compris)
doit porter `allowed_account_ids` en constante ÉGALE à `[account_id]`, et il en faut au moins un, sinon
`portee_non_fixee`. Format JSON du plan NON re-téléchargé ici : la clé `name` puis le suffixe de `full_name`
identifient le fournisseur. Rien de ce qui est rendu ne porte une VALEUR du plan : des adresses et des comptes.

SCANNERS (`constats_trivy`, `constats_checkov`). Ne relaient que l'IDENTIFIANT de règle (forme bornée, sinon
`<id illisible>`), l'ADRESSE et la sévérité de chaque constat en échec — jamais un message, un bloc de code ni une
valeur. Formes lues (NON MESURÉES ici, scanners absents du poste) : trivy `Results[].Misconfigurations[]` (`ID` ou
`AVDID`, `Severity`, `Status` FAIL, `CauseMetadata.Resource`) ; checkov un objet ou une liste d'objets
`results.failed_checks[]` (`check_id`, `resource`, `severity`) — checkov sans clé d'API rend `severity: null`, donc
ses échecs sont RELAYÉS sans jamais faire un NO_GO (borne nommée). Une sortie illisible lève `ValueError`.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

RC_GO, RC_NO_GO, RC_REFUS, RC_DEGRADED = 0, 1, 2, 3


class Refus(Exception):
    """La demande est refusée (exit 2) ; `motif` est un code STABLE du contrat, `detail` le dit."""

    def __init__(self, motif: str, detail: str) -> None:
        super().__init__(f"{motif}: {detail}")
        self.motif = motif
        self.detail = detail


class Degrade(Exception):
    """Le verdict est absent (exit 3) : `outil` nomme ce qui manque ou ne répond pas."""

    def __init__(self, outil: str, motif: str) -> None:
        super().__init__(f"{outil}: {motif}")
        self.outil = outil
        self.motif = motif


# --- environnement : liste blanche, portée posée ----------------------------------------------------------------

ENV_RESEAU = ("PATH", "HOME", "TMPDIR", "LANG", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy",
              "https_proxy", "no_proxy", "SSL_CERT_FILE", "SSL_CERT_DIR")
ENV_AWS_AUTH = ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_CONFIG_FILE",
                "AWS_SHARED_CREDENTIALS_FILE", "AWS_ROLE_ARN", "AWS_WEB_IDENTITY_TOKEN_FILE", "AWS_ROLE_SESSION_NAME",
                "TF_AWS_WEB_IDENTITY_TOKEN")
ENV_NOMS_ADMIS = frozenset(ENV_RESEAU + ENV_AWS_AUTH)
ENV_PREFIXES_ADMIS = ("LC_", "ARM_", "AZURE_", "GOOGLE_", "CLOUDSDK_", "TF_TOKEN_")
ENV_SCANNER_NOMS = frozenset(ENV_RESEAU)
ENV_SCANNER_PREFIXES = ("LC_",)

# Variable posée -> champ de la cible. L'ORDRE gcp suit la précédence du provider google (GOOGLE_PROJECT d'abord).
PORTEE_PAR_FOURNISSEUR: dict[str, tuple[tuple[str, str], ...]] = {
    "azure": (("ARM_SUBSCRIPTION_ID", "subscription_id"), ("ARM_TENANT_ID", "tenant_id")),
    "gcp": (("GOOGLE_PROJECT", "project_id"), ("GOOGLE_CLOUD_PROJECT", "project_id"),
            ("GCLOUD_PROJECT", "project_id"), ("CLOUDSDK_CORE_PROJECT", "project_id")),
    "aws": (("AWS_REGION", "region"), ("AWS_DEFAULT_REGION", "region")),
}


def env_admis(ambiant: Mapping[str, str], noms: frozenset = ENV_NOMS_ADMIS,
              prefixes: tuple[str, ...] = ENV_PREFIXES_ADMIS) -> dict[str, str]:
    """Les seules variables de `ambiant` que la liste blanche admet — jamais une liste noire."""
    return {k: v for k, v in ambiant.items() if k in noms or k.startswith(prefixes)}


def portee_posee(cible: Mapping[str, Any]) -> dict[str, str]:
    """Les variables de PORTÉE que le runner pose depuis la cible, en écrasant l'ambiant."""
    fournisseur = cible["provider"]
    pose = {var: str(cible[champ]) for var, champ in PORTEE_PAR_FOURNISSEUR[fournisseur]}
    if fournisseur == "aws" and cible.get("profile"):
        pose["AWS_PROFILE"] = str(cible["profile"])
    return pose


def env_terraform(cible: Mapping[str, Any], ambiant: Mapping[str, str], plugin_cache: Path,
                  tfrc: Path) -> dict[str, str]:
    """L'environnement EXACT de terraform et des CLI d'`identity` (docstring du module, ENVIRONNEMENT)."""
    env = env_admis(ambiant)
    env.update(portee_posee(cible))
    env.update({"TF_WORKSPACE": str(cible["workspace"]), "TF_INPUT": "0", "TF_IN_AUTOMATION": "1",
                "TF_PLUGIN_CACHE_DIR": str(plugin_cache), "TF_CLI_CONFIG_FILE": str(tfrc)})
    return env


def env_scanner(ambiant: Mapping[str, str]) -> dict[str, str]:
    """trivy, checkov : réseau et locale seulement, aucune authentification cloud."""
    return env_admis(ambiant, ENV_SCANNER_NOMS, ENV_SCANNER_PREFIXES)


# --- git ---------------------------------------------------------------------------------------------------------

GIT_DELAI_S = 60
_GIT_CONSERVE = ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM")


def git_env(**pose: str) -> dict[str, str]:
    """L'environnement de l'appelant sans `GIT_*` (sauf la config globale/système), locale C, plus `pose`."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_") or k in _GIT_CONSERVE}
    env["LC_ALL"] = "C"
    env["LANGUAGE"] = ""
    env.update(pose)
    return env


def git(racine: Path, *args: str, env: Mapping[str, str] | None = None, entree: bytes | None = None,
        delai: int = GIT_DELAI_S) -> subprocess.CompletedProcess:
    """git en argv, hooks et fsmonitor coupés, sans verrou optionnel ; absent ou muet = `Degrade`."""
    argv = ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null",
            "-c", "core.autocrlf=false", "-C", str(racine), *args]
    try:
        return subprocess.run(argv, input=entree, capture_output=True, env=dict(env or git_env()),
                              timeout=delai, check=False)
    except FileNotFoundError as e:
        raise Degrade("git", "git absent du PATH") from e
    except subprocess.TimeoutExpired as e:
        raise Degrade(f"git (délai {delai} s dépassé)", f"délai dépassé: git {args[0] if args else ''}") from e


def _git_ok(racine: Path, *args: str, env: Mapping[str, str], quoi: str) -> subprocess.CompletedProcess:
    p = git(racine, *args, env=env)
    if p.returncode != 0:
        raise Degrade(f"git {quoi}", f"git {quoi} rc={p.returncode}")
    return p


# --- cache, dossiers de plan, balayage ---------------------------------------------------------------------------

CACHE_NOM = "cadre-tfdeploy"
PLUGIN_CACHE_NOM = "plugin-cache"
TFRC_NOM = "tfdeploy.tfrc"
PLANFILE_NOM = "plan.tfplan"
PLAN_JSON_NOM = "plan.json"
EXPORT_NOM = "export"
INDEX_NOM = "index.tmp"
PLAN_ID_RE = re.compile(r"\A([0-9]{10,})-[0-9a-f]{16}\Z")
EMPREINTE_DEPOT_RE = re.compile(r"\A[0-9a-f]{64}\Z")
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


def racine_cache() -> Path:
    """`~/.cache/cadre-tfdeploy`, absolu, HOME lu À L'APPEL."""
    return Path(os.path.abspath(Path.home() / ".cache" / CACHE_NOM))


def _mkdir_0700(chemin: Path) -> Path:
    if os.path.islink(chemin):
        raise Degrade("cache tfdeploy", f"{chemin} est un lien symbolique : refusé")
    chemin.mkdir(mode=0o700, exist_ok=True)
    os.chmod(chemin, 0o700)
    return chemin


def ecrire_0600(chemin: Path, data: bytes) -> None:
    """Écrit `data` en 0600, sans suivre un lien posé à ce chemin."""
    fd = os.open(str(chemin), os.O_WRONLY | os.O_CREAT | os.O_TRUNC | _O_NOFOLLOW, 0o600)
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, data)
    finally:
        os.close(fd)


def _hcl_chaine(texte: str) -> str:
    return texte.replace("\\", "\\\\").replace('"', '\\"').replace("${", "$${").replace("%{", "%%{")


def preparer_cache() -> tuple[Path, Path]:
    """Crée le cache (0700), le cache des providers (0700) et le `tfdeploy.tfrc` (0600) ; rend les deux chemins."""
    racine = racine_cache()
    racine.parent.mkdir(parents=True, exist_ok=True)
    _mkdir_0700(racine)
    plugin = _mkdir_0700(racine / PLUGIN_CACHE_NOM)
    tfrc = racine / TFRC_NOM
    ecrire_0600(tfrc, f'plugin_cache_dir = "{_hcl_chaine(str(plugin))}"\n'.encode("utf-8"))
    return plugin, tfrc


def empreinte_depot(racine: Path) -> str:
    return hashlib.sha256(os.path.abspath(racine).encode("utf-8", "surrogateescape")).hexdigest()


def nouvel_id_plan(t: float) -> str:
    return f"{int(t):010d}-{secrets.token_hex(8)}"


def age_id_plan(id_plan: str, t: float) -> float | None:
    m = PLAN_ID_RE.match(id_plan)
    return None if m is None else t - int(m.group(1))


def dossier_plan(racine_depot: Path, cible: str, id_plan: str) -> Path:
    return racine_cache() / empreinte_depot(racine_depot) / cible / id_plan


def creer_dossier_plan(racine_depot: Path, cible: str, id_plan: str) -> Path:
    """`<cache>/<empreinte>/<cible>/<id>`, chaque niveau en 0700 ; le cache doit déjà exister (`preparer_cache`)."""
    chemin = racine_cache()
    for nom in (empreinte_depot(racine_depot), cible, id_plan):
        chemin = _mkdir_0700(chemin / nom)
    return chemin


def effacer(chemin: Path) -> bool:
    """Efface `chemin` (dossier entier ou fichier) sans suivre de lien ; rend True s'il n'existe plus."""
    if not os.path.lexists(chemin):
        return True
    if os.path.islink(chemin) or not os.path.isdir(chemin):
        try:
            os.unlink(chemin)
        except OSError:
            pass
        return not os.path.lexists(chemin)

    def _rattraper(fonction: Any, nom: str, _exc: Any) -> None:
        try:
            os.chmod(os.path.dirname(nom), 0o700)
            if not os.path.islink(nom):
                os.chmod(nom, 0o700)
            fonction(nom)
        except OSError:
            pass

    if sys.version_info >= (3, 12):
        shutil.rmtree(chemin, onexc=_rattraper)
    else:
        shutil.rmtree(chemin, onerror=_rattraper)
    return not os.path.lexists(chemin)


def _sous_dossiers(chemin: Path) -> list[Path]:
    try:
        noms = sorted(os.listdir(chemin))
    except OSError:
        return []
    return [chemin / n for n in noms if os.path.isdir(chemin / n) and not os.path.islink(chemin / n)]


def balayer(t: float, seuil_s: float) -> list[str]:
    """Efface tout dossier de plan du cache dont l'âge (lu dans son NOM) dépasse `seuil_s` ; rend ce qui l'a été."""
    racine = racine_cache()
    if not racine.is_dir() or os.path.islink(racine):
        return []
    effaces: list[str] = []
    for depot in _sous_dossiers(racine):
        if not EMPREINTE_DEPOT_RE.match(depot.name):
            continue
        for cible in _sous_dossiers(depot):
            for plan in _sous_dossiers(cible):
                age = age_id_plan(plan.name, t)
                if age is not None and age > seuil_s and effacer(plan):
                    effaces.append(f"{depot.name[:12]}/{cible.name}/{plan.name}")
    return effaces


# --- export : index jetable, read-tree, checkout-index -----------------------------------------------------------

EXCLUS_EXPORT = (".agents/state", "runs")
SHA1_RE = re.compile(r"\A[0-9a-f]{40}\Z")
MODE_GITLINK = "160000"
_FILTRE_NEUTRE = ("unspecified", "unset")


def _entrees_index(racine: Path, env: Mapping[str, str]) -> list[tuple[str, str]]:
    """(mode, chemin) de chaque entrée de l'index jetable."""
    p = _git_ok(racine, "ls-files", "-s", "-z", env=env, quoi="ls-files")
    entrees = []
    for brut in p.stdout.split(b"\0"):
        if not brut:
            continue
        tete, _, chemin = brut.partition(b"\t")
        entrees.append((tete.split(b" ", 1)[0].decode("ascii", "replace"), chemin.decode("utf-8", "surrogateescape")))
    return entrees


def _filtres(racine: Path, env: Mapping[str, str], chemins: Sequence[str], cached: bool) -> list[tuple[str, str]]:
    """(chemin, valeur) de l'attribut `filter` de chaque chemin dont la valeur n'est pas neutre."""
    if not chemins:
        return []
    args = ["check-attr", "-z", "--stdin"] + (["--cached"] if cached else []) + ["filter"]
    entree = b"".join(c.encode("utf-8", "surrogateescape") + b"\0" for c in chemins)
    p = git(racine, *args, env=env, entree=entree)
    if p.returncode != 0:
        raise Degrade("git check-attr", f"git check-attr rc={p.returncode}")
    champs = p.stdout.split(b"\0")
    poses = []
    for i in range(0, len(champs) - 2, 3):
        valeur = champs[i + 2].decode("utf-8", "replace")
        if valeur not in _FILTRE_NEUTRE:
            poses.append((champs[i].decode("utf-8", "surrogateescape"), valeur))
    return poses


def exporter(racine: Path, dossier: Path, head: str) -> Path:
    """L'export du commit `head` (sha de HEAD relu par l'appelant, 40 hex) hors `.agents/state/` et `runs/` dans
    `<dossier>/export` (docstring du module, EXPORT)."""
    if not isinstance(head, str) or not SHA1_RE.match(head):
        raise Refus("head_non_relu", "sha de HEAD hors forme (40 hex attendus) : export refusé")
    index = dossier / INDEX_NOM
    env = git_env(GIT_INDEX_FILE=str(index))
    try:
        _git_ok(racine, "read-tree", head, env=env, quoi="read-tree <sha relu>")
        _git_ok(racine, "rm", "-r", "-q", "--cached", "--ignore-unmatch", "--", *EXCLUS_EXPORT, env=env,
                quoi="rm --cached")
        entrees = _entrees_index(racine, env)
        gitlinks = [c for m, c in entrees if m == MODE_GITLINK]
        if gitlinks:
            raise Refus("sous_module", f"{len(gitlinks)} sous-module(s) (gitlink) dans l'arbre, ex. {gitlinks[0]} : "
                                       "l'export ne les extrait pas fidèlement ; aucun déploiement de ce dépôt")
        chemins = [c for _m, c in entrees]
        poses = dict(_filtres(racine, env, chemins, cached=True))
        poses.update(_filtres(racine, env, chemins, cached=False))
        lfs = sorted(c for c, v in poses.items() if v == "lfs")
        if lfs:
            raise Refus("lfs", f"{len(lfs)} chemin(s) en filter=lfs, ex. {lfs[0]} : l'export n'en extrait que le "
                               "pointeur ; aucun déploiement de ce dépôt")
        if poses:
            premier = sorted(poses)[0]
            raise Refus("filtre_git", f"{len(poses)} chemin(s) portent un attribut filter, ex. {premier} "
                                      f"(filter={poses[premier]}) : un smudge réécrirait l'export")
        export = _mkdir_0700(dossier / EXPORT_NOM)
        _git_ok(racine, "checkout-index", "-a", f"--prefix={export}{os.sep}", env=env, quoi="checkout-index")
        return export
    finally:
        try:
            index.unlink()
        except OSError:
            pass


# --- empreinte de l'export ---------------------------------------------------------------------------------------

def _sha256_fichier(chemin: str) -> str:
    h = hashlib.sha256()
    with open(chemin, "rb") as fh:
        for bloc in iter(lambda: fh.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def _lignes_empreinte(base: str) -> Iterator[str]:
    for parent, sous, fichiers in os.walk(base, followlinks=False):
        for nom in sous + fichiers:
            chemin = os.path.join(parent, nom)
            rel = os.path.relpath(chemin, base)
            st = os.lstat(chemin)
            mode = stat.S_IMODE(st.st_mode)
            if stat.S_ISLNK(st.st_mode):
                yield f"l\0{rel}\0{os.readlink(chemin)}"
            elif stat.S_ISDIR(st.st_mode):
                yield f"d\0{rel}\0{mode:o}"
            elif stat.S_ISREG(st.st_mode):
                yield f"f\0{rel}\0{mode:o}\0{_sha256_fichier(chemin)}"
            else:
                yield f"x\0{rel}\0{stat.S_IFMT(st.st_mode):o}"


def empreinte(dossier: Path) -> str:
    """sha256 du relevé TRIÉ de `dossier` (chemins, types, modes, contenus, cibles de liens) ; absent ⇒ OSError."""
    base = str(dossier)
    if not os.path.isdir(base) or os.path.islink(base):
        raise FileNotFoundError(base)
    h = hashlib.sha256()
    for ligne in sorted(_lignes_empreinte(base)):
        h.update(ligne.encode("utf-8", "surrogateescape"))
        h.update(b"\n")
    return h.hexdigest()


def sha256_fichier(chemin: Path) -> str:
    return _sha256_fichier(str(chemin))


# --- plan JSON : comptes, destructions, portée écrite dans le code -----------------------------------------------

ACTIONS = {("create",): "create", ("update",): "update", ("delete",): "delete",
           ("delete", "create"): "replace", ("create", "delete"): "replace"}
ADRESSE_MAX = 256
_CONTROLE_RE = re.compile(r"[\x00-\x1f\x7f]")


def _adresse(brut: Any) -> str:
    return _CONTROLE_RE.sub("?", str(brut))[:ADRESSE_MAX] if isinstance(brut, str) and brut else "<adresse absente>"


def analyser_plan(plan: Any) -> dict[str, Any]:
    """Comptes et adresses de `resource_changes` ; forme inattendue ⇒ `ValueError` (jamais un compte faux)."""
    if not isinstance(plan, dict):
        raise ValueError("plan JSON : objet attendu")
    changements = plan.get("resource_changes")
    if changements is None:  # clé ABSENTE (plan sans changement) ; toute autre forme vide est hors forme
        changements = []
    if not isinstance(changements, list):
        raise ValueError("plan JSON : `resource_changes` n'est pas une liste")
    comptes = {cle: 0 for cle in ("create", "update", "delete", "replace")}
    adresses: dict[str, list[str]] = {cle: [] for cle in comptes}
    destructions: list[str] = []
    for rc in changements:
        change = rc.get("change") if isinstance(rc, dict) else None
        actions = change.get("actions") if isinstance(change, dict) else None
        if not isinstance(actions, list) or not all(isinstance(a, str) for a in actions):
            raise ValueError("plan JSON : `change.actions` absent ou hors forme")
        adresse = _adresse(rc.get("address"))
        cle = ACTIONS.get(tuple(actions))
        if cle is not None:
            comptes[cle] += 1
            adresses[cle].append(adresse)
        if "delete" in actions:
            destructions.append(adresse)
    return {"comptes": {**comptes, "destroy": len(destructions)}, "adresses": adresses,
            "destructions": destructions}


FOURNISSEURS_TF = {"azure": ("azurerm",), "gcp": ("google", "google-beta"), "aws": ("aws",)}
CLES_PORTEE_CODE = {"azure": (("subscription_id", "subscription_id"), ("tenant_id", "tenant_id")),
                    "gcp": (("project", "project_id"),), "aws": ()}


def _configs_fournisseur(plan: Mapping[str, Any], noms: Sequence[str]) -> list[tuple[str, dict]]:
    configuration = plan.get("configuration")
    pc = configuration.get("provider_config") if isinstance(configuration, dict) else None
    if not isinstance(pc, dict):
        return []
    trouves = []
    for cle, entree in sorted(pc.items()):
        if not isinstance(entree, dict):
            continue
        nom = entree.get("name") if isinstance(entree.get("name"), str) else ""
        complet = entree.get("full_name") if isinstance(entree.get("full_name"), str) else ""
        if nom in noms or complet.rsplit("/", 1)[-1] in noms:
            trouves.append((str(cle), entree))
    return trouves


def _constante(entree: Mapping[str, Any], cle: str) -> tuple[bool, Any]:
    expressions = entree.get("expressions")
    expr = expressions.get(cle) if isinstance(expressions, dict) else None
    if isinstance(expr, dict) and "constant_value" in expr:
        return True, expr["constant_value"]
    return False, None


def verifier_portee_code(plan: Mapping[str, Any], cible: Mapping[str, Any]) -> dict[str, Any]:
    """`portee_code_ecart` / `portee_non_fixee` (docstring du module, PLAN JSON) ; rend ce qui a été jugé."""
    fournisseur = cible["provider"]
    configs = _configs_fournisseur(plan, FOURNISSEURS_TF[fournisseur])
    if fournisseur == "aws":
        if not configs:
            raise Refus("portee_non_fixee", "aucun bloc provider aws dans configuration.provider_config : "
                                            "allowed_account_ids = [account_id] est EXIGÉ (CONVENTIONS_infra)")
        for cle, entree in configs:
            constant, valeur = _constante(entree, "allowed_account_ids")
            if not (constant and isinstance(valeur, list) and [str(v) for v in valeur] == [str(cible["account_id"])]):
                raise Refus("portee_non_fixee", f"bloc provider {cle!r} : allowed_account_ids n'est pas la constante "
                                                "[account_id] de la cible (profile et assume_role du bloc priment "
                                                "sur l'environnement posé)")
        return {"blocs_juges": [c for c, _e in configs], "cles": ["allowed_account_ids"]}
    non_constantes = []
    for cle, entree in configs:
        for cle_tf, champ in CLES_PORTEE_CODE[fournisseur]:
            constant, valeur = _constante(entree, cle_tf)
            if not constant or valeur is None:
                non_constantes.append(f"{cle}.{cle_tf}")
                continue
            if str(valeur).casefold() != str(cible[champ]).casefold():
                raise Refus("portee_code_ecart", f"bloc provider {cle!r} : la constante `{cle_tf}` contredit le "
                                                 f"`{champ}` de la cible (le bloc prime sur l'environnement posé)")
    return {"blocs_juges": [c for c, _e in configs], "non_juges": non_constantes}


# --- scanners : identifiants et adresses, jamais un message ------------------------------------------------------

SEVERITES_BLOQUANTES = frozenset({"HIGH", "CRITICAL"})
SEVERITES_CONNUES = frozenset({"LOW", "MEDIUM", "HIGH", "CRITICAL", "UNKNOWN", "INFO"})
ID_REGLE_RE = re.compile(r"\A[A-Za-z0-9_.:-]{1,64}\Z")


def _id_regle(brut: Any) -> str:
    return brut if isinstance(brut, str) and ID_REGLE_RE.match(brut) else "<id illisible>"


def _severite(brut: Any) -> str:
    s = str(brut).upper() if isinstance(brut, str) else ""
    return s if s in SEVERITES_CONNUES else "?"


def constats_trivy(sortie: bytes) -> list[dict[str, str]]:
    data = json.loads(sortie.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("trivy : objet JSON attendu")
    constats = []
    for resultat in data.get("Results") or []:
        if not isinstance(resultat, dict):
            raise ValueError("trivy : `Results[]` hors forme")
        for m in resultat.get("Misconfigurations") or []:
            if not isinstance(m, dict):
                raise ValueError("trivy : `Misconfigurations[]` hors forme")
            if m.get("Status", "FAIL") != "FAIL":
                continue
            cause = m.get("CauseMetadata") if isinstance(m.get("CauseMetadata"), dict) else {}
            constats.append({"regle": _id_regle(m.get("ID") or m.get("AVDID")), "adresse": _adresse(cause.get("Resource")),
                             "severite": _severite(m.get("Severity"))})
    return constats


def constats_checkov(sortie: bytes) -> list[dict[str, str]]:
    data = json.loads(sortie.decode("utf-8"))
    blocs = data if isinstance(data, list) else [data]
    constats = []
    for bloc in blocs:
        if not isinstance(bloc, dict):
            raise ValueError("checkov : objet JSON attendu")
        resultats = bloc.get("results") or {}
        if not isinstance(resultats, dict):
            raise ValueError("checkov : `results` hors forme")
        for c in resultats.get("failed_checks") or []:
            if not isinstance(c, dict):
                raise ValueError("checkov : `failed_checks[]` hors forme")
            constats.append({"regle": _id_regle(c.get("check_id")), "adresse": _adresse(c.get("resource")),
                             "severite": _severite(c.get("severity"))})
    return constats


def bloquants(constats: Sequence[Mapping[str, str]]) -> list[Mapping[str, str]]:
    return [c for c in constats if c.get("severite") in SEVERITES_BLOQUANTES]
