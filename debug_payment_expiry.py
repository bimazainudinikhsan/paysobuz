from src.core.auth import AuthManager
from src.core.api import APIManager
import json
import sys

def debug_payment_flow():
    auth = AuthManager()
    if not auth.check_session():
        print("Not logged in. Logging in...")
        if not auth.login():
            print("Login failed")
            return

    api = APIManager(auth.session)
    
    # 1. Create Payment
    print("Creating payment...")
    username = "bimaikhsan" # Ganti dengan username target yang valid jika perlu, atau gunakan input
    amount = 10000
    msg = "Debug Expiry"
    
    res = api.create_support_payment(username, amount, msg, "debug@test.com", "DebugUser")
    
    url = None
    if res:
        if 'content' in res and 'redirect' in res['content']:
            url = res['content']['redirect']
        elif 'data' in res and 'url' in res['data']:
            url = res['data']['url']
            
    if not url:
        print("Failed to get payment URL")
        print(json.dumps(res, indent=2))
        return

    print(f"Payment URL: {url}")
    
    # 2. Select QRIS
    print("\nSelecting QRIS...")
    qris_res = api.select_payment_method(url, "qris")
    print(json.dumps(qris_res, indent=2))
    
    # 3. Select GoPay
    print("\nSelecting GoPay...")
    gopay_res = api.select_payment_method(url, "gopay")
    print(json.dumps(gopay_res, indent=2))

if __name__ == "__main__":
    debug_payment_flow()
