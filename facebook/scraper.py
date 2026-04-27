import time
import os
import json
import re
import urllib.parse
from datetime import datetime
from selenium.webdriver.common.by import By
from utils import get_human_delay, human_typing

def search_facebook(driver, query):
    """
    Executes a search on Facebook for the given query.
    Uses direct URL navigation for robustness against changing search bar UI locators.
    """
    print(f"Searching Facebook for: '{query}'")
    encoded_query = urllib.parse.quote(query)
    search_url = f"https://www.facebook.com/search/top/?q={encoded_query}"
    
    driver.get(search_url)
    
    # Allow time for search results to load
    time.sleep(get_human_delay(3, 6))
    print(f"Search navigation complete for '{query}'")


# ─────────────────────────────────────────────────
#  The JS payload that extracts ALL visible posts
#  in a single atomic browser call.  No Selenium
#  element handles are used, so no stale-element
#  or index-shifting bugs are possible.
# ─────────────────────────────────────────────────
EXTRACT_JS = r"""
try {
    let articles = Array.from(document.querySelectorAll('div[aria-posinset]'));
    if(!articles.length) articles = Array.from(document.querySelectorAll('div[role="article"]'));
    if(!articles.length) return [];


    // 2. Extract each article
    let results = [];
    articles.forEach(article => {

        // Skip empty/loading skeleton articles
        let tc = (article.textContent || '').trim();
        if(!tc || tc.length < 10 || tc.includes('Loading...')) return;

        // --- AUTHOR ---
        let author = '';
        let authorEl = article.querySelector('a[href*="/user/"][aria-label]');
        if(authorEl) {
            author = authorEl.getAttribute('aria-label').trim();
        } else {
            article.querySelectorAll('a[href*="/user/"]').forEach(el => {
                if(!author) {
                    let t = (el.textContent || '').trim();
                    if(t && t.length > 1 && t.length < 80) author = t;
                }
            });
        }

        // --- TIMESTAMP & POST LINK ---
        let timestamp = '';
        let postLink = '';
        article.querySelectorAll('a[href*="/posts/"], a[href*="/permalink/"], a[href*="story_fbid"]').forEach(el => {
            let href = el.getAttribute('href') || '';
            let txt = (el.textContent || '').trim();
            if(!timestamp && txt && txt.length < 20 && /[0-9]/.test(txt)) timestamp = txt;
            if(!postLink) {
                let clean = href.split('?')[0];
                if(clean && clean.includes('/posts/')) postLink = clean;
            }
        });
        if(!postLink) {
            article.querySelectorAll('a').forEach(el => {
                if(!postLink) {
                    let href = el.getAttribute('href') || '';
                    if(href.includes('/groups/') && href.includes('/posts/'))
                        postLink = href.split('?')[0];
                }
            });
        }

        // --- POST BODY TEXT ---
        let bodyText = '';
        let msgEl = article.querySelector('[data-ad-comet-preview="message"]');
        if(msgEl) {
            bodyText = (msgEl.textContent || '').trim();
        } else {
            let best = null, bestLen = 0;
            article.querySelectorAll('div[dir="auto"]').forEach(el => {
                let t = (el.textContent || '').trim();
                if(t.length > bestLen && !t.startsWith('Facebook')) { bestLen = t.length; best = el; }
            });
            if(best) bodyText = (best.textContent || '').trim();
        }

        // --- REACTIONS ---
        let likeCount = 0;
        let reactEl = article.querySelector('span[aria-label*="reaction"]');
        if(reactEl) {
            let m = (reactEl.getAttribute('aria-label') || '').match(/[0-9,]+/);
            if(m) likeCount = parseInt(m[0].replace(/,/g, ''));
        }
        if(!likeCount) {
            article.querySelectorAll('span, div').forEach(el => {
                if(!likeCount) {
                    let t = (el.textContent || '').trim();
                    let m = t.match(/All reactions:\s*([0-9,K]+)/);
                    if(m) likeCount = m[1];
                }
            });
        }

        // --- COMMENTS COUNT ---
        let commentCount = 0;
        article.querySelectorAll('span, div').forEach(el => {
            if(!commentCount) {
                let t = (el.textContent || '').trim();
                let m = t.match(/^([0-9,]+)\s+comment/i);
                if(m) commentCount = parseInt(m[1].replace(/,/g, ''));
            }
        });

        // --- COMMENTS LIST ---
        let comments = [];
        article.querySelectorAll('div[aria-label^="Comment by"]').forEach(cDiv => {
            let label = cDiv.getAttribute('aria-label') || '';
            let rest = label.replace(/^Comment by\s+/, '');
            let cAuthor = rest.split(' at ')[0]
                .replace(/\s*(\d+\s+(second|minute|hour|day|week|month|year)s?\s+ago|yesterday|just now)$/i, '')
                .trim();
            let textEl = cDiv.querySelector('div[dir="auto"]');
            let cText = textEl ? (textEl.textContent || '').trim() : '';
            if(!cText) cText = (cDiv.textContent || '').trim().replace(cAuthor, '').trim();
            if(cAuthor && cText) comments.push({author: cAuthor, text: cText});
        });

        // --- ATTACHMENTS ---
        let hasAttachment = false;
        if(article.querySelectorAll('a[href*="/photo/"], a[href*="/video/"], a[href*="watch"]').length > 0) hasAttachment = true;
        if(article.querySelectorAll('video').length > 0) hasAttachment = true;

        // --- EXTERNAL LINKS ---
        let externalLinks = [];
        article.querySelectorAll('a[href]').forEach(el => {
            let href = el.getAttribute('href') || '';
            if(href.startsWith('http') && !href.includes('facebook.com')) externalLinks.push(href);
        });
        externalLinks = Array.from(new Set(externalLinks));

        results.push({
            author: author || 'Unknown',
            time: timestamp || 'Unknown',
            main_link: postLink || '',
            post_text: bodyText,
            reactions: { like: likeCount, love: 0, care: 0, haha: 0, wow: 0, sad: 0, angry: 0, total: likeCount },
            comments_count: commentCount,
            comments: comments,
            has_attachment: hasAttachment,
            extracted_links: externalLinks
        });
    });
    return results;
} catch(err) {
    return [{_error: err.toString()}];
}
"""


