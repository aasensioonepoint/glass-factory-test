"""`cadre.managed` — la primitive du marqueur des fichiers générés (T-00000735).

Ce banc exerce `cadre/managed.py` (le paquet où qu'il vive : `.agents/vendor/cadre/`
d'abord, `src/cadre/` sinon) sur des FIXTURES TEXTE, jamais sur un
fichier de ce dépôt (S-00001608 : fixture d'abord, dogfooding en dernier — le
dogfooding est T-00000736). Aucune E/S hors d'un répertoire jetable (le seul, celui
du témoin J), aucun skip kit-only : il voyage tel quel.

T-00000786 (S-00002846) a fait du marqueur un COMMENTAIRE à trois porteurs —
`# cadre.*` dans le frontmatter d'un `.md`, `<!-- cadre.* -->` en tête d'un
`.md` sans frontmatter, `# cadre.*` en tête d'un `.toml` — et chaque témoin
ci-dessous a été re-ciblé sur les trois. Les témoins PROPRES à la forme
commentaire (site exact, inertie, forme d'avant, régions, en-tête HTML devant
un frontmatter, frontmatter vide, reprise, corps qui ouvre sur `cadre.`,
linéarité HTML/TOML) vivent dans `test_cadre_managed_commentaire.py`, T29-T37 :
ce banc-ci est tenu sous les 800 lignes (S-00002684 ; borne relevée à 1600 par S-00004034).

Ce qu'il tient, témoin par témoin (numéros du plan) :

* T1 aller-retour `poser` → `lire` sur les trois porteurs, champs exacts.
* T2 idempotence (`poser(poser(x)) == poser(x)`) et déterminisme à l'octet.
* T3 `verifier` : INTACT après pose, MODIFIE après UN caractère du corps ET
  après un `model:` changé dans le frontmatter non-cadre (le checksum couvre
  TOUT le frontmatter), NON_MARQUE sur texte vierge ; REPRIS sur `managed:
  false` — `lire` rend un `Marqueur` à `managed` faux, jamais `None`, et
  `poser` REFUSE de re-marquer une reprise (binôme F2, S-00001602).
* T4 refus : les catalogues `cas_markdown()` / `cas_toml()` (clés partielles,
  checksum hors forme, `managed: yes`, clé inconnue, doublon, ligne mal
  enveloppée, forme d'avant, HTML non refermé ou devant un frontmatter, TOML à
  candidate illisible…) ; `poser` et `depouiller` refusent AVANT de retirer ;
  `FormeInconnue` pour `.sh`, `.json`, `.py`, `.yml`.
* T5 `depouiller(poser(x)) == x` et `empreinte(depouiller(m)) == lire(m).checksum`.
* T6 même corps en CRLF ⇒ INTACT, et même rendu à l'octet.
* T8 négatif du filet : le module est au périmètre de `OrchestrationPurityTests`
  et y passe sans fautif — assertion ICI, sans toucher `test_cadre_package.py`.
* T9 région BORNÉE : un corps `.md` qui cite les trois enveloppes hors
  frontmatter, un `managed = true` sous une autre table TOML, des lignes
  `# cadre.*` après la tête TOML ⇒ NON_MARQUE, et `depouiller` les garde.
* T10 les bornes ÉCRITES dans la docstring du module sont tenues — dont le
  frontmatter VIDE, INVERSÉ par T-00000786 : il est rendu à l'octet, plus
  traité comme absent (l'ÉCART 1 est retiré avec la création de frontmatter).
* T14 (sécurité #2) : `RecursionError` de `tomllib` ⇒ `MarqueurIllisible`, en
  lecture sur un TOML à candidate `[cadre]` comme au chargement du corps par
  `poser` ; sans candidate, le fichier n'est jamais chargé.
* T15 (sécurité #5) : version hors `[0-9A-Za-z.+-]+` refusée par `poser` (à
  la LECTURE aussi depuis la passe 2 de T-00000786 : T38).
* T16 (sécurité #1) : une ligne `# cadre.*` de 40 000 caractères se lit — ou
  se refuse — en < 0,5 s (3 s mesurées sur f40de4f2 : rebroussement
  quadratique).
* T17 : la comparaison de relecture de `poser` est ATTEIGNABLE et refuse —
  prouvé par un collaborateur substitué (`mock.patch.object`) : depuis
  T-00000786 aucune entrée connue ne l'atteint plus, et c'est dit.
* T18 (binôme F1) : le jeton `cadre.managed` est dans les TROIS porteurs, et
  ses lignes sont hors checksum.
* T19 (témoins critic-fable a, c) : `managed: false` avec un checksum de 63 hex
  est un refus, pas une reprise — validé AVANT que `managed` compte, sur les
  quatre entrées ; `cadre.managed: 1` n'est pas un booléen.
* T20 (binôme F3) : un BOM initial n'est ni corps ni marqueur — INTACT sur les
  trois porteurs, `poser(BOM + x) == poser(x)`, et le rendu n'en porte pas.
* T23 (binôme F6, F8) : aucun U+2028 ni U+FEFF brut dans les sources ; la
  migration du format est nommée question OUVERTE, portée par T-752,
  bloquante pour T-741.
* T26 (binôme final, S-00002731) : la forme MINIMALE d'une reprise est UNE
  ligne `# cadre.managed: false` (`<!-- … -->` en tête HTML) ⇒ REPRIS sur les
  trois porteurs, `poser` refuse encore ; version/checksum facultatifs mais
  VALIDÉS s'ils sont là.
* T27 (binôme final) : les refus portent leur REMÈDE, dans la forme
  commentaire du porteur lu (« une reprise peut s'écrire `# cadre.managed:
  false` seule »).
* T28 (binôme final, critic-opus F5) : la docstring porte les bornes écrites —
  `git grep` rend un SUR-ENSEMBLE filtré par `lire`, REPRIS ne compare pas donc
  `check_socle_integrity` compare lui-même, `apply-mode.py` ⇒ MODIFIE (T-752).

RETIRÉS par T-00000786, leur objet n'existant plus avec la table `[cadre]` :
T7 (deux témoins : bloc suivi d'une autre table, deux tables), T11 (en-tête
dans une chaîne multi-ligne), T12 (bloc de quatre lignes), T13 (espace de noms
`cadre` déjà pris — sans objet pour une clé `cadre` quelconque, que l'en-tête
commentaire ne heurte plus ; il SURVIT pour la clé racine `cadre.managed`,
pointée ou en ligne, que `poser` refuse désormais : T31), T21 (borne de 64
candidates), T22 (en-tête quoté simple), T24 (ligne vide devant le bloc), T25
(citation après le bloc). La table `[cadre]` n'est plus lue que pour être
REFUSÉE comme forme d'avant (T31).

Les fixtures (formes, textes vierges, `PORTEURS`, `fm`, `tete`, `html`,
catalogues de refus T4) vivent dans `cadre_managed_fixtures.py`, à côté,
importé ici comme `classification_rules.py` l'est par son banc — règle pilote
des 800 lignes par `.py` (S-00002684, relevée à 1600 par S-00004034) ; il voyage comme ce banc (classe
OUTILLAGE par le préfixe, aucun `strip:`).

Chaque témoin a été rendu ROUGE par un mutant du module (M1–M9 du plan
T-00000735, X1–X12 des passes exec-critic/sécurité, N1–N10 de la passe binôme,
K1–K8 et M1 de T-00000786, P1–P7 et L1 de sa passe 2) ou par le module au
commit précédent avant d'être
compté vert : c'est ce qui prouve qu'il mesure quelque chose. T19 est un
témoin de MUTANT (N4, N10), pas de régression, et c'est dit plutôt que
confondu.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
EVALS = Path(__file__).resolve().parent
# Le paquet `cadre` où qu'il vive, chargé par chemin par `vendor_paths`, sans rien insérer en
# tête de `sys.path` (S-01M5BXT85VP4JBBMXVXR9STP5F ; témoin J ci-dessous).
_SPEC_VENDOR = importlib.util.spec_from_file_location(
    "_managed_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
assert _SPEC_VENDOR is not None and _SPEC_VENDOR.loader is not None
_VENDOR = importlib.util.module_from_spec(_SPEC_VENDOR)
sys.modules[_SPEC_VENDOR.name] = _VENDOR
_SPEC_VENDOR.loader.exec_module(_VENDOR)
_VENDOR.charger_paquet(ROOT, "cadre")
if str(EVALS) not in sys.path:
    sys.path.insert(0, str(EVALS))

import cadre  # noqa: E402
from cadre import managed  # noqa: E402
from cadre.managed import (  # noqa: E402
    Etat,
    FormeInconnue,
    Marqueur,
    MarqueurIllisible,
    depouiller,
    empreinte,
    forme_de,
    lire,
    poser,
    verifier,
)

import cadre_managed_fixtures as fixtures  # noqa: E402
from cadre_managed_fixtures import (  # noqa: E402
    BOM,
    MD,
    MD_SANS_FRONTMATTER,
    MD_VIERGE,
    PORTEURS,
    TOML_VIERGE,
    TT,
    ZEROS,
    cas_markdown,
    cas_toml,
    fm as _fm,
    html,
    tete,
)

#: La ligne `managed` de chaque porteur, vraie puis reprise.
_MANAGED = {
    "frontmatter": ("# cadre.managed: true", "# cadre.managed: false"),
    "html": (html("cadre.managed: true"), html("cadre.managed: false")),
    "toml": ("# cadre.managed: true", "# cadre.managed: false"),
}


class ManagedAllerRetourTests(unittest.TestCase):
    """T1, T2, T5, T6 — ce que `poser` rend se relit, se dépouille, se répète."""

    def test_T1_aller_retour_poser_lire_sur_les_trois_porteurs(self):
        for nom, forme, vierge in PORTEURS:
            with self.subTest(porteur=nom):
                rendu = poser(vierge, forme)
                self.assertEqual(
                    lire(rendu, forme),
                    Marqueur(version=cadre.__version__, checksum=empreinte(vierge)),
                )
                self.assertIn("cadre.managed", rendu, "le jeton doit être dans les TROIS porteurs")
                # Version explicite : elle est portée telle quelle, jamais remplacée.
                self.assertEqual(lire(poser(vierge, forme, version="9.9.9"), forme).version, "9.9.9")
        # La forme posée au frontmatter est EXACTEMENT celle de la docstring :
        # trois lignes `# ` juste avant le `---` fermant, valeurs quotées.
        rendu = poser(MD_VIERGE, MD)
        self.assertEqual(
            rendu.split("\n")[3:7],
            ["# cadre.managed: true",
             f'# cadre.version: "{cadre.__version__}"',
             f'# cadre.checksum: "{empreinte(MD_VIERGE)}"',
             "---"],
        )

    def test_T2_idempotence_et_determinisme(self):
        for nom, forme, vierge in PORTEURS:
            with self.subTest(porteur=nom):
                une_fois = poser(vierge, forme)
                self.assertEqual(poser(une_fois, forme), une_fois, "poser n'est pas idempotent")
                self.assertEqual(poser(vierge, forme), une_fois, "deux poses identiques divergent")
                self.assertEqual(
                    poser(vierge, forme).encode("utf-8"), une_fois.encode("utf-8"))

    def test_T5_depouiller_est_l_inverse_de_poser(self):
        for nom, forme, vierge in PORTEURS:
            with self.subTest(porteur=nom):
                marque = poser(vierge, forme)
                self.assertEqual(depouiller(marque, forme), vierge)
                self.assertEqual(empreinte(depouiller(marque, forme)), lire(marque, forme).checksum)
                # Sans marqueur, `depouiller` est l'identité (à la normalisation près).
                self.assertEqual(depouiller(vierge, forme), vierge)

    def test_T6_un_checkout_crlf_n_est_pas_une_reprise(self):
        for nom, forme, vierge in PORTEURS:
            with self.subTest(porteur=nom):
                marque = poser(vierge, forme)
                crlf = marque.replace("\n", "\r\n")
                self.assertNotEqual(crlf, marque)
                self.assertIs(verifier(crlf, forme), Etat.INTACT)
                self.assertEqual(lire(crlf, forme), lire(marque, forme))
                # Poser sur un corps CRLF rend le MÊME octet que sur le corps LF.
                self.assertEqual(poser(vierge.replace("\n", "\r\n"), forme), marque)
                self.assertEqual(empreinte(vierge.replace("\n", "\r\n")), empreinte(vierge))


class ManagedVerifierTests(unittest.TestCase):
    """T3 — les trois états, et ce que le checksum couvre."""

    def test_T3_intact_modifie_non_marque(self):
        for nom, forme, vierge in PORTEURS:
            with self.subTest(porteur=nom):
                self.assertIs(verifier(vierge, forme), Etat.NON_MARQUE)
                marque = poser(vierge, forme)
                self.assertIs(verifier(marque, forme), Etat.INTACT)
                # UN caractère du corps : l'avant-dernier, le dernier étant le LF.
                un_caractere = marque[:-2] + "!" + marque[-1]
                self.assertNotEqual(un_caractere, marque)
                self.assertIs(verifier(un_caractere, forme), Etat.MODIFIE)
                self.assertIs(verifier(marque.replace("Corps", "Corp5").replace('"read"', '"reed"'), forme),
                              Etat.MODIFIE)
        # Le checksum couvre le frontmatter NON-cadre : `model:` change ⇒ MODIFIE.
        marque_md = poser(MD_VIERGE, MD)
        self.assertIs(verifier(marque_md.replace("model: sonnet", "model: opus"), MD), Etat.MODIFIE)
        marque_toml = poser(TOML_VIERGE, TT)
        self.assertIs(verifier(marque_toml.replace('model = "sonnet"', 'model = "opus"'), TT),
                      Etat.MODIFIE)

    def test_T3_managed_false_est_une_reprise_explicite_et_se_voit(self):
        """Binôme F2 (S-00001602). Sur cb98e90c `lire` rendait `None` et
        `verifier` NON_MARQUE sur une reprise — indiscernables d'un fichier
        vierge —, et `poser` réécrivait le `false` de l'adoptant en `true`."""
        for nom, forme, vierge in PORTEURS:
            vrai, faux = _MANAGED[nom]
            with self.subTest(porteur=nom):
                marque = poser(vierge, forme)
                repris = marque.replace(vrai, faux)
                self.assertNotEqual(repris, marque, "témoin vide : rien n'a été repris")
                self.assertEqual(
                    lire(repris, forme),
                    Marqueur(version=cadre.__version__, checksum=empreinte(vierge), managed=False))
                self.assertIs(verifier(repris, forme), Etat.REPRIS)
                # Un marqueur repris ET modifié reste REPRIS : la reprise prime sur le corps.
                self.assertIs(verifier(repris + "ajout\n", forme), Etat.REPRIS)
                # `depouiller` retire la reprise comme un marqueur : ce n'est pas du corps.
                self.assertEqual(depouiller(repris, forme), vierge)
                # `poser` REFUSE avant tout rendu, et nomme la reprise — modifiée ou non.
                for texte in (repris, repris + "ajout\n"):
                    with self.assertRaisesRegex(MarqueurIllisible, "repris"):
                        poser(texte, forme)
        # `managed` vaut True par défaut : la seule valeur que `poser` écrit.
        self.assertTrue(Marqueur(version="1", checksum=ZEROS).managed)
        self.assertEqual(lire(poser(MD_VIERGE, MD), MD).managed, True)


