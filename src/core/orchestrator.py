"""
Orchestrator - The main engine that ties everything together.
Runs the full pipeline: discover -> score -> apply -> track -> report.
Designed for zero-failure operation in CI/CD (GitHub Actions).
"""

import asyncio
import logging
import traceback
from datetime import datetime
from typing import Optional

from src.core.config import config
from src.core.browser import BrowserManager
from src.core.profile import ProfileManager
from src.core.form_filler import AdaptiveFormFiller
from src.ai.engine import AIEngine
from src.tracker.database import ApplicationTracker
from src.tracker.sheets import GoogleSheetsReporter, CSVExporter
from src.portals.base import BasePortalAdapter, ApplicationResult

logger = logging.getLogger("orchestrator")


class Orchestrator:
    """
    Main orchestrator that runs the full job application pipeline.
    Coordinates all components: browser, AI, portals, tracker.
    """

    def __init__(self):
        self.browser = BrowserManager()
        self.profile = ProfileManager()
        self.ai = AIEngine()
        self.tracker = ApplicationTracker()
        self.sheets = GoogleSheetsReporter()
        self.csv_exporter = CSVExporter()
        self.form_filler: Optional[AdaptiveFormFiller] = None
        self._portals: list[BasePortalAdapter] = []
        self._daily_target = config.get("app", "daily_application_target", default=10)
        self._max_daily = config.get("app", "max_daily_applications", default=25)
        self._total_applied = 0
        self._total_success = 0
        self._run_id: Optional[int] = None

    async def initialize(self):
        """Initialize all components."""
        logger.info("=" * 60)
        logger.info("AUTO JOB APPLIER - Initializing")
        logger.info("=" * 60)

        # Start browser
        await self.browser.start()

        # Initialize AI
        await self.ai.initialize()

        # Initialize form filler
        self.form_filler = AdaptiveFormFiller(self.browser, self.profile, self.ai)

        # Initialize tracker
        await self.tracker.initialize()

        # Initialize portal adapters
        await self._init_portals()

        # Initialize Google Sheets (non-blocking, graceful if unavailable)
        try:
            await self.sheets.initialize()
        except Exception as e:
            logger.warning(f"Google Sheets not available (will use CSV): {e}")

        logger.info(f"Initialized {len(self._portals)} portal adapters")
        logger.info(f"Daily target: {self._daily_target} applications")

    async def _init_portals(self):
        """Initialize enabled portal adapters."""
        from src.portals.linkedin.adapter import LinkedInAdapter
        from src.portals.naukri.adapter import NaukriAdapter
        from src.portals.wellfound.adapter import WellfoundAdapter
        from src.portals.instahyre.adapter import InstahyreAdapter
        from src.portals.generic_career_page.adapter import GenericCareerPageAdapter

        portal_classes = [
            LinkedInAdapter,
            NaukriAdapter,
            WellfoundAdapter,
            InstahyreAdapter,
            GenericCareerPageAdapter,
        ]

        for cls in portal_classes:
            adapter = cls(
                browser=self.browser,
                profile=self.profile,
                ai=self.ai,
                form_filler=self.form_filler,
            )
            if adapter.is_enabled:
                self._portals.append(adapter)
                logger.info(f"  ✓ {adapter.portal_name} enabled")
            else:
                logger.info(f"  ✗ {adapter.portal_name} disabled")

    async def run(self) -> dict:
        """
        Run the full application pipeline.
        Returns a summary report.
        Designed for ZERO failures — every exception is caught and logged.
        """
        report = {"total_attempted": 0, "total_success": 0, "total_failed": 0,
                  "success_rate": "0%", "successful_applications": [], "failed_applications": []}
        try:
            await self.initialize()
            self._run_id = await self.tracker.start_run()

            logger.info("\n" + "=" * 60)
            logger.info("STARTING APPLICATION RUN")
            logger.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info("=" * 60)

            all_results: list[ApplicationResult] = []

            # Process each portal (each portal is independently wrapped)
            for portal in self._portals:
                if self._total_applied >= self._max_daily:
                    logger.info(f"Daily max ({self._max_daily}) reached, stopping")
                    break

                logger.info(f"\n--- Processing: {portal.portal_name.upper()} ---")
                try:
                    results = await asyncio.wait_for(
                        portal.discover_and_apply(),
                        timeout=600,  # 10 min max per portal
                    )
                    all_results.extend(results)

                    # Update counts & track
                    for r in results:
                        self._total_applied += 1
                        if r.success:
                            self._total_success += 1

                        # Track in database (never fail on this)
                        try:
                            await self.tracker.record_application(r)
                        except Exception as db_err:
                            logger.error(f"DB record error: {db_err}")

                        # Track in Google Sheet (non-blocking)
                        try:
                            await self.sheets.append_application(
                                portal=r.portal,
                                job_id=r.job_id,
                                job_title=r.job_title,
                                company=r.company,
                                status="applied" if r.success else "failed",
                                steps_completed=r.steps_completed,
                                error=r.error,
                                screenshot_path=r.screenshot_path,
                            )
                        except Exception:
                            pass  # Sheet errors are non-critical

                except asyncio.TimeoutError:
                    logger.error(f"Portal TIMEOUT ({portal.portal_name}) - skipping")
                except Exception as e:
                    logger.error(f"Portal error ({portal.portal_name}): {e}\n{traceback.format_exc()}")

                # Cool-down between portals
                await asyncio.sleep(5)

            # Generate report
            report = await self._generate_report(all_results)

            # End run in tracker
            try:
                await self.tracker.end_run(
                    self._run_id, self._total_applied, self._total_success
                )
                await self.tracker.update_daily_stats()
            except Exception as e:
                logger.error(f"Tracker finalize error: {e}")

            # Export to CSV (always, as backup)
            try:
                await self.csv_exporter.export_all()
                await self.csv_exporter.export_today_summary()
            except Exception as e:
                logger.error(f"CSV export error: {e}")

            # Sync full data to Google Sheets
            try:
                await self.sheets.create_daily_summary_sheet()
            except Exception:
                pass

            return report

        except Exception as e:
            logger.error(f"Orchestrator critical error: {e}\n{traceback.format_exc()}")
            if self._run_id:
                try:
                    await self.tracker.end_run(self._run_id, self._total_applied, self._total_success, str(e))
                except Exception:
                    pass
            return report
        finally:
            await self.shutdown()

    async def run_single_portal(self, portal_name: str) -> dict:
        """Run the pipeline for a single portal only."""
        await self.initialize()

        portal = next((p for p in self._portals if p.portal_name == portal_name), None)
        if not portal:
            return {"error": f"Portal '{portal_name}' not found or not enabled"}

        results = await portal.discover_and_apply()

        for r in results:
            await self.tracker.record_application(r)

        report = await self._generate_report(results)
        await self.shutdown()
        return report

    async def apply_to_urls(self, urls: list[str]) -> dict:
        """Apply to a list of direct URLs."""
        await self.initialize()

        from src.portals.generic_career_page.adapter import GenericCareerPageAdapter

        generic = GenericCareerPageAdapter(
            browser=self.browser,
            profile=self.profile,
            ai=self.ai,
            form_filler=self.form_filler,
        )

        results = []
        for url in urls:
            logger.info(f"\nApplying to: {url}")
            result = await generic.apply_to_url(url)
            results.append(result)
            await self.tracker.record_application(result)
            await asyncio.sleep(3)

        report = await self._generate_report(results)
        await self.shutdown()
        return report

    async def login_to_portals(self):
        """Interactive login to all enabled portals (for first-time setup)."""
        await self.initialize()

        for portal in self._portals:
            logger.info(f"\n--- Login to {portal.portal_name.upper()} ---")
            success = await portal.ensure_logged_in()
            if success:
                logger.info(f"✓ {portal.portal_name}: Logged in")
            else:
                logger.warning(f"✗ {portal.portal_name}: Login failed")

        logger.info("\nLogin sessions saved. You won't need to login again.")

    async def show_stats(self) -> dict:
        """Show application statistics."""
        await self.tracker.initialize()

        today = await self.tracker.get_today_stats()
        total = await self.tracker.get_total_stats()
        portal_stats = await self.tracker.get_portal_stats()
        recent = await self.tracker.get_recent_applications(10)
        trend = await self.tracker.get_weekly_trend()

        await self.tracker.close()

        return {
            "today": today,
            "total": total,
            "portal_stats": portal_stats,
            "recent": recent,
            "weekly_trend": trend,
        }

    async def export_to_sheets(self):
        """Export all application data to Google Sheets."""
        await self.tracker.initialize()

        sheets_ok = await self.sheets.initialize()
        if sheets_ok:
            await self.sheets.sync_from_database()
            await self.sheets.create_daily_summary_sheet()
            logger.info("Google Sheets export complete")
        else:
            logger.warning("Google Sheets not configured, skipping")

        await self.tracker.close()

    async def export_to_csv(self) -> str:
        """Export all application data to CSV."""
        path = await self.csv_exporter.export_all()
        await self.csv_exporter.export_today_summary()
        return path

    async def export_cookies(self):
        """Export browser cookies for CI/CD use."""
        await self.browser.start()
        from src.utils.cookies import export_cookies, get_cookies_for_secret
        await export_cookies(self.browser.context)
        get_cookies_for_secret()
        await self.browser.stop()

    async def _generate_report(self, results: list[ApplicationResult]) -> dict:
        """Generate a summary report."""
        success = [r for r in results if r.success]
        failed = [r for r in results if not r.success]

        report = {
            "timestamp": datetime.now().isoformat(),
            "total_attempted": len(results),
            "total_success": len(success),
            "total_failed": len(failed),
            "success_rate": f"{len(success) / max(len(results), 1) * 100:.1f}%",
            "successful_applications": [
                {"portal": r.portal, "job": r.job_title, "company": r.company}
                for r in success
            ],
            "failed_applications": [
                {"portal": r.portal, "job": r.job_title, "company": r.company, "error": r.error}
                for r in failed
            ],
        }

        # Log report
        logger.info("\n" + "=" * 60)
        logger.info("APPLICATION RUN REPORT")
        logger.info("=" * 60)
        logger.info(f"Total Attempted: {report['total_attempted']}")
        logger.info(f"Successful: {report['total_success']}")
        logger.info(f"Failed: {report['total_failed']}")
        logger.info(f"Success Rate: {report['success_rate']}")

        if success:
            logger.info("\nSuccessful Applications:")
            for app in report["successful_applications"]:
                logger.info(f"  ✓ {app['job']} @ {app['company']} ({app['portal']})")

        if failed:
            logger.info("\nFailed Applications:")
            for app in report["failed_applications"]:
                logger.info(f"  ✗ {app['job']} @ {app['company']} - {app['error']}")

        logger.info("=" * 60)

        return report

    async def shutdown(self):
        """Clean shutdown of all components."""
        logger.info("Shutting down...")
        try:
            await self.browser.stop()
        except Exception:
            pass
        try:
            await self.tracker.close()
        except Exception:
            pass
        logger.info("Shutdown complete")
