#!/usr/bin/env python3
"""CORPUS ADVERSARIAL DE LA RÉDACTION, BASE FIGÉE 645846e8 — module frère de
`test_cadre_ledger_redaction.py` (`T-00001130` plan r4, avec `T-00001143` et `T-00001144`).

HISTOIRE. La passe de `T-00001130` (projection du texte privé de ses `Cf`, union d'empans)
avait RÉGRESSÉ contre 645846e8 — `"Key x"+U+200B+"AIza…"+"-sk-proj-…"` sortait la clé
Google ENTIÈRE en clair (`test_ancre_S_00004014…`) — et la règle d'arrêt (S-00004011,
S-00004014) avait rendu `rediger` à 645846e8, ce module épinglant alors sa sortie EXACTE. Le
plan r4 rend la passe, avec la double union des correspondances brutes, les frontières du
souligné et le jwt linéaire : ce module n'exige plus la sortie EXACTE de 645846e8, il exige
qu'aucun cas ne rougisse là où 645846e8 est vert.

POURQUOI UN CORPUS PAR CLASSE. Le fuzz du voisin (`_cas_fuzz`) EXCLUT de son domaine deux
jetons séparés par un `Cf` SEUL : c'est là que la passe projection jouée la première
(0dc39b67) régressait sans qu'aucun témoin ne rougisse (faux vert, S-00004005). Ce corpus est
construit D'ABORD, déterministe (une graine par classe), par CLASSE nommée, et la MÊME
fonction `defauts(module, cas)` sert au banc de mesure et aux témoins ci-dessous : le tableau
mesuré et les tests ne peuvent pas diverger. LE CORPUS EST UNE DONNÉE DU PLAN : il ne lit que
la base figée, jamais le module vivant, et `test_le_corpus_est_celui_que_le_plan_a_mesure`
rougit s'il dérive.

CLASSES. (i) un `Cf` DANS un jeton, avant et après sa longueur minimale ; (ii) deux jetons
ENTIERS séparés par un `Cf` seul ou par `Cf-` ; (iii) un jeton entier, un `Cf`, un jeton
COUPÉ ; (iv) un jeton collé derrière un jeton coupé ; (v) deux jetons collés sans
séparateur ; (vi) texte légitime ; (vii) toutes les familles de `MOTIFS` ; fuzz (20 000) ;
(viii) un jeton, un `Cf` seul, une clé AWS, un jeton COLLÉ qui ouvre en minuscule ; (ix)
`x<Cf>` devant une clé Google dont le dernier caractère du corps est `-` ou `_`, puis un jeton
collé (l'ancre S-00004014 généralisée) ; (x) le souligné AUTOUR d'un jeton (`T-00001144`) ;
(q) 40 000 jetons entre des têtes et des queues réelles (`foo_`, `-hello`, `_suite`, `x`…) ;
(xi) la (viii) SANS son `Cf` (plan r4, étape 2). Une classe neuve vient EN FIN de `CLASSES` :
l'insérer plus haut redistribuerait les graines des autres.

ALPHABETS RÉELS (plan r4, C1 du critique) : chaque corps est tiré dans l'alphabet de sa
famille, tirets et soulignés compris — `gh?_` `[0-9A-Za-z]`, `github_pat_` `+_`, `glpat-`,
`eyJ`, `AIza`, `sk-` `+_-`, `xox?-` `+-`, AWS `[0-9A-Z]` ; une ouverture d'une autre famille
est retirée d'un corps tiré.

BASE FIGÉE. `MOTIFS_645846E8` recopie LITTÉRALEMENT les motifs de 645846e8 (empreinte
`7e86aab4…`) et `BASE_645846E8` y joue l'algorithme de 645846e8 (une passe brute
séquentielle) : les motifs vivants peuvent changer sans déplacer la base.

CRITÈRE PAR CAS (`defauts`) : aucune fenêtre de 10 caractères d'un jeton dans la sortie privée
de ses `Cf`, `rediger` idempotent, `contient_secret(rediger(x))` faux ; un texte légitime sort
IDENTIQUE et n'est pas reconnu comme secret. CE QUI EST EXIGÉ : (1) la base figée est celle de
645846e8 et l'empreinte des motifs vivants est celle mesurée ; (2) aucune régression contre la
base, par classe ; (3) les FUITES CONNUES du module vivant comptées par classe
(`FUITES_CONNUES`), toutes des fragments en clair ; (4) l'ancre S-00004014 ; (5) un témoin par
union ; (6) le point fixe et les effets nommés du docstring de `redaction.py`.

Les faux jetons sont TIRÉS à l'exécution (graine fixe) et leurs préfixes coupés dans le
source : le gitleaks du dépôt n'y voit aucun secret.
"""

from __future__ import annotations

