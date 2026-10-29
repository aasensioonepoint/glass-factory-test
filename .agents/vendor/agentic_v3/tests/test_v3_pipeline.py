"""Banc du noyau V3 SURVIVANT — event sourcing et Hot Spec Mutation.

CE QUE CE FICHIER A PERDU, ET POURQUOI (T-012, refonte packaging)
-----------------------------------------------------------------
Sept des neuf tests de ce banc ont ete RETIRES AVEC LEUR SUJET le 2026-09-12.
Ils ne sont pas casses par un refactor — ce qu'ils testaient n'existe plus, sur
decision tracee au registre et dans `docs/interne/classification.md` §4.

  test_phase3_mcp_gateway_isolation          -> `agentic_v3/mcp/` retire
  test_phase4_orchestrator_and_hot_spec…     -> `orchestrator/nodes.py` retire
  test_phase5_agent_execution_pydantic…      -> `agents/` retire
  test_phase6_visual_reconciliation          -> `reconciliation/visual_diff.py` retire
  test_blocked_dependency_and_human_decision -> `orchestrator/nodes.py` retire
  test_graph_syncs_full_workflow_statuses…   -> `orchestrator/graph.py` retire
  test_graph_syncs_blocked_route…            -> `orchestrator/graph.py` retire

LA MESURE QUI A DECIDE. Aucune surface du depot ne citait la sous-commande
`run-task`, seul chemin vers ce FSM ; `agents/base.py` renvoyait un dictionnaire
ecrit en dur au lieu d'appeler un modele, donc ses verdicts etaient fabriques ;
et `orchestrator/nodes.py` instanciait `EventStore` et `LessonsStore`, ce qui
viole « aucun acces disque depuis la logique d'orchestration ».

OU LES GARANTIES ONT ATTERRI — aucune n'est perdue sauf une, nommee plus bas.
  * La synchronisation du board (etat `blocked`, stage, supersession d'une
    commande perimee, outbox) reste couverte par `test_board_bridge.py`, qui
    l'eprouve sur `BoardBridge` DIRECTEMENT — 19 tests, sans passer par le FSU.
  * Le routage de la chaine reste en PROSE dans `/kickoff` et `AGENTS.md`,
    interprete par le LLM de l'hote : c'est la decision D1 de la refonte.
  * La fidelite visuelle est portee par la paire d'agents `frontend-fidelity`
    puis `design-review`, qui compare des styles CALCULES a des tokens.
  * SEULE PERTE REELLE : l'isolation d'outils MCP PAR ROLE que portait
    `mcp/gateway.py`. Elle n'etait appliquee nulle part — aucun appelant — mais
    rien ne la remplace non plus : `MCP_ALLOWLIST.md` est plat et enregistre des
    VERSIONS de serveurs auditees, pas un peril par role. Exigence reportee sur
    l'executeur de gates de la Phase 3, qui est le seul endroit ou elle peut
    etre APPLIQUEE plutot que declaree.
"""

import io
import sqlite3
import tempfile
from contextlib import redirect_stderr
from pathlib import Path

import pytest

from agentic_v3.db.event_store import EventStore
from agentic_v3.db.lessons_store import LessonsStore
from agentic_v3.ingestion.parse_specs import SpecParser


@pytest.fixture(autouse=True)
def _isolation_export_run(tmp_path, monkeypatch, request):
    """T-00000650 : chaque construction d'`EventStore`/`SpecParser` écrit son
    export sous une racine de TEST (`CADRE_PROJECT_ROOT`) et sa base sous
    `CADRE_STATE_DIR` — jamais sous le dépôt réel — avec un auteur FIXÉ (la jambe
    conteneur tourne en root sans `git config user.email` global).

    PORTE UNIQUE (L-00000500, T-00000695/696) : la greffe passe par
    `conftest.py::greffe_email_git_franchissable`. C'était la 6e greffe du dépôt et
    la SEULE posée par un `setattr` NU — donc NON franchissable : un témoin d'aval
    du vrai git posé dans ce fichier aurait été éteint en silence, pendant que la
    docstring de la porte annonçait « toutes les fixtures »."""
    from conftest import greffe_email_git_franchissable
    from agentic_v3.db import run_export

    proj = tmp_path / "proj"
    proj.mkdir()
    monkeypatch.setenv("CADRE_PROJECT_ROOT", str(proj))
    monkeypatch.setenv("CADRE_STATE_DIR", str(tmp_path / "state"))
    greffe_email_git_franchissable(monkeypatch, request, run_export)


