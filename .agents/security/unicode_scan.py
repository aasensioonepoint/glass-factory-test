#!/usr/bin/env python3
"""Contrôle Unicode — caractères invisibles et de contrôle bidi dans un texte d'instructions.

POURQUOI. Un prompt (déf d'agent, commande, skill, doctrine) ou une skill tierce peut porter
des caractères que le relecteur NE VOIT PAS et que le modèle LIT : surcharges bidi (« Trojan
Source »), espaces de largeur nulle, caractères TAG (« ASCII smuggling ») ou suites de
sélecteurs de variante. Ce module les repère ; il ne réécrit jamais rien.

CE QUI EST SIGNALÉ (code points en ENTIERS ci-dessous, jamais de littéral invisible dans ce
fichier — L-00000535) : bidi 202A-202E, 2066-2069, 200E, 200F, 061C ; largeur nulle
200B-200D, 2060-2065 ; FEFF hors position 0 du texte ; tags E0000-E007F et tout le reste
du bloc E0080-E0FFF ; sélecteurs de variante FE00-FE0F, E0100-E01EF et mongols 180B-180F ;
00AD, 034F, 115F, 1160, 17B4, 17B5, 3164, FFA0, FFF0-FFF8 ; séparateurs 2028/2029 ;
toute catégorie Cf, Co, Cs ; tout Cc hors TAB, LF, CR (CR seulement juste avant LF : un CR
isolé, ou final sans LF, ramène le curseur et masque ce qui le précède à l'affichage).

CE QUI EST ADMIS (séquences emoji standard) :
  * FEFF en tout premier caractère (BOM) ;
  * UN FE0E/FE0F juste après un `So`, ou après un `Sm`/`Po` non ASCII (flèche, double
    point d'exclamation) ; FE0F entre un chiffre, `#` ou `*` et U+20E3 (keycap) ;
  * 200D (ZWJ) entre, à gauche, un `So` — éventuellement suivi d'un FE0F admis ou d'un
    modificateur de teint 1F3FB-1F3FF — et, à droite, un `So` ;
  * les TROIS seuls drapeaux de subdivision RGI, JEU FERMÉ : 1F3F4 puis les tags de
    « gbeng », « gbsct » ou « gbwls », clos par E007F. Tout autre tag — autre suite, même
    de forme valide (2 à 7 tags [0-9a-z]) — est un constat : la forme seule laissait passer
    une contrebande ASCII invisible (« ignore » en tags).

SORTIE ET CODES. Une ligne par constat, `chemin:ligne:col:U+XXXX:NOM` ; les lignes se
comptent sur LF seul (jamais `splitlines()`, qui coupe aussi sur 0085, 001C-001E, 2028...),
les colonnes en code points depuis 1. rc 0 aucun constat, 1 constat(s), 2 usage, fichier
illisible ou allowlist invalide. Les fichiers se passent après `--` ; un chemin relatif se
lit sous la racine. Ce module ne parcourt aucun arbre : l'appelant lui donne ses fichiers.

ALLOWLIST. `.agents/security/unicode-allowlist.json` sous la racine (`--racine`, défaut :
le répertoire courant) : `{"entrees": [{"cible": ..., "codepoint": "U+XXXX", "decision":
"S-<id>"}]}`, clé optionnelle `note`. `cible` = chemin relatif à la racine (posix), ou
`<owner>/<repo>#<skill>@<sha>` pour une skill tierce — un sha neuf annule l'entrée. La CLI
(`scanner`) la valide à CHAQUE appel, constat ou non : invalide, rc 2 même sur des fichiers
propres. ABSENTE, elle vaut vide ; illisible, clé inconnue ou entrée sans décision `S-<id>` :
refus (rc 2, ou message de refus pour `refus()`). Registre DISTINCT de `sca-waivers.json`
(clé paquet/version, lu par waiver_filter.py et les compteurs SCA). Le registre est RÉSERVÉ
AU PILOTE (T-01M5CN9FM2MPY8Z00AS7FTXXWH) : `protect-paths` refuse son Edit/Write sur les trois
familles d'hôtes.

LA DÉCISION EST VÉRIFIÉE CONTRE LE JOURNAL (T-01M5CN9FM2MPY8Z00AS7FTXXWH). Une entrée n'est
HONORÉE que si son `decision` est l'`id` d'une entrée `kind: decision` du journal de specs
sous la même racine : `.agents/state/specs/SPECS.jsonl`, sinon `SPECS.json` (même choix de
store que specs.py ; les deux présents = illisible, specs.py le refuse aussi). Le journal se
lit ligne à ligne, chaque ligne bornée à `MAX_LIGNE_SPECS` octets, le monolithe borné à
`MAX_MONOLITHE_SPECS` ; il n'est ouvert que si l'allowlist porte au moins une entrée. Une
entrée dont la décision n'y est pas — S-id inventé, ou `kind` autre que `decision` — est
IGNORÉE ; journal absent ou illisible (ligne non JSON, en-tête absent ou étranger, ligne
trop longue) : TOUTES les entrées ignorées (fail-closed). Ignorer n'est pas taire : le
refus de `refus()` et le stderr de la CLI DISENT chaque entrée ignorée qui aurait admis un
constat (`allowlist entry <n> ignored: decision <S-id> not found in SPECS`) ; l'allowlist
invalide reste un rc 2, une entrée ignorée ne change pas le rc (1 sur constat).

BORNES, ÉCRITES.
  * Homoglyphes (cyrillique pour latin...) : NON repérés.
  * Le journal prouve qu'une décision `S-<id>` EXISTE, jamais qu'elle porte sur CETTE entrée :
    citer une décision réelle mais étrangère passe. Ça empêche d'inventer, pas de citer à
    tort ; et `cp`, `sed -i`, `tee`, `python -c` écrivent encore le registre.
  * `refus()` (install/search de skills_github_fallback.py) ne lit l'allowlist QUE sur
    constat : une allowlist invalide n'y est vue qu'au premier texte qui porte un constat ;
    un texte propre passe sans la lire.
  * Chaînes ZWJ de `So` : aucun plafond de longueur — chaque jonction est jugée seule, et
    l'admission ZWJ/VS est STRUCTURELLE (la séquence n'est pas cherchée dans
    emoji-zwj-sequences de l'Unicode). Une longue chaîne d'emoji visibles reste admise.
  * VS15/VS16 après un `Sm`/`Po` non ASCII : admis, donc au plus UN bit caché par glyphe
    visible (FE0E ou FE0F).
  * Espaces `Zs` (2000-200A, 202F, 205F, 3000...) et U+2800 (braille vide, `So`) : admis,
    ils occupent une largeur à l'écran.
  * Catégories : `unicodedata` de l'interpréteur (Unicode 13 en 3.9, 15.1 en 3.13) — un code
    point assigné après cette version est `Cn`, non signalé hors des intervalles ci-dessus.

CRÉDIT. Écrit à neuf en Python ; liste de code points et idée inspirées de
`scripts/ci/check-unicode-safety.js` du projet ECC (github.com/affaan-m/ECC, commit
6f1881ae), distribué sous la licence suivante :

    MIT License

    Copyright (c) 2026 Affaan Mustafa

    Permission is hereby granted, free of charge, to any person obtaining a copy
    of this software and associated documentation files (the "Software"), to deal
    in the Software without restriction, including without limitation the rights
    to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
    copies of the Software, and to permit persons to whom the Software is
    furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in all
    copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
    SOFTWARE.

stdlib seule : argparse, json, re, sys, unicodedata, pathlib.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

RC_OK = 0
RC_CONSTAT = 1
RC_USAGE = 2

ALLOWLIST_REL = (".agents", "security", "unicode-allowlist.json")
CLES_ENTREE = frozenset(("cible", "codepoint", "decision"))
CLES_OPTION = frozenset(("note",))
CODEPOINT_RE = re.compile(r"U\+[0-9A-F]{4,6}")
DECISION_RE = re.compile(r"S-[0-9A-Z]{4,26}")
SPECS_REL = (".agents", "state", "specs")
SPECS_JOURNAL = "SPECS.jsonl"
SPECS_MONOLITHE = "SPECS.json"
KIND_DECISION = "decision"
MAX_LIGNE_SPECS = 1 << 20  # octets par ligne du journal ; au-delà : illisible
MAX_MONOLITHE_SPECS = 64 << 20  # octets du monolithe `SPECS.json` ; au-delà : illisible

# Intervalles fermés signalés quelle que soit leur catégorie.
SUSPECTS = (
    (0x00AD, 0x00AD),  # SOFT HYPHEN
    (0x034F, 0x034F),  # COMBINING GRAPHEME JOINER
    (0x061C, 0x061C),  # ARABIC LETTER MARK
    (0x115F, 0x1160),  # HANGUL CHOSEONG/JUNGSEONG FILLER
    (0x17B4, 0x17B5),  # KHMER VOWEL INHERENT AQ/AA
    (0x180B, 0x180F),  # sélecteurs de variante mongols 180B-180D/180F, séparateur 180E
    (0x200B, 0x200F),  # largeur nulle 200B-200D, marques LRM/RLM 200E-200F
    (0x2028, 0x202E),  # LINE/PARAGRAPH SEPARATOR 2028-2029, bidi 202A-202E
    (0x2060, 0x2065),  # WORD JOINER, opérateurs mathématiques invisibles, 2065 réservé
    (0x2066, 0x2069),  # isolats bidi
    (0x3164, 0x3164),  # HANGUL FILLER
    (0xFE00, 0xFE0F),  # sélecteurs de variante
    (0xFEFF, 0xFEFF),  # ZERO WIDTH NO-BREAK SPACE (BOM)
    (0xFFA0, 0xFFA0),  # HALFWIDTH HANGUL FILLER
    (0xFFF0, 0xFFF8),  # réservés du bloc Specials
    (0xE0000, 0xE007F),  # tags
    (0xE0080, 0xE0FFF),  # reste du bloc : VS supplémentaires E0100-E01EF et réservés
)
CATEGORIES = frozenset(("Cf", "Co", "Cs"))
CC_ADMIS = frozenset((0x09, 0x0A, 0x0D))

BOM = 0xFEFF
CR = 0x0D
VS15 = 0xFE0E
VS16 = 0xFE0F
ZWJ = 0x200D
KEYCAP = 0x20E3
KEYCAP_BASES = frozenset(ord(c) for c in "0123456789#*")
TEINTS = (0x1F3FB, 0x1F3FF)
DRAPEAU_NOIR = 0x1F3F4
TAG_ANNULE = 0xE007F
# JEU FERMÉ RGI (emoji-sequences.txt, RGI_Emoji_Tag_Sequence) : Angleterre, Écosse, pays de Galles.
SUBDIVISIONS_RGI = frozenset(tuple(0xE0000 + ord(c) for c in s) for s in ("gbeng", "gbsct", "gbwls"))


class AllowlistInvalide(Exception):
    """Allowlist illisible ou mal formée : l'appelant refuse (fail-closed)."""


