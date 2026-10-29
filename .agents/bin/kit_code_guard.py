#!/usr/bin/env python3
"""kit_code_guard — le CODE DU KIT armable, octroi pilote-seul (T-00000763 A).

CE QUE ÇA FAIT. Quand le pilote pose `.agents/state/gates/KIT_CODE_PROTEGE`,
toute écriture Edit/Write vers l'ENSEMBLE kit-code ci-dessous est refusée, sauf
si une ligne VALIDE de `.agents/state/gates/KIT_CODE_AUTORISE` l'octroie :

    <chemin|préfixe/> T-<8 chiffres ou ULID> <AAAA-MM-JJTHH:MMZ>

— UTC, un chemin ou un préfixe (terminé par `/`) DANS l'ensemble, un ticket, une
échéance. Une ligne malformée, échue ou hors ensemble est IGNORÉE et COMPTÉE
dans le refus, avec sa cause : un octroi qui ne mord pas en silence se lit
« accordé ». Un fichier d'octroi présent mais illisible est un refus.

QUI L'APPELLE. Les deux gardes de chemin, SEULEMENT si le marqueur existe :
`protect-paths.sh` (Claude) par la CLI ci-dessous, les jumeaux
`protect_paths.py` par chargement PARESSEUX, par CHEMIN EXPLICITE. Toujours
APRÈS les règles absolues : un octroi n'ouvre jamais un `.env`, un credential,
un marqueur ou un interne git — il ne lève que CE refus-ci.

LIVRÉ DÉSARMÉ. Aucun marqueur n'est posé par le kit ; l'armer révoque
S-00000059 (« le kit se maintient lui-même »), donc c'est un geste pilote.

CLI : `kit_code_guard.py --root R -- c1 [c2 …]` — les candidats sont
l'ENSEMBLE des formes canoniques d'UN chemin que l'appelant a calculé (point
fixe, T-00000722). La garde le REFERME elle-même (`canonical_forms`, même point
fixe, borne 5 tours, refus `formes-instables` au-delà), puis chaque forme est
RÉSOLUE ici même (`os.path.realpath` : `.`, `..`, liens) et normalisée avant le
test de préfixe ; les octrois sont comparés à ces formes : la garde ne dépend
pas du zèle de son appelant. Sortie 0 : rien à dire ; 3 : octroi (stdout = la
ligne) ; 2 : refus (stderr = la raison).

stdlib seule.
"""
from __future__ import annotations

import argparse
import os
import posixpath
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# L'ENSEMBLE FERMÉ (plan T-00000721, « Définitions »). EXCLUS, et c'est écrit :
# `agentic_v3/`, `src/cadre/`, leur emplacement neuf `.agents/vendor/`, `.agents/evals/`,
# le reste de `core-scripts/`, `.github/workflows/`.
KIT_CODE_PREFIXES = (
    ".claude/hooks/",
    ".codex/hooks/",
    ".gemini/hooks/",
    ".agents/bin/",
    ".agents/security/",
    ".githooks/",
    ".github/hooks/",
)

KIT_CODE_FILES = (
    ".agents/pyrun.sh",
    ".agents/pyrun.ps1",
    ".claude/statusline.sh",
    ".claude/settings.json",
    ".codex/hooks.json",
    ".agents/hooks.json",
    ".kimi-code/hooks.json",
    "core-scripts/verify.sh",
    ".agents/protected-paths.local",
)

ARMING_REL = ".agents/state/gates/KIT_CODE_PROTEGE"
GRANT_REL = ".agents/state/gates/KIT_CODE_AUTORISE"

# Ticket d'un octroi : `T-<ULID>` (T-00000726, ULID EN PREMIER) ou l'ancien
# `T-<8 chiffres>`, ancré aux DEUX bouts (`\Z`, jamais `$` qui laisse passer un
# `\n` final). RECOPIÉ, jamais importé ; témoins : test_kit_code_guard.py.
_TICKET = re.compile(r"\AT-(?:[0-9A-HJKMNP-TV-Z]{26}|\d{8})\Z")
_DRIVE = re.compile(r"^([A-Za-z]):/(.*)$")
_MSYS = re.compile(r"^/([A-Za-z])/(.*)$")


