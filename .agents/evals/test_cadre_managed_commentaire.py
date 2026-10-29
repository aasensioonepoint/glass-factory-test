"""`cadre.managed` en COMMENTAIRE — les trois porteurs, chacun avec son mutant (T-00000786).

Décision pilote S-00002846 : le marqueur est un COMMENTAIRE, jamais une clé
d'en-tête — des clés `cadre.*` dans un frontmatter rendent une déf Gemini
inchargeable (schéma strict de gemini-cli 0.57, S-00002854). Trois porteurs,
une grammaire (`cadre.<clé>: <valeur>`) :

* `.md` à frontmatter → `# cadre.…` juste avant le `---` fermant ;
* `.md` sans frontmatter → `<!-- cadre.… -->` en lignes 1-3 ;
* `.toml` → `# cadre.…` en lignes 1-3.

Ce banc tient ce qui est PROPRE à cette forme ; son aîné
`test_cadre_managed.py` tient, re-ciblés sur les trois porteurs, les témoins
T1-T28 qui survivent. Fixture TEXTE seule, aucune E/S, aucun skip kit-only :
il voyage comme son aîné (classe OUTILLAGE par le préfixe `.agents/evals/`).

Témoin par témoin, et le mutant du module qui le rend ROUGE (joués puis
révertés à la livraison de T-00000786) :

* T29 site exact : `poser` insère EXACTEMENT les trois lignes enveloppées au
  site du tableau, et rien d'autre — K1 (lignes sans `# ` au frontmatter),
  K3 (un `.md` sans frontmatter en reçoit un).
* T30 inertie : TOML, `tomllib.loads(poser(x)) == tomllib.loads(x)` ;
  frontmatter, ses lignes non-commentaire inchangées — K1.
* T31 la forme d'avant est REFUSÉE avec son remède (clés nues au frontmatter,
  table `[cadre]` réelle en TOML), une citation dans une chaîne reste du
  corps, et la borne écrite est épinglée : la clé racine `cadre.managed`
  sans en-tête (pointée ou en ligne, `true` ou `false`) n'est PAS lue, et
  `poser` la refuse (binôme final, critic-fable F1) — K2 (lecture qui ignore
  les clés nues), K8 (détection TOML retirée), R1 (refus de `poser` retiré).
* T32 régions bornées : `<!-- cadre.… -->` hors tête, `# cadre.…` hors tête ou
  dans une chaîne ⇒ NON_MARQUE, gardés à l'octet par `depouiller` et `poser` ;
  un frontmatter qui porte `name:`/`description:` n'est jamais refusé pour
  ces lignes — K4 (tête HTML non bornée), K5 (tête TOML non bornée).
* T33 un en-tête HTML devant un frontmatter REFERMÉ ⇒ refus ; devant un `---`
  jamais refermé ⇒ marqué — K6 (refus retiré).
* T34 un frontmatter vide est rendu à l'octet — K7 (ÉCART 1 rétabli).
* T35 la reprise d'UNE ligne, sur les trois porteurs ⇒ REPRIS, `poser` refuse.
* T36 un corps qui ouvre sur `# cadre.note` (TOML) ou `<!-- cadre.note -->`
  ⇒ refusé en LECTURE, `poser` ne rend rien.
* T37 une ligne de région de 40 000 caractères se lit — ou, à blancs
  intérieurs, se refuse — en < 0,5 s, en tête HTML comme en tête TOML — L1
  (expression paresseuse rétablie).

Passe de correction 2 (security-code-review S-00002881, exec-critic
S-00002887) :

* T38 la version LUE est tenue à la forme de la version posée (U+2028, NEL,
  `--!>`, blancs ⇒ refus), et l'enveloppe HTML refuse `-->` et `--!>` —
  P1 (lecture « non vide » seule), P2 (`--!>` oublié).
* T39 un entier TOML de plus de 4 300 chiffres est un refus, pas une panne
  — P3 (`except TOMLDecodeError` seul).
* T40 un corps TOML à `nan`/`inf` se marque et se relit INTACT — P4
  (flottants rechargés en `float`).
* T41 une reprise mal espacée (`#cadre.managed: false`, `<!--  cadre.…`)
  est refusée, jamais écrasée ; une clé hors des trois reste du corps —
  P5 (tête), P6 (frontmatter), P7 (clé non bornée à droite).

Passe de correction 3 (binôme de clôture : critic-opus F1, critic-fable F1/F2) :

* T42 une reprise MAL PLACÉE (hors région, dans la zone de reprise) est lue
  NON_MARQUE et `poser` la refuse en nommant sa place ; une citation hors
  zone, ou une ligne de frontmatter qui n'ouvre pas sur `#`/`<!--`, reste
  libre — Q1 (refus de `poser` retiré), Q3 (zone sans `lstrip`), Q4 (`match`
  au lieu de `search`), Q5 (frontmatter entier dans la zone), R2 (`=` refusé
  par `_REPRISE_LIBRE` : binôme final, critic-opus C1).
* T43 un frontmatter ajouté AU-DESSUS d'une tête HTML posée est un refus, à
  la ligne absolue ; séparée par une ligne vide, la tête est du corps — Q2
  (refus de `_region` retiré).
"""

