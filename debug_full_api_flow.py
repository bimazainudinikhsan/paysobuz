import asyncio
import logging
import json
import requests
import time
from src.core.auth import AuthManager
from src.core.api import APIManager

# Configure logging
logging.basicConfig(level=logging.DEBUG)

def debug_api_flow():
    print("🚀 Starting API Debug Flow...")
    
    # 1. Initialize
    auth = AuthManager()
    # Manual session check
    try:
        r = auth.session.get("https://sociabuzz.com/pro/dashboard")
        if "login" in r.url:
            print("❌ Session invalid. Please login first.")
            return
    except:
        pass

    api = APIManager(auth.session)
    api.set_debug_mode(True) # Enable detailed logging
    
    # 2. Create Payment
    print("\n📦 Creating Test Payment...")
    username = "bimaikhsan" # Target username
    amount = 10000
    message = "Debug Test API"
    email = "debug@example.com"
    fullname = "Debug User"
    
    payment_data = api.create_support_payment(username, amount, message, email, fullname)
    
    if not payment_data:
        print("❌ Failed to create payment.")
        return

    print(f"✅ Payment Created: {json.dumps(payment_data, indent=2)}")
    
    redirect_url = payment_data.get('content', {}).get('redirect')
    if not redirect_url:
        print("❌ No redirect URL found.")
        return

    print(f"🔗 Redirect URL: {redirect_url}")
    order_id = redirect_url.split('/')[-1]
    print(f"🆔 Order ID: {order_id}")

    # 3. Select Payment Method (QRIS) to inspect response
    print("\n💳 Selecting Payment Method (QRIS)...")
    qris_data = api.select_payment_method(redirect_url, "qris")
    
    if qris_data:
        print(f"✅ QRIS Response Data: {json.dumps(qris_data, indent=2)}")
        
        # Analyze Response for Status URLs
        data = qris_data.get('data', {})
        # exit() # Stop here to see full output without truncation risk from subsequent calls
    else:
        print("❌ Failed to select QRIS.")
        
    return # Stop early
    
    # 4. Probe for Status API
    print("\n🕵️ Probing for potential Status APIs on SociaBuzz...")
    
    probe_endpoints = [
        f"https://sociabuzz.com/payment/check/{order_id}",
        f"https://sociabuzz.com/api/payment/{order_id}",
        f"https://sociabuzz.com/api/transaction/{order_id}",
        f"https://sociabuzz.com/payment/status?order_id={order_id}",
        f"https://sociabuzz.com/payment/check_status", # POST candidate
    ]
    
    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Referer": redirect_url
    }

    for url in probe_endpoints:
        print(f"   Probing {url}...", end=" ")
        try:
            resp = auth.session.get(url, headers=headers)
            print(f"[{resp.status_code}]")
            if resp.status_code == 200:
                try:
                    print(f"   🎉 FOUND POTENTIAL ENDPOINT! Content: {resp.text[:200]}")
                except:
                    pass
        except Exception as e:
            print(f"Error: {e}")

    # 5. Check GoPay/Midtrans as well
    print("\n💳 Selecting Payment Method (GoPay)...")
    gopay_data = api.select_payment_method(redirect_url, "gopay")
    if gopay_data:
         print(f"✅ GoPay Response Data: {json.dumps(gopay_data, indent=2)}")
         
         token = gopay_data.get('data', {}).get('token')
         if token:
             print(f"\n🔍 Checking Midtrans Status for Token: {token}")
             status = api.check_payment_status(token, "gopay", redirect_url)
             print(f"   Midtrans Status: {status}")

if __name__ == "__main__":
    debug_api_flow()
