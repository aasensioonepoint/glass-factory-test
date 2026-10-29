"""T-00000801, binôme de clôture de la fournée 9 — CE QUE LE git DU FILTRE ET DU HOOK CONSOMMENT ENCORE (F1, F2, F6).

(F1) LA TRACE GIT. Le git du filtre `safe.directory` du préfixe des jambes Claude tourne sous `exec env -i` : il ne reçoit QUE
PATH, `GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL=/dev/null` et les deux canaux (`GIT_CONFIG_PARAMETERS`, `GIT_CONFIG_COUNT`,
clés et valeurs 0..7) — une liste BLANCHE. La forme d'avant (rév. 9 fusionnée par ad18ef0d : `unset GIT_CONFIG` puis
`exec git`) héritait de `GIT_TRACE*` : P ou C posé, un FIFO sans lecteur désigné par `GIT_TRACE` ou `GIT_TRACE2` faisait PENDRE
la jambe (safe-bash `rm AGENTS.md` : refus rc 2 → pendaison, mesuré sous /bin/sh, bash-en-sh et dash), et un fichier ordinaire
recevait la trace (git 2.55 : `GIT_TRACE` 106 octets, `GIT_TRACE_PERFORMANCE` 187, `GIT_TRACE2` 605, `GIT_TRACE2_EVENT` 1310,
`GIT_TRACE2_PERF` 1044). Témoins : (i) sous un FIFO de trace, la jambe safe-bash REFUSE `rm AGENTS.md` dans un délai borné ;
(iii) le fichier de trace désigné reste VIDE — joué sur le PRÉFIXE SEUL (sonde `exec cat`, qui ne lance aucun git), parce que
le hook lui-même écrit la trace : pour `rm AGENTS.md`, `events.py` (attribution du `hook.deny`) lance `git config user.name`
sous le `gtimeout` d'un étage Python (mesuré : 78 octets sans P ni C ; sous un FIFO, coupé par ce délai d'étage, rc 2 tenu).
C'est le git d'un HOOK, hors de ce fichier (relevé NON CLOS). Contrôle de (iii) : sans P ni C, rien ne s'écrit.
(F2) LA BORNE DE L'ÉCRAN. `GIT_CONFIG_COUNT=8` et `GIT_CONFIG_KEY_7=include.path` vers un FIFO : l'écran lit la clé 7, git n'est
pas lancé, rien ne pend (ii). Le filet `test_hook_env_hardening.py` ne jouait aucun décompte 8 : retirer `${GIT_CONFIG_KEY_7-}`
de l'écran y restait vert hors des épingles de texte (mesuré par la critique A).
(F6) LE STDIN DU HOOK. `post-task-done-index.sh` lance un git (`rev-parse` de la racine, hors `CLAUDE_PROJECT_DIR`) AVANT de
lire sa charge ; sans `</dev/null` dans `git_hote`, une config globale qui inclut `/dev/stdin` faisait avaler la charge par ce
git — `grep` échouait, sortie 0, stores non commités, sans un mot (Codex, Copilot, Kimi : pas de préfixe). Témoin : la charge
reste intacte, les stores sont commités.

LA PENDAISON EST CONFIRMÉE, JAMAIS SUPPOSÉE. Une cellule qui dépasse son délai reçoit un LIBÉRATEUR branché sur le FIFO
(un lecteur pour une trace que git veut écrire, un écrivain pour un include que git veut lire) ; chaque ouverture par la jambe
est COMPTÉE puis libérée. Une ouverture comptée = violation (le FIFO était atteint) ; une jambe que le libérateur ne libère
pas = pendaison hors du FIFO, violation aussi ; une jambe seulement LENTE, qui finit sans rien ouvrir, n'est pas un rouge.

MUTANTS (chacun doit rougir) : le filtre d'AVANT la correction (i, iii) ; `${GIT_CONFIG_KEY_7-}` retiré de l'écran (ii) ;
`</dev/null` retiré de `git_hote` (F6). Les mutants de la liste blanche elle-même (`-i` retiré, GLOBAL/SYSTEM hérités, clé 8
transmise) sont dans `test_hook_env_hardening.py` (F14, F15, F17, F18).

HARNAIS IMPORTÉ, jamais recopié : banc, enveloppes, préfixe et `est_refus` de `test_hook_env_hardening.py` ; dépôt jetable,
jambe externe et issue attendue de `test_post_task_done_git_shield.py`. `HOOK_HARDENING_SETTINGS` y est honoré de même.

BORNES, écrites : darwin mesuré (git 2.55 ; /bin/sh = bash 3.2, bash >= 4 lié `sh`, /bin/dash) ; Linux lu. Ce fichier tient le
git du FILTRE et `git_hote` ; les git des HOOKS eux-mêmes lisent encore `GIT_TRACE*` (relevé NON CLOS du SKILL guardrails).
"""
from __future__ import annotations

