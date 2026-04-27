# Facebook Agentic Scraper

A modular, robust, and extensible Python-based Selenium scraper for Facebook designed to mimic human activity, reuse browser sessions automatically, and gracefully handle rate-limit avoidance via realistic delays.

## 📁 Project Structure

```text
facebook/
├── config.yaml          # The main configuration file for URLs, searches, and scraping limits
├── `auth.py`              # Handles Chrome instantiation, session connectivity, and smart login injection
├── `scraper.py`           # Contains the core extraction logic, now functioning via an atomic JS payload to bypass DOM inconsistencies
├── `utils.py`             # Contains human-delay algorithms and realistic typing simulation
├── `facebook_operator.py` # The main controller/entry-point which coordinates the target URLs, searches, and browser
├── `.env`                 # Stores your sensitive environment credentials
└── `chrome_profile/`      # (Auto-generated) Saves cookies/localstorage to persist Facebook logins!
```

## 🛠️ Setup & Installation

1. Make sure you have the required packages installed:
   ```bash
   pip install selenium python-dotenv pyyaml
   ```
2. Create your `.env` file inside the `facebook/` folder:
   ```env
   FACEBOOK_EMAIL=your_email@example.com
   FACEBOOK_PASSWORD=your_secure_password
   ```

## 🚀 Configuration (`config.yaml`)

You no longer need to pass command line arguments for tweaking limits. All parameters are defined centrally in `facebook/config.yaml`:

```yaml
target_urls:
  - "https://www.facebook.com/groups/2693327660749392"
  # Add as many URLs (pages/groups/feed) as you want

searches:
  - "Machine Learning Bangalore"
  # The operator will run these queries and scrape their result feeds

stopping:
  max_posts: 20          # Stop after collecting this many posts (null = no limit)
  max_scrolls: 20        # Stop after this many scroll actions
  max_time_seconds: 300  # Stop after this many seconds elapsed

browser:
  keep_open: true        # Leaves browser open after finishing
  mfa_sleep: 30          # Seconds to wait for 2FA after login
  restart: false         # Force clear session cache

output:
  export_folder: "exports"
  filename_prefix: null  # Optional prefix. Output unifies all tasks into a single JSON per run.
```

## 🔧 Running the Script

To start the scraping workflow across all configured target URLs and searches, simply run:

```bash
python facebook/facebook_operator.py
```

*Note: You can still force a fresh session instance by passing `--restart` via CLI.*

## 🧠 Working Principle

1. **`facebook_operator.py`**
   - Parses the `config.yaml` file.
   - Bootstraps the Chrome environment (`auth.py`) which re-uses any open debugger instances to evade repetitive MFA.
   - Pre-calculates a unified `scraped_posts_{timestamp}.json` file so that all `target_urls` and `searches` results accumulate in a single list instead of cluttering the exports.
   - Loops through each URL and search term, handing them to `perform_scraping()`.

2. **`scraper.py`**
   - Implements `navigate_to_page` to safely get to groups, pages, or search results.
   - `scrape_posts` begins scrolling down the Facebook feed incrementally (one viewport height at a time). This effectively prevents Facebook's virtualized list from skipping or evicting posts entirely before they are read.
   - **Atomic JS DOM Extraction:** In the past, matching element indices to Selenium Python handles crashed because Facebook shifted the DOM between queries. Now, an enclosed JS routine runs synchronously in one shot:
     - It expands all "See more" buttons gracefully.
     - Loops through every feed article on the screen.
     - Cleans author names, dates, text, comment authors, external links, and engagement counts right in the browser engine.
     - Returns a clean JSON representation of all data for Python to just parse.
   - Post deduping is now performed via the unique permalink (`main_link`). If a post is retrieved over multiple scrolls, it is successfully skipped to prevent duplication.

3. **`auth.py`**
   - Deploys Chrome using `--remote-debugging-port=9222` alongside `--user-data-dir=chrome_profile`. If you set `keep_open: true`, subsequent runs will instantly reconnect to the existing chrome tab without refreshing constraints.
