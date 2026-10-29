"""Canal B : recalcul borné, valeur datée, lecture incrémentale (T-01M5T5G6MR) — témoins W1-W9.

Annexe du plan, § Témoins : `docs/tasks/T-01M5T5G6MR3K1MEK4N8K7S19H7-annexe.md`. Les fixtures autouse de
`test_dashboard.py` (`_redirect`, `_drain_streams`) sont ré-exposées ici, comme `test_dashboard_degradations.py` :
même isolation que le fichier d'origine. Horloge monotone patchée sur `dashboard._canal_b_mod` (fixe par défaut :
durée 0, rien n'est différé) ; comptes relevés par un espion sur `normalize_envelope`. Chaque témoin nomme le
mutant qui doit le faire rougir.
"""
from __future__ import annotations

import contextlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

import test_dashboard as td
from test_dashboard import _drain_streams, _redirect  # noqa: F401 — fixtures autouse, ré-exposées pour CE module

dashboard, event_store = td.dashboard, td.event_store
canal_b, transport = dashboard._canal_b_mod, dashboard._transport_mod
_ANCIEN, _RECENT = "2026-07-27T19:58:52Z", "2026-08-27T10:00:00Z"


class _Horloge:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture(autouse=True)
def horloge(monkeypatch):
    h = _Horloge()
    monkeypatch.setattr(canal_b, "_horloge", h)
    return h


@pytest.fixture
def espion(monkeypatch):
    compte = {"c": 0}
    vrai = dashboard._otel_normalize_mod.normalize_envelope

    def _compte(envelope):
        compte["c"] += 1
        return vrai(envelope)

    monkeypatch.setattr(dashboard._otel_normalize_mod, "normalize_envelope", _compte)
    return compte


def _duree(monkeypatch, horloge: _Horloge, secondes: float) -> None:
    """Chaque calcul de canal B dure `secondes` sur l'horloge simulée."""
    vrai_top = canal_b.top

    def _top() -> float:
        debut = vrai_top()
        horloge.t += secondes
        return debut

    monkeypatch.setattr(canal_b, "top", _top)


def _lignes(n: int, ts: str = _ANCIEN, depart: int = 0) -> list[dict]:
    return [td._metric_envelope(ts, "claude_code.cost.usage", float(depart + i + 1),
                                {"model": "m", "session.id": f"s{depart + i}"}) for i in range(n)]


def _ajouter(_redirect, envelopes: list, fichier: str, now: datetime | None = None) -> None:
    """Ingère SANS remettre canal B à zéro (contrairement à `td._ingest_otel`) : le chemin du démon."""
    td._write_otel(_redirect["otel_dir"], envelopes, fichier)
    with event_store.open_store(create=True) as store:
        store.ingest_once(now=now) if now is not None else store.ingest_once()


def _entier() -> dict:
    dashboard._reset_canal_b_cache_for_tests()
    return dashboard._read_canal_b()


def _sans_date(section: dict) -> dict:
    return {k: v for k, v in section.items() if k != "fraicheur"}


def _fenetre(_redirect, monkeypatch, horloge) -> tuple[float, dict]:
    """Une valeur ok calculée en 1,0 s simulée, puis une ligne neuve ingérée : la fenêtre s'ouvre."""
    td._ingest_otel(_redirect, _lignes(1))
    _duree(monkeypatch, horloge, 1.0)
    v1 = dashboard._read_canal_b()
    assert v1["status"] == "ok" and v1["fraicheur"]["differe"] is False, v1
    assert v1["fraicheur"]["duree_s"] == 1.0
    _ajouter(_redirect, _lignes(1, depart=1), "2026-07-27.2.jsonl")
    return canal_b._etat["debut"], v1


def test_w1_dans_la_fenetre_la_valeur_est_differee_et_datee(_redirect, monkeypatch, horloge, espion):
    """W1. M1 (`differer` rend None) et M1b (`FACTEUR = 1`) -> recalcul à +5 s, rouge."""
    debut, v1 = _fenetre(_redirect, monkeypatch, horloge)
    horloge.t = debut + 5
    espion["c"] = 0
    v2 = dashboard._read_canal_b()
    assert espion["c"] == 0, "un recalcul dans la fenêtre"
    assert v2["fraicheur"]["differe"] is True
    assert v2["fraicheur"]["calcule_le"] == v1["fraicheur"]["calcule_le"]
    assert v2["rows_read"] == 1
    assert canal_b._etat["valeur"]["fraicheur"]["differe"] is False, "l'objet en cache a été muté"


