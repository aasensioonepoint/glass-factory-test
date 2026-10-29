"""T-00001068 — la fusion git de `runs/` (exports « run par auteur »,
`runs/<auteur>/<copie>/<AAAA-MM>.jsonl`), entre deux branches et entre un worktree et
son principal. Plan T-00001068 rév. 0, option A (décision pilote S-01M4N1FHE79ZENZ4HKCYHJK44P).

Témoins W1-W5, sur des dépôts JETABLES (identité git LOCALE, `GIT_CONFIG_GLOBAL=os.devnull`,
`GIT_CONFIG_NOSYSTEM=1`, `CADRE_PROJECT_ROOT` retiré — sinon `depuis` serait ignoré et W2
passerait à vide —, `CADRE_STATE_DIR` sous le bac) :

  * W1 — UNE MÊME copie sur deux branches, ajouts disjoints, le VRAI `.gitattributes` du kit
    copié (forme de T17, `.agents/evals/test_index_machine.py`) : fusion rc 0, lignes
    [socle, courante, fusionnée]. Bras de CONTRÔLE dans le même test : la copie privée SANS
    la ligne `runs/**/*.jsonl merge=union` conflicte (rc ≠ 0) — `merge=union` est PORTEUR
    pour ce cas, et le scénario conflicte bien sans lui.
  * W2 — principal et `git worktree add` RÉEL : `ajouter_a_l_export` depuis chacun rend deux
    chemins de MÊME `<auteur>` (la config git est commune) et de MÊME `<mois>`, qui ne
    diffèrent QUE par `<copie>` — la copie est tirée sous la partition, clé = chemin de la
    racine. W2 prouve ce nommage SOUS ISOLATION (`CADRE_STATE_DIR`) : hors isolation, la
    route de production REFUSE la naissance de la partition du worktree
    (`agentic_v3/db/naissance_partition.py`, `refus_naissance`, T-00001069), et W2 l'asserte
    aussi — il ne prétend pas qu'un worktree hors isolation exporte.
  * W3 — suite de W2 : la copie du principal est COMMITÉE, PUIS une ligne SALE non commitée
    y est ajoutée ; `runs/` commité dans le worktree ; `merge --no-ff` depuis le principal
    rend 0, le diff de la fusion est le SEUL fichier du worktree, et la ligne sale reste
    intacte (copies distinctes : git ne touche jamais le fichier du principal).
  * W4 — la BORNE de union, mesurée : un MÊME ULID ajouté avec des contenus DIVERGENTS sur
    deux branches (même copie) passe en DOUBLE à la fusion ; `reconstruire_depuis_exports`
    rend total=2, applied=1, divergentes=1 (l'ULID nommé dans `divergentes_ulid`), l'ANNONCE
    sur stderr et garde la PREMIÈRE ligne (T-01M4N496YD7BZDA2NHYQ73JND9). W4b-W4d : doublon
    identique muet, chacun des neuf champs de `run_export._CHAMPS_DIVERGENCE`, borne de 20
    ULID nommés annoncée ; W4e : les surfaces qui citent la borne disent ce que le code fait.
  * W5 — la fusion d'un worktree laisse un écart runs/ -> base vivante : une
    sauvegarde précède l'import automatique ; le store local est préservé.

BORNE DE `merge=union`, dite plutôt que découverte (L-00000111) : union ne signale JAMAIS un
conflit. Une même ligne (même ULID) devenue divergente sur deux branches passe en DOUBLE (W4) ;
la reconstruction (`EventStore.reconstruire_depuis_exports`) garde la première dans l'ordre
(ULID, auteur/copie), écarte l'autre, la COMPTE (`divergentes`) et l'ANNONCE, sans la réparer
(W4) — comme la passe de ré-export `re_exporter_frappees` (`test_run_export.py`,
`test_une_ligne_presente_mais_DIVERGENTE_est_comptee_pas_reparee`).
Un principal SALE sur le fichier qu'une branche modifie refuse la fusion, union ou non.
Fusion côté serveur (PR GitHub) : NON mesurée. Mesuré sous macOS, Linux NON MESURÉ.

MUTANTS (joués à la main, un par un, chacun rouge PAR ASSERTION puis retiré — plan § étape 4) :
  * M-sans-union : ligne `runs/**/*.jsonl merge=union` retirée du VRAI `.gitattributes`
    ⇒ W1 rouge (rc ≠ 0) ;
  * M-copie-partagée : `run_export._fichier_copie` remplacé par un chemin UNIQUE pour les deux
    racines ⇒ W2 rouge (chemins égaux) et W3 rouge (rc ≠ 0, le fichier du principal touché) ;
  * M-W4-silence : `EventStore._appliquer_lignes` ne compte plus la divergente
    ⇒ W4, W4c, W4d rouges (compteur nul) ; M-W4-annonce (annonce retirée) ⇒ W4, W4d rouges ;
  * M-W4-seconde : `EventStore._appliquer_lignes` garde la DERNIÈRE ligne d'un ULID ⇒ W4 rouge
    (la ligne gardée est la seconde).
"""
from __future__ import annotations

import contextlib
import datetime
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Dict, List, Tuple
from unittest import mock

from agentic_v3.db import naissance_partition, run_export
from agentic_v3.db.event_store import EventStore
from agentic_v3.tests.test_run_export import _ReconstructionFixture

ROOT = Path(__file__).resolve().parents[4] if Path(__file__).resolve().parents[2].name == "vendor" else Path(__file__).resolve().parents[2]
EVALS = ROOT / ".agents" / "evals"
if str(EVALS) not in sys.path:
    sys.path.insert(0, str(EVALS))
from surface_kit import EST_LE_KIT  # noqa: E402

GIT = shutil.which("git") or "git"
REGLE_UNION = "runs/**/*.jsonl merge=union"
#: W1 : un chemin d'export à la forme réelle, écrit par git seul (aucun appel au module).
EXPORT_W1 = "runs/0123456789abcdef/fedcba9876543210/2026-10.jsonl"
EMAIL = "banc@example.invalid"
#: Le mois de chaque ULID fabriqué par W2/W3 : `<AAAA-MM>` est décodé de l'ULID.
MS_OCTOBRE = int(datetime.datetime(2026, 10, 1, tzinfo=datetime.timezone.utc).timestamp() * 1000)


def _env_banc(state: Path) -> Dict[str, str]:
    """L'environnement du banc : aucune variable `GIT_*` héritée, config git globale et
    système coupées, `CADRE_PROJECT_ROOT` retiré, `CADRE_STATE_DIR` jetable."""
    env = {
        k: v for k, v in os.environ.items()
        if not k.startswith("GIT_") and k != "CADRE_PROJECT_ROOT"
    }
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", LC_ALL="C",
               CADRE_STATE_DIR=str(state))
    return env


