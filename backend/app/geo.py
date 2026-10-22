"""Route geometry: resampling, similarity between two runs, direction detection, grouping
runs that follow the same trail, and elevation gain from GPS altitude."""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

EARTH_R = 6371000.0


def haversine_m(lat1: np.ndarray, lon1: np.ndarray, lat2: np.ndarray, lon2: np.ndarray) -> np.ndarray:
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = p2 - p1
    dl = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * EARTH_R * np.arcsin(np.sqrt(a))


def cumulative_distance_m(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    if len(lat) == 0:
        return np.array([])
    seg = haversine_m(lat[:-1], lon[:-1], lat[1:], lon[1:])
    return np.concatenate([[0.0], np.cumsum(seg)])


@dataclass
class Track:
    """A route resampled to points every `step_m` metres along the path."""

    lat: np.ndarray
    lon: np.ndarray
    cum_m: np.ndarray

    @property
    def length_m(self) -> float:
        return float(self.cum_m[-1]) if len(self.cum_m) else 0.0

    def xy(self, ref_lat: float, ref_lon: float) -> np.ndarray:
        """Flat-earth metres relative to a reference point: shape (n, 2)."""
        k_lat = 111132.0
        k_lon = 111320.0 * math.cos(math.radians(ref_lat))
        return np.stack([(self.lon - ref_lon) * k_lon, (self.lat - ref_lat) * k_lat], axis=1)


def resample(points: list[dict], step_m: float = 50.0) -> Track | None:
    """Resample raw GPS points to equal distance spacing. Drops points without position."""
    lat = np.array([p["lat"] for p in points if p.get("lat") is not None and p.get("lon") is not None], dtype=float)
    lon = np.array([p["lon"] for p in points if p.get("lat") is not None and p.get("lon") is not None], dtype=float)
    if len(lat) < 5:
        return None
    cum = cumulative_distance_m(lat, lon)
    total = cum[-1]
    if total < 200:
        return None
    # cum must be strictly increasing for interpolation
    keep = np.concatenate([[True], np.diff(cum) > 0])
    lat, lon, cum = lat[keep], lon[keep], cum[keep]
    targets = np.arange(0.0, total, step_m)
    return Track(lat=np.interp(targets, cum, lat), lon=np.interp(targets, cum, lon), cum_m=targets)


def similarity(a: Track, b: Track, radius_m: float = 60.0) -> tuple[float, float, float]:
    """Returns (coverage_ab, coverage_ba, direction_corr).

    coverage_ab = fraction of A's points that lie within radius_m of B's path.
    direction_corr = rank correlation between A's point order and the order of the nearest
    B point, over the matched points. +1 means both runs traverse the shared path the same
    way, -1 means opposite directions.
    """
    ref_lat, ref_lon = float(a.lat[0]), float(a.lon[0])
    xa, xb = a.xy(ref_lat, ref_lon), b.xy(ref_lat, ref_lon)
    d = np.sqrt(((xa[:, None, :] - xb[None, :, :]) ** 2).sum(axis=2))  # (na, nb)
    nearest_b = d.argmin(axis=1)
    match_a = d.min(axis=1) <= radius_m
    match_b = d.min(axis=0) <= radius_m
    cov_ab = float(match_a.mean())
    cov_ba = float(match_b.mean())
    corr = 0.0
    if match_a.sum() >= 5:
        ia = np.nonzero(match_a)[0].astype(float)
        ib = nearest_b[match_a].astype(float)
        if ib.std() > 0 and ia.std() > 0:
            corr = float(np.corrcoef(_rank(ia), _rank(ib))[0, 1])
    return cov_ab, cov_ba, corr


def _rank(x: np.ndarray) -> np.ndarray:
    order = x.argsort()
    r = np.empty_like(order, dtype=float)
    r[order] = np.arange(len(x), dtype=float)
    return r


def start_bearing_deg(track: Track, along_m: float = 800.0) -> float | None:
    """Compass bearing (0 = north, 90 = east) from the start to the point `along_m` metres
    into the run. For out-and-back runs from a fixed start this is the "direction" a runner
    means when they say they went one way or the other."""
    if track.length_m < along_m * 0.5:
        return None
    idx = int(np.searchsorted(track.cum_m, min(along_m, track.length_m - 1)))
    idx = max(1, min(idx, len(track.lat) - 1))
    lat1, lon1 = math.radians(track.lat[0]), math.radians(track.lon[0])
    lat2, lon2 = math.radians(track.lat[idx]), math.radians(track.lon[idx])
    dlon = lon2 - lon1
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def compass_label(bearing: float | None) -> str | None:
    if bearing is None:
        return None
    names = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return names[int(((bearing + 22.5) % 360) // 45)]


def bearings_agree(a: float | None, b: float | None, tol_deg: float = 60.0) -> int | None:
    if a is None or b is None:
        return None
    diff = abs((a - b + 180.0) % 360.0 - 180.0)
    return 1 if diff <= tol_deg else 0


class UnionFind:
    def __init__(self, ids: list[str]) -> None:
        self.parent = {i: i for i in ids}

    def find(self, i: str) -> str:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def build_groups(
    ids: list[str],
    sims: dict[tuple[str, str], tuple[float, float, float]],
    lengths_m: dict[str, float],
    bearings: dict[str, float | None],
    coverage_threshold: float = 0.8,
) -> dict[str, tuple[int, str, int | None]]:
    """Group runs that share a trail: two runs are linked when the shorter one is at least
    `coverage_threshold` covered by the longer one. Out-and-backs, loops run in either
    direction, and extended/shortened variants therefore land in the same group.

    Returns {activity_id: (group_id, reference_id, same_direction)} where group ids are
    assigned 1..n by descending group size, and same_direction compares each run's start
    bearing with the group's reference run (the member most covered by the others)."""
    uf = UnionFind(ids)
    for (a, b), (cov_ab, cov_ba, _) in sims.items():
        if a in uf.parent and b in uf.parent and max(cov_ab, cov_ba) >= coverage_threshold:
            uf.union(a, b)

    members: dict[str, list[str]] = {}
    for i in ids:
        members.setdefault(uf.find(i), []).append(i)

    def centrality(i: str, group: list[str]) -> float:
        tot = 0.0
        for j in group:
            if j == i:
                continue
            s = sims.get((i, j)) or _swap(sims.get((j, i)))
            if s:
                tot += s[0]  # how much of i is covered by j
        return tot

    groups = sorted(members.values(), key=lambda g: (-len(g), -max(lengths_m.get(i, 0) for i in g)))
    out: dict[str, tuple[int, str, int | None]] = {}
    for gid, group in enumerate(groups, start=1):
        ref = max(group, key=lambda i: (centrality(i, group), lengths_m.get(i, 0)))
        for i in group:
            if i == ref:
                out[i] = (gid, ref, 1)
                continue
            out[i] = (gid, ref, bearings_agree(bearings.get(i), bearings.get(ref)))
    return out


def _swap(s: tuple[float, float, float] | None) -> tuple[float, float, float] | None:
    return None if s is None else (s[1], s[0], s[2])


def elevation_gain_m(points: list[dict], window: int = 15, min_climb_m: float = 3.0) -> float | None:
    """Sum of climbs from smoothed GPS altitude, counting a climb only once it exceeds
    min_climb_m (hysteresis) so GPS jitter does not inflate the total."""
    alt = np.array([p["alt_m"] for p in points if p.get("alt_m") is not None], dtype=float)
    if len(alt) < window * 2:
        return None
    kernel = np.ones(window) / window
    smooth = np.convolve(alt, kernel, mode="valid")
    gain = 0.0
    base = smooth[0]
    for v in smooth[1:]:
        if v - base >= min_climb_m:
            gain += v - base
            base = v
        elif v < base:
            base = v
    return float(gain)


def downsample(points: list[dict], n: int = 400) -> list[dict]:
    if len(points) <= n:
        return points
    idx = np.linspace(0, len(points) - 1, n).round().astype(int)
    return [points[i] for i in idx]
