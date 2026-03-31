# Auto Job Applier

**Adaptive AI-Powered Job Application Bot** — Apply to 10+ jobs daily, completely hands-free.

Uses Google Gemini AI (free tier) + Playwright browser automation to intelligently navigate any job portal or company career page, fill forms adaptively, and submit applications while you sleep.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Module Breakdown](#module-breakdown)
3. [Data Flow](#data-flow)
4. [Prerequisites](#prerequisites)
5. [Quick Start](#quick-start)
6. [Configuration Guide](#configuration-guide)
7. [CLI Commands](#cli-commands)
8. [Results & Output Locations](#results--output-locations)
9. [GitHub Actions (CI/CD)](#github-actions-cicd)
10. [Google Sheets Dashboard](#google-sheets-dashboard-optional)
11. [How the AI Form Filler Works](#how-the-ai-form-filler-works)
12. [Adding New Portals](#adding-new-portals)
13. [Testing](#testing)
14. [Project Structure](#project-structure)
15. [Troubleshooting](#troubleshooting)

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                         CLI  (click + rich)                          │
│                  main.py  →  src/cli.py  →  commands                 │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │                    ORCHESTRATOR  (src/core/orchestrator.py)     │  │
│  │          Coordinates: discover → score → apply → track         │  │
│  │          Zero-failure design for headless CI/CD runs           │  │
│  └──────────┬──────────┬──────────┬──────────┬───────────────────┘  │
│             │          │          │          │                        │
│   ┌─────────▼──┐ ┌────▼─────┐ ┌─▼────────┐ │                       │
│   │ AI ENGINE  │ │ BROWSER  │ │  FORM    │ │                        │
│   │ (Gemini/   │ │ ENGINE   │ │  FILLER  │ │                        │
│   │  Groq/     │ │(Playwright│ │(Adaptive)│ │                        │
│   │  Ollama)   │ │ Stealth) │ │ 3-layer  │ │                        │
│   └────────────┘ └──────────┘ └──────────┘ │                        │
│                                             │                        │
│   ┌─────────────────────────────────────────▼────────────────────┐  │
│   │                    PORTAL ADAPTERS                            │  │
│   │  ┌──────────┐ ┌────────┐ ┌───────────┐ ┌───────────┐        │  │
│   │  │ LinkedIn │ │ Naukri │ │ Wellfound │ │ Instahyre │        │  │
│   │  └──────────┘ └────────┘ └───────────┘ └───────────┘        │  │
│   │  ┌──────────────────────────────────────────────────┐        │  │
│   │  │  GENERIC CAREER PAGE  (AI-driven, works on ANY   │        │  │
│   │  │  company website — no selectors needed)           │        │  │
│   │  └──────────────────────────────────────────────────┘        │  │
│   └──────────────────────────────────────────────────────────────┘  │
│                                                                      │
│   ┌───────────────┐ ┌──────────────┐ ┌────────────────────────┐     │
│   │ TRACKER       │ │ SCHEDULER    │ │ NOTIFICATIONS          │     │
│   │ SQLite + CSV  │ │ APScheduler  │ │ Desktop / Telegram     │     │
│   │ + Sheets sync │ │ + GHA cron   │ │ / Email                │     │
│   └───────────────┘ └──────────────┘ └────────────────────────┘     │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Module Breakdown

### `src/core/` — Core Engine

| File | Responsibility |
|------|---------------|
| `config.py` | Singleton config loader — reads `settings.yaml` + `profile.yaml`, applies env-var overrides, validates at startup |
| `profile.py` | Manages your personal details, skills, work history, resume data |
| `browser.py` | Playwright browser with stealth mode — persistent sessions, anti-detection, proxy support, human-like delays |
| `form_filler.py` | **The brain** — 3-layer adaptive form filler (regex → AI analysis → AI navigation) |
| `orchestrator.py` | Pipeline runner — initializes all components, loops over portals, handles errors, produces reports |

### `src/ai/` — AI Integration

| File | Responsibility |
|------|---------------|
| `engine.py` | Multi-provider AI engine with automatic fallback chain: Gemini → Groq → Ollama. Rate-limited, retry-on-transient-errors |

### `src/portals/` — Job Portal Adapters

| File | Responsibility |
|------|---------------|
| `base.py` | Abstract base class (`BasePortalAdapter`) + data classes (`JobListing`, `ApplicationResult`) |
| `linkedin/adapter.py` | LinkedIn automation — Easy Apply + external apply, pagination, job search |
| `naukri/adapter.py` | Naukri.com — Quick Apply, chatbot-based apply, profile refresh |
| `wellfound/adapter.py` | Wellfound (AngelList) — startup jobs with salary transparency |
| `instahyre/adapter.py` | Instahyre — AI-matched opportunities, accept invites |
| `generic_career_page/adapter.py` | **Universal adapter** — works on ANY website using AI to navigate and fill forms |

### `src/tracker/` — Application Tracking

| File | Responsibility |
|------|---------------|
| `database.py` | SQLite database — stores every application, prevents duplicates, provides stats queries |
| `sheets.py` | `GoogleSheetsReporter` (live dashboard sync) + `CSVExporter` (offline export) |

### `src/scheduler/` — Scheduling

| File | Responsibility |
|------|---------------|
| `scheduler.py` | APScheduler integration — runs the pipeline at configured times locally |

### `src/utils/` — Utilities

| File | Responsibility |
|------|---------------|
| `logging_config.py` | Structured logging to console + rotating file |
| `notifications.py` | Desktop (plyer), Telegram, and email notifications |
| `cookies.py` | Cookie export/import for headless CI/CD runs |

### `src/cli.py` — CLI Interface

Rich, interactive command-line interface built with Click + Rich. All commands documented below.

---

## Data Flow

```
1. STARTUP
   main.py → cli.py → Orchestrator.__init__()
   ↓
   Config loads settings.yaml + profile.yaml
   ↓
   Browser launches (headless or headed)
   ↓
   AI engine initializes (validates API key)

2. PER-PORTAL LOOP
   For each enabled portal:
   ├── Check login status (restore cookies if needed)
   ├── Search for jobs matching your keywords + location
   ├── For each job listing:
   │   ├── Check DB: already applied? → skip
   │   ├── Check blacklist: blocked company? → skip
   │   ├── AI scores job relevance (0-100)
   │   ├── If score ≥ threshold → proceed
   │   ├── Navigate to application page
   │   ├── Form Filler handles all fields:
   │   │   ├── Layer 1: regex patterns (fast, no AI cost)
   │   │   ├── Layer 2: AI page analysis (if needed)
   │   │   └── Layer 3: AI navigation (unknown pages)
   │   ├── Submit application
   │   └── Record result in SQLite + sync to Sheets
   └── Continue until daily limit reached

3. REPORTING
   ├── Log summary to console (rich tables)
   ├── Save to SQLite database
   ├── Sync to Google Sheets (if configured)
   ├── Export CSV (if configured)
   ├── Send notifications (Desktop / Telegram / Email)
   └── In GHA: commit updated DB back to repo
```

---

## Prerequisites

### Required

| Prerequisite | Details |
|-------------|---------|
| **Python 3.11+** | Tested with 3.12. Check: `python3 --version` |
| **Google Gemini API Key** | **Free.** Get at [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey). 15 RPM, 1500 req/day — enough for 10-20 applications |
| **Job portal accounts** | Active accounts on LinkedIn, Naukri, etc. — whichever portals you enable |
| **Resume PDF** | Place at `data/resume.pdf`. Used for file upload fields |

### Optional

| Prerequisite | Details |
|-------------|---------|
| **Google Cloud service account** | For Google Sheets live dashboard. Free tier is fine |
| **Telegram bot** | For mobile push notifications. Create via [@BotFather](https://t.me/BotFather) |
| **Groq API Key** | Free fallback AI provider if Gemini is down |
| **Ollama** | Local AI fallback — no API key needed, runs on your machine |
| **Proxy server** | Configure in `settings.yaml` if your IP is rate-limited |

### System Dependencies (auto-installed by `setup.sh`)

- Playwright Chromium browser
- Python virtual environment + all pip packages from `requirements.txt`

---

## Quick Start

### 1. Clone & Setup

```bash
git clone <your-repo-url> auto-job-applier
cd auto-job-applier
chmod +x setup.sh
./setup.sh
```

`setup.sh` will:
- Create a Python virtual environment
- Install all dependencies
- Install Playwright Chromium
- Create `config/profile.yaml` from the example template
- Create a `.env` file for your API keys

### 2. Configure Your Profile

Edit `config/profile.yaml` with your real details:

```yaml
personal:
  first_name: "Jane"
  last_name: "Doe"
  email: "jane.doe@example.com"
  phone: "+1-555-0123"

job_search:
  keywords: ["Software Engineer", "Backend Developer", "Python Developer"]
  location: "San Francisco, CA"
  experience_years: 5

skills:
  primary: ["Python", "JavaScript", "AWS", "Docker"]
  # ... more fields in the file
```

### 3. Add Your API Key

```bash
# Option A: Edit .env file
echo 'GEMINI_API_KEY=your_key_here' >> .env

# Option B: Set in settings.yaml under ai.gemini.api_key
```

### 4. Place Your Resume

```bash
cp ~/path/to/your/resume.pdf data/resume.pdf
```

### 5. Login to Portals (First Time Only)

```bash
source venv/bin/activate
python main.py login
```

A browser window opens — login to each portal manually. Sessions are saved for all future runs.

### 6. Start Applying

```bash
python main.py run
```

### 7. Validate Setup (Optional)

```bash
python main.py validate
```

Checks all configs, API keys, browser installation, and database access without submitting any applications.

---

## Configuration Guide

### `config/settings.yaml` — Application Settings

```yaml
# ── Portal Configuration ──────────────────────────
portals:
  linkedin:
    enabled: true
    max_applications_per_day: 5
    easy_apply_only: false        # true = Easy Apply only
  naukri:
    enabled: true
    max_applications_per_day: 5
  wellfound:
    enabled: true
    max_applications_per_day: 3
  instahyre:
    enabled: true
    max_applications_per_day: 3
  generic_career_page:
    enabled: true
    company_career_urls:          # Add specific career pages
      - "https://careers.google.com"
      - "https://jobs.lever.co/your-target-company"

# ── AI Configuration ──────────────────────────────
ai:
  provider: "gemini"              # gemini | groq | ollama
  gemini:
    api_key: ""                   # Or set GEMINI_API_KEY env var
    model: "gemini-2.0-flash"     # Free tier
  groq:
    api_key: ""                   # Fallback provider
  ollama:
    model: "llama3"               # Local fallback

# ── Browser Configuration ─────────────────────────
browser:
  headless: true                  # false = see the browser
  stealth_mode: true
  random_delays: true
  min_delay_ms: 800
  max_delay_ms: 3000
  proxy:
    enabled: false
    server: ""                    # e.g. "http://proxy:8080"

# ── Application Settings ─────────────────────────
app:
  daily_application_target: 10
  max_daily_applications: 25
  company_blacklist: []           # Companies to never apply to

# ── Notifications ─────────────────────────────────
notifications:
  desktop: true
  telegram:
    enabled: false
    bot_token: ""                 # Or TELEGRAM_BOT_TOKEN env var
    chat_id: ""                   # Or TELEGRAM_CHAT_ID env var

# ── Reporting ─────────────────────────────────────
reporting:
  google_sheets:
    enabled: false
    sheet_id: ""                  # Or GOOGLE_SHEET_ID env var
```

### `config/profile.yaml` — Your Personal Details

Created from `config/profile.yaml.example` during setup. Contains your name, contact info, work history, skills, education, and job preferences — everything the AI needs to fill applications on your behalf.

### `.env` — API Keys & Secrets

```bash
GEMINI_API_KEY=your_key_here
TELEGRAM_BOT_TOKEN=             # optional
TELEGRAM_CHAT_ID=               # optional
SMTP_PASSWORD=                  # optional
```

---

## CLI Commands

All commands are run via `python main.py <command>`:

| Command | Description |
|---------|-------------|
| `run` | Run the full pipeline for all enabled portals |
| `run-portal <name>` | Run for a single portal (e.g., `linkedin`, `naukri`) |
| `apply-urls <url1> <url2> ...` | Apply to specific career page URLs directly |
| `login` | Open a browser to login to all portals (first-time setup) |
| `validate` | Check all configs, API keys, browser, and DB — without applying |
| `stats` | Show rich terminal dashboard with application statistics |
| `schedule` | Start APScheduler to run daily at configured time |
| `export-cookies` | Export browser cookies for GitHub Actions (CI/CD) |
| `export-csv` | Export all application data to CSV |
| `export-sheet` | Sync all application data to Google Sheets |
| `setup` | Interactive setup wizard with step-by-step guidance |

---

## Results & Output Locations

After running the bot, here's where to find everything:

### Application Database

| Location | Description |
|----------|-------------|
| `data/applications.db` | **SQLite database** — every application ever submitted. Contains: job title, company, portal, status, timestamps, AI score, error logs. Query with any SQLite client. |

### Exported Reports

| Location | Description |
|----------|-------------|
| `data/applications_export.csv` | CSV export of all applications. Generated by `python main.py export-csv` |
| `data/daily_reports/` | Daily summary reports (JSON) |
| **Google Sheets** | Live dashboard synced after each run (if configured) |

### Logs & Screenshots

| Location | Description |
|----------|-------------|
| `logs/app.log` | Rotating application log — all events, warnings, errors |
| `logs/screenshots/` | Screenshots captured during application (for debugging failed submissions) |

### Terminal Dashboard

```bash
python main.py stats
```

Shows: today's applications, all-time stats, per-portal breakdown, weekly trend, recent applications — all in rich formatted tables.

### Quick Stats via SQLite

```bash
# Total applications
sqlite3 data/applications.db "SELECT COUNT(*) FROM applications"

# Today's applications
sqlite3 data/applications.db "SELECT COUNT(*) FROM applications WHERE date(applied_at) = date('now')"

# Success rate by portal
sqlite3 data/applications.db \
  "SELECT portal, COUNT(*), SUM(CASE WHEN status='applied' THEN 1 ELSE 0 END) FROM applications GROUP BY portal"
```

---

## GitHub Actions (CI/CD)

The bot can run fully automated via GitHub Actions — zero human intervention after initial setup.

### How It Works

- **Cron schedule**: Runs at 9:00 AM and 3:00 PM IST daily
- **Cookie persistence**: Your login sessions are stored as a GitHub Secret
- **State persistence**: The SQLite database is committed back to the repo after each run
- **Manual trigger**: Can also be triggered manually from the GitHub Actions UI

### Setup Steps

1. Push the repo to GitHub
2. Login to portals locally: `python main.py login`
3. Export cookies: `python main.py export-cookies`
4. Add these **GitHub Secrets**:

| Secret | Required | Description |
|--------|----------|-------------|
| `GEMINI_API_KEY` | Yes | Your Gemini API key |
| `BROWSER_COOKIES` | Yes | Output of `export-cookies` command |
| `GOOGLE_SHEETS_CREDS` | No | Base64-encoded service account JSON |
| `GOOGLE_SHEET_ID` | No | Google Sheet ID from the URL |
| `TELEGRAM_BOT_TOKEN` | No | Telegram bot token |
| `TELEGRAM_CHAT_ID` | No | Your Telegram chat ID |

5. The workflow at `.github/workflows/daily_apply.yml` handles everything else.

---

## Google Sheets Dashboard (Optional)

Get a live dashboard that updates after every run.

### Setup

1. Create a Google Cloud project (free tier)
2. Enable the Google Sheets API
3. Create a service account and download the credentials JSON
4. Create a Google Sheet and share it with the service account email
5. Configure:
   - **Local**: Set `reporting.google_sheets.sheet_id` in `settings.yaml` + put creds JSON at `config/sheets_credentials.json`
   - **GitHub Actions**: Base64-encode the JSON (`base64 < creds.json`) → add as `GOOGLE_SHEETS_CREDS` secret + set `GOOGLE_SHEET_ID` secret

### Manual Sync

```bash
python main.py export-sheet
```

---

## How the AI Form Filler Works

The form filler uses a 3-layer intelligence system:

### Layer 1: Direct Pattern Matching (Fast, Zero AI Cost)

45+ regex patterns match common form fields instantly:

```
"First Name"     → profile.first_name
"Email Address"  → profile.email
"Years of Exp"   → profile.years_of_experience
"Phone"          → profile.phone
```

Handles ~60% of all form fields without any AI call.

### Layer 2: AI Page Analysis (Smart, Uses Gemini)

For fields that can't be pattern-matched:
1. JavaScript extracts all visible form fields from the DOM
2. Field labels + types are sent to Gemini along with your profile
3. AI returns a mapping of each field to the correct value
4. AI generates answers for open-ended questions ("Why do you want this role?")

### Layer 3: AI Navigation (Fully Autonomous)

For unknown/multi-step career pages:
1. AI analyzes the page screenshot + simplified HTML
2. Determines the next action: click button, fill field, scroll, navigate
3. Executes the action via Playwright
4. Checks for success/error states
5. Repeats until the application is submitted (or gives up after max retries)

---

## Adding New Portals

1. Create a new directory under `src/portals/`:

```
src/portals/myportal/
├── __init__.py
└── adapter.py
```

2. Implement the adapter:

```python
# src/portals/myportal/adapter.py
from src.portals.base import BasePortalAdapter, JobListing, ApplicationResult

class MyPortalAdapter(BasePortalAdapter):
    async def check_login_status(self) -> bool:
        """Return True if already logged in."""
        ...

    async def login(self) -> bool:
        """Perform login flow."""
        ...

    async def search_jobs(self, keywords: list[str], location: str) -> list[JobListing]:
        """Search and return job listings."""
        ...

    async def apply_to_job(self, job: JobListing) -> ApplicationResult:
        """Apply to a single job. Return success/failure."""
        ...
```

3. Register it in `src/core/orchestrator.py` — add to the portal initialization map.

4. Add portal config in `config/settings.yaml` under `portals:`.

---

## Testing

```bash
source venv/bin/activate

# Run all tests
pytest tests/ -v

# Run a specific test file
pytest tests/test_config.py -v

# Run with async support
pytest tests/ -v --asyncio-mode=auto
```

### Test Files

| File | Covers |
|------|--------|
| `tests/test_config.py` | Config loading, env-var overrides, validation |
| `tests/test_profile.py` | Profile data loading and field access |
| `tests/test_ai_engine.py` | AI engine initialization, provider fallback |
| `tests/test_database.py` | SQLite tracker — insert, dedup, stats queries |
| `tests/test_portals.py` | Portal adapter base class contracts |

---

## Project Structure

```
auto-job-applier/
├── main.py                          # Entry point → CLI
├── setup.sh                         # One-click setup script
├── requirements.txt                 # Python dependencies
├── pyproject.toml                   # Project metadata
├── .env.example                     # Env vars template (no real keys)
├── .gitignore                       # Ignores venv, data, __pycache__, .env
│
├── config/
│   ├── settings.yaml                # App config (portals, AI, browser, etc.)
│   ├── profile.yaml                 # YOUR personal data (fill this!)
│   └── profile.yaml.example         # Template for profile.yaml
│
├── src/
│   ├── __init__.py                  # Package root — exports __version__
│   ├── cli.py                       # CLI commands (click + rich)
│   │
│   ├── core/
│   │   ├── __init__.py              # Exports: config, PROJECT_ROOT, paths
│   │   ├── config.py                # YAML config loader + validator
│   │   ├── profile.py               # Profile data manager
│   │   ├── browser.py               # Playwright browser + stealth
│   │   ├── form_filler.py           # 3-layer adaptive form filler
│   │   └── orchestrator.py          # Main pipeline orchestrator
│   │
│   ├── ai/
│   │   ├── __init__.py              # Exports: AIEngine
│   │   └── engine.py                # Gemini/Groq/Ollama with fallback
│   │
│   ├── portals/
│   │   ├── __init__.py              # Exports: BasePortalAdapter, etc.
│   │   ├── base.py                  # Abstract base + data classes
│   │   ├── linkedin/adapter.py      # LinkedIn automation
│   │   ├── naukri/adapter.py        # Naukri.com automation
│   │   ├── wellfound/adapter.py     # Wellfound automation
│   │   ├── instahyre/adapter.py     # Instahyre automation
│   │   └── generic_career_page/
│   │       └── adapter.py           # Universal AI-driven adapter
│   │
│   ├── tracker/
│   │   ├── __init__.py              # Exports: ApplicationTracker, etc.
│   │   ├── database.py              # SQLite application tracker
│   │   └── sheets.py                # Google Sheets + CSV exporters
│   │
│   ├── scheduler/
│   │   ├── __init__.py              # Exports: JobScheduler
│   │   └── scheduler.py             # APScheduler integration
│   │
│   └── utils/
│       ├── __init__.py              # Exports: setup_logging, etc.
│       ├── logging_config.py        # Logging setup
│       ├── notifications.py         # Desktop/Telegram/Email alerts
│       └── cookies.py               # Cookie export/import for CI/CD
│
├── data/                            # Runtime data (gitignored)
│   ├── applications.db              # SQLite database (created on first run)
│   ├── applications_export.csv      # CSV export
│   ├── resume.pdf                   # YOUR resume (place here)
│   ├── cookies.json                 # Browser cookies (for CI/CD)
│   └── daily_reports/               # Daily JSON summaries
│
├── logs/                            # Logs & screenshots (gitignored)
│   ├── app.log                      # Rotating application log
│   └── screenshots/                 # Debug screenshots
│
├── tests/                           # Test suite
│   ├── conftest.py                  # Shared fixtures
│   ├── test_config.py
│   ├── test_profile.py
│   ├── test_ai_engine.py
│   ├── test_database.py
│   └── test_portals.py
│
└── .github/
    └── workflows/
        └── daily_apply.yml          # Cron job: 9 AM & 3 PM IST daily
```

---

## Troubleshooting

### "Gemini API key not set"

```bash
# Set via environment variable
export GEMINI_API_KEY=your_key_here

# Or add to .env file
echo 'GEMINI_API_KEY=your_key_here' >> .env
```

### "No portals are enabled"

Edit `config/settings.yaml` and set `enabled: true` for at least one portal.

### Browser crashes or hangs

- Set `browser.headless: false` in `settings.yaml` to see what's happening
- Check `logs/app.log` for error details
- Check `logs/screenshots/` for visual debugging
- The orchestrator auto-recovers from browser crashes with retry logic

### "Already applied" — skipping everything

The bot prevents duplicate applications. To reset:

```bash
# See what's in the database
sqlite3 data/applications.db "SELECT job_title, company, portal FROM applications ORDER BY applied_at DESC LIMIT 20"

# Nuclear option: delete the database (starts fresh)
rm data/applications.db
```

### GitHub Actions not running

- Check the Actions tab for errors
- Ensure all required secrets are set
- Try triggering manually via `workflow_dispatch`
- Verify cookies are fresh: re-run `python main.py export-cookies` locally

### Validate your setup

```bash
python main.py validate
```

Checks all configuration, API connectivity, browser installation, and database access without submitting any applications.

---

## AI Cost: Zero

Uses Google Gemini 2.0 Flash free tier:
- **15 requests per minute**
- **1,500 requests per day**
- Enough for **10-20 applications daily** (~5-8 AI calls per application)

The system minimizes AI calls:
1. Regex patterns handle ~60% of form fields (zero cost)
2. JavaScript extraction reduces payload sent to AI
3. Rate limiter prevents quota exhaustion
4. Fallback chain: Gemini → Groq → Ollama (all have free tiers)

---

## Disclaimer

This tool is for educational and personal use. Please:
- Respect each platform's Terms of Service
- Don't spam — the bot has built-in rate limits and daily caps
- Review applications after they're submitted
- Keep your profile data accurate

---

## License

MIT License — Use freely, build upon it.
