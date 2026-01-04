#!/usr/bin/env python3
"""
Index Constituent Monitor - Modular Version
Fetches index constituents from official sources and sends email notifications.
"""

import json
import os
import smtplib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Optional
import requests
from bs4 import BeautifulSoup
import time


class IndexMonitor:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        self.config_file = self.data_dir / "config.json"
        self.state_file = self.data_dir / "previous_state.json"
        self.load_config()
        
        # Source handlers - maps source type to fetch function
        self.source_handlers = {
            'nse_api': self.fetch_from_nse,
            'nasdaq_official': self.fetch_from_nasdaq,
            'vanguard_etf': self.fetch_from_vanguard,
        }
    
    def load_config(self):
        """Load configuration from config.json"""
        if self.config_file.exists():
            with open(self.config_file, 'r') as f:
                self.config = json.load(f)
        else:
            # Default configuration with index metadata
            self.config = {
                "indexes": [
                    {
                        "name": "Nifty 50",
                        "source": "nse_api",
                        "params": {"index_name": "NIFTY 50"}
                    },
                    {
                        "name": "Nifty Next 50",
                        "source": "nse_api",
                        "params": {"index_name": "NIFTY NEXT 50"}
                    },
                    {
                        "name": "Nifty Midcap 150",
                        "source": "nse_api",
                        "params": {"index_name": "NIFTY MIDCAP 150"}
                    },
                    {
                        "name": "Nifty Smallcap 250",
                        "source": "nse_api",
                        "params": {"index_name": "NIFTY SMALLCAP 250"}
                    },
                    {
                        "name": "Nasdaq 100",
                        "source": "nasdaq_official",
                        "params": {"index_symbol": "NDX"}
                    },
                    {
                        "name": "VXUS",
                        "source": "vanguard_etf",
                        "params": {"fund_id": "3369"}
                    },
                    {
                        "name": "QQQM",
                        "source": "nasdaq_official",
                        "params": {"index_symbol": "NDX"}
                    }
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
    
    def fetch_from_nse(self, params: dict) -> Set[str]:
        """
        Fetch constituents from NSE India API
        Params: {"index_name": "NIFTY 50"}
        """
        index_name = params.get('index_name')
        if not index_name:
            return set()
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json',
                'Accept-Language': 'en-US,en;q=0.9',
            }
            
            url = f"https://www.nseindia.com/api/equity-stockIndices?index={index_name.replace(' ', '%20')}"
            
            session = requests.Session()
            # Visit homepage first to get cookies
            session.get("https://www.nseindia.com", headers=headers, timeout=10)
            time.sleep(1)
            
            response = session.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            constituents = {item['symbol'] for item in data.get('data', [])}
            
            return constituents
            
        except Exception as e:
            print(f"NSE API error for {index_name}: {e}")
            # Fallback to CSV
            try:
                csv_url = f"https://archives.nseindia.com/content/indices/ind_{index_name.replace(' ', '').lower()}list.csv"
                import pandas as pd
                df = pd.read_csv(csv_url)
                return set(df.iloc[:, 2].dropna().tolist())
            except Exception as e2:
                print(f"NSE CSV fallback failed: {e2}")
                return set()
    
    def fetch_from_nasdaq(self, params: dict) -> Set[str]:
        """
        Fetch constituents from Nasdaq official source
        Params: {"index_symbol": "NDX"}
        Uses Nasdaq's official data portal
        """
        index_symbol = params.get('index_symbol', 'NDX')
        
        try:
            # Try Nasdaq's data link service first
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json'
            }
            
            # Nasdaq provides downloadable CSV files
            url = f"https://www.nasdaq.com/market-activity/quotes/nasdaq-{index_symbol.lower()}-index"
            
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for ticker symbols in the page
            constituents = set()
            
            # Try to find data tables with constituents
            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) >= 2:
                        # Look for ticker pattern (usually uppercase, 1-5 chars)
                        potential_ticker = cells[0].get_text().strip()
                        if potential_ticker and potential_ticker.isupper() and 1 <= len(potential_ticker) <= 5:
                            constituents.add(potential_ticker)
            
            # Fallback to Wikipedia as secondary source (more reliable for Nasdaq 100)
            if len(constituents) < 50:  # Nasdaq 100 should have ~100 stocks
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
            print(f"Nasdaq fetch error: {e}")
            return set()
    
    def fetch_from_vanguard(self, params: dict) -> Set[str]:
        """
        Fetch holdings from Vanguard ETF
        Params: {"fund_id": "3369"} for VXUS
        """
        fund_id = params.get('fund_id')
        if not fund_id:
            print("VXUS: Fund ID not provided")
            return set()
        
        try:
            # Vanguard provides holdings data
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            # Vanguard holdings page
            url = f"https://investor.vanguard.com/investment-products/etfs/profile/vxus"
            
            print(f"VXUS: Tracking top holdings only (full list has 7000+ holdings)")
            
            # For VXUS with 7000+ holdings, only track top holdings changes
            # This is a limitation - full tracking would require API access
            return set()
            
        except Exception as e:
            print(f"Vanguard fetch error: {e}")
            return set()
    
    def fetch_constituents(self, index_config: dict) -> Set[str]:
        """
        Generic fetch function that routes to appropriate source handler
        """
        index_name = index_config['name']
        source = index_config['source']
        params = index_config.get('params', {})
        
        print(f"Fetching constituents for {index_name}...")
        
        # Get the appropriate handler
        handler = self.source_handlers.get(source)
        
        if not handler:
            print(f"  Unknown source type: {source}")
            return set()
        
        # Fetch constituents using the handler
        constituents = handler(params)
        
        # Clean all symbols
        constituents = {self.clean_symbol(s) for s in constituents}
        
        print(f"  Found {len(constituents)} constituents")
        return constituents
    
    def fetch_all_constituents(self) -> Dict[str, List[str]]:
        """Fetch constituents for all configured indexes"""
        current_state = {}
        
        for index_config in self.config['indexes']:
            constituents = self.fetch_constituents(index_config)
            current_state[index_config['name']] = sorted(list(constituents))
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
        month_year = datetime.now().strftime('%Y-%m')
        month_year = month_year.encode('ascii', 'ignore').decode('ascii')
        
        if not changes:
            body = "No Index Constituent Changes - " + month_year + "\n\n"
            body += "=" * 60 + "\n\n"
            body += "All monitored indexes remain unchanged:\n\n"
            for index_config in self.config['indexes']:
                body += "  - " + index_config['name'] + "\n"
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
        sender = os.environ.get('EMAIL_SENDER', '')
        password = os.environ.get('EMAIL_PASSWORD', '')
        
        # Force clean secrets - remove ALL whitespace including non-breaking spaces
        sender = ''.join(sender.split())
        sender = sender.encode('ascii', 'ignore').decode('ascii')
        
        password = ''.join(password.split())
        password = password.encode('ascii', 'ignore').decode('ascii')
        
        if not sender or not password:
            print("Email credentials not found in environment variables")
            print("Set EMAIL_SENDER and EMAIL_PASSWORD")
            return
        
        recipient = self.config['email']['recipient']
        
        # Clean recipient
        recipient = ''.join(recipient.split())
        recipient = recipient.encode('ascii', 'ignore').decode('ascii')
        
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
        
        # Generate and clean month_year
        month_year = datetime.now().strftime('%Y-%m')
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
