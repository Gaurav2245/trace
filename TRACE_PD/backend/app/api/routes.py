from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
from typing import List

from app.db.session import get_db
from app.models.models import User, Log, Loop, Fix, Breakpoint, ChatMessage
from app.schemas.schemas import (
    UserRegister, TokenResponse, UserOut,
    LogCreate, LogOut,
    LoopOut, FixShort,
    FixCreate, FixOut, FixApply,
    BreakpointCreate, BreakpointOut,
    DebugQuery, DebugResponse,
    DashboardStats,
)
from app.core.auth import hash_password, verify_password, create_token, get_current_user_id
from app.core.websocket_manager import ws_manager
from app.agents.pipeline import run_debug_pipeline
from app.ml.engine import (
    compute_focus_score, build_focus_timeline,
    build_activity_distribution, build_mood_trend,
    detect_anomalous_loops,
)
from loguru import logger

router = APIRouter()

ACTIVITY_SIGNAL_SCHEMA = {
    "deep_work": {
        "categories": ["focus_activity", "high_cognitive_load"],
        "fields": ["duration", "focus_score", "interruptions", "interruption_source", "task_difficulty", "trigger", "outcome"],
    },
    "sleep": {
        "categories": ["recovery_activity"],
        "fields": ["duration", "bedtime", "wake_time", "awakenings", "mood", "outcome"],
    },
    "exercise": {
        "categories": ["activation_activity", "recovery_activity"],
        "fields": ["duration", "exercise_type", "enjoyment", "energy_before", "energy_after", "social_context", "outcome"],
    },
    "phone": {
        "categories": ["stimulation_activity", "distraction_activity"],
        "fields": ["duration", "intended_duration", "phone_purpose", "trigger", "outcome", "mood"],
    },
    "reading": {
        "categories": ["focus_activity", "low_stimulation_activity"],
        "fields": ["duration", "focus_score", "task_difficulty", "trigger", "outcome"],
    },
    "break": {
        "categories": ["recovery_activity"],
        "fields": ["duration", "outcome", "trigger"],
    },
}


def _build_structured_details(body: LogCreate) -> dict:
    """
    Normalize typed telemetry fields into `details` JSON.
    Keeps API backward compatible while improving data richness.
    """
    details = dict(body.details or {})
    fields = (
        "start_time", "end_time", "previous_activity", "next_activity",
        "trigger", "outcome", "planned",
        "interruptions", "interruption_source", "task_difficulty",
        "bedtime", "wake_time", "awakenings",
        "exercise_type", "enjoyment", "energy_before", "energy_after", "social_context",
        "phone_purpose", "intended_duration",
    )
    for field in fields:
        value = getattr(body, field, None)
        if value is None:
            continue
        if isinstance(value, datetime):
            details[field] = value.isoformat()
        else:
            details[field] = value
    return details


def _extract_signals_from_notes(notes: str) -> dict:
    text = (notes or "").lower()
    out: dict = {}
    if not text:
        return out
    if "notification" in text:
        out.setdefault("trigger", "notification")
    elif "bored" in text or "boredom" in text:
        out.setdefault("trigger", "boredom")
    elif "stress" in text or "anxious" in text:
        out.setdefault("trigger", "stress")

    if "interrupt" in text or "disturb" in text:
        out.setdefault("interruption_source", "external_interruption")
    if "couldn't focus" in text or "cant focus" in text or "can't focus" in text:
        out.setdefault("outcome", "focus_loss")
    if "motivated" in text or "energized" in text:
        out.setdefault("outcome", "positive_activation")
    return out


# ════════════════════════════════════════════════
# AUTH
# ════════════════════════════════════════════════
@router.post("/auth/register", response_model=TokenResponse, tags=["Auth"])
async def register(body: UserRegister, db: AsyncSession = Depends(get_db)):
    existing = (await db.execute(select(User).where(User.email == body.email))).scalar_one_or_none()
    if existing:
        raise HTTPException(400, "Email already registered")
    user = User(
        email=body.email, username=body.username,
        hashed_pw=hash_password(body.password),
        timezone=body.timezone, consent=body.consent,
    )
    db.add(user)
    await db.flush()
    return TokenResponse(
        access_token=create_token({"sub": str(user.id)}),
        user_id=str(user.id), username=user.username,
    )


@router.post("/auth/login", response_model=TokenResponse, tags=["Auth"])
async def login(form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).where(User.email == form.username))).scalar_one_or_none()
    if not user or not verify_password(form.password, user.hashed_pw):
        raise HTTPException(401, "Invalid credentials")
    return TokenResponse(
        access_token=create_token({"sub": str(user.id)}),
        user_id=str(user.id), username=user.username,
    )


