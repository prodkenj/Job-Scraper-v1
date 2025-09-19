# LinkedIn → Airtable Job Scraper (AgentQL + Playwright)

Scrapes LinkedIn job postings (e.g., “Data Analyst”) and saves structured records to **Airtable**—including full descriptions and extracted qualifications—using **Playwright** for navigation and **AgentQL** for resilient element queries.

> Use responsibly and lawfully. Review LinkedIn’s Terms of Service before scraping. Rotate any credentials or API keys if they were ever committed.

---

## Features
- **One-time login** with session reuse (`linkedin_login.json`) to avoid repeated sign-ins.
- **AgentQL-powered selectors** for robust DOM querying across LinkedIn UI changes.
- **Full-job-description capture** via auto-scrolling the description container.
- **Qualification extraction** from text (Minimum / Preferred Qualifications, Requirements) using regex.
- **Airtable integration**: pushes each job as a record with title, org, location, date, salary (if present), description, and qualifications.
- **Pagination support** that clicks the next numbered page until results end.

---

## How it works (flow)
1. **Auth** → Launch Chromium, go to LinkedIn login, enter creds, save storage state.
2. **Search** → Go to Jobs, fill query (default: “Data Analyst”), submit.
3. **Iterate** → Click each listing, wait for details card, scrape metadata + description.
4. **Parse** → Extract “Minimum/Preferred Qualifications” or “Requirements” sections when present.
5. **Persist** → Create Airtable records for each job.
6. **Paginate** → Move to the next results page until none remain.

---

## Requirements
- Python 3.10+ recommended
- A free LinkedIn account you own
- Airtable base with an API key
- AgentQL API key

**Install system/browser deps**
```bash
pip install -r requirements.txt     # (see suggested list below)
python -m playwright install        # installs the Chromium browser for Playwright
