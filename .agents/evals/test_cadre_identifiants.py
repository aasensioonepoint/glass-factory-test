"""`cadre.identifiants` — la couche de résolution des secrets, environnement seul
(T-00000898, plan `docs/tasks/T-00000898-plan.md` rév. 2, réserves S-00004506).

Ce banc exerce `src/cadre/identifiants.py` sans jamais toucher au trousseau (la
couche n'en a pas : décision pilote S-00003973). L'environnement est posé par
`mock.patch.dict(os.environ, …)`, sur des noms suffixés `_T898` retirés avant
usage ; les faux secrets sont construits PAR CONCATÉNATION, pour qu'aucun jeton
entier n'existe dans ce fichier. Chaque témoin nomme en docstring le MUTANT qui
le fait rougir.

Témoins du plan : A1-A12, plus le contrôle négatif de A6. Réserves du critique :
- C1 : aucune désérialisation `pickle` ici (règle semgrep
  python-insecure-deserialization-pickle) ; la reconstruction d'une exception est
  témoignée par `copy.copy` / `copy.deepcopy`, qui suivent le même
  `__reduce_ex__`, et la sérialisation par `pickle.dumps` seul ;
- C2 : `Secret.nom` est rédigé (A6) ;
- C3 : la frontière du vide est `str.isspace`, U+200B est « présente », et
  `"tok\\r"` est rendu exact ;
- C4 : aucun module du noyau chargé par l'import de la couche n'importe la
  couche (cycle) ;
- C7 : toute entrée passe par une VARIABLE, pour que la ligne source citée par
  `traceback.format_exception` ne porte jamais la sentinelle.
"""

from __future__ import annotations

