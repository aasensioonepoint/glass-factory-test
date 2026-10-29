"""Contrat de views.chrono : journaux réels, cycles, service complet et cache."""
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("_dashboard_chrono_test", HERE / "dashboard_readers.py")
readers = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = readers
spec.loader.exec_module(readers)
chrono = readers._chrono_module()
TID = "T-01M5KP1ZMSCDZM804QA8H1TRC2"
LOT_A = "T-101"
LOT_B = "T-102"
T0 = 1_792_730_000_000
VIDE = {"status": "ok", "data": {"entries": []}}


def _cycle(root: Path, tid: str = TID, debut: int = T0) -> None:
    chrono.commencer(root, tid, now_ms=debut)


def _etape(root: Path, nom: str, phase: str, ts: int, lot: str | None = None, tid: str = TID) -> None:
    chrono.etape(root, tid, nom, phase, lot=lot, now_ms=ts)


def _id_ulid(ms: int) -> str:
    n = ms
    chars = []
    for _ in range(10):
        chars.append(readers._ULID_ALPHABET[n % 32])
        n //= 32
    return "S-" + "".join(reversed(chars)) + "0000000000000000"


def _verdict(ms: int, texte: str, titre: str = "plan-critic GO") -> dict:
    return {"id": _id_ulid(ms), "task": TID, "kind": "verdict", "title": titre,
            "text": texte, "date": "2026-10-23"}


def _frise_source() -> str:
    # Chez l'adoptant, `.template-exclude` retire ui-src/ : le témoin croisé n'a rien à lire.
    chemin = HERE.parent / "ui-src" / "src" / "lib" / "frise.js"
    if not chemin.is_file():
        pytest.skip("source du front absente (arbre livré sans ui-src)")
    return chemin.read_text(encoding="utf-8")


def _sans_commentaires_js(source: str) -> str:
    """Le code JS sans ses commentaires `//` (en tête OU en fin de ligne) ni `/* … */` (une ou plusieurs
    lignes) ; les chaînes '…', "…" et `…` sont gardées entières. BORNE : un littéral regex n'est pas reconnu."""
    out, i, n, quote = [], 0, len(source), None
    while i < n:
        c = source[i]
        if quote:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(source[i + 1])
                i += 1
            elif c == quote:
                quote = None
        elif c in "'\"`":
            quote = c
            out.append(c)
        elif source.startswith("//", i):
            fin = source.find("\n", i)
            i = n if fin == -1 else fin
            continue
        elif source.startswith("/*", i):
            fin = source.find("*/", i + 2)
            fin = n if fin == -1 else fin + 2
            out.append("\n" * source.count("\n", i, fin))
            i = fin
            continue
        else:
            out.append(c)
        i += 1
    return "".join(out)


def test_t1_ordre_vient_du_module(tmp_path, monkeypatch):
    _cycle(tmp_path)
    _etape(tmp_path, "dev", "begin", T0 + 1000)
    monkeypatch.setattr(chrono, "ETAPES", tuple(reversed(chrono.ETAPES)))
    lu = readers.build_chrono(tmp_path, VIDE, T0 + 2000)
    assert lu["etapes_ordre"] == list(chrono.ETAPES)
    assert lu["taches"][0]["etapes"][0]["etape"] == "dev"


def test_t2_dossier_absent_est_no_events(tmp_path):
    lu = readers.build_chrono(tmp_path, VIDE, T0)
    assert lu["status"] == "no_events" and lu["taches"] == [] and lu["tronque"] == 0


def test_t3_nom_invalide_ignore(tmp_path):
    _cycle(tmp_path)
    dossier = tmp_path / chrono.JOURNAL_DIR_REL
    (dossier / "hors-contrat.jsonl").write_text("{}\n", encoding="utf-8")
    lu = readers.build_chrono(tmp_path, VIDE, T0)
    assert [t["tid"] for t in lu["taches"]] == [TID]


def test_t4_tous_les_journaux_servis(tmp_path):
    for n in range(15):
        _cycle(tmp_path, f"T-{n + 1:03}", T0 + n)
    lu = readers.build_chrono(tmp_path, VIDE, T0 + 100)
    assert len(lu["taches"]) == 15 and lu["tronque"] == 0