@router.get("/users/me", response_model=UserOut, tags=["Auth"])
async def me(uid: str = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    return user


# ════════════════════════════════════════════════
# LOGS
# ════════════════════════════════════════════════
@router.get("/logs", response_model=List[LogOut], tags=["Logs"])
async def list_logs(limit: int = 50, uid: str = Depends(get_current_user_id),
                    db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(Log).where(Log.user_id == uid)
        .order_by(Log.timestamp.desc()).limit(limit)
    )).scalars().all()
    return rows


@router.post("/logs", response_model=LogOut, status_code=201, tags=["Logs"])
async def create_log(body: LogCreate, uid: str = Depends(get_current_user_id),
                     db: AsyncSession = Depends(get_db)):
    previous_log = (await db.execute(
        select(Log).where(Log.user_id == uid).order_by(Log.timestamp.desc()).limit(1)
    )).scalars().first()
    details = _build_structured_details(body)
    note_signals = _extract_signals_from_notes(body.notes or "")
    for k, v in note_signals.items():
        details.setdefault(k, v)
    if previous_log and "previous_activity" not in details:
        details["previous_activity"] = previous_log.activity_type

    log = Log(
        user_id=uid,
        timestamp=body.timestamp or datetime.utcnow(),
        activity_type=body.activity_type,
        duration=body.duration,
        mood=body.mood,
        focus_score=body.focus_score,
        notes=body.notes,
        details=details,
    )
    db.add(log)
    await db.flush()
    await _fire_breakpoints(uid, log, db)
    await _detect_and_upsert_loop(uid, log, db)
    return log


@router.get("/activities/schema", tags=["Logs"])
async def activity_schema():
    """
    Dynamic telemetry contract for activity-specific forms in frontend.
    """
    return {
        "activity_signal_schema": ACTIVITY_SIGNAL_SCHEMA,
        "common_fields": [
            "activity_type", "duration", "mood", "focus_score", "notes", "timestamp",
            "start_time", "end_time", "previous_activity", "next_activity",
            "trigger", "outcome", "planned",
        ],
    }


async def _fire_breakpoints(uid: str, log: Log, db: AsyncSession):
    bps = (await db.execute(
        select(Breakpoint).where(Breakpoint.user_id == uid, Breakpoint.active == True)
    )).scalars().all()
    for bp in bps:
        hit = False
        if bp.condition_type == "focus_drop" and log.focus_score and log.focus_score < bp.threshold:
            hit = True
        elif bp.condition_type == "phone_overuse" and log.activity_type == "phone" and log.duration > bp.threshold:
            hit = True
        if hit:
            await ws_manager.push(uid, {
                "type": "breakpoint", "breakpoint_id": bp.id,
                "name": bp.name, "message": bp.action_msg,
                "condition_type": bp.condition_type,
                "timestamp": datetime.utcnow().isoformat(),
            })
            logger.info(f"[TRACE_PD] breakpoint fired: {bp.name} uid={uid}")


def _build_loop_from_log(log: Log, anomaly_score: float) -> dict:
    hour = log.timestamp.hour if log.timestamp else None
    trigger_time = f"{hour:02d}:00" if hour is not None else None
    low_focus = log.focus_score is not None and log.focus_score < 60

    if log.activity_type == "phone" and log.duration >= 20:
        trigger = "Energy/focus dip before distraction"
        action = f"Phone usage spike ({log.duration} min)"
        outcome = "Sustained attention dropped after phone interruption"
    elif low_focus and log.activity_type != "deep_work":
        trigger = "Low-focus state during work window"
        action = f"Shift to {log.activity_type} activity ({log.duration} min)"
        outcome = "Deep-work continuity broke and recovery lag increased"
    else:
        trigger = f"Anomalous {log.activity_type} pattern"
        action = f"{log.activity_type} duration outlier ({log.duration} min)"
        outcome = "Routine consistency weakened relative to recent baseline"

    confidence = max(0.55, min(0.95, 0.55 + anomaly_score))
    estimate = (
        f"IsolationForest detected this event as an outlier "
        f"(anomaly_score={anomaly_score:.3f})."
    )
    return {
        "trigger_desc": trigger,
        "trigger_time": trigger_time,
        "action_desc": action,
        "outcome_desc": outcome,
        "confidence": confidence,
        "causal_estimate": estimate,
    }


def _rule_based_loop_candidate(log: Log) -> dict | None:
    return _rule_based_loop_candidate_with_history(log, [])


