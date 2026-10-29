"""test_vendor_paths.py — témoin de la phase R de T-01M5BXTGX5YN8XEXTG1PP7A5ZX.

CE QUE CE BANC TIENT, sur des racines jetables (jamais l'arbre du dépôt) :
  R1  ancien seul      `src/cadre`, `agentic_v3/`         → provenance « ancien » ;
  R2  neuf seul        `.agents/vendor/<paquet>`          → provenance « vendor » ;
  R3  les deux         le NEUF gagne (mutant : ordre inversé) ;
  R4  absent           `None`, et `exiger` lève un refus qui NOMME les deux lieux ;
  R5  racines isolées  deux racines dans le même processus, cwd sur l'autre ;
  R6  un dossier sans `__init__.py` ne gagne pas ;
  R7  aucun cache : la même racine, re-résolue après création du vendor, le voit
      (mutant `lru_cache`) ;
  P1  `inserer_en_tete` RETIRE puis insère (réserve C14 ; mutant
      `if … not in sys.path: insert(0)`), sur liste injectée ET en import réel
      contre un `cadre` installé par `.pth` (`site.addsitedir`) ; l'entrée vide
      reste, même cwd SUR la cible ;
  P2  `ajouter_en_queue` laisse gagner le `cadre` de l'adoptant (mutant `insert(0)`) ;
  P3  `amorcer_cli` : `paquets` obligatoire, ordre, dédoublonnage, refus AVANT
      toute modification quel que soit le paquet absent (mutant `exiger`
      paresseux) ; `amorcer_conftest` saute l'absent ;
  P4  jamais devant `BIN` quand BIN figure sur sys.path, comparé par chemin
      RÉEL : un `tasks.py` à la racine de l'adoptant ne masque pas
      `.agents/bin/tasks.py` en disposition ancienne (import réel, BIN en tête,
      en queue, et en queue par un lien symbolique sous `-I`/-P) ; le rang BIN
      se calcule APRÈS le retrait (`[P, BIN, x]` → `[BIN, P, x]`) ;
  P5  jamais devant la bibliothèque standard : un `calendar.py` (et un module
      de `lib-dynload`) à la racine ne masque pas le module standard, avec et
      sans `site-packages` sur sys.path (`-S`) ; un `cadre` `.pth` perd encore ;
  V1  `verifier_charge`, pour CHAQUE paquet de `PAQUETS` : un ancien arbre déjà
      importé alors que le vendor existe est REFUSÉ (`ProvenanceRefusee`) ; un
      module non chargé aussi ; un paquet d'espace de noms (sans `__file__`)
      aussi, en refus propre ;
  V2  un alias du même arbre (lien symbolique ; `/tmp` → `/private/tmp` sur
      macOS) est ACCEPTÉ, pour chaque paquet.
Les imports réels tournent en SOUS-PROCESSUS `-I` : le `sys.path` du processus
pytest n'est jamais modifié.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULE = HERE / "vendor_paths.py"


def _charger():
    spec = importlib.util.spec_from_file_location("vendor_paths_sous_test", MODULE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


vp = _charger()


def _paquet(dossier: Path, origine: str) -> Path:
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / "__init__.py").write_text(f'ORIGINE = "{origine}"\n', encoding="utf-8")
    return dossier


def _ancien(racine: Path, paquet: str) -> Path:
    return _paquet(racine / vp.ANCIENS[paquet], "ancien")


def _neuf(racine: Path, paquet: str) -> Path:
    return _paquet(racine / ".agents" / "vendor" / paquet, "vendor")


class _Racines(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="vendor_paths_")
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name).resolve()

    def racine(self, nom: str) -> Path:
        r = self.base / nom
        r.mkdir()
        return r


class ResolutionTests(_Racines):
    def test_ancien_seul(self) -> None:
        r = self.racine("ancien")
        _ancien(r, "cadre")
        _ancien(r, "agentic_v3")
        self.assertEqual(vp.resoudre(r, "cadre"), (r / "src" / "cadre", "ancien"))
        self.assertEqual(vp.resoudre(r, "agentic_v3"), (r / "agentic_v3", "ancien"))
        self.assertEqual(vp.parent_import(r, "cadre"), r / "src")
        self.assertEqual(vp.parent_import(r, "agentic_v3"), r)

    def test_neuf_seul(self) -> None:
        r = self.racine("neuf")
        _neuf(r, "cadre")
        _neuf(r, "agentic_v3")
        for paquet in vp.PAQUETS:
            with self.subTest(paquet=paquet):
                self.assertEqual(vp.provenance(r, paquet), "vendor")
                self.assertEqual(vp.dossier_paquet(r, paquet), r / ".agents" / "vendor" / paquet)
                self.assertEqual(vp.parent_import(r, paquet), r / ".agents" / "vendor")
                self.assertEqual(vp.exiger(r, paquet), r / ".agents" / "vendor" / paquet)

    def test_les_deux_le_neuf_gagne(self) -> None:
        r = self.racine("deux")
        for paquet in vp.PAQUETS:
            _ancien(r, paquet)
            _neuf(r, paquet)
        for paquet in vp.PAQUETS:
            with self.subTest(paquet=paquet):
                self.assertEqual(vp.resoudre(r, paquet), (r / ".agents" / "vendor" / paquet, "vendor"))

    def test_absent(self) -> None:
        r = self.racine("vide")
        for paquet in vp.PAQUETS:
            with self.subTest(paquet=paquet):
                self.assertIsNone(vp.resoudre(r, paquet))
                self.assertIsNone(vp.provenance(r, paquet))
                self.assertIsNone(vp.parent_import(r, paquet))
                with self.assertRaises(vp.PaquetIntrouvable) as ctx:
                    vp.exiger(r, paquet)
                texte = str(ctx.exception)
                self.assertIn(str(Path(".agents") / "vendor" / paquet), texte)
                self.assertIn(str(vp.ANCIENS[paquet]), texte)

    def test_dossier_sans_init_ne_gagne_pas(self) -> None:
        r = self.racine("reste")
        (r / ".agents" / "vendor" / "cadre").mkdir(parents=True)
        _ancien(r, "cadre")
        self.assertEqual(vp.provenance(r, "cadre"), "ancien")

    def test_racines_isolees(self) -> None:
        a = self.racine("a")
        b = self.racine("b")
        _neuf(a, "cadre")
        _ancien(b, "cadre")
        precedent = os.getcwd()
        os.chdir(b)
        self.addCleanup(os.chdir, precedent)
        self.assertEqual(vp.resoudre(a, "cadre"), (a / ".agents" / "vendor" / "cadre", "vendor"))
        self.assertEqual(vp.resoudre(b, "cadre"), (b / "src" / "cadre", "ancien"))
        self.assertEqual(vp.resoudre(a, "cadre"), (a / ".agents" / "vendor" / "cadre", "vendor"))
        self.assertIsNone(vp.resoudre(a, "agentic_v3"))

    def test_pas_de_cache_re_resolution(self) -> None:
        r = self.racine("deplacement")
        _ancien(r, "cadre")
        self.assertEqual(vp.resoudre(r, "cadre"), (r / "src" / "cadre", "ancien"))
        _neuf(r, "cadre")
        self.assertEqual(vp.resoudre(r, "cadre"), (r / ".agents" / "vendor" / "cadre", "vendor"))
        self.assertEqual(vp.provenance(r, "cadre"), "vendor")

    def test_paquet_inconnu(self) -> None:
        with self.assertRaises(ValueError):
            vp.resoudre(self.base, "autre")


class SysPathTests(unittest.TestCase):
    P = os.path.abspath(os.sep + "kit")

    def test_inserer_absent_va_en_tete(self) -> None:
        chemins = ["/a", "/b"]
        vp.inserer_en_tete(self.P, chemins)
        self.assertEqual(chemins, [self.P, "/a", "/b"])

    def test_inserer_deja_en_queue_remonte(self) -> None:
        chemins = ["/a", self.P, "/b", self.P]
        vp.inserer_en_tete(self.P, chemins)
        self.assertEqual(chemins, [self.P, "/a", "/b"])

    def test_inserer_garde_l_entree_vide(self) -> None:
        chemins = ["", "/a"]
        vp.inserer_en_tete(self.P, chemins)
        self.assertEqual(chemins, [self.P, "", "/a"])

    def test_inserer_jamais_devant_bin(self) -> None:
        bin_ = str(vp.BIN)
        chemins = ["/a", bin_, "/b", bin_]
        vp.inserer_en_tete(self.P, chemins)
        self.assertEqual(chemins, ["/a", bin_, self.P, "/b", bin_])

    def test_rang_bin_calcule_apres_le_retrait(self) -> None:
        bin_ = str(vp.BIN)
        chemins = [self.P, bin_, "/x"]
        vp.inserer_en_tete(self.P, chemins)
        self.assertEqual(chemins, [bin_, self.P, "/x"])

    def test_inserer_derriere_la_stdlib_devant_site_packages(self) -> None:
        coeur = os.path.dirname(os.path.realpath(os.__file__))
        dyn = os.path.join(coeur, "lib-dynload")
        zip_ = os.path.join(os.path.dirname(coeur), "python3.zip")
        site = os.path.join(os.sep + "venv", "lib", "site-packages")
        pth = os.path.join(os.sep + "installe")
        chemins = [zip_, coeur, dyn, site, pth]
        vp.inserer_en_tete(self.P, chemins)
        self.assertEqual(chemins, [zip_, coeur, dyn, self.P, site, pth])
        # Sans site-packages (`-S`) : juste derrière la stdlib, `lib-dynload` comprise.
        chemins = [zip_, coeur, dyn, "/x"]
        vp.inserer_en_tete(self.P, chemins)
        self.assertEqual(chemins, [zip_, coeur, dyn, self.P, "/x"])
        # Un site-packages DEVANT la stdlib (PYTHONPATH) n'ouvre pas la zone.
        chemins = [site, coeur, dyn, "/autre/dist-packages"]
        vp.inserer_en_tete(self.P, chemins)
        self.assertEqual(chemins, [site, coeur, dyn, self.P, "/autre/dist-packages"])
        # `dist-packages` (Debian) ouvre la zone aussi, même après une autre entrée.
        dist = os.path.join(os.sep + "usr", "lib", "python3", "dist-packages")
        chemins = [coeur, "/entre", dist, pth]
        vp.inserer_en_tete(self.P, chemins)
        self.assertEqual(chemins, [coeur, "/entre", self.P, dist, pth])
        # DEUX entrées site après la stdlib (venv --system-site-packages, Debian) :
        # devant la PREMIÈRE, sinon un `cadre` du venv gagne.
        chemins = [coeur, dyn, site, dist]
        vp.inserer_en_tete(self.P, chemins)
        self.assertEqual(chemins, [coeur, dyn, self.P, site, dist])
        # BIN derrière site-packages : jamais devant lui.
        bin_ = str(vp.BIN)
        chemins = [coeur, site, bin_]
        vp.inserer_en_tete(self.P, chemins)
        self.assertEqual(chemins, [coeur, site, bin_, self.P])

    def test_ajouter_en_queue(self) -> None:
        chemins = ["/a"]
        vp.ajouter_en_queue(self.P, chemins)
        self.assertEqual(chemins, ["/a", self.P])
        chemins = [self.P, "/a"]
        vp.ajouter_en_queue(self.P, chemins)
        self.assertEqual(chemins, [self.P, "/a"])


class AmorcageTests(_Racines):
    def test_inserer_garde_l_entree_vide_cwd_sur_la_cible(self) -> None:
        kit = self.racine("kit")
        precedent = os.getcwd()
        os.chdir(kit)
        self.addCleanup(os.chdir, precedent)
        chemins = ["", "/a"]
        vp.inserer_en_tete(kit, chemins)
        self.assertEqual(chemins, [str(kit), "", "/a"])

    def test_bin_et_cible_reconnus_par_chemin_reel(self) -> None:
        lien_bin = self.base / "lien-bin"
        kit = self.racine("kit")
        lien_kit = self.base / "lien-kit"
        try:
            lien_bin.symlink_to(vp.BIN, target_is_directory=True)
            lien_kit.symlink_to(kit, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"lien symbolique impossible ici : {exc}")
        chemins = [str(lien_kit), str(lien_bin), "/x"]
        vp.inserer_en_tete(kit, chemins)
        self.assertEqual(chemins, [str(lien_bin), str(kit), "/x"])

    def test_stdlib_reconnue_par_chemin_reel(self) -> None:
        lien_stdlib = self.base / "lien-stdlib"
        try:
            lien_stdlib.symlink_to(Path(os.path.realpath(os.__file__)).parent, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"lien symbolique impossible ici : {exc}")
        chemins = [str(lien_stdlib), "/x"]
        vp.inserer_en_tete(self.base / "kit", chemins)
        self.assertEqual(chemins, [str(lien_stdlib), str(self.base / "kit"), "/x"])

    def test_amorcer_cli_paquets_obligatoires(self) -> None:
        r = self.racine("ancien")
        _ancien(r, "cadre")
        _ancien(r, "agentic_v3")
        with self.assertRaises(TypeError):
            vp.amorcer_cli(r, chemins=[])  # type: ignore[call-arg]

    def test_amorcer_cli_ordre_et_dedoublonnage(self) -> None:
        r = self.racine("ancien")
        _ancien(r, "cadre")
        _ancien(r, "agentic_v3")
        chemins = ["/x", str(r)]
        self.assertEqual(vp.amorcer_cli(r, vp.PAQUETS, chemins), [r / "src", r])
        self.assertEqual(chemins, [str(r / "src"), str(r), "/x"])
        n = self.racine("neuf")
        _neuf(n, "cadre")
        _neuf(n, "agentic_v3")
        chemins = []
        self.assertEqual(vp.amorcer_cli(n, vp.PAQUETS, chemins), [n / ".agents" / "vendor"])
        self.assertEqual(chemins, [str(n / ".agents" / "vendor")])

    def test_amorcer_cli_absent_ne_touche_rien(self) -> None:
        for present, absent in (("cadre", "agentic_v3"), ("agentic_v3", "cadre")):
            with self.subTest(absent=absent):
                r = self.racine(f"sans-{absent}")
                _ancien(r, present)
                chemins = ["/x"]
                with self.assertRaises(vp.PaquetIntrouvable):
                    vp.amorcer_cli(r, vp.PAQUETS, chemins)
                self.assertEqual(chemins, ["/x"])

    def test_amorcer_conftest_saute_l_absent(self) -> None:
        r = self.racine("partiel")
        _neuf(r, "agentic_v3")
        chemins = ["/x"]
        self.assertEqual(vp.amorcer_conftest(r, chemins=chemins), [r / ".agents" / "vendor"])
        self.assertEqual(chemins, ["/x", str(r / ".agents" / "vendor")])


_SCRIPT_CLI = """
import site, sys
racine, bindir, sitedir = sys.argv[1:4]
site.addsitedir(sitedir)
sys.path.insert(0, bindir)
import vendor_paths
parent = vendor_paths.parent_import(racine, "cadre")
sys.path.append(str(parent))
vendor_paths.amorcer_cli(racine, ("cadre",))
import cadre
print(cadre.ORIGINE)
"""

_SCRIPT_CONFTEST = """
import sys
racine, bindir, adoptant = sys.argv[1:4]
sys.path.insert(0, adoptant)
sys.path.insert(0, bindir)
import vendor_paths
vendor_paths.amorcer_conftest(racine, ("cadre",))
import cadre
print(cadre.ORIGINE)
"""

_SCRIPT_OMBRE = """
import sys
racine, bindir, place = sys.argv[1:4]
if place == "tete":
    sys.path.insert(0, bindir)
