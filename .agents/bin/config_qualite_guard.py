#!/usr/bin/env python3
"""config_qualite_guard — refuser qu'un agent MODIFIE une config lint/format EXISTANTE
du projet (T-01M5C1AHZM41P9C3QH6X7PEQY1, chantier reprise-ecc).

CE QUE ÇA FAIT. Quand `.agents/state/gates/CONFIG_QUALITE_PROTEGE` est posé, une
écriture Edit/Write dont le NOM DE BASE (replié : casse, pli NTFS) est une config de
linter ou de formateur de la liste FERMÉE ci-dessous, ou répond à l'un des deux motifs,
est REFUSÉE dès qu'UNE de ses formes existe sur disque (union : brute, repliée,
canoniques ; un lien pendant compte comme présent ; une erreur de `lstat` autre que
« absent » compte comme présent — fail-closed). Aucune forme n'existe : c'est une
CRÉATION, permise — il n'y a pas de config à affaiblir. Le refus renvoie l'agent au
code : corriger la source plutôt qu'affaiblir la règle.

LA SORTIE est pilote-seule : une ligne VALIDE de `.agents/state/gates/CONFIG_QUALITE_AUTORISE`,

    <chemin|préfixe/> T-<8 chiffres ou ULID> <AAAA-MM-JJTHH:MMZ>

— la grammaire de `KIT_CODE_AUTORISE`, UTC, recopiée, jamais importée. Un chemin
couvre par égalité, un préfixe (terminé par `/`) par préfixe ; un octroi de fichier
doit nommer une config de la liste. Une ligne malformée, échue ou hors liste est
IGNORÉE et COMPTÉE dans le refus ; un fichier d'octroi présent mais illisible est un
refus. Octroi : sortie 3, et l'appelant passe la main à la garde suivante (le code du
kit juge encore) — l'octroi ne lève QUE ce refus-ci.

QUI L'APPELLE. Les deux gardes de chemin, SEULEMENT si le marqueur existe, APRÈS les
règles absolues et AVANT la garde du code du kit : `protect-paths.sh` (Claude) par la
CLI, les jumeaux `protect_paths.py` par chargement PARESSEUX, par CHEMIN EXPLICITE.
Le marqueur n'est PAS relu ici. Marqueur posé et ce module absent, illisible ou qui
lève : l'appelant refuse TOUT (`config-qualite-illisible`). Les jumeaux passent, en
plus des formes résolues, le chemin BRUT de la charge (avant résolution des liens)
quand sa FEUILLE est un lien symbolique (ou que son `lstat` échoue) : le NOM écrit
d'un lien est jugé, et un lien pendant compte comme présent ; un brut dont seule la
racine passe par un alias (`/var` → `/private/var`) n'est pas rejugé seul.

BORNES, ÉCRITES. Hors liste, par choix : `pyproject.toml`, `setup.cfg`, `tsconfig*`,
`jest`/`vitest`, `pytest.ini`, `package.json` (métadonnées et build mêlées à la config) ;
`.gitleaks.toml` a sa propre règle, absolue. Un `extends` vers un nom libre n'est pas
suivi. La CRÉATION d'une config IMBRIQUÉE absente (`sub/.eslintrc.json` avec
`root: true`, un `.editorconfig` de sous-dossier) est PERMISE, et peut affaiblir les
règles par cascade sur ce sous-arbre. Un lien PHYSIQUE (hard link) au nom hors liste
écrit la config sans que son nom soit vu. Une écriture par Bash (`sed -i`, `cp`, `tee`,
`ln`) n'est pas vue : la garde empêche l'OUBLI, pas la triche.

CLI : `config_qualite_guard.py --root R`, les formes d'UN chemin sur STDIN séparées
par NUL (jamais en argv : Git Bash réécrit un argv qui ressemble à un chemin). Sortie
0 : rien à dire, et stdout = `CONFIG_QUALITE_OK` — le verdict POSITIF, sans lequel
l'appelant shell refuse (un module vide ou qui sort 0 à l'import ne l'écrit pas) ;
3 : octroi (stdout = `CONFIG_QUALITE_OCTROI <la ligne>` — préfixe POSITIF, sans lequel
l'appelant shell refuse : un `sys.exit(3)` à l'import ne l'écrit pas) ; 2 : refus
(stderr = la raison). STDIN vide : refus (aucun chemin lu n'est un chemin jugé).

CRÉDIT. Écrit à neuf en Python ; liste de noms et idée (existence comme critère,
motifs `<outil>.config.<qualif>.<ext>`) inspirées de `scripts/hooks/config-protection.js`
du projet ECC (github.com/affaan-m/ECC, commit 6f1881ae), distribué sous la licence
suivante :

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

stdlib seule. Feuille : n'importe aucun module du kit.
"""
from __future__ import annotations

