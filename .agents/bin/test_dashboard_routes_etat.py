#!/usr/bin/env python3
"""Banc du lot D de T-01M51Q7GJ1B6315SFKNDAAE2P0 — `dashboard_routes_etat.py` et son branchement dans `dashboard.py`.

Les témoins de l'annexe A3 D, chacun écrit pour ROUGIR sous le mutant qu'il nomme, la grammaire FIGÉE au journal
du parent (S-01M53C814Z, S-01M53E5XBA, S-01M53BTDZA) et les réserves du verdict plan-critic 2/8 qui touchent D :
C1 (parité sur source dégradée), C3 (aucun nom de magasin écrit en dur), C4 (`open` retiré, départage par `rang`,
`q` littéral, domaines, `autour` + `offset`), C8 (requête base qui lève → direct ; `ordre` absent = `recent`).

DEUX JEUX DE VECTEURS, écrits À LA MAIN par d'autres lots et recopiés ici en littéraux : ceux du stub de E
(smoketest.mjs § 46 a, égalités au rang) et ceux de G (glass.spec.ts `G_CASES`, « LOT G × D — parité »). Chaque
vecteur est joué DEUX fois — base etat.db rafraîchie (`source: "base"` EXIGÉ), puis lecture directe — et les deux
réponses doivent être égales hors `source`.

ISOLATION (L-00000076, L-00000537) : chaque cas redirige `AGENTS_ETAT_DB`, `CADRE_STATE_DIR`,
`AGENTS_DASHBOARD_PROJECT_ROOT`, `AGENTS_EVENTS_DIR`, `AGENTS_OTEL_DIR`, `AGENTS_PROJECT_JSON`,
`AGENTS_OTEL_PROJECT_ROOT`, `AGENTKIT_REGISTRY` et `AGENTS_TERM_DIR` vers un répertoire jetable ; aucun démon
n'est lancé ; la base n'est écrite que par `rafraichir`, jamais par une route.
"""
from __future__ import annotations

import ast
import gzip
import http.client
import importlib.util
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
import unittest
import urllib.parse
from pathlib import Path
from typing import Any
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


routes = _load("_test_routes_etat", HERE / "dashboard_routes_etat.py")
ep = routes._etat
dashboard = _load("_test_routes_dashboard", HERE / "dashboard.py")

# ---------------------------------------------------------------------------
# A2.3 telle que FIGÉE (S-01M53C814Z : `open` retiré ; S-01M53E5XBA : plafond de 10 chiffres), en LITTÉRAUX.
# ---------------------------------------------------------------------------
A2_3 = {
    "/api/specs": ("task", "kind", "dernier", "avec", "ordre", "q", "autour", "offset", "limit"),
    "/api/lecons": ("category", "status", "q", "autour", "offset", "limit"),
    "/api/recherche": (),
    "/api/livrables": ("task",),  # B3 (T-01M54GENAAVDSBX5QWJV9PKEDP) : rouverte d'une route, plan r3 approuvé
}
COUNTS_CLES = ["all", "constraint", "decision", "lesson", "archived"]

# --- vecteurs de E (smoketest.mjs § 46 a) ------------------------------------
ULID_E = "S-01J9ZK3Q4N8VXW2T5R7M6P0ABC"
SPECS_E = [
    {"id": "S-00000010", "task": "T-00000001", "kind": "plan", "date": "2026-10-01", "title": "plan v1 Élève",
     "text": "texte-seul-xyz", "files": ["a.py"]},
    {"id": "S-00000011", "task": "T-00000001", "kind": "verdict", "date": "2026-10-01", "title": "verdict v1"},
    {"id": "S-9", "task": "T-00000002", "kind": "plan", "date": "2026-10-01", "title": "plan court a_b"},
    {"id": ULID_E, "task": "T-00000001", "kind": "plan", "date": "2026-10-02", "title": "plan v2 100%"},
    {"id": "S-0012", "task": "T-00000001", "kind": "decision", "date": "2026-10-02", "title": "décision"},
    {"id": "S-12", "task": "T-00000003", "kind": "verdict", "date": "2026-10-02", "title": "verdict sans plan axb"},
    {"id": "libre", "task": "T-00000002", "kind": "decision", "date": "2026-10-03", "title": "décision 1000"},
    {"id": "S-00000013", "task": "T-00000002", "kind": "verdict", "date": "2026-10-03", "title": "verdict t2"},
]
LEDGER_E = [
    {"id": "L-00000001", "category": "constraint", "status": "active", "title": "contrainte une",
     "text": "corps-unique", "tags": ["porte"], "related": "T-00000001", "created": "2026-09-01"},
    {"id": "L-00000002", "category": "lesson", "status": "archived", "title": "leçon archivée", "created": "2026-09-02"},
    {"id": "L-00000003", "category": "decision", "status": "active", "title": "décision",
     "text_preview": "aperçu-seul", "created": "2026-09-03"},
    {"id": "L-00000004", "category": "lesson", "status": "active", "title": "leçon", "related": ["T-00000009"],
     "created": "2026-09-04"},
]
RECENT_E = [ULID_E, "S-00000013", "S-0012", "S-12", "S-00000011", "S-00000010", "S-9", "libre"]
GATE_E = [ULID_E, "S-00000013", "S-0012", "S-00000011", "S-9", "libre"]
# MESURÉ : `specs.load` REFUSE ce jeu (« numeric id collision — S-0012 and S-12 both resolve to 12 », et « libre »
# sans queue numérique) — une égalité (tier, num, valeur) ne peut pas exister dans un journal réel. Le départage
# au rang (C4) est donc témoigné sur le SQL de la base et sur le tri direct ; les cas qui passent par les
# magasins jouent la variante CHARGEABLE ci-dessous (S-0012 → S-00000012, S-12 → S-00000014, libre → S-00000005).
_RENOMMES = {"S-0012": "S-00000012", "S-12": "S-00000014", "libre": "S-00000005"}
SPECS_R = [dict(e, id=_RENOMMES.get(e["id"], e["id"])) for e in SPECS_E]
RECENT_R = [ULID_E, "S-00000014", "S-00000013", "S-00000012", "S-00000011", "S-00000010", "S-9", "S-00000005"]
GATE_R = [ULID_E, "S-00000013", "S-00000012", "S-00000011", "S-9", "S-00000005"]

# --- vecteurs de G (glass.spec.ts, G_SPECS / G_LEDGER / G_CASES) ------------------------------------------
G_ULID, G_ULID_L = "01M51Q7GJ1B6315SFKNDAAE2P1", "01M51Q7GJ1B6315SFKNDAAE2P2"


def gs(n: int) -> str:
    return f"S-{n:08d}"


def gl(n: int) -> str:
    return f"L-{n:08d}"


def _g_spec(ident: str, t: int, kind: str, title: str, text: str | None = None) -> dict[str, Any]:
    return {"id": ident, "task": f"T-{t:08d}", "kind": kind, "title": title, "date": "2026-10-01",
            "text": text or f"texte {ident}", "files": []}


G_SPECS = [_g_spec(gs(3), 1, "plan", "plan de la tâche un"), _g_spec(gs(1), 1, "verdict", "verdict ancien"),
           _g_spec(f"S-{G_ULID}", 1, "verdict", "verdict récent"),
           _g_spec(gs(10), 2, "decision", "Élève à 100% : a_b", "seulement-dans-le-texte"),
           _g_spec(gs(2), 2, "delta", "delta deux"), _g_spec(gs(4), 3, "decision", "décision sans plan"),
           _g_spec(gs(11), 2, "plan", "plan deux"), _g_spec(gs(12), 2, "decision", "axb sans tiret bas"),
           _g_spec(gs(13), 3, "delta", "1000 essais")]
