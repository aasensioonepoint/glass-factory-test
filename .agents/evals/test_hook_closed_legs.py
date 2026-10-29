"""W-C — JAMBES CLAUDE QUI ÉCHOUENT FERMÉES (T-01M5CH9GATN4G2SP1VKCVR1HC3, T-01M4JRFRSMSA57ZT7D099G9F3H).

ORIGINE. Ce bloc vivait en fin de `test_hook_env_hardening.py` (W-C, W-C4, W-C5) ; il en est sorti
tel quel quand ce fichier a passé le plafond de `test_python_file_length.py`. Les aides du filet 801
(`jambes_hooks`, `_muter`, `_jambe`, `_sb`, `choix_reglages`, `ROOT`, `SKILL`) sont IMPORTÉES de
`test_hook_env_hardening`, jamais recopiées ; seule la fixture `reglages` est redéclarée ici, à
l'identique, pour que ce module se joue seul.

CE QUE CE FILET TIENT. wc1 : les HUIT jambes PreToolUse de `.claude/settings.json` sous
`garde-fermee.sh` (forme, hôte, échéance entière, timeout), leurs contrôles négatifs nommés. wc2 :
chaque jambe ENREGISTRÉE, jouée sous /bin/sh, refuse le plantage de sa garde (rc 2) et transmet à
l'octet un passage. wc3 : une garde sourde à TERM est refusée avant la clé timeout. wc4 : un
gitleaks lent est refusé, avec et sans timeout(1). wc5 : la ligne deny Edit du lanceur, la borne
Bash écrite au SKILL et épinglée par son comportement.
"""
from __future__ import annotations

import os

import pytest

if os.name == "nt":
    pytest.skip("filet POSIX : jambes jouées sous /bin/sh (dette CI Windows T-00000744)",
                allow_module_level=True)

import json  # noqa: E402
import re  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
import warnings  # noqa: E402
from pathlib import Path  # noqa: E402

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_hook_env_hardening as H  # noqa: E402 — aides du filet 801 : importées, jamais recopiées

ROOT = H.ROOT
SKILL = H.SKILL
jambes_hooks = H.jambes_hooks
_muter = H._muter
_jambe = H._jambe
_sb = H._sb


@pytest.fixture(scope="session")
def reglages():
    chemin, v = H.choix_reglages(os.environ)
    if os.environ.get("HOOK_HARDENING_SETTINGS"):
        warnings.warn(f"HOOK_HARDENING_SETTINGS actif : {chemin}")
    if v:
        pytest.fail("; ".join(v))
    return chemin, json.loads(chemin.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# W-C — JAMBES CLAUDE QUI ÉCHOUENT FERMÉES (T-01M5CH9GATN4G2SP1VKCVR1HC3)
# ---------------------------------------------------------------------------
LANCEUR_FERME = '"$CLAUDE_PROJECT_DIR/.agents/security/garde-fermee.sh"'
#: Les HUIT jambes PreToolUse enveloppées : nom -> (repère, cible EXACTE après l'échéance).
#: T-01M4JRFRSMSA57ZT7D099G9F3H (S-01M5SZJEYP, S-01M5WG8ZJT) y ajoute protect-paths, safe-bash,
#: bancs-mandat, la jambe Bash de context-retro et gitleaks `--content` ; aucune jambe PreToolUse
#: de garde ne reste NUE par décision (l'ancien JAMBES_NUES est vidé : une boucle sur un dict vide
#: serait vraie à vide, elle est retirée). PostToolUse et Stop restent nus : le compte du registre
#: ci-dessous les tient (une jambe Stop enveloppée ferait 9).
JAMBES_FERMEES = {
    "kickoff_guard": ('kickoff_guard.py"', '"$CLAUDE_PROJECT_DIR/.agents/pyrun.sh" '
                      '"$CLAUDE_PROJECT_DIR/.agents/bin/kickoff_guard.py"'),
    "audit-gate": ('audit-gate.sh"', '"$CLAUDE_PROJECT_DIR/.claude/hooks/audit-gate.sh"'),
    "iac_guard": ('iac_guard.py"', '"$CLAUDE_PROJECT_DIR/.agents/pyrun.sh" '
                  '"$CLAUDE_PROJECT_DIR/.codex/hooks/iac_guard.py"'),
    "protect-paths": ('protect-paths.sh"', '"$CLAUDE_PROJECT_DIR/.claude/hooks/protect-paths.sh"'),
    "safe-bash": ('safe-bash.sh"', '"$CLAUDE_PROJECT_DIR/.claude/hooks/safe-bash.sh"'),
    "bancs-mandat": ('bancs-mandat.sh"', '"$CLAUDE_PROJECT_DIR/.claude/hooks/bancs-mandat.sh"'),
    "context-retro": ('context-retro.sh"', '"$CLAUDE_PROJECT_DIR/.claude/hooks/context-retro.sh"'),
    "gitleaks": ('gitleaks-scan.sh" --content', '"$CLAUDE_PROJECT_DIR/.agents/security/gitleaks-scan.sh" --content'),
}
GARDES_FACTICES = {"kickoff_guard": ".agents/bin/kickoff_guard.py",
                   "audit-gate": ".claude/hooks/audit-gate.sh", "iac_guard": ".codex/hooks/iac_guard.py",
                   "protect-paths": ".claude/hooks/protect-paths.sh", "safe-bash": ".claude/hooks/safe-bash.sh",
                   "bancs-mandat": ".claude/hooks/bancs-mandat.sh",
                   "context-retro": ".claude/hooks/context-retro.sh",
                   "gitleaks": ".agents/security/gitleaks-scan.sh"}
_SH = ("protect-paths", "safe-bash", "bancs-mandat", "context-retro", "gitleaks")
PLANTAGES = {"kickoff_guard": "raise SystemExit(1)\n", "audit-gate": "exit 1\n", "iac_guard": "1 / 0\n",
             **{n: "exit 1\n" for n in _SH}}
PASSAGES = {"kickoff_guard": "import sys\nsys.stdout.write(sys.stdin.read())\n",
            "audit-gate": "exec cat\n", "iac_guard": "import sys\nsys.stdout.write(sys.stdin.read())\n",
            **{n: "exec cat\n" for n in _SH}}
CHARGE_WC = json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}}) + "\n"


