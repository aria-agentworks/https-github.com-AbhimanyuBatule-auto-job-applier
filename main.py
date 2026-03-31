#!/usr/bin/env python3
"""
Auto Job Applier - Main Entry Point
Apply to 10+ jobs daily, completely hands-free.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.cli import cli

if __name__ == "__main__":
    cli()
