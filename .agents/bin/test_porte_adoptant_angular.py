"""Témoins et mutants ANGULAR de la porte de l'ADOPTANT — T-01M5DFN4GRJMVQ4QZ1D88D6TXG, lot A.

POURQUOI UN FRÈRE : le banc principal, `test_porte_adoptant.py`, tient à
quelques lignes de la borne de 1600 lignes par fichier (convention python du
kit) ; les témoins du module Angular vivent donc ici, sur l'outillage du banc
principal (`_Banc`, `bouchon_source`, `references_ancrees`,
`MutantsDurablesTests.muter`), comme le frère yarn.

RÈGLE D'IMPORT (celle du frère yarn) : toute sous-classe de unittest.TestCase
importée par son nom est recollectée QUEL QUE SOIT son nom ; seules `_Banc`
(0 test) et des constantes s'importent, le reste passe par le module (`banc.…`).

CONTRAT TENU : un module Angular (`angular.json` + script `test` qui lance
`ng test`) joue son test en `--watch=false` — npm `run test -- --watch=false`,
pnpm et yarn `run test --watch=false` (annexe C2, mesuré) — avec `CI=true` au
SEUL processus de test ; `--watch` au script est un ROUGE nommé, comme un `ng test`
(alias `ng t`, `ng run <app>:test`) qui n'est pas le dernier segment d'une chaîne
sans couper son watch (M1 : la queue n'atteint que le dernier) ; un test karma
rouge sans option `browsers` nomme le Chrome fenêtré (C9), ou le `karmaConfig`
qui choisit les navigateurs (C5). Tout autre module garde `run test` à l'octet.

BOUCHONS : le gestionnaire journalise argv ET `CI` à chaque étape ; `CI` est
retiré de l'environnement hérité (GitHub Actions le pose globalement), sinon
le témoin « CI au seul test » serait vide. BRAS RÉELS npm, pnpm et yarn : le
vrai gestionnaire écrit le verrou puis la porte le joue, `ng` bouchonné en tête
du PATH ; un gestionnaire absent est un SAUT ANNONCÉ, jamais un vert vide.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

import test_porte_adoptant as banc
from test_porte_adoptant import _Banc

ANGULAR_VITEST = {"projects": {"web": {"architect": {"test": {"builder": "@angular/build:unit-test"}}}}}
NG = {"lint": "ng lint", "test": "ng test", "build": "ng build"}
ENTETE_V1 = "# yarn lockfile v1\n"
ENTETE_BERRY = "__metadata:\n  version: 8\n"
# (verrou, gestionnaire, contenu bouchonné, install attendue, queue attendue du test)
CAS = (("package-lock.json", "npm", "{}\n", ["ci"], ["--", "--watch=false"]),
       ("pnpm-lock.yaml", "pnpm", "lockfileVersion: '9.0'\n", ["install", "--frozen-lockfile"],
        ["--watch=false"]),
       ("yarn.lock", "yarn", ENTETE_V1, ["install", "--frozen-lockfile"], ["--watch=false"]),
       ("yarn.lock", "yarn", ENTETE_BERRY, ["install", "--immutable"], ["--watch=false"]))
WATCH_ROUGE = "met `ng test` en mode watch, la porte ne finirait jamais — retirez `--watch`"
INDICE_DEFAUT = ("projet web : builder karma sans option `browsers`, donc le Chrome fenêtré par "
                 "défaut, qui ne démarre pas sans écran")
INDICE_CONFIG = "projet web : karma lit ses navigateurs dans karma.conf.js"
CHAINE_ROUGE = ("chaîne où `ng test` n'est pas le dernier segment ; la porte ne réécrit pas une "
                "chaîne et `--watch=false` posé en queue n'atteindrait pas `ng test`")


def ligne_angular(outil: str, queue: list[str], lance: str = "ng test --watch=false") -> str:
    """La ligne du journal : la commande RÉELLEMENT lancée et le script qu'elle joue (M1)."""
    return f"module Angular . : {' '.join([outil, 'run', 'test', *queue])} (script lancé : {lance}), CI=true"