@pytest.mark.parametrize("running_count,done_count,expected_count", [(14, 3, 17), (0, 14, 14)])
def test_aucune_limite_de_journaux(tmp_path, running_count, done_count, expected_count):
    tasks = []
    for n in range(running_count + done_count):
        tid = f"T-{n + 1:03}"
        _cycle(tmp_path, tid, T0 + n)
        tasks.append({"id": tid, "state": "running" if n < running_count else "done", "task": "témoin"})
    board = tmp_path / ".agents" / "state" / "board" / "TASKS.json"
    board.parent.mkdir(parents=True, exist_ok=True)
    board.write_text(json.dumps({"tasks": tasks}), encoding="utf-8")
    lu = readers.build_chrono(tmp_path, VIDE, T0 + 100)
    assert len(lu["taches"]) == expected_count
    assert {ligne["tid"] for ligne in lu["taches"]} == {task["id"] for task in tasks}
    assert lu["tronque"] == 0


def test_running_servies_avant_les_journaux_recents(tmp_path):
    for n in range(14):
        tid = f"T-{n + 1:03}"
        _cycle(tmp_path, tid, T0 + n)
        chemin = chrono.chemin_journal(tmp_path, tid)
        mtime_ns = (T0 + n) * 1_000_000
        os.utime(chemin, ns=(mtime_ns, mtime_ns))
    board = tmp_path / ".agents" / "state" / "board" / "TASKS.json"
    board.parent.mkdir(parents=True, exist_ok=True)
    board.write_text(json.dumps({"tasks": [
        {"id": f"T-{n + 1:03}", "state": "running" if n < 3 else "done", "task": "témoin"}
        for n in range(14)]}), encoding="utf-8")
    lu = readers.build_chrono(tmp_path, VIDE, T0 + 100)
    servis = {ligne["tid"] for ligne in lu["taches"]}
    assert len(servis) == 14 and lu["tronque"] == 0
    assert {"T-001", "T-002", "T-003"} <= servis
    assert {"T-004", "T-005"} <= servis
    assert [ligne["tid"] for ligne in lu["taches"][:3]] == ["T-003", "T-002", "T-001"]


def test_empreinte_chrono_suit_running_et_journal_sans_suivre_les_pending(tmp_path):
    _cycle(tmp_path)
    board = tmp_path / ".agents" / "state" / "board" / "TASKS.json"
    board.parent.mkdir(parents=True, exist_ok=True)
    board.write_text(json.dumps({"tasks": [{"id": TID, "state": "pending", "task": "témoin"}]}),
                     encoding="utf-8")
    avant = readers.views_fingerprint(tmp_path, None, None)
    board.write_text(json.dumps({"tasks": [{"id": TID, "state": "pending", "task": "témoin"},
                                          {"id": "T-998", "state": "pending", "task": "nouvelle"}]}),
                     encoding="utf-8")
    assert readers.views_fingerprint(tmp_path, None, None) == avant
    board.write_text(json.dumps({"tasks": [{"id": TID, "state": "running", "task": "témoin"}]}),
                     encoding="utf-8")
    running = readers.views_fingerprint(tmp_path, None, None)
    assert running != avant
    board.write_text(json.dumps({"tasks": [{"id": TID, "state": "blocked", "task": "témoin"}]}),
                     encoding="utf-8")
    blocked = readers.views_fingerprint(tmp_path, None, None)
    assert blocked == avant
    board.write_text(json.dumps({"tasks": [{"id": TID, "state": "running", "task": "témoin"}]}),
                     encoding="utf-8")
    assert readers.views_fingerprint(tmp_path, None, None) == running
    _etape(tmp_path, "dev", "begin", T0 + 1000)
    assert readers.views_fingerprint(tmp_path, None, None) != running


