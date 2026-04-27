import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from utils import get_human_delay, human_typing

def init_browser(auto_close=True, restart=False):
    """
    Initializes the browser. Tries to connect to an open browser first.
    If it fails or restart is True, starts a new one using a persistent profile.
    """
    import os
    import socket
    
    profile_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'chrome_profile'))
    
    def is_port_open(port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            try:
                s.connect(("127.0.0.1", port))
                return True
            except Exception:
                return False

    if not restart and is_port_open(9222):
        try:
            attach_options = Options()
            attach_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
            driver = webdriver.Chrome(options=attach_options)
            print("Successfully connected to an existing browser session.")
            return driver, True
        except Exception:
            pass # No existing browser listening, will start a new one
            
    print("Starting a new browser session...")
    chrome_options = Options()
    
    # Store persistent data here so closing the browser doesn't lose login state
    chrome_options.add_argument(f"user-data-dir={profile_dir}")
    chrome_options.add_argument("--remote-debugging-port=9222")
    
    # Disable automation extension to appear less like a bot
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    # Keep browser open if requested
    if not auto_close:
        chrome_options.add_experimental_option("detach", True)
    
    # Common headers to trick basic detection
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")

    driver = webdriver.Chrome(options=chrome_options)
    
    # Hide webdriver flag using CDP
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": """
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            })
        """
    })
    
    driver.maximize_window()
    return driver, False

def login_to_facebook(driver, email, password, mfa_sleep_seconds=0):
    """Navigates to Facebook and logs in using the provided credentials, unless already logged in."""
    print("Navigating to Facebook...")
    driver.get("https://www.facebook.com/")
    time.sleep(get_human_delay(2, 4))
    
    # Check if we are already logged in by looking for the email field
    try:
        wait = WebDriverWait(driver, 5)
        print("Checking if login is required...")
        email_field = wait.until(EC.presence_of_element_located((By.NAME, "email")))
    except Exception:
        print("Login fields not found. Assuming we are already logged in!")
        return # Skip the rest of the login sequence
        
    print("Entering email...")
    human_typing(email_field, email)
    time.sleep(get_human_delay(0.5, 1.5))
    
    print("Entering password...")
    password_field = wait.until(EC.presence_of_element_located((By.NAME, "pass")))
    human_typing(password_field, password)
    time.sleep(get_human_delay(0.5, 1.5))
    
    print("Clicking login...")
    password_field.send_keys(Keys.RETURN)
    
    if mfa_sleep_seconds > 0:
        print(f"Waiting {mfa_sleep_seconds} seconds for potential 2FA verification...")
        time.sleep(mfa_sleep_seconds)
    else:
        # Standard wait
        time.sleep(get_human_delay(5, 8))
        
    print("Login sequence completed.")
