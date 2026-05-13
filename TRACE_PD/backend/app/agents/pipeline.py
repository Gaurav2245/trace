"""
TRACE_PD — LangGraph Multi-Agent Pipeline
Agents: Parser → Retriever → Causal → Fixer
Falls back gracefully when LangGraph is not installed.
"""
from typing import TypedDict, List, Annotated, Optional, Tuple
import operator
import time
from datetime import datetime
from collections import Counter
import json
from datetime import timedelta
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings

try:
    from langgraph.graph import StateGraph, END
    _HAS_LANGGRAPH = True
except ImportError:
    _HAS_LANGGRAPH = False
    logger.warning("LangGraph not found — sequential fallback active")


# ── Shared state ──────────────────────────────────────────
class AgentState(TypedDict):
    query:            str
    normalized_query: str
    user_id:          str
    logs:             List[dict]
    filtered_logs:    List[dict]
    loops:            List[dict]
    parsed_intent:    str
    intent_confidence: float
    behavior_entities: List[str]
    semantic_entity:  str
    semantic_intent:  str
    semantic_metric:  str
    time_window:      str
    query_hour_hint:  Optional[int]
    retrieved_ctx:    str
    retrieval_status: str
    retrieved_log_count: int
    context_window:   dict
    behavior_state:   dict
    causal_analysis:  str
    fix_suggestion:   str
    pipeline_mode:    str
    allow_causal:     bool
    response_style:   str
    agent_trace:      Annotated[List[str], operator.add]
    tokens_used:      int
    confidence:       float


# ── Intent classifier ─────────────────────────────────────
_INTENTS = {
    "exercise_enjoyment": ["exercise", "workout", "gym", "run", "running", "yoga", "fitness", "enjoy exercise", "enjoy workout"],
    "sleep_cause_analysis": ["why sleep", "sleep pattern", "sleep issue", "sleep quality", "insomnia"],
    "sleep_now_assistance": ["i want to sleep", "cant sleep now", "can't sleep now", "help me sleep", "sleep now"],
    "fatigue_expression": ["exhausted", "drained", "so tired", "very tired", "fatigue", "burned out", "burnt out"],
    "emotional_distress": ["hopeless", "overwhelmed", "anxious", "stressed", "panic", "cannot cope", "can't cope"],
    "energy_analysis":  ["tired", "energy", "fatigue", "3pm", "afternoon", "crash"],
    "focus_analysis":   ["procrastinat", "distract", "focus", "youtube", "scroll", "attention"],
    "study_focus":      ["study", "studying", "homework", "exam", "revision", "can't study", "cant study", "unable to study"],
    "sleep_analysis":   ["sleep", "wake", "rest", "bed", "tired morning"],
    "loop_analysis":    ["habit", "loop", "pattern", "repeat", "cycle"],
}

_INTENT_FEATURE_SCOPE = {
    "sleep_analysis": {"sleep", "phone"},
    "sleep_cause_analysis": {"sleep", "phone"},
    "sleep_now_assistance": {"sleep", "phone"},
    "focus_analysis": {"deep_work", "phone"},
    "energy_analysis": {"deep_work", "sleep", "phone", "walk", "exercise", "workout"},
    "fatigue_expression": {"sleep", "walk", "exercise", "workout"},
    "loop_analysis": {"phone", "deep_work", "sleep"},
    "exercise_enjoyment": {"exercise", "workout", "walk", "run", "running", "gym", "yoga", "cycle", "cycling"},
}

# Behavior ontology: map many activities into general reasoning classes.
ACTIVITY_ONTOLOGY = {
    "deep_work": {
        "categories": ["focus_activity", "high_cognitive_load"],
        "related_signals": ["interruptions", "task_difficulty", "focus_score", "previous_activity"],
    },
    "study": {
        "categories": ["focus_activity", "high_cognitive_load"],
        "related_signals": ["interruptions", "task_difficulty", "focus_score", "previous_activity"],
    },
    "reading": {
        "categories": ["focus_activity", "low_stimulation_activity"],
        "related_signals": ["duration", "focus_score", "previous_activity"],
    },
    "sleep": {
        "categories": ["recovery_activity"],
        "related_signals": ["bedtime", "wake_time", "awakenings", "mood"],
    },
    "phone": {
        "categories": ["stimulation_activity", "distraction_activity"],
        "related_signals": ["intended_duration", "duration", "trigger", "phone_purpose"],
    },
    "exercise": {
        "categories": ["activation_activity", "recovery_activity"],
        "related_signals": ["exercise_type", "enjoyment", "energy_before", "energy_after"],
    },
    "break": {
        "categories": ["recovery_activity"],
        "related_signals": ["duration", "outcome", "previous_activity"],
    },
}

_ENTITY_ALIASES = {
    "study": {"study", "studying", "homework", "revision", "exam"},
    "exercise": {"exercise", "workout", "gym", "run", "running", "yoga", "cardio"},
    "sleep": {"sleep", "bed", "bedtime", "wake", "insomnia"},
    "phone": {"phone", "scroll", "scrolling", "social media", "instagram", "youtube"},
    "focus": {"focus", "concentrate", "attention", "distract", "procrastinate"},
}

_SEMANTIC_INTENT_KEYWORDS = {
    "lookup": {"how much", "how many", "tell me", "show me", "what is", "what was"},
    "timeline": {"timeline", "over time", "trend", "this week", "last week", "today"},
    "comparison": {"compare", "vs", "versus", "more than", "less than"},
    "cause_analysis": {"why", "cause", "because", "reason"},
    "improvement": {"improve", "better", "optimize", "help me", "what should i do", "fix"},
    "loop_detection": {"loop", "pattern", "repeat", "cycle"},
    "summary": {"summary", "summarize", "overview", "recap"},
}

_SEMANTIC_METRIC_KEYWORDS = {
    "duration": {"time", "duration", "hours", "minutes", "long"},
    "frequency": {"often", "frequency", "times", "count"},
    "focus": {"focus", "attention", "distract"},
    "mood": {"mood", "feel", "emotion"},
    "consistency": {"consistent", "consistency", "regular", "routine"},
    "interruptions": {"interrupt", "notification", "disturb"},
    "transitions": {"before", "after", "transition", "happens before", "happens after"},
}


def normalize_query(raw: str) -> str:
    """
    Lightweight query normalization for messy human input:
    - collapses whitespace
    - removes immediate repetitions (e.g. "why cant i why cant i study" -> "why cant i study")
    - keeps original meaning; does not attempt grammar correction
    """
    q = " ".join((raw or "").strip().split())
    if not q:
        return ""
    tokens = q.lower().replace("?", "").replace("!", "").replace(".", "").replace(",", "").split()
    # Deduplicate repeated bigrams/trigrams appearing back-to-back.
    out: List[str] = []
    i = 0
    while i < len(tokens):
        # Try remove repeated trigram
        if i + 5 < len(tokens) and tokens[i:i+3] == tokens[i+3:i+6]:
            out.extend(tokens[i:i+3])
            i += 6
            continue
        # Try remove repeated bigram
        if i + 3 < len(tokens) and tokens[i:i+2] == tokens[i+2:i+4]:
            out.extend(tokens[i:i+2])
            i += 4
            continue
        out.append(tokens[i])
        i += 1
    return " ".join(out)


def _normalize_activity_label(name: str) -> str:
    return (name or "").strip().lower().replace(" ", "_")


def _activity_category(activity: str) -> str:
    a = _normalize_activity_label(activity)
    entry = ACTIVITY_ONTOLOGY.get(a)
    if entry and entry.get("categories"):
        return str(entry["categories"][0])
    # Soft aliases for common variants.
    if a in {"workout", "run", "running", "yoga", "walk"}:
        return "recovery_activity"
    if a in {"social_media", "youtube", "gaming", "scrolling", "notifications"}:
        return "stimulation_activity"
    if a in {"writing", "coding", "homework", "studying"}:
        return "focus_activity"
    if a in {"meal", "eating", "lunch", "breakfast", "dinner"}:
        return "maintenance_activity"
    if a in {"meeting", "chat", "call", "social"}:
        return "social_activity"
    return "other_activity"


def _extract_behavior_entities(query: str) -> List[str]:
    q = " ".join((query or "").lower().split())
    entities: List[str] = []
    for entity, aliases in _ENTITY_ALIASES.items():
        if any(alias in q for alias in aliases):
            entities.append(entity)
    # Fallback entity for generic behavioral language.
    if not entities and any(w in q for w in ("habit", "pattern", "routine", "behavior", "loop")):
        entities.append("behavior_pattern")
    return entities


