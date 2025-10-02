import argparse
import asyncio
import socket
from dataclasses import dataclass
from typing import Annotated, Literal

import uvicorn
from litestar import Litestar, Response, delete, get, post
from litestar.datastructures import Cookie
from litestar.exceptions import NotAuthorizedException
from litestar.logging import LoggingConfig
from litestar.params import Parameter

from simple_kv.lib.kv_db import (
    KvDb,
    check_sid,
    check_table_perms,
    check_user_perm,
    select_from_kv,
)


@get("/ping")
async def ping() -> str:
    return "pong"


@dataclass
class LoginDto:
    username: str
    password: str


# Rate limit handled by nginx
@post("/login")
async def login(data: LoginDto) -> Response[dict]:
    db = KvDb()

    with db.connect() as conn:
        session = db.login(conn, data.username, data.password)
        if not session:
            raise NotAuthorizedException()

    return Response(
        session,
        cookies=[
            Cookie(
                key="sid",
                value=session["sid"],
                max_age=session["duration"],
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
    sid: Annotated[str, Parameter(cookie="sid")],
) -> None:
    db = KvDb()

    # Check session
    uid = check_sid(db, sid)
    if not uid:
        raise NotAuthorizedException()

    # Check perms
    can_create = check_user_perm(db, uid, db.ADMIN_PERM)
    if not can_create:
        raise NotAuthorizedException()

    # Create
    with db.connect() as conn:
        db.create_kv_table(conn, data.name)

        db.register_kv_table_user(
            conn,
            data.name,
            uid,
            read=True,
            write=True,
        )

        db.register_kv_table_user(
            conn,
            data.name,
            db.GUEST_USER_ID,
            read=data.allow_guest_read,
            write=data.allow_guest_write,
        )


@get("/kv/{raw_table:str}/{key:str}")
async def get_kv_item(
    raw_table: str,
    key: str,
    sid: Annotated[str | None, Parameter(cookie="sid")],
) -> dict:
    db = KvDb()

    # Check perms
    can_read = _check_kv_perms(db, raw_table, "read", sid)
    if not can_read:
        raise NotAuthorizedException()

    # Select
    return select_from_kv(db, raw_table, key)


@dataclass
class SetKvDto:
    value: str | float | bool


@post("/kv/{raw_table:str}/{key:str}")
async def set_kv_item(
    data: SetKvDto,
    raw_table: str,
    key: str,
    sid: Annotated[str | None, Parameter(cookie="sid")],
) -> None:
    db = KvDb()

    # Check perms
    can_write = _check_kv_perms(db, raw_table, "write", sid)
    if not can_write:
        raise NotAuthorizedException()

    # Insert
    with db.connect() as conn:
        db.insert_kv_item(conn, raw_table, key, data.value)


@delete("/kv/{raw_table:str}/{key:str}")
async def delete_kv_item(
    raw_table: str,
    key: str,
    sid: Annotated[str | None, Parameter(cookie="sid")],
) -> None:
    db = KvDb()

    # Check perms
    can_write = _check_kv_perms(db, raw_table, "write", sid)
    if not can_write:
        raise NotAuthorizedException()

    # Delete
    with db.connect() as conn:
        return db.delete_kv_item(conn, raw_table, key)


def _check_kv_perms(
    db: KvDb,
    raw_table: str,
    perm_type: Literal["read", "write"],
    sid: str | None,
):
    # Check guest
    guest_perms = check_table_perms(db, db.GUEST_USER_ID, raw_table)
    if guest_perms[perm_type]:
        return True

    # Check user
    if sid:
        uid = check_sid(db, sid)
        if uid:
            perms = check_table_perms(db, uid, raw_table)
            if perms[perm_type]:
                return True
            else:
                # Check admin
                is_admin = check_user_perm(db, uid, db.ADMIN_PERM)
                if is_admin:
                    return True

    return False


logging_config = LoggingConfig(
    root={"level": "INFO", "handlers": ["queue_listener"]},
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
        delete_kv_item,
    ],
    logging_config=logging_config,
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
    # Init db file
    KvDb(missing_ok=True)

    asyncio.run(main())
