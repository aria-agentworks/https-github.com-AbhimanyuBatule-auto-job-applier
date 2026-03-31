# 🚀 Auto Job Applier

**Adaptive AI-Powered Job Application Bot** — Apply to 10+ jobs daily, completely hands-free.

Uses Google Gemini AI (free tier) + Playwright browser automation to intelligently navigate any job portal or company career page, fill forms adaptively, and submit applications while you sleep.

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        ORCHESTRATOR                          │
│              (Coordinates the entire pipeline)               │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐    │
│  │  JOB SEARCH  │  │   AI ENGINE   │  │  FORM FILLER    │    │
│  │  & DISCOVERY │  │ (Gemini Free) │  │  (Adaptive)     │    │
│  └──────┬───────┘  └──────┬───────┘  └────────┬────────┘    │
│         │                 │                    │              │
│  ┌──────▼─────────────────▼────────────────────▼──────────┐  │
│  │              BROWSER ENGINE (Playwright)                │  │
│  │         Stealth mode · Human-like behavior              │  │
│  │         Persistent sessions · Anti-detection            │  │
│  └──────────────────────┬─────────────────────────────────┘  │
│                         │                                    │
│  ┌──────────────────────▼─────────────────────────────────┐  │
│  │                PORTAL ADAPTERS                          │  │
│  │  ┌──────────┐ ┌────────┐ ┌───────────┐ ┌───────────┐  │  │
│  │  │ LinkedIn │ │ Naukri │ │ Wellfound │ │ Instahyre │  │  │
│  │  └──────────┘ └────────┘ └───────────┘ └───────────┘  │  │
│  │  ┌──────────────────────────────────────────────────┐  │  │
│  │  │    GENERIC CAREER PAGE (AI-driven navigation)    │  │  │
│  │  │    Works on ANY company's application page       │  │  │
│  │  └──────────────────────────────────────────────────┘  │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌─────────────────┐  ┌──────────────┐  ┌───────────────┐   │
│  │  TRACKER (SQLite)│  │  SCHEDULER   │  │ NOTIFICATIONS │   │
│  │  Dedup · Stats   │  │  Cron/Daily  │  │ Desktop/TG    │   │
│  └─────────────────┘  └──────────────┘  └───────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

---

## ✨ Key Features

### 🧠 AI-Powered Adaptive Form Filling
- **No hardcoded selectors** — AI analyzes each page in real-time
- Uses Google Gemini 2.0 Flash (FREE tier: 15 RPM, 1500 req/day)
- Falls back to regex patterns for common fields (saves AI quota)
- Handles dropdowns, checkboxes, radio buttons, textareas, file uploads
- Generates answers for open-ended questions from your profile

### 🌐 Multi-Portal Support
| Portal | Status | Features |
|--------|--------|----------|
| **LinkedIn** | ✅ | Easy Apply + External Apply |
| **Naukri.com** | ✅ | Quick Apply + Chatbot Apply + Profile Refresh |
| **Wellfound** | ✅ | Startup jobs with salary transparency |
| **Instahyre** | ✅ | AI-matched opportunities, accept invites |
| **Generic Career Page** | ✅ | **Works on ANY website** using AI navigation |
| Hirist | 🔧 | Config ready, adapter pending |
| Otta | 🔧 | Config ready, adapter pending |
| SEEK | 🔧 | Config ready, adapter pending |

### 🕵️ Anti-Detection (Stealth Mode)
- Persistent browser sessions (login once, run forever)
- Randomized human-like delays between actions
- Realistic user agents & browser fingerprints  
- Overrides `navigator.webdriver` and other bot detection signals
- Configurable proxy support

### 📊 Application Tracking
- SQLite database tracks every application
- Prevents duplicate applications
- Daily, weekly, and all-time statistics
- Per-portal breakdowns
- Rich CLI dashboard

### 🔔 Notifications
- Desktop notifications (macOS/Linux/Windows)
- Telegram bot integration
- Email summary reports

---

## 🚀 Quick Start

### 1. Setup
```bash
cd auto-job-applier
chmod +x setup.sh
./setup.sh
```

### 2. Configure Your Profile
Edit `config/profile.yaml` with your personal details, skills, experience, and preferences.

### 3. Get Free Gemini API Key
1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Create a free API key
3. Add to `.env` file: `GEMINI_API_KEY=your_key_here`

### 4. Add Your Resume
Place your resume at `data/resume.pdf`

### 5. Login to Portals (First Time Only)
```bash
source venv/bin/activate
python main.py login
```
This opens a browser — login manually to each portal. Sessions are saved permanently.

### 6. Start Applying!
```bash
# Apply to all enabled portals
python main.py run

# Or just one portal
python main.py run-portal linkedin
python main.py run-portal naukri

# Or apply to specific URLs
python main.py apply-urls "https://company.com/careers/sdet" "https://another.com/apply"

# View statistics
python main.py stats

# Run on schedule (daily at 9 AM)
python main.py schedule
```

---

## 📁 Project Structure

