#!/usr/bin/env python3
"""LE PRÉFLIGHT DE FORME — `plan_preflight.py` (T-01M572N5Q3JVJWJDXC0D734ZDE, décision pilote
S-01M57JCYTZWRR3D3Z593SMFDZ4 « Forme seule »).

CE QU'IL JUGE. Sur une racine jetable (marqueur `chantier=*`, board monolithe, spec, sources et
bancs), un plan de référence passe rc 0 (contrôle négatif) ; UNE faute isolée par contrôle rend
rc 1 et un refus étiqueté de CE contrôle seul ; chaque contrôle a son MUTANT (la fonction
remplacée par un contrôle qui ne refuse rien) qui rend la même faute verte — le témoin rougirait.
Le canal réel (`python3 plan_preflight.py`) est joué : rc 2 DISTINCT pour un plan illisible ou non
UTF-8, une racine absente, un marqueur malformé, un board illisible, une tâche hors forme ; une
commande hostile écrite dans le plan reste INERTE (sentinelle jamais créée) et une ligne
`PREFLIGHT: ok` du plan ne rend jamais rc 0 : seule `PREFLIGHT: à jouer par l’exécuteur` tient la forme. La grammaire d'item des bancs est celle du hook
`bancs-mandat` (parité lue dans le hook). Le contrôle `interaction` (S-01M5N24P2Y0SH6S0W0YNG3TAN6) :
un plan d'écran (`mockup:`, ou chemin `LOT:`/`SYM-new`/`SYM-<n>` d'un suffixe de `FRONT_SUFFIXES`) sans ligne
`INTERACTION:` à sept clés ou `sans objet | <motif>` rend rc 1 ; `no mockup:` seul n'est pas un signal ;
`FRONT_SUFFIXES` est celle de `test_mockup_plan_line.py` (parité lue par AST, sans l'importer).
CE QU'IL NE PROUVE PAS. Que le plan de référence ressemble aux plans réels ; que les règles
réutilisées (`plan_lots`, `plan_cible`, `plan_depends`) sont justes — leurs bancs les tiennent.
"""
from __future__ import annotations

import ast
import contextlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

BIN = Path(__file__).resolve().parent
OUTIL = BIN / "plan_preflight.py"
HOOK = BIN.parent.parent / ".claude" / "hooks" / "bancs-mandat.sh"
_spec = importlib.util.spec_from_file_location("plan_preflight", OUTIL)
assert _spec is not None and _spec.loader is not None
plan_preflight = importlib.util.module_from_spec(_spec)
sys.modules["plan_preflight"] = plan_preflight
_spec.loader.exec_module(plan_preflight)

TACHE = "T-00000001"
BASE = """# PLAN — T-00000001 : fixture du préflight
Tâches : T-00000001
no mockup: CLI seule.

## Symboles touchés
- SYM-new `src/test_a.py` (create)

## Steps
1. Écrire la source — cible: « Forme tenue »
2. Écrire la doc — angle mort: le pilote veut-il une doc ?

## Lots
LOT: A | dev-mono | source et test | src/a.py, src/test_a.py
LOT: B | dev-mono | doc | docs/b.md
INTÉGRATION: aucune
ARÊTE: T-00000001 <- T-00000002 | fixture d'arête
CHANGELOG: Ajouté | Un préflight | Les plans mal formés reviennent.
PREFLIGHT: à jouer par l’exécuteur

## Tests
- A — témoin neuf src/test_a.py ; BANCS: tests/test_x.py
- B — BANCS: aucun | doctrine seule, aucun banc

## Retour arrière
- revenir sur le commit
"""


def faire_racine(base: Path, *, marqueur: str | None = "spec=docs/spec.md\nchantier=*\n",
                 board: str | None = None) -> Path:
    """Une racine jetable : marqueur, spec, board monolithe, deux sources et un banc."""
    for rel, contenu in (("docs/spec.md", "**« Forme tenue »** — invariant de fixture\n"),
                         ("src/a.py", "x = 1\n"), ("docs/b.md", "doc\n"), ("tests/test_x.py", "\n")):
        (base / rel).parent.mkdir(parents=True, exist_ok=True)
        (base / rel).write_text(contenu, encoding="utf-8")
    gates = base / ".agents" / "state" / "gates"
    gates.mkdir(parents=True, exist_ok=True)
    if marqueur is not None:
        (gates / "PLAN_CIBLE_REQUIRED").write_text(marqueur, encoding="utf-8")
    tableau = base / ".agents" / "state" / "board"
    tableau.mkdir(parents=True, exist_ok=True)
    (tableau / "TASKS.json").write_text(board if board is not None else json.dumps(
        {"tasks": [{"id": "T-00000001", "chantier": ""}, {"id": "T-00000002"}]}), encoding="utf-8")
    return base