def violations_fermees(doc) -> list[str]:
    """Chaque message COMMENCE par le nom de la jambe fautive."""
    v: list[str] = []
    pre = [h for ev, h in jambes_hooks(doc) if ev == "PreToolUse"]
    for nom, (repere, cible) in JAMBES_FERMEES.items():
        jambes = [h for h in pre if repere in h.get("command", "")]
        if len(jambes) != 1:
            v.append(f"{nom} : {len(jambes)} jambe(s) PreToolUse, 1 attendue")
            continue
        h = jambes[0]
        m = re.search(r"AGENTS_HOOK_HOST=claude exec bash -p " + re.escape(LANCEUR_FERME)
                      + r" --echeance=([0-9]+) " + re.escape(cible) + "$", h["command"])
        if m is None:
            v.append(f"{nom} : queue hors forme (lanceur, AGENTS_HOOK_HOST=claude, échéance entière)")
        elif not isinstance(h.get("timeout"), int) or int(m.group(1)) + 1 + 1 > h["timeout"]:
            v.append(f"{nom} : échéance {m.group(1)} + 1 s de grâce + 1 s de marge > timeout "
                     f"{h.get('timeout')}")
        if nom == "gitleaks" and "GITLEAKS_TIMEOUT=" in h["command"]:
            # Un GITLEAKS_TIMEOUT sous l'échéance ferait DÉGRADER le scan (rc 0) avant le refus du lanceur.
            v.append("gitleaks : GITLEAKS_TIMEOUT= posé sur la jambe (S-01M5SZJEYP : jamais)")
    portees = [h["command"][-50:] for _, h in jambes_hooks(doc) if "garde-fermee" in h.get("command", "")]
    if len(portees) != len(JAMBES_FERMEES):
        v.append(f"registre : {len(portees)} jambes portent le lanceur, {len(JAMBES_FERMEES)} attendues")
    return v


def _sur_jambe(motif, f):
    return lambda d: f(_jambe(d, motif))


def _envelopper_stop(d, motif):
    """Mutant : la jambe Stop qui porte `motif` passe sous le lanceur (PostToolUse/Stop restent nus)."""
    h = next(h for b in d["hooks"]["Stop"] for h in b["hooks"] if motif in h["command"])
    h["command"] = h["command"].replace(
        "exec bash -p ", f"AGENTS_HOOK_HOST=claude exec bash -p {LANCEUR_FERME} --echeance=7 ", 1)