def bouchon_angular_source(nom: str) -> str:
    """Gestionnaire bouchon : journalise argv ET `CI` ; rc `BANC_RC_RUN_TEST` sur
    `run test` seul (les autres étapes vertes), pour rougir le test sans l'install."""
    return (f"#!{sys.executable}\n"
            "import json, os, sys\n"
            "with open(os.environ['BANC_JOURNAL'], 'a', encoding='utf-8') as fh:\n"
            f"    fh.write(json.dumps({{'outil': {nom!r}, 'argv': sys.argv[1:], "
            "'ci': os.environ.get('CI')}) + '\\n')\n"
            "rc = os.environ.get('BANC_RC_RUN_TEST', '0') if sys.argv[1:3] == ['run', 'test'] else '0'\n"
            "sys.exit(int(rc))\n")


def karma(**options) -> dict:
    cible = {"builder": options.pop("builder", "@angular/build:karma"), "options": options}
    return {"projects": {"web": {"architect": {"test": cible}}}}


class _BancAngular(_Banc):
    """Outillage commun aux témoins et aux mutants (0 test)."""

    def env(self, hermetique: bool = True, **extra: str) -> dict[str, str]:
        env = super().env(hermetique, **extra)
        if "CI" not in extra:
            env.pop("CI", None)
        return env

    def bouchon_angular(self, nom: str) -> None:
        chemin = self.bouchons / nom
        chemin.write_text(bouchon_angular_source(nom), encoding="utf-8")
        chemin.chmod(0o755)

    def arbre(self, scripts: dict | None = None, angular: dict | None = ANGULAR_VITEST,
              verrou: str = "package-lock.json", outil: str = "npm", contenu: str = "{}\n") -> Path:
        """Un adoptant NEUF dont la racine est un module npm ; journal vidé."""
        arbre = self.tmp / "adoptant"
        if arbre.exists():
            shutil.rmtree(arbre)
        self.journal.unlink(missing_ok=True)
        self.bouchon_angular(outil)
        fichiers = {"package.json": json.dumps({"name": "web", "scripts": scripts or NG}),
                    verrou: contenu}
        if angular is not None:
            fichiers["angular.json"] = json.dumps(angular)
        return self.adoptant(fichiers)

    def etapes(self, outil: str) -> list[tuple[list[str], str | None]]:
        return [(a["argv"], a["ci"]) for a in self.appels(outil)]

    def argv_du_test(self, outil: str) -> list[str]:
        return [a for a, _ci in self.etapes(outil) if a[:2] == ["run", "test"]][0]