def test_w2_l_echeance_change_la_cle_du_transport_sans_ligne_neuve(_redirect, monkeypatch, horloge):
    """W2. M2 (`jeton` rend None) -> la clé ne bouge pas à l'échéance, rouge."""
    debut, _v1 = _fenetre(_redirect, monkeypatch, horloge)
    racine = _redirect["project_root"]
    horloge.t = debut + 5
    assert dashboard._read_canal_b()["fraicheur"]["differe"] is True
    cle = transport.empreinte_snapshot(racine, dashboard._SNAPSHOT_SOURCES)
    assert transport.empreinte_snapshot(racine, dashboard._SNAPSHOT_SOURCES) == cle, "clé instable"
    horloge.t = debut + 10.5
    assert transport.empreinte_snapshot(racine, dashboard._SNAPSHOT_SOURCES) != cle
    v3 = dashboard._read_canal_b()
    assert v3["rows_read"] == 2 and v3["fraicheur"]["differe"] is False


def test_w3_sous_le_seuil_rien_n_est_differe(_redirect, monkeypatch, horloge, espion):
    """W3. M3 (`SEUIL_S = 0`) -> différé à +0,5 s d'un calcul de 0,1 s, rouge."""
    td._ingest_otel(_redirect, _lignes(1))
    _duree(monkeypatch, horloge, 0.1)
    dashboard._read_canal_b()
    debut = canal_b._etat["debut"]
    _ajouter(_redirect, _lignes(1, depart=1), "2026-07-27.2.jsonl")
    horloge.t = debut + 0.5
    espion["c"] = 0
    v2 = dashboard._read_canal_b()
    assert espion["c"] > 0 and v2["rows_read"] == 2 and v2["fraicheur"]["differe"] is False


def test_w4_la_lecture_incrementale_egale_un_recalcul_entier(_redirect, espion):
    """W4. M4 (`suite` rend None) -> 53 appels ; M5 (`id >= ?`) -> doublon : rouges."""
    td._ingest_otel(_redirect, _lignes(50))
    assert dashboard._read_canal_b()["rows_read"] == 50 and espion["c"] == 50
    _ajouter(_redirect, _lignes(3, depart=50), "2026-07-27.2.jsonl")
    espion["c"] = 0
    v2 = dashboard._read_canal_b()
    assert espion["c"] == 3, f"{espion['c']} normalisations pour 3 lignes neuves"
    assert v2["rows_read"] == 53
    assert _sans_date(v2) == _sans_date(_entier())


def _retention(_redirect) -> dict:
    td._ingest_otel(_redirect, _lignes(3))
    _ajouter(_redirect, _lignes(2, ts=_RECENT, depart=3), "2026-08-27.1.jsonl")
    v1 = dashboard._read_canal_b()
    assert v1["rows_read"] == 5
    (_redirect["otel_dir"] / "2026-07-27.1.jsonl").unlink()
    return v1


def test_w5_le_repli_de_retention_relit_tout(_redirect, espion):
    """W5, par le VRAI `ingest_once(now=…+31 j)` : relecture entière, les lignes repliées sortent. Le compteur
    `rewrite_generation` avance avec le repli : M15 (repli sans incrément dans `ingest_once`) -> rouge."""
    _retention(_redirect)
    avant = _compteur()
    with event_store.open_store(create=True) as store:
        assert store.ingest_once(now=datetime(2026, 8, 28, 12, tzinfo=timezone.utc)
                                 )["retention"]["rows_folded"] == 3
    assert _compteur() == avant + 1, "le repli n'a pas avancé rewrite_generation"
    espion["c"] = 0
    v2 = dashboard._read_canal_b()
    assert espion["c"] == 2 and v2["rows_read"] == 2
    assert _sans_date(v2) == _sans_date(_entier())


