"""
Instahyre Portal Adapter
AI-driven matching platform popular in Indian tech hiring.
"""

import asyncio
import re
import logging
import hashlib
from typing import Optional
from datetime import datetime

from src.portals.base import BasePortalAdapter, JobListing, ApplicationResult

logger = logging.getLogger("portals.instahyre")


class InstahyreAdapter(BasePortalAdapter):
    """Instahyre-specific job search and application automation."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.portal_name = "instahyre"

    async def check_login_status(self) -> bool:
        """Check if logged into Instahyre."""
        await self.browser.goto("https://www.instahyre.com/candidate/opportunities/")
        await asyncio.sleep(3)
        url = await self.browser.get_current_url()
        if "login" in url or "signup" in url:
            return False
        return await self.browser.element_exists('.navbar-profile') or \
               await self.browser.element_exists('[data-testid="profile-menu"]')

    async def login(self) -> bool:
        """Login to Instahyre."""
        await self.browser.goto("https://www.instahyre.com/login/")
        await asyncio.sleep(2)

        if await self.check_login_status():
            return True

        logger.warning("Please log in to Instahyre manually. Session will be saved.")

        for _ in range(60):
            await asyncio.sleep(5)
            if await self.check_login_status():
                logger.info("Instahyre login successful!")
                return True

        return False

    async def search_jobs(self, keywords: list[str], location: str = "") -> list[JobListing]:
        """Search for jobs on Instahyre (uses their matching system)."""
        jobs = []

        # Instahyre works on a matching/invitation model
        # Navigate to opportunities page
        await self.browser.goto("https://www.instahyre.com/candidate/opportunities/")
        await asyncio.sleep(3)

        # Scroll to load
        for _ in range(3):
            await self.browser.scroll_down(500)
            await asyncio.sleep(1)

        # Extract opportunity cards
        cards = await self.browser.page.query_selector_all(
            '.opportunity-card, .job-card, [data-testid="opportunity"]'
        )

        for card in cards[:15]:
            try:
                title_el = await card.query_selector('h3, .job-title, .opportunity-title')
                company_el = await card.query_selector('.company-name, .employer-name')
                location_el = await card.query_selector('.location, .job-location')
                link_el = await card.query_selector('a[href*="opportunity"], a[href*="job"]')

                title = (await title_el.text_content()).strip() if title_el else ""
                company = (await company_el.text_content()).strip() if company_el else ""
                location_text = (await location_el.text_content()).strip() if location_el else ""
                href = (await link_el.get_attribute("href")) if link_el else ""

                if title:
                    if href and not href.startswith("http"):
                        href = f"https://www.instahyre.com{href}"

                    job_id = hashlib.md5(f"{title}{company}{href}".encode()).hexdigest()[:12]
                    jobs.append(JobListing(
                        portal="instahyre",
                        job_id=f"ih_{job_id}",
                        title=title,
                        company=company,
                        location=location_text,
                        listing_url=href,
                        apply_url=href,
                    ))
            except Exception as e:
                logger.debug(f"Error extracting Instahyre card: {e}")

        logger.info(f"Instahyre: Found {len(jobs)} opportunities")
        return jobs

    async def apply_to_job(self, job: JobListing) -> ApplicationResult:
        """Apply/accept an Instahyre opportunity."""
        result = ApplicationResult(
            portal="instahyre",
            job_id=job.job_id,
            job_title=job.title,
            company=job.company,
            timestamp=datetime.now().isoformat(),
        )

        try:
            if job.listing_url:
                await self.browser.goto(job.listing_url)
                await asyncio.sleep(3)

            # Instahyre typically has an "Accept" or "Interested" button
            accept_btn = await self.browser.page.query_selector(
                'button:has-text("Accept"), '
                'button:has-text("Interested"), '
                'button:has-text("Apply"), '
                'button:has-text("I\'m Interested")'
            )

            if accept_btn:
                await accept_btn.click()
                await asyncio.sleep(3)

                # Handle any follow-up form
                job_context = {"title": job.title, "company": job.company}
                form_result = await self.form_filler.handle_multi_step_form(
                    max_steps=3, job_context=job_context
                )
                result.success = form_result.get("success", False)
                result.steps_completed = form_result.get("steps", 0)

                # Check success
                if not result.success:
                    page_text = await self.browser.get_visible_text()
                    if re.search(r"accepted|interest.*noted|applied", page_text, re.IGNORECASE):
                        result.success = True
            else:
                result.error = "No accept/apply button found"

        except Exception as e:
            result.error = str(e)

        result.screenshot_path = await self.browser.take_screenshot(
            f"instahyre_{'success' if result.success else 'fail'}_{job.job_id}"
        )
        return result