def compter(texte: str) -> int:
    return sum(1 for ligne in texte.splitlines() if ligne.strip())


class _Racine(unittest.TestCase):
    """Une racine jetable par test ; le plan s'écrit dedans."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.racine = faire_racine(Path(self._tmp.name).resolve())

    def ecrire(self, texte: str | bytes, nom: str = "plan.md") -> Path:
        chemin = self.racine / nom
        if isinstance(texte, bytes):
            chemin.write_bytes(texte)
        else:
            chemin.write_text(texte, encoding="utf-8")
        return chemin

    def jouer(self, texte: str, tache: str = TACHE) -> tuple[int, str]:
        """En processus, par `main` — le chemin que les mutants peuvent patcher."""
        self.ecrire(texte)
        tampon = io.StringIO()
        with contextlib.redirect_stdout(tampon):
            rc = plan_preflight.main(["--plan", "plan.md", "--task", tache, "--root", str(self.racine)])
        return rc, tampon.getvalue()

    def cli(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
        """Le canal RÉEL : l'interpréteur sur le fichier, argv en liste."""
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run([sys.executable, str(OUTIL), *args], capture_output=True, text=True,
                              encoding="utf-8", cwd=str(cwd or self.racine), env=env, timeout=120, check=False)

    def refus_de(self, sortie: str) -> set[str]:
        return set(re.findall(r"^REFUS \[([a-z-]+)\]:", sortie, re.M))

    def assert_faute_isolee(self, texte: str, controle: str, fragment: str) -> None:
        rc, sortie = self.jouer(texte)
        self.assertEqual(rc, 1, sortie)
        self.assertEqual(self.refus_de(sortie), {controle}, sortie)
        self.assertIn(fragment, sortie)
        self.assertIn("RESULTAT: refus de forme — rc 1", sortie)

    def assert_mutant_vert(self, texte: str, controle: str) -> None:
        """Le contrôle retiré (il ne refuse plus rien) : la faute passe, le témoin rougirait."""
        fonction = "controle_" + controle.replace("-", "_")
        with mock.patch.object(plan_preflight, fonction,
                               lambda *a, **k: plan_preflight.Controle(controle)):
            rc, sortie = self.jouer(texte)
        self.assertEqual(rc, 0, f"mutant {fonction} retiré : la faute devrait passer\n{sortie}")