def test_w5b_un_repli_sans_compteur_est_vu_par_les_bornes(_redirect, espion):
    """W5b. Le même repli, écrit par un démon du kit d'AVANT ce ticket (il avance `data_generation`, pas
    `rewrite_generation`) : seules les bornes le voient. M6 (bornes ignorées) -> cumul périmé, rouge."""
    _retention(_redirect)
    with event_store.open_store(create=True) as store:
        store._conn.execute("BEGIN IMMEDIATE")
        fold = store._fold_retention_locked(datetime(2026, 8, 28, 12, tzinfo=timezone.utc), frozenset())
        store._bump_meta_counter_locked("data_generation", 1)
        store._conn.execute("COMMIT")
        assert fold["rows_folded"] == 3
    espion["c"] = 0
    v2 = dashboard._read_canal_b()
    assert v2["rows_read"] == 2, v2["rows_read"]
    assert espion["c"] == 2
    assert _sans_date(v2) == _sans_date(_entier())


def _compteur() -> int:
    with event_store.open_store() as store:
        return store.meta_counter("rewrite_generation")


def test_w6a_une_identite_resolue_a_l_ouverture_avance_le_compteur(_redirect):
    """W6(a). M7 (pas d'incrémentation dans `open_store`) -> rouge."""
    identite = Path(os.environ["AGENTS_PROJECT_JSON"])
    identite.unlink()
    td._ingest_otel(_redirect, _lignes(2))
    avant = _compteur()
    identite.write_text(json.dumps({"project_id": td._OWN_ID}), encoding="utf-8", newline="\n")
    with event_store.open_store(create=True) as store:
        assert store.open_report["relabel"].get("adopted"), store.open_report
    assert _compteur() == avant + 1


def test_w6c_un_increment_refuse_annule_le_lot_lui_meme(_redirect):
    """W6(c), clôture T1. L'incrément vit DANS la transaction du lot : refusé (déclencheur SQLite), le lot
    réécrit est annulé avec lui — jamais des corps réécrits sans compteur. La lecture suivante égale un recalcul
    entier. Mutant : incrément hors du lot (après son COMMIT) -> corps réécrits, cumul périmé, rouge."""
    v1 = _legendes(_redirect)
    with event_store.open_store() as store:
        for moment in ("INSERT", "UPDATE"):
            store._conn.execute(f"CREATE TRIGGER refus_{moment.lower()} BEFORE {moment} ON meta "
                                "WHEN NEW.key = 'rewrite_generation' BEGIN SELECT RAISE(ABORT, 'refus simulé'); END")
    with event_store.open_store(create=True) as store:
        rapport = store.open_report["backfill"]
    assert "refus simulé" in (rapport.get("error") or ""), rapport
    assert rapport.get("rows_materialised") == 0, rapport
    v2 = dashboard._read_canal_b()
    assert _sans_date(v2) == _sans_date(v1) == _sans_date(_entier())


def _legendes(_redirect) -> dict:
    racine = os.environ["AGENTS_OTEL_PROJECT_ROOT"]  # provenance concordante : la passe attribue au projet
    td._ingest_otel(_redirect, [td._legacy_metric_envelope(_ANCIEN, "claude_code.cost.usage", float(i + 1),
                                                           {"model": "m"}, provenance=racine)
                                for i in range(3)])
    v1 = dashboard._read_canal_b()
    assert v1["rows_read"] == 3
    return v1


def _backfill(_redirect) -> dict:
    """Des enveloppes d'avant V1-c, lues ; puis la passe d'ouverture les réécrit EN PLACE."""
    v1 = _legendes(_redirect)
    avant = _compteur()
    with event_store.open_store(create=True) as store:
        assert store.open_report["backfill"].get("rows_materialised") == 3, store.open_report
    assert _compteur() == avant + 1
    return v1


def test_w6b_le_compteur_qui_bouge_relit_tout(_redirect, espion):
    """W6(b). M7b (compteur ignoré par `suite`) -> 0 ligne relue, attribution périmée : rouge."""
    v1 = _backfill(_redirect)
    espion["c"] = 0
    v2 = dashboard._read_canal_b()
    assert espion["c"] == 3, espion["c"]
    assert _sans_date(v2) != _sans_date(v1), "la réécriture ne change rien : témoin sans prise"
    assert _sans_date(v2) == _sans_date(_entier())