@pytest.mark.email_git_reel
def test_la_greffe_email_git_est_franchissable_ici():
    """TÉMOIN (L-00000500, T-00000695/696) — la 6e greffe de `_email_git`, et la
    SEULE qui n'était pas franchissable : sous le marqueur `email_git_reel`, la
    fixture `_isolation_export_run` doit SAUTER sa greffe, et le VRAI `_email_git`
    rester en place (un def -> `__name__ == "_email_git"`, la greffe étant un
    `<lambda>`). MUTATION (rétablir le `monkeypatch.setattr` NU dans la fixture) :
    l'objet devient le `<lambda>` et cet assert rougit."""
    from agentic_v3.db import run_export

    assert run_export._email_git.__name__ == "_email_git", (
        "greffe NON franchie : la fixture de ce fichier ne passe pas par la porte "
        "unique `conftest.py::greffe_email_git_franchissable`"
    )


@pytest.fixture
def tmp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    Path(db_path).unlink(missing_ok=True)


def test_phase1_event_sourcing_and_lessons_limit(tmp_db):
    event_store = EventStore(tmp_db)
    lessons_store = LessonsStore(tmp_db)

    # Test Event Store
    event_id = event_store.append_event(
        task_id="TASK-100",
        agent_role="DevAgent",
        event_type="CODE_GENERATED",
        payload={"code_diff": "diff text"}
    )
    assert event_id > 0

    proj = event_store.get_task_projection("TASK-100")
    assert proj["status"] == "IN_DEV"
    assert proj["code_diff"] == "diff text"

    # Test Lessons Store max 3 limit
    for i in range(5):
        lessons_store.add_lesson(
            language="python",
            domain_tag="backend",
            error_pattern="syntax_error",
            lesson_text=f"Lesson {i+1}"
        )

    retrieved = lessons_store.query_lessons("python", "backend", "syntax_error", limit=10)
    assert len(retrieved) <= 3
    assert len(retrieved) == 3


def test_phase2_spec_parser_and_hot_mutation(tmp_db, tmp_path):
    spec_file = tmp_path / "spec.md"
    spec_file.write_text("# [REQ-AUTH-001] Authentication\nMust require 2FA.", encoding="utf-8")

    parser = SpecParser(tmp_db)
    results1 = parser.process_and_sync_spec(spec_file)
    assert len(results1) == 1
    slice1, is_mutated1 = results1[0]
    assert slice1.req_id == "REQ-AUTH-001"
    assert slice1.version == 1
    assert not is_mutated1

    # Modify spec to trigger Hot Spec Mutation
    spec_file.write_text("# [REQ-AUTH-001] Authentication\nMust require 2FA and Biometrics.", encoding="utf-8")
    results2 = parser.process_and_sync_spec(spec_file)
    slice2, is_mutated2 = results2[0]
    assert slice2.version == 2
    assert is_mutated2
    assert "Biometrics" in slice2.content_markdown
    assert slice2.spec_diff_from_previous is not None


# T-00001223 (décision pilote S-00004503) — la chaîne de versions de
# `spec_requirements` est propre à CHAQUE fichier : clé (file_path, req_id).
# L'ANCIEN DDL est écrit ici en littéral, jamais importé : ce banc doit
# s'importer sur l'ancien code pour y rougir par ses assertions.
_REQ = "REQ-X-001"
_ANCIEN_DDL_SPEC = """
    CREATE TABLE spec_requirements (
        req_id TEXT NOT NULL,
        version INTEGER NOT NULL DEFAULT 1,
        file_path TEXT NOT NULL,
        section_title TEXT NOT NULL,
        content_markdown TEXT NOT NULL,
        tags_json TEXT NOT NULL,
        PRIMARY KEY (req_id, version)
    )
"""


def _lire(db, sql, params=()):
    conn = sqlite3.connect(str(db))
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def _chaines(db):
    return _lire(db, "SELECT file_path, req_id, version FROM spec_requirements "
                     "ORDER BY file_path, version")


def _nb_spec_mutated(db):
    return _lire(db, "SELECT COUNT(*) FROM events_ledger "
                     "WHERE event_type='SPEC_MUTATED'")[0][0]


