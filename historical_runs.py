import pandas as pd
import os

# Hardcoded reference dictionary of early watch runs (Dec 29, 2025 - Mar 8, 2026)
# to guarantee full history is auto-healed across all deployments.
EMBEDDED_HISTORICAL_RUNS = [
  {
    "name": "users/6365399212480104868/dataTypes/exercise/dataPoints/4677591905212757976",
    "dataSource.recordingMethod": "ACTIVELY_MEASURED",
    "dataSource.device.formFactor": "WATCH",
    "dataSource.device.displayName": "Google Pixel Watch 4 (45mm)",
    "dataSource.platform": "FITBIT",
    "exercise.interval.startTime": "2025-12-29T19:16:31Z",
    "exercise.interval.startUtcOffset": "-18000s",
    "exercise.interval.endTime": "2025-12-29T19:49:12.756Z",
    "exercise.interval.endUtcOffset": "-18000s",
    "exercise.exerciseType": "RUNNING",
    "exercise.metricsSummary.caloriesKcal": 444.0,
    "exercise.metricsSummary.distanceMillimeters": 5370258.0,
    "exercise.metricsSummary.steps": 4697.0,
    "exercise.metricsSummary.averagePaceSecondsPerMeter": 0.365345557788102,
    "exercise.metricsSummary.averageHeartRateBeatsPerMinute": 154.0,
    "exercise.metricsSummary.elevationGainMillimeters": 39396.0,
    "exercise.metricsSummary.activeZoneMinutes": 62.0,
    "exercise.metricsSummary.heartRateZoneDurations.lightTime": "0s",
    "exercise.metricsSummary.heartRateZoneDurations.moderateTime": "120s",
    "exercise.metricsSummary.heartRateZoneDurations.vigorousTime": "1800s",
    "exercise.metricsSummary.heartRateZoneDurations.peakTime": "0s",
    "exercise.displayName": "Run",
    "exercise.activeDuration": "1962s",
    "exercise.updateTime": "2025-12-29T19:49:15.540118Z",
    "exercise.createTime": "2025-12-29T19:47:33.407982Z",
    "exercise.splits": "[{'startTime': '2025-12-29T19:16:32Z', 'startUtcOffset': '-18000s', 'endTime': '2025-12-29T19:26:02.827663385Z', 'endUtcOffset': '-18000s', 'activeDuration': '570.827663385s', 'metricsSummary': {'distanceMillimeters': 1609344, 'averagePaceSecondsPerMeter': 0.35469584742511475}, 'splitType': 'DISTANCE'}, {'startTime': '2025-12-29T19:26:02.827663385Z', 'startUtcOffset': '-18000s', 'endTime': '2025-12-29T19:35:46.903964177Z', 'endUtcOffset': '-18000s', 'activeDuration': '584.076300792s', 'metricsSummary': {'distanceMillimeters': 1609344, 'averagePaceSecondsPerMeter': 0.36292819864287846}, 'splitType': 'DISTANCE'}, {'startTime': '2025-12-29T19:35:46.903964177Z', 'startUtcOffset': '-18000s', 'endTime': '2025-12-29T19:45:37.498495045Z', 'endUtcOffset': '-18000s', 'activeDuration': '590.594530868s', 'metricsSummary': {'distanceMillimeters': 1609344, 'averagePaceSecondsPerMeter': 0.36697843336780076}, 'splitType': 'DISTANCE'}, {'startTime': '2025-12-29T19:45:37.498495045Z', 'startUtcOffset': '-18000s', 'endTime': '2025-12-29T19:49:12Z', 'endUtcOffset': '-18000s', 'activeDuration': '214.501504955s', 'metricsSummary': {'distanceMillimeters': 542226, 'averagePaceSecondsPerMeter': 0.39560349845084964}, 'splitType': 'DISTANCE'}]",
    "exercise.metricsSummary.mobilityMetrics.avgCadenceStepsPerMinute": 144.0,
    "exercise.metricsSummary.mobilityMetrics.avgStrideLengthMillimeters": 1143.0,
    "exercise.metricsSummary.mobilityMetrics.avgVerticalOscillationMillimeters": 96.0,
    "exercise.metricsSummary.mobilityMetrics.avgVerticalRatio": 8.52843952178955,
    "exercise.metricsSummary.mobilityMetrics.avgGroundContactTimeDuration": "0.301s",
    "exercise.exerciseMetadata.hasGps": True,
    "exercise.exerciseEvents": "[{'eventTime': '2025-12-29T19:16:31Z', 'eventUtcOffset': '-18000s', 'exerciseEventType': 'START'}, {'eventTime': '2025-12-29T19:49:12Z', 'eventUtcOffset': '-18000s', 'exerciseEventType': 'PAUSE'}, {'eventTime': '2025-12-29T19:49:12Z', 'eventUtcOffset': '-18000s', 'exerciseEventType': 'STOP'}]"
  },
  {
    "name": "users/6365399212480104868/dataTypes/exercise/dataPoints/2517636786014678560",
    "dataSource.recordingMethod": "ACTIVELY_MEASURED",
    "dataSource.device.formFactor": "WATCH",
    "dataSource.device.displayName": "Google Pixel Watch 4 (45mm)",
    "dataSource.platform": "FITBIT",
    "exercise.interval.startTime": "2026-01-07T15:49:32Z",
    "exercise.interval.startUtcOffset": "-18000s",
    "exercise.interval.endTime": "2026-01-07T16:27:32.493Z",
    "exercise.interval.endUtcOffset": "-18000s",
    "exercise.exerciseType": "RUNNING",
    "exercise.metricsSummary.caloriesKcal": 560.0,
    "exercise.metricsSummary.distanceMillimeters": 6889269.0,
    "exercise.metricsSummary.steps": 5797.0,
    "exercise.metricsSummary.averagePaceSecondsPerMeter": 0.3309540445695022,
    "exercise.metricsSummary.averageHeartRateBeatsPerMinute": 162.0,
    "exercise.metricsSummary.elevationGainMillimeters": 48116.0,
    "exercise.metricsSummary.activeZoneMinutes": 74.0,
    "exercise.metricsSummary.heartRateZoneDurations.lightTime": "0s",
    "exercise.metricsSummary.heartRateZoneDurations.moderateTime": "0s",
    "exercise.metricsSummary.heartRateZoneDurations.vigorousTime": "2280s",
    "exercise.metricsSummary.heartRateZoneDurations.peakTime": "0s",
    "exercise.displayName": "Run",
    "exercise.activeDuration": "2280s",
    "exercise.updateTime": "2026-01-07T16:27:35.857644Z",
    "exercise.createTime": "2026-01-07T16:26:01.077271Z",
    "exercise.splits": "[{'startTime': '2026-01-07T15:49:33Z', 'startUtcOffset': '-18000s', 'endTime': '2026-01-07T15:58:24.492750697Z', 'endUtcOffset': '-18000s', 'activeDuration': '531.492750697s', 'metricsSummary': {'distanceMillimeters': 1609344, 'averagePaceSecondsPerMeter': 0.33025428489725734}, 'splitType': 'DISTANCE'}, {'startTime': '2026-01-07T15:58:24.492750697Z', 'startUtcOffset': '-18000s', 'endTime': '2026-01-07T16:07:18.069929944Z', 'endUtcOffset': '-18000s', 'activeDuration': '533.577179247s', 'metricsSummary': {'distanceMillimeters': 1609344, 'averagePaceSecondsPerMeter': 0.3315494921980391}, 'splitType': 'DISTANCE'}, {'startTime': '2026-01-07T16:07:18.069929944Z', 'startUtcOffset': '-18000s', 'endTime': '2026-01-07T16:16:11.758416805Z', 'endUtcOffset': '-18000s', 'activeDuration': '533.688486861s', 'metricsSummary': {'distanceMillimeters': 1609344, 'averagePaceSecondsPerMeter': 0.33161864883499775}, 'splitType': 'DISTANCE'}, {'startTime': '2026-01-07T16:16:11.758416805Z', 'startUtcOffset': '-18000s', 'endTime': '2026-01-07T16:25:05.155986874Z', 'endUtcOffset': '-18000s', 'activeDuration': '533.397570069s', 'metricsSummary': {'distanceMillimeters': 1609344, 'averagePaceSecondsPerMeter': 0.33143788226065584}, 'splitType': 'DISTANCE'}, {'startTime': '2026-01-07T16:25:05.155986874Z', 'startUtcOffset': '-18000s', 'endTime': '2026-01-07T16:27:30Z', 'endUtcOffset': '-18000s', 'activeDuration': '144.844013126s', 'metricsSummary': {'distanceMillimeters': 451893, 'averagePaceSecondsPerMeter': 0.32052723389020436}, 'splitType': 'DISTANCE'}]",
    "exercise.metricsSummary.mobilityMetrics.avgCadenceStepsPerMinute": 153.0,
    "exercise.metricsSummary.mobilityMetrics.avgStrideLengthMillimeters": 1188.0,
    "exercise.metricsSummary.mobilityMetrics.avgVerticalOscillationMillimeters": 92.0,
    "exercise.metricsSummary.mobilityMetrics.avgVerticalRatio": 7.8286919593811035,
    "exercise.metricsSummary.mobilityMetrics.avgGroundContactTimeDuration": "0.296s",
    "exercise.exerciseMetadata.hasGps": True,
    "exercise.exerciseEvents": "[{'eventTime': '2026-01-07T15:49:32Z', 'eventUtcOffset': '-18000s', 'exerciseEventType': 'START'}, {'eventTime': '2026-01-07T16:27:32Z', 'eventUtcOffset': '-18000s', 'exerciseEventType': 'STOP'}, {'eventTime': '2026-01-07T16:27:32Z', 'eventUtcOffset': '-18000s', 'exerciseEventType': 'PAUSE'}]"
  },
  {
    "name": "users/6365399212480104868/dataTypes/exercise/dataPoints/5096069050685456512",
    "dataSource.recordingMethod": "ACTIVELY_MEASURED",
    "dataSource.device.formFactor": "WATCH",
    "dataSource.device.displayName": "Google Pixel Watch 4 (45mm)",
    "dataSource.platform": "FITBIT",
    "exercise.interval.startTime": "2026-01-13T20:02:13Z",
    "exercise.interval.startUtcOffset": "-18000s",
    "exercise.interval.endTime": "2026-01-13T20:37:37.387Z",
    "exercise.interval.endUtcOffset": "-18000s",
    "exercise.exerciseType": "RUNNING",
    "exercise.metricsSummary.caloriesKcal": 519.0,
    "exercise.metricsSummary.distanceMillimeters": 6475283.0,
    "exercise.metricsSummary.steps": 5469.0,
    "exercise.metricsSummary.averagePaceSecondsPerMeter": 0.3280145292211997,
    "exercise.metricsSummary.averageHeartRateBeatsPerMinute": 170.0,
    "exercise.metricsSummary.elevationGainMillimeters": 43232.0,
    "exercise.metricsSummary.activeZoneMinutes": 69.0,
    "exercise.metricsSummary.heartRateZoneDurations.lightTime": "0s",
    "exercise.metricsSummary.heartRateZoneDurations.moderateTime": "0s",
    "exercise.metricsSummary.heartRateZoneDurations.vigorousTime": "1260s",
    "exercise.metricsSummary.heartRateZoneDurations.peakTime": "840s",
    "exercise.displayName": "Run",
    "exercise.activeDuration": "2124s",
    "exercise.updateTime": "2026-01-13T20:37:41.229959Z",
    "exercise.createTime": "2026-01-13T20:36:00.672901Z",
    "exercise.splits": "[{'startTime': '2026-01-13T20:02:14Z', 'startUtcOffset': '-18000s', 'endTime': '2026-01-13T20:11:02.164344933Z', 'endUtcOffset': '-18000s', 'activeDuration': '528.164344933s', 'metricsSummary': {'distanceMillimeters': 1609344, 'averagePaceSecondsPerMeter': 0.32818610531557004}, 'splitType': 'DISTANCE'}, {'startTime': '2026-01-13T20:11:02.164344933Z', 'startUtcOffset': '-18000s', 'endTime': '2026-01-13T20:19:50.057393433Z', 'endUtcOffset': '-18000s', 'activeDuration': '527.893048500s', 'metricsSummary': {'distanceMillimeters': 1609344, 'averagePaceSecondsPerMeter': 0.32801753424756573}, 'splitType': 'DISTANCE'}, {'startTime': '2026-01-13T20:19:50.057393433Z', 'startUtcOffset': '-18000s', 'endTime': '2026-01-13T20:28:44.821102923Z', 'endUtcOffset': '-18000s', 'activeDuration': '534.763709490s', 'metricsSummary': {'distanceMillimeters': 1609344, 'averagePaceSecondsPerMeter': 0.33228676579899516}, 'splitType': 'DISTANCE'}, {'startTime': '2026-01-13T20:28:44.821102923Z', 'startUtcOffset': '-18000s', 'endTime': '2026-01-13T20:37:34.908077561Z', 'endUtcOffset': '-18000s', 'activeDuration': '530.086974638s', 'metricsSummary': {'distanceMillimeters': 1609344, 'averagePaceSecondsPerMeter': 0.32938077098485514}, 'splitType': 'DISTANCE'}, {'startTime': '2026-01-13T20:37:34.908077561Z', 'startUtcOffset': '-18000s', 'endTime': '2026-01-13T20:37:37Z', 'endUtcOffset': '-18000s', 'activeDuration': '2.091922439s', 'metricsSummary': {'distanceMillimeters': 37907, 'averagePaceSecondsPerMeter': 0.05518512119107292}, 'splitType': 'DISTANCE'}]",
    "exercise.metricsSummary.mobilityMetrics.avgCadenceStepsPerMinute": 154.0,
    "exercise.metricsSummary.mobilityMetrics.avgStrideLengthMillimeters": 1184.0,
    "exercise.metricsSummary.mobilityMetrics.avgVerticalOscillationMillimeters": 92.0,
    "exercise.metricsSummary.mobilityMetrics.avgVerticalRatio": 7.8286919593811035,
    "exercise.metricsSummary.mobilityMetrics.avgGroundContactTimeDuration": "0.295s",
    "exercise.exerciseMetadata.hasGps": True,
    "exercise.exerciseEvents": "[{'eventTime': '2026-01-13T20:02:13Z', 'eventUtcOffset': '-18000s', 'exerciseEventType': 'START'}, {'eventTime': '2026-01-13T20:37:37Z', 'eventUtcOffset': '-18000s', 'exerciseEventType': 'PAUSE'}, {'eventTime': '2026-01-13T20:37:37Z', 'eventUtcOffset': '-18000s', 'exerciseEventType': 'STOP'}]"
  },
  {
    "name": "users/6365399212480104868/dataTypes/exercise/dataPoints/2819394409313817720",
    "dataSource.recordingMethod": "ACTIVELY_MEASURED",
    "dataSource.device.formFactor": "WATCH",
    "dataSource.device.displayName": "Google Pixel Watch 4 (45mm)",
    "dataSource.platform": "FITBIT",
    "exercise.interval.startTime": "2026-02-28T19:21:01Z",
    "exercise.interval.startUtcOffset": "-18000s",
    "exercise.interval.endTime": "2026-02-28T20:00:44.015Z",
    "exercise.interval.endUtcOffset": "-18000s",
    "exercise.exerciseType": "RUNNING",
    "exercise.metricsSummary.caloriesKcal": 568.0,
    "exercise.metricsSummary.distanceMillimeters": 6871628.0,
    "exercise.metricsSummary.steps": 6028.0,
    "exercise.metricsSummary.averagePaceSecondsPerMeter": 0.3466427460857892,
    "exercise.metricsSummary.averageHeartRateBeatsPerMinute": 159.0,
    "exercise.metricsSummary.elevationGainMillimeters": 50346.0,
    "exercise.metricsSummary.activeZoneMinutes": 77.0,
    "exercise.metricsSummary.heartRateZoneDurations.lightTime": "0s",
    "exercise.metricsSummary.heartRateZoneDurations.moderateTime": "0s",
    "exercise.metricsSummary.heartRateZoneDurations.vigorousTime": "1560s",
    "exercise.metricsSummary.heartRateZoneDurations.peakTime": "780s",
    "exercise.displayName": "Run",
    "exercise.activeDuration": "2382s",
    "exercise.updateTime": "2026-02-28T20:00:47.288559Z",
    "exercise.createTime": "2026-02-28T19:59:10.316667Z",
    "exercise.splits": "[{'startTime': '2026-02-28T19:21:02Z', 'startUtcOffset': '-18000s', 'endTime': '2026-02-28T19:29:44.562249175Z', 'endUtcOffset': '-18000s', 'activeDuration': '522.562249175s', 'metricsSummary': {'distanceMillimeters': 1609344, 'averagePaceSecondsPerMeter': 0.3247051277880926}, 'splitType': 'DISTANCE'}, {'startTime': '2026-02-28T19:29:44.562249175Z', 'startUtcOffset': '-18000s', 'endTime': '2026-02-28T19:39:00.681037332Z', 'endUtcOffset': '-18000s', 'activeDuration': '556.118788157s', 'metricsSummary': {'distanceMillimeters': 1609344, 'averagePaceSecondsPerMeter': 0.34555619442269647}, 'splitType': 'DISTANCE'}, {'startTime': '2026-02-28T19:39:00.681037332Z', 'startUtcOffset': '-18000s', 'endTime': '2026-02-28T19:48:24.618947293Z', 'endUtcOffset': '-18000s', 'activeDuration': '563.937909961s', 'metricsSummary': {'distanceMillimeters': 1609344, 'averagePaceSecondsPerMeter': 0.3504147714602968}, 'splitType': 'DISTANCE'}, {'startTime': '2026-02-28T19:48:24.618947293Z', 'startUtcOffset': '-18000s', 'endTime': '2026-02-28T19:57:41.832280168Z', 'endUtcOffset': '-18000s', 'activeDuration': '557.213332875s', 'metricsSummary': {'distanceMillimeters': 1609344, 'averagePaceSecondsPerMeter': 0.3462363129790772}, 'splitType': 'DISTANCE'}, {'startTime': '2026-02-28T19:57:41.832280168Z', 'startUtcOffset': '-18000s', 'endTime': '2026-02-28T20:00:42Z', 'endUtcOffset': '-18000s', 'activeDuration': '180.167719832s', 'metricsSummary': {'distanceMillimeters': 434252, 'averagePaceSecondsPerMeter': 0.4148920899201385}, 'splitType': 'DISTANCE'}]",
    "exercise.metricsSummary.mobilityMetrics.avgCadenceStepsPerMinute": 154.0,
    "exercise.metricsSummary.mobilityMetrics.avgStrideLengthMillimeters": 1140.0,
    "exercise.metricsSummary.mobilityMetrics.avgVerticalOscillationMillimeters": 92.0,
    "exercise.metricsSummary.mobilityMetrics.avgVerticalRatio": 8.140137672424316,
    "exercise.metricsSummary.mobilityMetrics.avgGroundContactTimeDuration": "0.292s",
    "exercise.exerciseMetadata.hasGps": True,
    "exercise.exerciseEvents": "[{'eventTime': '2026-02-28T19:21:01Z', 'eventUtcOffset': '-18000s', 'exerciseEventType': 'START'}, {'eventTime': '2026-02-28T20:00:43Z', 'eventUtcOffset': '-18000s', 'exerciseEventType': 'STOP'}, {'eventTime': '2026-02-28T20:00:43Z', 'eventUtcOffset': '-18000s', 'exerciseEventType': 'PAUSE'}]"
  },
  {
    "name": "users/6365399212480104868/dataTypes/exercise/dataPoints/6427585472882602304",
    "dataSource.recordingMethod": "ACTIVELY_MEASURED",
    "dataSource.device.formFactor": "WATCH",
    "dataSource.device.displayName": "Google Pixel Watch 4 (45mm)",
    "dataSource.platform": "FITBIT",
    "exercise.interval.startTime": "2026-03-08T17:40:07Z",
    "exercise.interval.startUtcOffset": "-14400s",
    "exercise.interval.endTime": "2026-03-08T18:15:59.608Z",
    "exercise.interval.endUtcOffset": "-14400s",
    "exercise.exerciseType": "RUNNING",
    "exercise.metricsSummary.caloriesKcal": 563.0,
    "exercise.metricsSummary.distanceMillimeters": 6456086.0,
    "exercise.metricsSummary.steps": 5505.0,
    "exercise.metricsSummary.averagePaceSecondsPerMeter": 0.333174000470254,
    "exercise.metricsSummary.averageHeartRateBeatsPerMinute": 174.0,
    "exercise.metricsSummary.elevationGainMillimeters": 43778.0,
    "exercise.metricsSummary.activeZoneMinutes": 69.0,
    "exercise.metricsSummary.heartRateZoneDurations.lightTime": "0s",
    "exercise.metricsSummary.heartRateZoneDurations.moderateTime": "0s",
    "exercise.metricsSummary.heartRateZoneDurations.vigorousTime": "300s",
    "exercise.metricsSummary.heartRateZoneDurations.peakTime": "1800s",
    "exercise.displayName": "Run",
    "exercise.activeDuration": "2151s",
    "exercise.updateTime": "2026-03-08T18:16:04.999391Z",
    "exercise.createTime": "2026-03-08T17:45:48.473949Z",
    "exercise.splits": "[{'startTime': '2026-03-08T17:42:13Z', 'startUtcOffset': '-14400s', 'endTime': '2026-03-08T17:51:03.713820312Z', 'endUtcOffset': '-14400s', 'activeDuration': '530.713820312s', 'metricsSummary': {'distanceMillimeters': 1609344, 'averagePaceSecondsPerMeter': 0.3297702792640977}, 'splitType': 'DISTANCE'}, {'startTime': '2026-03-08T17:51:03.713820312Z', 'startUtcOffset': '-14400s', 'endTime': '2026-03-08T17:59:58.941724664Z', 'endUtcOffset': '-14400s', 'activeDuration': '535.227904352s', 'metricsSummary': {'distanceMillimeters': 1609344, 'averagePaceSecondsPerMeter': 0.332575201045892}, 'splitType': 'DISTANCE'}, {'startTime': '2026-03-08T17:59:58.941724664Z', 'startUtcOffset': '-14400s', 'endTime': '2026-03-08T18:09:07.169236054Z', 'endUtcOffset': '-14400s', 'activeDuration': '548.227511390s', 'metricsSummary': {'distanceMillimeters': 1609344, 'averagePaceSecondsPerMeter': 0.3406527823697109}, 'splitType': 'DISTANCE'}, {'startTime': '2026-03-08T18:09:07.169236054Z', 'startUtcOffset': '-14400s', 'endTime': '2026-03-08T18:15:53.278631056Z', 'endUtcOffset': '-14400s', 'activeDuration': '406.109395002s', 'metricsSummary': {'distanceMillimeters': 1609344, 'averagePaceSecondsPerMeter': 0.2523446789511751}, 'splitType': 'DISTANCE'}, {'startTime': '2026-03-08T18:15:53.278631056Z', 'startUtcOffset': '-14400s', 'endTime': '2026-03-08T18:15:58Z', 'endUtcOffset': '-14400s', 'activeDuration': '4.721368943s', 'metricsSummary': {'distanceMillimeters': 18710, 'averagePaceSecondsPerMeter': 0.25234467894174234}, 'splitType': 'DISTANCE'}]",
    "exercise.metricsSummary.mobilityMetrics.avgCadenceStepsPerMinute": 153.0,
    "exercise.metricsSummary.mobilityMetrics.avgStrideLengthMillimeters": 1183.0,
    "exercise.metricsSummary.mobilityMetrics.avgVerticalOscillationMillimeters": 92.0,
    "exercise.metricsSummary.mobilityMetrics.avgVerticalRatio": 7.86740255355835,
    "exercise.metricsSummary.mobilityMetrics.avgGroundContactTimeDuration": "0.295s",
    "exercise.exerciseMetadata.hasGps": True,
    "exercise.exerciseEvents": "[{'eventTime': '2026-03-08T17:40:07Z', 'eventUtcOffset': '-14400s', 'exerciseEventType': 'START'}, {'eventTime': '2026-03-08T18:15:59Z', 'eventUtcOffset': '-14400s', 'exerciseEventType': 'PAUSE'}, {'eventTime': '2026-03-08T18:15:59Z', 'eventUtcOffset': '-14400s', 'exerciseEventType': 'STOP'}]"
  }
]


