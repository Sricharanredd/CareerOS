"""Owner and database maintenance commands.

python -m app.cli bootstrap-owner --email you@example.com
python -m app.cli reset-password --email you@example.com
python -m app.cli revoke-sessions
python -m app.cli check-db
"""

from __future__ import annotations

import argparse
import getpass
import sys

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import hash_password, verify_password
from app.db.session import assert_mysql_8, session_scope
from app.repositories import owner as owner_repo
from app.repositories import session as session_repo
from app.services import auth as auth_service

MIN_PASSWORD = 12


def _read_password(confirm: bool = True, current: str | None = None) -> str:
    while True:
        first = getpass.getpass("Password: ")
        if len(first) < MIN_PASSWORD:
            print(f"Use at least {MIN_PASSWORD} characters.", file=sys.stderr)
            continue
        if current is not None and not verify_password(first, current):
            print("Password does not match the current one.", file=sys.stderr)
            continue
        if not confirm:
            return first
        second = getpass.getpass("Confirm password: ")
        if first != second:
            print("Passwords do not match.", file=sys.stderr)
            continue
        return first


def cmd_bootstrap_owner(args: argparse.Namespace) -> int:
    with session_scope() as db:
        if owner_repo.owner_exists(db):
            print("An owner already exists. CareerOS supports exactly one owner.", file=sys.stderr)
            return 1
        password = args.password or _read_password()
        owner = auth_service.create_owner(
            db, email=args.email, password=password, full_name=args.name
        )
        print(f"Created owner {owner.email} (id={owner.id}).")
    return 0


def cmd_reset_password(args: argparse.Namespace) -> int:
    with session_scope() as db:
        owner = owner_repo.get_by_email(db, args.email)
        if owner is None:
            print("No owner with that email.", file=sys.stderr)
            return 1
        password = args.password or _read_password()
        owner.password_hash = hash_password(password)
        revoked = session_repo.revoke_owner_sessions(db, owner.id)
        print(f"Password reset for {owner.email}. Revoked {revoked} session(s).")
    return 0


def cmd_revoke_sessions(args: argparse.Namespace) -> int:
    with session_scope() as db:
        owner = owner_repo.get_owner(db)
        if owner is None:
            print("No owner account yet.", file=sys.stderr)
            return 1
        revoked = session_repo.revoke_owner_sessions(db, owner.id)
        print(f"Revoked {revoked} active session(s).")
    return 0


def cmd_check_db(args: argparse.Namespace) -> int:
    settings = get_settings()
    version = assert_mysql_8()
    print(f"MySQL {version} OK")
    print(f"Environment: {settings.careeros_env}")
    print(f"Database: {settings.active_database_url().split('@')[-1]}")
    with session_scope() as db:
        owner = owner_repo.get_owner(db)
        print(f"Owner configured: {'yes' if owner else 'no'}")
        if owner:
            print(f"Active sessions: {len(session_repo.list_active(db, owner.id))}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="CareerOS admin CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    bootstrap = sub.add_parser("bootstrap-owner", help="Create the single owner account")
    bootstrap.add_argument("--email", required=True)
    bootstrap.add_argument("--name", default=None)
    bootstrap.add_argument("--password", default=None, help="Prefer the interactive prompt")
    bootstrap.set_defaults(func=cmd_bootstrap_owner)

    reset = sub.add_parser("reset-password", help="Reset the owner password and revoke sessions")
    reset.add_argument("--email", required=True)
    reset.add_argument("--password", default=None)
    reset.set_defaults(func=cmd_reset_password)

    revoke = sub.add_parser("revoke-sessions", help="Sign out every active session")
    revoke.set_defaults(func=cmd_revoke_sessions)

    check = sub.add_parser("check-db", help="Validate the MySQL connection and owner state")
    check.set_defaults(func=cmd_check_db)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except AppError as exc:
        print(f"{exc.code}: {exc.message}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