import argparse
import os
import posixpath
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# LA LISTE FERMÉE (plan, annexe § 3) : celle d'ECC, plus les linters des stacks du kit.
CONFIG_NAMES = frozenset({
    # ESLint (ancien format et config plate v9)
    ".eslintrc", ".eslintrc.js", ".eslintrc.cjs", ".eslintrc.json", ".eslintrc.yml",
    ".eslintrc.yaml", "eslint.config.js", "eslint.config.mjs", "eslint.config.cjs",
    "eslint.config.ts", "eslint.config.mts", "eslint.config.cts",
    # Prettier
    ".prettierrc", ".prettierrc.js", ".prettierrc.cjs", ".prettierrc.json", ".prettierrc.yml",
    ".prettierrc.yaml", "prettier.config.js", "prettier.config.cjs", "prettier.config.mjs",
    # Biome
    "biome.json", "biome.jsonc", ".biome.json", ".biome.jsonc",
    # Ruff
    ".ruff.toml", "ruff.toml",
    # Shell, style, Markdown
    ".shellcheckrc", ".stylelintrc", ".stylelintrc.json", ".stylelintrc.yml",
    ".stylelintrc.yaml", ".stylelintrc.js", ".stylelintrc.cjs", ".stylelintrc.mjs",
    "stylelint.config.js", "stylelint.config.cjs", "stylelint.config.mjs",
    "stylelint.config.ts", "stylelint.config.mts", "stylelint.config.cts",
    ".markdownlint.json", ".markdownlint.jsonc", ".markdownlint.yaml", ".markdownlint.yml",
    ".markdownlint.cjs", ".markdownlint.mjs", ".markdownlintrc",
    ".markdownlint-cli2.jsonc", ".markdownlint-cli2.yaml", ".markdownlint-cli2.cjs",
    ".markdownlint-cli2.mjs",
    # Listes d'exclusion : la façon la moins chère de faire passer un contrôle
    ".eslintignore", ".prettierignore", ".stylelintignore", ".markdownlintignore",
    ".semgrepignore",
    # Go, Ruby, Java, Python, éditeur, C/C++, Swift, Dockerfile, YAML
    ".golangci.yml", ".golangci.yaml", ".golangci.toml", ".golangci.json",
    ".rubocop.yml", ".rubocop_todo.yml",
    "checkstyle.xml",
    ".coveragerc", ".flake8", ".pylintrc", "pylintrc", "mypy.ini", ".mypy.ini",
    ".editorconfig",
    ".clang-format", "_clang-format", ".clang-tidy",
    ".swiftlint.yml", ".swiftlint.yaml",
    ".hadolint.yaml", ".hadolint.yml",
    ".yamllint", ".yamllint.yml", ".yamllint.yaml",
})

