"""La CHAÎNE DE PLAN : trace d'hôte + refus sur `tasks.py start` (T-00000624).

ZÉRO APPEL LLM. On pose des traces à la main et on regarde `tasks.py` refuser
ou non — le même contrat que `test_binome_guard.py` tient pour la clôture.

*** CE BANC EXISTE PARCE QU'UN TÉMOIN QUI NE PEUT PAS ÉCHOUER EST DÉCORATIF. ***
Ce dépôt l'a payé trois fois dans la seule journée du 2026-09-14 : neuf témoins
verts sur un défaut réel, parce qu'aucun n'avait été joué sur un MUTANT. Chaque
test ci-dessous a donc son bras NÉGATIF — un cas où la garde DOIT refuser — et
le plus important d'entre eux est `test_la_consommation_est_a_un_coup` : sans
lui, une garde qui n'effacerait rien resterait verte sur tous les autres bras.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TASKS = ROOT / ".agents" / "bin" / "tasks.py"
TRACER = ROOT / ".agents" / "bin" / "plan_trace.py"
CODEX_HOOKS = ROOT / ".codex" / "hooks.json"
CODEX_ORCHESTRATOR = ROOT / ".codex" / "agents" / "orchestrator.toml"


def _erreurs_cablage_codex(charge: dict) -> list[str]:
    """Juge le RACCORD, pas seulement l'existence du script cible."""
    trouvailles: list[tuple[str, dict]] = []
    for evenement, groupes in charge.get("hooks", {}).items():
        for groupe in groupes:
            for crochet in groupe.get("hooks", []):
                commandes = (str(crochet.get("command", "")),
                             str(crochet.get("commandWindows", "")))
                if any(".agents/bin/plan_trace.py" in commande for commande in commandes):
                    trouvailles.append((evenement, crochet))

    erreurs: list[str] = []
    if len(trouvailles) != 1:
        erreurs.append(f"plan_trace attendu une fois, trouve {len(trouvailles)}")
        return erreurs
    evenement, crochet = trouvailles[0]
    if evenement != "SubagentStop":
        erreurs.append(f"plan_trace cable sur {evenement}, pas SubagentStop")
    for champ in ("command", "commandWindows"):
        commande = str(crochet.get(champ, ""))
        if ".agents/bin/plan_trace.py" not in commande:
            erreurs.append(f"{champ} ne lance pas plan_trace")
        if "AGENTS_HOOK_HOST" not in commande or "codex" not in commande:
            erreurs.append(f"{champ} ne borne pas l'hote Codex")
    return erreurs


def _erreurs_routeur_codex(texte: str) -> list[str]:
    plat = " ".join(texte.split())
    attendus = (
        # S-00003871 (decision pilote du 2026-10-03) : l etape 3 nomme UN critique
        # de plan — plus la paire « plan-critic ∥ … BOTH in parallel ».
        # S-01M4TZZ13Y (decision pilote du 2026-10-13, planification sur Opus
        # seul) : plus de repli, et le NO_GO revient a `planner`. Fragment lu sur
        # le texte APLATI : il est replie sur plusieurs lignes dans le .toml.
        "3. plan-critic, the ONLY plan critic - its verdict IS the verdict "
        "(no fallback since S-01M4TZZ13Y: unavailable means COVERAGE DEGRADED, "
        "verdict absent); NO_GO returns to planner, which revises with the findings",
        # T-00000707 : « five » devient « six » — planner-sonnet ENTRE dans
        # l enumeration, que le routeur codex oubliait. S-01M4TZZ13Y : les six
        # restent enumeres (les defs sont sur disque, et declarent toujours leur
        # sandbox), mais deux sont HORS CHAINE, et l enumeration le dit.
        # T-01M5S9338BJP1B5RM3TG14AMYT : la déf est en anglais, « deux hors chaîne »
        # y est devenu « two off-chain » (mutant dédié : la forme française rougit).
        "six agents upstream of the gate (two off-chain, S-01M4TZZ13Y) — "
        "language-detector, planner, planner-sonnet, analyzer, plan-critic, "
        "plan-critic-sonnet-max — each declare sandbox_mode",
    )
    # S-01M4TZZ13Y : la PRESENCE des fragments ne voit pas un retour de l ancien
    # routage AJOUTE a cote du nouveau. L absence se juge donc a part — sans elle,
    # les mutants d insertion ci-dessous seraient verts par vacuite. Les deux
    # anciennes parentheses de repli (etape 3 en anglais, schema en francais)
    # sont SCINDEES en chaines contigues, comme les mutants : le balayage des
    # anciens litteraux sur les surfaces ne doit pas compter ce banc. Comparaison
    # en minuscules : une reecriture en casse differente reste un retour.
    # T-01M5S9338BJP1B5RM3TG14AMYT : la parenthèse ouvrante est retirée du
    # premier interdit — un repli revenu en anglais dans le schéma (« Fallback
    # plan-critic-sonnet-max alone ») rougit comme celui de l étape 3.
    interdits = (
        "──NO_GO──> planner-sonnet",
        "fallback plan-critic-sonnet-max " "ALONE",
        "repli plan-critic-sonnet-max " "SEUL",
    )
    bas = plat.lower()
    erreurs = [f"fragment absent: {fragment}" for fragment in attendus if fragment not in plat]
    erreurs += [f"fragment interdit: {fragment}" for fragment in interdits
                if fragment.lower() in bas]
    return erreurs


