import json
import os
import requests
import pandas as pd

# Paste the long Access Token string you just copied from the OAuth Playground
ACCESS_TOKEN = ""

# Set up the secure authentication headers required by Google
headers = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/json",
}

def get_headers():
    token = ACCESS_TOKEN
    credentials_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'credentials.json')
    if os.path.exists(credentials_path):
        try:
            with open(credentials_path, 'r') as f:
                creds = json.load(f)
            url = "https://oauth2.googleapis.com/token"
            data = {
                "client_id": creds.get("client_id"),
                "client_secret": creds.get("client_secret"),
                "refresh_token": creds.get("refresh_token"),
                "grant_type": "refresh_token"
            }
            res = requests.post(url, data=data)
            if res.status_code == 200:
                token = res.json().get("access_token")
                print("Successfully refreshed Google API access token using refresh token.")
            else:
                raise Exception(f"OAuth token refresh failed ({res.status_code}): {res.text}")
        except Exception as e:
            raise Exception(f"Failed to refresh Google API token: {str(e)}")
    elif not token:
        raise Exception("No API credentials or access token found. Please configure credentials.")
            
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

# Base endpoint for Google Health API v4
BASE_URL = "https://health.googleapis.com/v4"


def get_recent_exercises(start_date="2025-12-01T00:00:00Z"):
    """Fetches a list of tracked exercises (runs, walks, etc.) paginating to get all history from start_date onwards."""
    url = f"{BASE_URL}/users/me/dataTypes/exercise/dataPoints"
    all_points = []
    page_token = None

    print(f"Fetching tracked exercises with pagination (from {start_date})...")
    while True:
        params = {}
        if page_token:
            params["pageToken"] = page_token
        elif start_date:
            params["filter"] = f'exercise.interval.start_time >= "{start_date}"'

        response = requests.get(url, headers=headers, params=params)
        # Fallback if filter expression is rejected by API
        if response.status_code != 200 and "filter" in params:
            del params["filter"]
            response = requests.get(url, headers=headers, params=params)

        if response.status_code == 200:
            data = response.json()
            points = data.get("dataPoints", [])
            all_points.extend(points)
            print(f"Fetched {len(points)} exercises. Total: {len(all_points)}")

            page_token = data.get("nextPageToken")
            if not page_token:
                break
        else:
            raise Exception(f"Error fetching exercises ({response.status_code}): {response.text}")

    if not all_points:
        print("No exercise data points found.")
        return None

    # Flatten into a Pandas DataFrame for easy scanning
    df = pd.json_normalize(all_points)
    print(f"\nFound {len(df)} total exercises!")
    return df


def save_exercises(new_df, csv_path="my_exercises.csv"):
    """Merges newly fetched exercises with existing CSV to prevent loss of historical data."""
    if new_df is None or new_df.empty:
        if os.path.exists(csv_path):
            return pd.read_csv(csv_path)
        return new_df

    if os.path.exists(csv_path):
        try:
            existing_df = pd.read_csv(csv_path)
            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
            if "name" in combined_df.columns:
                combined_df["_run_id"] = combined_df["name"].astype(str).apply(lambda x: x.split("/")[-1])
                combined_df = combined_df.drop_duplicates(subset=["_run_id"], keep="last").drop(columns=["_run_id"])
            if "exercise.interval.startTime" in combined_df.columns:
                combined_df["_sort_time"] = pd.to_datetime(combined_df["exercise.interval.startTime"], format="ISO8601")
                combined_df = combined_df.sort_values("_sort_time").drop(columns=["_sort_time"])
            combined_df.to_csv(csv_path, index=False)
            print(f"Successfully merged {len(new_df)} new data points with existing exercises. Total saved: {len(combined_df)}")
            return combined_df
        except Exception as e:
            print(f"Error merging exercise data: {e}. Overwriting CSV fallback.")
            new_df.to_csv(csv_path, index=False)
            return new_df
    else:
        new_df.to_csv(csv_path, index=False)
        return new_df


