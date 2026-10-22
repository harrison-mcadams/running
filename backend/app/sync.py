"""Sync pipeline: pull new exercises from Google, then enrich runs (routes, heart rate,
weather, terrain elevation, route similarity and grouping). Runs in a background thread;
the API polls `state` for progress."""
from __future__ import annotations

import logging
import threading
import traceback
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone

import pandas as pd

from . import geo, store, weather
from .db import db, get_setting
from .google_health import HealthClient
from .parsing import datapoint_to_activity, hr_points_to_samples, parse_tcx

log = logging.getLogger("strides.sync")


@dataclass
class SyncState:
    running: bool = False
    phase: str = ""
    message: str = ""
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    new_activities: int = 0
    log: list[str] = field(default_factory=list)

    def note(self, msg: str) -> None:
        self.message = msg
        self.log.append(msg)
        self.log = self.log[-50:]
        log.info(msg)


state = SyncState()
_thread: threading.Thread | None = None
_on_data_changed: list = []


def on_data_changed(cb) -> None:
    _on_data_changed.append(cb)


def _notify() -> None:
    for cb in _on_data_changed:
        try:
            cb()
        except Exception:  # pragma: no cover
            log.exception("data-changed callback failed")


def start_sync(full: bool = False) -> bool:
    """Kick off a background sync. Returns False if one is already running."""
    global _thread
    if state.running:
        return False
    state.running = True
    state.error = None
    state.finished_at = None
    state.new_activities = 0
    state.log = []
    state.started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _thread = threading.Thread(target=_run, args=(full,), daemon=True)
    _thread.start()
    return True


def _run(full: bool) -> None:
    log_id = None
    try:
        with db() as conn:
            cur = conn.execute("INSERT INTO sync_log (started_at, status) VALUES (?, 'running')", (state.started_at,))
            log_id = cur.lastrowid
        state.phase = "google"
        state.note("Connecting to Google...")
        client = HealthClient()
        new = pull_exercises(client, full)
        state.new_activities = new
        enrich(client)
        status, msg = "ok", f"Synced. {new} new activities."
    except Exception as e:  # noqa: BLE001
        state.error = str(e)
        status, msg = "error", str(e)
        log.error("sync failed: %s\n%s", e, traceback.format_exc())
    finally:
        state.running = False
        state.finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        state.phase = "done"
        state.note(msg)
        with db() as conn:
            conn.execute(
                "UPDATE sync_log SET finished_at = ?, status = ?, message = ?, new_activities = ? WHERE id = ?",
                (state.finished_at, status, msg, state.new_activities, log_id),
            )
        _notify()


def pull_exercises(client: HealthClient, full: bool) -> int:
    with db() as conn:
        last = conn.execute("SELECT MAX(start_time) AS t FROM activities").fetchone()["t"]
        sync_from = get_setting(conn, "sync_from")
    if full or not last:
        since = f"{sync_from}T00:00:00Z"
    else:
        # Re-fetch a two-week window so late edits on the watch are picked up.
        since = (pd.Timestamp(last) - timedelta(days=14)).strftime("%Y-%m-%dT%H:%M:%SZ")
    state.note(f"Fetching exercises since {since[:10]}...")
    points = client.exercises_since(since)
    new = 0
    with db() as conn:
        for dp in points:
            try:
                row, splits = datapoint_to_activity(dp)
            except ValueError as e:
                log.warning("skipping datapoint: %s", e)
                continue
            if store.upsert_activity(conn, row, splits):
                new += 1
    state.note(f"{len(points)} exercises fetched, {new} new.")
    return new


def _runs_needing(conn, what: str) -> list[dict]:
    if what == "route":
        sql = """SELECT a.id, a.name, a.start_time, a.end_time FROM activities a
                 LEFT JOIN route_meta rm ON rm.activity_id = a.id
                 WHERE a.activity_type = 'RUNNING' AND a.has_gps = 1
                   AND (rm.activity_id IS NULL
                        OR (rm.n_points = 0 AND rm.fetch_error IS NULL)
                        OR (rm.n_points = 0 AND rm.fetched_at < ?))"""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat(timespec="seconds")
        return [dict(r) for r in conn.execute(sql, (cutoff,)).fetchall()]
    if what == "hr":
        sql = """SELECT a.id, a.name, a.start_time, a.end_time FROM activities a
                 WHERE a.activity_type = 'RUNNING' AND a.avg_hr > 0 AND a.end_time > a.start_time
                   AND NOT EXISTS (SELECT 1 FROM hr_samples h WHERE h.activity_id = a.id)"""
        return [dict(r) for r in conn.execute(sql).fetchall()]
    raise ValueError(what)


def enrich(client: HealthClient | None) -> None:
    """Fill in everything derived. `client` may be None for offline enrichment (after import)."""
    if client is not None:
        state.phase = "routes"
        with db() as conn:
            todo = _runs_needing(conn, "route")
        for i, r in enumerate(todo, 1):
            state.note(f"Downloading GPS route {i}/{len(todo)}...")
            try:
                pts = parse_tcx(client.exercise_tcx(r["name"]))
                with db() as conn:
                    if pts:
                        store.store_route(conn, r["id"], pts, geo.elevation_gain_m(pts))
                    else:
                        store.mark_route_failed(conn, r["id"], "empty TCX")
            except Exception as e:  # noqa: BLE001
                with db() as conn:
                    store.mark_route_failed(conn, r["id"], str(e))

        state.phase = "heart rate"
        with db() as conn:
            todo = _runs_needing(conn, "hr")
        for i, r in enumerate(todo, 1):
            state.note(f"Downloading heart rate {i}/{len(todo)}...")
            try:
                samples = hr_points_to_samples(client.heart_rate_between(r["start_time"], r["end_time"]), r["start_time"])
                if samples:
                    with db() as conn:
                        store.store_hr(conn, r["id"], samples)
            except Exception as e:  # noqa: BLE001
                log.warning("HR fetch failed for %s: %s", r["id"], e)

    enrich_offline()