def nt_fold(p: str, dots: bool = False) -> str:
    """Le pli NTFS du plan, même corps que `_nt_fold` des jumeaux : minuscule,
    `\\` → `/`, flux ADS coupé au 1er `:` par segment (lecteur de tête gardé),
    point/espace finaux retirés par segment. `dots` : la lecture « points » d'un
    segment fait seulement de points et d'espaces (`..` pour au moins deux
    points, `.` pour un) au lieu de le vider — les deux lectures sont jugées."""
    segs = p.lower().replace(chr(92), "/").split("/")
    out = []
    for i, s in enumerate(segs):
        head = ""
        if i == 0 and len(s) >= 2 and s[1] == ":" and s[0].isalpha():
            head, s = s[:2], s[2:]
        s = s.split(":", 1)[0]
        if dots and "." in s and not s.strip(". "):
            s = ".." if s.count(".") >= 2 else "."
        elif s not in (".", ".."):
            s = s.rstrip(". ")
        out.append(head + s)
    return "/".join(out)


def armed(root: str | os.PathLike) -> bool:
    """Le marqueur est-il posé ?"""
    return (Path(root) / ARMING_REL).is_file()


def _root_spellings(root: str | os.PathLike) -> list:
    """La racine sous toutes les orthographes qu'un chemin absolu peut porter :
    telle quelle, résolue (macOS `/var` → `/private/var`), `c:/x` ↔ `/c/x`
    (Git Bash) avec la lettre dans SES DEUX CASSES — `realpath` rend `C:/…`
    quand cygpath donne `/c/…` (binôme de clôture sur ae45e199, F2 : une seule
    casse ici, deux dans les gardes de chemin) —, et chacune minusculisée et
    repliée NT. Les plus longues d'abord."""
    base = str(root).replace("\\", "/").rstrip("/")
    forms = {base}
    try:
        forms.add(os.path.realpath(base).replace("\\", "/").rstrip("/"))
    except (OSError, ValueError):
        pass
    for f in list(forms):
        m = _DRIVE.match(f + "/")
        if m:
            for lettre in (m.group(1).lower(), m.group(1).upper()):
                forms.add(f"/{lettre}/{m.group(2)}".rstrip("/"))
        m = _MSYS.match(f + "/")
        if m:
            for lettre in (m.group(1).lower(), m.group(1).upper()):
                forms.add(f"{lettre}:/{m.group(2)}".rstrip("/"))
    out = set()
    for f in forms:
        if f:
            out.update((f, f.lower(), nt_fold(f)))
    return sorted(out, key=len, reverse=True)


def _is_absolute(c: str) -> bool:
    return c.startswith("/") or _DRIVE.match(c) is not None


def _normpath(c: str) -> str:
    """Segments `.` et `..` résolus textuellement. Les jumeaux Python reçoivent un
    chemin déjà résolu (`_common.normalize_path`) ; Claude passe le chemin brut, et
    `a/../.claude/hooks/x.sh` ou `.claude/./hooks/x.sh` échappaient au test de
    PRÉFIXE de l'ensemble (mesuré : rc 0 sur Claude, refus sur les jumeaux)."""
    n = posixpath.normpath(c) if c else c
    return "" if n == "." else n


def _resolve(c: str, root: str) -> str:
    """Le candidat RÉSOLU par `os.path.realpath` — `.`, `..` ET liens
    symboliques, segment terminal inexistant toléré — joint à la racine s'il est
    relatif (revue de sécurité du lot T-00000721, finding 2, class 1). Sur le
    texte brut, un lien `lnk -> .claude/hooks` faisait passer `lnk/x.sh` (rc 0)
    quand `.claude/hooks/x.sh` était refusé. Résolution PHYSIQUE, comme
    `Path.resolve` des jumeaux : un `..` après un lien remonte depuis la CIBLE du
    lien. Un chemin à lettre de lecteur lu hors Windows n'a rien à résoudre ici :
    il est seulement normalisé textuellement."""
    if _DRIVE.match(c) and os.name != "nt":
        return _normpath(c)
    base = c if os.path.isabs(c) else os.path.join(root, c)
    try:
        return os.path.realpath(base).replace("\\", "/")
    except (OSError, ValueError):
        return _normpath(base)


