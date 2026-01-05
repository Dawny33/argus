# Mutual Fund Tracking Guide

## Overview

Argus now supports tracking Indian mutual fund portfolio holdings alongside index constituents. The system monitors monthly portfolio changes and sends email notifications when significant changes are detected.

## Features

- **Monthly Portfolio Monitoring**: Automatically fetches latest portfolio holdings
- **Change Detection**: Tracks additions, exits, and rebalances (≥0.5% by default)
- **International Holdings**: Supports funds with foreign stocks (e.g., Parag Parikh Flexi Cap)
- **Unified Notifications**: Combines index and mutual fund changes in one email
- **Configurable Thresholds**: Customize minimum holding and change percentages

## Supported AMCs

### ✅ Fully Supported (Auto-Fetch)

| AMC | Source Code | Funds Tested | Status |
|-----|-------------|--------------|--------|
| PPFAS (Parag Parikh) | `ppfas_mf` | Flexi Cap, ELSS | Working ✅ |

### ⚠️ Partial Support / In Development

| AMC | Source Code | Status | Notes |
|-----|-------------|--------|-------|
| HDFC Mutual Fund | `hdfc_mf` | Not Working | Website uses JavaScript - requires alternative approach |
| ICICI Prudential | TBD | Not Implemented | - |
| Axis Mutual Fund | TBD | Not Implemented | - |
| Nippon India | TBD | Not Implemented | - |

## Configuration

### Basic Setup

Add mutual funds to `data/config.json`:

```json
{
  "indexes": [
    // ... existing index configs
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
  }
}
```

### PPFAS (Parag Parikh) Funds

**Available Funds:**

| Fund Name | Fund Code | Scheme Name |
|-----------|-----------|-------------|
| Parag Parikh Flexi Cap Fund | PPFCF | Parag Parikh Flexi Cap Fund |
| Parag Parikh ELSS Tax Saver | PPTSF | Parag Parikh ELSS Tax Saver Fund |
| Parag Parikh Liquid Fund | PPLF | Parag Parikh Liquid Fund |
| Parag Parikh Conservative Hybrid Fund | PPCHF | Parag Parikh Conservative Hybrid Fund |
| Parag Parikh Arbitrage Fund | PPAF | Parag Parikh Arbitrage Fund |

**Example Config:**

```json
{
  "name": "Parag Parikh Flexi Cap Fund - Direct Growth",
  "source": "ppfas_mf",
  "params": {
    "scheme_name": "Parag Parikh Flexi Cap Fund",
    "fund_code": "PPFCF"
  }
}
```

## Configuration Parameters

### Thresholds

```json
"thresholds": {
  "mf_percentage_change": 0.5,    // Minimum change to report (in percentage points)
  "min_holding_to_report": 0.5     // Minimum holding size to track (in %)
}
```

**Explanation:**
- `mf_percentage_change`: Only report changes ≥ this value (e.g., 0.5 = report if holding changes by 0.5% or more)
- `min_holding_to_report`: Ignore holdings smaller than this percentage (reduces noise from tiny positions)

## Email Notification Format

### Example Output

```
Portfolio Changes Detected - 2026-01

============================================================
MUTUAL FUND HOLDINGS CHANGES
============================================================

Parag Parikh Flexi Cap Fund - Direct Growth
--------------------------------------------
Period: November 2025

NEW ADDITIONS (2):
  + RELIANCE (2.3%)
  + TCS (1.8%)

COMPLETE EXITS (1):
  - WIPRO (was 1.2%)

SIGNIFICANT INCREASES:
  ICICIBANK: 6.5% -> 7.2% (+0.7%)

SIGNIFICANT DECREASES:
  BHARTIARTL: 3.5% -> 2.8% (-0.7%)
```

## Understanding Portfolio Changes

### Change Types

1. **NEW ADDITIONS**: Stocks added to portfolio (were 0%, now >0%)
2. **COMPLETE EXITS**: Stocks removed from portfolio (were >0%, now 0%)
3. **SIGNIFICANT INCREASES**: Holdings increased by ≥ threshold
4. **SIGNIFICANT DECREASES**: Holdings decreased by ≥ threshold

### International Holdings

The system tracks both Indian and international stocks:
- **Indian stocks**: HDFC Bank, ICICI Bank, Reliance, etc.
- **International stocks**: Alphabet, Meta, Microsoft, Amazon, etc.

Stock names are shown as they appear in fund disclosures.

## Data Sources & Timing

### PPFAS (Parag Parikh)
- **Source**: https://amc.ppfas.com/downloads/portfolio-disclosure/
- **Format**: Excel (.xls) files
- **Update Schedule**: Monthly (within 7 days of month-end per SEBI regulations)
- **Coverage**: Full portfolio with all holdings and percentages

## Troubleshooting

### No Holdings Found

**Possible causes:**
1. **AMC website down or slow**: Try running again later
2. **File format changed**: AMC may have updated their Excel structure
3. **Wrong scheme name**: Check exact scheme name on AMC website

