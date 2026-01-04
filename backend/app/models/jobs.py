"""
Job status models
"""
from pydantic import BaseModel
from typing import Optional
from enum import Enum
from datetime import datetime


class JobStatus(str, Enum):
    """Job status enumeration"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobInfo(BaseModel):
    """Job information model"""
    process_id: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    progress: Optional[float] = None  # 0.0 to 1.0
    games_generated: Optional[int] = None  # Number of games generated so far
    total_games: Optional[int] = None  # Total number of games to generate
    error: Optional[str] = None
    download_url: Optional[str] = None
    
    class Config:
        # Ensure enum values are serialized as strings
        use_enum_values = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

