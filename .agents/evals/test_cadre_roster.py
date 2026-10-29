#!/usr/bin/env python3
"""Banc du roster canonique (T-00000973, BK-139) : `<paquet cadre>/data/roster/*.json` lu par `cadre.roster`.

Le paquet est celui que `vendor_paths` désigne (`.agents/vendor/cadre`, sinon `src/cadre`).

DEUX CLASSES DE TÉMOINS.

* La FORME (T4, T4bis, T5, T6, T7, T9, et l'aller-retour synthétique de T3) : sur des rosters
  synthétiques montés sous `tmp_path`, ou sur les octets de la donnée. Elle tourne partout.
* L'ÉQUIVALENCE (T1, T1b, T2, T3, T8, T10) : le roster contre les defs VIVANTES des cinq
  hôtes. Elle ne juge que le KIT (marqueur `.agents/IS_THE_KIT`) : chez un adoptant elle
  jugerait SES defs, qu'il a le droit de modifier. Hors du kit elle saute en l'annonçant.

LE SENS DE VÉRITÉ : la source `agents/<nom>.md` fait foi (décision pilote
S-01M5C01EAKQACKA27PNH804CR3) ; les defs des cinq hôtes ET le roster en sont RENDUS par
`bash .agents/pyrun.sh .agents/bin/render_hosts.py --ecrire`, dans le même commit — T1 et T2
le disent en rougissant, `render_hosts.py --check` nomme la dérive. `--regenerer` (plus bas)
reste une SECONDE voie d'écriture du roster, depuis les defs d'hôte : il n'est plus le remède.

LE DÉCOUPAGE, par la forme du fichier (`managed.forme_de`), APRÈS dépouillement du marqueur
`cadre.managed` (`source`, constat C1 : T-00000984 marquera les defs vivantes, et le roster ne
stocke jamais de marqueur) :
  Markdown : `---` / entête / `---` / corps, lignes jointes par `\\n` ;
  TOML     : entête / `developer_instructions = \"\"\"` / corps, puis `\"\"\"\\n` final.
Un corps identique à celui de `claude` est stocké `{"comme": "claude"}` (S-00003176).

LA TABLE hôte -> (répertoire, motif) est LUE dans `core-scripts/apply-mode.py`
(`LEVER_HOSTS`, `INDICATIVE_HOSTS`), jamais recopiée (constat C6). Seul ajout : `ALIAS`,
parce que `config.HOTES` dit `copilot` là où apply-mode dit `github` ; T1b tient l'égalité.

BORNE NOMMÉE : le même banc régénère et juge, avec le même découpage. T3 tranche — il
vérifie l'aller-retour sans perte sur les defs vivantes sans passer par le roster — et T10
vérifie qu'une def marquée donne le JSON de sa jumelle nue.

`--regenerer` n'existe que sous `__main__` (précédent : `--initialiser` de
`test_python_file_length.py`). Il refuse avant toute écriture tant qu'apply-mode est actif et
devant un lien symbolique ; ses témoins posent un kit synthétique sous `tmp_path`. Aucun
cardinal n'est écrit dans ce fichier : il se dérive.
"""
from __future__ import annotations

