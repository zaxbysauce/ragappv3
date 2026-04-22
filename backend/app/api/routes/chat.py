"""
Chat API routes for RAG-based conversational interface.

Provides streaming and non-streaming chat endpoints that leverage
the RAG engine for context-aware responses.
"""

import asyncio
import json
import logging
import sqlite3
from typing import Any, Dict, List, Optional, Set

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.deps import (
    evaluate_policy,
    get_current_active_user,
    get_db,
    get_rag_engine,
    get_user_accessible_vault_ids,
)
from app.config import settings
from app.models.database import get_pool
from app.services.rag_engine import RAGEngine, RAGEngineError

# Track background tasks to prevent garbage collection
_background_tasks: Set[asyncio.Task] = set()


router = APIRouter()

logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""

    message: str
    history: List[Dict[str, Any]] = Field(default_factory=list)
    stream: bool = False
    vault_id: Optional[int] = None


class ChatResponse(BaseModel):
    """Response model for non-streaming chat endpoint."""

    content: str
    sources: List[Dict[str, Any]] = Field(default_factory=list)
    memories_used: List[str] = Field(default_factory=list)
    # "distance" | "rerank" | "rrf" — tells the client how to interpret `score`
    # values in each source (polarity + thresholds). Default "distance" keeps
    # older clients on the safe path if the engine omits it.
    score_type: str = "distance"


class ChatMessage(BaseModel):
    role: str
    content: str
    name: Optional[str] = None


class ChatStreamRequest(BaseModel):
    messages: List[ChatMessage]
    vault_id: Optional[int] = None


class CreateSessionRequest(BaseModel):
    """Request model for creating a new chat session."""

    title: Optional[str] = None
    vault_id: int = 1


class AddMessageRequest(BaseModel):
    """Request model for adding a message to a chat session."""

    role: str
    content: str
    sources: Optional[List[dict]] = None


class UpdateSessionRequest(BaseModel):
    """Request model for updating a chat session title."""

    title: str


class ForkSessionRequest(BaseModel):
    """Request model for forking a chat session from a specific message index."""

    message_index: int = Field(..., ge=0, description="Index of the last message to include in the fork (0-based)")


def stream_chat_response(
    message: str,
    history: List[Dict[str, Any]],
    rag_engine: Optional[RAGEngine],
    vault_id: Optional[int] = None,
) -> StreamingResponse:
    """
    Generate a streaming chat response using SSE format.

    Yields SSE events with JSON data chunks from the RAG engine.
    Each event is formatted as: data: {json}\n\n
    Ends with a done event containing sources and memories_used.
    """
    if rag_engine is None:

        async def error_generator():
            yield f"data: {json.dumps({'type': 'error', 'message': 'RAG engine not available', 'code': 'SERVICE_UNAVAILABLE'})}\n\n"

        return StreamingResponse(
            error_generator(),
            media_type="text/event-stream",
        )

    async def event_generator():
        collected_content = []
        sources = []
        memories_used = []
        # Default to "distance" so the frontend always has a well-defined
        # score polarity to interpret `score` values against, even if the
        # engine never emits a done event (e.g. early error).
        score_type = "distance"

        try:
            async for chunk in rag_engine.query(
                message, history, stream=True, vault_id=vault_id
            ):
                chunk_type = chunk.get("type")

                if chunk_type == "content":
                    content = chunk.get("content", "")
                    collected_content.append(content)
                    yield f"data: {json.dumps({'type': 'content', 'content': content})}\n\n"
                elif chunk_type == "error":
                    yield f"data: {json.dumps({'type': 'error', 'message': chunk.get('message', 'Chat stream failed'), 'code': chunk.get('code', 'UNKNOWN_ERROR')})}\n\n"
                    yield f"data: {json.dumps({'type': 'done', 'sources': [], 'memories_used': [], 'score_type': score_type})}\n\n"
                    return
                elif chunk_type == "fallback":
                    content = chunk.get("content", "")
                    if content:
                        collected_content.append(content)
                        yield f"data: {json.dumps({'type': 'content', 'content': content})}\n\n"
                elif chunk_type == "done":
                    sources = chunk.get("sources", [])
                    memories_used = chunk.get("memories_used", [])
                    score_type = chunk.get("score_type", score_type)
        except Exception as e:
            logger.error(
                "Chat stream failed: message_len=%d, history_len=%d, exception=%s, error=%s",
                len(message),
                len(history),
                type(e).__name__,
                str(e),
                exc_info=True,
            )
            # Include exception type so users can report actionable errors
            error_msg = f"Chat failed ({type(e).__name__}): {str(e)[:200]}"
            yield f"data: {json.dumps({'type': 'error', 'message': error_msg, 'code': 'INTERNAL_ERROR'})}\n\n"
            return

        # Yield final done event with sources, memories, and score_type so the
        # frontend can correctly map `score` to relevance labels. Omitting
        # `score_type` forces the client to guess and historically caused every
        # source to render as "Tangential" via the distance-mode fallback.
        yield f"data: {json.dumps({'type': 'done', 'sources': sources, 'memories_used': memories_used, 'score_type': score_type})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
    )


