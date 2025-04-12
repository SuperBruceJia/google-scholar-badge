from fastapi import FastAPI
from bs4 import BeautifulSoup
import uvicorn  # For running the server
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
import asyncio # Needed for playwright execution

app = FastAPI()

# Simple in-memory cache with expiration
cache = {}
CACHE_DURATION = timedelta(hours=4) # Cache results for 4 hours

async def get_citation_number(user_id: str):
    # Check cache first
    now = datetime.now()
    if user_id in cache:
        cached_result, timestamp = cache[user_id]
        if now - timestamp < CACHE_DURATION:
            print(f"Returning cached result for user: {user_id}")
            if isinstance(cached_result, dict) and 'status' in cached_result:
                return cached_result
            else:
                print("Old cache format detected, refetching...")
        else:
            print(f"Cache expired for user: {user_id}")
            del cache[user_id]

    print(f"Fetching new result for user: {user_id} using Playwright")
    url = f"https://scholar.google.com/citations?user={user_id}&hl=en"
    html_content = None
    status_code = None

    try:
        async with async_playwright() as p:
            # Launch browser (consider chromium, firefox, or webkit)
            # Add '--no-sandbox' args for Linux environments like Vercel
            browser = await p.chromium.launch(args=['--no-sandbox', '--disable-setuid-sandbox'])
            page = await browser.new_page()

            # Set a realistic User-Agent
            await page.set_extra_http_headers({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            })

            print(f"Navigating to {url}")
            response = await page.goto(url, timeout=15000) # Increased timeout for browser rendering
            status_code = response.status if response else None
            print(f"Navigation completed with status code: {status_code}")

            if status_code != 200:
                 # Raise an error similar to httpx.raise_for_status()
                 raise Exception(f"HTTP Error {status_code}")

            # Wait briefly for dynamic content if necessary (optional)
            # await asyncio.sleep(1)

            html_content = await page.content()
            await browser.close()

    except Exception as exc:
        print(f"An error occurred during Playwright operation: {exc}")
        result = {"status": "error", "value": f"Playwright Error: {str(exc)[:100]}"}
        cache[user_id] = (result, now)
        return result

    if not html_content:
        print("Failed to retrieve HTML content using Playwright.")
        result = {"status": "error", "value": "No HTML Content"}
        cache[user_id] = (result, now)
        return result

    html_snippet = html_content[:500]
    soup = BeautifulSoup(html_content, 'html.parser')

    # Check for CAPTCHA
    if soup.find("div", class_="g-recaptcha") or "Sorry..." in soup.title.string:
        print(f"CAPTCHA or block page detected for user: {user_id}")
        result = {"status": "captcha", "value": None}
        cache[user_id] = (result, now)
        return result

    # Find the stats table by its ID
    stats_table = soup.find('table', {'id': 'gsc_rsb_st'})
    if stats_table:
        citations_label = stats_table.find(lambda tag: tag.name == 'a' and 'citations' in tag.get('href', '').lower())
        if citations_label:
            row = citations_label.find_parent('tr')
            if row:
                citation_element = row.find('td', {'class': 'gsc_rsb_std'})
                if citation_element:
                    citation_count = citation_element.text.strip()
                    print(f"Successfully parsed citation count: {citation_count} for user: {user_id}")
                    result = {"status": "success", "value": citation_count}
                    cache[user_id] = (result, now)
                    return result

    # If parsing fails or element not found
    print(f"Could not find citation element for user: {user_id}. HTML snippet: {html_snippet}")
    result = {"status": "not_found", "value": None}
    cache[user_id] = (result, now)
    return result

@app.get("/citations")
async def get_citations(user: str):
    result_data = await get_citation_number(user)
    status = result_data.get("status", "error")
    value = result_data.get("value")

    print(f"API received status: {status}, value: {repr(value)} for user {user}")

    message_value = "Error"
    if status == "success":
        try:
            message_value = str(int(value))
        except (ValueError, TypeError):
            print(f"Could not convert successful value '{value}' to int/str for user {user}. Defaulting to \"Error\".")
            message_value = "Error"
    elif status == "captcha":
        message_value = "Blocked by CAPTCHA"
    elif status == "not_found":
        message_value = "Not found"
    elif status == "error":
        message_value = value if value else "Error"

    return {
        "schemaVersion": 1,
        "label": "Citations",
        "message": message_value,
        "style": "social",
        "namedLogo": "Google Scholar"
    }

# Ensure this block works properly
if __name__ == '__main__':
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
