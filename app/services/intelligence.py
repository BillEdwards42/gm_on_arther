import asyncio
import httpx
import time
import math
import json
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Tuple, Optional, Any
from collections import deque
import numpy as np

from app.core.logging import logger
from app.core.config import get_settings

from app.repository.local_file_repo import LocalFileRepo

# Services
from app.services.ml_inference import MLInferenceService 

# Schemas
from app.schemas.weather import WeatherResponse
from app.schemas.generation import TaipowerResponse, Generation
from app.schemas.forecast import PredictionArtifact, CarbonLevel, TimeStep, OptimizationWindow
from app.schemas.ml_cache import MlCache, RegionDataRow

settings = get_settings()

# --- CONSTANTS ---
TAIPOWER_URL = "https://www.taipower.com.tw/d006/loadGraph/loadGraph/data/genary.json"
CWA_URL = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0003-001"
CACHE_FILENAME = "ml_cache_v2.json"
CACHE_WINDOW_SIZE = 720 # 5 days * 24 hours * 6 (10-min intervals)

# Regions
REGIONS = ["North", "Central", "South", "East", "Other"]

# Physics Constants
CARBON_FACTORS = {
    'Nuclear': 0.0, 'Coal': 0.912, 'Co-Gen': 1.111, 'IPP-Coal': 0.919,
    'LNG': 0.389, 'IPP-LNG': 0.378, 'Oil': 0.818, 'Diesel': 0.811,
    'Hydro': 0.0, 'Wind': 0.0, 'Solar': 0.0, 'Other_Renewable': 1.002, 'Storage': 0.0
}
LINE_LOSS_RATE = 0.0293

STATIONS_BY_REGION = {
    "North": ["基隆", "淡水", "新北", "新竹", "臺北", "新屋", "桃園農改", "文山茶改", "新埔工作站"],
    "Central": ["臺中", "梧棲", "後龍", "古坑", "彰師大", "麥寮", "田中", "日月潭", "苗栗農改"],
    "South": ["嘉義", "臺南", "高雄", "恆春", "永康", "臺南農改", "旗南農改", "高雄農改", "屏東"],
    "East": ["宜蘭", "花蓮", "成功", "臺東", "大武"],
    "Other": []
}

REGION_KEYWORDS = {
    'North': ['林口', '大潭', '新桃', '通霄', '協和', '石門', '翡翠', '桂山', '觀音', '龍潭', '北部'],
    'Central': ['台中', '大甲溪', '明潭', '彰工', '中港', '竹南', '苗栗', '雲林', '麥寮', '中部', '彰'],
    'South': ['興達', '大林', '南部', '核三', '曾文', '嘉義', '台南', '高雄', '永安', '屏東'],
    'East': ['和平', '花蓮', '蘭陽', '卑南', '立霧', '東部'], 
    'Other': ['汽電共生', '其他台電自有', '其他購電太陽能', '其他購電風力', '購買地熱', '台電自有地熱', '生質能']
}

# --- HELPERS ---

class RegionMapper:
    """Maps plant names to regions using CSV or Heuristics."""
    def __init__(self):
        self.csv_map = {}
        self._load_csv_map()

    def _load_csv_map(self):
        try:
            # Assumes Docker structure /app/app/data
            # Using relative path for safety
            from pathlib import Path
            path = Path(__file__).parent.parent / "data" / "plant_to_region_map.csv"
            if path.exists():
                import pandas as pd
                df = pd.read_csv(path)
                self.csv_map = dict(zip(df['UNIT_NAME'], df['REGION']))
                logger.info(f"Loaded {len(self.csv_map)} mappings from CSV.")
            else:
                logger.warning("⚠️ plant_to_region_map.csv not found. Relying on Keywords.")
        except Exception as e:
            logger.error(f"Failed to load region map CSV: {e}")

    def get_region(self, unit_name: str) -> str:
        if unit_name in self.csv_map: return self.csv_map[unit_name]
        for region, keywords in REGION_KEYWORDS.items():
            for kw in keywords:
                if kw in unit_name: return region
        return "Other"

region_mapper = RegionMapper()