class ManagedRefusTests(unittest.TestCase):
    """T4 — le refus est un TYPE, jamais une valeur par défaut. Les catalogues
    de cas vivent dans `cadre_managed_fixtures` (`cas_markdown`, `cas_toml`)."""

    def test_T4_marqueur_illisible_sur_les_trois_porteurs(self):
        for forme, catalogue in ((MD, cas_markdown()), (TT, cas_toml())):
            for nom, texte in catalogue.items():
                with self.subTest(forme=forme.value, cas=nom):
                    for fonction in (lire, verifier, depouiller, poser):
                        with self.assertRaises(MarqueurIllisible, msg=fonction.__name__):
                            fonction(texte, forme)

    def test_T4_poser_et_depouiller_refusent_avant_de_retirer_une_cle_etrangere(self):
        """R3 : jamais de clé étrangère silencieusement perdue — le refus
        précède tout retrait, et `depouiller` seul refuse aussi."""
        for forme, texte in ((MD, cas_markdown()["cle cadre.* inconnue (R3)"]),
                             (MD, cas_markdown()["html : cle inconnue"]),
                             (TT, cas_toml()["cle etrangere (R3)"])):
            with self.subTest(forme=forme.value, texte=texte[:24]):
                with self.assertRaisesRegex(MarqueurIllisible, "inconnue"):
                    poser(texte, forme)
                with self.assertRaisesRegex(MarqueurIllisible, "inconnue"):
                    depouiller(texte, forme)

    def test_T4_forme_inconnue_est_le_point_d_extension(self):
        for relatif in ("x.sh", ".claude/settings.json", ".claude/hooks/garde.py", "hooks.json",
                        "README", "shim.py", "ci.yml"):
            with self.subTest(relatif=relatif):
                with self.assertRaises(FormeInconnue):
                    forme_de(relatif)
        self.assertIs(forme_de(".claude/agents/planner.md"), MD)
        self.assertIs(forme_de(".codex/agents/planner.toml"), TT)
        self.assertIs(forme_de("AGENTS.MD"), MD)
        with self.assertRaises(FormeInconnue):
            lire(MD_VIERGE, "markdown")  # type: ignore[arg-type]


