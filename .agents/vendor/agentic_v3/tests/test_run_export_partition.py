"""Témoins du marqueur interne de racine et du signal des partitions apparentées
(T-00000692 ; décision pilote S-00002199 options C+D ; S-00002240).

Chaque banc pose SES `CADRE_STATE_DIR` et `CADRE_PROJECT_ROOT` jetables AVANT
toute résolution : rien n'est lu ni écrit sous le vrai `~/.local/state/cadre/`
ni sous le `runs/` du dépôt (leçon L-00000527). Les dépôts git sont créés dans
le bac, avec des messages de commit DISTINCTS par dépôt : deux `git init` aux
mêmes auteur, date et message rendraient le MÊME commit racine, et J2 les
rapprocherait à tort (bruit de banc nommé dans `signaler_partitions_apparentees`).

Chaque témoin nomme la mutation qui le rougit, jouée une fois à la main (E1).
"""

import hashlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from agentic_v3.db import run_export
from agentic_v3.db.event_store import EventStore

#: L'en-tête que le pilote `grep` (critère E3 du plan, octets : apostrophe
#: ASCII, `É` précomposé U+00C9).
EN_TETE = "PARTITION D'\u00c9TAT APPARENT\u00c9E"
ULID = "01ARZ3NDEKTSV4RRFFQ69G5FAV"


def _git(cwd: Path, *args: str) -> str:
    """git dans le bac, identité fournie par `-c` (jamais l'identité du poste)."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    r = subprocess.run(
        ["git", "-C", str(cwd), "-c", "user.email=banc@example.invalid",
         "-c", "user.name=banc", *args],
        capture_output=True, text=True, check=True, env=env,
    )
    return r.stdout.strip()


def _empreinte_arbre(racine: Path) -> dict:
    """`{chemin relatif: sha256}` de chaque fichier sous `racine` — le témoin (m)."""
    return {
        str(p.relative_to(racine)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(racine.rglob("*")) if p.is_file()
    }


class _Bac(unittest.TestCase):
    """Un bac par test : `CADRE_STATE_DIR` posé, `CADRE_PROJECT_ROOT` RETIRÉ (chaque
    construction le pose explicitement via `store`/`partition`)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.bac = Path(self._tmp.name).resolve()
        self.state = self.bac / "state"
        env = {k: v for k, v in os.environ.items() if k != "CADRE_PROJECT_ROOT"}
        env["CADRE_STATE_DIR"] = str(self.state)
        self._env = mock.patch.dict(os.environ, env, clear=True)
        self._env.start()
        self.addCleanup(self._env.stop)
        run_export._paths().vider_cache_racine()

    # --- fabriques ----------------------------------------------------------
    def depot(self, nom: str) -> Path:
        racine = self.bac / nom
        racine.mkdir()
        _git(racine, "init", "-q")
        _git(racine, "commit", "-q", "--allow-empty", "-m", f"init {nom}")
        return racine

    def partition(self, racine: Path) -> Path:
        with mock.patch.dict(os.environ, {"CADRE_PROJECT_ROOT": str(racine)}):
            return run_export.state_project()

    def store(self, racine: Path, **kw) -> "tuple[EventStore, str]":
        """Construit un `EventStore` depuis `racine`, stderr capturé."""
        err = io.StringIO()
        with mock.patch.dict(os.environ, {"CADRE_PROJECT_ROOT": str(racine)}):
            with redirect_stderr(err):
                s = EventStore(**kw)
        return s, err.getvalue()

    def soeur_sans_marqueur(self, nom: str, copie: str) -> Path:
        """Une partition SŒUR née avant ce lot : `run/copie`, aucun marqueur."""
        p = self.state / "projets" / nom
        (p / "run").mkdir(parents=True)
        (p / "run" / "copie").write_text(copie + "\n", encoding="utf-8")
        return p

    @staticmethod
    def marqueur(partition: Path) -> dict:
        return json.loads((partition / "racine.json").read_text(encoding="utf-8"))

    @staticmethod
    def cache(partition: Path) -> dict:
        """Le cache `apparentees.json` ENTIER : `{"soeurs": [...], "apparentees": [...]}`."""
        return json.loads((partition / "apparentees.json").read_text(encoding="utf-8"))

    @classmethod
    def apparentees(cls, partition: Path) -> dict:
        return {e["partition"]: e for e in cls.cache(partition)["apparentees"]}

    @staticmethod
    def identite_forgee(racine: str, modele: Path) -> dict:
        """Une identité de racine FORGÉE (`racine` libre, `(dev, ino)` de `modele`)."""
        st = os.stat(modele)
        return {
            "racine": racine, "dev": int(st.st_dev), "ino": int(st.st_ino),
            "commits_racines": None, "remote": None,
        }

    @staticmethod
    def empreinte(racine: str) -> str:
        """`sha256(racine)[:16]` comme `cadre.paths._empreinte_de_racine` (surrogateescape)."""
        return hashlib.sha256(racine.encode("utf-8", "surrogateescape")).hexdigest()[:16]


