"""Linear model of what moves your pace.

One ridge regression per variant ("conditions" and "effort", the latter adding average heart
rate as a control). Features are kept in natural units so every coefficient reads as
"seconds per mile per unit". The ridge penalty is chosen by leave-one-out cross-validation,
and uncertainty comes from bootstrap resampling, so with a few dozen runs the output stays
honest about what it does and does not know."""
from __future__ import annotations

import threading
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from . import store
from .db import db

# (key, label, unit, description, plausible range for sliders)
FEATURES = [
    ("distance_mi", "Distance", "mi", "Longer runs are paced slower.", (1.0, 15.0)),
    ("temp_f", "Temperature", "°F", "Air temperature at the start of the run.", (20.0, 100.0)),
    ("humidity", "Humidity", "%", "Relative humidity at the start of the run.", (10.0, 100.0)),
    ("local_hour", "Time of day", "h", "Local start time, as hours after midnight.", (5.0, 21.0)),
    ("days_since_last_run", "Rest days", "days", "Days since the previous run (capped at 10).", (0.5, 10.0)),
    ("recent_7d_miles", "7-day mileage", "mi", "Miles run in the 7 days before this run.", (0.0, 40.0)),
    ("elev_gain_ft_per_mi", "Hilliness", "ft/mi", "Elevation gain per mile.", (0.0, 150.0)),
    ("weeks", "Training time", "weeks", "Weeks since your first run on record: the fitness trend.", (0.0, 104.0)),
]
EFFORT_FEATURE = ("avg_hr", "Heart rate", "bpm", "Average heart rate: how hard you were working.", (120.0, 190.0))

ALPHAS = [0.03, 0.1, 0.3, 1.0, 3.0, 10.0, 30.0, 100.0]
BOOTSTRAPS = 300


def build_frame(runs: list[dict]) -> pd.DataFrame:
    """Per-run feature table. Runs lacking weather are dropped; missing terrain fields are
    filled with the median of the rest (almost always the home trail)."""
    # Runs flagged "exclude from model" still count toward rest days and 7-day mileage
    # of the runs after them, so build features on everything and drop them at the end.
    df = pd.DataFrame(runs)
    if df.empty:
        return df
    df["local_dt"] = pd.to_datetime(df["local_datetime"])
    df = df.sort_values("local_dt").reset_index(drop=True)
    df["temp_f"] = df["weather"].apply(lambda w: w.get("temp_f") if w else None)
    df["humidity"] = df["weather"].apply(lambda w: w.get("humidity") if w else None)
    df["local_hour"] = df["local_dt"].dt.hour + df["local_dt"].dt.minute / 60.0
    gaps = df["local_dt"].diff().dt.total_seconds() / 86400.0
    df["days_since_last_run"] = gaps.fillna(7.0).clip(upper=10.0)
    df["recent_7d_miles"] = [
        float(df.loc[(df["local_dt"] < t) & (df["local_dt"] >= t - pd.Timedelta(days=7)), "distance_mi"].sum())
        for t in df["local_dt"]
    ]
    df["elev_gain_ft_per_mi"] = df["elevation_gain_ft"] / df["distance_mi"]
    df["weeks"] = (df["local_dt"] - df["local_dt"].min()).dt.total_seconds() / (7 * 86400.0)
    for col in ("elev_gain_ft_per_mi",):
        df[col] = df[col].fillna(df[col].median()).fillna(0.0)
    keep = df["temp_f"].notna() & df["pace_sec_mi"].notna()
    if "excluded_from_model" in df:
        keep &= ~df["excluded_from_model"].astype(bool)
    df = df[keep].reset_index(drop=True)
    return df


@dataclass
class Fitted:
    variant: str
    feature_keys: list[str]       # features actually in the model
    inactive_keys: list[str]      # features with no useful variation in the data yet
    scaler: StandardScaler
    model: Ridge
    alpha: float
    df: pd.DataFrame
    loo_residuals: np.ndarray
    coef_boot: np.ndarray  # (BOOTSTRAPS, n_features) in natural units
    baseline: dict[str, float]

    @property
    def coefs(self) -> dict[str, float]:
        return dict(zip(self.feature_keys, self.model.coef_ / self.scaler.scale_))

    def predict_rows(self, X: pd.DataFrame) -> np.ndarray:
        return self.model.predict(self.scaler.transform(X[self.feature_keys].values))

    def predict_one(self, x: dict[str, float]) -> float:
        return float(self.predict_rows(pd.DataFrame([{k: x[k] for k in self.feature_keys}]))[0])


# A feature only enters the model when the runs span at least this fraction of its plausible
# range; otherwise its coefficient would be pure noise (e.g. hilliness when every run is on flat ground).
MIN_SPAN_FRACTION = 0.03