class JournalIllisible(Exception):
    """Journal de specs absent ou illisible : aucune entrée d'allowlist n'est honorée."""


def suspect(cp: int) -> bool:
    if any(lo <= cp <= hi for lo, hi in SUSPECTS):
        return True
    cat = unicodedata.category(chr(cp))
    return cat in CATEGORIES or (cat == "Cc" and cp not in CC_ADMIS)


def nom(cp: int) -> str:
    ch = chr(cp)
    return unicodedata.name(ch, "") or f"<{unicodedata.category(ch)}>"


def _cat(ligne: str, k: int) -> str:
    return unicodedata.category(ligne[k]) if 0 <= k < len(ligne) else ""


def _vs_admis(ligne: str, k: int) -> bool:
    """FE0E/FE0F en k : un seul, après une base emoji, ou dans un keycap."""
    if k == 0:
        return False
    base = ord(ligne[k - 1])
    cat = _cat(ligne, k - 1)
    if cat == "So" or (cat in ("Sm", "Po") and base > 0x7F):
        return True
    suivant = ord(ligne[k + 1]) if k + 1 < len(ligne) else -1
    return ord(ligne[k]) == VS16 and base in KEYCAP_BASES and suivant == KEYCAP


def _zwj_admis(ligne: str, k: int) -> bool:
    if _cat(ligne, k + 1) != "So" or k == 0:
        return False
    gauche = ord(ligne[k - 1])
    if gauche in (VS15, VS16):
        return _vs_admis(ligne, k - 1)
    if TEINTS[0] <= gauche <= TEINTS[1]:
        return _cat(ligne, k - 2) == "So"
    return _cat(ligne, k - 1) == "So"


