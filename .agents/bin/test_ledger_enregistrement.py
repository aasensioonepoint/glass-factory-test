"""T-00001010 (E-26, BK-417) — le LEDGER « un fichier par leçon » : témoins W1-W13 du plan rév. 2.

`ledger.py` est chargé depuis CE dossier, à côté de son frère `record_id.py` (C4 du plan : `record_id_module`
le résout par `__file__`, jamais par `--root`), enregistré dans `sys.modules` avant `exec_module` (L-00000142).
Chaque appel CLI porte `--root <tmp>`, sans `CLAUDE_PROJECT_DIR` dans l'environnement enfant. Les ids créés
sont lus au retour d'`add_entry`, jamais prédits.

UN TÉMOIN DE REFUS NE PASSE QUE SUR UN `LedgerError` QUI NOMME SA GARDE (`_Socle.refus`) : toute autre issue —
acceptation, exception d'une autre nature, message d'une autre garde — est un échec d'assertion. Chaque
docstring nomme le mutant que son témoin tue ; le journal des mutants est au rapport de T-1010 (étape 7).

BORNE (Piège 2 du plan) : test_ledger.py et test_ledger_parity.py écrivent ou lisent un MONOLITHE. La forme
dossier est jugée ici, et AUSSI par test_bascule_lecteurs.py (lecteurs hors module, fixture migrée) et par
test_etat_partage_fusionnable.py (fusion de deux branches et lecteurs sur l'arbre fusionné, T-00000727). W3 et
W12 sont des garde-fous, verts à la base ; W12 épingle À DESSEIN l'absence d'un verbe CLI `migrate` : la bascule
ne l'a pas posé (elle appelle `migrate_store` en module), et le lever est le geste de migration de l'ADOPTANT,
hors T-00000727.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from typing import Any, Callable
from unittest import mock

BIN = Path(__file__).resolve().parent
ROOT = BIN.parents[1]
MONO = Path(".agents") / "state" / "memory" / "LEDGER.json"
ENTREES = Path(".agents") / "state" / "memory" / "entries"


def _charger(nom: str, chemin: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(nom, chemin)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ledger = _charger("ledger_sous_test_enregistrement", BIN / "ledger.py")
_TASKS: list[types.ModuleType] = []

#: Deux corps ULID figés (ceux de test_record_id.py) : deux entrées neuves sans horloge.
U1 = "01M3250V003HCPQKTZ8ENYF4VM"
U2 = "01M3253WN0W4D0K2S3759WV6M2"
#: Les trois ids hostiles mesurés par le critique de la rév. 1 (plan, M-NOM).
HOSTILES = ("../../escape-1", "L-1 ; touch PWN #  42", "L-1/x")
VERBES = {"add", "archive", "restore", "promote", "list", "render", "context"}
_AJOUT = re.compile(r"\ALEDGER: (L-[0-9A-Z]+) added \(")


def _tasks() -> types.ModuleType:
    """La façade `tasks.py` (le format de T-1008 vit dans sa partie `tasks_stockage.py`, qui ne se charge
    jamais seule), chargée une fois et pour W11 seulement."""
    if not _TASKS:
        _TASKS.append(_charger("tasks_sous_test_enregistrement", BIN / "tasks.py"))
    return _TASKS[0]


def ent(lid: str, created: str = "2026-07-01", status: str = "active", category: str = "lesson",
        tags: tuple[str, ...] = (), promoted: str | None = None, title: str | None = None) -> dict[str, Any]:
    entree: dict[str, Any] = {"id": lid, "category": category, "title": title or f"titre {lid}",
                              "text": f"texte {lid} é", "created": created, "tags": list(tags), "related": "",
                              "status": status}
    if promoted:
        entree["promoted"] = {"date": "2026-07-02", "ref": "AGENTS.md", "token": promoted}
    return entree


def mono() -> list[dict[str, Any]]:
    """W1 : en ordre `sort_key` ; L-009 et L-00000057 (largeurs mêlées), L-999 ARCHIVÉE entre deux actives,
    L-1000, deux ULID, `created` NON monotone, trois promues."""
    return [
        ent("L-009", "2026-07-05", category="constraint", tags=("a",), promoted="tok1"),
        ent("L-00000057", "2026-07-01", category="decision", tags=("b",)),
        ent("L-999", "2026-07-09", status="archived", category="constraint"),
        ent("L-1000", "2026-07-03", tags=("a", "b"), promoted="tok2"),
        ent(f"L-{U1}", "2026-07-08", category="constraint", promoted="tok3"),
        ent(f"L-{U2}", "2026-07-02", tags=("b",)),
    ]


def ids_de(entrees: list[dict[str, Any]]) -> list[str]:
    return [e["id"] for e in entrees]


def canon(data: Any) -> bytes:
    """Les octets de `save()` du monolithe (indent 2, clés triées, UTF-8 brut, LF), recalculés ICI."""
    return (json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def enveloppe(entree: dict[str, Any]) -> bytes:
    """Un fichier d'entrée écrit par le banc lui-même, jamais par le code jugé."""
    return canon({"format": 1, "id": entree["id"], "record": entree})


def snap(dossier: Path) -> dict[str, bytes]:
    if not dossier.exists():
        return {}
    return {str(p.relative_to(dossier)): p.read_bytes() for p in sorted(dossier.rglob("*")) if p.is_file()}


def sans_cpd() -> dict[str, str]:
    return {cle: valeur for cle, valeur in os.environ.items() if cle != "CLAUDE_PROJECT_DIR"}


def cli(racine: Path, *argv: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(BIN / "ledger.py"), "--root", str(racine), *argv],
                          capture_output=True, text=True, env=sans_cpd(), timeout=60, check=False)