G_LEDGER = [
    {"id": gl(1), "category": "lesson", "title": "Leçon sur l'Élève", "created": "2026-10-01", "status": "active",
     "text": "texte un", "tags": ["e2e"], "related": "T-00000001"},
    {"id": gl(2), "category": "constraint", "title": "contrainte", "created": "2026-10-01", "status": "active",
     "text": "100% a_b", "tags": [], "related": ""},
    {"id": gl(3), "category": "decision", "title": "décision du ledger", "created": "2026-10-01", "status": "active",
     "text": "texte trois", "tags": [], "related": ""},
    {"id": gl(4), "category": "lesson", "title": "archivée", "created": "2026-10-01", "status": "archived",
     "text": "texte quatre", "tags": [], "related": ""},
    {"id": f"L-{G_ULID_L}", "category": "constraint", "title": "contrainte ULID", "created": "2026-10-01",
     "status": "active", "text": "texte", "text_preview": "aperçu", "tags": [], "related": ""},
]
G_RECENT = [f"S-{G_ULID}", gs(13), gs(12), gs(11), gs(10), gs(4), gs(3), gs(2), gs(1)]
G_COUNTS = {"all": 4, "constraint": 2, "decision": 1, "lesson": 1, "archived": 1}
# (chemin, requête, ids attendus ou None, champs attendus, règle) — 200 seulement ; les 400 sont plus bas.
G_CASES: list[tuple[str, list[tuple[str, str]], list[str] | None, dict[str, Any], str]] = [
    ("/api/specs", [], G_RECENT, {"total": 9, "offset": 0, "limit": 25}, "défauts limit 25 offset 0, recent"),
    ("/api/specs", [("ordre", "store")], [gs(3), gs(1), f"S-{G_ULID}", gs(10), gs(2), gs(4), gs(11), gs(12), gs(13)],
     {}, "ordre=store = rang"),
    ("/api/specs", [("ordre", "recent"), ("limit", "2"), ("offset", "2")], [gs(12), gs(11)],
     {"total": 9, "offset": 2, "limit": 2}, "page"),
    ("/api/specs", [("offset", "1000000000")], [], {"total": 9, "offset": 10 ** 9}, "offset ≤ 10^9"),
    ("/api/specs", [("task", "T-00000002")], [gs(12), gs(11), gs(10), gs(2)], {}, "task"),
    ("/api/specs", [("kind", "delta"), ("ordre", "store")], [gs(2), gs(13)], {}, "kind, ordre=store"),
    ("/api/specs", [("kind", "plan,verdict,decision"), ("dernier", "1"), ("avec", "plan")],
     [f"S-{G_ULID}", gs(12), gs(11), gs(3)], {}, "kind multiple + dernier + avec=plan (Gouvernance)"),
    ("/api/specs", [("q", "ELEVE")], [gs(10)], {}, "q replié (accents, casse)"),
    ("/api/specs", [("q", "a_b")], [gs(10)], {}, "C4 `_` n'est pas un joker"),
    ("/api/specs", [("q", "100%")], [gs(10)], {}, "C4 `%` n'est pas un joker"),
    ("/api/specs", [("q", "t-00000003")], [gs(13), gs(4)], {}, "q lit task"),
    ("/api/specs", [("q", "seulement-dans-le-texte")], [], {"total": 0}, "q ne lit PAS text sur /api/specs"),
    ("/api/specs", [("autour", gs(2)), ("limit", "2")], [gs(3), gs(2)],
     {"offset": 6, "rang": 7, "trouve": True, "total": 9}, "autour"),
    ("/api/specs", [("autour", "S-99999999")], None, {"trouve": False, "total": 9}, "autour introuvable"),
    ("/api/lecons", [], [f"L-{G_ULID_L}", gl(3), gl(2), gl(1)], {"total": 4, "counts": G_COUNTS},
     "actives seules + counts"),
    ("/api/lecons", [("status", "archived")], [gl(4)], {"total": 1, "counts": G_COUNTS}, "status=archived"),
    ("/api/lecons", [("category", "constraint")], [f"L-{G_ULID_L}", gl(2)], {"counts": G_COUNTS},
     "category, counts insensibles"),
    ("/api/lecons", [("category", "lesson"), ("q", "eleve")], [gl(1)], {"counts": G_COUNTS}, "category + q replié"),
    ("/api/lecons", [("q", "a_b")], [gl(2)], {}, "q lit text sur /api/lecons"),
    ("/api/lecons", [("q", "E2E")], [gl(1)], {}, "q lit tags"),
    ("/api/lecons", [("q", "t-00000001")], [gl(1)], {}, "q lit related"),
    ("/api/lecons", [("q", "apercu")], [f"L-{G_ULID_L}"], {}, "q lit text_preview"),
    ("/api/lecons", [("autour", gl(2)), ("limit", "2")], [gl(2), gl(1)], {"offset": 2, "rang": 2, "trouve": True},
     "autour"),
    ("/api/lecons", [("autour", gl(4))], None, {"trouve": False, "total": 4}, "autour d'une archivée : hors liste"),
    ("/api/lecons", [("status", "archived"), ("autour", gl(4))], [gl(4)], {"rang": 0, "trouve": True},
     "autour parmi les archivées"),
]
# Les 400 de G (parité exigée) PLUS les choix de E figés par S-01M53C814Z (kind vide, paramètre répété).
G_REFUS: list[tuple[str, list[tuple[str, str]]]] = [
    *[("/api/specs", [(k, v)]) for k, v in (
        ("page", "1"), ("limit", "0"), ("limit", "201"), ("limit", ""), ("limit", "-1"), ("limit", "a"),
        ("limit", "٣"), ("limit", "５"), ("limit", "5_0"), ("limit", "+5"), ("offset", "1000000001"),
        ("offset", "9223372036854775808"), ("ordre", "x"), ("dernier", "2"), ("avec", "x"), ("open", "1"))],
    ("/api/specs", [("autour", gs(1)), ("offset", "0")]),
    ("/api/specs", [("kind", "plan,,verdict")]),
    ("/api/specs", [("limit", "2"), ("limit", "3")]),
    ("/api/lecons", [("task", "T-00000001")]), ("/api/lecons", [("category", "x")]),
    ("/api/lecons", [("status", "active")]), ("/api/recherche", [("x", "1")]),
]


def _qs(brut: str) -> dict[str, list[str]]:
    """La requête TELLE QUE dashboard.py la passe (`parse_qs`, valeurs vides gardées)."""
    return urllib.parse.parse_qs(brut, keep_blank_values=True)


def _url(path: str, paires: list[tuple[str, str]]) -> str:
    """L'URL telle que l'envoie le client (`URLSearchParams` : espace → `+`, `+` → `%2B`)."""
    return f"{path}?{urllib.parse.urlencode(paires)}" if paires else path


def _ids(liste: Any) -> list[str]:
    return [e.get("id") for e in liste] if isinstance(liste, list) else []


def _sans_source(corps: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in corps.items() if k != "source"}


