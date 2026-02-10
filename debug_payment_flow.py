
import asyncio
import time
from src.core.database import PaymentDatabase
from src.core.api import APIManager
from unittest.mock import MagicMock

async def debug_auto_payment_flow():
    print("=== DEBUG AUTO PAYMENT FLOW ===")
    
    # 1. Initialize DB
    db = PaymentDatabase("payment_history.json")
    
    # 2. Simulate User creating a payment
    user_id = 123456789
    print(f"1. Simulating payment creation for user {user_id}...")
    
    payment_id = db.add_payment(
        user_id=user_id,
        payment_url="https://sociabuzz.com/test/pay",
        method="gopay",
        amount=10000,
        message="Test Debug",
        donor_name="Debug User"
    )
    
    # Add dummy token for GoPay
    db.update_payment_status(payment_id, "pending", {"token": "DUMMY_TOKEN_123"})
    print(f"   Payment created! ID: {payment_id}")
    
    # 3. Verify it is pending
    pending = db.get_pending_payments()
    found = any(p['id'] == payment_id for p in pending)
    print(f"2. Verifying pending status... {'OK' if found else 'FAIL'}")
    
    if not found:
        return
        
    # 4. Simulate Background Task Logic (Mocking API)
    print("3. Simulating background monitoring...")
    
    # Mock API
    mock_api = MagicMock()
    # Simulate Success Response
    mock_api.check_payment_status.return_value = {
        "status": "settlement",
        "status_code": "200",
        "message": "Payment Successful"
    }
    
    # Monitoring Loop Iteration
    pending_payments = db.get_pending_payments()
    for payment in pending_payments:
        if payment['id'] == payment_id:
            print(f"   Checking status for {payment['id']}...")
            
            # Call Mock API
            status_info = mock_api.check_payment_status("DUMMY_TOKEN_123", "gopay", "http://mock.url")
            
            status_code = status_info.get('status_code')
            status_msg = status_info.get('status')
            
            if str(status_code) == "200" or status_msg == "settlement":
                print(f"   ✅ API returned SUCCESS! Updating DB...")
                db.update_payment_status(payment['id'], "success", status_info)
                
                # Mock Notification
                print(f"   📨 Sending Telegram Notification to {payment['user_id']}:")
                print(f"      'Payment Received! Rp{payment['amount']}'")
            else:
                print("   ❌ API returned pending/failed.")

    # 5. Verify DB Update
    updated_payment = db.get_payment(payment_id)
    print(f"4. Verifying final status... {updated_payment['status']}")
    
    if updated_payment['status'] == 'success':
        print("\n✅ TEST PASSED: System correctly handles auto-check and update.")
    else:
        print("\n❌ TEST FAILED: Status was not updated.")

    # Cleanup (Optional: remove test data)
    # db.data["payments"] = [p for p in db.data["payments"] if p['id'] != payment_id]
    # db._save_data()

if __name__ == "__main__":
    asyncio.run(debug_auto_payment_flow())
