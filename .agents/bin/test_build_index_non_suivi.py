"""Témoin T-00000608, passe de correction 2 : LE REMÈDE QUE LA SONDE AFFICHE
SUR UN NON SUIVI EST JOUÉ, PAS SEULEMENT LU.

La passe 1 (a37ca6cc) écrivait, dans le message de `--stale-check` et sa ligne
REMEDE, qu'un `git add` éteignait ce STALE. FAUX, mesuré par les deux critiques
du binôme bis puis rejoué ici : après un add SEUL, `_changed_names` renomme le
fichier par sa jambe `diff --cached`, la sonde reste STALE et `--if-stale`
reconstruit à CHAQUE appel. Seul un commit, PUIS un `--if-stale`, rend la sonde
CURRENT — le commit seul la laisse STALE.

Un témoin qui vérifierait l'absence d'une phrase laisserait passer la phrase
suivante, aussi fausse. Celui-ci appaire chaque mot du message à un geste joué :
« commit » nommé ↔ add seul STALE puis commit + `--if-stale` CURRENT ; « ignore »
nommé ↔ ignore CURRENT ; AJOUTE / RETIRE ↔ lignes actives de l'index.

PASSE 3 (binôme ter, critic-opus R1, mesuré) : « retrait, ignore … rendent
CURRENT » taisait le FANTÔME. La SONDE devient bien CURRENT, mais un non suivi
déjà ABSORBÉ par un build incrémental garde ses symboles actifs : un retiré
tombe au prochain build nu (T-00000681), un ignoré survit aux builds
incrémentaux, `--full` retire l'un et l'autre aussitôt. Et « seuls … » était une
énumération fausse : commit puis build nu, ou commit puis `--full`, rendent
aussi CURRENT. Chaque mode nommé par le texte est joué ci-dessous.

PIÈGE NOMMÉ : la ligne `DB STALE @ …` de la même sonde contient « nothing to
commit ». Une assertion sur la sortie ENTIÈRE passerait à vide dès qu'elle
s'affiche ; on lit donc la ligne de verdict et la ligne REMEDE, nommément.

Réutilise la fixture `_Case` de `test_build_index_atomic.py`, importée par nom
comme `build_index` l'est là-bas (pytest met ce répertoire sur `sys.path`).
Commits par `_git("add", <nom>)` puis `_git("commit", …)`, jamais `self.commit()` :
son `add -A` effacerait l'état « add seul » que ce témoin mesure.
"""
import unittest

import build_index as bi
from test_build_index_atomic import _Case

NOM = "zz_orphelin.py"
SUIVI = "src/alpha/one.py"
MODES = ((), ("--full",), ("--if-stale",))  # build nu, --full, --if-stale


