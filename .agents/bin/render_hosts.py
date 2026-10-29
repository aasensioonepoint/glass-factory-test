#!/usr/bin/env python3
"""render_hosts — `agents/<nom>.md` et `commands/<nom>.md` (SOURCES UNIQUES) rendues vers les hôtes.

    python3 .agents/bin/render_hosts.py [--check | --ecrire [--retirer-orphelins] | --importer] [--racine R]

T-01M5C1NXE5JWY6A0C2XWEGDPCC, décisions pilote S-01M5C01EAKQACKA27PNH804CR3 (`agents/` à la
racine = source unique) et S-01M5CD56VRE6MBVEKWB2FR7MWN (ce générateur et ses bancs sont des
chemins de garde de la voie directe, `tasks_direct.CHEMINS_GARDE`) ; T-01M5C1P67FN2YR9T3R0BHV7M3M
(`commands/` à la racine, même décision).

LES CIBLES d'une source `agents/<nom>.md` : le fichier de chaque hôte qu'elle porte (table
hôte -> (répertoire, motif) LUE dans `core-scripts/apply-mode.py`, jamais recopiée) et
`.agents/vendor/cadre/data/roster/<nom>.json`, DÉRIVÉ (sa sérialisation canonique). Celles d'une source
`commands/<nom>.md` : `.claude/commands/<nom>.md` (la source à l'octet) et, hors des commandes
Claude Code seul (`night`), le miroir cross-hôte
`.agents/skills/source-command-<nom>/SKILL.md` (`renderers.commands`), dérivé du corps de la
source par la règle de régénération des miroirs (sans ligne `Effort:`, trois traductions
d'hôte) ; la ligne qui pointe la skill partagée vit dans la source. Les formats source et les rendus sont
dans `.agents/vendor/cadre/renderers/` (PURS) ; toute E/S est ici.

CURSOR, CIBLE DÉRIVÉE, NON MESURÉE (T-01M5BZCDMCEQXKA2RKTB2EMW8M) : Cursor n'est PAS dans
`cadre.config.HOTES` ni dans les tables d'apply-mode ; rien ne prouve que Cursor lise ces
fichiers. Chaque déf qui porte un rendu `kimi` rend `.cursor/rules/<nom>.mdc` (frontmatter
`description` + `alwaysApply: false`, puis le corps kimi — `renderers.cursor`) ; une déf sans
rendu kimi n'en a pas, et `--check` comme `--ecrire` le DISENT (`cursor: sans rendu kimi :
<noms>`, sans écart). Chaque commande hors Claude Code seul rend `.cursor/commands/<nom>.md`
(les octets de la source quand son frontmatter ne porte que `description`). Sous `.cursor/`,
SEULS `.cursor/rules/*.mdc` et `.cursor/commands/*.md` sont lus, et seul un fichier RECONNU
comme rendu (`renderers.cursor.est_une_regle`, `commands.est_une_commande`) ET dont le témoin
du kit est présent y est un ORPHELIN ; tout autre fichier de ces deux dossiers est celui de
l'adoptant : HORS RENDU, jamais ETRANGER, jamais retiré. `--importer` ne lit jamais `.cursor/`.

LE TÉMOIN DE RENDU d'un fichier d'un dossier rendu est le fichier du kit du même nom :
`ROSTER/<nom>.json` pour une déf d'hôte ou une règle `.cursor/rules/`, le miroir
`source-command-<nom>` pour une commande `.claude/commands/` ou `.cursor/commands/`, lui-même
pour un JSON du roster ou un miroir. Le témoin compte présent sur le disque OU comme cible
du rendu (que `--ecrire` écrira). Un fichier qu'aucune source ne rend et SANS témoin présent,
ou sous `.cursor/` sans en-tête reconnu, est HORS RENDU : celui de l'adoptant, compté par une
note (`hors rendu : <n> fichier(s) …`, un compte, jamais un nom), jamais un écart, jamais
retiré, rc inchangé.

MODES (un seul) :
  --check    (défaut) compare chaque cible à son rendu et liste TOUS les écarts — source
             illisible, cible ABSENTE, DÉRIVE (octets différents), ORPHELIN (fichier de déf
             d'hôte reconnu, JSON du roster, commande ou miroir reconnu, qu'aucune source ne
             rend, dont le témoin du kit est présent), ETRANGER (fichier d'un dossier de défs
             ou de commandes, ou `SKILL.md` d'un dossier `source-command-*`, à témoin présent
             mais sans en-tête reconnu) ; chaque ligne nomme le fichier ; le résumé nomme le
             remède de CHAQUE classe d'écart. Un fichier sans témoin (un README.md, une déf de
             l'adoptant) est HORS RENDU : compté, jamais nommé ni bloquant.
  --ecrire   réécrit (temp + `os.replace`, mode conservé) les cibles ABSENT/DÉRIVE. Rien n'est
             écrit tant qu'une source est illisible, qu'un ETRANGER est présent, ou qu'un
             ORPHELIN est présent sans `--retirer-orphelins` (un `agents/` PARTIEL retirerait
             en masse les défs d'hôte, juges compris) ; un lien symbolique, sur une cible ou
             sur un répertoire qui sort de R, refuse AVANT toute écriture. Une entrée dont le
             nom ouvre par `.` (artefact d'OS, temporaire d'écriture) n'est jamais vue ni retirée ;
             `agents/README.md` et `commands/README.md` (le mode d'emploi de la source) ne sont
             jamais lus comme une source.
  --retirer-orphelins  avec `--ecrire` seulement : retire aussi les ORPHELIN. Un fichier de
             déf d'hôte n'est un ORPHELIN, donc retirable, qu'avec un en-tête reconnu ET son
             témoin du kit présent : une ligne `name:` dans le frontmatter markdown (un miroir
             `source-command-*` aussi), `name =` avant `developer_instructions` en TOML, une
             ligne `description:` dans le frontmatter d'une commande `.claude/commands/` ; un
             ETRANGER ou un HORS RENDU n'est JAMAIS retiré. Tout `*.json` du répertoire du
             roster est une déf (`cadre.roster` les lit tous). Les témoins (JSON du roster,
             miroirs) sont retirés APRÈS les fichiers qu'ils couvrent. Le dossier
             `source-command-<nom>/` d'un miroir retiré est retiré s'il reste vide.
  --importer amorce `agents/` depuis le roster JSON de R (`cadre.roster`, FORMAT 1 validé) ;
             n'écrase JAMAIS une source existante qui diffère (refus, rien d'écrit) — une source
             qui ne diffère que par le saut de ligne final toléré (`renderers.source`) est la même.
             Il n'amorce pas `commands/` (une source absente s'y restaure par `git restore`).
  --racine R l'arbre jugé (défaut : la racine de ce dépôt).

BORNES : l'écriture d'un fichier est atomique, pas celle du lot — une E/S qui échoue au milieu
laisse les cibles déjà écrites et les orphelins déjà retirés (rc 2), qu'un `--check` relance
nomme : les témoins étant retirés en dernier, un orphelin resté sur le disque garde le sien et
reste ORPHELIN. Un lien symbolique posé entre le contrôle et l'écriture (course) n'est pas
vu. Une déf retirée AVEC son JSON du roster, ou une commande sans miroir (`night`), laisse
ses rendus HORS RENDU, à ôter à la main. Le témoin est jugé sur le disque et le rendu
attendu, jamais sur l'histoire : un témoin retiré à la main (ni sur le disque ni rendu)
laisse hors rendu les fichiers qu'il couvrait.

CODES DE SORTIE : 0 à jour / fait ; 1 écart(s), source (`agents/` ou `commands/`) absente, vide
ou illisible, import refusé, orphelin sans `--retirer-orphelins`, étranger (une source ou une
cible ILLISIBLE sur le disque est un écart nommé, jamais une trace de pile) ; 2 usage, apply-mode
actif, lien
symbolique, Python < 3.11 (`tomllib` absent), paquet `cadre` introuvable, toute autre E/S
impossible.

APPLY-MODE : `<R>/.agents/state/local/MODEL_MODE` présent (lu sous R, jamais sous la racine du
script), les défs d'hôte portent les tiers `expert` : `--check` et `--ecrire` refusent (rc 2) et
nomment le remède `python3 core-scripts/apply-mode.py restore`. `--importer` ne lit ni n'écrit
une déf d'hôte : il n'est pas concerné.
"""
from __future__ import annotations

