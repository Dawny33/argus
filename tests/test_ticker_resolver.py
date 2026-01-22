"""Tests for TickerResolver class."""
import json
import pytest
from unittest.mock import Mock, patch, MagicMock

from src.resolvers.ticker_resolver import TickerResolver


class TestTickerResolver:
    """Test cases for TickerResolver."""

    def test_init_without_api_key(self):
        """Test initialization without API key."""
        with patch.dict('os.environ', {}, clear=True):
            resolver = TickerResolver()
            assert not resolver.is_available()
            assert resolver.client is None

    def test_init_with_api_key(self):
        """Test initialization with API key."""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('src.resolvers.ticker_resolver.Anthropic') as mock_anthropic:
                resolver = TickerResolver()
                assert resolver.is_available()
                mock_anthropic.assert_called_once_with(api_key='test-key')

    def test_resolve_tickers_not_available(self):
        """Test resolve_tickers when resolver is not available."""
        with patch.dict('os.environ', {}, clear=True):
            resolver = TickerResolver()
            result = resolver.resolve_tickers("Added: + ANTO", "VXUS")
            assert result == {}

    def test_resolve_tickers_indian_market(self):
        """Test resolve_tickers for Indian market."""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('src.resolvers.ticker_resolver.Anthropic') as mock_anthropic:
                # Setup mock response
                mock_client = MagicMock()
                mock_anthropic.return_value = mock_client

                mock_response = MagicMock()
                mock_response.content = [MagicMock(text='{"TCS": "Tata Consultancy Services", "INFY": "Infosys Limited"}')]
                mock_client.messages.create.return_value = mock_response

                resolver = TickerResolver()
                result = resolver.resolve_tickers("Added: + TCS, + INFY", "Nifty 50")

                assert result == {
                    "TCS": "Tata Consultancy Services",
                    "INFY": "Infosys Limited"
                }

                # Verify the prompt contains Indian market context
                call_args = mock_client.messages.create.call_args
                prompt = call_args[1]['messages'][0]['content']
                assert 'Indian stock market (NSE/BSE)' in prompt
                assert 'Nifty 50' in prompt

    def test_resolve_tickers_international_market(self):
        """Test resolve_tickers for international market."""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('src.resolvers.ticker_resolver.Anthropic') as mock_anthropic:
                # Setup mock response
                mock_client = MagicMock()
                mock_anthropic.return_value = mock_client

                mock_response = MagicMock()
                mock_response.content = [MagicMock(text='{"ANTO": "Antofagasta plc", "BOL": "Boliden AB"}')]
                mock_client.messages.create.return_value = mock_response

                resolver = TickerResolver()
                result = resolver.resolve_tickers("Added: + ANTO, + BOL", "VXUS")

                assert result == {
                    "ANTO": "Antofagasta plc",
                    "BOL": "Boliden AB"
                }

                # Verify the prompt contains international market context
                call_args = mock_client.messages.create.call_args
                prompt = call_args[1]['messages'][0]['content']
                assert 'International stock market' in prompt
                assert 'VXUS' in prompt

    def test_resolve_tickers_with_markdown_code_blocks(self):
        """Test resolve_tickers handles markdown code blocks in response."""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('src.resolvers.ticker_resolver.Anthropic') as mock_anthropic:
                # Setup mock response with markdown code blocks
                mock_client = MagicMock()
                mock_anthropic.return_value = mock_client

                mock_response = MagicMock()
                mock_response.content = [MagicMock(text='```json\n{"AAPL": "Apple Inc."}\n```')]
                mock_client.messages.create.return_value = mock_response

                resolver = TickerResolver()
                result = resolver.resolve_tickers("Added: + AAPL", "Nasdaq 100")

                assert result == {"AAPL": "Apple Inc."}

    def test_resolve_tickers_api_error(self):
        """Test resolve_tickers handles API errors gracefully."""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('src.resolvers.ticker_resolver.Anthropic') as mock_anthropic:
                # Setup mock to raise exception
                mock_client = MagicMock()
                mock_anthropic.return_value = mock_client
                mock_client.messages.create.side_effect = Exception("API Error")

                resolver = TickerResolver()
                result = resolver.resolve_tickers("Added: + AAPL", "Nasdaq 100")

                assert result == {}

    def test_format_with_company_names(self):
        """Test format_with_company_names method."""
        resolver = TickerResolver()

        ticker_map = {
            "ANTO": "Antofagasta plc",
            "BOL": "Boliden AB",
            "UNKNOWN": "Unknown Company"
        }

        tickers = ["ANTO", "BOL", "UNKNOWN", "NOTFOUND"]
        result = resolver.format_with_company_names(tickers, ticker_map)

        assert result == [
            "ANTO (Antofagasta plc)",
            "BOL (Boliden AB)",
            "UNKNOWN",  # Unknown Company is not included
            "NOTFOUND"  # Not in map
        ]

    def test_format_with_empty_ticker_map(self):
        """Test format_with_company_names with empty ticker map."""
        resolver = TickerResolver()

        tickers = ["AAPL", "GOOGL"]
        result = resolver.format_with_company_names(tickers, {})

        assert result == ["AAPL", "GOOGL"]