async def non_stream_chat_response(
    message: str,
    history: List[Dict[str, Any]],
    rag_engine: Optional[RAGEngine],
    vault_id: Optional[int] = None,
) -> ChatResponse:
    """
    Generate a non-streaming chat response.

    Collects all chunks from the RAG engine and returns a complete
    response with content, sources, and memories used.
    """
    logger.info(
        "[non_stream_chat_response] ENTER: message_len=%d, vault_id=%s",
        len(message),
        vault_id,
    )
    if rag_engine is None:
        raise HTTPException(status_code=503, detail="RAG engine not available")

    collected_content = []
    sources = []
    memories_used = []
    score_type = "distance"

    try:
        async for chunk in rag_engine.query(
            message, history, stream=False, vault_id=vault_id
        ):
            chunk_type = chunk.get("type")
            logger.debug(
                "[non_stream_chat_response] Received chunk type='%s'", chunk_type
            )

            if chunk_type == "content":
                collected_content.append(chunk.get("content", ""))
            elif chunk_type == "done":
                sources = chunk.get("sources", [])
                memories_used = chunk.get("memories_used", [])
                score_type = chunk.get("score_type", score_type)
    except RAGEngineError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    logger.info(
        "[non_stream_chat_response] Final: sources_count=%d, memories_used_count=%d",
        len(sources),
        len(memories_used),
    )

    full_content = "".join(collected_content)

    return ChatResponse(
        content=full_content,
        sources=sources,
        memories_used=memories_used,
        score_type=score_type,
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    rag_engine: RAGEngine = Depends(get_rag_engine),
    user: dict = Depends(get_current_active_user),
):
    """
    Chat endpoint for RAG-based conversational interface.

    Args:
        request: ChatRequest containing message, optional history, and stream flag

    Returns:
        ChatResponse with content, sources, memories_used

    Raises:
        HTTPException: If stream=True is requested (use /chat/stream instead)
    """
    logger.info(
        "[chat] Request received: message_len=%d, vault_id=%s, stream=%s",
        len(request.message),
        request.vault_id,
        request.stream,
    )
    if request.stream:
        raise HTTPException(
            status_code=400,
            detail="Streaming is not supported on this endpoint. Use /chat/stream for streaming responses.",
        )
    if request.vault_id is not None:
        if not await evaluate_policy(user, "vault", request.vault_id, "read"):
            raise HTTPException(status_code=403, detail="No read access to this vault")
    else:
        # vault_id=None ("All Vaults") searches across all vaults without filtering.
        # Restrict to admin/superadmin — non-admin users must specify a vault_id.
        if user.get("role") not in ("superadmin", "admin"):
            raise HTTPException(
                status_code=403,
                detail="Searching all vaults requires admin access. Please select a specific vault.",
            )
    try:
        return await non_stream_chat_response(
            request.message, request.history, rag_engine, vault_id=request.vault_id
        )
    except Exception:
        logger.exception("[chat] UNHANDLED EXCEPTION during chat processing")
        raise


@router.post("/chat/stream")
async def chat_stream(
    request: ChatStreamRequest,
    rag_engine: RAGEngine = Depends(get_rag_engine),
    user: dict = Depends(get_current_active_user),
):
    """Streaming chat endpoint that accepts a sequence of chat messages."""
    if not request.messages:
        raise HTTPException(status_code=400, detail="At least one message is required")

    last_message = request.messages[-1]
    if last_message.role.lower() != "user":
        raise HTTPException(
            status_code=400, detail="The last message must be from the user"
        )

    if request.vault_id is not None:
        if not await evaluate_policy(user, "vault", request.vault_id, "read"):
            raise HTTPException(status_code=403, detail="No read access to this vault")
    else:
        # vault_id=None ("All Vaults") searches across all vaults without filtering.
        # Restrict to admin/superadmin — non-admin users must specify a vault_id.
        if user.get("role") not in ("superadmin", "admin"):
            raise HTTPException(
                status_code=403,
                detail="Searching all vaults requires admin access. Please select a specific vault.",
            )

    history = [msg.model_dump(exclude_none=True) for msg in request.messages[:-1]]
    return stream_chat_response(
        last_message.content, history, rag_engine, vault_id=request.vault_id
    )


