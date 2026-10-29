#!/usr/bin/env python3
"""Banc de `setup_bilan.py` — le bilan vérifié du poste (T-01M54GEA4BNFC7QDJVK6P53Y4B, lot B).

Chaque scénario joue le VRAI `setup_bilan.py` (sous-processus, canal réel) sur une
racine JETABLE (`git init`, config git isolée) qui porte le vrai `.agents/pyrun.sh`,
des bouchons et les variables réservées aux bancs :
  BILAN_PROBE_PATH = <bouchons>:/usr/bin:/bin — un `python3` bouchon répond à la
                     sonde de `pyrun.sh` (son propre chemin), à la sonde de version
                     (fichier `version`) et à `dashboard_daemon.py --status`
                     (fichiers `demon.out`, `demon.err`, `demon.rc`) ;
  BILAN_DOCTOR     = un doctor bouchon qui recopie `doctor.out` (ou dort).

Témoins et le mutant qui les rougit (mesurés au clone de livraison) :
  seuil 3.11 (`VERSION_MIN` à (3, 9), ou `<` en `<=`) -> test_interpreteur ;
  Classe B ignorée / ligne `doctor:` non exigée -> test_outils ;
  protect-paths, chemin cité, core.hooksPath, `disableAllHooks`, dossier
  `.githooks` absent non jugés -> test_hooks ; remède `git config core.hooksPath .githooks`
  rendu inconditionnel, ou `--git-path hooks` résolu contre le cwd ->
  test_bilan_remede_conditionnel (T-01M5DJHCNK6ZX1XEG8XY0A8JR3) ;
  graine non lue (CHRONO_REQUIRED comprise) / marqueur du kit ignoré -> test_portes ;
  GRAINES désaccordées du canal seed du kit -> test_graines_egales_au_canal_seed ;
  `code: stale` non lu, `status: stale` en OK, plantage de la sonde -> test_dashboard ;
  `_tuer` sans `killpg`, ou `p.kill()` sur la branche du délai (le `sleep` du
  doctor survit) -> test_delai, qui exige sa mort par son pid ;
  le groupe non tué sur SIGINT -> test_sigint_ne_laisse_aucun_enfant ; SIGTERM
  sans gestionnaire -> test_sigterm_ne_laisse_aucun_enfant ;
  `--sans-ecrire` ignoré, `os.replace` retiré, contrat réécrit EN PLACE (inode
  inchangé), écriture à travers un lien symbolique (`.agents`, `.agents/state`
  ou `.agents/state/local`) -> test_contrat_* ;
  variable de banc posée mais tue, `BILAN_DOCTOR=""` étiquetée banc mais
  ignorée -> test_variables_de_banc_dites, test_bilan_doctor_vide_honore ;
  `datetime.UTC` (écriture), `zip(strict=True)` (analyse du doctor) -> SousPython39Tests,
  qui porte AUSSI ces deux mutants en non-vacuité.
Jambes version et scanners (T-01M5VYNMZPG8G0JZG48HV4K0PN, lot B) — AUCUN banc ne touche le
réseau : le dépôt du kit est un dépôt LOCAL (BILAN_KIT_REMOTE) ou un `git` journaliste qui
refuse tout `ls-remote` :
  tri lexical, clé dev/publiée inversée, remède ancien -> test_tri_numerique_et_remede ;
  marqueur du kit ignoré, tête `## Non publié` sautée, valeur `-x` passée à git ->
  test_git_jamais_lance ; URL de distribution, `--`, GIT_TERMINAL_PROMPT=0 ou GIT_ASKPASS
  vide retirés -> test_appel_par_defaut_sans_reseau ; borne 15 s retirée ->
  test_borne_15_s ; doctor rejoué par `scanners` -> test_doctor_joue_une_fois ; remède de
  famille générique, setup.sh proposé dans le kit (C15), paquet brew faux ->
  test_remede_par_plateforme ; ligne modules absente lue « aucun » ->
  test_modules_illisibles ; valeur de NVD_API_KEY imprimée ou écrite, clé non exigée sous
  java -> test_nvd_jamais_la_valeur ; SEMGREP_ENABLE_VERSION_CHECK=0 retiré, pin CI non lu ->
  test_semgrep_version_et_pin ; tables darwin du bilan et de setup.sh désaccordées (C17) ->
  PariteSetupShTests (ROUGE, jamais sauté, tant que la ligne SP_SCANNERS_DARWIN manque).
Passe de correction (exec-critic, sécurité) : titre du journal du kit non exigé ->
  test_changelog_de_l_adoptant ; titre désaccordé du journal livré ->
  test_titre_epingle_au_journal_livre ; dernière ligne de git au lieu de la 1re `fatal:` ->
  test_injoignable_dit_la_cause ; userinfo affichée -> test_userinfo_jamais_dite ; nombres
  non bornés -> test_nombres_bornes ; `-c credential.helper=` retiré sous BILAN_KIT_REMOTE,
  ou BatchMode retiré -> test_appel_de_banc_sans_assistant ; semgrep de l'arbre exécuté ->
  test_semgrep_du_projet_jamais_lance ; détail scanners non neutralisé ->
  test_detail_sans_controles.
Passe de clôture (critic-opus, décision pilote S-01M5WJR9ME0EKZC1RPGDMC316D, dépôt PRIVÉ) :
  `-c credential.helper=` posé sur l'URL de distribution, GCM_INTERACTIVE=never ou
  GIT_TERMINAL_PROMPT=0 retirés -> test_appel_par_defaut_sans_reseau ; « could not read
  Username » dit injoignable -> test_depot_prive_sans_identifiants ; userinfo d'une URL dans
  la ligne de git -> test_userinfo_dans_l_erreur_de_git ; `@` du mot de passe qui laisse sa
  fin -> test_userinfo_jamais_dite ; BOM en tête du CHANGELOG -> test_changelog_avec_bom ;
  remède setup.sh sur la plateforme windows -> test_remede_outils_windows.
`DefautsReelsTests` joue le bilan sur l'arbre qui porte ce banc, sans `--root`, depuis
un autre répertoire, `--sans-ecrire` : rien n'est écrit sous la racine réelle.

BORNES : bouchons shell POSIX — sous Windows les classes à bouchons SAUTENT,
annoncé ; l'interpréteur < 3.11 réel est cherché par `uv python find 3.9`, puis
`/usr/bin/python3` s'il rend < 3.11, sinon saut ANNONCÉ.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path

ICI = Path(__file__).resolve().parent
BILAN = ICI / "setup_bilan.py"
ROOT = ICI.parents[1]
GIT = shutil.which("git")
POSIX = os.name != "nt"

_LIGNE = re.compile(r"^bilan: (?P<jambe>\S+) : (?P<etat>OK|KO|SANS OBJET) — (?P<detail>.*?)"
                    r"(?: ; remède : (?P<remede>.*))?$")
_RESUME = re.compile(r"^bilan: OK=(\d+) KO=(\d+) SANS OBJET=(\d+) — exit (\d+)$")
JAMBES = ["version", "outils", "scanners", "interpréteur", "hooks", "portes", "dashboard"]
REMEDE_PY = "installer Python ≥ 3.11 et le placer avant dans le PATH"
REMEDE_VERSION = "usage.html § Monter de version du kit (#monter-version)"
REMEDE_SETUP = "bash core-scripts/setup.sh"
URL_KIT = "https://gitlab.groupeonepoint.com/glass-factory/glass-factory-kit.git"
ACTIVER = "git config core.hooksPath .githooks"
REMEDE_SANS_DOSSIER = ("bloc hooks du kit ; .githooks/ absent : resynchroniser le kit avant "
                       "toute activation")
GRAINES = ("BINOME_REQUIRED", "CHRONO_REQUIRED", "CONFIG_QUALITE_PROTEGE", "PLAN_CHAIN_REQUIRED",
           "PLAN_CIBLE_REQUIRED")


def _survit(pid: int, delai: float) -> bool:
    """Vrai si `pid` vit encore après `delai` s ; un survivant est tué (aucun orphelin laissé)."""
    limite = time.monotonic() + delai
    while time.monotonic() < limite:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        time.sleep(0.05)
    os.kill(pid, signal.SIGKILL)
    return True

_PYTHON_BOUCHON = """#!/bin/sh
d="${0%/*}"
case "$*" in
  *sys.stdout.write*) printf '%s' "$0"; exit 0 ;;
  *dashboard_daemon.py*) cat "$d/demon.out"; cat "$d/demon.err" >&2; exit "$(cat "$d/demon.rc")" ;;
esac
v="$(cat "$d/version")"
if [ "$v" = ECHEC ]; then echo "interpreteur casse" >&2; exit 3; fi
printf '%s\\n%s\\n' "$v" "$0"
"""
_DOCTOR_BOUCHON = """#!/bin/sh
d="${0%/*}"
echo appel >> "$d/doctor.appels"
if [ -f "$d/doctor.dort" ]; then sleep 30 & echo $! > "$d/doctor.pid"; wait; fi
if [ -f "$d/doctor.evade" ]; then
  "$(cat "$d/doctor.evade")" -c 'import os, time; os.setsid(); time.sleep(30)' &
  echo $! > "$d/doctor.pid"; wait