# LES DEUX MOTIFS : une config plate découpée (`eslint.config.base.mjs`, le tronc d'un
# monorepo) et un rc qualifié (`.eslintrc.base.json`). Jugés sur le nom REPLIÉ.
CONFIG_PATTERNS = (
    re.compile(r"\A(?:eslint|prettier|stylelint|commitlint|oxlint)\.config"
               r"(?:\.[a-z0-9_-]+)*\.(?:js|mjs|cjs|ts|mts|cts)\Z"),
    re.compile(r"\A\.(?:eslintrc|prettierrc|stylelintrc|markdownlintrc)"
               r"(?:\.[a-z0-9_-]+)*\.(?:js|cjs|mjs|json|jsonc|yml|yaml|toml)\Z"),
)

ARMING_REL = ".agents/state/gates/CONFIG_QUALITE_PROTEGE"
GRANT_REL = ".agents/state/gates/CONFIG_QUALITE_AUTORISE"

RULE = "config-qualite"
RULE_OCTROI = "config-qualite-octroi"
# Le verdict positif de la CLI (sortie 0) : `protect-paths.sh` refuse toute autre sortie.
VERDICT_OK = "CONFIG_QUALITE_OK"
# Le préfixe de la ligne d'octroi (sortie 3) : `protect-paths.sh` refuse un rc 3 sans lui.
PREFIXE_OCTROI = "CONFIG_QUALITE_OCTROI "

# Ticket d'un octroi, ancré aux DEUX bouts : la grammaire de KIT_CODE_AUTORISE.
_TICKET = re.compile(r"\AT-(?:[0-9A-HJKMNP-TV-Z]{26}|\d{8})\Z")
_DRIVE = re.compile(r"\A([A-Za-z]):/(.*)\Z")
_MSYS = re.compile(r"\A/([A-Za-z])/(.*)\Z")


def nt_fold(p: str) -> str:
    """Le pli NTFS des gardes de chemin, lecture rognée : minuscule, `\\` → `/`, flux ADS
    coupé au 1er `:` par segment (lecteur de tête gardé), point et espace finaux retirés."""
    out = []
    for i, s in enumerate(p.lower().replace("\\", "/").split("/")):
        head = ""
        if i == 0 and len(s) >= 2 and s[1] == ":" and s[0].isalpha():
            head, s = s[:2], s[2:]
        s = s.split(":", 1)[0]
        if s not in (".", ".."):
            s = s.rstrip(". ")
        out.append(head + s)
    return "/".join(out)


def folded_name(path: str) -> str:
    """Le nom de base REPLIÉ (casse, pli NTFS) d'un chemin."""
    return posixpath.basename(nt_fold(str(path)).rstrip("/"))


def is_config_name(name: str) -> bool:
    """`name` (déjà replié) est-il une config lint/format de la liste ou d'un motif ?"""
    return name in CONFIG_NAMES or any(p.match(name) for p in CONFIG_PATTERNS)


def existe(path: str) -> bool:
    """Présent sur disque — fichier, dossier ou lien, même pendant. FAIL-CLOSED : seule
    une absence CONSTATÉE (`FileNotFoundError`, `NotADirectoryError`) rend faux ; toute
    autre erreur (droits, boucle, octet nul) compte comme présent."""
    try:
        os.lstat(path)
    except (FileNotFoundError, NotADirectoryError):
        return False
    except (OSError, ValueError):
        return True
    return True


def _root_spellings(root: str) -> list:
    """La racine sous ses orthographes : telle quelle, résolue (`/var` → `/private/var`),
    `c:/x` ↔ `/c/x` dans les deux casses de la lettre, chacune minusculisée et repliée.
    Les plus longues d'abord."""
    base = str(root).replace("\\", "/").rstrip("/")
    forms = {base}
    try:
        forms.add(os.path.realpath(base).replace("\\", "/").rstrip("/"))
    except (OSError, ValueError):
        pass
    for f in list(forms):
        m = _DRIVE.match(f + "/")
        if m:
            forms.update(f"/{x}/{m.group(2)}".rstrip("/") for x in (m.group(1).lower(), m.group(1).upper()))
        m = _MSYS.match(f + "/")
        if m:
            forms.update(f"{x}:/{m.group(2)}".rstrip("/") for x in (m.group(1).lower(), m.group(1).upper()))
    out = set()
    for f in forms:
        if f:
            out.update((f, f.lower(), nt_fold(f)))
    return sorted(out, key=len, reverse=True)


