#!/usr/bin/env python3
"""MESURE SEO TECHNIQUE DÉTERMINISTE D'UNE PAGE OU D'UN DOSSIER HTML (T-01M5BZC1Y0T36EHTZY9AKZ650F).

POURQUOI CE FICHIER. Un conseil SEO écrit sans mesure est une opinion : ce script
produit la MESURE que l'agent `seo-specialist` et la skill `seo` exigent AVANT
toute ligne de conseil. Bibliothèque standard seule, aucun accès réseau, aucun
`eval` ; le HTML est lu par `html.parser`, le JSON-LD par `json.loads`.

CLI :
  seo_mesure.py <fichier.html|dossier> [--json <sortie>] [--delai-lighthouse <s>]

CE QU'IL MESURE — trois jambes :
  (a) jsonld — chaque `<script type="application/ld+json">` : JSON valide (NaN et
      Infinity REFUSÉS), `@context` schema.org exigé, `@type` présent, et pour un
      sous-ensemble FERMÉ de types (`TYPES_REQUIS`) leurs champs requis. Un type
      hors liste rend un constat INFO « non vérifié », jamais un faux vert.
  (b) balises — `<title>` absent, vide, multiple ou trop long (au-delà de
      `TITRE_MAX` caractères : heuristique, pas un seuil publié par Google),
      `<meta name="description">`, compte des `<h1>`, `<link rel="canonical">`,
      `noindex`/`none` dans `<meta name="robots|googlebot">`, `lang` sur `<html>`.
  (c) lighthouse — SEULEMENT si l'exécutable `lighthouse` est dans le PATH (jamais
      `npx`, qui est un accès réseau) ET que la cible est UN fichier : il est joué
      `--only-categories=seo --output=json --quiet --chrome-flags=--headless` sous
      une borne de temps, et son score est lu. Sinon la jambe dit `non mesuré :
      <raison>` — jamais un score inventé.

SORTIE. Une ligne `[HIGH|MEDIUM|LOW|INFO] <location> — <issue> — <fix>` par constat
sur stdout, puis l'état des trois jambes et un total. `--json <sortie>` écrit
`{schema:1, genere_le, cible, constats:[{sev,location,issue,fix,jambe}],
jambes:{jsonld,balises,lighthouse}}` par écriture ATOMIQUE (fichier temporaire du
même dossier puis `os.replace`) ; une sortie qui est un lien symbolique est refusée,
et `os.replace` remplace le lien, jamais sa cible.

CODES DE SORTIE — 0 aucun constat HIGH · 1 au moins un HIGH · 2 usage ou refus
(cible absente, lien symbolique, dossier sans HTML, sortie `--json` refusée), ou
AUCUN fichier lu (tous trop gros ou illisibles : rien mesuré n'est jamais un vert).

BORNES, dites :
  - un fichier de plus de `TAILLE_MAX` octets (4 Mio) n'est PAS lu : constat INFO
    `non lu` ; un lien symbolique rencontré dans un dossier n'est pas suivi
    (constat INFO `non lu`) ; au-delà de `FICHIERS_MAX` fichiers, le reste n'est
    pas lu, et c'est dit ; `node_modules/` et `.git/` ne sont pas parcourus ;
  - les champs requis sont ceux du KIT (`TYPES_REQUIS`), pas la liste d'éligibilité
    aux résultats enrichis de Google, qui se lit sur sa page, type par type ;
  - les nœuds imbriqués (un `author` dans un `Article`) ne sont pas vérifiés ;
    seuls le nœud racine et les nœuds d'un `@graph` le sont ;
  - le HTML est lu tel qu'il est sur disque : une page rendue côté client par
    JavaScript n'est jugée que sur son squelette — mesurer la SORTIE RENDUE ;
  - Lighthouse charge la page dans Chrome : les ressources distantes qu'elle
    référence sont chargées par Chrome, pas par ce script.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

SCHEMA = 1
TAILLE_MAX = 4 * 1024 * 1024
FICHIERS_MAX = 500
TITRE_MAX = 60
DELAI_LIGHTHOUSE = 180
DELAI_LIGHTHOUSE_MAX = 900
DOSSIERS_SAUTES = frozenset({"node_modules", ".git"})
SEVERITES = ("HIGH", "MEDIUM", "LOW", "INFO")
EXTENSIONS = (".html", ".htm")

# Sous-ensemble FERMÉ : type schema.org -> champs dont le kit exige la présence.
TYPES_REQUIS: dict[str, tuple[str, ...]] = {
    "Organization": ("name",),
    "WebSite": ("name", "url"),
    "Article": ("headline", "datePublished"),
    "BlogPosting": ("headline", "datePublished"),
    "Product": ("name",),
    "BreadcrumbList": ("itemListElement",),
    "FAQPage": ("mainEntity",),
}
CONTEXTES_SCHEMA = frozenset({"https://schema.org", "http://schema.org"})
PREFIXES_TYPE = ("https://schema.org/", "http://schema.org/", "schema:")


class Refus(Exception):
    """Usage ou refus : code de sortie 2."""


def constat(sev: str, location: str, issue: str, fix: str, jambe: str) -> dict:
    return {"sev": sev, "location": location, "issue": issue, "fix": fix, "jambe": jambe}


# --------------------------------------------------------------------------- lecture HTML
class _Page(HTMLParser):
    """Relève ce que les jambes jugent ; `<title>` dans un `<svg>` n'est pas le titre de page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lang: str | None = None
        self.html_vu = False
        self.titres: list[tuple[int, str]] = []
        self.descriptions: list[tuple[int, str]] = []
        self.robots: list[tuple[int, str, str]] = []
        self.canoniques: list[tuple[int, str]] = []
        self.h1: list[int] = []
        self.jsonld: list[tuple[int, str]] = []
        self._svg = 0
        self._titre: list[str] | None = None
        self._titre_ligne = 0
        self._script: list[str] | None = None
        self._script_ligne = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        ligne = self.getpos()[0]
        if tag == "html" and not self.html_vu:
            self.html_vu = True
            self.lang = a.get("lang")
        elif tag == "svg":
            self._svg += 1
        elif tag == "title" and not self._svg:
            self._titre, self._titre_ligne = [], ligne
        elif tag == "meta":
            nom = a.get("name", "").strip().lower()
            if nom == "description":
                self.descriptions.append((ligne, a.get("content", "")))
            elif nom in ("robots", "googlebot"):
                self.robots.append((ligne, nom, a.get("content", "")))
        elif tag == "link" and "canonical" in a.get("rel", "").lower().split():
            self.canoniques.append((ligne, a.get("href", "")))
        elif tag == "h1":
            self.h1.append(ligne)
        elif tag == "script" and a.get("type", "").strip().lower() == "application/ld+json":
            self._script, self._script_ligne = [], ligne

    def handle_endtag(self, tag: str) -> None:
        if tag == "svg" and self._svg:
            self._svg -= 1
        elif tag == "title" and self._titre is not None:
            self.titres.append((self._titre_ligne, "".join(self._titre)))
            self._titre = None
        elif tag == "script" and self._script is not None:
            self.jsonld.append((self._script_ligne, "".join(self._script)))
            self._script = None

    def handle_data(self, data: str) -> None:
        if self._titre is not None:
            self._titre.append(data)
        if self._script is not None:
            self._script.append(data)