import argparse
import functools
import importlib.util
import os
import stat
import sys
import tempfile
from pathlib import Path
from typing import NamedTuple

KIT = Path(__file__).resolve().parents[2]
#: Le paquet `cadre` vit sous `.agents/vendor/cadre` (T-01M5BXTRP8GKS7DMDQCTKK88DZ).
CADRE = ".agents/vendor/cadre"


def _amorcer_cadre() -> None:
    """Le paquet `cadre` EXACT de CETTE racine (`vendor_paths.charger_paquet`), comme `project_init.py`."""
    chemin = Path(__file__).resolve().with_name("vendor_paths.py")
    spec = importlib.util.spec_from_file_location("_render_hosts_vendor_paths", chemin)
    if spec is None or spec.loader is None:  # pragma: no cover - défensif
        raise ImportError(f"résolveur illisible : {chemin}")
    resolveur = importlib.util.module_from_spec(spec)
    existant = sys.modules.get(spec.name)
    sys.modules[spec.name] = resolveur  # enregistré AVANT `exec_module` (T-00000134)
    try:
        spec.loader.exec_module(resolveur)
    except BaseException:
        if existant is not None:
            sys.modules[spec.name] = existant
        else:
            sys.modules.pop(spec.name, None)
        raise
    resolveur.charger_paquet(KIT, "cadre")

