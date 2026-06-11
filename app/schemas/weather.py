from pydantic import BaseModel, Field, model_validator, field_validator
from typing import List, Optional, Dict

# --- 1. The Leaf Nodes (Deepest Data) ---
# class StationObsTime(BaseModel):
#     DateTime: str
class NowWeather(BaseModel):
    precipitation: str

# --- 2. The Core Logic (Cleaning the Data) ---
class WeatherElement(BaseModel):
    """
    Handles the dirty work:
    1. Extracting nested fields.
    2. converting strings to floats.
    3. Turning '-99' into None.
    """
    AirTemperature: Optional[float] = None
    WindSpeed: Optional[float] = None
    SunshineDuration: Optional[float] = None
    Precipitation: Optional[float] = None

    # We use 'mode="before"' to intercept the dictionary before Pydantic validates it.
    @model_validator(mode='before')
    @classmethod
    def flatten_and_clean(cls, data: dict) -> dict:
        # 1. Flatten nested Precipitation (It's inside "Now" in the JSON)
        # The raw JSON has: "Now": { "Precipitation": "25.5" }
        precip_val = data.get("Now", {}).get("Precipitation", "-99")
        
        # 2. Extract direct fields
        raw_map = {
            "AirTemperature": data.get("AirTemperature", "-99"),
            "WindSpeed": data.get("WindSpeed", "-99"),
            "SunshineDuration": data.get("SunshineDuration", "-99"),
            "Precipitation": precip_val
        }

        cleaned_data = {}
        
        # 3. Clean "Poison Values" (-99)
        for key, val in raw_map.items():
            try:
                f_val = float(val)
                # Taipower/CWA often uses -99, -99.0, or extremely negative numbers for errors
                if f_val < -90: 
                    cleaned_data[key] = None
                else:
                    cleaned_data[key] = f_val
            except (ValueError, TypeError):
                cleaned_data[key] = None
                
        return cleaned_data

# --- 3. The Station Wrapper ---
class Station(BaseModel):
    StationName: str
    WeatherElement: WeatherElement

# --- 4. The Root & Aggregation Logic ---
class WeatherRecords(BaseModel):
    Station: List[Station]

class WeatherResponse(BaseModel):
    success: str
    records: WeatherRecords

    def calculate_regional_averages(self, region_mapping: Dict[str, List[str]]) -> Dict[str, Dict[str, float]]:
        """
        Input: A dictionary mapping Region Name -> List of County Names
        e.g., { "North": ["臺北市", "新北市", "基隆市", "桃園市", "新竹市", "新竹縣", "宜蘭縣"] }
        
        Output: { "North": { "AirTemperature": 22.5, ... } }
        """
        results = {}
        
        for region, station_name_list in region_mapping.items():
            # 1. Filter valid stations for this region
            target_stations = [
                s.WeatherElement for s in self.records.Station 
                if s.StationName in station_name_list
            ]
            
            if not target_stations:
                continue

            # 2. Calculate averages for each metric (ignoring None)
            metrics = ["AirTemperature", "WindSpeed", "SunshineDuration", "Precipitation"]
            region_data = {}
            
            for metric in metrics:
                valid_values = [
                    getattr(s, metric) for s in target_stations 
                    if getattr(s, metric) is not None
                ]
                
                if valid_values:
                    avg = sum(valid_values) / len(valid_values)
                    region_data[metric] = round(avg, 2)
                else:
                    region_data[metric] = 0.0 # Fallback if all sensors are broken
            
            results[region] = region_data
            
        return results