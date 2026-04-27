import time
import os
import json
import urllib.parse
from datetime import datetime
from utils import get_human_delay

def search_linkedin(driver, query):
    """
    Executes a search on LinkedIn for the given query (posts/content only).
    """
    print(f"Searching LinkedIn for: '{query}'")
    encoded_query = urllib.parse.quote(query)
    search_url = f"https://www.linkedin.com/search/results/content/?keywords={encoded_query}&sortBy=date_posted"
    driver.get(search_url)
    time.sleep(get_human_delay(3, 6))
    print(f"Search navigation complete for '{query}'")


# ─────────────────────────────────────────────────
#  Debug: dump info about the live DOM
# ─────────────────────────────────────────────────
DEBUG_JS = r"""
let info = {};
info.url = window.location.href;
info.title = document.title;

// Look for POST CONTAINERS - try multiple selectors
let feedUpdateLinks = Array.from(document.querySelectorAll('a[href*="/feed/update/urn"]'));
info.feedUpdateLinkCount = feedUpdateLinks.length;
info.sampleLinks = feedUpdateLinks.slice(0,5).map(a => ({
    href: (a.getAttribute('href')||'').substring(0,100),
    text: (a.textContent||'').trim().substring(0,60)
}));

// Check for article/post container tags
let articles = Array.from(document.querySelectorAll('article, [data-id*="activity"], [data-id*="update"], div[class*="feed"], div[class*="post"]'));
info.articleCount = articles.length;
info.sampleArticles = articles.slice(0,3).map(a => ({
    tag: a.tagName,
    classes: (a.className||'').substring(0,100),
    dataId: (a.getAttribute('data-id')||'').substring(0,100),
    childCount: a.children.length
}));

// Look for text containers
let dirLtr = Array.from(document.querySelectorAll('[dir="ltr"]'));
info.dirLtrCount = dirLtr.length;
info.sampleDirLtr = dirLtr.slice(0,5).map(el => ({
    tag: el.tagName,
    textLength: (el.textContent||'').length,
    preview: (el.textContent||'').trim().substring(0,80)
}));

// Look for reaction patterns more broadly
let spans = Array.from(document.querySelectorAll('span, a, button')).filter(el => {
    let t = (el.textContent||'').toLowerCase();
    return t.match(/\d+\s*(reaction|comment|repost|like|view)/);
}).slice(0,10);
info.socialElements = spans.map(el => ({
    tag: el.tagName,
    text: (el.textContent||'').trim().substring(0,80)
}));

// Dump ALL links to see what's available
let allLinks = Array.from(document.querySelectorAll('a[href]'));
info.totalLinks = allLinks.length;
info.linkHrefPatterns = {};
allLinks.forEach(a => {
    let href = (a.getAttribute('href')||'').split('?')[0];
    if(href.includes('/feed/')) {
        let key = href.split('/').slice(0,7).join('/');
        info.linkHrefPatterns[key] = (info.linkHrefPatterns[key]||0) + 1;
    }
});

// Look for author anchors
let authorAnchors = Array.from(document.querySelectorAll('a[href*="/in/"], a[href*="/company/"]')).slice(0,15);
info.authorAnchors = authorAnchors.map(a => ({
    href: (a.getAttribute('href')||'').substring(0,80),
    text: (a.textContent||'').trim().substring(0,100)
}));

// Check for time elements
let times = Array.from(document.querySelectorAll('time'));
info.timeCount = times.length;
info.timeSamples = times.slice(0,5).map(t => ({
    datetime: (t.getAttribute('datetime')||'').substring(0,80),
    text: (t.textContent||'').trim().substring(0,40)
}));

info.bodyHTML = document.body.innerHTML.substring(0, 200);

return JSON.stringify(info);
"""


