"""Contrat de la skill maison React 19 / Next.js 15-16 (T-01M5DFV8YEAF4G68TXDD86QXP0, lot A).

Ce banc épingle la skill `.agents/skills/react-best-practices/SKILL.md` et son
pointeur Claude `.claude/skills/react-best-practices-pointer/SKILL.md` :

- le CONTENU promis (sections React 19 et Next 15/16, vérification lint,
  `tsc --noEmit` et build choisie d'après le lockfile, script absent jamais vert,
  `agentRules: false` et `--no-agents-md`) ;
- la DÉLÉGATION des tests : aucune commande de runner, aucun nom de l'ancienne
  skill Playwright, renvoi vers `CONVENTIONS_nextjs.md` § Testing ;
- AUCUN CHEMIN NI NOM DE SKILL qui pende : un `.agents/skills/<n>/SKILL.md` cité
  existe sur disque, et les skills de test annoncées par T-01M5DJQSP0 ne sont
  pas nommées tant que leur dossier n'existe pas (réserve C7, noms nus) ;
- la PROVENANCE : sources épinglées au commit, MIT, datées, synthèse adaptée, et
  aucune instruction tierce reprise ;
- les liens vers `composition-patterns` et le vendor, gardé intact ;
- le pointeur, qui vise la skill maison ;
- le VOYAGE : les trois chemins du lot partent chez l'adoptant (TAKE).

`sync_template` est importé par `sys.path`, jamais par chargement de module à la
main. Chaque assertion a son mutant, joué hors dépôt (rapport du lot A).
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL_REL = ".agents/skills/react-best-practices/SKILL.md"
POINTER_REL = ".claude/skills/react-best-practices-pointer/SKILL.md"
WITNESS_REL = ".agents/evals/test_react_skill_contract.py"
VENDOR_REL = ".agents/skills/vendor/react-best-practices/SKILL.md"
COMPOSITION_REL = ".agents/skills/composition-patterns/SKILL.md"
NEXT_SHEET_REL = ".agents/ref/CONVENTIONS_nextjs.md"

# Les skills de test que T-01M5DJQSP0 doit créer, hors du tag courant
# (S-01M5J3W9CY). Écrites ICI, jamais globbées : tant que leur dossier n'existe
# pas, la skill React ne les nomme pas, ni par chemin ni par nom nu.
PENDING_TEST_SKILLS = ("vitest", "playwright-cli", "react-testing-library")

CITED_SKILL_PATH = re.compile(r"\.agents/skills/[A-Za-z0-9_./-]+?/SKILL\.md")
SKILL_NAME_NEAR_WORD = re.compile(
    r"(?i)skills?\s+`([a-z0-9][a-z0-9-]*)`|`([a-z0-9][a-z0-9-]*)`\s+skills?\b"
)
FORBIDDEN_RUNNER = (
    re.compile(r"(?i)vitest\s+run"),
    re.compile(r"(?i)npx\s+vitest"),
    re.compile(r"(?i)playwright\s+test"),
    re.compile(r"(?i)playwright-(?!cli)"),
)
# Une mention de version : « React 19 », « Next ≥ 16.3 », « Next.js 16 », « 16.3 »,
# « 19.3.1 », « v16.2.0 », « 15.5.x ».
VERSION_MENTION = re.compile(
    r"\b(?:React|Next(?:\.js)?)\s+[≥≤]?\s*\d+|\bv?\d+\.\d+(?:\.(?:\d+|x))?\b"
)
FORBIDDEN_THIRD_PARTY = (
    re.compile(r"(?i)npx\s+skills\s+add"),
    re.compile(r"(?i)curl[^\n]*\|\s*(?:ba|z)?sh\b"),
    re.compile(r"\|\s*tail\b"),
    re.compile(r"--forceExit"),
)


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _split_frontmatter(text: str) -> tuple[str, str]:
    if not text.startswith("---\n"):
        return "", text
    end = text.find("\n---\n", 4)
    if end == -1:
        return "", text
    return text[4:end], text[end + 5:]


def _section(body: str, heading: str) -> str:
    start = body.find(f"\n{heading}\n")
    if start == -1:
        return ""
    nxt = body.find("\n## ", start + len(heading) + 2)
    return body[start:] if nxt == -1 else body[start:nxt]


class ReactSkillContract(unittest.TestCase):
    def setUp(self) -> None:
        self.text = _read(SKILL_REL)
        self.frontmatter, self.body = _split_frontmatter(self.text)

    def test_frontmatter_opens_on_line_one_with_the_directory_name(self):
        self.assertTrue(self.text.startswith("---\n"), "frontmatter must open on line 1")
        self.assertIn("name: react-best-practices\n", self.frontmatter + "\n")
        self.assertRegex(self.frontmatter, r"(?m)^description: \S")

    def test_react_skill_sections(self):
        for heading in (
            "## Server et Client Components",
            "## Server Actions et leur sécurité",
            "## Hooks React 19",
            "## État",
            "## Fetching et cache (Next)",
            "## Performance",
            "## Ruptures React 19",
            "## Tests",
            "## Provenance",
        ):
            self.assertIn(f"\n{heading}\n", self.body, f"missing section {heading!r}")

    def test_react19_hooks_named(self):
        hooks = _section(self.body, "## Hooks React 19")
        for token in ("`use(promise)`", "`useActionState(", "`useOptimistic("):
            self.assertIn(token, hooks, f"hook {token} absent from § Hooks React 19")

    def test_server_actions_are_treated_as_public_endpoints(self):
        actions = _section(self.body, "## Server Actions et leur sécurité")
        self.assertIn("POINT D'ENTRÉE HTTP PUBLIC", actions)
        for step in ("authentifier", "autoriser", "valider les entrées"):
            self.assertIn(step, actions, f"server action rule {step!r} lost")

    def test_next_15_and_16_both_covered(self):
        fetching = _section(self.body, "## Fetching et cache (Next)")
        self.assertRegex(fetching, r"Next 15 : `params`")
        self.assertIn("`revalidateTag(tag, profil)`", fetching)
        self.assertIn("`updateTag(tag)`", fetching)

    def test_verification_chosen_from_the_lockfile(self):
        verify = _section(self.body, "## Vérifier : lint, `tsc --noEmit` et build, d'après le lockfile")
        self.assertTrue(verify, "verification section missing")
        for lockfile in ("pnpm-lock.yaml", "yarn.lock", "bun.lock", "package-lock.json"):
            self.assertIn(f"`{lockfile}`", verify, f"lockfile {lockfile} not mapped")
        # Dans la RÈGLE, pas seulement dans le titre de la section (survivant mesuré).
        self.assertIn("Typage sans script dédié : `tsc --noEmit`", verify)
        self.assertIn("`next lint` est retiré", verify)
        self.assertIn("Un script absent ne vaut jamais réussite", verify)

    def test_agents_md_guard_for_next_16_3(self):
        guard = _section(self.body, "## Next ≥ 16.3 et le AGENTS.md du kit")
        self.assertIn("`agentRules: false`", guard)
        self.assertIn("--no-agents-md", guard)

    def test_next_sheet_requires_agent_rules_off_for_kit_repositories(self):
        sheet = _read(NEXT_SHEET_REL)
        self.assertIn(
            "In a repository equipped with this kit, `AGENTS.md` is the doctrine: set\n"
            "  `agentRules: false` in Next config.",
            sheet,
        )
        self.assertNotIn("if the project owns those instructions", sheet)

    def test_exact_facts_pinned(self):
        """Faits EXACTS — version, négation, seuil : chacun avait un mutant survivant."""
        for fact in (
            # versions relevées au registre npm
            "`react` 19.3.1, `next` 16.4.2 (dist-tag `latest`)",
            "(dist-tag `backport` 15.5.x)",
            # négations du lint sous Next 16
            "sous Next 16, `next lint` est retiré et le build ne lint plus",
            "Lint : sous Next 15, `next build` lint aussi et `next lint` existe",
            # seuil de agentRules
            "Depuis Next 16.3 (`agentRules` absent de `config-shared.ts` à `v16.2.0`, présent à `v16.4.2`",
            # l'autorisation des Server Actions, dans l'ordre
            "Dans CHAQUE action : authentifier, puis autoriser sur la ressource visée, "
            "puis valider les entrées par un schéma",
        ):
            self.assertIn(fact, self.body, f"exact fact lost: {fact!r}")
        for wrong in ("agentRules: true", "webpack"):
            self.assertNotIn(wrong, self.body, f"wrong or out-of-scope fact written: {wrong!r}")

    def test_versioned_lines_carry_their_source(self):
        """La règle de SKILL.md:10 : une ligne qui nomme une version porte `https://`
        ou `à vérifier` ; un titre, sur la première ligne non vide qui le suit."""
        self.assertIn(
            "Toute ligne qui nomme une version porte sa source (`https://`) ou le "
            "marqueur `à vérifier` ; un titre la porte sur la première ligne non vide qui le suit.",
            self.body,
        )
        for probe in ("Next.js 16", "Next 15", "React 19", "16.3", "v16.2.0", "15.5.x"):
            self.assertRegex(probe, VERSION_MENTION, f"VERSION_MENTION is blind to {probe!r}")
        lines = self.body.splitlines()
        unsourced = []
        for index, line in enumerate(lines):
            if not VERSION_MENTION.search(line):
                continue
            carrier = line
            if line.startswith("#"):
                carrier = next((nxt for nxt in lines[index + 1:] if nxt.strip()), "")
            if "https://" not in carrier and "à vérifier" not in carrier:
                unsourced.append(line)
        self.assertEqual(unsourced, [], "version named without its source")

    def test_dangerously_set_inner_html_rule(self):
        boundary = _section(self.body, "## Server et Client Components")
        self.assertIn(
            "`dangerouslySetInnerHTML` ne reçoit que du HTML ASSAINI par une bibliothèque nommée "
            "(DOMPurify, ou `sanitize-html` côté serveur), jamais une entrée utilisateur brute "
            "ni un contenu stocké non filtré",
            boundary,
        )
        self.assertIn(
            "Assainis APRÈS la dernière transformation ; DOMPurify exige un DOM "
            "(serveur : sanitize-html ou DOMPurify sur jsdom).",
            boundary,
        )

    def test_registry_names_a_house_skill_not_the_section_kit_skill(self):
        """`kit_skill:` routes the WHOLE typescript section: a NestJS project
        must not stop on the React skill."""
        registry = _read(".agents/ref/DOCS_REGISTRY.md")
        self.assertNotIn(f"kit_skill: {SKILL_REL}", registry)
        self.assertIn(
            "house_skill (react/next.js only, never this section's kit_skill): "
            f"{SKILL_REL} (React 19 / Next.js 15-16; conventions: {NEXT_SHEET_REL})",
            registry,
        )

    def test_typescript_sheet_is_linked(self):
        self.assertIn("et `.agents/ref/CONVENTIONS_typescript.md`.", self.body)
        self.assertTrue((ROOT / ".agents/ref/CONVENTIONS_typescript.md").is_file())

    def test_react_tests_delegated(self):
        for pattern in FORBIDDEN_RUNNER:
            self.assertIsNone(
                pattern.search(self.text),
                f"test command or retired Playwright skill named: {pattern.pattern}",
            )
        # Le paragraphe de DÉLÉGATION seul : la limite qui le suit cite aussi la
        # feuille, et la masquerait (survivant mesuré).
        delegation = _section(self.body, "## Tests").split("Limite, dite", 1)[0]
        self.assertIn("la skill de test du kit", delegation)
        self.assertIn(f"`{NEXT_SHEET_REL}` § Testing", delegation)
        self.assertTrue((ROOT / NEXT_SHEET_REL).is_file(), f"{NEXT_SHEET_REL} missing")

    def test_test_skill_limit_is_stated(self):
        tests = _section(self.body, "## Tests")
        self.assertRegex(tests, r"Limite, dite : .*aucune skill dédiée à Vitest ni à React Testing Library")

    def test_react_cited_skills_exist(self):
        cited = sorted(set(CITED_SKILL_PATH.findall(self.text)))
        self.assertTrue(cited, "the skill cites no skill path at all — the check measures nothing")
        missing = [rel for rel in cited if not (ROOT / rel).is_file()]
        self.assertEqual(missing, [], f"cited skill paths absent from disk: {missing}")

    def test_bare_skill_names_resolve(self):
        """Réserve C7 : un nom de skill NU (sans chemin) pend aussi bien qu'un chemin."""
        body = self.body.split("\n## Provenance\n", 1)[0]
        for match in SKILL_NAME_NEAR_WORD.finditer(body):
            name = match.group(1) or match.group(2)
            self.assertTrue(
                (ROOT / ".agents/skills" / name / "SKILL.md").is_file()
                or (ROOT / ".claude/skills" / name / "SKILL.md").is_file(),
                f"skill name `{name}` cited but no such skill on disk",
            )
        for name in PENDING_TEST_SKILLS:
            if (ROOT / ".agents/skills" / name / "SKILL.md").is_file():
                continue
            self.assertNotIn(f"`{name}`", self.text, f"pending skill `{name}` named before it exists")
            self.assertNotIn(f"skills/{name}", self.text, f"pending skill path {name} cited")

    def test_react_sources_and_license(self):
        provenance = _section(self.body, "## Provenance")
        for pin in ("@72895219d44d", "@613efc8c21d9", "@7c180d9044c9"):
            self.assertIn(pin, provenance, f"source pin {pin} missing")
        self.assertGreaterEqual(provenance.count("MIT"), 3, "each source must carry its licence")
        self.assertRegex(provenance, r"Relevé le 20\d\d-\d\d-\d\d")
        self.assertIn("Synthèse adaptée", provenance)
        self.assertIn("aucun import vendorisé", provenance)

    def test_no_third_party_instruction_carried(self):
        for pattern in FORBIDDEN_THIRD_PARTY:
            self.assertIsNone(pattern.search(self.text), f"forbidden instruction: {pattern.pattern}")

    def test_react_links_composition(self):
        self.assertIn(f"`{COMPOSITION_REL}`", self.text)
        self.assertIn(f"`{VENDOR_REL}`", self.text)
        self.assertTrue((ROOT / VENDOR_REL).is_file(), "vendored perf reference removed")
        self.assertIn("7c180d9044c9ae2b442b567aad4e42a28dd5ed62", _read(VENDOR_REL))


class ClaudePointerContract(unittest.TestCase):
    def test_claude_pointer_targets_house_skill(self):
        text = _read(POINTER_REL)
        frontmatter, body = _split_frontmatter(text)
        self.assertIn("name: react-best-practices-pointer\n", frontmatter + "\n")
        self.assertIn(f"**La substance vit dans `{SKILL_REL}`", body)
        self.assertIn(f"`{VENDOR_REL}`", body, "the vendor perf reference must stay linked")


class TemplateTakeContract(unittest.TestCase):
    def test_template_take_react(self):
        sys.path.insert(0, str(ROOT / ".agents" / "bin"))
        try:
            import sync_template as st
        finally:
            sys.path.pop(0)
        rules = st.parse_exclude((ROOT / ".template-exclude").read_text(encoding="utf-8"))
        for rel in (SKILL_REL, POINTER_REL, WITNESS_REL):
            self.assertIsNone(st.match_rule(rel, rules), f"{rel} no longer travels to adopters")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
