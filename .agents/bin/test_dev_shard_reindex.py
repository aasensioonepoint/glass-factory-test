"""Tests for dev_shard_reindex.py (T-00000593, candidate (g)).

THE REAL `build_index.py` IS NEVER CALLED HERE, and that is the design rather
than a shortcut. Each arm plants a FAKE builder in a throwaway root and decides
what it prints, how long it takes and what it returns — so the arms measure the
hook's own branching instead of the index of whatever tree the suite happens to
run in. A bench that needed a real index would be slow, non-deterministic, and
would have gone green on a repo whose index was already current.

Measured on this repo the day the hook was written: the staleness probe costs
0,29 s and the incremental rebuild 0,43 s. Those two numbers are what decided
REBUILD over NUDGE; they are recorded in the hook's own docstring, not asserted
here — a bench must not pin a machine's timing.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
HOOK = HERE / "dev_shard_reindex.py"

_spec = importlib.util.spec_from_file_location("dev_shard_reindex", HOOK)
dev_shard_reindex = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = dev_shard_reindex
_spec.loader.exec_module(dev_shard_reindex)


def _plant(root: Path, body: str) -> None:
    """Write a fake `build_index.py` that behaves exactly as `body` says."""
    target = root / ".agents" / "bin"
    target.mkdir(parents=True, exist_ok=True)
    (target / "build_index.py").write_text(body, encoding="utf-8")


BUILDER_REBUILT = (
    "print('INDEX BUILT @ abc1234 [ctags, incremental, 11 files scanned]:')\n"
    "print('- SYMBOLS: 6130 active')\n"
)
# IL PARLE COMME LE VRAI, et la première rédaction ne le faisait pas : elle
# mettait `pass` (stdout vide) là où `--if-stale` imprime réellement
# `INDEX CURRENT @ <sha> — nothing to rebuild`. Un faux constructeur muet rend
# l'arm du cas courant VACANT — il passerait sur n'importe quelle logique.
BUILDER_CURRENT = "print('INDEX CURRENT @ abc1234 - nothing to rebuild')\n"
# LES DEUX FORMES QUE LES 26 PREMIERS ARMS NE VOYAIENT PAS. `build_index.py`
# imprime ses lignes de VERROU sur stdout AVANT sa ligne de résultat : un
# `startswith` prenait donc une reconstruction FAITE pour une absence.
BUILDER_STOLEN_LOCK = (
    "print('build_index: lock older than 300s taken over (previous build died "
    "without releasing it)')\n"
    "print('INDEX BUILT @ abc1234 [ctags, incremental, 11 files scanned]:')\n"
)
BUILDER_IN_FLIGHT = "print('INDEX BUILD IN FLIGHT - skipped')\n"
BUILDER_SLOW = "import time\ntime.sleep(30)\n"
BUILDER_BROKEN = "import sys\nsys.exit(3)\n"


def _run(root: Path, payload, env_extra=None) -> subprocess.CompletedProcess:
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    env = {"CLAUDE_PROJECT_DIR": str(root), "PATH": "/usr/bin:/bin"}
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(HOOK)], input=raw, text=True,
        capture_output=True, env=env, timeout=60, check=False,
    )


def _message(done: subprocess.CompletedProcess) -> str:
    out = done.stdout.strip()
    if not out:
        return ""
    return json.loads(out).get("systemMessage", "")


# --- le périmètre, et le fait qu'il soit FERMÉ -------------------------------

@pytest.mark.parametrize("agent", ["dev-mono", "dev-multi", "frontend-fidelity"])
def test_every_dev_slot_triggers_a_rebuild(tmp_path, agent):
    """Les trois slots qui ÉCRIVENT du code. `frontend-fidelity` en fait partie
    parce qu'`AGENTS.md` en fait LE slot dev d'une tâche UI : l'omettre
    laisserait la fenêtre grande ouverte sur les tâches qui déplacent le plus de
    fichiers de composants."""
    _plant(tmp_path, BUILDER_REBUILT)
    done = _run(tmp_path, {"agent_type": agent})
    assert done.returncode == 0
    assert "Index rebuilt" in _message(done)
    assert agent in _message(done)


@pytest.mark.parametrize("agent", [
    "planner", "documenter", "critic-opus", "indexer", "communicator",
    "security-code-review", "exec-critic", "", "dev", "dev-mono-extra",
    # T-01M52X1W3WPKCWX1DC36NMKJB6 (2026-10-19) : terraform-deployer ÉCRIT (de l'IaC) mais
    # reste HORS de DEV_AGENTS — `.tf` n'est pas indexé ; rien ne l'épinglait avant.
    "terraform-deployer",
])
def test_the_set_is_closed_and_everything_else_is_silent(tmp_path, agent):
    """CONTRÔLE NÉGATIF, et c'est lui qui donne son sens au paramétrage
    ci-dessus. Sans lui, un hook qui reconstruirait sur CHAQUE retour de
    sous-agent passerait les trois arms précédents — en payant une
    reconstruction par retour, y compris après un agent read-only."""
    _plant(tmp_path, BUILDER_REBUILT)
    done = _run(tmp_path, {"agent_type": agent})
    assert done.returncode == 0
    assert done.stdout == "", f"le hook a parlé pour '{agent}'"


def test_both_spellings_of_the_field_are_accepted(tmp_path):
    """`agent_type` ET `agentType`. Ce n'est pas de la programmation défensive :
    `binome-trace` ne lisait que la première, et sur un hôte en camelCase il se
    taisait EN SILENCE — donc aucune trace, donc la sortie tracée comme seule
    issue. Une seule panne muette mesurée suffit à accepter les deux."""
    _plant(tmp_path, BUILDER_REBUILT)
    for field in ("agent_type", "agentType"):
        done = _run(tmp_path, {field: "dev-multi"})
        assert "Index rebuilt" in _message(done), field


# --- le cas courant : il se TAIT quand il n'a rien fait ----------------------

def test_an_index_already_current_produces_zero_bytes(tmp_path):
    """`--if-stale` n'imprime `INDEX BUILT` que s'il a VRAIMENT reconstruit. Le
    hook s'ancre sur cette ligne, ce qui le rend muet sur le cas courant — un
    hook qui annonce son inaction est du bruit à chaque retour."""
    _plant(tmp_path, BUILDER_CURRENT)
    done = _run(tmp_path, {"agent_type": "dev-mono"})
    assert done.returncode == 0
    assert done.stdout == ""


def test_it_speaks_when_it_acts(tmp_path):
    """L'INVERSE DU PRÉCÉDENT, et il faut les deux : une reconstruction muette
    est indiscernable de « rien n'a changé », lecture que ce dépôt refuse
    ailleurs dans les mêmes termes. Le message doit porter la ligne du
    constructeur, pas une paraphrase."""
    _plant(tmp_path, BUILDER_REBUILT)
    message = _message(_run(tmp_path, {"agent_type": "dev-mono"}))
    assert "INDEX BUILT @ abc1234" in message
    assert "0 LLM" in message


# --- fail-open sur toutes les surprises --------------------------------------

@pytest.mark.parametrize("payload", ["", "   ", "pas du json", "[]", "null", '"texte"'])
def test_a_payload_it_cannot_read_is_never_fatal(tmp_path, payload):
    """Un hook qui meurt sur une forme qu'il n'attendait pas emporte le tour
    avec lui. Toutes les surfaces advisory de ce kit échouent OUVERTES."""
    _plant(tmp_path, BUILDER_REBUILT)
    done = _run(tmp_path, payload)
    assert done.returncode == 0
    assert done.stdout == ""


def test_an_absent_builder_is_silent_not_fatal(tmp_path):
    """Chez un adoptant sans `build_index.py`, le hook ne doit rien dire et
    surtout rien casser."""
    (tmp_path / ".agents" / "bin").mkdir(parents=True, exist_ok=True)
    done = _run(tmp_path, {"agent_type": "dev-multi"})
    assert done.returncode == 0
    assert done.stdout == ""


def test_a_rebuild_behind_a_lock_notice_is_still_announced(tmp_path):
    """LE DÉFAUT QUE LES 26 PREMIERS ARMS NE VOYAIENT PAS. Mesuré sur ce dépôt :
    `build_index.py` imprime jusqu'à cinq lignes de verrou sur stdout AVANT sa
    ligne de résultat, dont celle qu'il écrit quand il VOLE un verrou fuité. Le
    `startswith` de la première rédaction les prenait pour une absence de
    reconstruction — donc le hook se taisait ALORS QU'IL AVAIT AGI, ce que son
    propre docstring interdit en toutes lettres."""
    _plant(tmp_path, BUILDER_STOLEN_LOCK)
    message = _message(_run(tmp_path, {"agent_type": "dev-mono"}))
    assert "Index rebuilt" in message
    assert "INDEX BUILT @ abc1234" in message


def test_a_skipped_rebuild_is_a_coverage_loss_and_says_so(tmp_path):
    """Deux shards d'un groupe parallèle qui rendent la main à 0,1 s, ou un
    build tué qui a fui son verrou : le second reçoit `INDEX BUILD IN FLIGHT`
    et rc=0. Se taire là laisse le shard suivant lire un index périmé sans que
    personne le sache — la fenêtre même que ce hook existe pour fermer."""
    _plant(tmp_path, BUILDER_IN_FLIGHT)
    message = _message(_run(tmp_path, {"agent_type": "dev-multi"}))
    assert "COVERAGE DEGRADED" in message
    assert "SKIPPED" in message
    assert "Index rebuilt" not in message


def test_a_builder_that_fails_announces_the_loss(tmp_path):
    """Un constructeur en panne ne doit pas produire un « Index rebuilt » — mais
    il ne doit pas se taire non plus, et c'est le cas qui appelle LE PLUS une
    action humaine (un publish de générations mêlées ne converge que sur un
    re-run). La première rédaction n'assertait qu'une ABSENCE : elle serait
    restée verte sur un hook parfaitement muet."""
    _plant(tmp_path, BUILDER_BROKEN)
    done = _run(tmp_path, {"agent_type": "dev-mono"})
    assert done.returncode == 0
    message = _message(done)
    assert "COVERAGE DEGRADED" in message
    assert "build_index.py --if-stale" in message, "le remède doit être TAPABLE"
    assert "Index rebuilt" not in message


def test_the_lock_path_still_matches_the_one_build_index_owns():
    """LE CHEMIN DU VERROU EST DUPLIQUÉ, donc il doit être ÉPINGLÉ. Le hook le
    retire lui-même après un dépassement de plafond, parce qu'un SIGKILL ne
    laisse pas `build_index.py` libérer le sien. Si ce dernier déplaçait son
    verrou, l'`unlink` deviendrait INERTE EN SILENCE et les 300 s de péremption
    reviendraient éteindre les trois points de contact."""
    source = (HERE / "build_index.py").read_text(encoding="utf-8")
    assert 'LOCK_REL = Path(".agents") / "state" / "local" / ".build_index.lock"' in source, (
        "build_index.py a deplace son verrou : le retrait du hook est devenu inerte"
    )
    hook = HOOK.read_text(encoding="utf-8")
    assert '".build_index.lock"' in hook


class _Stdin:
    def __init__(self, text: str) -> None:
        self._text = text

    def read(self) -> str:
        return self._text


def test_the_ceiling_is_announced_rather_than_silently_abandoned(
        tmp_path, monkeypatch, capsys):
    """Un plafond atteint est une COUVERTURE PERDUE, pas un succès. Sans ce
    message, un arbre froid sur lequel la reconstruction dépasse le plafond
    laisserait le shard suivant lire un index périmé sans que personne le
    sache — exactement la fenêtre que ce hook existe pour fermer.

    APPELÉ EN PROCESS, parce que le plafond est une constante du module et que
    le sous-processus la rechargerait. Et la première rédaction de cet arm
    n'assertait que `rc == 0` : elle aurait été verte sur un hook qui avale le
    dépassement EN SILENCE, c'est-à-dire sur le défaut même qu'elle garde."""
    _plant(tmp_path, BUILDER_SLOW)
    monkeypatch.setattr(dev_shard_reindex, "TIMEOUT_SECONDS", 1)
    monkeypatch.setattr("sys.stdin", _Stdin(json.dumps({"agent_type": "dev-mono"})))
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

    assert dev_shard_reindex.main() == 0
    message = json.loads(capsys.readouterr().out.strip())["systemMessage"]
    assert "COVERAGE DEGRADED" in message
    assert "build_index.py --if-stale" in message, "le remède doit être TAPABLE"
    assert "Index rebuilt" not in message, "un abandon ne s'annonce jamais en succès"


def test_it_never_exits_non_zero(tmp_path):
    """LA PROPRIÉTÉ QUI TIENT TOUTES LES AUTRES. Ce hook est advisory : le jour
    où il rend autre chose que 0, il devient une garde que personne n'a
    décidée."""
    for builder in (BUILDER_REBUILT, BUILDER_CURRENT, BUILDER_BROKEN):
        _plant(tmp_path, builder)
        for payload in ({"agent_type": "dev-mono"}, {"agent_type": "planner"}, "casse"):
            assert _run(tmp_path, payload).returncode == 0
