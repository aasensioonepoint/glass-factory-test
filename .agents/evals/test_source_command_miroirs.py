"""Les miroirs source-command suivent leur source Claude (T-01M5MY185WQ8S3F4D7ZFNCR390).

Population : lue sur le DISQUE — chaque `.agents/skills/source-command-<nom>/SKILL.md` est
apparié à `.claude/commands/<nom>.md` — et tenue égale à `POPULATION_ATTENDUE` (les douze
commandes hors `night`) : un miroir retiré ou ajouté sans ce banc rougit. Les miroirs sont
RENDUS par `render_hosts.py` (`cadre.renderers.commands.corps_du_miroir` applique la règle
ci-dessous) ; ce banc la rejoue de son côté, sans importer le renderer.

Règle de régénération (plan T-01M5MCXMQVHZ231CW0K2JR76MD, étape 7, décision pilote
S-01M5MCXYV352ZNNW7ZC75T8DJH ; traductions d'hôte ajoutées par la passe de correction
d'après S-01M5MZN96C) : le corps du miroir, sous `## Command Template`, est le corps de
`.claude/commands/<nom>.md` sans son front-matter, sans la ligne `Effort:` (propre à
Claude Code), avec trois traductions d'hôte :
* « Claude Code session » lu « Codex session » ;
* `/<commande>` lu `$<commande>`, pour toute commande de `.claude/commands/` (le
  sigil Codex/Copilot, AGENTS.md § Docs & skills) — jamais un segment de chemin ;
* `` `.claude/skills/` `` lu `` `.agents/skills/<name>/` or `.github/skills/<name>/` `` —
  la forme hôte-neutre de `.agents/skills/docs-sync/SKILL.md` (étape 5).
Le front-matter du miroir ouvre en ligne 1 et porte son propre `name:`. Une ligne
changée d'un côté sans l'autre rougit ce banc.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMANDES = ROOT / ".claude" / "commands"
PREFIXE = "source-command-"
# Douze depuis la source unique des commandes (`commands/<nom>.md`, rendue par
# `render_hosts.py`) : un miroir pour chaque commande hors Claude Code seul (`night`).
POPULATION_ATTENDUE = {"audit", "dash", "docs-sync", "index", "jira", "kickoff", "lang",
                       "planning", "planning-all", "setup", "skills-sync", "specs-sync"}
ANCRE = "## Command Template\n\n"
SKILLS_CLAUDE = "`.claude/skills/`"
SKILLS_HOTE_NEUTRE = "`.agents/skills/<name>/` or `.github/skills/<name>/`"
# Commande Claude Code seule (AGENTS.md § Unattended overnight mode) :
# aucun `$night` n'existe ailleurs, son `/` n'est jamais traduit.
CLAUDE_SEULES = frozenset({"night"})


def paires() -> list[tuple[str, Path, Path]]:
    """(nom, source Claude, miroir) pour chaque miroir présent sur disque."""
    miroirs = sorted((ROOT / ".agents" / "skills").glob(f"{PREFIXE}*/SKILL.md"))
    return [(m.parent.name[len(PREFIXE):], COMMANDES / f"{m.parent.name[len(PREFIXE):]}.md", m)
            for m in miroirs]


def _noms_de_commandes() -> list[str]:
    return sorted(p.stem for p in COMMANDES.glob("*.md") if p.stem not in CLAUDE_SEULES)


def _sans_front_matter(texte: str) -> str:
    m = re.match(r"---\n.*?\n---\n", texte, re.S)
    if not m:
        raise AssertionError("front-matter absent ou non ouvert en ligne 1")
    return texte[m.end():]


def traduire(corps: str, commandes: list[str]) -> str:
    """Les trois traductions d'hôte de la règle de régénération."""
    corps = corps.replace("Claude Code session", "Codex session")
    corps = corps.replace(SKILLS_CLAUDE, SKILLS_HOTE_NEUTRE)
    if commandes:
        alternance = "|".join(re.escape(c) for c in sorted(commandes, key=len, reverse=True))
        corps = re.sub(rf"(?<![\w./-])/({alternance})(?![\w/-])", r"$\1", corps)
    return corps


def corps_attendu(source: str, commandes: list[str] | None = None) -> str:
    """Corps du miroir dérivé de la source : sans front-matter ni ligne `Effort:`, traduit."""
    lignes = _sans_front_matter(source).split("\n")
    garde: list[str] = []
    saute_vide = False
    for ligne in lignes:
        if ligne.startswith("Effort:"):
            saute_vide = True
            continue
        if saute_vide and ligne == "":
            saute_vide = False
            continue
        saute_vide = False
        garde.append(ligne)
    corps = "\n".join(garde).strip("\n") + "\n"
    return traduire(corps, _noms_de_commandes() if commandes is None else commandes)