def test_tasks_start_ecrit_un_jalon_et_invalide_les_vues(tmp_path):
    def cli(*args):
        result = subprocess.run([sys.executable, str(HERE / "tasks.py"), "--root", str(tmp_path), *args],
                                capture_output=True, text=True, timeout=15, check=False)
        assert result.returncode == 0, result.stderr
        return result.stdout

    created = cli("new", "Chrono start probe", "--pas-un-defaut", "feature probe")
    match = re.search(r"TASKS: (T-[0-9A-HJKMNP-TV-Z]{26}) → pending", created)
    assert match is not None, created
    tid = match.group(1)
    avant = readers.views_fingerprint(tmp_path, None, None)
    cli("start", tid)
    assert chrono.chemin_journal(tmp_path, tid).is_file()
    running = readers.views_fingerprint(tmp_path, None, None)
    assert running != avant
    lignes = readers.build_chrono(tmp_path, VIDE)["taches"]
    assert lignes[0]["tid"] == tid and lignes[0]["etapes"][0]["etape"] == "dev"
    cli("block", tid, "--note", "pause")
    blocked = readers.views_fingerprint(tmp_path, None, None)
    assert blocked != running
    cli("unblock", tid)
    # Le vrai verbe remet à pending : l'ensemble running reste vide.
    assert readers.views_fingerprint(tmp_path, None, None) == blocked
    cli("start", tid)
    assert readers.views_fingerprint(tmp_path, None, None) != blocked


def test_board_illisible_replie_sur_mtime_sans_degrader_la_frise(tmp_path):
    for n in range(14):
        tid = f"T-{n + 1:03}"
        _cycle(tmp_path, tid, T0 + n)
        chemin = chrono.chemin_journal(tmp_path, tid)
        mtime_ns = (T0 + 14 - n) * 1_000_000
        os.utime(chemin, ns=(mtime_ns, mtime_ns))
    board = tmp_path / ".agents" / "state" / "board" / "TASKS.json"
    board.parent.mkdir(parents=True, exist_ok=True)
    board.write_text("{illisible", encoding="utf-8")
    lu = readers.build_chrono(tmp_path, VIDE, T0 + 100)
    assert lu["status"] == "ok" and lu["tronque"] == 0
    assert [ligne["tid"] for ligne in lu["taches"]] == [f"T-{n:03}" for n in range(1, 15)]
    assert all(ligne["erreur"] is None for ligne in lu["taches"])


def test_total_estime_absent_puis_partiel(tmp_path, monkeypatch):
    _cycle(tmp_path)
    monkeypatch.setattr(chrono, "estimer", lambda *_args: {"source": "inconnu", "n": 0})
    _etape(tmp_path, "planification", "begin", T0 + 1)
    sans = readers.build_chrono(tmp_path, VIDE, T0 + 2)["taches"][0]
    assert sans["total"]["estime_s"] is None
    assert sans["etapes"][0]["estime_s"] is None
    monkeypatch.setattr(chrono, "estimer", lambda *_args: {
        "source": "historique", "n": 1, "mediane_s": 120, "p90_s": 180})
    _etape(tmp_path, "dev", "begin", T0 + 3)
    partiel = readers.build_chrono(tmp_path, VIDE, T0 + 4)["taches"][0]
    assert [e["estime_s"] for e in partiel["etapes"]] == [None, 120]
    assert partiel["total"]["estime_s"] == 120


def test_t5_append_change_empreinte(tmp_path):
    _cycle(tmp_path)
    avant = readers.views_fingerprint(tmp_path, None, None)
    _etape(tmp_path, "dev", "begin", T0 + 1000)
    apres = readers.views_fingerprint(tmp_path, None, None)
    assert avant != apres


def test_t6_bilan_qui_leve_reste_sur_ligne(tmp_path, monkeypatch):
    _cycle(tmp_path)
    def panne(*_args, **_kwargs):
        raise RuntimeError("cassé")
    monkeypatch.setattr(chrono, "bilan", panne)
    lu = readers.build_chrono(tmp_path, VIDE, T0)
    assert lu["status"] == "ok" and "RuntimeError" in lu["taches"][0]["erreur"]


def test_t6b_module_sans_bilan_degrade_la_section_par_build_views(tmp_path, monkeypatch):
    _cycle(tmp_path)
    monkeypatch.delattr(chrono, "bilan")
    readers.reset_cache_for_tests()
    result = readers.build_views(tmp_path, None, None, None, VIDE, VIDE, VIDE, VIDE, VIDE, VIDE)
    lu = result["views"]["chrono"]
    assert lu["status"] == "degraded" and "bilan" in lu["reason"]
    assert result["meta"]["section_statuses"]["chrono"] == "degraded"


