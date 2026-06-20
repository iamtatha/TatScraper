import time
import os
import json
import urllib.parse
from facebook.utils import get_human_delay, human_typing

def search_facebook(driver, query):
    """
    Executes a search on Facebook for the given query.
    Uses direct URL navigation for robustness against changing search bar UI locators.
    """
    print(f"Searching Facebook for: '{query}'")
    encoded_query = urllib.parse.quote(query)
    search_url = f"https://www.facebook.com/search/top/?q={encoded_query}"
    driver.get(search_url)
    time.sleep(get_human_delay(3, 6))
    print(f"Search navigation complete for '{query}'")


# ─────────────────────────────────────────────────
#  Atomic JS extraction payload.
#  Priority fields: post_text, main_link, time, has_attachment.
#  Everything else is best-effort.
# ─────────────────────────────────────────────────
EXTRACT_JS = r"""
try {
    let articles = Array.from(document.querySelectorAll('div[aria-posinset]'));
    if (!articles.length) articles = Array.from(document.querySelectorAll('div[role="article"]'));
    if (!articles.length) return [];

    // Visible text helper — innerText skips hidden screen-reader-only spans
    function vis(el) { return el ? (el.innerText || el.textContent || '').trim() : ''; }

    function cleanHref(href) {
        if (!href || href === '#' || href.startsWith('javascript')) return '';
        let base = href.startsWith('http') ? href : 'https://www.facebook.com' + href;
        // Reject photo links that have no real photo ID (fbid=digits)
        // These are image viewer links with only tracking params — not post permalinks.
        if (base.includes('/photo') && !/[?&]fbid=\d/.test(base)) return '';
        try {
            let u = new URL(base);
            let keep = ['fbid', 'set', 'story_fbid', 'id', 'v'];
            let params = [];
            for (let k of keep) {
                if (u.searchParams.has(k)) params.push(k + '=' + u.searchParams.get(k));
            }
            let clean = u.origin + u.pathname;
            if (params.length > 0) clean += '?' + params.join('&');
            return clean;
        } catch(e) {
            // Fallback: strip all query params
            let clean = base.split('?')[0];
            // Recheck: reject bare photo path even in fallback
            if (/\/photo\/?$/.test(clean)) return '';
            return clean;
        }
    }


    // Aria-label time pattern: "3 hours ago", "June 20 at 2:30 PM", "Yesterday", etc.
    const TIME_ARIA = /(\d+\s*(second|minute|hour|day|week|month|year)s?\s*(ago)?|yesterday|just now|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)/i;
    // Short relative-time pattern for visible text: "3h", "2d", "Monday"
    const TIME_SHORT = /^(\d+\s*(s|m|h|d|w)|(monday|tuesday|wednesday|thursday|friday|saturday|sunday)|yesterday|just now)$/i;

    let results = [];

    articles.forEach(article => {
        let articleText = vis(article);
        if (!articleText || articleText.length < 10 || articleText.includes('Loading...')) return;

        // ── 1. POST TEXT (highest priority) ──────────────────────────────────
        // Expand "See more" inline before reading text
        article.querySelectorAll('[role="button"]').forEach(btn => {
            let t = vis(btn).toLowerCase();
            if (t === 'see more' || t === 'see more...') {
                try { btn.click(); } catch(e) {}
            }
        });

        let bodyText = '';
        // Try the comet message container first (most reliable)
        let msgEl = article.querySelector('[data-ad-comet-preview="message"], [data-ad-preview="message"]');
        if (msgEl) {
            bodyText = vis(msgEl);
        }
        // Fallback: largest dir="auto" div that isn't in a comment list
        if (!bodyText) {
            let best = null, bestLen = 0;
            article.querySelectorAll('div[dir="auto"], span[dir="auto"]').forEach(el => {
                if (el.closest('ul') || el.closest('[aria-label*="comment" i]')) return;
                let t = vis(el);
                if (t.length > bestLen && !t.startsWith('Facebook')) {
                    bestLen = t.length; best = el;
                }
            });
            if (best) bodyText = vis(best);
        }
        // Strip "See less" / "See more" button text that got included
        bodyText = bodyText.replace(/\s*See\s+(less|more)\s*$/i, '').trim();

        // ── 2. POST LINK (high priority) ─────────────────────────────────────
        // Score every link in the article by how likely it is to be the post URL.
        // Higher score = more post-like. Take the highest-scoring link.
        let postLink = '';
        let bestScore = 0;

        article.querySelectorAll('a[href]').forEach(el => {
            let href = el.getAttribute('href') || '';
            if (!href || href === '#' || href.startsWith('javascript')) return;

            let score = 0;
            if (/\/posts\/pfbid/.test(href))                      score = 100;
            else if (/\/posts\/\d/.test(href))                    score = 90;
            else if (/\/posts\//.test(href))                      score = 80;
            else if (/story_fbid=/.test(href))                    score = 70;
            else if (/\/permalink\//.test(href))                  score = 60;
            else if (/\/videos\/\d/.test(href))                   score = 50;
            else if (/\/reel\/\d/.test(href))                     score = 40;
            // Photo link only valid if it has a real fbid or set param
            else if (/\/photo/.test(href) && /[?&]fbid=\d/.test(href)) score = 30;

            if (score > bestScore) {
                bestScore = score;
                let cleaned = cleanHref(href);
                if (cleaned) { postLink = cleaned; }
            }
        });

        // ── 3. TIMESTAMP & POST LINK (from timestamp anchor) ─────────────────
        // The timestamp element ALWAYS links to the post — even for photo posts
        // whose URL is /photo/?fbid=... That IS the canonical post URL.
        // Do NOT exclude /photo links here.
        let timestamp = '';
        let allEls = Array.from(article.querySelectorAll('[aria-label]'));
        for (let el of allEls) {
            let al = el.getAttribute('aria-label') || '';
            if (TIME_ARIA.test(al)) {
                timestamp = al;
                // The parent <a> of the timestamp element is the post link
                let linkEl = (el.tagName === 'A') ? el : el.closest('a');
                if (linkEl) {
                    let href = linkEl.getAttribute('href') || '';
                    if (href && href !== '#' && !href.startsWith('javascript')) {
                        let cleaned = cleanHref(href);
                        // Only override if cleaned URL is non-empty and not a bare /photo/
                        if (cleaned) postLink = cleaned;
                    }
                }
                break;
            }
        }
        // Fallback: scan links for short relative-time visible text ("3h", "Monday")
        // For photo posts, the visible time link also goes to /photo/?fbid=... — allow it.
        if (!timestamp) {
            article.querySelectorAll('a[href]').forEach(el => {
                if (timestamp) return;
                let href = el.getAttribute('href') || '';
                // Only skip hashtags and anchor-only links, NOT photo links
                if (href.includes('/hashtag') || href === '#' || href.includes('?__cft__')) return;
                let t = vis(el);
                if (TIME_SHORT.test(t)) {
                    timestamp = t;
                    if (!postLink) postLink = cleanHref(href);
                }
            });
        }

        // ── 4. HAS ATTACHMENT ────────────────────────────────────────────────
        let hasAttachment = false;
        if (article.querySelector('img[src*="scontent"], video')) hasAttachment = true;
        if (article.querySelector('a[href*="/photo/"], a[href*="/video/"], a[href*="watch"]')) hasAttachment = true;

        // ── 5. REACTIONS (best-effort) ───────────────────────────────────────
        let likeCount = 0;
        let reactEl = article.querySelector('span[aria-label*="reaction" i]');
        if (reactEl) {
            let m = (reactEl.getAttribute('aria-label') || '').match(/[\d,]+/);
            if (m) likeCount = parseInt(m[0].replace(/,/g, ''));
        }

        // ── 6. COMMENTS COUNT (best-effort) ──────────────────────────────────
        let commentCount = 0;
        article.querySelectorAll('span, div').forEach(el => {
            if (commentCount) return;
            let t = vis(el);
            let m = t.match(/^([\d,]+)\s+comment/i);
            if (m) commentCount = parseInt(m[1].replace(/,/g, ''));
        });

        // ── 7. AUTHOR (best-effort) ───────────────────────────────────────────
        let author = '';
        // Try heading link first (most reliable on group/page feeds)
        let hLink = article.querySelector('h2 a, h3 a, h4 a');
        if (hLink) {
            let t = vis(hLink) || hLink.getAttribute('aria-label') || '';
            if (t && t.length > 1 && t.length < 100 && t !== 'Sponsored') author = t;
        }
        // Try strong > a (sponsored/page posts)
        if (!author) {
            let sa = article.querySelector('strong a');
            if (sa) {
                let t = vis(sa) || sa.getAttribute('aria-label') || '';
                if (t && t.length > 1 && t.length < 100) author = t;
            }
        }

        // ── 8. COMMENTS LIST (best-effort) ───────────────────────────────────
        let comments = [];
        article.querySelectorAll('div[aria-label^="Comment by"]').forEach(cDiv => {
            let label = cDiv.getAttribute('aria-label') || '';
            let rest = label.replace(/^Comment by\s+/, '');
            let cAuthor = rest.split(' at ')[0].replace(/\s*(\d+\s+\w+s?\s+ago|yesterday|just now)$/i, '').trim();
            let textEl = cDiv.querySelector('div[dir="auto"]');
            let cText = textEl ? vis(textEl) : vis(cDiv).replace(cAuthor, '').trim();
            if (cAuthor && cText && !comments.find(c => c.text === cText)) {
                comments.push({ author: cAuthor, text: cText });
            }
        });
        if (!comments.length) {
            article.querySelectorAll('ul li').forEach(li => {
                let nameEl = li.querySelector('a');
                let textEl = li.querySelector('div[dir="auto"], span[dir="auto"]');
                if (!nameEl || !textEl) return;
                let cAuthor = vis(nameEl), cText = vis(textEl);
                if (cAuthor && cText && cAuthor.length < 80 &&
                    !comments.find(c => c.text === cText)) {
                    comments.push({ author: cAuthor, text: cText });
                }
            });
        }

        // ── 9. EXTERNAL LINKS ────────────────────────────────────────────────
        let externalLinks = [];
        article.querySelectorAll('a[href]').forEach(el => {
            let href = el.getAttribute('href') || '';
            if (href.startsWith('http') && !href.includes('facebook.com') && !href.includes('fb.com')) {
                externalLinks.push(href);
            }
        });
        externalLinks = Array.from(new Set(externalLinks));

        results.push({
            author:          author || 'Unknown',
            time:            timestamp || 'Unknown',
            main_link:       postLink || '',
            post_text:       bodyText,
            has_attachment:  hasAttachment,
            reactions:       { total: likeCount },
            comments_count:  commentCount,
            comments:        comments,
            extracted_links: externalLinks
        });
    });

    return results;
} catch(err) {
    return [{ _error: err.toString() }];
}
"""


