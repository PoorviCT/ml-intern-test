"""Chat and agent interaction routes (including SSE endpoints)."""

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from dependencies import get_current_user
from models import ApprovalRequest, SubmitRequest, TruncateRequest
from session_manager import session_manager

from routes.utils import _check_session_access, _enforce_claude_quota

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])

# ---------------------------------------------------------------------------
# Shared SSE helpers
# ---------------------------------------------------------------------------
_TERMINAL_EVENTS = {"turn_complete", "approval_required", "error", "interrupted", "shutdown"}
_SSE_KEEPALIVE_SECONDS = 15


def _sse_response(broadcaster: Any, event_queue: asyncio.Queue, sub_id: int) -> StreamingResponse:
    """Build a StreamingResponse that drains *event_queue* as SSE,
    sending keepalive comments every 15 s to prevent proxy timeouts."""

    async def event_generator():
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(
                        event_queue.get(), timeout=_SSE_KEEPALIVE_SECONDS
                    )
                except asyncio.TimeoutError:
                    # SSE comment — ignored by parsers, keeps connection alive
                    yield ": keepalive\n\n"
                    continue
                event_type = msg.get("event_type", "")
                yield f"data: {json.dumps(msg)}\n\n"
                if event_type in _TERMINAL_EVENTS:
                    break
        finally:
            broadcaster.unsubscribe(sub_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/submit")
async def submit_input(
    request: SubmitRequest, user: dict[str, Any] = Depends(get_current_user)
) -> dict:
    """Submit user input to a session. Only accessible by the session owner."""
    _check_session_access(request.session_id, user)
    agent_session = session_manager.sessions.get(request.session_id)
    if agent_session is not None:
        await _enforce_claude_quota(user, agent_session)
    success = await session_manager.submit_user_input(request.session_id, request.text)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found or inactive")
    return {"status": "submitted", "session_id": request.session_id}


@router.post("/approve")
async def submit_approval(
    request: ApprovalRequest, user: dict[str, Any] = Depends(get_current_user)
) -> dict:
    """Submit tool approvals to a session. Only accessible by the session owner."""
    _check_session_access(request.session_id, user)
    approvals = [
        {
            "tool_call_id": a.tool_call_id,
            "approved": a.approved,
            "feedback": a.feedback,
            "edited_script": a.edited_script,
        }
        for a in request.approvals
    ]
    success = await session_manager.submit_approval(request.session_id, approvals)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found or inactive")
    return {"status": "submitted", "session_id": request.session_id}


@router.post("/chat/{session_id}")
async def chat_sse(
    session_id: str,
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
) -> StreamingResponse:
    """SSE endpoint: submit input or approval, then stream events until turn ends."""
    _check_session_access(session_id, user)

    agent_session = session_manager.sessions.get(session_id)
    if not agent_session or not agent_session.is_active:
        raise HTTPException(status_code=404, detail="Session not found or inactive")

    # Parse body
    body = await request.json()

    # Subscribe BEFORE submitting so we never miss events — even if the
    # agent loop processes the submission before this coroutine continues.
    broadcaster = agent_session.broadcaster
    sub_id, event_queue = broadcaster.subscribe()

    # Submit the operation
    text = body.get("text")
    approvals = body.get("approvals")

    # Gate user-message sends against the daily Claude quota. Approvals are
    # continuations of an in-progress turn — the session was already charged
    # on its first message, so we skip the gate there.
    if text is not None and not approvals:
        try:
            await _enforce_claude_quota(user, agent_session)
        except HTTPException:
            broadcaster.unsubscribe(sub_id)
            raise

    try:
        if approvals:
            formatted = [
                {
                    "tool_call_id": a["tool_call_id"],
                    "approved": a["approved"],
                    "feedback": a.get("feedback"),
                    "edited_script": a.get("edited_script"),
                }
                for a in approvals
            ]
            success = await session_manager.submit_approval(session_id, formatted)
        elif text is not None:
            success = await session_manager.submit_user_input(session_id, text)
        else:
            broadcaster.unsubscribe(sub_id)
            raise HTTPException(status_code=400, detail="Must provide 'text' or 'approvals'")

        if not success:
            broadcaster.unsubscribe(sub_id)
            raise HTTPException(status_code=404, detail="Session not found or inactive")
    except HTTPException:
        raise
    except Exception:
        broadcaster.unsubscribe(sub_id)
        raise

    return _sse_response(broadcaster, event_queue, sub_id)


@router.get("/events/{session_id}")
async def subscribe_events(
    session_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> StreamingResponse:
    """Subscribe to events for a running session without submitting new input.

    Used by the frontend to re-attach after a connection drop (e.g. screen
    sleep).  Returns 404 if the session isn't active or isn't processing.
    """
    _check_session_access(session_id, user)

    agent_session = session_manager.sessions.get(session_id)
    if not agent_session or not agent_session.is_active:
        raise HTTPException(status_code=404, detail="Session not found or inactive")

    broadcaster = agent_session.broadcaster
    sub_id, event_queue = broadcaster.subscribe()
    return _sse_response(broadcaster, event_queue, sub_id)


@router.post("/interrupt/{session_id}")
async def interrupt_session(
    session_id: str, user: dict[str, Any] = Depends(get_current_user)
) -> dict:
    """Interrupt the current operation in a session."""
    _check_session_access(session_id, user)
    success = await session_manager.interrupt(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found or inactive")
    return {"status": "interrupted", "session_id": session_id}


@router.get("/session/{session_id}/messages")
async def get_session_messages(
    session_id: str, user: dict[str, Any] = Depends(get_current_user)
) -> list[dict]:
    """Return the session's message history from memory."""
    _check_session_access(session_id, user)
    agent_session = session_manager.sessions.get(session_id)
    if not agent_session or not agent_session.is_active:
        raise HTTPException(status_code=404, detail="Session not found or inactive")
    return [msg.model_dump() for msg in agent_session.session.context_manager.items]


@router.post("/undo/{session_id}")
async def undo_session(session_id: str, user: dict[str, Any] = Depends(get_current_user)) -> dict:
    """Undo the last turn in a session."""
    _check_session_access(session_id, user)
    success = await session_manager.undo(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found or inactive")
    return {"status": "undo_requested", "session_id": session_id}


@router.post("/truncate/{session_id}")
async def truncate_session(
    session_id: str, body: TruncateRequest, user: dict[str, Any] = Depends(get_current_user)
) -> dict:
    """Truncate conversation to before a specific user message."""
    _check_session_access(session_id, user)
    success = await session_manager.truncate(session_id, body.user_message_index)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found, inactive, or message index out of range")
    return {"status": "truncated", "session_id": session_id}


@router.post("/compact/{session_id}")
async def compact_session(
    session_id: str, user: dict[str, Any] = Depends(get_current_user)
) -> dict:
    """Compact the context in a session."""
    _check_session_access(session_id, user)
    success = await session_manager.compact(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found or inactive")
    return {"status": "compact_requested", "session_id": session_id}


@router.post("/shutdown/{session_id}")
async def shutdown_session(
    session_id: str, user: dict[str, Any] = Depends(get_current_user)
) -> dict:
    """Shutdown a session."""
    _check_session_access(session_id, user)
    success = await session_manager.shutdown_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found or inactive")
    return {"status": "shutdown_requested", "session_id": session_id}


@router.post("/feedback/{session_id}")
async def submit_feedback(
    session_id: str,
    body: dict[str, Any],
    user: dict[str, Any] = Depends(get_current_user),
) -> dict:
    """Attach a user feedback signal to a session's event log.

    Body: {rating: "up"|"down"|"outcome_success"|"outcome_fail",
           turn_index?: int, comment?: str, message_id?: str}
    Appended as a `feedback` event and saved with the session trajectory.
    """
    _check_session_access(session_id, user)
    agent_session = session_manager.sessions.get(session_id)
    if not agent_session:
        raise HTTPException(status_code=404, detail="Session not found")

    rating = body.get("rating")
    if rating not in {"up", "down", "outcome_success", "outcome_fail"}:
        raise HTTPException(status_code=400, detail="invalid rating")

    from agent.core import telemetry
    await telemetry.record_feedback(
        agent_session.session,
        rating=rating,
        turn_index=body.get("turn_index"),
        message_id=body.get("message_id"),
        comment=body.get("comment"),
    )
    # Fire-and-forget save so feedback reaches the dataset even if the user
    # closes the tab right after clicking.
    if agent_session.session.config.save_sessions:
        agent_session.session.save_and_upload_detached(
            agent_session.session.config.session_dataset_repo
        )
    return {"status": "ok"}
