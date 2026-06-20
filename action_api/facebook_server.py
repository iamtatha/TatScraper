from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from facebook_core import fb_agent
import uvicorn

app = FastAPI(
    title="Facebook Agent Action API",
    description="An API exposing Facebook scraping and browser actions for an Agentic System.",
    version="1.0.0"
)

# --- Pydantic Models ---

class ScrapeRequest(BaseModel):
    max_posts: int = 10
    max_scrolls: int = 10

class UrlScrapeRequest(ScrapeRequest):
    url: str

class SearchScrapeRequest(ScrapeRequest):
    query: str

class ClickRequest(BaseModel):
    selector: Optional[str] = None
    text: Optional[str] = None

# --- Endpoints ---

@app.post("/api/init", tags=["System"])
def initialize_browser():
    """Starts the browser and logs into Facebook."""
    try:
        return fb_agent.initialize()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/close", tags=["System"])
def close_browser():
    """Closes the browser session."""
    return fb_agent.close()

@app.post("/api/scrape/home", tags=["Scraping"])
def scrape_home(req: ScrapeRequest):
    """Navigates to the Facebook home feed and scrapes posts."""
    try:
        return fb_agent.scrape_home(max_posts=req.max_posts, max_scrolls=req.max_scrolls)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/scrape/url", tags=["Scraping"])
def scrape_url(req: UrlScrapeRequest):
    """Navigates to a specific Facebook URL and scrapes posts."""
    try:
        return fb_agent.scrape_url(url=req.url, max_posts=req.max_posts, max_scrolls=req.max_scrolls)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/scrape/search", tags=["Scraping"])
def search_and_scrape(req: SearchScrapeRequest):
    """Searches Facebook for a string and scrapes the resulting posts."""
    try:
        return fb_agent.search_and_scrape(query=req.query, max_posts=req.max_posts, max_scrolls=req.max_scrolls)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/action/click", tags=["Interaction"])
def click_element(req: ClickRequest):
    """
    Clicks a button or link on the current page.
    Provide either a CSS `selector` or exact `text` matching the button.
    """
    if not req.selector and not req.text:
        raise HTTPException(status_code=400, detail="Must provide either 'selector' or 'text'")
    
    res = fb_agent.click_element(selector=req.selector, text=req.text)
    if res.get("status") == "error":
        raise HTTPException(status_code=500, detail=res.get("message"))
    return res

@app.get("/api/debug/dom", tags=["Debug"])
def debug_dom():
    """Dumps raw link/heading/time structure of first 2 articles for selector debugging."""
    if not fb_agent.driver:
        raise HTTPException(status_code=400, detail="Browser not initialized.")
    DEBUG_JS = r"""
    try {
        let articles = Array.from(document.querySelectorAll('div[aria-posinset]'));
        if (!articles.length) articles = Array.from(document.querySelectorAll('div[role="article"]'));
        if (!articles.length) return [{error: 'No articles found'}];
        let out = [];
        articles.slice(0, 2).forEach((article, idx) => {
            let links = [];
            article.querySelectorAll('a[href]').forEach(el => {
                links.push({
                    href: (el.getAttribute('href') || '').slice(0, 120),
                    innerText: (el.innerText || '').trim().slice(0, 60),
                    ariaLabel: (el.getAttribute('aria-label') || '').slice(0, 80),
                    title: (el.getAttribute('title') || '').slice(0, 80)
                });
            });
            let headings = [];
            article.querySelectorAll('h1,h2,h3,h4,h5,strong,b').forEach(el => {
                headings.push({ tag: el.tagName, text: (el.innerText || '').trim().slice(0, 80) });
            });
            let timeEls = [];
            article.querySelectorAll('abbr,[data-utime],time,[aria-label*="ago"],[aria-label*="hour"],[aria-label*="minute"],[aria-label*="day"]').forEach(el => {
                timeEls.push({
                    tag: el.tagName, selector: el.tagName.toLowerCase(),
                    innerText: (el.innerText || '').trim().slice(0, 40),
                    title: (el.getAttribute('title') || '').slice(0, 80),
                    ariaLabel: (el.getAttribute('aria-label') || '').slice(0, 80),
                    dataUtime: el.getAttribute('data-utime') || '',
                    datetime: el.getAttribute('datetime') || ''
                });
            });
            out.push({ article_index: idx, link_count: links.length, links: links.slice(0, 40), headings: headings, time_elements: timeEls });
        });
        return out;
    } catch(e) { return [{error: e.toString()}]; }
    """
    result = fb_agent.driver.execute_script(DEBUG_JS)
    return {"status": "success", "dom_debug": result}

if __name__ == "__main__":
    print("Starting Facebook Agent API Server...")
    uvicorn.run("facebook_server:app", host="127.0.0.1", port=8000, reload=True)
