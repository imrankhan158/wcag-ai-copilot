from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.db.session import get_async_db
from app.db.models import User, Conversation, Audit

router = APIRouter(prefix="/history", tags=["History"])


@router.get("/chats")
async def get_chats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """List all past conversations for the current authenticated user."""
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == user.id)
        .order_by(Conversation.created_at.desc())
    )
    chats = result.scalars().all()
    return [{"id": c.id, "title": c.title, "created_at": c.created_at} for c in chats]


@router.get("/chats/{id}")
async def get_chat_details(
    id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Retrieve detailed messages for a specific conversation."""
    result = await db.execute(
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(Conversation.id == id, Conversation.user_id == user.id)
    )
    conv = result.scalars().first()
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found or access denied",
        )
    return {
        "id": conv.id,
        "title": conv.title,
        "created_at": conv.created_at,
        "messages": [
            {"role": m.role, "content": m.content, "created_at": m.created_at}
            for m in conv.messages
        ],
    }


@router.get("/audits")
async def get_audits(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """List all past accessibility audits for the current user."""
    result = await db.execute(
        select(Audit)
        .where(Audit.user_id == user.id)
        .order_by(Audit.created_at.desc())
    )
    audits = result.scalars().all()
    return [
        {
            "id": a.id,
            "input_type": a.input_type,
            "input_content": a.input_content,
            "summary": a.summary,
            "score": {
                "A": a.score_a,
                "AA": a.score_aa,
                "AAA": a.score_aaa,
                "total": a.score_total,
            },
            "created_at": a.created_at,
        }
        for a in audits
    ]


@router.get("/audits/{id}")
async def get_audit_details(
    id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Retrieve details and specific violations list for a past audit."""
    result = await db.execute(
        select(Audit)
        .options(selectinload(Audit.violations))
        .where(Audit.id == id, Audit.user_id == user.id)
    )
    audit = result.scalars().first()
    if not audit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audit not found or access denied",
        )
    return {
        "id": audit.id,
        "input_type": audit.input_type,
        "input_content": audit.input_content,
        "summary": audit.summary,
        "score": {
            "A": audit.score_a,
            "AA": audit.score_aa,
            "AAA": audit.score_aaa,
            "total": audit.score_total,
        },
        "created_at": audit.created_at,
        "violations": [
            {
                "criterion_id": v.criterion_id,
                "title": v.title,
                "level": v.level,
                "issue": v.issue,
                "element": v.element,
                "fix": v.fix,
                "explanation": v.explanation,
            }
            for v in audit.violations
        ],
    }
