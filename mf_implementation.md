# Indian Mutual Fund Monitoring - Implementation Plan

## Project Overview

Extend the existing Argus index monitoring system to track Indian mutual fund portfolio holdings and detect significant changes.

**Goal:** Monitor mutual fund holdings on a monthly basis and send email notifications when:
- New stocks are added to portfolio
- Existing stocks are completely removed
- Stock allocation changes by ≥0.5% (absolute)

---

## Requirements Summary

### User Requirements
1. **Data Source:** Best free option (AMFI preferred)
2. **Fund Selection:** User-configurable via config.json
3. **Frequency:** Monthly (same as existing ETF monitoring)
4. **Change Threshold:** Report only changes ≥0.5% (absolute)
5. **Email Format:** Detailed report (Option A format)
6. **Integration:** Extend existing Argus codebase

### Technical Requirements
1. Reuse existing infrastructure (IndexMonitor class, email system, state management)
2. Modular source handler pattern (like existing NSE/Nasdaq handlers)
3. Unified email notification (indexes + mutual funds in one email)
4. JSON-based configuration
5. State persistence in previous_state.json
6. GitHub Actions compatible

---

## Architecture Design

### System Components

```
Argus (Extended)
│
├── Data Layer
│   ├── Index Sources (Existing)
│   │   ├── NSE API
│   │   ├── Nasdaq Official
│   │   ├── Invesco ETF
│   │   └── Vanguard ETF
│   │
│   └── Mutual Fund Sources (NEW)
│       ├── AMFI (Primary)
│       ├── Fund House Websites (Fallback)
│       └── Value Research (Last Resort)
│
├── Storage Layer
│   └── previous_state.json
│       ├── indexes: {name: [stocks]}  (Existing)
│       └── mutual_funds: {name: {holdings: {stock: %}}}  (NEW)
│
├── Processing Layer
│   ├── Index Change Detector (Existing)
│   │   └── Binary: added/removed
│   │
│   └── MF Change Detector (NEW)
│       ├── Additions: 0% → X%
│       ├── Exits: X% → 0%
│       ├── Increases: X% → Y% where (Y-X) ≥ 0.5%
│       └── Decreases: X% → Y% where (X-Y) ≥ 0.5%
│
└── Notification Layer
    └── Unified Email (Extended)
        ├── Section 1: Index Changes
        └── Section 2: MF Holdings Changes (NEW)
```

### Data Models

#### Config Schema Extension

**File:** `data/config.json`

```json
{
  "indexes": [
    // Existing index configurations
  ],
  "mutual_funds": [
    {
      "name": "HDFC Flexi Cap Fund - Direct",
      "isin": "INF179K01997",
      "source": "amfi",
      "params": {
        "amc_code": "HDFC",
        "scheme_code": "119551",
        "scheme_name": "HDFC Flexi Cap Fund - Direct Plan - Growth"
      }
    },
    {
      "name": "Parag Parikh Flexi Cap Fund - Direct",
      "isin": "INF195K01SE2",
      "source": "amfi",
      "params": {
        "amc_code": "PPFAS",
        "scheme_code": "122639",
        "scheme_name": "Parag Parikh Flexi Cap Fund - Direct - Growth"
      }
    }
  ],
  "thresholds": {
    "mf_percentage_change": 0.5,
    "min_holding_to_report": 0.5
  },
  "email": {
    "recipient": "jrajrohit33@gmail.com",
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587
  }
}
```

#### State Schema Extension

**File:** `data/previous_state.json`

