import asyncio
import re
from unittest.mock import MagicMock
from colorama import Fore, Style

# Mocking the structure of the API response
GOPAY_RESPONSE_JSON = {
    "status": True,
    "csrf_hash": "mock_hash",
    "payment_method": "gopay",
    "type_payment": "ewallet_id",
    "source_payment": "midtrans",
    "inv_id": "TRIBE-IDR-123456",
    "redirect": False,
    "data": {
        "token": "685c0cc7-77f5-4358-a8ce-24a978416a95",
        "redirect_url": "https://app.midtrans.com/snap/v4/redirection/685c0cc7-77f5-4358-a8ce-24a978416a95"
    }
}

# The goal is to simulate how the bot processes this to extract the deep link or redirection URL
# and then construct the UI message.

async def simulate_gopay_flow():
    print(f"{Fore.CYAN}🚀 Simulating GoPay Payment Flow...{Style.RESET_ALL}")
    
    # 1. API Response Simulation
    result = GOPAY_RESPONSE_JSON
    print(f"   [API Response] {result}")
    
    # 2. Extract Data
    data = result.get('data', {})
    midtrans_token = data.get('token')
    redirect_url = data.get('redirect_url')
    
    print(f"   [Extracted] Token: {midtrans_token}")
    print(f"   [Extracted] Redirect URL: {redirect_url}")
    
    # 3. Determine the "Button" URL
    # For GoPay/Midtrans, the redirect_url usually handles the app opening on mobile.
    # It might redirect to gojek:// or show a QR code on desktop.
    # The user wants "Buka Aplikasi GoJek".
    
    target_url = redirect_url
    
    # 4. Construct UI Message (Simulated)
    method_name = "GOPAY"
    
    message_text = (
        f"✅ *Tagihan {method_name} Dibuat!*\n\n"
        f"Klik tombol di bawah untuk membuka aplikasi {method_name} dan menyelesaikan pembayaran.\n\n"
        f"_Bot akan otomatis memberitahu jika pembayaran berhasil._"
    )
    
    buttons = [
        {"text": f"📱 Buka Aplikasi {method_name}", "url": target_url},
        {"text": "🔄 Cek Status", "callback_data": f"chk_gopay_{midtrans_token}"},
        {"text": "🔙 Ganti Metode", "callback_data": "change_method"}
    ]
    
    print("\n--------------------------------")
    print(f"{Fore.GREEN}🖼️  UI PREVIEW:{Style.RESET_ALL}")
    print("--------------------------------")
    print(message_text)
    print("--------------------------------")
    for btn in buttons:
        if "url" in btn:
             print(f"[{btn['text']}] -> (Opens {btn['url']})")
        else:
             print(f"[{btn['text']}] -> (Callback: {btn['callback_data']})")
    print("--------------------------------")

    # 5. Verify Deep Link Logic
    # In api.py, _get_midtrans_deep_link fetches deep link details. 
    # Let's verify if we need that or if redirect_url is enough.
    # If redirect_url is "https://app.midtrans.com/snap/v4/redirection/...", 
    # it is a universal link that should open GoJek app on mobile.
    
    if "midtrans.com" in target_url:
        print(f"\n✅ URL seems valid for Midtrans Snap Redirection.")
    else:
        print(f"\n❌ URL might be incorrect.")

if __name__ == "__main__":
    asyncio.run(simulate_gopay_flow())