class ManagedPeriMetreTests(unittest.TestCase):
    """T8 — le négatif du filet de pureté, joué ICI."""

    def test_T8_le_module_neuf_est_au_perimetre_du_filet_et_y_passe(self):
        import test_cadre_package as paquet  # noqa: PLC0415 — import au témoin, jamais à la collecte

        banc = paquet.OrchestrationPurityTests()
        cibles = banc._modules_d_orchestration()
        chemin = paquet.PKG / "managed.py"
        self.assertIn(chemin, cibles, f"managed.py hors du périmètre de pureté : {cibles}")
        self.assertEqual(banc._fautifs_purete([chemin], paquet.PKG), [])
        self.assertEqual(chemin.resolve(), Path(managed.__file__).resolve(),
                         "le module testé n'est pas celui du périmètre")


class ManagedRegionBorneeTests(unittest.TestCase):
    """T9 (R2) — la lecture et le dépouillement sont BORNÉS à la région."""

    def test_T9_un_corps_md_qui_cite_le_marqueur_n_est_pas_marque(self):
        corps = (
            "\n# Le format du marqueur\n\n```yaml\n# cadre.managed: true\n"
            f'# cadre.version: "1"\n# cadre.checksum: "{ZEROS}"\n```\n'
            f"{html('cadre.managed: true')}\ncadre.managed: true\n"
        )
        texte = "---\nname: doc\n---" + corps
        self.assertIsNone(lire(texte, MD))
        self.assertIs(verifier(texte, MD), Etat.NON_MARQUE)
        self.assertEqual(depouiller(texte, MD), texte, "une ligne du corps a été retirée")
        rendu = poser(texte, MD)
        self.assertEqual(rendu.count("# cadre.managed: true"), 2, "le corps doit garder sa citation")
        self.assertTrue(rendu.endswith(corps))
        self.assertEqual(depouiller(rendu, MD), texte)
        # Sans frontmatter du tout, un corps qui cite (hors tête) reste vierge aussi.
        self.assertIsNone(lire(corps, MD))
        self.assertEqual(depouiller(corps, MD), corps)

    def test_T9_hors_de_la_tete_toml_rien_n_est_le_marqueur(self):
        texte = f'[autre]\nmanaged = true\nversion = "1"\nchecksum = "{ZEROS}"\n'
        self.assertIsNone(lire(texte, TT))
        self.assertIs(verifier(texte, TT), Etat.NON_MARQUE)
        self.assertEqual(depouiller(texte, TT), texte)
        sous_table = f'[cadre.sub]\nmanaged = true\nversion = "1"\nchecksum = "{ZEROS}"\n'
        self.assertIsNone(lire(sous_table, TT))
        apres = 'name = "x"\n# cadre.managed: true\n# cadre.version: "1"\n' f'# cadre.checksum: "{ZEROS}"\n'
        self.assertIsNone(lire(apres, TT), "une ligne de corps devant : ce n'est plus la tête")
        self.assertEqual(depouiller(apres, TT), apres)


