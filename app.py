import ast
import json
import os
import xml.etree.ElementTree as ET
from flask import Flask, jsonify, send_from_directory, request, redirect
import pandas as pd
import math
from historical_runs import auto_heal_exercises

app = Flask(__name__, static_folder='static', static_url_path='')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXERCISES_CSV = os.path.join(BASE_DIR, 'my_exercises.csv')
HR_DIR = os.path.join(BASE_DIR, 'run_heart_rates')
ROUTES_DIR = os.path.join(BASE_DIR, 'run_routes')


def parse_splits(splits_str):
    """Safely parse splits list from string representation."""
    if not isinstance(splits_str, str) or not splits_str.strip():
        return []
    try:
        # Splits are formatted as a string representation of list of dicts
        # e.g., "[{'startTime': '...', ...}]"
        splits_list = ast.literal_eval(splits_str)
        parsed = []
        for i, split in enumerate(splits_list):
            dist_mm = split.get('metricsSummary', {}).get('distanceMillimeters', 0)
            dist_mi = dist_mm / 1609344.0
            pace_sec_m = split.get('metricsSummary', {}).get(
                'averagePaceSecondsPerMeter', 0
            )
            pace_sec_mi = pace_sec_m * 1609.344

            # Format split pace
            min_part = int(pace_sec_mi / 60)
            sec_part = int(pace_sec_mi % 60)
            pace_str = f"{min_part}:{sec_part:02d}"

            # Only append valid splits
            if dist_mi > 0.01:
                parsed.append(
                    {
                        "split_num": i + 1,
                        "distance_mi": round(dist_mi, 2),
                        "pace_sec_mi": int(pace_sec_mi),
                        "pace_str": pace_str,
                    }
                )
        return parsed
    except Exception as e:
        print(f"Error parsing splits: {e}")
        return []


def parse_tcx_xml(xml_str):
    """Parse Garmin TCX XML data and return list of coordinates and metrics."""
    if not xml_str:
        return []
    try:
        root = ET.fromstring(xml_str)
        ns = {'ns': 'http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2'}
        points = []

        trackpoints = root.findall('.//ns:Trackpoint', ns)
        for tp in trackpoints:
            pos = tp.find('ns:Position', ns)
            if pos is None:
                continue

            lat_node = pos.find('ns:LatitudeDegrees', ns)
            lon_node = pos.find('ns:LongitudeDegrees', ns)
            if lat_node is None or lon_node is None:
                continue

            lat = float(lat_node.text)
            lon = float(lon_node.text)

            time_node = tp.find('ns:Time', ns)
            time_str = time_node.text if time_node is not None else ""

            alt_node = tp.find('ns:AltitudeMeters', ns)
            alt = float(alt_node.text) if alt_node is not None else 0.0

            dist_node = tp.find('ns:DistanceMeters', ns)
            dist_mi = (
                (float(dist_node.text) / 1609.344)
                if dist_node is not None
                else 0.0
            )

            hr_node = tp.find('ns:HeartRateBpm/ns:Value', ns)
            hr = int(hr_node.text) if hr_node is not None else None

            points.append(
                {
                    "lat": lat,
                    "lon": lon,
                    "alt_ft": round(alt * 3.28084, 1),  # Convert to feet
                    "time": time_str,
                    "hr": hr,
                    "dist_mi": round(dist_mi, 3),
                }
            )
        return points
    except Exception as e:
        print(f"Error parsing TCX XML: {e}")
        return []


@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')


