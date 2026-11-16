"""Trusted server-side commands, run inside the container.

python -m app.manage create-user demo            # password from NEW_USER_PASSWORD or a prompt
python -m app.manage create-user bridge --admin
python -m app.manage import                      # re-import corpus/ (unchanged files are skipped)
python -m app.manage stats
"""

import argparse
import getpass
import os
import sys

from fastapi import HTTPException

from app import database, security
from app.rag.store import Index
from app.settings import Settings


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.manage")
    commands = parser.add_subparsers(dest="command", required=True)
    user = commands.add_parser("create-user", help="create an account")
    user.add_argument("username")
    user.add_argument("--admin", action="store_true")
    commands.add_parser("import", help="import the transcripts in the corpus folder")
    commands.add_parser("stats", help="show what is indexed")
    args = parser.parse_args(argv)

    settings = Settings.load()
    database.initialize(settings)

    if args.command == "create-user":
        password = os.environ.get("NEW_USER_PASSWORD") or getpass.getpass(
            "Password (15+ characters): "
        )
        try:
            security.signup(settings, args.username, password)
        except HTTPException as error:
            print(error.detail, file=sys.stderr)
            return 1
        except ValueError:
            print(
                "Use a 3-32 character username and a 15-128 character password.",
                file=sys.stderr,
            )
            return 1
        if args.admin:
            database.set_role(settings, args.username, "admin")
        print(f"created {args.username} ({'admin' if args.admin else 'member'})")
        return 0

    index = Index(settings.rag_dir)
    if args.command == "import":
        for session_id, status in index.import_directory(settings.corpus).items():
            print(f"{session_id}: {status}")
    print(
        f"sessions: {len(index.sessions())}, "
        f"exchange chunks: {index.chunk_count('exchange')}, "
        f"fixed chunks: {index.chunk_count('fixed')}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
