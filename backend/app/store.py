"""Reads and writes against the SQLite tables, and the derived "run" record the API serves."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pandas as pd

from . import geo
from .config import FEET_PER_METER, METERS_PER_MILE
from .db import get_setting

ACTIVITY_COLS = [
    "id", "name", "activity_type", "start_time", "end_time", "utc_offset_sec", "active_duration_sec",
    "distance_m", "avg_pace_sec_per_m", "avg_hr", "calories", "steps", "elevation_gain_m", "cadence_spm",
    "stride_m", "vertical_osc_mm", "ground_contact_sec", "zone_light_sec", "zone_moderate_sec",
    "zone_vigorous_sec", "zone_peak_sec", "has_gps", "source_platform", "source_device", "raw_json", "updated_at",
]


def upsert_activity(conn: sqlite3.Connection, row: dict, splits: list[dict], overwrite: bool = True) -> bool:
    """Insert or update. Returns True when the activity was new."""
    exists = conn.execute("SELECT 1 FROM activities WHERE id = ?", (row["id"],)).fetchone() is not None
    if exists and not overwrite:
        return False
    cols = ", ".join(ACTIVITY_COLS)
    marks = ", ".join("?" for _ in ACTIVITY_COLS)
    updates = ", ".join(f"{c} = excluded.{c}" for c in ACTIVITY_COLS if c != "id")
    conn.execute(
        f"INSERT INTO activities ({cols}) VALUES ({marks}) ON CONFLICT(id) DO UPDATE SET {updates}",
        [row.get(c) for c in ACTIVITY_COLS],
    )
    if splits or not exists:
        conn.execute("DELETE FROM splits WHERE activity_id = ?", (row["id"],))
        conn.executemany(
            "INSERT INTO splits (activity_id, split_index, distance_m, duration_sec, pace_sec_per_m) VALUES (?, ?, ?, ?, ?)",
            [(s["activity_id"], s["split_index"], s["distance_m"], s["duration_sec"], s["pace_sec_per_m"]) for s in splits],
        )
    return not exists


def store_route(conn: sqlite3.Connection, activity_id: str, points: list[dict], elevation_gain: float | None) -> None:
    conn.execute("DELETE FROM route_points WHERE activity_id = ?", (activity_id,))
    conn.executemany(
        "INSERT INTO route_points (activity_id, seq, t_sec, lat, lon, alt_m, dist_m, hr) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (activity_id, i, p["t_sec"], p["lat"], p["lon"], p["alt_m"], p["dist_m"], p["hr"])
            for i, p in enumerate(points)
        ],
    )
    first = next((p for p in points if p.get("lat") is not None), None)
    track = geo.resample(points)
    bearing = geo.start_bearing_deg(track) if track is not None else None
    conn.execute(
        """INSERT INTO route_meta (activity_id, n_points, start_lat, start_lon, elevation_gain_m, start_bearing_deg, location_inferred, fetch_error, fetched_at)
           VALUES (?, ?, ?, ?, ?, ?, 0, NULL, ?)
           ON CONFLICT(activity_id) DO UPDATE SET n_points = excluded.n_points, start_lat = excluded.start_lat,
             start_lon = excluded.start_lon, elevation_gain_m = excluded.elevation_gain_m,
             start_bearing_deg = excluded.start_bearing_deg, location_inferred = 0, elevation_m = NULL,
             fetch_error = NULL, fetched_at = excluded.fetched_at""",
        (
            activity_id,
            len(points),
            first["lat"] if first else None,
            first["lon"] if first else None,
            elevation_gain,
            bearing,
            _now(),
        ),
    )


def infer_locations(conn: sqlite3.Connection) -> int:
    """Give runs without a GPS track a start location borrowed from the nearest-in-time GPS run
    recorded in the same UTC offset (so a no-GPS run in Tanzania borrows a Tanzanian run, not
    the home trail). Weather and altitude lookups then use it. Returns the number filled."""
    known = conn.execute(
        """SELECT a.start_time, a.utc_offset_sec, rm.start_lat, rm.start_lon FROM activities a
           JOIN route_meta rm ON rm.activity_id = a.id
           WHERE rm.n_points > 0 AND rm.start_lat IS NOT NULL"""
    ).fetchall()
    todo = conn.execute(
        """SELECT a.id, a.start_time, a.utc_offset_sec FROM activities a
           LEFT JOIN route_meta rm ON rm.activity_id = a.id
           WHERE a.activity_type = 'RUNNING' AND (rm.activity_id IS NULL OR rm.n_points = 0)
             AND (rm.start_lat IS NULL OR rm.location_inferred = 1)"""
    ).fetchall()
    if not known:
        return 0
    n = 0
    for r in todo:
        t = pd.Timestamp(r["start_time"])
        pool = [k for k in known if r["utc_offset_sec"] is not None and k["utc_offset_sec"] == r["utc_offset_sec"]] or list(known)
        best = min(pool, key=lambda k: abs((pd.Timestamp(k["start_time"]) - t).total_seconds()))
        cur = conn.execute("SELECT start_lat, start_lon FROM route_meta WHERE activity_id = ?", (r["id"],)).fetchone()
        if cur and cur["start_lat"] == best["start_lat"] and cur["start_lon"] == best["start_lon"]:
            continue
        conn.execute(
            """INSERT INTO route_meta (activity_id, n_points, start_lat, start_lon, location_inferred) VALUES (?, 0, ?, ?, 1)
               ON CONFLICT(activity_id) DO UPDATE SET start_lat = excluded.start_lat, start_lon = excluded.start_lon,
                 location_inferred = 1, elevation_m = NULL""",
            (r["id"], best["start_lat"], best["start_lon"]),
        )
        # Location changed, so any weather fetched for the old guess is stale.
        conn.execute("DELETE FROM weather WHERE activity_id = ?", (r["id"],))
        n += 1
    return n


def get_comments(conn: sqlite3.Connection, activity_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT id, body, created_at FROM run_comments WHERE activity_id = ? ORDER BY created_at, id", (activity_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def add_comment(conn: sqlite3.Connection, activity_id: str, body: str) -> dict:
    created = _now()
    cur = conn.execute(
        "INSERT INTO run_comments (activity_id, body, created_at) VALUES (?, ?, ?)", (activity_id, body, created)
    )
    return {"id": cur.lastrowid, "body": body, "created_at": created}


def delete_comment(conn: sqlite3.Connection, activity_id: str, comment_id: int) -> bool:
    cur = conn.execute("DELETE FROM run_comments WHERE id = ? AND activity_id = ?", (comment_id, activity_id))
    return cur.rowcount > 0


def set_excluded(conn: sqlite3.Connection, activity_id: str, excluded: bool) -> None:
    conn.execute(
        """INSERT INTO run_flags (activity_id, exclude_from_model, updated_at) VALUES (?, ?, ?)
           ON CONFLICT(activity_id) DO UPDATE SET exclude_from_model = excluded.exclude_from_model,
             updated_at = excluded.updated_at""",
        (activity_id, 1 if excluded else 0, _now()),
    )


def mark_route_failed(conn: sqlite3.Connection, activity_id: str, error: str) -> None:
    conn.execute(
        """INSERT INTO route_meta (activity_id, n_points, fetch_error, fetched_at) VALUES (?, 0, ?, ?)
           ON CONFLICT(activity_id) DO UPDATE SET fetch_error = excluded.fetch_error, fetched_at = excluded.fetched_at""",
        (activity_id, error[:500], _now()),
    )


def store_hr(conn: sqlite3.Connection, activity_id: str, samples: list[tuple[float, int]]) -> None:
    conn.execute("DELETE FROM hr_samples WHERE activity_id = ?", (activity_id,))
    conn.executemany(
        "INSERT INTO hr_samples (activity_id, t_sec, bpm) VALUES (?, ?, ?)",
        [(activity_id, t, b) for t, b in samples],
    )


def store_weather(conn: sqlite3.Connection, activity_id: str, w: dict) -> None:
    conn.execute(
        """INSERT INTO weather (activity_id, temp_f, feels_like_f, humidity, dew_point_f, wind_mph, weather_code, condition, lat, lon, fetched_at)
           VALUES (:activity_id, :temp_f, :feels_like_f, :humidity, :dew_point_f, :wind_mph, :weather_code, :condition, :lat, :lon, :fetched_at)
           ON CONFLICT(activity_id) DO UPDATE SET temp_f = excluded.temp_f, feels_like_f = excluded.feels_like_f,
             humidity = excluded.humidity, dew_point_f = excluded.dew_point_f, wind_mph = excluded.wind_mph,
             weather_code = excluded.weather_code, condition = excluded.condition, lat = excluded.lat, lon = excluded.lon,
             fetched_at = excluded.fetched_at""",
        {"activity_id": activity_id, **{k: w.get(k) for k in ("temp_f", "feels_like_f", "humidity", "dew_point_f", "wind_mph", "weather_code", "condition", "lat", "lon", "fetched_at")}},
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Derived run records
# ---------------------------------------------------------------------------

def local_datetime(start_time: str, utc_offset_sec: int | None, lon: float | None) -> datetime:
    """Local wall-clock time of the run. Falls back to a longitude-based offset when the
    source did not record one (some phone-logged runs)."""
    t = pd.Timestamp(start_time)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    if utc_offset_sec is None:
        utc_offset_sec = int(round((lon or -75.0) / 15.0)) * 3600
    return (t + timedelta(seconds=utc_offset_sec)).tz_localize(None).to_pydatetime()


def fmt_pace(sec: float | None) -> str | None:
    if sec is None or sec <= 0:
        return None
    return f"{int(sec // 60)}:{int(sec % 60):02d}"


def fmt_duration(sec: float | None) -> str | None:
    if sec is None:
        return None
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def run_filters(conn: sqlite3.Connection) -> dict:
    return {
        "hidden_before": get_setting(conn, "hidden_before"),
        "min_distance_mi": float(get_setting(conn, "min_distance_mi")),
        "max_pace_sec_mi": float(get_setting(conn, "max_pace_sec_mi")),
    }


def list_runs(conn: sqlite3.Connection, include_hidden: bool = False) -> list[dict]:
    """All runs that pass the visibility filters, oldest first, with weather, route metadata and
    group membership joined in."""
    flt = run_filters(conn)
    rows = conn.execute(
        """
        SELECT a.*, w.temp_f, w.feels_like_f, w.humidity, w.dew_point_f, w.wind_mph, w.condition, w.weather_code,
               w.lat AS w_lat, w.lon AS w_lon,
               rm.n_points, rm.start_lat, rm.start_lon, rm.elevation_m, rm.elevation_gain_m AS gps_gain_m,
               rm.start_bearing_deg, rm.location_inferred,
               g.group_id, g.same_direction, gn.name AS group_name, COALESCE(f.exclude_from_model, 0) AS excluded,
               (SELECT COUNT(*) FROM hr_samples h WHERE h.activity_id = a.id) AS n_hr,
               (SELECT COUNT(*) FROM splits s WHERE s.activity_id = a.id) AS n_splits,
               (SELECT COUNT(*) FROM run_comments c WHERE c.activity_id = a.id) AS n_comments
        FROM activities a
        LEFT JOIN weather w ON w.activity_id = a.id
        LEFT JOIN route_meta rm ON rm.activity_id = a.id
        LEFT JOIN route_groups g ON g.activity_id = a.id
        LEFT JOIN group_names gn ON gn.group_id = g.group_id
        LEFT JOIN run_flags f ON f.activity_id = a.id
        WHERE a.activity_type = 'RUNNING'
        ORDER BY a.start_time
        """
    ).fetchall()
    out = []
    for r in rows:
        rec = _run_record(r)
        if rec is None:
            continue
        if not include_hidden:
            if flt["hidden_before"] and rec["date"] < flt["hidden_before"]:
                continue
            if rec["distance_mi"] < flt["min_distance_mi"]:
                continue
            if rec["pace_sec_mi"] is None or rec["pace_sec_mi"] > flt["max_pace_sec_mi"]:
                continue
        out.append(rec)
    # Fill in automatic route names where no custom name is set.
    auto = auto_group_names(out)
    for rec in out:
        if rec["group_id"] is not None and not rec["group_name"]:
            rec["group_name"] = auto.get(rec["group_id"])
    return out


def auto_group_names(runs: list[dict]) -> dict[int, str]:
    """'N out from home, 4.0-6.0 mi' style names from the members' headings and distances."""
    groups: dict[int, list[dict]] = {}
    for r in runs:
        if r["group_id"] is not None:
            groups.setdefault(r["group_id"], []).append(r)
    names = {}
    for gid, members in groups.items():
        dists = sorted(m["distance_mi"] for m in members)
        headings = "/".join(sorted({m["heading"] for m in members if m["heading"]})) or "Route"
        if len(dists) > 1 and dists[-1] - dists[0] >= 0.3:
            names[gid] = f"{headings} out from home, {dists[0]:.1f}-{dists[-1]:.1f} mi"
        else:
            names[gid] = f"{headings} route, {dists[len(dists) // 2]:.1f} mi"
    return names


