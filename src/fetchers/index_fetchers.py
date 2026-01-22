"""
Index Fetchers Module

Contains specialized fetcher classes for different index data sources:
- NSEFetcher: Fetches constituents from NSE India API
- NasdaqFetcher: Fetches Nasdaq 100 constituents from Wikipedia
- VanguardFetcher: Fetches Vanguard ETF holdings from official API
- InvescoFetcher: Fetches Invesco ETF holdings (delegates to Nasdaq for QQQM)
"""

import logging
import re
import time
from typing import Set
import requests
from bs4 import BeautifulSoup
import pandas as pd

# Module-level logging setup
logger = logging.getLogger(__name__)


def clean_symbol(symbol: str) -> str:
    """Clean stock symbol by removing non-breaking spaces and whitespace."""
    return symbol.replace('\xa0', ' ').replace('\u00a0', ' ').strip()


class NSEFetcher:
    """
    Fetches index constituents from NSE India API.

    Supports all NSE indices including:
    - NIFTY 50
    - NIFTY NEXT 50
    - NIFTY MIDCAP 150
    - NIFTY SMALLCAP 250

    Falls back to CSV archive if API fails.
    """

    def __init__(self):
        """Initialize NSE fetcher with default headers."""
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        self.base_url = "https://www.nseindia.com"
        self.api_url = "https://www.nseindia.com/api/equity-stockIndices"

    def fetch(self, params: dict) -> Set[str]:
        """
        Fetch constituents from NSE India API.

        Args:
            params: Dictionary containing:
                - index_name: NSE index name (e.g., "NIFTY 50")

        Returns:
            Set of stock symbols (tickers)
        """
        index_name = params.get('index_name')
        if not index_name:
            logger.error("NSE: index_name not specified in params")
            return set()

        try:
            # Build API URL with encoded index name
            url = f"{self.api_url}?index={index_name.replace(' ', '%20')}"

            # Create session and establish connection
            session = requests.Session()
            session.get(self.base_url, headers=self.headers, timeout=10)
            time.sleep(1)  # Rate limiting

            # Fetch index data
            response = session.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()

            data = response.json()
            constituents = set()

            # Extract symbols from response
            for item in data.get('data', []):
                symbol = item.get('symbol', '')
                # Filter out the index name itself from constituents
                if symbol and symbol != index_name:
                    constituents.add(symbol)

            logger.info(f"NSE API: Fetched {len(constituents)} constituents for {index_name}")
            return constituents

        except Exception as e:
            logger.warning(f"NSE API error for {index_name}: {e}")
            return self._fetch_nse_csv_fallback(index_name)

    def _fetch_nse_csv_fallback(self, index_name: str) -> Set[str]:
        """
        Fallback to NSE CSV archive when API fails.

        Args:
            index_name: NSE index name

        Returns:
            Set of stock symbols
        """
        try:
            # Build CSV URL (removes spaces and converts to lowercase)
            csv_url = f"https://archives.nseindia.com/content/indices/ind_{index_name.replace(' ', '').lower()}list.csv"

            logger.info(f"NSE CSV fallback: Fetching from {csv_url}")
            df = pd.read_csv(csv_url)

            # Column 2 (index 2) typically contains the symbol
            symbols = set(df.iloc[:, 2].dropna().astype(str).tolist())

            # Filter out index name
            symbols.discard(index_name)

            logger.info(f"NSE CSV: Fetched {len(symbols)} constituents for {index_name}")
            return symbols

        except Exception as e:
            logger.error(f"NSE CSV fallback failed for {index_name}: {e}")
            return set()


