"""Témoins du lanceur `.agents/security/garde-fermee.sh` (T-01M5CH9FA8BDDM33QKDBAZG42S).

Le lanceur porte une garde PreToolUse et échoue FERMÉ : délai, plantage, rc hors
contrat, échéance invalide ou répertoire temporaire impossible valent REFUS —
enveloppe `deny` à rc 0 hors de l'hôte `claude`, `BLOCKED:` à rc 2 sous `claude`.
W1-W10 de l'annexe du plan ; chaque garde lancée ici est un script écrit sous
`tmp_path`. W9 lit le registre `.codex/hooks.json` : depuis T-01M4JRFR3QYKP9MC77V7XQ36BE
(S-01M5SZJEFVR5SNVC5F9B8Y9201), la jambe gitleaks `--content` y est ENVELOPPÉE sous
`--echeance=50`, assertée par égalité ; ses `commandWindows` restent nues.
W15-W16 jouent cette jambe telle que le registre l'écrit, dans un dépôt jetable :
un gitleaks qui pend est refusé à l'échéance, un secret trouvé (rc 2) devient un
`deny` à rc 0. W17 : la skill guardrails dit cette borne ; W18 : elle dit
l'orphelin gitleaks laissé vivant à l'échéance.
W11-W13 (T-01M5MCXKHQS4BME9Z9VVSWD6VT, S-01M5MCXYH5) : la branche `copilot` du
lanceur (refus à la racine ET imbriqué — Copilot CLI ignore l'imbriqué seul, M3)
et les cinq jambes `bash` preToolUse de `.github/hooks/agent-guardrails.json`
qu'il enveloppe ; gitleaks et les jambes powershell y restent nues.
W14 : la skill guardrails dit, sur ses trois sites, ce que W11-W13 tiennent.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
from surface_kit import jambe_du_kit, jambe_jugee  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
LANCEUR = ROOT / ".agents" / "security" / "garde-fermee.sh"
REGISTRE = ROOT / ".codex" / "hooks.json"
RACINE = '"$(git rev-parse --show-toplevel)'
PREFIXE = f'AGENTS_HOOK_HOST=codex bash {RACINE}/.agents/security/garde-fermee.sh" --echeance='
GARDES_ENVELOPPEES = {"protect_paths.py", "kickoff_guard.py", "audit_gate.py",
                      "safe_bash.py", "iac_guard.py"}
ECHEANCE_GITLEAKS = 50
JAMBE_GITLEAKS_ENVELOPPEE = (
    f'{PREFIXE}{ECHEANCE_GITLEAKS} {RACINE}/.agents/security/gitleaks-scan.sh" --content'
)
REGISTRE_COPILOT = ROOT / ".github" / "hooks" / "agent-guardrails.json"
JAMBE_COPILOT_RE = re.compile(
    r"AGENTS_HOOK_HOST=copilot bash \.agents/security/garde-fermee\.sh "
    r"--echeance=(?P<echeance>[0-9]+) \.agents/pyrun\.sh (?P<garde>\.[^ ]+/(?P<nom>[^ /]+\.py))"
)
JAMBE_COPILOT_GITLEAKS_NUE = "AGENTS_HOOK_HOST=copilot bash .agents/security/gitleaks-scan.sh --content"

posix = pytest.mark.skipif(os.name == "nt", reason="lanceur POSIX (bash, sleep, kill)")


def _bash() -> str:
    moteur = shutil.which("bash")
    if moteur is None:
        pytest.skip("bash absent — lanceur POSIX non mesuré")
    return moteur


def _lancer(tmp_path: Path, corps: str | None, *, hote: str | None = "codex",
            echeance: str | None = "5", entree: bytes = b"payload\n",
            path: str | None = None, extra: dict[str, str] | None = None
            ) -> tuple[subprocess.CompletedProcess[bytes], float]:
    env = {"PATH": path if path is not None else os.environ.get("PATH", ""),
           "TMPDIR": str(tmp_path), "HOME": str(tmp_path)}
    if hote is not None:
        env["AGENTS_HOOK_HOST"] = hote
    env.update(extra or {})
    cmd = [_bash(), str(LANCEUR)]
    if echeance is not None:
        cmd.append(f"--echeance={echeance}")
    if corps is not None:
        garde = tmp_path / "garde.sh"
        garde.write_text(corps, encoding="utf-8")
        cmd.append(str(garde))
    debut = time.monotonic()
    proc = subprocess.run(cmd, input=entree, capture_output=True, env=env,
                          cwd=tmp_path, timeout=60, check=False)
    return proc, time.monotonic() - debut


def _refus_enveloppe(proc: subprocess.CompletedProcess[bytes], raison: str) -> None:
    assert proc.returncode == 0, proc.stderr
    corps = json.loads(proc.stdout.decode("utf-8"))["hookSpecificOutput"]
    assert corps["hookEventName"] == "PreToolUse"
    assert corps["permissionDecision"] == "deny"
    assert corps["permissionDecisionReason"] == f"garde-fermee: {raison}, refus par defaut"


@posix
def test_w1_garde_libre_transmise_a_l_octet(tmp_path: Path) -> None:
    proc, _ = _lancer(tmp_path, "printf 'sortie libre\\n'\nprintf 'diag\\n' >&2\n")
    assert proc.returncode == 0
    assert proc.stdout == b"sortie libre\n"
    assert proc.stderr == b"diag\n"
    assert not list(tmp_path.glob("garde-fermee.*")), "répertoire temporaire laissé"


@posix
@pytest.mark.parametrize(("hote", "attendu_rc"), (("codex", 0), ("claude", 2)))
def test_w2_garde_lente_refusee_au_delai(tmp_path: Path, hote: str, attendu_rc: int) -> None:
    proc, duree = _lancer(tmp_path, "exec sleep 30\n", hote=hote, echeance="1")
    assert duree < 4, duree
    if hote == "claude":
        assert proc.returncode == attendu_rc
        assert b"BLOCKED: garde-fermee: delai depasse" in proc.stderr
        assert proc.stdout == b""
    else:
        _refus_enveloppe(proc, "delai depasse")


@posix
def test_w3_garde_sourde_a_term_tuee_apres_la_grace(tmp_path: Path) -> None:
    proc, duree = _lancer(tmp_path, 'trap "" TERM\nexec sleep 10\n', echeance="1")
    assert duree < 1 + 3, duree
    _refus_enveloppe(proc, "delai depasse")


@posix
def test_w3_garde_qui_range_a_term_a_sa_grace(tmp_path: Path) -> None:
    corps = ("trap 'kill \"$!\"; sleep 0.3; : > \"$TMPDIR/propre\"; exit 143' TERM\n"
             "sleep 30 &\nwait \"$!\"\n")
    proc, _ = _lancer(tmp_path, corps, echeance="1")
    _refus_enveloppe(proc, "delai depasse")
    assert (tmp_path / "propre").exists(), "KILL avant la seconde de grâce"


@posix
@pytest.mark.parametrize("hote", ("codex", "claude"))
def test_w4_rc_1_refuse(tmp_path: Path, hote: str) -> None:
    proc, _ = _lancer(tmp_path, "printf 'sortie\\n'\nexit 1\n", hote=hote)
    if hote == "claude":
        assert proc.returncode == 2
        assert proc.stdout == b""
        assert proc.stderr.endswith(
            b"BLOCKED: garde-fermee: garde sortie en echec, refus par defaut\n"
        )
    else:
        _refus_enveloppe(proc, "garde sortie en echec")


@posix
def test_w5_rc_2_enveloppe_sur_codex(tmp_path: Path) -> None:
    proc, _ = _lancer(tmp_path, "printf 'sortie\\n'\nexit 2\n")
    _refus_enveloppe(proc, "garde sortie en echec")


@posix
@pytest.mark.parametrize("hote", ("claude", None))
def test_w6_rc_2_transmis_sous_claude(tmp_path: Path, hote: str | None) -> None:
    proc, _ = _lancer(tmp_path, "printf 'sortie\\n'\nprintf 'BLOCKED: motif\\n' >&2\nexit 2\n",
                      hote=hote)
    assert proc.returncode == 2
    assert proc.stdout == b"sortie\n"
    assert proc.stderr == b"BLOCKED: motif\n"


@posix
def test_w7_sans_mktemp_refuse(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin-sans-mktemp"
    bin_dir.mkdir()
    for outil in ("bash", "cat", "sleep", "rm"):
        resolu = shutil.which(outil)
        if resolu is None:
            pytest.skip(f"{outil} absent — bras PATH réduit non mesuré")
        (bin_dir / outil).symlink_to(resolu)
    proc, _ = _lancer(tmp_path, "printf 'sortie\\n'\n", path=str(bin_dir))
    _refus_enveloppe(proc, "repertoire temporaire impossible")


@posix
def test_w7_tmpdir_perime_repli_sur_tmp(tmp_path: Path) -> None:
    """Un TMPDIR périmé ne refuse pas tout : repli sur /tmp (F2, clôture couloir B).
    MUTATION : retirer le repli `|| d=$(mktemp -d /tmp/…)` → refus → rouge."""
    proc, _ = _lancer(tmp_path, "printf 'sortie\\n'\n", extra={"TMPDIR": "/nonexistent"})
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stdout == b"sortie\n"
    assert proc.stderr == b""


@posix
def test_w7_entree_standard_fermee_refusee(tmp_path: Path) -> None:
    """Une entrée standard FERMÉE (fd 0 absent) est un refus à raison fixe.
    MUTATION : retirer `|| refuser "lecture du payload impossible"` → la raison
    devient « garde sortie en echec » → rouge."""
    garde = tmp_path / "garde.sh"
    garde.write_text("printf 'sortie\\n'\n", encoding="utf-8")
    env = {"PATH": os.environ.get("PATH", ""), "TMPDIR": str(tmp_path),
           "HOME": str(tmp_path), "AGENTS_HOOK_HOST": "codex"}
    proc = subprocess.run([_bash(), "-c", 'exec "$@" <&-', "_", _bash(), str(LANCEUR),
                           "--echeance=5", str(garde)],
                          capture_output=True, env=env, cwd=tmp_path, timeout=60,
                          check=False)
    _refus_enveloppe(proc, "lecture du payload impossible")


@posix
@pytest.mark.parametrize("echeance", ("x", "", "-1", "1.5"))
def test_w7_echeance_invalide_refusee(tmp_path: Path, echeance: str) -> None:
    proc, _ = _lancer(tmp_path, "printf 'sortie\\n'\n", echeance=echeance)
    _refus_enveloppe(proc, "echeance invalide")


@posix
def test_w7_echeance_absente_refusee(tmp_path: Path) -> None:
    proc, _ = _lancer(tmp_path, "printf 'sortie\\n'\n", echeance=None)
    _refus_enveloppe(proc, "echeance invalide")


@posix
def test_w7_aucune_garde_nommee_refusee(tmp_path: Path) -> None:
    proc, _ = _lancer(tmp_path, None)
    _refus_enveloppe(proc, "aucune garde nommee")


@posix
def test_w8_payload_transmis_identique(tmp_path: Path) -> None:
    entree = bytes(range(256)) * 64 + b"\xc3\xa9 sans fin de ligne"
    proc, _ = _lancer(tmp_path, "exec cat\n", entree=entree)
    assert proc.returncode == 0
    assert hashlib.sha256(proc.stdout).hexdigest() == hashlib.sha256(entree).hexdigest()


@posix
def test_w8_payload_jamais_sur_disque(tmp_path: Path) -> None:
    """Le payload (le contenu d'un Write) n'est jamais copié dans le répertoire
    temporaire : seuls `out` et `err` y vivent pendant la garde.
    MUTATION : rétablir `cat > "$d/in"` et `< "$d/in"` → `in` listé → rouge."""
    corps = ('cat > /dev/null\n'
             'for f in "$TMPDIR"/garde-fermee.*/*; do printf \'%s\\n\' "${f##*/}"; done\n')
    proc, _ = _lancer(tmp_path, corps, entree=b"secret du Write\n")
    assert proc.returncode == 0, proc.stderr
    assert sorted(proc.stdout.decode("utf-8").split()) == ["err", "out"]


@posix
def test_w8_garde_lancee_sans_bash_env(tmp_path: Path) -> None:
    injection = tmp_path / "bash_env.sh"
    injection.write_text('case "$0" in\n  */garde.sh) printf INJECTE ;;\nesac\n', encoding="utf-8")
    proc, _ = _lancer(tmp_path, "printf 'sortie\\n'\n", extra={"BASH_ENV": str(injection)})
    assert proc.returncode == 0
    assert proc.stdout == b"sortie\n"


def _jambes(doc: dict) -> list[tuple[str, dict]]:
    return [(evenement, jambe) for evenement, blocs in doc["hooks"].items()
            for bloc in blocs for jambe in bloc["hooks"]]


def test_w9_registre_codex_enveloppe_les_cinq_gardes_pyrun() -> None:
    doc = json.loads(REGISTRE.read_text(encoding="utf-8"))
    enveloppees: set[str] = set()
    gitleaks_vue = False
    for evenement, jambe in _jambes(doc):
        commande = str(jambe.get("command", ""))
        fenetres = str(jambe.get("commandWindows", ""))
        if jambe_jugee(fenetres):
            assert "garde-fermee" not in fenetres, fenetres
        # Hors du kit, une jambe AJOUTÉE par l'adoptant est à sa charge (surface_kit).
        if not jambe_jugee(commande):
            continue
        if evenement != "PreToolUse":
            assert "garde-fermee" not in commande, (evenement, commande)
            continue
        if "gitleaks-scan.sh" in commande:
            assert commande == JAMBE_GITLEAKS_ENVELOPPEE, commande
            assert ECHEANCE_GITLEAKS + 1 + 1 <= int(jambe["timeout"]), commande
            gitleaks_vue = True
            continue
        assert ".agents/pyrun.sh" in commande, commande
        assert commande.startswith(PREFIXE), commande
        echeance = re.match(r"([0-9]+) ", commande[len(PREFIXE):])
        assert echeance is not None, commande
        assert int(echeance.group(1)) + 1 + 1 <= int(jambe["timeout"]), commande
        assert commande.count(".agents/pyrun.sh") == 1
        enveloppees.add(commande.rsplit("/", 1)[1].rstrip('"'))
    assert enveloppees == GARDES_ENVELOPPEES
    assert gitleaks_vue, "jambe gitleaks --content absente du PreToolUse Codex"


def test_w9_lanceur_du_kit_n_attribue_pas_la_jambe_de_l_adoptant() -> None:
    """`garde-fermee.sh` est un lanceur du kit (surface_kit.LANCEURS_DU_KIT) : une
    jambe de l'adoptant qu'il enveloppe reste à l'adoptant, une jambe du kit au kit.
    MUTATION : retirer `garde-fermee.sh` de LANCEURS_DU_KIT → jambe adoptant
    attribuée au kit → rouge."""
    adoptant = f"{PREFIXE}7 {RACINE}/.agents/pyrun.sh\" {RACINE}/scripts/audit.py\""
    du_kit = f"{PREFIXE}7 {RACINE}/.agents/pyrun.sh\" {RACINE}/.codex/hooks/iac_guard.py\""
    assert not jambe_du_kit(adoptant), adoptant
    assert jambe_du_kit(du_kit), du_kit


@posix
def test_w10_aucun_sleep_orphelin_apres_une_garde_rapide(tmp_path: Path) -> None:
    if shutil.which("pgrep") is None:
        pytest.skip("pgrep absent — orphelin non mesuré")
    echeance = "4747"
    motif = f"^sleep {echeance}$"
    proc, _ = _lancer(tmp_path, "printf 'sortie\\n'\n", echeance=echeance)
    assert proc.returncode == 0
    trouves = subprocess.run(["pgrep", "-f", motif], capture_output=True, text=True,
                             check=False).stdout.split()
    if trouves:
        subprocess.run(["pkill", "-f", motif], check=False)
    assert trouves == [], f"sleep {echeance} orphelin(s) : {trouves}"


@posix
@pytest.mark.parametrize(("corps", "raison"), (
    ("exec sleep 30\n", "delai depasse"),
    ("exit 1\n", "garde sortie en echec"),
    ("exit 2\n", "garde sortie en echec"),
))
def test_w11_copilot_refus_a_la_racine_et_imbrique(tmp_path: Path, corps: str,
                                                    raison: str) -> None:
    """Sous `copilot`, le refus est porté à la racine ET imbriqué, rc 0 : Copilot CLI
    ignore l'imbriqué seul (M3) et laisserait l'outil tourner (M4, M5). Hors
    `copilot`, la racine reste vide.
    MUTATION : retirer la branche `copilot)` de refuser() → racine absente → rouge."""
    proc, _ = _lancer(tmp_path, corps, hote="copilot", echeance="1")
    _refus_enveloppe(proc, raison)
    corps_json = json.loads(proc.stdout.decode("utf-8"))
    attendu = f"garde-fermee: {raison}, refus par defaut"
    assert corps_json.get("permissionDecision") == "deny", corps_json
    assert corps_json.get("permissionDecisionReason") == attendu, corps_json
    autre, _ = _lancer(tmp_path, corps, hote="codex", echeance="1")
    _refus_enveloppe(autre, raison)
    assert "permissionDecision" not in json.loads(autre.stdout.decode("utf-8"))


def _jambes_copilot() -> list[tuple[str, dict]]:
    doc = json.loads(REGISTRE_COPILOT.read_text(encoding="utf-8"))
    return [(evenement, jambe) for evenement, jambes in doc["hooks"].items()
            for jambe in jambes]


def test_w12_registre_copilot_enveloppe_les_cinq_gardes_pyrun() -> None:
    """Les cinq gardes `pyrun` preToolUse de Copilot passent par le lanceur fermé,
    sous sa forme EXACTE, avec une échéance + 1 s de grâce sous `timeoutSec`
    (refus avant que Copilot ne laisse passer, M1, M9) ; gitleaks reste nue,
    aucune jambe powershell ni hors preToolUse n'est enveloppée.
    MUTATION : une jambe remise nue, ou `--echeance=9` → rouge."""
    enveloppees: set[str] = set()
    for evenement, jambe in _jambes_copilot():
        commande = str(jambe.get("bash", ""))
        fenetres = str(jambe.get("powershell", ""))
        if jambe_jugee(fenetres):
            assert "garde-fermee" not in fenetres, fenetres
        if not jambe_jugee(commande):
            continue
        if evenement != "preToolUse":
            assert "garde-fermee" not in commande, (evenement, commande)
            continue
        if "gitleaks-scan.sh" in commande:
            assert commande == JAMBE_COPILOT_GITLEAKS_NUE, commande
            continue
        forme = JAMBE_COPILOT_RE.fullmatch(commande)
        assert forme is not None, commande
        assert (ROOT / forme.group("garde")).is_file(), commande
        assert int(forme.group("echeance")) + 1 < int(jambe["timeoutSec"]), commande
        enveloppees.add(forme.group("nom"))
    assert enveloppees == GARDES_ENVELOPPEES


@posix
@pytest.mark.parametrize(("interpreteur", "raison"), (
    ("exec sleep 60\n", "delai depasse"),
    ("exit 1\n", "garde sortie en echec"),
))
def test_w13_jambe_copilot_enregistree_refuse(tmp_path: Path, interpreteur: str,
                                              raison: str) -> None:
    """La jambe safe_bash ENREGISTRÉE, jouée telle quelle, avec un interpréteur qui
    dort ou plante : refus à la racine, rc 0, avant `timeoutSec`.
    MUTATION : jambe remise nue → l'interpréteur dort jusqu'à `timeoutSec`
    (TimeoutExpired) ou sort rc 1 sans refus → rouge."""
    _bash()
    jambe = next(j for e, j in _jambes_copilot()
                 if e == "preToolUse" and str(j.get("bash", "")).endswith("/safe_bash.py"))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "python3").write_text('#!/bin/sh\nprintf "%s\\n" "$FAUX"\n', encoding="utf-8")
    (bin_dir / "faux").write_text(f"#!/bin/sh\n{interpreteur}", encoding="utf-8")
    for nom in ("python3", "faux"):
        (bin_dir / nom).chmod(0o755)
    for outil in ("bash", "git", "mktemp", "sleep", "cat", "rm"):
        resolu = shutil.which(outil)
        if resolu is None:
            pytest.skip(f"{outil} absent — jambe Copilot enregistrée non mesurée")
        (bin_dir / outil).symlink_to(resolu)
    env = {"PATH": str(bin_dir), "FAUX": str(bin_dir / "faux"),
           "HOME": str(tmp_path), "TMPDIR": str(tmp_path)}
    debut = time.monotonic()
    proc = subprocess.run([_bash(), "-c", jambe["bash"]], cwd=ROOT, env=env,
                          input=b'{"toolName":"bash","toolArgs":{"command":"ls"}}',
                          capture_output=True, timeout=jambe["timeoutSec"], check=False)
    assert time.monotonic() - debut < jambe["timeoutSec"]
    _refus_enveloppe(proc, raison)
    corps = json.loads(proc.stdout.decode("utf-8"))
    assert corps.get("permissionDecision") == "deny", corps


GUARDRAILS = ROOT / ".agents" / "skills" / "guardrails" / "SKILL.md"
DOCTRINE_COPILOT = (
    ("kickoff_guard", (
        "on Copilot POSIX the five `bash` preToolUse legs",
        "an expired deadline, a crash or an rc 2 into a `deny` at the ROOT and nested, rc 0",
        "Copilot CLI ignores the nested deny alone")),
    ("safe_bash", (
        "On Copilot POSIX too:",
        "a deadline, a crash or an rc 2 is a `deny` carried at the root and nested, rc 0")),
    ("iac_guard", (
        "sous Copilot POSIX, le délai, le plantage et le rc 2 sont refusés à la racine ET "
        "imbriqués, rc 0",
        "Copilot ignore l'imbriqué seul")),
)


@pytest.mark.parametrize(("site", "jetons"), DOCTRINE_COPILOT)
def test_w14_doctrine_guardrails_copilot_refuse_delai_plantage_rc2(site: str,
                                                                   jetons: tuple[str, ...]) -> None:
    """La skill guardrails DIT ce que W11-W13 tiennent : sous Copilot POSIX, le délai, le
    plantage et le rc 2 sont refusés (racine ET imbriqué, rc 0), sur chacun des trois sites
    qui en parlent. Les jetons d'un site doivent tenir sur UNE même ligne (un paragraphe).
    MUTATION : texte de la skill remis à 1ea14e67b (avant la branche Copilot) → rouge."""
    lignes = GUARDRAILS.read_text(encoding="utf-8").splitlines()
    porteuses = [ligne for ligne in lignes if all(j in ligne for j in jetons)]
    assert porteuses, f"{site} : doctrine Copilot POSIX absente de {GUARDRAILS.name} — {jetons}"


SCAN_SECRETS = ROOT / ".agents" / "security" / "gitleaks-scan.sh"
PATH_REPLI = "/usr/bin:/bin"


def _jambe_gitleaks_du_registre() -> dict:
    doc = json.loads(REGISTRE.read_text(encoding="utf-8"))
    for evenement, jambe in _jambes(doc):
        commande = str(jambe.get("command", ""))
        if evenement == "PreToolUse" and "gitleaks-scan.sh" in commande:
            return jambe
    raise AssertionError("jambe gitleaks --content absente du PreToolUse Codex")


def _depot_jetable(tmp_path: Path) -> Path:
    """Dépôt git sous tmp_path qui porte les deux scripts de la jambe : la commande
    du registre y résout `git rev-parse --show-toplevel` sur lui, jamais sur le kit."""
    depot = tmp_path / "depot"
    securite = depot / ".agents" / "security"
    securite.mkdir(parents=True)
    for script in (LANCEUR, SCAN_SECRETS):
        shutil.copy2(script, securite / script.name)
    git = shutil.which("git")
    if git is None:
        pytest.skip("git absent — jambe gitleaks Codex non mesurée")
    subprocess.run([git, "init", "-q", str(depot)], check=True, capture_output=True)
    return depot


def _jouer_jambe(tmp_path: Path, depot: Path, commande: str, path: str,
                 charge: bytes) -> tuple[subprocess.CompletedProcess[bytes], float]:
    evenements = tmp_path / "evenements"
    evenements.mkdir(exist_ok=True)
    env = {"PATH": path, "HOME": str(tmp_path), "TMPDIR": str(tmp_path),
           "AGENTS_EVENTS_DIR": str(evenements)}
    debut = time.monotonic()
    proc = subprocess.run([_bash(), "-c", commande], cwd=depot, env=env, input=charge,
                          capture_output=True, timeout=60, check=False)
    return proc, time.monotonic() - debut


def _charge_write(contenu: str) -> bytes:
    return json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Write",
                       "tool_input": {"file_path": "note.txt", "content": contenu}}).encode()


@posix
def test_w15_jambe_gitleaks_codex_qui_pend_refusee_a_l_echeance(tmp_path: Path) -> None:
    """La jambe gitleaks `--content` du registre, jouée telle qu'écrite (échéance
    ramenée de 50 à 1 s pour le banc), refuse un gitleaks qui pend au lieu de le
    laisser courir jusqu'au `timeout` de l'hôte.
    MUTATION : jambe remise NUE au registre → le bouchon dort 10 s → durée ≥ 5 s, rouge."""
    depot = _depot_jetable(tmp_path)
    bouchons = tmp_path / "bouchons"
    bouchons.mkdir()
    gitleaks = bouchons / "gitleaks"
    gitleaks.write_text("#!/bin/sh\nexec sleep 10\n", encoding="utf-8")
    gitleaks.chmod(0o755)
    commande = str(_jambe_gitleaks_du_registre()["command"]).replace(
        f"--echeance={ECHEANCE_GITLEAKS} ", "--echeance=1 ")
    proc, duree = _jouer_jambe(tmp_path, depot, commande,
                               f"{bouchons}{os.pathsep}{os.environ.get('PATH', '')}",
                               _charge_write("texte banal\n"))
    assert duree < 5, (duree, proc.stderr)
    _refus_enveloppe(proc, "delai depasse")


@posix
def test_w16_jambe_gitleaks_codex_secret_trouve_devient_deny(tmp_path: Path) -> None:
    """Sur le repli déterministe (PATH sans gitleaks), un secret trouvé sort rc 2 du
    scanner ; la jambe du registre telle quelle le rend en `deny` à rc 0, avec le
    constat du scanner sur stderr (un scanner planté ne ferait pas ce constat) ; une
    charge banale passe, rc 0, sans décision (C1, critique 1).
    MUTATION : jambe remise NUE au registre → rc 2 sans enveloppe deny → rouge."""
    if shutil.which("gitleaks", path=PATH_REPLI) is not None:
        pytest.skip("gitleaks sous /usr/bin:/bin — repli déterministe non joué")
    if shutil.which("git", path=PATH_REPLI) is None:
        pytest.skip("git absent de /usr/bin:/bin — jambe gitleaks Codex non mesurée")
    depot = _depot_jetable(tmp_path)
    commande = str(_jambe_gitleaks_du_registre()["command"])
    jeton = "gh" + "p_" + "aB3dE6gH9jK2mN5pQ8sT1vW4yZ7cF0hJ3lR6"
    proc, _ = _jouer_jambe(tmp_path, depot, commande, PATH_REPLI,
                           _charge_write(f"cle = {jeton}\n"))
    _refus_enveloppe(proc, "garde sortie en echec")
    assert b"1 finding(s)" in proc.stderr, proc.stderr
    benin, _ = _jouer_jambe(tmp_path, depot, commande, PATH_REPLI,
                            _charge_write("texte banal\n"))
    assert benin.returncode == 0, benin.stderr
    assert b"permissionDecision" not in benin.stdout, benin.stdout
    assert b"0 finding(s)" in benin.stderr, benin.stderr


DOCTRINE_GITLEAKS_CODEX = (
    "the gitleaks `--content` leg of the `PreToolUse Edit|Write|apply_patch` block",
    "`--echeance=50`",
    "a `GITLEAKS_TIMEOUT` set below 50 s still degrades to rc 0 and lets the write through",
    "The six Codex PreToolUse `commandWindows` legs, gitleaks included, stay bare: out of scope, not measured",
    "rc 127, 126 or 0, read as an approval (not measured on Codex)", "T-01M5Y4VEGG",
)
DOCTRINE_GITLEAKS_ORPHELIN = (
    "kills only its direct child",
    "the gitleaks grandchild outlives the `deny` as an orphan",
    "unbounded where `timeout(1)` is missing",
)


def _ligne_guardrails_portant(jetons: tuple[str, ...]) -> list[str]:
    lignes = GUARDRAILS.read_text(encoding="utf-8").splitlines()
    return [ligne for ligne in lignes if all(j in ligne for j in jetons)]


def test_w17_doctrine_guardrails_jambe_gitleaks_codex() -> None:
    """La skill guardrails DIT ce que W9, W15 et W16 tiennent, sur UNE ligne : la jambe
    gitleaks Codex POSIX sous `--echeance=50` et son matcher, la borne `GITLEAKS_TIMEOUT`
    sous 50 s, les six `commandWindows` nues, et la borne héritée du lanceur absent,
    illisible ou vide (C2, critique 1 ; S-01M5YE6RY3). Chaque phrase de borne porte un
    jeton qu'elle seule écrit.
    MUTATION : une phrase de borne retirée de la skill → rouge."""
    assert _ligne_guardrails_portant(DOCTRINE_GITLEAKS_CODEX), \
        f"borne gitleaks Codex absente de {GUARDRAILS.name}"


def test_w18_doctrine_guardrails_gitleaks_orphelin_a_l_echeance() -> None:
    """La skill guardrails DIT, sur la ligne de W17, qu'à l'échéance le lanceur ne tue que
    son enfant direct : le gitleaks petit-enfant survit au `deny`, sans limite sans
    `timeout(1)` (exec-critic, constat 1 de la passe R3Q).
    MUTATION : phrase « Deadline bound » retirée de la skill → rouge."""
    assert _ligne_guardrails_portant(DOCTRINE_GITLEAKS_CODEX + DOCTRINE_GITLEAKS_ORPHELIN), \
        f"borne de l'orphelin gitleaks absente de {GUARDRAILS.name}"
