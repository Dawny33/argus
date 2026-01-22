#!/usr/bin/env python3
"""
Gmail Portfolio Fetcher Module
Fetches mutual fund portfolio disclosure emails from Gmail.
AMCs send monthly portfolio disclosure emails with download links.
"""

import logging
import imaplib
import email
from datetime import datetime, timedelta
from typing import List, Tuple, Optional

from bs4 import BeautifulSoup

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


class GmailPortfolioFetcher:
    """
    Fetches mutual fund portfolio disclosure emails from Gmail.
    AMCs send monthly portfolio disclosure emails with download links.
    """

    def __init__(self, email_address: str, email_password: str):
        """
        Initialize Gmail fetcher with credentials.

        Args:
            email_address: Gmail address
            email_password: App password for Gmail
        """
        # Clean credentials to remove whitespace and non-ASCII characters
        self.email_address = _clean_credential(email_address)
        self.email_password = _clean_credential(email_password)
        self.imap_server = "imap.gmail.com"

    def connect(self) -> Optional[imaplib.IMAP4_SSL]:
        """
        Connect to Gmail via IMAP.

        Returns:
            IMAP4_SSL connection object, or None if connection failed
        """
        try:
            mail = imaplib.IMAP4_SSL(self.imap_server)
            mail.login(self.email_address, self.email_password)
            return mail
        except Exception as e:
            logger.error(f"Gmail connection failed: {e}")
            return None

    def search_portfolio_emails(self, amc_name: str, fund_name: str = "",
                                days_back: int = 60) -> List[Tuple[str, str]]:
        """
        Search for portfolio disclosure emails from specific AMC.

        Args:
            amc_name: Name of AMC (e.g., "Bandhan", "Tata", "Quant")
            fund_name: Optional specific fund name
            days_back: How many days back to search

        Returns:
            List of tuples: (email_subject, email_body_html)
        """
        mail = self.connect()
        if not mail:
            return []

        try:
            mail.select('INBOX')

            # Calculate date for search
            since_date = (datetime.now() - timedelta(days=days_back)).strftime("%d-%b-%Y")

            # Build search query
            search_terms = [
                f'FROM "{amc_name}"',
                'SUBJECT "portfolio"',
                f'SINCE {since_date}'
            ]

            search_query = f'({" ".join(search_terms)})'
            logger.info(f"  Gmail search: {search_query}")

            # Search for emails
            status, messages = mail.search(None, search_query)

            if status != 'OK':
                logger.error(f"  Gmail search failed")
                return []

            email_ids = messages[0].split()
            results = []

            logger.info(f"  Found {len(email_ids)} matching emails")

            # Fetch and parse emails (most recent first)
            for email_id in reversed(email_ids[-10:]):  # Last 10 emails
                status, msg_data = mail.fetch(email_id, '(RFC822)')

                if status != 'OK':
                    continue

                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        subject = msg['subject']

                        # Extract email body
                        body = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                content_type = part.get_content_type()
                                if content_type == "text/html":
                                    body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                                    break
                                elif content_type == "text/plain" and not body:
                                    body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                        else:
                            body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')

                        # Check if fund name matches (if specified)
                        if fund_name:
                            if fund_name.lower() not in subject.lower() and fund_name.lower() not in body.lower():
                                continue

                        results.append((subject, body))

            mail.close()
            mail.logout()

            return results

        except Exception as e:
            logger.error(f"  Gmail search error: {e}")
            try:
                mail.close()
                mail.logout()
            except:
                pass
            return []

    def extract_download_links(self, email_body: str, fund_name: str = "") -> List[Tuple[str, str]]:
        """
        Extract Excel/XLS download links from email body.

        Args:
            email_body: HTML or plain text email body
            fund_name: Optional fund name to prioritize matching links

        Returns:
            List of tuples: (link_text, url)
        """
        links = []

        # Parse HTML if present
        soup = BeautifulSoup(email_body, 'html.parser')

        # Find all links
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            link_text = link.get_text().strip()

            # Skip if no valid URL
            if not href.startswith('http'):
                continue

            # Look for portfolio-related links:
            # 1. Direct Excel links (.xls, .xlsx)
            # 2. CAMS delivery links (camsonline.com)
            # 3. Links with "portfolio", "disclosure", "download" in URL or text
            # 4. Links with fund names in text (e.g., "Bandhan ELSS Tax saver Fund")

            is_portfolio_link = any([
                '.xls' in href.lower() or '.xlsx' in href.lower(),
                'camsonline.com' in href.lower() and 'delivery' in href.lower(),
                any(keyword in href.lower() for keyword in ['portfolio', 'disclosure', 'download']),
                any(keyword in link_text.lower() for keyword in ['portfolio', 'disclosure', 'elss', 'fund', 'scheme'])
            ])

            if is_portfolio_link:
                # Exclude image links
                if not any(ext in href.lower() for ext in ['.jpg', '.jpeg', '.png', '.gif']):
                    links.append((link_text, href))

        # Remove duplicates while preserving order
        seen = set()
        unique_links = []
        for text, url in links:
            if url not in seen:
                seen.add(url)
                unique_links.append((text, url))

        # If fund_name specified, prioritize matching links
        if fund_name:
            matching_links = [(t, u) for t, u in unique_links if fund_name.lower() in t.lower()]
            non_matching = [(t, u) for t, u in unique_links if fund_name.lower() not in t.lower()]
            return matching_links + non_matching

        return unique_links

    def fetch_portfolio_from_email(self, amc_name: str, fund_name: str = "",
                                    days_back: int = 60) -> Optional[str]:
        """
        Find and return the download URL for the most recent portfolio disclosure.

        Args:
            amc_name: Name of AMC
            fund_name: Optional fund name
            days_back: Days to search back

        Returns:
            Download URL for portfolio Excel file, or None
        """
        logger.info(f"  Searching Gmail for {amc_name} portfolio emails...")

        emails = self.search_portfolio_emails(amc_name, fund_name, days_back)

        if not emails:
            logger.warning(f"  No portfolio emails found from {amc_name}")
            return None

        # Try to extract download link from most recent email
        for subject, body in emails:
            logger.info(f"  Checking email: {subject[:80]}")

            download_links = self.extract_download_links(body, fund_name)

            if download_links:
                logger.info(f"  Found {len(download_links)} portfolio links")
                # Return the first valid link (prioritized by fund_name if specified)
                for link_text, url in download_links:
                    logger.info(f"  Link: '{link_text}' -> {url[:80]}...")
                    return url

        logger.warning(f"  No download links found in {amc_name} emails")
        return None