def _mod(path: Path, nom: str):
    spec = importlib.util.spec_from_file_location(nom, path)
    module = importlib.util.module_from_spec(spec)
    # ENREGISTRER AVANT D EXECUTER — exigence du filet `test_modload_registration`,
    # et ce n est pas une formalite : un module execute hors de `sys.modules` se
    # re-execute a chaque import, ses dataclasses et ses exceptions deviennent
    # des TYPES DISTINCTS d une charge a l autre, et un `except` cesse
    # silencieusement d attraper. La seule autre issue admise par le filet est un
    # marqueur `# unregistered on purpose: <raison>`, qui ne s applique pas ici.
    sys.modules[nom] = module
    spec.loader.exec_module(module)
    return module


class CablageCodexTests(unittest.TestCase):
    """Le raccord Codex est la preuve absente que T-00000684 ajoute."""

    def test_le_routeur_nomme_le_critique_unique_et_le_pre_gate(self):
        texte = CODEX_ORCHESTRATOR.read_text(encoding="utf-8")
        self.assertEqual(_erreurs_routeur_codex(texte), [])

    def test_mutants_du_routeur_sont_tues(self):
        texte = CODEX_ORCHESTRATOR.read_text(encoding="utf-8")
        plat = " ".join(texte.split())
        mutants = (
            # S-00003871 — mutant « retour a la paire » : l etape 3 d AVANT la
            # decision du critique unique. Applique sur le texte APLATI (etape
            # repliee sur deux lignes dans le .toml).
            plat.replace("3. plan-critic, the ONLY plan critic - its verdict IS the verdict",
                         "3. plan-critic ∥ plan-critic-sonnet-max, BOTH in parallel on the "
                         "same plan; the weaker verdict wins", 1),
            # S-01M4TZZ13Y — le repli REVIENT dans l etape 3 : doit rougir.
            # Les anciens litteraux des mutants sont SCINDES en deux chaines
            # contigues (meme valeur a l execution) : le balayage des anciens
            # litteraux de routage sur les surfaces ne doit pas compter un mutant.
            plat.replace("(no fallback since S-01M4TZZ13Y: unavailable means COVERAGE "
                         "DEGRADED, verdict absent)",
                         "(fallback plan-critic-sonnet-max "
                         "ALONE, COVERAGE DEGRADED)", 1),
            # S-01M4TZZ13Y — la mention « hors chaine » disparait de l enumeration
            # du pre-gate : doit rougir aussi.
            plat.replace("(two off-chain, S-01M4TZZ13Y) ", "", 1),
            # T-01M5S9338BJP1B5RM3TG14AMYT — la forme française d avant revient : rouge.
            plat.replace("(two off-chain, S-01M4TZZ13Y)", "(deux hors chaîne, S-01M4TZZ13Y)", 1),
            # S-01M4TZZ13Y — l ancienne fleche du NO_GO est INSEREE a cote de la
            # nouvelle, qui reste presente : seul le fragment interdit le voit.
            # Applique sur le texte APLATI (un replace sur le texte brut ne
            # changeait RIEN ici le 2026-09-22 : mutant == base, temoin vert sur
            # du vide). Le schema est un bloc imprime, francais a l octet sur les
            # cinq hotes (T-01M5S9338BJP1B5RM3TG14AMYT, correction finale) : ancre francaise.
            plat.replace("──NO_GO──> planner reprend",
                         "──NO_GO──> planner-sonnet "
                         "au 1er NO_GO (S-01M4TZZ13Y) "
                         "──NO_GO──> planner reprend", 1),
        )
        # S-01M4TZZ13Y — mutants d INSERTION : l ancien routage revient A COTE du
        # nouveau, dont chaque fragment attendu reste intact. Ils doivent rougir
        # par le SEUL controle d absence (aucun « fragment absent ») — sinon ils
        # ne prouvent pas que ce controle mord.
        insertions = (
            # la fleche du NO_GO vers planner-sonnet (meme insertion que le
            # dernier mutant ci-dessus, jugee ici par sa raison).
            plat.replace("──NO_GO──> planner reprend",
                         "──NO_GO──> planner-sonnet "
                         "au 1er NO_GO (S-01M4TZZ13Y) "
                         "──NO_GO──> planner reprend", 1),
            # l ancienne parenthese de repli de l etape 3, inseree APRES le
            # fragment attendu de l etape 3 (avant, elle le couperait).
            plat.replace("which revises with the findings",
                         "which revises with the findings (fallback plan-critic-sonnet-max "
                         "ALONE, COVERAGE DEGRADED)", 1),
            # l ancien repli du schema, insere et en casse differente : le
            # controle d absence compare en minuscules.
            plat.replace("son verdict EST le verdict ; indisponible",
                         "son verdict EST le verdict ; Repli plan-critic-sonnet-max "
                         "seul, COVERAGE DEGRADED ; indisponible", 1),
            # le même repli, revenu en ANGLAIS dans le schéma (défs traduites,
            # T-01M5S9338BJP1B5RM3TG14AMYT), sans parenthèse : rouge aussi.
            plat.replace("son verdict EST le verdict ; indisponible",
                         "son verdict EST le verdict ; Fallback plan-critic-sonnet-max "
                         "alone, COVERAGE DEGRADED ; indisponible", 1),
        )
        for mutant in mutants:
            with self.subTest():
                # La mutation doit avoir CHANGE quelque chose avant qu on lise un
                # verdict (L-00000161) — sans cette ligne, le troisieme mutant
                # ci-dessus etait vert par vacuite.
                self.assertNotEqual(" ".join(mutant.split()), plat,
                                    "la mutation n a rien change — elle ne mesure rien")
                self.assertTrue(_erreurs_routeur_codex(mutant))
        for mutant in insertions:
            with self.subTest(insertion=True):
                self.assertNotEqual(" ".join(mutant.split()), plat,
                                    "la mutation n a rien change — elle ne mesure rien")
                erreurs = _erreurs_routeur_codex(mutant)
                self.assertTrue(erreurs)
                self.assertTrue(all(e.startswith("fragment interdit: ") for e in erreurs),
                                erreurs)

    def test_le_traceur_est_cable_une_fois_sur_subagent_stop(self):
        charge = json.loads(CODEX_HOOKS.read_text(encoding="utf-8"))
        self.assertEqual(_erreurs_cablage_codex(charge), [])

    def test_deplacer_le_traceur_sur_stop_fait_rougir_le_temoin(self):
        charge = json.loads(CODEX_HOOKS.read_text(encoding="utf-8"))
        groupes = charge["hooks"]["SubagentStop"]
        index = next(
            i for i, groupe in enumerate(groupes)
            if any(".agents/bin/plan_trace.py" in str(crochet)
                   for crochet in groupe.get("hooks", []))
        )
        charge["hooks"]["Stop"].append(groupes.pop(index))
        self.assertTrue(_erreurs_cablage_codex(charge))


