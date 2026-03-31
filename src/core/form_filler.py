"""
Adaptive Form Filler - The crown jewel of this automation.

This module combines AI analysis + profile data + browser automation to:
1. Detect form fields on ANY page (no hardcoded selectors)
2. Map fields to profile data intelligently
3. Fill forms with human-like behavior
4. Handle multi-step application flows
5. Deal with custom questions, dropdowns, file uploads
6. Recover from errors and adapt to unexpected page states
"""

import asyncio
import json
import logging
import re
from typing import Optional

from src.core.browser import BrowserManager
from src.core.profile import ProfileManager
from src.ai.engine import AIEngine

logger = logging.getLogger("core.form_filler")


# ── Direct Field Mapping (fast, no AI needed) ──────────────────
# Maps common field patterns to profile fields
DIRECT_FIELD_MAP = {
    # Name fields
    r"first.?name": "first_name",
    r"last.?name": "last_name",
    r"full.?name|your.?name": "full_name",
    r"^name$": "full_name",

    # Contact
    r"e.?mail": "email",
    r"phone|mobile|cell|contact.?number": "phone",
    r"country.?code": "phone_country_code",

    # Location
    r"city|current.?city": "current_city",
    r"state|province": "current_state",
    r"country": "current_country",
    r"zip|postal|pin.?code": "zip_code",
    r"address": "address",

    # Professional
    r"current.?title|job.?title|designation": "current_title",
    r"current.?company|employer|organization": "current_company",
    r"experience|years?.?of?.?exp": "years_of_experience",
    r"current.?salary|current.?ctc|ctc": "current_salary",
    r"expected.?salary|expected.?ctc": "expected_salary",
    r"notice.?period": "notice_period_days",

    # Links
    r"linkedin": "linkedin_url",
    r"github": "github_url",
    r"portfolio|website|personal.?site": "portfolio_url",

    # Education
    r"degree|qualification": "degree",
    r"university|college|institution": "university",
    r"graduation|grad.?year": "graduation_year",
    r"gpa|cgpa|percentage": "gpa",
    r"field.?of.?study|major|specialization": "field_of_study",

    # Other
    r"skill": "primary_skills",
    r"cover.?letter": "_generate_cover_letter",
}


