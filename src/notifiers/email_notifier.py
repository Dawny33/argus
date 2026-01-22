#!/usr/bin/env python3
"""
Email Notifier Module
Sends email notifications for portfolio changes.
"""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Optional

# Setup module-level logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def _clean_credential(value: str) -> str:
    """
    Force-clean credentials by removing all whitespace and non-ASCII chars.

    Args:
        value: The credential string to clean

    Returns:
        Cleaned credential string with only ASCII characters
    """
    # Remove ALL whitespace including non-breaking spaces (\xa0)
    cleaned = ''.join(value.split())
    # Force ASCII encoding to strip any remaining non-ASCII characters
    return cleaned.encode('ascii', 'ignore').decode('ascii')


class EmailNotifier:
    """
    Sends email notifications using SMTP.
    Handles authentication and message formatting.
    """

    def __init__(self, smtp_server: str = "smtp.gmail.com",
                 smtp_port: int = 587,
                 sender: Optional[str] = None,
                 password: Optional[str] = None,
                 recipient: Optional[str] = None):
        """
        Initialize the EmailNotifier.

        Args:
            smtp_server: SMTP server address (default: Gmail)
            smtp_port: SMTP port (default: 587 for TLS)
            sender: Email sender address (cleaned automatically)
            password: Email password/app password (cleaned automatically)
            recipient: Email recipient address (defaults to sender if not provided)
        """
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port

        # Clean credentials if provided
        self.sender = _clean_credential(sender) if sender else ""
        self.password = _clean_credential(password) if password else ""
        self.recipient = _clean_credential(recipient) if recipient else self.sender

    def send_email(self, subject: str, body: str,
                   sender: Optional[str] = None,
                   password: Optional[str] = None,
                   recipient: Optional[str] = None) -> bool:
        """
        Send email notification using MIME.

        Args:
            subject: Email subject line
            body: Email body text (plain text)
            sender: Override default sender (optional)
            password: Override default password (optional)
            recipient: Override default recipient (optional)

        Returns:
            True if email was sent successfully, False otherwise
        """
        # Use provided credentials or fall back to instance defaults
        email_sender = _clean_credential(sender) if sender else self.sender
        email_password = _clean_credential(password) if password else self.password
        email_recipient = _clean_credential(recipient) if recipient else self.recipient

        # Default recipient to sender if not specified
        if not email_recipient:
            email_recipient = email_sender

        if not email_sender or not email_password:
            logger.warning("Email credentials not found. Cannot send email.")
            return False

        # Build MIME message
        msg = MIMEMultipart()
        msg['From'] = email_sender
        msg['To'] = email_recipient
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        try:
            # Connect to SMTP server and send
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(email_sender, email_password)
                server.send_message(msg)

            logger.info(f"Email sent successfully to {email_recipient}")
            return True

        except smtplib.SMTPAuthenticationError:
            logger.error("Email authentication failed. Check sender credentials.")
            return False

        except Exception as e:
            logger.error(f"Error sending email: {e}")
            return False