def _rule_based_loop_candidate_with_history(log: Log, recent_logs: List[Log]) -> dict | None:
    # Fallback for cold-start / low-variance histories where anomaly models stay silent.
    hour = log.timestamp.hour if log.timestamp else None
    trigger_time = f"{hour:02d}:00" if hour is not None else None

    # 1) Distraction / phone loops
    if log.activity_type == "phone" and log.duration >= 25:
        return _build_loop_from_log(log, anomaly_score=0.20)

    # 2) Focus collapse loops
    if log.focus_score is not None and log.focus_score <= 45:
        return _build_loop_from_log(log, anomaly_score=0.16)

    # 3) Deep-work instability loops
    if log.activity_type == "deep_work" and log.duration <= 20:
        return {
            "trigger_desc": "Shallow work burst during focus block",
            "trigger_time": trigger_time,
            "action_desc": f"Deep-work session too short ({log.duration} min)",
            "outcome_desc": "Flow state did not stabilize, leading to repeated task resets",
            "confidence": 0.64,
            "causal_estimate": "Rule-based detector flagged repeated short deep-work intervals.",
        }

    # 4) Break overrun loops
    if log.activity_type == "break" and log.duration >= 45:
        return {
            "trigger_desc": "Recovery break exceeded reset window",
            "trigger_time": trigger_time,
            "action_desc": f"Extended break ({log.duration} min)",
            "outcome_desc": "Return-to-focus latency increased after long break",
            "confidence": 0.63,
            "causal_estimate": "Rule-based detector identified break-overrun pattern affecting focus continuity.",
        }

    # 5) Sleep debt loops (single-log + weak historical corroboration)
    if log.activity_type == "sleep" and log.duration <= 300:
        short_sleep_recent = sum(
            1 for l in recent_logs[:15] if l.activity_type == "sleep" and (l.duration or 0) <= 360
        )
        return {
            "trigger_desc": "Insufficient sleep before performance window",
            "trigger_time": trigger_time,
            "action_desc": f"Short sleep interval ({log.duration} min)",
            "outcome_desc": "Energy/focus resilience reduced the next day",
            "confidence": 0.62 if short_sleep_recent < 2 else 0.7,
            "causal_estimate": (
                "Rule-based detector flagged sleep debt; confidence raised by repeated short-sleep history."
            ),
        }

    # 6) Reading fragmentation loops
    if log.activity_type == "reading" and log.duration <= 10:
        return {
            "trigger_desc": "Low-attention reading attempt",
            "trigger_time": trigger_time,
            "action_desc": f"Reading block too short ({log.duration} min)",
            "outcome_desc": "Knowledge session fragmented before retention threshold",
            "confidence": 0.6,
            "causal_estimate": "Rule-based detector flagged repeated micro-reading risk pattern.",
        }

    # 7) Exercise omission loops (detected when non-exercise logs dominate recent history)
    if log.activity_type in {"deep_work", "phone", "break", "reading"}:
        has_recent_exercise = any(l.activity_type == "exercise" for l in recent_logs[:20])
        if not has_recent_exercise and len(recent_logs) >= 8:
            return {
                "trigger_desc": "No movement pattern in recent routine",
                "trigger_time": trigger_time,
                "action_desc": "Exercise missing across recent activity window",
                "outcome_desc": "Cognitive energy regulation weakened without physical reset",
                "confidence": 0.61,
                "causal_estimate": "Rule-based detector found no exercise events in recent behavior trace.",
            }

    return None