# Un script lancé par n'importe quel `python3`, hors du `requires-python` du paquet : le test reste.
if sys.version_info < (3, 11):  # noqa: UP036 — le rendu TOML relit par `tomllib` : dit, jamais muet
    print(f"render_hosts : Python >= 3.11 requis (tomllib) — {sys.version.split()[0]} trouve", file=sys.stderr)
    sys.exit(2)

try:
    _amorcer_cadre()
    from cadre import roster
    from cadre.config import HOTES
    from cadre.renderers import rendus, serialiser
    from cadre.renderers.commands import PREFIXE_MIROIR, est_une_commande, rendus_commande
    from cadre.renderers.cursor import HOTE_CORPS, commande as commande_cursor, est_une_regle, regle
    from cadre.renderers.source import ecrire_source, lire_source
    from cadre.workspace import Workspace
except ImportError as exc:  # pragma: no cover - dit, jamais muet
    print(f"render_hosts : paquet `cadre` (renderers) introuvable — {exc}", file=sys.stderr)
    sys.exit(2)
except LookupError as exc:  # `vendor_paths.PaquetIntrouvable`, ou une clé levée pendant l'import — dit, jamais muet
    print(f"render_hosts : paquet `cadre` introuvable ou illisible — {type(exc).__name__}: {exc}", file=sys.stderr)
    sys.exit(2)

SOURCES = "agents"
SUFFIXE_SOURCE = ".md"
ROSTER = f"{CADRE}/{roster.REPERTOIRE}"
MODE_RELATIF = ".agents/state/local/MODEL_MODE"
RESTAURER = "python3 core-scripts/apply-mode.py restore"
REMEDE_MODE = (f"apply-mode actif ({MODE_RELATIF} present) : les defs d'hote portent les tiers `expert` ; "
               f"`{RESTAURER}` d'abord, puis relance")
#: `config.HOTES` -> nom d'hôte d'apply-mode, là où ils diffèrent.
ALIAS = {"copilot": "github"}
IGNORE_SI_PREFIXE = "."
#: Fichiers de `agents/` et de `commands/` qui ne sont PAS des sources (nom exact) : jamais lus ni rendus.
NON_SOURCES = frozenset({"README.md"})
COMMANDES = "commands"
CIBLES_COMMANDES = ".claude/commands"
SKILLS = ".agents/skills"
SKILL = "SKILL.md"
CURSOR_REGLES = ".cursor/rules"
SUFFIXE_REGLE = ".mdc"
CURSOR_COMMANDES = ".cursor/commands"
#: Sous `.cursor/`, un fichier non reconnu comme rendu est celui de l'adoptant : HORS RENDU, ni ETRANGER ni retiré.
CURSOR = (f"{CURSOR_REGLES}/", f"{CURSOR_COMMANDES}/")


def cible_commande(nom: str) -> str:
    return f"{CIBLES_COMMANDES}/{nom}{SUFFIXE_SOURCE}"


def cible_miroir(nom: str) -> str:
    return f"{SKILLS}/{PREFIXE_MIROIR}{nom}/{SKILL}"


def cible_regle(nom: str) -> str:
    return f"{CURSOR_REGLES}/{nom}{SUFFIXE_REGLE}"


def cible_commande_cursor(nom: str) -> str:
    return f"{CURSOR_COMMANDES}/{nom}{SUFFIXE_SOURCE}"


def _source_de(rel: str) -> str:
    """Le répertoire source dont `rel` serait une cible."""
    return COMMANDES if rel.startswith((f"{CIBLES_COMMANDES}/", f"{SKILLS}/", f"{CURSOR_COMMANDES}/")) else SOURCES


class Refus(Exception):
    """Un refus AVANT toute écriture ; `code` est le code de sortie."""

    def __init__(self, message: str, code: int) -> None:
        super().__init__(message)
        self.code = code


