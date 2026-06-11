from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

from app.ingestion.models import DocumentChunk, IngestDocument

MAX_CHARS = 3_200
OVERLAP_CHARS = 350


def stable_chunk_id(document: IngestDocument, chunk_index: int, text: str) -> str:
    raw = "|".join([
        document.doc_type,
        document.source_url,
        document.criterion_id or "",
        document.technique_id or "",
        str(chunk_index),
        hashlib.sha256(text.encode("utf-8")).hexdigest(),
    ])
    return str(uuid.uuid5(uuid.NAMESPACE_URL, raw))


def split_text(text: str, max_chars: int = MAX_CHARS, overlap_chars: int = OVERLAP_CHARS) -> list[str]:
    text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if len(text) <= max_chars:
        return [text] if text else []

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            boundary = max(text.rfind("\n", start, end), text.rfind(". ", start, end))
            if boundary > start + max_chars // 2:
                end = boundary + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(0, end - overlap_chars)
    return chunks


def build_chunk_text(document: IngestDocument, body: str) -> str:
    metadata_lines = [
        f"Title: {document.title}",
        f"Document type: {document.doc_type}",
    ]
    if document.criterion_id:
        metadata_lines.append(f"WCAG success criterion: {document.criterion_id}")
    if document.level:
        metadata_lines.append(f"Conformance level: {document.level}")
    if document.principle:
        metadata_lines.append(f"Principle: {document.principle}")
    if document.guideline:
        metadata_lines.append(f"Guideline: {document.guideline}")
    if document.technique_id:
        metadata_lines.append(f"Technique or failure ID: {document.technique_id}")
    if document.technology:
        metadata_lines.append(f"Technology: {document.technology}")
    if document.tags:
        metadata_lines.append(f"Related tags: {', '.join(document.tags)}")
    return "\n".join(metadata_lines) + "\n\n" + body


def build_payload(document: IngestDocument, chunk_text: str, chunk_index: int) -> dict:
    now = datetime.now(UTC).isoformat()
    return {
        "doc_type": document.doc_type,
        "source_url": document.source_url,
        "source_title": document.source_title,
        "title": document.title,
        "wcag_version": document.wcag_version,
        "criterion_id": document.criterion_id,
        "level": document.level,
        "principle": document.principle,
        "guideline": document.guideline,
        "technique_id": document.technique_id,
        "technology": document.technology,
        "tags": document.tags,
        "related_urls": document.related_urls,
        "chunk_index": chunk_index,
        "content_hash": hashlib.sha256(chunk_text.encode("utf-8")).hexdigest(),
        "last_ingested_at": now,
        "text": chunk_text,
    }


def chunk_document(document: IngestDocument) -> list[DocumentChunk]:
    chunks: list[DocumentChunk] = []
    for index, body in enumerate(split_text(document.text)):
        chunk_text = build_chunk_text(document, body)
        chunks.append(
            DocumentChunk(
                id=stable_chunk_id(document, index, chunk_text),
                text=chunk_text,
                payload=build_payload(document, chunk_text, index),
            )
        )
    return chunks


def chunk_documents(documents: list[IngestDocument]) -> list[DocumentChunk]:
    chunks: list[DocumentChunk] = []
    for document in documents:
        chunks.extend(chunk_document(document))
    return chunks
