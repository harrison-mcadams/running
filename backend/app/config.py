"""Paths and tunables. Everything that used to be hard-coded lives here or in the settings table."""
from __future__ import annotations

import os
from pathlib import Path

ROOT_DIR = Path(os.environ.get("STRIDES_ROOT", Path(__file__).resolve().parents[2]))
DATA_DIR = Path(os.environ.get("STRIDES_DATA_DIR", ROOT_DIR / "data"))
DB_PATH = DATA_DIR / "strides.db"
CREDENTIALS_PATH = Path(os.environ.get("STRIDES_CREDENTIALS", ROOT_DIR / "credentials.json"))
LEGACY_DIR = ROOT_DIR / "legacy"
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"

HEALTH_API_BASE = "https://health.googleapis.com/v4"
OAUTH_SCOPES = [
    "https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly",
    "https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly",
    "https://www.googleapis.com/auth/googlehealth.location.readonly",
]

# Default settings; stored in the settings table so they can be edited without code changes.
DEFAULT_SETTINGS = {
    # Runs before this date are stored but hidden (pre-watch phone runs).
    "hidden_before": "2025-12-29",
    # Sync fetches exercises from this date on the very first sync.
    "sync_from": "2025-01-01",
    # Run filters (accidental starts and walks-logged-as-runs).
    "min_distance_mi": "0.5",
    "max_pace_sec_mi": "900",
    # Route matching.
    "match_radius_m": "60",
    "group_coverage": "0.8",
}

METERS_PER_MILE = 1609.344
FEET_PER_METER = 3.28084
