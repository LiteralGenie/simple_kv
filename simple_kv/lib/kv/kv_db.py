import sqlite3
from dataclasses import dataclass
from pathlib import Path
from sqlite3 import Connection
from typing import Any

from simple_kv.lib.db_wrapper import DbWrapper
from simple_kv.lib.loggers import KV_LOG
from simple_kv.lib.utils.kv_utils import KvIdentifier

_ACTION_CODE_TO_NAME = {getattr(sqlite3, k): k for k in dir(sqlite3)}


class KvDb(DbWrapper):
    enable_authorizer: bool

    dbid: str
    real_dbid: str
    select: "_KvDbSelect"
    insert: "_KvDbInsert"
    delete: "_KvDbDelete"

    def __init__(self, save_dir: Path, dbid: KvIdentifier, **kwargs):
        self.dbid = dbid.text
        self.real_dbid = self._real_dbid(dbid)

        self.enable_authorizer = False
        super().__init__(
            save_dir / self.save_name(dbid),
            **kwargs,
        )
        self.enable_authorizer = True

        self.select = _KvDbSelect(self)
        self.insert = _KvDbInsert(self)
        self.delete = _KvDbDelete(self)

    def init_schema(self, conn: Connection) -> None:
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS kv (
                key     TEXT    PRIMARY KEY,
                value   TEXT    NOT NULL        -- not strict, any data type
            )
            """
        )

    def connect(self):
        conn = super().connect()

        conn.set_authorizer(self._authorize)

        return conn

    # https://docs.python.org/3/library/sqlite3.html#sqlite3.Connection.set_authorizer
    # https://www.sqlite.org/c3ref/c_alter_table.html
    def _authorize(self, action_code: int, arg2, arg3, db_name, trigger_or_view):
        if not self.enable_authorizer:
            return sqlite3.SQLITE_OK

        match (action_code, arg2, arg3):
            case (sqlite3.SQLITE_CREATE_INDEX, index, table):
                return sqlite3.SQLITE_OK
            case (sqlite3.SQLITE_CREATE_TABLE, table, None):
                return sqlite3.SQLITE_OK
            case (sqlite3.SQLITE_INSERT, table, None):
                return sqlite3.SQLITE_OK
            case (sqlite3.SQLITE_READ, table, col):
                return sqlite3.SQLITE_OK
            case (sqlite3.SQLITE_SELECT, None, None):
                return sqlite3.SQLITE_OK
            case (sqlite3.SQLITE_TRANSACTION, op, None):
                if op in ["BEGIN", "COMMIT", "ROLLBACK"]:
                    return sqlite3.SQLITE_OK
            case (sqlite3.SQLITE_UPDATE, table, col):
                return sqlite3.SQLITE_OK
            case (sqlite3.SQLITE_ALTER_TABLE, self.real_dbid, table):
                return sqlite3.SQLITE_OK
            case (sqlite3.SQLITE_FUNCTION, None, function):
                if function in ["json_extract"]:
                    return sqlite3.SQLITE_OK

        name = _ACTION_CODE_TO_NAME.get(action_code, "???")
        KV_LOG.warning(f"SQL action rejected: {name} ({action_code}) {arg2} {arg3}")
        return sqlite3.SQLITE_DENY

    @classmethod
    def _real_dbid(cls, dbid: KvIdentifier):
        return f"kv_{dbid.text}"

    @classmethod
    def save_name(cls, dbid: KvIdentifier):
        return f"kv_{dbid.text}.sqlite"


@dataclass
class _KvDbSelect:
    db: KvDb

    def one(self, key: str):
        with self.db.connect() as conn:
            r = conn.execute(
                f"""
                SELECT value FROM kv
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


@dataclass
class _KvDbInsert:
    db: KvDb

    def one(self, conn: Connection, key: str, value: Any):
        conn.execute(
            f"""
            INSERT OR REPLACE INTO kv (
                key, value
            ) VALUES (
                ?, ?
            )
            """,
            [key, value],
        )


@dataclass
class _KvDbDelete:
    db: KvDb

    def one(self, conn: Connection, key: str):
        conn.execute(
            f"""
            DELETE FROM kv
            WHERE key = ?
            """,
            [key],
        )