# --------------------------------------------------------------------------- jambe (a) JSON-LD
def _refuse_constante(nom: str):
    raise ValueError(f"constante {nom} refusée (hors JSON strict)")


def _contexte_schema(ctx) -> bool:
    if isinstance(ctx, str):
        return ctx.strip().rstrip("/").lower() in CONTEXTES_SCHEMA
    if isinstance(ctx, list):
        return any(_contexte_schema(c) for c in ctx)
    if isinstance(ctx, dict):
        return _contexte_schema(ctx.get("@vocab"))
    return False


def _nom_type(brut: str) -> str:
    for prefixe in PREFIXES_TYPE:
        if brut.startswith(prefixe):
            return brut[len(prefixe):]
    return brut


def _vide(valeur) -> bool:
    if valeur is None:
        return True
    if isinstance(valeur, str):
        return not valeur.strip()
    if isinstance(valeur, (list, dict)):
        return not valeur
    return False


def _noeud(noeud, loc: str, sortie: list[dict]) -> None:
    if not isinstance(noeud, dict):
        sortie.append(constat("HIGH", loc, "nœud JSON-LD qui n'est pas un objet",
                              "chaque nœud est un objet `{\"@type\": …}`", "jsonld"))
        return
    types = noeud.get("@type")
    if _vide(types):
        sortie.append(constat("HIGH", loc, "`@type` absent ou vide",
                              "déclarer le type schema.org du nœud (`\"@type\": \"Organization\"`…)", "jsonld"))
        return
    for brut in (types if isinstance(types, list) else [types]):
        if not isinstance(brut, str):
            sortie.append(constat("HIGH", loc, "`@type` qui n'est pas une chaîne",
                                  "écrire le type comme une chaîne schema.org", "jsonld"))
            continue
        nom = _nom_type(brut.strip())
        requis = TYPES_REQUIS.get(nom)
        if requis is None:
            sortie.append(constat("INFO", loc, f"type `{nom}` non vérifié (hors du sous-ensemble du kit)",
                                  "lire ses champs requis sur la page du type (schema.org, Google Search Central)",
                                  "jsonld"))
            continue
        manquants = [champ for champ in requis if _vide(noeud.get(champ))]
        if manquants:
            sortie.append(constat("HIGH", loc, f"`{nom}` sans champ requis : {', '.join(manquants)}",
                                  f"renseigner {', '.join(manquants)} sur le nœud `{nom}`", "jsonld"))