def _semantic_decompose(query: str, entities: List[str], parsed_intent: str, time_window: str) -> tuple[str, str, str]:
    q = " ".join((query or "").lower().split())
    semantic_entity = entities[0] if entities else (
        "focus_activity" if parsed_intent in {"focus_analysis", "study_focus"} else
        "sleep" if parsed_intent in {"sleep_analysis", "sleep_cause_analysis", "sleep_now_assistance"} else
        "exercise" if parsed_intent == "exercise_enjoyment" else
        "behavior"
    )

    semantic_intent = "analysis"
    for key, kws in _SEMANTIC_INTENT_KEYWORDS.items():
        if any(k in q for k in kws):
            semantic_intent = key
            break
    if parsed_intent in {"sleep_cause_analysis", "loop_analysis"}:
        semantic_intent = "cause_analysis" if parsed_intent == "sleep_cause_analysis" else "loop_detection"
    if parsed_intent in {"chat_smalltalk"}:
        semantic_intent = "summary"

    semantic_metric = "general_behavior"
    for key, kws in _SEMANTIC_METRIC_KEYWORDS.items():
        if any(k in q for k in kws):
            semantic_metric = key
            break
    if parsed_intent in {"focus_analysis", "study_focus"}:
        semantic_metric = "focus"
    elif parsed_intent in {"sleep_analysis", "sleep_cause_analysis", "sleep_now_assistance"}:
        semantic_metric = "consistency"

    # Respect parser-extracted time window for downstream planning.
    if time_window != "all_day" and semantic_intent in {"lookup", "analysis"}:
        semantic_intent = "timeline"
    return semantic_entity, semantic_intent, semantic_metric


def _classify(query: str) -> str:
    q = " ".join(query.lower().strip().split())
    tokens = set(q.replace(",", " ").replace(".", " ").replace("!", " ").replace("?", " ").split())

    # Handle short greetings/small-talk before analysis intents.
    if q in {"hi", "hello", "hey", "yo", "sup", "hii", "heyy"}:
        return "chat_smalltalk"
    if q in {"good morning", "good afternoon", "good evening"}:
        return "chat_smalltalk"
    if tokens & {"thanks", "thank", "thx", "bye", "goodbye"}:
        return "chat_smalltalk"

    for intent in ("sleep_now_assistance", "emotional_distress", "fatigue_expression", "sleep_cause_analysis", "exercise_enjoyment"):
        if any(k in q for k in _INTENTS[intent]):
            return intent

    # Study is a focus problem (route into focus pipeline).
    if any(k in q for k in _INTENTS.get("study_focus", [])):
        return "focus_analysis"

    for intent, keywords in _INTENTS.items():
        if intent in {"sleep_now_assistance", "emotional_distress", "fatigue_expression", "sleep_cause_analysis", "exercise_enjoyment"}:
            continue
        if any(k in q for k in keywords):
            return intent
    return "general_analysis"


def _classify_with_confidence(query: str) -> tuple[str, float]:
    """
    Heuristic intent confidence:
    - high for explicit conversational intents (hi/bye/thanks)
    - medium/high when multiple keywords match a specific intent
    - low when falling back to general_analysis
    """
    q = " ".join((query or "").lower().strip().split())
    if not q:
        return "chat_smalltalk", 0.85

    tokens = set(q.replace(",", " ").replace(".", " ").replace("!", " ").replace("?", " ").split())
    if q in {"hi", "hello", "hey", "yo", "sup", "hii", "heyy"}:
        return "chat_smalltalk", 0.95
    if q in {"good morning", "good afternoon", "good evening"}:
        return "chat_smalltalk", 0.90
    if tokens & {"thanks", "thank", "thx", "bye", "goodbye"}:
        return "chat_smalltalk", 0.90

    # If the query mentions a known behavior entity (phone/sleep/exercise/study/etc),
    # treat it as a behavior query even if it's a lookup-style question.
    entity_hits = 0
    for aliases in _ENTITY_ALIASES.values():
        entity_hits += sum(1 for a in aliases if a in q)
    if entity_hits:
        # Keep intent generic unless a stronger match occurs later, but avoid "low confidence" fallback.
        return "general_analysis", min(0.55 + 0.08 * entity_hits, 0.80)

    # Priority intents
    priority = ("sleep_now_assistance", "emotional_distress", "fatigue_expression", "sleep_cause_analysis", "exercise_enjoyment")
    for intent in priority:
        hits = sum(1 for k in _INTENTS[intent] if k in q)
        if hits:
            return intent, min(0.65 + 0.12 * hits, 0.92)

    # Study routes into focus.
    study_hits = sum(1 for k in _INTENTS.get("study_focus", []) if k in q)
    if study_hits:
        return "focus_analysis", min(0.62 + 0.10 * study_hits, 0.88)

    best_intent = "general_analysis"
    best_hits = 0
    for intent, keywords in _INTENTS.items():
        if intent in set(priority) | {"study_focus"}:
            continue
        hits = sum(1 for k in keywords if k in q)
        if hits > best_hits:
            best_hits = hits
            best_intent = intent

    if best_intent != "general_analysis" and best_hits:
        return best_intent, min(0.52 + 0.10 * best_hits, 0.85)
    return "general_analysis", 0.25


def _extract_time_window(query: str) -> tuple[str, Optional[int]]:
    q = query.lower()
    hour_hint: Optional[int] = None

    # Quick parse for "4 pm", "4pm", "16:00", etc.
    for token in q.replace(":", " ").split():
        raw = token.strip(",.?!")
        if raw.endswith("am") or raw.endswith("pm"):
            num = raw[:-2]
            if num.isdigit():
                h = int(num)
                if 1 <= h <= 12:
                    if raw.endswith("pm") and h != 12:
                        h += 12
                    if raw.endswith("am") and h == 12:
                        h = 0
                    hour_hint = h
                    break
        elif raw.isdigit():
            h = int(raw)
            if 0 <= h <= 23:
                hour_hint = h
                break

    if hour_hint is not None:
        if 5 <= hour_hint < 12:
            return "morning", hour_hint
        if 12 <= hour_hint < 18:
            return "afternoon", hour_hint
        if 18 <= hour_hint < 22:
            return "evening", hour_hint
        return "night", hour_hint

    if any(k in q for k in ["morning", "am", "breakfast"]):
        return "morning", None
    if any(k in q for k in ["afternoon", "post-lunch", "lunch", "3pm", "4pm", "5pm"]):
        return "afternoon", None
    if any(k in q for k in ["evening", "dinner", "7pm", "8pm", "9pm"]):
        return "evening", None
    if any(k in q for k in ["night", "late", "bedtime", "10pm", "11pm", "12am"]):
        return "night", None
    return "all_day", None


def _resolve_context_window(query: str, time_window: str) -> dict:
    """
    Canonical temporal scope used across the pipeline to prevent contradictory totals.
    """
    q = " ".join((query or "").lower().split())
    now = datetime.utcnow()
    scope = time_window
    start: datetime | None = None
    end: datetime | None = None

    if "today" in q:
        scope = "today"
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now
    elif "this week" in q or "this_week" in q:
        scope = "this_week"
        start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        end = now
    elif "last 14 days" in q or "14 days" in q:
        scope = "last_14_days"
        start = now - timedelta(days=14)
        end = now
    elif scope in {"morning", "afternoon", "evening", "night"}:
        # time-of-day window for "today"
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now
    else:
        scope = "all_time"
        start = None
        end = None

    return {
        "scope": scope,
        "start_utc": start.isoformat() if start else None,
        "end_utc": end.isoformat() if end else None,
    }


def _parse_hour(timestamp: str) -> Optional[int]:
    try:
        ts = timestamp.replace("Z", "+00:00")
        return datetime.fromisoformat(ts).hour
    except Exception:
        return None


def _in_window(hour: int, window: str) -> bool:
    if window == "morning":
        return 5 <= hour < 12
    if window == "afternoon":
        return 12 <= hour < 18
    if window == "evening":
        return 18 <= hour < 22
    if window == "night":
        return hour >= 22 or hour < 5
    return True


def _filter_logs_by_window(logs: List[dict], window: str) -> List[dict]:
    if window == "all_day":
        return logs
    filtered: List[dict] = []
    for log in logs:
        hour = _parse_hour(str(log.get("timestamp", "")))
        if hour is not None and _in_window(hour, window):
            filtered.append(log)
    return filtered


