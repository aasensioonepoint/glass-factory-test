"""FILET DE FORME DU CHANGELOG (T-01M4ZWNEDCJCNFF4HWQEWZX1J0, décisions pilote S-01M51GYP87BQ6BYF956WG29GKM
et S-01M4ZWNQXF3KGWSM2KVX6ECEWT).

Ce qu'il juge : la FORME de `## Non publié` (vide admis entre deux tags ; hors du tag, seule `### Contrat`
y reçoit des lignes, décision S-01M51H3PTQ75984NP7ZD7JZBMS) et de chaque section de version —
titre de version, sous-sections de la liste fermée, entrée en trois lignes au plus (titre en gras sans
identifiant, « Ce que ça change pour vous : » de 320 caractères au plus, au besoin une ligne `Technique :`),
« à paraître » sur la version la plus récente seule, `### Historique` sous la plus ancienne seule, chaque
numéro de version une seule fois, les versions en ordre décroissant, et au moins une ligne en gras (`**`)
sous une version datée — une coupe vide rougit. Et l'historique FIGÉ, par son empreinte sha256.
Ce qu'il ne juge PAS : la lisibilité, la vérité d'une entrée, `## Pour les mainteneurs`, ni le CONTENU de
l'historique (seule son empreinte est comparée), ni le tag oublié (« à paraître » sur une version déjà
tagguée) : il ne lit pas git, pour qu'un rejeu `--at <sha>` d'un arbre ancien ne dépende pas des tags posés
depuis.

Mode script : `python3 .agents/evals/test_changelog_format.py CHANGELOG.md` imprime une faute par ligne et
rend 1 s'il en trouve, 0 et rien sinon.
"""
import hashlib
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CHANGELOG = ROOT / "CHANGELOG.md"
# adopting-tree: HISTORIQUE reste dans le kit ; le skip de module ci-dessous couvre tous ses lecteurs.
HISTORIQUE = ROOT / "docs" / "HISTORIQUE-0.1.0.md"
# L'historique est FIGÉ : empreinte relevée sur la copie faite à la coupe, octet pour octet.
# Toute RECOPIE de l'historique (au retour du lot comme à la reprise avant la fusion de la livraison)
# recalcule cette empreinte dans le même commit ; aucune autre écriture ne la change.
EMPREINTE_HISTORIQUE = "a6c0def36eb8c139adec37b02b086879a334dbb7dc3a74d6e02bba2cea31689e"
# adopting-tree: le marqueur du kit ne voyage pas ; son absence déclenche ce skip de module.
EST_LE_KIT = (ROOT / ".agents" / "IS_THE_KIT").is_file()
pytestmark = pytest.mark.skipif(not EST_LE_KIT, reason="SAUT ANNONCE : `.agents/IS_THE_KIT` absent (projet adoptant)")

SOUS = ("Ce que fait le kit", "Ajouté", "Changé", "Corrigé", "Retiré", "Limites connues", "Contrat", "Historique")
VERSION = re.compile(r"^## (\d+\.\d+\.\d+) — (\d{4}-\d{2}-\d{2}|à paraître)$")
ID = re.compile(r"(?<![0-9A-Za-z])[TSL]-(?:[0-9A-HJKMNP-TV-Z]{26}|\d{1,12})(?![0-9A-Za-z])")
VOUS = "Ce que ça change pour vous : "
BORNE = 320


