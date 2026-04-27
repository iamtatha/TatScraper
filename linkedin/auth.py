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
    NOTE: Uses port 9223 so it doesn't conflict with the Facebook scraper on 9222.
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

    if not restart and is_port_open(9223):
        try:
            attach_options = Options()
            attach_options.add_experimental_option("debuggerAddress", "127.0.0.1:9223")
            driver = webdriver.Chrome(options=attach_options)
            print("Successfully connected to an existing browser session.")
            return driver, True
        except Exception:
            pass

    print("Starting a new browser session...")
    chrome_options = Options()
    chrome_options.add_argument(f"user-data-dir={profile_dir}")
    chrome_options.add_argument("--remote-debugging-port=9223")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)

    if not auto_close:
        chrome_options.add_experimental_option("detach", True)

    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")

    driver = webdriver.Chrome(options=chrome_options)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": """
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            })
        """
    })
    driver.maximize_window()
    return driver, False


def login_to_linkedin(driver, email, password, mfa_sleep_seconds=0):
    """Navigates to LinkedIn and logs in using the provided credentials, unless already logged in."""
    print("Navigating to LinkedIn...")
    driver.get("https://www.linkedin.com/")
    time.sleep(get_human_delay(3, 5))

    # Check login state by URL — the most reliable signal.
    # If we are logged in, LinkedIn redirects to /feed/. 
    # If not logged in, we land on the homepage at "/" or get sent to "/login" or "/authwall".
    current_url = driver.current_url
    print(f"Current URL after navigation: {current_url}")

    is_logged_in = (
        "/feed" in current_url or
        "/mynetwork" in current_url or
        "/messaging" in current_url or
        "/notifications" in current_url
    )
    
    is_login_required = (
        "/login" in current_url or
        "/authwall" in current_url or
        "/checkpoint" in current_url or
        "linkedin.com/" == current_url.replace("https://www.", "").replace("https://", "") or
        current_url.rstrip("/").endswith("linkedin.com")
    )

    if is_logged_in:
        print("Already logged in. Skipping login sequence.")
        return

    if not is_login_required:
        # Ambiguous URL - look for login form as confirmation
        try:
            wait = WebDriverWait(driver, 5)
            wait.until(EC.presence_of_element_located((By.ID, "session_key")))
            is_login_required = True
        except Exception:
            print(f"Unrecognized page state at: {current_url}. Assuming logged in.")
            return

    if is_login_required:
        # Navigate explicitly to login page if not already there
        if "/login" not in current_url:
            driver.get("https://www.linkedin.com/login")
            time.sleep(get_human_delay(2, 4))

        print("Login required. Entering credentials...")
        try:
            wait = WebDriverWait(driver, 10)
            email_field = wait.until(EC.presence_of_element_located((By.ID, "username")))
        except Exception:
            try:
                email_field = driver.find_element(By.ID, "session_key")
            except Exception as e:
                print(f"Could not find login email field: {e}")
                return

        human_typing(email_field, email)
        time.sleep(get_human_delay(0.5, 1.5))

        print("Entering password...")
        try:
            password_field = driver.find_element(By.ID, "password")
        except Exception:
            password_field = driver.find_element(By.ID, "session_password")
        human_typing(password_field, password)
        time.sleep(get_human_delay(0.5, 1.5))

        print("Clicking login...")
        password_field.send_keys(Keys.RETURN)

        if mfa_sleep_seconds > 0:
            print(f"Waiting {mfa_sleep_seconds} seconds for potential 2FA verification...")
            time.sleep(mfa_sleep_seconds)
        else:
            time.sleep(get_human_delay(5, 8))

    print("Login sequence completed.")
