from src.core.auth import AuthManager

def sniff_transactions():
    print("=== SNIFFING TRANSACTION API ===")
    print("Browser will open. Please log in if needed.")
    print("Then navigate to the TRANSACTION page (https://sociabuzz.com/proaccount/transaction).")
    print("Wait for the data to load.")
    print("Then check back here and press Ctrl+C to stop and analyze logs.")
    
    auth = AuthManager()
    auth.sniff_api_traffic()

if __name__ == "__main__":
    sniff_transactions()