def _cle(db):
    rangs = sorted((l[5], l[1]) for l in _lire(db, "PRAGMA table_info(spec_requirements)") if l[5])
    return tuple(nom for _r, nom in rangs)


def _deux_specs(tmp_path):
    a, b = tmp_path / "a.md", tmp_path / "b.md"
    a.write_text(f"## Login [{_REQ}]\ncontenu de a\n", encoding="utf-8")
    b.write_text(f"## Login [{_REQ}]\ncontenu de b\n", encoding="utf-8")
    return a, b


def test_un_req_id_partage_entre_deux_fichiers_donne_deux_chaines(tmp_db, tmp_path):
    """Deux fichiers INCHANGÉS portant le même tag : syncs a, b, a, b -> aucune
    mutation, une v1 par fichier ; puis seul le fichier modifié passe en v2.
    MUTATION (lire la dernière version par `req_id` seul, l'ancien code) : chaque
    sync voit le contenu de l'AUTRE fichier -> 3 faux SPEC_MUTATED."""
    a, b = _deux_specs(tmp_path)
    parser = SpecParser(tmp_db)
    verdicts = [parser.process_and_sync_spec(f)[0] for f in (a, b, a, b)]
    assert _nb_spec_mutated(tmp_db) == 0, "faux SPEC_MUTATED entre deux fichiers"
    assert [(c.version, m) for c, m in verdicts] == [(1, False)] * 4
    assert _chaines(tmp_db) == [(str(a), _REQ, 1), (str(b), _REQ, 1)]

    a.write_text(f"## Login [{_REQ}]\ncontenu de a, modifie\n", encoding="utf-8")
    (ca, ma), = parser.process_and_sync_spec(a)
    (cb, mb), = parser.process_and_sync_spec(b)
    assert (ca.version, ma, cb.version, mb) == (2, True, 1, False)
    assert _nb_spec_mutated(tmp_db) == 1


def test_une_base_a_l_ancienne_cle_migre_sans_perte(tmp_db, tmp_path, monkeypatch):
    """Un store à l'ANCIENNE clé (req_id, version), chaîne partagée a1, b2, a3,
    b4 : au premier sync il passe à la clé (file_path, req_id, version), ses 4
    lignes recopiées TELLES QUELLES (aucune renumérotation), aucun événement
    émis, a reste en v3 et b en v4 UP-TO-DATE, et la ligne de migration ne sort
    qu'UNE fois sur deux appels. Le second sync tourne sous le verrou d'un autre
    écrivain : clé déjà neuve, AUCUN verrou demandé. Enfin la course (clé neuve
    trouvée SOUS le verrou) : ROLLBACK, rien écrit, `isolation_level` restauré.
    MUTATIONS (rejouées, toutes rouges) : retirer l'appel à `_migrer_cle_spec`
    -> la clé reste (req_id, version) ; changer une valeur à la recopie
    (`version + 1`) -> lignes changées ; imprimer la ligne sans tester
    `recopiees` -> elle sort dans la course ; retirer l'inspection AVANT le
    verrou -> le second sync attend le verrou puis lève `database is locked`
    (retirer le seul retour anticipé : `RuntimeError`) ; retirer le
    `ROLLBACK`/retour sous le verrou -> `RuntimeError` ; retirer le `finally`
    -> `isolation_level` reste `None`."""
    from agentic_v3.db.schema import get_db_connection

    a, b = _deux_specs(tmp_path)
    parser = SpecParser(tmp_db)  # fait naître le store, puis on le vieillit
    contenu_a = a.read_text(encoding="utf-8").strip()
    contenu_b = b.read_text(encoding="utf-8").strip()
    conn = sqlite3.connect(tmp_db)
    try:
        conn.execute("DROP TABLE spec_requirements")
        conn.execute(_ANCIEN_DDL_SPEC)
        conn.executemany(
            "INSERT INTO spec_requirements (req_id, version, file_path, section_title, "
            "content_markdown, tags_json) VALUES (?, ?, ?, ?, ?, '[]')",
            [(_REQ, 1, str(a), f"Login [{_REQ}]", "a ancien"),
             (_REQ, 2, str(b), f"Login [{_REQ}]", "b ancien"),
             (_REQ, 3, str(a), f"Login [{_REQ}]", contenu_a),
             (_REQ, 4, str(b), f"Login [{_REQ}]", contenu_b)])
        conn.commit()
    finally:
        conn.close()
    toutes = "SELECT * FROM spec_requirements ORDER BY version"
    avant = _lire(tmp_db, toutes)
    assert _cle(tmp_db) == ("req_id", "version"), "banc non armé"

    err = io.StringIO()
    with redirect_stderr(err):
        (ca, ma), = parser.process_and_sync_spec(a)
    assert _cle(tmp_db) == ("file_path", "req_id", "version")
    assert _lire(tmp_db, toutes) == avant, "lignes perdues ou renumérotées"

    verrou = sqlite3.connect(tmp_db, isolation_level=None)
    try:
        verrou.execute("BEGIN IMMEDIATE")  # un autre écrivain tient le verrou
        with redirect_stderr(err):
            (cb, mb), = parser.process_and_sync_spec(b)
    finally:
        verrou.execute("ROLLBACK")
        verrou.close()
    assert _nb_spec_mutated(tmp_db) == 0
    assert (ca.version, ma, cb.version, mb) == (3, False, 4, False)
    assert err.getvalue().count("spec_requirements migree vers la cle") == 1, err.getvalue()

    # Le texte de `sqlite_master` est celui d'un store NEUF ; l'ancienne table est partie.
    neuf = tmp_path / "neuf.db"
    SpecParser(neuf)
    texte = "SELECT sql FROM sqlite_master WHERE name LIKE 'spec_requirements%'"
    assert _lire(tmp_db, texte) == _lire(neuf, texte)
    assert len(_lire(tmp_db, texte)) == 1

    # Course : ancienne clé lue AVANT le verrou, neuve SOUS le verrou (un concurrent
    # a migré pendant l'attente) -> ROLLBACK et retour, isolation d'origine rendue.
    formes = iter([("req_id", "version"), ("file_path", "req_id", "version")])
    monkeypatch.setattr(SpecParser, "_cle_spec", staticmethod(lambda _conn: next(formes)))
    conn = get_db_connection(tmp_db)
    niveau = conn.isolation_level
    course = io.StringIO()
    try:
        with redirect_stderr(course):
            parser._migrer_cle_spec(conn)
        assert (conn.isolation_level, conn.in_transaction) == (niveau, False)
    finally:
        conn.close()
    assert course.getvalue() == "" and _lire(tmp_db, toutes) == avant


