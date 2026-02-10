from src.core.transactions import TransactionManager
import json

def test_transactions():
    print("=== Testing Transaction Module ===")
    
    # Initialize
    tm = TransactionManager()
    
    # 1. Test Balance
    print("\n[*] Testing get_balance_info()...")
    balance_info = tm.get_balance_info()
    print(json.dumps(balance_info, indent=2))
    
    if not balance_info.get("success"):
        print("[-] Failed to get balance. Stopping.")
        return

    # 2. Test History
    print("\n[*] Testing get_history()...")
    history = tm.get_history(page=1)
    # Print summary to avoid clutter
    print(f"Success: {history.get('success')}")
    print(f"Total Transactions: {history.get('total')}")
    print(f"Transactions Data: {history.get('transactions')}")

    # 3. Test Withdraw History (Optional)
    print("\n[*] Testing get_withdraw_history()...")
    withdraw = tm.get_withdraw_history()
    print(f"Success: {withdraw.get('success')}")
    print(f"Total Withdrawals: {withdraw.get('total')}")

if __name__ == "__main__":
    try:
        test_transactions()
    except Exception as e:
        print(f"[-] Error: {e}")
