# Strides

A personal running dashboard. It pulls runs from the Google Health API (Pixel Watch via
Fitbit), stores them in SQLite, and gives you three views:

1. **Runs**: every run, filterable by period, distance and route, with charts and a per-run
   detail sheet (map, mile splits, rolling pace, heart rate, zones, weather).
2. **Routes**: runs grouped automatically by the trail they follow. Pick a route and a run,
   then compare it with the similar runs: direction out, distance tolerance and route
   overlap are all filters.
3. **Pace model**: a ridge regression of pace on distance, weather, time of day, rest,
   weekly mileage, hilliness, altitude and training time. It reports effect sizes with
   bootstrap intervals, predicts a pace for a planned run, shows one-factor sensitivity
   curves, and plots a conditions-adjusted fitness trend. A second variant adds average
   heart rate as an effort control.

## Layout

```
backend/            FastAPI app (python -m backend)
  app/config.py     paths and default settings
  app/db.py         SQLite schema
  app/google_health.py  OAuth + Google Health API client
  app/sync.py       background sync pipeline (exercises, routes, HR, weather, elevation, grouping)
  app/importer.py   one-time import of the old CSV / TCX / HR files
  app/geo.py        route resampling, similarity, direction, grouping, elevation gain
  app/pace_model.py the linear pace model
  app/store.py      queries and the derived run record
  app/main.py       HTTP API and static serving
frontend/           Vite + React + TypeScript (built output in frontend/dist, committed)
legacy/             the previous app, kept for reference and for the first import
data/               strides.db (created on first start; not committed)
credentials.json    {"client_id", "client_secret", "refresh_token"} (not committed)
```

## Run it

```bash
pip install -r requirements.txt
python -m backend --port 8088
```

Open http://localhost:8088. On first start, if the database is empty, the server imports
everything it can find in `legacy/` (and the repository root), then computes weather,
elevation and route groups. That takes a minute the first time.

To rebuild the frontend after changing it (needs Node, not needed on the Pi):

```bash
cd frontend && npm install && npm run build
```

For frontend development with hot reload, run the backend on port 8089 and `npm run dev`;
the dev server proxies `/api` to it.

## Google connection

Settings → Connect Google. The server builds the redirect URI from the host you opened it
on, so add `http://<host>:<port>/api/auth/google/callback` to the OAuth client's authorized
redirect URIs in Google Cloud Console. The refresh token is written to `credentials.json`.
If you prefer, paste a refresh token or the client id/secret directly in Settings.

Sync runs in the background. It fetches exercises from the last two weeks (or the full
history on a full re-sync), then downloads GPS tracks and heart-rate samples for new runs,
looks up the weather and terrain elevation at each start point, scores route similarity and
regroups routes. The pace model refits on the next request.

## Raspberry Pi

```ini
# /etc/systemd/system/strides.service
[Unit]
Description=Strides running dashboard
After=network-online.target

[Service]
WorkingDirectory=/home/pi/running
ExecStart=/home/pi/running/.venv/bin/python -m backend --port 8088
Restart=on-failure
User=pi

[Install]
WantedBy=multi-user.target
```

`git pull` on the Pi brings the built frontend along; restart the service afterwards.

## Settings (stored in the database)

| key | default | meaning |
|---|---|---|
| hidden_before | 2025-12-29 | runs before this date are stored but hidden (pre-watch phone runs) |
| sync_from | 2025-01-01 | first sync fetches exercises from this date |
| min_distance_mi | 0.5 | shorter activities are hidden |
| max_pace_sec_mi | 900 | slower activities are hidden |
| match_radius_m | 60 | two tracks "share" a point when within this distance |
| group_coverage | 0.8 | the shorter run must be this covered by the longer one to share a route |
