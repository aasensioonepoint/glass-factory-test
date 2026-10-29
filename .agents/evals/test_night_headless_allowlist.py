"""L'allowlist headless couvre les commandes que `/night` fait taper, et rien de trop large (T-00001044).

ZERO LLM CALLS. `.agents/state/gates/NIGHT_HEADLESS.allow` devient le
`--allowed-tools` de la boucle imprimee par `/night --headless`. Une commande que
`night.md` ou `night/SKILL.md` fait taper et que la liste ne couvre pas est
refusee par `claude -p` en headless — sans erreur visible avant le matin.

PERIMETRE REEL DE CE BANC — ce qu'il extrait des deux surfaces, et rien d'autre :
  (a) toute commande `python3`/`python`/`bash .agents/pyrun.sh` sur un script
      `.agents/bin/*.py`, avec son premier drapeau ou sous-verbe (texte entier) ;
  (b) dans le CODE seulement (blocs cloturés et spans entre accents graves) :
      `bash .agents/bin/*.sh`, `bash core-scripts/*.sh`, `date`, `git <verbe>`,
      `gh <verbe> <verbe>`, `bash .agents/pyrun.sh -c`.
Chaque commande extraite est COUVERTE par un prefixe de la liste, ou figure dans
`EXEMPTIONS` — gestes du gate ou du pilote, joues hors de la boucle, chacun avec
sa raison. Ce que ce banc NE voit PAS : une commande ecrite hors de ces motifs
(outil tiers, redirection, commande qu'un sous-agent choisit seul) ; la
couverture est donc BORNEE par ces motifs, jamais declaree complete.

Il tient aussi la forme de la liste : prefixes `Bash(<p>:*)` et `Bash(<p> *)`
reconnus ; refus de tout prefixe qui finit sur un repertoire (`/`) ou sur `-m`,
ou qui porte un `*` ailleurs qu'en fin ; aucun interpreteur ou `pyrun.sh` nu ;
aucun motif `Bash(` dans un commentaire (la liste est lue par une commande, mais
un LLM qui la lirait en prose y releverait un motif) ; `night_approve.py`
n'ouvre que `--delivered`, et tout autre drapeau cite est une ERREUR, jamais un
silence.

`NIGHT_HEADLESS_ALLOW` (variable d'environnement) pointe le banc sur un autre
fichier — pour verifier une proposition AVANT de l'ecrire, le fichier reel etant
protege (protect-paths + permissions.deny).
"""

import os
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ALLOWLIST = Path(
    os.environ.get("NIGHT_HEADLESS_ALLOW")
    # adopting-tree: gate du kit, absent chez l'adoptant -> setUp saute (skipTest)
    or ROOT / ".agents" / "state" / "gates" / "NIGHT_HEADLESS.allow"
)
NIGHT_SURFACES = (
    ROOT / ".claude" / "commands" / "night.md",
    ROOT / ".agents" / "skills" / "night" / "SKILL.md",
)

# (a) Interpreteur (ou pyrun.sh) + script du kit, puis son premier drapeau
# (`--x`, `--x=`) ou sous-verbe, meme apres un retour a la ligne.
COMMAND_RE = re.compile(
    r"(?<![\w./-])(python3|python|bash \.agents/pyrun\.sh) +(\.agents/bin/[A-Za-z0-9_]+\.py)\b"
    r"(?:[ \t]*\n?[ \t]*(--[a-z][a-z-]*=?|[a-z][a-z-]*))?"
)
# (b) Commandes simples, cherchees dans le code seulement.
CODE_PATTERNS = (
    re.compile(r"(?<![\w./-])bash +((?:\.agents/bin|core-scripts)/[A-Za-z0-9_.-]+\.sh)(?: +(--?[a-z][a-z-]*|[a-z][a-z-]*))?"),
    # `date` AVEC ses arguments : la liste n'ouvre que la forme exacte, sans argument.
    re.compile(r"(?<![\w./-])(date)(?![\w-])((?: +[+-][^\s`|;&)]*)*)"),
    re.compile(r"(?<![\w./-])(git) +([a-z][a-z-]*)"),
    re.compile(r"(?<![\w./-])(gh) +([a-z]+) +([a-z]+)"),
    re.compile(r"(?<![\w./-])(bash \.agents/pyrun\.sh) +(-c|-m)\b(?: +([a-z_]+))?"),
)
# Le bloc de la BOUCLE IMPRIMÉE (celui qui lance `claude -p`) est tapé par le
# shell du pilote, pas par un tour : ses `date +%s`, `grep`, `trap` n'ont pas à
# passer l'allowlist. Il est donc sorti de l'extraction — nommément.
OUTER_LOOP_MARK = "claude -p"
# Un bloc cloture, y compris dans une citation (`> ```text`) : sinon ses accents
# graves decalent l'appariement des spans de tout le reste du fichier.
_FENCE = re.compile(r"^[ \t>]*(```|~~~)[^\n]*\n(.*?)^[ \t>]*\1", re.DOTALL | re.MULTILINE)
_SPAN = re.compile(r"`([^`]+)`")