fi
cat "$d/doctor.out"
"""

_B_PRESENT = ("  PRESENT                  git — /usr/bin/git — version 2.50.0, attendue >=2.34\n"
              "  PRESENT (python3)        python3|python|py — /x/python3 — version 3.12.1, "
              "attendue >=3.11\n"
              "  PRESENT                  pytest — /x/python3 -m pytest\n")


_A_SCANNERS = ("  PRESENT                  gitleaks — /x/gitleaks\n"
               "  PRESENT                  semgrep — /x/semgrep\n")


def _absent(outil: str) -> str:
    return f"  ABSENT (optionnel)       {outil} — version attendue : aucune — coût : x\n"


def _doctor(classe_b: str = _B_PRESENT, classe_a: str = "", compte: bool = True,
            section_b: bool = True, scanners: str = _A_SCANNERS, modules: str | None = "aucun",
            plateforme: str = "darwin") -> str:
    """La sortie du doctor ; `doctor: modules :` imprimée AVANT le résumé (lot A)."""
    texte = f"doctor — outils du poste\n\nPlateforme\n  {plateforme} (uname -s : X)\n"
    if section_b:
        texte += "\nClasse B — absence : porte nue du kit ROUGE\n" + classe_b
    texte += ("\nClasse A — absence : annoncée (saut ou COVERAGE DEGRADED), porte verte\n"
              "  PRESENT                  ctags — /x/ctags\n" + scanners + classe_a + "\n")
    if modules is not None:
        texte += f"doctor: modules : {modules}\n"
    if compte:
        texte += ("doctor: 4/5 présents, 0 N/A, 1 absents (B manquants=aucun, A manquants=1), "
                  "mauvaise version=aucune, 9 conditions non sondées — exit 0\n")
    return texte


def _lire(stdout: str):
    jambes, resume = {}, None
    for ligne in stdout.splitlines():
        m = _LIGNE.match(ligne)
        if m and m["jambe"] in JAMBES:
            jambes[m["jambe"]] = (m["etat"], m["detail"], m["remede"])
        r = _RESUME.match(ligne)
        if r:
            resume = tuple(int(x) for x in r.groups())
    return jambes, resume


class _Racine:
    """Une racine jetable dont chaque jambe vaut OK par défaut."""

    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.racine = tmp / "racine"
        self.bouchons = tmp / "bouchons"
        for d in (self.racine / ".agents" / "bin", self.bouchons, self.racine / ".githooks",
                  self.racine / ".claude" / "hooks", self.racine / ".agents" / "state" / "gates"):
            d.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / ".agents" / "pyrun.sh", self.racine / ".agents" / "pyrun.sh")
        (self.racine / ".agents" / "bin" / "dashboard_daemon.py").write_text("", encoding="utf-8")
        for nom, texte in (("python3", _PYTHON_BOUCHON), ("doctor.sh", _DOCTOR_BOUCHON)):
            (self.bouchons / nom).write_text(texte, encoding="utf-8")
            (self.bouchons / nom).chmod(0o755)
        self.poser(version="3.12.1", demon={"status": "alive", "code": "current"}, demon_rc=0,
                   demon_err="", doctor=_doctor())
        self.reglages({"hooks": {"PreToolUse": [{"hooks": [{"type": "command", "command":
                       'bash "$CLAUDE_PROJECT_DIR/.claude/hooks/protect-paths.sh"'}]}]}})
        (self.racine / ".claude" / "hooks" / "protect-paths.sh").write_text("", encoding="utf-8")
        for graine in GRAINES:
            (self.racine / ".agents" / "state" / "gates" / graine).write_text("", encoding="utf-8")
        (tmp / "gitconfig").write_text("", encoding="utf-8")
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith(("GIT_", "BILAN_", "CLAUDE_")) and k != "NVD_API_KEY"}
        self.env.update({"GIT_CONFIG_GLOBAL": str(tmp / "gitconfig"), "GIT_CONFIG_NOSYSTEM": "1",
                         "BILAN_PROBE_PATH": f"{self.bouchons}:/usr/bin:/bin",
                         "BILAN_DOCTOR": str(self.bouchons / "doctor.sh"),
                         "PYTHONDONTWRITEBYTECODE": "1"})
        self.git("init", "-q")
        self.git("config", "core.hooksPath", ".githooks")

    def git(self, *args: str) -> None:
        subprocess.run([GIT, "-C", str(self.racine), *args], check=True, capture_output=True,
                       env=getattr(self, "env", None))

    def poser(self, **valeurs) -> None:
        for cle, valeur in valeurs.items():
            nom = {"demon": "demon.out", "demon_rc": "demon.rc", "demon_err": "demon.err",
                   "doctor": "doctor.out"}.get(cle, cle)
            json_attendu = cle == "demon" and not isinstance(valeur, str)
            texte = json.dumps(valeur) if json_attendu else str(valeur)
            (self.bouchons / nom).write_text(texte, encoding="utf-8")

    def reglages(self, donnees) -> None:
        texte = donnees if isinstance(donnees, str) else json.dumps(donnees)
        (self.racine / ".claude" / "settings.json").write_text(texte, encoding="utf-8")

    def jouer(self, *args: str, python: str = sys.executable, script: Path = BILAN):
        p = subprocess.run([python, str(script), "--root", str(self.racine), *args],
                           cwd=str(self.tmp), env=self.env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=180,
                           stdin=subprocess.DEVNULL, check=False)
        return p.returncode, p.stdout, p.stderr

    @property
    def contrat(self) -> Path:
        return self.racine / ".agents" / "state" / "local" / "setup-bilan.json"


#: Le titre du journal que le kit livre (.agents/adopter-docs/CHANGELOG.md:1), épinglé par
#: test_titre_epingle_au_journal_livre.
TITRE_KIT = "# Journal des versions — Cadre"


def _changelog(r: _Racine, tete: str, titre: str = TITRE_KIT) -> None:
    (r.racine / "CHANGELOG.md").write_text(f"{titre}\n\nTexte.\n\n{tete}\n\n## 0.0.1 — 2026-01-01\n",
                                           encoding="utf-8")


def _depot_kit(r: _Racine, *versions: str) -> Path:
    """Un dépôt LOCAL qui porte exactement les tags `template/v<version>-2026-10-01`."""
    depot = r.tmp / "kit-distant"
    git = [GIT, "-C", str(depot)]
    if not depot.is_dir():
        depot.mkdir()
        subprocess.run([*git, "init", "-q"], check=True, capture_output=True, env=r.env)
        subprocess.run([*git, "-c", "user.name=banc", "-c", "user.email=banc@exemple.invalid",
                        "commit", "-q", "--allow-empty", "-m", "kit"], check=True,
                       capture_output=True, env=r.env)
    anciens = subprocess.run([*git, "tag", "-l"], check=True, capture_output=True, text=True,
                             env=r.env).stdout.split()
    for tag in anciens:
        subprocess.run([*git, "tag", "-d", tag], check=True, capture_output=True, env=r.env)
    for version in versions:
        subprocess.run([*git, "tag", f"template/v{version}-2026-10-01"], check=True,
                       capture_output=True, env=r.env)
    subprocess.run([*git, "tag", "template/v9.9.9-sans-date"], check=True, capture_output=True,
                   env=r.env)  # hors forme TAG_RE : jamais lu comme une version
    return depot


#: Un `git` journaliste : tout `ls-remote` est JOURNALISÉ (argv, GIT_TERMINAL_PROMPT,
#: GIT_ASKPASS, SSH_ASKPASS, GCM_INTERACTIVE, GIT_SSH_COMMAND) puis, jamais le réseau : endormi
#: (`ls-remote.dort`), réponse fabriquée rc 0 (`ls-remote.sortie`), échec fabriqué rc 128
#: (`ls-remote.err` sur stderr), sinon rc 2 ; le reste va au vrai git.
_GIT_JOURNALISTE = """#!/bin/sh
d="${0%/*}"
case " $* " in
  *" ls-remote "*)
    printf '%s|%s|%s|%s|%s|%s\\n' "$*" "${GIT_TERMINAL_PROMPT-absent}" "${GIT_ASKPASS-absent}" \\
      "${SSH_ASKPASS-absent}" "${GCM_INTERACTIVE-absent}" "${GIT_SSH_COMMAND-absent}" >> "$d/ls-remote.log"
    if [ -f "$d/ls-remote.dort" ]; then sleep 30 & echo $! > "$d/ls-remote.pid"; wait; fi
    if [ -f "$d/ls-remote.sortie" ]; then cat "$d/ls-remote.sortie"; exit 0; fi
    if [ -f "$d/ls-remote.err" ]; then cat "$d/ls-remote.err" >&2; exit 128; fi
    exit 2 ;;
