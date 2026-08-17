# main.py
import json
import os

import httpx
import redis.asyncio as redis
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

load_dotenv()

app = FastAPI()

# ── Redis ──────────────────────────────────────────────────────────────────────
REDIS_URL = os.getenv("REDIS_URL")
REDIS_CACHE_TTL_SUCCESS = 604_800  # 7 days
REDIS_CACHE_TTL_ERROR = 600        # 10 minutes
REDIS_KEY_PREFIX = "metrics:"      # new format: all metrics in one entry

redis_client = None
if REDIS_URL:
    try:
        redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        print("Connected to Redis.")
    except Exception as e:
        print(f"Error connecting to Redis: {e}")
else:
    print("REDIS_URL env var not set – caching disabled.")

# ── Metrics ────────────────────────────────────────────────────────────────────
# SerpApi returns all three in the same `cited_by.table`, so one request
# is enough to serve every badge.
METRIC_LABELS = {
    "citations": "Citations",
    "h_index": "h-index",
    "i10_index": "i10-index",
}

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


def parse_metrics(data: dict) -> dict:
    """Pull the all-time citations / h-index / i10-index out of `cited_by.table`."""
    metrics = {}
    table = data.get("cited_by", {}).get("table") or []
    for row in table:
        for name in METRIC_LABELS:
            if (value := row.get(name, {}).get("all")) is not None:
                metrics[name] = value
    return metrics


async def get_author_metrics(user_id: str) -> dict:
    cache_key = REDIS_KEY_PREFIX + user_id

    # ── 1) Try Redis ──────────────────────────────────────────────────────────
    if redis_client:
        try:
            cached = await redis_client.get(cache_key)
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
            metrics = parse_metrics(data)
            if metrics:
                result = {"status": "success", "metrics": metrics}
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
        print(f"Processing error for {user_id}: {e}")
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
            await redis_client.set(cache_key, json.dumps(result), ex=ttl)
        except Exception as e:
            print(f"Redis write error for {user_id}: {e}")

    return result


async def build_badge(user_id: str, metric: str) -> dict:
    res = await get_author_metrics(user_id)
    status = res.get("status")

    msg, color = "Error", "red"
    if status == "success":
        value = res.get("metrics", {}).get(metric)
        if value is None:
            msg, color = "Not found", "yellow"
        else:
            msg, color = str(value), "brightgreen"
    elif status == "not_found":
        msg, color = "Not found", "yellow"
    else:  # error
        msg = res.get("value") or "Error"

    return {
        "schemaVersion": 1,
        "label": METRIC_LABELS[metric],
        "message": msg,
        "color": color,
        "style": "social",
        "namedLogo": "Google Scholar",
    }


# ── FastAPI routes ────────────────────────────────────────────────────────────
@app.get("/citations")
async def citations(user: str):
    return await build_badge(user, "citations")


@app.get("/h-index")
async def h_index(user: str):
    return await build_badge(user, "h_index")


@app.get("/i10-index")
async def i10_index(user: str):
    return await build_badge(user, "i10_index")


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
