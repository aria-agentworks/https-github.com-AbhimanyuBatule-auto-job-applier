"""
Notification Manager - Sends notifications via multiple channels.
Desktop, Telegram, Email.
"""

import logging
from src.core.config import config

logger = logging.getLogger("utils.notifications")


class NotificationManager:
    """Manages notifications across channels."""

    def __init__(self):
        self._notifications_enabled = config.get("notifications", "enabled", default=True)

    async def send(self, title: str, message: str):
        """Send notification via all enabled channels."""
        if not self._notifications_enabled:
            return

        # Desktop
        if config.get("notifications", "desktop", "enabled", default=True):
            await self._send_desktop(title, message)

        # Telegram
        if config.get("notifications", "telegram", "enabled", default=False):
            await self._send_telegram(title, message)

        # Email
        if config.get("notifications", "email", "enabled", default=False):
            await self._send_email(title, message)

    async def _send_desktop(self, title: str, message: str):
        """Send desktop notification."""
        try:
            from plyer import notification
            notification.notify(
                title=title,
                message=message[:256],  # Limit length
                timeout=10,
            )
        except Exception as e:
            logger.debug(f"Desktop notification failed: {e}")

    async def _send_telegram(self, title: str, message: str):
        """Send Telegram notification."""
        try:
            import httpx
            bot_token = config.get("notifications", "telegram", "bot_token")
            chat_id = config.get("notifications", "telegram", "chat_id")

            if not bot_token or not chat_id:
                return

            text = f"*{title}*\n\n{message}"
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
                )
        except Exception as e:
            logger.debug(f"Telegram notification failed: {e}")

    async def _send_email(self, title: str, message: str):
        """Send email notification."""
        try:
            import smtplib
            from email.mime.text import MIMEText

            smtp_server = config.get("notifications", "email", "smtp_server")
            smtp_port = config.get("notifications", "email", "smtp_port", default=587)
            sender = config.get("notifications", "email", "sender_email")
            password = config.get("notifications", "email", "sender_password")
            recipient = config.get("notifications", "email", "recipient_email")

            if not all([smtp_server, sender, password, recipient]):
                return

            msg = MIMEText(message)
            msg["Subject"] = title
            msg["From"] = sender
            msg["To"] = recipient

            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(sender, password)
                server.send_message(msg)

            logger.info("Email notification sent")
        except Exception as e:
            logger.debug(f"Email notification failed: {e}")
