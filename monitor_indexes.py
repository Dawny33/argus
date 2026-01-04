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
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Dict, List, Set
import time

import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


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
        }
    
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
                        "params": {"fund_id": "3369"}
                    },
                    {
                        "name": "QQQM",
                        "source": "nasdaq_official",
                        "params": {"index_symbol": "NDX"}
                    }
                ],
                "email": {
                    "recipient": "jrajrohit33@gmail.com",
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
        Fetch holdings from Vanguard ETF.
        Note: VXUS has 7000+ holdings. Full tracking is not practical.
        This handler is a placeholder for ETFs with manageable holding counts.
        """
        fund_id = params.get('fund_id')
        if not fund_id:
            logger.warning("Vanguard ETF: fund_id not provided")
            return set()

        # VXUS has 7000+ holdings - tracking all is impractical
        # This would require Vanguard API access or downloading their full holdings CSV
        logger.info(f"Vanguard ETF (fund_id={fund_id}): Skipping - 7000+ holdings not trackable")
        return set()
    
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
    
    def fetch_all_constituents(self) -> Dict[str, List[str]]:
        """Fetch constituents for all configured indexes"""
        current_state = {}
        
        for index_config in self.config['indexes']:
            constituents = self.fetch_constituents(index_config)
            current_state[index_config['name']] = sorted(list(constituents))
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
    
    def format_email_body(self, changes: Dict[str, Dict[str, List[str]]]) -> str:
        """Format the email body with changes."""
        month_year = datetime.now().strftime('%Y-%m')
        lines = []

        if not changes:
            lines.append(f"No Index Constituent Changes - {month_year}")
            lines.append("")
            lines.append("=" * 60)
            lines.append("")
            lines.append("All monitored indexes remain unchanged:")
            lines.append("")
            for index_config in self.config['indexes']:
                lines.append(f"  - {index_config['name']}")
            lines.append("")
            lines.append("Your monitoring system is working correctly.")
            lines.append("You will receive an email next month with any changes detected.")
            return "\n".join(lines)

        lines.append(f"Index Constituent Changes - {month_year}")
        lines.append("")
        lines.append("=" * 60)
        lines.append("")

        for index, change in changes.items():
            lines.append(index)
            lines.append("-" * len(index))

            if change['added']:
                lines.append(f"Added ({len(change['added'])}):")
                for stock in change['added']:
                    lines.append(f"  + {stock}")
                lines.append("")

            if change['removed']:
                lines.append(f"Removed ({len(change['removed'])}):")
                for stock in change['removed']:
                    lines.append(f"  - {stock}")
                lines.append("")

            lines.append("")

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

        if not sender or not password:
            logger.warning("Email credentials not found. Set EMAIL_SENDER and EMAIL_PASSWORD.")
            return

        recipient = self._clean_credential(self.config['email']['recipient'])

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
        logger.info("Index Constituent Monitor")
        logger.info(f"Run date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 60)

        current_state = self.fetch_all_constituents()

        logger.info("Loading previous state...")
        previous_state = self.load_previous_state()

        logger.info("Detecting changes...")
        changes = self.detect_changes(previous_state, current_state)

        self.save_current_state(current_state)
        logger.info("Current state saved")

        month_year = datetime.now().strftime('%Y-%m')

        if changes:
            logger.info(f"{len(changes)} index(es) have changes")
            subject = f"Index Changes Detected - {month_year}"
        else:
            logger.info("No changes detected")
            subject = f"No Index Changes - {month_year}"

        email_body = self.format_email_body(changes)
        print("\n" + email_body)
        self.send_email(subject, email_body)


if __name__ == "__main__":
    monitor = IndexMonitor()
    monitor.run()
