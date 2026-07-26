import json
import os
import xml.etree.ElementTree as ET
import pandas as pd
import requests

WMO_WEATHER_MAP = {
    0: ("Clear Sky", "fa-sun"),
    1: ("Mainly Clear", "fa-cloud-sun"),
    2: ("Partly Cloudy", "fa-cloud-sun"),
    3: ("Overcast", "fa-cloud"),
    45: ("Foggy", "fa-smog"),
    48: ("Depositing Rime Fog", "fa-smog"),
    51: ("Light Drizzle", "fa-cloud-rain"),
    53: ("Moderate Drizzle", "fa-cloud-rain"),
    55: ("Dense Drizzle", "fa-cloud-rain"),
    56: ("Light Freezing Drizzle", "fa-snowflake"),
    57: ("Dense Freezing Drizzle", "fa-snowflake"),
    61: ("Slight Rain", "fa-cloud-rain"),
    63: ("Moderate Rain", "fa-cloud-showers-heavy"),
    65: ("Heavy Rain", "fa-cloud-showers-heavy"),
    66: ("Light Freezing Rain", "fa-snowflake"),
    67: ("Heavy Freezing Rain", "fa-snowflake"),
    71: ("Slight Snow", "fa-snowflake"),
    73: ("Moderate Snow", "fa-snowflake"),
    75: ("Heavy Snow", "fa-snowflake"),
    77: ("Snow Grains", "fa-snowflake"),
    80: ("Slight Rain Showers", "fa-cloud-sun-rain"),
    81: ("Moderate Rain Showers", "fa-cloud-sun-rain"),
    82: ("Violent Rain Showers", "fa-cloud-showers-heavy"),
    85: ("Slight Snow Showers", "fa-snowflake"),
    86: ("Heavy Snow Showers", "fa-snowflake"),
    95: ("Thunderstorm", "fa-cloud-bolt"),
    96: ("Thunderstorm with Hail", "fa-cloud-bolt"),
    99: ("Heavy Thunderstorm", "fa-cloud-bolt"),
}

DEFAULT_LAT = 39.9473
DEFAULT_LON = -75.1795


def get_location_name(lat, lon):
    """Map coordinates to a clean human-readable city name."""
    if lat is None or lon is None:
        return "Philadelphia, PA"
    if 39.8 <= lat <= 40.1 and -75.3 <= lon <= -75.0:
        return "Philadelphia, PA"
    if 18.3 <= lat <= 18.6 and -66.3 <= lon <= -66.0:
        return "San Juan, PR"
    return f"{lat:.2f}°, {lon:.2f}°"


def extract_start_coords_from_tcx(route_file):
    """Extract start lat/lon from TCX JSON route file."""
    if not route_file or not os.path.exists(route_file):
        return None, None

    try:
        with open(route_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        tcx_str = data.get("tcxData", "")
        if not tcx_str:
            return None, None

        root = ET.fromstring(tcx_str)
        ns = {"ns": "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"}
        trackpoints = root.findall(".//ns:Trackpoint", ns)

        for tp in trackpoints:
            pos = tp.find("ns:Position", ns)
            if pos is not None:
                lat_node = pos.find("ns:LatitudeDegrees", ns)
                lon_node = pos.find("ns:LongitudeDegrees", ns)
                if lat_node is not None and lon_node is not None:
                    return float(lat_node.text), float(lon_node.text)
    except Exception as e:
        print(f"Error reading TCX coords from {route_file}: {e}")

    return None, None


def fetch_weather_for_run(lat, lon, start_time_iso):
    """Fetch weather metrics from Open-Meteo API for given location and timestamp."""
    try:
        dt = pd.to_datetime(start_time_iso)
        date_str = dt.strftime("%Y-%m-%d")
        hour_idx = dt.hour

        lat_val = lat if lat is not None else DEFAULT_LAT
        lon_val = lon if lon is not None else DEFAULT_LON

        params = {
            "latitude": round(lat_val, 4),
            "longitude": round(lon_val, 4),
            "start_date": date_str,
            "end_date": date_str,
            "hourly": [
                "temperature_2m",
                "apparent_temperature",
                "relative_humidity_2m",
                "weather_code",
                "wind_speed_10m",
            ],
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
        }

        # Try historical archive API first
        archive_url = "https://archive-api.open-meteo.com/v1/archive"
        res = requests.get(archive_url, params=params, timeout=10)

        # Fallback to forecast API for recent dates if archive returns non-200
        if res.status_code != 200:
            forecast_url = "https://api.open-meteo.com/v1/forecast"
            res = requests.get(forecast_url, params=params, timeout=10)

        if res.status_code == 200:
            data = res.json()
            hourly = data.get("hourly", {})
            temps = hourly.get("temperature_2m", [])

            if temps and hour_idx < len(temps):
                temp = temps[hour_idx]
                feels = hourly.get("apparent_temperature", [temp])[hour_idx]
                humidity = hourly.get("relative_humidity_2m", [50])[hour_idx]
                code = hourly.get("weather_code", [0])[hour_idx]
                wind = hourly.get("wind_speed_10m", [0.0])[hour_idx]

                cond_name, icon = WMO_WEATHER_MAP.get(
                    code, ("Partly Cloudy", "fa-cloud-sun")
                )
                loc_name = get_location_name(lat, lon)

                return {
                    "temp_f": round(temp),
                    "feels_like_f": round(feels),
                    "humidity": round(humidity),
                    "weather_code": code,
                    "condition": cond_name,
                    "icon": icon,
                    "wind_mph": round(wind, 1),
                    "location": loc_name,
                }
    except Exception as e:
        print(f"Error fetching weather for {start_time_iso}: {e}")

    loc_name = get_location_name(lat, lon)
    return {
        "temp_f": None,
        "feels_like_f": None,
        "humidity": None,
        "weather_code": None,
        "condition": "N/A",
        "icon": "fa-cloud",
        "wind_mph": None,
        "location": loc_name,
    }


def load_weather_cache(base_dir):
    cache_path = os.path.join(base_dir, "run_weather.json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading weather cache: {e}")
    return {}


def save_weather_cache(cache, base_dir):
    cache_path = os.path.join(base_dir, "run_weather.json")
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        print(f"Error saving weather cache: {e}")


def get_weather_for_runs(runs_data, routes_dir, base_dir):
    """Populates and caches weather information for a list of runs."""
    cache = load_weather_cache(base_dir)
    updated = False

    for run_item in runs_data:
        run_id = run_item.get("id") or run_item.get("name", "").split("/")[-1]
        start_time = run_item.get("datetime") or run_item.get(
            "exercise.interval.startTime"
        )

        if not run_id or not start_time:
            continue

        # Check if already cached with valid temperature
        if run_id in cache and cache[run_id].get("temp_f") is not None:
            continue

        # Locate route file to get exact starting coordinates
        route_file = None
        if os.path.exists(routes_dir):
            for f in os.listdir(routes_dir):
                if f.endswith(f"_{run_id}.json"):
                    route_file = os.path.join(routes_dir, f)
                    break

        lat, lon = extract_start_coords_from_tcx(route_file)

        print(
            f"Fetching weather for run {run_id} ({start_time}) at ({lat}, {lon})..."
        )
        weather_info = fetch_weather_for_run(lat, lon, start_time)
        cache[run_id] = weather_info
        updated = True

    if updated:
        save_weather_cache(cache, base_dir)

    return cache
