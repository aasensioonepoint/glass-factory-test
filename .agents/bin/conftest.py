"""Isolation de l'état MACHINE des bancs de `.agents/bin/` — T-00000758 (BK-422).

`CADRE_STATE_DIR` y devient une PROPRIÉTÉ de chaque test, en portée fonction (BORNE
plus bas), plus une DISCIPLINE d'héritage.
Avant cette fixture, l'isolation de `migrate_index_to_db.db_path` tenait par deux
corps de `setUp` et par chaque sous-classe qui appelait `super().setUp()` : une
sous-classe qui l'oubliait, ou un module neuf qui pilotait `mig.cli` hors de
`_Case`, retombait EN SILENCE sur la valeur héritée — mesure du plan-critic it.4
de T-00000668 (S-00002278).

Le filet de session du `conftest.py` RACINE (`_isolation_state_dir_session`) ne
ferme pas ce trou : il ne pose `CADRE_STATE_DIR` que si l'appelant ne l'a PAS
posé, et partage UNE valeur pour toute la session. Un appelant qui exporte
`CADRE_STATE_DIR` vers le vrai `~/.local/state/cadre` y envoie donc tous les
bancs, et deux bancs d'une même session se voient l'un l'autre.

Cette fixture, elle, FORCE une valeur NEUVE par test, que l'appelant en ait posé
une ou non, sur le modèle de `_isolation_state_home`
(`.agents/evals/test_cadre_ledger_stores.py`, à relocaliser par son nom). Elle
tourne AVANT le `setUp` d'un `unittest.TestCase` et avant le corps d'un test : un
banc qui pose sa propre valeur (`setUp`, `mock.patch.dict`, `monkeypatch`)
l'écrase ensuite, et c'est voulu. Le dossier est un FRÈRE du `tmp_path` du test,
jamais un enfant : un banc qui inventorie son `tmp_path` n'y trouve rien de plus.

Elle tient sa valeur par SON PROPRE `pytest.MonkeyPatch`, jamais par la fixture
`monkeypatch` qu'elle partagerait avec le test : un `monkeypatch.undo()` dans le
corps d'un banc (huit sites de bancs dans `.agents/bin/` ; la commande `LC_ALL=C
git grep -n 'monkeypatch.undo()' -- '.agents/bin/*.py'` rend aussi les trois lignes
de cette docstring) ramène `CADRE_STATE_DIR` au dossier de CE test, jamais à la
valeur de l'appelant. La garde est rendue au démontage
de la fixture, après celui du `monkeypatch` du test tant qu'aucune fixture
`autouse` du `conftest.py` racine ne demande `monkeypatch` (aucune aujourd'hui,
relu par nom). BORNE : un banc qui écrit
`os.environ["CADRE_STATE_DIR"]` directement, ou qui vide `os.environ` sans le
restaurer, la défait encore jusqu'à la fin de ce test — rien ici ne l'empêche.

BORNE : portée FONCTION. `setUpClass`/`setUpModule`, une fixture
`scope="class"|"module"|"session"` et le code exécuté à l'import voient encore la
valeur de l'appelant (mesuré : sentinelle relevée dans les trois cas) ; seul
`setUpClass` aujourd'hui (`LC_ALL=C git grep -nE 'def (setUpClass|setUpModule)'
-- '.agents/bin/*.py'`) : `test_tasks_retour.py:249` (`Temoins`, à relocaliser
par son nom), auto-isolé — son `Depot` pose son propre `CADRE_STATE_DIR`.

BORNE : seul pytest charge ce fichier. `python3 .agents/bin/test_x.py` ou
`python -m unittest` n'en héritent pas ; là, l'isolation reste celle que chaque
banc pose lui-même.

UN EFFET DE BORD À ANNULER, MESURÉ. Ni `.agents/` ni `.agents/bin/` n'est un
paquet : pytest (mode `prepend`) importe ce fichier sous le nom `conftest`, après
avoir RETIRÉ de `sys.modules` le `conftest.py` racine. Sept sites font
`from conftest import greffe_email_git_franchissable` au moment d'une fixture
(`LC_ALL=C git grep -n 'from conftest import' -- '*.py'`), dans `.agents/evals/`
et `agentic_v3/tests/`, collectés APRÈS ce répertoire. Sans le pont ci-dessous,
`pytest .agents/bin/test_stop_reindex_domaine.py
.agents/evals/test_cadre_ledger_redaction.py agentic_v3/tests/test_v3_pipeline.py`
rendait `2 passed, 38 errors` (`ImportError … from 'conftest'
(.agents/bin/conftest.py)`), alors que `pytest .agents/bin` seul restait vert.
`pytest_configure` remet donc le module racine DÉJÀ CHARGÉ sous ce nom, sans
rien ré-exécuter : un import `from conftest import …` résout comme si ce
fichier n'existait pas, quel que soit le nom importé.

Témoins (`.agents/evals/test_cadre_state_partition.py`, Témoin 12, le « T9 » de
l'énoncé de T-00000758) : `test_la_fixture_de_agents_bin_FORCE_un_CADRE_STATE_DIR_neuf_par_test`
l'observe sur un VRAI banc de ce répertoire, dans un sous-processus pytest, et
rougit si elle disparaît, cesse d'être `autouse`, respecte la valeur de
l'appelant ou partage un dossier entre deux tests ;
`test_la_garde_TIENT_jusqu_a_la_fin_d_un_banc_qui_appelle_monkeypatch_undo` la
relève en FIN de test sur un banc qui appelle `monkeypatch.undo()`, et rougit si
elle repasse par la fixture `monkeypatch` partagée ;
`test_le_conftest_de_agents_bin_n_ombre_pas_le_conftest_racine` rougit si le pont
disparaît.
"""