def test_w7_le_cumul_est_vide_au_debut_de_toute_relecture_entiere(_redirect, monkeypatch):
    """W7. M8 (pas d'`oublier` avant la relecture entière) -> l'ancien cumul coexiste, rouge."""
    _backfill(_redirect)
    vus = []
    vrai = dashboard._otel_normalize_mod.stream_bodies

    def _espion(bodies):
        vus.append(canal_b._etat["cumul"])
        return vrai(bodies)

    monkeypatch.setattr(dashboard._otel_normalize_mod, "stream_bodies", _espion)
    assert dashboard._read_canal_b()["rows_read"] == 3
    assert vus == [None], vus


def test_w8a_un_store_degrade_n_est_jamais_masque_par_la_valeur_differee(_redirect, monkeypatch, horloge):
    """W8(a), C1. M9 (garde de statut, membre `store_status` et statut de la génération retirés) -> la
    valeur ok est servie : rouge."""
    debut, _v1 = _fenetre(_redirect, monkeypatch, horloge)
    horloge.t = debut + 5

    def _leve(*_a, **_k):
        raise sqlite3.OperationalError("store simulé indisponible")

    monkeypatch.setattr(dashboard._event_store_mod, "open_store", _leve)
    section = dashboard._read_canal_b()
    assert section["status"] == "degraded" and section["source"] == "unavailable", section
    assert "fraicheur" not in section


def test_w8b_une_identite_changee_recalcule_dans_la_fenetre(_redirect, monkeypatch, horloge):
    """W8(b), C1. M9b (identité exclue de la comparaison) -> l'ancienne attribution servie : rouge."""
    debut, _v1 = _fenetre(_redirect, monkeypatch, horloge)
    horloge.t = debut + 5
    Path(os.environ["AGENTS_PROJECT_JSON"]).write_text(json.dumps({"project_id": "autre-projet-0002"}),
                                                       encoding="utf-8", newline="\n")
    section = dashboard._read_canal_b()
    assert section["attribution"]["own_project_id"] == "autre-projet-0002"
    assert section["fraicheur"]["differe"] is False


def test_w9_un_flux_incremental_mort_degrade_puis_reprend_au_meme_filigrane(_redirect, monkeypatch, espion):
    """W9, C7. Une lecture INCRÉMENTALE meurt en plein flux : `degraded` ; l'appel suivant relit les SEULES
    lignes neuves et rend un recalcul entier. M10 (cumul et filigrane écrits avant la fin du flux) : rouge."""
    td._ingest_otel(_redirect, _lignes(50))
    dashboard._read_canal_b()
    _ajouter(_redirect, _lignes(3, depart=50), "2026-07-27.2.jsonl")
    vrai = dashboard._event_store_mod.EventStore.iter_canal_b_bodies

    def _meurt(self, apres=None):
        assert apres is not None, "la lecture devait être incrémentale"
        for rang, body in enumerate(vrai(self, apres=apres)):
            if rang == 1:
                raise sqlite3.OperationalError("flux mort simulé")
            yield body

    with monkeypatch.context() as m:
        m.setattr(dashboard._event_store_mod.EventStore, "iter_canal_b_bodies", _meurt)
        mort = dashboard._read_canal_b()
    assert mort["status"] == "degraded" and mort["source"] == "unavailable", mort
    assert "flux mort simulé" in mort["reason"]
    espion["c"] = 0
    v2 = dashboard._read_canal_b()
    assert espion["c"] == 3, f"{espion['c']} normalisations : l'état a bougé avec le flux mort"
    assert v2["rows_read"] == 53
    assert _sans_date(v2) == _sans_date(_entier())


def test_canal_b_bornes_et_filigrane_d_une_lecture_complete(_redirect):
    """Le contrat côté store : `canal_b_lu` n'existe qu'à une lecture COMPLÈTE, et `canal_b_bornes` le rejoue."""
    td._ingest_otel(_redirect, _lignes(4))
    with event_store.open_store() as store:
        flux = store.iter_canal_b_bodies()
        next(flux)
        assert store.canal_b_lu is None
        with contextlib.closing(flux):
            pass
        assert store.canal_b_lu is None, "une lecture abandonnée a posé un filigrane"
        assert len(list(store.iter_canal_b_bodies())) == 4
        premier, dernier, lignes, empreinte = store.canal_b_lu
        assert lignes == 4 and empreinte and store.canal_b_bornes(dernier) == (premier, 4, empreinte)
        assert list(store.iter_canal_b_bodies(apres=dernier)) == [] and store.canal_b_lu == (None, None, 0, None)