class ChaineDePlanTests(unittest.TestCase):
    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.d = Path(self._tmp.name)
        for sub in ("board", "gates", "local/plan", "local/binome"):
            (self.d / ".agents" / "state" / sub).mkdir(parents=True, exist_ok=True)
        # Ids CAPTURÉS à la création, jamais prédits (T-00000726, R-BANCS (i)).
        self.t1 = self._nouvelle("tache de banc")
        self.t2 = self._nouvelle("seconde tache")

    def tearDown(self):
        self._tmp.cleanup()

    # -- outillage -----------------------------------------------------------
    def tasks(self, *args: str):
        return subprocess.run(
            [sys.executable, str(TASKS), "--root", str(self.d), *args],
            capture_output=True, text=True, timeout=60,
        )

    def _nouvelle(self, titre: str) -> str:
        """`new`, puis l'id RENDU (« TASKS: <id> → pending »)."""
        r = self.tasks("new", titre)
        trouve = re.search(r"^TASKS: (\S+) → pending$", r.stdout, re.M)
        self.assertIsNotNone(trouve, r.stdout + r.stderr)
        return trouve.group(1)

    def armer(self):
        (self.d / ".agents" / "state" / "gates" / "PLAN_CHAIN_REQUIRED").touch()

    def poser(self, *noms: str, quand: str | None = None):
        """Pose des traces comme le TRACEUR les écrit — `role` compris.

        LA PREMIÈRE RÉDACTION POSAIT `"role": "x"` ET RIEN NE BRONCHAIT, parce
        que `role` était alors écrit et jamais lu. Un champ décoratif dans une
        preuve se lit comme une garantie ; il est croisé avec le nom de fichier
        depuis, et ce banc doit donc poser la vraie valeur — sinon il testerait
        une charge qu'aucun hôte ne produit.

        `quand` par défaut = MAINTENANT, et pas une date figée : les traces
        PÉRIMENT (TTL), donc une constante de 2026 aurait fait rougir ce banc le
        jour où l'horloge la dépasse — un témoin qui meurt du calendrier.
        """
        horodatage = quand or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for nom in noms:
            role = "reviewer" if "critic" in nom else "planner"
            (self.d / ".agents" / "state" / "local" / "plan" / f"{nom}.json").write_text(
                json.dumps({"at": horodatage, "sha": "abc", "role": role}),
                encoding="utf-8",
            )

    def traces(self):
        return sorted(p.name for p in
                      (self.d / ".agents" / "state" / "local" / "plan").glob("*.json"))

    # -- le régime de référence ---------------------------------------------
    def test_marqueur_absent_la_garde_est_inerte(self):
        """L'ABSENCE du marqueur EST le régime de référence DU KIT, qui n'est pas
        armé : sans marqueur, rien ne change. L'adoptant, lui, naît ARMÉ — la
        sync template lui SÈME ce marqueur, et c'est sa présence qui mord."""
        r = self.tasks("start", self.t1)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("→ running", r.stdout)

    # -- les bras NÉGATIFS : la garde doit savoir refuser ---------------------
    def test_arme_sans_aucune_trace_refuse(self):
        self.armer()
        r = self.tasks("start", self.t1)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("la chaîne de plan n'est pas tracée", r.stderr)
        # S-01M4TZZ13Y : le refus ne propose plus les deux defs HORS CHAÎNE en
        # remède (ni repli, ni escalade). Rouges sur le refus d'avant la décision,
        # qui interpolait `PLAN_REVIEWERS[1]` et `PLAN_PLANNERS`.
        self.assertNotIn("plan-critic-sonnet-max", r.stderr)
        self.assertNotIn("planner-sonnet", r.stderr)

    def test_un_critique_mais_aucun_plan_refuse(self):
        """Un verdict sur un plan qui n'existe pas est un cas vide, pas un cas
        nominal : le critique seul ne suffit pas, il faut aussi un plan."""
        self.armer()
        self.poser("plan-critic")
        r = self.tasks("start", self.t1)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("aucun plan tracé", r.stderr)

    def test_une_trace_de_cloture_ne_vaut_pas_une_trace_de_plan(self):
        """ÉTANCHÉITÉ. `plan-critic-sonnet-max` contient la sous-chaîne
        `critic`, et ce dépôt a DÉJÀ corrigé un `startswith` trop large qui
        laissait un fichier posé à la main satisfaire une garde. Deux dossiers
        séparés rendent la confusion impossible plutôt qu'interdite."""
        self.armer()
        for critique in ("critic-opus", "critic-fable", "critic-sonnet-max"):
            (self.d / ".agents" / "state" / "local" / "binome"
             / f"{self.t1}.{critique}.json").write_text(
                json.dumps({"at": "2026-09-14T21:00:00Z", "sha": "abc"}), encoding="utf-8")
        self.poser("planner")
        r = self.tasks("start", self.t1)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("aucun critique de plan tracé", r.stderr)

    # -- le bras POSITIF, et sa non-vacuité ----------------------------------
    # CRITIQUE UNIQUE (décision pilote S-00003871, 2026-10-03) : `plan-critic`
    # est LE critique. Depuis S-01M4TZZ13Y (2026-10-13) `plan-critic-sonnet-max`
    # est HORS CHAÎNE, mais ses traces restent ACCEPTÉES par la garde, sans
    # échéance (tuples inchangés) ; chaque trace expire 24 h après son écriture,
    # comme toute trace. Les deux premiers bras ci-dessous sont ROUGES sous l'ancienne
    # exigence de DEUX critiques (mutant `len(relecteurs) >= 2` dans
    # `plan_chain_refusal`).
    def test_la_chaine_complete_passe_et_est_consommee(self):
        self.armer()
        self.poser("plan-critic", "planner")
        r = self.tasks("start", self.t1)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.traces(), [], "les traces devaient être CONSOMMÉES")
        journal = (self.d / ".agents" / "state" / "local"
                   / "plan-chain-consommations.log").read_text(encoding="utf-8")
        self.assertIn(self.t1, journal)
        self.assertIn("plan-critic@abc", journal)

    def test_le_repli_seul_passe(self):
        """Trace fraîche d'une déf HORS CHAÎNE (S-01M4TZZ13Y) : encore ACCEPTÉE
        par la garde, sans échéance ; chaque trace expire 24 h après son
        écriture, comme toute trace — une chaîne lancée avant la décision finit
        sans être refusée. Le refus ne la propose plus (voir
        `test_arme_sans_aucune_trace_refuse`)."""
        self.armer()
        self.poser("plan-critic-sonnet-max", "planner")
        r = self.tasks("start", self.t1)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.traces(), [], "les traces devaient être CONSOMMÉES")

    def test_une_paire_tracee_passe_et_est_consommee_entiere(self):
        """Une paire lancée avant S-00003871 finit : elle passe, et ses DEUX
        traces sont consommées — une moitié laissée couvrirait un second start."""
        self.armer()
        self.poser("plan-critic", "plan-critic-sonnet-max", "planner")
        r = self.tasks("start", self.t1)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.traces(), [], "les traces devaient être CONSOMMÉES")
        journal = (self.d / ".agents" / "state" / "local"
                   / "plan-chain-consommations.log").read_text(encoding="utf-8")
        self.assertIn("plan-critic-sonnet-max@abc", journal)

    def test_la_consommation_est_a_un_coup(self):
        """LE TÉMOIN QUI TIENT TOUS LES AUTRES. Si la consommation n'effaçait
        rien, chacun des bras ci-dessus resterait VERT et une seule chaîne de
        verdicts couvrirait tous les démarrages d'un chantier — le défaut exact
        que `T-00000592` a dû corriger APRÈS COUP sur le binôme de clôture.
        C'est aussi ce qui porte l'attribution : la trace ne nomme aucune tâche,
        donc seule la comptabilité « une chaîne = un démarrage » la porte."""
        self.armer()
        self.poser("plan-critic", "planner")
        self.assertEqual(self.tasks("start", self.t1).returncode, 0)
        r = self.tasks("start", self.t2)
        self.assertNotEqual(r.returncode, 0, "la MÊME chaîne a autorisé DEUX démarrages")
        self.assertIn("aucun critique de plan tracé", r.stderr)

    # -- les quatre contournements que la critique de plan a fait nommer -------
    def test_une_tache_bloquee_ne_contourne_pas_la_chaine(self):
        """MUTANT VERT MESURÉ, et c'est le témoin qui le tue. Ajouter
        `and before["state"] == "pending"` à la garde laissait les 17 témoins
        d'origine VERTS, et `block` puis `start` la franchissait en deux
        commandes, sans dérogation et sans rien au board. Aucun témoin ne
        variait l'ÉTAT DE DÉPART ; c'était le seul axe non couvert."""
        self.armer()
        self.tasks("block", self.t1, "--note", "en attente")
        r = self.tasks("start", self.t1)
        self.assertNotEqual(r.returncode, 0, "une tâche `blocked` a franchi la chaîne")
        self.assertIn("la chaîne de plan n'est pas tracée", r.stderr)

    def test_reouvrir_redemande_la_chaine(self):
        """Le drapeau `plan_chain_consumed` survit au board. Sans son retrait
        dans `reopen_task`, une tâche fermée puis rouverte sautait la garde
        DÉFINITIVEMENT — et cette mitigation était écrite dans la section Risks
        d'un plan sans exister nulle part dans le code. Rouvrir, c'est refaire du
        travail : le plan d'hier ne couvre pas ce qu'on réécrit aujourd'hui."""
        self.armer()
        self.poser("plan-critic", "plan-critic-sonnet-max", "planner")
        self.assertEqual(self.tasks("start", self.t1).returncode, 0)
        self.tasks("done", self.t1, "--raison", "fini", "--sans-binome", "banc")
        self.tasks("reopen", self.t1, "--raison", "on y retourne")
        r = self.tasks("start", self.t1)
        self.assertNotEqual(r.returncode, 0, "une tâche ROUVERTE a gardé son dédouanement")
        self.assertIn("la chaîne de plan n'est pas tracée", r.stderr)

    def test_une_trace_perimee_ne_couvre_plus_un_demarrage(self):
        """Sans péremption, UNE chaîne couvre tous les démarrages à venir — le
        défaut que `T-00000592` a dû corriger APRÈS COUP sur le binôme de
        clôture. Mesuré sur ce dépôt : une chaîne complète de la veille attendait
        d'autoriser le prochain `start`."""
        self.armer()
        vieux = (datetime.now(timezone.utc) - timedelta(hours=48)).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        self.poser("plan-critic", "plan-critic-sonnet-max", "planner", quand=vieux)
        r = self.tasks("start", self.t1)
        self.assertNotEqual(r.returncode, 0, "une trace de 48 h a couvert un démarrage")
        self.assertIn("PÉRIMÉE", r.stderr)

    def test_l_emprunt_de_groupe_est_ecrit_au_board(self):
        """UNE chaîne couvre légitimement un groupe parallèle — sa disjonction
        vient du shard split d'UN plan. Mais `declare_parallel_group` dit
        lui-même être « A GUARD OF COHERENCE, NOT OF SECURITY » : rien n'empêche
        un groupe bidon. L'emprunt est donc ÉCRIT au board, pour que le pilote
        voie de qui la tâche tient son dédouanement — et l'empruntante n'hérite
        PAS du drapeau, donc son prochain `start` hors groupe le redemandera."""
        self.armer()
        self.tasks("writeset", self.t1, "a/**")
        self.tasks("writeset", self.t2, "b/**")
        self.tasks("parallel", self.t1, self.t2)
        self.poser("plan-critic", "plan-critic-sonnet-max", "planner")
        self.assertEqual(self.tasks("start", self.t1).returncode, 0)
        r = self.tasks("start", self.t2)
        self.assertEqual(r.returncode, 0, r.stderr)
        vue = self.tasks("list", "--task", self.t2).stdout
        self.assertIn("chaîne de plan empruntée au groupe", vue)
        self.assertIn(self.t1, vue)

    # -- la sortie tracée ----------------------------------------------------
    def test_la_sortie_tracee_passe_et_reste_visible_au_board(self):
        """Une garde qui mord sur CHAQUE tâche sans échappatoire praticable est
        désarmée dans la semaine — mesuré deux fois sur ce dépôt. Elle ferme
        l'OUBLI, pas la TRICHE, et c'est la VISIBILITÉ qui rend la triche
        coûteuse."""
        self.armer()
        r = self.tasks("start", self.t1, "--sans-chaine", "coquille")
        self.assertEqual(r.returncode, 0, r.stderr)
        vue = self.tasks("list", "--task", self.t1).stdout
        self.assertIn("SANS CHAÎNE DE PLAN : coquille", vue)

    def test_la_derogation_sans_stage_ne_laisse_pas_fuir_None(self):
        """`--stage` est FACULTATIF sur `start`, contrairement au `--raison` de
        `done` : la première rédaction affichait le littéral `None` collé à la
        dérogation. Une dérogation illisible est une dérogation qu'on ne relit
        pas."""
        self.armer()
        self.tasks("start", self.t1, "--sans-chaine", "coquille")
        vue = self.tasks("list", "--task", self.t1).stdout
        self.assertNotIn("None [SANS CHAÎNE", vue)