# --- la table des hôtes, LUE dans apply-mode.py --------------------------------------------------
@functools.cache
def _apply_mode():
    spec = importlib.util.spec_from_file_location("render_hosts_apply_mode", KIT / "core-scripts" / "apply-mode.py")
    module = importlib.util.module_from_spec(spec)
    # Enregistré AVANT d'exécuter (T-00000134, `test_modload_registration.py`).
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def emplacements() -> dict[str, tuple[str, str]]:
    """Hôte de `HOTES` -> (répertoire, motif `{agent}`), dans l'ordre de `HOTES`."""
    mode = _apply_mode()
    table = {hote: (rep, motif) for hote, (rep, motif, _axes) in mode.LEVER_HOSTS.items()}
    table.update(mode.INDICATIVE_HOSTS)
    return {hote: table[ALIAS.get(hote, hote)] for hote in HOTES}


def cible_hote(hote: str, nom: str) -> str:
    rep, motif = emplacements()[hote]
    return f"{rep}/{motif.format(agent=nom)}"


def cibles_possibles(nom: str) -> set[str]:
    return {cible_hote(hote, nom) for hote in HOTES} | {f"{ROSTER}/{nom}{roster.SUFFIXE}", cible_regle(nom)}


# --- les sources et leurs rendus -----------------------------------------------------------------
def _lire_repertoire(racine: Path, repertoire: str, lire, absent: str) -> tuple[dict, list[str], set[str]]:
    """(nom -> valeur lue, fautes, noms des sources illisibles) pour chaque `<nom>.md` de
    `repertoire` ; `lire(texte, nom, rel)` valide ou lève une `ValueError` qui nomme la source.
    Refus rc 1 si le répertoire est absent (`absent` dit le remède) ou vide."""
    rep = racine / repertoire
    if not rep.is_dir():
        raise Refus(f"source absente : {repertoire}/ n'existe pas sous {racine} — {absent}", 1)
    lus: dict = {}
    fautes: list[str] = []
    illisibles: set[str] = set()
    for chemin in sorted(rep.iterdir()):
        if chemin.name.startswith(IGNORE_SI_PREFIXE) or chemin.name in NON_SOURCES:
            continue
        rel = f"{repertoire}/{chemin.name}"
        if chemin.suffix != SUFFIXE_SOURCE or not chemin.is_file():
            fautes.append(f"ILLISIBLE {rel} : hors format, seul un `<nom>{SUFFIXE_SOURCE}` vit dans {repertoire}/")
            illisibles.add(chemin.stem)
            continue
        try:
            lus[chemin.stem] = lire(chemin.read_bytes().decode("utf-8"), chemin.stem, rel)
        except UnicodeDecodeError as exc:
            fautes.append(f"ILLISIBLE {rel} : octets non UTF-8 — {exc}")
            illisibles.add(chemin.stem)
        except OSError as exc:
            fautes.append(f"ILLISIBLE {rel} : lecture impossible — {exc.strerror or exc}")
            illisibles.add(chemin.stem)
        except ValueError as exc:
            fautes.append(f"ILLISIBLE {exc}")
            illisibles.add(chemin.stem)
    if not lus and not fautes:
        raise Refus(f"source vide : aucune `<nom>{SUFFIXE_SOURCE}` sous {repertoire}/ — jamais un rendu nul", 1)
    return lus, fautes, illisibles


def _lire_def(texte: str, nom: str, rel: str) -> dict:
    """L'objet de la source, dont la règle Cursor se rend : son refus rend la source ILLISIBLE."""
    objet = lire_source(texte, nom, rel)
    try:
        regle(objet)
    except ValueError as exc:
        raise ValueError(f"{rel} : {exc}") from exc
    return objet


def lire_sources(racine: Path) -> tuple[dict[str, dict], list[str], set[str]]:
    """(nom -> objet FORMAT 1, fautes, noms des sources illisibles). Refus rc 1 si `agents/`
    est absent ou vide."""
    return _lire_repertoire(racine, SOURCES, _lire_def, "`--importer` l'amorce depuis le roster JSON")


def _lire_texte_de_commande(texte: str, nom: str, rel: str) -> str:
    try:
        commande_cursor(texte, nom, rel)
    except ValueError as exc:
        raise ValueError(exc if str(exc).startswith(rel) else f"{rel} : {exc}") from exc
    return texte


def lire_commandes(racine: Path) -> tuple[dict[str, str], list[str], set[str]]:
    """(nom -> texte validé de `commands/<nom>.md`, fautes, noms illisibles). Refus rc 1 si
    `commands/` est absent ou vide."""
    return _lire_repertoire(racine, COMMANDES, _lire_texte_de_commande,
                            f"`git restore {COMMANDES}/` la restaure (aucun import ne l'amorce)")


