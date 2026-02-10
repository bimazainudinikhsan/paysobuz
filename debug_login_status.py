from src.core.auth import AuthManager
import requests

def debug_check_session():
    auth = AuthManager()
    print("Cookies loaded:", auth.session.cookies.get_dict())
    
    urls_to_check = [
        "https://sociabuzz.com/pro/dashboard",
        "https://sociabuzz.com/dashboard",
        "https://sociabuzz.com/client",
        "https://sociabuzz.com/pro",
        "https://sociabuzz.com/mylink"
    ]
    
    for url in urls_to_check:
        print(f"\nChecking {url}...")
        try:
            r = auth.session.get(url, allow_redirects=True)
            print(f"Status: {r.status_code}")
            print(f"Final URL: {r.url}")
            if "login" not in r.url and r.status_code == 200:
                print(">>> POTENTIAL VALID DASHBOARD <<<")
        except Exception as e:
            print(f"Error checking {url}: {e}")
            
    # Original check logic test removed for brevity as we are exploring


if __name__ == "__main__":
    debug_check_session()
