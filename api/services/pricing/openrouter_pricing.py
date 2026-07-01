import urllib.request
import json
import time
from decimal import Decimal
from loguru import logger

_openrouter_cache = {}
_last_fetch_time = 0
CACHE_TTL = 3600  # 1 hour cache TTL


def fetch_openrouter_prices() -> dict:
    global _openrouter_cache, _last_fetch_time
    now = time.time()
    if _openrouter_cache and (now - _last_fetch_time) < CACHE_TTL:
        return _openrouter_cache

    try:
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/models",
            headers={"User-Agent": "VCalls-AI-SaaS/1.0"},
        )
        # Using a timeout to ensure it doesn't block the caller too long
        with urllib.request.urlopen(req, timeout=3.0) as response:
            data = json.loads(response.read().decode())
            models_data = data.get("data", [])
            new_cache = {}
            for m in models_data:
                model_id = m.get("id")
                pricing = m.get("pricing", {})
                if model_id and pricing:
                    new_cache[model_id] = {
                        "prompt_token_price": Decimal(
                            str(pricing.get("prompt", "0.0"))
                        ),
                        "completion_token_price": Decimal(
                            str(pricing.get("completion", "0.0"))
                        ),
                    }
            if new_cache:
                _openrouter_cache = new_cache
                _last_fetch_time = now
                logger.info(
                    f"Successfully cached {len(new_cache)} OpenRouter model prices."
                )
    except Exception as e:
        logger.error(f"Failed to fetch OpenRouter prices: {e}")
        # If fetch fails but we have stale cache, keep using it
        if _openrouter_cache:
            logger.warning("Using stale OpenRouter cache.")
            return _openrouter_cache

    return _openrouter_cache