def _lexical(c: str, root: str) -> str:
    """Le candidat normalisé LEXICALEMENT (`posixpath.normpath`), joint à la
    racine s'il est relatif, sans toucher aux liens : c'est la lecture Win32, où
    `lnk/../x` vaut `x` quel que soit `lnk`."""
    if _DRIVE.match(c) or os.path.isabs(c):
        return _normpath(c)
    return _normpath(posixpath.join(root.replace("\\", "/"), c))


def _forms(candidate: str, root: str) -> list:
    """LES DEUX FORMES d'un candidat, PHYSIQUE (`_resolve`) et LEXICALE
    (`_lexical`), sans doublon (exec-critic, constat 2). Elles divergent quand un
    `..` suit un lien : `lnksub/../.claude/hooks/x.sh` (lnksub → docs/sub) vaut
    `docs/.claude/hooks/x.sh` physiquement et `.claude/hooks/x.sh`
    lexicalement. À 604db568, la forme physique avait REMPLACÉ la lexicale et ce
    chemin, refusé à 6503c35b, passait — un refus qui disparaissait, contre
    « union de refus » du plan."""
    c = candidate.replace("\\", "/")
    out = []
    for form in (_resolve(c, root), _lexical(c, root)):
        if form not in out:
            out.append(form)
    return out


# LE POINT FIXE DES FORMES CANONIQUES (T-00000722 ; revue du lot T-00000721,
# HIGH « pli avant résolution »). Les orthographes reçues ne formaient pas une
# liste CLOSE : une forme PLIÉE pouvait encore porter un lien que rien n'avait
# résolu — `z/.../lnkhooks/x.sh` (lnkhooks -> .claude/hooks) passait sur les
# jumeaux Python (mesuré, rc 0), qui n'envoyaient ici que brute, minuscule et
# pli rogné. La garde referme donc l'ensemble reçu elle-même.
FORMES_BORNE = 5
FORMES_INSTABLES = "formes-instables"


def _physique(c: str, root: str, spellings: list) -> str:
    """La résolution PHYSIQUE (`_resolve`), rendue RELATIVE à la racine quand
    elle est dessous — sous l'une de ses orthographes (`_root_spellings` : telle
    quelle, résolue, minusculisée, pliée) —, absolue sinon. Relativiser sur la
    seule orthographe exacte laissait la forme minusculisée d'un chemin absolu
    un tour en retard (racine sous `/var` → `/private/var` avec `T/`), et des
    fichiers ordinaires dépassaient la borne."""
    return _relativiser(_resolve(c.replace("\\", "/"), root), spellings)


def _relativiser(r: str, spellings: list) -> str:
    """Fonction PURE, même corps que `relativiser` des gardes de chemin : `r`
    (déjà résolu) rendu relatif à la racine quand il est sous l'une de ses
    orthographes (`.` pour la racine même), inchangé sinon."""
    for s in spellings:
        if r == s:
            return "."
        if s and r.startswith(s + "/"):
            return r[len(s) + 1:]
    return r


def canonical_forms(candidates, root) -> tuple:
    """`(formes, stable)` — l'ensemble COMPLET des formes canoniques, calculé
    comme un POINT FIXE depuis les candidats reçus : à chaque tour, chaque forme
    ajoute sa casse repliée, ses deux plis NT (`nt_fold`, rognée et « points »),
    sa renormalisation lexicale (`posixpath.normpath`) et sa résolution
    physique (`_physique`). Arrêt quand l'ensemble ne grandit plus.

    BORNE : `FORMES_BORNE` = 5 tours ; la stabilité doit être CONSTATÉE au plus
    tard au 5e (un tour qui n'ajoute rien). POURQUOI 5 : un alias (point,
    espace, flux ADS, détour de points) d'un lien dont la cible porte un segment
    de points (`courte1 -> z/.../courte2`) ne se stabilise qu'au 5e — à 4, ce
    fichier ordinaire était refusé (exec-critic sur fdc7cd75, M2). Une CHAÎNE de
    tels liens n'avance que d'un maillon tous les deux tours et dépasse la
    borne : `stable` est faux et l'appelant REFUSE (fail-closed). COÛT : au plus
    5 × 5 opérations par forme, dont un `realpath` (un `lstat` par composant).
    La mesure de la marge est écrite UNE fois, à `canonical_forms` de
    `.codex/hooks/protect_paths.py`."""
    root = str(root) or os.getcwd()
    spellings = _root_spellings(root)
    formes = []
    for cand in candidates:
        if cand and str(cand) not in formes:
            formes.append(str(cand))
    vues = set(formes)
    # PAS DE try/except ICI, À LA DIFFÉRENCE DES GARDES DE CHEMIN (security-
    # code-review sur fdc7cd75, S1) : `_physique` passe par `_resolve`, qui
    # rattrape déjà OSError/ValueError et retombe sur la forme LEXICALE — une
    # résolution qui lève ne sort donc jamais d'ici. Ce repli n'ouvre rien : les
    # gardes de chemin, qui appellent ce module, ont déjà REFUSÉ un chemin dont
    # la résolution lève (`formes-instables`) avant d'arriver jusqu'ici.
    for _tour in range(FORMES_BORNE):
        neuves = []
        for forme in formes:
            for g in (forme.lower(), nt_fold(forme), nt_fold(forme, True),
                      posixpath.normpath(forme), _physique(forme, root, spellings)):
                if g and g not in vues:
                    vues.add(g)
                    neuves.append(g)
        if not neuves:
            return formes, True
        formes.extend(neuves)
    return formes, False


