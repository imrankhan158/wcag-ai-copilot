import re
import json
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.graph import advisor_graph
from app.ingestion.fetcher import PlaywrightFetcher
from app.api.deps import get_current_user, get_async_db
from app.db.models import User

router = APIRouter()


class ChatRequest(BaseModel):
    input: str
    session_id: str | None = None


def resolve_input(user_input: str) -> str:
    input_stripped = user_input.strip()
    if re.match(r"^https?://", input_stripped):
        try:
            fetcher = PlaywrightFetcher(refresh=True)
            html = fetcher.fetch(input_stripped)
            soup = BeautifulSoup(html, "html.parser")
            
            # Remove scripts, styles, and links to keep tokens low
            for tag in soup(["script", "style", "meta", "link", "svg", "noscript"]):
                tag.decompose()
                
            body = soup.body
            content = str(body) if body else html
            if len(content) > 15000:
                content = content[:15000] + "\n... [HTML truncated for length] ..."
            return f"CRAWLED URL: {input_stripped}\n\nHTML CONTENT:\n```html\n{content}\n```"
        except Exception as e:
            return f"Failed to crawl URL {input_stripped}: {str(e)}"
    return user_input


async def stream_analysis(user_input: str, user_id: str | None = None, db: AsyncSession | None = None):
    """Stream events from LangGraph as SSE."""
    resolved = resolve_input(user_input)
    clean_output = None
    async for event in advisor_graph.astream_events(
        {
            "user_input": resolved,
            "retrieved_criteria": [],
            "messages": [],
            "violations": [],
            "summary": "",
            "score": {},
        },
        version="v1",
    ):
        kind = event.get("event")

        # Stream LLM token chunks
        if kind == "on_chat_model_stream":
            chunk = event["data"]["chunk"].content
            if chunk:
                yield f"data: {json.dumps({'type': 'token', 'content': chunk})}\n\n"

        # Node completion events
        elif kind == "on_chain_end":
            name = event.get("name", "")
            if name in ("analyze", "evaluate", "suggest"):
                yield f"data: {json.dumps({'type': 'node_done', 'node': name})}\n\n"

        # Final result
        if kind == "on_chain_end" and event.get("name") == "LangGraph":
            output = event["data"].get("output", {})
            final_data = output.get("suggest", output) if isinstance(output, dict) else {}
            clean_output = {
                "violations": final_data.get("violations", []),
                "summary": final_data.get("summary", ""),
                "score": final_data.get("score", {"A": 0, "AA": 0, "AAA": 0, "total": 0})
            }
            yield f"data: {json.dumps({'type': 'result', 'data': clean_output})}\n\n"

    # Save to database if user is authenticated and we have the result
    if user_id and db and clean_output:
        from app.db.models import User, Audit, AuditViolation
        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalars().first()
        if user:
            input_type = "url" if user_input.strip().startswith(("http://", "https://")) else "code"
            score = clean_output.get("score", {"A": 0, "AA": 0, "AAA": 0, "total": 0})
            
            audit = Audit(
                user_id=user.id,
                input_type=input_type,
                input_content=user_input,
                summary=clean_output.get("summary", ""),
                score_a=score.get("A", 0),
                score_aa=score.get("AA", 0),
                score_aaa=score.get("AAA", 0),
                score_total=score.get("total", 0),
            )
            db.add(audit)
            await db.commit()
            await db.refresh(audit)

            for v in clean_output.get("violations", []):
                violation = AuditViolation(
                    audit_id=audit.id,
                    criterion_id=v.get("criterion_id", "n/a"),
                    title=v.get("title", "Untitled"),
                    level=v.get("level", "A"),
                    issue=v.get("issue", ""),
                    element=v.get("element"),
                    fix=v.get("fix"),
                    explanation=v.get("explanation"),
                )
                db.add(violation)
            await db.commit()

    yield "data: [DONE]\n\n"


class MessageItem(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class QARequest(BaseModel):
    message: str
    conversation_id: str | None = None
    history: list[MessageItem] = []


async def stream_qa(
    message: str,
    history: list[MessageItem],
    conversation_id: str | None = None,
    user_id: str | None = None,
    db: AsyncSession | None = None,
):
    """Conversational RAG Q&A stream with optional database logging."""
    from app.retrieval.retriever import retrieve
    from app.agent.nodes import llm
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
    from app.db.models import Conversation, Message

    conv_id = conversation_id
    if user_id and db:
        if conv_id:
            # Check conversation exists and belongs to user
            res = await db.execute(
                select(Conversation).where(Conversation.id == conv_id, Conversation.user_id == user_id)
            )
            conv = res.scalars().first()
            if not conv:
                yield f"data: {json.dumps({'type': 'error', 'content': 'Conversation not found'})}\n\n"
                return
        else:
            # Create a new conversation
            title = message[:50] + "..." if len(message) > 50 else message
            conv = Conversation(user_id=user_id, title=title)
            db.add(conv)
            await db.commit()
            await db.refresh(conv)
            conv_id = conv.id
            yield f"data: {json.dumps({'type': 'conversation_id', 'id': conv_id})}\n\n"

        # Log user message
        user_msg = Message(conversation_id=conv_id, role="user", content=message)
        db.add(user_msg)
        await db.commit()

    # Retrieve context
    criteria = retrieve(message, top_k=5)
    context_items = []
    for c in criteria:
        doc_type = c.get("doc_type") or "document"
        crit_id = c.get("criterion_id") or c.get("technique_id") or "n/a"
        title = c.get("title") or "Untitled"
        text = c.get("text") or ""
        context_items.append(f"[{doc_type.upper()}] {crit_id} {title}\n{text}")

    criteria_context = "\n\n".join(context_items)

    system_msg = SystemMessage(
        content=f"You are WCAG AI Copilot, a senior accessibility advisor. "
        f"Answer the user's questions about web accessibility and the WCAG 2.2 guidelines. "
        f"Use the following WCAG Criteria Context to ground your answer. Always cite specific Success Criteria IDs and Techniques where applicable. "
        f"Provide clear, copy-paste-ready code examples where helpful. Keep your tone professional, helpful, and concise.\n\n"
        f"WCAG CRITERIA CONTEXT:\n{criteria_context}"
    )

    messages = [system_msg]
    for h in history:
        if h.role == "user":
            messages.append(HumanMessage(content=h.content))
        elif h.role == "assistant":
            messages.append(AIMessage(content=h.content))

    messages.append(HumanMessage(content=message))

    accumulated = []
    async for chunk in llm.astream(messages):
        token = chunk.content
        if token:
            accumulated.append(token)
            yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

    # Save assistant message to DB
    if user_id and db and conv_id:
        assistant_text = "".join(accumulated)
        assistant_msg = Message(conversation_id=conv_id, role="assistant", content=assistant_text)
        db.add(assistant_msg)
        await db.commit()

    yield "data: [DONE]\n\n"


@router.post("/chat")
async def chat_stream(
    req: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    return StreamingResponse(
        stream_analysis(req.input, current_user.id, db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat/qa")
async def chat_qa(
    req: QARequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    return StreamingResponse(
        stream_qa(req.message, req.history, req.conversation_id, current_user.id, db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

