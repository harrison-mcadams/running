"""HTTP API and static file serving. Run with:  python -m backend  (see backend/__main__.py)."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import pandas as pd
from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import google_health, store, sync, weather
from .config import FRONTEND_DIST, METERS_PER_MILE
from .db import db, get_setting, init_db, set_setting
from .geo import compass_label, downsample
from .importer import import_legacy
from .pace_model import service as model_service

log = logging.getLogger("strides")
app = FastAPI(title="Strides", docs_url="/api/docs", openapi_url="/api/openapi.json")


@app.on_event("startup")
def _startup() -> None:
    init_db()
    with db() as conn:
        n = conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
    if n == 0:
        with db() as conn:
            counts = import_legacy(conn)
        if counts["activities"]:
            log.info("imported legacy data: %s", counts)
            try:
                sync.enrich_offline()
            except Exception:  # noqa: BLE001
                log.exception("offline enrichment after import failed")
    sync.on_data_changed(model_service.invalidate)


# --------------------------------------------------------------------------- runs

@app.get("/api/runs")
def api_runs(include_hidden: bool = False) -> list[dict]:
    with db() as conn:
        return store.list_runs(conn, include_hidden=include_hidden)


@app.get("/api/runs/{run_id}")
def api_run(run_id: str) -> dict:
    with db() as conn:
        run = next((r for r in store.list_runs(conn, include_hidden=True) if r["id"] == run_id), None)
        if run is None:
            raise HTTPException(404, "run not found")
        route = store.get_route(conn, run_id)
        return {
            **run,
            "splits": store.get_splits(conn, run_id),
            "hr": store.get_hr_series(conn, run_id),
            "route": [{"lat": p["lat"], "lon": p["lon"], "alt_m": p["alt_m"]} for p in downsample(route, 600)],
            "pace_curve": store.pace_curve(route),
            "comments": store.get_comments(conn, run_id),
        }


def _require_run(conn, run_id: str) -> None:
    if not conn.execute("SELECT 1 FROM activities WHERE id = ?", (run_id,)).fetchone():
        raise HTTPException(404, "run not found")


@app.put("/api/runs/{run_id}/exclude")
def api_run_exclude(run_id: str, body: dict = Body(...)) -> dict:
    excluded = bool(body.get("excluded"))
    with db() as conn:
        _require_run(conn, run_id)
        store.set_excluded(conn, run_id, excluded)
    model_service.invalidate()
    return {"ok": True, "excluded_from_model": excluded}


@app.post("/api/runs/{run_id}/comments")
def api_add_comment(run_id: str, body: dict = Body(...)) -> dict:
    text = (body.get("body") or "").strip()
    if not text:
        raise HTTPException(400, "comment is empty")
    if len(text) > 4000:
        raise HTTPException(400, "comment is too long (4000 characters max)")
    with db() as conn:
        _require_run(conn, run_id)
        return store.add_comment(conn, run_id, text)


@app.delete("/api/runs/{run_id}/comments/{comment_id}")
def api_delete_comment(run_id: str, comment_id: int) -> dict:
    with db() as conn:
        if not store.delete_comment(conn, run_id, comment_id):
            raise HTTPException(404, "comment not found")
    return {"ok": True}


# --------------------------------------------------------------------------- route groups

def _group_payload(conn, runs: list[dict]) -> list[dict]:
    groups: dict[int, list[dict]] = {}
    for r in runs:
        if r["group_id"] is not None:
            groups.setdefault(r["group_id"], []).append(r)
    names = {r["group_id"]: r["name"] for r in conn.execute("SELECT group_id, name FROM group_names").fetchall()}
    autos = store.auto_group_names(runs)
    out = []
    for gid, members in sorted(groups.items()):
        ref_id = conn.execute("SELECT reference_id FROM route_groups WHERE group_id = ? LIMIT 1", (gid,)).fetchone()["reference_id"]
        ref = next((m for m in members if m["id"] == ref_id), members[0])
        dists = sorted(m["distance_mi"] for m in members)
        headings = sorted({m["heading"] for m in members if m["heading"]})
        auto = autos[gid]
        out.append(
            {
                "group_id": gid,
                "name": names.get(gid) or auto,
                "auto_name": auto,
                "custom_name": names.get(gid),
                "n_runs": len(members),
                "reference_id": ref["id"],
                "headings": headings,
                "distance_range_mi": [dists[0], dists[-1]],
                "median_distance_mi": round(dists[len(dists) // 2], 2),
                "last_date": max(m["date"] for m in members),
                "member_ids": [m["id"] for m in members],
            }
        )
    out.sort(key=lambda g: -g["n_runs"])
    return out


@app.get("/api/groups")
def api_groups() -> list[dict]:
    with db() as conn:
        return _group_payload(conn, store.list_runs(conn))


@app.put("/api/groups/{group_id}/name")
def api_group_name(group_id: int, body: dict = Body(...)) -> dict:
    name = (body.get("name") or "").strip()
    with db() as conn:
        if name:
            conn.execute(
                "INSERT INTO group_names (group_id, name) VALUES (?, ?) ON CONFLICT(group_id) DO UPDATE SET name = excluded.name",
                (group_id, name),
            )
        else:
            conn.execute("DELETE FROM group_names WHERE group_id = ?", (group_id,))
    return {"ok": True}


@app.get("/api/groups/{group_id}")
def api_group_detail(group_id: int, focus: str | None = None) -> dict:
    """Members of a route group with their mile splits and overlap with the focus run."""
    with db() as conn:
        runs = store.list_runs(conn)
        members = [r for r in runs if r["group_id"] == group_id]
        if not members:
            raise HTTPException(404, "group not found")
        groups = _group_payload(conn, runs)
        group = next(g for g in groups if g["group_id"] == group_id)
        focus_id = focus if focus in {m["id"] for m in members} else members[-1]["id"]
        sims = store.all_similarities(conn)
        for m in members:
            if m["id"] == focus_id:
                m["overlap"] = 1.0
                m["coverage_of_focus"] = 1.0
            else:
                s = sims.get((focus_id, m["id"]))
                if s:
                    cov_focus_by_m, cov_m_by_focus = s[0], s[1]
                else:
                    s2 = sims.get((m["id"], focus_id))
                    cov_focus_by_m, cov_m_by_focus = (s2[1], s2[0]) if s2 else (0.0, 0.0)
                m["overlap"] = round(min(cov_focus_by_m, cov_m_by_focus), 3)
                m["coverage_of_focus"] = round(cov_focus_by_m, 3)
            m["splits"] = store.get_splits(conn, m["id"])
        ref_route = downsample(store.get_route(conn, group["reference_id"]), 400)
        focus_route = downsample(store.get_route(conn, focus_id), 400) if focus_id != group["reference_id"] else ref_route
        return {
            "group": group,
            "focus_id": focus_id,
            "members": members,
            "reference_route": [{"lat": p["lat"], "lon": p["lon"]} for p in ref_route],
            "focus_route": [{"lat": p["lat"], "lon": p["lon"]} for p in focus_route],
        }


# --------------------------------------------------------------------------- model

@app.get("/api/model")
def api_model(variant: str = "conditions") -> dict:
    if variant not in ("conditions", "effort"):
        raise HTTPException(400, "variant must be conditions or effort")
    return model_service.summary(variant)


@app.post("/api/model/predict")
def api_predict(body: dict = Body(...)) -> dict:
    variant = body.get("variant", "conditions")
    if variant not in ("conditions", "effort"):
        raise HTTPException(400, "variant must be conditions or effort")
    return model_service.predict(variant, body.get("inputs", {}))


@app.get("/api/conditions")
def api_conditions() -> dict:
    """Sensible defaults for the predictor form: now, here, current weather, recent training."""
    with db() as conn:
        runs = store.list_runs(conn)
    now = datetime.now()
    out = {
        "date": now.strftime("%Y-%m-%d"),
        "local_hour": round(now.hour + now.minute / 60.0, 2),
        "temp_f": None,
        "humidity": None,
        "days_since_last_run": None,
        "recent_7d_miles": 0.0,
        "altitude_kft": None,
        "elev_gain_ft_per_mi": None,
        "distance_mi": None,
        "location": None,
    }
    if runs:
        last = runs[-1]
        last_dt = pd.Timestamp(last["local_datetime"])
        out["days_since_last_run"] = round(min(10.0, max(0.5, (pd.Timestamp(now) - last_dt).total_seconds() / 86400.0)), 1)
        out["recent_7d_miles"] = round(sum(r["distance_mi"] for r in runs if pd.Timestamp(r["local_datetime"]) >= pd.Timestamp(now) - pd.Timedelta(days=7)), 1)
        recent = [r for r in runs[-10:] if r["start_lat"] is not None]
        loc = recent[-1] if recent else None
        if loc:
            out["location"] = {"lat": loc["start_lat"], "lon": loc["start_lon"]}
            cur = weather.fetch_current(loc["start_lat"], loc["start_lon"])
            if cur:
                out.update(cur)
            if loc["altitude_ft"] is not None:
                out["altitude_kft"] = round(loc["altitude_ft"] / 1000.0, 2)
        dists = sorted(r["distance_mi"] for r in runs[-10:])
        out["distance_mi"] = dists[len(dists) // 2]
        gains = [r["elevation_gain_ft"] / r["distance_mi"] for r in runs[-10:] if r["elevation_gain_ft"] is not None]
        if gains:
            out["elev_gain_ft_per_mi"] = round(sorted(gains)[len(gains) // 2], 1)
    return out


# --------------------------------------------------------------------------- sync & auth

@app.post("/api/sync")
def api_sync(full: bool = False) -> dict:
    started = sync.start_sync(full=full)
    return {"started": started, **sync.status()}


@app.get("/api/sync/status")
def api_sync_status() -> dict:
    return sync.status()


@app.get("/api/auth/status")
def api_auth_status() -> dict:
    return google_health.credential_status()


@app.post("/api/auth/client")
def api_auth_client(body: dict = Body(...)) -> dict:
    cid, secret = body.get("client_id", ""), body.get("client_secret", "")
    if not cid or not secret:
        raise HTTPException(400, "client_id and client_secret are required")
    google_health.set_client(cid, secret)
    return {"ok": True}


@app.post("/api/auth/token")
def api_auth_token(body: dict = Body(...)) -> dict:
    token = (body.get("refresh_token") or "").strip()
    if not token:
        raise HTTPException(400, "refresh_token is required")
    google_health.set_refresh_token(token)
    return {"ok": True}


def _redirect_uri(request: Request) -> str:
    return str(request.url_for("api_auth_callback"))


@app.get("/api/auth/google")
def api_auth_google(request: Request):
    try:
        return RedirectResponse(google_health.build_auth_url(_redirect_uri(request)))
    except google_health.AuthError as e:
        raise HTTPException(400, str(e))


@app.get("/api/auth/google/callback", name="api_auth_callback")
def api_auth_callback(request: Request, code: str | None = None, error: str | None = None):
    if error or not code:
        return HTMLResponse(_callback_page(False, error or "no authorization code returned"))
    try:
        google_health.exchange_code(code, _redirect_uri(request))
    except google_health.AuthError as e:
        return HTMLResponse(_callback_page(False, str(e)))
    return HTMLResponse(_callback_page(True, "Google account connected. You can close this tab and sync."))


def _callback_page(ok: bool, msg: str) -> str:
    color = "#0a7a3b" if ok else "#b42318"
    title = "Connected" if ok else "Connection failed"
    return f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
    <title>{title}</title></head>
    <body style='font-family:system-ui,sans-serif;max-width:480px;margin:15vh auto;padding:0 24px;color:#1b1b1b'>
    <h2 style='color:{color}'>{title}</h2><p style='font-size:16px;line-height:1.5'>{msg}</p>
    <p><a href='/' style='color:#2a78d6'>Back to Strides</a></p></body></html>"""


