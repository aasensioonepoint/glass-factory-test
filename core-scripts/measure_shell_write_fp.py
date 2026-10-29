#!/usr/bin/env python3
"""T-00000244 — MESURE des faux positifs/negatifs d'un garde d'ECRITURE SHELL.

Ce script INSTRUIT un arbitrage : « un garde qui refuse les ecritures shell
(`>`, `>>`, ...) vers une cible git-suivie OU protegee vaut-il son bruit ? ».
« Aucun garde » reste une issue legitime — le livrable est le CHIFFRE.

CE QU'IL FAIT, ET CE QU'IL NE FAIT PAS.
  * Il PORTE le predicat reel plutot que de le reimplementer : il importe
    ``git_tracked`` / ``normalize_path`` (``.codex/hooks/_common``) et
    ``protected_reason`` (``.codex/hooks/protect_paths``), donc la clause de
    refus mesuree ici est, au byte pres, celle que le garde retenu porterait.
  * Il REUTILISE les etages d'epuration de ``.codex/hooks/safe_bash`` (heredoc,
    scrub isometrique des segments cites, coupe grossiere) pour que le parseur de
    redirection voie exactement ce que le garde verrait.
  * Il N'ECRIT AUCUN garde et ne modifie aucun hook. Il lit des transcripts et
    compte.

LE CRITERE DE VERITE DE LA REVUE, pre-enregistre AVANT tout rejeu (etape 2) :
    « bash executerait-il cette ecriture sur la commande BRUTE ? »
  jamais « le texte epure la montre-t-il ». Un operateur `>` qui, sur la commande
  brute, ne redirige RIEN (il vit dans un corps de heredoc a delimiteur nu, dans
  un commentaire, dans une chaine que l'epuration n'a pas neutralisee) et que le
  garde refuserait quand meme est un FAUX POSITIF. Un `>` que bash execute
  reellement vers un fichier suivi est un VRAI positif — le refus voulu.

LE DENOMINATEUR ET SA COMPOSITION (etape 1). Un `tool_use` ``Bash`` est retenu
au denominateur SEULEMENT s'il est APPARIE a un ``tool_result`` dont ``is_error``
n'est pas ``True``. Les refus (``is_error=True``) et les non-apparies sont
comptes A PART, jamais fondus dans le taux. Les ids sont dedupliques (une reprise
de session recopie l'historique : le meme ``tool_use_id`` apparait dans
plusieurs fichiers).

CONFIDENTIALITE. Le corpus extrait (commandes brutes, pour revue) va sous
``--out-dir`` (defaut ``.agents/state/local/t244-corpus/``, NON SUIVI, supprime a
l'etape 8). Ce script n'imprime sur stdout que des COMPTES et des empreintes
sha256 tronquees — jamais le texte brut d'une commande. ``--corpus-dir`` est
OBLIGATOIRE et sans defaut : aucun chemin machine n'est code en dur ici.

LIMITES NOMMEES.
  * ``git_tracked`` / ``protected_reason`` sont evalues contre l'ARBRE COURANT de
    CE depot. Une commande d'une session ancienne visant un fichier depuis
    supprime/renomme se lira « non suivie » aujourd'hui : le biais va vers la
    SOUS-estimation des refus (conservateur), et il est nomme au rapport.
  * Un projet ADOPTANT protege ``.agents/bin/`` (suivi ET liste locale) ; non
    mesure ici, limite nommee au rapport.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Import du predicat REEL (jamais reimplemente) et des etages d'epuration.
# ---------------------------------------------------------------------------

def _load_predicate(repo_root: Path):
    """Importe ``_common``, ``protect_paths`` et ``safe_bash`` du cote Codex.

    C'est le port exige par le plan : la clause de refus mesuree est celle du
    garde canonique, pas une copie qui deriverait.
    """
    hooks = repo_root / ".codex" / "hooks"
    if str(hooks) not in sys.path:
        sys.path.insert(0, str(hooks))
    import _common  # noqa: E402
    import protect_paths  # noqa: E402
    import safe_bash  # noqa: E402
    return _common, protect_paths, safe_bash


# ---------------------------------------------------------------------------
# git_tracked RAPIDE — meme semantique que _common.git_tracked, sans un fork
# par cible. `git ls-files --error-unmatch -- P` reussit si P est un fichier
# suivi, ou un repertoire contenant au moins un fichier suivi. On precalcule
# l'ensemble une fois.
# ---------------------------------------------------------------------------

class TrackedSet:
    def __init__(self, tracked: set[str]):
        self.files = tracked
        # Prefixes de repertoire suivis, pour reproduire le cas `-- dir/`.
        self.dirs: set[str] = set()
        for f in tracked:
            parts = f.split("/")
            for k in range(1, len(parts)):
                self.dirs.add("/".join(parts[:k]))

    def tracked(self, path: str) -> bool:
        if not path:
            return False
        p = path.rstrip("/")
        return p in self.files or p in self.dirs


def build_tracked_set(repo_root: Path) -> TrackedSet:
    import subprocess
    out = subprocess.run(
        ["git", "ls-files"],
        cwd=repo_root, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, check=False,
    )
    tracked = {line.strip() for line in out.stdout.splitlines() if line.strip()}
    return TrackedSet(tracked)


# ---------------------------------------------------------------------------
# Le parseur de REDIRECTION (le motif 4 mesure). Il opere sur les segments
# EPURES de safe_bash — un `>` cite ou dans un corps de heredoc a delimiteur
# cite est deja neutralise, donc invisible ici, exactement comme pour le garde.
# ---------------------------------------------------------------------------

# Table de polarite (plan) :
#   JUGE   : >  >>  >|  &>  &>>  N>fichier  (2>err.log INCLUS)
#   PASSE  : >&N  N>&M (duplication de descripteur)  <
#   INVISIBLE => PASSE, compte : cible citee `> "x"`, cible a expansion `> $VAR`
_WORD_STOP = set(" \t;&|(){}<>`\n")
_BOUNDARY = set(" \t;&|(){}`\n")


def redirect_targets(command: str, safe_bash):
    """Rend la liste des cibles de redirection ECRITURE d'une commande.

    Chaque element : ``(raw_target, category)`` ou category vaut
    ``literal`` (cible litterale a juger), ``invisible-quoted``,
    ``invisible-expansion``, ``no-target``. Les formes de PASSE (duplication de
    descripteur, `<`) ne sont pas rendues.
    """
    analysable = safe_bash.strip_heredoc_bodies(command)
    found: list[tuple[str, str]] = []
    for raw_seg, scrubbed in safe_bash.coarse_segments(analysable):
        s, r = scrubbed, raw_seg
        n = len(s)
        i = 0
        while i < n:
            ch = s[i]
            if ch == "<":
                i += 1
                continue
            if ch != ">":
                i += 1
                continue
            # Second '>' d'un '>>' deja consomme par l'iteration precedente ?
            if i > 0 and s[i - 1] == ">":
                i += 1
                continue
            # Longueur de l'operateur : '>' ou '>>'
            if i + 1 < n and s[i + 1] == ">":
                op_end = i + 2
            else:
                op_end = i + 1
            # '>|' (contournement de noclobber)
            if op_end < n and s[op_end] == "|":
                op_end += 1
            # Peek : duplication de descripteur '>&' / 'N>&M' => PASSE
            t = op_end
            while t < n and s[t] in " \t":
                t += 1
            if t < n and s[t] == "&":
                i = op_end
                continue
            # Cible = prochain mot dans l'epure, lu dans le BRUT aux memes offsets
            te = t
            while te < n and s[te] not in _WORD_STOP:
                te += 1
            raw_target = r[t:te]
            if not raw_target:
                found.append(("", "no-target"))
            elif raw_target[:1] in ("'", '"'):
                found.append((raw_target, "invisible-quoted"))
            else:
                prefix = safe_bash.literal_prefix(raw_target)
                if not prefix.strip():
                    found.append((raw_target, "invisible-expansion"))
                else:
                    found.append((raw_target, "literal"))
            i = op_end
    return found


# ---------------------------------------------------------------------------
# Population candidate a HAUT RAPPEL pour les FAUX NEGATIFS — construite sur le
# corpus BRUT (avant epuration), toute ligne portant un verbe/idiome d'ecriture.
# La liste des verbes est CLOSE et publiee ; le RESIDU hors filtre est nomme au
# rapport, verbe par verbe.
# ---------------------------------------------------------------------------

# Idiomes/verbes du sur-ensemble (CLOS). Chaque motif porte un nom lisible.
_FN_PATTERNS = {
    "redirect-gt": re.compile(r">"),
    "sed-inplace": re.compile(r"\bsed\b[^\n|;&]*\s-i"),
    "perl-inplace": re.compile(r"\bperl\b[^\n|;&]*\s-i"),
    "tee": re.compile(r"\btee\b"),
    "dd-of": re.compile(r"\bdd\b[^\n|;&]*\bof="),
    "cp": re.compile(r"\bcp\b"),
    "mv": re.compile(r"\bmv\b"),
    "install": re.compile(r"\binstall\b\s+-"),
    "truncate": re.compile(r"\btruncate\b"),
    "tr-redirect": re.compile(r"\btruncate\b|\b:\s*>\s*"),
    "git-checkout-dd": re.compile(r"\bgit\s+checkout\s+--"),
    "git-restore": re.compile(r"\bgit\s+restore\b"),
    "awk-inplace": re.compile(r"\bawk\b[^\n|;&]*-i\s*inplace|\bgawk\b[^\n|;&]*-i\s*inplace"),
    "python-write": re.compile(r"\bpython[0-9.]*\b\s+-c\b"),
    "patch": re.compile(r"\bpatch\b\s"),
    "cat-heredoc": re.compile(r"\bcat\b[^\n]*<<"),
}


def fn_superset_hits(command: str) -> set[str]:
    hits = set()
    for name, pat in _FN_PATTERNS.items():
        if pat.search(command):
            hits.add(name)
    return hits


# --- Cibles d'ecriture NON-redirect, quand elles sont statiquement lisibles ---
# On extrait la cible de fichier des verbes a cible claire, pour compter combien
# d'ecritures NON-redirect atterrissent sur un fichier suivi/protege : ce sont
# les MANQUES d'un garde redirect-only (faux negatifs). Les ecritures OPAQUES
# (`python -c`, corps de heredoc a delimiteur nu) sont comptees a part : leur
# cible n'est pas etablissable statiquement — residu nomme.
_SEDI = re.compile(r"\bsed\b((?:\s+-\S+|\s+'[^']*'|\s+\"[^\"]*\")*)\s+(\S+)\s*$")


def nonredirect_write_targets(command: str, safe_bash):
    """Rend ``(parseable_targets, opaque)`` pour UNE commande.

    ``parseable_targets`` : liste de ``raw_target`` pour les verbes a cible
    claire (sed -i, tee, cp/mv dest, dd of=, truncate, patch). ``opaque`` : True
    si la commande porte un ecrivain opaque (python -c, heredoc a delim nu vers
    un `cat`/`tee`), dont la cible n'est pas etablissable ici.
    """
    targets: list[str] = []
    opaque = False
    for seg in re.split(r"[;&|\n]+", command):
        s = seg.strip()
        if not s:
            continue
        toks = s.split()
        low = [t.lower() for t in toks]
        # sed -i FILE / sed -i.bak ... FILE
        if "sed" in low:
            si = low.index("sed")
            rest = toks[si + 1:]
            if any(t.startswith("-i") for t in rest):
                nonopt = [t for t in rest if not t.startswith("-")]
                if nonopt:
                    targets.append(nonopt[-1])
        # tee [-a] FILE...
        if "tee" in low:
            ti = low.index("tee")
            for t in toks[ti + 1:]:
                if t.startswith("-"):
                    continue
                if t.startswith(("$", "`", '"', "'")):
                    continue
                targets.append(t)
        # cp/mv ... DEST   (dernier argument non-option)
        for verb in ("cp", "mv"):
            if verb in low:
                vi = low.index(verb)
                rest = [t for t in toks[vi + 1:] if not t.startswith("-")]
                if len(rest) >= 2:
                    targets.append(rest[-1])
        # dd of=FILE
        for t in toks:
            if t.startswith("of="):
                targets.append(t[3:])
        # truncate ... FILE
        if "truncate" in low:
            ti = low.index("truncate")
            nonopt = [t for t in toks[ti + 1:] if not t.startswith("-") and not t.isdigit()]
            for t in nonopt:
                targets.append(t)
        # patch FILE  (patch < diff  ou  patch FILE < diff)
        if low and low[0] == "patch":
            for t in toks[1:]:
                if not t.startswith("-"):
                    targets.append(t)
                    break
        # ecrivains OPAQUES
        if "python" in low[0:1] or (low and low[0].startswith("python")):
            if "-c" in low:
                opaque = True
        if low and low[0] in ("cat", "tee") and "<<" in s and "'" not in s and '"' not in s.split("<<", 1)[1][:6]:
            opaque = True
    # nettoie les cibles a expansion (non etablissables)
    clean = []
    for t in targets:
        t = t.strip("\"'")
        if safe_bash.literal_prefix(t).strip():
            clean.append(t)
        else:
            opaque = True
    return clean, opaque


# ---------------------------------------------------------------------------
# Lecture des transcripts, appariement, deduplication.
# ---------------------------------------------------------------------------

def iter_events(corpus_dirs: list[Path]):
    for d in corpus_dirs:
        for path in sorted(d.rglob("*.jsonl")):
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            yield json.loads(line)
                        except json.JSONDecodeError:
                            continue
            except OSError:
                continue


def collect_bash(corpus_dirs: list[Path]):
    """Rend ``(uses, results, is_error, ts_min, ts_max)``.

    ``uses``: id -> commande (dedupliquee). ``results``: id present si un
    tool_result existe. ``is_error``: id -> valeur is_error du result.
    """
    uses: dict[str, str] = {}
    is_error: dict[str, object] = {}
    ts_min = ts_max = None
    for o in iter_events(corpus_dirs):
        ts = o.get("timestamp")
        if isinstance(ts, str):
            if ts_min is None or ts < ts_min:
                ts_min = ts
            if ts_max is None or ts > ts_max:
                ts_max = ts
        msg = o.get("message")
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for b in content:
            if not isinstance(b, dict):
                continue
            bt = b.get("type")
            if bt == "tool_use" and b.get("name") == "Bash":
                cmd = (b.get("input") or {}).get("command", "")
                if b.get("id") and b["id"] not in uses:
                    uses[b["id"]] = cmd or ""
            elif bt == "tool_result":
                tid = b.get("tool_use_id")
                if tid and tid not in is_error:
                    is_error[tid] = b.get("is_error")
    return uses, is_error, ts_min, ts_max


def sha12(text: str) -> str:
    # T-00000785 : `surrogatepass`, comme safe_bash.command_fingerprint — un
    # surrogate isole dans une commande du corpus faisait planter la mesure ;
    # octets identiques a l'UTF-8 strict pour tout texte encodable.
    return hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Le rejeu et le compte.
# ---------------------------------------------------------------------------

def measure(corpus_dirs, repo_root, out_dir, protected_clause=True):
    _common, protect_paths, safe_bash = _load_predicate(repo_root)
    tracked = build_tracked_set(repo_root)

    def judge(raw_target):
        """Rend ``('git', None)`` / ``('protected', rule)`` / ``('pass', None)``.

        Reproduit le predicat du garde : refus ssi cible git-suivie OU protegee.
        Le prefixe litteral est normalise comme dans ``judge_targets``.
        """
        prefix = safe_bash.literal_prefix(raw_target)
        if not prefix.strip():
            return ("pass", None)
        candidate, resolved = _common.normalize_path_checked(prefix)
        if not candidate:
            return ("pass", None)
        if prefix.endswith(("/", "\\")) and not candidate.endswith("/"):
            candidate += "/"
        # T-00000785 (R3) : meme refus que safe_bash.judge_redirect sur un
        # candidat dont la RESOLUTION a echoue, quelle qu'en soit la cause (NUL,
        # surrogate isole, OSError), AVANT les deux clauses et sans condition
        # sur protected_clause (le garde le tient aussi en branche stricte) —
        # sinon « cannot drift » deviendrait faux. L'affichage du chemin cote
        # garde (main, passe de redirection, `cand = normalize_path(prefix)`)
        # ne leve plus depuis le correctif de normalize_path. Le refus de la
        # commande ENTIERE (regle unrepresentable-command de safe_bash.main)
        # n'est pas porte ici, pas plus que les regles rm/mv : cette mesure
        # compte le predicat de redirection seul.
        if not resolved:
            return ("protected", "unresolvable-path")
        if tracked.tracked(candidate):
            return ("git", None)
        if protected_clause:
            reason, rule = protect_paths.protected_reason(candidate)
            if reason:
                return ("protected", rule)
        return ("pass", None)

    uses, is_error, ts_min, ts_max = collect_bash(corpus_dirs)

    total_uses = len(uses)
    matched = [i for i in uses if i in is_error]
    executed = [i for i in matched if is_error[i] is not True]
    errored = [i for i in matched if is_error[i] is True]
    unmatched = [i for i in uses if i not in is_error]

    # Categories de redirection sur les EXECUTES.
    cat = Counter()
    exposed_ids = []          # au moins une cible litterale etablie
    refused_ids = []          # au moins une cible litterale jugee (git OU protege)
    refused_git_ids = []
    refused_protected_ids = []
    protected_by_prefix = Counter()   # ventilation de la clause protegee
    invisible_ids = []
    absolute_pass_ids = []    # cible etablie hors depot (> /tmp/x)

    # Enregistrement pour revue (BRUT, sous out-dir non suivi).
    refused_records = []
    invisible_records = []

    for i in executed:
        cmd = uses[i]
        targets = redirect_targets(cmd, safe_bash)
        if not targets:
            continue
        has_literal = False
        this_refused = False
        this_git = False
        this_protected = False
        this_prefixes = set()
        this_invisible = False
        this_absolute_pass = False
        target_notes = []
        for raw_target, category in targets:
            cat[category] += 1
            if category in ("invisible-quoted", "invisible-expansion"):
                this_invisible = True
                continue
            if category == "no-target":
                continue
            # category == literal
            verdict, rule = judge(raw_target)
            has_literal = True
            norm = _common.normalize_path(safe_bash.literal_prefix(raw_target))
            if verdict == "git":
                this_refused = True
                this_git = True
                target_notes.append(("git", norm))
            elif verdict == "protected":
                this_refused = True
                this_protected = True
                this_prefixes.add(rule)
                protected_by_prefix[rule] += 1
                target_notes.append(("protected:" + str(rule), norm))
            else:
                # pass : etabli mais ni suivi ni protege.
                if os.path.isabs(safe_bash.literal_prefix(raw_target).replace("\\", "/")) or \
                        raw_target.startswith("/"):
                    this_absolute_pass = True
                target_notes.append(("pass", norm))
        if has_literal:
            exposed_ids.append(i)
        if this_invisible:
            invisible_ids.append(i)
            invisible_records.append({"sha12": sha12(cmd), "len": len(cmd)})
        if this_absolute_pass:
            absolute_pass_ids.append(i)
        if this_refused:
            refused_ids.append(i)
            if this_git:
                refused_git_ids.append(i)
            if this_protected:
                refused_protected_ids.append(i)
            refused_records.append({
                "sha12": sha12(cmd),
                "len": len(cmd),
                "git": this_git,
                "protected_rules": sorted(this_prefixes),
                "notes": target_notes,
                "command": cmd,   # BRUT — pour revue, reste sous out-dir non suivi
            })

    # Population candidate faux-negatifs (sur le BRUT des executes).
    fn_hits = Counter()
    fn_ids = []
    fn_records = []
    for i in executed:
        cmd = uses[i]
        hits = fn_superset_hits(cmd)
        if hits:
            fn_ids.append(i)
            for h in hits:
                fn_hits[h] += 1
            # Verbes NON-redirect presents (ce qu'un garde redirect-only manque).
            non_redirect = hits - {"redirect-gt"}
            if non_redirect:
                fn_records.append({
                    "sha12": sha12(cmd), "len": len(cmd),
                    "verbs": sorted(non_redirect),
                    "command": cmd,
                })

    # --- RECALL : ecritures NON-redirect qui atterrissent sur un fichier
    # suivi/protege = les MANQUES d'un garde redirect-only. Plus les ecrivains
    # OPAQUES (cible non etablissable), comptes a part comme residu.
    nonredirect_hits = 0          # ecritures non-redirect -> cible suivie/protegee
    nonredirect_pass = 0          # ecritures non-redirect -> cible libre
    opaque_writers = 0            # python -c, heredoc nu : cible non etablissable
    nonredirect_hit_records = []
    for i in executed:
        cmd = uses[i]
        clean, opaque = nonredirect_write_targets(cmd, safe_bash)
        if opaque:
            opaque_writers += 1
        hit_here = False
        for tgt in clean:
            verdict, rule = judge(tgt)
            if verdict in ("git", "protected"):
                hit_here = True
        if hit_here:
            nonredirect_hits += 1
            nonredirect_hit_records.append({"sha12": sha12(cmd), "len": len(cmd),
                                            "command": cmd})
        elif clean:
            nonredirect_pass += 1

    # Fenetre temporelle -> semaines d'historique.
    weeks = None
    if ts_min and ts_max:
        try:
            a = datetime.fromisoformat(ts_min.replace("Z", "+00:00"))
            b = datetime.fromisoformat(ts_max.replace("Z", "+00:00"))
            days = (b - a).total_seconds() / 86400.0
            weeks = max(days / 7.0, 1e-9)
        except ValueError:
            weeks = None

    D = len(executed)
    result = {
        "corpus_dirs": [str(d) for d in corpus_dirs],
        "protected_clause": protected_clause,
        "denominator": {
            "unique_bash_tool_use": total_uses,
            "matched_to_result": len(matched),
            "executed_non_error": D,
            "errored_or_refused": len(errored),
            "unmatched": len(unmatched),
        },
        "timespan": {"min": ts_min, "max": ts_max, "weeks": weeks},
        "redirect_categories": dict(cat),
        "exposed_calls": len(exposed_ids),
        "invisible_calls": len(invisible_ids),
        "absolute_pass_calls": len(absolute_pass_ids),
        "refused": {
            "total": len(refused_ids),
            "git_clause": len(refused_git_ids),
            "protected_clause": len(refused_protected_ids),
            "protected_by_rule": dict(protected_by_prefix),
        },
        "fn_superset": {
            "total_candidates": len(fn_ids),
            "by_pattern": dict(fn_hits),
            "non_redirect_write_calls": len(fn_records),
        },
        "recall": {
            "redirect_writes_to_tracked_raw": len(refused_ids),
            "nonredirect_writes_to_tracked": nonredirect_hits,
            "nonredirect_writes_to_free": nonredirect_pass,
            "opaque_writers": opaque_writers,
        },
    }

    # Ecriture des corpus de revue sous out-dir (NON SUIVI).
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = "with-protected" if protected_clause else "no-protected"
    # T-00000785 : errors="backslashreplace" — ces corpus portent la commande
    # BRUTE, et un surrogate isole y faisait planter l'ecriture en UTF-8 strict.
    (out_dir / f"refused-{tag}.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in refused_records),
        encoding="utf-8", errors="backslashreplace",
    )
    (out_dir / f"fn-nonredirect-{tag}.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in fn_records),
        encoding="utf-8", errors="backslashreplace",
    )
    (out_dir / f"nonredirect-hits-{tag}.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in nonredirect_hit_records),
        encoding="utf-8", errors="backslashreplace",
    )
    (out_dir / f"summary-{tag}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return result


def _fmt_rate(num, den):
    if not den:
        return "n/a"
    return f"{num}/{den} = {100.0*num/den:.3f}%"


def print_report(result):
    d = result["denominator"]
    print("=== T-00000244 — MESURE ECRITURES SHELL NON GARDEES ===")
    print(f"corpus: {result['corpus_dirs']}")
    print(f"clause protegee active: {result['protected_clause']}")
    print("--- DENOMINATEUR (composition) ---")
    print(f"  unique Bash tool_use     : {d['unique_bash_tool_use']}")
    print(f"  apparies a un result     : {d['matched_to_result']}")
    print(f"  EXECUTES non-erreur (D)  : {d['executed_non_error']}")
    print(f"  erreur/refuses (a part)  : {d['errored_or_refused']}")
    print(f"  non-apparies (a part)    : {d['unmatched']}")
    ts = result["timespan"]
    print(f"  fenetre: {ts['min']} .. {ts['max']}  (~{ts['weeks']:.1f} semaines)" if ts["weeks"] else "  fenetre: n/a")
    print("--- FORMES DE REDIRECTION (sur executes) ---")
    for k, v in sorted(result["redirect_categories"].items()):
        print(f"  {k:22s}: {v}")
    print(f"  appels EXPOSES (>=1 cible litterale etablie): {result['exposed_calls']}")
    print(f"  appels INVISIBLES (cite/expansion, PASSE)   : {result['invisible_calls']}")
    print(f"  appels cible absolue hors depot (PASSE)     : {result['absolute_pass_calls']}")
    r = result["refused"]
    D = d["executed_non_error"]
    print("--- REFUS DU GARDE (positifs bruts, avant revue FP) ---")
    print(f"  total refuses            : {r['total']}")
    print(f"    dont clause git-suivie : {r['git_clause']}")
    print(f"    dont clause protegee   : {r['protected_clause']}")
    print(f"    protege ventile/regle  : {r['protected_by_rule']}")
    print("--- TROIS NOMBRES (positifs bruts ; FP = a soustraire apres revue) ---")
    print(f"  positifs / EXECUTES      : {_fmt_rate(r['total'], D)}")
    print(f"  positifs / EXPOSES       : {_fmt_rate(r['total'], result['exposed_calls'])}")
    if result["timespan"]["weeks"]:
        print(f"  positifs / SEMAINE       : {r['total']/result['timespan']['weeks']:.2f}")
    print("--- FAUX NEGATIFS : population candidate (haut rappel, BRUT) ---")
    fn = result["fn_superset"]
    print(f"  candidats total          : {fn['total_candidates']}")
    print(f"  par motif                : {fn['by_pattern']}")
    print(f"  ecritures NON-redirect   : {fn['non_redirect_write_calls']}  (ce qu'un garde redirect-only MANQUE)")
    rc = result["recall"]
    print("--- RECALL d'un garde REDIRECT-ONLY ---")
    print(f"  ecritures redirect -> suivi/protege (bruts, dont FP) : {rc['redirect_writes_to_tracked_raw']}")
    print(f"  ecritures NON-redirect -> suivi/protege (MANQUEES)   : {rc['nonredirect_writes_to_tracked']}")
    print(f"  ecritures NON-redirect -> cible libre                : {rc['nonredirect_writes_to_free']}")
    print(f"  ecrivains OPAQUES (python -c, heredoc nu) : {rc['opaque_writers']}  (cible non etablissable = residu)")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus-dir", nargs="+", required=True,
                    help="Repertoire(s) de transcripts JSONL. OBLIGATOIRE, sans defaut.")
    ap.add_argument("--out-dir", default=None,
                    help="Corpus extrait (non suivi). Defaut: .agents/state/local/t244-corpus/")
    ap.add_argument("--repo-root", default=None,
                    help="Racine du depot cible du predicat. Defaut: racine de ce script.")
    ap.add_argument("--no-protected-clause", action="store_true",
                    help="Mesure la forme SANS la clause chemins-proteges (pour compter son impact a part).")
    args = ap.parse_args(argv)

    repo_root = Path(args.repo_root).resolve() if args.repo_root else Path(__file__).resolve().parents[1]
    out_dir = Path(args.out_dir).resolve() if args.out_dir else (
        repo_root / ".agents" / "state" / "local" / "t244-corpus")
    corpus_dirs = [Path(c).resolve() for c in args.corpus_dir]
    for c in corpus_dirs:
        if not c.is_dir():
            ap.error(f"corpus dir introuvable: {c}")

    result = measure(corpus_dirs, repo_root, out_dir,
                     protected_clause=not args.no_protected_clause)
    print_report(result)
    print(f"\n[corpus de revue ecrit sous: {out_dir}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
