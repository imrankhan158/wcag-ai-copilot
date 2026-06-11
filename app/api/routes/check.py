import re
from fastapi import APIRouter
from pydantic import BaseModel
from bs4 import BeautifulSoup

from app.agent.graph import advisor_graph
from app.ingestion.fetcher import PlaywrightFetcher

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.api.deps import get_current_user
from app.db.session import get_async_db
from app.db.models import User, Audit, AuditViolation

router = APIRouter()


class CheckRequest(BaseModel):
    input: str  # HTML/JSX code or description
    session_id: str | None = None


class CheckResponse(BaseModel):
    violations: list[dict]
    summary: str
    score: dict


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


@router.post("/check", response_model=CheckResponse)
async def check_accessibility(
    req: CheckRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    resolved = resolve_input(req.input)
    result = await advisor_graph.ainvoke({
        "user_input": resolved,
        "retrieved_criteria": [],
        "messages": [],
        "violations": [],
        "summary": "",
        "score": {},
    })

    input_type = "url" if req.input.strip().startswith(("http://", "https://")) else "code"
    score = result.get("score", {"A": 0, "AA": 0, "AAA": 0, "total": 0})
    
    audit = Audit(
        user_id=current_user.id,
        input_type=input_type,
        input_content=req.input,
        summary=result.get("summary", ""),
        score_a=score.get("A", 0),
        score_aa=score.get("AA", 0),
        score_aaa=score.get("AAA", 0),
        score_total=score.get("total", 0),
    )
    db.add(audit)
    await db.commit()
    await db.refresh(audit)

    for v in result.get("violations", []):
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

    return CheckResponse(
        violations=result["violations"],
        summary=result["summary"],
        score=result["score"],
    )