# ============================================================================
# Chat Session History Management Endpoints
# ============================================================================


@router.get("/chat/sessions")
async def list_sessions(
    vault_id: Optional[int] = Query(None),
    conn: sqlite3.Connection = Depends(get_db),
    user: dict = Depends(get_current_active_user),
):
    """
    List all chat sessions, optionally filtered by vault_id.

    Returns sessions sorted by updated_at DESC with message count for each session.
    """
    # Build single JOIN query with optional vault_id filter to avoid N+1
    if vault_id is not None:
        query = """
            SELECT s.id, s.vault_id, s.title, s.created_at, s.updated_at, COUNT(m.id) as message_count, s.forked_from_session_id, s.fork_message_index
            FROM chat_sessions s
            LEFT JOIN chat_messages m ON m.session_id = s.id
            WHERE s.vault_id = ?
            GROUP BY s.id
            ORDER BY s.updated_at DESC
        """
        params = (vault_id,)
    else:
        query = """
            SELECT s.id, s.vault_id, s.title, s.created_at, s.updated_at, COUNT(m.id) as message_count, s.forked_from_session_id, s.fork_message_index
            FROM chat_sessions s
            LEFT JOIN chat_messages m ON m.session_id = s.id
            GROUP BY s.id
            ORDER BY s.updated_at DESC
        """
        params = ()

    result = await asyncio.to_thread(conn.execute, query, params)
    rows = await asyncio.to_thread(result.fetchall)

    # Map rows to dicts
    sessions_with_count = []
    for row in rows:
        sessions_with_count.append(
            {
                "id": row[0],
                "vault_id": row[1],
                "title": row[2],
                "created_at": row[3],
                "updated_at": row[4],
                "message_count": row[5],
                "forked_from_session_id": row[6],
                "fork_message_index": row[7],
            }
        )

    # Filter sessions for non-admin users
    if user.get("role") not in ("superadmin", "admin"):
        accessible_ids = get_user_accessible_vault_ids(user, conn)
        if accessible_ids:
            sessions_with_count = [
                r for r in sessions_with_count if r.get("vault_id") in accessible_ids
            ]
        else:
            sessions_with_count = []

    return {"sessions": sessions_with_count}


@router.get("/chat/sessions/{session_id}")
async def get_session(
    session_id: int,
    conn: sqlite3.Connection = Depends(get_db),
    user: dict = Depends(get_current_active_user),
):
    """
    Get a specific chat session with all its messages.

    Returns session details and messages ordered by created_at ASC.
    Parses the sources field from JSON string to list.
    """
    # Get session
    session_query = "SELECT id, vault_id, title, created_at, updated_at FROM chat_sessions WHERE id = ?"
    session_result = await asyncio.to_thread(conn.execute, session_query, (session_id,))
    session_row = await asyncio.to_thread(session_result.fetchone)

    if session_row is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if not await evaluate_policy(user, "vault", session_row[1], "read"):
        raise HTTPException(status_code=403, detail="No read access to this vault")

    # Get messages
    messages_query = "SELECT id, role, content, sources, created_at FROM chat_messages WHERE session_id = ? ORDER BY created_at ASC, id ASC"
    messages_result = await asyncio.to_thread(
        conn.execute, messages_query, (session_id,)
    )
    message_rows = await asyncio.to_thread(messages_result.fetchall)

    # Parse messages with JSON sources
    messages = []
    for msg_row in message_rows:
        sources = None
        if msg_row[3]:
            try:
                sources = json.loads(msg_row[3])
            except json.JSONDecodeError:
                sources = []

        messages.append(
            {
                "id": msg_row[0],
                "role": msg_row[1],
                "content": msg_row[2],
                "sources": sources,
                "created_at": msg_row[4],
            }
        )

    return {
        "id": session_row[0],
        "vault_id": session_row[1],
        "title": session_row[2],
        "created_at": session_row[3],
        "updated_at": session_row[4],
        "messages": messages,
    }