**Solutions:**
- Check logs for specific error messages
- Verify scheme name matches exactly
- Try different fund from same AMC to isolate issue

### Holdings Look Wrong

**Check for:**
1. **Metadata included**: Parser might be picking up row headers (should be filtered)
2. **Percentage format**: Should be in % format (e.g., 8.5 not 0.085)
3. **Old data**: Fund might not have updated disclosure yet

### Timeout Errors

**For slow AMC websites:**
- Default timeout is 60 seconds
- Network issues or slow servers can cause timeouts
- Try running at different times of day

## State Management

### Storage Format

Holdings are stored in `data/previous_state.json`:

```json
{
  "indexes": {
    // ... index data
  },
  "mutual_funds": {
    "Parag Parikh Flexi Cap Fund - Direct Growth": {
      "month": "2025-12",
      "disclosure_date": "2026-01-05",
      "holdings": {
        "HDFC BANK": 8.0,
        "POWER GRID CORPORATION OF INDIA": 5.9,
        "ICICI BANK": 4.9,
        ...
      }
    }
  }
}
```

### First Run Behavior

- **First run**: All holdings are saved as baseline, no changes reported
- **Subsequent runs**: Changes detected by comparing to previous state

## Adding More Funds

### For PPFAS Funds

1. Find the fund on https://amc.ppfas.com/schemes/
2. Note the exact scheme name (e.g., "Parag Parikh Flexi Cap Fund")
3. Check the fund code from portfolio disclosure files (e.g., PPFCF, PPTSF)
4. Add to config.json following the format above

### For Other AMCs (Future)

AMC-specific fetchers need to be implemented for each fund house. This requires:
1. Analyzing AMC website structure
2. Understanding Excel file format
3. Implementing custom parser

**Contribution welcome!** If you want to add support for your AMC, see implementation guide below.

## Implementation Notes

### For Developers: Adding New AMC Support

To add a new AMC fetcher:

1. **Create fetcher method** in `monitor_indexes.py`:
```python
def fetch_from_xyz_mf(self, params: dict) -> Dict[str, float]:
    # Fetch portfolio page
    # Download Excel/CSV file
    # Parse to extract holdings
    # Return {stock_name: percentage}
```

2. **Create parser method**:
```python
def _parse_xyz_excel(self, excel_file: BytesIO, scheme_name: str) -> Dict[str, float]:
    # Handle AMC-specific Excel structure
    # Extract stock names and percentages
    # Clean and normalize data
```

3. **Register handler**:
```python
self.mf_source_handlers = {
    'xyz_mf': self.fetch_from_xyz_mf,
}
```

4. **Test thoroughly** with multiple funds from the AMC

### Parser Best Practices

- Handle multiple Excel formats (.xls, .xlsx)
- Skip header/footer rows
- Filter out metadata (totals, returns, etc.)
- Normalize stock names (remove "Limited", ".Ltd", etc.)
- Convert percentage formats correctly
- Set reasonable limits (e.g., max 25% single holding)

## Limitations

### Current Limitations

1. **Limited AMC Coverage**: Only PPFAS fully supported currently
2. **JavaScript Websites**: AMCs using dynamic content (like HDFC) require different approach
3. **Manual Configuration**: Need to manually add each fund to config
4. **Monthly Data Only**: No intraday or weekly data
5. **No Historical Tracking**: Only tracks changes since last run

### Planned Improvements

- Add support for more AMCs (ICICI, Axis, Nippon, SBI, etc.)
- Handle JavaScript-rendered websites (using Selenium or API endpoints)
- Improve stock name normalization
- Add sector allocation tracking
- Historical change tracking beyond previous month

## FAQ

**Q: How often should I run the monitor?**
A: Monthly is sufficient. Funds update portfolios once per month per SEBI regulations.

**Q: Will this work with Regular plans or only Direct plans?**
A: Works with both. Portfolio composition is same for Direct and Regular plans.

**Q: Can I track debt funds?**
A: Yes, but the parser may need adjustments for debt fund Excel formats which differ from equity funds.

**Q: What about fund performance/NAV tracking?**
A: This tool only tracks portfolio holdings changes, not NAV or performance. Use fund house websites or apps for NAV tracking.

**Q: How to track more than 10 funds?**
A: No limit! Add as many funds as you want to the config. Just be mindful of rate limiting (2 sec delay between funds).

**Q: Can I customize the email format?**
A: Yes, modify the `format_mf_changes()` method in `monitor_indexes.py`.

## Support

For issues or questions:
1. Check this guide first
2. Review error logs for specific messages
3. Open an issue on GitHub with full error details

## Example Complete Config

```json
{
  "indexes": [
    {
      "name": "Nifty 50",
      "source": "nse_api",
      "params": {"index_name": "NIFTY 50"}
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
    },
    {
      "name": "Parag Parikh ELSS Tax Saver - Direct Growth",
      "source": "ppfas_mf",
      "params": {
        "scheme_name": "Parag Parikh ELSS Tax Saver Fund",
        "fund_code": "PPTSF"
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

---

**Happy Monitoring!** 📊
