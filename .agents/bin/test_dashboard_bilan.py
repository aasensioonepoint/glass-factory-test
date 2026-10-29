"""Témoins du dernier bilan de setup servi par `/api/snapshot` (T-01M5A1244ZHSSA8RPCZYDJ49XE, lot S de
T-01M54GEA4BNFC7QDJVK6P53Y4B).

Le CONTRAT est écrit par `setup_bilan.py` (lot B) dans `.agents/state/local/setup-bilan.json` :
`{"schema": 1, "genere_le", "rc", "jambes": [{"jambe", "etat", "detail", "remede"}], "commande"}`. Ce banc
fabrique ses PROPRES fichiers de bilan sur une racine jetable : il ne lit jamais celui du développeur.

Rougissent : `read_setup_bilan` absent, ok, degraded (au-delà de 64 Kio — borne EXACTE éprouvée —, JSON
illisible, octets non UTF-8, imbrication trop profonde, NaN / Infinity, forme fausse, aucune jambe, `etat` hors
vocabulaire — `repr` tronqué, conteneur nommé par son type —, `schema` booléen, substitut UTF-16 isolé,
`genere_le` hors ISO, `rc` incohérent avec les jambes, lien symbolique — avec ou sans `O_NOFOLLOW` —, FIFO sans
blocage) ; la garde générale du gabarit (`/api/snapshot` réel : 200 dégradé borné, jamais une connexion coupée,
quelle que soit la section non sérialisable) ; la lecture BORNÉE (espion sur
`open`, au plus 64 Kio + 1 octet lus d'un fichier de 4 Mio) ; la clé RACINE `setup` du snapshot ; `views`
inchangé (`_EXPECTED_VIEW_KEYS` relu dans `test_dashboard.py`, jamais recopié) ; l'empreinte de transport qui
bouge quand le bilan est réécrit ou paraît, et son mutant `FICHIERS_HORS_VUES` sans l'entrée, qui la laisse
immobile (CONVENTIONS_python.md : « A test must be able to fail »).
"""
from __future__ import annotations

import ast
import http.client
import importlib.util
import json
import os
import sys
import threading
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("_banc_bilan_dashboard", HERE / "dashboard.py")
dashboard = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = dashboard
_spec.loader.exec_module(dashboard)

readers = dashboard._readers_mod
transport = dashboard._transport_mod

_REL = (".agents", "state", "local", "setup-bilan.json")
_BORNE = 64 * 1024


def _vues_attendues() -> set[str]:
    """`_EXPECTED_VIEW_KEYS` tel que `test_dashboard.py` le gèle : relu, jamais recopié ici."""
    arbre = ast.parse((HERE / "test_dashboard.py").read_text(encoding="utf-8"))
    for noeud in arbre.body:
        cibles = noeud.targets if isinstance(noeud, ast.Assign) else []
        if any(isinstance(c, ast.Name) and c.id == "_EXPECTED_VIEW_KEYS" for c in cibles):
            return set(ast.literal_eval(noeud.value))
    raise AssertionError("_EXPECTED_VIEW_KEYS introuvable dans test_dashboard.py")


