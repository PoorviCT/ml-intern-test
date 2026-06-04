"""Shared utilities and constants for routes."""

import logging
from typing import Any

from fastapi import HTTPException, Request

from dependencies import require_huggingface_org_member
import user_quotas
from session_manager import AgentSession, session_manager

logger = logging.getLogger(__name__)

AVAILABLE_MODELS = [
    {
        "id": "moonshotai/Kimi-K2.6",
        "label": "Kimi K2.6",
        "provider": "huggingface",
        "tier": "free",
        "recommended": True,
    },
    {
        "id": "bedrock/us.anthropic.claude-opus-4-6-v1",
        "label": "Claude Opus 4.6",
        "provider": "anthropic",
        "tier": "pro",
        "recommended": True,
    },
    {
        "id": "MiniMaxAI/MiniMax-M2.7",
        "label": "MiniMax M2.7",
        "provider": "huggingface",
        "tier": "free",
    },
    {
        "id": "zai-org/GLM-5.1",
        "label": "GLM 5.1",
        "provider": "huggingface",
        "tier": "free",
    },
]


def _is_anthropic_model(model_id: str) -> bool:
    return "anthropic" in model_id


async def _require_hf_for_anthropic(request: Request, model_id: str) -> None:
    """403 if a non-``huggingface``-org user tries to select an Anthropic model.

    Anthropic models are billed to the Space's ``ANTHROPIC_API_KEY``; every
    other model in ``AVAILABLE_MODELS`` is routed through HF Router and
    billed via ``X-HF-Bill-To``. The gate only fires for Anthropic so
    non-HF users can still freely switch between the free models.
    """
    if not _is_anthropic_model(model_id):
        return
    if not await require_huggingface_org_member(request):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "anthropic_restricted",
                "message": (
                    "Opus is gated to HF staff. Pick a free model — "
                    "Kimi K2.6, MiniMax M2.7, or GLM 5.1 — instead."
                ),
            },
        )


async def _enforce_claude_quota(
    user: dict[str, Any],
    agent_session: AgentSession,
) -> None:
    """Charge the user's daily Claude quota on first use of Anthropic in a session.

    Runs at *message-submit* time, not session-create time — so spinning up a
    Claude session to look around doesn't burn quota. The ``claude_counted``
    flag on ``AgentSession`` guards against re-counting the same session.

    No-ops when the session's current model isn't Anthropic, or when this
    session has already been charged. Raises 429 when the user has hit
    their daily cap.
    """
    if agent_session.claude_counted:
        return
    model_name = agent_session.session.config.model_name
    if not _is_anthropic_model(model_name):
        return
    user_id = user["user_id"]
    used = await user_quotas.get_claude_used_today(user_id)
    cap = user_quotas.daily_cap_for(user.get("plan"))
    if used >= cap:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "claude_daily_cap",
                "plan": user.get("plan", "free"),
                "cap": cap,
                "message": (
                    "Daily Claude limit reached. Upgrade to HF Pro for "
                    f"{user_quotas.CLAUDE_PRO_DAILY}/day or use a free model."
                ),
            },
        )
    await user_quotas.increment_claude(user_id)
    agent_session.claude_counted = True


def _check_session_access(session_id: str, user: dict[str, Any]) -> None:
    """Verify the user has access to the given session. Raises 403 or 404."""
    info = session_manager.get_session_info(session_id)
    if not info:
        raise HTTPException(status_code=404, detail="Session not found")
    if not session_manager.verify_session_access(session_id, user["user_id"]):
        raise HTTPException(status_code=403, detail="Access denied to this session")
