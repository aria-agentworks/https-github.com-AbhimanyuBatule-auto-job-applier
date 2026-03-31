"""
AI module — provider-agnostic AI engine with rate limiting,
retry logic, and provider fallback chain.
"""

from src.ai.engine import AIEngine

__all__ = ["AIEngine"]