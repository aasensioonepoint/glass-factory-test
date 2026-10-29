"""Témoins du transport de `/api/snapshot` (T-01M4XR9ESWKJ8G545AJBJQNC7Q, E-36 vague 0).

Chaque témoin est accompagné, quand le mandat le nomme, de son MUTANT joué en place (monkeypatch) et
attendu ROUGE : horodatage du spool remis dans la clé canal B, verrou de la construction unique retiré,
case du mémo choisie sans la variante, fichier d'entrée oublié par l'empreinte ; et, depuis le lot A de
T-01M4XMQ1QC : `json.dumps` de la charge entière rétabli dans `gabarit`, ETag tiré aussi des greffes,
borne de l'en-tête vivant ignorée. Un témoin dont le mutant reste vert ne prouverait rien
(CONVENTIONS_python.md : « A test must be able to fail »).
"""
from __future__ import annotations

import contextlib
import dataclasses
import gzip
import hashlib
import http.client
import importlib.util
import json
import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("_banc_transport_dashboard", HERE / "dashboard.py")
dashboard = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = dashboard
_spec.loader.exec_module(dashboard)

transport = dashboard._transport_mod
readers = dashboard._readers_mod
event_store = dashboard._event_store_mod
otel_receiver = dashboard._otel_receiver

_OWN_ID = "own-project-id-transport"
_TS = "2026-07-27T19:58:52Z"
_NOW = datetime.fromisoformat(_TS.replace("Z", "+00:00"))  # dans la rétention : rien ne se replie


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Le même isolement que `test_dashboard._redirect` : aucune entrée du développeur n'est lue."""
    root, events, otel = tmp_path / "project", tmp_path / "events", tmp_path / "otel"
    root.mkdir()
    monkeypatch.setenv("AGENTS_DASHBOARD_PROJECT_ROOT", str(root))
    monkeypatch.setenv("AGENTS_EVENTS_DIR", str(events))
    monkeypatch.setenv("AGENTS_OTEL_DIR", str(otel))
    monkeypatch.setenv("AGENTS_PROJECT_JSON", str(tmp_path / "project.json"))
    monkeypatch.setenv("AGENTS_OTEL_PROJECT_ROOT", str(tmp_path / "own-root"))
    monkeypatch.setenv("AGENTKIT_REGISTRY", str(tmp_path / "registry.json"))
    monkeypatch.setenv("AGENTS_TERM_DIR", str(tmp_path / "term"))
    _identite(tmp_path / "project.json", _OWN_ID)
    otel_receiver._reset_identity_cache_for_tests()
    dashboard._reset_canal_b_cache_for_tests()
    dashboard._reset_canal_a_cache_for_tests()
    readers.reset_cache_for_tests()
    yield {"root": root, "events": events, "otel": otel, "identity": tmp_path / "project.json"}
    dashboard._reset_canal_b_cache_for_tests()
    dashboard._reset_canal_a_cache_for_tests()
    readers.reset_cache_for_tests()


@pytest.fixture
def horloge(monkeypatch):
    """`generated_at` est greffé à chaque envoi et part dans l'en-tête vivant : une horloge pilotée rend
    chaque valeur vivante prévisible, et la fait bouger SANS reconstruire ni changer l'ETag du gabarit."""
    instant = {"iso": "2026-10-15T08:00:00Z"}
    monkeypatch.setattr(dashboard, "_now_iso", lambda: instant["iso"])
    return instant


@pytest.fixture
def serveur(env, horloge):
    httpd, token = dashboard.create_ui_server(project_root=env["root"])
    fil = threading.Thread(target=httpd.serve_forever, daemon=True)
    fil.start()
    try:
        yield httpd, httpd.server_address[1], token
    finally:
        httpd.shutdown()
        httpd.server_close()
        fil.join(timeout=5)


def _identite(path: Path, project_id: str) -> None:
    path.write_text(json.dumps({"project_id": project_id}), encoding="utf-8", newline="\n")


def _metrique(valeur: float, project_id: str = _OWN_ID) -> dict:
    return {"ts": _TS, "kind": "metric", "project_id": project_id, "provenance": project_id,
            "path": "/v1/metrics",
            "body": {"resourceMetrics": [{
                "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "claude-code"}}]},
                "scopeMetrics": [{"metrics": [{"name": "claude_code.cost.usage", "sum": {"dataPoints": [{
                    "attributes": [{"key": "model", "value": {"stringValue": "m"}}],
                    "asDouble": valeur}]}}]}]}]}}


def _ecrire_otel(otel: Path, valeur: float, nom: str = "2026-07-27.1.jsonl") -> Path:
    otel.mkdir(parents=True, exist_ok=True)
    chemin = otel / nom
    with open(chemin, "a", encoding="utf-8", newline="\n") as fichier:
        fichier.write(json.dumps(_metrique(valeur)) + "\n")
    return chemin


def _get(port: int, token: str, entetes: dict | None = None) -> http.client.HTTPResponse:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    try:
        conn.request("GET", "/api/snapshot", headers={"Authorization": f"Bearer {token}", **(entetes or {})})
        resp = conn.getresponse()
        resp.data = resp.read()  # type: ignore[attr-defined]
        return resp
    finally:
        conn.close()


def _compter(monkeypatch, module, nom: str) -> list:
    appels: list = []
    reel = getattr(module, nom)

    def compte(*args, **kwargs):
        appels.append(1)
        return reel(*args, **kwargs)

    monkeypatch.setattr(module, nom, compte)
    return appels


