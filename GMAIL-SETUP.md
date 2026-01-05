# Gmail Portfolio Fetcher Setup

The Gmail portfolio fetcher accesses your Gmail inbox to find monthly portfolio disclosure emails sent by AMCs (Asset Management Companies). This is the most reliable method since you receive these emails automatically as an investor.

## Setup Steps

### 1. Generate Gmail App Password

Since you're already using Gmail for sending notifications, you likely already have an app password set up. If not:

1. Go to your Google Account: https://myaccount.google.com/
2. Select "Security" from the left menu
3. Under "How you sign in to Google," select "2-Step Verification"
4. At the bottom, select "App passwords"
5. Select "Mail" and "Mac" (or your device)
6. Click "Generate"
7. Copy the 16-character password (remove spaces)

### 2. Set Environment Variables

Add these to your `~/.bashrc`, `~/.zshrc`, or export them before running:

```bash
export EMAIL_SENDER="jrajrohit33@gmail.com"
export EMAIL_PASSWORD="your-16-char-app-password"
export EMAIL_RECIPIENT="jrajrohit33@gmail.com"  # Same as sender for testing
```

### 3. Test Gmail Access

Run the test script to verify it can access your portfolio emails:

```bash
cd /Users/jalemrajrohit/Documents/VibeCoding/argus
source ../venv/bin/activate
python /tmp/test_gmail_fetcher.py
```

## How It Works

### Portfolio Disclosure Emails

AMCs send monthly portfolio disclosure emails that look like:

**From:** Bandhan Mutual Fund (noreply@bandhanmutual.com)
**Subject:** Monthly Portfolio Disclosure - November 2025
**Body:** Contains link to download Excel file with holdings

### Search Process

The Gmail fetcher:

1. **Connects** to your Gmail via IMAP using your app password
2. **Searches** for emails from specific AMCs with "portfolio" in subject
3. **Extracts** download links from the email body (HTML parsing)
4. **Downloads** the Excel file and parses holdings
5. **Falls back** to Advisorkhoj or Selenium if Gmail fails

### Benefits Over Web Scraping

- ✅ **More reliable**: You get these emails automatically
- ✅ **Always current**: Latest disclosure right in your inbox
- ✅ **Works for all AMCs**: Even those with complex websites
- ✅ **No website changes**: Email format is more stable
- ✅ **Solves Bandhan issue**: Direct access to portfolio files

## Privacy & Security

- Your Gmail app password is stored **only** in environment variables
- The script **reads emails only** (IMAP read-only access)
- No emails are modified or deleted
- Only searches for portfolio disclosure emails from AMCs
- Download links are extracted but emails remain in your inbox

## Testing

After setting up credentials, test with:

```bash
# Test Gmail fetcher alone
python /tmp/test_gmail_fetcher.py

# Test full Bandhan fetch (with Gmail as primary source)
python /tmp/test_bandhan_gmail.py
```

## Troubleshooting

### "Gmail connection failed"
- Verify app password is correct (16 characters, no spaces)
- Ensure 2-Step Verification is enabled on your Google account
- Try regenerating the app password

### "No portfolio emails found"
- Check if you actually receive portfolio disclosure emails
- Try increasing `days_back` parameter (default: 60 days)
- Search your Gmail manually for emails from AMC names

### "No download links found"
- AMC may use different email format
- Check email body manually for how links are formatted
- May need to adjust link extraction logic

## Fallback Behavior

The system uses a **cascading fallback** approach:

1. **Gmail** (primary) - Checks investor's portfolio disclosure emails
2. **Advisorkhoj** (fallback) - Third-party aggregator portal
3. **Selenium** (last resort) - Direct AMC website scraping

Each fund tries the next method if the previous one fails.