class AdaptiveFormFiller:
    """
    Fills any job application form using a combination of:
    1. Direct mapping (fast pattern matching for common fields)
    2. AI analysis (for complex/unusual fields)
    3. Profile data (single source of truth)
    """

    def __init__(self, browser: BrowserManager, profile: ProfileManager, ai: AIEngine):
        self.browser = browser
        self.profile = profile
        self.ai = ai
        self._profile_flat = profile.to_flat_dict()
        self._filled_fields: dict[str, str] = {}  # Track what we filled
        self._errors: list[str] = []

    async def fill_current_page(self, job_context: dict = None) -> dict:
        """
        Analyze and fill all form fields on the current page.
        Returns a report of what was filled, skipped, and any errors.
        """
        report = {
            "fields_filled": 0,
            "fields_skipped": 0,
            "fields_failed": 0,
            "errors": [],
            "used_ai": False,
            "details": [],
        }

        try:
            # Step 1: Extract form fields using JavaScript
            js_fields = await self.browser.get_form_fields()
            visible_fields = [f for f in js_fields if f.get("visible", True)]

            if not visible_fields:
                logger.info("No visible form fields found on page")
                report["details"].append("No visible form fields found")
                return report

            logger.info(f"Found {len(visible_fields)} visible form fields")

            # Step 2: Try direct mapping first (fast, no AI cost)
            unmapped_fields = []
            for field in visible_fields:
                mapped = self._try_direct_mapping(field)
                if mapped:
                    success = await self._fill_field(field, mapped)
                    if success:
                        report["fields_filled"] += 1
                        report["details"].append(f"✓ {field['label'] or field['name']}: {mapped[:50]}")
                    else:
                        report["fields_failed"] += 1
                        report["errors"].append(f"Failed to fill: {field['label'] or field['name']}")
                else:
                    unmapped_fields.append(field)

            # Step 3: Use AI for remaining unmapped fields
            if unmapped_fields:
                report["used_ai"] = True
                logger.info(f"Using AI to analyze {len(unmapped_fields)} unmapped fields")

                page_html = await self.browser.get_page_html(clean=True)
                page_url = await self.browser.get_current_url()

                ai_analysis = await self.ai.analyze_page_for_forms(page_html, page_url)

                if "form_fields" in ai_analysis:
                    for ai_field in ai_analysis["form_fields"]:
                        # Find matching unmapped field
                        matching_field = self._match_ai_field_to_js_field(ai_field, unmapped_fields)
                        if matching_field:
                            value = await self._get_ai_field_value(ai_field, job_context)
                            if value and value != "SKIP":
                                success = await self._fill_field(matching_field, value)
                                if success:
                                    report["fields_filled"] += 1
                                    label = ai_field.get("label", matching_field.get("name", "unknown"))
                                    report["details"].append(f"✓ [AI] {label}: {value[:50]}")
                                else:
                                    report["fields_failed"] += 1
                            else:
                                report["fields_skipped"] += 1
                        else:
                            report["fields_skipped"] += 1

            # Step 4: Handle file uploads (resume)
            await self._handle_file_uploads()

        except Exception as e:
            logger.error(f"Form filling error: {e}")
            report["errors"].append(str(e))

        logger.info(
            f"Form fill complete: {report['fields_filled']} filled, "
            f"{report['fields_skipped']} skipped, {report['fields_failed']} failed"
        )
        return report

    def _try_direct_mapping(self, field: dict) -> Optional[str]:
        """
        Try to map a field to a profile value using regex patterns.
        This is fast and doesn't need AI.
        """
        # Get all identifying info about the field
        identifiers = " ".join([
            field.get("label", ""),
            field.get("name", ""),
            field.get("id", ""),
            field.get("placeholder", ""),
        ]).lower().strip()

        if not identifiers:
            return None

        for pattern, profile_key in DIRECT_FIELD_MAP.items():
            if re.search(pattern, identifiers, re.IGNORECASE):
                # Special case: cover letter generation
                if profile_key == "_generate_cover_letter":
                    return self._generate_cover_letter_text()

                # Special case: dropdowns
                if field.get("type") == "select" and field.get("options"):
                    return self._match_dropdown_option(field["options"], profile_key)

                value = self._profile_flat.get(profile_key, "")
                if value:
                    return str(value)

        return None

    def _match_dropdown_option(self, options: list[dict], profile_key: str) -> Optional[str]:
        """Match dropdown options to profile data."""
        profile_value = str(self._profile_flat.get(profile_key, "")).lower()
        if not profile_value:
            return None

        # Try exact match first
        for opt in options:
            if opt.get("text", "").lower().strip() == profile_value:
                return opt.get("value") or opt.get("text")

        # Try partial/fuzzy match
        for opt in options:
            opt_text = opt.get("text", "").lower()
            if profile_value in opt_text or opt_text in profile_value:
                return opt.get("value") or opt.get("text")

        return None

    def _match_ai_field_to_js_field(self, ai_field: dict, js_fields: list[dict]) -> Optional[dict]:
        """Match an AI-identified field to a JS-extracted field."""
        ai_selector = ai_field.get("field_id", "")
        ai_label = ai_field.get("label", "").lower()

        for js_field in js_fields:
            # Match by selector
            if ai_selector and (
                ai_selector == js_field.get("selector") or
                ai_selector == f"#{js_field.get('id')}" or
                ai_selector == f"[name=\"{js_field.get('name')}\"]"
            ):
                return js_field

            # Match by label similarity
            js_label = (js_field.get("label", "") or js_field.get("name", "")).lower()
            if ai_label and js_label and (ai_label in js_label or js_label in ai_label):
                return js_field

        return None

    async def _get_ai_field_value(self, ai_field: dict, job_context: dict = None) -> Optional[str]:
        """Get the value for an AI-identified field."""
        # Check if AI already suggested a mapping
        maps_to = ai_field.get("maps_to_profile", "")
        if maps_to and maps_to in self._profile_flat:
            return str(self._profile_flat[maps_to])

        # Check if AI suggested a value
        suggested = ai_field.get("suggested_value", "")
        if suggested:
            return suggested

        # For complex fields, ask AI to generate an answer
        field_type = ai_field.get("field_type", "text")
        label = ai_field.get("label", "")
        options = ai_field.get("options", [])

        if field_type in ("textarea",) and label:
            # This is likely a question - generate an answer
            context = json.dumps(job_context) if job_context else ""
            return await self.ai.generate_answer(label, context, self._profile_flat)

        if field_type == "select" and options:
            return await self.ai.map_field_to_value(label, field_type, options, self._profile_flat)

        if label:
            return await self.ai.map_field_to_value(label, field_type, options, self._profile_flat)

        return None

    async def _fill_field(self, field: dict, value: str) -> bool:
        """Actually fill a field in the browser."""
        selector = field.get("selector", "")
        field_type = field.get("type", "text")

        if not selector:
            # Try to build a selector
            if field.get("id"):
                selector = f"#{field['id']}"
            elif field.get("name"):
                selector = f"[name=\"{field['name']}\"]"
            else:
                return False

        try:
            if field_type == "select":
                # For dropdowns
                success = await self.browser.select_option(selector, value=value)
                if not success:
                    success = await self.browser.select_option(selector, label=value)
                return success

            elif field_type in ("checkbox", "radio"):
                return await self.browser.check_checkbox(selector)

            elif field_type == "file":
                resume_path = self.profile.get_resume_path()
                if resume_path and resume_path.exists():
                    return await self.browser.upload_file(selector, str(resume_path))
                return False

            elif field_type == "textarea":
                return await self.browser.type_text(selector, value)

            else:
                # text, email, tel, number, date, url, etc.
                return await self.browser.type_text(selector, value)

        except Exception as e:
            logger.warning(f"Failed to fill field {selector}: {e}")
            return False

    async def _handle_file_uploads(self):
        """Handle resume/CV file upload fields."""
        # Check for common resume upload selectors
        upload_selectors = [
            'input[type="file"]',
            'input[accept*=".pdf"]',
            'input[accept*=".doc"]',
            '[data-testid*="resume"]',
            '[data-testid*="cv"]',
        ]

        resume_path = self.profile.get_resume_path()
        if not resume_path or not resume_path.exists():
            logger.warning("No resume file found for upload")
            return

        for selector in upload_selectors:
            if await self.browser.element_exists(selector):
                await self.browser.upload_file(selector, str(resume_path))
                logger.info(f"Resume uploaded via: {selector}")
                break

    def _generate_cover_letter_text(self) -> str:
        """Generate a cover letter using the template."""
        return self.profile.generate_cover_letter(
            company="the company",
            role=self.profile.professional.current_title,
        )

    async def submit_form(self) -> bool:
        """
        Find and click the submit button.
        Uses multiple strategies to find the correct button.
        """
        submit_selectors = [
            'button[type="submit"]',
            'input[type="submit"]',
            'button:has-text("Submit")',
            'button:has-text("Apply")',
            'button:has-text("Send")',
            'button:has-text("Next")',
            'button:has-text("Continue")',
            'a:has-text("Submit Application")',
            'a:has-text("Apply Now")',
            '[data-testid*="submit"]',
            '[data-testid*="apply"]',
        ]

        for selector in submit_selectors:
            try:
                if await self.browser.element_exists(selector):
                    await self.browser.click(selector)
                    logger.info(f"Form submitted via: {selector}")
                    await self.browser.wait_for_page_load()
                    return True
            except Exception:
                continue

        # Fallback: Ask AI to find the submit button
        logger.info("Standard submit selectors failed, asking AI...")
        html = await self.browser.get_page_html(clean=True)
        url = await self.browser.get_current_url()
        action = await self.ai.determine_next_action(html, url, "Submit the application form")

        if action.get("action") == "click" and action.get("selector"):
            return await self.browser.click(action["selector"])

        return False

    async def handle_multi_step_form(self, max_steps: int = 10, job_context: dict = None) -> dict:
        """
        Handle multi-step application forms.
        Fills each page and clicks Next until completion.
        """
        all_reports = []

        for step in range(max_steps):
            logger.info(f"Processing application step {step + 1}")

            # Fill current page
            report = await self.fill_current_page(job_context)
            all_reports.append(report)

            # Take screenshot
            await self.browser.take_screenshot(f"step_{step + 1}")

            # Check if we're on a confirmation/success page
            page_text = await self.browser.get_visible_text()
            success_patterns = [
                r"application.*(submitted|received|confirmed|successful)",
                r"thank.?you.*(apply|application|submitting)",
                r"we.*(received|review).*(application|resume)",
                r"successfully applied",
            ]
            for pattern in success_patterns:
                if re.search(pattern, page_text, re.IGNORECASE):
                    logger.info("Application submission confirmed!")
                    return {
                        "success": True,
                        "steps": step + 1,
                        "reports": all_reports,
                    }

            # Try to advance to next step
            next_clicked = await self._click_next_or_submit()
            if not next_clicked:
                logger.info("No next/submit button found - may be done or stuck")
                break

            await self.browser.wait_for_page_load()
            await asyncio.sleep(1)

            # Check if URL changed (indicates page transition)
            current_url = await self.browser.get_current_url()
            logger.debug(f"After step {step + 1}, URL: {current_url}")

        return {
            "success": False,
            "steps": len(all_reports),
            "reports": all_reports,
        }

    async def _click_next_or_submit(self) -> bool:
        """Click Next, Continue, or Submit button."""
        # Order matters: try Submit first on last pages, Next/Continue for intermediate
        selectors = [
            'button:has-text("Submit Application")',
            'button:has-text("Submit")',
            'button:has-text("Apply")',
            'button:has-text("Next")',
            'button:has-text("Continue")',
            'button:has-text("Save and Continue")',
            'button:has-text("Review")',
            'button[type="submit"]',
            'input[type="submit"]',
            'a:has-text("Next")',
            'a:has-text("Continue")',
        ]

        for selector in selectors:
            try:
                if await self.browser.element_exists(selector):
                    await self.browser.click(selector)
                    return True
            except Exception:
                continue

        return False
