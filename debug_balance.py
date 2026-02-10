import re
from src.core.auth import AuthManager
from src.core.api import APIManager
from bs4 import BeautifulSoup

def check_balance():
    print("=== DEBUG BALANCE CHECK ===")
    
    auth = AuthManager()
    if not auth.check_session():
        print("Not logged in. Please login via main.py first.")
        return

    session = auth.session
    base_url = "https://sociabuzz.com"
    
    # 1. Try Dashboard Page
    print("\n1. Fetching Dashboard...")
    dashboard_url = f"{base_url}/pro/dashboard"
    res = session.get(dashboard_url)
    
    if res.status_code == 200:
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # Try to find balance elements
        # Pattern usually: Rp 10.000 or IDR 10.000
        # Common classes: 'balance', 'amount', 'wallet'
        
        print("Searching for balance in HTML...")
        
        # Approach 1: Regex search on text
        # Look for "Rp" followed by numbers
        text = res.text
        # Remove massive whitespace for easier regex
        clean_text = re.sub(r'\s+', ' ', text)
        
        # Common patterns in SociaBuzz dashboard (based on assumption)
        # Usually in a div with "Saldo" or "Balance" label
        
        # Let's print out text that looks like currency
        matches = re.findall(r'Rp\s*[\d\.,]+', clean_text)
        print(f"Currency strings found: {matches[:5]}...") # Show first 5
        
        # Approach 2: Look for specific API endpoints called in the page
        # Often dashboard loads data via AJAX
        print("\nChecking for AJAX calls in scripts...")
        scripts = soup.find_all('script')
        for script in scripts:
            if script.string and '/api/' in script.string:
                print(f"Found potential API call: {script.string[:100]}...")

    # 2. Try specific likely endpoints
    print("\n2. Probing Balance Endpoints...")
    endpoints = [
        "/pro/api/wallet",
        "/pro/api/balance",
        "/api/balance",
        "/api/wallet",
        "/pro/dashboard/wallet"
    ]
    
    for ep in endpoints:
        url = f"{base_url}{ep}"
        print(f"Checking {url}...")
        try:
            r = session.get(url)
            if r.status_code == 200 and 'json' in r.headers.get('Content-Type', ''):
                print(f"FOUND JSON at {ep}: {r.json()}")
            elif r.status_code == 200:
                print(f"Found Page at {ep} (HTML)")
        except:
            pass

if __name__ == "__main__":
    check_balance()
