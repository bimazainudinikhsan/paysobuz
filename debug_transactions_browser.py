import time
import undetected_chromedriver as uc
from src.core.auth import AuthManager
from bs4 import BeautifulSoup

def debug_transactions_browser():
    print("=== DEBUG TRANSACTIONS (BROWSER) ===")
    
    auth = AuthManager()
    if not auth.check_session():
        print("Warning: Session might be invalid, but we'll try injecting cookies anyway.")

    options = uc.ChromeOptions()
    options.add_argument("--no-first-run")
    options.add_argument("--password-store=basic")
    
    driver = uc.Chrome(options=options, use_subprocess=True, version_main=144)
    
    try:
        # 1. Go to domain to set cookies
        driver.get("https://sociabuzz.com")
        
        # 2. Inject cookies
        for cookie in auth.session.cookies:
            try:
                driver.add_cookie({
                    'name': cookie.name,
                    'value': cookie.value,
                    'domain': cookie.domain if cookie.domain else '.sociabuzz.com',
                    'path': '/'
                })
            except:
                pass
        
        print("Cookies injected.")
        
        # 3. Go to Transaction Page
        url = "https://sociabuzz.com/proaccount/transaction"
        print(f"Navigating to {url}...")
        driver.get(url)
        
        print("Waiting 10 seconds for content to load...")
        time.sleep(10)
        
        # 4. Get HTML
        html = driver.page_source
        soup = BeautifulSoup(html, 'html.parser')
        
        # 5. Analyze
        print("\n[Analysis]")
        
        # Check title
        print(f"Page Title: {driver.title}")
        
        # Check current URL (did we get redirected?)
        print(f"Current URL: {driver.current_url}")
        
        if "login" in driver.current_url:
            print("REDIRECTED TO LOGIN! Cookies might be expired or invalid.")
        else:
            # Search for tables
            tables = soup.find_all('table')
            print(f"Found {len(tables)} tables.")
            
            for i, table in enumerate(tables):
                print(f"\nTable {i+1} Content:")
                # Headers
                headers = [th.get_text(strip=True) for th in table.find_all('th')]
                print(f"Headers: {headers}")
                
                # First row
                rows = table.find_all('tr')
                if len(rows) > 1:
                    first_row = rows[1] # 0 is header usually
                    cols = [td.get_text(strip=True) for td in first_row.find_all('td')]
                    print(f"First Data Row: {cols}")
                else:
                    print("Table empty.")
            
            # If no tables, dump some text to see what's there
            if not tables:
                print("\nNo tables found. Page text snippet:")
                print(soup.get_text(separator=' ', strip=True)[:500])

    except Exception as e:
        print(f"Error: {e}")
    finally:
        print("Closing browser...")
        driver.quit()

if __name__ == "__main__":
    debug_transactions_browser()