@router.post("/chat/sessions")
async def create_session(
    request: CreateSessionRequest,
    conn: sqlite3.Connection = Depends(get_db),
    user: dict = Depends(get_current_active_user),
):
    """
    Create a new chat session.

    Returns the created session with its ID.
    """
    if not await evaluate_policy(user, "vault", request.vault_id, "write"):
        raise HTTPException(status_code=403, detail="No write access to this vault")

    query = "INSERT INTO chat_sessions (vault_id, title, created_at, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
    cursor = await asyncio.to_thread(
        conn.execute, query, (request.vault_id, request.title)
    )
    await asyncio.to_thread(conn.commit)

    # Get the created session
    session_id = cursor.lastrowid
    select_query = "SELECT id, vault_id, title, created_at, updated_at FROM chat_sessions WHERE id = ?"
    result = await asyncio.to_thread(conn.execute, select_query, (session_id,))
    row = await asyncio.to_thread(result.fetchone)

    if row is None:
        raise HTTPException(status_code=500, detail="Session was created but could not be retrieved")

    return {
        "id": row[0],
        "vault_id": row[1],
        "title": row[2],
        "created_at": row[3],
        "updated_at": row[4],
    }


@router.post("/chat/sessions/{session_id}/fork")
async def fork_session(
    session_id: int,
    request: ForkSessionRequest,
    conn: sqlite3.Connection = Depends(get_db),
    user: dict = Depends(get_current_active_user),
):
    """
    Fork a chat session from a specific message index.

    Creates a new session containing messages 0..message_index (inclusive)
    from the original session, preserving vault context.
    """
    # Fetch original session
    session_result = await asyncio.to_thread(
        conn.execute,
        "SELECT id, vault_id, title FROM chat_sessions WHERE id = ?",
        (session_id,),
    )
    session_row = await asyncio.to_thread(session_result.fetchone)
    if session_row is None:
        raise HTTPException(status_code=404, detail="Session not found")

    vault_id = session_row[1]
    if not await evaluate_policy(user, "vault", vault_id, "write"):
        raise HTTPException(status_code=403, detail="No write access to this vault")

    # Fetch messages up to message_index
    messages_result = await asyncio.to_thread(
        conn.execute,
        "SELECT role, content, sources, created_at FROM chat_messages WHERE session_id = ? ORDER BY created_at ASC, id ASC",
        (session_id,),
    )
    all_rows = await asyncio.to_thread(messages_result.fetchall)
    if request.message_index >= len(all_rows):
        raise HTTPException(
            status_code=400,
            detail=f"message_index {request.message_index} is out of bounds for session with {len(all_rows)} messages",
        )
    forked_rows = all_rows[: request.message_index + 1]

    # Create new forked session
    fork_title = f"Branch of {session_row[2] or 'conversation'}"
    cursor = await asyncio.to_thread(
        conn.execute,
        "INSERT INTO chat_sessions (vault_id, title, forked_from_session_id, fork_message_index, created_at, updated_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
        (vault_id, fork_title, session_id, request.message_index),
    )
    await asyncio.to_thread(conn.commit)
    new_session_id = cursor.lastrowid

    # Copy messages into the new session
    for row in forked_rows:
        await asyncio.to_thread(
            conn.execute,
            "INSERT INTO chat_messages (session_id, role, content, sources, created_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
            (new_session_id, row[0], row[1], row[2]),
        )
    await asyncio.to_thread(conn.commit)

    # Return new session info with copied messages
    messages = []
    for row in forked_rows:
        sources = None
        if row[2]:
            try:
                sources = json.loads(row[2])
            except json.JSONDecodeError:
                sources = []
        messages.append({"role": row[0], "content": row[1], "sources": sources})

    return {
        "id": new_session_id,
        "vault_id": vault_id,
        "title": fork_title,
        "forked_from_session_id": session_id,
        "fork_message_index": request.message_index,
        "messages": messages,
    }