def corps_miroir(miroir: str) -> str:
    idx = miroir.find(ANCRE)
    if idx < 0:
        raise AssertionError(f"ancre {ANCRE!r} absente du miroir")
    return miroir[idx + len(ANCRE):]


class MiroirsSourceCommandTests(unittest.TestCase):
    def test_population_lue_sur_disque(self) -> None:
        trouvees = paires()
        self.assertEqual({nom for nom, _s, _m in trouvees}, POPULATION_ATTENDUE,
                         "population des miroirs source-command changée")
        for nom, source, _miroir in trouvees:
            with self.subTest(nom=nom):
                self.assertTrue(source.is_file(), f"source Claude absente : {source}")

    def test_chaque_miroir_reprend_sa_source(self) -> None:
        for nom, source, miroir in paires():
            with self.subTest(nom=nom):
                attendu = corps_attendu(source.read_text(encoding="utf-8"))
                obtenu = corps_miroir(miroir.read_text(encoding="utf-8"))
                self.assertEqual(obtenu, attendu, f"{miroir} diverge de {source}")

    def test_front_matter_du_miroir(self) -> None:
        for nom, _source, miroir in paires():
            with self.subTest(nom=nom):
                texte = miroir.read_text(encoding="utf-8")
                self.assertTrue(texte.startswith("---\n"), "front-matter hors ligne 1")
                self.assertIn(f'name: "source-command-{nom}"', _entete(texte))
                self.assertNotIn("\nEffort:", texte, "ligne Effort: propre à Claude Code")

    def test_controle_negatif_derivation(self) -> None:
        """La dérivation retire bien `Effort:` et applique les trois traductions : sans quoi
        le banc comparerait deux textes également faux (L-00000232)."""
        source = ("---\ndescription: x\n---\n\nEffort: y\n\n1. a\n2. Claude Code session\n"
                  "3. run `/skills-sync`, see `.agents/skills/index/SKILL.md`\n"
                  "4. promoted to `.claude/skills/`\n")
        self.assertEqual(
            corps_attendu(source, ["index", "skills-sync"]),
            "1. a\n2. Codex session\n3. run `$skills-sync`, see `.agents/skills/index/SKILL.md`\n"
            f"4. promoted to {SKILLS_HOTE_NEUTRE}\n")
        # Non-vacuité sur l'arbre réel : au moins une source porte `Effort:`, donc le retrait
        # est exercé par `test_chaque_miroir_reprend_sa_source` (toutes n'en portent pas).
        self.assertTrue(any("Effort:" in s.read_text(encoding="utf-8") for _n, s, _m in paires()),
                        "aucune source miroitée ne porte Effort: — le retrait n'est plus exercé")

    def test_chaque_miroir_nomme_sa_skill_partagee(self) -> None:
        """La ligne `Shared process reference:` vit dans la SOURCE (le renderer n'ajoute rien) :
        un miroir dont la skill partagée existe la nomme, sinon Codex et Copilot la perdent."""
        vus = 0
        for nom, _source, miroir in paires():
            if (ROOT / ".agents" / "skills" / nom / "SKILL.md").is_file():
                vus += 1
                with self.subTest(nom=nom):
                    self.assertIn(f"Shared process reference: `.agents/skills/{nom}/SKILL.md`",
                                  miroir.read_text(encoding="utf-8"))
        self.assertGreater(vus, 0, "aucune skill partagée vue — le témoin serait vide")

    def test_commandes_claude_seules_jamais_traduites(self) -> None:
        """`/night` existe sur disque mais reste `/` dans un miroir : le traduire
        promettrait à Codex et Copilot une commande que leur hôte refuse."""
        for nom in CLAUDE_SEULES:
            self.assertTrue((COMMANDES / f"{nom}.md").is_file(), nom)
        commandes = _noms_de_commandes()
        self.assertFalse(CLAUDE_SEULES & set(commandes), commandes)
        self.assertIn("skills-sync", commandes)
        source = "---\ndescription: x\n---\n\nrun `/night`, or `/skills-sync`\n"
        self.assertEqual(corps_attendu(source),
                         "run `/night`, or `$skills-sync`\n")


def _entete(texte: str) -> str:
    return texte[: len(texte) - len(_sans_front_matter(texte))]


if __name__ == "__main__":
    unittest.main()