# Gestes cites par les surfaces mais JOUES HORS DE LA BOUCLE headless. Chacun
# doit (1) apparaitre dans les surfaces — une exemption morte est retiree — et
# (2) NE PAS etre couvert par la liste : une exemption couverte serait un
# mensonge sur ce que la nuit peut taper.
EXEMPTIONS = {
    "bash .agents/bin/night_keepawake.sh":
        "anti-veille : --probe et --check-prompt au gate ; start et stop tenus par la "
        "boucle externe imprimee (trap EXIT) — jamais un tour (variante headless du reveil)",
    "git push": "push du SHA vert : geste du pilote au matin — HORS de cette liste, mais HERITE "
        "de `.claude/settings.json` (`git push*`) : c'est le prompt headless qui ne le porte pas",
    "date +%H:%M": "phase 0 : H0 lue au gate, avant le go (le tour ne tape que `date` nu)",
    "gh run": "phase 1 (list/view, avant le go) et releve CI apres push (watch) — hors boucle",
    "git rev-parse": "phase 1 : ecart memoire/depot, releve du gate avant le go",
    "git ls-remote": "phase 1 : ecart memoire/depot, releve du gate avant le go",
    "git grep": "releve de jour (points d'entree V3 ; provenance du reveil), hors liste — mais "
        "ouvert par le socle de lectures de Claude Code (mesure : passe hors liste)",
    "git reset": "remede local d'une porte rouge sur secret : geste du PILOTE au matin",
    "git rebase": "re-signature LOCALE des commits d'etat avant le push (T-00000724) : "
        "geste du PILOTE au matin, hors boucle — jamais dans cette liste",
    "bash .agents/pyrun.sh -c": "au gate seulement : sha256 du plan et refus d'un lien (condition 3, phase 3) et liste "
        "des autorisations heritees (--headless, point 4) ; `-c` jamais liste",
    "bash .agents/bin/codex-dev.sh": "regle HERITEE de `.claude/settings.json` (lanceur Codex), citee dans "
        "la liste des autorisations heritees ; jamais tapee par un tour de nuit, hors de cette liste",
}
# `night_approve.py` : la nuit n'en joue QUE `--delivered` (lecture seule,
# T-00000847). `--apply` (ecrit un contrat) et `--check` sont des gestes du
# pilote que les memes documents CITENT. Tout AUTRE drapeau — ou aucun — est une
# erreur : un filtre qui ignorerait l'inconnu en silence laisserait passer un
# geste nouveau sans que personne ne decide s'il est de nuit.
NIGHT_APPROVE = ".agents/bin/night_approve.py"
NIGHT_APPROVE_NIGHT_VERBS = ("--delivered", "--delivered=")
NIGHT_APPROVE_PILOT_VERBS = ("--apply", "--check")
FORMS = ("python3", "python", "bash .agents/pyrun.sh")
# Prefixes nus qui ouvriraient n'importe quel script ou `-c "<code>"`.
FORBIDDEN_BARE = {
    "python", "python3", "bash", "bash .agents/pyrun.sh", "py", "py -3",
    "python -c", "python3 -c", "bash .agents/pyrun.sh -c", "sh", "bash -c",
}
_PREFIX_RE = re.compile(r"Bash\((.+?)(?::\*| \*)\)")


def _tool_lines(text):
    for raw in text.splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and not line.startswith("max-budget-usd"):
            yield line


def _bash_prefixes(text):
    out = []
    for line in _tool_lines(text):
        m = _PREFIX_RE.fullmatch(line)
        if m:
            out.append(m.group(1))
        elif line.startswith("Bash(") or line == "Bash":
            out.append(line)  # forme exacte ou nue : gardee pour le refus
    return out


def _malformed(prefix):
    """Un prefixe qui ouvrirait plus que le geste qu'il nomme."""
    if prefix.endswith("/"):
        return "finit sur un repertoire (ouvre tout script dessous)"
    if prefix == "-m" or prefix.endswith(" -m"):
        return "finit sur `-m` (ouvre tout module)"
    if "*" in prefix:
        return "porte un `*` ailleurs qu'en fin"
    return None


