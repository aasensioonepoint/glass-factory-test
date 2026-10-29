#!/usr/bin/env python3
"""BANCS DE `cadre hook <evenement> --host <hote>` — T-00000862.

CE QUE LA TÂCHE PROMET, ET CE QUE CHAQUE TÉMOIN TIENT :
  * H1 — le refus d'une GARDE sort par le canal de l'hôte, forme exacte, sur les
    cinq hôtes : claude, stderr et 2, stdout vide ; codex, gemini, copilot,
    kimi, l'enveloppe `deny` sur stdout et 0 (copilot : plus les clés plates),
    `hookEventName` CANONIQUE (`PreToolUse`, jamais la graphie native
    `preToolUse` de copilot). Le premier refus l'emporte.
  * H1b — la même chose EN PROCESSUS par `cli.main`, l'entrée standard patchée
    en `io.TextIOWrapper(io.BytesIO(…))` (un `StringIO` n'a pas `.buffer`) et
    la garde patchée par `cadre.hook.resoudre`.
  * H2 — laisser passer : rien sur aucun flux, code 0, sur les cinq hôtes, par
    l'API, par `cli.main` et de bout en bout ; la table de production est vide.
    Une garde EN FAUTE — elle lève quoi que ce soit (toute `BaseException` :
    `SystemExit` 0 ou 2, `KeyboardInterrupt`, `GeneratorExit`), ou rend autre
    chose que `None` ou un `Refus` — n'est JAMAIS un laisser-passer ni un
    traceback : un refus par le canal de l'hôte, `cadre hook : garde en faute
    (<type>)`, le message de l'exception jamais repris ; claude 2, enveloppe et
    0 ailleurs, jamais 1 ni un 0 silencieux ; par l'API, par `cli.main` et de
    bout en bout.
  * H3 — événement INCONNU : claude 2 ; enveloppe `deny` et 0 ailleurs,
    `hookEventName` = l'argument tel que reçu (S-01M54WTQTHB14SH0W0KZTHNCYB).
  * H4 — `SessionEnd --host codex` (cellule absente de la table) : refus par le
    canal de l'hôte, avec la raison.
  * H5 — payload vide, non-JSON, liste, trop imbriqué, non UTF-8, BOM UTF-8 :
    refus par le canal de l'hôte ; un `\\ud800` repris dans la raison est rendu
    ÉCHAPPÉ, sans traceback, même sur un flux strict.
  * H6 — `--host antigravity` : 2, le refus et l'aide nomment gemini ; l'API
    lève `HoteInconnu`.
  * H7 — `--host claude --hots x` : 2 « inconnue » ; `--host` absent : 2, un
    refus distinct.
  * H8 — `hook` est hors de `RESERVEES`, dans `IMPLEMENTEES`, et `public` au
    verrou. H8b — chaque « refus honoré sur PreToolUse » du verrou et de
    CONTRAT-v0.md porte sa portée PAR HÔTE (Gemini CLI et Antigravity
    inertes-mesurés). H8c — les surfaces qui le disaient réservé (guardrails
    SKILL, `.agents/README.md`) ne le disent plus.
  * H9 — `cadre/hook.py` ne référence ni les flux standard de `sys` (doubles
    dunder et nom en chaîne compris), ni `print`, `input`, `open`,
    `__import__`, ni `subprocess`, `os` ou `builtins`, et n'importe que sa
    liste fermée : relevé sur l'ARBRE SYNTAXIQUE ; chaque forme est vue rouge
    sur une COPIE MUTÉE de `hook.py`, avec un contrôle négatif du détecteur.
  * H10 — l'entrée standard PAR `cli.main`, la couture d'E/S, jamais par l'API
    pure : octets non UTF-8, BOM, entrée fermée (`sys.stdin` vaut `None`),
    lecture qui lève `OSError`, et toute AUTRE `Exception` de la lecture
    (`ValueError` d'un flux clos, `AttributeError` d'un flux sans `.buffer`) —
    refus par le canal de l'hôte et code vérifiés sur les cinq hôtes ; non
    UTF-8 et BOM aussi de bout en bout, sur la vraie entrée standard d'un
    processus.
  * H11 — une table des gardes EN FAUTE : `resoudre()` qui lève (toute
    `BaseException`), ou une entrée qui n'est pas une séquence de gardes —
    refus `cadre hook : table des gardes en faute (<type>)` par le canal de
    l'hôte, par l'API, par `cli.main` et de bout en bout ; jamais 1 ni un 0
    silencieux.
  * H12 — chaque garde reçoit SA copie du payload : une garde qui le mute
    (`pop("tool_input")`, ou une écriture imbriquée) n'aveugle pas la
    suivante, dont le refus sort par le canal de l'hôte, par l'API et par
    `cli.main` (revue de clôture commune : payload partagé ⇒ code 0).

Chaque témoin a été vu rougir sur une mutation nommée (rapport de T-00000862 et
de sa passe de correction).
"""

from __future__ import annotations