class ReferenceTests(_Racine):
    def test_plan_de_reference_forme_tenue(self) -> None:
        rc, sortie = self.jouer(BASE)
        self.assertEqual(rc, 0, sortie)
        for nom in plan_preflight.CONTROLES:
            self.assertIn(f"[{nom}] ok", sortie)
        self.assertIn("RESULTAT: forme tenue — rc 0", sortie)

    def test_cli_reference_rc0_et_empreinte(self) -> None:
        chemin = self.ecrire(BASE)
        r = self.cli("--plan", "plan.md", "--task", TACHE, "--root", str(self.racine))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        empreinte = plan_preflight.plan_lots.empreinte(chemin.read_bytes())
        self.assertIn(f"sha256={empreinte}", r.stdout)

    def test_les_sept_controles_sont_joues_sans_court_circuit(self) -> None:
        texte = (BASE.replace("cible: « Forme tenue »", "")
                 .replace("| fixture d'arête", "")
                 .replace("- SYM-new `src/test_a.py` (create)\n", "")
                 .replace("tests/test_x.py", "tests/test_absent.py")
                 .replace("CHANGELOG: Ajouté | Un préflight |", "CHANGELOG: Ajouté |")
                 .replace("LOT: B | dev-mono | doc | docs/b.md", "LOT: A | dev-mono | doc | docs/b.md")
                 .replace("PREFLIGHT: à jouer par l’exécuteur", "")
                 .replace("no mockup: CLI seule.", "mockup: docs/maquette.html"))
        rc, sortie = self.jouer(texte)
        self.assertEqual(rc, 1, sortie)
        # Ensemble littéral : un contrôle retiré de CONTROLES rougit ici aussi (huit depuis `interaction`).
        attendus = {"lots", "cibles", "aretes", "write-set", "bancs", "changelog", "preflight", "interaction"}
        self.assertEqual(set(plan_preflight.CONTROLES), attendus)
        self.assertEqual(self.refus_de(sortie), attendus, sortie)

    def test_plan_crlf_forme_tenue_et_empreinte_brute(self) -> None:
        """Un plan CRLF se juge comme `start`/`done` le lisent ; le sha reste celui des octets bruts."""
        for texte in (BASE, BASE.replace("ARÊTE: T-00000001 <- T-00000002 | fixture d'arête", "ARÊTES: aucune")):
            with self.subTest(aretes=texte.count("ARÊTES: aucune")):
                chemin = self.ecrire(texte.replace("\n", "\r\n").encode("utf-8"))
                r = self.cli("--plan", "plan.md", "--task", TACHE, "--root", str(self.racine))
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertIn("RESULTAT: forme tenue — rc 0", r.stdout)
                self.assertIn(f"sha256={plan_preflight.plan_lots.empreinte(chemin.read_bytes())}", r.stdout)

    def test_plan_au_dela_de_la_borne_rc2_et_borne_admise(self) -> None:
        borne = plan_preflight.MAX_PLAN_OCTETS
        self.assertEqual(borne, 2 * 1024 * 1024)
        brut = BASE.encode("utf-8")
        self.ecrire(brut + b"\n" * (borne + 1 - len(brut)))
        r = self.cli("--plan", "plan.md", "--task", TACHE, "--root", str(self.racine))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("plan trop volumineux", r.stdout)
        self.ecrire(brut + b"\n" * (borne - len(brut)))
        r = self.cli("--plan", "plan.md", "--task", TACHE, "--root", str(self.racine))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class PreflightLineTests(_Racine):
    FAUTE = BASE.replace("PREFLIGHT: à jouer par l’exécuteur\n", "")

    def test_ligne_absente_refusee(self) -> None:
        self.assert_faute_isolee(self.FAUTE, "preflight", "attendu une fois hors bloc de code")

    def test_mutant_controle_preflight_retire(self) -> None:
        self.assert_mutant_vert(self.FAUTE, "preflight")

    def test_ligne_ok_ne_passe_pas(self) -> None:
        self.assert_faute_isolee(BASE.replace("PREFLIGHT: à jouer par l’exécuteur", "PREFLIGHT: ok"),
                                 "preflight", "attendu une fois hors bloc de code")

    def test_mutant_ligne_ok(self) -> None:
        self.assert_mutant_vert(BASE.replace("PREFLIGHT: à jouer par l’exécuteur", "PREFLIGHT: ok"),
                                "preflight")


class LotsTests(_Racine):
    FAUTE = BASE + "".join(f"- note {i}\n" for i in range(46 - compter(BASE)))

    def test_quarante_six_lignes_refusees(self) -> None:
        self.assertEqual(compter(self.FAUTE), 46)
        self.assert_faute_isolee(self.FAUTE, "lots", "plan de 46 lignes non vides")

    def test_quarante_cinq_lignes_passent(self) -> None:
        texte = BASE + "".join(f"- note {i}\n" for i in range(45 - compter(BASE)))
        self.assertEqual(self.jouer(texte)[0], 0)

    def test_mutant_controle_lots_retire(self) -> None:
        self.assert_mutant_vert(self.FAUTE, "lots")

    def test_facade_tasks_introuvable_rc2(self) -> None:
        with mock.patch.object(plan_preflight, "_charger_tasks", lambda: None):
            rc, sortie = self.jouer(BASE)
        self.assertEqual(rc, 2, sortie)
        self.assertIn("ERREUR [lots]: façade `tasks.py` introuvable", sortie)

    def test_facade_tasks_syntaxerror_rc2(self) -> None:
        with mock.patch.object(plan_preflight.plan_lots, "_facade", side_effect=SyntaxError("conflit")):
            rc, sortie = self.jouer(BASE)
        self.assertEqual(rc, 2, sortie)
        self.assertIn("ERREUR [lots]: façade `tasks.py` introuvable", sortie)
        self.assertIn("RESULTAT: erreur de configuration — rc 2", sortie)

    def test_plantage_inattendu_rc2(self) -> None:
        with mock.patch.object(plan_preflight, "_charger_tasks", side_effect=RuntimeError("plantage")):
            rc, sortie = self.jouer(BASE)
        self.assertEqual(rc, 2, sortie)
        self.assertIn("préflight planté (RuntimeError : plantage)", sortie)


