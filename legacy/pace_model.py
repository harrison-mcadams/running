import os
import json
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge, LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import LeaveOneOut, cross_val_score
from sklearn.metrics import mean_absolute_error, r2_score

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXERCISES_CSV = os.path.join(BASE_DIR, 'my_exercises.csv')
ROUTES_DIR = os.path.join(BASE_DIR, 'run_routes')

class PacePredictorModel:
    def __init__(self, base_dir=BASE_DIR):
        self.base_dir = base_dir
        self.is_trained = False
        self.df = None
        self.factor_model = None
        self.rf_model = None
        self.baseline_pace = 540.0 # ~9:00 min/mi
        self.feature_cols = []
        self.metrics = {}
        self.last_loaded_mtime = 0

    def _is_csv_updated(self):
        csv_path = os.path.join(self.base_dir, 'my_exercises.csv')
        if not os.path.exists(csv_path):
            return False
        return os.path.getmtime(csv_path) > self.last_loaded_mtime

    def load_and_prepare_data(self):
        from historical_runs import auto_heal_exercises
        from weather_service import get_weather_for_runs
        
        csv_path = os.path.join(self.base_dir, 'my_exercises.csv')
        if os.path.exists(csv_path):
            self.last_loaded_mtime = os.path.getmtime(csv_path)
            
        df_raw = auto_heal_exercises(self.base_dir)
        if df_raw is None or df_raw.empty:
            if not os.path.exists(EXERCISES_CSV):
                raise FileNotFoundError("my_exercises.csv not found")
            df_raw = pd.read_csv(EXERCISES_CSV)
            
        runs = df_raw[df_raw['exercise.exerciseType'] == 'RUNNING'].copy()
        runs['startTime'] = pd.to_datetime(runs['exercise.interval.startTime'], format='ISO8601')
        runs = runs.sort_values('startTime')
        
        # Filter for runs from watch era (Dec 29, 2025 onwards)
        runs = runs[runs['startTime'] >= pd.to_datetime('2025-12-29', utc=True)].copy()
        
        # Fetch weather cache
        runs_meta = [
            {"id": r['name'].split('/')[-1], "datetime": r['exercise.interval.startTime']}
            for _, r in runs.iterrows()
        ]
        weather_cache = get_weather_for_runs(runs_meta, ROUTES_DIR, self.base_dir)
        
        records = []
        for idx, row in runs.iterrows():
            run_id = row['name'].split('/')[-1]
            start_time_iso = row['exercise.interval.startTime']
            dt_utc = pd.to_datetime(start_time_iso, format='ISO8601')
            
            # UTC offset
            off_val = row.get('exercise.interval.startUtcOffset')
            if pd.notna(off_val) and str(off_val).strip() and str(off_val).lower() != 'nan':
                try:
                    off_sec = int(float(str(off_val).replace('s', '')))
                except Exception:
                    off_sec = -18000
            else:
                off_sec = -18000

            local_dt = dt_utc + pd.Timedelta(seconds=off_sec)
            
            # Metrics
            dist_mm = row.get('exercise.metricsSummary.distanceMillimeters', 0)
            dist_mi = dist_mm / 1609344.0 if pd.notna(dist_mm) else 0.0
            
            sec_per_meter = row.get('exercise.metricsSummary.averagePaceSecondsPerMeter')
            if pd.notna(sec_per_meter) and sec_per_meter > 0:
                pace_sec_mi = sec_per_meter * 1609.344
            else:
                dur_str = str(row.get('exercise.activeDuration', '0s')).replace('s', '')
                duration_sec = float(dur_str) if dur_str and dur_str.lower() != 'nan' else 0.0
                if duration_sec > 0 and dist_mi > 0:
                    pace_sec_mi = duration_sec / dist_mi
                else:
                    pace_sec_mi = 0
                
            # Filter out accidental/short activities (<0.5 mi) and extreme outliers (>15:00 min/mi)
            if dist_mi < 0.5 or pace_sec_mi <= 0 or pace_sec_mi > 900:
                continue
                
            weather_info = weather_cache.get(run_id, {})
            temp_f = weather_info.get('temp_f', 65.0)
            feels_like_f = weather_info.get('feels_like_f', temp_f)
            humidity = weather_info.get('humidity', 60.0)
            wind_mph = weather_info.get('wind_mph', 5.0)
            
            records.append({
                'id': run_id,
                'datetime': start_time_iso,
                'local_dt': local_dt,
                'date_str': local_dt.strftime('%Y-%m-%d'),
                'distance_mi': round(dist_mi, 2),
                'pace_sec_mi': int(pace_sec_mi),
                'temp_f': temp_f if temp_f is not None else 65.0,
                'feels_like_f': feels_like_f if feels_like_f is not None else temp_f,
                'humidity': humidity if humidity is not None else 60.0,
                'wind_mph': wind_mph if wind_mph is not None else 5.0,
                'avg_hr': row.get('exercise.metricsSummary.averageHeartRateBeatsPerMinute')
            })
            
        df = pd.DataFrame(records)
        df = df.sort_values('local_dt').reset_index(drop=True)
        
        # Feature Engineering
        min_dt = df['local_dt'].min()
        df['days_elapsed'] = (df['local_dt'] - min_dt).dt.total_seconds() / (24 * 3600.0)
        df['weeks'] = df['days_elapsed'] / 7.0
        
        # Local hour & morning flag
        df['local_hour'] = df['local_dt'].dt.hour + df['local_dt'].dt.minute / 60.0
        df['is_morning'] = (df['local_hour'] < 12).astype(int)
        df['is_weekend'] = (df['local_dt'].dt.dayofweek >= 5).astype(int)
        
        # Heat penalty > 75°F
        df['temp_over_75'] = np.maximum(0.0, df['temp_f'] - 75.0)
        df['temp_over_80'] = np.maximum(0.0, df['temp_f'] - 80.0)
        
        # Fatigue features
        df['days_since_last_run'] = df['local_dt'].diff().dt.total_seconds() / (24 * 3600.0)
        df['days_since_last_run'] = df['days_since_last_run'].fillna(7.0)
        df['ran_yesterday'] = (df['days_since_last_run'] <= 1.5).astype(int)
        
        # Rolling prior 7-day mileage
        recent_7d = []
        for i, row in df.iterrows():
            t = row['local_dt']
            sub_7d = df[(df['local_dt'] < t) & (df['local_dt'] >= t - pd.Timedelta(days=7))]
            recent_7d.append(sub_7d['distance_mi'].sum())
        df['recent_7d_miles'] = recent_7d
        
        self.df = df
        return df

    def ensure_up_to_date(self):
        if not self.is_trained or self._is_csv_updated():
            self.train(force_reload=True)

    def train(self, force_reload=False):
        if force_reload or self.df is None or len(self.df) < 5 or self._is_csv_updated():
            self.load_and_prepare_data()
            
        df = self.df
        
        # Primary feature set for interpretable model & predictor
        # Distance, Weather (Temp, Temp>75, Humidity), Time of Day, Fatigue (Ran Yesterday, Rest Days, 7d Vol), Progression (Weeks)
        self.feature_cols = [
            'distance_mi',
            'temp_f',
            'temp_over_75',
            'humidity',
            'local_hour',
            'is_morning',
            'ran_yesterday',
            'days_since_last_run',
            'recent_7d_miles',
            'weeks'
        ]
        
        X = df[self.feature_cols]
        y = df['pace_sec_mi']
        
        # 1. Ridge regularized model for clean feature attribution & preventing overfitting
        ridge = Ridge(alpha=10.0, random_state=42)
        ridge.fit(X, y)
        self.factor_model = ridge
        
        # 2. Random Forest for non-linear ensemble prediction
        rf = RandomForestRegressor(n_estimators=100, max_depth=3, random_state=42)
        rf.fit(X, y)
        self.rf_model = rf
        
        # Compute LOOCV error (Leave-One-Out Cross Validation) to ensure model doesn't overfit
        loo = LeaveOneOut()
        preds_ridge = []
        preds_rf = []
        for train_idx, test_idx in loo.split(X):
            X_tr, X_te = X.iloc[train_idx], X.iloc[test_idx]
            y_tr, y_te = y.iloc[train_idx], y.iloc[test_idx]
            
            r_temp = Ridge(alpha=10.0, random_state=42).fit(X_tr, y_tr)
            preds_ridge.append(r_temp.predict(X_te)[0])
            
            rf_temp = RandomForestRegressor(n_estimators=50, max_depth=3, random_state=42).fit(X_tr, y_tr)
            preds_rf.append(rf_temp.predict(X_te)[0])
            
        mae_ridge_cv = mean_absolute_error(y, preds_ridge)
        mae_rf_cv = mean_absolute_error(y, preds_rf)
        r2_ridge = r2_score(y, ridge.predict(X))
        r2_rf = r2_score(y, rf.predict(X))
        
        self.baseline_pace = float(ridge.intercept_)
        
        # Also compute Temp-In-Isolation model vs Full-Weather model to present comparative stats
        X_temp_only = df[['distance_mi', 'temp_f', 'local_hour', 'ran_yesterday', 'weeks']]
        lr_temp_only = LinearRegression().fit(X_temp_only, y)
        r2_temp_only = r2_score(y, lr_temp_only.predict(X_temp_only))
        
        self.metrics = {
            'n_runs': len(df),
            'r2_factor_model': round(float(r2_ridge), 3),
            'mae_factor_cv_sec': round(float(mae_ridge_cv), 2),
            'r2_rf_model': round(float(r2_rf), 3),
            'mae_rf_cv_sec': round(float(mae_rf_cv), 2),
            'r2_temp_only': round(float(r2_temp_only), 3),
            'improvement_rate_sec_per_week': round(float(ridge.coef_[self.feature_cols.index('weeks')]), 2),
            'improvement_rate_sec_per_month': round(float(ridge.coef_[self.feature_cols.index('weeks')] * 4.345), 2),
            'baseline_pace_sec': round(float(self.baseline_pace), 1)
        }
        
        self.is_trained = True
        return self.metrics

    def predict(self, distance_mi=4.0, temp_f=65.0, humidity=60.0, time_str="09:00", ran_yesterday=False, rest_days=2.0, recent_7d_miles=10.0, target_date_str=None, model_type="hybrid"):
        self.ensure_up_to_date()
            
        # Time parsing
        try:
            parts = time_str.split(':')
            hour_val = float(parts[0]) + float(parts[1]) / 60.0
        except Exception:
            hour_val = 9.0
            
        is_morning_val = 1 if hour_val < 12.0 else 0
        temp_over_75_val = max(0.0, float(temp_f) - 75.0)
        
        # Target date / progression weeks
        if target_date_str:
            target_dt = pd.to_datetime(target_date_str)
            min_dt = self.df['local_dt'].min().tz_localize(None)
            days_el = (target_dt - min_dt).total_seconds() / (24 * 3600.0)
            weeks_val = max(0.0, days_el / 7.0)
        else:
            weeks_val = float(self.df['weeks'].max())
            
        input_dict = {
            'distance_mi': float(distance_mi),
            'temp_f': float(temp_f),
            'temp_over_75': temp_over_75_val,
            'humidity': float(humidity),
            'local_hour': hour_val,
            'is_morning': is_morning_val,
            'ran_yesterday': 1 if ran_yesterday else 0,
            'days_since_last_run': float(rest_days),
            'recent_7d_miles': float(recent_7d_miles),
            'weeks': weeks_val
        }
        
        input_df = pd.DataFrame([input_dict])[self.feature_cols]
        
        ridge_pred = float(self.factor_model.predict(input_df)[0])
        rf_pred = float(self.rf_model.predict(input_df)[0])
        
        model_type_clean = str(model_type).lower().strip()
        if model_type_clean == 'glm':
            ensemble_pred_sec = ridge_pred
            mae_cv = self.metrics['mae_factor_cv_sec']
        elif model_type_clean == 'rf':
            ensemble_pred_sec = rf_pred
            mae_cv = self.metrics['mae_rf_cv_sec']
        else:
            model_type_clean = 'hybrid'
            ensemble_pred_sec = 0.5 * ridge_pred + 0.5 * rf_pred
            mae_cv = self.metrics['mae_rf_cv_sec']
        
        # Factor decomposition relative to standard baseline run:
        # Standard Baseline: 4 miles, 60°F, 50% hum, 9 AM morning, 2 days rest, ran_yesterday=0, 8 mi 7d, current weeks
        std_input = {
            'distance_mi': 4.0,
            'temp_f': 60.0,
            'temp_over_75': 0.0,
            'humidity': 50.0,
            'local_hour': 9.0,
            'is_morning': 1,
            'ran_yesterday': 0,
            'days_since_last_run': 2.0,
            'recent_7d_miles': 8.0,
            'weeks': weeks_val
        }
        std_df = pd.DataFrame([std_input])[self.feature_cols]
        base_pred_sec = float(self.factor_model.predict(std_df)[0])
        
        coefs = dict(zip(self.feature_cols, self.factor_model.coef_))
        
        # Factor contributions relative to standard run
        dist_impact = (input_dict['distance_mi'] - 4.0) * coefs['distance_mi']
        temp_impact = (input_dict['temp_f'] - 60.0) * coefs['temp_f'] + input_dict['temp_over_75'] * coefs['temp_over_75']
        humidity_impact = (input_dict['humidity'] - 50.0) * coefs['humidity']
        time_impact = (input_dict['local_hour'] - 9.0) * coefs['local_hour'] + (input_dict['is_morning'] - 1) * coefs['is_morning']
        soreness_impact = input_dict['ran_yesterday'] * coefs['ran_yesterday'] + (input_dict['days_since_last_run'] - 2.0) * coefs['days_since_last_run']
        volume_impact = (input_dict['recent_7d_miles'] - 8.0) * coefs['recent_7d_miles']
        fitness_credit = (weeks_val - 0.0) * coefs['weeks']
        
        min_sec = int(ensemble_pred_sec // 60)
        sec_part = int(ensemble_pred_sec % 60)
        pace_str = f"{min_sec}:{sec_part:02d}"
        
        # 95% Confidence range (~ ±1.96 * CV MAE)
        margin_sec = max(12, int(1.5 * mae_cv))
        lower_sec = int(max(240, ensemble_pred_sec - margin_sec))
        upper_sec = int(ensemble_pred_sec + margin_sec)
        
        lower_str = f"{lower_sec // 60}:{lower_sec % 60:02d}"
        upper_str = f"{upper_sec // 60}:{upper_sec % 60:02d}"
        
        return {
            'predicted_pace_sec': int(ensemble_pred_sec),
            'predicted_pace_str': pace_str,
            'confidence_range': f"{lower_str} - {upper_str}",
            'range_sec': [lower_sec, upper_sec],
            'base_pred_sec': int(base_pred_sec),
            'base_pred_str': f"{int(base_pred_sec // 60)}:{int(base_pred_sec % 60):02d}",
            'breakdown': {
                'distance_impact_sec': round(float(dist_impact), 1),
                'temp_impact_sec': round(float(temp_impact), 1),
                'humidity_impact_sec': round(float(humidity_impact), 1),
                'time_impact_sec': round(float(time_impact), 1),
                'soreness_impact_sec': round(float(soreness_impact), 1),
                'volume_impact_sec': round(float(volume_impact), 1),
                'fitness_credit_sec': round(float(fitness_credit), 1)
            }
        }

    def get_improvement_timeline(self):
        self.ensure_up_to_date()
            
        df = self.df.copy()
        coefs = dict(zip(self.feature_cols, self.factor_model.coef_))
        
        # Calculate Adjusted Pace for each run:
        # Subtract environmental & fatigue & distance penalties so pace reflects pure fitness level under standard conditions (4mi, 60F, 9AM, 2d rest)
        adjusted_paces = []
        for _, row in df.iterrows():
            act_pace = row['pace_sec_mi']
            
            d_adj = (row['distance_mi'] - 4.0) * coefs['distance_mi']
            t_adj = (row['temp_f'] - 60.0) * coefs['temp_f'] + row['temp_over_75'] * coefs['temp_over_75']
            h_adj = (row['humidity'] - 50.0) * coefs['humidity']
            tod_adj = (row['local_hour'] - 9.0) * coefs['local_hour'] + (row['is_morning'] - 1) * coefs['is_morning']
            f_adj = row['ran_yesterday'] * coefs['ran_yesterday'] + (row['days_since_last_run'] - 2.0) * coefs['days_since_last_run']
            
            # Adjusted pace = actual pace minus environmental/fatigue distortions
            adj_pace = act_pace - (d_adj + t_adj + h_adj + tod_adj + f_adj)
            adjusted_paces.append(round(float(adj_pace), 1))
            
        df['adjusted_pace_sec'] = adjusted_paces
        
        # Non-linear exponential rolling fitness curve
        df['rolling_fitness_sec'] = df['adjusted_pace_sec'].ewm(span=4, min_periods=1).mean()
        
        # Linear macro trend line over weeks
        X_weeks = df[['weeks']]
        lr_trend = LinearRegression().fit(X_weeks, df['adjusted_pace_sec'])
        trend_preds = lr_trend.predict(X_weeks)
        df['trend_pace_sec'] = [round(float(p), 1) for p in trend_preds]
        
        total_improvement_sec = float(trend_preds[0] - trend_preds[-1])
        improvement_pct = float((total_improvement_sec / trend_preds[0]) * 100.0) if trend_preds[0] > 0 else 0.0
        
        runs_timeline = []
        for _, r in df.iterrows():
            act_m, act_s = int(r['pace_sec_mi'] // 60), int(r['pace_sec_mi'] % 60)
            adj_m, adj_s = int(r['adjusted_pace_sec'] // 60), int(r['adjusted_pace_sec'] % 60)
            roll_m, roll_s = int(r['rolling_fitness_sec'] // 60), int(r['rolling_fitness_sec'] % 60)
            tr_m, tr_s = int(r['trend_pace_sec'] // 60), int(r['trend_pace_sec'] % 60)
            
            d_adj = (r['distance_mi'] - 4.0) * coefs['distance_mi']
            t_adj = (r['temp_f'] - 60.0) * coefs['temp_f'] + r['temp_over_75'] * coefs['temp_over_75']
            h_adj = (r['humidity'] - 50.0) * coefs['humidity']
            tod_adj = (r['local_hour'] - 9.0) * coefs['local_hour'] + (r['is_morning'] - 1) * coefs['is_morning']
            f_adj = r['ran_yesterday'] * coefs['ran_yesterday'] + (r['days_since_last_run'] - 2.0) * coefs['days_since_last_run']

            runs_timeline.append({
                'id': r['id'],
                'date': r['date_str'],
                'time': r['local_dt'].strftime('%H:%M'),
                'distance_mi': r['distance_mi'],
                'temp_f': r['temp_f'],
                'humidity': r['humidity'],
                'ran_yesterday': int(r['ran_yesterday']),
                'days_since_last_run': round(float(r['days_since_last_run']), 1),
                'actual_pace_sec': int(r['pace_sec_mi']),
                'actual_pace_str': f"{act_m}:{act_s:02d}",
                'adjusted_pace_sec': int(r['adjusted_pace_sec']),
                'adjusted_pace_str': f"{adj_m}:{adj_s:02d}",
                'rolling_fitness_sec': int(r['rolling_fitness_sec']),
                'rolling_fitness_str': f"{roll_m}:{roll_s:02d}",
                'trend_pace_sec': int(r['trend_pace_sec']),
                'trend_pace_str': f"{tr_m}:{tr_s:02d}",
                'adjustments': {
                    'dist_impact_sec': round(float(d_adj), 1),
                    'temp_impact_sec': round(float(t_adj), 1),
                    'humidity_impact_sec': round(float(h_adj), 1),
                    'tod_impact_sec': round(float(tod_adj), 1),
                    'soreness_impact_sec': round(float(f_adj), 1)
                }
            })

        # Generate Parameter Relationship Curves for Visualization
        current_weeks = float(df['weeks'].max())
        
        # 1. Temperature Curve (40°F to 95°F)
        temp_curve = []
        for t in range(40, 96, 5):
            res = self.predict(distance_mi=4.0, temp_f=t, humidity=60.0, time_str="09:00", ran_yesterday=False, rest_days=2.0)
            temp_curve.append({
                'temp_f': t,
                'predicted_pace_sec': res['predicted_pace_sec'],
                'predicted_pace_str': res['predicted_pace_str']
            })

        # 2. Time of Day Curve (6 AM to 8 PM)
        tod_curve = []
        for h in range(6, 21):
            h_str = f"{h:02d}:00"
            res = self.predict(distance_mi=4.0, temp_f=65.0, humidity=60.0, time_str=h_str, ran_yesterday=False, rest_days=2.0)
            tod_curve.append({
                'hour': h,
                'hour_label': f"{h if h<=12 else h-12}:00 {'AM' if h<12 else 'PM'}",
                'predicted_pace_sec': res['predicted_pace_sec'],
                'predicted_pace_str': res['predicted_pace_str']
            })

        # 3. Distance Curve (1 to 12 miles)
        dist_curve = []
        for d in [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0]:
            res = self.predict(distance_mi=d, temp_f=65.0, humidity=60.0, time_str="09:00", ran_yesterday=False, rest_days=2.0)
            dist_curve.append({
                'distance_mi': d,
                'predicted_pace_sec': res['predicted_pace_sec'],
                'predicted_pace_str': res['predicted_pace_str']
            })
            
        return {
            'metrics': self.metrics,
            'summary': {
                'total_improvement_sec': round(total_improvement_sec, 1),
                'total_improvement_str': f"{int(abs(total_improvement_sec)//60)}m {int(abs(total_improvement_sec)%60)}s {'faster' if total_improvement_sec>=0 else 'slower'}",
                'improvement_rate_sec_per_month': round(float(lr_trend.coef_[0] * 4.345), 1),
                'is_improving': total_improvement_sec > 0
            },
            'parameter_curves': {
                'temp_curve': temp_curve,
                'tod_curve': tod_curve,
                'dist_curve': dist_curve
            },
            'runs': runs_timeline
        }

    def get_parameter_sensitivity_curves(self, distance_mi=4.0, temp_f=65.0, humidity=60.0, time_str="09:00", ran_yesterday=False, rest_days=2.0, recent_7d_miles=10.0, target_date_str=None, model_type="hybrid"):
        self.ensure_up_to_date()
            
        temp_curve = []
        for t in range(40, 96, 5):
            res = self.predict(distance_mi=distance_mi, temp_f=t, humidity=humidity, time_str=time_str, ran_yesterday=ran_yesterday, rest_days=rest_days, recent_7d_miles=recent_7d_miles, target_date_str=target_date_str, model_type=model_type)
            temp_curve.append({
                'temp_f': t,
                'predicted_pace_sec': res['predicted_pace_sec'],
                'predicted_pace_str': res['predicted_pace_str']
            })

        tod_curve = []
        for h in range(6, 21):
            h_str = f"{h:02d}:00"
            res = self.predict(distance_mi=distance_mi, temp_f=temp_f, humidity=humidity, time_str=h_str, ran_yesterday=ran_yesterday, rest_days=rest_days, recent_7d_miles=recent_7d_miles, target_date_str=target_date_str, model_type=model_type)
            tod_curve.append({
                'hour': h,
                'hour_label': f"{h if h<=12 else h-12}:00 {'AM' if h<12 else 'PM'}",
                'predicted_pace_sec': res['predicted_pace_sec'],
                'predicted_pace_str': res['predicted_pace_str']
            })

        dist_curve = []
        for d_val in [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 10.0, 12.0]:
            res = self.predict(distance_mi=d_val, temp_f=temp_f, humidity=humidity, time_str=time_str, ran_yesterday=ran_yesterday, rest_days=rest_days, recent_7d_miles=recent_7d_miles, target_date_str=target_date_str, model_type=model_type)
            dist_curve.append({
                'distance_mi': d_val,
                'predicted_pace_sec': res['predicted_pace_sec'],
                'predicted_pace_str': res['predicted_pace_str']
            })

        hum_curve = []
        for hum_val in range(20, 101, 10):
            res = self.predict(distance_mi=distance_mi, temp_f=temp_f, humidity=float(hum_val), time_str=time_str, ran_yesterday=ran_yesterday, rest_days=rest_days, recent_7d_miles=recent_7d_miles, target_date_str=target_date_str, model_type=model_type)
            hum_curve.append({
                'humidity': hum_val,
                'predicted_pace_sec': res['predicted_pace_sec'],
                'predicted_pace_str': res['predicted_pace_str']
            })

        return {
            'temp_curve': temp_curve,
            'tod_curve': tod_curve,
            'dist_curve': dist_curve,
            'hum_curve': hum_curve,
            'active_config': {
                'distance_mi': float(distance_mi),
                'temp_f': float(temp_f),
                'humidity': float(humidity),
                'time_str': time_str,
                'model_type': model_type
            }
        }


# Global model instance
model_instance = PacePredictorModel()

if __name__ == '__main__':
    print("Training Pace Predictor Model...")
    m = model_instance.train()
    print("Model Training Complete! Metrics:")
    print(json.dumps(m, indent=2))
    
    print("\nSample Prediction (4 miles, 82°F, 70% humidity, 2:00 PM, Ran Yesterday=True):")
    pred = model_instance.predict(distance_mi=4.0, temp_f=82.0, humidity=70.0, time_str="14:00", ran_yesterday=True)
    print(json.dumps(pred, indent=2))
    
    print("\nImprovement Timeline Summary:")
    timeline = model_instance.get_improvement_timeline()
    print(json.dumps(timeline['summary'], indent=2))