class NasdaqFetcher:
    """
    Fetches Nasdaq 100 constituents from Wikipedia.

    Wikipedia maintains an up-to-date table of Nasdaq 100 constituents
    which is more reliable than scraping the official Nasdaq website.
    """

    def __init__(self):
        """Initialize Nasdaq fetcher with default headers."""
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html'
        }
        self.wiki_url = "https://en.wikipedia.org/wiki/Nasdaq-100"

    def fetch(self, params: dict) -> Set[str]:
        """
        Fetch Nasdaq 100 constituents from Wikipedia.

        Args:
            params: Dictionary containing:
                - index_symbol: Index symbol (e.g., "NDX")

        Returns:
            Set of stock ticker symbols
        """
        try:
            logger.info("Nasdaq: Fetching from Wikipedia")
            response = requests.get(self.wiki_url, headers=self.headers, timeout=15)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')
            constituents = set()

            # Find the constituents table
            table = soup.find('table', {'id': 'constituents'})

            if not table:
                # Fallback: find wikitable with "Ticker" header
                tables = soup.find_all('table', {'class': 'wikitable'})
                for t in tables:
                    headers_row = t.find('tr')
                    if headers_row:
                        header_text = headers_row.get_text().lower()
                        if 'ticker' in header_text or 'symbol' in header_text:
                            table = t
                            break

            if not table:
                logger.warning("Nasdaq: Could not find constituents table")
                return set()

            # Find the ticker column index
            ticker_col_idx = self._find_ticker_column(table)

            # Extract tickers from data rows
            rows = table.find_all('tr')[1:]  # Skip header row
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) > ticker_col_idx:
                    ticker_cell = cells[ticker_col_idx]
                    ticker = ticker_cell.get_text().strip()

                    # Valid ticker: 1-5 uppercase letters
                    if ticker and re.match(r'^[A-Z]{1,5}$', ticker):
                        constituents.add(ticker)

            # Validate result
            if len(constituents) < 90:
                logger.warning(f"Nasdaq: Only found {len(constituents)} stocks, expected ~100")

            logger.info(f"Nasdaq: Fetched {len(constituents)} constituents")
            return constituents

        except Exception as e:
            logger.error(f"Nasdaq fetch error: {e}")
            return set()

    def _find_ticker_column(self, table) -> int:
        """
        Find the ticker column index in the table.

        Args:
            table: BeautifulSoup table element

        Returns:
            Column index for ticker symbols (defaults to 1)
        """
        header_row = table.find('tr')
        ticker_col_idx = None

        if header_row:
            header_cells = header_row.find_all(['th', 'td'])
            for idx, cell in enumerate(header_cells):
                cell_text = cell.get_text().strip().lower()
                if cell_text in ('ticker', 'symbol', 'ticker symbol'):
                    ticker_col_idx = idx
                    break

        # Default to second column if not found
        return ticker_col_idx if ticker_col_idx is not None else 1


class VanguardFetcher:
    """
    Fetches holdings from Vanguard ETFs using their official API.

    Supports all Vanguard ETFs including:
    - VXUS (Total International Stock ETF)
    - VTI (Total Stock Market ETF)
    - And others

    Returns top 500 holdings by weight.
    """

    def __init__(self):
        """Initialize Vanguard fetcher with default headers."""
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
        }
        self.api_base_url = "https://investor.vanguard.com/investment-products/etfs/profile/api"

    def fetch(self, params: dict) -> Set[str]:
        """
        Fetch holdings from Vanguard ETF using their official API.

        Args:
            params: Dictionary containing:
                - ticker: ETF ticker symbol (e.g., "VXUS", "VTI")
                - fund_id: Optional fund ID (not used, kept for compatibility)

        Returns:
            Set of stock ticker symbols (top 500 holdings by weight)
        """
        ticker = params.get('ticker', 'VXUS').upper()

        try:
            # Vanguard API returns top 500 holdings sorted by weight
            url = f"{self.api_base_url}/{ticker}/portfolio-holding/stock"

            logger.info(f"Vanguard: Fetching holdings for {ticker}")
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()

            data = response.json()
            constituents = set()

            # Extract holdings
            holdings = data.get('fund', {}).get('entity', [])
            total_available = data.get('size', len(holdings))

            for holding in holdings:
                ticker_symbol = holding.get('ticker', '').strip()
                # Validate ticker format (1-12 alphanumeric characters, including dots/slashes)
                if ticker_symbol and re.match(r'^[A-Z0-9./]{1,12}$', ticker_symbol):
                    constituents.add(ticker_symbol)

            # Log info about holdings
            if total_available > len(holdings):
                logger.info(
                    f"Vanguard {ticker}: Tracking top {len(constituents)} "
                    f"of {total_available} total holdings"
                )
            else:
                logger.info(f"Vanguard {ticker}: Fetched {len(constituents)} holdings")

            return constituents

        except requests.exceptions.HTTPError as e:
            logger.warning(f"Vanguard API HTTP error for {ticker}: {e}")
            return set()
        except Exception as e:
            logger.error(f"Vanguard API error for {ticker}: {e}")
            return set()


class InvescoFetcher:
    """
    Fetches holdings from Invesco ETFs.

    Note: Invesco's website has bot protection, so this fetcher
    delegates to NasdaqFetcher for QQQM (which tracks Nasdaq 100).

    For other Invesco ETFs, manual CSV download is required.
    """

    def __init__(self):
        """Initialize Invesco fetcher."""
        self.nasdaq_fetcher = NasdaqFetcher()

    def fetch(self, params: dict) -> Set[str]:
        """
        Fetch holdings from Invesco ETF.

        Args:
            params: Dictionary containing:
                - ticker: ETF ticker symbol (e.g., "QQQM")

        Returns:
            Set of stock ticker symbols
        """
        ticker = params.get('ticker', 'QQQM').upper()

        # QQQM tracks Nasdaq 100, so use Nasdaq fetcher
        if ticker == 'QQQM':
            logger.info(f"Invesco {ticker}: Using Nasdaq 100 constituents (same underlying index)")
            return self.nasdaq_fetcher.fetch({'index_symbol': 'NDX'})

        # For other Invesco ETFs, manual download required
        logger.warning(
            f"Invesco {ticker}: Manual CSV download required from invesco.com. "
            "Bot protection prevents automated fetching."
        )
        return set()