class ManagedBornesTests(unittest.TestCase):
    """T10 — les bornes écrites dans la docstring du module sont tenues."""

    def test_T10_un_frontmatter_vide_est_un_frontmatter_rendu_a_l_octet(self):
        """INVERSÉ par T-00000786 (Piège 2 du plan), explicitement : avant, un
        frontmatter vide était traité comme ABSENT (ÉCART 1) — `depouiller` en
        retirait les délimiteurs, parce que `poser` créait un frontmatter. Il
        n'en crée plus : le frontmatter vide reçoit le marqueur, et le
        dépouillement le lui rend TEL QUEL."""
        texte = "---\n---\n# Corps\n"
        self.assertIsNone(lire(texte, MD))
        self.assertEqual(depouiller(texte, MD), texte)
        rendu = poser(texte, MD)
        self.assertIs(verifier(rendu, MD), Etat.INTACT)
        self.assertEqual(rendu.count("---"), 2)
        self.assertTrue(rendu.startswith("---\n# cadre.managed: true\n"))
        self.assertEqual(depouiller(rendu, MD), texte)

    def test_T10_une_regle_horizontale_en_ligne_1_n_est_pas_un_frontmatter(self):
        texte = "---\n# Corps\n"
        self.assertIsNone(lire(texte, MD))
        rendu = poser(texte, MD)
        self.assertTrue(rendu.startswith(html("cadre.managed: true") + "\n"), "tête HTML attendue")
        self.assertIs(verifier(rendu, MD), Etat.INTACT)
        self.assertEqual(depouiller(rendu, MD), texte)

    def test_T10_poser_n_ajoute_aucun_octet_au_corps(self):
        """Avant T-00000786, `poser` terminait un TOML par LF (le bloc allait en
        fin de fichier). L'en-tête est en TÊTE désormais : le corps est gardé
        à l'octet, fin de ligne absente comprise."""
        sans_lf = 'name = "exemple"'
        rendu = poser(sans_lf, TT)
        self.assertEqual(depouiller(rendu, TT), sans_lf)
        self.assertTrue(rendu.endswith("\n" + sans_lf))
        self.assertIs(verifier(rendu, TT), Etat.INTACT)
        self.assertTrue(poser("", TT).startswith("# cadre.managed: true\n"))
        self.assertEqual(depouiller(poser("", TT), TT), "")
        self.assertEqual(depouiller(poser("", MD), MD), "")

    def test_T10_le_module_ne_prend_aucun_chemin(self):
        """La primitive travaille sur du TEXTE : aucun paramètre n'est un chemin,
        et le module n'importe ni `Workspace` ni `kitlock` (R5)."""
        for fonction in (empreinte, depouiller, lire, poser, verifier):
            for nom, param in inspect.signature(fonction).parameters.items():
                self.assertNotIn("chemin", nom)
                self.assertNotIn("Path", str(param.annotation))
        self.assertFalse(hasattr(managed, "Workspace"))
        self.assertFalse(hasattr(managed, "kitlock"))


