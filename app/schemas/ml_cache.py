from pydantic import BaseModel, Field, ConfigDict
from typing import List, Dict, Deque
from datetime import datetime

#---------- Layer one, individual features ----------

#Time
class TimeFeatures(BaseModel):
    year: float
    # Cyclical encoding ensures 23:00 is 'close' to 00:00
    month_sin: float
    month_cos: float
    day_sin: float
    day_cos: float
    dayofweek_sin: float
    dayofweek_cos: float
    hour_sin: float
    hour_cos: float
    minute_sin: float
    minute_cos: float

#Weather
from typing import Optional
class WeatherFeatures(BaseModel):
    WindSpeed: Optional[float] = None
    Precipitation: Optional[float] = None
    SunshineDuration: Optional[float] = None
    AirTemperature: Optional[float] = None

#Generation
class GenerationFeatures(BaseModel):
    Solar: float
    Wind: float
    Coal: float
    LNG: float
    Hydro: float
    Nuclear: float
    Co_Gen: float = Field(alias="Co-Gen")     # Pydantic handles the hyphen mapping
    IPP_Coal: float = Field(alias="IPP-Coal")
    IPP_LNG: float = Field(alias="IPP-LNG")
    Oil: float
    Diesel: float
    Other_Renewable: float
    Storage: float

#---------- Layer two, regional data ----------
class RegionDataRow(TimeFeatures, WeatherFeatures, GenerationFeatures):
    """
    Represents a SINGLE timestep (one dictionary inside the Deque).
    We use inheritance here because a row contains ALL these fields flatly.
    """
    # Cross-regional features
    # Using extra='allow' lets us handle the specific cross-region columns 
    # (like South_Coal inside North) without defining 5 different classes.
    model_config = ConfigDict(extra="allow", populate_by_name=True)


#---------- Layer three, the root schema(The .pkl structure) ----------
class MlCache(BaseModel):
    """
    The master schema representing the whole pickle file structure.
    """
    # The 'Deque' in Python is just a list in JSON/Pydantic validation terms
    North: List[RegionDataRow]
    Central: List[RegionDataRow]
    South: List[RegionDataRow]
    East: List[RegionDataRow]
    Other: List[RegionDataRow]
    
    previous_generators: List[str]