def _load_runs_from_csv():
    df = auto_heal_exercises(BASE_DIR)
    if df is None or df.empty:
        if not os.path.exists(EXERCISES_CSV):
            return []
        df = pd.read_csv(EXERCISES_CSV)
    if df.empty:
        return []

    runs = df[df['exercise.exerciseType'] == 'RUNNING'].copy()
    if runs.empty:
        return []

    # Sort by start time ascending
    runs['startTime'] = pd.to_datetime(
        runs['exercise.interval.startTime'], format='ISO8601'
    )
    runs = runs.sort_values('startTime')

    # Filter for runs from 2025-12-29 onwards (when the user got their watch)
    runs = runs[runs['startTime'] >= pd.to_datetime('2025-12-29', utc=True)]

    runs_list = []
    for idx, row in runs.iterrows():
        run_id = row['name'].split('/')[-1]
        start_time = row['exercise.interval.startTime']
        end_time = row['exercise.interval.endTime']

        # Basic metrics
        dist_mm = row.get('exercise.metricsSummary.distanceMillimeters', 0)
        dist_mi = dist_mm / 1609344.0 if pd.notna(dist_mm) else 0.0

        dur_str = str(row.get('exercise.activeDuration', '0s')).replace(
            's', ''
        )
        duration_sec = float(dur_str) if dur_str else 0.0

        sec_per_meter = row.get(
            'exercise.metricsSummary.averagePaceSecondsPerMeter'
        )
        if pd.notna(sec_per_meter) and sec_per_meter > 0:
            pace_sec_mi = sec_per_meter * 1609.344
            pace_min = int(pace_sec_mi / 60)
            pace_sec = int(pace_sec_mi % 60)
            pace_str = f"{pace_min}:{pace_sec:02d}"
        else:
            pace_sec_mi = 0
            pace_str = "N/A"

        # Filter out accidental runs (< 0.5 miles) and very slow outlier activities (> 15:00 min/mi)
        if dist_mi < 0.5 or (pace_sec_mi > 0 and pace_sec_mi > 900):
            continue

        avg_hr = row.get(
            'exercise.metricsSummary.averageHeartRateBeatsPerMinute'
        )
        avg_hr = int(avg_hr) if pd.notna(avg_hr) else None

        # Aerobic Efficiency = Speed (mph) / Average Heart Rate (bpm)
        # Speed = distance (mi) / duration (hr)
        if dist_mi > 0 and duration_sec > 0 and avg_hr and avg_hr > 0:
            speed_mph = dist_mi / (duration_sec / 3600.0)
            aerobic_efficiency = speed_mph / avg_hr
        else:
            aerobic_efficiency = None

        # Form & Cadence
        cadence = row.get(
            'exercise.metricsSummary.mobilityMetrics.avgCadenceStepsPerMinute'
        )
        cadence = int(cadence) if pd.notna(cadence) else None

        stride_mm = row.get(
            'exercise.metricsSummary.mobilityMetrics.avgStrideLengthMillimeters'
        )
        stride_cm = round(stride_mm / 10.0, 1) if pd.notna(stride_mm) else None

        # Splits
        splits_raw = row.get('exercise.splits')
        splits = parse_splits(splits_raw) if pd.notna(splits_raw) else []

        # Heart Rate Zone durations (convert from strings like '2280s')
        def parse_zone_time(val):
            if pd.isna(val):
                return 0
            return int(float(str(val).replace('s', '')))

        light = parse_zone_time(
            row.get('exercise.metricsSummary.heartRateZoneDurations.lightTime')
        )
        mod = parse_zone_time(
            row.get(
                'exercise.metricsSummary.heartRateZoneDurations.moderateTime'
            )
        )
        vig = parse_zone_time(
            row.get(
                'exercise.metricsSummary.heartRateZoneDurations.vigorousTime'
            )
        )
        peak = parse_zone_time(
            row.get('exercise.metricsSummary.heartRateZoneDurations.peakTime')
        )

        # Metadata
        has_gps = bool(row.get('exercise.exerciseMetadata.hasGps', False))

        runs_list.append(
            {
                "id": run_id,
                "date": pd.to_datetime(start_time).strftime('%Y-%m-%d'),
                "time": pd.to_datetime(start_time).strftime('%H:%M'),
                "datetime": start_time,
                "distance_mi": round(dist_mi, 2),
                "duration_sec": int(duration_sec),
                "duration_str": f"{int(duration_sec // 60)}:{int(duration_sec % 60):02d}",
                "pace_sec_mi": int(pace_sec_mi),
                "pace_str": pace_str,
                "avg_hr": avg_hr,
                "calories": int(row.get('exercise.metricsSummary.caloriesKcal', 0)),
                "aerobic_efficiency": (
                    round(aerobic_efficiency, 4)
                    if aerobic_efficiency
                    else None
                ),
                "cadence": cadence,
                "stride_cm": stride_cm,
                "has_gps": has_gps,
                "splits": splits,
                "zones": {
                    "light_sec": light,
                    "moderate_sec": mod,
                    "vigorous_sec": vig,
                    "peak_sec": peak,
                },
            }
        )
    return runs_list


