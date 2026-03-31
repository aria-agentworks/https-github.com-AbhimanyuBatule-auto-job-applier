"""
Google Sheets Reporter - Syncs application data to a Google Sheet.

Gives you a live, shareable dashboard of every application:
- When you applied
- Which portal
- Job title, company, location
- Status (applied/failed)
- Match score
- Error details (if any)

Uses a Google Service Account (free) to write to a shared Google Sheet.
Falls back to CSV export if Sheets creds aren't configured.
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.core.config import config, PROJECT_ROOT

logger = logging.getLogger("tracker.sheets")

CREDS_PATH = PROJECT_ROOT / "data" / "google_sheets_creds.json"
CSV_EXPORT_PATH = PROJECT_ROOT / "data" / "applications_export.csv"
DAILY_REPORTS_DIR = PROJECT_ROOT / "data" / "daily_reports"

# Sheet column headers
HEADERS = [
    "Timestamp",
    "Date",
    "Portal",
    "Job Title",
    "Company",
    "Location",
    "Salary Range",
    "Match Score",
    "Status",
    "Steps Completed",
    "Error",
    "Job URL",
    "Screenshot",
]


class GoogleSheetsReporter:
    """
    Syncs application tracking data to Google Sheets.
    Provides a real-time view of all applications in a spreadsheet.
    """

    def __init__(self):
        self._sheet_id = os.environ.get("GOOGLE_SHEET_ID", "") or config.get(
            "reporting", "google_sheets", "sheet_id", default=""
        )
        self._creds_path = CREDS_PATH
        self._client = None
        self._sheet = None
        self._available = False

    async def initialize(self) -> bool:
        """Initialize Google Sheets connection. Returns True if available."""
        if not self._sheet_id:
            logger.info("Google Sheet ID not configured, Sheets sync disabled")
            return False

        if not self._creds_path.exists():
            logger.info("Google Sheets credentials not found, Sheets sync disabled")
            return False

        try:
            import gspread
            from google.oauth2.service_account import Credentials

            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ]
            creds = Credentials.from_service_account_file(
                str(self._creds_path), scopes=scopes
            )
            self._client = gspread.authorize(creds)
            self._sheet = self._client.open_by_key(self._sheet_id)
            self._available = True

            # Ensure headers exist on the main worksheet
            await self._ensure_headers()

            logger.info("Google Sheets connected successfully")
            return True

        except ImportError:
            logger.warning("gspread not installed. Run: pip install gspread google-auth")
            return False
        except Exception as e:
            logger.error(f"Google Sheets init error: {e}")
            return False

    async def _ensure_headers(self):
        """Ensure the first row has headers."""
        try:
            ws = self._sheet.sheet1
            existing = await asyncio.to_thread(ws.row_values, 1)
            if not existing or existing != HEADERS:
                await asyncio.to_thread(ws.update, "A1", [HEADERS])
                # Format header row (bold, frozen)
                await asyncio.to_thread(
                    ws.format, "A1:M1", {
                        "textFormat": {"bold": True},
                        "backgroundColor": {"red": 0.2, "green": 0.4, "blue": 0.8},
                        "horizontalAlignment": "CENTER",
                    }
                )
                # Freeze header row
                await asyncio.to_thread(ws.freeze, rows=1)
                logger.info("Headers set up on Google Sheet")
        except Exception as e:
            logger.warning(f"Could not set headers: {e}")

    async def append_application(
        self,
        portal: str,
        job_id: str,
        job_title: str,
        company: str,
        location: str = "",
        salary_range: str = "",
        match_score: int = 0,
        status: str = "applied",
        steps_completed: int = 0,
        error: str = "",
        job_url: str = "",
        screenshot_path: str = "",
    ):
        """Append a single application row to the Google Sheet."""
        if not self._available:
            return

        now = datetime.now()
        row = [
            now.strftime("%Y-%m-%d %H:%M:%S"),
            now.strftime("%Y-%m-%d"),
            portal.capitalize(),
            job_title,
            company,
            location,
            salary_range,
            str(match_score),
            "✅ Applied" if status == "applied" else "❌ Failed",
            str(steps_completed),
            error[:200] if error else "",
            job_url,
            screenshot_path,
        ]

        try:
            await asyncio.to_thread(
                self._sheet.sheet1.append_row, row,
                value_input_option="USER_ENTERED",
            )
            logger.debug(f"Sheet row added: {job_title} @ {company}")
        except Exception as e:
            logger.warning(f"Sheet append error: {e}")

    async def sync_from_database(self, db_path: str = None):
        """
        Full sync: read all applications from SQLite and write to Sheet.
        Used for initial population or recovery.
        """
        if not self._available:
            logger.info("Sheets not available, skipping sync")
            return

        import aiosqlite

        db_file = db_path or str(PROJECT_ROOT / "data" / "applications.db")
        if not Path(db_file).exists():
            logger.warning("Database not found for sheet sync")
            return

        try:
            async with aiosqlite.connect(db_file) as db:
                async with db.execute(
                    """SELECT portal, job_id, job_title, company, location, 
                              salary_range, match_score, status, steps_completed,
                              error_message, job_url, screenshot_path, applied_at
                       FROM applications
                       ORDER BY applied_at DESC"""
                ) as cursor:
                    rows = await cursor.fetchall()

            if not rows:
                logger.info("No applications to sync")
                return

            # Build sheet data
            sheet_rows = []
            for r in rows:
                applied_at = r[12] or ""
                date_str = applied_at[:10] if applied_at else ""
                sheet_rows.append([
                    applied_at,
                    date_str,
                    (r[0] or "").capitalize(),
                    r[2] or "",          # job_title
                    r[3] or "",          # company
                    r[4] or "",          # location
                    r[5] or "",          # salary_range
                    str(r[6] or 0),      # match_score
                    "✅ Applied" if r[7] == "applied" else "❌ Failed",
                    str(r[8] or 0),      # steps_completed
                    (r[9] or "")[:200],  # error_message
                    r[10] or "",         # job_url
                    r[11] or "",         # screenshot_path
                ])

            # Clear existing data (keep headers) and write fresh
            ws = self._sheet.sheet1
            await asyncio.to_thread(ws.clear)
            await asyncio.to_thread(
                ws.update, "A1", [HEADERS] + sheet_rows,
                value_input_option="USER_ENTERED",
            )

            # Re-apply header formatting
            await asyncio.to_thread(
                ws.format, "A1:M1", {
                    "textFormat": {"bold": True},
                    "backgroundColor": {"red": 0.2, "green": 0.4, "blue": 0.8},
                    "horizontalAlignment": "CENTER",
                }
            )
            await asyncio.to_thread(ws.freeze, rows=1)

            # Auto-resize columns
            try:
                await asyncio.to_thread(ws.columns_auto_resize, 0, len(HEADERS) - 1)
            except Exception:
                pass

            logger.info(f"Synced {len(sheet_rows)} applications to Google Sheet")

        except Exception as e:
            logger.error(f"Sheet sync error: {e}")

    async def create_daily_summary_sheet(self):
        """
        Create/update a 'Daily Summary' worksheet with aggregated stats.
        """
        if not self._available:
            return

        try:
            # Get or create the summary worksheet
            try:
                summary_ws = await asyncio.to_thread(self._sheet.worksheet, "Daily Summary")
            except Exception:
                summary_ws = await asyncio.to_thread(
                    self._sheet.add_worksheet,
                    title="Daily Summary", rows=100, cols=10,
                )

            import aiosqlite
            db_file = str(PROJECT_ROOT / "data" / "applications.db")
            if not Path(db_file).exists():
                return

            async with aiosqlite.connect(db_file) as db:
                # Get daily aggregates
                async with db.execute(
                    """SELECT DATE(applied_at) as day,
                              COUNT(*) as total,
                              SUM(CASE WHEN status='applied' THEN 1 ELSE 0 END) as success,
                              SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) as failed,
                              COUNT(DISTINCT company) as companies,
                              COUNT(DISTINCT portal) as portals,
                              ROUND(AVG(match_score), 1) as avg_score
                       FROM applications
                       GROUP BY DATE(applied_at)
                       ORDER BY day DESC"""
                ) as cursor:
                    daily_rows = await cursor.fetchall()

            if not daily_rows:
                return

            summary_headers = [
                "Date", "Total", "Success", "Failed",
                "Success Rate", "Companies", "Portals", "Avg Match Score"
            ]

            summary_data = []
            for r in daily_rows:
                total = r[1] or 0
                success = r[2] or 0
                rate = f"{(success / max(total, 1)) * 100:.0f}%"
                summary_data.append([
                    r[0], str(total), str(success), str(r[3] or 0),
                    rate, str(r[4] or 0), str(r[5] or 0), str(r[6] or 0),
                ])

            await asyncio.to_thread(summary_ws.clear)
            await asyncio.to_thread(
                summary_ws.update, "A1", [summary_headers] + summary_data,
                value_input_option="USER_ENTERED",
            )
            await asyncio.to_thread(
                summary_ws.format, "A1:H1", {
                    "textFormat": {"bold": True},
                    "backgroundColor": {"red": 0.15, "green": 0.65, "blue": 0.35},
                    "horizontalAlignment": "CENTER",
                }
            )
            await asyncio.to_thread(summary_ws.freeze, rows=1)

            logger.info("Daily Summary sheet updated")

        except Exception as e:
            logger.warning(f"Summary sheet error: {e}")


class CSVExporter:
    """
    Fallback CSV exporter - always works, no API keys needed.
    Exports the full applications table to a CSV file.
    """

    def __init__(self):
        self._csv_path = CSV_EXPORT_PATH
        self._daily_dir = DAILY_REPORTS_DIR
        self._daily_dir.mkdir(parents=True, exist_ok=True)

    async def export_all(self, db_path: str = None) -> str:
        """
        Export all applications from SQLite to CSV.
        Returns the CSV file path.
        """
        import csv
        import aiosqlite

        db_file = db_path or str(PROJECT_ROOT / "data" / "applications.db")
        if not Path(db_file).exists():
            logger.warning("Database not found for CSV export")
            return ""

        try:
            async with aiosqlite.connect(db_file) as db:
                async with db.execute(
                    """SELECT applied_at, portal, job_title, company, location,
                              salary_range, match_score, status, steps_completed,
                              error_message, job_url
                       FROM applications
                       ORDER BY applied_at DESC"""
                ) as cursor:
                    rows = await cursor.fetchall()

            csv_headers = [
                "Applied At", "Date", "Portal", "Job Title", "Company",
                "Location", "Salary Range", "Match Score", "Status",
                "Steps Completed", "Error", "Job URL",
            ]

            with open(self._csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(csv_headers)
                for r in rows:
                    applied_at = r[0] or ""
                    date_str = applied_at[:10] if applied_at else ""
                    writer.writerow([
                        applied_at,
                        date_str,
                        (r[1] or "").capitalize(),
                        r[2] or "",
                        r[3] or "",
                        r[4] or "",
                        r[5] or "",
                        str(r[6] or 0),
                        "Applied" if r[7] == "applied" else "Failed",
                        str(r[8] or 0),
                        (r[9] or "")[:200],
                        r[10] or "",
                    ])

            logger.info(f"Exported {len(rows)} applications to {self._csv_path}")

            # Also save a dated copy
            today = datetime.now().strftime("%Y-%m-%d")
            daily_path = self._daily_dir / f"applications_{today}.csv"
            import shutil
            shutil.copy2(str(self._csv_path), str(daily_path))
            logger.info(f"Daily report saved: {daily_path}")

            return str(self._csv_path)

        except Exception as e:
            logger.error(f"CSV export error: {e}")
            return ""

    async def export_today_summary(self) -> str:
        """Export just today's applications to a compact summary."""
        import csv
        import aiosqlite

        db_file = str(PROJECT_ROOT / "data" / "applications.db")
        if not Path(db_file).exists():
            return ""

        today = datetime.now().strftime("%Y-%m-%d")
        summary_path = self._daily_dir / f"summary_{today}.csv"

        try:
            async with aiosqlite.connect(db_file) as db:
                async with db.execute(
                    """SELECT applied_at, portal, job_title, company, status
                       FROM applications
                       WHERE DATE(applied_at) = ?
                       ORDER BY applied_at DESC""",
                    (today,),
                ) as cursor:
                    rows = await cursor.fetchall()

            with open(summary_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Time", "Portal", "Job Title", "Company", "Status"])
                for r in rows:
                    time_str = (r[0] or "")[-8:]  # Just the time part
                    writer.writerow([
                        time_str,
                        (r[1] or "").capitalize(),
                        r[2] or "",
                        r[3] or "",
                        "✅" if r[4] == "applied" else "❌",
                    ])

            return str(summary_path)

        except Exception as e:
            logger.error(f"Today summary export error: {e}")
            return ""