def juger_jsonld(rel: str, blocs: list[tuple[int, str]], sortie: list[dict]) -> None:
    for ligne, texte in blocs:
        loc = f"{rel}:{ligne}"
        if not texte.strip():
            sortie.append(constat("HIGH", loc, "bloc JSON-LD vide",
                                  "retirer le `<script type=\"application/ld+json\">` vide ou le remplir", "jsonld"))
            continue
        try:
            donnees = json.loads(texte, parse_constant=_refuse_constante)
        except ValueError as exc:
            sortie.append(constat("HIGH", loc, f"JSON-LD invalide : {exc}",
                                  "corriger la syntaxe JSON (validateur : Rich Results Test de Google)", "jsonld"))
            continue
        for item in (donnees if isinstance(donnees, list) else [donnees]):
            if not isinstance(item, dict):
                sortie.append(constat("HIGH", loc, "racine JSON-LD qui n'est pas un objet",
                                      "la racine est un objet (ou une liste d'objets)", "jsonld"))
                continue
            if not _contexte_schema(item.get("@context")):
                sortie.append(constat("HIGH", loc, "`@context` absent ou autre que schema.org",
                                      "écrire `\"@context\": \"https://schema.org\"`", "jsonld"))
                continue
            graphe = item.get("@graph")
            if isinstance(graphe, list):
                if not graphe:
                    sortie.append(constat("HIGH", loc, "`@graph` vide", "retirer `@graph` ou y mettre des nœuds",
                                          "jsonld"))
                for noeud in graphe:
                    _noeud(noeud, loc, sortie)
            else:
                _noeud(item, loc, sortie)


