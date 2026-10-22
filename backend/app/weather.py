"""Historical weather and terrain elevation from Open-Meteo (no API key)."""
from __future__ import annotations

import math
from datetime import datetime, timezone

import pandas as pd
import requests

WMO_CONDITIONS = {
    0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Rime fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Dense drizzle",
    56: "Freezing drizzle", 57: "Freezing drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain",
    66: "Freezing rain", 67: "Freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Rain showers", 81: "Rain showers", 82: "Violent showers",
    85: "Snow showers", 86: "Snow showers",
    95: "Thunderstorm", 96: "Thunderstorm, hail", 99: "Thunderstorm, hail",
}


def dew_point_f(temp_f: float, rh: float) -> float:
    """Magnus formula; inputs in °F and %, output °F."""
    t_c = (temp_f - 32.0) * 5.0 / 9.0
    a, b = 17.625, 243.04
    rh = max(1.0, min(100.0, rh))
    gamma = math.log(rh / 100.0) + a * t_c / (b + t_c)
    dp_c = b * gamma / (a - gamma)
    return dp_c * 9.0 / 5.0 + 32.0


def fetch_weather(lat: float, lon: float, start_time_iso: str) -> dict | None:
    """Hourly weather at the run's start hour. Returns None on failure (caller retries next sync)."""
    t_utc = pd.Timestamp(start_time_iso)
    if t_utc.tzinfo is None:
        t_utc = t_utc.tz_localize("UTC")
    else:
        t_utc = t_utc.tz_convert("UTC")
    date_utc = t_utc.strftime("%Y-%m-%d")
    params = {
        "latitude": round(lat, 4),
        "longitude": round(lon, 4),
        "hourly": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "timezone": "UTC",
        "start_date": date_utc,
        "end_date": date_utc,
    }
    data = None
    for url in ("https://archive-api.open-meteo.com/v1/archive", "https://api.open-meteo.com/v1/forecast"):
        try:
            res = requests.get(url, params=params, timeout=15)
        except requests.RequestException:
            continue
        if res.status_code == 200:
            d = res.json()
            temps = d.get("hourly", {}).get("temperature_2m") or []
            if temps and any(v is not None for v in temps):
                data = d
                break
    if not data:
        return None
    hourly = data["hourly"]
    idx = int(t_utc.hour)
    temps = hourly["temperature_2m"]
    if idx >= len(temps) or temps[idx] is None:
        return None
    temp = float(temps[idx])
    rh_list = hourly.get("relative_humidity_2m") or []
    rh = float(rh_list[idx]) if idx < len(rh_list) and rh_list[idx] is not None else 50.0
    codes = hourly.get("weather_code") or []
    code = codes[idx] if idx < len(codes) else None
    feels = hourly.get("apparent_temperature") or []
    wind = hourly.get("wind_speed_10m") or []
    return {
        "temp_f": temp,
        "feels_like_f": float(feels[idx]) if idx < len(feels) and feels[idx] is not None else temp,
        "humidity": rh,
        "dew_point_f": dew_point_f(temp, rh),
        "wind_mph": float(wind[idx]) if idx < len(wind) and wind[idx] is not None else 0.0,
        "weather_code": int(code) if code is not None else None,
        "condition": WMO_CONDITIONS.get(int(code), "Unknown") if code is not None else "Unknown",
        "lat": lat,
        "lon": lon,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def fetch_current(lat: float, lon: float) -> dict | None:
    try:
        res = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": round(lat, 4),
                "longitude": round(lon, 4),
                "current": "temperature_2m,relative_humidity_2m",
                "temperature_unit": "fahrenheit",
            },
            timeout=5,
        )
        cur = res.json().get("current", {})
        return {"temp_f": float(cur["temperature_2m"]), "humidity": float(cur["relative_humidity_2m"])}
    except Exception:
        return None


def fetch_elevation(lat: float, lon: float) -> float | None:
    """Terrain elevation (metres) from Open-Meteo's digital elevation model."""
    try:
        res = requests.get(
            "https://api.open-meteo.com/v1/elevation",
            params={"latitude": round(lat, 5), "longitude": round(lon, 5)},
            timeout=10,
        )
        vals = res.json().get("elevation") or []
        return float(vals[0]) if vals else None
    except Exception:
        return None