def test_t7_chaque_etape_servie_a_un_libelle_dans_la_frise():
    source = _frise_source()
    bloc = re.search(r"export const ETAPE_LABEL = \{\n(?P<cles>(?:[^\n]*\n)*?)\};", source)
    assert bloc is not None
    cles = re.findall(r'^  "([^"]+)":', bloc["cles"], re.MULTILINE)
    assert len(cles) == len(chrono.ETAPES) and set(cles) == set(chrono.ETAPES)


def test_contrat_statuts_et_plan_lus_par_la_frise(tmp_path):
    ouvert, fini, clos = (tmp_path / nom for nom in ("ouvert", "fini", "clos"))
    for root in (ouvert, fini, clos):
        _cycle(root)
        _etape(root, "dev", "begin", T0)
    _etape(fini, "dev", "end", T0 + 1_000)
    _etape(clos, "done", "begin", T0 + 2_000)
    _etape(clos, "done", "end", T0 + 2_000)
    entries = [_verdict(T0 + 1, "chrono: planner=10m/1200 plan-critic=5m/600")]
    section = {"status": "ok", "data": {"entries": entries}}
    lignes = [readers.build_chrono(root, section, T0 + 3_000)["taches"][0]
              for root in (ouvert, fini, clos)]
    statuts = {etape["statut"] for ligne in lignes for etape in ligne["etapes"]}
    assert statuts == {"en cours", "finie", "incomplète"}
    plan = lignes[0]["plan"]
    assert plan is not None and plan["mesures"] == 1
    source = _sans_commentaires_js(_frise_source())
    for valeur in statuts:
        assert f'"{valeur}"' in source
    cles = {"planner_s", "critic_s", "tours", "mesures"}
    assert cles <= plan.keys()
    assert set(re.findall(r"\bplan\.([a-z_]+)\b", source)) == cles
    assert 'statuts.every((s) => s === "finie") ? "finie"' in source
    assert 'if (statut === "finie") return "done"' in source
    assert 'statuts.includes("en cours") ? "en cours"' in source
    assert 'if (statut === "en cours") return' in source


def test_contrat_lots_durees_lu_par_la_frise(tmp_path):
    """Les clés que `_lots_durees` sert sont celles que `lotsDureesDe` (frise.js) lit, dans les deux sens,
    hors `etapes` (les étapes comptées, servies au lecteur humain du JSON, que le front n'affiche pas) :
    une clé renommée d'un côté rougit ici, jamais une durée muette au Board."""
    _cycle(tmp_path)
    _etape(tmp_path, "dev", "begin", T0, LOT_A)
    ligne = readers.build_chrono(tmp_path, VIDE, T0 + 1_000)["taches"][0]
    assert ligne["lots_durees"], ligne
    servies = set(ligne["lots_durees"][0])
    assert servies == {"lot", "reel_s", "statut", "live", "etapes", "ouvertes", "non_bornees"}
    source = _sans_commentaires_js(_frise_source())
    assert "t.lots_durees" in source
    corps = re.search(r"function lotsDureesDe\(raw, frozen\) \{\n(.*?)\n\}\n", source, re.S)
    assert corps, "lotsDureesDe introuvable dans frise.js"
    lues = set(re.findall(r"\be\.([a-z_]+)\b", corps.group(1)))
    assert lues == servies - {"etapes"}, sorted(lues ^ (servies - {"etapes"}))


def test_commentaires_js_retires_en_fin_de_ligne_et_en_bloc():
    source = 'a = "x"; // b\n/* c\nd */e "//garde" `/*garde*/`'
    assert _sans_commentaires_js(source) == 'a = "x"; \n\ne "//garde" `/*garde*/`'


def test_t8_tours_et_mesures_du_cycle(tmp_path):
    _cycle(tmp_path)
    texte = "chrono: planner=10m/1200 plan-critic=5m/600"
    entries = [_verdict(T0 + 1, texte), _verdict(T0 + 2, texte, "lot A : plan-critic GO"),
               _verdict(T0 + 3, "--sans-chrono raison")]
    lu = readers.build_chrono(tmp_path, {"status": "ok", "data": {"entries": entries}}, T0 + 4)
    plan = lu["taches"][0]["plan"]
    assert (plan["tours"], plan["mesures"], plan["planner_s"], plan["critic_s"]) == (3, 2, 1200, 600)
    assert (plan["planner_jetons"], plan["critic_jetons"]) == (2400, 1200)