def _parents_resolus(c: str) -> str:
    """`c` aux dossiers parents résolus (liens compris), NOM DE FEUILLE GARDÉ : un lien de
    feuille garde son nom écrit. Erreur de résolution : `c` tel quel."""
    d, b = posixpath.split(c)
    if not d or not b:
        return c
    try:
        return posixpath.join(os.path.realpath(d).replace("\\", "/"), b)
    except (OSError, ValueError):
        return c


def _key(form: str, spellings: list, root: str = ""):
    """La clé d'une forme, relative à la racine et repliée, ou None hors racine. Les
    dossiers PARENTS sont résolus d'abord (`web -> shared` : la clé est
    `shared/.eslintrc.json`, comme le résolu des jumeaux ; `/var` → `/private/var`), la
    forme littérale ensuite : un octroi juge le fichier, jamais l'orthographe du dossier."""
    c = str(form).replace("\\", "/")
    absolu = bool(c.startswith("/") or _DRIVE.match(c))
    if not absolu and root:
        r = _parents_resolus(posixpath.join(str(root).replace("\\", "/"), c))
        if any(r.startswith(s + "/") for s in spellings):
            c, absolu = r, True
    if absolu:
        for cand in dict.fromkeys((_parents_resolus(c), c)):
            s = next((s for s in spellings if cand.startswith(s + "/")), None)
            if s is not None:
                c = cand[len(s) + 1:]
                break
        else:
            return None
    k = posixpath.normpath(nt_fold(c))
    if k == "." or k == ".." or k.startswith("../"):
        return None
    return k


def _absolute(form: str, root: str) -> str:
    c = str(form)
    return c if os.path.isabs(c) or _DRIVE.match(c.replace("\\", "/")) else os.path.join(root, c)


def _grant_valid(grant: str) -> bool:
    """Un préfixe nomme un dossier (`x/`, jamais `/` ni `./`) ; un fichier, une config."""
    if grant.endswith("/"):
        return grant not in ("/", "./") and not grant.startswith("../")
    return is_config_name(posixpath.basename(grant))


def _covers(grant: str, key: str) -> bool:
    """Préfixe si l'octroi finit par `/`, égalité sinon — jamais une sous-chaîne."""
    return key.startswith(grant) if grant.endswith("/") else key == grant


def read_grants(root, now: datetime | None = None):
    """`(octrois valides [(clé repliée, ligne)], ignorées {cause: n})` ; lève OSError ou
    UnicodeDecodeError si le fichier existe et ne se lit pas. Absent → `([], {})`."""
    path = Path(root) / GRANT_REL
    if not path.exists():
        return [], {}
    text = path.read_text(encoding="utf-8")
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
                while grant.startswith("./") and len(grant) > 2:
                    grant = grant[2:]
                grant = nt_fold(grant)
                if due <= now:
                    cause = "échue"
                elif not _grant_valid(grant):
                    cause = "hors liste"
                else:
                    valid.append((grant, line))
        if cause:
            ignored[cause] = ignored.get(cause, 0) + 1
    return valid, ignored


def _ignored_text(ignored: dict) -> str:
    if not ignored:
        return ""
    detail = ", ".join(f"{n} {cause}" for cause, n in sorted(ignored.items()))
    return f" {sum(ignored.values())} ligne(s) d'octroi ignorée(s) : {detail}."