@pytest.fixture
def racine(tmp_path, monkeypatch):
    """Le même isolement que `test_dashboard._redirect` : aucune entrée du développeur n'est lue."""
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("AGENTS_DASHBOARD_PROJECT_ROOT", str(root))
    monkeypatch.setenv("AGENTS_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("AGENTS_OTEL_DIR", str(tmp_path / "otel"))
    monkeypatch.setenv("AGENTS_PROJECT_JSON", str(tmp_path / "project.json"))
    monkeypatch.setenv("AGENTS_OTEL_PROJECT_ROOT", str(tmp_path / "own-root"))
    monkeypatch.setenv("AGENTKIT_REGISTRY", str(tmp_path / "registry.json"))
    monkeypatch.setenv("AGENTS_TERM_DIR", str(tmp_path / "term"))
    (tmp_path / "project.json").write_text(json.dumps({"project_id": "banc-bilan"}), encoding="utf-8")
    dashboard._reset_canal_b_cache_for_tests()
    dashboard._reset_canal_a_cache_for_tests()
    readers.reset_cache_for_tests()
    yield root
    dashboard._reset_canal_b_cache_for_tests()
    dashboard._reset_canal_a_cache_for_tests()
    readers.reset_cache_for_tests()


def _bilan(**champs) -> dict:
    base = {
        "schema": 1, "genere_le": "2026-10-20T08:00:00Z", "rc": 1,
        "jambes": [
            {"jambe": "outils", "etat": "OK", "detail": "doctor: 12/12 présents", "remede": None},
            {"jambe": "interpréteur", "etat": "KO", "detail": "python3 3.9.6 (/usr/bin/python3)",
             "remede": "installer Python ≥ 3.11 et le placer avant dans le PATH"},
            {"jambe": "portes", "etat": "SANS OBJET", "detail": "kit", "remede": None},
        ],
        "commande": "python3 .agents/bin/setup_bilan.py",
    }
    base.update(champs)
    return base


def _ecrire(root: Path, contenu: bytes | dict) -> Path:
    chemin = root.joinpath(*_REL)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_bytes(contenu if isinstance(contenu, bytes) else json.dumps(contenu).encode("utf-8"))
    return chemin


def _taille_exacte(n: int) -> bytes:
    """Un bilan VALIDE de `n` octets exactement : le JSON admet des blancs en queue."""
    brut = json.dumps(_bilan()).encode("utf-8")
    assert len(brut) < n
    return brut + b" " * (n - len(brut))


# --------------------------------------------------------------------------- le lecteur

def test_absent(racine):
    lu = readers.read_setup_bilan(racine)
    assert lu["status"] == "absent"
    assert lu["jambes"] == [] and lu["rc"] is None and lu["genere_le"] is None and lu["commande"] is None
    assert "setup-bilan.json" in lu["reason"]


def test_ok_rend_les_champs_du_contrat(racine):
    _ecrire(racine, _bilan())
    lu = readers.read_setup_bilan(racine)
    assert lu["status"] == "ok", lu
    assert lu["reason"] is None
    assert lu["genere_le"] == "2026-10-20T08:00:00Z" and lu["rc"] == 1
    assert lu["commande"] == "python3 .agents/bin/setup_bilan.py"
    assert lu["jambes"] == _bilan()["jambes"]
    assert set(lu) == {"status", "reason", "genere_le", "rc", "jambes", "commande"}


def test_borne_exacte_64_kio(racine):
    _ecrire(racine, _taille_exacte(_BORNE))
    assert readers.read_setup_bilan(racine)["status"] == "ok", "un bilan de 64 Kio pile reste lisible"
    _ecrire(racine, _taille_exacte(_BORNE + 1))
    lu = readers.read_setup_bilan(racine)
    assert lu["status"] == "degraded" and "64 Kio" in lu["reason"], lu
    assert lu["jambes"] == []


@pytest.mark.parametrize("brut, mot", [
    (b"{pas du json", "illisible"),
    (b"\xff\xfe{}", "illisible"),
    (b"", "illisible"),
])
def test_json_illisible_degrade(racine, brut, mot):
    _ecrire(racine, brut)
    lu = readers.read_setup_bilan(racine)
    assert lu["status"] == "degraded" and mot in lu["reason"], lu
    assert lu["jambes"] == []


@pytest.mark.parametrize("contenu", [
    [1, 2],
    _bilan(jambes={"outils": "OK"}),
    _bilan(jambes=["outils"]),
], ids=["racine-liste", "jambes-objet", "jambe-chaine"])
def test_forme_fausse_degrade(racine, contenu):
    _ecrire(racine, contenu)
    lu = readers.read_setup_bilan(racine)
    assert lu["status"] == "degraded" and "forme" in lu["reason"], lu


@pytest.mark.parametrize("etat", ["ok", "PEUT-ÊTRE", None, ""])
def test_etat_hors_vocabulaire_degrade(racine, etat):
    contenu = _bilan()
    contenu["jambes"][1]["etat"] = etat
    _ecrire(racine, contenu)
    lu = readers.read_setup_bilan(racine)
    assert lu["status"] == "degraded" and "hors vocabulaire" in lu["reason"], lu
    assert lu["jambes"] == []


def test_illisible_par_l_os_degrade(racine):
    chemin = _ecrire(racine, _bilan())
    chemin.unlink()
    chemin.mkdir()  # un dossier à la place du fichier : `open` lève, ce n'est pas une absence
    lu = readers.read_setup_bilan(racine)
    assert lu["status"] == "degraded", lu


def test_imbrication_trop_profonde_degrade(racine, monkeypatch):
    """3.11 et 3.12 lèvent `RecursionError` sur un JSON très imbriqué (3.14 le masque) : forcé ici, partout."""
    _ecrire(racine, _bilan())

    def leve(*_a, **_k):
        raise RecursionError("profond")

    monkeypatch.setattr(readers.json, "loads", leve)
    lu = readers.read_setup_bilan(racine)
    assert lu["status"] == "degraded" and "illisible" in lu["reason"] and lu["jambes"] == [], lu


@pytest.mark.parametrize("constante", ["NaN", "Infinity", "-Infinity"])
def test_constante_non_json_degrade(racine, constante):
    brut = json.dumps(_bilan()).replace('"rc": 1', f'"rc": {constante}').encode("utf-8")
    assert constante.encode() in brut
    _ecrire(racine, brut)
    lu = readers.read_setup_bilan(racine)
    assert lu["status"] == "degraded" and "illisible" in lu["reason"], lu


def test_aucune_jambe_degrade(racine):
    _ecrire(racine, _bilan(jambes=[]))
    lu = readers.read_setup_bilan(racine)
    assert lu["status"] == "degraded" and "aucune jambe" in lu["reason"], lu


def test_lecture_bornee_meme_sur_un_gros_fichier(racine, monkeypatch):
    """Au plus 64 Kio + 1 octet LUS, quelle que soit la taille du fichier : un espion sur `open` du lecteur."""
    _ecrire(racine, b" " * (4 * 1024 * 1024))
    lus: list[int] = []
    vrai_open = open

    class Espion:
        def __init__(self, fichier):
            self.fichier = fichier

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return self.fichier.__exit__(*exc)

        def __getattr__(self, nom):
            return getattr(self.fichier, nom)

        def read(self, *args):
            bloc = self.fichier.read(*args)
            lus.append(len(bloc))
            return bloc

    monkeypatch.setattr(readers, "open", lambda *a, **k: Espion(vrai_open(*a, **k)), raising=False)
    assert readers.read_setup_bilan(racine)["status"] == "degraded"
    assert lus and sum(lus) <= readers.SETUP_BILAN_MAX + 1, lus


def test_lien_symbolique_jamais_suivi(racine, tmp_path):
    ailleurs = tmp_path / "ailleurs.json"
    ailleurs.write_text(json.dumps(_bilan()), encoding="utf-8")
    chemin = racine.joinpath(*_REL)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.symlink_to(ailleurs)
    lu = readers.read_setup_bilan(racine)
    assert lu["status"] == "degraded" and lu["jambes"] == [], lu
    if readers._SANS_SUIVRE:  # POSIX : le refus d'O_NOFOLLOW (ELOOP) est NOMMÉ, pas un « OSError » muet
        assert "lien symbolique" in lu["reason"], lu


def test_absent_dossier_present_rien_cree(racine):
    """Le lecteur n'écrit jamais : un `O_CREAT` glissé dans l'opener créerait le bilan quand le dossier existe."""
    chemin = racine.joinpath(*_REL)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    assert readers.read_setup_bilan(racine)["status"] == "absent"
    assert not os.path.lexists(chemin), "le lecteur a créé le bilan"


def test_opener_sans_drapeau_d_ecriture(racine, monkeypatch):
    _ecrire(racine, _bilan())
    vus: list = []
    vrai = os.open

    def espion(*a, **k):
        vus.append(k.get("flags", a[1] if len(a) > 1 else None))
        return vrai(*a, **k)

    monkeypatch.setattr(readers.os, "open", espion)
    assert readers.read_setup_bilan(racine)["status"] == "ok"
    ecrit = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
    assert vus and all(f & ecrit == 0 for f in vus), vus


# --------------------------------------------------------------------------- le CONTRAT typé

def _jambe_mutee(**champs) -> dict:
    jambe = {"jambe": "outils", "etat": "OK", "detail": "d", "remede": None}
    jambe.update(champs)
    return _bilan(jambes=[jambe])


def _sans(cle: str, contenu: dict) -> dict:
    contenu.pop(cle)
    return contenu


@pytest.mark.parametrize("contenu", [
    _bilan(rc="x"), _bilan(rc=2), _bilan(rc=True), _bilan(genere_le=5), _bilan(commande=7), _bilan(schema=2),
    _bilan(schema="1"), _bilan(schema=True), _bilan(x=1), _sans("commande", _bilan()), _sans("schema", _bilan()),
    _jambe_mutee(detail={"a": 1}), _jambe_mutee(remede=[1]), _jambe_mutee(jambe=None), _jambe_mutee(x="y"),
    _jambe_mutee(detail=None), {**_bilan(), "jambes": [_sans("remede", _jambe_mutee()["jambes"][0])]},
], ids=["rc-chaine", "rc-2", "rc-bool", "genere_le-nombre", "commande-nombre", "schema-2", "schema-chaine",
        "schema-bool", "cle-inconnue-entete", "commande-absente", "schema-absent", "detail-objet", "remede-liste",
        "jambe-null", "cle-inconnue-jambe", "detail-null", "remede-absent"])
def test_hors_contrat_degrade(racine, contenu):
    _ecrire(racine, contenu)
    lu = readers.read_setup_bilan(racine)
    assert lu["status"] == "degraded" and "hors contrat" in lu["reason"] and lu["jambes"] == [], lu


def test_etat_conteneur_nomme_par_son_type(racine):
    _ecrire(racine, _jambe_mutee(etat=[1]))
    lu = readers.read_setup_bilan(racine)
    assert lu["status"] == "degraded" and "<list>" in lu["reason"], lu


def test_etat_long_tronque_dans_la_raison(racine):
    """Un `etat` de 60 000 caractères : la raison servie reste courte (`repr` tronqué à 40)."""
    _ecrire(racine, _jambe_mutee(etat="x" * 60_000))
    lu = readers.read_setup_bilan(racine)
    assert lu["status"] == "degraded" and "hors vocabulaire 'xxx" in lu["reason"], lu
    assert len(lu["reason"]) < 120, len(lu["reason"])


@pytest.mark.parametrize("champs, mot", [
    ({"genere_le": "pas une date"}, "genere_le hors contrat"),
    ({"genere_le": ""}, "genere_le hors contrat"),
    ({"rc": 0}, "rc incohérent"),
    ({"rc": 1, "jambes": [{"jambe": "outils", "etat": "OK", "detail": "d", "remede": None}]}, "rc incohérent"),
], ids=["genere_le-texte", "genere_le-vide", "rc-0-avec-un-KO", "rc-1-sans-KO"])
def test_contrat_semantique_degrade(racine, champs, mot):
    """`genere_le` lu par `fromisoformat`, `rc` recalculé des jambes : ce que l'écrivain (lot B) garantit."""
    _ecrire(racine, _bilan(**champs))
    lu = readers.read_setup_bilan(racine)
    assert lu["status"] == "degraded" and mot in lu["reason"] and lu["jambes"] == [], lu


def test_genere_le_de_l_ecrivain_reste_ok(racine):
    """La forme que `setup_bilan.py` écrit (`isoformat`, `+00:00`, microsecondes) et un `rc` 0 sans KO."""
    jambes = [{"jambe": "outils", "etat": "OK", "detail": "d", "remede": None},
              {"jambe": "portes", "etat": "SANS OBJET", "detail": "kit", "remede": None}]
    _ecrire(racine, _bilan(genere_le="2026-10-20T08:00:00.123456+00:00", rc=0, jambes=jambes))
    assert readers.read_setup_bilan(racine)["status"] == "ok"


@pytest.mark.parametrize("champ", ["detail", "remede", "jambe", "genere_le", "commande"])
def test_substitut_isole_jamais_servi(racine, champ):
    """`"\\ud800"` est du JSON valide : `json.loads` le rend, `.encode("utf-8")` le refuse. Le bilan reste
    cohérent (`rc` 1, une jambe KO) : seul le substitut peut le dégrader."""
    contenu = _bilan()
    cible = contenu if champ in ("genere_le", "commande") else contenu["jambes"][1]
    cible[champ] = "§"
    brut = json.dumps(contenu, ensure_ascii=False).replace('"§"', '"\\ud800"')
    assert '"\\ud800"' in brut, "substitut non posé : le témoin serait creux"
    _ecrire(racine, brut.encode("utf-8"))
    lu = readers.read_setup_bilan(racine)
    assert lu["status"] == "degraded" and "substitut" in lu["reason"] and lu["jambes"] == [], lu
    corps = json.loads(transport.serialiser(dashboard.build_snapshot(racine)))
    assert corps["setup"]["status"] == "degraded"


@pytest.mark.parametrize("ou", ["detail", "x", "entete"])
def test_imbrication_jamais_servie_au_transport(racine, ou):
    """d = 1200 : sous 3.12+ le décodeur C l'accepte, l'encodeur pur Python de `serialiser` ne sait pas la
    réécrire. Le lecteur la refuse (au parse sous 3.11, au contrat ailleurs) et le snapshot se sérialise."""
    contenu = _bilan(x="§") if ou == "entete" else _jambe_mutee(**{ou: "§"})
    brut = json.dumps(contenu, ensure_ascii=False).replace('"§"', "[" * 1200 + "]" * 1200).encode("utf-8")
    assert b"[" * 1200 in brut, "imbrication non posée : le témoin serait creux"
    _ecrire(racine, brut)
    lu = readers.read_setup_bilan(racine)
    assert lu["status"] == "degraded", lu
    corps = json.loads(transport.serialiser(dashboard.build_snapshot(racine)))
    assert corps["setup"]["status"] == "degraded"


def test_bilan_sain_traverse_serialiser(racine):
    _ecrire(racine, _bilan())
    corps = json.loads(transport.serialiser(dashboard.build_snapshot(racine)))
    assert corps["setup"] == {"status": "ok", "reason": None, "genere_le": "2026-10-20T08:00:00Z", "rc": 1,
                              "jambes": _bilan()["jambes"], "commande": "python3 .agents/bin/setup_bilan.py"}


def test_lien_symbolique_sans_o_nofollow_jamais_suivi(racine, tmp_path, monkeypatch):
    """Le repli d'un hôte sans `O_NOFOLLOW` (Windows) : `islink` avant d'ouvrir."""
    monkeypatch.setattr(readers, "_SANS_SUIVRE", 0)
    ailleurs = tmp_path / "ailleurs.json"
    ailleurs.write_text(json.dumps(_bilan()), encoding="utf-8")
    chemin = racine.joinpath(*_REL)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.symlink_to(ailleurs)
    lu = readers.read_setup_bilan(racine)
    assert lu["status"] == "degraded" and "lien symbolique" in lu["reason"], lu


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="pas de FIFO sur cet hôte (Windows) : témoin sauté, DIT")
def test_fifo_degrade_sans_bloquer(racine):
    """Une FIFO sans écrivain BLOQUERAIT un `open` en lecture : le lecteur rend la main et dit pourquoi."""
    chemin = racine.joinpath(*_REL)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    os.mkfifo(chemin)
    lu: dict = {}
    fil = threading.Thread(target=lambda: lu.update(readers.read_setup_bilan(racine)), daemon=True)
    fil.start()
    fil.join(timeout=5)
    bloque = fil.is_alive()
    if bloque:  # débloque le lecteur pour ne pas laisser un fil pendu : un écrivain paraît, puis s'en va
        os.close(os.open(chemin, os.O_WRONLY | os.O_NONBLOCK))
        fil.join(timeout=5)
    assert not bloque, "le lecteur reste bloqué sur une FIFO"
    assert lu["status"] == "degraded" and "pas un fichier régulier" in lu["reason"], lu


