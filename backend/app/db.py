"""SQLite schema and connection helpers. One file, no ORM."""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from typing import Iterator

from .config import DATA_DIR, DB_PATH, DEFAULT_SETTINGS

SCHEMA = """
CREATE TABLE IF NOT EXISTS activities (
    id TEXT PRIMARY KEY,
    name TEXT,
    activity_type TEXT,
    start_time TEXT NOT NULL,
    end_time TEXT,
    utc_offset_sec INTEGER,
    active_duration_sec REAL,
    distance_m REAL,
    avg_pace_sec_per_m REAL,
    avg_hr REAL,
    calories REAL,
    steps INTEGER,
    elevation_gain_m REAL,
    cadence_spm REAL,
    stride_m REAL,
    vertical_osc_mm REAL,
    ground_contact_sec REAL,
    zone_light_sec INTEGER,
    zone_moderate_sec INTEGER,
    zone_vigorous_sec INTEGER,
    zone_peak_sec INTEGER,
    has_gps INTEGER DEFAULT 0,
    source_platform TEXT,
    source_device TEXT,
    raw_json TEXT,
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_activities_type_time ON activities(activity_type, start_time);

CREATE TABLE IF NOT EXISTS splits (
    activity_id TEXT NOT NULL,
    split_index INTEGER NOT NULL,
    distance_m REAL,
    duration_sec REAL,
    pace_sec_per_m REAL,
    PRIMARY KEY (activity_id, split_index)
);

CREATE TABLE IF NOT EXISTS hr_samples (
    activity_id TEXT NOT NULL,
    t_sec REAL NOT NULL,
    bpm INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_hr_activity ON hr_samples(activity_id);

CREATE TABLE IF NOT EXISTS route_points (
    activity_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    t_sec REAL,
    lat REAL,
    lon REAL,
    alt_m REAL,
    dist_m REAL,
    hr INTEGER,
    PRIMARY KEY (activity_id, seq)
);

CREATE TABLE IF NOT EXISTS route_meta (
    activity_id TEXT PRIMARY KEY,
    n_points INTEGER,
    start_lat REAL,
    start_lon REAL,
    elevation_m REAL,          -- terrain elevation at start (DEM), metres
    elevation_gain_m REAL,     -- computed from smoothed GPS altitude
    start_bearing_deg REAL,    -- compass heading of the first ~800 m
    location_inferred INTEGER, -- 1 when start_lat/lon were borrowed from a nearby GPS run
    fetch_error TEXT,
    fetched_at TEXT
);

CREATE TABLE IF NOT EXISTS weather (
    activity_id TEXT PRIMARY KEY,
    temp_f REAL,
    feels_like_f REAL,
    humidity REAL,
    dew_point_f REAL,
    wind_mph REAL,
    weather_code INTEGER,
    condition TEXT,
    lat REAL,
    lon REAL,
    fetched_at TEXT
);

CREATE TABLE IF NOT EXISTS route_similarity (
    a_id TEXT NOT NULL,
    b_id TEXT NOT NULL,
    coverage_ab REAL,          -- fraction of A's points within radius of B
    coverage_ba REAL,
    direction_corr REAL,       -- +1 same direction, -1 reversed
    PRIMARY KEY (a_id, b_id)
);

CREATE TABLE IF NOT EXISTS route_groups (
    activity_id TEXT PRIMARY KEY,
    group_id INTEGER NOT NULL,
    reference_id TEXT,
    same_direction INTEGER     -- 1 same as reference, 0 reversed, NULL unknown
);

CREATE TABLE IF NOT EXISTS group_names (
    group_id INTEGER PRIMARY KEY,
    name TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT,
    finished_at TEXT,
    status TEXT,
    message TEXT,
    new_activities INTEGER DEFAULT 0
);
"""

_lock = threading.RLock()


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


MIGRATIONS = [
    ("route_meta", "start_bearing_deg", "ALTER TABLE route_meta ADD COLUMN start_bearing_deg REAL"),
    ("route_meta", "location_inferred", "ALTER TABLE route_meta ADD COLUMN location_inferred INTEGER"),
]


def init_db() -> None:
    with db() as conn:
        conn.executescript(SCHEMA)
        for table, col, ddl in MIGRATIONS:
            cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            if col not in cols:
                conn.execute(ddl)
        for k, v in DEFAULT_SETTINGS.items():
            conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (k, v))


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    """Serialized connection with commit-on-success."""
    with _lock:
        conn = connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def get_setting(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if row is None:
        return DEFAULT_SETTINGS.get(key, default)
    return row["value"]


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
