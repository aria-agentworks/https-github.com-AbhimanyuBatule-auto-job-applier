"""
Auto Job Applier - CLI Interface
Rich, interactive command-line interface.
"""

import asyncio
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

console = Console()

BANNER = """
╔═══════════════════════════════════════════════════════════╗
║           🚀 AUTO JOB APPLIER v1.0.0 🚀                 ║
║         Adaptive AI-Powered Job Application Bot          ║
║                                                          ║
║  • AI-driven form filling (Google Gemini - Free Tier)    ║
║  • Multi-portal support (LinkedIn, Naukri, Wellfound...) ║
║  • Generic career page navigator                         ║
║  • Smart job matching & scoring                          ║
║  • Application tracking & reporting                      ║
╚═══════════════════════════════════════════════════════════╝
"""


@click.group()
def cli():
    """Auto Job Applier - Apply to 10+ jobs daily, hands-free."""
    pass


@cli.command()
def run():
    """Run the full application pipeline (all enabled portals)."""
    console.print(Panel(BANNER, border_style="green"))
    console.print("[bold green]Starting full application run...[/]")

    from src.utils.logging_config import setup_logging
    setup_logging()

    from src.core.orchestrator import Orchestrator

    async def _run():
        orchestrator = Orchestrator()
        report = await orchestrator.run()
        _display_report(report)

    asyncio.run(_run())


@cli.command()
@click.argument("portal")
def run_portal(portal):
    """Run the pipeline for a single portal (e.g., linkedin, naukri)."""
    console.print(f"[bold blue]Running for portal: {portal}[/]")

    from src.utils.logging_config import setup_logging
    setup_logging()

    from src.core.orchestrator import Orchestrator

    async def _run():
        orchestrator = Orchestrator()
        report = await orchestrator.run_single_portal(portal)
        _display_report(report)

    asyncio.run(_run())


@cli.command()
@click.argument("urls", nargs=-1)
def apply_urls(urls):
    """Apply to specific career page URLs directly."""
    if not urls:
        console.print("[red]Please provide at least one URL[/]")
        return

    console.print(f"[bold blue]Applying to {len(urls)} URLs...[/]")

    from src.utils.logging_config import setup_logging
    setup_logging()

    from src.core.orchestrator import Orchestrator

    async def _run():
        orchestrator = Orchestrator()
        report = await orchestrator.apply_to_urls(list(urls))
        _display_report(report)

    asyncio.run(_run())


@cli.command()
def login():
    """Login to all enabled portals (first-time setup)."""
    console.print("[bold yellow]Starting portal login setup...[/]")
    console.print("You'll need to login manually to each portal once.")
    console.print("Sessions will be saved for future automated runs.\n")

    from src.utils.logging_config import setup_logging
    setup_logging()

    from src.core.orchestrator import Orchestrator

    async def _run():
        orchestrator = Orchestrator()
        await orchestrator.login_to_portals()
        await orchestrator.shutdown()

    asyncio.run(_run())
    console.print("\n[bold green]Login setup complete! Sessions saved.[/]")


@cli.command()
def stats():
    """Show application statistics and dashboard."""
    from src.utils.logging_config import setup_logging
    setup_logging()

    from src.core.orchestrator import Orchestrator

    async def _run():
        orchestrator = Orchestrator()
        data = await orchestrator.show_stats()
        _display_dashboard(data)

    asyncio.run(_run())


@cli.command()
def schedule():
    """Start the scheduler (runs daily at configured time)."""
    console.print(Panel(BANNER, border_style="green"))
    console.print("[bold green]Starting scheduled mode...[/]")
    console.print("The bot will run automatically at the configured time.\n")

    from src.utils.logging_config import setup_logging
    setup_logging()

    from src.scheduler.scheduler import JobScheduler

    async def _run():
        scheduler = JobScheduler()
        await scheduler.run_scheduled()

    asyncio.run(_run())


@cli.command()
def export_cookies():
    """Export browser cookies for GitHub Actions (CI/CD)."""
    console.print("[bold cyan]Exporting browser cookies...[/]")
    console.print("This captures your login sessions for headless runs.\n")

    from src.utils.logging_config import setup_logging
    setup_logging()

    from src.core.orchestrator import Orchestrator

    async def _run():
        orchestrator = Orchestrator()
        await orchestrator.export_cookies()

    asyncio.run(_run())
    console.print("\n[bold green]Done! See instructions above to set as GitHub Secret.[/]")


