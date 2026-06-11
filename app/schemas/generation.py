import re
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Optional

# --- 1. The Normalized "Clean" Object ---
class Generation(BaseModel):
    name: str
    fuel_type: str
    capacity_mw: float
    current_generation_mw: float
    status: str

# --- 2. The Raw Row Parser ---
# This handles the ugly list ["<HTML>", "", "Name", "800", ...]
class RawGeneration(BaseModel):
    # We don't define fields 1-by-1 because the input is a list, not a dict.
    # We use a trick to parse the list into this object.

    name: str
    fuel_type: str
    capacity_mw: float
    current_generation_mw: float
    status: str

    @model_validator(mode="before")
    @classmethod
    def parse_raw_list(cls, data: List[str]) -> dict:
        """
        Input: ["<A..><b>燃煤(Coal)</b></A>", "", "Linkou#1", "800.0", "757.3", "94%", "Run", ""]
        Output: Dict mapping to the fields above.
        """
        if not isinstance(data, list) or len(data)<7:
            raise ValueError("Invalid row format.")

        # Helper to strip HTML tags (General purpose fallback)
        def clean_str(s: str) -> str:
            return re.sub('<[^<]+?>', '', s).strip()

        # Helper to handle "-", "N/A", or valid floats
        def parse_float(s: str) -> float:
            s = str(s).replace(',', '').strip()
            if s in ['', '-', 'N/A']:
                return 0.0
            try:
                if '(' in s: s = s.split('(')[0]
                return float(s)
            except ValueError:
                return 0.0

        # 1. Extract Fuel Type using precise Regex (per user script)
        # Usage: match = re.search(r'<b>(.*?)</b>', row[0])
        raw_fuel_html = data[0]
        fuel_type_extracted = ""
        match = re.search(r'<b>(.*?)</b>', raw_fuel_html)
        if match:
             fuel_type_extracted = match.group(1).strip()
        else:
             # Fallback: clean all tags if <b> not found
             fuel_type_extracted = clean_str(raw_fuel_html)

        # 2. Normalize using the comprehensive map
        normalized_fuel = cls._normalize_fuel(fuel_type_extracted)

        # 3. Parse result
        return {
            "fuel_type": normalized_fuel,
            "name": clean_str(data[2]),
            "capacity_mw": parse_float(data[3]),
            "current_generation_mw": parse_float(data[4]),
            "status": clean_str(data[6])
        }

    @staticmethod
    def _normalize_fuel(raw_fuel: str) -> str:
        """
        Maps raw scraped usage types to the keys expected by CARBON_FACTORS.
        Adopts the comprehensive mapping from live_pipeline_integrated.py
        """
        # Comprehensive Mapping from User Script
        mapping = {
            # Chinese Keys
            '核能': 'Nuclear',
            '燃煤': 'Coal',
            '汽電共生': 'Co-Gen',
            '民營電廠-燃煤': 'IPP-Coal',
            '燃氣': 'LNG',
            '民營電廠-燃氣': 'IPP-LNG',
            '燃油': 'Oil',
            '輕油': 'Diesel',
            '水力': 'Hydro',
            '風力': 'Wind',
            '太陽能': 'Solar',
            '其它再生能源': 'Other_Renewable',
            '儲能': 'Storage',
            
            # Mixed/Duplicate Keys (Taipower format variations)
            '太陽能(Solar)': 'Solar', 
            '風力(Wind)': 'Wind', 
            '燃煤(Coal)': 'Coal', 
            '燃氣(LNG)': 'LNG',
            '水力(Hydro)': 'Hydro', 
            '核能(Nuclear)': 'Nuclear', 
            '汽電共生(Co-Gen)': 'Co-Gen',
            '民營電廠-燃煤(IPP-Coal)': 'IPP-Coal', 
            '民營電廠-燃氣(IPP-LNG)': 'IPP-LNG', 
            '燃油(Oil)': 'Oil',
            '輕油(Diesel)': 'Diesel', 
            '其它再生能源(Other Renewable Energy)': 'Other_Renewable',
            '儲能(Energy Storage System)': 'Storage',
            
            # Additional mappings handled previously or extra robust keys
            "Other Renewable Energy": "Other_Renewable",
            "Energy Storage System": "Storage",
            "Biofuel": "Other_Renewable",
            "Pumped Hydro": "Storage",
            "Battery": "Storage",
            "Natural Gas": "LNG",
            "Proton Exchange Membrane": "FuelCell"
        }
        
        # 1. Direct Lookup
        if raw_fuel in mapping:
            return mapping[raw_fuel]

        # 2. If not found, try stripping parens (Fallback logic)
        match = re.search(r'\((.*?)\)', raw_fuel)
        if match:
            english_part = match.group(1).strip()
            return mapping.get(english_part, english_part)
        
        # 3. Last Resort
        print(f"::debug:: Fallback Fuel Normalization: {raw_fuel}")
        return raw_fuel

# --- 3. The Root Response ---
# This matches the JSON structure exactly.
class TaipowerResponse(BaseModel):
    timestamp: str = Field(alias='')
    aaData: List[RawGeneration]
    
    #Logic to filter out "Subtotals" or "Trash" rows
    @property
    def valid_generators(self) -> List[Generation]:
        """Returns only actual power plants, filtering out 'Subtotal' rows"""
        return [
            Generation(
                name=row.name,
                fuel_type=row.fuel_type,
                capacity_mw=row.capacity_mw,
                current_generation_mw=row.current_generation_mw,
                status=row.status
            )
            for row in self.aaData
            if "小計" not in row.name # Filter out subtotals
        ]