# --------------------------------------------------------------------------- jambe (b) balises
def juger_balises(rel: str, page: _Page, sortie: list[dict]) -> None:
    if not page.titres:
        sortie.append(constat("HIGH", f"{rel}", "`<title>` absent",
                              "ajouter un `<title>` unique et descriptif dans `<head>`", "balises"))
    else:
        if len(page.titres) > 1:
            sortie.append(constat("MEDIUM", f"{rel}:{page.titres[1][0]}", f"{len(page.titres)} `<title>`",
                                  "garder un seul `<title>` par page", "balises"))
        ligne, texte = page.titres[0]
        titre = " ".join(texte.split())
        if not titre:
            sortie.append(constat("HIGH", f"{rel}:{ligne}", "`<title>` vide",
                                  "écrire un titre unique et descriptif", "balises"))
        elif len(titre) > TITRE_MAX:
            sortie.append(constat("LOW", f"{rel}:{ligne}",
                                  f"`<title>` de {len(titre)} caractères (> {TITRE_MAX}, heuristique : risque de coupe)",
                                  f"resserrer le titre sous {TITRE_MAX} caractères, l'essentiel en tête", "balises"))
    if not page.descriptions:
        sortie.append(constat("MEDIUM", rel, "`<meta name=\"description\">` absente",
                              "ajouter une description propre à la page", "balises"))
    elif not page.descriptions[0][1].strip():
        sortie.append(constat("MEDIUM", f"{rel}:{page.descriptions[0][0]}", "`<meta name=\"description\">` vide",
                              "écrire une description propre à la page", "balises"))
    if not page.h1:
        sortie.append(constat("MEDIUM", rel, "aucun `<h1>`", "donner à la page un titre principal `<h1>`", "balises"))
    elif len(page.h1) > 1:
        sortie.append(constat("LOW", f"{rel}:{page.h1[1]}", f"{len(page.h1)} `<h1>`",
                              "un `<h1>` unique porte le sujet de la page ; les autres en `<h2>`", "balises"))
    if not page.canoniques:
        sortie.append(constat("LOW", rel, "`<link rel=\"canonical\">` absent",
                              "déclarer l'URL canonique absolue de la page", "balises"))
    else:
        if len(page.canoniques) > 1:
            sortie.append(constat("MEDIUM", f"{rel}:{page.canoniques[1][0]}",
                                  f"{len(page.canoniques)} `<link rel=\"canonical\">`",
                                  "une seule URL canonique par page", "balises"))
        if not page.canoniques[0][1].strip():
            sortie.append(constat("MEDIUM", f"{rel}:{page.canoniques[0][0]}", "`canonical` sans `href`",
                                  "renseigner l'URL canonique absolue", "balises"))
    for ligne, nom, contenu in page.robots:
        jetons = {j.strip().lower() for j in contenu.split(",")}
        if "noindex" in jetons or "none" in jetons:
            sortie.append(constat("HIGH", f"{rel}:{ligne}", f"`<meta name=\"{nom}\">` interdit l'indexation ({contenu.strip()})",
                                  "retirer `noindex`/`none` d'une page publique ; si voulu, le dire au rapport", "balises"))
    if not page.html_vu or page.lang is None or not page.lang.strip():
        sortie.append(constat("MEDIUM", rel, "`lang` absent de `<html>`",
                              "déclarer la langue : `<html lang=\"fr\">`", "balises"))


# --------------------------------------------------------------------------- jambe (c) Lighthouse
def jouer_lighthouse(cible: Path, est_fichier: bool, delai: int, sortie: list[dict]) -> str:
    exe = shutil.which("lighthouse")
    if exe is None:
        return "non mesuré : lighthouse absent du PATH"
    if not est_fichier:
        return "non mesuré : cible dossier — Lighthouse se joue sur une page"
    commande = [exe, cible.resolve().as_uri(), "--only-categories=seo", "--output=json", "--quiet",
                "--chrome-flags=--headless"]
    try:
        fini = subprocess.run(commande, capture_output=True, text=True, timeout=delai, check=False)
    except subprocess.TimeoutExpired:
        return f"non mesuré : lighthouse a dépassé {delai} s"
    except OSError as exc:
        return f"non mesuré : lighthouse non lancé ({type(exc).__name__})"
    if fini.returncode != 0:
        return f"non mesuré : lighthouse rc {fini.returncode}"
    try:
        rapport = json.loads(fini.stdout, parse_constant=_refuse_constante)
        score = rapport["categories"]["seo"]["score"]
    except (ValueError, KeyError, TypeError):
        return "non mesuré : sortie lighthouse illisible"
    if not isinstance(score, (int, float)) or isinstance(score, bool) or not 0 <= score <= 1:
        return "non mesuré : score SEO absent de la sortie lighthouse"
    centieme = round(score * 100)
    if centieme < 50:
        sev = "MEDIUM"
    elif centieme < 90:
        sev = "LOW"
    else:
        sev = "INFO"
    echecs = []
    try:
        for ref in rapport["categories"]["seo"].get("auditRefs", []):
            audit = rapport.get("audits", {}).get(ref.get("id"), {})
            if audit.get("score") == 0:
                echecs.append(ref.get("id"))
    except (AttributeError, TypeError):
        echecs = []
    detail = f" ; audits en échec : {', '.join(echecs)}" if echecs else ""
    sortie.append(constat(sev, str(cible), f"score Lighthouse SEO {centieme}/100{detail}",
                          "corriger les audits en échec (rapport Lighthouse)" if echecs else "aucun audit en échec",
                          "lighthouse"))
    return f"mesuré : score {centieme}/100"


