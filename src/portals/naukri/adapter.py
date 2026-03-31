"""
Naukri.com Portal Adapter
India's largest job portal - handles job search and application.
"""

import asyncio
import re
import logging
import hashlib
from typing import Optional
from datetime import datetime

from src.portals.base import BasePortalAdapter, JobListing, ApplicationResult

logger = logging.getLogger("portals.naukri")


class NaukriAdapter(BasePortalAdapter):
    """Naukri.com-specific job search and application automation."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.portal_name = "naukri"

    async def check_login_status(self) -> bool:
        """Check if logged into Naukri."""
        await self.browser.goto("https://www.naukri.com/mnjuser/homepage")
        await asyncio.sleep(3)
        url = await self.browser.get_current_url()

        if "naukri.com/nlogin" in url or "login" in url.lower():
            return False

        # Check for logged-in indicators
        return await self.browser.element_exists('.nI-gNb-drawer__icon') or \
               await self.browser.element_exists('[data-gaid="header-profile"]') or \
               await self.browser.element_exists('.view-profile-wrapper')

    async def login(self) -> bool:
        """Login to Naukri - uses saved session or prompts manual login."""
        await self.browser.goto("https://www.naukri.com/nlogin/login")
        await asyncio.sleep(2)

        if await self.check_login_status():
            return True

        # Try auto-login with credentials if available
        email = self.profile.personal.email
        if email:
            email_field = await self.browser.page.query_selector(
                'input[type="text"][placeholder*="Email"], #usernameField'
            )
            if email_field:
                await self.browser.type_text(
                    'input[type="text"][placeholder*="Email"], #usernameField',
                    email
                )
                logger.info("Entered email, waiting for manual password entry...")

        logger.warning(
            "Please complete Naukri login manually in the browser. "
            "Your session will be saved."
        )

        # Wait for login
        for _ in range(60):
            await asyncio.sleep(5)
            url = await self.browser.get_current_url()
            if "homepage" in url or "dashboard" in url:
                logger.info("Naukri login successful!")
                return True

        return False

    async def search_jobs(self, keywords: list[str], location: str = "") -> list[JobListing]:
        """Search for jobs on Naukri."""
        jobs = []
        keyword_str = "-".join(keywords).replace(" ", "-").lower()

        # Build Naukri search URL
        search_url = self._build_search_url(keyword_str, location)
        await self.browser.goto(search_url)
        await asyncio.sleep(3)

        # Scroll to load results
        for _ in range(3):
            await self.browser.scroll_down(600)
            await asyncio.sleep(1)

        # Extract job cards
        job_cards = await self.browser.page.query_selector_all(
            '.cust-job-tuple, .jobTuple, .srp-jobtuple-wrapper, article.jobTuple'
        )

        for card in job_cards[:20]:
            try:
                job = await self._extract_job_from_card(card)
                if job:
                    # Filter excluded keywords
                    exclude = self.profile.get_exclude_keywords()
                    title_lower = job.title.lower()
                    if not any(exc.lower() in title_lower for exc in exclude):
                        jobs.append(job)
            except Exception as e:
                logger.debug(f"Error extracting Naukri job card: {e}")

        logger.info(f"Naukri: Found {len(jobs)} jobs for '{keyword_str}' in '{location}'")
        return jobs

    async def apply_to_job(self, job: JobListing) -> ApplicationResult:
        """Apply to a Naukri job listing."""
        result = ApplicationResult(
            portal="naukri",
            job_id=job.job_id,
            job_title=job.title,
            company=job.company,
            timestamp=datetime.now().isoformat(),
        )

        try:
            # Navigate to job page
            await self.browser.goto(job.listing_url or job.apply_url)
            await asyncio.sleep(3)

            # Look for Apply button
            apply_btn = await self.browser.page.query_selector(
                'button:has-text("Apply"), '
                'button:has-text("Apply on company site"), '
                'a:has-text("Apply"), '
                '#apply-button, '
                '.apply-btn, '
                '[data-gaid="top-apply"]'
            )

            if not apply_btn:
                # Try the chat/quick apply button
                apply_btn = await self.browser.page.query_selector(
                    'button:has-text("Quick Apply"), '
                    '.chatbot-apply-btn'
                )

            if apply_btn:
                await apply_btn.click()
                await asyncio.sleep(3)

                # Check if it opened a new page or a modal
                pages = self.browser.context.pages
                if len(pages) > 1:
                    # External application
                    new_page = pages[-1]
                    await self.browser.switch_to_page(new_page)
                    await asyncio.sleep(2)

                    # Use adaptive form filler
                    job_context = {"title": job.title, "company": job.company}
                    form_result = await self.form_filler.handle_multi_step_form(
                        max_steps=8, job_context=job_context
                    )
                    result.success = form_result.get("success", False)
                    result.steps_completed = form_result.get("steps", 0)

                    await self.browser.close_extra_tabs()
                else:
                    # Modal/inline application
                    await self._handle_naukri_apply_flow(result, job)
            else:
                # Check if already applied
                already_applied = await self.browser.element_exists(
                    ':has-text("Already Applied"), :has-text("You have already applied")'
                )
                if already_applied:
                    result.error = "Already applied"
                else:
                    result.error = "No apply button found"

        except Exception as e:
            result.error = str(e)
            logger.error(f"Naukri apply error: {e}")

        result.screenshot_path = await self.browser.take_screenshot(
            f"naukri_{'success' if result.success else 'fail'}_{job.job_id}"
        )

        return result

    async def _handle_naukri_apply_flow(self, result: ApplicationResult, job: JobListing):
        """Handle Naukri's inline apply flow."""
        await asyncio.sleep(2)

        # Check for "Application Sent" confirmation
        page_text = await self.browser.get_visible_text()
        if re.search(r"application.*sent|successfully applied|applied successfully", page_text, re.IGNORECASE):
            result.success = True
            result.steps_completed = 1
            return

        # Handle chatbot-style apply
        chatbot = await self.browser.element_exists('.chatbot-container, .apply-chatbot')
        if chatbot:
            result = await self._handle_chatbot_apply(result, job)
            return

        # Handle traditional form
        job_context = {"title": job.title, "company": job.company}
        fill_report = await self.form_filler.fill_current_page(job_context)

        # Try to submit
        submitted = await self.form_filler.submit_form()
        if submitted:
            await asyncio.sleep(3)
            page_text = await self.browser.get_visible_text()
            if re.search(r"application.*sent|successfully|submitted", page_text, re.IGNORECASE):
                result.success = True
                result.steps_completed = 1

    async def _handle_chatbot_apply(self, result: ApplicationResult, job: JobListing) -> ApplicationResult:
        """Handle Naukri's chatbot-style application."""
        max_steps = 10

        for step in range(max_steps):
            await asyncio.sleep(2)

            # Get current question in chatbot
            questions = await self.browser.page.query_selector_all(
                '.chatbot-question, .chatbot-message:last-child'
            )

            if questions:
                last_q = questions[-1]
                q_text = await last_q.text_content()
                q_text = (q_text or "").strip()

                if q_text:
                    # Get answer from AI
                    profile_data = self.profile.to_flat_dict()
                    answer = await self.ai.generate_answer(
                        q_text,
                        f"Applying for {job.title} at {job.company}",
                        profile_data,
                        max_chars=200,
                    )

                    # Type answer
                    input_field = await self.browser.page.query_selector(
                        '.chatbot-input, input[type="text"]:last-of-type, textarea:last-of-type'
                    )
                    if input_field:
                        selector = '.chatbot-input, input[type="text"]:last-of-type'
                        await self.browser.type_text(selector, answer)
                        await self.browser.press_key("Enter")

            # Check for completion
            page_text = await self.browser.get_visible_text()
            if re.search(r"application.*sent|successfully|submitted|thank you", page_text, re.IGNORECASE):
                result.success = True
                result.steps_completed = step + 1
                return result

        return result

    async def update_naukri_profile(self):
        """
        Update Naukri profile to keep it active and visible to recruiters.
        Naukri ranks recently updated profiles higher.
        """
        await self.browser.goto("https://www.naukri.com/mnjuser/profile")
        await asyncio.sleep(3)

        # Just update the resume (this refreshes the profile)
        resume_path = self.profile.get_resume_path()
        if resume_path and resume_path.exists():
            upload_btn = await self.browser.page.query_selector(
                'input[type="file"], #attachCV, .upload-resume'
            )
            if upload_btn:
                await self.browser.upload_file('input[type="file"]', str(resume_path))
                logger.info("Naukri profile refreshed with resume upload")
                await asyncio.sleep(3)

    def _build_search_url(self, keywords: str, location: str) -> str:
        """Build Naukri search URL."""
        import urllib.parse

        # Naukri URL format: /keyword-jobs-in-location
        base = f"https://www.naukri.com/{keywords}-jobs"
        if location:
            loc_slug = location.lower().replace(" ", "-")
            base += f"-in-{loc_slug}"

        params = {
            "k": keywords.replace("-", " "),
            "experience": str(self.profile.professional.years_of_experience),
        }

        # Add salary filter
        min_salary = self.profile.job_search.get("min_salary", 0)
        if min_salary:
            # Naukri uses lakhs
            params["nignbelow_salary"] = str(min_salary // 100000)

        query = urllib.parse.urlencode(params)
        return f"{base}?{query}"

    async def _extract_job_from_card(self, card) -> Optional[JobListing]:
        """Extract job details from a Naukri job card."""
        try:
            title_el = await card.query_selector('.title, .jobTuple-title, a.title')
            company_el = await card.query_selector('.comp-name, .subTitle, .company-name')
            location_el = await card.query_selector('.loc, .locWdth, .location')
            salary_el = await card.query_selector('.sal, .salary')
            exp_el = await card.query_selector('.exp, .experience')
            link_el = await card.query_selector('a[href*="job-listings"], a.title')

            title = (await title_el.text_content()).strip() if title_el else ""
            company = (await company_el.text_content()).strip() if company_el else ""
            location = (await location_el.text_content()).strip() if location_el else ""
            salary = (await salary_el.text_content()).strip() if salary_el else ""
            experience = (await exp_el.text_content()).strip() if exp_el else ""
            href = (await link_el.get_attribute("href")) if link_el else ""

            if not title:
                return None

            job_id = hashlib.md5(f"{title}{company}".encode()).hexdigest()[:12]

            return JobListing(
                portal="naukri",
                job_id=f"nk_{job_id}",
                title=title,
                company=company,
                location=location,
                salary_range=salary,
                experience_required=experience,
                listing_url=href if href and href.startswith("http") else f"https://www.naukri.com{href}" if href else "",
                apply_url=href if href else "",
            )

        except Exception as e:
            logger.debug(f"Error parsing Naukri job card: {e}")
            return None