async def _auto_name_session(
    session_id: int,
    first_message: str,
    llm_client,
) -> None:
    """
    Generate a 3-6 word title from the first user message using LLM.
    Runs as a background task (does not block streaming).
    Manual rename overwrites auto-generated title permanently.
    """
    # Acquire connection from pool for this background task
    pool = get_pool(str(settings.sqlite_path))

    try:
        # Truncate input to first 200 chars to avoid wasting tokens
        prompt_text = first_message[:200]

        messages = [
            {
                "role": "system",
                "content": "Generate a very short title (3-6 words only, no quotes, no punctuation at end) for a chat conversation that starts with this message. Output ONLY the title, nothing else.",
            },
            {"role": "user", "content": prompt_text},
        ]

        title = await llm_client.chat_completion(
            messages=messages, temperature=0.3, max_tokens=20
        )

        # Clean up the title
        title = title.strip().strip('"').strip("'")

        # Ensure title is reasonable length
        if len(title) < 3:
            title = first_message[:50] + ("..." if len(first_message) > 50 else "")
        elif len(title) > 60:
            title = title[:57] + "..."

        # Atomic UPDATE with WHERE clause to prevent TOCTOU race
        # Only update if the title still starts with first_message prefix and is short (auto-title characteristics)
        with pool.connection() as conn:
            # Get current title for guard check
            check_query = "SELECT title FROM chat_sessions WHERE id = ?"
            check_result = await asyncio.to_thread(
                conn.execute, check_query, (session_id,)
            )
            current_title = await asyncio.to_thread(check_result.fetchone)

            # Only update if the title hasn't been changed manually
            existing_title = current_title[0] if current_title else None
            if existing_title is not None and existing_title != "":
                # Improved guard: check prefix match AND length (auto-titles are typically short)
                if len(existing_title) < 60 and existing_title.startswith(
                    first_message[:10]
                ):
                    # Atomic UPDATE with WHERE clause - only updates if title hasn't changed
                    update_query = """
                        UPDATE chat_sessions SET title = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ? AND title = ?
                    """
                    cursor = await asyncio.to_thread(
                        conn.execute, update_query, (title, session_id, existing_title)
                    )
                    affected = cursor.rowcount
                    if affected > 0:
                        await asyncio.to_thread(conn.commit)
                        logger.info(
                            "Auto-named session %d: %s (rows_affected=%d)",
                            session_id,
                            title,
                            affected,
                        )
                    else:
                        logger.warning(
                            "Auto-name skipped for session %d — title was changed concurrently",
                            session_id,
                        )
            else:
                # Title is NULL/empty (untitled session) — update unconditionally
                update_query = """
                    UPDATE chat_sessions SET title = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """
                cursor = await asyncio.to_thread(
                    conn.execute, update_query, (title, session_id)
                )
                affected = cursor.rowcount
                if affected > 0:
                    await asyncio.to_thread(conn.commit)
                    logger.info("Auto-named untitled session %d: %s", session_id, title)

    except Exception as e:
        logger.warning(
            "Auto-name session %d failed: %s. Using fallback.", session_id, e
        )
        # Fallback: truncate first message
        try:
            auto_title = (
                first_message[:50] + "..." if len(first_message) > 50 else first_message
            )
            with pool.connection() as conn:
                # Atomic UPDATE for fallback too
                update_query = """
                    UPDATE chat_sessions SET title = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND title IS NULL
                """
                cursor = await asyncio.to_thread(
                    conn.execute, update_query, (auto_title, session_id)
                )
                if cursor.rowcount > 0:
                    await asyncio.to_thread(conn.commit)
        except Exception:
            logger.error("Auto-name fallback also failed for session %d", session_id)