import ast
import importlib.util
import io
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
# Le paquet `cadre` de CETTE racine, chargé par chemin (`.agents/vendor/cadre`
# d'abord, `src/cadre` ensuite) ; `SRC` est son parent d'import.
_SPEC_VENDOR = importlib.util.spec_from_file_location(
    "_cadre_hook_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
assert _SPEC_VENDOR is not None and _SPEC_VENDOR.loader is not None
_VENDOR = importlib.util.module_from_spec(_SPEC_VENDOR)
sys.modules[_SPEC_VENDOR.name] = _VENDOR
_SPEC_VENDOR.loader.exec_module(_VENDOR)
_VENDOR.charger_paquet(ROOT, "cadre")
SRC = _VENDOR.exiger(ROOT, "cadre").parent

from cadre import cli  # noqa: E402
from cadre import hook as hk  # noqa: E402
from cadre.config import HOTES, HoteInconnu  # noqa: E402

LOCK = ROOT / "contract.lock.json"
DOC = ROOT / "docs" / "contrat" / "CONTRAT-v0.md"
HOOK_PY = SRC / "cadre" / "hook.py"
PAYLOAD = b'{"tool_name":"Bash","tool_input":{"command":"ls"}}'
RAISON = "garde de test : commande refusee"
CLES_PLATES = {"permissionDecision", "permissionDecisionReason"}


def _refusant(raison: str = RAISON):
    """Une garde qui refuse toujours, avec `raison`."""
    def garde(payload):
        return hk.Refus(raison)
    return garde


def _laissant(payload):
    """Une garde qui laisse toujours passer."""
    return None


#: Un texte qu'une faute porte dans son MESSAGE : il ne doit sortir sur aucun
#: flux — un message d'exception peut citer le payload.
SECRET = "secret-du-payload"


def _levant(cls: type[BaseException], *args: object):
    """Une garde qui lève `cls(*args)`, une instance NEUVE à chaque appel."""
    def garde(payload):
        raise cls(*args)
    return garde


class _RefusTordu(hk.Refus):
    """Un `Refus` dérivé qui contourne `__post_init__` : sa raison peut ne pas
    être une `str`, et sa sérialisation lèverait hors de toute protection."""

    def __post_init__(self) -> None:
        pass


#: (nom, garde en faute, type nommé par le refus). Les retours FAUX (`0`,
#: `False`) tiennent la frontière `is None` : un `if not verdict` les
#: laisserait passer.
FAUTES = (
    ("leve KeyError", _levant(KeyError, SECRET), "KeyError"),
    ("leve ValueError", _levant(ValueError, SECRET), "ValueError"),
    ("leve RecursionError", _levant(RecursionError, SECRET), "RecursionError"),
    ("leve OSError", _levant(OSError, 5, SECRET), "OSError"),
    ("leve SystemExit(0)", _levant(SystemExit, 0), "SystemExit"),
    ("leve SystemExit(2)", _levant(SystemExit, 2), "SystemExit"),
    ("leve GeneratorExit", _levant(GeneratorExit, SECRET), "GeneratorExit"),
    ("leve KeyboardInterrupt", _levant(KeyboardInterrupt, SECRET), "KeyboardInterrupt"),
    ("construit un Refus sans raison", lambda payload: hk.Refus(""), "ValueError"),
    ("rend une chaine", lambda payload: SECRET, "TypeError"),
    ("rend True", lambda payload: True, "TypeError"),
    ("rend False", lambda payload: False, "TypeError"),
    ("rend 0", lambda payload: 0, "TypeError"),
    ("rend un dict", lambda payload: {"raison": SECRET}, "TypeError"),
    ("rend un Refus a raison non str", lambda payload: _RefusTordu(object()), "TypeError"),
)


def _faute(type_: str) -> str:
    """La raison EXACTE du refus d'une garde en faute."""
    return f"cadre hook : garde en faute ({type_})"


class _EntreeQuiCasse:
    """Un `sys.stdin` dont TOUTE lecture lève `exc` — octets (`.buffer.read`)
    comme texte (`.read`)."""

    def __init__(self, exc: BaseException) -> None:
        self.buffer = self
        self._exc = exc

    def read(self, *args: object) -> bytes:
        raise self._exc


#: Le programme d'un processus, `argv` = hôte, lieu, faute, secret : il fait
#: lever la faute nommée par UNE garde branchée par la couture
#: `cadre.hook.resoudre` (lieu `garde`), ou par `resoudre` elle-même (lieu
#: `table`), puis joue `cli.main` — la vraie entrée et les vrais flux d'un
#: processus, donc son VRAI code de sortie.
_PROG_EN_FAUTE = (
    "import sys\n"
    "from cadre import cli, hook\n"
    "hote, lieu, nom, secret = sys.argv[1:5]\n"
    "FAUTES = {'KeyError': lambda: KeyError(secret), 'OSError': lambda: OSError(5, secret),\n"
    "          'SystemExit0': lambda: SystemExit(0), 'SystemExit2': lambda: SystemExit(2),\n"
    "          'KeyboardInterrupt': lambda: KeyboardInterrupt(secret)}\n"
    "def garde(payload):\n"
    "    raise FAUTES[nom]()\n"
    "def table():\n"
    "    raise FAUTES[nom]()\n"
    "hook.resoudre = table if lieu == 'table' else (lambda: {'PreToolUse': (garde,)})\n"
    "sys.exit(cli.main(['hook', 'PreToolUse', '--host', hote]))\n"
)


def _jouer_processus(hote: str, lieu: str, faute: str) -> hk.Reponse:
    """`_PROG_EN_FAUTE` dans un processus ; sa sortie en `Reponse` (ASCII)."""
    r = subprocess.run(
        [sys.executable, "-c", _PROG_EN_FAUTE, hote, lieu, faute, SECRET],
        input=PAYLOAD, capture_output=True, env=dict(os.environ, PYTHONPATH=str(SRC)),
        timeout=60, check=False)
    return hk.Reponse(r.stdout.decode("ascii", "replace"), r.stderr.decode("ascii", "replace"),
                      r.returncode)


def _jouer(argv: list[str], entree: object) -> tuple[int, hk.Reponse]:
    """`cli.main(argv)` en processus, flux patchés STRICTS en UTF-8.

    `entree` en OCTETS : l'entrée est un `TextIOWrapper` STRICT sur eux — `cli`
    lit `.buffer`, et une lecture TEXTE d'octets non UTF-8 y lève, comme sur
    l'entrée standard d'un poste UTF-8. Tout autre `entree` est posé TEL QUEL
    en `sys.stdin` : `None` (entrée fermée), ou un double qui lève. Les
    sorties sont des `TextIOWrapper` aux erreurs `strict` : un surrogate isolé
    y lève `UnicodeEncodeError`, comme sur le vrai flux d'un poste UTF-8. Le
    code de sortie vient du retour, ou de `SystemExit` (argparse). Une
    `BaseException` hors `Exception` qui S'ÉCHAPPE (`KeyboardInterrupt`) est
    un ÉCHEC du témoin, jamais l'interruption de toute la session pytest.
    """
    stdin = (io.TextIOWrapper(io.BytesIO(entree), encoding="utf-8", errors="strict")
             if isinstance(entree, bytes) else entree)
    sortie = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    erreur = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    with mock.patch.object(sys, "stdin", stdin), \
            mock.patch.object(sys, "stdout", sortie), \
            mock.patch.object(sys, "stderr", erreur):
        try:
            code = cli.main(argv)
        except SystemExit as exc:
            code = exc.code
        except BaseException as exc:  # noqa: BLE001 — échec propre, pas d'arrêt de session
            if isinstance(exc, Exception):
                raise
            raise AssertionError(
                f"une faute s'échappe de cli.main : {type(exc).__name__}") from exc
    sortie.flush()
    erreur.flush()
    rendu = hk.Reponse(sortie.buffer.getvalue().decode("utf-8"),
                       erreur.buffer.getvalue().decode("utf-8"), code)
    return code, rendu


class _Banc(unittest.TestCase):
    def repartir_sans_fuite(self, *args) -> hk.Reponse:
        """`hk.repartir(*args)` ; une faute qui s'en ÉCHAPPE est un ÉCHEC du
        témoin — un `KeyboardInterrupt` libre arrêterait toute la session."""
        try:
            return hk.repartir(*args)
        except BaseException as exc:  # noqa: BLE001 — échec propre, pas d'arrêt de session
            self.fail(f"une faute s'échappe de repartir : {type(exc).__name__}")

    def assert_refus(self, rep: hk.Reponse, hote: str, evenement: str,
                     raison: str | None = None) -> str:
        """La forme EXACTE du refus par le canal de `hote` ; rend la raison."""
        self.assertTrue(rep.stdout.isascii() and rep.stderr.isascii(),
                        f"une Reponse est de l'ASCII pur : {rep!r}")
        if hote == "claude":
            self.assertEqual(rep.stdout, "", "claude : le refus n'écrit RIEN sur stdout")
            self.assertEqual(rep.code, 2)
            tete = f"cadre hook {json.dumps(evenement)} --host claude : REFUS : "
            self.assertTrue(rep.stderr.startswith(tete), rep.stderr)
            self.assertTrue(rep.stderr.endswith("\n"), rep.stderr)
            lue = json.loads(rep.stderr[len(tete):-1])
        else:
            self.assertEqual(rep.stderr, "", f"{hote} : le refus n'écrit rien sur stderr")
            self.assertEqual(rep.code, 0, f"{hote} : enveloppe et code 0, jamais 2")
            self.assertTrue(rep.stdout.endswith("\n"), rep.stdout)
            objet = json.loads(rep.stdout)
            cles = {"hookSpecificOutput"} | (CLES_PLATES if hote == "copilot" else set())
            self.assertEqual(set(objet), cles, f"{hote} : clés de l'enveloppe")
            lue = objet["hookSpecificOutput"].get("permissionDecisionReason")
            self.assertEqual(
                objet["hookSpecificOutput"],
                {"hookEventName": evenement, "permissionDecision": "deny",
                 "permissionDecisionReason": lue})
            if hote == "copilot":
                self.assertEqual((objet["permissionDecision"], objet["permissionDecisionReason"]),
                                 ("deny", lue))
        self.assertIsInstance(lue, str)
        self.assertTrue(lue.strip(), "un refus porte sa raison")
        if raison is not None:
            self.assertEqual(lue, raison)
        return lue


class RefusGardeTests(_Banc):
    """H1 et H1b."""

    def test_H1_chaque_hote_a_son_canal_decide(self):
        self.assertEqual({"claude"} | hk.HOTES_A_ENVELOPPE, set(HOTES))
        self.assertNotIn("claude", hk.HOTES_A_ENVELOPPE)

    def test_H1_refus_d_une_garde_par_le_canal_de_l_hote(self):
        for hote in HOTES:
            with self.subTest(hote=hote):
                rep = hk.repartir("PreToolUse", hote, PAYLOAD, {"PreToolUse": (_refusant(),)})
                self.assert_refus(rep, hote, "PreToolUse", RAISON)

    def test_H1_hookEventName_est_canonique_meme_chez_copilot(self):
        rep = hk.repartir("PreToolUse", "copilot", PAYLOAD, {"PreToolUse": (_refusant(),)})
        objet = json.loads(rep.stdout)
        self.assertEqual(objet["hookSpecificOutput"]["hookEventName"], "PreToolUse")

    def test_H1_le_premier_refus_l_emporte_et_l_evenement_est_cible(self):
        appels = []

        def autre(payload):
            appels.append(payload)
            return hk.Refus("garde d'un autre evenement")

        table = {"PreToolUse": (_laissant, _refusant("A"), _refusant("B")),
                 "Stop": (autre,)}
        for hote in HOTES:
            with self.subTest(hote=hote):
                self.assert_refus(hk.repartir("PreToolUse", hote, PAYLOAD, table),
                                  hote, "PreToolUse", "A")
        self.assertEqual(appels, [], "une garde d'un autre événement a été appelée")

    def test_H12_une_garde_qui_mute_le_payload_n_aveugle_pas_la_suivante(self):
        """Garde A mute le payload, garde B refuse sur `tool_input` : le refus
        de B sort. Payload PARTAGÉ : B ne voit plus `tool_input` et laisse
        passer, code 0 ; copie SUPERFICIELLE : l'écriture imbriquée l'aveugle
        encore."""
        def videuse(payload):
            payload.pop("tool_input")

        def ecraseuse(payload):
            payload["tool_input"]["command"] = "autre"

        def juge(payload):
            entree = payload.get("tool_input")
            if isinstance(entree, dict) and entree.get("command") == "ls":
                return hk.Refus(RAISON)
            return None

        for nom, premiere in (("pop", videuse), ("ecriture imbriquee", ecraseuse)):
            table = {"PreToolUse": (premiere, juge)}
            for hote in HOTES:
                with self.subTest(mutation=nom, hote=hote, par="api"):
                    self.assert_refus(self.repartir_sans_fuite("PreToolUse", hote, PAYLOAD, table),
                                      hote, "PreToolUse", RAISON)
                with self.subTest(mutation=nom, hote=hote, par="cli.main"), \
                        mock.patch.object(hk, "resoudre", return_value=table):
                    code, rep = _jouer(["hook", "PreToolUse", "--host", hote], PAYLOAD)
                    self.assertEqual(code, 2 if hote == "claude" else 0)
                    self.assert_refus(rep, hote, "PreToolUse", RAISON)

    def test_H1b_cli_main_en_processus_rend_le_refus_de_la_garde(self):
        table = {"PreToolUse": (_refusant(),)}
        for hote in HOTES:
            with self.subTest(hote=hote), \
                    mock.patch.object(hk, "resoudre", return_value=table):
                code, rep = _jouer(["hook", "PreToolUse", "--host", hote], PAYLOAD)
                self.assertEqual(code, rep.code)
                self.assert_refus(rep, hote, "PreToolUse", RAISON)


class LaisserTests(_Banc):
    """H2."""

    def test_H2_laisser_passer_ne_rend_rien_et_sort_en_0(self):
        for hote in HOTES:
            for table in ({}, {"PreToolUse": (_laissant,)}, hk.resoudre()):
                with self.subTest(hote=hote, table=table):
                    self.assertEqual(hk.repartir("PreToolUse", hote, PAYLOAD, table),
                                     hk.Reponse("", "", 0))

    def test_H2_la_table_de_production_est_vide(self):
        self.assertEqual(dict(hk.resoudre()), {})

    def test_H2_cli_main_laisse_passer_avec_la_table_de_production(self):
        for hote in HOTES:
            with self.subTest(hote=hote):
                code, rep = _jouer(["hook", "PreToolUse", "--host", hote], PAYLOAD)
                self.assertEqual((code, rep.stdout, rep.stderr), (0, "", ""))

    def test_H2_de_bout_en_bout(self):
        env = dict(os.environ, PYTHONPATH=str(SRC))
        for hote in HOTES:
            with self.subTest(hote=hote):
                r = subprocess.run(
                    [sys.executable, "-m", "cadre.cli", "hook", "PreToolUse", "--host", hote],
                    input=PAYLOAD, capture_output=True, env=env, timeout=60, check=False)
                self.assertEqual((r.returncode, r.stdout, r.stderr), (0, b"", b""))

    def test_H2_une_garde_en_faute_est_refusee_par_le_canal_de_l_hote(self):
        """Seule, ou entre une garde qui laisse et une qui refuse : la faute
        REFUSE, avec sa propre raison — ni un laisser-passer, ni la garde
        suivante appelée à sa place, ni le message de l'exception."""
        for nom, garde, type_ in FAUTES:
            for tables in ((garde,), (_laissant, garde, _refusant())):
                for hote in HOTES:
                    with self.subTest(garde=nom, gardes=len(tables), hote=hote):
                        rep = self.repartir_sans_fuite("PreToolUse", hote, PAYLOAD,
                                                       {"PreToolUse": tables})
                        self.assert_refus(rep, hote, "PreToolUse", _faute(type_))
                        self.assertNotIn(SECRET, rep.stdout + rep.stderr)

    def test_H2_un_refus_avant_la_faute_l_emporte_sans_l_appeler(self):
        appels = []

        def fautive(payload):
            appels.append(payload)
            raise KeyError(SECRET)

        for hote in HOTES:
            with self.subTest(hote=hote):
                rep = hk.repartir("PreToolUse", hote, PAYLOAD,
                                  {"PreToolUse": (_refusant(), fautive)})
                self.assert_refus(rep, hote, "PreToolUse", RAISON)
        self.assertEqual(appels, [], "la garde qui suit un refus a été appelée")

    def test_H2_une_garde_en_faute_par_cli_main_jamais_un_code_1(self):
        for nom, garde, type_ in FAUTES:
            for hote in HOTES:
                with self.subTest(garde=nom, hote=hote), \
                        mock.patch.object(hk, "resoudre",
                                          return_value={"PreToolUse": (garde,)}):
                    code, rep = _jouer(["hook", "PreToolUse", "--host", hote], PAYLOAD)
                    self.assertEqual(code, 2 if hote == "claude" else 0)
                    self.assert_refus(rep, hote, "PreToolUse", _faute(type_))
                    self.assertNotIn(SECRET, rep.stdout + rep.stderr)

    def test_H2_une_garde_en_faute_de_bout_en_bout(self):
        cas = {"KeyError": "KeyError", "SystemExit0": "SystemExit",
               "SystemExit2": "SystemExit", "KeyboardInterrupt": "KeyboardInterrupt"}
        for faute, type_ in cas.items():
            for hote in HOTES:
                with self.subTest(faute=faute, hote=hote):
                    rep = _jouer_processus(hote, "garde", faute)
                    self.assertNotIn("Traceback", rep.stderr)
                    self.assertNotIn(SECRET, rep.stdout + rep.stderr)
                    self.assertNotEqual((rep.code, rep.stdout), (0, ""),
                                        "un 0 silencieux est un laisser-passer")
                    self.assertEqual(rep.code, 2 if hote == "claude" else 0)
                    self.assert_refus(rep, hote, "PreToolUse", _faute(type_))

    def test_H2_un_refus_sans_raison_n_est_pas_constructible(self):
        for raison in ("", "   ", None):
            with self.subTest(raison=raison), self.assertRaises(ValueError):
                hk.Refus(raison)


class EvenementTests(_Banc):
    """H3 et H4."""

    def test_H3_un_evenement_inconnu_est_refuse_par_le_canal_de_l_hote(self):
        for evenement in ("Inconnu", "pre-tool-use", "preToolUse"):
            for hote in HOTES:
                with self.subTest(evenement=evenement, hote=hote):
                    rep = hk.repartir(evenement, hote, PAYLOAD, {})
                    raison = self.assert_refus(rep, hote, evenement)
                    self.assertIn("evenement canonique inconnu", raison)

    def test_H3_un_evenement_inconnu_par_cli_main(self):
        for hote in HOTES:
            with self.subTest(hote=hote):
                code, rep = _jouer(["hook", "Inconnu", "--host", hote], PAYLOAD)
                self.assertEqual(code, 2 if hote == "claude" else 0)
                self.assert_refus(rep, hote, "Inconnu")

    def test_H4_SessionEnd_sur_codex_est_refuse_avec_sa_raison(self):
        rep = hk.repartir("SessionEnd", "codex", PAYLOAD, {"SessionEnd": (_laissant,)})
        raison = self.assert_refus(rep, "codex", "SessionEnd")
        self.assertIn("n'est pas declare par l'hote codex", raison)
        self.assertIn(".codex/hooks.json", raison)

    def test_H4_chaque_cellule_absente_est_refusee(self):
        from cadre.hotes_evenements import TABLE  # noqa: PLC0415
        absentes = [(ev, h) for ev, ligne in TABLE.items() for h, g in ligne.items()
                    if g.natif is None]
        self.assertTrue(absentes, "aucune cellule absente : le témoin ne mesurerait rien")
        for evenement, hote in absentes:
            with self.subTest(evenement=evenement, hote=hote):
                self.assert_refus(hk.repartir(evenement, hote, PAYLOAD, {}), hote, evenement)


class PayloadTests(_Banc):
    """H5."""

    ILLISIBLES = {
        "vide": b"",
        "non-JSON": b"pas du json",
        "liste": b"[1, 2]",
        "chaine": b'"x"',
        "null": b"null",
        "trop imbrique": b"[" * 200000 + b"]" * 200000,
        "non UTF-8": b'{"x": "\xff"}',
        "BOM UTF-8": b"\xef\xbb\xbf{}",
    }

    def test_H5_un_payload_illisible_est_refuse_par_le_canal_de_l_hote(self):
        for nom, brut in self.ILLISIBLES.items():
            for hote in HOTES:
                with self.subTest(payload=nom, hote=hote):
                    raison = self.assert_refus(
                        hk.repartir("PreToolUse", hote, brut, {}), hote, "PreToolUse")
                    self.assertTrue(raison.startswith("cadre hook : payload"), raison)

    def test_H5_c_est_le_BOM_qui_est_refuse(self):
        self.assertEqual(hk.repartir("PreToolUse", "claude", b"{}", {}), hk.Reponse("", "", 0))
        rep = hk.repartir("PreToolUse", "claude", b"\xef\xbb\xbf{}", {})
        self.assertIn("BOM", self.assert_refus(rep, "claude", "PreToolUse"))

    def test_H5_un_surrogate_isole_est_rendu_echappe_sans_traceback(self):
        def garde(payload):
            return hk.Refus("chemin refuse : " + payload["chemin"])

        table = {"PreToolUse": (garde,)}
        for hote in HOTES:
            with self.subTest(hote=hote), \
                    mock.patch.object(hk, "resoudre", return_value=table):
                code, rep = _jouer(["hook", "PreToolUse", "--host", hote],
                                   b'{"chemin": "\\ud800"}')
                self.assertEqual(code, rep.code)
                self.assert_refus(rep, hote, "PreToolUse", "chemin refuse : \ud800")
                self.assertIn("\\ud800", rep.stdout + rep.stderr)

    @unittest.skipIf(os.name == "nt", "argv en octets : POSIX seulement")
    def test_H5_un_argv_non_UTF8_de_bout_en_bout_sans_traceback(self):
        env = dict(os.environ, PYTHONPATH=str(SRC))
        for hote in HOTES:
            with self.subTest(hote=hote):
                r = subprocess.run(
                    [sys.executable.encode(), b"-m", b"cadre.cli", b"hook", b"\xff",
                     b"--host", hote.encode()],
                    input=PAYLOAD, capture_output=True, env=env, timeout=60, check=False)
                self.assertNotIn(b"Traceback", r.stderr)
                rep = hk.Reponse(r.stdout.decode("ascii"), r.stderr.decode("ascii"),
                                 r.returncode)
                self.assert_refus(rep, hote, "\udcff")


class EntreeTests(_Banc):
    """H10 — l'entrée standard PAR `cli.main`, jamais par l'API pure : c'est la
    lecture de la CLI que ces témoins tiennent. Une lecture TEXTE
    (`flux.read().encode(…)`) rougit sur les octets non UTF-8, en processus
    comme de bout en bout."""

    NON_UTF8 = b'{"x": "\xff"}'
    BOM = b'\xef\xbb\xbf{"tool_name":"Bash"}'

    def _refus_par_cli(self, entree: object, debut: str, contient: str = "") -> None:
        for hote in HOTES:
            with self.subTest(hote=hote):
                code, rep = _jouer(["hook", "PreToolUse", "--host", hote], entree)
                self.assertEqual(code, 2 if hote == "claude" else 0)
                raison = self.assert_refus(rep, hote, "PreToolUse")
                self.assertTrue(raison.startswith(debut), raison)
                self.assertIn(contient, raison)

    def test_H10_des_octets_non_UTF8_par_cli_main(self):
        self._refus_par_cli(self.NON_UTF8,
                            "cadre hook : payload illisible, pas de l'UTF-8 strict")

    def test_H10_un_BOM_par_cli_main(self):
        self._refus_par_cli(self.BOM, "cadre hook : payload illisible, pas du JSON", "BOM")

    def test_H10_une_entree_fermee_par_cli_main(self):
        self._refus_par_cli(None, "cadre hook : payload illisible, pas du JSON")

    def test_H10_une_lecture_qui_leve_OSError_par_cli_main(self):
        for exc in (OSError(5, SECRET), BrokenPipeError(32, SECRET), BlockingIOError(11, SECRET)):
            for hote in HOTES:
                with self.subTest(faute=type(exc).__name__, hote=hote):
                    code, rep = _jouer(["hook", "PreToolUse", "--host", hote],
                                       _EntreeQuiCasse(exc))
                    self.assertEqual(code, 2 if hote == "claude" else 0)
                    self.assert_refus(
                        rep, hote, "PreToolUse",
                        f"cadre hook : entree standard illisible ({type(exc).__name__})")
                    self.assertNotIn(SECRET, rep.stdout + rep.stderr)

    def test_H10_une_lecture_qui_leve_hors_OSError_par_cli_main(self):
        """Toute `Exception` de la lecture refuse, pas seulement `OSError` :
        sous `except OSError`, ces trois-là s'échappaient de `cli.main`, un
        traceback en code 1, donc un échec OUVERT (revue de clôture commune)."""
        clos = io.TextIOWrapper(io.BytesIO(PAYLOAD), encoding="utf-8")
        clos.close()
        cas = (("ValueError levee par read", _EntreeQuiCasse(ValueError(SECRET)), "ValueError"),
               ("flux clos", clos, "ValueError"),
               ("flux sans .buffer", io.StringIO(PAYLOAD.decode("utf-8")), "AttributeError"))
        for nom, entree, type_ in cas:
            for hote in HOTES:
                with self.subTest(entree=nom, hote=hote):
                    code, rep = _jouer(["hook", "PreToolUse", "--host", hote], entree)
                    self.assertEqual(code, 2 if hote == "claude" else 0)
                    self.assert_refus(rep, hote, "PreToolUse",
                                      f"cadre hook : entree standard illisible ({type_})")
                    self.assertNotIn(SECRET, rep.stdout + rep.stderr)

    def test_H10_non_UTF8_et_BOM_de_bout_en_bout(self):
        env = dict(os.environ, PYTHONPATH=str(SRC))
        env.pop("PYTHONIOENCODING", None)
        cas = {"non UTF-8": (self.NON_UTF8, "pas de l'UTF-8 strict"),
               "BOM": (self.BOM, "BOM")}
        for nom, (brut, attendu) in cas.items():
            for hote in HOTES:
                with self.subTest(payload=nom, hote=hote):
                    r = subprocess.run(
                        [sys.executable, "-m", "cadre.cli", "hook", "PreToolUse", "--host", hote],
                        input=brut, capture_output=True, env=env, timeout=60, check=False)
                    self.assertNotIn(b"Traceback", r.stderr)
                    self.assertEqual(r.returncode, 2 if hote == "claude" else 0)
                    rep = hk.Reponse(r.stdout.decode("ascii"), r.stderr.decode("ascii"),
                                     r.returncode)
                    self.assertIn(attendu, self.assert_refus(rep, hote, "PreToolUse"))


def _table(type_: str) -> str:
    """La raison EXACTE du refus d'une table des gardes en faute."""
    return f"cadre hook : table des gardes en faute ({type_})"


class TableTests(_Banc):
    """H11 — la table des gardes, couture `resoudre()` que d'autres tâches
    brancheront : sa faute refuse par le canal de l'hôte, jamais un traceback."""

    def test_H11_une_entree_qui_n_est_pas_une_sequence_est_refusee(self):
        tables = {
            "une garde seule au lieu d'un tuple": ({"PreToolUse": _refusant()}, "TypeError"),
            "un nombre": ({"PreToolUse": 3}, "TypeError"),
            "une table None": (None, "AttributeError"),
        }
        for nom, (table, type_) in tables.items():
            for hote in HOTES:
                with self.subTest(table=nom, hote=hote):
                    rep = self.repartir_sans_fuite("PreToolUse", hote, PAYLOAD, table)
                    self.assert_refus(rep, hote, "PreToolUse", _table(type_))

    def test_H11_resoudre_qui_leve_par_cli_main(self):
        fautes = (OSError(5, SECRET), RuntimeError(SECRET), SystemExit(0), SystemExit(2),
                  KeyboardInterrupt(SECRET))
        for exc in fautes:
            for hote in HOTES:
                with self.subTest(faute=repr(exc), hote=hote), \
                        mock.patch.object(hk, "resoudre", side_effect=exc):
                    code, rep = _jouer(["hook", "PreToolUse", "--host", hote], PAYLOAD)
                    self.assertEqual(code, 2 if hote == "claude" else 0)
                    self.assert_refus(rep, hote, "PreToolUse", _table(type(exc).__name__))
                    self.assertNotIn(SECRET, rep.stdout + rep.stderr)

    def test_H11_resoudre_qui_leve_de_bout_en_bout(self):
        for faute, type_ in {"OSError": "OSError", "SystemExit0": "SystemExit"}.items():
            for hote in HOTES:
                with self.subTest(faute=faute, hote=hote):
                    rep = _jouer_processus(hote, "table", faute)
                    self.assertNotIn("Traceback", rep.stderr)
                    self.assertNotIn(SECRET, rep.stdout + rep.stderr)
                    self.assertNotEqual((rep.code, rep.stdout), (0, ""),
                                        "un 0 silencieux est un laisser-passer")
                    self.assertEqual(rep.code, 2 if hote == "claude" else 0)
                    self.assert_refus(rep, hote, "PreToolUse", _table(type_))


class HoteTests(_Banc):
    """H6 et H7."""

    def test_H6_antigravity_est_refuse_en_2_et_oriente_vers_gemini(self):
        for saisie in ("antigravity", "Antigravity"):
            with self.subTest(saisie=saisie):
                code, rep = _jouer(["hook", "PreToolUse", "--host", saisie], PAYLOAD)
                self.assertEqual(code, 2)
                self.assertEqual(rep.stdout, "")
                self.assertIn("herite de gemini", rep.stderr)
                self.assertNotIn("Traceback", rep.stderr)

    def test_H6_l_aide_nomme_gemini_pour_antigravity(self):
        code, rep = _jouer(["hook", "--help"], b"")
        self.assertEqual(code, 0)
        self.assertIn("(Antigravity : utiliser gemini)", " ".join(rep.stdout.split()))

    def test_H6_l_api_leve_HoteInconnu(self):
        for hote in ("antigravity", "x", None):
            with self.subTest(hote=hote), self.assertRaises(HoteInconnu):
                hk.repartir("PreToolUse", hote, PAYLOAD, {})

    def test_H7_une_option_inconnue_est_refusee_en_2(self):
        code, rep = _jouer(["hook", "PreToolUse", "--host", "claude", "--hots", "x"], PAYLOAD)
        self.assertEqual(code, 2)
        self.assertEqual(rep.stdout, "")
        self.assertIn("inconnue", rep.stderr)

    def test_H7_host_absent_est_un_refus_distinct_en_2(self):
        code, rep = _jouer(["hook", "PreToolUse"], PAYLOAD)
        self.assertEqual(code, 2)
        self.assertEqual(rep.stdout, "")
        self.assertIn("--host", rep.stderr)
        self.assertNotIn("inconnue", rep.stderr)
        self.assertNotIn("Traceback", rep.stderr)


class ContratTests(unittest.TestCase):
    """H8."""

    def test_H8_hook_est_implemente_et_public(self):
        self.assertNotIn("hook", cli.RESERVEES)
        self.assertIn("hook", cli.IMPLEMENTEES)
        verrou = json.loads(LOCK.read_text(encoding="utf-8"))
        entree = [e for e in verrou["elements"] if e["element"] == "cadre hook"]
        self.assertEqual(len(entree), 1)
        self.assertEqual((entree[0]["type"], entree[0]["statut"]), ("cli", "public"))

    #: (surface, tête de la phrase, portée qui doit la SUIVRE) — revue de clôture
    #: commune : sans portée, « refus honoré sur PreToolUse » se relit universel,
    #: alors que Gemini CLI et Antigravity sont INERTES-MESURÉS. La doc est lue
    #: espaces normalisés (la phrase y est coupée en lignes).
    PORTEE_DU_REFUS = (
        ("contract.lock.json", "Refus honore sur PreToolUse",
         " chez claude et codex (mesures), copilot en dossier approuve ; "
         "gemini et antigravity inertes-mesures ;"),
        ("docs/contrat/CONTRAT-v0.md", "Le refus est honoré sur `hook:PreToolUse`",
         " là où l'hôte charge et lit ses hooks — Claude Code et Codex, mesurés ; "
         "Copilot en dossier approuvé seulement ; Gemini CLI et Antigravity "
         "INERTES-MESURÉS"),
    )

    def test_H8b_le_refus_honore_porte_sa_portee_par_hote(self):
        """Chaque occurrence de la tête est suivie de SA portée : la phrase
        universelle d'avant la revue rougit, une seconde phrase sans portée
        aussi."""
        verrou = json.loads(LOCK.read_text(encoding="utf-8"))
        note = next(e["note"] for e in verrou["elements"] if e["element"] == "cadre hook")
        textes = {"contract.lock.json": note,
                  "docs/contrat/CONTRAT-v0.md": " ".join(DOC.read_text(encoding="utf-8").split())}
        for surface, tete, portee in self.PORTEE_DU_REFUS:
            with self.subTest(surface=surface):
                texte = textes[surface]
                self.assertGreaterEqual(texte.count(tete), 1, f"{surface} : « {tete} » absent")
                self.assertEqual(texte.count(tete + portee), texte.count(tete),
                                 f"{surface} : un « {tete} » sans sa portée par hôte")

    #: (surface qui voyage, forme PÉRIMÉE, forme juste) — `cadre hook` est public
    #: depuis T-00000862. BORNE : seules ces formes NOMMÉES sont vues ; une autre
    #: phrase qui le dirait réservé passe.
    STATUT_DU_HOOK = (
        (".agents/skills/guardrails/SKILL.md",
         "`cadre init`, `cadre hook` and `cadre doctor` are RESERVED names",
         "and `cadre hook` ships with an empty guard table (T-00000862)"),
        (".agents/README.md",
         "to be read by `cadre hook` (not shipped yet)",
         "to be read by `cadre hook`'s lockstep (T-00000731, not shipped yet)"),
    )

    def test_H8c_aucune_surface_ne_dit_cadre_hook_reserve(self):
        for surface, perimee, juste in self.STATUT_DU_HOOK:
            with self.subTest(surface=surface):
                texte = (ROOT / surface).read_text(encoding="utf-8")
                self.assertFalse(perimee in texte, f"{surface} : forme périmée « {perimee} »")
                self.assertTrue(juste in texte, f"{surface} : forme juste absente « {juste} »")


#: Ce que `cadre/hook.py` ne référence jamais (H9). Les flux de `sys`, leurs
#: doubles dunder compris : en attribut sur N'IMPORTE QUEL récepteur.
_FLUX = {"stdin", "stdout", "stderr", "__stdin__", "__stdout__", "__stderr__"}
#: Des appelables d'E/S ou d'évasion : en nom nu (`print`) comme en attribut
#: (`builtins.print`, `io.open`, `Path(…).open`).
_APPELABLES_INTERDITS = {"print", "input", "open", "__import__", "exec", "eval", "breakpoint"}
#: Des modules d'E/S : en nom (`os.write`, `os.system`) comme en attribut
#: (`m.os.system`) — leur IMPORT est déjà refusé par `_IMPORTS_PERMIS`.
_MODULES_INTERDITS = {"subprocess", "os", "builtins", "__builtins__", "io", "importlib",
                      "socket", "pty", "shutil"}
#: LES SEULS imports de `cadre/hook.py`, liste FERMÉE : un import de plus est
#: une faute jusqu'à ce que ce banc l'admette, à la main et en le disant.
_IMPORTS_PERMIS = {"__future__", "json", "dataclasses", "types", "typing",
                   "cadre.config", "cadre.hotes_evenements"}
_INTERDITS = _FLUX | _APPELABLES_INTERDITS | _MODULES_INTERDITS


def fautes_d_e_s(source: str) -> list[str]:
    """Les références d'E/S de `source`, relevées sur l'ARBRE SYNTAXIQUE.

    Une faute : un attribut nommé dans `_INTERDITS` sur n'importe quel
    récepteur (un alias de `sys` ne s'en échappe pas) ; un nom nu d'appelable
    ou de module interdit ; une CHAÎNE littérale qui vaut exactement l'un de
    ces noms (`getattr(sys, "stdout")`, `sys.modules["os"]`) ; un import hors
    de `_IMPORTS_PERMIS`, relatif compris ; un nom interdit importé depuis un
    module permis. Une docstring qui les nomme n'est pas une faute : elle ne
    vaut jamais EXACTEMENT un nom.

    BORNE : un filet contre l'inadvertance, pas contre l'obfuscation — un nom
    fabriqué à l'exécution (`getattr(m, "std" + "out")`), ou une E/S atteinte
    par un objet d'un module permis sous un nom neutre, lui échappe.
    """
    fautes: list[str] = []
    for n in ast.walk(ast.parse(source)):
        if isinstance(n, ast.Attribute) and n.attr in _INTERDITS:
            fautes.append(f"{n.lineno} .{n.attr}")
        elif isinstance(n, ast.Name) and n.id in _APPELABLES_INTERDITS | _MODULES_INTERDITS:
            fautes.append(f"{n.lineno} {n.id}")
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value in _INTERDITS:
            fautes.append(f"{n.lineno} {n.value!r}")
        elif isinstance(n, ast.Import):
            fautes += [f"{n.lineno} import {a.name}" for a in n.names
                       if a.name not in _IMPORTS_PERMIS]
        elif isinstance(n, ast.ImportFrom):
            if n.level or n.module not in _IMPORTS_PERMIS:
                fautes.append(f"{n.lineno} from {'.' * n.level}{n.module or ''}")
            fautes += [f"{n.lineno} from {n.module} import {a.name}" for a in n.names
                       if a.name in _INTERDITS]
    return fautes


class PureteTests(unittest.TestCase):
    """H9."""

    def test_H9_hook_py_ne_fait_aucune_E_S(self):
        self.assertEqual(fautes_d_e_s(HOOK_PY.read_text(encoding="utf-8")), [])

    #: Chaque forme est AJOUTÉE à une copie de `hook.py`, qui doit rougir. Les
    #: formes sans import tiennent la règle des noms et des attributs SEULE
    #: (l'import est refusé à part).
    MUTANTS = {
        "import subprocess": "import subprocess",
        "from subprocess": "from subprocess import run",
        "__import__": "__import__('subprocess')",
        "sys.stdout": "import sys\nsys.stdout.write('x')",
        "alias de sys": "import sys as s\ns.stdin.read()",
        "from sys import stderr": "from sys import stderr",
        "sys.__stdout__ sans import": "sys.__stdout__.write('x')",
        "sys.__stderr__ sans import": "sys.__stderr__.write('x')",
        "sys.__stdin__ sans import": "sys.__stdin__.read()",
        "from sys import __stdout__": "from sys import __stdout__",
        "getattr(sys, 'stdout')": "getattr(sys, 'stdout').write('x')",
        "getattr(sys, '__stderr__')": "getattr(sys, '__stderr__').write('x')",
        "typing.sys.modules['os']": "typing.sys.modules['os'].system('x')",
        "print": "print('x')",
        "builtins.print": "import builtins\nbuiltins.print('x')",
        "builtins.print sans import": "builtins.print('x')",
        "__builtins__.print": "__builtins__.print('x')",
        "from builtins import print": "from builtins import print as p",
        "input": "x = input()",
        "os.write sans import": "os.write(1, b'x')",
        "os.system sans import": "os.system('x')",
        "import os": "import os",
        "os atteint par un module permis": "from cadre.config import os",
        "open en ecriture": "open('f', 'w').write('x')",
        "open en lecture": "open('f').read()",
        "io.open sans import": "io.open('f', 'w')",
        "Path.open": "Path('f').open('w')",
        "import hors liste": "import re",
        "import relatif": "from . import config",
    }

    def test_H9_le_detecteur_voit_chaque_forme_sur_une_copie_mutee(self):
        base = HOOK_PY.read_text(encoding="utf-8")
        self.assertEqual(fautes_d_e_s(base), [])
        for nom, ajout in self.MUTANTS.items():
            with self.subTest(forme=nom):
                self.assertNotEqual(fautes_d_e_s(f"{base}\n{ajout}\n"), [], ajout)

    def test_H9_controle_negatif_du_detecteur(self):
        for source in ('"""print, input, sys.stdout, subprocess, os.write, open"""',
                       "x = 'standard output'", "import json\njson.dumps({})"):
            with self.subTest(source=source):
                self.assertEqual(fautes_d_e_s(source), [])


if __name__ == "__main__":
    unittest.main()
