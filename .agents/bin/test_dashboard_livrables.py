#!/usr/bin/env python3
"""Banc de `/api/livrables` (B3, T-01M54GENAAVDSBX5QWJV9PKEDP, lot S) — le lecteur de `dashboard_routes_etat.py`.

Chaque témoin nomme le mutant de l'annexe § 3 qu'il fait rougir : M1 (forme de la tâche), M2 (lien hors du
dossier), M3 (borne par document), M4 (ETag qui suit le fichier), M12 (octets LUS, pas seulement rendus), M14
(aucun ETag hors `ok`). S'y ajoute le durcissement venu de la revue sécurité du lot voisin : une FIFO, ou un lien
vers elle, ne bloque jamais le handler (`O_NONBLOCK`, `O_NOFOLLOW`, `fstat` + `S_ISREG`). Passe de correction
(exec-critic S-01M5AYZE45W205Z7D1NZXC41MV, sécurité S-01M5AY8VJ7NM1H13J8NWTYRSMY) : témoin FIFO qui rougit, dossier
illisible `degraded`, lien DUR écarté, texte borné en caractères, octets hostiles et sérialisation qui lève.

ISOLATION : la case du banc des routes (`RoutesCase`, relue de son fichier) — racine jetable, environnement du
dashboard redirigé (L-00000076) ; le serveur réel est lancé par `serveur()` et arrêté au nettoyage.
"""
from __future__ import annotations

import importlib.util
import json
import os
import stat
import sys
import threading
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

HERE = Path(__file__).resolve().parent


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_banc = _load("_test_livrables_banc_routes", HERE / "test_dashboard_routes_etat.py")
routes = _banc.routes
T = "T-ABC12"


class LivrablesCase(_banc.RoutesCase):
    def setUp(self) -> None:
        super().setUp()
        self.dossier = self.racine / "docs" / "tasks"
        self.dossier.mkdir(parents=True)

    def doc(self, nom: str, contenu: bytes | str = b"# titre\n") -> Path:
        chemin = self.dossier / nom
        chemin.write_bytes(contenu.encode("utf-8") if isinstance(contenu, str) else contenu)
        return chemin

    def lire(self) -> dict[str, Any]:
        return routes.lire_livrables(self.racine, T)

    def http(self, **entetes: str) -> tuple[int, Any, dict[str, str]]:
        if not hasattr(self, "port"):
            self.httpd, self.port, self.jeton = self.serveur()
        return self.get_json(self.port, f"/api/livrables?task={T}", self.jeton, **entetes)


class GrammaireLivrablesTests(LivrablesCase):
    def test_tache_hors_forme_400(self) -> None:
        """M1 : la forme est un `re.fullmatch` de `T-[0-9A-Z]{3,26}` — `.+` ou `re.match` laisseraient passer la
        traversée, le joker et la fin de ligne (`%0A`) → 200 → rouge."""
        self.doc(f"{T}-plan.md")
        self.httpd, self.port, self.jeton = self.serveur()
        for brut in ("T-1/../../etc", "*", "T-ABC%0A", "T-ABC12%0A", "T-AB", "T-abc12", "T-ABC12/", "x" + T,
                     "T-" + "A" * 27, "T-ABC12%00", "%20T-ABC12"):
            with self.subTest(brut=brut):
                statut, corps, h = self.get_json(self.port, f"/api/livrables?task={brut}", self.jeton)
                self.assertEqual((statut, corps), (400, {"error": "bad_request"}))
                self.assertNotIn("etag", h)
        self.assertEqual(self.get_json(self.port, f"/api/livrables?task={T}", self.jeton)[0], 200)
        self.assertIsNone(routes.refus("/api/livrables", {"task": ["T-" + "Z" * 26]}))
        self.assertIsNotNone(routes.refus("/api/livrables", {"task": ["T-ABC\n"]}))
        self.assertIsNotNone(routes.refus("/api/livrables", {}))