def enrich_offline() -> None:
    """Weather, elevation, similarity and groups. Needs only Open-Meteo, not Google."""
    state.phase = "weather"
    with db() as conn:
        n = store.infer_locations(conn)
        if n:
            state.note(f"Borrowed a start location for {n} runs without GPS.")
        runs = conn.execute(
            """SELECT a.id, a.start_time, rm.start_lat, rm.start_lon FROM activities a
               LEFT JOIN route_meta rm ON rm.activity_id = a.id
               LEFT JOIN weather w ON w.activity_id = a.id
               WHERE a.activity_type = 'RUNNING' AND w.activity_id IS NULL ORDER BY a.start_time"""
        ).fetchall()
        known = conn.execute(
            """SELECT a.start_time, rm.start_lat, rm.start_lon FROM activities a
               JOIN route_meta rm ON rm.activity_id = a.id WHERE rm.start_lat IS NOT NULL ORDER BY a.start_time"""
        ).fetchall()
    for i, r in enumerate(runs, 1):
        lat, lon = r["start_lat"], r["start_lon"]
        if lat is None:
            lat, lon = _nearest_known_location(known, r["start_time"])
        if lat is None:
            continue
        state.note(f"Fetching weather {i}/{len(runs)}...")
        w = weather.fetch_weather(lat, lon, r["start_time"])
        if w:
            with db() as conn:
                store.store_weather(conn, r["id"], w)

    state.phase = "elevation"
    with db() as conn:
        todo = conn.execute(
            "SELECT activity_id, start_lat, start_lon FROM route_meta WHERE start_lat IS NOT NULL AND elevation_m IS NULL"
        ).fetchall()
    for i, r in enumerate(todo, 1):
        state.note(f"Looking up terrain elevation {i}/{len(todo)}...")
        elev = weather.fetch_elevation(r["start_lat"], r["start_lon"])
        if elev is not None:
            with db() as conn:
                conn.execute("UPDATE route_meta SET elevation_m = ? WHERE activity_id = ?", (elev, r["activity_id"]))

    state.phase = "routes"
    update_similarity_and_groups()


def _nearest_known_location(known, start_time: str) -> tuple[float | None, float | None]:
    if not known:
        return None, None
    t = pd.Timestamp(start_time)
    best = min(known, key=lambda k: abs((pd.Timestamp(k["start_time"]) - t).total_seconds()))
    return best["start_lat"], best["start_lon"]


def update_similarity_and_groups() -> None:
    """Compute similarity for every pair of visible runs that lacks it, then rebuild groups."""
    with db() as conn:
        radius = float(get_setting(conn, "match_radius_m"))
        thr = float(get_setting(conn, "group_coverage"))
        runs = store.list_runs(conn)
        ids = [r["id"] for r in runs if r["has_route"]]
        existing = store.all_similarities(conn)
        tracks: dict[str, geo.Track] = {}
        missing = [(a, b) for i, a in enumerate(ids) for b in ids[i + 1:] if (a, b) not in existing and (b, a) not in existing]
        if missing:
            needed = {x for pair in missing for x in pair}
            for rid in needed:
                tr = geo.resample(store.get_route(conn, rid))
                if tr is not None:
                    tracks[rid] = tr
    for n, (a, b) in enumerate(missing, 1):
        if n % 20 == 0:
            state.note(f"Comparing routes {n}/{len(missing)}...")
        ta, tb = tracks.get(a), tracks.get(b)
        sim = geo.similarity(ta, tb, radius) if ta is not None and tb is not None else (0.0, 0.0, 0.0)
        existing[(a, b)] = sim
        with db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO route_similarity (a_id, b_id, coverage_ab, coverage_ba, direction_corr) VALUES (?, ?, ?, ?, ?)",
                (a, b, *sim),
            )
    state.note("Grouping routes...")
    with db() as conn:
        lengths, bearings = {}, {}
        for rid in ids:
            row = conn.execute("SELECT MAX(dist_m) AS d FROM route_points WHERE activity_id = ?", (rid,)).fetchone()
            lengths[rid] = row["d"] or 0.0
            rm = conn.execute("SELECT start_bearing_deg FROM route_meta WHERE activity_id = ?", (rid,)).fetchone()
            bearings[rid] = rm["start_bearing_deg"] if rm else None
        groups = geo.build_groups(ids, existing, lengths, bearings, thr)
        conn.execute("DELETE FROM route_groups")
        conn.executemany(
            "INSERT INTO route_groups (activity_id, group_id, reference_id, same_direction) VALUES (?, ?, ?, ?)",
            [(rid, g, ref, same) for rid, (g, ref, same) in groups.items()],
        )


def status() -> dict:
    d = asdict(state)
    with db() as conn:
        d["last_sync"] = store.last_sync(conn)
    return d
