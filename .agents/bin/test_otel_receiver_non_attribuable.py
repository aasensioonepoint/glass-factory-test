"""T-00000927 — banc : la télémétrie OTLP globale au poste et son marquage
« non attribuable ».

Cible (inventaire-cible P9) : « Coûts : un receveur OTLP global au poste. Ce qui
n'est pas attribuable à un projet est affiché « non attribuable », jamais comme
un zéro. » Critères BK-525 : (1) un span sans projet est rendu « non
attribuable », pas 0 ; (2) un span attribué reste attribué à son projet ; (3) un
écart est nommé, jamais corrigé en silence.

BOUT EN BOUT : un vrai POST OTLP/JSON sur le récepteur réel (`OTLPHandler`, port
loopback ÉPHÉMÈRE — jamais 4318, que tient le démon du poste), puis la lecture
que sert la route (`dashboard._read_canal_b`) : par le store SQLite, la source de
production, et par le repli fichier d'un store `absent`. `test_otel_receiver.py`
couvre le récepteur seul et `test_dashboard.py` le recensement sur fixtures
écrites à la main ; ce fichier relie les deux bouts.

Fichier FRÈRE (règle des 1600 lignes, S-00002684, S-00004034) : il importe les fixtures autouse de
`test_dashboard.py` (précédent `test_dashboard_degradations.py`) pour n'avoir
qu'UNE instance du dashboard, donc UN récepteur — celui qui reçoit est celui dont
le dashboard lit l'identité et les compteurs.

ÉCART MESURÉ (critère 3), marqué `xfail(strict=True)` et non corrigé : le
MONTANT d'un span sans projet entre dans `cost.native_usd`, que la vue Coût
étiquette « $ natif cumulé (projet, 30 j) ». Le COMPTE est rendu « inattribuable »
(tenu) ; le montant ne l'est pas. Le contrat V1-c le veut ainsi
(`totals_include: ["attributed", "unattributed"]`, pinné par
`test_dashboard.py::test_foreign_rows_are_excluded_from_the_monetary_totals`) :
le trancher est une décision pilote, portée par T-00001147, pas un correctif
de dev.

BORNE, pas écart : le récepteur ne sert que `/v1/logs` et `/v1/metrics` ; un
span de TRACE (`/v1/traces`) est un 404 et n'est compté nulle part. P9 parle de
coûts, qui arrivent par métriques et logs.
"""
from __future__ import annotations

import http.client
import http.server
import json
import re
import threading
from pathlib import Path

import pytest

import test_dashboard as td
from test_dashboard import _drain_streams, _redirect  # noqa: F401 — fixtures autouse, ré-exposées pour CE module

dashboard = td.dashboard
receiver = td.otel_receiver      # `dashboard._otel_receiver` : la MÊME instance
event_store = td.event_store     # `dashboard._event_store_mod`

_OWN_ID = td._OWN_ID
_PEER_ID = "peer-project-id-0927"
_TIMEOUT = 30.0  # borne de patience (cf. test_otel_receiver.py), pas un seuil mesuré
_UI_BUNDLE = Path(__file__).resolve().parent.parent / "ui" / "assets" / "app.js"
_RECENSEMENT_VIDE = {"attributed": 0, "attributed_by_backfill": 0,
                     "unattributed": 0, "foreign_held": 0}


# ---------------------------------------------------------------------------
# Outils
# ---------------------------------------------------------------------------