class RoutesCase(unittest.TestCase):
    """Une racine de projet jetable, une base HORS de cette racine, l'environnement du dashboard isolé."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name).resolve()
        self.racine = self.tmp / "projet"
        (self.racine / ".agents").mkdir(parents=True)
        self.etat = self.tmp / "machine" / "etat.db"
        self.absente = self.tmp / "machine" / "absente.db"
        (self.tmp / "project.json").write_text(json.dumps({"project_id": "banc-routes-etat"}), encoding="utf-8")
        self._horloge = 1_700_000_000_000_000_000
        env = mock.patch.dict(os.environ, {
            "AGENTS_ETAT_DB": str(self.etat), "CADRE_STATE_DIR": str(self.tmp / "cadre"),
            "AGENTS_DASHBOARD_PROJECT_ROOT": str(self.racine), "AGENTS_EVENTS_DIR": str(self.tmp / "events"),
            "AGENTS_OTEL_DIR": str(self.tmp / "otel"), "AGENTS_PROJECT_JSON": str(self.tmp / "project.json"),
            "AGENTS_OTEL_PROJECT_ROOT": str(self.tmp / "own-root"),
            "AGENTKIT_REGISTRY": str(self.tmp / "registry.json"), "AGENTS_TERM_DIR": str(self.tmp / "term")})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("CADRE_PROJECT_ROOT", None)
        dashboard._readers_mod.reset_cache_for_tests()

    # -- les magasins, écrits par la forme que lit leur propriétaire ------------------------------------------
    def _dater(self, chemin: Path) -> None:
        self._horloge += 1_000_000_000
        os.utime(chemin, ns=(self._horloge, self._horloge))

    def ecrire(self, specs: list[dict[str, Any]], ledger: list[dict[str, Any]]) -> None:
        for chemin, entrees in ((ep._specs.store_path(self.racine), specs),
                                (ep._ledger.store_path(self.racine), ledger)):
            chemin.parent.mkdir(parents=True, exist_ok=True)
            chemin.write_bytes(json.dumps({"entries": entrees}, ensure_ascii=False).encode("utf-8"))
            self._dater(chemin)

    def rafraichir(self) -> None:
        os.environ["AGENTS_ETAT_DB"] = str(self.etat)
        self.assertEqual(ep.rafraichir(self.racine), {"SPECS": "ok", "LEDGER": "ok"})

    # -- une réponse, en base ou en direct -----------------------------------------------------------------
    def corps(self, path: str, paires: list[tuple[str, str]] = (), *, base: bool) -> dict[str, Any]:
        params = routes.parametres(path, _qs(urllib.parse.urlencode(list(paires))))
        self.assertIsNotNone(params, f"{path} {paires} : hors grammaire")
        os.environ["AGENTS_ETAT_DB"] = str(self.etat if base else self.absente)
        return routes.corps_route(path, params, self.racine, empreinte="e")

    def deux(self, path: str, paires: list[tuple[str, str]] = ()) -> dict[str, Any]:
        """La réponse en base (source EXIGÉE : base) ET en direct (source : direct) ; égales hors `source`."""
        en_base = self.corps(path, paires, base=True)
        en_direct = self.corps(path, paires, base=False)
        if path != "/api/recherche":
            self.assertEqual(en_base["source"], "base", f"{path} {paires} : repli direct MUET")
            self.assertEqual(en_direct["source"], "direct")
        self.assertEqual(_sans_source(en_base), _sans_source(en_direct), f"parité base/direct : {path} {paires}")
        return en_direct

    # -- le vrai serveur ------------------------------------------------------------------------------------
    def serveur(self) -> tuple[Any, int, str]:
        httpd, jeton = dashboard.create_ui_server(project_root=self.racine)
        fil = threading.Thread(target=httpd.serve_forever, daemon=True)
        fil.start()

        def arreter() -> None:
            httpd.shutdown()
            httpd.server_close()
            fil.join(timeout=5)
        self.addCleanup(arreter)
        return httpd, httpd.server_address[1], jeton

    @staticmethod
    def get(port: int, url: str, jeton: str | None, **entetes: str) -> tuple[int, bytes, dict[str, str]]:
        con = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        try:
            h = {k.replace("_", "-"): v for k, v in entetes.items()}
            if jeton is not None:
                h["Authorization"] = f"Bearer {jeton}"
            con.request("GET", url, headers=h)
            r = con.getresponse()
            return r.status, r.read(), {k.lower(): v for k, v in r.getheaders()}
        finally:
            con.close()

    def get_json(self, port: int, url: str, jeton: str, **entetes: str) -> tuple[int, Any, dict[str, str]]:
        statut, octets, h = self.get(port, url, jeton, **entetes)
        return statut, (json.loads(octets) if octets else None), h


# ---------------------------------------------------------------------------
# La grammaire FERMÉE, sans socket.
# ---------------------------------------------------------------------------

class GrammaireTests(unittest.TestCase):
    def test_grammaire_egale_A2_3(self) -> None:
        """Mutant « `open` gardé » ou « un paramètre de trop » → rouge."""
        self.assertEqual(routes.PARAMETRES, A2_3)
        self.assertEqual(routes.ROUTES, frozenset(A2_3))
        self.assertEqual(routes.CATEGORIES, ("constraint", "decision", "lesson"))
        self.assertEqual((routes.LIMITE_DEFAUT, routes.LIMITE_MAX, routes.DECALAGE_MAX), (25, 200, 10 ** 9))

    def test_parametre_inconnu_400(self) -> None:
        for path, brut in (("/api/specs", "open=1"), ("/api/specs", "page=2"), ("/api/specs", "x=1"),
                           ("/api/specs", "category=lesson"), ("/api/lecons", "kind=plan"),
                           ("/api/lecons", "ordre=recent"), ("/api/lecons", "task=T-1"),
                           ("/api/recherche", "x=1"), ("/api/recherche", "q=a"), ("/api/specs", "=1")):
            with self.subTest(path=path, brut=brut):
                self.assertIsNotNone(routes.refus(path, _qs(brut)))
                self.assertIsNone(routes.parametres(path, _qs(brut)))

    def test_bornes_limit_offset_400(self) -> None:
        """Jamais OverflowError ; `[0-9]{1,10}` ASCII ; plafond de 10 chiffres (S-01M53E5XBA)."""
        brutes = ["0", "201", "", "-1", str(2 ** 63), "a", "%D9%A3", "%EF%BC%95", "5_0", "%2B5", "+5", " 5",
                  "5%0A", "5.0", "1e3", "00000000001", "99999999999", "%EF%BC%91"]
        for cle in ("limit", "offset"):
            for v in brutes:
                if cle == "offset" and v in ("0", "201"):
                    continue
                with self.subTest(cle=cle, valeur=v):
                    self.assertIsNotNone(routes.refus("/api/specs", _qs(f"{cle}={v}")))
        self.assertIsNotNone(routes.refus("/api/specs", _qs("offset=1000000001")))
        self.assertIsNotNone(routes.refus("/api/lecons", _qs("limit=0")))

    def test_bornes_acceptees(self) -> None:
        for brut in ("limit=1", "limit=200", "limit=0000000025", "offset=0", "offset=1000000000",
                     "offset=0000000000"):
            with self.subTest(brut=brut):
                self.assertIsNone(routes.refus("/api/specs", _qs(brut)))

    def test_defauts_limit_25_offset_0(self) -> None:
        self.assertEqual(routes.parametres("/api/specs", {}), {})
        self.assertEqual(routes.parametres("/api/specs", _qs("limit=0000000007")), {"limit": "0000000007"})

    def test_domaines_et_combinaisons_400(self) -> None:
        """C4 : `autour` + `offset`, `kind` vide, répétition, valeur vide, domaines fermés."""
        for path, brut in (("/api/specs", "autour=S-1&offset=0"), ("/api/lecons", "autour=L-1&offset=5"),
                           ("/api/specs", "kind=plan,"), ("/api/specs", "kind=,plan"), ("/api/specs", "kind=,"),
                           ("/api/specs", "limit=2&limit=3"), ("/api/specs", "task=a&task=b"),
                           ("/api/specs", "q="), ("/api/specs", "task="), ("/api/specs", "q"),
                           ("/api/specs", "dernier=0"), ("/api/specs", "dernier=true"), ("/api/specs", "avec=verdict"),
                           ("/api/specs", "ordre=x"), ("/api/specs", "ordre=RECENT"),
                           ("/api/lecons", "category=x"), ("/api/lecons", "category=Lesson"),
                           ("/api/lecons", "status=active"), ("/api/lecons", "status=archived&status=archived")):
            with self.subTest(path=path, brut=brut):
                self.assertIsNotNone(routes.refus(path, _qs(brut)))

    def test_dans_la_grammaire(self) -> None:
        for path, brut in (("/api/specs", "task=T-1&kind=plan,verdict&dernier=1&avec=plan&ordre=store&q=a&limit=5"),
                           ("/api/specs", "autour=S-1&limit=5"), ("/api/lecons", "category=lesson&status=archived"),
                           ("/api/lecons", "q=%25&autour=L-1"), ("/api/recherche", "")):
            with self.subTest(path=path, brut=brut):
                self.assertIsNone(routes.refus(path, _qs(brut)))

    def test_variante_du_contrat(self) -> None:
        self.assertEqual([routes.variante(_qs(b)) for b in ("", "contrat=1", "contrat=2")], [1, 1, 2])
        for brut in ("contrat=3", "contrat=abc", "contrat=", "contrat", "contrat=1&contrat=2", "x=1",
                     "contrat=2&x=1", "contrat=02", "contrat=%EF%BC%92"):
            with self.subTest(brut=brut):
                self.assertIsNone(routes.variante(_qs(brut)))

    def test_alleger_variante_2(self) -> None:
        snap = {"specs": 1, "ledger": 2, "journaux": {"empreinte": "e"}, "board": 3}
        self.assertEqual(routes.alleger(snap, 2), {"journaux": {"empreinte": "e"}, "board": 3})
        self.assertIs(routes.alleger(snap, 1), snap)
        self.assertEqual(snap["specs"], 1, "le corps du contrat 1 n'est jamais muté")


# ---------------------------------------------------------------------------
# Les vecteurs de E et de G, base ET direct.
# ---------------------------------------------------------------------------

class VecteursTests(RoutesCase):
    def test_vecteurs_de_G_base_et_direct(self) -> None:
        """« LOT G × D — parité », porté : mêmes magasins, mêmes attentes écrites à la main."""
        self.ecrire(G_SPECS, G_LEDGER)
        self.rafraichir()
        for path, paires, ids, extra, regle in G_CASES:
            with self.subTest(regle=regle, path=path, paires=paires):
                corps = self.deux(path, paires)
                if ids is not None:
                    self.assertEqual(_ids(corps["entries"]), ids)
                for cle, valeur in extra.items():
                    self.assertEqual(corps.get(cle), valeur, cle)
                self.assertEqual([(s["nom"], s["statut"]) for s in corps["sources"]],
                                 [("SPECS", "ok"), ("LEDGER", "ok")])
                if "autour" not in dict(paires):
                    self.assertNotIn("rang", corps, "rang/trouve n'existent que sous `autour`")
                    self.assertNotIn("trouve", corps)
        recherche = self.deux("/api/recherche")
        self.assertEqual(_ids(recherche["decisions"]), [gs(10), gs(4), gs(12)])
        self.assertEqual(_ids(recherche["lecons"]), [gl(1), gl(2), gl(3), f"L-{G_ULID_L}"])
        self.assertEqual(recherche["stores"], [{"nom": "SPECS", "statut": "ok", "raison": None},
                                               {"nom": "LEDGER", "statut": "ok", "raison": None}])
        self.assertEqual(sorted(recherche), ["decisions", "empreinte", "lecons", "stores"])

    def test_ordre_recent_et_store(self) -> None:
        """Mutant « ordre inversé », « tri par chaîne » → rouge."""
        self.ecrire(SPECS_R, LEDGER_E)
        self.rafraichir()
        self.assertEqual(_ids(self.deux("/api/specs")["entries"]), RECENT_R)
        self.assertEqual(_ids(self.deux("/api/specs", [("ordre", "recent")])["entries"]), RECENT_R)
        self.assertEqual(_ids(self.deux("/api/specs", [("ordre", "store")])["entries"]), [e["id"] for e in SPECS_R])
        self.assertEqual(_ids(self.deux("/api/lecons")["entries"]), ["L-00000004", "L-00000003", "L-00000001"])

    def test_departage_par_rang_sql_et_direct(self) -> None:
        """S-0012 (rang 4) avant S-12 (rang 5) : même numéro, le store départage (C4) — sur le SQL de la base
        (une table au DDL de A2.1, lignes calculées par les fonctions de la projection) ET sur le tri direct, avec
        les vecteurs BRUTS de E (aucun propriétaire ne les charge, mesuré). Mutant « rang DESC » → rouge."""
        con = sqlite3.connect(":memory:")
        self.addCleanup(con.close)
        for instruction in ep.DDL:
            con.execute(instruction)
        for rang, e in enumerate(SPECS_E):
            tier, num, valeur = ep.rangement(e["id"])
            con.execute("INSERT INTO specs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (e["id"], rang, e["task"], e["kind"], e["date"], tier, num, valeur,
                         ep.plier(ep.foin("SPECS", e)), "sha", json.dumps(e)))
        vide = {"task": None, "kinds": None, "avec": None, "dernier": None, "q": None, "store": None}
        self.assertEqual([i for (i,) in con.execute(routes._SQL_SPECS, vide)], RECENT_E)
        self.assertEqual([i for (i,) in con.execute(routes._SQL_SPECS, dict(vide, store="1"))],
                         [e["id"] for e in SPECS_E])
        porte = dict(vide, kinds=json.dumps(["plan", "verdict", "decision"]), avec="plan", dernier="1")
        self.assertEqual([i for (i,) in con.execute(routes._SQL_SPECS, porte)], GATE_E)
        lignes = routes._lignes("SPECS", SPECS_E)
        self.assertEqual([ligne.ident for ligne in routes._recentes(lignes)], RECENT_E)
        p = {"kind": "plan,verdict,decision", "dernier": "1", "avec": "plan"}
        self.assertEqual([ligne.ident for ligne in routes._filtrer_specs(lignes, p)], GATE_E)

    def test_ordre_absent_egal_recent(self) -> None:
        """C8 : mutant « défaut store » → rouge."""
        self.ecrire(SPECS_R, LEDGER_E)
        self.rafraichir()
        self.assertEqual(self.deux("/api/specs"), self.deux("/api/specs", [("ordre", "recent")]))
        self.assertNotEqual(_ids(self.deux("/api/specs")["entries"]),
                            _ids(self.deux("/api/specs", [("ordre", "store")])["entries"]))

    def test_rangement_vecteurs_A2(self) -> None:
        """Les vecteurs de A2.1, par la fonction PARTAGÉE avec la projection (pas une copie)."""
        self.assertIs(routes._etat.rangement, ep.rangement)
        self.assertEqual(ep.rangement("S-" + G_ULID), (2, None, G_ULID))
        self.assertEqual(ep.rangement("S-00000123"), (1, 123, ""))
        self.assertEqual(ep.rangement("T-12"), (1, 12, ""))
        self.assertEqual(ep.rangement("libre"), (0, None, "libre"))
        self.assertEqual(ep.plier("Élève ÇA S-12"), "eleve ca s-12")

    def test_q_litteral_et_replie(self) -> None:
        """C4 : `a_b` ne trouve pas `axb`, `100%` ne trouve pas `1000` (mutant « LIKE ») ; accents et casse
        repliés (mutant « sans NFD »)."""
        self.ecrire(SPECS_R, LEDGER_E)
        self.rafraichir()
        self.assertEqual(_ids(self.deux("/api/specs", [("q", "a_b")])["entries"]), ["S-9"])
        self.assertEqual(_ids(self.deux("/api/specs", [("q", "100%")])["entries"]), [ULID_E])
        self.assertEqual(_ids(self.deux("/api/specs", [("q", "ÉLÈVE")])["entries"]), ["S-00000010"])
        self.assertEqual(_ids(self.deux("/api/specs", [("q", "DÉCISION")])["entries"]), ["S-00000012", "S-00000005"])
        self.assertEqual(self.deux("/api/specs", [("q", "́")])["total"], len(SPECS_R), "q replié vide = tout")

    def test_q_champs_par_route(self) -> None:
        """Une valeur du seul `text` d'une entrée SPECS n'est PAS trouvée (mutant « q sur un champ de trop ») ;
        LEDGER lit text, text_preview, tags, related."""
        self.ecrire(SPECS_R, LEDGER_E)
        self.rafraichir()
        self.assertEqual(self.deux("/api/specs", [("q", "texte-seul-xyz")])["total"], 0)
        self.assertEqual(_ids(self.deux("/api/specs", [("q", "t-00000003")])["entries"]), ["S-00000014"])
        for q, attendu in (("corps-unique", "L-00000001"), ("aperçu-seul", "L-00000003"), ("porte", "L-00000001"),
                           ("t-00000009", "L-00000004")):
            with self.subTest(q=q):
                self.assertEqual(_ids(self.deux("/api/lecons", [("q", q)])["entries"]), [attendu])

    def test_dernier_avec_plan_egale_gateCandidates(self) -> None:
        """L'URL unique de F : la dernière par tâche×kind, tâches à plan seules (T-3 exclue) — l'oracle de E."""
        self.ecrire(SPECS_R, LEDGER_E)
        self.rafraichir()
        corps = self.deux("/api/specs", [("kind", "plan,verdict,decision"), ("dernier", "1"), ("avec", "plan"),
                                         ("limit", "200")])
        self.assertEqual(_ids(corps["entries"]), GATE_R)
        self.assertEqual(_ids(self.deux("/api/specs", [("kind", "plan,verdict")])["entries"]),
                         [ULID_E, "S-00000014", "S-00000013", "S-00000011", "S-00000010", "S-9"])

    def test_avec_lit_le_store_entier(self) -> None:
        """S-01M53C814Z (3) : T-2 a un plan, le filtre `kind=verdict` ne le voit pas — mutant « avec sur les lignes
        déjà filtrées » → liste vide → rouge."""
        self.ecrire(SPECS_R, LEDGER_E)
        self.rafraichir()
        corps = self.deux("/api/specs", [("task", "T-00000002"), ("kind", "verdict"), ("avec", "plan")])
        self.assertEqual(_ids(corps["entries"]), ["S-00000013"])
        self.assertEqual(self.deux("/api/specs", [("task", "T-00000003"), ("avec", "plan")])["total"], 0)

    def test_ordre_des_filtres_dernier_avant_q(self) -> None:
        """task → kind → avec → dernier → q : le dernier plan de T-1 (ULID) ne porte pas « élève » ; un `q` appliqué
        AVANT `dernier` rendrait S-00000010 — rouge."""
        self.ecrire(SPECS_R, LEDGER_E)
        self.rafraichir()
        corps = self.deux("/api/specs", [("task", "T-00000001"), ("kind", "plan"), ("dernier", "1"), ("q", "eleve")])
        self.assertEqual((corps["total"], _ids(corps["entries"])), (0, []))
        corps = self.deux("/api/specs", [("task", "T-00000001"), ("kind", "plan"), ("dernier", "1"), ("q", "100%")])
        self.assertEqual(_ids(corps["entries"]), [ULID_E])

    def test_lecons_archivees_hors_liste_et_counts(self) -> None:
        """Mutant « archivées listées » → rouge ; `counts` entiers, sur le store entier, insensibles à q/category."""
        self.ecrire(SPECS_R, LEDGER_E)
        self.rafraichir()
        attendu = {"all": 3, "constraint": 1, "decision": 1, "lesson": 1, "archived": 1}
        corps = self.deux("/api/lecons")
        self.assertNotIn("L-00000002", _ids(corps["entries"]))
        self.assertEqual(list(corps["counts"]), COUNTS_CLES)
        self.assertEqual(corps["counts"], attendu)
        self.assertTrue(all(type(v) is int for v in corps["counts"].values()), corps["counts"])
        for paires in ([("q", "porte"), ("category", "constraint")], [("status", "archived")], [("q", "zzz")]):
            with self.subTest(paires=paires):
                self.assertEqual(self.deux("/api/lecons", paires)["counts"], attendu)
        self.assertEqual(_ids(self.deux("/api/lecons", [("status", "archived")])["entries"]), ["L-00000002"])
        self.assertEqual(_ids(self.deux("/api/lecons", [("category", "lesson")])["entries"]), ["L-00000004"])
        self.assertNotIn("counts", self.deux("/api/specs"))

    def test_entries_brutes(self) -> None:
        """Les champs du store intacts, `files` et un champ inconnu compris : l'entrée telle que la rend son
        propriétaire."""
        specs = [dict(SPECS_R[0], champ_neuf={"x": [1, 2.5, None]})] + SPECS_R[1:]
        self.ecrire(specs, LEDGER_E)
        self.rafraichir()
        brutes = ep._specs.load(self.racine)["entries"]
        corps = self.deux("/api/specs", [("ordre", "store"), ("limit", "200")])
        self.assertEqual(corps["entries"], brutes)
        self.assertEqual(corps["entries"][0]["files"], ["a.py"])
        self.assertEqual(corps["entries"][0]["champ_neuf"], {"x": [1, 2.5, None]})

    def test_autour_rend_la_page(self) -> None:
        self.ecrire(SPECS_R, LEDGER_E)
        self.rafraichir()
        corps = self.deux("/api/lecons", [("autour", "L-00000001"), ("limit", "2")])
        self.assertEqual((corps["offset"], corps["rang"], corps["trouve"], _ids(corps["entries"])),
                         (2, 2, True, ["L-00000001"]))
        perdu = self.deux("/api/lecons", [("autour", "L-00000002")])
        self.assertEqual((perdu["trouve"], perdu["rang"], perdu["offset"]), (False, None, 0))
        corps = self.deux("/api/specs", [("autour", "S-00000005"), ("limit", "3")])
        self.assertEqual((corps["offset"], corps["rang"], _ids(corps["entries"])), (6, 7, ["S-9", "S-00000005"]))

    def test_pages_disjointes(self) -> None:
        self.ecrire([_g_spec(gs(n), n % 4, "plan" if n % 3 else "verdict", f"t {n}") for n in range(1, 58)], LEDGER_E)
        self.rafraichir()
        tout = _ids(self.deux("/api/specs", [("limit", "200")])["entries"])
        vus: list[str] = []
        for decalage in range(0, 57, 7):
            vus += _ids(self.deux("/api/specs", [("limit", "7"), ("offset", str(decalage))])["entries"])
        self.assertEqual(vus, tout)
        self.assertEqual(len(set(vus)), 57)


# ---------------------------------------------------------------------------
# Base périmée, source dégradée, requête qui lève : toujours la lecture directe, jamais un 500.
# ---------------------------------------------------------------------------

class ReplisTests(RoutesCase):
    def test_direct_si_perimee(self) -> None:
        """Un journal modifié après `rafraichir` : `lire` rend None, la route lit les journaux — données fraîches."""
        self.ecrire(SPECS_R, LEDGER_E)
        self.rafraichir()
        self.assertEqual(self.corps("/api/specs", base=True)["source"], "base")
        self.ecrire(SPECS_R + [{"id": "S-00000099", "task": "T-00000009", "kind": "plan", "title": "neuve",
                                "date": "2026-10-17"}], LEDGER_E)
        corps = self.corps("/api/specs", base=True)
        self.assertEqual(corps["source"], "direct")
        self.assertEqual(_ids(corps["entries"])[:2], [ULID_E, "S-00000099"])
        self.assertEqual(corps["total"], len(SPECS_R) + 1)

    def test_source_degradee_parite(self) -> None:
        """C1 : LEDGER illisible après un premier rafraîchissement — la base garde ses lignes d'avant, `lire` rend
        None, les routes servent la lecture directe : la page de LEDGER est vide et le DIT, SPECS reste servie.
        Mutant « tables intactes servies » → les leçons d'avant reviennent → rouge."""
        self.ecrire(SPECS_R, LEDGER_E)
        self.rafraichir()
        chemin = ep._ledger.store_path(self.racine)
        chemin.write_bytes(b"{ illisible")
        self._dater(chemin)
        self.assertEqual(ep.rafraichir(self.racine)["LEDGER"], "degraded")
        for path in ("/api/specs", "/api/lecons", "/api/recherche"):
            with self.subTest(path=path):
                en_base, en_direct = self.corps(path, base=True), self.corps(path, base=False)
                self.assertEqual(en_base, en_direct)
        lecons = self.corps("/api/lecons", base=True)
        self.assertEqual((lecons["source"], lecons["entries"], lecons["total"]), ("direct", [], 0))
        self.assertNotIn("counts", lecons)
        self.assertEqual([(s["nom"], s["statut"]) for s in lecons["sources"]], [("SPECS", "ok"), ("LEDGER", "degraded")])
        self.assertTrue(lecons["sources"][1]["raison"])
        self.assertEqual(_ids(self.corps("/api/specs", base=True)["entries"]), RECENT_R)
        self.assertEqual(self.corps("/api/recherche", base=True)["lecons"], [])

    def test_requete_base_qui_leve_direct(self) -> None:
        """C8 : une requête base qui lève — y compris une classe que rien n'attend — rend la lecture directe."""
        self.ecrire(SPECS_R, LEDGER_E)
        self.rafraichir()
        attendu = self.corps("/api/specs", base=False)
        for exc in (sqlite3.OperationalError("no such column: pli"), sqlite3.DatabaseError("malformed"),
                    RuntimeError("inattendue"), KeyError("SPECS")):
            with self.subTest(exc=type(exc).__name__), mock.patch.object(routes, "_depuis_base", side_effect=exc), \
                    self.assertLogs(routes._LOG, level="WARNING"):
                self.assertEqual(self.corps("/api/specs", base=True), attendu)

    def test_la_connexion_est_fermee(self) -> None:
        """La connexion de `lire` revient en transaction de lecture : la route la FERME, base lue ou non."""
        self.ecrire(SPECS_R, LEDGER_E)
        self.rafraichir()
        vues: list[Any] = []
        vrai_lire = ep.lire

        def espion(racine: Any) -> Any:
            con = vrai_lire(racine)
            vues.append(con)
            return con
        with mock.patch.object(routes._etat, "lire", espion):
            self.corps("/api/specs", base=True)
            with mock.patch.object(routes, "_depuis_base", side_effect=RuntimeError("x")), \
                    self.assertLogs(routes._LOG, level="WARNING"):
                self.corps("/api/lecons", base=True)
        self.assertEqual(len(vues), 2)
        for con in vues:
            with self.assertRaises(sqlite3.ProgrammingError):
                con.execute("SELECT 1")


