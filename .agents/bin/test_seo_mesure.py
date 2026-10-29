#!/usr/bin/env python3
"""Témoins de `.agents/bin/seo_mesure.py` — mesure SEO technique déterministe (T-01M5BZC1Y0T36EHTZY9AKZ650F).

CE QU'ILS PROUVENT. Les codes de sortie du contrat (0 sans HIGH, 1 au moindre HIGH,
2 usage, refus ou rien lu) et les constats, observés de l'EXTÉRIEUR : le script
est lancé en sous-processus (`sys.executable`) sur des fixtures HTML construites
sous `tmp_path`, jamais sur l'arbre du dépôt. Lighthouse n'est JAMAIS requis ni
installé : le PATH du sous-processus est un dossier vide (jambe `non mesuré`) ou
un dossier qui porte un FAUX `lighthouse` (script /bin/sh) dont la sortie, le code
retour et la durée sont réglés par le témoin. Aucun accès réseau.

PORTÉE OS : mesuré macOS ; Linux assumé ; Windows non mesuré — les témoins à faux
`lighthouse`, à lien symbolique et à lien dur sautent hors POSIX, nommément.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent / "seo_mesure.py"
POSIX = os.name == "posix"
SAUT_POSIX = pytest.mark.skipif(not POSIX, reason="SAUT ANNONCÉ : témoin POSIX (sh, lien) — Windows non mesuré")

JSONLD_ORG = '{"@context":"https://schema.org","@type":"Organization","name":"Atelier Exemple","url":"https://exemple.test/"}'


def page(*, titre="Atelier Exemple — reliure artisanale", lang=' lang="fr"', head_extra="", body="<h1>Atelier</h1>",
         jsonld=(JSONLD_ORG,), description="Reliure et restauration de livres anciens.",
         canonical="https://exemple.test/") -> str:
    morceaux = ["<!doctype html>", f"<html{lang}>", "<head>", '<meta charset="utf-8">']
    if titre is not None:
        morceaux.append(f"<title>{titre}</title>")
    if description is not None:
        morceaux.append(f'<meta name="description" content="{description}">')
    if canonical is not None:
        morceaux.append(f'<link rel="canonical" href="{canonical}">')
    for bloc in jsonld:
        morceaux.append(f'<script type="application/ld+json">{bloc}</script>')
    morceaux += [head_extra, "</head>", "<body>", body, '<svg><title>icône</title></svg>', "</body>", "</html>"]
    return "\n".join(morceaux) + "\n"


def ecrire(dossier: Path, nom: str, texte: str) -> Path:
    chemin = dossier / nom
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(texte, encoding="utf-8")
    return chemin


@pytest.fixture()
def vide_bin(tmp_path: Path) -> Path:
    dossier = tmp_path / "bin-vide"
    dossier.mkdir()
    return dossier


def lancer(*args: str, path: Path | None = None, tmp: Path | None = None) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in ("PATH",)}
    env["PATH"] = str(path) if path is not None else str(tmp / "bin-vide")
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True,
                          env=env, timeout=60, check=False)


def mesurer(cible: Path, vide_bin: Path, *extra: str) -> subprocess.CompletedProcess:
    return lancer(str(cible), *extra, path=vide_bin)


def lignes(sortie: str, sev: str) -> list[str]:
    return [ligne for ligne in sortie.splitlines() if ligne.startswith(f"[{sev}] ")]


# --------------------------------------------------------------------------- terminal sûr
def test_controle_de_la_page_ou_du_nom_jamais_brut_au_terminal(tmp_path, vide_bin):
    """Un ESC/BEL venu du `content` d'un robots ou du NOM du fichier s'imprime échappé (`\\x1b`),
    jamais brut : une page hostile ne réécrit pas le terminal du pilote ; le `--json` reste brut."""
    robots = '<meta name="robots" content="noindex,\x1b]0;PWNED\x07\x1b[2J">'
    cible = ecrire(tmp_path / "site", "a\x1b[2Jb.html", page(head_extra=robots))
    sortie_json = tmp_path / "r.json"
    fini = mesurer(cible, vide_bin, "--json", str(sortie_json))
    assert "\x1b" not in fini.stdout and "\x07" not in fini.stdout, repr(fini.stdout)
    assert "\\x1b]0;PWNED\\x07" in fini.stdout and "a\\x1b[2Jb.html" in fini.stdout, fini.stdout
    rapport = json.loads(sortie_json.read_text(encoding="utf-8"))
    assert any("\x1b]0;PWNED\x07" in c["issue"] for c in rapport["constats"]), rapport["constats"]


def test_refus_au_stderr_jamais_brut(tmp_path, vide_bin):
    """Le refus d'une cible absente nomme son chemin sur stderr : échappé, jamais brut."""
    fini = mesurer(tmp_path / "a\x1b]0;X\x07b", vide_bin)
    assert fini.returncode == 2, fini.stderr
    assert "\x1b" not in fini.stderr and "a\\x1b]0;X\\x07b" in fini.stderr, repr(fini.stderr)