def _scope_logs_by_intent(logs: List[dict], intent: str) -> List[dict]:
    scope = _INTENT_FEATURE_SCOPE.get(intent)
    if not scope:
        return logs
    scoped = [l for l in logs if str(l.get("activity_type", "")).lower() in scope]
    return scoped if scoped else logs


# ── Agent nodes ───────────────────────────────────────────
def parser_agent(state: AgentState) -> AgentState:
    t0     = time.time()
    normalized = normalize_query(state["query"])
    entities = _extract_behavior_entities(normalized or state["query"])
    intent, intent_conf = _classify_with_confidence(normalized or state["query"])
    time_window, hour_hint = _extract_time_window(normalized or state["query"])
    ctx_window = _resolve_context_window(normalized or state["query"], time_window)
    semantic_entity, semantic_intent, semantic_metric = _semantic_decompose(
        normalized or state["query"], entities, intent, time_window
    )
    ms     = round((time.time() - t0) * 1000, 1)
    return {**state,
            "parsed_intent": intent,
            "intent_confidence": intent_conf,
            "behavior_entities": entities,
            "semantic_entity": semantic_entity,
            "semantic_intent": semantic_intent,
            "semantic_metric": semantic_metric,
            "normalized_query": normalized,
            "time_window": time_window,
            "context_window": ctx_window,
            "query_hour_hint": hour_hint,
            "agent_trace": [f"[Parser] normalized='{normalized}', intent='{intent}' (conf={intent_conf:.2f}), semantics={{entity:{semantic_entity}, intent:{semantic_intent}, metric:{semantic_metric}, window:{time_window}}} ({ms} ms)"]}


def _scope_logs_by_entities(logs: List[dict], entities: List[str]) -> List[dict]:
    if not entities:
        return logs
    mapped_activities = set()
    if "exercise" in entities:
        mapped_activities |= {"exercise", "workout", "run", "running", "yoga", "walk"}
    if "study" in entities or "focus" in entities:
        mapped_activities |= {"deep_work", "study", "reading", "writing"}
    if "sleep" in entities:
        mapped_activities |= {"sleep", "nap", "rest"}
    if "phone" in entities:
        mapped_activities |= {"phone", "social_media", "youtube", "gaming"}
    if not mapped_activities:
        return logs
    scoped = [l for l in logs if _normalize_activity_label(str(l.get("activity_type", ""))) in mapped_activities]
    return scoped if scoped else logs


def _scope_logs_by_semantic_entity(logs: List[dict], semantic_entity: str) -> List[dict]:
    if not semantic_entity or semantic_entity in {"behavior", "behavior_pattern"}:
        return logs
    entity_map = {
        "focus_activity": {"deep_work", "study", "reading", "writing", "coding", "homework"},
        "recovery_activity": {"sleep", "nap", "rest", "break", "walk", "exercise", "workout", "yoga"},
        "stimulation_activity": {"phone", "social_media", "youtube", "gaming", "scrolling"},
        "sleep": {"sleep", "nap", "rest"},
        "exercise": {"exercise", "workout", "run", "running", "yoga", "walk"},
        "study": {"deep_work", "study", "reading", "homework"},
        "phone": {"phone", "social_media", "youtube", "gaming"},
    }
    targets = entity_map.get(semantic_entity, set())
    if not targets:
        return logs
    scoped = [l for l in logs if _normalize_activity_label(str(l.get("activity_type", ""))) in targets]
    return scoped if scoped else logs


def _looks_like_general_chat(query: str) -> bool:
    q = " ".join((query or "").lower().strip().split())
    if not q:
        return True
    # If it doesn't reference behavior categories and looks like general knowledge/help.
    behavior_tokens = {
        "sleep", "focus", "phone", "deep work", "deep-work", "habit", "loop",
        "exercise", "workout", "gym", "run", "running", "yoga", "energy",
    }
    if any(bt in q for bt in behavior_tokens):
        return False
    return any(w in q for w in ("what", "why", "how", "explain", "define", "meaning", "help"))


def orchestrator_agent(state: AgentState) -> AgentState:
    """
    Policy/orchestrator layer.
    Decides: chat vs analysis, whether causal is allowed, response style.
    """
    t0 = time.time()
    intent = state.get("parsed_intent", "general_analysis")
    intent_conf = float(state.get("intent_confidence", 0.0))
    semantic_intent = state.get("semantic_intent", "analysis")
    logs = state.get("logs", [])
    loops = state.get("loops", [])

    # Default: analysis pipeline.
    pipeline_mode = "analysis"
    response_style = "diagnostic"
    allow_causal = True

    # Conversational intents always use chat style.
    q_for_policy = state.get("normalized_query") or state.get("query", "")
    if intent in {"chat_smalltalk"} or _looks_like_general_chat(q_for_policy):
        pipeline_mode = "chat"
        response_style = "chat"
        allow_causal = False
    elif _is_improvement_query(q_for_policy):
        response_style = "improvement"

    # Universal fallback: low-confidence intent → behave like a real chatbot + ask minimal questions.
    if intent_conf < 0.45:
        pipeline_mode = "chat"
        response_style = "clarify"
        allow_causal = False

    # Query-driven orchestration: not every semantic intent should run causal analysis.
    if semantic_intent in {"lookup", "timeline", "comparison", "summary"}:
        allow_causal = False
        if response_style == "diagnostic":
            response_style = "informational"

    # Data sufficiency gating: with sparse evidence, skip causal inference (stay observational).
    signals = _extract_signals(logs, loops) if logs else {}
    n = len(logs)
    unique_days = len({str(l.get("timestamp", "")).split("T")[0] for l in logs if l.get("timestamp")})
    # Very conservative gating: causal requires some longitudinal density.
    if n < 10 or unique_days < 3:
        allow_causal = False

    ms = round((time.time() - t0) * 1000, 1)
    return {**state,
            "pipeline_mode": pipeline_mode,
            "allow_causal": allow_causal,
            "response_style": response_style,
            "agent_trace": [f"[Orchestrator] mode={pipeline_mode}, style={response_style}, allow_causal={allow_causal}, semantic_intent={semantic_intent} (intent_conf={intent_conf:.2f}, n={n}, days={unique_days}) ({ms} ms)"]}


def _sleep_duration_variability(logs: List[dict]) -> Optional[float]:
    sleep_durations = [float(l.get("duration", 0)) for l in logs if l.get("activity_type") == "sleep" and l.get("duration")]
    if len(sleep_durations) < 2:
        return None
    return max(sleep_durations) - min(sleep_durations)


def _bedtime_variability_hours(logs: List[dict]) -> Optional[float]:
    hours: List[int] = []
    for l in logs:
        if l.get("activity_type") != "sleep":
            continue
        h = _parse_hour(str(l.get("timestamp", "")))
        if h is not None:
            hours.append(h)
    if len(hours) < 2:
        return None
    return float(max(hours) - min(hours))


