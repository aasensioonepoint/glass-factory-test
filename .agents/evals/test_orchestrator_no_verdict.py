"""Le security-orchestrator ne lit summary.json que sur le verdict de SON run (F3).

T-01M5398WBYGCPKDBE3VF9W9C1D, lot B de T-01M51RFFECAFAAR0CM3NR1GYEC (plan, étapes 6 et 8 ;
réserves C11 et C15 du critique de plan, itération 2/8).

MESURÉ avant ce lot : en mode audit, la déf lisait `modules/summary.json` sans condition après
`sca-scan.sh --all-modules`. Un run au verrou occupé, coupé ou hors délai laisse le summary d'un run
ANTÉRIEUR, lu comme celui du jour. Et un TERM envoyé au seul parent laisse en DERNIÈRE ligne celle
d'un MODULE, `SCA GATE (effective, waivers applied): GO`, à un mot de la ligne du run (C11, mesuré
sous bash 3.2 et 5.3 par le critique).

CE QUE CE BANC PROUVE, par un comportement et pas seulement par la présence d'un texte :
  (1) la table de décision ÉCRITE dans chacune des 5 défs et dans chaque rendu résolu du roster
      (``rc=<n> + `<ligne>` → <issue>``) est extraite, puis JOUÉE : toute fin qui n'est pas l'une
      de ses quatre paires EXACTES rend NO-GO — la ligne d'un module, le verrou occupé, une ligne
      en retrait, un rc en désaccord avec la ligne, l'absence de `rc=` ;
  (2) ces quatre paires sont celles que `sca-scan.sh` émet VRAIMENT : chaque ligne y est cherchée au
      mot près, avec le `exit` qui la suit ; le jour où le scanner change sa fin, ce banc rougit ;
  (3) la commande de lecture écrite dans les défs, jouée par bash sur un FAUX `sca-scan.sh`, rend au
      plus deux lignes (`rc=<n>`, puis la dernière ligne du journal), même après 20 000 lignes de
      sortie et sur un arbre où le répertoire des rapports n'existe pas encore ; un TERM envoyé au
      seul faux scanner y rend `rc=143` suivi de la ligne du module, que (1) rejette. Le journal est
      un `mktemp` PAR RUN (revue de clôture du lot e47f77cc..bbf26b6f) : deux audits concurrents
      lisent chacun SA fin — MESURÉ sous l'ancien nom fixe `last-audit-scan.log`, le run lent
      lisait la dernière ligne du run rapide ;
  (4) un module dont l'entrée de summary dit `"verdict": "ERROR"` n'a obtenu AUCUN verdict : chaque
      déf et chaque rendu le disent, et `sca-scan.sh` écrit bien ce verdict et ses
      `degraded_reasons` — le jour où le scanner les renomme, ce banc rougit.
BORNES : le comportement du LLM au runtime n'est pas mesuré — ce banc prouve la règle écrite et la
commande, jamais qu'un modèle les suit. La Phase 2 (run nu lancé par les spécialistes) n'est
qu'ÉPINGLÉE en texte, avec sa borne écrite dans la déf : les formats de sortie des spécialistes ne
rendent ni le rc ni la dernière ligne de leur run.
"""

from __future__ import annotations

import functools
import importlib.util
import os
import re
import shutil
import subprocess
import time
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# adopting-tree: le marqueur d'identite du kit ne voyage pas (strip: .agents/IS_THE_KIT) ;
# son absence EST le signal « projet adoptant » : le banc y saute en l'annoncant.
EST_LE_KIT = (ROOT / ".agents" / "IS_THE_KIT").is_file()
pytestmark = pytest.mark.skipif(
    not EST_LE_KIT,
    reason="SAUT ANNONCE : marqueur `.agents/IS_THE_KIT` absent (projet adoptant) — "
           "la regle de fin de run du security-orchestrator n'est jugee que dans le kit",
)

NOM = "security-orchestrator"
DEFS = {
    "claude": ".claude/agents/security-orchestrator.md",
    "codex": ".codex/agents/security-orchestrator.toml",
    "gemini": ".gemini/agents/security-orchestrator.md",
    "copilot": ".github/agents/security-orchestrator.agent.md",
    "kimi": ".kimi-code/agents/security-orchestrator.md",
}
SOURCES = [*DEFS.values(), *(f"roster/{h}" for h in DEFS)]
SCA_SCAN = ROOT / ".agents" / "security" / "sca-scan.sh"