def _fin_subdivision(ligne: str, k: int) -> int | None:
    """Index du E007F qui clôt un drapeau RGI ouvert en k (jeu fermé), sinon None."""
    if k == 0 or ord(ligne[k - 1]) != DRAPEAU_NOIR:
        return None
    for suite in SUBDIVISIONS_RGI:
        j = k + len(suite)
        clos = j < len(ligne) and ord(ligne[j]) == TAG_ANNULE
        if clos and tuple(ord(c) for c in ligne[k:j]) == suite:
            return j
    return None


def constats(texte: str) -> list[tuple[int, int, int]]:
    """Liste de (ligne, colonne, code point) des caractères signalés et non admis."""
    trouves = []
    lignes = texte.split("\n")
    for numero, ligne in enumerate(lignes, 1):
        saut = -1
        for k, ch in enumerate(ligne):
            if k <= saut:
                continue
            cp = ord(ch)
            if cp == CR and not (k == len(ligne) - 1 and numero < len(lignes)):
                trouves.append((numero, k + 1, cp))
                continue
            if not suspect(cp):
                continue
            if cp == BOM and numero == 1 and k == 0:
                continue
            if cp in (VS15, VS16) and _vs_admis(ligne, k):
                continue
            if cp == ZWJ and _zwj_admis(ligne, k):
                continue
            fin = _fin_subdivision(ligne, k)
            if fin is not None:
                saut = fin
                continue
            trouves.append((numero, k + 1, cp))
    return trouves