def download_run_heart_rates(df):
    """Downloads intraday heart rate data for every RUNNING exercise and caches as CSV."""
    if "exercise.exerciseType" not in df.columns:
        print("No exerciseType column found in data.")
        return

    runs = df[df["exercise.exerciseType"] == "RUNNING"].copy()
    if runs.empty:
        print("No running exercises found to download heart rates for.")
        return

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_heart_rates")
    os.makedirs(out_dir, exist_ok=True)
    url = f"{BASE_URL}/users/me/dataTypes/heart-rate/dataPoints"

    print(f"\nChecking heart rate data for {len(runs)} runs...")
    for idx, row in runs.iterrows():
        start_str = row["exercise.interval.startTime"]
        end_str = row["exercise.interval.endTime"]
        date_str = pd.to_datetime(start_str).strftime('%Y%m%d_%H%M%S')
        run_id = row["name"].split("/")[-1]

        out_path = os.path.join(out_dir, f"run_hr_{date_str}_{run_id}.csv")
        if os.path.exists(out_path):
            continue

        avg_hr = row.get("exercise.metricsSummary.averageHeartRateBeatsPerMinute")
        if pd.isna(avg_hr) or avg_hr == 0:
            continue

        print(f"Fetching heart rate for run {date_str} ({start_str} to {end_str})...")
        all_points = []
        page_token = None
        filter_expr = f'heart_rate.sample_time.physical_time >= "{start_str}" AND heart_rate.sample_time.physical_time < "{end_str}"'

        while True:
            params = {"filter": filter_expr, "pageSize": 2000}
            if page_token:
                params["pageToken"] = page_token

            response = requests.get(url, headers=headers, params=params)
            if response.status_code != 200:
                raise Exception(f"Error fetching HR ({response.status_code}): {response.text}")

            data = response.json()
            points = data.get("dataPoints", [])
            all_points.extend(points)

            page_token = data.get("nextPageToken")
            if not page_token:
                break

        print(f"  Fetched {len(all_points)} HR points.")
        if all_points:
            hr_df = pd.json_normalize(all_points)
            hr_df.to_csv(out_path, index=False)


def download_run_tcx_routes(df):
    """Downloads TCX route files for every RUNNING exercise and caches as TCX JSON."""
    if "exercise.exerciseType" not in df.columns:
        return

    runs = df[df["exercise.exerciseType"] == "RUNNING"].copy()
    if runs.empty:
        return

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_routes")
    os.makedirs(out_dir, exist_ok=True)

    print(f"\nChecking GPS route data for {len(runs)} runs...")
    for idx, row in runs.iterrows():
        has_gps = row.get("exercise.exerciseMetadata.hasGps")
        if not has_gps:
            continue

        start_str = row["exercise.interval.startTime"]
        date_str = pd.to_datetime(start_str).strftime('%Y%m%d_%H%M%S')
        run_name = row["name"]  # Full name e.g. users/me/dataTypes/exercise/dataPoints/83318539700303576
        run_id = run_name.split("/")[-1]

        out_path = os.path.join(out_dir, f"run_route_{date_str}_{run_id}.json")
        if os.path.exists(out_path):
            continue

        print(f"Fetching GPS TCX data for run {date_str}...")
        url = f"{BASE_URL}/{run_name}:exportExerciseTcx"
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            data = response.json()
            tcx_data = data.get("tcxData", "")
            print(f"  Fetched TCX data ({len(tcx_data)} chars). Saving route...")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump({"tcxData": tcx_data}, f, indent=2)
        else:
            raise Exception(f"Error fetching GPS route ({response.status_code}): {response.text}")


def get_heart_rate_samples():
    """Fetches high-density time-series heart rate sample data (last 100)."""
    url = f"{BASE_URL}/users/me/dataTypes/heart-rate/dataPoints"
    params = {"pageSize": 100}

    print("\nFetching intraday heart rate data points...")
    response = requests.get(url, headers=headers, params=params)

    if response.status_code == 200:
        data = response.json()
        points = data.get("dataPoints", [])
        if not points:
            print("No heart rate data points found.")
            return None
        df = pd.json_normalize(points)
        return df
    else:
        raise Exception(f"Error fetching heart rate ({response.status_code}): {response.text}")


# --- Execution Flow ---
if __name__ == "__main__":
    # Dynamically update headers using credentials.json if available
    headers.update(get_headers())
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(base_dir, "my_exercises.csv")

    # 1. Pull exercise sessions (great for isolating specific running workouts)
    exercise_df = get_recent_exercises()
    if exercise_df is not None:
        # Display the first few workouts
        print(exercise_df.head(5))
        # Merge with existing CSV to prevent overwriting historical runs
        merged_df = save_exercises(exercise_df, csv_path)

        # 2. Download detailed heart rate metrics and routes for each run
        download_run_heart_rates(merged_df)
        download_run_tcx_routes(merged_df)
    elif os.path.exists(csv_path):
        existing_df = pd.read_csv(csv_path)
        download_run_heart_rates(existing_df)
        download_run_tcx_routes(existing_df)

    # 3. Pull raw general heart rate samples
    hr_df = get_heart_rate_samples()
    if hr_df is not None:
        print("\nFirst few heart rate data points:")
        print(hr_df.head(10))
        hr_df.to_csv(os.path.join(base_dir, "my_heart_rate_samples.csv"), index=False)