class VocabulaireLieTests(unittest.TestCase):
    """LES DEUX MOITIÉS D'UN MÊME CONTRAT NE DOIVENT PAS DIVERGER.

    Le traceur écrit sous un nom ; le refus cherche ce nom. Une divergence
    produirait une preuve INVISIBLE — chaîne réellement jouée, démarrage refusé,
    et un message qui ne peut pas l'expliquer. Le binôme de clôture porte le même
    banc de liaison, pour la même raison.
    """

    def test_les_vocabulaires_sont_identiques_des_deux_cotes(self):
        tracer = _mod(TRACER, "plan_trace_mod")
        board = _mod(TASKS, "tasks_mod")
        self.assertEqual(tracer.PLAN_REVIEWERS, board.PLAN_REVIEWERS)
        self.assertEqual(tracer.PLAN_PLANNERS, board.PLAN_PLANNERS)

    def test_aucun_nom_de_plan_n_entre_dans_le_vocabulaire_de_cloture(self):
        """LE MÉLANGE EST LA FAUTE À NE PAS COMMETTRE : deux critiques de PLAN
        acceptés comme binôme de CLÔTURE, c'est la garde la plus lourde du dépôt
        franchie par un plan jamais relu APRÈS implémentation."""
        board = _mod(TASKS, "tasks_mod2")
        melange = set(board.PLAN_REVIEWERS + board.PLAN_PLANNERS) & set(board.BINOME_CRITIQUES)
        self.assertEqual(melange, set(), f"vocabulaires mélangés : {melange}")

    def test_les_deux_dossiers_de_traces_sont_distincts(self):
        board = _mod(TASKS, "tasks_mod3")
        self.assertNotEqual(board.PLAN_TRACES, board.BINOME_TRACES)