def attendus(objets: dict[str, dict]) -> dict[str, tuple[bytes, str]]:
    """Cible relative -> (octets attendus, source qui la rend)."""
    sortie: dict[str, tuple[bytes, str]] = {}
    for nom, objet in objets.items():
        source = f"{SOURCES}/{nom}{SUFFIXE_SOURCE}"
        for hote, texte in rendus(objet).items():
            sortie[cible_hote(hote, nom)] = (texte.encode("utf-8"), source)
        sortie[f"{ROSTER}/{nom}{roster.SUFFIXE}"] = (serialiser(objet).encode("utf-8"), source)
        texte = regle(objet)
        if texte is not None:
            sortie[cible_regle(nom)] = (texte.encode("utf-8"), source)
    return sortie


def attendus_commandes(racine: Path, textes: dict[str, str]) -> dict[str, tuple[bytes, str]]:
    """Cible relative -> (octets attendus, source) des commandes : `.claude/commands/<nom>.md`
    et, hors Claude Code seul, le miroir, dont la traduction `/<commande>` lit tous les noms."""
    sortie: dict[str, tuple[bytes, str]] = {}
    for nom, texte in textes.items():
        source = f"{COMMANDES}/{nom}{SUFFIXE_SOURCE}"
        rendus_cmd = rendus_commande(texte, nom, textes, source)
        sortie[cible_commande(nom)] = (rendus_cmd["claude"].encode("utf-8"), source)
        if "miroir" in rendus_cmd:
            sortie[cible_miroir(nom)] = (rendus_cmd["miroir"].encode("utf-8"), source)
        cursor = commande_cursor(texte, nom, source)
        if cursor is not None:
            sortie[cible_commande_cursor(nom)] = (cursor.encode("utf-8"), source)
    return sortie


def _present(chemin: Path) -> bool:
    return chemin.is_file() or chemin.is_symlink()


def existants(racine: Path) -> set[str]:
    """Les fichiers de déf d'hôte, les JSON du roster, les commandes `.claude/commands/*.md`,
    les miroirs `.agents/skills/source-command-*/SKILL.md`, `.cursor/rules/*.mdc` et
    `.cursor/commands/*.md` présents sous `racine` (point initial ignoré)."""
    vus: set[str] = set()
    reps = [(rep, *motif.split("{agent}")) for rep, motif in emplacements().values()]
    reps.append((ROSTER, "", roster.SUFFIXE))
    reps.append((CIBLES_COMMANDES, "", SUFFIXE_SOURCE))
    reps.append((CURSOR_REGLES, "", SUFFIXE_REGLE))
    reps.append((CURSOR_COMMANDES, "", SUFFIXE_SOURCE))
    for rep, prefixe, suffixe in reps:
        if not (racine / rep).is_dir():
            continue
        for chemin in (racine / rep).glob(f"{prefixe}*{suffixe}"):
            if not chemin.name.startswith(IGNORE_SI_PREFIXE) and _present(chemin):
                vus.add(f"{rep}/{chemin.name}")
    if (racine / SKILLS).is_dir():
        for chemin in (racine / SKILLS).glob(f"{PREFIXE_MIROIR}*/{SKILL}"):
            if _present(chemin):
                vus.add(f"{SKILLS}/{chemin.parent.name}/{SKILL}")
    return vus


def est_une_def(racine: Path, rel: str) -> bool:
    """Le fichier `rel` porte-t-il un en-tête de déf reconnu ? Condition NÉCESSAIRE d'un ORPHELIN
    (retirable), jamais suffisante : son témoin du kit (`_temoin`) doit aussi être présent,
    sinon le fichier est HORS RENDU. Tout JSON du roster en est une ; une commande `.claude/commands/` en est une avec une ligne
    `description:` dans son frontmatter (`renderers.commands.est_une_commande`), une commande
    `.cursor/commands/` aussi, une règle `.cursor/rules/` avec la forme rendue
    (`renderers.cursor.est_une_regle`) ; un lien n'est pas lu, il reste candidat et
    `_refuser_les_liens` le refuse ; un fichier illisible n'en est pas une."""
    chemin = racine / rel
    if rel.startswith(f"{ROSTER}/") or chemin.is_symlink():
        return True
    try:
        texte = chemin.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    if rel.startswith((f"{CIBLES_COMMANDES}/", f"{CURSOR_COMMANDES}/")):
        return est_une_commande(texte)
    if rel.startswith(f"{CURSOR_REGLES}/"):
        return est_une_regle(texte)
    lignes = texte.split("\n")
    if chemin.suffix == ".toml":
        for ligne in lignes:
            if ligne.startswith(("developer_instructions", "[")):
                return False
            if ligne.startswith("name") and ligne[len("name"):].lstrip(" \t").startswith("="):
                return True
        return False
    if lignes[0] != "---":
        return False
    for ligne in lignes[1:]:
        if ligne == "---":
            return False
        if ligne.startswith("name:"):
            return True
    return False