class ListeFermeeTests(LivrablesCase):
    def test_ordre_genres_et_liste_fermee(self) -> None:
        """Ordre de l'annexe § 2 : plan, annexe, critic-n CROISSANT (10 après 2), exec-critic-n, LOT-*, puis le
        reste par nom ; ni une autre tâche au préfixe commun, ni un suffixe hors forme, ni un sous-dossier."""
        for nom in (f"{T}-releve.md", f"{T}-LOT-S.md", f"{T}-exec-critic-1.md", f"{T}-critic-10.md",
                    f"{T}-critic-2.md", f"{T}.md", f"{T}-annexe.md", f"{T}-plan.md", f"{T}3-plan.md",
                    f"{T}-a b.md", f"{T}-plan.txt", f"{T}-plan.md.bak"):
            self.doc(nom)
        (self.dossier / "x").mkdir()
        (self.dossier / "x" / f"{T}-critic-1.md").write_text("# sous-dossier\n", encoding="utf-8")
        corps = self.lire()
        self.assertEqual((corps["task"], corps["statut"], corps["raison"]), (T, "ok", None))
        self.assertEqual([(d["nom"], d["genre"]) for d in corps["documents"]], [
            (f"{T}-plan.md", "plan"), (f"{T}-annexe.md", "annexe"), (f"{T}-critic-2.md", "critic"),
            (f"{T}-critic-10.md", "critic"), (f"{T}-exec-critic-1.md", "exec-critic"), (f"{T}-LOT-S.md", "lot"),
            (f"{T}.md", "autre"), (f"{T}-releve.md", "autre")])
        document = corps["documents"][0]
        self.assertEqual(set(document), {"nom", "genre", "octets", "mtime", "tronque", "texte"})
        self.assertEqual((document["octets"], document["tronque"], document["texte"]), (8, False, "# titre\n"))
        self.assertRegex(document["mtime"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")

    def test_absent(self) -> None:
        """Dossier sans document de la tâche, puis dossier absent : `absent`, dit, sans document."""
        self.doc("T-ZZZ99-plan.md")
        corps = self.lire()
        self.assertEqual((corps["statut"], corps["documents"]), ("absent", []))
        self.assertIn(T, corps["raison"])
        self.doc("T-ZZZ99-plan.md").unlink()
        self.dossier.rmdir()
        self.assertEqual((self.lire()["statut"], self.lire()["raison"]), ("absent", "docs/tasks absent"))

    def test_lien_hors_dossier_refuse(self) -> None:
        """M2 : un lien `docs/tasks/<T>-plan.md` vers un fichier HORS du dossier est ÉCARTÉ AU LISTAGE (`lstat`,
        parent résolu), jamais lu, et le dit ; le document régulier voisin reste servi. Mutant « `stat` qui suit
        le lien, sans le test de parent » → le lien entre dans la liste → rouge."""
        secret = self.tmp / "secret.md"
        secret.write_text("SECRET-hors-dossier\n", encoding="utf-8")
        (self.dossier / f"{T}-plan.md").symlink_to(secret)
        self.doc(f"{T}-annexe.md", "# annexe\n")
        liste = routes._lister(self.racine, T)
        self.assertEqual([c.nom for c in liste.candidats], [f"{T}-annexe.md"])
        corps = self.lire()
        self.assertNotIn("SECRET", str(corps))
        self.assertEqual((corps["statut"], [d["nom"] for d in corps["documents"]]), ("degraded", [f"{T}-annexe.md"]))
        self.assertEqual(corps["raison"], f"entrée non régulière écartée : {T}-plan.md")
        self.assertNotIn(str(self.tmp), corps["raison"])

    @unittest.skipUnless(hasattr(os, "link"), "pas de lien dur sur cet hôte")
    def test_lien_dur_ecarte(self) -> None:
        """Avis sécurité 1 : un lien DUR `docs/tasks/<T>-plan.md` vers un fichier hors du dossier est un fichier
        régulier pour `lstat` — `st_nlink > 1` l'ÉCARTE au listage, dit ; et `fstat` refuse un fichier devenu
        multi-lié après le listage. Mutants « sans `st_nlink` au listage » et « sans `st_nlink` au `fstat` » →
        rouge."""
        secret = self.tmp / "secret-dur.md"
        secret.write_text("SECRET-lien-dur\n", encoding="utf-8")
        os.link(secret, self.dossier / f"{T}-plan.md")
        self.doc(f"{T}-annexe.md", "# annexe\n")
        corps = self.lire()
        self.assertNotIn("SECRET", str(corps))
        self.assertEqual((corps["statut"], [d["nom"] for d in corps["documents"]]), ("degraded", [f"{T}-annexe.md"]))
        self.assertEqual(corps["raison"], f"entrée non régulière écartée : {T}-plan.md")
        with self.assertRaises(OSError) as leve:
            routes._lire_document(self.dossier / f"{T}-plan.md", 100)
        self.assertEqual(leve.exception.strerror, "fichier à liens multiples")

    def test_dossier_illisible_degraded(self) -> None:
        """`docs/tasks` présent mais illisible (mode 0o300) : `glob` avalerait EACCES en une liste vide — la
        réponse est `degraded`, dite, jamais `absent`. Mutant « sans `os.access` » → `absent` → rouge."""
        self.doc(f"{T}-plan.md")
        self.dossier.chmod(0o300)
        self.addCleanup(self.dossier.chmod, 0o755)
        if os.access(self.dossier, os.R_OK):  # pragma: no cover - root lit tout : le cas ne se construit pas ainsi
            self.skipTest("lecteur root : un dossier en mode 0o300 reste lisible")
        corps = self.lire()
        self.assertEqual((corps["statut"], corps["documents"]), ("degraded", []))
        self.assertEqual(corps["raison"], "docs/tasks illisible (PermissionError: Permission denied)")

    def test_plus_de_40_documents(self) -> None:
        for i in range(45):
            self.doc(f"{T}-n{i:02d}.md", "x")
        corps = self.lire()
        self.assertEqual((corps["statut"], len(corps["documents"])), ("ok", 40))
        self.assertEqual(corps["raison"], "5 document(s) au-delà de 40, non listés")


class BornesTests(LivrablesCase):
    def test_borne_par_document(self) -> None:
        """M3 : 600 Kio rendus à 512 Kio exactement, `tronque` vrai, `octets` = la taille réelle ; un petit document
        n'est pas tronqué ; c'est la borne de LECTURE qui coupe, pas celle du texte (`raison` nulle). Mutant « borne
        relevée » → texte de plus de 512 Kio, ou coupé par la seule borne en caractères → rouge."""
        self.assertEqual(routes.BORNE_DOC, 512 * 1024)
        self.doc(f"{T}-plan.md", b"a" * (600 * 1024))
        self.doc(f"{T}-annexe.md", "court")
        corps = self.lire()
        self.assertEqual((corps["statut"], corps["raison"]), ("ok", None))
        plan, annexe = corps["documents"]
        self.assertEqual((len(plan["texte"]), plan["tronque"], plan["octets"]), (512 * 1024, True, 600 * 1024))
        self.assertEqual((annexe["texte"], annexe["tronque"]), ("court", False))

    def test_borne_totale_2_mio(self) -> None:
        """Au-delà de 2 Mio lus en tout : les documents suivants partent SANS texte, `tronque`, raison dite."""
        self.assertEqual(routes.BORNE_TOTALE, 2 * 1024 * 1024)
        for i in range(5):
            self.doc(f"{T}-critic-{i + 1}.md", b"b" * (600 * 1024))
        corps = self.lire()
        self.assertEqual([len(d["texte"]) for d in corps["documents"]], [512 * 1024] * 4 + [0])
        self.assertTrue(all(d["tronque"] for d in corps["documents"]))
        self.assertEqual((corps["statut"], corps["raison"]),
                         ("ok", "borne totale de 2097152 octets atteinte : 1 document(s) sans texte"))

    def test_coupe_par_la_borne_totale_dite(self) -> None:
        """Un document que le RESTE du budget coupe sous `BORNE_DOC` le dit (le client afficherait sinon « tronqué
        à 512 Kio ») ; celui que coupe sa propre borne de 512 Kio, non ; celui que le reste du budget ne coupe pas
        (lu en entier sous un plafond réduit), non plus. Budget : 3 × 512 Kio + 100 000 o, puis critic-3 de
        124 288 o lu ENTIER sous un plafond de 424 288 o, restent 300 000 o pour critic-4 de 400 000 o. Mutants
        « raison retirée », « raison sur toute coupe » et « raison sur tout plafond réduit » → rouge."""
        for suffixe in ("plan", "annexe", "critic-1"):
            self.doc(f"{T}-{suffixe}.md", b"a" * (600 * 1024))
        self.doc(f"{T}-critic-2.md", b"b" * 100_000)
        self.doc(f"{T}-critic-3.md", b"c" * (routes.BORNE_TOTALE - 3 * routes.BORNE_DOC - 100_000 - 300_000))
        self.doc(f"{T}-critic-4.md", b"d" * 400_000)
        corps = self.lire()
        entier, coupe = corps["documents"][4:6]
        self.assertEqual((entier["nom"], len(entier["texte"]), entier["tronque"]), (f"{T}-critic-3.md", 124_288, False))
        self.assertEqual((coupe["nom"], len(coupe["texte"]), coupe["tronque"], coupe["octets"]),
                         (f"{T}-critic-4.md", 300_000, True, 400_000))
        self.assertEqual((corps["statut"], corps["raison"]),
                         ("ok", f"{T}-critic-4.md : tronqué à 300000 octets par la borne totale de la tâche"))

    def test_lecture_bornee_compte_les_octets(self) -> None:
        """M12 : sur un document de 3 Mio, `os.read` rend EXACTEMENT `BORNE_DOC + 1` octets au total. Mutant « lire
        tout puis couper » (`read_bytes()[:BORNE_DOC]` : 0 octet par `os.read`, ou `os.read(fd, taille)` : 3 Mio)
        → rouge."""
        self.doc(f"{T}-plan.md", b"c" * (3 * 1024 * 1024))
        vrai_read, lus = os.read, []

        def compteur(fd: int, n: int) -> bytes:
            bloc = vrai_read(fd, n)
            lus.append(len(bloc))
            return bloc
        with mock.patch.object(routes.os, "read", compteur):
            corps = self.lire()
        self.assertEqual(sum(lus), routes.BORNE_DOC + 1)
        self.assertEqual((len(corps["documents"][0]["texte"]), corps["documents"][0]["tronque"]),
                         (routes.BORNE_DOC, True))

    def test_decodage_backslashreplace_et_coupe(self) -> None:
        """Un octet invalide est rendu `\\xff`, jamais une exception ; un caractère coupé par la borne est retiré,
        pas rendu en `\\xc3`."""
        self.doc(f"{T}-plan.md", b"ok \xff fin")
        self.doc(f"{T}-annexe.md", b"a" * (routes.BORNE_DOC - 1) + "é".encode("utf-8") + b"suite")
        plan, annexe = self.lire()["documents"]
        self.assertEqual(plan["texte"], "ok \\xff fin")
        self.assertEqual((annexe["texte"], annexe["tronque"]), ("a" * (routes.BORNE_DOC - 1), True))


class HostilesTests(LivrablesCase):
    """Les avis sécurité 2 et l'angle mort de l'exec-critic : des octets hostiles par le VRAI serveur."""

    def brut(self) -> tuple[int, bytes, dict[str, str]]:
        if not hasattr(self, "port"):
            self.httpd, self.port, self.jeton = self.serveur()
        return self.get(self.port, f"/api/livrables?task={T}", self.jeton)

    def test_amplification_bornee(self) -> None:
        """Avis 2 : 600 000 octets de `\\xff` rendent 4 caractères chacun (`backslashreplace`) — le texte est
        coupé à `BORNE_DOC` caractères, `tronque`, raison dite, et la réponse sérialisée reste sous ~2,1 Mio.
        Mutant « sans la coupe du texte » → 2,6 Mo → rouge."""
        self.doc(f"{T}-plan.md", b"\xff" * 600_000)
        statut, octets, _h = self.brut()
        corps = json.loads(octets)
        self.assertEqual(statut, 200)
        self.assertLessEqual(len(octets), int(2.1 * 1024 * 1024))
        plan = corps["documents"][0]
        self.assertEqual((len(plan["texte"]), plan["tronque"], plan["texte"][:8]), (routes.BORNE_DOC, True, "\\xff\\xff"))
        self.assertEqual((corps["statut"], corps["raison"]),
                         ("ok", f"{T}-plan.md : texte coupé à {routes.BORNE_DOC} caractères (octets invalides)"))

    def test_pire_cas_nul_epingle(self) -> None:
        """Le pire cas ÉCRIT de la docstring : 2 Mio de NUL lus (UTF-8 valide, `\\u0000` en JSON, ×6) se servent
        sous 13 Mo en clair et sous 100 Ko en gzip. 5 documents de 600 Kio, pour que le budget total morde.
        Mutant « `BORNE_TOTALE` ×2 » → 5 × 512 Kio × 6 ≈ 15,7 Mo → rouge."""
        for i in range(5):
            self.doc(f"{T}-critic-{i + 1}.md", b"\x00" * (600 * 1024))
        statut, octets, _h = self.brut()
        _s, zippe, hz = self.get(self.port, f"/api/livrables?task={T}", self.jeton, Accept_Encoding="gzip")
        corps = json.loads(octets)
        self.assertEqual((statut, corps["statut"], sum(len(d["texte"]) for d in corps["documents"])),
                         (200, "ok", routes.BORNE_TOTALE))
        self.assertGreater(len(octets), 12_000_000, "le témoin ne mesurerait plus le pire cas")
        self.assertLessEqual(len(octets), 13_000_000)
        self.assertEqual(hz.get("content-encoding"), "gzip")
        self.assertLessEqual(len(zippe), 100_000)

    def test_non_ascii_a_sa_taille_utf8(self) -> None:
        """Un caractère non ASCII est servi à sa taille UTF-8 (`ensure_ascii=False` du transport) : 2 Mio d'emoji
        → ~2 Mio servis. Mutant « `ensure_ascii=True` » → `\\ud83d\\ude00`, 12 octets pour 4 → ~6,3 Mo → rouge."""
        for i in range(4):
            self.doc(f"{T}-critic-{i + 1}.md", "\U0001F600".encode("utf-8") * (128 * 1024))
        statut, octets, _h = self.brut()
        self.assertEqual((statut, json.loads(octets)["statut"]), (200, "ok"))
        self.assertLessEqual(len(octets), int(2.1 * 1024 * 1024))

    def test_octets_hostiles_json_valide(self) -> None:
        """Angle mort : `\\xed\\xb3\\xbf` (un substitut encodé, interdit en UTF-8) dans un `.md` → 200, JSON valide,
        octets rendus `\\xNN`. Mutant « `surrogateescape` au décodage » → substitut isolé → `degraded` → rouge."""
        self.doc(f"{T}-plan.md", b"# x\n\xed\xb3\xbf fin\n")
        statut, octets, h = self.brut()
        corps = json.loads(octets.decode("utf-8"))
        self.assertEqual((statut, corps["statut"], corps["documents"][0]["texte"]),
                         (200, "ok", "# x\n\\xed\\xb3\\xbf fin\n"))
        self.assertIn("etag", h)

    def test_serialisation_qui_leve_degraded(self) -> None:
        """Une réponse qui ne se sérialise pas (un substitut isolé dans le texte) part 200 `degraded`, sans ETag,
        jamais en connexion coupée. Mutant « sérialisation hors `try` » → connexion coupée → rouge."""
        self.doc(f"{T}-plan.md")
        with mock.patch.object(_banc.dashboard._routes_mod, "_decoder", return_value="\udcff"):
            statut, octets, h = self.brut()
        self.assertEqual((statut, json.loads(octets)), (200, {
            "task": T, "statut": "degraded", "raison": "réponse non sérialisable (UnicodeEncodeError)",
            "documents": []}))
        self.assertNotIn("etag", h)


class EtagTests(LivrablesCase):
    def test_etag_suit_le_fichier(self) -> None:
        """M4 : l'ETag est fait de `mtime_ns:size` de chaque document — réécrit à la même taille (mtime neuf) ou à
        la même date (taille neuve), le 304 cède la place à un 200. Mutant « ETag sans `mtime_ns:size` » →
        304 servi sur l'annexe réécrite → rouge."""
        self.doc(f"{T}-plan.md")
        annexe = self.doc(f"{T}-annexe.md", "version 1")
        os.utime(annexe, ns=(1_700_000_000_000_000_000,) * 2)
        statut, _c, h1 = self.http()
        self.assertEqual(self.http(If_None_Match=h1["etag"])[0], 304)
        annexe.write_text("version 2", encoding="utf-8")
        os.utime(annexe, ns=(1_700_000_001_000_000_000,) * 2)
        statut, corps, h2 = self.http(If_None_Match=h1["etag"])
        self.assertEqual((statut, corps["documents"][1]["texte"]), (200, "version 2"))
        self.assertNotEqual(h2["etag"], h1["etag"])
        annexe.write_text("version 2 longue", encoding="utf-8")
        os.utime(annexe, ns=(1_700_000_001_000_000_000,) * 2)
        statut, corps, h3 = self.http(If_None_Match=h2["etag"])
        self.assertEqual((statut, corps["documents"][1]["texte"]), (200, "version 2 longue"))
        self.assertNotEqual(h3["etag"], h2["etag"])

    def test_sans_etag_hors_ok(self) -> None:
        """M14 : `absent` et `degraded` partent SANS ETag ; quand la LISTE n'est pas `ok`, `If-None-Match: *` n'y
        rend jamais 304. Mutant « ETag émis sur tout statut » → rouge. BORNE (celle d'A2.3) : la revalidation
        précède la lecture — un fichier rendu illisible sans que bouge son `mtime_ns:size` (chmod) se revalide en
        304 chez un client qui tient déjà l'ETag ; le 200 qui le lit, lui, part sans ETag (cas 3)."""
        cas = []
        statut, corps, h = self.http(If_None_Match="*")
        cas.append(("absent", statut, corps["statut"], h))
        self.doc(f"{T}-plan.md")
        (self.dossier / f"{T}-annexe.md").symlink_to(self.tmp)
        statut, corps, h = self.http(If_None_Match="*")
        cas.append(("degraded", statut, corps["statut"], h))
        (self.dossier / f"{T}-annexe.md").unlink()
        illisible = self.doc(f"{T}-critic-1.md")
        illisible.chmod(0)
        self.addCleanup(illisible.chmod, 0o644)
        if os.access(illisible, os.R_OK):  # pragma: no cover - root lit tout : le cas ne se construit pas ainsi
            self.skipTest("lecteur root : un fichier en mode 0 reste lisible")
        statut, corps, h = self.http()
        cas.append(("degraded", statut, corps["statut"], h))
        self.assertNotIn(str(self.tmp), corps["raison"])
        self.assertIn(f"{T}-critic-1.md illisible (PermissionError", corps["raison"])
        for attendu, statut, lu, h in cas:
            with self.subTest(attendu=attendu):
                self.assertEqual((statut, lu), (200, attendu))
                self.assertNotIn("etag", h)
        illisible.chmod(0o644)
        statut, corps, h = self.http()
        self.assertEqual((statut, corps["statut"]), (200, "ok"))
        self.assertIn("etag", h)


class FifoEtLiensTests(LivrablesCase):
    """Le durcissement de la revue sécurité : une FIFO bloque un `open()` ordinaire jusqu'à ce qu'un écrivain
    arrive — le handler ne doit jamais l'attendre."""

    def ouvrir_en_fil(self, chemin: Path) -> tuple[threading.Thread, list[Any]]:
        issue: list[Any] = []

        def lire() -> None:
            try:
                issue.append(routes._lire_document(chemin, 100))
            except OSError as exc:
                issue.append(exc)
        fil = threading.Thread(target=lire, daemon=True)
        fil.start()
        fil.join(timeout=5)
        return fil, issue

    def debloquer(self, fifo: Path, fil: threading.Thread) -> None:
        """Si l'ouverture a bloqué (mutant), un écrivain la libère : le fil ne survit pas au cas."""
        if fil.is_alive():
            try:
                os.close(os.open(fifo, os.O_WRONLY | os.O_NONBLOCK))
            except OSError:
                pass
            fil.join(timeout=5)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "pas de FIFO sur cet hôte")
    def test_fifo_ecartee_au_listage(self) -> None:
        fifo = self.dossier / f"{T}-plan.md"
        os.mkfifo(fifo)
        issue: list[Any] = []
        fil = threading.Thread(target=lambda: issue.append(self.lire()), daemon=True)
        fil.start()
        fil.join(timeout=5)
        bloque = fil.is_alive()  # AVANT de débloquer : sinon l'écrivain libère le fil et le témoin ne rougit plus
        self.debloquer(fifo, fil)
        self.assertFalse(bloque, "la route a bloqué sur la FIFO")
        self.assertEqual(len(issue), 1, "la route a bloqué sur la FIFO")
        self.assertEqual((issue[0]["statut"], issue[0]["documents"]), ("degraded", []))
        self.assertEqual(issue[0]["raison"], f"entrée non régulière écartée : {T}-plan.md")

    @unittest.skipUnless(hasattr(os, "mkfifo") and hasattr(os, "O_NONBLOCK"), "pas de FIFO sur cet hôte")
    def test_ouverture_d_une_fifo_ne_bloque_pas_et_leve(self) -> None:
        """`O_NONBLOCK` : l'ouverture rend la main ; `fstat` + `S_ISREG` : elle lève avant toute lecture. Mutants
        « sans `O_NONBLOCK` » (bloque) et « sans `S_ISREG` » (rend b"" sans erreur) → rouge."""
        fifo = self.tmp / "fifo"
        os.mkfifo(fifo)
        fil, issue = self.ouvrir_en_fil(fifo)
        bloque = fil.is_alive()
        self.debloquer(fifo, fil)
        self.assertFalse(bloque, "l'ouverture de la FIFO a bloqué")
        self.assertEqual(len(issue), 1)
        self.assertIsInstance(issue[0], OSError)
        self.assertEqual(issue[0].strerror, "pas un fichier régulier")

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"), "pas d'O_NOFOLLOW sur cet hôte")
    def test_ouverture_d_un_lien_leve(self) -> None:
        """`O_NOFOLLOW` : un lien glissé après le listage n'est jamais suivi, vers un fichier comme vers une FIFO.
        Mutant « sans `O_NOFOLLOW` » → le secret est lu → rouge."""
        secret = self.tmp / "secret.md"
        secret.write_text("SECRET\n", encoding="utf-8")
        lien = self.dossier / f"{T}-plan.md"
        lien.symlink_to(secret)
        with self.assertRaises(OSError):
            routes._lire_document(lien, 100)
        if hasattr(os, "mkfifo"):
            fifo = self.tmp / "fifo"
            os.mkfifo(fifo)
            vers_fifo = self.dossier / f"{T}-annexe.md"
            vers_fifo.symlink_to(fifo)
            fil, issue = self.ouvrir_en_fil(vers_fifo)
            bloque = fil.is_alive()
            self.debloquer(fifo, fil)
            self.assertFalse(bloque, "l'ouverture du lien vers la FIFO a bloqué")
            self.assertIsInstance(issue[0], OSError)
        self.assertTrue(stat.S_ISLNK(lien.lstat().st_mode))


if __name__ == "__main__":
    unittest.main()
