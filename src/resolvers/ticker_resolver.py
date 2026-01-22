"""Ticker symbol resolution using Claude LLM."""
import json
import logging
import os
from typing import Dict, List, Optional

from anthropic import Anthropic

logger = logging.getLogger(__name__)


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
                logger.info("TickerResolver initialized with Claude API")
            except Exception as e:
                logger.warning(f"Could not initialize TickerResolver: {e}")
        else:
            logger.warning("ANTHROPIC_API_KEY not found. Ticker resolution will be skipped.")

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
            logger.info(f"Resolved {len(ticker_map)} tickers for {index_name}")
            return ticker_map

        except Exception as e:
            logger.error(f"Error resolving tickers: {e}")
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
