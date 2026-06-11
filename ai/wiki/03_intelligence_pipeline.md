# Intelligence Pipeline

The Intelligence Pipeline (`app.services.intelligence`) is the core data processing engine of the application. It aggregates raw data, engineering features, and prepares the cache for ML inference.

## 1. Data Fetching Strategy
- **Taipower Generation Data:** Fetched using a proxy network (Bright Data) to prevent IP blocking from Taipower. A unique timestamp parameter is appended to bypass caching.
- **CWA Weather Data:** Fetched directly using an authorization key.
- **Concurrency:** `httpx.AsyncClient` is used to execute both requests concurrently with strict timeouts to prevent hanging.

## 2. Feature Engineering & Cross-Regional Coupling
The application splits Taiwan into five logical regions: North, Central, South, East, and Other. A CSV file (`plant_to_region_map.csv`) maps individual power plants to these regions.

- **Cyclical Time Features:** Transforms the current timestamp into continuous cyclical variables (sine and cosine of month, day, day_of_week, hour, minute) to help the ML model understand seasonality and time of day.
- **Base Features:** For each region, weather parameters (Wind Speed, Precipitation, Sunshine Duration, Air Temperature) and generation per fuel type are extracted.
- **Cross-Regional Coupling:** Because the power grid is connected, generation and weather in one region affect others. The pipeline injects features from neighboring regions (e.g., Central receives South Solar and North Wind data). 

## 3. Cache Management
Because the ML model requires a 720-step (5 days at 10-minute intervals) look-back window, the system maintains a rolling cache.
- The pipeline downloads `ml_cache_v2.json` from GCS.
- It appends the newly constructed `RegionDataRow` for the current timestamp.
- It trims the history to exactly 720 entries (Last In, First Out).
- The updated cache is serialized and uploaded back to GCS.

## 4. Carbon Intensity Calculation
After the ML model outputs a 144-step forecast for 13 fuel types across all regions, the pipeline calculates the projected carbon intensity.

- **Carbon Factors:** Each fuel type has a fixed carbon emission factor (e.g., Coal: 0.912, LNG: 0.389, Solar/Wind: 0.0).
- **Line Loss Rate:** A fixed transmission loss of 2.93% (`LINE_LOSS_RATE = 0.0293`) is factored into the final consumer intensity.
- **Dynamic Levels:** The pipeline determines if the intensity is GREEN, YELLOW, or RED based on percentiles (43rd and 76th) of the forecast timeline.

## 5. Optimization Window Calculation
The `_calculate_best_window` function slides a 2-hour (12 steps) window across the 24-hour forecast to find the continuous period with the lowest sum of carbon intensity.
- **Constraint:** The window must strictly fall within active hours (07:00 - 22:00) to ensure alerts are sent at actionable times. If a window falls outside this period, it is skipped.