import ast
import contextlib
import copy
import importlib.util
import io
import json
import logging
import os
import pickle
import subprocess
import sys
import tempfile
import traceback
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
# Le paquet `cadre` de CETTE racine, chargé par chemin (`.agents/vendor/cadre`
# d'abord, `src/cadre` ensuite) ; `SRC` est son parent d'import.
_SPEC_VENDOR = importlib.util.spec_from_file_location(
    "_cadre_identifiants_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
assert _SPEC_VENDOR is not None and _SPEC_VENDOR.loader is not None
_VENDOR = importlib.util.module_from_spec(_SPEC_VENDOR)
sys.modules[_SPEC_VENDOR.name] = _VENDOR
_SPEC_VENDOR.loader.exec_module(_VENDOR)
_VENDOR.charger_paquet(ROOT, "cadre")
SRC = _VENDOR.exiger(ROOT, "cadre").parent
EVALS = Path(__file__).resolve().parent
if str(EVALS) not in sys.path:
    sys.path.insert(0, str(EVALS))

from cadre import identifiants  # noqa: E402
from cadre.identifiants import (  # noqa: E402
    ErreurSecret,
    NomSecretInvalide,
    Secret,
    SecretAbsent,
    resoudre_secret,
)

MODULE = SRC / "cadre" / "identifiants.py"
JETON = "ghp_" + "a" * 36
MARQUE = "[SECRET RÉDIGÉ:github_token]"
SENTINELLE = "SENTI" + "NELLE-"
#: Préfixe des variables du contrat ; construit, pour que ce banc n'en porte aucun.
PREFIXE_CONTRAT = "CAD" + "RE_"


@contextlib.contextmanager
def environnement(valeurs: dict[str, str | None]):
    """`patch.dict` de `os.environ` ; un nom à `None` est RETIRÉ. Tout est
    restauré à la sortie, retraits compris."""
    with mock.patch.dict(os.environ):
        for nom, valeur in valeurs.items():
            if valeur is None:
                os.environ.pop(nom, None)
            else:
                os.environ[nom] = valeur
        yield


def _leve(test: unittest.TestCase, classe: type[BaseException], nom: object) -> BaseException:
    """L'exception levée, AVEC sa trace : `assertRaises` la rend sans
    (`with_traceback(None)`), ce qui rendrait vacants A5, A6 et A10."""
    try:
        resoudre_secret(nom)  # type: ignore[arg-type]
    except classe as exc:
        test.assertIsNotNone(exc.__traceback__)
        return exc
    test.fail(f"{classe.__name__} attendue, rien n'a été levé")


class PresenteTests(unittest.TestCase):
    """A1 et C3 — la valeur présente est rendue EXACTE."""

    def test_A1_valeur_rendue_exacte_et_nom(self):
        """Mutant : `return Secret(nom, valeur.strip())` ⇒ rouge."""
        nom, valeur = "X_T898", " a b "
        with environnement({nom: valeur}):
            s = resoudre_secret(nom)
        self.assertIsInstance(s, Secret)
        self.assertEqual(s.reveler(), valeur)
        self.assertEqual(s.nom, nom)

    def test_C3_la_frontiere_du_vide_est_str_isspace(self):
        """Mutants : `.strip()` au retour ⇒ `"tok\\r"` rendu `"tok"` ⇒ rouge ;
        vide jugé sur les seuls blancs ASCII ⇒ `"\\u3000"` présente ⇒ rouge ;
        vide jugé sur `isprintable` ⇒ U+200B vide ⇒ rouge."""
        nom = "F_T898"
        for valeur in ("\N{ZERO WIDTH SPACE}", "tok\r", "\N{ZERO WIDTH SPACE}tok", "\ttok"):
            with self.subTest(presente=repr(valeur)), environnement({nom: valeur}):
                self.assertEqual(resoudre_secret(nom).reveler(), valeur)
        for valeur in ("\N{IDEOGRAPHIC SPACE}", "\xa0", "\r", " \N{EM SPACE} "):
            with self.subTest(vide=repr(valeur)), environnement({nom: valeur}):
                exc = _leve(self, SecretAbsent, nom)
                self.assertEqual(exc.statut, "vide")


class AbsenteTests(unittest.TestCase):
    """A2 — absente : erreur nommée, bornée, sans cache."""

    def test_A2_absente_leve_SecretAbsent_nomme(self):
        """Mutants : `return Secret(nom, "")` ou `return None` ⇒ rouge."""
        nom = "ABSENT_T898"
        with environnement({nom: None}):
            exc = _leve(self, SecretAbsent, nom)
        self.assertIsInstance(exc, LookupError)
        self.assertIsInstance(exc, ErreurSecret)
        self.assertEqual(exc.statut, "absente")
        self.assertEqual(exc.nom, nom)
        self.assertIn(nom, str(exc))

    def test_A2_le_message_est_borne(self):
        """Mutant : message qui recopie l'environnement ⇒ rouge."""
        nom = "A" * 128
        with environnement({nom: None}):
            exc = _leve(self, SecretAbsent, nom)
        self.assertLessEqual(len(str(exc)), 300, str(exc))

    def test_A2_aucun_cache_lecture_a_l_appel(self):
        """Mutant : cache de lecture (`functools.lru_cache`) ⇒ rouge."""
        nom = "TARDIVE_T898"
        with environnement({nom: None}):
            _leve(self, SecretAbsent, nom)
            os.environ[nom] = "v1"
            self.assertEqual(resoudre_secret(nom).reveler(), "v1")
            os.environ[nom] = "v2"
            self.assertEqual(resoudre_secret(nom).reveler(), "v2")
            del os.environ[nom]
            _leve(self, SecretAbsent, nom)


class VideTests(unittest.TestCase):
    """A3 — vide : erreur nommée, distincte de l'absente."""

    def test_A3_vide_leve_SecretAbsent_statut_vide(self):
        """Mutant : le vide est accepté (`return Secret(nom, brut)`) ⇒ rouge."""
        nom = "VIDE_T898"
        with environnement({nom: None}):
            absent = str(_leve(self, SecretAbsent, nom))
        for valeur in ("", "   ", "\t\n"):
            with self.subTest(valeur=repr(valeur)), environnement({nom: valeur}):
                exc = _leve(self, SecretAbsent, nom)
                self.assertEqual(exc.statut, "vide")
                self.assertNotEqual(str(exc), absent)


class NomTests(unittest.TestCase):
    """A4 — le nom est validé AVANT toute lecture."""

    INVALIDES = ("-w", "a b", "", "x\x00", "a=b", "A\n", "1A", "É", "A١",
                 "A" * 129, None, b"A")
    VALIDES = ("A", "_", "A" * 128)

    def test_A4_nom_invalide_refuse_sans_lecture(self):
        """Mutants : `re.match` + `^…$` ⇒ `"A\\n"` passe ⇒ rouge ; `\\w` ⇒ `"É"`
        passe ⇒ rouge ; validation retirée ⇒ rouge."""
        for nom in self.INVALIDES:
            with self.subTest(nom=repr(nom)), \
                    mock.patch.object(identifiants, "_lire_env") as lecture:
                exc = _leve(self, NomSecretInvalide, nom)
                self.assertIsInstance(exc, ValueError)
                self.assertIsInstance(exc, ErreurSecret)
                lecture.assert_not_called()

    def test_A4_nom_valide_passe_la_validation(self):
        """Mutant : borne `{0,126}` ⇒ `"A"*128` refusé ⇒ rouge."""
        for nom in self.VALIDES:
            with self.subTest(nom=nom), mock.patch.object(
                    identifiants, "_lire_env", return_value=("présente", "v")) as lecture:
                self.assertEqual(resoudre_secret(nom).reveler(), "v")
                lecture.assert_called_once_with(nom, os.environ)


class NomJamaisRecopieTests(unittest.TestCase):
    """A5 et C7 — un nom refusé n'est jamais recopié ; l'entrée passe par une
    variable (la ligne source citée par la trace ne porte que `entree`)."""

    def test_A5_ni_str_ni_repr_ni_args_ni_trace(self):
        """Mutant : `f"nom de secret invalide {nom!r}"` ⇒ rouge."""
        entrees = (SENTINELLE + "z" * 12, JETON + " ", "Z" * 300, b"SENTI" + b"NELLE")
        for entree in entrees:
            with self.subTest(entree=entree[:16]):
                exc = _leve(self, NomSecretInvalide, entree)
                textes = (str(exc), repr(exc), repr(exc.args),
                          "".join(traceback.format_exception(exc)))
                cherche = entree if isinstance(entree, str) else entree.decode()
                for texte in textes:
                    self.assertNotIn(cherche, texte)
                    self.assertNotIn(SENTINELLE[:-1], texte)
                    self.assertNotIn(JETON, texte)
                if isinstance(entree, str):
                    self.assertIn(f"({len(entree)} caractères)", str(exc))
                else:
                    self.assertIn("une chaîne est attendue", str(exc))


class RedactionTests(unittest.TestCase):
    """A6 et C2 — tout texte qui porte le nom passe par `rediger`."""

    def _absent_et_present(self) -> tuple[SecretAbsent, Secret]:
        nom = JETON
        with environnement({nom: None}):
            exc = _leve(self, SecretAbsent, nom)
        with environnement({nom: "valeur"}):
            s = resoudre_secret(nom)
        return exc, s  # type: ignore[return-value]

    def test_A6_le_nom_qui_est_un_jeton_est_redige(self):
        """Mutants : `rediger` retiré de `_absent` ⇒ rouge ; `self.nom = nom`
        dans `Secret` (C2) ⇒ rouge."""
        exc, s = self._absent_et_present()
        for texte in (str(exc), repr(exc), exc.nom, repr(s), str(s), s.nom,
                      "".join(traceback.format_exception(exc))):
            self.assertNotIn(JETON, texte)
        for texte in (str(exc), repr(exc), exc.nom, repr(s), s.nom):
            self.assertIn(MARQUE, texte)

    def test_le_controle_negatif_mord(self):
        """Sans rédaction, le MÊME témoin voit le jeton : A6 n'est pas vacant."""
        with mock.patch.object(identifiants, "rediger", lambda t: t):
            exc, s = self._absent_et_present()
        self.assertIn(JETON, str(exc))
        self.assertEqual(exc.nom, JETON)
        self.assertEqual(s.nom, JETON)
        self.assertIn(JETON, repr(s))


class MasqueTests(unittest.TestCase):
    """A7 — `Secret` masque sa valeur, et la couche n'écrit rien."""

    VALEURS = ("ghp_" + "b" * 36, "hun" + "ter2")

    def test_A7_aucun_rendu_ne_montre_la_valeur(self):
        """Mutants : `@dataclass` ou `__repr__` par défaut ⇒ rouge ;
        `__format__` retiré ⇒ `f"{s:>20}"` lève ⇒ rouge."""
        nom = "MASQUE_T898"
        for valeur in self.VALEURS:
            with self.subTest(valeur=valeur[:4]), environnement({nom: valeur}):
                s = resoudre_secret(nom)
                attendu = f"Secret(nom={nom}, valeur=<masquée>)"
                rendus = (repr(s), str(s), f"{s}", f"{s:>20}", "%s" % s,
                          "{}".format(s), "%r" % (s,))
                for rendu in rendus:
                    self.assertEqual(rendu, attendu)
                sortie = io.StringIO()
                with contextlib.redirect_stdout(sortie):
                    print(s)
                with self.assertLogs("t898", level="WARNING") as journal:
                    logging.getLogger("t898").warning("%s", s)
                for texte in (sortie.getvalue(), "\n".join(journal.output)):
                    self.assertNotIn(valeur, texte)
                    self.assertIn("<masquée>", texte)
                self.assertEqual(s.reveler(), valeur)

    def test_A7_ni_json_ni_concatenation_ni_vars(self):
        """Mutant : `class Secret(str)` ⇒ `"x" + s` réussit ⇒ rouge."""
        nom, valeur = "MASQUE_T898", "hun" + "ter2"
        with environnement({nom: valeur}):
            s = resoudre_secret(nom)
        operations = {"json": lambda: json.dumps(s), "concaténation": lambda: "x" + s,
                      "vars": lambda: vars(s)}
        for etiquette, operation in operations.items():
            with self.subTest(etiquette):
                with self.assertRaises(TypeError) as cm:
                    operation()
                self.assertNotIn(valeur, str(cm.exception))

    def test_A7_une_resolution_n_ecrit_rien(self):
        """Mutant : `print(valeur)` ou `logging.debug` dans le module ⇒ rouge."""
        nom, absent = "MASQUE_T898", "ABSENT_T898"
        sortie, erreur = io.StringIO(), io.StringIO()
        with environnement({nom: "hun" + "ter2", absent: None}), \
                contextlib.redirect_stdout(sortie), contextlib.redirect_stderr(erreur), \
                self.assertNoLogs(level=logging.DEBUG):
            resoudre_secret(nom)
            with self.assertRaises(SecretAbsent):
                resoudre_secret(absent)
            with self.assertRaises(NomSecretInvalide):
                resoudre_secret("a b")
        self.assertEqual(sortie.getvalue(), "")
        self.assertEqual(erreur.getvalue(), "")


class SerialisationTests(unittest.TestCase):
    """A8 — un `Secret` ne se copie ni ne se sérialise."""

    def test_A8_copie_et_pickle_levent_TypeError(self):
        """Mutant : `__getstate__` retiré ⇒ `copy.copy` réussit ⇒ rouge."""
        nom, valeur = "SERIAL_T898", "hun" + "ter2"
        with environnement({nom: valeur}):
            s = resoudre_secret(nom)
        operations = {
            "copy": lambda: copy.copy(s),
            "deepcopy": lambda: copy.deepcopy(s),
            "pickle 0": lambda: pickle.dumps(s, protocol=0),
            "pickle 2": lambda: pickle.dumps(s, protocol=2),
            "pickle 5": lambda: pickle.dumps(s, protocol=5),
            "__getstate__": lambda: s.__getstate__(),
            "__reduce_ex__": lambda: s.__reduce_ex__(4),
            "__reduce__": lambda: s.__reduce__(),
        }
        for etiquette, operation in operations.items():
            with self.subTest(etiquette):
                with self.assertRaises(TypeError) as cm:
                    operation()
                self.assertNotIn(valeur, str(cm.exception))


class ExceptionsCopiablesTests(unittest.TestCase):
    """A9 et C1 — les exceptions survivent à la copie ; message = unique argument."""

    def _exceptions(self) -> list[ErreurSecret]:
        nom = "EXC_T898"
        with environnement({nom: None}):
            absente = _leve(self, SecretAbsent, nom)
        with environnement({nom: " "}):
            vide = _leve(self, SecretAbsent, nom)
        invalide = _leve(self, NomSecretInvalide, "a b")
        return [absente, vide, invalide]  # type: ignore[list-item]

    def test_A9_copie_reconstruit_meme_type_meme_texte(self):
        """Mutant : constructeur à deux arguments (`__init__(self, nom, statut)`)
        ⇒ `copy.deepcopy` lève `TypeError` à la reconstruction ⇒ rouge."""
        for exc in self._exceptions():
            self.assertEqual(exc.args, (str(exc),))
            self.assertEqual(exc.__reduce__()[1], (str(exc),))
            for copieur in (copy.copy, copy.deepcopy):
                with self.subTest(type(exc).__name__, copieur=copieur.__name__):
                    double = copieur(exc)
                    self.assertIs(type(double), type(exc))
                    self.assertEqual(str(double), str(exc))
                    if isinstance(exc, SecretAbsent):
                        self.assertEqual((double.nom, double.statut), (exc.nom, exc.statut))
            for protocole in range(pickle.HIGHEST_PROTOCOL + 1):
                self.assertTrue(pickle.dumps(exc, protocol=protocole))


def _cadres_du_module(exc: BaseException) -> list[traceback.FrameSummary]:
    pile = traceback.TracebackException.from_exception(exc, capture_locals=True).stack
    cible = Path(identifiants.__file__).resolve()
    return [cadre for cadre in pile if Path(cadre.filename).resolve() == cible]


class LocauxDeCadreTests(unittest.TestCase):
    """A10 — le cadre qui lève ne tient ni la table d'environnement ni une valeur."""

    def test_A10_aucun_local_ne_porte_l_environnement(self):
        """Mutants : `environ = os.environ` dans `resoudre_secret` ⇒ rouge ;
        `raise` DANS `_lire_env` ⇒ son cadre (qui tient la table) ⇒ rouge ;
        `_lire_env` lève `LookupError`, que `resoudre_secret` attrape pour lever
        `_absent` (avec ou sans `from None`) ⇒ exception chaînée ⇒ rouge (T1,
        S-00004537 : la pile seule ne voit pas la chaîne)."""
        sentinelle = SENTINELLE + "z" * 12
        absent, invalide = "ABSENT_T898", "a b"
        with environnement({"AUTRE_T898": sentinelle, absent: None}):
            cas = ((absent, SecretAbsent), (invalide, NomSecretInvalide))
            for nom, classe in cas:
                with self.subTest(classe.__name__):
                    exc = _leve(self, classe, nom)
                    self.assertIsNone(exc.__context__)
                    trace = "".join(traceback.TracebackException.from_exception(
                        exc, capture_locals=True).format())
                    self.assertFalse(SENTINELLE in trace,
                                     "table d'environnement dans la trace, chaîne comprise")
                    cadres = _cadres_du_module(exc)
                    self.assertTrue(cadres, "aucun cadre du module : témoin vacant")
                    self.assertIn("nom", cadres[0].locals or {})
                    for cadre in cadres:
                        for local, rendu in (cadre.locals or {}).items():
                            self.assertNotIn(SENTINELLE, rendu, f"{cadre.name}:{local}")


def _construit(test: unittest.TestCase, classe: type[BaseException], nom: object,
               valeur: object) -> BaseException:
    """Le refus de `Secret(nom, valeur)`, AVEC sa trace (même raison que `_leve`).
    La valeur est un local de CE cadre : un témoin ne juge que les cadres du module."""
    try:
        Secret(nom, valeur)  # type: ignore[arg-type]
    except classe as exc:
        test.assertIsNotNone(exc.__traceback__)
        return exc
    test.fail(f"{classe.__name__} attendue, rien n'a été levé")


class ConstructeurTests(unittest.TestCase):
    """L1 (S-00004531) et T2 (S-00004537) — `Secret` construit en direct tient les
    invariants de `resoudre_secret`, et un refus ne laisse pas la valeur en clair."""

    def test_L1_le_constructeur_refuse_nom_et_valeur_hors_forme(self):
        """Mutants : validation du nom retirée de `__init__` ⇒ rouge ; contrôle de
        la valeur retiré ⇒ `None` ou `""` acceptés ⇒ rouge ; `self.nom = nom` ⇒ rouge."""
        for nom in NomTests.INVALIDES:
            with self.subTest(nom=repr(nom)):
                _construit(self, NomSecretInvalide, nom, "v")
        refus = ((None, TypeError), (b"v", TypeError), ("", ValueError),
                 ("   ", ValueError), ("\N{IDEOGRAPHIC SPACE}", ValueError))
        for valeur, classe in refus:
            with self.subTest(valeur=repr(valeur)):
                _construit(self, classe, "A_T898", valeur)
        for valeur in ("v", "\N{ZERO WIDTH SPACE}", "tok\r"):
            with self.subTest(acceptee=repr(valeur)):
                s = Secret("A_T898", valeur)
                self.assertEqual((s.nom, s.reveler()), ("A_T898", valeur))
        self.assertEqual(Secret(JETON, "v").nom, MARQUE)

    def test_L1_un_refus_ne_laisse_la_valeur_dans_aucun_cadre(self):
        """Mutants : `del valeur` retiré ⇒ la valeur est un local du cadre qui lève
        ⇒ rouge ; `nom` provisoire retiré ⇒ `repr(self)` échoue (3.11 : lève ;
        3.12+ : `<local repr() failed>`) ⇒ rouge."""
        brute = SENTINELLE + "z" * 12
        cas = (("a b", brute, NomSecretInvalide), (b"A", brute, NomSecretInvalide),
               ("A_T898", [brute], TypeError), ("A_T898", brute.encode(), TypeError))
        for nom, valeur, classe in cas:
            with self.subTest(classe.__name__, valeur=type(valeur).__name__):
                exc = _construit(self, classe, nom, valeur)
                self.assertIsNone(exc.__context__)
                self.assertNotIn(SENTINELLE, str(exc))
                cadres = _cadres_du_module(exc)
                self.assertEqual([c.name for c in cadres][-1:], ["__init__"],
                                 "cadre du constructeur non vu : témoin vacant")
                self.assertIn("<masquée>", (cadres[-1].locals or {}).get("self", ""))
                for cadre in cadres:
                    for local, rendu in (cadre.locals or {}).items():
                        self.assertFalse(SENTINELLE in rendu, f"{cadre.name}:{local}")


IMPORTS_PERMIS ={"__future__", "os", "re", "collections.abc", "cadre.ledger.redaction"}
NOMS_PUBLICS = ["resoudre_secret", "Secret", "ErreurSecret", "SecretAbsent",
                "NomSecretInvalide"]


def _imports(arbre: ast.AST) -> set[str]:
    vus: set[str] = set()
    for n in ast.walk(arbre):
        if isinstance(n, ast.Import):
            vus.update(a.name for a in n.names)
        elif isinstance(n, ast.ImportFrom):
            vus.add("." * n.level + (n.module or ""))
    return vus


def _fautes_ast(source: str) -> list[str]:
    """Les écarts de A11 : import hors liste, littéral du préfixe du contrat,
    appel `print`, `__all__` différent des cinq noms."""
    arbre = ast.parse(source)
    fautes = [f"import {m}" for m in sorted(_imports(arbre) - IMPORTS_PERMIS)]
    for n in ast.walk(arbre):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) \
                and n.value.startswith(PREFIXE_CONTRAT):
            fautes.append(f"{n.lineno} littéral {n.value}")
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "print":
            fautes.append(f"{n.lineno} print")
        elif isinstance(n, ast.Assign) and any(
                isinstance(c, ast.Name) and c.id == "__all__" for c in n.targets):
            if ast.literal_eval(n.value) != NOMS_PUBLICS:
                fautes.append(f"{n.lineno} __all__")
    return fautes