import os

import pytest

if os.name == "nt":
    pytest.skip("filet POSIX : enveloppes /bin/sh et dash, FIFO (dette CI Windows T-00000744)", allow_module_level=True)

import json  # noqa: E402
import signal  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402
import threading  # noqa: E402
import warnings  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_hook_env_hardening as H  # noqa: E402 — banc, enveloppes, préfixe : importés, jamais recopiés
import test_post_task_done_git_shield as S  # noqa: E402 — dépôt jetable et jambe externe du hook

#: Délai d'une cellule saine : large (la jambe safe-bash `rm AGENTS.md` prend ≈ 2,4 s sur darwin) ; une jambe lente n'est pas
#: un rouge (voir le libérateur). Délai d'un MUTANT : court — un mutant pend sans fin, le délai ne fait que séparer.
DELAI = 60.0
DELAI_MUTANT = 8.0
#: (i) les deux noms de la critique ; (iii) les cinq qui, mesurés sous git 2.55, faisaient écrire le git du filtre.
TRACES_FIFO = ("GIT_TRACE", "GIT_TRACE2")
TRACES_FICHIER = ("GIT_TRACE", "GIT_TRACE_PERFORMANCE", "GIT_TRACE2", "GIT_TRACE2_EVENT", "GIT_TRACE2_PERF")
CHARGE_REFUS = H._sb("rm AGENTS.md")
CANAUX = {"P": dict(H.SAFE_P),
          "C": {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "safe.directory", "GIT_CONFIG_VALUE_0": "/c"},
          "aucun (contrôle)": {}}
#: F2 : huit entrées, sept `safe.directory` puis la clé 7 qui inclut le FIFO (`@F@`).
HUIT_CLE_7 = {"GIT_CONFIG_COUNT": "8", **{f"GIT_CONFIG_KEY_{i}": "safe.directory" for i in range(7)},
              **{f"GIT_CONFIG_VALUE_{i}": f"/v{i}" for i in range(7)},
              "GIT_CONFIG_KEY_7": "include.path", "GIT_CONFIG_VALUE_7": "@F@"}
#: Le lancement du git du filtre AVANT la correction (rév. 9 fusionnée par ad18ef0d), embarqué en littéral pour le mutant.
LANCEMENT_AVANT = "(unset GIT_CONFIG; GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null exec git "
ECRAN_K7 = "${GIT_CONFIG_KEY_6-}${GIT_CONFIG_KEY_7-}"
STDIN_HOTE = ('"$@" </dev/null', '"$@"')


# ---------------------------------------------------------------------------
# LE FILTRE, ET SES DEUX MUTANTS
# ---------------------------------------------------------------------------
def filtre_avant() -> str:
    """Le filtre de la rév. 9 telle que fusionnée : le lancement `env -i … git ` remplacé par l'ancien, le reste intact."""
    f = H.FILTRE_LIT
    assert f.count("(exec env -i ") == 1, "ancre `(exec env -i ` absente du filtre : mutant impossible"
    debut = f.index("(exec env -i ")
    fin = f.index(" git -c core.fsmonitor=false", debut) + len(" git ")
    return f[:debut] + LANCEMENT_AVANT + f[fin:]


def filtre_sans_cle_7() -> str:
    assert H.FILTRE_LIT.count(ECRAN_K7) == 1, f"ancre {ECRAN_K7!r} : {H.FILTRE_LIT.count(ECRAN_K7)} occurrence(s)"
    return H.FILTRE_LIT.replace(ECRAN_K7, "${GIT_CONFIG_KEY_6-}", 1)


