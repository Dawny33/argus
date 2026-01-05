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
import pandas as pd
from io import BytesIO

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
        }

        # MF change detector
        mf_threshold = self.config.get('thresholds', {}).get('mf_percentage_change', 0.5)
        self.mf_detector = MFChangeDetector(threshold=mf_threshold)
    
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
        Downloads and parses monthly portfolio Excel file.

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
            # Fetch the portfolio disclosure page
            portfolio_url = "https://amc.ppfas.com/downloads/portfolio-disclosure/"
            logger.info(f"  Fetching PPFAS portfolio page...")
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
