import datetime
import re
import secrets
from dataclasses import dataclass
from sqlite3 import Connection
from typing import Any

import bcrypt
import loguru

from simple_kv.lib.db_wrapper import DbWrapper
from simple_kv.lib.paths import DATA_DIR, LOG_DIR

loguru.logger.add(
    LOG_DIR / "kv_db.log",
    filter=lambda record: record["extra"].get("name") == "kv_db",
    rotation="10 MB",
    retention=2,
)
_LOG = loguru.logger.bind(name="kv_db")


@dataclass
class ValTableName:
    name: str


class KvDb(DbWrapper):
    GUEST_USER_ID = 1
    GUEST_USER = "anon"

    ADMIN_PERM = "admin"

    SESSION_DURATION_SECONDS = 86400

    user: "_UserHelper"
    kv: "_KvHelper"

    def __init__(self, **kwargs):
        super().__init__(
            DATA_DIR / "kv.sqlite",
            **kwargs,
        )

        self.user = _UserHelper(self)

    def init_schema(self, conn: Connection) -> None:
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS users (
                id      INTEGER     PRIMARY KEY,
                user    TEXT        NOT NULL,
                pass    BLOB        NOT NULL,

                UNIQUE (user)
            ) STRICT
            """
        )
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS users_permissions (
                uid     INTEGER     NOT NULL,
                perm    TEXT        NOT NULL,

                UNIQUE (uid, perm),
                FOREIGN KEY (uid) REFERENCES users (id) ON DELETE CASCADE
            ) STRICT
            """
        )
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS users_sessions (
                uid         INTEGER     NOT NULL,
                sid         TEXT        NOT NULL,
                expires     TEXT        NOT NULL,

                UNIQUE (uid, sid),
                FOREIGN KEY (uid) REFERENCES users (id) ON DELETE CASCADE
            ) STRICT
            """
        )

        # Create special guest user
        conn.execute(
            """
            INSERT OR IGNORE INTO users (
                id, user, pass
            ) VALUES (
                ?, ?, ?
            )
            """,
            [self.GUEST_USER_ID, self.GUEST_USER, b""],
        )


@dataclass
class _UserHelper:
    db: KvDb

    def register_user(self, conn: Connection, username: str, raw_password: str):
        password = bcrypt.hashpw(raw_password.encode(), bcrypt.gensalt())

        conn.execute(
            """
            INSERT INTO users (
                user, pass
            ) VALUES (
                ?, ?
            )
            """,
            [username, password],
        )

    def login(self, conn: Connection, username: str, raw_password: str) -> dict | None:
        r = conn.execute(
            """
                SELECT id, pass
                FROM users
                WHERE user = ?
                """,
            [username],
        ).fetchone()
        if not r:
            return None

        is_password_match = bcrypt.checkpw(raw_password.encode(), r["pass"])
        if not is_password_match:
            return None

        sid = secrets.token_hex()
        duration = datetime.timedelta(seconds=self.db.SESSION_DURATION_SECONDS)
        expires = duration + datetime.datetime.now(tz=datetime.timezone.utc)
        conn.execute(
            """
            INSERT INTO users_sessions (
                uid, sid, expires
            ) VALUES (
                ?, ?, ?
            )
            """,
            [r["id"], sid, expires.isoformat()],
        )

        self.vacuum_sessions(conn)

        return dict(
            sid=sid,
            uid=r["id"],
            duration=self.db.SESSION_DURATION_SECONDS,
        )

    def vacuum_sessions(self, conn: Connection):
        cursor = conn.cursor()
        cursor.execute(
            """
            DELETE FROM users_sessions
            WHERE expires < ?
            """,
            [datetime.datetime.now().isoformat()],
        )

        if cursor.rowcount > 0:
            _LOG.info(f"Vacuum'd {cursor.rowcount} sessions")

    def register_kv_table_user(
        self,
        conn: Connection,
        raw_table: str,
        uid: int,
        read=False,
        write=False,
    ):
        table = self.db.kv.prepare_kv_table_name(raw_table)

        all_vals = []
        if read:
            all_vals.append((uid, self.db.kv.read_perm(table)))
        if write:
            all_vals.append((uid, self.db.kv.write_perm(table)))

        for vals in all_vals:
            conn.execute(
                f"""
                INSERT INTO users_permissions (
                    uid, perm
                ) VALUES (
                    ?, ?
                )
                """,
                vals,
            )

    def check_sid(self, sid: str) -> int | None:
        with self.db.connect() as conn:
            r = conn.execute(
                """
                SELECT uid, expires
                FROM users_sessions
                WHERE sid = ?
                """,
                [sid],
            ).fetchone()

            if not r:
                return None

            if r["expires"] < datetime.datetime.now().isoformat():
                return None

            return r["uid"]

    def check_kv_perms(self, uid: int, raw_table: str) -> dict[str, bool]:
        table = self.db.kv.prepare_kv_table_name(raw_table)

        return dict(
            read=self.check_perm(uid, self.db.kv.read_perm(table)),
            write=self.check_perm(uid, self.db.kv.write_perm(table)),
        )

    def check_perm(self, uid: int, perm: str) -> bool:
        with self.db.connect() as conn:
            r = conn.execute(
                """
                SELECT 1
                FROM users_permissions
                WHERE
                    uid = ?
                    AND perm = ?
                """,
                [uid, perm],
            ).fetchone()

        return bool(r)

    def find_uid_by_username(self, username: str) -> int | None:
        with self.db.connect() as conn:
            r = conn.execute(
                """
                SELECT id
                FROM users
                WHERE user = ?
                """,
                [username],
            ).fetchone()
            if not r:
                return None

        return r["id"]


@dataclass
class _KvHelper:
    db: KvDb

    def create(self, conn: Connection, raw_table: str):
        table = self.prepare_kv_table_name(raw_table)

        conn.execute(
            f"""
            CREATE TABLE {table.name} (
                key     TEXT    PRIMARY KEY,
                value   TEXT    NOT NULL        -- not strict, any data type
            )
            """
        )

    def select_value(self, raw_table: str, key: str):
        table = self.prepare_kv_table_name(raw_table)

        with self.db.connect() as conn:
            r = conn.execute(
                f"""
                SELECT value FROM {table.name}
                WHERE key = ?
                """,
                [key],
            ).fetchone()

        if not r:
            return dict(
                value=None,
                exists=False,
            )

        return dict(
            value=r["value"],
            exists=True,
        )

    def insert(self, conn: Connection, raw_table: str, key: str, value: Any):
        table = self.prepare_kv_table_name(raw_table)

        conn.execute(
            f"""
            INSERT OR REPLACE INTO {table.name} (
                key, value
            ) VALUES (
                ?, ?
            )
            """,
            [key, value],
        )

    def delete(self, conn: Connection, raw_table: str, key: str):
        table = self.prepare_kv_table_name(raw_table)

        conn.execute(
            f"""
            DELETE FROM {table.name}
            WHERE key = ?
            """,
            [key],
        )

    def prepare_kv_table_name(self, raw_table: str) -> "ValTableName":
        table = "kv_" + raw_table.lower()

        m = re.search(r"[^a-z_]", table, re.IGNORECASE)
        if m:
            raise Exception(f"Invalid table name: {raw_table}")

        return ValTableName(table)

    def read_perm(self, table: "ValTableName"):
        return f"{table.name}_read"

    def write_perm(self, table: "ValTableName"):
        return f"{table.name}_write"