from __future__ import annotations

import importlib.util
import itertools
import sys
import types
from collections.abc import Iterator
from pathlib import Path

import pytest


def _amorcer_vendor() -> None:
    """T-01M5BXTGX5YN8XEXTG1PP7A5ZX (phase D) : les parents de `cadre` et `agentic_v3`
    de CET arbre (résolveur `vendor_paths.py`, frère chargé par chemin) AJOUTÉS EN
    QUEUE de `sys.path` s'ils manquent (`amorcer_conftest`), jamais en tête : le
    paquet de l'adoptant, plus haut, garde la priorité. Résolveur absent ou
    illisible : rien n'est ajouté, l'état d'avant (témoin : `test_vendor_setup.py`).
    BORNE : l'ajout EN QUEUE rend le `src/` de l'adoptant (ancienne disposition)
    importable par son nom dans ses tests, là où `charger_paquet` le tient hors de `sys.path`."""
    try:
        chemin = Path(__file__).resolve().with_name("vendor_paths.py")
        spec = importlib.util.spec_from_file_location("_conftest_bin_vendor_paths", chemin)
        resolveur = importlib.util.module_from_spec(spec)
        existant = sys.modules.get(spec.name)
        sys.modules[spec.name] = resolveur  # enregistré AVANT `exec_module` (T-00000134) ; s'il lève, l'entrée d'avant
        try:
            spec.loader.exec_module(resolveur)
        except BaseException:
            if existant is not None:
                sys.modules[spec.name] = existant
            else:
                sys.modules.pop(spec.name, None)
            raise
        resolveur.amorcer_conftest(chemin.parents[2])
    except Exception:  # noqa: BLE001 — résolveur absent ou illisible : aucun amorçage
        return


_amorcer_vendor()

#: Le numéro du prochain dossier d'état : un compteur, pas un `mktemp` numéroté,
#: parce que ce dernier relit le dossier parent à chaque appel.
_NUMERO = itertools.count()


@pytest.fixture(scope="session")
def _racine_des_etats_cadre(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Le parent, sous le `basetemp` de pytest, des dossiers d'état de chaque test."""
    return tmp_path_factory.mktemp("cadre_state")


@pytest.fixture(autouse=True)
def _isolation_cadre_state_dir(_racine_des_etats_cadre: Path) -> Iterator[None]:
    """Pose `CADRE_STATE_DIR` sur un dossier neuf et CRÉÉ, propre à ce test.

    Son propre `MonkeyPatch`, pas la fixture `monkeypatch` : un `undo()` du test
    ne la défait pas (docstring du module)."""
    etat = _racine_des_etats_cadre / f"t{next(_NUMERO)}"
    etat.mkdir()
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("CADRE_STATE_DIR", str(etat))
        yield


def pytest_configure(config: pytest.Config) -> None:
    """Rend à `sys.modules["conftest"]` le `conftest.py` racine, si CE fichier l'a ombré.

    Hook historique : appelé à l'enregistrement de ce conftest quand pytest est
    déjà configuré (conftest découvert en descente : pluggy rejoue l'historique,
    `_maybe_apply_history`), sinon à `Config._do_configure` (conftest initial,
    importé avant la configuration) — dans les deux cas avant le premier `from
    conftest import` d'un banc. Lu dans pytest 9.1.1 et pluggy 1.6.0, à relire
    par nom. Rien n'est touché quand l'entrée n'est pas ce fichier ni quand la
    racine n'en a pas chargé (adoptant sans `conftest.py` racine, `--confcutdir`
    sous ce répertoire).

    BORNE MESURÉE : le pont ne sert que `prepend` (défaut, porte et CI). Sous
    `--import-mode=importlib`, `from conftest import` résout par `sys.path`, où les
    bancs d'ici placent ce répertoire DEVANT la racine (`sys.path.insert(0,
    str(HERE))` de `test_stop_reindex_domaine.py`) : `pytest --import-mode=importlib
    .agents/bin/test_stop_reindex_domaine.py .agents/evals/test_cadre_ledger_redaction.py
    agentic_v3/tests/test_v3_pipeline.py` => 2 passed, 38 errors (38 passed quand
    aucun banc de `.agents/bin/` n'est lancé avec eux). Sous `append`, ce fichier
    lève `ImportPathMismatchError` au chargement.
    """
    ombre = sys.modules.get("conftest")
    ici = Path(__file__).resolve()
    if ombre is None or Path(getattr(ombre, "__file__", "") or "").resolve() != ici:
        return
    racine = ici.parents[2] / "conftest.py"
    for plugin in config.pluginmanager.get_plugins():
        fichier = getattr(plugin, "__file__", None) if isinstance(plugin, types.ModuleType) else None
        if fichier and Path(fichier).resolve() == racine:
            sys.modules["conftest"] = plugin
            return
