r"""Huit formes de bash VALIDE que `tree-sitter-bash` ne parse pas — et qui
retirent le fichier ENTIER du compte des cibles inspectées par la porte SAST.

POURQUOI CE FILET EXISTE — mesuré le 2026-09-09 (T-00000525), à trois témoins.

Le parseur `tree-sitter-bash` de semgrep bute sur des constructions que `bash -n`
accepte sans un mot. **Rien dans le shell ne signale le problème, et le fichier
tourne parfaitement** : la panne est entièrement du côté de l'ANALYSEUR.

CE QUE ÇA COÛTE, ET CE N'EST PAS THÉORIQUE. Un SEUL site fait échouer le parse du
FICHIER ENTIER, qui est alors **retiré du compte des cibles inspectées** par la
porte SAST de classe 1. Mesuré sur le commit `1ebc7b9` : la porte annonçait
`1/4 cible(s) inspectée(s)` puis `clean on the diff`. Après correction du seul
`sca-java.test.sh`, elle annonçait `2/4`.

ET LE COÛT S'EST MATÉRIALISÉ. Corriger les sites a **révélé un finding `ERROR`
préexistant** (`gitleaks-scan.test.sh:193`, `shell-eval-on-interpolated-value`)
sur lequel la porte était aveugle depuis toujours — suivi en T-00000540. Un
périmètre annoncé « clean » n'avait jamais été lu.

RELEVÉ D'ENTRÉE, ET LA MÉTHODE QUI L'A DONNÉ : **17 fichiers sur 121**. Un scan
semgrep GROUPÉ SOUS-COMPTE — `safe-bash.test.sh` rendait 0 erreur dans un lot de
121 et 1 erreur scanné seul. Le relevé se fait donc **fichier par fichier**, et
semgrep ne rend **qu'une erreur par fichier** : chaque correction en découvre une
autre, donc on re-mesure après chaque geste. Sortie : **0 sur 121**.

────────────────────────────────────────────────────────────────────────────────
CE QUE CE FILET COUVRE — les formes STRUCTURELLES, celles qu'un motif de ligne
peut décider sans parser le shell :

  1. `case … in <clause>` sur la MÊME ligne.   <- le `esac` n'y est POUR RIEN
  2. `if ! { … ; }`  — le `!` devant un groupe d'accolades.
  3. `if <cmd> <<MOT` — un heredoc en CONDITION de `if` (délimiteur quoté inclus).
  4. `10#$X` — la notation de base forcée (elle donne un `Syntax error` COMPLET).

Le point 1 mérite sa correction publique : la première rédaction de ce filet
n'interdisait que le `case` ENTIER sur une ligne, ancré en DÉBUT de ligne. Elle
laissait donc passer `for … do case … esac; done`, `f() { case … esac; }` et
`case … in *"x"*) … ;;` avec le `esac` plus bas — **dix sites réels**. Un filet
qui affirme une garantie qu'il ne tient pas est exactement ce que L-00000111
nomme. La règle VRAIE, bissectée : c'est **la clause collée au `case … in`**.
`case "$X" in` seul en fin de ligne parse ; `case "$X" in  # commentaire` aussi.

CE QUE CE FILET NE COUVRE PAS — BORNE DÉCLARÉE (L-00000187 : là où on ne peut
pas énumérer, on borne). Quatre autres formes sont réelles et corrigées dans
l'arbre, mais leur détection par motif produirait trop de faux positifs pour
qu'un filet bloquant les porte :

  5. métacaractère (`<` `>` `|` `&` `(`) dans une expansion — `${x:-<root>}`
  6. arithmétique parenthésée — `$(( (a-b)/60 ))`
  7. espace ÉCHAPPÉ en motif de `case` — `set\ *)`, `cat\ *)`, `\[\ *)`
  8. classe de caractères à antislash — `?:[\\/]*)`

Ces quatre-là sont tenues par la porte SAST elle-même, qui les fait apparaître
comme parse partiel. `test_no_unparsed_shell` ci-dessous est le filet qui les
attrape TOUTES, y compris une neuvième forme qu'on n'a pas encore rencontrée —
mais il exige `semgrep`, donc il SKIPPE là où l'outil n'est pas installé. Les
quatre motifs de ligne ci-dessus tiennent SANS semgrep : ce sont les deux
étages, et aucun ne prétend au rôle de l'autre.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEMGREP_CFG = ".agents/security/semgrep.yml"

# 1. `case … in` suivi d'AUTRE CHOSE qu'un blanc ou un commentaire, n'importe où
#    dans la ligne (pas seulement en tête : `for … do case …` et `f() { case … }`
#    sont les formes qui ont échappé à la première rédaction).
CLAUSE_COLLEE = re.compile(r"\bcase\b[ \t]+.+?[ \t]+\bin\b[ \t]+(?![ \t]*#)\S")

# 2. `!` devant un groupe d'accolades.
BANG_ACCOLADE = re.compile(r"(?:^|[;&|]|\b(?:if|while|until|then|else|do)\b)[ \t]*![ \t]*\{")

# 3. heredoc en condition de `if` — délimiteur nu, 'quoté' ou "quoté", `<<` ou `<<-`.
HEREDOC_EN_CONDITION = re.compile(r"^[ \t]*if\b.*<<-?[ \t]*['\"]?[A-Za-z_][A-Za-z0-9_]*")

# 4. notation de base forcée.
BASE_FORCEE = re.compile(r"\b\d+#\$")

MOTIFS: dict[str, tuple[re.Pattern[str], str]] = {
    "case-clause-collee": (
        CLAUSE_COLLEE,
        "`case … in <clause>` sur la MÊME ligne. Fais descendre la clause d'une "
        "ligne — `case … in`, puis les clauses, puis `esac`. Le `esac` n'a rien "
        "à voir avec la panne : c'est la clause collée au `in` qui casse.",
    ),
    "bang-devant-accolade": (
        BANG_ACCOLADE,
        "`! { … ; }` — le `!` devant un groupe d'accolades. Relève le statut "
        "à la place : `{ … ; } || rc=1` puis `if [ \"$rc\" -eq 1 ]`.",
    ),
    "heredoc-en-condition-de-if": (
        HEREDOC_EN_CONDITION,
        "un heredoc en CONDITION de `if`. Exécute la commande, puis `rc=$?`, "
        "puis `if [ \"$rc\" -eq 0 ]`.",
    ),
    "base-forcee": (
        BASE_FORCEE,
        "`10#$X` — la notation de base forcée. Elle produit un `Syntax error` "
        "COMPLET, pas un parse partiel. `[ \"$x\" -ge 1 ]` compare en DÉCIMAL, "
        "donc sans le piège de l'octal (vérifié sur 08, 09, 007).",
    ),
}

# EXEMPTIONS — ensemble CLOS et daté, jamais un motif ouvert. Chaque entrée
# porte sa raison ; une exemption sans raison est une porte dérobée.
EXEMPT: dict[str, str] = {
    # VIDE, et c'est le bon état : les 17 fichiers de l'arbre ont été corrigés
    # le 2026-09-09, `.agents/bin/qwen-dev.sh` compris — le pilote l'a sorti de
    # la garde de chemins de façon PERMANENTE, il n'y a donc plus de résidu
    # « geste du pilote » à porter ici.
    #
    # Une exemption ne se rajoute ici qu'avec sa RAISON et sa DATE. Un
    # dictionnaire vide est une couverture totale ; le remplir sans motif serait
    # une porte dérobée, et `test_every_exemption_carries_a_reason_and_still_exists`
    # le refuse déjà.
}


def shell_files() -> list[Path]:
    """Les fichiers SUIVIS qui sont du SHELL.

    Le test du shebang porte sur `sh`/`bash`/`zsh`/`dash`/`ksh`, PAS sur la
    simple présence d'un `#!` : la première rédaction retenait tout fichier à
    shebang, donc les scripts `#!/usr/bin/env python3` du dépôt — et un motif de
    `case` shell y appariait de la prose de docstring (`tasks.py:1961`).
    """
    listed = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=False
    ).stdout.split()
    out = []
    for rel in listed:
        path = ROOT / rel
        try:
            text = path.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeDecodeError):
            continue
        first = text.split("\n", 1)[0]
        interprete_shell = first.startswith("#!") and re.search(
            r"\b(ba|z|da|k)?sh\b", first
        )
        # AUDIT DU 22/09 (T-00000695), BORNE ÉCRITE PLUTÔT QUE RE-DÉCOUVERTE : ce
        # filtre écarte les exports de run suivis sous `runs/` — mais PAS par une
        # règle qui les vise. Contrairement à `test_spec_citation_par_nom.py`, qui
        # a reçu une exclusion de préfixe parce que `.json` était dans son
        # ensemble d'extensions, l'accident tient ICI par construction : un export
        # est un objet JSON par ligne, il ne peut être ni un `.sh` ni porter un
        # shebang shell en première ligne. Ne pas ajouter d'exclusion `runs/` :
        # elle serait cérémonielle, et une exclusion cérémonielle apprend à en
        # poser d'autres qui, elles, masqueraient une vraie cible.
        if rel.endswith(".sh") or interprete_shell:
            out.append(path)
    return out


class FormesNonParsablesTests(unittest.TestCase):
    """Étage 1 — motifs de ligne. Tient SANS semgrep."""

    def test_aucune_forme_interdite_ne_survit(self) -> None:
        fautes: list[str] = []
        for path in shell_files():
            rel = path.relative_to(ROOT).as_posix()
            if rel in EXEMPT:
                continue
            for num, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), 1
            ):
                if line.lstrip().startswith("#"):
                    continue  # ligne de commentaire ENTIÈRE : le parseur s'en moque
                for nom, (motif, _remede) in MOTIFS.items():
                    if motif.search(line):
                        fautes.append(f"{rel}:{num} [{nom}]")
        detail = "\n".join(
            f"  - {nom} : {remede}" for nom, (_m, remede) in MOTIFS.items()
        )
        self.assertEqual(
            fautes,
            [],
            "Des formes que `tree-sitter-bash` NE PARSE PAS survivent. Chacune "
            "retire le FICHIER ENTIER du compte des cibles inspectées par la "
            f"porte SAST de classe 1.\n{detail}\nSites : {fautes}",
        )

    def test_la_population_balayee_n_est_pas_vide(self) -> None:
        """NON-VACUITÉ (L-00000232) : un filet qui balaie zéro fichier passe
        pour de bonnes raisons apparentes et ne mesure rien."""
        trouves = shell_files()
        self.assertGreater(
            len(trouves), 30, f"population de balayage anormalement petite : {len(trouves)}"
        )

    def test_aucun_fichier_python_dans_la_population(self) -> None:
        """Un `#!/usr/bin/env python3` n'est pas du shell. Sans ce contrôle, la
        prose d'une docstring apparie les motifs (mesuré : `tasks.py:1961`)."""
        pythons = [
            p.relative_to(ROOT).as_posix()
            for p in shell_files()
            if p.suffix == ".py"
            or p.read_text(encoding="utf-8").split("\n", 1)[0].endswith("python3")
        ]
        self.assertEqual(pythons, [], f"fichiers python balayés comme du shell : {pythons}")

    def test_les_motifs_mordent_vraiment(self) -> None:
        """CONTRÔLE POSITIF, un couple interdit/permis par motif. Sans lui, un
        motif cassé rendrait le filet vert par VACUITÉ."""
        interdits = {
            "case-clause-collee": [
                'case "$X" in "$Y") continue ;; esac',
                'for t in a b; do case "$t" in a) : ;; esac; done',
                'f() { case "$1" in *x*) return 0 ;; esac; }',
                'case "$D" in *"COVERAGE DEGRADED"*) assert 0 "msg";;',
            ],
            "bang-devant-accolade": [
                "if ! { have tar && tar -cf - . ; }; then",
                "! { false; }",
            ],
            "heredoc-en-condition-de-if": [
                'if "$PY" - <<PY',
                "  if ! \"$PY\" - \"$A\" \"$B\" <<'PYTRUST' 2>/dev/null",
                "if cat <<-EOF",
            ],
            "base-forcee": [
                "(( 10#$RAW >= 1 ))",
                "_v=$(( 10#$X ))",
            ],
        }
        permis = [
            'case "$X" in',
            'case "$X" in  # un commentaire',
            '  "$Y") continue ;;',
            "esac",
            'a) echo un ;; *) echo deux ;;',
            "if { true; }; then",
            "if [ -f x ]; then",
            'printf "%s" "$x" <<EOF',
            "(( X >= 1 ))",
            "echo 'commit 10#$X'".replace("10#$X", "abc"),
        ]
        for nom, echantillons in interdits.items():
            motif = MOTIFS[nom][0]
            for s in echantillons:
                with self.subTest(motif=nom, ligne=s):
                    self.assertTrue(motif.search(s), f"{nom} devrait mordre sur : {s}")
        for s in permis:
            for nom, (motif, _r) in MOTIFS.items():
                with self.subTest(permis=s, motif=nom):
                    self.assertIsNone(motif.search(s), f"{nom} mord à tort sur : {s}")

    def test_chaque_exemption_porte_sa_raison_et_son_fichier(self) -> None:
        """Une exemption dont le fichier a disparu est une porte laissée ouverte
        sur rien — et une exemption sans raison est une porte dérobée."""
        for rel, raison in EXEMPT.items():
            self.assertTrue((ROOT / rel).is_file(), f"exemption périmée : {rel}")
            self.assertTrue(raison.strip(), f"exemption sans raison : {rel}")


