import os # Add os import
from fastapi import FastAPI
import httpx # Re-add httpx
# Remove BeautifulSoup import
import uvicorn
from datetime import datetime, timedelta
from dotenv import load_dotenv # Add dotenv import

load_dotenv() # Load environment variables from .env file

app = FastAPI()

# Simple in-memory cache with expiration
cache = {}
CACHE_DURATION = timedelta(hours=4)

# Define SerpApi base URL
SERPAPI_BASE_URL = "https://serpapi.com/search.json"

async def get_citation_number(user_id: str):
    # Check cache first
    now = datetime.now()
    if user_id in cache:
        cached_result, timestamp = cache[user_id]
        if now - timestamp < CACHE_DURATION:
            print(f"Returning cached result for user: {user_id}")
            # Ensure cached result is a dict with 'status'
            if isinstance(cached_result, dict) and 'status' in cached_result:
                return cached_result
            else:
                # Clear invalid cache entry
                print(f"Invalid cache format for user: {user_id}, refetching...")
                del cache[user_id]
        else:
            print(f"Cache expired for user: {user_id}")
            del cache[user_id]

    # Get API key from environment variable
    api_key = os.getenv("SERPAPI_API_KEY")
    if not api_key:
        print("ERROR: SERPAPI_API_KEY environment variable not set.")
        # Return an error immediately, don't cache this config issue
        return {"status": "error", "value": "Server Configuration Error"}

    print(f"Fetching new result for user: {user_id} using SerpApi")
    params = {
        "engine": "google_scholar_author",
        "author_id": user_id,
        "api_key": api_key,
        "hl": "en", # Keep language consistency
    }

    async with httpx.AsyncClient(timeout=20.0) as client: # Increased timeout slightly
        try:
            response = await client.get(SERPAPI_BASE_URL, params=params)
            print(f"Request to SerpApi for {user_id} completed with status code: {response.status_code}")
            response.raise_for_status() # Raise exception for 4xx/5xx status codes
            data = response.json()

            # Check for SerpApi-level errors first
            if "error" in data:
                 error_message = data["error"]
                 print(f"SerpApi returned an error for user {user_id}: {error_message}")
                 result = {"status": "error", "value": f"SerpApi Error: {error_message}"}
                 # Cache SerpApi errors as they might be persistent (e.g., invalid key)
                 cache[user_id] = (result, now)
                 return result

            # Extract citation count - Structure based on SerpApi Google Scholar Author docs
            # Look in 'cited_by' first, then potentially 'author_results' or similar if needed
            cited_by_info = data.get('cited_by')
            if cited_by_info and 'value' in cited_by_info:
                 citation_count = cited_by_info['value']
                 print(f"Successfully parsed citation count: {citation_count} for user: {user_id} from SerpApi")
                 result = {"status": "success", "value": str(citation_count)} # Ensure value is string
                 cache[user_id] = (result, now)
                 return result
            # Fallback: Check if citation count is in the table structure (less common for author endpoint?)
            elif 'cited_by' in data and 'table' in data['cited_by']:
                for item in data['cited_by']['table']:
                    if 'citations' in item and 'all' in item['citations']:
                        citation_count = item['citations']['all']
                        print(f"Successfully parsed citation count from table: {citation_count} for user: {user_id}")
                        result = {"status": "success", "value": str(citation_count)}
                        cache[user_id] = (result, now)
                        return result

            # If no citation count found in expected places
            print(f"Could not find citation count in SerpApi response for user: {user_id}. Response keys: {list(data.keys())}")
            result = {"status": "not_found", "value": None}
            cache[user_id] = (result, now)
            return result

        except httpx.RequestError as exc:
            print(f"An HTTP Request error occurred while contacting SerpApi for {user_id}: {exc}")
            result = {"status": "error", "value": "Network Error"}
            # Don't cache temporary network errors aggressively
            # cache[user_id] = (result, now) # Optional: Cache network errors
            return result
        except httpx.HTTPStatusError as exc:
            print(f"HTTP Status error {exc.response.status_code} while contacting SerpApi for {user_id}: {exc.response.text[:200]}...")
            error_value = f"API Error {exc.response.status_code}"
            # Check if the error might be due to invalid API key or usage limits
            if exc.response.status_code == 401 or exc.response.status_code == 403:
                 error_value = "Authentication Error" # More specific message
            elif exc.response.status_code == 429:
                 error_value = "Rate Limit Exceeded"
            result = {"status": "error", "value": error_value}
            # Cache API status errors as they might persist
            cache[user_id] = (result, now)
            return result
        except Exception as e: # Catch unexpected errors during processing
            print(f"An unexpected error occurred processing SerpApi response for {user_id}: {e}")
            result = {"status": "error", "value": "Processing Error"}
            # Cache unexpected errors cautiously
            cache[user_id] = (result, now)
            return result

@app.get("/citations")
async def get_citations(user: str):
    result_data = await get_citation_number(user)
    status = result_data.get("status", "error") # Default to error if status key is missing
    value = result_data.get("value")

    print(f"API received status: {status}, value: {repr(value)} for user {user}")

    message_value = "Error" # Default message
    color = "red" # Default color for shields.io badge

    if status == "success":
        try:
            # Ensure value is a string representation of an integer
            citations = int(value)
            message_value = str(citations)
            color = "brightgreen" # Green for success
        except (ValueError, TypeError):
            print(f"Could not convert successful value '{value}' to int for user {user}. Defaulting to 'Error'.")
            message_value = "Error" # Fallback if conversion fails
            color = "red"
    elif status == "not_found":
        message_value = "Not found"
        color = "yellow" # Yellow for not found
    elif status == "error":
        # Use the specific error value if available, otherwise generic 'Error'
        message_value = value if value else "Error"
        color = "red"
    # Removed 'captcha' status as SerpApi handles retries/blocking differently; map to 'error' now.
    # Add other specific error statuses from get_citation_number if needed

    return {
        "schemaVersion": 1,
        "label": "Citations",
        "message": message_value,
        "color": color, # Added color parameter for shields.io
        "style": "social",
        "namedLogo": "Google Scholar"
    }

# Ensure this block works properly
if __name__ == '__main__':
    # Get port from environment variable or default to 8080
    port = int(os.getenv("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port) # Use host/port suitable for deployment