# =============================================================================
class AngularTests(_BancAngular):
    """Le test Angular se termine : argv par gestionnaire, `CI` au seul test."""

    def test_argv_et_ci_par_gestionnaire(self):
        """MUTANTS M-A1, M-A2, M-A4 (rejoués par MutantsAngularTests)."""
        for verrou, outil, contenu, install, queue in CAS:
            with self.subTest(outil=outil, verrou=contenu):
                rc, sortie, _res = self.lancer(self.arbre(verrou=verrou, outil=outil, contenu=contenu))
                self.assertEqual(rc, 0, sortie)
                self.assertIn(ligne_angular(outil, queue), sortie)
                self.assertEqual(self.etapes(outil), [(install, None), (["run", "lint"], None),
                                                      (["run", "test", *queue], "true"),
                                                      (["run", "build"], None)], sortie)

    def test_module_non_angular_inchange(self):
        """Sans `angular.json`, ou sans `ng test` au script : `run test` à l'octet,
        `CI` non posé. MUTANTS M-A3, M-A6, M-NG (rejoués)."""
        for scripts, angular in (({"test": "ng test"}, None), ({"test": "jest"}, ANGULAR_VITEST),
                                 ({"test": "ng testing"}, ANGULAR_VITEST)):
            with self.subTest(scripts=scripts, angular=angular is not None):
                rc, sortie, _res = self.lancer(self.arbre(scripts, angular))
                self.assertEqual(rc, 0, sortie)
                self.assertNotIn("module Angular", sortie)
                self.assertEqual(self.etapes("npm"), [(["ci"], None), (["run", "test"], None)])

    def test_watch_au_script_rouge_nomme(self):
        """MUTANTS M-A5, M-WATCH-FALSE (rejoués)."""
        for script in ("ng test --watch", "ng test --watch=true", "ng test --watch true"):
            with self.subTest(script=script):
                rc, sortie, _res = self.lancer(self.arbre({"test": script}))
                self.assertEqual(rc, 1, sortie)
                self.assertIn(f"module Angular . : le script `test` ({script}) " + WATCH_ROUGE, sortie)
                self.assertEqual(self.appels("npm"), [])
        for script in ("ng test --watch=false", "ng test --watch false", "ng test --no-progress"):
            with self.subTest(script=script):
                rc, sortie, _res = self.lancer(self.arbre({"test": script}))
                self.assertEqual(rc, 0, sortie)
                self.assertEqual(self.argv_du_test("npm"), ["run", "test", "--", "--watch=false"])

    def test_chaine_drapeau_au_bon_segment_ou_refus(self):
        """M1 : le drapeau n'atteint que le DERNIER segment ; un `ng test` qui ne l'est pas, sans
        `--watch=false`, est un ROUGE nommé, jamais une réécriture. MUTANT M-CHAINE (rejoué)."""
        for script in ("ng test && echo fini", "ng test; echo fini", "ng test | tee log", "ng test;"):
            with self.subTest(script=script):
                rc, sortie, _res = self.lancer(self.arbre({"test": script}))
                self.assertEqual(rc, 1, sortie)
                self.assertIn(f"le script `test` ({script}) est une {CHAINE_ROUGE}", sortie)
                self.assertEqual(self.appels("npm"), [])
        for script, queue in (("npm run lint && ng test", ["--", "--watch=false"]),
                              ("ng test 2>&1", ["--", "--watch=false"]),
                              ("ng test --watch=false && echo fini", [])):
            with self.subTest(script=script):
                rc, sortie, _res = self.lancer(self.arbre({"test": script}))
                self.assertEqual(rc, 0, sortie)
                lance = f"{script} --watch=false" if queue else script
                self.assertIn(ligne_angular("npm", queue, lance), sortie)
                self.assertEqual(self.etapes("npm"), [(["ci"], None), (["run", "test", *queue], "true")])

    def test_alias_ng_t_et_ng_run_test(self):
        """Trou ng : `ng t` et `ng run <app>:test` sont des `ng test` ; `ng run web:test-e2e` non.
        MUTANT M-NG-ALIAS (rejoué)."""
        for script, angular in (("ng t", True), ("ng run web:test", True),
                                ("ng run web:test-e2e", False), ("ng to", False)):
            with self.subTest(script=script):
                rc, sortie, _res = self.lancer(self.arbre({"test": script}))
                self.assertEqual(rc, 0, sortie)
                queue = ["--", "--watch=false"] if angular else []
                self.assertEqual(self.etapes("npm"), [(["ci"], None),
                                                      (["run", "test", *queue], "true" if angular else None)])

    def test_karma_rouge_nomme_le_navigateur(self):
        """C9 et C5. MUTANTS M-A7, M-BROWSERS, M-RUNNER, M-CONFIG, M-RUNNERCONFIG (rejoués)."""
        cas = ((karma(), INDICE_DEFAUT),
               (karma(builder="@angular/build:unit-test", runner="karma"), INDICE_DEFAUT),
               (karma(karmaConfig="karma.conf.js"), INDICE_CONFIG),
               (karma(builder="@angular/build:unit-test", runner="karma", runnerConfig="karma.conf.js"),
                INDICE_CONFIG),
               (karma(browsers=["ChromeHeadless"]), None),
               (karma(builder="@angular/build:unit-test", runner="vitest"), None),
               (ANGULAR_VITEST, None))
        for angular, indice in cas:
            with self.subTest(angular=angular):
                rc, sortie, _res = self.lancer(self.arbre(angular=angular), BANC_RC_RUN_TEST="1")
                self.assertEqual(rc, 1, sortie)
                self.assertIn("npm run test -- --watch=false a échoué sur . (rc 1)", sortie)
                if indice is None:
                    self.assertNotIn("karma", sortie)
                else:
                    self.assertIn(indice, sortie)


