from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List, Any
from datetime import datetime, timezone
import uuid


# ── Auth ──────────────────────────────────────────────────
class UserRegister(BaseModel):
    email: EmailStr
    username: str
    password: str = Field(min_length=6)
    timezone: str = "UTC"
    consent: bool = True

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    username: str

class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    username: str
    timezone: str
    created_at: datetime
    model_config = {"from_attributes": True}


# ── Logs ──────────────────────────────────────────────────
class LogCreate(BaseModel):
    activity_type: str
    duration: int = Field(gt=0)
    mood: Optional[int] = Field(None, ge=1, le=10)
    focus_score: Optional[int] = Field(None, ge=0, le=100)
    notes: Optional[str] = None
    timestamp: Optional[datetime] = None
    details: dict = Field(default_factory=dict)

    @field_validator("timestamp")
    @classmethod
    def _assume_utc_if_naive(cls, v: Optional[datetime]) -> Optional[datetime]:
        # Log.timestamp is a TIMESTAMPTZ column; a naive value from a client
        # that omitted a UTC offset would otherwise fail on insert.
        if v is not None and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v

    # Core temporal context
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    previous_activity: Optional[str] = None
    next_activity: Optional[str] = None

    # Trigger + outcome telemetry
    trigger: Optional[str] = None
    outcome: Optional[str] = None
    planned: Optional[bool] = None

    # Friction / interruption telemetry (deep work, study, exercise)
    interruptions: Optional[int] = Field(None, ge=0)
    interruption_source: Optional[str] = None
    task_difficulty: Optional[int] = Field(None, ge=1, le=10)

    # Sleep-specific telemetry
    bedtime: Optional[datetime] = None
    wake_time: Optional[datetime] = None
    awakenings: Optional[int] = Field(None, ge=0)

    # Exercise-specific telemetry
    exercise_type: Optional[str] = None
    enjoyment: Optional[int] = Field(None, ge=1, le=10)
    energy_before: Optional[int] = Field(None, ge=1, le=10)
    energy_after: Optional[int] = Field(None, ge=1, le=10)
    social_context: Optional[str] = None

    # Phone-specific telemetry
    phone_purpose: Optional[str] = None
    intended_duration: Optional[int] = Field(None, ge=0)

class LogOut(BaseModel):
    id: int
    user_id: uuid.UUID
    timestamp: datetime
    activity_type: str
    duration: int
    mood: Optional[int]
    focus_score: Optional[int]
    notes: Optional[str]
    details: Optional[dict]
    created_at: datetime
    model_config = {"from_attributes": True}


# ── Loops ─────────────────────────────────────────────────
class FixShort(BaseModel):
    id: int
    suggestion: str
    effort: str
    impact: str
    applied: bool

class LoopOut(BaseModel):
    id: int
    trigger_desc: str
    trigger_time: Optional[str]
    action_desc: str
    outcome_desc: str
    confidence: float
    occurrences: int
    status: str
    causal_estimate: Optional[str]
    detected_at: datetime
    fixes: List[FixShort] = []


# ── Fixes ─────────────────────────────────────────────────
class FixCreate(BaseModel):
    loop_id: int
    suggestion: str
    effort: str = "Medium"
    impact: str = "Medium"

class FixOut(BaseModel):
    id: int
    loop_id: Optional[int]
    suggestion: str
    effort: str
    impact: str
    applied: bool
    created_at: datetime
    model_config = {"from_attributes": True}

class FixApply(BaseModel):
    applied: bool


# ── Breakpoints ───────────────────────────────────────────
class BreakpointCreate(BaseModel):
    name: str
    condition_type: str
    threshold: float
    action_msg: Optional[str] = None

class BreakpointOut(BaseModel):
    id: int
    name: str
    condition_type: str
    threshold: float
    action_msg: Optional[str]
    active: bool
    created_at: datetime
    model_config = {"from_attributes": True}


# ── Debug ─────────────────────────────────────────────────
class DebugQuery(BaseModel):
    query: str
    include_context: bool = True

class DebugResponse(BaseModel):
    query: str
    cause: str
    suggestion: str
    confidence: float
    agent_trace: List[str] = []
    tokens_used: int = 0


# ── Dashboard ─────────────────────────────────────────────
class DashboardStats(BaseModel):
    focus_score: float
    focus_delta: float
    sleep_hours: float
    sleep_delta: float
    productive_hours: float
    productive_delta: float
    focus_timeline: List[dict]
    activity_distribution: List[dict]
    mood_trend: List[dict]
    active_loops: int
    resolved_loops: int
    top_loop: Optional[dict] = None
    alert: Optional[dict] = None