def _mutant_horodatage_du_spool(monkeypatch) -> None:
    """MUTANT : la clé canal B reprend l'empreinte `(nom, mtime, taille)` du spool, quel que soit le statut."""
    monkeypatch.setattr(transport, "part_du_spool",
                        lambda repertoire, statut, motif="*.jsonl": readers.dir_fingerprint(repertoire, motif))


# ---------------------------------------------------------------------------
# ETag / 304 / gzip — HTTP réel sur `UIHTTPServer` (ThreadingMixIn).
# ---------------------------------------------------------------------------

def test_etag_stable_au_repos_puis_304(serveur):
    httpd, port, token = serveur
    premier, second = _get(port, token), _get(port, token)
    assert premier.status == second.status == 200
    assert premier.getheader("Cache-Control") == "private, no-cache" == transport.CACHE_CONTROL
    etag = premier.getheader("ETag")
    assert etag and etag.startswith('W/"') and second.getheader("ETag") == etag, "ETag instable au repos"
    assert premier.data == second.data, "deux GET au repos doivent servir les mêmes octets"
    revalide = _get(port, token, {"If-None-Match": etag})
    assert revalide.status == 304 and revalide.data == b""
    assert revalide.getheader("ETag") == etag and revalide.getheader("Vary") == "Accept-Encoding"
    assert revalide.getheader("Cache-Control") == transport.CACHE_CONTROL
    assert revalide.getheader("X-Content-Type-Options") == "nosniff"
    assert revalide.getheader("Referrer-Policy") == "no-referrer"
    assert not [h for h, _v in revalide.getheaders() if h.lower().startswith("access-control-")]
    assert _get(port, token, {"If-None-Match": 'W/"autre"'}).status == 200, "un ETag étranger reçoit 200"
    assert httpd.snapshot_memo.constructions == 1, "le repos a reconstruit le corps"


def test_une_ligne_canal_b_neuve_donne_200_et_un_etag_neuf(serveur, env):
    _httpd, port, token = serveur
    with event_store.open_store(create=True) as store:  # tenu ouvert, comme le démon le tient
        _ecrire_otel(env["otel"], 1.0)
        store.ingest_once(now=_NOW)
        avant = _get(port, token)
        etag = avant.getheader("ETag")
        assert json.loads(avant.data)["canal_b"]["rows_read"] == 1
        _ecrire_otel(env["otel"], 2.0, "2026-07-27.2.jsonl")
        store.ingest_once(now=_NOW + timedelta(seconds=5))
        for fichier in env["otel"].glob("*.jsonl"):
            fichier.unlink()  # l'état drainé : plus aucune entrée ne bouge entre les deux GET qui suivent
        apres = _get(port, token, {"If-None-Match": etag})
        assert apres.status == 200, "une ligne canal B ingérée a reçu un 304"
        assert apres.getheader("ETag") != etag
        assert json.loads(apres.data)["canal_b"]["rows_read"] == 2
        assert _get(port, token, {"If-None-Match": apres.getheader("ETag")}).status == 304


def test_gzip_seulement_si_accept_encoding_le_nomme(serveur):
    _httpd, port, token = serveur
    brut = _get(port, token)
    assert brut.getheader("Content-Encoding") is None
    assert isinstance(json.loads(brut.data), dict)
    compresse = _get(port, token, {"Accept-Encoding": "gzip, deflate"})
    assert compresse.getheader("Content-Encoding") == "gzip"
    assert int(compresse.getheader("Content-Length")) == len(compresse.data) < len(brut.data)
    assert gzip.decompress(compresse.data) == brut.data, "le gzip ne porte pas les octets du corps"
    for refus in ("gzip;q=0", "br", "identity, *"):
        assert _get(port, token, {"Accept-Encoding": refus}).getheader("Content-Encoding") is None, refus
    assert compresse.getheader("ETag") == brut.getheader("ETag"), "un ETag par corps, pas par codage"
    assert compresse.getheader("Vary") == brut.getheader("Vary") == "Accept-Encoding"


def test_la_date_utc_qui_change_donne_une_cle_neuve(serveur, monkeypatch):
    httpd, port, token = serveur
    horloge = [datetime(2026, 10, 15, 8, 0, tzinfo=timezone.utc)]
    monkeypatch.setattr(transport, "_maintenant", lambda: horloge[0])
    etag = _get(port, token).getheader("ETag")
    horloge[0] = datetime(2026, 10, 15, 23, 59, tzinfo=timezone.utc)
    assert _get(port, token, {"If-None-Match": etag}).status == 304, "même jour UTC : même clé"
    # 23 h 30 à UTC-2 est déjà le 16 en UTC : le jour se lit en UTC, jamais à l'heure locale.
    horloge[0] = datetime(2026, 10, 15, 23, 30, tzinfo=timezone(timedelta(hours=-2)))
    lendemain = _get(port, token, {"If-None-Match": etag})
    assert lendemain.status == 200 and lendemain.getheader("ETag") != etag
    assert httpd.snapshot_memo.constructions == 2


def _ecrire_canal_a(events: Path, nom: str = "2026-10-15.claude.1.jsonl") -> Path:
    events.mkdir(parents=True, exist_ok=True)
    chemin = events / nom
    with open(chemin, "a", encoding="utf-8", newline="\n") as fichier:
        fichier.write(json.dumps({"ts": _TS, "kind": "hook.deny", "host": "claude", "sid": "s1", "pid": "p1",
                                  "aid": "a1", "task": None, "agent": None}) + "\n")
    return chemin