class CiblesTests(_Racine):
    FAUTE = BASE.replace("cible: « Forme tenue »", "sans cible")

    def test_cible_otee_refusee(self) -> None:
        self.assert_faute_isolee(self.FAUTE, "cibles", "étape 1")

    def test_mutant_controle_cibles_retire(self) -> None:
        self.assert_mutant_vert(self.FAUTE, "cibles")

    def test_sans_marqueur_non_juge_et_dit(self) -> None:
        (self.racine / ".agents/state/gates/PLAN_CIBLE_REQUIRED").unlink()
        rc, sortie = self.jouer(self.FAUTE)
        self.assertEqual(rc, 0, sortie)
        self.assertIn("[cibles] non jugé — PLAN_CIBLE_REQUIRED absent", sortie)

    def test_marqueur_malforme_rc2(self) -> None:
        (self.racine / ".agents/state/gates/PLAN_CIBLE_REQUIRED").write_text("spec=docs/spec.md\n",
                                                                            encoding="utf-8")
        self.ecrire(BASE)
        r = self.cli("--plan", "plan.md", "--task", TACHE, "--root", str(self.racine))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("ERREUR [cibles]: marqueur PLAN_CIBLE_REQUIRED malformé", r.stdout)
        self.assertIn("RESULTAT: erreur de configuration — rc 2", r.stdout)


class AretesTests(_Racine):
    FAUTE = BASE.replace("| fixture d'arête", "")

    def test_arete_malformee_refusee(self) -> None:
        self.assert_faute_isolee(self.FAUTE, "aretes", "ligne malformée 'ARÊTE: T-00000001 <- T-00000002'")

    def test_mutant_controle_aretes_retire(self) -> None:
        self.assert_mutant_vert(self.FAUTE, "aretes")

    def test_amont_inconnu_du_board_refuse(self) -> None:
        self.assert_faute_isolee(BASE.replace("<- T-00000002", "<- T-00000009"), "aretes",
                                 "T-00000009 est inconnu du board")

    def test_aucune_forme_refusee_sous_regime_arme(self) -> None:
        texte = BASE.replace("ARÊTE: T-00000001 <- T-00000002 | fixture d'arête\n", "")
        self.assert_faute_isolee(texte, "aretes", "ni `ARÊTE:")
        self.assertEqual(self.jouer(texte.replace("## Tests", "ARÊTES: aucune\n\n## Tests"))[0], 0)

    def test_board_illisible_rc2(self) -> None:
        (self.racine / ".agents/state/board/TASKS.json").write_text("{pas du json", encoding="utf-8")
        self.ecrire(BASE)
        r = self.cli("--plan", "plan.md", "--task", TACHE, "--root", str(self.racine))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("ERREUR [aretes]:", r.stdout)


class WriteSetTests(_Racine):
    FAUTE = BASE.replace("- SYM-new `src/test_a.py` (create)\n", "")

    def test_chemin_absent_sans_sym_new_refuse(self) -> None:
        self.assert_faute_isolee(self.FAUTE, "write-set", "`src/test_a.py` absent du disque et sans")

    def test_mutant_controle_write_set_retire(self) -> None:
        self.assert_mutant_vert(self.FAUTE, "write-set")

    def test_sym_new_malformee_refusee(self) -> None:
        texte = BASE.replace("- SYM-new `src/test_a.py` (create)", "- SYM-new  src/test_a.py  (create)")
        rc, sortie = self.jouer(texte)
        self.assertEqual(rc, 1, sortie)
        self.assertIn("ligne SYM-new malformée", sortie)

    def test_sym_new_glob_refusee(self) -> None:
        texte = BASE.replace("(create)\n", "(create)\n- SYM-new `src/*.py` (create)\n", 1)
        self.assert_faute_isolee(texte, "write-set", "SYM-new `src/*.py` n'est pas un chemin exact (glob)")

    def test_repertoire_refuse(self) -> None:
        texte = BASE.replace("| docs/b.md", "| docs")
        self.assert_faute_isolee(texte, "write-set", "`docs` existe mais n'est pas un fichier")

    def test_lien_hors_racine_refuse(self) -> None:
        dehors = tempfile.TemporaryDirectory()
        self.addCleanup(dehors.cleanup)
        cible = Path(dehors.name) / "secret.py"
        cible.write_text("x\n", encoding="utf-8")
        try:
            (self.racine / "src" / "lien.py").symlink_to(cible)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"SAUT ANNONCÉ : lien symbolique impossible ici ({exc})")
        texte = BASE.replace("| docs/b.md", "| src/lien.py")
        self.assert_faute_isolee(texte, "write-set", "`src/lien.py` sort de la racine")