def charger_allowlist(racine: str | Path) -> list[dict]:
    """Entrées de l'allowlist sous `racine` ; absente = vide ; invalide = AllowlistInvalide."""
    chemin = Path(racine).joinpath(*ALLOWLIST_REL)
    rel = "/".join(ALLOWLIST_REL)
    if not chemin.exists():
        return []
    try:
        data = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise AllowlistInvalide(f"{rel} unreadable ({exc.__class__.__name__})") from exc
    if not isinstance(data, dict) or set(data) != {"entrees"} or not isinstance(
        data["entrees"], list
    ):
        raise AllowlistInvalide(f'{rel} must be {{"entrees": [...]}} and nothing else')
    for n, e in enumerate(data["entrees"]):
        if not isinstance(e, dict) or not CLES_ENTREE <= set(e) or set(e) - CLES_ENTREE - CLES_OPTION:
            raise AllowlistInvalide(f"{rel} entry {n}: keys must be cible, codepoint, decision[, note]")
        if not isinstance(e["cible"], str) or not e["cible"]:
            raise AllowlistInvalide(f"{rel} entry {n}: empty cible")
        if not isinstance(e["codepoint"], str) or not CODEPOINT_RE.fullmatch(e["codepoint"]):
            raise AllowlistInvalide(f"{rel} entry {n}: codepoint must read U+XXXX (uppercase hex)")
        if not isinstance(e["decision"], str) or not DECISION_RE.fullmatch(e["decision"]):
            raise AllowlistInvalide(f"{rel} entry {n}: no pilot decision S-<id>")
    return data["entrees"]


