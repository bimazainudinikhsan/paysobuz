import logging
import requests
from src.core.auth import AuthManager
from bs4 import BeautifulSoup

# Configure logging
logging.basicConfig(level=logging.INFO)

def debug_withdrawal_page():
    print("🚀 Starting Withdrawal Page Debug...")
    
    # 1. Initialize Auth
    auth = AuthManager()
    
    # Check session
    try:
        r = auth.session.get("https://sociabuzz.com/pro/dashboard")
        if "login" in r.url:
            print("❌ Session invalid. Please login first via main CLI.")
            return
        print("✅ Session valid.")
    except Exception as e:
        print(f"❌ Error checking session: {e}")
        return

    # 2. Fetch Transaction Page
    url = "https://sociabuzz.com/proaccount/transaction"
    print(f"\n🌍 Fetching {url}...")
    
    try:
        response = auth.session.get(url)
        print(f"✅ Response Code: {response.status_code}")
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 3. Analyze "Saldo" Tab
            print("\n🔍 Analyzing Withdrawal/Saldo Section...")
            
            # Find balance
            # Based on common patterns, looking for currency format or specific classes
            # Since I don't know the exact class, I'll print potential candidates
            
            # Try to find specific elements mentioned in the user's image request
            # "Saldo", "Cairkan ke", "BANK", "GOPAY", "DANA"
            
            page_text = soup.get_text()
            if "Saldo" in page_text:
                print("✅ Found 'Saldo' text in page.")
            else:
                print("⚠️ 'Saldo' text not found.")

            # Look for the form or inputs
            forms = soup.find_all('form')
            print(f"\n📋 Found {len(forms)} forms.")
            for i, form in enumerate(forms):
                print(f"  Form #{i+1} Action: {form.get('action')}")
                inputs = form.find_all('input')
                print(f"  Inputs: {[inp.get('name') for inp in inputs]}")
                
            # Dump a portion of HTML for manual inspection if needed
            print("\n📄 Page Content Snippet (First 1000 chars of body):")
            body = soup.find('body')
            if body:
                print(body.prettify()[:1000])
            else:
                print(response.text[:1000])
                
            print("\n💾 Saving full HTML to 'debug_withdrawal_page.html' for inspection...")
            with open("debug_withdrawal_page.html", "w", encoding="utf-8") as f:
                f.write(response.text)
            print("✅ Saved.")
            
    except Exception as e:
        print(f"❌ Error fetching page: {e}")

if __name__ == "__main__":
    debug_withdrawal_page()