else:
    sys.path.append(bindir)
import vendor_paths
vendor_paths.amorcer_cli(racine, ("cadre", "agentic_v3"))
import tasks
print(tasks.ORIGINE)
"""

_SCRIPT_STDLIB = """
import sys
racine, bindir, dynamique = sys.argv[1:4]
sys.path.insert(0, bindir)
import vendor_paths
vendor_paths.amorcer_cli(racine, ("agentic_v3",))
import calendar, agentic_v3
noms = ["calendar=" + getattr(calendar, "ORIGINE", "stdlib")]
if dynamique != "-":
    module = __import__(dynamique)
    noms.append("dyn=" + getattr(module, "ORIGINE", "stdlib"))
print(" ".join(noms), "agentic_v3=" + agentic_v3.ORIGINE)
"""

_SCRIPT_CHARGE = """
import sys
racine, bindir, chemin_import, mode, paquet = sys.argv[1:6]
sys.path.insert(0, bindir)
import vendor_paths
if mode == "importer":
    sys.path.insert(0, chemin_import)
    __import__(paquet)
try:
    print("ACCEPTE", vendor_paths.verifier_charge(racine, paquet)[1])
except vendor_paths.ProvenanceRefusee as exc:
    print("REFUS", exc)
"""


def _module_dynload() -> str | None:
    # Un module de `lib-dynload` (extension compilée de la stdlib), absent de
    # `sys.modules` au démarrage d'un `-I -S`, que la racine pourrait masquer.
    dyn = Path(os.path.realpath(os.__file__)).parent / "lib-dynload"
    if not dyn.is_dir():
        return None
    noms = sorted({f.name.split(".")[0] for f in dyn.iterdir() if f.suffix in (".so", ".pyd")})
    for nom in noms:
        if nom not in sys.builtin_module_names and nom in ("_bisect", "_json", "_csv", "_heapq", "_statistics"):
            return nom
    return None


class ImportReelTests(_Racines):
    """Concurrence réelle d'import, en sous-processus isolé (`-I`)."""

    def _jouer(self, script: str, *args: Path | str, flags: tuple[str, ...] = ("-I",)) -> str:
        sortie = subprocess.run(
            [sys.executable, *flags, "-c", script, *map(str, args)],
            cwd=str(self.base),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
            check=False,
        )
        self.assertEqual(sortie.returncode, 0, sortie.stderr)
        return sortie.stdout.strip()

    def test_cli_bat_un_cadre_installe_par_pth(self) -> None:
        r = self.racine("deux")
        _ancien(r, "cadre")
        _neuf(r, "cadre")
        installe = self.base / "installe"
        _paquet(installe / "cadre", "installe")
        sitedir = self.racine("site-packages")
        (sitedir / "cadre-kit.pth").write_text(f"{installe}\n", encoding="utf-8")
        for flags in (("-I",), ("-I", "-S")):
            with self.subTest(flags=" ".join(flags)):
                self.assertEqual(self._jouer(_SCRIPT_CLI, r, HERE, sitedir, flags=flags), "vendor")

    def test_cli_racine_ne_masque_pas_la_stdlib(self) -> None:
        r = self.racine("adoptant-ancien")
        _ancien(r, "agentic_v3")
        (r / "calendar.py").write_text('ORIGINE = "adoptant-racine"\n', encoding="utf-8")
        dynamique = _module_dynload()
        attendu = "calendar=stdlib"
        if dynamique is not None:
            (r / f"{dynamique}.py").write_text('ORIGINE = "adoptant-racine"\n', encoding="utf-8")
            attendu += " dyn=stdlib"
        attendu += " agentic_v3=ancien"
        for flags in (("-I",), ("-I", "-S")):
            with self.subTest(flags=" ".join(flags)):
                sortie = self._jouer(_SCRIPT_STDLIB, r, HERE, dynamique or "-", flags=flags)
                self.assertEqual(sortie, attendu)

    def test_conftest_laisse_gagner_l_adoptant(self) -> None:
        r = self.racine("neuf")
        _neuf(r, "cadre")
        adoptant = self.base / "adoptant"
        _paquet(adoptant / "cadre", "adoptant")
        self.assertEqual(self._jouer(_SCRIPT_CONFTEST, r, HERE, adoptant), "adoptant")

    def test_cli_racine_ne_masque_pas_le_bin_du_kit(self) -> None:
        r = self.racine("adoptant-ancien")
        _ancien(r, "cadre")
        _ancien(r, "agentic_v3")
        (r / "tasks.py").write_text('ORIGINE = "adoptant-racine"\n', encoding="utf-8")
        bindir = r / ".agents" / "bin"
        bindir.mkdir(parents=True)
        (bindir / "vendor_paths.py").write_bytes(MODULE.read_bytes())
        (bindir / "tasks.py").write_text('ORIGINE = "kit-bin"\n', encoding="utf-8")
        for place in ("tete", "queue"):
            with self.subTest(bin=place):
                self.assertEqual(self._jouer(_SCRIPT_OMBRE, r, bindir, place), "kit-bin")
        # BIN en queue, nommé par un lien symbolique (`-I` implique -P : aucun
        # dossier de script ajouté) : reconnu par son chemin réel.
        lien = self.base / "lien-adoptant"
        try:
            lien.symlink_to(r, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"lien symbolique impossible ici : {exc}")
        sortie = self._jouer(_SCRIPT_OMBRE, lien, lien / ".agents" / "bin", "queue")
        self.assertEqual(sortie, "kit-bin")

    def test_charge_ancien_deja_importe_alors_que_vendor_existe_refuse(self) -> None:
        for paquet in vp.PAQUETS:
            with self.subTest(paquet=paquet):
                r = self.racine(f"deux-{paquet}")
                ancien = _ancien(r, paquet)
                _neuf(r, paquet)
                sortie = self._jouer(_SCRIPT_CHARGE, r, HERE, ancien.parent, "importer", paquet)
                self.assertTrue(sortie.startswith("REFUS "), sortie)
                self.assertIn(str(ancien), sortie)
                self.assertIn(str(r / ".agents" / "vendor" / paquet), sortie)

    def test_charge_non_importe_refuse(self) -> None:
        for paquet in vp.PAQUETS:
            with self.subTest(paquet=paquet):
                r = self.racine(f"neuf-{paquet}")
                _neuf(r, paquet)
                sortie = self._jouer(_SCRIPT_CHARGE, r, HERE, r, "non", paquet)
                self.assertTrue(sortie.startswith("REFUS "), sortie)
                self.assertIn(f"{paquet} n'est pas chargé", sortie)

    def test_charge_paquet_d_espace_de_noms_refuse(self) -> None:
        for paquet in vp.PAQUETS:
            with self.subTest(paquet=paquet):
                r = self.racine(f"ns-{paquet}")
                _neuf(r, paquet)
                espace = self.racine(f"espace-{paquet}")
                (espace / paquet).mkdir()  # sans __init__.py : paquet d'espace de noms
                sortie = self._jouer(_SCRIPT_CHARGE, r, HERE, espace, "importer", paquet)
                self.assertTrue(sortie.startswith("REFUS "), sortie)
                self.assertIn("sans __file__", sortie)

    def test_charge_par_un_alias_du_meme_arbre_accepte(self) -> None:
        for paquet in vp.PAQUETS:
            r = self.racine(f"vrai-{paquet}")
            _neuf(r, paquet)
            alias = self.base / f"alias-{paquet}"
            try:
                alias.symlink_to(r, target_is_directory=True)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"lien symbolique impossible ici : {exc}")
            for racine, chemin in ((r, alias), (alias, r)):
                with self.subTest(paquet=paquet, racine=racine.name, import_par=chemin.name):
                    sortie = self._jouer(
                        _SCRIPT_CHARGE, racine, HERE, chemin / ".agents" / "vendor", "importer", paquet
                    )
                    self.assertEqual(sortie, "ACCEPTE vendor")

    def test_charge_par_tmp_alias_de_private_tmp_accepte(self) -> None:
        tmp = Path("/tmp")
        if not tmp.is_symlink():
            self.skipTest("/tmp n'est pas un alias sur ce poste (macOS seul : /tmp -> /private/tmp)")
        with tempfile.TemporaryDirectory(prefix="vendor_paths_tmp_", dir=str(tmp)) as brut:
            alias = Path(brut)  # /tmp/...
            reel = alias.resolve()  # /private/tmp/...
            self.assertNotEqual(str(alias), str(reel))
            for paquet in vp.PAQUETS:
                with self.subTest(paquet=paquet):
                    _neuf(reel, paquet)
                    sortie = self._jouer(
                        _SCRIPT_CHARGE, reel, HERE, alias / ".agents" / "vendor", "importer", paquet
                    )
                    self.assertEqual(sortie, "ACCEPTE vendor")


if __name__ == "__main__":
    unittest.main()
