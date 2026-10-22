"""Turn Google Health API payloads (nested JSON, or the flattened dotted-key rows the old CSVs
used) into the row shapes the database stores. Also parses TCX route XML."""
from __future__ import annotations

import ast
import json
import math
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Iterable

import pandas as pd

TCX_NS = {"ns": "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"}


def _flat(obj: dict) -> dict:
    """Flatten nested dicts into dotted keys, like pandas.json_normalize does."""
    out: dict = {}

    def rec(o: Any, pre: str) -> None:
        if isinstance(o, dict):
            for k, v in o.items():
                rec(v, f"{pre}{k}.")
        else:
            out[pre[:-1]] = o

    rec(obj, "")
    return out


def _is_flat(dp: dict) -> bool:
    return any("." in k for k in dp)


def _num(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _dur(v: Any) -> float | None:
    """'1962s' or '0.301s' -> seconds."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return None if (isinstance(v, float) and math.isnan(v)) else float(v)
    s = str(v).strip()
    if not s or s.lower() == "nan":
        return None
    try:
        return float(s.rstrip("s"))
    except ValueError:
        return None


def _str(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    s = str(v)
    return s if s and s.lower() != "nan" else None


def _bool(v: Any) -> int:
    if isinstance(v, str):
        return 1 if v.strip().lower() == "true" else 0
    if isinstance(v, float) and math.isnan(v):
        return 0
    return 1 if v else 0


def _mm_to_m(v: float | None) -> float | None:
    return v / 1000.0 if v is not None else None


def _jsonable(v: Any) -> Any:
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, pd.Timestamp):
        return v.isoformat()
    if hasattr(v, "item"):
        try:
            return v.item()
        except Exception:
            return str(v)
    return v


def datapoint_to_activity(dp: dict) -> tuple[dict, list[dict]]:
    """Accepts either a nested API datapoint or a flattened dotted-key dict.
    Returns (activity_row, split_rows)."""
    flat = _is_flat(dp)
    f = dp if flat else _flat(dp)
    name = _str(f.get("name")) or ""
    act_id = name.split("/")[-1] if name else None
    if not act_id:
        raise ValueError("datapoint has no name/id")

    start = _str(f.get("exercise.interval.startTime"))
    if not start:
        raise ValueError(f"datapoint {act_id} has no start time")
    offset = _dur(f.get("exercise.interval.startUtcOffset"))
    dist_m = _mm_to_m(_num(f.get("exercise.metricsSummary.distanceMillimeters")))

    row = {
        "id": act_id,
        "name": name,
        "activity_type": _str(f.get("exercise.exerciseType")) or "OTHER",
        "start_time": start,
        "end_time": _str(f.get("exercise.interval.endTime")),
        "utc_offset_sec": int(offset) if offset is not None else None,
        "active_duration_sec": _dur(f.get("exercise.activeDuration")),
        "distance_m": dist_m,
        "avg_pace_sec_per_m": _num(f.get("exercise.metricsSummary.averagePaceSecondsPerMeter")),
        "avg_hr": _num(f.get("exercise.metricsSummary.averageHeartRateBeatsPerMinute")),
        "calories": _num(f.get("exercise.metricsSummary.caloriesKcal")),
        "steps": int(_num(f.get("exercise.metricsSummary.steps")) or 0) or None,
        "elevation_gain_m": _mm_to_m(_num(f.get("exercise.metricsSummary.elevationGainMillimeters"))),
        "cadence_spm": _num(f.get("exercise.metricsSummary.mobilityMetrics.avgCadenceStepsPerMinute")),
        "stride_m": _mm_to_m(_num(f.get("exercise.metricsSummary.mobilityMetrics.avgStrideLengthMillimeters"))),
        "vertical_osc_mm": _num(f.get("exercise.metricsSummary.mobilityMetrics.avgVerticalOscillationMillimeters")),
        "ground_contact_sec": _dur(f.get("exercise.metricsSummary.mobilityMetrics.avgGroundContactTimeDuration")),
        "zone_light_sec": int(_dur(f.get("exercise.metricsSummary.heartRateZoneDurations.lightTime")) or 0),
        "zone_moderate_sec": int(_dur(f.get("exercise.metricsSummary.heartRateZoneDurations.moderateTime")) or 0),
        "zone_vigorous_sec": int(_dur(f.get("exercise.metricsSummary.heartRateZoneDurations.vigorousTime")) or 0),
        "zone_peak_sec": int(_dur(f.get("exercise.metricsSummary.heartRateZoneDurations.peakTime")) or 0),
        "has_gps": _bool(f.get("exercise.exerciseMetadata.hasGps")),
        "source_platform": _str(f.get("dataSource.platform")),
        "source_device": _str(f.get("dataSource.device.displayName")),
        "raw_json": json.dumps({k: _jsonable(v) for k, v in dp.items()} if flat else dp),
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    splits = parse_splits(f.get("exercise.splits"))
    return row, [dict(activity_id=act_id, **s) for s in splits]


def parse_splits(raw: Any) -> list[dict]:
    """Splits arrive as a list of dicts from the API, or as a python-literal string in the old CSV."""
    if raw is None:
        return []
    if isinstance(raw, float) and math.isnan(raw):
        return []
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return []
        try:
            raw = ast.literal_eval(s)
        except (ValueError, SyntaxError):
            try:
                raw = json.loads(s)
            except ValueError:
                return []
    if not isinstance(raw, list):
        return []
    out = []
    for i, sp in enumerate(raw):
        if not isinstance(sp, dict):
            continue
        ms = sp.get("metricsSummary", {}) or {}
        dist_m = (_num(ms.get("distanceMillimeters")) or 0.0) / 1000.0
        pace = _num(ms.get("averagePaceSecondsPerMeter"))
        dur = _dur(sp.get("activeDuration"))
        if dist_m < 10:
            continue
        out.append(
            {
                "split_index": i,
                "distance_m": dist_m,
                "duration_sec": dur if dur is not None else (pace * dist_m if pace else None),
                "pace_sec_per_m": pace if pace else (dur / dist_m if dur and dist_m else None),
            }
        )
    return out


def parse_tcx(tcx_xml: str) -> list[dict]:
    """TCX -> list of {t_sec, lat, lon, alt_m, dist_m, hr}. t_sec is relative to the first point."""
    if not tcx_xml:
        return []
    root = ET.fromstring(tcx_xml)
    pts = []
    t0 = None
    for tp in root.iter(f"{{{TCX_NS['ns']}}}Trackpoint"):
        tnode = tp.find("ns:Time", TCX_NS)
        if tnode is None or not tnode.text:
            continue
        t = pd.Timestamp(tnode.text)
        if t0 is None:
            t0 = t
        pos = tp.find("ns:Position", TCX_NS)
        lat = lon = None
        if pos is not None:
            la = pos.find("ns:LatitudeDegrees", TCX_NS)
            lo = pos.find("ns:LongitudeDegrees", TCX_NS)
            lat = float(la.text) if la is not None and la.text else None
            lon = float(lo.text) if lo is not None and lo.text else None
        alt = tp.find("ns:AltitudeMeters", TCX_NS)
        dist = tp.find("ns:DistanceMeters", TCX_NS)
        hr = tp.find("ns:HeartRateBpm/ns:Value", TCX_NS)
        pts.append(
            {
                "t_sec": float((t - t0).total_seconds()),
                "lat": lat,
                "lon": lon,
                "alt_m": float(alt.text) if alt is not None and alt.text else None,
                "dist_m": float(dist.text) if dist is not None and dist.text else None,
                "hr": int(float(hr.text)) if hr is not None and hr.text else None,
            }
        )
    return pts


def hr_points_to_samples(points: Iterable[dict], start_time_iso: str) -> list[tuple[float, int]]:
    """API heart-rate datapoints (nested or flattened) -> (seconds since activity start, bpm)."""
    t0 = pd.Timestamp(start_time_iso)
    out = []
    for p in points:
        f = p if _is_flat(p) else _flat(p)
        ts = _str(f.get("heartRate.sampleTime.physicalTime"))
        bpm = _num(f.get("heartRate.beatsPerMinute"))
        if not ts or bpm is None:
            continue
        out.append((float((pd.Timestamp(ts) - t0).total_seconds()), int(bpm)))
    out.sort()
    return out
