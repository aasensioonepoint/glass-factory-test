"""Template hygiene — what TRAVELS to the distributable branch must carry no
project or personal identity (T-00000029 / D7).

WHY THIS EXISTS. `sync_template.py` copies `main` onto
`template/starter-kit`, and `.template-exclude` decides what is stripped
(project state), frozen (`keep: docs/`) or taken. L-025 recorded that the
human reading the sync diff was the ONLY detector of a leak. That held until
it didn't: D7's audit found `.agents/bin/otel_gate_a_fixture.jsonl` — a
capture of REAL host telemetry, tracked so the normaliser could be tested
against genuine payloads — carrying, on all nine records, the pilot's
absolute filesystem path (their OS username and their employer's name) plus
ten live session UUIDs. Nothing secret, nothing exploitable; simply someone's
identity riding into a kit meant for other people. A human had reviewed that
file's diff and not seen it, which is exactly what "the only detector is a
human" gets you at scale.

WHAT IT ASSERTS
  1. Every tracked path classifies against the rules as intended: nothing
     under `.agents/state/` travels, and the artefacts the dashboard needs DO.
     "Travels" here is the TAKE predicate (`match_rule(p) is None`), the only
     one this module reads. The SEED channel (T-00001093) is a second one:
     sync_template.py writes five markers (the four `*_REQUIRED` and
     `CONFIG_QUALITE_PROTEGE`) under `.agents/state/gates/` from
     `.agents/adopter-seed/`, both stripped by TAKE — witnessed by
     test_sync_template_seed.py and test_adopting_gate_seed.py, not here.
  2. No travelling file carries a concrete identity marker: a home directory
     with a real username, or an email outside the reserved example/test
     domains.

DELIBERATELY NOT FLAGGED — the difference between a shape and an identity:
`/Users/...`, `C:/Users/<name>` in a docstring explaining a path FORM, and
addresses under `example.com` / `*.example` / `test.local`, are documentation
and fixtures. A pattern that flagged those would be silenced within a week,
which is worse than no test. The markers of the CURRENT machine are derived
at runtime (git `user.name`, the home directory's own basename) so this also
catches the next contributor's leak, not just the one already found.
"""
from __future__ import annotations

import contextlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".agents" / "bin"))

import sync_template as st  # noqa: E402 — needs the path above


def _vendor_paths():
    """`vendor_paths.py` loaded BY PATH (v3prep pattern): `sys.path` is not touched for it."""
    spec = importlib.util.spec_from_file_location(
        "_template_hygiene_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


VP = _vendor_paths()


def cadre_rel(racine: Path = ROOT) -> str:
    """The `cadre` package relative to `racine`, wherever it lives (the new place wins);
    absent: the old place, so the refusal names it."""
    dossier = VP.dossier_paquet(racine, "cadre")
    return (dossier.relative_to(Path(racine).resolve()) if dossier else VP.ANCIENS["cadre"]).as_posix()


def population_planification(racine: Path = ROOT) -> tuple[str, ...]:
    """The 37 paths of the planning optimisation (T-01M57F1AG0DYF5QJ8YXNV76RTR); the roster
    is taken where the `cadre` package of `racine` lives."""
    return tuple(
        f"{d}/{r}{s}"
        for r in ("planner", "plan-critic", "orchestrator", "plan-critic-sonnet-max")
        for d, s in ((".claude/agents", ".md"), (".codex/agents", ".toml"),
                     (".gemini/agents", ".md"), (".github/agents", ".agent.md"),
                     (".kimi-code/agents", ".md"), (f"{cadre_rel(racine)}/data/roster", ".json"))
    ) + tuple(f".agents/evals/{b}.py" for b in (
        "test_golden_transcripts", "test_juges_sans_fable", "test_planner_preflight_contract",
        "test_planification_courte", "test_template_hygiene", "test_effort_devs",
    )) + ("README.md", "README-CLAUDE.md", "docs/usage.html", "AGENTS.md",
          ".agents/ref/MODEL_MODES.md", "core-scripts/apply-mode.py",
          ".agents/skills/planning/SKILL.md")


def tracked_paths() -> list[str]:
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files"],
                         capture_output=True, text=True)
    return out.stdout.split()


def rules():
    return st.parse_exclude((ROOT / ".template-exclude").read_text(encoding="utf-8"))


def identity_scan_paths(paths: list[str], parsed) -> list[str]:
    """Travellers and tracked private inputs of the SEED and DOCS channels."""
    tracked = set(paths)
    channel_inputs = set(st.seed_targets(tracked).values())
    channel_inputs.update(st.doc_targets(tracked).values())
    return sorted(path for path in tracked
                  if travels(path, parsed) or path in channel_inputs)


# ---------------------------------------------------------------------------
# STATE IS A NATURE, NOT A PATH (T-00000354)
# ---------------------------------------------------------------------------
# The prefixes whose content is THIS repository's own accumulated history rather
# than the kit's product. A path under any of them must never reach the template
# — that is what `strip:` exists for, and `test_every_declared_state_prefix_is_
# actually_stripped` refuses to let this list name a prefix nobody strips.
STATE_BEARING_PREFIXES = (
    ".agents/state/",      # board, ledger, specs, index, local reports
    ".gemini/backups/",    # transcript backups
    "runs/",               # T-00000650 — exports « run par auteur » (JSONL), etat
                           # de run propre a CE depot ; `strip: runs/`
    "retro/",              # the LESSONS journal P3 introduced — the case that
                           # exposed the old path-anchored rule
    "PLAN-ETAT.md",        # T-012 — l'etat du chantier de refonte packaging.
    "PLAN-ETAT-DETAIL.md", # meme nature : le detail du meme etat (split 14/09).
                           # Un FICHIER, pas un repertoire : la liste est faite
                           # de prefixes et `startswith` ne demande pas une
                           # barre finale. C'est de l'histoire accumulee par CE
                           # depot, au meme titre que `retro/`.
)

# THE CLOSED PARTITION of the top level. Every tracked path's first segment must
# appear here, or the suite fails and names the remedy. Values:
#   "product"  — part of the kit; travels to the template.
#   "state"    — this repo's own history; must be stripped in full.
#   "mixed"    — holds both; the state part is named in STATE_BEARING_PREFIXES.
#   "kit-only" — belongs to THIS repository and never travels, WITHOUT being
#                state. T-00000379 lot F opened this category and `CADRE/` is its
#                first member: a showcase accumulates none of this repo's history,
#                so calling it "state" would make `is_state_bearing` lie about its
#                nature — and calling it "product" would ship an adopting project
#                our sales pitch. The three existing values had no honest slot for
#                "stripped, but not state", and inventing one was cheaper than
#                bending a predicate that other tests replay.
#                The label is NOT decorative: `test_every_kit_only_segment_is_
#                actually_stripped` proves each one is refused travel.
#   "template-only" — T-00000425. The MIRROR of "kit-only": it exists ONLY on the
#                template branch, never on main, because an `own:` rule keeps it
#                there (`TEMPLATE.md` is its first and only member today). The
#                four values above all describe a path SEEN FROM MAIN, and this
#                suite TRAVELS: run on the adopting branch it meets a tracked
#                top-level segment that main has never held, and an unclassified
#                segment is a loud failure — measured 2026-09-03 on the branch
#                after a sync, `Lists differ: ['TEMPLATE.md'] != []`, the single
#                red of 2086 tests. So the table must cover the UNION of both
#                branches, not the one branch it is written on. No `is_state_
#                bearing` claim is made about it, and no travel claim either:
#                the sync tool alone decides an `own:` path's fate.
#
# WHY A PARTITION AND NOT A LIST OF STATE FILES: `sync_template`'s default
# polarity is TAKE, so anything unclassified TRAVELS. A list of known state paths
# would therefore be a fail-OPEN enumeration; a partition is fail-CLOSED, because
# the failure mode of forgetting to update it is a red test rather than a leak.
TOP_LEVEL_CLASSIFICATION = {
    ".agents": "mixed",        # tooling + skills travel; .agents/state/ does not
    ".claude": "product",
    ".codex": "product",
    ".cursor": "product",      # T-01M5BZCDMCEQXKA2RKTB2EMW8M — cible derivee de render_hosts.py, voyage par TAKE
    ".gemini": "mixed",        # host wiring travels; .gemini/backups/ does not
    ".geminiignore": "product",
    ".gitattributes": "product",
    # T-00000464 — le hook git `pre-push` et son banc. "product" et non "state" :
    # rien ne s'y accumule, c'est un livrable comme .codex/ ou .github/, et
    # `.template-exclude` n'a AUCUNE regle dessus = TAKE par defaut, donc il
    # VOYAGE. Le tampon qu'il lit, lui, est git-ignore (.agents/state/local/) et
    # ne voyage jamais.
    ".githooks": "product",
    ".github": "product",
    ".gitignore": "product",
    ".gitleaks.toml": "product",
    ".kimi-code": "product",   # T-00000394 — 6e hote, delivrable qui voyage (comme .codex/.github) ; .template-exclude n'a AUCUNE regle dessus = TAKE par defaut
    ".template-exclude": "product",
    "AGENTS.md": "product",
    "CADRE": "kit-only",   # la vitrine : strip: CADRE/ — ne voyage pas, n est pas de l etat
    "CLAUDE.md": "product",
    "GEMINI.md": "product",
    "QUICK-SETUP.md": "product",
    "README-CLAUDE.md": "product",
    "README-OTHER-HOSTS.md": "product",
    "README-SECURITY-SCAN-SETUP.md": "product",
    "README.md": "product",
    # T-00000425 — CE FICHIER N'EXISTE QUE SUR LA BRANCHE TEMPLATE (`own: TEMPLATE.md`),
    # et il est classe ICI parce que cette suite VOYAGE. Sur main, `seen` ne le
    # contient jamais et l'entree dort ; sur la branche d'adoption, ou la suite
    # tourne aussi, il EST un segment de tete suivi — et sans cette ligne il en
    # etait un NON CLASSE, donc un echec bruyant chez chaque adoptant.
    # Mesure du 2026-09-03, porte jouee SUR la branche apres sync :
    # `AssertionError: Lists differ: ['TEMPLATE.md'] != []`, seul rouge de 2086
    # tests. Sixieme occurrence de la meme classe en une journee : une suite qui
    # voyage et qui suppose le jeu de fichiers de main. La table doit donc couvrir
    # l'UNION des deux branches, pas la seule branche ou on l'ecrit.
    "TEMPLATE.md": "template-only",  # `own:` — jamais pris de main, jamais supprime la-bas
    "agentic_v3": "product",
    # S-01M5C01EAKQACKA27PNH804CR3 — SOURCE UNIQUE des defs d'agents, rendue vers
    # les cinq hotes par `.agents/bin/render_hosts.py` : elle voyage (polarite TAKE,
    # aucune regle dans .template-exclude), l'adoptant re-rend depuis elle.
    "agents": "product",
    # T-01M5C1P67FN2YR9T3R0BHV7M3M — SOURCE UNIQUE des commandes, rendue vers
    # `.claude/commands/` et les miroirs `source-command-*` : elle voyage comme `agents`.
    "commands": "product",
    "conftest.py": "product",
    # T-012 — `docs` reste "product" bien qu'il porte desormais UNE exclusion,
    # `strip: docs/interne/` (les arbitrages de la refonte packaging). "mixed"
    # ne convient pas : cette valeur exige que la part exclue soit de l'ETAT et
    # figure dans STATE_BEARING_PREFIXES, ce que `docs/interne/` n'est pas — ce
    # sont des notes de conception du kit, pas de l'histoire accumulee. La
    # partition n'a pas de valeur pour « mixte dont la part exclue n'est pas de
    # l'etat » ; l'ecart est ECRIT plutot que masque par une etiquette fausse.
    "docs": "product",
    "pytest.ini": "product",
    "retro": "state",
    "runs": "state",                     # T-00000650 — exports « run par auteur »
    # T-012, refonte packaging. Quatre artefacts du chantier, a la racine.
    "checks.manifest.json": "kit-only",  # registre des checks, lu par la release
    "PLAN-ETAT.md": "state",             # etat du chantier — cf. STATE_BEARING_PREFIXES
    "PLAN-ETAT-DETAIL.md": "state",      # meme nature — cf. STATE_BEARING_PREFIXES
    # Ces deux-la VOYAGENT, donc "product" et aucune regle dans .template-exclude :
    # le verrou du contrat est le registre de ce que le kit PROMET, et le
    # CHANGELOG est ce que la politique de version de 0.x exige d'ecrire pour
    # retirer un element. Un adoptant a besoin des deux. `CHANGELOG.md` est
    # classe AVANT d'exister, pour la meme raison que sa regle de classification :
    # une entree absente le jour de la creation rougit la porte au moment ou il
    # faut justement ecrire le fichier.
    # T-012 Phase 1 — LE PAQUET. "product" : c est le kit lui-meme, et il
    # voyage. Aucune regle dans .template-exclude, donc polarite TAKE.
    "src": "product",
    # S-00004099 (ordre pilote) — LE MANIFESTE DE LA DISTRIBUTION NE VOYAGE PAS.
    # "kit-only" et non "product" : `pyproject.toml` declare `cadre-kit`, le
    # produit que CE depot fabrique, et un adoptant ne le fabrique pas
    # (`strip: pyproject.toml`). Pas "state" non plus : il n accumule aucune
    # histoire. `test_every_kit_only_segment_is_actually_stripped` rougit si la
    # regle disparait, et le controle negatif sur sonde fichier le prouve.
    "pyproject.toml": "kit-only",
    # T-00000991 — la commande de release du kit (`scripts/release.sh`) et son
    # point d'entree `make` : ils fabriquent la release de CE depot, un adoptant
    # n'en fabrique pas (`strip: scripts/`, `strip: Makefile`).
    "scripts": "kit-only",
    "Makefile": "kit-only",
    "contract.lock.json": "product",
    "CHANGELOG.md": "product",
    "core-scripts": "product",
    "verifier-agent.md": "product",
    # Notice de licence tierce (MIT d'ECC) et politique de divulgation : elles
    # VOYAGENT, la licence MIT exige que la notice accompagne la copie adaptee.
    "SECURITY.md": "product",
    "THIRD_PARTY_NOTICES.md": "product",
}