def _objet_specs(octets: bytes, ou: str) -> dict:
    try:
        obj = json.loads(octets.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise JournalIllisible(f"SPECS unreadable ({ou}: {exc.__class__.__name__})") from None
    if not isinstance(obj, dict):
        raise JournalIllisible(f"SPECS unreadable ({ou}: not a JSON object)")
    return obj


def _decisions_journal(chemin: Path) -> set[str]:
    """Ids `kind: decision` de `SPECS.jsonl`, lu ligne à ligne (coupé sur LF seul, comme
    specs.py) : lignes vides sautées, première ligne non vide = en-tête `store: specs`."""
    ids: set[str] = set()
    entete = False
    with chemin.open("rb") as flux:
        numero = 0
        while True:
            brut = flux.readline(MAX_LIGNE_SPECS + 1)
            if not brut:
                break
            numero += 1
            if len(brut) > MAX_LIGNE_SPECS:
                raise JournalIllisible(f"SPECS unreadable (line {numero}: over {MAX_LIGNE_SPECS} bytes)")
            if not brut.strip():
                continue
            obj = _objet_specs(brut, f"line {numero}")
            if not entete:
                if obj.get("store") != "specs" or "format" not in obj:
                    raise JournalIllisible(f"SPECS unreadable (line {numero}: no journal header)")
                entete = True
                continue
            if obj.get("kind") == KIND_DECISION and isinstance(obj.get("id"), str):
                ids.add(obj["id"])
    if not entete:
        raise JournalIllisible("SPECS unreadable (no journal header)")
    return ids


def _decisions_monolithe(chemin: Path) -> set[str]:
    if chemin.stat().st_size > MAX_MONOLITHE_SPECS:
        raise JournalIllisible(f"SPECS unreadable ({SPECS_MONOLITHE} over {MAX_MONOLITHE_SPECS} bytes)")
    data = _objet_specs(chemin.read_bytes(), SPECS_MONOLITHE)
    if not isinstance(data.get("entries"), list):
        raise JournalIllisible(f"SPECS unreadable ({SPECS_MONOLITHE}: no 'entries' list)")
    return {e["id"] for e in data["entries"]
            if isinstance(e, dict) and e.get("kind") == KIND_DECISION and isinstance(e.get("id"), str)}


def decisions_tracees(racine: str | Path) -> set[str]:
    """Ids des entrées `kind: decision` du journal de specs sous `racine` (SPECS.jsonl, sinon
    SPECS.json) ; absent, les deux présents ou illisible : JournalIllisible."""
    dossier = Path(racine).joinpath(*SPECS_REL)
    journal, monolithe = dossier / SPECS_JOURNAL, dossier / SPECS_MONOLITHE
    try:
        if journal.exists() and monolithe.exists():
            raise JournalIllisible(f"SPECS unreadable (both {SPECS_MONOLITHE} and {SPECS_JOURNAL})")
        if journal.exists():
            return _decisions_journal(journal)
        if monolithe.exists():
            return _decisions_monolithe(monolithe)
    except OSError as exc:
        raise JournalIllisible(f"SPECS unreadable ({exc.__class__.__name__})") from exc
    raise JournalIllisible("SPECS journal absent")


def entrees_honorees(entrees: list, racine: str | Path) -> tuple[list, list[tuple[dict, str]]]:
    """(entrées dont la décision est une entrée `kind: decision` du journal, [(entrée ignorée,
    avis)]). Le journal n'est lu que si `entrees` n'est pas vide."""
    if not entrees:
        return [], []
    try:
        connues = decisions_tracees(racine)
    except JournalIllisible as exc:
        return [], [(e, f"allowlist entry {n} ignored: decision {e['decision']} unverifiable, {exc}")
                    for n, e in enumerate(entrees)]
    honorees, ignorees = [], []
    for n, e in enumerate(entrees):
        if e["decision"] in connues:
            honorees.append(e)
        else:
            ignorees.append((e, f"allowlist entry {n} ignored: decision {e['decision']} not found in SPECS"))
    return honorees, ignorees


def _avis(ignorees: list, cible: str, reste: list) -> list[str]:
    """Les avis des entrées ignorées qui auraient admis l'un des constats restants."""
    codes = {f"U+{t[2]:04X}" for t in reste}
    return [a for e, a in ignorees if e["cible"] == cible and e["codepoint"] in codes]


def _filtrer(trouves: list, cible: str, entrees: list) -> list:
    admis = {e["codepoint"] for e in entrees if e["cible"] == cible}
    return [t for t in trouves if f"U+{t[2]:04X}" not in admis]


def refus(content: str, cible: str | None = None, racine: str | Path | None = None) -> str | None:
    """Message de refus, ou None. L'allowlist (sous `racine`) n'est lue qu'en cas de constat,
    le journal de specs seulement si elle porte une entrée."""
    trouves = constats(content)
    if not trouves:
        return None
    try:
        entrees = charger_allowlist(racine) if racine is not None else []
    except AllowlistInvalide as exc:
        return f"invisible-unicode allowlist refused: {exc}"
    entrees, ignorees = entrees_honorees(entrees, racine)
    reste = _filtrer(trouves, cible, entrees)
    if not reste:
        return None
    ligne, col, cp = reste[0]
    autres = f" (+{len(reste) - 1} more)" if len(reste) > 1 else ""
    dits = "".join(f"; {a}" for a in _avis(ignorees, cible, reste))
    return f"invisible-unicode character refused: U+{cp:04X} {nom(cp)} at line {ligne} col {col}{autres}{dits}"


def _cible_de(chemin: Path, racine: Path) -> str:
    try:
        return chemin.resolve().relative_to(racine.resolve()).as_posix()
    except ValueError:
        return chemin.as_posix()


def scanner(fichiers: list[str], racine: str | Path,
            avis: list[str] | None = None) -> tuple[list[str], list[str]]:
    """(lignes de constat, lignes d'erreur) ; un chemin relatif se lit SOUS `racine`.

    L'allowlist est validée D'ABORD, constat ou non : invalide, une erreur et rien d'autre.
    `avis`, s'il est donné, reçoit l'avis de chaque entrée ignorée (décision absente du
    journal) qui aurait admis un constat — une fois chacun."""
    racine = Path(racine)
    sorties, erreurs = [], []
    try:
        entrees = charger_allowlist(racine)
    except AllowlistInvalide as exc:
        return sorties, [str(exc)]
    entrees, ignorees = entrees_honorees(entrees, racine)
    for f in fichiers:
        chemin = Path(f) if Path(f).is_absolute() else racine / f
        try:
            texte = chemin.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            erreurs.append(f"{f}: unreadable ({exc.__class__.__name__})")
            continue
        cible = _cible_de(chemin, racine)
        reste = _filtrer(constats(texte), cible, entrees)
        for ligne, col, cp in reste:
            sorties.append(f"{f}:{ligne}:{col}:U+{cp:04X}:{nom(cp)}")
        if avis is not None:
            avis.extend(a for a in _avis(ignorees, cible, reste) if a not in avis)
    return sorties, erreurs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="unicode_scan.py",
        description="Signale les caractères invisibles et bidi (rc 0 propre, 1 constat, 2 usage).",
    )
    parser.add_argument("--racine", default=None, help="racine de l'allowlist (défaut : cwd)")
    parser.add_argument("fichiers", nargs="*", help="fichiers à lire, après --")
    args = parser.parse_args(argv)
    if not args.fichiers:
        print("unicode_scan.py: no file given (usage: unicode_scan.py -- FILE...)", file=sys.stderr)
        return RC_USAGE
    avis: list[str] = []
    sorties, erreurs = scanner(args.fichiers, Path(args.racine) if args.racine else Path.cwd(), avis)
    for ligne in sorties:
        print(ligne)
    for ligne in avis:
        print(f"unicode_scan.py: {ligne}", file=sys.stderr)
    for ligne in erreurs:
        print(f"unicode_scan.py: {ligne}", file=sys.stderr)
    if erreurs:
        return RC_USAGE
    return RC_CONSTAT if sorties else RC_OK


if __name__ == "__main__":
    raise SystemExit(main())