def fautes(texte: str) -> list[str]:
    """Les fautes de forme du journal `texte`, dans l'ordre de lecture ; liste vide si le journal est au format."""
    f = []
    sections = re.split(r"(?m)^(?=## )", texte)
    titres = [s.split("\n", 1)[0] for s in sections[1:]]
    if titres.count("## Non publié") != 1 or not titres or titres[0] != "## Non publié":
        return ["`## Non publié` absent, double ou pas en premier"]
    if re.search(r"(?m)^(\*\*|### |- )", sections[0]):
        f.append("une entrée ou une sous-section précède `## Non publié`")
    versions = [t for t in titres[1:] if VERSION.match(t)]
    numeros = [VERSION.match(t).group(1) for t in versions]
    cles = [tuple(int(x) for x in n.split(".")) for n in numeros]
    if cles != sorted(cles, reverse=True):
        f.append("versions hors de l'ordre décroissant")
    for n in sorted({n for n in numeros if numeros.count(n) > 1}):
        f.append(f"version en double : {n}")
    for k, t in enumerate(versions):
        if t.endswith("— à paraître") and k != 0:
            f.append(f"« à paraître » ailleurs que sur la version la plus récente : {t}")
    for s in sections[1:]:
        tete, _, corps = s.partition("\n")
        if tete == "## Pour les mainteneurs":
            break
        la_plus_ancienne = bool(versions) and tete == versions[-1]
        if tete != "## Non publié" and not VERSION.match(tete):
            f.append(f"titre de section inconnu : {tete}")
            continue
        sous = None
        for bloc in re.split(r"\n\s*\n", corps):
            lignes = [l for l in bloc.split("\n") if l.strip()]
            if not lignes:
                continue
            if lignes[0].startswith("### "):
                sous = lignes[0][4:].strip()
                if tete == "## Non publié" and sous != "Contrat":
                    f.append(f"{tete} : seule `### Contrat` s'écrit hors du tag (S-01M51H3PTQ75984NP7ZD7JZBMS) : {sous}")
                if sous not in SOUS:
                    f.append(f"{tete} : sous-section hors liste : {sous}")
                elif sous == "Historique" and not la_plus_ancienne:
                    f.append(f"{tete} : `### Historique` admis sous la version la plus ancienne seule")
                lignes = lignes[1:]
                if not lignes:
                    continue
            if sous == "Historique":
                continue
            t = lignes[0][:60]
            if sous is None:
                f.append(f"{tete} : entrée hors sous-section : {t}")
                continue
            if not re.fullmatch(r"\*\*[^*].*[^*]\*\*", lignes[0]) or ID.search(lignes[0]):
                f.append(f"{tete} : titre hors `**…**` ou avec identifiant : {t}")
            if len(lignes) < 2 or not lignes[1].startswith(VOUS):
                f.append(f"{tete} : ligne « {VOUS.strip()} » absente : {t}")
            elif len(lignes[1]) > BORNE or ID.search(lignes[1]):
                f.append(f"{tete} : « pour vous » trop long ou avec identifiant : {t}")
            if len(lignes) > 3 or (len(lignes) == 3 and not lignes[2].startswith("Technique : ")):
                f.append(f"{tete} : au plus une ligne `Technique :` après « pour vous » : {t}")
    for s in sections[1:]:
        tete, _, corps = s.partition("\n")
        if tete == "## Pour les mainteneurs":
            break
        m = VERSION.match(tete)
        if m and m.group(2) != "à paraître" and not re.search(r"(?m)^\*\*", corps):
            f.append(f"{tete} : version datée sans aucune entrée")
    return f


def test_le_changelog_reel_est_au_format():
    assert fautes(CHANGELOG.read_text(encoding="utf-8")) == []


ECHANTILLON = """# Journal

## Non publié

## 0.2.0 — à paraître

### Corrigé

**Un titre clair.**
Ce que ça change pour vous : une phrase.
Technique : `outil` (T-00000001).

### Ajouté

**Un ajout.**
Ce que ça change pour vous : une phrase.

## 0.1.0 — 2026-10-16

### Limites connues

**Une limite.**
Ce que ça change pour vous : une phrase.

### Historique

Texte libre.

## Pour les mainteneurs

Rien n'est jugé ici (T-00000002).
"""


def test_l_echantillon_est_vert():
    assert fautes(ECHANTILLON) == []