def _targeted_evidence(intent: str, logs_for_analysis: List[dict], loops: List[dict], window: str) -> List[str]:
    evidence: List[str] = []
    counts = Counter(l.get("activity_type", "") for l in logs_for_analysis)
    late_phone = _count_window_phone(logs_for_analysis, 22, 5)
    afternoon_phone = _count_window_phone(logs_for_analysis, 12, 18)
    sleep_var = _sleep_duration_variability(logs_for_analysis)
    bedtime_var = _bedtime_variability_hours(logs_for_analysis)
    active_loops = [l for l in loops if l.get("status") == "active"]

    def detail_count(keys: tuple[str, ...]) -> int:
        c = 0
        for l in logs_for_analysis:
            d = l.get("details") or {}
            if any(d.get(k) not in (None, "", 0, False) for k in keys):
                c += 1
        return c

    if intent in {"sleep_analysis", "sleep_cause_analysis", "sleep_now_assistance"}:
        evidence.append(f"Phone activity detected after 10 PM in {late_phone} session(s)")
        if sleep_var is not None:
            evidence.append(f"Sleep duration varied by ~{sleep_var / 60:.1f} hours across recent logs")
        if bedtime_var is not None:
            evidence.append(f"Bedtime varied by ~{bedtime_var:.1f} hours")
        evidence.append(f"Sleep telemetry entries (bedtime/wake/awakenings): {detail_count(('bedtime', 'wake_time', 'awakenings'))}")
    elif intent == "focus_analysis":
        evidence.append(f"Phone activity detected in afternoon work window in {afternoon_phone} session(s)")
        evidence.append(f"Deep-work entries logged: {counts.get('deep_work', 0)}")
        evidence.append(f"Phone-use entries logged: {counts.get('phone', 0)}")
        evidence.append(f"Interruption telemetry entries: {detail_count(('interruptions', 'interruption_source'))}")
    elif intent in {"energy_analysis", "fatigue_expression"}:
        evidence.append(f"Afternoon phone activity present in {afternoon_phone} session(s)")
        evidence.append(f"Movement entries logged: {counts.get('walk', 0) + counts.get('exercise', 0) + counts.get('workout', 0)}")
        evidence.append(f"Sleep entries available: {counts.get('sleep', 0)}")
        evidence.append(f"Trigger/outcome telemetry entries: {detail_count(('trigger', 'outcome'))}")
    elif intent == "exercise_enjoyment":
        exercise_entries = sum(counts.get(k, 0) for k in ("exercise", "workout", "walk", "run", "running", "gym", "yoga", "cycle", "cycling"))
        mood_entries = sum(1 for l in logs_for_analysis if l.get("mood") is not None)
        evidence.append(f"Exercise-related entries detected: {exercise_entries}")
        evidence.append(f"Mood-linked exercise entries available: {mood_entries}")
        evidence.append(f"Exercise telemetry entries (type/enjoyment/energy): {detail_count(('exercise_type', 'enjoyment', 'energy_before', 'energy_after'))}")
        evidence.append(f"Window analyzed: {window}")
    elif intent == "loop_analysis":
        evidence.append(f"Active loops detected: {len(active_loops)}")
        if active_loops:
            top = max(active_loops, key=lambda x: x.get("confidence", 0))
            evidence.append(
                f"Top loop: '{top.get('trigger_desc')}' → '{top.get('action_desc')}' "
                f"(confidence {top.get('confidence', 0):.0%})"
            )
        evidence.append(f"Phone-use entries logged: {counts.get('phone', 0)}")
    else:
        evidence.append(f"Logs analyzed in {window} window: {len(logs_for_analysis)}")
        evidence.append(f"Phone entries: {counts.get('phone', 0)}, deep-work entries: {counts.get('deep_work', 0)}, sleep entries: {counts.get('sleep', 0)}")
        evidence.append(f"Active loops detected: {len(active_loops)}")

    return [e for e in evidence if e]


def retriever_agent(state: AgentState) -> AgentState:
    t0   = time.time()
    logs = state.get("logs", [])
    if not logs:
        # Context is unavailable (e.g. include_context=false or cold start).
        ms = round((time.time() - t0) * 1000, 1)
        return {**state,
                "filtered_logs": [],
                "retrieved_ctx": "No behavior data available yet.",
                "retrieval_status": "empty",
                "retrieved_log_count": 0,
                "context_window": state.get("context_window", {"scope": "unknown", "start_utc": None, "end_utc": None}),
                "behavior_state": {},
                "agent_trace": [f"[Retriever] no logs available (context empty) ({ms} ms)"]}
    window = state.get("time_window", "all_day")
    ctx_window = state.get("context_window") or _resolve_context_window(state.get("query", ""), window)
    filtered_logs = _filter_logs_by_window(logs, window)
    logs_for_window = filtered_logs if filtered_logs else logs
    loops = state.get("loops", [])
    parts = []
    intent = state.get("parsed_intent", "general_analysis")
    logs_for_analysis = _scope_logs_by_intent(logs_for_window, intent)
    logs_for_analysis = _scope_logs_by_entities(logs_for_analysis, state.get("behavior_entities", []))
    logs_for_analysis = _scope_logs_by_semantic_entity(logs_for_analysis, state.get("semantic_entity", "behavior"))

    if logs_for_analysis:
        counts    = Counter(l.get("activity_type", "") for l in logs_for_analysis)
        phone_min = sum(l.get("duration", 0) for l in logs_for_analysis if l.get("activity_type") == "phone")
        dw_min    = sum(l.get("duration", 0) for l in logs_for_analysis if l.get("activity_type") == "deep_work")
        sleep_min = sum(l.get("duration", 0) for l in logs_for_analysis if l.get("activity_type") == "sleep")
        parts.append(
            f"{len(logs_for_analysis)} {window} logs: {dw_min}min deep-work, "
            f"{phone_min}min phone, {sleep_min}min sleep, "
            f"top activities={dict(counts)}"
        )

    active = [l for l in loops if l.get("status") == "active"]
    if active:
        top = max(active, key=lambda x: x.get("confidence", 0))
        parts.append(
            f"{len(active)} active loops; top: "
            f"'{top.get('trigger_desc')}' → '{top.get('action_desc')}' "
            f"({top.get('confidence', 0):.0%}, ×{top.get('occurrences', 0)})"
        )

    evidence_lines = _targeted_evidence(intent, logs_for_analysis, loops, window) if logs_for_analysis else []
    targeted = " | ".join(evidence_lines)
    retrieval_status = "success" if logs_for_analysis else "empty"

    # Canonical behavior state for downstream agents (single source of truth).
    totals = Counter()
    for l in logs_for_analysis:
        totals[str(l.get("activity_type", ""))] += int(l.get("duration", 0) or 0)
    category_totals = Counter()
    for l in logs_for_analysis:
        category_totals[_activity_category(str(l.get("activity_type", "")))] += int(l.get("duration", 0) or 0)
    transitions = Counter()
    for l in logs_for_analysis:
        d = l.get("details") or {}
        prev = d.get("previous_activity")
        if prev:
            transitions[f"{_normalize_activity_label(str(prev))}→{_normalize_activity_label(str(l.get('activity_type','')))}"] += 1

    # Loop relevance filter: only show "validated recurring loops" here.
    semantic_entity = state.get("semantic_entity", "behavior")
    active_loops = [l for l in loops if l.get("status") == "active"]
    relevant_loops = []
    for lp in active_loops:
        text = " ".join(str(lp.get(k, "")) for k in ("trigger_desc", "action_desc", "outcome_desc")).lower()
        if semantic_entity in {"phone", "sleep", "exercise", "study"} and semantic_entity not in text:
            continue
        if int(lp.get("occurrences", 0) or 0) < 3:
            continue
        if float(lp.get("confidence", 0.0) or 0.0) < 0.65:
            continue
        relevant_loops.append(lp)
    relevant_loops = sorted(relevant_loops, key=lambda x: float(x.get("confidence", 0.0) or 0.0), reverse=True)[:3]

    # Reading is not guaranteed focus — classify it using available telemetry.
    high_focus_reading = 0
    passive_reading = 0
    for l in logs_for_analysis:
        if _normalize_activity_label(str(l.get("activity_type", ""))) != "reading":
            continue
        d = l.get("details") or {}
        fs = l.get("focus_score")
        td = d.get("task_difficulty")
        # Heuristic: high-focus reading if focus_score is high or task_difficulty is high.
        if (isinstance(fs, (int, float)) and fs >= 70) or (isinstance(td, (int, float)) and td >= 6):
            high_focus_reading += 1
        else:
            passive_reading += 1

    behavior_state = {
        "context_window": ctx_window,
        "scoped_log_count": len(logs_for_analysis),
        "activity_totals_min": dict(totals),
        "category_totals_min": dict(category_totals),
        "top_transitions": [{"edge": k, "count": v} for k, v in transitions.most_common(5)],
        "validated_loops": relevant_loops,
        "reading_focus_split": {"high_focus": high_focus_reading, "passive_or_unknown": passive_reading},
    }

    ctx = (
        f"{len(logs_for_analysis)} {window} logs; "
        f"activity_totals_min={dict(totals)}; "
        f"category_totals_min={dict(category_totals)}"
    ) if logs_for_analysis else "No relevant logs matched this query yet."
    full_ctx = f"{ctx}; targeted evidence: {targeted}" if targeted else ctx
    ms  = round((time.time() - t0) * 1000, 1)
    return {**state,
            "filtered_logs": logs_for_analysis,
            "retrieved_ctx": full_ctx,
            "retrieval_status": retrieval_status,
            "retrieved_log_count": len(logs_for_analysis),
            "context_window": ctx_window,
            "behavior_state": behavior_state,
            "agent_trace": [
                f"[Retriever] fetched {len(logs_for_analysis)} scoped logs (window={window}, source_total={len(logs)}, intent={intent}) ({ms} ms)",
                f"[Retriever] evidence summary: {targeted or ctx}"
            ]}


def _confidence_label(score: float) -> str:
    if score >= 0.7:
        return "high"
    if score >= 0.45:
        return "low-to-medium"
    if score >= 0.4:
        return "medium"
    return "low"