import functools
import importlib.util
import inspect
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
# Le paquet `cadre` OÙ QU'IL VIVE (`.agents/vendor/cadre`, sinon `src/cadre`) : chargé par
# chemin par `vendor_paths` (T-01M5BXTPQE3JZV3KZA6WD9P5XC lot K), jamais par `sys.path`.
_SPEC_VENDOR = importlib.util.spec_from_file_location(
    "_cadre_roster_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
assert _SPEC_VENDOR is not None and _SPEC_VENDOR.loader is not None
_VENDOR = importlib.util.module_from_spec(_SPEC_VENDOR)
sys.modules[_SPEC_VENDOR.name] = _VENDOR
_SPEC_VENDOR.loader.exec_module(_VENDOR)
_VENDOR.charger_paquet(ROOT, "cadre")
PAQUET = _VENDOR.exiger(ROOT, "cadre")

# La classe d'ÉQUIVALENCE ne juge que le KIT ; la classe de FORME tourne partout.
# adopting-tree: le marqueur d'identite du kit ne voyage pas (strip: .agents/IS_THE_KIT) ;
# son absence EST le signal « projet adoptant » : l'equivalence y saute en l'annoncant.
EST_LE_KIT = (ROOT / ".agents" / "IS_THE_KIT").is_file()
DANS_LE_KIT = pytest.mark.skipif(
    not EST_LE_KIT,
    reason="SAUT ANNONCE : marqueur `.agents/IS_THE_KIT` absent (projet adoptant) — "
           "l'equivalence roster/defs vivantes n'est pas jugee ici",
)

from cadre import managed, roster  # noqa: E402
from cadre.config import HOTES, HoteInconnu  # noqa: E402
from cadre.workspace import Workspace  # noqa: E402

DONNEES = PAQUET / roster.REPERTOIRE
REGENERER = "python3 .agents/evals/test_cadre_roster.py --regenerer"
#: Le fichier de mode d'apply-mode, relatif à la racine : présent, les defs portent les tiers
#: `expert`. Écrit ici pour REMEDE, que la classe de FORME lit sans charger apply-mode ;
#: `test_REMEDE_nomme_le_fichier_de_mode_d_apply_mode_et_le_write_set` le tient égal à `MODE_FILE`.
MODE_RELATIF = ".agents/state/local/MODEL_MODE"
RESTAURER = "python3 core-scripts/apply-mode.py restore"
REMEDE = ("la source agents/<nom>.md fait foi : `bash .agents/pyrun.sh .agents/bin/render_hosts.py "
          "--ecrire` rend les hotes ET le roster, DANS LE MEME COMMIT que la modification de la source, et ajoute "
          f"{DONNEES.relative_to(ROOT).as_posix()}/<nom>.json au write-set de ta tache (tasks.py writeset) ; "
          f"si {MODE_RELATIF} existe, `{RESTAURER}` d'abord")
#: `config.HOTES` -> nom d'hôte d'apply-mode, là où ils diffèrent.
ALIAS = {"copilot": "github"}
OUVERTURE_TOML = 'developer_instructions = """'
FERMETURE_TOML = '"""\n'
CLES_ORDONNEES = ("version_format", "nom", "rendus")


# --- la table des hôtes, LUE dans apply-mode.py ---------------------------------------------------
@functools.cache
def _apply_mode():
    spec = importlib.util.spec_from_file_location("cadre_roster_apply_mode",
                                                  ROOT / "core-scripts" / "apply-mode.py")
    module = importlib.util.module_from_spec(spec)
    # Enregistré AVANT d'exécuter (T-00000134, `test_modload_registration.py`) ;
    # gardé, comme le module que `functools.cache` garde, sous un nom propre au banc.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def table_apply_mode() -> dict[str, tuple[str, str]]:
    """Hôte d'apply-mode -> (répertoire, motif de nom de fichier)."""
    mode = _apply_mode()
    table = {hote: (rep, motif) for hote, (rep, motif, _axes) in mode.LEVER_HOSTS.items()}
    table.update(mode.INDICATIVE_HOSTS)
    return table


def emplacements() -> dict[str, tuple[str, str]]:
    """Hôte de `HOTES` -> (répertoire, motif), dans l'ordre de `HOTES`."""
    table = table_apply_mode()
    return {hote: table[ALIAS.get(hote, hote)] for hote in HOTES}


def fichier_de(hote: str, nom: str) -> str:
    rep, motif = emplacements()[hote]
    return f"{rep}/{motif.format(agent=nom)}"


def noms_vivants(racine: Path, hote: str) -> list[str]:
    rep, motif = emplacements()[hote]
    prefixe, suffixe = motif.split("{agent}")
    return sorted(p.name[len(prefixe):len(p.name) - len(suffixe)]
                  for p in (racine / rep).glob(f"{prefixe}*{suffixe}"))


# --- le découpage --------------------------------------------------------------------------------
def source(texte: str, fichier: str) -> str:
    """Le texte d'une def tel que le roster le stocke : DÉPOUILLÉ de son marqueur (C1)."""
    return managed.depouiller(texte, managed.forme_de(fichier))


def lire_def(racine: Path, hote: str, nom: str) -> str:
    fichier = fichier_de(hote, nom)
    return source((racine / fichier).read_bytes().decode("utf-8"), fichier)


def decouper(texte: str, fichier: str) -> tuple[list[str], list[str]]:
    """(entête, corps) en lignes ; `ValueError` si la forme attendue manque."""
    lignes = texte.split("\n")
    if managed.forme_de(fichier) is managed.Forme.TOML:
        if OUVERTURE_TOML not in lignes:
            raise ValueError(f"{fichier} : aucune ligne {OUVERTURE_TOML!r}")
        i = lignes.index(OUVERTURE_TOML)
        reste = "\n".join(lignes[i + 1:])
        if not reste.endswith(FERMETURE_TOML):
            raise ValueError(f"{fichier} : ne finit pas par {FERMETURE_TOML!r}")
        return lignes[:i], reste[:-len(FERMETURE_TOML)].split("\n")
    if lignes[0] != "---" or "---" not in lignes[1:]:
        raise ValueError(f"{fichier} : frontmatter `---` absent ou non referme")
    fin = lignes.index("---", 1)
    return lignes[1:fin], lignes[fin + 1:]


def recomposer(entete: list[str], corps: list[str], fichier: str) -> str:
    if managed.forme_de(fichier) is managed.Forme.TOML:
        return "\n".join([*entete, OUVERTURE_TOML]) + "\n" + "\n".join(corps) + FERMETURE_TOML
    return "\n".join(["---", *entete, "---", *corps])


def construire(nom: str, textes: dict[str, str]) -> dict:
    """L'objet FORMAT 1 de `nom` depuis ses textes DÉPOUILLÉS par hôte, dans l'ordre de `HOTES`."""
    decoupes = {hote: decouper(textes[hote], fichier_de(hote, nom)) for hote in HOTES if hote in textes}
    corps_reference = decoupes[roster.REFERENCE][1]
    rendus = {}
    for hote, (entete, corps) in decoupes.items():
        renvoi = hote != roster.REFERENCE and corps == corps_reference
        rendus[hote] = {"entete": entete, "corps": {"comme": roster.REFERENCE} if renvoi else corps}
    return {"version_format": 1, "nom": nom, "rendus": rendus}


def serialiser(objet: dict) -> str:
    return json.dumps(objet, indent=2, ensure_ascii=False) + "\n"


def ecarts(charge: roster.Roster, racine: Path, lecteur=lire_def) -> list[str]:
    """Chaque rendu RÉSOLU du roster contre le découpage de la def vivante, TOUS les écarts."""
    fautes = []
    for nom in noms_vivants(racine, roster.REFERENCE):
        try:
            definition = charge.definition(nom)
        except KeyError:
            fautes.append(f"{nom} : absente du roster")
            continue
        for hote in HOTES:
            fichier = fichier_de(hote, nom)
            if hote not in definition.rendus:
                fautes.append(f"{nom}/{hote} : aucun rendu au roster pour {fichier}")
                continue
            entete, corps = decouper(lecteur(racine, hote, nom), fichier)
            if list(definition.rendus[hote].entete) != entete:
                fautes.append(f"{nom}/{hote} : l'entete differe de {fichier}")
            if list(roster.corps_de(definition, hote)) != corps:
                fautes.append(f"{nom}/{hote} : le corps differe de {fichier}")
    return fautes


# --- la régénération (sous __main__ seulement) ---------------------------------------------------
def regenerer(racine: Path = ROOT, donnees: Path = DONNEES) -> list[str]:
    """Réécrit le roster depuis les defs vivantes. Tout est construit et VALIDÉ avant la
    première écriture : un refus laisse la donnée intacte. Rend les gestes faits.

    REFUSE (`SystemExit`), avant toute écriture : apply-mode actif sous `racine` (son fichier
    de mode présent : les defs portent les tiers `expert`, que le roster figerait) ; un lien
    symbolique sur le chemin du roster sous `racine` ou sur une cible (`write_bytes` le
    suivrait hors du dépôt). Ne retire jamais une entrée que le module IGNORE (point initial)."""
    mode = _apply_mode()
    if (racine / mode.MODE_FILE.relative_to(mode.ROOT)).exists():
        raise SystemExit(f"apply-mode actif ({MODE_RELATIF} present) : les defs portent les tiers "
                         f"`expert` ; `{RESTAURER}` avant de regenerer")
    noms = noms_vivants(racine, roster.REFERENCE)
    for hote in HOTES:
        if noms_vivants(racine, hote) != noms:
            raise SystemExit(f"{hote} : ses defs ne portent pas les memes noms que celles de "
                             f"{roster.REFERENCE} — aligne les repertoires avant de regenerer")
    textes = {}
    for nom in noms:
        cible = donnees / f"{nom}{roster.SUFFIXE}"
        objet = construire(nom, {hote: lire_def(racine, hote, nom) for hote in HOTES})
        roster._valider(objet, str(cible), nom)
        textes[cible] = serialiser(objet).encode("utf-8")
    # `resolve` dit un lien sur le roster OU sur l'un de ses parents sous `racine`.
    if (donnees.resolve() != racine.resolve() / donnees.relative_to(racine)
            or any(cible.is_symlink() for cible in textes)):
        raise SystemExit(f"lien symbolique refuse dans le roster ({donnees}) : une ecriture "
                         "le suivrait hors du depot")
    gestes = []
    donnees.mkdir(parents=True, exist_ok=True)
    for cible, octets in textes.items():
        if not cible.is_file() or cible.read_bytes() != octets:
            cible.write_bytes(octets)
            gestes.append(f"ecrit   {cible.relative_to(racine).as_posix()}")
    for orphelin in sorted(donnees.glob(f"*{roster.SUFFIXE}")):
        if orphelin not in textes and not orphelin.name.startswith(roster.IGNORE_SI_PREFIXE):
            orphelin.unlink()
            gestes.append(f"retire  {orphelin.relative_to(racine).as_posix()}")
    return gestes


def main(argv: list[str]) -> int:
    if argv != ["--regenerer"]:
        print(f"usage : {REGENERER}", file=sys.stderr)
        return 2
    gestes = regenerer()
    for geste in gestes:
        print(geste)
    print("roster a jour" if gestes else "roster deja a jour : aucun fichier touche")
    return 0


# --- synthèse de rosters (classe de FORME) --------------------------------------------------------
def _valide(nom: str = "alpha") -> dict:
    return {"version_format": 1, "nom": nom, "rendus": {
        "claude": {"entete": [f"name: {nom}", "description: a"], "corps": ["corps", ""]},
        "codex": {"entete": [f'name = "{nom}"', 'model = "m"'], "corps": ["autre", ""]},
        "gemini": {"entete": [f"name: {nom}", "# un commentaire YAML"], "corps": {"comme": "claude"}},
    }}


def _poser(racine: Path, fichiers: dict[str, object]) -> Workspace:
    """Écrit `fichiers` (nom -> objet JSON, `str` ou `bytes` bruts) sous `racine/data/roster/`.
    Un nom `rep/fichier` crée le sous-répertoire `rep`."""
    rep = racine / roster.REPERTOIRE
    rep.mkdir(parents=True, exist_ok=True)
    for nom, contenu in fichiers.items():
        if isinstance(contenu, bytes):
            octets = contenu
        elif isinstance(contenu, str):
            octets = contenu.encode("utf-8")
        else:
            octets = serialiser(contenu).encode("utf-8")
        (rep / nom).parent.mkdir(parents=True, exist_ok=True)
        (rep / nom).write_bytes(octets)
    return Workspace(racine)


def _mute(**gestes):
    """Un objet valide, puis `gestes` : chemin pointé -> valeur (`...` = clé retirée)."""
    objet = _valide()
    for chemin, valeur in gestes.items():
        *parents, feuille = chemin.split("__")
        noeud = objet
        for cle in parents:
            noeud = noeud[cle]
        if valeur is ...:
            del noeud[feuille]
        else:
            noeud[feuille] = valeur
    return objet


# --- T4 / T6 : les formes refusées ----------------------------------------------------------------
REFUS = [
    ("json-casse", {"alpha.json": "{"}, "JSON invalide"),
    ("cle-double", {"alpha.json": '{"version_format": 1, "version_format": 1, "nom": "alpha", '
                                  '"rendus": {}}'}, "cle JSON en double"),
    ("trop-profond", {"alpha.json": "[" * 200_000}, "JSON invalide"),
    ("non-utf8", {"alpha.json": b"\xff\xfe{}"}, "illisible"),
    ("racine-liste", {"alpha.json": "[]"}, "la racine doit etre un objet"),
    ("version-booleen", {"alpha.json": _mute(version_format=True)}, "version_format"),
    ("version-flottant", {"alpha.json": _mute(version_format=1.0)}, "version_format"),
    ("cle-racine-inconnue", {"alpha.json": _mute(**{"$comment": "x"})}, "cles racine"),
    ("cle-racine-manquante", {"alpha.json": _mute(rendus=...)}, "cles racine"),
    ("nom-invalide", {"Alpha.json": _mute(nom="Alpha")}, "identifiant ASCII"),
    ("nom-different", {"alpha.json": _mute(nom="beta")}, "different du nom de fichier"),
    ("rendus-non-objet", {"alpha.json": _mute(rendus=[])}, "`rendus` doit etre un objet"),
    ("hote-inconnu", {"alpha.json": _mute(rendus__vscode={"entete": ["name: alpha"], "corps": []})},
     "inconnu"),
    ("claude-absent", {"alpha.json": _mute(rendus__claude=...)}, "reference 'claude' est absent"),
    ("rendu-cle-inconnue", {"alpha.json": _mute(rendus__claude__x=1)}, "doit porter exactement"),
    ("entete-vide", {"alpha.json": _mute(rendus__claude__entete=[])}, "entete est vide"),
    ("corps-chaine", {"alpha.json": _mute(rendus__codex__corps="autre")}, "liste de lignes"),
    ("ligne-non-chaine", {"alpha.json": _mute(rendus__claude__corps=[42])}, "doit etre une chaine"),
    ("saut-de-ligne-n", {"alpha.json": _mute(rendus__claude__corps=["a\nb"])}, "saut de ligne"),
    ("saut-de-ligne-r", {"alpha.json": _mute(rendus__codex__entete=['name = "alpha"', "x\r"])},
     "saut de ligne"),
    ("identite-yaml-absente", {"alpha.json": _mute(rendus__claude__entete=["description: a"])},
     "ligne d'identite"),
    ("identite-toml-absente", {"alpha.json": _mute(rendus__codex__entete=["name: alpha"])},
     "ligne d'identite"),
    ("comme-sur-claude", {"alpha.json": _mute(rendus__claude__corps={"comme": "claude"})},
     "ne renvoie a aucun hote"),
    ("comme-vers-autre", {"alpha.json": _mute(rendus__gemini__corps={"comme": "codex"})},
     "ne vise que"),
    ("renvoi-cle-inconnue", {"alpha.json": _mute(rendus__gemini__corps={"comme": "claude", "x": 1})},
     "un renvoi porte exactement"),
    ("cle-cadre-hors-CLES", {"alpha.json": _mute(rendus__claude__entete=["name: alpha",
                                                                         "# cadre.autre: x"])},
     "hors de managed.CLES"),
    # La forme d'avant (S-00002846), que `managed.lire` refuse dans le rendu : clé nue, pas un commentaire.
    ("cle-cadre-nue", {"alpha.json": _mute(rendus__claude__entete=["name: alpha", "cadre.managed: true"])},
     "NUE"),
    # Le fichier FAUTIF est toujours la PREMIÈRE clé ; ici `alpha.json`, valide, est lu avant lui.
    ("fichier-non-json", {"notes.txt": "x", "alpha.json": _valide()}, "fichier hors format"),
    # BORNE écrite au module : seul le point initial est ignoré ; les artefacts Windows restent refusés.
    ("borne-desktop-ini", {"desktop.ini": "[.ShellClassInfo]\r\n", "alpha.json": _valide()},
     "fichier hors format"),
    ("borne-thumbs-db", {"Thumbs.db": b"\xd0\xcf\x11\xe0", "alpha.json": _valide()}, "fichier hors format"),
    # Le FAUTIF est ici le répertoire, premier segment de la clé ; une def y serait perdue en silence.
    ("sous-repertoire", {"imbrique/beta.json": _valide("beta"), "alpha.json": _valide()},
     "sous-repertoire"),
]


@pytest.mark.parametrize("fichiers,cause", [(f, c) for _, f, c in REFUS], ids=[i for i, _, _ in REFUS])
def test_T4_chaque_forme_refusee_leve_en_nommant_le_fichier(tmp_path, fichiers, cause):
    fautif = next(iter(fichiers)).split("/")[0]
    with pytest.raises(roster.RosterIllisible) as refus:
        roster._lire(_poser(tmp_path, fichiers))
    assert fautif in str(refus.value), f"le refus ne nomme pas {fautif} : {refus.value}"
    assert cause in str(refus.value), f"refus pour une autre cause que « {cause} » : {refus.value}"


def test_T4_la_forme_valide_est_lue_et_le_renvoi_se_resout(tmp_path):
    lu = roster._lire(_poser(tmp_path, {"alpha.json": _valide()}))
    definition = lu.definition("alpha")
    assert tuple(definition.rendus) == ("claude", "codex", "gemini")
    assert roster.corps_de(definition, "gemini") == ("corps", "")
    assert roster.corps_de(definition, "codex") == ("autre", "")
    with pytest.raises(KeyError):
        roster.corps_de(definition, "kimi")
    with pytest.raises(HoteInconnu):
        roster.corps_de(definition, "vscode")


@pytest.mark.parametrize("artefact", [".DS_Store", "._alpha.json", ".cache/x"],
                         ids=["ds-store", "appledouble", "repertoire-point"])
def test_T4bis_une_entree_qui_ouvre_sur_un_point_est_ignoree(tmp_path, artefact):
    """Un artefact d'OS, invisible à git, ne rend pas illisible un roster valide (S-00004573 C1)."""
    atelier = _poser(tmp_path, {artefact: b"\x00\x00\x00\x01Bud1", "alpha.json": _valide()})
    assert roster._lire(atelier).noms() == ("alpha",)


MARQUEURS = [
    ("frontmatter", "claude", "# cadre.managed: true"),
    ("toml", "codex", '# cadre.checksum: "sha256:' + "0" * 64 + '"'),
    ("html", "claude", '<!-- cadre.version: "1.0.0" -->'),
]


@pytest.mark.parametrize("hote,ligne", [(h, l) for _, h, l in MARQUEURS], ids=[i for i, _, _ in MARQUEURS])
def test_T6_un_marqueur_cadre_dans_une_entete_est_refuse(tmp_path, hote, ligne):
    objet = _valide()
    objet["rendus"][hote]["entete"].append(ligne)
    with pytest.raises(roster.RosterIllisible, match="marqueur"):
        roster._lire(_poser(tmp_path, {"alpha.json": objet}))


#: (hôte, en tête de l'entête ?, ligne, cause du refus du roster, `managed.lire` refuse-t-il le
#: RENDU ?). Le rendu est celui que le banc recompose : la ligne DANS le frontmatter, ou dans
#: l'entête TOML. Mesuré à T-00000973 (S-00004580 F3) : le roster refuse chacune ; `lire` ne juge
#: que sa RÉGION — colonne 0 du frontmatter, suite de tête du TOML.
LIGNES_CADRE = [
    ("frontmatter", "claude", False, "# cadre.autre: x", "hors de managed.CLES", True),
    ("mention", "claude", False, "# cadre.json est vide", "hors de managed.CLES", True),
    ("toml-en-tete", "codex", True, '# cadre.origine: "kit"', "hors de managed.CLES", True),
    ("nue", "claude", False, "cadre.managed: true", "NUE", True),
    # Hors de la région de `lire` : il accepte, le roster refuse — PLUS STRICT.
    ("indentee", "claude", False, "  # cadre.autre: x", "hors de managed.CLES", False),
    ("marqueur-indente", "claude", False, "  # cadre.managed: true", "marqueur", False),
    ("collee", "claude", False, "#cadre.autre: x", "hors de managed.CLES", False),
    ("html-dans-frontmatter", "claude", False, "<!-- cadre.autre: x -->", "hors de managed.CLES", False),
    ("toml-sous-la-tete", "codex", False, '# cadre.origine: "kit"', "hors de managed.CLES", False),
    ("nue-indentee", "claude", False, "  cadre.managed: true", "NUE", False),
    ("nue-quotee", "claude", False, '"cadre.managed": true', "NUE", False),
]


def _fichier_synthetique(hote: str) -> str:
    return "a/alpha.toml" if hote == "codex" else "a/alpha.md"


@pytest.mark.parametrize("hote,en_tete,ligne,cause,lire_refuse",
                         [cas[1:] for cas in LIGNES_CADRE], ids=[cas[0] for cas in LIGNES_CADRE])
def test_T6_une_ligne_cadre_d_entete_est_refusee_plus_strictement_que_par_managed_lire(
        tmp_path, hote, en_tete, ligne, cause, lire_refuse):
    """Constats S-00004573 C3 et S-00004580 F3 : le roster refuse toute ligne `cadre.` de
    l'entête, à toute place. Le second volet MESURE `managed.lire` sur le rendu recomposé : si
    `lire` change de région, la docstring du module ment, et ce témoin rougit."""
    objet = _valide()
    entete = objet["rendus"][hote]["entete"]
    entete.insert(0 if en_tete else len(entete), ligne)
    with pytest.raises(roster.RosterIllisible, match=cause):
        roster._lire(_poser(tmp_path, {"alpha.json": objet}))
    fichier = _fichier_synthetique(hote)
    rendu = recomposer(entete, objet["rendus"][hote]["corps"], fichier)
    if lire_refuse:
        with pytest.raises(managed.MarqueurIllisible):
            managed.lire(rendu, managed.forme_de(fichier))
    else:
        assert managed.lire(rendu, managed.forme_de(fichier)) is None, (
            f"managed.lire refuse desormais {ligne!r} : reecris la region decrite par cadre.roster")


def test_T6_BORNE_une_cle_cadre_pointee_en_toml_passe_le_roster_et_poser_la_refuse(tmp_path):
    """La BORNE écrite au module : en TOML, `cadre.managed = …` n'est pas refusée par le roster."""
    objet = _valide()
    objet["rendus"]["codex"]["entete"].append("cadre.managed = true")
    lu = roster._lire(_poser(tmp_path, {"alpha.json": objet})).definition("alpha")
    rendu = recomposer(list(lu.rendus["codex"].entete), ["autre", ""], _fichier_synthetique("codex"))
    assert managed.lire(rendu, managed.Forme.TOML) is None
    with pytest.raises(managed.MarqueurIllisible, match="TOML"):
        managed.poser(rendu, managed.Forme.TOML, version="0.0.0")


def test_T6_un_commentaire_qui_n_ouvre_pas_sur_cadre_passe(tmp_path):
    objet = _valide()
    objet["rendus"]["claude"]["entete"] += ["# un commentaire", "description: voir cadre.json"]
    assert roster._lire(_poser(tmp_path, {"alpha.json": objet})).noms() == ("alpha",)


# --- T7 / T9 : le cardinal et `charger` ----------------------------------------------------------
def test_T7_le_cardinal_suit_le_nombre_de_fichiers(tmp_path):
    atelier = _poser(tmp_path, {"alpha.json": _valide("alpha"), "beta.json": _valide("beta")})
    deux = roster._lire(atelier)
    assert (deux.cardinal, deux.noms()) == (2, ("alpha", "beta"))
    (tmp_path / roster.REPERTOIRE / "beta.json").unlink()
    un = roster._lire(atelier)
    assert (un.cardinal, un.noms()) == (1, ("alpha",))


def test_T9_charger_et_cardinal_n_ont_aucun_parametre():
    assert list(inspect.signature(roster.charger).parameters) == []
    assert list(inspect.signature(roster.cardinal).parameters) == []


def test_T9_un_roster_absent_leve_jamais_un_cardinal_nul(tmp_path):
    with pytest.raises(roster.RosterIllisible, match="repertoire absent"):
        roster._lire(Workspace(tmp_path))


def test_T9_un_roster_vide_leve_jamais_un_cardinal_nul(tmp_path):
    (tmp_path / roster.REPERTOIRE).mkdir(parents=True)
    with pytest.raises(roster.RosterIllisible, match="roster vide"):
        roster._lire(Workspace(tmp_path))


def test_T9_un_roster_d_artefacts_ignores_seuls_leve_jamais_un_cardinal_nul(tmp_path):
    with pytest.raises(roster.RosterIllisible, match="roster vide"):
        roster._lire(_poser(tmp_path, {".DS_Store": b"\x00", ".cache/x": "y"}))


# --- T3 (synthétique) / T5 : la forme des octets ---------------------------------------------------
@pytest.mark.parametrize("fichier,texte", [
    ("a/x.md", "---\nname: x\n---\ncorps\n\n"),
    ("a/x.agent.md", "---\nname: x\n---\n"),
    ("a/x.md", "---\nname: x\n---"),
    ("a/x.toml", 'name = "x"\ndeveloper_instructions = """\ncorps\n\n"""\n'),
])
def test_T3_le_decoupage_synthetique_fait_l_aller_retour(fichier, texte):
    assert recomposer(*decouper(texte, fichier), fichier) == texte


def test_T5_les_octets_sur_disque_sont_la_serialisation_canonique():
    fichiers = sorted(DONNEES.glob(f"*{roster.SUFFIXE}"))
    assert fichiers, f"aucun fichier sous {DONNEES} : le banc passerait sur une population vide"
    fautes = []
    for chemin in fichiers:
        octets = chemin.read_bytes()
        objet = json.loads(octets.decode("utf-8"))
        if serialiser(objet).encode("utf-8") != octets:
            fautes.append(f"{chemin.name} : octets hors de la serialisation canonique")
        if tuple(objet) != CLES_ORDONNEES:
            fautes.append(f"{chemin.name} : cles racine dans l'ordre {list(objet)}")
        elif list(objet["rendus"]) != [h for h in HOTES if h in objet["rendus"]]:
            fautes.append(f"{chemin.name} : rendus hors de l'ordre de HOTES {list(objet['rendus'])}")
    assert fautes == [], f"{REMEDE} :\n" + "\n".join(fautes)


# --- L'ÉQUIVALENCE (kit seulement) ---------------------------------------------------------------
@DANS_LE_KIT
def test_T1b_la_table_des_hotes_est_celle_d_apply_mode():
    assert set(ALIAS) <= set(HOTES), f"ALIAS {ALIAS} nomme un hote hors de HOTES {HOTES}"
    assert {ALIAS.get(h, h) for h in HOTES} == set(table_apply_mode()), (
        f"HOTES {HOTES} (via ALIAS {ALIAS}) != hotes d'apply-mode {sorted(table_apply_mode())}")


@DANS_LE_KIT
def test_T1_les_noms_du_roster_egalent_ceux_de_chaque_repertoire_de_defs():
    noms = set(roster.charger().noms())
    fautes = []
    for hote in HOTES:
        vivants = set(noms_vivants(ROOT, hote))
        if vivants != noms:
            fautes.append(f"{hote} ({emplacements()[hote][0]}) : absentes du roster "
                          f"{sorted(vivants - noms)}, en trop au roster {sorted(noms - vivants)}")
    assert fautes == [], f"{REMEDE} :\n" + "\n".join(fautes)


@DANS_LE_KIT
def test_T2_chaque_rendu_resolu_egale_la_def_vivante_depouillee():
    fautes = ecarts(roster.charger(), ROOT)
    assert fautes == [], f"{REMEDE} :\n" + "\n".join(fautes)


@DANS_LE_KIT
def test_T3_le_decoupage_des_defs_vivantes_fait_l_aller_retour_sans_perte():
    noms = noms_vivants(ROOT, roster.REFERENCE)
    fautes, vus = [], 0
    for nom in noms:
        for hote in HOTES:
            fichier = fichier_de(hote, nom)
            texte = lire_def(ROOT, hote, nom)
            vus += 1
            if recomposer(*decouper(texte, fichier), fichier) != texte:
                fautes.append(fichier)
    assert noms and vus == len(noms) * len(HOTES)
    assert fautes == [], "aller-retour avec perte :\n" + "\n".join(fautes)


@DANS_LE_KIT
def test_T8_le_cardinal_embarque_egale_le_nombre_de_defs_claude():
    assert roster.cardinal() == len(sorted((ROOT / ".claude" / "agents").glob("*.md")))


@DANS_LE_KIT
def test_T10_une_def_marquee_donne_le_meme_json_que_sa_jumelle_nue():
    """Le marqueur posé par `managed.poser` (fin de frontmatter, tête de TOML) est retiré
    AVANT le découpage : même JSON, et T2 reste vert sur les defs marquées."""
    noms = noms_vivants(ROOT, roster.REFERENCE)
    marquees = {}
    for nom in noms:
        for hote in HOTES:
            fichier = fichier_de(hote, nom)
            forme = managed.forme_de(fichier)
            nue = (ROOT / fichier).read_bytes().decode("utf-8")
            marquee = managed.poser(nue, forme, version="0.0.0")
            assert marquee != nue and managed.lire(marquee, forme) is not None, fichier
            marquees[(hote, nom)] = marquee
    fautes = [nom for nom in noms
              if construire(nom, {h: source(marquees[(h, nom)], fichier_de(h, nom)) for h in HOTES})
              != construire(nom, {h: lire_def(ROOT, h, nom) for h in HOTES})]
    assert fautes == [], f"une def marquee ne donne pas le JSON de sa jumelle nue : {fautes}"

    def lecteur_marque(_racine: Path, hote: str, nom: str) -> str:
        return source(marquees[(hote, nom)], fichier_de(hote, nom))

    assert ecarts(roster.charger(), ROOT, lecteur_marque) == [], REMEDE


# --- la régénération (kit seulement : `emplacements` lit apply-mode) -------------------------------
def _kit_synthetique(racine: Path, nom: str = "alpha") -> Path:
    """Pose la def `nom` sur les cinq hôtes sous `racine` ; rend le répertoire du roster, non créé."""
    for hote in HOTES:
        fichier = fichier_de(hote, nom)
        if managed.forme_de(fichier) is managed.Forme.TOML:
            texte = f'name = "{nom}"\n{OUVERTURE_TOML}\ncorps\n{FERMETURE_TOML}'
        else:
            texte = f"---\nname: {nom}\ndescription: d\n---\ncorps\n"
        (racine / fichier).parent.mkdir(parents=True, exist_ok=True)
        (racine / fichier).write_bytes(texte.encode("utf-8"))
    return racine / "src" / "cadre" / roster.REPERTOIRE


@DANS_LE_KIT
def test_regenerer_ecrit_retire_l_orphelin_puis_refuse_une_def_invalide_sans_rien_ecrire(tmp_path):
    """Tue deux mutants qui survivaient (S-00004580) : `regenerer` sans `_valider`, et sans le
    retrait des orphelins."""
    donnees = _kit_synthetique(tmp_path)
    donnees.mkdir(parents=True)
    (donnees / "fantome.json").write_bytes(b"{}\n")
    rel = f"src/cadre/{roster.REPERTOIRE}"
    assert regenerer(tmp_path, donnees) == [f"ecrit   {rel}/alpha.json", f"retire  {rel}/fantome.json"]
    assert sorted(p.name for p in donnees.iterdir()) == ["alpha.json"]
    assert regenerer(tmp_path, donnees) == []
    assert ecarts(roster._lire(Workspace(tmp_path / "src" / "cadre")), tmp_path) == []
    avant = (donnees / "alpha.json").read_bytes()
    claude = tmp_path / fichier_de("claude", "alpha")
    claude.write_bytes(claude.read_bytes().replace(b"name: alpha\n", b""))
    with pytest.raises(roster.RosterIllisible, match="ligne d'identite"):
        regenerer(tmp_path, donnees)
    assert (donnees / "alpha.json").read_bytes() == avant


@DANS_LE_KIT
def test_regenerer_refuse_tant_qu_apply_mode_est_actif(tmp_path):
    """S-00004580 F1 : les defs montées en `expert` ne se figent pas au roster. Le fichier de
    mode est SIMULÉ sous `tmp_path` : apply-mode ne tourne jamais ici."""
    donnees = _kit_synthetique(tmp_path)
    mode = _apply_mode()
    fichier_mode = tmp_path / mode.MODE_FILE.relative_to(mode.ROOT)
    fichier_mode.parent.mkdir(parents=True)
    fichier_mode.write_bytes(b"expert\n")
    with pytest.raises(SystemExit, match="restore"):
        regenerer(tmp_path, donnees)
    assert not donnees.exists(), "un refus doit preceder toute ecriture"


@DANS_LE_KIT
@pytest.mark.parametrize("lien", ["repertoire", "cible"])
def test_regenerer_refuse_un_lien_symbolique_sans_ecrire_hors_du_depot(tmp_path, lien):
    """S-00004580 F4 : `write_bytes` suit un lien ; mesuré, il écrasait un fichier hors dépôt."""
    racine = tmp_path / "depot"
    donnees = _kit_synthetique(racine)
    dehors = tmp_path / "dehors"
    dehors.mkdir()
    victime = dehors / "alpha.json"
    victime.write_bytes(b"hors depot\n")
    if lien == "repertoire":
        donnees.parent.mkdir(parents=True)
        donnees.symlink_to(dehors, target_is_directory=True)
    else:
        donnees.mkdir(parents=True)
        (donnees / "alpha.json").symlink_to(victime)
    with pytest.raises(SystemExit, match="lien symbolique"):
        regenerer(racine, donnees)
    assert victime.read_bytes() == b"hors depot\n"


@DANS_LE_KIT
def test_regenerer_garde_une_entree_que_le_module_ignore(tmp_path):
    """S-00004580 F4 : `glob("*.json")` rend `._alpha.json`, que `cadre.roster` IGNORE ;
    `regenerer` ne le retire pas."""
    donnees = _kit_synthetique(tmp_path)
    donnees.mkdir(parents=True)
    (donnees / "._alpha.json").write_bytes(b"\x00\x05\x16\x07")
    regenerer(tmp_path, donnees)
    assert sorted(p.name for p in donnees.iterdir()) == ["._alpha.json", "alpha.json"]


@DANS_LE_KIT
def test_REMEDE_nomme_le_fichier_de_mode_d_apply_mode_et_le_write_set():
    """S-00004580 F1/F2 : le remède dit de restaurer apply-mode, et de déclarer le JSON touché."""
    mode = _apply_mode()
    assert mode.MODE_FILE.relative_to(mode.ROOT).as_posix() == MODE_RELATIF
    assert f"si {MODE_RELATIF} existe, `{RESTAURER}` d'abord" in REMEDE
    assert "au write-set de ta tache (tasks.py writeset)" in REMEDE


def test_vendor_seul_k(tmp_path):
    """Lot K (T-01M5BXTPQE3JZV3KZA6WD9P5XC) : dans un kit jetable où le paquet vit sous
    `.agents/vendor/cadre` et où un `src/cadre` LEURRE refuse d'être importé, le banc lit
    `cadre` et son roster au lieu neuf. Mutant tué : `sys.path.insert(0, ROOT / "src")`
    suivi d'un `from cadre import …` (le leurre lève), ou `DONNEES` en dur sous `src`."""
    kit = tmp_path / "kit"
    banc = kit / ".agents" / "evals" / Path(__file__).name
    banc.parent.mkdir(parents=True)
    shutil.copyfile(__file__, banc)
    resolveur = kit / ".agents" / "bin" / "vendor_paths.py"
    resolveur.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / ".agents" / "bin" / "vendor_paths.py", resolveur)
    neuf = kit / ".agents" / "vendor" / "cadre"
    shutil.copytree(PAQUET, neuf, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    leurre = kit / "src" / "cadre"
    leurre.mkdir(parents=True)
    (leurre / "__init__.py").write_text('raise ImportError("ancien src/cadre importe")\n',
                                        encoding="utf-8")
    sonde = ("import runpy, sys; m = runpy.run_path(sys.argv[1]); "
             "print(m['roster'].__file__); print(m['DONNEES']); print(m['REMEDE'])")
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    rendu = subprocess.run([sys.executable, "-B", "-c", sonde, str(banc)], cwd=kit, env=env,
                           capture_output=True, text=True, timeout=120, check=False)
    assert rendu.returncode == 0, rendu.stderr
    fichier, donnees, remede = rendu.stdout.splitlines()[:3]
    attendu = neuf.resolve()
    assert Path(fichier).resolve().parent == attendu, fichier
    assert Path(donnees).resolve() == attendu / roster.REPERTOIRE, donnees
    assert f".agents/vendor/cadre/{roster.REPERTOIRE}/<nom>.json" in remede, remede


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