async def _detect_and_upsert_loop(uid: str, new_log: Log, db: AsyncSession):
    recent_logs = (await db.execute(
        select(Log).where(Log.user_id == uid).order_by(Log.timestamp.desc()).limit(60)
    )).scalars().all()
    if len(recent_logs) < 5:
        return

    # Run anomaly detection on chronological data so index mapping is stable.
    ordered = list(reversed(recent_logs))
    payload = [{
        "id": l.id,
        "activity_type": l.activity_type,
        "duration": l.duration,
        "mood": l.mood,
        "focus_score": l.focus_score,
        "timestamp": str(l.timestamp),
    } for l in ordered]
    anomalies = detect_anomalous_loops(payload)
    loop_data = None
    if anomalies:
        # Primary path: only use anomaly output when the latest log is flagged.
        target = next((a for a in anomalies if payload[a["log_index"]]["id"] == new_log.id), None)
        if target:
            anomaly_score = float(target.get("anomaly_score", 0.0))
            loop_data = _build_loop_from_log(new_log, anomaly_score)

    # Fallback path for predictable but important patterns.
    if loop_data is None:
        loop_data = _rule_based_loop_candidate_with_history(new_log, ordered)
    if loop_data is None:
        return
    existing = (await db.execute(
        select(Loop).where(
            Loop.user_id == uid,
            Loop.trigger_desc == loop_data["trigger_desc"],
            Loop.action_desc == loop_data["action_desc"],
            Loop.outcome_desc == loop_data["outcome_desc"],
            Loop.status == "active",
        )
    )).scalar_one_or_none()

    if existing:
        existing.occurrences = (existing.occurrences or 1) + 1
        existing.confidence = max(existing.confidence or 0.0, loop_data["confidence"])
        existing.trigger_time = loop_data["trigger_time"] or existing.trigger_time
        existing.causal_estimate = loop_data["causal_estimate"]
        logger.info(f"[TRACE_PD] loop updated id={existing.id} uid={uid}")
        return

    loop = Loop(
        user_id=uid,
        trigger_desc=loop_data["trigger_desc"],
        trigger_time=loop_data["trigger_time"],
        action_desc=loop_data["action_desc"],
        outcome_desc=loop_data["outcome_desc"],
        confidence=loop_data["confidence"],
        occurrences=1,
        status="active",
        causal_estimate=loop_data["causal_estimate"],
    )
    db.add(loop)
    await db.flush()
    logger.info(f"[TRACE_PD] loop created id={loop.id} uid={uid}")


# ════════════════════════════════════════════════
# LOOPS
# ════════════════════════════════════════════════
@router.get("/loops", response_model=List[LoopOut], tags=["Loops"])
async def list_loops(uid: str = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    loops = (await db.execute(
        select(Loop).where(Loop.user_id == uid).order_by(Loop.confidence.desc())
    )).scalars().all()
    result = []
    for loop in loops:
        fixes = (await db.execute(select(Fix).where(Fix.loop_id == loop.id))).scalars().all()
        result.append(LoopOut(
            id=loop.id, trigger_desc=loop.trigger_desc, trigger_time=loop.trigger_time,
            action_desc=loop.action_desc, outcome_desc=loop.outcome_desc,
            confidence=loop.confidence, occurrences=loop.occurrences,
            status=loop.status, causal_estimate=loop.causal_estimate,
            detected_at=loop.detected_at,
            fixes=[FixShort(id=f.id, suggestion=f.suggestion, effort=f.effort,
                            impact=f.impact, applied=f.applied) for f in fixes],
        ))
    return result


@router.patch("/loops/{loop_id}/status", tags=["Loops"])
async def update_loop_status(loop_id: int, status: str,
                              uid: str = Depends(get_current_user_id),
                              db: AsyncSession = Depends(get_db)):
    loop = (await db.execute(
        select(Loop).where(Loop.id == loop_id, Loop.user_id == uid)
    )).scalar_one_or_none()
    if not loop:
        raise HTTPException(404, "Loop not found")
    loop.status = status
    return {"ok": True, "status": status}


# ════════════════════════════════════════════════
# FIXES
# ════════════════════════════════════════════════
@router.patch("/fixes/{fix_id}", response_model=FixOut, tags=["Fixes"])
async def apply_fix(fix_id: int, body: FixApply,
                    uid: str = Depends(get_current_user_id),
                    db: AsyncSession = Depends(get_db)):
    fix = (await db.execute(
        select(Fix).where(Fix.id == fix_id, Fix.user_id == uid)
    )).scalar_one_or_none()
    if not fix:
        raise HTTPException(404, "Fix not found")
    fix.applied = body.applied
    return fix


# ════════════════════════════════════════════════
# DEBUG — LangGraph multi-agent
# ════════════════════════════════════════════════
@router.post("/debug", response_model=DebugResponse, tags=["AI Debug"])
async def debug_query(body: DebugQuery, uid: str = Depends(get_current_user_id),
                      db: AsyncSession = Depends(get_db)):
    logs_raw = (await db.execute(
        select(Log).where(Log.user_id == uid).order_by(Log.timestamp.desc()).limit(30)
    )).scalars().all()
    loops_raw = (await db.execute(select(Loop).where(Loop.user_id == uid))).scalars().all()

    logs  = [{"activity_type": l.activity_type, "duration": l.duration,
               "mood": l.mood, "focus_score": l.focus_score,
               "timestamp": str(l.timestamp), "details": l.details or {}} for l in logs_raw]
    loops = [{"trigger_desc": l.trigger_desc, "action_desc": l.action_desc,
               "confidence": l.confidence, "occurrences": l.occurrences,
               "status": l.status} for l in loops_raw]

    result = await run_debug_pipeline(
        query=body.query,
        user_id=uid,
        logs=logs,
        loops=loops,
        include_context=body.include_context,
    )

    db.add(ChatMessage(user_id=uid, role="user", content=body.query))
    db.add(ChatMessage(
        user_id=uid, role="assistant",
        content=result["cause"] + "\n\n" + result["suggestion"],
        tokens_used=result["tokens_used"], model_used="trcpd-langgraph",
    ))
    return DebugResponse(query=body.query, **result)


# ════════════════════════════════════════════════
# CHAT HISTORY
# ════════════════════════════════════════════════
@router.get("/chat/history", tags=["Chat"])
async def chat_history(limit: int = 40, uid: str = Depends(get_current_user_id),
                       db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(ChatMessage).where(ChatMessage.user_id == uid)
        .order_by(ChatMessage.created_at.asc()).limit(limit)
    )).scalars().all()
    return [{"role": m.role, "content": m.content,
             "created_at": m.created_at.isoformat()} for m in rows]