def _intent_required_signals(intent: str) -> List[str]:
    mapping = {
        "sleep_analysis": ["sleep_logs", "late_phone", "bedtime_var_hours", "sleep_meta_logs"],
        "sleep_cause_analysis": ["sleep_logs", "late_phone", "bedtime_var_hours", "sleep_meta_logs"],
        "sleep_now_assistance": ["sleep_logs"],
        "focus_analysis": ["deep_work_logs", "phone_logs", "active_loop_count", "interruption_logs", "transition_logs"],
        "energy_analysis": ["afternoon_phone", "movement_logs", "sleep_logs", "outcome_logs"],
        "fatigue_expression": ["sleep_logs", "movement_logs"],
        "loop_analysis": ["active_loop_count", "phone_logs"],
        "exercise_enjoyment": ["exercise_logs", "mood_logs", "exercise_meta_logs", "outcome_logs"],
        "general_analysis": ["phone_logs", "deep_work_logs", "sleep_logs"],
    }
    return mapping.get(intent, ["phone_logs", "deep_work_logs", "sleep_logs"])


def _compute_confidence(intent: str, query: str, logs: List[dict], loops: List[dict], signals: dict) -> tuple[float, str, str, dict]:
    n = len(logs)
    if n == 0:
        components = {
            "retrieval_quality": 0.10,
            "data_sufficiency": 0.10,
            "causal_certainty": 0.10,
            "recommendation_confidence": 0.20,
        }
        return 0.15, "low", "no logs available", components

    unique_days = len({
        str(l.get("timestamp", "")).split("T")[0]
        for l in logs if l.get("timestamp")
    })
    counts = Counter(l.get("activity_type", "") for l in logs)
    present_core = sum(1 for k in ("phone", "deep_work", "sleep") if k in counts)
    required = _intent_required_signals(intent)
    matched = sum(1 for key in required if signals.get(key) not in (None, 0, "", False))
    signal_relevance = matched / max(len(required), 1)

    # Completeness: are we seeing rich attributes beyond activity_type?
    # (e.g., timestamps, duration, mood, focus_score)
    rich_fields = ("timestamp", "duration", "mood", "focus_score")
    rich_hits = 0
    rich_total = 0
    for l in logs:
        for f in rich_fields:
            rich_total += 1
            if l.get(f) not in (None, "", 0):
                rich_hits += 1
    signal_completeness = (rich_hits / rich_total) if rich_total else 0.0

    retrieval_quality = min(0.10 + signal_relevance * 0.55 + signal_completeness * 0.35, 0.90)

    sample_score = min(n / 30.0, 1.0)
    temporal_coverage = min(unique_days / 14.0, 1.0)
    diversity = min(len(counts) / 8.0, 1.0)
    data_sufficiency = min(sample_score * 0.55 + temporal_coverage * 0.35 + diversity * 0.10, 0.90)

    evidence_strength = min((retrieval_quality * 0.6) + (min(len(loops), 5) / 5.0) * 0.15 + (present_core / 3.0) * 0.25, 0.90)
    causal_certainty = min(evidence_strength * data_sufficiency + 0.10, 0.90)
    recommendation_confidence = min(0.20 + retrieval_quality * 0.35 + causal_certainty * 0.45, 0.90)
    score = min(
        retrieval_quality * 0.20 +
        data_sufficiency * 0.35 +
        causal_certainty * 0.30 +
        recommendation_confidence * 0.15,
        0.90
    )

    # Guardrails: never claim high certainty on sparse logs.
    if n < 8:
        score = min(score, 0.45)
    elif n < 15:
        score = min(score, 0.60)
    if intent in {"sleep_analysis", "sleep_cause_analysis"} and int(signals.get("sleep_logs", 0)) < 3:
        score = min(score, 0.42)

    # Small deterministic jitter prevents visibly repeated scores while staying stable per query+evidence.
    seed = sum(ord(ch) for ch in (query or "")) + n + unique_days + int(signals.get("active_loop_count", 0))
    jitter = ((seed % 9) - 4) * 0.005
    score = min(max(score + jitter, 0.05), 0.90)

    label = _confidence_label(score)
    reason = f"{n} logs across {max(unique_days, 1)} day(s)"
    if present_core < 3:
        reason += ", partial behavior coverage"
    components = {
        "retrieval_quality": retrieval_quality,
        "signal_relevance": signal_relevance,
        "signal_completeness": signal_completeness,
        "temporal_coverage": temporal_coverage,
        "data_sufficiency": data_sufficiency,
        "causal_certainty": min(causal_certainty, score + 0.10),
        "recommendation_confidence": min(recommendation_confidence, max(score, 0.20) + 0.20),
    }
    return score, label, reason, components


def _count_window_phone(logs: List[dict], start_hour: int, end_hour: int) -> int:
    hits = 0
    for l in logs:
        if l.get("activity_type") != "phone":
            continue
        h = _parse_hour(str(l.get("timestamp", "")))
        if h is None:
            continue
        if start_hour <= end_hour:
            if start_hour <= h < end_hour:
                hits += 1
        else:
            if h >= start_hour or h < end_hour:
                hits += 1
    return hits


def _extract_signals(logs: List[dict], loops: List[dict]) -> dict:
    counts = Counter(l.get("activity_type", "") for l in logs)
    sleep_var = _sleep_duration_variability(logs)
    bedtime_var = _bedtime_variability_hours(logs)
    active_loops = [l for l in loops if l.get("status") == "active"]
    def detail_count(keys: tuple[str, ...]) -> int:
        c = 0
        for l in logs:
            d = l.get("details") or {}
            if any(d.get(k) not in (None, "", 0, False) for k in keys):
                c += 1
        return c

    return {
        "phone_logs": counts.get("phone", 0),
        "sleep_logs": counts.get("sleep", 0),
        "deep_work_logs": counts.get("deep_work", 0),
        "late_phone": _count_window_phone(logs, 22, 5),
        "afternoon_phone": _count_window_phone(logs, 12, 18),
        "movement_logs": sum(counts.get(k, 0) for k in ("walk", "exercise", "workout")),
        "sleep_var_hours": (sleep_var / 60.0) if sleep_var is not None else None,
        "bedtime_var_hours": bedtime_var,
        "active_loop_count": len(active_loops),
        "exercise_logs": sum(counts.get(k, 0) for k in ("exercise", "workout", "walk", "run", "running", "gym", "yoga", "cycle", "cycling")),
        "mood_logs": sum(1 for l in logs if l.get("mood") is not None),
        "transition_logs": detail_count(("previous_activity", "next_activity")),
        "trigger_logs": detail_count(("trigger",)),
        "outcome_logs": detail_count(("outcome",)),
        "interruption_logs": detail_count(("interruptions", "interruption_source")),
        "sleep_meta_logs": detail_count(("bedtime", "wake_time", "awakenings")),
        "exercise_meta_logs": detail_count(("exercise_type", "enjoyment", "energy_before", "energy_after")),
        "phone_meta_logs": detail_count(("phone_purpose", "intended_duration")),
    }


def _has_signal(signals: dict, key: str) -> bool:
    value = signals.get(key)
    return value not in (None, 0, "", False)


def _is_improvement_query(query: str) -> bool:
    q = " ".join((query or "").lower().strip().split())
    if not q:
        return False
    return any(
        phrase in q
        for phrase in (
            "how can i", "how do i", "help me", "improve", "get better",
            "want enjoy", "enjoy", "make it enjoyable", "optimize",
            "what should i do", "tips", "advice",
        )
    )


def _repeatability_note(relevant_events: int) -> str:
    if relevant_events >= 3:
        return "Observed repeatedly across recent logs, but more data is needed for high-confidence inference."
    return "Only limited relevant history is available, so stable patterns cannot yet be verified."


def _missing_signals(intent: str) -> List[str]:
    if intent == "exercise_enjoyment":
        return [
            "Workout duration",
            "Energy before exercise",
            "Enjoyment after exercise (1–10)",
            "Type of exercise",
            "Solo vs group context",
        ]
    if intent in {"sleep_analysis", "sleep_cause_analysis"}:
        return [
            "Bedtime + wake time",
            "Sleep quality rating (1–10)",
            "Caffeine / late meals",
            "Late-night screen exposure detail",
            "Night awakenings",
        ]
    if intent == "focus_analysis":
        return [
            "Session start/end times",
            "Distraction trigger type",
            "Task switch count",
            "Environment (location/noise)",
            "Planned vs unplanned work blocks",
        ]
    return ["Consistent timestamps", "Mood/energy rating around the event"]