def test_la_compensation_ignore_la_posterieure_d_un_autre_fichier(tmp_db, tmp_path, monkeypatch):
    """La version postérieure d'un AUTRE fichier ne bloque plus la compensation.
    Bras comportemental d'abord (forme de T47) : seule (a,X,1) existe ; a modifié,
    `append_event` pose (b,X,3) puis lève -> la v2 de a, sans événement, est
    EFFACÉE. MUTATION (`NOT EXISTS` par `req_id` seul, l'ancien code) : (a,X,2)
    reste, annoncée « version conservée sous une version postérieure ». Puis
    l'appel direct `_compenser_version(conn, a, X, 2, ulid)` efface (a,X,2)."""
    a, _b = _deux_specs(tmp_path)
    autre = str(tmp_path / "b.md")
    parser = SpecParser(tmp_db)
    parser.process_and_sync_spec(a)
    a.write_text(f"## Login [{_REQ}]\ncontenu de a, v2\n", encoding="utf-8")

    def posterieure_d_un_autre_fichier_puis_echec(*_args, **_kwargs):
        conn = sqlite3.connect(tmp_db)
        conn.execute(
            "INSERT INTO spec_requirements (req_id, version, file_path, section_title, "
            "content_markdown, tags_json) VALUES (?, 3, ?, 'Login', 'b v3', '[]')",
            (_REQ, autre))
        conn.commit()
        conn.close()
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(parser.event_store, "append_event",
                        posterieure_d_un_autre_fichier_puis_echec)
    err = io.StringIO()
    with redirect_stderr(err), pytest.raises(sqlite3.OperationalError):
        parser.process_and_sync_spec(a)
    assert _chaines(tmp_db) == [(str(a), _REQ, 1), (autre, _REQ, 3)], err.getvalue()
    assert "version conservée sous une version postérieure" not in err.getvalue()

    conn = sqlite3.connect(tmp_db)
    try:
        conn.execute(
            "INSERT INTO spec_requirements (req_id, version, file_path, section_title, "
            "content_markdown, tags_json) VALUES (?, 2, ?, 'Login', 'a v2', '[]')",
            (_REQ, str(a)))
        conn.commit()
        SpecParser._compenser_version(conn, str(a), _REQ, 2, "01ULIDABSENTDUREGISTRE0000")
    finally:
        conn.close()
    assert _chaines(tmp_db) == [(str(a), _REQ, 1), (autre, _REQ, 3)]