def test_t9_verdict_ancien_exclu_du_cycle_courant(tmp_path):
    _cycle(tmp_path)
    _etape(tmp_path, "done", "begin", T0 + 100)
    _etape(tmp_path, "done", "end", T0 + 101)
    chrono.commencer(tmp_path, TID, now_ms=T0 + 200)
    entries = [_verdict(T0 + 150, ""), _verdict(T0 + 250, "")]
    lu = readers.build_chrono(tmp_path, {"status": "ok", "data": {"entries": entries}}, T0 + 300)
    assert lu["taches"][0]["cycle"] == 2 and lu["taches"][0]["plan"]["tours"] == 1


def test_verdict_id_non_ulid_se_replie_sur_la_date(tmp_path):
    _cycle(tmp_path)
    jour = datetime.fromtimestamp(T0 / 1000, timezone.utc).date()
    entries = [
        {"id": "S-00000001", "task": TID, "kind": "verdict", "title": "plan-critic GO",
         "text": "", "date": (jour - timedelta(days=1)).isoformat()},
        {"id": "S-00000002", "task": TID, "kind": "verdict", "title": "plan-critic GO",
         "text": "", "date": jour.isoformat()},
    ]
    lu = readers.build_chrono(tmp_path, {"status": "ok", "data": {"entries": entries}}, T0 + 1)
    assert lu["taches"][0]["plan"]["tours"] == 1


def test_titre_specs_non_chaine_reste_une_erreur_de_ligne(tmp_path):
    _cycle(tmp_path)
    _cycle(tmp_path, "T-999")
    entries = [{"id": "S-00000001", "task": TID, "kind": "verdict", "title": {"bad": 1},
                "text": "", "date": "2026-10-23"}]
    lu = readers.build_chrono(tmp_path, {"status": "ok", "data": {"entries": entries}}, T0 + 1)
    lignes = {ligne["tid"]: ligne for ligne in lu["taches"]}
    assert lu["status"] == "ok" and "TypeError" in lignes[TID]["erreur"]
    assert lignes["T-999"]["erreur"] is None


def test_t10_lots_chevauchants_font_union(tmp_path):
    _cycle(tmp_path)
    _etape(tmp_path, "dev", "begin", T0, LOT_A)
    _etape(tmp_path, "dev", "begin", T0 + 50_000, LOT_B)
    _etape(tmp_path, "dev", "end", T0 + 100_000, LOT_A)
    _etape(tmp_path, "dev", "end", T0 + 150_000, LOT_B)
    lu = readers.build_chrono(tmp_path, VIDE, T0 + 200_000)["taches"][0]
    assert lu["etapes"][0]["reel_s"] == 150 and lu["total"]["reel_s"] == 150


def test_b2_lots_journalises_servis_par_identifiant(tmp_path):
    """e2e-dashboard B2 : la mère sert les IDENTIFIANTS des lots de son cycle courant, la frise les lit."""
    _cycle(tmp_path)
    _etape(tmp_path, "cadrage", "begin", T0)
    _etape(tmp_path, "dev", "begin", T0 + 1_000, LOT_B)
    _etape(tmp_path, "dev", "begin", T0 + 2_000, LOT_A)
    _etape(tmp_path, "dev", "end", T0 + 3_000, LOT_A)
    lu = readers.build_chrono(tmp_path, VIDE, T0 + 10_000)["taches"][0]
    assert lu["lots_journalises"] == [LOT_A, LOT_B]
    # un journal sans lot sert une liste vide, jamais une clé absente
    autre = tmp_path / "sans-lot"
    _cycle(autre)
    _etape(autre, "dev", "begin", T0)
    assert readers.build_chrono(autre, VIDE, T0 + 10_000)["taches"][0]["lots_journalises"] == []
    assert "lots_journalises" in _sans_commentaires_js(_frise_source())