esac
exec @GIT@ "$@"
"""


@unittest.skipIf(not POSIX or GIT is None, "SAUT ANNONCÉ — bouchons shell POSIX et git requis")
class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="setup-bilan-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.r = _Racine(self.tmp)

    def jambe(self, nom: str, *args: str):
        rc, out, err = self.r.jouer("--sans-ecrire", *args)
        jambes, resume = _lire(out)
        self.assertIn(nom, jambes, out + err)
        return jambes[nom], rc, out + err


class ToutOkTests(_Base):
    def test_tout_ok_et_json_egal_aux_lignes(self):
        rc, out, err = self.r.jouer()
        jambes, resume = _lire(out)
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(list(jambes), JAMBES, out)
        # Sans CHANGELOG.md versionné, la jambe version ne compare rien (aucun réseau).
        attendus = {**dict.fromkeys(JAMBES, "OK"), "version": "SANS OBJET"}
        self.assertEqual({k: v[0] for k, v in jambes.items()}, attendus, out)
        self.assertEqual(out.strip().splitlines()[-1], "bilan: OK=6 KO=0 SANS OBJET=1 — exit 0")
        contrat = json.loads(self.r.contrat.read_text(encoding="utf-8"))
        self.assertEqual((contrat["schema"], contrat["rc"], contrat["commande"]),
                         (1, 0, "python3 .agents/bin/setup_bilan.py"))
        ecrites = [(j["jambe"], j["etat"], j["detail"], j["remede"]) for j in contrat["jambes"]]
        self.assertEqual(ecrites, [(n, *jambes[n]) for n in JAMBES])
        self.assertIsNotNone(datetime.fromisoformat(contrat["genere_le"]).utcoffset())


class InterpreteurTests(_Base):
    def test_interpreteur(self):
        for version, etat in (("3.9.6", "KO"), ("3.10.14", "KO"), ("3.11.0", "OK"),
                              ("3.12.1", "OK")):
            with self.subTest(version=version):
                self.r.poser(version=version)
                (e, detail, remede), rc, sortie = self.jambe("interpréteur")
                self.assertEqual(e, etat, sortie)
                self.assertIn(str(self.r.bouchons / "python3"), detail, "l'exécutable est nommé")
                self.assertIn(version, detail)
                if etat == "KO":
                    self.assertEqual(remede, REMEDE_PY)
                    self.assertEqual(rc, 1)
        self.r.poser(version="ECHEC")
        (e, detail, remede), rc, sortie = self.jambe("interpréteur")
        self.assertEqual((e, "rc 3" in detail, "interpreteur casse" in detail), ("KO", True, True),
                         sortie)


class OutilsTests(_Base):
    def test_outils(self):
        absent = "  ABSENT (requis)          tee — version attendue : aucune — coût : rouge\n"
        mauvaise = ("  MAUVAISE VERSION         bash — /bin/bash — version 3.2.57, attendue >=4 "
                    "— coût : rouge\n")
        cas = {
            "absent B": (_doctor(_B_PRESENT + absent), "KO", "tee ABSENT (requis)"),
            "mauvaise version B": (_doctor(_B_PRESENT + mauvaise), "KO", "bash MAUVAISE VERSION"),
            "absent A seul": (_doctor(classe_a="  ABSENT (optionnel)       k6 — x\n"
                                      + mauvaise.replace("bash", "node")), "OK", "doctor: 4/5"),
            "sans ligne doctor:": (_doctor(compte=False), "KO", "doctor illisible"),
            "sans section B": (_doctor(section_b=False), "KO", "doctor illisible"),
        }
        for nom, (texte, etat, morceau) in cas.items():
            with self.subTest(cas=nom):
                self.r.poser(doctor=texte)
                (e, detail, remede), rc, sortie = self.jambe("outils")
                self.assertEqual(e, etat, sortie)
                self.assertIn(morceau, detail)
                self.assertIn(str(self.r.bouchons / "doctor.sh"), detail, "le doctor lu est nommé")
                self.assertEqual(remede, None if etat == "OK" else "bash core-scripts/setup.sh")

    def test_remede_outils_windows(self):
        """Plateforme windows du doctor : setup.ps1 par la commande de docs/usage.html, sur
        `outils` ET sur le doctor illisible de `scanners` ; linux : setup.sh. Mutant : remède
        setup.sh inconditionnel -> rouge."""
        windows = r"powershell -NoProfile -ExecutionPolicy Bypass -File core-scripts\setup.ps1"
        absent = "  ABSENT (requis)          tee — version attendue : aucune — coût : rouge\n"
        for plateforme, attendu in (("windows", windows), ("linux", REMEDE_SETUP)):
            with self.subTest(plateforme=plateforme):
                self.r.poser(doctor=_doctor(_B_PRESENT + absent, plateforme=plateforme))
                (e, _, remede), _, sortie = self.jambe("outils")
                self.assertEqual((e, remede), ("KO", attendu), sortie)
                self.r.poser(doctor=f"Plateforme\n  {plateforme} (uname -s : X)\n")
                (e, _, remede), _, sortie = self.jambe("scanners")
                self.assertEqual((e, remede), ("KO", attendu), sortie)

    def test_remede_windows_egal_a_usage(self):
        """`REMEDE_OUTILS_WINDOWS` == la commande setup.ps1 que docs/usage.html fait taper."""
        usage = next((p for p in (ROOT / ".agents" / "adopter-docs" / "docs" / "usage.html",
                                  ROOT / "docs" / "usage.html") if p.is_file()), None)
        if usage is None:
            self.skipTest("SAUT ANNONCÉ — docs/usage.html absent de cet arbre")
        self.assertIn(_module_bilan().REMEDE_OUTILS_WINDOWS, usage.read_text(encoding="utf-8"),
                      f"le remède windows diverge de la commande de {usage}")


class HooksTests(_Base):
    def test_diagnostics_sans_controles(self):
        self.r.git("config", "core.hooksPath", "ailleurs\x1b[31m")
        (_, detail, remede), _, sortie = self.jambe("hooks")
        self.assertNotIn("\x1b", detail + (remede or "") + sortie)
        self.r.git("config", "--unset", "core.hooksPath")
        (self.r.racine / ".git" / "hooks" / "pre-\x1b[31mpush").write_text("hook\n",
                                                                   encoding="utf-8")
        (_, detail, remede), _, sortie = self.jambe("hooks")
        self.assertNotIn("\x1b", detail + (remede or "") + sortie)

    def test_githooks_lien_hors_racine(self):
        """Le refus du setup (`.githooks/ hors de cette racine`) tient au bilan : jambe KO, et le
        remède ne propose jamais l'activation. MUTANT : retirer le contrôle ⇒ OK ou `git config`."""
        externe = self.tmp / "externe"
        externe.mkdir()
        (self.r.racine / ".githooks").rmdir()
        (self.r.racine / ".githooks").symlink_to(externe, target_is_directory=True)
        (e, detail, remede), _, sortie = self.jambe("hooks")
        self.assertEqual(e, "KO", sortie)
        self.assertIn(".githooks/ hors de cette racine", detail)
        self.assertIn(".githooks/ hors de cette racine", remede or "")
        self.assertNotIn("git config core.hooksPath", sortie)

    def test_hooks(self):
        remede = "bloc hooks du kit ; git config core.hooksPath .githooks"
        (e, detail, r), _, sortie = self.jambe("hooks")
        self.assertEqual(e, "OK", sortie)
        self.assertIn("1 chemin(s) cité(s)", detail)
        self.assertIn("jamais « tirés par l'hôte »", detail)
        commande = 'bash "$CLAUDE_PROJECT_DIR/.claude/hooks/{}"'
        cas = {
            "sans protect-paths": ({"hooks": {"Stop": [{"hooks": [{"command": commande.format(
                "autre.sh")}]}]}}, "aucun hook protect-paths"),
            "chemin cité absent": ({"hooks": {"Stop": [{"hooks": [{"command": commande.format(
                "protect-paths.sh") + "; " + commande.format("manque.sh")}]}]}},
                ".claude/hooks/manque.sh"),
            "hors racine": ({"hooks": {"Stop": [{"hooks": [{"command": commande.format(
                "protect-paths.sh") + "; " + commande.format("../../x.sh")}]}]}}, "hors racine"),
            "sans bloc hooks": ({"permissions": {}}, "sans bloc hooks"),
            "illisible": ("{pas du json", "illisible"),
        }
        for nom, (donnees, morceau) in cas.items():
            with self.subTest(cas=nom):
                self.r.reglages(donnees)
                (e, detail, r), rc, sortie = self.jambe("hooks")
                self.assertEqual((e, r, rc), ("KO", remede, 1), sortie)
                self.assertIn(morceau, detail)
        sain = {"hooks": {"Stop": [{"hooks": [{"command": commande.format("protect-paths.sh")}]}]}}
        local = self.r.racine / ".claude" / "settings.local.json"
        for nom, fichier in (("settings.json", None), ("settings.local.json", local)):
            with self.subTest(disableAllHooks=nom):
                if fichier is None:
                    self.r.reglages({**sain, "disableAllHooks": True})
                else:
                    self.r.reglages(sain)
                    fichier.write_text(json.dumps({"disableAllHooks": True}), encoding="utf-8")
                (e, detail, r), rc, sortie = self.jambe("hooks")
                self.assertEqual((e, r, rc), ("KO", remede, 1), sortie)
                self.assertIn(f".claude/{nom} : disableAllHooks = true", detail)
        local.write_text(json.dumps({"disableAllHooks": False}), encoding="utf-8")
        self.r.reglages(sain)
        (e, detail, r), _, sortie = self.jambe("hooks")
        self.assertEqual(e, "OK", sortie)
        githooks = self.r.racine / ".githooks"
        githooks.rmdir()
        (e, detail, r), _, sortie = self.jambe("hooks")
        self.assertEqual((e, r), ("KO", REMEDE_SANS_DOSSIER), sortie)
        self.assertIn(f"mais {githooks} absent", detail)
        githooks.mkdir()
        etranger = ("bloc hooks du kit ; core.hooksPath = {} conservé : y intégrer les hooks du "
                    "kit, en chaînant les noms communs")
        # Posée VIDE, Git lit `./` (mesuré 2.55) : une valeur étrangère, jamais écrasée.
        for valeur, morceau, attendu in (("", "core.hooksPath posé vide (Git lit ./)",
                                          etranger.format("(vide)")),
                                         ("/ailleurs/.githooks", "pas .githooks",
                                          etranger.format("/ailleurs/.githooks"))):
            with self.subTest(hooks_path=valeur):
                self.r.git("config", "core.hooksPath", valeur)
                (e, detail, r), _, sortie = self.jambe("hooks")
                self.assertEqual((e, r), ("KO", attendu), sortie)
                self.assertIn(morceau, detail)
        (self.r.racine / ".claude" / "settings.json").unlink()
        (e, detail, r), _, sortie = self.jambe("hooks")
        self.assertEqual((e, detail), ("KO", ".claude/settings.json absent"), sortie)

    def test_bilan_remede_conditionnel(self):
        """T-01M5DJHCNK6ZX1XEG8XY0A8JR3 : appelé SEUL, depuis un cwd extérieur à la racine, le
        bilan ne propose `git config core.hooksPath .githooks` qu'avec `.githooks/` présent, sans
        valeur étrangère ni hook actif. Mutants : remède inconditionnel, `--git-path hooks` résolu
        contre le cwd -> rouge (cas « pre-push et pre-commit actifs »)."""
        self.r.git("config", "--unset", "core.hooksPath")
        hooks = self.r.racine / ".git" / "hooks"
        (hooks / "pre-push.sample").write_text("#!/bin/sh\n", encoding="utf-8")
        (e, detail, r), _, sortie = self.jambe("hooks")
        self.assertEqual((e, r), ("KO", "bloc hooks du kit ; " + ACTIVER), sortie)
        (hooks / "pre-push").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        (hooks / "pre-push").chmod(0o755)
        (hooks / "pre-commit").symlink_to(hooks / "pre-push")  # un lien compte comme un hook
        sain = json.loads((self.r.racine / ".claude" / "settings.json").read_text(encoding="utf-8"))
        for nom, reglages in (("jambe git", sain), ("réglages KO", {"permissions": {}})):
            with self.subTest(cas=nom):
                self.r.reglages(reglages)
                (e, detail, r), rc, sortie = self.jambe("hooks")
                self.assertEqual((e, rc), ("KO", 1), sortie)
                self.assertIn(f"hooks actifs dans {hooks} (pre-commit, pre-push)", r, sortie)
                self.assertIn("chaîner les deux pre-push, jamais copier celui du kit par-dessus", r)
                self.assertIn("sans changer core.hooksPath", r)
                self.assertNotIn(ACTIVER, sortie, "le remède contourne le refus")
                self.assertNotIn("cp ", sortie, "conseil de copie par-dessus")
        self.r.reglages(sain)
        (hooks / "pre-push").unlink()
        (hooks / "pre-commit").unlink()
        (hooks / "pre-commit").write_text("#!/bin/sh\n", encoding="utf-8")
        (e, detail, r), _, sortie = self.jambe("hooks")
        self.assertIn("(pre-commit) : intégrer ces hooks", r, sortie)
        self.assertTrue(r.endswith("— chaîner les noms communs"), r)
        self.assertNotIn(ACTIVER, sortie)
        if os.geteuid() != 0:  # root lit un répertoire 000 : sous-cas sans objet
            hooks.chmod(0)
            try:
                (e, detail, r), _, sortie = self.jambe("hooks")
            finally:
                hooks.chmod(0o755)
            self.assertTrue(r.startswith("bloc hooks du kit ; lecture git échouée"), sortie)
            self.assertIn("inventaire de", r)
            self.assertNotIn(ACTIVER, sortie)
        (self.r.racine / ".githooks").rmdir()
        (e, detail, r), _, sortie = self.jambe("hooks")
        self.assertEqual((e, r), ("KO", REMEDE_SANS_DOSSIER), sortie)
        self.assertNotIn(ACTIVER, sortie)