def _build_hypotheses(intent: str, logs: List[dict], loops: List[dict]) -> List[Tuple[str, str]]:
    s = _extract_signals(logs, loops)
    phone_logs = int(s["phone_logs"])
    sleep_logs = int(s["sleep_logs"])
    deep_work_logs = int(s["deep_work_logs"])
    late_phone = int(s["late_phone"])
    afternoon_phone = int(s["afternoon_phone"])
    movement_logs = int(s["movement_logs"])
    active_loop_count = int(s["active_loop_count"])

    if intent == "focus_analysis":
        hypotheses: List[Tuple[str, str]] = []
        if _has_signal(s, "phone_logs"):
            hypotheses.append(("Phone interruptions during work blocks", "medium"))
        if _has_signal(s, "deep_work_logs") and deep_work_logs <= phone_logs:
            hypotheses.append(("Fragmented deep-work routine", "low-to-medium"))
        if movement_logs == 0:
            hypotheses.append(("Energy dip from low movement breaks", "low-to-medium"))
        if active_loop_count == 0:
            hypotheses.append(("No stable productivity loop detected yet", "low"))
        if not hypotheses:
            hypotheses.append(("Insufficient focus-session evidence for stable contributors", "low"))
        return hypotheses
    if intent in {"sleep_analysis", "sleep_cause_analysis"}:
        hypotheses = []
        if late_phone > 0:
            hypotheses.append(("Late-night screen exposure", "medium"))
        if sleep_logs >= 3:
            hypotheses.append(("Irregular sleep schedule", "medium"))
        elif sleep_logs > 0:
            hypotheses.append(("Sleep schedule consistency is still unclear", "low"))
        hypotheses.append(("Low daytime physical fatigue", "medium" if movement_logs == 0 else "low"))
        if not hypotheses:
            hypotheses.append(("Insufficient sleep-history evidence for stable contributors", "low"))
        return hypotheses
    if intent == "sleep_now_assistance":
        return [
            ("Mental overstimulation close to bedtime", "medium"),
            ("Difficulty winding down from recent activity", "medium"),
            ("Acute stress carryover", "low-to-medium"),
        ]
    if intent == "fatigue_expression":
        return [
            ("Energy depletion from low recovery", "medium"),
            ("Workload-fatigue mismatch", "low-to-medium"),
            ("Possible sleep debt accumulation", "low-to-medium"),
        ]
    if intent == "emotional_distress":
        return [
            ("Elevated stress load", "medium"),
            ("Emotional fatigue spillover into routines", "low-to-medium"),
            ("Limited evidence for stable behavioral drivers", "low"),
        ]
    if intent == "exercise_enjoyment":
        hypotheses = []
        exercise_logs = int(s.get("exercise_logs", 0))
        mood_logs = int(s.get("mood_logs", 0))
        if exercise_logs < 2:
            hypotheses.append(("Insufficient exercise-history density to estimate stable enjoyment patterns", "low"))
        else:
            hypotheses.append(("Exercise style may not match natural preference", "low-to-medium"))
        if mood_logs == 0:
            hypotheses.append(("No mood-after-exercise signal available yet", "low"))
        if exercise_logs > 0:
            hypotheses.append(("Inconsistent routine may reduce perceived reward", "low-to-medium"))
        return hypotheses
    if intent == "energy_analysis":
        hypotheses = []
        if afternoon_phone > 0:
            hypotheses.append(("Post-lunch behavioral drift", "medium"))
        if movement_logs == 0:
            hypotheses.append(("Low movement before afternoon blocks", "low-to-medium"))
        if sleep_logs >= 3:
            hypotheses.append(("Carryover from sleep inconsistency", "low-to-medium"))
        if not hypotheses:
            hypotheses.append(("Insufficient energy-related evidence for stable contributors", "low"))
        return hypotheses
    if intent == "loop_analysis":
        active = [l for l in loops if l.get("status") == "active"]
        return [
            ("Recurring trigger-action cycle in logs", "medium" if active else "low"),
            ("Phone-first coping response under friction", "medium" if phone_logs else "low"),
            ("Weak routine anchors across days", "low"),
        ]
    # Generic ontology-driven reasoning path (non-domain hardcoded).
    transition_count = 0
    for l in logs:
        d = l.get("details") or {}
        if d.get("previous_activity"):
            transition_count += 1
    focus_like = sum(1 for l in logs if _activity_category(str(l.get("activity_type", ""))) == "focus_activity")
    stim_like = sum(1 for l in logs if _activity_category(str(l.get("activity_type", ""))) == "stimulation_activity")
    recovery_like = sum(1 for l in logs if _activity_category(str(l.get("activity_type", ""))) == "recovery_activity")

    hypotheses = []
    if transition_count > 0 and stim_like >= focus_like:
        hypotheses.append(("Frequent transitions away from sustained-focus activities were detected", "low-to-medium"))
    if recovery_like == 0:
        hypotheses.append(("Your logs show very few breaks or recovery periods between focus activities", "low-to-medium"))
    if focus_like == 0 and stim_like > 0:
        hypotheses.append(("Stimulation-heavy activity mix may be crowding focused tasks", "low"))
    if not hypotheses:
        hypotheses.append(("Insufficient cross-activity transition signal for stable contributors", "low"))
    return hypotheses


def _format_analysis(intent: str, query: str, window: str, logs: List[dict], loops: List[dict], retrieved_ctx: str) -> tuple[str, float, str, dict]:
    if not logs:
        # When there's no data, behave like a normal chatbot first:
        # answer generally, then ask for minimal signals to personalize.
        missing_block = "\n".join(f"- {m}" for m in _missing_signals(intent))
        msg = (
            "I can help with that.\n\n"
            "I don't have your behavior history yet, so I can't verify personal patterns — "
            "but I *can* give practical next steps now.\n\n"
            "Quick questions (optional, 1–2 lines each):\n"
            "1. When does this usually happen (morning/afternoon/night)?\n"
            "2. What does it look like for you (examples)?\n"
            "3. What outcome do you want in the next 24 hours?\n\n"
            "Additional signals that would improve analysis:\n"
            f"{missing_block}\n\n"
            "If you start logging even 3–5 entries, I can begin producing evidence-based, "
            "confidence-calibrated insights."
        )
        return msg, 0.15, "no logs available", {
            "retrieval_quality": 0.10,
            "data_sufficiency": 0.10,
            "causal_certainty": 0.10,
            "recommendation_confidence": 0.20,
        }

    signals = _extract_signals(logs, loops)
    score, label, reason, components = _compute_confidence(intent, query, logs, loops, signals)
    hypotheses = _build_hypotheses(intent, logs, loops)
    ranked = "\n".join(
        f"{idx}. {name} ({conf} confidence)"
        for idx, (name, conf) in enumerate(hypotheses, start=1)
    )
    if intent == "exercise_enjoyment":
        relevant_events = int(signals.get("exercise_logs", 0))
    elif intent in {"sleep_analysis", "sleep_cause_analysis"}:
        relevant_events = int(signals.get("sleep_logs", 0))
    elif intent == "focus_analysis":
        relevant_events = int(signals.get("deep_work_logs", 0))
    else:
        relevant_events = len(logs)
    observed = _repeatability_note(relevant_events)
    missing_block = "\n".join(f"- {m}" for m in _missing_signals(intent))
    if intent == "sleep_now_assistance":
        analysis = (
            "You may be mentally overstimulated or unable to wind down right now.\n\n"
            "Try now:\n"
            "1. Put the phone away for 15-20 minutes\n"
            "2. Reduce bright light and noise\n"
            "3. Avoid mentally demanding work right now\n"
            "4. Keep the room cool and quiet\n\n"
            f"Evidence used: {retrieved_ctx}\n"
            "I do not yet have enough behavioral history to confidently identify a long-term sleep pattern."
        )
    elif intent == "emotional_distress":
        analysis = (
            "This sounds emotionally heavy. I can help with immediate stabilization first.\n\n"
            "Try now:\n"
            "1. Pause and take 10 slow breaths\n"
            "2. Reduce stimulation for the next 10 minutes\n"
            "3. Reach out to someone you trust if you need support\n\n"
            f"Evidence used: {retrieved_ctx}\n"
            f"Model confidence for long-term inference: {label} ({score:.2f})"
        )
    else:
        heading = "Early optimization opportunities" if _is_improvement_query(query) else "Possible contributors"
        analysis = (
            f"{heading} ({window} window):\n"
            f"{ranked}\n\n"
            f"Evidence used: {retrieved_ctx}\n"
            f"{observed}\n"
            f"Model confidence: {label} ({score:.2f})\n\n"
            "Additional signals that would improve analysis:\n"
            f"{missing_block}\n\n"
            "Confidence breakdown:\n"
            f"- Signal relevance: {components.get('signal_relevance', 0.0):.2f}\n"
            f"- Signal completeness: {components.get('signal_completeness', 0.0):.2f}\n"
            f"- Temporal coverage: {components.get('temporal_coverage', 0.0):.2f}\n"
            f"- Retrieval quality: {components['retrieval_quality']:.2f}\n"
            f"- Data sufficiency: {components['data_sufficiency']:.2f}\n"
            f"- Causal certainty: {components['causal_certainty']:.2f}\n"
            f"- Recommendation confidence: {components['recommendation_confidence']:.2f}"
        )
        if intent == "focus_analysis" and int(signals["active_loop_count"]) == 0:
            analysis += (
                "\n\nI do not yet detect a stable productivity loop from your logs.\n"
                "Possible early signals: inconsistent deep-work tracking, limited focus-session evidence, and sparse activity history."
            )
    return analysis, score, reason, components


