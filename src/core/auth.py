import requests
import pickle
import os
import time
import json
from colorama import init, Fore, Style
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from config.settings import Config

# Initialize colorama
init(autoreset=True)

COOKIES_FILE = "cookies.pkl"
API_LOGS_FILE = "api_logs.json"

class AuthManager:
    def __init__(self):
        self.session = requests.Session()
        # Use a standard browser User-Agent to avoid detection
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        })
        self.load_cookies()

    def login_with_browser(self):
        """
        Launches a visible browser (Undetected Chromedriver) for the user to log in manually.
        After login (detected by URL change), cookies are saved.
        """
        print(f"{Fore.YELLOW}Launching stealth browser... Please login in the opened window.")
        
        # Setup Undetected Chromedriver
        # Note: uc.Chrome() automatically downloads and patches the driver
        options = uc.ChromeOptions()
        # Add arguments to make it look more like a real user
        options.add_argument("--no-first-run")
        options.add_argument("--no-service-autorun")
        options.add_argument("--password-store=basic")
        
        driver = None
        try:
            # use_subprocess=True is recommended for better stability and hiding console windows
            # version_main=144 ensures it uses the driver compatible with Chrome 144
            driver = uc.Chrome(options=options, use_subprocess=True, version_main=144)
            
            print(f"{Fore.CYAN}Navigating to login page...")
            driver.get("https://sociabuzz.com/pro/login")
            
            print(f"{Fore.YELLOW}Waiting for login to complete (detecting dashboard)...")
            
            # Wait loop until URL contains 'dashboard'
            # Timeout after 5 minutes (300 seconds) to give ample time for captchas
            max_wait = 300
            start_time = time.time()
            
            while True:
                try:
                    current_url = driver.current_url
                    # Debug print to help user understand what is happening
                    print(f"{Fore.CYAN}Checking URL: {current_url}", end='\r')
                    
                    # Indikator sukses: Ada di dashboard, halaman link saya, atau halaman pro utama, dan BUKAN di login
                    success_keywords = ["dashboard", "/pro", "/client", "mylink"]
                    if any(keyword in current_url for keyword in success_keywords) and "login" not in current_url and "register" not in current_url:
                        print(f"\n{Fore.GREEN}Login detected! URL: {current_url}")
                        break
                except:
                    # Driver might be closed or disconnected
                    pass
                
                if time.time() - start_time > max_wait:
                    raise Exception("Login timed out")
                
                time.sleep(2)
            
            # Get cookies from Selenium
            selenium_cookies = driver.get_cookies()
            
            # Update requests session cookies
            self._update_session_cookies(selenium_cookies)
            
            # Save to file
            self.save_cookies()
            
        except Exception as e:
            print(f"{Fore.RED}Login failed or timed out: {e}")
            print(f"{Fore.RED}Make sure you have Chrome installed.")
        finally:
            if driver:
                print(f"{Fore.CYAN}Closing browser...")
                driver.quit()

    def login_headless(self):
        """
        Attempts to login automatically using credentials from Config.
        Runs in headless mode suitable for servers (Render).
        """
        if not Config.SOCIABUZZ_EMAIL or not Config.SOCIABUZZ_PASSWORD:
            print(f"{Fore.RED}Auto-login failed: Missing SOCIABUZZ_EMAIL or SOCIABUZZ_PASSWORD in .env")
            return False

        print(f"{Fore.YELLOW}Attempting auto-login (headless)...")
        
        options = uc.ChromeOptions()
        options.add_argument("--headless=new") # Modern headless mode
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--no-first-run")
        options.add_argument("--no-service-autorun")
        options.add_argument("--password-store=basic")
        
        driver = None
        try:
            # version_main=144 ensures it uses the driver compatible with Chrome 144
            driver = uc.Chrome(options=options, use_subprocess=True, version_main=144)
            
            print(f"{Fore.CYAN}Navigating to login page...")
            driver.get("https://sociabuzz.com/pro/login")
            
            # Wait for email field
            wait = WebDriverWait(driver, 20)
            email_field = wait.until(EC.presence_of_element_located((By.NAME, "email")))
            
            print(f"{Fore.CYAN}Entering credentials...")
            email_field.clear()
            email_field.send_keys(Config.SOCIABUZZ_EMAIL)
            
            password_field = driver.find_element(By.NAME, "password")
            password_field.clear()
            password_field.send_keys(Config.SOCIABUZZ_PASSWORD)
            
            # Click login button
            # Usually it's a button with type="submit" or specific class
            try:
                submit_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
                submit_btn.click()
            except:
                # Fallback: press enter on password field
                password_field.submit()
            
            print(f"{Fore.YELLOW}Waiting for redirection...")
            
            # Wait for dashboard or successful login indicator
            # We wait up to 60 seconds
            max_wait = 60
            start_time = time.time()
            success = False
            
            while time.time() - start_time < max_wait:
                current_url = driver.current_url
                if any(k in current_url for k in ["dashboard", "/pro", "/client", "mylink"]) and "login" not in current_url:
                    success = True
                    break
                
                # Check for error messages
                try:
                    error_el = driver.find_element(By.CLASS_NAME, "alert-danger")
                    if error_el:
                        print(f"{Fore.RED}Login Error: {error_el.text}")
                        break
                except:
                    pass
                    
                time.sleep(1)
            
            if success:
                print(f"{Fore.GREEN}Auto-login successful!")
                # Get cookies from Selenium
                selenium_cookies = driver.get_cookies()
                # Update requests session cookies
                self._update_session_cookies(selenium_cookies)
                # Save to file
                self.save_cookies()
                return True
            else:
                print(f"{Fore.RED}Auto-login timed out. URL: {driver.current_url}")
                return False

        except Exception as e:
            print(f"{Fore.RED}Auto-login failed: {e}")
            return False
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass

    def sniff_api_traffic(self):
        """
        Launches browser with performance logging enabled to capture API traffic.
        """
        print(f"{Fore.YELLOW}Launching browser in SNIFFING MODE...")
        print(f"{Fore.YELLOW}Browse the website normally. API requests will be recorded in background.")
        print(f"{Fore.YELLOW}Press CTRL+C in this terminal to stop capturing and save logs.")
        
        options = uc.ChromeOptions()
        options.add_argument("--no-first-run")
        options.add_argument("--password-store=basic")
        
        # Enable Performance Logging
        options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
        
        driver = None
        captured_requests = []
        
        try:
            # version_main=144 ensures it uses the driver compatible with Chrome 144
            driver = uc.Chrome(options=options, use_subprocess=True, version_main=144)
            
            # Load cookies if available to auto-login
            if os.path.exists(COOKIES_FILE):
                driver.get("https://sociabuzz.com") # Need to navigate to domain first
                for cookie in self.session.cookies:
                    try:
                        driver.add_cookie({
                            'name': cookie.name,
                            'value': cookie.value,
                            'domain': cookie.domain if cookie.domain else '.sociabuzz.com',
                            'path': cookie.path if cookie.path else '/'
                        })
                    except:
                        pass
                print(f"{Fore.GREEN}Cookies injected. Navigating to dashboard...")
                driver.get("https://sociabuzz.com/pro/dashboard")
            else:
                print(f"{Fore.YELLOW}No cookies found. Please login manually in the browser.")
                driver.get("https://sociabuzz.com/pro/login")

            while True:
                # Retrieve performance logs
                logs = driver.get_log('performance')
                
                for entry in logs:
                    try:
                        message = json.loads(entry['message'])['message']
                        
                        # Filter for Network.requestWillBeSent (Request)
                        if message['method'] == 'Network.requestWillBeSent':
                            request = message['params']['request']
                            url = request['url']
                            method = request['method']
                            
                            # Capture ALL POST requests (forms, APIs, etc.) OR relevant API GET requests
                            is_post = method == 'POST'
                            is_api = 'api' in url or 'json' in url or request.get('type') in ['XHR', 'Fetch']
                            
                            if is_post or is_api:
                                if not any(ext in url for ext in ['.js', '.css', '.png', '.jpg', '.svg', '.woff']):
                                    log_entry = {
                                        "type": "REQUEST",
                                        "timestamp": message['params']['timestamp'],
                                        "url": url,
                                        "method": method,
                                        "headers": request['headers'],
                                        "postData": request.get('postData', None)
                                    }
                                    captured_requests.append(log_entry)
                                    print(f"{Fore.CYAN}[REQ] {method} {url[:60]}...")
                                    
                    except Exception as e:
                        pass
                
                time.sleep(0.5)

        except KeyboardInterrupt:
            print(f"\n{Fore.GREEN}Stopping capture...")
        except Exception as e:
            print(f"{Fore.RED}Error during sniffing: {e}")
        finally:
            if captured_requests:
                print(f"{Fore.YELLOW}Saving {len(captured_requests)} logs to {API_LOGS_FILE}...")
                with open(API_LOGS_FILE, "w", encoding='utf-8') as f:
                    json.dump(captured_requests, f, indent=2)
                print(f"{Fore.GREEN}Logs saved successfully!")
            
            if driver:
                print(f"{Fore.CYAN}Closing browser...")
                driver.quit()

    def _update_session_cookies(self, selenium_cookies):
        """Converts Selenium cookies to Requests cookies."""
        for cookie in selenium_cookies:
            self.session.cookies.set(
                cookie['name'],
                cookie['value'],
                domain=cookie['domain'],
                path=cookie['path']
            )

    def save_cookies(self):
        with open(COOKIES_FILE, "wb") as f:
            pickle.dump(self.session.cookies, f)
        print(f"{Fore.BLUE}Cookies saved.")

    def load_cookies(self):
        if os.path.exists(COOKIES_FILE):
            try:
                with open(COOKIES_FILE, "rb") as f:
                    self.session.cookies.update(pickle.load(f))
                # print(f"{Fore.BLUE}Cookies loaded.")
            except Exception as e:
                print(f"{Fore.RED}Failed to load cookies: {e}")

    def check_session(self):
        """Checks if the current session is valid by hitting a protected endpoint."""
        # User confirmed dashboard URL: https://sociabuzz.com/proaccount/profile
        # Also keeping /mylink as a fallback if needed, but prioritizing the user's URL
        dashboard_url = "https://sociabuzz.com/proaccount/profile"
        try:
            r = self.session.get(dashboard_url, allow_redirects=False)
            
            # If we are redirected to login, session is invalid
            if r.status_code in [301, 302] and "login" in r.headers.get("Location", ""):
                return False
                
            # If we get a 200 OK, it's valid.
            if r.status_code == 200:
                if "login" in r.url:
                    return False
                return True
                
            return False
        except:
            return False

    def get_session(self):
        return self.session