def test_les_champs_vivants_ne_gelent_pas_au_repos(serveur, env, horloge):
    """B1 de l'exec-critic : deux ticks À VIDE espacés — la pastille d'ingestion (Header.jsx) et l'horodatage
    (Board.jsx) DOIVENT bouger, sans reconstruction ; puis un retard qui grandit doit se lire grandir."""
    httpd, port, token = serveur
    with event_store.open_store(create=True) as store:
        _ecrire_otel(env["otel"], 1.0)
        store.ingest_once(now=_NOW)
        for fichier in env["otel"].glob("*.jsonl"):
            fichier.unlink()  # l'état drainé, comme le laisse l'ingesteur
        _get(port, token)
        avant, vus = httpd.snapshot_memo.constructions, []
        for secondes in (10, 20):  # deux ticks à vide, espacés
            store.ingest_once(now=_NOW + timedelta(seconds=secondes))
            horloge["iso"] = f"2026-10-15T08:00:{secondes}Z"
            corps = json.loads(_get(port, token).data)
            vus.append((corps["ingestion"]["last_ingest_at"], corps["generated_at"]))
        assert vus == [("2026-07-27T19:59:02Z", "2026-10-15T08:00:10Z"),
                       ("2026-07-27T19:59:12Z", "2026-10-15T08:00:20Z")], f"champ vivant figé : {vus}"
        assert httpd.snapshot_memo.constructions == avant, "un tick à vide a reconstruit le corps"
        attente = _ecrire_canal_a(env["events"])  # en attente depuis 120 s, jamais ingéré ici
        st = attente.stat()
        os.utime(attente, (st.st_atime - 120, st.st_mtime - 120))
        premier = json.loads(_get(port, token).data)["ingestion"]
        apres_ajout = httpd.snapshot_memo.constructions
        time.sleep(0.5)
        second = json.loads(_get(port, token).data)["ingestion"]
        assert premier["late"] is True and second["late"] is True
        assert second["oldest_pending_age_seconds"] > premier["oldest_pending_age_seconds"], "le retard est figé"
        assert httpd.snapshot_memo.constructions == apres_ajout, "le retard qui grandit a reconstruit le corps"


# ---------------------------------------------------------------------------
# ETag du gabarit seul, champs vivants en en-tête (lot A de T-01M4XMQ1QC, geste 5).
# ---------------------------------------------------------------------------

def _mutant_etag_sur_greffes(monkeypatch) -> None:
    """MUTANT : l'ETag d'avant le lot A, tiré du gabarit ET des greffes (`servir` lit `rendre` au module)."""
    reel = transport.rendre

    def rendre_mutant(entree_, valeurs):
        rendu = reel(entree_, valeurs)
        empreinte = hashlib.sha256(entree_.empreinte + b"\x00" + b"\x00".join(rendu.greffes)).hexdigest()
        return dataclasses.replace(rendu, etag='W/"' + empreinte[:32] + '"')

    monkeypatch.setattr(transport, "rendre", rendre_mutant)


def _revalider_apres_un_tick(port: int, token: str, horloge: dict):
    """Un 200, puis seule une greffe bouge (`generated_at`), puis une revalidation avec l'ETag du 200."""
    premier = _get(port, token)
    horloge["iso"] = "2026-10-15T08:00:07Z"
    return premier, _get(port, token, {"If-None-Match": premier.getheader("ETag")})


def test_etag_stable_quand_seules_les_greffes_bougent(serveur, horloge):
    httpd, port, token = serveur
    premier, revalide = _revalider_apres_un_tick(port, token, horloge)
    assert revalide.status == 304, "une greffe qui bouge seule a refusé le 304 : au repos, rien ne revalide"
    assert revalide.getheader("ETag") == premier.getheader("ETag")
    assert httpd.snapshot_memo.constructions == 1


def test_mutant_etag_sur_greffes_rougit(serveur, horloge, monkeypatch):
    _mutant_etag_sur_greffes(monkeypatch)
    _httpd, port, token = serveur
    _premier, revalide = _revalider_apres_un_tick(port, token, horloge)
    assert revalide.status == 200, "le mutant « ETag sur greffes » doit refuser le 304 : sinon le témoin est sourd"


def test_entete_vivant_sur_200_et_304(serveur, horloge):
    _httpd, port, token = serveur
    premier = _get(port, token)
    entete = premier.getheader(transport.ENTETE_VIVANT)
    assert entete and entete.isascii(), f"en-tête vivant absent du 200 ou hors ASCII : {entete!r}"
    corps = json.loads(premier.data)
    assert json.loads(entete) == {"generated_at": corps["generated_at"], "ingestion": corps["ingestion"]}
    horloge["iso"] = "2026-10-15T08:00:42Z"
    revalide = _get(port, token, {"If-None-Match": premier.getheader("ETag")})
    assert revalide.status == 304 and revalide.data == b""
    vivant = json.loads(revalide.getheader(transport.ENTETE_VIVANT))
    assert vivant["generated_at"] == "2026-10-15T08:00:42Z", "le 304 a figé le champ vivant"
    # Le client greffe l'objet de tête sur le corps qu'il a mémorisé : il doit obtenir le corps du moment.
    assert {**corps, **vivant} == json.loads(_get(port, token).data)


def test_vivant_trop_gros_pas_de_304(serveur, monkeypatch):
    # `dashboard.py` passe ce dict à `servir` par référence, à chaque GET : la greffe grossie y est lue.
    monkeypatch.setitem(dashboard._SNAPSHOT_SOURCES["vivant"], ("ingestion",), lambda: {"pad": "x" * 9000})
    _httpd, port, token = serveur
    premier = _get(port, token)
    etag = premier.getheader("ETag")
    assert etag and premier.getheader(transport.ENTETE_VIVANT) is None, "un en-tête de plus de 8 Kio est parti"
    revalide = _get(port, token, {"If-None-Match": etag})
    assert revalide.status == 200 and revalide.getheader(transport.ENTETE_VIVANT) is None, \
        "un 304 sans en-tête vivant figerait l'écran"
    assert json.loads(revalide.data)["ingestion"] == {"pad": "x" * 9000}, "le 200 doit porter la greffe"
    monkeypatch.setattr(transport, "VIVANT_MAX", 10**9)  # MUTANT : la borne ignorée
    assert _get(port, token, {"If-None-Match": etag}).status == 304, "le mutant « borne ignorée » doit rendre 304"


