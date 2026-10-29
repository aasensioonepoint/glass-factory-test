"""Banc de `charge_poste.py` — cas de l'annexe A4 du plan T-01M4XZWZ9C0ZFVXN3MFSFY1G5V (lot T).

ISOLATION : chaque test pose HOME, XDG_STATE_HOME, XDG_CONFIG_HOME, CADRE_STATE_DIR et CADRE_CONFIG_HOME sous
son `tmp_path` (fixture autouse ci-dessous, en plus de celle de `.agents/bin/conftest.py`) : l'état réel du
poste n'est jamais lu ni écrit. La mesure est INJECTÉE (`Sources`), sauf dans le seul test de bout en bout, qui
n'affirme que la FORME des lignes.

HORLOGE : les cas de calibration et de verrou tournent sur une horloge scriptée ; chaque fait temporel fabriqué
(mtime du verrou, horodatages de plafond.json et des relevés) est posé sur CETTE horloge (CONVENTIONS_python).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import charge_poste as cp  # noqa: E402

#: Le contrat lisible de l'outil (voyage avec lui) : le banc vérifie qu'il dit la base à cinq.
CONTRAT = HERE.parent / "ref" / "CHARGE_POSTE.md"
T0 = 1_800_000_000.0
JOUR = 24 * 3600

# Lignes `ps -Ao pcpu=,comm=` relevées sur le poste du pilote (darwin-arm64, 2026-10-17, LC_ALL=C).
PS_MESURE = """\
 28.3 /Library/Application Support/JAMF/Jamf.app/Contents/MacOS/JamfDaemon.app/Contents/MacOS/JamfDaemon
221.6 /Library/SystemExtensions/AD6A1A54/com.jamf.protect.security-extension.systemextension/Contents/MacOS/com.jamf.protect.security-extension
  0.0 /Applications/JamfProtect.app/Contents/Helpers/JamfProtectAgent.app/Contents/MacOS/JamfProtectAgent
  0.0 /Applications/Self Service.app/Contents/MacOS/Jamf Connect.app/Contents/MacOS/Jamf Connect
 17.0 /Library/Application Support/Zscaler/zdp/bin/zdpesd.app/Contents/MacOS/zdpesd
  6.1 /Library/Application Support/Zscaler/zdp/bin/zdpd.app/Contents/MacOS/zdpd
  3.0 /usr/libexec/logd
"""


def _sous(chemin: Path, racine: Path) -> bool:
    try:
        Path(chemin).resolve().relative_to(racine.resolve())
    except ValueError:
        return False
    return True


@pytest.fixture(autouse=True)
def _poste_isole(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """HOME JETABLE ET EXPLICITE, jamais retiré : sans HOME, `Path.home()` retombe sur passwd et l'état part dans
    le VRAI `~/.local/state` du poste (mesuré par l'exec-critic, 2026-10-17). En plus, une GARDE : tout
    emplacement résolu, tout verrou et toute écriture hors du `tmp_path` de CE test font rougir le test AVANT
    d'écrire (témoin : `test_garde_refuse_un_etat_hors_du_tmp_du_banc`). CLAUDE_PID est RETIRÉ (C60, plan
    T-01M56Q23NH étape 4) : hérité d'une session Claude Code, il ferait de chaque verdict un appelant identifié
    et changerait les accords ; seuls les témoins d'identité le posent, par `sessions`."""
    for var, sous in (("HOME", "home"), ("XDG_STATE_HOME", "xdg-state"), ("XDG_CONFIG_HOME", "xdg-config"),
                      ("CADRE_STATE_DIR", "state"), ("CADRE_CONFIG_HOME", "config")):
        monkeypatch.setenv(var, str(tmp_path / sous))
    monkeypatch.delenv("CLAUDE_PID", raising=False)
    (tmp_path / "home").mkdir()
    vrai_emplacements, vrai_ecrire, vrai_verrou = cp.emplacements, cp.ecrire_atomique, cp.verrou

    def refuser_hors_tmp(chemin: Path) -> None:
        if not _sous(chemin, tmp_path):
            raise AssertionError(f"GARDE DU BANC : {chemin} hors de {tmp_path} — état RÉEL du poste refusé")

    def emplacements():
        dossier, config, avert = vrai_emplacements()
        for chemin in (dossier, config):
            if chemin is not None:
                refuser_hors_tmp(chemin)
        return dossier, config, avert

    def ecrire_atomique(chemin, texte):
        refuser_hors_tmp(chemin)
        vrai_ecrire(chemin, texte)

    def verrou(dossier, horloge, attente):
        refuser_hors_tmp(dossier)
        return vrai_verrou(dossier, horloge, attente)
    monkeypatch.setattr(cp, "emplacements", emplacements)
    monkeypatch.setattr(cp, "ecrire_atomique", ecrire_atomique)
    monkeypatch.setattr(cp, "verrou", verrou)