```json
{
  "indexes": {
    "Nifty 50": ["RELIANCE", "TCS", "INFY"],
    "Nasdaq 100": ["AAPL", "MSFT", "GOOGL"]
  },
  "mutual_funds": {
    "HDFC Flexi Cap Fund - Direct": {
      "month": "2025-12",
      "disclosure_date": "2026-01-07",
      "holdings": {
        "RELIANCE": 6.5,
        "TCS": 5.2,
        "HDFCBANK": 4.8,
        "ICICIBANK": 3.7,
        "INFY": 3.2
      }
    },
    "Parag Parikh Flexi Cap Fund - Direct": {
      "month": "2025-12",
      "disclosure_date": "2026-01-05",
      "holdings": {
        "ALPHABET-C": 8.2,
        "META": 6.5,
        "MICROSOFT": 6.1,
        "RELIANCE": 5.8,
        "AMAZON": 4.9
      }
    }
  }
}
```

---

## Implementation Phases

### Phase 1: Data Source Research (Week 1)

**Objective:** Identify and validate best free data source for Indian MF holdings

#### Tasks

1. **Research AMFI Data Access**
   - [ ] Explore AMFI website (https://www.amfiindia.com)
   - [ ] Identify portfolio disclosure URLs/formats
   - [ ] Test manual download for 3 sample funds
   - [ ] Document data format (PDF/Excel/HTML/API)
   - [ ] Identify update schedule and reliability

2. **Evaluate Alternative Sources**
   - [ ] Check individual AMC websites (HDFC, ICICI, PPFAS)
   - [ ] Test Value Research free tier
   - [ ] Test Moneycontrol scraping feasibility
   - [ ] Compare data quality and reliability

3. **Design Data Parser**
   - [ ] Create parsing strategy for chosen source
   - [ ] Handle multiple formats if needed
   - [ ] Extract: stock name, percentage, date
   - [ ] Map stock names to standard symbols

#### Deliverables

- **Document:** `AMFI-DATA-SOURCE.md`
  - Data source URLs and access methods
  - Data format documentation
  - Parsing strategy
  - Sample data for 3 funds
  
- **Prototype:** `test_amfi_parser.py`
  - Basic parser for testing
  - Sample output for validation

**Decision Point:** Validate with user before proceeding to Phase 2

---

### Phase 2: Core Implementation (Week 2)

**Objective:** Implement MF data fetching and change detection

#### Task 2.1: Implement AMFI Source Handler

**File:** `monitor_indexes.py`

**Add to IndexMonitor class:**

```python
def fetch_from_amfi(self, params: dict) -> Dict[str, float]:
    """
    Fetch mutual fund holdings from AMFI
    
    Args:
        params: Dict containing:
            - amc_code: AMC identifier (e.g., 'HDFC')
            - scheme_code: Scheme identifier
            - scheme_name: Full scheme name
    
    Returns:
        Dict mapping stock symbol to percentage
        Example: {'RELIANCE': 6.5, 'TCS': 5.2, 'HDFCBANK': 4.8}
    
    Raises:
        AMFIFetchError: If data cannot be fetched
        AMFIParseError: If data cannot be parsed
    """
    
    amc_code = params.get('amc_code')
    scheme_code = params.get('scheme_code')
    scheme_name = params.get('scheme_name')
    
    # Implementation based on Phase 1 findings
    # This is a placeholder - actual implementation depends on data source
    
    try:
        # Step 1: Fetch data
        url = self._get_amfi_url(amc_code, scheme_code)
        data = self._fetch_amfi_data(url)
        
        # Step 2: Parse holdings
        holdings = self._parse_amfi_holdings(data)
        
        # Step 3: Clean and normalize
        holdings = self._normalize_holdings(holdings)
        
        return holdings
        
    except Exception as e:
        print(f"AMFI fetch error for {scheme_name}: {e}")
        return {}

def _get_amfi_url(self, amc_code: str, scheme_code: str) -> str:
    """Construct URL for AMFI data access"""
    # Implementation based on Phase 1 research
    pass

def _fetch_amfi_data(self, url: str) -> Any:
    """Fetch raw data from AMFI"""
    # Implementation based on Phase 1 research
    pass

def _parse_amfi_holdings(self, data: Any) -> Dict[str, float]:
    """Parse holdings from AMFI data format"""
    # Implementation based on Phase 1 research
    pass

def _normalize_holdings(self, holdings: Dict[str, float]) -> Dict[str, float]:
    """
    Normalize stock names and clean percentages
    
    - Standardize stock symbols
    - Handle international stocks (ADRs, foreign listings)
    - Remove holdings below minimum threshold
    - Round percentages to 1 decimal place
    """
    normalized = {}
    min_pct = self.config.get('thresholds', {}).get('min_holding_to_report', 0.5)
    
    for stock, pct in holdings.items():
        # Clean stock symbol
        stock_clean = stock.strip().upper()
        stock_clean = stock_clean.replace('\xa0', ' ')
        
        # Round percentage
        pct_rounded = round(pct, 1)
        
        # Filter by minimum
        if pct_rounded >= min_pct:
            normalized[stock_clean] = pct_rounded
    
    return normalized
```

#### Task 2.2: Implement MF Change Detector

**File:** `monitor_indexes.py`

**Add new class:**

```python
class MFChangeDetector:
    """
    Detect changes in mutual fund holdings
    
    Tracks:
    - New additions (stocks not in previous holdings)
    - Complete exits (stocks removed from portfolio)
    - Significant increases (≥0.5% increase)
    - Significant decreases (≥0.5% decrease)
    """
    
    def __init__(self, threshold: float = 0.5):
        """
        Args:
            threshold: Minimum percentage point change to report (default: 0.5)
        """
        self.threshold = threshold
    
    def detect_changes(self, previous: Dict[str, float], 
                       current: Dict[str, float]) -> Dict[str, List]:
        """
        Compare previous and current holdings
        
        Args:
            previous: Previous month's holdings {stock: %}
            current: Current month's holdings {stock: %}
        
        Returns:
            Dict with keys:
            - 'additions': [(stock, pct), ...]
            - 'exits': [(stock, old_pct), ...]
            - 'increases': [(stock, old_pct, new_pct, change), ...]
            - 'decreases': [(stock, old_pct, new_pct, change), ...]
        """
        
        changes = {
            'additions': [],
            'exits': [],
            'increases': [],
            'decreases': []
        }
        
        prev_stocks = set(previous.keys())
        curr_stocks = set(current.keys())
        
        # New additions (not in previous)
        for stock in curr_stocks - prev_stocks:
            changes['additions'].append((stock, current[stock]))
        
        # Complete exits (not in current)
        for stock in prev_stocks - curr_stocks:
            changes['exits'].append((stock, previous[stock]))
        
        # Rebalances (present in both)
        for stock in prev_stocks & curr_stocks:
            old_pct = previous[stock]
            new_pct = current[stock]
            change = new_pct - old_pct
            
            # Only report if change meets threshold
            if abs(change) >= self.threshold:
                entry = (stock, old_pct, new_pct, change)
                
                if change > 0:
                    changes['increases'].append(entry)
                else:
                    changes['decreases'].append(entry)
        
        return changes
    
    def has_changes(self, changes: Dict[str, List]) -> bool:
        """Check if any changes were detected"""
        return any(len(v) > 0 for v in changes.values())
```

#### Task 2.3: Update IndexMonitor Class

**File:** `monitor_indexes.py`

**Modify existing methods:**

```python
class IndexMonitor:
    def __init__(self, data_dir: str = "data"):
        # Existing initialization
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        self.config_file = self.data_dir / "config.json"
        self.state_file = self.data_dir / "previous_state.json"
        self.load_config()
        
        # Existing source handlers
        self.source_handlers = {
            'nse_api': self.fetch_from_nse,
            'nasdaq_official': self.fetch_from_nasdaq,
            'vanguard_etf': self.fetch_from_vanguard,
            'invesco_etf': self.fetch_from_invesco,
            'amfi': self.fetch_from_amfi,  # NEW
        }
        
        # NEW: MF change detector
        mf_threshold = self.config.get('thresholds', {}).get('mf_percentage_change', 0.5)
        self.mf_detector = MFChangeDetector(threshold=mf_threshold)
    
    def fetch_all_constituents(self) -> Dict:
        """
        Fetch constituents for both indexes and mutual funds
        
        Returns:
            Dict with keys 'indexes' and 'mutual_funds'
        """
        current_state = {
            'indexes': {},
            'mutual_funds': {}
        }
        
        # Fetch indexes (existing logic)
        for index_config in self.config.get('indexes', []):
            constituents = self.fetch_constituents(index_config)
            current_state['indexes'][index_config['name']] = sorted(list(constituents))
            time.sleep(2)  # Rate limiting
        
        # Fetch mutual funds (NEW)
        for fund_config in self.config.get('mutual_funds', []):
            holdings = self.fetch_fund_holdings(fund_config)
            current_state['mutual_funds'][fund_config['name']] = {
                'month': datetime.now().strftime('%Y-%m'),
                'disclosure_date': datetime.now().strftime('%Y-%m-%d'),
                'holdings': holdings
            }
            time.sleep(2)  # Rate limiting
        
        return current_state
    
    def fetch_fund_holdings(self, fund_config: dict) -> Dict[str, float]:
        """
        Fetch holdings for a single mutual fund
        
        Args:
            fund_config: Fund configuration from config.json
        
        Returns:
            Dict mapping stock to percentage
        """
        fund_name = fund_config['name']
        source = fund_config['source']
        params = fund_config.get('params', {})
        
        print(f"Fetching holdings for {fund_name}...")
        
        # Get appropriate handler
        handler = self.source_handlers.get(source)
        
        if not handler:
            print(f"  Unknown source type: {source}")
            return {}
        
        # Fetch holdings
        holdings = handler(params)
        
        print(f"  Found {len(holdings)} holdings")
        return holdings
```

#### Deliverables

- **Updated:** `monitor_indexes.py`
  - AMFI source handler implemented
  - MFChangeDetector class added
  - fetch_all_constituents() extended
  - fetch_fund_holdings() added

- **Tests:** `test_mf_detection.py`
  - Unit tests for change detection
  - Edge cases validated

---

### Phase 3: Email Notification (Week 3)

**Objective:** Extend email formatting to include MF changes

#### Task 3.1: MF Email Formatter

**File:** `monitor_indexes.py`

**Add new method:**

```python
def format_mf_changes(self, fund_name: str, changes: Dict, 
                       month: str) -> str:
    """
    Format mutual fund changes for email
    
    Args:
        fund_name: Name of the mutual fund
        changes: Changes dict from MFChangeDetector
        month: Month in format 'YYYY-MM'
    
    Returns:
        Formatted text for email body
    
    Example output:
        HDFC Flexi Cap Fund - Direct - December 2025
        
        NEW ADDITIONS (2):
          + RELIANCE (2.3%)
          + TCS (1.8%)
        
        COMPLETE EXITS (1):
          - WIPRO (was 1.2%)
        
        SIGNIFICANT INCREASES:
          ICICIBANK: 6.5% → 7.2% (+0.7%)
        
        SIGNIFICANT DECREASES:
          BHARTIARTL: 3.5% → 2.8% (-0.7%)
    """
    
    if not self.mf_detector.has_changes(changes):
        return f"{fund_name} - No changes"
    
    # Convert month format: 2025-12 → December 2025
    try:
        date_obj = datetime.strptime(month, '%Y-%m')
        month_name = date_obj.strftime('%B %Y')
    except:
        month_name = month
    
    lines = [
        f"{fund_name} - {month_name}",
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
```

#### Task 3.2: Unified Email Body

**File:** `monitor_indexes.py`

**Modify format_email_body method:**

```python
def format_email_body(self, index_changes: Dict, mf_changes: Dict) -> str:
    """
    Format unified email body with both index and MF changes
    
    Args:
        index_changes: Index changes (existing format)
        mf_changes: MF changes {fund_name: changes_dict}
    
    Returns:
        Complete email body text
    """
    
    month_year = datetime.now().strftime('%Y-%m')
    month_year = month_year.encode('ascii', 'ignore').decode('ascii')
    
    # Check if any changes at all
    has_index_changes = bool(index_changes)
    has_mf_changes = any(self.mf_detector.has_changes(c) 
                         for c in mf_changes.values())
    
    if not has_index_changes and not has_mf_changes:
        body = "No Portfolio Changes - " + month_year + "\n\n"
        body += "=" * 60 + "\n\n"
        body += "All monitored indexes and mutual funds remain unchanged.\n"
        return body
    
    body = "Portfolio Changes Detected - " + month_year + "\n\n"
    
    # Index changes section
    if has_index_changes:
        body += "=" * 60 + "\n"
        body += "INDEX CONSTITUENT CHANGES\n"
        body += "=" * 60 + "\n\n"
        
        for index, change in index_changes.items():
            body += index + "\n"
            body += "-" * len(index) + "\n"
            
            if change['added']:
                body += "Added (" + str(len(change['added'])) + "):\n"
                for stock in change['added']:
                    body += "  + " + stock + "\n"
                body += "\n"
            
            if change['removed']:
                body += "Removed (" + str(len(change['removed'])) + "):\n"
                for stock in change['removed']:
                    body += "  - " + stock + "\n"
                body += "\n"
            
            body += "\n"
    
    # Mutual fund changes section
    if has_mf_changes:
        body += "=" * 60 + "\n"
        body += "MUTUAL FUND HOLDINGS CHANGES\n"
        body += "=" * 60 + "\n\n"
        
        for fund_name, changes in mf_changes.items():
            if self.mf_detector.has_changes(changes):
                month = mf_changes.get(fund_name + '_month', month_year)
                fund_section = self.format_mf_changes(fund_name, changes, month)
                body += fund_section + "\n\n"
    
    body += "=" * 60 + "\n"
    
    return body
```

#### Task 3.3: Update Main Run Method

**File:** `monitor_indexes.py`

**Modify run() method:**

```python
def run(self):
    """Main execution method"""
    print("=" * 60)
    print("Portfolio Monitor (Indexes + Mutual Funds)")
    print(f"Run date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print()
    
    # Fetch current state
    print("Fetching current data...")
    current_state = self.fetch_all_constituents()
    
    # Load previous state
    print("\nLoading previous state...")
    previous_state = self.load_previous_state()
    
    # Detect index changes (existing)
    print("\nDetecting index changes...")
    index_changes = self.detect_changes(
        previous_state.get('indexes', {}),
        current_state.get('indexes', {})
    )
    
    # Detect MF changes (NEW)
    print("Detecting mutual fund changes...")
    mf_changes = {}
    for fund_name, fund_data in current_state.get('mutual_funds', {}).items():
        prev_fund = previous_state.get('mutual_funds', {}).get(fund_name, {})
        prev_holdings = prev_fund.get('holdings', {})
        curr_holdings = fund_data.get('holdings', {})
        
        changes = self.mf_detector.detect_changes(prev_holdings, curr_holdings)
        mf_changes[fund_name] = changes
        mf_changes[fund_name + '_month'] = fund_data.get('month')
    
    # Save current state
    self.save_current_state(current_state)
    print("Current state saved")
    
    # Generate email
    month_year = datetime.now().strftime('%Y-%m')
    month_year = month_year.encode('ascii', 'ignore').decode('ascii')
    
    has_index_changes = bool(index_changes)
    has_mf_changes = any(self.mf_detector.has_changes(c) 
                         for c in mf_changes.values())
    
    if has_index_changes or has_mf_changes:
        print(f"\nChanges detected!")
        email_body = self.format_email_body(index_changes, mf_changes)
        subject = "Portfolio Changes Detected - " + month_year
    else:
        print("\nNo changes detected")
        email_body = self.format_email_body({}, {})
        subject = "No Portfolio Changes - " + month_year
    
    # Send email
    print("\n" + email_body)
    self.send_email(subject, email_body)
```

#### Deliverables

- **Updated:** `monitor_indexes.py`
  - format_mf_changes() added
  - format_email_body() extended
  - run() method updated

- **Sample output:** Email preview with test data

---

### Phase 4: Testing & Documentation (Week 4)

**Objective:** Test end-to-end and update documentation

#### Task 4.1: End-to-End Testing

**Test scenarios:**

1. **New fund (no previous state)**
   - Expected: Report all holdings as "current portfolio"
   - No changes detected (first run)

2. **No changes**
   - Expected: "No changes" message
   - Email sent confirming monitoring is active

3. **Only additions**
   - Add 3 new stocks
   - Expected: Report 3 additions

4. **Only exits**
   - Remove 2 stocks
   - Expected: Report 2 exits

5. **Mixed changes**
   - Add 2 stocks
   - Remove 1 stock
   - Increase 2 stocks by >0.5%
   - Decrease 1 stock by >0.5%
   - Change 1 stock by <0.5% (should be ignored)
   - Expected: All significant changes reported

6. **Edge cases**
   - Stock with 0.5% exactly (should be reported)
   - Stock with 0.49% change (should be ignored)
   - International holdings (ADRs)
   - Sectoral funds vs equity funds

**Test execution:**
```bash
# Test with sample config
python monitor_indexes.py

# Verify email output
# Check previous_state.json structure
# Validate change detection accuracy
```

#### Task 4.2: Documentation

**Update README.md:**

Add section:

```markdown
## Mutual Fund Monitoring

Argus now supports tracking Indian mutual fund portfolio holdings.

### Supported Features

- Monthly portfolio monitoring
- Change detection (additions, exits, rebalances)
- Configurable threshold (default: 0.5% change)
- Unified notifications (indexes + mutual funds)

### Configuration

Add mutual funds to `data/config.json`:

```json
{
  "mutual_funds": [
    {
      "name": "HDFC Flexi Cap Fund - Direct",
      "isin": "INF179K01997",
      "source": "amfi",
      "params": {
        "amc_code": "HDFC",
        "scheme_code": "119551"
      }
    }
  ],
  "thresholds": {
    "mf_percentage_change": 0.5
  }
}
```

### Finding Scheme Codes

[Instructions on how to find ISIN and scheme codes]

### Data Sources

- Primary: AMFI (Association of Mutual Funds in India)
- Update frequency: Monthly (within 7 days of month-end)
- Coverage: Top 10-20 holdings typically disclosed

### Example Output

```
HDFC Flexi Cap Fund - Direct - December 2025

NEW ADDITIONS (2):
  + RELIANCE (2.3%)
  + TCS (1.8%)

COMPLETE EXITS (1):
  - WIPRO (was 1.2%)

SIGNIFICANT INCREASES:
  ICICIBANK: 6.5% → 7.2% (+0.7%)
```
```

**Create MF-GUIDE.md:**

Comprehensive guide covering:
- How to find fund ISINs and scheme codes
- Understanding portfolio disclosures
- Interpreting percentage changes
- Troubleshooting common issues

#### Deliverables

- **Updated:** README.md
- **New:** MF-GUIDE.md
- **Test report:** Test results summary
- **Example configs:** Sample configurations

---

## Technical Specifications

### Error Handling

```python
class AMFIFetchError(Exception):
    """Raised when AMFI data cannot be fetched"""
    pass

class AMFIParseError(Exception):
    """Raised when AMFI data cannot be parsed"""
    pass

# In fetch_from_amfi():
try:
    data = fetch_amfi_data(url)
except requests.RequestException as e:
    print(f"Network error fetching {fund_name}: {e}")
    return {}
except AMFIParseError as e:
    print(f"Parse error for {fund_name}: {e}")
    return {}
```

### Logging

Add detailed logging:

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('argus')

# In methods:
logger.info(f"Fetching holdings for {fund_name}")
logger.debug(f"Holdings: {holdings}")
logger.warning(f"No data found for {fund_name}")
logger.error(f"Failed to parse: {e}")
```

### Rate Limiting

```python
import time

# Between fund fetches
time.sleep(2)  # 2 seconds delay

# For bulk operations
for fund in funds:
    fetch_fund(fund)
    time.sleep(2)
```

---

## Integration Checklist

- [ ] Phase 1: Data source validated
- [ ] Phase 2: Core implementation complete
- [ ] Phase 3: Email notification working
- [ ] Phase 4: Testing complete
- [ ] Documentation updated
- [ ] GitHub Actions workflow verified
- [ ] Example configs provided
- [ ] Ready for production use

---

## Success Criteria

**Functionality:**
- [ ] Correctly fetches MF holdings from AMFI
- [ ] Accurately detects changes ≥0.5%
- [ ] Sends unified email (indexes + MFs)
- [ ] Persists state correctly
- [ ] Handles errors gracefully

**Quality:**
- [ ] Code follows existing patterns
- [ ] Proper error handling
- [ ] Comprehensive logging
- [ ] Well documented

**Performance:**
- [ ] Processes 10 funds in <3 minutes
- [ ] Respects rate limits
- [ ] Efficient state storage

---

## Future Enhancements

**Potential improvements for v2.0:**
1. Historical change tracking
2. Visual charts/graphs
3. Sector allocation tracking
4. Fund performance metrics
5. Multi-AMC batch processing
6. Web dashboard for viewing changes
7. Slack/Telegram notifications
8. Custom alert rules per fund

---

## Questions & Clarifications

**Before starting implementation, confirm:**

1. Is AMFI the preferred data source? (Y/N)
2. Should we handle international holdings in MFs? (Y/N)
3. Minimum number of funds to support? (3-5 for testing?)
4. Should sectoral funds be treated differently? (Y/N)
5. Need historical tracking beyond previous month? (Y/N)

**Contact:** Provide answers before proceeding to implementation

---

## File Structure

```
argus/
├── monitor_indexes.py          # Main file (to be extended)
├── requirements.txt            # Dependencies (to be updated)
├── data/
│   ├── config.json            # Extended with MF configs
│   └── previous_state.json    # Extended with MF state
├── .github/
│   └── workflows/
│       └── monitor.yml        # GitHub Actions (no changes needed)
├── README.md                  # Updated with MF docs
├── MF-GUIDE.md               # New: MF-specific guide
└── tests/
    └── test_mf_detection.py  # New: MF tests
```

---

## Dependencies

**New packages needed:**

```
# Add to requirements.txt
pandas>=2.0.0      # For Excel/CSV parsing (if AMFI uses these)
openpyxl>=3.1.0    # For Excel files
PyPDF2>=3.0.0      # For PDF parsing (if AMFI uses PDFs)
```

**Verify existing packages sufficient:**
- requests
- beautifulsoup4
- lxml

---

## Execution Timeline

| Phase | Duration | Deliverable |
|-------|----------|-------------|
| Phase 1 | Week 1 | Data source validated |
| Phase 2 | Week 2 | Core implementation |
| Phase 3 | Week 3 | Email integration |
| Phase 4 | Week 4 | Testing & docs |

**Total:** 4 weeks from start to production

---

## Notes for Claude Code

**Implementation priority:**
1. Start with Phase 1 (data source research)
2. Create prototype parser
3. Validate with user before Phase 2
4. Follow existing code patterns from monitor_indexes.py
5. Reuse IndexMonitor class structure
6. Maintain backward compatibility
7. Test incrementally

**Code style:**
- Follow PEP 8
- Use type hints
- Add docstrings to all methods
- Match existing error handling patterns
- Reuse existing helper methods where possible

**Testing approach:**
- Unit tests for change detection
- Integration tests with sample data
- Manual verification with 3-5 real funds
- Email format validation

---

**Ready to begin implementation!** 🚀

Start with Phase 1: Research AMFI data sources and create prototype parser.