class BrasReelsTests(_BancAngular):
    """Le VRAI gestionnaire écrit son verrou puis la porte le joue ; `ng` est un
    bouchon en tête du PATH. Absent du poste : SAUT ANNONCÉ."""

    GENERER = {"npm": ["install", "--package-lock-only", "--ignore-scripts", "--no-audit", "--no-fund"],
               "pnpm": ["install", "--lockfile-only", "--ignore-scripts"],
               "yarn": ["install", "--ignore-scripts"]}
    VERROU = {"npm": "package-lock.json", "pnpm": "pnpm-lock.yaml", "yarn": "yarn.lock"}

    def jouer_reel(self, outil: str, queue: list[str]) -> None:
        reel = shutil.which(outil)
        if reel is None:
            self.skipTest(f"SAUT ANNONCÉ : {outil} absent du PATH de ce poste, bras réel non joué")
        paquet = {"name": "web", "version": "1.0.0", "private": True, "scripts": {"test": "ng test"}}
        gabarit = self.tmp / "gabarit"
        gabarit.mkdir()
        (gabarit / "package.json").write_text(json.dumps(paquet), encoding="utf-8")
        p = subprocess.run([reel, *self.GENERER[outil]], cwd=str(gabarit), env=self.env(False),
                           capture_output=True, text=True, timeout=300, check=False)
        verrou = gabarit / self.VERROU[outil]
        self.assertTrue(p.returncode == 0 and verrou.is_file(), f"{outil} : {p.stdout}{p.stderr}")
        self.bouchon_angular("ng")
        arbre = self.adoptant({"package.json": json.dumps(paquet), "angular.json": json.dumps(ANGULAR_VITEST),
                               self.VERROU[outil]: verrou.read_text(encoding="utf-8")})
        chemin = os.pathsep.join([str(self.bouchons), os.environ.get("PATH", "")])
        rc, sortie, _res = self.lancer(arbre, PATH=chemin)
        self.assertEqual(rc, 0, sortie)
        self.assertEqual([(a["argv"], a["ci"]) for a in self.appels("ng")],
                         [(["test", *queue], "true")], sortie)

    def test_npm_reel(self):
        self.jouer_reel("npm", ["--watch=false"])

    def test_pnpm_reel(self):
        self.jouer_reel("pnpm", ["--watch=false"])

    def test_yarn_reel(self):
        self.jouer_reel("yarn", ["--watch=false"])


class EtageAAngularTests(unittest.TestCase):
    """Ce fichier voyage : aucune référence ancrée sur la racine réelle au
    marqueur ni à l'état local (les arbres sont temporaires)."""

    def test_aucune_reference_ancree(self):
        self.assertEqual(banc.references_ancrees(Path(__file__).read_text(encoding="utf-8")), [])


