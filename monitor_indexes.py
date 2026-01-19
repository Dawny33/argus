#!/usr/bin/env python3
"""
Index Constituent Monitor - Modular Version
Fetches index constituents from official sources and sends email notifications.
"""

import json
import logging
import os
import re
import smtplib
import imaplib
import email
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple
import time

import requests
from bs4 import BeautifulSoup
import pandas as pd
from io import BytesIO
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from anthropic import Anthropic

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MFChangeDetector:
    """
    Detect changes in mutual fund holdings.

    Tracks:
    - New additions (stocks not in previous holdings)
    - Complete exits (stocks removed from portfolio)
    - Significant increases (≥threshold% increase)
    - Significant decreases (≥threshold% decrease)
    """

    def __init__(self, threshold: float = 0.5):
        """
        Args:
            threshold: Minimum percentage point change to report (default: 0.5)
        """
        self.threshold = threshold

    def detect_changes(self, previous: Dict[str, float],
                       current: Dict[str, float]) -> Dict[str, List]:
        """
        Compare previous and current holdings.

        Args:
            previous: Previous month's holdings {stock: %}
            current: Current month's holdings {stock: %}

        Returns:
            Dict with keys:
            - 'additions': [(stock, pct), ...]
            - 'exits': [(stock, old_pct), ...]
            - 'increases': [(stock, old_pct, new_pct, change), ...]
            - 'decreases': [(stock, old_pct, new_pct, change), ...]
        """

        changes = {
            'additions': [],
            'exits': [],
            'increases': [],
            'decreases': []
        }

        prev_stocks = set(previous.keys())
        curr_stocks = set(current.keys())

        # New additions (not in previous)
        for stock in curr_stocks - prev_stocks:
            changes['additions'].append((stock, current[stock]))

        # Complete exits (not in current)
        for stock in prev_stocks - curr_stocks:
            changes['exits'].append((stock, previous[stock]))

        # Rebalances (present in both)
        for stock in prev_stocks & curr_stocks:
            old_pct = previous[stock]
            new_pct = current[stock]
            change = new_pct - old_pct

            # Only report if change meets threshold
            if abs(change) >= self.threshold:
                entry = (stock, old_pct, new_pct, change)

                if change > 0:
                    changes['increases'].append(entry)
                else:
                    changes['decreases'].append(entry)

        return changes

    def has_changes(self, changes: Dict[str, List]) -> bool:
        """Check if any changes were detected."""
        return any(len(v) > 0 for v in changes.values())


class GmailPortfolioFetcher:
    """
    Fetches mutual fund portfolio disclosure emails from Gmail.
    AMCs send monthly portfolio disclosure emails with download links.
    """

    @staticmethod
    def _clean_credential(value: str) -> str:
        """Force-clean credentials by removing all whitespace and non-ASCII chars."""
        # Remove ALL whitespace including non-breaking spaces (\xa0)
        cleaned = ''.join(value.split())
        # Force ASCII encoding to strip any remaining non-ASCII characters
        return cleaned.encode('ascii', 'ignore').decode('ascii')

    def __init__(self, email_address: str, email_password: str):
        """
        Initialize Gmail fetcher with credentials.

        Args:
            email_address: Gmail address
            email_password: App password for Gmail
        """
        # Clean credentials to remove whitespace and non-ASCII characters
        self.email_address = self._clean_credential(email_address)
        self.email_password = self._clean_credential(email_password)
        self.imap_server = "imap.gmail.com"

    def connect(self) -> Optional[imaplib.IMAP4_SSL]:
        """Connect to Gmail via IMAP."""
        try:
            mail = imaplib.IMAP4_SSL(self.imap_server)
            mail.login(self.email_address, self.email_password)
            return mail
        except Exception as e:
            logging.error(f"Gmail connection failed: {e}")
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
            logging.info(f"  Gmail search: {search_query}")

            # Search for emails
            status, messages = mail.search(None, search_query)

            if status != 'OK':
                logging.error(f"  Gmail search failed")
                return []

            email_ids = messages[0].split()
            results = []

            logging.info(f"  Found {len(email_ids)} matching emails")

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
            logging.error(f"  Gmail search error: {e}")
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
        logging.info(f"  Searching Gmail for {amc_name} portfolio emails...")

        emails = self.search_portfolio_emails(amc_name, fund_name, days_back)

        if not emails:
            logging.warning(f"  No portfolio emails found from {amc_name}")
            return None

        # Try to extract download link from most recent email
        for subject, body in emails:
            logging.info(f"  Checking email: {subject[:80]}")

            download_links = self.extract_download_links(body, fund_name)

            if download_links:
                logging.info(f"  Found {len(download_links)} portfolio links")
                # Return the first valid link (prioritized by fund_name if specified)
                for link_text, url in download_links:
                    logging.info(f"  Link: '{link_text}' -> {url[:80]}...")
                    return url

        logging.warning(f"  No download links found in {amc_name} emails")
        return None


class TickerResolver:
    """
    Resolves ticker symbols to company names using Claude LLM.
    Differentiates between Indian and international stocks.
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the TickerResolver.

        Args:
            api_key: Anthropic API key. If not provided, reads from ANTHROPIC_API_KEY env var.
        """
        self.api_key = api_key or os.getenv('ANTHROPIC_API_KEY')
        self.client = None

        if self.api_key:
            try:
                self.client = Anthropic(api_key=self.api_key)
                logging.info("TickerResolver initialized with Claude API")
            except Exception as e:
                logging.warning(f"Could not initialize TickerResolver: {e}")
        else:
            logging.warning("ANTHROPIC_API_KEY not found. Ticker resolution will be skipped.")

    def is_available(self) -> bool:
        """Check if the resolver is available (API key configured)."""
        return self.client is not None

    def resolve_tickers(self, diff_text: str, index_name: str) -> Dict[str, str]:
        """
        Resolve ticker symbols in the diff to company names.

        Args:
            diff_text: The diff text containing ticker symbols (e.g., "Added: + ANTO, + BOL")
            index_name: The name of the index/fund (e.g., "VXUS", "Nifty 50")

        Returns:
            Dict mapping ticker symbols to company names
            Example: {"ANTO": "Antofagasta plc", "BOL": "Boliden AB"}
        """
        if not self.is_available():
            return {}

        # Determine if this is an Indian or international index
        indian_keywords = ['nifty', 'sensex', 'bse', 'nse']
        is_indian = any(keyword in index_name.lower() for keyword in indian_keywords)

        market_context = "Indian stock market (NSE/BSE)" if is_indian else "International stock market"

        prompt = f"""Given the following portfolio changes from {index_name} (which tracks {market_context}), please identify all the ticker symbols and provide their full company names.

Diff text:
{diff_text}

Please analyze the ticker symbols and return them in the following JSON format:
{{
  "TICKER1": "Full Company Name 1",
  "TICKER2": "Full Company Name 2",
  ...
}}

Important guidelines:
1. For {market_context}, focus on stocks from that market
2. Ticker symbols are typically 1-6 characters (uppercase letters/numbers)
3. If you see numbers like "012330", these are stock codes (especially for international markets)
4. For Indian stocks, tickers are usually 1-5 uppercase letters (e.g., TCS, INFY, RELIANCE)
5. For international stocks, they can be letters with numbers (e.g., 2383, 6920)
6. Provide the most commonly known company name
7. If a ticker is ambiguous or unknown, use "Unknown Company" as the value

Return ONLY the JSON object, nothing else."""

        try:
            message = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=2048,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            response_text = message.content[0].text.strip()

            # Parse JSON response
            # Remove markdown code blocks if present
            if response_text.startswith('```'):
                lines = response_text.split('\n')
                response_text = '\n'.join(lines[1:-1])

            ticker_map = json.loads(response_text)
            logging.info(f"Resolved {len(ticker_map)} tickers for {index_name}")
            return ticker_map

        except Exception as e:
            logging.error(f"Error resolving tickers: {e}")
            return {}

    def format_with_company_names(self, tickers: List[str], ticker_map: Dict[str, str]) -> List[str]:
        """
        Format ticker list with company names.

        Args:
            tickers: List of ticker symbols
            ticker_map: Dict mapping tickers to company names

        Returns:
            List of formatted strings like "ANTO (Antofagasta plc)"
        """
        formatted = []
        for ticker in tickers:
            company_name = ticker_map.get(ticker)
            if company_name and company_name != "Unknown Company":
                formatted.append(f"{ticker} ({company_name})")
            else:
                formatted.append(ticker)
        return formatted