def _run_record(r: sqlite3.Row) -> dict | None:
    dist_m = r["distance_m"] or 0.0
    dist_mi = dist_m / METERS_PER_MILE
    dur = r["active_duration_sec"]
    pace_sec_mi = None
    if r["avg_pace_sec_per_m"] and r["avg_pace_sec_per_m"] > 0:
        pace_sec_mi = r["avg_pace_sec_per_m"] * METERS_PER_MILE
    elif dur and dist_mi > 0:
        pace_sec_mi = dur / dist_mi
    lon = r["start_lon"] if r["start_lon"] is not None else r["w_lon"]
    local = local_datetime(r["start_time"], r["utc_offset_sec"], lon)
    gain_m = r["elevation_gain_m"] if r["elevation_gain_m"] is not None else r["gps_gain_m"]
    weather = None
    if r["temp_f"] is not None:
        weather = {
            "temp_f": round(r["temp_f"]),
            "feels_like_f": round(r["feels_like_f"]) if r["feels_like_f"] is not None else None,
            "humidity": round(r["humidity"]) if r["humidity"] is not None else None,
            "dew_point_f": round(r["dew_point_f"]) if r["dew_point_f"] is not None else None,
            "wind_mph": round(r["wind_mph"], 1) if r["wind_mph"] is not None else None,
            "condition": r["condition"],
            "weather_code": r["weather_code"],
        }
    return {
        "id": r["id"],
        "date": local.strftime("%Y-%m-%d"),
        "time": local.strftime("%H:%M"),
        "local_datetime": local.isoformat(timespec="minutes"),
        "start_time": r["start_time"],
        "distance_mi": round(dist_mi, 2),
        "duration_sec": int(dur) if dur else None,
        "duration_str": fmt_duration(dur),
        "pace_sec_mi": round(pace_sec_mi) if pace_sec_mi else None,
        "pace_str": fmt_pace(pace_sec_mi),
        "avg_hr": int(r["avg_hr"]) if r["avg_hr"] else None,
        "calories": int(r["calories"]) if r["calories"] else None,
        "cadence_spm": int(r["cadence_spm"]) if r["cadence_spm"] else None,
        "stride_cm": round(r["stride_m"] * 100, 1) if r["stride_m"] else None,
        "elevation_gain_ft": round(gain_m * FEET_PER_METER) if gain_m is not None else None,
        "altitude_ft": round(r["elevation_m"] * FEET_PER_METER) if r["elevation_m"] is not None else None,
        "has_gps": bool(r["has_gps"]),
        "has_route": bool(r["n_points"]),
        "has_hr": bool(r["n_hr"]),
        "has_splits": bool(r["n_splits"]),
        "start_lat": r["start_lat"],
        "start_lon": r["start_lon"],
        "start_bearing_deg": round(r["start_bearing_deg"]) if r["start_bearing_deg"] is not None else None,
        "heading": geo.compass_label(r["start_bearing_deg"]),
        "location_inferred": bool(r["location_inferred"]),
        "zones": {
            "light_sec": r["zone_light_sec"] or 0,
            "moderate_sec": r["zone_moderate_sec"] or 0,
            "vigorous_sec": r["zone_vigorous_sec"] or 0,
            "peak_sec": r["zone_peak_sec"] or 0,
        },
        "weather": weather,
        "group_id": r["group_id"],
        "group_name": r["group_name"],
        "same_direction": r["same_direction"],
        "source": r["source_device"] or r["source_platform"],
        "excluded_from_model": bool(r["excluded"]),
        "n_comments": r["n_comments"],
    }