```
auto-job-applier/
├── main.py                     # Entry point
├── setup.sh                    # One-click setup
├── requirements.txt            # Dependencies
├── .env.example                # Environment variables template
│
├── config/
│   ├── settings.yaml           # App settings (portals, AI, browser)
│   └── profile.yaml            # YOUR profile data (fill this!)
│
├── src/
│   ├── core/
│   │   ├── config.py           # Configuration loader
│   │   ├── profile.py          # Profile data manager
│   │   ├── browser.py          # Playwright browser with stealth
│   │   ├── form_filler.py      # Adaptive AI form filler (THE BRAIN)
│   │   └── orchestrator.py     # Main pipeline orchestrator
│   │
│   ├── ai/
│   │   └── engine.py           # AI engine (Gemini/Ollama/Groq)
│   │
│   ├── portals/
│   │   ├── base.py             # Base adapter (abstract)
│   │   ├── linkedin/adapter.py # LinkedIn automation
│   │   ├── naukri/adapter.py   # Naukri.com automation
│   │   ├── wellfound/adapter.py # Wellfound automation
│   │   ├── instahyre/adapter.py # Instahyre automation
│   │   └── generic_career_page/adapter.py # Universal adapter
│   │
│   ├── tracker/
│   │   └── database.py         # SQLite application tracker
│   │
│   ├── scheduler/
│   │   └── scheduler.py        # APScheduler for daily runs
│   │
│   ├── utils/
│   │   ├── logging_config.py   # Logging setup
│   │   └── notifications.py    # Desktop/Telegram/Email alerts
│   │
│   └── cli.py                  # Rich CLI interface
│
├── data/                       # Resume, DB, browser profile
├── logs/                       # Application logs & screenshots
└── templates/                  # Response templates
```

---

## 🔧 How the Adaptive Form Filler Works

This is the core innovation. Here's the 3-layer intelligence:

### Layer 1: Direct Pattern Matching (Fast, No AI)
```
Field label: "First Name"  →  regex matches  →  profile.first_name
Field label: "Email"       →  regex matches  →  profile.email
Field label: "Experience"  →  regex matches  →  profile.years_of_experience
```
45+ regex patterns handle common fields instantly without using AI quota.

### Layer 2: AI Page Analysis (Smart, Uses Gemini)
For fields that can't be pattern-matched:
1. Extracts all form fields using JavaScript injection
2. Sends cleaned HTML to Gemini with your profile
3. AI maps each field to the correct profile value
4. AI generates answers for open-ended questions

### Layer 3: AI Navigation (Adaptive, Fully Autonomous)
For unknown career pages:
1. AI analyzes the page screenshot + HTML
2. Determines the next action (click, type, scroll, navigate)
3. Executes the action via Playwright
4. Checks for success/error states
5. Repeats until application is submitted or stuck

---

## ⚙️ Configuration Reference

### Portal Settings (`config/settings.yaml`)
```yaml
portals:
  linkedin:
    enabled: true
    max_applications_per_day: 5
    easy_apply_only: false    # Set true for Easy Apply only
  naukri:
    enabled: true
    max_applications_per_day: 5
  generic_career_page:
    enabled: true
    company_career_urls:      # Add specific career pages
      - "https://google.com/careers"
      - "https://microsoft.com/careers"
```

### AI Settings
```yaml
ai:
  provider: "gemini"          # gemini | ollama | groq
  gemini:
    api_key: ""               # Or use GEMINI_API_KEY env var
    model: "gemini-2.0-flash" # Free tier model
```

### Browser Settings
```yaml
browser:
  headless: true              # false for debugging
  stealth_mode: true          # Anti-detection
  random_delays: true         # Human-like behavior
  min_delay_ms: 800
  max_delay_ms: 3000
```

---

## 📊 CLI Commands

| Command | Description |
|---------|-------------|
| `python main.py setup` | Interactive setup wizard |
| `python main.py login` | Login to all portals (first time) |
| `python main.py run` | Run full pipeline (all portals) |
| `python main.py run-portal <name>` | Run for specific portal |
| `python main.py apply-urls <url1> <url2>` | Apply to specific URLs |
| `python main.py stats` | Show application dashboard |
| `python main.py schedule` | Start daily scheduler |

---

## 🛡️ AI Cost: ZERO

Uses Google Gemini 2.0 Flash free tier:
- **15 requests per minute**
- **1,500 requests per day**
- That's enough for **10-20 applications daily** (uses ~5-8 AI calls per application)

The system is optimized to minimize AI calls:
1. Direct regex mapping handles ~60% of form fields
2. JavaScript extraction reduces HTML sent to AI
3. Rate limiter prevents quota exhaustion

---

## 🤖 Adding New Portals

Create a new adapter by extending `BasePortalAdapter`:

```python
from src.portals.base import BasePortalAdapter, JobListing, ApplicationResult

class NewPortalAdapter(BasePortalAdapter):
    async def check_login_status(self) -> bool:
        # Check if logged in
        ...
    
    async def login(self) -> bool:
        # Login flow
        ...
    
    async def search_jobs(self, keywords, location) -> list[JobListing]:
        # Search for jobs
        ...
    
    async def apply_to_job(self, job) -> ApplicationResult:
        # Apply to a job
        ...
```

Then register it in `src/core/orchestrator.py`.

---

## ⚠️ Disclaimer

This tool is for educational and personal use. Please:
- Respect each platform's Terms of Service
- Don't spam — the bot has built-in rate limits
- Review applications after they're submitted
- Keep your profile data accurate

---

## 📝 License

MIT License - Use freely, build upon it.