class NonSuiviRemedeTests(_Case):

    def _ecrire(self, nom: str = NOM) -> None:
        (self.root / nom).write_text("def zz_fn():\n    return 1\n", encoding="utf-8")

    def _actif(self, nom: str = NOM) -> bool:
        return any(path == nom for (path, _nom, _kind) in self.ids())

    def _sonde(self) -> list:
        """Les lignes de `--stale-check`, la ligne DB (advisory) retirée."""
        return [l for l in self.build("--stale-check").splitlines()
                if not l.startswith(bi.DB_STALE_PREFIX)]

    def _ligne(self, lignes: list, tete: str) -> str:
        trouvees = [l for l in lignes if l.lstrip().startswith(tete)]
        self.assertEqual(1, len(trouvees), f"une ligne {tete!r} attendue : {lignes}")
        return trouvees[0]

    def test_add_seul_laisse_stale_seul_commit_puis_if_stale_rend_current(self):
        self.git_init()
        self.build()
        self._ecrire()

        # LE TEXTE : la ligne de verdict et la ligne REMEDE nomment le commit, et
        # REMEDE dit qu'un add SEUL ne suffit pas — les deux gestes joués plus bas.
        lignes = self._sonde()
        verdict = self._ligne(lignes, "INDEX STALE")
        self.assertIn("NON SUIVI", verdict)
        self.assertIn(NOM, "\n".join(lignes), "la sonde ne nomme pas le fichier")
        self.assertIn("commit", verdict,
                      "le verdict ne nomme pas le commit : un add SEUL laisse STALE")
        remede = self._ligne(lignes, "REMEDE")
        self.assertIn("commit", remede,
                      "REMEDE ne nomme pas le commit : un add SEUL laisse STALE")
        self.assertIn("add SEUL", remede,
                      "REMEDE ne dit pas qu'un add SEUL laisse la sonde STALE")

        # (1) Un build incrémental AJOUTE le non suivi, et la sonde reste STALE.
        self.build()
        self.assertTrue(self._actif(), "un build incrémental n'AJOUTE pas le non suivi")
        self._ligne(self._sonde(), "INDEX STALE")

        # (2) Un --full le RETIRE (index bâti depuis `git ls-files` seul), et la
        # sonde reste STALE.
        self.build("--full")
        self.assertFalse(self._actif(), "un --full ne RETIRE pas le non suivi")
        self._ligne(self._sonde(), "INDEX STALE")

        # (3) `git add` SEUL : la sonde reste STALE, et `--if-stale` reconstruit à
        # CHAQUE appel. DÉFAUT PRÉEXISTANT, constaté ici et non corrigé, parce que
        # REMEDE l'affirme : s'il rougit parce que le défaut a été corrigé, c'est la
        # ligne REMEDE de `build_index.py` qu'il faut réécrire avec lui.
        self._git("add", NOM)
        self._ligne(self._sonde(), "INDEX STALE")
        for appel in (1, 2):
            self.assertIn("INDEX BUILT", self.build("--if-stale"),
                          f"add seul, appel {appel} : --if-stale ne reconstruit plus — "
                          "réécrire la ligne REMEDE de build_index.py")
        self._ligne(self._sonde(), "INDEX STALE")

        # (4) Le commit SEUL laisse encore STALE ; c'est le --if-stale qui suit qui
        # rend CURRENT, et le suivant n'a plus rien à faire.
        self._git("commit", "-qm", "suit zz_orphelin")
        self._ligne(self._sonde(), "INDEX STALE")
        self.assertIn("INDEX BUILT", self.build("--if-stale"))
        self._ligne(self._sonde(), "INDEX CURRENT")
        self.assertIn("INDEX CURRENT", self.build("--if-stale"))

    def test_retrait_ou_ignore_rend_la_sonde_current(self):
        self.git_init()
        self.build()

        # LE TEXTE : REMEDE nomme le retrait et l'ignore ; les deux sont joués.
        self._ecrire()
        remede = self._ligne(self._sonde(), "REMEDE")
        self.assertIn("retir", remede, "REMEDE ne nomme pas le retrait")
        self.assertIn("ignore", remede, "REMEDE ne nomme pas l'ignore")

        # Retrait : la sonde redevient CURRENT, sans reconstruction.
        (self.root / NOM).unlink()
        self._ligne(self._sonde(), "INDEX CURRENT")

        # Ignore : même effet, fichier laissé sur le disque.
        self._ecrire()
        self._ligne(self._sonde(), "INDEX STALE")
        (self.root / ".gitignore").write_text(NOM + "\n", encoding="utf-8")
        self._ligne(self._sonde(), "INDEX CURRENT")
        self.assertIn("INDEX CURRENT", self.build("--if-stale"))

    # --- passe 3 : le fantôme absorbé, et les rebuilds après commit -----------
    def _absorber(self) -> None:
        """Un non suivi ABSORBÉ : écrit, puis un build incrémental l'ajoute."""
        self.git_init()
        self.build()
        self._ecrire()
        self.build()
        self.assertTrue(self._actif(), "prémisse : le build nu n'a pas absorbé")

    def test_ignore_apres_absorption_laisse_un_fantome_que_full_retire(self):
        self._absorber()
        remede = self._ligne(self._sonde(), "REMEDE")
        for mot in ("ABSORBÉ", "ACTIFS", "--full", "ignoré survit"):
            self.assertIn(mot, remede, f"REMEDE ne dit pas {mot!r} : fantôme tu")

        (self.root / ".gitignore").write_text(NOM + "\n", encoding="utf-8")
        self._ligne(self._sonde(), "INDEX CURRENT")
        self.assertTrue(self._actif(), "ignore : le fantôme absorbé a disparu")
        self.assertIn("INDEX CURRENT", self.build("--if-stale"))
        for appel in (1, 2):
            self.assertIn("INDEX BUILT", self.build())
            self.assertTrue(self._actif(), f"build nu {appel} a retiré l'ignoré")
        self.assertIn("INDEX BUILT", self.build("--full"))
        self.assertFalse(self._actif(), "--full ne retire pas le fantôme ignoré")
        self._ligne(self._sonde(), "INDEX CURRENT")

    def _retrait_apres_absorption(self, *geste: str) -> None:
        self._absorber()
        remede = self._ligne(self._sonde(), "REMEDE")
        for mot in ("retiré tombe au prochain build nu", "--full"):
            self.assertIn(mot, remede, f"REMEDE ne dit pas {mot!r}")

        (self.root / NOM).unlink()
        self._ligne(self._sonde(), "INDEX CURRENT")
        self.assertTrue(self._actif(), "retrait : le fantôme absorbé a disparu")
        self.assertIn("INDEX CURRENT", self.build("--if-stale"))
        self.assertTrue(self._actif(), "--if-stale a reconstruit sur un CURRENT")
        self.assertIn("INDEX BUILT", self.build(*geste))
        self.assertFalse(self._actif(), f"{geste or 'build nu'} garde le fantôme")
        self._ligne(self._sonde(), "INDEX CURRENT")

    def test_retrait_apres_absorption_le_build_nu_retire_le_fantome(self):
        self._retrait_apres_absorption()

    def test_retrait_apres_absorption_full_retire_le_fantome(self):
        self._retrait_apres_absorption("--full")

    def test_commit_puis_build_nu_ou_full_rend_aussi_current(self):
        self.git_init()
        self.build()
        for nom, geste in (("zz_a.py", ()), ("zz_b.py", ("--full",))):
            (self.root / nom).write_text("y = 2\n", encoding="utf-8")
            lignes = self._sonde()
            self.assertNotIn("seuls", self._ligne(lignes, "INDEX STALE"),
                             "énumération fermée : build nu, --full rendent CURRENT")
            self.assertIn("build nu ou --full", self._ligne(lignes, "REMEDE"))
            self._git("add", nom)
            self._git("commit", "-qm", f"suit {nom}")
            self._ligne(self._sonde(), "INDEX STALE")
            self.assertIn("INDEX BUILT", self.build(*geste))
            self._ligne(self._sonde(), "INDEX CURRENT")

    # --- T-00001136 : l'état MIXTE (suivi modifié + non suivi) les nomme aussi --
    def _mixte(self, noms: list) -> list:
        """Non suivis absorbés, PUIS un fichier suivi modifié : la branche générique."""
        self.git_init()
        self.build()
        for nom in noms:
            self._ecrire(nom)
        self.build()
        self._bouger_suivi()
        return self._sonde()

    def _bouger_suivi(self) -> None:
        suivi = self.root / SUIVI
        suivi.write_text(suivi.read_text(encoding="utf-8") + "\n# bouge\n",
                         encoding="utf-8")

    def test_etat_mixte_nomme_les_non_suivis_qu_un_rebuild_n_eteint_pas(self):
        lignes = self._mixte([NOM])
        self.assertIn("a rebuild would change the index files",
                      self._ligne(lignes, "INDEX STALE"), "verdict générique changé")
        self.assertIn(f"    - {NOM}", lignes, "état mixte : le non suivi n'est pas nommé")
        tete = self._ligne(lignes, "dont 1 NON SUIVI")
        self.assertIn("qu'un rebuild n'éteint pas", tete)
        # LA PHRASE EST JOUÉE : après chaque geste, le non suivi reste nommé. Le
        # VERDICT de `--if-stale` n'est pas asserté ici : sur un suivi modifié non
        # commité il relève de T-00001138 (boucle de reconstruction), dont la
        # correction ne doit pas rougir ce témoin. Build nu et --full bâtissent.
        for geste in MODES:
            sortie = self.build(*geste)
            if geste != ("--if-stale",):
                self.assertIn("INDEX BUILT", sortie)
            self.assertIn(f"    - {NOM}", self._sonde(), f"{geste} l'a éteint")

    def test_etat_mixte_borne_la_liste_a_dix_avec_le_compte(self):
        noms = [f"zz_{i:02d}.py" for i in range(11)]
        lignes = self._mixte(noms)
        self._ligne(lignes, "dont 11 NON SUIVI")
        self.assertEqual(10, sum(f"    - {n}" in lignes for n in noms))
        self._ligne(lignes, "… et 1 autre(s)")

    # --- T-00001136, passe de correction : le REMEDE de l'état MIXTE, JOUÉ ------
    # La base n'en imprimait AUCUN en mixte ; copier celui du cas pur aurait menti
    # (« un non suivi seul ne fait plus reconstruire », « un retiré tombe au
    # prochain build nu » : ici le rebuild qui suit le commit le retire déjà).
    def test_etat_mixte_imprime_son_propre_remede(self):
        remede = self._ligne(self._mixte([NOM]), "REMEDE")
        for mot in ("(état mixte)", "`git commit` des SUIVIS",
                    "--if-stale, build nu ou --full", "`git add` + `git commit`",
                    "retrait", "tombent à ce rebuild", "ignore",
                    "survivent aux builds incrémentaux", "un --full les retire",
                    "ne nomme plus qu'eux"):
            self.assertIn(mot, remede, f"REMEDE mixte ne dit pas {mot!r}")
        for faux in ("ne fait plus reconstruire", "tombe au prochain build nu"):
            self.assertNotIn(faux, remede, f"phrase du cas pur, fausse ici : {faux!r}")

    def _jouer(self, regler, apres) -> None:
        """Chaque mode de rebuild NOMMÉ par le REMEDE mixte, dans un même dépôt :
        mixte → `regler(nom)` → commit du suivi → rebuild → `apres(nom, mode)`."""
        self.git_init()
        self.build()
        for i, mode in enumerate(MODES):
            nom = f"zz_m{i}.py"
            with self.subTest(mode=mode or "build nu"):
                self._ecrire(nom)
                self.build()
                self.assertTrue(self._actif(nom), "prémisse : non suivi pas absorbé")
                self._bouger_suivi()
                self._ligne(self._sonde(), "REMEDE (état mixte)")
                regler(nom)
                self._git("add", SUIVI)
                self._git("commit", "-qm", f"suivi {i}")
                self.assertIn("INDEX BUILT", self.build(*mode))
                apres(nom, mode)

    def test_mixte_add_commit_puis_rebuild_rend_current(self):
        def apres(nom, _mode):
            self._ligne(self._sonde(), "INDEX CURRENT")
            self.assertTrue(self._actif(nom), "le non suivi commité n'est pas indexé")
        self._jouer(lambda nom: self._git("add", nom), apres)

    def test_mixte_retrait_les_symboles_absorbes_tombent_a_ce_rebuild(self):
        def apres(nom, _mode):
            self._ligne(self._sonde(), "INDEX CURRENT")
            self.assertFalse(self._actif(nom), "retrait : le fantôme survit au rebuild")
        self._jouer(lambda nom: (self.root / nom).unlink(), apres)

    def test_mixte_ignore_survit_aux_incrementaux_full_le_retire(self):
        def ignorer(nom):
            with (self.root / ".gitignore").open("a", encoding="utf-8") as f:
                f.write(nom + "\n")

        def apres(nom, mode):
            self._ligne(self._sonde(), "INDEX CURRENT")
            if mode != ("--full",):
                self.assertTrue(self._actif(nom), f"{mode} a retiré l'ignoré absorbé")
                self.assertIn("INDEX BUILT", self.build())
                self.assertTrue(self._actif(nom), "le build nu a retiré l'ignoré absorbé")
                self.assertIn("INDEX BUILT", self.build("--full"))
            self.assertFalse(self._actif(nom), "--full ne retire pas l'ignoré absorbé")
            self._ligne(self._sonde(), "INDEX CURRENT")
        self._jouer(ignorer, apres)

    def test_mixte_sans_regler_la_sonde_ne_nomme_plus_que_les_non_suivis(self):
        def apres(nom, _mode):
            lignes = self._sonde()
            self.assertIn("NON SUIVI", self._ligne(lignes, "INDEX STALE"))
            self.assertIn(f"    - {nom}", lignes)
            self.assertNotIn("(état mixte)", self._ligne(lignes, "REMEDE"))
            self._git("add", nom)  # retour à CURRENT pour le mode suivant
            self._git("commit", "-qm", f"suit {nom}")
            self.assertIn("INDEX BUILT", self.build())
            self._ligne(self._sonde(), "INDEX CURRENT")
        self._jouer(lambda _nom: None, apres)


if __name__ == "__main__":
    unittest.main()