def test_t11_lien_fifo_et_depassement_restent_erreurs(tmp_path):
    _cycle(tmp_path)
    dossier = tmp_path / chrono.JOURNAL_DIR_REL
    chemin = chrono.chemin_journal(tmp_path, TID)
    cible = dossier / "cible"
    cible.write_bytes(chemin.read_bytes())
    chemin.unlink()
    chemin.symlink_to(cible)
    assert "lien" in readers.build_chrono(tmp_path, VIDE, T0)["taches"][0]["erreur"]
    chemin.unlink()
    if hasattr(os, "mkfifo"):
        os.mkfifo(chemin)
        assert "régulier" in readers.build_chrono(tmp_path, VIDE, T0)["taches"][0]["erreur"]
        chemin.unlink()
    chemin.write_bytes(b" " * (chrono.LIRE_MAX + 1))
    assert "1 Mio" in readers.build_chrono(tmp_path, VIDE, T0)["taches"][0]["erreur"]


def test_dossier_chrono_en_lien_reste_une_erreur_de_ligne(tmp_path):
    _cycle(tmp_path)
    dossier = tmp_path / chrono.JOURNAL_DIR_REL
    reel = dossier.with_name("task-chrono-reel")
    dossier.rename(reel)
    dossier.symlink_to(reel, target_is_directory=True)
    lu = readers.build_chrono(tmp_path, VIDE, T0)
    assert lu["status"] == "ok" and "lien symbolique" in lu["taches"][0]["erreur"]


def test_chaque_journal_n_est_ouvert_qu_une_fois(tmp_path, monkeypatch):
    """F1 du chrono : contrôle et analyse sur les MÊMES octets ; une seconde ouverture rouvre une fenêtre TOCTOU."""
    _cycle(tmp_path)
    _etape(tmp_path, "dev", "begin", T0 + 1000)
    chemin = str(chrono.chemin_journal(tmp_path, TID))
    vrai_open, ouvertures = os.open, []

    def espion(*args, **kwargs):
        cible = kwargs.get("path", args[0] if args else None)
        if os.fspath(cible) == chemin:
            ouvertures.append(cible)
        return vrai_open(*args, **kwargs)

    monkeypatch.setattr(os, "open", espion)
    ligne = readers.build_chrono(tmp_path, VIDE, T0 + 2000)["taches"][0]
    assert ligne["erreur"] is None and ligne["etapes"][0]["etape"] == "dev"
    assert len(ouvertures) == 1, ouvertures


def test_releve_scandir_egal_au_glob_d_avant(tmp_path):
    """`_dir_stats` (os.scandir) relève le même ensemble que `Path.glob` qu'il remplace : noms cachés compris,
    autre extension exclue, casse du système, ordre trié, sous-dossier qui répond au motif compris."""
    for nom in ("b.json", "a.json", ".cache.json", "c.jsonl", "D.JSON", "notes.txt"):
        (tmp_path / nom).write_text(nom, encoding="utf-8")
    (tmp_path / "e.json").mkdir()
    for motif in ("*.json", "*.jsonl"):
        attendu = tuple((p.name, p.stat().st_mtime_ns, p.stat().st_size) for p in sorted(tmp_path.glob(motif)))
        assert readers.dir_fingerprint(tmp_path, motif) == attendu
    assert readers.dir_fingerprint(tmp_path / "absent", "*.json") == ()
    assert readers.dir_fingerprint(None) == ()


def test_empreinte_des_vues_ne_relit_pas_un_board_inchange(tmp_path):
    """Contrat « Cheap » de l'empreinte (sondée toutes les 0,5 s par flux) : sur 2 000 tâches, le second appel sans
    écriture ne recharge pas le board. Forme DOSSIER, celle du kit : un enregistrement par tâche, que l'empreinte
    stat relève un par un. Mutant : mémo retiré → rouge."""
    dossier = tmp_path / ".agents" / "state" / "board" / "tasks"
    dossier.mkdir(parents=True)
    for n in range(1, 2001):
        tid = f"T-{n:08}"
        (dossier / f"{tid}.json").write_text(json.dumps({"format": 1, "id": tid, "sync_operations": [], "record": {
            "id": tid, "owner": "banc", "stage": "", "state": "running" if n % 100 == 0 else "pending",
            "task": "banc de coût de l'empreinte", "updated": "2026-10-23"}}), encoding="utf-8")
    premier = readers.views_fingerprint(tmp_path, None, None)
    assert premier[-1] == tuple(f"T-{n:08}" for n in range(100, 2001, 100))
    durees = []
    for _ in range(3):
        debut = time.perf_counter()
        assert readers.views_fingerprint(tmp_path, None, None) == premier
        durees.append(time.perf_counter() - debut)
    assert min(durees) < 0.010, durees