def _calculate_time_features(dt: datetime) -> dict:
    """Computes Cyclical Time Features"""
    def sin_trans(val, max_val): return math.sin(2 * math.pi * val / max_val)
    def cos_trans(val, max_val): return math.cos(2 * math.pi * val / max_val)
    return {
        "year": float(dt.year),
        "month_sin": sin_trans(dt.month - 1, 12), "month_cos": cos_trans(dt.month - 1, 12),
        "day_sin": sin_trans(dt.day - 1, 31),     "day_cos": cos_trans(dt.day - 1, 31),
        "dayofweek_sin": sin_trans(dt.weekday(), 7), "dayofweek_cos": cos_trans(dt.weekday(), 7),
        "hour_sin": sin_trans(dt.hour, 24),       "hour_cos": cos_trans(dt.hour, 24),
        "minute_sin": sin_trans(dt.minute, 60),   "minute_cos": cos_trans(dt.minute, 60)
    }

# --- CACHE MANAGEMENT FUNCTIONS ---

async def _fetch_current_cache(repo: LocalFileRepo) -> Dict[str, List[RegionDataRow]]:
    """Downloads and deserializes the ML cache from GCS."""
    try:
        # Pydantic v2: Use model_validate_json directly if fetching raw string
        # But BucketRepo usually returns string.
        json_str = await repo.download_json(CACHE_FILENAME)
        cache_obj = MlCache.model_validate_json(json_str)
    
        # Convert to a dict of lists for easier manipulation
        return {
            "North": cache_obj.North,
            "Central": cache_obj.Central,
            "South": cache_obj.South,
            "East": cache_obj.East,
            "Other": cache_obj.Other
        }
    except Exception as e:
        # Use repr(e) to see exception type even if message is empty (e.g. TimeoutError)
        logger.warning(f"Cache not found or corrupt ({repr(e)}). Starting fresh.")
        return {r: [] for r in REGIONS}

async def _save_cache_to_gcs(repo: LocalFileRepo, cache_data: Dict[str, List[RegionDataRow]]):
    """Serializes and uploads the ML cache to GCS."""
    try:
        # Reconstruct the Root Model
        cache_obj = MlCache(
            North=cache_data["North"],
            Central=cache_data["Central"],
            South=cache_data["South"],
            East=cache_data["East"],
            Other=cache_data["Other"],
            previous_generators=[] # Unused in this logic, but required by Schema
        )
        await repo.upload_json(CACHE_FILENAME, cache_obj.model_dump_json(by_alias=True))
    except Exception as e:
        logger.error(f"Failed to save cache: {e}")

def _update_cache_state(
    current_cache: Dict[str, List[RegionDataRow]], 
    new_rows: Dict[str, RegionDataRow]
) -> Dict[str, List[RegionDataRow]]:
    """
    Appends new rows and trims to the fixed window size.
    Enforces 'Last In, First Out' logic to keep the most recent data.
    """
    updated_cache = {}
    for region in REGIONS:
        # Get existing list
        history = current_cache.get(region, [])
        
        # Append new data
        if region in new_rows:
            history.append(new_rows[region])
        
        # Trim to Window Size (Exactly 720 as requested, or slight buffer?)
        # We adhere to "Safe Buffer" logic: keep 720, but slice at usage.
        # Actually, strict maintenance prevents file bloat.
        if len(history) > CACHE_WINDOW_SIZE:
            history = history[-CACHE_WINDOW_SIZE:] # Keep last 720
            
        updated_cache[region] = history
        
    return updated_cache

