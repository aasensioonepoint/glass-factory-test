"""Filet de T-01M4RWC6VHHN479J2A9RRY1BE3 (E-47, F4) : la sortie précoce des
hooks natifs sur les outils de LECTURE LOCALE, sous Copilot seulement.

Ce que le filet tient, et rien de plus :

  (i)     COPIE TEXTUELLE — le bloc `OUTILS_LECTURE_COPILOT` (de `# >>>` à
          `# <<<`) est identique, octet pour octet, à REFERENCE dans les cinq
          copies : les deux `_common.py` et les trois scripts shell à bloc. Une
          seule occurrence par copie.
  (i bis) VACUITÉ VOULUE — les consommateurs Python (protect_paths, safe_bash,
          audit_gate, post_edit_check, sous `.codex/hooks` ET `.gemini/hooks`)
          ne portent AUCUNE copie locale : ni bloc, ni liste, ni
          `def _lecture_copilot`. La garde vient de `_common` par import.
  (ii)    DISJONCTION — la liste est disjointe des noms exclus avec motif
          (EXCLUS_DE_LA_LISTE), des outils d'écriture de kickoff_guard
          (WRITE_TOOL_NAMES, clés de MULTIPLEXED_WRITE_TOOLS) et des outils qui
          écrivent ou exécutent ; chaque exclusion porte un motif non vide.
  (iii)   VERDICTS — en sous-processus, sur une fixture : `view` sous copilot
          est muet (rc 0, 0 octet, 0 événement) pour les quatre consommateurs ;
          tout le reste est jugé comme avant. Un refus se lit à
          `hookSpecificOutput.permissionDecision`, JAMAIS par comparaison du
          stdout à l'octet (C5 du plan). post_edit_check joue sur un arbre FAUTIF
          (C2) : sur un arbre propre il est muet de toute façon, et le mutant
          « garde retirée » y survivrait.
  (iv)    UNITAIRE — `lecture_copilot`, chargé PAR CHEMIN, environnement patché ;
          et les trois programmes shell décident comme lui sur la même matrice.
          Le jumeau Gemini la joue aussi, son `event_host` forcé à copilot.
          Matrice comprise : la forme HYBRIDE (nom listé au premier niveau ET
          `toolCalls` ou `tool_calls`) et deux graphies du nom en désaccord
          rendent FAUX — F2 de la revue de clôture, classe 0 : un second outil
          porté à côté du nom listé sortait sans scan.
  (iv bis) BOUT EN BOUT — les trois scripts, sur ces charges, gardent le
          chemin entier : bouchon `git` appelé ; `view` nu ne l'appelle pas.
  (v)     RÉINJECTION — la charge d'un nom non listé revient au scanner par une
          here-string SANS numéro de descripteur, jamais par une substitution de
          processus (fail-open si `/dev/fd` ou la fifo manque) ; son échec est
          relevé selon le script : gitleaks BLOQUE (rc 2, mesuré sur un mutant
          dont la redirection échoue), semgrep l'annonce, sca n'a aucun lecteur.

Plus les contrôles négatifs : une copie qui diffère, `create` ajouté, un bloc
remis dans safe_bash.py, une exclusion sans motif, une réinjection fautive —
chacun doit ROUGIR.

Source : docs/tasks/T-01M4RWBSR48YW8RPAV7TG6HKET-plan.md, révision 5, section
« T-00001247 » (ancien id). Décisions S-01M4RWM3TC4JWE5FDC8YB819Z4 et
S-01M4RWM6VG0M0THSNDRJFV1090 : un outil IDENTIFIÉ POSITIVEMENT, jamais un trou.
"""
import ast
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
# `cadre` résolu par vendor_paths chargé PAR CHEMIN, vendor d'abord (S-01M5BXT85VP4JBBMXVXR9STP5F).
_SPEC_VP = importlib.util.spec_from_file_location("_cee_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
assert _SPEC_VP is not None and _SPEC_VP.loader is not None
_VP = sys.modules[_SPEC_VP.name] = importlib.util.module_from_spec(_SPEC_VP)
_SPEC_VP.loader.exec_module(_VP)

DEBUT = "# >>> OUTILS_LECTURE_COPILOT"
FIN = "# <<< OUTILS_LECTURE_COPILOT"

# Le bloc de RÉFÉRENCE. ASCII seulement et SANS apostrophe : dans les scripts
# shell il vit à l'intérieur d'un `"$PY" -c '…'`, où une apostrophe fermerait la
# chaîne. Les cinq copies doivent le porter tel quel.
REFERENCE = '''\
# >>> OUTILS_LECTURE_COPILOT (bloc jumeau, 5 copies : test_copilot_early_exit.py)
# Outils de LECTURE LOCALE sous Copilot : leurs arguments ne sortent pas du
# processus local. Liste POSITIVE et close, comparee au nom de premier niveau
# replie (minuscules, espaces otes, tiret vers souligne) ; tout autre nom est
# juge. Les noms exclus, et leur motif : EXCLUS_DE_LA_LISTE du filet.
OUTILS_LECTURE_COPILOT = (
    "view",  # Copilot CLI, mesure (M-P9) : path, view_range
    "grep",  # Copilot CLI, mesure (M-P9) : pattern, paths, output_mode
    "read_agent",  # Copilot CLI, mesure (M-P9) : agent_id, since_turn
    "list_agents",  # Copilot CLI, mesure (M-P9) : include_completed
    "read_file",  # Chat Local, documente, non mesure (U8)
    "file_search",  # Chat Local, documente, non mesure (U8)
    "grep_search",  # Chat Local, documente, non mesure (U8)
    "list_dir",  # Chat Local, documente, non mesure (U8)
)
# <<< OUTILS_LECTURE_COPILOT
'''

NOMS_ATTENDUS = (
    "view", "grep", "read_agent", "list_agents",
    "read_file", "file_search", "grep_search", "list_dir",
)

COPIES = (
    ".codex/hooks/_common.py",
    ".gemini/hooks/_common.py",
    ".agents/security/gitleaks-scan.sh",
    ".agents/security/sca-scan.sh",
    ".agents/security/semgrep-scan.sh",
)
SCRIPTS_SHELL = COPIES[2:]

# Table FERMÉE des noms écartés, chacun avec son motif (critère d'entrée C1 du
# plan : un argument qui n'atteint aucun destinataire hors du processus local,
# destination ÉTABLIE). Un nom d'ici qui entre dans une copie rougit (ii).
EXCLUS_DE_LA_LISTE = {
    "web_fetch": "sortie réseau : l'URL quitte le poste ; classe 0, gitleaks --content "
                 "la juge (rc 2 mesuré sur un faux jeton dans l'URL)",
    "web_search": "sortie réseau : la requête quitte le poste ; classe 0 (rc 2 mesuré)",
    "fetch_webpage": "sortie réseau : les URL quittent le poste ; classe 0 (rc 2 mesuré)",
    "semantic_search": "requête libre vers un index dont la destination, locale ou "
                       "distante, n'est pas établie (U8)",
    "tool_search_tool": "requête libre, destination non établie, gain nul "
                        "(1 appel sur 1 493)",
    "ask_user": "texte libre montré au pilote, gain nul (34 appels ; l'attente "
                "humaine domine le coût du hook)",
}

# Outils qui ÉCRIVENT ou EXÉCUTENT, hors des tables de kickoff_guard (étape 2).
ECRITURE_ET_EXECUTION = (
    "bash", "shell", "run_in_terminal", "powershell", "apply_patch",
    "create", "edit", "task", "write_agent", "sql",
)

# (i bis) ÉPINGLE DE VACUITÉ VOULUE (Piège 2 du plan) : ces fichiers ne doivent
# porter AUCUNE copie de la liste ni de la garde. Une copie locale réintroduite
# divergerait en silence de `_common.py`, que seul (i) compare.
CONSOMMATEURS_PY = tuple(
    f".{hote}/hooks/{module}.py"
    for hote in ("codex", "gemini")
    for module in ("protect_paths", "safe_bash", "audit_gate", "post_edit_check")
)
# Ceux qui portent la garde, importée de `_common` (les deux autres sortent par
# leur `if not command: return` existant, mesuré muet sur `view` à la base).
GARDES = tuple(p for p in CONSOMMATEURS_PY if p.endswith(("protect_paths.py", "post_edit_check.py")))


def lire(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def replier(nom):
    """Même repliement que kickoff_guard.fold_tool_name (SYM-00763)."""
    return str(nom or "").strip().lower().replace("-", "_")


def extraire_blocs(texte):
    """Chaque bloc `# >>> …` / `# <<< …`, lignes de bornes comprises."""
    blocs, courant = [], None
    for ligne in texte.splitlines(keepends=True):
        if ligne.startswith(DEBUT):
            courant = [ligne]
            continue
        if courant is not None:
            courant.append(ligne)
            if ligne.startswith(FIN):
                blocs.append("".join(courant))
                courant = None
    return blocs


def ecarts_copie(texte):
    """(i) Les écarts d'une copie à REFERENCE ; [] si elle la porte une fois, telle quelle."""
    blocs = extraire_blocs(texte)
    if len(blocs) != 1:
        return [f"{len(blocs)} bloc(s) au lieu d'un"]
    if blocs[0] != REFERENCE:
        return ["le bloc diffère de REFERENCE"]
    return []


def noms_du_bloc(bloc):
    """Les noms du tuple `OUTILS_LECTURE_COPILOT`, lus par l'AST (jamais à la regex)."""
    for noeud in ast.parse(bloc).body:
        if isinstance(noeud, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "OUTILS_LECTURE_COPILOT" for t in noeud.targets
        ):
            return tuple(ast.literal_eval(noeud.value))
    raise AssertionError("OUTILS_LECTURE_COPILOT absent du bloc")


def ecarts_vacuite(texte):
    """(i bis) Toute trace d'une copie locale dans un consommateur."""
    ecarts = []
    if DEBUT in texte or FIN in texte:
        ecarts.append("bornes du bloc présentes")
    if re.search(r"^\s*OUTILS_LECTURE_COPILOT\s*=", texte, re.M):
        ecarts.append("liste OUTILS_LECTURE_COPILOT définie localement")
    if re.search(r"^\s*def\s+_?lecture_copilot\b", texte, re.M):
        ecarts.append("def lecture_copilot locale")
    return ecarts


def noms_ecriture_kickoff():
    """WRITE_TOOL_NAMES et les clés de MULTIPLEXED_WRITE_TOOLS, lus par l'AST de
    kickoff_guard.py — sans l'importer (il importe tasks et specs)."""
    arbre = ast.parse(lire(".agents/bin/kickoff_guard.py"))
    ecriture, multiplexes = set(), set()
    for noeud in arbre.body:
        if isinstance(noeud, ast.Assign):
            cibles, valeur = [t.id for t in noeud.targets if isinstance(t, ast.Name)], noeud.value
        elif isinstance(noeud, ast.AnnAssign) and isinstance(noeud.target, ast.Name):
            cibles, valeur = [noeud.target.id], noeud.value
        else:
            continue
        if "WRITE_TOOL_NAMES" in cibles and isinstance(valeur, ast.Call):
            ecriture = set(ast.literal_eval(valeur.args[0]))
        if "MULTIPLEXED_WRITE_TOOLS" in cibles and isinstance(valeur, ast.Dict):
            multiplexes = {ast.literal_eval(k) for k in valeur.keys}
    return ecriture, multiplexes


def interdits():
    ecriture, multiplexes = noms_ecriture_kickoff()
    return {replier(n) for n in set(EXCLUS_DE_LA_LISTE) | ecriture | multiplexes | set(ECRITURE_ET_EXECUTION)}


def ecarts_disjonction(noms):
    """(ii) Les noms de la liste qui tombent dans un ensemble interdit."""
    return sorted({replier(n) for n in noms} & interdits())


def ecarts_motifs(table):
    """(ii) Les exclusions sans motif écrit."""
    return sorted(nom for nom, motif in table.items() if not str(motif or "").strip())


def programme_shell(texte):
    """Le programme Python qu'un script shell passe à `"$PY" -c '…'` pour décider."""
    trouve = re.search(r"\"\$PY\" -c '\n(" + re.escape(DEBUT) + r".*?)\n'", texte, re.S)
    return trouve.group(1) + "\n" if trouve else None


def charger_common(hote):
    """`.<hote>/hooks/_common.py` chargé PAR CHEMIN, sous un nom privé par hôte.

    Enregistré dans `sys.modules` AVANT `exec_module` (T-00000134) ; chaque appel
    rend un module NEUF qui remplace le précédent sous le même nom, et les deux
    jumeaux restent indépendants puisque leurs noms diffèrent."""
    chemin = ROOT / f".{hote}" / "hooks" / "_common.py"
    spec = importlib.util.spec_from_file_location(f"_common_filet_{hote}", chemin)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(spec.name, None)
        raise
    return module


# Matrice de charges partagée par (iv) et (i ter) : (charge, attendu sous copilot).
MATRICE = (
    ({"toolName": "view", "toolArgs": {"path": "a.py"}}, True),
    ({"toolName": "grep", "toolArgs": {"pattern": "x"}}, True),
    ({"tool_name": "read_file"}, True),
    ({"toolName": " VIEW "}, True),
    ({"toolName": "list-dir"}, True),
    ({"name": "list_agents"}, True),
    ({"toolName": "bash", "toolArgs": {"command": "ls"}}, False),
    ({"toolName": "create", "toolArgs": {"path": "x"}}, False),
    ({"toolName": "web_fetch", "toolArgs": {"url": "https://x.invalid"}}, False),
    ({"toolName": "ask_user"}, False),
    ({"toolName": ""}, False),
    ({"toolName": "inconnu_xyz"}, False),
    ({"toolCalls": [{"toolName": "view", "toolArgs": {"path": "a"}}]}, False),
    ({"tool_calls": [{"name": "view", "args": {"path": "a"}}]}, False),
    # F2 (classe 0) : un nom listé au premier niveau n'identifie pas la charge
    # quand elle porte AUSSI une forme groupée, ou une autre graphie du nom.
    ({"toolName": "view", "toolArgs": {"path": "a.py"},
      "toolCalls": [{"name": "create", "args": {"file_text": "x"}}]}, False),
    ({"toolName": "view", "tool_calls": [{"name": "create", "args": {"file_text": "x"}}]}, False),
    ({"toolName": "view", "tool_name": "create", "tool_input": {"file_text": "x"}}, False),
    ({"toolName": "view", "name": "create"}, False),
    ({"toolName": "view", "tool_name": " VIEW "}, True),
    ({"toolName": ["view"]}, False),
    ({}, False),
    (["view"], False),
    ("view", False),
)


class CopieTextuelle(unittest.TestCase):
    """(i) le bloc de référence, identique dans les cinq copies."""

    def test_le_bloc_de_reference_est_dans_les_cinq_copies(self):
        for rel in COPIES:
            with self.subTest(copie=rel):
                self.assertEqual(ecarts_copie(lire(rel)), [])

    def test_la_reference_porte_les_huit_noms_attendus(self):
        self.assertEqual(noms_du_bloc(REFERENCE), NOMS_ATTENDUS)

    def test_la_reference_tient_dans_une_chaine_shell_entre_apostrophes(self):
        self.assertNotIn("'", REFERENCE)
        REFERENCE.encode("ascii")

    def test_controle_negatif_une_copie_qui_differe_rougit(self):
        texte = lire(COPIES[0])
        self.assertIn('    "grep",', texte)
        self.assertNotEqual(ecarts_copie(texte.replace('    "grep",', '    "grepx",', 1)), [])
        self.assertNotEqual(ecarts_copie(texte + "\n" + REFERENCE), [], "un bloc en double doit rougir")
        self.assertNotEqual(ecarts_copie(texte.replace(DEBUT, "# ---", 1)), [], "un bloc absent doit rougir")


class VacuiteDesConsommateurs(unittest.TestCase):
    """(i bis) aucune copie locale ; la garde vient de `_common` par import."""

    def test_aucun_consommateur_ne_porte_de_copie_locale(self):
        for rel in CONSOMMATEURS_PY:
            with self.subTest(consommateur=rel):
                self.assertEqual(ecarts_vacuite(lire(rel)), [])

    def test_protect_paths_et_post_edit_check_importent_la_garde_de_common(self):
        for rel in GARDES:
            with self.subTest(consommateur=rel):
                arbre = ast.parse(lire(rel))
                importes = {
                    alias.name
                    for noeud in arbre.body
                    if isinstance(noeud, ast.ImportFrom) and noeud.module == "_common"
                    for alias in noeud.names
                }
                self.assertIn("lecture_copilot", importes)
                main = next(n for n in arbre.body if isinstance(n, ast.FunctionDef) and n.name == "main")
                # La garde suit IMMÉDIATEMENT la lecture du stdin (étape 3).
                garde = main.body[1]
                self.assertIsInstance(garde, ast.If)
                self.assertEqual(ast.unparse(garde.test), "lecture_copilot(payload)")
                self.assertIsInstance(garde.body[0], ast.Return)

    def test_controle_negatif_un_bloc_remis_dans_safe_bash_rougit(self):
        texte = lire(".codex/hooks/safe_bash.py")
        self.assertNotEqual(ecarts_vacuite(texte + "\n" + REFERENCE), [])
        self.assertNotEqual(ecarts_vacuite(texte + "\ndef _lecture_copilot(p):\n    return 1\n"), [])


class Disjonction(unittest.TestCase):
    """(ii) la liste ne touche aucun outil exclu, d'écriture ou d'exécution."""

    def test_chaque_exclusion_porte_un_motif(self):
        self.assertEqual(ecarts_motifs(EXCLUS_DE_LA_LISTE), [])
        self.assertEqual(len(EXCLUS_DE_LA_LISTE), 6)

    def test_les_tables_de_kickoff_guard_sont_lues(self):
        ecriture, multiplexes = noms_ecriture_kickoff()
        self.assertIn("edit", ecriture)
        self.assertIn("str_replace_editor", multiplexes)

    def test_la_liste_est_disjointe_dans_chaque_copie(self):
        for rel in COPIES:
            with self.subTest(copie=rel):
                blocs = extraire_blocs(lire(rel))
                self.assertEqual(len(blocs), 1)
                self.assertEqual(ecarts_disjonction(noms_du_bloc(blocs[0])), [])

    def test_controle_negatif_create_ou_un_exclu_ajoute_rougit(self):
        for intrus in ("create", "web_fetch", "Run-In-Terminal", "str_replace_editor"):
            with self.subTest(intrus=intrus):
                mute = REFERENCE.replace('    "view",', f'    "{intrus}",\n    "view",', 1)
                self.assertEqual(ecarts_disjonction(noms_du_bloc(mute)), [replier(intrus)])

    def test_controle_negatif_un_motif_vide_rougit(self):
        self.assertEqual(ecarts_motifs({**EXCLUS_DE_LA_LISTE, "ask_user": "  "}), ["ask_user"])


class Fixture:
    """Un projet git jetable portant les ponts des deux hôtes et `events.py`,
    avec un fichier SUIVI dont la modification finit par une espace : l'arbre
    est FAUTIF, donc post_edit_check parle quand il juge (C2)."""

    MODULES = ("_common", "protect_paths", "safe_bash", "safe_bash_git", "safe_bash_hooks", "audit_gate", "post_edit_check")

    def __init__(self, racine):
        self.racine = racine
        (racine / ".agents" / "bin").mkdir(parents=True)
        shutil.copy2(ROOT / ".agents" / "bin" / "events.py", racine / ".agents" / "bin" / "events.py")
        # redaction.py n'est copié que s'il existe : sans lui, events.py écrit
        # quand même la ligne (voie dégradée, data réduite), et ce filet ne lit
        # que le `kind`. Une extraction partielle (§9, étape 3 : sans paquet)
        # rejoue donc ce banc sans échouer sur un fichier de fixture absent.
        # Source : le paquet que vendor_paths résout ; posé à l'ancien lieu ET
        # au neuf, dont le lieu que lit events.py (`_CHEMIN_REDACTION`).
        paquet = _VP.dossier_paquet(ROOT, "cadre")
        redaction = paquet / "ledger" / "redaction.py" if paquet else None
        for lieu in ("src/cadre/ledger", ".agents/vendor/cadre/ledger"):
            (racine / lieu).mkdir(parents=True, exist_ok=True)
            if redaction is not None and redaction.is_file():
                shutil.copy2(redaction, racine / lieu / "redaction.py")
        for hote in ("codex", "gemini"):
            cible = racine / f".{hote}" / "hooks"
            cible.mkdir(parents=True)
            for module in self.MODULES:
                shutil.copy2(ROOT / f".{hote}" / "hooks" / f"{module}.py", cible / f"{module}.py")
        (racine / ".gitignore").write_text(".agents/\n.codex/\n.gemini/\nsrc/cadre/\n", encoding="utf-8")
        (racine / "ws.txt").write_text("propre\n", encoding="utf-8")
        git = ["git", "-C", str(racine)]
        subprocess.run(git + ["init", "-q"], check=True)
        subprocess.run(git + ["add", "-A"], check=True, capture_output=True)
        subprocess.run(
            git + ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "fixture"],
            check=True, capture_output=True,
        )
        (racine / "ws.txt").write_text("propre \n", encoding="utf-8")
        self.compteur = 0

    def jouer(self, module, charge, hote, dossier="codex", script=None):
        """`(rc, stdout en octets, événements)` d'un vrai sous-processus."""
        self.compteur += 1
        evenements = self.racine.parent / f"ev-{self.compteur}"
        evenements.mkdir()
        env = dict(os.environ)
        for cle in ("AGENTS_HOOK_HOST", "CLAUDE_PROJECT_DIR"):
            env.pop(cle, None)
        env["AGENTS_EVENTS_DIR"] = str(evenements)
        if hote is not None:
            env["AGENTS_HOOK_HOST"] = hote
        chemin = script or self.racine / f".{dossier}" / "hooks" / f"{module}.py"
        fini = subprocess.run(
            [sys.executable, "-B", str(chemin)],
            input=json.dumps(charge).encode("utf-8"),
            capture_output=True, cwd=str(self.racine), env=env, timeout=60,
        )
        lignes = b"".join(p.read_bytes() for p in sorted(evenements.glob("*.jsonl")))
        recs = [json.loads(l) for l in lignes.decode("utf-8").splitlines() if l.strip()]
        return fini.returncode, fini.stdout, recs


def decision(stdout):
    """Le refus, lu à `hookSpecificOutput.permissionDecision` (C5), jamais à l'octet."""
    if not stdout.strip():
        return None
    return (json.loads(stdout).get("hookSpecificOutput") or {}).get("permissionDecision")


class Verdicts(unittest.TestCase):
    """(iii) `view` muet sous copilot ; tout le reste jugé comme à la base."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.fx = Fixture(Path(cls._tmp.name) / "projet")
        cls.env_local = str(cls.fx.racine / ".env.local")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def charge(self, nom, **extra):
        return {"toolName": nom, "toolArgs": {"path": self.env_local, **extra}}

    def test_view_sous_copilot_est_muet_pour_les_quatre_consommateurs(self):
        for module in ("protect_paths", "safe_bash", "audit_gate", "post_edit_check"):
            with self.subTest(module=module):
                rc, out, recs = self.fx.jouer(module, self.charge("view"), "copilot")
                self.assertEqual((rc, out, recs), (0, b"", []))

    def test_protect_paths_refuse_tout_ce_qui_n_est_pas_une_lecture_listee(self):
        cas = {
            "create": self.charge("create"),
            "bash": self.charge("bash"),
            "nom vide": self.charge(""),
            "nom inconnu": self.charge("inconnu_xyz"),
            "forme groupee": {
                "toolCalls": [{"toolName": "view"}],
                "toolArgs": {"path": self.env_local},
            },
        }
        for etiquette, charge in cas.items():
            with self.subTest(cas=etiquette):
                rc, out, recs = self.fx.jouer("protect_paths", charge, "copilot")
                self.assertEqual(decision(out), "deny")
                self.assertEqual([r["kind"] for r in recs], ["hook.deny"])

    def test_view_hors_copilot_reste_refuse(self):
        for hote in ("codex", "kimi", None):
            with self.subTest(hote=hote):
                rc, out, recs = self.fx.jouer("protect_paths", self.charge("view"), hote)
                self.assertEqual(decision(out), "deny")

    def test_le_jumeau_gemini_est_inerte_sous_copilot(self):
        rc, out, recs = self.fx.jouer("protect_paths", self.charge("view"), "copilot", dossier="gemini")
        self.assertEqual(decision(out), "deny")

    def test_safe_bash_et_audit_gate_jugent_toujours_bash_sous_copilot(self):
        for module, commande in (("safe_bash", "rm -rf /"), ("audit_gate", "npx skills add some/ref")):
            with self.subTest(module=module):
                charge = {"toolName": "bash", "toolArgs": {"command": commande}}
                rc, out, recs = self.fx.jouer(module, charge, "copilot")
                self.assertEqual(decision(out), "deny")

    def test_post_edit_check_sur_arbre_fautif(self):
        rc, out, recs = self.fx.jouer("post_edit_check", self.charge("view"), "copilot")
        self.assertEqual((out, recs), (b"", []), "copilot + view doit sortir avant git diff --check")
        for hote, nom in (("codex", "view"), ("copilot", "bash")):
            with self.subTest(hote=hote, outil=nom):
                rc, out, recs = self.fx.jouer("post_edit_check", self.charge(nom), hote)
                self.assertIn("additionalContext", json.loads(out)["hookSpecificOutput"])
                self.assertEqual([r["kind"] for r in recs], ["hook.check_fail"])

    def test_controle_negatif_garde_retiree_le_bras_post_edit_check_rougit(self):
        source = (self.fx.racine / ".codex" / "hooks" / "post_edit_check.py").read_text(encoding="utf-8")
        garde = "    if lecture_copilot(payload):\n        return\n"
        self.assertEqual(source.count(garde), 1, "un mutant qui ne mute rien est un témoin muet")
        mutant = self.fx.racine / ".codex" / "hooks" / "post_edit_check_mutant.py"
        mutant.write_text(source.replace(garde, "", 1), encoding="utf-8")
        rc, out, recs = self.fx.jouer("post_edit_check", self.charge("view"), "copilot", script=mutant)
        self.assertNotEqual(out, b"", "sans la garde, copilot + view doit parler : le bras discrimine")
        self.assertEqual([r["kind"] for r in recs], ["hook.check_fail"])


class LectureCopilotUnitaire(unittest.TestCase):
    """(iv) la fonction, chargée par chemin ; et les programmes shell décident pareil."""

    def test_vrai_seulement_pour_une_lecture_listee_sous_copilot(self):
        codex = charger_common("codex")
        with mock.patch.dict(os.environ, {"AGENTS_HOOK_HOST": "copilot"}):
            for charge, attendu in MATRICE:
                with self.subTest(charge=charge):
                    self.assertIs(codex.lecture_copilot(charge), attendu)
        vue = {"toolName": "view"}
        for valeur in ("codex", "kimi", "inconnu"):
            with self.subTest(hote=valeur), mock.patch.dict(os.environ, {"AGENTS_HOOK_HOST": valeur}):
                self.assertFalse(codex.lecture_copilot(vue))
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AGENTS_HOOK_HOST", None)
            self.assertFalse(codex.lecture_copilot(vue))

    def test_le_jumeau_gemini_rend_faux_meme_sous_copilot(self):
        gemini = charger_common("gemini")
        with mock.patch.dict(os.environ, {"AGENTS_HOOK_HOST": "copilot"}):
            self.assertFalse(gemini.lecture_copilot({"toolName": "view"}))

    def test_la_concordance_lit_toutes_les_graphies_de_tool_name(self):
        """lecture_copilot et les trois programmes recopient les graphies de
        tool_name() : une graphie ajoutée là et pas ici rouvrirait F2 en silence.
        Chacune, seule, identifie une lecture ; en désaccord, elle la défait."""
        arbre = ast.parse(lire(".codex/hooks/_common.py"))
        corps = next(n for n in arbre.body if isinstance(n, ast.FunctionDef) and n.name == "tool_name")
        graphies = [n.args[0].value for n in ast.walk(corps)
                    if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "get"]
        self.assertEqual(graphies, ["toolName", "tool_name", "tool", "name"])
        cas = []
        for cle in graphies:
            autre = next(g for g in graphies if g != cle)
            cas += [({cle: "view"}, True), ({cle: "view", autre: "create"}, False)]
        codex = charger_common("codex")
        with mock.patch.dict(os.environ, {"AGENTS_HOOK_HOST": "copilot"}):
            for charge, attendu in cas:
                with self.subTest(charge=charge):
                    self.assertIs(codex.lecture_copilot(charge), attendu)
        for rel in SCRIPTS_SHELL:
            programme = programme_shell(lire(rel))
            for charge, attendu in cas:
                with self.subTest(script=rel, charge=charge):
                    fini = subprocess.run([sys.executable, "-c", programme], input=json.dumps(charge),
                                          capture_output=True, text=True, timeout=30)
                    self.assertEqual(fini.returncode == 0, attendu, (charge, fini.stderr))

    def test_le_corps_du_jumeau_gemini_decide_comme_codex_hote_force(self):
        """Inerte en vrai (sous `.gemini/`, event_host() rend « gemini » par la table
        par répertoire, avant toute lecture d'AGENTS_HOOK_HOST), le corps Gemini doit
        tout de même décider comme Codex : sans hôte forcé, ce bras ne pourrait pas rougir."""
        gemini = charger_common("gemini")
        with mock.patch.object(gemini, "event_host", return_value="copilot"):
            for charge, attendu in MATRICE:
                with self.subTest(charge=charge):
                    self.assertIs(gemini.lecture_copilot(charge), attendu)

    def test_les_trois_programmes_shell_decident_comme_lecture_copilot(self):
        codex = charger_common("codex")
        for rel in SCRIPTS_SHELL:
            programme = programme_shell(lire(rel))
            with self.subTest(script=rel):
                self.assertIsNotNone(programme, "programme de décision introuvable")
                self.assertEqual(extraire_blocs(programme), [REFERENCE])
                for charge, _ in MATRICE:
                    fini = subprocess.run(
                        [sys.executable, "-c", programme], input=json.dumps(charge),
                        capture_output=True, text=True, timeout=30,
                    )
                    with mock.patch.dict(os.environ, {"AGENTS_HOOK_HOST": "copilot"}):
                        attendu = codex.lecture_copilot(charge)
                    self.assertEqual(fini.returncode == 0, attendu, (charge, fini.stderr))
                illisible = subprocess.run(
                    [sys.executable, "-c", programme], input="pas { du json",
                    capture_output=True, text=True, timeout=30,
                )
                self.assertEqual(illisible.returncode, 1, "une charge illisible est jugée")


class FormeHybrideBoutEnBout(unittest.TestCase):
    """(iv bis) F2 : sur une charge hybride ou à graphies en désaccord, chaque script
    garde le chemin entier (bouchon `git` appelé, comme à la base 111393b6) ; `view`
    nu sort avant tout git (0 appel) — le bouchon sait compter zéro."""

    APPELS = {
        ".agents/security/gitleaks-scan.sh": (["--content"], {}),
        ".agents/security/sca-scan.sh": ([], {"SCA_CHANGED_ONLY": "1"}),
        ".agents/security/semgrep-scan.sh": (
            ["--hook", "--event=post"],
            {"SEMGREP_CONFIG": str(ROOT / ".agents" / "security" / "semgrep.yml")},
        ),
    }
    JUGEES = {
        "hybride toolCalls": {"toolName": "view", "toolArgs": {"path": "a.py"},
                              "toolCalls": [{"name": "create", "args": {"file_text": "x"}}]},
        "hybride tool_calls": {"toolName": "view", "toolArgs": {"path": "a.py"},
                               "tool_calls": [{"name": "create", "args": {"file_text": "x"}}]},
        "graphies en désaccord": {"toolName": "view", "tool_name": "create",
                                  "tool_input": {"path": "cfg.py", "file_text": "x"}},
    }
    VUE = {"toolName": "view", "toolArgs": {"path": "src/a.py"}}

    def appels_git(self, rel, charge, tmp, n):
        """Le nombre d'appels au bouchon `git` d'un vrai sous-processus du script."""
        reel = shutil.which("git")
        if not reel or not os.path.isabs(reel):
            self.skipTest("git absent ou hors chemin absolu — l'observable nommé est le bouchon git")
        base = Path(tmp) / f"r{n}"
        for sous in ("w", "bouchons", "tmp", "ev"):
            (base / sous).mkdir(parents=True)
        trace = base / "trace"
        trace.write_text("", encoding="utf-8")
        bouchon = base / "bouchons" / "git"
        bouchon.write_text(f'#!/bin/sh\nprintf "%s\\n" git >> "{trace}"\nexec "{reel}" "$@"\n',
                           encoding="utf-8")
        bouchon.chmod(0o755)
        args, extra = self.APPELS[rel]
        env = dict(os.environ)
        env.pop("CLAUDE_PROJECT_DIR", None)
        env.update(extra)
        env.update(PATH=f"{base / 'bouchons'}{os.pathsep}{env.get('PATH', '')}", TMPDIR=str(base / "tmp"),
                   AGENTS_EVENTS_DIR=str(base / "ev"), AGENTS_HOOK_HOST="copilot")
        subprocess.run(["bash", str(ROOT / rel), *args], input=json.dumps(charge).encode("utf-8"),
                       capture_output=True, cwd=str(base / "w"), env=env, timeout=300)
        return trace.read_text(encoding="utf-8").split().count("git")

    def test_les_trois_scripts_jugent_la_forme_hybride_et_les_graphies_en_desaccord(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            n = 0
            for rel in self.APPELS:
                n += 1
                with self.subTest(script=rel, charge="view nu"):
                    self.assertEqual(self.appels_git(rel, self.VUE, tmp, n), 0,
                                     "view nu doit sortir avant tout git : sinon le bouchon ne discrimine rien")
                for etiquette, charge in self.JUGEES.items():
                    n += 1
                    with self.subTest(script=rel, charge=etiquette):
                        self.assertGreaterEqual(self.appels_git(rel, charge, tmp, n), 1,
                                                "chemin entier perdu : un second outil sortirait sans scan")


# (v) RÉINJECTION — avis LOW de security-code-review sur T-01M4RWC6VHHN479J2A9RRY1BE3.
# La charge lue sous copilot revenait au scanner par une SUBSTITUTION DE
# PROCESSUS : si `/dev/fd` ou la fifo manque, la redirection échoue, et bash
# CONTINUE — un `exec` dont la redirection échoue ne fait pas sortir le script
# (mesuré sous bash 3.2.57 et 5.3.15) — sur un stdin déjà VIDÉ : fail-open, de
# classe 0 pour gitleaks --content. Forme fermée : une here-string SANS numéro
# de descripteur. `exec 0<<<…` passe `bash -n` mais rend PartialParsing sous le
# parseur du SAST (mesuré, semgrep 1.172.0) : le script ENTIER sortirait des
# cibles inspectées. La here-string ajoute un saut de ligne final, sans effet :
# gitleaks scanne du texte, semgrep relit par `INPUT="$(cat)"` qui l'ôte, sca ne
# relit pas stdin. Elle passe par un fichier temporaire (toujours sous bash 3.2,
# au-delà d'un pipe plein sous 5.3) : son échec se lit au statut de `exec`.
REINJECTION = 'exec <<<"$charge"'

# Ce qui suit la réinjection sur sa ligne, par script : la réponse à son ÉCHEC.
SUITE_REINJECTION = {
    # classe 0 : une charge non réinjectée est BLOQUÉE, jamais jugée vide
    ".agents/security/gitleaks-scan.sh": re.compile(r' \|\| \{ echo "[^"]+" >&2; exit 2; \}'),
    # le hook annonce, ne bloque jamais (doctrine du hook semgrep)
    ".agents/security/semgrep-scan.sh": re.compile(r' \|\| echo "COVERAGE DEGRADED: [^"]+" >&2'),
    # aucun lecteur de stdin en aval : un échec ne change aucun verdict
    ".agents/security/sca-scan.sh": re.compile(r""),
}


def corps_sortie_precoce(texte):
    """Le corps de `sortie_precoce_copilot`, de sa ligne de tête à la `}` en colonne 0."""
    trouve = re.search(r"^sortie_precoce_copilot\(\) \{.*?^\}$", texte, re.S | re.M)
    return trouve.group(0) if trouve else None


def ligne_reinjection(texte):
    """La ligne `exec` du bloc, telle qu'écrite (retrait compris), ou None."""
    corps = corps_sortie_precoce(texte) or ""
    lignes = [l for l in corps.splitlines() if re.match(r"\s*exec\b", l)]
    return lignes[0] if len(lignes) == 1 else None


def ecarts_reinjection(rel, texte):
    """(v) Les écarts d'un script à la réinjection fermée ; [] s'il la porte."""
    corps = corps_sortie_precoce(texte)
    if corps is None:
        return ["fonction sortie_precoce_copilot introuvable"]
    ecarts = []
    if "<(" in corps:
        ecarts.append("substitution de processus dans le bloc : stdin vide si /dev/fd "
                      "ou la fifo manque (fail-open)")
    if any("$charge" in l and "<(" in l for l in texte.splitlines()):
        ecarts.append("la charge est réinjectée par substitution de processus")
    execs = [l.strip() for l in corps.splitlines() if re.match(r"\s*exec\b", l)]
    if len(execs) != 1:
        ecarts.append(f"{len(execs)} ligne(s) exec dans le bloc au lieu d'une")
    elif not execs[0].startswith(REINJECTION):
        ecarts.append(f"réinjection hors forme fermée : {execs[0]}")
    elif not SUITE_REINJECTION[rel].fullmatch(execs[0][len(REINJECTION):]):
        ecarts.append(f"échec de réinjection non traité comme le veut le script : {execs[0]}")
    return ecarts


def interpretes_bash():
    """bash du PATH, plus /bin/bash s'il est un AUTRE binaire (3.2 sous macOS)."""
    vus, liste = set(), []
    for chemin in (shutil.which("bash"), "/bin/bash"):
        if chemin and os.path.isfile(chemin) and os.path.realpath(chemin) not in vus:
            vus.add(os.path.realpath(chemin))
            liste.append(chemin)
    return liste


class Reinjection(unittest.TestCase):
    """(v) réinjection sans substitution de processus ; échec relevé selon le script."""

    GITLEAKS = SCRIPTS_SHELL[0]
    SEMGREP = SCRIPTS_SHELL[2]
    # Un nom NON listé, charge PROPRE : rc 0 attendu quand la réinjection réussit,
    # donc un rc 2 sur le mutant ne peut venir que de la garde de réinjection.
    PROPRE = {"toolName": "create", "toolArgs": {"path": "cfg.py", "file_text": "valeur = 1\n"}}
    # Une redirection qui ÉCHOUE, au même endroit et par le même statut que la
    # here-string sans fichier temporaire (que ce banc ne sait pas provoquer).
    ECHEC = "exec </nonexistent-filet-reinjection/charge"

    def test_les_trois_scripts_portent_la_reinjection_fermee(self):
        self.assertEqual(set(SUITE_REINJECTION), set(SCRIPTS_SHELL))
        for rel in SCRIPTS_SHELL:
            with self.subTest(script=rel):
                self.assertEqual(ecarts_reinjection(rel, lire(rel)), [])

    def test_controle_negatif_chaque_reinjection_fautive_rougit(self):
        texte = lire(self.GITLEAKS)
        ligne = ligne_reinjection(texte)
        self.assertIsNotNone(ligne, "ligne de réinjection introuvable dans gitleaks-scan.sh")
        retrait = ligne[: len(ligne) - len(ligne.lstrip())]
        suite = ligne.strip()[len(REINJECTION):]
        for etiquette, fautive in (
            ("substitution de processus", "exec 0< <(printf '%s' \"$charge\")"),
            ("descripteur explicite, illisible du SAST", 'exec 0<<<"$charge"' + suite),
            ("garde retirée", REINJECTION),
            ("garde qui ne bloque pas", REINJECTION + ' || echo "x" >&2'),
        ):
            with self.subTest(mutant=etiquette):
                mute = texte.replace(ligne, retrait + fautive, 1)
                self.assertTrue(mute != texte, "un mutant qui ne mute rien est un témoin muet")
                self.assertNotEqual(ecarts_reinjection(self.GITLEAKS, mute), [])
        semgrep = lire(self.SEMGREP)
        ligne = ligne_reinjection(semgrep)
        self.assertIsNotNone(ligne, "ligne de réinjection introuvable dans semgrep-scan.sh")
        mute = semgrep.replace(ligne, ligne[: len(ligne) - len(ligne.lstrip())] + REINJECTION, 1)
        self.assertTrue(mute != semgrep, "un mutant qui ne mute rien est un témoin muet")
        self.assertNotEqual(ecarts_reinjection(self.SEMGREP, mute), [], "un échec muet doit rougir")

    def test_gitleaks_bloque_quand_la_reinjection_echoue(self):
        texte = lire(self.GITLEAKS)
        ligne = ligne_reinjection(texte)
        self.assertIsNotNone(ligne, "ligne de réinjection introuvable dans gitleaks-scan.sh")
        self.assertTrue(ligne.strip().startswith(REINJECTION), f"réinjection hors forme fermée : {ligne.strip()}")
        self.assertEqual(texte.count(ligne), 1, "un mutant qui ne mute rien est un témoin muet")
        retrait = ligne[: len(ligne) - len(ligne.lstrip())]
        suite = ligne.strip()[len(REINJECTION):]
        variantes = {
            "base": texte,
            "garde": texte.replace(ligne, retrait + self.ECHEC + suite, 1),
            "nu": texte.replace(ligne, retrait + self.ECHEC, 1),
        }
        interpretes = interpretes_bash()
        if not interpretes:
            self.skipTest("bash introuvable — bras de comportement NON joué")
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            for nom, source in variantes.items():
                (Path(tmp) / f"{nom}.sh").write_text(source, encoding="utf-8")
            n = 0
            for interprete in interpretes:
                rcs = {}
                for nom in variantes:
                    n += 1
                    travail = Path(tmp) / f"w{n}"
                    travail.mkdir()
                    env = dict(os.environ)
                    env.pop("CLAUDE_PROJECT_DIR", None)
                    env["AGENTS_HOOK_HOST"] = "copilot"
                    env["AGENTS_EVENTS_DIR"] = str(Path(tmp) / f"ev{n}")
                    fini = subprocess.run(
                        [interprete, str(Path(tmp) / f"{nom}.sh"), "--content"],
                        input=json.dumps(self.PROPRE).encode("utf-8"),
                        capture_output=True, cwd=str(travail), env=env, timeout=120,
                    )
                    rcs[nom] = (fini.returncode, fini.stderr.decode("utf-8", "replace")[-400:])
                with self.subTest(bash=interprete):
                    # base : la charge propre est propre — le rc 2 du mutant vient de la garde
                    self.assertEqual(rcs["base"][0], 0, rcs["base"])
                    # garde : la redirection échoue, la charge n'est pas jugée vide : BLOQUÉE
                    self.assertEqual(rcs["garde"][0], 2, rcs["garde"])
                    # nu : sans la garde, le même échec passe (rc 0) — le fail-open reproduit,
                    # preuve que ce bras rougirait si la garde tombait
                    self.assertEqual(rcs["nu"][0], 0, rcs["nu"])


if __name__ == "__main__":
    unittest.main()
