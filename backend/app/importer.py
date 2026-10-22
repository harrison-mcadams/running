"""One-time import of the old app's files (CSV exercise dumps, per-run TCX and heart-rate
files, weather cache) into the database. Safe to re-run: it never overwrites an activity
that already exists, and skips routes/HR/weather already stored."""
from __future__ import annotations

import csv
import glob
import json
import logging
import os
import sqlite3
from pathlib import Path

from . import geo, store
from .config import LEGACY_DIR, ROOT_DIR
from .parsing import datapoint_to_activity, hr_points_to_samples, parse_tcx
from .weather import dew_point_f

log = logging.getLogger("strides.import")

csv.field_size_limit(10_000_000)


def _candidates(name: str) -> list[Path]:
    """Root copies first: on a live install they are the newest (the old app kept syncing into
    them), and import never overwrites, so whichever file is read first wins for shared runs."""
    return [p for p in (ROOT_DIR / name, LEGACY_DIR / name) if p.exists()]


def import_legacy(conn: sqlite3.Connection) -> dict:
    counts = {"activities": 0, "routes": 0, "hr": 0, "weather": 0}

    # Newest dump first: activities are never overwritten, so the first file to contain a run wins.
    for csv_name in ("my_exercises.csv", "my_exercises_all.csv"):
        for path in _candidates(csv_name):
            with open(path, newline="", encoding="utf-8") as fh:
                for rec in csv.DictReader(fh):
                    rec = {k: (v if v != "" else None) for k, v in rec.items()}
                    try:
                        row, splits = datapoint_to_activity(rec)
                    except ValueError:
                        continue
                    if store.upsert_activity(conn, row, splits, overwrite=False):
                        counts["activities"] += 1

    for d in _candidates("run_routes"):
        for path in glob.glob(os.path.join(d, "run_route_*.json")):
            act_id = Path(path).stem.split("_")[-1]
            if conn.execute("SELECT 1 FROM route_meta WHERE activity_id = ? AND n_points > 0", (act_id,)).fetchone():
                continue
            if not conn.execute("SELECT 1 FROM activities WHERE id = ?", (act_id,)).fetchone():
                continue
            try:
                with open(path, encoding="utf-8") as fh:
                    pts = parse_tcx(json.load(fh).get("tcxData", ""))
            except Exception as e:  # noqa: BLE001
                log.warning("bad route file %s: %s", path, e)
                continue
            if pts:
                store.store_route(conn, act_id, pts, geo.elevation_gain_m(pts))
                counts["routes"] += 1

    for d in _candidates("run_heart_rates"):
        for path in glob.glob(os.path.join(d, "run_hr_*.csv")):
            act_id = Path(path).stem.split("_")[-1]
            if conn.execute("SELECT 1 FROM hr_samples WHERE activity_id = ? LIMIT 1", (act_id,)).fetchone():
                continue
            act = conn.execute("SELECT start_time FROM activities WHERE id = ?", (act_id,)).fetchone()
            if not act:
                continue
            with open(path, newline="", encoding="utf-8") as fh:
                samples = hr_points_to_samples(list(csv.DictReader(fh)), act["start_time"])
            if samples:
                store.store_hr(conn, act_id, samples)
                counts["hr"] += 1

    for path in _candidates("run_weather.json"):
        with open(path, encoding="utf-8") as fh:
            cache = json.load(fh)
        for act_id, w in cache.items():
            if w.get("temp_f") is None:
                continue
            if conn.execute("SELECT 1 FROM weather WHERE activity_id = ?", (act_id,)).fetchone():
                continue
            if not conn.execute("SELECT 1 FROM activities WHERE id = ?", (act_id,)).fetchone():
                continue
            rm = conn.execute("SELECT start_lat, start_lon FROM route_meta WHERE activity_id = ?", (act_id,)).fetchone()
            store.store_weather(
                conn,
                act_id,
                {
                    "temp_f": w["temp_f"],
                    "feels_like_f": w.get("feels_like_f"),
                    "humidity": w.get("humidity"),
                    "dew_point_f": dew_point_f(w["temp_f"], w["humidity"]) if w.get("humidity") is not None else None,
                    "wind_mph": w.get("wind_mph"),
                    "weather_code": w.get("weather_code"),
                    "condition": w.get("condition"),
                    "lat": rm["start_lat"] if rm else None,
                    "lon": rm["start_lon"] if rm else None,
                    "fetched_at": None,
                },
            )
            counts["weather"] += 1

    log.info("legacy import: %s", counts)
    return counts
