#!/usr/bin/env python3
"""LE CHRONO D'UNE TÂCHE — estimer chaque étape avant son départ, relever son temps réel
(T-01M5HST80E30DFMV3S7WM68Q7N, décision pilote S-01M5HSTM4SXJQFMTGZ82807TJT).

Frère de `tasks.py`, chargé par `tasks.task_chrono_module()` au premier `tasks.py chrono`, après
`start`, `fournee`, `retour`, `done` et `review-scope` (`jalons_du_verbe` : `review-scope` relève
`juges` et ouvre `cloture`, `done` complète `cloture`, `correction` et `porte`), et par `--statusline`
(`suffixe_statusline`) — jamais une partie : il ne lit le board que par les `data` que la façade lui passe.
`plan_preflight.py` et `plan_pool.py check` READY le chargent aussi pour `jalon_de_planification`.

LE JOURNAL. `.agents/state/local/task-chrono/<tid>.jsonl` (ignoré par git) sous la RACINE
COMMUNE (`agent_chrono.racine_commune`) : un dev en worktree lié écrit au même journal que
l'orchestrateur du dépôt principal. UNE ligne JSON par événement, ajoutée en un seul
`os.write` `O_APPEND` :
- `{"ev": "cycle", "cycle": n, "ts"}` — `chrono begin` ouvre le cycle n, ou REPREND le cycle
  ouvert (idempotent) ; un cycle est CLOS quand son étape `done` a une fin — dans l'ordre d'AGENTS.md
  (… cloture → correction → porte → done), la correction et la porte restent dans le cycle ;
  `done` est un JALON : ni estimé, ni compté dans les étapes mesurées ;
- `{"ev": "etape", "cycle", "etape", "lot", "tentative", "phase": "begin"|"end", "ts"}` ; un
  `begin` porte la `taille` lue au board et l'`estimation` FIGÉE avant le départ.
La lecture garde, par clé (cycle, étape, lot, tentative), le PREMIER début et la PREMIÈRE fin
qui le suit : deux écrivains parallèles ou une double fin ne faussent rien.

L'ESTIMATION (avant chaque étape) : (1) `historique` — les étapes finies des cycles locaux
CLOS de toutes les tâches, même étape, même taille connue (fichiers ET lots) ; médiane et p90,
effectif dit ; (2) repli `rôle <agent>` — médiane et p90 mesurées par rôle
(`agent_chrono.releve_etapes`, porte : `porte-chrono.tsv`) ; (3) `inconnu`. L'attente du pilote
n'a jamais d'estimation (`attente humaine`), le jalon `done` non plus (`jalon`).

L'AFFICHAGE (`show`, `--watch`, `--json`) : chaque étape, son estimation, son temps réel ou
écoulé, son écart ; les étapes commencées sans fin restent VISIBLES. Le total : temps écoulé =
UNION des intervalles (des lots parallèles ne s'additionnent jamais), estimation = somme par
étape du plus long lot ; l'écart total n'est rendu que si TOUT le périmètre est mesuré, sinon
les raisons sont dites.

BORNES, DITES : l'historique est LOCAL au poste (un cycle d'un autre poste n'y est pas) ;
l'ajout n'est pas atomique sous Windows (une ligne entrelacée est ignorée à la lecture) ; un
journal illisible lève `ChronoErreur` (rc 2 par la façade) ; le chrono ne BLOQUE rien — ses
appelants ignorent son rc (réserve C28). Stdlib seule.
"""
from __future__ import annotations

import json
import os
import re
import stat
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Callable

JOURNAL_DIR_REL = Path(".agents") / "state" / "local" / "task-chrono"
# Les formes d'id du board (`tasks_requetes._SESSION_ID`) : le nom du journal n'en sort jamais.
TID = re.compile(r"T-(?:[0-9]{1,15}|[0-9A-HJKMNP-TV-Z]{26})")
LIRE_MAX = 1024 * 1024
# Les sources d'estimation qu'écrit `estimer` : une grammaire FERMÉE, bornée, sans caractère de contrôle.
# `?` : le repli de `agent_chrono.releve_etapes` pour un mode de porte vide (agent_chrono.py, `or "?"`).
NOM_SUR = r"(?:[a-z0-9-]{1,40}|\?)"
SOURCE = re.compile(r"historique|attente humaine|jalon|inconnu|(?:rôle|porte) " + NOM_SUR)
ESTIMATION_CLES = ("source", "n", "mediane_s", "p90_s")
# L'ordre d'AGENTS.md, recopié par kickoff.md (témoin W13) ; il ne joue qu'aux messages : `bilan` trie par horodatage.
ETAPES = ("cadrage", "planification", "attente-pilote", "dev", "juges", "fusion", "integration",
          "cloture", "correction", "porte", "done")
ATTENTE_HUMAINE = frozenset({"attente-pilote"})
ETAPE_FINALE = "done"
JALONS = frozenset({ETAPE_FINALE})
NON_MESUREES = ATTENTE_HUMAINE | JALONS
PHASES = ("begin", "end")
# Au-delà, le temps entre l'ouverture du cycle et sa première étape est signalé non relevé dans `bilan`.
TROU_D_OUVERTURE_MS = 60_000
# Repli par rôle : les défs qui jouent l'étape ; la plus mesurée l'emporte. `porte` : porte-chrono.tsv.
# `juges` n'y est pas : une FENÊTRE (juges, intégration, documenter), jamais comparée à la médiane d'un rôle.
ROLES_DE_L_ETAPE: dict[str, tuple[str, ...]] = {
    "cadrage": ("planner",),
    "planification": ("planner", "plan-critic"),
    "dev": ("dev-multi", "dev-mono", "frontend-fidelity", "terraform-deployer"),
    "correction": ("dev-multi", "dev-mono"),
    "cloture": ("critic-opus", "critic-fable", "critic-sonnet-max"),
}
MODE_PORTE_PREFERE = "frozen"
INTERVALLE_WATCH_S = 5.0
_AGENT_CHRONO_NOM = "_task_chrono_agent_chrono"


class ChronoErreur(Exception):
    """Un usage ou un journal que le chrono refuse ; la façade le rend en rc 2."""


def agent_chrono_module() -> Any:
    """Le frère `agent_chrono.py` (racine commune, relevé par rôle), chargé au premier usage."""
    chemin = Path(__file__).resolve().with_name("agent_chrono.py")
    existant = sys.modules.get(_AGENT_CHRONO_NOM)
    if existant is not None and Path(getattr(existant, "__file__", "") or ".").resolve() == chemin:
        return existant
    if not chemin.is_file():
        raise ChronoErreur(f"le frère {chemin} est ABSENT — remède : `git checkout -- .agents/bin/agent_chrono.py`")
    import importlib.util

    spec = importlib.util.spec_from_file_location(_AGENT_CHRONO_NOM, chemin)
    module = importlib.util.module_from_spec(spec)
    sys.modules[_AGENT_CHRONO_NOM] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(_AGENT_CHRONO_NOM, None)
        raise
    return module


def _maintenant_ms() -> int:
    return int(time.time() * 1000)


def racine(root: str | os.PathLike[str]) -> Path:
    """La racine COMMUNE : celle du board validé ET du journal écrit (worktree lié → principal)."""
    return Path(agent_chrono_module().racine_commune(root))


def chemin_journal(base: str | os.PathLike[str], tid: str) -> Path:
    """Le journal de `tid`, revalidé aux formes d'id du board : jamais un chemin hors du dossier."""
    if not isinstance(tid, str) or not TID.fullmatch(tid):
        raise ChronoErreur(f"id {tid!r} hors des formes du board (T-<chiffres> ou T-<ULID>)")
    return Path(base) / JOURNAL_DIR_REL / f"{tid}.jsonl"


def _dossier_sur(chemin: Path) -> None:
    """Le dossier `task-chrono` lui-même n'est pas un lien (`lstat`). BORNE : seuls ce dossier et le journal
    (O_NOFOLLOW, dernier composant) sont gardés ; les composants plus hauts de la racine ne le sont pas."""
    if not stat.S_ISDIR(os.lstat(chemin.parent).st_mode):
        raise ChronoErreur(f"dossier du journal chrono {chemin.parent} : lien symbolique ou pas un dossier")


