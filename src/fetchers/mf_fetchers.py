#!/usr/bin/env python3
"""
Mutual Fund Fetchers
Fetches holdings from various Indian mutual fund AMCs (Asset Management Companies).

Each fetcher class handles:
- Downloading portfolio disclosure Excel files from AMC websites or Gmail
- Parsing Excel files to extract stock holdings and percentages
- Returning structured holdings data

Supported AMCs:
- HDFC Mutual Fund
- PPFAS (Parag Parikh) Mutual Fund
- Tata Mutual Fund
- Quant Mutual Fund
- Bandhan Mutual Fund
"""

import logging
import time
from io import BytesIO
from typing import Dict, Optional

import pandas as pd
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from pathlib import Path

# Module-level logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def _get_selenium_driver(data_dir: Optional[Path] = None):
    """
    Create and return a headless Chrome WebDriver instance.

    Args:
        data_dir: Optional directory for downloads. If None, uses current directory.

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
    if data_dir is None:
        data_dir = Path.cwd()
    download_dir = str(data_dir / 'temp_downloads')
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


class HDFCFetcher:
    """
    Fetcher for HDFC Mutual Fund holdings.
    Downloads and parses monthly portfolio Excel files from HDFC's official website.
    """

    def __init__(self, min_holding_to_report: float = 0.5):
        """
        Initialize HDFC fetcher.

        Args:
            min_holding_to_report: Minimum percentage threshold for reporting holdings (default: 0.5%)
        """
        self.min_holding_to_report = min_holding_to_report

    def fetch(self, params: dict, gmail_fetcher=None) -> Dict[str, float]:
        """
        Fetch mutual fund holdings from HDFC Mutual Fund.
        Downloads and parses monthly portfolio Excel file.

        Args:
            params: Dict containing:
                - scheme_name: Full scheme name (e.g., "HDFC Flexi Cap Fund")
                - scheme_code: Optional scheme code for validation
            gmail_fetcher: Optional GmailPortfolioFetcher instance (not used by HDFC)

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

        Args:
            excel_file: BytesIO object containing Excel file data
            scheme_name: Name of the scheme to parse

        Returns:
            Dict mapping stock symbol to percentage
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
                    if pct >= self.min_holding_to_report:
                        holdings[stock] = round(pct, 1)
                except (ValueError, TypeError):
                    continue

            return holdings

        except Exception as e:
            logger.error(f"  Error parsing HDFC Excel: {e}")
            return {}


