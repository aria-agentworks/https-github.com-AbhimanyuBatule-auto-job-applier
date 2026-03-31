"""Tests for the application tracker database."""

import asyncio
import os
import pytest
import pytest_asyncio
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, MagicMock


@pytest_asyncio.fixture
async def tracker(tmp_path):
    """Create a real tracker with a temporary database."""
    db_path = tmp_path / "test_applications.db"

    with patch("src.tracker.database.config") as mock_cfg:
        mock_cfg.get = MagicMock(return_value=str(db_path))

        with patch("src.tracker.database.PROJECT_ROOT", tmp_path):
            from src.tracker.database import ApplicationTracker
            tracker = ApplicationTracker()
            tracker._db_path = db_path
            await tracker.initialize()
            yield tracker
            await tracker.close()


@pytest_asyncio.fixture
async def sample_result():
    """Sample ApplicationResult."""
    from src.portals.base import ApplicationResult
    return ApplicationResult(
        success=True,
        portal="linkedin",
        job_id="li_12345",
        job_title="Senior SDET",
        company="Test Corp",
        steps_completed=3,
        timestamp=datetime.now().isoformat(),
    )


@pytest_asyncio.fixture
async def sample_listing():
    """Sample JobListing."""
    from src.portals.base import JobListing
    return JobListing(
        portal="linkedin",
        job_id="li_12345",
        title="Senior SDET",
        company="Test Corp",
        location="Pune",
        salary_range="15-22 LPA",
        listing_url="https://linkedin.com/jobs/view/12345",
    )


class TestApplicationTracker:
    """Test database operations."""

    @pytest.mark.asyncio
    async def test_initialize_creates_tables(self, tracker):
        """Database should have all required tables after init."""
        async with tracker._db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ) as cursor:
            tables = [row[0] for row in await cursor.fetchall()]

        assert "applications" in tables
        assert "job_listings" in tables
        assert "daily_stats" in tables
        assert "run_log" in tables

    @pytest.mark.asyncio
    async def test_record_application(self, tracker, sample_result):
        """Should record an application successfully."""
        count = await tracker.record_application(sample_result)
        assert count > 0

    @pytest.mark.asyncio
    async def test_is_already_applied_true(self, tracker, sample_result):
        """Should detect already-applied jobs."""
        await tracker.record_application(sample_result)
        result = await tracker.is_already_applied("linkedin", "li_12345")
        assert result is True

    @pytest.mark.asyncio
    async def test_is_already_applied_false(self, tracker):
        """Should return False for non-applied jobs."""
        result = await tracker.is_already_applied("linkedin", "li_99999")
        assert result is False

    @pytest.mark.asyncio
    async def test_record_job_listing(self, tracker, sample_listing):
        """Should record a job listing."""
        await tracker.record_job_listing(sample_listing)

        async with tracker._db.execute(
            "SELECT title, company FROM job_listings WHERE job_id = ?",
            ("li_12345",),
        ) as cursor:
            row = await cursor.fetchone()
        assert row is not None
        assert row[0] == "Senior SDET"

    @pytest.mark.asyncio
    async def test_duplicate_listing_ignored(self, tracker, sample_listing):
        """Duplicate job listings should be ignored (INSERT OR IGNORE)."""
        await tracker.record_job_listing(sample_listing)
        await tracker.record_job_listing(sample_listing)  # Should not raise

        async with tracker._db.execute(
            "SELECT COUNT(*) FROM job_listings WHERE job_id = ?",
            ("li_12345",),
        ) as cursor:
            count = (await cursor.fetchone())[0]
        assert count == 1

    @pytest.mark.asyncio
    async def test_get_today_stats(self, tracker, sample_result):
        """Should return today's stats correctly."""
        await tracker.record_application(sample_result)
        stats = await tracker.get_today_stats()
        assert stats["total"] >= 1
        assert stats["success"] >= 1

    @pytest.mark.asyncio
    async def test_get_total_stats(self, tracker, sample_result):
        """Should return all-time stats."""
        await tracker.record_application(sample_result)
        stats = await tracker.get_total_stats()
        assert stats["total"] >= 1

    @pytest.mark.asyncio
    async def test_start_and_end_run(self, tracker):
        """Should log a run start/end cycle."""
        run_id = await tracker.start_run()
        assert run_id > 0
        await tracker.end_run(run_id, 5, 3)

        async with tracker._db.execute(
            "SELECT status, total_applied, total_success FROM run_log WHERE id = ?",
            (run_id,),
        ) as cursor:
            row = await cursor.fetchone()
        assert row[0] == "completed"
        assert row[1] == 5
        assert row[2] == 3

    @pytest.mark.asyncio
    async def test_update_daily_stats(self, tracker, sample_result):
        """Should update daily stats with discovered count."""
        await tracker.record_application(sample_result)
        await tracker.update_daily_stats()

        today = datetime.now().strftime("%Y-%m-%d")
        async with tracker._db.execute(
            "SELECT total_applied FROM daily_stats WHERE date = ?", (today,)
        ) as cursor:
            row = await cursor.fetchone()
        assert row is not None
        assert row[0] >= 1

    @pytest.mark.asyncio
    async def test_get_recent_applications(self, tracker, sample_result):
        """Should return recent applications."""
        await tracker.record_application(sample_result)
        recent = await tracker.get_recent_applications(5)
        assert len(recent) >= 1
        assert recent[0]["job_title"] == "Senior SDET"

    @pytest.mark.asyncio
    async def test_on_conflict_updates_status(self, tracker):
        """Re-recording same job should update status, not overwrite."""
        from src.portals.base import ApplicationResult

        # First: failed attempt
        r1 = ApplicationResult(
            success=False, portal="linkedin", job_id="li_same",
            job_title="Job A", company="Co", error="timeout",
            timestamp=datetime.now().isoformat(),
        )
        await tracker.record_application(r1)

        # Second: success
        r2 = ApplicationResult(
            success=True, portal="linkedin", job_id="li_same",
            job_title="Job A", company="Co", steps_completed=5,
            timestamp=datetime.now().isoformat(),
        )
        await tracker.record_application(r2)

        # Should have updated to "applied", not created a duplicate
        async with tracker._db.execute(
            "SELECT status, steps_completed FROM applications WHERE job_id = 'li_same'"
        ) as cursor:
            row = await cursor.fetchone()
        assert row[0] == "applied"
        assert row[1] == 5

        # Should still be 1 record
        async with tracker._db.execute(
            "SELECT COUNT(*) FROM applications WHERE job_id = 'li_same'"
        ) as cursor:
            count = (await cursor.fetchone())[0]
        assert count == 1
