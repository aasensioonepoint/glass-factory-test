"""Témoin de `python -m agentic_v3 dashboard-summary` (T-00001066).

Le verbe lisait le store par `store.get_db_connection`, un attribut d'INSTANCE qui
n'existe pas : `get_db_connection` est une fonction de MODULE de
`agentic_v3.db.schema`. Résultat : `AttributeError`, rc 1, sur tout store sain. Ce
banc lance le VRAI verbe dans un SOUS-PROCESSUS — le seul canal où le verbe tourne
tel qu'un appelant le lance — et lit son rc, son stdout et son stderr.

AUCUNE variable `ROOT` liée à `__file__` : le fichier voyage avec `agentic_v3/` et
n'a rien à nommer sur la racine réelle, donc `test_adopting_gate` ne le balaye pas.

SEMENCE : cinq événements, trois tâches projetées (T-4 n'a que CODE_GENERATED).
Le quatrième (`SPEC_MUTATION_CANCEL` sur `T-3`, tâche jamais créée) entre au
registre mais ne crée aucune ligne de projection (son `UPDATE` ne touche rien) ;
le cinquième (`CODE_GENERATED` sur `T-4`, sans `TASK_CREATED`) en crée une (son
`UPSERT`). Le registre compte QUATRE `task_id` distincts et DEUX `TASK_CREATED`,
la projection TROIS. Un compte de tâches lu sur le registre au lieu de la
projection rend donc 4 (tâches distinctes) ou 2 (`TASK_CREATED`), jamais 3.

BORNES ÉCRITES : darwin mesuré, Linux supposé, Windows non mesuré. Le chemin
« reconstruit depuis runs/ » et le store sous écrivain WAL sont mesurés (T-00001066,
rc 0), pas épinglés ici. `COUNT(DISTINCT ulid)` à la place de `COUNT(*)` n'est pas
séparé : `append_event` pose toujours un ulid, seule une ligne historique à ulid
NULL le distinguerait, et la semer demanderait du SQL hors du vrai canal. Le
témoin 3 prouve que la lecture OUVRE la couture `schema.get_db_connection` ; il ne
prouve pas qu'elle n'ouvre RIEN d'autre.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import agentic_v3

# Parent du PAQUET : `agentic_v3/__init__.py` -> `agentic_v3/` -> la racine qui le porte.
RACINE_DU_PAQUET = str(Path(agentic_v3.__file__).resolve().parents[1])

SEMENCE = """
from agentic_v3.db.event_store import EventStore
s = EventStore()
s.append_event('T-1', 'dev', 'TASK_CREATED', {'req_id': 'R1'})
s.append_event('T-1', 'dev', 'CODE_GENERATED', {'code_diff': 'x'})
s.append_event('T-2', 'dev', 'TASK_CREATED', {'req_id': 'R2'})
s.append_event('T-3', 'dev', 'SPEC_MUTATION_CANCEL', {})
s.append_event('T-4', 'dev', 'CODE_GENERATED', {'code_diff': 'y'})
"""

# L'espion se pose AVANT l'import de `agentic_v3.cli` : le `from … import` de `cli`
# lie alors l'espion, et un homonyme local qui contournerait la couture ne passe pas
# par lui. Il se pose aussi sur les deux liaisons qui existent déjà (`event_store`,
# `agentic_v3.db`) : une lecture déplacée dans une méthode d'`EventStore`, ou dans
# un module importé APRÈS la pose de l'espion, reste verte ; un module chargé avant
# l'espion (par `agentic_v3/db/__init__.py`) ou qui ouvre le store par ses propres
# moyens la rougit. Il ne compte que les ouvertures APRÈS la construction de
# l'`EventStore`.
ESPION = """
import sys
import agentic_v3.db as db
import agentic_v3.db.schema as schema
import agentic_v3.db.event_store as es

reel = schema.get_db_connection
etat = {"construit": False, "ouvertures": 0}

def espion(*args, **kwargs):
    if etat["construit"]:
        etat["ouvertures"] += 1
    return reel(*args, **kwargs)

for module in (schema, es, db):
    module.get_db_connection = espion

init = es.EventStore.__init__

def init_espion(self, *args, **kwargs):
    init(self, *args, **kwargs)
    etat["construit"] = True