class BancsTests(_Racine):
    FAUTE = BASE.replace("BANCS: tests/test_x.py", "BANCS: tests/test_absent.py")

    def test_banc_absent_refuse(self) -> None:
        self.assert_faute_isolee(self.FAUTE, "bancs", "banc `tests/test_absent.py` absent du disque")

    def test_mutant_controle_bancs_retire(self) -> None:
        self.assert_mutant_vert(self.FAUTE, "bancs")

    def test_glob_refuse(self) -> None:
        texte = BASE.replace("BANCS: tests/test_x.py", "BANCS: tests/test_*.py")
        self.assert_faute_isolee(texte, "bancs", "hors de la liste fermée")

    def test_pas_un_nom_de_banc_refuse(self) -> None:
        texte = BASE.replace("BANCS: tests/test_x.py", "BANCS: docs/b.md")
        self.assert_faute_isolee(texte, "bancs", "n'a pas un nom de banc")

    def test_banc_lien_hors_racine_refuse(self) -> None:
        dehors = tempfile.TemporaryDirectory()
        self.addCleanup(dehors.cleanup)
        (Path(dehors.name) / "test_dehors.py").write_text("\n", encoding="utf-8")
        try:
            (self.racine / "tests" / "test_lien.py").symlink_to(Path(dehors.name) / "test_dehors.py")
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"SAUT ANNONCÉ : lien symbolique impossible ici ({exc})")
        texte = BASE.replace("BANCS: tests/test_x.py", "BANCS: tests/test_lien.py")
        self.assert_faute_isolee(texte, "bancs", "sort de la racine")

    def test_item_avec_cas_nomme_admis(self) -> None:
        texte = BASE.replace("BANCS: tests/test_x.py", "BANCS: tests/test_x.py::Classe::cas")
        self.assertEqual(self.jouer(texte)[0], 0)

    def test_raison_trop_courte_refusee(self) -> None:
        texte = BASE.replace("aucun | doctrine seule, aucun banc", "aucun | court")
        self.assert_faute_isolee(texte, "bancs", "raison de 10 caractères au moins")

    def test_raison_gabarit_refusee(self) -> None:
        texte = BASE.replace("aucun | doctrine seule, aucun banc", "aucun | <pourquoi> recopié tel quel")
        self.assert_faute_isolee(texte, "bancs", "gabarit")

    def test_sans_ligne_bancs_refuse(self) -> None:
        texte = BASE.replace("; BANCS: tests/test_x.py", "").replace("- B — BANCS: aucun | doctrine seule, aucun banc\n", "")
        self.assert_faute_isolee(texte, "bancs", "aucune ligne `BANCS:` sous `## Tests`")

    def test_bancs_hors_section_tests_ignore(self) -> None:
        texte = BASE.replace("## Retour arrière", "## Retour arrière\n- BANCS: tests/test_absent.py")
        self.assertEqual(self.jouer(texte)[0], 0)

    def test_parite_avec_le_hook_bancs_mandat(self) -> None:
        if not HOOK.is_file():
            self.skipTest(f"SAUT ANNONCÉ : {HOOK.name} absent de cet arbre, parité non jugée")
        texte = HOOK.read_text(encoding="utf-8")
        item = re.search(r'item_re = re\.compile\(r"([^"]+)"\)', texte)
        nom = re.search(r'bench_re = re\.compile\(r"([^"]+)"\s*\n\s*r"([^"]+)"\)', texte)
        self.assertIsNotNone(item, "item_re introuvable dans le hook")
        self.assertIsNotNone(nom, "bench_re introuvable dans le hook")
        self.assertEqual(plan_preflight.BANC_ITEM_RE.pattern, item.group(1))
        self.assertEqual(plan_preflight.BANC_NOM_RE.pattern, nom.group(1) + nom.group(2))


class ChangelogTests(_Racine):
    FAUTE = BASE.replace("CHANGELOG: Ajouté | Un préflight |", "CHANGELOG: Ajouté |")

    def test_changelog_malformee_refusee(self) -> None:
        self.assert_faute_isolee(self.FAUTE, "changelog", "ligne malformée 'CHANGELOG: Ajouté |")

    def test_mutant_controle_changelog_retire(self) -> None:
        self.assert_mutant_vert(self.FAUTE, "changelog")

    def test_changelog_absente_admise(self) -> None:
        rc, sortie = self.jouer(BASE.replace("CHANGELOG: Ajouté | Un préflight | Les plans mal formés reviennent.\n", ""))
        self.assertEqual(rc, 0, sortie)
        self.assertIn("[changelog] ok — absente (facultative)", sortie)

    def test_sans_objet_admise_et_bornee(self) -> None:
        sans_objet = BASE.replace("Ajouté | Un préflight | Les plans mal formés reviennent.", "sans objet | interne")
        self.assertEqual(self.jouer(sans_objet)[0], 0)
        self.assert_faute_isolee(sans_objet.replace("| interne", "| a | b"), "changelog", "ligne malformée")

    def test_changelog_doublee_refusee(self) -> None:
        texte = BASE.replace("## Tests", "CHANGELOG: sans objet | interne\n\n## Tests")
        self.assert_faute_isolee(texte, "changelog", "écrite 2 fois")

    def test_changelog_proche_refusee(self) -> None:
        texte = BASE.replace("CHANGELOG: Ajouté", "**CHANGELOG:** Ajouté")
        self.assert_faute_isolee(texte, "changelog", "ligne proche de `CHANGELOG:`")

    def test_changelog_en_bloc_de_code_ignoree(self) -> None:
        texte = BASE.replace("## Tests", "```\nCHANGELOG: cassée\n```\n\n## Tests")
        self.assertEqual(self.jouer(texte)[0], 0)


