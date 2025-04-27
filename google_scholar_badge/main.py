# main.py
import os
from datetime import datetime, timedelta

import httpx
import redis.asyncio as redis
from dotenv import load_dotenv
from fastapi import FastAPI
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
import json
import uvicorn

load_dotenv()

app = FastAPI()

# ── Redis ──────────────────────────────────────────────────────────────────────
REDIS_URL = os.getenv("REDIS_URL")
REDIS_CACHE_TTL_SUCCESS = 302_400  # 3.5 days
REDIS_CACHE_TTL_ERROR = 600        # 10 minutes

redis_client = None
if REDIS_URL:
    try:
        redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        print("Connected to Redis.")
    except Exception as e:
        print(f"Error connecting to Redis: {e}")
else:
    print("REDIS_URL env var not set – caching disabled.")

# ── SerpApi ────────────────────────────────────────────────────────────────────
SERPAPI_BASE_URL = "https://serpapi.com/search.json"
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")
if not SERPAPI_API_KEY:
    raise RuntimeError("SERPAPI_API_KEY env var not set.")

# Retry any network-level error up to 3 times with exponential back-off
@retry(
    retry=retry_if_exception_type(httpx.RequestError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
)
async def fetch_serpapi(params: dict) -> dict:
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(SERPAPI_BASE_URL, params=params)
        response.raise_for_status()
        return response.json()


async def get_citation_number(user_id: str) -> dict:
    # ── 1) Try Redis ──────────────────────────────────────────────────────────
    if redis_client:
        try:
            cached = await redis_client.get(user_id)
            if cached:
                return json.loads(cached)
        except Exception as e:
            print(f"Redis read error for {user_id}: {e}")

    # ── 2) Hit SerpApi (with retry) ───────────────────────────────────────────
    params = {
        "engine": "google_scholar_author",
        "author_id": user_id,
        "api_key": SERPAPI_API_KEY,
        "hl": "en",
    }

    result = {"status": "error", "value": "Unknown error"}
    try:
        data = await fetch_serpapi(params)

        if "error" in data:
            result = {"status": "error", "value": f"SerpApi: {data['error']}"}
        else:
            citation_count = None
            cb = data.get("cited_by")
            if cb and "value" in cb:
                citation_count = cb["value"]
            elif cb and "table" in cb:
                for row in cb["table"]:
                    if (cits := row.get("citations", {}).get("all")) is not None:
                        citation_count = cits
                        break

            if citation_count is not None:
                result = {"status": "success", "value": str(citation_count)}
            else:
                result = {"status": "not_found", "value": None}

    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        if code in (401, 403):
            result = {"status": "error", "value": "Auth error"}
        elif code == 429:
            result = {"status": "error", "value": "Rate limit"}
        else:
            result = {"status": "error", "value": f"API {code}"}
    except Exception as e:
        result = {"status": "error", "value": "Network/processing error"}

    # ── 3) Cache if appropriate ───────────────────────────────────────────────
    if redis_client:
        try:
            status = result.get("status")
            ttl = (
                REDIS_CACHE_TTL_SUCCESS
                if status in {"success", "not_found"}
                else REDIS_CACHE_TTL_ERROR
            )
            # Optionally skip caching for errors altogether by uncommenting:
            # if status not in {"success", "not_found"}: return result
            await redis_client.set(user_id, json.dumps(result), ex=ttl)
        except Exception as e:
            print(f"Redis write error for {user_id}: {e}")

    return result


# ── FastAPI route ─────────────────────────────────────────────────────────────
@app.get("/citations")
async def citations(user: str):
    res = await get_citation_number(user)
    status, value = res.get("status"), res.get("value")

    msg, color = "Error", "red"
    if status == "success":
        try:
            msg, color = str(int(value)), "brightgreen"
        except Exception:
            pass
    elif status == "not_found":
        msg, color = "Not found", "yellow"
    else:  # error
        msg = value or "Error"

    return {
        "schemaVersion": 1,
        "label": "Citations",
        "message": msg,
        "color": color,
        "style": "social",
        "namedLogo": "Google Scholar",
    }


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
