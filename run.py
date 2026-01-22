#!/usr/bin/env python3
"""
Portfolio Monitor Entry Point

This script provides a clean entry point for running the portfolio monitor
using the refactored modular architecture.
"""
import logging
import os
import sys

from src.monitor import PortfolioMonitor

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Main entry point for portfolio monitor."""
    try:
        # Get Gmail credentials from environment (optional)
        gmail_creds = None
        email_sender = os.getenv('EMAIL_SENDER')
        email_password = os.getenv('EMAIL_PASSWORD')

        if email_sender and email_password:
            gmail_creds = {
                'email': email_sender,
                'password': email_password
            }

        # Get Anthropic API key from environment (optional)
        anthropic_key = os.getenv('ANTHROPIC_API_KEY')

        # Initialize and run monitor
        monitor = PortfolioMonitor(
            data_dir="data",
            gmail_credentials=gmail_creds,
            anthropic_api_key=anthropic_key
        )

        monitor.run()

    except KeyboardInterrupt:
        logger.info("\nMonitor interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