# TWO LIMITS, WRITTEN RATHER THAN LEFT TO BE DISCOVERED:
#  1. `tracked_paths()` uses `git ls-files`, which does NOT descend into a git
#     submodule (L-00000231). State committed inside a submodule is invisible to
#     every check in this file.
#  2. The partition keys on the FIRST segment only. A state file created deep
#     under a segment classified "product" — say `docs/state/…` — passes. Closing
#     that would mean classifying every directory, which is the enumeration this
#     design avoids; the partition raises the floor, it does not seal the room.


def top_segment(path: str) -> str:
    """First path segment — the key of the partition above."""
    return path.split("/", 1)[0]


def is_state_bearing(path: str) -> bool:
    """THE NATURE PREDICATE, as a function, so the negative control replays THIS
    rule rather than a re-derivation of it (L-00000057)."""
    return any(path.startswith(prefix) for prefix in STATE_BEARING_PREFIXES)


def travels(path: str, parsed) -> bool:
    """True when this path is copied onto the template branch. `own` paths
    exist only there; `keep`/`strip` never carry main's content over."""
    rule = st.match_rule(path, parsed)
    return rule is None


# Usernames that are placeholders, not people.
_GENERIC_USERS = {
    "dev", "user", "users", "you", "me", "runner", "example", "someone",
    "root", "username", "USERNAME", "home", "test", "ci", "tmp", "your-user",
}
# Reserved-for-documentation domains (RFC 2606 and local test forms).
_DOC_DOMAINS = re.compile(
    r"@(?:[\w-]+\.)?(?:example\.(?:com|org|net)|example|test|test\.local|localhost|invalid)$",
    re.IGNORECASE,
)

_HOME_WIN = re.compile(r"[Cc]:[\\/]{1,2}Users[\\/]{1,2}([A-Za-z0-9._-]+)")
_HOME_POSIX = re.compile(r"/(?:home|Users)/([A-Za-z0-9._-]+)")
_EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")


def _machine_markers(name: str | None = None, home: str | None = None) -> dict[str, str]:
    """Who runs this suite, so the guard is not a hardcoded list that only knows
    yesterday's leak — each marker with the FORM naming someone (S-00002996: `node`,
    `vscode`, `Claude` are also prose): `nom` (git name holding a space or a backslash) anywhere,
    `mot` (one-word git name) in a home path or email, `chemin` (HOME account) in a home path."""
    name = subprocess.run(["git", "-C", str(ROOT), "config", "user.name"], capture_output=True,
                          text=True).stdout.strip() if name is None else name
    home = (os.environ.get("USERPROFILE") or os.environ.get("HOME") or "") if home is None else home
    compte = name.rsplit("\\", 1)[-1]  # Windows `DOMAIN\account`: a home path holds the ACCOUNT
    formes = {Path(home).name if home else "": "chemin", compte: "nom" if " " in compte else "mot",
              name: "nom" if " " in name or "\\" in name else "mot"}  # no `\`: name is compte
    return {m: f for m, f in formes.items() if len(m) > 3 and m.lower() not in _GENERIC_USERS}


def _machine_hits(markers: dict[str, str], text: str) -> list[str]:
    """Each of `markers` found in `text`, in its naming FORM only (bounded path)."""
    hits = [m for m, forme in markers.items() if forme == "nom" and m in text]
    hits += [h.group(0) for p in (_HOME_WIN, _HOME_POSIX) for h in p.finditer(text)
             if markers.get(h.group(1).rstrip(".")) in ("mot", "chemin")]
    return hits + [a for a in _EMAIL.findall(text) if not _DOC_DOMAINS.search(a) and any(
        f == "mot" and m.lower() in a.split("@")[0].lower() for m, f in markers.items())]


def _is_kit_repo() -> bool:
    """The KIT only: in a template-derived tree or a consumer project nothing
    travels, and fixtures legitimately carry emails (measured on Lavande, 2026-08-02).
    Discriminator: the kit marker (T-00000513), `strip:` in `.template-exclude`,
    absent from the wheel — a hand copy carries it (QUICK-SETUP: delete it)."""
    # adopting-tree: the kit marker never travels, its absence IS the adopting tree
    return (ROOT / ".agents" / "IS_THE_KIT").is_file()


class KitDiscriminantTests(unittest.TestCase):
    def test_le_marqueur_du_kit_coincide_avec_le_front_suivi(self):
        """HORS setUp pour pouvoir rougir : l'ancienne sonde `main:.agents/ui-src`
        rendait 128, douze tests éteints. rc 0 exigé : sans git, deux faux égaux."""
        out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "--", ".agents/ui-src"],
                             capture_output=True, text=True)
        self.assertEqual(0, out.returncode, out.stderr)
        self.assertEqual(bool(out.stdout.strip()), _is_kit_repo(),
                         "marqueur et front suivi divergent — kit : restaurer .agents/IS_THE_KIT ; copie : retirer .agents/ui-src/ (QUICK-SETUP § 3)")