class PortesTests(_Base):
    def test_portes(self):
        (self.r.racine / ".agents" / "state" / "gates" / "PLAN_CHAIN_REQUIRED").unlink()
        (e, detail, remede), rc, sortie = self.jambe("portes")
        self.assertEqual((e, rc), ("KO", 1), sortie)
        self.assertIn("PLAN_CHAIN_REQUIRED", detail)
        self.assertNotIn("BINOME_REQUIRED", detail)
        self.assertIn("indiscernable ici", detail)
        self.assertEqual(remede, "rétablir par la sync du template si non voulu")
        (self.r.racine / ".agents" / "IS_THE_KIT").write_text("kit\n", encoding="utf-8")
        (e, detail, remede), _, sortie = self.jambe("portes")
        self.assertEqual((e, remede), ("SANS OBJET", None), sortie)
        for graine in GRAINES:
            self.assertIn(graine, detail)
        (self.r.racine / ".agents" / "IS_THE_KIT").unlink()
        (self.r.racine / ".agents" / "state" / "gates" / "PLAN_CHAIN_REQUIRED").write_text(
            "", encoding="utf-8")
        (self.r.racine / ".agents" / "state" / "gates" / "CHRONO_REQUIRED").unlink()
        (e, detail, remede), rc, sortie = self.jambe("portes")
        self.assertEqual((e, rc), ("KO", 1), sortie)
        self.assertTrue(detail.startswith("CHRONO_REQUIRED absente(s)"), detail)

    def test_graines_egales_au_canal_seed(self):
        """GRAINES du bilan == les portes que le canal seed du kit pose chez l'adoptant."""
        seed = ROOT / ".agents" / "adopter-seed" / "gates"
        if not seed.is_dir():
            self.skipTest("SAUT ANNONCÉ — canal seed absent (adoptant) : témoin réservé au kit")
        spec = importlib.util.spec_from_file_location("_banc_setup_bilan", BILAN)
        setup_bilan = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = setup_bilan  # T-00000134 ; nom privé, chargé par chemin : sys.path intact
        spec.loader.exec_module(setup_bilan)
        semees = {p.name for p in seed.iterdir() if p.is_file()}
        self.assertTrue(semees, "canal seed vide : le témoin serait vert par vacuité")
        self.assertEqual(set(setup_bilan.GRAINES), semees)
        self.assertEqual(set(GRAINES), semees, "la racine jetable du banc pose une autre liste")


class DashboardTests(_Base):
    def test_dashboard(self):
        cas = {
            "code périmé": ({"status": "alive", "code": "stale"}, 0, "", "KO", "code: stale"),
            "verrou sans démon": ({"status": "stale", "lock": None}, 0, "", "KO", "status: stale"),
            "absent": ({"status": "absent"}, 0, "", "KO", "status: absent"),
            "sonde qui plante": ("", 1, "Traceback (most recent call last):\n  x\n"
                                 "ModuleNotFoundError: No module named 'tomllib'", "KO",
                                 "sonde illisible : ModuleNotFoundError: No module named "
                                 "'tomllib'"),
            "vivant": ({"status": "alive", "code": "current"}, 0, "", "OK", "démon vivant"),
        }
        for nom, (demon, rc_demon, err, etat, morceau) in cas.items():
            with self.subTest(cas=nom):
                self.r.poser(demon=demon, demon_rc=rc_demon, demon_err=err)
                (e, detail, remede), _, sortie = self.jambe("dashboard")
                self.assertEqual(e, etat, sortie)
                self.assertIn(morceau, detail)
                if nom == "code périmé":
                    self.assertRegex(remede or "", r"dashboard_daemon\.py --stop, puis /dash")
                elif nom == "sonde qui plante":
                    self.assertEqual(remede, REMEDE_PY)
                elif etat == "KO":
                    self.assertEqual(remede, "/dash ($dash hors Claude Code)")
                    self.assertNotIn("--stop", remede)


class DelaiTests(_Base):
    def test_delai(self):
        (self.r.bouchons / "doctor.dort").write_text("", encoding="utf-8")
        debut = time.monotonic()
        (e, detail, remede), rc, sortie = self.jambe("outils", "--delai", "1")
        duree = time.monotonic() - debut
        self.assertEqual((e, rc), ("KO", 1), sortie)
        self.assertIn("délai dépassé (1 s)", detail)
        self.assertLess(duree, 20, "lecture non bornée après le délai")
        # La durée seule ne prouve rien : `_vider` borne la lecture à 5 s, même groupe non tué.
        enfant = int((self.r.bouchons / "doctor.pid").read_text().strip())
        self.assertFalse(_survit(enfant, 5), f"le sleep {enfant} du doctor a survécu au délai : "
                                             "groupe non tué")

    def test_lecture_bornee_apres_kill(self):
        """Un petit-enfant sorti du groupe (`setsid`) tient le tube après le kill :
        la lecture qui suit est bornée (5 s), le bilan rend quand même son KO."""
        (self.r.bouchons / "doctor.evade").write_text(sys.executable, encoding="utf-8")
        pidfile = self.r.bouchons / "doctor.pid"

        def _tuer_l_evade():
            if pidfile.exists() and pidfile.read_text().strip():
                try:
                    os.kill(int(pidfile.read_text().strip()), signal.SIGKILL)
                except ProcessLookupError:
                    pass
        self.addCleanup(_tuer_l_evade)
        debut = time.monotonic()
        (e, detail, remede), rc, sortie = self.jambe("outils", "--delai", "1")
        duree = time.monotonic() - debut
        self.assertEqual((e, rc), ("KO", 1), sortie)
        self.assertIn("délai dépassé (1 s)", detail)
        self.assertLess(duree, 20, "lecture non bornée après le kill : le petit-enfant hors "
                                   "groupe a tenu le tube 30 s")

    def _interrompre(self, signum: int) -> tuple[int, int]:
        """Le bilan interrompu par `signum` pendant le doctor : (son rc, le pid du `sleep`)."""
        (self.r.bouchons / "doctor.dort").write_text("", encoding="utf-8")
        pidfile = self.r.bouchons / "doctor.pid"
        p = subprocess.Popen([sys.executable, str(BILAN), "--root", str(self.r.racine),
                              "--sans-ecrire"], cwd=str(self.tmp), env=self.r.env,
                             stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE,
                             # Sous la porte, les bancs tournent en tâche de fond :
                             # SIGINT y est hérité IGNORÉ et le bilan ne le recevrait jamais.
                             preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_DFL))
        self.addCleanup(lambda: p.poll() is None and p.kill())
        limite = time.monotonic() + 20
        while not (pidfile.exists() and pidfile.read_text().strip()) and time.monotonic() < limite:
            time.sleep(0.05)
        enfant = int(pidfile.read_text().strip())
        p.send_signal(signum)
        p.communicate(timeout=20)
        return p.returncode, enfant

    def test_sigint_ne_laisse_aucun_enfant(self):
        """Interrompu (SIGINT) pendant le doctor, le bilan tue le GROUPE de
        l'enfant avant de sortir : le `sleep` du doctor ne lui survit pas."""
        _, enfant = self._interrompre(signal.SIGINT)
        self.assertFalse(_survit(enfant, 5), f"le sleep {enfant} du doctor a survécu au bilan "
                                             "interrompu")

    def test_sigterm_ne_laisse_aucun_enfant(self):
        """SIGTERM devient SystemExit(143) : même mise à mort du groupe que SIGINT."""
        rc, enfant = self._interrompre(signal.SIGTERM)
        survit = _survit(enfant, 5)
        self.assertEqual(rc, 128 + signal.SIGTERM, "SIGTERM non converti en SystemExit")
        self.assertFalse(survit, f"le sleep {enfant} du doctor a survécu au SIGTERM du bilan")


