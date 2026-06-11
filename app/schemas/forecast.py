from pydantic import BaseModel, Field
from datetime import datetime
from typing import List
from enum import Enum

#To ensure the code is readable, no more "Red" or "red"
class CarbonLevel(str, Enum):
    GREEN = "Green"
    YELLOW = "Yellow"
    RED = "Red"

#The atomic unit for the forecast, this will be validating each timesteps' prediction value
class TimeStep(BaseModel):
    timestamp: datetime
    carbon_intensity: int = Field(..., ge=0)
    level: CarbonLevel

#Best usage window
class OptimizationWindow(BaseModel):
    start_time: datetime
    end_time: datetime

#The whole prediction output data schema
class PredictionArtifact(BaseModel):
    last_updated: datetime
    status: str = "Complete"
    errors: List[str] = []

    #Currect section
    current_intensity: int
    current_level: CarbonLevel

    #Forecast section
    forecast_start_time: datetime
    forecast_end_time: datetime
    best_usage_window: OptimizationWindow
    timeline: List[TimeStep]