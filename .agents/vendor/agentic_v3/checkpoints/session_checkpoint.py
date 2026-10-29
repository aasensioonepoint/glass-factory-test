"""
SessionCheckpointManager: Persists phase completion and state snapshots to SQLite.
Allows any agent or future session to resume seamlessly when token budgets are reached.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional, Union
from agentic_v3.db.schema import get_db_connection, create_tables, DEFAULT_DB_PATH
from agentic_v3.db.refus_store import refus_nomme


class SessionCheckpointManager:
    """Manages session checkpoints for multi-session resilience."""

    def __init__(self, session_id: str = "v3_default_session", db_path: Union[str, Path, None] = None):
        self.session_id = session_id
        # T-00001005 : résolution ET ouverture sous le refus nommé — un store
        # refusé lève `StoreV3Refuse`, toute autre levée remonte telle quelle.
        with refus_nomme(db_path):
            # T-00000650 (patron c) : `None` résout vers `DEFAULT_DB_PATH()`.
            self.db_path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH()
            create_tables(self.db_path)

    def save_checkpoint(self, phase_number: int, phase_name: str, checkpoint_data: Dict[str, Any]) -> None:
        """Saves a checkpoint snapshot for the current session."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO session_checkpoints (session_id, current_phase, phase_name, checkpoint_data_json, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(session_id) DO UPDATE SET
                current_phase=excluded.current_phase,
                phase_name=excluded.phase_name,
                checkpoint_data_json=excluded.checkpoint_data_json,
                updated_at=CURRENT_TIMESTAMP;
            """,
            (self.session_id, phase_number, phase_name, json.dumps(checkpoint_data, ensure_ascii=False))
        )
        conn.commit()
        conn.close()

    def get_latest_checkpoint(self) -> Optional[Dict[str, Any]]:
        """Retrieves the latest checkpoint snapshot to resume execution."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM session_checkpoints WHERE session_id=?", (self.session_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            data = dict(row)
            data["checkpoint_data"] = json.loads(data["checkpoint_data_json"])
            return data
        return None