class ContratTests(_Base):
    def test_contrat_sans_ecrire(self):
        rc, out, err = self.r.jouer("--sans-ecrire")
        self.assertEqual(rc, 0, out + err)
        self.assertFalse((self.r.racine / ".agents" / "state" / "local").exists(),
                         "--sans-ecrire a écrit (ou créé le répertoire du contrat)")

    def test_contrat_atomique_et_rejoue(self):
        self.r.poser(demon={"status": "absent"})
        rc, out, err = self.r.jouer()
        self.assertEqual(rc, 1, out + err)
        premier = json.loads(self.r.contrat.read_text(encoding="utf-8"))
        self.assertEqual(premier["rc"], 1)
        inode = self.r.contrat.stat().st_ino
        rc, out, err = self.r.jouer()
        second = json.loads(self.r.contrat.read_text(encoding="utf-8"))
        self.assertGreater(datetime.fromisoformat(second["genere_le"]),
                           datetime.fromisoformat(premier["genere_le"]))
        self.assertNotEqual(self.r.contrat.stat().st_ino, inode,
                            "contrat réécrit en place : ni fichier temporaire ni os.replace")
        self.assertEqual(sorted(p.name for p in self.r.contrat.parent.iterdir()),
                         ["setup-bilan.json"], "un fichier temporaire est resté")

    def test_contrat_jamais_par_un_lien(self):
        """`.agents/state/local` ou un parent sous la racine en lien symbolique :
        contrat non écrit, dit sur stderr, rien d'écrit au bout du lien."""
        # `.agents` EN DERNIER : il est recréé vide, aucun cas ne le relit ensuite.
        for lien in (Path(".agents") / "state" / "local", Path(".agents") / "state",
                     Path(".agents")):
            with self.subTest(lien=str(lien)):
                ailleurs = Path(tempfile.mkdtemp(prefix="bilan-ailleurs-")).resolve()
                self.addCleanup(shutil.rmtree, ailleurs, True)
                chemin = self.r.racine / lien
                if chemin.is_symlink():
                    chemin.unlink()
                elif chemin.exists():
                    shutil.rmtree(chemin)
                chemin.symlink_to(ailleurs, target_is_directory=True)
                rc, out, err = self.r.jouer()
                self.assertEqual(f"exit {rc}", out.strip().splitlines()[-1][-6:], out + err)
                self.assertIn("bilan: contrat non écrit", err)
                self.assertIn("lien symbolique", err)
                self.assertNotIn("Traceback", err)
                self.assertEqual(sorted(p.name for p in ailleurs.iterdir()), [],
                                 "écrit à travers le lien")
                chemin.unlink()
                chemin.mkdir(parents=True, exist_ok=True)

    def test_variables_de_banc_dites(self):
        rc, out, err = self.r.jouer("--sans-ecrire")
        jambes, _ = _lire(out)
        for nom in ("outils", "scanners"):
            self.assertIn("BILAN_DOCTOR posé (banc)", jambes[nom][1])
        for nom in ("outils", "scanners", "interpréteur", "dashboard"):
            with self.subTest(jambe=nom):
                self.assertIn("BILAN_PROBE_PATH posé (banc)", jambes[nom][1])
        for nom in ("version", "hooks", "portes"):
            self.assertNotIn("posé (banc)", jambes[nom][1])
        self.r.env["BILAN_KIT_REMOTE"] = str(self.tmp / "nulle-part")
        jambes, _ = _lire(self.r.jouer("--sans-ecrire")[1])
        self.assertIn("BILAN_KIT_REMOTE posé (banc)", jambes["version"][1])

    def test_bilan_doctor_vide_honore(self):
        """`BILAN_DOCTOR=""` est POSÉE : la jambe l'honore (doctor vide, illisible) et le dit,
        jamais le doctor réel sous l'étiquette « banc »."""
        self.r.env["BILAN_DOCTOR"] = ""
        reel = self.r.racine / "core-scripts" / "doctor.sh"
        reel.parent.mkdir()
        reel.write_text(_DOCTOR_BOUCHON, encoding="utf-8")
        (e, detail, remede), _, sortie = self.jambe("outils")
        self.assertEqual(e, "KO", sortie)
        self.assertIn("doctor illisible", detail)
        self.assertIn("BILAN_DOCTOR posé (banc)", detail)
        self.assertNotIn(str(reel), detail, "variable posée vide ignorée : doctor réel lu")

    def test_contrat_non_ecrit_dit(self):
        local = self.r.racine / ".agents" / "state" / "local"
        local.write_text("un fichier, pas un répertoire", encoding="utf-8")
        rc, out, err = self.r.jouer()
        self.assertEqual(rc, 0, out + err)
        self.assertIn("bilan: contrat non écrit", err)
        self.assertNotIn("Traceback", err)
        self.assertEqual(out.strip().splitlines()[-1], "bilan: OK=6 KO=0 SANS OBJET=1 — exit 0")

    def test_usage_rc_2(self):
        for args, morceau in ((("--root", str(self.tmp / "absente")), "REFUS"),
                              (("--delai", "0"), "REFUS"), (("--inconnu",), "usage")):
            with self.subTest(args=args):
                p = subprocess.run([sys.executable, str(BILAN), *args], cwd=str(self.tmp),
                                   env=self.r.env, capture_output=True, text=True, timeout=60,
                                   stdin=subprocess.DEVNULL, check=False)
                self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
                self.assertIn(morceau, p.stderr)
                self.assertEqual(_lire(p.stdout), ({}, None), "aucune jambe sous un refus d'usage")


def _module_bilan():
    spec = importlib.util.spec_from_file_location("_banc_setup_bilan_jambes", BILAN)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # nom privé, chargé par chemin : sys.path intact
    spec.loader.exec_module(module)
    return module