def causal_agent(state: AgentState) -> AgentState:
    t0     = time.time()
    intent = state["parsed_intent"]
    window = state.get("time_window", "all_day")
    filtered_logs = state.get("filtered_logs", [])

    base = "Hi! I can analyze your behavior trace for focus, sleep, loops, and likely causes."
    if intent == "chat_smalltalk":
        ms = round((time.time() - t0) * 1000, 1)
        return {**state,
                "causal_analysis": base,
                "confidence": 1.0,
                "agent_trace": [f"[Causal] conversational response generated ({ms} ms)"]}

    if state.get("pipeline_mode") == "chat":
        ms = round((time.time() - t0) * 1000, 1)
        msg = (
            "I can help with that. What would you like to know?\n\n"
            "If you want a behavior-trace answer, ask about sleep, focus, exercise, energy, or loops."
        )
        return {**state,
                "causal_analysis": msg,
                "confidence": 0.3,
                "agent_trace": [f"[Causal] general chat response (no analysis) ({ms} ms)"]}

    ctx = state.get("retrieved_ctx", "")
    analysis, conf, conf_reason, conf_components = _format_analysis(
        intent=intent,
        query=state.get("query", ""),
        window=window,
        logs=filtered_logs,
        loops=state.get("loops", []),
        retrieved_ctx=ctx,
    )
    if state.get("allow_causal") is False:
        # Replace causal framing with observation-only framing when policy disallows causal inference.
        analysis = analysis.replace("Causal certainty", "Causal certainty (skipped/limited)")

    # Trace reasoning add-on: surface transitions + telemetry availability (observability-style).
    bs = state.get("behavior_state", {}) or {}
    transitions = bs.get("top_transitions", []) or []
    reading_split = bs.get("reading_focus_split", {}) or {}
    interruption_logs = _extract_signals(filtered_logs, state.get("loops", [])).get("interruption_logs", 0) if filtered_logs else 0

    if transitions or interruption_logs or reading_split:
        lines = []
        if transitions:
            top = transitions[:3]
            lines.append("Observed transitions:")
            for t in top:
                edge = t.get("edge")
                count = t.get("count")
                if edge and count is not None:
                    lines.append(f"- {edge} (×{count})")
        if interruption_logs == 0 and intent in {"focus_analysis"}:
            lines.append("Interruption telemetry: none logged yet (can’t confirm interruption-driven focus loss).")
        if reading_split:
            hf = int(reading_split.get("high_focus", 0) or 0)
            pu = int(reading_split.get("passive_or_unknown", 0) or 0)
            if hf + pu > 0:
                lines.append(f"Reading focus signal: high-focus={hf}, passive/unknown={pu} (reading isn’t guaranteed deep focus).")
        analysis = analysis + "\n\n" + "\n".join(lines)
    ms     = round((time.time() - t0) * 1000, 1)
    return {**state,
            "causal_analysis": analysis,
            "confidence":      conf,
            "agent_trace": [
                f"[Causal] competing hypotheses ranked for intent='{intent}'",
                f"[Causal] confidence calibration: {conf:.2f} ({conf_reason})",
                f"[Causal] confidence breakdown: retrieval={conf_components['retrieval_quality']:.2f}, data={conf_components['data_sufficiency']:.2f}, causal={conf_components['causal_certainty']:.2f}, recommendation={conf_components['recommendation_confidence']:.2f}",
                f"[Causal] uncertainty-first narrative generated ({ms} ms)",
            ]}


def _generate_fixes(intent: str, logs: List[dict], loops: List[dict], confidence: float) -> str:
    s = _extract_signals(logs, loops)
    late_phone = int(s["late_phone"])
    bedtime_var = s["bedtime_var_hours"]
    active_loop_count = int(s["active_loop_count"])

    if intent == "chat_smalltalk":
        return (
            "Ask me something like:\n"
            "1. Why does my focus drop in the afternoon?\n"
            "2. What loop hurts my productivity the most?\n"
            "3. Which habit change would improve sleep this week?"
        )
    if intent == "sleep_now_assistance":
        return (
            "Immediate sleep assistance:\n"
            "1. Keep your phone away for 20 minutes\n"
            "2. Dim lights and reduce noise\n"
            "3. Try slow breathing or a short body-scan\n"
            "4. If still awake, avoid forcing sleep and stay in a calm routine"
        )
    if intent in {"sleep_analysis", "sleep_cause_analysis"}:
        recs = ["1. Track sleep quality and bedtime for 7-14 days"]
        idx = 2
        if late_phone > 0:
            recs.append(f"{idx}. Add a gentle screen cutoff before bedtime")
            idx += 1
        if bedtime_var is not None and bedtime_var >= 1.0:
            recs.append(f"{idx}. Stabilize bedtime within a 45-minute window")
            idx += 1
        if late_phone == 0 and (bedtime_var is None or bedtime_var < 1.0):
            recs.append(f"{idx}. Keep current routine and collect more logs before changing sleep strategy")
        return "Recommended sleep actions:\n" + "\n".join(recs)
    if intent == "focus_analysis":
        if active_loop_count == 0:
            return (
                "Exploratory guidance (no stable loop detected yet):\n"
                "1. Log at least 5 focused work sessions this week\n"
                "2. Capture exact distraction triggers when focus breaks\n"
                "3. Start with 20-25 minute deep-work blocks"
            )
        return (
            "Recommended focus actions:\n"
            "1. Use protected 25-minute focus blocks\n"
            "2. Add friction before distracting apps\n"
            "3. Review trigger patterns daily"
        )
    if intent == "exercise_enjoyment":
        exercise_logs = int(s.get("exercise_logs", 0))
        mood_logs = int(s.get("mood_logs", 0))
        recs = []
        recs.append("1. Track post-exercise enjoyment (1-10) after each session")
        recs.append("2. Experiment with different exercise styles before increasing intensity")
        if exercise_logs < 3:
            recs.append("3. Build consistency first with short, repeatable workouts")
        if mood_logs == 0:
            recs.append("4. Log mood before and after exercise to identify rewarding patterns")
        return "Recommended exercise-enjoyment actions:\n" + "\n".join(recs)
    if intent in {"fatigue_expression", "energy_analysis"}:
        return (
            "Recommended energy actions:\n"
            "1. Add a short movement break before heavy work\n"
            "2. Reduce post-lunch cognitive load\n"
            "3. Track energy at fixed times for one week"
        )
    if confidence < 0.5:
        return (
            "Recommendations are exploratory due to limited confidence:\n"
            "1. Improve logging consistency for 10-14 days\n"
            "2. Run one small behavior experiment at a time\n"
            "3. Re-check after new data accumulates"
        )
    return (
        "General recommendations:\n"
        "1. Keep activity logging consistent\n"
        "2. Change one behavior at a time\n"
        "3. Reassess trends with updated evidence"
    )


