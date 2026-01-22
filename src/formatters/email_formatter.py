"""Email body formatting for change reports."""
import logging
from datetime import datetime
from typing import Dict, List, Optional

from src.detectors.change_detector import MFChangeDetector
from src.resolvers.ticker_resolver import TickerResolver

logger = logging.getLogger(__name__)


class EmailFormatter:
    """Formats portfolio changes into email body text."""

    def __init__(self, config: Dict, ticker_resolver: Optional[TickerResolver] = None):
        """
        Initialize the email formatter.

        Args:
            config: Configuration dict containing indexes, mutual_funds, and thresholds
            ticker_resolver: Optional TickerResolver for converting tickers to company names
        """
        self.config = config
        self.ticker_resolver = ticker_resolver or TickerResolver()
        self.mf_detector = MFChangeDetector(
            threshold=config.get('thresholds', {}).get('mf_percentage_change', 0.5)
        )

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

    def format_email_body(self, index_changes: Dict[str, Dict[str, List[str]]],
                         mf_changes: Optional[Dict] = None) -> str:
        """
        Format unified email body with both index and MF changes.

        Args:
            index_changes: Index changes {index_name: {'added': [...], 'removed': [...]}}
            mf_changes: MF changes {fund_name: {'changes': {...}, 'month': '2025-12'}}

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