def scrape_posts(driver, max_posts=None, max_scrolls=None, max_time_seconds=None, output_filename=None, scraped_posts=None, seen_keys=None):
    """
    Scrolls down the current page and scrapes posts until ANY of the specified limits are met.
    
    :param driver: Selenium WebDriver instance
    :param max_posts: Maximum number of posts to extract
    :param max_scrolls: Maximum number of scroll down actions
    :param max_time_seconds: Maximum time to spend scrolling and extracting
    :param output_filename: If provided, exports the extracted dataset to this JSON file path.
    :return: A list of extracted posts
    """
    print(f"Starting to scrape posts. Limits - Posts: {max_posts}, Scrolls: {max_scrolls}, Time: {max_time_seconds}s")
    
    start_time = time.time()
    scroll_count = 0
    if scraped_posts is None:
        scraped_posts = []
    if seen_keys is None:
        seen_keys = set()  # dedup by post permalink
    initial_count = len(scraped_posts)
    
    # Helper to save JSON structurally in a folder
    def save_json():
        if output_filename and scraped_posts:
            try:
                out_dir = os.path.dirname(output_filename)
                if out_dir and not os.path.exists(out_dir):
                    os.makedirs(out_dir)
                with open(output_filename, 'w', encoding='utf-8') as f:
                    json.dump(scraped_posts, f, indent=4, ensure_ascii=False)
                print(f"\n[{len(scraped_posts)} posts successfully saved to '{output_filename}']")
            except Exception as e:
                print(f"Error saving to JSON: {e}")

    while True:
        elapsed_time = time.time() - start_time
        
        # 1. Check time limit
        if max_time_seconds and elapsed_time > max_time_seconds:
            print(f"Time limit reached ({elapsed_time:.1f}s / {max_time_seconds}s). Stopping scrape.")
            break
            
        # 2. Check scroll limit
        if max_scrolls is not None and scroll_count >= max_scrolls:
            print(f"Scroll limit reached ({scroll_count} / {max_scrolls}). Stopping scrape.")
            break
            
        # 3. Dismiss popups
        try:
            driver.execute_script("""
                document.querySelectorAll('div[role="button"], span, div, button').forEach(b => {
                    let t = b.innerText;
                    if (t && (t === 'Not Now' || t === 'OK' || t === 'Allow' || t === 'Block')) {
                        b.click();
                    }
                });
                document.querySelectorAll('div[aria-label="Close"], div[aria-label="Cancel"]').forEach(b => b.click());
            """)
        except Exception:
            pass
            
        # 4. Click all "See more" buttons first, then wait for DOM to expand
        try:
            driver.execute_script("""
                let articles = Array.from(document.querySelectorAll('div[aria-posinset]'));
                if(!articles.length) articles = Array.from(document.querySelectorAll('div[role="article"]'));
                articles.forEach(a => {
                    a.querySelectorAll('[role="button"]').forEach(btn => {
                        let t = (btn.textContent || '').trim().toLowerCase();
                        if(t === 'see more' || t === 'see more...' || t === '...see more') {
                            try { btn.click(); } catch(e) {}
                        }
                    });
                });
            """)
            time.sleep(0.6)  # Wait for DOM to update after See More expansion
        except Exception:
            pass

        # 5. Extract ALL visible posts in one atomic JS call
        try:
            all_posts = driver.execute_script(EXTRACT_JS)
            
            if all_posts:
                new_count = 0
                for post_js in all_posts:
                    if '_error' in post_js:
                        print('JS Error:', post_js['_error'])
                        continue
                    
                    if not post_js.get('post_text') and post_js.get('author') == 'Unknown':
                        continue
                    
                    # Dedup: if the post has a permalink, skip if already seen
                    link = f"{post_js.get('author', '').strip()}_{post_js.get('post_text', '').strip().lower()[:50]}"
                    print(link)
                    if link:
                        if link in seen_keys:
                            continue
                        seen_keys.add(link)
                    post_data = {"extracted_at": time.time()}
                    post_data.update(post_js)
                    scraped_posts.append(post_data)
                    new_count += 1
                    
                    if max_posts and (len(scraped_posts) - initial_count) >= max_posts:
                        print(f"Post limit reached ({len(scraped_posts) - initial_count} / {max_posts}). Stopping scrape.")
                        save_json()
                        return scraped_posts

        except Exception as e:
            print(f"Encountered an issue parsing posts: {e}")

        # 5. Scroll down by one viewport height
        print(f"Scrolling down... (Scroll {scroll_count + 1})  [collected {len(scraped_posts)} posts so far]")
        driver.execute_script("window.scrollBy(0, window.innerHeight);")
        scroll_count += 1
        
        # Wait for Facebook to render newly-loaded posts
        time.sleep(get_human_delay(2.0, 4.0))
        
    print(f"Scraping finished. Collected {len(scraped_posts)} posts.")
    save_json()
    return scraped_posts