@pytest.mark.skipif(not hasattr(os, "geteuid") or os.geteuid() == 0, reason="root lit un dossier chmod 000")
def test_dossier_illisible_dit_jamais_saute(tmp_path, vide_bin):
    """Un sous-dossier que `os.walk` ne peut pas lister est un constat INFO, jamais un silence."""
    site = tmp_path / "site"
    ecrire(site, "index.html", page())
    ferme = site / "prive"
    ecrire(ferme, "cache.html", page())
    ferme.chmod(0)
    try:
        fini = mesurer(site, vide_bin)
    finally:
        ferme.chmod(0o755)
    assert "dossier illisible" in fini.stdout, fini.stdout


# --------------------------------------------------------------------------- page saine
def test_page_saine_zero_high_rc0(tmp_path, vide_bin):
    cible = ecrire(tmp_path, "index.html", page())
    fini = mesurer(cible, vide_bin)
    assert fini.returncode == 0, fini.stdout + fini.stderr
    assert lignes(fini.stdout, "HIGH") == []
    assert lignes(fini.stdout, "MEDIUM") == [], fini.stdout
    # le `<title>` d'un `<svg>` n'est pas un second titre de page
    assert "`<title>`" not in fini.stdout
    assert "jambe jsonld : mesuré : 1 fichier(s)" in fini.stdout
    assert "seo_mesure : 0 HIGH" in fini.stdout


# --------------------------------------------------------------------------- jambe JSON-LD
@pytest.mark.parametrize("bloc, attendu", [
    ('{"@context":"https://schema.org","@type":"Organization","name":"A",}', "JSON-LD invalide"),
    ('{"@context":"https://schema.org","@type":"Organization","name":NaN}', "JSON-LD invalide"),
    ('{"@context":"https://schema.org","@type":"Organization","name":Infinity}', "JSON-LD invalide"),
    ("   ", "bloc JSON-LD vide"),
    ('"une chaîne"', "racine JSON-LD qui n'est pas un objet"),
    ('{"@type":"Organization","name":"A"}', "`@context` absent ou autre que schema.org"),
    ('{"@context":"https://example.test/vocab","@type":"Organization","name":"A"}', "`@context` absent"),
    ('{"@context":"https://schema.org","name":"A"}', "`@type` absent ou vide"),
    ('{"@context":"https://schema.org","@type":7}', "`@type` qui n'est pas une chaîne"),
    ('{"@context":"https://schema.org","@graph":[]}', "`@graph` vide"),
    ('{"@context":"https://schema.org","@graph":[{"@type":"WebSite","name":"A"}]}', "`WebSite` sans champ requis : url"),
])
def test_jsonld_defaut_rend_high_rc1(tmp_path, vide_bin, bloc, attendu):
    cible = ecrire(tmp_path, "p.html", page(jsonld=(bloc,)))
    fini = mesurer(cible, vide_bin)
    assert fini.returncode == 1, fini.stdout + fini.stderr
    assert any(attendu in ligne for ligne in lignes(fini.stdout, "HIGH")), fini.stdout


VALIDES = {
    "Organization": {"name": "A"},
    "WebSite": {"name": "A", "url": "https://exemple.test/"},
    "Article": {"headline": "Titre", "datePublished": "2026-10-21"},
    "BlogPosting": {"headline": "Titre", "datePublished": "2026-10-21"},
    "Product": {"name": "Reliure"},
    "BreadcrumbList": {"itemListElement": [{"@type": "ListItem", "position": 1, "name": "Accueil"}]},
    "FAQPage": {"mainEntity": [{"@type": "Question", "name": "Q"}]},
}


@pytest.mark.parametrize("type_, champs", sorted(VALIDES.items()))
def test_chaque_type_ferme_complet_est_vert(tmp_path, vide_bin, type_, champs):
    bloc = json.dumps({"@context": "https://schema.org", "@type": type_, **champs})
    fini = mesurer(ecrire(tmp_path, "p.html", page(jsonld=(bloc,))), vide_bin)
    assert fini.returncode == 0, fini.stdout