def _covered(command, prefixes):
    """Couvert par un prefixe (`Bash(p:*)`), ou EGAL a une forme exacte (`Bash(c)`)."""
    return f"Bash({command})" in prefixes or any(
        command == p or command.startswith(p + " ") for p in prefixes if not p.startswith("Bash(")
    )


def _code_chunks(text):
    fences = [body for _f, body in _FENCE.findall(text) if OUTER_LOOP_MARK not in body]
    return fences + _SPAN.findall(_FENCE.sub("", text))


def _code_commands(text):
    found = set()
    for chunk in _code_chunks(text):
        for pattern in CODE_PATTERNS:
            for m in pattern.finditer(chunk):
                parts = [g.strip() for g in m.groups() if g and g.strip()]
                if parts[0].startswith((".agents/", "core-scripts/")):
                    parts[0] = "bash " + parts[0]
                found.add(" ".join(parts))
    return found


def _exempt(command):
    return next((k for k in EXEMPTIONS if command == k or command.startswith(k + " ")), None)


def _script_commands(text):
    """(commande a couvrir ou None, erreur ou None) pour chaque appel de script."""
    for form, script, verb in COMMAND_RE.findall(text):
        if script == NIGHT_APPROVE:
            if verb in NIGHT_APPROVE_PILOT_VERBS:
                continue  # geste du pilote cite ; son refus est teste plus bas
            if verb not in NIGHT_APPROVE_NIGHT_VERBS:
                yield None, f"{form} {script} {verb or '<aucun drapeau>'} : drapeau ni de nuit ni du pilote"
                continue
            yield f"{form} {script} --delivered", None
        else:
            yield (f"{form} {script} {verb}".rstrip(), None)


