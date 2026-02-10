from src.core.auth import AuthManager
from src.core.api import APIManager
from colorama import init, Fore
import json
import requests

init(autoreset=True)

def debug_midtrans():
    print("Initializing Auth and API...")
    auth = AuthManager()
    api = APIManager(auth.session)
    
    # 1. Create a payment first to get a URL
    username = "bimaikhsan" 
    amount = 10000
    message = "Debug Midtrans Pay"
    email = "debug@example.com"
    fullname = "Debug User"
    
    print(f"Creating payment for {username}...")
    create_result = api.create_support_payment(username, amount, message, email, fullname)
    
    payment_url = None
    if create_result:
        if 'content' in create_result and 'redirect' in create_result['content']:
            payment_url = create_result['content']['redirect']
        elif 'data' in create_result and 'url' in create_result['data']:
            payment_url = create_result['data']['url']
            
    if not payment_url:
        print(f"{Fore.RED}Failed to create payment. Cannot proceed.")
        return

    print(f"Payment URL created: {payment_url}")
    
    # 2. Select GoPay method
    print("Selecting GoPay method...")
    gopay_result = api.select_payment_method(payment_url, "gopay")
    
    if gopay_result and 'data' in gopay_result and 'token' in gopay_result['data']:
        token = gopay_result['data']['token']
        print(f"\nMidtrans Token: {token}")
        
        # 3. POST to Midtrans Pay API
        print("Charging GoPay Transaction...")
        try:
            api_url = f"https://app.midtrans.com/snap/v1/transactions/{token}/pay"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'Origin': 'https://app.midtrans.com',
                'Referer': f"https://app.midtrans.com/snap/v4/redirection/{token}"
            }
            payload = {
                "payment_type": "gopay"
            }
            
            response = requests.post(api_url, json=payload, headers=headers)
            print(f"Pay API Response Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print("\nPayment Data:")
                print(json.dumps(data, indent=2))
            else:
                print(f"Failed to charge transaction. Response: {response.text[:500]}")
                
        except Exception as e:
            print(f"Error calling midtrans pay api: {e}")
    else:
        print("Could not find token in GoPay response")
        print(json.dumps(gopay_result, indent=2))

if __name__ == "__main__":
    debug_midtrans()
