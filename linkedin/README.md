# LinkedIn Agentic Scraper

A modular, robust Python-based Selenium scraper for LinkedIn, matching the same design as the Facebook scraper. Reuses persistent Chrome sessions, mimics human behavior with realistic delays, and accumulates all targets into a single unified JSON export per run.

## 📁 Project Structure

```text
linkedin/
├── config.yaml              # Targets, searches, stopping conditions, browser settings
├── auth.py                  # Chrome launch + LinkedIn login
├── scraper.py               # Atomic JS extraction engine (LinkedIn DOM selectors)
├── utils.py                 # Human delay and typing utilities
├── linkedin_operator.py     # Main entry point
├── .env                     # (shared with root) LinkedIn credentials
└── chrome_profile/          # (Auto-generated) Persistent Chrome session
```

## 🛠️ Setup & Installation

```bash
pip install selenium python-dotenv pyyaml
```

Add your credentials to a `.env` file in the **scrapers root** (it's shared with the Facebook scraper):

```env
LINKEDIN_EMAIL=your_email@example.com
LINKEDIN_PASSWORD=your_secure_password
```

> **Note**: The LinkedIn scraper uses **port 9223** for remote debugging so it doesn't conflict with the Facebook scraper running on port 9222.

## 🚀 Configuration (`config.yaml`)

```yaml
target_urls:
  - "https://www.linkedin.com/feed/"
  # Accepts any LinkedIn URL: company posts, profile activity, etc.

searches:
  - "Machine Learning jobs"
  # Each query searches linkedin.com/search/results/content/

stopping:
  max_posts: 20
  max_scrolls: 20
  max_time_seconds: 300

browser:
  keep_open: true
  mfa_sleep: 30
  restart: false

output:
  export_folder: "exports"
  filename_prefix: null   # auto-generates scraped_posts_YYYYMMDD_HHMMSS.json
```

## 🔧 Running the Script

```bash
python linkedin/linkedin_operator.py
```

Pass `--restart` to force a fresh login:

```bash
python linkedin/linkedin_operator.py --restart
```

## 🧠 Working Principle

1. **`linkedin_operator.py`** — Loads config, initializes Chrome (re-attaches to port 9223 if already open), logs in, builds a unified output path, and iterates through all target URLs + search queries.

2. **`auth.py`** — Handles LinkedIn's login form (`#session_key` / `#session_password`). Detects if already logged in and skips. Keeps persistent profile in `chrome_profile/`.

3. **`scraper.py`** — Uses an atomic JS payload (`EXTRACT_JS`) to:
   - Select post containers via `div[data-urn]`, `li.occludable-update`, or `div.feed-shared-update-v2`
   - De-duplicate nested containers to avoid counting the same post twice
   - Expand "…more" / "see more" buttons before reading text
   - Extract: author, timestamp, post link, post text, reactions, comment count, repost count, attachments, external links
   - Post link Strategy: tries `/feed/update/` links → then builds from `data-urn` directly (always present)
   - Dedup: by `main_link`, with author+text-slice fallback

## 📦 Output Fields

Each JSON record contains:

| Field | Description |
|---|---|
| `author` | Post author's name |
| `time` | Relative timestamp (e.g. "2h", "3d") |
| `main_link` | Canonical post URL |
| `post_text` | Full post text (after "see more" expansion) |
| `reactions.total` | Total reaction count |
| `comments_count` | Number of comments |
| `reposts_count` | Number of reposts/shares |
| `has_attachment` | True if post contains image/video/document |
| `extracted_links` | Non-LinkedIn external URLs found in post |
| `extracted_at` | Unix timestamp of when the post was scraped |