def _variantes(_redirect):
    """Le VRAI mémo du transport, une case et une clé par variante (`VARIANTES`), sur la VRAIE clé du snapshot."""
    memo, vus = transport.MemoCorps(), []
    racine = _redirect["project_root"]

    def _construire(variante):
        section = dashboard._read_canal_b()
        vus.append((variante, section["rows_read"], section["fraicheur"]["differe"]))
        return {"canal_b": section}

    def _poll(variante):
        transport.entree(memo, construire=_construire, variante=variante,
                         empreinte=lambda: transport.empreinte_snapshot(racine, dashboard._SNAPSHOT_SOURCES))

    return memo, vus, _poll


def test_w10_l_echeance_franchie_par_une_variante_reconstruit_l_autre(_redirect, monkeypatch, horloge):
    """W10 (exec-critic, bloquant 1). La variante 1 franchit l'échéance et provoque le recalcul ; la variante 2
    doit être reconstruite aussi et servir la valeur fraîche. Une construction par variante et par événement,
    jamais une de trop (mineur 2). Mutants : jeton global d'avant (None après le recalcul) -> la variante 2
    garde son différé, rouge ; M13 (`servir` ne finit pas le différé) -> une construction de trop, rouge."""
    debut, _v1 = _fenetre(_redirect, monkeypatch, horloge)
    memo, vus, poll = _variantes(_redirect)
    horloge.t = debut + 5
    for variante in (1, 2, 1, 2):  # ouverture du différé : une construction par variante, puis rien
        poll(variante)
    assert vus == [(1, 1, True), (2, 1, True)], vus
    horloge.t = debut + 10.5
    for variante in (1, 2, 1, 2):
        poll(variante)
    assert vus[2:] == [(1, 2, False), (2, 2, False)], vus
    assert memo.constructions == 4, memo.constructions
    horloge.t = debut + 5000
    poll(1)
    poll(2)
    assert memo.constructions == 4, "une construction au repos après le recalcul"


def test_w12_le_jeton_ne_bouge_pas_au_repos(_redirect, monkeypatch, horloge):
    """W12 (exec-critic, mineur 3). Une valeur calculée en 1,0 s, AUCUN différé servi : l'échéance passe sans
    changer la clé. M11 (le jeton ignore `differe`) -> la clé bouge au repos, rouge."""
    td._ingest_otel(_redirect, _lignes(1))
    _duree(monkeypatch, horloge, 1.0)
    dashboard._read_canal_b()
    debut, racine = canal_b._etat["debut"], _redirect["project_root"]
    cle = transport.empreinte_snapshot(racine, dashboard._SNAPSHOT_SOURCES)
    horloge.t = debut + 20
    assert transport.empreinte_snapshot(racine, dashboard._SNAPSHOT_SOURCES) == cle


def test_w11_le_chemin_sans_store_ne_garde_aucun_cumul(_redirect):
    """W11 (survivant M14). Le store disparaît : la lecture des fichiers ne garde pas le cumul résident de la
    base d'avant. M14 (chemin `absent` sans `oublier`) -> cumul encore là, rouge."""
    td._ingest_otel(_redirect, _lignes(2))
    assert dashboard._read_canal_b()["source"] == "sqlite" and canal_b._etat["cumul"] is not None
    base = Path(event_store.store_fingerprint()[0])
    for chemin in (base, Path(f"{base}-wal"), Path(f"{base}-shm")):
        chemin.unlink(missing_ok=True)
    section = dashboard._read_canal_b()
    assert section["source"] == "spool_files", section
    assert canal_b._etat["cumul"] is None and canal_b._etat["filigrane"] is None