# --- CORE LOGIC ---
async def fetch_raw_data() -> Tuple[str, dict]:
    """
    Fetches data directly from both sources.
    - Taipower: Direct with realistic browser headers to avoid bot detection.
    - CWA: Direct with API key.

    Returns: (taipower_json_text, weather_json_dict)
    """
    cwa_key = settings.CWA_API_KEY
    timestamp_suffix = int(time.time())

    # Realistic browser headers to avoid bot detection on Taipower
    browser_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.taipower.com.tw/d006/loadGraph/loadGraph/genary.html",
        "X-Requested-With": "XMLHttpRequest",
    }

    timeout_config = httpx.Timeout(30.0, connect=10.0)

    print("📡 Fetching data directly (no proxy)...")

    async with httpx.AsyncClient(timeout=timeout_config, headers=browser_headers) as client:

        task_tp = client.get(TAIPOWER_URL, params={"_": timestamp_suffix})
        task_wt = client.get(CWA_URL, params={"Authorization": cwa_key})

        try:
            tp_res, wt_res = await asyncio.gather(task_tp, task_wt)

            tp_res.raise_for_status()
            wt_res.raise_for_status()

            print("✅ Fetch successful. Passing data to parser...")
            return tp_res.text, wt_res.json()

        except httpx.TimeoutException:
            print("❌ Request timed out during fetch.")
            raise
        except Exception as e:
            print(f"❌ Fetch failed with error: {e}")
            raise e

def _process_generation_data(generators: List[Generation]) -> Dict[str, Dict[str, float]]:
    """

    Aggregates individual plants into Region + Fuel Type buckets.

    Output: { "North": { "Coal": 1200.5, "Solar": 50.0 }, "South": ... }

    """
    regional_data = {r: {} for r in STATIONS_BY_REGION.keys()}
    for gen in generators:
        region = region_mapper.get_region(gen.name)
        if region not in regional_data: region = "Other"
        
        # BUG FIX: Ensure the fuel type is valid, but use the NAME as the key, not the factor.
        if gen.fuel_type not in CARBON_FACTORS: 
            print(f"::warning:: Unknown fuel type: {gen.fuel_type}")
            continue
            
        fuel_name = gen.fuel_type
        if fuel_name not in regional_data[region]: regional_data[region][fuel_name] = 0.0
        regional_data[region][fuel_name] += gen.current_generation_mw
    return regional_data

def _process_weather_data(weather_resp: WeatherResponse) -> Dict[str, Dict[str, float]]:
    """
    Aggregates station data into regional averages. 

    CRITICAL FIX: 

    We rely on the 'Rich Domain Model' pattern. The logic for aggregation 

    is defined in the Schema itself (calculate_regional_averages). 

    We simply pass the configuration map to it.

    """
    try:
        return weather_resp.calculate_regional_averages(STATIONS_BY_REGION)
    except Exception as e:
        logger.error(f"Weather Aggregation Error: {e}")
        return {r: {} for r in STATIONS_BY_REGION.keys()}

