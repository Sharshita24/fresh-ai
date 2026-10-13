"""Live weather from Open-Meteo (free, no key) with a bundled real snapshot as offline fallback.

Rain keeps shoppers at home, so the next three hours of precipitation scale the footfall forecast:
  footfall factor = 1 - 0.35 × (1 - e^(-mm_per_h / 3))      → 3 mm/h ≈ -22%, heavy rain caps at -35%
"""

import json
import math
import os
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SNAPSHOT = Path(__file__).resolve().parent.parent / "data" / "weather_snapshot_bengaluru_east.json"
IST = ZoneInfo("Asia/Kolkata")
CACHE_S = 1800
_cache: dict[tuple[float, float], tuple[float, dict]] = {}


def _live_enabled() -> bool:
    return os.getenv("WEATHER_LIVE", "true").lower() in ("1", "true", "yes")


def _fetch_live(lat: float, lon: float) -> dict | None:
    try:
        import httpx

        r = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "hourly": "precipitation,precipitation_probability,temperature_2m,relative_humidity_2m",
                "current": "precipitation,temperature_2m,relative_humidity_2m,weather_code",
                "past_days": 1,
                "forecast_days": 2,
                "timezone": "Asia/Kolkata",
            },
            timeout=4.0,
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def _load(lat: float, lon: float) -> tuple[dict, str]:
    key = (round(lat, 2), round(lon, 2))
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_S:
        return hit[1], "open-meteo live"
    if _live_enabled():
        data = _fetch_live(lat, lon)
        if data:
            _cache[key] = (time.time(), data)
            return data, "open-meteo live"
    return json.loads(SNAPSHOT.read_text()), "open-meteo snapshot"


def footfall_factor(mm_per_h: float) -> float:
    return round(1 - 0.35 * (1 - math.exp(-max(0.0, mm_per_h) / 3)), 3)


def outlook(lat: float, lon: float, now: datetime) -> dict:
    data, source = _load(lat, lon)
    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    precip = hourly.get("precipitation", [])
    local = now.astimezone(IST)
    stamp = local.strftime("%Y-%m-%dT%H:00")
    if stamp in times:
        i = times.index(stamp)
    else:  # snapshot from another day: line up by hour of day
        i = next((k for k, t in enumerate(times) if t.endswith(f"T{local.hour:02d}:00")), 0)
    next3 = [p or 0.0 for p in precip[i : i + 3]] or [0.0]
    avg = sum(next3) / len(next3)
    current = data.get("current", {})
    return {
        "source": source,
        "temperatureC": current.get("temperature_2m"),
        "humidityPct": current.get("relative_humidity_2m"),
        "precipNowMm": precip[i] if i < len(precip) and precip[i] is not None else current.get("precipitation", 0.0),
        "precipNext3hMm": round(sum(next3), 1),
        "rainExpected": avg >= 0.5,
        "footfallFactor": footfall_factor(avg),
    }