# ─────────────────────────────────────────────────
#  Main extraction payload.
#
#  LinkedIn 2025 DOM: all CSS classes obfuscated.
#  Strategy: find a[href*="/feed/update/urn"] links
#  (post permalinks that are always stable), walk
#  UP to locate the post container, then extract
#  data using structural patterns only.
#
#  FIXES:
#   1. AUTHOR: Skip anchors whose text is short/badge-like
#      ("Premium", "1st", "2nd", etc.). The real author
#      anchor has meaningful name text (>4 chars, not a badge).
#      Also strip inline badge nodes (SVG, img, nested spans)
#      by reading only the direct text nodes.
#
#   2. POST TEXT: LinkedIn wraps the body in a div/span with
#      dir="ltr" BUT the "see more" truncated version lives
#      inside a nested structure. We collect ALL dir="ltr"
#      spans that are NOT inside a[href] (link previews) and
#      pick the longest contiguous block.
#
#   3. TIMESTAMP: The <time> element with datetime attr is the
#      most reliable source. Fallback: the permalink anchor
#      whose aria-label often contains "• Xh •" patterns.
# ─────────────────────────────────────────────────
EXTRACT_JS = r"""
try {
    // ── HELPERS ──────────────────────────────────────────────────────────────

    function directTextOf(el) {
        let text = '';
        el.childNodes.forEach(node => {
            if (node.nodeType === Node.TEXT_NODE) {
                text += node.textContent;
            }
        });
        return text.trim();
    }

    const BADGE_NOISE = /^(premium|1st|2nd|3rd|\d+(st|nd|rd|th)?|follow|connect|\u2022|\u00b7|linkedin member)$/i;

    function extractAuthor(article) {
        let candidates = Array.from(article.querySelectorAll(
            'a[href*="/in/"], a[href*="/company/"]'
        ));
        for (let a of candidates) {
            let direct = directTextOf(a);
            let raw = direct || (a.textContent || '').trim();
            let name = raw.split(/\s*[•·\n]\s*/)[0]
                          .split(/\s{2,}/)[0]
                          .trim();

            if (!name || name.length <= 3 || BADGE_NOISE.test(name)) continue;
            if (name.startsWith('http') || name.includes('/')) continue;
            if (name.length > 80) name = name.substring(0, 80).trim();

            return name;
        }
        return '';
    }

    function extractTimestamp(article) {
        let timeEl = article.querySelector('time');
        if (timeEl) {
            let dt = timeEl.getAttribute('datetime');
            if (dt) return dt.trim();
            let txt = (timeEl.textContent || '').trim();
            if (txt) return txt;
        }
        
        let tsAnchor = article.querySelector('a[href*="/feed/update/urn"]');
        if (tsAnchor) {
            let label = (tsAnchor.getAttribute('aria-label') || '').trim();
            let m = label.match(/[•·]\s*(\d+[smhdwmy][a-z]*)\s*[•·]/i);
            if (m) return m[1];
            let txt = (tsAnchor.textContent || '').trim();
            if (txt.length <= 10 && txt.length > 0) return txt;
        }
        return '';
    }

    function extractPostText(article) {
        let best = '';
        let bestLen = 0;

        // Try dir="ltr" first
        let candidates = Array.from(article.querySelectorAll('[dir="ltr"]'));

        for (let el of candidates) {
            if (el.closest('a')) continue;
            let t = (el.textContent || '').trim();
            if (t.length <= 30) continue;
            if (t.length > bestLen) {
                bestLen = t.length;
                best = t;
            }
        }

        // Fallback: look for p, div, span in the article that contain reasonable text
        if (!best || bestLen < 50) {
            let fallback = Array.from(article.querySelectorAll('p, div, span')).filter(el => {
                // Skip navigation/button areas
                if (el.closest('nav') || el.closest('button')) return false;
                let t = (el.textContent || '').trim();
                return t.length > 50 && t.length < 5000 && !t.match(/^\d+\s*(reaction|comment|repost|like)/i);
            });

            for (let el of fallback) {
                let t = (el.textContent || '').trim();
                if (t.length > bestLen) {
                    bestLen = t.length;
                    best = t;
                }
            }
        }

        best = best.replace(/\n{3,}/g, '\n\n').trim();
        return best;
    }

    // ── CONTAINER DETECTION ───────────────────────────────────────────────────
    function findPostContainer(anchor) {
        let el = anchor;
        let maxLevels = 30;
        while (el.parentElement && maxLevels-- > 0) {
            let parent = el.parentElement;
            let siblingsWithLinks = 0;
            for (let child of parent.children) {
                if (child.querySelector('a[href*="/feed/update/urn"]')) {
                    siblingsWithLinks++;
                }
                if (siblingsWithLinks >= 2) {
                    return el;
                }
            }
            el = el.parentElement;
        }
        return el;
    }

    // ── MAIN LOOP ─────────────────────────────────────────────────────────────
    // Try multiple selectors for permalinks
    let permalinks = Array.from(document.querySelectorAll('a[href*="/feed/update/urn"]'));
    
    // If no /feed/update/ links, try broader patterns
    if (!permalinks.length) {
        permalinks = Array.from(document.querySelectorAll('a[href*="linkedin.com/feed"]'));
    }
    
    if (!permalinks.length) {
        return [{_info: 'No posts found - no permalink anchors detected'}];
    }

    let containerMap = new Map();
    permalinks.forEach(anchor => {
        let href = anchor.getAttribute('href') || '';
        if (!href) return;
        let cleanLink = href.startsWith('http')
            ? href.split('?')[0]
            : 'https://www.linkedin.com' + href.split('?')[0];
        let container = findPostContainer(anchor);
        if (container && !containerMap.has(container)) {
            containerMap.set(container, cleanLink);
        }
    });

    if (!containerMap.size) {
        return [{_info: 'No post containers found'}];
    }
    let results = [];

    containerMap.forEach((postLink, article) => {

        let author    = extractAuthor(article);
        let timestamp = extractTimestamp(article);
        let bodyText  = extractPostText(article);

        // ── REACTIONS ──────────────────────────────────────────────────────────
        let likeCount = 0;
        article.querySelectorAll('a, span, button').forEach(el => {
            if (likeCount) return;
            let t = (el.textContent || '').trim();
            let m1 = t.match(/and\s+([\d,]+)\s+others?\s+react/i);
            if (m1) { likeCount = parseInt(m1[1].replace(/,/g, '')) + 1; return; }
            let m2 = t.match(/([\d,]+)\s+reactions?/i);
            if (m2) { likeCount = parseInt(m2[1].replace(/,/g, '')); return; }
        });

        // ── COMMENTS ──────────────────────────────────────────────────────────
        let commentCount = 0;
        article.querySelectorAll('a, span, button').forEach(el => {
            if (commentCount) return;
            let t = (el.textContent || '').trim();
            let m = t.match(/([\d,]+)\s+comments?/i);
            if (m) commentCount = parseInt(m[1].replace(/,/g, ''));
        });

        // ── REPOSTS ───────────────────────────────────────────────────────────
        let repostCount = 0;
        article.querySelectorAll('a, span, button').forEach(el => {
            if (repostCount) return;
            let t = (el.textContent || '').trim();
            let m = t.match(/([\d,]+)\s+reposts?/i);
            if (m) repostCount = parseInt(m[1].replace(/,/g, ''));
        });

        // ── ATTACHMENTS ───────────────────────────────────────────────────────
        let hasAttachment = !!(
            article.querySelector('video') ||
            article.querySelector('img[src*="media"]') ||
            article.querySelector('[data-test-id*="image"]')
        );

        // ── EXTERNAL LINKS ────────────────────────────────────────────────────
        let externalLinks = [];
        article.querySelectorAll('a[href]').forEach(el => {
            let href = el.getAttribute('href') || '';
            if (href.startsWith('http') && !href.includes('linkedin.com')) {
                externalLinks.push(href);
            }
        });
        externalLinks = Array.from(new Set(externalLinks));

        // Only skip if BOTH are missing
        if (!bodyText && !author) return;

        results.push({
            author:          author || 'Unknown',
            time:            timestamp || 'Unknown',
            main_link:       postLink || '',
            post_text:       bodyText,
            reactions:       { total: likeCount },
            comments_count:  commentCount,
            reposts_count:   repostCount,
            has_attachment:  hasAttachment,
            extracted_links: externalLinks
        });
    });

    if (!results.length) {
        return [{_info: 'No valid posts extracted after filtering'}];
    }

    return results;

} catch(err) {
    return [{ _error: err.toString(), _stack: err.stack }];
}
"""