# ---------------------------------------------------------------------------
# Construction unique — deux requêtes simultanées, UNE construction.
# ---------------------------------------------------------------------------

def _deux_get_simultanes(httpd, port, token, monkeypatch) -> tuple[int, list[int], set]:
    """A construit et attend ; B arrive à `entree` PENDANT ce temps ; puis A est libéré. Déterministe :
    le fil principal attend l'arrivée de B, il ne parie sur aucun délai."""
    debut, libere, constructions, arrivees = threading.Event(), threading.Event(), [], []
    construire_reel, entree_reelle = dashboard.build_snapshot, transport.entree

    def construire_lent(root=None):
        constructions.append(1)
        if len(constructions) == 1:
            debut.set()
            libere.wait(10)
        return construire_reel(root)

    def entree_comptee(*args, **kwargs):
        arrivees.append(1)
        return entree_reelle(*args, **kwargs)

    monkeypatch.setattr(dashboard, "build_snapshot", construire_lent)
    monkeypatch.setattr(transport, "entree", entree_comptee)
    reponses: list = []
    fils = [threading.Thread(target=lambda: reponses.append(_get(port, token))) for _ in range(2)]
    fils[0].start()
    assert debut.wait(10), "la première construction n'a pas démarré"
    fils[1].start()
    limite = time.monotonic() + 10
    while len(arrivees) < 2 and time.monotonic() < limite:
        time.sleep(0.005)
    time.sleep(0.05)  # B est entré dans `entree` ; ce délai ne sert qu'au mutant, jamais au verdict
    libere.set()
    for fil in fils:
        fil.join(20)
    return len(constructions), [r.status for r in reponses], {r.getheader("ETag") for r in reponses}


def test_deux_requetes_simultanees_une_seule_construction(serveur, monkeypatch):
    httpd, port, token = serveur
    n, statuts, etags = _deux_get_simultanes(httpd, port, token, monkeypatch)
    assert statuts == [200, 200] and len(etags) == 1
    assert n == 1 and httpd.snapshot_memo.constructions == 1, f"{n} constructions pour deux requêtes"


def test_mutant_verrou_retire_construit_deux_fois(serveur, monkeypatch):
    httpd, port, token = serveur
    monkeypatch.setattr(httpd.snapshot_memo, "verrou", contextlib.nullcontext())  # MUTANT : plus de verrou
    n, statuts, _etags = _deux_get_simultanes(httpd, port, token, monkeypatch)
    assert statuts == [200, 200]
    assert n == 2, "sans verrou le témoin de construction unique doit rougir"


# ---------------------------------------------------------------------------
# Le mémo, sans socket : variante, crochet `avant_cle`, exception.
# ---------------------------------------------------------------------------

def _construire_par_variante(appels: list):
    def construire(variante):
        appels.append(variante)
        return {"contrat": variante}
    return construire


def _rendu(entree_) -> object:
    return transport.rendre(entree_, {})


def _jouer_1_2_1_2(memo, construire) -> list:
    return [_rendu(transport.entree(memo, construire=construire, empreinte=lambda: ("e",), variante=v))
            for v in (1, 2, 1, 2)]


def test_deux_variantes_donnent_deux_corps(monkeypatch):
    """UNE case par variante (lot A de T-01M4XMQ1QC) : 1, 2, 1, 2 construit DEUX fois, jamais quatre."""
    memo, appels = transport.MemoCorps(), []
    construire = _construire_par_variante(appels)
    un, deux, un_bis, deux_bis = _jouer_1_2_1_2(memo, construire)
    assert json.loads(un.corps) == {"contrat": 1} and json.loads(deux.corps) == {"contrat": 2}
    assert (un_bis.corps, deux_bis.corps) == (un.corps, deux.corps) and un.etag != deux.etag
    assert appels == [1, 2] and memo.constructions == 2, f"{memo.constructions} constructions pour 1, 2, 1, 2"
    for autre in (0, 3, "1", True, 1.0, None):
        with pytest.raises(ValueError):
            transport.entree(memo, construire=construire, empreinte=lambda: ("e",), variante=autre)
    assert appels == [1, 2] and memo.constructions == 2 and not memo.verrou.locked()
    # MUTANT : la case choisie sans la variante -> chaque alternance évince le gabarit de l'autre contrat.
    memo2 = transport.MemoCorps()
    monkeypatch.setattr(memo2, "case", lambda variante: memo2.cases[1])
    _jouer_1_2_1_2(memo2, _construire_par_variante([]))
    assert memo2.constructions == 4, "le mutant « case choisie sans la variante » doit construire 4 fois"


def test_serialiser_identique_a_dumps(env):
    charges = [{"accents": "àçèùÉ — « guillemets »", "emoji": "🧪🚀👩‍💻", "cjk": "漢字",
                "echappes": "a\nb\t\"\\\x00\x7f", "nombres": [0, -2, 3.5, 1e100, 2**70],
                "atomes": [None, True, False], "vides": {"o": {}, "l": [], "s": ""}},
               [], "é", 0, None, dashboard.build_snapshot(env["root"])]
    for charge in charges:
        assert transport.serialiser(charge) == json.dumps(charge, ensure_ascii=False).encode("utf-8"), charge


