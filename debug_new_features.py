import logging
import asyncio
import json
from src.core.auth import AuthManager
from src.core.api import APIManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def debug_new_features():
    print("🚀 Starting Debug for New Features...")
    
    auth = AuthManager()
    api = APIManager(auth.session)
    
    # Check session
    if not auth.check_session():
        print("❌ Not logged in. Please login first.")
        return

    print("✅ Session valid.")

    # 1. Test Payment Creation & New Bank Methods
    print("\n--------------------------------")
    print("🧪 TEST 1: Create Payment & Select Bank Method")
    print("--------------------------------")
    
    # Create a dummy payment (10,000 IDR)
    username = "bimaputra1" # Using the username from logs/previous context if available, or just a known one.
    # If username is unknown, we might fail. Let's try to get it from profile or use a common one.
    # Actually, let's use a dummy or the user's own profile if we can find it.
    # In api_logs.json, I saw requests to "sociabuzz.com/payment/send/create".
    # But create_support_payment needs a target username.
    # Let's assume we can pay to 'sociabuzz' or 'test'. 
    # Better: Use the one from the code or previous interactions.
    # Let's try 'bimaputra1' as it was seen in file paths/logs usually? No, I see 'bimaz' in file path.
    # Let's use a generic one or just skip if we don't know.
    # Wait, create_support_payment is for *donating* to someone.
    # Let's try to donate to 'sociabuzz' (official account) or just skip this real test if risky.
    
    # Actually, we can test the `withdraw_funds` payload formatting without sending it (Mocking).
    # But let's try to call the real API for `select_payment_method` if we can get a payment URL.
    
    # Mocking approach for safety and speed:
    print("⚠️ Skipping real payment creation to avoid spamming.")
    print("🔍 Verifying 'select_payment_method' logic locally...")
    
    # Mock _get_csrf_token to bypass 404 error
    api._get_csrf_token = lambda url: "mock_csrf_token_payment"
    
    # We will inspect the internal config map of the class instance if possible, 
    # or just call it and catch the error to see the payload.
    
    # Let's use a mock method to print what it WOULD send.
    original_post = api.session.post
    
    def mock_post(url, data=None, json=None, **kwargs):
        print(f"   [MOCK POST] URL: {url}")
        if json:
            print(f"   [MOCK POST] JSON: {json}")
        if data:
            print(f"   [MOCK POST] DATA: {data}")
            
        class MockResponse:
            status_code = 200
            text = "{}"
            def json(self): return {}
            
        return MockResponse()
    
    api.session.post = mock_post
    
    # Test Bank Mandiri
    print("\n👉 Testing 'mandiri' selection...")
    api.select_payment_method("https://sociabuzz.com/payment/123", "mandiri")
    
    # Test Bank BNC
    print("\n👉 Testing 'bnc' selection...")
    api.select_payment_method("https://sociabuzz.com/payment/123", "bnc")
    
    # 2. Test Withdrawal Payload Format
    print("\n--------------------------------")
    print("🧪 TEST 2: Withdrawal Payload Format")
    print("--------------------------------")
    
    # We want to ensure 50000 becomes "50.000" (dot separator)
    print("👉 Testing withdrawal of 50,000 to DANA...")
    # We need to mock _get_csrf_token too because withdraw_funds calls it
    # api._get_csrf_token = lambda url: "mock_csrf_token" # Already mocked above
    
    api.withdraw_funds("dana", 50000)
    
    print("\n--------------------------------")
    print("✅ Debug Complete.")

if __name__ == "__main__":
    asyncio.run(debug_new_features())