class AstDuModuleTests(unittest.TestCase):
    """A11 — imports, `__all__`, littéraux et `print`, lus sur l'arbre."""

    def test_A11_le_module_reel_n_a_aucune_faute(self):
        """Mutants : `import subprocess` ⇒ rouge ; `_ENV_ZZ = "<préfixe>ZZ"` ⇒ rouge."""
        self.assertEqual(MODULE.resolve(), Path(identifiants.__file__).resolve())
        self.assertEqual(_fautes_ast(MODULE.read_text(encoding="utf-8")), [])
        self.assertEqual(identifiants.__all__, NOMS_PUBLICS)

    def test_A11_le_detecteur_mord(self):
        """Contrôle négatif : chaque mutant, ajouté au source réel, est vu."""
        source = MODULE.read_text(encoding="utf-8")
        mutants = {
            "import subprocess": "\nimport subprocess\n",
            "littéral": f'\n_ENV_ZZ = "{PREFIXE_CONTRAT}ZZ_T898"\n',
            "print": "\nprint(1)\n",
            "__all__": '\n__all__ = ["resoudre_secret"]\n',
        }
        for etiquette, ajout in mutants.items():
            with self.subTest(etiquette):
                self.assertTrue(_fautes_ast(source + ajout))


class PerimetreDuFiletTests(unittest.TestCase):
    """A12 — le module est au périmètre du filet de pureté, et y passe
    (forme du précédent `test_T8_le_module_neuf_est_au_perimetre_du_filet_et_y_passe`)."""

    def test_A12_au_perimetre_et_sans_fautif(self):
        """Mutant : `import subprocess` dans le module ⇒ fautif ⇒ rouge."""
        import test_cadre_package as paquet  # noqa: PLC0415 — import au témoin, jamais à la collecte

        banc = paquet.OrchestrationPurityTests()
        chemin = paquet.PKG / "identifiants.py"
        self.assertIn(chemin, banc._modules_d_orchestration())
        self.assertEqual(banc._fautifs_purete([chemin], paquet.PKG), [])
        self.assertEqual(chemin.resolve(), Path(identifiants.__file__).resolve())
        with tempfile.TemporaryDirectory() as dossier:
            racine = Path(dossier)
            copie = racine / "identifiants.py"
            copie.write_text(chemin.read_text(encoding="utf-8") + "\nimport subprocess\n",
                             encoding="utf-8")
            self.assertTrue(banc._fautifs_purete([copie], racine),
                            "copie fantôme impure non vue : témoin vacant")


