"""
SpecParser: Markdown specification AST parser with versioning and Hot Spec Mutation diff detection.
Scans .md files, calculates hashes, emits SPEC_MUTATED events on modifications.
"""

import contextlib
import difflib
import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
from agentic_v3.db import run_export
from agentic_v3.db.event_store import EventStore
from agentic_v3.db.refus_store import aplatir_message, refus_nomme
from agentic_v3.db.schema import get_db_connection, DEFAULT_DB_PATH, SPEC_REQUIREMENTS_DDL
from agentic_v3.models.slices import SpecChunkSlice
from agentic_v3.models.events import EventType

#: T-00001223 (S-00004503) — les deux formes CONNUES de la clé primaire de
#: `spec_requirements`, colonnes dans leur rang de clé (`PRAGMA table_info`).
_CLE_PAR_FICHIER = ("file_path", "req_id", "version")
_CLE_REQ_ID_SEUL = ("req_id", "version")


class SpecParser:
    """Parses markdown specifications into versioned SpecChunkSlices."""

    def __init__(self, db_path: Union[str, Path, None] = None):
        # T-00001005 : résolution ET ouverture sous le refus nommé — un store
        # refusé lève `StoreV3Refuse`, toute autre levée remonte telle quelle.
        # `EventStore(self.db_path)` résout aussi la racine, même `db_path` donné.
        with refus_nomme(db_path):
            # T-00000650 (patron c) : `None` résout vers `DEFAULT_DB_PATH()`.
            self.db_path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH()
            self.event_store = EventStore(self.db_path)

    def _compute_hash(self, content: str) -> str:
        return hashlib.sha256(content.strip().encode("utf-8")).hexdigest()

    def parse_markdown_file(self, file_path: Union[str, Path]) -> List[SpecChunkSlice]:
        """Parses a markdown specification file into section headers and content."""
        path_obj = Path(file_path)
        if not path_obj.exists():
            raise FileNotFoundError(f"Specification file not found: {file_path}")

        raw_text = path_obj.read_text(encoding="utf-8")
        sections = re.split(r'\n(?=#{1,3}\s+)', raw_text)

        chunks: List[SpecChunkSlice] = []
        for idx, section in enumerate(sections):
            section = section.strip()
            if not section:
                continue

            lines = section.split("\n")
            header_match = re.match(r'^(#{1,3})\s+(.*)$', lines[0])
            if header_match:
                section_title = header_match.group(2).strip()
            else:
                section_title = f"Section-{idx+1}"

            # Extract req_id tag if present e.g. [REQ-AUTH-001], or generate slug
            req_match = re.search(r'\[(REQ-[A-Z0-9_-]+)\]', section_title)
            if req_match:
                req_id = req_match.group(1)
            else:
                slug = re.sub(r'[^A-Z0-9]+', '-', section_title.upper()).strip('-')
                req_id = f"REQ-{slug}" if slug else f"REQ-SEC-{idx+1}"

            chunk = SpecChunkSlice(
                req_id=req_id,
                version=1,
                file_path=str(path_obj),
                section_title=section_title,
                content_markdown=section
            )
            chunks.append(chunk)

        return chunks

    @staticmethod
    def _compenser_version(
        conn: sqlite3.Connection, file_path: str, req_id: str, version: int, ulid: str
    ) -> None:
        """Défait la version `version` de `req_id` dans `file_path`, tout juste
        commitée, quand
        l'événement `SPEC_MUTATED` d'ULID `ulid` n'est PAS en base — l'appel
        `append_event` a levé AVANT son commit. Si l'événement EST en base (l'export
        a échoué APRÈS le commit : `PanneInfrastructure` remonte de `_flush_export`),
        la version RESTE : l'effacer laisserait un événement sans version, puis un
        second SPEC_MUTATED de la même version au sync suivant.

        T-00000691 (S-00002557) : la version RESTE AUSSI quand une version
        POSTÉRIEURE existe déjà — un sync-spec CONCURRENT l'a posée, et son diff part
        de CELLE-CI : l'effacer trouerait l'historique sous elle. Le `DELETE` porte
        donc `AND NOT EXISTS (… version > ?)`, et ce cas est ANNONCÉ (« version
        conservée sous une version postérieure »), la version restant sans son
        SPEC_MUTATED. Ne lève jamais : un échec de la compensation elle-même est
        ANNONCÉ, la version restant alors sans événement (le résidu nommé dans
        `process_and_sync_spec`).

        T-00001223 (S-00004503) : le `DELETE` et le `NOT EXISTS` portent la clé
        (file_path, req_id) — une version postérieure du même id dans un AUTRE
        fichier est une autre chaîne et ne bloque plus la compensation. Les deux
        lignes nomment le fichier sur UNE ligne (`aplatir_message`, S-00003354) ;
        le `req_id` et le message de l'exception aussi (S-00004519)."""
        fichier = aplatir_message(file_path)
        ident = aplatir_message(req_id)
        try:
            present = conn.execute(
                "SELECT 1 FROM events_ledger WHERE ulid=?", (ulid,)
            ).fetchone() is not None
            if present:
                return
            efface = conn.execute(
                "DELETE FROM spec_requirements WHERE file_path=? AND req_id=? "
                "AND version=? AND NOT EXISTS (SELECT 1 FROM spec_requirements "
                "WHERE file_path=? AND req_id=? AND version > ?)",
                (file_path, req_id, version, file_path, req_id, version),
            ).rowcount
            conn.commit()
            if not efface:
                print(
                    f"agentic_v3 sync-spec: version conservée sous une version "
                    f"postérieure — version {version} de {ident} dans {fichier} "
                    "laissee SANS evenement SPEC_MUTATED (un sync-spec concurrent a "
                    "pose une version plus recente de ce req_id dans ce fichier, dont "
                    "le diff part d'elle) ; remede : relancer sync-spec apres la fin "
                    "du sync concurrent",
                    file=sys.stderr,
                )
        except Exception as exc:
            with contextlib.suppress(Exception):
                conn.rollback()
            print(
                f"agentic_v3 sync-spec: compensation IMPOSSIBLE, version {version} de "
                f"{ident} dans {fichier} laissee SANS evenement SPEC_MUTATED "
                f"({type(exc).__name__}: {aplatir_message(str(exc))}) ; remede : "
                "supprimer cette version de "
                "spec_requirements puis relancer sync-spec (seulement si c'est la "
                "version la plus recente de ce req_id dans ce fichier)",
                file=sys.stderr,
            )

    @staticmethod
    def _cle_spec(conn: sqlite3.Connection) -> Tuple[str, ...]:
        """La clé primaire de `spec_requirements`, colonnes dans leur rang de clé,
        lue par INSPECTION (`PRAGMA table_info`) ; `()` si la table est absente."""
        rangs = sorted(
            (ligne[5], ligne[1])
            for ligne in conn.execute("PRAGMA table_info(spec_requirements)")
            if ligne[5]
        )
        return tuple(nom for _rang, nom in rangs)

    @staticmethod
    def _cle_inconnue(cle: Tuple[str, ...]) -> RuntimeError:
        """L'erreur qui NOMME une forme de clé inconnue : on échoue fermé. Une clé
        VIDE (table absente ou sans clé primaire) est dite telle quelle plutôt
        qu'affichée `()` ; les deux formes gardent le jeton `cle primaire
        inconnue`, sur lequel specs-sync s'arrête (S-00004527 F3)."""
        forme = repr(cle) if cle else "(table absente ou sans cle primaire)"
        return RuntimeError(
            f"spec_requirements porte une cle primaire inconnue {forme} : ni "
            f"{_CLE_REQ_ID_SEUL!r} (a migrer) ni {_CLE_PAR_FICHIER!r} ; rien n'est "
            "modifie, la table est laissee telle quelle"
        )

    def _migrer_cle_spec(self, conn: sqlite3.Connection) -> None:
        """T-00001223 (décision pilote S-00004503) — porte un store à l'ANCIENNE
        clé (req_id, version) à la clé (file_path, req_id, version), au premier
        sync-spec. Pilotée par INSPECTION de la clé, jamais par `user_version`.

          * Clé déjà neuve : RIEN n'est écrit et AUCUN verrou n'est pris.
          * Forme inconnue : `RuntimeError` qui la nomme, rien n'est modifié.
          * Ancienne clé : `exiger_ecriture_permise()` (instance bloquée -> code 3,
            rien écrit), puis, en autocommit (`isolation_level` d'origine RESTAURÉ
            dans un `finally`), `BEGIN IMMEDIATE` et nouvelle inspection SOUS LE
            VERROU — un sync concurrent qui a migré entre-temps : `ROLLBACK`, retour.
            Un objet `spec_requirements__cle_req_id` déjà présent : `ROLLBACK` et
            `RuntimeError` qui le nomme, rien n'est modifié. Sinon `RENAME` vers `spec_requirements__cle_req_id`, `CREATE` sous
            `SPEC_REQUIREMENTS_DDL` (le texte de `sqlite_master` reste celui d'un
            store neuf), recopie des six colonnes TELLES QUELLES (aucune
            renumérotation : les versions restent alignées sur les payloads
            SPEC_MUTATED déjà écrits), comptes comparés — écart : `ROLLBACK` et
            levée —, `DROP` de l'ancienne table, `COMMIT`, et UNE ligne stderr
            informative. Un verrou tenu au-delà de l'attente lève l'erreur SQLite
            brute, que la CLI rend en code 4 (`refus_nomme`)."""
        cle = self._cle_spec(conn)
        if cle == _CLE_PAR_FICHIER:
            return
        if cle != _CLE_REQ_ID_SEUL:
            raise self._cle_inconnue(cle)
        self.event_store.exiger_ecriture_permise()
        niveau = conn.isolation_level
        conn.isolation_level = None
        try:
            recopiees = self._recopier_sous_la_cle_par_fichier(conn)
        finally:
            conn.isolation_level = niveau
        if recopiees is not None:
            print(
                "agentic_v3 sync-spec: spec_requirements migree vers la cle "
                f"(file_path, req_id, version), {recopiees} lignes recopiees telles "
                "quelles",
                file=sys.stderr,
            )

    @classmethod
    def _recopier_sous_la_cle_par_fichier(cls, conn: sqlite3.Connection) -> Optional[int]:
        """Le corps transactionnel de `_migrer_cle_spec` (voir sa docstring), sur
        une connexion en autocommit. Rend le nombre de lignes recopiées, ou `None`
        si la clé était déjà neuve sous le verrou (rien écrit)."""
        conn.execute("BEGIN IMMEDIATE")
        try:
            cle = cls._cle_spec(conn)
            if cle == _CLE_PAR_FICHIER:
                conn.execute("ROLLBACK")
                return None
            if cle != _CLE_REQ_ID_SEUL:
                raise cls._cle_inconnue(cle)
            # S-00004519 : un objet de ce nom (reste d'une migration, ou posé à la
            # main) ferait échouer le RENAME en erreur SQLite brute ; on le NOMME.
            if conn.execute(
                "SELECT 1 FROM sqlite_master WHERE name='spec_requirements__cle_req_id'"
            ).fetchone() is not None:
                raise RuntimeError(
                    "migration de spec_requirements impossible : la table "
                    "spec_requirements__cle_req_id existe deja ; rien n'est modifie"
                )
            conn.execute(
                "ALTER TABLE spec_requirements RENAME TO spec_requirements__cle_req_id"
            )
            conn.execute(SPEC_REQUIREMENTS_DDL)
            conn.execute(
                "INSERT INTO spec_requirements (req_id, version, file_path, "
                "section_title, content_markdown, tags_json) "
                "SELECT req_id, version, file_path, section_title, content_markdown, "
                "tags_json FROM spec_requirements__cle_req_id"
            )
            lues = conn.execute(
                "SELECT COUNT(*) FROM spec_requirements__cle_req_id"
            ).fetchone()[0]
            recopiees = conn.execute(
                "SELECT COUNT(*) FROM spec_requirements"
            ).fetchone()[0]
            if lues != recopiees:
                raise RuntimeError(
                    f"migration de spec_requirements annulee : {lues} lignes lues, "
                    f"{recopiees} recopiees ; ROLLBACK, store inchange"
                )
            conn.execute("DROP TABLE spec_requirements__cle_req_id")
            conn.execute("COMMIT")
            return recopiees
        except BaseException:
            with contextlib.suppress(sqlite3.Error):
                conn.execute("ROLLBACK")
            raise

    def process_and_sync_spec(self, file_path: Union[str, Path]) -> List[Tuple[SpecChunkSlice, bool]]:
        """
        Syncs spec file with SQLite database.
        Returns list of (SpecChunkSlice, is_mutated) tuples.
        Emits SPEC_MUTATED event if a specification has evolved.

        T-00000691 (S-00002518 F2, S-00002519) — AUCUNE VERSION SANS SON ÉVÉNEMENT.
        La version est commitée par CETTE connexion, l'événement par celle
        d'`append_event` : deux transactions. Avant ce correctif, un événement
        refusé (instance dont la reconstruction due n'est pas commitée) ou en échec
        laissait la version SANS `SPEC_MUTATED`, et le sync suivant la voyait
        « UP-TO-DATE » — l'événement était perdu DÉFINITIVEMENT.
          * `event_store.exiger_ecriture_permise()` AVANT CHAQUE écriture de
            `spec_requirements` (donc avant la première) : sur une instance
            bloquée, rien n'est écrit (`ReconstructionAvorteeError`, que `cli`
            rend en une ligne et le code 3) ; un sync sans changement n'écrit rien
            et n'est pas refusé — SAUF le premier sync sur un store à l'ANCIENNE
            clé (req_id, version) : la migration `_migrer_cle_spec` (T-00001223)
            y ÉCRIT, sous la même garde (code 3) puis sous `BEGIN IMMEDIATE`, donc
            refusable en code 4 par la CLI quand un autre écrivain tient le verrou.
          * T-00001223 (S-00004503) : la chaîne de versions est propre à CHAQUE
            fichier — lecture, écriture et compensation portent la clé
            (file_path, req_id), le chemin tel que passé (après `Path`).
          * l'ULID de l'événement est tiré AVANT toute écriture (S-00002557) :
            un tirage qui lève ne laisse aucune version derrière lui.
          * COMPENSATION : si `append_event` lève, la version est défaite SI SON
            ÉVÉNEMENT (ULID tiré ici, puis relu) n'est pas en base ET qu'aucune
            version postérieure n'existe — le sync suivant la redétecte et émet
            SPEC_MUTATED. Sinon elle reste (annoncé quand c'est une postérieure).
        RÉSIDU NOMMÉ, NON FERMÉ ICI (S-00002519 : une API transactionnelle commune
        version + événement est une décision d'architecture, hors tâche) : un
        ARRÊT du processus (SIGKILL, coupure) ENTRE le commit de la version et
        celui de l'événement laisse une version sans SPEC_MUTATED, que le sync
        suivant voit « UP-TO-DATE ». Une compensation qui échoue elle-même laisse
        le même état, annoncé.
        """
        chunks = self.parse_markdown_file(file_path)
        results: List[Tuple[SpecChunkSlice, bool]] = []
        conn = get_db_connection(self.db_path)
        try:
            self._migrer_cle_spec(conn)
            self._synchroniser(conn, chunks, results)
        finally:
            conn.close()
        return results

    def _synchroniser(
        self,
        conn: sqlite3.Connection,
        chunks: List[SpecChunkSlice],
        results: List[Tuple[SpecChunkSlice, bool]],
    ) -> None:
        """Le corps de `process_and_sync_spec` (garde et compensation : voir sa
        docstring) ; la connexion est fermée par l'appelant, même sur levée."""
        cursor = conn.cursor()

        for chunk in chunks:
            cursor.execute(
                """
                SELECT version, content_markdown FROM spec_requirements
                WHERE file_path=? AND req_id=? ORDER BY version DESC LIMIT 1;
                """,
                (chunk.file_path, chunk.req_id)
            )
            row = cursor.fetchone()

            if row is None:
                # Initial insert (Version 1) — T-00000691 : garde AVANT l'écriture.
                self.event_store.exiger_ecriture_permise()
                cursor.execute(
                    """
                    INSERT INTO spec_requirements (req_id, version, file_path, section_title, content_markdown, tags_json)
                    VALUES (?, 1, ?, ?, ?, ?);
                    """,
                    (chunk.req_id, chunk.file_path, chunk.section_title, chunk.content_markdown, json.dumps([]))
                )
                conn.commit()
                results.append((chunk, False))
            else:
                old_version = row["version"]
                old_content = row["content_markdown"]

                if self._compute_hash(old_content) != self._compute_hash(chunk.content_markdown):
                    # Hot Spec Mutation detected!
                    new_version = old_version + 1
                    diff_lines = list(difflib.unified_diff(
                        old_content.splitlines(),
                        chunk.content_markdown.splitlines(),
                        fromfile=f"v{old_version}",
                        tofile=f"v{new_version}",
                        lineterm=""
                    ))
                    diff_text = "\n".join(diff_lines)

                    chunk.version = new_version
                    chunk.spec_diff_from_previous = diff_text

                    # T-00000691 (S-00002557, MAJEURE) : l'ULID de l'événement est tiré
                    # AVANT TOUTE écriture (même générateur monotone que l'écrivain).
                    # Tiré APRÈS le commit de la version et hors du `try` compensé, un
                    # tirage qui lève (couture `cadre.ledger.ids` absente) laissait la
                    # version SANS SPEC_MUTATED — la perte que ce correctif ferme.
                    ulid_evenement = run_export.nouvel_ulid()
                    # Insert new version into spec_requirements — T-00000691 : garde
                    # AVANT l'écriture (instance bloquée ⇒ rien écrit).
                    self.event_store.exiger_ecriture_permise()
                    cursor.execute(
                        """
                        INSERT INTO spec_requirements (req_id, version, file_path, section_title, content_markdown, tags_json)
                        VALUES (?, ?, ?, ?, ?, ?);
                        """,
                        (chunk.req_id, new_version, chunk.file_path, chunk.section_title, chunk.content_markdown, json.dumps([]))
                    )
                    conn.commit()

                    # Emit immutable SPEC_MUTATED event to ledger, sous l'ULID tiré
                    # plus haut : la compensation relit si l'événement est en base.
                    try:
                        self.event_store.append_event(
                            task_id=f"SYSTEM-MUTATION-{chunk.req_id}",
                            agent_role="SpecParser",
                            event_type=EventType.SPEC_MUTATED,
                            payload={
                                "req_id": chunk.req_id,
                                "version": new_version,
                                "diff": diff_text,
                                "file_path": chunk.file_path,
                                "hash_checksum": self._compute_hash(chunk.content_markdown)
                            },
                            ulid=ulid_evenement,
                        )
                    except BaseException:
                        self._compenser_version(
                            conn, chunk.file_path, chunk.req_id, new_version,
                            ulid_evenement,
                        )
                        raise
                    results.append((chunk, True))
                else:
                    chunk.version = old_version
                    results.append((chunk, False))