#: Contrôles négatifs (a)-(f) de l'annexe : chacun doit rougir en NOMMANT sa jambe.
MUTANTS_FERMES = (
    ("a lanceur retiré", "kickoff_guard", _sur_jambe('kickoff_guard.py"', lambda h: h.update(
        command=h["command"].replace(LANCEUR_FERME + " --echeance=7 ", "", 1)))),
    ("b timeout 8", "kickoff_guard", _sur_jambe('kickoff_guard.py"', lambda h: h.update(timeout=8))),
    ("c hôte retiré", "audit-gate", _sur_jambe('audit-gate.sh"', lambda h: h.update(
        command=h["command"].replace("AGENTS_HOOK_HOST=claude ", "", 1)))),
    ("d timeout gitleaks", "gitleaks", _sur_jambe('gitleaks-scan.sh"', lambda h: h.update(timeout=10))),
    ("e lanceur retiré de safe-bash", "safe-bash", _sur_jambe('safe-bash.sh"', lambda h: h.update(
        command=h["command"].replace(LANCEUR_FERME + " --echeance=7 ", "", 1)))),
    ("f échéance non entière", "iac_guard", _sur_jambe('iac_guard.py"', lambda h: h.update(
        command=h["command"].replace("--echeance=7", "--echeance=x", 1)))),
    ("g GITLEAKS_TIMEOUT posé", "gitleaks", _sur_jambe('gitleaks-scan.sh" --content', lambda h: h.update(
        command=h["command"].replace("AGENTS_HOOK_HOST=claude exec", "GITLEAKS_TIMEOUT=5 AGENTS_HOOK_HOST=claude exec",
                                     1)))),
    ("h jambe Stop enveloppée", "registre", lambda d: _envelopper_stop(d, 'context-retro.sh"')),
    ("i lanceur retiré de bancs-mandat", "bancs-mandat", _sur_jambe('bancs-mandat.sh"', lambda h: h.update(
        command=h["command"].replace(LANCEUR_FERME + " --echeance=7 ", "", 1)))),
)


def test_wc1_registre_claude_jambes_fermees(reglages):
    doc = reglages[1]
    v = violations_fermees(doc)
    assert not v, "\n".join(v)
    survivants = []
    for etiquette, nom, f in MUTANTS_FERMES:
        vm = violations_fermees(_muter(doc, f))
        if not any(x.startswith(f"{nom} ") for x in vm):
            survivants.append(f"({etiquette}) attendu {nom} : {vm}")
    assert not survivants, "contrôles négatifs survivants :\n" + "\n".join(survivants)


def _racine_fermee(base: Path, garde: str, corps: str) -> Path:
    """Racine jetable : le lanceur et pyrun.sh RÉELS, une garde factice au chemin enregistré."""
    for rel in (".agents/security/garde-fermee.sh", ".agents/pyrun.sh"):
        (base / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, base / rel)
    (base / garde).parent.mkdir(parents=True, exist_ok=True)
    (base / garde).write_text(corps, encoding="utf-8")
    return base


def _jambe_fermee(doc, nom) -> dict:
    h = next((h for ev, h in jambes_hooks(doc)
              if ev == "PreToolUse" and JAMBES_FERMEES[nom][0] in h.get("command", "")), None)
    assert h is not None, f"{nom} : aucune jambe PreToolUse enregistrée"
    return h


def _jouer_fermee(cmd: str, racine: Path, delai: int = 60):
    env = {k: os.environ[k] for k in ("PATH", "HOME", "TMPDIR") if k in os.environ}
    env.update(CLAUDE_PROJECT_DIR=str(racine), LC_ALL="C")
    debut = time.monotonic()
    p = subprocess.run(["/bin/sh", "-c", cmd], input=CHARGE_WC, capture_output=True, text=True,
                       env=env, cwd=str(racine), timeout=delai)
    return p, time.monotonic() - debut


@pytest.mark.parametrize("nom", tuple(JAMBES_FERMEES))
def test_wc2_jambes_enregistrees_refusent_le_plantage(reglages, tmp_path, nom):
    """La jambe ENREGISTRÉE, jouée sous /bin/sh : garde qui plante => BLOCKED rc 2 ; garde qui
    laisse passer => rc 0, sa sortie transmise à l'octet (R1, bras positif)."""
    cmd = _jambe_fermee(reglages[1], nom)["command"]
    p, _ = _jouer_fermee(cmd, _racine_fermee(tmp_path / "plante", GARDES_FACTICES[nom], PLANTAGES[nom]))
    assert p.returncode == 2 and "BLOCKED: garde-fermee: garde sortie en echec" in p.stderr, (
        f"{nom} : plantage non refusé — rc {p.returncode}, {p.stderr[-200:]!r}")
    p, _ = _jouer_fermee(cmd, _racine_fermee(tmp_path / "passe", GARDES_FACTICES[nom], PASSAGES[nom]))
    assert (p.returncode, p.stdout, p.stderr) == (0, CHARGE_WC, ""), (
        f"{nom} : bras positif — rc {p.returncode}, stdout {p.stdout[:80]!r}, {p.stderr[-200:]!r}")