_MIO = 1024 * 1024


class _JsonPiege:
    """Le `json` du module transport, dont `dumps` refuse toute sortie de plus d'1 Mio : la charge entière
    bâtie en UNE chaîne (le défaut mémoire de :152 d'avant le lot A). Le reste du module est le vrai."""

    def __init__(self, reel) -> None:
        self._reel = reel

    def __getattr__(self, nom: str):
        return getattr(self._reel, nom)

    def dumps(self, obj, *args, **kwargs):
        sortie = self._reel.dumps(obj, *args, **kwargs)
        if len(sortie) > _MIO:
            raise AssertionError(f"json.dumps de la charge entière ({len(sortie)} caractères)")
        return sortie


def test_gabarit_sans_dumps_de_la_charge(monkeypatch):
    monkeypatch.setattr(transport, "json", _JsonPiege(json))  # jamais le `json.dumps` global : le banc s'en sert
    vivants = (("generated_at",), ("ingestion",))
    charge = {"generated_at": "G0", "lignes": [{"id": i, "texte": "é" * 64} for i in range(20_000)],
              "ingestion": {"n": 1}}
    rendu = transport.rendre(transport.gabarit(charge, vivants), {("generated_at",): "G1", ("ingestion",): {"n": 2}})
    assert rendu.taille > _MIO, "charge trop petite : le piège ne pourrait pas partir"
    assert json.loads(rendu.corps) == {**charge, "generated_at": "G1", "ingestion": {"n": 2}}
    # MUTANT : :152 rétabli, `json.dumps` de la charge entière -> le piège DOIT partir.
    monkeypatch.setattr(transport, "serialiser", lambda c: transport.json.dumps(c, ensure_ascii=False).encode("utf-8"))
    with pytest.raises(AssertionError, match="charge entière"):
        transport.gabarit(charge, vivants)


def test_le_gabarit_greffe_sans_toucher_l_original_et_le_gzip_s_assemble():
    partage = {"last_ingest_at": "ancien", "n": 1}
    charge = {"generated_at": "G0", "liste": [1, 2], "ingestion": partage, "fin": "z"}
    gabarit = transport.gabarit(charge, (("generated_at",), ("ingestion",), ("absent", "x")))
    assert gabarit.chemins == (("generated_at",), ("ingestion",)), "un chemin absent n'est ni greffé ni ajouté"
    assert charge["generated_at"] == "G0" and partage == {"last_ingest_at": "ancien", "n": 1}, "original modifié"
    rendu = transport.rendre(gabarit, {("generated_at",): "G1", ("ingestion",): {"last_ingest_at": "neuf"}})
    assert json.loads(rendu.corps) == {"generated_at": "G1", "liste": [1, 2],
                                       "ingestion": {"last_ingest_at": "neuf"}, "fin": "z"}
    assert gzip.decompress(transport.assembler_gzip(gabarit, rendu)) == rendu.corps
    autre = transport.rendre(gabarit, {("generated_at",): "G2", ("ingestion",): {"last_ingest_at": "neuf"}})
    # P2 du plan de T-01M4XMQ1QC, amendé : l'ETag est celui du GABARIT, il ne couvre plus les greffes ; « rien
    # de vivant n'est figé » passe à l'en-tête vivant (témoins HTTP `test_entete_vivant_sur_200_et_304`…).
    assert autre.etag == rendu.etag, "l'ETag doit être celui du gabarit seul"
    assert json.loads(rendu.vivant) == {"generated_at": "G1", "ingestion": {"last_ingest_at": "neuf"}}
    assert json.loads(autre.vivant)["generated_at"] == "G2", "l'en-tête doit porter la greffe du moment"
    neuf = transport.gabarit({**charge, "fin": "y"}, (("generated_at",), ("ingestion",)))
    assert transport.rendre(neuf, {}).etag != rendu.etag, "un gabarit neuf doit changer l'ETag"
    profond = transport.gabarit({"a": {"b": 1}}, (("a", "b"),))
    assert transport.rendre(profond, {("a", "b"): 2}).vivant is None, "champ vivant pas de tête : ni en-tête ni 304"


def test_avant_cle_sous_le_verrou_avant_la_cle_et_dans_la_cle():
    memo, ordre, jeton = transport.MemoCorps(), [], [7]

    def avant_cle():
        ordre.append(("avant_cle", memo.verrou.locked()))
        return jeton[0]

    def empreinte():
        ordre.append(("empreinte", memo.verrou.locked()))
        return ("e",)

    construire = _construire_par_variante([])
    transport.entree(memo, construire=construire, empreinte=empreinte, avant_cle=avant_cle)
    assert ordre == [("avant_cle", True), ("empreinte", True)], "le crochet vient sous le verrou, AVANT la clé"
    transport.entree(memo, construire=construire, empreinte=empreinte, avant_cle=avant_cle)
    assert memo.constructions == 1, "même jeton : même clé"
    jeton[0] = 8
    transport.entree(memo, construire=construire, empreinte=empreinte, avant_cle=avant_cle)
    assert memo.constructions == 2, "le retour du crochet doit entrer dans la clé"
    assert _rendu(transport.entree(transport.MemoCorps(), construire=construire, empreinte=empreinte)).corps, \
        "crochet absent par défaut"