# --------------------------------------------------------------------------- settings

SETTING_KEYS = ["hidden_before", "sync_from", "min_distance_mi", "max_pace_sec_mi", "match_radius_m", "group_coverage"]


@app.get("/api/settings")
def api_settings() -> dict:
    with db() as conn:
        return {k: get_setting(conn, k) for k in SETTING_KEYS}


@app.put("/api/settings")
def api_settings_put(body: dict = Body(...)) -> dict:
    regroup = False
    with db() as conn:
        for k, v in body.items():
            if k not in SETTING_KEYS:
                raise HTTPException(400, f"unknown setting {k}")
            set_setting(conn, k, str(v))
            if k in ("match_radius_m", "group_coverage"):
                regroup = True
    if regroup:
        with db() as conn:
            conn.execute("DELETE FROM route_similarity")
        sync.update_similarity_and_groups()
    model_service.invalidate()
    return api_settings()


# --------------------------------------------------------------------------- static frontend

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        target = FRONTEND_DIST / path
        if path and target.is_file():
            return FileResponse(target)
        return FileResponse(FRONTEND_DIST / "index.html")
else:

    @app.get("/", include_in_schema=False)
    def no_frontend():
        return JSONResponse({"detail": "frontend not built; run `npm run build` in frontend/"}, status_code=503)
