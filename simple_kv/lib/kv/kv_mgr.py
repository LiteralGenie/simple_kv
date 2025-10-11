import datetime
import secrets
from pathlib import Path
from sqlite3 import Connection

import bcrypt

from simple_kv.lib.db_wrapper import DbWrapper
from simple_kv.lib.kv.kv_db import KvDb
from simple_kv.lib.loggers import KV_LOG
from simple_kv.lib.paths import KV_DIR
from simple_kv.lib.utils.kv_utils import KvIdentifier


class KvMgr:
    GUEST_USER_ID = 1
    GUEST_USER = "anon"

    ADMIN_PERM = "admin"

    save_dir: Path
    user_db: "KvUserDb"

    def __init__(self, save_dir=KV_DIR):
        self.save_dir = save_dir
        self.user_db = KvUserDb(
            self.save_dir / "auth.sqlite",
            missing_ok=True,
        )

        self.user_db = KvUserDb(self.save_dir / "auth.sqlite")

    def db(self, raw_name: str, missing_ok=False):
        name = KvIdentifier.validate(raw_name)
        return KvDb(
            self.save_dir,
            name,
            missing_ok=missing_ok,
        )

    def db_exists(self, raw_name: str):
        name = KvIdentifier.validate(raw_name)
        fp = self.save_dir / KvDb.save_name(name)
        return fp.exists()


class KvUserDb(DbWrapper):
    def __init__(self, fp: Path, **kwargs):
        super().__init__(fp, **kwargs)

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
                expires     TEXT,

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
            [KvMgr.GUEST_USER_ID, KvMgr.GUEST_USER, b""],
        )

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

    def login(
        self,
        conn: Connection,
        username: str,
        raw_password: str,
        seconds: int | None = 86400,
    ) -> dict | None:
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

        if seconds:
            duration = datetime.timedelta(seconds=seconds)
            expires = duration + datetime.datetime.now(tz=datetime.timezone.utc)
            expires = expires.isoformat()
        else:
            duration = None
            expires = None

        conn.execute(
            """
            INSERT INTO users_sessions (
                uid, sid, expires
            ) VALUES (
                ?, ?, ?
            )
            """,
            [r["id"], sid, expires],
        )

        self.vacuum_sessions(conn)

        return dict(
            sid=sid,
            uid=r["id"],
            username=username,
            duration=seconds,
            expires=expires,
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
            KV_LOG.info(f"Vacuum'd {cursor.rowcount} sessions")

    def register_kv_table_user(
        self,
        conn: Connection,
        dbid: str,
        uid: int,
        read=False,
        write=False,
    ):
        all_vals = []
        if read:
            all_vals.append((uid, self.read_perm(dbid)))
        if write:
            all_vals.append((uid, self.write_perm(dbid)))

        for vals in all_vals:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO users_permissions (
                    uid, perm
                ) VALUES (
                    ?, ?
                )
                """,
                vals,
            )

    def check_sid(self, sid: str) -> int | None:
        with self.connect() as conn:
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

            if (
                r["expires"] is not None
                and r["expires"] < datetime.datetime.now().isoformat()
            ):
                return None

            return r["uid"]

    def check_kv_perms(self, uid: int, dbid: str) -> dict[str, bool]:
        return dict(
            read=self.check_perm(uid, self.read_perm(dbid)),
            write=self.check_perm(uid, self.write_perm(dbid)),
        )

    def check_perm(self, uid: int, perm: str) -> bool:
        with self.connect() as conn:
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
        with self.connect() as conn:
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

    def read_perm(self, dbid: str):
        return f"{dbid}_read"

    def write_perm(self, dbid: str):
        return f"{dbid}_write"