def ajouter(racine: Path, titre: str) -> str:
    """`add_entry`, et l'id qu'il a RENDU."""
    trouve = _AJOUT.match(ledger.add_entry(racine, "lesson", titre))
    assert trouve, "add_entry n'a pas rendu d'id lisible"
    return trouve.group(1)


def observer(racine: Path) -> dict[str, Any]:
    return {
        "ids": ids_de(ledger.load(racine)["entries"]),
        "list": ledger.render_list(racine),
        "context": [ledger.context(racine), ledger.context(racine, context_tags=["a"]),
                    ledger.context(racine, max_chars=300), ledger.context(racine, max_chars=120, context_tags=["b"])],
    }


def hostiles_poses(racine: Path) -> list[str]:
    return sorted(str(p) for p in racine.rglob("*") if "escape" in p.name or "PWN" in p.name or p.suffix == ".tmp")


class _Socle(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.root = self.racine("r")

    def racine(self, nom: str) -> Path:
        racine = self.tmp / nom
        (racine / MONO).parent.mkdir(parents=True, exist_ok=True)
        return racine

    def poser(self, racine: Path, entrees: list[dict[str, Any]], **tete: Any) -> bytes:
        octets = canon({"entries": entrees, **tete})
        (racine / MONO).write_bytes(octets)
        return octets

    def dossier(self, racine: Path, entrees: list[dict[str, Any]]) -> Path:
        d = racine / ENTREES
        d.mkdir(parents=True, exist_ok=True)
        for entree in entrees:
            (d / f"{entree['id']}.json").write_bytes(enveloppe(entree))
        return d

    def migre(self, racine: Path, entrees: list[dict[str, Any]] | None = None) -> Path:
        self.poser(racine, mono() if entrees is None else entrees)
        ledger.migrate_store(racine)
        self.assertEqual("folder", ledger.store_form(racine))
        return racine / ENTREES

    def refus(self, appel: Callable[[], Any], *aiguilles: str) -> str:
        """Un refus NOMMÉ : un `LedgerError` dont le message porte chaque aiguille, sinon un échec d'assertion."""
        try:
            appel()
        except ledger.LedgerError as exc:
            message = str(exc)
            for aiguille in aiguilles:
                self.assertIn(aiguille, message, f"refus d'une autre garde : {message}")
            return message
        except Exception as exc:  # converti en échec d'assertion, jamais avalé
            self.fail(f"refus d'une autre nature : {type(exc).__name__}: {exc}")
        self.fail("accepté — aucun refus")


class MigrationTests(_Socle):
    def test_W1_avant_apres_identiques_ids_context_list(self) -> None:
        """W1 ⇒ M-tri-chaîne, M-status-first, M-created, M-ordre-inverse. Première jambe : un dossier BÂTI par le banc
        (sans migration, donc sans la relecture vérifiée de `migrate_store`) se lit en ordre `sort_key`."""
        bati = self.racine("bati")
        self.dossier(bati, mono()[::-1])
        self.assertEqual(ids_de(mono()), ids_de(ledger.load(bati)["entries"]), "le dossier ne se lit pas en ordre sort_key")
        octets = self.poser(self.root, mono())
        avant = observer(self.root)
        ledger.migrate_store(self.root)
        self.assertEqual("folder", ledger.store_form(self.root))
        self.assertFalse((self.root / MONO).exists(), "le monolithe survit à la migration")
        self.assertEqual(sorted(f"{i}.json" for i in ids_de(mono())),
                         sorted(p.name for p in (self.root / ENTREES).iterdir()))
        apres = observer(self.root)
        self.assertEqual(avant["ids"], apres["ids"], "l'ordre des ids a changé à la migration")
        self.assertEqual(avant, apres)
        self.assertEqual(octets, canon(ledger.load(self.root)), "l'assemblage ne rend pas les octets du monolithe")

    def test_W2_idempotente_et_no_op(self) -> None:
        """W2 ⇒ M-monolithe-gardé."""
        d = self.migre(self.root)
        self.assertFalse((self.root / MONO).exists(), "le monolithe est gardé après la migration")
        premier = snap(d)
        self.assertIn("already migrated", ledger.migrate_store(self.root))
        self.assertEqual(premier, snap(d))
        self.assertFalse((self.root / MONO).exists())
        absente = self.tmp / "absente"
        ledger.migrate_store(absente)
        self.assertFalse((absente / ENTREES).exists(), "une racine absente a créé un dossier")
        vide = self.racine("vide")
        octets = self.poser(vide, [])
        ledger.migrate_store(vide)
        self.assertFalse((vide / ENTREES).exists(), "un monolithe vide a créé un dossier")
        self.assertEqual(octets, (vide / MONO).read_bytes())

    def test_W2_cle_de_tete_inconnue_refusee_et_nommee(self) -> None:
        """W2 ⇒ M-clé-perdue."""
        octets = self.poser(self.root, mono(), extra=1)
        self.refus(lambda: ledger.migrate_store(self.root), "'extra'")
        self.assertEqual(octets, (self.root / MONO).read_bytes())
        self.assertFalse((self.root / ENTREES).exists())

    def test_W2b_monolithe_hors_ordre_refuse_nommant_l_inversion(self) -> None:
        """W2b ⇒ M-ordre-ignore."""
        entrees = mono()
        entrees[0], entrees[1] = entrees[1], entrees[0]
        octets = self.poser(self.root, entrees)
        self.refus(lambda: ledger.migrate_store(self.root), "L-00000057 is stored before L-009")
        self.assertEqual(octets, (self.root / MONO).read_bytes())
        self.assertFalse((self.root / ENTREES).exists())

    def test_W2_entries_non_vide_sans_fichier_d_entree_refuse(self) -> None:
        """Étape 5 : `entries/` non vide sans `<id>.json` ⇒ refus, rien écrit."""
        octets = self.poser(self.root, mono())
        d = self.root / ENTREES
        d.mkdir()
        (d / "x.txt").write_bytes(b"x")
        self.refus(lambda: ledger.migrate_store(self.root), str(d), "not empty")
        self.assertEqual(octets, (self.root / MONO).read_bytes())
        self.assertEqual({"x.txt": b"x"}, snap(d))

    def test_W5a_coupure_apres_k_fichiers(self) -> None:
        """W5(a) ⇒ M-staging-reste."""
        octets = self.poser(self.root, mono())
        reel = ledger._write_atomic
        appels: list[Any] = []

        def coupe(*args: Any, **kwargs: Any) -> None:
            appels.append(args)
            if len(appels) == 3:
                raise OSError("coupure simulée après deux fichiers")
            reel(*args, **kwargs)

        with mock.patch.object(ledger, "_write_atomic", side_effect=coupe), self.assertRaises(OSError):
            ledger.migrate_store(self.root)
        self.assertEqual(octets, (self.root / MONO).read_bytes())
        self.assertFalse((self.root / ENTREES).exists())
        self.assertFalse(ledger.staging_dir(self.root).exists(), "le staging survit à la coupure")
        ledger.migrate_store(self.root)
        propre = self.racine("propre")
        self.migre(propre)
        self.assertEqual(snap(propre / ENTREES), snap(self.root / ENTREES), "la relance diffère d'un run propre")

    def test_W5b_coupure_a_la_publication_garde_le_monolithe(self) -> None:
        """W5(b) ⇒ M-unlink-premier."""
        octets = self.poser(self.root, mono())
        reel = ledger._replace_with_retry
        cible_dossier = self.root / ENTREES

        def coupe(src: Any, cible: Any) -> None:
            if Path(cible) == cible_dossier:
                raise OSError("coupure simulée à la publication")
            reel(src, cible)

        with mock.patch.object(ledger, "_replace_with_retry", side_effect=coupe), self.assertRaises(OSError):
            ledger.migrate_store(self.root)
        self.assertTrue((self.root / MONO).is_file(), "le monolithe a disparu avant la publication")
        self.assertEqual(octets, (self.root / MONO).read_bytes())
        self.assertFalse((self.root / ENTREES).exists())

    def test_W5c_publication_tronquee_rollback(self) -> None:
        """W5(c) ⇒ M-sans-vérif."""
        octets = self.poser(self.root, mono())
        reel = ledger._replace_with_retry
        cible_dossier = self.root / ENTREES

        def tronque(src: Any, cible: Any) -> None:
            reel(src, cible)
            if Path(cible) == cible_dossier:
                sorted(cible_dossier.glob("L-*.json"))[0].unlink()

        with mock.patch.object(ledger, "_replace_with_retry", side_effect=tronque):
            self.refus(lambda: ledger.migrate_store(self.root), "rolled back")
        self.assertEqual(octets, (self.root / MONO).read_bytes())
        self.assertFalse((self.root / ENTREES).exists(), "le dossier tronqué est resté publié")

    def test_W5d_detection_perimee_relue_une_fois(self) -> None:
        """W5(d) ⇒ M-sans-relecture."""
        self.migre(self.root)
        reel = ledger.store_form
        perimees = ["monolith"]

        def detecte(racine: Any) -> str:
            return perimees.pop() if perimees else reel(racine)

        with mock.patch.object(ledger, "store_form", side_effect=detecte):
            try:
                lus = ids_de(ledger.load(self.root)["entries"])
            except FileNotFoundError as exc:
                self.fail(f"aucune relecture après une détection périmée : {exc}")
        self.assertEqual(ids_de(mono()), lus)


class DeuxFormesTests(_Socle):
    def test_W3_matrice_c1_un_monolithe_reste_un_monolithe(self) -> None:
        """W3 (garde-fou, vert à la base) ⇒ M-vide-migre, M-dotted-compte."""
        for etat in ("absent", "monolithe", "entries-vide", "nom-pointe"):
            with self.subTest(etat=etat):
                racine = self.racine(etat)
                if etat != "absent":
                    self.poser(racine, mono())
                d = racine / ENTREES
                if etat in ("entries-vide", "nom-pointe"):
                    d.mkdir()
                if etat == "nom-pointe":
                    (d / ".L-1.json").write_bytes(enveloppe(ent("L-1")))
                avant = snap(d)
                fait = cli(racine, "add", "--category", "lesson", "--title", "neuve")
                self.assertEqual(0, fait.returncode, fait.stderr)
                lid = _AJOUT.match(fait.stdout).group(1)
                for argv in (("archive", lid), ("restore", lid), ("promote", lid, "--ref", "AGENTS.md"),
                             ("list",), ("render",), ("context",)):
                    fait = cli(racine, *argv)
                    self.assertEqual(0, fait.returncode, f"{argv[0]} : {fait.stderr}")
                self.assertTrue((racine / MONO).is_file(), "le monolithe a disparu")
                self.assertEqual([], sorted(p.name for p in d.glob("L-*.json")) if d.is_dir() else [])
                self.assertEqual(avant, snap(d), "le dossier a bougé")

    def test_W4a_un_fichier_et_le_monolithe_refuses(self) -> None:
        """W4(a) ⇒ M-sous-ensemble."""
        self.poser(self.root, mono())
        self.dossier(self.root, mono()[:1])
        avant = snap(self.root / MONO.parent)
        self.refus(lambda: ledger.load(self.root), "DISAGREE", "L-00000057")
        fait = cli(self.root, "add", "--category", "lesson", "--title", "x")
        self.assertEqual(2, fait.returncode, fait.stdout + fait.stderr)
        self.assertIn("DISAGREE", fait.stderr)
        self.assertEqual(avant, snap(self.root / MONO.parent))

    def test_W4b_dossier_egal_lu_mais_tout_verbe_refuse(self) -> None:
        """W4(b) ⇒ M-reprise-save."""
        temoin = self.racine("temoin")
        self.poser(temoin, mono())
        self.poser(self.root, mono())
        self.dossier(self.root, mono())
        self.assertEqual("both", ledger.store_form(self.root))
        self.assertEqual(ledger.load(temoin), ledger.load(self.root))
        self.assertEqual(ledger.render_list(temoin), ledger.render_list(self.root))
        avant = snap(self.root / MONO.parent)
        for argv in (("add", "--category", "lesson", "--title", "x"), ("archive", "L-1000"),
                     ("restore", "L-999"), ("promote", "L-1000", "--ref", "AGENTS.md")):
            fait = cli(self.root, *argv)
            self.assertEqual(2, fait.returncode, f"{argv[0]} n'a pas refusé : {fait.stdout}{fait.stderr}")
            self.assertIn("both hold the ledger", fait.stderr)
        self.assertEqual(avant, snap(self.root / MONO.parent), "un verbe a écrit sous deux formes")
        ledger.migrate_store(self.root)
        self.assertEqual("folder", ledger.store_form(self.root))
        self.assertEqual(ids_de(mono()), ids_de(ledger.load(self.root)["entries"]))

    def test_W4c_branche_both_memes_controles_que_la_voie_directe(self) -> None:
        """W4c (C2 rév. 1) ⇒ M-both-sans-controle."""
        cas = {"cle-de-tete": (mono(), {"extra": 1}, "'extra'"),
               "hors-ordre": (mono()[::-1], {}, "is stored before")}
        for nom, (entrees, tete, aiguille) in cas.items():
            with self.subTest(cas=nom):
                racine = self.racine(nom)
                octets = self.poser(racine, entrees, **tete)
                self.dossier(racine, mono())
                self.assertEqual(sorted(ids_de(mono())), sorted(ids_de(ledger.load(racine)["entries"])))
                self.refus(lambda: ledger.migrate_store(racine), aiguille)
                self.assertEqual(octets, (racine / MONO).read_bytes())
        racine = self.racine("next-id")
        self.poser(racine, mono(), next_id=7)
        self.dossier(racine, mono())
        ledger.migrate_store(racine)
        self.assertEqual("folder", ledger.store_form(racine))

    def test_W4d_la_ligne_de_remede_s_execute_telle_quelle(self) -> None:
        """W4d (C3 rév. 1), racine à espace ET apostrophe ⇒ M-remede-absent."""
        racine = self.racine("s17 it's")
        self.poser(racine, mono())
        self.dossier(racine, mono())
        message = self.refus(lambda: ledger.save(racine, ledger.load(racine)), "both hold the ledger")
        lignes = [ligne for ligne in message.splitlines() if ligne.startswith("python3 -c ")]
        self.assertEqual(1, len(lignes), f"pas UNE ligne de remède : {message}")
        fait = subprocess.run(shlex.split(lignes[0]), capture_output=True, text=True, env=sans_cpd(),
                              cwd=str(self.tmp), timeout=60, check=False)
        self.assertEqual(0, fait.returncode, fait.stderr)
        self.assertEqual("folder", ledger.store_form(racine))
        self.assertEqual(ids_de(mono()), ids_de(ledger.load(racine)["entries"]))
        autre = self.racine("s17 it's bis")
        self.poser(autre, mono())
        self.dossier(autre, mono())
        fait = cli(autre, "add", "--category", "lesson", "--title", "x")
        self.assertEqual(2, fait.returncode, fait.stdout + fait.stderr)
        self.assertEqual(1, sum(1 for ligne in fait.stderr.splitlines() if ligne.startswith("python3 -c ")),
                         fait.stderr)

    def test_W4e_memes_ids_un_contenu_different_est_refuse(self) -> None:
        """W4e (exec-critic T-1010, MAJEUR :704-705) : MÊMES ids, L-1000 ARCHIVÉE dans le seul monolithe (l'écriture
        d'un vieux ledger.py) ⇒ `load` ET `migrate_store` refusent « different: L-1000 », le monolithe reste octet pour
        octet et les deux formes restent là. Tue M1 (`differ = []`) et D-differ-check (`if only_mono or only_folder:`)."""
        archivee = [dict(e, status="archived") if e["id"] == "L-1000" else e for e in mono()]
        octets = self.poser(self.root, archivee)
        self.dossier(self.root, mono())
        self.assertEqual("both", ledger.store_form(self.root))
        self.refus(lambda: ledger.load(self.root), "DISAGREE", "different: L-1000")
        self.refus(lambda: ledger.migrate_store(self.root), "DISAGREE", "different: L-1000")
        self.assertEqual(octets, (self.root / MONO).read_bytes())
        self.assertEqual("both", ledger.store_form(self.root))

    def test_W4f_la_ligne_rm_rejouee_ailleurs_n_efface_pas_un_autre_magasin(self) -> None:
        """W4f (exec-critic T-1010, MAJEUR :831 ; T6, clôture fournée 4) : `--root .` (le défaut CLI sans
        CLAUDE_PROJECT_DIR) ; le refus n'imprime AUCUN `rm` — la 2e voie est la mise de côté GARDÉE et DATÉE du dossier
        (`test -e … && test ! -e … && mv -n …`, forme de tasks.py), le texte en commentaires shell ; rejouée sans shell
        depuis la racine d'un AUTRE magasin, elle ne déplace que le dossier du sien — chemin ABSOLU —, intact, et
        refuse si la cible datée existe (jamais d'imbrication). Tue M15 (non quotée), M18 (racine non résolue),
        M-rm-r (la ligne destructive d'avant) et M-imbrication (garde `test ! -e` retirée)."""
        if os.name == "nt":
            self.skipTest("W4f : ligne de remède POSIX (L-00000079)")
        ici = self.racine("ici it's")
        self.poser(ici, mono())
        avant_ici = snap(self.dossier(ici, mono()))
        autre = self.racine("autre")
        d_autre = self.dossier(autre, mono())
        avant_autre = snap(d_autre)
        fait = subprocess.run([sys.executable, str(BIN / "ledger.py"), "--root", ".", "add", "--category", "lesson",
                               "--title", "x"], capture_output=True, text=True, env=sans_cpd(), cwd=str(ici),
                              timeout=60, check=False)
        self.assertEqual(2, fait.returncode, fait.stdout + fait.stderr)
        refus = fait.stderr.splitlines()
        self.assertTrue(refus[0].startswith("ledger.py: # "), refus[0])
        for ligne in refus[1:]:
            self.assertTrue(ligne.startswith(("# ", "python3 -c ")) or ligne.startswith("test -e ")
                            and " && test ! -e " in ligne and " && mv -n " in ligne, f"ni commentée ni gardée : {ligne}")
        lignes = [ligne for ligne in refus if " mv -n " in ligne]
        self.assertEqual(1, len(lignes), fait.stderr)
        cible = Path(shlex.split(lignes[0].split(" && ")[-1])[-1])
        self.assertTrue(cible.is_absolute() and cible.name.startswith("entries.mis-de-cote-"), lignes[0])

        def rejouer() -> subprocess.CompletedProcess:
            for maillon in lignes[0].split(" && "):
                rejoue = subprocess.run(shlex.split(maillon), capture_output=True, text=True, cwd=str(autre),
                                        timeout=60, check=False)
                if rejoue.returncode:
                    break
            return rejoue

        cible.mkdir()
        self.assertNotEqual(0, rejouer().returncode, "cible datée existante : la ligne doit refuser")
        self.assertEqual(([], "both"), (list(cible.iterdir()), ledger.store_form(ici)), "dossier imbriqué")
        cible.rmdir()
        rejoue = rejouer()
        self.assertEqual(avant_autre, snap(d_autre), f"`{lignes[0]}` a touché le dossier d'un AUTRE magasin")
        self.assertEqual(0, rejoue.returncode, rejoue.stderr)
        self.assertFalse((ici / ENTREES).exists(), "la ligne n'a pas mis de côté le dossier de SON magasin")
        self.assertEqual(("monolith", avant_ici), (ledger.store_form(ici), snap(cible)))

    def test_W4g_le_refus_colle_entier_dans_bash_ne_joue_qu_une_voie(self) -> None:
        """W4g (T6, clôture fournée 4) : le refus imprimé par le CLI (formes ÉGALES), collé ENTIER dans bash : la ligne
        `python3 -c` finit la migration, puis la mise de côté gardée voit son témoin (LEDGER.json) parti et ne joue pas
        ⇒ `folder`, toutes les entrées, rien de mis de côté. Tue M-témoin-retiré (la mise de côté jouait aussi : board
        `absent`)."""
        if os.name == "nt":
            self.skipTest("W4g : lignes de remède POSIX (L-00000079)")
        ici = self.racine("ici bash it's")
        self.poser(ici, mono())
        self.dossier(ici, mono())
        fait = cli(ici, "add", "--category", "lesson", "--title", "x")
        self.assertEqual(2, fait.returncode, fait.stdout + fait.stderr)
        subprocess.run(["bash"], input=fait.stderr, capture_output=True, text=True, cwd=str(self.tmp), env=sans_cpd(),
                       timeout=120, check=False)
        self.assertEqual("folder", ledger.store_form(ici))
        self.assertEqual(ids_de(mono()), ids_de(ledger.load(ici)["entries"]))
        self.assertEqual([], [p.name for p in (ici / ENTREES).parent.iterdir() if ".mis-de-cote-" in p.name])


class FormeDossierTests(_Socle):
    def test_W6_un_verbe_ecrit_un_seul_fichier(self) -> None:
        """W6 ⇒ M-écrit-tout."""
        d = self.migre(self.root)
        avant = snap(d)
        with mock.patch.object(ledger, "_replace_with_retry", wraps=ledger._replace_with_retry) as remplace:
            ledger.set_status(self.root, "L-1000", "archived")
        self.assertEqual(1, remplace.call_count, "un verbe a réécrit plus d'un fichier")
        apres = snap(d)
        self.assertEqual(set(avant), set(apres))
        self.assertEqual({"L-1000.json"}, {nom for nom in avant if avant[nom] != apres[nom]})
        with mock.patch.object(ledger, "_replace_with_retry", wraps=ledger._replace_with_retry) as remplace:
            lid = ajouter(self.root, "neuve")
        self.assertEqual(1, remplace.call_count)
        self.assertTrue((d / f"{lid}.json").is_file())
        self.assertFalse((self.root / MONO).exists(), "LEDGER.json recréé")
        self.assertEqual([], sorted(str(p) for p in self.tmp.rglob("*.tmp")))

    def test_W6b_un_fichier_ne_d_un_verbe_fsync_son_dossier(self) -> None:
        """W6b (critic-opus E-26, C2) : un fichier d'entrée NÉ par `add` en forme dossier voit son DOSSIER fsync
        APRÈS son écriture (`_fsync_dir`) — sinon `add` rc 0, coupure, `L-….json` absent ; un `save` qui n'écrit
        rien n'en fait aucun. Tue « fsync de dossier absent » et « fsync avant l'écriture »."""
        d = self.migre(self.root)
        journal: list[tuple[str, str]] = []
        ecrire, synchroniser = ledger._write_atomic, ledger._fsync_dir

        def ecrit(cible: Path, octets: bytes, tmp: Path) -> None:
            ecrire(cible, octets, tmp)
            journal.append(("écrit", str(cible.parent)))

        def fsync(dossier: Path) -> None:
            synchroniser(dossier)
            journal.append(("fsync", str(dossier)))

        with mock.patch.object(ledger, "_write_atomic", ecrit), mock.patch.object(ledger, "_fsync_dir", fsync):
            lid = ajouter(self.root, "neuve")
            self.assertIn(("écrit", str(d)), journal)
            apres = journal[journal.index(("écrit", str(d))) + 1:]
            self.assertIn(("fsync", str(d)), apres, f"dossier non fsync après la naissance de {lid} : {journal}")
            journal.clear()
            ledger.save(self.root, ledger.load(self.root))
            self.assertNotIn(("fsync", str(d)), journal, "un save sans écriture a fsync le dossier")
        self.assertTrue((d / f"{lid}.json").is_file())

    def test_W7_refus_a_la_lecture_nommes(self) -> None:
        """W7 ⇒ M-tombe-acceptée (cas « tombe ») ; les autres cas tiennent la forme du format."""
        cas = {
            "tombe": ({"L-1000.json": canon({"format": 1, "id": "L-1000", "record": None})},
                      ("L-1000.json", "tombstone")),
            "nom-id": ({"L-1000.json": enveloppe(ent("L-1001"))}, ("L-1000.json", "not the 'L-1000'")),
            "record-id": ({"L-1000.json": canon({"format": 1, "id": "L-1000", "record": ent("L-1001")})},
                          ("L-1000.json", "whose id is not 'L-1000'")),
            "format-2": ({"L-1000.json": canon({"format": 2, "id": "L-1000", "record": ent("L-1000")})},
                         ("L-1000.json", "newer than this code reads")),
            "cle-en-trop": ({"L-1000.json": canon({"format": 1, "id": "L-1000", "record": ent("L-1000"),
                                                   "sync_operations": []})}, ("L-1000.json", "expected exactly")),
            "json": ({"L-1000.json": b"{"}, ("L-1000.json", "not valid JSON")),
            "identite": ({"L-012.json": enveloppe(ent("L-012")), "L-00000012.json": enveloppe(ent("L-00000012"))},
                         ("L-012.json", "L-00000012.json", "identity_key")),
            "x-txt": ({"x.txt": b"x"}, ("'x.txt'", "refused")),
        }
        for nom, (fichiers, aiguilles) in cas.items():
            with self.subTest(cas=nom):
                racine = self.racine(nom)
                d = self.dossier(racine, mono())
                for fichier, octets in fichiers.items():
                    (d / fichier).write_bytes(octets)
                self.refus(lambda: ledger.load(racine), *aiguilles)

    def test_W7_save_prive_d_un_id_refuse_rien_ecrit(self) -> None:
        """W7 ⇒ M-suppression."""
        d = self.migre(self.root)
        avant = snap(d)
        data = ledger.load(self.root)
        data["entries"] = [e for e in data["entries"] if e["id"] != "L-1000"]
        self.refus(lambda: ledger.save(self.root, data), "L-1000", "never deletes")
        self.assertEqual(avant, snap(d))

    def test_W7_save_forme_dossier_refuse_un_id_qui_n_est_pas_un_nom(self) -> None:
        """W7 (C1 rév. 1, pré-passe des noms) ⇒ M-nom-libre, 3/3."""
        for rang, hostile in enumerate(HOSTILES):
            with self.subTest(id=hostile):
                racine = self.racine(f"h{rang}")
                self.migre(racine)
                etat = racine / ".agents" / "state"
                avant = snap(etat)
                data = ledger.load(racine)
                data["entries"].append(ent(hostile))
                self.refus(lambda: ledger.save(racine, data), repr(hostile), "file name")
                self.assertEqual(avant, snap(etat), "save a écrit avant de juger les noms")
                self.assertEqual([], hostiles_poses(self.tmp))
                self.assertEqual(ids_de(mono()), ids_de(ledger.load(racine)["entries"]))

    def test_W7b_migrate_refuse_un_id_qui_n_est_pas_un_nom(self) -> None:
        """W7b ⇒ M-nom-libre, 2/2 ; `L-1/x` : masque NOMMÉ (`numeric_id`, « malformed id »), sans mutant."""
        for rang, hostile in enumerate(HOSTILES[:2]):
            with self.subTest(id=hostile):
                racine = self.racine(f"m{rang}")
                entrees = sorted(mono() + [ent(hostile)], key=lambda e: ledger.sort_key(e["id"]))
                self.assertEqual(ids_de(entrees), sorted(ids_de(entrees), key=ledger.sort_key),
                                 "fixture hors ordre : la garde d'ordre masquerait celle du nom")
                octets = self.poser(racine, entrees)
                message = self.refus(lambda: ledger.migrate_store(racine), repr(hostile), "file name")
                self.assertNotIn("sort_key", message, "la garde jugée est celle de l'ordre, pas celle du nom")
                self.assertEqual(octets, (racine / MONO).read_bytes())
                self.assertFalse((racine / ENTREES).exists())
                self.assertFalse(ledger.staging_dir(racine).exists())
                self.assertEqual([], hostiles_poses(self.tmp))
        racine = self.racine("m2")
        octets = self.poser(racine, mono() + [ent("L-1/x")])
        self.refus(lambda: ledger.migrate_store(racine), "malformed id")
        self.assertEqual(octets, (racine / MONO).read_bytes())
        self.assertFalse((racine / ENTREES).exists())

    def test_W7c_reserve_c1_dossier_au_nom_d_entree_ou_entries_fichier_rc2(self) -> None:
        """Réserve C1 du mandat ⇒ M-is-file, M-is-dir."""
        d = self.migre(self.root)
        (d / "L-2.json").mkdir()
        fait = cli(self.root, "list")
        self.assertEqual(2, fait.returncode, fait.stdout + fait.stderr)
        self.assertIn("L-2.json", fait.stderr)
        self.assertIn("is_file", fait.stderr)
        autre = self.racine("entries-fichier")
        octets = self.poser(autre, mono())
        (autre / ENTREES).write_bytes(b"pas un dossier")
        fait = cli(autre, "add", "--category", "lesson", "--title", "x")
        self.assertEqual(2, fait.returncode, fait.stdout + fait.stderr)
        self.assertIn("is_dir", fait.stderr)
        self.assertEqual(octets, (autre / MONO).read_bytes())

    def test_W7d_reserve_c2_chiffres_non_ascii_refuses(self) -> None:
        """Réserve C2 du mandat ⇒ M-unicode."""
        self.assertTrue(ledger._ENTRY_NAME.flags & re.ASCII, "_ENTRY_NAME n'est pas compilé en re.ASCII")
        for rid in ("L-١٢", "L-１２"):
            with self.subTest(id=rid):
                self.refus(lambda: ledger.entry_file(self.tmp, rid), repr(rid), "file name")

    def test_W7e_numeric_id_ascii_nan_et_surrogat_refuses(self) -> None:
        """W7e (passe de clôture E-26, la COPIE ledger.py du correctif T-1008) : `numeric_id` ne lit que des chiffres
        ASCII (`L-١٢`, `L-١12` : « malformed id », jamais 12) ; `record_bytes` refuse en `LedgerError` un NaN /
        Infinity et un surrogat isolé (`UnicodeEncodeError` brut avant) — des octets qu'aucun lecteur ne relit."""
        for rid in ("L-١٢", "L-١12"):
            with self.subTest(id=rid):
                self.refus(lambda: ledger.numeric_id(rid), "malformed id")
        self.assertEqual(12, ledger.numeric_id("L-012"), "contrôle : un id ASCII reste lu")
        for nom, champ in (("NaN", {"poids": float("nan")}), ("Infinity", {"poids": float("-inf")}),
                           ("surrogat", {"title": "\udc80"})):
            env = {"format": 1, "id": "L-5", "record": dict(ent("L-5"), **champ)}
            with self.subTest(octets=nom):
                self.refus(lambda: ledger.record_bytes(env), "'L-5'", "strict UTF-8 JSON")
        self.assertEqual(enveloppe(ent("L-5")), ledger.record_bytes({"format": 1, "id": "L-5", "record": ent("L-5")}))

    def test_W8_la_validation_porte_sur_l_entree_lue(self) -> None:
        """W8 ⇒ M-validation-sautée."""
        d = self.migre(self.root)
        (d / "L-1000.json").write_bytes(enveloppe(ent("L-1000", category="bogus")))
        message = self.refus(lambda: ledger.load(self.root), "has category 'bogus'")
        self.assertTrue(message.startswith(str(d / "L-1000.json")), message)


class FermetureTests(_Socle):
    def test_W9_deux_ajouts_paralleles_fusionnent_sans_conflit(self) -> None:
        """W9 (dépôt jetable, identité LOCALE) ⇒ M-un-fichier."""
        if shutil.which("git") is None:
            self.skipTest("W9 : git absent")
        self.migre(self.root)
        env = {cle: valeur for cle, valeur in sans_cpd().items() if not cle.startswith("GIT_")}
        env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")

        def git(*argv: str) -> None:
            fait = subprocess.run(["git", "-c", "user.name=Banc T-1010", "-c", "user.email=banc@example.invalid",
                                   "-c", "commit.gpgsign=false", *argv], cwd=str(self.root), capture_output=True,
                                  text=True, env=env, timeout=60, check=False)
            self.assertEqual(0, fait.returncode, f"git {argv[0]} : {fait.stdout}{fait.stderr}")

        git("init", "-q", "-b", "main")
        git("add", "--", ".agents/state/memory")
        git("commit", "-q", "-m", "base")
        ids = {}
        for branche in ("a", "b"):
            git("switch", "-q", "-c", branche, "main")
            ids[branche] = ajouter(self.root, f"de {branche}")
            git("add", "--", ".agents/state/memory")
            git("commit", "-q", "-m", branche)
        git("merge", "-q", "--no-edit", "a")
        lus = ids_de(ledger.load(self.root)["entries"])
        self.assertEqual(len(mono()) + 2, len(lus))
        self.assertIn(ids["a"], lus)
        self.assertIn(ids["b"], lus)
        self.assertFalse((self.root / MONO).exists())

    def test_W10_une_copie_seule_lit_et_ecrit_les_deux_formes(self) -> None:
        """W10 (aucun import d'un frère, S-00003552) ⇒ M-import."""
        bin_seul = self.tmp / "seule" / ".agents" / "bin"
        bin_seul.mkdir(parents=True)
        copie = bin_seul / "ledger.py"
        copie.write_bytes((BIN / "ledger.py").read_bytes())
        self.assertEqual(["ledger.py"], sorted(p.name for p in bin_seul.iterdir()), "la copie a un frère")
        dossier = self.racine("dossier")
        self.migre(dossier)
        monolithe = self.racine("monolithe")
        self.poser(monolithe, mono())
        for racine in (dossier, monolithe):
            with self.subTest(forme=racine.name):
                for argv in (("list",), ("archive", "L-1000")):
                    fait = subprocess.run([sys.executable, "-I", str(copie), "--root", str(racine), *argv],
                                          capture_output=True, text=True, env=sans_cpd(), cwd=str(self.tmp),
                                          timeout=60, check=False)
                    self.assertEqual(0, fait.returncode, fait.stderr)
                statut = {e["id"]: e["status"] for e in ledger.load(racine)["entries"]}
                self.assertEqual("archived", statut["L-1000"])
        self.assertEqual("folder", ledger.store_form(dossier))

    def test_W11_parite_d_octets_avec_le_format_de_t1008(self) -> None:
        """W11 (CONDITIONNEL P2 : le format de T-1008 est présent) ⇒ M-ensure-ascii, M-indent."""
        tasks = _tasks()
        if not hasattr(tasks, "record_bytes"):
            self.skipTest("W11 : le format de T-1008 (record_bytes) est absent de tasks_stockage.py")
        for entree in mono() + [ent("L-42", title="ünïcödé ✓   fin")]:
            with self.subTest(id=entree["id"]):
                env = {"format": 1, "id": entree["id"], "record": entree}  # sans sync_operations : collection entries
                self.assertEqual(tasks.record_bytes(env), ledger.record_bytes(env))
                self.assertEqual(tasks.record_file(self.tmp, entree["id"]), ledger.entry_file(self.tmp, entree["id"]))
        d = self.migre(self.root)
        fichiers = {f"entries/{p.name}": p.read_bytes() for p in d.iterdir()}
        self.assertEqual(tasks.assemble_store(fichiers, ("entries",)), ledger.load(self.root))

    def test_W12_aucun_verbe_cli_migrate(self) -> None:
        """W12 (garde-fou) : épingle l'absence d'un verbe CLI `migrate` — la bascule ne l'a pas levée (elle appelle
        `migrate_store` en module) ; le lever est le geste de migration de l'adoptant, hors T-00000727 ⇒
        M-verbe-migrate."""
        sous = [a for a in ledger.build_parser()._actions if isinstance(a, argparse._SubParsersAction)]
        self.assertEqual(1, len(sous))
        self.assertEqual(VERBES, set(sous[0].choices))

    def test_W13_magasin_reel_copie_context_et_octets(self) -> None:
        """W13 (kit seul) : le magasin réel COPIÉ sous tmp, jamais migré en place ⇒ M-ulid-avant. Monolithe réel ⇒
        sa migration, inchangée. Dossier réel (le kit basculé, T-00000727) ⇒ la copie du dossier ET son équivalent
        monolithe (`canon` de son assemblage) sous une 2e racine : `six()` égaux, puis `migrate_store` de la 2e
        redonne les octets de la copie, fichier pour fichier (l'échec nomme le PREMIER fichier divergent, jamais un
        diff de tout le magasin). Kit sans AUCUNE forme ⇒ ÉCHEC, plus un saut ; hors kit ⇒ saut. MW1 : la copie
        du dossier réel remplacée par un dossier vide ⇒ rouge."""
        reel, dossier = ROOT / MONO, ROOT / ENTREES
        if not (ROOT / ".agents" / "IS_THE_KIT").is_file():
            self.skipTest("W13 : kit seul — .agents/IS_THE_KIT absent")
        if not reel.is_file() and not dossier.is_dir():
            self.fail("W13 : le kit ne porte AUCUNE forme du LEDGER réel — ni LEDGER.json ni memory/entries/")

        def six(racine: Path) -> list[Any]:
            return [ids_de(ledger.load(racine)["entries"]), ledger.context(racine),
                    ledger.context(racine, context_tags=["security"]),
                    ledger.context(racine, context_tags=["ledger", "index"]), ledger.context(racine, max_chars=1200),
                    ledger.context(racine, max_chars=500), ledger.context(racine, max_chars=300, context_tags=["cost"])]

        racine = self.racine("reel")
        if reel.is_file():
            octets = reel.read_bytes()
            (racine / MONO).write_bytes(octets)
            avant = six(racine)
            ledger.migrate_store(racine)
            self.assertEqual("folder", ledger.store_form(racine))
            self.assertEqual(avant, six(racine))
            self.assertEqual(octets, canon(ledger.load(racine)), "l'assemblage du réel ne rend pas ses octets")
            return
        shutil.copytree(dossier, racine / ENTREES)
        self.assertEqual("folder", ledger.store_form(racine))
        copie = snap(racine / ENTREES)
        # La copie est le magasin ENTIER (MWpart, un seul fichier copié, passait : `six()` et les octets se jugeaient
        # alors sur la copie partielle des DEUX côtés — réserve 4 de l'exec-critic de T-00000727).
        reels = sorted(p.name for p in dossier.iterdir())
        self.assertEqual(len(reels), len(copie), "copie PARTIELLE du magasin réel : premier manquant "
                                                 f"{next((n for n in reels if n not in copie), None)!r}")
        equivalent = self.racine("reel-monolithe")
        (equivalent / MONO).write_bytes(canon(ledger.load(racine)))
        self.assertEqual(six(racine), six(equivalent))
        ledger.migrate_store(equivalent)
        rendu = snap(equivalent / ENTREES)
        divergent = next((nom for nom in sorted(set(copie) | set(rendu)) if copie.get(nom) != rendu.get(nom)), None)
        self.assertIsNone(divergent, "la migration du monolithe équivalent ne redonne pas les octets du dossier réel : "
                                     f"premier fichier divergent {divergent!r} ({len(copie)} copiés, {len(rendu)} "
                                     "rendus)")


if __name__ == "__main__":
    unittest.main()