def test_une_construction_qui_leve_laisse_le_memo_et_libere_le_verrou():
    memo = transport.MemoCorps()
    bon = transport.entree(memo, construire=lambda v: {"ok": 1}, empreinte=lambda: ("a",))

    def leve(_variante):
        raise RuntimeError("construction simulée en échec")

    with pytest.raises(RuntimeError):
        transport.entree(memo, construire=leve, empreinte=lambda: ("b",))
    case = memo.case(1)
    assert case.entree is bon and case.cle is not None and not memo.verrou.locked()
    # La clé n'est posée qu'APRÈS une construction réussie : la même clé « b » doit donc reconstruire, jamais
    # servir l'ancien corps sous la clé neuve (mutant « clé posée avant construire » de l'exec-critic).
    neuf = transport.entree(memo, construire=lambda v: {"ok": 2}, empreinte=lambda: ("b",))
    assert json.loads(_rendu(neuf).corps) == {"ok": 2} and memo.constructions == 2


# ---------------------------------------------------------------------------
# La clé du mémo canal B, sans l'horodatage du spool.
# ---------------------------------------------------------------------------

def _decaler_mtime(chemin: Path) -> None:
    st = chemin.stat()
    os.utime(chemin, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))


def _scenario_absent(env, monkeypatch) -> list:
    lectures = _compter(monkeypatch, dashboard._otel_normalize_mod, "iter_envelopes")
    fichier = _ecrire_otel(env["otel"], 1.0)
    assert dashboard._read_canal_b()["source"] == "spool_files"
    _decaler_mtime(fichier)  # l'horodatage bouge, aucune ligne
    dashboard._read_canal_b()
    return lectures


def test_absent_un_mtime_qui_bouge_seul_ne_reconstruit_pas_canal_b(env, monkeypatch):
    lectures = _scenario_absent(env, monkeypatch)
    assert len(lectures) == 1, "un mtime sans ligne neuve a reconstruit canal B"
    _ecrire_otel(env["otel"], 0.5)
    assert dashboard._read_canal_b()["cost"]["native_usd"] == 1.5 and len(lectures) == 2, "une ligne neuve DOIT"


def test_mutant_horodatage_du_spool_rougit_le_temoin_absent(env, monkeypatch):
    _mutant_horodatage_du_spool(monkeypatch)
    assert len(_scenario_absent(env, monkeypatch)) == 2, "le mutant doit reconstruire : sinon le témoin est sourd"


def _scenario_ok(env, monkeypatch, store) -> list:
    lectures = _compter(monkeypatch, dashboard._otel_normalize_mod, "stream_bodies")
    _ecrire_otel(env["otel"], 1.0)
    store.ingest_once(now=_NOW)
    assert dashboard._read_canal_b()["rows_read"] == 1
    _ecrire_otel(env["otel"], 2.0, "2026-07-27.9.jsonl")  # écrite, PAS encore ingérée
    _ecrire_canal_a(env["events"])  # la ligne qu'un hook écrit à chaque usage d'outil, pas encore ingérée
    for fichier in [*env["otel"].glob("*.jsonl"), *env["events"].glob("*.jsonl")]:
        _decaler_mtime(fichier)
    dashboard._read_canal_b()
    return lectures


def test_ok_le_spool_ne_reconstruit_pas_canal_b_le_tick_une_fois(env, monkeypatch):
    with event_store.open_store(create=True) as store:
        lectures = _scenario_ok(env, monkeypatch, store)
        assert len(lectures) == 1, "une ligne pas encore ingérée a reconstruit canal B pour rien"
        store.ingest_once(now=_NOW + timedelta(seconds=5))
        assert dashboard._read_canal_b()["rows_read"] == 2 and len(lectures) == 2, "le tick reconstruit UNE fois"
        dashboard._read_canal_b()
        assert len(lectures) == 2


def test_mutant_horodatage_du_spool_rougit_le_temoin_ok(env, monkeypatch):
    _mutant_horodatage_du_spool(monkeypatch)
    with event_store.open_store(create=True) as store:
        assert len(_scenario_ok(env, monkeypatch, store)) == 2, "le mutant doit reconstruire"


def test_une_identite_changee_recalcule_canal_b(env, monkeypatch):
    """`_resolve_identity_once` relit `project.json` à chaque appel : sans l'identité dans la clé, une
    attribution périmée resterait servie par le mémo canal B (corrigé en place, T-01M4XR9ESW)."""
    lectures = _compter(monkeypatch, dashboard._otel_normalize_mod, "iter_envelopes")
    _ecrire_otel(env["otel"], 1.0)
    assert dashboard._read_canal_b()["attribution"]["own_project_id"] == _OWN_ID
    _identite(env["identity"], "autre-projet-0002")
    assert dashboard._read_canal_b()["attribution"]["own_project_id"] == "autre-projet-0002"
    assert len(lectures) == 2


def test_late_rejets_et_identite_font_bouger_l_empreinte(tmp_path):
    """Les entrées SANS fichier du snapshot : `late` vieillit avec l'horloge, `dropped_foreign` (gelé à 0
    depuis T-00000084) vit en mémoire. Le témoin d'audit ci-dessous ne les voit pas ; celui-ci les éprouve."""
    etat = {"late": False, "rejets": 0}
    identite = tmp_path / "identite.json"
    identite.write_text("{}", encoding="utf-8")
    sources = {"store_fingerprint": lambda: ("store",), "events_dir": lambda: None, "otel_dir": lambda: None,
               "ingestion": lambda: {"late": etat["late"]}, "inputs": lambda *_a: ("entrees",),
               "identity_path": lambda: identite, "dropped_foreign": lambda: etat["rejets"]}
    base = transport.empreinte_snapshot(tmp_path, sources)
    assert transport.empreinte_snapshot(tmp_path, sources) == base, "empreinte instable au repos"
    etat["late"] = True
    assert transport.empreinte_snapshot(tmp_path, sources) != base, "`late` qui bascule doit changer la clé"
    etat.update(late=False, rejets=1)
    assert transport.empreinte_snapshot(tmp_path, sources) != base, "`dropped_foreign` doit changer la clé"
    etat["rejets"] = 0
    assert transport.empreinte_snapshot(tmp_path, sources) == base
    _decaler_mtime(identite)
    assert transport.empreinte_snapshot(tmp_path, sources) != base, "le fichier d'identité doit changer la clé"