# --------------------------------------------------------------------------- le snapshot

def test_snapshot_sert_la_cle_racine_setup(racine):
    assert dashboard.build_snapshot(racine)["setup"]["status"] == "absent"
    _ecrire(racine, _bilan())
    snap = dashboard.build_snapshot(racine)
    assert snap["setup"] == readers.read_setup_bilan(racine)
    assert snap["setup"]["status"] == "ok"
    assert "setup" not in snap["views"]
    assert set(snap["views"]) == _vues_attendues()


# --------------------------------------------------------------------------- l'empreinte de transport

def _la_cle_bouge(root: Path) -> bool:
    """Le bilan réécrit (taille et mtime changés) PUIS paru d'une absence : vrai si la clé bouge chaque fois."""
    chemin = _ecrire(root, _bilan())
    sources = dashboard._SNAPSHOT_SOURCES
    base = transport.empreinte_snapshot(root, sources)
    assert transport.empreinte_snapshot(root, sources) == base, "clé instable au repos : témoin invalide"
    _ecrire(root, _bilan(rc=0, genere_le="2026-10-20T09:00:00Z"))
    st = os.stat(chemin)
    os.utime(chemin, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
    reecrit = transport.empreinte_snapshot(root, sources) != base
    chemin.unlink()
    avant = transport.empreinte_snapshot(root, sources)
    _ecrire(root, _bilan())
    paru = transport.empreinte_snapshot(root, sources) != avant
    return reecrit and paru


def test_bilan_reecrit_fait_bouger_l_empreinte(racine):
    assert _la_cle_bouge(racine)


# --------------------------------------------------------------------------- la garde générale du transport

def _profond(n: int) -> list:
    valeur: list = []
    for _ in range(n):
        valeur = [valeur]
    return valeur


@pytest.mark.parametrize("piege", ["substitut", "imbrication"])
def test_snapshot_jamais_tue_par_une_section_non_serialisable(racine, monkeypatch, piege):
    """N'IMPORTE QUELLE source — ici une section qui contourne son lecteur : `/api/snapshot` réel répond 200,
    un corps dégradé BORNÉ qui nomme le type, jamais la donnée ; un mutant sans la garde coupe la connexion."""
    poison = "\ud800" if piege == "substitut" else _profond(5000)
    monkeypatch.setattr(readers, "read_setup_bilan", lambda _r: {"status": "ok", "reason": poison})
    httpd, token = dashboard.create_ui_server(project_root=racine)
    fil = threading.Thread(target=httpd.serve_forever, daemon=True)
    fil.start()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=30)
        try:
            conn.request("GET", "/api/snapshot", headers={"Authorization": f"Bearer {token}"})
            reponse = conn.getresponse()
            statut, corps = reponse.status, reponse.read()
        finally:
            conn.close()
    finally:
        httpd.shutdown()
        httpd.server_close()
        fil.join(timeout=5)
    assert statut == 200
    servi = json.loads(corps)
    attendu = "UnicodeEncodeError" if piege == "substitut" else "RecursionError"
    assert set(servi) == {"status", "reason"} and servi["status"] == "degraded", servi
    assert servi["reason"].startswith(f"snapshot non sérialisable : {attendu}"), servi
    assert len(corps) < 200, len(corps)


def test_mutant_fichiers_hors_vues_sans_le_bilan_rougit(racine, monkeypatch):
    sans = tuple(rel for rel in transport.FICHIERS_HORS_VUES if rel != _REL)
    assert len(sans) == len(transport.FICHIERS_HORS_VUES) - 1, "le bilan n'est pas dans FICHIERS_HORS_VUES"
    monkeypatch.setattr(transport, "FICHIERS_HORS_VUES", sans)  # MUTANT : le bilan hors de la clé
    assert not _la_cle_bouge(racine)