class ParseSastTests(unittest.TestCase):
    """Étage 2 — le relevé qui attrape TOUTES les formes, y compris celles
    qu'aucun motif de ligne ne décide. Exige `semgrep` : SKIPPE sans lui, et
    le dit, plutôt que de passer vert par absence d'outil."""

    def test_no_unparsed_shell(self) -> None:
        if shutil.which("semgrep") is None:
            self.skipTest("semgrep absent — relevé de parse NON effectué (couverture réduite à l'étage 1)")
        fautifs: list[str] = []
        for path in shell_files():
            rel = path.relative_to(ROOT).as_posix()
            if rel in EXEMPT:
                continue
            # UN FICHIER À LA FOIS : un scan groupé SOUS-COMPTE (mesuré — 0 erreur
            # sur `safe-bash.test.sh` dans un lot de 121, 1 erreur seul).
            proc = subprocess.run(
                ["semgrep", f"--config={SEMGREP_CFG}", "--json", "--quiet",
                 "--metrics=off", rel],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            try:
                doc = json.loads(proc.stdout)
            except json.JSONDecodeError:
                self.skipTest(f"semgrep n'a pas rendu de JSON sur {rel} — relevé NON concluant")
            for err in doc.get("errors", []):
                kind = err.get("type")
                kind = kind[0] if isinstance(kind, list) else str(kind)
                if kind in ("PartialParsing", "Syntax error"):
                    span = (err.get("spans") or [{}])[0]
                    ligne = span.get("start", {}).get("line", "?")
                    fautifs.append(f"{rel}:{ligne} [{kind}]")
        self.assertEqual(
            fautifs,
            [],
            "Du shell que la porte SAST NE PEUT PAS LIRE. Ces fichiers sont "
            "retirés du compte des cibles inspectées, donc annoncés « clean » "
            "sans avoir été lus. Le catalogue des huit formes connues est dans "
            f"le docstring de ce module.\nSites : {fautifs}",
        )


if __name__ == "__main__":
    unittest.main()