def config_qualite_reason(candidates, root, now: datetime | None = None):
    """`(raison, règle, octroi)` pour les formes d'UN chemin.

    ("", "", "")                    aucune forme n'est une config, ou aucune n'existe ;
    ("", "config-qualite-octroi", l) config existante, CHAQUE clé visée couverte ;
    (raison, "config-qualite", "")  config existante non couverte, ou octroi illisible.

    Une forme est VISÉE si son nom replié est une config ; l'existence se juge en UNION
    sur TOUTES les formes reçues. Un octroi ne vaut que si chaque forme visée a une clé
    sous la racine, et que chaque clé est couverte : une forme visée hors racine ne
    s'octroie pas, et son refus le DIT (le seul levier est le marqueur, jamais un octroi).
    Juger ou filtrer ces formes hors racine reste une question au pilote."""
    root = str(root) or os.getcwd()
    formes = list(dict.fromkeys(str(c) for c in candidates if c))
    visees = [f for f in formes if is_config_name(folded_name(f))]
    if not visees:
        return "", "", ""
    if not any(existe(_absolute(f, root)) for f in formes):
        return "", "", ""
    shown = formes[0]
    try:
        grants, ignored = read_grants(root, now)
    except (OSError, UnicodeDecodeError) as exc:
        return (f"BLOCKED by config-qualite guard: '{shown}' est une config lint/format EXISTANTE "
                f"et CONFIG_QUALITE_PROTEGE est posé ; le fichier d'octroi {GRANT_REL} est ILLISIBLE "
                f"({type(exc).__name__}) — refus plutôt que deviner.", RULE, "")
    spellings = _root_spellings(root)
    keys = [_key(f, spellings, root) for f in visees]
    hors = next((f for f, k in zip(visees, keys) if k is None), None)
    if hors is not None:
        return (f"BLOCKED by config-qualite guard: '{shown}' est une config lint/format EXISTANTE "
                f"dont une forme ('{hors}') est HORS de la racine du projet, et CONFIG_QUALITE_PROTEGE "
                f"est posé — aucun octroi de {GRANT_REL} ne couvre un chemin hors racine ; seul le "
                "pilote lève ce refus, en retirant le marqueur.", RULE, "")
    lines = [next((ln for g, ln in grants if _covers(g, k)), None) for k in keys]
    line = lines[0] if all(lines) else None
    if line is None:
        return (f"BLOCKED by config-qualite guard: '{shown}' est une config lint/format EXISTANTE "
                "du projet et CONFIG_QUALITE_PROTEGE est posé — corrige le code pour satisfaire la "
                "règle plutôt que d'affaiblir la config. Un changement de config légitime est ouvert "
                "par le pilote seul, par une ligne `<chemin|préfixe/> T-<8 chiffres ou ULID> "
                f"<AAAA-MM-JJTHH:MMZ>` (UTC) dans {GRANT_REL}.{_ignored_text(ignored)} "
                "Un agent n'écrit ni le marqueur ni l'octroi.", RULE, "")
    return "", RULE_OCTROI, line


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="garde des configs lint/format existantes")
    ap.add_argument("--root", required=True)
    args = ap.parse_args(argv)
    data = sys.stdin.buffer.read().decode("utf-8", "surrogateescape")
    candidates = [c for c in data.split("\0") if c]
    if not candidates:
        sys.stderr.write("BLOCKED by config-qualite guard: aucun chemin reçu sur STDIN "
                         "(formes séparées par NUL) — refus plutôt qu'accord.\n")
        return 2
    reason, rule, grant = config_qualite_reason(candidates, args.root)
    if reason:
        sys.stderr.buffer.write((reason + "\n").encode("utf-8", "surrogateescape"))
        return 2
    if rule == RULE_OCTROI:
        sys.stdout.buffer.write((PREFIXE_OCTROI + grant + "\n").encode("utf-8", "surrogateescape"))
        return 3
    # En OCTETS, comme le rc 3 : le mode texte traduirait `\n` en `\r\n` sous Windows, et
    # `protect-paths.sh` exige `CONFIG_QUALITE_OK` à l'octet.
    sys.stdout.buffer.write((VERDICT_OK + "\n").encode("ascii"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