def _construct_coupled_rows(
    regional_gen: Dict[str, Dict[str, float]],
    regional_weather: Dict[str, Dict[str, float]],
    now: datetime
) -> Dict[str, RegionDataRow]:
    """
    PASS 1 & PASS 2: Builds features and handles Cross-Regional Coupling.
    """
    # --- [VERIFICATION LOGS] START ---
    print(f"\n🔍 [VERIFICATION] 1. Timestamp (Before Feature Derivation): {now}")
    
    print("🔍 [VERIFICATION] 2. Raw Inputs per Region (Gen & Weather):")
    for r in REGIONS:
        gen = regional_gen.get(r, {})
        weather = regional_weather.get(r, {})
        print(f"   👉 REGION: {r}")
        print(f"      Gen Mix: {gen}")
        print(f"      Weather: {weather}")
    # --- [VERIFICATION LOGS] END ---

    time_feats = _calculate_time_features(now)

    # --- [VERIFICATION LOGS] START ---
    print(f"🔍 [VERIFICATION] 3. Derived Time Features:\n{json.dumps(time_feats, indent=2)}")
    # --- [VERIFICATION LOGS] END ---
    staging_data = {}

    # PASS 1: Base Features
    for region in REGIONS:
        gen_mix = regional_gen.get(region, {})# { "North": { "Coal": 1200.5, "Solar": 50.0 }, "South": ... }
        weather = regional_weather.get(region, {})# {"North": {"AirTempreture": 29.4, ...}, "South"...}
        
        # Flatten Generation: Ensure all 13 fuels exist (default 0.0)
        flat_gen = {k: gen_mix.get(k, 0.0) for k in CARBON_FACTORS.keys()}
        
        if region == "Other":
            # "Other" region logic: Strictly exclude weather features.
            # We only keep Time Features + Generation Mix.
            staging_data[region] = {
                **time_feats,
                **flat_gen
            }
        else:
            staging_data[region] = {
                **time_feats,
                "WindSpeed": weather.get("WindSpeed", 0.0),
                "Precipitation": weather.get("Precipitation", 0.0),
                "SunshineDuration": weather.get("SunshineDuration", 0.0),
                "AirTemperature": weather.get("AirTemperature", 25.0),
                **flat_gen
            }

    # PASS 2: Cross-Regional Coupling (Injecting Neighbors)
    def get_val(r, key): return staging_data.get(r, {}).get(key, 0.0)

    # North Coupling
    staging_data["North"]["South_Coal"] = get_val("South", "Coal")
    staging_data["North"]["South_IPP-LNG"] = get_val("South", "IPP-LNG")
    staging_data["North"]["South_Diesel"] = get_val("South", "Diesel")
    staging_data["North"]["Central_Diesel"] = get_val("Central", "Diesel")
    staging_data["North"]["Central_Hydro"] = get_val("Central", "Hydro")
    staging_data["North"]["Central_Wind"] = get_val("Central", "Wind")

    # Central Coupling
    staging_data["Central"]["South_Diesel"] = get_val("South", "Diesel")
    staging_data["Central"]["North_Diesel"] = get_val("North", "Diesel")
    staging_data["Central"]["North_Hydro"] = get_val("North", "Hydro")
    staging_data["Central"]["Other_Wind"] = get_val("Other", "Wind")
    staging_data["Central"]["North_Wind"] = get_val("North", "Wind")
    staging_data["Central"]["Other_Solar"] = get_val("Other", "Solar")
    staging_data["Central"]["South_Solar"] = get_val("South", "Solar")
    staging_data["Central"]["South_AirTemperature"] = get_val("South", "AirTempreture")
    staging_data["Central"]["East_AirTemperature"] = get_val("East", "AirTempreture")
    staging_data["Central"]["North_AirTemperature"] = get_val("North", "AirTempreture")
    staging_data["Central"]["Other_Storage"] = get_val("Other", "Storage")
    staging_data["Central"]["North_SunshineDuration"] = get_val("North", "SunshineDuration")
    staging_data["Central"]["East_SunshineDuration"] = get_val("East", "SunshineDuration")
    staging_data["Central"]["South_SunshineDuration"] = get_val("South", "SunshineDuration")

    # South Coupling
    staging_data["South"]["North_Coal"] = get_val("North", "Coal")
    staging_data["South"]["North_IPP-LNG"] = get_val("North", "IPP-LNG")
    staging_data["South"]["North_Diesel"] = get_val("North", "Diesel")
    staging_data["South"]["Central_Diesel"] = get_val("Central", "Diesel")
    staging_data["South"]["Other_Solar"] = get_val("Other", "Solar")
    staging_data["South"]["Central_Solar"] = get_val("Central", "Solar")
    staging_data["South"]["East_AirTemperature"] = get_val("East", "AirTempreture")
    staging_data["South"]["Central_AirTemperature"] = get_val("Central", "AirTempreture")
    staging_data["South"]["North_AirTemperature"] = get_val("North", "AirTempreture")

    # East Coupling
    staging_data["East"]["North_Hydro"] = get_val("North", "Hydro")
    staging_data["East"]["Central_Wind"] = get_val("Central", "Wind")
    staging_data["East"]["South_Solar"] = get_val("South", "Solar")

    # --- [VERIFICATION LOGS] START ---
    print("🔍 [VERIFICATION] 4. Final Coupled Features (Excluding Time, Ready for Cache):")
    for r, data in staging_data.items():
        # Filter out time keys to focus on physical columns (Generation, Weather, Coupling)
        physical_cols = {k: v for k, v in data.items() if k not in time_feats}
        # Sort keys for easier reading
        sorted_cols = dict(sorted(physical_cols.items()))
        print(f"   👉 REGION {r}: {json.dumps(sorted_cols, ensure_ascii=False)}")
    # --- [VERIFICATION LOGS] END ---

    # PASS 3: Validation (Pydantic)
    final_rows = {}
    for region in REGIONS:
        # Pydantic v2 'extra="allow"' will capture the coupled columns automatically
        final_rows[region] = RegionDataRow(**staging_data[region])
        
    return final_rows

