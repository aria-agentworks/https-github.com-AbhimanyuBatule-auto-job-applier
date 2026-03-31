"""
LinkedIn Portal Adapter
Handles job search and application on LinkedIn.
Supports both Easy Apply and external applications.
"""

import asyncio
import re
import logging
import hashlib
from typing import Optional
from datetime import datetime

from src.portals.base import BasePortalAdapter, JobListing, ApplicationResult

logger = logging.getLogger("portals.linkedin")


class LinkedInAdapter(BasePortalAdapter):
    """LinkedIn-specific job search and application automation."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.portal_name = "linkedin"
        self._config = self._config or {}
        self._easy_apply_only = self._config.get("easy_apply_only", False)

    async def check_login_status(self) -> bool:
        """Check if logged into LinkedIn."""
        await self.browser.goto("https://www.linkedin.com/feed/")
        await asyncio.sleep(2)
        url = await self.browser.get_current_url()

        # If redirected to login page, not logged in
        if "login" in url or "authwall" in url or "checkpoint" in url:
            return False

        # Check for feed elements
        return await self.browser.element_exists('[data-testid="nav-search-bar"]') or \
               await self.browser.element_exists('.feed-identity-module') or \
               await self.browser.element_exists('.global-nav')

    async def login(self) -> bool:
        """
        LinkedIn login - uses saved browser session.
        First time: opens login page for manual intervention.
        """
        await self.browser.goto("https://www.linkedin.com/login")
        await asyncio.sleep(2)

        # Check if already logged in via saved session
        if await self.check_login_status():
            return True

        # If not logged in, we need manual intervention for first time
        logger.warning(
            "LinkedIn requires manual login for the first time. "
            "Please log in manually in the browser window. "
            "Your session will be saved for future runs."
        )

        # Wait for user to login (check every 5 seconds for up to 5 minutes)
        for _ in range(60):
            await asyncio.sleep(5)
            url = await self.browser.get_current_url()
            if "feed" in url or "mynetwork" in url:
                logger.info("LinkedIn login successful!")
                return True

        logger.error("LinkedIn login timed out")
        return False

    async def search_jobs(self, keywords: list[str], location: str = "") -> list[JobListing]:
        """Search for jobs on LinkedIn."""
        jobs = []
        keyword_str = " ".join(keywords)

        # Build search URL
        search_url = self._build_search_url(keyword_str, location)
        await self.browser.goto(search_url)
        await asyncio.sleep(3)
        await self.browser.wait_for_page_load()

        # Scroll to load more results
        for _ in range(3):
            await self.browser.scroll_down(800)
            await asyncio.sleep(1)

        # Extract job cards
        job_cards = await self.browser.page.query_selector_all('.job-card-container, .jobs-search-results__list-item, [data-job-id]')

        for card in job_cards[:20]:  # Limit to 20 results
            try:
                job = await self._extract_job_from_card(card)
                if job:
                    # Filter out excluded keywords
                    exclude = self.profile.get_exclude_keywords()
                    title_lower = job.title.lower()
                    if not any(exc.lower() in title_lower for exc in exclude):
                        jobs.append(job)
            except Exception as e:
                logger.debug(f"Error extracting job card: {e}")

        logger.info(f"LinkedIn: Found {len(jobs)} jobs for '{keyword_str}' in '{location}'")
        return jobs

    async def apply_to_job(self, job: JobListing) -> ApplicationResult:
        """Apply to a LinkedIn job listing."""
        result = ApplicationResult(
            portal="linkedin",
            job_id=job.job_id,
            job_title=job.title,
            company=job.company,
            timestamp=datetime.now().isoformat(),
        )

        try:
            # Navigate to job listing
            listing_url = job.listing_url or job.apply_url
            if not listing_url:
                result.error = "No listing URL"
                return result

            await self.browser.goto(listing_url)
            await asyncio.sleep(2)

            # Check for Easy Apply button
            easy_apply_btn = await self.browser.page.query_selector(
                'button.jobs-apply-button, '
                'button:has-text("Easy Apply"), '
                '[data-control-name="jobdetails_topcard_inapply"]'
            )

            if easy_apply_btn:
                result = await self._do_easy_apply(job, result)
            elif not self._easy_apply_only:
                result = await self._do_external_apply(job, result)
            else:
                result.error = "Not Easy Apply and easy_apply_only is set"

        except Exception as e:
            result.error = str(e)
            logger.error(f"LinkedIn apply error: {e}")

        # Take screenshot
        result.screenshot_path = await self.browser.take_screenshot(
            f"linkedin_{'success' if result.success else 'fail'}_{job.job_id}"
        )

        return result

    async def _do_easy_apply(self, job: JobListing, result: ApplicationResult) -> ApplicationResult:
        """Handle LinkedIn Easy Apply flow."""
        logger.info(f"Starting Easy Apply for: {job.title}")

        # Click Easy Apply button
        clicked = await self.browser.click(
            'button.jobs-apply-button, button:has-text("Easy Apply")'
        )
        if not clicked:
            result.error = "Could not click Easy Apply button"
            return result

        await asyncio.sleep(2)

        # Handle the multi-step Easy Apply modal
        max_steps = 8
        for step in range(max_steps):
            logger.info(f"Easy Apply step {step + 1}")
            await asyncio.sleep(1)

            # Check for modal
            modal = await self.browser.element_exists('.jobs-easy-apply-modal, .artdeco-modal')
            if not modal:
                # Check if we're done
                success_text = await self.browser.get_visible_text()
                if re.search(r"application.*sent|successfully applied", success_text, re.IGNORECASE):
                    result.success = True
                    result.steps_completed = step + 1
                    return result
                break

            # Fill form fields on current step
            job_context = {"title": job.title, "company": job.company}
            fill_report = await self.form_filler.fill_current_page(job_context)
            result.steps_completed = step + 1

            # Handle resume upload specifically in Easy Apply
            await self._handle_resume_upload()

            # Look for Next/Review/Submit button
            next_btn = await self.browser.page.query_selector(
                'button[aria-label*="next"], '
                'button[aria-label*="Review"], '
                'button[aria-label*="Submit"], '
                'button:has-text("Next"), '
                'button:has-text("Review"), '
                'button:has-text("Submit application")'
            )

            if next_btn:
                btn_text = await next_btn.text_content()
                btn_text = (btn_text or "").strip().lower()

                if "submit" in btn_text:
                    await next_btn.click()
                    await asyncio.sleep(3)
                    result.success = True
                    logger.info("Application submitted!")
                    return result
                else:
                    await next_btn.click()
                    await asyncio.sleep(2)
            else:
                # Try dismiss button if stuck
                dismiss = await self.browser.page.query_selector(
                    'button[aria-label="Dismiss"], button:has-text("Dismiss")'
                )
                if dismiss:
                    await dismiss.click()
                break

        # Check final state
        page_text = await self.browser.get_visible_text()
        if re.search(r"application.*sent|successfully", page_text, re.IGNORECASE):
            result.success = True

        return result

    async def _do_external_apply(self, job: JobListing, result: ApplicationResult) -> ApplicationResult:
        """Handle external application (redirects to company site)."""
        logger.info(f"External apply for: {job.title}")

        # Click Apply button
        apply_btn = await self.browser.page.query_selector(
            'a:has-text("Apply"), button:has-text("Apply on company site"), '
            'a.jobs-apply-button'
        )
        if apply_btn:
            await apply_btn.click()
            await asyncio.sleep(3)

            # Switch to new tab if opened
            pages = self.browser.context.pages
            if len(pages) > 1:
                new_page = pages[-1]
                await self.browser.switch_to_page(new_page)

            # Use adaptive form filler on the external page
            job_context = {"title": job.title, "company": job.company}
            form_result = await self.form_filler.handle_multi_step_form(
                max_steps=8, job_context=job_context
            )
            result.success = form_result.get("success", False)
            result.steps_completed = form_result.get("steps", 0)

            # Close extra tabs
            await self.browser.close_extra_tabs()
        else:
            result.error = "No apply button found"

        return result

    async def _handle_resume_upload(self):
        """Handle resume upload in Easy Apply modal."""
        upload_btn = await self.browser.page.query_selector(
            'input[type="file"], '
            '[data-test-file-input-upload], '
            'label:has-text("Upload resume")'
        )
        if upload_btn:
            resume = self.profile.get_resume_path()
            if resume and resume.exists():
                await self.browser.upload_file('input[type="file"]', str(resume))
                logger.info("Resume uploaded in Easy Apply")

    def _build_search_url(self, keywords: str, location: str) -> str:
        """Build LinkedIn job search URL with filters."""
        import urllib.parse

        params = {
            "keywords": keywords,
            "location": location,
            "f_TPR": "r604800",  # Past week
            "sortBy": "DD",  # Most recent
        }

        # Add experience filter
        min_exp = self.profile.job_search.get("min_experience", 0)
        if min_exp <= 2:
            params["f_E"] = "2"  # Entry level
        elif min_exp <= 5:
            params["f_E"] = "3"  # Associate
        else:
            params["f_E"] = "4"  # Mid-Senior

        # Add work type filter
        work_types = self.profile.professional.preferred_work_type
        if "remote" in work_types:
            params["f_WT"] = "2"

        query = urllib.parse.urlencode(params)
        return f"https://www.linkedin.com/jobs/search/?{query}"

    async def _extract_job_from_card(self, card) -> Optional[JobListing]:
        """Extract job details from a LinkedIn job card element."""
        try:
            title_el = await card.query_selector('.job-card-list__title, .artdeco-entity-lockup__title, a[data-control-name="job_card_title"]')
            company_el = await card.query_selector('.job-card-container__primary-description, .artdeco-entity-lockup__subtitle')
            location_el = await card.query_selector('.job-card-container__metadata-item, .artdeco-entity-lockup__caption')
            link_el = await card.query_selector('a[href*="/jobs/view/"]')

            title = await title_el.text_content() if title_el else ""
            company = await company_el.text_content() if company_el else ""
            location = await location_el.text_content() if location_el else ""
            href = await link_el.get_attribute("href") if link_el else ""

            title = title.strip()
            company = company.strip()
            location = location.strip()

            if not title:
                return None

            # Extract job ID from URL
            job_id = ""
            if href:
                match = re.search(r'/jobs/view/(\d+)', href)
                if match:
                    job_id = match.group(1)
                if not href.startswith("http"):
                    href = f"https://www.linkedin.com{href}"

            if not job_id:
                job_id = hashlib.md5(f"{title}{company}{href}".encode()).hexdigest()[:12]

            # Check for Easy Apply badge
            easy_apply = await card.query_selector('[data-is-easy-apply], .job-card-container__easy-apply-text')

            return JobListing(
                portal="linkedin",
                job_id=f"li_{job_id}",
                title=title,
                company=company,
                location=location,
                listing_url=href,
                apply_url=href,
                easy_apply=easy_apply is not None,
            )

        except Exception as e:
            logger.debug(f"Error parsing LinkedIn job card: {e}")
            return None
