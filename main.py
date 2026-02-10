import sys
import os
import json
import qrcode
import io
import threading
import time
import logging 
from colorama import init, Fore, Style
from src.core.auth import AuthManager

# Configure logging to silence httpx
logging.getLogger("httpx").setLevel(logging.WARNING)

from src.core.api import APIManager
from src.core.transactions import TransactionManager
from src.bot.telegram_bot import SocialBuzzBot
from config.settings import Config

# Initialize colorama
init(autoreset=True)

# Global flag for background monitoring
MONITORING_ACTIVE = False

def monitor_transactions_loop(tm):
    """Background task to save transaction data periodically."""
    global MONITORING_ACTIVE
    print(f"{Fore.MAGENTA}[Monitor] Background transaction monitoring started.")
    
    while MONITORING_ACTIVE:
        try:
            if tm.auth.check_session():
                tm.save_to_json()
            else:
                # If not logged in, just wait longer or do nothing
                pass
        except Exception as e:
            print(f"{Fore.RED}[Monitor] Error: {e}")
        
        # Wait for 60 seconds before next check
        time.sleep(60)
    
    print(f"{Fore.MAGENTA}[Monitor] Background transaction monitoring stopped.")

def start_monitoring(tm):
    global MONITORING_ACTIVE
    if not MONITORING_ACTIVE:
        MONITORING_ACTIVE = True
        t = threading.Thread(target=monitor_transactions_loop, args=(tm,), daemon=True)
        t.start()

def stop_monitoring():
    global MONITORING_ACTIVE
    MONITORING_ACTIVE = False

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def print_header():
    clear_screen()
    print(f"{Fore.BLUE}{Style.BRIGHT}{'='*40}")
    print(f"{Fore.BLUE}{Style.BRIGHT}        SociaBuzz Bot System")
    print(f"{Fore.BLUE}{Style.BRIGHT}{'='*40}")
    print(f"{Fore.CYAN}CLI & Telegram Bot Manager\n")

def run_cli():
    auth = AuthManager()
    api = APIManager(auth.get_session())
    tm = TransactionManager(auth)
    
    while True:
        print_header()
        
        is_logged_in = auth.check_session()
        if is_logged_in:
            status_text = f"{Fore.GREEN}Connected"
        else:
            status_text = f"{Fore.RED}Not Logged In"
            
        print(f"Status: {status_text}\n")
        
        print("1. Login (Browser)")
        print("2. Show Transactions (Get API)")
        print("3. Create Support Payment (Tribe)")
        print("4. Process Payment (Select Method)")
        print("5. Analyze API Traffic (Sniffing Mode)")
        print("6. Clear Cookies/Logout")
        print("7. Return to Main Menu")
        
        choice = input(f"\n{Fore.YELLOW}Select an option [7]: {Style.RESET_ALL}") or "7"
        
        if choice == "1":
            auth.login_with_browser()
            input("Press Enter to continue...")
            
        elif choice == "2":
            if not is_logged_in:
                print(f"{Fore.YELLOW}Warning: You are not logged in. Showing simulated data.")
                api.show_transactions()
            else:
                print(f"\n{Fore.CYAN}Fetching real transaction data...")
                
                # 1. Balance Info
                balance_info = tm.get_balance_info()
                if balance_info['success']:
                    print(f"\n{Fore.WHITE}{Style.BRIGHT}Balance Information")
                    print("-" * 40)
                    print(f"{Fore.GREEN}Active Balance : Rp{balance_info['balance']:,}")
                    print(f"{Fore.CYAN}Total Earnings : Rp{balance_info['total_saldo']:,}")
                    print("-" * 40)
                else:
                    print(f"{Fore.RED}Failed to fetch balance: {balance_info.get('error')}")

                # 2. History
                history = tm.get_history()
                if history['success']:
                    print(f"\n{Fore.WHITE}{Style.BRIGHT}Recent Transactions")
                    print("-" * 80)
                    transactions = history['transactions']
                    if not transactions:
                        print(f"{Fore.YELLOW}No transactions found.")
                    else:
                        for tx in transactions:
                            # If it's a dict with 'text', print it. If it's parsed structure, format it.
                            # Currently we return dict with 'text' and 'html' or raw text.
                            if isinstance(tx, dict):
                                print(f"{Fore.WHITE}{tx.get('text', str(tx))}")
                            else:
                                print(f"{Fore.WHITE}{tx}")
                            print("-" * 80)
                else:
                    print(f"{Fore.RED}Failed to fetch history: {history.get('error')}")

            input("Press Enter to continue...")
            
        elif choice == "3":
            print(f"\n{Fore.WHITE}{Style.BRIGHT}Create Support/Tribe Payment")
            print(f"{Fore.YELLOW}Note: Make sure the username exists and has Tribe enabled.")
            username = input("Target Username (e.g. bimaikhsan): ")
            if not username:
                print(f"{Fore.RED}Username is required!")
            else:
                while True:
                    try:
                        amount = int(input("Amount (IDR): "))
                        break
                    except ValueError:
                        print(f"{Fore.RED}Please enter a valid number.")
                
                message = input("Message (Note): ")
                fullname = input("Your Name [Supporter]: ") or "Supporter"
                email = input("Your Email [supporter@example.com]: ") or "supporter@example.com"
                
                result = api.create_support_payment(username, amount, message, email, fullname)
                if result:
                    print(f"{Fore.GREEN}Success! Result: {result}")
                    # If there's a redirect URL, show it
                    if 'content' in result and 'redirect' in result['content']:
                         print(f"{Fore.CYAN}Payment URL: {result['content']['redirect']}")
                    elif 'data' in result and 'url' in result['data']:
                         print(f"{Fore.CYAN}Payment URL: {result['data']['url']}")
                else:
                    print(f"{Fore.RED}Failed to create payment.")
            input("Press Enter to continue...")

        elif choice == "4":
            print(f"\n{Fore.WHITE}{Style.BRIGHT}Process Payment (Select Method)")
            url = input("Payment URL (e.g. https://sociabuzz.com/payment/x/...): ")
            if not url:
                print(f"{Fore.RED}URL is required!")
            else:
                method = input("Method (gopay/qris) [gopay]: ").lower() or "gopay"
                if method not in ['gopay', 'qris']:
                    print(f"{Fore.YELLOW}Invalid method, defaulting to gopay")
                    method = "gopay"
                
                result = api.select_payment_method(url, method)
                if result:
                    print(f"{Fore.GREEN}Payment Processed Successfully!")
                    print(json.dumps(result, indent=2))
                    # Try to extract QR or Deep Link
                    try:
                        data = result.get('data', {})
                        
                        # Handle QRIS
                        if method == 'qris' and 'qr_string' in data:
                            qr_string = data['qr_string']
                            print(f"{Fore.CYAN}QR String: {qr_string}")
                            
                            # Generate and display QR Code in terminal
                            print(f"\n{Fore.WHITE}Generating QR Code...")
                            qr = qrcode.QRCode()
                            qr.add_data(qr_string)
                            qr.make()
                            qr.print_ascii(invert=True)
                            
                        # Check midtrans_details first
                        elif 'midtrans_details' in data:
                            mt = data['midtrans_details']
                            if 'actions' in mt:
                                for action in mt['actions']:
                                    if action['name'] == 'generate-qr-code':
                                        print(f"{Fore.CYAN}QR Code URL: {action['url']}")
                                    elif action['name'] == 'deeplink-redirect':
                                        print(f"{Fore.CYAN}Deep Link: {action['url']}")
                        
                        # Legacy fallback
                        elif method == 'gopay' and 'actions' in data:
                             for action in data['actions']:
                                 if action['name'] == 'generate-qr-code':
                                     print(f"{Fore.CYAN}QR Code URL: {action['url']}")
                                 elif action['name'] == 'deeplink-redirect':
                                     print(f"{Fore.CYAN}Deep Link: {action['url']}")
                    except:
                        pass
                else:
                     print(f"{Fore.RED}Failed to process payment.")
            input("Press Enter to continue...")

        elif choice == "5":
            auth.sniff_api_traffic()
            input("Press Enter to continue...")
            
        elif choice == "6":
            if os.path.exists("cookies.pkl"):
                os.remove("cookies.pkl")
                # Clear session cookies in memory too
                auth.session.cookies.clear()
                print(f"{Fore.GREEN}Cookies cleared. Logged out.")
            else:
                print(f"{Fore.YELLOW}No cookies found.")
            input("Press Enter to continue...")
            
        elif choice == "7":
            return