def get_splits(conn: sqlite3.Connection, activity_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT split_index, distance_m, duration_sec, pace_sec_per_m FROM splits WHERE activity_id = ? ORDER BY split_index",
        (activity_id,),
    ).fetchall()
    out = []
    cum = 0.0
    for i, r in enumerate(rows):
        pace = (r["pace_sec_per_m"] or 0) * METERS_PER_MILE
        cum += r["distance_m"] / METERS_PER_MILE
        out.append(
            {
                "index": i + 1,
                "distance_mi": round(r["distance_m"] / METERS_PER_MILE, 3),
                "cumulative_mi": round(cum, 3),
                "duration_sec": round(r["duration_sec"]) if r["duration_sec"] else None,
                "pace_sec_mi": round(pace) if pace else None,
                "pace_str": fmt_pace(pace),
            }
        )
    return out


def get_hr_series(conn: sqlite3.Connection, activity_id: str) -> list[dict]:
    rows = conn.execute("SELECT t_sec, bpm FROM hr_samples WHERE activity_id = ? ORDER BY t_sec", (activity_id,)).fetchall()
    if rows:
        return [{"sec": int(r["t_sec"]), "bpm": r["bpm"]} for r in rows]
    # fall back to heart rate embedded in the TCX track
    rows = conn.execute(
        "SELECT t_sec, hr FROM route_points WHERE activity_id = ? AND hr IS NOT NULL ORDER BY seq", (activity_id,)
    ).fetchall()
    return [{"sec": int(r["t_sec"]), "bpm": r["hr"]} for r in rows]


