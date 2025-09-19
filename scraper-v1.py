import os
import re
import agentql
from playwright.sync_api import sync_playwright
from pyairtable import Api
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# User credentials and API keys
USER_NAME = os.getenv('EMAIL')
PASSWORD = os.getenv('PASSWORD')
os.environ["AGENTQL_API_KEY"] = os.getenv('AGENTQL_API_KEY')

AIRTABLE_API_KEY = os.getenv('AIRTABLE_API_KEY')
AIRTABLE_BASE_ID = os.getenv('AIRTABLE_BASE_ID')
AIRTABLE_TABLE_NAME = os.getenv('AIRTABLE_TABLE_NAME')

"""
LinkedIn Job Scraper
-------------------
This script automates the process of scraping job listings from LinkedIn and storing them in Airtable.
The process follows these main steps:

1. Authentication:
   - Logs into LinkedIn using provided credentials
   - Saves browser state to avoid future logins
   
2. Job Search:
   - Navigates to LinkedIn jobs page
   - Searches for "Data Analyst" positions
   
3. Data Collection (per page):
   - Iterates through job listings
   - Extracts job details (title, company, location, etc.)
   - Scrapes full job descriptions
   - Extracts qualification requirements
   
4. Data Storage:
   - Pushes collected job data to Airtable
"""

def login():
    """
    Handles LinkedIn authentication process using Playwright and AgentQL.
    
    The function:
    1. Launches a browser window
    2. Navigates to LinkedIn login page
    3. Fills in credentials using AgentQL queries
    4. Saves authentication state for future use
    """
    print("[LOGIN] Starting LinkedIn login process...")
    INITIAL_URL = "https://www.linkedin.com/login?fromSignIn=true&trk=guest_homepage-basic_nav-header-signin"
    EMAIL_INPUT_QUERY = """
    {
        login_form {
            email_input
            password_input
            sign_in_button
        }
    }
    """
    PASSWORD_INPUT_QUERY = """
    {
        login_form {
            password_input
        }
    }
    """
    with sync_playwright() as playwright, playwright.chromium.launch(headless=False) as browser:
        print("[LOGIN] Browser launched, opening a new page...")
        page = agentql.wrap(browser.new_page())
        print(f"[LOGIN] Navigating to {INITIAL_URL}")
        page.goto(INITIAL_URL)
        print("[LOGIN] Querying email input field...")
        response = page.query_elements(EMAIL_INPUT_QUERY)
        print("[LOGIN] Filling in email...")
        response.login_form.email_input.fill(USER_NAME)
        page.wait_for_timeout(300)  # Reduced from 500ms
        print("[LOGIN] Querying password input field...")
        password_response = page.query_elements(PASSWORD_INPUT_QUERY)
        print("[LOGIN] Filling in password...")
        password_response.login_form.password_input.fill(PASSWORD)
        page.wait_for_timeout(300)  # Reduced from 500ms
        print("[LOGIN] Clicking sign in button...")
        response.login_form.sign_in_button.click()
        print("[LOGIN] Waiting for page to load after login...")
        page.wait_for_page_ready_state()
        print("[LOGIN] Saving browser storage state to 'linkedin_login.json'")
        browser.contexts[0].storage_state(path="linkedin_login.json")

def push_to_airtable(job_posts_data):
    """
    Stores scraped job listings in Airtable.
    
    Args:
        job_posts_data (list): List of dictionaries containing job posting information
        
    Each job post contains:
    - org_name: Company name
    - job_title: Position title
    - salary: Compensation information (if available)
    - location: Job location
    - date_posted: Posting date
    - job_description: Full job description
    - qualifications: Extracted qualification requirements
    """
    print("[AIRTABLE] Preparing to push job posts data to Airtable...")
    airtable = Api(AIRTABLE_API_KEY)
    table = airtable.table(AIRTABLE_BASE_ID, AIRTABLE_TABLE_NAME)
    for job in job_posts_data:
        if job.get("salary") is not None and not isinstance(job.get("salary"), str):
            job["salary"] = str(job["salary"])
        print(f"[AIRTABLE] Pushing record: {job}")
        table.create(job)
    print(f"[AIRTABLE] Finished pushing {len(job_posts_data)} records to Airtable.")