# Les mutants portent sur l'ÉCHANTILLON, jamais sur la prose réelle du CHANGELOG.
@pytest.mark.parametrize("avant,apres", [
    ("Ce que ça change pour vous : une phrase.\nTechnique", "Une phrase.\nTechnique"),
    ("**Un titre clair.**", "**Un titre clair (T-00000003).**"),
    ("## Non publié\n", ""),
    ("### Limites connues", "### Divers"),
    ("Ce que ça change pour vous : une phrase.\n\n### Historique", "Ce que ça change pour vous : S-00000004.\n\n### Historique"),
    ("## 0.1.0 — 2026-10-16", "## 0.1.0"),
    ("Technique : `outil` (T-00000001).", "Technique : a.\nTechnique : b."),
    # « pour vous » de 321 caractères ; 2e `## Non publié` ; entrée avant lui ; entrée hors `###`
    ("Ce que ça change pour vous : une phrase.\nTechnique", VOUS + "x" * (321 - len(VOUS)) + "\nTechnique"),
    ("## 0.2.0", "## Non publié\n\n## 0.2.0"),
    ("# Journal\n", "# Journal\n\n**Avant tout.**\n"),
    # (ancrés sous `## 0.2.0`, pas sous `## Non publié` : la règle « seule `### Contrat` » y tuerait le mutant
    # à la place de la règle visée)
    ("## 0.2.0 — à paraître\n\n### Corrigé",
     "## 0.2.0 — à paraître\n\n**Orphelin.**\nCe que ça change pour vous : x.\n\n### Corrigé"),
    # `### Historique` ailleurs que sous la version la plus ancienne
    ("## 0.2.0 — à paraître\n\n### Corrigé",
     "## 0.2.0 — à paraître\n\n### Historique\n\n**Vieux (T-00000001).**\n- puce\n\n### Corrigé"),
    # « à paraître » sur une autre version que la plus récente
    ("## 0.1.0 — 2026-10-16", "## 0.1.0 — à paraître"),
    # titre non gras ; version en double
    ("**Un titre clair.**", "Un titre clair."),
    ("## 0.1.0 — 2026-10-16", "## 0.1.0 — 2026-10-16\n\n### Ajouté\n\n**Bis.**\nCe que ça change pour vous : x.\n\n## 0.1.0 — 2026-10-16"),
    # coupe ratée : `à paraître` au-dessus de la même version datée
    ("## 0.2.0 — à paraître", "## 0.1.0 — à paraître"),
    # `## Non publié` présent une fois mais pas en premier (survivant des mutants du dev, lot A)
    ("# Journal\n", "# Journal\n\n## 0.3.0 — 2026-10-17\n\n### Ajouté\n\n**Avant.**\nCe que ça change pour vous : x.\n"),
    # écriture au fil de l'eau : une entrée bien formée sous `## Non publié` hors `### Contrat`
    ("## Non publié\n", "## Non publié\n\n### Ajouté\n\n**Au fil de l'eau.**\nCe que ça change pour vous : x.\n"),
    # coupe vide : une version datée sans aucune entrée
    ("## 0.1.0 — 2026-10-16\n\n### Limites connues\n\n**Une limite.**\nCe que ça change pour vous : une phrase.\n\n",
     "## 0.1.0 — 2026-10-16\n\n"),
    # versions hors de l'ordre décroissant
    ("## 0.2.0 — à paraître", "## 0.0.9 — à paraître"),
])
def test_un_mutant_rougit(avant, apres):
    assert ECHANTILLON.count(avant) == 1, avant
    assert fautes(ECHANTILLON.replace(avant, apres)) != []


def test_la_regle_admet_contrat_sous_non_publie_et_une_version_a_paraitre_vide():
    contrat = ECHANTILLON.replace(
        "## Non publié\n", "## Non publié\n\n### Contrat\n\n**Un retrait.**\nCe que ça change pour vous : x.\n")
    vide = re.sub(r"(?s)(## 0\.2\.0 — à paraître\n).*?(?=## 0\.1\.0)", r"\1\n", ECHANTILLON)
    assert contrat != ECHANTILLON and vide != ECHANTILLON and "**Un ajout.**" not in vide
    assert fautes(contrat) == [] and fautes(vide) == []


def test_la_borne_est_incluse():
    ligne = VOUS + "x" * (320 - len(VOUS))  # littéral : la borne promise, jamais relue de BORNE
    assert len(ligne) == 320
    assert fautes(ECHANTILLON.replace("Ce que ça change pour vous : une phrase.\nTechnique", ligne + "\nTechnique")) == []


def test_le_mode_script_rend_1_sur_un_fichier_fautif(tmp_path):
    p = tmp_path / "c.md"
    p.write_text(ECHANTILLON.replace("## Non publié\n", ""), encoding="utf-8")
    r = subprocess.run([sys.executable, __file__, str(p)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 1 and r.stdout.strip()
    p.write_text(ECHANTILLON, encoding="utf-8")
    r = subprocess.run([sys.executable, __file__, str(p)], capture_output=True, text=True, timeout=60)
    assert (r.returncode, r.stdout) == (0, "")


def historique_fige(octets: bytes) -> bool:
    """Vrai si `octets` sont exactement ceux de l'historique figé à la coupe."""
    return hashlib.sha256(octets).hexdigest() == EMPREINTE_HISTORIQUE


def test_l_historique_est_fige():
    assert historique_fige(HISTORIQUE.read_bytes())


def test_une_retouche_de_l_historique_rougit():
    assert not historique_fige(HISTORIQUE.read_bytes() + b" ")


def test_l_ancien_format_rougit():
    assert fautes(HISTORIQUE.read_text(encoding="utf-8")) != []


if __name__ == "__main__":
    _f = fautes(Path(sys.argv[1]).read_text(encoding="utf-8"))
    for x in _f:
        print(x)
    sys.exit(1 if _f else 0)
