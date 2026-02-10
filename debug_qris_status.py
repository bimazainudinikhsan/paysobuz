from src.core.auth import AuthManager
from src.core.api import APIManager
import json
import time

def check_qris_status_simulation():
    auth = AuthManager()
    if not auth.check_session():
        auth.login()
        
    api = APIManager(auth.session)
    
    # 1. Create Payment
    print("Creating payment...")
    res = api.create_support_payment("bimaikhsan", 10000, "Status Check Test", "debug@test.com", "DebugUser")
    
    url = None
    if res and 'data' in res and 'url' in res['data']:
        url = res['data']['url']
    elif res and 'content' in res and 'redirect' in res['content']:
        url = res['content']['redirect']
        
    if not url:
        print("Failed to get URL")
        return
        
    print(f"Payment URL: {url}")
    
    # 2. Select QRIS
    print("Selecting QRIS...")
    qris_res = api.select_payment_method(url, "qris")
    # print(json.dumps(qris_res, indent=2))
    
    # 3. Check status mechanism
    # Try fetching the payment URL again to see if it changes or if there's a status in the HTML
    print("Checking status via Payment URL...")
    r = api.session.get(url)
    print(f"Status Code: {r.status_code}")
    # print(r.text[:500]) # Peek content
    
    if "payment_status" in r.text or "status" in r.text:
        print("Found 'status' keyword in HTML")
        
    # Also try the endpoint /payment/check/{uuid} if it exists (guessing)
    # The uuid is in the URL: https://sociabuzz.com/payment/x/{uuid}
    uuid = url.split('/')[-1]
    check_url = f"https://sociabuzz.com/payment/check/{uuid}"
    print(f"Trying guessed endpoint: {check_url}")
    r2 = api.session.get(check_url)
    print(f"Check Endpoint Status: {r2.status_code}")
    if r2.status_code == 200:
        print("Response:", r2.text)

if __name__ == "__main__":
    check_qris_status_simulation()