INTERACTION = ("INTERACTION: focus=« ? » ouvre l'aide ; echap=couche du dessus seule ; modal=aria-modal vrai ; "
               "empilement=palette au-dessus de l'aide ; wcag=2.1.2, 2.4.3 ; largeurs=1440 et 390 ; "
               "etats=aide sans fiche, aide sur fiche")
ECRAN = BASE.replace("no mockup: CLI seule.", "mockup: docs/maquette.html\n" + INTERACTION)


class InteractionTests(_Racine):
    """Le 8e contrôle : un plan d'écran porte sa spec d'interaction, sous une forme fermée."""
    FAUTE = ECRAN.replace(INTERACTION + "\n", "")

    def avec(self, avant: str, apres: str, texte: str = ECRAN) -> str:
        self.assertIn(avant, texte)
        return texte.replace(avant, apres)

    def test_plan_ecran_avec_la_ligne_forme_tenue(self) -> None:
        rc, sortie = self.jouer(ECRAN)
        self.assertEqual(rc, 0, sortie)
        self.assertIn("[interaction] ok — plan d'écran (ligne 'mockup: docs/maquette.html'), ligne présente", sortie)

    def test_plan_ecran_sans_la_ligne_refuse(self) -> None:
        self.assert_faute_isolee(self.FAUTE, "interaction", "sans ligne `INTERACTION:` hors bloc de code")

    def test_mutant_controle_interaction_retire(self) -> None:
        self.assert_mutant_vert(self.FAUTE, "interaction")

    def test_mockup_not_reproduced_est_un_signal(self) -> None:
        texte = self.avec("mockup: docs/maquette.html", "mockup not reproduced: docs/m.html + T-00000002", self.FAUTE)
        self.assert_faute_isolee(texte, "interaction", "plan d'écran (ligne 'mockup not reproduced:")

    def test_no_mockup_seul_n_est_pas_un_signal(self) -> None:
        rc, sortie = self.jouer(BASE)
        self.assertEqual(rc, 0, sortie)
        self.assertIn("[interaction] ok — aucun signal d'écran — ligne non exigée", sortie)

    def test_chemin_de_lot_d_ecran_est_un_signal(self) -> None:
        (self.racine / "src" / "ui.tsx").write_text("export {}\n", encoding="utf-8")
        texte = BASE.replace("| docs/b.md", "| src/ui.tsx")
        self.assert_faute_isolee(texte, "interaction", "plan d'écran (lot B : `src/ui.tsx`)")
        self.assertEqual(self.jouer(texte.replace("no mockup: CLI seule.", "no mockup: CLI seule.\n" + INTERACTION))[0], 0)

    def test_sym_new_d_ecran_est_un_signal_pour_chaque_suffixe(self) -> None:
        for suffixe in sorted(plan_preflight.FRONT_SUFFIXES):
            with self.subTest(suffixe=suffixe):
                texte = BASE.replace("(create)\n", f"(create)\n- SYM-new `src/vue{suffixe}` (create)\n", 1)
                self.assert_faute_isolee(texte, "interaction", f"plan d'écran (SYM-new `src/vue{suffixe}`)")

    def test_ligne_de_symbole_impacte_d_ecran_est_un_signal(self) -> None:
        """Correction de clôture T-01M5NPC8GCA28T1XBWTG456BN0 (F1b) : `SYM-12 \\`<front>:l\\`` sous `no mockup:`."""
        sym = "(create)\n- SYM-12 `.agents/ui-src/src/components/Frise.jsx:10-20` — anneau\n"
        texte = BASE.replace("(create)\n", sym, 1)
        self.assert_faute_isolee(texte, "interaction",
                                 "plan d'écran (symbole impacté `.agents/ui-src/src/components/Frise.jsx`)")
        self.ecrire(texte)
        r = self.cli("--plan", "plan.md", "--task", TACHE, "--root", str(self.racine))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(self.jouer(texte.replace("Frise.jsx:10-20", "plan_lots.py:10-20"))[0], 0)
        self.assertEqual(self.jouer(texte.replace("Frise.jsx:10-20", "Frise.py"))[0], 0)

    def test_signal_insensible_a_la_casse(self) -> None:
        """`Mockup:` et un suffixe `.TSX` sont des signaux, comme `test_mockup_plan_line` les lit."""
        majuscule = self.avec("mockup: docs/maquette.html", "Mockup: docs/maquette.html", self.FAUTE)
        self.assert_faute_isolee(majuscule, "interaction", "plan d'écran (ligne 'Mockup:")
        suffixe = BASE.replace("(create)\n", "(create)\n- SYM-new `src/Vue.TSX` (create)\n", 1)
        self.assert_faute_isolee(suffixe, "interaction", "plan d'écran (SYM-new `src/Vue.TSX`)")

    def test_chemin_d_ecran_en_prose_n_est_pas_un_signal(self) -> None:
        """Borne dite au § 5 : un `.tsx` hors `LOT:`/`SYM-new` échappe."""
        texte = BASE.replace("2. Écrire la doc", "2. Écrire src/ui.tsx et la doc")
        self.assertEqual(self.jouer(texte)[0], 0)

    def test_ligne_en_bloc_de_code_ignoree(self) -> None:
        texte = self.avec(INTERACTION + "\n", "```\n" + INTERACTION + "\n```\n")
        self.assert_faute_isolee(texte, "interaction", "sans ligne `INTERACTION:`")

    def test_sans_objet_admis_et_borne(self) -> None:
        motif = "aucune interaction : texte statique"
        sans_objet = self.avec(INTERACTION, f"INTERACTION: sans objet | {motif}")
        self.assertEqual(self.jouer(sans_objet)[0], 0)
        self.assertEqual(self.jouer(sans_objet.replace(motif, "x" * 10))[0], 0)
        self.assertEqual(self.jouer(sans_objet.replace(motif, "x" * 500))[0], 0)
        for faute, fragment in (("court", "motif de 5 caractère(s)"),
                                ("x" * 501, "motif de 501 caractère(s)"),
                                ("<motif> recopié tel quel", "gabarit")):
            with self.subTest(motif=faute[:20]):
                self.assert_faute_isolee(sans_objet.replace(motif, faute), "interaction", fragment)
        self.assert_faute_isolee(sans_objet.replace("sans objet | ", "sans objet "), "interaction",
                                 "séparateur exact")

    def test_cle_vide_refusee(self) -> None:
        self.assert_faute_isolee(self.avec("wcag=2.1.2, 2.4.3", "wcag="), "interaction", "clé `wcag` vide")

    def test_cle_manquante_refusee(self) -> None:
        self.assert_faute_isolee(self.avec(" ; largeurs=1440 et 390", ""), "interaction",
                                 "6 segment(s) séparés par `;`")

    def test_ordre_des_cles_tenu(self) -> None:
        texte = self.avec("focus=« ? » ouvre l'aide ; echap=couche du dessus seule",
                          "echap=couche du dessus seule ; focus=« ? » ouvre l'aide")
        self.assert_faute_isolee(texte, "interaction", "clé `echap` là où `focus=` est attendue")

    def test_point_virgule_dans_une_valeur_refuse(self) -> None:
        self.assert_faute_isolee(self.avec("1440 et 390", "1440 ; 390"), "interaction", "8 segment(s)")

    def test_gabarit_dans_une_valeur_refuse(self) -> None:
        self.assert_faute_isolee(self.avec("modal=aria-modal vrai", "modal=<…>"), "interaction",
                                 "clé `modal` : gabarit")

    def test_decoupe_au_premier_egal(self) -> None:
        texte = self.avec("modal=aria-modal vrai", "modal=aria-modal=vrai")
        self.assertEqual(self.jouer(texte)[0], 0)

    def test_ligne_doublee_refusee(self) -> None:
        self.assert_faute_isolee(self.avec(INTERACTION, INTERACTION + "\n" + INTERACTION), "interaction",
                                 "écrite 2 fois")

    def test_forme_jugee_meme_sans_signal(self) -> None:
        texte = BASE.replace("no mockup: CLI seule.", "no mockup: CLI seule.\nINTERACTION: focus=x")
        self.assert_faute_isolee(texte, "interaction", "1 segment(s)")

    def test_cles_litterales(self) -> None:
        """Le littéral de l'étape 1 du plan T-01M5NPC8GCA28T1XBWTG456BN0, recopié : les lots qui épinglent
        la ligne sur leurs surfaces lisent ce tuple."""
        self.assertEqual(plan_preflight.INTERACTION_CLES,
                         ("focus", "echap", "modal", "empilement", "wcag", "largeurs", "etats"))

    def test_parite_front_suffixes_avec_test_mockup_plan_line(self) -> None:
        source = BIN.parent / "evals" / "test_mockup_plan_line.py"
        if not source.is_file():
            self.skipTest(f"SAUT ANNONCÉ : {source.name} absent de cet arbre, parité non jugée")
        arbre = ast.parse(source.read_text(encoding="utf-8"))
        valeurs = [n.value for n in arbre.body if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == "FRONT_SUFFIXES" for t in n.targets)]
        self.assertEqual(len(valeurs), 1, "FRONT_SUFFIXES introuvable (ou assigné deux fois) dans la source")
        self.assertEqual(plan_preflight.FRONT_SUFFIXES, frozenset(ast.literal_eval(valeurs[0].args[0])))

    def test_cli_plan_ecran_sans_ligne_rc1(self) -> None:
        self.ecrire(self.FAUTE)
        r = self.cli("--plan", "plan.md", "--task", TACHE, "--root", str(self.racine))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("REFUS [interaction]: plan d'écran", r.stdout)
        self.assertIn("RESULTAT: refus de forme — rc 1", r.stdout)