class VersionTests(_Base):
    """La jambe version : dépôt du kit LOCAL ou `git` journaliste — jamais le réseau."""

    def _journaliste(self) -> Path:
        dossier = self.tmp / "git-journaliste"
        dossier.mkdir(exist_ok=True)
        (dossier / "git").write_text(_GIT_JOURNALISTE.replace("@GIT@", GIT), encoding="utf-8")
        (dossier / "git").chmod(0o755)
        self.r.env["PATH"] = f"{dossier}:{self.r.env.get('PATH', '/usr/bin:/bin')}"
        return dossier

    def test_tri_numerique_et_remede(self):
        """Mutants : tri lexical (dev9 > dev11), clé dev/publiée inversée, remède ancien -> rouge."""
        cas = (("0.1.0.dev11", ("0.1.0.dev9", "0.1.0.dev11", "0.1.0.dev12"), "KO", "0.1.0.dev12"),
               ("0.1.0.dev11", ("0.1.0.dev9", "0.1.0.dev11"), "OK", "0.1.0.dev11"),
               ("0.1.0.dev11", ("0.1.0",), "KO", "0.1.0"),
               ("0.1.0", ("0.1.0.dev12", "0.1.0.dev9"), "OK", "0.1.0.dev12"),
               ("0.2.0", ("0.10.0",), "KO", "0.10.0"))
        for locale, tags, etat, derniere in cas:
            with self.subTest(locale=locale, tags=tags):
                _changelog(self.r, f"## {locale} — 2026-10-25")
                self.r.env["BILAN_KIT_REMOTE"] = str(_depot_kit(self.r, *tags))
                (e, detail, remede), rc, sortie = self.jambe("version")
                self.assertEqual(e, etat, sortie)
                self.assertIn(f"copie {locale}", detail)
                self.assertIn(f"publiée {derniere} (", detail)
                self.assertEqual(remede, REMEDE_VERSION if etat == "KO" else None)
                self.assertEqual(rc == 1, etat == "KO")
        self.r.env["BILAN_KIT_REMOTE"] = str(self.tmp / "nulle-part")
        (e, detail, remede), _, sortie = self.jambe("version")
        self.assertEqual((e, remede), ("SANS OBJET", None), sortie)
        self.assertIn("dépôt du kit injoignable", detail)
        self.assertIn("does not appear to be a git repository", detail, "la cause (1re `fatal:`) "
                      "n'est pas dite")

    def test_git_jamais_lance(self):
        """Kit, tête non versionnée, CHANGELOG absent, valeur en `-` : SANS OBJET, AUCUN
        `ls-remote`. Mutants : marqueur ignoré, 1re tête sautée, refus du `-` retiré -> rouge."""
        dossier = self._journaliste()
        marqueur = self.r.racine / ".agents" / "IS_THE_KIT"
        cas = (("marqueur du kit", "## 0.1.0.dev11 — 2026-10-25", True, None, "kit (.agents/IS_THE_KIT)"),
               ("tête non publiée", "## Non publié\n\n## 0.1.0.dev11 — 2026-10-25", False, None,
                "« ## Non publié » sans version"),
               ("CHANGELOG absent", None, False, None, "CHANGELOG.md absent"),
               ("valeur en -", "## 0.1.0.dev11 — 2026-10-25", False, "-x",
                "BILAN_KIT_REMOTE refusé (commence par « - ») : git non lancé"))
        for nom, tete, kit, distant, morceau in cas:
            with self.subTest(cas=nom):
                (self.r.racine / "CHANGELOG.md").unlink(missing_ok=True)
                if tete is not None:
                    _changelog(self.r, tete)
                if kit:
                    marqueur.write_text("kit\n", encoding="utf-8")
                elif marqueur.exists():
                    marqueur.unlink()
                self.r.env.pop("BILAN_KIT_REMOTE", None)
                if distant is not None:
                    self.r.env["BILAN_KIT_REMOTE"] = distant
                (e, detail, remede), _, sortie = self.jambe("version")
                self.assertEqual((e, remede), ("SANS OBJET", None), sortie)
                self.assertIn(morceau, detail)
                self.assertFalse((dossier / "ls-remote.log").exists(),
                                 "git ls-remote lancé : " + nom)

    def test_appel_par_defaut_sans_reseau(self):
        """Sans BILAN_KIT_REMOTE, l'URL de distribution, après `--` : l'assistant d'identifiants
        du poste répond (AUCUN `-c credential.helper=`, dépôt privé), jamais une invite
        (GIT_TERMINAL_PROMPT=0, GIT_ASKPASS et SSH_ASKPASS vides, GCM_INTERACTIVE=never). Le
        `git` journaliste refuse (rc 2), la jambe dit SANS OBJET. Aucun octet sur le réseau.
        Mutants : `-c credential.helper=` partout, GCM_INTERACTIVE ou GIT_TERMINAL_PROMPT
        retiré -> rouge."""
        dossier = self._journaliste()
        _changelog(self.r, "## 0.1.0.dev11 — 2026-10-25")
        self.r.env["GCM_INTERACTIVE"] = "always"  # celui du poste est écrasé, jamais hérité
        (e, detail, remede), _, sortie = self.jambe("version")
        self.assertEqual((e, remede), ("SANS OBJET", None), sortie)
        self.assertIn("git ls-remote rc 2", detail)
        journal = (dossier / "ls-remote.log").read_text(encoding="utf-8").splitlines()
        self.assertEqual(journal, [f"ls-remote --tags --refs -- {URL_KIT} "
                                   "refs/tags/template/v*|0|||never|absent"])
        self.assertNotIn("credential.helper", journal[0])

    def test_appel_de_banc_sans_assistant(self):
        """Sous BILAN_KIT_REMOTE (banc, URL tierce) : `-c credential.helper=`, aucun identifiant
        du poste présenté ; URL ssh : `ssh -o BatchMode=yes`. Mutants : `-c` retiré sous le banc,
        BatchMode retiré -> rouge."""
        dossier = self._journaliste()
        _changelog(self.r, "## 0.1.0.dev11 — 2026-10-25")
        for distant, ssh in ((str(self.tmp / "nulle-part"), "absent"),
                             ("git@kit.invalid:kit.git", "ssh -o BatchMode=yes"),
                             ("ssh://kit.invalid/kit.git", "ssh -o BatchMode=yes"),
                             ("https://kit.invalid/kit.git", "absent")):
            with self.subTest(distant=distant):
                (dossier / "ls-remote.log").unlink(missing_ok=True)
                self.r.env["BILAN_KIT_REMOTE"] = distant
                (e, _, remede), _, sortie = self.jambe("version")
                self.assertEqual((e, remede), ("SANS OBJET", None), sortie)
                journal = (dossier / "ls-remote.log").read_text(encoding="utf-8").splitlines()
                self.assertEqual(journal, [f"-c credential.helper= ls-remote --tags --refs -- "
                                           f"{distant} refs/tags/template/v*|0|||never|{ssh}"])

    def test_depot_prive_sans_identifiants(self):
        """git sans identifiant (« could not read Username|Password », invite interdite) : SANS
        OBJET qui dit le dépôt privé et la version non comparée. Mutant : branche retirée ->
        « injoignable » -> rouge."""
        dossier = self._journaliste()
        _changelog(self.r, "## 0.1.0.dev11 — 2026-10-25")
        for quoi in ("Username", "Password"):
            with self.subTest(quoi=quoi):
                (dossier / "ls-remote.err").write_text(
                    f"fatal: could not read {quoi} for 'https://gitlab.groupeonepoint.com': "
                    "terminal prompts disabled\n", encoding="utf-8")
                (e, detail, remede), rc, sortie = self.jambe("version")
                self.assertEqual((e, remede), ("SANS OBJET", None), sortie)
                self.assertIn("copie 0.1.0.dev11 ; dépôt du kit privé : identifiants du poste "
                              "absents, version non comparée (", detail)
                self.assertIn(f"rc 128 : fatal: could not read {quoi}", detail)
                self.assertNotIn("injoignable", detail)

    def test_userinfo_dans_l_erreur_de_git(self):
        """L'URL que git CITE dans son erreur perd son userinfo, `@` du mot de passe compris :
        ni sur stdout, ni au contrat. Mutant : `_ligne_utile` sans `_USERINFO_DANS` -> rouge."""
        dossier = self._journaliste()
        _changelog(self.r, "## 0.1.0.dev11 — 2026-10-25")
        self.r.env["BILAN_KIT_REMOTE"] = "https://kit.invalid/kit.git"
        (dossier / "ls-remote.err").write_text(
            "fatal: unable to access 'https://lecteur:MDP@SENTINELLE@kit.invalid/kit.git/': "
            "The requested URL returned error: 401\n", encoding="utf-8")
        rc, out, err = self.r.jouer()
        jambes, _ = _lire(out)
        self.assertEqual(jambes["version"][0], "SANS OBJET", out + err)
        self.assertIn("fatal: unable to access 'https://kit.invalid/kit.git/': The requested URL "
                      "returned error: 401", jambes["version"][1])
        contrat = self.r.contrat.read_text(encoding="utf-8")
        for secret in ("SENTINELLE", "lecteur", "MDP"):
            self.assertNotIn(secret, out + err)
            self.assertNotIn(secret, contrat)

    def test_changelog_avec_bom(self):
        """Un CHANGELOG.md à BOM UTF-8 (éditeur Windows) reste le journal du kit : comparé.
        Mutant : lu en `utf-8` -> titre « \\ufeff# Journal… » -> SANS OBJET -> rouge."""
        (self.r.racine / "CHANGELOG.md").write_text(
            f"﻿{TITRE_KIT}\n\n## 0.1.0.dev11 — 2026-10-25\n", encoding="utf-8")
        self.r.env["BILAN_KIT_REMOTE"] = str(_depot_kit(self.r, "0.1.0.dev11"))
        (e, detail, remede), _, sortie = self.jambe("version")
        self.assertEqual((e, remede), ("OK", None), sortie)
        self.assertIn("copie 0.1.0.dev11, dernière publiée 0.1.0.dev11 (", detail)

    def test_changelog_de_l_adoptant(self):
        """Le CHANGELOG PROPRE de l'adoptant (fusionné, jamais écrasé) : SANS OBJET, git non lancé.
        Mutant : contrôle du titre retiré -> `## 0.0.1` en KO perpétuel, `## 2.3.0` en faux OK."""
        dossier = self._journaliste()
        for titre, tete in (("# Mon projet — journal", "## 0.0.1 — 2026-01-01"),
                            ("# Mon projet — journal", "## 2.3.0 — 2026-05-01"),
                            ("# Journal des versions — kit Cadre", "## 0.1.0.dev11 — 2026-10-25"),
                            ("## 0.1.0.dev11 — 2026-10-25", "## 0.1.0.dev11 — 2026-10-25")):
            with self.subTest(titre=titre, tete=tete):
                _changelog(self.r, tete, titre=titre)
                (e, detail, remede), _, sortie = self.jambe("version")
                self.assertEqual((e, remede), ("SANS OBJET", None), sortie)
                self.assertIn("CHANGELOG.md n'est pas le journal du kit", detail)
                self.assertFalse((dossier / "ls-remote.log").exists(), "git ls-remote lancé")
        _changelog(self.r, "## 0.1.0.dev11 — 2026-10-25")  # non-vacuité : le titre du kit lance git
        self.jambe("version")
        self.assertTrue((dossier / "ls-remote.log").exists(), "le titre du kit ne lance pas git")

    def test_titre_epingle_au_journal_livre(self):
        """`TITRE_JOURNAL_KIT` == la 1re ligne du journal que le kit livre aux adoptants."""
        livre = ROOT / ".agents" / "adopter-docs" / "CHANGELOG.md"
        if not livre.is_file():
            self.skipTest("SAUT ANNONCÉ — .agents/adopter-docs/ absent (adoptant) : témoin du kit")
        premiere = livre.read_text(encoding="utf-8").splitlines()[0]
        self.assertEqual(_module_bilan().TITRE_JOURNAL_KIT, premiere)
        self.assertEqual(TITRE_KIT, premiere, "le banc écrit un autre titre que le journal livré")

    def test_injoignable_dit_la_cause(self):
        """La 1re ligne `fatal:` de git, jamais sa dernière (« and the repository exists. »)."""
        dossier = self._journaliste()
        (dossier / "ls-remote.err").write_text(
            "fatal: Could not read from remote repository.\n\nPlease make sure you have the correct "
            "access rights\nand the repository exists.\n", encoding="utf-8")
        _changelog(self.r, "## 0.1.0.dev11 — 2026-10-25")
        (e, detail, _), _, sortie = self.jambe("version")
        self.assertEqual(e, "SANS OBJET", sortie)
        self.assertIn("rc 128 : fatal: Could not read from remote repository.", detail)
        self.assertNotIn("and the repository exists", detail)

    def test_userinfo_jamais_dite(self):
        """`user:mot de passe@` d'une BILAN_KIT_REMOTE : ni sur stdout, ni au contrat, `@` du
        mot de passe compris. Mutant : `_USERINFO` arrêtée au 1er `@` -> « SENTINELLE@… »
        affiché -> rouge."""
        self._journaliste()
        _changelog(self.r, "## 0.1.0.dev11 — 2026-10-25")
        for distant in ("https://lecteur:MDP-SENTINELLE@kit.invalid/kit.git",
                        "https://lecteur:MDP@SENTINELLE@kit.invalid/kit.git"):
            with self.subTest(distant=distant):
                self.r.env["BILAN_KIT_REMOTE"] = distant
                rc, out, err = self.r.jouer()
                jambes, _ = _lire(out)
                self.assertEqual(jambes["version"][0], "SANS OBJET", out + err)
                self.assertIn("(https://kit.invalid/kit.git, git ls-remote rc 2",
                              jambes["version"][1])
                contrat = self.r.contrat.read_text(encoding="utf-8")
                for secret in ("SENTINELLE", "lecteur", "MDP"):
                    self.assertNotIn(secret, out + err)
                    self.assertNotIn(secret, contrat)

    def test_nombres_bornes(self):
        """Un nombre de 5000 chiffres (tête ou tag) n'est jamais converti : aucun Traceback.
        Mutant : bornes `{1,9}` retirées -> `int()` lève (> 4300 chiffres) -> rouge."""
        dossier = self._journaliste()
        geant = "9" * 5000
        _changelog(self.r, f"## {geant}.0.0 — 2026-10-25")
        rc, out, err = self.r.jouer("--sans-ecrire")
        self.assertNotIn("Traceback", err)
        self.assertEqual(_lire(out)[0]["version"][0], "SANS OBJET", out + err)
        self.assertFalse((dossier / "ls-remote.log").exists())
        (dossier / "ls-remote.sortie").write_text(
            f"a\trefs/tags/template/v{geant}.0.0-2026-10-01\n"
            "b\trefs/tags/template/v0.1.0.dev12-2026-10-01\n", encoding="utf-8")
        _changelog(self.r, "## 0.1.0.dev11 — 2026-10-25")
        rc, out, err = self.r.jouer("--sans-ecrire")
        self.assertNotIn("Traceback", err)
        etat, detail, remede = _lire(out)[0]["version"]
        self.assertEqual((etat, remede), ("KO", REMEDE_VERSION), out + err)
        self.assertIn("dernière publiée 0.1.0.dev12 (", detail)

    def test_borne_15_s(self):
        """Un dépôt qui ne répond pas : 15 s au plus, groupe tué. Mutant : borne retirée -> le
        délai global (120 s) joue et le témoin rougit sur la durée et le texte."""
        dossier = self._journaliste()
        (dossier / "ls-remote.dort").write_text("", encoding="utf-8")
        _changelog(self.r, "## 0.1.0.dev11 — 2026-10-25")
        debut = time.monotonic()
        (e, detail, remede), _, sortie = self.jambe("version")
        duree = time.monotonic() - debut
        self.assertEqual((e, remede), ("SANS OBJET", None), sortie)
        self.assertIn("délai dépassé (15 s)", detail)
        self.assertLess(duree, 40, "borne 15 s non tenue")
        enfant = int((dossier / "ls-remote.pid").read_text().strip())
        self.assertFalse(_survit(enfant, 5), "le git ls-remote a survécu à la borne")