def jambe(b: H.Banc, filtre: str) -> str:
    """La jambe safe-bash LUE dans les réglages, son préfixe refait avec `filtre`. Préfixe absent : ÉCHEC (témoin vide)."""
    lue = b.jambes.get("safe-bash", "")
    if not lue.startswith(H.PREFIX):
        pytest.fail("jambe safe-bash sans le préfixe attendu : ce témoin jouerait une autre forme (voir test_legs_text_rule)")
    return lue.replace(H.PREFIX, H.faire_prefixe(filtre=filtre), 1)


# ---------------------------------------------------------------------------
# LA CELLULE BORNÉE, ET SON LIBÉRATEUR
# ---------------------------------------------------------------------------
class Liberateur:
    """Branché APRÈS le délai sur un FIFO, côté `lecteur` (une trace que git veut écrire) ou `ecrivain` (un include que git
    veut lire) : chaque ouverture par l'autre bout est COMPTÉE puis libérée (lue jusqu'à EOF, ou EOF donné)."""

    def __init__(self, chemin: Path, cote: str):
        self.chemin, self.cote, self.n, self.stop = chemin, cote, 0, False
        self.fil = threading.Thread(target=self._boucle, daemon=True)
        self.fil.start()

    def _boucle(self):
        drapeau = os.O_RDONLY if self.cote == "lecteur" else os.O_WRONLY
        while True:
            fd = os.open(self.chemin, drapeau)
            if self.stop:
                os.close(fd)
                return
            self.n += 1
            if self.cote == "lecteur":
                while os.read(fd, 65536):
                    pass
            os.close(fd)

    def clore(self) -> int:
        n, self.stop = self.n, True
        inverse = (os.O_WRONLY if self.cote == "lecteur" else os.O_RDONLY) | os.O_NONBLOCK
        for _ in range(50):
            try:
                fd = os.open(self.chemin, inverse)
            except OSError:  # ENXIO : le fil est entre deux ouvertures — on réessaie
                self.fil.join(0.1)
                continue
            self.fil.join(0.1)
            os.close(fd)
            if not self.fil.is_alive():
                break
        return n