def test_la_migration_est_refusee_sur_une_instance_bloquee(tmp_db, tmp_path, monkeypatch):
    """La migration est une ÉCRITURE : sur une instance dont la reconstruction
    n'est pas commitée, elle est refusée AVANT tout verrou (code 3 par la CLI) et
    la table garde l'ancienne clé (exec-critic M2, S-00004518). Vert aussi sur
    l'ancien code, qui ne migre rien : ce témoin borne la garde, il ne motive pas
    la clé. MUTATION (retirer `exiger_ecriture_permise()` avant la migration) :
    la table est migrée, puis le refus tombe au premier INSERT -> clé neuve."""
    from agentic_v3.db.event_store import ReconstructionAvorteeError

    a, _b = _deux_specs(tmp_path)
    parser = SpecParser(tmp_db)
    conn = sqlite3.connect(tmp_db)
    try:
        conn.execute("DROP TABLE spec_requirements")
        conn.execute(_ANCIEN_DDL_SPEC)
        conn.commit()
    finally:
        conn.close()

    def bloquee():
        raise ReconstructionAvorteeError("instance bloquee (banc)")

    monkeypatch.setattr(parser.event_store, "exiger_ecriture_permise", bloquee)
    with pytest.raises(ReconstructionAvorteeError):
        parser.process_and_sync_spec(a)
    assert _cle(tmp_db) == ("req_id", "version"), "migration écrite sur instance BLOQUÉE"


# Passe de correction de T-00001223 (S-00004519, S-00004527 F3) : chaque erreur
# qui vaut pour tout le store est NOMMÉE, sur UNE ligne, et ne modifie rien.
def _executer(db, *sqls):
    conn = sqlite3.connect(str(db))
    try:
        for sql in sqls:
            if isinstance(sql, tuple):
                conn.execute(*sql)
            else:
                conn.execute(sql)
        conn.commit()
    finally:
        conn.close()


def test_un_reste_de_migration_est_refuse_par_son_nom(tmp_db, tmp_path):
    """Store à l'ANCIENNE clé ET objet `spec_requirements__cle_req_id` déjà là :
    `RuntimeError` qui le nomme, ROLLBACK — clé, lignes et reste inchangés.
    MUTATION (retirer le `SELECT … sqlite_master` avant le RENAME, la base
    9ffa41a3) : le RENAME lève `sqlite3.OperationalError` brute -> rouge."""
    a, _b = _deux_specs(tmp_path)
    parser = SpecParser(tmp_db)
    _executer(
        tmp_db, "DROP TABLE spec_requirements", _ANCIEN_DDL_SPEC,
        ("INSERT INTO spec_requirements (req_id, version, file_path, section_title, "
         "content_markdown, tags_json) VALUES (?, 1, ?, 'Login', 'a ancien', '[]')",
         (_REQ, str(a))),
        "CREATE TABLE spec_requirements__cle_req_id (reste TEXT)",
        "INSERT INTO spec_requirements__cle_req_id VALUES ('ne pas toucher')")
    etat = ("SELECT * FROM spec_requirements", "SELECT * FROM spec_requirements__cle_req_id")
    avant = [_lire(tmp_db, sql) for sql in etat]
    with pytest.raises(RuntimeError, match="spec_requirements__cle_req_id existe deja"):
        parser.process_and_sync_spec(a)
    assert _cle(tmp_db) == ("req_id", "version")
    assert [_lire(tmp_db, sql) for sql in etat] == avant


class _ConnEnPanne:
    def execute(self, *_args):
        raise sqlite3.OperationalError("verrou\ntenu")

    def rollback(self):
        pass