def _relatives(candidate: str, spellings: list, root: str) -> list:
    """Les clés (relatives à la racine, repliées) des DEUX formes du candidat ;
    une forme absolue HORS racine ne donne pas de clé. La racine a aussi sa forme
    résolue parmi `spellings` (`_root_spellings`), donc un chemin sous `/var` et
    une racine sous `/private/var` (macOS) se reconnaissent."""
    keys = []
    for form in _forms(candidate, root):
        for key in _relative(form, spellings):
            if key not in keys:
                keys.append(key)
    return keys


def _relative(c: str, spellings: list) -> list:
    """Une forme (déjà résolue ou normalisée), relative à la racine, repliée sous
    ses DEUX lectures (rognée, « points ») ; liste vide si elle est absolue HORS
    racine."""
    if _is_absolute(c):
        for s in spellings:
            if c.startswith(s + "/"):
                c = c[len(s) + 1:]
                break
        else:
            return []
    while c.startswith("./"):
        c = c[2:]
    # Le pli retire point et espace finaux, donc il peut VIDER un segment
    # (`a/.../b` → `a//b`) ou y faire naître un `..` : on renormalise APRÈS le
    # pli, pour chacune des deux lectures.
    out = []
    for key in (_normpath(nt_fold(c)), _normpath(nt_fold(c, True))):
        if key not in out:
            out.append(key)
    return out


def in_kit_code(key: str) -> bool:
    """`key` (relatif, replié) est-il dans l'ensemble kit-code ?"""
    return key in KIT_CODE_FILES or key.startswith(KIT_CODE_PREFIXES)


def _grant_in_set(grant: str) -> bool:
    """Un octroi ne vaut que DANS l'ensemble : un fichier de l'ensemble, un
    préfixe de l'ensemble, ou un chemin/préfixe sous l'un d'eux. `.`, `.claude/`
    ou `core-scripts/` sont hors ensemble."""
    return grant in KIT_CODE_FILES or grant.startswith(KIT_CODE_PREFIXES)


def _covers(grant: str, key: str) -> bool:
    """Préfixe si l'octroi finit par `/`, égalité sinon — jamais une sous-chaîne."""
    if grant.endswith("/"):
        return key.startswith(grant)
    return key == grant


