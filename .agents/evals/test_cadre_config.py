#!/usr/bin/env python3
"""Banc de la précédence de configuration — `cadre config explain`. Phase 1.

Ce qui compte ici n'est pas qu'une valeur se lise, c'est que la PRÉCÉDENCE soit
la bonne dans les quatre sens et que la traçabilité dise vrai. Une précédence
fausse ne se voit pas : elle rend une valeur plausible, simplement pas celle que
l'adoptant a écrite.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Le paquet `cadre` de CETTE racine, chargé par chemin (`.agents/vendor/cadre`
# d'abord, `src/cadre` ensuite) ; les sous-processus reçoivent son parent.
_SPEC_VENDOR = importlib.util.spec_from_file_location(
    "_cadre_config_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
assert _SPEC_VENDOR is not None and _SPEC_VENDOR.loader is not None
_VENDOR = importlib.util.module_from_spec(_SPEC_VENDOR)
sys.modules[_SPEC_VENDOR.name] = _VENDOR
_SPEC_VENDOR.loader.exec_module(_VENDOR)
_VENDOR.charger_paquet(ROOT, "cadre")
PARENT_CADRE = _VENDOR.exiger(ROOT, "cadre").parent

import cadre.config as _config_a_la_collecte  # noqa: E402

#: La classe telle que tout module importé AVANT ce banc l'a liée (`cadre.init`
#: via `cadre.cli`, `cadre.hotes_evenements`) ; voir le dernier test du banc.
_HOTE_INCONNU_A_LA_COLLECTE = _config_a_la_collecte.HoteInconnu


class PrecedenceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.conf = self.base / "conf"
        (self.conf / "hotes").mkdir(parents=True)
        (self.base / ".agents").mkdir()
        self._env = dict(os.environ)
        os.environ["CADRE_CONFIG_HOME"] = str(self.conf)
        os.environ["CADRE_PROJECT_ROOT"] = str(self.base)
        import cadre.config as c  # noqa: PLC0415

        # JAMAIS `importlib.reload` : le module lit l'environnement à l'appel,
        # et recharger recréait ses classes (dernier test du banc).
        self.c = c

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)
        self._tmp.cleanup()

    def _ecrire(self, couche: str, contenu: dict) -> None:
        cibles = {
            "utilisateur": self.conf / "cadre.json",
            "hote": self.conf / "hotes" / "claude.json",
            "projet": self.base / ".agents" / "cadre.json",
        }
        cibles[couche].write_text(json.dumps(contenu), encoding="utf-8")

    # -- la précédence, dans les deux sens ------------------------------

    def test_le_projet_bat_l_hote_qui_bat_l_utilisateur(self):
        """L'ORDRE EST LA PROPRIÉTÉ. On l'éprouve sur UNE clé posée par les
        trois couches, sinon on ne mesure qu'une absence."""
        self._ecrire("utilisateur", {"k": "u"})
        self._ecrire("hote", {"k": "h"})
        self._ecrire("projet", {"k": "p"})
        self.assertEqual(self.c.charger("claude").get("k"), "p")

    def test_une_couche_forte_absente_laisse_gagner_la_suivante(self):
        self._ecrire("utilisateur", {"k": "u"})
        self._ecrire("hote", {"k": "h"})
        self.assertEqual(self.c.charger("claude").get("k"), "h")

    def test_l_ordre_declare_est_celui_qui_est_applique(self):
        """CONTRÔLE DE NON-VACUITÉ DE L'ORDRE. `COUCHES` pourrait être réordonné
        sans que rien d'autre ne rougisse ; ce test lie la constante au
        comportement."""
        self.assertEqual(self.c.COUCHES, ("embarque", "utilisateur", "hote", "projet"))

    # -- la fusion ------------------------------------------------------

    def test_les_tables_fusionnent_en_profondeur(self):
        """Un projet qui règle UN seuil n'a pas à recopier toute la table."""
        self._ecrire("utilisateur", {"t": {"a": 1, "b": 2}})
        self._ecrire("projet", {"t": {"b": 20}})
        self.assertEqual(self.c.charger().get("t"), {"a": 1, "b": 20})

    def test_les_listes_sont_remplacees_jamais_concatenees(self):
        """LA FAUTE LA PLUS CHÈRE DE CE MODULE, si elle était commise : une
        allowlist fusionnée réinjecterait ce qu'une couche forte croit avoir
        retiré."""
        self._ecrire("utilisateur", {"allow": ["a", "b"]})
        self._ecrire("projet", {"allow": ["c"]})
        self.assertEqual(self.c.charger().get("allow"), ["c"])

    def test_une_surcharge_ne_peut_pas_RETIRER_une_cle(self):
        """Le coût assumé de la fusion profonde, éprouvé plutôt qu'affirmé dans
        une docstring : on remplace une valeur, on ne supprime pas une clé."""
        self._ecrire("utilisateur", {"t": {"a": 1}})
        self._ecrire("projet", {"t": {"b": 2}})
        self.assertEqual(self.c.charger().get("t"), {"a": 1, "b": 2})

    # -- la traçabilité -------------------------------------------------

    def test_explain_nomme_la_couche_ET_ce_qu_elle_recouvre(self):
        """La seconde moitié est celle qui répond à « pourquoi mon changement
        ne prend pas » — sans elle, `explain` ne sert à rien."""
        self._ecrire("utilisateur", {"t": {"b": 2}})
        self._ecrire("hote", {"t": {"b": 20}})
        o = self.c.expliquer("t.b", "claude")
        self.assertEqual((o.valeur, o.couche), (20, "hote"))
        self.assertEqual(o.recouvre, (("utilisateur", 2),))

    def test_explain_sur_une_cle_absente_le_dit(self):
        o = self.c.expliquer("jamais.posee")
        self.assertEqual(o.couche, "aucune")
        self.assertIn("rien", o.rendu())

    # -- les refus ------------------------------------------------------

    def test_un_json_invalide_LEVE_au_lieu_d_etre_avale(self):
        """L'avaler ferait appliquer le défaut à la place du réglage écrit —
        silencieusement, donc le pire des deux."""
        (self.conf / "cadre.json").write_text("{ pas du json", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.c.charger()

    def test_une_racine_non_objet_est_refusee(self):
        (self.conf / "cadre.json").write_text("[1, 2]", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.c.charger()

    def test_un_fichier_absent_est_le_regime_normal(self):
        """La plupart des couches n'existent pas ; ce n'est pas une erreur."""
        self.assertEqual(self.c.charger().effective, {})

    # -- les constats de la revue de clôture du 2026-09-12 --------------

    def test_explain_rend_la_valeur_EFFECTIVE_meme_sur_une_TABLE(self):
        """LE CONSTAT LE PLUS GRAVE DE LA REVUE, et il frappait exactement le cas
        où la fusion profonde rend la question intéressante.

        `expliquer` rendait la table BRUTE de la couche la plus forte. Mesuré :
        utilisateur `{"seuil": 3, "mode": "strict"}`, projet `{"seuil": 5}` — la
        valeur lue par le kit est `{"seuil": 5, "mode": "strict"}` et `explain`
        annonçait `{"seuil": 5}` en disant recouvrir l'autre couche. Faux deux
        fois : `mode` survit, et rien ne l'a recouvert. L'adoptant qui demande
        « pourquoi mon changement ne prend pas » recevait une réponse fausse,
        c'est-à-dire l'objet même du module retourné contre lui.

        L'ASSERTION LIE `explain` À `get`, elle ne recopie pas une valeur
        attendue : c'est l'égalité des deux qui est la propriété, et une valeur
        écrite à la main dériverait le jour où la fusion changerait.
        """
        self._ecrire("utilisateur", {"securite": {"seuil": 3, "mode": "strict"}})
        self._ecrire("projet", {"securite": {"seuil": 5}})
        o = self.c.expliquer("securite")
        self.assertEqual(o.valeur, self.c.charger().get("securite"))
        self.assertEqual(o.valeur, {"seuil": 5, "mode": "strict"})

    def test_une_table_fusionnee_est_dite_FUSION_et_non_posee_par_une_couche(self):
        """Le corollaire : quand plusieurs couches contribuent, AUCUNE n'a posé
        la valeur. Nommer la plus forte serait rendre la moitié de la réponse."""
        self._ecrire("utilisateur", {"t": {"a": 1}})
        self._ecrire("projet", {"t": {"b": 2}})
        o = self.c.expliquer("t")
        self.assertTrue(o.couche.startswith("fusion("), f"couche annoncee : {o.couche}")
        self.assertIn("utilisateur", o.couche)
        self.assertIn("projet", o.couche)
        self.assertEqual({c for c, _ in o.recouvre}, {"utilisateur", "projet"})

    def test_un_scalaire_garde_sa_poseuse_unique(self):
        """CONTRÔLE DE NON-RÉGRESSION DU RÉGIME NORMAL. Le correctif ci-dessus ne
        doit pas transformer toute explication en `fusion(...)` : sur une valeur
        qui n'est pas une table, la couche la plus forte gagne ENTIÈREMENT et
        c'est elle la poseuse."""
        self._ecrire("utilisateur", {"k": "u"})
        self._ecrire("projet", {"k": "p"})
        o = self.c.expliquer("k")
        self.assertEqual((o.valeur, o.couche), ("p", "projet"))
        self.assertEqual(o.recouvre, (("utilisateur", "u"),))

    def test_la_couche_EMBARQUEE_existe_dans_le_paquet(self):
        """La précédence promet quatre couches ; le répertoire `data/` n'était
        pas dans le paquet, donc elle en avait trois et `explain` ne pouvait
        jamais répondre `posee par : embarque`. Le banc n'écrivait que les trois
        autres couches, donc il était vert sur une couche VIDE."""
        embarque = self.c.fichiers()["embarque"]
        self.assertIsNotNone(embarque, "la couche embarquee n'a pas de lieu")
        self.assertTrue(embarque.is_file(),
                        f"couche embarquee promise au contrat et absente : {embarque}")

    def test_la_couche_embarquee_est_la_PLUS_FAIBLE(self):
        """Elle existe : encore faut-il qu'elle perde contre les trois autres.
        Une couche présente mais mal ordonnée serait pire qu'absente."""
        self.assertEqual(self.c.COUCHES[0], "embarque")
        self._ecrire("utilisateur", {"k": "u"})
        self.assertEqual(self.c.charger().get("k"), "u")

    def test_un_hote_hors_de_la_liste_fermee_est_REFUSE(self):
        """`hote` était interpolé nu dans un chemin, donc n'importe quel JSON du
        disque devenait une couche de configuration. Deux fuites distinctes, et
        les deux sont éprouvées : `..` traverse, et `pathlib` efface l'opérande
        gauche dès que la droite est absolue."""
        for mauvais in ("../../vole", "/etc/passwd", "Claude", "inconnu"):
            with self.subTest(hote=mauvais):
                with self.assertRaises(self.c.HoteInconnu):
                    self.c.expliquer("k", mauvais)

    def test_les_cinq_hotes_de_la_liste_sont_ACCEPTES(self):
        """CONTRÔLE DE NON-VACUITÉ DU REFUS. Une liste fermée qui refuserait
        TOUT serait verte au test précédent et inutilisable."""
        for bon in self.c.HOTES:
            with self.subTest(hote=bon):
                self.assertEqual(self.c.expliquer("k", bon).couche, "aucune")

    def test_sans_hote_nomme_AUCUN_fichier_d_hote_ne_s_applique(self):
        """La couche hôte pointait `hotes/aucun.json` quand aucun hôte n'était
        nommé — un fichier qu'un utilisateur pouvait créer, et qui se serait
        alors appliqué à toutes les invocations sans qu'aucune option ne le
        demande."""
        (self.conf / "hotes" / "aucun.json").write_text('{"k": "PIEGE"}', encoding="utf-8")
        self.assertIsNone(self.c.fichiers()["hote"])
        self.assertIsNone(self.c.charger().get("k"))

    # -- antigravity : refusé, mais ORIENTÉ (T-00000861, BK-110) ---------

    def test_antigravity_est_REFUSE_et_ORIENTE_vers_gemini(self):
        """Antigravity partage la doctrine et les hooks de Gemini sans être une
        entrée de `HOTES` (`capacites_hotes.json` le déclare hors liste). Le
        refus seul laissait l'appelant devant cinq noms dont aucun n'est le
        sien ; le remède nomme celui qui l'active. La casse et les espaces de
        bord ne changent pas l'orientation — `Antigravity` est le nom du produit
        tel qu'on le tape —, ni le refus : orienter n'est jamais accepter."""
        for nom in ("antigravity", "Antigravity", " ANTIGRAVITY\t"):
            with self.subTest(hote=nom):
                with self.assertRaises(self.c.HoteInconnu) as cm:
                    self.c.expliquer("k", nom)
                message = str(cm.exception)
                self.assertIn("antigravity herite de gemini", message)
                self.assertIn("utiliser l'hote 'gemini'", message)

    def test_un_hote_inconnu_quelconque_n_est_oriente_vers_AUCUN_porteur(self):
        """CONTRÔLE DE NON-VACUITÉ DE L'ORIENTATION. Un remède posé sur TOUT
        refus, ou une recherche par sous-chaîne, enverrait `../../vole` ou
        `antigravity-x` vers gemini ; un argument qui n'est pas une chaîne ne
        doit pas changer le type du refus. Le message d'un hôte qui n'hérite de
        rien reste celui d'avant : liste admise et rappel « jamais un chemin »."""
        for nom in ("inconnu", "Claude", "../../vole", "antigravity-x", ["antigravity"]):
            with self.subTest(hote=nom):
                with self.assertRaises(self.c.HoteInconnu) as cm:
                    self.c.expliquer("k", nom)
                message = str(cm.exception)
                self.assertNotIn("herite de", message)
                self.assertIn("Valeurs admises : " + ", ".join(self.c.HOTES), message)
                self.assertIn("jamais un chemin", message)

    def test_l_heritier_est_celui_de_la_table_des_hooks_et_reste_HORS_liste(self):
        """`HERITIERS` a UNE source, ce module (S-00004509) : `hotes_evenements`
        la RÉEXPORTE au lieu d'en déclarer une copie, et ce test l'exige par
        IDENTITÉ — une copie, même égale, rougit. L'alias privé `_HERITIERS`
        est le même objet. Le JSON des capacités est lié à `he.HERITIERS` par
        `test_cadre_hook_table`. Un héritier ne rejoint JAMAIS `HOTES` ; son
        porteur y est toujours. La table est en LECTURE SEULE : un `dict` nu
        laisserait un appelant réécrire l'orientation de tous les autres."""
        from cadre import hotes_evenements as he  # noqa: PLC0415

        self.assertIs(he.HERITIERS, self.c.HERITIERS)
        self.assertIs(self.c._HERITIERS, self.c.HERITIERS)
        with self.assertRaises(TypeError):
            self.c.HERITIERS["antigravity"] = "codex"
        for heritier, porteur in self.c.HERITIERS.items():
            with self.subTest(heritier=heritier):
                self.assertNotIn(heritier, self.c.HOTES)
                self.assertIn(porteur, self.c.HOTES)

    # -- la CLI : `type=hote_cli` oriente AVANT `choices` (T-00000861) ---

    #: Les deux options d'hôte de la CLI, préfixe d'appel compris.
    _OPTIONS_HOTE = (("init", "--host"), ("config", "explain", "k", "--hote"))

    def _cadre(self, *args: str) -> subprocess.CompletedProcess:
        """La CLI réelle en sous-processus, partition d'état sous la base."""
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
        env |= {"PYTHONPATH": str(PARENT_CADRE), "CADRE_STATE_DIR": str(self.base / "etat"),
                "PYTHONDONTWRITEBYTECODE": "1"}
        return subprocess.run([sys.executable, "-m", "cadre.cli", *args],
                              cwd=str(self.base), env=env, capture_output=True,
                              encoding="utf-8", timeout=120, check=False)

    def test_hote_cli_ne_leve_QUE_pour_un_heritier(self):
        """Le `type=` des deux options, en direct. Il lève `ArgumentTypeError`
        avec le remède pour un héritier (même recherche que `_refus_hote` :
        égalité, sans casse ni espaces de bord) et rend TOUT autre nom
        INCHANGÉ — le même objet —, pour que `choices` en décide seul."""
        for nom in ("antigravity", " Antigravity\t"):
            with self.subTest(hote=nom):
                with self.assertRaises(argparse.ArgumentTypeError) as cm:
                    self.c.hote_cli(nom)
                self.assertIn("antigravity herite de gemini", str(cm.exception))
        for nom in (*self.c.HOTES, "xyz", "Claude", "antigravity-x", "../../vole",
                    " gemini", "claude\t"):
            with self.subTest(hote=nom):
                self.assertIs(self.c.hote_cli(nom), nom)

    def test_la_CLI_refuse_host_antigravity_en_2_et_ORIENTE_vers_gemini(self):
        """Le critère du ticket, par la CLI réelle. `--host` (`init`) et
        `--hote` (`config explain`) portent `type=hote_cli`, qu'argparse
        applique AVANT `choices` (doc 3.11 : « checked after any type
        conversions » ; mesuré sous 3.11, 3.12 et 3.14). Le refus sort en 2 par
        argparse, garde sa formule « invalid choice » et y AJOUTE le remède.
        Sur 58fe0409, sans `type=`, ce témoin ROUGIT : argparse nommait gemini
        parmi les cinq choix sans orienter. Orienter n'est jamais accepter :
        rien n'est écrit."""
        for option in self._OPTIONS_HOTE:
            for nom in ("antigravity", "Antigravity"):
                with self.subTest(args=(*option, nom)):
                    r = self._cadre(*option, nom)
                    self.assertEqual(r.returncode, 2, r.stderr)
                    self.assertIn(f"invalid choice: {nom!r}", r.stderr)
                    self.assertIn("antigravity herite de gemini", r.stderr)
                    self.assertIn("utiliser l'hote 'gemini'", r.stderr)
                    self.assertNotIn("Traceback", r.stderr)
        self.assertFalse((self.base / "etat").exists(), "le refus a cree la partition d'etat")

    def test_la_CLI_garde_le_refus_d_ARGPARSE_pour_tout_AUTRE_hote(self):
        """CONTRÔLE DE NON-VACUITÉ DE L'ORIENTATION CÔTÉ CLI. Tout nom qui
        n'hérite de rien passe `hote_cli` inchangé et `choices` garde SON refus
        — « invalid choice » ET la liste « choose from », sans remède. Un
        `type=` qui refuserait lui-même tout hôte hors liste perdrait cette
        liste ; un remède posé sur tout refus enverrait `xyz` vers gemini. Un
        hôte de la liste passe, et c'est SA couche qui est lue."""
        for option in self._OPTIONS_HOTE:
            for nom in ("xyz", "antigravity-x"):
                with self.subTest(args=(*option, nom)):
                    r = self._cadre(*option, nom)
                    self.assertEqual(r.returncode, 2, r.stderr)
                    self.assertIn(f"invalid choice: {nom!r}", r.stderr)
                    self.assertIn("choose from", r.stderr)
                    self.assertNotIn("herite de", r.stderr)
        self.assertFalse((self.base / "etat").exists(), "le refus a cree la partition d'etat")
        (self.conf / "hotes" / "gemini.json").write_text('{"k": "pose-par-gemini"}',
                                                          encoding="utf-8")
        r = self._cadre("config", "explain", "k", "--hote", "gemini")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('k = "pose-par-gemini"', r.stdout)
        self.assertIn("posee par : hote", r.stdout)

    #: Les deux aides qui portent une option d'hôte.
    _AIDES_HOTE = (("init", "--help"), ("config", "explain", "--help"))

    def test_l_aide_des_options_d_hote_oriente_chaque_heritier(self):
        """L'aide des deux options d'hôte nomme le remède de CHAQUE héritier.
        Les espaces sont normalisés : argparse replie l'aide à la largeur du
        terminal, et peut couper la parenthèse."""
        for args in self._AIDES_HOTE:
            r = self._cadre(*args)
            self.assertEqual(r.returncode, 0, r.stderr)
            aide = " ".join(r.stdout.split())
            for h, p in self.c.HERITIERS.items():
                with self.subTest(args=args, heritier=h):
                    self.assertIn(f"({h.capitalize()} : utiliser {p})", aide)

    def test_l_aide_est_TIREE_de_HERITIERS_et_non_d_un_litteral(self):
        """Tant qu'il n'y a qu'un héritier, le témoin précédent reste vert sur
        un littéral « (Antigravity : utiliser gemini) ». Celui-ci ajoute un
        héritier fictif à `cadre.config.HERITIERS` AVANT d'importer la CLI,
        dont l'aide est calculée à l'import : un littéral le tairait."""
        script = ("import sys, types, cadre.config as c\n"
                  "c.HERITIERS = types.MappingProxyType({**c.HERITIERS, 'fictif': 'codex'})\n"
                  "import cadre.cli\n"
                  "sys.exit(cadre.cli.main(sys.argv[1:]))\n")
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
        env |= {"PYTHONPATH": str(PARENT_CADRE), "CADRE_STATE_DIR": str(self.base / "etat"),
                "PYTHONDONTWRITEBYTECODE": "1"}
        for args in self._AIDES_HOTE:
            with self.subTest(args=args):
                r = subprocess.run([sys.executable, "-c", script, *args], cwd=str(self.base),
                                   env=env, capture_output=True, encoding="utf-8",
                                   timeout=120, check=False)
                self.assertEqual(r.returncode, 0, r.stderr)
                aide = " ".join(r.stdout.split())
                self.assertIn("(Antigravity : utiliser gemini)", aide)
                self.assertIn("(Fictif : utiliser codex)", aide)

    def test_le_banc_ne_RECREE_pas_les_classes_du_module(self):
        """`setUp` faisait `importlib.reload(cadre.config)`, qui RECRÉE
        `HoteInconnu` : un module importé avant (`cadre.init`, via `cadre.cli`)
        gardait l'ancienne classe, et l'`assertRaises(HoteInconnu)` de
        `test_cadre_init` ratait l'exception levée dès que ce banc tournait
        avant lui dans un même processus (mesuré sur 4431e767 : `pytest
        test_cadre_config.py test_cadre_init.py` -> 1 failed). Le module et le
        banc lisent l'environnement à l'appel : il n'y a rien à recharger."""
        self.assertIs(self.c.HoteInconnu, _HOTE_INCONNU_A_LA_COLLECTE)

    def test_cadre_charge_est_celui_que_vendor_paths_designe(self):
        """Le `cadre` importé à la collecte est le dossier que la règle désigne
        (`.agents/vendor/cadre` d'abord) : un `sys.path.insert(0, ROOT/"src")`
        remis à la place de `charger_paquet` charge `src/cadre` et rougit ici
        quand les deux lieux coexistent (T-01M5BXTPQE3JZV3KZA6WD9P5XC)."""
        attendu, _ = _VENDOR.verifier_charge(ROOT, "cadre")
        self.assertEqual(Path(_config_a_la_collecte.__file__).resolve().parent, attendu)


if __name__ == "__main__":
    unittest.main()