class PariteReelleTests(RoutesCase):
    """parite_base_direct_reelle : les journaux RÉELS du dépôt, copiés ; chaque route × chaque paramètre."""

    def copier_les_vrais_magasins(self) -> None:
        for source in (ep._specs.store_path(ROOT), ep._specs.journal_store_path(ROOT), ep._ledger.store_path(ROOT)):
            if source.is_file():
                cible = self.racine / source.relative_to(ROOT)
                cible.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, cible)
        dossier = ep._ledger.entries_dir(ROOT)
        if dossier.is_dir():
            shutil.copytree(dossier, self.racine / dossier.relative_to(ROOT))

    def test_borne_5_mo_de_recherche_sur_les_journaux_reels(self) -> None:
        """Avis 5, le FIL de la décision S-01M530QPV2 (a) : le corpus de /api/recherche des journaux RÉELS du dépôt
        (lus en place, en direct) reste sous ~5 Mo bruts ; au-delà ce banc ROUGIT et le plan se reprend (paginer la
        palette). Mesuré au lot D : 2 097 805 octets."""
        self.assertEqual(routes.RECHERCHE_BORNE_OCTETS, 5_000_000)
        os.environ["AGENTS_ETAT_DB"] = str(self.absente)
        corps = routes.corps_route("/api/recherche", {}, ROOT, empreinte="e")
        self.assertEqual([s["statut"] for s in corps["stores"]], ["ok", "ok"], "journaux réels illisibles")
        taille = len(routes._transport.serialiser(corps))
        self.assertGreater(taille, 10 ** 6, "le corpus réel n'a pas été lu — le fil serait vide")
        self.assertLessEqual(taille, routes.RECHERCHE_BORNE_OCTETS,
                             f"/api/recherche = {taille} octets bruts > borne S-01M530QPV2 (a) : replanifier")

    def test_parite_base_direct_reelle(self) -> None:
        self.copier_les_vrais_magasins()
        specs = ep._specs.load(self.racine)["entries"]
        ledger = ep._ledger.load(self.racine)["entries"]
        self.assertGreater(len(specs), 100, "les journaux réels n'ont pas été copiés")
        self.assertGreater(len(ledger), 10)
        self.rafraichir()
        taches: dict[str, int] = {}
        for e in specs:
            taches[e.get("task")] = taches.get(e.get("task"), 0) + 1
        tache = max(taches, key=lambda t: taches[t])
        kinds: dict[str, int] = {}
        for e in specs:
            kinds[e.get("kind")] = kinds.get(e.get("kind"), 0) + 1
        k1, k2 = sorted(kinds, key=lambda k: -kinds[k])[:2]
        milieu = sorted(specs, key=lambda e: ep.rangement(e["id"]), reverse=True)[len(specs) // 2]["id"]
        active = next(e["id"] for e in reversed(ledger) if e.get("status") != "archived")
        cas: list[tuple[str, list[tuple[str, str]]]] = [
            ("/api/specs", []), ("/api/specs", [("limit", "200"), ("offset", "25")]),
            ("/api/specs", [("task", tache), ("ordre", "store"), ("limit", "200")]),
            ("/api/specs", [("kind", f"{k1},{k2}"), ("limit", "50"), ("offset", "50")]),
            ("/api/specs", [("kind", "plan,verdict,decision"), ("dernier", "1"), ("avec", "plan"), ("limit", "200")]),
            ("/api/specs", [("kind", "plan,verdict,decision"), ("dernier", "1"), ("avec", "plan"), ("limit", "200"),
                            ("offset", "200")]),
            ("/api/specs", [("q", "plan")]), ("/api/specs", [("q", "é"), ("ordre", "store")]),
            ("/api/specs", [("q", "T-0"), ("limit", "200")]), ("/api/specs", [("autour", milieu)]),
            ("/api/specs", [("task", tache), ("dernier", "1")]), ("/api/specs", [("offset", "1000000000")]),
            ("/api/lecons", []), ("/api/lecons", [("status", "archived"), ("limit", "200")]),
            ("/api/lecons", [("category", "constraint"), ("limit", "200")]),
            ("/api/lecons", [("category", "lesson"), ("q", "porte")]), ("/api/lecons", [("q", "é")]),
            ("/api/lecons", [("autour", active), ("limit", "10")]), ("/api/recherche", []),
        ]
        for path, paires in cas:
            with self.subTest(path=path, paires=paires):
                self.deux(path, paires)
        recherche = self.corps("/api/recherche", base=False)
        self.assertEqual(_ids(recherche["decisions"]), [e["id"] for e in specs if e.get("kind") == "decision"])
        self.assertEqual(_ids(recherche["lecons"]), [e["id"] for e in ledger if e.get("status") != "archived"])
        with mock.patch.object(routes, "_en_direct", side_effect=AssertionError("repli direct MUET")):
            self.corps("/api/recherche", base=True)
        # toutes les leçons actives, page à page, sans trou ni doublon
        total, vus = self.corps("/api/lecons", base=True)["total"], []
        for decalage in range(0, total, 50):
            vus += _ids(self.corps("/api/lecons", [("limit", "50"), ("offset", str(decalage))], base=True)["entries"])
        premiere = _ids(self.corps("/api/lecons", [("limit", "200")], base=True)["entries"])
        self.assertEqual(vus[:len(premiere)], premiere)
        self.assertEqual(len(vus), len(set(vus)))
        self.assertEqual(sorted(vus), sorted(e["id"] for e in ledger if e.get("status") != "archived"))


# ---------------------------------------------------------------------------
# Le vrai serveur : branchement, en-têtes, ETag, contrat du snapshot.
# ---------------------------------------------------------------------------

class ServeurTests(RoutesCase):
    def setUp(self) -> None:
        super().setUp()
        self.ecrire(G_SPECS, G_LEDGER)
        self.httpd, self.port, self.jeton = self.serveur()

    def test_get_reel_par_route(self) -> None:
        """Mutant « elif retiré » → 404 → rouge. Sans jeton : 401 ; voisins : 404 (table fermée)."""
        for url, cle in (("/api/specs?limit=2", "entries"), ("/api/lecons", "counts"), ("/api/recherche", "decisions")):
            with self.subTest(url=url):
                statut, corps, h = self.get_json(self.port, url, self.jeton)
                self.assertEqual(statut, 200)
                self.assertIn(cle, corps)
                self.assertEqual(h["content-type"], "application/json")
                self.assertEqual(self.get(self.port, url, None)[0], 401)
        for url in ("/api/specs/", "/api/Specs", "/api/lecon", "/api/recherche/x", "/api/specs/S-1"):
            with self.subTest(url=url):
                self.assertEqual(self.get(self.port, url, self.jeton)[0], 404)

    def test_vecteurs_de_G_par_le_serveur(self) -> None:
        """Le test « LOT G × D — parité » joue le serveur en sous-processus ; ici, le même, en direct puis en base."""
        for base in (False, True):
            if base:
                self.rafraichir()
            else:
                os.environ["AGENTS_ETAT_DB"] = str(self.absente)
            for path, paires, ids, extra, regle in G_CASES:
                with self.subTest(base=base, regle=regle):
                    statut, corps, _h = self.get_json(self.port, _url(path, paires), self.jeton)
                    self.assertEqual(statut, 200)
                    self.assertEqual(corps["source"], "base" if base else "direct")
                    if ids is not None:
                        self.assertEqual(_ids(corps["entries"]), ids)
                    for cle, valeur in extra.items():
                        self.assertEqual(corps.get(cle), valeur, cle)
            for path, paires in G_REFUS + [("/api/snapshot", [("contrat", "3")]),
                                           ("/api/snapshot", [("contrat", "abc")])]:
                with self.subTest(base=base, refus=(path, paires)):
                    statut, corps, h = self.get_json(self.port, _url(path, paires), self.jeton)
                    self.assertEqual((statut, corps), (400, {"error": "bad_request"}))
                    self.assertNotIn("etag", h)

    def test_entetes(self) -> None:
        for url in ("/api/specs", "/api/lecons", "/api/recherche"):
            with self.subTest(url=url):
                _s, _o, h = self.get(self.port, url, self.jeton)
                self.assertEqual(h.get("cache-control"), "no-store")
                self.assertEqual(h.get("x-content-type-options"), "nosniff")
                self.assertEqual(h.get("referrer-policy"), "no-referrer")
                self.assertEqual(h.get("vary"), "Accept-Encoding")
                self.assertTrue(h.get("etag", "").startswith('W/"'))
                self.assertFalse([k for k in h if k.startswith("access-control-")], h)

    def test_gzip_au_client_qui_le_nomme(self) -> None:
        _s, brut, h = self.get(self.port, "/api/recherche", self.jeton)
        _s, zippe, hz = self.get(self.port, "/api/recherche", self.jeton, Accept_Encoding="gzip")
        self.assertNotIn("content-encoding", h)
        self.assertEqual(hz.get("content-encoding"), "gzip")
        self.assertEqual(gzip.decompress(zippe), brut)
        self.assertEqual(hz["etag"], h["etag"], "un ETag pour les deux codages")
        _s, refuse, hr = self.get(self.port, "/api/recherche", self.jeton, Accept_Encoding="gzip;q=0, *")
        self.assertNotIn("content-encoding", hr)

    def test_memes_sources_deux_requetes_deux_etag_et_304(self) -> None:
        """Mutant « ETag sans requête » ou « ETag sans les sources » → rouge."""
        _s, _o, h2 = self.get(self.port, "/api/specs?limit=2", self.jeton)
        _s, _o, h3 = self.get(self.port, "/api/specs?limit=3", self.jeton)
        self.assertNotEqual(h2["etag"], h3["etag"])
        self.assertEqual(self.get(self.port, "/api/specs?limit=2", self.jeton)[2]["etag"], h2["etag"])
        statut, octets, h = self.get(self.port, "/api/specs?limit=2", self.jeton, If_None_Match=h2["etag"])
        self.assertEqual((statut, octets), (304, b""))
        self.assertEqual((h["etag"], h["cache-control"]), (h2["etag"], "no-store"))
        self.assertEqual(self.get(self.port, "/api/specs?limit=3", self.jeton, If_None_Match=h2["etag"])[0], 200)
        self.ecrire(G_SPECS[1:], G_LEDGER)
        statut, _o, h = self.get(self.port, "/api/specs?limit=2", self.jeton, If_None_Match=h2["etag"])
        self.assertEqual(statut, 200)
        self.assertNotEqual(h["etag"], h2["etag"])

    def test_degradee_sans_etag(self) -> None:
        """Une panne de lecture passagère sans changement de fichier ne doit jamais être revalidée en 304 : une
        réponse dont une source n'est pas `ok` ne porte pas d'ETag. Mutant « ETag toujours » → rouge."""
        chemin = ep._specs.store_path(self.racine)
        chemin.write_bytes(b"{ illisible")
        self._dater(chemin)
        for url, etag in (("/api/specs", False), ("/api/lecons", True), ("/api/recherche", False)):
            with self.subTest(url=url):
                statut, corps, h = self.get_json(self.port, url, self.jeton)
                self.assertEqual(statut, 200)
                self.assertEqual("etag" in h, etag)
                lignes = corps.get("sources") or corps.get("stores")
                self.assertEqual(lignes[0]["statut"], "degraded")
        statut, corps, _h = self.get_json(self.port, "/api/specs?limit=7", self.jeton)
        self.assertEqual((corps["entries"], corps["total"], corps["offset"], corps["limit"]), ([], 0, 0, 25))

    def test_la_panne_de_l_autre_journal_garde_le_304(self) -> None:
        """Avis 1 : LEDGER illisible, /api/specs (qui ne lit que SPECS) garde son ETag ET son 304 ; /api/lecons et
        /api/recherche, qui lisent LEDGER, partent sans. Mutant « saine sur toutes les sources » → rouge."""
        chemin = ep._ledger.store_path(self.racine)
        chemin.write_bytes(b"{ illisible")
        self._dater(chemin)
        statut, corps, h = self.get_json(self.port, "/api/specs?limit=2", self.jeton)
        self.assertEqual((statut, [s["statut"] for s in corps["sources"]]), (200, ["ok", "degraded"]))
        self.assertIn("etag", h)
        self.assertEqual(self.get(self.port, "/api/specs?limit=2", self.jeton, If_None_Match=h["etag"])[0], 304)
        for url in ("/api/lecons", "/api/recherche"):
            with self.subTest(url=url):
                self.assertNotIn("etag", self.get(self.port, url, self.jeton)[2])

    def test_empreinte_indisponible_le_snapshot_repond(self) -> None:
        """Avis 2 : `empreinte_sources` qui lève (dashboard.py, `build_snapshot` et `avant_cle`, deux contrats) →
        /api/snapshot 200 quand même, `journaux.empreinte` = la constante ; les routes 200 sans ETag. Mutant
        « try retiré » → la connexion tombe → rouge."""
        mod = dashboard._routes_mod
        with mock.patch.object(mod._etat, "empreinte_sources", side_effect=PermissionError("refusé")), \
                self.assertLogs(mod._LOG, level="WARNING"):
            for url in ("/api/snapshot", "/api/snapshot?contrat=2"):
                with self.subTest(url=url):
                    statut, corps, _h = self.get_json(self.port, url, self.jeton)
                    self.assertEqual((statut, corps["journaux"]), (200, {"empreinte": "indisponible"}))
            self.assertEqual(dashboard.build_snapshot(self.racine)["journaux"]["empreinte"], "indisponible")
            for url in ("/api/specs", "/api/recherche"):
                with self.subTest(url=url):
                    statut, corps, h = self.get_json(self.port, url, self.jeton, If_None_Match="*")
                    self.assertEqual(statut, 200)
                    self.assertNotIn("etag", h)
            self.assertEqual(corps["empreinte"], "indisponible")
        self.assertNotEqual(self.get_json(self.port, "/api/snapshot", self.jeton)[1]["journaux"]["empreinte"],
                            "indisponible")

    def test_raison_sans_chemin_absolu(self) -> None:
        """Avis 3 : la raison d'un journal illisible en direct ne porte pas la racine absolue (le message du
        propriétaire, lui, la porte — témoin non vide)."""
        chemin = ep._specs.store_path(self.racine)
        chemin.write_bytes(b"{ illisible")
        self._dater(chemin)
        with self.assertRaises(Exception) as brut:
            ep._specs.load(self.racine)
        self.assertIn(str(self.racine), str(brut.exception), "le témoin serait vide")
        raison = self.get_json(self.port, "/api/specs", self.jeton)[1]["sources"][0]["raison"]
        self.assertTrue(raison.startswith(type(brut.exception).__name__ + ": "), raison)
        self.assertNotIn(str(self.tmp), raison)
        lien = self.tmp / "lien"
        lien.symlink_to(self.racine)
        for message in (f"{self.racine}/a", f"{lien}/b", f"x {self.racine.resolve()} y {lien} z"):
            with self.subTest(message=message):
                self.assertNotIn(str(self.tmp), routes._raison(ValueError(message), lien))

        class Alias:  # la forme courte est une SOUS-CHAÎNE de la résolue (macOS : /var → /private/var)
            def resolve(self) -> Path:
                return Path("/private/var/x")

            def __str__(self) -> str:
                return "/var/x"
        self.assertEqual(routes._raison(ValueError("/private/var/x/a.json et /var/x/b"), Alias()),
                         "ValueError: ./a.json et ./b", "la forme longue d'abord, sinon « /private./a.json »")

    def test_recherche_memorisee_par_etag(self) -> None:
        """Avis 4 : sans changement, un GET de /api/recherche ne reconstruit rien (identité ET gzip) ; un journal
        qui bouge reconstruit ; une réponse non saine n'est jamais mémorisée. Mutant « mémo contourné » → rouge."""
        mod = dashboard._routes_mod
        memo = self.httpd.recherche_memo
        self.assertIsInstance(memo, mod.MemoRecherche)
        with mock.patch.object(mod, "corps_route", wraps=mod.corps_route) as espion:
            _s, un, h1 = self.get(self.port, "/api/recherche", self.jeton)
            _s, deux, h2 = self.get(self.port, "/api/recherche", self.jeton)
            _s, zippe, _h = self.get(self.port, "/api/recherche", self.jeton, Accept_Encoding="gzip")
            self.assertEqual((espion.call_count, memo.constructions), (1, 1))
            self.assertEqual((un, h1["etag"]), (deux, h2["etag"]))
            self.assertEqual(gzip.decompress(zippe), un)
            self.ecrire(G_SPECS[1:], G_LEDGER)
            _s, trois, h3 = self.get(self.port, "/api/recherche", self.jeton)
            self.assertEqual((espion.call_count, memo.constructions), (2, 2))
            self.assertNotEqual(h3["etag"], h1["etag"])
            chemin = ep._ledger.store_path(self.racine)
            chemin.write_bytes(b"{ illisible")
            self._dater(chemin)
            self.get(self.port, "/api/recherche", self.jeton)
            self.get(self.port, "/api/recherche", self.jeton)
            self.assertEqual((espion.call_count, memo.constructions), (4, 2))

    def test_borne_journalisee(self) -> None:
        """Avis 5 (côté serveur) : un corpus au-delà de la borne le DIT au journal du démon, et reste servi."""
        mod = dashboard._routes_mod
        with mock.patch.object(mod, "RECHERCHE_BORNE_OCTETS", 100), self.assertLogs(mod._LOG, level="WARNING") as j:
            self.assertEqual(self.get(self.port, "/api/recherche", self.jeton)[0], 200)
        self.assertIn("S-01M530QPV2", "".join(j.output))

    def test_authorization_non_ascii_401(self) -> None:
        """Avis 6 (dashboard.py `_check_token`, préexistant) : un `Authorization` non ASCII rend 401, jamais un
        TypeError de `compare_digest` (connexion coupée). Mutant « comparaison de str » → rouge."""
        for url in ("/api/snapshot", "/api/specs", "/api/ping"):
            for valeur in ("Bearer \xe9t\xe9", "Bearer " + self.jeton[:-1] + "\xe9", b"Bearer \xc3\xa9"):
                with self.subTest(url=url, valeur=valeur):
                    self.assertEqual(self.get(self.port, url, None, Authorization=valeur)[0], 401)
        self.assertEqual(self.get(self.port, "/api/ping", self.jeton)[0], 200)

    def test_etag_code_fige_au_chargement(self) -> None:
        """L'empreinte du code entre dans l'ETag, prise UNE fois au chargement de dashboard.py : mutant « recalculée
        à chaque requête » ou « absente de l'ETag » → rouge."""
        _s, _o, h = self.get(self.port, "/api/specs", self.jeton)
        with mock.patch.object(dashboard, "served_code_fingerprint", return_value="code-sur-disque-neuf"):
            self.assertEqual(self.get(self.port, "/api/specs", self.jeton)[2]["etag"], h["etag"])
        with mock.patch.object(dashboard, "_EMPREINTE_CODE", "code-servi-autre"):
            self.assertNotEqual(self.get(self.port, "/api/specs", self.jeton)[2]["etag"], h["etag"])
        # Pris AU CHARGEMENT : une affectation de module, une seule (l'égalité au disque n'est PAS un invariant —
        # mesuré, un banc du démon réécrit `assets/app.js` à l'identique et son mtime bouge l'empreinte du disque).
        arbre = ast.parse((HERE / "dashboard.py").read_text(encoding="utf-8"))
        poses = [n for n in arbre.body if isinstance(n, ast.Assign)
                 and any(isinstance(c, ast.Name) and c.id == "_EMPREINTE_CODE" for c in n.targets)]
        self.assertEqual([ast.unparse(n.value) for n in poses], ["served_code_fingerprint()"])

    def test_le_code_des_routes_est_servi(self) -> None:
        """`served_code_fingerprint` lit les deux modules neufs : une copie plus vieille se lit STALE."""
        avant = dashboard.served_code_fingerprint()
        for nom in ("dashboard_routes_etat.py", "etat_projection.py"):
            with self.subTest(nom=nom):
                st = (HERE / nom).stat()
                vrai_stat = Path.stat

                def faux_stat(chemin: Path, *a: Any, _nom: str = nom, **k: Any) -> Any:
                    res = vrai_stat(chemin, *a, **k)
                    if chemin.name == _nom:
                        return os.stat_result((res.st_mode, res.st_ino, res.st_dev, res.st_nlink, res.st_uid,
                                               res.st_gid, st.st_size + 1, res.st_atime, res.st_mtime, res.st_ctime))
                    return res
                with mock.patch.object(Path, "stat", faux_stat):
                    self.assertNotEqual(dashboard.served_code_fingerprint(), avant)

    def test_contrat_1_puis_2_puis_1(self) -> None:
        """Mutant « lambda qui ignore la variante » → `specs` dans le contrat 2 → rouge ; une case par variante :
        revenir au 1 ne reconstruit rien."""
        statut, un, _h = self.get_json(self.port, "/api/snapshot", self.jeton)
        self.assertEqual(statut, 200)
        self.assertTrue({"specs", "ledger", "journaux"} <= set(un))
        statut, deux, h2 = self.get_json(self.port, "/api/snapshot?contrat=2", self.jeton)
        self.assertEqual(statut, 200)
        self.assertFalse({"specs", "ledger"} & set(deux))
        self.assertEqual(deux["journaux"], un["journaux"])
        self.assertEqual(set(un) - set(deux), {"specs", "ledger"})
        self.assertIn("x-snapshot-vivant", h2)
        constructions = self.httpd.snapshot_memo.constructions
        statut, encore, _h = self.get_json(self.port, "/api/snapshot?contrat=1", self.jeton)
        self.assertEqual((statut, set(encore)), (200, set(un)))
        self.assertEqual(self.httpd.snapshot_memo.constructions, constructions, "le contrat 1 a été reconstruit")
        for brut in ("contrat=3", "contrat=abc", "contrat=", "x=1", "contrat=1&contrat=2", "contrat=2&x=1"):
            with self.subTest(brut=brut):
                self.assertEqual(self.get_json(self.port, f"/api/snapshot?{brut}", self.jeton)[:2],
                                 (400, {"error": "bad_request"}))

    def test_journaux_empreinte_suit_les_sources(self) -> None:
        """`journaux.empreinte` (deux variantes) = `/api/recherche.empreinte` ; elle suit un changement que voit
        `empreinte_sources` même quand l'empreinte du snapshot ne le voit pas (un chmod) — mutant « avant_cle
        retiré » → le mémo resert l'ancienne → rouge."""
        e1 = self.get_json(self.port, "/api/snapshot", self.jeton)[1]["journaux"]["empreinte"]
        self.assertEqual(self.get_json(self.port, "/api/recherche", self.jeton)[1]["empreinte"], e1)
        self.assertEqual(dashboard.build_snapshot(self.racine)["journaux"]["empreinte"], e1)
        os.chmod(ep._specs.store_path(self.racine), 0o640)
        e2 = self.get_json(self.port, "/api/snapshot?contrat=2", self.jeton)[1]["journaux"]["empreinte"]
        self.assertNotEqual(e2, e1)
        self.assertEqual(self.get_json(self.port, "/api/snapshot", self.jeton)[1]["journaux"]["empreinte"], e2)
        self.assertEqual(self.get_json(self.port, "/api/recherche", self.jeton)[1]["empreinte"], e2)

    def test_livrables_200_304_400_401(self) -> None:
        """B3 : `/api/livrables` est servie par le vrai serveur sans toucher `dashboard.py` (une route de `ROUTES`)
        — 200 et ETag, 304, 400 hors grammaire, 401 sans jeton. Mutant M5 (route hors de `ROUTES`) → 404 → rouge."""
        dossier = self.racine / "docs" / "tasks"
        dossier.mkdir(parents=True)
        (dossier / "T-ABC12-plan.md").write_text("# Plan\n", encoding="utf-8")
        url = "/api/livrables?task=T-ABC12"
        statut, corps, h = self.get_json(self.port, url, self.jeton)
        self.assertEqual((statut, corps["statut"], [d["nom"] for d in corps["documents"]]),
                         (200, "ok", ["T-ABC12-plan.md"]))
        self.assertEqual((h["content-type"], h["cache-control"]), ("application/json", "no-store"))
        self.assertTrue(h["etag"].startswith('W/"'), h)
        self.assertEqual(self.get(self.port, url, self.jeton, If_None_Match=h["etag"])[:2], (304, b""))
        _s, clair, _h = self.get(self.port, url, self.jeton)
        _s, zippe, hz = self.get(self.port, url, self.jeton, Accept_Encoding="gzip")  # mutant « gzip coupé » → rouge
        self.assertEqual((hz.get("content-encoding"), gzip.decompress(zippe), hz["etag"]), ("gzip", clair, h["etag"]))
        for brut in ("", "?task=", "?task=t-abc12", "?task=T-ABC12&task=T-ABC12", "?task=T-ABC12&x=1",
                     "?task=T-ABC%0A"):
            with self.subTest(brut=brut):
                statut, corps, h = self.get_json(self.port, "/api/livrables" + brut, self.jeton)
                self.assertEqual((statut, corps), (400, {"error": "bad_request"}))
                self.assertNotIn("etag", h)
        self.assertEqual(self.get(self.port, url, None)[0], 401)

    def test_m4_base_servie_par_le_vrai_serveur(self) -> None:
        """M4 (S-01M51V3SVN) : base fraîche → `/api/specs?limit=25` 200 ET `source: "base"` ; `?x=1` 400 ; sans
        jeton 401."""
        self.rafraichir()
        statut, corps, _h = self.get_json(self.port, "/api/specs?limit=25", self.jeton)
        self.assertEqual((statut, corps["source"]), (200, "base"))
        self.assertEqual(self.get(self.port, "/api/specs?x=1", self.jeton)[0], 400)
        self.assertEqual(self.get(self.port, "/api/specs?limit=25", None)[0], 401)


# ---------------------------------------------------------------------------
# Lecture seule, et aucun nom de magasin écrit en dur (C3).
# ---------------------------------------------------------------------------

class LectureSeuleTests(unittest.TestCase):
    SOURCE = (HERE / "dashboard_routes_etat.py").read_text(encoding="utf-8")

    def test_lecture_seule_ast(self) -> None:
        """Aucun écrivain : ni `rafraichir`, ni la boucle, ni un SQL qui écrit, ni une écriture de fichier."""
        arbre = ast.parse(self.SOURCE)
        lus = {n.attr for n in ast.walk(arbre) if isinstance(n, ast.Attribute)
               and isinstance(n.value, ast.Name) and n.value.id == "_etat"}
        self.assertLessEqual(lus, {"lire", "empreinte_sources", "rangement", "foin", "plier", "_texte", "SOURCES",
                                   "STATUT_OK", "STATUT_DEGRADE"})
        appels = {n.func.attr for n in ast.walk(arbre) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        self.assertFalse(appels & {"executescript", "executemany", "commit", "write_text", "write_bytes", "unlink",
                                   "mkdir", "rafraichir", "rename", "touch", "chmod"}, appels)
        # `Path.replace(cible)` déplace un fichier (UN argument) ; `str.replace(a, b)` en prend deux.
        self.assertFalse([n for n in ast.walk(arbre) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                          and n.func.attr == "replace" and len(n.args) != 2])
        noms = {n.func.id for n in ast.walk(arbre) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        self.assertNotIn("open", noms)
        sql = [n.value for n in ast.walk(arbre) if isinstance(n, ast.Constant) and isinstance(n.value, str)
               and n.value.lstrip().upper().startswith(("SELECT", "WITH", "INSERT", "UPDATE", "DELETE", "CREATE",
                                                        "DROP", "PRAGMA", "BEGIN", "ATTACH", "REPLACE", "ALTER"))]
        self.assertGreaterEqual(len(sql), 5, "le relevé des requêtes est aveugle")
        for requete in sql:
            self.assertTrue(requete.lstrip().upper().startswith(("SELECT", "WITH")), requete)
            self.assertNotIn(" LIKE ", requete.upper(), "C4 : q par instr, jamais LIKE")

    def test_aucun_nom_de_magasin_c3(self) -> None:
        """Le motif du cliquet `test_lecture_etat_cliquet.py`, relu de son banc : un module neuf hors de sa LISTE."""
        cliquet = _load("_test_routes_cliquet", ROOT / ".agents" / "evals" / "test_lecture_etat_cliquet.py")
        self.assertIsNone(cliquet.MOTIF.search(self.SOURCE))
        self.assertIsNone(cliquet.JOINTURE.search(self.SOURCE))
        self.assertNotIn(".agents/bin/dashboard_routes_etat.py", cliquet.LISTE)


if __name__ == "__main__":
    unittest.main()