def _active_features(df: pd.DataFrame, keys: list[str]) -> tuple[list[str], list[str]]:
    ranges = {k: rng for k, _, _, _, rng in FEATURES + [EFFORT_FEATURE]}
    active, inactive = [], []
    for k in keys:
        lo, hi = ranges[k]
        span = float(df[k].max() - df[k].min())
        (active if df[k].std() > 0 and span >= MIN_SPAN_FRACTION * (hi - lo) else inactive).append(k)
    return active, inactive


def _loo_residuals(X: np.ndarray, y: np.ndarray, alpha: float) -> np.ndarray:
    """Exact leave-one-out residuals for ridge via the hat matrix (no refitting needed)."""
    n, p = X.shape
    sc = StandardScaler().fit(X)
    Xs = sc.transform(X)
    Xc = np.hstack([np.ones((n, 1)), Xs])
    pen = np.eye(p + 1) * alpha
    pen[0, 0] = 0.0
    H = Xc @ np.linalg.solve(Xc.T @ Xc + pen, Xc.T)
    fitted = H @ y
    h = np.diag(H)
    return (y - fitted) / (1.0 - h)


def fit(df: pd.DataFrame, variant: str) -> Fitted | None:
    keys = [f[0] for f in FEATURES]
    if variant == "effort":
        keys = keys + [EFFORT_FEATURE[0]]
        df = df[df["avg_hr"].notna()].reset_index(drop=True)
    keys, inactive = _active_features(df, keys)
    if len(df) < len(keys) + 3 or not keys:
        return None
    X = df[keys].values.astype(float)
    y = df["pace_sec_mi"].values.astype(float)

    best_alpha, best_res = None, None
    for a in ALPHAS:
        res = _loo_residuals(X, y, a)
        if best_res is None or np.abs(res).mean() < np.abs(best_res).mean():
            best_alpha, best_res = a, res

    scaler = StandardScaler().fit(X)
    model = Ridge(alpha=best_alpha).fit(scaler.transform(X), y)

    rng = np.random.default_rng(7)
    boots = np.empty((BOOTSTRAPS, len(keys)))
    n = len(df)
    for b in range(BOOTSTRAPS):
        idx = rng.integers(0, n, n)
        if len(np.unique(idx)) < len(keys) + 2:
            boots[b] = np.nan
            continue
        sc_b = StandardScaler().fit(X[idx])
        m_b = Ridge(alpha=best_alpha).fit(sc_b.transform(X[idx]), y[idx])
        boots[b] = m_b.coef_ / sc_b.scale_

    baseline = {k: float(df[k].median()) for k in keys + inactive}
    return Fitted(variant, keys, inactive, scaler, model, best_alpha, df, best_res, boots, baseline)