def _lire_octets(chemin: Path, plafond: int, *, fin: bool = False) -> bytes:
    """Un fichier RÉGULIER lu par son descripteur — ni lien sur le journal ni sur son dossier (`_dossier_sur`),
    ni FIFO bloquante — : `plafond` octets au plus, la FIN du fichier si `fin`, sinon tout le fichier, et
    au-delà du plafond `ChronoErreur`."""
    _dossier_sur(chemin)
    fd = os.open(str(chemin), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    try:
        etat = os.fstat(fd)
        if not stat.S_ISREG(etat.st_mode):
            raise ChronoErreur(f"journal chrono {chemin.name} : pas un fichier régulier")
        if fin:
            os.lseek(fd, max(0, etat.st_size - plafond), os.SEEK_SET)
        elif etat.st_size > plafond:
            raise ChronoErreur(f"journal chrono {chemin.name} : {etat.st_size} octets, au-delà de {plafond}")
        morceaux, reste = [], plafond
        while reste > 0:
            morceau = os.read(fd, min(reste, 65536))
            if not morceau:
                break
            morceaux.append(morceau)
            reste -= len(morceau)
        return b"".join(morceaux)
    finally:
        os.close(fd)


def lire_brut(base: str | os.PathLike[str], tid: str) -> bytes:
    """Les octets du journal de `tid` par la lecture contrôlée (id revalidé, dossier et journal sans lien,
    fichier régulier, LIRE_MAX) ; absent → b"" ; illisible → ChronoErreur. Le lecteur qui passe ensuite
    `octets=` à `lire`/`bilan` les tient d'ici."""
    chemin = chemin_journal(base, tid)
    try:
        return _lire_octets(chemin, LIRE_MAX)
    except FileNotFoundError:
        return b""
    except OSError as exc:
        raise ChronoErreur(f"journal chrono de {tid} illisible ({type(exc).__name__})") from exc


def _octets_admis(chemin: Path, octets: Any) -> bytes:
    """`octets=` fourni : mêmes bornes que la lecture — dossier du journal sans lien (`_dossier_sur`, sauté
    s'il n'existe pas : rien à suivre), type bytes/bytearray, LIRE_MAX ; le chemin n'est jamais ouvert."""
    if not isinstance(octets, (bytes, bytearray)):
        raise ChronoErreur(f"octets du journal chrono : {type(octets).__name__}, ni bytes ni bytearray")
    if len(octets) > LIRE_MAX:
        raise ChronoErreur(f"journal chrono {chemin.name} : {len(octets)} octets, au-delà de {LIRE_MAX}")
    try:
        _dossier_sur(chemin)
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise ChronoErreur(f"dossier du journal chrono illisible ({type(exc).__name__})") from exc
    return bytes(octets)


def lire(base: str | os.PathLike[str], tid: str, octets: bytes | None = None) -> list[dict[str, Any]]:
    """Les lignes lisibles du journal de `tid`, dans l'ordre ; absent → [] ; illisible, pas régulier, lien
    ou au-delà de LIRE_MAX → ChronoErreur. `octets` fourni : ce contenu est analysé sans ouvrir le chemin,
    APRÈS les mêmes contrôles d'id, de dossier et de taille (`_octets_admis`) — le type et l'absence de lien
    du journal lui-même restent à la lecture qui l'a produit (`lire_brut`)."""
    chemin = chemin_journal(base, tid)
    octets = lire_brut(base, tid) if octets is None else _octets_admis(chemin, octets)
    return _analyser(octets.decode("utf-8", errors="replace"))


def _analyser(brut: str) -> list[dict[str, Any]]:
    """Les lignes au schéma, dans l'ordre ; une ligne entrelacée ou coupée est ignorée."""
    out = []
    for ligne in brut.splitlines():
        try:
            obj = json.loads(ligne)
        except ValueError:
            continue
        if _ligne_valide(obj):
            out.append(obj)
    return out


def _entier(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _ligne_valide(obj: Any) -> bool:
    """Une ligne au schéma du journal ; une ligne JSON valide mais d'un autre type est IGNORÉE comme
    une ligne entrelacée — jamais une trace (contrat rc 0 ou 2)."""
    # Les champs COMMUNS (ligne `cycle` comme ligne `etape`) : un cycle entier ≥ 1, un horodatage entier,
    # un `tid` absent ou à la forme d'un id du board.
    if not isinstance(obj, dict) or obj.get("ev") not in ("cycle", "etape") or not _entier(obj.get("cycle")) \
            or obj["cycle"] < 1 or not _entier(obj.get("ts")):
        return False
    tid = obj.get("tid")
    if not (tid is None or (isinstance(tid, str) and TID.fullmatch(tid))):
        return False
    if obj["ev"] == "cycle":
        return True
    # FILTRE À LA SOURCE : une ligne d'étape est REJETÉE si son étape n'est pas dans ETAPES, si son lot n'a pas
    # la forme d'un id du board, ou si une des clés d'estimation connues (ESTIMATION_CLES) a un mauvais type ou,
    # pour `source`, sort de la grammaire SOURCE. Les AUTRES clés d'estimation ne sont pas jugées ici : `cycles`
    # ne garde que ESTIMATION_CLES (projection), donc aucune ne ressort ni dans `show`, ni dans `--json`, ni dans
    # la ligne d'état. `taille` n'est jamais rendue : seul son type (dict ou None) est contrôlé.
    lot = obj.get("lot")
    if obj.get("etape") not in ETAPES or not (lot is None or (isinstance(lot, str) and TID.fullmatch(lot))):
        return False
    taille, est = obj.get("taille"), obj.get("estimation")
    if not (taille is None or isinstance(taille, dict)) or not (est is None or isinstance(est, dict)):
        return False
    if est is None:
        return True
    if "source" in est and not (isinstance(est["source"], str) and SOURCE.fullmatch(est["source"])):
        return False
    if not all(_entier(est[k]) for k in ("n", "mediane_s", "p90_s") if k in est):
        return False
    return "mediane_s" not in est or all(k in est for k in ESTIMATION_CLES)


def _estimation_projetee(est: Any) -> dict[str, Any] | None:
    """Les seules clés connues d'une estimation déjà validée ; toute autre clé du journal est écartée."""
    return {k: est[k] for k in ESTIMATION_CLES if k in est} if isinstance(est, dict) else None


def _noter(base: str | os.PathLike[str], tid: str, ligne: dict[str, Any]) -> None:
    """UNE ligne en un seul `os.write` `O_APPEND` dans un fichier RÉGULIER ; ni le journal ni son dossier
    ne sont suivis s'ils sont des liens (même borne que `_dossier_sur`) ; une FIFO, même lue, est refusée."""
    chemin = chemin_journal(base, tid)
    try:
        chemin.parent.mkdir(parents=True, exist_ok=True)
        _dossier_sur(chemin)
        octets = (json.dumps(ligne, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
        fd = os.open(str(chemin), os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
                     | getattr(os, "O_NONBLOCK", 0), 0o644)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ChronoErreur(f"journal chrono de {tid} non écrit : pas un fichier régulier")
            os.write(fd, octets)
        finally:
            os.close(fd)
    except OSError as exc:
        raise ChronoErreur(f"journal chrono de {tid} non écrit ({type(exc).__name__}: {exc})") from exc


def cycles(lignes: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """{n: {"debut", "etapes": {(etape, lot, tentative): {...}}}} ; premier début, première fin après lui."""
    out: dict[int, dict[str, Any]] = {}
    for ligne in lignes:
        c = out.setdefault(ligne["cycle"], {"debut": ligne["ts"], "etapes": {}})
        if ligne["ev"] != "etape" or ligne.get("phase") not in PHASES or not _entier(ligne.get("tentative")):
            continue
        cle = (str(ligne.get("etape")), ligne.get("lot") or "", ligne["tentative"])
        e = c["etapes"].get(cle)
        if ligne["phase"] == "begin" and e is None:
            c["etapes"][cle] = {"etape": cle[0], "lot": cle[1] or None, "tentative": cle[2], "debut": ligne["ts"],
                                "taille": ligne.get("taille"),
                                "estimation": _estimation_projetee(ligne.get("estimation"))}
        elif ligne["phase"] == "end" and e is not None and "fin" not in e and ligne["ts"] >= e["debut"]:
            e["fin"] = ligne["ts"]
    return out


def est_clos(cycle: dict[str, Any]) -> bool:
    """Seul le jalon final du PARENT (sans lot) clôt le cycle ; une ligne de lot ne le ferme jamais."""
    return any(e["etape"] == ETAPE_FINALE and e["lot"] is None and "fin" in e for e in cycle["etapes"].values())


def _fin_du_jalon(cycle: dict[str, Any]) -> int | None:
    """La fin du jalon done du PARENT : l'instant où le cycle s'est clos ; None tant qu'il est ouvert."""
    fins = [e["fin"] for e in cycle["etapes"].values() if e["etape"] == ETAPE_FINALE and e["lot"] is None and "fin" in e]
    return min(fins) if fins else None


def cycle_ouvert(lignes: list[dict[str, Any]]) -> int | None:
    ouverts = [n for n, c in cycles(lignes).items() if not est_clos(c)]
    return max(ouverts) if ouverts else None


def commencer(base: str | os.PathLike[str], tid: str, now_ms: int | None = None) -> tuple[int, bool]:
    """(n, nouveau) : le cycle ouvert est REPRIS (nouveau False), sinon le cycle suivant est ouvert."""
    lignes = lire(base, tid)
    ouvert = cycle_ouvert(lignes)
    if ouvert is not None:
        return ouvert, False
    n = max((l["cycle"] for l in lignes), default=0) + 1
    _noter(base, tid, {"ev": "cycle", "tid": tid, "cycle": n, "ts": _maintenant_ms() if now_ms is None else int(now_ms)})
    return n, True


def taille_de(data: dict[str, Any], tid: str, lot: str | None = None) -> dict[str, int | None]:
    """Taille CONNUE : fichiers du write-set (le lot ; sinon la tâche ∪ ses lots) et nombre de lots.
    Aucun write-set → `fichiers` None : la taille est inconnue, l'historique ne s'applique pas."""
    taches = {t.get("id"): t for t in data.get("tasks", [])}
    if lot:
        return {"fichiers": len(set(taches.get(lot, {}).get("writeset") or [])) or None, "lots": 1}
    lots = [t for t in taches.values() if isinstance(t.get("fournee"), dict) and t["fournee"].get("parent") == tid]
    fichiers = set(taches.get(tid, {}).get("writeset") or [])
    for t in lots:
        fichiers |= set(t.get("writeset") or [])
    return {"fichiers": len(fichiers) or None, "lots": len(lots)}


def _mediane_p90(valeurs: list[int]) -> tuple[int, int]:
    tri = sorted(valeurs)
    return int(round(statistics.median(tri))), tri[max(0, -(-9 * len(tri) // 10) - 1)]


def historique(base: str | os.PathLike[str], etape: str, taille: dict[str, Any] | None) -> list[int]:
    """Durées (s) de `etape` dans les cycles CLOS de tous les journaux locaux, à taille égale."""
    if not taille or not taille.get("fichiers"):
        return []
    dossier = Path(base) / JOURNAL_DIR_REL
    try:
        fichiers = sorted(dossier.glob("*.jsonl"))
    except OSError:
        return []
    out = []
    for fichier in fichiers:
        try:
            lignes = lire(base, fichier.stem)
        except ChronoErreur:
            continue
        for c in cycles(lignes).values():
            if not est_clos(c):
                continue
            out += [max(0, round((e["fin"] - e["debut"]) / 1000)) for e in c["etapes"].values()
                    if e["etape"] == etape and "fin" in e and e.get("taille") == taille]
    return out


def _repli_par_role(base: str | os.PathLike[str], etape: str) -> dict[str, Any] | None:
    releve = agent_chrono_module().releve_etapes(base)
    if etape == "porte":
        modes = {m: f for m, f in releve["portes"]["modes"].items() if "duree_mediane" in f}
        if not modes:
            return None
        mode = MODE_PORTE_PREFERE if MODE_PORTE_PREFERE in modes else max(modes, key=lambda m: modes[m]["vertes"])
        f = modes[mode]
        # Le mode vient du TSV de la porte, écrit hors du chrono : hors grammaire, il s'écrit `?` — jamais une
        # source que `_ligne_valide` rejetterait à la relecture (le `end` tomberait en « fin sans début »).
        nom = mode if re.fullmatch(NOM_SUR, mode) else "?"
        return {"source": f"porte {nom}", "n": f["vertes"], "mediane_s": f["duree_mediane"], "p90_s": f["duree_p90"]}
    candidats = [(releve["agents"][a]["mesures"], a) for a in ROLES_DE_L_ETAPE.get(etape, ())
                 if "duree_mediane" in releve["agents"].get(a, {})]
    if not candidats:
        return None
    _n, agent = max(candidats)
    f = releve["agents"][agent]
    return {"source": f"rôle {agent}", "n": f["mesures"], "mediane_s": f["duree_mediane"], "p90_s": f["duree_p90"]}


def estimer(base: str | os.PathLike[str], etape: str, taille: dict[str, Any] | None) -> dict[str, Any]:
    """{"source", "n"[, "mediane_s", "p90_s"]} : historique, puis rôle, puis inconnu."""
    if etape not in ETAPES:
        raise ChronoErreur(f"étape {etape!r} hors liste fermée {', '.join(ETAPES)}")
    if etape in ATTENTE_HUMAINE:
        return {"source": "attente humaine", "n": 0}
    if etape in JALONS:
        return {"source": "jalon", "n": 0}
    durees = historique(base, etape, taille)
    if durees:
        med, p90 = _mediane_p90(durees)
        return {"source": "historique", "n": len(durees), "mediane_s": med, "p90_s": p90}
    return _repli_par_role(base, etape) or {"source": "inconnu", "n": 0}


def _cles(c: dict[str, Any], etape: str, lot: str | None) -> list[tuple[str, str, int]]:
    return sorted(k for k in c["etapes"] if k[0] == etape and k[1] == (lot or ""))


def _ecart(sec: int) -> str:
    return ("+" if sec >= 0 else "-") + agent_chrono_module().fmt_duree(abs(sec))


def _texte_estimation(est: dict[str, Any] | None) -> str:
    fmt = agent_chrono_module().fmt_duree
    if not est:
        return "inconnu"
    if "mediane_s" not in est:
        return est.get("source") or "inconnu"
    return f"{fmt(est['mediane_s'])} (p90 {fmt(est['p90_s'])}) — {est['source']}, n={est['n']}"


def etape(base: str | os.PathLike[str], tid: str, nom: str, phase: str, lot: str | None = None,
          tentative: int | None = None, taille: dict[str, Any] | None = None, now_ms: int | None = None) -> str:
    """`step` : un début (estimation figée avant le départ) ou une fin ; reprise et double fin idempotentes."""
    if nom not in ETAPES:
        raise ChronoErreur(f"étape {nom!r} hors liste fermée {', '.join(ETAPES)}")
    if phase not in PHASES:
        raise ChronoErreur(f"phase {phase!r} hors {PHASES}")
    if tentative is not None and tentative < 1:
        raise ChronoErreur(f"--tentative {tentative} : un entier ≥ 1")
    if lot is not None and not TID.fullmatch(lot):
        raise ChronoErreur(f"lot {lot!r} hors des formes du board (T-<chiffres> ou T-<ULID>)")
    if nom in JALONS and lot:
        raise ChronoErreur(f"jalon {nom!r} refusé sous le lot {lot} : il se joue sur le PARENT seul, après SON done")
    ts = _maintenant_ms() if now_ms is None else int(now_ms)
    quoi = nom + (f" lot {lot}" if lot else "")
    if phase == "begin" and nom == ETAPE_FINALE:
        tous = cycles(lire(base, tid))
        if tous and not any(not est_clos(c) for c in tous.values()):
            # `tasks.py done` a déjà posé le jalon : celui du lanceur, joué après, ne rouvre pas un cycle fantôme.
            return f"CHRONO: {tid} cycle {max(tous)} déjà clos — jalon {nom} ignoré"
    if phase == "begin":
        n, _nouveau = commencer(base, tid, ts)
        c = cycles(lire(base, tid))[n]
        cles = _cles(c, nom, lot)
        if tentative is None:
            ouvertes = [k for k in cles if "fin" not in c["etapes"][k]]
            if ouvertes:
                return f"CHRONO: {tid} cycle {n} {quoi} tentative {ouvertes[-1][2]} déjà commencée — reprise"
            tentative = (cles[-1][2] + 1) if cles else 1
        elif (nom, lot or "", tentative) in c["etapes"]:
            return f"CHRONO: {tid} cycle {n} {quoi} tentative {tentative} déjà commencée — reprise"
        est = estimer(base, nom, taille)
        _noter(base, tid, {"ev": "etape", "tid": tid, "cycle": n, "etape": nom, "lot": lot, "tentative": tentative,
                           "phase": "begin", "ts": ts, "taille": taille, "estimation": est})
        return f"CHRONO: {tid} cycle {n} {quoi} tentative {tentative} — début ; estimation {_texte_estimation(est)}"
    tous = cycles(lire(base, tid))
    # Le cycle COURANT seul : une fin sans début ici ne ferme jamais un début orphelin d'un cycle clos.
    for n in ([max(tous)] if tous else []):
        c = tous[n]
        cles = [k for k in _cles(c, nom, lot) if tentative is None or k[2] == tentative]
        if not cles:
            continue
        ouvertes = [k for k in cles if "fin" not in c["etapes"][k]]
        if not ouvertes:
            return f"CHRONO: {tid} cycle {n} {quoi} tentative {cles[-1][2]} déjà finie — fin ignorée"
        cle = ouvertes[-1]
        e = c["etapes"][cle]
        _noter(base, tid, {"ev": "etape", "tid": tid, "cycle": n, "etape": nom, "lot": lot, "tentative": cle[2],
                           "phase": "end", "ts": max(ts, e["debut"])})
        duree = max(0, round((max(ts, e["debut"]) - e["debut"]) / 1000))
        est = e.get("estimation") or {}
        ecart = f", écart {_ecart(duree - est['mediane_s'])}" if "mediane_s" in est else ""
        return (f"CHRONO: {tid} cycle {n} {quoi} tentative {cle[2]} — fin en "
                f"{agent_chrono_module().fmt_duree(duree)}{ecart}")
    raise ChronoErreur(f"{tid} : fin de {quoi} sans début relevé — `tasks.py chrono {tid} step --etape {nom} --phase begin` d'abord")


def _union_s(intervalles: list[tuple[int, int]]) -> int:
    total, fin_courante, debut_courant = 0, None, None
    for d, f in sorted(intervalles):
        if fin_courante is None or d > fin_courante:
            if fin_courante is not None:
                total += fin_courante - debut_courant
            debut_courant, fin_courante = d, f
        else:
            fin_courante = max(fin_courante, f)
    if fin_courante is not None:
        total += fin_courante - debut_courant
    return round(total / 1000)


def bilan(base: str | os.PathLike[str], tid: str, now_ms: int | None = None,
          octets: bytes | None = None) -> dict[str, Any]:
    """Le dernier cycle de `tid` : étapes, totaux, et l'écart total seulement si tout est mesuré.
    `octets` : le journal déjà lu par l'appelant (`lire_brut`), passé à `lire` sans réouverture du chemin,
    sous les mêmes contrôles d'id, de dossier, de type et de taille (`_octets_admis`)."""
    now = _maintenant_ms() if now_ms is None else int(now_ms)
    tous = cycles(lire(base, tid, octets))
    if not tous:
        return {"tid": tid, "cycle": None, "clos": False, "etapes": [], "total": None,
                "incomplet": ["aucun cycle relevé"]}
    n = max(tous)
    c = tous[n]
    # UN CYCLE CLOS NE GRANDIT PLUS (C1) : une étape sans fin y est bornée à la fin du jalon done — en
    # LECTURE seule ; aucune fin n'est écrite, l'historique n'apprend que des fins réelles.
    borne = _fin_du_jalon(c)
    if borne is not None:
        now = borne
    lignes, incomplet = [], []
    for e in sorted(c["etapes"].values(), key=lambda e: (e["debut"], e["etape"], e["lot"] or "", e["tentative"])):
        fin = e.get("fin")
        reel = max(0, round(((fin if fin is not None else now) - e["debut"]) / 1000))
        est = e.get("estimation") or {"source": "inconnu", "n": 0}
        ligne = {"etape": e["etape"], "lot": e["lot"], "tentative": e["tentative"], "statut": "finie" if fin else
                 ("incomplète" if est_clos(c) else "en cours"), "reel_s": reel, "estimation": est}
        if fin is not None and "mediane_s" in est:
            ligne["ecart_s"] = reel - est["mediane_s"]
        lignes.append(ligne)
    mesurees = [l for l in lignes if l["etape"] not in NON_MESUREES]
    if any(l["statut"] != "finie" for l in mesurees):
        incomplet.append(f"{sum(1 for l in mesurees if l['statut'] != 'finie')} étape(s) sans fin")
    if any("mediane_s" not in l["estimation"] for l in mesurees):
        incomplet.append(f"{sum(1 for l in mesurees if 'mediane_s' not in l['estimation'])} étape(s) sans estimation")
    if not est_clos(c):
        incomplet.append(f"cycle ouvert ({ETAPE_FINALE} non fini)")
    premiere = min((e["debut"] for e in c["etapes"].values()), default=None)
    if premiere is not None and premiere - c["debut"] > TROU_D_OUVERTURE_MS:
        incomplet.append(f"{agent_chrono_module().fmt_duree(round((premiere - c['debut']) / 1000))} entre "
                         "l'ouverture du cycle et la première étape, non relevés")
    intervalles = [(e["debut"], max(e["debut"], e.get("fin", now))) for e in c["etapes"].values()
                   if e["etape"] not in NON_MESUREES]
    par_etape: dict[str, dict[str, int]] = {}
    for l in mesurees:
        if "mediane_s" in l["estimation"]:
            groupe = par_etape.setdefault(l["etape"], {})
            groupe[l["lot"] or ""] = groupe.get(l["lot"] or "", 0) + l["estimation"]["mediane_s"]
    total = {"reel_s": _union_s(intervalles), "estime_s": sum(max(g.values()) for g in par_etape.values())}
    if not incomplet:
        total["ecart_s"] = total["reel_s"] - total["estime_s"]
    return {"tid": tid, "cycle": n, "clos": est_clos(c), "etapes": lignes, "total": total,
            "incomplet": incomplet + ["historique local seulement (un autre poste n'y est pas)"]}


def rendre(b: dict[str, Any]) -> str:
    fmt = agent_chrono_module().fmt_duree
    if b["cycle"] is None:
        return f"CHRONO {b['tid']} : aucun cycle relevé"
    out = [f"CHRONO {b['tid']} cycle {b['cycle']} — {'clos' if b['clos'] else 'en cours'}",
           f"  {'étape':<15} {'lot':<8} {'t':>2} {'statut':<10} {'réel':>9} {'écart':>9}  estimation"]
    for l in b["etapes"]:
        ecart = _ecart(l["ecart_s"]) if "ecart_s" in l else "-"
        # La FIN de l'id : le préfixe ULID (horodatage) est commun aux lots d'une même fournée.
        out.append(f"  {l['etape']:<15} {(l['lot'] or '-')[-8:]:<8} {l['tentative']:>2} {l['statut']:<10} "
                   f"{fmt(l['reel_s']):>9} {ecart:>9}  {_texte_estimation(l['estimation'])}")
    t = b["total"]
    if "ecart_s" in t:
        out.append(f"total : réel {fmt(t['reel_s'])}, estimé {fmt(t['estime_s'])}, écart {_ecart(t['ecart_s'])}")
    else:
        out.append(f"total : réel {fmt(t['reel_s'])}, estimé {fmt(t['estime_s'])} — écart non rendu")
    out.append("incomplet : " + " ; ".join(b["incomplet"]))
    return "\n".join(out)


def regarder(base: str | os.PathLike[str], tid: str, ecrire: Callable[[str], None] = print,
             dormir: Callable[[float], None] = time.sleep, max_tours: int | None = None,
             horloge: Callable[[], int] | None = None) -> None:
    """`show --watch` : un cadre par intervalle jusqu'au cycle clos, Ctrl-C, ou `max_tours` (bancs)."""
    tours = 0
    try:
        while True:
            b = bilan(base, tid, horloge() if horloge else None)
            ecrire(rendre(b))
            tours += 1
            if b["clos"] or b["cycle"] is None or (max_tours is not None and tours >= max_tours):
                return
            dormir(INTERVALLE_WATCH_S)
    except KeyboardInterrupt:
        return


def executer(base: str | os.PathLike[str], data: dict[str, Any], tid: str, action: str, *, etape_nom: str | None = None,
             phase: str | None = None, lot: str | None = None, tentative: int | None = None, watch: bool = False,
             en_json: bool = False, ecrire: Callable[[str], None] = print) -> str:
    """Une action, ses options validées ; `tid` et `lot` sont déjà validés au board par la façade."""
    permises = {"estimate": {"etape", "lot"}, "begin": set(), "step": {"etape", "phase", "lot", "tentative"},
                "show": {"watch", "json"}}
    donnees = {"etape": etape_nom, "phase": phase, "lot": lot, "tentative": tentative,
               "watch": watch or None, "json": en_json or None}
    if action not in permises:
        raise ChronoErreur(f"action {action!r} hors estimate|begin|step|show")
    hors = sorted(o for o, v in donnees.items() if v is not None and o not in permises[action])
    if hors:
        raise ChronoErreur(f"chrono {action} : option(s) {', '.join('--' + o for o in hors)} hors de cette action")
    if action in ("estimate", "step") and etape_nom is None:
        raise ChronoErreur(f"chrono {action} exige --etape ({'|'.join(ETAPES)})")
    if action == "step" and phase is None:
        raise ChronoErreur("chrono step exige --phase begin|end")
    if watch and en_json:
        raise ChronoErreur("chrono show : --watch et --json ne se combinent pas")
    if action == "estimate":
        taille = taille_de(data, tid, lot)
        return (f"CHRONO: estimation {etape_nom}{' lot ' + lot if lot else ''} : "
                f"{_texte_estimation(estimer(base, etape_nom, taille))} ; taille {taille['fichiers'] or '?'} "
                f"fichier(s), {taille['lots']} lot(s)")
    if action == "begin":
        n, nouveau = commencer(base, tid)
        return f"CHRONO: {tid} cycle {n} {'ouvert' if nouveau else 'repris (déjà ouvert)'}"
    if action == "step":
        taille = taille_de(data, tid, lot) if phase == "begin" else None
        return etape(base, tid, etape_nom, phase, lot=lot, tentative=tentative, taille=taille)
    if watch:
        regarder(base, tid, ecrire=ecrire)
        return ""
    b = bilan(base, tid)
    return json.dumps(b, ensure_ascii=False, indent=2) if en_json else rendre(b)


# LES JALONS POSÉS PAR `tasks.py` (T-01M5KKFBCXXEVYR8GJPYFEH3C8, décision pilote S-01M5KKFJ4MB8BYA3B9K2SE3973) :
# `start`/`fournee` ouvrent le cycle puis le dev, `retour` ferme le dev et ouvre la fusion, `done` pose le
# jalon et DIT ce qui reste sans fin. Hors /kickoff le cycle se relève donc quand même ; sous /kickoff, les
# appels du lanceur deviennent des reprises (tentative ouverte réutilisée, finie jamais rouverte).
# LA FIN DE LA FUSION S'ÉCRIT SEULE (T-01M5PFPSCG0GXM12SK1MRYGZDY, même décision) : au `retour` et au
# `done`, chaque fusion OUVERTE du cycle courant (journal de la mère pour un lot) dont la pointe relevée
# `retour.tip` est le SECOND parent d'une fusion de la chaîne `--first-parent` de HEAD — ou, pour un
# relevé `--vers <L>` (voie livraison, `retour.vers`), de la branche `refs/heads/<L>` ; un `vers` hors du
# motif d'un nom de branche simple retombe sur HEAD avec un avis — se ferme à
# l'HEURE DU COMMIT de la plus ancienne de ces fusions. git tourne HORS du verrou du board (S-00004192,
# voie (a)) : `fusions_a_mesurer` (sous verrou, aucun git) → `fusions_premesurees` (git injecté) →
# `jalons_du_verbe(fusions=…)` (sous verrou, chaque fusion RELUE au journal avant d'être écrite). La fin
# manuelle du lanceur (`chrono <lot> step --etape fusion --phase end`, après SAST et tests) reste
# admise : la première fin écrite l'emporte — posée AVANT le `retour` ou le `done`, c'est elle la fin
# retenue, la fin automatique est alors sautée ; posée APRÈS la fin automatique, elle est ignorée (« déjà
# finie »). BORNES : une avance rapide, un squash, un rebase, ou une fusion du lot amenée dans HEAD par
# une autre fusion (hors chaîne `--first-parent`) n'écrivent aucune fin — la fusion reste dite sans fin ;
# une passe de correction qui réécrit `retour.tip` avant tout `retour`/`done` ferme la fusion à la
# fusion de correction. Rien ici ne refuse : la façade (`tasks._chrono_apres`) imprime les avis sur
# stderr, sans toucher au rc ni au stdout du verbe. BORNE : le dev d'un lot de fournée court dès la
# fournée, l'attente d'une place de charge y est comptée.
# LA QUEUE APRÈS LE DEV (T-01M5PVWHM8KRNRF960PTBV4FE7) : `review-scope` abouti ferme d'abord les fusions
# (comme `retour`), puis relève `juges` = [plus grande fin dev/fusion du cycle → maintenant] si le cycle
# n'a AUCUNE clé `juges` (tout lot) — une FENÊTRE (juges, intégration, documenter), jamais « exec-critic
# mesuré », ni estimée par un rôle — et ouvre `cloture`. Avec des lots, seules leurs fins comptent (la
# fusion de correction du parent n'avance pas le début) ; une fusion de tentative > 1 non plus. BORNE : un
# dev encore ouvert (d'un lot, ou à côté d'une fin écrite) rend un avis « dev encore ouvert » et n'écrit
# ni juges ni clôture — le review-scope suivant les relève ; une tâche sans lot dont le SEUL dev est
# ouvert (voie directe sans `retour`) n'est pas couverte : avis « aucune fin », `cloture` ouverte. Le `done` du parent (ou d'une tâche seule ; jamais d'un lot) complète, en
# trois temps comme la fusion (`portes_a_mesurer` sous verrou sans git → `portes_premesurees` hors verrou →
# `jalons_du_verbe(portes=…)` sous verrou) : la fin de `cloture` (celle du journal, sinon le plus grand `at`
# des traces de revue dans [début de cloture ou du cycle, maintenant]), une `porte` par ligne frozen ou
# frozen-linux de `porte-chrono.tsv` dans [fin de clôture à la seconde, maintenant] dont le sha CONTIENT toutes les
# pointes relevées (tâche et lots), et `correction` = [fin de clôture → 1re porte]. BORNES : une porte
# commune d'une fournée, ou le sha d'une autre tâche qui contient nos pointes, est comptée pour chacune ;
# sans clé `cloture` ni trace, rien (aucun avis, aucun git).
VERBES_JALONNES = ("start", "fournee", "retour", "done", "review-scope")
VERBES_DE_FUSION = ("retour", "done", "review-scope")
MODES_PORTE_FIGES = frozenset({"frozen", "frozen-linux"})
AVIS_ETAPES_NOMMEES = 5
# Seule une pointe de cette forme atteint git : un relevé forgé au board n'y devient jamais une option.
SHA_PLEIN = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
# Seule une livraison `retour.vers` de cette forme (et sans `..`) devient une ref passée à git.
BRANCHE_SIMPLE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*")


def _parent_de(data: dict[str, Any], tid: str) -> str | None:
    for t in data.get("tasks", []):
        if t.get("id") == tid:
            f = t.get("fournee")
            parent = f.get("parent") if isinstance(f, dict) else None
            return parent if isinstance(parent, str) and parent else None
    return None


def _lots_de(data: dict[str, Any], tid: str, etats: tuple[str, ...] | None = None) -> list[str]:
    return [t["id"] for t in data.get("tasks", []) if isinstance(t.get("id"), str)
            and isinstance(t.get("fournee"), dict) and t["fournee"].get("parent") == tid
            and (etats is None or t.get("state") in etats)]


def _cycle_courant(base: str | os.PathLike[str], tid: str) -> tuple[int, dict[str, Any]] | None:
    tous = cycles(lire(base, tid))
    ouverts = [n for n, c in tous.items() if not est_clos(c)]
    return (max(ouverts), tous[max(ouverts)]) if ouverts else None


def _ouvrir_dev(base: str | os.PathLike[str], data: dict[str, Any], journal: str, lot: str | None, now: int) -> None:
    """Le dev de `lot` au cycle (ouvert ou repris) de `journal`, seulement s'il n'y a AUCUNE clé dev pour lui.
    `start`/`fournee` ferment d'abord `planification` et `attente-pilote` (sans lot) restées ouvertes : le dev
    part, elles sont finies (`jalon_de_planification` a pu les ouvrir — /kickoff ne joue pas de `check` READY
    entre préflight et start) ; une fin du lanceur posée avant l'emporte."""
    n, _nouveau = commencer(base, journal, now)
    for nom in ("planification", "attente-pilote"):
        if any("fin" not in e for k, e in cycles(lire(base, journal))[n]["etapes"].items() if k[:2] == (nom, "")):
            etape(base, journal, nom, "end", now_ms=now)
    if not _cles(cycles(lire(base, journal))[n], "dev", lot):
        etape(base, journal, "dev", "begin", lot=lot, taille=taille_de(data, journal, lot), now_ms=now)


def _retour(base: str | os.PathLike[str], data: dict[str, Any], journal: str, lot: str | None, now: int) -> None:
    courant = _cycle_courant(base, journal)
    if courant is None:  # sans cycle ouvert, rien d'écrit
        return
    _n, c = courant
    if any("fin" not in c["etapes"][k] for k in _cles(c, "dev", lot)):
        etape(base, journal, "dev", "end", lot=lot, now_ms=now)
    if not _cles(c, "fusion", lot):
        etape(base, journal, "fusion", "begin", lot=lot, taille=taille_de(data, journal, lot), now_ms=now)


def _jalon_done(base: str | os.PathLike[str], tid: str, now: int) -> list[str]:
    tous = cycles(lire(base, tid))
    if not tous:
        return [f"CHRONO: avis {tid} — aucun cycle au journal local : ce done n'est pas mesuré "
                "(journal git-ignoré : absent de ce poste, ou effacé)"]
    courant = _cycle_courant(base, tid)
    if courant is None:  # dernier cycle clos : no-op, jamais un cycle fantôme
        return []
    n, c = courant
    sans_fin = sorted((e for e in c["etapes"].values() if "fin" not in e and e["etape"] not in JALONS),
                      key=lambda e: (e["debut"], e["etape"], e["lot"] or "", e["tentative"]))
    etape(base, tid, ETAPE_FINALE, "begin", now_ms=now)
    etape(base, tid, ETAPE_FINALE, "end", now_ms=now)
    if not sans_fin:
        return []
    noms = [e["etape"] + (f" lot {e['lot'][-8:]}" if e["lot"] else "") for e in sans_fin]
    reste = len(noms) - AVIS_ETAPES_NOMMEES
    return [f"CHRONO: avis {tid} cycle {n} clos avec {len(noms)} étape(s) sans fin, bornée(s) au done : "
            + ", ".join(noms[:AVIS_ETAPES_NOMMEES]) + (f" (+{reste})" if reste > 0 else "")]


def _parent_clos(base: str | os.PathLike[str], data: dict[str, Any], parent: str) -> bool:
    """Un PARENT `done` au board, sans journal local (git-ignoré : autre poste, ou effacé) ou dont le
    dernier cycle est clos : le verbe d'un de ses lots n'y ouvre pas de cycle (cycle fantôme). Une reprise
    du parent lui-même (start après reopen) en ouvre un."""
    etat = next((t.get("state") for t in data.get("tasks", []) if t.get("id") == parent), None)
    if etat != "done":
        return False
    tous = cycles(lire(base, parent))
    return not tous or est_clos(tous[max(tous)])


def _pointe(data: dict[str, Any], tid: str) -> tuple[str, str, str | None] | None:
    """La pointe `retour.tip` de `tid` au board, seulement si c'est un sha PLEIN, avec la ref où chercher
    sa fusion : `refs/heads/<vers>` pour un relevé `--vers <L>` (branche de livraison), HEAD sinon. Un
    `vers` hors du motif d'un nom de branche simple retombe sur HEAD avec un avis (3e élément)."""
    for t in data.get("tasks", []):
        if t.get("id") == tid:
            releve = t.get("retour")
            releve = releve if isinstance(releve, dict) else {}
            tip = releve.get("tip")
            if not (isinstance(tip, str) and SHA_PLEIN.fullmatch(tip)):
                return None
            vers = releve.get("vers")
            if vers is None or vers == "":
                return tip, "HEAD", None
            if isinstance(vers, str) and BRANCHE_SIMPLE.fullmatch(vers) and ".." not in vers:
                return tip, f"refs/heads/{vers}", None
            return tip, "HEAD", (f"CHRONO: avis {tid} — livraison {vers!r} hors du motif d'un nom de branche : "
                                 "fin de fusion cherchée dans HEAD")
    return None


def fusions_a_mesurer(base: str | os.PathLike[str], data: dict[str, Any], verbe: str,
                      tids: list[str]) -> list[dict[str, Any]]:
    """SANS git (appelée sous le verrou du board) : les fusions OUVERTES du cycle courant de chaque journal
    touché par `retour`/`done` — la mère pour un lot, la tâche sinon —, tous lots du cycle compris, chacune
    avec la pointe relevée de sa tâche. Une fusion sans pointe en sha plein n'est pas candidate."""
    if verbe not in VERBES_DE_FUSION:
        return []
    journaux: list[str] = []
    for tid in tids:
        journal = _parent_de(data, tid) or tid
        if journal not in journaux:
            journaux.append(journal)
    candidats: list[dict[str, Any]] = []
    for journal in journaux:
        courant = _cycle_courant(base, journal)
        if courant is None:
            continue
        n, c = courant
        for (nom, lot, tentative), mesure in c["etapes"].items():
            if nom != "fusion" or "fin" in mesure:
                continue
            pointe = _pointe(data, lot or journal)
            if pointe is not None:
                tip, ref, avis = pointe
                cand = {"journal": journal, "cycle": n, "lot": lot or None, "tentative": tentative,
                        "tip": tip, "ref": ref}
                if avis:
                    cand["avis"] = avis
                candidats.append(cand)
    return candidats


def fusions_premesurees(candidats: list[dict[str, Any]],
                        git: Callable[..., str]) -> tuple[dict[tuple[str, int, str | None, int], int], list[str]]:
    """HORS du verrou : pour chaque pointe, `git log --first-parent --merges --ancestry-path <tip>..<ref>`
    (`ref` : la livraison `refs/heads/<L>` d'un relevé `--vers`, HEAD sinon) ; la fusion la PLUS ANCIENNE
    dont le second parent est la pointe donne la fin (heure du commit, en ms). Rend
    ({(journal, cycle, lot, tentative): ts_ms}, avis). Aucun candidat : aucun git, aucun avis ; une pointe
    sans telle fusion (pas encore fusionnée, avance rapide) : rien ; une panne git : un avis."""
    mesures: dict[tuple[str, int, str | None, int], int] = {}
    pannes: list[str] = []
    avis: list[str] = []
    par_pointe: dict[tuple[str, str], int | None] = {}
    for cand in candidats:
        if cand.get("avis") and cand["avis"] not in avis:
            avis.append(cand["avis"])
        tip, ref = cand["tip"], cand.get("ref", "HEAD")
        if (tip, ref) not in par_pointe:
            par_pointe[(tip, ref)] = None
            try:
                sortie = git("log", "--first-parent", "--merges", "--ancestry-path", "--format=%H %P %ct",
                             f"{tip}..{ref}")
            except Exception as exc:  # noqa: BLE001 — le chrono observe, il ne bloque jamais le verbe
                pannes.append(f"{type(exc).__name__}: {exc}")
                continue
            for ligne in sortie.splitlines():  # du plus récent au plus ancien : la dernière trouvée gagne
                champs = ligne.split()
                if len(champs) >= 4 and champs[2] == tip and champs[-1].isdigit():
                    par_pointe[(tip, ref)] = int(champs[-1]) * 1000
        fin = par_pointe[(tip, ref)]
        if fin is not None:
            mesures[(cand["journal"], cand["cycle"], cand["lot"], cand["tentative"])] = fin
    if pannes:
        avis.append(f"CHRONO: avis — fin de fusion non mesurée ({len(pannes)} pointe(s)) : {pannes[0]}")
    return mesures, avis


def _fermer_fusions(base: str | os.PathLike[str], fusions: dict[tuple[str, int, str | None, int], int]) -> list[str]:
    """Sous le verrou : chaque fin pré-mesurée n'est écrite que si le journal RELU porte encore cette fusion
    OUVERTE, au même cycle, dernier du journal ; sinon (déjà finie, cycle changé, fusion absente) sautée.
    Une erreur d'une entrée devient un avis : les jalons du verbe qui suivent sont toujours posés."""
    avis: list[str] = []
    for (journal, n, lot, tentative), ts in fusions.items():
        try:
            tous = cycles(lire(base, journal))
            c = tous.get(n)
            mesure = c["etapes"].get(("fusion", lot or "", tentative)) if c is not None else None
            if mesure is None or "fin" in mesure or n != max(tous) or est_clos(c):
                continue
            etape(base, journal, "fusion", "end", lot=lot, tentative=tentative, now_ms=ts)
        except (ChronoErreur, OSError) as exc:
            avis.append(f"CHRONO: avis {journal} — fin de fusion non écrite ({exc})")
    return avis


def _juges_et_cloture(base: str | os.PathLike[str], data: dict[str, Any], journal: str, now: int) -> list[str]:
    """`review-scope` abouti, au journal `journal` (la mère pour un lot) : un dev encore ouvert (d'un lot, ou
    à côté d'une fin déjà écrite) rend un avis et n'écrit RIEN — ni juges, ni clôture. Sinon `juges` si le
    cycle courant n'a AUCUNE clé `juges`, du plus grand `fin` des dev/fusion du cycle (des lots seuls s'il
    y en a ; fusion de tentative 1) à maintenant ; sans telle fin, rien
    d'inventé, un avis ; une fusion encore ouverte, un avis « chevauche ». Puis `cloture` ouverte (reprise
    si déjà ouverte). Sans cycle ouvert : rien."""
    courant = _cycle_courant(base, journal)
    if courant is None:
        return []
    n, c = courant
    avis: list[str] = []
    devs_ouverts = [e for e in c["etapes"].values() if e["etape"] == "dev" and "fin" not in e]
    fins_toutes = [e["fin"] for e in c["etapes"].values() if e["etape"] in ("dev", "fusion") and "fin" in e]
    if devs_ouverts and (fins_toutes or any(e["lot"] for e in devs_ouverts)):
        return [f"CHRONO: avis {journal} cycle {n} — dev encore ouvert ({len(devs_ouverts)}) : ni juges ni clôture relevés"]
    if not any(k[0] == "juges" for k in c["etapes"]):
        # Avec des lots, seules leurs fins comptent (la fusion de la passe de correction du parent n'avance
        # pas le début de juges) ; une fusion de tentative > 1 non plus.
        a_lots = any(e["lot"] for e in c["etapes"].values() if e["etape"] in ("dev", "fusion"))
        fins = [e["fin"] for e in c["etapes"].values() if e["etape"] in ("dev", "fusion") and "fin" in e
                and (e["lot"] or not a_lots) and (e["etape"] == "dev" or e["tentative"] == 1)]
        if not fins:
            avis.append(f"CHRONO: avis {journal} cycle {n} — juges non relevé : aucune fin de dev ni de fusion")
        else:
            debut = max(fins)
            etape(base, journal, "juges", "begin", taille=taille_de(data, journal), now_ms=debut)
            etape(base, journal, "juges", "end", now_ms=now)
            ouvertes = sorted("fusion" + (f" lot {e['lot'][-8:]}" if e["lot"] else "")
                              for e in c["etapes"].values() if e["etape"] == "fusion" and "fin" not in e)
            if ouvertes:
                avis.append(f"CHRONO: avis {journal} cycle {n} — juges relevés depuis la dernière fin, une "
                            f"fusion encore ouverte les chevauche : {', '.join(ouvertes)}")
    etape(base, journal, "cloture", "begin", taille=taille_de(data, journal), now_ms=now)
    return avis


def portes_du_journal(base: str | os.PathLike[str]) -> list[dict[str, Any]]:
    """Les lignes de `porte-chrono.tsv` (racine commune) : 5 OU 6 colonnes (la 6e, l'étape rouge), début
    ISO UTC en col. 1, durée en secondes (chiffres) col. 2, sha PLEIN col. 3, mode col. 4, rc col. 5 ; toute
    autre largeur, ou un champ hors forme, est ignorée. Fichier absent ou illisible : []."""
    ac = agent_chrono_module()
    try:
        lignes = (Path(base) / ac.PORTE_REL).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    out = []
    for ligne in lignes:
        champs = ligne.split("\t")
        if (len(champs) not in (5, 6) or not (champs[1].isascii() and champs[1].isdigit())
                or not SHA_PLEIN.fullmatch(champs[2])):
            continue
        debut = ac._iso_utc_ms(champs[0])
        if debut is None:
            continue
        out.append({"debut": debut, "duree_s": int(champs[1]), "sha": champs[2], "mode": champs[3].strip(),
                    "rc": champs[4].strip()})
    return out


def _fin_par_les_traces(traces: list[dict[str, Any]], depuis: int, now: int) -> int | None:
    """Le plus grand `at` (ISO UTC, à la seconde) des traces de revue dans [depuis, now] ; aucune : None."""
    iso = agent_chrono_module()._iso_utc_ms
    ats = [iso(t["at"]) for t in traces if isinstance(t, dict) and isinstance(t.get("at"), str)]
    dans = [a for a in ats if a is not None and depuis <= a <= now]
    return max(dans) if dans else None


def portes_a_mesurer(base: str | os.PathLike[str], data: dict[str, Any], verbe: str, tids: list[str],
                     traces: Callable[[str], dict[str, Any]], now_ms: int | None = None) -> list[dict[str, Any]]:
    """SANS git (sous le verrou du board), au `done` du PARENT ou d'une tâche seule — jamais d'un lot (C21) :
    la fin de clôture (fin au journal, sinon le plus grand `at` des traces de la tâche et de ses lots dans
    [début de cloture ou du cycle, maintenant]), les lignes frozen/frozen-linux de la porte dans [fin
    tronquée à la seconde, maintenant] (le début de porte est ISO à la seconde), les pointes `_pointe` de la tâche et de ses lots. Ni clé `cloture` ni trace du cycle :
    aucun candidat (silence) ; une clôture sans fin : un candidat sans ligne, qui porte son avis."""
    if verbe != "done":
        return []
    now = _maintenant_ms() if now_ms is None else int(now_ms)
    candidats: list[dict[str, Any]] = []
    for tid in tids:
        etat = next((t.get("state") for t in data.get("tasks", []) if t.get("id") == tid), None)
        if _parent_de(data, tid) or etat != "done":
            continue
        courant = _cycle_courant(base, tid)
        if courant is None:
            continue
        n, c = courant
        clotures = [e for e in c["etapes"].values() if e["etape"] == "cloture"]
        lots = _lots_de(data, tid)
        vues = [t for m in [tid, *lots] for t in (traces(m) or {}).values()]
        ouvertes = [e for e in clotures if "fin" not in e]
        if clotures and not ouvertes:
            fin, source = max(e["fin"] for e in clotures), "journal"
        else:
            depuis = max(e["debut"] for e in ouvertes) if ouvertes else c["debut"]
            fin, source = _fin_par_les_traces(vues, depuis, now), "trace"
        cand: dict[str, Any] = {"journal": tid, "cycle": n, "fin_cloture": fin, "source": source, "lignes": [],
                                "pointes": [], "avis": []}
        if fin is None:
            if clotures or vues:
                cand["avis"].append(f"CHRONO: avis {tid} cycle {n} — clôture sans fin relevée (ni fin au journal, "
                                    "ni trace de revue dans sa fenêtre) : ni porte ni correction")
                candidats.append(cand)
            continue
        borne = fin - fin % 1000  # le début de porte est ISO à la seconde : même seconde que la fin, admis
        cand["lignes"] = [l for l in portes_du_journal(base) if l["mode"] in MODES_PORTE_FIGES
                          and borne <= l["debut"] <= now]
        cand["pointes"] = [p[0] for p in (_pointe(data, m) for m in [tid, *lots]) if p is not None]
        candidats.append(cand)
    return candidats


def portes_premesurees(candidats: list[dict[str, Any]], git: Callable[..., str]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """HORS du verrou : une ligne de porte est RETENUE si son sha CONTIENT toutes les pointes relevées
    (`git rev-list -n 1 <sha>..<pointe>` vide) ; une panne git : un avis, la ligne exclue ; aucune pointe :
    lignes non filtrées, un avis ; des lignes toutes hors pointes : un avis. Aucune ligne : aucun git.
    Rend ({journal: candidat avec `retenues`}, avis)."""
    mesures: dict[str, dict[str, Any]] = {}
    avis: list[str] = []
    contient: dict[tuple[str, str], bool] = {}
    for cand in candidats:
        avis += cand.get("avis", [])
        retenues, pannes = [], []
        if cand["fin_cloture"] is None:
            continue
        if cand["lignes"] and not cand["pointes"]:
            retenues = list(cand["lignes"])
            avis.append(f"CHRONO: avis {cand['journal']} — porte non filtrée par sha : aucune pointe relevée "
                        f"({len(retenues)} ligne(s) comptée(s))")
        else:
            for ligne in cand["lignes"]:
                garde = True
                for pointe in cand["pointes"]:
                    cle = (ligne["sha"], pointe)
                    if cle not in contient:
                        try:
                            contient[cle] = git("rev-list", "-n", "1", f"{ligne['sha']}..{pointe}").strip() == ""
                        except Exception as exc:  # noqa: BLE001 — le chrono observe, il ne bloque jamais le verbe
                            pannes.append(f"{type(exc).__name__}: {exc}")
                            garde = False
                            break
                    if not contient[cle]:
                        garde = False
                        break
                if garde:
                    retenues.append(ligne)
            if pannes:
                avis.append(f"CHRONO: avis {cand['journal']} — porte non filtrée ({len(pannes)} ligne(s) exclue(s), "
                            f"git en panne) : {pannes[0]}")
            hors = len(cand["lignes"]) - len(retenues) - len(pannes)
            if cand["lignes"] and not retenues and hors > 0:
                avis.append(f"CHRONO: avis {cand['journal']} — porte non relevée : {hors} ligne(s) dans la "
                            "fenêtre, hors pointes")
        mesures[cand["journal"]] = dict(cand, retenues=retenues)
    return mesures, avis


def _queue_du_done(base: str | os.PathLike[str], tid: str, mesure: dict[str, Any], now: int) -> None:
    """Sous le verrou, AVANT le jalon : relu au journal, au même cycle courant — la fin de `cloture` (trace),
    une `porte` par ligne retenue si le cycle n'a AUCUNE clé `porte`, re-bornée à [fin de clôture
    tronquée à la seconde, maintenant], puis `correction` = [fin de clôture → 1re porte] si AUCUNE clé `correction`."""
    courant = _cycle_courant(base, tid)
    if courant is None or courant[0] != mesure["cycle"]:
        return
    n, c = courant
    fin = mesure["fin_cloture"]
    borne = fin - fin % 1000  # même borne que portes_a_mesurer : début de porte ISO tronqué à la seconde
    for cle, e in sorted(c["etapes"].items()):
        if cle[0] == "cloture" and "fin" not in e and e["debut"] <= fin:
            etape(base, tid, "cloture", "end", lot=cle[1] or None, tentative=cle[2], now_ms=fin)
    if not any(k[0] == "porte" for k in c["etapes"]):
        for i, ligne in enumerate(sorted(mesure["retenues"], key=lambda l: l["debut"]), start=1):
            if not borne <= ligne["debut"] <= now:
                continue
            etape(base, tid, "porte", "begin", tentative=i, now_ms=ligne["debut"])
            etape(base, tid, "porte", "end", tentative=i, now_ms=min(now, ligne["debut"] + ligne["duree_s"] * 1000))
    c = cycles(lire(base, tid))[n]
    portes = [e["debut"] for e in c["etapes"].values() if e["etape"] == "porte" and e["debut"] >= borne]
    if portes and not any(k[0] == "correction" for k in c["etapes"]):
        etape(base, tid, "correction", "begin", now_ms=fin)
        etape(base, tid, "correction", "end", now_ms=min(portes))


def jalons_du_verbe(base: str | os.PathLike[str], data: dict[str, Any], verbe: str, tids: list[str],
                    now_ms: int | None = None,
                    fusions: dict[tuple[str, int, str | None, int], int] | None = None,
                    portes: dict[str, dict[str, Any]] | None = None) -> list[str]:
    """Les jalons d'un verbe ABOUTI ; rend les avis (stderr). Une tâche qui a des lots n'ouvre JAMAIS de
    dev sans lot (C3) ; un lot joue au journal de son parent, sous sa clé ; le `done` d'un lot ne pose
    aucun jalon. `fusions` (de `fusions_premesurees`) : fins de fusion écrites AVANT les jalons du verbe,
    donc avant que le `done` de la mère ne dise ce qui reste sans fin ; `portes` (de `portes_premesurees`) :
    clôture, porte et correction écrites au `done`, AVANT le jalon ; `review-scope` relève `juges` et ouvre
    `cloture` au journal de chaque membre (la mère pour un lot), une fois par journal."""
    if verbe not in VERBES_JALONNES:
        raise ChronoErreur(f"verbe {verbe!r} hors {', '.join(VERBES_JALONNES)}")
    now = _maintenant_ms() if now_ms is None else int(now_ms)
    avis: list[str] = _fermer_fusions(base, fusions) if fusions else []
    if verbe == "review-scope":
        # Un parent clos (journal absent ou dernier cycle clos) n'a pas de cycle courant : rien d'écrit.
        journaux: list[str] = []
        for tid in tids:
            journal = _parent_de(data, tid) or tid
            if journal not in journaux:
                journaux.append(journal)
                avis += _juges_et_cloture(base, data, journal, now)
        return avis
    for tid in tids:
        parent = _parent_de(data, tid)
        if verbe in ("start", "fournee"):
            if parent:
                if not _parent_clos(base, data, parent):
                    _ouvrir_dev(base, data, parent, tid, now)
            elif _lots_de(data, tid):
                commencer(base, tid, now)
                for lot in _lots_de(data, tid, ("running",)):
                    _ouvrir_dev(base, data, tid, lot, now)
            else:
                _ouvrir_dev(base, data, tid, None, now)
        elif verbe == "retour":
            _retour(base, data, parent or tid, tid if parent else None, now)
        elif not parent:
            # Le board est relu APRÈS le verbe : une reprise intercalée (`fournee`, `start` après `reopen`)
            # a pu rendre la tâche active ; le jalon clôrait alors le cycle repris.
            etat = next((t.get("state") for t in data.get("tasks", []) if t.get("id") == tid), None)
            if etat == "done":
                if portes and tid in portes:
                    try:
                        _queue_du_done(base, tid, portes[tid], now)
                    except (ChronoErreur, OSError) as exc:
                        avis.append(f"CHRONO: avis {tid} — clôture, porte ou correction non écrite ({exc})")
                avis += _jalon_done(base, tid, now)
            else:
                avis.append(f"CHRONO: avis {tid} — reprise depuis le done, jalon non posé")
    return avis


# LES JALONS DE PLANIFICATION (T-01M5VZF47T9RT1YM9KC67HCQPP) : `/planning` ne jouait que `chrono begin`, la
# frise restait vide tout le tour. `plan_preflight.py` (avant chaque plan-critic) joue « plan-soumis » : ouvre
# `planification` ; `plan_pool.py check` READY joue « plan-pret » : ferme `planification`, ouvre `attente-pilote`,
# que `start`/`fournee` ferment au départ du dev (`_ouvrir_dev`). Idempotents, jamais bloquants : toute panne
# devient un avis texte, jamais une exception. Un LOT (`fournee.parent`) n'écrit rien : la planification se
# compte sur son maître, dont le préflight et le `check` READY suffisent. BORNES : `cadrage` n'est pas posé ;
# hors du verrou du board (ajouts O_APPEND, première ligne retenue à la lecture) ; une racine jetable
# (`racine_de_jalon` : `AGENTS_EVENTS_DIR` posé, ou sous le dossier temporaire) n'écrit rien.
JALONS_DE_PLANIFICATION = ("plan-soumis", "plan-pret")
RACINES_TEMPORAIRES = ("/tmp", "/private/tmp")


def racine_de_jalon(root: str | os.PathLike[str], env: dict[str, str] | None = None,
                    temporaires: tuple[str, ...] | None = None) -> Path | None:
    """La racine COMMUNE où un jalon de planification s'écrit, ou None pour une racine JETABLE : un
    `AGENTS_EVENTS_DIR` posé (bancs, sondes), ou `root` sous `/tmp`, `/private/tmp` ou le dossier temporaire du
    système (clone de mesure, fixture). Le contrôle précède tout git : une racine jetable n'en lance aucun."""
    env = os.environ if env is None else env
    if env.get("AGENTS_EVENTS_DIR"):
        return None
    if temporaires is None:
        import tempfile

        temporaires = RACINES_TEMPORAIRES + (tempfile.gettempdir(),)
    reel = Path(root).resolve()
    for t in temporaires:
        tr = Path(t).resolve()
        if reel == tr or tr in reel.parents:
            return None
    return racine(reel)


def _posterieure(c: dict[str, Any], nom: str) -> bool:
    """Une étape APRÈS `nom` dans l'ordre d'`ETAPES` (tout lot, toute tentative) existe dans le cycle."""
    rang = ETAPES.index(nom)
    return any(k[0] in ETAPES and ETAPES.index(k[0]) > rang for k in c["etapes"])


def _ouverte(c: dict[str, Any], nom: str) -> bool:
    return any("fin" not in c["etapes"][k] for k in _cles(c, nom, None))


def _jalon_de_planification(base: str | os.PathLike[str], data: dict[str, Any], tid: str, quoi: str,
                            now: int) -> list[str]:
    if quoi not in JALONS_DE_PLANIFICATION:
        raise ChronoErreur(f"jalon {quoi!r} hors {', '.join(JALONS_DE_PLANIFICATION)}")
    tache = next((t for t in data.get("tasks", []) if isinstance(t, dict) and t.get("id") == tid), None)
    if tache is None or _parent_de(data, tid):
        return []  # tâche hors du board ; lot : la planification se compte sur le maître
    if quoi == "plan-soumis":
        if tache.get("state") == "done":
            return []  # une tâche close n'ouvre pas de cycle fantôme ; `reopen` la rend pending
        n, _nouveau = commencer(base, tid, now)
        c = cycles(lire(base, tid))[n]
        if not _ouverte(c, "planification") and not _posterieure(c, "planification"):
            etape(base, tid, "planification", "begin", taille=taille_de(data, tid), now_ms=now)
        return []
    courant = _cycle_courant(base, tid)
    if courant is None:
        return []  # « plan-pret » n'ouvre jamais de cycle : sans cycle ouvert, rien
    n, c = courant
    if _posterieure(c, "attente-pilote"):
        return []  # déjà en dev (ou au-delà) : rien
    if _ouverte(c, "planification"):
        etape(base, tid, "planification", "end", now_ms=now)
    if not _cles(cycles(lire(base, tid))[n], "attente-pilote", None):
        etape(base, tid, "attente-pilote", "begin", now_ms=now)
    return []


def jalon_de_planification(base: str | os.PathLike[str], data: dict[str, Any], tid: str, quoi: str,
                           now_ms: int | None = None) -> list[str]:
    """« plan-soumis » : dans le cycle courant ouvert de `tid` (créé s'il manque, comme `commencer`), ouvre
    `planification` si aucune n'est ouverte ET qu'aucune étape postérieure n'existe. « plan-pret » : dans le
    cycle courant ouvert seulement, ferme `planification` si elle l'est, puis ouvre `attente-pilote` si le cycle
    n'en a aucune ; une étape postérieure à `attente-pilote` (dev…) : rien. Rend les AVIS (stderr de
    l'appelant) ; succès ou no-op : []. Jamais d'exception vers l'appelant."""
    try:
        return _jalon_de_planification(base, data, tid, quoi, _maintenant_ms() if now_ms is None else int(now_ms))
    except Exception as exc:  # noqa: BLE001 — le chrono observe, il ne bloque jamais l'appelant
        return [f"CHRONO: avis {tid} — jalon {quoi} non relevé ({type(exc).__name__}: {exc})"]


# LA LIGNE D'ÉTAT (`tasks.py --statusline`, étape 6, C2/C12) : ` · ⏱ <étape> <écoulé>/~<médiane figée>|?[ +N]`.
# Durées compactes, N plafonné (« 9 ou plus ») : le pire cas tient en SUFFIXE_MAX sans rien couper. Une
# lecture bornée de la FIN du journal de `root` tel quel, sans git : en worktree lié, le journal est à la
# racine commune, le suffixe y est donc absent (borne dite). Toute erreur rend '' : la ligne d'avant.
SUFFIXE_MAX = 36
LECTURE_MAX = 256 * 1024
AUTRES_MAX = 9


def duree_compacte(sec: int) -> str:
    """`Ns` (< 60 s), `Nm` (< 60 min), `HhMM` (< 100 h), `Nj` (3 chiffres au plus)."""
    sec = max(0, int(sec))
    if sec < 60:
        return f"{sec}s"
    if sec < 3600:
        return f"{sec // 60}m"
    if sec < 100 * 3600:
        return f"{sec // 3600}h{sec % 3600 // 60:02d}"
    return f"{min(999, sec // 86400)}j"


def suffixe(nom: str, ecoule_s: int, mediane_s: int | None, autres: int) -> str:
    med = f"~{duree_compacte(mediane_s)}" if mediane_s is not None else "?"
    n = min(AUTRES_MAX, max(0, autres))
    return f" · ⏱ {nom} {duree_compacte(ecoule_s)}/{med}" + (f" +{n}" if n else "")


def suffixe_statusline(root: str | os.PathLike[str], tid: str, lot: str | None = None,
                       now_ms: int | None = None) -> str:
    """L'étape ouverte la plus récente du cycle ouvert de `tid` (de `lot` seul s'il est donné), et le nombre
    des AUTRES étapes ouvertes ; '' sans étape ouverte ou sur toute erreur. Ne lève jamais."""
    try:
        brut = _lire_octets(chemin_journal(root, tid), LECTURE_MAX, fin=True)
        tous = cycles(_analyser(brut.decode("utf-8", errors="replace")))
        if not tous or est_clos(tous[max(tous)]):
            return ""
        ouvertes = [e for e in tous[max(tous)]["etapes"].values()
                    if "fin" not in e and e["etape"] not in JALONS and (lot is None or e["lot"] == lot)]
        if not ouvertes:
            return ""
        e = max(ouvertes, key=lambda e: (e["debut"], e["etape"], e["lot"] or "", e["tentative"]))
        now = _maintenant_ms() if now_ms is None else int(now_ms)
        # Le nom est de la liste FERMÉE : `_ligne_valide` a rejeté toute autre ligne à la lecture.
        return suffixe(e["etape"], (now - e["debut"]) // 1000, (e.get("estimation") or {}).get("mediane_s"),
                       len(ouvertes) - 1)
    except Exception:  # noqa: BLE001 — la ligne d'état ne lève jamais
        return ""
