"""
AI Engine - The brain of the adaptive form filler.
Uses Google Gemini (free tier) or Ollama/Groq as fallback.

Key capabilities:
1. Analyze page HTML/screenshots to identify form fields
2. Map form fields to profile data
3. Generate context-aware answers for open-ended questions
4. Determine next actions on a page (click, scroll, navigate)
5. Evaluate if a job posting matches user criteria
"""

import asyncio
import json
import time
import logging
from typing import Optional
from pathlib import Path

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.core.config import config

logger = logging.getLogger("ai.engine")


class RateLimiter:
    """Simple token-bucket rate limiter for API calls."""

    def __init__(self, max_per_minute: int = 15, max_per_day: int = 1500):
        self.max_per_minute = max_per_minute
        self.max_per_day = max_per_day
        self._minute_timestamps: list[float] = []
        self._day_count = 0
        self._day_start = time.time()

    async def acquire(self):
        """Wait until a request slot is available."""
        now = time.time()

        # Reset daily counter
        if now - self._day_start > 86400:
            self._day_count = 0
            self._day_start = now

        if self._day_count >= self.max_per_day:
            logger.warning("Daily AI rate limit reached. Waiting until tomorrow.")
            raise RuntimeError("Daily AI rate limit exceeded")

        # Clean old minute timestamps
        self._minute_timestamps = [t for t in self._minute_timestamps if now - t < 60]

        while len(self._minute_timestamps) >= self.max_per_minute:
            wait_time = 60 - (now - self._minute_timestamps[0]) + 0.5
            logger.debug(f"Rate limit: waiting {wait_time:.1f}s")
            await asyncio.sleep(wait_time)
            now = time.time()
            self._minute_timestamps = [t for t in self._minute_timestamps if now - t < 60]

        self._minute_timestamps.append(now)
        self._day_count += 1


