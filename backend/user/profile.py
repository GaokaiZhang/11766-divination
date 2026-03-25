import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "users.db"


@dataclass
class UserProfile:
    user_id: str
    name: str
    birth_date: str | None = None
    birth_time: str | None = None
    birth_location: str | None = None
    themes: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


class ProfileStore:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id       TEXT PRIMARY KEY,
                    name          TEXT NOT NULL,
                    birth_date    TEXT,
                    birth_time    TEXT,
                    birth_location TEXT,
                    themes        TEXT DEFAULT '[]',
                    created_at    TEXT
                );
                CREATE TABLE IF NOT EXISTS readings (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id          TEXT NOT NULL,
                    system           TEXT NOT NULL,
                    result_json      TEXT,
                    conversation_json TEXT,
                    created_at       TEXT
                );
            """)

    # ------------------------------------------------------------------
    # Profile CRUD
    # ------------------------------------------------------------------

    def get_or_create(self, user_id: str, name: str) -> UserProfile:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
            if row:
                return UserProfile(
                    user_id=row[0], name=row[1],
                    birth_date=row[2], birth_time=row[3], birth_location=row[4],
                    themes=json.loads(row[5] or "[]"), created_at=row[6],
                )
            profile = UserProfile(user_id=user_id, name=name)
            self._upsert(conn, profile)
            return profile

    def update(self, profile: UserProfile) -> None:
        with sqlite3.connect(self.db_path) as conn:
            self._upsert(conn, profile)

    def _upsert(self, conn: sqlite3.Connection, p: UserProfile) -> None:
        conn.execute(
            "INSERT OR REPLACE INTO users VALUES (?,?,?,?,?,?,?)",
            (p.user_id, p.name, p.birth_date, p.birth_time,
             p.birth_location, json.dumps(p.themes), p.created_at),
        )

    def add_theme(self, user_id: str, theme: str) -> None:
        """Append a newly extracted theme to the user's profile (no duplicates)."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT themes FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
            if not row:
                return
            themes: list[str] = json.loads(row[0] or "[]")
            if theme not in themes:
                themes.append(theme)
                conn.execute(
                    "UPDATE users SET themes = ? WHERE user_id = ?",
                    (json.dumps(themes), user_id),
                )

    # ------------------------------------------------------------------
    # Reading history
    # ------------------------------------------------------------------

    def save_reading(
        self,
        user_id: str,
        system: str,
        result: dict,
        conversation: list[dict],
    ) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO readings (user_id,system,result_json,conversation_json,created_at)"
                " VALUES (?,?,?,?,?)",
                (user_id, system, json.dumps(result),
                 json.dumps(conversation), datetime.now().isoformat()),
            )

    def get_readings(self, user_id: str, limit: int = 5) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT system,result_json,conversation_json,created_at"
                " FROM readings WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [
            {"system": r[0], "result": json.loads(r[1]),
             "conversation": json.loads(r[2]), "created_at": r[3]}
            for r in rows
        ]