def _lots(root: Path, now_ms: int) -> dict[str, dict]:
    return {d["lot"]: d for d in readers.build_chrono(root, VIDE, now_ms)["taches"][0]["lots_durees"]}


def test_lots_durees_union_dans_un_lot(tmp_path):
    """T1 : dev [0,100 s] et juges [50,150 s] d'un MÊME lot font 150 s (union), jamais 200 (somme)."""
    _cycle(tmp_path)
    _etape(tmp_path, "dev", "begin", T0, LOT_A)
    _etape(tmp_path, "juges", "begin", T0 + 50_000, LOT_A)
    _etape(tmp_path, "dev", "begin", T0 + 50_000, LOT_B)
    _etape(tmp_path, "dev", "end", T0 + 100_000, LOT_A)
    _etape(tmp_path, "juges", "end", T0 + 150_000, LOT_A)
    _etape(tmp_path, "dev", "end", T0 + 150_000, LOT_B)
    lots = _lots(tmp_path, T0 + 200_000)
    assert [lot for lot in lots] == [LOT_A, LOT_B]
    assert (lots[LOT_A]["reel_s"], lots[LOT_B]["reel_s"]) == (150, 100)
    assert lots[LOT_A]["etapes"] == ["dev", "juges"] and lots[LOT_A]["statut"] == "finie"


def _board_fournee(root: Path, etat_mere: str) -> dict:
    data = {"tasks": [{"id": TID, "state": etat_mere, "task": "mère"},
                      {"id": LOT_A, "state": "running", "task": "lot", "fournee": {"parent": TID}}]}
    board = root / ".agents" / "state" / "board" / "TASKS.json"
    board.parent.mkdir(parents=True, exist_ok=True)
    board.write_text(json.dumps(data), encoding="utf-8")
    return data


@pytest.mark.parametrize("fin_fusion,reel,non_bornees,statut", [
    (None, 600, ["fusion"], "incomplète"),
    (T0 + 660_000, 660, [], "finie"),
])
def test_lots_durees_sequence_des_verbes(tmp_path, fin_fusion, reel, non_bornees, statut):
    """T2 / T2b (R1) par les VRAIS verbes : fournee T0, retour +600 s, done de la mère +17 000 s. La fusion
    ouverte chez la mère n'est ni bornée au done ni comptée (600 s, dite) ; FINIE (+660 s), elle compte."""
    data = _board_fournee(tmp_path, "running")
    chrono.jalons_du_verbe(tmp_path, data, "fournee", [TID], now_ms=T0)
    chrono.jalons_du_verbe(tmp_path, data, "retour", [LOT_A], now_ms=T0 + 600_000)
    if fin_fusion is not None:
        _etape(tmp_path, "fusion", "end", fin_fusion, LOT_A)
    data = _board_fournee(tmp_path, "done")
    chrono.jalons_du_verbe(tmp_path, data, "done", [TID], now_ms=T0 + 17_000_000)
    lot = _lots(tmp_path, T0 + 18_000_000)[LOT_A]
    assert lot["reel_s"] == reel
    assert lot["non_bornees"] == non_bornees and lot["statut"] == statut and lot["live"] is False
    assert lot["etapes"] == ["dev"] + ([] if fin_fusion is None else ["fusion"])