# La commande de lecture, telle que chaque déf l'écrit. Le banc joue CETTE constante, jamais un
# texte lu dans un fichier : l'égalité avec chaque déf est vérifiée à part (test_la_commande_…).
COMMANDE = (
    "mkdir -p .agents/state/local/sca-reports && "
    "L=$(mktemp .agents/state/local/sca-reports/last-audit-scan.XXXXXX) && "
    "bash .agents/security/sca-scan.sh --all-modules > \"$L\" 2>&1; echo \"rc=$?\"; tail -n 1 \"$L\""
)
COMMANDE_RE = re.compile(r"`(mkdir -p [^`\n]*?tail -n 1 [^`\n]*)`")
PAIRE_RE = re.compile(r"rc=(\d+) \+ `([^`\n]+)` → (consolidate|DEGRADED|NO-ECOSYSTEM)\b")


@functools.lru_cache(maxsize=None)
def texte(source: str) -> str:
    """Une déf vivante, ou le corps RÉSOLU de son rendu au roster (`roster/<hôte>`)."""
    if not source.startswith("roster/"):
        return (ROOT / source).read_text(encoding="utf-8")
    # Le paquet que `vendor_paths` designe (patron v3prep, T-01M5BXTPQE3JZV3KZA6WD9P5XC) :
    # charge PAR CHEMIN, `sys.path` intact.
    spec = importlib.util.spec_from_file_location(
        "_orchestrator_no_verdict_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
    assert spec is not None and spec.loader is not None
    vendor = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = vendor
    spec.loader.exec_module(vendor)
    vendor.charger_paquet(ROOT, "cadre")
    from cadre import roster  # noqa: E402
    from cadre.config import HOTES  # noqa: E402

    assert set(HOTES) == set(DEFS), f"les hotes du roster ont change : {HOTES} contre {sorted(DEFS)}"
    definition = roster.charger().definition(NOM)
    return "\n".join(roster.corps_de(definition, source.split("/", 1)[1]))


def table(contenu: str) -> dict[tuple[int, str], str]:
    paires: dict[tuple[int, str], str] = {}
    for m in PAIRE_RE.finditer(contenu):
        cle = (int(m.group(1)), m.group(2))
        assert cle not in paires, f"paire ecrite deux fois : {cle}"
        paires[cle] = m.group(3)
    return paires


def decider(paires: dict[tuple[int, str], str], rc: int | None, ligne: str | None) -> str:
    """La règle écrite, jouée : égalité de la ligne ENTIÈRE et du rc, sinon NO-GO."""
    if rc is None or ligne is None:
        return "NO-GO"
    return paires.get((rc, ligne), "NO-GO")


@functools.lru_cache(maxsize=None)
def scanner() -> dict[str, object]:
    """Les lignes de fin que `sca-scan.sh` émet vraiment, et le rc de chacune."""
    script = SCA_SCAN.read_text(encoding="utf-8")
    lignes = script.splitlines()

    def exit_apres(echo: str) -> str:
        sites = [i for i, l in enumerate(lignes) if echo in l]
        assert len(sites) == 1, f"sca-scan.sh : {echo!r} attendu une fois, vu aux lignes {sites}"
        i = sites[0]
        meme = re.search(r";\s*exit (\S+?);?\s*\}?$", lignes[i][lignes[i].index(echo):])
        if meme:
            return meme.group(1)
        for suite in lignes[i + 1:]:
            if suite.strip().startswith("exit "):
                return suite.strip().split()[1]
        raise AssertionError(f"sca-scan.sh : aucun exit apres {echo!r}")

    run = "SCA GATE all-modules (effective, waivers applied): "
    module = "SCA GATE (effective, waivers applied): "
    assert exit_apres(f'echo "{run}$verdict"') == '"$global"'
    assert 'verdict="GO"; [ "$global" -eq 1 ] && verdict="NO-GO"' in script
    deg = f"{run}GO (DEGRADED — no effective verdict)"
    eco = "SCA: no known ecosystem detected in any module."
    lock = "SCA: reports lock held by live pid ${o_pid} — re-run when it ends; do not remove the lock"
    assert f'log "{lock}"' in script, "sca-scan.sh : la ligne du verrou occupe a change"
    assert "log()  { printf '  %s\\n' \"$*\"; }" in script, "sca-scan.sh : log() ne met plus de retrait"
    return {
        "all_go": f"{run}GO", "all_nogo": f"{run}NO-GO", "all_deg": deg, "no_eco": eco,
        "rc_deg": int(exit_apres(f'echo "{deg}"')), "rc_eco": int(exit_apres(f'echo "{eco}"')),
        "mod_go": f"{module}GO", "mod_nogo": f"{module}NO-GO",
        "rc_mod_go": int(exit_apres(f'echo "{module}GO"')),
        "lock": "  " + lock.replace("${o_pid}", "4242"),
    }


def attendu() -> dict[tuple[int, str], str]:
    s = scanner()
    return {(0, s["all_go"]): "consolidate", (1, s["all_nogo"]): "consolidate",
            (s["rc_deg"], s["all_deg"]): "DEGRADED", (s["rc_eco"], s["no_eco"]): "NO-ECOSYSTEM"}


# (libellé, rc, ligne(scanner), issue attendue)
CAS = [
    ("verdict GO du run", lambda s: 0, lambda s: s["all_go"], "consolidate"),
    ("verdict NO-GO du run", lambda s: 1, lambda s: s["all_nogo"], "consolidate"),
    ("python absent", lambda s: s["rc_deg"], lambda s: s["all_deg"], "DEGRADED"),
    ("aucun ecosysteme", lambda s: s["rc_eco"], lambda s: s["no_eco"], "NO-ECOSYSTEM"),
    ("TERM au seul parent (C11)", lambda s: 143, lambda s: s["mod_go"], "NO-GO"),
    ("ligne GO d'un module, rc du module", lambda s: s["rc_mod_go"], lambda s: s["mod_go"], "NO-GO"),
    ("ligne NO-GO d'un module", lambda s: 1, lambda s: s["mod_nogo"], "NO-GO"),
    ("verrou occupe", lambda s: 1, lambda s: s["lock"], "NO-GO"),
    ("ligne du run en retrait", lambda s: 1, lambda s: "  " + s["all_nogo"], "NO-GO"),
    ("ligne du run avec un reste", lambda s: 0, lambda s: s["all_go"] + " — module x", "NO-GO"),
    ("rc 1 sous une ligne GO", lambda s: 1, lambda s: s["all_go"], "NO-GO"),
    ("rc 0 sous une ligne NO-GO", lambda s: 0, lambda s: s["all_nogo"], "NO-GO"),
    ("aucun ecosysteme sous rc 0", lambda s: 0, lambda s: s["no_eco"], "NO-GO"),
    ("KILL", lambda s: 137, lambda s: s["mod_go"], "NO-GO"),
    ("journal vide", lambda s: 0, lambda s: "", "NO-GO"),
    ("sortie coupee : ni rc ni ligne", lambda s: None, lambda s: None, "NO-GO"),
]


@pytest.mark.parametrize("source", SOURCES)
def test_la_table_ecrite_est_celle_que_le_scanner_emet(source):
    assert table(texte(source)) == attendu(), (
        f"{source} : la table `rc=<n> + `<ligne>` → <issue>` ne porte plus EXACTEMENT les quatre "
        "fins que sca-scan.sh --all-modules emet. Restaure la phrase dans "
        "`agents/<nom>.md` (puis `render_hosts.py --ecrire`), n'amende pas ce banc."
    )


@pytest.mark.parametrize("source", SOURCES)
@pytest.mark.parametrize("libelle, rc, ligne, issue", CAS, ids=[c[0] for c in CAS])
def test_la_regle_ecrite_jouee_sur_chaque_fin(source, libelle, rc, ligne, issue):
    s = scanner()
    vu = decider(table(texte(source)), rc(s), ligne(s))
    assert vu == issue, f"{source} — {libelle} : la regle ecrite rend {vu}, attendu {issue}"


@pytest.mark.parametrize("source", SOURCES)
def test_la_commande_de_lecture_est_la_meme_partout(source):
    assert COMMANDE_RE.findall(texte(source)) == [COMMANDE], (
        f"{source} : la commande qui lit le rc et la DERNIERE ligne depuis un fichier a change "
        "ou manque (C11 : une sortie coupee par l'hote ne doit pas decider du verdict)"
    )


def est_copilot(source: str) -> bool:
    """La forme d'une ligne par consigne (`.github`) : même règle, phrasé adapté."""
    return source in (DEFS["copilot"], "roster/copilot")


@pytest.mark.parametrize("source", SOURCES)
def test_la_ligne_d_un_module_n_est_jamais_le_verdict_du_run(source):
    contenu = re.sub(r"\s+", " ", texte(source))
    exact = "WHOLE last line compared EXACTLY" if est_copilot(source) else "the WHOLE line compared EXACTLY"
    for phrase in ("`SCA GATE (effective, waivers applied): …` WITHOUT `all-modules` is a "
                   "MODULE's line, never the run's verdict", exact, "an EARLIER run's"):
        assert phrase in contenu, f"{source} : phrase absente : {phrase!r}"


@pytest.mark.parametrize("source", SOURCES)
def test_phase2_le_pivot_du_run_nu_porte_sa_condition_et_sa_borne(source):
    contenu = re.sub(r"\s+", " ", texte(source))
    phrases = ["WHOLE last line exactly `SCA GATE (effective, waivers applied): GO`",
               "(a lock-busy run writes none)"]
    if not est_copilot(source):
        # Copilot lance le scan lui-même : il tient son rc, la borne des spécialistes ne le vise pas.
        phrases.append("output formats name neither the rc nor the last line of their run")
    for phrase in phrases:
        assert phrase in contenu, f"{source} : phrase absente : {phrase!r}"


# --- (4) un module ERROR n'a obtenu aucun verdict ---------------------------------------------

# (phrase écrite dans chaque déf et chaque rendu, espaces normalisés)
MODULE_ERROR = (
    "A module whose summary entry reads `\"verdict\": \"ERROR\"` obtained NO verdict",
    "its `effective-verdict.json` is NEVER read nor cited",
    "AUDIT-GAPS carries `SCA module <slug>: no verdict obtained (<degraded_reasons>)`",
)


@pytest.mark.parametrize("source", SOURCES)
@pytest.mark.parametrize("phrase", MODULE_ERROR)
def test_un_module_error_n_a_obtenu_aucun_verdict(source, phrase):
    assert phrase in re.sub(r"\s+", " ", texte(source)), f"{source} : phrase absente : {phrase!r}"


AUDIT_SURFACES = (".claude/commands/audit.md", ".agents/skills/audit/SKILL.md")


@pytest.mark.parametrize("surface", AUDIT_SURFACES)
def test_audit_delegue_la_commande_et_dit_l_absence_de_verdict(surface):
    """/audit ne dicte pas une commande NUE (sans journal ni dernière ligne) à l'orchestrateur, et ne
    remplace jamais « no verdict obtained » par le global_verdict d'un summary.json antérieur."""
    contenu = re.sub(r"\s+", " ", (ROOT / surface).read_text(encoding="utf-8"))
    assert "`bash .agents/security/sca-scan.sh --all-modules`" not in contenu, f"{surface} : commande nue"
    for phrase in ("its audit-mode command (the run's end read from the last-audit-scan log, rc + whole "
                   "last line)","said « no verdict obtained », print that, never summary.json's global_verdict"):
        assert phrase in contenu, f"{surface} : phrase absente : {phrase!r}"


def test_le_scanner_ecrit_le_verdict_error_et_ses_raisons():
    script = SCA_SCAN.read_text(encoding="utf-8")
    for ancre in ('verdict = "ERROR"', '"verdict": verdict,', '"degraded_reasons": reasons',
                  'reasons.append(f"module run exited rc={rc} — no verdict obtained")'):
        assert ancre in script, f"sca-scan.sh : {ancre!r} absent — la phrase (4) des defs ne dit plus vrai"


# --- (3) la commande, jouée par bash sur un faux scanner ---------------------------------------

STUBS = {
    "GO apres 20000 lignes, arbre sans repertoire de rapports":
        ('cat "$(dirname "$0")/bruit.txt"\nprintf \'%s\\n\' \'{all_go}\'\nexit 0\n',
         0, "all_go", "consolidate"),
    "TERM au seul scanner apres la ligne d'un module":
        ("printf '%s\\n' '== module sub (sub, submodules=0) =='\nprintf '%s\\n' '{mod_go}'\n"
         "kill -TERM $$\nsleep 5\nprintf '%s\\n' '{all_go}'\n", 143, "mod_go", "NO-GO"),
    "verrou occupe":
        ("printf '%s\\n' '{lock}'\nexit 1\n", 1, "lock", "NO-GO"),
    "KILL avant toute sortie":
        ("kill -KILL $$\n", 137, None, "NO-GO"),
}


def lire_fin(sortie: str) -> tuple[int | None, str | None]:
    lignes = sortie.split("\n")
    if lignes and lignes[-1] == "":
        lignes.pop()
    assert len(lignes) <= 2, f"la commande rend {len(lignes)} lignes, au plus 2 attendues"
    m = re.fullmatch(r"rc=(\d+)", lignes[0]) if lignes else None
    return (int(m.group(1)) if m else None), (lignes[1] if len(lignes) == 2 else None)


@pytest.mark.skipif(shutil.which("bash") is None, reason="SAUT ANNONCE : bash introuvable")
@pytest.mark.parametrize("scenario", list(STUBS))
def test_la_commande_rend_le_rc_et_la_derniere_ligne(tmp_path, scenario):
    corps, rc_attendu, cle, issue = STUBS[scenario]
    s = scanner()
    valeurs = {k: v for k, v in s.items() if isinstance(v, str)}
    assert all("'" not in v for v in valeurs.values())
    stub = tmp_path / ".agents" / "security" / "sca-scan.sh"
    stub.parent.mkdir(parents=True)
    # write_bytes : LF partout — write_text mettrait du CRLF sous Windows, et bash lirait `exit 0\r`.
    stub.write_bytes(corps.format(**valeurs).encode("utf-8"))
    (stub.parent / "bruit.txt").write_bytes(
        "".join(f"  bruit {i}\n" for i in range(20000)).encode("utf-8"))
    assert not (tmp_path / ".agents" / "state").exists()

    fini = subprocess.run(["bash", "-c", COMMANDE], cwd=tmp_path, capture_output=True,
                          text=True, encoding="utf-8", timeout=60, check=False)
    rc, ligne = lire_fin(fini.stdout)
    assert rc == rc_attendu, f"{scenario} : rc {rc}, attendu {rc_attendu} ; sortie {fini.stdout!r}"
    assert ligne == (s[cle] if cle else None), f"{scenario} : derniere ligne {ligne!r}"
    for source in SOURCES:
        vu = decider(table(texte(source)), rc, ligne)
        assert vu == issue, f"{scenario} / {source} : la regle ecrite rend {vu}, attendu {issue}"


# Faux scanner piloté par l'environnement : `PAUSE` avant toute sortie, `BRUIT` lignes, puis `FIN`.
STUB_CONCURRENT = ('[ -n "${PAUSE:-}" ] && sleep "$PAUSE"\n'
                   '[ -n "${BRUIT:-}" ] && cat "$(dirname "$0")/bruit.txt"\n'
                   'printf \'%s\\n\' "$FIN"\nexit "$RC"\n')


def deux_audits(racine: Path, commande: str) -> tuple[tuple[int | None, str | None], ...]:
    """Run LENT (ouvre son journal, attend, écrit sa fin) puis run RAPIDE lancé pendant la pause."""
    s = scanner()
    stub = racine / ".agents" / "security" / "sca-scan.sh"
    stub.parent.mkdir(parents=True)
    stub.write_bytes(STUB_CONCURRENT.encode("utf-8"))
    (stub.parent / "bruit.txt").write_bytes("".join(f"  bruit {i}\n" for i in range(200)).encode("utf-8"))

    def lancer(**env: str) -> subprocess.Popen:
        return subprocess.Popen(["bash", "-c", commande], cwd=racine, env={**os.environ, **env},
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8")

    lent = lancer(PAUSE="2", FIN=s["all_go"], RC="0")
    time.sleep(0.5)
    rapide = lancer(BRUIT="1", FIN=s["all_nogo"], RC="1")
    return tuple(lire_fin(p.communicate(timeout=60)[0]) for p in (lent, rapide))


@pytest.mark.skipif(shutil.which("bash") is None, reason="SAUT ANNONCE : bash introuvable")
def test_deux_audits_concurrents_lisent_chacun_leur_fin(tmp_path):
    s = scanner()
    lent, rapide = deux_audits(tmp_path, COMMANDE)
    assert rapide == (1, s["all_nogo"]), f"run rapide : {rapide!r}"
    assert lent == (0, s["all_go"]), (
        f"run lent : {lent!r} — il lit la fin d'un AUTRE run : le journal doit etre un mktemp par run")
    journaux = sorted(p.name for p in (tmp_path / ".agents/state/local/sca-reports").iterdir())
    assert len(journaux) == 2 and all(re.fullmatch(r"last-audit-scan\.\w{6}", j) for j in journaux), journaux