def _temoin(rel: str) -> str:
    """Le TÉMOIN DE RENDU de `rel`, fichier de l'espace de noms du kit : le JSON du roster
    `ROSTER/<nom>.json` pour une déf d'hôte (nom tiré du motif `{agent}` d'`emplacements()`) ou
    une règle `.cursor/rules/<nom>.mdc` ; le miroir `source-command-<nom>` pour une commande
    `.claude/commands/` ou `.cursor/commands/` ; `rel` lui-même pour un JSON du roster ou un
    miroir. Sans témoin présent, un fichier est HORS RENDU : celui de l'adoptant."""
    if rel.startswith((f"{ROSTER}/", f"{SKILLS}/")):
        return rel
    repertoire, _, fichier = rel.rpartition("/")
    if repertoire in (CIBLES_COMMANDES, CURSOR_COMMANDES):
        return cible_miroir(fichier.removesuffix(SUFFIXE_SOURCE))
    if repertoire == CURSOR_REGLES:
        nom = fichier.removesuffix(SUFFIXE_REGLE)
    else:
        prefixe, suffixe = {rep: motif.split("{agent}") for rep, motif in emplacements().values()}[repertoire]
        nom = fichier[len(prefixe):len(fichier) - len(suffixe)]
    return f"{ROSTER}/{nom}{roster.SUFFIXE}"


class Ecarts(NamedTuple):
    lignes: list[str]       # écarts lisibles, dans l'ordre : ABSENT/DERIVE, ORPHELIN, ETRANGER
    a_ecrire: list[str]     # cibles ABSENT/DERIVE
    orphelins: list[str]    # défs reconnues, à témoin, qu'aucune source ne rend : retirables sur drapeau
    etrangers: list[str]    # à témoin, ni rendus ni reconnus : jamais retirés
    hors_rendu: list[str]   # sans témoin du kit, ou `.cursor/` sans en-tête : à l'adoptant, comptés, jamais nommés


def ecarts(racine: Path, voulus: dict[str, tuple[bytes, str]], muets: set[str]) -> Ecarts:
    """Les écarts de `racine` à `voulus`. `muets` : cibles d'une source illisible. Seul un
    fichier dont le témoin (`_temoin`) est présent peut être ORPHELIN ou ETRANGER."""
    lignes: list[str] = []
    a_ecrire: list[str] = []
    for rel, (octets, source) in sorted(voulus.items()):
        chemin = racine / rel
        if not chemin.is_file():
            lignes.append(f"ABSENT   {rel} : rendu de {source}, absent du disque")
            a_ecrire.append(rel)
            continue
        try:
            sur_disque = chemin.read_bytes()
        except OSError as exc:
            lignes.append(f"DERIVE   {rel} : illisible ({exc.strerror or exc}), rendu de {source}")
            a_ecrire.append(rel)
            continue
        if sur_disque != octets:
            lignes.append(f"DERIVE   {rel} : differe du rendu de {source}")
            a_ecrire.append(rel)
    restes = sorted(existants(racine) - set(voulus) - muets)
    # Un témoin compte présent sur le disque OU comme cible du rendu (ABSENT, que `--ecrire` écrira) :
    # une seule passe classe l'ORPHELIN, jamais « hors rendu » puis ORPHELIN au `--check` suivant.
    vus = [rel for rel in restes if _temoin(rel) in voulus or _present(racine / _temoin(rel))]
    orphelins = [rel for rel in vus if est_une_def(racine, rel)]
    etrangers = [rel for rel in vus if rel not in orphelins and not rel.startswith(CURSOR)]
    hors_rendu = [rel for rel in restes if rel not in orphelins and rel not in etrangers]
    lignes += [f"ORPHELIN {rel} : aucune source {_source_de(rel)}/ ne le rend" for rel in orphelins]
    lignes += [f"ETRANGER {rel} : dans un dossier de defs ou de commandes, sans en-tete reconnu (ligne "
               "`name`, `description` pour une commande) — jamais retire, a deplacer ou retirer a la main"
               for rel in etrangers]
    return Ecarts(lignes, a_ecrire, orphelins, etrangers, hors_rendu)


def _refuser_apply_mode(racine: Path) -> None:
    if (racine / MODE_RELATIF).exists():
        raise Refus(REMEDE_MODE, 2)


def _refuser_les_liens(racine: Path, rels: list[str]) -> None:
    """Un lien sur une cible, ou un ancêtre existant qui se résout hors de `racine` : refus rc 2."""
    base = racine.resolve()
    for rel in rels:
        chemin = racine / rel
        ancetre = chemin.parent
        while not ancetre.exists() and ancetre != racine:
            ancetre = ancetre.parent
        if chemin.is_symlink() or not ancetre.resolve().is_relative_to(base):
            raise Refus(f"lien symbolique refuse ({rel}) : une ecriture le suivrait hors de {racine}", 2)


