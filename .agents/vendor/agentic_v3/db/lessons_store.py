"""
LessonsStore: Tagged repository of lessons learned for prompt injection.
Strictly caps injected lessons to 3 per context slice (Scope-Slicing rule).
"""

from pathlib import Path
from typing import List, Union
from agentic_v3.db.schema import get_db_connection, create_tables, DEFAULT_DB_PATH
from agentic_v3.db.refus_store import refus_nomme


class LessonsStore:
    """Manages recording and querying tagged lessons with a max 3 limit."""

    def __init__(self, db_path: Union[str, Path, None] = None):
        # T-00001005 : résolution ET ouverture sous le refus nommé — un store
        # refusé lève `StoreV3Refuse`, toute autre levée remonte telle quelle.
        with refus_nomme(db_path):
            # T-00000650 (patron c) : `None` résout PARESSEUSEMENT vers
            # `DEFAULT_DB_PATH()` (partition MACHINE), jamais `= DEFAULT_DB_PATH` nu
            # en défaut, qui lierait l'objet fonction. `lessons_store` partage ce
            # fichier avec le store d'événements.
            self.db_path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH()
            create_tables(self.db_path)

    def add_lesson(self, language: str, domain_tag: str, error_pattern: str, lesson_text: str) -> int:
        """Stores a new lesson tagged by language, domain_tag, and error_pattern."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO lessons_learned (language, domain_tag, error_pattern, lesson_text)
            VALUES (?, ?, ?, ?);
            """,
            (language.lower(), domain_tag.lower(), error_pattern.lower(), lesson_text)
        )
        lesson_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return lesson_id

    def query_lessons(self, language: str, domain_tag: str, error_pattern: str, limit: int = 3) -> List[str]:
        """Queries matching lessons by triple tag (language, domain_tag, error_pattern) strictly capped at 3."""
        limit_cap = min(limit, 3)
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            """
            SELECT lesson_text FROM lessons_learned
            WHERE language=? AND domain_tag=? AND error_pattern=?
            ORDER BY lesson_id DESC
            LIMIT ?;
            """,
            (language.lower(), domain_tag.lower(), error_pattern.lower(), limit_cap)
        )
        rows = cursor.fetchall()
        
        if not rows:
            # Fallback to broader match on language and domain_tag
            cursor.execute(
                """
                SELECT lesson_text FROM lessons_learned
                WHERE language=? AND domain_tag=?
                ORDER BY lesson_id DESC
                LIMIT ?;
                """,
                (language.lower(), domain_tag.lower(), limit_cap)
            )
            rows = cursor.fetchall()
            
        conn.close()
        return [row["lesson_text"] for row in rows[:limit_cap]]