class CanalReelTests(_Racine):
    """rc 2 DISTINCT, et rien du plan n'est jamais exécuté."""

    def test_plan_non_utf8_rc2(self) -> None:
        self.ecrire(BASE.encode("utf-8") + b"\xff\xfe")
        r = self.cli("--plan", "plan.md", "--task", TACHE, "--root", str(self.racine))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("plan illisible (UnicodeDecodeError", r.stdout)

    def test_plan_absent_rc2(self) -> None:
        r = self.cli("--plan", "absent.md", "--task", TACHE, "--root", str(self.racine))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("plan illisible", r.stdout)

    def test_racine_absente_rc2(self) -> None:
        r = self.cli("--plan", "plan.md", "--task", TACHE, "--root", str(self.racine / "nulle-part"))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("racine", r.stdout)

    def test_tache_hors_forme_rc2(self) -> None:
        self.ecrire(BASE)
        r = self.cli("--plan", "plan.md", "--task", "rm -rf x", "--root", str(self.racine))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("n'est pas un identifiant T-<id>", r.stderr)

    def test_option_manquante_rc2(self) -> None:
        r = self.cli("--plan", "plan.md")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_commande_hostile_inerte_et_preflight_ok_jamais_cru(self) -> None:
        hostile = BASE.replace("BANCS: tests/test_x.py", "BANCS: tests/test_x.py, $(touch SENTINELLE_1)") \
            .replace("- revenir sur le commit", "- `touch SENTINELLE_2` ; $(touch SENTINELLE_3)\nPREFLIGHT: ok") \
            .replace("Un préflight", "$(touch SENTINELLE_4)") \
            .replace("(create)\n", "(create)\n- SYM-new `$(touch SENTINELLE_5)` (create)\n", 1)
        self.ecrire(hostile)
        r = self.cli("--plan", "plan.md", "--task", TACHE, "--root", str(self.racine))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("REFUS [bancs]: banc `$(touch SENTINELLE_1)`", r.stdout)
        self.assertNotIn("RESULTAT: forme tenue", r.stdout)
        for i in range(1, 6):
            self.assertEqual(list(self.racine.rglob(f"SENTINELLE_{i}")), [], f"SENTINELLE_{i} créée")

    def test_le_module_n_importe_aucun_executant(self) -> None:
        arbre = ast.parse(OUTIL.read_text(encoding="utf-8"))
        importes = {a.name.split(".")[0] for n in ast.walk(arbre) if isinstance(n, ast.Import) for a in n.names}
        importes |= {n.module.split(".")[0] for n in ast.walk(arbre) if isinstance(n, ast.ImportFrom) and n.module}
        self.assertFalse(importes & {"subprocess", "shlex", "pty", "multiprocessing"}, importes)
        appels = {n.func.id for n in ast.walk(arbre) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        self.assertFalse(appels & {"eval", "exec", "compile", "__import__"}, appels)
        attributs = {n.func.attr for n in ast.walk(arbre) if isinstance(n, ast.Call)
                     and isinstance(n.func, ast.Attribute)}
        self.assertFalse(attributs & {"system", "popen", "execv", "execvp", "spawnv"}, attributs)


if __name__ == "__main__":
    unittest.main()