def get_route(conn: sqlite3.Connection, activity_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT t_sec, lat, lon, alt_m, dist_m, hr FROM route_points WHERE activity_id = ? AND lat IS NOT NULL ORDER BY seq",
        (activity_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def pace_curve(points: list[dict], window_sec: float = 60.0, every_sec: float = 15.0) -> list[dict]:
    """Rolling pace (sec/mi) along the run from the TCX distance stream."""
    pts = [(p["t_sec"], p["dist_m"]) for p in points if p.get("dist_m") is not None]
    if len(pts) < 3:
        return []
    out = []
    j = 0
    last_emit = -1e9
    for i, (t, d) in enumerate(pts):
        while j < i and t - pts[j][0] > window_sec:
            j += 1
        t0, d0 = pts[j]
        dt, dd = t - t0, d - d0
        if dt < 20 or dd < 30:
            continue
        pace = dt / (dd / METERS_PER_MILE)
        if t - last_emit >= every_sec:
            out.append({"sec": int(t), "dist_mi": round(d / METERS_PER_MILE, 3), "pace_sec_mi": int(min(max(pace, 180), 1200))})
            last_emit = t
    return out


def all_similarities(conn: sqlite3.Connection) -> dict[tuple[str, str], tuple[float, float, float]]:
    rows = conn.execute("SELECT a_id, b_id, coverage_ab, coverage_ba, direction_corr FROM route_similarity").fetchall()
    return {(r["a_id"], r["b_id"]): (r["coverage_ab"], r["coverage_ba"], r["direction_corr"]) for r in rows}


def last_sync(conn: sqlite3.Connection) -> dict | None:
    r = conn.execute("SELECT * FROM sync_log ORDER BY id DESC LIMIT 1").fetchone()
    return dict(r) if r else None


def raw_activity(conn: sqlite3.Connection, activity_id: str) -> dict | None:
    r = conn.execute("SELECT raw_json FROM activities WHERE id = ?", (activity_id,)).fetchone()
    return json.loads(r["raw_json"]) if r and r["raw_json"] else None
