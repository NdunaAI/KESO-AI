"""CLI to create local users for the self-issued JWT auth flow.

See docs/07-security-auth.md #7.1 -- there is no self-service signup in the
PoC, so accounts are provisioned by an operator with this command, run
inside the api-gateway container (or a matching venv):

    python -m app.manage create-user --email pm@keso.org --password 'x' \\
        --display-name "Alice PM" --role project_manager \\
        --settlement A --settlement C
"""

from __future__ import annotations

import argparse
import asyncio

from app.db import SessionLocal, init_models
from app.db_models import User, UserScope
from app.security import hash_password


async def create_user(
    email: str,
    password: str,
    display_name: str,
    roles: list[str],
    projects: list[str],
    settlements: list[str],
) -> None:
    await init_models()
    async with SessionLocal() as db:
        user = User(
            email=email.lower(),
            password_hash=hash_password(password),
            display_name=display_name,
            roles=roles,
        )
        db.add(user)
        await db.flush()
        for project_id in projects:
            db.add(UserScope(user_id=user.id, scope_type="project", scope_value=project_id))
        for settlement_id in settlements:
            db.add(UserScope(user_id=user.id, scope_type="settlement", scope_value=settlement_id))
        await db.commit()
        print(f"Created user {email} ({user.id}) with roles {roles}")


def main() -> None:
    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(dest="command", required=True)

    create = subcommands.add_parser("create-user")
    create.add_argument("--email", required=True)
    create.add_argument("--password", required=True)
    create.add_argument("--display-name", required=True)
    create.add_argument("--role", action="append", dest="roles", required=True)
    create.add_argument("--project", action="append", dest="projects", default=[])
    create.add_argument("--settlement", action="append", dest="settlements", default=[])

    args = parser.parse_args()
    if args.command == "create-user":
        asyncio.run(
            create_user(
                args.email, args.password, args.display_name, args.roles, args.projects, args.settlements
            )
        )


if __name__ == "__main__":
    main()