def scrape_posts(driver, max_posts=None, max_scrolls=None, max_time_seconds=None,
                 output_filename=None, scraped_posts=None, seen_keys=None):
    """
    Scrolls down the current page and scrapes posts until any limit is hit.
    See more buttons are expanded both in the pre-scroll JS step and inline in EXTRACT_JS.
    """
    print(f"Starting to scrape. Limits — Posts: {max_posts}, Scrolls: {max_scrolls}, Time: {max_time_seconds}s")

    start_time = time.time()
    scroll_count = 0
    if scraped_posts is None:
        scraped_posts = []
    if seen_keys is None:
        seen_keys = set()
    initial_count = len(scraped_posts)

    def save_json():
        if output_filename and scraped_posts:
            try:
                out_dir = os.path.dirname(output_filename)
                if out_dir and not os.path.exists(out_dir):
                    os.makedirs(out_dir)
                with open(output_filename, 'w', encoding='utf-8') as f:
                    json.dump(scraped_posts, f, indent=4, ensure_ascii=False)
                print(f"\n[{len(scraped_posts)} posts saved to '{output_filename}']")
            except Exception as e:
                print(f"Error saving JSON: {e}")

    while True:
        elapsed = time.time() - start_time

        if max_time_seconds and elapsed > max_time_seconds:
            print(f"Time limit reached ({elapsed:.1f}s). Stopping.")
            break
        if max_scrolls is not None and scroll_count >= max_scrolls:
            print(f"Scroll limit reached ({scroll_count}). Stopping.")
            break

        # Dismiss popups
        try:
            driver.execute_script("""
                ['Not Now','OK','Allow','Block'].forEach(txt => {
                    document.querySelectorAll('[role="button"],button').forEach(b => {
                        if ((b.innerText||'').trim() === txt) b.click();
                    });
                });
                document.querySelectorAll('[aria-label="Close"],[aria-label="Cancel"]').forEach(b => b.click());
            """)
        except Exception:
            pass

        # Expand ALL "See more" buttons on visible posts before extraction
        try:
            driver.execute_script("""
                let arts = Array.from(document.querySelectorAll('div[aria-posinset], div[role="article"]'));
                arts.forEach(a => {
                    a.querySelectorAll('[role="button"]').forEach(btn => {
                        let t = (btn.innerText || btn.textContent || '').trim().toLowerCase();
                        if (t === 'see more' || t === 'see more...') {
                            try { btn.click(); } catch(e) {}
                        }
                    });
                });
            """)
            time.sleep(0.8)  # Let DOM update after expansions
        except Exception:
            pass

        # Extract all visible posts atomically
        try:
            all_posts = driver.execute_script(EXTRACT_JS)

            if all_posts:
                for post in all_posts:
                    if '_error' in post:
                        print('JS Error:', post['_error'])
                        continue

                    # Skip empty/placeholder posts
                    if not post.get('post_text') and post.get('author') == 'Unknown':
                        continue

                    # Dedup by link first, then by text fingerprint
                    link = post.get('main_link', '')
                    if link:
                        if link in seen_keys:
                            continue
                        seen_keys.add(link)
                    else:
                        fp = f"{post.get('author','').strip()}|{post.get('post_text','').strip()[:100]}"
                        if fp in seen_keys:
                            continue
                        seen_keys.add(fp)

                    post_data = {"extracted_at": time.time()}
                    post_data.update(post)
                    scraped_posts.append(post_data)

                    if max_posts and (len(scraped_posts) - initial_count) >= max_posts:
                        print(f"Post limit reached ({len(scraped_posts) - initial_count} / {max_posts}).")
                        save_json()
                        return scraped_posts

        except Exception as e:
            print(f"Extraction error: {e}")

        print(f"Scroll {scroll_count + 1} — {len(scraped_posts)} posts collected so far")
        driver.execute_script("window.scrollBy(0, window.innerHeight);")
        scroll_count += 1
        time.sleep(get_human_delay(2.0, 4.0))

    print(f"Scraping done. Total: {len(scraped_posts)} posts.")
    save_json()
    return scraped_posts


def navigate_to_page(driver, url):
    """Navigates to a Facebook group, page, or any URL."""
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
    print(f"\n--- Scraping: {target_url} ---")

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

    print(f"\n--- Done: {len(posts)} posts — {export_path} ---")
    for idx, p in enumerate(posts, 1):
        preview = p['post_text'].replace('\n', ' ')[:80]
        print(f"  [{idx}] {p['author']} | {p['time']} | {preview}...")