@app.route('/api/debug')
def debug_info():
    csv_path = os.path.join(BASE_DIR, 'my_exercises.csv')
    all_csv_path = os.path.join(BASE_DIR, 'my_exercises_all.csv')

    my_ex_exists = os.path.exists(csv_path)
    my_ex_all_exists = os.path.exists(all_csv_path)

    my_ex_len = len(pd.read_csv(csv_path)) if my_ex_exists else 0
    my_ex_all_len = len(pd.read_csv(all_csv_path)) if my_ex_all_exists else 0

    runs = _load_runs_from_csv()

    return jsonify({
        "my_exercises_exists": my_ex_exists,
        "my_exercises_len": my_ex_len,
        "my_exercises_all_exists": my_ex_all_exists,
        "my_exercises_all_len": my_ex_all_len,
        "loaded_runs_count": len(runs),
        "loaded_runs_total_dist": round(sum(r['distance_mi'] for r in runs), 2),
        "run_dates": [f"{r['date']} ({r['id']}): {r['distance_mi']} mi" for r in runs]
    })


@app.route('/api/sync', methods=['POST'])
def sync_data():
    import subprocess
    import sys
    try:
        script_path = os.path.join(BASE_DIR, 'get_data.py')
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            check=True
        )
        print("Data sync script output:\n", result.stdout)
        return jsonify({"success": True, "output": result.stdout})
    except subprocess.CalledProcessError as e:
        print("Data sync script failed. Error:\n", e.stderr)
        error_msg = "Data sync failed."
        if e.stderr:
            lines = e.stderr.splitlines()
            idx = -1
            for i in range(len(lines) - 1, -1, -1):
                if lines[i].startswith("Exception:"):
                    idx = i
                    break
            if idx != -1:
                error_msg = "\n".join(lines[idx:])
                if error_msg.startswith("Exception:"):
                    error_msg = error_msg[len("Exception:"):].strip()
            else:
                error_msg = e.stderr.strip().splitlines()[-1] if e.stderr.strip() else "Subprocess failed."
        return jsonify({"success": False, "error": error_msg, "output": e.stdout}), 500
    except Exception as e:
        print("Data sync failed with error:", str(e))
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/auth/google')
def auth_google():
    credentials_path = os.path.join(BASE_DIR, 'credentials.json')
    if not os.path.exists(credentials_path):
        return jsonify({"error": "credentials.json not found on server"}), 400
    try:
        with open(credentials_path, 'r') as f:
            creds = json.load(f)
        client_id = creds.get("client_id")
        if not client_id:
            return jsonify({"error": "client_id not configured in credentials.json"}), 400
        
        # Build redirect URI dynamically
        redirect_uri = f"{request.scheme}://{request.host}/api/auth/google/callback"
        
        auth_url = (
            "https://accounts.google.com/o/oauth2/v2/auth?"
            f"client_id={client_id}&"
            f"redirect_uri={redirect_uri}&"
            "response_type=code&"
            "scope=https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly%20https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly%20https://www.googleapis.com/auth/googlehealth.location.readonly&"
            "access_type=offline&"
            "prompt=consent"
        )
        return redirect(auth_url)
    except Exception as e:
        return jsonify({"error": f"Failed to initiate OAuth: {str(e)}"}), 500


@app.route('/api/auth/google/callback')
def auth_google_callback():
    import requests
    code = request.args.get('code')
    error = request.args.get('error')
    if error:
        return f"OAuth Error: {error}. Please close this window and try again."
    if not code:
        return "Authorization code not found. Please try again."

    credentials_path = os.path.join(BASE_DIR, 'credentials.json')
    if not os.path.exists(credentials_path):
        return "credentials.json not found on server."
        
    try:
        with open(credentials_path, 'r') as f:
            creds = json.load(f)
        client_id = creds.get("client_id")
        client_secret = creds.get("client_secret")
        
        redirect_uri = f"{request.scheme}://{request.host}/api/auth/google/callback"
        
        url = "https://oauth2.googleapis.com/token"
        data = {
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code"
        }
        res = requests.post(url, data=data)
        if res.status_code == 200:
            tokens = res.json()
            refresh_token = tokens.get("refresh_token")
            
            if refresh_token:
                creds["refresh_token"] = refresh_token
            
            with open(credentials_path, 'w') as f:
                json.dump(creds, f, indent=2)
                
            return """
            <html>
                <body style="font-family: sans-serif; text-align: center; padding: 50px; background-color: #080c14; color: #f8fafc;">
                    <div style="max-width: 500px; margin: 0 auto; background: rgba(15, 23, 42, 0.65); border: 1px solid rgba(255, 255, 255, 0.08); padding: 30px; border-radius: 16px; box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37); backdrop-filter: blur(8px);">
                        <h2 style="color: #34d399; margin-bottom: 20px; font-family: sans-serif;">✓ Authentication Successful</h2>
                        <p style="font-size: 16px; line-height: 1.6; color: #94a3b8;">
                            Google API access has been successfully authorized and your credentials file has been updated.
                        </p>
                        <p style="font-size: 14px; color: #94a3b8; margin-top: 20px;">
                            You can now close this tab and click <strong>Sync Fitbit Data</strong> on the dashboard.
                        </p>
                        <button onclick="window.close();" style="margin-top: 20px; padding: 12px 24px; font-size: 14px; background: linear-gradient(135deg, rgba(56, 189, 248, 0.2), rgba(52, 211, 153, 0.2)); border: 1px solid rgba(52, 211, 153, 0.4); color: white; border-radius: 8px; cursor: pointer; font-weight: bold; transition: all 0.3s ease;">
                            Close Window
                        </button>
                    </div>
                </body>
            </html>
            """
        else:
            return f"Failed to exchange token ({res.status_code}): {res.text}"
    except Exception as e:
        return f"Error during token exchange: {str(e)}"