import hashlib
import importlib.util
import random
import re
import string
import sys
import unicodedata
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[2]
#: Le paquet `cadre` que `vendor_paths` désigne (vendor d'abord, puis `src/cadre`), chargé PAR CHEMIN sans
#: toucher `sys.path` (patron v3prep, S-01M5BXT85VP4JBBMXVXR9STP5F).
_SPEC_VENDOR = importlib.util.spec_from_file_location(
    "_redaction_cf_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
assert _SPEC_VENDOR is not None and _SPEC_VENDOR.loader is not None
_VENDOR = importlib.util.module_from_spec(_SPEC_VENDOR)
sys.modules[_SPEC_VENDOR.name] = _VENDOR
_SPEC_VENDOR.loader.exec_module(_VENDOR)
_VENDOR.charger_paquet(ROOT, "cadre")

from cadre.ledger import redaction  # noqa: E402

ZWSP, ZWJ, SHY, BOM, RLO, WJ = (chr(c) for c in (0x200B, 0x200D, 0x00AD, 0xFEFF, 0x202E, 0x2060))
#: Les `Cf` SÉPARATEURS de la classe (ii).
CF_SEPARATEURS = (ZWSP, ZWJ, SHY, BOM, RLO)
CF_TOUS = CF_SEPARATEURS + (WJ, chr(0x2061), chr(0x200C), chr(0x200E))
GRAINE = 1130

_AN = string.ascii_letters + string.digits
_MAJ = string.ascii_uppercase + string.digits
_AWS = ("AK" + "IA", "ASIA", "AGPA", "AIDA", "AROA", "AIPA", "ANPA", "ANVA", "ABIA", "ACCA")
#: Ouvertures ALPHANUMÉRIQUES de `MOTIFS` : un corps PEM qui en porte une est retiré au tirage.
_OUVERTURES_AN = _AWS + ("ey" + "J", "AI" + "za")
#: Toutes les ouvertures : un corps de JETON tiré dans un alphabet réel qui en porte une
#: fausserait le tableau (un jeton dans le jeton) — il est retiré au tirage.
_INTERDITS = _OUVERTURES_AN + ("sk-", "gh" + "p_", "gh" + "o_", "gh" + "s_", "gh" + "u_", "gh" + "r_",
                               "git" + "hub", "gl" + "pat", "xo" + "x")
_PAT, _GL, _JWT, _SL, _GO, _SK = _AN + "_", _AN + "_-", _AN + "_-", _AN + "-", _AN + "_-", _AN + "_-"


class Cas(NamedTuple):
    classe: str
    texte: str
    purs: tuple[str, ...]  # jetons d'origine, sans `Cf` ; vide = texte légitime
    detail: str
    #: la forme dont relève le cas (`b`, `b'`, `b''`, `c`), telle que la passe de T-00001130
    #: l'a nommée — donnée du plan, jamais lue par les témoins ci-dessous.
    borne: str = ""


def _corps(rng: random.Random, n: int, alphabet: str = _AN, interdits: tuple[str, ...] = _INTERDITS) -> str:
    while True:
        s = "".join(rng.choice(alphabet) for _ in range(n))
        if not any(o in s for o in interdits):
            return s


def _pem(rng: random.Random, label: str = "RSA ", fin: bool = True) -> str:
    corps = "\n".join(_corps(rng, 48, _AN + "+/", _OUVERTURES_AN) for _ in range(3))
    tete = "-----BEGIN " + label + "PRIVATE " + "KEY-----\n"
    return tete + corps + ("\n-----END " + label + "PRIVATE " + "KEY-----" if fin else "\n")


#: `(type, fabrique(rng, rallonge, variante))` — une famille de `MOTIFS` par entrée,
#: `variante` choisissant le préfixe (AWS, `gh?_`, `xox?-`, `sk-…`, étiquette PEM).
FAMILLES = (
    ("private_key", lambda g, r, v: _pem(g, ("RSA ", "EC ", "DSA ", "OPENSSH ", "ENCRYPTED ",
                                             "PGP ", "")[v % 7])),
    ("aws_access_key", lambda g, r, v: _AWS[v % 10] + _corps(g, 16, _MAJ)),
    ("github_token", lambda g, r, v: "gh" + "posur"[v % 5] + "_" + _corps(g, 36 + r)),
    ("github_token", lambda g, r, v: "github" + "_pat_" + _corps(g, 22 + r, _PAT)),
    ("gitlab_token", lambda g, r, v: "gl" + "pat-" + _corps(g, 20 + r, _GL)),
    ("jwt", lambda g, r, v: "ey" + "J" + _corps(g, 8, _JWT) + "." + _corps(g, 9, _JWT) + "."
     + _corps(g, 8 + r, _JWT)),
    ("slack_token", lambda g, r, v: "xo" + "x" + "baprs"[v % 5] + "-" + _corps(g, 10 + r, _SL)),
    ("google_api_key", lambda g, r, v: "AI" + "za" + _corps(g, 35, _GO)),
    ("openai_key", lambda g, r, v: "sk-" + ("", "proj-", "ant-api03-", "svcacct-")[v % 4]
     + _corps(g, 20 + r, _SK)),
)
#: Le PEM SANS marqueur END avale tout ce qui le suit : il n'est jamais suivi d'un jeton.
PEM_TRONQUE = ("private_key", lambda g, r, v: _pem(g, fin=False))
_AVANT = ("", "Key ", "token=", "« ", "\n")
_APRES = ("", " fin", " »", ".\n")


def _minimal(jeton: str) -> int:
    """La plus courte tête de `jeton` qu'un motif de la BASE FIGÉE reconnaît ENTIÈRE —
    mesurée, jamais écrite à la main (`sk-ant-api03-` + 10 suffit : le groupe optionnel se
    saute). La base, pas le module vivant : le corpus est une donnée du plan."""
    for n in range(1, len(jeton) + 1):
        if any(m.fullmatch(jeton[:n]) for _, m in MOTIFS_645846E8):
            return n
    raise AssertionError("jeton du corpus non reconnu : " + jeton[:6])


def _coupures(jeton: str) -> list[int]:
    """Où couper : dans l'ouverture, avant la longueur minimale, à elle, après elle."""
    mini = _minimal(jeton)
    return sorted({2, mini // 2, mini - 1} | ({mini, mini + 3} if len(jeton) > mini + 3 else set()))


def classe_i(rng: random.Random) -> list[Cas]:
    cas = []
    for k, (type_, fab) in enumerate(FAMILLES + (PEM_TRONQUE,)):
        for c, cf in enumerate(CF_TOUS):
            jeton = fab(rng, 10, k + c)
            av, ap = _AVANT[c % 5], ("" if fab is PEM_TRONQUE[1] else _APRES[c % 4])
            for i in _coupures(jeton):
                cas.append(Cas("i", av + jeton[:i] + cf + jeton[i:] + ap, (jeton,),
                               f"{type_} U+{ord(cf):04X} @{i}/{_minimal(jeton)}"))
    return cas


def classe_ii(rng: random.Random) -> list[Cas]:
    a36, h36 = "A" * 36, "H" * 36
    jwt1 = "ey" + "J" + "abc12345" + "." + "payload01" + "." + "sig012345"
    jwt2 = "ey" + "J" + "zyx98765" + "." + "payload02" + "." + "sig543210"
    cas = [  # ANCRES du binôme bis, verbatim
        Cas("ii", "gh" + "p_" + a36 + ZWSP + "sk-" + "ant-api03-" + "C" * 30,
            ("gh" + "p_" + a36, "sk-" + "ant-api03-" + "C" * 30), "ancre ghp+ZWSP+sk-ant"),
        Cas("ii", jwt1 + ZWSP + "-" + jwt2, (jwt1, jwt2), "ancre JWT+ZWSP-+JWT"),
        Cas("ii", "gh" + "p_" + h36 + ZWSP + "xo" + "xb-" + "1" * 10,
            ("gh" + "p_" + h36, "xo" + "xb-" + "1" * 10), "ancre ghp+ZWSP+xoxb"),
    ]
    for k1, (t1, f1) in enumerate(FAMILLES):
        for k2, (t2, f2) in enumerate(FAMILLES + (PEM_TRONQUE,)):
            for c, cf in enumerate(CF_SEPARATEURS):
                for sep in (cf, cf + "-"):
                    j1, j2 = f1(rng, 6 * (c % 2), k1 + c), f2(rng, 6 * (k2 % 2), k2 + c)
                    ap = "" if f2 is PEM_TRONQUE[1] else _APRES[c % 4]
                    cas.append(Cas("ii", _AVANT[k1 % 5] + j1 + sep + j2 + ap, (j1, j2),
                                   f"{t1}|U+{ord(cf):04X}{sep[1:]}|{t2}"))
    return cas


def classe_iii(rng: random.Random) -> list[Cas]:
    cas = []
    for k1, (t1, f1) in enumerate(FAMILLES):
        for k2, (t2, f2) in enumerate(FAMILLES + (PEM_TRONQUE,)):
            sep, cf = CF_SEPARATEURS[(k1 + k2) % 5], CF_TOUS[(k1 * 3 + k2) % 9]
            j1, j2 = f1(rng, 0, k1), f2(rng, 13, k2)  # rallonge 13 : queue de 10 ou de 7
            mini = _minimal(j2)
            for i in sorted({mini // 2} | ({mini + 3, mini + 6} if len(j2) > mini + 6 else {2})):
                cas.append(Cas("iii", "Key " + j1 + sep + j2[:i] + cf + j2[i:], (j1, j2),
                               f"{t1}|U+{ord(sep):04X}|{t2} coupé @{i}/{mini}", "b'"))
    return cas


def classe_iv(rng: random.Random) -> list[Cas]:
    cas = [
        Cas("iv", "AK" + "IA" + "ABCDEFGHIJKLMN" + RLO + "OP" + "xo" + "xb-" + "1" * 10,
            ("AK" + "IA" + "ABCDEFGHIJKLMNOP", "xo" + "xb-" + "1" * 10), "ancre AWS coupé+xoxb"),
        Cas("iv", "Q" + ZWSP + "AK" + "IA" + "Z3XYQ7WNRT4KLMND" + "xo" + "xb-11" + ZWSP + "1" * 8,
            ("AK" + "IA" + "Z3XYQ7WNRT4KLMND", "xo" + "xb-" + "1" * 10), "ancre point fixe"),
    ]
    for k1, (t1, f1) in enumerate(FAMILLES):
        for k2, (t2, f2) in enumerate(FAMILLES + (PEM_TRONQUE,)):
            cf = CF_TOUS[(k1 + 2 * k2) % 9]
            j1, j2 = f1(rng, 10, k1 + k2), f2(rng, 0, k2)
            mini = _minimal(j1)
            for i in sorted({mini // 2, mini + 3 if len(j1) > mini + 3 else mini - 2}):
                cas.append(Cas("iv", "Key " + j1[:i] + cf + j1[i:] + j2, (j1, j2),
                               f"{t1} coupé @{i}/{mini}|U+{ord(cf):04X}|{t2} collé", "c"))
    return cas


def classe_v(rng: random.Random) -> list[Cas]:
    cas = []
    for k1, (t1, f1) in enumerate(FAMILLES):
        for k2, (t2, f2) in enumerate(FAMILLES + (PEM_TRONQUE,)):
            j1, j2 = f1(rng, 0, k1 + k2), f2(rng, 0, k2)
            cas.append(Cas("v", "Key " + j1 + j2, (j1, j2), f"{t1}{t2} collés", "c"))
    return cas


_MOTS = ("bonjour", "famille", "coupure", "douce", "naïve", "valeur", "clé", "שלום", "مرحبا",
         "日本語", "token", "risque", "tâche", "secret", "AK" + "IA", "ey" + "Jhb", "xo" + "xb",
         "gh" + "p", "sk-court", "AI" + "za", "glpat")
_EMOJI = ("\U0001F468" + ZWJ + "\U0001F469" + ZWJ + "\U0001F467", "\U0001F3F3" + "️" + ZWJ
          + "\U0001F308", "❤" + "️")
_BIDI = tuple(chr(c) for c in (0x200E, 0x200F, 0x202A, 0x202B, 0x202C, 0x202D, 0x202E, 0x2066,
                               0x2067, 0x2068, 0x2069, 0x061C))


def classe_vi(rng: random.Random) -> list[Cas]:
    fixes = ["famille " + _EMOJI[0], BOM + "texte précédé d'un BOM", "שלום" + chr(0x200F) + " abc",
             "coupure" + SHY + "douce", "mot" + ZWSP + "coupé", "task-" + "ABCDEFGHIJKLMNOPQRSTUVWX",
             "AK" + "IA" + ZWSP + "court", "x" + WJ + "y" + chr(0x2061) + "z", RLO + "evil" + chr(0x202C),
             "ey" + "J" + ZWSP + "abc.def", "sk" + ZWSP + "-" + "abc", BOM * 3, ZWJ, ""]
    cas = [Cas("vi", t, (), "fixe") for t in fixes]
    for n in range(300):
        morceaux = []
        for _ in range(rng.randint(1, 8)):
            mot = rng.choice(_MOTS)
            if len(mot) > 2 and rng.random() < 0.5:
                i = rng.randint(1, len(mot) - 1)
                mot = mot[:i] + rng.choice((SHY, ZWSP, ZWJ, chr(0x200C))) + mot[i:]
            morceaux.append(rng.choice((mot, mot, rng.choice(_EMOJI), rng.choice(_BIDI) + mot)))
        texte = rng.choice(("", BOM)) + rng.choice((" ", ", ", "\n")).join(morceaux)
        cas.append(Cas("vi", texte, (), f"tiré {n}"))
    return cas


def classe_vii(rng: random.Random) -> list[Cas]:
    cas = []
    for type_, fab in FAMILLES:
        for v in range(10):
            jeton = fab(rng, v % 3, v)
            cf, cf2 = CF_TOUS[v % 9], CF_TOUS[(v + 4) % 9]
            for texte in (jeton, "Key " + jeton + " fin", "x" + cf + jeton + cf2 + "y",
                          "« " + jeton[:len(jeton) // 2] + cf + jeton[len(jeton) // 2:] + " »"):
                cas.append(Cas("vii", texte, (jeton,), f"{type_} v{v}"))
    jeton = PEM_TRONQUE[1](rng, 0, 0)
    cas += [Cas("vii", "Key " + jeton, (jeton,), "private_key tronqué"),
            Cas("vii", "Key " + jeton[:20] + ZWSP + jeton[20:], (jeton,), "private_key tronqué coupé")]
    return cas


#: Familles qui ouvrent en MINUSCULE : derrière une clé AWS sans séparateur, 645846e8 les
#: rédige (lookahead AWS `(?![A-Z0-9])`, puis frontière que pose le marqueur AWS).
MINUSCULES = tuple(f for f in FAMILLES if f[0] in ("github_token", "gitlab_token", "jwt", "slack_token",
                                                    "openai_key"))


def classe_viii(rng: random.Random) -> list[Cas]:
    """Un jeton, un `Cf` SEUL, une clé AWS, un jeton COLLÉ qui ouvre en minuscule : vert à
    645846e8 ; rouge à 95df5a87, où les correspondances brutes, prises sans les frontières
    des marqueurs successifs, ne voyaient pas le troisième."""
    cas = []
    for k1, (t1, f1) in enumerate(FAMILLES):
        for k3, (t3, f3) in enumerate(MINUSCULES):
            for c, cf in enumerate(CF_SEPARATEURS):
                j1, j3 = f1(rng, 0, k1 + c), f3(rng, 0, k3 + c)
                aws = _AWS[(k1 + k3 + c) % 10] + _corps(rng, 16, _MAJ)
                cas.append(Cas("viii", "Key " + j1 + cf + aws + j3 + " fin", (j1, aws, j3),
                               f"{t1}|U+{ord(cf):04X}|aws|{t3}"))
    return cas


_SEP_ELARGIS = (" ", "\n", ", ", "=", ": ", "", ZWSP + " ") + CF_TOUS + tuple(c + "-" for c in CF_SEPARATEURS)
_SEP_CF = frozenset(CF_TOUS) | {c + "-" for c in CF_SEPARATEURS}


def classe_fuzz(rng: random.Random, n: int = 20_000) -> list[Cas]:
    """1 à 4 jetons coupés par 0 à 2 `Cf`, séparés par un séparateur ordinaire, un `Cf` SEUL,
    `Cf-`, ou RIEN. La forme se lit sur le texte : (b) `x<Cf>` devant un premier jeton coupé,
    (b') un `Cf` seul ou `Cf-` devant un jeton coupé, (b'') un jeton coupé suivi d'un `Cf` seul
    ou `Cf-`, (c) deux jetons collés — SAUF une clé AWS suivie d'un jeton qui ouvre en
    minuscule, que 645846e8 rédige (lookahead AWS). TAILLE 20 000 : à 2 500, ce fuzz ne
    rougissait pas contre 95df5a87 (mesuré) ; à 20 000 il rougissait (`ghu_…<U+FEFF>-ghs_…`)."""
    cas = []
    for n_ in range(n):
        tete = rng.choice(("", "Key ", "token=", "x" + ZWSP))
        purs, morceaux, bornes = [], [tete], set()
        coupes_prec = 0
        for k in range(rng.randint(1, 4)):
            j = rng.choice(FAMILLES)[1](rng, rng.choice((0, 0, 6, 12)), rng.randint(0, 9))
            sep = rng.choice(_SEP_ELARGIS) if k else tete
            morceaux += [sep] if k else []
            purs.append(j)
            coupes = rng.choice((0, 0, 1, 2))
            for _ in range(coupes):
                i = rng.randint(1, len(j) - 1)
                j = j[:i] + rng.choice(CF_TOUS) + j[i:]
            morceaux.append(j)
            aws_puis_minuscule = k and purs[-2][:4] in _AWS and purs[-1][0].islower()
            bornes |= ({"c"} if k and sep == "" and not aws_puis_minuscule else set()) | (
                {"b" if not k else "b'"} if coupes and (sep in _SEP_CF or sep == "x" + ZWSP) else set()) | (
                {"b''"} if k and coupes_prec and sep in _SEP_CF else set())
            coupes_prec = coupes
        cas.append(Cas("fuzz", "".join(morceaux), tuple(purs), f"fuzz {n_}", "".join(sorted(bornes))))
    return cas


def classe_ix(rng: random.Random) -> list[Cas]:
    """`x<Cf>` devant une clé Google (longueur FIXE) dont le DERNIER caractère du corps est le
    séparateur `-` ou `_`, puis un jeton COLLÉ : l'empan brut du premier TOUCHE l'empan projeté
    du second (ancre S-00004014 généralisée ; d4542c09 y rougissait 18 fois contre 645846e8)."""
    cas = []
    for t1, f1 in [f for f in FAMILLES if f[0] == "google_api_key"]:
        for k2, (t2, f2) in enumerate(FAMILLES + (PEM_TRONQUE,)):
            for c, cf in enumerate(CF_TOUS):
                for sep in ("-", "_"):
                    j1, j2 = f1(rng, 0, c)[:-1] + sep, f2(rng, 0, k2 + c)
                    cas.append(Cas("ix", "Key x" + cf + j1 + j2 + ("" if f2 is PEM_TRONQUE[1] else " fin"),
                                   (j1, j2), f"ix {t1}{sep}{t2}"))
    return cas


def classe_x(rng: random.Random) -> list[Cas]:
    """Le souligné AUTOUR d'un jeton (`T-00001144`) : devant, derrière, des deux côtés, avec un
    `Cf` dans le jeton, et deux jetons collés par `_` (le reste rouge relève de la borne (c2))."""
    cas = []
    for k, (t, f) in enumerate(FAMILLES):
        for v in range(5):
            j = f(rng, v % 3, k + v)
            for av, ap in (("foo_", ""), ("foo_", "_suite"), ("", "_suite"), ("_", "_"), ("k=", "_suite"),
                           ("x_", "_y")):
                cas.append(Cas("x", av + j + ap + " fin", (j,), f"{t} {av}|{ap}"))
            cf, i = CF_TOUS[(k + v) % 9], len(j) // 2
            cas.append(Cas("x", "foo_" + j[:i] + cf + j[i:] + "_suite", (j,), f"{t} foo_ Cf _suite"))
    for k1, (t1, f1) in enumerate(FAMILLES):
        for k2, (t2, f2) in enumerate(FAMILLES + (PEM_TRONQUE,)):
            j1, j2 = f1(rng, 0, k1), f2(rng, 0, k2)
            cas.append(Cas("x", "k=" + j1 + "_" + j2, (j1, j2), f"{t1}_{t2}"))
    return cas


def classe_q(rng: random.Random, n: int = 40_000) -> list[Cas]:
    """Têtes et queues RÉELLES (C1 du critique, r3) autour d'un jeton hors PEM tiré dans
    l'alphabet réel. Le reste rouge : des jetons à LONGUEUR FIXE collés à ce qui prolongerait
    leur corps, la borne (c3)."""
    cas = []
    for i in range(n):
        t, f = FAMILLES[1 + i % 8]
        j = f(rng, rng.choice((0, 0, 3, 9)), rng.randint(0, 9))
        av = rng.choice(("", "k=", "foo_", "_", "-", " ", "x-"))
        ap = rng.choice(("", "-hello", "_suite", " fin", "-", "_", ".x", "-_", "__x", "hello", "9", "x"))
        cas.append(Cas("q", av + j + ap, (j,), f"{t} {av}|{ap}"))
    return cas


def classe_xi(rng: random.Random) -> list[Cas]:
    """La (viii) SANS son `Cf` (plan r4, étape 2) : un jeton, une clé AWS, un jeton qui ouvre
    en minuscule, COLLÉS. Rouge au prototype r3g, dont la passe brute ne prenait que les
    correspondances indépendantes : le corps du premier traversait la clé AWS jusqu'à
    l'ouverture du troisième, et la suite de celui-ci sortait en clair."""
    cas = []
    for k1, (t1, f1) in enumerate(FAMILLES):
        for k3, (t3, f3) in enumerate(MINUSCULES):
            for c, (av, ap) in enumerate((("Key ", " fin"), ("k=", "_"), ("", ""), ("'=", "'"), (" ", " fin"))):
                j1, j3 = f1(rng, 0, k1 + c), f3(rng, 0, k3 + c)
                aws = _AWS[(k1 + k3 + c) % 10] + _corps(rng, 16, _MAJ)
                cas.append(Cas("xi", av + j1 + aws + j3 + ap, (j1, aws, j3), f"{t1}|aws|{t3} {av!r}{ap!r}"))
    return cas


#: L'ORDRE fait les graines (`corpus()` en tire une par RANG) : une classe neuve vient en fin.
CLASSES = (("i", classe_i), ("ii", classe_ii), ("iii", classe_iii), ("iv", classe_iv),
           ("v", classe_v), ("vi", classe_vi), ("vii", classe_vii), ("fuzz", classe_fuzz),
           ("viii", classe_viii), ("ix", classe_ix), ("x", classe_x), ("q", classe_q), ("xi", classe_xi))


def corpus() -> dict[str, list[Cas]]:
    """Le corpus ENTIER, déterministe : une graine par classe, pour qu'ajouter une
    classe ne redistribue pas les tirages des autres."""
    return {nom: fab(random.Random(GRAINE * 100 + k)) for k, (nom, fab) in enumerate(CLASSES)}


def defauts(module, cas: Cas) -> list[str]:
    """Les critères violés par `module.rediger` sur `cas` — vide si le cas est VERT."""
    r = module.rediger(cas.texte)
    if not cas.purs:
        return ((["légitime modifié"] if r != cas.texte else [])
                + (["faux positif"] if module.contient_secret(cas.texte) else []))
    plat = "".join(c for c in r if unicodedata.category(c) != "Cf")
    sortie = []
    if any(j[i:i + 10] in plat for j in cas.purs for i in range(len(j) - 9)):
        sortie.append("fragment")
    if module.rediger(r) != r:
        sortie.append("idempotence")
    if module.contient_secret(r):
        sortie.append("contient_secret")
    return sortie


_PEM_LABEL_645846E8 = r"(?:RSA |EC |DSA |OPENSSH |ENCRYPTED |PGP )?"
#: Les `MOTIFS` de 645846e8, recopiés LITTÉRALEMENT (jamais lus au module vivant, qui change) :
#: `test_la_base_figee_est_celle_de_645846e8` les tient par leur empreinte.
MOTIFS_645846E8 = (
    ("private_key", re.compile(r"-----BEGIN " + _PEM_LABEL_645846E8 + r"PRIVATE KEY-----[\s\S]*?"
                               r"(?:-----END " + _PEM_LABEL_645846E8 + r"PRIVATE KEY-----|\Z)")),
    ("aws_access_key", re.compile(r"(?<![A-Z0-9])(?:AKIA|ASIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ABIA|ACCA)"
                                  r"[0-9A-Z]{16}(?![A-Z0-9])")),
    ("github_token", re.compile(r"\bgh[posur]_[0-9A-Za-z]{36,}\b")),
    ("github_token", re.compile(r"\bgithub_pat_[0-9A-Za-z_]{22,}\b")),
    ("gitlab_token", re.compile(r"\bglpat-[0-9A-Za-z_-]{20,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")),
    ("slack_token", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("openai_key", re.compile(r"\bsk-(?:proj-|ant-api\d{2}-|svcacct-)?[A-Za-z0-9_-]{20,}")),
)


def _rediger_645846e8(texte: str) -> str:
    """L'ALGORITHME de 645846e8 — une seule passe brute SÉQUENTIELLE, rien à travers les
    `Cf` — sur ses `MOTIFS` figés."""
    for type_, motif in MOTIFS_645846E8:
        texte = motif.sub(lambda _m, t=type_: "[SECRET RÉDIGÉ:" + t + "]", texte)
    return texte


#: La BASE de comparaison des témoins, FIGÉE ici plutôt que lue au code vivant (qui dérive).
BASE_645846E8 = SimpleNamespace(rediger=_rediger_645846e8,
                                contient_secret=lambda t: any(m.search(t) for _, m in MOTIFS_645846E8))


def _empreinte(motifs) -> str:
    """sha256 des `(type, motif)` de `MOTIFS`, dans l'ordre (l'ordre fait la sortie)."""
    return hashlib.sha256("\n".join(t + "\t" + m.pattern for t, m in motifs).encode("utf-8")).hexdigest()


def _empreinte_vivante(motifs) -> str:
    """sha256 de chaque `type`, classe et `pattern` de `MOTIFS`, plus le `depart` et la `suite`
    d'un `_MotifLineaire` (critique de plan, C2 r3) : l'un ou l'autre changé casse
    l'équivalence au motif nu, que le banc voisin tient, et change cette empreinte."""
    lignes = []
    for t, m in motifs:
        champs = [t, type(m).__name__, m.pattern]
        if hasattr(m, "depart"):
            champs += [m.depart.pattern, m.suite.pattern]
        lignes.append("\t".join(champs))
    return hashlib.sha256("\n".join(lignes).encode("utf-8")).hexdigest()


#: Empreinte MESURÉE sur le fichier de 645846e8, identique à c6aee28a.
EMPREINTE_MOTIFS_645846E8 = "7e86aab4a88db966124b20c69d3cfb53917887ee2b52ed18fe0b626893a69f94"
#: Empreinte MESURÉE des `MOTIFS` du plan r4 (tête, queue gardée, jwt linéaire), queue
#: `(?![0-9A-Za-z_])` de `github_pat_` comprise (avis LOW de la revue de sécurité).
EMPREINTE_MOTIFS_VIVANTS = "f7d398f0f6adb41af45cf7b466b1440cdcb8d8effc81949e633031444ea56c58"

#: Rouges de la BASE figée, MESURÉS par classe sur ce corpus (annexe r3 du plan, rejoués à
#: l'identique ; (xi) mesurée ici) : le corpus est une donnée — un tirage qui dérive les change.
FUITES_645846E8 = {"i": 330, "ii": 7, "iii": 162, "iv": 158, "v": 26, "vi": 0, "vii": 81,
                   "fuzz": 14_049, "viii": 0, "ix": 135, "x": 261, "q": 13_935, "xi": 99}

#: FUITES CONNUES du module vivant, MESURÉES par classe : cas où `defauts` n'est pas vide (toutes
#: des fenêtres de 10 caractères d'un jeton, en clair), toutes rouges aussi à la base. Dans les
#: bornes (b), (b'), (b'') et (c) du docstring de `redaction.py` : (iii) b', (iv), (v) et (xi) c1
#: (le corps du premier traverse ce qui le suit), (x) c2, (q) c3, fuzz toutes. Une fuite qui
#: tombe ou qui grossit fait rougir ce compte : se re-mesure et se ré-écrit au docstring de
#: `redaction.py`, jamais en silence.
FUITES_CONNUES = {"i": 0, "ii": 0, "iii": 36, "iv": 50, "v": 24, "vi": 0, "vii": 0,
                  "fuzz": 3_396, "viii": 0, "ix": 0, "x": 1, "q": 1_615, "xi": 90}


class CorpusSainTests(unittest.TestCase):
    """Le corpus ne ment pas : chaque jeton tiré, SEUL, est un secret ENTIER de sa
    famille, et aucun corps ne porte l'ouverture d'une autre famille."""

    def test_chaque_jeton_seul_est_un_seul_secret_de_sa_famille(self):
        rng = random.Random(GRAINE)
        for type_, fab in FAMILLES + (PEM_TRONQUE,):
            for v in range(10):
                jeton = fab(rng, v, v)
                with self.subTest(famille=type_, v=v):
                    self.assertEqual(redaction.rediger(jeton), "[SECRET RÉDIGÉ:" + type_ + "]")


class CorpusContreLaBaseTests(unittest.TestCase):
    """Le module vivant contre la BASE FIGÉE, classe par classe. MUTATIONS mesurées rouges :
    le prototype r3g ((xi) et fuzz), le tip d4542c09 ((ix)), 95df5a87 ((viii))."""

    corpus: dict[str, list[Cas]] = {}
    vivant: dict[str, list[list[str]]] = {}
    base: dict[str, list[list[str]]] = {}

    @classmethod
    def setUpClass(cls):
        cls.corpus = corpus()
        cls.vivant = {k: [defauts(redaction, c) for c in v] for k, v in cls.corpus.items()}
        cls.base = {k: [defauts(BASE_645846E8, c) for c in v] for k, v in cls.corpus.items()}

    def test_la_base_figee_est_celle_de_645846e8(self):
        self.assertEqual(_empreinte(MOTIFS_645846E8), EMPREINTE_MOTIFS_645846E8)

    def test_l_empreinte_des_MOTIFS_vivants_est_celle_mesuree(self):
        """Un motif vivant changé — `depart` et `suite` du jwt compris — rougit ici : les
        comptes ci-dessous ont été mesurés sur CES motifs."""
        self.assertEqual(_empreinte_vivante(redaction.MOTIFS), EMPREINTE_MOTIFS_VIVANTS)

    def test_le_corpus_est_celui_que_le_plan_a_mesure(self):
        self.assertEqual(set(FUITES_645846E8), set(self.corpus), "une classe sans compte de base")
        self.assertEqual({k: sum(map(bool, d)) for k, d in self.base.items()}, FUITES_645846E8)

    def test_aucune_regression_vs_645846e8(self):
        """Le corpus ENTIER, fuzz compris, peut ROUGIR contre sa base : un cas rouge ici et
        vert sous `BASE_645846E8` est une RÉGRESSION, dans une borne ou non."""
        for classe, cas in self.corpus.items():
            with self.subTest(classe=classe):
                regr = [c.detail for c, dv, db in zip(cas, self.vivant[classe], self.base[classe])
                        if dv and not db]
                self.assertEqual(regr[:3], [], f"({classe}) {len(regr)} régression(s) vs 645846e8")

    def test_les_fuites_connues_sont_comptees_par_classe(self):
        self.assertEqual(set(FUITES_CONNUES), set(self.corpus), "une classe sans compte déclaré")
        for classe, d in self.vivant.items():
            with self.subTest(classe=classe):
                self.assertEqual(sum(map(bool, d)), FUITES_CONNUES[classe], f"({classe}) fuites")
                self.assertLessEqual({k for x in d for k in x}, {"fragment"},
                                     f"({classe}) un défaut autre qu'un fragment en clair")

    def test_ancre_S_00004014_la_cle_Google_devant_un_sk_proj_est_redigee(self):
        """La régression qui a déclenché la règle d'arrêt : à c6aee28a la clé Google sortait
        ENTIÈRE en clair ; 645846e8, et le module vivant, rédigent les deux jetons."""
        texte = ("Key x" + ZWSP + "AI" + "za" + "Q" * 34 + "-sk-" + "proj-" + "K2BgfucQZjDU4tGkQPUiBm9d"
                 + " fin")
        attendu = "Key x" + ZWSP + "[SECRET RÉDIGÉ:google_api_key][SECRET RÉDIGÉ:openai_key] fin"
        self.assertEqual(BASE_645846E8.rediger(texte), attendu)
        self.assertEqual(redaction.rediger(texte), attendu)


MARQUEUR_GH = "[SECRET RÉDIGÉ:github_token]"
GHP = "gh" + "p_" + "A" * 36


class PointFixeEtEtiquetteTests(unittest.TestCase):
    """Réserves du binôme bis, chaque phrase du docstring de `redaction.py` épinglée."""

    def test_la_boucle_de_point_fixe_est_necessaire(self):
        """M1 — le marqueur AWS du premier tour ouvre une frontière devant `xoxb-` : un
        seul tour laisse le slack en clair. MUTATION « un seul tour » de `rediger` : rouge."""
        texte = "Q" + ZWSP + "AK" + "IA" + "Z3XYQ7WNRT4KLMND" + "xo" + "xb-11" + ZWSP + "1" * 8
        attendu = "Q" + ZWSP + "[SECRET RÉDIGÉ:aws_access_key][SECRET RÉDIGÉ:slack_token]"
        un_tour = redaction._rediger_brut(redaction._rediger_a_travers_le_format(texte))
        self.assertNotEqual(un_tour, attendu, "un seul tour suffit : ce témoin ne mord plus")
        self.assertEqual(redaction.rediger(texte), attendu)

    def test_deux_jetons_soudes_sortent_sous_l_etiquette_du_premier(self):
        """Sur-étiquette, sens sûr : le groupe (empan projeté + correspondances brutes qui
        le chevauchent) prend le marqueur du motif projeté. ROUGE à 231bda6d (queue en clair)."""
        self.assertEqual(redaction.rediger(GHP + ZWSP + "sk-" + "ant-api03-" + "C" * 30), MARQUEUR_GH)

    def test_un_jeton_suivi_d_un_Cf_et_d_un_mot_avale_le_mot(self):
        """Sur-absorption NOMMÉE, sens sûr : la projection soude le mot au corps du jeton."""
        self.assertEqual(redaction.rediger("Key " + GHP + ZWSP + "suite fin"), "Key " + MARQUEUR_GH + " fin")

    def test_un_jeton_soude_a_une_cle_AWS_ne_laisse_pas_le_jeton_colle(self):
        """Binôme ter (critic-opus R1, S-00004011) — les correspondances brutes de la passe
        projection portent les SÉQUENTIELLES : le marqueur AWS ouvre la frontière du jeton
        collé, qui rejoint le groupe. ROUGE à 95df5a87 et au mutant D (`UnionsTests`) : W1
        sortait `[…]-1111111111`, W2 `Key [SECRET RÉDIGÉ:jwt].payload02.sig543210`."""
        w1 = GHP + ZWSP + "AK" + "IA" + "B" * 16 + "xo" + "xb-" + "1" * 10
        self.assertEqual(redaction.rediger(w1), MARQUEUR_GH)
        w2 = ("Key " + "ey" + "J" + "abc12345.payload01.sig012345" + chr(0x200E) + "AI" + "DA"
              + "C" * 16 + "ey" + "J" + "zyx98765.payload02.sig543210")
        self.assertEqual(redaction.rediger(w2), "Key [SECRET RÉDIGÉ:jwt]")


class UnionsTests(unittest.TestCase):
    """La DOUBLE UNION des correspondances brutes (`_bruts` : indépendantes ET séquentielles),
    dans les deux passes (plan r4, étape 2). Un témoin FIXE par côté de chaque union, chacun
    MESURÉ rouge sur son mutant : A les groupes de la projection sans les indépendantes, D sans
    les séquentielles, B la passe brute sans les indépendantes, C sans les séquentielles (le
    prototype r3g ; le mutant B change aussi la forme de C, trois marqueurs, sans fragment). A
    et B sont rouges aussi à 645846e8."""

    def test_A_la_projection_unit_les_independantes(self):
        """`glpat-` fini par `-`, un jwt COLLÉ, un `Cf`, un mot : le masque de `glpat-` cache
        l'ouverture du jwt, seule sa correspondance INDÉPENDANTE (après `-`) étend le groupe.
        Mutant A : `.bbbbbbbbb.cccccccc` en clair."""
        texte = ("k=" + "gl" + "pat-" + "A" * 19 + "-" + "ey" + "J" + "a" * 8 + "." + "b" * 9 + "."
                 + "c" * 8 + ZWSP + "tail")
        self.assertEqual(redaction.rediger(texte), "k=[SECRET RÉDIGÉ:gitlab_token]" + ZWSP + "tail")

    def test_D_la_projection_unit_les_sequentielles(self):
        """Le W1 du binôme ter : seul le marqueur AWS ouvre la frontière du `xoxb-` collé.
        Mutant D, comme 95df5a87 : `-1111111111` en clair."""
        texte = GHP + ZWSP + "AK" + "IA" + "B" * 16 + "xo" + "xb-" + "1" * 10
        self.assertEqual(redaction.rediger(texte), MARQUEUR_GH)

    def test_B_la_passe_brute_unit_les_independantes(self):
        """`github_pat_` dont le corps avale `_xoxa` : son masque cache l'ouverture du slack,
        que seule sa correspondance INDÉPENDANTE (après `_`) rattache. Mutant B, comme
        645846e8 : `-1111111111` en clair."""
        texte = "k=" + "github" + "_pat_" + "B" * 22 + "_" + "xo" + "xa-" + "1" * 10
        self.assertEqual(redaction.rediger(texte), "k=" + MARQUEUR_GH)

    def test_C_la_passe_brute_unit_les_sequentielles_sans_aucun_fragment(self):
        """La (viii) sans son `Cf` (plan r4, étape 2) : le corps de `github_pat_` traverse la
        clé AWS jusqu'au `xoxa` ; seul le masque AWS rend au slack sa frontière. Mutant C, le
        prototype r3g : `-777777777777` en clair. Aucun fragment des trois jetons ne reste."""
        pat, aws, slack = ("github" + "_pat_" + "x9Kq" * 6, "AK" + "IA" + "Z3XYQ7WNRT4KLMND",
                           "xo" + "xa-" + "7" * 12)
        redige = redaction.rediger("k=" + pat + aws + slack + " fin")
        self.assertEqual(redige, "k=" + MARQUEUR_GH + " fin")
        self.assertEqual([j for j in (pat, aws, slack) for i in range(len(j) - 9) if j[i:i + 10] in redige], [])

    def test_C_BORNE_un_corps_fini_par_une_majuscule_cache_la_cle_AWS(self):
        """BORNE (c1) écrite au docstring de `redaction.py` : le témoin C ne ferme le triple que
        si le corps de `github_pat_` finit par `[a-z_]`. Fini par `B`, le lookbehind AWS refuse
        la clé dans toutes les passes et la suite du slack sort en clair, comme à 645846e8. Ce
        témoin rougit le jour où la borne tombe — mettre alors le docstring à jour."""
        texte = ("k=" + "github" + "_pat_" + "B" * 24 + "AK" + "IA" + "Z3XYQ7WNRT4KLMND" + "xo" + "xa-"
                 + "7" * 12 + " fin")
        attendu = "k=" + MARQUEUR_GH + "-" + "7" * 12 + " fin"
        self.assertEqual(BASE_645846E8.rediger(texte), attendu)
        self.assertEqual(redaction.rediger(texte), attendu)


if __name__ == "__main__":
    unittest.main()