def scroll_description_container(page, container_selector):
    """
    Ensures complete job description loading by scrolling the container.
    
    Args:
        page: Playwright page object
        container_selector (str): CSS selector for the description container
        
    The function scrolls in increments and checks for content changes to ensure
    all dynamic content is loaded before extraction.
    """
    print("[SCROLL-DESCRIPTION] Scrolling the job description container...")
    last_height = page.evaluate(f"() => document.querySelector('{container_selector}').scrollHeight")
    no_change_counter = 0
    scroll_increment = 200
    while True:
        page.evaluate(f"() => document.querySelector('{container_selector}').scrollBy(0, {scroll_increment})")
        page.wait_for_timeout(500)  # Reduced from 1000ms
        new_height = page.evaluate(f"() => document.querySelector('{container_selector}').scrollHeight")
        scroll_top = page.evaluate(f"() => document.querySelector('{container_selector}').scrollTop")
        print(f"[SCROLL-DESCRIPTION] scrollTop: {scroll_top} | New height: {new_height}")
        if new_height == last_height:
            no_change_counter += 1
        else:
            no_change_counter = 0
        if no_change_counter >= 3 or (scroll_top + scroll_increment >= new_height):
            print("[SCROLL-DESCRIPTION] Finished scrolling description container.")
            break
        last_height = new_height

def scrape_job_description(page):
    """
    Extracts the complete job description text from the current job listing.
    
    Args:
        page: Playwright page object
        
    Returns:
        str: Complete job description text
        
    Process:
    1. Waits for description container to load
    2. Scrolls to ensure all content is visible
    3. Extracts and returns the full text
    """
    DESCRIPTION_CONTAINER_SELECTOR = "div.jobs-search__job-details--wrapper"
    print("[DESCRIPTION] Waiting for the job description container to load...")
    page.wait_for_selector(DESCRIPTION_CONTAINER_SELECTOR, timeout=10000)
    scroll_description_container(page, DESCRIPTION_CONTAINER_SELECTOR)
    job_description = page.inner_text(DESCRIPTION_CONTAINER_SELECTOR)
    print("[DESCRIPTION] Extracted job description text.")
    return job_description

def extract_qualifications_general(description_text):
    """
    Parses job description to extract qualification requirements.
    
    Args:
        description_text (str): Full job description
        
    Returns:
        str: Extracted qualifications text
        
    Looks for:
    1. Minimum qualifications
    2. Preferred qualifications
    3. General qualifications
    4. Requirements
    """
    min_match = re.search(
        r"Minimum Qualifications:\s*(.*?)\s*(?=(Preferred Qualifications:|$))",
        description_text, re.DOTALL | re.IGNORECASE
    )
    pref_match = re.search(
        r"Preferred Qualifications:\s*(.*)",
        description_text, re.DOTALL | re.IGNORECASE
    )
    if min_match or pref_match:
        minimum_quals = min_match.group(1).strip() if min_match else ""
        preferred_quals = pref_match.group(1).strip() if pref_match else ""
        combined = ""
        if minimum_quals:
            combined += "Minimum Qualifications:\n" + minimum_quals + "\n\n"
        if preferred_quals:
            combined += "Preferred Qualifications:\n" + preferred_quals
        return combined.strip()
    else:
        generic_match = re.search(
            r"Qualifications:\s*(.*)",
            description_text, re.DOTALL | re.IGNORECASE
        )
        if generic_match:
            return generic_match.group(1).strip()
        else:
            req_match = re.search(
                r"Requirements?:\s*(.*)",
                description_text, re.DOTALL | re.IGNORECASE
            )
            if req_match:
                return req_match.group(1).strip()
    return ""

