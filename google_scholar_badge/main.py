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
        data, timestamp = cache[user_id]
        if now - timestamp < CACHE_DURATION:
            print(f"Returning cached result for user: {user_id}")
            return data
        else:
            # Cache expired, remove entry
            print(f"Cache expired for user: {user_id}")
            del cache[user_id]

    # If not in cache or expired, fetch from Google Scholar
    print(f"Fetching new result for user: {user_id}")
    url = f"https://scholar.google.com/citations?user={user_id}"
    async with httpx.AsyncClient(timeout=10.0) as client: # Added timeout
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.google.com/'
        }
        try:
            response = await client.get(url, headers=headers, follow_redirects=True)
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        except httpx.RequestError as exc:
            print(f"An error occurred while requesting {exc.request.url!r}: {exc}")
            return None # Or handle error appropriately
        except httpx.HTTPStatusError as exc:
            print(f"Error response {exc.response.status_code} while requesting {exc.request.url!r}: {exc.response.text}")
            return None # Or handle error appropriately

        soup = BeautifulSoup(response.text, 'html.parser')

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
                        # Update cache
                        cache[user_id] = (citation_count, now)
                        return citation_count
        return None # Return None if not found


@app.get("/citations")
async def get_citations(user: str):
    citation_count = await get_citation_number(user)
    print(f"Raw citation_count for user {user}: {repr(citation_count)}") # Log the raw value

    message_value = "0" # Default to string "0"
    if citation_count:
        try:
            # Try converting to int first to validate it's numeric
            numeric_value = int(citation_count)
            message_value = str(numeric_value) # Convert back to string for the response
        except (ValueError, TypeError):
            print(f"Could not convert citation count '{citation_count}' to integer for user {user}. Defaulting to \"0\".")
            message_value = "0" # Ensure it's string "0" if conversion fails

    return {
        "schemaVersion": 1,
        "label": "Citations",
        "message": message_value, # Ensure message is always a string
        "style": "social",
        "namedLogo": "Google Scholar"
    }

# Ensure this block works properly
if __name__ == '__main__':
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
