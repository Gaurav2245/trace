from typing import TypedDict, List, Annotated, Optional
import operator


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
