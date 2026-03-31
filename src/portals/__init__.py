"""
Portals module — adapters for each job portal.
Each sub-package implements BasePortalAdapter for portal-specific automation.

Supported portals:
- LinkedIn (Easy Apply + External)
- Naukri.com (Quick Apply + Chatbot)
- Wellfound (Startup jobs)
- Instahyre (AI-matched opportunities)
- Generic Career Page (works on ANY website via AI navigation)

To add a new portal, create a sub-package with an adapter.py
that extends BasePortalAdapter (see base.py for the interface).
"""

from src.portals.base import BasePortalAdapter, JobListing, ApplicationResult

__all__ = ["BasePortalAdapter", "JobListing", "ApplicationResult"]