def test_les_lignes_de_compensation_tiennent_sur_une_ligne(tmp_db):
    """Un `req_id` ou un message d'exception porteur d'un saut de ligne ne
    donne qu'UNE ligne stderr, dans les deux messages de `_compenser_version`.
    MUTATIONS (rendre `{req_id}` à l'une OU l'autre ligne, ou `{exc}`, la base
    9ffa41a3) : deux lignes -> rouge."""
    SpecParser(tmp_db)
    conn = sqlite3.connect(tmp_db)
    try:
        for cnx, mot in ((conn, "version conservée"), (_ConnEnPanne(), "verrou tenu")):
            err = io.StringIO()
            with redirect_stderr(err):
                SpecParser._compenser_version(cnx, "a.md", "REQ\nX", 2, "01ULIDABSENT")
            assert err.getvalue().count("\n") == 1, err.getvalue()
            assert "REQ X" in err.getvalue() and mot in err.getvalue(), err.getvalue()
    finally:
        conn.close()


def test_une_table_absente_ou_sans_cle_primaire_est_nommee(tmp_db, tmp_path):
    """Table sans clé primaire, puis table absente : le message le DIT (plus
    « inconnue () ») et garde le jeton `cle primaire inconnue` sur lequel
    specs-sync s'arrête ; rien n'est créé ni modifié. MUTATION (la base
    9ffa41a3, message `{cle!r}` seul) : « absente ou sans cle primaire » absent."""
    a, _b = _deux_specs(tmp_path)
    parser = SpecParser(tmp_db)
    _executer(tmp_db, "DROP TABLE spec_requirements",
              "CREATE TABLE spec_requirements (req_id TEXT, version INTEGER, file_path "
              "TEXT, section_title TEXT, content_markdown TEXT, tags_json TEXT)")
    texte = "SELECT sql FROM sqlite_master WHERE name LIKE 'spec_req%'"
    sans_cle = _lire(tmp_db, texte)
    assert len(sans_cle) == 1 and _cle(tmp_db) == (), "banc non armé"
    for attendu in (sans_cle, []):  # sans clé primaire, puis absente
        with pytest.raises(RuntimeError, match="absente ou sans cle primaire") as exc:
            parser.process_and_sync_spec(a)
        assert "cle primaire inconnue" in str(exc.value)
        assert _lire(tmp_db, texte) == attendu
        _executer(tmp_db, "DROP TABLE IF EXISTS spec_requirements")


def test_le_fsm_retire_ne_revient_pas_par_un_import_oublie():
    """CONTROLE NEGATIF DU RETRAIT. Un paquet supprime dont un `__init__.py`
    re-exporte encore le nom reviendrait par la bande, et les deux bancs
    ci-dessus passeraient sans rien dire.

    LA PROPRIETE MESUREE EST « AUCUN CODE SOURCE SOUS CE NOM », PAS « NOM
    INTROUVABLE », et la nuance n'est pas une commodite. Depuis Python 3.3 un
    REPERTOIRE VIDE s'importe comme paquet-espace de noms : apres un `git rm`,
    un `__pycache__/` residuel non suivi laisse `import agentic_v3.agents`
    REUSSIR sur un arbre de travail, alors qu'il echoue sur tout clone frais.
    Mesure du 2026-09-12 : c'est exactement ce qui s'est produit ici. Exiger
    `ModuleNotFoundError` rendait donc ce banc rouge chez le mainteneur et vert
    en CI — le pire des deux, un filet qu'on finit par desarmer.

    Un espace de noms vide n'a pas de `__file__`. Une VRAIE reintroduction en a
    un, et c'est elle que ce test doit attraper.
    """
    import importlib

    for mort in (
        "agentic_v3.agents",
        "agentic_v3.mcp",
        "agentic_v3.orchestrator",
        "agentic_v3.reconciliation.visual_diff",
    ):
        try:
            module = importlib.import_module(mort)
        except ModuleNotFoundError:
            continue  # le cas propre : rien sur disque
        assert getattr(module, "__file__", None) is None, (
            f"{mort} porte a nouveau du code source ({module.__file__}) — il a ete "
            "RETIRE le 2026-09-12 par T-012 ; sa reintroduction est une decision "
            "a tracer, pas un import a rajouter."
        )

    # NON-VACUITE : le module vivant, lui, doit s'importer ET porter un fichier —
    # sinon la boucle ci-dessus passerait sur un arbre entierement casse.
    vivant = importlib.import_module("agentic_v3.reconciliation.board_bridge")
    assert getattr(vivant, "__file__", None) is not None
