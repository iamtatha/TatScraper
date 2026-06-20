import time
import os
import json
from utils import get_human_delay
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ─────────────────────────────────────────────────
#  JS Payload to extract the current selected job
#  from the right pane.
# ─────────────────────────────────────────────────
EXTRACT_JOB_JS = r"""
try {
    let result = {};
    
    // The right pane container
    let detailsContainer = document.querySelector('.jobs-search__job-details--container, .job-details');
    if (!detailsContainer) detailsContainer = document.body; // Fallback to whole page
    
    // Role / Title
    let titleEl = detailsContainer.querySelector('h2, .job-details-jobs-unified-top-card__job-title, h1');
    if (titleEl) result.role = titleEl.textContent.trim();
    
    // Company
    let companyEl = document.querySelector('.job-details-jobs-unified-top-card__company-name, .jobs-unified-top-card__company-name, a[href*="/company/"] span');
    if (companyEl) {result.company = companyEl.textContent.trim();}
    
    // Location & Posting Time (often in primary description)
    let metaEls = document.querySelectorAll('.job-details-jobs-unified-top-card__primary-description-container .tvm__text');
    let metaTexts = Array.from(metaEls).map(el => el.textContent.trim()).filter(t => t && t !== '·');

    metaTexts.forEach(text => {
    if (text.includes('ago')) {
        result.posted = text;
    } else if (text.toLowerCase().includes('apply')) {
        result.applicants = text;
    } else if (
        text.includes('India') || 
        text.includes(',')   // fallback for location
    ) {
        result.location = text;
    }
    });
    
    // Description
    let descEl = detailsContainer.querySelector('.jobs-description-content__text, article');
    if (descEl) result.description = descEl.textContent.trim();
    
    // Link
    let applyLinkEl = detailsContainer.querySelector('a.jobs-apply-button, a[href*="/jobs/view/"]');
    if (applyLinkEl) result.link = applyLinkEl.getAttribute('href');
    
    // Fallback for getting link from current URL if it's a job view
    if (window.location.href.includes('/jobs/view/')) {
        result.link = window.location.href.split('?')[0];
    }
    
    // Cleanup spacing in description
    if (result.description) {
        result.description = result.description.replace(/\n\s*\n/g, '\n\n');
    }
    
    return result;
} catch(err) {
    return {_error: err.toString()};
}
"""