class ManagedStructureTomlTests(unittest.TestCase):
    """T14 — la vraie structure TOML n'est chargée que pour juger la forme
    d'avant, et son échec est un refus."""

    def test_T14_un_toml_trop_imbrique_est_un_refus_pas_une_panne(self):
        """Sécurité #2 : `tomllib` laisse remonter `RecursionError` ; ici c'est
        `MarqueurIllisible` — en lecture sur un TOML qui porte une candidate
        `[cadre]` (sa vraie structure doit être lue), sur les quatre entrées,
        et au chargement du corps par `poser`."""
        profond = "[" * 5000 + "]" * 5000
        a_candidate = f'[cadre]\nmanaged = true\nversion = {profond}\nchecksum = "{ZEROS}"\n'
        with self.assertRaises(RecursionError):
            tomllib.loads(a_candidate)
        for fonction in (lire, depouiller, verifier, poser):
            with self.subTest(fonction=fonction.__name__):
                with self.assertRaisesRegex(MarqueurIllisible, "trop imbriqué"):
                    fonction(a_candidate, TT)
        sans_candidate = f"x = {profond}\n"
        with self.assertRaisesRegex(MarqueurIllisible, "trop imbriqué"):
            poser(sans_candidate, TT)
        # Sans candidate, la LECTURE ne charge jamais le fichier : borne de coût.
        self.assertIsNone(lire(sans_candidate, TT))


class ManagedPoserRefusTests(unittest.TestCase):
    """T15–T17 — ce que `poser` refuse, et par quelle ligne."""

    def test_T15_poser_refuse_une_version_hors_forme_sur_les_trois_porteurs(self):
        """Sécurité #5. Sur f40de4f2, `a"b` et `a\\b` se posaient en frontmatter
        (le déquotage les relisait tels quels) et `1\\n2` n'était refusé qu'à la
        relecture."""
        for nom, forme, vierge in PORTEURS:
            for version in ('a"b', "a\\b", "1\n2", "1 2", "", "é"):
                with self.subTest(porteur=nom, version=version):
                    with self.assertRaisesRegex(MarqueurIllisible, "hors de la forme"):
                        poser(vierge, forme, version=version)
            with self.subTest(porteur=nom, version="acceptée"):
                self.assertEqual(
                    lire(poser(vierge, forme, version="1.0.0-rc.1+build.7"), forme).version,
                    "1.0.0-rc.1+build.7")
        self.assertRegex(cadre.__version__, r"^[0-9A-Za-z.+-]+$", "la version du kit doit se poser")

    def test_T16_une_ligne_cadre_de_40_000_caracteres_se_lit_en_temps_lineaire(self):
        """Sécurité #1 : `(.*?)[ \\t]*$` rebroussait en O(n²) — 3,04 s mesurées
        sur f40de4f2 pour « a + 40 000 blancs + b » ; `(.*)$` puis `rstrip` est
        linéaire (< 5 ms). Le seuil laisse 6× de marge au pire mesuré. Depuis
        la passe 2 de T-00000786 cette valeur est REFUSÉE (version lue hors
        forme, T38) — mais APRÈS l'expression, qui la parcourt en entier : c'est
        le refus qui se chronomètre, et le mutant paresseux L1 le rend rouge.
        Une version longue VALIDE se relit, elle, entière. Les enveloppes HTML
        et TOML ont leur propre témoin (T37)."""
        valeur = "a" + " " * 40_000 + "b"
        texte = _fm("# cadre.managed: true", f"# cadre.version: {valeur}", f'# cadre.checksum: "{ZEROS}"')
        debut = time.perf_counter()
        with self.assertRaisesRegex(MarqueurIllisible, "hors de la forme"):
            lire(texte, MD)
        duree = time.perf_counter() - debut
        self.assertLess(duree, 0.5, f"refus en {duree:.2f} s : rebroussement quadratique")
        longue = "1." + "0" * 40_000
        valide = _fm("# cadre.managed: true", f"# cadre.version: {longue}", f'# cadre.checksum: "{ZEROS}"')
        self.assertEqual(lire(valide, MD).version, longue, "une version longue valide est la valeur")
        # Seuls les blancs de QUEUE partent, par `rstrip`, pas par la regex.
        queue = _fm("# cadre.managed: true", '# cadre.version: "1" \t ', f'# cadre.checksum: "{ZEROS}"')
        self.assertEqual(lire(queue, MD).version, "1")

    def test_T17_la_relecture_de_poser_est_atteignable_et_refuse(self):
        """La comparaison de relecture (`relu != attendu or verifier(rendu) is
        not INTACT`) est la dernière défense. Avant T-00000786, une ENTRÉE
        l'atteignait : un corps ouvrant sur un frontmatter vide (ÉCART 1
        appliqué deux fois). L'ÉCART 1 étant retiré, cette entrée passe
        désormais — épinglé ci-dessous —, et un corps qui ouvre sur `# cadre.`
        ou `<!-- cadre.` est refusé en LECTURE, avant tout rendu (T36) : aucune
        entrée connue n'atteint plus la relecture, et c'est dit. Le témoin
        prouve donc l'ATTEIGNABILITÉ par un collaborateur substitué
        (`mock.patch.object`, jamais une affectation nue) : `verifier` qui
        dirait MODIFIE, puis `lire` qui relirait une autre version — chacune
        des deux moitiés du `or`. Mutant X3 (`if False:`) ⇒ rouge."""
        entree_d_avant = "---\n---\n---\n---\nx\n"
        self.assertIs(verifier(poser(entree_d_avant, MD), MD), Etat.INTACT)
        vrai_lire = managed.lire

        def autre_version(texte, forme):
            relu = vrai_lire(texte, forme)
            return None if relu is None else Marqueur("autre", relu.checksum, relu.managed)

        for nom, forme, vierge in PORTEURS:
            with self.subTest(porteur=nom, moitie="verifier"):
                with mock.patch.object(managed, "verifier", return_value=Etat.MODIFIE):
                    with self.assertRaisesRegex(MarqueurIllisible, "rendu relu"):
                        poser(vierge, forme)
            with self.subTest(porteur=nom, moitie="lire"):
                with mock.patch.object(managed, "lire", side_effect=autre_version):
                    with self.assertRaisesRegex(MarqueurIllisible, "rendu relu"):
                        poser(vierge, forme)
        # Hors substitution, les mêmes poses passent : c'est la relecture qui a parlé.
        for nom, forme, vierge in PORTEURS:
            self.assertIs(verifier(poser(vierge, forme), forme), Etat.INTACT)


