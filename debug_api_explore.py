import json
import re
from urllib.parse import unquote, parse_qs, urlparse
from src.core.auth import AuthManager
from src.core.api import APIManager

def explore_api_data():
    print("=== DEBUG API EXPLORATION ===")
    
    auth = AuthManager()
    # Login is not required for creating support payment as a guest
    api = APIManager(auth.session)
    
    username = "bimaikhsan"
    amount = 10000
    
    # 1. Create Payment
    print(f"\n1. Creating Payment for {username}...")
    res = api.create_support_payment(username, amount, "Explore Data", "debug@explore.com", "Explore User")
    
    payment_url = None
    if 'content' in res and 'redirect' in res['content']:
        payment_url = res['content']['redirect']
    elif 'data' in res and 'url' in res['data']:
        payment_url = res['data']['url']
    
    if not payment_url:
        print("Failed to create payment.")
        return
        
    print(f"Payment URL: {payment_url}")

    # 2. Analyze GoPay/Midtrans Data
    print("\n--- GOPAY EXPLORATION ---")
    gopay_res = api.select_payment_method(payment_url, "gopay")
    
    if gopay_res and 'data' in gopay_res and 'midtrans_details' in gopay_res['data']:
        mt = gopay_res['data']['midtrans_details']
        
        print("\n[Deep Link Analysis]")
        deeplink = mt.get('deeplink_url', '')
        print(f"Original: {deeplink}")
        
        # Parse Query Params
        parsed = urlparse(deeplink)
        params = parse_qs(parsed.query)
        print(f"Params: {json.dumps(params, indent=2)}")
        
        # Check callback_url
        if 'callback_url' in params:
            print(f"Current callback_url: {params['callback_url']}")
            
            # EXPERIMENT: Can we inject a Telegram URL?
            # e.g., tg://resolve?domain=YourBotName
            # Or a simple http url
            new_callback = "https://t.me/SocialBuzzBot"
            print(f"Experiment: Changing callback_url to {new_callback}")
            
            # Construct new link
            # We need to be careful with encoding
            pass
            
        print("\n[Midtrans Response Keys]")
        print(list(mt.keys()))
        
    # 3. Analyze QRIS/Xendit Data
    print("\n--- QRIS EXPLORATION ---")
    # Need new payment to avoid conflict? Usually same payment URL allows switching methods
    qris_res = api.select_payment_method(payment_url, "qris")
    
    if qris_res and 'data' in qris_res:
        data = qris_res['data']
        qr_string = data.get('qr_string', '')
        
        print(f"\nQR String: {qr_string}")
        
        # Simple analysis of QR string (EMVCo format)
        # Look for merchant name tag (ID 59)
        # Format: ID (2 chars) Length (2 chars) Value
        
        i = 0
        while i < len(qr_string):
            tag = qr_string[i:i+2]
            length = int(qr_string[i+2:i+4])
            value = qr_string[i+4:i+4+length]
            
            tag_name = "Unknown"
            if tag == "59": tag_name = "Merchant Name"
            elif tag == "60": tag_name = "Merchant City"
            elif tag == "58": tag_name = "Country Code"
            elif tag == "53": tag_name = "Currency"
            elif tag == "54": tag_name = "Amount"
            elif tag == "62": tag_name = "Additional Data"
            
            if tag in ["59", "60", "62"]:
                 print(f"Tag {tag} ({tag_name}): {value}")
                 
            i += 4 + length

if __name__ == "__main__":
    explore_api_data()
