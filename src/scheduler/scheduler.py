"""
Scheduler - Runs the job application pipeline on a schedule.
Uses APScheduler for cron-like scheduling.
"""

import asyncio
import logging
import signal
import sys
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.core.config import config
from src.core.orchestrator import Orchestrator
from src.utils.notifications import NotificationManager

logger = logging.getLogger("scheduler")


class JobScheduler:
    """
    Schedules and runs the automation pipeline.
    Can run as a daemon or one-shot.
    """

    def __init__(self):
        self._scheduler = AsyncIOScheduler()
        self._notification = NotificationManager()
        self._running = False

    async def run_once(self):
        """Run the pipeline once immediately."""
        logger.info("Running one-shot application cycle...")
        orchestrator = Orchestrator()
        report = await orchestrator.run()
        await self._send_report(report)
        return report

    async def run_scheduled(self):
        """Start the scheduler to run at configured times."""
        cron_expr = config.get("scheduler", "cron_expression", default="0 9 * * *")
        tz = config.get("scheduler", "timezone", default="Asia/Kolkata")

        # Parse cron expression
        parts = cron_expr.split()
        trigger = CronTrigger(
            minute=parts[0],
            hour=parts[1],
            day=parts[2],
            month=parts[3],
            day_of_week=parts[4],
            timezone=tz,
        )

        self._scheduler.add_job(self._scheduled_run, trigger, id="daily_apply")

        # Also run immediately if configured
        self._scheduler.start()
        self._running = True

        logger.info(f"Scheduler started: {cron_expr} ({tz})")
        logger.info("Press Ctrl+C to stop")

        # Handle graceful shutdown
        loop = asyncio.get_event_loop()

        def shutdown_handler():
            logger.info("Shutdown signal received")
            self._running = False
            self._scheduler.shutdown(wait=False)

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, shutdown_handler)

        # Keep running
        while self._running:
            await asyncio.sleep(60)

    async def _scheduled_run(self):
        """Execute a scheduled run."""
        try:
            logger.info(f"\n{'='*60}")
            logger.info(f"SCHEDULED RUN - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f"{'='*60}")

            orchestrator = Orchestrator()
            report = await orchestrator.run()
            await self._send_report(report)

        except Exception as e:
            logger.error(f"Scheduled run failed: {e}")
            await self._notification.send(
                title="Auto Job Applier - Error",
                message=f"Scheduled run failed: {e}",
            )

    async def _send_report(self, report: dict):
        """Send the application report via configured notification channels."""
        success = report.get("total_success", 0)
        failed = report.get("total_failed", 0)
        total = report.get("total_attempted", 0)

        message = (
            f"Application Report - {datetime.now().strftime('%Y-%m-%d')}\n"
            f"Total: {total} | Success: {success} | Failed: {failed}\n"
            f"Success Rate: {report.get('success_rate', 'N/A')}"
        )

        if report.get("successful_applications"):
            message += "\n\nSuccessful:"
            for app in report["successful_applications"]:
                message += f"\n  ✓ {app['job']} @ {app['company']}"

        await self._notification.send(
            title="Auto Job Applier - Daily Report",
            message=message,
        )
