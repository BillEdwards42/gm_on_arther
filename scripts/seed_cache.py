import sys
import os
import asyncio
import pandas as pd
from datetime import datetime
from typing import Dict, List

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.repository.local_file_repo import LocalFileRepo
from app.schemas.ml_cache import MlCache, RegionDataRow
from app.services.intelligence import _construct_coupled_rows
from dotenv import load_dotenv

load_dotenv()

DATA_DIR = "data_backfill"
REGIONS = ["North", "Central", "South", "East", "Other"]
REQUIRED_ROWS = 720

# 1. Exact list of fuels Pydantic expects (via Aliases)
ALL_FUELS = [
    'Nuclear', 'Coal', 'Co-Gen', 'IPP-Coal', 'LNG', 'IPP-LNG',
    'Oil', 'Diesel', 'Hydro', 'Wind', 'Solar', 'Other_Renewable', 'Storage'
]

# 2. Exact list of weather features Pydantic expects
ALL_WEATHER = [
    'AirTemperature',
    'WindSpeed',
    'SunshineDuration',
    'Precipitation'
]

# Map CSV headers (Keys) to Schema keys (Values)
CSV_TO_SCHEMA_MAP = {
    'AirTemperature': 'AirTemperature',
    'WindSpeed': 'WindSpeed',
    'SunshineDuration': 'SunshineDuration',
    'Precipitation': 'Precipitation'
}

async def seed_cache():
    print("🌱 Starting Cache Seeding Process...")

    # --- STEP 1: LOAD & INDEX ---
    dfs = {}
    for region in REGIONS:
        path = os.path.join(DATA_DIR, f"{region}.csv")
        if not os.path.exists(path):
            print(f"❌ Missing file: {path}")
            return

        df = pd.read_csv(path)
        df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        df = df.sort_values('Timestamp')

        # Shift Weather Logic
        if region != "Other":
            weather_cols_in_csv = [c for c in CSV_TO_SCHEMA_MAP.keys() if c in df.columns]
            if weather_cols_in_csv:
                df[weather_cols_in_csv] = df[weather_cols_in_csv].shift(1).fillna(0.0)
                print(f"   ↘️ Lagged weather for {region}")

        df.set_index('Timestamp', inplace=True)
        dfs[region] = df

    print("✅ Data Loaded. Aligning...")

    # --- STEP 2: ALIGN & SLICE ---
    common_indices = None
    for r in REGIONS:
        if r not in dfs: continue
        if common_indices is None:
            common_indices = dfs[r].index
        else:
            common_indices = common_indices.intersection(dfs[r].index)

    if common_indices is None or len(common_indices) == 0:
        print("❌ No common timestamps found across regions!")
        return

    common_indices = common_indices.sort_values()
    if len(common_indices) > REQUIRED_ROWS:
        target_indices = common_indices[-REQUIRED_ROWS:]
    else:
        target_indices = common_indices

    print(f"✅ Aligned Data. Processing {len(target_indices)} time steps...")

    if len(target_indices) >= 2:
        diff = target_indices[-1] - target_indices[-2]
        print(f"   ℹ️ Detected Time Step: {diff}")
        if diff.total_seconds() != 600:
            print(f"   ⚠️ WARNING: Time step is not 10 minutes! It is {diff}.")

    cache_history = {r: [] for r in REGIONS}

    count = 0
    for ts in target_indices:
        step_gen = {}
        step_weather = {}

        for region in REGIONS:
            try:
                r_df = dfs[region]
                r_row = r_df.loc[ts]
            except KeyError:
                print(f"❌ Missing data for {region} at {ts} (Unexpected)")
                continue

            step_gen[region] = {}
            step_weather[region] = {}

            for fuel in ALL_FUELS:
                val = r_row.get(fuel, 0.0)
                step_gen[region][fuel] = float(val)

            for w_feat in ALL_WEATHER:
                step_weather[region][w_feat] = 0.0

            if region != "Other":
                for csv_col, schema_key in CSV_TO_SCHEMA_MAP.items():
                    if csv_col in r_row:
                        step_weather[region][schema_key] = float(r_row[csv_col])

        ts_py = ts.to_pydatetime()
        try:
            coupled_row_map = _construct_coupled_rows(step_gen, step_weather, ts_py)
            for region, data_row in coupled_row_map.items():
                cache_history[region].append(data_row)
        except Exception as e:
            print(f"❌ Error at {ts}: {e}")

        count += 1

    # --- STEP 4: SAVE TO LOCAL STORAGE ---
    print(f"✅ Generated {count} rows per region.")
    ml_cache = MlCache(
        North=cache_history["North"],
        Central=cache_history["Central"],
        South=cache_history["South"],
        East=cache_history["East"],
        Other=cache_history["Other"],
        previous_generators=[]
    )

    repo = LocalFileRepo()
    print("🚀 Saving to local storage...")

    # FIX: Add by_alias=True to force "Co-Gen" (Hyphens) instead of "Co_Gen"
    await repo.upload_json("ml_cache_v2.json", ml_cache.model_dump_json(by_alias=True))
    print("🎉 Done! Run your pipeline now.")

if __name__ == "__main__":
    asyncio.run(seed_cache())
