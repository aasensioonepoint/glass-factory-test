"""Toute variable d'environnement PUBLIQUE des scanners est documentée.

POURQUOI CE FILET EXISTE — mesuré le 2026-09-09.

Les scanners de sécurité lisent 15 variables d'environnement réglables par le
projet adoptant. **Cinq n'étaient documentées NULLE PART** : `GITLEAKS_TIMEOUT`,
`SUBMODULE_SCAN_DEPTH`, `SCA_ROOT_ONLY`, `SCA_AUDIT_DEV_DEPS` et surtout
`SCA_GATE_LEVEL` — celle qui décide de ce qui **BLOQUE**. Un adoptant ne peut pas
régler un levier dont il ignore l'existence, et il n'avait aucun moyen de le
découvrir sans lire le shell.

CE QUE CE FILET FAIT, ET POURQUOI IL EST DÉRIVÉ. La liste des variables est
**extraite du code**, jamais recopiée ici : une liste tenue à la main se périme
au premier ajout, et c'est exactement comme ça que le trou s'est creusé. Ajoute
une variable publique à un scanner sans la documenter, et ce test rougit en la
nommant.

LA FRONTIÈRE PUBLIQUE / INTERNE, ET COMMENT ELLE EST DÉCIDÉE. Une variable est
PUBLIQUE si le script la lit avec un défaut (`${VAR:-…}`) sans jamais la calculer
lui-même. Elle est INTERNE si le script la **fabrique** pour se la passer à
lui-même — celles-là n'ont rien à faire dans une doc d'adoptant, et les exiger
serait du bruit qui ferait retirer le filet.

Deux formes trompent un classement naïf, et les deux sont traitées :
  * `VAR="${VAR:-défaut}"` — le script se relit avec un défaut. C'est l'idiome
    d'une variable PUBLIQUE, pas d'une interne, même si la ligne est une
    affectation.
  * `AUDIT_MODE="hook" AUDIT_EVENT="$X" audit …` — affectation en PRÉFIXE de
    commande. C'est une variable INTERNE, bien qu'aucune ligne ne commence par
    `AUDIT_EVENT=`. D'où l'ensemble d'exemptions nommées ci-dessous.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCANNERS = ROOT / ".agents" / "security"
DOC = ROOT / "README-SECURITY-SCAN-SETUP.md"

# L'espace de noms PUBLIC des scanners. Fermé et commenté : une variable hors de
# ces préfixes n'est pas un réglage d'adoptant.
PREFIXES = ("SEMGREP_", "GITLEAKS_", "SCA_", "NVD_", "SUBMODULE_")

# INTERNES portant malgré tout un préfixe public. Ensemble CLOS, chaque entrée
# avec sa raison — une exemption sans raison est une porte dérobée.
INTERNES: dict[str, str] = {
    "NVD_OFFLINE_ON": (
        "dérivée par sca-scan.sh à partir de NVD_OFFLINE ; le script se la passe "
        "à lui-même, l'adoptant règle NVD_OFFLINE"
    ),
    "NVD_OFFLINE_RAW_UNKNOWN": (
        "idem — valeur intermédiaire du diagnostic hors-ligne, jamais un réglage"
    ),
}


def scanners() -> list[Path]:
    """Les scanners EXÉCUTABLES, jamais leurs bancs : un banc fabrique des
    variables pour ses fixtures, elles ne sont pas des réglages d'adoptant."""
    return sorted(p for p in SCANNERS.glob("*.sh") if not p.name.endswith(".test.sh"))