@pytest.mark.parametrize("type_, champ", [(t, c) for t, cs in sorted(VALIDES.items()) for c in sorted(cs)])
def test_chaque_champ_requis_manquant_rend_high(tmp_path, vide_bin, type_, champ):
    """Article sans headline, et chaque autre (type, champ) du sous-ensemble fermé : HIGH, rc 1."""
    champs = {k: v for k, v in VALIDES[type_].items() if k != champ}
    bloc = json.dumps({"@context": "https://schema.org", "@type": type_, **champs})
    fini = mesurer(ecrire(tmp_path, "p.html", page(jsonld=(bloc,))), vide_bin)
    assert fini.returncode == 1, fini.stdout
    assert any(f"`{type_}` sans champ requis : {champ}" in ligne for ligne in lignes(fini.stdout, "HIGH")), fini.stdout


def test_champ_requis_vide_compte_comme_absent(tmp_path, vide_bin):
    bloc = '{"@context":"https://schema.org","@type":"Article","headline":"  ","datePublished":"2026-10-21"}'
    fini = mesurer(ecrire(tmp_path, "p.html", page(jsonld=(bloc,))), vide_bin)
    assert fini.returncode == 1 and "sans champ requis : headline" in fini.stdout, fini.stdout


def test_type_hors_liste_est_info_non_verifie_jamais_vert_muet(tmp_path, vide_bin):
    bloc = '{"@context":"https://schema.org","@type":"Recipe","name":"Pain"}'
    fini = mesurer(ecrire(tmp_path, "p.html", page(jsonld=(bloc,))), vide_bin)
    assert fini.returncode == 0
    assert any("type `Recipe` non vérifié" in ligne for ligne in lignes(fini.stdout, "INFO")), fini.stdout


def test_contexte_et_type_prefixes_sont_reconnus(tmp_path, vide_bin):
    bloc = ('{"@context":["http://schema.org/"],"@graph":[{"@type":"schema:Article","headline":"T",'
            '"datePublished":"2026-10-21"},{"@type":["https://schema.org/Organization"],"name":"A"}]}')
    fini = mesurer(ecrire(tmp_path, "p.html", page(jsonld=(bloc,))), vide_bin)
    assert fini.returncode == 0, fini.stdout
    assert "non vérifié" not in fini.stdout


def test_page_sans_jsonld_est_dite_pas_jugee_fautive(tmp_path, vide_bin):
    fini = mesurer(ecrire(tmp_path, "p.html", page(jsonld=())), vide_bin)
    assert fini.returncode == 0
    assert any("aucune donnée structurée JSON-LD" in ligne for ligne in lignes(fini.stdout, "INFO"))


# --------------------------------------------------------------------------- jambe balises
def test_title_absent_rend_high(tmp_path, vide_bin):
    fini = mesurer(ecrire(tmp_path, "p.html", page(titre=None)), vide_bin)
    assert fini.returncode == 1
    assert any("`<title>` absent" in ligne for ligne in lignes(fini.stdout, "HIGH")), fini.stdout


def test_title_vide_rend_high(tmp_path, vide_bin):
    fini = mesurer(ecrire(tmp_path, "p.html", page(titre="   ")), vide_bin)
    assert fini.returncode == 1 and "`<title>` vide" in fini.stdout


def test_deux_title_rend_medium(tmp_path, vide_bin):
    fini = mesurer(ecrire(tmp_path, "p.html", page(head_extra="<title>Autre</title>")), vide_bin)
    assert any("2 `<title>`" in ligne for ligne in lignes(fini.stdout, "MEDIUM")), fini.stdout


def test_seuil_de_longueur_du_titre_est_60(tmp_path, vide_bin):
    a_la_borne = mesurer(ecrire(tmp_path, "a.html", page(titre="x" * 60)), vide_bin)
    assert "caractères" not in a_la_borne.stdout, a_la_borne.stdout
    au_dela = mesurer(ecrire(tmp_path, "b.html", page(titre="x" * 61)), vide_bin)
    assert any("`<title>` de 61 caractères" in ligne for ligne in lignes(au_dela.stdout, "LOW")), au_dela.stdout
    assert au_dela.returncode == 0