def click_next_page(page):
    """
    Handles pagination in job search results.
    
    Args:
        page: Playwright page object
        
    Returns:
        bool: True if successfully moved to next page, False if no more pages
        
    Process:
    1. Identifies current page number
    2. Locates and clicks next page button
    3. Waits for new page to load
    """
    print("[PAGINATION] Attempting to click to the next page using numbered pagination...")
    try:
        current_page_button = page.query_selector("button[aria-current='true']")
        if current_page_button:
            current_page = int(current_page_button.inner_text().strip())
            next_page_number = current_page + 1
            print(f"[PAGINATION] Current page is {current_page}. Looking for button with text '{next_page_number}'.")
            next_page_button = page.query_selector(f"button:has-text('{next_page_number}')")
            if next_page_button:
                print("[PAGINATION] Next page button found. Clicking it...")
                next_page_button.click()
                page.wait_for_timeout(1500)  # Reduced from 3000ms
                return True
            else:
                print("[PAGINATION] Next page button not found. Possibly reached the last page.")
                return False
        else:
            print("[PAGINATION] Current page indicator not found. Trying to click button with text '2'.")
            next_page_button = page.query_selector("button:has-text('2')")
            if next_page_button:
                next_page_button.click()
                page.wait_for_timeout(1500)
                return True
            else:
                print("[PAGINATION] Button for page 2 not found. Ending pagination loop.")
                return False
    except Exception as e:
        print(f"[PAGINATION] Exception occurred while trying to click next page: {e}")
        return False

URL = "https://www.linkedin.com/jobs/"