def run_telegram_bot():
    print(f"\n{Fore.CYAN}Starting Telegram Bot...")
    print(f"{Fore.YELLOW}Make sure you have set TELEGRAM_BOT_TOKEN in .env file.")
    
    # Start monitoring thread
    auth = AuthManager()
    tm = TransactionManager(auth)
    start_monitoring(tm)
    
    bot = SocialBuzzBot()
    try:
        bot.run()
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Bot stopped by user.")
    except Exception as e:
        print(f"{Fore.RED}Bot crashed or failed to start: {e}")
    finally:
        stop_monitoring()

def run_interactive_menu():
    while True:
        print(f"{Fore.GREEN}{Style.BRIGHT}SOCIALBUZZ BOT - MAIN MENU")
        print("-" * 50)
        print("1. Run CLI Tool (Interactive)")
        print("2. Run Telegram Bot (Server Mode)")
        print("3. Debug & Settings")
        print("4. Exit")
        print("-" * 50)

        choice = input(f"{Fore.YELLOW}Enter your choice (1-4): ")

        if choice == "1":
            run_cli()
        elif choice == "2":
            run_telegram_bot()
            input("Press Enter to return...")
        elif choice == "3":
            debug_settings_menu()
        elif choice == "4":
            print("Goodbye!")
            stop_monitoring()
            sys.exit(0)
        else:
            print(f"{Fore.RED}Invalid choice. Please try again.")

def main():
    # Check for arguments to run interactive mode
    if len(sys.argv) > 1 and sys.argv[1] in ['--menu', '-m', 'interactive']:
        run_interactive_menu()
    else:
        run_telegram_bot()

def debug_settings_menu():
    """Menu for debug settings and tools."""
    while True:
        clear_screen()
        print(f"{Fore.MAGENTA}{Style.BRIGHT}DEBUG & SETTINGS")
        print("-" * 50)
        
        # Check current debug status
        # Since APIManager is instantiated inside classes, we can't check a global instance easily here
        # But we can check a config file or just offer to run the tool
        
        print("1. Open Browser for API Monitoring (Sniffing Mode)")
        print("2. Back to Main Menu")
        print("-" * 50)
        print(f"{Fore.WHITE}Note: API Logging is enabled by default in 'api_debug.log'.")
        
        choice = input(f"{Fore.YELLOW}Enter your choice (1-2): ")
        
        if choice == "1":
            auth = AuthManager()
            try:
                auth.sniff_api_traffic()
            except Exception as e:
                print(f"{Fore.RED}Error: {e}")
            input("\nPress Enter to return...")
        elif choice == "2":
            break
        else:
            print(f"{Fore.RED}Invalid choice.")
            time.sleep(1)

if __name__ == "__main__":
    main()