es.EventStore.__init__ = init_espion

import agentic_v3.cli as cli

sys.argv = ["agentic_v3", "dashboard-summary"]
cli.main()
print("ESPION", etat["ouvertures"], file=sys.stderr)
"""


FERMETURE = """
import sys
import agentic_v3.db as db
import agentic_v3.db.schema as schema
import agentic_v3.db.event_store as es

mode = sys.argv[1]
reel = schema.get_db_connection
etat = {"construit": False, "ouvertes": 0, "fermees": 0}


class Suivie:
    def __init__(self, conn):
        self._c = conn

    def cursor(self):
        if mode == "echec":
            raise RuntimeError("lecture en echec")
        return self._c.cursor()

    def close(self):
        etat["fermees"] += 1
        self._c.close()


def espion(*args, **kwargs):
    conn = reel(*args, **kwargs)
    if etat["construit"]:
        etat["ouvertes"] += 1
        return Suivie(conn)
    return conn


for module in (schema, es, db):
    module.get_db_connection = espion

init = es.EventStore.__init__


def init_espion(self, *args, **kwargs):
    init(self, *args, **kwargs)
    etat["construit"] = True


es.EventStore.__init__ = init_espion

import agentic_v3.cli as cli

sys.argv = ["agentic_v3", "dashboard-summary"]
try:
    cli.main()
except RuntimeError:
    pass
print("FERMETURE", etat["ouvertes"], etat["fermees"], file=sys.stderr)
"""


@pytest.fixture
def banc(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (tmp_path / "gitconfig").write_text("", encoding="utf-8")
    # Aucune variable GIT_* héritée (un `GIT_DIR` de crochet ferait résoudre la
    # racine du dépôt RÉEL), ni `PYTHONPATH`, ni la partition d'un appelant.
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("GIT_") and k not in ("CADRE_PROJECT_ROOT", "CADRE_STATE_DIR", "PYTHONPATH")
    }
    env.update(
        CADRE_PROJECT_ROOT=str(proj),
        CADRE_STATE_DIR=str(tmp_path / "state"),
        GIT_CONFIG_GLOBAL=str(tmp_path / "gitconfig"),
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CEILING_DIRECTORIES=str(tmp_path),
        PYTHONPATH=RACINE_DU_PAQUET,
    )

    def lancer(*args):
        return subprocess.run(
            [sys.executable, *args], cwd=proj, env=env, capture_output=True, text=True, timeout=120
        )

    return lancer


def test_store_peuple_compte_par_le_vrai_canal(banc):
    semence = banc("-c", SEMENCE)
    assert semence.returncode == 0, semence.stderr
    r = banc("-m", "agentic_v3", "dashboard-summary")
    assert r.returncode == 0, r.stderr
    assert "Traceback" not in r.stderr, r.stderr
    assert json.loads(r.stdout) == {"total_events": 5, "total_tasks": 3}, r.stdout


def test_store_neuf_rend_zero(banc):
    r = banc("-m", "agentic_v3", "dashboard-summary")
    assert r.returncode == 0, r.stderr
    assert "Traceback" not in r.stderr, r.stderr
    assert json.loads(r.stdout) == {"total_events": 0, "total_tasks": 0}, r.stdout


def test_lecture_par_la_couture_de_schema(banc):
    r = banc("-c", ESPION)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == {"total_events": 0, "total_tasks": 0}, r.stdout
    lignes = [l for l in r.stderr.splitlines() if l.startswith("ESPION ")]
    assert len(lignes) == 1, r.stderr
    assert int(lignes[0].split()[1]) >= 1, f"la lecture n'a pas ouvert la couture : {lignes[0]!r}"


@pytest.mark.parametrize("mode", ("ok", "echec"))
def test_la_connexion_de_lecture_est_fermee_meme_si_la_lecture_leve(banc, mode):
    r = banc("-c", FERMETURE, mode)
    lignes = [l for l in r.stderr.splitlines() if l.startswith("FERMETURE ")]
    assert len(lignes) == 1, r.stderr
    ouvertes, fermees = (int(x) for x in lignes[0].split()[1:3])
    assert (ouvertes, fermees) == (1, 1), f"connexion non fermee ({mode}) : {lignes[0]!r}"