def _calculate_intensity_from_mix(fuel_mix: Dict[str, float]) -> float:
    total_emission_kg = 0.0
    total_gen_mw = 0.0
    
    # Debug inputs
    logger.info(f"📉 Calculating Input Mix: {fuel_mix}")
    
    for fuel, mw in fuel_mix.items():
        if mw <= 0: continue
        factor = CARBON_FACTORS.get(fuel, 0.0)
        total_emission_kg += mw * factor
        total_gen_mw += mw
        
    if total_gen_mw == 0: 
        print("❌ Total Gen is 0! Defaulting to 500.")
        return 500.0 
        
    avg_gen_intensity = total_emission_kg / total_gen_mw
    consumer_intensity = avg_gen_intensity / (1 - LINE_LOSS_RATE)
    
    final_val = round(consumer_intensity * 1000.0, 2)
    print(f"✅ Intensity Result: {final_val} (Gen: {total_gen_mw:.1f} MW)")
    return final_val

def _determine_dynamic_level(current_val: float, forecast_timeline: List[float]) -> CarbonLevel:
    all_values = [current_val] + forecast_timeline
    p43 = 0.0
    p76 = 0.0
    if len(all_values) > 0:
        p43 = np.percentile(all_values, 43)
        p76 = np.percentile(all_values, 76)
    
    if current_val <= p43: return CarbonLevel.GREEN
    elif current_val <= p76: return CarbonLevel.YELLOW
    else: return CarbonLevel.RED

def _calculate_best_window(start_time: datetime, intensities: List[int], step_minutes: int = 10) -> OptimizationWindow:
    """
    Finds the 2-hour window with the lowest total carbon intensity.
    Constraint: The window must strictly fall within 07:00 - 22:00 (Active Hours).
    If a window starts at 20:00, it ends at 22:00 (Allowed).
    If a window starts at 21:00, it ends at 23:00 (Disallowed).
    """
    WINDOW_SIZE = 12
    FORBIDDEN_START_HOUR = 22 # 10 PM
    FORBIDDEN_END_HOUR = 7    # 7 AM
    
    best_sum = float('inf')
    best_start_idx = -1
    
    # We have 24 points. We can slide 23 times (indices 0 to 22)
    # Range is len() - WINDOW_SIZE + 1
    for i in range(len(intensities) - WINDOW_SIZE + 1):
        
        # 1. Check Time Constraints
        # We check every hour covered by this window
        window_is_valid = True
        for offset in range(WINDOW_SIZE):
            # Calculate the specific hour for this step in the window
            # IMPORTANT: start_time must have timezone info already
            step_dt = start_time + timedelta(minutes=(i + offset) * step_minutes)
            h = step_dt.hour
            
            # Logic: If hour is >= 22 OR < 7, it's inside the "No-Go Zone"
            if h >= FORBIDDEN_START_HOUR or h < FORBIDDEN_END_HOUR:
                window_is_valid = False
                break
        
        if not window_is_valid:
            continue

        # 2. Calculate Intensity Sum (Lower is better)
        current_sum = sum(intensities[i : i + WINDOW_SIZE])
        
        if current_sum < best_sum:
            best_sum = current_sum
            best_start_idx = i
 
    # Fallback: If no valid window found (unlikely in 24h, but good safety),
    # default to right now.
    if best_start_idx == -1:
        logger.warning("⚠️ No valid optimization window found matching constraints. Defaulting to now.")
        best_start_idx = 0

    return OptimizationWindow(
        start_time=start_time + timedelta(minutes=best_start_idx * step_minutes),
        end_time=start_time + timedelta(minutes=(best_start_idx + WINDOW_SIZE) * step_minutes)
    )

# --- ORCHESTRATOR ---

