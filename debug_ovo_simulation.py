import asyncio
from colorama import Fore, Style

# Mocking the structure of the OVO API response
# OVO usually requires a phone number, and the response might be slightly different
# but generally follows the same Midtrans/SociaBuzz structure.
OVO_RESPONSE_JSON = {
    "status": True,
    "csrf_hash": "mock_hash_ovo",
    "payment_method": "ovo",
    "type_payment": "ewallet_id",
    "source_payment": "midtrans",
    "inv_id": "TRIBE-IDR-OVO-123456",
    "redirect": False,
    "data": {
        "token": "ovo-token-uuid-12345",
        # OVO via Midtrans Snap often redirects to a page where you input phone number 
        # OR if phone was pre-filled, it might push to app. 
        # SociaBuzz usually gives the Snap URL.
        "redirect_url": "https://app.midtrans.com/snap/v4/redirection/ovo-token-uuid-12345" 
    }
}

async def simulate_ovo_flow():
    print(f"{Fore.MAGENTA}🚀 Simulating OVO Payment Flow...{Style.RESET_ALL}")
    
    # 1. API Response Simulation
    result = OVO_RESPONSE_JSON
    print(f"   [API Response] {result}")
    
    # 2. Extract Data
    method = "ovo"
    data = result.get('data', {})
    midtrans_token = data.get('token')
    redirect_url = data.get('redirect_url')
    
    # 3. UI Logic (mimicking telegram_bot.py)
    keyboard = []
    if redirect_url:
            # Dynamic button text check
            btn_text = "📱 Buka Aplikasi GoJek" if method == "gopay" else f"📱 Buka Aplikasi {method.upper()}"
            keyboard.append({"text": btn_text, "url": redirect_url})
    
    keyboard.append({"text": "🔄 Cek Status", "callback_data": f"chk_{method}_{midtrans_token}"})
    keyboard.append({"text": "🔙 Ganti Metode", "callback_data": "change_method"})
    
    msg_text = f"✅ *Tagihan {method.upper()} Dibuat!*\n\n"
    if redirect_url:
        msg_text += f"Klik tombol di bawah untuk membuka aplikasi {method.upper()} dan menyelesaikan pembayaran.\n\n"
    else:
        msg_text += f"Silakan selesaikan pembayaran melalui aplikasi {method.upper()}.\n\n"
        
    msg_text += f"_Bot akan otomatis memberitahu jika pembayaran berhasil._"

    print("\n--------------------------------")
    print(f"{Fore.GREEN}🖼️  UI PREVIEW ({method.upper()}):{Style.RESET_ALL}")
    print("--------------------------------")
    print(msg_text)
    print("--------------------------------")
    for btn in keyboard:
        if "url" in btn:
             print(f"[{btn['text']}] -> (Opens {btn['url']})")
        else:
             print(f"[{btn['text']}] -> (Callback: {btn['callback_data']})")
    print("--------------------------------")
    
    # 4. Status Check Logic Verification
    print(f"\n🔍 Verifying Status Check Logic for {method}...")
    # OVO typically sends a push notification. The "Check Status" usually looks for "Pending" or "Success".
    # In api.py, we check for "Menunggu Pembayaran" or "Cek ponsel Anda".
    
    print(f"   - Callback Data: chk_{method}_{midtrans_token}")
    print(f"   - Token for API Check: {midtrans_token}")
    print(f"   - Fallback URL (if token fails): https://sociabuzz.com/payment/x/{{UUID}} (Not present in this mock, but handled in bot)")

if __name__ == "__main__":
    asyncio.run(simulate_ovo_flow())
