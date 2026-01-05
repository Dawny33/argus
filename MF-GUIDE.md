# Mutual Fund Tracking Guide

Complete guide to adding and tracking Indian mutual funds in Argus.

## Table of Contents

- [Overview](#overview)
- [Supported AMCs](#supported-amcs)
- [Quick Start](#quick-start)
- [Adding Mutual Funds](#adding-mutual-funds)
- [Configuration Examples](#configuration-examples)
- [Data Sources](#data-sources)
- [Troubleshooting](#troubleshooting)

---

## Overview

Argus tracks monthly portfolio holdings for Indian mutual funds and notifies you of:

- **New additions** - Stocks added to the portfolio
- **Exits** - Stocks removed from the portfolio
- **Increases** - Holdings increased by ≥0.5% (configurable)
- **Decreases** - Holdings decreased by ≥0.5% (configurable)

### How It Works

1. **Monthly Fetch**: Automatically retrieves portfolio disclosures (SEBI mandate: within 7 days of month-end)
2. **Change Detection**: Compares current vs. previous month to identify rebalancing
3. **Email Notification**: Sends unified alerts for both index and mutual fund changes
4. **State Tracking**: Stores portfolio snapshots in `data/previous_state.json`

---

## Supported AMCs

### ✅ Fully Working

| AMC | Source Code | Tested Funds | Data Sources |
|-----|-------------|--------------|--------------|
| **PPFAS (Parag Parikh)** | `ppfas_mf` | Flexi Cap, ELSS | Gmail → Direct website |
| **Tata Mutual Fund** | `tata_mf` | ELSS, All equity funds | Gmail → Advisorkhoj |
| **Quant Mutual Fund** | `quant_mf` | Small Cap, All funds | Gmail → Advisorkhoj |

### ⚠️ Partial Support

| AMC | Source Code | Status | Notes |
|-----|-------------|--------|-------|
| **Bandhan Mutual Fund** | `bandhan_mf` | Requires Gmail | Advisorkhoj doesn't have files; needs portfolio emails |

### 🚧 Planned / Not Working

| AMC | Status | Notes |
|-----|--------|-------|
| HDFC Mutual Fund | Blocked | Website uses aggressive bot detection |
| ICICI Prudential | Not Implemented | Coming soon |
| Axis Mutual Fund | Not Implemented | Coming soon |
| SBI Mutual Fund | Not Implemented | Coming soon |

---

## Quick Start

### 1. Prerequisites

Ensure you have:
- ✅ Gmail credentials configured (`EMAIL_SENDER`, `EMAIL_PASSWORD`)
- ✅ Python environment set up (see main README.md)
- ✅ All dependencies installed (`pip install -r requirements.txt`)

### 2. Add Your First Fund

Edit `data/config.json` and add a fund to the `mutual_funds` array:

```json
{
  "mutual_funds": [
    {
      "name": "Parag Parikh Flexi Cap Fund - Direct Growth",
      "source": "ppfas_mf",
      "params": {
        "scheme_name": "Parag Parikh Flexi Cap Fund",
        "fund_code": "PPFCF"
      }
    }
  ]
}
```

### 3. Test It

```bash
cd /path/to/argus
source venv/bin/activate
export EMAIL_SENDER="your@email.com"
export EMAIL_PASSWORD="your-app-password"
python monitor_indexes.py
```

You should see output like:
```
✓ Fetching PPFAS portfolio page...
✓ Downloaded Excel file: https://amc.ppfas.com/...
✓ Parsed 28 holdings from PPFAS Excel
```

---

## Adding Mutual Funds

### Step-by-Step Guide

#### Step 1: Identify the AMC

Check if your AMC is supported in the [Supported AMCs](#supported-amcs) table above.

#### Step 2: Get Fund Parameters

Each AMC requires different parameters:

**PPFAS Funds:**
- `scheme_name`: Full fund name (e.g., "Parag Parikh Flexi Cap Fund")
- `fund_code`: Short code (e.g., "PPFCF")

**Tata Funds:**
- `scheme_name`: Full fund name (e.g., "TATA ELSS FUND")
- `sheet_code`: Excel sheet code (e.g., "TTSF96")

**Quant Funds:**
- `scheme_name`: Full fund name (e.g., "Quant Small Cap Fund")

**Bandhan Funds:**
- `scheme_name`: Full fund name (e.g., "Bandhan ELSS Tax Saver Fund")

#### Step 3: Add to Config

Open `data/config.json` and add your fund:

```json
{
  "indexes": [
    // ... your index configs
  ],
  "mutual_funds": [
    {
      "name": "Display Name for Notifications",
      "source": "amc_source_code",
      "params": {
        // AMC-specific parameters
      }
    }
  ]
}
```

#### Step 4: Test the Configuration

Run a test to ensure it fetches correctly:

```bash
python monitor_indexes.py
```

Check the logs for successful fetching and parsing.

---

## Configuration Examples

### PPFAS (Parag Parikh) Funds

**Available Funds:**

| Fund Name | Fund Code | Configuration |
|-----------|-----------|---------------|
| Flexi Cap Fund | PPFCF | See below |
| ELSS Tax Saver | PPTSF | See below |
| Conservative Hybrid | PPCHF | See below |
| Liquid Fund | PPLF | See below |

**Example:**

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

### Tata Mutual Fund

**How to find `sheet_code`:**

1. Visit [Advisorkhoj Tata MF Downloads](https://www.advisorkhoj.com/form-download-centre/Mutual/Tata-Mutual-Fund/Monthly-Portfolio-Disclosures)
2. Download the latest consolidated Excel file
3. Open it and find your fund's sheet name (e.g., "TTSF96" for ELSS)

**Example:**

```json
{
  "name": "Tata ELSS Fund - Direct Growth",
  "source": "tata_mf",
  "params": {
    "sheet_code": "TTSF96",
    "scheme_name": "TATA ELSS FUND"
  }
}
```

**Common Tata Fund Sheet Codes:**

| Fund | Sheet Code |
|------|------------|
| ELSS Fund | TTSF96 |
| Digital India Fund | Check consolidated file |
| Small Cap Fund | Check consolidated file |

### Quant Mutual Fund

**Example:**

```json
{
  "name": "Quant Small Cap Fund - Direct Growth",
  "source": "quant_mf",
  "params": {
    "scheme_name": "Quant Small Cap Fund"
  }
}
```

The system automatically finds the correct sheet in Quant's consolidated file.

### Bandhan Mutual Fund

**Note:** Requires Gmail portfolio disclosure emails for best results.

**Example:**

```json
{
  "name": "Bandhan ELSS Tax Saver Fund - Direct Growth",
  "source": "bandhan_mf",
  "params": {
    "scheme_name": "Bandhan ELSS Tax Saver Fund"
  }
}
```

### Multiple Funds from Same AMC

You can track multiple funds from the same AMC:

```json
{
  "mutual_funds": [
    {
      "name": "Parag Parikh Flexi Cap - Direct",
      "source": "ppfas_mf",
      "params": {
        "scheme_name": "Parag Parikh Flexi Cap Fund",
        "fund_code": "PPFCF"
      }
    },
    {
      "name": "Parag Parikh ELSS - Direct",
      "source": "ppfas_mf",
      "params": {
        "scheme_name": "Parag Parikh ELSS Tax Saver Fund",
        "fund_code": "PPTSF"
      }
    }
  ]
}
```

---

## Data Sources

### Gmail Portfolio Emails (Primary)

**How it works:**
1. AMCs send monthly portfolio disclosure emails to investors
2. System checks your Gmail inbox using IMAP
3. Extracts download links from email body
4. Downloads and parses Excel files

**Advantages:**
- ✅ Most reliable - you get emails automatically as an investor
- ✅ Fastest - no web scraping delays
- ✅ Works for all AMCs that send emails

**Setup:**
See [GMAIL-SETUP.md](GMAIL-SETUP.md) for detailed instructions.

**Current Status:**
- System checks Gmail first for ALL funds
- Falls back to web scraping if no emails found
- Will automatically use emails when they arrive (future-proof)

### Advisorkhoj (Fallback #1)

**What it is:**
Third-party aggregator that maintains AMC portfolio files.

**Supported AMCs:**
- Tata Mutual Fund
- Quant Mutual Fund
- Many others (check [Advisorkhoj](https://www.advisorkhoj.com))

**Advantages:**
- ✅ Direct download links (no JavaScript)
- ✅ Consolidated files with all schemes
- ✅ Regularly updated

**Limitations:**
- ❌ May lag behind AMC website by a few days
- ❌ Not all AMCs are covered (e.g., Bandhan missing)

### Direct AMC Website (Fallback #2)

**What it is:**
Scrapes portfolio files directly from AMC websites.

**Supported AMCs:**
- PPFAS (Parag Parikh) - Direct website scraping

**Advantages:**
- ✅ Most up-to-date data
- ✅ Official source

**Limitations:**
- ❌ Many AMCs use JavaScript/bot protection
- ❌ Website structure changes break scrapers

### Selenium Browser Automation (Fallback #3)

**What it is:**
Headless Chrome browser for JavaScript-heavy sites.

**When used:**
- Bandhan Mutual Fund (when Gmail and Advisorkhoj fail)
- Future AMCs with complex websites

**Advantages:**
- ✅ Can handle JavaScript rendering
- ✅ Bypasses some bot detection

**Limitations:**
- ❌ Slower than direct scraping
- ❌ Requires Chrome/ChromeDriver
- ❌ May still fail on heavily protected sites

---

## Configuration Parameters

### Thresholds

Control what changes get reported:

```json
{
  "thresholds": {
    "mf_percentage_change": 0.5,
    "min_holding_to_report": 0.5
  }
}
```

**Parameters:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `mf_percentage_change` | 0.5 | Minimum change to report (percentage points) |
| `min_holding_to_report` | 0.5 | Ignore holdings smaller than this % |

**Examples:**

- `mf_percentage_change: 0.5` → Only report if ICICI Bank goes from 5.0% → 5.5% or higher
- `min_holding_to_report: 0.5` → Ignore stocks with <0.5% allocation (reduces noise)

### Disabling a Fund

Add `"_enabled": false` to temporarily disable tracking:

```json
{
  "name": "Some Fund",
  "source": "ppfas_mf",
  "params": { ... },
  "_enabled": false
}
```

The fund will be skipped during fetching.

---

## Troubleshooting

### Common Issues

#### Issue 1: "No holdings found"

**Possible Causes:**
- AMC hasn't published current month's data yet
- Website structure changed
- Network/connectivity issue

**Solutions:**
1. Check AMC website manually to see if data is available
2. Wait a few days (AMCs have 7 days to publish)
3. Check logs for specific error messages

#### Issue 2: "Could not find sheet for [fund name]"

**Cause:** Sheet code mismatch in consolidated Excel files.

**Solution (Tata/Quant):**
1. Download the consolidated file manually from Advisorkhoj
2. Open it and find the exact sheet name
3. Update `sheet_code` parameter in config

#### Issue 3: Gmail not finding emails

**Cause:** You don't receive portfolio disclosure emails from that AMC.

**Why This Happens:**
- You invest through platforms (Groww/Zerodha) that don't forward AMC emails
- You haven't opted in for email disclosures
- Emails go to spam/promotions

**Solution:**
- System automatically falls back to web scraping
- Optionally: Contact AMC to enable email disclosures

#### Issue 4: "Website blocks automation"

**Cause:** AMC uses bot detection (e.g., HDFC MF).

**Solution:**
- Use Gmail-based approach (requires portfolio emails)
- Wait for AMC support to be added with alternative method
- Manual tracking as interim solution

### Debug Mode

Enable detailed logging:

```bash
export LOG_LEVEL=DEBUG
python monitor_indexes.py
```

This shows:
- Gmail search queries
- Download URLs
- Excel parsing details
- Fallback attempts

### Testing Individual Funds

Create a test script:

```python
from monitor_indexes import IndexMonitor

monitor = IndexMonitor()

params = {
    "scheme_name": "Your Fund Name",
    "fund_code": "CODE"  # if applicable
}

holdings = monitor.fetch_from_ppfas_mf(params)
print(f"Found {len(holdings)} holdings")
for stock, pct in sorted(holdings.items(), key=lambda x: x[1], reverse=True)[:10]:
    print(f"  {stock}: {pct}%")
```

---

## Email Notification Format

When changes are detected, you'll receive emails like:

```
Portfolio Changes Detected - 2026-01

============================================================
MUTUAL FUND HOLDINGS CHANGES
============================================================

Parag Parikh Flexi Cap Fund - Direct Growth
--------------------------------------------
Period: November 2025

NEW ADDITIONS (2):
  + RELIANCE INDUSTRIES (2.3%)
  + TCS (1.8%)

EXITS (1):
  - WIPRO

SIGNIFICANT INCREASES:
  ICICIBANK: 6.5% -> 7.2% (+0.7%)
  HDFC BANK: 7.8% -> 8.5% (+0.7%)

SIGNIFICANT DECREASES:
  BHARTI AIRTEL: 3.5% -> 2.8% (-0.7%)
```

---

## Advanced Topics

### Adding a New AMC

To add support for a new AMC:

1. **Create fetcher method** in `monitor_indexes.py`:

```python
def fetch_from_new_amc_mf(self, params: dict) -> Dict[str, float]:
    """
    Fetch holdings from New AMC.
    Tries Gmail first, then falls back to website.
    """
    scheme_name = params.get('scheme_name', '')

    try:
        # Step 1: Try Gmail
        if self.gmail_fetcher:
            download_url = self.gmail_fetcher.fetch_portfolio_from_email(
                amc_name="New AMC Name",
                fund_name=scheme_name,
                days_back=60
            )
            if download_url:
                # Download and parse
                # ...
                return holdings

        # Step 2: Fallback to website/Advisorkhoj
        # ...

    except Exception as e:
        logger.error(f"New AMC fetch error: {e}")
        return {}
```

2. **Register handler** in `__init__`:

```python
self.mf_source_handlers = {
    # ... existing handlers
    'new_amc_mf': self.fetch_from_new_amc_mf,
}
```

3. **Add to config**:

```json
{
  "name": "Fund Name",
  "source": "new_amc_mf",
  "params": {
    "scheme_name": "Full Scheme Name"
  }
}
```

4. **Test thoroughly** before production use

---

## FAQ

**Q: How often should I run the monitor?**
A: Weekly is recommended (current GitHub Actions schedule). AMCs publish monthly, so daily checks aren't necessary.

**Q: Can I track regular plans instead of direct plans?**
A: Yes, just use the regular plan's scheme name in the configuration.

**Q: Does this work for debt funds?**
A: Technically yes, but the system is optimized for equity funds. Debt fund portfolios may have different formats.

**Q: What happens if an AMC changes their website?**
A: The fetcher may fail. Report the issue on GitHub and it will be fixed. Gmail-based approach is more resilient to website changes.

**Q: Can I track international mutual funds?**
A: Currently only Indian mutual funds are supported. International holdings within Indian funds (like Parag Parikh) work fine.

---

## Getting Help

- **Issues:** [GitHub Issues](https://github.com/Dawny33/argus/issues)
- **Discussions:** [GitHub Discussions](https://github.com/Dawny33/argus/discussions)
- **Email:** See repository for contact info

---

## Contributing

Want to add support for a new AMC? Contributions welcome!

1. Fork the repository
2. Add fetcher for new AMC
3. Test with real data
4. Submit PR with documentation

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.