class Horloge:
    def __init__(self, t: float = T0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def avancer(self, secondes: float) -> None:
        self.t += secondes


def mesure(c: int | None = 18, l1: float = 5.0, l5: float | None = None, pression: int | None = 1,
           charge: bool = True, plateforme: str = "darwin") -> cp.Mesure:
    valeurs = (l1, l1 if l5 is None else l5, 4.0) if charge else None
    return cp.Mesure(c, valeurs, "getloadavg" if charge else "aucune", pression, 12.5, ("zdpd",), plateforme)


def sources(cpu: object = 18, loadavg=None, fichiers: dict | None = None, commandes: dict | None = None,
            plateforme: str = "darwin") -> cp.Sources:
    fichiers, commandes = fichiers or {}, commandes or {}
    return cp.Sources(lambda: cpu, loadavg, fichiers.get, lambda argv: commandes.get(tuple(argv)), plateforme)


class Banc:
    """Un poste scripté : dossier d'état, déclaration, horloge."""

    def __init__(self, tmp: Path) -> None:
        self.dossier = tmp / "etat" / "charge_poste"
        self.config = tmp / "conf" / "parallelisme.json"
        self.horloge = Horloge()

    def verdict(self, actifs: int, **kw) -> cp.Verdict:
        m = kw.pop("m", None) or mesure(**kw)
        return cp.executer_verdict(actifs, mesure=m, horloge=self.horloge, dossier=self.dossier,
                                   fichier_config=self.config, poste="banc", attente_verrou=0)

    def declarer(self, m: int, c: int = 18) -> None:
        self.config.parent.mkdir(parents=True, exist_ok=True)
        self.config.write_text(json.dumps({"postes": {f"banc|{c}": {"max": m, "motif": "S-banc"}}}),
                               encoding="utf-8")

    def poser_plafond(self, plafond: object, *, cree_le: float, dernier_sature: float | None = None,
                      c: int | str = 18) -> None:
        self.dossier.mkdir(parents=True, exist_ok=True)
        entree = {"plafond": plafond, "cree_le": cree_le, "dernier_sature": dernier_sature, "relache_le": None}
        (self.dossier / cp.NOM_PLAFOND).write_text(json.dumps({"version": 1, "postes": {f"banc|{c}": entree}}),
                                                   encoding="utf-8")

    def appris(self, c: int = 18) -> int | None:
        """La valeur apprise SUR DISQUE (None : rien d'appris, ou pas de fichier) — jamais une borne recopiée."""
        chemin = self.dossier / cp.NOM_PLAFOND
        if not chemin.exists():
            return None
        entree = json.loads(chemin.read_text(encoding="utf-8"))["postes"].get(f"banc|{c}")
        return entree["plafond"] if entree is not None else None


@pytest.fixture
def banc(tmp_path: Path) -> Banc:
    return Banc(tmp_path)


class Sessions:
    """L'identité des appelants, posée par monkeypatch : CLAUDE_PID et les PID VIVANTS (`cp.pid_vivant`)."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.mp, self.vivants = monkeypatch, set()
        monkeypatch.setattr(cp, "pid_vivant", lambda pid: pid in self.vivants)

    def appelant(self, pid: int | None) -> None:
        """`pid` vivant devient l'appelant ; None : appelant ANONYME (CLAUDE_PID retiré)."""
        if pid is None:
            self.mp.delenv("CLAUDE_PID", raising=False)
            return
        self.vivants.add(pid)
        self.mp.setenv("CLAUDE_PID", str(pid))

    def mourir(self, pid: int) -> None:
        self.vivants.discard(pid)


@pytest.fixture
def sessions(monkeypatch: pytest.MonkeyPatch) -> Sessions:
    return Sessions(monkeypatch)


PID_A, PID_B = 4101, 4102   # PID fictifs de deux sessions identifiées


# =========================================================================== mesure
def test_sysctl_virgule_vaut_point():
    s = sources(commandes={("sysctl", "-n", "vm.loadavg"): "{ 4,79 8,62 43,95 }\n"})
    assert cp.lire_charge(s) == ((4.79, 8.62, 43.95), "sysctl")


def test_sysctl_point_et_proc_loadavg():
    s = sources(commandes={("sysctl", "-n", "vm.loadavg"): "{ 4.79 8.62 43.95 }"})
    assert cp.lire_charge(s) == ((4.79, 8.62, 43.95), "sysctl")
    s = sources(fichiers={"/proc/loadavg": "0.52 0.58 0.59 1/389 12345\n"})
    assert cp.lire_charge(s) == ((0.52, 0.58, 0.59), "/proc/loadavg")


def test_getloadavg_d_abord_puis_repli_sur_oserror():
    assert cp.lire_charge(sources(loadavg=lambda: (1.0, 2.0, 3.0))) == ((1.0, 2.0, 3.0), "getloadavg")

    def casse():
        raise OSError("indisponible")
    s = sources(loadavg=casse, fichiers={"/proc/loadavg": "0.5 0.6 0.7 1/2 3"})
    assert cp.lire_charge(s) == ((0.5, 0.6, 0.7), "/proc/loadavg")


@pytest.mark.parametrize("absurde", ["-1", "nan", "1e400", "abc", ""])
def test_valeur_absurde_tombe_au_defaut(absurde):
    assert cp.nombre(absurde) is None
    s = sources(fichiers={"/proc/loadavg": f"{absurde} 0.5 0.5 1/2 3"},
                commandes={("sysctl", "-n", "vm.loadavg"): f"{{ {absurde} 1,0 1,0 }}"})
    assert cp.lire_charge(s) == (None, "aucune")
    assert cp.lire_charge(sources(loadavg=lambda: (float("nan"), 1.0, 1.0))) == (None, "aucune")


def test_getloadavg_retire_rend_non_mesurable(monkeypatch, banc):
    monkeypatch.delattr(os, "getloadavg", raising=False)
    assert cp.sources_du_poste().getloadavg is None  # résolu à l'APPEL, pas à l'import
    m = cp.mesurer(sources(loadavg=None, plateforme="win32"))
    assert m.charge is None and not m.mesurable
    v = banc.verdict(0, m=m)
    lignes = v.lignes()
    assert lignes[0] == "PLAFOND=5 BASE=5 SOURCE=non-mesurable"
    assert lignes[2].startswith("CHARGE=inconnu C=18 ")
    assert "COVERAGE DEGRADED — charge du poste non mesurable sur Windows" in lignes
    assert v.peut_ajouter == 5 and v.calibration == "stable"
    assert banc.verdict(2, m=m).peut_ajouter == 3  # cinq moins les actifs


def test_ps_mesure_jamf_et_zdp_un_seul_split():
    total, noms = cp.analyser_ps(PS_MESURE)
    assert total == round(28.3 + 221.6 + 17.0 + 6.1, 1)
    # JamfDaemon et zdpesd vivent sous un chemin À ESPACES : un split multiple les perd.
    assert {"JamfDaemon", "com.jamf.protect.security-extension", "JamfProtectAgent", "zdpesd", "zdpd"} == set(noms)
    assert "logd" not in noms and "Jamf Connect" not in noms


def test_ps_virgule_toleree_et_aucun_edr_inconnu():
    assert cp.analyser_ps(" 28,3 /x/JamfDaemon\n") == (28.3, ("JamfDaemon",))
    assert cp.analyser_ps(" 3.0 /usr/libexec/logd\n") == (None, ())
    m = cp.mesurer(sources(loadavg=lambda: (1.0, 1.0, 1.0)))
    assert m.edr_cpu is None
    assert cp.ligne_mesure(m).endswith("EDR_CPU=inconnu")


@pytest.mark.parametrize("brut, attendu", [("1\n", 1), ("2", 2), ("4", 4), ("3", None), ("abc", None), (None, None)])
def test_pression_darwin(brut, attendu):
    s = sources(commandes={("sysctl", "-n", "kern.memorystatus_vm_pressure_level"): brut})
    assert cp.lire_pression(s) == attendu


def test_pression_linux_psi_puis_meminfo():
    psi = "some avg10={s} avg60=0.00 avg300=0.00 total=1\nfull avg10={f} avg60=0.00 avg300=0.00 total=1\n"
    lire = cp.lire_pression
    assert lire(sources(plateforme="linux", fichiers={"/proc/pressure/memory": psi.format(s=12, f=0)})) == 2
    assert lire(sources(plateforme="linux", fichiers={"/proc/pressure/memory": psi.format(s=12, f=10)})) == 4
    assert lire(sources(plateforme="linux", fichiers={"/proc/pressure/memory": psi.format(s=9.9, f=0)})) == 1
    meminfo = "MemTotal: 1000 kB\nMemAvailable: {d} kB\n"
    for dispo, attendu in ((40, 4), (80, 2), (500, 1)):
        assert lire(sources(plateforme="linux", fichiers={"/proc/meminfo": meminfo.format(d=dispo)})) == attendu
    assert lire(sources(plateforme="linux")) is None
    assert lire(sources(plateforme="win32")) is None


# =========================================================================== verdict (C = 18 sauf mention)
def test_c18_sous_deux_tiers_accorde_libre_sans_limite_de_deux(banc):
    """S-01M59PGM83 : ACTIFS > 0 sous 2C/3 ⇒ LIBRE = 12 − 1 − 0 = 11 ; l'ancien « +2 sous C/2 » est retiré."""
    assert banc.verdict(1, l1=8.99, l5=8.99).peut_ajouter == 11


def test_c18_cinq_minutes_a_la_moitie_ne_bloque_plus(banc):
    """L'ancien seuil C/2 de départ est retiré : 8,99/9,00 accorde LIBRE (C/2 reste le seuil de MONTÉE)."""
    assert banc.verdict(1, l1=8.99, l5=9.00).peut_ajouter == 11


@pytest.mark.parametrize("l1, l5, peut, doit", [(11.99, 11.99, 7, None), (11.99, 12.00, 0, None),
                                                (11.99, 12.01, 0, None), (12.01, 12.01, 0, 5)])
def test_c18_seuil_deux_tiers_strict(banc, l1, l5, peut, doit):
    """C67 : ACTIFS = 5, TENU = 0 — sous 2C/3 (1 min ET 5 min) ⇒ 12 − 5 = 7 ; à l'égalité 12,00 ou au-dessus en
    5 min ⇒ 0 sans repli ; 12,01 en 1 min ⇒ 0 et DOIT_REDESCENDRE_A = BASE = 5."""
    v = banc.verdict(5, l1=l1, l5=l5)
    assert (v.peut_ajouter, v.doit_redescendre_a) == (peut, doit)


@pytest.mark.parametrize("l1, l5, base", [(3.0, 3.0, 9), (4.49, 4.49, 9), (4.50, 4.49, 5), (4.49, 4.50, 5),
                                          (5.05, 5.05, 5)])
def test_c18_premiere_vague_neuf_au_repos_cinq_hors_repos(banc, l1, l5, base):
    """S-01M56T0DBKR9 : au repos (1 min ET 5 min < C/4 = 4,5, strict), BASE = max(min(5, 12), min(12, 9)) = 9 ;
    ailleurs min(5, PLAFOND) = 5. Le premier verdict à ACTIFS = 0, sans état, accorde BASE."""
    v = banc.verdict(0, l1=l1, l5=l5)
    assert (v.plafond, v.base, v.peut_ajouter) == (12, base, base)
    assert v.lignes()[0] == f"PLAFOND=12 BASE={base} SOURCE=defaut"


def test_c18_hors_repos_cinq_puis_libre_sept_sans_delai(banc):
    """C67 : à 5,05/5,05 (hors repos), ACTIFS = 0 ⇒ 5 ; une seconde plus tard ACTIFS = 5 ⇒ 7 : l'accord
    anonyme de 5 est déduit des ACTIFS (max(0, 5 − 5) = 0), aucun délai de 300 s."""
    assert banc.verdict(0, l1=5.05, l5=5.05).peut_ajouter == 5
    banc.horloge.avancer(1)
    assert banc.verdict(5, l1=5.05, l5=5.05).peut_ajouter == 7


def test_c24_quinze_sur_quinze_hors_repos_accorde_libre(banc):
    """C67 : C = 24, plafond déclaré 15, charge 15/15 (sous 2C/3 = 16, loin du repos C/4 = 6), ACTIFS = 5 ⇒
    LIBRE = 15 − 5 = 10. Le seuil de l'accord rapide est 2C/3, jamais celui du repos."""
    banc.declarer(15, c=24)
    v = banc.verdict(5, c=24, l1=15.0, l5=15.0)
    assert (v.plafond, v.base, v.peut_ajouter) == (15, 5, 10)


def test_c18_douze_pile_pas_de_repli_douze_01_repli(banc, tmp_path):
    v = banc.verdict(1, l1=12.00)
    assert (v.peut_ajouter, v.doit_redescendre_a) == (0, None)
    autre = Banc(tmp_path / "b")
    v = autre.verdict(1, l1=12.01)
    assert (v.peut_ajouter, v.doit_redescendre_a) == (0, 5)
    assert "DOIT_REDESCENDRE_A=5" in v.lignes()[1]


def test_c18_actifs_zero_sans_fichier_cinq_puis_zero_sous_12_01(banc, tmp_path):
    assert banc.verdict(0, l1=12.00).peut_ajouter == 5
    assert Banc(tmp_path / "b").verdict(0, l1=12.01).peut_ajouter == 0


@pytest.mark.parametrize("l1, doit", [(18.00, 5), (18.01, 3)])
def test_c18_au_dela_des_coeurs(banc, l1, doit):
    """Surcharge SÉVÈRE = 1 min > C, strict (S-01M54W6K0C) : à 18,00 elle reste modérée (BASE = 5), à 18,01 elle
    redescend à min(3, BASE) = 3."""
    v = banc.verdict(2, l1=l1)
    assert (v.peut_ajouter, v.doit_redescendre_a) == (0, doit)


@pytest.mark.parametrize("pression, peut, doit", [(1, 11, None), (None, 11, None), (2, 0, 5), (4, 0, 3)])
def test_pression(banc, pression, peut, doit):
    v = banc.verdict(1, pression=pression)
    assert (v.peut_ajouter, v.doit_redescendre_a) == (peut, doit)


def test_c1_vaut_un(banc):
    v = banc.verdict(0, c=1, l1=0.1)
    assert (v.plafond, v.base, v.peut_ajouter) == (1, 1, 1)
    assert cp.dur_de(1, None) == 1


def test_c4_plafond_deux_porte_de_securite_part(banc, tmp_path):
    """C30 côté outil : à C=4 sans fichier, PEUT_AJOUTER = 2 et aucun NO-GO de charge — la porte part
    (budget max(1, 2 − 2) = 1, règle de K/S) ; le seul NO-GO de charge est 1 min > 2C/3 ou PRESSION ≥ 2."""
    v = banc.verdict(0, c=4, l1=2.66)
    assert (v.plafond, v.base, v.peut_ajouter, v.doit_redescendre_a) == (2, 2, 2, None)
    v = Banc(tmp_path / "b").verdict(0, c=4, l1=2.67)
    assert (v.peut_ajouter, v.doit_redescendre_a) == (0, 2)


@pytest.mark.parametrize("c, plafond, repos, hors_repos", [(18, 12, 9, 5), (8, 5, 5, 5), (6, 4, 4, 4), (4, 2, 2, 2),
                                                            (1, 1, 1, 1)])
def test_base_a_cinq_sous_cinq_quand_le_plafond_l_est(banc, tmp_path, c, plafond, repos, hors_repos):
    """S-01M54B1KQ6 : hors repos BASE = min(5, PLAFOND) — cinq sur 18 ou 8 cœurs, sous cinq quand ⌊2C/3⌋ l'est
    (C=6 ⇒ 4, C=4 ⇒ 2) : jamais un plancher (S-01M54NGJ3S0). Au repos (S-01M56T0DBKR9) BASE =
    max(min(5, P), min(P, ⌊C/2⌋)) : 9 sur 18 cœurs, inchangée sur un petit poste."""
    v = banc.verdict(0, c=c, l1=0.1, l5=0.1)
    assert (v.plafond, v.base, v.peut_ajouter) == (plafond, repos, repos)
    v = Banc(tmp_path / "hors-repos").verdict(0, c=c, l1=c / 4, l5=c / 4)
    assert (v.plafond, v.base, v.peut_ajouter) == (plafond, hors_repos, hors_repos)


def test_plafond_appris_sous_cinq_garde(banc):
    """S-01M54NGJ3S0NHR7BEFZY94PF7W : un plafond appris de 4 sur 18 cœurs tient la base à 4, jamais relevée à 5."""
    banc.poser_plafond(4, cree_le=T0 - 3600)
    v = banc.verdict(0)
    assert (v.plafond, v.base, v.peut_ajouter, v.source) == (4, 4, 4, "appris")


@pytest.mark.parametrize("appris, plafond", [(2, 2), (4, 4), (50, 5)])
def test_non_mesurable_un_plafond_appris_sous_cinq_le_tient(banc, appris, plafond):
    """Revue de clôture commune (S-01M54NGJ3S0NHR7BEFZY94PF7W) : charge illisible, un plafond APPRIS sous cinq
    tient PLAFOND et BASE, jamais relevé à cinq (:689 rendait 5 sur un appris de 2) ; au-dessus de cinq,
    min(5, DUR), le 50 de `test_jamais_au_dessus_de_dur_meme_non_mesurable`."""
    banc.poser_plafond(appris, cree_le=T0 - 3600)
    v = banc.verdict(0, charge=False)
    assert (v.source, v.plafond, v.base, v.peut_ajouter) == ("non-mesurable", plafond, plafond, plafond)
    assert v.lignes()[0] == f"PLAFOND={plafond} BASE={plafond} SOURCE=non-mesurable"
    assert banc.appris() == appris                              # lu, jamais réécrit


@pytest.mark.skipif(not hasattr(os, "geteuid") or os.geteuid() == 0, reason="root ignore les droits")
def test_non_inscrit_non_mesurable_un_plafond_appris_sous_cinq_le_tient(banc):
    """La même borne sur la branche NON INSCRITE (:728) : état en lecture seule, plafond.json lisible."""
    banc.poser_plafond(2, cree_le=T0 - 3600)
    banc.dossier.chmod(0o500)
    try:
        v = banc.verdict(0, charge=False)
    finally:
        banc.dossier.chmod(0o700)
    assert (v.etat, v.source, v.plafond, v.base, v.peut_ajouter) == ("non-inscriptible", "non-mesurable", 2, 2, 1)


def test_c_inconnu_la_regle_sans_mesure_ne_change_pas(banc):
    """CHARGE_POSTE.md § 7, « sauf à C inconnu » : la clé `<poste>|inconnu` n'est jamais calibrée — un plafond
    posé sous elle n'est pas lu, PLAFOND = min(5, DUR) = 5."""
    banc.poser_plafond(2, cree_le=T0 - 3600, c="inconnu")
    v = banc.verdict(0, c=None, charge=False)
    assert (v.source, v.plafond, v.base) == ("non-mesurable", 5, 5)


@pytest.mark.parametrize("pression, doit", [(2, 5), (4, 3)])
def test_non_mesurable_la_pression_retient_d_abord(banc, pression, doit):
    """Garde de pression (plan T-01M54B1SX, étape 1) : charge illisible, pression LISIBLE — PRESSION ≥ 2 rend 0
    avant tout ; sans elle, cinq agents partiraient sous une pression mémoire mesurée. PRESSION 4 ⇒ min(3, BASE)."""
    v = banc.verdict(0, charge=False, pression=pression)
    assert (v.source, v.plafond, v.peut_ajouter, v.doit_redescendre_a) == ("non-mesurable", 5, 0, doit)
    assert f"DOIT_REDESCENDRE_A={doit}" in v.lignes()[1]
    assert banc.verdict(0, charge=False, pression=1).peut_ajouter == 5      # PRESSION 1 : aucune retenue


@pytest.mark.parametrize("c", [18, None])
def test_non_inscrit_non_mesurable_plafond_cinq(c):
    """:714 — non inscrit ET non mesurable : PLAFOND = BASE = min(5, DUR) (C inconnu : DUR = 5), un à un (C31)."""
    v = cp.executer_verdict(0, mesure=mesure(c=c, charge=False), horloge=Horloge(), dossier=None,
                            fichier_config=None, poste="banc")
    assert (v.plafond, v.base, v.peut_ajouter, v.doit_redescendre_a, v.etat) == (5, 5, 1, None, "non-inscriptible")
    assert v.lignes()[0] == "PLAFOND=5 BASE=5 SOURCE=non-mesurable"


@pytest.mark.parametrize("pression, doit", [(4, 3), (2, 5)])
def test_non_inscrit_non_mesurable_la_pression_retient_avant_le_un_a_un(pression, doit):
    """La garde de pression mord AVANT le « 1 à ACTIFS = 0 » de C31 : non inscrit, non mesurable, PRESSION 4
    ⇒ (0, 3)."""
    v = cp.executer_verdict(0, mesure=mesure(charge=False, pression=pression), horloge=Horloge(), dossier=None,
                            fichier_config=None, poste="banc")
    assert (v.peut_ajouter, v.doit_redescendre_a, v.etat) == (0, doit, "non-inscriptible")


def test_releve_c_inconnu_dur_cinq_sans_borne_de_coeurs(capsys):
    """Nombre de cœurs inconnu : DUR = 5, sans borne de cœurs (CHARGE_POSTE.md § 7) — `releve` le dit."""
    s = sources(cpu=None, loadavg=lambda: (1.0, 1.0, 1.0))
    assert cp.main(["releve", "--poste", "banc"], sources=s) == 0
    sortie = capsys.readouterr().out
    assert "C=inconnu" in sortie and "POSTE=banc|inconnu M=- DUR=5 " in sortie


def _section(texte: str, numero: int) -> str:
    """Le § `numero` de CHARGE_POSTE.md, de son titre au suivant ; '' s'il manque."""
    trouve = re.search(rf"^## {numero}\. .*?(?=^## |\Z)", texte, re.M | re.S)
    return trouve.group(0) if trouve else ""


def test_contrat_dit_la_base_a_cinq():
    """Le contrat lisible suit l'outil : « min(5, PLAFOND) » écrit, « min(3, PLAFOND) » retiré, et la surcharge
    sévère « min(3, BASE) » dite (plan T-01M54B1SX, étape 2). Le repli des lanceurs sur une sortie illisible,
    « max(0, 5 − ACTIFS) », est lu dans le § 2 SEUL : le § 7 le cite aussi, et un `in texte` laissait vert un
    § 2 muté (mutant M27 de la revue de clôture commune)."""
    texte = CONTRAT.read_text(encoding="utf-8")
    assert "min(5, PLAFOND)" in texte
    assert "min(3, PLAFOND)" not in texte
    assert "min(3, BASE)" in texte
    assert "max(0, 5 − ACTIFS)" in _section(texte, 2), "§ 2 : le repli des lanceurs à cinq moins les actifs"


def test_c37_deux_verdicts_a_zero_actif_a_dix_secondes(banc):
    """Hors repos (5,0) : 5, puis 10 s plus tard encore 5 — l'accord anonyme retenu (5) laisse LIBRE = 7."""
    assert banc.verdict(0).peut_ajouter == 5
    banc.horloge.avancer(10)
    assert banc.verdict(0).peut_ajouter == 5


def test_un_actif_sans_delai_d_accord_puis_retenue_300_s(banc):
    """Plus de délai de 300 s entre accords (DELAI_ACCORD_S retiré) : 11, puis 10 s plus tard 1 — l'accord
    anonyme de 11, moins ACTIFS = 1, reste TENU (10) pendant RETENUE_S ; à 300 s il est libéré ⇒ 11."""
    assert banc.verdict(1).peut_ajouter == 11
    banc.horloge.avancer(10)
    assert banc.verdict(1).peut_ajouter == 1
    banc.horloge.avancer(290)
    assert banc.verdict(1).peut_ajouter == 11


def test_c45_accord_a_zero_actif_horodate(banc):
    """L'accord à ACTIFS = 0 est horodaté : 10 s plus tard, ACTIFS = 3 ⇒ TENU = max(0, 5 − 3) = 2, LIBRE = 7."""
    assert banc.verdict(0).peut_ajouter == 5
    banc.horloge.avancer(10)
    assert banc.verdict(3).peut_ajouter == 7


def test_c45_jamais_negatif(banc):
    banc.declarer(3)
    v = banc.verdict(5)
    assert (v.plafond, v.peut_ajouter) == (3, 0)
    assert cp.decider(c=18, charge=(1.0, 1.0, 1.0), pression=1, actifs=5, plafond=3, tenu=0,
                      inscriptible=True) == (0, None)
    assert cp.decider(c=18, charge=(1.0, 1.0, 1.0), pression=1, actifs=0, plafond=12, tenu=20,
                      inscriptible=True) == (0, None)


def test_c46_une_regle_de_dur(banc, tmp_path):
    banc.declarer(40)
    v = banc.verdict(0)
    assert (v.plafond, v.source) == (18, "declare")
    assert any("hors 1..18" in a for a in v.avertissements)
    autre = Banc(tmp_path / "b")
    autre.declarer(0)
    v = autre.verdict(0)
    assert (v.plafond, v.peut_ajouter) == (1, 1)
    assert autre.verdict(0).peut_ajouter == 0                  # l'accord de 1, retenu, occupe le plafond 1
    assert (cp.dur_de(18, 40), cp.dur_de(18, 0), cp.dur_de(18, None), cp.dur_de(1, None)) == (18, 1, 12, 1)


def test_concurrents_accords_retenus_sous_le_plafond(banc, monkeypatch):
    """Huit appelants anonymes à ACTIFS=1 en même temps : le verrou sérialise, chaque accord est RETENU pour les
    suivants — 11, puis 1 (12 − 1 − (11 − 1)), puis 0 ; jamais plus que le plafond. L'écriture est ralentie pour
    que, sans verrou, toutes lisent l'état avant qu'aucune n'écrive (huit fois 11)."""
    vrai = cp.ecrire_atomique

    def lente(chemin, texte):
        time.sleep(0.05)
        vrai(chemin, texte)
    monkeypatch.setattr(cp, "ecrire_atomique", lente)
    banc.dossier.mkdir(parents=True)
    resultats: list[int] = []

    def session():
        v = cp.executer_verdict(1, mesure=mesure(), horloge=time.time, dossier=banc.dossier,
                                fichier_config=banc.config, poste="banc", attente_verrou=10)
        resultats.append(v.peut_ajouter)
    fils = [threading.Thread(target=session) for _ in range(8)]
    for f in fils:
        f.start()
    for f in fils:
        f.join()
    assert sorted(resultats) == [0] * 6 + [1, 11]


@pytest.mark.parametrize("age, etat, reste", [(31, "ok", False), (29, "non-inscriptible", True)])
def test_verrou_31_s_repris_29_s_refuse(banc, age, etat, reste):
    banc.dossier.mkdir(parents=True)
    verrou = banc.dossier / cp.NOM_VERROU
    verrou.write_text("4242 0\n", encoding="utf-8")
    os.utime(verrou, (banc.horloge() - age, banc.horloge() - age))
    v = banc.verdict(1)
    assert v.etat == etat
    assert v.peut_ajouter == (11 if etat == "ok" else 0)
    assert verrou.exists() is reste


def test_verrou_rendu_apres_le_verdict(banc):
    banc.verdict(0)
    assert not (banc.dossier / cp.NOM_VERROU).exists()


@pytest.mark.skipif(not hasattr(os, "geteuid") or os.geteuid() == 0, reason="root ignore les droits")
def test_c31_etat_en_lecture_seule_un_puis_zero(tmp_path, capsys):
    etat = tmp_path / "state"
    etat.mkdir()
    etat.chmod(0o500)
    try:
        s = sources(loadavg=lambda: (1.0, 1.0, 1.0))
        assert cp.main(["verdict", "--actifs", "0", "--poste", "banc"], sources=s, horloge=Horloge()) == 0
        sortie = capsys.readouterr().out.splitlines()
        assert sortie[1].startswith("PEUT_AJOUTER=1 ")
        assert sortie[3] == "CALIBRATION=non-inscriptible RELEVES=0 ETAT=non-inscriptible"
        assert cp.TEXTE_NON_INSCRIPTIBLE in sortie
        cp.main(["verdict", "--actifs", "1", "--poste", "banc", "--attendre", "540"], sources=s,
                horloge=Horloge(), dormir=lambda _s: pytest.fail("aucune attente : rien ne peut changer"))
        assert capsys.readouterr().out.splitlines()[1].startswith("PEUT_AJOUTER=0 ")
        assert list(etat.iterdir()) == []
    finally:
        etat.chmod(0o700)


@pytest.mark.skipif(not hasattr(os, "geteuid") or os.geteuid() == 0, reason="root ignore les droits")
def test_attendre_non_inscriptible_attend_que_la_surcharge_retombe(tmp_path, capsys):
    """MAJEUR 1 de l'exec-critic : non inscriptible, le 0 d'une SURCHARGE présente peut changer — l'attente
    continue ; charge 12,5 puis 5,0 ⇒ 1 après une attente."""
    etat = tmp_path / "state"
    etat.mkdir()
    etat.chmod(0o500)
    try:
        charges = iter([(12.5, 12.5, 4.0), (5.0, 5.0, 4.0)])
        horloge, dormi = Horloge(), []

        def dormir(secondes):
            dormi.append(secondes)
            horloge.avancer(secondes)
        s = sources(loadavg=lambda: next(charges))
        assert cp.main(["verdict", "--actifs", "0", "--poste", "banc", "--attendre", "540"], sources=s,
                       horloge=horloge, dormir=dormir) == 0
        sortie = capsys.readouterr().out.splitlines()
        assert sortie[1] == "PEUT_AJOUTER=1 DOIT_REDESCENDRE_A=- ACTIFS=0"
        assert sortie[3].endswith("ETAT=non-inscriptible") and dormi == [cp.PAS_ATTENTE_S]
    finally:
        etat.chmod(0o700)


def test_garde_refuse_un_etat_hors_du_tmp_du_banc(tmp_path, monkeypatch):
    """La garde de `_poste_isole` peut rougir : un CADRE_STATE_DIR hors du tmp de CE test est refusé avant toute
    écriture (le chemin choisi reste sous le basetemp de pytest : rien de réel n'est jamais visé)."""
    ailleurs = tmp_path.parent / f"{tmp_path.name}-ailleurs"
    monkeypatch.setenv("CADRE_STATE_DIR", str(ailleurs))
    with pytest.raises(AssertionError, match="GARDE DU BANC"):
        cp.main(["verdict", "--actifs", "0"], sources=sources(loadavg=lambda: (1.0, 1.0, 1.0)),
                horloge=Horloge())
    assert not ailleurs.exists()
    with pytest.raises(AssertionError, match="GARDE DU BANC"):
        cp.ecrire_atomique(ailleurs / "x", "x")


def test_etat_ou_config_dans_un_depot_refuses(tmp_path, monkeypatch, capsys):
    depot = tmp_path / "depot"
    (depot / ".git").mkdir(parents=True)
    monkeypatch.setenv("CADRE_STATE_DIR", str(depot / "etat"))
    monkeypatch.setenv("CADRE_CONFIG_HOME", str(depot / "conf"))
    dossier, config, avert = cp.emplacements()
    assert dossier is None and config is None and len(avert) == 2
    s = sources(loadavg=lambda: (1.0, 1.0, 1.0))
    assert cp.main(["verdict", "--actifs", "0"], sources=s, horloge=Horloge()) == 0
    sortie = capsys.readouterr()
    assert "ETAT=non-inscriptible" in sortie.out and "dépôt git" in sortie.err
    assert cp.main(["declarer", "--max", "4", "--motif", "S-banc"], sources=s, horloge=Horloge()) == 1
    assert sorted(p.name for p in depot.iterdir()) == [".git"]  # rien d'écrit dans le dépôt
    monkeypatch.setenv("CADRE_STATE_DIR", str(tmp_path / "hors"))
    assert cp.emplacements()[0] == (tmp_path / "hors").resolve() / cp.NOM_DOSSIER_ETAT


def test_declarer_puis_verdict_par_la_cli(tmp_path, capsys):
    s = sources(loadavg=lambda: (1.0, 1.0, 1.0))
    assert cp.main(["declarer", "--max", "5", "--motif", "S-banc", "--poste", "Banc.local"], sources=s,
                   horloge=Horloge()) == 0
    assert "DECLARE POSTE=banc|18 MAX=5 DUR=5" in capsys.readouterr().out
    assert cp.main(["verdict", "--actifs", "0", "--poste", "banc"], sources=s, horloge=Horloge()) == 0
    assert capsys.readouterr().out.splitlines()[0] == "PLAFOND=5 BASE=5 SOURCE=declare"
    assert (tmp_path / "config" / cp.NOM_CONFIG).is_file()
    assert (tmp_path / "state" / cp.NOM_DOSSIER_ETAT / cp.NOM_RELEVES).is_file()


@pytest.mark.parametrize("argv", [["verdict", "--actifs", "-1"], ["verdict", "--actifs", "0", "--attendre", "541"],
                                  ["verdict"], ["declarer", "--max", "-2", "--motif", "x"]])
def test_usage_invalide_rc_2(argv):
    with pytest.raises(SystemExit) as fin:
        cp.main(argv, sources=sources())
    assert fin.value.code == 2


def test_attendre_jusqu_a_l_accord(tmp_path, capsys, sessions):
    """Par la CLI : un appelant anonyme prend BASE = 9 au repos ; 10 s plus tard une session identifiée à
    ACTIFS = 3 trouve LIBRE = 12 − 3 − 9 = 0 et attend que la retenue de 300 s libère l'accord ⇒ 9."""
    s, horloge = sources(loadavg=lambda: (1.0, 1.0, 1.0)), Horloge()
    sessions.appelant(None)
    cp.main(["verdict", "--actifs", "0", "--poste", "banc"], sources=s, horloge=horloge)
    assert capsys.readouterr().out.splitlines()[1].startswith("PEUT_AJOUTER=9 ")
    horloge.avancer(10)
    dormi: list[float] = []

    def dormir(secondes):
        dormi.append(secondes)
        horloge.avancer(secondes)
    sessions.appelant(PID_A)
    assert cp.main(["verdict", "--actifs", "3", "--poste", "banc", "--attendre", "540"], sources=s,
                   horloge=horloge, dormir=dormir) == 0
    assert capsys.readouterr().out.splitlines()[1].startswith("PEUT_AJOUTER=9 ")
    assert 290 <= sum(dormi) <= 320 and max(dormi) <= cp.PAS_ATTENTE_S


def test_attendre_borne_par_sa_duree(tmp_path, capsys):
    s, horloge = sources(loadavg=lambda: (15.0, 15.0, 15.0)), Horloge()

    def dormir(secondes):
        horloge.avancer(secondes)
    cp.main(["verdict", "--actifs", "1", "--poste", "banc", "--attendre", "100"], sources=s, horloge=horloge,
            dormir=dormir)
    assert capsys.readouterr().out.splitlines()[1].startswith("PEUT_AJOUTER=0 ")
    assert horloge.t == T0 + 100


def test_releve_n_ecrit_rien(tmp_path, capsys):
    s = sources(loadavg=lambda: (1.0, 1.0, 1.0), commandes={("ps", "-Ao", "pcpu=,comm="): PS_MESURE})
    assert cp.main(["releve", "--poste", "banc"], sources=s) == 0
    sortie = capsys.readouterr().out
    assert "EDR_CPU=273.0" in sortie and "SOURCE_CHARGE=getloadavg" in sortie and "ETAT=absent" in sortie
    assert not (tmp_path / "state").exists()


def test_chaque_verdict_ajoute_un_releve_borne_a_500(banc):
    banc.dossier.mkdir(parents=True)
    ancien = {"ts": T0 - 1000, "cle": "banc|18", "actifs": 0, "peut_ajouter": 0}
    (banc.dossier / cp.NOM_RELEVES).write_text("".join(json.dumps(ancien) + "\n" for _ in range(505)) + "{cassé\n",
                                               encoding="utf-8")
    v = banc.verdict(2, l1=3.0, l5=4.0, pression=1)
    lignes = (banc.dossier / cp.NOM_RELEVES).read_text(encoding="utf-8").splitlines()
    assert v.releves == len(lignes) == cp.MAX_RELEVES
    dernier = json.loads(lignes[-1])
    assert (dernier["ts"], dernier["actifs"], dernier["charge1"], dernier["charge5"], dernier["pression"],
            dernier["edr_cpu"], dernier["peut_ajouter"], dernier["claude_pid"], dernier["tenu"]) == (
        T0, 2, 3.0, 4.0, 1, 12.5, 10, None, 0)


def test_sortie_degradee_porte_toujours_ses_lignes(tmp_path, banc):
    """C33 côté outil : rien de lisible ne manque même tout dégradé — illisible n'arrive qu'à une commande tuée."""
    v = cp.executer_verdict(1, mesure=mesure(c=None, charge=False), horloge=Horloge(), dossier=None,
                            fichier_config=None, poste="banc")
    lignes = v.lignes()
    assert re.fullmatch(r"PLAFOND=\d+ BASE=\d+ SOURCE=non-mesurable", lignes[0])
    assert lignes[1].startswith("PEUT_AJOUTER=0 ") and "C=inconnu" in lignes[2]


# =========================================================================== calibration (horloge scriptée)
def test_sature_a_a_dix_descend_a_neuf(banc):
    banc.poser_plafond(10, cree_le=T0 - 3600)
    assert banc.verdict(8, l1=5.0).peut_ajouter == 2           # accord : 8 + LIBRE 2 = 10
    banc.horloge.avancer(400)
    v = banc.verdict(10, l1=12.5)
    assert (v.calibration, v.plafond, v.source) == ("descend", 9, "appris")
    assert banc.appris() == 9


def test_non_probant_moins_de_300_s_inchange(banc):
    banc.verdict(8, l1=5.0)
    banc.horloge.avancer(100)
    v = banc.verdict(10, l1=12.5)
    assert (v.calibration, v.plafond) == ("stable", 12)


@pytest.mark.parametrize("age, calibration, appris", [(299, "stable", 10), (300, "descend", 9)])
def test_sature_a_exactement_300_s_descend(banc, age, calibration, appris):
    """Probance 299/300 : FENETRE_PROBANTE_S, distincte de la retenue des accords (RETENUE_S)."""
    banc.poser_plafond(10, cree_le=T0 - 3600)
    banc.verdict(8, l1=5.0)                                     # accord : 8 + LIBRE 2 = 10
    banc.horloge.avancer(age)
    assert (banc.verdict(10, l1=12.5).calibration, banc.appris()) == (calibration, appris)


def test_sature_a_zero_actif_non_probant(banc):
    banc.verdict(0)
    banc.horloge.avancer(400)
    v = banc.verdict(0, l1=12.5)
    assert (v.calibration, v.plafond, banc.appris()) == ("stable", 12, None)


def test_sature_non_probant_rearme_les_24_h(banc):
    """Un relevé saturé NON probant (ACTIFS=0, charge étrangère) remet la fenêtre de relâche à zéro : 24 h − 60 s
    plus tard, rien ; à 24 h, +1."""
    banc.poser_plafond(9, cree_le=T0 - 3 * JOUR, dernier_sature=T0 - 2 * JOUR)
    assert banc.verdict(0, l1=12.5).calibration == "stable"
    banc.horloge.avancer(JOUR - 60)
    assert (banc.verdict(0).calibration, banc.appris()) == ("stable", 9)
    banc.horloge.avancer(60)
    assert (banc.verdict(0).calibration, banc.appris()) == ("relache", 10)


def test_premier_verdict_sature_sans_accord_non_probant(banc):
    """Défaut trouvé au premier rejeu : sans accord, `a` retombait sur l'ACTIFS du relevé et UN verdict saturé
    à ACTIFS=1 mettait le plafond appris à 1. Sans accord, aucune vague n'est mesurée : rien ne bouge."""
    v = banc.verdict(1, l1=12.01)
    assert (v.calibration, v.plafond, v.doit_redescendre_a, banc.appris()) == ("stable", 12, 5, None)


def test_sain_a_neuf_monte_a_dix(banc):
    banc.poser_plafond(9, cree_le=T0 - 3600)
    assert banc.verdict(7, l1=5.0).peut_ajouter == 2           # accord : 7 + 2 = 9
    banc.horloge.avancer(400)
    v = banc.verdict(9, l1=5.0, l5=5.0, pression=1)
    assert (v.calibration, v.plafond, v.peut_ajouter) == ("monte", 10, 1)


def test_sain_sous_le_plafond_ou_pression_inconnue_ne_monte_pas(banc, tmp_path):
    banc.poser_plafond(9, cree_le=T0 - 3600)
    banc.verdict(6, l1=5.0)
    banc.horloge.avancer(400)
    assert banc.verdict(8, l1=5.0).calibration == "stable"
    autre = Banc(tmp_path / "b")
    autre.poser_plafond(9, cree_le=T0 - 3600)
    autre.verdict(7, l1=5.0)
    autre.horloge.avancer(400)
    assert autre.verdict(9, l1=5.0, pression=None).calibration == "stable"


def test_vingt_quatre_heures_relache_de_un(banc):
    banc.poser_plafond(9, cree_le=T0 - 2 * JOUR, dernier_sature=T0 - JOUR - 1)
    v = banc.verdict(0)
    assert (v.calibration, v.plafond) == ("relache", 10)


def test_moins_de_vingt_quatre_heures_pas_de_relache(banc):
    banc.poser_plafond(9, cree_le=T0 - 2 * JOUR, dernier_sature=T0 - JOUR + 60)
    assert (banc.verdict(0).calibration, banc.appris()) == ("stable", 9)


def test_c43_relache_au_plus_une_fois_par_24_h(banc):
    banc.poser_plafond(5, cree_le=T0 - 3 * JOUR, dernier_sature=T0 - 2 * JOUR)
    assert banc.verdict(0).calibration == "relache"
    banc.horloge.avancer(60)
    assert banc.verdict(0).calibration == "stable"
    assert banc.appris() == 6
    banc.horloge.avancer(JOUR)
    assert (banc.verdict(0).calibration, banc.appris()) == ("relache", 7)


def test_c44_a_est_l_accord_accordes_compris(banc):
    banc.poser_plafond(4, cree_le=T0 - 3600)
    assert banc.verdict(2, l1=5.0).peut_ajouter == 2           # accord : 2 + LIBRE 2 = 4
    banc.horloge.avancer(400)
    v = banc.verdict(1, l1=12.5)                                # le relevé dit 1 : la charge est en retard
    assert (v.calibration, v.plafond) == ("descend", 3)


def test_vingt_saturations_a_un_jamais_zero(banc):
    for _ in range(20):
        banc.verdict(0)                                         # accord à 0 actif (BASE)
        banc.horloge.avancer(301)
        banc.verdict(1, l1=13.0)                                # probant, saturé
        banc.horloge.avancer(301)
    assert banc.appris() == 1
    v = banc.verdict(0)
    assert v.plafond == 1 and v.peut_ajouter >= 1


def test_plafond_json_corrompu_vaut_dur(banc):
    banc.dossier.mkdir(parents=True)
    (banc.dossier / cp.NOM_PLAFOND).write_text("{cassé", encoding="utf-8")
    v = banc.verdict(0)
    assert (v.plafond, v.source) == (12, "illisible")
    assert any("illisible" in a for a in v.avertissements)
    assert (banc.dossier / (cp.NOM_PLAFOND + ".illisible")).read_text(encoding="utf-8") == "{cassé"
    assert banc.appris() is None                                # réparé : rien d'appris, DUR du moment


@pytest.mark.parametrize("plafond", [0, -3, "9", True, 2.5])
def test_entree_absurde_vaut_dur(banc, plafond):
    banc.poser_plafond(plafond, cree_le=T0)
    assert (banc.verdict(0).plafond, banc.appris()) == (12, None)


def test_json_imbrique_sans_fond_vaut_illisible(banc, capsys):
    """`json.loads` sur 200 000 niveaux lève RecursionError (mesuré : « Stack overflow … decoding a JSON
    array »), qui n'est PAS une ValueError : plafond.json, une ligne de relevé et la déclaration la rattrapent."""
    profond = "[" * 200_000 + "]" * 200_000
    banc.dossier.mkdir(parents=True)
    (banc.dossier / cp.NOM_PLAFOND).write_text(profond, encoding="utf-8")
    valide = {"ts": T0 - 1000, "cle": "banc|18", "actifs": 0, "peut_ajouter": 0}
    (banc.dossier / cp.NOM_RELEVES).write_text(profond + "\n" + json.dumps(valide) + "\n", encoding="utf-8")
    banc.config.parent.mkdir(parents=True)
    banc.config.write_text(profond, encoding="utf-8")
    v = banc.verdict(0)
    assert (v.plafond, v.source, v.releves) == (12, "illisible", 2)
    assert any("plafond déclaré ignoré" in a for a in v.avertissements)
    assert cp.main(["declarer", "--max", "4", "--motif", "S-banc"], sources=sources(),
                   horloge=Horloge()) == 0                       # config_home du banc : vide, accepte
    (Path(os.environ["CADRE_CONFIG_HOME"]) / cp.NOM_CONFIG).write_text(profond, encoding="utf-8")
    capsys.readouterr()
    assert cp.main(["declarer", "--max", "4", "--motif", "S-banc"], sources=sources(), horloge=Horloge()) == 1
    assert "illisible (RecursionError)" in capsys.readouterr().err


def test_entier_json_geant_vaut_illisible_sans_traceback(banc, capsys):
    """Avis MEDIUM de la sécurité : un entier JSON ≥ 10^309 dans `cree_le` ou `ts` levait OverflowError
    (`float()` / `math.isfinite`) et `verdict` s'arrêtait sur un traceback tant que le fichier restait."""
    geant = "1" + "0" * 400
    assert cp.nombre(10 ** 400) is None and cp._horodatage(10 ** 400) is None
    banc.dossier.mkdir(parents=True)
    (banc.dossier / cp.NOM_PLAFOND).write_text(
        '{"version": 1, "postes": {"banc|18": {"plafond": 5, "cree_le": %s}}}' % geant, encoding="utf-8")
    v = banc.verdict(0)
    assert (v.plafond, v.source, v.peut_ajouter) == (12, "illisible", 5)
    (banc.dossier / cp.NOM_RELEVES).write_text(
        '{"ts": %s, "cle": "banc|18", "actifs": 2, "peut_ajouter": 2}\n' % geant, encoding="utf-8")
    assert cp.dernier_accord([{"ts": 10 ** 400, "cle": "banc|18", "actifs": 2, "peut_ajouter": 2}],
                             "banc|18") is None
    banc.horloge.avancer(10)
    v = banc.verdict(1)                                         # le relevé géant est sauté : rien de TENU
    assert (v.peut_ajouter, v.releves, v.etat) == (11, 1, "ok")
    assert cp.main(["releve", "--poste", "banc"], sources=sources(loadavg=lambda: (1.0, 1.0, 1.0))) == 0
    assert "RELEVES=" in capsys.readouterr().out


def test_jamais_au_dessus_de_dur_borne_a_l_usage(banc):
    banc.poser_plafond(50, cree_le=T0 - 3 * JOUR)
    assert banc.verdict(10, l1=1.0, l5=1.0).peut_ajouter == 2  # accord : 10 + 2 = 12
    banc.horloge.avancer(400)
    v = banc.verdict(12, l1=1.0, l5=1.0)                        # probant, sain, au plafond : déjà DUR
    assert (v.plafond, v.calibration) == (12, "stable")
    banc.horloge.avancer(2 * JOUR)
    assert (banc.verdict(0).plafond, banc.verdict(0).calibration) == (12, "stable")
    assert banc.appris() == 50                                  # la borne n'est jamais recopiée sur disque


def test_jamais_au_dessus_de_dur_meme_non_mesurable(banc):
    banc.poser_plafond(50, cree_le=T0)
    v = banc.verdict(0, charge=False)
    assert (v.source, v.plafond, banc.appris()) == ("non-mesurable", 5, 50)


def test_declarer_deux_puis_douze_rend_douze(tmp_path, capsys):
    """MAJEUR 2 de l'exec-critic : la borne DUR=2 était recopiée dans plafond.json, et `declarer 12` laissait
    `PLAFOND=2 SOURCE=appris`."""
    s = sources(loadavg=lambda: (1.0, 1.0, 1.0))
    for m, attendu in ((2, "PLAFOND=2 BASE=2 SOURCE=declare"), (12, "PLAFOND=12 BASE=9 SOURCE=declare")):
        assert cp.main(["declarer", "--max", str(m), "--motif", "S-banc", "--poste", "banc"], sources=s,
                       horloge=Horloge()) == 0
        assert cp.main(["verdict", "--actifs", "0", "--poste", "banc"], sources=s, horloge=Horloge()) == 0
        assert capsys.readouterr().out.splitlines()[-4] == attendu


def test_appris_survit_a_une_declaration_plus_basse(banc):
    banc.poser_plafond(10, cree_le=T0 - 3600)
    banc.verdict(8, l1=5.0)                                     # accord : 8 + LIBRE 2 = 10
    banc.horloge.avancer(400)
    assert banc.verdict(10, l1=12.5).plafond == 9               # appris 9
    banc.declarer(4)
    assert (banc.verdict(0).plafond, banc.verdict(0).source, banc.appris()) == (4, "declare", 9)
    banc.declarer(12)
    assert (banc.verdict(0).plafond, banc.verdict(0).source, banc.appris()) == (9, "appris", 9)


def test_plafond_json_non_reecrit_quand_rien_ne_change(banc):
    banc.poser_plafond(9, cree_le=T0 - 3600)
    avant = (banc.dossier / cp.NOM_PLAFOND).read_bytes()
    assert banc.verdict(0).calibration == "stable"
    assert (banc.dossier / cp.NOM_PLAFOND).read_bytes() == avant


def test_calibrer_borne_haute_et_basse_en_direct():
    e = cp.Entree(12, T0 - 3 * JOUR)
    suivante, action = cp.calibrer(e, actifs=12, charge=(1.0, 1.0, 1.0), pression=1, c=18, dur=12,
                                   accord=cp.Accord(T0 - 400, 10, 2), maintenant=T0)
    assert (suivante.plafond, action) == (12, "stable")
    un = cp.Entree(1, T0)
    accord = cp.Accord(T0 - 400, 0, 1)
    suivante, _ = cp.calibrer(un, actifs=1, charge=(13.0, 13.0, 1.0), pression=1, c=18, dur=12, accord=accord,
                              maintenant=T0)
    assert suivante.plafond == 1


# =========================================================================== plafond partagé (T-01M56Q23NH)
# Chaque témoin pose ou retire CLAUDE_PID par `sessions` (monkeypatch) ; C = 18, P = 12, charge 3/3 sauf mention.
@pytest.fixture(scope="module")
def _claude_pid_herite():
    """Un CLAUDE_PID HÉRITÉ, posé AVANT `_poste_isole` (une fixture de portée module s'installe avant toute
    fixture de fonction, autouse comprise) : le témoin C60 rougit sans dépendre de l'environnement du lanceur.
    Il reste posé jusqu'à la fin du module — chaque test suivant le voit donc retiré par `_poste_isole`."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("CLAUDE_PID", str(os.getpid()))
        yield


def test_poste_isole_retire_claude_pid(_claude_pid_herite):
    """C60 : la fixture autouse retire un CLAUDE_PID hérité (rouge si le `delenv` saute, même hors Claude Code)."""
    assert "CLAUDE_PID" not in os.environ


def test_propres_deduits_des_actifs(banc, sessions):
    """C59 : même session, ACTIFS = 0 ⇒ 9 ; 60 s plus tard ses 9 agents tournent, ACTIFS = 9 ⇒ TENU =
    max(0, 9 − 9) = 0, LIBRE = 3. Sans « − ACTIFS », les 9 compteraient deux fois ⇒ 0."""
    sessions.appelant(PID_A)
    assert banc.verdict(0, l1=3.0, l5=3.0).peut_ajouter == 9
    banc.horloge.avancer(60)
    assert banc.verdict(9, l1=3.0, l5=3.0).peut_ajouter == 3


def test_c44_tenu_poste_entier(banc, sessions):
    """C50 : B tient 10 (5 min à 12,5 ⇒ 0 accordé) ; A, ACTIFS = 1, reçoit LIBRE = 12 − 1 − 10 = 1 (tenu 10).
    400 s plus tard B sature : a = 1 + 1 + 10 = 12 ⇒ appris 11 — jamais 1 (a sans tenu = 2)."""
    sessions.appelant(PID_B)
    v = banc.verdict(10, l1=11.0, l5=12.5)
    assert (v.peut_ajouter, v.doit_redescendre_a) == (0, None)
    banc.horloge.avancer(60)
    sessions.appelant(PID_A)
    assert banc.verdict(1, l1=5.0).peut_ajouter == 1
    banc.horloge.avancer(400)
    sessions.appelant(PID_B)
    v = banc.verdict(11, l1=12.5)
    assert (v.calibration, v.plafond, banc.appris()) == ("descend", 11, 11)


@pytest.mark.parametrize("tenu, lu", [(10, 10), (None, 0), (-1, 0), (True, 0), ("3", 0)])
def test_dernier_accord_tenu_ancien_ou_invalide_vaut_zero(tenu, lu):
    releve = {"ts": T0, "cle": "banc|18", "actifs": 1, "peut_ajouter": 1}
    if tenu is not None:
        releve["tenu"] = tenu
    assert cp.dernier_accord([releve], "banc|18") == cp.Accord(T0, 1, 1, lu)


def test_anonyme_voit_les_sessions(banc, sessions):
    """C65/C72 : B identifiée, ACTIFS = 10 ⇒ accordé 2 ; puis un appelant ANONYME à ACTIFS = 1 ⇒ TENU =
    Σ(B : 10 + 2) = 12 ⇒ 0. Sans la Σ des sessions, l'anonyme recevrait 11 (24/12 sur le poste)."""
    sessions.appelant(PID_B)
    assert banc.verdict(10, l1=3.0, l5=3.0).peut_ajouter == 2
    banc.horloge.avancer(60)
    sessions.appelant(None)
    assert banc.verdict(1, l1=3.0, l5=3.0).peut_ajouter == 0


def test_c39_anonyme_puis_session_identifiee(banc, sessions):
    """C39 : un Codex sans session, ACTIFS = 3 ⇒ 9 ; une seconde plus tard une session identifiée à ACTIFS = 3
    ⇒ 0 : les 9 accords anonymes restent TENUS, jamais déduits de l'ACTIFS d'une session identifiée."""
    sessions.appelant(None)
    assert banc.verdict(3, l1=3.0, l5=3.0).peut_ajouter == 9
    banc.horloge.avancer(1)
    sessions.appelant(PID_A)
    assert banc.verdict(3, l1=3.0, l5=3.0).peut_ajouter == 0


def test_c39_meme_pid_second_appelant(banc, sessions):
    """C39 : même CLAUDE_PID (sous-agent au PID du principal) — ACTIFS = 3 ⇒ 9 ; puis un second appelant au même
    PID, ACTIFS = 2 ⇒ TENU = max(0, 9 − 2) = 7, LIBRE = 3 : au plus 3, surcompte nommé au § Risques."""
    sessions.appelant(PID_A)
    assert banc.verdict(3, l1=3.0, l5=3.0).peut_ajouter == 9
    banc.horloge.avancer(1)
    assert banc.verdict(2, l1=3.0, l5=3.0).peut_ajouter == 3


def test_session_au_pid_mort_liberee(banc, sessions):
    """Le dernier relevé d'une session ne la tient que tant que son CLAUDE_PID est VIVANT."""
    sessions.appelant(PID_B)
    assert banc.verdict(10, l1=3.0, l5=3.0).peut_ajouter == 2
    banc.horloge.avancer(60)
    sessions.appelant(PID_A)
    assert banc.verdict(1, l1=3.0, l5=3.0).peut_ajouter == 0
    sessions.mourir(PID_B)
    assert banc.verdict(1, l1=3.0, l5=3.0).peut_ajouter == 11


@pytest.mark.parametrize("age, peut", [(299, 0), (300, 1), (3599, 1), (3600, 11), (3605, 11)])
def test_session_expire_une_heure_apres_son_dernier_releve(banc, sessions, age, peut):
    """B, ACTIFS = 10, reçoit 2. Ses 2 accordés (relevé à ACTIFS ≥ 1) sont tenus 300 s : A, ACTIFS = 1, reçoit
    0 à t299, 1 à t300 (S-01M5BSJ7PB). Ses 10 actifs restent tenus jusqu'à 1 h après son dernier relevé, borne
    exclue (t3600 : libérée — `age < VIE_SESSION_S`, jamais `<=`) ⇒ 11."""
    sessions.appelant(PID_B)
    assert banc.verdict(10, l1=3.0, l5=3.0).peut_ajouter == 2
    banc.horloge.avancer(age)
    sessions.appelant(PID_A)
    assert banc.verdict(1, l1=3.0, l5=3.0).peut_ajouter == peut


@pytest.mark.parametrize("appelant_b", [PID_B, None], ids=["B-identifiee", "B-anonyme"])
@pytest.mark.parametrize("age, peut", [(60, 0), (299, 0), (301, 9), (3700, 9)])
def test_accord_de_tout_libre_a_actifs_un_tenu_300_s(banc, sessions, appelant_b, age, peut):
    """F1, régression de S-01M56Z5GT8 corrigée par S-01M5BSJ7PB : au repos (C = 18, P = 12), A à ACTIFS = 1
    reçoit tout LIBRE, 11. Avant, ces 11 étaient tenus 1 h : B à ACTIFS = 0 recevait 0 jusqu'à t3600. Désormais
    tenus 300 s seulement : B reçoit 0 dans les 300 s, puis min(BASE, P − actifs de A) = min(9, 11) = 9 —
    appelant identifié OU anonyme (les deux formules somment la même garde)."""
    sessions.appelant(PID_A)
    assert banc.verdict(1, l1=3.0, l5=3.0).peut_ajouter == 11
    banc.horloge.avancer(age)
    sessions.appelant(appelant_b)
    assert banc.verdict(0, l1=3.0, l5=3.0).peut_ajouter == peut


@pytest.mark.parametrize("appelant_b", [PID_B, None], ids=["B-identifiee", "B-anonyme"])
@pytest.mark.parametrize("age, peut", [(301, 3), (1800, 3), (3599, 3), (3600, 9)])
def test_accord_d_un_lanceur_a_vague_bloquante_tenu_une_heure(banc, sessions, appelant_b, age, peut):
    """Résidu nommé (CHARGE_POSTE.md § 7) : un accord à ACTIFS = 0 (lanceur à vague bloquante, borné par BASE)
    reste tenu jusqu'à 1 h — A reçoit 9 ; B à ACTIFS = 0 reçoit min(9, 12 − 9) = 3 jusqu'à t3599, 9 à t3600."""
    sessions.appelant(PID_A)
    assert banc.verdict(0, l1=3.0, l5=3.0).peut_ajouter == 9
    banc.horloge.avancer(age)
    sessions.appelant(appelant_b)
    assert banc.verdict(0, l1=3.0, l5=3.0).peut_ajouter == peut


@pytest.mark.parametrize("age, peut", [(200, 3), (299, 3), (300, 9)])
def test_retenue_des_accords_anonymes_300_s(banc, sessions, age, peut):
    """RETENUE_S = 300 : un accord anonyme de 9 (ACTIFS = 0, repos) occupe le plafond 300 s — une session
    identifiée à ACTIFS = 0 reçoit min(9, 12 − 9) = 3 à t200 et t299, 9 à t300."""
    sessions.appelant(None)
    assert banc.verdict(0, l1=3.0, l5=3.0).peut_ajouter == 9
    banc.horloge.avancer(age)
    sessions.appelant(PID_A)
    assert banc.verdict(0, l1=3.0, l5=3.0).peut_ajouter == peut


def test_releve_porte_claude_pid_verifie_et_tenu(banc, sessions):
    sessions.appelant(PID_B)
    banc.verdict(10, l1=3.0, l5=3.0)
    banc.horloge.avancer(1)
    sessions.appelant(PID_A)
    banc.verdict(0, l1=3.0, l5=3.0)
    sessions.mourir(PID_A)                                      # CLAUDE_PID posé mais mort : appelant anonyme
    banc.verdict(0, l1=3.0, l5=3.0)
    lus = [json.loads(x) for x in (banc.dossier / cp.NOM_RELEVES).read_text(encoding="utf-8").splitlines()]
    assert [(r["claude_pid"], r["actifs"], r["peut_ajouter"], r["tenu"]) for r in lus] == [
        (PID_B, 10, 2, 0), (PID_A, 0, 0, 12), (None, 0, 0, 12)]


@pytest.mark.skipif(sys.platform.startswith("win"), reason="PID invérifiable sous Windows : supposé vivant")
def test_claude_pid_illisible_ou_mort_vaut_anonyme(monkeypatch):
    """Le canal réel : `os.kill(pid, 0)` sur ce processus (vivant) et sur un processus fini (mort)."""
    mort = subprocess.Popen([sys.executable, "-c", "pass"])
    mort.wait(timeout=60)
    for brut, attendu in ((str(os.getpid()), os.getpid()), (str(mort.pid), None), ("abc", None), ("0", None),
                          ("-1", None), ("", None), ("12345678901", None), (" 42", None)):
        monkeypatch.setenv("CLAUDE_PID", brut)
        assert cp.session_appelante() == attendu, brut
    monkeypatch.delenv("CLAUDE_PID")
    assert cp.session_appelante() is None


@pytest.mark.skipif(sys.platform.startswith("win"), reason="PID invérifiable sous Windows : supposé vivant")
def test_pid_vivant_eperm_vaut_vivant(monkeypatch):
    """EPERM (PermissionError) : le processus EXISTE, appartenant à un autre utilisateur — il reste TENU."""
    def refuse(pid, sig):
        raise PermissionError(1, "Operation not permitted")
    monkeypatch.setattr(cp.os, "kill", refuse)
    assert cp.pid_vivant(123) is True


def test_pression_2_au_repos_redescend_a_base(banc):
    """Décision tracée (correction lot A, T-01M56Q23NH) : PRESSION 2 au repos (3/3) ⇒ aucun départ, et
    DOIT_REDESCENDRE_A = BASE = 9 (le plan : DOIT = BASE) — jamais la retenue de 5 hors repos."""
    v = banc.verdict(0, l1=3.0, l5=3.0, pression=2)
    assert (v.peut_ajouter, v.doit_redescendre_a) == (0, 9)


# =========================================================================== bout en bout (forme seule)
def test_bout_en_bout_lang_fr(tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CADRE_", "XDG_"))}
    env.update(LANG="fr_FR.UTF-8", HOME=str(tmp_path / "home"), CADRE_STATE_DIR=str(tmp_path / "e2e"),
               CADRE_CONFIG_HOME=str(tmp_path / "e2e-conf"))
    sortie = subprocess.run([sys.executable, str(HERE / "charge_poste.py"), "verdict", "--actifs", "0"],
                            capture_output=True, text=True, encoding="utf-8", timeout=60, env=env, check=False)
    assert sortie.returncode == 0, sortie.stderr
    lignes = sortie.stdout.splitlines()
    assert re.fullmatch(r"PLAFOND=\d+ BASE=[1-9]\d* SOURCE=(appris|defaut|declare|illisible|non-mesurable)",
                        lignes[0])                              # BASE monte au-dessus de cinq au repos
    assert re.fullmatch(r"PEUT_AJOUTER=\d+ DOIT_REDESCENDRE_A=(\d+|-) ACTIFS=0", lignes[1])
    assert re.fullmatch(r"CHARGE=(\d+\.\d\d/\d+\.\d\d/\d+\.\d\d|inconnu) C=(\d+|inconnu) PRESSION=(1|2|4|inconnu) "
                        r"EDR_CPU=(\d+\.\d|inconnu)", lignes[2])
    assert re.fullmatch(r"CALIBRATION=(monte|descend|relache|stable|non-inscriptible) RELEVES=\d+ "
                        r"ETAT=(ok|non-inscriptible)", lignes[3])
    assert (tmp_path / "e2e" / cp.NOM_DOSSIER_ETAT / cp.NOM_RELEVES).is_file()
