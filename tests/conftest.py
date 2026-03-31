"""
Shared test fixtures for auto-job-applier test suite.
"""

import os
import sys
import pytest
import pytest_asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def mock_config():
    """Mock configuration with sensible test defaults."""
    settings = {
        "app": {
            "daily_application_target": 10,
            "max_daily_applications": 25,
            "headless_browser": True,
            "blacklist_companies": ["Scam Corp"],
        },
        "ai": {
            "provider": "gemini",
            "gemini": {
                "api_key": "test-key-12345",
                "model": "gemini-2.0-flash",
                "max_requests_per_minute": 15,
                "max_requests_per_day": 1500,
                "temperature": 0.3,
            },
        },
        "browser": {
            "type": "chromium",
            "stealth_mode": True,
            "random_delays": False,
            "timeout_ms": 5000,
        },
        "portals": {
            "linkedin": {"enabled": True, "base_url": "https://www.linkedin.com", "max_applications_per_day": 5},
            "naukri": {"enabled": True, "base_url": "https://www.naukri.com", "max_applications_per_day": 5},
            "wellfound": {"enabled": False},
            "instahyre": {"enabled": False},
            "generic_career_page": {"enabled": True, "max_applications_per_day": 5},
        },
        "notifications": {"enabled": False},
        "reporting": {
            "google_sheets": {"enabled": False, "sheet_id": ""},
            "csv": {"enabled": True},
        },
    }

    profile = {
        "personal": {
            "first_name": "Test",
            "last_name": "User",
            "full_name": "Test User",
            "email": "test@example.com",
            "phone": "+91-9876543210",
        },
        "professional": {
            "current_title": "Senior SDET",
            "years_of_experience": 5,
            "preferred_locations": ["Pune", "Bangalore"],
        },
        "skills": {
            "primary": ["Python", "Selenium", "Playwright"],
            "secondary": ["JavaScript", "Docker"],
            "frameworks": ["pytest"],
            "tools": ["JIRA"],
        },
        "education": [
            {"degree": "B.E.", "field": "Computer Science", "university": "Test University", "graduation_year": 2018},
        ],
        "experience": [
            {
                "company": "Test Corp",
                "title": "Senior SDET",
                "start_date": "2022-01",
                "end_date": "present",
                "description": "Led test automation.",
                "highlights": ["Built E2E framework from scratch"],
            },
        ],
        "job_search": {
            "keywords": ["SDET", "QA Automation"],
            "exclude_keywords": ["Manual Testing", "Intern"],
        },
        "common_answers": {},
        "cover_letter_template": "Dear {company}, I am applying for {role}. {full_name}",
    }

    with patch("src.core.config.Config") as MockConfig:
        mock = MagicMock()
        mock._settings = settings
        mock._profile = profile
        mock.settings = settings
        mock.profile = profile

        def get_side_effect(*keys, default=None):
            d = settings
            for k in keys:
                if isinstance(d, dict):
                    d = d.get(k, default)
                else:
                    return default
            return d

        def get_profile_side_effect(*keys, default=None):
            d = profile
            for k in keys:
                if isinstance(d, dict):
                    d = d.get(k, default)
                else:
                    return default
            return d

        mock.get = MagicMock(side_effect=get_side_effect)
        mock.get_profile = MagicMock(side_effect=get_profile_side_effect)
        mock.get_portal_config = MagicMock(side_effect=lambda name: settings.get("portals", {}).get(name, {}))
        mock.is_portal_enabled = MagicMock(side_effect=lambda name: settings.get("portals", {}).get(name, {}).get("enabled", False))

        yield mock


@pytest.fixture
def mock_browser():
    """Mock BrowserManager."""
    browser = AsyncMock()
    browser.page = MagicMock()
    browser.context = MagicMock()
    browser.is_alive.return_value = True
    browser.start = AsyncMock()
    browser.stop = AsyncMock()
    browser.restart = AsyncMock()
    browser.ensure_alive = AsyncMock()
    browser.goto = AsyncMock(return_value=True)
    browser.take_screenshot = AsyncMock(return_value="/tmp/test_screenshot.png")
    browser.get_page_html = AsyncMock(return_value="<html><body>Test</body></html>")
    browser.get_visible_text = AsyncMock(return_value="Test page content")
    return browser


@pytest.fixture
def mock_ai():
    """Mock AIEngine."""
    ai = AsyncMock()
    ai.initialize = AsyncMock()
    ai.evaluate_job_match = AsyncMock(return_value={"match_score": 75, "should_apply": True})
    ai.analyze_page_for_forms = AsyncMock(return_value={"form_fields": [], "page_type": "application_form"})
    ai.generate_answer = AsyncMock(return_value="Test answer")
    ai.determine_next_action = AsyncMock(return_value={"action": "done"})
    return ai


@pytest.fixture
def sample_job_listing():
    """Sample job listing for testing."""
    from src.portals.base import JobListing
    return JobListing(
        portal="linkedin",
        job_id="li_12345",
        title="Senior SDET",
        company="Test Corp",
        location="Pune",
        salary_range="15-22 LPA",
        listing_url="https://linkedin.com/jobs/view/12345",
        apply_url="https://linkedin.com/jobs/view/12345/apply",
        match_score=80,
    )


@pytest.fixture
def sample_application_result():
    """Sample application result."""
    from src.portals.base import ApplicationResult
    from datetime import datetime
    return ApplicationResult(
        success=True,
        portal="linkedin",
        job_id="li_12345",
        job_title="Senior SDET",
        company="Test Corp",
        steps_completed=3,
        timestamp=datetime.now().isoformat(),
    )