class _Bac(unittest.TestCase):
    """Un bac par test, passé par `realpath` (macOS : /var est /private/var)."""

    def setUp(self) -> None:
        self.bac = Path(os.path.realpath(tempfile.mkdtemp(prefix="t1068_")))
        self.addCleanup(shutil.rmtree, str(self.bac), True)
        patch = mock.patch.dict(os.environ, _env_banc(self.bac / "state"), clear=True)
        patch.start()
        self.addCleanup(patch.stop)
        run_export._paths().vider_cache_racine()
        self.addCleanup(run_export._paths().vider_cache_racine)

    def git(self, cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        r = subprocess.run([GIT, "-C", str(cwd), *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60, check=False)
        if check:
            self.assertEqual(0, r.returncode, f"git {args!r} : {r.stdout}{r.stderr}")
        return r

    def depot(self, nom: str, attributs: str) -> Path:
        """Dépôt jetable, identité LOCALE, `.gitattributes` = `attributs`, un commit socle."""
        racine = self.bac / nom
        racine.mkdir()
        self.git(racine, "init", "-q", "-b", "main")
        self.git(racine, "config", "user.email", EMAIL)
        self.git(racine, "config", "user.name", "banc")
        (racine / ".gitattributes").write_bytes(attributs.encode("utf-8"))
        self.git(racine, "add", "--", ".gitattributes")
        self.git(racine, "commit", "-qm", f"socle {nom}")
        return racine


def _ajouter(chemin: Path, valeur: str) -> None:
    with open(chemin, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps({"valeur": valeur}, sort_keys=True) + "\n")


def _valeurs(chemin: Path) -> List[str]:
    return [json.loads(l)["valeur"] for l in chemin.read_text(encoding="utf-8").splitlines()]


class FusionDUneMemeCopieTests(_Bac):
    def _fusion_meme_copie(self, nom: str, attributs: str) -> Tuple[subprocess.CompletedProcess, Path, str]:
        """MÊME copie sur deux branches, ajouts disjoints : rend (fusion, fichier, check-attr)."""
        r = self.depot(nom, attributs)
        fichier = r / EXPORT_W1
        fichier.parent.mkdir(parents=True)
        _ajouter(fichier, "socle")
        self.git(r, "add", "--", EXPORT_W1)
        self.git(r, "commit", "-qm", "export socle")
        self.git(r, "checkout", "-qb", "autre")
        _ajouter(fichier, "fusionnée")
        self.git(r, "commit", "-qam", "autre")
        self.git(r, "checkout", "-q", "main")
        _ajouter(fichier, "courante")
        self.git(r, "commit", "-qam", "courante")
        attr = self.git(r, "check-attr", "merge", "--", EXPORT_W1).stdout.strip()
        fusion = self.git(r, "merge", "-q", "--no-edit", "autre", check=False)
        return fusion, fichier, attr

    def test_W1_une_meme_copie_sur_deux_branches_fusionne_par_union_et_conflicte_sans(self) -> None:
        reel = (ROOT / ".gitattributes").read_text(encoding="utf-8")
        fusion, fichier, attr = self._fusion_meme_copie("w1", reel)
        self.assertEqual(0, fusion.returncode,
                         f"avec le VRAI .gitattributes, la fusion conflicte : {fusion.stdout}{fusion.stderr}")
        self.assertEqual(["socle", "courante", "fusionnée"], _valeurs(fichier))
        self.assertEqual(f"{EXPORT_W1}: merge: union", attr)

        # Bras de CONTRÔLE : la copie privée SANS la règle (muté != original, une ligne retirée).
        sans = "".join(l for l in reel.splitlines(keepends=True) if l.strip() != REGLE_UNION)
        self.assertEqual(1, len(reel.splitlines()) - len(sans.splitlines()),
                         "la règle union de runs/ doit figurer UNE fois au vrai .gitattributes")
        fusion, _, attr = self._fusion_meme_copie("w1-controle", sans)
        self.assertEqual(f"{EXPORT_W1}: merge: unspecified", attr)
        self.assertNotEqual(0, fusion.returncode,
                            "sans la règle, le même scénario doit CONFLICTER : sinon W1 ne prouve rien")


class FusionDUnWorktreeTests(_Bac):
    def _principal_et_worktree(self) -> Tuple[Path, Path]:
        principal = self.depot("principal", (ROOT / ".gitattributes").read_text(encoding="utf-8"))
        worktree = self.bac / "worktree"
        self.git(principal, "worktree", "add", "-q", "-b", "wt/x", str(worktree))
        run_export._paths().vider_cache_racine()
        return principal, worktree

    @staticmethod
    def _ligne(valeur: str) -> Dict[str, str]:
        return {"ulid": run_export.nouvel_ulid(MS_OCTOBRE), "valeur": valeur}

    def test_W2_principal_et_worktree_exportent_sous_deux_copies_meme_auteur_meme_mois(self) -> None:
        self.assertTrue(naissance_partition.isole(os.environ),
                        "W2 se joue SOUS isolation (CADRE_STATE_DIR) : sans elle, rien ne naît")
        principal, worktree = self._principal_et_worktree()

        cp = run_export.ajouter_a_l_export(self._ligne("principal"), depuis=principal)
        cw = run_export.ajouter_a_l_export(self._ligne("worktree"), depuis=worktree)

        rp, rw = cp.relative_to(principal).parts, cw.relative_to(worktree).parts
        self.assertEqual(4, len(rp), cp)
        self.assertEqual(4, len(rw), cw)
        self.assertEqual(("runs", "runs"), (rp[0], rw[0]))
        self.assertEqual(rp[1], rw[1], "<auteur> : la config git est commune au worktree")
        self.assertEqual(run_export.empreinte_auteur(EMAIL), rp[1])
        self.assertEqual(("2026-10.jsonl", "2026-10.jsonl"), (rp[3], rw[3]))
        self.assertNotEqual(rp[2], rw[2], "<copie> PARTAGÉE : les deux racines écrivent le MÊME fichier")
        self.assertNotEqual(run_export.state_project(principal), run_export.state_project(worktree))

        # Hors isolation, la route de PRODUCTION refuse la partition du worktree (T-00001069),
        # pas celle du principal : W2 prouve le nommage, jamais qu'un worktree hors isolation exporte.
        refus = naissance_partition.refus_naissance(worktree, environ={}, zones=[])
        self.assertIsNotNone(refus)
        self.assertIn("worktree LIÉ", refus)
        self.assertIsNone(naissance_partition.refus_naissance(principal, environ={}, zones=[]))

    def test_W3_merge_no_ff_du_worktree_n_apporte_que_sa_copie_et_garde_la_ligne_sale(self) -> None:
        principal, worktree = self._principal_et_worktree()

        cp = run_export.ajouter_a_l_export(self._ligne("commitée"), depuis=principal)
        rel_p = cp.relative_to(principal).as_posix()
        self.git(principal, "add", "--", rel_p)
        self.git(principal, "commit", "-qm", "principal : runs/")
        # PUIS une ligne SALE, non commitée, sur la copie COMMITÉE du principal (réserve C3).
        self.assertEqual(cp, run_export.ajouter_a_l_export(self._ligne("sale"), depuis=principal))
        sale = f" M {rel_p}"
        self.assertEqual(sale, self.git(principal, "status", "--porcelain", "--", "runs").stdout.rstrip("\n"))

        cw = run_export.ajouter_a_l_export(self._ligne("du worktree"), depuis=worktree)
        rel_w = cw.relative_to(worktree).as_posix()
        self.git(worktree, "add", "--", rel_w)
        self.git(worktree, "commit", "-qm", "worktree : runs/")

        fusion = self.git(principal, "merge", "--no-ff", "--no-edit", "-m", "merge: wt/x", "wt/x",
                          check=False)

        self.assertEqual(0, fusion.returncode, f"fusion refusée : {fusion.stdout}{fusion.stderr}")
        diff = self.git(principal, "diff", "--no-renames", "--name-only", "HEAD^1", "HEAD").stdout
        self.assertEqual([rel_w], diff.splitlines())
        self.assertEqual(["commitée", "sale"], _valeurs(cp), "la ligne sale du principal n'est pas intacte")
        self.assertEqual(sale, self.git(principal, "status", "--porcelain", "--", "runs").stdout.rstrip("\n"))
        self.assertEqual(["du worktree"], _valeurs(principal / rel_w))

    def test_W5_la_fusion_d_un_worktree_laisse_un_ecart_ANNONCE_et_le_geste_encadre_le_ferme(self) -> None:
        """Un merge --no-ff suivi d'une réouverture sauvegarde puis importe l'écart."""
        from agentic_v3.db import event_store, event_store_annonces as annonces

        principal, worktree = self._principal_et_worktree()
        with mock.patch.object(annonces, "_ECARTS_RUNS_ANNONCES", set()):
            store = EventStore(project_root=principal)
            store.append_event("T-PRINC", "run", "TASK_CREATED", {"req_id": "R"}, operation_id="op-princ")
            base = store.db_path
            cw = run_export.ajouter_a_l_export(
                _evenement(run_export.nouvel_ulid(MS_OCTOBRE), "T-WORKTREE"), depuis=worktree)
            rel_w = cw.relative_to(worktree).as_posix()
            self.git(worktree, "add", "--", rel_w)
            self.git(worktree, "commit", "-qm", "worktree : runs/")
            fusion = self.git(principal, "merge", "--no-ff", "--no-edit", "-m", "merge: wt/x", "wt/x", check=False)
            self.assertEqual(0, fusion.returncode, f"fusion refusee : {fusion.stdout}{fusion.stderr}")

            def ouvrir() -> str:
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    EventStore(project_root=principal)
                return err.getvalue()

            def compter() -> int:
                import sqlite3
                conn = sqlite3.connect(str(base))
                try:
                    return conn.execute("SELECT COUNT(*) FROM events_ledger").fetchone()[0]
                finally:
                    conn.close()

            self.assertEqual(1, compter())
            texte = ouvrir()
            self.assertIn("synchro V3 appliquee", texte)
            self.assertIn("ecart=1 applied=1", texte)
            copies = list((base.parent / "v3-auto-sync" / "backups").glob("*.db"))
            self.assertEqual(len(copies), 1)
            self.assertEqual(2, compter(), "la fusion est importee sur la base vivante")
            import sqlite3
            copie = sqlite3.connect(str(copies[0]))
            try:
                self.assertEqual(1, copie.execute("SELECT COUNT(*) FROM events_ledger").fetchone()[0])
            finally:
                copie.close()
            annonces._ECARTS_RUNS_ANNONCES.clear()
            self.assertNotIn("synchro V3", ouvrir(), "l'ecart est ferme")
            self.assertEqual(len(list((base.parent / "v3-auto-sync" / "backups").glob("*.db"))), 1)


class SynchronisationAutomatiqueTests(_ReconstructionFixture):
    """Cas actifs par défaut, isolés du kit et de son store réel."""

    def _ecart(self, n: int = 1, *, task_id: str = "T-IMPORT") -> tuple[EventStore, list[str]]:
        store, _ = self._ouvrir_defaut()
        store.append_event("T-LOCAL", "run", "TASK_CREATED", {"req_id": "LOCAL"},
                           operation_id="op-local")
        ulids = self._ulids(n)
        self._ecrire_runs([self._ligne(u, task_id=task_id) for u in ulids])
        return store, ulids

    def _copies(self) -> list[Path]:
        return list((self._base_defaut().parent / "v3-auto-sync" / "backups").glob("*.db"))

    def test_auto_sync_inhibe_toute_partition_kit(self) -> None:
        self._ecart()
        marker = self.racine / ".agents" / "IS_THE_KIT"
        marker.parent.mkdir(exist_ok=True)
        marker.touch()
        _, err = self._ouvrir_defaut()
        self.assertIn("synchro V3 inhibee", err)
        self.assertIn("autorise-" + self._base_defaut().parent.parent.name, err)
        self.assertIn("apportes par :", err)
        self.assertEqual(1, self._compter(self._base_defaut()))
        self.assertEqual([], self._copies())

    def test_auto_sync_inhibee_partition_reservee_nomme_le_geste(self) -> None:
        from agentic_v3.db import event_store_annonces
        self._ecart()
        marker = self.racine / ".agents" / "IS_THE_KIT"
        marker.parent.mkdir(exist_ok=True)
        marker.touch()
        partition = self._base_defaut().parent.parent.name
        with mock.patch.object(event_store_annonces, "_PARTITION_GESTE_S2370", partition):
            _, err = self._ouvrir_defaut()
        self.assertIn("S-00002370", err)
        self.assertIn("autorise-" + partition, err)
        self.assertIn("apportes par :", err)

    def test_auto_sync_autorisee_kit(self) -> None:
        self._ecart()
        marker = self.racine / ".agents" / "IS_THE_KIT"
        marker.parent.mkdir(exist_ok=True)
        marker.touch()
        partition = self._base_defaut().parent.parent
        autorisation = partition / "run" / "v3-auto-sync" / f"autorise-{partition.name}"
        autorisation.parent.mkdir()
        autorisation.touch()
        _, err = self._ouvrir_defaut()
        self.assertIn("synchro V3 appliquee", err)
        self.assertEqual(2, self._compter(self._base_defaut()))

    @unittest.skipUnless(os.name == "posix", "liens POSIX")
    def test_auto_sync_refuse_marqueur_symbolique(self) -> None:
        self._ecart()
        kit = self.racine / ".agents" / "IS_THE_KIT"
        kit.parent.mkdir(exist_ok=True)
        kit.touch()
        partition = self._base_defaut().parent.parent
        marqueur = partition / "run" / "v3-auto-sync" / f"autorise-{partition.name}"
        marqueur.parent.mkdir()
        cible = self.racine / "autorisation-victime"
        cible.touch()
        marqueur.symlink_to(cible)
        _, err = self._ouvrir_defaut()
        self.assertIn("synchro V3 inhibee", err)
        self.assertEqual([], self._copies())

    def test_auto_sync_inhibition_annoncee_une_fois(self) -> None:
        self._ecart()
        kit = self.racine / ".agents" / "IS_THE_KIT"
        kit.parent.mkdir(exist_ok=True)
        kit.touch()
        _, premier = self._ouvrir_defaut()
        _, second = self._ouvrir_defaut()
        self.assertIn("synchro V3 inhibee", premier)
        self.assertNotIn("synchro V3 inhibee", second)

    def test_auto_sync_non_sonde_65_mib_et_ecriture_permises(self) -> None:
        self._ecart()
        from agentic_v3.db import event_store_annonces
        for kit in (False, True):
            with self.subTest(kit=kit):
                event_store_annonces._ECARTS_RUNS_ANNONCES.discard(str(self._base_defaut()))
                if kit:
                    marqueur = self.racine / ".agents" / "IS_THE_KIT"
                    marqueur.parent.mkdir(exist_ok=True)
                    marqueur.touch()
                with mock.patch.object(self._es().EventStore, "_taille_runs",
                                       return_value=65 * 1024 * 1024):
                    store, err = self._ouvrir_defaut()
                self.assertIn("NON sonde", err)
                self.assertTrue(store._auto_sync_result["non_sonde"])
                store.append_event(f"T-GROS-{kit}", "run", "TASK_CREATED", {"req_id": "R"})

    def test_auto_sync_annonce_divergence_sans_import(self) -> None:
        store, _ = self._ouvrir_defaut()
        ulid = run_export.nouvel_ulid(MS_OCTOBRE)
        store.append_event("T-A", "run", "TASK_CREATED", {"req_id": "R"}, ulid=ulid)
        self._ecrire_runs([self._ligne(ulid, task_id="T-B")])
        _, err = self._ouvrir_defaut()
        self.assertIn("DIVERGENT", err)
        self.assertIn(ulid, err)
        self.assertEqual(1, self._compter(self._base_defaut()))

    def test_auto_sync_divergence_annoncee_une_fois_par_ensemble(self) -> None:
        from agentic_v3.db import event_store_annonces
        with mock.patch.object(event_store_annonces, "_ECARTS_RUNS_ANNONCES", set()):
            store, _ = self._ouvrir_defaut()
            premier, second = self._ulids(2)
            store.append_event("T-LOCAL-1", "run", "TASK_CREATED", {"req_id": "R"}, ulid=premier)
            store.append_event("T-LOCAL-2", "run", "TASK_CREATED", {"req_id": "R"}, ulid=second)
            self._ecrire_runs([self._ligne(premier, task_id="T-AUTRE-1")])
            premier_err = self._ouvrir_defaut()[1]
            second_err = self._ouvrir_defaut()[1]
            self._ecrire_runs([self._ligne(second, task_id="T-AUTRE-2")])
            troisieme_err = self._ouvrir_defaut()[1]
        self.assertEqual(1, premier_err.count("DIVERGENT(S)"))
        self.assertNotIn("DIVERGENT", second_err)
        self.assertIn(second, troisieme_err)
        self.assertEqual(1, troisieme_err.count("DIVERGENT(S)"))

    def test_auto_sync_rotations_et_modes_prives(self) -> None:
        from agentic_v3.db import event_store_sync
        self._ecart()
        base = self._base_defaut()
        partition = base.parent.parent
        _, premiere_annonce = self._ouvrir_defaut()
        copies = [self._copies()[0]]
        self.assertIn(str(copies[0]), premiere_annonce)
        remplacement = base.with_name("remplacement-vivant.db")
        neuf = self._es().EventStore(remplacement, project_root=self.racine)
        neuf.append_event("T-NEUF", "run", "TASK_CREATED", {"req_id": "NEUF"})
        os.replace(remplacement, base)
        _, seconde_annonce = self._ouvrir_defaut()
        nouvelle_copie = next(p for p in self._copies() if p != copies[0])
        self.assertIn(str(nouvelle_copie), seconde_annonce)
        copies.append(nouvelle_copie)
        remplacements = []
        from agentic_v3.db.schema import create_tables
        for n in range(2):
            remplacement = base.with_name(f"remplacement-{n}.db")
            create_tables(remplacement, racine=self.racine)
            remplacements.append(remplacement)
        troisieme = copies[0].parent / f"v3-999999999-20261001T000000000000Z-{'a' * 32}.db"
        shutil.copyfile(copies[0], troisieme)
        copies.append(troisieme)
        self.assertEqual(3, len(self._copies()), "trois copies anciennes avant la rotation")
        for identite, remplacement in enumerate(remplacements, 1):
            os.replace(remplacement, base)
            copie = event_store_sync.sauvegarder(
                partition, base, lambda c: c.execute("PRAGMA data_version").fetchone()[0], identite)
            copies.append(copie)
            self.assertEqual(identite, int(copie.name.split("-")[1]))
            self.assertTrue(copie.exists(), "la rotation a efface la copie neuve")
        self.assertEqual(3, len(self._copies()))
        self.assertNotEqual(copies[0], copies[1])
        self.assertEqual({0o700}, {p.stat().st_mode & 0o777 for p in
                         (partition / "run" / "v3-auto-sync", partition / "run" / "v3-auto-sync" / "backups")})

    def test_auto_sync_identite_survit_a_un_inode_reutilise(self) -> None:
        import sqlite3
        from agentic_v3.db import event_store
        self._ecart()
        base = self._base_defaut()
        vrai_stat = Path.stat

        def inode_constant(chemin, *args, **kwargs):
            stat = vrai_stat(chemin, *args, **kwargs)
            if chemin == base:
                valeurs = list(stat)
                valeurs[1] = 77
                return os.stat_result(valeurs)
            return stat

        with mock.patch.object(Path, "stat", inode_constant), mock.patch.object(
            event_store.secrets, "randbelow", side_effect=[100, 101]
        ):
            self._ouvrir_defaut()
            ancienne = self._copies()[0]
            remplacement = base.with_name("remplacement-identite.db")
            neuf = self._es().EventStore(remplacement, project_root=self.racine)
            neuf.append_event("T-NEUF", "run", "TASK_CREATED", {"req_id": "NEUF"})
            os.replace(remplacement, base)
            self._ecrire_runs([self._ligne(self._ulids(1)[0], task_id="T-NOUVEL-ECART")])
            self._ouvrir_defaut()
        self.assertEqual(2, len(self._copies()))
        self.assertTrue(ancienne.exists())
        self.assertEqual({101, 102}, {int(p.name.split("-")[1]) for p in self._copies()})
        with sqlite3.connect(base) as conn:
            self.assertEqual(102, conn.execute("PRAGMA application_id").fetchone()[0])

    def test_auto_sync_annonce_lignes_ecartees(self) -> None:
        self._ecart()
        deux = self._ulids(2)
        invalide = self._ligne(self._ulids(1)[0])
        invalide["task_id"] = 42
        self._ecrire_runs([self._ligne(deux[0]), self._ligne(deux[1]),
                           self._ligne("ULID-INVALIDE"), invalide])
        _, err = self._ouvrir_defaut()
        self.assertIn("ulid_hors_forme=1", err)
        self.assertIn("malformes=1", err)
        for nom in ("echecs", "fichiers_illisibles", "fichiers_trop_gros",
                    "lignes_illisibles", "pont_ecartes"):
            self.assertIn(nom + "=0", err)

    def test_auto_sync_annonce_ecarts_sans_ligne_applicable(self) -> None:
        store, _ = self._ouvrir_defaut()
        store.append_event("T-LOCAL", "run", "TASK_CREATED", {"req_id": "LOCAL"})
        ligne = self._ligne(self._ulids(1)[0])
        ligne["task_id"] = 42
        fichier = self._ecrire_runs([ligne])
        with fichier.open("a", encoding="utf-8") as sortie:
            sortie.write("{not-json}\n")
        _, err = self._ouvrir_defaut()
        self.assertIn("synchro V3 sondee", err)
        self.assertIn("malformes=1", err)
        self.assertIn("lignes_illisibles=1", err)

    def test_auto_sync_champs_implicites_ne_divergent_pas_aux_trois_ouvertures(self) -> None:
        self._ecart()
        ligne = self._ligne(self._ulids(1)[0], task_id="T-IMPLICITE")
        ligne.pop("attempt")
        ligne.pop("created_at")
        self._ecrire_runs([ligne])
        sorties = [self._ouvrir_defaut()[1] for _ in range(3)]
        self.assertIn("synchro V3 appliquee", sorties[0])
        self.assertTrue(all("DIVERGENT" not in sortie for sortie in sorties), sorties)

    def test_auto_sync_refuse_copie_corrompue_avant_publication(self) -> None:
        from agentic_v3.db import event_store_sync
        self._ecart()
        vrai_write = os.write

        def corrompre(fd, bloc):
            octets = bytes(bloc)
            return vrai_write(fd, b"BAD" + octets[3:])

        with mock.patch.object(event_store_sync.os, "write", side_effect=corrompre):
            _, err = self._ouvrir_defaut()
        self.assertIn("synchro V3 AVORTEE", err)
        self.assertEqual([], self._copies())
        self.assertIn('getattr(os, "O_BINARY", 0)',
                      __import__("inspect").getsource(event_store_sync.sauvegarder))

    def test_auto_sync_ignore_nom_etranger_et_nettoie_tmp_age(self) -> None:
        import time
        self._ecart()
        backups = self._base_defaut().parent / "v3-auto-sync" / "backups"
        backups.mkdir(parents=True)
        (backups / "etranger.db").write_bytes(b"etranger")
        orphelin = backups / ".v3-ancien.db.tmp"
        orphelin.write_bytes(b"ancien")
        os.utime(orphelin, (time.time() - 3700, time.time() - 3700))
        _, err = self._ouvrir_defaut()
        self.assertIn("synchro V3 appliquee", err)
        self.assertFalse(orphelin.exists())
        self.assertTrue((backups / "etranger.db").exists())

    def test_auto_sync_courses_creation_et_rotation(self) -> None:
        from agentic_v3.db import event_store_sync
        self._ecart()
        base = self._base_defaut()
        partition = base.parent.parent
        vrai_mkdir = Path.mkdir

        def creer_en_parallele(chemin, *args, **kwargs):
            if chemin.name == "v3-auto-sync" and not chemin.exists():
                vrai_mkdir(chemin, mode=0o700)
            return vrai_mkdir(chemin, *args, **kwargs)

        with mock.patch.object(Path, "mkdir", creer_en_parallele):
            _, err = self._ouvrir_defaut()
        self.assertIn("synchro V3 appliquee", err)

        backups = base.parent / "v3-auto-sync" / "backups"
        for n in range(3):
            (backups / f"v3-{n + 1}-20261001T00000000000{n}Z-{'a' * 32}.db").write_bytes(b"ancienne")
        vrai_unlink = Path.unlink
        courses = []

        def effacer_en_parallele(chemin, *args, **kwargs):
            if chemin.name.startswith("v3-1-") and not courses:
                vrai_unlink(chemin)
                courses.append(chemin)
            return vrai_unlink(chemin, *args, **kwargs)

        with mock.patch.object(Path, "unlink", effacer_en_parallele):
            copie = event_store_sync.sauvegarder(
                partition, base, lambda c: c.execute("PRAGMA data_version").fetchone()[0], 1234)
        self.assertTrue(courses)
        self.assertTrue(copie.exists())

    def test_auto_sync_un_seul_parcours_pour_la_comparaison(self) -> None:
        from agentic_v3.db import event_store_annonces
        self._ecart(3)
        vrai = event_store_annonces.AnnoncesRunsMixin._connexion_lecture
        requetes = []

        def tracer(store):
            conn = vrai(store)
            conn.set_trace_callback(requetes.append)
            return conn

        with mock.patch.object(event_store_annonces.AnnoncesRunsMixin, "_connexion_lecture", tracer):
            self._ouvrir_defaut()
        comparaison = [q for q in requetes if q.startswith("SELECT ulid, task_id")]
        self.assertEqual(1, len(comparaison), requetes)

    def test_auto_sync_sauvegarde_avant_premier_import(self) -> None:
        self._ecart()
        es = self._es()
        original = es.EventStore._appliquer_lignes
        ordre = []

        def inspecter(store, *args):
            copies = self._copies()
            self.assertEqual(len(copies), 1)
            self.assertEqual(1, self._compter(copies[0]))
            ordre.append("sauvegarde")
            return original(store, *args)

        with mock.patch.object(es.EventStore, "_appliquer_lignes", inspecter):
            _, err = self._ouvrir_defaut()
        self.assertEqual(ordre, ["sauvegarde"])
        self.assertIn("synchro V3 appliquee", err)

    def test_auto_sync_refuse_sans_sauvegarde(self) -> None:
        self._ecart()
        from agentic_v3.db import event_store_sync
        with mock.patch.object(event_store_sync, "sauvegarder", side_effect=OSError("copie refusee")):
            store, err = self._ouvrir_defaut()
        self.assertIn("synchro V3 AVORTEE", err)
        self.assertIn("contournement : AGENTS_V3_AUTO_SYNC=0", err)
        self.assertEqual(1, self._compter(self._base_defaut()))
        with self.assertRaises(self._es().ReconstructionAvorteeError):
            store.append_event("T-REFUS", "run", "TASK_CREATED", {"req_id": "R"})

    @unittest.skipUnless(os.name == "posix", "liens POSIX")
    def test_auto_sync_refuse_lien_sauvegarde(self) -> None:
        self._ecart()
        victime = self.racine / "victime"
        victime.mkdir()
        dossier = self._base_defaut().parent / "v3-auto-sync"
        dossier.symlink_to(victime, target_is_directory=True)
        _, err = self._ouvrir_defaut()
        self.assertIn("synchro V3 AVORTEE", err)
        self.assertEqual(list(victime.iterdir()), [])
        self.assertEqual(1, self._compter(self._base_defaut()))

    def test_auto_sync_avorte_si_pont_non_rebati(self) -> None:
        self._ecart()
        import sqlite3
        conn = sqlite3.connect(str(self._base_defaut()))
        conn.execute("INSERT INTO events_ledger (task_id,agent_role,event_type,payload_json,"
                     "operation_id,event_kind,attempt) VALUES (?,?,?,?,?,?,0)",
                     ("T-ANCIEN", "BoardBridge", "BOARD_TASK_OBSERVED", "{}",
                      "op-ancien", "BOARD_TASK_OBSERVED"))
        conn.commit()
        conn.close()
        store, err = self._ouvrir_defaut()
        self.assertIn("synchro V3 AVORTEE", err)
        self.assertIn("ordre de rejeu indefinissable", err)
        self.assertFalse(store._reconstruction_bloquee)
        store.append_event("T-APRES-ECHEC", "run", "TASK_CREATED", {"req_id": "R"})
        self.assertEqual(3, self._compter(self._base_defaut()))

    def test_auto_sync_une_seule_sauvegarde(self) -> None:
        self._ecart()
        self._ouvrir_defaut()
        copie = self._copies()[0]
        self._ecrire_runs([self._ligne(self._ulids(1)[0], task_id="T-AUTRE")])
        self._ouvrir_defaut()
        self.assertEqual(self._copies(), [copie])
        self.assertEqual(1, self._compter(copie))
        self.assertEqual(3, self._compter(self._base_defaut()))

    def test_auto_sync_sonde_sans_verrou(self) -> None:
        self._ecart()
        self._ouvrir_defaut()
        es = self._es()
        vrai = es.get_db_connection
        appels = []

        def sans_seconde_connexion(*args, **kwargs):
            appels.append(1)
            if len(appels) > 1:
                raise AssertionError("connexion ecriture apres la sonde")
            return vrai(*args, **kwargs)

        with mock.patch.object(es, "get_db_connection", sans_seconde_connexion):
            store, err = self._ouvrir_defaut()
        self.assertEqual(len(appels), 1)
        self.assertFalse(store._auto_sync_result["avortee"])
        self.assertNotIn("AVORTEE", err)
        self.assertNotIn("synchro V3", err)

    def test_auto_sync_recompte_sous_verrou(self) -> None:
        self._ecart()
        es = self._es()
        original = es.EventStore._manquants_nommes
        appels = []

        def mesure(store, cursor, lignes):
            appels.append(1)
            return original(store, cursor, lignes) if len(appels) == 1 else {}

        with mock.patch.object(es.EventStore, "_manquants_nommes", mesure):
            _, err = self._ouvrir_defaut()
        self.assertEqual(len(appels), 2)
        self.assertEqual(1, self._compter(self._base_defaut()))
        self.assertNotIn("synchro V3 appliquee", err)
        self.assertEqual(len(self._copies()), 1)

    def test_intents_board_entrelaces_ulid(self) -> None:
        store, _ = self._ouvrir_defaut()
        store.append_event("T-LOCAL", "run", "TASK_CREATED", {"req_id": "LOCAL"},
                           operation_id="op-local")
        import sqlite3
        conn = sqlite3.connect(str(self._base_defaut()))
        conn.execute("INSERT INTO task_board_mapping (board_task_id,v3_task_id,create_operation_id) "
                     "VALUES ('T-MIX','V3:mix','op-link')")
        conn.commit()
        conn.close()
        remplacement = self._intent("op-replace", before=self._snap("T-MIX", "running"),
                                    after=self._snap("T-MIX", "pending"),
                                    kind="BOARD_RUNNING_REPLACED")
        blocage = self._intent("op-block", before=self._snap("T-MIX", "pending"),
                               after=self._snap("T-MIX", "blocked"))
        ulids = [run_export.nouvel_ulid(MS_OCTOBRE + i * 1_000) for i in range(1, 6)]
        self._ecrire_runs([
            self._ligne(ulids[0], task_id="V3:mix"),
            self._ligne(ulids[1], task_id="V3:mix", event_type="CODE_GENERATED"),
            self._ligne_intent(ulids[2], remplacement),
            self._ligne(ulids[3], task_id="V3:mix", event_type="TEST_RUN",
                        payload={"passed": True}),
            self._ligne_intent(ulids[4], blocage),
        ])
        _, err = self._ouvrir_defaut()
        self.assertIn("synchro V3 appliquee", err)
        self.assertEqual(self._scalaire(self._base_defaut(),
                         "SELECT status FROM task_projections WHERE task_id='V3:mix'"), "BLOCKED")
        self.assertEqual(self._scalaire(self._base_defaut(),
                         "SELECT is_blocked FROM task_projections WHERE task_id='V3:mix'"), 1)
        effet = self._scalaire(self._base_defaut(),
                              "SELECT effect_json FROM board_sync_inbox WHERE operation_id='op-replace'")
        self.assertTrue(json.loads(effet)["applied"])

    def test_lien_non_touche_garde_son_statut(self) -> None:
        store, _ = self._ecart()
        base = self._base_defaut()
        import sqlite3
        conn = sqlite3.connect(str(base))
        conn.execute("INSERT INTO task_board_mapping (board_task_id,v3_task_id,create_operation_id) "
                     "VALUES ('T-STABLE','V3:stable','op-link')")
        conn.commit()
        conn.close()
        store.consume_board_intent(self._intent(
            "op-delta", before=self._snap("T-STABLE", "pending"),
            after=self._snap("T-STABLE", "running")))
        store.append_event("V3:stable", "run", "CRITIC_VERDICT", {"passed": True},
                           operation_id="op-stable")
        self._ouvrir_defaut()
        self.assertEqual(self._scalaire(base,
                         "SELECT status FROM task_projections WHERE task_id='V3:stable'"), "IN_TEST")
        self.assertEqual(self._scalaire(base,
                         "SELECT COUNT(*) FROM task_board_mapping WHERE v3_task_id='V3:stable'"), 1)

    def test_reprojection_ulid_u1_u3_u5(self) -> None:
        store, _ = self._ecart()
        u1 = run_export.nouvel_ulid(MS_OCTOBRE + 1_000)
        u3 = run_export.nouvel_ulid(MS_OCTOBRE + 3_000)
        u5 = run_export.nouvel_ulid(MS_OCTOBRE + 5_000)
        store.append_event("T-ORDER", "run", "TEST_RUN", {"passed": False},
                           operation_id="op-middle", ulid=u3)
        self._ecrire_runs([self._ligne(u1, task_id="T-ORDER", event_type="TASK_CREATED"),
                           self._ligne(u5, task_id="T-ORDER", event_type="TEST_RUN",
                                       payload={"passed": True})])
        self._ouvrir_defaut()
        self.assertEqual(self._scalaire(self._base_defaut(),
                         "SELECT status FROM task_projections WHERE task_id='T-ORDER'"), "COMPLETED")
        self.assertEqual(self._scalaire(self._base_defaut(),
                         "SELECT COUNT(*) FROM events_ledger WHERE task_id='T-ORDER'"), 3)
        autre = "T-ORDER-FAUX"
        store.append_event(autre, "run", "TEST_RUN", {"passed": True},
                           operation_id="op-middle-true",
                           ulid=run_export.nouvel_ulid(MS_OCTOBRE + 4_000))
        self._ecrire_runs([
            self._ligne(run_export.nouvel_ulid(MS_OCTOBRE + 2_000), task_id=autre),
            self._ligne(run_export.nouvel_ulid(MS_OCTOBRE + 6_000), task_id=autre,
                        event_type="TEST_RUN", payload={"passed": False}),
        ])
        self._ouvrir_defaut()
        self.assertEqual(self._scalaire(self._base_defaut(),
                         "SELECT status FROM task_projections WHERE task_id=?", (autre,)), "IN_DEV")

    def test_reprojection_ordre_ulid_local_u5_import_u1_u3(self) -> None:
        store, _ = self._ouvrir_defaut()
        u1, u3, u5 = (run_export.nouvel_ulid(MS_OCTOBRE + k * 1_000) for k in (1, 3, 5))
        store.append_event("T-ORD", "run", "TEST_RUN", {"passed": False},
                           operation_id="op-local", ulid=u5)
        self._ecrire_runs([self._ligne(u1, task_id="T-ORD"),
                           self._ligne(u3, task_id="T-ORD", event_type="TEST_RUN",
                                       payload={"passed": True})])
        self._ouvrir_defaut()
        self.assertEqual("IN_DEV", self._scalaire(self._base_defaut(),
                         "SELECT status FROM task_projections WHERE task_id='T-ORD'"))

    def test_reprojection_retry_count_ne_double_pas(self) -> None:
        store, _ = self._ouvrir_defaut()
        u1, u2, u4 = (run_export.nouvel_ulid(MS_OCTOBRE + k * 1_000) for k in (1, 2, 4))
        store.append_event("T-RC", "run", "TASK_CREATED", {"req_id": "R"},
                           operation_id="op-created", ulid=u1)
        store.append_event("T-RC", "run", "CRITIC_VERDICT", {"passed": False},
                           operation_id="op-verdict", ulid=u2)
        self._ecrire_runs([self._ligne(u4, task_id="T-RC", event_type="CODE_GENERATED",
                                      payload={"code_diff": ""})])
        self._ouvrir_defaut()
        self.assertEqual(1, self._scalaire(self._base_defaut(),
                         "SELECT retry_count FROM task_projections WHERE task_id='T-RC'"))

    def test_auto_sync_plus_de_999_ulid(self) -> None:
        store, _ = self._ouvrir_defaut()
        store.append_event("T-LOCAL", "run", "TASK_CREATED", {"req_id": "R"})
        self._ecrire_runs([self._ligne(run_export.nouvel_ulid(MS_OCTOBRE + i * 1_000),
                                      task_id=f"T-{i}") for i in range(1_001)])
        import sqlite3
        es = self._es()
        vrai = es.get_db_connection

        def limiter(*args, **kwargs):
            conn = vrai(*args, **kwargs)
            conn.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 999)
            return conn

        with mock.patch.object(es, "get_db_connection", limiter):
            _, err = self._ouvrir_defaut()
        self.assertIn("synchro V3 appliquee", err)
        self.assertEqual(1_002, self._compter(self._base_defaut()))


def _evenement(ulid: str, task_id: str) -> Dict[str, object]:
    """Une ligne d'export complète : les quatre champs que la reconstruction consomme."""
    return {"ulid": ulid, "task_id": task_id, "agent_role": "run", "event_type": "TASK_CREATED",
            "payload_json": "{}", "operation_id": f"op-{task_id}", "event_kind": "TASK_CREATED",
            "attempt": 0, "predecesseur_ulid": None, "created_at": "2026-10-01 00:00:00"}


class ReconstructionDUneLigneDivergenteTests(_Bac):
    def _racine_nue(self, nom: str) -> Path:
        """Une racine sans git (`.agents/` seul) : `reconstruire_depuis_exports(racine=…)` lit `runs/` dessous."""
        r = self.bac / nom
        (r / ".agents").mkdir(parents=True)
        return r

    @staticmethod
    def _ecrire_export(racine: Path, copie: str, lignes: List[Dict[str, object]]) -> None:
        fichier = racine / "runs" / "0123456789abcdef" / copie / "2026-10.jsonl"
        fichier.parent.mkdir(parents=True, exist_ok=True)
        with open(fichier, "a", encoding="utf-8", newline="\n") as fh:
            for ligne in lignes:
                fh.write(json.dumps(ligne, sort_keys=True) + "\n")

    def _reconstruire(self, racine: Path, nom: str):
        base = self.bac / nom / "v3.db"
        base.parent.mkdir()
        store = EventStore(base, project_root=racine)
        annonce = io.StringIO()
        with contextlib.redirect_stderr(annonce):
            res = store.reconstruire_depuis_exports(racine)
        return res, annonce.getvalue()

    def test_W4b_un_doublon_IDENTIQUE_n_est_pas_une_divergente(self) -> None:
        # M-W4-tout-doublon.
        r = self._racine_nue("w4b")
        ulid = run_export.nouvel_ulid(MS_OCTOBRE)
        for copie in ("aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb"):
            self._ecrire_export(r, copie, [_evenement(ulid, "T-IDENTIQUE")])
        res, texte = self._reconstruire(r, "base-w4b")
        self.assertEqual((2, 1, 0), (res["total"], res["applied"], res["divergentes"]), res)
        self.assertEqual([], res["divergentes_ulid"])
        self.assertNotIn("DIVERGENT", texte)

    def test_W4c_chacun_des_neuf_champs_de_comparaison_fait_une_divergente(self) -> None:
        # M-W4-champ-partiel.
        autre = {"task_id": "T-AUTRE", "agent_role": "autre", "event_type": "TASK_UPDATED",
                 "payload_json": '{"x": 1}', "created_at": "2026-10-02 00:00:00", "operation_id": "op-autre",
                 "event_kind": "TASK_UPDATED", "attempt": 1, "predecesseur_ulid": "01ARZ3NDEKTSV4RRFFQ69G5FAV"}
        self.assertEqual(set(autre), set(run_export._CHAMPS_DIVERGENCE), "les neuf champs, ni plus ni moins")
        for champ in run_export._CHAMPS_DIVERGENCE:
            with self.subTest(champ=champ):
                r = self._racine_nue(f"w4c-{champ}")
                ulid = run_export.nouvel_ulid(MS_OCTOBRE)
                a = _evenement(ulid, "T-A")
                b = dict(a)
                b[champ] = autre[champ]
                self._ecrire_export(r, "aaaaaaaaaaaaaaaa", [a])
                self._ecrire_export(r, "bbbbbbbbbbbbbbbb", [b])
                res, _ = self._reconstruire(r, f"base-w4c-{champ}")
                self.assertEqual(1, res["divergentes"], f"{champ} : {res}")
                self.assertEqual([ulid], res["divergentes_ulid"])

    def test_W4d_la_borne_est_annoncee_et_un_ULID_est_compte_une_fois(self) -> None:
        # M-W4-par-ligne ; M-W4-borne-muette ; M-W4-borne-5 (20, la borne de `re_exporter_frappees`).
        r = self._racine_nue("w4d")
        ulids = sorted(run_export.nouvel_ulid(MS_OCTOBRE) for _ in range(22))
        for i, ulid in enumerate(ulids):
            self._ecrire_export(r, "aaaaaaaaaaaaaaaa", [_evenement(ulid, f"T-{i}-A")])
            self._ecrire_export(r, "bbbbbbbbbbbbbbbb", [_evenement(ulid, f"T-{i}-B")])
        self._ecrire_export(r, "cccccccccccccccc", [_evenement(ulids[0], "T-0-C")])  # TRIPLE : compte UNE fois
        res, texte = self._reconstruire(r, "base-w4d")
        self.assertEqual(22, res["divergentes"], res)
        self.assertEqual(ulids[:20], res["divergentes_ulid"], "la liste nommee est BORNEE (20)")
        self.assertIn("22 ULID DIVERGENT(S)", texte)
        self.assertIn("et 2 autres", texte, "une borne appliquee est ANNONCEE")
        self.assertNotIn(ulids[21], texte)

    def test_W4e_les_surfaces_qui_citent_la_borne_disent_ce_que_le_code_fait(self) -> None:
        # M-W4-doc : une surface qui garde « sans la compter ni l'annoncer » MENT (L-00000111). QUATRE
        # surfaces : `.gitattributes`, la skill, et CE fichier (docstring du MODULE et docstring de W4, par `ast`).
        # NO_GO it. 3 (C2) : les deux surfaces de texte disent AUSSI la borne de l'annonce - elle n'existe que pour
        # les verbes qui construisent le store, et runs/ > 64 MiB la rend « NON sonde ». NO_GO it. 4 (C1) : « verbes qui
        # écrivent seulement » était FAUX (status et dashboard-summary construisent le store : T64) - la portée dite est
        # CHAQUE construction du store au chemin par défaut, et la phrase fausse est REFUSÉE.
        # Réserve 6 (it. 5) : « qui écrivent LE BOARD » — render, commit-stores et commit-run-exports écrivent
        # sans construire le store.
        portee = ("annoncé à chaque construction du store au chemin par défaut — verbes de tasks.py qui "
                  "écrivent le board, replay-sync, python -m agentic_v3 status, dashboard-summary et sync-spec ; "
                  "tasks.py list ne le construit pas")
        import ast

        def plat(texte: str) -> str:
            return " ".join(texte.replace("\n# ", " ").split())

        for chemin in (".gitattributes", ".agents/skills/task-board/SKILL.md"):
            with self.subTest(chemin=chemin):
                texte = plat((ROOT / chemin).read_text(encoding="utf-8"))
                self.assertNotIn("sans la compter ni l'annoncer", texte)
                self.assertIn("la COMPTE (`divergentes`", texte)
                self.assertIn("ANNONCÉ à l'ouverture", texte)
                self.assertIn(portee, texte)
                self.assertNotIn("verbes qui écrivent seulement", texte)
                self.assertIn("runs/ ≤ 64 MiB", texte)
                self.assertIn("« NON sonde »", texte)
                # R1 (cloture fournee 4) : le geste S-00002370 est BORNE a la partition du kit ; une surface qui le
                # tait le rend universel (L-00000079).
                self.assertIn("décidé pour la seule partition du kit", texte)
                self.assertIn("toute autre partition : décision du pilote d'abord", texte)
        skill = (ROOT / ".agents/skills/task-board/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("toute écriture V3 de cette ouverture (intents board gardés dans l'outbox", skill)
        # E3 : README.md devient le guide de l'adoptant. La skill reste jugée
        # hors du kit ; le README technique reste épinglé dans le kit.
        if EST_LE_KIT:
            readme = (ROOT / "README.md").read_text(encoding="utf-8")
            self.assertIn("refuses every V3 write of that opening (board intents stay in the outbox", readme)
        arbre = ast.parse(Path(__file__).read_text(encoding="utf-8"))
        w4 = next(n for n in ast.walk(arbre) if isinstance(n, ast.FunctionDef) and n.name.startswith("test_W4_"))
        for nom, doc in (("module", ast.get_docstring(arbre)), ("W4", ast.get_docstring(w4))):
            with self.subTest(docstring=nom):
                texte = plat(doc or "")
                self.assertNotIn("sans la compter ni l'annoncer", texte)
                self.assertNotIn("aucune clé `divergentes`", texte)
                self.assertNotIn("(clé présente)", texte)
                self.assertIn("la COMPTE", texte)

    def test_W4_un_meme_ulid_divergent_passe_en_double_et_la_reconstruction_garde_la_premiere(self) -> None:
        """La borne de union, MESURÉE (exec-critic, NO_GO S-01M4N496S56T4GS2P2ZNP24QCS) : la
        reconstruction dédoublonne par ULID (`EventStore._appliquer_lignes`), garde la PREMIÈRE
        ligne dans l'ordre (ULID, auteur/copie) — ici une seule copie, donc l'ordre du fichier —
        écarte l'autre, la COMPTE (`divergentes`, l'ULID dans `divergentes_ulid`) et l'ANNONCE sur
        stderr, sans la réparer (T-01M4N496YD7BZDA2NHYQ73JND9 : la perte n'est plus silencieuse).
        Le compte s'asserte sur l'ENSEMBLE des compteurs non nuls (un autre nom compterait en
        double), l'annonce sur un stderr CAPTURÉ (une ligne, l'ULID nommé). Mutants M-W4-silence,
        M-W4-annonce, M-W4-seconde, M-W4-nom-absent. Les trois surfaces qui citent cette borne
        (ce docstring, `.gitattributes`, point (1) du MODE WORKTREE de la skill task-board) sont
        lues par W4e."""
        r = self.depot("w4", (ROOT / ".gitattributes").read_text(encoding="utf-8"))
        fichier = r / EXPORT_W1
        fichier.parent.mkdir(parents=True)
        fichier.write_bytes(b"")
        self.git(r, "add", "--", EXPORT_W1)
        self.git(r, "commit", "-qm", "export socle vide")
        ulid = run_export.nouvel_ulid(MS_OCTOBRE)

        def ajouter(task_id: str) -> None:
            with open(fichier, "a", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps(_evenement(ulid, task_id), sort_keys=True) + "\n")

        self.git(r, "checkout", "-qb", "autre")
        ajouter("T-FUSIONNEE")
        self.git(r, "commit", "-qam", "autre")
        self.git(r, "checkout", "-q", "main")
        ajouter("T-COURANTE")
        self.git(r, "commit", "-qam", "courante")
        fusion = self.git(r, "merge", "-q", "--no-edit", "autre", check=False)

        self.assertEqual(0, fusion.returncode, f"union a signalé un conflit : {fusion.stdout}{fusion.stderr}")
        lignes = [json.loads(l) for l in fichier.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([(ulid, "T-COURANTE"), (ulid, "T-FUSIONNEE")],
                         [(l["ulid"], l["task_id"]) for l in lignes], "union : le même ULID passe en DOUBLE")

        base = self.bac / "base" / "v3.db"
        base.parent.mkdir()
        store = EventStore(base, project_root=r)
        annonce = io.StringIO()
        with contextlib.redirect_stderr(annonce):
            res = store.reconstruire_depuis_exports()

        self.assertEqual((2, 1, 1), (res["total"], res["applied"], res["divergentes"]), res)
        self.assertEqual([ulid], res["divergentes_ulid"])
        self.assertEqual({"applied", "total", "auteurs_rejoues", "divergentes", "divergentes_ulid"},
                         {k for k, v in res.items() if v}, f"ensemble des compteurs non nuls : {res}")
        texte = annonce.getvalue()
        self.assertEqual(1, texte.count("1 ULID DIVERGENT(S)"), texte)
        self.assertIn(ulid, texte)
        self.assertIn("jamais reparee", texte)
        self.assertEqual({"ignores": 0, "malformes": 0, "echecs": 0, "lignes_illisibles": 0, "avortee": 0},
                         {k: res[k] for k in ("ignores", "malformes", "echecs", "lignes_illisibles", "avortee")},
                         "aucun compteur ne nomme la ligne écartée")
        self.assertEqual(1, len(store.get_task_events("T-COURANTE")), "la PREMIÈRE ligne n'est pas gardée")
        self.assertEqual([], store.get_task_events("T-FUSIONNEE"), "la SECONDE ligne est entrée en base")


if __name__ == "__main__":
    unittest.main()