def test_w13_des_ids_reutilises_apres_un_repli_ne_passent_pas_pour_les_memes_lignes(_redirect):
    """W13, clôture T2 (sonde h1 du critique). Tout le canal replié par un démon du kit d'AVANT (sans
    `rewrite_generation`), puis trois lignes neuves : SQLite (sans AUTOINCREMENT) RÉUTILISE les ids, et
    (MIN, COUNT) au filigrane sont identiques. Le `line_hash` de la dernière ligne lue nomme la ligne.
    Mutant : hash ignoré par `suite` -> 6.0 USD servis au lieu de 306.0, rouge."""
    td._ingest_otel(_redirect, _lignes(3))
    assert dashboard._read_canal_b()["cost"]["native_usd"] == 6.0
    (_redirect["otel_dir"] / "2026-07-27.1.jsonl").unlink()
    with event_store.open_store(create=True) as store:
        store._conn.execute("BEGIN IMMEDIATE")
        store._fold_retention_locked(datetime(2026, 8, 28, 12, tzinfo=timezone.utc), frozenset())
        store._bump_meta_counter_locked("data_generation", 1)
        store._conn.execute("COMMIT")
    _ajouter(_redirect, _lignes(3, ts=_RECENT, depart=100), "2026-08-27.1.jsonl")
    v2 = dashboard._read_canal_b()
    assert v2["cost"]["native_usd"] == 306.0, v2["cost"]["native_usd"]
    assert _sans_date(v2) == _sans_date(_entier())


def test_w14_un_compteur_illisible_degrade_au_lieu_de_valoir_zero(_redirect, monkeypatch):
    """W14, clôture T3. `meta_counter` avale l'erreur et rend 0 ; la décision incrémentale lit le compteur par
    `canal_b_reecriture`, qui LÈVE : canal `unavailable`, jamais un cumul ajouté sur un 0 inventé.
    Mutant : `suite` relit par `meta_counter` -> lecture servie ok, rouge."""
    td._ingest_otel(_redirect, _lignes(2))
    dashboard._read_canal_b()
    with event_store.open_store() as store:
        store._conn.execute("ALTER TABLE meta RENAME TO meta_cachee")
        try:
            assert store.meta_counter("rewrite_generation") == 0
            with pytest.raises(sqlite3.Error):
                store.canal_b_reecriture()
        finally:
            store._conn.execute("ALTER TABLE meta_cachee RENAME TO meta")
    _ajouter(_redirect, _lignes(1, depart=2), "2026-07-27.2.jsonl")

    def _illisible(self):
        raise sqlite3.OperationalError("meta illisible simulée")

    monkeypatch.setattr(dashboard._event_store_mod.EventStore, "canal_b_reecriture", _illisible)
    section = dashboard._read_canal_b()
    assert section["status"] == "degraded" and section["source"] == "unavailable", section
    assert "meta illisible simulée" in section["reason"]


def test_w15_un_lot_incremental_degrade_dit_que_rows_read_ne_compte_que_le_lot(_redirect, monkeypatch):
    """W15, clôture (trou 5). Une normalisation qui échoue en plein flux INCRÉMENTAL : `rows_read` ne compte
    que le lot, et le payload le dit (`rows_read_scope: increment`) ; sur une lecture entière, `full`."""
    td._ingest_otel(_redirect, _lignes(5))
    dashboard._read_canal_b()
    _ajouter(_redirect, _lignes(2, depart=5), "2026-07-27.2.jsonl")
    vrai = dashboard._otel_normalize_mod.stream_bodies

    def _casse(bodies):
        for _ in bodies:
            raise ValueError("normalisation cassée simulée")
        return vrai([])

    monkeypatch.setattr(dashboard._otel_normalize_mod, "stream_bodies", _casse)
    section = dashboard._read_canal_b()
    assert section["status"] == "degraded" and section["rows_read"] == 1, section
    assert section["rows_read_scope"] == "increment"
    dashboard._reset_canal_b_cache_for_tests()
    assert dashboard._read_canal_b()["rows_read_scope"] == "full"


def test_w16_la_lecture_de_canal_b_du_snapshot_tient_le_verrou_du_processus(_redirect, monkeypatch):
    """W16, clôture (trou 4). `_etat` est global au processus, le verrou du transport par serveur : le snapshot
    lit canal B sous `dashboard_canal_b.VERROU`. Mutant : appel sans `sous_verrou` -> rouge."""
    vus = []
    vrai = dashboard._read_canal_b

    def _espion():
        vus.append(canal_b.VERROU.locked())
        return vrai()

    monkeypatch.setattr(dashboard, "_read_canal_b", _espion)
    dashboard.build_snapshot(_redirect["project_root"])
    assert vus == [True], vus
    assert not canal_b.VERROU.locked()
