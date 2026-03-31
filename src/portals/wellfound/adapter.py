"""
Wellfound (AngelList) Portal Adapter
Startup-focused job portal with salary transparency.
"""

import asyncio
import re
import logging
import hashlib
from typing import Optional
from datetime import datetime

from src.portals.base import BasePortalAdapter, JobListing, ApplicationResult

logger = logging.getLogger("portals.wellfound")


class WellfoundAdapter(BasePortalAdapter):
    """Wellfound-specific job search and application automation."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.portal_name = "wellfound"

    async def check_login_status(self) -> bool:
        """Check if logged into Wellfound."""
        await self.browser.goto("https://wellfound.com/jobs")
        await asyncio.sleep(3)
        url = await self.browser.get_current_url()
        if "login" in url or "sign_up" in url:
            return False
        return await self.browser.element_exists('[data-test="UserMenu"]') or \
               await self.browser.element_exists('.styles_component__navigation')

    async def login(self) -> bool:
        """Login to Wellfound."""
        await self.browser.goto("https://wellfound.com/login")
        await asyncio.sleep(2)

        if await self.check_login_status():
            return True

        logger.warning("Please log in to Wellfound manually. Session will be saved.")

        for _ in range(60):
            await asyncio.sleep(5)
            url = await self.browser.get_current_url()
            if "jobs" in url or "profile" in url:
                logger.info("Wellfound login successful!")
                return True

        return False

    async def search_jobs(self, keywords: list[str], location: str = "") -> list[JobListing]:
        """Search for jobs on Wellfound."""
        jobs = []
        keyword_str = " ".join(keywords)

        search_url = f"https://wellfound.com/role/r/{keyword_str.lower().replace(' ', '-')}"
        if location:
            search_url += f"/{location.lower().replace(' ', '-')}"

        await self.browser.goto(search_url)
        await asyncio.sleep(3)

        # Scroll to load
        for _ in range(3):
            await self.browser.scroll_down(600)
            await asyncio.sleep(1)

        # Extract job cards
        job_cards = await self.browser.page.query_selector_all(
            '[data-test="StartupResult"], .styles_result, .job-listing'
        )

        for card in job_cards[:15]:
            try:
                job = await self._extract_job_from_card(card)
                if job:
                    jobs.append(job)
            except Exception as e:
                logger.debug(f"Error extracting Wellfound card: {e}")

        logger.info(f"Wellfound: Found {len(jobs)} jobs")
        return jobs

    async def apply_to_job(self, job: JobListing) -> ApplicationResult:
        """Apply to a Wellfound job."""
        result = ApplicationResult(
            portal="wellfound",
            job_id=job.job_id,
            job_title=job.title,
            company=job.company,
            timestamp=datetime.now().isoformat(),
        )

        try:
            await self.browser.goto(job.listing_url or job.apply_url)
            await asyncio.sleep(3)

            # Click Apply button
            apply_btn = await self.browser.page.query_selector(
                'button:has-text("Apply"), '
                '[data-test="ApplyButton"], '
                'a:has-text("Apply Now")'
            )

            if apply_btn:
                await apply_btn.click()
                await asyncio.sleep(3)

                # Fill the application form
                job_context = {"title": job.title, "company": job.company}
                form_result = await self.form_filler.handle_multi_step_form(
                    max_steps=5, job_context=job_context
                )
                result.success = form_result.get("success", False)
                result.steps_completed = form_result.get("steps", 0)
            else:
                result.error = "No apply button found"

        except Exception as e:
            result.error = str(e)

        result.screenshot_path = await self.browser.take_screenshot(
            f"wellfound_{'success' if result.success else 'fail'}_{job.job_id}"
        )
        return result

    async def _extract_job_from_card(self, card) -> Optional[JobListing]:
        """Extract job from Wellfound card."""
        try:
            title_el = await card.query_selector('h2, .styles_title, [data-test="JobTitle"]')
            company_el = await card.query_selector('h3, .styles_name, [data-test="StartupName"]')
            salary_el = await card.query_selector('.styles_compensation, [data-test="Compensation"]')
            location_el = await card.query_selector('.styles_location, [data-test="Location"]')
            link_el = await card.query_selector('a[href*="/jobs/"]')

            title = (await title_el.text_content()).strip() if title_el else ""
            company = (await company_el.text_content()).strip() if company_el else ""
            salary = (await salary_el.text_content()).strip() if salary_el else ""
            location = (await location_el.text_content()).strip() if location_el else ""
            href = (await link_el.get_attribute("href")) if link_el else ""

            if not title:
                return None

            if href and not href.startswith("http"):
                href = f"https://wellfound.com{href}"

            job_id = hashlib.md5(f"{title}{company}".encode()).hexdigest()[:12]

            return JobListing(
                portal="wellfound",
                job_id=f"wf_{job_id}",
                title=title,
                company=company,
                location=location,
                salary_range=salary,
                listing_url=href,
                apply_url=href,
            )
        except Exception as e:
            logger.debug(f"Error parsing Wellfound card: {e}")
            return None
