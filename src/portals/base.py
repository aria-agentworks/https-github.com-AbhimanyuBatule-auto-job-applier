"""
Base Portal Adapter - Abstract base class for all job portal adapters.
Each portal (LinkedIn, Naukri, etc.) extends this with portal-specific logic.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Optional
from dataclasses import dataclass, field

from src.core.browser import BrowserManager
from src.core.profile import ProfileManager
from src.core.form_filler import AdaptiveFormFiller
from src.ai.engine import AIEngine
from src.core.config import config

# TYPE_CHECKING import to avoid circular imports
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.tracker.database import ApplicationTracker

logger = logging.getLogger("portals.base")


@dataclass
class JobListing:
    """Represents a discovered job listing."""
    portal: str = ""
    job_id: str = ""
    title: str = ""
    company: str = ""
    location: str = ""
    salary_range: str = ""
    experience_required: str = ""
    job_type: str = ""
    work_mode: str = ""
    description: str = ""
    required_skills: list[str] = field(default_factory=list)
    posted_date: str = ""
    apply_url: str = ""
    listing_url: str = ""
    match_score: int = 0
    easy_apply: bool = False
    applied: bool = False
    raw_data: dict = field(default_factory=dict)


@dataclass
class ApplicationResult:
    """Result of an application attempt."""
    success: bool = False
    portal: str = ""
    job_id: str = ""
    job_title: str = ""
    company: str = ""
    steps_completed: int = 0
    error: str = ""
    screenshot_path: str = ""
    timestamp: str = ""


class BasePortalAdapter(ABC):
    """
    Abstract base class for portal-specific adapters.
    Each portal implements its own:
    - Login flow
    - Job search
    - Job listing extraction
    - Application flow
    """

    def __init__(
        self,
        browser: BrowserManager,
        profile: ProfileManager,
        ai: AIEngine,
        form_filler: AdaptiveFormFiller,
        tracker: "ApplicationTracker | None" = None,
    ):
        self.browser = browser
        self.profile = profile
        self.ai = ai
        self.form_filler = form_filler
        self.tracker = tracker
        self.portal_name = self.__class__.__name__.replace("Adapter", "").lower()
        self._config = config.get_portal_config(self.portal_name)
        self._max_daily = self._config.get("max_applications_per_day", 5)
        self._applied_today = 0

    @property
    def is_enabled(self) -> bool:
        return self._config.get("enabled", False)

    @property
    def base_url(self) -> str:
        return self._config.get("base_url", "")

    @property
    def can_apply_more(self) -> bool:
        return self._applied_today < self._max_daily

    # ── Abstract Methods (must implement) ───────────────────────

    @abstractmethod
    async def check_login_status(self) -> bool:
        """Check if user is logged in to this portal."""
        ...

    @abstractmethod
    async def login(self) -> bool:
        """Perform login (usually prompts user for first time)."""
        ...

    @abstractmethod
    async def search_jobs(self, keywords: list[str], location: str = "") -> list[JobListing]:
        """Search for jobs matching criteria."""
        ...

    @abstractmethod
    async def apply_to_job(self, job: JobListing) -> ApplicationResult:
        """Apply to a specific job listing."""
        ...

    # ── Common Methods ──────────────────────────────────────────

    async def ensure_logged_in(self) -> bool:
        """Ensure we're logged in, attempt login if not."""
        if await self.check_login_status():
            logger.info(f"Already logged in to {self.portal_name}")
            return True

        logger.info(f"Not logged in to {self.portal_name}, attempting login...")
        return await self.login()

    async def discover_and_apply(self) -> list[ApplicationResult]:
        """
        Full pipeline: discover jobs, filter, and apply.
        This is the main entry point for each portal.
        """
        results = []

        if not self.is_enabled:
            logger.info(f"{self.portal_name} is disabled, skipping")
            return results

        if not self.can_apply_more:
            logger.info(f"{self.portal_name} daily limit reached")
            return results

        # Ensure logged in
        if not await self.ensure_logged_in():
            logger.error(f"Cannot login to {self.portal_name}")
            return results

        # Search for jobs
        keywords = self.profile.get_search_keywords()
        preferred_locations = self.profile.professional.preferred_locations

        all_jobs = []
        for keyword in keywords[:3]:  # Limit keyword variations
            for location in preferred_locations[:2]:  # Limit locations
                try:
                    jobs = await self.search_jobs([keyword], location)
                    all_jobs.extend(jobs)
                except Exception as e:
                    logger.error(f"Search error on {self.portal_name}: {e}")

        # Deduplicate by job_id
        seen_ids = set()
        unique_jobs = []
        for job in all_jobs:
            if job.job_id not in seen_ids:
                seen_ids.add(job.job_id)
                unique_jobs.append(job)

        # Filter out already-applied jobs using tracker
        if self.tracker:
            new_jobs = []
            for job in unique_jobs:
                try:
                    already = await self.tracker.is_already_applied(self.portal_name, job.job_id)
                    if already:
                        logger.debug(f"Skipping already-applied: {job.title} at {job.company}")
                    else:
                        new_jobs.append(job)
                        # Record the job listing in the DB
                        try:
                            await self.tracker.record_job_listing(job)
                        except Exception:
                            pass
                except Exception as e:
                    logger.debug(f"Dedup check error: {e}")
                    new_jobs.append(job)  # Keep if check fails
            logger.info(f"Filtered {len(unique_jobs) - len(new_jobs)} already-applied jobs")
            unique_jobs = new_jobs

        logger.info(f"Found {len(unique_jobs)} unique jobs on {self.portal_name}")

        # Pre-filter: keyword blacklist + company blacklist (saves AI calls)
        exclude_keywords = [kw.lower() for kw in self.profile.get_exclude_keywords()]
        blacklisted_companies = [
            c.lower() for c in config.get("app", "blacklist_companies", default=[])
        ]
        if exclude_keywords or blacklisted_companies:
            filtered = []
            for job in unique_jobs:
                title_lower = job.title.lower()
                company_lower = job.company.lower()
                if any(kw in title_lower for kw in exclude_keywords):
                    logger.debug(f"Filtered by keyword: {job.title}")
                    continue
                if any(c == company_lower for c in blacklisted_companies):
                    logger.debug(f"Filtered by company blacklist: {job.company}")
                    continue
                filtered.append(job)
            if len(unique_jobs) != len(filtered):
                logger.info(f"Pre-filtered {len(unique_jobs) - len(filtered)} jobs by blacklist/keywords")
            unique_jobs = filtered

        # Filter and score jobs using AI
        scored_jobs = await self._score_jobs(unique_jobs)

        # Apply to top matching jobs
        for job in scored_jobs:
            if not self.can_apply_more:
                break

            if job.match_score < 50:
                logger.info(f"Skipping low-match job: {job.title} at {job.company} (score: {job.match_score})")
                continue

            try:
                logger.info(f"Applying to: {job.title} at {job.company} (score: {job.match_score})")
                result = await self.apply_to_job(job)
                results.append(result)

                if result.success:
                    self._applied_today += 1
                    logger.info(f"✓ Applied: {job.title} at {job.company}")
                else:
                    logger.warning(f"✗ Failed: {job.title} at {job.company} - {result.error}")

                # Delay between applications (be polite to servers)
                await asyncio.sleep(5)

            except Exception as e:
                logger.error(f"Application error: {job.title} - {e}")
                results.append(ApplicationResult(
                    success=False,
                    portal=self.portal_name,
                    job_title=job.title,
                    company=job.company,
                    error=str(e),
                ))

        return results

    async def _score_jobs(self, jobs: list[JobListing]) -> list[JobListing]:
        """Score and sort jobs by match quality."""
        profile_data = self.profile.to_flat_dict()

        for job in jobs:
            try:
                job_data = {
                    "title": job.title,
                    "company": job.company,
                    "location": job.location,
                    "description": job.description[:1000],
                    "required_skills": job.required_skills,
                    "salary_range": job.salary_range,
                    "experience_required": job.experience_required,
                }
                result = await self.ai.evaluate_job_match(job_data, profile_data)
                job.match_score = result.get("match_score", 50)
            except Exception as e:
                logger.warning(f"Scoring error for {job.title}: {e}")
                job.match_score = 50  # Default score

        # Sort by score descending
        jobs.sort(key=lambda j: j.match_score, reverse=True)
        return jobs

    async def _wait_random(self, min_s: float = 2, max_s: float = 5):
        """Random wait to appear human."""
        import random
        await asyncio.sleep(random.uniform(min_s, max_s))