class NightHeadlessAllowlistTests(unittest.TestCase):
    def setUp(self):
        if not ALLOWLIST.is_file():
            self.skipTest(f"{ALLOWLIST} absente : headless desarme, rien a couvrir")
        self.text = ALLOWLIST.read_text(encoding="utf-8")
        self.prefixes = _bash_prefixes(self.text)

    def test_surfaces_do_copy_commands(self):
        """Temoin : sans commande extraite, le banc ne prouverait rien."""
        for path in NIGHT_SURFACES:
            text = path.read_text(encoding="utf-8")
            self.assertTrue(COMMAND_RE.findall(text), f"{path}: aucune commande python extraite")
            code = _code_commands(text)
            for witness in ("date", "bash core-scripts/verify.sh", "git status"):
                self.assertTrue(
                    any(c == witness or c.startswith(witness + " ") for c in code),
                    f"{path}: temoin {witness!r} non extrait — l'extraction a derive",
                )

    def test_every_copied_command_is_allowed(self):
        missing, errors = set(), set()
        for path in NIGHT_SURFACES:
            text = path.read_text(encoding="utf-8")
            rel = path.relative_to(ROOT)
            for command, error in _script_commands(text):
                if error:
                    errors.add(f"{rel}: {error}")
                elif not _covered(command, self.prefixes):
                    missing.add(f"{rel}: {command}")
            for command in _code_commands(text):
                if not _covered(command, self.prefixes) and not _exempt(command):
                    missing.add(f"{rel}: {command}")
        self.assertFalse(errors, "night_approve cite sous un drapeau inconnu :\n  " + "\n  ".join(sorted(errors)))
        self.assertFalse(
            missing,
            "commandes que /night fait taper mais que l'allowlist headless refuserait "
            "(ni couvertes, ni exemptees nommement) :\n  " + "\n  ".join(sorted(missing)),
        )

    def test_exemptions_are_live_and_not_allowed(self):
        cited = set()
        for path in NIGHT_SURFACES:
            text = path.read_text(encoding="utf-8")
            cited |= {k for c in _code_commands(text) for k in [_exempt(c)] if k}
        self.assertEqual(set(EXEMPTIONS) - cited, set(), "exemption morte : a retirer")
        for key in EXEMPTIONS:
            self.assertFalse(_covered(key + " x", self.prefixes), f"exemption pourtant ouverte : {key}")
            self.assertTrue(EXEMPTIONS[key].strip(), f"exemption sans raison : {key}")

    def test_each_script_is_listed_under_the_three_forms(self):
        scripts = {
            m.group(1)
            for p in self.prefixes
            for m in [re.fullmatch(r"(?:python3|python|bash \.agents/pyrun\.sh) (\.agents/bin/[A-Za-z0-9_]+\.py(?: (?:--)?[a-z][a-z-]*)?)", p)]
            if m
        }
        self.assertTrue(scripts, "aucun script .agents/bin/*.py dans l'allowlist")
        missing = sorted(
            f"{form} {script}"
            for script in scripts
            for form in FORMS
            if f"{form} {script}" not in self.prefixes
        )
        self.assertFalse(missing, "forme manquante pour un script liste : " + ", ".join(missing))

    def test_night_approve_only_its_night_verb(self):
        """La nuit relit le marqueur ; elle n'ecrit ni ne juge un contrat."""
        for form in FORMS:
            self.assertTrue(
                _covered(f"{form} {NIGHT_APPROVE} --delivered T-00000001", self.prefixes),
                f"{form} {NIGHT_APPROVE} --delivered refuse",
            )
            for verb in ("--apply", "--check", ""):
                command = f"{form} {NIGHT_APPROVE} {verb} --lot p.md T-00000001".replace("  ", " ")
                self.assertFalse(
                    _covered(command, self.prefixes),
                    f"geste du pilote ouvert a la nuit : {command}",
                )

    def test_night_approve_unknown_flag_is_an_error(self):
        """T4 : le filtre ne classe plus en silence ce qu'il ne connait pas."""
        for sample, bad in (
            ("`bash .agents/pyrun.sh .agents/bin/night_approve.py --purge T-1`", True),
            ("`python .agents/bin/night_approve.py`", True),
            ("`python .agents/bin/night_approve.py --delivered=T-1`", False),
            ("`python .agents/bin/night_approve.py\n--apply --lot x`", False),
        ):
            errors = [e for _c, e in _script_commands(sample) if e]
            self.assertEqual(bool(errors), bad, f"{sample!r} -> {errors}")

    def test_pytest_is_listed_under_the_three_forms(self):
        """Fable T3 : la nuit tape `bash .agents/pyrun.sh -m pytest` (python absent)."""
        for form in FORMS:
            self.assertIn(f"{form} -m pytest", self.prefixes)

    def test_no_comma_inside_a_tool_line(self):
        """T5 : la liste est jointe par des virgules — une virgule DANS une entree la
        couperait en deux entrees que personne n'a ecrites."""
        bad = [line for line in _tool_lines(self.text) if "," in line]
        self.assertFalse(bad, f"virgule dans une ligne d'outil : {bad}")

    def test_date_is_the_exact_form_only(self):
        """T7 : `date -f <fichier>` lit un fichier ; seule la forme nue est ouverte."""
        self.assertTrue(_covered("date", self.prefixes), "`date` nu refuse")
        for wide in ("date -f .env", "date +%s", "date -s 12:00"):
            self.assertFalse(_covered(wide, self.prefixes), f"{wide} ouvert")

    def test_no_bare_interpreter(self):
        bare = [p for p in self.prefixes if p in FORBIDDEN_BARE or p in ("Bash", "Bash(*)")]
        self.assertFalse(bare, f"prefixe nu qui rendrait l'allowlist decorative : {bare}")

    def test_no_prefix_opens_more_than_it_names(self):
        bad = {p: why for p in self.prefixes for why in [_malformed(p)] if why}
        self.assertFalse(bad, f"prefixe trop large : {bad}")

    def test_prefix_parser_reads_both_syntaxes_and_refuses_wide_ones(self):
        """T1 : `Bash(x:*)` et `Bash(x *)` sont la meme regle pour Claude Code."""
        self.assertEqual(_bash_prefixes("Bash(git log:*)\nBash(git log *)\n"), ["git log", "git log"])
        for wide in (
            "Bash(python3 .agents/bin/:*)",
            "Bash(bash .agents/pyrun.sh .agents/bin/ *)",
            "Bash(python3 -m:*)",
            "Bash(python3 .agents/bin/*.py:*)",
        ):
            (prefix,) = _bash_prefixes(wide)
            self.assertTrue(_malformed(prefix), f"{wide} n'est pas refuse")

    def test_no_tool_pattern_in_a_comment(self):
        """Un LLM qui lirait le fichier en prose releverait un motif commente."""
        hits = [
            raw for raw in self.text.splitlines()
            if raw.strip().startswith("#") and "Bash(" in raw
        ]
        self.assertFalse(hits, "motif d'outil dans un commentaire du gate :\n  " + "\n  ".join(hits))


if __name__ == "__main__":
    unittest.main()
