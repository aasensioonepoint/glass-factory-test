"""Le roster canonique des défs d'agents, lu dans le NOYAU (T-00000973, BK-139).

`data/roster/<nom>.json` porte, une def par fichier, ses RENDUS par hôte. Ce
module les LIT et les VALIDE ; il ne rend aucun fichier d'hôte et ne compare
rien aux defs vivantes. Le roster est DÉRIVÉ de la source unique `agents/<nom>.md`
(décision pilote S-01M5C01EAKQACKA27PNH804CR3) : `bash .agents/pyrun.sh
.agents/bin/render_hosts.py --ecrire` rend les défs des cinq hôtes ET ces JSON,
dans le même commit, et `--check` signale toute dérive des fichiers à plat de ces
dossiers (un sous-dossier, un fichier caché ou un autre suffixe n'est pas lu). L'équivalence roster /
defs vivantes reste jugée par `.agents/evals/test_cadre_roster.py`, dont le
`--regenerer` RÉÉCRIT encore la donnée depuis les defs d'hôte (`.claude/agents/`
et ses quatre jumeaux) : une SECONDE voie d'écriture, gardée, que `--check`
contredit si elle s'écarte de `agents/`. Rien n'écrit ces JSON à la main.

FORMAT 1, la forme entière (`_valider`, stdlib seule) :

    {"version_format": 1, "nom": "<nom>", "rendus": {"<hote>": RENDU, ...}}
    RENDU = {"entete": [ligne, ...], "corps": [ligne, ...] | {"comme": "claude"}}

* La racine porte EXACTEMENT ces trois clés ; `version_format` est l'ENTIER 1.
  `nom` est un identifiant ASCII minuscule ÉGAL au nom du fichier.
* Les clés de `rendus` sont des hôtes de `config.HOTES` ; `claude` est
  obligatoire : c'est la RÉFÉRENCE. Un corps identique au sien s'écrit
  `{"comme": "claude"}` (S-00003176). `comme` n'est admis que sur un hôte autre
  que `claude`, et ne vise que `claude` : ni auto-référence, ni chaîne de renvois.
* Une ligne est une chaîne SANS `\\n` ni `\\r` : le texte d'un rendu est ses
  lignes jointes par `\\n`, ce qui garde un fichier qui finit par « \\n\\n ».
* L'entête porte sa ligne d'identité : `name: <nom>` (frontmatter YAML) ou
  `name = "<nom>"` (TOML, `_IDENTITE_TOML`).
* AUCUN MARQUEUR N'EST STOCKÉ. Une ligne d'entête est refusée, à TOUTE
  indentation et sur TOUTE ligne de l'entête, si elle est un commentaire (`#`
  ou `<!--`, blancs admis avant `cadre.`) qui ouvre sur `cadre.` — clé de
  `managed.CLES` ou non, mention sans `: <valeur>` comprise —, ou, hors TOML,
  une clé `cadre.…` NUE ou quotée (`cadre.managed: true`, la forme d'avant,
  S-00002846). Le marqueur se POSE au rendu (T-00000752), jamais dans la
  source (décision pilote S-00003215) ; et aucune autre ligne `cadre.` ne se
  stocke.
  PLUS STRICT QUE `managed.lire`, qui ne juge que sa RÉGION, en colonne 0 :
  dans un frontmatter, `# cadre.…`, `cadre.…` nue et `#cadre.` collé à l'une
  des trois clés ; dans un TOML, la suite de lignes de TÊTE. Mesuré (T6 du
  banc, sur le rendu que le banc recompose) : `lire` accepte `  # cadre.autre:
  x` indenté, `<!-- cadre.… -->` dans un frontmatter, `# cadre.…` sous la tête
  d'un TOML, `  cadre.managed: true` indentée ; le roster les refuse.
  BORNE : en TOML, une clé `cadre.managed = …` (pointée) n'est PAS refusée
  ici ; `managed.poser` la refuse au rendu, `managed.lire` l'accepte.

Ce qui est REFUSÉ, toujours par `RosterIllisible`, qui nomme le fichier (ou le
répertoire) et la cause : répertoire absent, roster VIDE (jamais un cardinal
0), SOUS-RÉPERTOIRE (le roster est à plat : une def qu'on y rangerait serait
perdue sans un mot), fichier qui n'est pas un `.json`, octets non UTF-8, JSON
cassé ou trop imbriqué, clé répétée dans un même objet, et toute forme hors du
FORMAT 1.

Ce qui est IGNORÉ (`IGNORE_SI_PREFIXE`) : une entrée, fichier ou répertoire,
dont le NOM ouvre sur `.`, `.json` compris. C'est un artefact d'OS invisible à
git (`.DS_Store`, `._<nom>` AppleDouble), qui ne doit pas rendre illisible un
roster valide. BORNE : le point initial, et lui seul ; `desktop.ini` et
`Thumbs.db` (Windows) restent REFUSÉS, comme tout fichier qui n'est pas un
`.json`. Un roster d'entrées ignorées seules est VIDE.

LE SENS DE VÉRITÉ : la source `agents/<nom>.md` fait foi et le roster en est
rendu, avec les défs d'hôte, par `render_hosts.py --ecrire` ; le REMEDE du banc
donne cette commande (S-01M5C01EAKQACKA27PNH804CR3).

`charger()` n'a AUCUN paramètre et lit `pkg_root()/data/roster/` et rien
d'autre, sur le modèle de `socle.charger()`. `cardinal()` est le nombre de defs
CHARGÉES : aucun littéral ne l'écrit. Les sous-répertoires, que
`Workspace.iter_files` ne rend pas, sont vus par `Workspace.walk` (un lien vers
un répertoire compris). BORNE : `iter_files` saute sans le dire un lien qui sort
du paquet et un lien pendant (mesuré) ; dans le kit, le témoin T1 du banc (noms
du roster = noms de chaque répertoire de defs) rattrape la def qui manquerait.

Imports : `config` (la liste fermée des hôtes), `managed` (les clés du
marqueur), `paths` et `workspace`. Aucun n'ouvre de fichier à l'import.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from cadre.config import HOTES, HoteInconnu
from cadre.managed import CLES
from cadre.paths import pkg_root
from cadre.workspace import HorsRacine, Workspace

__all__ = ["REFERENCE", "REPERTOIRE", "Definition", "Rendu", "Roster", "RosterIllisible",
           "cardinal", "charger", "corps_de"]

#: Relatif à `pkg_root()`. Écrit UNE fois ici.
REPERTOIRE = "data/roster"
SUFFIXE = ".json"
#: Une entrée du roster dont le nom ouvre ainsi est IGNORÉE (artefact d'OS,
#: S-00004573 C1). BORNE : `desktop.ini` et `Thumbs.db` restent refusés.
IGNORE_SI_PREFIXE = "."
#: L'hôte dont les autres reprennent le corps par `{"comme": "claude"}`.
REFERENCE = "claude"
#: Les hôtes dont l'entête est du TOML ; les autres portent un frontmatter YAML.
_IDENTITE_TOML = frozenset({"codex"})

_CLES_RACINE = frozenset({"version_format", "nom", "rendus"})
_CLES_RENDU = frozenset({"entete", "corps"})
_CLES_RENVOI = frozenset({"comme"})
_NOM = re.compile(r"[a-z][a-z0-9-]*")
#: Une ligne de commentaire qui OUVRE sur `cadre.…` : `# ` (frontmatter, TOML)
#: ou `<!-- ` (en-tête HTML). Toujours refusée ; `managed.CLES` choisit le message.
_COMMENTAIRE_CADRE = re.compile(r"[ \t]*(?:#|<!--)[ \t]*(cadre\.[\w.-]*)", re.ASCII)
#: Une clé de frontmatter `cadre.…` NUE ou quotée, suivie de `:` — la forme d'avant
#: (S-00002846), que `managed.lire` refuse en colonne 0. Jugée hors TOML seulement.
_CLE_CADRE_NUE = re.compile(r"""[ \t]*["']?cadre\.[\w.-]*["']?[ \t]*:""", re.ASCII)


class RosterIllisible(ValueError):
    """Le roster n'a pas pu être lu ; le message nomme le fichier et la cause."""


@dataclass(frozen=True)
class Rendu:
    """Un rendu d'hôte. `corps` vaut `None` quand `comme` renvoie à la référence."""

    entete: tuple[str, ...]
    corps: tuple[str, ...] | None
    comme: str | None = None


@dataclass(frozen=True)
class Definition:
    nom: str
    #: Dans l'ordre de `HOTES`, en lecture seule.
    rendus: Mapping[str, Rendu]


@dataclass(frozen=True)
class Roster:
    #: Triées par nom (l'ordre de `iter_files`).
    definitions: tuple[Definition, ...]

    @property
    def cardinal(self) -> int:
        return len(self.definitions)

    def noms(self) -> tuple[str, ...]:
        return tuple(d.nom for d in self.definitions)

    def definition(self, nom: str) -> Definition:
        for d in self.definitions:
            if d.nom == nom:
                return d
        raise KeyError(f"aucune def {nom!r} au roster")


def _refus(source: str, cause: str) -> RosterIllisible:
    return RosterIllisible(f"{source} : {cause}")


def _lignes(valeur: object, source: str, ou: str) -> tuple[str, ...]:
    if not isinstance(valeur, list):
        raise _refus(source, f"{ou} doit etre une liste de lignes (vu {type(valeur).__name__})")
    for rang, ligne in enumerate(valeur):
        if not isinstance(ligne, str):
            raise _refus(source, f"{ou}[{rang}] doit etre une chaine (vu {type(ligne).__name__})")
        if "\n" in ligne or "\r" in ligne:
            raise _refus(source, f"{ou}[{rang}] contient un saut de ligne : une ligne n'en porte aucun")
    return tuple(valeur)


def _rendu(brut: object, hote: str, nom: str, source: str) -> Rendu:
    ou = f"rendus.{hote}"
    if not isinstance(brut, dict) or set(brut) != _CLES_RENDU:
        vu = sorted(brut) if isinstance(brut, dict) else type(brut).__name__
        raise _refus(source, f"{ou} doit porter exactement {sorted(_CLES_RENDU)} (vu {vu})")
    entete = _lignes(brut["entete"], source, f"{ou}.entete")
    if not entete:
        raise _refus(source, f"{ou}.entete est vide")
    identite = f'name = "{nom}"' if hote in _IDENTITE_TOML else f"name: {nom}"
    if identite not in entete:
        raise _refus(source, f"{ou}.entete ne porte pas sa ligne d'identite {identite!r}")
    for rang, ligne in enumerate(entete):
        if hote not in _IDENTITE_TOML and _CLE_CADRE_NUE.match(ligne):
            raise _refus(source, f"{ou}.entete[{rang}] porte une cle cadre.* NUE (forme d'avant, "
                                 "S-00002846) : refusee a toute indentation, managed.lire la "
                                 "refuse en colonne 0")
        trouve = _COMMENTAIRE_CADRE.match(ligne)
        if trouve is None:
            continue
        cle = trouve.group(1)
        if cle in CLES:
            raise _refus(source, f"{ou}.entete[{rang}] porte le marqueur {cle!r} : "
                                 "il se pose au rendu (T-00000752), jamais dans la source")
        raise _refus(source, f"{ou}.entete[{rang}] ouvre sur {cle!r}, hors de managed.CLES "
                             f"{sorted(CLES)} : aucune ligne cadre. ne se stocke (plus strict "
                             "que managed.lire, qui ne juge que sa region)")
    corps = brut["corps"]
    if isinstance(corps, dict):
        if set(corps) != _CLES_RENVOI:
            raise _refus(source, f"{ou}.corps : un renvoi porte exactement {sorted(_CLES_RENVOI)} "
                                 f"(vu {sorted(corps)})")
        if hote == REFERENCE:
            raise _refus(source, f"{ou}.corps : la reference {REFERENCE!r} ne renvoie a aucun hote")
        if corps["comme"] != REFERENCE:
            raise _refus(source, f"{ou}.corps : `comme` ne vise que {REFERENCE!r} "
                                 f"(vu {corps['comme']!r})")
        return Rendu(entete, None, REFERENCE)
    return Rendu(entete, _lignes(corps, source, f"{ou}.corps"))


def _valider(brut: object, source: str, attendu: str) -> Definition:
    """Le FORMAT 1 (voir le module). `attendu` est le nom du fichier sans suffixe."""
    if not isinstance(brut, dict):
        raise _refus(source, f"la racine doit etre un objet (vu {type(brut).__name__})")
    if set(brut) != _CLES_RACINE:
        raise _refus(source, f"cles racine {sorted(brut)} : attendu exactement {sorted(_CLES_RACINE)}")
    # L'ENTIER 1, et lui seul : `True == 1` et `1.0 == 1` sont vrais en Python, d'où `type(...) is int`.
    version = brut["version_format"]
    if type(version) is not int or version != 1:
        raise _refus(source, f"version_format {version!r} : seul l'entier 1 est connu")
    nom = brut["nom"]
    # `fullmatch`, pas `match` : avec `match`, le `$` admet un saut de ligne final.
    if not isinstance(nom, str) or not _NOM.fullmatch(nom):
        raise _refus(source, f"nom {nom!r} : identifiant ASCII minuscule attendu")
    if nom != attendu:
        raise _refus(source, f"nom {nom!r} different du nom de fichier {attendu!r}")
    rendus = brut["rendus"]
    if not isinstance(rendus, dict):
        raise _refus(source, f"`rendus` doit etre un objet (vu {type(rendus).__name__})")
    inconnus = sorted(set(rendus) - set(HOTES))
    if inconnus:
        raise _refus(source, f"hote(s) inconnu(s) {inconnus} : liste fermee {list(HOTES)}")
    if REFERENCE not in rendus:
        raise _refus(source, f"le rendu de reference {REFERENCE!r} est absent")
    lus = {hote: _rendu(rendus[hote], hote, nom, source) for hote in HOTES if hote in rendus}
    return Definition(nom, MappingProxyType(lus))


def _sans_doublon(source: str):
    """`object_pairs_hook` : une cle repetee dans un meme objet LEVE (`json` garde la derniere en silence)."""
    def crochet(paires: list[tuple[str, object]]) -> dict:
        vues: set[str] = set()
        for cle, _ in paires:
            if cle in vues:
                raise _refus(source, f"cle JSON en double {cle!r}")
            vues.add(cle)
        return dict(paires)
    return crochet


def _lire(atelier: Workspace) -> Roster:
    """Lit `REPERTOIRE` sous `atelier`. `atelier` EST ANNOTÉ : c'est la forme que
    `check_orchestration_purity` sanctionne pour une E/S."""
    repertoire = str(atelier.racine / REPERTOIRE)
    try:
        present = atelier.est_repertoire(REPERTOIRE)
    except OSError as exc:
        raise _refus(repertoire, f"illisible — {exc}") from exc
    if not present:
        raise _refus(repertoire, "repertoire absent : aucun roster n'est livre avec ce paquet")
    try:
        _rel, sous_repertoires, _noms = next(atelier.walk(REPERTOIRE))
    except (OSError, HorsRacine) as exc:
        raise _refus(repertoire, f"illisible — {exc}") from exc
    for nom in sorted(sous_repertoires):
        if not nom.startswith(IGNORE_SI_PREFIXE):
            raise _refus(str(atelier.racine / REPERTOIRE / nom),
                         "sous-repertoire refuse : le roster est a plat, une def par `<nom>.json`")
    fichiers = [chemin for chemin in atelier.iter_files(f"{REPERTOIRE}/*")
                if not chemin.name.startswith(IGNORE_SI_PREFIXE)]
    if not fichiers:
        raise _refus(repertoire, "roster vide : aucune def, jamais un cardinal nul")
    definitions = []
    for chemin in fichiers:
        relatif = f"{REPERTOIRE}/{chemin.name}"
        source = str(atelier.racine / relatif)
        if chemin.suffix != SUFFIXE:
            raise _refus(source, f"fichier hors format : seul un `{SUFFIXE}` vit dans le roster")
        try:
            brut = atelier.read_text(relatif)
        except (OSError, UnicodeDecodeError, HorsRacine) as exc:
            raise _refus(source, f"illisible — {exc}") from exc
        try:
            charge = json.loads(brut, object_pairs_hook=_sans_doublon(source))
        except (json.JSONDecodeError, RecursionError) as exc:
            raise _refus(source, f"JSON invalide — {exc}") from exc
        definitions.append(_valider(charge, source, chemin.stem))
    return Roster(tuple(definitions))


def charger() -> Roster:
    """Le roster embarqué. Aucun paramètre, aucun cache : voir le module."""
    return _lire(Workspace(pkg_root()))


def cardinal() -> int:
    """Le nombre de defs du roster embarqué, DÉRIVÉ de la donnée chargée."""
    return charger().cardinal


def corps_de(definition: Definition, hote: str) -> tuple[str, ...]:
    """Les lignes du corps de `definition` pour `hote`, renvoi `comme` RÉSOLU.

    `HoteInconnu` pour un hôte hors de `HOTES` ; `KeyError` pour un hôte que
    cette def ne rend pas."""
    if hote not in HOTES:
        raise HoteInconnu(f"hote {hote!r} hors de la liste fermee {list(HOTES)}")
    try:
        rendu = definition.rendus[hote]
    except KeyError:
        raise KeyError(f"{definition.nom} : aucun rendu pour l'hote {hote!r}") from None
    corps = rendu.corps if rendu.comme is None else definition.rendus[rendu.comme].corps
    if corps is None:  # impossible apres `_valider` ; une Definition montee a la main peut l'etre
        raise RosterIllisible(f"{definition.nom} : le corps de {hote} ne se resout pas")
    return corps