def _tuer(p: subprocess.Popen):
    try:
        os.killpg(p.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def jouer_borne(a0: str, cmd: str, charge: str, env: dict, cwd: Path, fifo: Path | None = None, cote: str = "lecteur",
                delai: float = DELAI) -> tuple[subprocess.CompletedProcess, str | None]:
    """Joue la jambe dans sa PROPRE session (un git pendu est tué avec elle). Rend le processus et la pendaison CONSTATÉE
    (None = aucune). Au délai : un libérateur sur `fifo` ; ouverture comptée ou jambe non libérée = pendaison."""
    p = subprocess.Popen([a0, "-c", cmd], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                         encoding="utf-8", errors="replace", env=env, cwd=str(cwd), start_new_session=True)
    try:
        out, err = p.communicate(charge, timeout=delai)
        return subprocess.CompletedProcess(p.args, p.returncode, out, err), None
    except subprocess.TimeoutExpired:
        pass
    lib = Liberateur(fifo, cote) if fifo else None
    try:
        out, err = p.communicate(timeout=DELAI)
        liberee = True
    except subprocess.TimeoutExpired:
        _tuer(p)
        out, err = p.communicate()
        liberee = False
    n = lib.clore() if lib else 0
    fini = subprocess.CompletedProcess(p.args, p.returncode, out, err)
    if n:
        return fini, (f"PENDAISON sur le FIFO (> {delai:.0f} s) : {n} ouverture(s) par la jambe une fois un {cote} branché, "
                      f"jambe {'libérée' if liberee else 'toujours pendue'}")
    if not liberee:
        return fini, f"PENDAISON hors du FIFO (> {delai + DELAI:.0f} s)"
    warnings.warn(f"jambe lente (> {delai:.0f} s) mais aucune ouverture du FIFO : pas un rouge")
    return fini, None


def _refuse(p: subprocess.CompletedProcess) -> bool:
    return H.est_refus(p)


def _fifo(b: H.Banc, prefixe: str) -> Path:
    chemin = Path(tempfile.mkdtemp(prefix=prefixe, dir=b.base)) / "fifo"
    os.mkfifo(chemin)
    return chemin


# ---------------------------------------------------------------------------
# LES TROIS TÉMOINS
# ---------------------------------------------------------------------------
def violations_trace_fifo(b: H.Banc, a0: str, filtre: str, premier=False, delai=DELAI) -> list[str]:
    """(i) GIT_TRACE / GIT_TRACE2 vers un FIFO sans lecteur, P, C ou aucun canal : la jambe refuse, sans ouvrir le FIFO."""
    cmd, v = jambe(b, filtre), []
    for var in TRACES_FIFO:
        for canal, pose in CANAUX.items():
            fifo = _fifo(b, "tr-")
            p, pendu = jouer_borne(a0, cmd, CHARGE_REFUS, b.env(b.clone, {var: str(fifo), **pose}), b.clone, fifo, "lecteur", delai)
            if pendu:
                v.append(f"{var}=FIFO + {canal} : {pendu}")
            elif not _refuse(p):
                v.append(f"{var}=FIFO + {canal} : rc {p.returncode}, stderr {p.stderr[:70]!r} (refus attendu)")
            if v and premier:
                return v
    return v


def violations_trace_fichier(b: H.Banc, a0: str, filtre: str, premier=False) -> list[str]:
    """(iii) les cinq GIT_TRACE* vers cinq fichiers ordinaires, P, C ou aucun canal, PRÉFIXE SEUL (sonde `exec cat` : le seul git
    lancé est celui du filtre) : la charge traverse intacte, les cinq fichiers restent VIDES."""
    cmd, v = H.faire_prefixe(filtre=filtre) + H.SONDE_LECTURE, []
    for canal, pose in CANAUX.items():
        rep = Path(tempfile.mkdtemp(prefix="tf-", dir=b.base))
        cibles = {var: rep / var for var in TRACES_FICHIER}
        for c in cibles.values():
            c.write_text("")
        env = b.env(b.clone, {**{k: str(c) for k, c in cibles.items()}, **pose})
        p, pendu = jouer_borne(a0, cmd, H.CHARGE_LECTURE, env, b.clone)
        ecrits = {var: c.stat().st_size for var, c in cibles.items() if c.stat().st_size}
        if pendu or p.stdout != H.CHARGE_LECTURE:
            v.append(f"traces=fichiers + {canal} : {pendu or f'charge reçue {p.stdout[:50]!r}, rc {p.returncode}'}")
        if ecrits and canal.startswith("aucun"):
            v.append(f"CONTRÔLE : sans P ni C le préfixe seul écrit la trace {ecrits} — la sonde ou l'enveloppe lance git, "
                     "le témoin ne vise plus le filtre")
        elif ecrits:
            v.append(f"traces=fichiers + {canal} : trace ÉCRITE par le git du filtre (octets {ecrits})")
        if v and premier:
            return v
    return v


def violations_cle_7(b: H.Banc, a0: str, filtre: str, delai=DELAI) -> list[str]:
    """(ii) décompte 8, clé 7 `include.path` vers un FIFO sans écrivain : la jambe refuse, sans ouvrir le FIFO."""
    fifo = _fifo(b, "k7-")
    pose = {k: x.replace("@F@", str(fifo)) for k, x in HUIT_CLE_7.items()}
    p, pendu = jouer_borne(a0, jambe(b, filtre), CHARGE_REFUS, b.env(b.clone, pose), b.clone, fifo, "ecrivain", delai)
    if pendu:
        return [f"C décompte 8, clé 7 include=FIFO : {pendu}"]
    return [] if _refuse(p) else [f"C décompte 8, clé 7 include=FIFO : rc {p.returncode}, stderr {p.stderr[:70]!r}"]


def violations_stdin_hook(base: Path, hook_texte: str | None = None) -> list[str]:
    """(F6) jambe externe du hook SANS `CLAUDE_PROJECT_DIR` (le `rev-parse` de la racine passe AVANT le `cat` de la charge),
    config globale qui inclut `/dev/stdin` : la charge doit survivre et les stores être commités."""
    d = S.Depot(base, "normal", hook_texte)
    inclut = S.ecrire(base / "gconf-stdin", S.SANS_MAINTENANCE + "[include]\n\tpath = /dev/stdin\n")
    sortie = S.FLUX_FN["sans-racine"](d, d.env({"GIT_CONFIG_GLOBAL": str(inclut)}))
    return S.issue_attendue("sans-racine", sortie)


# ---------------------------------------------------------------------------
# FIXTURE ET TESTS
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def banc(tmp_path_factory):
    chemin, v = H.choix_reglages(os.environ)
    if v:
        pytest.fail("; ".join(v))
    base = tmp_path_factory.mktemp("trace801")
    env = H.decouvrir(os.environ.get("PATH", ""), "/bin/dash", H.EST_LE_KIT, os.environ.get("CI") == "true", base)
    return H.Banc(base, json.loads(chemin.read_text(encoding="utf-8")), env)


@pytest.mark.parametrize("nom", H.ENVELOPPES_POSIX)
def test_trace_fifo_leaves_guard_refusing(nom, banc):
    """(i) F1 : un FIFO de trace ne fait plus pendre la jambe safe-bash, et elle refuse encore `rm AGENTS.md`."""
    a0 = H.exiger(banc.enveloppes[nom])
    v = violations_trace_fifo(banc, a0, H.FILTRE_LIT)
    assert not v, "\n".join(v)


@pytest.mark.parametrize("nom", H.ENVELOPPES_POSIX)
def test_trace_file_stays_empty(nom, banc):
    """(iii) F1 : le fichier désigné par chaque GIT_TRACE* reste vide — le git du filtre n'écrit plus de trace."""
    a0 = H.exiger(banc.enveloppes[nom])
    v = violations_trace_fichier(banc, a0, H.FILTRE_LIT)
    assert not v, "\n".join(v)


@pytest.mark.parametrize("nom", H.ENVELOPPES_POSIX)
def test_screen_reads_key_7(nom, banc):
    """(ii) F2 : la huitième clé (KEY_7) est lue par l'écran — un include qu'elle porte ne lance pas git."""
    a0 = H.exiger(banc.enveloppes[nom])
    v = violations_cle_7(banc, a0, H.FILTRE_LIT)
    assert not v, "\n".join(v)


@pytest.mark.parametrize("nom", H.ENVELOPPES_POSIX)
def test_mutations_are_killed(nom, banc):
    """Chaque témoin PEUT rougir : le filtre d'avant la correction (i, iii) et l'écran sans KEY_7 (ii), par délai ET ouverture."""
    a0 = H.exiger(banc.enveloppes[nom])
    survivants = []
    if not violations_trace_fifo(banc, a0, filtre_avant(), premier=True, delai=DELAI_MUTANT):
        survivants.append("filtre d'avant la correction (i, FIFO de trace)")
    if not violations_trace_fichier(banc, a0, filtre_avant(), premier=True):
        survivants.append("filtre d'avant la correction (iii, fichier de trace)")
    if not violations_cle_7(banc, a0, filtre_sans_cle_7(), delai=DELAI_MUTANT):
        survivants.append("KEY_7 retiré de l'écran (ii)")
    assert not survivants, "mutants survivants :\n" + "\n".join(survivants)


def test_hook_payload_survives_stdin_include(tmp_path):
    """(F6) `git_hote` ferme stdin : une config globale qui inclut `/dev/stdin` n'avale plus la charge du hook."""
    v = violations_stdin_hook(tmp_path)
    assert not v, "\n".join(v)


def test_hook_stdin_mutant_killed(tmp_path):
    """(F6) mutant : `</dev/null` retiré de `git_hote` — la charge est avalée, les stores ne sont pas commités."""
    texte = S.muter(S.HOOK_VIVANT.read_text(encoding="utf-8"), *STDIN_HOTE)
    assert violations_stdin_hook(tmp_path, texte), "mutant « </dev/null retiré de git_hote » survit : témoin F6 vide"
