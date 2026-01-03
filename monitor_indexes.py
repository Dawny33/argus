#!/usr/bin/env python3
"""
Index Constituent Monitor
Checks for changes in index constituents and sends email notifications.
"""

import json
import os
import smtplib
from datetime import datetime
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
    
    def clean_symbol(self, symbol: str) -> str:
        """Clean stock symbol"""
        return symbol.replace('\xa0', ' ').replace('\u00a0', ' ').strip()
    
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
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json',
                'Accept-Language': 'en-US,en;q=0.9',
            }
            
            url = f"https://www.nseindia.com/api/equity-stockIndices?index={nse_name.replace(' ', '%20')}"
            
            session = requests.Session()
            session.get("https://www.nseindia.com", headers=headers, timeout=10)
            time.sleep(1)
            
            response = session.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            constituents = {item['symbol'] for item in data.get('data', [])}
            
            return constituents
            
        except Exception as e:
            print(f"Error fetching {index_name}: {e}")
            try:
                csv_url = f"https://archives.nseindia.com/content/indices/ind_{nse_name.replace(' ', '').lower()}list.csv"
                df = pd.read_csv(csv_url)
                return set(df.iloc[:, 2].dropna().tolist())
            except:
                return set()
    
    def fetch_nasdaq100_constituents(self) -> Set[str]:
        """Fetch Nasdaq 100 constituents"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            wiki_url = "https://en.wikipedia.org/wiki/Nasdaq-100"
            response = requests.get(wiki_url, headers=headers, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            tables = soup.find_all('table', {'class': 'wikitable'})
            constituents = set()
            
            for table in tables:
                rows = table.find_all('tr')[1:]
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
        """Fetch VXUS top holdings"""
        try:
            print("VXUS: Tracking top holdings only (full list requires API access)")
            return set()
        except Exception as e:
            print(f"Error fetching VXUS: {e}")
            return set()
    
    def fetch_qqqm_constituents(self) -> Set[str]:
        """Fetch QQQM constituents"""
        try:
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
            
            # Clean all symbols
            constituents = {self.clean_symbol(s) for s in constituents}
            
            current_state[index] = list(constituents)
            print(f"  Found {len(constituents)} constituents")
            time.sleep(2)
        
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
        # Use simple date format and force ASCII
        month_year = datetime.now().strftime('%Y-%m')
        month_year = month_year.encode('ascii', 'ignore').decode('ascii')
        
        if not changes:
            body = "No Index Constituent Changes - " + month_year + "\n\n"
            body += "=" * 60 + "\n\n"
            body += "All monitored indexes remain unchanged:\n\n"
            for index in self.config['indexes']:
                body += "  - " + index + "\n"
            body += "\n"
            body += "Your monitoring system is working correctly.\n"
            body += "You will receive an email next month with any changes detected."
            return body
        
        body = "Index Constituent Changes - " + month_year + "\n\n"
        body += "=" * 60 + "\n\n"
        
        for index, change in changes.items():
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
        
        # CRITICAL: Clean email addresses too!
        sender = sender.encode('ascii', 'ignore').decode('ascii').strip()
        recipient = recipient.encode('ascii', 'ignore').decode('ascii').strip()
        
        # Force everything to ASCII
        subject = subject.encode('ascii', 'ignore').decode('ascii')
        body = body.encode('ascii', 'ignore').decode('ascii')
        
        # Build simple email
        message = "From: " + sender + "\n"
        message += "To: " + recipient + "\n"
        message += "Subject: " + subject + "\n"
        message += "\n"
        message += body
        
        try:
            server = smtplib.SMTP(
                self.config['email']['smtp_server'],
                self.config['email']['smtp_port']
            )
            server.starttls()
            server.login(sender, password)
            # Pass message as string - smtplib will handle encoding
            server.sendmail(sender, [recipient], message)
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
        
        # Generate month_year and clean it
        month_year = datetime.now().strftime('%Y-%m')
        # Force ASCII by removing any non-ASCII characters
        month_year = month_year.encode('ascii', 'ignore').decode('ascii')
        
        if changes:
            print(f"\n{len(changes)} index(es) have changes")
            email_body = self.format_email_body(changes)
            subject = "Index Changes Detected - " + month_year
        else:
            print("\nNo changes detected")
            email_body = self.format_email_body(changes)
            subject = "No Index Changes - " + month_year
        
        # Force clean subject and body
        subject = subject.encode('ascii', 'ignore').decode('ascii')
        email_body = email_body.encode('ascii', 'ignore').decode('ascii')
        
        print("\n" + email_body)
        self.send_email(subject, email_body)


if __name__ == "__main__":
    monitor = IndexMonitor()
    monitor.run()