class ScannersTests(_Base):
    """La jambe scanners, sur la MÊME sortie du doctor bouchon que la jambe outils."""

    def scanners(self, **doctor):
        self.r.poser(doctor=_doctor(**doctor))
        return self.jambe("scanners")

    def test_defaut_ok(self):
        (e, detail, remede), _, sortie = self.scanners()
        self.assertEqual((e, remede), ("OK", None), sortie)
        for morceau in ("gitleaks PRESENT", "semgrep version non lue", "modules : aucun",
                        "NVD_API_KEY absente (non exigée : ni java ni swift)", "plateforme darwin",
                        str(self.r.bouchons / "doctor.sh")):
            self.assertIn(morceau, detail)

    def test_doctor_joue_une_fois(self):
        """`outils` et `scanners` lisent la MÊME sortie. Mutant : doctor rejoué -> 2 appels."""
        rc, out, err = self.r.jouer("--sans-ecrire")
        self.assertEqual(rc, 0, out + err)
        appels = (self.r.bouchons / "doctor.appels").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(appels), 1, out)

    def test_remede_par_plateforme(self):
        """C11, C15 : le remède ferme le KO — darwin hors du kit setup.sh, darwin DANS le kit la
        commande brew de l'outil (setup.sh n'y planifie aucun scanner), ailleurs la commande propre.
        Mutants : remède générique, setup.sh dans le kit, paquet brew faux -> rouge."""
        sans_pip_audit = {"modules": "python", "classe_a": _absent("pip-audit")}
        sans_npm = {"modules": "npm", "classe_a": _absent("npm")}
        sans_gitleaks = {"scanners": "  PRESENT                  semgrep — /x/semgrep\n"
                                     + _absent("gitleaks")}
        tout_absent = {"modules": "python,npm,java,swift,iac",
                       "scanners": "".join(_absent(o) for o in ("gitleaks", "semgrep", "pip-audit",
                                                                "npm", "dependency-check"))}
        cas = (
            ("linux pip-audit", "linux", False, sans_pip_audit, "pip-audit ABSENT",
             "pipx install pip-audit"),
            ("darwin pip-audit", "darwin", False, sans_pip_audit, "pip-audit ABSENT", REMEDE_SETUP),
            ("kit darwin pip-audit", "darwin", True, sans_pip_audit, "pip-audit ABSENT",
             "brew install -- pip-audit"),
            ("linux npm", "linux", False, sans_npm, "npm ABSENT", "sudo apt-get install npm"),
            ("kit darwin npm", "darwin", True, sans_npm, "npm ABSENT", "brew install -- node"),
            ("windows gitleaks", "windows", False, sans_gitleaks, "gitleaks ABSENT",
             "winget install gitleaks"),
            ("linux gitleaks", "linux", False, sans_gitleaks, "gitleaks ABSENT",
             "README-SECURITY-SCAN-SETUP.md § Secrets scan (gitleaks)"),
            ("linux trivy non sondé", "linux", False, {"modules": "iac"},
             "trivy NON SONDÉ par le doctor",
             "README-SECURITY-SCAN-SETUP.md § IaC misconfiguration scan (trivy)"),
            ("darwin six absents", "darwin", False, tout_absent, "trivy NON SONDÉ",
             REMEDE_SETUP + " ; README-SECURITY-SCAN-SETUP.md § The NVD API key"),
            ("kit darwin six absents", "darwin", True, tout_absent, "dependency-check ABSENT",
             "brew install -- gitleaks ; brew install -- semgrep ; brew install -- pip-audit ; "
             "brew install -- node ; brew install -- dependency-check ; brew install -- trivy ; "
             "README-SECURITY-SCAN-SETUP.md § The NVD API key"),
        )
        marqueur = self.r.racine / ".agents" / "IS_THE_KIT"
        for nom, plateforme, kit, doctor, morceau, attendu in cas:
            with self.subTest(cas=nom):
                if kit:
                    marqueur.write_text("kit\n", encoding="utf-8")
                elif marqueur.exists():
                    marqueur.unlink()
                (e, detail, remede), rc, sortie = self.scanners(plateforme=plateforme, **doctor)
                self.assertEqual((e, rc), ("KO", 1), sortie)
                self.assertIn(morceau, detail)
                self.assertIn(f"plateforme {plateforme}", detail)
                self.assertEqual(remede, attendu)
                if kit:
                    self.assertNotIn("setup.sh", remede, "C15 : setup.sh n'installe aucun scanner "
                                                        "dans le kit")

    def test_modules_illisibles(self):
        """Ligne absente ou `illisible` : KO dit, jamais lue comme « aucun » (fail-closed)."""
        for modules in (None, "illisible"):
            with self.subTest(modules=modules):
                (e, detail, remede), _, sortie = self.scanners(modules=modules)
                self.assertEqual(e, "KO", sortie)
                self.assertIn("modules : illisibles", detail)
                self.assertEqual(remede, "resynchroniser core-scripts/doctor.sh et "
                                         ".agents/security/module_discovery.py (ligne doctor: modules)")

    def test_nvd_jamais_la_valeur(self):
        """NVD_API_KEY posée|absente, JAMAIS sa valeur — ni stdout, ni stderr, ni contrat.
        Mutants : valeur imprimée -> rouge ; clé non exigée sous java -> rouge."""
        sentinelle = "SENTINELLE-NVD-7f3a9c"
        java = {"modules": "java", "classe_a": "  PRESENT                  dependency-check — /x/dc\n"}
        self.r.poser(doctor=_doctor(**java))
        self.r.env["NVD_API_KEY"] = sentinelle
        rc, out, err = self.r.jouer()
        jambes, _ = _lire(out)
        self.assertEqual(jambes["scanners"][0], "OK", out + err)
        self.assertIn("NVD_API_KEY posée", jambes["scanners"][1])
        self.assertNotIn(sentinelle, out + err)
        self.assertNotIn(sentinelle, self.r.contrat.read_text(encoding="utf-8"))
        del self.r.env["NVD_API_KEY"]
        (e, detail, remede), _, sortie = self.scanners(**java)
        self.assertEqual((e, remede), ("KO", "README-SECURITY-SCAN-SETUP.md § The NVD API key"),
                         sortie)
        self.assertIn("NVD_API_KEY absente", detail)

    def test_semgrep_version_et_pin(self):
        """La version du semgrep que le doctor a trouvé, lue SANS la vérification en ligne, et le
        pin CI de tool-inventory.tsv. Mutants : SEMGREP_ENABLE_VERSION_CHECK=0 retiré, pin non lu."""
        semgrep = self.r.bouchons / "semgrep"
        semgrep.write_text('#!/bin/sh\nif [ "$SEMGREP_ENABLE_VERSION_CHECK" = 0 ] && '
                           '[ "$1" = --version ]; then echo 1.182.0; exit 0; fi\n'
                           'echo "verification en ligne" >&2; exit 3\n', encoding="utf-8")
        semgrep.chmod(0o755)
        inventaire = self.r.racine / "core-scripts" / "tool-inventory.tsv"
        inventaire.parent.mkdir()
        inventaire.write_text("# entête\nsemgrep\toutil\tany\tA\t-\t-\t1.175.0@pip-hash(adoptant)"
                              "\t-\t-\t-\tx\t-\t-\t-\n", encoding="utf-8")
        scanners = (f"  PRESENT                  gitleaks — /x/gitleaks\n"
                    f"  PRESENT                  semgrep — {semgrep}\n")
        (e, detail, _), _, sortie = self.scanners(scanners=scanners)
        self.assertEqual(e, "OK", sortie)
        self.assertIn("semgrep 1.182.0 (pin CI 1.175.0)", detail)
        (e, detail, remede), _, sortie = self.scanners(
            plateforme="linux", scanners="  PRESENT                  gitleaks — /x/gitleaks\n"
                                         + _absent("semgrep"))
        self.assertEqual((e, remede), ("KO", "pipx install semgrep==1.175.0"), sortie)


    def test_semgrep_du_projet_jamais_lance(self):
        """Un `semgrep` DANS l'arbre du projet n'est jamais exécuté. Mutant : contrôle retiré ->
        le bouchon tourne (marqueur écrit) -> rouge."""
        semgrep = self.r.racine / "outils" / "semgrep"
        semgrep.parent.mkdir()
        semgrep.write_text(f'#!/bin/sh\necho lance > "{self.tmp}/semgrep-lance"\necho 1.0.0\n',
                           encoding="utf-8")
        semgrep.chmod(0o755)
        (e, detail, _), _, sortie = self.scanners(
            scanners=f"  PRESENT                  gitleaks — /x/gitleaks\n"
                     f"  PRESENT                  semgrep — {semgrep}\n")
        self.assertEqual(e, "OK", sortie)
        self.assertIn("dans l'arbre du projet : non exécuté", detail)
        self.assertFalse((self.tmp / "semgrep-lance").exists(), "le semgrep du projet a tourné")

    def test_detail_sans_controles(self):
        """Un état du doctor porteur d'une séquence de contrôle est neutralisé (`\\u001b`)."""
        (e, detail, _), _, sortie = self.scanners(
            scanners="  PRESENT\x1b[31m                gitleaks — /x/gitleaks\n"
                     "  PRESENT                  semgrep — /x/semgrep\n")
        self.assertNotIn("\x1b", sortie)
        self.assertIn("gitleaks PRESENT\\u001b[31m", detail)


