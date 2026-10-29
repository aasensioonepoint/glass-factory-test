#!/usr/bin/env python3
"""LE CHRONO RÉEL DES AGENTS — journal, durée, jetons estimés (T-01M55Z3ZCS34CDR2EQN1CEBHR7).

POURQUOI. Le chrono d'un tour de critique de plan (`chrono: planner=<durée>/<jetons>
plan-critic=<durée>/<jetons>`, S-01M534MZK4) se recopiait à la main ; mesuré sur ce dépôt, aucun
`agent.stop` du canal A ne portait ni aid, ni durée, ni jetons. Ce module tient le relevé :

- `.agents/state/local/agent-chrono.jsonl` (ignoré par git), UNE ligne JSON par événement :
  `{"ev": "start"|"stop", "aid", "agent", "ts": <epoch ms>, "duration_ms"?, "tokens"?}` —
  `duration_ms` et `tokens` sur un `stop` seul, et SEULEMENT quand ils sont connus : jamais un 0.
- le départ est écrit par le hook Claude SubagentStart (`agent-events.sh`), la fin par le hook
  SubagentStop (`log-agent-usage.sh`) ; les traceurs `binome-trace.sh` et `plan_trace.py` LISENT le
  départ sans rien écrire (trois hooks SubagentStop tournent en parallèle : un seul écrit le stop).
- durée = fin − DERNIER départ du même aid (une reprise repart de son propre départ) ; un stop
  déjà relevé après ce départ (reprise sans nouveau départ) ne donne AUCUNE durée — elle compterait
  l'attente (sonde : départ, stop à 60 s, stop à 690 s → 690 s écrits) ;
  jetons = usage du DERNIER tour d'assistant du transcript de l'agent (entrée + cache + sortie),
  jamais une somme par tour, qui recompterait le préfixe en cache. C'est une ESTIMATION : voir
  l'en-tête de `log-agent-usage.sh` pour l'écart mesuré et sa portée.

CE QU'IL NE FAIT PAS : il n'appelle aucun modèle, n'écrit que sous `.agents/state/local/`, et ne
LÈVE JAMAIS depuis ses fonctions de hook (`marquer_debut`, `chrono_de`, `noter_fin`) : un échec
de chrono ne doit jamais empêcher un hook. Ses appelants le chargent eux-mêmes sous `try`.

BORNES, DITES : le journal n'est pas tourné ; il est LU par sa queue (`QUEUE_JOURNAL` octets), donc
un aid plus ancien que cette fenêtre se lit inconnu. Un départ de plus de 7 jours ne donne pas de
durée. Un aid hors de la forme `AID_RE` n'écrit ni ne lit rien. Un stop sans agent_type prend le nom
du départ du même aid ; sans départ nommé, il n'est ni écrit ni relevé : mesuré le 2026-10-19 sur ce
dépôt, 155 stops sur 165 en une heure, sans départ ni transcript d'agent, à cadence fixe (~31 s) par
agent en cours, sans lien mesuré avec les appels Bash (agents internes de l'hôte, identité non
établie). L'ajout d'une ligne est un seul
`os.write` en `O_APPEND`, atomique entre processus sur POSIX, PAS sous Windows (CONVENTIONS_python) :
deux hooks concurrents peuvent y entrelacer une ligne, que la lecture ignore. Couverture : Claude Code seul
câble SubagentStart ; un rôle qui a tourné ailleurs (Codex) passe sa valeur mesurée,
`--chrono-aid ROLE=<durée>/<jetons>` (jamais 0), à côté de `--chrono-aid ROLE=<aid>`.

CLI : `python .agents/bin/agent_chrono.py show <aid>` imprime `<durée>/<jetons>` (`3m12s/216k`),
rc 1 si l'aid est inconnu, sans stop, sans durée ou sans jetons (cause sur stderr).
"""
from __future__ import annotations

import argparse
import calendar
import json
import os
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

JOURNAL_REL = Path(".agents") / "state" / "local" / "agent-chrono.jsonl"
PORTE_REL = Path(".agents") / "state" / "local" / "porte-chrono.tsv"
AID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
QUEUE_JOURNAL = 4 * 1024 * 1024
QUEUE_TRANSCRIPT = 8 * 1024 * 1024
DUREE_MAX_MS = 7 * 24 * 3600 * 1000
USAGE_CLES = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")
ROLES = ("planner", "plan-critic")
# Les défs admises par rôle : les tuples de `plan_trace.py` (les défs hors chaîne restent lisibles).
AGENTS_DU_ROLE = {"planner": ("planner", "planner-sonnet"),
                  "plan-critic": ("plan-critic", "plan-critic-sonnet-max")}
