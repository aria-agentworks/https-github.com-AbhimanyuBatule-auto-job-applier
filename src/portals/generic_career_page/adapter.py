"""
Generic Career Page Adapter
The most adaptive component - handles ANY company career page.
Uses AI to navigate, find application forms, and fill them.
This is the "Swiss Army knife" that makes the system truly universal.
"""

import asyncio
import re
import logging
import hashlib
from typing import Optional
from datetime import datetime

from src.portals.base import BasePortalAdapter, JobListing, ApplicationResult

logger = logging.getLogger("portals.generic")


class GenericCareerPageAdapter(BasePortalAdapter):
    """
    Handles any company career page using AI-driven navigation.
    This is where the real adaptive intelligence shines - no hardcoded selectors.
    The AI analyzes each page, determines what to do, and executes.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.portal_name = "generic_career_page"
        self._company_urls: list[str] = self._config.get("company_career_urls", [])

    async def check_login_status(self) -> bool:
        """Generic pages don't require login usually."""
        return True

    async def login(self) -> bool:
        """No login needed for generic career pages."""
        return True

    async def search_jobs(self, keywords: list[str], location: str = "") -> list[JobListing]:
        """
        Search for jobs on configured career pages.
        Can also handle direct job URLs.
        """
        jobs = []

        for career_url in self._company_urls:
            try:
                page_jobs = await self._search_career_page(career_url, keywords, location)
                jobs.extend(page_jobs)
            except Exception as e:
                logger.error(f"Error searching {career_url}: {e}")

        return jobs

    async def apply_to_job(self, job: JobListing) -> ApplicationResult:
        """Apply to a job on any career page using AI-driven navigation."""
        result = ApplicationResult(
            portal="generic",
            job_id=job.job_id,
            job_title=job.title,
            company=job.company,
            timestamp=datetime.now().isoformat(),
        )

        try:
            await self.browser.goto(job.apply_url or job.listing_url)
            await asyncio.sleep(3)

            # Use AI to navigate the application process
            job_context = {
                "title": job.title,
                "company": job.company,
                "url": job.apply_url,
            }

            result = await self._ai_driven_application(result, job_context)

        except Exception as e:
            result.error = str(e)
            logger.error(f"Generic career page apply error: {e}")

        result.screenshot_path = await self.browser.take_screenshot(
            f"generic_{'success' if result.success else 'fail'}_{job.job_id}"
        )
        return result

    async def apply_to_url(self, url: str, job_title: str = "", company: str = "") -> ApplicationResult:
        """
        Apply to a specific URL directly.
        This is the key method for applying to any career page URL.
        """
        result = ApplicationResult(
            portal="generic",
            job_id=hashlib.md5(url.encode()).hexdigest()[:12],
            job_title=job_title,
            company=company,
            timestamp=datetime.now().isoformat(),
        )

        try:
            await self.browser.goto(url)
            await asyncio.sleep(3)

            job_context = {"title": job_title, "company": company, "url": url}
            result = await self._ai_driven_application(result, job_context)

        except Exception as e:
            result.error = str(e)

        return result

    async def _ai_driven_application(
        self, result: ApplicationResult, job_context: dict, max_actions: int = 30
    ) -> ApplicationResult:
        """
        Use AI to navigate and fill an application on any page.
        This is the most adaptive part of the entire system.
        """
        goal = f"Apply for the {job_context.get('title', 'job')} position at {job_context.get('company', 'the company')}"

        for action_num in range(max_actions):
            current_url = await self.browser.get_current_url()
            page_html = await self.browser.get_page_html(clean=True)
            page_text = await self.browser.get_visible_text()

            # Check for success indicators
            if self._check_success(page_text):
                result.success = True
                result.steps_completed = action_num + 1
                logger.info(f"Application submitted successfully after {action_num + 1} actions!")
                return result

            # Check for error/blocked states
            if self._check_blocked(page_text):
                result.error = "Application blocked or requires CAPTCHA"
                return result

            # Step 1: Check if current page has a form
            form_fields = await self.browser.get_form_fields()
            visible_forms = [f for f in form_fields if f.get("visible")]

            if visible_forms:
                # There's a form - fill it
                logger.info(f"Action {action_num + 1}: Filling form with {len(visible_forms)} fields")
                fill_report = await self.form_filler.fill_current_page(job_context)
                result.steps_completed += 1

                # Try to submit/advance
                submitted = await self.form_filler.submit_form()
                if submitted:
                    await asyncio.sleep(3)
                    continue
                
            # Step 2: Ask AI what to do next
            logger.info(f"Action {action_num + 1}: Asking AI for next action")
            action = await self.ai.determine_next_action(page_html, current_url, goal)

            action_type = action.get("action", "stuck")
            selector = action.get("selector", "")
            value = action.get("value", "")
            confidence = action.get("confidence", 0)

            logger.info(f"AI action: {action_type} -> {selector} (confidence: {confidence})")

            if action_type == "done":
                result.success = True
                result.steps_completed = action_num + 1
                return result

            if action_type == "stuck":
                result.error = f"AI got stuck: {action.get('reasoning', 'unknown reason')}"
                return result

            if confidence < 0.3:
                logger.warning(f"Low confidence action ({confidence}), attempting anyway")

            # Execute the action
            success = await self._execute_action(action_type, selector, value)
            if not success:
                logger.warning(f"Action failed: {action_type} on {selector}")
                # Try taking screenshot for AI visual analysis
                screenshot = await self.browser.take_screenshot(f"action_fail_{action_num}")

            await asyncio.sleep(2)

        result.error = f"Max actions ({max_actions}) reached without completion"
        return result

    async def _execute_action(self, action_type: str, selector: str, value: str) -> bool:
        """Execute a single AI-determined action."""
        try:
            if action_type == "click":
                return await self.browser.click(selector)
            elif action_type == "type":
                return await self.browser.type_text(selector, value)
            elif action_type == "select":
                return await self.browser.select_option(selector, label=value)
            elif action_type == "scroll":
                await self.browser.scroll_down(500)
                return True
            elif action_type == "wait":
                await asyncio.sleep(3)
                return True
            elif action_type == "navigate":
                return await self.browser.goto(value or selector)
            elif action_type == "upload_file":
                resume = self.profile.get_resume_path()
                if resume and resume.exists():
                    return await self.browser.upload_file(selector, str(resume))
                return False
            elif action_type == "submit":
                return await self.form_filler.submit_form()
            else:
                logger.warning(f"Unknown action type: {action_type}")
                return False
        except Exception as e:
            logger.warning(f"Action execution error: {e}")
            return False

    def _check_success(self, page_text: str) -> bool:
        """Check if the page indicates successful application."""
        patterns = [
            r"application.*(submitted|received|confirmed|successful|sent)",
            r"thank.?you.*(apply|application|submitting|interest)",
            r"we.*(received|review).*(application|resume|cv)",
            r"successfully\s+applied",
            r"your\s+application\s+has\s+been",
            r"application\s+complete",
            r"we'll\s+be\s+in\s+touch",
            r"you('ve|\s+have)\s+(been|successfully)\s+(applied|submitted)",
        ]
        for pattern in patterns:
            if re.search(pattern, page_text, re.IGNORECASE):
                return True
        return False

    def _check_blocked(self, page_text: str) -> bool:
        """Check if the application is blocked."""
        patterns = [
            r"captcha|recaptcha|hcaptcha",
            r"verify.*(human|robot)",
            r"access.denied",
            r"too.many.requests",
            r"rate.limit",
        ]
        for pattern in patterns:
            if re.search(pattern, page_text, re.IGNORECASE):
                return True
        return False

    async def _search_career_page(
        self, career_url: str, keywords: list[str], location: str
    ) -> list[JobListing]:
        """Search a specific career page for matching jobs."""
        jobs = []

        await self.browser.goto(career_url)
        await asyncio.sleep(3)

        # Try to find search functionality
        search_input = await self.browser.page.query_selector(
            'input[type="search"], input[placeholder*="search"], '
            'input[placeholder*="Search"], input[name*="search"], '
            '#search, .search-input'
        )

        if search_input:
            keyword = keywords[0] if keywords else "SDET"
            selector = 'input[type="search"], input[placeholder*="search"], input[placeholder*="Search"]'
            await self.browser.type_text(selector, keyword)
            await self.browser.press_key("Enter")
            await asyncio.sleep(3)

        # Use AI to extract job listings from the page
        page_html = await self.browser.get_page_html(clean=True)
        page_url = await self.browser.get_current_url()

        # Try extracting with AI
        job_details = await self.ai.extract_job_details(page_html, page_url)

        if job_details and not job_details.get("error"):
            title = job_details.get("title", "")
            company = job_details.get("company", "")
            if title:
                job_id = hashlib.md5(f"{title}{company}{career_url}".encode()).hexdigest()[:12]
                jobs.append(JobListing(
                    portal="generic",
                    job_id=f"gn_{job_id}",
                    title=title,
                    company=company,
                    location=job_details.get("location", ""),
                    salary_range=job_details.get("salary_range", ""),
                    experience_required=job_details.get("experience_required", ""),
                    description=job_details.get("description", ""),
                    required_skills=job_details.get("required_skills", []),
                    listing_url=career_url,
                    apply_url=job_details.get("apply_url", career_url),
                ))

        return jobs
