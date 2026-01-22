"""Data fetchers for indexes, ETFs, and mutual funds."""
from .gmail_fetcher import GmailPortfolioFetcher
from .index_fetchers import NSEFetcher, NasdaqFetcher, VanguardFetcher, InvescoFetcher
from .mf_fetchers import PPFASFetcher, TataFetcher, QuantFetcher, BandhanFetcher, HDFCFetcher

__all__ = [
    'GmailPortfolioFetcher',
    'NSEFetcher',
    'NasdaqFetcher',
    'VanguardFetcher',
    'InvescoFetcher',
    'PPFASFetcher',
    'TataFetcher',
    'QuantFetcher',
    'BandhanFetcher',
    'HDFCFetcher',
]
