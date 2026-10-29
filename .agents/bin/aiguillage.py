#!/usr/bin/env python3
"""AIGUILLEUR DES COMMANDES — quelle commande lancer, et quoi faire pendant qu'une tâche tourne
(T-01M54GE7B18G5A1BCG7YBY0ZAN, épopée E-48). LECTURE SEULE, 0 LLM.

CE QU'IL FAIT. Il lit le board (`etat_lecture.taches`, qui délègue au propriétaire `tasks`), le jugement d'amont
(`tasks.releve_amont`, le même que `deps-ready`) et le pool de plans (`core-scripts/plan_pool.py status --json`,
en SOUS-PROCESSUS : `.agents/bin` n'importe jamais `core-scripts/`), puis il imprime des lignes fixes :
  EN COURS:      les tâches `running`, avec la règle R1 (FERMER AVANT D'OUVRIR) quand il y en a ;
  BLOQUÉES:      au board, par l'amont (le premier amont nommé), par recouvrement de write-set, CYCLE et autres ;
  SUIVANTE:      UNE commande et sa raison, ou `aucune` et pourquoi ;
  EN PARALLÈLE:  ce qu'un équipier peut prendre — `/kickoff <B>`, write-set DÉCLARÉ prouvé disjoint par
                 `writeset_paths_overlap`, le prédicat de `tasks.py parallel` ;
  À DÉCLARER:    les tâches dont la disjonction est improuvable faute de write-set déclaré ;
  TRONQUÉ:       toute borne appliquée, ou `aucune borne atteinte` ;
  RELEVÉ INDICATIF, NON-AUTORITATIF — toujours la dernière ligne.

CE QU'IL NE FAIT PAS. Il n'écrit RIEN (ni board, ni journal, ni cache) et ne remplace ni `tasks.py parallel`, ni
`tasks.py deps-ready`, ni `plan_pool.py check` : il les LIT ou les imite, et dit de les rejouer avant d'agir. Aucun
code ne juge « livraison prête » : la ligne R1 le DIT, elle ne le calcule pas. Le `responsable` du board (D2) n'est
pas lu ici ; « équipier » reste indicatif.

TABLE TOTALE code de pool → commande (`TABLE_POOL`, fonction pure `commande_pour`) :
  READY → `/kickoff <T>` ; NO_PLAN → `/planning` (deux ou plus) ou `/kickoff <T>` (une seule), et
  `/planning-all --chantier X` sous `--chantier X` ; PLAN_SANS_VERDICT, STALE, VERDICT_FAIL, SHA_ABSENT,
  WRITE_SET_ABSENT → `/planning-all <T>` avec la raison, sauf un SHA_ABSENT dont le dernier plan est un
  `lot K : Plan @…` (boucle de plan PAR LOT en cours, état attendu) → dit, sans commande ; TASK_ABSENT → dit, sans
  commande ; code inconnu →
  `COVERAGE DEGRADED`, sans commande. Board sans tâche en attente → `/kickoff "<ta demande>"`. Une tâche dont
  l'amont ne passe pas (`AMONT_OUVERT`, `CYCLE`, `INEXPLOITABLE`, `PLAN_A_REPLANIFIER`) n'est JAMAIS proposée.
  Préséance : READY, puis les plans à reprendre, puis les tâches sans plan (R1 : fermer avant d'ouvrir).

COÛT BORNÉ. `releve_amont` coûte (mesuré : 4,1 s sur 683 `pending`) : les candidates sont évaluées dans l'ordre et
l'examen s'arrête dès que SUIVANTE est fixée et que EN PARALLÈLE porte `--max` entrées ; le compte examiné est dit.

CODES DE RETOUR : 0 relevé imprimé (même dégradé) · 1 board illisible · 2 usage.
PYTHON : parsable en 3.9 (ni `match`, ni annotation `X | Y` évaluée).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_BIN = Path(__file__).resolve().parent
_KIT = _BIN.parent.parent
POOL_SCRIPT = _KIT / "core-scripts" / "plan_pool.py"

MAX_DEFAUT = 5
TITRE_MAX = 60
DEMANDE_LIBRE = '/kickoff "<ta demande>"'
NON_AUTORITATIF = "RELEVÉ INDICATIF, NON-AUTORITATIF"
#: Les commandes que SUIVANTE et EN PARALLÈLE peuvent rendre — chacune existe sous `.claude/commands/` et est citée
#: dans la carte `id="quelle-commande"` de `docs/usage.html`, onglet Avancé (témoin T13).
COMMANDES_PROPOSEES = ("/kickoff", "/planning", "/planning-all")

KICKOFF, PLANIFIER, REPLANIFIER, DIRE = "kickoff", "planifier", "replanifier", "dire"
#: TOTALE sur les clés d'`EXIT` de `core-scripts/plan_pool.py` (témoin T14, qui les lit par `ast`).
TABLE_POOL: Dict[str, Tuple[str, str]] = {
    "READY": (KICKOFF, "plan frais, verdict plan-critic approuvant"),
    "NO_PLAN": (PLANIFIER, "aucun plan"),
    "PLAN_SANS_VERDICT": (REPLANIFIER, "plan sans verdict plan-critic final"),
    "SHA_ABSENT": (REPLANIFIER, "titre de plan sans sha canonique"),
    "WRITE_SET_ABSENT": (REPLANIFIER, "write-set du plan vide"),
    "STALE": (REPLANIFIER, "un fichier du write-set a bougé depuis le sha du plan"),
    "VERDICT_FAIL": (REPLANIFIER, "dernier verdict plan-critic NO_GO ou FAIL"),
    "TASK_ABSENT": (DIRE, "absente du board ou non pending"),
}
#: SHA_ABSENT pendant une boucle de plan PAR LOT : le dernier plan est `lot K : Plan @…` (plan_pool le dit non
#: canonique), état ATTENDU jusqu'à la consolidation du maître — jamais un `/planning-all <T>` proposé.
BOUCLE_PAR_LOT = re.compile(r"non canonique : \s*lot\s+[A-Z][A-Z0-9]{0,3}\s*:\s*plan\s*@", re.IGNORECASE)
#: Préséance de SUIVANTE (R1 : fermer avant d'ouvrir) — rang le plus bas d'abord.
RANG = {KICKOFF: 0, REPLANIFIER: 1, PLANIFIER: 2}
JETONS_COMPTES = ("CYCLE", "INEXPLOITABLE", "PLAN_A_REPLANIFIER")
LIGNE_R1 = ("R1 FERMER AVANT D'OUVRIR : clore d'abord ce qui est prêt ou presque ; aucun code ne juge "
            "« livraison prête », l'aiguilleur le DIT")
GESTE_PARALLEL = "ÉCRIT le groupe au board, geste de l'orchestrateur"


class AiguillageError(Exception):
    """Le board ne se lit pas : rc 1, jamais un relevé vide qui se lirait « rien à faire »."""


def commande_pour(code: str, tid: str, n_sans_plan: int = 1, chantier: str = "",
                  au_moins: bool = False) -> Tuple[Optional[str], str]:
    """PURE. `(commande ou None, raison)` pour le code de pool `code` de la tâche `tid`.
    `au_moins` : la liste des candidates a été COUPÉE, `n_sans_plan` est un plancher, pas un compte."""
    entree = TABLE_POOL.get(code)
    if entree is None:
        return None, f"COVERAGE DEGRADED — code de pool inconnu « {code} » pour {tid} : aucune commande"
    genre, raison = entree
    if genre == KICKOFF:
        return f"/kickoff {tid}", f"{code} : {raison}"
    if genre == PLANIFIER:
        if n_sans_plan >= 2:
            cmd = f"/planning-all --chantier {chantier}" if chantier else "/planning"
            compte = f"au moins {n_sans_plan}" if au_moins else str(n_sans_plan)
            return cmd, f"NO_PLAN : {compte} tâches sans plan, à préparer ensemble"
        return f"/kickoff {tid}", "NO_PLAN : une seule tâche sans plan, /kickoff la planifie puis la lance"
    if genre == REPLANIFIER:
        return f"/planning-all {tid}", f"{code} : {raison}, à replanifier"
    return None, f"{code} : {tid} {raison}, aucune commande"


def lire_pool(root: Path) -> Tuple[Optional[Dict[str, Dict[str, Any]]], str]:
    """`({tâche: verdict}, "")`, ou `(None, raison)` si le pool ne se lit pas — jamais un READY supposé."""
    if not POOL_SCRIPT.is_file():
        return None, f"{POOL_SCRIPT} absent"
    try:
        proc = subprocess.run([sys.executable, str(POOL_SCRIPT), "--root", str(root), "status", "--json"],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"plan_pool injouable : {exc}"
    if proc.returncode != 0:
        premiere = (proc.stderr.strip().splitlines() or ["(stderr vide)"])[0]
        return None, f"plan_pool rc {proc.returncode} : {premiere}"
    try:
        brut = json.loads(proc.stdout)
    except ValueError as exc:
        return None, f"JSON de plan_pool illisible : {exc}"
    if not isinstance(brut, list):
        return None, "JSON de plan_pool hors forme (liste attendue)"
    pool: Dict[str, Dict[str, Any]] = {}
    for v in brut:
        if isinstance(v, dict) and isinstance(v.get("task"), str) and isinstance(v.get("code"), str):
            pool[v["task"]] = v
    return pool, ""


def _titre(t: Dict[str, Any]) -> str:
    # Donnée du board, texte libre : seuls ses caractères imprimables sortent (ESC, CR, NUL… tus).
    titre = "".join(c for c in str(t.get("task") or "").replace("\n", " ") if c.isprintable()).strip()
    return titre if len(titre) <= TITRE_MAX else titre[:TITRE_MAX - 1] + "…"


def aiguiller(root: str, taches: List[Dict[str, Any]], pool: Optional[Dict[str, Dict[str, Any]]], api: Any,
              epic: str = "", chantier: str = "", max_: int = MAX_DEFAUT, pool_raison: str = "") -> Dict[str, Any]:
    """Le relevé, en dict. `api` porte `releve_amont`, `DEPS_READY_PASSANTS`, `writeset_of`,
    `writeset_paths_overlap` et `sort_key` (le module `tasks`). `pool` à None : pool illisible."""
    def retenue(t: Dict[str, Any]) -> bool:
        return (not epic or t.get("epic") == epic) and (not chantier or t.get("chantier") == chantier)

    ws = api.writeset_of
    rel: Dict[str, Any] = {
        "en_cours": [], "bloquees_board": [], "amont": [], "recouvrement": [],
        "comptes": {j: 0 for j in JETONS_COMPTES}, "suivante": None, "en_parallele": [], "parallel_direct": [],
        "a_declarer": [], "degrade": [], "tronque": [], "examinees": 0, "candidates": 0,
    }
    par_id = {t["id"]: t for t in taches}
    running = sorted((t for t in taches if t.get("state") == "running"), key=lambda t: api.sort_key(t["id"]))
    rel["en_cours"] = [{"id": t["id"], "titre": _titre(t), "writeset": ws(t)} for t in running]
    rel["bloquees_board"] = sorted((t["id"] for t in taches if t.get("state") == "blocked" and retenue(t)),
                                   key=api.sort_key)
    pending = [t for t in taches if t.get("state") == "pending" and retenue(t)]
    if not pending:
        portee = " et ".join(x for x in (f"l'épopée {epic}" if epic else "",
                                         f"le chantier {chantier}" if chantier else "") if x)
        rel["suivante"] = {"commande": DEMANDE_LIBRE, "tache": None,
                           "raison": "aucune tâche en attente" + (f" dans {portee}" if portee else "")}
        return rel
    if pool is None:
        rel["degrade"].append(f"COVERAGE DEGRADED — plan_pool illisible ({pool_raison}) : aucun READY affirmé")
        rel["suivante"] = {"commande": None, "tache": None,
                           "raison": "pool illisible : rejoue `python3 core-scripts/plan_pool.py status`"}
        return rel
    candidates: List[Tuple[int, Any, Dict[str, Any], str]] = []
    for t in pending:
        verdict = pool.get(t["id"])
        code = verdict["code"] if verdict else "ABSENT_DU_POOL"
        if code == "SHA_ABSENT" and BOUCLE_PAR_LOT.search(str((verdict or {}).get("detail") or "")):
            rel["degrade"].append(f"{t['id']} : boucle de plan par lot en cours — attendre la consolidation du maître")
            continue
        genre = TABLE_POOL.get(code, (None, ""))[0]
        if genre in RANG:
            candidates.append((RANG[genre], api.sort_key(t["id"]), t, code))
        else:
            rel["degrade"].append(commande_pour(code, t["id"])[1])
    candidates.sort(key=lambda c: (c[0], c[1]))
    rel["candidates"] = len(candidates)

    data = {"tasks": taches}
    occupes = [(t["id"], ws(t)) for t in running]
    def declarer(tid: str, raison: str) -> None:
        if all(a["id"] != tid for a in rel["a_declarer"]):
            rel["a_declarer"].append({"id": tid, "raison": raison})

    for rid, rws in occupes:
        if not rws:
            declarer(rid, "en cours sans write-set déclaré : aucune disjonction prouvable tant qu'elle tourne")
    sans_plan: List[Dict[str, Any]] = []
    suivante: Optional[Dict[str, Any]] = None

    def libre(t: Dict[str, Any], contre: List[Tuple[str, List[str]]]) -> Optional[str]:
        """None si `t` est prouvé disjoint de chaque entrée de `contre`, sinon la raison du refus (dite)."""
        mien = ws(t)
        for oid, ows in contre:
            if not mien:
                return "sans write-set"
            if not ows:
                declarer(oid, "write-set non déclaré : aucune tâche ne se prouve parallèle à elle")
                return f"{oid} sans write-set"
            paire = api.writeset_paths_overlap(mien, ows)
            if paire is not None:
                rel["recouvrement"].append({"id": t["id"], "avec": oid, "chemins": list(paire)})
                return "recouvrement"
        return None

    arret = ""  # la borne qui a COUPÉ la liste des candidates, dite au TRONQUÉ
    for rang, _cle, t, code in candidates:
        if suivante is not None and len(rel["en_parallele"]) >= max_:
            arret = f"arrêt dès SUIVANTE et --max {max_}"
            break
        if suivante is None and rang == RANG[PLANIFIER] and len(sans_plan) >= 2:
            arret = "arrêt à la 2e tâche sans plan : deux NO_PLAN suffisent à choisir la planification groupée"
            break
        rel["examinees"] += 1
        tid = t["id"]
        try:
            releve = api.releve_amont(root, tid, data)
            jeton = releve["jeton"]
        except Exception as exc:  # un relevé qui lève n'est jamais « passant » : compté, dit
            rel["comptes"]["INEXPLOITABLE"] += 1
            rel["degrade"].append(f"COVERAGE DEGRADED — relevé d'amont de {tid} : {type(exc).__name__}")
            continue
        if jeton not in api.DEPS_READY_PASSANTS:
            if jeton == "AMONT_OUVERT":
                premier = releve["ouverts"][0]["id"] if releve.get("ouverts") else "?"
                rel["amont"].append({"id": tid, "premier_amont": premier})
            else:
                rel["comptes"][jeton] = rel["comptes"].get(jeton, 0) + 1
            continue
        genre = TABLE_POOL[code][0]
        if genre == PLANIFIER and suivante is None:
            sans_plan.append(t)
            continue
        if genre == REPLANIFIER:
            if suivante is None:
                cmd, raison = commande_pour(code, tid)
                suivante = {"commande": cmd, "tache": tid, "raison": raison, "ecrit": False}
            continue
        # Une `/kickoff` lance un dev : elle doit être prouvée disjointe de ce qui tourne (et, en parallèle, de la
        # suivante et des parallèles déjà retenues). Rien ne tourne : la suivante part sans preuve à faire.
        if suivante is None:
            refus = libre(t, occupes) if occupes else None
            if refus is None:
                cmd, raison = commande_pour(code, tid)
                suivante = {"commande": cmd, "tache": tid, "raison": raison, "ecrit": True}
            elif refus == "sans write-set":
                declarer(tid, "write-set non déclaré, disjonction improuvable avec ce qui tourne")
            continue
        contre = list(occupes)
        if suivante.get("ecrit"):
            contre.append((suivante["tache"], ws(par_id[suivante["tache"]])))
        contre += [(p["tache"], ws(par_id[p["tache"]])) for p in rel["en_parallele"]]
        refus = libre(t, contre) if contre else (None if ws(t) else "sans write-set")
        if refus is None:
            rel["en_parallele"].append({"commande": f"/kickoff {tid}", "tache": tid,
                                        "raison": f"{code}, write-set déclaré disjoint de "
                                                  + (", ".join(c[0] for c in contre) or "rien")})
            if (suivante.get("ecrit") and isinstance(par_id[suivante["tache"]].get("direct"), dict)
                    and isinstance(t.get("direct"), dict)):
                rel["parallel_direct"].append(f"tasks.py parallel {suivante['tache']} {tid}")
        elif refus == "sans write-set":
            declarer(tid, "write-set non déclaré, disjonction improuvable")
    if suivante is None and sans_plan:
        if len(sans_plan) >= 2:
            cmd, raison = commande_pour("NO_PLAN", sans_plan[0]["id"], len(sans_plan), chantier,
                                        au_moins=bool(arret))
            suivante = {"commande": cmd, "tache": None, "raison": raison, "ecrit": False}
        else:
            seule = sans_plan[0]
            refus = libre(seule, occupes) if occupes else None
            if refus is None:
                cmd, raison = commande_pour("NO_PLAN", seule["id"], 1, chantier)
                suivante = {"commande": cmd, "tache": seule["id"], "raison": raison, "ecrit": True}
            elif refus == "sans write-set":
                declarer(seule["id"], "write-set non déclaré, disjonction improuvable avec ce qui tourne")
    if suivante is None:
        suivante = {"commande": None, "tache": None,
                    "raison": "aucune candidate libre : amont ouvert, recouvrement ou write-set à déclarer"}
    suivante.pop("ecrit", None)
    rel["suivante"] = suivante
    if rel["examinees"] < rel["candidates"]:
        rel["tronque"].append(f"{rel['examinees']} candidates examinées sur {rel['candidates']} ({arret})")
    return rel


def _borne(ids: List[str], max_: int, nom: str, tronque: List[str]) -> str:
    if len(ids) > max_:
        tronque.append(f"{nom} : {max_} affichées sur {len(ids)}")
    return ", ".join(ids[:max_])


def rendre(rel: Dict[str, Any], max_: int = MAX_DEFAUT) -> List[str]:
    """PURE. Les lignes fixes du relevé ; la dernière est toujours `NON_AUTORITATIF`."""
    tronque = list(rel["tronque"])
    lignes: List[str] = []
    if rel["en_cours"]:
        ids = [f"{c['id']} ({c['titre']})" for c in rel["en_cours"]]
        lignes.append(f"EN COURS: {_borne(ids, max_, 'EN COURS', tronque)} — {LIGNE_R1}")
    else:
        lignes.append("EN COURS: aucune")
    lignes.append("BLOQUÉES: au board — " + (_borne(rel["bloquees_board"], max_, "BLOQUÉES au board", tronque)
                                              or "aucune"))
    if rel["amont"]:
        ids = [f"{a['id']} attend {a['premier_amont']}" for a in rel["amont"]]
        lignes.append(f"BLOQUÉES: amont ouvert (jamais proposée) — {_borne(ids, max_, 'amont ouvert', tronque)}")
    if rel["recouvrement"]:
        ids = [f"{r['id']} recoupe {r['avec']} ({' ↔ '.join(r['chemins'])})" for r in rel["recouvrement"]]
        lignes.append(f"BLOQUÉES: recouvrement de write-set — {_borne(ids, max_, 'recouvrement', tronque)}")
    if any(rel["comptes"].values()):
        lignes.append("BLOQUÉES: " + " · ".join(f"{j} {n}" for j, n in rel["comptes"].items())
                      + " — détail : `tasks.py deps-ready <T>`")
    s = rel["suivante"] or {"commande": None, "raison": "?"}
    lignes.append(f"SUIVANTE: {s['commande']} — {s['raison']}" if s["commande"]
                  else f"SUIVANTE: aucune — {s['raison']}")
    if rel["en_parallele"]:
        for p in rel["en_parallele"]:
            lignes.append(f"EN PARALLÈLE: {p['commande']} — {p['raison']}")
        for geste in rel["parallel_direct"]:
            lignes.append(f"EN PARALLÈLE: voie directe seulement — `{geste}` {GESTE_PARALLEL}")
    else:
        lignes.append("EN PARALLÈLE: aucune")
    if rel["a_declarer"]:
        ids = [f"{a['id']} ({a['raison']})" for a in rel["a_declarer"]]
        lignes.append(f"À DÉCLARER: {_borne(ids, max_, 'À DÉCLARER', tronque)} — `tasks.py writeset <T> <chemins>` "
                      "ÉCRIT au board")
    else:
        lignes.append("À DÉCLARER: aucune")
    lignes += rel["degrade"]
    lignes.append("TRONQUÉ: " + (" · ".join(tronque) if tronque else
                                 f"aucune borne atteinte ({rel['examinees']} candidates examinées sur "
                                 f"{rel['candidates']})"))
    lignes.append(f"{NON_AUTORITATIF} — rien n'est écrit ; rejoue `tasks.py deps-ready`, `tasks.py parallel` et "
                  "`plan_pool.py check` avant d'agir")
    return lignes


def _charger_api() -> Tuple[Any, Any]:
    """`etat_lecture` et `tasks`, frères de ce fichier — chargés à l'appel, jamais à l'import (les témoins purs
    n'en ont pas besoin)."""
    if str(_BIN) not in sys.path:
        sys.path.insert(0, str(_BIN))
    import etat_lecture  # noqa: E402 — frère, après l'insertion du chemin
    import tasks  # noqa: E402
    return etat_lecture, tasks


def relever(root: str, epic: str = "", chantier: str = "", max_: int = MAX_DEFAUT) -> Dict[str, Any]:
    """Le relevé complet de `root` ; lève `AiguillageError` si le board ne se lit pas."""
    etat_lecture, tasks = _charger_api()
    erreurs = (etat_lecture.EtatError, OSError, ValueError) + etat_lecture.erreurs_de_lecture("board")
    try:
        taches = etat_lecture.taches(root)
    except erreurs as exc:
        raise AiguillageError(f"board illisible : {exc}") from exc
    a_lire = any(t.get("state") == "pending" for t in taches)
    pool, raison = lire_pool(Path(root)) if a_lire else ({}, "")
    return aiguiller(root, taches, pool, tasks, epic=epic, chantier=chantier, max_=max_, pool_raison=raison)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Command router (READ ONLY): which command to run next, and what a teammate can pick up "
                    "while a task is running. Indicative reading, non-authoritative.",
        epilog="exit codes: 0 reading printed (even degraded) - 1 unreadable board - 2 usage")
    ap.add_argument("--root", default=".", help="repository root (default: .)")
    ap.add_argument("--epic", default="", help="keep only the tasks of this epic (E-NN)")
    ap.add_argument("--workstream", "--chantier", dest="chantier", default="", metavar="WORKSTREAM",
                    help="keep only the tasks of this workstream (old name: --chantier)")
    ap.add_argument("--max", dest="max_", type=int, default=MAX_DEFAUT,
                    help=f"bound of each list and of the parallel picks (default {MAX_DEFAUT}, at least 1)")
    ap.add_argument("--json", action="store_true", help="the reading as JSON")
    args = ap.parse_args(argv)
    if args.max_ < 1:
        ap.error("--max doit valoir au moins 1")
    try:
        rel = relever(str(Path(args.root)), epic=args.epic, chantier=args.chantier, max_=args.max_)
    except AiguillageError as exc:
        print(f"aiguillage: {exc}", file=sys.stderr)
        return 1
    if args.json:
        rel["lignes"] = rendre(rel, args.max_)
        print(json.dumps(rel, indent=2, ensure_ascii=False))
    else:
        print("\n".join(rendre(rel, args.max_)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
