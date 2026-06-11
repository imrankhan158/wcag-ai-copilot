from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

SourceType = Literal[
    "wcag_quickref",
    "wcag_understanding",
    "wcag_technique",
    "wcag_techniques_index",
    "aria_apg",
    "generic",
]

DocumentType = Literal[
    "success_criterion",
    "understanding",
    "technique",
    "failure",
    "aria_pattern",
    "reference",
]


@dataclass(frozen=True)
class SourceDefinition:
    """A fetchable source and the parser that should handle it."""

    url: str
    source_type: SourceType
    title: str
    wcag_version: str | None = "2.2"


@dataclass
class IngestDocument:
    """Normalized document unit before final chunking and vectorization."""

    doc_type: DocumentType
    source_url: str
    source_title: str
    title: str
    text: str
    wcag_version: str | None = "2.2"
    criterion_id: str | None = None
    level: str | None = None
    principle: str | None = None
    guideline: str | None = None
    technique_id: str | None = None
    technology: str | None = None
    tags: list[str] = field(default_factory=list)
    related_urls: list[str] = field(default_factory=list)


@dataclass
class ParsedSource:
    """Documents parsed from a source plus discovered official links."""

    documents: list[IngestDocument] = field(default_factory=list)
    discovered_sources: list[SourceDefinition] = field(default_factory=list)


@dataclass
class DocumentChunk:
    """Final text unit that is embedded and stored in Qdrant."""

    id: str
    text: str
    payload: dict
