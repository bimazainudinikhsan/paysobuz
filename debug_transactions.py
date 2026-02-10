import requests
import json
from src.core.auth import AuthManager
from bs4 import BeautifulSoup
import re

def fetch_transactions():
    auth = AuthManager()
    auth.load_cookies()
    
    if not auth.check_session():
        print("[-] Session invalid or cookies missing. Please login first.")
        # Optional: Trigger login if needed, or just warn
        return

    session = auth.session
    # Set headers mimicking the browser
    session.headers.update({
        "Referer": "https://sociabuzz.com/proaccount/transaction",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/javascript, */*; q=0.01"
    })

    print("[*] Fetching Menu and Balance...")
    try:
        r = session.get("https://sociabuzz.com/proaccount/transaction/getMenu")
        if r.status_code == 200:
            data = r.json()
            if data.get("success"):
                print(f"[+] Balance: {data.get('balance')}")
                print(f"[+] Total Saldo: {data.get('totalSaldo')}")
            else:
                print("[-] getMenu success=False")
                print(data)
        else:
            print(f"[-] getMenu failed: {r.status_code}")
    except Exception as e:
        print(f"[-] Error fetching menu: {e}")

    print("\n[*] Fetching Transaction History...")
    try:
        r = session.get("https://sociabuzz.com/proaccount/transaction/getDataHistory?page=1&search=")
        if r.status_code == 200:
            data = r.json()
            if data.get("success"):
                html_content = data.get("data", "")
                # Save for debugging
                with open("transactions_data.html", "w", encoding="utf-8") as f:
                    f.write(html_content)
                
                print("[+] Transaction history HTML fetched. Parsing...")
                parse_transactions(html_content)
            else:
                print("[-] getDataHistory success=False")
        else:
            print(f"[-] getDataHistory failed: {r.status_code}")
    except Exception as e:
        print(f"[-] Error fetching history: {e}")

def parse_transactions(html):
    soup = BeautifulSoup(html, 'html.parser')
    
    # Based on typical bootstrap/table structure, or div structure seen in other files
    # The user said "0 tables", so it's likely div-based.
    # Let's look for typical row containers.
    # From the file analysis earlier, we saw classes like 'transaction-pro'
    
    # Let's inspect the saved HTML to be sure, but for now let's try to print text of all divs
    # that look like rows.
    
    rows = soup.find_all('div', class_='row') # Generic guess
    if not rows:
        # specific class search
        rows = soup.find_all('div', class_=re.compile(r'item|history|trans'))
    
    print(f"[*] Found {len(rows)} potential row elements.")
    
    # Let's try to be more specific if we can, but printing raw text helps identifying structure
    for i, row in enumerate(rows[:5]): # Print first 5
        print(f"--- Row {i+1} ---")
        print(row.get_text(strip=True))

if __name__ == "__main__":
    fetch_transactions()