class PariteSetupShTests(unittest.TestCase):
    """C17 : UN témoin lit les DEUX tables — `SP_SCANNERS_DARWIN='…'` de core-scripts/setup.sh
    (lecture seule) et les paquets que le remède darwin du bilan dit installés par setup.sh.
    Ligne absente : ROUGE (jamais un saut) — le lot A la pose, il est fusionné avant ce banc."""

    def test_sp_scanners_darwin_egal_au_remede(self):
        setup = ROOT / "core-scripts" / "setup.sh"
        lignes = [ligne for ligne in setup.read_text(encoding="utf-8").splitlines()
                  if ligne.startswith("SP_SCANNERS_DARWIN=")]
        self.assertEqual(len(lignes), 1, f"{setup} : ligne SP_SCANNERS_DARWIN='…' en colonne 0 "
                         f"absente ou doublée ({len(lignes)}) — lot A (T-01M5VYNMZPG8G0JZG48HV4K0PN) "
                         "non fusionné ? La parité des deux tables darwin n'est PAS prouvée.")
        m = re.fullmatch(r"SP_SCANNERS_DARWIN='([a-z0-9 -]+)'", lignes[0])
        self.assertIsNotNone(m, lignes[0])
        noms = m.group(1).split()
        self.assertEqual(len(noms), len(set(noms)), "nom doublé dans SP_SCANNERS_DARWIN")
        bilan = _module_bilan()
        dits = {bilan.PAQUET_DARWIN[outil] for outil in bilan.PAQUET_DARWIN
                if bilan.remede_scanner(outil, "darwin", False, None) == REMEDE_SETUP}
        self.assertEqual(set(noms), dits, "setup.sh et le remède darwin du bilan désaccordés")
        voulus = {"gitleaks", "semgrep", *bilan._OUTIL_DE_FAMILLE.values()}
        self.assertEqual(voulus, set(bilan.PAQUET_DARWIN), "un scanner voulu sans paquet darwin")


def _python_ancien() -> str | None:
    uv = shutil.which("uv")
    candidats = []
    if uv:
        p = subprocess.run([uv, "python", "find", "3.9"], capture_output=True, text=True,
                           timeout=60, stdin=subprocess.DEVNULL, check=False,
                           cwd=tempfile.gettempdir())
        if p.returncode == 0 and p.stdout.strip():
            candidats.append(p.stdout.strip().splitlines()[-1])
    candidats.append("/usr/bin/python3")
    for candidat in candidats:
        if not Path(candidat).is_file():
            continue
        v = subprocess.run([candidat, "-c", "import sys; print(sys.version_info < (3, 11))"],
                           capture_output=True, text=True, timeout=60, check=False,
                           stdin=subprocess.DEVNULL)
        if v.stdout.strip() == "True":
            return candidat
    return None


PYTHON_ANCIEN = _python_ancien() if POSIX else None


@unittest.skipIf(PYTHON_ANCIEN is None, "SAUT ANNONCÉ — aucun interpréteur < 3.11 réel "
                 "(ni `uv python find 3.9`, ni /usr/bin/python3 < 3.11)")
class SousPython39Tests(_Base):
    """Le bilan DIT un interpréteur trop vieux, il ne plante pas dessus : joué
    SOUS un < 3.11 réel, SANS `--sans-ecrire`, sur les bouchons des sept jambes (la version
    comparée à un dépôt LOCAL : le tri numérique joue sous 3.9 aussi)."""

    def _scenarios(self):
        yield "tout OK", 0
        self.r.poser(version="3.9.6", doctor=_doctor(_B_PRESENT + "  ABSENT (requis)  tee — x\n",
                                                     modules=None),
                     demon={"status": "alive", "code": "stale"})
        (self.r.racine / ".agents" / "state" / "gates" / "BINOME_REQUIRED").unlink()
        self.r.git("config", "core.hooksPath", "")
        _changelog(self.r, "## 0.1.0.dev11 — 2026-10-25")
        self.r.env["BILAN_KIT_REMOTE"] = str(_depot_kit(self.r, "0.1.0.dev9", "0.1.0.dev12"))
        yield "sept KO", 1

    def _jouer_ancien(self, script: Path = BILAN):
        if self.r.contrat.exists():
            self.r.contrat.unlink()
        return self.r.jouer(python=PYTHON_ANCIEN, script=script)

    def test_sous_python_ancien(self):
        for nom, verdict in self._scenarios():
            with self.subTest(scenario=nom):
                rc, out, err = self._jouer_ancien()
                self.assertNotIn("Traceback", err, err)
                lignes = out.strip().splitlines()
                n = len(JAMBES)
                self.assertEqual([_LIGNE.match(x)["jambe"] for x in lignes[:n]], JAMBES, out)
                self.assertRegex(lignes[n], _RESUME)
                self.assertEqual(rc, verdict, out + err)
                self.assertEqual(_lire(out)[1][1], 0 if verdict == 0 else n, out)
                contrat = json.loads(self.r.contrat.read_text(encoding="utf-8"))
                self.assertEqual(contrat["rc"], verdict)
                self.assertTrue(datetime.fromisoformat(contrat["genere_le"]))

    def test_le_temoin_ancien_rougit_sur_310(self):
        """Non-vacuité : `datetime.UTC` et `zip(strict=True)` dans une copie du
        bilan font planter le < 3.11 réel — le témoin ci-dessus les verrait."""
        source = BILAN.read_text(encoding="utf-8")
        for avant, apres in (("datetime.timezone.utc", "datetime.UTC"),
                             ("zip(etats, outils)", "zip(etats, outils, strict=True)")):
            with self.subTest(mutant=apres):
                self.assertEqual(source.count(avant), 1, avant)
                copie = self.tmp / "mutant_setup_bilan.py"
                copie.write_text(source.replace(avant, apres), encoding="utf-8")
                rc, out, err = self._jouer_ancien(copie)
                self.assertIn("Traceback", err, f"le mutant {apres} n'a pas planté sous "
                              f"{PYTHON_ANCIEN}")
                self.assertFalse(self.r.contrat.exists() and rc == 0)


class DefautsReelsTests(unittest.TestCase):
    """Sans `--root`, lancé d'un autre répertoire : la racine est l'arbre qui
    porte le bilan. `--sans-ecrire` : rien n'est écrit sous la racine réelle."""

    def test_defauts_reels(self):
        tmp = Path(tempfile.mkdtemp(prefix="setup-bilan-reel-")).resolve()
        self.addCleanup(shutil.rmtree, tmp, True)
        env = {k: v for k, v in os.environ.items() if not k.startswith(("BILAN_", "GIT_CONFIG"))}
        env.update({"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.hooksPath",
                    "GIT_CONFIG_VALUE_0": ".githooks", "PYTHONDONTWRITEBYTECODE": "1"})
        p = subprocess.run([sys.executable, str(BILAN), "--sans-ecrire"], cwd=str(tmp), env=env,
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=600, stdin=subprocess.DEVNULL, check=False)
        jambes, resume = _lire(p.stdout)
        self.assertEqual(list(jambes), JAMBES, p.stdout + p.stderr)
        self.assertIsNotNone(resume)
        etat, detail, _ = jambes["outils"]
        self.assertIn(str(ROOT / "core-scripts" / "doctor.sh"), detail, "le doctor du kit est lu")
        self.assertNotIn("doctor illisible", detail)
        self.assertRegex(detail, r"doctor: \d+/\d+ présents" if etat == "OK" else r"Classe B : ")
        self.assertRegex(jambes["interpréteur"][1], r"^Python \d+\.\d+\.\d+ : \S")
        etat, detail, _ = jambes["hooks"]
        self.assertEqual(etat, "OK", detail)
        self.assertRegex(detail, r"^\.claude/settings\.json : [1-9]\d* chemin\(s\) cité\(s\)")


class TemoinAstTests(unittest.TestCase):
    """Imports en liste FERMÉE, un seul site subprocess, aucune construction ≥ 3.10
    visible à l'AST (joué partout, CI comprise)."""

    IMPORTS = {"__future__", "argparse", "datetime", "json", "os", "re", "shutil", "signal",
               "subprocess", "sys", "tempfile", "time", "pathlib"}

    def test_imports_et_constructions(self):
        arbre = ast.parse(BILAN.read_text(encoding="utf-8"))
        imports = set()
        for n in ast.walk(arbre):
            if isinstance(n, ast.Import):
                imports |= {a.name for a in n.names}
            elif isinstance(n, ast.ImportFrom):
                imports.add(n.module or "")
        self.assertEqual(imports - self.IMPORTS, set(), "import hors liste fermée")
        self.assertIn("datetime", imports, "le témoin passerait à vide")
        sites = [n for n in ast.walk(arbre) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name)
                 and n.func.value.id == "subprocess"]
        self.assertEqual(len(sites), 1, "un seul site subprocess, celui de `_executer`")
        interdits = [n for n in ast.walk(arbre)
                     if (isinstance(n, ast.Attribute) and n.attr == "UTC")
                     or (isinstance(n, ast.keyword) and n.arg in ("strict", "slots", "kw_only"))
                     or type(n).__name__ in ("Match", "TryStar")]
        self.assertEqual(interdits, [], "construction qui exige Python ≥ 3.10")


if __name__ == "__main__":
    unittest.main()
