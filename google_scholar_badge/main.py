from fastapi import FastAPI
import httpx
from bs4 import BeautifulSoup
import uvicorn  # For running the server
from datetime import datetime, timedelta

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
            # Ensure cached result is in the new dictionary format
            if isinstance(cached_result, dict) and 'status' in cached_result:
                return cached_result
            else:
                # Adapt old cache format if necessary (or just refetch)
                print("Old cache format detected, refetching...")
                # Fall through to fetch new data
        else:
            print(f"Cache expired for user: {user_id}")
            del cache[user_id]

    print(f"Fetching new result for user: {user_id}")
    url = f"https://scholar.google.com/citations?user={user_id}&hl=en"
    async with httpx.AsyncClient(timeout=10.0) as client:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.google.com/'
        }
        try:
            response = await client.get(url, headers=headers, follow_redirects=True)
            print(f"Request to {url} completed with status code: {response.status_code}")
            response.raise_for_status()
        except httpx.RequestError as exc:
            print(f"An error occurred while requesting {exc.request.url!r}: {exc}")
            result = {"status": "error", "value": "Request Error"}
            cache[user_id] = (result, now) # Cache error state briefly?
            return result
        except httpx.HTTPStatusError as exc:
            print(f"Error response {exc.response.status_code} while requesting {exc.request.url!r}: {exc.response.text[:200]}...")
            result = {"status": "error", "value": f"HTTP {exc.response.status_code}"}
            cache[user_id] = (result, now)
            return result

        html_snippet = response.text[:500]
        soup = BeautifulSoup(response.text, 'html.parser')

        # Check for CAPTCHA
        if soup.find("div", class_="g-recaptcha"):
            print(f"CAPTCHA detected for user: {user_id}")
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
            # Ensure value is treated as string for the badge
            message_value = str(int(value)) # Validate as int first, then convert to string
        except (ValueError, TypeError):
            print(f"Could not convert successful value '{value}' to int/str for user {user}. Defaulting to \"Error\".")
            message_value = "Error" # Or maybe "Parse Error"?
    elif status == "captcha":
        message_value = "Blocked by CAPTCHA"
    elif status == "not_found":
        message_value = "Not found" # Or default to "0"?
    elif status == "error":
        message_value = value if value else "Error" # Use specific HTTP error if available

    # Override message to "0" if specific errors should just show 0?
    # Decision: Let's be informative for now.
    # if status in ["captcha", "not_found", "error"]:
    #     message_value = "0"

    return {
        "schemaVersion": 1,
        "label": "Citations",
        "message": message_value, # The informative message or count
        "style": "social", # Maybe change style based on status later?
        "namedLogo": "Google Scholar"
    }

# Ensure this block works properly
if __name__ == '__main__':
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
