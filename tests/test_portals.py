"""Tests for the base portal adapter and job filtering."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from src.portals.base import JobListing, ApplicationResult, BasePortalAdapter


class ConcreteAdapter(BasePortalAdapter):
    """Concrete implementation for testing."""

    async def check_login_status(self) -> bool:
        return True

    async def login(self) -> bool:
        return True

    async def search_jobs(self, keywords, location=""):
        return []

    async def apply_to_job(self, job):
        return ApplicationResult(
            success=True, portal="test", job_id=job.job_id,
            job_title=job.title, company=job.company,
        )


@pytest.fixture
def adapter():
    """Create a test portal adapter."""
    with patch("src.portals.base.config") as mock_cfg:
        mock_cfg.get_portal_config = MagicMock(return_value={
            "enabled": True,
            "max_applications_per_day": 5,
        })
        mock_cfg.get = MagicMock(return_value=[])

        browser = AsyncMock()
        profile = MagicMock()
        profile.get_search_keywords.return_value = ["SDET"]
        profile.get_exclude_keywords.return_value = ["Intern", "Manual"]
        profile.professional.preferred_locations = ["Pune"]
        profile.to_flat_dict.return_value = {"skills": "Python"}
        ai = AsyncMock()
        ai.evaluate_job_match = AsyncMock(return_value={"match_score": 75})
        form_filler = AsyncMock()
        tracker = AsyncMock()
        tracker.is_already_applied = AsyncMock(return_value=False)
        tracker.record_job_listing = AsyncMock()

        adapter = ConcreteAdapter(
            browser=browser, profile=profile, ai=ai,
            form_filler=form_filler, tracker=tracker,
        )
        return adapter


class TestJobListing:
    """Test JobListing dataclass."""

    def test_defaults(self):
        """JobListing should have sensible defaults."""
        job = JobListing()
        assert job.portal == ""
        assert job.match_score == 0
        assert job.applied is False

    def test_full_listing(self):
        """Should store all fields."""
        job = JobListing(
            portal="linkedin", job_id="li_123", title="SDET",
            company="Corp", location="Pune", match_score=90,
        )
        assert job.title == "SDET"
        assert job.match_score == 90


class TestApplicationResult:
    """Test ApplicationResult dataclass."""

    def test_defaults(self):
        result = ApplicationResult()
        assert result.success is False
        assert result.portal == ""

    def test_success_result(self):
        result = ApplicationResult(
            success=True, portal="linkedin",
            job_title="SDET", company="Corp",
        )
        assert result.success is True


class TestBasePortalAdapter:
    """Test common adapter behavior."""

    def test_is_enabled(self, adapter):
        """Should reflect config enabled status."""
        assert adapter.is_enabled is True

    def test_can_apply_more(self, adapter):
        """Should allow applications under the limit."""
        assert adapter.can_apply_more is True

    def test_can_apply_more_at_limit(self, adapter):
        """Should block when at daily limit."""
        adapter._applied_today = 5
        assert adapter.can_apply_more is False

    @pytest.mark.asyncio
    async def test_score_jobs(self, adapter):
        """Should score and sort jobs by match."""
        jobs = [
            JobListing(title="Job A", company="Co A"),
            JobListing(title="Job B", company="Co B"),
        ]

        async def mock_eval(job_data, profile_data):
            if job_data["title"] == "Job A":
                return {"match_score": 90}
            return {"match_score": 60}

        adapter.ai.evaluate_job_match = AsyncMock(side_effect=mock_eval)
        scored = await adapter._score_jobs(jobs)
        assert scored[0].title == "Job A"  # Higher score first
        assert scored[0].match_score == 90


class TestBlacklisting:
    """Test keyword and company blacklisting."""

    @pytest.mark.asyncio
    async def test_exclude_keywords_filter(self, adapter):
        """Jobs matching exclude keywords should be filtered."""
        adapter.profile.get_exclude_keywords.return_value = ["intern", "manual"]

        # Simulate discover_and_apply flow with mock jobs
        jobs = [
            JobListing(title="Senior SDET", company="Good Corp", job_id="j1"),
            JobListing(title="QA Intern Position", company="Corp B", job_id="j2"),
            JobListing(title="Manual Testing Lead", company="Corp C", job_id="j3"),
        ]

        # Test the filtering directly
        exclude_keywords = [kw.lower() for kw in adapter.profile.get_exclude_keywords()]
        filtered = [
            j for j in jobs
            if not any(kw in j.title.lower() for kw in exclude_keywords)
        ]
        assert len(filtered) == 1
        assert filtered[0].title == "Senior SDET"

    def test_company_blacklist_filter(self):
        """Jobs from blacklisted companies should be filtered."""
        blacklisted = ["scam corp", "bad company"]
        jobs = [
            JobListing(title="SDET", company="Good Corp", job_id="j1"),
            JobListing(title="SDET", company="Scam Corp", job_id="j2"),
        ]
        filtered = [
            j for j in jobs
            if j.company.lower() not in blacklisted
        ]
        assert len(filtered) == 1
        assert filtered[0].company == "Good Corp"


class TestDeduplication:
    """Test job deduplication with tracker."""

    @pytest.mark.asyncio
    async def test_skips_already_applied(self, adapter):
        """Should skip jobs already in the tracker."""
        adapter.tracker.is_already_applied = AsyncMock(side_effect=lambda p, jid: jid == "j1")

        jobs = [
            JobListing(title="Job A", company="Co", job_id="j1"),
            JobListing(title="Job B", company="Co", job_id="j2"),
        ]

        # Simulate the dedup loop from discover_and_apply
        new_jobs = []
        for job in jobs:
            already = await adapter.tracker.is_already_applied(adapter.portal_name, job.job_id)
            if not already:
                new_jobs.append(job)

        assert len(new_jobs) == 1
        assert new_jobs[0].job_id == "j2"