@cli.command()
def export_sheet():
    """Sync all application data to Google Sheets."""
    console.print("[bold cyan]Syncing to Google Sheets...[/]")

    from src.utils.logging_config import setup_logging
    setup_logging()

    from src.core.orchestrator import Orchestrator

    async def _run():
        orchestrator = Orchestrator()
        await orchestrator.export_to_sheets()

    asyncio.run(_run())
    console.print("[bold green]Google Sheets sync complete.[/]")


@cli.command()
def export_csv():
    """Export all applications to CSV file."""
    from src.utils.logging_config import setup_logging
    setup_logging()

    from src.core.orchestrator import Orchestrator

    async def _run():
        orchestrator = Orchestrator()
        path = await orchestrator.export_to_csv()
        if path:
            console.print(f"[bold green]CSV exported: {path}[/]")
        else:
            console.print("[yellow]No data to export yet.[/]")

    asyncio.run(_run())


@cli.command()
def validate():
    """Check all configs, API keys, browser, and DB without applying."""
    console.print(Panel(BANNER, border_style="cyan"))
    console.print("[bold cyan]VALIDATION CHECK[/]\n")

    all_ok = True

    # ── 1. Config files ──────────────────────────────────────
    from src.core.config import CONFIG_DIR, DATA_DIR

    settings_path = CONFIG_DIR / "settings.yaml"
    profile_path = CONFIG_DIR / "profile.yaml"

    if settings_path.exists():
        console.print("[green]✓[/] config/settings.yaml found")
    else:
        console.print("[red]✗[/] config/settings.yaml MISSING")
        all_ok = False

    if profile_path.exists():
        console.print("[green]✓[/] config/profile.yaml found")
    else:
        console.print("[red]✗[/] config/profile.yaml MISSING — run: cp config/profile.yaml.example config/profile.yaml")
        all_ok = False

    # ── 2. Config validation ─────────────────────────────────
    from src.core.config import config

    provider = config.get("ai", "provider", default="gemini")
    api_key = config.get("ai", provider, "api_key") or ""
    if api_key and api_key != "your_key_here":
        console.print(f"[green]✓[/] AI provider '{provider}' API key is set")
    else:
        console.print(f"[red]✗[/] AI provider '{provider}' API key NOT set — set GEMINI_API_KEY env var or ai.gemini.api_key in settings.yaml")
        all_ok = False

    # ── 3. Profile validation ────────────────────────────────
    email = config.get_profile("personal", "email") or ""
    if email and email != "your.email@example.com":
        console.print(f"[green]✓[/] Profile email configured: {email}")
    else:
        console.print("[red]✗[/] Profile email not configured — edit config/profile.yaml")
        all_ok = False

    keywords = config.get_profile("job_search", "keywords") or []
    if keywords:
        console.print(f"[green]✓[/] Job search keywords: {', '.join(keywords[:5])}")
    else:
        console.print("[yellow]⚠[/] No job search keywords configured in profile.yaml")

    # ── 4. Enabled portals ───────────────────────────────────
    portals = config.settings.get("portals", {})
    enabled = [name for name, cfg in portals.items() if isinstance(cfg, dict) and cfg.get("enabled")]
    if enabled:
        console.print(f"[green]✓[/] Enabled portals: {', '.join(enabled)}")
    else:
        console.print("[red]✗[/] No portals enabled — edit config/settings.yaml")
        all_ok = False

    # ── 5. Resume file ───────────────────────────────────────
    resume_path = DATA_DIR / "resume.pdf"
    if resume_path.exists():
        size_kb = resume_path.stat().st_size / 1024
        console.print(f"[green]✓[/] Resume found: data/resume.pdf ({size_kb:.0f} KB)")
    else:
        console.print("[yellow]⚠[/] No resume at data/resume.pdf — file upload fields won't work")

    # ── 6. Playwright browser ────────────────────────────────
    import shutil
    if shutil.which("playwright"):
        console.print("[green]✓[/] Playwright CLI available")
    else:
        console.print("[yellow]⚠[/] Playwright CLI not found in PATH — run: pip install playwright && playwright install chromium")

    # ── 7. Database ──────────────────────────────────────────
    db_path = DATA_DIR / "applications.db"
    if db_path.exists():
        size_kb = db_path.stat().st_size / 1024
        console.print(f"[green]✓[/] Database exists: data/applications.db ({size_kb:.0f} KB)")
    else:
        console.print("[dim]ℹ[/] Database will be created on first run")

    # ── 8. .env file ─────────────────────────────────────────
    import os
    env_path = CONFIG_DIR.parent / ".env"
    if env_path.exists():
        console.print("[green]✓[/] .env file found")
    else:
        console.print("[dim]ℹ[/] No .env file — using settings.yaml and environment variables only")

    # ── Summary ──────────────────────────────────────────────
    console.print("")
    if all_ok:
        console.print(Panel("[bold green]All critical checks passed! Ready to run: python main.py run[/]", border_style="green"))
    else:
        console.print(Panel("[bold red]Some checks failed. Fix the issues above before running.[/]", border_style="red"))


