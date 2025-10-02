import argparse

from simple_kv.lib.kv_db import KvDb


def main():
    db = KvDb(missing_ok=True)

    args = _parse_args()
    match args.cmd:
        case "create" | "delete":
            _register_user(
                db,
                args,
                is_delete=args.cmd == "delete",
            )
        case "admin":
            _set_admin(db, args)
        case "table":
            _set_kv_perms(db, args)
        case _:
            raise Exception(f"Invalid command {args.cmd}")


def _register_user(db: KvDb, args, is_delete: bool):
    with db.connect() as conn:
        if not is_delete:
            if not args.password:
                raise Exception("No password provided")

            print(f"Creating user {args.username} with password {args.password}")
            db.user.register_user(conn, args.username, args.password)
        else:
            print(f"Deleting user {args.username}")
            conn.execute(
                """
                DELETE FROM users
                WHERE user = ?
                """,
                [args.username],
            )


def _set_admin(db: KvDb, args):
    with db.connect() as conn:
        uid = db.user.find_uid_by_username(args.username)
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
                [uid, db.ADMIN_PERM],
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
                [uid, db.ADMIN_PERM],
            )


def _set_kv_perms(db: KvDb, args):
    db = KvDb()

    with db.connect() as conn:
        uid = db.user.find_uid_by_username(args.username)
        if not uid:
            raise Exception(f"User does not exist: {args.username}")

        print(f"Modifying permissions for {args.username}")

        for table in args.tables:
            if not args.remove:
                if not args.no_read:
                    print(f"Enabling read of table {table}")
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO users_permissions (
                            uid, perm
                        ) VALUES (
                            ?, ?
                        )
                        """,
                        [uid, db.kv.read_perm(table)],
                    )
                if not args.no_write:
                    print(f"Enabling write of table {table}")
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO users_permissions (
                            uid, perm
                        ) VALUES (
                            ?, ?
                        )
                        """,
                        [uid, db.kv.write_perm(table)],
                    )
            else:
                if not args.no_read:
                    print(f"Disabling read of table {table}")
                    conn.execute(
                        """
                        DELETE FROM users_permissions
                        WHERE
                            uid = ?
                            AND perm = ?
                        """,
                        [uid, db.ADMIN_PERM],
                    )
                if not args.no_write:
                    print(f"Disabling write of table {table}")
                    conn.execute(
                        """
                        DELETE FROM users_permissions
                        WHERE
                            uid = ?
                            AND perm = ?
                        """,
                        [uid, db.kv.write_perm(table)],
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