def test_deux_h1_rend_low_et_aucun_h1_medium(tmp_path, vide_bin):
    deux = mesurer(ecrire(tmp_path, "a.html", page(body="<h1>Un</h1><h1>Deux</h1>")), vide_bin)
    assert any("2 `<h1>`" in ligne for ligne in lignes(deux.stdout, "LOW")), deux.stdout
    aucun = mesurer(ecrire(tmp_path, "b.html", page(body="<p>rien</p>")), vide_bin)
    assert any("aucun `<h1>`" in ligne for ligne in lignes(aucun.stdout, "MEDIUM")), aucun.stdout


@pytest.mark.parametrize("meta", [
    '<meta name="robots" content="noindex, follow">',
    '<meta name="ROBOTS" content="NOINDEX">',
    '<meta name="robots" content="none">',
    '<meta name="googlebot" content="noindex">',
])
def test_noindex_rend_high(tmp_path, vide_bin, meta):
    fini = mesurer(ecrire(tmp_path, "p.html", page(head_extra=meta)), vide_bin)
    assert fini.returncode == 1, fini.stdout
    assert any("interdit l'indexation" in ligne for ligne in lignes(fini.stdout, "HIGH")), fini.stdout


def test_robots_index_follow_reste_vert(tmp_path, vide_bin):
    fini = mesurer(ecrire(tmp_path, "p.html", page(head_extra='<meta name="robots" content="index, follow">')),
                   vide_bin)
    assert fini.returncode == 0, fini.stdout


def test_description_canonical_lang_absents(tmp_path, vide_bin):
    fini = mesurer(ecrire(tmp_path, "p.html", page(description=None, canonical=None, lang="")), vide_bin)
    assert any("description\">` absente" in ligne for ligne in lignes(fini.stdout, "MEDIUM")), fini.stdout
    assert any("`lang` absent" in ligne for ligne in lignes(fini.stdout, "MEDIUM")), fini.stdout
    assert any("canonical\">` absent" in ligne for ligne in lignes(fini.stdout, "LOW")), fini.stdout


def test_location_porte_fichier_et_ligne(tmp_path, vide_bin):
    fini = mesurer(ecrire(tmp_path, "p.html", page(head_extra='<meta name="robots" content="noindex">')), vide_bin)
    haut = lignes(fini.stdout, "HIGH")
    assert haut and haut[0].startswith(f"[HIGH] {tmp_path / 'p.html'}:"), haut


# --------------------------------------------------------------------------- dossier, bornes de lecture
def test_dossier_relatif_et_node_modules_saute(tmp_path, vide_bin):
    site = tmp_path / "site"
    ecrire(site, "index.html", page())
    ecrire(site, "blog/billet.html", page(titre=None))
    ecrire(site, "node_modules/paquet/x.html", page(head_extra='<meta name="robots" content="noindex">'))
    fini = mesurer(site, vide_bin)
    assert fini.returncode == 1
    assert "[HIGH] blog/billet.html — `<title>` absent" in fini.stdout, fini.stdout
    assert "node_modules" not in fini.stdout
    assert "jambe balises : mesuré : 2 fichier(s)" in fini.stdout
    assert "jambe lighthouse : non mesuré : lighthouse absent du PATH" in fini.stdout


def test_dossier_sans_html_refuse_rc2(tmp_path, vide_bin):
    (tmp_path / "vide").mkdir()
    fini = mesurer(tmp_path / "vide", vide_bin)
    assert fini.returncode == 2 and "aucun fichier .html/.htm" in fini.stderr


def test_cible_absente_refuse_rc2(tmp_path, vide_bin):
    fini = mesurer(tmp_path / "absent.html", vide_bin)
    assert fini.returncode == 2 and "cible absente" in fini.stderr


def test_usage_sans_argument_rc2(tmp_path, vide_bin):
    fini = lancer(path=vide_bin)
    assert fini.returncode == 2 and "usage" in fini.stderr


@SAUT_POSIX
def test_cible_lien_symbolique_refusee(tmp_path, vide_bin):
    reel = ecrire(tmp_path, "reel.html", page())
    lien = tmp_path / "lien.html"
    lien.symlink_to(reel)
    fini = mesurer(lien, vide_bin)
    assert fini.returncode == 2 and "lien symbolique" in fini.stderr