# --------------------------------------------------------------------------- parcours
def _lire(chemin: Path, rel: str, sortie: list[dict]) -> str | None:
    if chemin.is_symlink():
        sortie.append(constat("INFO", rel, "non lu : lien symbolique (jamais suivi)",
                              "mesurer le fichier réel", "lecture"))
        return None
    drapeaux = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(chemin, drapeaux)
    except OSError as exc:
        sortie.append(constat("INFO", rel, f"non lu : {type(exc).__name__}", "vérifier les droits du fichier",
                              "lecture"))
        return None
    with os.fdopen(fd, "rb") as fichier:
        taille = os.fstat(fichier.fileno()).st_size
        if taille > TAILLE_MAX:
            sortie.append(constat("INFO", rel, f"non lu : {taille} octets (> {TAILLE_MAX})",
                                  "mesurer une page plus petite ou la découper", "lecture"))
            return None
        octets = fichier.read(TAILLE_MAX + 1)
    if len(octets) > TAILLE_MAX:
        sortie.append(constat("INFO", rel, f"non lu : plus de {TAILLE_MAX} octets", "mesurer une page plus petite",
                              "lecture"))
        return None
    texte = octets.decode("utf-8", errors="replace")
    if "�" in texte and b"\xef\xbf\xbd" not in octets:
        sortie.append(constat("INFO", rel, "octets non UTF-8 remplacés à la lecture",
                              "servir la page en UTF-8", "lecture"))
    return texte


def lister(cible: Path, sortie: list[dict]) -> list[tuple[Path, str]]:
    if cible.is_file():
        return [(cible, str(cible))]
    trouves: list[tuple[Path, str]] = []

    def _illisible(exc: OSError) -> None:
        # Un dossier que `os.walk` ne peut pas lister est DIT, comme un fichier illisible : jamais sauté en silence.
        sortie.append(constat("INFO", str(exc.filename or cible), f"non lu : dossier illisible ({type(exc).__name__})",
                              "vérifier les droits du dossier", "lecture"))

    for racine, dossiers, fichiers in os.walk(cible, followlinks=False, onerror=_illisible):
        dossiers[:] = sorted(d for d in dossiers if d not in DOSSIERS_SAUTES)
        for nom in sorted(fichiers):
            if nom.lower().endswith(EXTENSIONS):
                chemin = Path(racine) / nom
                trouves.append((chemin, chemin.relative_to(cible).as_posix()))
    if len(trouves) > FICHIERS_MAX:
        sortie.append(constat("INFO", str(cible),
                              f"{len(trouves) - FICHIERS_MAX} fichier(s) HTML non lus (borne {FICHIERS_MAX})",
                              "mesurer le dossier par sous-dossiers", "lecture"))
        trouves = trouves[:FICHIERS_MAX]
    return trouves


def mesurer(cible: Path, delai: int) -> tuple[list[dict], dict, int]:
    if cible.is_symlink():
        raise Refus(f"refus : la cible {cible} est un lien symbolique (jamais suivi)")
    if not cible.exists():
        raise Refus(f"refus : cible absente : {cible}")
    if not (cible.is_file() or cible.is_dir()):
        raise Refus(f"refus : cible ni fichier ni dossier : {cible}")
    constats: list[dict] = []
    fichiers = lister(cible, constats)
    if not fichiers:
        raise Refus(f"refus : aucun fichier .html/.htm sous {cible} — rien à mesurer")
    lus = 0
    for chemin, rel in fichiers:
        texte = _lire(chemin, rel, constats)
        if texte is None:
            continue
        lus += 1
        page = _Page()
        page.feed(texte)
        page.close()
        juger_jsonld(rel, page.jsonld, constats)
        if not page.jsonld:
            constats.append(constat("INFO", rel, "aucune donnée structurée JSON-LD",
                                    "en ajouter si un type schema.org décrit la page", "jsonld"))
        juger_balises(rel, page, constats)
    etat = f"mesuré : {lus} fichier(s)" if lus else "non mesuré : aucun fichier lu"
    lighthouse = (jouer_lighthouse(cible, cible.is_file(), delai, constats) if lus
                  else "non mesuré : aucun fichier lu")
    jambes = {"jsonld": etat, "balises": etat, "lighthouse": lighthouse}
    constats.sort(key=lambda c: (SEVERITES.index(c["sev"]), c["location"], c["issue"]))
    return constats, jambes, lus


