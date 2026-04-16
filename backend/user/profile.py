import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "users.db"

# Cap on how many themes we keep per user. Older entries are dropped so the
# system prompt does not get flooded as sessions accumulate.
MAX_THEMES = 8


def _themes_blob_to_texts(raw: str) -> list[str]:
    """Load the themes JSON blob and return plain theme texts, newest first.

    Handles two on-disk formats:
      - legacy: list[str]
      - current: list[{text, ts, count}]
    """
    parsed = json.loads(raw or "[]")
    if not parsed:
        return []
    if isinstance(parsed[0], str):
        return list(parsed)
    normalized = [
        p for p in parsed if isinstance(p, dict) and p.get("text")
    ]
    normalized.sort(key=lambda p: p.get("ts", ""), reverse=True)
    return [p["text"] for p in normalized]


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
                    themes=_themes_blob_to_texts(row[5])[:MAX_THEMES],
                    created_at=row[6],
                )
            profile = UserProfile(user_id=user_id, name=name)
            self._upsert(conn, profile, initial=True)
            return profile

    def update(self, profile: UserProfile) -> None:
        """Update non-theme profile fields. Themes are managed via add_theme."""
        with sqlite3.connect(self.db_path) as conn:
            self._upsert(conn, profile, initial=False)

    def _upsert(
        self, conn: sqlite3.Connection, p: UserProfile, *, initial: bool
    ) -> None:
        # Never clobber the themes column from this path — add_theme owns it.
        # On initial insert the column starts as an empty JSON list.
        if initial:
            themes_blob = "[]"
        else:
            row = conn.execute(
                "SELECT themes FROM users WHERE user_id = ?", (p.user_id,)
            ).fetchone()
            themes_blob = row[0] if row else "[]"
        conn.execute(
            "INSERT OR REPLACE INTO users VALUES (?,?,?,?,?,?,?)",
            (p.user_id, p.name, p.birth_date, p.birth_time,
             p.birth_location, themes_blob, p.created_at),
        )

    def add_theme(self, user_id: str, theme: str) -> None:
        """Record a theme with a timestamp, refresh recency on duplicates,
        and keep only the most recent MAX_THEMES entries.

        Storage format: list of {text, ts, count} dicts, sorted newest first.
        """
        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT themes FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
            if not row:
                return

            raw = json.loads(row[0] or "[]")
            # Migrate legacy list[str] entries in-place.
            entries: list[dict] = [
                {"text": t, "ts": now, "count": 1} if isinstance(t, str) else t
                for t in raw
                if isinstance(t, (str, dict))
            ]

            existing = next(
                (e for e in entries if e.get("text") == theme), None
            )
            if existing:
                existing["ts"] = now
                existing["count"] = int(existing.get("count", 1)) + 1
            else:
                entries.append({"text": theme, "ts": now, "count": 1})

            entries.sort(key=lambda e: e.get("ts", ""), reverse=True)
            entries = entries[:MAX_THEMES]

            conn.execute(
                "UPDATE users SET themes = ? WHERE user_id = ?",
                (json.dumps(entries), user_id),
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