@router.post("/chat/sessions/{session_id}/messages")
async def add_message(
    session_id: int,
    request: AddMessageRequest,
    conn: sqlite3.Connection = Depends(get_db),
    user: dict = Depends(get_current_active_user),
    rag_engine: Optional[RAGEngine] = Depends(get_rag_engine),
):
    """
    Add a message to a chat session.

    If this is the first message and the session has no title,
    auto-titles the session using LLM (fire-and-forget, non-blocking).
    Falls back to truncating the first message if LLM is unavailable.
    Updates the session's updated_at timestamp.
    """
    # Verify session exists
    session_query = "SELECT id, title, vault_id FROM chat_sessions WHERE id = ?"
    session_result = await asyncio.to_thread(conn.execute, session_query, (session_id,))
    session_row = await asyncio.to_thread(session_result.fetchone)

    if session_row is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if not await evaluate_policy(user, "vault", session_row[2], "write"):
        raise HTTPException(status_code=403, detail="No write access to this vault")

    # Check if this is the first message
    count_query = "SELECT COUNT(*) FROM chat_messages WHERE session_id = ?"
    count_result = await asyncio.to_thread(conn.execute, count_query, (session_id,))
    message_count_row = await asyncio.to_thread(count_result.fetchone)
    is_first_message = message_count_row[0] == 0

    # Auto-title if this is the first *user* message and the session has no title.
    # Role guard is critical: concurrent saves (Promise.all) mean both user and assistant
    # inserts can see COUNT(*)=0 simultaneously. Without the role check, the assistant
    # message could trigger auto-naming with its own response content as the title basis.
    if is_first_message and session_row[1] is None and request.role == "user":
        # Fire-and-forget LLM auto-naming (does not block the response)
        if rag_engine and rag_engine.llm_client is not None:
            task = asyncio.create_task(
                _auto_name_session(session_id, request.content, rag_engine.llm_client)
            )
            _background_tasks.add(task)
            task.add_done_callback(_background_tasks.discard)
        else:
            # Fallback: truncate first message
            auto_title = (
                request.content[:50] + "..."
                if len(request.content) > 50
                else request.content
            )
            update_title_query = "UPDATE chat_sessions SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?"
            await asyncio.to_thread(
                conn.execute, update_title_query, (auto_title, session_id)
            )

    # Serialize sources to JSON
    sources_json = json.dumps(request.sources) if request.sources else None

    # Insert message
    insert_query = """
        INSERT INTO chat_messages (session_id, role, content, sources, created_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
    """
    cursor = await asyncio.to_thread(
        conn.execute,
        insert_query,
        (session_id, request.role, request.content, sources_json),
    )

    # Update session's updated_at
    update_query = (
        "UPDATE chat_sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?"
    )
    await asyncio.to_thread(conn.execute, update_query, (session_id,))
    await asyncio.to_thread(conn.commit)

    # Get the created message
    message_id = cursor.lastrowid
    select_query = (
        "SELECT id, role, content, sources, created_at FROM chat_messages WHERE id = ?"
    )
    result = await asyncio.to_thread(conn.execute, select_query, (message_id,))
    row = await asyncio.to_thread(result.fetchone)

    if row is None:
        raise HTTPException(status_code=500, detail="Message was created but could not be retrieved")

    # Parse sources
    sources = None
    if row[3]:
        try:
            sources = json.loads(row[3])
        except json.JSONDecodeError:
            sources = []

    return {
        "id": row[0],
        "role": row[1],
        "content": row[2],
        "sources": sources,
        "created_at": row[4],
    }


@router.put("/chat/sessions/{session_id}")
async def update_session(
    session_id: int,
    request: UpdateSessionRequest,
    conn: sqlite3.Connection = Depends(get_db),
    user: dict = Depends(get_current_active_user),
):
    """
    Update a chat session's title.

    Updates the session's title and updated_at timestamp.
    """
    # Verify session exists and get vault_id
    select_query = "SELECT id, vault_id FROM chat_sessions WHERE id = ?"
    select_result = await asyncio.to_thread(conn.execute, select_query, (session_id,))
    select_row = await asyncio.to_thread(select_result.fetchone)

    if select_row is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if not await evaluate_policy(user, "vault", select_row[1], "write"):
        raise HTTPException(status_code=403, detail="No write access to this vault")

    # Update session
    update_query = "UPDATE chat_sessions SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?"
    await asyncio.to_thread(conn.execute, update_query, (request.title, session_id))
    await asyncio.to_thread(conn.commit)

    # Get updated session (fetch all needed fields)
    fetch_query = "SELECT id, vault_id, title, created_at, updated_at FROM chat_sessions WHERE id = ?"
    result = await asyncio.to_thread(conn.execute, fetch_query, (session_id,))
    row = await asyncio.to_thread(result.fetchone)

    if row is None:
        raise HTTPException(status_code=404, detail="Session not found after update")

    return {
        "id": row[0],
        "vault_id": row[1],
        "title": row[2],
        "created_at": row[3],
        "updated_at": row[4],
    }


@router.delete("/chat/sessions/{session_id}")
async def delete_session(
    session_id: int,
    conn: sqlite3.Connection = Depends(get_db),
    user: dict = Depends(get_current_active_user),
):
    """
    Delete a chat session.

    The CASCADE constraint will automatically delete all messages
    associated with the session.
    """
    # Verify session exists and get vault_id
    select_query = "SELECT id, vault_id FROM chat_sessions WHERE id = ?"
    select_result = await asyncio.to_thread(conn.execute, select_query, (session_id,))
    select_row = await asyncio.to_thread(select_result.fetchone)

    if select_row is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if not await evaluate_policy(user, "vault", select_row[1], "write"):
        raise HTTPException(status_code=403, detail="No write access to this vault")

    # Delete session (CASCADE will delete messages)
    delete_query = "DELETE FROM chat_sessions WHERE id = ?"
    await asyncio.to_thread(conn.execute, delete_query, (session_id,))
    await asyncio.to_thread(conn.commit)

    return {"status": "deleted", "session_id": session_id}