class TemplateClassificationTests(unittest.TestCase):
    def setUp(self):
        if not _is_kit_repo():
            self.skipTest("not the kit's repo — nothing travels from here")
        self.parsed = rules()
        self.tracked = tracked_paths()

    def test_no_project_state_travels(self):
        """State must not reach the template — checked by NATURE, over a CLOSED
        PARTITION of the top level (T-00000354).

        WHAT THIS USED TO BE, AND WHY IT WAS THE WRONG ANCHOR. The check was
        `p.startswith(".agents/state/")` and nothing else. `sync_template`'s
        default polarity is TAKE, so any state file created ANYWHERE ELSE reached
        the template with the maintainer repo's content in it — which is exactly
        the exfiltration `strip: .agents/state/` exists to prevent, escaping
        through a path the net did not look at. Good logic, wrong anchor
        (L-00000057): the rule keyed on ONE PATH where the property is a NATURE.
        """
        leaked = [p for p in self.tracked
                  if is_state_bearing(p) and travels(p, self.parsed)]
        self.assertEqual(leaked, [], "project state would be copied onto the template")

    def test_adopting_gate_and_angular_witness_travel(self):
        """The gate, its CI wiring, and both lot witnesses must reach adopters."""
        paths = (
            ".agents/bin/porte_adoptant.py",
            ".agents/bin/test_porte_adoptant_angular.py",
            ".github/workflows/ci.yml",
            ".agents/security/semgrep.yml",
        )
        base = (ROOT / ".template-exclude").read_text(encoding="utf-8")
        for path in paths:
            with self.subTest(path=path):
                self.assertTrue(travels(path, self.parsed), f"{path} would not reach the adopter")
                mutated = st.parse_exclude(base + f"\nstrip: {path}\n")
                self.assertFalse(travels(path, mutated), f"strip: {path} did not change the verdict")

    def test_les_surfaces_java_voyagent_par_take(self):
        """Both Java lots, their witnesses and all resolver defs reach an adopter."""
        paths = (
            ".agents/skills/java-hexagonal-spring/SKILL.md",
            ".claude/skills/java-hexagonal-spring-pointer/SKILL.md",
            ".agents/evals/test_stack_skills_contract.py",
            ".agents/ref/CONVENTIONS_java.md",
            ".agents/ref/DOCS_REGISTRY.md",
            ".agents/evals/test_conventions_contract.py",
            ".agents/evals/test_template_hygiene.py",
            ".claude/agents/skills-resolver.md",
            ".codex/agents/skills-resolver.toml",
            ".gemini/agents/skills-resolver.md",
            ".github/agents/skills-resolver.agent.md",
            ".kimi-code/agents/skills-resolver.md",
        )
        self.assertEqual(len(paths), len(set(paths)), "duplicate Java travel path")
        for path in paths:
            with self.subTest(present=path):
                self.assertTrue((ROOT / path).is_file(), f"missing Java travel surface: {path}")
        self.assertEqual([p for p in paths if not travels(p, self.parsed)], [],
                         "a Java or resolver surface would not reach the adopter")
        self.assertFalse(travels(".agents/IS_THE_KIT", self.parsed),
                         "the kit marker would reach the adopter")
        base = (ROOT / ".template-exclude").read_text(encoding="utf-8")
        for path in paths:
            with self.subTest(strip=path):
                mutant = st.parse_exclude(base + f"\nstrip: {path}\n")
                self.assertFalse(travels(path, mutant), f"strip: {path} did not change TAKE")

    def test_negative_control_a_strip_rule_over_the_skills_would_be_caught(self):
        """THE must_travel ARM MUST BE ABLE TO GO RED (L-00000057), and the
        control is IN-PROCESS rather than a temporary edit of `.template-exclude`:
        mutating a tracked config file to prove a test works leaves a window where
        the repo is wrong, and the shell guard rightly refuses the redirect that
        would do it. Parsing a mutated rule TEXT replays the same `travels()` rule
        with nothing on disk touched.

        The mutation chosen is the realistic one: `strip: .agents/skills/`. It is
        exactly the rule someone would add on the reasoning that skills are
        "state-ish", and it would leave every invariant in the thin router pointing
        at a file the adopter does not have — the router's whole design broken by
        one plausible line.
        """
        mutated = st.parse_exclude(
            (ROOT / ".template-exclude").read_text(encoding="utf-8")
            + os.linesep.join(["", "strip: .agents/skills/", ""])
        )
        probe = ".agents/skills/task-board/SKILL.md"
        self.assertTrue(
            travels(probe, self.parsed),
            "base not green: the skill does not travel under the REAL rules, so the "
            "control below would prove nothing",
        )
        self.assertFalse(
            travels(probe, mutated),
            "THE RULE DOES NOT BITE: a `strip: .agents/skills/` rule still let the "
            "skill travel, so the must_travel arm cannot detect the one mutation that "
            "would silently gut the thin router.",
        )

    def test_vendor_voyage_sans_marqueur(self):
        """The tracked engine travels from either layout; kit identity does not."""
        engines = ("agentic_v3/__init__.py", ".agents/vendor/agentic_v3/__init__.py")
        present = [path for path in engines if path in self.tracked]
        self.assertTrue(present, "aucun moteur suivi par Git")
        self.assertEqual([path for path in present if not travels(path, self.parsed)], [])
        for path in engines:  # `travels` juge une chaîne : l'emplacement non suivi est jugé aussi
            self.assertTrue(travels(path, self.parsed), f"{path} ne voyagerait pas")
        marker = ".agents/IS_THE_KIT"
        self.assertIn(marker, self.tracked)
        self.assertFalse(travels(marker, self.parsed), "le marqueur voyagerait chez l'adoptant")
        guide = (ROOT / "README.md").read_text(encoding="utf-8")
        for path in ("`agentic_v3/`", "`.agents/vendor/agentic_v3/`"):  # délimités : l'un n'est plus contenu dans l'autre
            self.assertIn(path, guide, f"README ne nomme pas le moteur sous {path}")
        mutated = st.parse_exclude((ROOT / ".template-exclude").read_text(encoding="utf-8")
                                   + "\nstrip: .agents/vendor/agentic_v3/\n")
        self.assertFalse(travels(engines[1], mutated), "un strip du vendor ne mord pas")

    def test_v3_auto_sync_voyage_chez_adoptant(self):
        """Moteur et défs par TAKE ; graine par SEED, marqueur kit exclu."""
        chemins = (
            ".agents/vendor/agentic_v3/db/event_store.py", ".agents/vendor/agentic_v3/db/event_store_sync.py",
            ".agents/vendor/agentic_v3/db/event_store_annonces.py", ".agents/vendor/agentic_v3/db/run_export.py",
            ".claude/agents/orchestrator.md", ".codex/agents/orchestrator.toml",
            ".gemini/agents/orchestrator.md", ".github/agents/orchestrator.agent.md",
            ".kimi-code/agents/orchestrator.md", ".agents/skills/task-board/SKILL.md",
        )
        self.assertEqual([p for p in chemins if p not in self.tracked], [], "source non suivie")
        self.assertEqual([p for p in chemins if not travels(p, self.parsed)], [], "sync absente chez adoptant")
        self.assertFalse(travels(".agents/IS_THE_KIT", self.parsed))
        graine = ".agents/adopter-seed/gates/PLAN_CHAIN_REQUIRED"
        self.assertIn(graine, self.tracked)
        self.assertFalse(travels(graine, self.parsed))
        self.assertEqual(st.seed_targets({graine}),
                         {".agents/state/gates/PLAN_CHAIN_REQUIRED": graine})
        self.assertFalse(travels("runs/exemple/copie/2026-10.jsonl", self.parsed))
        base = (ROOT / ".template-exclude").read_text(encoding="utf-8")
        for p in chemins:
            with self.subTest(strip=p):
                mutant = st.parse_exclude(base + f"\nstrip: {p}\n")
                self.assertFalse(travels(p, mutant), f"strip: {p} ne mord pas")

    def test_notice_jira_et_manifeste_adoptant(self):
        """La notice voyage ; le manifeste de la wheel appartient au kit."""
        notice = ".agents/ref/JIRA_CONNECTOR.md"
        self.assertIn(notice, self.tracked, "notice Jira non suivie par Git")
        self.assertTrue(travels(notice, self.parsed), "notice Jira absente chez l'adoptant")
        contenu = (ROOT / notice).read_text(encoding="utf-8")
        for terme in ("CADRE_JIRA_SITE", "CADRE_JIRA_EMAIL", "JIRA_API_TOKEN",
                      "cadre-jira", "JIRA_AGENT_CLAIM=0", "--dry-run",
                      "/rest/api/3/search/jql", "localhost"):
            with self.subTest(terme=terme):
                self.assertIn(terme, contenu)
        self.assertFalse(travels("pyproject.toml", self.parsed),
                         "le manifeste de distribution du kit voyagerait")

    def test_connecteur_jira_et_banc_voyagent(self):
        """Les sources et le banc doivent exister et passer le filtre TAKE."""
        chemins = (
            ".agents/bin/tasks_jira.py",
            ".agents/bin/tracabilite_jira.py",
            ".agents/bin/etat_lecture.py",
            ".agents/bin/ledger.py",
            ".agents/bin/test_tasks_jira.py",
            ".agents/ref/JIRA_CONNECTOR.md",
            ".agents/evals/test_template_hygiene.py",
        )
        self.assertEqual([p for p in chemins if p not in self.tracked], [],
                         "source ou banc Jira absent : TAKE ne prouverait rien")
        self.assertEqual([p for p in chemins if not travels(p, self.parsed)], [],
                         "source ou banc Jira exclu du modèle adoptant")
        base = (ROOT / ".template-exclude").read_text(encoding="utf-8")
        for chemin in chemins:
            with self.subTest(strip=chemin):
                mutant = st.parse_exclude(base + f"\nstrip: {chemin}\n")
                self.assertFalse(travels(chemin, mutant),
                                 f"strip: {chemin} ne modifie pas le voyage")

    def test_verbes_jira_du_contrat_voyagent(self):
        """Un verbe omis du contrat rend le témoin rouge."""
        chemin = ".agents/ref/TASKS_CLI_CONTRACT.json"
        self.assertIn(chemin, self.tracked, "contrat CLI non suivi par Git")
        self.assertTrue(travels(chemin, self.parsed), "contrat CLI absent chez l'adoptant")
        verbes = json.loads((ROOT / chemin).read_text(encoding="utf-8"))["verbes"]
        for verbe in ("jira-import", "jira-claim"):
            with self.subTest(verbe=verbe):
                self.assertTrue(verbe in verbes, f"{verbe} omis du contrat CLI")
                self.assertEqual(verbes[verbe]["statut"], "noyau")

    # T-01M57F1AG0DYF5QJ8YXNV76RTR (S-01M57F5ST : toute optimisation de la
    # planification voyage chez l'adoptant). Les 37 chemins des lots A-F et de
    # l'intégration — défs des cinq hôtes et rosters, bancs, doctrine, grille,
    # apply-mode, skill planning — voyagent par TAKE, chacun. Le banc de contrat
    # de la route de dev locale, retiré avec elle, y est remplacé par
    # test_effort_devs, qui en reçoit les trois cas de planification
    # (T-01M5PCCHMWXTRCM5QJT8J5KNEH) : la population reste à 37.
    PLANIFICATION_TAKE = population_planification()

    def test_vendor_seul_m(self):
        """Lot M of T-01M5BXTPQE3JZV3KZA6WD9P5XC: the roster of the population follows the `cadre`
        package — new place alone, old place alone, both (the new one wins). Kills a roster
        path written by hand (`src/cadre/data/roster` in the vendor-only tree)."""
        cas = {"vendor": ((VP.VENDOR / "cadre",), ".agents/vendor/cadre"),
               "ancien": ((VP.ANCIENS["cadre"],), "src/cadre"),
               "les deux": ((VP.VENDOR / "cadre", VP.ANCIENS["cadre"]), ".agents/vendor/cadre")}
        for nom, (lieux, attendu) in cas.items():
            with self.subTest(disposition=nom), tempfile.TemporaryDirectory() as tmp:
                for lieu in lieux:
                    (Path(tmp) / lieu).mkdir(parents=True)
                    (Path(tmp) / lieu / "__init__.py").write_text("", encoding="utf-8")
                rosters = [p for p in population_planification(Path(tmp)) if p.endswith(".json")]
                self.assertEqual(len(rosters), 4)
                self.assertEqual([p for p in rosters if not p.startswith(attendu + "/data/roster/")], [])
        self.assertEqual([p for p in self.PLANIFICATION_TAKE if p.endswith(".json")],
                         [p for p in population_planification(ROOT) if p.endswith(".json")])
        self.assertIn(f"{cadre_rel()}/data/roster/planner.json", self.tracked,
                      "the roster is not tracked where the cadre package lives")

    def test_planification_et_routeur_voyagent_par_take(self):
        paths = self.PLANIFICATION_TAKE
        self.assertEqual((len(paths), len(set(paths))), (37, 37), "the declared population moved")
        absent = [p for p in paths if p not in self.tracked]
        self.assertEqual(absent, [], "a path of the population is not tracked: TAKE would prove nothing")
        blocked = [p for p in paths if not travels(p, self.parsed)]
        self.assertEqual(blocked, [], "a planning optimisation would not reach the adopter")
        base = (ROOT / ".template-exclude").read_text(encoding="utf-8")
        for p in paths:
            with self.subTest(mutant=p):
                mutated = st.parse_exclude(base + os.linesep.join(["", f"strip: {p}", ""]))
                self.assertFalse(travels(p, mutated), f"a `strip: {p}` rule does not bite")

    # T-01M5F729719KX08RQQCVS1PX0T (S-01M57F5ST) : la doctrine multi-poste de la nuit et du miroir
    # Copilot — running étrangers préservés, portée de revue déclarée avant le critique — voyage
    # par TAKE avec son banc, et chaque surface de doctrine qui voyage PORTE la portée.
    MULTI_POSTE_TAKE = (".agents/skills/night/SKILL.md", ".claude/commands/night.md",
                        ".github/copilot-instructions.md", ".agents/evals/test_night_contract.py")

    def test_portee_multi_poste_voyage_par_take(self):
        paths = self.MULTI_POSTE_TAKE
        self.assertEqual([p for p in paths if p not in self.tracked], [], "untracked: TAKE would prove nothing")
        self.assertEqual([p for p in paths if not travels(p, self.parsed)], [],
                         "the multi-poste doctrine would not reach the adopter")
        for p in paths[:3]:
            self.assertIn("review-scope", (ROOT / p).read_text(encoding="utf-8"),
                          f"{p} travels without the review scope")
        base = (ROOT / ".template-exclude").read_text(encoding="utf-8")
        for p in paths:
            with self.subTest(mutant=p):
                mutated = st.parse_exclude(base + os.linesep.join(["", f"strip: {p}", ""]))
                self.assertFalse(travels(p, mutated), f"a `strip: {p}` rule does not bite")

    def test_git_claim_travels(self):
        """The claim reader, its doctrine, launchers and five host defs reach adopters.

        These are TAKE paths; gate markers instead use the separately tested
        SEED channel. A `strip:` mutant for EACH path must turn this witness red.
        """
        paths = (
            ".agents/bin/tasks.py",
            ".agents/bin/tasks_requetes.py",
            ".agents/bin/tasks_fournee.py",
            ".agents/bin/tasks_cli.py",
            ".agents/skills/task-board/SKILL.md",
            ".agents/skills/kickoff/SKILL.md",
            ".agents/skills/night/SKILL.md",
            ".agents/skills/context-retro/SKILL.md",
            ".agents/skills/planning/SKILL.md",
            "AGENTS.md",
            ".github/copilot-instructions.md",
            ".claude/commands/night.md",
            ".claude/commands/kickoff.md",
            ".claude/agents/orchestrator.md",
            ".codex/agents/orchestrator.toml",
            ".gemini/agents/orchestrator.md",
            ".github/agents/orchestrator.agent.md",
            ".kimi-code/agents/orchestrator.md",
        )
        self.assertEqual([p for p in paths if p not in self.tracked], [],
                         "a claim channel is untracked: TAKE would prove nothing")
        base = (ROOT / ".template-exclude").read_text(encoding="utf-8")
        for path in paths:
            with self.subTest(path=path):
                self.assertTrue(travels(path, self.parsed),
                                f"Git claim channel would not reach the adopter: {path}")
                mutant = st.parse_exclude(base + f"\nstrip: {path}\n")
                self.assertFalse(travels(path, mutant),
                                 f"strip mutant does not bite: {path}")
        fusion_no_ff = {
            "AGENTS.md": "une sortie `done` fusionnée en `--no-ff` sur l'upstream",
            ".github/copilot-instructions.md": "A `done` exit merged with `--no-ff` on the upstream",
            ".agents/skills/task-board/SKILL.md": "Une sortie fusionnée en `--no-ff` est reconnue",
            ".agents/skills/kickoff/SKILL.md": "a `done` exit merged with `--no-ff`",
        }
        for path, phrase in fusion_no_ff.items():
            with self.subTest(doctrine=path):
                doctrine = (ROOT / path).read_text(encoding="utf-8")
                self.assertIn("REVENDICATION", doctrine)
                self.assertIn("--sans-revendication", doctrine)
                self.assertIn(phrase, doctrine)
        router = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        skill = (ROOT / ".agents/skills/task-board/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("le lanceur saute la tâche et rapporte le refus, y compris", router)
        self.assertIn("**BORNES DE LA PREUVE.**", skill)
        self.assertIn("Une sortie fusionnée en `--no-ff` est reconnue", skill)

    def test_task_ownership_doctrine_travels_with_measured_host_bound(self):
        """Every lot E surface tells the pilot what the transfer guard can prove."""
        copilot_fr = ("Copilot CLI pose `COPILOT_AGENT_SESSION_ID` et `COPILOT_CLI` dans le shell de "
                      "l'agent (mesuré, 1.0.96) : ce marqueur refuse la reprise")
        copilot_en = ("Copilot CLI sets `COPILOT_AGENT_SESSION_ID` and `COPILOT_CLI` in the agent shell "
                      "(measured, 1.0.96): that marker refuses the transfer")
        ancienne_fr = "Codex, Gemini, Copilot et Kimi sans marqueur"
        ancienne_en = "Codex, Gemini, Copilot and Kimi without that marker"
        expected = {
            "AGENTS.md": ("terminal interactif (TTY)", "saisie exacte", "Un agent ne reprend jamais",
                          "Codex, Gemini et Kimi sans marqueur", copilot_fr,
                          "TTY + saisie en une commande", "REFUSÉE"),
            ".agents/skills/task-board/SKILL.md": (
                "terminal interactif (TTY)", "saisie exacte", "Un agent ne reprend jamais",
                "Codex, Gemini et Kimi sans marqueur", copilot_fr, "TTY + saisie en une commande", "REFUSÉE"),
            ".agents/skills/kickoff/SKILL.md": (
                "interactive stdin and stderr (TTY)", "exact entry", "An agent never takes ownership",
                "Codex, Gemini and Kimi without that marker", copilot_en,
                "TTY + confirmation in one command", "refused"),
        }
        for path, phrases in expected.items():
            with self.subTest(path=path):
                self.assertIn(path, self.tracked)
                self.assertTrue(travels(path, self.parsed))
                doctrine = " ".join((ROOT / path).read_text(encoding="utf-8").split())
                for phrase in (*phrases, "AGENTS_HOOK_HOST", "Claude Code", "--reprise",
                               "--sans-revendication", "--no-ff", "COPILOT_CLI` est hérité"
                               if path != ".agents/skills/kickoff/SKILL.md" else "COPILOT_CLI` is inherited"):
                    self.assertIn(phrase, doctrine, f"{path}: missing ownership bound {phrase}")
                for ancienne in (ancienne_fr, ancienne_en):
                    self.assertNotIn(ancienne, doctrine,
                                     f"{path}: Copilot sets an agent marker (1.0.96); old bound {ancienne!r} is false")
                self.assertIn("(Codex, Kimi, Copilot)", doctrine,
                              f"{path}: marker hooks must be scoped to measured hosts")

    def test_every_top_level_segment_is_classified(self):
        """THE CLOSED PROPERTY, and the reason this is a partition rather than a
        list of known state files.

        A list of state paths would be an enumeration under a universal title —
        true the day it is written, false at the next directory (L-00000187). A
        PARTITION of the top level cannot go quietly stale: a new top-level
        segment is UNCLASSIFIED, and unclassified is a loud failure carrying the
        remedy. The population is small enough for this to be honest — measured
        at the time of writing: 604 tracked paths, 25 top-level segments — and the
        noise is bounded to the moment a genuinely new top-level thing appears,
        which is precisely when the travel decision needs making.
        """
        seen = {top_segment(p) for p in self.tracked}
        unclassified = sorted(seen - set(TOP_LEVEL_CLASSIFICATION))
        self.assertEqual(
            unclassified, [],
            "top-level segment(s) tracked but NOT classified for template travel: "
            f"{unclassified}. Add each to TOP_LEVEL_CLASSIFICATION as 'product' "
            "(it is part of the kit and travels), 'state' (it accumulates this "
            "repo's own history and must be stripped — then add a `strip:` rule to "
            ".template-exclude and a prefix to STATE_BEARING_PREFIXES), or 'mixed' "
            "(it holds both, and the state part needs its own prefix) or 'kit-only' "
            "(it belongs to this repo and must be stripped WITHOUT being state — "
            "then add a `strip:` rule to .template-exclude). Refusing to "
            "guess is the point: the default polarity of sync_template is TAKE, so "
            "an unclassified directory TRAVELS.",
        )
        # NON-VACUITY (L-00000232): a sweep over an empty tracked set would also
        # report nothing unclassified.
        self.assertGreater(
            len(seen), 10,
            "the tracked-path sweep found almost nothing — it is measuring an empty "
            "population, so its green says nothing about template hygiene",
        )

    def test_every_declared_state_prefix_is_actually_stripped(self):
        """A prefix nobody strips is a certification with no effect. Each entry of
        STATE_BEARING_PREFIXES must be matched by a rule in `.template-exclude`,
        or the list above merely LOOKS like protection.
        """
        for prefix in STATE_BEARING_PREFIXES:
            # LA SONDE SUIT LA FORME DU PREFIXE (T-012). `Rule.matches` fait du
            # prefixe pour une regle qui finit par "/" et de l'EGALITE STRICTE
            # sinon — c'est ecrit en tete de `.template-exclude` (« directory
            # rules MUST end in "/" »). Une sonde `f"{prefix}__probe__"` appliquee
            # a une entree FICHIER (`PLAN-ETAT.md`) fabrique donc un chemin
            # qu'aucune regle ne peut couvrir, et le banc rougit sur une
            # protection qui existe pourtant. Le probe d'un repertoire reste un
            # enfant synthetique ; celui d'un fichier est le fichier lui-meme.
            probe = f"{prefix}__probe__" if prefix.endswith("/") else prefix
            self.assertFalse(
                travels(probe, self.parsed),
                f"{prefix!r} is declared state-bearing but `.template-exclude` lets "
                f"{probe} travel — add a `strip: {prefix}` rule, or remove the prefix "
                "from STATE_BEARING_PREFIXES and stop claiming it is protected",
            )

    def test_every_kit_only_segment_is_actually_stripped(self):
        """Meme discipline que pour les prefixes d etat : une etiquette que rien
        n applique est une certification sans effet. Un segment classe `kit-only`
        qui VOYAGERAIT serait le pire des deux mondes — non protege par
        `is_state_bearing` (il n est pas de l etat) et pourtant expedie chez un
        adoptant, alors que la partition affirme le contraire.
        """
        kit_only = sorted(k for k, v in TOP_LEVEL_CLASSIFICATION.items() if v == "kit-only")
        # NON-VACUITE : une categorie vide passerait cette boucle en silence.
        self.assertTrue(
            kit_only,
            "aucun segment `kit-only` : si la categorie n a plus de membre, retirez-la "
            "du vocabulaire plutot que de garder une boucle qui ne parcourt rien",
        )
        # LA SONDE SUIT LA FORME DU SEGMENT (T-012), meme raison qu'au-dessus :
        # un segment de tete peut etre un FICHIER (`checks.manifest.json`, comme
        # `TEMPLATE.md` l'est deja pour `template-only`), et `Rule.matches` exige
        # alors l'egalite stricte. Sonder `checks.manifest.json/__probe__`
        # fabriquerait un chemin qu'aucune regle ne peut couvrir.
        tracked_dirs = {p.split("/", 1)[0] for p in self.tracked if "/" in p}
        for segment in kit_only:
            probe = f"{segment}/__probe__" if segment in tracked_dirs else segment
            remedy = f"strip: {segment}/" if segment in tracked_dirs else f"strip: {segment}"
            self.assertFalse(
                travels(probe, self.parsed),
                f"{segment!r} est classe `kit-only` mais `.template-exclude` laisse "
                f"{probe} voyager — ajoutez une regle `{remedy}`, ou reclassez "
                "le segment et cessez d affirmer qu il ne part pas",
            )

    def test_negative_control_une_sonde_fichier_sait_encore_rougir(self):
        """LA SONDE FICHIER DOIT POUVOIR ALLER AU ROUGE (L-00000057, T-012).

        Les deux boucles ci-dessus sondent desormais un segment FICHIER par
        lui-meme plutot que par un enfant synthetique. Une sonde qui ne peut plus
        echouer certifierait `checks.manifest.json` et `PLAN-ETAT.md` proteges
        quoi qu'il arrive. Le controle est IN-PROCESS — on reparse un TEXTE de
        regles ampute, rien n'est touche sur disque — exactement comme le
        controle des skills plus haut.
        """
        reel = (ROOT / ".template-exclude").read_text(encoding="utf-8")
        # `pyproject.toml` (S-00004099) : le temoin qui rougit s'il repart.
        for cible in ("checks.manifest.json", "PLAN-ETAT.md", "pyproject.toml"):
            self.assertFalse(
                travels(cible, self.parsed),
                f"base pas verte : {cible} voyage sous les VRAIES regles, donc le "
                "controle ci-dessous ne prouverait rien",
            )
            ampute = st.parse_exclude(
                os.linesep.join(
                    ligne for ligne in reel.splitlines()
                    if ligne.strip() != f"strip: {cible}"
                )
            )
            self.assertTrue(
                travels(cible, ampute),
                f"LA REGLE NE MORD PAS : privee de sa ligne `strip: {cible}`, la "
                "configuration laisse toujours le fichier immobile — la sonde "
                "fichier est vide et ne prouve rien.",
            )

    def test_negative_control_the_old_path_anchored_rule_accepted_state_outside_agents_state(self):
        """THE GAP IS MEASURED HERE, NOT ASSERTED.

        The old rule is re-implemented verbatim below and replayed on synthetic
        state paths that live OUTSIDE `.agents/state/`. The point is not that the
        new rule refuses them — that alone would be a tautology — but that the OLD
        rule ACCEPTED them. Without this contrast the widening reads as a
        preference; with it, it is a defect that was there.
        """
        def old_rule(path: str) -> bool:
            # verbatim, as it stood before T-00000354
            return path.startswith(".agents/state/")

        offenders = [
            "retro/LESSONS.md",            # the case the P3 planner actually found
            ".gemini/backups/session.jsonl",
        ]
        for path in offenders:
            self.assertTrue(
                is_state_bearing(path),
                f"the new rule does not recognise {path} as state — the prefix list "
                "has drifted from what it claims to cover",
            )
            self.assertFalse(
                old_rule(path),
                f"the old rule already caught {path}, so this control proves nothing "
                "about the widening — pick a case the old anchor really missed",
            )
        # And prove the pair is not vacuous in the other direction: the case the
        # OLD rule did catch must still be caught.
        self.assertTrue(old_rule(".agents/state/board/TASKS.json"))
        self.assertTrue(is_state_bearing(".agents/state/board/TASKS.json"))

    def test_the_dashboard_artefacts_do_travel(self):
        # The failure this pins is the opposite one: a future strip rule that
        # accidentally widens and leaves consumers a kit without its dashboard.
        must_travel = [
            ".agents/bin/dashboard.py",
            ".agents/bin/dashboard_daemon.py",
            ".agents/bin/dashboard_readers.py",
            ".agents/bin/events.py",
            ".agents/ui/index.html",
            ".agents/ui/app.js",
            ".agents/ui/views/board.js",
            ".claude/commands/dash.md",
            ".gitattributes",
            # T-00000343 (P6): the three artefacts the routeur-mince chantier
            # produced that an adopter is USELESS without, each named because the
            # default polarity is TAKE and a future `strip:` rule could widen over
            # any of them silently.
            #
            #  * the portable verifier prompt — the cross-host form of exec-critic's
            #    contract, and the only form available on a host with no
            #    Claude-style agent def;
            #  * the LESSONS consolidator — `retro/` itself is STRIPPED (it is this
            #    repo's own history), so the TOOL must travel even though its DATA
            #    must not. That asymmetry is exactly the kind a single `strip:` rule
            #    gets wrong, which is why it is pinned rather than assumed;
            #  * one skill CREATED by P4, as a witness that the new
            #    `.agents/skills/*/SKILL.md` family travels at all — without it a
            #    rule stripping `.agents/skills/` would leave every invariant in the
            #    thin router pointing at a file the adopter does not have.
            "verifier-agent.md",
            ".agents/bin/retro.py",
            ".agents/skills/task-board/SKILL.md",
            # T-00001051: the five parts of the `dashboard_readers.py` façade (its closed
            # `PARTIES` list). Without any one of them the façade does not load, and the
            # adopter's dashboard has no view at all.
            ".agents/bin/dashboard_readers_base.py",
            ".agents/bin/dashboard_readers_coverage_mcp.py",
            ".agents/bin/dashboard_readers_governance.py",
            ".agents/bin/dashboard_readers_security.py",
            ".agents/bin/dashboard_readers_memory.py",
            # T-01M4XKCTGEW9MDAYNCBK6R7SD9 and T-01M4XR9ESWKJ8G545AJBJQNC7Q: two modules `dashboard.py` loads at
            # import (the access handoff, the `/api/snapshot` transport) — without either it does not start.
            ".agents/bin/dashboard_handoff.py",
            ".agents/bin/dashboard_transport.py",
            # T-01M4XZWZ9C0ZFVXN3MFSFY1G5V (lot T): the station-load verdict every launcher calls before a
            # wave, and its contract — without either the adopter's launchers cite a tool it does not have.
            ".agents/bin/charge_poste.py",
            ".agents/ref/CHARGE_POSTE.md",
            # T-01M51Q7GJ1B6315SFKNDAAE2P0 (SQLite base, lots C and D): `dashboard.py` loads the paginated
            # routes at import, and they load the derived base's module at theirs (`_etat`) — without either
            # the adopter's dashboard does not start.
            ".agents/bin/etat_projection.py",
            ".agents/bin/dashboard_routes_etat.py",
        ]
        for rel in must_travel:
            if rel not in self.tracked:
                continue  # not landed yet on this branch — not this test's business
            self.assertTrue(travels(rel, self.parsed), f"{rel} would not reach the template")

    def test_codex_dev_seul_preapprouve_et_voyage(self):
        """T-01M5PTFPBDBXE3KMZNHP5DE31A (S-01M5Q52QHWWC0YTFFK39EEH3EG) : seul le lanceur vérifié est
        pré-approuvé — la règle exacte une fois, aucune règle Bash large ni `Bash(codex…` — et la règle,
        le lanceur et son banc voyagent. Mutants en mémoire : chacun doit rougir."""
        settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
        allow = settings["permissions"]["allow"]
        self.assertEqual([], defauts_regle_codex(allow), "règle du lanceur Codex")
        mutants = {
            "règle retirée": [r for r in allow if r != REGLE_CODEX_DEV],
            "règle doublée": allow + [REGLE_CODEX_DEV],
            "règle élargie": [r.replace(" *)", "*)") if r == REGLE_CODEX_DEV else r for r in allow],
        }
        mutants.update({f"ajout {large}": allow + [large] for large in REGLES_BASH_LARGES})
        mutants["ajout Bash(codex exec *)"] = allow + ["Bash(codex exec *)"]
        mutants["ajout Bash(codex:*)"] = allow + ["Bash(codex:*)"]
        for large in ("Bash(bash .agents/bin/codex-dev.sh*)", "Bash(bash .agents/bin/*)", "Bash(bash .agents/*)"):
            mutants[f"ajout {large}"] = allow + [large]
        for nom, muté in mutants.items():
            with self.subTest(mutant=nom):
                self.assertNotEqual([], defauts_regle_codex(muté), f"le mutant « {nom} » ne rougit pas")
        base = (ROOT / ".template-exclude").read_text(encoding="utf-8")
        for path in (".claude/settings.json", ".agents/bin/codex-dev.sh", ".agents/bin/codex-dev.test.sh"):
            with self.subTest(path=path):
                self.assertTrue(travels(path, self.parsed), f"{path} n'atteindrait pas l'adoptant")
                muté = st.parse_exclude(base + f"\nstrip: {path}\n")
                self.assertFalse(travels(path, muté), f"strip: {path} ne change pas le verdict")


# T-01M5PTFPBDBXE3KMZNHP5DE31A : la seule pré-approbation qui lance Codex, et les règles Bash qui la rendraient vaine.
REGLE_CODEX_DEV = "Bash(bash .agents/bin/codex-dev.sh *)"
REGLES_BASH_LARGES = ("Bash", "Bash(*)", "Bash(bash *)", "Bash(bash:*)")


def defauts_regle_codex(allow: list[str]) -> list[str]:
    """Les fautes de la liste `allow` au regard du lanceur Codex ; vide si elle est conforme."""
    f = []
    if allow.count(REGLE_CODEX_DEV) != 1:
        f.append(f"{REGLE_CODEX_DEV} présente {allow.count(REGLE_CODEX_DEV)} fois, une exigée")
    f += [f"règle Bash large : {r}" for r in allow if r in REGLES_BASH_LARGES]
    f += [f"Codex pré-approuvé hors lanceur : {r}" for r in allow if r.startswith("Bash(codex")]
    for r in allow:
        if r == REGLE_CODEX_DEV or not (r.startswith("Bash(") and r.endswith(")")):
            continue
        motif = r[5:-1]
        if "*" not in motif:
            continue
        tete = motif[:-2] if motif.endswith(":*") and "*" not in motif[:-2] else motif.split("*", 1)[0]
        if "bash .agents/bin/codex-dev.sh".startswith(tete):
            f.append(f"règle qui couvre aussi le lanceur : {r}")
    return f


class TravellingIdentityTests(unittest.TestCase):
    """No concrete identity in anything copied to the distributable branch."""

    def setUp(self):
        if not _is_kit_repo():
            self.skipTest("not the kit's repo — nothing travels from here")
        self.parsed = rules()
        self.files = identity_scan_paths(tracked_paths(), self.parsed)
        self.assertGreater(len(self.files), 50, "sanity: the travelling set looks empty")

    def _read(self, rel: str) -> str | None:
        try:
            return (ROOT / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None  # binary or unreadable: nothing textual to leak

    def test_no_home_directory_with_a_real_username(self):
        offenders: list[str] = []
        for rel in self.files:
            text = self._read(rel)
            if text is None:
                continue
            for pattern in (_HOME_WIN, _HOME_POSIX):
                for match in pattern.finditer(text):
                    who = match.group(1)
                    if who.lower() in _GENERIC_USERS or set(who) <= {".", "_", "-"}:
                        continue  # a path SHAPE in prose, not a person
                    offenders.append(f"{rel}: {match.group(0)}")
        self.assertEqual(offenders, [], "home directories naming a real user would travel")

    def test_no_real_email_address(self):
        offenders: list[str] = []
        for rel in self.files:
            text = self._read(rel)
            if text is None:
                continue
            for match in _EMAIL.finditer(text):
                address = match.group(0)
                if _DOC_DOMAINS.search(address):
                    continue
                offenders.append(f"{rel}: {address}")
        self.assertEqual(offenders, [], "real email addresses would travel")

    def test_source_suivie_porteuse_d_email_rougit(self):
        source = ".agents/adopter-docs/README.md"
        parsed = st.parse_exclude("strip: .agents/adopter-docs/\n")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / source
            path.parent.mkdir(parents=True)
            identity = "jean.dupont" + "@" + "groupeonepoint.fr"
            path.write_text(identity + "\n", encoding="utf-8")
            selected = identity_scan_paths([source], parsed)
            offenders = [match.group(0) for rel in selected
                         for match in _EMAIL.finditer((root / rel).read_text(encoding="utf-8"))
                         if not _DOC_DOMAINS.search(match.group(0))]
        self.assertEqual(selected, [source])
        self.assertEqual(offenders, [identity])

    def test_no_marker_of_the_machine_running_this_suite(self):
        """Seul le bras `nom` ajoute une détection ; `chemin`/`mot` doublent les deux tests voisins ;
        `<compte>@hôte` sans TLD et `~<compte>` ne sont plus détectés (S-00002996)."""
        markers = _machine_markers()
        if not markers:
            self.skipTest("no usable machine marker (generic git user and home)")
        offenders = [f"{rel}: contains {hit!r}" for rel in self.files
                     for hit in _machine_hits(markers, self._read(rel) or "")]
        self.assertEqual(offenders, [], "this machine's identity would travel")

    def test_the_guard_can_actually_fail(self):
        """Negative control: the same scan over a planted string must trip.
        Without this, a regex that silently stops matching reads as success.

        The planted values are ASSEMBLED at runtime on purpose. Written as
        literals they would be found by this very suite scanning its own source
        — which is not a false positive, it is the guard working: a file that
        travels must not contain a home path naming someone, not even as an
        example. This test found that in its own first version."""
        who = "jd" + "oe"
        planted = f'provenance = "C:\\Users\\{who}\\Projects\\acme"'
        found = [m.group(1) for m in _HOME_WIN.finditer(planted)]
        self.assertEqual(found, [who], "the home-directory pattern no longer matches")
        real_domain_address = "someone@" + "realcompany" + ".fr"
        self.assertFalse(_DOC_DOMAINS.search(real_domain_address),
                         "a real domain must not be treated as documentation")
        self.assertTrue(_DOC_DOMAINS.search("someone@" + "example.com"),
                        "documentation domains must stay exempt")
        home, dom, plein, domaine = ("/home/" + "vscode", "@" + "corp.fr", "Ada" + " Lovelace",
                                     "AC" + "ME\\jd" + "upont")
        mots = _machine_markers(name="Claude", home=home)  # S-00002996: prose never counts
        self.assertEqual(_machine_hits(mots, f"cd {home}/p {home}x the vscode editor, Claude"), [home])
        self.assertEqual(_machine_hits(mots, f"vscode{dom} claude{dom}"), [f"claude{dom}"])
        self.assertEqual(_machine_hits(_machine_markers(name=plein, home=""), plein), [plein])
        self.assertEqual(_machine_hits(_machine_markers(name=domaine, home=""), domaine), [domaine])
        self.assertEqual(_machine_hits(_machine_markers(name="CO" + "RP\\" + plein, home=""), plein), [plein])


# ---------------------------------------------------------------------------
# THE TRAVELLING STATION-LOAD CONTRACT (T-01M56Q23NHTEXES5CAT0A03TFJ, lot B)
# ---------------------------------------------------------------------------
CONTRAT_CHARGE = ".agents/ref/CHARGE_POSTE.md"

# Clauses the contract MUST state, per section (whitespace collapsed: the Markdown wraps).
CONTRAT_ANCRES = {
    2: (
        "`BASE` imprime la base EFFECTIVE de ce verdict, celle du § 3 à la charge mesurée : sur 18 cœurs, "
        "9 au repos et 5 hors repos",
    ),
    3: (
        "au repos** (charges 1 ET 5 min < C/4, strict), BASE = max(min(5, PLAFOND), min(PLAFOND, ⌊C/2⌋))",
        "ailleurs BASE = min(5, PLAFOND)",
        "LIBRE = PLAFOND − ACTIFS − TENU",
        "ACTIFS = 0 ⇒ PEUT_AJOUTER = max(0, min(BASE, LIBRE))",
        "ACTIFS > 0 et charges 1 min ET 5 min < 2C/3 (strict) ⇒ PEUT_AJOUTER = max(0, LIBRE)",
        "À l'égalité 2C/3, 0",
        "Ni ce repli ni celui de l'état non inscriptible ne lisent TENU (§ 7)",
        "Sans TENU, à ACTIFS = 0 hors surcharge PRÉSENTE, PEUT_AJOUTER ≥ 1",
        "au repos 3/3, BASE = 9 et premier départ 9",
        "à 5,05/5,05 (hors repos, BASE = 5) avec ACTIFS = 5 et TENU = 0, accord 7",
        "à 11,99/11,99, accord 7",
        "à 11,99/12,00, accord 0",
        "à 12,01 en 1 min, accord 0 et DOIT_REDESCENDRE_A = 5 (modérée",
        "à 18,00, encore 5 ; à 18,01 ou PRESSION 4, DOIT_REDESCENDRE_A = 3 (sévère)",
        "C = 8 : PLAFOND 5, BASE 5. C = 6 : PLAFOND 4, BASE 4. C = 4 : PLAFOND 2, BASE 2. C = 1 : 1.",
        "PEUT_AJOUTER = 9 : les deux revues partent ensemble, budget 7",
    ),
    4: (
        "accordés, CLAUDE_PID, tenu)",
        "Chaque relevé porte les champs `claude_pid` (`null` pour un appelant anonyme) et `tenu` "
        "(le TENU lu à ce verdict)",
        "Un PID invérifiable (Windows) est SUPPOSÉ vivant",
        "un ancien relevé sans `tenu`, ou un `tenu` invalide, vaut 0",
        "RETENUE_S = 300 s",
        "+ accords anonymes de moins de 300 s + max(0, accords propres de moins de 300 s − ACTIFS)",
        "appelant anonyme, TENU = Σ (actifs + garde des sessions identifiées vivantes",
        "appelant identifié, TENU = Σ (actifs + garde (ci-dessous) du",
        "de moins d'une heure) + max(0, accords anonymes de moins de 300 s − ACTIFS)",
        "Une session dont le PID est mort, ou dont le dernier relevé a plus d'une heure, ne tient plus rien",
        # S-01M5BSJ7PB (revises S-01M56Z5GT8): another session's grants held 300 s, an ACTIFS = 0 grant 1 h.
        "**Les accordés d'une autre session** (S-01M5BSJ7PB, qui révise S-01M56Z5GT8)",
        "son dernier relevé tient ses accordés seulement s'il a moins de 300 s ou s'il est à ACTIFS = 0, sinon 0 ; "
        "ses actifs restent tenus jusqu'à une heure",
        "les accords des autres sessions sont tenus 300 s",
        "un accord à ACTIFS = 0 (lanceur à vague bloquante, déjà borné par BASE) est tenu une heure",
        "A reçoit 11 à ACTIFS = 1 ; B, à ACTIFS = 0, reçoit 0 dans les 300 s, puis 9",
        "FENETRE_PROBANTE_S, distincte de la retenue",
        "a = ACTIFS + accordés + tenu du DERNIER ACCORD",
    ),
    7: (
        "Après trois attentes rendues à 0 à cause de TENU, ce secours peut lancer un agent sous « poste "
        "surchargé » sans surcharge réelle et dépasser le plafond partagé ; ce dépassement est dit",
        "chaque vague reçoit max(0, min(BASE, LIBRE)), soit neuf sur 18 cœurs au repos",
        "deux vagues à moins de 300 s : la seconde reçoit min(BASE, PLAFOND − accord précédent) — 9, 3, puis 0 "
        "sur PLAFOND 12 au repos",
        "**Accord d'un lanceur à vague bloquante tenu une heure** (résidu de S-01M5BSJ7PB)",
        "B, à ACTIFS = 0, reçoit 3 jusqu'à t3599, puis 9 à t3600",
        "17 en vol pour un plafond de 12",
        "15 en vol pour un plafond de 12",
        "descendre de 1 par cycle",
        "Le dépassement transitoire de 2C/3 est ACCEPTÉ",
        "aucun agent en vol n'est arrêté",
        "plafond partagé a au moins ces six trous (L-00000187)",
        "**accord lancé sans nouveau relevé** (envers de S-01M5BSJ7PB)",
        "21 en vol pour un plafond de 12",
        "**PID réutilisé, relevé remplacé** : surcompte prudent (moins de départs, jamais plus)",
        "**replis sans TENU** : la charge non mesurable et l'état non inscriptible (§ 3) ne lisent pas TENU",
        "ACTIFS = 0 et TENU = 12 reçoit encore 5",
        "non inscriptible, 1 à ACTIFS = 0 dans chaque session",
        "`CLAUDE_PID` sous l'outil Workflow et sous `claude -p` : NON MESURÉ",
    ),
}
# The abolished cadence (+2 per measure, 300 s between accords, C/2 start threshold, base at
# five for every wave), anywhere in the file.
CONTRAT_INTERDITS = (
    "+2",
    "min(2, PLAFOND − ACTIFS)",
    "ACTIFS = 0 ⇒ PEUT_AJOUTER = BASE",
    "PEUT_AJOUTER = 5 : les deux",
    "un accord date de moins de 300 s",
    "règle des 300 s",
    "(au plus cinq)",
    "aucun 0 permanent",
    "plafond partagé a quatre trous",
)


def _plat(texte: str) -> str:
    """Whitespace collapsed to one space: an anchor survives a Markdown re-wrap."""
    return re.sub(r"\s+", " ", texte)


def _section_contrat(texte: str, numero: int) -> str:
    """Section `## <numero>.` of the contract, up to the next `## ` title; '' when absent."""
    trouve = re.search(rf"^## {numero}\. .*?(?=^## |\Z)", texte, re.M | re.S)
    return trouve.group(0) if trouve else ""


def _garantie(section3: str) -> str:
    """The GARANTIE bullet of § 3, flattened; '' when absent."""
    trouve = re.search(r"^- \*\*GARANTIE\*\*.*?(?=^- |^\s*$)", section3, re.M | re.S)
    return _plat(trouve.group(0)) if trouve else ""


def defauts_contrat_charge(texte: str) -> list[str]:
    """Every way `texte` departs from the contract of plan r14: a missing anchor, an abolished
    clause, an unqualified GARANTIE. Pure, so the negative control replays THIS rule."""
    defauts = []
    for numero, ancres in CONTRAT_ANCRES.items():
        section = _plat(_section_contrat(texte, numero))
        defauts += [f"§ {numero} sans « {a} »" for a in ancres if a not in section]
    plat = _plat(texte)
    defauts += [f"cadence abolie « {i} »" for i in CONTRAT_INTERDITS if i in plat]
    if "< C/2" in _plat(_section_contrat(texte, 3)):
        defauts.append("§ 3 : seuil de départ C/2 aboli (2C/3 seul)")
    garantie = _garantie(_section_contrat(texte, 3))
    if not ("TENU occupe le plafond" in garantie and "une heure" in garantie):
        defauts.append("GARANTIE non qualifiée par TENU")
    return defauts


class ChargePosteContratTests(unittest.TestCase):
    """The station-load contract TRAVELS (TAKE) and is read by every adopter launcher: it must
    state the first wave BASE then the immediate LIBRE under 2C/3, the retention between callers,
    C44 over the whole station, and the named holes — never the abolished cadence. Runs in an
    adopting tree too: the file travels, so the clauses must hold there."""

    def setUp(self):
        chemin = ROOT / CONTRAT_CHARGE
        if not chemin.is_file():
            self.skipTest(f"{CONTRAT_CHARGE} absent from this tree — nothing to read")
        self.texte = chemin.read_text(encoding="utf-8")

    def test_contrat_separe_accord_et_probant(self):
        self.assertEqual(defauts_contrat_charge(self.texte), [])

    def test_contrat_voyage_par_take(self):
        if not _is_kit_repo():
            self.skipTest("not the kit's repo — the TAKE predicate is judged in the kit only")
        self.assertTrue(travels(CONTRAT_CHARGE, rules()), f"{CONTRAT_CHARGE} would not reach the template")

    def test_controle_negatif_chaque_mutant_rougit(self):
        """Each mutant is applied to THE contract, sections kept (the replacement must hit), and must
        add a defect to those of the unmutated text — never a control that is red for another reason."""
        garantie = _garantie(_section_contrat(self.texte, 3))
        nue = "- **GARANTIE** : PLAFOND ≥ 1 et BASE ≥ 1 ; à ACTIFS = 0, hors surcharge PRÉSENTE, PEUT_AJOUTER ≥ 1. "
        temoin = defauts_contrat_charge(self.texte)
        mutants = {
            "min(2) en :65-66": ("PEUT_AJOUTER = max(0, LIBRE), sans délai",
                                 "PEUT_AJOUTER = max(0, min(2, PLAFOND − ACTIFS)), sans délai"),
            "+2 dans l'exemple": ("TENU = 0, accord 7", "TENU = 0, accord 7, puis +2"),
            "BASE seule en :64": ("ACTIFS = 0 ⇒ PEUT_AJOUTER = max(0, min(BASE, LIBRE))",
                                  "ACTIFS = 0 ⇒ PEUT_AJOUTER = BASE"),
            "porte à cinq en :88": ("PEUT_AJOUTER = 9 : les deux revues partent ensemble, budget 7",
                                    "PEUT_AJOUTER = 5 : les deux partent ensemble, budget 3"),
            "vague à cinq en :158": ("chaque vague reçoit max(0, min(BASE, LIBRE))",
                                     "chaque vague vaut BASE (au plus cinq)"),
            "C44 sans tenu": ("a = ACTIFS + accordés + tenu du", "a = ACTIFS + accordés du"),
            "seuil C/2 en :65-66": ("sinon 0. À l'égalité 2C/3, 0",
                                    "sinon 2 si 1 min ET 5 min < C/2, sinon 0. À l'égalité 2C/3, 0"),
            # The qualifier alone is dropped: the old « aucun 0 permanent » is a separate, forbidden clause.
            "GARANTIE non qualifiée": (garantie, nue),
            # The qualified bullet survives, but in the header, out of § 3: it binds nothing there.
            "GARANTIE qualifiée hors du § 3": (garantie, nue, garantie),
            "GARANTIE sans sa borne d'une heure": ("jusqu'à une heure après le dernier relevé d'une autre session "
                                                   "vivante, ou sans borne tant qu'elle relève", "sans borne"),
            "GARANTIE sans « Sans TENU … ≥ 1 »": ("Sans TENU, à ACTIFS = 0 hors surcharge PRÉSENTE, "
                                                  "PEUT_AJOUTER ≥ 1.", ""),
            "BASE= nominale": ("`BASE` imprime la base EFFECTIVE", "`BASE` imprime la base NOMINALE"),
            "replis du § 3 lisant TENU": ("Ni ce repli ni celui de l'état non inscriptible ne lisent TENU",
                                          "Ces deux replis lisent TENU"),
            "exemple 11,99/11,99 à 0": ("à 11,99/11,99, accord 7", "à 11,99/11,99, accord 0"),
            "exemple 12,01 à 9": ("accord 0 et DOIT_REDESCENDRE_A = 5 (modérée",
                                  "accord 0 et DOIT_REDESCENDRE_A = 9 (modérée"),
            "exemple hors repos à 9": ("(hors repos, BASE = 5)", "(hors repos, BASE = 9)"),
            "relevé sans ses champs": ("Chaque relevé porte les champs `claude_pid` (`null` pour un appelant "
                                       "anonyme) et `tenu` (le TENU lu à ce verdict).", ""),
            "PID Windows supposé mort": ("est SUPPOSÉ vivant", "est supposé mort"),
            "ancien relevé sans tenu rejeté": ("un ancien relevé sans `tenu`, ou un `tenu` invalide, vaut 0.",
                                               "un ancien relevé sans `tenu` est rejeté."),
            "TENU identifié sans les anonymes": ("+ accords anonymes de moins de 300 s + max(0, accords propres",
                                                 "+ max(0, accords propres"),
            "TENU anonyme sans − ACTIFS": ("max(0, accords anonymes de moins de 300 s − ACTIFS).",
                                           "accords anonymes de moins de 300 s."),
            "PID mort tient encore": ("Une session dont le PID est mort, ou dont le dernier relevé a plus d'une "
                                      "heure, ne tient plus rien.", "Une session tient ses places tant qu'elle "
                                                                    "a relevé."),
            "secours dû à TENU retiré": ("Après trois attentes rendues à 0 à cause de TENU, ce secours peut lancer "
                                         "un agent sous « poste surchargé » sans surcharge réelle et dépasser le "
                                         "plafond partagé ; ce dépassement est dit.", ""),
            "quatre trous": ("a au moins ces six trous (L-00000187)", "a quatre trous"),
            "PID réutilisé retiré": ("- **PID réutilisé, relevé remplacé** : surcompte prudent (moins de départs, "
                                     "jamais plus) ;", ""),
            "replis sans TENU à 0": ("TENU = 12 reçoit encore 5", "TENU = 12 reçoit 0"),
            "non inscriptible partagé": ("1 à ACTIFS = 0 dans chaque session", "1 à ACTIFS = 0 pour le poste"),
            "NON MESURÉ retiré": ("`CLAUDE_PID` sous l'outil Workflow et sous `claude -p` : NON MESURÉ.", ""),
            # S-01M5BSJ7PB: the revised retention, its residual, and the § 3 examples.
            "retenue sans la clause ACTIFS = 0": ("moins de 300 s ou s'il est à ACTIFS = 0, sinon 0",
                                                  "moins de 300 s, sinon 0"),
            "retenue sans la clause 300 s": ("s'il a moins de 300 s ou s'il est à ACTIFS = 0",
                                             "s'il est à ACTIFS = 0"),
            "accords tenus une heure (S-01M56Z5GT8)": ("les accords des autres sessions sont tenus 300 s",
                                                       "les accords des autres sessions sont tenus une heure"),
            "exemple F1 bloqué une heure": ("reçoit 0 dans les 300 s, puis 9", "reçoit 0 pendant une heure"),
            "vagues rapprochées sans retenue": ("9, 3, puis 0 sur PLAFOND 12", "9, 9, puis 9 sur PLAFOND 12"),
            "résidu d'une heure retiré": ("**Accord d'un lanceur à vague bloquante tenu une heure** (résidu de "
                                          "S-01M5BSJ7PB)", "**Accord bloquant**"),
            "exemple sévère à 5": ("DOIT_REDESCENDRE_A = 3 (sévère)", "DOIT_REDESCENDRE_A = 5 (sévère)"),
            "exemple 18,00 à 0": ("à 18,00, encore 5", "à 18,00, accord 0"),
            "exemple C = 6 à PLAFOND 5": ("C = 6 : PLAFOND 4,", "C = 6 : PLAFOND 5,"),
            "exemple C = 1 à 5": ("C = 1 : 1.", "C = 1 : 5."),
        }
        for nom, (avant, apres, *en_tete) in mutants.items():
            with self.subTest(mutant=nom):
                motif = r"\s+".join(map(re.escape, avant.split()))
                mute, coups = re.subn(motif, lambda _m, a=apres: a.strip(), self.texte)
                self.assertTrue(avant and coups, f"mutant {nom} : la cible a disparu du contrat")
                mute = "\n".join([*en_tete, mute])
                self.assertNotEqual(defauts_contrat_charge(mute), temoin, f"mutant {nom} : le témoin reste vert")

    def test_controle_negatif_chaque_clause_compte(self):
        """Every anchor, once MOVED out of its section (to the header, which belongs to none), and every
        abolished clause, once appended, is caught on its own: no entry of the two tables is dead weight,
        and an anchor counts only in its own section."""
        temoin = defauts_contrat_charge(self.texte)
        for numero, ancres in CONTRAT_ANCRES.items():
            for ancre in ancres:
                with self.subTest(ancre=ancre):
                    motif = r"\s+".join(map(re.escape, ancre.split()))
                    mute, coups = re.subn(motif, "", self.texte)
                    self.assertTrue(coups, f"§ {numero} : ancre absente du contrat")
                    self.assertNotEqual(defauts_contrat_charge(f"{ancre}\n{mute}"), temoin)
        for interdit in CONTRAT_INTERDITS:
            with self.subTest(interdit=interdit):
                self.assertNotEqual(defauts_contrat_charge(f"{self.texte}\n{interdit}\n"), temoin)


# ---------------------------------------------------------------------------
# THE V3 EVENT STORE AND ITS WAL SIDECARS (T-00000376)
# ---------------------------------------------------------------------------
V3_STORE = ".agents/state/v3_event_store.db"
V3_WAL = V3_STORE + "-wal"
V3_SHM = V3_STORE + "-shm"
# The two rules as they must appear in `.gitignore`: leading slash = anchored to
# the repo root, full filename = literal. The controls below read them from the
# file rather than re-deriving them, so they replay THE rule (L-00000057).
V3_SIDECAR_RULES = ("/" + V3_WAL, "/" + V3_SHM)
# The OTHER SQLite store of the same tree, and the reason the rules above are
# anchored rather than globbed.
INDEX_DB = ".agents/state/index/index.db"
INDEX_WAL = INDEX_DB + "-wal"


def _check_ignore(root: Path, rel: str, env: dict | None = None) -> int:
    """Return code of `git check-ignore --no-index` — 0 ignored, 1 not ignored,
    128 fatal. Callers assert it AT EQUALITY; see the class docstring."""
    return subprocess.run(
        ["git", "-C", str(root), "check-ignore", "--no-index", "-q", "--", rel],
        capture_output=True, text=True, env=env).returncode


@contextlib.contextmanager
def _repo_carrying(gitignore_text: str):
    """A throwaway repository whose entire `.gitignore` is `gitignore_text`.

    Editing the real `.gitignore` to prove these controls can go red would leave
    a window where the repository is wrong, and the shell guard rightly refuses
    the redirect that would do it — the same reasoning as the `travels()` control
    above. Replaying the rule TEXT in a scratch repo touches nothing tracked.

    The scratch repo is also insulated from the MACHINE's git configuration AND its
    global ignore file, whose default path (`$XDG_CONFIG_HOME/git/ignore`) no config
    key names (measured, T-00000766): a contributor carrying `*.db-wal` there would
    otherwise see these arms answer for reasons foreign to this repository's rules —
    the class of an ignore rule that exists on one machine, recorded above `*.bak`."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "repo"
        root.mkdir()
        neutral = Path(tmp) / "neutral.gitconfig"
        neutral.write_text("", encoding="utf-8")
        # `safe.directory` is read from protected scope only: the neutral global erases the one
        # verify.sh sets in the container, so the ROOT probe would answer 128 — command scope here.
        env = dict(os.environ, GIT_CONFIG_GLOBAL=str(neutral), GIT_CONFIG_SYSTEM=str(neutral),
                   XDG_CONFIG_HOME=tmp,  # no `git/ignore` under it
                   GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="safe.directory", GIT_CONFIG_VALUE_0=str(ROOT))
        subprocess.run(["git", "init", "-q", str(root)],
                       capture_output=True, text=True, check=True, env=env)
        (root / ".gitignore").write_text(gitignore_text, encoding="utf-8")
        yield root, env


class V3EventStoreSidecarTests(unittest.TestCase):
    """ONE committed file, and no WAL noise beside it (T-00000376).

    `agentic_v3/db/schema.py:20` opens every connection on
    `PRAGMA journal_mode = WAL`, which drops `-wal` and `-shm` next to the
    database while it is open. The kit already held this exact reasoning for its
    OTHER SQLite store and had simply never applied it here:
    `.agents/bin/migrate_index_to_db.py` refused WAL for `index.db` because it
    "would add `-wal`/`-shm` sidecar files next to a store whose whole point is
    to be ONE committed file" (the store was committed then; since T-00000668 it
    is machine state outside the repository, and the rule stays for a legacy
    duplicate). Two SQLite stores in one directory, two policies, only one of
    them owned.

    WHY NOTHING HERE IS CHECKED AGAINST `git status`. Closing a task runs
    `PRAGMA wal_checkpoint(TRUNCATE)`, so the sidecars are usually absent from
    the tree — and a control that observed their absence would pass exactly as
    happily on a repository carrying no rule at all. Two empty sets agree
    (L-00000186). Every arm below therefore interrogates the RULES, and every
    negative control MANUFACTURES its condition in a scratch repository instead
    of observing this one.

    WHY `--no-index` IS NOT OPTIONAL. Without it, check-ignore consults the index
    and answers "not ignored" for ANY tracked file. The arm watching for an
    over-broad rule would then stay green after someone added
    `/.agents/state/*.db` — green while measuring nothing. `--no-index` catches
    an over-broad RULE; `ls-files --error-unmatch` catches an actual UN-TRACKING.
    Neither replaces the other, which is why both are here.

    WHY RETURN CODES ARE COMPARED AT EQUALITY. `git` answers 128 when it is
    missing or run outside a repository. An `assertNotEqual(0, ...)` would read
    that fatal as a successful control and go green on a broken environment.
    """

    def _gitignore(self) -> str:
        return (ROOT / ".gitignore").read_text(encoding="utf-8")

    # -- the two arms, read on this repository ------------------------------

    def test_wal_sidecars_du_store_v3_sont_ignores(self):
        for rel in (V3_WAL, V3_SHM):
            with self.subTest(sidecar=rel):
                self.assertEqual(
                    0, _check_ignore(ROOT, rel),
                    f"{rel} is NOT ignored. The WAL sidecar of the V3 event store surfaces as "
                    "untracked, and the two gestures this repo prescribes itself — the adoption "
                    "`git add -A` in docs/usage.html and the one in sync_template.py — would "
                    "sweep it into a commit.")

    def test_le_store_v3_event_store_est_desuivi_et_absent_de_l_arbre(self):
        # Témoin 12 (T-00000677) — RENOMMÉ et INVERSÉ depuis l'arm SYM-3766 qui assertait
        # « suivi ET non ignoré ». Le store V3 figé a été DÉSINDEXÉ : il est désormais IGNORÉ
        # (`check-ignore` = 0) ET ABSENT DES SUIVIS (`ls-files --error-unmatch` = 1) — l'INVERSE
        # exact des deux assertions historiques. MUTATION : inverser une seule des deux moitiés
        # fait rougir le témoin (un fichier à la fois suivi ET ignoré est une incohérence).
        self.assertEqual(
            0, _check_ignore(ROOT, V3_STORE),
            f"{V3_STORE} n'est PAS ignoré. Après désindexation (T-00000677) le "
            "doublon figé doit être ignoré — règle littérale et ancrée dans "
            "`.gitignore` — pour qu'un `git add -A` ne le re-commite jamais.")
        if _is_kit_repo():
            self.assertEqual(
                1,
                subprocess.run(
                    ["git", "-C", str(ROOT), "ls-files", "--error-unmatch",
                     "--", V3_STORE],
                    capture_output=True, text=True).returncode,
                f"{V3_STORE} est ENCORE suivi. La désindexation (`git rm --cached`) "
                "doit l'avoir retiré des suivis : les règles d'ignore peuvent être "
                "parfaites et l'histoire suivie subsister quand même.")
        # Bras INVERSÉ par T-00000668, sur le patron du store V3 ci-dessus : `index.db` est
        # désormais un store MACHINE hors dépôt (`cadre.paths.index_db()`) ; l'ancien chemin est
        # DÉSINDEXÉ, donc IGNORÉ (règle littérale et ancrée `/.agents/state/index/index.db`, pour
        # qu'un doublon hérité ne soit jamais re-commité) ET ABSENT DES SUIVIS.
        # MUTATION : retirer la règle de `.gitignore` → `check-ignore` rend 1, rouge.
        self.assertEqual(
            0, _check_ignore(ROOT, INDEX_DB),
            f"{INDEX_DB} n'est PAS ignoré. Après désindexation (T-00000668) un doublon hérité à "
            "l'ancien chemin doit être ignoré — règle littérale et ancrée dans `.gitignore` — "
            "pour qu'un `git add -A` ne le re-commite jamais.")
        # Le bras de DÉSUIVI d'`index.db` : méthode suivante, même discriminant.

    def test_index_db_est_desuivi_dans_tout_clone_du_kit(self):
        """Bras de DÉSUIVI de T11 (T-00000668), pour TOUT clone du kit. Chez un
        adoptant : skip EXPLICITE — un `index.db` qu'il aurait commité est nommé,
        avec son geste, par la NOTE « doublon hérité » de `migrate_index_to_db.py`.
        Mutation : `git add -f` de l'ancien chemin dans un clone → rouge."""
        if not _is_kit_repo():
            self.skipTest("adoptant : .agents/state/ ne voyage pas — un index.db commité "
                          "par l'adoptant est nommé par la NOTE « doublon hérité »")
        # À l'ÉGALITÉ (1 = non suivi), jamais `!= 0` : 128 (git absent, hors
        # dépôt) passerait pour un désuivi réussi — voir la docstring de classe.
        self.assertEqual(
            1,
            subprocess.run(
                ["git", "-C", str(ROOT), "ls-files", "--error-unmatch",
                 "--", INDEX_DB],
                capture_output=True, text=True).returncode,
            f"{INDEX_DB} est ENCORE suivi. La désindexation (`git rm --cached`, "
            "T-00000668) doit l'avoir retiré des suivis.")

    # -- the controls, each manufacturing its own condition ------------------

    def test_controle_negatif_privee_de_ses_deux_lignes_la_regle_cesse_de_mordre(self):
        """The control this tree cannot provide. Delete the two rules and the
        positive arm above must go RED — otherwise it was passing on the WAL
        checkpoint's good manners rather than on anything in `.gitignore`."""
        real = self._gitignore()
        present = real.splitlines()
        for rule in V3_SIDECAR_RULES:
            self.assertIn(rule, present,
                          f"{rule} is absent from .gitignore, so this control "
                          "would compare two identical texts and prove nothing.")
        without = "\n".join(
            line for line in present if line.strip() not in V3_SIDECAR_RULES) + "\n"

        with _repo_carrying(real) as (root, env):
            self.assertEqual(0, _check_ignore(root, V3_WAL, env),
                             "base not green: the real rules do not ignore the sidecar in a "
                             "scratch repo, so the mutation below would prove nothing")
        with _repo_carrying(without) as (root, env):
            for rel in (V3_WAL, V3_SHM):
                with self.subTest(sidecar=rel):
                    self.assertEqual(
                        1, _check_ignore(root, rel, env),
                        "THE RULE DOES NOT BITE: the sidecar is still ignored "
                        "with both lines removed, so something else covers it "
                        "and the positive arm no longer measures these rules.")

    def test_controle_negatif_un_motif_flottant_capturerait_le_store_d_index(self):
        """WHY THE RULES ARE ANCHORED, proven rather than asserted. `*.db-wal` reads as the obvious
        form and would quietly annex the sidecars of every other SQLite store in the tree —
        starting with `index.db`, a different file with its own written policy."""
        real = self._gitignore()
        floating = real.replace("/" + V3_WAL, "*.db-wal").replace("/" + V3_SHM,
                                                                 "*.db-shm")
        self.assertNotEqual(real, floating,
                            "the anchored rules were not found, so the mutation "
                            "below is not the one being described")

        with _repo_carrying(real) as (root, env):
            self.assertEqual(1, _check_ignore(root, INDEX_WAL, env),
                             "base not green: the anchored rules already reach "
                             "the index store's sidecar")
        with _repo_carrying(floating) as (root, env):
            self.assertEqual(
                0, _check_ignore(root, INDEX_WAL, env),
                "the floating form no longer catches the index store's sidecar, "
                "so this control has stopped demonstrating why the rules are "
                "anchored — re-establish what it measures, do not delete it.")
            # The REAL tree under `env`: the machine's git config cut off; this clone's
            # `.git/info/exclude` is NOT covered by that isolation (non mesuré).
            if _is_kit_repo():
                self.assertEqual(
                    1, _check_ignore(ROOT, INDEX_WAL, env),
                    "something in this repository's ignore stack now covers the "
                    "index store's sidecar. `index.db` is deliberately NOT in WAL "
                    "mode, so that rule is either dead or too broad.")

    def test_controle_negatif_une_regle_trop_large_desuivrait_le_store(self):
        """The mirror control, AMENDÉ le 2026-09-21 (T-00000677) — sa prémisse a été INVERSÉE par
        ce lot. Le store V3 est désormais DÉSINDEXÉ, donc IGNORÉ sous les règles réelles par sa
        ligne ANCRÉE `/.agents/state/v3_event_store.db`. La base est donc « ignoré (0) », et la
        mutation RETIRE la ligne ancrée : le store cesse d'être ignoré (`1`). C'est l'INVERSE de
        l'ancienne mutation (qui AJOUTAIT `/.agents/state/*.db`). Conservé, jamais supprimé :
        c'est ce qui prouve que la ligne ancrée du store MORD."""
        real = self._gitignore()
        anchored = "/" + V3_STORE
        self.assertIn(
            anchored, real.splitlines(),
            f"{anchored} absent de .gitignore : la mutation comparerait deux "
            "textes identiques et ne prouverait rien.")
        without = "\n".join(
            line for line in real.splitlines() if line.strip() != anchored) + "\n"

        with _repo_carrying(real) as (root, env):
            self.assertEqual(0, _check_ignore(root, V3_STORE, env),
                             "base not green: le store désindexé DOIT être ignoré "
                             "sous les règles réelles (ligne ancrée présente)")
        with _repo_carrying(without) as (root, env):
            self.assertEqual(
                1, _check_ignore(root, V3_STORE, env),
                f"LA LIGNE ANCRÉE NE MORD PAS : privé de `{anchored}`, le store reste ignoré — "
                "une autre règle le couvre et ce contrôle ne mesure plus la ligne du store.")


if __name__ == "__main__":
    unittest.main()