def scrape_jobs(driver, max_jobs=None, max_scrolls=None, max_time_seconds=None,
                 output_filename=None, scraped_jobs=None, seen_keys=None):
    """
    Scrolls the job list and clicks each job to extract details from the right pane.
    """
    print(f"Starting to scrape jobs. Limits - Jobs: {max_jobs}, Scrolls: {max_scrolls}, Time: {max_time_seconds}s")

    print("Waiting for LinkedIn jobs feed to fully render...")
    time.sleep(get_human_delay(5.0, 7.0))

    start_time = time.time()
    scroll_count = 0
    if scraped_jobs is None:
        scraped_jobs = []
    if seen_keys is None:
        seen_keys = set()
    initial_count = len(scraped_jobs)
    no_new_jobs_count = 0

    def save_json():
        if output_filename and scraped_jobs:
            try:
                out_dir = os.path.dirname(output_filename)
                if out_dir and not os.path.exists(out_dir):
                    os.makedirs(out_dir)
                with open(output_filename, 'w', encoding='utf-8') as f:
                    json.dump(scraped_jobs, f, indent=4, ensure_ascii=False)
                print(f"\n[{len(scraped_jobs)} jobs successfully saved to '{output_filename}']")
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

        # Dismiss popups
        try:
            driver.execute_script("""
                document.querySelectorAll('button').forEach(b => {
                    let t = (b.textContent || '').trim();
                    if(['Dismiss','Not now','Maybe later','Skip','Close','Got it'].includes(t)) b.click();
                });
            """)
        except Exception:
            pass

        # Find all job cards in the current list
        try:
            # We execute JS to get all job IDs and click them one by one
            job_elements = driver.execute_script(r"""
                let jobs = [];
                document.querySelectorAll('li.jobs-search-results__list-item, div[data-job-id]').forEach((el, index) => {
                    let id = el.getAttribute('data-job-id') || el.getAttribute('data-occludable-job-id');
                    if (id) {
                        jobs.push({id: id, index: index});
                    }
                });
                return jobs;
            """)
            
            if not job_elements:
                print("No job elements found. Might be end of list or layout changed.")
                break

            new_this_scroll = 0
            
            for job in job_elements:
                job_id = job['id']
                
                if job_id in seen_keys:
                    continue
                    
                seen_keys.add(job_id)
                
                # Click the job card
                try:
                    driver.execute_script(f"""
                        let el = document.querySelector('div[data-job-id="{job_id}"], li[data-occludable-job-id="{job_id}"]');
                        if (el) {{
                            let clickable = el.querySelector('a') || el;
                            clickable.click();
                        }}
                    """)
                    
                    # Wait for right pane to load
                    time.sleep(get_human_delay(2.0, 3.5))
                    
                    # Click "See more" if present in description
                    driver.execute_script(r"""
                        let btn = document.querySelector('.jobs-description__footer-button, button[aria-label*="Click to see more"]');
                        if (btn) btn.click();
                    """)
                    time.sleep(0.5)
                    
                    # Extract job details
                    job_data = driver.execute_script(EXTRACT_JOB_JS)
                    
                    if job_data and not job_data.get('_error'):
                        job_data['job_id'] = job_id
                        job_data['extracted_at'] = time.time()
                        
                        # Fix missing link
                        if not job_data.get('link'):
                            job_data['link'] = f"https://www.linkedin.com/jobs/view/{job_id}/"
                            
                        scraped_jobs.append(job_data)
                        new_this_scroll += 1
                        
                        if max_jobs and (len(scraped_jobs) - initial_count) >= max_jobs:
                            print(f"Job limit reached ({len(scraped_jobs) - initial_count} / {max_jobs}). Stopping scrape.")
                            save_json()
                            return scraped_jobs
                            
                except Exception as e:
                    print(f"Error processing job {job_id}: {e}")
                    
            if new_this_scroll > 0:
                print(f"  -> Found {new_this_scroll} new jobs this scroll")
                no_new_jobs_count = 0
            else:
                no_new_jobs_count += 1
                
        except Exception as e:
            print(f"Encountered an issue listing jobs: {e}")

        if no_new_jobs_count >= 3:
            print("No new jobs found after scrolling. Trying next page...")
            clicked_next = driver.execute_script(r"""
                let nextBtn = document.querySelector('button[aria-label="View next page"]');
                if (nextBtn && !nextBtn.disabled) {
                    nextBtn.click();
                    return true;
                }
                
                let activePage = document.querySelector('li.artdeco-pagination__indicator--active');
                if (activePage && activePage.nextElementSibling) {
                    let btn = activePage.nextElementSibling.querySelector('button');
                    if (btn) {
                        btn.click();
                        return true;
                    }
                }
                return false;
            """)
            
            if clicked_next:
                print("Clicked next page. Waiting for jobs to load...")
                time.sleep(get_human_delay(4.0, 6.0))
                no_new_jobs_count = 0
                continue
            else:
                print("No more pages or jobs found. Ending scrape.")
                break

        print(f"Scrolling down list... (Scroll {scroll_count + 1})  [collected {len(scraped_jobs)} jobs so far]")
        
        # Scroll the left pane (job list)
        driver.execute_script(r"""
            let list = document.querySelector('.jobs-search-results-list, .scaffold-layout__list');
            if (list) {
                list.scrollTop = list.scrollHeight;
                let items = list.querySelectorAll('li.jobs-search-results__list-item, div[data-job-id]');
                if (items.length > 0) {
                    items[items.length - 1].scrollIntoView({behavior: "smooth", block: "end"});
                }
            } else {
                window.scrollTo(0, document.body.scrollHeight);
            }
        """)
        
        scroll_count += 1
        time.sleep(get_human_delay(2.5, 4.5))

    print(f"Job scraping finished. Collected {len(scraped_jobs)} jobs.")
    save_json()
    return scraped_jobs


def navigate_to_page(driver, url):
    """Navigates to a specific LinkedIn page."""
    if not url.startswith("http"):
        url = "https://" + url
    print(f"Navigating to: {url}")
    driver.get(url)
    time.sleep(get_human_delay(4, 7))
    print("Navigation complete. Ready to scrape.")


def perform_job_scraping(
    driver,
    target_url=None,
    export_path=None,
    max_jobs=10,
    max_scrolls=20,
    max_time_seconds=300,
    scraped_jobs=None,
    seen_keys=None,
):
    """Orchestrates navigation and scraping for LinkedIn jobs."""
    print(f"\n--- Starting job scraping workflow for {target_url} ---")

    if target_url:
        navigate_to_page(driver, target_url)

    jobs = scrape_jobs(
        driver=driver,
        max_jobs=max_jobs,
        max_scrolls=max_scrolls,
        max_time_seconds=max_time_seconds,
        output_filename=export_path,
        scraped_jobs=scraped_jobs,
        seen_keys=seen_keys,
    )

    print(f"\n--- Workflow complete: {len(jobs)} jobs saved to {export_path} ---")
    for idx, j in enumerate(jobs, 1):
        title = j.get('role', 'Unknown Role')
        company = j.get('company', 'Unknown Company')
        print(f"  [{idx}] {title} @ {company}")