class ManagedBinomeTests(unittest.TestCase):
    """T18–T23 — les constats du binôme de clôture (critic-opus ∥ critic-fable,
    S-00002699) et la décision S-00002700, témoin par témoin."""

    def test_T18_le_jeton_cadre_managed_est_dans_les_trois_porteurs_hors_empreinte(self):
        """Binôme F1 : sur cb98e90c le TOML posé ne portait pas le jeton, donc
        `git grep -F cadre.managed` n'énumérait aucune déf Codex. Depuis
        T-00000786 le jeton est dans la LIGNE elle-même, sur les trois
        porteurs, et ses lignes sont hors checksum : une `version` éditée à la
        main reste INTACT (la docstring le dit, `cadre doctor` le nommera)."""
        for nom, forme, vierge in PORTEURS:
            with self.subTest(porteur=nom):
                rendu = poser(vierge, forme)
                self.assertIn("cadre.managed", rendu)
                self.assertEqual(sum("cadre." in ligne for ligne in rendu.split("\n")), 3)
                self.assertEqual(depouiller(rendu, forme), vierge)
                self.assertEqual(lire(rendu, forme).checksum, empreinte(vierge))
                edite = rendu.replace(f'"{cadre.__version__}"', '"0.0.0-main"')
                self.assertNotEqual(edite, rendu, "témoin vide : la version n'a pas été éditée")
                self.assertEqual(lire(edite, forme).version, "0.0.0-main")
                self.assertIs(verifier(edite, forme), Etat.INTACT)

    def test_T19_une_reprise_mutilee_est_un_refus_pas_une_reprise(self):
        """Témoins critic-fable (a) et (c). Mutant N4 : `managed=false` rendu
        AVANT la validation ⇒ une reprise à checksum de 63 hex passerait pour
        une reprise. Version et checksum comptent AVANT `managed`, sur les
        quatre entrées et les trois porteurs ; et `cadre.managed: 1` n'est pas
        un booléen (mutant N10)."""
        def trois(ouvre, ferme, corps, *lignes):
            return tete(*(f"{ouvre}{l}{ferme}" for l in lignes), corps=corps)

        porteurs = {
            "frontmatter": (MD, lambda *l: _fm(*(f"# {x}" for x in l))),
            "html": (MD, lambda *l: trois("<!-- ", " -->", "# Corps\n", *l)),
            "toml": (TT, lambda *l: trois("# ", "", TOML_VIERGE, *l)),
        }
        for nom, (forme, faire) in porteurs.items():
            mutile = faire("cadre.managed: false", 'cadre.version: "1"', f'cadre.checksum: "{ZEROS[:-1]}"')
            for fonction in (lire, verifier, depouiller, poser):
                with self.subTest(cas="checksum 63 hex", porteur=nom, fonction=fonction.__name__):
                    with self.assertRaisesRegex(MarqueurIllisible, "checksum"):
                        fonction(mutile, forme)
            vide = faire("cadre.managed: false", 'cadre.version: ""', f'cadre.checksum: "{ZEROS}"')
            with self.subTest(cas="version vide", porteur=nom):
                with self.assertRaisesRegex(MarqueurIllisible, "version vide"):
                    verifier(vide, forme)
            # (c) `cadre.managed: 1` : une valeur VRAIE, pas un booléen.
            un = faire("cadre.managed: 1", 'cadre.version: "1"', f'cadre.checksum: "{ZEROS}"')
            for fonction in (lire, verifier, depouiller, poser):
                with self.subTest(cas="managed: 1", porteur=nom, fonction=fonction.__name__):
                    with self.assertRaisesRegex(MarqueurIllisible, "managed doit valoir"):
                        fonction(un, forme)

    def test_T20_un_bom_initial_n_est_ni_corps_ni_marqueur(self):
        """Binôme F3. Sur cb98e90c un `.md` marqué rouvert avec un BOM était
        NON_MARQUE (le `---` n'était plus en ligne 1) et `poser` empilait un
        second frontmatter par-dessus le premier ; en `.toml` il était MODIFIE."""
        for nom, forme, vierge in PORTEURS:
            with self.subTest(porteur=nom):
                marque = poser(vierge, forme)
                self.assertIs(verifier(BOM + marque, forme), Etat.INTACT)
                self.assertEqual(lire(BOM + marque, forme), lire(marque, forme))
                self.assertEqual(poser(BOM + vierge, forme), marque)
                self.assertEqual(poser(BOM + marque, forme), marque)
                self.assertEqual(depouiller(BOM + vierge, forme), vierge)
                self.assertEqual(empreinte(BOM + vierge), empreinte(vierge))
                self.assertNotIn(BOM, poser(BOM + vierge, forme), "poser rend un texte SANS BOM")
        # Un BOM ailleurs qu'en tête est du corps : il compte.
        self.assertIs(verifier(poser(MD_VIERGE, MD).replace("Corps", BOM + "Corps"), MD), Etat.MODIFIE)

    def test_T23_la_source_et_la_docstring_portent_ce_qui_est_ecrit(self):
        """Binôme F6 : un U+2028 BRUT dans la docstring (ligne 119 sur
        cb98e90c) — un éditeur qui le normalise casse la ligne ; l'échappement
        le montre. F8 : la migration du format (clés gelées ou tolérance N-1
        derrière une version de format) est une question OUVERTE, nommée,
        portée par T-752 et bloquante pour le scénario N-1→N de T-741 —
        écrite dans la docstring, jamais tranchée ici. Les bancs se jugent
        aussi : un outil d'édition a rendu `\\ufeff` en U+FEFF BRUT pendant
        T-735, et `\\u2028` en U+2028 BRUT pendant T-786 — un caractère
        invisible dans un banc est aussi faux que dans le module."""
        import test_cadre_managed_commentaire as banc_neuf  # noqa: PLC0415

        sources = {"managed": inspect.getsource(managed),
                   "ce banc": inspect.getsource(sys.modules[__name__]),
                   "le banc commentaire": inspect.getsource(banc_neuf),
                   "ses fixtures": inspect.getsource(fixtures)}
        for nom, source in sources.items():
            for point in (0x2028, 0xFEFF):
                with self.subTest(source=nom, point=f"U+{point:04X}"):
                    self.assertNotIn(chr(point), source, f"U+{point:04X} BRUT dans {nom}")
        self.assertIn("`\\u2028`", managed.__doc__)
        self.assertIn("T-00000752", managed.__doc__)
        self.assertIn("T-00000741", managed.__doc__)