@SAUT_POSIX
def test_lien_dans_un_dossier_non_suivi(tmp_path, vide_bin):
    dehors = ecrire(tmp_path, "dehors/x.html", page(head_extra='<meta name="robots" content="noindex">'))
    site = tmp_path / "site"
    ecrire(site, "index.html", page())
    (site / "lien.html").symlink_to(dehors)
    fini = mesurer(site, vide_bin)
    assert fini.returncode == 0, fini.stdout
    assert "[INFO] lien.html — non lu : lien symbolique" in fini.stdout, fini.stdout


def test_fichier_trop_gros_non_lu_et_jamais_vert(tmp_path, vide_bin):
    gros = tmp_path / "gros.html"
    texte = page()
    gros.write_bytes(texte.encode("utf-8") + b" " * (4 * 1024 * 1024 + 1 - len(texte.encode("utf-8"))))
    fini = mesurer(gros, vide_bin)
    assert fini.returncode == 2, fini.stdout
    assert any("non lu : 4194305 octets" in ligne for ligne in lignes(fini.stdout, "INFO")), fini.stdout
    assert "jambe jsonld : non mesuré : aucun fichier lu" in fini.stdout


def test_fichier_a_la_borne_est_lu(tmp_path, vide_bin):
    juste = tmp_path / "juste.html"
    texte = page().encode("utf-8")
    juste.write_bytes(texte + b" " * (4 * 1024 * 1024 - len(texte)))
    fini = mesurer(juste, vide_bin)
    assert fini.returncode == 0, fini.stdout
    assert "non lu" not in fini.stdout


# --------------------------------------------------------------------------- jambe Lighthouse (faux exécutable)
def faux_lighthouse(tmp_path: Path, *, sortie: str = "", rc: int = 0, dort: int = 0) -> tuple[Path, Path]:
    dossier = tmp_path / "bin-lh"
    dossier.mkdir(exist_ok=True)
    args = tmp_path / "lh-args.txt"
    corps = tmp_path / "lh-sortie.json"
    corps.write_text(sortie, encoding="utf-8")
    lignes_sh = ["#!/bin/sh", f"printf '%s\\n' \"$@\" > {shlex.quote(str(args))}"]
    if dort:
        lignes_sh.append(f"exec /bin/sleep {dort}")
    lignes_sh += [f"/bin/cat {shlex.quote(str(corps))}", f"exit {rc}"]
    exe = dossier / "lighthouse"
    exe.write_text("\n".join(lignes_sh) + "\n", encoding="utf-8")
    exe.chmod(0o755)
    return dossier, args


def rapport_lh(score, echec=None) -> str:
    refs = [{"id": "document-title"}, {"id": "meta-description"}]
    audits = {"document-title": {"score": 1}, "meta-description": {"score": 0 if echec else 1}}
    return json.dumps({"categories": {"seo": {"score": score, "auditRefs": refs}}, "audits": audits})


def test_lighthouse_absent_jambe_non_mesuree(tmp_path, vide_bin):
    fini = mesurer(ecrire(tmp_path, "p.html", page()), vide_bin)
    assert "jambe lighthouse : non mesuré : lighthouse absent du PATH" in fini.stdout
    assert "score Lighthouse" not in fini.stdout


@SAUT_POSIX
def test_lighthouse_present_score_lu_et_arguments_exacts(tmp_path):
    cible = ecrire(tmp_path, "p.html", page())
    dossier, args = faux_lighthouse(tmp_path, sortie=rapport_lh(0.92))
    fini = lancer(str(cible), path=dossier)
    assert fini.returncode == 0, fini.stdout + fini.stderr
    assert "jambe lighthouse : mesuré : score 92/100" in fini.stdout
    vus = args.read_text(encoding="utf-8").splitlines()
    assert vus == [cible.resolve().as_uri(), "--only-categories=seo", "--output=json", "--quiet",
                   "--chrome-flags=--headless"], vus


@SAUT_POSIX
def test_lighthouse_score_bas_et_audit_en_echec(tmp_path):
    cible = ecrire(tmp_path, "p.html", page())
    dossier, _ = faux_lighthouse(tmp_path, sortie=rapport_lh(0.41, echec=True))
    fini = lancer(str(cible), path=dossier)
    assert any("score Lighthouse SEO 41/100 ; audits en échec : meta-description" in ligne
               for ligne in lignes(fini.stdout, "MEDIUM")), fini.stdout


