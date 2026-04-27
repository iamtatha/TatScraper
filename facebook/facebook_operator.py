import os
import re
import argparse
import yaml
from dotenv import load_dotenv
from auth import init_browser, login_to_facebook
from scraper import perform_scraping

# Load environment variables
load_dotenv()

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")

def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def main():
    parser = argparse.ArgumentParser(description="Facebook Operator Script")
    parser.add_argument("--restart", action="store_true",
                        help="Force a fresh browser session even if one is running or cookies exist")
    args = parser.parse_args()

    email = os.getenv("FACEBOOK_EMAIL")
    password = os.getenv("FACEBOOK_PASSWORD")

    if not email or not password:
        print("Error: FACEBOOK_EMAIL or FACEBOOK_PASSWORD not found in .env file.")
        return

    # Load config.yaml
    cfg = load_config()
    browser_cfg = cfg.get("browser", {})
    stopping_cfg = cfg.get("stopping", {})
    output_cfg = cfg.get("output", {})

    keep_open = browser_cfg.get("keep_open", True)
    mfa_sleep = browser_cfg.get("mfa_sleep", 30)
    restart = args.restart or browser_cfg.get("restart", False)

    target_urls = cfg.get("target_urls") or []
    searches = cfg.get("searches") or []
    export_folder = output_cfg.get("export_folder", "exports")
    filename_prefix = output_cfg.get("filename_prefix", None)

    max_posts = stopping_cfg.get("max_posts", 10)
    max_scrolls = stopping_cfg.get("max_scrolls", 20)
    max_time_seconds = stopping_cfg.get("max_time_seconds", 300)

    auto_close_browser = not keep_open
    driver = None

    try:
        driver, is_existing = init_browser(auto_close=auto_close_browser, restart=restart)
        login_to_facebook(driver, email, password, mfa_sleep_seconds=mfa_sleep)

        # Build unified export path
        from datetime import datetime
        if not filename_prefix:
            filename_prefix = f"scraped_posts_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        root = os.path.dirname(os.path.dirname(__file__))
        export_path = os.path.join(root, export_folder, f"{filename_prefix}.json")

        global_posts = []
        global_seen_keys = set()

        # Scrape each explicit target URL
        for url in target_urls:
            perform_scraping(
                driver,
                target_url=url,
                export_path=export_path,
                max_posts=max_posts,
                max_scrolls=max_scrolls,
                max_time_seconds=max_time_seconds,
                scraped_posts=global_posts,
                seen_keys=global_seen_keys,
            )

        # Run each search query and scrape its results feed
        import urllib.parse
        for query in searches:
            search_url = f"https://www.facebook.com/search/top/?q={urllib.parse.quote(query)}"
            perform_scraping(
                driver,
                target_url=search_url,
                export_path=export_path,
                max_posts=max_posts,
                max_scrolls=max_scrolls,
                max_time_seconds=max_time_seconds,
                scraped_posts=global_posts,
                seen_keys=global_seen_keys,
            )

    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()
        if driver:
            driver.save_screenshot("error.png")
            print("Saved error screenshot to error.png")
    finally:
        if auto_close_browser and driver:
            print("Closing browser...")
            driver.quit()
        elif driver:
            print("Browser left open as requested (keep_open=true in config).")

if __name__ == "__main__":
    main()