def fixer_agent(state: AgentState) -> AgentState:
    t0  = time.time()
    fix = _generate_fixes(
        intent=state["parsed_intent"],
        logs=state.get("filtered_logs", []),
        loops=state.get("loops", []),
        confidence=state.get("confidence", 0.0),
    )
    ms  = round((time.time() - t0) * 1000, 1)
    return {**state,
            "fix_suggestion": fix,
            "tokens_used":    850,
            "agent_trace": [f"[Fixer] evidence-gated strategies generated ({ms} ms)"]}


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=0.6, min=0.6, max=3))
async def _openai_json(system: str, user: str) -> dict:
    settings = get_settings()
    if not settings.AZURE_OPENAI_API_KEY or not settings.AZURE_OPENAI_ENDPOINT:
        raise RuntimeError("Azure OpenAI is not configured")
    try:
        from openai import AsyncAzureOpenAI
    except Exception as e:
        raise RuntimeError("OpenAI SDK not installed") from e

    if not isinstance(system, str) or not system.strip():
        raise RuntimeError("Invalid writer payload: empty system message")
    if not isinstance(user, str) or not user.strip():
        raise RuntimeError("Invalid writer payload: empty user message")

    # Conservative payload cap to avoid oversized context in Azure request.
    max_user_chars = 18000
    if len(user) > max_user_chars:
        user = user[:max_user_chars]

    # Very rough estimate (chars/4) for diagnostics only.
    approx_tokens = int((len(system) + len(user)) / 4)

    client = AsyncAzureOpenAI(
        api_key=settings.AZURE_OPENAI_API_KEY,
        azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
        api_version=settings.AZURE_OPENAI_API_VERSION,
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    logger.info({
        "agent": "writer",
        "provider": "azure_openai",
        "deployment": settings.azure_openai_deployment_name,
        "api_version": settings.AZURE_OPENAI_API_VERSION,
        "message_count": len(messages),
        "approx_tokens": approx_tokens,
        "payload_preview": {
            "system": system[:220],
            "user": user[:320],
        },
    })

    try:
        # Preferred path: ask model for JSON object.
        resp = await client.chat.completions.create(
            model=settings.azure_openai_deployment_name,
            temperature=settings.OPENAI_TEMPERATURE,
            messages=messages,
            response_format={"type": "json_object"},
        )
        content = (resp.choices[0].message.content or "").strip()
        return json.loads(content or "{}")
    except Exception as first_error:
        # Azure deployments can reject response_format depending on model/api version.
        logger.warning(f"Writer structured response failed: {first_error}")
        resp = await client.chat.completions.create(
            model=settings.azure_openai_deployment_name,
            temperature=settings.OPENAI_TEMPERATURE,
            messages=messages,
        )
        content = (resp.choices[0].message.content or "").strip()
        if not content:
            raise RuntimeError("Azure writer returned empty content")
        try:
            return json.loads(content)
        except Exception:
            # Last-resort wrapper if model returned plain text.
            return {"cause": content, "suggestion": ""}


async def writer_agent(state: AgentState) -> AgentState:
    """
    Uses OpenAI to produce a more ChatGPT-like response while being strictly
    evidence- and confidence-bound. Falls back silently if OpenAI is unavailable.
    """
    t0 = time.time()
    settings = get_settings()
    if not settings.AZURE_OPENAI_API_KEY or not settings.AZURE_OPENAI_ENDPOINT:
        ms = round((time.time() - t0) * 1000, 1)
        return {**state, "agent_trace": [f"[Writer] skipped (Azure OpenAI not configured) ({ms} ms)"]}

    intent = state.get("parsed_intent", "general_analysis")
    window = state.get("time_window", "all_day")
    ctx = state.get("retrieved_ctx", "")
    conf = float(state.get("confidence", 0.0))
    intent_conf = float(state.get("intent_confidence", 0.0))
    style = state.get("response_style", "diagnostic")
    retrieval_status = state.get("retrieval_status", "unknown")
    retrieved_log_count = int(state.get("retrieved_log_count", 0))
    behavior_state = state.get("behavior_state", {}) or {}
    draft_analysis = state.get("causal_analysis", "")
    draft_fixes = state.get("fix_suggestion", "")
    if not isinstance(draft_analysis, str):
        draft_analysis = str(draft_analysis or "")
    if not isinstance(draft_fixes, str):
        draft_fixes = str(draft_fixes or "")

    system = (
        "You are TRACE_PD, a behavior observability + debugging assistant. "
        "Be helpful, natural, and non-templated. "
        "If user data is missing/sparse, still respond like a normal helpful chatbot, "
        "then ask 1-3 minimal clarifying questions to personalize. "
        "Do NOT invent evidence. You must stay consistent with the Evidence used. "
        "Never claim you 'don't have access to the user's data' unless retrieval_status is 'failed' or 'skipped'. "
        "If behavior_state.activity_totals_min exists, treat it as canonical and do not contradict it. "
        "Never claim p-values, R^2, or causal certainty beyond the provided confidence. "
        "If the data is sparse, say so. Keep it concise."
    )
    user = json.dumps({
        "query": state.get("query", ""),
        "normalized_query": state.get("normalized_query", ""),
        "intent": intent,
        "intent_confidence": intent_conf,
        "semantic_entity": state.get("semantic_entity", "behavior"),
        "semantic_intent": state.get("semantic_intent", "analysis"),
        "semantic_metric": state.get("semantic_metric", "general_behavior"),
        "response_style": style,
        "time_window": window,
        "confidence": conf,
        "retrieval_status": retrieval_status,
        "retrieved_log_count": retrieved_log_count,
        "behavior_state": behavior_state,
        "evidence_used": ctx,
        "guardrailed_analysis_draft": draft_analysis,
        "guardrailed_recommendations_draft": draft_fixes,
        "output_schema": {
            "cause": "string (final assistant analysis/narrative)",
            "suggestion": "string (final next steps / recommendations)",
        }
    }, ensure_ascii=False)

    try:
        out = await _openai_json(system=system, user=user)
        cause = str(out.get("cause", "")).strip() or draft_analysis
        suggestion = str(out.get("suggestion", "")).strip() or draft_fixes
        ms = round((time.time() - t0) * 1000, 1)
        return {**state,
                "causal_analysis": cause,
                "fix_suggestion": suggestion,
                "agent_trace": [f"[Writer] Azure OpenAI response generated ({ms} ms)"]}
    except Exception as e:
        ms = round((time.time() - t0) * 1000, 1)
        logger.exception(f"Writer agent fallback: {e}")
        return {**state, "agent_trace": [f"[Writer] fallback (Azure OpenAI unavailable) ({ms} ms)"]}


# ── Build / run ───────────────────────────────────────────
def _build_graph():
    if not _HAS_LANGGRAPH:
        return None
    g = StateGraph(AgentState)
    for name, fn in [("parser", parser_agent), ("orchestrator", orchestrator_agent), ("retriever", retriever_agent),
                     ("causal", causal_agent), ("fixer", fixer_agent), ("writer", writer_agent)]:
        g.add_node(name, fn)
    g.set_entry_point("parser")
    g.add_edge("parser",    "orchestrator")
    g.add_edge("orchestrator", "retriever")
    g.add_edge("retriever", "causal")
    g.add_edge("causal",    "fixer")
    g.add_edge("fixer",     "writer")
    g.add_edge("writer",    END)
    return g.compile()


async def run_debug_pipeline(query: str, user_id: str,
                              logs: list, loops: list,
                              include_context: bool = True) -> dict:
    init: AgentState = {
        "query": query, "user_id": user_id,
        "normalized_query": "",
        "logs": logs if include_context else [], "loops": loops if include_context else [],
        "filtered_logs": [],
        "parsed_intent": "", "intent_confidence": 0.0, "behavior_entities": [],
        "semantic_entity": "behavior", "semantic_intent": "analysis", "semantic_metric": "general_behavior",
        "retrieved_ctx": "",
        "retrieval_status": "unknown",
        "retrieved_log_count": 0,
        "context_window": {"scope": "unknown", "start_utc": None, "end_utc": None},
        "behavior_state": {},
        "time_window": "all_day", "query_hour_hint": None,
        "causal_analysis": "", "fix_suggestion": "",
        "pipeline_mode": "analysis",
        "allow_causal": True,
        "response_style": "diagnostic",
        "agent_trace": ["[Orchestrator] pipeline started"],
        "tokens_used": 0, "confidence": 0.0,
    }

    app = _build_graph()
    if app:
        final = await app.ainvoke(init)
    else:
        s = parser_agent(init)
        s = orchestrator_agent(s)
        s = retriever_agent(s)
        s = causal_agent(s)
        s = fixer_agent(s)
        s = await writer_agent(s)
        final = s

    final["agent_trace"].append("[Orchestrator] pipeline complete ✓")
    return {
        "cause":       final["causal_analysis"],
        "suggestion":  final["fix_suggestion"],
        "confidence":  final["confidence"],
        "agent_trace": final["agent_trace"],
        "tokens_used": final["tokens_used"],
    }
