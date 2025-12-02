import argparse
import asyncio
import socket
from dataclasses import dataclass
from typing import Annotated, Literal, TypeAlias

import uvicorn
from litestar import Litestar, Response, delete, get, post
from litestar.config.cors import CORSConfig
from litestar.datastructures import Cookie
from litestar.exceptions import NotAuthorizedException
from litestar.logging import LoggingConfig
from litestar.params import Parameter

from simple_kv.lib.kv.kv_mgr import KvMgr

JsonValue: TypeAlias = str | float | bool | None


@get("/ping")
async def ping() -> str:
    return "pong"


@dataclass
class LoginDto:
    username: str
    password: str
    duration: int | None


# Rate limit handled by nginx
@post("/login")
async def login(data: LoginDto) -> Response[dict]:
    mgr = KvMgr()

    with mgr.user_db.connect() as conn:
        session = mgr.user_db.login(
            conn,
            data.username,
            data.password,
            seconds=data.duration,
        )
        if not session:
            raise NotAuthorizedException()

    return Response(
        session,
        cookies=[
            Cookie(
                key="sid",
                value=session["sid"],
                max_age=session["duration"],
                httponly=True,
                samesite="none",
                secure=True,
            ),
        ],
    )


@dataclass
class CreateTableDto:
    name: str
    allow_guest_read: bool
    allow_guest_write: bool


# @todo: ep for modifying perms
@post("/create_kv")
async def create_kv_table(
    data: CreateTableDto,
    sid: Annotated[str, Parameter(header="sid")],
) -> bool:
    mgr = KvMgr()

    # Check session
    uid = mgr.user_db.check_sid(sid)
    if not uid:
        raise NotAuthorizedException()

    # Check perms
    can_create = mgr.user_db.check_perm(uid, mgr.ADMIN_PERM)
    if not can_create:
        raise NotAuthorizedException()

    if mgr.db_exists(data.name):
        return False

    # Create
    with mgr.user_db.connect() as conn:
        mgr.db(data.name, missing_ok=True)

        mgr.user_db.register_kv_table_user(
            conn,
            data.name,
            uid,
            read=True,
            write=True,
        )

        mgr.user_db.register_kv_table_user(
            conn,
            data.name,
            mgr.GUEST_USER_ID,
            read=data.allow_guest_read,
            write=data.allow_guest_write,
        )

    return True


@get("/kv/{dbid:str}/{key:str}")
async def get_kv_item(
    dbid: str,
    key: str,
    sid: Annotated[str | None, Parameter(header="sid")],
) -> dict:
    mgr = KvMgr()

    # Check perms
    can_read = _check_kv_perms(mgr, dbid, "read", sid)
    if not can_read:
        raise NotAuthorizedException()

    # Select
    return mgr.db(dbid).select.one(key)


@dataclass
class SetKvDto:
    value: JsonValue


@post("/kv/{dbid:str}/{key:str}")
async def set_kv_item(
    data: SetKvDto,
    dbid: str,
    key: str,
    sid: Annotated[str | None, Parameter(header="sid")],
) -> None:
    mgr = KvMgr()
    db = mgr.db(dbid)

    # Check perms
    can_write = _check_kv_perms(mgr, dbid, "write", sid)
    if not can_write:
        raise NotAuthorizedException()

    # Insert
    with db.connect() as conn:
        db.insert.one(conn, key, data.value)


@dataclass
class SetKvBulkDto:
    items: list[tuple[str, JsonValue]]


@post("/kv/{dbid:str}")
async def set_kv_bulk(
    data: SetKvBulkDto,
    dbid: str,
    sid: Annotated[str | None, Parameter(header="sid")],
) -> None:
    mgr = KvMgr()
    db = mgr.db(dbid)

    # Check perms
    can_write = _check_kv_perms(mgr, dbid, "write", sid)
    if not can_write:
        raise NotAuthorizedException()

    # Insert
    with db.connect() as conn:
        for [k, v] in data.items:
            db.insert.one(conn, k, v)


@delete("/kv/{dbid:str}/{key:str}")
async def delete_kv_item(
    dbid: str,
    key: str,
    sid: Annotated[str | None, Parameter(header="sid")],
) -> None:
    mgr = KvMgr()
    db = mgr.db(dbid)

    # Check perms
    can_write = _check_kv_perms(mgr, dbid, "write", sid)
    if not can_write:
        raise NotAuthorizedException()

    # Delete
    with db.connect() as conn:
        return db.delete.one(conn, key)


@dataclass
class ExecuteSqlDto:
    sql: str


@post("/select/{dbid:str}")
async def execute_sql(
    data: ExecuteSqlDto,
    dbid: str,
    sid: Annotated[str | None, Parameter(header="sid")],
) -> list[dict]:
    mgr = KvMgr()

    can_read = _check_kv_perms(mgr, dbid, "read", sid)
    if not can_read:
        raise NotAuthorizedException()

    db = mgr.db(dbid)
    with db.connect() as conn:
        rs = conn.execute(data.sql).fetchall()

    return [dict(r) for r in rs]


@post("/execute/{dbid:str}", request_max_body_size=50 * 1024**2)
async def execute_sql_script(
    data: ExecuteSqlDto,
    dbid: str,
    sid: Annotated[str | None, Parameter(header="sid")],
) -> None:
    mgr = KvMgr()

    can_read = _check_kv_perms(mgr, dbid, "read", sid)
    can_write = _check_kv_perms(mgr, dbid, "write", sid)
    if not (can_read and can_write):
        raise NotAuthorizedException()

    db = mgr.db(dbid)
    with db.connect() as conn:
        conn.executescript(data.sql)

    return


def _check_kv_perms(
    mgr: KvMgr,
    dbid: str,
    perm_type: Literal["read", "write"],
    sid: str | None,
):
    # Check guest
    guest_perms = mgr.user_db.check_kv_perms(mgr.GUEST_USER_ID, dbid)
    if guest_perms[perm_type]:
        return True

    # Check user
    if sid:
        uid = mgr.user_db.check_sid(sid)
        if uid:
            perms = mgr.user_db.check_kv_perms(uid, dbid)
            if perms[perm_type]:
                return True
            else:
                # Check admin
                is_admin = mgr.user_db.check_perm(uid, mgr.ADMIN_PERM)
                if is_admin:
                    return True

    return False


logging_config = LoggingConfig(
    root={"level": "DEBUG", "handlers": ["queue_listener"]},
    formatters={
        "standard": {"format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"}
    },
    log_exceptions="always",
)


app = Litestar(
    [
        ping,
        login,
        create_kv_table,
        get_kv_item,
        set_kv_item,
        set_kv_bulk,
        delete_kv_item,
        execute_sql,
        execute_sql_script,
    ],
    logging_config=logging_config,
    middleware=[
        # LoggingMiddlewareConfig(
        # request_log_fields=["headers"],
        # response_log_fields=["headers"],
        # ).middleware,
        # MyCorsMiddleware(),
    ],
    cors_config=CORSConfig(
        allow_origins=[""],
        allow_origin_regex=r".*",
    ),
)


def _parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8267)

    args = parser.parse_args()
    return args


async def main():
    args = _parse_args()

    config = uvicorn.Config(
        "__main__:app",
        port=args.port,
        host=args.host,
        workers=1,
    )

    server = uvicorn.Server(config)

    print(f"Running web server at host={config.host} port={config.port}")
    sock = socket.socket(family=socket.AF_INET)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    sock.bind((config.host, config.port))

    await server.serve(sockets=[sock])


if __name__ == "__main__":
    # Init user db file
    KvMgr()

    asyncio.run(main())