def scrape_posts(driver, max_posts=None, max_scrolls=None, max_time_seconds=None,
                 output_filename=None, scraped_posts=None, seen_keys=None):
    """
    Scrolls down the current LinkedIn page and scrapes posts until ANY limit is met.
    """
    print(f"Starting to scrape posts. Limits - Posts: {max_posts}, Scrolls: {max_scrolls}, Time: {max_time_seconds}s")

    # Extra wait: LinkedIn is a heavy SPA — give it time to render React components.
    print("Waiting for LinkedIn feed to fully render...")
    time.sleep(get_human_delay(5.0, 7.0))

    start_time = time.time()
    scroll_count = 0
    if scraped_posts is None:
        scraped_posts = []
    if seen_keys is None:
        seen_keys = set()
    initial_count = len(scraped_posts)
    debug_done = False

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

        if max_time_seconds and elapsed_time > max_time_seconds:
            print(f"Time limit reached ({elapsed_time:.1f}s / {max_time_seconds}s). Stopping scrape.")
            break

        if max_scrolls is not None and scroll_count >= max_scrolls:
            print(f"Scroll limit reached ({scroll_count} / {max_scrolls}). Stopping scrape.")
            break

        # Dismiss LinkedIn popups / modals
        try:
            driver.execute_script("""
                document.querySelectorAll('button').forEach(b => {
                    let t = (b.textContent || '').trim();
                    if(['Dismiss','Not now','Maybe later','Skip','Close','Got it'].includes(t)) b.click();
                });
            """)
        except Exception:
            pass

        # == DOM DIAGNOSTICS (first scroll only) ==
        if not debug_done:
            try:
                debug_info = driver.execute_script(DEBUG_JS)
                diag_path = os.path.join(os.path.dirname(__file__), 'dom_diagnostics.json')
                with open(diag_path, 'w', encoding='utf-8') as f:
                    f.write(debug_info)
                parsed = json.loads(debug_info)
                print(f"[DOM Diagnostics] feedUpdateLinks: {parsed.get('feedUpdateLinkCount', 0)}, "
                      f"samples: {[s.get('text','')[:30] for s in parsed.get('sampleLinks',[])]}")
                print(f"[DOM Diagnostics] reactionAnchors: {[r.get('text','')[:50] for r in parsed.get('reactionAnchors',[])]}")
                print(f"[DOM Diagnostics] authorAnchors sample: {[a.get('text','')[:60] for a in parsed.get('authorAnchors',[])]}")
                print(f"[DOM Diagnostics] Full diagnostics saved to {diag_path}")
            except Exception as e:
                print(f"[DOM Diagnostics failed] {e}")
            debug_done = True

        # Expand "…more" / "see more" toggles
        try:
            driver.execute_script(r"""
                document.querySelectorAll('button').forEach(btn => {
                    let t = (btn.textContent || '').trim().toLowerCase();
                    if(t === 'see more' || t === '...more' || t === '\u2026more' ||
                       t === 'more' || t === '\u2026 more' || t === '… more') {
                        try { btn.click(); } catch(e) {}
                    }
                });
            """)
            time.sleep(0.6)
        except Exception:
            pass

        # Extract all visible posts atomically
        try:
            all_posts = driver.execute_script(EXTRACT_JS)

            if all_posts:
                new_this_scroll = 0
                for post_js in all_posts:
                    if '_error' in post_js:
                        print('JS Error:', post_js['_error'])
                        continue

                    if not post_js.get('post_text') and post_js.get('author') == 'Unknown':
                        continue

                    # Dedup by main_link, fallback to author+text slice
                    link = post_js.get('main_link', '')
                    if link:
                        if link in seen_keys:
                            continue
                        seen_keys.add(link)
                    else:
                        fallback_key = f"{post_js.get('author', '').strip()}_{post_js.get('post_text', '').strip().lower()[:80]}"
                        if fallback_key in seen_keys:
                            continue
                        seen_keys.add(fallback_key)

                    post_data = {"extracted_at": time.time()}
                    post_data.update(post_js)
                    scraped_posts.append(post_data)
                    new_this_scroll += 1

                    if max_posts and (len(scraped_posts) - initial_count) >= max_posts:
                        print(f"Post limit reached ({len(scraped_posts) - initial_count} / {max_posts}). Stopping scrape.")
                        save_json()
                        return scraped_posts

                if new_this_scroll > 0:
                    print(f"  -> Found {new_this_scroll} new posts this scroll")

        except Exception as e:
            print(f"Encountered an issue parsing posts: {e}")

        print(f"Scrolling down... (Scroll {scroll_count + 1})  [collected {len(scraped_posts)} posts so far]")
        # Scroll multiple viewport heights to trigger LinkedIn's lazy-loading
        driver.execute_script("window.scrollBy(0, window.innerHeight * 2);")
        scroll_count += 1
        time.sleep(get_human_delay(2.5, 4.5))

    print(f"Scraping finished. Collected {len(scraped_posts)} posts.")
    save_json()
    return scraped_posts


def navigate_to_page(driver, url):
    """Navigates to a specific LinkedIn page, profile, or company."""
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
    """Orchestrates navigation and scraping for one target LinkedIn URL."""
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