def read_grants(root: str | os.PathLike, now: datetime | None = None):
    """`(octrois valides [(chemin replié, ligne)], ignorées {cause: n})`, ou lève
    OSError si le fichier existe et ne se lit pas. Absent → `([], {})`."""
    path = Path(root) / GRANT_REL
    if not path.exists():
        return [], {}
    text = path.read_text(encoding="utf-8")  # OSError/UnicodeDecodeError : refus
    now = now or datetime.now(timezone.utc)
    valid, ignored = [], {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        cause = None
        if len(fields) != 3 or not _TICKET.match(fields[1]):
            cause = "malformée"
        else:
            try:
                due = datetime.strptime(fields[2], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)
            except ValueError:
                cause = "malformée"
            else:
                grant = fields[0].replace("\\", "/")
                while grant.startswith("./"):
                    grant = grant[2:]
                grant = nt_fold(grant)  # le `/` final survit : segment vide gardé
                if due <= now:
                    cause = "échue"
                elif not _grant_in_set(grant):
                    cause = "hors ensemble"
                else:
                    valid.append((grant, line))
        if cause:
            ignored[cause] = ignored.get(cause, 0) + 1
    return valid, ignored


def _ignored_text(ignored: dict) -> str:
    if not ignored:
        return ""
    total = sum(ignored.values())
    detail = ", ".join(f"{n} {cause}" for cause, n in sorted(ignored.items()))
    return f" {total} ligne(s) d'octroi ignorée(s) : {detail}."


def kit_code_reason(candidates, root, now: datetime | None = None):
    """`(raison, règle, octroi)` pour les orthographes d'UN chemin.

    ("", "", "")                   hors ensemble, ou rien à dire ;
    ("", "kit-code-octroi", ligne) dans l'ensemble ET couvert par un octroi ;
    (raison, "kit-code", "")       dans l'ensemble et non couvert — ou fichier
                                   d'octroi illisible.

    LA RÈGLE RETENUE (exec-critic, constat 2) : chaque orthographe est jugée
    sous ses DEUX formes, physique et lexicale (`_forms`). REFUS dès qu'UNE
    forme tombe dans l'ensemble sans être couverte ; OCTROI seulement si CHAQUE
    forme qui tombe dans l'ensemble est couverte par une ligne valide — une forme
    HORS ensemble ne demande rien (elle n'est pas du code du kit), et un octroi
    qui ne couvre que l'une des deux formes dans l'ensemble ne vaut pas.
    Le marqueur n'est PAS relu ici : l'appelant ne consulte ce module que s'il
    est posé.

    L'ENSEMBLE, PAS UNE LISTE (T-00000722) : les candidats sont d'abord
    REFERMÉS (`canonical_forms`), puis chaque forme de l'ensemble est jugée ;
    un ensemble qui ne se stabilise pas dans la borne est un REFUS
    (`formes-instables`), jamais un jugement partiel."""
    root = str(root) or os.getcwd()
    spellings = _root_spellings(root)
    formes, stable = canonical_forms(candidates, root)
    shown = next((str(c) for c in candidates if c), "")
    if not stable:
        return (f"BLOCKED by kit-code guard: '{shown}' — ses formes canoniques (plis "
                f"NTFS, renormalisation, casse, résolution physique) ne se stabilisent "
                f"pas en {FORMES_BORNE} tours : refus plutôt que deviner (T-00000722).",
                FORMES_INSTABLES, "")
    keys = []
    for cand in formes:
        for key in _relatives(cand, spellings, root):
            if in_kit_code(key) and key not in keys:
                keys.append(key)
    if not keys:
        return "", "", ""
    try:
        grants, ignored = read_grants(root, now)
    except (OSError, UnicodeDecodeError) as exc:
        return (f"BLOCKED by kit-code guard: '{shown}' est du code du kit et "
                f"KIT_CODE_PROTEGE est posé ; le fichier d'octroi {GRANT_REL} est "
                f"ILLISIBLE ({type(exc).__name__}) — refus plutôt que deviner "
                "(T-00000763).", "kit-code", "")
    for key in keys:
        line = next((ln for g, ln in grants if _covers(g, key)), None)
        if line is None:
            return (f"BLOCKED by kit-code guard: '{shown}' est du code du kit et "
                    f"KIT_CODE_PROTEGE est posé (T-00000763) — seul le pilote l'ouvre, "
                    f"par une ligne `<chemin|préfixe/> T-<8 chiffres ou ULID> "
                    f"<AAAA-MM-JJTHH:MMZ>` (UTC) dans {GRANT_REL}.{_ignored_text(ignored)} "
                    "Un agent n'écrit ni le marqueur ni l'octroi.", "kit-code", "")
    return "", "kit-code-octroi", line


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="garde du code du kit (T-00000763)")
    ap.add_argument("--root", required=True)
    ap.add_argument("candidates", nargs="*")
    args = ap.parse_args(argv)
    reason, rule, grant = kit_code_reason(args.candidates, args.root)
    if reason:
        sys.stderr.write(reason + "\n")
        return 2
    if rule == "kit-code-octroi":
        sys.stdout.write(grant + "\n")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