# =============================================================================
class MutantsAngularTests(_BancAngular):
    """Les mutants du lot A, rejoués à chaque passage : le scénario tourne sur
    la source PUIS sur la copie mutée (`muter` du banc principal)."""

    muter = banc.MutantsDurablesTests.muter

    def comparer(self, mutant: Path, attendu, mute, **arbre) -> None:
        """L'argv et le `CI` des étapes du gestionnaire de l'arbre, source puis mutant."""
        for porte, voulu in ((banc.PORTE, attendu), (mutant, mute)):
            rc, sortie, _res = self.lancer(self.arbre(**arbre), porte=porte)
            self.assertEqual(rc, 0, sortie)
            self.assertEqual(self.etapes(arbre.get("outil", "npm")), voulu, sortie)

    def test_M_A1_forme_npm_pour_pnpm(self):
        mutant = self.muter('"pnpm": ("--watch=false",),', '"pnpm": ("--", "--watch=false"),')
        pnpm = {"verrou": "pnpm-lock.yaml", "outil": "pnpm", "contenu": "x\n", "scripts": {"test": "ng test"}}
        install = (["install", "--frozen-lockfile"], None)
        self.comparer(mutant, [install, (["run", "test", "--watch=false"], "true")],
                      [install, (["run", "test", "--", "--watch=false"], "true")], **pnpm)

    def test_M_A2_npm_sans_separateur(self):
        mutant = self.muter('{"npm": ("--", "--watch=false"),', '{"npm": ("--watch=false",),')
        self.comparer(mutant,[(["ci"], None), (["run", "test", "--", "--watch=false"], "true")],
                      [(["ci"], None), (["run", "test", "--watch=false"], "true")],
                      scripts={"test": "ng test"})

    def test_M_A3_drapeau_sur_tout_module(self):
        mutant = self.muter('if s == "test" and angular:', 'if s == "test":')
        self.comparer(mutant,[(["ci"], None), (["run", "test"], None)],
                      [(["ci"], None), (["run", "test"], "true")],
                      scripts={"test": "jest"})

    def test_M_A4_ci_dans_env_enfant(self):
        mutant = self.muter('if not k.startswith("GIT_") or k in GIT_CONSERVE}',
                            'if not k.startswith("GIT_") or k in GIT_CONSERVE} | {"CI": "true"}')
        self.comparer(mutant,[(["ci"], None), (["run", "test", "--", "--watch=false"], "true")],
                      [(["ci"], "true"), (["run", "test", "--", "--watch=false"], "true")],
                      scripts={"test": "ng test"})

    def test_M_A5_controle_watch_retire(self):
        mutant = self.muter("    if angular and WATCH_ACTIF.search(test):", "    if False:")
        rc, sortie, _res = self.lancer(self.arbre({"test": "ng test --watch"}))
        self.assertEqual(rc, 1, sortie)
        self.assertIn(WATCH_ROUGE, sortie)
        rc, sortie, _res = self.lancer(self.arbre({"test": "ng test --watch"}), porte=mutant)
        self.assertEqual(rc, 0, "le mutant M-A5 devait laisser passer --watch : " + sortie)
        self.assertNotIn(WATCH_ROUGE, sortie)

    def test_M_WATCH_FALSE_espace(self):
        mutant = self.muter(r'(?!\s+false\b)")', '")')
        arbre = {"scripts": {"test": "ng test --watch false"}}
        self.assertEqual(self.lancer(self.arbre(**arbre))[0], 0)
        rc, sortie, _res = self.lancer(self.arbre(**arbre), porte=mutant)
        self.assertEqual(rc, 1, sortie)
        self.assertIn(WATCH_ROUGE, sortie)

    def test_M_A6_angular_json_ignore(self):
        mutant = self.muter('angular = ((dossier / "angular.json").is_file() and',
                            "angular = (True and")
        self.comparer(mutant,[(["ci"], None), (["run", "test"], None)],
                      [(["ci"], None), (["run", "test", "--", "--watch=false"], "true")],
                      scripts={"test": "ng test"}, angular=None)

    def test_M_NG_script_ignore(self):
        mutant = self.muter("and NG_TEST.search(test) is not None)", "and True)")
        self.comparer(mutant,[(["ci"], None), (["run", "test"], None)],
                      [(["ci"], None), (["run", "test"], "true")],
                      scripts={"test": "jest"})

    def rouge_karma(self, mutant: Path, angular: dict, present: str, absent: str | None) -> None:
        """Le test rougit sous karma : `present` est dans la sortie de la source,
        ABSENT de celle du mutant (et `absent` y paraît, s'il est donné)."""
        for porte, voulu in ((banc.PORTE, True), (mutant, False)):
            rc, sortie, _res = self.lancer(self.arbre(angular=angular), porte=porte, BANC_RC_RUN_TEST="1")
            self.assertEqual(rc, 1, sortie)
            self.assertEqual(present in sortie, voulu, sortie)
            if absent is not None and not voulu:
                self.assertIn(absent, sortie)

    def test_M_A7_indice_karma_retire(self):
        mutant = self.muter("indice = indice_karma(dossier) if angular and env is not None else", "indice = '' if True else")
        self.rouge_karma(mutant, karma(), INDICE_DEFAUT, None)

    def test_M_RUNNER_unit_test_karma(self):
        mutant = self.muter('and options.get("runner") == "karma")', "and False)")
        self.rouge_karma(mutant, karma(builder="@angular/build:unit-test", runner="karma"), INDICE_DEFAUT, None)

    def test_M_CONFIG_karma_config_tu(self):
        mutant = self.muter("        if config is not None:\n            return (f\" — projet", "        if False:\n            return (f\" — projet")
        self.rouge_karma(mutant, karma(karmaConfig="karma.conf.js"), INDICE_CONFIG, INDICE_DEFAUT)

    def test_M_RUNNERCONFIG_cle_unit_test_ignoree(self):
        mutant = self.muter('for c in ("karmaConfig", "runnerConfig")', 'for c in ("karmaConfig",)')
        angular = karma(builder="@angular/build:unit-test", runner="karma", runnerConfig="karma.conf.js")
        self.rouge_karma(mutant, angular, INDICE_CONFIG, INDICE_DEFAUT)

    def test_M_CHAINE_drapeau_colle_en_queue(self):
        """Le mutant rend l'ancien comportement : `--watch=false` collé à la fin de la chaîne."""
        mutant = self.muter("    if any(NG_TEST.search(s) and not WATCH_COUPE.search(s) for s in segments[:-1]):",
                            "    if False:")
        arbre = {"scripts": {"test": "ng test && echo fini"}}
        self.assertEqual(self.lancer(self.arbre(**arbre))[0], 1)
        rc, sortie, _res = self.lancer(self.arbre(**arbre), porte=mutant)
        self.assertEqual(rc, 0, sortie)
        self.assertNotIn(CHAINE_ROUGE, sortie)

    def test_M_NG_ALIAS_regex_d_avant(self):
        mutant = self.muter(r"ng\s+(?:test|t|run\s+\S+:test)(?![\w-])", r"ng\s+test(?![\w-])")
        for script in ("ng t", "ng run web:test"):
            with self.subTest(script=script):
                self.comparer(mutant, [(["ci"], None), (["run", "test", "--", "--watch=false"], "true")],
                              [(["ci"], None), (["run", "test"], None)], scripts={"test": script})

    def test_M_BROWSERS_option_ignoree(self):
        mutant = self.muter('if not karma or "browsers" in options:', "if not karma:")
        for porte, voulu in ((banc.PORTE, False), (mutant, True)):
            rc, sortie, _res = self.lancer(self.arbre(angular=karma(browsers=["ChromeHeadless"])),
                                           porte=porte, BANC_RC_RUN_TEST="1")
            self.assertEqual(rc, 1, sortie)
            self.assertEqual(INDICE_DEFAUT in sortie, voulu, sortie)


if __name__ == "__main__":
    unittest.main()
