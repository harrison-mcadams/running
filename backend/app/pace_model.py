"""Model of what moves your pace.

A ridge regression on a small set of factors, with two shapes a plain linear model can't express:

* heat: pace depends on dew point, with a steeper slope above HEAT_DEW_F (humid heat costs much
  more than mild humidity), modelled as a hinge term max(0, dew - HEAT_DEW_F);
* (optional, off for now) distance x time of day, see USE_DISTANCE_HOUR.

Because of those terms, each factor's effect is reported from the model's own predictions
(moving one factor from its 25th to its 75th percentile, everything else at your median run),
with an 80% bootstrap interval. Accuracy is measured honestly: repeated 5-fold cross-validation
with the ridge penalty re-chosen inside every fold, compared against just guessing your average.
The "effort" variant adds average heart rate as a control."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge, RidgeCV
from sklearn.model_selection import RepeatedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from . import store
from .db import db
from .weather import dew_point_f

HEAT_DEW_F = 57.0
# Distance x time-of-day interaction. Off: on the current data it rests on two long afternoon
# runs and makes wild predictions for combinations you haven't run. Turn on once those exist.
USE_DISTANCE_HOUR = False

# (key, label, unit, description, slider range, minimum interquartile spread to be fitted)
FEATURES = [
    ("distance_mi", "Distance", "mi", "Run length.", (1.0, 15.0), 0.0),
    ("dew_point_f", "Dew point", "°F", f"Air moisture at the start; costs much more above {HEAT_DEW_F:.0f}°F.", (20.0, 80.0), 0.0),
    ("local_hour", "Time of day", "h", "Local start time, as hours after midnight.", (5.0, 21.0), 0.0),
    ("recent_7d_miles", "7-day mileage", "mi", "Miles run in the 7 days before this run.", (0.0, 40.0), 0.0),
    ("weeks", "Training time", "weeks", "Weeks since your first run on record: the fitness trend.", (0.0, 104.0), 0.0),
    # Your routes are all similar in climbing; this joins the model once they vary more.
    ("elev_gain_ft_per_mi", "Hilliness", "ft/mi", "Elevation gain per mile.", (0.0, 150.0), 15.0),
]
EFFORT_FEATURE = ("avg_hr", "Heart rate", "bpm", "Average heart rate: how hard you were working.", (120.0, 190.0), 0.0)
META = {f[0]: f for f in FEATURES + [EFFORT_FEATURE]}

ALPHAS = np.logspace(-2, 3, 30)
BOOTSTRAPS = 300
CV_REPEATS = 20


def build_frame(runs: list[dict]) -> pd.DataFrame:
    """Per-run feature table. Runs lacking weather are dropped; missing hilliness is filled with
    the median of the rest (almost always the home trail)."""
    # Runs flagged "exclude from model" or FAIL still count toward the 7-day mileage of the runs
    # after them, so build features on everything and drop them at the end.
    df = pd.DataFrame(runs)
    if df.empty:
        return df
    df["local_dt"] = pd.to_datetime(df["local_datetime"])
    df = df.sort_values("local_dt").reset_index(drop=True)
    temp = df["weather"].apply(lambda w: w.get("temp_f") if w else None)
    hum = df["weather"].apply(lambda w: w.get("humidity") if w else None)
    dew = df["weather"].apply(lambda w: w.get("dew_point_f") if w else None)
    df["dew_point_f"] = [
        d if d is not None else (dew_point_f(t, h) if t is not None and h is not None else None)
        for d, t, h in zip(dew, temp, hum)
    ]
    df["local_hour"] = df["local_dt"].dt.hour + df["local_dt"].dt.minute / 60.0
    df["recent_7d_miles"] = [
        float(df.loc[(df["local_dt"] < t) & (df["local_dt"] >= t - pd.Timedelta(days=7)), "distance_mi"].sum())
        for t in df["local_dt"]
    ]
    df["elev_gain_ft_per_mi"] = (df["elevation_gain_ft"] / df["distance_mi"]).astype(float)
    df["elev_gain_ft_per_mi"] = df["elev_gain_ft_per_mi"].fillna(df["elev_gain_ft_per_mi"].median()).fillna(0.0)
    df["weeks"] = (df["local_dt"] - df["local_dt"].min()).dt.total_seconds() / (7 * 86400.0)
    keep = df["dew_point_f"].notna() & df["pace_sec_mi"].notna()
    if "excluded_from_model" in df:
        keep &= ~df["excluded_from_model"].astype(bool)
    if "is_fail" in df:
        keep &= ~df["is_fail"].astype(bool)
    df = df[keep].reset_index(drop=True)
    df["dew_point_f"] = df["dew_point_f"].astype(float)
    return df


@dataclass
class Fitted:
    variant: str
    keys: list[str]               # raw factors in the model
    inactive: list[str]           # raw factors without enough spread yet
    centers: dict[str, float]     # medians used to center the interaction
    bounds: dict[str, tuple[float, float]]  # observed ranges; the interaction never extrapolates past them
    model: object                 # StandardScaler + Ridge pipeline on the design matrix
    alpha: float
    df: pd.DataFrame
    oof_pred: np.ndarray          # out-of-fold predictions, averaged over CV repeats
    cv_mae: float
    mean_mae: float               # same folds, predicting the training-fold average
    boot_models: list = field(default_factory=list)
    baseline: dict[str, float] = field(default_factory=dict)

    def design(self, X: pd.DataFrame) -> np.ndarray:
        return design_matrix(X, self.keys, self.centers, self.bounds)

    def predict_frame(self, X: pd.DataFrame) -> np.ndarray:
        return self.model.predict(self.design(X))

    def predict_one(self, x: dict[str, float]) -> float:
        return float(self.predict_frame(pd.DataFrame([{k: x[k] for k in self.keys}]))[0])


def design_matrix(
    X: pd.DataFrame, keys: list[str], centers: dict[str, float], bounds: dict[str, tuple[float, float]]
) -> np.ndarray:
    cols = [X[k].values.astype(float) for k in keys]
    if "dew_point_f" in keys:
        cols.append(np.maximum(0.0, X["dew_point_f"].values.astype(float) - HEAT_DEW_F))
    if USE_DISTANCE_HOUR and "distance_mi" in keys and "local_hour" in keys:
        # Product terms blow up outside the data, so the interaction holds flat beyond the
        # distances and start times you've actually run; the main effects still extend.
        d = np.clip(X["distance_mi"].values.astype(float), *bounds["distance_mi"])
        h = np.clip(X["local_hour"].values.astype(float), *bounds["local_hour"])
        cols.append((d - centers["distance_mi"]) * (h - centers["local_hour"]))
    return np.column_stack(cols)


def _active(df: pd.DataFrame, keys: list[str]) -> tuple[list[str], list[str]]:
    active, inactive = [], []
    for k in keys:
        iqr = float(df[k].quantile(0.75) - df[k].quantile(0.25))
        (active if df[k].std() > 0 and iqr >= META[k][5] else inactive).append(k)
    return active, inactive


def _pipeline(alpha: float | None = None):
    reg = RidgeCV(alphas=ALPHAS) if alpha is None else Ridge(alpha=alpha)
    return make_pipeline(StandardScaler(), reg)


def fit(df: pd.DataFrame, variant: str) -> Fitted | None:
    keys = [f[0] for f in FEATURES]
    if variant == "effort":
        keys = keys + [EFFORT_FEATURE[0]]
        df = df[df["avg_hr"].notna()].reset_index(drop=True)
    if df.empty:
        return None
    keys, inactive = _active(df, keys)
    centers = {k: float(df[k].median()) for k in keys}
    bounds = {k: (float(df[k].min()), float(df[k].max())) for k in keys}
    X = design_matrix(df, keys, centers, bounds)
    y = df["pace_sec_mi"].values.astype(float)
    n = len(df)
    if n < X.shape[1] + 5:
        return None

    model = _pipeline().fit(X, y)
    alpha = float(model[-1].alpha_)

    # Honest accuracy: penalty re-chosen inside every training fold.
    oof_sum, oof_cnt = np.zeros(n), np.zeros(n)
    err, err_mean = [], []
    for tr, te in RepeatedKFold(n_splits=5, n_repeats=CV_REPEATS, random_state=0).split(X):
        p = _pipeline().fit(X[tr], y[tr]).predict(X[te])
        oof_sum[te] += p
        oof_cnt[te] += 1
        err.append(np.abs(p - y[te]))
        err_mean.append(np.abs(y[tr].mean() - y[te]))

    rng = np.random.default_rng(7)
    boots = []
    for _ in range(BOOTSTRAPS):
        idx = rng.integers(0, n, n)
        if len(np.unique(idx)) < X.shape[1] + 2:
            continue
        boots.append(_pipeline(alpha).fit(X[idx], y[idx]))

    baseline = {k: float(df[k].median()) for k in keys + inactive}
    return Fitted(
        variant, keys, inactive, centers, bounds, model, alpha, df,
        oof_sum / np.maximum(oof_cnt, 1), float(np.concatenate(err).mean()), float(np.concatenate(err_mean).mean()),
        boots, baseline,
    )


def _with(base: dict[str, float], **kw: float) -> dict[str, float]:
    x = dict(base)
    x.update(kw)
    return x


class ModelService:
    """Caches fitted models; invalidated when sync or a run flag changes the data."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cache: dict[str, Fitted | None] = {}
        self._frame: pd.DataFrame | None = None
        self._n_excluded = 0
        self._n_fails = 0

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
                    self._n_excluded = sum(1 for r in runs if r.get("excluded_from_model") and not r.get("is_fail"))
                    self._n_fails = sum(1 for r in runs if r.get("is_fail"))
                    self._frame = build_frame(runs)
                self._cache[variant] = fit(self._frame, variant) if not self._frame.empty else None
            return self._cache[variant]

    # ------------------------------------------------------------------ reporting

    def _swing(self, f: Fitted, model, k: str, lo: float, hi: float) -> float:
        a = pd.DataFrame([_with(f.baseline, **{k: lo})])
        b = pd.DataFrame([_with(f.baseline, **{k: hi})])
        return float(model.predict(f.design(b))[0] - model.predict(f.design(a))[0])

    def _slope(self, model, f: Fitted, k: str, at: float, step: float = 1.0) -> float:
        return self._swing(f, model, k, at - step / 2, at + step / 2) / step

    def summary(self, variant: str) -> dict:
        f = self.get(variant)
        if f is None:
            return {"ok": False, "reason": "Not enough runs with weather data to fit the model yet."}
        y = f.df["pace_sec_mi"].values.astype(float)
        ss_tot = float(((y - y.mean()) ** 2).sum())
        r2_in = 1.0 - float(((y - f.predict_frame(f.df)) ** 2).sum()) / ss_tot if ss_tot else 0.0
        r2_oos = 1.0 - float(((y - f.oof_pred) ** 2).sum()) / ss_tot if ss_tot else 0.0

        rows = []
        for k in f.keys:
            _, lab, unit, desc, rng, _ = META[k]
            q25, q75 = float(f.df[k].quantile(0.25)), float(f.df[k].quantile(0.75))
            swing = self._swing(f, f.model, k, q25, q75)
            boot = np.array([self._swing(f, m, k, q25, q75) for m in f.boot_models])
            if k == "dew_point_f":
                below = self._slope(f.model, f, k, HEAT_DEW_F - 5)
                above = self._slope(f.model, f, k, HEAT_DEW_F + 5)
                detail = f"{below:+.1f} s/mi per °F below {HEAT_DEW_F:.0f}°F, {above:+.1f} above"
            else:
                slope = self._slope(f.model, f, k, f.baseline[k])
                detail = f"{slope:+.{2 if abs(slope) < 1 else 1}f} s/mi per {unit}"
                if USE_DISTANCE_HOUR and k in ("distance_mi", "local_hour") and "distance_mi" in f.keys and "local_hour" in f.keys:
                    detail += " at your usual " + ("time of day" if k == "distance_mi" else "distance")
            rows.append(
                {
                    "key": k,
                    "label": lab,
                    "unit": unit,
                    "description": desc,
                    "active": True,
                    "detail": detail,
                    "typical_swing_sec": round(swing, 1),
                    "swing_low": round(float(np.percentile(boot, 10)), 1) if len(boot) else swing,
                    "swing_high": round(float(np.percentile(boot, 90)), 1) if len(boot) else swing,
                    "q25": round(q25, 2),
                    "q75": round(q75, 2),
                    "baseline": round(f.baseline[k], 2),
                    "range": list(rng),
                    "observed": [round(float(f.df[k].min()), 2), round(float(f.df[k].max()), 2)],
                }
            )
        rows.sort(key=lambda r: -abs(r["typical_swing_sec"]))
        for k in f.inactive:
            _, lab, unit, desc, rng, _ = META[k]
            rows.append(
                {
                    "key": k, "label": lab, "unit": unit, "description": desc, "active": False, "detail": "",
                    "typical_swing_sec": 0.0, "swing_low": 0.0, "swing_high": 0.0,
                    "q25": round(float(f.df[k].quantile(0.25)), 2), "q75": round(float(f.df[k].quantile(0.75)), 2),
                    "baseline": round(f.baseline[k], 2), "range": list(rng),
                    "observed": [round(float(f.df[k].min()), 2), round(float(f.df[k].max()), 2)],
                }
            )

        interaction = None
        if USE_DISTANCE_HOUR and "distance_mi" in f.keys and "local_hour" in f.keys:
            # Cost of an extra mile for your earlier vs later runs (your own 20th/80th percentile
            # start times, so nothing is extrapolated), with a bootstrap interval on the gap.
            early, late = float(f.df["local_hour"].quantile(0.2)), float(f.df["local_hour"].quantile(0.8))
            d0 = f.baseline["distance_mi"]

            def per_mile(model, hour: float) -> float:
                return self._slope(model, _FakeBase(f, local_hour=hour), "distance_mi", d0)

            gap_boot = np.array([per_mile(m, late) - per_mile(m, early) for m in f.boot_models])
            lo, hi = (float(np.percentile(gap_boot, 10)), float(np.percentile(gap_boot, 90))) if len(gap_boot) else (0.0, 0.0)
            interaction = {
                "early_hour": round(early, 2),
                "late_hour": round(late, 2),
                "per_mile_early": round(per_mile(f.model, early), 1),
                "per_mile_late": round(per_mile(f.model, late), 1),
                "gap_low": round(lo, 1),
                "gap_high": round(hi, 1),
                "clear": bool(lo > 0 or hi < 0),
            }

        return {
            "ok": True,
            "variant": variant,
            "n_runs": int(len(f.df)),
            "n_excluded": self._n_excluded,
            "n_fails": self._n_fails,
            "alpha": round(f.alpha, 3),
            "heat_dew_f": HEAT_DEW_F,
            "r2_in_sample": round(r2_in, 3),
            "r2_loo": round(r2_oos, 3),
            "mae_loo_sec": round(f.cv_mae, 1),
            "mae_guess_sec": round(f.mean_mae, 1),
            "interaction": interaction,
            "baseline": {k: round(v, 2) for k, v in f.baseline.items()},
            "baseline_pace_sec": round(f.predict_one(f.baseline)),
            "features": rows,
            "timeline": self._timeline(f),
            "last_run": {k: round(float(f.df.iloc[-1][k]), 2) for k in f.keys + f.inactive},
        }

    def _timeline(self, f: Fitted) -> dict:
        """Actual pace, pace adjusted to your median conditions (so only training time differs),
        and the smoothed trend of that adjusted pace."""
        df = f.df
        cond = [k for k in f.keys if k != "weeks"]
        pred = f.predict_frame(df)
        at_base = df.copy()
        for k in cond:
            at_base[k] = f.baseline[k]
        pred_base = f.predict_frame(at_base)
        adj = df["pace_sec_mi"].values.astype(float) - (pred - pred_base)
        per_factor = {}
        for k in cond:
            one = df.copy()
            one[k] = f.baseline[k]
            per_factor[k] = -(pred - f.predict_frame(one))
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
                    "predicted_sec": int(round(f.oof_pred[i])),
                    "adjustments": {k: round(float(per_factor[k][i]), 1) for k in cond},
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
        x = {k: float(inputs.get(k, f.baseline[k])) for k in f.keys + f.inactive}
        pred = f.predict_one(x)
        q80 = float(np.percentile(np.abs(f.df["pace_sec_mi"].values - f.oof_pred), 80))
        contributions = {k: round(pred - f.predict_one(_with(x, **{k: f.baseline[k]})), 1) for k in f.keys}
        contributions.update({k: 0.0 for k in f.inactive})
        curves = {}
        for k in f.keys:
            lo_r, hi_r = META[k][4]
            obs_lo, obs_hi = float(f.df[k].min()), float(f.df[k].max())
            xs = np.linspace(lo_r, hi_r, 31)
            frame = pd.DataFrame([_with(x, **{k: float(v)}) for v in xs])
            ys = f.predict_frame(frame)
            curves[k] = [
                {"x": round(float(v), 2), "pace_sec": round(float(p)), "observed": bool(obs_lo <= v <= obs_hi)}
                for v, p in zip(xs, ys)
            ]
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


class _FakeBase:
    """A view of a Fitted model with a different baseline, for slopes at another time of day."""

    def __init__(self, f: Fitted, **override: float) -> None:
        self._f = f
        self.baseline = _with(f.baseline, **override)

    def design(self, X: pd.DataFrame) -> np.ndarray:
        return self._f.design(X)


service = ModelService()
