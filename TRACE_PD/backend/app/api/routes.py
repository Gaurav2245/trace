from fastapi import APIRouter, Depends, HTTPException, Query, Request, status, WebSocket, WebSocketDisconnect
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from typing import List, Literal

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
from jose import JWTError
from app.core.auth import hash_password, verify_password, create_token, get_current_user_id, decode_user_id
from app.core.limiter import limiter
from app.core.websocket_manager import ws_manager
from app.agents.pipeline import run_debug_pipeline
from app.ml.engine import (
    compute_focus_score, build_focus_timeline,
    build_activity_distribution, build_mood_trend,
)
from app.services.log_ingestion import (
    ACTIVITY_SIGNAL_SCHEMA,
    build_structured_details,
    extract_signals_from_notes,
    fire_breakpoints,
    detect_and_upsert_loop,
)
from loguru import logger

router = APIRouter()


# ════════════════════════════════════════════════
# AUTH
# ════════════════════════════════════════════════
@router.post("/auth/register", response_model=TokenResponse, tags=["Auth"])
@limiter.limit("10/minute")
async def register(request: Request, body: UserRegister, db: AsyncSession = Depends(get_db)):
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
@limiter.limit("10/minute")
async def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
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
async def list_logs(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                    uid: str = Depends(get_current_user_id),
                    db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(Log).where(Log.user_id == uid)
        .order_by(Log.timestamp.desc()).limit(limit).offset(offset)
    )).scalars().all()
    return rows


@router.post("/logs", response_model=LogOut, status_code=201, tags=["Logs"])
async def create_log(body: LogCreate, uid: str = Depends(get_current_user_id),
                     db: AsyncSession = Depends(get_db)):
    previous_log = (await db.execute(
        select(Log).where(Log.user_id == uid).order_by(Log.timestamp.desc()).limit(1)
    )).scalars().first()
    details = build_structured_details(body)
    note_signals = extract_signals_from_notes(body.notes or "")
    for k, v in note_signals.items():
        details.setdefault(k, v)
    if previous_log and "previous_activity" not in details:
        details["previous_activity"] = previous_log.activity_type

    log = Log(
        user_id=uid,
        timestamp=body.timestamp or datetime.now(timezone.utc),
        activity_type=body.activity_type,
        duration=body.duration,
        mood=body.mood,
        focus_score=body.focus_score,
        notes=body.notes,
        details=details,
    )
    db.add(log)
    await db.flush()
    await fire_breakpoints(uid, log, db)
    await detect_and_upsert_loop(uid, log, db)
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


# ════════════════════════════════════════════════
# LOOPS
# ════════════════════════════════════════════════
@router.get("/loops", response_model=List[LoopOut], tags=["Loops"])
async def list_loops(uid: str = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    loops = (await db.execute(
        select(Loop).where(Loop.user_id == uid).order_by(Loop.confidence.desc())
    )).scalars().all()

    fixes_by_loop: dict[int, list[Fix]] = {}
    if loops:
        loop_ids = [loop.id for loop in loops]
        all_fixes = (await db.execute(
            select(Fix).where(Fix.loop_id.in_(loop_ids))
        )).scalars().all()
        for fix in all_fixes:
            fixes_by_loop.setdefault(fix.loop_id, []).append(fix)

    result = []
    for loop in loops:
        fixes = fixes_by_loop.get(loop.id, [])
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
async def update_loop_status(loop_id: int, status: Literal["active", "resolved", "monitoring"],
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
async def chat_history(limit: int = Query(40, ge=1, le=200), offset: int = Query(0, ge=0),
                       uid: str = Depends(get_current_user_id),
                       db: AsyncSession = Depends(get_db)):
    # Order DESC to always page from the most recent messages, then reverse
    # so the response is still oldest-first for chronological display.
    rows = (await db.execute(
        select(ChatMessage).where(ChatMessage.user_id == uid)
        .order_by(ChatMessage.created_at.desc()).limit(limit).offset(offset)
    )).scalars().all()
    return [{"role": m.role, "content": m.content,
             "created_at": m.created_at.isoformat()} for m in reversed(rows)]


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
async def websocket_endpoint(ws: WebSocket, uid: str, token: str | None = None):
    if not token:
        await ws.close(code=4401)
        return
    try:
        token_uid = decode_user_id(token)
    except (JWTError, ValueError):
        await ws.close(code=4401)
        return
    if token_uid != uid:
        await ws.close(code=4403)
        return

    await ws_manager.connect(ws, uid)
    try:
        await ws.send_json({"type": "connected", "uid": uid, "app": "TRACE_PD"})
        while True:
            data = await ws.receive_json()
            if data.get("type") == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        ws_manager.disconnect(ws, uid)
