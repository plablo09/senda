from __future__ import annotations

from unittest.mock import AsyncMock, patch

from api.tasks.cleanup import cleanup_expired_sessions


def _make_session() -> AsyncMock:
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    return session


def test_cleanup_expired_sessions_deletes_and_commits():
    session = _make_session()

    with patch("api.tasks.cleanup.AsyncSessionLocal", return_value=session):
        cleanup_expired_sessions()

    session.execute.assert_called_once()
    session.commit.assert_called_once()


def test_cleanup_expired_sessions_delete_uses_correct_conditions():
    """Verify the DELETE WHERE clause covers both expired and revoked rows."""
    session = _make_session()
    captured: list = []

    async def _capture_execute(stmt):
        captured.append(stmt)

    session.execute = AsyncMock(side_effect=_capture_execute)

    with patch("api.tasks.cleanup.AsyncSessionLocal", return_value=session):
        cleanup_expired_sessions()

    assert len(captured) == 1
    sql = str(captured[0].compile(compile_kwargs={"literal_binds": False}))
    assert "expires_at" in sql
    assert "revoked_at" in sql
