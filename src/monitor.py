"""Main Portfolio Monitor orchestration class."""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import time

from src.fetchers.gmail_fetcher import GmailPortfolioFetcher
from src.fetchers.index_fetchers import NSEFetcher, NasdaqFetcher, VanguardFetcher, InvescoFetcher
from src.fetchers.mf_fetchers import PPFASFetcher, TataFetcher, QuantFetcher, BandhanFetcher, HDFCFetcher
from src.detectors.change_detector import MFChangeDetector, detect_index_changes
from src.resolvers.ticker_resolver import TickerResolver
from src.formatters.email_formatter import EmailFormatter
from src.notifiers.email_notifier import EmailNotifier

logger = logging.getLogger(__name__)


class PortfolioMonitor:
    """
    Main orchestrator for portfolio monitoring.

    Coordinates fetching, change detection, and notification for both
    index constituents and mutual fund holdings.
    """

    def __init__(self, data_dir: str = "data", gmail_credentials: Optional[Dict[str, str]] = None,
                 anthropic_api_key: Optional[str] = None):
        """
        Initialize the portfolio monitor.

        Args:
            data_dir: Directory for storing config and state files
            gmail_credentials: Optional dict with 'email' and 'password' for Gmail fetching
            anthropic_api_key: Optional Anthropic API key for ticker resolution
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)

        self.config_file = self.data_dir / "config.json"
        self.state_file = self.data_dir / "previous_state.json"

        # Load configuration
        self.config = self._load_config()

        # Initialize fetchers
        self._init_fetchers(gmail_credentials)

        # Initialize detectors and resolvers
        self.mf_detector = MFChangeDetector(
            threshold=self.config.get('thresholds', {}).get('mf_percentage_change', 0.5)
        )
        self.ticker_resolver = TickerResolver(api_key=anthropic_api_key)

        # Initialize formatter and notifier
        self.formatter = EmailFormatter(self.config, self.ticker_resolver)
        self.notifier = EmailNotifier(self.config.get('email', {}))

    def _load_config(self) -> Dict:
        """Load configuration from config.json."""
        if self.config_file.exists():
            with open(self.config_file, 'r') as f:
                return json.load(f)

        # Default configuration
        return {
            "indexes": [],
            "mutual_funds": [],
            "thresholds": {
                "mf_percentage_change": 0.5,
                "min_holding_to_report": 0.5
            },
            "email": {
                "smtp_server": "smtp.gmail.com",
                "smtp_port": 587
            }
        }

    def _init_fetchers(self, gmail_credentials: Optional[Dict[str, str]]):
        """Initialize all data fetchers."""
        # Index fetchers
        self.index_fetchers = {
            'nse_api': NSEFetcher(),
            'nasdaq_official': NasdaqFetcher(),
            'vanguard_etf': VanguardFetcher(),
            'invesco_etf': InvescoFetcher(),
        }

        # Gmail fetcher (optional)
        self.gmail_fetcher = None
        if gmail_credentials:
            try:
                self.gmail_fetcher = GmailPortfolioFetcher(
                    gmail_credentials['email'],
                    gmail_credentials['password']
                )
                logger.info("Gmail portfolio fetcher initialized")
            except Exception as e:
                logger.warning(f"Could not initialize Gmail fetcher: {e}")

        # Mutual fund fetchers
        min_holding = self.config.get('thresholds', {}).get('min_holding_to_report', 0.5)
        self.mf_fetchers = {
            'ppfas_mf': PPFASFetcher(min_holding_to_report=min_holding),
            'tata_mf': TataFetcher(min_holding_to_report=min_holding),
            'quant_mf': QuantFetcher(min_holding_to_report=min_holding),
            'bandhan_mf': BandhanFetcher(min_holding_to_report=min_holding, data_dir=self.data_dir),
            'hdfc_mf': HDFCFetcher(min_holding_to_report=min_holding),
        }

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

        # Fetch indexes
        for index_config in self.config.get('indexes', []):
            index_name = index_config['name']
            source = index_config['source']
            params = index_config.get('params', {})

            logger.info(f"Fetching constituents for {index_name}...")

            fetcher = self.index_fetchers.get(source)
            if not fetcher:
                logger.error(f"Unknown source type: {source}")
                continue

            try:
                constituents = fetcher.fetch(params)
                current_state['indexes'][index_name] = sorted(list(constituents))
                logger.info(f"  {index_name}: Found {len(constituents)} constituents")
            except Exception as e:
                logger.error(f"Error fetching {index_name}: {e}")
                current_state['indexes'][index_name] = []

            time.sleep(2)  # Rate limiting

        # Fetch mutual funds
        for fund_config in self.config.get('mutual_funds', []):
            # Skip disabled funds
            if not fund_config.get('_enabled', True):
                logger.info(f"Skipping disabled fund: {fund_config['name']}")
                continue

            fund_name = fund_config['name']
            source = fund_config['source']
            params = fund_config.get('params', {})

            logger.info(f"Fetching holdings for {fund_name}...")

            fetcher = self.mf_fetchers.get(source)
            if not fetcher:
                logger.error(f"  Unknown MF source type: {source}")
                continue

            try:
                holdings = fetcher.fetch(params, gmail_fetcher=self.gmail_fetcher)
                current_state['mutual_funds'][fund_name] = {
                    'month': datetime.now().strftime('%Y-%m'),
                    'disclosure_date': datetime.now().strftime('%Y-%m-%d'),
                    'holdings': holdings
                }
                logger.info(f"  Found {len(holdings)} holdings for {fund_name}")
            except Exception as e:
                logger.error(f"Error fetching {fund_name}: {e}")
                current_state['mutual_funds'][fund_name] = {
                    'month': datetime.now().strftime('%Y-%m'),
                    'disclosure_date': datetime.now().strftime('%Y-%m-%d'),
                    'holdings': {}
                }

            time.sleep(2)  # Rate limiting

        return current_state

    def load_previous_state(self) -> Dict:
        """Load previous state from file."""
        if self.state_file.exists():
            with open(self.state_file, 'r') as f:
                return json.load(f)
        return {}

    def save_current_state(self, state: Dict):
        """Save current state to file."""
        with open(self.state_file, 'w') as f:
            json.dump(state, f, indent=2)

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

        # Detect index changes
        logger.info("Detecting index changes...")
        index_changes = detect_index_changes(
            previous_state.get('indexes', {}),
            current_state.get('indexes', {})
        )

        # Detect MF changes
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

        email_body = self.formatter.format_email_body(index_changes, mf_changes)
        print("\n" + email_body)

        # Send email notification
        self.notifier.send_email(subject, email_body)
