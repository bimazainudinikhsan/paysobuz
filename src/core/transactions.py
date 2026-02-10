import requests
from bs4 import BeautifulSoup
import re
import json
import os
from .auth import AuthManager

class TransactionManager:
    def __init__(self, auth_manager=None):
        self.auth = auth_manager if auth_manager else AuthManager()
        self.base_url = "https://sociabuzz.com/proaccount/transaction"
        self.headers = {
            "Referer": "https://sociabuzz.com/proaccount/transaction",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01"
        }
        
    def save_to_json(self, filename="transactions.json"):
        """Fetches latest data and saves to a JSON file."""
        try:
            print(f"Fetching transaction data for {filename}...")
            # Fetch various data points
            balance_info = self.get_balance_info()
            history = self.get_history(page=1)
            pending = self.get_pending_transactions(page=1)
            withdrawals = self.get_withdraw_history(page=1)
            
            data = {
                "timestamp": __import__('time').time(),
                "balance_info": balance_info,
                "history": history,
                "pending": pending,
                "withdrawals": withdrawals
            }
            
            # Save to file
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            print(f"Transaction data saved to {filename}")
            return True
        except Exception as e:
            print(f"Error saving transaction data: {e}")
            return False

    def ensure_session(self):
        """Ensures that the session is valid and cookies are loaded."""
        # self.auth.load_cookies() # Redundant if sharing AuthManager instance
        if not self.auth.check_session():
            raise Exception("Session invalid. Please login first.")

    def get_balance_info(self):
        """
        Fetches the menu data which includes current balance and total earnings.
        Returns:
            dict: {
                "balance": float,
                "total_saldo": float,
                "success": bool,
                "raw_response": dict
            }
        """
        self.ensure_session()
        endpoint = f"{self.base_url}/getMenu"
        
        self.auth.session.headers.update(self.headers)
        
        try:
            r = self.auth.session.get(endpoint)
            if r.status_code == 200:
                data = r.json()
                if data.get("success"):
                    return {
                        "balance": data.get("balance", 0),
                        "total_saldo": data.get("totalSaldo", 0),
                        "success": True,
                        "raw_response": data
                    }
                return {"success": False, "error": "API returned success=False", "raw_response": data}
            else:
                return {"success": False, "error": f"HTTP {r.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_history(self, page=1, search=""):
        """
        Fetches transaction history.
        Args:
            page (int): Page number.
            search (str): Search keyword.
        Returns:
            dict: Parsed transaction data.
        """
        self.ensure_session()
        endpoint = f"{self.base_url}/getDataHistory"
        params = {"page": page, "search": search}
        
        self.auth.session.headers.update(self.headers)
        
        try:
            r = self.auth.session.get(endpoint, params=params)
            if r.status_code == 200:
                data = r.json()
                if data.get("success"):
                    # Parse HTML data
                    parsed_transactions = self._parse_transaction_html(data.get("data", ""))
                    return {
                        "success": True,
                        "total": data.get("total", 0),
                        "limit": data.get("limit", 10),
                        "transactions": parsed_transactions,
                        "raw_html": data.get("data", "")
                    }
                return {"success": False, "error": "API returned success=False", "raw_response": data}
            else:
                return {"success": False, "error": f"HTTP {r.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _parse_transaction_html(self, html_content):
        """Parses the HTML content returned by the API."""
        soup = BeautifulSoup(html_content, 'html.parser')
        transactions = []
        
        # Check for empty state
        if "Belum ada riwayat transaksi" in soup.get_text():
            return []
            
        # Update class selector to match actual HTML: transaction__item
        # Use strict regex to avoid matching children like transaction__itemLeft or transaction__item__title
        rows = soup.find_all('div', class_=re.compile(r'^(transaction__item|transaction-item)$'))
        
        if not rows:
            # Fallback: Split by common dividers if no clear rows found, or return raw text blocks
            # For now, if no structure is found but it's not empty, we return the text to be safe
            text_content = soup.get_text(separator=' | ', strip=True)
            if text_content:
                return [{"title": "Raw Data", "date": "", "amount": "", "text": text_content}]
            return []
        
        for row in rows:
            # Title
            title_div = row.find('div', class_=re.compile(r'transaction__item__title|title'))
            title = title_div.get_text(strip=True) if title_div else "No Title"
            
            # Date
            date_div = row.find('div', class_=re.compile(r'transaction__item__date|date'))
            date = date_div.get_text(strip=True) if date_div else "No Date"
            
            # Amount
            amt_div = row.find('div', class_=re.compile(r'transaction__item__amt|amount'))
            amount = amt_div.get_text(strip=True) if amt_div else "0"
            
            # Filter out empty or invalid rows
            if title == "No Title" and date == "No Date" and amount == "0":
                continue
                
            transactions.append({
                "title": title,
                "date": date,
                "amount": amount,
                "text": f"{title} - {amount}" # For backward compatibility if needed
            })
            
        return transactions

    def get_withdraw_history(self, page=1):
        return self._fetch_generic_data("getDataWithdraw", page)

    def get_pending_transactions(self, page=1):
        return self._fetch_generic_data("getDataPending", page)

    def get_waiting_payment(self, page=1):
        return self._fetch_generic_data("getDataWaiting", page)
        
    def get_in_process(self, page=1, search=""):
        return self._fetch_generic_data("getDataInprocess", page, search=search)

    def _fetch_generic_data(self, endpoint_suffix, page, search=None):
        """Helper for other similar endpoints."""
        self.ensure_session()
        endpoint = f"{self.base_url}/{endpoint_suffix}"
        params = {"page": page}
        if search is not None:
            params["search"] = search
            
        self.auth.session.headers.update(self.headers)
        
        try:
            r = self.auth.session.get(endpoint, params=params)
            if r.status_code == 200:
                data = r.json()
                if data.get("success"):
                    parsed_data = self._parse_transaction_html(data.get("data", ""))
                    return {
                        "success": True,
                        "total": data.get("total", 0),
                        "limit": data.get("limit", 10),
                        "data": parsed_data
                    }
                return {"success": False, "error": "API returned success=False", "raw_response": data}
            else:
                return {"success": False, "error": f"HTTP {r.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
