"""CLI to bootstrap the first platform super_admin.

Usage:
    python -m xtrusio_api.scripts.bootstrap create-platform-owner \\
        --email owner@example.com --password '...'
"""

from __future__ import annotations

import asyncio
import sys
from typing import Annotated

import typer
from sqlalchemy import select
from supabase import create_client

from ..core.config import get_settings
from ..core.db import SessionLocal
from ..models.platform_user import PlatformRole, PlatformUser

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command()
def create_platform_owner(
    email: Annotated[str, typer.Option("--email", help="Owner email address")],
    password: Annotated[str, typer.Option("--password", help="Initial password")],
    force: Annotated[
        bool, typer.Option("--force", help="Override existing super_admin check")
    ] = False,
) -> None:
    """Create the platform's first super_admin (Supabase auth + platform_users row)."""
    asyncio.run(_run(email=email, password=password, force=force))


async def _run(*, email: str, password: str, force: bool) -> None:
    settings = get_settings()
    sb = create_client(settings.supabase_url, settings.supabase_service_role_key)

    async with SessionLocal() as db:
        existing = (
            await db.execute(
                select(PlatformUser).where(PlatformUser.role == PlatformRole.SUPER_ADMIN)
            )
        ).scalar_one_or_none()
        if existing and not force:
            typer.echo(
                f"❌ super_admin already exists: {existing.email}. "
                f"Re-run with --force to override.",
                err=True,
            )
            sys.exit(1)

        result = sb.auth.admin.create_user(
            {"email": email, "password": password, "email_confirm": True}
        )
        if result.user is None:
            typer.echo("❌ Supabase did not return a user.", err=True)
            sys.exit(2)

        db.add(
            PlatformUser(
                id=result.user.id,
                email=email,
                role=PlatformRole.SUPER_ADMIN,
                is_active=True,
            )
        )
        await db.commit()

    typer.echo(f"✅ super_admin created: {email}")
    typer.echo("   Sign in at http://localhost:5173/sign-in")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
