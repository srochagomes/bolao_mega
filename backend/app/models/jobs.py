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
    error: Optional[str] = None
    download_url: Optional[str] = None