class AIEngine:
    """
    Adaptive AI engine that powers the form-filling intelligence.
    Designed to be provider-agnostic (Gemini, Ollama, Groq).
    """

    def __init__(self):
        self._provider = config.get("ai", "provider", default="gemini")
        self._model = None
        self._rate_limiter = RateLimiter(
            max_per_minute=config.get("ai", "gemini", "max_requests_per_minute", default=15),
            max_per_day=config.get("ai", "gemini", "max_requests_per_day", default=1500),
        )
        self._initialized = False

    async def initialize(self):
        """Initialize the AI provider."""
        if self._initialized:
            return

        if self._provider == "gemini":
            await self._init_gemini()
        elif self._provider == "ollama":
            await self._init_ollama()
        elif self._provider == "groq":
            await self._init_groq()
        else:
            raise ValueError(f"Unknown AI provider: {self._provider}")

        self._initialized = True
        logger.info(f"AI Engine initialized with provider: {self._provider}")

    async def _init_gemini(self):
        """Initialize Google Gemini."""
        import google.generativeai as genai

        api_key = config.get("ai", "gemini", "api_key")
        if not api_key:
            raise ValueError(
                "Gemini API key not set. Get one free at https://aistudio.google.com/app/apikey "
                "and set it in config/settings.yaml or GEMINI_API_KEY env var."
            )

        genai.configure(api_key=api_key)
        model_name = config.get("ai", "gemini", "model", default="gemini-2.0-flash")
        self._model = genai.GenerativeModel(
            model_name=model_name,
            generation_config={
                "temperature": config.get("ai", "gemini", "temperature", default=0.3),
                "top_p": 0.95,
                "max_output_tokens": 4096,
            },
        )
        logger.info(f"Gemini model loaded: {model_name}")

    async def _init_ollama(self):
        """Initialize Ollama (local)."""
        # Ollama uses HTTP API, no special init needed
        self._ollama_url = config.get("ai", "ollama", "base_url", default="http://localhost:11434")
        self._ollama_model = config.get("ai", "ollama", "model", default="llama3.1:8b")

    async def _init_groq(self):
        """Initialize Groq."""
        self._groq_api_key = config.get("ai", "groq", "api_key")
        self._groq_model = config.get("ai", "groq", "model", default="llama-3.1-70b-versatile")

    # ── Core AI Methods ──────────────────────────────────────────

    async def _call_ai(self, prompt: str, system_prompt: str = "", image_path: str = None) -> str:
        """
        Send a prompt to the AI provider and return the response.
        Handles rate limiting, retries with exponential backoff, and provider fallback.
        """
        await self.initialize()
        await self._rate_limiter.acquire()

        # Build ordered provider fallback chain
        providers = [self._provider]
        for p in ["gemini", "groq", "ollama"]:
            if p != self._provider:
                providers.append(p)

        last_error = None
        for provider in providers:
            try:
                return await self._call_with_retry(provider, prompt, system_prompt, image_path)
            except Exception as e:
                last_error = e
                if provider == self._provider:
                    logger.warning(f"Primary AI provider ({provider}) failed: {e}. Trying fallback...")
                else:
                    logger.warning(f"Fallback provider ({provider}) also failed: {e}")

        raise RuntimeError(f"All AI providers failed. Last error: {last_error}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    async def _call_with_retry(self, provider: str, prompt: str, system_prompt: str = "", image_path: str = None) -> str:
        """Call a specific provider with tenacity retry."""
        try:
            if provider == "gemini":
                if not self._model:
                    await self._init_gemini()
                return await self._call_gemini(prompt, system_prompt, image_path)
            elif provider == "ollama":
                if not hasattr(self, '_ollama_url'):
                    await self._init_ollama()
                return await self._call_ollama(prompt, system_prompt)
            elif provider == "groq":
                if not hasattr(self, '_groq_api_key'):
                    await self._init_groq()
                return await self._call_groq(prompt, system_prompt)
        except Exception as e:
            logger.error(f"AI call to {provider} failed (will retry): {e}")
            raise

    async def _call_gemini(self, prompt: str, system_prompt: str = "", image_path: str = None) -> str:
        """Call Gemini API."""
        import google.generativeai as genai

        parts = []

        if system_prompt:
            parts.append(f"[System Instructions]\n{system_prompt}\n\n")

        if image_path:
            img = Path(image_path)
            if img.exists():
                import PIL.Image
                image = PIL.Image.open(str(img))
                parts.append(image)

        parts.append(prompt)

        response = await asyncio.to_thread(
            self._model.generate_content, parts
        )
        return response.text

    async def _call_ollama(self, prompt: str, system_prompt: str = "") -> str:
        """Call Ollama local API."""
        import httpx

        payload = {
            "model": self._ollama_model,
            "prompt": prompt,
            "system": system_prompt,
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(f"{self._ollama_url}/api/generate", json=payload)
            resp.raise_for_status()
            return resp.json()["response"]

    async def _call_groq(self, prompt: str, system_prompt: str = "") -> str:
        """Call Groq API."""
        import httpx

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {self._groq_api_key}"},
                json={"model": self._groq_model, "messages": messages, "temperature": 0.3},
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]

    # ── High-Level Intelligence Methods ──────────────────────────

    async def analyze_page_for_forms(self, page_html: str, page_url: str) -> dict:
        """
        Analyze a page's HTML and identify all form fields.
        Returns structured data about what needs to be filled.
        """
        system_prompt = """You are an expert web form analyzer. Your job is to look at HTML and identify 
all form fields that need to be filled for a job application. Be thorough and precise.

Return a JSON object with this structure:
{
    "page_type": "login|job_listing|application_form|profile_update|confirmation|unknown",
    "form_fields": [
        {
            "field_id": "CSS selector or identifier",
            "field_type": "text|email|tel|select|radio|checkbox|textarea|file|date|number",
            "label": "Human-readable label",
            "placeholder": "Placeholder text if any",
            "required": true/false,
            "options": ["for select/radio/checkbox only"],
            "maps_to_profile": "profile field name that matches this (e.g., 'first_name', 'email', 'phone')",
            "suggested_value": "What to fill based on the field context"
        }
    ],
    "submit_button": "CSS selector for the submit/next button",
    "has_next_page": true/false,
    "has_captcha": true/false,
    "has_file_upload": true/false,
    "additional_notes": "Any important observations"
}

IMPORTANT: Only return valid JSON, nothing else."""

        prompt = f"""Analyze this job application page and identify all form fields:

URL: {page_url}

HTML (trimmed):
{page_html[:15000]}

Identify every input field, dropdown, checkbox, radio button, and textarea.
Map each to the most likely profile field (first_name, last_name, email, phone, 
current_title, years_of_experience, skills, education, etc.)."""

        response = await self._call_ai(prompt, system_prompt)
        return self._parse_json_response(response)

    async def analyze_screenshot_for_forms(self, screenshot_path: str, page_url: str) -> dict:
        """
        Analyze a page screenshot to identify form fields visually.
        Used as a fallback when HTML analysis isn't sufficient.
        """
        system_prompt = """You are an expert at analyzing screenshots of web pages, specifically job application forms.
Look at the screenshot and identify all visible form fields, buttons, and interactive elements.

Return a JSON object with:
{
    "page_type": "login|job_listing|application_form|profile_update|confirmation|unknown",
    "visible_fields": [
        {
            "label": "Field label text",
            "field_type": "text|email|select|radio|checkbox|textarea|file|date",
            "approximate_position": "top|middle|bottom of page",
            "maps_to_profile": "profile field name",
            "current_value": "Already filled value if visible",
            "needs_action": true/false
        }
    ],
    "visible_buttons": [
        {"text": "Button text", "type": "submit|next|cancel|other"}
    ],
    "page_state": "empty_form|partially_filled|error_state|success|blocked",
    "errors_visible": ["List of any error messages visible"],
    "notes": "Additional observations"
}

Return ONLY valid JSON."""

        prompt = f"Analyze this screenshot of a job application page at {page_url}. Identify all form fields and their states."

        response = await self._call_ai(prompt, system_prompt, image_path=screenshot_path)
        return self._parse_json_response(response)

    async def generate_answer(
        self, question: str, context: str, profile_data: dict, max_chars: int = 500
    ) -> str:
        """
        Generate a contextual answer for an application question.
        Uses profile data to craft personalized responses.
        """
        system_prompt = """You are a professional job applicant. Generate a concise, authentic, and compelling answer 
to the application question. Use the provided profile data to personalize the response.

Guidelines:
- Be professional but not robotic
- Highlight relevant experience and skills
- Keep within the character limit
- Never fabricate information not in the profile
- Sound natural and human-written"""

        prompt = f"""Generate an answer for this job application question:

QUESTION: {question}
CONTEXT: {context}
CHARACTER LIMIT: {max_chars}

APPLICANT PROFILE:
{json.dumps(profile_data, indent=2)}

Write a compelling answer that fits within {max_chars} characters."""

        response = await self._call_ai(prompt, system_prompt)
        # Trim to max chars
        return response.strip()[:max_chars]

    async def determine_next_action(self, page_html: str, page_url: str, goal: str) -> dict:
        """
        Given a page state and a goal, determine what action to take next.
        This is the adaptive intelligence that figures out navigation.
        """
        system_prompt = """You are a web automation expert. Given a page's HTML and a goal, determine the SINGLE 
next best action to take. You must return a JSON object with EXACTLY one of these action types:

{
    "action": "click|type|select|scroll|wait|navigate|upload_file|submit|done|stuck",
    "selector": "CSS selector of the element to interact with",
    "value": "Value to type or select (if applicable)",
    "confidence": 0.0 to 1.0,
    "reasoning": "Brief explanation of why this action",
    "wait_after_ms": milliseconds to wait after action
}

IMPORTANT:
- Only return valid JSON
- Be precise with CSS selectors
- If stuck, explain why in reasoning
- If the goal is achieved, return action: "done"
"""

        prompt = f"""Current page URL: {page_url}
Current goal: {goal}

Page HTML (trimmed):
{page_html[:12000]}

What is the single next action to take to achieve the goal?"""

        response = await self._call_ai(prompt, system_prompt)
        return self._parse_json_response(response)

    async def evaluate_job_match(self, job_data: dict, profile_data: dict) -> dict:
        """
        Evaluate how well a job posting matches the user's profile.
        Returns a match score and analysis.
        """
        system_prompt = """You are a job matching expert. Evaluate how well a job posting matches the candidate's profile.
Return a JSON object:
{
    "match_score": 0-100,
    "should_apply": true/false,
    "matching_skills": ["skill1", "skill2"],
    "missing_skills": ["skill1"],
    "salary_match": true/false/unknown,
    "experience_match": true/false,
    "location_match": true/false,
    "red_flags": ["Any concerns"],
    "reasoning": "Brief explanation"
}

Only return valid JSON."""

        prompt = f"""Evaluate this job match:

JOB POSTING:
{json.dumps(job_data, indent=2)}

CANDIDATE PROFILE:
{json.dumps(profile_data, indent=2)}

Should this candidate apply? Provide a match score 0-100."""

        response = await self._call_ai(prompt, system_prompt)
        return self._parse_json_response(response)

    async def extract_job_details(self, page_html: str, page_url: str) -> dict:
        """
        Extract structured job details from a job listing page.
        """
        system_prompt = """Extract structured job details from this page. Return JSON:
{
    "title": "Job title",
    "company": "Company name",
    "location": "Location",
    "salary_range": "Salary if mentioned",
    "experience_required": "Years of experience",
    "job_type": "full-time|part-time|contract",
    "work_mode": "remote|hybrid|onsite",
    "description": "Brief description",
    "required_skills": ["skill1", "skill2"],
    "nice_to_have_skills": ["skill1"],
    "apply_url": "Direct apply URL if found",
    "posted_date": "When posted",
    "deadline": "Application deadline if any"
}

Only return valid JSON."""

        prompt = f"""Extract job details from this page:
URL: {page_url}

HTML (trimmed):
{page_html[:15000]}"""

        response = await self._call_ai(prompt, system_prompt)
        return self._parse_json_response(response)

    async def map_field_to_value(
        self, field_label: str, field_type: str, options: list, profile_data: dict
    ) -> str:
        """
        Given a form field, determine the best value from the profile.
        This is for fields that don't have an obvious mapping.
        """
        system_prompt = """You are mapping a form field to a profile value. Return ONLY the value to fill, nothing else.
If it's a select/dropdown, return the EXACT option text that best matches.
If no good match exists, return "SKIP" ."""

        options_str = f"\nAvailable options: {json.dumps(options)}" if options else ""

        prompt = f"""Form field: "{field_label}"
Field type: {field_type}{options_str}

Profile data:
{json.dumps(profile_data, indent=2)}

What value should be filled? Return ONLY the value."""

        response = await self._call_ai(prompt, system_prompt)
        return response.strip()

    # ── Utility Methods ──────────────────────────────────────────

    def _parse_json_response(self, response: str) -> dict:
        """Parse JSON from AI response, handling markdown code blocks."""
        text = response.strip()

        # Remove markdown code blocks
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first and last lines (```json and ```)
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON in the response
            import re
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass
            logger.warning(f"Could not parse AI response as JSON: {text[:200]}")
            return {"error": "Failed to parse AI response", "raw": text[:500]}