@SAUT_POSIX
@pytest.mark.parametrize("sortie, rc, attendu", [
    ("", 3, "non mesuré : lighthouse rc 3"),
    ("pas du json", 0, "non mesuré : sortie lighthouse illisible"),
    ('{"categories":{"seo":{"score":null}}}', 0, "non mesuré : score SEO absent"),
])
def test_lighthouse_en_echec_jamais_un_score_invente(tmp_path, sortie, rc, attendu):
    cible = ecrire(tmp_path, "p.html", page())
    dossier, _ = faux_lighthouse(tmp_path, sortie=sortie, rc=rc)
    fini = lancer(str(cible), path=dossier)
    assert f"jambe lighthouse : {attendu}" in fini.stdout, fini.stdout
    assert "score Lighthouse" not in fini.stdout


@SAUT_POSIX
def test_lighthouse_borne_de_temps(tmp_path):
    cible = ecrire(tmp_path, "p.html", page())
    dossier, _ = faux_lighthouse(tmp_path, sortie=rapport_lh(1), dort=20)
    fini = lancer(str(cible), "--delai-lighthouse", "1", path=dossier)
    assert "jambe lighthouse : non mesuré : lighthouse a dépassé 1 s" in fini.stdout, fini.stdout


@SAUT_POSIX
def test_lighthouse_jamais_sur_un_dossier(tmp_path):
    site = tmp_path / "site"
    ecrire(site, "index.html", page())
    dossier, args = faux_lighthouse(tmp_path, sortie=rapport_lh(1))
    fini = lancer(str(site), path=dossier)
    assert "jambe lighthouse : non mesuré : cible dossier" in fini.stdout
    assert not args.exists()


def test_delai_hors_borne_refuse(tmp_path, vide_bin):
    fini = mesurer(ecrire(tmp_path, "p.html", page()), vide_bin, "--delai-lighthouse", "0")
    assert fini.returncode == 2 and "usage" in fini.stderr


# --------------------------------------------------------------------------- sortie --json
def test_json_schema_et_contenu(tmp_path, vide_bin):
    cible = ecrire(tmp_path, "p.html", page(titre=None))
    sortie = tmp_path / "rapport.json"
    fini = mesurer(cible, vide_bin, "--json", str(sortie))
    assert fini.returncode == 1
    rapport = json.loads(sortie.read_text(encoding="utf-8"))
    assert set(rapport) == {"schema", "genere_le", "cible", "constats", "jambes"}
    assert rapport["schema"] == 1 and rapport["cible"] == str(cible)
    assert set(rapport["jambes"]) == {"jsonld", "balises", "lighthouse"}
    assert rapport["jambes"]["lighthouse"] == "non mesuré : lighthouse absent du PATH"
    haut = [c for c in rapport["constats"] if c["sev"] == "HIGH"]
    assert haut and set(haut[0]) == {"sev", "location", "issue", "fix", "jambe"}
    assert haut[0]["jambe"] == "balises"
    assert [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")] == []


@SAUT_POSIX
def test_json_lien_symbolique_refuse_cible_intacte(tmp_path, vide_bin):
    victime = tmp_path / "victime.txt"
    victime.write_text("intacte\n", encoding="utf-8")
    lien = tmp_path / "rapport.json"
    lien.symlink_to(victime)
    fini = mesurer(ecrire(tmp_path, "p.html", page()), vide_bin, "--json", str(lien))
    assert fini.returncode == 2 and "lien symbolique" in fini.stderr
    assert victime.read_text(encoding="utf-8") == "intacte\n"


@SAUT_POSIX
def test_json_ecriture_atomique_ne_traverse_pas_un_lien_dur(tmp_path, vide_bin):
    """`os.replace` pose un NOUVEL inode : un lien dur vers la sortie n'est pas réécrit en place."""
    victime = tmp_path / "victime.txt"
    victime.write_text("intacte\n", encoding="utf-8")
    sortie = tmp_path / "rapport.json"
    os.link(victime, sortie)
    fini = mesurer(ecrire(tmp_path, "p.html", page()), vide_bin, "--json", str(sortie))
    assert fini.returncode == 0, fini.stdout + fini.stderr
    assert victime.read_text(encoding="utf-8") == "intacte\n"
    assert json.loads(sortie.read_text(encoding="utf-8"))["schema"] == 1


def test_json_dossier_de_sortie_absent_refuse(tmp_path, vide_bin):
    fini = mesurer(ecrire(tmp_path, "p.html", page()), vide_bin, "--json", str(tmp_path / "nulle-part" / "r.json"))
    assert fini.returncode == 2 and "dossier de sortie absent" in fini.stderr