def main():
    """
    Main execution function that orchestrates the scraping process.
    
    Process Flow:
    1. Browser Setup:
       - Launches browser
       - Handles authentication
       
    2. Search Initialization:
       - Navigates to jobs page
       - Enters search query
       
    3. Data Collection Loop:
       - Outer loop: Handles pagination
       - Inner loop: Processes individual job listings
       
    4. For Each Job:
       - Clicks listing
       - Extracts metadata
       - Scrapes description
       - Stores in Airtable
       
    5. Cleanup:
       - Closes browser when complete
    """
    print("[MAIN] Starting job scraping process...")
    JOB_PAGE_QUERY = """
    {
        search_jobs_form {
            search_input(attr="[aria-label='Search by title, skill, or company']")
        }
    }
    """
    JOB_POSTS_QUERY = """
    {
        job_details {
            org_name(selector=".job-details-jobs-unified-top-card__company-name")
            job_title(selector=".job-details-jobs-unified-top-card__job-title")
            salary(selector=".job-details-jobs-unified-top-card__salary")
            location(selector=".job-details-jobs-unified-top-card__primary-description")
            date_posted(selector=".job-details-jobs-unified-top-card__posted-date")
        }
    }
    """
    with sync_playwright() as playwright, playwright.chromium.launch(headless=False) as browser:
        if not os.path.exists("linkedin_login.json"):
            print("[MAIN] No login state found. Logging in...")
            login()
        else:
            print("[MAIN] Found existing login state. Using 'linkedin_login.json'.")
        print("[MAIN] Creating browser context with saved storage state...")
        context = browser.new_context(storage_state="linkedin_login.json")
        page = agentql.wrap(context.new_page())
        print(f"[MAIN] Navigating to jobs page: {URL}")
        page.goto(URL)
        print("[MAIN] Querying search input on the job page...")
        response = page.query_elements(JOB_PAGE_QUERY)
        print("[MAIN] Filling search input with 'Data Analyst'...")
        response.search_jobs_form.search_input.fill("Data Analyst")
        print("[MAIN] Pressing Enter to initiate the search...")
        response.search_jobs_form.search_input.press('Enter')
        print("[MAIN] Waiting for search results to load...")
        page.wait_for_timeout(2000)  # Reduced from 3000ms
        
        JOB_LISTINGS_CONTAINER = ".ezZPeqioPHkZBgdJkFjeFSVWOCuBIof"
        JOB_LISTING_ITEM_SELECTOR = f"{JOB_LISTINGS_CONTAINER} li"
        while True:  # Outer loop for pagination
            last_listing = None
            while True:  # Inner loop for job listings on current page
                if last_listing is None:
                    listing = page.query_selector(JOB_LISTING_ITEM_SELECTOR)
                    if not listing:
                        print("[MAIN] No job listings found. Breaking inner loop.")
                        break
                else:
                    next_listing_handle = last_listing.evaluate_handle("el => el.nextElementSibling")
                    listing = next_listing_handle.as_element() if next_listing_handle else None
                    if not listing:
                        print("[MAIN] Reached end of current listings, scrolling container for more...")
                        page.evaluate(f"() => document.querySelector('{JOB_LISTINGS_CONTAINER}').scrollBy(0, 300)")
                        page.wait_for_timeout(1000)  # Reduced from 2000ms
                        next_listing_handle = last_listing.evaluate_handle("el => el.nextElementSibling")
                        listing = next_listing_handle.as_element() if next_listing_handle else None
                        if not listing:
                            print("[MAIN] No further listings found after scrolling. Ending loop.")
                            break

                print("[MAIN] Clicking on the next job listing...")
                listing.click()
                page.wait_for_timeout(1000)  # Reduced from 2000ms

                # Updated selectors and added more robust waiting logic
                try:
                    # Reduced timeouts
                    details_card = page.wait_for_selector(
                        ".job-details-jobs-unified-top-card, .jobs-unified-top-card, .jobs-search__job-details",
                        timeout=5000  # Reduced from 10000ms
                    )
                    if not details_card:
                        print("[MAIN] Warning: Could not find job details card. Skipping listing.")
                        continue

                    # Reduced timeouts
                    title_element = page.wait_for_selector(
                        ".job-details-jobs-unified-top-card__job-title, h2[class*='job-title']",
                        timeout=3000  # Reduced from 5000ms
                    )
                    if not title_element:
                        print("[MAIN] Warning: Could not find job title. Skipping listing.")
                        continue

                except Exception as e:
                    print(f"[MAIN] Error waiting for job details: {e}")
                    continue
                
                # Add debug logging
                print("[MAIN] Successfully found job details card and title. Extracting data...")
                
                # Add retry logic for job metadata extraction
                max_retries = 3
                retry_count = 0
                while retry_count < max_retries:
                    try:
                        job_metadata_response = page.query_data(JOB_POSTS_QUERY)
                        break
                    except Exception as e:
                        retry_count += 1
                        print(f"[MAIN] Attempt {retry_count} failed: {e}")
                        if retry_count == max_retries:
                            print("[MAIN] Max retries reached, skipping this listing")
                            continue
                        page.wait_for_timeout(2000)  # Wait 2 seconds before retrying
                
                job = {}
                if job_metadata_response.get('job_details'):
                    job = job_metadata_response['job_details']
                    print(f"[MAIN] Extracted job metadata: {job}")
                else:
                    print("[MAIN] Warning: No job metadata returned after clicking the listing.")
                
                job_description = scrape_job_description(page)
                job['job_description'] = job_description
                job['qualifications'] = extract_qualifications_general(job_description)
                push_to_airtable([job])
                page.wait_for_timeout(300)  # Reduced from 500ms
                
                last_listing = listing

            # After processing all listings on current page, try moving to next page
            if click_next_page(page):
                print("[MAIN] Successfully moved to next page. Continuing to scrape...")
                page.wait_for_timeout(2000)  # Wait for new page to load
                continue  # Continue outer loop to process next page
            else:
                print("[MAIN] No more pages available. Ending scraping process.")
                break  # Break outer loop when no more pages

        print("[MAIN] Closing the page...")
        page.close()

if __name__ == "__main__":
    main()
