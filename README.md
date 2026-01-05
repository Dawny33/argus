# Argus - Portfolio Monitor

Argus monitors stock index constituents, ETF holdings, and mutual fund portfolios, detecting changes and sending email notifications. Perfect for investors who want to stay informed about index rebalancing events and mutual fund portfolio changes.

## Features

- **Multi-source data fetching** - Supports NSE India, Nasdaq 100, Vanguard ETFs, Invesco ETFs, and Indian Mutual Funds
- **Change detection** - Tracks additions and removals from indexes, plus percentage changes in mutual fund holdings
- **Email notifications** - Unified alerts for both index and mutual fund changes
- **Mutual fund tracking** - Monitor portfolio holdings with configurable thresholds (≥0.5% changes)
- **International holdings** - Tracks both Indian and foreign stocks in mutual funds
- **Configurable** - Easy JSON-based configuration for indexes and mutual funds
- **Production-ready** - Proper logging, error handling, and rate limiting

## Supported Indexes, ETFs & Mutual Funds

### Indexes & ETFs

| Index/ETF | Source | Coverage |
|-----------|--------|----------|
| Nifty 50 | NSE India API | Full |
| Nifty Next 50 | NSE India API | Full |
| Nifty Midcap 150 | NSE India API | Full |
| Nifty Smallcap 250 | NSE India API | Full |
| Nasdaq 100 | Wikipedia | Full |
| VXUS (Vanguard) | Vanguard API | Top 500 holdings |
| QQQM (Invesco) | Nasdaq 100 data | Full |

### Mutual Funds (NEW!)

| AMC | Status | Coverage |
|-----|--------|----------|
| PPFAS (Parag Parikh) | ✅ Working | Full portfolio with all holdings |
| HDFC MF | ⚠️ In Development | - |
| Others | 🚧 Planned | - |

See **[MF-GUIDE.md](MF-GUIDE.md)** for detailed mutual fund configuration and usage.

## Installation

```bash
# Clone the repository
git clone https://github.com/Dawny33/argus.git
cd argus

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Configuration

### Email Setup

Set these environment variables for email notifications:

```bash
export EMAIL_SENDER="your-email@gmail.com"
export EMAIL_PASSWORD="your-app-password"
export EMAIL_RECIPIENT="recipient@example.com"
```

> **Note**: For Gmail, use an [App Password](https://support.google.com/accounts/answer/185833) instead of your regular password.

### Index & Mutual Fund Configuration

Edit `data/config.json` to customize monitored indexes and mutual funds:

```json
{
  "indexes": [
    {
      "name": "Nifty 50",
      "source": "nse_api",
      "params": {"index_name": "NIFTY 50"}
    },
    {
      "name": "VXUS",
      "source": "vanguard_etf",
      "params": {"ticker": "VXUS"}
    }
  ],
  "mutual_funds": [
    {
      "name": "Parag Parikh Flexi Cap Fund - Direct Growth",
      "source": "ppfas_mf",
      "params": {
        "scheme_name": "Parag Parikh Flexi Cap Fund",
        "fund_code": "PPFCF"
      }
    }
  ],
  "thresholds": {
    "mf_percentage_change": 0.5,
    "min_holding_to_report": 0.5
  },
  "email": {
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587
  }
}
```

**For detailed mutual fund configuration, see [MF-GUIDE.md](MF-GUIDE.md)**

### Available Sources

**Index & ETF Sources:**

| Source | Description | Parameters |
|--------|-------------|------------|
| `nse_api` | NSE India stock indexes | `index_name`: e.g., "NIFTY 50" |
| `nasdaq_official` | Nasdaq 100 index | `index_symbol`: e.g., "NDX" |
| `vanguard_etf` | Vanguard ETF holdings | `ticker`: e.g., "VXUS", "VTI" |
| `invesco_etf` | Invesco ETF holdings | `ticker`: e.g., "QQQM" |

**Mutual Fund Sources:**

| Source | AMC | Parameters |
|--------|-----|------------|
| `ppfas_mf` | PPFAS (Parag Parikh) | `scheme_name`, `fund_code` |

## Usage

### Manual Run

```bash
python monitor_indexes.py
```

### Scheduled Run (Cron)

Add to crontab for monthly monitoring:

```bash
# Run on the 1st of every month at 9 AM
0 9 1 * * cd /path/to/argus && /path/to/venv/bin/python monitor_indexes.py
```

### GitHub Actions

The repository includes a GitHub Actions workflow for automated monthly runs. Set these secrets in your repository:

- `EMAIL_SENDER`
- `EMAIL_PASSWORD`
- `EMAIL_RECIPIENT`

## Output Example

### Index Changes
```
Portfolio Changes Detected - 2026-01

============================================================
INDEX CONSTITUENT CHANGES
============================================================

Nifty 50
--------
Added (2):
  + NEWSTOCK1
  + NEWSTOCK2

Removed (2):
  - OLDSTOCK1
  - OLDSTOCK2
```

### Mutual Fund Changes
```
============================================================
MUTUAL FUND HOLDINGS CHANGES
============================================================

Parag Parikh Flexi Cap Fund - Direct Growth
--------------------------------------------
Period: November 2025

NEW ADDITIONS (2):
  + RELIANCE (2.3%)
  + TCS (1.8%)

SIGNIFICANT INCREASES:
  ICICIBANK: 6.5% -> 7.2% (+0.7%)

SIGNIFICANT DECREASES:
  BHARTIARTL: 3.5% -> 2.8% (-0.7%)
```

## Project Structure

```
argus/
├── monitor_indexes.py       # Main application
├── requirements.txt         # Python dependencies
├── README.md               # This file
├── MF-GUIDE.md            # Mutual fund tracking guide
├── data/
│   ├── config.json         # Index & MF configuration
│   └── previous_state.json # Last known state (indexes + MFs)
└── .github/
    └── workflows/          # GitHub Actions
```

## Adding New Indexes

1. Identify the data source for the index
2. Add a new source handler method in `IndexMonitor` class
3. Register the handler in `self.source_handlers`
4. Add the index to `config.json`

Example for adding a new source:

```python
def fetch_from_new_source(self, params: dict) -> Set[str]:
    """Fetch constituents from new source."""
    # Implement fetching logic
    return set_of_ticker_symbols
```

## Limitations

### Indexes & ETFs
- **Vanguard ETFs**: Only top 500 holdings are tracked (API limitation)
- **Invesco ETFs**: Uses Nasdaq 100 data for QQQM (direct API requires authentication)

### Mutual Funds
- **Limited AMC coverage**: Currently only PPFAS (Parag Parikh) fully supported
- **Monthly data only**: Funds update portfolios monthly per SEBI regulations
- **Excel format dependency**: Requires AMC to publish data in parseable Excel format

### General
- **Rate limiting**: 2-second delay between requests to avoid blocking

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License - see LICENSE file for details.