def test_wc3_jambe_lente_refusee(reglages, tmp_path):
    """La jambe audit-gate ENREGISTRÉE, garde sourde à TERM : refus avant la clé timeout de l'hôte."""
    h = _jambe_fermee(reglages[1], "audit-gate")
    racine = _racine_fermee(tmp_path, GARDES_FACTICES["audit-gate"], 'trap "" TERM\nexec sleep 30\n')
    p, duree = _jouer_fermee(h["command"], racine, delai=45)
    assert p.returncode == 2 and "BLOCKED: garde-fermee: delai depasse" in p.stderr, (
        f"audit-gate : rc {p.returncode}, {p.stderr[-200:]!r}")
    assert duree <= h["timeout"], f"audit-gate : refus en {duree:.1f} s > timeout {h['timeout']}"


# ---------------------------------------------------------------------------
# W-C4 — GITLEAKS LENT REFUSÉ (T-01M4JRFRSMSA57ZT7D099G9F3H, S-01M5SZJEYP)
# ---------------------------------------------------------------------------
#: Échéance du rejeu : la jambe ENREGISTRÉE est lue au registre, seule son échéance 58 est
#: ramenée à 3 s (le bouchon dort 10 s : un refus au-delà prouverait une attente du scan).
ECHEANCE_WC4 = 3


def _bin_sans_timeout(base: Path, timeout_bin: str | None) -> Path:
    """PATH de liens vers /usr/bin et /bin, SANS timeout/gtimeout ni python* ; python3 lié à
    l'interpréteur du banc ; un `gitleaks` bouchon qui marque son passage puis dort 10 s."""
    d = base / "bin"
    d.mkdir()
    for src in ("/usr/bin", "/bin"):
        for f in sorted(Path(src).iterdir()):
            if f.name in ("timeout", "gtimeout") or f.name.startswith("python") or (d / f.name).exists():
                continue
            os.symlink(f, d / f.name)
    os.symlink(sys.executable, d / "python3")
    if timeout_bin:
        os.symlink(timeout_bin, d / "timeout")
    marque = base / "gitleaks-atteint"
    (d / "gitleaks").write_text(f"#!/bin/sh\n: > '{marque}'\nexec sleep 10\n", encoding="utf-8")
    (d / "gitleaks").chmod(0o755)
    return d


def _jouer_gitleaks_lent(reglages, base: Path, timeout_bin: str | None):
    h = _jambe_fermee(reglages[1], "gitleaks")
    assert "--echeance=58 " in h["command"] and "GITLEAKS_TIMEOUT" not in h["command"], (
        "gitleaks : jambe enregistrée hors forme (échéance 58, sans GITLEAKS_TIMEOUT)")
    cmd = h["command"].replace("--echeance=58 ", f"--echeance={ECHEANCE_WC4} ", 1)
    racine = base / "racine"
    for rel in (".agents/security/garde-fermee.sh", ".agents/security/gitleaks-scan.sh"):
        (racine / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, racine / rel)
    subprocess.run(["git", "init", "-q", str(racine)], check=True, capture_output=True, timeout=30)
    path = _bin_sans_timeout(base, timeout_bin)
    env = {k: os.environ[k] for k in ("HOME", "TMPDIR") if k in os.environ}
    env.update(PATH=str(path), CLAUDE_PROJECT_DIR=str(racine), LC_ALL="C", AGENTS_EVENTS_DIR=str(base / "ev"))
    debut = time.monotonic()
    p = subprocess.run(["/bin/sh", "-c", cmd], input=CHARGE_WC, capture_output=True, text=True,
                       env=env, cwd=str(racine), timeout=45)
    return p, time.monotonic() - debut, (base / "gitleaks-atteint").exists()


def _juger_gitleaks_lent(p, duree, atteint, bras):
    assert atteint, f"gitleaks {bras} : le bouchon n'a pas été atteint — rc {p.returncode}, {p.stderr[-300:]!r}"
    assert p.returncode == 2 and "BLOCKED: garde-fermee: delai depasse" in p.stderr, (
        f"gitleaks {bras} : scan lent non refusé — rc {p.returncode}, {p.stderr[-300:]!r}")
    assert duree < 10, f"gitleaks {bras} : refus en {duree:.1f} s, le scan a été attendu"