class ModelService:
    """Caches fitted models; invalidated when sync changes the data."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cache: dict[str, Fitted | None] = {}
        self._frame: pd.DataFrame | None = None
        self._n_excluded = 0

    def invalidate(self) -> None:
        with self._lock:
            self._cache.clear()
            self._frame = None

    def get(self, variant: str = "conditions") -> Fitted | None:
        with self._lock:
            if variant not in self._cache:
                if self._frame is None:
                    with db() as conn:
                        runs = store.list_runs(conn)
                    self._n_excluded = sum(1 for r in runs if r.get("excluded_from_model"))
                    self._frame = build_frame(runs)
                self._cache[variant] = fit(self._frame, variant) if not self._frame.empty else None
            return self._cache[variant]

    # ------------------------------------------------------------------ reporting

    def summary(self, variant: str) -> dict:
        f = self.get(variant)
        if f is None:
            return {"ok": False, "reason": "Not enough runs with weather data to fit the model yet."}
        y = f.df["pace_sec_mi"].values.astype(float)
        pred_in = f.predict_rows(f.df)
        loo_pred = y - f.loo_residuals
        ss_tot = ((y - y.mean()) ** 2).sum()
        r2_in = 1.0 - ((y - pred_in) ** 2).sum() / ss_tot if ss_tot else 0.0
        r2_loo = 1.0 - (f.loo_residuals ** 2).sum() / ss_tot if ss_tot else 0.0
        mae_loo = float(np.abs(f.loo_residuals).mean())
        coefs = f.coefs
        meta = {k: (lab, unit, desc, rng) for k, lab, unit, desc, rng in FEATURES + [EFFORT_FEATURE]}
        lo = np.nanpercentile(f.coef_boot, 10, axis=0)
        hi = np.nanpercentile(f.coef_boot, 90, axis=0)
        # Effect size: coefficient times the feature's observed interquartile range.
        q = f.df[f.feature_keys].quantile([0.25, 0.75])
        rows = []
        for i, k in enumerate(f.feature_keys):
            lab, unit, desc, rng = meta[k]
            iqr = float(q.loc[0.75, k] - q.loc[0.25, k])
            rows.append(
                {
                    "key": k,
                    "label": lab,
                    "unit": unit,
                    "description": desc,
                    "active": True,
                    "coef_sec_per_unit": round(float(coefs[k]), 3),
                    "ci_low": round(float(lo[i]), 3),
                    "ci_high": round(float(hi[i]), 3),
                    "typical_swing_sec": round(float(coefs[k]) * iqr, 1),
                    "iqr": round(iqr, 2),
                    "baseline": round(f.baseline[k], 2),
                    "range": list(rng),
                    "observed": [round(float(f.df[k].min()), 2), round(float(f.df[k].max()), 2)],
                }
            )
        rows.sort(key=lambda r: -abs(r["typical_swing_sec"]))
        for k in f.inactive_keys:
            lab, unit, desc, rng = meta[k]
            rows.append(
                {
                    "key": k,
                    "label": lab,
                    "unit": unit,
                    "description": desc,
                    "active": False,
                    "coef_sec_per_unit": 0.0,
                    "ci_low": 0.0,
                    "ci_high": 0.0,
                    "typical_swing_sec": 0.0,
                    "iqr": 0.0,
                    "baseline": round(f.baseline[k], 2),
                    "range": list(rng),
                    "observed": [round(float(f.df[k].min()), 2), round(float(f.df[k].max()), 2)],
                }
            )
        return {
            "ok": True,
            "variant": variant,
            "n_runs": int(len(f.df)),
            "n_excluded": self._n_excluded,
            "alpha": f.alpha,
            "r2_in_sample": round(float(r2_in), 3),
            "r2_loo": round(float(r2_loo), 3),
            "mae_loo_sec": round(mae_loo, 1),
            "baseline": {k: round(v, 2) for k, v in f.baseline.items()},
            "baseline_pace_sec": round(f.predict_one(f.baseline)),
            "features": rows,
            "timeline": self._timeline(f, loo_pred),
            "last_run": {k: round(float(f.df.iloc[-1][k]), 2) for k in f.feature_keys + f.inactive_keys},
        }

    def _timeline(self, f: Fitted, loo_pred: np.ndarray) -> dict:
        """Actual pace, pace adjusted to baseline conditions (so only training time differs), and
        the smoothed trend of that adjusted pace."""
        coefs = f.coefs
        cond_keys = [k for k in f.feature_keys if k != "weeks"]
        df = f.df
        adj = df["pace_sec_mi"].values.astype(float).copy()
        for k in cond_keys:
            adj -= coefs[k] * (df[k].values - f.baseline[k])
        ewm = pd.Series(adj).ewm(span=5, min_periods=1).mean().values
        weeks = df["weeks"].values
        slope, intercept = np.polyfit(weeks, adj, 1) if len(df) > 2 else (0.0, float(adj.mean()))
        runs = []
        for i, r in df.iterrows():
            runs.append(
                {
                    "id": r["id"],
                    "date": r["date"],
                    "distance_mi": r["distance_mi"],
                    "actual_sec": int(r["pace_sec_mi"]),
                    "adjusted_sec": int(round(adj[i])),
                    "smoothed_sec": int(round(ewm[i])),
                    "trend_sec": int(round(intercept + slope * weeks[i])),
                    "predicted_sec": int(round(loo_pred[i])),
                    "adjustments": {k: round(float(-coefs[k] * (r[k] - f.baseline[k])), 1) for k in cond_keys},
                }
            )
        return {
            "runs": runs,
            "trend_sec_per_month": round(float(slope * 4.345), 1),
            "trend_total_sec": round(float(slope * (weeks[-1] - weeks[0])), 1) if len(df) > 1 else 0.0,
        }

    def predict(self, variant: str, inputs: dict) -> dict:
        f = self.get(variant)
        if f is None:
            return {"ok": False, "reason": "Model not available."}
        x = {k: float(inputs.get(k, f.baseline[k])) for k in f.feature_keys + f.inactive_keys}
        pred = f.predict_one(x)
        q80 = float(np.percentile(np.abs(f.loo_residuals), 80))
        coefs = f.coefs
        contributions = {k: round(float(coefs[k] * (x[k] - f.baseline[k])), 1) for k in f.feature_keys}
        contributions.update({k: 0.0 for k in f.inactive_keys})
        curves = {}
        meta = {k: rng for k, _, _, _, rng in FEATURES + [EFFORT_FEATURE]}
        for k in f.feature_keys:
            lo_r, hi_r = meta[k]
            obs_lo, obs_hi = float(f.df[k].min()), float(f.df[k].max())
            xs = np.linspace(lo_r, hi_r, 25)
            pts = []
            for v in xs:
                xx = dict(x)
                xx[k] = float(v)
                pts.append({"x": round(float(v), 2), "pace_sec": round(f.predict_one(xx)), "observed": bool(obs_lo <= v <= obs_hi)})
            curves[k] = pts
        return {
            "ok": True,
            "inputs": x,
            "pace_sec": round(pred),
            "pace_str": store.fmt_pace(pred),
            "low_sec": round(pred - q80),
            "high_sec": round(pred + q80),
            "baseline_pace_sec": round(f.predict_one(f.baseline)),
            "contributions": contributions,
            "curves": curves,
        }


service = ModelService()
