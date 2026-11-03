"""Line runs up by place rather than by distance from the start.

Each run is matched point by point to a reference track (the run being compared against). The
match is a dynamic-programming alignment with two rules:

* it only moves forward along the reference, so on an out-and-back the way out can never be
  matched to the reference's way back, even though both pass the same spot;
* any run point further than `radius_m` from the reference is "off route" and left unmatched,
  at a fixed cost per point, so detours and extra turnaround distance simply drop out.

The reference may also be skipped over freely, so a run that turned around earlier, or whose GPS
started late, matches only the stretches it actually covered.
"""
from __future__ import annotations

import math

import numpy as np

from .config import METERS_PER_MILE
from .store import moving_time_curve, pace_at

SAMPLE_M = 25.0


def samples(points: list[dict], step_m: float = SAMPLE_M) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    """Points with GPS and watch distance, thinned to one every `step_m` metres of watch distance.
    Returns (lat, lon, dist_m)."""
    pts = [p for p in points if p.get("lat") is not None and p.get("lon") is not None and p.get("dist_m") is not None]
    if len(pts) < 10:
        return None
    lat, lon, dist, last = [], [], [], -1e9
    for p in pts:
        if p["dist_m"] - last >= step_m:
            lat.append(p["lat"])
            lon.append(p["lon"])
            dist.append(p["dist_m"])
            last = p["dist_m"]
    if len(dist) < 5:
        return None
    return np.array(lat), np.array(lon), np.array(dist)


def _xy(lat: np.ndarray, lon: np.ndarray, lat0: float, lon0: float) -> np.ndarray:
    k_lat = 111132.0
    k_lon = 111320.0 * math.cos(math.radians(lat0))
    return np.stack([(lon - lon0) * k_lon, (lat - lat0) * k_lat], axis=1)


def align(run_xy: np.ndarray, ref_xy: np.ndarray, radius_m: float = 60.0) -> np.ndarray:
    """For each run point, the index of the matched reference point, or -1 when off route.

    State per (run point i, reference point j): either "on" (i matched to j) or "off" (i
    unmatched, last match at or before j). Both take their predecessor from the cheapest state at
    i-1 with reference index <= j, which enforces forward-only matching and lets the reference be
    skipped. On costs the distance in metres; off costs radius_m; matches beyond radius_m are
    forbidden."""
    n, m = len(run_xy), len(ref_xy)
    dist = np.sqrt(((run_xy[:, None, :] - ref_xy[None, :, :]) ** 2).sum(axis=2))
    on_cost = np.where(dist <= radius_m, dist, np.inf)
    off_cost = radius_m

    arg_k = np.empty((n, m), dtype=np.int32)    # prefix-argmin over reference index, per row
    is_on = np.empty((n, m), dtype=bool)        # whether the cheaper state at (i, j) is "on"
    idx = np.arange(m)

    def prefix_min(row: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        best = np.minimum.accumulate(row)
        # index where each running minimum was achieved
        pos = np.where(row == best, idx, 0)
        return best, np.maximum.accumulate(pos)

    d_on = on_cost[0]
    d_off = np.full(m, off_cost)
    comb = np.minimum(d_on, d_off)
    is_on[0] = d_on <= d_off
    best, arg_k[0] = prefix_min(comb)
    for i in range(1, n):
        d_on = on_cost[i] + best
        d_off = off_cost + best
        comb = np.minimum(d_on, d_off)
        is_on[i] = d_on <= d_off
        best, arg_k[i] = prefix_min(comb)

    out = np.full(n, -1, dtype=np.int32)
    j = int(arg_k[n - 1][m - 1])
    for i in range(n - 1, -1, -1):
        if is_on[i][j]:
            out[i] = j
        if i:
            j = int(arg_k[i - 1][j])
    return out


_CACHE: dict[tuple, list[list[float]]] = {}


def aligned_profile(
    ref_id: str,
    ref_points: list[dict],
    run_id: str,
    run_points: list[dict],
    radius_m: float = 60.0,
    step_mi: float = 0.05,
    half_window_mi: float = 0.1,
) -> list[list[float]]:
    """The run's pace placed at the matching position along the reference, on the same 0.05 mi
    grid as the reference's own profile. Grid cells the run never passed through are absent."""
    key = (ref_id, run_id, len(ref_points), len(run_points), radius_m)
    if key in _CACHE:
        return _CACHE[key]
    out: list[list[float]] = []
    ref = samples(ref_points)
    run = samples(run_points)
    curve = moving_time_curve(run_points)
    if ref is not None and run is not None and curve is not None:
        lat0, lon0 = float(ref[0][0]), float(ref[1][0])
        match = align(_xy(run[0], run[1], lat0, lon0), _xy(ref[0], ref[1], lat0, lon0), radius_m)
        run_mi = run[2] / METERS_PER_MILE
        total = float(curve[0][-1])
        ok = (match >= 0) & (run_mi >= half_window_mi) & (run_mi <= total - half_window_mi)
        if ok.any():
            pace = pace_at(curve, run_mi[ok], half_window_mi)
            ref_mi = ref[2][match[ok]] / METERS_PER_MILE
            cells = np.round(ref_mi / step_mi).astype(int)
            sums: dict[int, list[float]] = {}
            for c, p in zip(cells, pace):
                if p > 0:
                    sums.setdefault(int(c), []).append(float(p))
            out = [
                [round(c * step_mi, 2), int(min(max(sum(v) / len(v), 180.0), 1200.0))]
                for c, v in sorted(sums.items())
                if c * step_mi >= half_window_mi
            ]
    _CACHE[key] = out
    return out
