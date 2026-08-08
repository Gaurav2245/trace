"""
Everything that happens as a side effect of a user creating an activity log:
telemetry enrichment, breakpoint alerts, and behavior-loop detection.
Kept out of app/api/routes.py so the HTTP layer stays thin.
"""
from datetime import datetime, timezone
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.models.models import Log, Loop, Breakpoint
from app.schemas.schemas import LogCreate
from app.core.websocket_manager import ws_manager
from app.ml.engine import detect_anomalous_loops

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


def build_structured_details(body: LogCreate) -> dict:
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


def extract_signals_from_notes(notes: str) -> dict:
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


async def fire_breakpoints(uid: str, log: Log, db: AsyncSession) -> None:
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
                "timestamp": datetime.now(timezone.utc).isoformat(),
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


def _rule_based_loop_candidate(log: Log, recent_logs: List[Log]) -> dict | None:
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


async def detect_and_upsert_loop(uid: str, new_log: Log, db: AsyncSession) -> None:
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
        loop_data = _rule_based_loop_candidate(new_log, ordered)
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