@cli.command()
def setup():
    """Interactive setup wizard."""
    console.print(Panel(BANNER, border_style="cyan"))
    _setup_wizard()


# ── Display Functions ───────────────────────────────────────────

def _display_report(report: dict):
    """Display application run report with rich formatting."""
    console.print("\n")

    # Summary table
    table = Table(title="Application Run Report", box=box.DOUBLE_EDGE)
    table.add_column("Metric", style="cyan", width=20)
    table.add_column("Value", style="bold")

    table.add_row("Total Attempted", str(report.get("total_attempted", 0)))
    table.add_row("Successful", f"[green]{report.get('total_success', 0)}[/]")
    table.add_row("Failed", f"[red]{report.get('total_failed', 0)}[/]")
    table.add_row("Success Rate", report.get("success_rate", "N/A"))

    console.print(table)

    # Successful applications
    if report.get("successful_applications"):
        console.print("\n[bold green]✓ Successful Applications:[/]")
        for app in report["successful_applications"]:
            console.print(f"  [green]✓[/] {app['job']} @ {app['company']} [dim]({app['portal']})[/]")

    # Failed applications
    if report.get("failed_applications"):
        console.print("\n[bold red]✗ Failed Applications:[/]")
        for app in report["failed_applications"]:
            console.print(f"  [red]✗[/] {app['job']} @ {app['company']} - [dim]{app['error']}[/]")


def _display_dashboard(data: dict):
    """Display the statistics dashboard."""
    console.print(Panel(BANNER, border_style="blue"))

    # Today's stats
    today = data.get("today", {})
    today_table = Table(title="Today's Stats", box=box.ROUNDED)
    today_table.add_column("Metric", style="cyan")
    today_table.add_column("Count", style="bold", justify="center")
    today_table.add_row("Total Applications", str(today.get("total", 0)))
    today_table.add_row("Successful", f"[green]{today.get('success', 0)}[/]")
    today_table.add_row("Failed", f"[red]{today.get('failed', 0)}[/]")
    console.print(today_table)

    # All-time stats
    total = data.get("total", {})
    total_table = Table(title="\nAll-Time Stats", box=box.ROUNDED)
    total_table.add_column("Metric", style="cyan")
    total_table.add_column("Count", style="bold", justify="center")
    total_table.add_row("Total Applications", str(total.get("total", 0)))
    total_table.add_row("Successful", f"[green]{total.get('success', 0)}[/]")
    total_table.add_row("Failed", f"[red]{total.get('failed', 0)}[/]")
    total_table.add_row("Unique Companies", str(total.get("unique_companies", 0)))
    total_table.add_row("Portals Used", str(total.get("portals_used", 0)))
    console.print(total_table)

    # Portal breakdown
    portal_stats = data.get("portal_stats", [])
    if portal_stats:
        portal_table = Table(title="\nPer-Portal Stats", box=box.ROUNDED)
        portal_table.add_column("Portal", style="cyan")
        portal_table.add_column("Total", justify="center")
        portal_table.add_column("Success", justify="center", style="green")
        portal_table.add_column("Failed", justify="center", style="red")
        for ps in portal_stats:
            portal_table.add_row(
                ps["portal"].capitalize(),
                str(ps["total"]),
                str(ps["success"]),
                str(ps["failed"]),
            )
        console.print(portal_table)

    # Weekly trend
    trend = data.get("weekly_trend", [])
    if trend:
        trend_table = Table(title="\nWeekly Trend", box=box.ROUNDED)
        trend_table.add_column("Date", style="cyan")
        trend_table.add_column("Total", justify="center")
        trend_table.add_column("Success", justify="center", style="green")
        for day in trend:
            trend_table.add_row(day["date"], str(day["total"]), str(day["success"]))
        console.print(trend_table)

    # Recent applications
    recent = data.get("recent", [])
    if recent:
        recent_table = Table(title="\nRecent Applications", box=box.ROUNDED)
        recent_table.add_column("Time", style="dim", width=20)
        recent_table.add_column("Portal", style="cyan", width=12)
        recent_table.add_column("Job Title", width=30)
        recent_table.add_column("Company", width=20)
        recent_table.add_column("Status", width=10)
        for r in recent:
            status = "[green]Applied[/]" if r["status"] == "applied" else "[red]Failed[/]"
            recent_table.add_row(
                r["applied_at"][:19] if r["applied_at"] else "",
                r["portal"].capitalize(),
                r["job_title"],
                r["company"],
                status,
            )
        console.print(recent_table)