@pytest.fixture
def recepteur(_redirect, monkeypatch):
    """Le récepteur réel sur un port loopback éphémère, servi dans un fil.
    `_redirect` (test_dashboard) a déjà redirigé spool, identité et registre ;
    on remet ici les compteurs et le cache du routeur du récepteur.
    `AGENTS_EVENTS_DB` exporté l'emporte sur `AGENTS_EVENTS_DIR`
    (`events.events_db_path`) : laissé, le store du banc serait celui du shell
    (mesuré : 3 failed) — on le retire d'abord."""
    monkeypatch.delenv("AGENTS_EVENTS_DB", raising=False)
    receiver._reset_state_for_tests()
    httpd = http.server.HTTPServer(("127.0.0.1", 0), receiver.OTLPHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd.server_address[1]
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
        receiver._reset_state_for_tests()


def _post(port: int, path: str, payload: dict) -> int:
    """UN envoi, jamais rejoué : un double POST doublerait le recensement."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=_TIMEOUT)
    try:
        conn.request("POST", path, body=json.dumps(payload).encode("utf-8"),
                     headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        resp.read()
        return resp.status
    finally:
        conn.close()


def _span_de_cout(usd: float, project_id: str | None) -> dict:
    """Un export OTLP/JSON `claude_code.cost.usage`, la forme que
    `otel_normalize` lit. `project_id=None` : l'hôte ne déclare rien (Codex, ou
    tout hôte dont le bloc `OTEL_RESOURCE_ATTRIBUTES` n'est pas posé)."""
    resource = [td._attr("service.name", "claude-code")]
    if project_id is not None:
        resource.append(td._attr("agentkit.project_id", project_id))
    return {"resourceMetrics": [{
        "resource": {"attributes": resource},
        "scopeMetrics": [{"metrics": [{
            "name": "claude_code.cost.usage",
            "sum": {"dataPoints": [{"attributes": [td._attr("model", "m")],
                                    "asDouble": usd}]},
        }]}],
    }]}


def _lignes(otel_dir: Path) -> list[dict]:
    """Les lignes du spool (`*.jsonl` au premier niveau : ni `orphans/`, ni
    `exports/`)."""
    if not otel_dir.is_dir():
        return []
    out: list[dict] = []
    for fichier in sorted(otel_dir.glob("*.jsonl")):
        out += [json.loads(ligne) for ligne in
                fichier.read_text(encoding="utf-8").splitlines() if ligne]
    return out


def _ingerer() -> None:
    """La voie de PRODUCTION : le démon projette le spool dans `events.db`.
    Préconditions par `pytest.fail`, jamais `assert` : un store qui ne s'ouvre
    pas ne doit pas pouvoir rendre l'xfail de l'écart `xfailed` en silence."""
    store = event_store.open_store(create=True)
    try:
        if store.status != "ok":
            pytest.fail(f"précondition : store {store.status} — {store.reason}")
        report = store.ingest_once()
        if report.get("rows_inserted", 0) < 1:
            pytest.fail(f"précondition : rien d'ingéré — {report}")
    finally:
        store.close()


def _section() -> dict:
    """`_read_canal_b()` est mémoïsé : cache remis à chaque lecture du banc."""
    dashboard._reset_canal_b_cache_for_tests()
    return dashboard._read_canal_b()


def _recensement(**compte: int) -> dict:
    return {**_RECENSEMENT_VIDE, **compte}


# ---------------------------------------------------------------------------
# Critère 1 — un span sans projet est rendu « non attribuable », pas 0
# ---------------------------------------------------------------------------

def test_un_span_sans_projet_est_compte_non_attribuable_jamais_zero(recepteur, _redirect):
    """Récepteur -> sentinelle `unattributed` -> store -> payload : le span est
    une ligne du seau `unattributed` (1, pas 0, pas `attributed`) et son
    argent est compté (pas un zéro). Mord : sentinelle retirée de `persist()`
    (la ligne n'a plus de `project_id` -> le recensement change de seau) ;
    seau `unattributed` fondu dans `attributed`."""
    assert _post(recepteur, "/v1/metrics", _span_de_cout(0.25, None)) == 200
    assert [ligne["project_id"] for ligne in _lignes(_redirect["otel_dir"])] == [
        "unattributed"]
    _ingerer()
    section = _section()
    assert (section["status"], section["source"]) == ("ok", "sqlite"), section.get("reason")
    assert section["attribution"]["own_project_id"] == _OWN_ID
    assert section["attribution"]["rows_in_store"] == _recensement(unattributed=1)
    assert section["cost"]["native_usd"] == 0.25, "l'argent non attribuable n'est pas un zéro"


def test_le_repli_fichier_compte_le_span_sans_projet_de_la_meme_facon(recepteur, _redirect):
    """Store `absent` (le démon n'a jamais ingéré) : le repli fichier rend le
    même recensement que le store — une seule histoire pour le même span."""
    assert _post(recepteur, "/v1/metrics", _span_de_cout(0.25, None)) == 200
    section = _section()
    assert (section["status"], section["source"]) == ("ok", "spool_files"), section.get("reason")
    assert section["attribution"]["rows_in_store"] == _recensement(unattributed=1)


def test_le_compte_non_attribuable_est_rendu_sous_le_libelle_inattribuable():
    """Le RENDU, lu dans le bundle construit `.agents/ui/assets/app.js` (il
    voyage ; `.agents/ui-src/` non) : le seau `unattributed` porte le libellé
    « inattribuable (hôte ne déclare rien) » ; le composant
    (`Attribution.jsx`) en affiche la valeur lue dans `rows_in_store`. Mord :
    libellé ou clé du seau changés."""
    bundle = _UI_BUNDLE.read_text(encoding="utf-8")
    assert re.search(r'\[\s*"unattributed"\s*,\s*"inattribuable \(hôte ne déclare rien\)"',
                     bundle), "le seau `unattributed` n'est plus rendu « inattribuable »"


# ---------------------------------------------------------------------------
# Critère 2 — un span attribué reste attribué à son projet
# ---------------------------------------------------------------------------

def test_un_span_du_projet_reste_attribue_a_son_projet(recepteur, _redirect):
    """Un span qui déclare l'id du projet et un span qui ne déclare rien, sur le
    même récepteur : chacun dans son seau, jamais l'un fondu dans l'autre."""
    assert _post(recepteur, "/v1/metrics", _span_de_cout(1.0, _OWN_ID)) == 200
    assert _post(recepteur, "/v1/metrics", _span_de_cout(0.25, None)) == 200
    assert sorted(ligne["project_id"] for ligne in _lignes(_redirect["otel_dir"])) == sorted(
        [_OWN_ID, "unattributed"])
    _ingerer()
    section = _section()
    assert section["source"] == "sqlite", section.get("reason")
    assert section["attribution"]["rows_in_store"] == _recensement(attributed=1, unattributed=1)


def test_un_span_d_un_pair_est_route_chez_lui_et_y_reste_attribue(
        recepteur, _redirect, tmp_path, monkeypatch):
    """LE RÉCEPTEUR GLOBAL AU POSTE (T-00000084) : le détenteur reçoit le span
    d'un AUTRE projet enregistré, le route dans le spool de ce projet, et ne le
    compte nulle part chez lui. Vu du pair (son spool, son identité), le span
    est `attributed` — pas `unattributed`, pas `foreign_held`."""
    pair = tmp_path / "pair"
    (pair / ".agents" / "state" / "local").mkdir(parents=True)
    (pair / ".agents" / "state" / "project.json").write_text(
        json.dumps({"project_id": _PEER_ID}), encoding="utf-8", newline="\n")
    (tmp_path / "registry.json").write_text(json.dumps({"version": 1, "projects": {
        _PEER_ID: {"project_id": _PEER_ID, "project_root": str(pair), "name": "Pair",
                   "pid": 1, "port": 61000, "started": "2026-10-04T00:00:00Z"}}}),
        encoding="utf-8", newline="\n")
    receiver._reset_router_cache()

    assert _post(recepteur, "/v1/metrics", _span_de_cout(2.0, _PEER_ID)) == 200
    spool_pair = pair / ".agents" / "state" / "local" / "otel"
    assert [ligne["project_id"] for ligne in _lignes(spool_pair)] == [_PEER_ID]
    assert _lignes(_redirect["otel_dir"]) == [], "le détenteur ne garde rien du pair"
    assert receiver.get_diagnostics()["routed_peer"] == 1

    # Être le pair : son spool, son identité, son répertoire d'événements.
    monkeypatch.setenv("AGENTS_OTEL_DIR", str(spool_pair))
    monkeypatch.setenv("AGENTS_PROJECT_JSON", str(pair / ".agents" / "state" / "project.json"))
    monkeypatch.setenv("AGENTS_EVENTS_DIR", str(pair / ".agents" / "state" / "events"))
    receiver._reset_identity_cache_for_tests()
    section = _section()
    assert (section["status"], section["source"]) == ("ok", "spool_files"), section.get("reason")
    assert section["attribution"]["own_project_id"] == _PEER_ID
    assert section["attribution"]["rows_in_store"] == _recensement(attributed=1)
    assert section["cost"]["native_usd"] == 2.0


# ---------------------------------------------------------------------------
# Borne — un span de TRACE n'est pas reçu
# ---------------------------------------------------------------------------

def test_borne_un_span_de_trace_est_un_404_et_n_est_compte_nulle_part(recepteur, _redirect):
    """Le récepteur sert `/v1/logs` et `/v1/metrics`, rien d'autre
    (otel_receiver.py `_ALLOWED_PATHS`). Un export `/v1/traces` est refusé et
    rien n'est persisté : ni attribué, ni « non attribuable ». Borne énoncée,
    pas un écart de P9 (les coûts arrivent par métriques et logs)."""
    trace = {"resourceSpans": [{"resource": {"attributes": []}, "scopeSpans": []}]}
    assert _post(recepteur, "/v1/traces", trace) == 404
    assert _lignes(_redirect["otel_dir"]) == []


# ---------------------------------------------------------------------------
# Critère 3 — l'écart mesuré, nommé et non corrigé
# ---------------------------------------------------------------------------

@pytest.mark.xfail(strict=True, raises=AssertionError, reason=(
    "T-00000927 — écart mesuré à P9 : le montant d'un span sans projet entre dans "
    "`cost.native_usd` (dashboard.py `_aggregate_canal_b`, `totals_include` = "
    "attributed + unattributed), que la vue Coût étiquette « $ natif cumulé (projet, "
    "30 j) ». Le compte est rendu « inattribuable », le montant non. Contredit le "
    "contrat V1-c pinné par test_dashboard.py : arbitrage pilote porté par "
    "T-00001147, pas un correctif."))
def test_ecart_le_montant_non_attribuable_ne_figure_pas_sous_le_chiffre_projet(
        recepteur, _redirect):
    """P9 au plus simple : le chiffre que la vue Coût étiquette « projet » ne
    porte que l'argent du projet. Mesuré : 1.25 (1.0 du projet + 0.25 non
    attribuable). Les préconditions passent par `pytest.fail`, pas par
    `assert`, pour que seul l'écart visé puisse rendre ce test `xfailed`."""
    if _post(recepteur, "/v1/metrics", _span_de_cout(1.0, _OWN_ID)) != 200:
        pytest.fail("précondition : span du projet refusé")
    if _post(recepteur, "/v1/metrics", _span_de_cout(0.25, None)) != 200:
        pytest.fail("précondition : span sans projet refusé")
    _ingerer()
    section = _section()
    if section.get("status") != "ok":
        pytest.fail(f"précondition : canal B {section.get('status')} — {section.get('reason')}")
    # Découplée du minifieur (design-review S-00004726, B2) : le nom qu'il donne
    # au formateur change d'un build à l'autre (`wn`, `Ls`, `Os`, `$s` mesurés),
    # et `$` n'est pas un `\w`. On cherche le LIBELLÉ littéral, puis `.native_usd)`
    # dans les 80 caractères qui le suivent — la valeur rendue sous ce libellé.
    bundle = _UI_BUNDLE.read_text(encoding="utf-8")
    libelle = 'label:"$ natif cumulé (projet, 30 j)"'
    debut = bundle.find(libelle)
    if debut < 0 or ".native_usd)" not in bundle[debut + len(libelle):debut + len(libelle) + 80]:
        pytest.fail("précondition : `native_usd` n'est plus rendu sous « (projet, 30 j) »")
    assert section["cost"]["native_usd"] == 1.0, section["cost"]["native_usd"]