def auto_heal_exercises(base_dir):
    csv_path = os.path.join(base_dir, "my_exercises.csv")
    df_embedded = pd.DataFrame(EMBEDDED_HISTORICAL_RUNS)

    if not os.path.exists(csv_path):
        try:
            df_embedded.to_csv(csv_path, index=False)
        except Exception as e:
            print(f"Auto-heal write error: {e}")
        return df_embedded

    try:
        df_current = pd.read_csv(csv_path)
    except Exception as e:
        print(f"Auto-heal read error: {e}")
        return df_embedded

    try:
        if "name" in df_current.columns:
            current_ids = set(df_current["name"].astype(str).apply(lambda x: x.split("/")[-1]))
            df_embedded["_run_id"] = df_embedded["name"].astype(str).apply(lambda x: x.split("/")[-1])
            missing_df = df_embedded[~df_embedded["_run_id"].isin(current_ids)].copy()

            if not missing_df.empty:
                print(f"Auto-heal: Merging {len(missing_df)} missing historical entries...")
                combined = pd.concat([df_current, missing_df.drop(columns=["_run_id"])], ignore_index=True)
                if "exercise.interval.startTime" in combined.columns:
                    combined["_sort_time"] = pd.to_datetime(combined["exercise.interval.startTime"], errors="coerce")
                    combined = combined.sort_values("_sort_time").drop(columns=["_sort_time"])
                
                try:
                    combined.to_csv(csv_path, index=False)
                except Exception as w_err:
                    print(f"Auto-heal disk write warning: {w_err}")
                
                return combined
        return df_current
    except Exception as e:
        print(f"Auto-heal warning: {e}")
        return df_current