def _setup_wizard():
    """Interactive setup wizard."""
    from src.core.config import CONFIG_DIR

    console.print("\n[bold cyan]SETUP WIZARD[/]\n")
    console.print("Let's configure your Auto Job Applier.\n")

    # Check profile
    profile_path = CONFIG_DIR / "profile.yaml"
    if profile_path.exists():
        console.print("[green]✓[/] Profile config found: config/profile.yaml")
        console.print("  [dim]Edit this file with your details[/]")
    else:
        console.print("[red]✗[/] Profile config missing!")

    # Check API key
    settings_path = CONFIG_DIR / "settings.yaml"
    if settings_path.exists():
        console.print("[green]✓[/] Settings config found: config/settings.yaml")
    else:
        console.print("[red]✗[/] Settings config missing!")

    console.print("\n[bold]Required Steps:[/]")
    console.print("1. Edit [cyan]config/profile.yaml[/] with your personal details")
    console.print("2. Get a free Gemini API key from [link]https://aistudio.google.com/app/apikey[/link]")
    console.print("3. Set the API key in [cyan]config/settings.yaml[/] or [cyan]GEMINI_API_KEY[/] env var")
    console.print("4. Place your resume PDF in [cyan]data/resume.pdf[/]")
    console.print("5. Run [bold green]python main.py login[/] to login to portals")
    console.print("6. Run [bold green]python main.py run[/] to start applying!")

    console.print("\n[bold]GitHub Actions (Fully Automated):[/]")
    console.print("7. Push repo to GitHub")
    console.print("8. Run [bold green]python main.py export-cookies[/] to capture login sessions")
    console.print("9. Add GitHub Secrets: GEMINI_API_KEY, BROWSER_COOKIES")
    console.print("10. The cron workflow runs at 9 AM & 3 PM IST daily, zero intervention")

    console.print("\n[bold]Google Sheets Dashboard (Optional):[/]")
    console.print("11. Create a Google Cloud service account (free)")
    console.print("12. Enable Google Sheets API, download creds JSON")
    console.print("13. Base64 encode it: [dim]base64 < creds.json[/]")
    console.print("14. Add GitHub Secret: GOOGLE_SHEETS_CREDS (base64 string)")
    console.print("15. Create a Google Sheet, share with service account email")
    console.print("16. Add GitHub Secret: GOOGLE_SHEET_ID (from sheet URL)")

    console.print("\n[bold]Other Options:[/]")
    console.print("• [bold green]python main.py export-csv[/]  — Export to CSV anytime")
    console.print("• [bold green]python main.py export-sheet[/] — Sync to Google Sheets")
    console.print("• [bold green]python main.py stats[/]        — View terminal dashboard")
    console.print("• Set up Telegram notifications for daily reports")


if __name__ == "__main__":
    cli()