async def run_intelligence_pipeline():
    logger.info("🧠 Intelligence Pipeline Initiated")
    bucket_repo = LocalFileRepo()
    ml_service = MLInferenceService() # Assumed to handle its own loading

    try:
        # 1. Fetch
        print("⏳ Step 1: Fetching data...", flush=True)
        raw_tp, raw_wt = await fetch_raw_data()
        print(f"✅ Step 1 Done. Taipower Size: {len(raw_tp)} chars", flush=True)
        
        # 2. Parse (Validation) - THE FIX IS HERE
        print("⏳ Step 2: Parsing Data...")
        
        # FIX: Validate Weather (JSON) normally
        wt_data = WeatherResponse.model_validate(raw_wt) 

        # FIX: Debugging the Taipower Hang
        # We suspect 'model_validate_json' is wrong for HTML, or the internal parser is slow.
        # We will parse explicitly first to prevent the hang.
        try:
            # Check if raw_tp is actually HTML (starts with <)
            if raw_tp.strip().startswith("<"):
                print("   👉 Detected HTML content. Attempting parse...", flush=True)
                import pandas as pd
                try:
                    # Force lxml flavor to prevent hanging, but handle missing dep
                    dfs = pd.read_html(raw_tp, flavor='lxml') 
                    print(f"   ✅ Parsed {len(dfs)} tables via lxml.", flush=True)
                    # For now, if we get HTML, we still can't magically turn it into the JSON structure 
                    # expected by TaipowerResponse.model_validate_json WITHOUT significant logic.
                    # The previous code seemed to assume 'model_validate_json' could somehow handle it 
                    # OR that the HTML parsing was just a debug check?
                    # ACTUALLY: The original code just printed "Parsed..." and then fell through to line 499 
                    # which calls model_validate_json(raw_tp). 
                    # IF raw_tp is HTML, model_validate_json WILL fail.
                    # We must abort or transform here.
                    raise ValueError("Received HTML (Maintenance Mode?) but parser expects JSON. Aborting validation.")
                    
                except ImportError:
                    print("   ❌ Missing 'lxml' dependency. Cannot parse HTML.", flush=True)
                    raise ValueError("Received HTML and missing lxml parser.")
                except Exception as e:
                    print(f"   ❌ HTML Parsing Failed: {e}", flush=True)
                    raise e
                
            tp_data = TaipowerResponse.model_validate_json(raw_tp)
        except Exception as parse_err:
            print(f"   ❌ Parsing Error Details: {parse_err}", flush=True)
            # If model_validate_json fails because it's HTML, we need to know.
            raise parse_err

        print("✅ Step 2 Done: Validation Complete.")
        
        # --- NEW LOGIC: SOURCE TIMESTAMP ---
        # We use the timestamp provided by Taipower as the single source of truth.
        source_ts_str = tp_data.timestamp # e.g. "2026-01-08 13:50"
        logger.info(f"🕒 Source Timestamp from Taipower: {source_ts_str}")
        
        # Parse to datetime (Asia/Taipei)
        tz_taiwan = timezone(timedelta(hours=8))
        try:
            # Parse strictly YYYY-MM-DD HH:MM
            now = datetime.strptime(source_ts_str, "%Y-%m-%d %H:%M")
            # Force timezone assignment (replace, don't adjust)
            now = now.replace(tzinfo=tz_taiwan)
            logger.info(f"   👉 Pipeline Time set to: {now}")
        except Exception as e:
            logger.error(f"❌ Failed to parse Taipower Timestamp '{source_ts_str}': {e}")
            # Fallback to system time if parsing fails, but warn heavily
            now = datetime.now(tz_taiwan)
            # Round to nearest 10 like before
            now = now.replace(minute=(now.minute // 10) * 10, second=0, microsecond=0)
            logger.warning(f"   ⚠️ Falling back to System Time: {now}")

        # 3. ETL (Raw -> Regional Dicts)
        print("⏳ Step 3: ETL...")
        regional_gen = _process_generation_data(tp_data.valid_generators)
        regional_weather = _process_weather_data(wt_data)
        
        # 4. Feature Construction
        print("⏳ Step 4: Feature Construction...")
        # (Removed old datetime.now logic here)
        
        new_rows_map = _construct_coupled_rows(regional_gen, regional_weather, now)
        
        # --- NEW LOGIC: DETAILED COLUMNS LOGGING ---
        logger.info("\n📊 [PRE-CACHE INSPECTION] Inspecting Data before ML Cache Insert:")
        for region_name, row_data in new_rows_map.items():
            # row_data is a Pydantic Model (RegionDataRow). Dump to dict for logging.
            d = row_data.model_dump()
            
            # Use log level INFO so it definitely shows up
            # We dump the Full Dict (including time features) as requested
            logger.info(f"   📍 Region [{region_name}]: {json.dumps(d, ensure_ascii=False)}")

        
        # 5. Cache Management
        print("⏳ Step 5: Cache Management...")
        current_cache = await _fetch_current_cache(bucket_repo)
        updated_cache = _update_cache_state(current_cache, new_rows_map)
        await _save_cache_to_gcs(bucket_repo, updated_cache)
        
        # 6. ML Inference
        print("⏳ Step 6: Inference...")
        forecasts_mw = ml_service.predict(updated_cache)
        
        # 7. Post-Processing
        print("⏳ Step 7: Post-Processing...")
        total_grid_mw = np.zeros((144, 13))
        
        for region_name, region_forecast in forecasts_mw.items():
            total_grid_mw += region_forecast

        fuel_order = [
            'Nuclear', 'Coal', 'Co-Gen', 'IPP-Coal', 'LNG', 'IPP-LNG',
            'Oil', 'Diesel', 'Hydro', 'Wind', 'Solar', 'Other_Renewable', 'Storage'
        ]

        forecast_timeline_intensities = []
        num_steps = total_grid_mw.shape[0] 
        
        for step_idx in range(num_steps):
            mix_at_step = total_grid_mw[step_idx]
            total_emission = 0.0
            total_gen = 0.0
            
            for i, fuel_name in enumerate(fuel_order):
                mw = mix_at_step[i]
                factor = CARBON_FACTORS.get(fuel_name, 0.0)
                total_emission += mw * factor
                total_gen += mw
            
            if total_gen > 0:
                intensity = (total_emission / total_gen) / (1 - LINE_LOSS_RATE)
                intensity = round(intensity * 1000, 0)
            else:
                intensity = 500
                
            forecast_timeline_intensities.append(intensity)
        
        # Current State
        current_grid_mix = {}
        for r_data in regional_gen.values():
            for fuel, mw in r_data.items():
                current_grid_mix[fuel] = current_grid_mix.get(fuel, 0) + mw
        current_intensity = _calculate_intensity_from_mix(current_grid_mix)
        current_level = _determine_dynamic_level(current_intensity, forecast_timeline_intensities)

        # 8. Artifact Construction
        # 8. Artifact Construction
        forecast_start = now + timedelta(minutes=10)
        
        # Calculate window based on FUTURE data, so start_time must match the first data point
        best_window = _calculate_best_window(forecast_start, forecast_timeline_intensities, step_minutes=10)

        timeline_objects = []
        for i, val in enumerate(forecast_timeline_intensities):
            # Model output[0] is t+1 (10 mins from now), output[1] is t+2, etc.
            step_time = now + timedelta(minutes=(i + 1) * 10)
            
            timeline_objects.append(
                TimeStep(
                    timestamp=step_time,
                    carbon_intensity=int(val),
                    level=_determine_dynamic_level(val, forecast_timeline_intensities)
                )
            )

        artifact = PredictionArtifact(
            last_updated=now,
            status="Complete",
            current_intensity=int(current_intensity),
            current_level=current_level,
            best_usage_window=best_window,
            forecast_start_time=forecast_start,
            forecast_end_time=forecast_start + timedelta(hours=24), # 144 steps * 10 = 24h duration
            timeline=timeline_objects
        )
        
        # 9. Save Artifact
        print("⏳ Step 9: Saving Artifact...")
        await bucket_repo.upload_json("carbon_intensity.json", artifact.model_dump_json())
        
        logger.info(f"✅ Pipeline Success. Intensity: {current_intensity} g/kWh")
        return {"status": "success", "intensity": current_intensity}

    except Exception as e:
        logger.error("❌ Pipeline Failed", exc_info=True)
        print(f"❌ PIPELINE ERROR: {e}") # Ensure we see it in console
        raise e