def navigate_to_page(driver, url):
    """
    Navigates to a specific Facebook group or page.
    """
    if not url.startswith("http"):
        url = "https://" + url
    print(f"Navigating to: {url}")
    driver.get(url)
    time.sleep(get_human_delay(4, 7))
    print("Navigation complete. Ready to scrape.")


def perform_scraping(
    driver,
    target_url=None,
    export_path=None,
    max_posts=10,
    max_scrolls=20,
    max_time_seconds=300,
    scraped_posts=None,
    seen_keys=None,
):
    """Orchestrates navigation and scraping for one target URL."""
    print(f"\n--- Starting scraping workflow for {target_url} ---")

    if target_url:
        navigate_to_page(driver, target_url)

    posts = scrape_posts(
        driver=driver,
        max_posts=max_posts,
        max_scrolls=max_scrolls,
        max_time_seconds=max_time_seconds,
        output_filename=export_path,
        scraped_posts=scraped_posts,
        seen_keys=seen_keys,
    )

    print(f"\n--- Workflow complete: {len(posts)} posts saved to {export_path} ---")
    for idx, p in enumerate(posts, 1):
        preview = p['post_text'].replace('\n', ' ')[:80]
        print(f"  [{idx}] {p['author']} | {p['time']} | {preview}...")
