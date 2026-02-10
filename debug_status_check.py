import json
import time
from src.core.auth import AuthManager
from src.core.api import APIManager

def debug_status():
    print("=== DEBUG STATUS CHECK ===")
    
    auth = AuthManager()
    api = APIManager(auth.session)
    
    # 1. Create a Payment to get a Token
    print("\n1. Creating Payment...")
    username = "bimaikhsan"
    amount = 10000
    res = api.create_support_payment(username, amount, "Status Check Test", "debug@test.com", "Debug User")
    
    if not res:
        print("Failed to create payment.")
        return

    payment_url = None
    if 'content' in res and 'redirect' in res['content']:
        payment_url = res['content']['redirect']
    elif 'data' in res and 'url' in res['data']:
        payment_url = res['data']['url']
        
    print(f"Payment URL: {payment_url}")
    
    if not payment_url:
        return

    # 2. Select GoPay to get Midtrans Token
    print("\n2. Selecting GoPay...")
    gopay_res = api.select_payment_method(payment_url, "gopay")
    
    midtrans_token = None
    if gopay_res and 'data' in gopay_res and 'token' in gopay_res['data']:
        midtrans_token = gopay_res['data']['token']
        print(f"Midtrans Token: {midtrans_token}")
    
    if not midtrans_token:
        print("Failed to get Midtrans token.")
        return

    # 3. Check Status using the Token (Simulate "Check Status" button click)
    print("\n3. Checking Status via Midtrans API...")
    status_data = api._get_midtrans_deep_link(midtrans_token)
    
    if status_data:
        print("\n[STATUS DATA]")
        # Print relevant status fields
        print(f"Transaction Status: {status_data.get('transaction_status')}")
        print(f"Status Message: {status_data.get('status_message')}")
        print(f"Status Code: {status_data.get('status_code')}")
    else:
        print("Failed to fetch status data.")

if __name__ == "__main__":
    debug_status()
