#!/usr/bin/env python3
"""T-00001089 — `tasks_sync._charger_events` mémoïsé par chemin RÉSOLU d'`events.py`.

Avant : chaque émission (`_signaler_degradation_v3`) ré-exécutait `events.py` dans un
module NEUF ; son cache `_cached_user` repartait vide, d'où un `git config user.name`
par événement. Après : un module par fichier, réutilisé. Deux gardes de fraîcheur :
un AUTRE chemin charge SON module (jamais celui d'un dépôt voisin), et un fichier
RÉÉCRIT (signature `st_mtime_ns`, `st_size`) est rechargé — le contrat de D31
(`test_tasks_pont_v3_deverse.py`), qui recharge le même chemin après réécriture.

Le compteur est un fichier : le faux `events.py` y ajoute une ligne à CHAQUE exécution,
sans rien supposer d'`importlib`. `tasks` est chargé par chemin sous un nom PROPRE,
`sys.modules[nom]` posé avant `exec_module` : son mémo n'est partagé avec aucun banc.

MUTANTS : aucun mémo (la BASE) ⇒ rouge A à E ; mémo à clé unique (un module pour
tous les chemins) ⇒ rouge B ; clé par chemin seul, sans signature ⇒ rouge C (et D31) ;
clé sur le chemin NON résolu ⇒ rouge D ; hit sans ré-enregistrement dans `sys.modules`
⇒ rouge F ; ré-enregistrement par affectation au lieu de `setdefault` ⇒ rouge F.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

BIN = Path(__file__).resolve().parent


def _charger(nom: str, chemin: Path):
    spec = importlib.util.spec_from_file_location(nom, chemin)
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(nom, None)
        raise
    return module


tasks = _charger("tasks_t1089_memo", BIN / "tasks.py")


class MemoEventsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.racine = Path(self.tmp.name)
        self.compteur = self.racine / "executions.txt"  # dossier neuf par test : clés de mémo neuves

    def _depot(self, nom: str, marque: str = "") -> Path:
        depot = self.racine / nom
        (depot / ".agents" / "bin").mkdir(parents=True, exist_ok=True)
        self._ecrire(depot, marque)
        return depot

    def _ecrire(self, depot: Path, marque: str = "") -> None:
        (depot / ".agents" / "bin" / "events.py").write_text(
            f"with open({str(self.compteur)!r}, 'a', encoding='utf-8') as f:\n"
            f"    f.write(__file__ + '\\n')\n"
            f"MARQUE = {marque!r}\n"
            "EMIS = []\n"
            "def emit(kind, **champs):\n"
            "    EMIS.append((kind, champs))\n",
            encoding="utf-8",
        )

    def _executions(self) -> int:
        return len(self.compteur.read_text(encoding="utf-8").splitlines()) if self.compteur.exists() else 0

    def test_A_n_emissions_un_seul_chargement(self) -> None:
        """Cinq émissions par le VRAI chemin d'appel : cinq `emit`, `events.py` exécuté UNE fois. BASE : 5."""
        depot = self._depot("a")
        for _ in range(5):
            tasks._signaler_degradation_v3(str(depot), str(depot), {}, "pont-v3-refuse")
        self.assertEqual(1, self._executions())
        self.assertEqual(5, len(tasks._charger_events(depot).EMIS))

    def test_B_deux_chemins_deux_modules_jamais_celui_du_voisin(self) -> None:
        a, b = self._depot("a", "A"), self._depot("b", "B")
        self.assertEqual("A", tasks._charger_events(a).MARQUE)
        self.assertEqual("B", tasks._charger_events(b).MARQUE)
        self.assertEqual("A", tasks._charger_events(a).MARQUE)
        self.assertIs(tasks._charger_events(b), tasks._charger_events(b))
        self.assertEqual(2, self._executions())

    def test_C_un_fichier_reecrit_est_recharge(self) -> None:
        """Le contrat de D31 : même chemin, contenu réécrit ⇒ nouveau chargement, jamais le module figé."""
        depot = self._depot("a", "v1")
        premier = tasks._charger_events(depot)
        self.assertIs(premier, tasks._charger_events(depot))
        self._ecrire(depot, "v2-plus-long")
        second = tasks._charger_events(depot)
        self.assertEqual("v2-plus-long", second.MARQUE)
        self.assertIsNot(premier, second)
        self.assertEqual(2, self._executions())

    def test_D_deux_chemins_vers_le_meme_fichier_un_seul_chargement(self) -> None:
        """La clé est le chemin RÉSOLU : un lien vers le dépôt ne recharge pas."""
        depot = self._depot("a")
        lien = self.racine / "lien"
        try:
            os.symlink(depot, lien, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"lien symbolique impossible ici : {exc}")
        self.assertIs(tasks._charger_events(depot), tasks._charger_events(lien))
        self.assertEqual(1, self._executions())

    def test_E_le_vrai_events_py_ne_lance_qu_un_git_config_pour_n_evenements(self) -> None:
        """Le défaut mesuré, sur le VRAI `events.py` : N événements, UN `git config user.name`. BASE : N."""
        appels: list[list[str]] = []

        def faux_run(argv, *a, **k):
            appels.append(list(argv))
            return subprocess.CompletedProcess(argv, 0, stdout="banc\n", stderr="")

        evenements = self.racine / "evenements"
        evenements.mkdir()
        depot = BIN.parent.parent
        with mock.patch.dict(os.environ, {"AGENTS_EVENTS_DIR": str(evenements)}), \
                mock.patch.object(subprocess, "run", side_effect=faux_run):
            for _ in range(4):
                tasks._signaler_degradation_v3(str(depot), str(depot), {}, "pont-v3-refuse")
        self.assertEqual(1, sum(1 for a in appels if a[:3] == ["git", "config", "user.name"]), appels)
        self.assertEqual(4, sum(len(p.read_text(encoding="utf-8").splitlines())
                                for p in evenements.iterdir() if p.is_file()))

    def test_F_un_hit_reenregistre_le_module_qu_un_tiers_a_retire(self) -> None:
        """Sécurité LOW : un tiers retire `sys.modules[spec.name]` ; le hit suivant le RÉ-ENREGISTRE, sans
        ré-exécuter. `setdefault`, jamais une affectation : `spec.name` est UNE constante pour tous les
        chemins, donc après le chargement de B un hit sur A laisse B en place. BASE : absent après le hit."""
        depot = self._depot("a")
        module = tasks._charger_events(depot)
        sys.modules.pop(module.__name__, None)
        self.assertIs(module, tasks._charger_events(depot))
        self.assertIs(module, sys.modules.get(module.__name__))
        self.assertEqual(1, self._executions())
        voisin = tasks._charger_events(self._depot("b", "B"))
        self.assertIs(module, tasks._charger_events(depot))
        self.assertIs(voisin, sys.modules.get(module.__name__))


if __name__ == "__main__":
    unittest.main()
