import argparse

from simple_kv.lib.kv.kv_mgr import KvMgr


def main():
    mgr = KvMgr()

    args = _parse_args()
    match args.cmd:
        case "create" | "delete":
            _register_user(
                mgr,
                args,
                is_delete=args.cmd == "delete",
            )
        case "admin":
            _set_admin(mgr, args)
        case "table":
            _set_kv_perms(mgr, args)
        case _:
            raise Exception(f"Invalid command {args.cmd}")


def _register_user(mgr: KvMgr, args, is_delete: bool):
    with mgr.user_db.connect() as conn:
        if not is_delete:
            if not args.password:
                raise Exception("No password provided")

            print(f"Creating user {args.username} with password {args.password}")
            mgr.user_db.register_user(conn, args.username, args.password)
        else:
            print(f"Deleting user {args.username}")
            conn.execute(
                """
                DELETE FROM users
                WHERE user = ?
                """,
                [args.username],
            )


def _set_admin(mgr: KvMgr, args):
    with mgr.user_db.connect() as conn:
        uid = mgr.user_db.find_uid_by_username(args.username)
        if not uid:
            raise Exception(f"User does not exist: {args.username}")

        if not args.remove:
            print(f"Adding admin perm to {args.username}")
            conn.execute(
                """
                INSERT OR REPLACE INTO users_permissions (
                    uid, perm
                ) VALUES (
                    ?, ?
                )
                """,
                [uid, mgr.ADMIN_PERM],
            )
        else:
            print(f"Removing admin perm from {args.username}")
            conn.execute(
                """
                DELETE FROM users_permissions
                WHERE
                    uid = ?
                    AND perm = ?
                """,
                [uid, mgr.ADMIN_PERM],
            )


def _set_kv_perms(mgr: KvMgr, args):
    mgr = KvMgr()

    with mgr.user_db.connect() as conn:
        uid = mgr.user_db.find_uid_by_username(args.username)
        if not uid:
            raise Exception(f"User does not exist: {args.username}")

        print(f"Modifying permissions for {args.username}")

        for dbid in args.tables:
            if not args.remove:
                if not args.no_read:
                    print(f"Enabling read of table {dbid}")
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO users_permissions (
                            uid, perm
                        ) VALUES (
                            ?, ?
                        )
                        """,
                        [uid, mgr.user_db.read_perm(dbid)],
                    )
                if not args.no_write:
                    print(f"Enabling write of table {dbid}")
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO users_permissions (
                            uid, perm
                        ) VALUES (
                            ?, ?
                        )
                        """,
                        [uid, mgr.user_db.write_perm(dbid)],
                    )
            else:
                if not args.no_read:
                    print(f"Disabling read of table {dbid}")
                    conn.execute(
                        """
                        DELETE FROM users_permissions
                        WHERE
                            uid = ?
                            AND perm = ?
                        """,
                        [uid, mgr.ADMIN_PERM],
                    )
                if not args.no_write:
                    print(f"Disabling write of table {dbid}")
                    conn.execute(
                        """
                        DELETE FROM users_permissions
                        WHERE
                            uid = ?
                            AND perm = ?
                        """,
                        [uid, mgr.user_db.write_perm(dbid)],
                    )


#


def _parse_args():
    parser = argparse.ArgumentParser()
    subs = parser.add_subparsers(dest="cmd")

    _parse_register_user(subs)
    _parse_set_admin_perm(subs)
    _parse_set_kv_perms(subs)

    args = parser.parse_args()
    return args


def _parse_register_user(subs: argparse._SubParsersAction):
    parser: argparse.ArgumentParser = subs.add_parser(
        "create",
        description="Create user",
    )
    parser.add_argument("username")
    parser.add_argument("password")

    parser: argparse.ArgumentParser = subs.add_parser(
        "delete",
        description="Delete user",
    )
    parser.add_argument("username")


def _parse_set_admin_perm(subs: argparse._SubParsersAction):
    parser: argparse.ArgumentParser = subs.add_parser(
        "admin",
        description="Mark / unmark user as admin",
    )
    parser.add_argument("username")
    parser.add_argument(
        "--remove",
        action="store_true",
    )


def _parse_set_kv_perms(subs: argparse._SubParsersAction):
    parser: argparse.ArgumentParser = subs.add_parser(
        "table",
        description="Add / remove user permissions for tables",
    )
    parser.add_argument("username")
    parser.add_argument(
        "tables",
        type=str,
        nargs=argparse.REMAINDER,
    )
    parser.add_argument(
        "--remove",
        action="store_true",
    )
    parser.add_argument(
        "--no-read",
        action="store_true",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
    )


#

main()