class TraceurTests(unittest.TestCase):
    """LE CANAL SE PROUVE BON AVANT QUE SON SILENCE NE PROUVE QUOI QUE CE SOIT.

    Un traceur qui ne trouve pas son champ se tait EXACTEMENT comme un traceur
    qui voit une def non concernée. Le bras négatif ne vaut donc rien sans le
    bras positif qui le précède — c'est la leçon `T-00000589`, où le traceur du
    binôme ne lisait que le snake_case et sortait 0 en silence sur tout hôte en
    camelCase.
    """

    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.d = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _tourne(self, charge: dict) -> list[str]:
        subprocess.run(
            [sys.executable, str(TRACER)], input=json.dumps(charge), text=True,
            capture_output=True, timeout=30, env={"CLAUDE_PROJECT_DIR": str(self.d),
                                                  "PATH": "/usr/bin:/bin"},
        )
        dossier = self.d / ".agents" / "state" / "local" / "plan"
        return sorted(p.name for p in dossier.glob("*.json")) if dossier.exists() else []

    def test_positif_snake_case(self):
        self.assertEqual(self._tourne({"agent_type": "plan-critic"}), ["plan-critic.json"])

    def test_positif_camel_case(self):
        """LES DEUX GRAPHIES DÈS LE PREMIER JOUR. Le traceur du binôme a mis un
        port entier à découvrir qu'il n'en lisait qu'une."""
        self.assertEqual(self._tourne({"agentType": "planner-sonnet"}),
                         ["planner-sonnet.json"])

    def test_negatif_une_def_non_concernee_n_ecrit_rien(self):
        """Canal prouvé par les deux tests ci-dessus : ce silence-ci SIGNIFIE
        quelque chose."""
        self.assertEqual(self._tourne({"agent_type": "dev-mono"}), [])

    def test_negatif_un_critique_de_cloture_n_ecrit_pas_de_trace_de_plan(self):
        self.assertEqual(self._tourne({"agent_type": "critic-opus"}), [])

    def test_negatif_charge_illisible(self):
        """ADVISORY, toujours `exit 0` — mais surtout : rien d'écrit. Une charge
        vide ne doit pas fabriquer une preuve."""
        self.assertEqual(self._tourne({}), [])


if __name__ == "__main__":
    unittest.main()