def _sources_figees(tmp_path: Path) -> dict:
    return {"store_fingerprint": lambda: ("store",), "events_dir": lambda: None, "otel_dir": lambda: None,
            "ingestion": lambda: {"late": False}, "inputs": lambda *_a: ("entrees",),
            "identity_path": lambda: None, "dropped_foreign": lambda: 0}


def _un_lot_ne_bouge_pas_la_cle(racine: Path) -> bool:
    """Un lot de sauvegarde inachevée apparaît dans le dossier que LIT `tasks_stockage._lire_lots` : vrai si la
    clé reste à sa base (la faute), faux si elle bouge. Le dossier n'existe pas avant : le cas du `tasks.py`
    tué entre l'écriture du lot et celle des enregistrements."""
    sources = _sources_figees(racine)
    dossier = dashboard._tasks_mod._dossier_lots(racine)
    assert not dossier.exists(), "dossier de lots déjà là : le témoin ne partirait pas de l'absence"
    base = transport.empreinte_snapshot(racine, sources)
    assert transport.empreinte_snapshot(racine, sources) == base, "clé instable au repos : témoin invalide"
    dossier.mkdir(parents=True)
    lot = dossier / "00000000000000000001.json"
    lot.write_bytes(b"{}")
    try:
        assert [chemin for chemin, _lot in dashboard._tasks_mod._lire_lots(racine)] == [lot], \
            "le lecteur du board ne lit pas ce lot : le témoin éprouverait un dossier que rien ne lit"
        immobile = transport.empreinte_snapshot(racine, sources) == base
    finally:
        lot.unlink()
    assert transport.empreinte_snapshot(racine, sources) == base, "clé non revenue après le lot retiré"
    return immobile


def test_un_lot_de_board_en_suspens_fait_bouger_la_cle(tmp_path):
    assert not _un_lot_ne_bouge_pas_la_cle(tmp_path)


def test_mutant_lots_hors_de_la_cle_rougit(tmp_path, monkeypatch):
    monkeypatch.setattr(transport, "DOSSIERS_HORS_VUES", ())  # MUTANT : les lots en suspens hors de la clé
    assert _un_lot_ne_bouge_pas_la_cle(tmp_path)


# ---------------------------------------------------------------------------
# Complétude de l'empreinte : chaque fichier que lit `build_snapshot` est observé par la clé.
# ---------------------------------------------------------------------------

_AUDIT: dict = {"actif": False, "ouverts": set(), "scannes": set()}


def _crochet_audit(evenement: str, args: tuple) -> None:
    if not _AUDIT["actif"] or not args:
        return
    cible = args[0]
    if evenement == "sqlite3.connect" and isinstance(cible, str):
        cible = cible.removeprefix("file:").split("?", 1)[0]
    if not isinstance(cible, (str, bytes, os.PathLike)):
        return
    if evenement in ("open", "sqlite3.connect"):
        _AUDIT["ouverts"].add(os.path.realpath(os.fsdecode(cible)))
    elif evenement in ("os.scandir", "os.listdir"):
        _AUDIT["scannes"].add(os.path.realpath(os.fsdecode(cible)))


sys.addaudithook(_crochet_audit)  # un crochet d'audit ne se retire pas : il ne fait rien hors `_AUDIT["actif"]`


def _releve(action, monkeypatch, stats: set | None = None) -> tuple[set, set]:
    _AUDIT.update(actif=True, ouverts=set(), scannes=set())
    reel = os.stat

    def espion(chemin, *args, **kwargs):
        if stats is not None and isinstance(chemin, (str, bytes, os.PathLike)):
            stats.add(os.path.realpath(os.fsdecode(chemin)))
        return reel(chemin, *args, **kwargs)

    monkeypatch.setattr(os, "stat", espion)
    try:
        action()
    finally:
        monkeypatch.setattr(os, "stat", reel)
        _AUDIT["actif"] = False
    return set(_AUDIT["ouverts"]), set(_AUDIT["scannes"])


def _code_python(chemin: str) -> bool:
    return chemin.endswith((".py", ".pyc", ".so")) or "__pycache__" in chemin or any(
        chemin.startswith(os.path.realpath(p)) for p in {sys.prefix, sys.base_prefix})


def _lectures_du_build(racine: Path, monkeypatch) -> tuple[list[str], list[str], set]:
    """(fichiers lus, fichiers CHERCHÉS et absents, répertoires scannés). L'événement d'audit `open` part
    avant l'échec : un fichier absent que le build tente d'ouvrir est relevé, et il doit compter aussi."""
    dashboard._reset_canal_b_cache_for_tests()
    dashboard._reset_canal_a_cache_for_tests()
    readers.reset_cache_for_tests()
    ouverts, scannes = _releve(lambda: dashboard.build_snapshot(racine), monkeypatch)
    utiles = [p for p in ouverts if not _code_python(p) and ".git" not in Path(p).parts]
    return (sorted(p for p in utiles if os.path.isfile(p)),
            sorted(p for p in utiles if not os.path.exists(p)), scannes)


# Au plus N fichiers copiés par répertoire : un répertoire d'enregistrements (board, ledger) en ouvre des
# centaines, et son empreinte de RÉPERTOIRE est éprouvée par le fichier témoin ajouté ci-dessous.
_COPIES_PAR_REPERTOIRE = 5