# --------------------------------------------------------------------------- sortie
def ecrire_atomique(chemin: Path, octets: bytes) -> None:
    """Fichier temporaire du même dossier, fsync, puis `os.replace` : jamais d'écriture en place."""
    dossier = chemin.parent
    fd, temporaire = tempfile.mkstemp(prefix=f".{chemin.name}.", suffix=".tmp", dir=dossier)
    try:
        with os.fdopen(fd, "wb") as fichier:
            fichier.write(octets)
            fichier.flush()
            os.fsync(fichier.fileno())
        os.replace(temporaire, chemin)
    except BaseException:
        try:
            os.unlink(temporaire)
        except FileNotFoundError:
            pass
        raise


def _verifier_sortie(chemin: Path) -> None:
    if chemin.is_symlink():
        raise Refus(f"refus : la sortie {chemin} est un lien symbolique (jamais écrite à travers)")
    if chemin.exists() and not chemin.is_file():
        raise Refus(f"refus : la sortie {chemin} existe et n'est pas un fichier")
    if not chemin.parent.is_dir():
        raise Refus(f"refus : dossier de sortie absent : {chemin.parent}")


def _delai(brut: str) -> int:
    try:
        valeur = int(brut)
    except ValueError:
        raise argparse.ArgumentTypeError(f"entier attendu, reçu {brut!r}") from None
    if not 1 <= valeur <= DELAI_LIGHTHOUSE_MAX:
        raise argparse.ArgumentTypeError(f"borne 1..{DELAI_LIGHTHOUSE_MAX} s")
    return valeur


class _Analyseur(argparse.ArgumentParser):
    def error(self, message: str):  # usage : code 2, une ligne
        raise Refus(f"usage : {message}")


def affichable(texte: object) -> str:
    """Un texte tiré de la page ou d'un nom de fichier, sûr pour le terminal : tout caractère
    non imprimable (ESC, BEL, CR…) écrit `\\xNN` / `\\uNNNN`. La sortie `--json` garde la valeur brute."""
    return "".join(c if c.isprintable() else (f"\\x{ord(c):02x}" if ord(c) < 0x100 else f"\\u{ord(c):04x}")
                   for c in str(texte))


def main(argv: list[str] | None = None) -> int:
    analyseur = _Analyseur(prog="seo_mesure.py", allow_abbrev=False,
                           description="Mesure SEO technique déterministe d'un fichier ou d'un dossier HTML.")
    analyseur.add_argument("cible")
    analyseur.add_argument("--json", dest="sortie_json")
    analyseur.add_argument("--delai-lighthouse", type=_delai, default=DELAI_LIGHTHOUSE)
    try:
        args = analyseur.parse_args(argv)
        cible = Path(args.cible)
        sortie_json = Path(args.sortie_json) if args.sortie_json else None
        if sortie_json is not None:
            _verifier_sortie(sortie_json)
        constats, jambes, lus = mesurer(cible, args.delai_lighthouse)
    except Refus as exc:
        print(f"seo_mesure : {affichable(exc)}", file=sys.stderr)
        return 2
    for c in constats:
        print(f"[{c['sev']}] {affichable(c['location'])} — {affichable(c['issue'])} — {affichable(c['fix'])}")
    for nom in ("jsonld", "balises", "lighthouse"):
        print(f"jambe {nom} : {affichable(jambes[nom])}")
    comptes = {sev: sum(1 for c in constats if c["sev"] == sev) for sev in SEVERITES}
    # Rien lu = rien mesuré : jamais un vert (2), même sans constat HIGH.
    code = 2 if not lus else (1 if comptes["HIGH"] else 0)
    print("seo_mesure : " + ", ".join(f"{n} {sev}" for sev, n in comptes.items()) + f" — rc {code}")
    if sortie_json is not None:
        rapport = {"schema": SCHEMA, "genere_le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "cible": str(cible), "constats": constats, "jambes": jambes}
        try:
            _verifier_sortie(sortie_json)
            ecrire_atomique(sortie_json, (json.dumps(rapport, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        except (Refus, OSError) as exc:
            print(f"seo_mesure : sortie JSON non écrite — {affichable(exc)}", file=sys.stderr)
            return 2
    return code


if __name__ == "__main__":
    sys.exit(main())