@app.route('/api/auth/save-token', methods=['POST'])
def save_token():
    try:
        data = request.get_json()
        if not data or 'refresh_token' not in data:
            return jsonify({"success": False, "error": "refresh_token is required"}), 400
            
        refresh_token = data['refresh_token'].strip()
        if not refresh_token:
            return jsonify({"success": False, "error": "refresh_token cannot be empty"}), 400
            
        credentials_path = os.path.join(BASE_DIR, 'credentials.json')
        if not os.path.exists(credentials_path):
            return jsonify({"success": False, "error": "credentials.json not found on server"}), 400
            
        with open(credentials_path, 'r') as f:
            creds = json.load(f)
            
        creds['refresh_token'] = refresh_token
        
        with open(credentials_path, 'w') as f:
            json.dump(creds, f, indent=2)
            
        return jsonify({"success": True, "message": "Refresh token updated successfully!"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/runs')
def get_runs():
    try:
        runs_list = _load_runs_from_csv()
        return jsonify(runs_list)
    except Exception as e:
        print(f"Error serving runs API: {e}")
        return jsonify({"error": str(e)}), 500


COORDINATE_CACHE = {}

def downsample_coordinates(coords, n_points=100):
    if not coords:
        return []
    if len(coords) <= n_points:
        return coords
    step = len(coords) / n_points
    return [coords[int(i * step)] for i in range(n_points)]

def get_run_coordinates(run_id):
    if run_id in COORDINATE_CACHE:
        return COORDINATE_CACHE[run_id]

    # Find the Route JSON file for this run ID
    route_file = None
    for f in os.listdir(ROUTES_DIR):
        if f.endswith(f"_{run_id}.json"):
            route_file = os.path.join(ROUTES_DIR, f)
            break

    if not route_file or not os.path.exists(route_file):
        COORDINATE_CACHE[run_id] = []
        return []

    try:
        with open(route_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        tcx_data = data.get("tcxData", "")
        points = parse_tcx_xml(tcx_data)
        
        coords = [{"lat": p["lat"], "lon": p["lon"]} for p in points if "lat" in p and "lon" in p]
        downsampled = downsample_coordinates(coords, 100)
        COORDINATE_CACHE[run_id] = downsampled
        return downsampled
    except Exception as e:
        print(f"Error serving/caching route for run {run_id}: {e}")
        COORDINATE_CACHE[run_id] = []
        return []


def compute_route_similarity(target_coords, candidate_coords, threshold_m=80.0):
    if not target_coords or not candidate_coords:
        return 0.0, 0.0

    # Get reference lat from target start point for flat-earth approximation
    ref_lat = target_coords[0]['lat']
    lat_rad = math.radians(ref_lat)
    meters_per_lat = 111132.0
    meters_per_lon = 111320.0 * math.cos(lat_rad)

    # Calculate target matches in candidate
    matched_target = 0
    for t_pt in target_coords:
        t_lat, t_lon = t_pt['lat'], t_pt['lon']
        found = False
        for c_pt in candidate_coords:
            c_lat, c_lon = c_pt['lat'], c_pt['lon']
            dy = (t_lat - c_lat) * meters_per_lat
            dx = (t_lon - c_lon) * meters_per_lon
            dist_sq = dx * dx + dy * dy
            if dist_sq <= threshold_m * threshold_m:
                found = True
                break
        if found:
            matched_target += 1

    # Calculate candidate matches in target
    matched_candidate = 0
    for c_pt in candidate_coords:
        c_lat, c_lon = c_pt['lat'], c_pt['lon']
        found = False
        for t_pt in target_coords:
            t_lat, t_lon = t_pt['lat'], t_pt['lon']
            dy = (t_lat - c_lat) * meters_per_lat
            dx = (t_lon - c_lon) * meters_per_lon
            dist_sq = dx * dx + dy * dy
            if dist_sq <= threshold_m * threshold_m:
                found = True
                break
        if found:
            matched_candidate += 1

    fwd_score = matched_target / len(target_coords)
    bwd_score = matched_candidate / len(candidate_coords)

    return fwd_score, bwd_score


@app.route('/api/runs/<run_id>/compare-similarity')
def compare_run_similarity(run_id):
    try:
        runs_list = _load_runs_from_csv()
        
        # Find target run
        target_run = None
        for run in runs_list:
            if run['id'] == run_id:
                target_run = run
                break
                
        if not target_run:
            return jsonify({"error": "Target run not found"}), 404
            
        target_coords = get_run_coordinates(run_id)
        
        results = []
        for run in runs_list:
            run_item = dict(run) # copy
            
            if run_item['id'] == run_id:
                run_item['exact_score'] = 1.0
                run_item['overlap_score'] = 1.0
            elif not run_item['has_gps'] or not target_coords:
                run_item['exact_score'] = 0.0
                run_item['overlap_score'] = 0.0
            else:
                candidate_coords = get_run_coordinates(run_item['id'])
                if not candidate_coords:
                    run_item['exact_score'] = 0.0
                    run_item['overlap_score'] = 0.0
                else:
                    fwd_score, bwd_score = compute_route_similarity(target_coords, candidate_coords)
                    run_item['exact_score'] = round(fwd_score * bwd_score, 4)
                    
                    # Overlap score: shorter run is a subset of longer run
                    if run_item['distance_mi'] < target_run['distance_mi']:
                        run_item['overlap_score'] = round(bwd_score, 4)
                    else:
                        run_item['overlap_score'] = round(fwd_score, 4)
                        
            results.append(run_item)
            
        return jsonify(results)
    except Exception as e:
        print(f"Error in compare-similarity: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/runs/<run_id>/hr')
def get_run_hr(run_id):
    if not os.path.exists(HR_DIR):
        return jsonify([])

    # Find the HR CSV file for this run ID
    hr_file = None
    for f in os.listdir(HR_DIR):
        if f.endswith(f"_{run_id}.csv"):
            hr_file = os.path.join(HR_DIR, f)
            break

    if not hr_file or not os.path.exists(hr_file):
        return jsonify([])

    try:
        df = pd.read_csv(hr_file)
        if df.empty:
            return jsonify([])

        # Sort by physical time
        df['time'] = pd.to_datetime(
            df['heartRate.sampleTime.physicalTime'], format='ISO8601'
        )
        df = df.sort_values('time')

        # Convert to relative time in seconds from start
        start_time = df['time'].min()
        df['rel_sec'] = (df['time'] - start_time).dt.total_seconds()

        hr_list = []
        for idx, row in df.iterrows():
            hr_list.append(
                {
                    "sec": int(row['rel_sec']),
                    "time": row['time'].strftime('%H:%M:%S'),
                    "bpm": int(row['heartRate.beatsPerMinute']),
                }
            )

        return jsonify(hr_list)
    except Exception as e:
        print(f"Error serving HR data for run {run_id}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/runs/<run_id>/route')
def get_run_route(run_id):
    if not os.path.exists(ROUTES_DIR):
        return jsonify([])

    # Find the Route JSON file for this run ID
    route_file = None
    for f in os.listdir(ROUTES_DIR):
        if f.endswith(f"_{run_id}.json"):
            route_file = os.path.join(ROUTES_DIR, f)
            break

    if not route_file or not os.path.exists(route_file):
        return jsonify([])

    try:
        with open(route_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        tcx_data = data.get("tcxData", "")
        points = parse_tcx_xml(tcx_data)
        return jsonify(points)
    except Exception as e:
        print(f"Error serving route for run {run_id}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/runs/progress-curves')
def get_progress_curves():
    if not os.path.exists(EXERCISES_CSV) or not os.path.exists(ROUTES_DIR):
        return jsonify([])

    try:
        df = pd.read_csv(EXERCISES_CSV)
        if df.empty:
            return jsonify([])

        runs = df[df['exercise.exerciseType'] == 'RUNNING'].copy()
        if runs.empty:
            return jsonify([])

        runs['startTime'] = pd.to_datetime(
            runs['exercise.interval.startTime'], format='ISO8601'
        )
        runs = runs.sort_values('startTime')
        runs = runs[runs['startTime'] >= pd.to_datetime('2025-12-29', utc=True)]

        curves = []
        for idx, row in runs.iterrows():
            run_id = row['name'].split('/')[-1]
            start_time_str = row['exercise.interval.startTime']

            # Basic metrics check
            dist_mm = row.get('exercise.metricsSummary.distanceMillimeters', 0)
            dist_mi = dist_mm / 1609344.0 if pd.notna(dist_mm) else 0.0

            sec_per_meter = row.get(
                'exercise.metricsSummary.averagePaceSecondsPerMeter'
            )
            pace_sec_mi = (
                sec_per_meter * 1609.344
                if pd.notna(sec_per_meter) and sec_per_meter > 0
                else 0
            )

            # Apply identical filters
            if dist_mi < 0.5 or (pace_sec_mi > 0 and pace_sec_mi > 900):
                continue

            # Find route file
            route_file = None
            for f in os.listdir(ROUTES_DIR):
                if f.endswith(f"_{run_id}.json"):
                    route_file = os.path.join(ROUTES_DIR, f)
                    break

            if not route_file or not os.path.exists(route_file):
                continue

            with open(route_file, 'r', encoding='utf-8') as rf:
                route_data = json.load(rf)

            tcx_data = route_data.get("tcxData", "")
            if not tcx_data:
                continue

            # Parse XML
            root = ET.fromstring(tcx_data)
            ns = {
                'ns': 'http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2'
            }
            trackpoints = root.findall('.//ns:Trackpoint', ns)

            if not trackpoints:
                continue

            # Determine start time from first point
            first_time_node = trackpoints[0].find('ns:Time', ns)
            if first_time_node is None:
                continue

            start_t = pd.to_datetime(first_time_node.text)

            # Parse all trackpoints to run rolling calculations
            all_pts = []
            for tp in trackpoints:
                time_node = tp.find('ns:Time', ns)
                dist_node = tp.find('ns:DistanceMeters', ns)
                if time_node is None:
                    continue
                t_pt = pd.to_datetime(time_node.text)
                rel_sec = (t_pt - start_t).total_seconds()
                dist_meters = float(dist_node.text) if dist_node is not None else 0.0
                dist_mi_pt = dist_meters / 1609.344
                all_pts.append((rel_sec, dist_mi_pt))

            # Calculate rolling pace (60s window)
            calculated_pts = []
            for i in range(len(all_pts)):
                t_curr, d_curr = all_pts[i]
                
                # Find lookback point for 60s
                j = i
                while j > 0 and t_curr - all_pts[j][0] < 60:
                    j -= 1
                    
                t_prev, d_prev = all_pts[j]
                dt = t_curr - t_prev
                dd = d_curr - d_prev
                
                # Fallback to cumulative pace if we haven't reached 60s yet
                if t_curr < 60:
                    dt = t_curr
                    dd = d_curr
                    
                if dd > 0.001 and dt > 0:
                    pace_sec = dt / dd
                    if pace_sec > 900:
                        pace_sec = 900
                    elif pace_sec < 240:
                        pace_sec = 240
                else:
                    pace_sec = 900
                    
                calculated_pts.append({
                    "sec": int(t_curr),
                    "dist_mi": round(d_curr, 3),
                    "pace_sec": int(pace_sec)
                })

            # Downsample to keep payload small: 1 point every 15 seconds
            run_points = []
            last_sec = -999.0
            for pt in calculated_pts:
                if pt["sec"] - last_sec >= 15:
                    run_points.append(pt)
                    last_sec = pt["sec"]

            # Always ensure the final point is included
            if calculated_pts and (not run_points or run_points[-1]["sec"] != calculated_pts[-1]["sec"]):
                run_points.append(calculated_pts[-1])

            curves.append(
                {
                    "id": run_id,
                    "date": pd.to_datetime(start_time_str).strftime('%Y-%m-%d'),
                    "points": run_points,
                }
            )

        return jsonify(curves)
    except Exception as e:
        print(f"Error serving progress curves: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8088)