from __future__ import annotations

import importlib.util
import re
import sys
import time
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVALS = Path(__file__).resolve().parent
# Le paquet `cadre` où qu'il vive, chargé par chemin par `vendor_paths` (S-01M5BXT85VP4JBBMXVXR9STP5F).
_SPEC_VENDOR = importlib.util.spec_from_file_location(
    "_managed_commentaire_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
assert _SPEC_VENDOR is not None and _SPEC_VENDOR.loader is not None
_VENDOR = importlib.util.module_from_spec(_SPEC_VENDOR)
sys.modules[_SPEC_VENDOR.name] = _VENDOR
_SPEC_VENDOR.loader.exec_module(_VENDOR)
_VENDOR.charger_paquet(ROOT, "cadre")
if str(EVALS) not in sys.path:
    sys.path.insert(0, str(EVALS))

import cadre  # noqa: E402
from cadre.managed import (  # noqa: E402
    Etat,
    Marqueur,
    MarqueurIllisible,
    depouiller,
    empreinte,
    lire,
    poser,
    verifier,
)

from cadre_managed_fixtures import (  # noqa: E402
    MD,
    MD_SANS_FRONTMATTER,
    MD_VIERGE,
    PORTEURS,
    TOML_CHAINE,
    TOML_VIERGE,
    TT,
    ZEROS,
    fm,
    html,
    tete,
)

#: Les quatre entrées publiques, jouées ensemble par les refus.
ENTREES = (lire, verifier, depouiller, poser)


def _lignes_du_frontmatter(texte: str) -> list[str]:
    """Les lignes ENTRE les deux `---` d'un texte qui ouvre sur un frontmatter."""
    lignes = texte.split("\n")
    return lignes[1:lignes.index("---", 1)]


class CommentaireSiteTests(unittest.TestCase):
    """T29, T30 — où `poser` écrit, et que ce qu'il écrit est inerte."""

    def test_T29_poser_insere_exactement_les_trois_lignes_au_site_du_tableau(self):
        version = cadre.__version__
        for nom, forme, vierge in PORTEURS:
            with self.subTest(porteur=nom):
                lignes = ["cadre.managed: true", f'cadre.version: "{version}"',
                          f'cadre.checksum: "{empreinte(vierge)}"']
                corps = vierge.split("\n")
                if nom == "frontmatter":
                    fermeture = corps.index("---", 1)
                    attendu = corps[:fermeture] + [f"# {l}" for l in lignes] + corps[fermeture:]
                elif nom == "html":
                    attendu = [html(l) for l in lignes] + corps
                else:
                    attendu = [f"# {l}" for l in lignes] + corps
                rendu = poser(vierge, forme)
                self.assertEqual(rendu, "\n".join(attendu), "site ou enveloppe inexacts")
                self.assertEqual(len(rendu.split("\n")) - len(corps), 3, "pas exactement trois lignes")
        # Un `.md` sans frontmatter n'en reçoit JAMAIS un (K3) : S-00002854,
        # un frontmatter créé déplacerait le corps et changerait ce que l'hôte charge.
        rendu = poser(MD_SANS_FRONTMATTER, MD)
        self.assertNotIn("---", rendu)
        self.assertTrue(rendu.startswith(html("cadre.managed: true") + "\n"))

    def test_T30_l_en_tete_est_inerte_pour_le_parseur_de_chaque_porteur(self):
        """TOML : un commentaire, que `tomllib` ignore — la structure lue est
        identique avant et après pose. Frontmatter : un commentaire YAML — les
        lignes qui ne sont pas des commentaires sont inchangées, dans l'ordre,
        et le frontmatter ne gagne que les trois lignes `# `."""
        for corps in (TOML_VIERGE, TOML_CHAINE, "", 'name = "x"',
                      '[a]\nb = 1\n\n[[c]]\nd = "e"\n', "# note\nx = 1\n"):
            with self.subTest(toml=corps[:16]):
                rendu = poser(corps, TT)
                self.assertEqual(tomllib.loads(rendu), tomllib.loads(corps))
                self.assertTrue(rendu.endswith(corps), "le corps TOML n'est pas gardé à l'octet")
        for texte in (MD_VIERGE, fm("name: x", "description: y", 'tools: ["read_file"]'),
                      "---\n---\nx\n", fm("name: x", "# un commentaire d'auteur")):
            with self.subTest(frontmatter=texte[:16]):
                rendu = poser(texte, MD)
                avant, apres = _lignes_du_frontmatter(texte), _lignes_du_frontmatter(rendu)
                ajoutees = [l for l in apres if l.startswith("# cadre.")]
                self.assertEqual(len(ajoutees), 3)
                self.assertEqual([l for l in apres if l not in ajoutees], avant)
                self.assertTrue(all(l.startswith("# ") for l in ajoutees))


class CommentaireFormeDAvantTests(unittest.TestCase):
    """T31 — la forme d'avant (clés d'en-tête) est refusée, jamais lue."""

    def test_T31_la_forme_d_avant_est_refusee_avec_son_remede(self):
        remede = r"forme d'avant, refusée \(S-00002846\).*écrire `# cadre\.managed: …`"
        cas = {
            "cles nues au frontmatter": (MD, fm(
                "cadre.managed: true", 'cadre.version: "1"', f'cadre.checksum: "{ZEROS}"')),
            "une cle nue parmi les commentaires": (MD, fm(
                "# cadre.managed: true", 'cadre.version: "1"', f'# cadre.checksum: "{ZEROS}"')),
            "table [cadre] reelle": (TT, TOML_VIERGE + (
                f'\n[cadre]  # cadre.managed\nmanaged = true\nversion = "1"\nchecksum = "{ZEROS}"\n')),
            "reprise [cadre] d'une ligne": (TT, TOML_VIERGE + "\n[cadre]\nmanaged = false\n"),
            "en-tete quote simple": (TT, "['cadre']\nmanaged = true\n"),
            "table d'avant sous une tete commentaire": (TT, (
                f'# cadre.managed: true\n# cadre.version: "1"\n# cadre.checksum: "{ZEROS}"\n'
                "[cadre]\nmanaged = true\n")),
        }
        for nom, (forme, texte) in cas.items():
            for fonction in ENTREES:
                with self.subTest(cas=nom, fonction=fonction.__name__):
                    with self.assertRaisesRegex(MarqueurIllisible, remede):
                        fonction(texte, forme)
        # Une citation DANS une chaîne reste du corps : la vraie structure n'a
        # pas de table `cadre`, et la tête n'ouvre pas sur `# cadre.`.
        self.assertIn("[cadre]", tomllib.loads(TOML_CHAINE)["developer_instructions"])
        self.assertIsNone(lire(TOML_CHAINE, TT))
        self.assertIs(verifier(TOML_CHAINE, TT), Etat.NON_MARQUE)
        self.assertEqual(depouiller(TOML_CHAINE, TT), TOML_CHAINE)
        self.assertIs(verifier(poser(TOML_CHAINE, TT), TT), Etat.INTACT)
        # Une table `[cadre]` SANS `managed` n'est pas la forme d'avant : du corps.
        self.assertIsNone(lire(TOML_VIERGE + '\n[cadre]\nnote = "x"\n', TT))
        # BORNE ÉCRITE, épinglée (réserve A-C5) : la clé racine `cadre.managed`
        # sans en-tête `[cadre]` — pointée ou en ligne, `true` comme `false` —
        # n'est PAS lue (NON_MARQUE), et `poser` les refuse (binôme final,
        # critic-fable F1 : un `false` y était marqué `true` par-dessus). Si ce
        # témoin rougit, la borne a bougé : mettre la docstring à jour aussi.
        cles = {
            "pointee true": 'cadre.managed = true\ncadre.version = "1"\n' + TOML_VIERGE,
            "pointee false": "cadre.managed = false\n" + TOML_VIERGE,
            "en ligne false": "cadre = { managed = false }\n" + TOML_VIERGE,
        }
        for nom, texte in cles.items():
            with self.subTest(cle=nom):
                self.assertIn("managed", tomllib.loads(texte)["cadre"])
                self.assertIsNone(lire(texte, TT))
                self.assertIs(verifier(texte, TT), Etat.NON_MARQUE)
                with self.assertRaisesRegex(MarqueurIllisible, "clé TOML"):
                    poser(texte, TT)
        # La même clé sous UNE AUTRE table, ou l'entrée de script `cadre =
        # "cadre.cli:main"` d'un pyproject, n'est pas la clé racine : posées.
        for texte in (TOML_VIERGE + "\n[t]\ncadre.managed = false\n",
                      '[project.scripts]\ncadre = "cadre.cli:main"\n'):
            with self.subTest(libre=texte[-24:]):
                self.assertIs(verifier(poser(texte, TT), TT), Etat.INTACT)


class CommentaireRegionsTests(unittest.TestCase):
    """T32, T33 — les régions lues sont bornées, et l'en-tête HTML ne précède
    jamais un frontmatter refermé."""

    def test_T32_hors_de_la_region_rien_n_est_lu_ni_retire(self):
        trois_html = [html("cadre.managed: true"), html('cadre.version: "1"'),
                      html(f'cadre.checksum: "{ZEROS}"')]
        trois_diese = ["# cadre.managed: true", '# cadre.version: "1"', f'# cadre.checksum: "{ZEROS}"']
        cas = {
            "html apres une ligne de corps": (MD, tete("# Titre", *trois_html)),
            "html apres une ligne vide": (MD, tete("", *trois_html)),
            "html dans le corps d'un md a frontmatter": (MD, fm("name: x", corps="\n" + "\n".join(trois_html) + "\n")),
            "diese dans le corps d'un md a frontmatter": (MD, fm("name: x", corps="\n" + "\n".join(trois_diese) + "\n")),
            "diese indente au frontmatter": (MD, fm("name: x", "  # cadre.managed: true")),
            "diese apres une ligne de corps toml": (TT, tete('name = "x"', *trois_diese, corps="")),
            "diese apres une ligne vide toml": (TT, tete("", *trois_diese, corps=TOML_VIERGE)),
            "diese dans une chaine toml": (TT, TOML_CHAINE),
        }
        for nom, (forme, texte) in cas.items():
            with self.subTest(cas=nom):
                self.assertIsNone(lire(texte, forme))
                self.assertIs(verifier(texte, forme), Etat.NON_MARQUE)
                self.assertEqual(depouiller(texte, forme), texte, "une ligne hors région a été retirée")
                rendu = poser(texte, forme)
                self.assertEqual(depouiller(rendu, forme), texte)
                self.assertIs(verifier(rendu, forme), Etat.INTACT)
        # Réserve A-C3 : seules les lignes qui OUVRENT sur `# cadre.` ou `cadre.`
        # sont jugées ; `name:`, `description:`, un commentaire d'auteur, un
        # `#cadre.` collé à une clé HORS des trois ne le sont jamais, même s'ils
        # citent le jeton (collé à une des trois clés, c'est un refus : T41).
        libre = fm("name: cadre.managed", "description: parle de cadre.managed: true",
                   'tools: ["read_file"]', "# un commentaire", "#cadre.colle: x")
        self.assertIsNone(lire(libre, MD))
        self.assertIs(verifier(poser(libre, MD), MD), Etat.INTACT)

    def test_T33_un_en_tete_html_devant_un_frontmatter_referme_est_refuse(self):
        """S-00002854 : une ligne AVANT le premier `---` casse le chargeur de
        frontmatter de l'hôte. Devant un `---` jamais refermé (une règle
        horizontale), l'en-tête HTML est le marqueur, et `poser` l'écrit."""
        devant = tete(html("cadre.managed: true"), html('cadre.version: "1"'),
                      html(f'cadre.checksum: "{ZEROS}"'), corps="---\nname: x\n---\nCorps.\n")
        reprise_devant = tete(html("cadre.managed: false"), corps="---\nname: x\n---\n")
        for nom, texte in (("marqueur", devant), ("reprise", reprise_devant)):
            for fonction in ENTREES:
                with self.subTest(cas=nom, fonction=fonction.__name__):
                    with self.assertRaisesRegex(MarqueurIllisible, "précèdent un frontmatter refermé"):
                        fonction(texte, MD)
        regle = "---\nCorps sans fermeture.\n"
        rendu = poser(regle, MD)
        self.assertTrue(rendu.startswith(html("cadre.managed: true") + "\n"))
        self.assertTrue(rendu.endswith(regle))
        self.assertEqual(lire(rendu, MD).checksum, empreinte(regle))
        self.assertIs(verifier(rendu, MD), Etat.INTACT)


class CommentaireRepriseEtCorpsTests(unittest.TestCase):
    """T34–T36 — frontmatter vide, reprise d'une ligne, corps qui ouvre sur
    `cadre.`."""

    def test_T34_un_frontmatter_vide_est_rendu_a_l_octet(self):
        """L'ÉCART 1 d'avant retirait les délimiteurs d'un frontmatter vidé
        (parce que `poser` en créait un). `poser` n'en crée plus : le
        frontmatter vide est un frontmatter, rendu INTACT et tel quel."""
        for texte in ("---\n---\nx", "---\n---\n", "---\n---\n---\n---\nx\n"):
            with self.subTest(texte=texte):
                rendu = poser(texte, MD)
                self.assertEqual(depouiller(rendu, MD), texte)
                self.assertIs(verifier(rendu, MD), Etat.INTACT)
                self.assertEqual(_lignes_du_frontmatter(rendu)[0], "# cadre.managed: true")

    def test_T35_la_reprise_d_une_ligne_sur_les_trois_porteurs(self):
        """S-00002731, dans la forme commentaire : UNE ligne
        `# cadre.managed: false` (ou `<!-- cadre.managed: false -->` en tête
        d'un `.md` sans frontmatter) suffit — REPRIS, et `poser` refuse."""
        repris = {}
        lignes = MD_VIERGE.split("\n")
        fermeture = lignes.index("---", 1)
        repris["frontmatter"] = "\n".join(lignes[:fermeture] + ["# cadre.managed: false"] + lignes[fermeture:])
        repris["html"] = html("cadre.managed: false") + "\n" + MD_SANS_FRONTMATTER
        repris["toml"] = "# cadre.managed: false\n" + TOML_VIERGE
        for nom, forme, vierge in PORTEURS:
            texte = repris[nom]
            with self.subTest(porteur=nom):
                self.assertEqual(lire(texte, forme), Marqueur(version=None, checksum=None, managed=False))
                self.assertIs(verifier(texte, forme), Etat.REPRIS)
                self.assertEqual(depouiller(texte, forme), vierge, "la reprise part, le corps reste")
                with self.assertRaisesRegex(MarqueurIllisible, "repris"):
                    poser(texte, forme)

    def test_T36_un_corps_qui_ouvre_sur_cadre_ne_recoit_pas_de_marqueur(self):
        """Borne écrite : sa première ligne entre dans la suite de tête et y
        est jugée. Le refus sort en LECTURE, avant tout rendu : `poser` ne
        rend rien. Un corps qui ouvre sur un AUTRE commentaire est libre."""
        refuses = {
            "toml # cadre.note": (TT, "# cadre.note\n" + TOML_VIERGE),
            "toml # cadre.note: libre": (TT, "# cadre.note: libre\n" + TOML_VIERGE),
            "html cadre.note": (MD, "<!-- cadre.note -->\n" + MD_SANS_FRONTMATTER),
            "html cadre.note: libre": (MD, html("cadre.note: libre") + "\n" + MD_SANS_FRONTMATTER),
        }
        for nom, (forme, texte) in refuses.items():
            with self.subTest(cas=nom):
                with self.assertRaises(MarqueurIllisible):
                    lire(texte, forme)
                rendu = None
                with self.assertRaises(MarqueurIllisible):
                    rendu = poser(texte, forme)
                self.assertIsNone(rendu, "poser a rendu un texte")
        for forme, texte in ((TT, "# note: libre\n" + TOML_VIERGE),
                             (MD, "<!-- note -->\n" + MD_SANS_FRONTMATTER)):
            with self.subTest(libre=texte[:12]):
                self.assertIs(verifier(poser(texte, forme), forme), Etat.INTACT)


class CommentaireLineariteTests(unittest.TestCase):
    """T37 — les enveloppes HTML et TOML se lisent en temps linéaire."""

    def test_T37_une_ligne_de_region_de_40_000_caracteres_se_lit_vite(self):
        """L'enveloppe est retirée à l'octet (`removeprefix`/`removesuffix`),
        jamais par une expression à quantificateur paresseux devant `-->` —
        le rebroussement quadratique mesuré par T16 (3 s) ne doit pas revenir
        par la porte HTML. Même seuil que T16. Depuis la passe 2, la valeur à
        blancs intérieurs est REFUSÉE (version lue hors forme, T38) après que
        l'expression l'a parcourue en entier : c'est le refus qui se
        chronomètre (mutant L1 ⇒ rouge) ; une version longue VALIDE se relit
        entière."""
        def cas(version: str) -> dict[str, tuple]:
            return {
                "html": (MD, tete(html("cadre.managed: true"), html(f"cadre.version: {version}"),
                                  html(f'cadre.checksum: "{ZEROS}"'))),
                "toml": (TT, tete("# cadre.managed: true", f"# cadre.version: {version}",
                                  f'# cadre.checksum: "{ZEROS}"', corps=TOML_VIERGE)),
            }

        for nom, (forme, texte) in cas("a" + " " * 40_000 + "b").items():
            with self.subTest(porteur=nom, cas="blancs interieurs, refus"):
                debut = time.perf_counter()
                with self.assertRaisesRegex(MarqueurIllisible, "hors de la forme"):
                    lire(texte, forme)
                duree = time.perf_counter() - debut
                self.assertLess(duree, 0.5, f"refus en {duree:.2f} s : rebroussement")
        longue = "1." + "0" * 40_000
        for nom, (forme, texte) in cas(longue).items():
            with self.subTest(porteur=nom, cas="version longue valide"):
                debut = time.perf_counter()
                self.assertEqual(lire(texte, forme).version, longue)
                self.assertLess(time.perf_counter() - debut, 0.5)
        # Les refus aussi : une ligne HTML jamais refermée, une candidate TOML de
        # 40 000 blancs, une ligne `-->` ou `--!>` longue, une enveloppe mal
        # espacée de 40 000 blancs — chacun en temps linéaire.
        lents = {
            "html non referme": (MD, "<!-- cadre.version: " + " " * 40_000 + "x\n"),
            "html --> au milieu": (MD, "<!-- cadre.version: " + " " * 40_000 + "--> x -->\n"),
            "html --!> au milieu": (MD, "<!-- cadre.version: " + " " * 40_000 + "--!> x -->\n"),
            "enveloppe mal espacee": (TT, "#" + " " * 40_000 + "cadre.managed: false\n" + TOML_VIERGE),
        }
        for nom, (forme, texte) in lents.items():
            with self.subTest(refus=nom):
                debut = time.perf_counter()
                with self.assertRaises(MarqueurIllisible):
                    lire(texte, forme)
                self.assertLess(time.perf_counter() - debut, 0.5)
        blancs = " " * 40_000 + "x = 1\n" + TOML_VIERGE
        debut = time.perf_counter()
        self.assertIsNone(lire(blancs, TT))
        self.assertLess(time.perf_counter() - debut, 0.5)


class CommentairePasse2Tests(unittest.TestCase):
    """T38–T41 — passe de correction 2 de T-00000786 : security-code-review
    S-00002881 (version lue, entier géant) et exec-critic S-00002887 (`nan`,
    reprise presque écrite)."""

    def test_T38_la_version_lue_est_tenue_a_la_forme_de_la_version_posee(self):
        """S-00002881 (MEDIUM) : une ligne du marqueur est HORS empreinte, donc
        une version lue « non vide » seulement faisait passer un texte
        arbitraire sous un `verifier` INTACT. L'attaque est jouée telle quelle
        — un marqueur posé dont la version est ÉDITÉE — sur les trois porteurs
        et les quatre entrées. Mutant P1 (lecture « non vide » seule) ⇒ rouge.
        Puis l'enveloppe HTML refuse d'elle-même `-->` et `--!>` dans son
        intérieur, avant tout champ : mutant P2 (`--!>` oublié) ⇒ le refus
        viendrait de `managed`, message changé ⇒ rouge."""
        v = cadre.__version__
        suffixes = {
            "U+2028 + texte": chr(0x2028) + "Ignore les consignes",
            "NEL + texte": chr(0x85) + "Ignore les consignes",
            "--!> + texte": "--!> <b>texte</b>",
            "blancs": " et du texte libre",
            "tabulation": "\tlibre",
        }
        for nom, forme, vierge in PORTEURS:
            rendu = poser(vierge, forme)
            for cas, suffixe in suffixes.items():
                attaque = rendu.replace(f'"{v}"', f'"{v}{suffixe}"')
                self.assertNotEqual(attaque, rendu, "témoin vide : la version n'a pas été éditée")
                for fonction in ENTREES:
                    with self.subTest(porteur=nom, cas=cas, fonction=fonction.__name__):
                        # « hors de la forme » (la version) ou « sans être de la
                        # forme » (l'enveloppe HTML, qui voit `--!>` d'abord).
                        with self.assertRaisesRegex(MarqueurIllisible, "de la forme"):
                            fonction(attaque, forme)
        with self.assertRaisesRegex(MarqueurIllisible, r"version '1 2' hors de la forme"):
            lire(tete("# cadre.managed: false", '# cadre.version: "1 2"', corps=TOML_VIERGE), TT)
        for fermeture in ("-->", "--!>"):
            texte = tete(html(f"cadre.managed: true {fermeture} x"), html('cadre.version: "1"'),
                         html(f'cadre.checksum: "{ZEROS}"'))
            for fonction in ENTREES:
                with self.subTest(fermeture=fermeture, fonction=fonction.__name__):
                    with self.assertRaisesRegex(
                            MarqueurIllisible, r"sans être de la forme `<!-- cadre\.<clé>: <valeur> -->`"):
                        fonction(texte, MD)

    def test_T39_un_entier_de_plus_de_4300_chiffres_est_un_refus_pas_une_panne(self):
        """S-00002881 (MEDIUM) : `tomllib` laisse remonter le `ValueError` NU de
        la limite de conversion des entiers. Précondition d'abord, comme T14 :
        si la limite est levée (`PYTHONINTMAXSTRDIGITS=0`), le témoin rougit au
        lieu de passer à vide. Avec candidate `[cadre]` : refus sur les quatre
        entrées (la lecture charge). Sans : la lecture ne charge jamais, et
        `poser`, qui charge le corps, refuse. Mutant P3 (`except
        TOMLDecodeError` seul) ⇒ rouge."""
        geant = "1" * max(5000, sys.get_int_max_str_digits() + 1)
        avec = f"[cadre]\nmanaged = true\nversion = {geant}\n"
        sans = f"x = {geant}\n"
        for texte in (avec, sans):
            with self.assertRaisesRegex(ValueError, "4300|limit") as brut:
                tomllib.loads(texte)
            self.assertNotIsInstance(brut.exception, tomllib.TOMLDecodeError, "précondition : ValueError NU")
        for fonction in ENTREES:
            with self.subTest(candidate="[cadre]", fonction=fonction.__name__):
                with self.assertRaisesRegex(MarqueurIllisible, "TOML illisible"):
                    fonction(avec, TT)
        self.assertIsNone(lire(sans, TT))
        self.assertIs(verifier(sans, TT), Etat.NON_MARQUE)
        self.assertEqual(depouiller(sans, TT), sans)
        rendu = None
        with self.assertRaisesRegex(MarqueurIllisible, "corps : TOML illisible"):
            rendu = poser(sans, TT)
        self.assertIsNone(rendu, "poser a rendu un texte")

    def test_T40_un_corps_toml_a_nan_ou_inf_se_marque_et_se_relit_intact(self):
        """exec-critic S-00002887 : l'égalité de chargement de `poser` comparait
        des flottants, et `nan != nan` refusait un corps valide. Chargés en
        TEXTE (`parse_float=str`), ils se comparent : le corps se marque, se
        relit INTACT, et se dépouille à l'octet. Mutant P4 (flottants rechargés
        en `float`) ⇒ rouge."""
        for corps in ("x = nan\n", "x = +nan\ny = -inf\n", "[t]\nv = [nan, inf, 1.5]\n",
                      TOML_VIERGE + "\n[f]\nz = -nan\n"):
            with self.subTest(corps=corps[:20]):
                rendu = poser(corps, TT)
                self.assertTrue(rendu.endswith(corps), "le corps TOML n'est pas gardé à l'octet")
                self.assertEqual(depouiller(rendu, TT), corps)
                self.assertIs(verifier(rendu, TT), Etat.INTACT)
                self.assertEqual(tomllib.loads(rendu, parse_float=str),
                                 tomllib.loads(corps, parse_float=str))

    def test_T41_une_reprise_presque_ecrite_est_refusee_jamais_ecrasee(self):
        """exec-critic S-00002887, rouvrant la garde S-00001602 : une reprise
        mal espacée (`#cadre.managed: false`) était lue NON_MARQUE, et `poser`
        la marquait `true` par-dessus — la décision de l'adoptant écrasée. Dans
        la région, l'enveloppe mal espacée d'une des trois clés (aucun blanc,
        plusieurs, une tabulation) est un refus qui nomme la forme exacte, sur
        les trois porteurs et les quatre entrées. Mutants P5 (tête) et P6
        (frontmatter) ⇒ rouges. Une clé HORS des trois ainsi enveloppée, une
        ligne hors région restent du corps : mutant P7 (clé non bornée à
        droite) ⇒ rouge. Une reprise INDENTÉE n'est pas lue non plus, mais
        `poser` la refuse (mal placée) : T42."""
        lignes_md = MD_VIERGE.split("\n")
        fermeture = lignes_md.index("---", 1)

        def au_frontmatter(ligne: str) -> str:
            return "\n".join(lignes_md[:fermeture] + [ligne] + lignes_md[fermeture:])

        cas = {}
        for cle, valeur in (("managed", "false"), ("version", '"1"'), ("checksum", f'"{ZEROS}"')):
            for blancs in ("", "  ", "\t", " \t"):
                ligne = f"cadre.{cle}: {valeur}"
                diese, attendu_diese = f"#{blancs}{ligne}", f"# cadre.{cle}: …"
                cas[f"frontmatter {diese[:12]!r}"] = (MD, au_frontmatter(diese), attendu_diese)
                cas[f"toml {diese[:12]!r}"] = (TT, diese + "\n" + TOML_VIERGE, attendu_diese)
                cas[f"html {blancs!r} {cle}"] = (MD, f"<!--{blancs}{ligne} -->\n" + MD_SANS_FRONTMATTER,
                                                 f"<!-- cadre.{cle}: … -->")
        cas["toml apres une ligne exacte"] = (
            TT, '# cadre.managed: true\n#cadre.version: "1"\n' + TOML_VIERGE, "# cadre.version: …")
        cas["frontmatter jamais referme"] = (MD, "---\n#cadre.managed: false\n# Corps\n", None)
        for nom, (forme, texte, attendu) in cas.items():
            motif = "jamais refermé" if attendu is None else (
                r"enveloppe malformée de cadre\.\w+, écrire `" + re.escape(attendu) + "`")
            for fonction in ENTREES:
                with self.subTest(cas=nom, fonction=fonction.__name__):
                    with self.assertRaisesRegex(MarqueurIllisible, motif):
                        fonction(texte, forme)
        rendu = None
        with self.assertRaises(MarqueurIllisible):
            rendu = poser("#cadre.managed: false\n" + TOML_VIERGE, TT)
        self.assertIsNone(rendu, "poser a rendu un texte : la reprise serait écrasée")
        libres = {
            "frontmatter #cadre.colle": (MD, au_frontmatter("#cadre.colle: x")),
            "frontmatter #cadre.managedx": (MD, au_frontmatter("#cadre.managedx: false")),
            "frontmatter #cadre.managed.note": (MD, au_frontmatter("#cadre.managed.note: x")),
            "toml #cadre.managed_old": (TT, "#cadre.managed_old: false\n" + TOML_VIERGE),
            "toml #  cadre.note": (TT, "#  cadre.note: x\n" + TOML_VIERGE),
            "html <!--cadre.versions": (MD, "<!--cadre.versions: x -->\n" + MD_SANS_FRONTMATTER),
            "toml hors region": (TT, TOML_VIERGE + "#cadre.managed: false\n"),
        }
        for nom, (forme, texte) in libres.items():
            with self.subTest(libre=nom):
                self.assertIsNone(lire(texte, forme))
                rendu = poser(texte, forme)
                self.assertEqual(depouiller(rendu, forme), texte)
                self.assertIs(verifier(rendu, forme), Etat.INTACT)


class CommentairePasse3Tests(unittest.TestCase):
    """T42, T43 — passe de correction 3 de T-00000786 : binôme de clôture
    (critic-opus F1, critic-fable F1/F2)."""

    def test_T42_une_reprise_mal_placee_n_est_jamais_ecrasee(self):
        """critic-opus F1 : sept reprises hors région étaient lues NON_MARQUE,
        puis marquées `true` par `poser` — la décision de l'adoptant écrasée.
        Elles restent NON_MARQUE à la lecture (aucun refus de `lire` : une doc
        titrée `# cadre.managed — …` doit rester lisible), mais `poser` les
        refuse en nommant la forme À SA PLACE, et ne rend rien. Le cas
        critic-fable F2 (`# cadre.managed: false` en ligne 1 d'un `.md` sans
        frontmatter) est le premier : un seul chemin de refus, qui nomme
        `<!-- cadre.managed: false -->`. Mutants Q1 (refus retiré), Q3 (zone
        sans `lstrip`), Q4 (`match`) ⇒ rouges ; Q5 (frontmatter entier dans la
        zone) ⇒ la ligne `description:` libre rougit."""
        lignes_md = MD_VIERGE.split("\n")
        fermeture = lignes_md.index("---", 1)

        def au_frontmatter(ligne: str) -> str:
            return "\n".join(lignes_md[:fermeture] + [ligne] + lignes_md[fermeture:])

        diese, balise = "# cadre.managed: false", html("cadre.managed: false")
        cas = {
            "F2 diese en ligne 1 d'un md sans frontmatter": (MD, f"{diese}\n{MD_SANS_FRONTMATTER}", balise),
            "ligne vide avant la balise": (MD, f"\n{balise}\n{MD_SANS_FRONTMATTER}", balise),
            "titre avant la balise": (MD, f"# Titre\n{balise}\n\nCorps.\n", balise),
            "balise dans le frontmatter": (MD, au_frontmatter(balise), diese),
            "diese indente au frontmatter": (MD, au_frontmatter("  " + diese), diese),
            "diese colle indente au frontmatter": (MD, au_frontmatter("  #cadre.managed: false"), diese),
            "toml SPDX puis reprise": (TT, f"# SPDX-License-Identifier: MIT\n{diese}\n{TOML_VIERGE}", diese),
            "toml diese + blanc insecable": (TT, f"#{chr(0xA0)}cadre.managed: false\n{TOML_VIERGE}", diese),
            "toml indente": (TT, f"  {diese}\n{TOML_VIERGE}", diese),
            "false quote": (TT, f'# SPDX\n# cadre.managed: "false"\n{TOML_VIERGE}', diese),
            "toml egal sous SPDX": (TT, f"# SPDX\n# cadre.managed = false\n{TOML_VIERGE}", diese),
            "False capitalise, indente": (MD, au_frontmatter("  # cadre.managed: False"), diese),
            "balise sous le --- fermant, apres une ligne vide": (MD, f"---\nname: x\n---\n\n{balise}\n", diese),
        }
        for nom, (forme, texte, remede) in cas.items():
            with self.subTest(cas=nom):
                self.assertIsNone(lire(texte, forme))
                self.assertIs(verifier(texte, forme), Etat.NON_MARQUE)
                self.assertEqual(depouiller(texte, forme), texte)
                rendu = None
                with self.assertRaisesRegex(MarqueurIllisible,
                                            "reprise mal placée, ligne .*" + re.escape(f"`{remede}`")):
                    rendu = poser(texte, forme)
                self.assertIsNone(rendu, "poser a rendu un texte : la reprise serait écrasée")
        libres = {
            "description qui cite la reprise": (MD, au_frontmatter(
                'description: "une reprise s\'écrit cadre.managed: false"')),
            "titre qui nomme le marqueur": (MD, "# cadre.managed — le marqueur\n\nCorps.\n"),
            "reprise apres un paragraphe": (MD, f"# Titre\n\nUn paragraphe.\n\n{diese}\n"),
            "toml apres une cle": (TT, f"{TOML_VIERGE}{diese}\n"),
            "managedx indente": (MD, au_frontmatter("  # cadre.managedx: false")),
            "falsely indente": (MD, au_frontmatter("  # cadre.managed: falsely")),
        }
        for nom, (forme, texte) in libres.items():
            with self.subTest(libre=nom):
                self.assertIsNone(lire(texte, forme))
                rendu = poser(texte, forme)
                self.assertEqual(depouiller(rendu, forme), texte)
                self.assertIs(verifier(rendu, forme), Etat.INTACT)

    def test_T43_un_frontmatter_ajoute_au_dessus_d_une_tete_html_est_refuse(self):
        """critic-fable F1 : un frontmatter ajouté au-dessus d'un marqueur posé
        en tête HTML était lu NON_MARQUE (MODIFIE avant T-00000786) — un
        fichier modifié échappait à `--upgrade`. Juste sous le `---` fermant
        d'un frontmatter qui ne porte pas de marqueur, la tête est un refus sur
        les quatre entrées, à la ligne ABSOLUE. Mutant Q2 (refus retiré) ⇒
        rouge. Bornes épinglées : séparée par une ligne vide, la tête est du
        corps ; sous un frontmatter déjà marqué, elle est du corps (MODIFIE)."""
        pose = poser(MD_SANS_FRONTMATTER, MD)
        cas = {
            "marqueur pose": "---\nname: x\n---\n" + pose,
            "reprise": f"---\nname: x\n---\n{html('cadre.managed: false')}\n{MD_SANS_FRONTMATTER}",
            "frontmatter vide": "---\n---\n" + pose,
        }
        for nom, texte in cas.items():
            for fonction in ENTREES:
                with self.subTest(cas=nom, fonction=fonction.__name__):
                    with self.assertRaisesRegex(
                            MarqueurIllisible, r"juste sous le `---` fermant \(ligne \d+\) — un frontmatter a été ajouté"):
                        fonction(texte, MD)
        with self.assertRaisesRegex(MarqueurIllisible, r"\(ligne 4\)"):
            lire(cas["marqueur pose"], MD)
        with self.assertRaisesRegex(MarqueurIllisible, r"en-tête HTML, ligne 4 : .* enveloppe malformée"):
            lire("---\nname: x\n---\n<!--cadre.managed: false -->\n# T\n", MD)
        separe = "---\nname: x\n---\n\n" + pose
        self.assertIsNone(lire(separe, MD))
        self.assertIs(verifier(poser(separe, MD), MD), Etat.INTACT)
        deja = poser("---\nname: x\n---\n", MD) + pose
        self.assertIs(verifier(deja, MD), Etat.MODIFIE)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