def _lignes_qui_importent_la_couche(source: str) -> list[int]:
    """Les lignes qui importent `identifiants`, sous toutes les formes : absolue,
    `from cadre import identifiants`, relative."""
    lignes = []
    for n in ast.walk(ast.parse(source)):
        if isinstance(n, ast.Import):
            if any(a.name.split(".")[-1] == "identifiants" for a in n.names):
                lignes.append(n.lineno)
        elif isinstance(n, ast.ImportFrom):
            module = n.module or ""
            if module.split(".")[-1] == "identifiants" or (
                    (module == "cadre" or n.level) and
                    any(a.name == "identifiants" for a in n.names)):
                lignes.append(n.lineno)
    return lignes


class CycleDImportTests(unittest.TestCase):
    """C4 — l'import de la couche charge le paquet ledger, `cadre.paths` et
    `cadre.workspace` (mesuré, et relevé ici dans un interpréteur neuf) : aucun
    d'eux ne peut importer la couche sans cycle."""

    CODE = ("import sys\nsys.path.insert(0, sys.argv[1])\nimport cadre.identifiants\n"
            "for n, m in sorted(sys.modules.items()):\n"
            "    if n.startswith('cadre') and n != 'cadre.identifiants':\n"
            "        print(getattr(m, '__file__', None) or '')\n")

    def _charges(self) -> list[Path]:
        sortie = subprocess.run(
            [sys.executable, "-I", "-c", self.CODE, str(SRC)],
            capture_output=True, text=True, encoding="utf-8", timeout=120, check=True,
        ).stdout
        return [Path(ligne) for ligne in sortie.splitlines() if ligne]

    def test_C4_aucun_module_charge_n_importe_la_couche(self):
        """Mutant : `from cadre import identifiants` ajouté à `paths.py` ⇒ rouge."""
        charges = self._charges()
        relatifs = {p.resolve().relative_to(SRC.resolve()).as_posix() for p in charges}
        # Non-vacuité sur la seule dépendance DIRECTE de la couche : `paths` et
        # `workspace` sont un couplage de zone A, libre de disparaître (T5, S-00004537).
        for attendu in ("cadre/ledger/redaction.py",):
            self.assertIn(attendu, relatifs, "fermeture d'import non vue : témoin vacant")
        fautes = {
            p.name: lignes for p in charges
            if (lignes := _lignes_qui_importent_la_couche(p.read_text(encoding="utf-8")))
        }
        self.assertEqual(fautes, {})

    def test_C4_le_detecteur_mord(self):
        """Contrôle négatif : chaque forme d'import, ajoutée à `paths.py`, est vue."""
        source = (SRC / "cadre" / "paths.py").read_text(encoding="utf-8")
        for ajout in ("from cadre import identifiants", "import cadre.identifiants",
                      "from cadre.identifiants import Secret", "from . import identifiants",
                      "from .identifiants import Secret", "from .. import identifiants"):
            with self.subTest(ajout):
                self.assertTrue(_lignes_qui_importent_la_couche(source + "\n" + ajout + "\n"))


if __name__ == "__main__":
    unittest.main()
