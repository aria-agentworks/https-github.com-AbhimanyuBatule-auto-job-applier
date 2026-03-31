"""
Cookie Manager - Export/Import browser cookies for headless CI/CD runs.

Problem: Playwright persistent context stores sessions in a browser profile
directory, which is huge and can't easily be stored as a GitHub Secret.

Solution: Export login cookies as a compact JSON, store as a GitHub Secret,
and re-inject them at runtime. This keeps portal sessions alive in CI.
"""

import json
import logging
from pathlib import Path

from src.core.config import PROJECT_ROOT

logger = logging.getLogger("utils.cookies")

COOKIES_PATH = PROJECT_ROOT / "data" / "cookies.json"


async def export_cookies(context) -> str:
    """
    Export all cookies from a Playwright BrowserContext to JSON.
    Run this after manual login to capture session cookies.
    
    Returns the JSON string (also saves to data/cookies.json).
    """
    cookies = await context.cookies()
    
    # Filter out unnecessary cookies to keep the secret small
    essential_cookies = []
    # Domains we care about
    keep_domains = [
        "linkedin.com", "www.linkedin.com",
        "naukri.com", "www.naukri.com", "login.naukri.com",
        "wellfound.com", "www.wellfound.com",
        "instahyre.com", "www.instahyre.com",
        "hirist.tech", "www.hirist.tech",
    ]
    
    for cookie in cookies:
        domain = cookie.get("domain", "")
        # Keep cookies from job portals
        if any(d in domain for d in keep_domains):
            essential_cookies.append({
                "name": cookie["name"],
                "value": cookie["value"],
                "domain": cookie["domain"],
                "path": cookie.get("path", "/"),
                "expires": cookie.get("expires", -1),
                "httpOnly": cookie.get("httpOnly", False),
                "secure": cookie.get("secure", False),
                "sameSite": cookie.get("sameSite", "Lax"),
            })
    
    # Save to file
    COOKIES_PATH.parent.mkdir(parents=True, exist_ok=True)
    cookies_json = json.dumps(essential_cookies, indent=2)
    COOKIES_PATH.write_text(cookies_json, encoding="utf-8")
    
    logger.info(f"Exported {len(essential_cookies)} cookies to {COOKIES_PATH}")
    logger.info(f"Cookie JSON size: {len(cookies_json)} bytes")
    
    return cookies_json


async def import_cookies(context) -> int:
    """
    Import cookies from JSON file into a Playwright BrowserContext.
    Call this before navigating to portals in CI/CD environments.
    
    Returns the number of cookies imported.
    """
    if not COOKIES_PATH.exists():
        logger.warning(f"No cookies file found at {COOKIES_PATH}")
        return 0
    
    try:
        cookies_json = COOKIES_PATH.read_text(encoding="utf-8")
        cookies = json.loads(cookies_json)
        
        if not cookies:
            logger.warning("Cookies file is empty")
            return 0
        
        # Validate and clean cookies before importing
        valid_cookies = []
        for cookie in cookies:
            # Playwright requires at least name, value, and domain or url
            if cookie.get("name") and cookie.get("value") and cookie.get("domain"):
                # Remove expired cookies (expires = epoch seconds, -1 = session)
                expires = cookie.get("expires", -1)
                if expires == -1 or expires > 0:
                    valid_cookies.append(cookie)
        
        if valid_cookies:
            await context.add_cookies(valid_cookies)
            logger.info(f"Imported {len(valid_cookies)} cookies from {COOKIES_PATH}")
        else:
            logger.warning("No valid cookies to import")
        
        return len(valid_cookies)
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid cookies JSON: {e}")
        return 0
    except Exception as e:
        logger.error(f"Cookie import error: {e}")
        return 0


async def refresh_cookies(context) -> str:
    """
    Re-export cookies after a run (sessions may have been refreshed).
    Call this at the end of every run to keep cookies fresh.
    """
    return await export_cookies(context)


def get_cookies_for_secret() -> str:
    """
    Read and return cookies JSON string, suitable for GitHub Secrets.
    Prints instructions for the user.
    """
    if not COOKIES_PATH.exists():
        return ""
    
    cookies_json = COOKIES_PATH.read_text(encoding="utf-8")
    
    print("\n" + "=" * 60)
    print("COOKIE EXPORT FOR GITHUB SECRETS")
    print("=" * 60)
    print(f"\nCookies file: {COOKIES_PATH}")
    print(f"Size: {len(cookies_json)} bytes")
    print(f"Cookies count: {len(json.loads(cookies_json))}")
    print("\nTo set as GitHub Secret:")
    print("  1. Go to your repo → Settings → Secrets and Variables → Actions")
    print("  2. Add new secret: BROWSER_COOKIES")
    print("  3. Paste the entire contents of data/cookies.json")
    print("\nOr use GitHub CLI:")
    print(f'  gh secret set BROWSER_COOKIES < {COOKIES_PATH}')
    print("=" * 60 + "\n")
    
    return cookies_json
