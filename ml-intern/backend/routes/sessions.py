"""Session management routes."""

import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from dependencies import get_current_user
from models import SessionInfo, SessionResponse
from session_manager import SessionCapacityError, session_manager

from routes.utils import AVAILABLE_MODELS, _require_hf_for_anthropic, _check_session_access

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["sessions"])


@router.post("/session", response_model=SessionResponse)
async def create_session(
    request: Request, user: dict[str, Any] = Depends(get_current_user)
) -> SessionResponse:
    """Create a new agent session bound to the authenticated user.

    The user's HF access token is extracted from the Authorization header
    and stored in the session so that tools (e.g. hf_jobs) can act on
    behalf of the user.

    Optional body ``{"model"?: <id>}`` selects the session's LLM; unknown
    ids are rejected (400). The Claude-quota gate runs at message-submit
    time, not here — spinning up an Opus session to look around is free.

    Returns 503 if the server or user has reached the session limit.
    """
    # Extract the user's HF token (Bearer header, HttpOnly cookie, or env var)
    hf_token = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        hf_token = auth_header[7:]
    if not hf_token:
        hf_token = request.cookies.get("hf_access_token")
    if not hf_token:
        hf_token = os.environ.get("HF_TOKEN")

    # Optional model override. Empty body falls back to the config default.
    model: str | None = None
    try:
        body = await request.json()
    except Exception:
        body = None
    if isinstance(body, dict):
        model = body.get("model")

    valid_ids = {m["id"] for m in AVAILABLE_MODELS}
    if model and model not in valid_ids:
        raise HTTPException(status_code=400, detail=f"Unknown model: {model}")

    # Opus is gated to HF staff (PR #63). Only fires when the resolved model
    # is Anthropic; free models pass through.
    resolved_model = model or session_manager.config.model_name
    await _require_hf_for_anthropic(request, resolved_model)

    try:
        session_id = await session_manager.create_session(
            user_id=user["user_id"], hf_token=hf_token, model=model
        )
    except SessionCapacityError as e:
        raise HTTPException(status_code=503, detail=str(e))

    return SessionResponse(session_id=session_id, ready=True)


@router.post("/session/restore-summary", response_model=SessionResponse)
async def restore_session_summary(
    request: Request, body: dict[str, Any], user: dict[str, Any] = Depends(get_current_user)
) -> SessionResponse:
    """Create a new session seeded with a summary of the caller's prior
    conversation. The client sends its cached messages; we run the standard
    summarization prompt on them and drop the result into the new
    session's context as a user-role system note.

    Optional ``"model"`` in the body overrides the session's LLM. The
    Claude-quota gate runs at message-submit time, not here.
    """
    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        raise HTTPException(status_code=400, detail="Missing 'messages' array")

    hf_token = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        hf_token = auth_header[7:]
    if not hf_token:
        hf_token = request.cookies.get("hf_access_token")
    if not hf_token:
        hf_token = os.environ.get("HF_TOKEN")

    model = body.get("model")
    valid_ids = {m["id"] for m in AVAILABLE_MODELS}
    if model and model not in valid_ids:
        raise HTTPException(status_code=400, detail=f"Unknown model: {model}")

    resolved_model = model or session_manager.config.model_name
    await _require_hf_for_anthropic(request, resolved_model)

    try:
        session_id = await session_manager.create_session(
            user_id=user["user_id"], hf_token=hf_token, model=model
        )
    except SessionCapacityError as e:
        raise HTTPException(status_code=503, detail=str(e))

    try:
        summarized = await session_manager.seed_from_summary(session_id, messages)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.exception("seed_from_summary failed")
        raise HTTPException(status_code=500, detail=f"Summary failed: {e}")

    logger.info(
        f"Seeded session {session_id} for {user.get('username', 'unknown')} "
        f"(summary of {summarized} messages)"
    )
    return SessionResponse(session_id=session_id, ready=True)


@router.get("/session/{session_id}", response_model=SessionInfo)
async def get_session(
    session_id: str, user: dict[str, Any] = Depends(get_current_user)
) -> SessionInfo:
    """Get session information. Only accessible by the session owner."""
    _check_session_access(session_id, user)
    info = session_manager.get_session_info(session_id)
    return SessionInfo(**info)


@router.post("/session/{session_id}/model")
async def set_session_model(
    session_id: str,
    body: dict[str, Any],
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict:
    """Switch the active model for a single session (tab-scoped).

    Takes effect on the next LLM call in that session — other sessions
    (including other browser tabs) are unaffected. Model switches don't
    charge quota — the Claude-quota gate only fires at message-submit time.

    Switching TO an Anthropic model requires HF org membership (PR #63);
    free-model switches are unrestricted.
    """
    _check_session_access(session_id, user)
    model_id = body.get("model")
    if not model_id:
        raise HTTPException(status_code=400, detail="Missing 'model' field")
    valid_ids = {m["id"] for m in AVAILABLE_MODELS}
    if model_id not in valid_ids:
        raise HTTPException(status_code=400, detail=f"Unknown model: {model_id}")
    await _require_hf_for_anthropic(request, model_id)
    agent_session = session_manager.sessions.get(session_id)
    if not agent_session:
        raise HTTPException(status_code=404, detail="Session not found")
    agent_session.session.update_model(model_id)
    logger.info(
        f"Session {session_id} model → {model_id} "
        f"(by {user.get('username', 'unknown')})"
    )
    return {"session_id": session_id, "model": model_id}


@router.get("/sessions", response_model=list[SessionInfo])
async def list_sessions(user: dict[str, Any] = Depends(get_current_user)) -> list[SessionInfo]:
    """List sessions belonging to the authenticated user."""
    sessions = session_manager.list_sessions(user_id=user["user_id"])
    return [SessionInfo(**s) for s in sessions]


@router.delete("/session/{session_id}")
async def delete_session(
    session_id: str, user: dict[str, Any] = Depends(get_current_user)
) -> dict:
    """Delete a session. Only accessible by the session owner."""
    _check_session_access(session_id, user)
    success = await session_manager.delete_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "deleted", "session_id": session_id}
