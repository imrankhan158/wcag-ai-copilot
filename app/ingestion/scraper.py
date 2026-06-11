from __future__ import annotations

from dataclasses import dataclass, field

from app.ingestion.models import IngestDocument, SourceDefinition
from app.ingestion.fetcher import PlaywrightFetcher
from app.ingestion.parsers.w3c import parse_quickref
from app.ingestion.source_registry import WCAG_QUICKREF_URL


@dataclass
class WCAGCriterion:
    criterion_id: str
    title: str
    level: str
    principle: str
    guideline: str
    description: str
    techniques: list[str] = field(default_factory=list)
    url: str = ""


def _document_to_criterion(document: IngestDocument) -> WCAGCriterion:
    return WCAGCriterion(
        criterion_id=document.criterion_id or "",
        title=document.title.replace(f"WCAG {document.criterion_id}: ", "", 1),
        level=document.level or "",
        principle=document.principle or "",
        guideline=document.guideline or "",
        description=document.text,
        techniques=document.tags,
        url=document.source_url,
    )


def scrape_wcag() -> list[WCAGCriterion]:
    """Backward-compatible criterion scraper for older scripts."""

    source = SourceDefinition(
        url=WCAG_QUICKREF_URL,
        source_type="wcag_quickref",
        title="How to Meet WCAG 2.2 Quick Reference",
    )
    html = PlaywrightFetcher().fetch(source.url)
    parsed = parse_quickref(html, source)
    return [
        _document_to_criterion(document)
        for document in parsed.documents
        if document.doc_type == "success_criterion"
    ]


if __name__ == "__main__":
    criteria = scrape_wcag()
    for criterion in criteria[:5]:
        print(f"{criterion.criterion_id} [{criterion.level}] {criterion.title}")
    print(f"Total: {len(criteria)}")
