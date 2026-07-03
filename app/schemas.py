"""
Pydantic schemas for API request/response validation.
No passwords. No JWT. Users are identified by user_id in job submissions.
"""
from pydantic import BaseModel, EmailStr, ConfigDict, Field
from uuid import UUID
from datetime import datetime
from typing import Optional, Any, Dict


# ─── User ────────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    email: str
    name: str

class UserResponse(BaseModel):
    id: UUID
    email: str
    name: str
    is_active: bool
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ─── Job ─────────────────────────────────────────────────────────────────────

class JobCreate(BaseModel):
    user_id: UUID
    payload: Dict[str, Any]

class JobResponse(BaseModel):
    id: UUID
    user_id: UUID
    status: str
    payload: Dict[str, Any]
    retry_count: int
    created_at: datetime
    completed_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


# ─── Metrics ─────────────────────────────────────────────────────────────────

class MetricsResponse(BaseModel):
    total_jobs_submitted: int
    total_jobs_completed: int
    total_jobs_failed: int
    total_jobs_queued: int
    total_jobs_running: int
    total_retries: int
    average_execution_time_ms: float
    success_rate_percent: float
    queue_depth: int
    active_workers: int


# ─── Load Test ───────────────────────────────────────────────────────────────

class LoadTestRequest(BaseModel):
    duration_minutes: int = Field(..., ge=0, le=30, description="Duration must be between 0 and 30 minutes")
