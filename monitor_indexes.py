#!/usr/bin/env python3
"""
Index Constituent Monitor
Checks for changes in index constituents and sends email notifications.
"""

import json
import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Dict, List, Set
import requests
from bs4 import BeautifulSoup
import pandas as pd
import time


class IndexMonitor:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        self.config_file = self.data_dir / "config.json"
        self.state_file = self.data_dir / "previous_state.json"
        self.load_config()
        
    def load_config(self):
        """Load configuration from config.json"""
        if self.config_file.exists():
            with open(self.config_file, 'r') as f:
                self.config = json.load(f)
        else:
            # Default configuration
            self.config = {
                "indexes": [
                    "Nifty 50",
                    "Nifty Next 50",
                    "Nifty Midcap 150",
                    "Nifty Smallcap 250",
                    "Nasdaq 100",
                    "VXUS",
                    "QQQM"
                ],
                "email": {
                    "recipient": "jrajrohit33@gmail.com",
                    "smtp_server": "smtp.gmail.com",
                    "smtp_port": 587
                }
            }
            self.save_config()
    
    def save_config(self):
        """Save configuration to config.json"""
        with open(self.config_file, 'w') as f:
            json.dump(self.config, f, indent=2)
    
    def fetch_nifty_constituents(self, index_name: str) -> Set[str]:
        """Fetch constituents for Nifty indexes from NSE"""
        index_mapping = {
            "Nifty 50": "NIFTY 50",
            "Nifty Next 50": "NIFTY NEXT 50",
            "Nifty Midcap 150": "NIFTY MIDCAP 150",
            "Nifty Smallcap 250": "NIFTY SMALLCAP 250"
        }
        
        nse_name = index_mapping.get(index_name)
        if not nse_name:
            return set()
        
        try:
            # NSE requires headers to prevent blocking
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json',
                'Accept-Language': 'en-US,en;q=0.9',
            }
            
            # Try the equity stockIndices API
            url = f"https://www.nseindia.com/api/equity-stockIndices?index={nse_name.replace(' ', '%20')}"
            
            session = requests.Session()
            # First visit homepage to get cookies
            session.get("https://www.nseindia.com", headers=headers, timeout=10)
            time.sleep(1)
            
            response = session.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            constituents = {item['symbol'] for item in data.get('data', [])}
            
            return constituents
            
        except Exception as e:
            print(f"Error fetching {index_name}: {e}")
            # Fallback: try CSV download method
            try:
                csv_url = f"https://archives.nseindia.com/content/indices/ind_{nse_name.replace(' ', '').lower()}list.csv"
                df = pd.read_csv(csv_url)
                return set(df.iloc[:, 2].dropna().tolist())  # Symbol column
            except:
                return set()
    
    def fetch_nasdaq100_constituents(self) -> Set[str]:
        """Fetch Nasdaq 100 constituents"""
        try:
            url = "https://www.nasdaq.com/market-activity/quotes/nasdaq-ndx-index"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            # Parse the page - Nasdaq provides data in various formats
            # This might need adjustment based on current page structure
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Alternative: Use Wikipedia as a reliable source
            wiki_url = "https://en.wikipedia.org/wiki/Nasdaq-100"
            response = requests.get(wiki_url, headers=headers, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find the constituents table
            tables = soup.find_all('table', {'class': 'wikitable'})
            constituents = set()
            
            for table in tables:
                rows = table.find_all('tr')[1:]  # Skip header
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) >= 2:
                        ticker = cells[1].get_text().strip()
                        if ticker:
                            constituents.add(ticker)
            
            return constituents
            
        except Exception as e:
            print(f"Error fetching Nasdaq 100: {e}")
            return set()
    
    def fetch_vxus_constituents(self) -> Set[str]:
        """Fetch VXUS (Vanguard Total International Stock ETF) top holdings"""
        try:
            # VXUS tracks FTSE Global All Cap ex US Index
            # We'll track top holdings from Vanguard's site
            url = "https://investor.vanguard.com/investment-products/etfs/profile/vxus"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            # Note: VXUS has thousands of holdings, so we track top holdings
            # This is a placeholder - actual implementation may need API access
            print("VXUS: Tracking top holdings only (full list requires API access)")
            return set()
            
        except Exception as e:
            print(f"Error fetching VXUS: {e}")
            return set()
    
    def fetch_qqqm_constituents(self) -> Set[str]:
        """Fetch QQQM (Invesco NASDAQ 100 ETF) constituents"""
        try:
            # QQQM tracks the same index as QQQ (Nasdaq-100)
            # So we can use the same constituents as Nasdaq 100
            return self.fetch_nasdaq100_constituents()
            
        except Exception as e:
            print(f"Error fetching QQQM: {e}")
            return set()
    
    def fetch_all_constituents(self) -> Dict[str, Set[str]]:
        """Fetch constituents for all configured indexes"""
        current_state = {}
        
        for index in self.config['indexes']:
            print(f"Fetching constituents for {index}...")
            
            if 'Nifty' in index:
                constituents = self.fetch_nifty_constituents(index)
            elif index == 'Nasdaq 100':
                constituents = self.fetch_nasdaq100_constituents()
            elif index == 'VXUS':
                constituents = self.fetch_vxus_constituents()
            elif index == 'QQQM':
                constituents = self.fetch_qqqm_constituents()
            else:
                constituents = set()
            
            current_state[index] = list(constituents)
            print(f"  Found {len(constituents)} constituents")
            time.sleep(2)  # Rate limiting
        
        return current_state
    
    def load_previous_state(self) -> Dict[str, List[str]]:
        """Load previous state from file"""
        if self.state_file.exists():
            with open(self.state_file, 'r') as f:
                return json.load(f)
        return {}
    
    def save_current_state(self, state: Dict[str, List[str]]):
        """Save current state to file"""
        with open(self.state_file, 'w') as f:
            json.dump(state, f, indent=2)
    
    def detect_changes(self, previous: Dict[str, List[str]], 
                      current: Dict[str, List[str]]) -> Dict[str, Dict[str, List[str]]]:
        """Detect changes between previous and current state"""
        changes = {}
        
        for index in current.keys():
            prev_set = set(previous.get(index, []))
            curr_set = set(current[index])
            
            added = curr_set - prev_set
            removed = prev_set - curr_set
            
            if added or removed:
                changes[index] = {
                    'added': sorted(list(added)),
                    'removed': sorted(list(removed))
                }
        
        return changes
    
    def format_email_body(self, changes: Dict[str, Dict[str, List[str]]]) -> str:
        """Format the email body with changes"""
        if not changes:
            return "No changes detected in any index constituents."
        
        body = "Index Constituent Changes - " + datetime.now().strftime("%B %Y") + "\n\n"
        body += "=" * 60 + "\n\n"
        
        for index, change in changes.items():
            body += f"{index}\n"
            body += "-" * len(index) + "\n"
            
            if change['added']:
                body += f"✓ Added ({len(change['added'])}):\n"
                for stock in change['added']:
                    body += f"  • {stock}\n"
                body += "\n"
            
            if change['removed']:
                body += f"✗ Removed ({len(change['removed'])}):\n"
                for stock in change['removed']:
                    body += f"  • {stock}\n"
                body += "\n"
            
            body += "\n"
        
        return body
    
    def send_email(self, subject: str, body: str):
        """Send email notification"""
        sender = os.environ.get('EMAIL_SENDER')
        password = os.environ.get('EMAIL_PASSWORD')
        
        if not sender or not password:
            print("Email credentials not found in environment variables")
            print("Set EMAIL_SENDER and EMAIL_PASSWORD")
            return
        
        recipient = self.config['email']['recipient']
        
        msg = MIMEMultipart()
        msg['From'] = sender
        msg['To'] = recipient
        msg['Subject'] = subject
        
        msg.attach(MIMEText(body, 'plain'))
        
        try:
            server = smtplib.SMTP(
                self.config['email']['smtp_server'],
                self.config['email']['smtp_port']
            )
            server.starttls()
            server.login(sender, password)
            server.send_message(msg)
            server.quit()
            print(f"Email sent successfully to {recipient}")
        except Exception as e:
            print(f"Error sending email: {e}")
    
    def run(self):
        """Main execution method"""
        print("=" * 60)
        print("Index Constituent Monitor")
        print(f"Run date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        print()
        
        # Fetch current constituents
        print("Fetching current constituents...")
        current_state = self.fetch_all_constituents()
        
        # Load previous state
        print("\nLoading previous state...")
        previous_state = self.load_previous_state()
        
        # Detect changes
        print("\nDetecting changes...")
        changes = self.detect_changes(previous_state, current_state)
        
        # Save current state
        self.save_current_state(current_state)
        print("Current state saved")
        
        # Send email if there are changes
        if changes:
            print(f"\n{len(changes)} index(es) have changes")
            email_body = self.format_email_body(changes)
            print("\n" + email_body)
            
            subject = f"Index Changes Detected - {datetime.now().strftime('%B %Y')}"
            self.send_email(subject, email_body)
        else:
            print("\nNo changes detected")


if __name__ == "__main__":
    monitor = IndexMonitor()
    monitor.run()