class IndexMonitor:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        self.config_file = self.data_dir / "config.json"
        self.state_file = self.data_dir / "previous_state.json"
        self.load_config()
        
        # Source handlers - maps source type to fetch function
        self.source_handlers = {
            'nse_api': self.fetch_from_nse,
            'nasdaq_official': self.fetch_from_nasdaq,
            'vanguard_etf': self.fetch_from_vanguard,
            'invesco_etf': self.fetch_from_invesco,
        }

        # Mutual fund source handlers
        self.mf_source_handlers = {
            'hdfc_mf': self.fetch_from_hdfc_mf,
            'ppfas_mf': self.fetch_from_ppfas_mf,
            'tata_mf': self.fetch_from_tata_mf,
            'quant_mf': self.fetch_from_quant_mf,
            'bandhan_mf': self.fetch_from_bandhan_mf,
        }

        # MF change detector
        mf_threshold = self.config.get('thresholds', {}).get('mf_percentage_change', 0.5)
        self.mf_detector = MFChangeDetector(threshold=mf_threshold)

        # Gmail portfolio fetcher (optional - only if credentials available)
        email_sender = self._clean_credential(os.getenv('EMAIL_SENDER', ''))
        email_password = self._clean_credential(os.getenv('EMAIL_PASSWORD', ''))

        self.gmail_fetcher = None
        if email_sender and email_password:
            try:
                self.gmail_fetcher = GmailPortfolioFetcher(email_sender, email_password)
                logging.info("Gmail portfolio fetcher initialized")
            except Exception as e:
                logging.warning(f"Could not initialize Gmail fetcher: {e}")

        # Initialize ticker resolver (optional - only if API key available)
        self.ticker_resolver = TickerResolver()
        if not self.ticker_resolver.is_available():
            logging.info("Ticker resolver not available. Set ANTHROPIC_API_KEY to enable company name resolution.")

    def _get_selenium_driver(self):
        """
        Create and return a headless Chrome WebDriver instance.

        Returns:
            WebDriver instance configured for headless operation
        """
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

        # Disable logging for cleaner output
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])

        # Set download directory
        download_dir = str(self.data_dir / 'temp_downloads')
        Path(download_dir).mkdir(exist_ok=True)

        prefs = {
            'download.default_directory': download_dir,
            'download.prompt_for_download': False,
            'download.directory_upgrade': True,
            'safebrowsing.enabled': False
        }
        chrome_options.add_experimental_option('prefs', prefs)

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(60)

        return driver

    def load_config(self):
        """Load configuration from config.json"""
        if self.config_file.exists():
            with open(self.config_file, 'r') as f:
                self.config = json.load(f)
        else:
            # Default configuration with index metadata
            self.config = {
                "indexes": [
                    {
                        "name": "Nifty 50",
                        "source": "nse_api",
                        "params": {"index_name": "NIFTY 50"}
                    },
                    {
                        "name": "Nifty Next 50",
                        "source": "nse_api",
                        "params": {"index_name": "NIFTY NEXT 50"}
                    },
                    {
                        "name": "Nifty Midcap 150",
                        "source": "nse_api",
                        "params": {"index_name": "NIFTY MIDCAP 150"}
                    },
                    {
                        "name": "Nifty Smallcap 250",
                        "source": "nse_api",
                        "params": {"index_name": "NIFTY SMALLCAP 250"}
                    },
                    {
                        "name": "Nasdaq 100",
                        "source": "nasdaq_official",
                        "params": {"index_symbol": "NDX"}
                    },
                    {
                        "name": "VXUS",
                        "source": "vanguard_etf",
                        "params": {"fund_id": "3369", "ticker": "VXUS"}
                    },
                    {
                        "name": "QQQM",
                        "source": "invesco_etf",
                        "params": {"ticker": "QQQM"}
                    }
                ],
                "email": {
                    "smtp_server": "smtp.gmail.com",
                    "smtp_port": 587
                }
            }
            self.save_config()
    
    def save_config(self):
        """Save configuration to config.json"""
        with open(self.config_file, 'w') as f:
            json.dump(self.config, f, indent=2)
    
    def clean_symbol(self, symbol: str) -> str:
        """Clean stock symbol"""
        return symbol.replace('\xa0', ' ').replace('\u00a0', ' ').strip()
    
    def fetch_from_nse(self, params: dict) -> Set[str]:
        """
        Fetch constituents from NSE India API.
        Params: {"index_name": "NIFTY 50"}
        """
        index_name = params.get('index_name')
        if not index_name:
            return set()

        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json',
                'Accept-Language': 'en-US,en;q=0.9',
            }

            url = f"https://www.nseindia.com/api/equity-stockIndices?index={index_name.replace(' ', '%20')}"

            session = requests.Session()
            session.get("https://www.nseindia.com", headers=headers, timeout=10)
            time.sleep(1)

            response = session.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            data = response.json()
            constituents = set()
            for item in data.get('data', []):
                symbol = item.get('symbol', '')
                # Filter out the index name itself from constituents
                if symbol and symbol != index_name:
                    constituents.add(symbol)

            return constituents

        except Exception as e:
            logger.warning(f"NSE API error for {index_name}: {e}")
            return self._fetch_nse_csv_fallback(index_name)

    def _fetch_nse_csv_fallback(self, index_name: str) -> Set[str]:
        """Fallback to NSE CSV archive."""
        try:
            import pandas as pd
            csv_url = f"https://archives.nseindia.com/content/indices/ind_{index_name.replace(' ', '').lower()}list.csv"
            df = pd.read_csv(csv_url)
            symbols = set(df.iloc[:, 2].dropna().astype(str).tolist())
            # Filter out index name
            symbols.discard(index_name)
            return symbols
        except Exception as e:
            logger.error(f"NSE CSV fallback failed for {index_name}: {e}")
            return set()
    
    def fetch_from_nasdaq(self, params: dict) -> Set[str]:
        """
        Fetch Nasdaq 100 constituents from Wikipedia.
        Params: {"index_symbol": "NDX"}
        """
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html'
        }

        try:
            wiki_url = "https://en.wikipedia.org/wiki/Nasdaq-100"
            response = requests.get(wiki_url, headers=headers, timeout=15)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')
            constituents = set()

            # Find the table with id="constituents"
            table = soup.find('table', {'id': 'constituents'})
            if not table:
                # Fallback: find wikitable with sortable class
                tables = soup.find_all('table', {'class': 'wikitable'})
                for t in tables:
                    # Look for table with "Ticker" header
                    headers_row = t.find('tr')
                    if headers_row:
                        header_text = headers_row.get_text().lower()
                        if 'ticker' in header_text or 'symbol' in header_text:
                            table = t
                            break

            if not table:
                logger.warning("Could not find Nasdaq 100 constituents table")
                return set()

            # Find the ticker column index
            header_row = table.find('tr')
            ticker_col_idx = None
            if header_row:
                header_cells = header_row.find_all(['th', 'td'])
                for idx, cell in enumerate(header_cells):
                    cell_text = cell.get_text().strip().lower()
                    if cell_text in ('ticker', 'symbol', 'ticker symbol'):
                        ticker_col_idx = idx
                        break

            if ticker_col_idx is None:
                ticker_col_idx = 1  # Default: second column

            # Extract tickers from data rows
            rows = table.find_all('tr')[1:]  # Skip header
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) > ticker_col_idx:
                    ticker_cell = cells[ticker_col_idx]
                    ticker = ticker_cell.get_text().strip()
                    # Valid ticker: 1-5 uppercase letters
                    if ticker and re.match(r'^[A-Z]{1,5}$', ticker):
                        constituents.add(ticker)

            if len(constituents) < 90:
                logger.warning(f"Nasdaq 100: Only found {len(constituents)} stocks, expected ~100")

            return constituents

        except Exception as e:
            logger.error(f"Nasdaq fetch error: {e}")
            return set()
    
    def fetch_from_vanguard(self, params: dict) -> Set[str]:
        """
        Fetch holdings from Vanguard ETF using their official API.
        Returns top 500 holdings (by weight) which covers the most significant positions.
        Params: {"ticker": "VXUS"} or {"ticker": "VTI"}
        """
        ticker = params.get('ticker', 'VXUS').upper()

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
        }

        try:
            # Vanguard API returns top 500 holdings sorted by weight
            url = f"https://investor.vanguard.com/investment-products/etfs/profile/api/{ticker}/portfolio-holding/stock"
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            data = response.json()
            constituents = set()

            # Extract holdings
            holdings = data.get('fund', {}).get('entity', [])
            total_available = data.get('size', len(holdings))

            for holding in holdings:
                ticker_symbol = holding.get('ticker', '').strip()
                if ticker_symbol and re.match(r'^[A-Z0-9./]{1,12}$', ticker_symbol):
                    constituents.add(ticker_symbol)

            if total_available > len(holdings):
                logger.info(f"Vanguard {ticker}: Tracking top {len(constituents)} of {total_available} total holdings")
            else:
                logger.info(f"Vanguard {ticker}: Fetched {len(constituents)} holdings")

            return constituents

        except requests.exceptions.HTTPError as e:
            logger.warning(f"Vanguard API HTTP error for {ticker}: {e}")
            return set()
        except Exception as e:
            logger.error(f"Vanguard API error for {ticker}: {e}")
            return set()

    def fetch_from_invesco(self, params: dict) -> Set[str]:
        """
        Fetch holdings from Invesco ETF.
        Since Invesco's website has bot protection, this uses Nasdaq 100 data
        for QQQM (which tracks the Nasdaq 100 index).
        Params: {"ticker": "QQQM"}
        """
        ticker = params.get('ticker', 'QQQM').upper()

        # QQQM tracks Nasdaq 100, so use our existing Nasdaq fetcher
        if ticker == 'QQQM':
            logger.info(f"Invesco {ticker}: Using Nasdaq 100 constituents (same underlying index)")
            return self.fetch_from_nasdaq({'index_symbol': 'NDX'})

        logger.warning(f"Invesco {ticker}: Manual CSV download required from invesco.com")
        return set()

    def fetch_from_hdfc_mf(self, params: dict) -> Dict[str, float]:
        """
        Fetch mutual fund holdings from HDFC Mutual Fund.
        Downloads and parses monthly portfolio Excel file.

        Args:
            params: Dict containing:
                - scheme_name: Full scheme name (e.g., "HDFC Flexi Cap Fund")
                - scheme_code: Optional scheme code for validation

        Returns:
            Dict mapping stock symbol to percentage
            Example: {'RELIANCE': 6.5, 'TCS': 5.2, 'HDFCBANK': 4.8}
        """
        scheme_name = params.get('scheme_name', '')
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        }

        try:
            # Fetch the monthly portfolio page
            portfolio_url = "https://www.hdfcfund.com/statutory-disclosure/portfolio/monthly-portfolio"
            logger.info(f"  Fetching HDFC portfolio page...")
            response = requests.get(portfolio_url, headers=headers, timeout=60)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Find the Excel file link for the specified scheme
            # Links have format: "Monthly HDFC Flexi Cap Fund - 30 November 2025.xlsx"
            excel_link = None
            for link in soup.find_all('a', href=True):
                href = link.get('href', '')
                link_text = link.get_text().strip()

                # Look for link containing scheme name and .xlsx
                if scheme_name.lower() in link_text.lower() and '.xlsx' in href.lower():
                    excel_link = href
                    # HDFC uses direct S3 links, no need to prepend domain
                    break

            if not excel_link:
                logger.warning(f"  Could not find Excel file for {scheme_name}")
                return {}

            # Download the Excel file
            logger.info(f"  Downloading Excel file: {excel_link}")
            excel_response = requests.get(excel_link, headers=headers, timeout=30)
            excel_response.raise_for_status()

            # Parse Excel file
            holdings = self._parse_hdfc_excel(BytesIO(excel_response.content), scheme_name)
            logger.info(f"  Parsed {len(holdings)} holdings from HDFC Excel")
            return holdings

        except Exception as e:
            logger.error(f"HDFC MF fetch error for {scheme_name}: {e}")
            return {}

    def _parse_hdfc_excel(self, excel_file: BytesIO, scheme_name: str) -> Dict[str, float]:
        """
        Parse HDFC Excel file to extract holdings.

        HDFC Excel files typically have:
        - Multiple sheets (one per scheme)
        - Columns: Security Name, ISIN, Quantity, Market Value, % to NAV
        """
        try:
            # Read Excel - try to find the right sheet
            xls = pd.ExcelFile(excel_file, engine='openpyxl')

            # Try to find sheet with matching scheme name or use first sheet
            sheet_name = xls.sheet_names[0]
            for name in xls.sheet_names:
                if scheme_name.lower() in name.lower():
                    sheet_name = name
                    break

            df = pd.read_excel(xls, sheet_name=sheet_name)

            # Find the column with percentages (% to NAV, % of NAV, etc.)
            pct_col = None
            stock_col = None

            for col in df.columns:
                col_lower = str(col).lower()
                if '%' in col_lower and ('nav' in col_lower or 'total' in col_lower):
                    pct_col = col
                if 'security' in col_lower or 'name' in col_lower or 'company' in col_lower:
                    stock_col = col

            if pct_col is None or stock_col is None:
                logger.warning(f"  Could not identify columns in HDFC Excel")
                return {}

            # Extract holdings
            holdings = {}
            min_pct = self.config.get('thresholds', {}).get('min_holding_to_report', 0.5)

            for idx, row in df.iterrows():
                stock = row[stock_col]
                pct = row[pct_col]

                # Skip if not valid
                if pd.isna(stock) or pd.isna(pct):
                    continue

                # Clean stock name
                stock = str(stock).strip().upper()
                # Remove common suffixes
                stock = stock.replace(' LTD', '').replace(' LIMITED', '').replace('.', '')

                try:
                    pct = float(pct)
                    if pct >= min_pct:
                        holdings[stock] = round(pct, 1)
                except (ValueError, TypeError):
                    continue

            return holdings

        except Exception as e:
            logger.error(f"  Error parsing HDFC Excel: {e}")
            return {}

    def fetch_from_ppfas_mf(self, params: dict) -> Dict[str, float]:
        """
        Fetch mutual fund holdings from PPFAS (Parag Parikh) Mutual Fund.
        Tries Gmail first (portfolio disclosure emails), then falls back to direct website.

        Args:
            params: Dict containing:
                - scheme_name: Full scheme name (e.g., "Parag Parikh Flexi Cap Fund")
                - fund_code: Optional fund code (PPFCF, PPTSF, etc.)

        Returns:
            Dict mapping stock symbol to percentage
        """
        scheme_name = params.get('scheme_name', '')
        fund_code = params.get('fund_code', '')

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/vnd.ms-excel'
        }

        try:
            # STEP 1: Try Gmail first (portfolio disclosure emails)
            if self.gmail_fetcher:
                logger.info(f"  Trying Gmail for PPFAS portfolio disclosure emails...")
                try:
                    # Use "Parag Parikh" for AMC name
                    download_url = self.gmail_fetcher.fetch_portfolio_from_email(
                        amc_name="Parag Parikh",
                        fund_name=scheme_name.split()[0] if scheme_name else "",  # "Flexi" or "ELSS"
                        days_back=60
                    )

                    if download_url:
                        logger.info(f"  Downloading from Gmail link...")
                        response = requests.get(download_url, headers=headers, timeout=60, allow_redirects=True)
                        response.raise_for_status()

                        holdings = self._parse_ppfas_excel(BytesIO(response.content), scheme_name)
                        if holdings:
                            logger.info(f"  ✓ Gmail fetch successful: {len(holdings)} holdings")
                            return holdings
                except Exception as e:
                    logger.warning(f"  Gmail fetch failed: {e}")

            # STEP 2: Fall back to direct PPFAS website
            portfolio_url = "https://amc.ppfas.com/downloads/portfolio-disclosure/"
            logger.info(f"  Trying PPFAS website...")
            response = requests.get(portfolio_url, headers=headers, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Find the Excel file link for the specified scheme
            excel_link = None
            for link in soup.find_all('a', href=True):
                href = link.get('href', '')
                link_text = link.get_text().lower()

                # Look for most recent file matching scheme
                if ('.xls' in href.lower() and
                    (scheme_name.lower() in link_text.lower() or
                     fund_code.lower() in link_text.lower() or
                     fund_code.lower() in href.lower())):
                    excel_link = href
                    if not excel_link.startswith('http'):
                        excel_link = f"https://amc.ppfas.com{excel_link}"
                    break

            if not excel_link:
                logger.warning(f"  Could not find Excel file for {scheme_name}")
                return {}

            # Download the Excel file
            logger.info(f"  Downloading Excel file: {excel_link}")
            excel_response = requests.get(excel_link, headers=headers, timeout=30)
            excel_response.raise_for_status()

            # Parse Excel file
            holdings = self._parse_ppfas_excel(BytesIO(excel_response.content), scheme_name)
            logger.info(f"  Parsed {len(holdings)} holdings from PPFAS Excel")
            return holdings

        except Exception as e:
            logger.error(f"PPFAS MF fetch error for {scheme_name}: {e}")
            return {}

    def _parse_ppfas_excel(self, excel_file: BytesIO, scheme_name: str) -> Dict[str, float]:
        """
        Parse PPFAS Excel file to extract holdings.

        PPFAS Excel files have a specific structure:
        - Row 3 contains headers
        - Column 1: Name of the Instrument
        - Column 6: % to Net Assets (in decimal format, e.g., 0.0803 = 8.03%)
        """
        try:
            # Read Excel with xlrd (PPFAS uses old .xls format)
            try:
                # Read without headers first to handle complex structure
                df = pd.read_excel(excel_file, engine='xlrd', header=None)
            except Exception as e1:
                logger.info(f"  Trying openpyxl...")
                excel_file.seek(0)
                df = pd.read_excel(excel_file, engine='openpyxl', header=None)

            # Row 3 (index 3) contains headers
            # Column 1: Stock Name
            # Column 6: % to Net Assets
            stock_col = 1
            pct_col = 6

            # Extract holdings starting from row 6 (after headers and section titles)
            holdings = {}
            min_pct = self.config.get('thresholds', {}).get('min_holding_to_report', 0.5)

            for idx, row in df.iterrows():
                if idx < 6:  # Skip header rows
                    continue

                stock = row[stock_col]
                pct = row[pct_col]

                # Skip if not valid
                if pd.isna(stock) or pd.isna(pct):
                    continue

                # Skip section headers and metadata
                stock_str = str(stock).strip()
                stock_upper = stock_str.upper()

                # Skip invalid/metadata rows
                skip_keywords = [
                    'TOTAL', 'GRAND', 'RETURNS', 'SINCE INCEPTION', 'MARKET VALUE',
                    'LAST', 'YEARS', 'NIFTY', 'SENSEX', 'DATE', 'PORTFOLIO',
                    'EQUITY', 'DEBT', 'CASH', 'SCHEME', 'FUND', 'ASSET', 'NAV',
                    'AWAITING', 'LISTED', 'GOVERNMENT', 'TREASURY', 'CLEARING'
                ]

                if (not stock_str or
                    stock_str.startswith('(') or
                    any(kw in stock_upper for kw in skip_keywords)):
                    continue

                # Clean stock name
                stock_clean = stock_str.upper()
                stock_clean = stock_clean.replace(' LIMITED', '').replace(' LTD', '').replace('.', '')

                try:
                    # Convert from decimal to percentage (0.0803 -> 8.03)
                    pct_value = float(pct) * 100

                    # Skip if percentage is unreasonable (likely metadata)
                    if pct_value < min_pct or pct_value > 25:  # Max 25% for single holding
                        continue

                    holdings[stock_clean] = round(pct_value, 1)
                except (ValueError, TypeError):
                    continue

                # Stop when we hit international holdings or other sections
                # (we can track both Indian and international stocks)

            return holdings

        except Exception as e:
            logger.error(f"  Error parsing PPFAS Excel: {e}")
            return {}

    def fetch_from_tata_mf(self, params: dict) -> Dict[str, float]:
        """
        Fetch mutual fund holdings from Tata Mutual Fund.
        Tries Gmail first (portfolio disclosure emails), then falls back to Advisorkhoj.

        Args:
            params: Dict containing:
                - sheet_code: Scheme code (e.g., "TTSF96" for TATA ELSS FUND)
                - scheme_name: Optional full scheme name

        Returns:
            Dict mapping stock symbol to percentage
        """
        sheet_code = params.get('sheet_code', '')
        scheme_name = params.get('scheme_name', sheet_code)

        try:
            # Try Gmail first
            if self.gmail_fetcher:
                logger.info(f"  Trying Gmail for Tata portfolio disclosure emails...")
                try:
                    download_url = self.gmail_fetcher.fetch_portfolio_from_email(
                        amc_name="Tata",
                        fund_name="ELSS",
                        days_back=60
                    )

                    if download_url:
                        logger.info(f"  Downloading from Gmail link...")
                        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
                        response = requests.get(download_url, headers=headers, timeout=60, allow_redirects=True)
                        response.raise_for_status()

                        holdings = self._parse_tata_excel(BytesIO(response.content), sheet_code, scheme_name)
                        if holdings:
                            logger.info(f"  ✓ Gmail fetch successful: {len(holdings)} holdings")
                            return holdings
                except Exception as e:
                    logger.warning(f"  Gmail fetch failed: {e}")

            # Fall back to Advisorkhoj
            logger.info(f"  Trying Advisorkhoj portal...")

            # Use Advisorkhoj which provides direct links
            url = "https://www.advisorkhoj.com/form-download-centre/Mutual/Tata-Mutual-Fund/Monthly-Portfolio-Disclosures"

            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }

            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Find all links
            download_link = None
            for link in soup.find_all('a', href=True):
                href = link.get('href', '')
                text = link.get_text().strip()

                # Look for most recent XLSX file (November 2025 or latest)
                if '.xlsx' in href.lower():
                    if 'november' in text.lower() and '2025' in text.lower():
                        download_link = href
                        logger.info(f"  Found file: {text}")
                        break
                    elif not download_link and 'portfolio' in text.lower() and '2025' in text.lower():
                        download_link = href

            if not download_link:
                raise Exception("Could not find portfolio download link on Advisorkhoj")

            logger.info(f"  Downloading file...")
            response = requests.get(download_link, headers=headers, timeout=60, allow_redirects=True)
            response.raise_for_status()

            # Parse Excel file
            holdings = self._parse_tata_excel(BytesIO(response.content), sheet_code, scheme_name)
            logger.info(f"  Parsed {len(holdings)} holdings from Tata MF Excel")
            return holdings

        except Exception as e:
            logger.error(f"Tata MF fetch error for {scheme_name}: {e}")
            return {}

    def _parse_tata_excel(self, excel_file: BytesIO, sheet_code: str, scheme_name: str) -> Dict[str, float]:
        """
        Parse Tata MF Excel file to extract holdings for specific scheme.

        Tata MF structure:
        - Consolidated file with multiple sheets (one per scheme)
        - Sheet name is scheme code (e.g., TTSF96)
        - Row 11: Headers
        - Column 1: Stock name
        - Column 7: % to NAV
        """
        try:
            # Read the specific scheme sheet
            df = pd.read_excel(excel_file, sheet_name=sheet_code, engine='openpyxl', header=None)

            # Data starts from row 14 (index 14)
            # Column 1: Stock name
            # Column 7: % to NAV
            stock_col = 1
            pct_col = 7

            holdings = {}
            min_pct = self.config.get('thresholds', {}).get('min_holding_to_report', 0.5)

            for idx, row in df.iterrows():
                if idx < 14:  # Skip header rows
                    continue

                stock = row[stock_col]
                pct = row[pct_col]

                # Skip if not valid
                if pd.isna(stock) or pd.isna(pct):
                    continue

                # Convert to string and check if it's a stock entry
                stock_str = str(stock).strip()

                # Skip section headers
                skip_keywords = [
                    'EQUITY', 'LISTED', 'AWAITING', 'TOTAL', 'GRAND',
                    'UNLISTED', 'SECURITIES', 'DEBT', 'MONEY', 'CASH',
                    'NET', 'INVESTMENT', 'NAME OF'
                ]

                if (not stock_str or
                    stock_str.startswith('(') or
                    stock_str.endswith(')') or
                    any(kw in stock_str.upper() for kw in skip_keywords)):
                    continue

                # Clean stock name
                stock_clean = stock_str.upper()
                stock_clean = stock_clean.replace(' LTD.', '').replace(' LTD', '').replace(' LIMITED', '')

                try:
                    pct_value = float(pct)
                    if pct_value >= min_pct:
                        holdings[stock_clean] = round(pct_value, 1)
                except (ValueError, TypeError):
                    continue

            return holdings

        except Exception as e:
            logger.error(f"  Error parsing Tata MF Excel: {e}")
            return {}

    def fetch_from_quant_mf(self, params: dict) -> Dict[str, float]:
        """
        Fetch mutual fund holdings from Quant Mutual Fund.
        Tries Gmail first (portfolio disclosure emails), then falls back to Advisorkhoj.

        Args:
            params: Dict containing:
                - scheme_name: Full scheme name (e.g., "Quant Small Cap Fund")

        Returns:
            Dict mapping stock symbol to percentage
        """
        scheme_name = params.get('scheme_name', '')

        try:
            # Try Gmail first
            if self.gmail_fetcher:
                logger.info(f"  Trying Gmail for Quant portfolio disclosure emails...")
                try:
                    download_url = self.gmail_fetcher.fetch_portfolio_from_email(
                        amc_name="Quant",
                        fund_name="Small Cap",
                        days_back=60
                    )

                    if download_url:
                        logger.info(f"  Downloading from Gmail link...")
                        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
                        response = requests.get(download_url, headers=headers, timeout=60, allow_redirects=True)
                        response.raise_for_status()

                        holdings = self._parse_quant_excel(BytesIO(response.content), scheme_name)
                        if holdings:
                            logger.info(f"  ✓ Gmail fetch successful: {len(holdings)} holdings")
                            return holdings
                except Exception as e:
                    logger.warning(f"  Gmail fetch failed: {e}")

            # Fall back to Advisorkhoj
            logger.info(f"  Trying Advisorkhoj portal...")

            # Use Advisorkhoj
            url = "https://www.advisorkhoj.com/form-download-centre/Mutual-Funds/Quant-Mutual-Fund/Monthly-Portfolio-Disclosures"

            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }

            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Find latest 2025 consolidated portfolio file (November or latest available)
            download_link = None
            for link in soup.find_all('a', href=True):
                href = link.get('href', '')
                text = link.get_text().strip()

                # Look for November 2025 file first, then Oct, Sep as fallback
                if ('.xlsx' in href.lower() or '.xls' in href.lower()) and '2025' in text.lower():
                    if 'november' in text.lower():
                        download_link = href
                        logger.info(f"  Found file: {text}")
                        break
                    elif 'october' in text.lower() and not download_link:
                        download_link = href
                        logger.info(f"  Found fallback file: {text}")
                    elif not download_link:  # Take any 2025 file as last resort
                        download_link = href

            if not download_link:
                raise Exception(f"Could not find 2025 portfolio file")

            logger.info(f"  Downloading consolidated file...")
            response = requests.get(download_link, headers=headers, timeout=60, allow_redirects=True)
            response.raise_for_status()

            # Parse Excel file - find Small Cap fund sheet
            holdings = self._parse_quant_excel(BytesIO(response.content), scheme_name)
            logger.info(f"  Parsed {len(holdings)} holdings from Quant MF Excel")
            return holdings

        except Exception as e:
            logger.error(f"Quant MF fetch error for {scheme_name}: {e}")
            return {}

    
    def _parse_quant_excel(self, excel_file: BytesIO, scheme_name: str) -> Dict[str, float]:
        """
        Parse Quant MF Excel file to extract holdings.
        Handles consolidated files with multiple sheets.
        """
        try:
            # Try to read the Excel file
            try:
                xls = pd.ExcelFile(excel_file, engine='openpyxl')
            except:
                excel_file.seek(0)
                xls = pd.ExcelFile(excel_file, engine='xlrd')

            logger.info(f"  Found {len(xls.sheet_names)} sheets in file")

            # Look for sheet matching scheme name
            target_sheet = None
            for sheet in xls.sheet_names:
                if 'small cap' in sheet.lower() or 'scf' in sheet.lower():
                    target_sheet = sheet
                    logger.info(f"  Found matching sheet: {sheet}")
                    break

            if not target_sheet:
                logger.warning(f"  Could not find sheet for {scheme_name}")
                return {}

            # Read the sheet
            df = pd.read_excel(xls, sheet_name=target_sheet, header=None)

            # Auto-detect columns and data
            holdings = {}
            min_pct = self.config.get('thresholds', {}).get('min_holding_to_report', 0.5)

            stock_col = None
            pct_col = None
            data_start_row = None

            # Scan first 30 rows
            for idx in range(min(30, len(df))):
                row = df.iloc[idx]
                row_text = ' '.join([str(cell).lower() for cell in row if pd.notna(cell)])

                if 'name' in row_text and ('instrument' in row_text or 'security' in row_text or 'company' in row_text):
                    for col_idx, cell in enumerate(row):
                        cell_str = str(cell).lower()
                        if 'name' in cell_str or 'instrument' in cell_str or 'company' in cell_str:
                            stock_col = col_idx
                        if '%' in cell_str and ('nav' in cell_str or 'portfolio' in cell_str or 'asset' in cell_str):
                            pct_col = col_idx

                    if stock_col is not None and pct_col is not None:
                        data_start_row = idx + 1
                        break

            if stock_col is None or pct_col is None:
                logger.warning("  Could not auto-detect columns")
                return {}

            # Extract holdings
            for idx in range(data_start_row, len(df)):
                row = df.iloc[idx]
                stock = row[stock_col]
                pct = row[pct_col]

                if pd.isna(stock) or pd.isna(pct):
                    continue

                stock_str = str(stock).strip()
                skip_keywords = ['EQUITY', 'TOTAL', 'GRAND', 'DEBT', 'CASH', 'NAME OF', 'INSTRUMENT', 'SECURITY', 'PORTFOLIO']

                if not stock_str or any(kw in stock_str.upper() for kw in skip_keywords):
                    continue

                stock_clean = stock_str.upper().replace(' LTD', '').replace(' LIMITED', '').replace('.', '')

                try:
                    pct_value = float(pct)
                    if pct_value >= min_pct:
                        holdings[stock_clean] = round(pct_value, 1)
                except (ValueError, TypeError):
                    continue

            return holdings

        except Exception as e:
            logger.error(f"  Error parsing Quant Excel: {e}")
            return {}

    
    def fetch_from_bandhan_mf(self, params: dict) -> Dict[str, float]:
        """
        Fetch mutual fund holdings from Bandhan Mutual Fund.
        Tries Gmail first (portfolio disclosure emails), then falls back to Advisorkhoj and Selenium.

        Args:
            params: Dict containing:
                - scheme_name: Full scheme name (e.g., "Bandhan ELSS Tax Saver Fund")

        Returns:
            Dict mapping stock symbol to percentage
        """
        scheme_name = params.get('scheme_name', '')

        try:
            # STEP 1: Try Gmail first (most reliable - uses investor's disclosure emails)
            if self.gmail_fetcher:
                logger.info(f"  Trying Gmail for Bandhan portfolio disclosure emails...")
                try:
                    download_url = self.gmail_fetcher.fetch_portfolio_from_email(
                        amc_name="Bandhan",
                        fund_name="ELSS",
                        days_back=60
                    )

                    if download_url:
                        logger.info(f"  Downloading from Gmail link...")
                        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
                        response = requests.get(download_url, headers=headers, timeout=60, allow_redirects=True)
                        response.raise_for_status()

                        holdings = self._parse_bandhan_excel(BytesIO(response.content), scheme_name)
                        if holdings:
                            logger.info(f"  ✓ Gmail fetch successful: {len(holdings)} holdings")
                            return holdings
                except Exception as e:
                    logger.warning(f"  Gmail fetch failed: {e}")

            # STEP 2: Fall back to Advisorkhoj
            logger.info(f"  Trying Advisorkhoj portal...")

            # Use Advisorkhoj
            url = "https://www.advisorkhoj.com/form-download-centre/Mutual-Funds/Bandhan-Mutual-Fund/Monthly-Portfolio-Disclosures"

            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }

            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Find latest portfolio file (try 2025 first, fall back to 2024)
            download_link = None
            file_year = None

            # First try to find 2025 files
            for link in soup.find_all('a', href=True):
                href = link.get('href', '')
                text = link.get_text().strip()

                if ('.xlsx' in href.lower() or '.xls' in href.lower()) and '2025' in text.lower():
                    if 'november' in text.lower():
                        download_link = href
                        file_year = '2025'
                        logger.info(f"  Found file: {text}")
                        break
                    elif 'october' in text.lower() and not download_link:
                        download_link = href
                        file_year = '2025'
                        logger.info(f"  Found fallback file: {text}")
                    elif not download_link:  # Take any 2025 file as last resort
                        download_link = href
                        file_year = '2025'

            # If no 2025 files found, try 2024 as fallback
            if not download_link:
                logger.warning(f"  No 2025 portfolio files found, trying 2024...")
                for link in soup.find_all('a', href=True):
                    href = link.get('href', '')
                    text = link.get_text().strip()

                    if ('.xlsx' in href.lower() or '.xls' in href.lower()) and '2024' in text.lower():
                        if 'december' in text.lower() or 'nov' in text.lower():
                            download_link = href
                            file_year = '2024'
                            logger.warning(f"  Using 2024 file: {text}")
                            break
                        elif not download_link:
                            download_link = href
                            file_year = '2024'

            if not download_link:
                # Advisorkhoj doesn't have the file, try direct Bandhan website with Selenium
                logger.warning(f"  No files found on Advisorkhoj, trying direct Bandhan website with Selenium...")
                return self._fetch_bandhan_selenium(scheme_name)

            if file_year == '2024':
                logger.warning(f"  WARNING: Using {file_year} data (2025 not yet available)")

            logger.info(f"  Downloading consolidated file...")
            response = requests.get(download_link, headers=headers, timeout=60, allow_redirects=True)
            response.raise_for_status()

            # Parse Excel file - find ELSS fund sheet
            holdings = self._parse_bandhan_excel(BytesIO(response.content), scheme_name)
            logger.info(f"  Parsed {len(holdings)} holdings from Bandhan MF Excel")
            return holdings

        except Exception as e:
            logger.error(f"Bandhan MF fetch error for {scheme_name}: {e}")
            return {}

    def _fetch_bandhan_selenium(self, scheme_name: str) -> Dict[str, float]:
        """
        Fetch Bandhan portfolio using Selenium (fallback when Advisorkhoj doesn't have files).
        """
        driver = None
        try:
            logger.info(f"  Launching headless Chrome browser...")
            driver = self._get_selenium_driver()

            # Navigate to Bandhan MF downloads page
            url = "https://bandhanmutual.com/Downloads/MutualFundPortfolios"
            logger.info(f"  Navigating to Bandhan website...")
            driver.get(url)

            # Wait for page to load
            time.sleep(5)

            # Find ELSS fund portfolio link (look for most recent month)
            logger.info(f"  Searching for ELSS fund portfolio...")
            elss_link = None

            # Try to find links with ELSS or "Tax Saver" in them
            links = driver.find_elements(By.TAG_NAME, 'a')
            for link in links:
                try:
                    text = link.text.lower()
                    href = link.get_attribute('href') or ''

                    if ('elss' in text or 'tax saver' in text) and ('.xls' in href.lower()):
                        # Check if it's a recent file (2025 or 2024)
                        if '2025' in text or '2024' in text:
                            elss_link = href
                            logger.info(f"  Found: {link.text}")
                            break
                except:
                    continue

            if not elss_link:
                raise Exception("Could not find ELSS portfolio file on Bandhan website")

            # Download the file
            logger.info(f"  Downloading file from Bandhan website...")
            response = requests.get(elss_link, timeout=60)
            response.raise_for_status()

            # Parse the Excel file
            holdings = self._parse_bandhan_excel(BytesIO(response.content), scheme_name)
            logger.info(f"  Parsed {len(holdings)} holdings from Bandhan Excel")
            return holdings

        except Exception as e:
            logger.error(f"  Selenium fetch failed: {e}")
            return {}

        finally:
            if driver:
                driver.quit()

    
    def _parse_bandhan_excel(self, excel_file: BytesIO, scheme_name: str) -> Dict[str, float]:
        """
        Parse Bandhan MF Excel file to extract holdings.
        Handles consolidated files with multiple sheets.
        """
        try:
            # Try to read the Excel file
            try:
                xls = pd.ExcelFile(excel_file, engine='openpyxl')
            except:
                excel_file.seek(0)
                xls = pd.ExcelFile(excel_file, engine='xlrd')

            logger.info(f"  Found {len(xls.sheet_names)} sheets in file")

            # Look for sheet matching scheme name
            target_sheet = None

            # If only 1 sheet, use it (e.g., individual fund file from Gmail)
            if len(xls.sheet_names) == 1:
                target_sheet = xls.sheet_names[0]
                logger.info(f"  Using single sheet: {target_sheet}")
            else:
                # Multiple sheets - look for one matching "elss"
                for sheet in xls.sheet_names:
                    if 'elss' in sheet.lower():
                        target_sheet = sheet
                        logger.info(f"  Found matching sheet: {sheet}")
                        break

            if not target_sheet:
                logger.warning(f"  Could not find sheet for {scheme_name}")
                return {}

            # Read the sheet
            df = pd.read_excel(xls, sheet_name=target_sheet, header=None)

            # Auto-detect columns and data
            holdings = {}
            min_pct = self.config.get('thresholds', {}).get('min_holding_to_report', 0.5)

            stock_col = None
            pct_col = None
            data_start_row = None

            # Scan first 30 rows
            for idx in range(min(30, len(df))):
                row = df.iloc[idx]
                row_text = ' '.join([str(cell).lower() for cell in row if pd.notna(cell)])

                if 'name' in row_text and ('instrument' in row_text or 'security' in row_text or 'company' in row_text):
                    for col_idx, cell in enumerate(row):
                        cell_str = str(cell).lower()
                        if 'name' in cell_str or 'instrument' in cell_str or 'company' in cell_str:
                            stock_col = col_idx
                        if '%' in cell_str and ('nav' in cell_str or 'portfolio' in cell_str or 'asset' in cell_str):
                            pct_col = col_idx

                    if stock_col is not None and pct_col is not None:
                        data_start_row = idx + 1
                        break

            if stock_col is None or pct_col is None:
                logger.warning("  Could not auto-detect columns")
                return {}

            # Extract holdings
            for idx in range(data_start_row, len(df)):
                row = df.iloc[idx]
                stock = row[stock_col]
                pct = row[pct_col]

                if pd.isna(stock) or pd.isna(pct):
                    continue

                stock_str = str(stock).strip()
                skip_keywords = ['EQUITY', 'TOTAL', 'GRAND', 'DEBT', 'CASH', 'NAME OF', 'INSTRUMENT', 'SECURITY', 'PORTFOLIO', 'LISTED', 'UNLISTED']

                if not stock_str or any(kw in stock_str.upper() for kw in skip_keywords):
                    continue

                stock_clean = stock_str.upper().replace(' LTD', '').replace(' LIMITED', '').replace('.', '')

                try:
                    pct_value = float(pct)

                    # Handle decimal format (0.0784) vs percentage format (7.84)
                    # Bandhan stores as decimal, so convert to percentage
                    if pct_value < 1.0 and pct_value > 0:
                        pct_value = pct_value * 100

                    if pct_value >= min_pct:
                        holdings[stock_clean] = round(pct_value, 1)
                except (ValueError, TypeError):
                    continue

            return holdings

        except Exception as e:
            logger.error(f"  Error parsing Bandhan Excel: {e}")
            return {}

    
    def fetch_constituents(self, index_config: dict) -> Set[str]:
        """
        Generic fetch function that routes to appropriate source handler.
        """
        index_name = index_config['name']
        source = index_config['source']
        params = index_config.get('params', {})

        logger.info(f"Fetching constituents for {index_name}...")

        handler = self.source_handlers.get(source)
        if not handler:
            logger.error(f"Unknown source type: {source}")
            return set()

        constituents = handler(params)
        constituents = {self.clean_symbol(s) for s in constituents if s}

        logger.info(f"  {index_name}: Found {len(constituents)} constituents")
        return constituents
    
    def fetch_fund_holdings(self, fund_config: dict) -> Dict[str, float]:
        """
        Fetch holdings for a single mutual fund.

        Args:
            fund_config: Fund configuration from config.json

        Returns:
            Dict mapping stock to percentage
        """
        fund_name = fund_config['name']
        source = fund_config['source']
        params = fund_config.get('params', {})

        logger.info(f"Fetching holdings for {fund_name}...")

        # Get appropriate handler
        handler = self.mf_source_handlers.get(source)

        if not handler:
            logger.error(f"  Unknown MF source type: {source}")
            return {}

        # Fetch holdings
        holdings = handler(params)

        logger.info(f"  Found {len(holdings)} holdings for {fund_name}")
        return holdings

    def fetch_all_constituents(self) -> Dict:
        """
        Fetch constituents for both indexes and mutual funds.

        Returns:
            Dict with keys 'indexes' and 'mutual_funds'
        """
        current_state = {
            'indexes': {},
            'mutual_funds': {}
        }

        # Fetch indexes (existing logic)
        for index_config in self.config.get('indexes', []):
            constituents = self.fetch_constituents(index_config)
            current_state['indexes'][index_config['name']] = sorted(list(constituents))
            time.sleep(2)  # Rate limiting

        # Fetch mutual funds (NEW)
        for fund_config in self.config.get('mutual_funds', []):
            # Skip disabled funds
            if not fund_config.get('_enabled', True):
                logger.info(f"Skipping disabled fund: {fund_config['name']}")
                continue

            holdings = self.fetch_fund_holdings(fund_config)
            current_state['mutual_funds'][fund_config['name']] = {
                'month': datetime.now().strftime('%Y-%m'),
                'disclosure_date': datetime.now().strftime('%Y-%m-%d'),
                'holdings': holdings
            }
            time.sleep(2)  # Rate limiting

        return current_state
    
    def load_previous_state(self) -> Dict[str, List[str]]:
        """Load previous state from file"""
        if self.state_file.exists():
            with open(self.state_file, 'r') as f:
                return json.load(f)
        return {}
    
    def save_current_state(self, state: Dict[str, List[str]]):
        """Save current state to file"""
        with open(self.state_file, 'w') as f:
            json.dump(state, f, indent=2)
    
    def detect_changes(self, previous: Dict[str, List[str]], 
                      current: Dict[str, List[str]]) -> Dict[str, Dict[str, List[str]]]:
        """Detect changes between previous and current state"""
        changes = {}
        
        for index in current.keys():
            prev_set = set(previous.get(index, []))
            curr_set = set(current[index])
            
            added = curr_set - prev_set
            removed = prev_set - curr_set
            
            if added or removed:
                changes[index] = {
                    'added': sorted(list(added)),
                    'removed': sorted(list(removed))
                }
        
        return changes
    
    def format_mf_changes(self, fund_name: str, changes: Dict, month: str) -> str:
        """
        Format mutual fund changes for email.

        Args:
            fund_name: Name of the mutual fund
            changes: Changes dict from MFChangeDetector
            month: Month in format 'YYYY-MM'

        Returns:
            Formatted text for email body
        """
        if not self.mf_detector.has_changes(changes):
            return ""

        # Convert month format: 2025-12 → December 2025
        try:
            date_obj = datetime.strptime(month, '%Y-%m')
            month_name = date_obj.strftime('%B %Y')
        except:
            month_name = month

        lines = [
            fund_name,
            "-" * len(fund_name),
            f"Period: {month_name}",
            ""
        ]

        # New additions
        if changes['additions']:
            lines.append(f"NEW ADDITIONS ({len(changes['additions'])}):")
            for stock, pct in sorted(changes['additions'],
                                     key=lambda x: x[1], reverse=True):
                lines.append(f"  + {stock} ({pct:.1f}%)")
            lines.append("")

        # Complete exits
        if changes['exits']:
            lines.append(f"COMPLETE EXITS ({len(changes['exits'])}):")
            for stock, old_pct in sorted(changes['exits'],
                                         key=lambda x: x[1], reverse=True):
                lines.append(f"  - {stock} (was {old_pct:.1f}%)")
            lines.append("")

        # Increases
        if changes['increases']:
            lines.append("SIGNIFICANT INCREASES:")
            for stock, old, new, change in sorted(changes['increases'],
                                                   key=lambda x: x[3], reverse=True):
                lines.append(f"  {stock}: {old:.1f}% -> {new:.1f}% (+{change:.1f}%)")
            lines.append("")

        # Decreases
        if changes['decreases']:
            lines.append("SIGNIFICANT DECREASES:")
            for stock, old, new, change in sorted(changes['decreases'],
                                                   key=lambda x: x[3]):
                lines.append(f"  {stock}: {old:.1f}% -> {new:.1f}% ({change:.1f}%)")
            lines.append("")

        return "\n".join(lines)

    def format_email_body(self, index_changes: Dict[str, Dict[str, List[str]]], mf_changes: Dict = None) -> str:
        """
        Format unified email body with both index and MF changes.

        Args:
            index_changes: Index changes (existing format)
            mf_changes: MF changes {fund_name: changes_dict}

        Returns:
            Complete email body text
        """
        if mf_changes is None:
            mf_changes = {}

        month_year = datetime.now().strftime('%Y-%m')

        # Check if any changes at all
        has_index_changes = bool(index_changes)
        has_mf_changes = any(self.mf_detector.has_changes(c.get('changes', {}))
                             for c in mf_changes.values() if isinstance(c, dict))

        lines = []

        if not has_index_changes and not has_mf_changes:
            lines.append(f"No Portfolio Changes - {month_year}")
            lines.append("")
            lines.append("=" * 60)
            lines.append("")
            lines.append("All monitored indexes and mutual funds remain unchanged.")
            lines.append("")
            if self.config.get('indexes'):
                lines.append("Monitored Indexes:")
                for index_config in self.config.get('indexes', []):
                    lines.append(f"  - {index_config['name']}")
                lines.append("")
            if self.config.get('mutual_funds'):
                lines.append("Monitored Mutual Funds:")
                for fund_config in self.config.get('mutual_funds', []):
                    lines.append(f"  - {fund_config['name']}")
                lines.append("")
            return "\n".join(lines)

        lines.append(f"Portfolio Changes Detected - {month_year}")
        lines.append("")

        # Index changes section
        if has_index_changes:
            lines.append("=" * 60)
            lines.append("INDEX CONSTITUENT CHANGES")
            lines.append("=" * 60)
            lines.append("")

            for index, change in index_changes.items():
                lines.append(index)
                lines.append("-" * len(index))

                # Try to resolve tickers to company names
                ticker_map = {}
                if self.ticker_resolver.is_available() and (change['added'] or change['removed']):
                    # Build a simple diff text for the LLM
                    diff_parts = []
                    if change['added']:
                        diff_parts.append(f"Added ({len(change['added'])}):")
                        for stock in change['added']:
                            diff_parts.append(f"  + {stock}")
                    if change['removed']:
                        diff_parts.append(f"Removed ({len(change['removed'])}):")
                        for stock in change['removed']:
                            diff_parts.append(f"  - {stock}")

                    diff_text = "\n".join(diff_parts)
                    logger.info(f"Resolving tickers for {index}...")
                    ticker_map = self.ticker_resolver.resolve_tickers(diff_text, index)

                if change['added']:
                    lines.append(f"Added ({len(change['added'])}):")
                    formatted_added = self.ticker_resolver.format_with_company_names(
                        change['added'], ticker_map
                    ) if ticker_map else change['added']
                    for stock in formatted_added:
                        lines.append(f"  + {stock}")
                    lines.append("")

                if change['removed']:
                    lines.append(f"Removed ({len(change['removed'])}):")
                    formatted_removed = self.ticker_resolver.format_with_company_names(
                        change['removed'], ticker_map
                    ) if ticker_map else change['removed']
                    for stock in formatted_removed:
                        lines.append(f"  - {stock}")
                    lines.append("")

                lines.append("")

        # Mutual fund changes section
        if has_mf_changes:
            lines.append("=" * 60)
            lines.append("MUTUAL FUND HOLDINGS CHANGES")
            lines.append("=" * 60)
            lines.append("")

            for fund_name, fund_data in mf_changes.items():
                if isinstance(fund_data, dict):
                    changes = fund_data.get('changes', {})
                    month = fund_data.get('month', month_year)
                    if self.mf_detector.has_changes(changes):
                        fund_section = self.format_mf_changes(fund_name, changes, month)
                        if fund_section:
                            lines.append(fund_section)
                            lines.append("")

        lines.append("=" * 60)

        return "\n".join(lines)
    
    def _clean_credential(self, value: str) -> str:
        """Force-clean credentials by removing all whitespace and non-ASCII chars."""
        # Remove ALL whitespace including non-breaking spaces (\xa0)
        cleaned = ''.join(value.split())
        # Force ASCII encoding to strip any remaining non-ASCII characters
        return cleaned.encode('ascii', 'ignore').decode('ascii')

    def send_email(self, subject: str, body: str):
        """Send email notification using MIME."""
        sender = self._clean_credential(os.environ.get('EMAIL_SENDER', ''))
        password = self._clean_credential(os.environ.get('EMAIL_PASSWORD', ''))
        # Default recipient to sender if not specified
        recipient = self._clean_credential(os.environ.get('EMAIL_RECIPIENT', '')) or sender

        if not sender or not password:
            logger.warning("Email credentials not found. Set EMAIL_SENDER and EMAIL_PASSWORD.")
            return

        msg = MIMEMultipart()
        msg['From'] = sender
        msg['To'] = recipient
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        try:
            with smtplib.SMTP(
                self.config['email']['smtp_server'],
                self.config['email']['smtp_port']
            ) as server:
                server.starttls()
                server.login(sender, password)
                server.send_message(msg)
            logger.info(f"Email sent successfully to {recipient}")
        except smtplib.SMTPAuthenticationError:
            logger.error("Email authentication failed. Check EMAIL_SENDER and EMAIL_PASSWORD.")
        except Exception as e:
            logger.error(f"Error sending email: {e}")
    
    def run(self):
        """Main execution method."""
        logger.info("=" * 60)
        logger.info("Portfolio Monitor (Indexes + Mutual Funds)")
        logger.info(f"Run date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 60)
        logger.info("")

        # Fetch current state
        logger.info("Fetching current data...")
        current_state = self.fetch_all_constituents()

        # Load previous state
        logger.info("\nLoading previous state...")
        previous_state = self.load_previous_state()

        # Detect index changes (existing)
        logger.info("Detecting index changes...")
        index_changes = self.detect_changes(
            previous_state.get('indexes', {}),
            current_state.get('indexes', {})
        )

        # Detect MF changes (NEW)
        logger.info("Detecting mutual fund changes...")
        mf_changes = {}
        for fund_name, fund_data in current_state.get('mutual_funds', {}).items():
            prev_fund = previous_state.get('mutual_funds', {}).get(fund_name, {})
            prev_holdings = prev_fund.get('holdings', {})
            curr_holdings = fund_data.get('holdings', {})

            changes = self.mf_detector.detect_changes(prev_holdings, curr_holdings)
            mf_changes[fund_name] = {
                'changes': changes,
                'month': fund_data.get('month')
            }

        # Save current state
        self.save_current_state(current_state)
        logger.info("Current state saved")

        # Generate email
        month_year = datetime.now().strftime('%Y-%m')

        has_index_changes = bool(index_changes)
        has_mf_changes = any(self.mf_detector.has_changes(c.get('changes', {}))
                             for c in mf_changes.values())

        if has_index_changes or has_mf_changes:
            logger.info(f"\nChanges detected!")
            if has_index_changes:
                logger.info(f"  - {len(index_changes)} index(es) have changes")
            if has_mf_changes:
                mf_count = sum(1 for c in mf_changes.values()
                              if self.mf_detector.has_changes(c.get('changes', {})))
                logger.info(f"  - {mf_count} mutual fund(s) have changes")
            subject = f"Portfolio Changes Detected - {month_year}"
        else:
            logger.info("\nNo changes detected")
            subject = f"No Portfolio Changes - {month_year}"

        email_body = self.format_email_body(index_changes, mf_changes)
        print("\n" + email_body)
        self.send_email(subject, email_body)


if __name__ == "__main__":
    monitor = IndexMonitor()
    monitor.run()