# ════════════════════════════════════════════════
# DASHBOARD
# ════════════════════════════════════════════════
@router.get("/dashboard", response_model=DashboardStats, tags=["Dashboard"])
async def dashboard(uid: str = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    logs_raw  = (await db.execute(
        select(Log).where(Log.user_id == uid).order_by(Log.timestamp.desc()).limit(100)
    )).scalars().all()
    loops_raw = (await db.execute(select(Loop).where(Loop.user_id == uid))).scalars().all()

    logs = [{"activity_type": l.activity_type, "duration": l.duration,
              "mood": l.mood, "focus_score": l.focus_score,
              "timestamp": str(l.timestamp), "details": l.details or {}} for l in logs_raw]

    focus_score = compute_focus_score(logs)
    sleep_hrs   = next((l.duration / 60 for l in logs_raw if l.activity_type == "sleep"), 0.0)
    prod_hrs    = sum(l.duration for l in logs_raw if l.activity_type == "deep_work") / 60

    active_loops   = [l for l in loops_raw if l.status == "active"]
    resolved_loops = [l for l in loops_raw if l.status == "resolved"]

    top_loop = None
    if active_loops:
        top = max(active_loops, key=lambda x: x.confidence)
        fixes = (await db.execute(select(Fix).where(Fix.loop_id == top.id))).scalars().all()
        top_loop = {
            "trigger_desc": top.trigger_desc, "trigger_time": top.trigger_time,
            "action_desc":  top.action_desc,  "outcome_desc": top.outcome_desc,
            "confidence":   top.confidence,   "occurrences":  top.occurrences,
            "fixes": [{"suggestion": f.suggestion, "applied": f.applied} for f in fixes],
        }

    alert = None
    if focus_score < 60:
        alert = {
            "title":   "Focus Drop Detected",
            "message": "Your focus score dropped below 60. Consider taking a break.",
            "action":  "Take a 10-min walk",
        }

    return DashboardStats(
        focus_score=focus_score, focus_delta=5.0,
        sleep_hours=round(sleep_hrs, 1), sleep_delta=0.5,
        productive_hours=round(prod_hrs, 1), productive_delta=1.2,
        focus_timeline=build_focus_timeline(logs),
        activity_distribution=build_activity_distribution(logs),
        mood_trend=build_mood_trend(logs),
        active_loops=len(active_loops),
        resolved_loops=len(resolved_loops),
        top_loop=top_loop, alert=alert,
    )


# ════════════════════════════════════════════════
# BREAKPOINTS
# ════════════════════════════════════════════════
@router.get("/breakpoints", response_model=List[BreakpointOut], tags=["Breakpoints"])
async def list_breakpoints(uid: str = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Breakpoint).where(Breakpoint.user_id == uid))).scalars().all()
    return rows


@router.post("/breakpoints", response_model=BreakpointOut, status_code=201, tags=["Breakpoints"])
async def create_breakpoint(body: BreakpointCreate, uid: str = Depends(get_current_user_id),
                             db: AsyncSession = Depends(get_db)):
    bp = Breakpoint(user_id=uid, **body.model_dump())
    db.add(bp); await db.flush()
    return bp


# ════════════════════════════════════════════════
# WEBSOCKET
# ════════════════════════════════════════════════
@router.websocket("/ws/{uid}")
async def websocket_endpoint(ws: WebSocket, uid: str):
    await ws_manager.connect(ws, uid)
    try:
        await ws.send_json({"type": "connected", "uid": uid, "app": "TRACE_PD"})
        while True:
            data = await ws.receive_json()
            if data.get("type") == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        ws_manager.disconnect(ws, uid)