class PPFASFetcher:
    """
    Fetcher for PPFAS (Parag Parikh) Mutual Fund holdings.
    Tries Gmail first (portfolio disclosure emails), then falls back to direct website.
    """

    def __init__(self, min_holding_to_report: float = 0.5):
        """
        Initialize PPFAS fetcher.

        Args:
            min_holding_to_report: Minimum percentage threshold for reporting holdings (default: 0.5%)
        """
        self.min_holding_to_report = min_holding_to_report

    def fetch(self, params: dict, gmail_fetcher=None) -> Dict[str, float]:
        """
        Fetch mutual fund holdings from PPFAS (Parag Parikh) Mutual Fund.
        Tries Gmail first (portfolio disclosure emails), then falls back to direct website.

        Args:
            params: Dict containing:
                - scheme_name: Full scheme name (e.g., "Parag Parikh Flexi Cap Fund")
                - fund_code: Optional fund code (PPFCF, PPTSF, etc.)
            gmail_fetcher: Optional GmailPortfolioFetcher instance for email-based fetching

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
            if gmail_fetcher:
                logger.info(f"  Trying Gmail for PPFAS portfolio disclosure emails...")
                try:
                    # Use "Parag Parikh" for AMC name
                    download_url = gmail_fetcher.fetch_portfolio_from_email(
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

        Args:
            excel_file: BytesIO object containing Excel file data
            scheme_name: Name of the scheme to parse

        Returns:
            Dict mapping stock symbol to percentage
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
                    if pct_value < self.min_holding_to_report or pct_value > 25:  # Max 25% for single holding
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


class TataFetcher:
    """
    Fetcher for Tata Mutual Fund holdings.
    Tries Gmail first (portfolio disclosure emails), then falls back to Advisorkhoj.
    """

    def __init__(self, min_holding_to_report: float = 0.5):
        """
        Initialize Tata fetcher.

        Args:
            min_holding_to_report: Minimum percentage threshold for reporting holdings (default: 0.5%)
        """
        self.min_holding_to_report = min_holding_to_report

    def fetch(self, params: dict, gmail_fetcher=None) -> Dict[str, float]:
        """
        Fetch mutual fund holdings from Tata Mutual Fund.
        Tries Gmail first (portfolio disclosure emails), then falls back to Advisorkhoj.

        Args:
            params: Dict containing:
                - sheet_code: Scheme code (e.g., "TTSF96" for TATA ELSS FUND)
                - scheme_name: Optional full scheme name
            gmail_fetcher: Optional GmailPortfolioFetcher instance for email-based fetching

        Returns:
            Dict mapping stock symbol to percentage
        """
        sheet_code = params.get('sheet_code', '')
        scheme_name = params.get('scheme_name', sheet_code)

        try:
            # Try Gmail first
            if gmail_fetcher:
                logger.info(f"  Trying Gmail for Tata portfolio disclosure emails...")
                try:
                    download_url = gmail_fetcher.fetch_portfolio_from_email(
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

        Args:
            excel_file: BytesIO object containing Excel file data
            sheet_code: Sheet code/name for the specific scheme
            scheme_name: Name of the scheme to parse

        Returns:
            Dict mapping stock symbol to percentage
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
                    if pct_value >= self.min_holding_to_report:
                        holdings[stock_clean] = round(pct_value, 1)
                except (ValueError, TypeError):
                    continue

            return holdings

        except Exception as e:
            logger.error(f"  Error parsing Tata MF Excel: {e}")
            return {}


class QuantFetcher:
    """
    Fetcher for Quant Mutual Fund holdings.
    Tries Gmail first (portfolio disclosure emails), then falls back to Advisorkhoj.
    """

    def __init__(self, min_holding_to_report: float = 0.5):
        """
        Initialize Quant fetcher.

        Args:
            min_holding_to_report: Minimum percentage threshold for reporting holdings (default: 0.5%)
        """
        self.min_holding_to_report = min_holding_to_report

    def fetch(self, params: dict, gmail_fetcher=None) -> Dict[str, float]:
        """
        Fetch mutual fund holdings from Quant Mutual Fund.
        Tries Gmail first (portfolio disclosure emails), then falls back to Advisorkhoj.

        Args:
            params: Dict containing:
                - scheme_name: Full scheme name (e.g., "Quant Small Cap Fund")
            gmail_fetcher: Optional GmailPortfolioFetcher instance for email-based fetching

        Returns:
            Dict mapping stock symbol to percentage
        """
        scheme_name = params.get('scheme_name', '')

        try:
            # Try Gmail first
            if gmail_fetcher:
                logger.info(f"  Trying Gmail for Quant portfolio disclosure emails...")
                try:
                    download_url = gmail_fetcher.fetch_portfolio_from_email(
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

        Args:
            excel_file: BytesIO object containing Excel file data
            scheme_name: Name of the scheme to parse

        Returns:
            Dict mapping stock symbol to percentage
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
                    if pct_value >= self.min_holding_to_report:
                        holdings[stock_clean] = round(pct_value, 1)
                except (ValueError, TypeError):
                    continue

            return holdings

        except Exception as e:
            logger.error(f"  Error parsing Quant Excel: {e}")
            return {}


class BandhanFetcher:
    """
    Fetcher for Bandhan Mutual Fund holdings.
    Tries Gmail first (portfolio disclosure emails), then falls back to Advisorkhoj and Selenium.
    """

    def __init__(self, min_holding_to_report: float = 0.5, data_dir: Optional[Path] = None):
        """
        Initialize Bandhan fetcher.

        Args:
            min_holding_to_report: Minimum percentage threshold for reporting holdings (default: 0.5%)
            data_dir: Optional directory for Selenium downloads
        """
        self.min_holding_to_report = min_holding_to_report
        self.data_dir = data_dir or Path.cwd()

    def fetch(self, params: dict, gmail_fetcher=None) -> Dict[str, float]:
        """
        Fetch mutual fund holdings from Bandhan Mutual Fund.
        Tries Gmail first (portfolio disclosure emails), then falls back to Advisorkhoj and Selenium.

        Args:
            params: Dict containing:
                - scheme_name: Full scheme name (e.g., "Bandhan ELSS Tax Saver Fund")
            gmail_fetcher: Optional GmailPortfolioFetcher instance for email-based fetching

        Returns:
            Dict mapping stock symbol to percentage
        """
        scheme_name = params.get('scheme_name', '')

        try:
            # STEP 1: Try Gmail first (most reliable - uses investor's disclosure emails)
            if gmail_fetcher:
                logger.info(f"  Trying Gmail for Bandhan portfolio disclosure emails...")
                try:
                    download_url = gmail_fetcher.fetch_portfolio_from_email(
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

        Args:
            scheme_name: Name of the scheme to fetch

        Returns:
            Dict mapping stock symbol to percentage
        """
        driver = None
        try:
            logger.info(f"  Launching headless Chrome browser...")
            driver = _get_selenium_driver(self.data_dir)

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

        Args:
            excel_file: BytesIO object containing Excel file data
            scheme_name: Name of the scheme to parse

        Returns:
            Dict mapping stock symbol to percentage
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

                    if pct_value >= self.min_holding_to_report:
                        holdings[stock_clean] = round(pct_value, 1)
                except (ValueError, TypeError):
                    continue

            return holdings

        except Exception as e:
            logger.error(f"  Error parsing Bandhan Excel: {e}")
            return {}
