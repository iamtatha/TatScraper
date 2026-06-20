import os
import sys
import time

# Add the root directory to path so we can import the existing facebook modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from facebook.auth import init_browser, login_to_facebook
from facebook.scraper import navigate_to_page, search_facebook, scrape_posts
from dotenv import load_dotenv

load_dotenv()

class FacebookAgentCore:
    def __init__(self):
        self.driver = None
        self.email = os.getenv("FACEBOOK_EMAIL")
        self.password = os.getenv("FACEBOOK_PASSWORD")
        self.is_logged_in = False
    
    def initialize(self):
        """Initializes the browser and logs in if not already done."""
        if not self.email or not self.password:
            raise ValueError("FACEBOOK_EMAIL or FACEBOOK_PASSWORD missing from .env")
        
        if not self.driver:
            self.driver, _ = init_browser(auto_close=False, restart=False)
        
        if not self.is_logged_in:
            login_to_facebook(self.driver, self.email, self.password, mfa_sleep_seconds=5)
            self.is_logged_in = True
            
        return {"status": "success", "message": "Browser initialized and logged in."}

    def close(self):
        """Closes the browser session."""
        if self.driver:
            self.driver.quit()
            self.driver = None
            self.is_logged_in = False
        return {"status": "success", "message": "Browser closed."}

    def scrape_url(self, url: str, max_posts: int = 10, max_scrolls: int = 10):
        """Navigates to a specific URL and scrapes posts."""
        if not self.driver:
            self.initialize()
            
        navigate_to_page(self.driver, url)
        posts = scrape_posts(
            driver=self.driver,
            max_posts=max_posts,
            max_scrolls=max_scrolls,
            max_time_seconds=300
        )
        return {"status": "success", "posts": posts, "count": len(posts)}

    def search_and_scrape(self, query: str, max_posts: int = 10, max_scrolls: int = 10):
        """Searches Facebook for a query and scrapes the resulting posts."""
        if not self.driver:
            self.initialize()
            
        search_facebook(self.driver, query)
        posts = scrape_posts(
            driver=self.driver,
            max_posts=max_posts,
            max_scrolls=max_scrolls,
            max_time_seconds=300
        )
        return {"status": "success", "posts": posts, "count": len(posts)}

    def scrape_home(self, max_posts: int = 10, max_scrolls: int = 10):
        """Scrapes the user's home feed."""
        if not self.driver:
            self.initialize()
            
        return self.scrape_url("https://www.facebook.com/", max_posts, max_scrolls)

    def click_element(self, selector: str = None, text: str = None):
        """
        Clicks an element on the current page either by CSS selector or by matching text.
        Useful for agentic exploration.
        """
        if not self.driver:
            raise Exception("Browser not initialized.")
            
        try:
            if selector:
                # Click via JS using selector
                self.driver.execute_script(f'''
                    let el = document.querySelector("{selector}");
                    if(el) el.click();
                    else throw new Error("Selector not found");
                ''')
                return {"status": "success", "message": f"Clicked element matching selector '{selector}'"}
            elif text:
                # Click via JS matching text content
                self.driver.execute_script(f'''
                    let found = false;
                    document.querySelectorAll('a, button, [role="button"], span, div').forEach(el => {{
                        if (!found && el.textContent.trim().toLowerCase() === "{text.lower()}") {{
                            el.click();
                            found = true;
                        }}
                    }});
                    if(!found) throw new Error("Text not found");
                ''')
                return {"status": "success", "message": f"Clicked element matching text '{text}'"}
            else:
                raise ValueError("Must provide either 'selector' or 'text'")
        except Exception as e:
            return {"status": "error", "message": str(e)}

# Singleton instance
fb_agent = FacebookAgentCore()
