import os # Add os import
from fastapi import FastAPI
import httpx # Re-add httpx
# Remove BeautifulSoup import
import uvicorn
from datetime import datetime, timedelta
from dotenv import load_dotenv # Add dotenv import
import redis.asyncio as redis # Add redis import
import json # Add json import

load_dotenv() # Load environment variables from .env file

app = FastAPI()

# --- Redis Initialization ---
REDIS_URL = os.getenv("REDIS_URL")
redis_client = None
if REDIS_URL:
    print("Connecting to Redis...")
    try:
        # Use from_url for easier configuration
        redis_client = redis.from_url(REDIS_URL, decode_responses=True) # Decode responses to strings
        # You might need specific SSL settings depending on your Redis provider
        # redis_client = redis.from_url(REDIS_URL, decode_responses=True, ssl_cert_reqs=None) # Example for disabling SSL verification if needed
    except Exception as e:
        print(f"Error connecting to Redis: {e}")
        redis_client = None # Ensure client is None if connection fails
else:
    print("REDIS_URL environment variable not set. Redis caching disabled.")

# Define SerpApi base URL
SERPAPI_BASE_URL = "https://serpapi.com/search.json"
REDIS_CACHE_TTL_SECONDS = 24 * 60 * 60 # 24 hours in seconds

async def get_citation_number(user_id: str):
    # --- Check Redis Cache ---
    if redis_client:
        try:
            cached_data_str = await redis_client.get(user_id)
            if cached_data_str:
                print(f"Returning cached result from Redis for user: {user_id}")
                cached_data = json.loads(cached_data_str) # Parse JSON string
                # Basic validation - could be more robust
                if isinstance(cached_data, dict) and 'status' in cached_data:
                     return cached_data
                else:
                    print(f"Invalid cache format in Redis for user: {user_id}, refetching...")
                    # Optionally delete invalid key: await redis_client.delete(user_id)
            else:
                 print(f"Cache miss in Redis for user: {user_id}")
        except redis.RedisError as e:
            print(f"Redis Error getting cache for {user_id}: {e}. Proceeding without cache.")
        except json.JSONDecodeError as e:
            print(f"Error decoding cached JSON for {user_id}: {e}. Refetching.")
            # Optionally delete invalid key: await redis_client.delete(user_id)
    else:
        # If Redis client isn't initialized, skip caching logic
        pass

    # --- Fetch from SerpApi (if not cached or Redis unavailable) ---
    api_key = os.getenv("SERPAPI_API_KEY")
    if not api_key:
        print("ERROR: SERPAPI_API_KEY environment variable not set.")
        return {"status": "error", "value": "Server Configuration Error"}

    print(f"Fetching new result for user: {user_id} using SerpApi")
    params = {
        "engine": "google_scholar_author",
        "author_id": user_id,
        "api_key": api_key,
        "hl": "en",
    }

    result = {"status": "error", "value": "Unknown Fetch Error"} # Default result

    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            response = await client.get(SERPAPI_BASE_URL, params=params)
            print(f"Request to SerpApi for {user_id} completed with status code: {response.status_code}")
            response.raise_for_status()
            data = response.json()

            if "error" in data:
                 error_message = data["error"]
                 print(f"SerpApi returned an error for user {user_id}: {error_message}")
                 result = {"status": "error", "value": f"SerpApi Error: {error_message}"}

            else:
                cited_by_info = data.get('cited_by')
                citation_count = None
                if cited_by_info and 'value' in cited_by_info:
                     citation_count = cited_by_info['value']
                     print(f"Successfully parsed citation count: {citation_count} for user: {user_id} from SerpApi")
                elif 'cited_by' in data and 'table' in data['cited_by']:
                    for item in data['cited_by']['table']:
                        if 'citations' in item and 'all' in item['citations']:
                            citation_count = item['citations']['all']
                            print(f"Successfully parsed citation count from table: {citation_count} for user: {user_id}")
                            break # Found it

                if citation_count is not None:
                    result = {"status": "success", "value": str(citation_count)}
                else:
                    print(f"Could not find citation count in SerpApi response for user: {user_id}. Response keys: {list(data.keys())}")
                    result = {"status": "not_found", "value": None}

        except httpx.RequestError as exc:
            print(f"An HTTP Request error occurred while contacting SerpApi for {user_id}: {exc}")
            result = {"status": "error", "value": "Network Error"}
        except httpx.HTTPStatusError as exc:
            print(f"HTTP Status error {exc.response.status_code} while contacting SerpApi for {user_id}: {exc.response.text[:200]}...")
            error_value = f"API Error {exc.response.status_code}"
            if exc.response.status_code in [401, 403]:
                 error_value = "Authentication Error"
            elif exc.response.status_code == 429:
                 error_value = "Rate Limit Exceeded"
            result = {"status": "error", "value": error_value}
        except Exception as e:
            print(f"An unexpected error occurred processing SerpApi response for {user_id}: {e}")
            result = {"status": "error", "value": "Processing Error"}

    # --- Store result in Redis Cache ---
    if redis_client and isinstance(result, dict): # Only cache if Redis is available and result is valid
        try:
            result_str = json.dumps(result) # Serialize dict to JSON string
            await redis_client.set(user_id, result_str, ex=REDIS_CACHE_TTL_SECONDS)
            print(f"Stored result in Redis cache for user: {user_id} with TTL {REDIS_CACHE_TTL_SECONDS}s")
        except redis.RedisError as e:
            print(f"Redis Error setting cache for {user_id}: {e}")
        except TypeError as e:
             print(f"Error serializing result to JSON for caching for user {user_id}: {e}")

    return result # Return the fetched/processed result

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
    # Make sure redis client is closed gracefully on shutdown if needed
    # uvicorn.run has lifecycle events, but for simplicity, we rely on OS closing connection
    uvicorn.run("main:app", host="0.0.0.0", port=port)
