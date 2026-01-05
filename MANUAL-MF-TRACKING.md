# Manual Mutual Fund Tracking Guide

## Current Status

Argus can automatically track **2 out of 5** of your equity mutual funds:

| Fund | AMC | Status | Notes |
|------|-----|--------|-------|
| Parag Parikh Flexi Cap Fund | PPFAS | ✅ Working | Auto-fetches monthly |
| Parag Parikh ELSS Tax Saver | PPFAS | ✅ Working | Auto-fetches monthly |
| Tata ELSS Fund | Tata | ❌ Blocked | Website blocks automation |
| Quant Small Cap Fund | Quant | ❌ JavaScript | Requires browser automation |
| Bandhan ELSS Tax Saver Fund | Bandhan | ❌ JavaScript | Requires browser automation |

## Why Some Funds Don't Work

### Technical Barriers

1. **Website Protection**: Tata MF website returns 403 Forbidden for automated requests
2. **JavaScript Rendering**: Quant and Bandhan websites load content dynamically via JavaScript
3. **Bot Detection**: AMCs use Cloudflare or similar services to block scraping

### AMC Website Comparison

| AMC | Website Type | Difficulty | Solution Needed |
|-----|--------------|------------|-----------------|
| PPFAS | Static HTML | Easy | ✅ Done! |
| Tata | Protected | Hard | Selenium + cookies |
| Quant | JavaScript | Medium | Selenium/Playwright |
| Bandhan | JavaScript | Medium | Selenium/Playwright |

## Options for Tracking Non-Working Funds

### Option 1: Manual Monthly Updates (Recommended for Now)

**How it works:**
1. Visit AMC website once a month
2. Download portfolio Excel file
3. Update a manual config with top holdings
4. System tracks changes from there

**Steps:**
1. On 7th of each month (after SEBI disclosure deadline):
   - Visit Tata MF, Quant MF, Bandhan MF websites
   - Download latest portfolio files
   - Extract top 10-15 holdings with percentages
   - Save to a local JSON file

2. Argus reads from this file and tracks changes going forward

**Pros:**
- Simple, works immediately
- No technical complexity
- Still get change notifications

**Cons:**
- Requires manual download once a month (5-10 minutes)
- Not fully automated

### Option 2: Implement Selenium/Browser Automation

**How it works:**
- Use Selenium or Playwright to control a real browser
- Navigate to AMC websites
- Wait for JavaScript to load
- Download files programmatically

**Pros:**
- Fully automated
- Works for all AMCs

**Cons:**
- Requires installing Chrome/Firefox driver
- Slower (launches browser each time)
- More complex to maintain
- May still be blocked by some sites

**Implementation effort:** ~4-6 hours per AMC

### Option 3: Track Only PPFAS Funds

**How it works:**
- Use only the 2 working Parag Parikh funds
- Skip tracking for Tata, Quant, Bandhan

**Pros:**
- Zero effort, works now
- Still covers 40% of your equity portfolio

**Cons:**
- Miss changes in 60% of equity holdings

### Option 4: Use Value Research / Morningstar API (If Available)

**How it works:**
- Third-party aggregators sometimes provide APIs
- Would work for all funds

**Pros:**
- Clean, reliable data
- Works for all funds

**Cons:**
- May require paid subscription
- API access might not be available

## Recommended Approach

**For immediate use:**

1. **Use automatic tracking for Parag Parikh funds** - Works perfectly right now
2. **Manual tracking for Tata/Quant/Bandhan** - Download portfolios monthly
3. **Consider Selenium later** - If manual tracking becomes tedious

## Manual Tracking Setup

### Step 1: Download Portfolio Files

Visit these URLs on the 7th of each month:

**Tata ELSS Fund:**
- URL: https://www.tatamutualfund.com/schemes-related/portfolio
- Find: "TATA ELSS FUND"
- Download: Latest monthly portfolio Excel

**Quant Small Cap Fund:**
- URL: https://quantmutual.com/statutory-disclosures
- Find: "Quant Small Cap Fund"
- Download: Latest portfolio disclosure

**Bandhan ELSS Tax Saver:**
- URL: https://bandhanmutual.com/downloads/disclosures
- Find: "Bandhan ELSS Tax Saver Fund"
- Download: Latest monthly portfolio

### Step 2: Extract Top Holdings

From each Excel file, extract:
- Stock names
- Percentage to NAV (% of total fund)
- Minimum 0.5% holdings

Example:
```
Tata ELSS (Nov 2025):
  HDFC BANK: 7.25%
  ICICI BANK: 6.15%
  BHARTI AIRTEL: 5.83%
  RELIANCE: 4.41%
  ... (continue for all stocks ≥0.5%)
```

### Step 3: Create Manual Holdings File

Create `data/manual_mf_holdings.json`:

```json
{
  "Tata ELSS Fund - Direct Growth": {
    "month": "2025-11",
    "date": "2025-11-30",
    "holdings": {
      "HDFC BANK": 7.25,
      "ICICI BANK": 6.15,
      "BHARTI AIRTEL": 5.83,
      "RELIANCE": 4.41
    }
  },
  "Quant Small Cap Fund - Direct Growth": {
    "month": "2025-11",
    "date": "2025-11-30",
    "holdings": {
      "STOCK1": 5.2,
      "STOCK2": 4.8
    }
  },
  "Bandhan ELSS Tax Saver Fund - Direct Growth": {
    "month": "2025-11",
    "date": "2025-11-30",
    "holdings": {
      "STOCK1": 6.1,
      "STOCK2": 5.5
    }
  }
}
```

### Step 4: Update Config

Modify `data/config.json` to use manual source:

```json
{
  "name": "Tata ELSS Fund - Direct Growth",
  "source": "manual_file",
  "params": {
    "file_path": "data/manual_mf_holdings.json",
    "fund_key": "Tata ELSS Fund - Direct Growth"
  }
}
```

## Time Investment

**Option 1 (Manual):** 10 minutes/month
**Option 2 (Selenium):** 6-8 hours one-time setup, then fully automated
**Option 3 (PPFAS only):** 0 minutes, works now

## What I Recommend

Since you want to track 10+ funds eventually:

1. **Short term (this month):**
   - Use Parag Parikh auto-tracking ✅
   - Manually check Tata/Quant/Bandhan once to set baseline

2. **Medium term (next 2-3 months):**
   - If you find manual tracking tedious, I can implement Selenium
   - Otherwise, continue with monthly manual updates

3. **Long term:**
   - As more AMCs are added, automate what's possible
   - Use manual for stubborn ones

## Need Help?

If you want me to:
1. Implement Selenium automation (4-6 hours work)
2. Create the manual holdings file for you
3. Add support for more AMCs

Just let me know! For now, the 2 Parag Parikh funds are fully working and will send you monthly email updates automatically.

---

**Next Steps:**
1. Test the current setup with Parag Parikh funds
2. Decide which option you prefer for the other 3 funds
3. I can implement whichever approach you choose
