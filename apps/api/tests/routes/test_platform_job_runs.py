"""Tests for GET /api/platform/job-runs (worker/system job-run log).

Auth gate: ``platform.audit.read`` (same gate as the audit log — held by both
seeded platform system roles). The unprivileged-user fixture holds no grants
and must therefore 403. job_runs rows are seeded directly and cleaned up by
their unique ``job_name``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from xtrusio_api.core.db import SessionLocal
from xtrusio_api.models.platform_user import PlatformRole, PlatformUser
from xtrusio_api.services.job_runs import record_job_run

pytestmark = pytest.mark.asyncio(loop_scope="session")

_BASE = datetime(2026, 6, 6, 9, 0, 0, tzinfo=UTC)


@pytest_asyncio.fixture
async def unprivileged_user() -> AsyncIterator[PlatformUser]:
    """A provisioned platform user with NO grants — `platform.audit.read` false."""
    user_id = uuid4()
    email = f"pjobs-noperm-{user_id.hex[:8]}@example.com"
    async with SessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, encrypted_password, "
                "email_confirmed_at, created_at, updated_at) VALUES "
                "(:id, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', "
                ":email, '', now(), now(), now())"
            ),
            {"id": str(user_id), "email": email},
        )
        pu = PlatformUser(id=user_id, email=email, role=PlatformRole.EDITOR, is_active=True)
        s.add(pu)
        await s.commit()
        await s.refresh(pu)
    try:
        yield pu
    finally:
        async with SessionLocal() as s:
            await s.execute(
                text("DELETE FROM user_roles WHERE auth_user_id = :id"), {"id": str(user_id)}
            )
            await s.execute(text("DELETE FROM platform_users WHERE id = :id"), {"id": str(user_id)})
            await s.execute(text("DELETE FROM auth.users WHERE id = :id"), {"id": str(user_id)})
            await s.commit()


async def _seed_runs(job_name: str, n: int) -> None:
    async with SessionLocal() as s:
        for i in range(n):
            started = _BASE + timedelta(minutes=i)
            await record_job_run(
                s,
                job_name=job_name,
                status="success",
                started_at=started,
                finished_at=started + timedelta(seconds=1),
                duration_ms=1000,
                items_processed=2,
                items_succeeded=2,
                items_failed=0,
            )
        await s.commit()


async def _cleanup_runs(job_name: str) -> None:
    async with SessionLocal() as s:
        await s.execute(text("DELETE FROM job_runs WHERE job_name = :jn"), {"jn": job_name})
        await s.commit()


async def test_list_requires_auth(http_client: AsyncClient) -> None:
    res = await http_client.get("/api/platform/job-runs")
    assert res.status_code == 401


async def test_list_403_for_unprivileged(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    unprivileged_user: PlatformUser,
) -> None:
    token = make_jwt(sub=unprivileged_user.id)
    res = await http_client.get(
        "/api/platform/job-runs", headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 403
    assert res.json()["detail"] == "permission_denied"


async def test_list_200_shape_and_job_name_filter(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
) -> None:
    jn = f"test_jobrun_route_{uuid4().hex}"
    try:
        await _seed_runs(jn, 2)
        token = make_jwt(sub=existing_super_admin.id)
        res = await http_client.get(
            f"/api/platform/job-runs?job_name={jn}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert "next_cursor" in body
        assert len(body["items"]) == 2
        for r in body["items"]:
            assert r["job_name"] == jn
            assert r["status"] == "success"
            assert r["items_processed"] == 2
    finally:
        await _cleanup_runs(jn)


async def test_list_rejects_invalid_cursor(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
) -> None:
    token = make_jwt(sub=existing_super_admin.id)
    res = await http_client.get(
        "/api/platform/job-runs?cursor=not-a-cursor",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "invalid cursor"