def test_lots_durees_statuts(tmp_path):
    """T3 : un dev ouvert d'une mère ouverte court (live, `en cours`) ; une fusion ouverte seule ne rend
    jamais live (`incomplète`). R3 : le lecteur ne lit pas le board du lot — un lot `done` au board avec une
    mesure orpheline reste live ICI, le front le gèle (`dureeLotDe`)."""
    _cycle(tmp_path)
    _etape(tmp_path, "dev", "begin", T0, LOT_A)
    _etape(tmp_path, "dev", "begin", T0, LOT_B)
    _etape(tmp_path, "dev", "end", T0 + 10_000, LOT_B)
    _etape(tmp_path, "fusion", "begin", T0 + 10_000, LOT_B)
    lots = _lots(tmp_path, T0 + 30_000)
    assert (lots[LOT_A]["statut"], lots[LOT_A]["live"], lots[LOT_A]["ouvertes"]) == ("en cours", True, ["dev"])
    assert lots[LOT_A]["reel_s"] == 30
    assert (lots[LOT_B]["statut"], lots[LOT_B]["live"], lots[LOT_B]["ouvertes"]) == ("incomplète", False, [])
    assert (lots[LOT_B]["reel_s"], lots[LOT_B]["non_bornees"]) == (10, ["fusion"])


def test_lots_durees_rien_de_borne_hors_fusion(tmp_path):
    """R2 : mère close, le seul dev du lot resté ouvert → 0 s servi MAIS `etapes` vide et `non_bornees`
    ["dev"] : le front lit « rien de borné », jamais une durée de 0 s mesurée."""
    _cycle(tmp_path)
    _etape(tmp_path, "dev", "begin", T0, LOT_A)
    _etape(tmp_path, "done", "begin", T0 + 900_000)
    _etape(tmp_path, "done", "end", T0 + 900_000)
    lot = _lots(tmp_path, T0 + 1_000_000)[LOT_A]
    assert (lot["reel_s"], lot["etapes"], lot["non_bornees"]) == (0, [], ["dev"])
    assert (lot["statut"], lot["live"]) == ("incomplète", False)


def test_lots_durees_une_seule_lecture(tmp_path, monkeypatch):
    """T4 : la durée des lots ne relit pas le journal (une lecture contrôlée par journal)."""
    _cycle(tmp_path)
    _etape(tmp_path, "dev", "begin", T0, LOT_A)
    vrai, appels = chrono._lire_octets, []

    def espion(*args, **kwargs):
        appels.append(args[0])
        return vrai(*args, **kwargs)

    monkeypatch.setattr(chrono, "_lire_octets", espion)
    ligne = readers.build_chrono(tmp_path, VIDE, T0 + 1_000)["taches"][0]
    assert ligne["lots_durees"][0]["lot"] == LOT_A
    assert len(appels) == 1, appels


def test_lots_durees_toujours_servie(tmp_path):
    """T5 : erreur de ligne, journal sans cycle, cycle sans lot → `[]`, jamais une clé absente."""
    sans_lot = tmp_path / "sans-lot"
    _cycle(sans_lot)
    _etape(sans_lot, "dev", "begin", T0)
    assert readers.build_chrono(sans_lot, VIDE, T0 + 1)["taches"][0]["lots_durees"] == []
    vide = tmp_path / "vide"
    _cycle(vide)
    chrono.chemin_journal(vide, TID).write_text("", encoding="utf-8")
    assert readers.build_chrono(vide, VIDE, T0)["taches"][0]["lots_durees"] == []
    erreur = tmp_path / "erreur"
    _cycle(erreur)
    chrono.chemin_journal(erreur, TID).write_bytes(b" " * (chrono.LIRE_MAX + 1))
    ligne = readers.build_chrono(erreur, VIDE, T0)["taches"][0]
    assert ligne["erreur"] and ligne["lots_durees"] == []


def test_t12_cycle_clos_borne_etape_ouverte_au_done(tmp_path):
    _cycle(tmp_path)
    _etape(tmp_path, "dev", "begin", T0, LOT_A)
    assert "done_at" not in readers.build_chrono(tmp_path, VIDE, T0)["taches"][0]
    _etape(tmp_path, "done", "begin", T0 + 900_000)
    _etape(tmp_path, "done", "end", T0 + 900_000)
    au_done = readers.build_chrono(tmp_path, VIDE, T0 + 900_000)["taches"][0]
    apres = readers.build_chrono(tmp_path, VIDE, T0 + 4_500_000)["taches"][0]
    assert au_done["clos"] and au_done["etapes"][0]["reel_s"] == 900
    assert au_done["done_at"] == T0 + 900_000
    assert apres["etapes"][0]["reel_s"] == au_done["etapes"][0]["reel_s"]
    assert apres["total"]["reel_s"] == au_done["total"]["reel_s"]