class TestMarqueur(_Bac):
    def test_a_naissance_marqueur_complet_racine_canonique(self) -> None:
        # (a) La racine est passée par LIEN SYMBOLIQUE, sans `CADRE_PROJECT_ROOT` :
        # le marqueur doit porter la graphie CANONIQUE (résolue), jamais la tapée.
        # MUTATION : dans `_identite_racine`, `racine = Path(depuis)` (graphie
        # tapée) → l'empreinte n'est plus le nom du dossier, écriture REFUSÉE, rouge.
        if os.name == "nt":
            self.skipTest("lien symbolique sans privilège : POSIX seulement")
        racine = self.depot("a")
        lien = self.bac / "lien"
        lien.symlink_to(racine, target_is_directory=True)
        err = io.StringIO()
        with redirect_stderr(err):
            s = EventStore(project_root=lien)
        partition = Path(s.db_path).parents[1]
        self.assertTrue((partition / "racine.json").is_file(), err.getvalue())
        m = self.marqueur(partition)
        canonique = run_export.project_root(lien).resolve().as_posix()
        self.assertEqual(m["racine"], canonique)
        self.assertNotEqual(m["racine"], lien.as_posix(), "graphie tapée écrite")
        self.assertEqual(
            hashlib.sha256(m["racine"].encode("utf-8")).hexdigest()[:16], partition.name
        )
        st = os.stat(racine)
        self.assertEqual((m["dev"], m["ino"]), (st.st_dev, st.st_ino))
        self.assertEqual(m["commits_racines"], [_git(racine, "rev-list", "--max-parents=0", "HEAD")])
        self.assertEqual(m["format"], run_export.FORMAT_MARQUEUR)
        self.assertEqual(m["origine"], "naissance")
        self.assertIsNone(m["remote"])
        self.assertRegex(m["ecrit_le"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertEqual(run_export.lire_marqueur_partition(partition), m)

    def test_b_marqueur_etranger_reste_octet_pour_octet(self) -> None:
        # (b) Un `racine.json` invalide PRÉEXISTANT n'est ni relu comme preuve ni
        # réécrit. Les octets intacts sont tenus DEUX fois — le CHEMIN RAPIDE
        # `exists()` d'`assurer_marqueur_partition` court-circuite l'écrivain, et
        # l'écrivain est exclusif — donc ce témoin ne rougit sur AUCUNE des deux
        # seule et ne prouve RIEN sur l'écrivain (c'est (b bis) qui l'atteint).
        # MUTATION qui le rougit : retirer la vérification d'empreinte de `lire_
        # marqueur_partition` (`return obj` inconditionnel) → le marqueur étranger
        # devient une preuve, `assertIsNone` rouge.
        racine = self.depot("b")
        partition = self.partition(racine)
        partition.mkdir(parents=True)
        octets = b'{"format": 1, "racine": "/ailleurs"}\n'
        (partition / "racine.json").write_bytes(octets)
        self.assertIsNone(run_export.lire_marqueur_partition(partition))
        _, err = self.store(racine)
        self.assertEqual((partition / "racine.json").read_bytes(), octets)
        self.assertIsNone(run_export.lire_marqueur_partition(partition))
        self.assertNotIn(EN_TETE, err)

    def test_b_bis_ecrivain_exclusif_octets_etrangers_intacts(self) -> None:
        # (b bis) ATTEINT l'écrivain : le chemin rapide voit le marqueur ABSENT, puis
        # `_identite_racine` (patchée, identité VRAIE + effet de bord) pose des
        # octets étrangers AVANT que l'écrivain ne tente sa création exclusive.
        # MUTATION : `os.replace(tmp, chemin)` dans `_ecrire_une_fois` → rouge.
        racine = self.depot("b2")
        partition = self.partition(racine)
        partition.mkdir(parents=True)
        chemin = partition / "racine.json"
        octets = b'{"format": 1, "racine": "/apparu/entre-temps"}\n'
        original = run_export._identite_racine

        def identite_puis_intrus(depuis=None):
            identite = original(depuis)
            chemin.write_bytes(octets)
            return identite

        self.assertFalse(chemin.exists())
        with mock.patch.object(run_export, "_identite_racine", identite_puis_intrus):
            err = io.StringIO()
            with redirect_stderr(err):
                run_export.assurer_marqueur_partition(partition, racine)
        self.assertEqual(chemin.read_bytes(), octets)
        self.assertEqual(err.getvalue(), "")
        self.assertEqual(list(partition.glob("*.tmp")), [], "temporaire abandonné")

    def test_f3_racine_non_decodable_marqueur_ecrit(self) -> None:
        # (F3) Une racine en `surrogateescape` (`'\udce9'`) doit ÊTRE ÉCRITE : avec
        # `ensure_ascii=False`, `json.dumps` rend la surrogate telle quelle et c'est
        # l'ENCODAGE UTF-8 de l'écriture qui lève `UnicodeEncodeError` (pas OSError)
        # — le marqueur ne s'écrivait jamais. Jambe 1, TOUJOURS jouée : l'écrivain
        # est atteint par patch (la partition est nommée en HEX, seul le JSON porte
        # la surrogate). Jambe 2, de bout en bout, SEULEMENT là où le FS accepte le
        # nom : APFS le REFUSE (`errno 92 Illegal byte sequence`, mesuré), donc sur
        # macOS seule la jambe 1 tourne ; ext4 accepte, les deux tournent.
        # MUTATION : remettre `ensure_ascii=False` dans `_json_texte` → rouge (jambe 1).
        forge = (self.bac / "x\udce9").as_posix()
        partition = self.state / "projets" / self.empreinte(forge)
        partition.mkdir(parents=True)
        identite = self.identite_forgee(forge, self.bac)
        with mock.patch.object(run_export, "_identite_racine", lambda depuis=None: identite):
            err = io.StringIO()
            with redirect_stderr(err):
                chemin = run_export.assurer_marqueur_partition(partition)
        self.assertEqual(err.getvalue(), "")
        self.assertEqual(chemin, partition / "racine.json")
        self.assertEqual(self.marqueur(partition)["racine"], forge)
        # Le même texte, par la fonction d'encodage seule : ASCII pur, rechargeable.
        texte = run_export._json_texte({"racine": forge})
        self.assertTrue(texte.isascii())
        self.assertEqual(json.loads(texte)["racine"], forge)
        # Jambe 2 : de bout en bout si le système de fichiers accepte le nom.
        try:
            racine = self.depot("y\udce9")
        except OSError:
            return  # FS qui refuse le nom (APFS) : jambe 1 seule, dite ci-dessus
        _, err2 = self.store(racine)
        p2 = self.partition(racine)
        self.assertTrue((p2 / "racine.json").is_file(), err2)
        self.assertTrue(self.marqueur(p2)["racine"].endswith("y\udce9"))

    def test_l_bis_sans_identifiants_huit_formes(self) -> None:
        # (F4) Toute la partie userinfo, la query-string et le fragment sont retirés
        # sur la forme à schéma ; la forme scp et le chemin local sont inchangés.
        # MUTATION : revenir à `re.sub(r"^(schéma://)[^/@]*@", ...)` → `p@ss@h`
        # garde `ss@`, `?access_token=S` et `#S` passent → rouge.
        cas = {
            "https://u:p@h/x.git": "https://h/x.git",
            "https://tok@h/x.git": "https://h/x.git",
            "https://u:p@ss@h/x.git": "https://h/x.git",
            "https://h/x.git?access_token=S": "https://h/x.git",
            "https://h/x.git#S": "https://h/x.git",
            "git@h:o/x.git": "git@h:o/x.git",
            "ssh://u@h/x.git": "ssh://h/x.git",
            "/chemin/local": "/chemin/local",
            # Bornes : port conservé, IPv6 re-crocheté, `file://` sans hôte intact.
            "https://u:p@h:8443/x.git": "https://h:8443/x.git",
            "ssh://u@[::1]:2222/x.git": "ssh://[::1]:2222/x.git",
            "file:///chemin/local.git": "file:///chemin/local.git",
        }
        for entree, attendu in cas.items():
            with self.subTest(entree=entree):
                self.assertEqual(run_export._sans_identifiants(entree), attendu)
        for entree in cas:
            with self.subTest(secret=entree):
                sortie = run_export._sans_identifiants(entree)
                for secret in ("p@", "tok", "ss@", "access_token", "S", "u@", "u:"):
                    self.assertNotIn(secret, sortie)

    def test_c_partition_preexistante_sans_marqueur_adoption(self) -> None:
        # (c) MUTATION : `origine="naissance"` inconditionnel dans `__init__` → rouge.
        racine = self.depot("c")
        partition = self.partition(racine)
        (partition / "run").mkdir(parents=True)
        self.store(racine)
        self.assertEqual(self.marqueur(partition)["origine"], "adoption")

    def test_c_bis_sites_createurs_de_run_export_naissance_puis_adoption(self) -> None:
        # Étape 2 : les trois créateurs posent le marqueur avec une SONDE avant le
        # mkdir. `identifiant_de_copie` sur racine neuve → naissance ; `_verrou_
        # export` sur une partition existante sans marqueur → adoption.
        racine = self.depot("c2")
        with mock.patch.dict(os.environ, {"CADRE_PROJECT_ROOT": str(racine)}):
            run_export.identifiant_de_copie()
            partition = run_export.state_project()
            self.assertEqual(self.marqueur(partition)["origine"], "naissance")
            (partition / "racine.json").unlink()
            with run_export._verrou_export():
                pass
            self.assertEqual(self.marqueur(partition)["origine"], "adoption")
            (partition / "racine.json").unlink()
            run_export.ecrire_journal_attente({"ulid": ULID})
            self.assertEqual(self.marqueur(partition)["origine"], "adoption")

    def test_d_lecture_ne_cree_rien(self) -> None:
        # (d) Un appel en LECTURE sur une racine neuve ne fait naître AUCUN dossier.
        # MUTATION qui ATTEINT l'écriture : dans `lister_journaux_attente`, appeler
        # `assurer_marqueur_partition(dossier.parents[1], depuis)` ET, dans
        # l'écrivain, `partition.mkdir(parents=True, exist_ok=True)` avant le tmp
        # → la partition naît, rouge. (« Appeler l'écrivain en lecture » seul ne
        # crée rien — l'écrivain ne crée pas le dossier — et ne rougirait pas.)
        racine = self.depot("d")
        with mock.patch.dict(os.environ, {"CADRE_PROJECT_ROOT": str(racine)}):
            partition = run_export.state_project()
            self.assertEqual(run_export.lister_journaux_attente(), [])
            run_export.journal_attente(ULID)
            self.assertIsNone(run_export.lire_marqueur_partition(partition))
            self.assertEqual(run_export.relever_partitions_apparentees(partition), [])
        self.assertFalse(self.state.exists(), "un appel en lecture a créé le state")

    def test_e_cle_inchangee_deux_clones_distincts(self) -> None:
        # (e) Le nom de la partition EST l'empreinte de la racine canonique, et deux
        # `git clone` du même dépôt donnent deux partitions DISTINCTES.
        racine = self.depot("e")
        partition = self.partition(racine)
        attendu = run_export._paths()._empreinte_de_racine(
            run_export.project_root(racine).resolve()
        )
        self.assertEqual(partition.name, attendu)
        _git(self.bac, "clone", "-q", str(racine), str(self.bac / "e1"))
        _git(self.bac, "clone", "-q", str(racine), str(self.bac / "e2"))
        p1, p2 = self.partition(self.bac / "e1"), self.partition(self.bac / "e2")
        self.assertEqual(len({partition.name, p1.name, p2.name}), 3)

    def test_l_remote_sans_identifiants(self) -> None:
        # (l) MUTATION : retirer `_sans_identifiants` → `jeton` dans le marqueur, rouge.
        racine = self.depot("l")
        _git(racine, "remote", "add", "origin", "https://u:jeton@h/x.git")
        self.store(racine)
        partition = self.partition(racine)
        self.assertEqual(self.marqueur(partition)["remote"], "https://h/x.git")
        self.assertNotIn("jeton", (partition / "racine.json").read_text(encoding="utf-8"))

    def test_base_explicite_ailleurs_ne_marque_rien_et_se_tait(self) -> None:
        # Étape 3 (i) : une base hors de la partition ne marque rien, sans un mot.
        racine = self.depot("x")
        _, err = self.store(racine, db_path=self.bac / "ailleurs.db")
        self.assertFalse(self.state.exists())
        self.assertEqual(err, "")


class TestRelevePuisSignal(_Bac):
    def test_f_mv_tient_J1_et_cp_ne_le_tient_pas(self) -> None:
        # (f) MUTATION : retirer le test `(dev, ino)` de J1 → la COPIE porte J1, rouge.
        a = self.depot("a")
        self.store(a)
        pa = self.partition(a)
        b = self.bac / "b"
        os.rename(a, b)
        _, err = self.store(b)
        pb = self.partition(b)
        self.assertNotEqual(pa.name, pb.name)
        self.assertEqual(self.apparentees(pb)[pa.name]["jambes"], ["J1", "J2"])
        self.assertEqual(err.count(EN_TETE), 1)
        self.assertIn(pa.name, err)
        self.assertIn(pb.name, err)
        self.assertIn("J1", err)
        self.assertIn("ABSENT du disque", err)
        self.assertIn(f"touch {pb / 'acquittements' / pa.name}", err)
        self.assertNotIn("J2 seule", err, "J1 tient aussi : pas de note J2 seule")
        c = self.bac / "c"
        shutil.copytree(b, c, symlinks=True)
        _, err_c = self.store(c)
        pc = self.partition(c)
        entrees = self.apparentees(pc)
        self.assertEqual(set(entrees), {pa.name, pb.name})
        for nom in (pa.name, pb.name):
            self.assertNotIn("J1", entrees[nom]["jambes"], nom)
            self.assertIn("J2", entrees[nom]["jambes"], nom)
        self.assertEqual(err_c.count(EN_TETE), 2)

    def test_g_J2_deux_clones_rien_sans_lien(self) -> None:
        # (g) MUTATION : UNION au lieu d'intersection des commits racines → le dépôt
        # sans lien est rapproché, rouge.
        a = self.depot("a")
        self.store(a)
        pa = self.partition(a)
        c = self.bac / "c"
        _git(self.bac, "clone", "-q", str(a), str(c))
        _, err = self.store(c)
        pc = self.partition(c)
        self.assertEqual(self.apparentees(pc)[pa.name]["jambes"], ["J2"])
        self.assertEqual(err.count(EN_TETE), 1)
        # J2 SEULE ⇒ la note « deux PROJETS différents ⇒ acquitter » (fable (3)) ;
        # elle est ABSENTE quand J1 tient aussi (voir (f)).
        self.assertIn("J2 seule", err)
        x = self.depot("x")
        _, err_x = self.store(x)
        self.assertEqual(self.apparentees(self.partition(x)), {})
        self.assertNotIn(EN_TETE, err_x)

    def test_h_J3_copie_versionnee_ici_rien_sinon(self) -> None:
        # (h) MUTATION : retirer J3 → aucune entrée, rouge.
        r = self.depot("r")
        (r / "runs" / "0123456789abcdef" / "aaaaaaaaaaaaaaaa").mkdir(parents=True)
        s1 = self.soeur_sans_marqueur("1111111111111111", "aaaaaaaaaaaaaaaa")
        self.soeur_sans_marqueur("2222222222222222", "bbbbbbbbbbbbbbbb")
        self.soeur_sans_marqueur("3333333333333333", "backfill")
        _, err = self.store(r)
        pr = self.partition(r)
        entrees = self.apparentees(pr)
        self.assertEqual(set(entrees), {s1.name})
        self.assertEqual(entrees[s1.name]["jambes"], ["J3"])
        self.assertIsNone(entrees[s1.name]["racine"])
        self.assertEqual(err.count(EN_TETE), 1)
        self.assertIn("sans marqueur", err)
        self.assertIn("aaaaaaaaaaaaaaaa", err)
        self.assertNotIn("2222222222222222", err)
        # Texte de reprise (fable (2)(4), opus F5) : le libellé J3 dit « commités ou
        # non », la reprise nomme la MÉTHODE Python et l'absence de verbe CLI, et
        # ce qui n'est PAS rebâti.
        self.assertIn("commités ou non", err)
        self.assertIn("EventStore.reconstruire_depuis_exports", err)
        self.assertIn("AUCUN verbe CLI", err)
        self.assertIn("T-00000691", err)
        self.assertIn("déplacement voulu : acquitter", err)
        # T-00000691 : le pont board se rebâtit AVEC les événements — le texte de
        # reprise ne doit plus dire le contraire. MUTATION : restaurer l'ancien
        # `_LIGNES_REPRISE` (« ne sont PAS rebâtis ») → rouge.
        self.assertIn("se rebâtissent depuis runs/", err)
        self.assertNotIn("ne sont PAS rebâtis", err)

    def test_i_acquittement_et_disparition_taisent(self) -> None:
        # (i) MUTATION : ignorer `acquittements/` → le bloc persiste, rouge.
        r = self.depot("r")
        (r / "runs" / "0123456789abcdef" / "aaaaaaaaaaaaaaaa").mkdir(parents=True)
        s1 = self.soeur_sans_marqueur("1111111111111111", "aaaaaaaaaaaaaaaa")
        _, err = self.store(r)
        self.assertEqual(err.count(EN_TETE), 1)
        pr = self.partition(r)
        _, err2 = self.store(r)
        self.assertEqual(err2.count(EN_TETE), 1, "le signal se RÉPÈTE (S-00002240)")
        (pr / "acquittements").mkdir()
        (pr / "acquittements" / s1.name).touch()
        _, err3 = self.store(r)
        self.assertNotIn(EN_TETE, err3)
        self.assertNotIn(s1.name, err3)
        (pr / "acquittements" / s1.name).unlink()
        cache_avant = (pr / "apparentees.json").read_bytes()
        os.rename(s1, self.bac / "hors" )
        _, err4 = self.store(r)
        self.assertNotIn(EN_TETE, err4)
        # Une DISPARITION ne rejoue pas le relevé (seule une APPARITION le fait) :
        # le cache est resté octet pour octet.
        self.assertEqual((pr / "apparentees.json").read_bytes(), cache_avant)

    def test_j_releve_une_fois_tant_qu_aucune_soeur_n_apparait(self) -> None:
        # (j) MUTATION : relever à chaque construction → compteur 3, rouge.
        r = self.depot("r")
        (r / "runs" / "0123456789abcdef" / "aaaaaaaaaaaaaaaa").mkdir(parents=True)
        self.soeur_sans_marqueur("1111111111111111", "aaaaaaaaaaaaaaaa")
        original = run_export.relever_partitions_apparentees
        appels = []

        def compte(partition, depuis=None):
            appels.append(partition)
            return original(partition, depuis)

        with mock.patch.object(run_export, "relever_partitions_apparentees", compte):
            for _ in range(3):
                _, err = self.store(r)
                self.assertEqual(err.count(EN_TETE), 1)
        self.assertEqual(len(appels), 1)

    def test_k_partition_en_lecture_seule_store_construit_panne_annoncee(self) -> None:
        # (k) MUTATION : laisser propager l'OSError de l'écrivain → construction
        # morte, rouge.
        if os.name == "nt" or os.geteuid() == 0:
            self.skipTest("chmod inopérant (root ou Windows)")
        r = self.depot("r")
        (r / "runs" / "0123456789abcdef" / "aaaaaaaaaaaaaaaa").mkdir(parents=True)
        self.soeur_sans_marqueur("1111111111111111", "aaaaaaaaaaaaaaaa")
        self.store(r)
        pr = self.partition(r)
        (pr / "racine.json").unlink()
        (pr / "apparentees.json").unlink()
        pr.chmod(0o555)
        self.addCleanup(pr.chmod, 0o755)
        s, err = self.store(r)
        self.assertIsInstance(s, EventStore)
        self.assertIn("marqueur de partition non écrit", err)
        self.assertIn("non enregistré", err)
        self.assertEqual(err.count(EN_TETE), 1, "signal émis depuis le relevé en mémoire")
        self.assertFalse((pr / "racine.json").exists())

    def test_m_arborescence_des_soeurs_intacte(self) -> None:
        # (m) Le relevé et le signal LISENT les sœurs : liste + sha de chaque fichier
        # identiques avant/après deux constructions.
        a = self.depot("a")
        self.store(a)
        pa = self.partition(a)
        r = self.depot("r")
        (r / "runs" / "0123456789abcdef" / "aaaaaaaaaaaaaaaa").mkdir(parents=True)
        s1 = self.soeur_sans_marqueur("1111111111111111", "aaaaaaaaaaaaaaaa")
        avant = (_empreinte_arbre(pa), _empreinte_arbre(s1))
        self.store(r)
        self.store(r)
        self.assertEqual((_empreinte_arbre(pa), _empreinte_arbre(s1)), avant)

    def test_en_tete_par_octets_et_bloc_sans_recapitulatif(self) -> None:
        # E3/E4 : l'en-tête est celui du plan, une ligne par bloc, et un bloc ne
        # nomme JAMAIS une autre sœur (un `grep` sur une sœur acquittée rend 0).
        self.assertEqual(run_export.EN_TETE_APPARENTEE, EN_TETE)
        r = self.depot("r")
        (r / "runs" / "0123456789abcdef" / "aaaaaaaaaaaaaaaa").mkdir(parents=True)
        (r / "runs" / "0123456789abcdef" / "bbbbbbbbbbbbbbbb").mkdir(parents=True)
        s1 = self.soeur_sans_marqueur("1111111111111111", "aaaaaaaaaaaaaaaa")
        s2 = self.soeur_sans_marqueur("2222222222222222", "bbbbbbbbbbbbbbbb")
        _, err = self.store(r)
        self.assertEqual(err.count(EN_TETE), 2)
        pr = self.partition(r)
        (pr / "acquittements").mkdir()
        (pr / "acquittements" / s1.name).touch()
        _, err2 = self.store(r)
        self.assertEqual(err2.count(EN_TETE), 1)
        self.assertNotIn(s1.name, err2)
        self.assertIn(s2.name, err2)

    def test_n_racine_non_imprimable_marqueur_ignore(self) -> None:
        # (n, security MEDIUM) Une sœur au marqueur FORGÉ dont la `racine` porte un
        # retour à la ligne : le marqueur est IGNORÉ (None), donc J1 ne tient pas
        # même avec les `(dev, ino)` de la racine courante, et la ligne injectée
        # n'atteint JAMAIS stderr. La sœur reste signalée par J3 (son `run/copie`),
        # sous « sans marqueur ». MUTATION : retirer le test `isprintable()` de
        # `lire_marqueur_partition` → J1 tient, `INJECTION` sort en ligne propre, rouge.
        r = self.depot("r")
        (r / "runs" / "0123456789abcdef" / "aaaaaaaaaaaaaaaa").mkdir(parents=True)
        forge = f"{self.bac.as_posix()}/ancien\nINJECTION: ligne forgée"
        soeur = self.soeur_sans_marqueur(self.empreinte(forge), "aaaaaaaaaaaaaaaa")
        marqueur = dict(
            self.identite_forgee(forge, r), format=run_export.FORMAT_MARQUEUR,
            ecrit_le="2026-01-01T00:00:00Z", origine="naissance",
        )
        (soeur / "racine.json").write_text(json.dumps(marqueur), encoding="utf-8")
        self.assertIsNone(run_export.lire_marqueur_partition(soeur))
        _, err = self.store(r)
        self.assertEqual(err.count(EN_TETE), 1)
        self.assertIn(soeur.name, err)
        self.assertIn("sans marqueur", err)
        self.assertNotIn("INJECTION", err)
        self.assertNotIn("J1", self.apparentees(self.partition(r))[soeur.name]["jambes"])

    def test_o_signal_repete_apres_retour_X_Y_X(self) -> None:
        # (o, F1 — S-00002240 « signal répété jusqu'à acquittement ou disparition »)
        # X → Y → X : au retour en X, la partition de Y est une sœur APPARUE depuis
        # le relevé de X (fait quand X n'avait aucune sœur) ; le relevé est REJOUÉ
        # et le bloc nomme la partition de Y. MUTATION : relevé figé à la naissance
        # (ne rejouer que si le cache est absent) → 0 bloc au retour, rouge.
        x = self.depot("x")
        self.store(x)
        px = self.partition(x)
        self.assertEqual(self.cache(px), {"soeurs": [], "apparentees": []})
        y = self.bac / "y"
        os.rename(x, y)
        _, err_y = self.store(y)
        py = self.partition(y)
        self.assertEqual(err_y.count(EN_TETE), 1)
        self.assertIn(px.name, err_y)
        os.rename(y, x)
        _, err_x = self.store(x)
        self.assertGreaterEqual(err_x.count(EN_TETE), 1)
        self.assertIn(py.name, err_x)
        self.assertEqual(self.apparentees(px)[py.name]["jambes"], ["J1", "J2"])
        self.assertEqual(self.cache(px)["soeurs"], [py.name])
        # Sans nouvelle sœur, le relevé n'est PAS rejoué (voir (j)) : le cache est
        # stable et le signal se répète.
        cache_apres = (px / "apparentees.json").read_bytes()
        _, err_x2 = self.store(x)
        self.assertIn(py.name, err_x2)
        self.assertEqual((px / "apparentees.json").read_bytes(), cache_apres)

    def test_p_cache_ancien_format_liste_rejoue_le_releve(self) -> None:
        # (p) Un `apparentees.json` au format LISTE (lot précédent, présent sur la
        # partition réelle `d5db…`), ou hors forme, ou illisible, fait REJOUER le
        # relevé et RÉÉCRIT le cache en dict. MUTATION : « pas un dict ⇒ signal
        # impossible, rendre 0 » → aucun bloc, rouge.
        r = self.depot("r")
        (r / "runs" / "0123456789abcdef" / "aaaaaaaaaaaaaaaa").mkdir(parents=True)
        s1 = self.soeur_sans_marqueur("1111111111111111", "aaaaaaaaaaaaaaaa")
        pr = self.partition(r)
        pr.mkdir(parents=True)
        for ancien in (b"[]\n", b'[{"partition": "1111111111111111"}]\n', b"{pas du json", b'{"soeurs": 3}\n'):
            with self.subTest(ancien=ancien):
                (pr / "apparentees.json").write_bytes(ancien)
                _, err = self.store(r)
                self.assertEqual(err.count(EN_TETE), 1, err)
                self.assertIn(s1.name, err)
                self.assertEqual(self.cache(pr)["soeurs"], [s1.name])
                self.assertEqual(self.apparentees(pr)[s1.name]["jambes"], ["J3"])
        self.assertEqual(list(pr.glob("apparentees.json.*")), [], "temporaire abandonné")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