@pytest.fixture
def copie_des_entrees(env, tmp_path, monkeypatch):
    """Une copie JETABLE des entrées que `build_snapshot` lit dans l'arbre RÉEL de ce dépôt (jamais écrit),
    plus un store `ok` jetable : le témoin décale des mtimes et ajoute des fichiers, donc jamais sur le vrai.

    BORNE dite : rien sous `.git` n'est copié — HEAD s'empreinte par son CONTENU (le sha, depuis
    T-00000026), un mtime décalé n'y serait pas un changement."""
    reel = os.path.realpath(HERE.parent.parent)
    copie = tmp_path / "copie"
    with event_store.open_store(create=True) as store:
        _ecrire_otel(env["otel"], 1.0)
        store.ingest_once(now=_NOW)
        lus, _absents, _scannes = _lectures_du_build(Path(reel), monkeypatch)
        par_repertoire: dict[str, int] = {}
        for chemin in lus:
            rel = os.path.relpath(chemin, reel)
            if rel.startswith(".."):
                continue
            parent = os.path.dirname(rel)
            if par_repertoire.get(parent, 0) >= _COPIES_PAR_REPERTOIRE:
                continue
            par_repertoire[parent] = par_repertoire.get(parent, 0) + 1
            (copie / rel).parent.mkdir(parents=True, exist_ok=True)
            (copie / rel).write_bytes(Path(chemin).read_bytes())
        assert len(par_repertoire) > 5, f"copie presque vide ({par_repertoire}) : le témoin serait creux"
        yield copie


def _entrees_qui_ne_bougent_pas_la_cle(racine: Path, sources, monkeypatch) -> list[str]:
    """Chaque fichier lu par `build_snapshot(racine)` voit son mtime décalé ; chaque fichier qu'il CHERCHE
    sans le trouver est créé ; chaque répertoire scanné dont il a lu un fichier en reçoit un de même
    suffixe. À chaque fois la clé DOIT bouger, puis revenir à sa base une fois l'état rendu."""
    lus, absents, scannes = _lectures_du_build(racine, monkeypatch)
    jetable = Path(os.path.realpath(racine.parent))  # le `tmp_path` du test : rien n'est créé hors de lui
    absents = [p for p in absents if Path(p).is_relative_to(jetable)]
    assert len(lus) > 10, f"relevé presque vide ({len(lus)}) : le témoin serait creux"
    base = transport.empreinte_snapshot(racine, sources)
    assert transport.empreinte_snapshot(racine, sources) == base, "clé instable au repos : témoin invalide"
    fautes = []
    for chemin in lus:
        st = os.stat(chemin)
        os.utime(chemin, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
        try:
            if transport.empreinte_snapshot(racine, sources) == base:
                fautes.append(chemin)
        finally:
            os.utime(chemin, ns=(st.st_atime_ns, st.st_mtime_ns))
        # Sans ce retour à la base, une entrée mal restaurée MASQUERAIT chaque entrée examinée après elle.
        assert transport.empreinte_snapshot(racine, sources) == base, f"clé non revenue après {chemin}"
    for chemin in absents:
        crees = [p for p in Path(chemin).parents if not p.exists()]
        Path(chemin).parent.mkdir(parents=True, exist_ok=True)
        Path(chemin).write_bytes(b"{}")
        try:
            if transport.empreinte_snapshot(racine, sources) == base:
                fautes.append(chemin)
        finally:
            Path(chemin).unlink()
            for repertoire in crees:  # du plus profond au plus haut : `parents` remonte
                repertoire.rmdir()
        assert transport.empreinte_snapshot(racine, sources) == base, f"clé non revenue après {chemin}"
    for repertoire in sorted(scannes):
        enfants = [p for p in lus if os.path.dirname(p) == repertoire]
        if not enfants:
            continue
        temoin = Path(repertoire) / ("zz-temoin-transport" + Path(enfants[0]).suffix)
        temoin.write_bytes(Path(enfants[0]).read_bytes())
        try:
            if transport.empreinte_snapshot(racine, sources) == base:
                fautes.append(repertoire + os.sep)
        finally:
            temoin.unlink()
    return fautes


def test_chaque_entree_de_build_snapshot_fait_bouger_la_cle(copie_des_entrees, monkeypatch):
    assert _entrees_qui_ne_bougent_pas_la_cle(copie_des_entrees, dashboard._SNAPSHOT_SOURCES, monkeypatch) == []


def test_mutants_entrees_oubliees_par_la_cle_rougissent(copie_des_entrees, env, monkeypatch):
    original = transport.FICHIERS_HORS_VUES
    monkeypatch.setattr(transport, "FICHIERS_HORS_VUES", ())  # MUTANT : badge et tarifs hors de la clé
    fautes = _entrees_qui_ne_bougent_pas_la_cle(copie_des_entrees, dashboard._SNAPSHOT_SOURCES, monkeypatch)
    assert os.path.realpath(copie_des_entrees / ".agents" / "ref" / "MODEL_RATES.json") in fautes
    assert os.path.realpath(copie_des_entrees / ".agents" / "state" / "project.json") in fautes
    monkeypatch.setattr(transport, "FICHIERS_HORS_VUES", original)  # jamais `undo()` : il défairait `env`
    sans_identite = {**dashboard._SNAPSHOT_SOURCES, "identity_path": lambda: None}  # MUTANT : identité oubliée
    fautes = _entrees_qui_ne_bougent_pas_la_cle(copie_des_entrees, sans_identite, monkeypatch)
    assert fautes == [os.path.realpath(env["identity"])]