def variables_publiques() -> dict[str, set[str]]:
    """{VAR: {fichiers}} — dérivé du code, jamais d'une liste tenue à la main."""
    lues: dict[str, set[str]] = {}
    fabriquees: set[str] = set()
    for path in scanners():
        texte = path.read_text(encoding="utf-8")
        for m in re.finditer(r"\$\{([A-Z][A-Z0-9_]{3,})(:?[-+])", texte):
            nom = m.group(1)
            if nom.startswith(PREFIXES):
                lues.setdefault(nom, set()).add(path.name)
        # Une AFFECTATION qui n'est PAS la relecture de soi-même => interne.
        for m in re.finditer(
            r"^\s*(?:export\s+)?([A-Z][A-Z0-9_]{3,})=(?!\"?\$\{\1[:\-+])", texte, re.M
        ):
            fabriquees.add(m.group(1))
    return {v: f for v, f in lues.items() if v not in fabriquees or v in _auto(v)}


def _auto(nom: str) -> set[str]:
    """Les fichiers où `nom` se relit lui-même (`VAR="${VAR:-…}"`) — la forme qui
    dit « publique » malgré une affectation."""
    trouves: set[str] = set()
    motif = re.compile(r"^\s*(?:export\s+)?%s=\"?\$\{%s[:\-+]" % (nom, nom), re.M)
    for path in scanners():
        if motif.search(path.read_text(encoding="utf-8")):
            trouves.add(path.name)
    return trouves


class SecurityEnvDocumentedTests(unittest.TestCase):
    def test_chaque_variable_publique_est_nommee_dans_la_doc(self) -> None:
        doc = DOC.read_text(encoding="utf-8")
        manquantes = []
        for nom, fichiers in sorted(variables_publiques().items()):
            if nom in INTERNES:
                continue
            if nom not in doc:
                manquantes.append(f"{nom} (lue par {', '.join(sorted(fichiers))})")
        self.assertEqual(
            manquantes,
            [],
            "Des variables d'environnement PUBLIQUES ne sont nommées nulle part "
            f"dans {DOC.name}. Un adoptant ne peut pas régler un levier dont il "
            "ignore l'existence — et c'est comme ça que SCA_GATE_LEVEL, qui "
            "décide de ce qui BLOQUE, est resté invisible. "
            f"Manquantes : {manquantes}",
        )

    def test_la_population_n_est_pas_vide(self) -> None:
        """NON-VACUITÉ (L-00000232) : un filet qui extrait zéro variable passe
        pour de bonnes raisons apparentes et ne mesure rien."""
        trouvees = variables_publiques()
        self.assertGreaterEqual(
            len(trouvees),
            10,
            f"extraction anormalement pauvre : {sorted(trouvees)} — les préfixes "
            "ont-ils changé, ou le répertoire des scanners a-t-il bougé ?",
        )

    def test_les_cinq_oubliees_sont_bien_couvertes(self) -> None:
        """CONTRÔLE POSITIF nommé. Ces cinq-là sont la RAISON de ce filet : elles
        n'étaient documentées nulle part le 2026-09-09. Les nommer ici fait que
        leur disparition de la doc rougit, même si l'extraction se cassait."""
        doc = DOC.read_text(encoding="utf-8")
        for nom in (
            "SCA_GATE_LEVEL",
            "GITLEAKS_TIMEOUT",
            "SUBMODULE_SCAN_DEPTH",
            "SCA_ROOT_ONLY",
            "SCA_AUDIT_DEV_DEPS",
        ):
            with self.subTest(variable=nom):
                self.assertIn(
                    nom, doc, f"{nom} a disparu de {DOC.name} — c'est l'un des "
                    "cinq trous que ce filet existe pour fermer"
                )

    def test_chaque_exemption_porte_sa_raison(self) -> None:
        """Une exemption sans raison est une porte dérobée ; une exemption dont
        la variable n'existe plus est une porte ouverte sur rien."""
        vues = set()
        for path in scanners():
            texte = path.read_text(encoding="utf-8")
            vues.update(re.findall(r"\$\{([A-Z][A-Z0-9_]{3,})[:\-+]", texte))
        for nom, raison in INTERNES.items():
            with self.subTest(variable=nom):
                self.assertTrue(raison.strip(), f"exemption sans raison : {nom}")
                self.assertIn(nom, vues, f"exemption périmée, {nom} n'est plus lue")


if __name__ == "__main__":
    unittest.main()