class ManagedBinomeFinalTests(unittest.TestCase):
    """T26–T28 — binôme FINAL du lot vague A (S-00002727) et la décision
    S-00002731 : la reprise en une ligne, les refus avec remède, les bornes."""

    def test_T26_la_forme_minimale_d_une_reprise_est_une_seule_ligne(self):
        """S-00002731. Sur 45bff5fa la seule ligne `cadre.managed: false` était
        `MarqueurIllisible` (clés manquantes) : l'adoptant qui reprend un
        fichier tombait en refus au lieu de REPRIS. T-00000786 la garde sur
        les trois porteurs, dans leur forme commentaire."""
        for nom, texte, forme, corps in (
            ("frontmatter", _fm("name: exemple", "# cadre.managed: false"), MD,
             "---\nname: exemple\n---\n\n# Exemple\n\nCorps.\n"),
            ("html", tete(html("cadre.managed: false")), MD, "# Exemple\n\nCorps.\n"),
            ("toml", "# cadre.managed: false\n" + TOML_VIERGE, TT, TOML_VIERGE),
        ):
            with self.subTest(porteur=nom):
                self.assertEqual(lire(texte, forme), Marqueur(version=None, checksum=None, managed=False))
                self.assertIs(verifier(texte, forme), Etat.REPRIS)
                self.assertEqual(depouiller(texte, forme), corps, "la reprise part, le corps reste")
                with self.assertRaisesRegex(MarqueurIllisible, "repris"):
                    poser(texte, forme)
        # Facultatifs mais VALIDÉS s'ils sont présents : une version seule passe,
        # une version vide ou un checksum de 63 hex refusent (T19 tenu).
        self.assertEqual(lire(_fm("# cadre.managed: false", '# cadre.version: "1"'), MD),
                         Marqueur(version="1", checksum=None, managed=False))
        self.assertIs(verifier(f'# cadre.managed: false\n# cadre.checksum: "{ZEROS}"\n' + TOML_VIERGE, TT),
                      Etat.REPRIS)
        for nom, texte, forme in (
            ("version vide md", _fm("# cadre.managed: false", '# cadre.version: ""'), MD),
            ("checksum 63 hex toml", f'# cadre.managed: false\n# cadre.checksum: "{ZEROS[:-1]}"\n', TT),
            ("version vide html", tete(html("cadre.managed: false"), html('cadre.version: ""')), MD),
        ):
            with self.subTest(cas=nom):
                with self.assertRaises(MarqueurIllisible):
                    verifier(texte, forme)
        # Un marqueur POSÉ n'a pas cette latitude : `managed: true` seul reste un refus.
        for texte, forme in ((_fm("# cadre.managed: true"), MD), ("# cadre.managed: true\n", TT),
                             (tete(html("cadre.managed: true")), MD)):
            with self.subTest(pose_seul=texte[:24]):
                with self.assertRaises(MarqueurIllisible):
                    lire(texte, forme)

    def test_T27_les_refus_portent_leur_remede(self):
        """Binôme final : un refus sans remède laisse l'adoptant deviner. Depuis
        T-00000786 le remède cite la forme COMMENTAIRE du porteur lu — `#` au
        frontmatter et en TOML, `<!-- -->` en tête HTML. Le remède de la forme
        d'avant a son témoin en T31."""
        seule = r"une reprise.*peut s'écrire `# cadre\.managed: false` seule"
        with self.assertRaisesRegex(MarqueurIllisible, seule):
            lire(_fm("# cadre.managed: true"), MD)
        with self.assertRaisesRegex(MarqueurIllisible, seule):
            lire(_fm("# cadre.managed: true", '# cadre.version: "1"'), MD)
        with self.assertRaisesRegex(MarqueurIllisible, r"cadre\.managed manquante.*" + seule):
            lire(_fm('# cadre.version: "1"', f'# cadre.checksum: "{ZEROS}"'), MD)
        with self.assertRaisesRegex(MarqueurIllisible, seule):
            lire("# cadre.managed: true\n", TT)
        with self.assertRaisesRegex(MarqueurIllisible, r"cadre\.managed manquante.*" + seule):
            lire('# cadre.version: "1"\n', TT)
        seule_html = r"une reprise.*peut s'écrire `<!-- cadre\.managed: false -->` seule"
        with self.assertRaisesRegex(MarqueurIllisible, seule_html):
            lire(tete(html("cadre.managed: true")), MD)
        with self.assertRaisesRegex(MarqueurIllisible, r"cadre\.managed manquante.*" + seule_html):
            lire(tete(html('cadre.version: "1"')), MD)
        # Une ligne mal enveloppée nomme la forme exacte attendue.
        with self.assertRaisesRegex(MarqueurIllisible, r"de la forme `<!-- cadre\.<clé>: <valeur> -->`"):
            lire(tete("<!-- cadre.managed: true"), MD)
        # Le message de la reprise mutilée (T19) reste celui du checksum, pas du remède.
        with self.assertRaisesRegex(MarqueurIllisible, "checksum"):
            lire(_fm("# cadre.managed: false", f'# cadre.checksum: "{ZEROS[:-1]}"'), MD)

    def test_T28_la_docstring_porte_les_bornes_du_binome_final(self):
        """Critic-opus F5 et la docstring :7 « git grep suffit » (fausse). Ce
        que le module NE fait PAS est écrit là où on le cherchera."""
        doc = managed.__doc__
        for attendu in (
            "SUR-ENSEMBLE",
            "git grep -l -F cadre.managed",
            "lire(texte, forme_de(chemin))",
            "check_socle_integrity",
            "empreinte(depouiller(t, forme))",
            "apply-mode.py",
            "T-00000752",
            "S-00002731",
        ):
            with self.subTest(attendu=attendu):
                self.assertIn(attendu, doc)
        self.assertNotIn("suffit à énumérer", doc, "l'ancienne affirmation est revenue")