# La cause d'un aid résolu mais d'un autre rôle ; `specs.py` la lit pour donner SON remède.
MAUVAIS_ROLE = "passé sous le mauvais rôle"


class ChronoErreur(Exception):
    """Un aid que le journal ne résout pas ; le message NOMME l'aid et la cause."""


def _maintenant_ms() -> int:
    return int(time.time() * 1000)


def aid_de(payload: dict) -> str | None:
    """L'aid de la charge (`agent_id` ou `agentId`), seulement s'il a la forme `AID_RE`."""
    if not isinstance(payload, dict):
        return None
    brut = payload.get("agent_id") or payload.get("agentId")
    return brut if isinstance(brut, str) and AID_RE.match(brut) else None


def agent_de(payload: dict) -> str:
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("agent_type") or payload.get("agentType") or "").strip()


def _noter(root: str | os.PathLike[str], ligne: dict[str, Any]) -> bool:
    """Ajoute UNE ligne au journal en un seul `os.write` (`O_APPEND`) ; ne lève jamais. Un journal
    qui est un lien symbolique n'est pas suivi (`O_NOFOLLOW` là où l'OS l'a) : rien n'est écrit."""
    try:
        chemin = Path(root) / JOURNAL_REL
        chemin.parent.mkdir(parents=True, exist_ok=True)
        octets = (json.dumps(ligne, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
        drapeaux = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(str(chemin), drapeaux, 0o644)
        try:
            os.write(fd, octets)
        finally:
            os.close(fd)
        return True
    except Exception:
        return False


def _queue(chemin: Path, borne: int) -> list[str]:
    """Les lignes complètes des `borne` derniers octets (la première, coupée, est jetée)."""
    with open(chemin, "rb") as fh:
        fh.seek(0, os.SEEK_END)
        taille = fh.tell()
        fh.seek(max(0, taille - borne))
        brut = fh.read()
    lignes = brut.decode("utf-8", errors="replace").splitlines()
    return lignes[1:] if taille > borne else lignes


def lire_journal(root: str | os.PathLike[str], strict: bool = False) -> list[dict[str, Any]]:
    """Les lignes lisibles de la queue du journal, dans l'ordre ; absent → []. Illisible → [] pour
    un hook ; `strict` (la résolution d'un aid) → `ChronoErreur`, jamais lu « aid inconnu »."""
    try:
        lignes = _queue(Path(root) / JOURNAL_REL, QUEUE_JOURNAL)
    except FileNotFoundError:
        return []
    except OSError as exc:
        if strict:
            raise ChronoErreur(f"journal {JOURNAL_REL.as_posix()} illisible ({type(exc).__name__})") from exc
        return []
    out = []
    for ligne in lignes:
        try:
            obj = json.loads(ligne)
        except ValueError:
            continue
        if isinstance(obj, dict) and obj.get("ev") in ("start", "stop") and isinstance(obj.get("aid"), str):
            out.append(obj)
    return out


def marquer_debut(root: str | os.PathLike[str], payload: dict, now_ms: int | None = None) -> bool:
    """SubagentStart : une ligne `start` pour l'aid de la charge ; ne lève jamais."""
    try:
        aid = aid_de(payload)
        if aid is None:
            return False
        ligne = {"ev": "start", "aid": aid, "agent": agent_de(payload),
                 "ts": _maintenant_ms() if now_ms is None else int(now_ms)}
        return _noter(root, ligne)
    except Exception:
        return False


def _dernier(journal: list[dict[str, Any]], aid: str, ev: str) -> dict[str, Any] | None:
    for ligne in reversed(journal):
        if ligne.get("aid") == aid and ligne.get("ev") == ev:
            return ligne
    return None


def jetons_transcript(chemin: str | os.PathLike[str] | None) -> int | None:
    """Usage du DERNIER tour d'assistant du transcript (entrée + cache + sortie) ; inconnu → None."""
    if not chemin:
        return None
    try:
        lignes = _queue(Path(chemin), QUEUE_TRANSCRIPT)
    except OSError:
        return None
    for ligne in reversed(lignes):
        try:
            obj = json.loads(ligne)
        except ValueError:
            continue
        msg = obj.get("message") if isinstance(obj, dict) else None
        usage = msg.get("usage") if isinstance(msg, dict) else None
        if not isinstance(usage, dict) or (obj.get("type") or msg.get("role")) != "assistant":
            continue
        valeurs = [usage.get(k) for k in USAGE_CLES]
        if not all(v is None or (isinstance(v, int) and not isinstance(v, bool) and v >= 0) for v in valeurs):
            continue
        total = sum(v or 0 for v in valeurs)
        return total if total > 0 else None
    return None


def chrono_de(root: str | os.PathLike[str], payload: dict, now_ms: int | None = None) -> dict[str, Any]:
    """SubagentStop, LECTURE seule : `{"aid", "agent"}` + `duration_ms` si un départ du même aid
    est au journal (0 ≤ durée ≤ 7 j), + `tokens` si le transcript d'agent les donne. `agent` : celui
    de la charge, sinon celui du départ du même aid. Clés ABSENTES quand inconnues, jamais 0 ; aid
    absent ou hors forme → {} ; ne lève jamais. La règle de la reprise sans départ est dans
    `noter_fin` (l'écrivain seul) : un lecteur parallèle verrait le stop du même événement."""
    try:
        aid = aid_de(payload)
        if aid is None:
            return {}
        debut = _dernier(lire_journal(root), aid, "start")
        out: dict[str, Any] = {"aid": aid, "agent": agent_de(payload) or str((debut or {}).get("agent") or "").strip()}
        maintenant = _maintenant_ms() if now_ms is None else int(now_ms)
        ts = debut.get("ts") if debut else None
        if isinstance(ts, int) and 0 <= maintenant - ts <= DUREE_MAX_MS:
            out["duration_ms"] = maintenant - ts
        tokens = jetons_transcript(payload.get("agent_transcript_path") or payload.get("agentTranscriptPath"))
        if tokens:
            out["tokens"] = tokens
        return out
    except Exception:
        return {}


def noter_fin(root: str | os.PathLike[str], chrono: dict[str, Any], now_ms: int | None = None) -> bool:
    """Une ligne `stop` depuis `chrono_de` ; rien sans aid ni sans agent (ni à la charge ni au
    départ : agent interne de l'hôte, la règle `if agent` du canal A et de RUN_LOG) ; sans durée
    quand un stop du même aid est déjà relevé depuis son dernier départ ; ne lève jamais."""
    try:
        if not chrono.get("aid") or not str(chrono.get("agent") or "").strip():
            return False
        ligne = {"ev": "stop", "aid": chrono["aid"], "agent": chrono.get("agent") or "",
                 "ts": _maintenant_ms() if now_ms is None else int(now_ms)}
        for cle in ("duration_ms", "tokens"):
            if isinstance(chrono.get(cle), int):
                ligne[cle] = chrono[cle]
        if "duration_ms" in ligne:  # reprise sans nouveau départ : la durée compterait l'attente
            journal = lire_journal(root)
            d, p = _dernier(journal, chrono["aid"], "start"), _dernier(journal, chrono["aid"], "stop")
            if d and p and isinstance(d.get("ts"), int) and isinstance(p.get("ts"), int) and p["ts"] >= d["ts"]:
                del ligne["duration_ms"]
        return _noter(root, ligne)
    except Exception:
        return False


def fmt_duree(sec: int) -> str:
    """MÊME forme que `specs.fmt_duree` (`3m12s`, `45s`, `1h02m03s`), relue par `specs.parse_duree`."""
    h, r = divmod(int(sec), 3600)
    m, s = divmod(r, 60)
    return f"{h}h{m:02d}m{s:02d}s" if h else (f"{m}m{s:02d}s" if m else f"{s}s")


def fmt_jetons(n: int) -> str:
    """`216k`, `216.4k`, `1.2M`, `850` — relue par `specs.parse_jetons`."""
    if n < 1000:
        return str(n)
    valeur, suffixe = (n / 1_000_000, "M") if n >= 1_000_000 else (n / 1000, "k")
    texte = f"{valeur:.1f}"
    return (texte[:-2] if texte.endswith(".0") else texte) + suffixe


def resoudre(root: str | os.PathLike[str], aid: str, role: str | None = None) -> tuple[int, int]:
    """(secondes, jetons) du DERNIER stop de l'aid ; sinon `ChronoErreur` nommant l'aid et la cause."""
    if not isinstance(aid, str) or not AID_RE.match(aid):
        raise ChronoErreur(f"aid {aid!r} hors forme (lettres, chiffres, `_`, `-`, 64 au plus)")
    try:
        journal = lire_journal(root, strict=True)
    except ChronoErreur as exc:
        raise ChronoErreur(f"aid {aid} non résolu : {exc}") from exc
    stop = _dernier(journal, aid, "stop")
    if stop is None:
        cause = "sans stop (départ vu, fin jamais relevée)" if _dernier(journal, aid, "start") else "inconnu du journal"
        raise ChronoErreur(f"aid {aid} {cause}")
    if role is not None and stop.get("agent") not in AGENTS_DU_ROLE.get(role, ()):
        raise ChronoErreur(f"aid {aid} {MAUVAIS_ROLE} : un `{stop.get('agent') or '?'}`, pas un {role}")
    duree, jetons = stop.get("duration_ms"), stop.get("tokens")
    if not isinstance(duree, int):
        raise ChronoErreur(f"aid {aid} sans durée (aucun départ relevé avant sa fin, ou reprise sans nouveau départ)")
    if not isinstance(jetons, int) or jetons <= 0:
        raise ChronoErreur(f"aid {aid} sans jetons (transcript d'agent illisible ou vide)")
    return max(1, round(duree / 1000)), jetons


def paires_chrono(valeurs: list[str], lire_valeur=None) -> dict[str, str | tuple[int, int]]:
    """`["planner=<aid>", "plan-critic=<durée>/<jetons>"]` → {rôle: aid ou (secondes, jetons)} ; les
    DEUX rôles, une fois chacun. Une valeur à la forme `AID_RE` est un aid ; sinon c'est la valeur
    MESURÉE d'un rôle routé hors Claude Code, lue par `lire_valeur` (`specs`), jamais 0 ; sinon
    `ValueError` qui dit la forme attendue."""
    forme = ("`--chrono-aid planner=<aid> --chrono-aid plan-critic=<aid>` ; un rôle routé hors Claude "
             "Code : `ROLE=<durée>/<jetons>` mesurés, jamais 0, ou `--sans-chrono`")
    out: dict[str, str | tuple[int, int]] = {}
    for brut in valeurs:
        role, sep, aid = (brut or "").partition("=")
        role, aid = role.strip(), aid.strip()
        if not sep or role not in ROLES or not aid:
            raise ValueError(f"--chrono-aid {brut!r} illisible ; forme attendue {forme}")
        if role in out:
            raise ValueError(f"--chrono-aid {role}= donné deux fois ; forme attendue {forme}")
        if AID_RE.match(aid):
            out[role] = aid
            continue
        lu = lire_valeur(aid) if lire_valeur else None
        if not lu or lu[0] <= 0 or lu[1] <= 0:
            raise ValueError(f"--chrono-aid {brut!r} : ni un aid, ni une valeur <durée>/<jetons> lisible et "
                             f"non nulle ; forme attendue {forme}")
        out[role] = lu
    if set(out) != set(ROLES):
        manque = ", ".join(r for r in ROLES if r not in out)
        raise ValueError(f"--chrono-aid sans {manque}= ; le champ exige les deux rôles : {forme}")
    return out


def champ_chrono(root: str | os.PathLike[str], paires: dict[str, str | tuple[int, int]]) -> tuple[str | None, list[str]]:
    """Le champ `chrono: planner=<d>/<j> plan-critic=<d>/<j>` depuis le journal (un aid) ou la valeur
    saisie (un couple de `paires_chrono`), ou (None, causes) dès qu'un aid ne se résout pas — jamais
    un champ partiel, jamais `0s/0`."""
    morceaux, causes = [], []
    for role in ROLES:
        try:
            valeur = paires[role]
            sec, jetons = valeur if isinstance(valeur, tuple) else resoudre(root, valeur, role)
            morceaux.append(f"{role}={fmt_duree(sec)}/{fmt_jetons(jetons)}")
        except ChronoErreur as exc:
            causes.append(f"{role} : {exc}")
    return (None, causes) if causes else ("chrono: " + " ".join(morceaux), [])


def _mediane_p90(valeurs: list[int]) -> tuple[int, int]:
    tri = sorted(valeurs)
    return int(round(statistics.median(tri))), tri[max(0, -(-9 * len(tri) // 10) - 1)]


def _git(root: str | os.PathLike[str], *args: str) -> str:
    p = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=5, check=False)
    return p.stdout.strip() if p.returncode == 0 else ""


def racine_commune(root: str | os.PathLike[str]) -> Path:
    """La racine où la porte écrit `porte-chrono.tsv` : LA MÊME RÈGLE que l'écrivain
    `core-scripts/verify.sh` (bloc CHRONO_ROOT) — git-dir == common-dir → `--show-toplevel` (dépôt,
    sous-module, `--separate-git-dir`) ; sinon (worktree lié) `core.worktree` du common-dir s'il est
    posé (worktree lié d'un sous-module), sinon le parent d'un common-dir nommé `.git` ; sinon son
    propre `--show-toplevel` : git n'enregistre pas le worktree principal d'un `--separate-git-dir`
    ni d'un dépôt nu (mesuré, `git worktree list` y nomme le répertoire git). Hors git → `root`."""
    try:
        commun = _git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
        if commun:
            commun_p = Path(commun).resolve()
            git_dir = _git(root, "rev-parse", "--absolute-git-dir")
            if not (git_dir and Path(git_dir).resolve() == commun_p):
                arbre = _git(root, "config", "--file", str(commun_p / "config"), "--get", "core.worktree")
                if arbre:
                    return (commun_p / arbre).resolve()
                if commun_p.name == ".git":
                    return commun_p.parent
            haut = _git(root, "rev-parse", "--show-toplevel")
            if haut:
                return Path(haut)
    except Exception:
        pass
    return Path(root)


def _iso_utc_ms(iso: str) -> int | None:
    """L'instant (epoch ms) d'un début de porte `AAAA-MM-JJTHH:MM:SSZ` (UTC) ; illisible → None."""
    try:
        return calendar.timegm(time.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S")) * 1000
    except ValueError:
        return None


def releve_etapes(root: str | os.PathLike[str], depuis: str | None = None) -> dict[str, Any]:
    """Durées par agent (stops du journal) et par porte (`porte-chrono.tsv` de la racine commune :
    `<début ISO>\\t<durée s>\\t<sha>\\t<mode>\\t<rc>[\\t<étape rouge>]`, 5 ou 6 colonnes ; les
    rouges comptées par étape, « non noté » pour une ligne à 5), la médiane des portes PAR MODE (`live`,
    `frozen`, `frozen-linux` ne se mélangent pas). Une étape sans mesure n'a pas de médiane.
    `depuis` est un jour LOCAL, comme la `date` des entrées SPECS (`date.today()` de `specs.py`, que
    d'autres lecteurs relisent) : UN seuil, minuit local, pour les trois sources ; le début ISO UTC
    d'une porte est comparé à ce même instant."""
    seuil = None
    if depuis:
        seuil = int(time.mktime(time.strptime(depuis, "%Y-%m-%d")) * 1000)
    par_agent: dict[str, dict[str, list[int]]] = {}
    for ligne in lire_journal(root):
        if ligne.get("ev") != "stop" or (seuil is not None and not (isinstance(ligne.get("ts"), int) and ligne["ts"] >= seuil)):
            continue
        nom = str(ligne.get("agent") or "").strip()
        if not nom:  # stop sans agent_type, écrit avant le filtre de `noter_fin`
            continue
        a = par_agent.setdefault(nom, {"durees": [], "jetons": [], "stops": []})
        a["stops"].append(1)
        if isinstance(ligne.get("duration_ms"), int):
            a["durees"].append(max(0, round(ligne["duration_ms"] / 1000)))
        if isinstance(ligne.get("tokens"), int):
            a["jetons"].append(ligne["tokens"])
    agents: dict[str, dict[str, Any]] = {}
    for nom, a in sorted(par_agent.items()):
        fiche: dict[str, Any] = {"stops": len(a["stops"]), "mesures": len(a["durees"])}
        if a["durees"]:
            fiche["duree_mediane"], fiche["duree_p90"] = _mediane_p90(a["durees"])
        if a["jetons"]:
            fiche["jetons_mediane"] = _mediane_p90(a["jetons"])[0]
        agents[nom] = fiche
    try:
        lignes = (racine_commune(root) / PORTE_REL).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        lignes = []
    par_mode: dict[str, dict[str, Any]] = {}
    par_etape: dict[str, int] = {}
    for ligne in lignes:
        champs = ligne.split("\t")
        # 5 colonnes (journal d'avant T-01M5PVWF7H) ou 6 (+ étape rouge : `-` au vert,
        # le premier libellé rouge, `?` quand verify.sh n'a rien pu noter).
        if len(champs) not in (5, 6) or not champs[1].isdigit():
            continue
        if seuil is not None and (_iso_utc_ms(champs[0]) or -1) < seuil:
            continue
        m = par_mode.setdefault(champs[3].strip() or "?", {"vertes": [], "rouges": 0})
        if champs[4].strip() == "0":
            m["vertes"].append(int(champs[1]))
        else:
            m["rouges"] += 1
            etape = champs[5].strip() if len(champs) == 6 else ""
            cle = etape or "non noté"
            par_etape[cle] = par_etape.get(cle, 0) + 1
    modes: dict[str, dict[str, Any]] = {}
    for nom, m in sorted(par_mode.items()):
        fiche = {"vertes": len(m["vertes"]), "rouges": m["rouges"]}
        if m["vertes"]:
            fiche["duree_mediane"], fiche["duree_p90"] = _mediane_p90(m["vertes"])
        modes[nom] = fiche
    portes = {"vertes": sum(f["vertes"] for f in modes.values()),
              "rouges": sum(f["rouges"] for f in modes.values()), "modes": modes,
              "rouges_par_etape": dict(sorted(par_etape.items()))}
    return {"agents": agents, "portes": portes}


def render_etapes(releve: dict[str, Any]) -> str:
    lignes = ["durées par agent (journal agent-chrono.jsonl, stops relevés)",
              f"{'agent':<28} {'stops':>5} {'mesurés':>7} {'médiane':>10} {'p90':>10} {'jetons':>8}"]
    for nom, f in releve["agents"].items():
        med = fmt_duree(f["duree_mediane"]) if "duree_mediane" in f else "-"
        p90 = fmt_duree(f["duree_p90"]) if "duree_p90" in f else "-"
        jet = fmt_jetons(f["jetons_mediane"]) if "jetons_mediane" in f else "-"
        lignes.append(f"{nom[:28]:<28} {f['stops']:>5} {f['mesures']:>7} {med:>10} {p90:>10} {jet:>8}")
    if not releve["agents"]:
        lignes.append("aucun stop relevé au journal")
    p = releve["portes"]
    lignes.append(f"portes (porte-chrono.tsv) : {p['vertes']} vertes, {p['rouges']} rouges")
    for nom, m in p["modes"].items():
        bilan = f"  {nom} : {m['vertes']} vertes, {m['rouges']} rouges"
        if m["vertes"]:
            bilan += f" ; durée médiane {fmt_duree(m['duree_mediane'])}, p90 {fmt_duree(m['duree_p90'])}"
        lignes.append(bilan)
    par_etape = p.get("rouges_par_etape") or {}
    if par_etape:
        lignes.append("rouges par étape (6e colonne ; « non noté » : ligne à 5 colonnes) : "
                      + ", ".join(f"{nom} {n}" for nom, n in par_etape.items()))
    return "\n".join(lignes)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Chrono réel des agents : relevé d'un aid.")
    ap.add_argument("--root", default=os.environ.get("CLAUDE_PROJECT_DIR", "."))
    sub = ap.add_subparsers(dest="cmd")
    p_show = sub.add_parser("show", help="imprime <durée>/<jetons> du dernier stop de l'aid")
    p_show.add_argument("aid")
    args = ap.parse_args(argv)
    if args.cmd != "show":
        ap.print_help()
        return 2
    try:
        sec, jetons = resoudre(args.root, args.aid)
    except ChronoErreur as exc:
        print(f"agent_chrono: {exc}", file=sys.stderr)
        return 1
    print(f"{fmt_duree(sec)}/{fmt_jetons(jetons)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