def test_wc4_gitleaks_lent_refuse_sans_timeout(reglages, tmp_path):
    """Sans timeout(1) sur le PATH, gitleaks-scan ne borne pas son scan : le lanceur refuse."""
    _juger_gitleaks_lent(*_jouer_gitleaks_lent(reglages, tmp_path, None), "SANS timeout")


def test_wc4_gitleaks_lent_refuse_avec_timeout(reglages, tmp_path):
    """Avec timeout(1) (GITLEAKS_TIMEOUT par défaut, 90 s) : l'échéance du lanceur passe avant."""
    tb = shutil.which("timeout") or shutil.which("gtimeout")
    if tb is None:
        pytest.skip("timeout(1)/gtimeout absent du PATH du banc : bras AVEC non mesurable ici, "
                    "le bras SANS tient le refus")
    _juger_gitleaks_lent(*_jouer_gitleaks_lent(reglages, tmp_path, tb), "AVEC timeout")


# ---------------------------------------------------------------------------
# W-C5 — DENY Edit DU LANCEUR, BORNE Bash ÉCRITE (S-01M5YXA6M9)
# ---------------------------------------------------------------------------
DENY_LANCEUR = "Edit(./.agents/security/garde-fermee.sh)"
#: La borne de l'étape 8, épinglée dans guardrails/SKILL.md.
BORNE_SKILL = ("l'écriture Bash du lanceur (`cp`, `sed -i`, `tee`, glob `garde-ferme[e].sh`) reste une BORNE",
               "ne sont tenues que par le banc de porte")
CP_LANCEUR = "cp /tmp/x .agents/security/garde-fermee.sh"
REDIRECTION_LANCEUR = "echo a > .agents/security/garde-fermee.sh"


def violations_deny(doc, skill: str) -> list[str]:
    deny = doc.get("permissions", {}).get("deny", [])
    v: list[str] = []
    if deny.count(DENY_LANCEUR) != 1:
        v.append("deny Edit du lanceur absent")
    if any(d.startswith("Bash(") and "garde-ferm" in d for d in deny):
        v.append("deny Bash du lanceur : retiré par S-01M5YXA6M9")
    v += [f"borne non écrite : « {p} »" for p in BORNE_SKILL if p not in skill]
    return v


def _safe_bash(cmd: str, ev: Path) -> subprocess.CompletedProcess:
    env = {k: os.environ[k] for k in ("PATH", "HOME", "TMPDIR") if k in os.environ}
    env.update(CLAUDE_PROJECT_DIR=str(ROOT), LC_ALL="C", AGENTS_EVENTS_DIR=str(ev))
    return subprocess.run(["bash", "-p", str(ROOT / ".claude/hooks/safe-bash.sh")], input=_sb(cmd),
                          capture_output=True, text=True, env=env, cwd=str(ROOT), timeout=60)


def test_wc5_deny_lanceur(reglages, tmp_path):
    doc, skill = reglages[1], SKILL.read_text(encoding="utf-8")
    v = violations_deny(doc, skill)
    assert not v, "\n".join(v)
    mutants = {
        "a ligne Edit retirée": (lambda d: d["permissions"]["deny"].remove(DENY_LANCEUR), skill,
                                 "deny Edit du lanceur absent"),
        "b deny Bash ajoutée": (lambda d: d["permissions"]["deny"].append("Bash(*garde-fermee.sh*)"), skill,
                                "deny Bash du lanceur"),
        "c borne retirée": (lambda d: None, skill.replace(BORNE_SKILL[1], ""), "borne non écrite"),
    }
    survivants = [nom for nom, (f, s, attendu) in mutants.items()
                  if not any(x.startswith(attendu) for x in violations_deny(_muter(doc, f), s))]
    assert not survivants, f"contrôles négatifs survivants : {survivants}"
    # Résidu K2, par COMPORTEMENT : l'écriture Bash du lanceur reste ouverte (borne écrite).
    p = _safe_bash(CP_LANCEUR, tmp_path)
    assert p.returncode == 0, (
        f"borne fermée : amender SKILL (« {BORNE_SKILL[0]} ») et ce pin — `{CP_LANCEUR}` rc {p.returncode}, "
        f"{p.stderr[-200:]!r}")
    p = _safe_bash(REDIRECTION_LANCEUR, tmp_path)
    assert p.returncode == 2, f"contrôle : `{REDIRECTION_LANCEUR}` rc {p.returncode}, {p.stderr[-200:]!r}"
