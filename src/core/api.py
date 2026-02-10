import json
import re
import logging
import datetime
from colorama import init, Fore, Style

# Initialize colorama
init(autoreset=True)

class APIManager:
    def __init__(self, session):
        self.session = session
        self.base_url = "https://sociabuzz.com"
        self.debug_mode = False # Default to False (non-active)
        self._setup_logging()

    def set_debug_mode(self, enabled: bool):
        self.debug_mode = enabled
        if enabled:
            self.logger.setLevel(logging.DEBUG)
        else:
            self.logger.setLevel(logging.CRITICAL) # Silence logs effectively

    def _setup_logging(self):
        self.logger = logging.getLogger("APIDebugger")
        self.logger.setLevel(logging.DEBUG)
        
        # File handler
        fh = logging.FileHandler("api_debug.log", encoding='utf-8')
        fh.setLevel(logging.DEBUG)
        
        # Formatter
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        fh.setFormatter(formatter)
        
        # Add handler if not exists
        if not self.logger.handlers:
            self.logger.addHandler(fh)

    def _log_request(self, method, url, **kwargs):
        if not self.debug_mode: return
        self.logger.debug(f"REQUEST {method} {url}")
        if 'params' in kwargs:
            self.logger.debug(f"Params: {kwargs['params']}")
        if 'json' in kwargs:
            self.logger.debug(f"JSON: {kwargs['json']}")
        if 'data' in kwargs:
            self.logger.debug(f"Data: {kwargs['data']}")

    def _log_response(self, response):
        if not self.debug_mode: return
        try:
            self.logger.debug(f"RESPONSE {response.status_code} {response.url}")
            self.logger.debug(f"Content (prefix): {response.text[:500]}")
        except:
            self.logger.debug("RESPONSE (Error reading content)")

    def _get_csrf_token(self, url):
        """Fetches the page and extracts the sb_token_csrf."""
        try:
            print(f"{Fore.CYAN}Connecting to {url}...")
            self._log_request("GET", url)
            response = self.session.get(url, timeout=15)
            self._log_response(response)
            
            if response.status_code == 404:
                print(f"{Fore.RED}Error: Page not found (404). Check the username/URL.")
                return None
            
            if response.status_code != 200:
                print(f"{Fore.RED}Error: HTTP {response.status_code}")
                return None

            # Pattern 1: <input type="hidden" name="sb_token_csrf" value="...">
            match = re.search(r'name="sb_token_csrf" value="([^"]+)"', response.text)
            if match:
                return match.group(1)
            
            # Pattern 2: var sb_token_csrf = '...';
            match = re.search(r"var sb_token_csrf = ['\"]([^'\"]+)['\"]", response.text)
            if match:
                return match.group(1)
            
            # Pattern 3: csrf_token meta tag (common in Laravel/modern apps)
            match = re.search(r'<meta name="csrf-token" content="([^"]+)">', response.text)
            if match:
                return match.group(1)
            
            # If not found on main page, try the donate/queue endpoint
            # Extract username from url (e.g. https://sociabuzz.com/bimaikhsan/tribe -> bimaikhsan)
            username_match = re.search(r'sociabuzz\.com/([^/]+)/tribe', url)
            if username_match:
                username = username_match.group(1)
                queue_url = f"{self.base_url}/{username}/donate/queue?type=donate&currency=IDR"
                print(f"{Fore.CYAN}Token not found on main page. Checking {queue_url}...")
                
                queue_response = self.session.get(queue_url, timeout=15)
                if queue_response.status_code == 200:
                    match = re.search(r'name="sb_token_csrf" value="([^"]+)"', queue_response.text)
                    if match:
                        print(f"{Fore.GREEN}Found CSRF token in queue response.")
                        return match.group(1)
                
            # Check for common error texts if token is missing
            if "Page Not Found" in response.text or "Halaman Tidak Ditemukan" in response.text:
                print(f"{Fore.RED}Error: The page seems to be missing (Soft 404).")
                print(f"{Fore.RED}Check if the username is correct and the user has Tribe enabled.")
            elif response.url != url:
                print(f"{Fore.YELLOW}Warning: Redirected to {response.url}")
                print(f"{Fore.YELLOW}The specific page might not exist.")

            return None
        except Exception as e:
            print(f"{Fore.RED}Error fetching CSRF token: {e}")
            return None

    def get_all_data(self):
        """
        Attempts to retrieve dashboard data or transaction history.
        """
        # Placeholder endpoint - needs verification
        api_url = f"{self.base_url}/api/transactions" 
        
        print(f"{Fore.YELLOW}Fetching data from {api_url} (Simulation)...")
        
        # In a real app, you would make the request here:
        # response = self.session.get(api_url)
        # data = response.json()
        
        # simulating data for the dashboard
        data = [
            {"id": "TX1001", "amount": 50000, "donor": "User A", "message": "Semangat!", "date": "2023-10-27"},
            {"id": "TX1002", "amount": 100000, "donor": "User B", "message": "Mantap bang", "date": "2023-10-28"},
        ]
        
        return data

    def create_support_payment(self, username, amount, message, email, fullname):
        """Creates a Tribe/Support payment link."""
        print(f"[DEBUG_FLOW] [API] create_support_payment called for {username}, amount={amount}")
        # 1. Get CSRF Token from the support page
        support_page_url = f"{self.base_url}/{username}/tribe"
        print(f"{Fore.CYAN}Fetching CSRF token from {support_page_url}...")
        csrf_token = self._get_csrf_token(support_page_url)
        
        if not csrf_token:
            print(f"{Fore.RED}Failed to get CSRF token.")
            return None

        # 2. Create the payment
        endpoint = f"{self.base_url}/{username}/donate/get-form-queue"
        
        # Format amount with comma separator (e.g. 10000 -> 10,000) based on logs
        formatted_amount = f"{amount:,}"
        
        payload = {
            "sb_token_csrf": csrf_token,
            "currency": "IDR",
            "amount": formatted_amount,
            "qty": "1",
            "support_duration": "30",
            "note": message,
            "fullname": fullname,
            "email": email,
            "is_agree": "1",
            "years18": "1",
            "is_vote": "0", "is_voice": "0", "is_mediashare": "0", 
            "is_gif": "0", "is_sound": "0", "vote_id": "", 
            "ms_maxtime": "", "start_from": "0", "ms_starthour": "0",
            "ms_startminute": "0", "ms_startsecond": "0", "spin_check": "0",
            "prev_url": support_page_url, "hide_email": "0", "is_tiktok": "0",
            "tiktok_duration": "0", "is_instagram": "0", "instagram_duration": "0",
            "wishlist_id": "", "quickpay": "0"
        }
        
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Referer": support_page_url
        }

        print(f"{Fore.YELLOW}Creating support payment for Rp{amount}...")
        try:
            self._log_request("POST", endpoint, data=payload, headers=headers)
            response = self.session.post(endpoint, data=payload, headers=headers)
            self._log_response(response)
            
            # Typically returns JSON with redirect URL
            try:
                data = response.json()
                print(f"[DEBUG_FLOW] [API] create_support_payment success. Data: {data}")
                return data
            except:
                print(f"{Fore.RED}Failed to parse JSON response. Response text:")
                print(response.text[:200])
                return None
                
        except Exception as e:
            print(f"{Fore.RED}Error creating payment: {e}")
            return None

    def select_payment_method(self, payment_url, method="gopay"):
        """Selects the payment method (gopay/qris) for a pending payment."""
        print(f"[DEBUG_FLOW] [API] select_payment_method called. URL={payment_url}, Method={method}")
        # 1. Get CSRF Token from the payment page
        print(f"{Fore.CYAN}Fetching CSRF token from {payment_url}...")
        csrf_token = self._get_csrf_token(payment_url)
        
        if not csrf_token:
             print(f"{Fore.RED}Failed to get CSRF token.")
             # Dump partial content for debug
             print(f"Debug Content: {self.session.get(payment_url).text[:500]}") 
             return {"error": "Failed to retrieve CSRF token from payment page."}
             
        # Extract order_id from URL
        order_id = payment_url.split('/')[-1]
        
        # 2. Select Payment Method
        endpoint = f"{self.base_url}/payment/send/create"
        
        payment_config = {
            # E-Wallets
            "gopay": {"type": "ewallet_id", "source": "midtrans"},
            "qris": {"type": "qris", "source": "xendit"},
            # Bank Transfers
        "mandiri": {"type": "bank_transfer", "source": "xendit"},
            "bri": {"type": "bank_transfer", "source": "xendit"},
            "bni": {"type": "bank_transfer", "source": "xendit"},
            "bsi": {"type": "bank_transfer", "source": "xendit"},
            "cimb": {"type": "bank_transfer", "source": "xendit"},
            "permata": {"type": "bank_transfer", "source": "xendit"},
            "bjb": {"type": "bank_transfer", "source": "xendit"},
            "bnc": {"type": "bank_transfer", "source": "xendit"},
            "bca": {"type": "bank_transfer", "source": "midtrans"},
            "maybank": {"type": "bank_transfer", "source": "faspay"},
            "sinarmas": {"type": "bank_transfer", "source": "faspay"}
        }
        
        config = payment_config.get(method, payment_config["gopay"])
        
        # Use explicit api_code if defined, otherwise use the method key
        api_method = config.get("api_code", method)

        payload = {
            "sb_token_csrf": csrf_token,
            "order_id": order_id,
            "final_currency": "IDR",
            "currency_def": "IDR",
            "payment_method": api_method,
            "type_payment": config["type"],
            "source_payment": config["source"],
            "country": "ID",
            "country_pay": "Indonesia"
        }
        
        headers = {
            "Content-Type": "application/json",
            "Referer": payment_url
        }
        
        print(f"{Fore.YELLOW}Selecting payment method: {method}...")
        try:
            self._log_request("POST", endpoint, json=payload, headers=headers)
            response = self.session.post(endpoint, json=payload, headers=headers)
            self._log_response(response)
            
            # Handle potential redirects (e.g. DANA redirects to m.dana.id)
            # or non-JSON responses (HTML pages)
            try:
                result = response.json()
            except ValueError:
                # JSONDecodeError usually
                print(f"{Fore.YELLOW}Response is not JSON. URL: {response.url}")
                # If the URL is different from endpoint, it might be a redirect
                if response.url != endpoint:
                     return {
                         "data": {
                             "redirect_url": response.url,
                             # No token available in this case, but we have the URL
                         }
                     }
                # If it's just HTML error page
                return {"error": "Invalid response from server (not JSON)"}
            
            # Check if it's a E-Wallet/Midtrans response that needs further processing
            if method in ['gopay', 'ovo', 'dana', 'linkaja', 'shopeepay'] and result and 'data' in result and 'token' in result['data']:
                midtrans_token = result['data']['token']
                print(f"[DEBUG_FLOW] [API] Midtrans token obtained: {midtrans_token}")
                
                # Only fetch deep link for GoPay/ShopeePay where we know it helps to get QR/App link
                # For others (OVO, DANA), the standard redirect URL is usually sufficient or requires web interaction
                # This prevents unnecessary 404 errors for methods that don't support this endpoint
                if method in ['gopay', 'shopeepay']:
                    if self.debug_mode:
                        print(f"{Fore.CYAN}Midtrans token found for {method}: {midtrans_token}. Fetching deep link...")
                    
                    midtrans_data = self._get_midtrans_deep_link(midtrans_token, method)
                    if midtrans_data:
                        # Merge midtrans data into result
                        result['data']['midtrans_details'] = midtrans_data
            
            # Check if it's a QRIS response (usually Xendit or other provider via SociaBuzz)
            elif method == 'qris' and result:
                data_obj = result.get('data', result)
                
                # Try to find QR string in various common fields
                qr_candidates = [
                    data_obj.get('qr_string'),
                    data_obj.get('qr_code'),
                    data_obj.get('payment_code'), # Sometimes reused
                    data_obj.get('string_qr')
                ]
                
                found_qr = next((x for x in qr_candidates if x), None)
                
                if found_qr:
                     # Standardize to 'qr_string' for the bot
                     if 'data' in result:
                         result['data']['qr_string'] = found_qr
                     else:
                         result['qr_string'] = found_qr
                
                print(f"[DEBUG_FLOW] [API] QRIS Extraction. Found: {found_qr[:20] if found_qr else 'None'}")
            
            print(f"[DEBUG_FLOW] [API] Payment method selection result: {str(result)[:100]}...")
            return result
        except Exception as e:
            print(f"{Fore.RED}Error selecting payment method: {e}")
            return {"error": str(e)}

    def _get_midtrans_deep_link(self, token, method="gopay"):
        """Fetches the actual GoPay deep link/QR from Midtrans Snap API."""
        try:
            # Endpoint to "charge" or get payment details
            api_url = f"https://app.midtrans.com/snap/v1/transactions/{token}/pay"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'Origin': 'https://app.midtrans.com',
                'Referer': f"https://app.midtrans.com/snap/v4/redirection/{token}"
            }
            
            # Map method to Midtrans payment_type if needed
            payment_type = method
            if method == "dana":
                payment_type = "dana" # Usually 'dana' or 'gopay' (some aggregators use gopay path?)
            elif method == "shopeepay":
                payment_type = "shopeepay"
            
            payload = {
                "payment_type": payment_type
            }
            
            # We use a fresh requests call here to avoid session cookie conflicts if any,
            # but using self.session is also fine if headers are set correctly.
            # Using self.session might carry over SociaBuzz cookies which is unnecessary but harmless.
            response = self.session.post(api_url, json=payload, headers=headers)
            
            if response.status_code == 200:
                return response.json()
            else:
                # 404 is common if the payment type is not compatible or token is just for redirection
                # We suppress the error log to avoid user confusion, as we have fallback
                if response.status_code == 404:
                     if self.debug_mode:
                        print(f"{Fore.YELLOW}Note: Direct deep link fetch failed (404). Using standard redirect URL.")
                else:
                     print(f"{Fore.RED}Failed to fetch Midtrans deep link. Status: {response.status_code}")
                return None
        except Exception as e:
            print(f"{Fore.RED}Error fetching Midtrans deep link: {e}")
            return None

    def _get_bca_va_from_snap(self, token):
        """Fetches the BCA VA number from Midtrans Snap API."""
        try:
            # Endpoint to get payment details for BCA
            # Based on common Midtrans Snap behavior, we can try to 'charge' or 'pay' with bank_transfer
            api_url = f"https://app.midtrans.com/snap/v1/transactions/{token}/pay"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'Origin': 'https://app.midtrans.com',
                'Referer': f"https://app.midtrans.com/snap/v4/redirection/{token}"
            }
            
            payload = {
                "payment_type": "bca_va" # Specific for BCA Virtual Account
            }
            
            response = self.session.post(api_url, json=payload, headers=headers)
            
            if response.status_code == 200:
                result = response.json()
                # Expected structure: {"status_code": "201", "va_numbers": [{"bank": "bca", "va_number": "12345"}], ...}
                if 'va_numbers' in result and len(result['va_numbers']) > 0:
                    return result['va_numbers'][0].get('va_number')
                    
            return None
        except Exception as e:
            print(f"{Fore.RED}Error fetching BCA VA: {e}")
            return None

    def withdraw_funds(self, method_code: str, amount: int) -> dict:
        """
        Withdraw funds to the specified method (e.g., 'dana', 'gopay', 'bank').
        Amount should be an integer (e.g., 10000).
        """
        try:
            # 1. Get CSRF Token from Transaction Page
            trans_url = f"{self.base_url}/proaccount/transaction"
            csrf_token = self._get_csrf_token(trans_url)
            
            if not csrf_token:
                return {"status": "error", "message": "Gagal mengambil token CSRF. Silakan coba lagi."}
            
            # 2. Format Amount (e.g. 10000 -> 10.000)
            # The log shows "9.500" for 9500. So we need dot as thousand separator.
            formatted_amount = f"{amount:,}".replace(",", ".")
            
            # 3. Prepare POST Data
            payload = {
                "sb_token_csrf": csrf_token,
                "amount": formatted_amount
            }
            
            # 4. Send Request
            target_url = f"{self.base_url}/proaccount/transaction/sendwithdrawalauto/{method_code.lower()}"
            print(f"{Fore.CYAN}Sending withdrawal request to {target_url}...")
            self._log_request("POST", target_url, data=payload)
            
            response = self.session.post(target_url, data=payload, timeout=30)
            self._log_response(response)
            
            # 5. Parse Response
            # We assume it returns JSON or we check status code
            try:
                # Some endpoints return JSON, some might redirect or return HTML
                # Log entry doesn't show response, but usually these APIs return JSON
                res_json = response.json()
                return res_json
            except:
                # If not JSON, check text for success/error keywords
                if response.status_code == 200:
                    if "berhasil" in response.text.lower() or "success" in response.text.lower():
                        return {"status": "success", "message": "Permintaan pencairan berhasil dikirim."}
                    else:
                        # Fallback: maybe it worked but returned HTML?
                        return {"status": "unknown", "message": "Respon tidak dikenali. Silakan cek saldo Anda.", "raw": response.text[:100]}
                else:
                    return {"status": "error", "message": f"HTTP Error {response.status_code}"}
                    
        except Exception as e:
            print(f"{Fore.RED}Withdrawal Error: {e}")
            return {"status": "error", "message": str(e)}


    def check_payment_status(self, payment_id, method, payment_url):
        """Checks the status of a payment using its token or URL."""
        # Clarify if we are using token or scraping
        check_type = "Token" if payment_id else "Scraping"
        print(f"[DEBUG_FLOW] [API] Checking status... ID={payment_id} ({check_type}), Method={method}")
        
        if self.debug_mode:
            print(f"{Fore.CYAN}Checking status for {method} (ID: {payment_id}, URL: {payment_url})")

        # 1. Try Midtrans/Token based check for E-Wallets
        # We try this first for e-wallets as it provides more detailed status
        
        if method in ["gopay", "ovo", "dana", "linkaja", "shopeepay"] and payment_id:
            # Attempt Midtrans check
            data = self._get_midtrans_deep_link(payment_id)
            if data and data.get("transaction_status"):
                if self.debug_mode:
                    print(f"{Fore.GREEN}Midtrans check success: {data.get('transaction_status')}")
                return {
                    "status": data.get("transaction_status"),
                    "status_code": data.get("status_code"),
                    "message": data.get("status_message")
                }
            elif self.debug_mode:
                print(f"{Fore.YELLOW}Midtrans check returned no status.")
        
        # 2. Fallback for ALL methods (including E-Wallets if above failed):
        # Use Page Scraping if payment_url is available
        if payment_url:
            if self.debug_mode:
                print(f"{Fore.CYAN}Falling back to scraping: {payment_url}")
            try:
                response = self.session.get(payment_url, timeout=10)
                if response.status_code == 200:
                    text_content = response.text.lower()
                    
                    # --- STATUS DETECTION LOGIC ---
                    # Priority: Strong Success > Pending > Weak Success
                    
                    # A. Strong Success Keywords (Unambiguous)
                    # User requested ONLY "terima kasih untuk dukungannya" and its variations
                    strong_success_keywords = [
                        "terima kasih untuk dukungannya",
                        "terimakasih atas dukungannya"
                    ]
                    
                    match_strong = next((x for x in strong_success_keywords if x in text_content), None)
                    if match_strong:
                        # DEBUG: Show context to debug false positives
                        idx = text_content.find(match_strong)
                        start = max(0, idx - 50)
                        end = min(len(text_content), idx + len(match_strong) + 50)
                        context_snippet = text_content[start:end].replace('\n', ' ').strip()
                        print(f"[DEBUG_FLOW] Found '{match_strong}' in context: ...{context_snippet}...")

                        # False Positive Check: Ensure it's not part of an instruction
                        # Common false positives: "jika pembayaran berhasil", "pastikan pembayaran berhasil", "menunggu pembayaran berhasil"
                        preceding_text = text_content[max(0, idx - 20):idx]
                        false_positive_triggers = ["jika ", "if ", "pastikan ", "ensure ", "menunggu ", "waiting ", "setelah ", "after "]
                        
                        is_false_positive = any(trigger in preceding_text for trigger in false_positive_triggers)
                        
                        if is_false_positive:
                            print(f"[DEBUG_FLOW] Ignored '{match_strong}' (Detected as False Positive due to preceding text)")
                        else:
                            print(f"[DEBUG_FLOW] Status: SUCCESS (Strong Match: '{match_strong}')")
                            return {
                                "status": "settlement",
                                "status_code": "200",
                                "message": "Payment Successful"
                            }

                    # B. Pending Keywords
                    pending_keywords = [
                        "menunggu pembayaran", "waiting for payment", 
                        "qr_string", "scan qr",
                        "nomor virtual account", "virtual account number", 
                        "cek ponsel anda", "check your phone", 
                        "payment code", "kode pembayaran",
                        "complete payment", "selesaikan pembayaran",
                        "batas waktu", "pay before"
                    ]
                    
                    match_pending = next((x for x in pending_keywords if x in text_content), None)
                    if match_pending:
                         print(f"[DEBUG_FLOW] Status: PENDING (Match: '{match_pending}')")
                         return {
                            "status": "pending",
                            "status_code": "201",
                            "message": "Waiting for payment"
                        }

                    # C. Weak Success Keywords (Ambiguous - only if NOT pending)
                    # "Terima kasih" now moved to Strong, but we keep this block empty or remove it.
                    # Removing to avoid confusion.
                    
                    # D. Default/Unknown
                    return {
                        "status": "pending",
                        "status_code": "201",
                        "message": "Waiting for payment (Unverified)"
                    }
            except Exception as e:
                if self.debug_mode:
                    print(f"{Fore.RED}Scraping error: {e}")
                pass
                
        return None

    def show_transactions(self):
        data = self.get_all_data()
        
        print(f"\n{Fore.WHITE}{Style.BRIGHT}Transaction History{Style.RESET_ALL}")
        print("-" * 80)
        # Header
        print(f"{Fore.CYAN}{'ID':<10} {Fore.MAGENTA}{'Date':<15} {Fore.GREEN}{'Donor':<20} {Fore.YELLOW}{'Amount':>10} {Fore.WHITE} Message")
        print("-" * 80)
        
        for item in data:
            print(f"{Fore.CYAN}{item['id']:<10} {Fore.MAGENTA}{item['date']:<15} {Fore.GREEN}{item['donor']:<20} {Fore.YELLOW}{f'Rp{item['amount']:,}':>10} {Fore.WHITE} {item['message']}")
        print("-" * 80)