#: Les cinq modules du lot J (T-01M5BXTPQE3JZV3KZA6WD9P5XC), copiés tels quels dans le kit jetable.
LOT_J = ("cadre_managed_fixtures", "test_cadre_managed", "test_cadre_managed_commentaire",
         "test_cadre_socle_chaine", "test_check_socle_integrity")
#: Ce que leurs imports de niveau module ferment dans le paquet, copié fichier par fichier : aucun parcours.
FERMETURE_J = ("__init__.py", "paths.py", "workspace.py", "socle.py", "managed.py", "data/socle.json")
#: UN module par processus : un `cadre` déjà chargé par le précédent masquerait le chemin du suivant.
SONDE_J = (
    "import importlib, json, sys\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "pkg = str(getattr(importlib.import_module(sys.argv[2]), 'PKG', ''))\n"
    "import cadre, cadre.managed\n"
    "print(json.dumps({'cadre': cadre.__file__, 'managed': cadre.managed.__file__, 'pkg': pkg}))\n"
)


class VendorSeulJTests(unittest.TestCase):
    """Témoin J (S-01M5BXT85VP4JBBMXVXR9STP5F) : les cinq modules du lot chargent `cadre` depuis
    `.agents/vendor/cadre/` dans un kit jetable « vendor seul », et encore dans « les deux », où un
    `src/cadre` leurre lève à l'import. Mutant : `sys.path.insert(0, ROOT / "src")` rétabli (ou
    `PKG = ROOT / "src" / "cadre"`) → le leurre est chargé (ou PKG le désigne), rouge."""

    def _kit(self, base: Path, leurre: bool) -> Path:
        kit = base / ("les-deux" if leurre else "vendor-seul")
        (kit / ".agents" / "bin").mkdir(parents=True)
        shutil.copy2(ROOT / ".agents" / "bin" / "vendor_paths.py", kit / ".agents" / "bin" / "vendor_paths.py")
        (kit / ".agents" / "evals").mkdir()
        for nom in LOT_J:
            shutil.copy2(EVALS / f"{nom}.py", kit / ".agents" / "evals" / f"{nom}.py")
        source = _VENDOR.exiger(ROOT, "cadre")
        for rel in FERMETURE_J:
            cible = kit / ".agents" / "vendor" / "cadre" / rel
            cible.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / rel, cible)
        if leurre:
            (kit / "src" / "cadre").mkdir(parents=True)
            (kit / "src" / "cadre" / "__init__.py").write_text(
                'raise ImportError("leurre src/cadre charge")\n', encoding="utf-8")
        return kit

    def test_vendor_seul_j(self):
        sobre = ("PATH", "SYSTEMROOT", "SYSTEMDRIVE", "TMPDIR", "TEMP", "TMP", "HOME", "USERPROFILE")
        env = {k: v for k, v in os.environ.items() if k in sobre}
        with tempfile.TemporaryDirectory() as tmp:
            for leurre in (False, True):
                kit = self._kit(Path(tmp), leurre)
                attendu = (kit / ".agents" / "vendor" / "cadre").resolve()
                for nom in LOT_J:
                    with self.subTest(arbre="les deux" if leurre else "vendor seul", module=nom):
                        r = subprocess.run(
                            [sys.executable, "-X", "utf8", "-I", "-B", "-c", SONDE_J,
                             str(kit / ".agents" / "evals"), nom],
                            capture_output=True, text=True, encoding="utf-8", env=env, cwd=tmp, timeout=120)
                        self.assertEqual(r.returncode, 0, r.stderr)
                        vu = json.loads(r.stdout.strip().splitlines()[-1])
                        self.assertEqual(Path(vu["cadre"]).resolve().parent, attendu, vu)
                        self.assertEqual(Path(vu["managed"]).resolve().parent, attendu, vu)
                        if nom == "test_cadre_socle_chaine":  # le seul qui nomme PKG, source des copies
                            self.assertEqual(Path(vu["pkg"]).resolve(), attendu, vu)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