def ecrire_atomique(chemin: Path, octets: bytes) -> None:
    """Temporaire `.<nom>.*` du même répertoire (O_EXCL, jamais suivi), puis `os.replace` :
    un lecteur voit l'ancien fichier ou le nouveau, jamais un fichier tronqué. Le mode d'un
    fichier existant est conservé ; sinon, 0666 moins l'umask (comme `write_bytes`)."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    if chemin.is_file():
        mode = stat.S_IMODE(chemin.stat().st_mode)
    else:
        masque = os.umask(0)
        os.umask(masque)
        mode = 0o666 & ~masque
    fd, temporaire = tempfile.mkstemp(dir=chemin.parent, prefix=f".{chemin.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as flux:
            flux.write(octets)
        os.chmod(temporaire, mode)
        os.replace(temporaire, chemin)
    except BaseException:
        Path(temporaire).unlink(missing_ok=True)
        raise


# --- les modes -----------------------------------------------------------------------------------
class Etat(NamedTuple):
    fautes: list[str]
    ecarts: Ecarts
    voulus: dict[str, tuple[bytes, str]]
    notes: list[str]        # dit, sans écart : les défs sans règle Cursor, le compte des hors rendu


def _etat(racine: Path) -> Etat:
    objets, fautes, illisibles = lire_sources(racine)
    textes, fautes_cmd, illisibles_cmd = lire_commandes(racine)
    muets: set[str] = set()
    for nom in illisibles:
        muets |= cibles_possibles(nom)
    for nom in illisibles_cmd:
        muets |= {cible_commande(nom), cible_miroir(nom), cible_commande_cursor(nom)}
    voulus = attendus(objets) | attendus_commandes(racine, textes)
    sans_kimi = sorted(nom for nom, objet in objets.items() if HOTE_CORPS not in objet["rendus"])
    notes = [f"cursor: sans rendu {HOTE_CORPS} : {', '.join(sans_kimi)}"] if sans_kimi else []
    e = ecarts(racine, voulus, muets)
    if e.hors_rendu:
        # Un COMPTE, jamais un nom : un fichier de l'adoptant n'est jamais nommé ; rc inchangé.
        notes.append(f"hors rendu : {len(e.hors_rendu)} fichier(s) sans temoin du kit "
                     "(roster ou miroir du meme nom) ou sans en-tete reconnu sous .cursor/, laisses intacts")
    return Etat(fautes + fautes_cmd, e, voulus, notes)


SCRIPT = "python3 .agents/bin/render_hosts.py"


def verifier(racine: Path) -> int:
    _refuser_apply_mode(racine)
    fautes, e, voulus, notes = _etat(racine)
    for note in notes:
        print(note)
    lignes = fautes + e.lignes
    for ligne in lignes:
        print(ligne)
    if not lignes:
        print(f"render_hosts : a jour — {len(voulus)} cible(s) rendue(s) depuis {SOURCES}/ et {COMMANDES}/")
        return 0
    remedes = []
    if fautes:
        remedes.append("corrige d'abord la source illisible")
    if e.a_ecrire:
        remedes.append(f"`{SCRIPT} --ecrire` rend les cibles ABSENT/DERIVE depuis {SOURCES}/ et {COMMANDES}/")
    if e.orphelins:
        remedes.append(f"ORPHELIN : une source manque a {SOURCES}/ ou {COMMANDES}/ ? restaure-la "
                       f"(`git restore {SOURCES}/<nom>.md` ou `git restore {COMMANDES}/<nom>.md` ; pour "
                       f"{SOURCES}/, `{SCRIPT} --importer` la recree aussi du roster JSON tant qu'aucune "
                       f"source n'en differe) ; def ou commande retiree pour de bon : "
                       f"`{SCRIPT} --ecrire --retirer-orphelins`")
    if e.etrangers:
        remedes.append("ETRANGER : a trancher a la main, jamais retire par ce script")
    print(f"render_hosts : {len(lignes)} ecart(s) — " + " ; ".join(remedes))
    return 1


def ecrire(racine: Path, retirer_orphelins: bool = False) -> int:
    _refuser_apply_mode(racine)
    fautes, e, voulus, notes = _etat(racine)
    for note in notes:
        print(note)
    if fautes:
        for ligne in fautes:
            print(ligne)
        print("render_hosts : source(s) illisible(s), rien n'est ecrit")
        return 1
    bloquants = [ligne for ligne in e.lignes if ligne.startswith("ETRANGER")
                 or (ligne.startswith("ORPHELIN") and not retirer_orphelins)]
    if bloquants:
        for ligne in bloquants:
            print(ligne)
        causes = (["un ETRANGER se tranche a la main"] if e.etrangers else []) + (
            [f"un ORPHELIN ne se retire qu'avec `--retirer-orphelins` (un {SOURCES}/ partiel retirerait "
             "les defs d'hote qu'il ne rend pas)"] if e.orphelins and not retirer_orphelins else [])
        print("render_hosts : rien n'est ecrit — " + " ; ".join(causes))
        return 1
    # Les témoins (JSON du roster, miroirs) se retirent EN DERNIER : un retrait qui échoue au
    # milieu laisse le témoin, et la relance nomme encore l'ORPHELIN qu'il couvre.
    retraits = sorted(e.orphelins, key=lambda rel: _temoin(rel) == rel) if retirer_orphelins else []
    gestes = e.a_ecrire + retraits
    _refuser_les_liens(racine, gestes)
    for rel in gestes:
        chemin = racine / rel
        if rel in voulus:
            ecrire_atomique(chemin, voulus[rel][0])
            print(f"ecrit   {rel}")
        else:
            chemin.unlink()
            print(f"retire  {rel}")
            if rel.startswith(f"{SKILLS}/{PREFIXE_MIROIR}") and not any(chemin.parent.iterdir()):
                chemin.parent.rmdir()
    print("render_hosts : " + ("cibles rendues" if gestes else "deja a jour, aucun fichier touche"))
    return 0


def _objet(definition: roster.Definition) -> dict:
    return {"version_format": 1, "nom": definition.nom, "rendus": {
        hote: {"entete": list(rendu.entete),
               "corps": {"comme": rendu.comme} if rendu.comme is not None else list(rendu.corps or ())}
        for hote, rendu in definition.rendus.items()}}


def _meme_source(existant: bytes, objet: dict, rel: str) -> bool:
    """La source sur disque rend-elle le même objet (saut de ligne final toléré compris) ?"""
    try:
        lu = lire_source(existant.decode("utf-8"), objet["nom"], rel)
    except (UnicodeDecodeError, ValueError):
        return False
    return serialiser(lu) == serialiser(objet)


def importer(racine: Path) -> int:
    try:
        charge = roster._lire(Workspace(racine / CADRE))
    except roster.RosterIllisible as exc:
        print(f"render_hosts : roster illisible, rien n'est importe — {exc}")
        return 1
    textes: dict[str, bytes] = {}
    conflits: list[str] = []
    for definition in charge.definitions:
        rel = f"{SOURCES}/{definition.nom}{SUFFIXE_SOURCE}"
        objet = _objet(definition)
        try:
            octets = ecrire_source(objet, rel).encode("utf-8")
        except ValueError as exc:
            conflits.append(f"REFUS    {exc}")
            continue
        chemin = racine / rel
        if chemin.is_file():
            existant = chemin.read_bytes()
            if existant != octets and not _meme_source(existant, objet, rel):
                conflits.append(f"CONFLIT  {rel} : source existante differente, --importer n'ecrase jamais une source")
        else:
            textes[rel] = octets
    if conflits:
        for ligne in conflits:
            print(ligne)
        print("render_hosts : import refuse, rien n'est ecrit")
        return 1
    _refuser_les_liens(racine, sorted(textes))
    for rel, octets in sorted(textes.items()):
        ecrire_atomique(racine / rel, octets)
        print(f"importe {rel}")
    print(f"render_hosts : {len(textes)} source(s) importee(s) sur {charge.cardinal} def(s) du roster")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="render_hosts.py", description=__doc__.split("\n\n")[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_const", dest="mode", const="check")
    mode.add_argument("--ecrire", action="store_const", dest="mode", const="ecrire")
    mode.add_argument("--importer", action="store_const", dest="mode", const="importer")
    parser.add_argument("--retirer-orphelins", action="store_true",
                        help="avec --ecrire : retire aussi les ORPHELIN (defs d'hote reconnues sans source)")
    parser.add_argument("--racine", type=Path, default=KIT)
    args = parser.parse_args(argv)
    if args.retirer_orphelins and args.mode != "ecrire":
        parser.error("--retirer-orphelins ne vaut qu'avec --ecrire")
    racine = args.racine.absolute()
    action = {"ecrire": functools.partial(ecrire, retirer_orphelins=args.retirer_orphelins),
              "importer": importer}.get(args.mode, verifier)
    try:
        return action(racine)
    except Refus as refus:
        print(f"render_hosts : {refus}", file=sys.stderr if refus.code == 2 else sys.stdout)
        return refus.code
    except OSError as exc:
        print(f"render_hosts : E/S impossible — {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
