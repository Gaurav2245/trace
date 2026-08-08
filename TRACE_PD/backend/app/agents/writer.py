"""
Writer agent: turns the guardrailed analysis/fix drafts from earlier agents
into a natural-language response via Azure OpenAI, falling back silently
(returning the drafts unchanged) when Azure OpenAI isn't configured.
Self-contained — only touches AgentState and app settings, so it's the one
part of the pipeline that doesn't share state with the classification/
evidence helpers in pipeline.py.
"""
import json
import time
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.agents.state import AgentState


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=0.6, min=0.6, max=3))
async def _openai_json(system: str, user: str) -> tuple[dict, int]:
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
        tokens = resp.usage.total_tokens if resp.usage else approx_tokens
        return json.loads(content or "{}"), tokens
    except Exception as first_error:
        # Azure deployments can reject response_format depending on model/api version.
        logger.warning(f"Writer structured response failed: {first_error}")
        resp = await client.chat.completions.create(
            model=settings.azure_openai_deployment_name,
            temperature=settings.OPENAI_TEMPERATURE,
            messages=messages,
        )
        content = (resp.choices[0].message.content or "").strip()
        tokens = resp.usage.total_tokens if resp.usage else approx_tokens
        if not content:
            raise RuntimeError("Azure writer returned empty content")
        try:
            return json.loads(content), tokens
        except Exception:
            # Last-resort wrapper if model returned plain text.
            return {"cause": content, "suggestion": ""}, tokens


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
        out, tokens = await _openai_json(system=system, user=user)
        cause = str(out.get("cause", "")).strip() or draft_analysis
        suggestion = str(out.get("suggestion", "")).strip() or draft_fixes
        ms = round((time.time() - t0) * 1000, 1)
        return {**state,
                "causal_analysis": cause,
                "fix_suggestion": suggestion,
                "tokens_used": tokens,
                "agent_trace": [f"[Writer] Azure OpenAI response generated ({ms} ms)"]}
    except Exception as e:
        ms = round((time.time() - t0) * 1000, 1)
        logger.exception(f"Writer agent fallback: {e}")
        return {**state, "agent_trace": [f"[Writer] fallback (Azure OpenAI unavailable) ({ms} ms)"]}
