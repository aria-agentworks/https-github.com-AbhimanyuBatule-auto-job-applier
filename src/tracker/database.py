"""
Application Tracker - SQLite-based tracking of all applications.
Stores every application attempt, result, and status.
Prevents duplicate applications. Generates reports.
"""

import asyncio
import aiosqlite
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from src.core.config import config, PROJECT_ROOT
from src.portals.base import ApplicationResult, JobListing

logger = logging.getLogger("tracker.db")


class ApplicationTracker:
    """Tracks all job applications in a SQLite database."""

    def __init__(self):
        db_path = config.get("database", "path", default="data/applications.db")
        self._db_path = PROJECT_ROOT / db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db: Optional[aiosqlite.Connection] = None

    async def initialize(self):
        """Create database and tables."""
        self._db = await aiosqlite.connect(str(self._db_path))
        await self._db.execute("PRAGMA journal_mode=WAL")

        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                portal TEXT NOT NULL,
                job_id TEXT NOT NULL,
                job_title TEXT NOT NULL,
                company TEXT NOT NULL,
                location TEXT DEFAULT '',
                salary_range TEXT DEFAULT '',
                job_url TEXT DEFAULT '',
                match_score INTEGER DEFAULT 0,
                status TEXT DEFAULT 'applied',  -- applied, failed, duplicate, skipped
                steps_completed INTEGER DEFAULT 0,
                error_message TEXT DEFAULT '',
                screenshot_path TEXT DEFAULT '',
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(portal, job_id)
            );

            CREATE TABLE IF NOT EXISTS job_listings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                portal TEXT NOT NULL,
                job_id TEXT NOT NULL,
                title TEXT NOT NULL,
                company TEXT NOT NULL,
                location TEXT DEFAULT '',
                salary_range TEXT DEFAULT '',
                experience_required TEXT DEFAULT '',
                job_type TEXT DEFAULT '',
                work_mode TEXT DEFAULT '',
                description TEXT DEFAULT '',
                required_skills TEXT DEFAULT '',
                listing_url TEXT DEFAULT '',
                apply_url TEXT DEFAULT '',
                match_score INTEGER DEFAULT 0,
                discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(portal, job_id)
            );

            CREATE TABLE IF NOT EXISTS daily_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL UNIQUE,
                total_discovered INTEGER DEFAULT 0,
                total_applied INTEGER DEFAULT 0,
                total_success INTEGER DEFAULT 0,
                total_failed INTEGER DEFAULT 0,
                portals_used TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS run_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                status TEXT DEFAULT 'running',  -- running, completed, error
                total_applied INTEGER DEFAULT 0,
                total_success INTEGER DEFAULT 0,
                error_message TEXT DEFAULT '',
                details TEXT DEFAULT ''
            );

            CREATE INDEX IF NOT EXISTS idx_applications_portal ON applications(portal);
            CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);
            CREATE INDEX IF NOT EXISTS idx_applications_date ON applications(applied_at);
            CREATE INDEX IF NOT EXISTS idx_listings_portal ON job_listings(portal);
        """)

        await self._db.commit()
        logger.info(f"Database initialized: {self._db_path}")

    async def close(self):
        """Close database connection."""
        if self._db:
            await self._db.close()

    # ── Application Tracking ────────────────────────────────────

    async def record_application(self, result: ApplicationResult, job: JobListing = None) -> int:
        """Record an application attempt."""
        try:
            await self._db.execute(
                """INSERT OR REPLACE INTO applications 
                   (portal, job_id, job_title, company, location, salary_range, 
                    job_url, match_score, status, steps_completed, error_message, 
                    screenshot_path, applied_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    result.portal,
                    result.job_id,
                    result.job_title,
                    result.company,
                    job.location if job else "",
                    job.salary_range if job else "",
                    job.listing_url if job else "",
                    job.match_score if job else 0,
                    "applied" if result.success else "failed",
                    result.steps_completed,
                    result.error,
                    result.screenshot_path,
                    result.timestamp or datetime.now().isoformat(),
                ),
            )
            await self._db.commit()
            return self._db.total_changes
        except Exception as e:
            logger.error(f"Failed to record application: {e}")
            return 0

    async def is_already_applied(self, portal: str, job_id: str) -> bool:
        """Check if we already applied to this job."""
        async with self._db.execute(
            "SELECT id FROM applications WHERE portal = ? AND job_id = ? AND status = 'applied'",
            (portal, job_id),
        ) as cursor:
            row = await cursor.fetchone()
            return row is not None

    async def record_job_listing(self, job: JobListing):
        """Save a discovered job listing."""
        try:
            skills_str = ", ".join(job.required_skills) if job.required_skills else ""
            await self._db.execute(
                """INSERT OR IGNORE INTO job_listings 
                   (portal, job_id, title, company, location, salary_range,
                    experience_required, job_type, work_mode, description,
                    required_skills, listing_url, apply_url, match_score)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    job.portal, job.job_id, job.title, job.company,
                    job.location, job.salary_range, job.experience_required,
                    job.job_type, job.work_mode, job.description,
                    skills_str, job.listing_url, job.apply_url, job.match_score,
                ),
            )
            await self._db.commit()
        except Exception as e:
            logger.error(f"Failed to record listing: {e}")

    # ── Statistics ──────────────────────────────────────────────

    async def get_today_stats(self) -> dict:
        """Get today's application statistics."""
        today = datetime.now().strftime("%Y-%m-%d")
        async with self._db.execute(
            """SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status='applied' THEN 1 ELSE 0 END) as success,
                SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) as failed
               FROM applications 
               WHERE DATE(applied_at) = ?""",
            (today,),
        ) as cursor:
            row = await cursor.fetchone()
            return {
                "date": today,
                "total": row[0] or 0,
                "success": row[1] or 0,
                "failed": row[2] or 0,
            }

    async def get_total_stats(self) -> dict:
        """Get all-time statistics."""
        async with self._db.execute(
            """SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status='applied' THEN 1 ELSE 0 END) as success,
                SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) as failed,
                COUNT(DISTINCT company) as unique_companies,
                COUNT(DISTINCT portal) as portals_used
               FROM applications"""
        ) as cursor:
            row = await cursor.fetchone()
            return {
                "total": row[0] or 0,
                "success": row[1] or 0,
                "failed": row[2] or 0,
                "unique_companies": row[3] or 0,
                "portals_used": row[4] or 0,
            }

    async def get_recent_applications(self, limit: int = 20) -> list[dict]:
        """Get recent applications."""
        async with self._db.execute(
            """SELECT portal, job_title, company, status, applied_at, match_score
               FROM applications 
               ORDER BY applied_at DESC 
               LIMIT ?""",
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "portal": row[0],
                    "job_title": row[1],
                    "company": row[2],
                    "status": row[3],
                    "applied_at": row[4],
                    "match_score": row[5],
                }
                for row in rows
            ]

    async def get_portal_stats(self) -> list[dict]:
        """Get per-portal statistics."""
        async with self._db.execute(
            """SELECT portal,
                COUNT(*) as total,
                SUM(CASE WHEN status='applied' THEN 1 ELSE 0 END) as success,
                SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) as failed
               FROM applications
               GROUP BY portal"""
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                {"portal": r[0], "total": r[1], "success": r[2], "failed": r[3]}
                for r in rows
            ]

    async def get_weekly_trend(self) -> list[dict]:
        """Get application count per day for the last 7 days."""
        week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        async with self._db.execute(
            """SELECT DATE(applied_at) as day, COUNT(*) as count,
                SUM(CASE WHEN status='applied' THEN 1 ELSE 0 END) as success
               FROM applications
               WHERE DATE(applied_at) >= ?
               GROUP BY DATE(applied_at)
               ORDER BY day""",
            (week_ago,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [{"date": r[0], "total": r[1], "success": r[2]} for r in rows]

    # ── Run Logging ─────────────────────────────────────────────

    async def start_run(self) -> int:
        """Log the start of an automation run."""
        cursor = await self._db.execute(
            "INSERT INTO run_log (started_at) VALUES (?)",
            (datetime.now().isoformat(),),
        )
        await self._db.commit()
        return cursor.lastrowid

    async def end_run(self, run_id: int, total_applied: int, total_success: int, error: str = ""):
        """Log the end of an automation run."""
        status = "error" if error else "completed"
        await self._db.execute(
            """UPDATE run_log 
               SET completed_at=?, status=?, total_applied=?, total_success=?, error_message=?
               WHERE id=?""",
            (datetime.now().isoformat(), status, total_applied, total_success, error, run_id),
        )
        await self._db.commit()

    async def update_daily_stats(self):
        """Update the daily stats summary."""
        today = datetime.now().strftime("%Y-%m-%d")
        stats = await self.get_today_stats()

        async with self._db.execute(
            "SELECT id FROM daily_stats WHERE date = ?", (today,)
        ) as cursor:
            exists = await cursor.fetchone()

        if exists:
            await self._db.execute(
                """UPDATE daily_stats SET 
                   total_discovered=?, total_applied=?, total_success=?, total_failed=?
                   WHERE date=?""",
                (0, stats["total"], stats["success"], stats["failed"], today),
            )
        else:
            await self._db.execute(
                """INSERT INTO daily_stats (date, total_applied, total_success, total_failed)
                   VALUES (?, ?, ?, ?)""",
                (today, stats["total"], stats["success"], stats["failed"]),
            )

        await self._db.commit()
