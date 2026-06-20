from __future__ import annotations

import re
from urllib.parse import urljoin, urldefrag

from bs4 import BeautifulSoup, Tag

from models import IngestDocument, ParsedSource, SourceDefinition
from source_registry import classify_url

PRINCIPLE_MAP = {
    "1": "Perceivable",
    "2": "Operable",
    "3": "Understandable",
    "4": "Robust",
}

CRITERION_RE = re.compile(r"^(\d+\.\d+\.\d+)\s+(.+)$")
LEVEL_RE = re.compile(r"\bLevel\s+(A{1,3})\b")
TECHNIQUE_RE = re.compile(r"^([A-Z]+\d+):\s*(.+)$")
FAILURE_RE = re.compile(r"^(F\d+):\s*(.+)$")


def clean_text(node: Tag | BeautifulSoup | None) -> str:
    if node is None:
        return ""
    return " ".join(node.get_text(" ", strip=True).split())


def section_text(start: Tag, stop_names: set[str]) -> str:
    parts: list[str] = []
    for sibling in start.find_all_next():
        if sibling is start:
            continue
        if sibling.name in stop_names:
            break
        if sibling.name in {"p", "li", "pre", "code"}:
            text = clean_text(sibling)
            if text and text not in parts:
                parts.append(text)
    return "\n".join(parts)


def infer_principle(criterion_id: str | None) -> str | None:
    if not criterion_id:
        return None
    return PRINCIPLE_MAP.get(criterion_id.split(".")[0])


def infer_guideline(criterion_id: str | None) -> str | None:
    if not criterion_id:
        return None
    parts = criterion_id.split(".")
    if len(parts) < 2:
        return None
    return f"{parts[0]}.{parts[1]}"


def discover_official_links(soup: BeautifulSoup, base_url: str) -> list[SourceDefinition]:
    discovered: dict[str, SourceDefinition] = {}
    for link in soup.find_all("a", href=True):
        absolute = urljoin(base_url, link["href"])
        clean, _ = urldefrag(absolute)
        source = classify_url(clean, clean_text(link))
        if source:
            discovered[source.url] = source
    return list(discovered.values())


def parse_quickref(html: str, source: SourceDefinition) -> ParsedSource:
    soup = BeautifulSoup(html, "html.parser")
    documents: list[IngestDocument] = []
    seen: set[str] = set()

    for heading in soup.find_all(["h4", "h3"]):
        heading_text = clean_text(heading)
        match = CRITERION_RE.match(heading_text)
        if not match:
            continue

        criterion_id, title = match.groups()
        if criterion_id == "4.1.1" or criterion_id in seen:
            continue
        seen.add(criterion_id)

        section = heading.find_parent("section") or heading.parent
        section_body = clean_text(section)
        level_match = LEVEL_RE.search(section_body)
        level = level_match.group(1) if level_match else None
        source_url = urljoin(source.url, f"#{section.get('id')}") if isinstance(section, Tag) and section.get("id") else source.url

        techniques: list[str] = []
        failures: list[str] = []
        related_urls: list[str] = []
        if isinstance(section, Tag):
            for link in section.find_all("a", href=True):
                text = clean_text(link)
                absolute = urljoin(source.url, link["href"])
                if TECHNIQUE_RE.match(text):
                    techniques.append(text)
                    related_urls.append(urldefrag(absolute)[0])
                elif FAILURE_RE.match(text):
                    failures.append(text)
                    related_urls.append(urldefrag(absolute)[0])
                elif "Understanding" in text:
                    related_urls.append(urldefrag(absolute)[0])

        description_parts: list[str] = []
        if isinstance(section, Tag):
            for child in section.find_all(["p", "li"], recursive=True):
                text = clean_text(child)
                if text and not text.startswith(("Sufficient Techniques", "Advisory Techniques", "Failures")):
                    description_parts.append(text)
        text = "\n".join(dict.fromkeys(description_parts)) or title

        tags = []
        for item in [*techniques, *failures]:
            code = item.split(":", 1)[0]
            if code:
                tags.append(code)

        documents.append(
            IngestDocument(
                doc_type="success_criterion",
                source_url=source_url,
                source_title=source.title,
                title=f"WCAG {criterion_id}: {title}",
                text=text,
                wcag_version=source.wcag_version,
                criterion_id=criterion_id,
                level=level,
                principle=infer_principle(criterion_id),
                guideline=infer_guideline(criterion_id),
                tags=sorted(set(tags)),
                related_urls=sorted(set(related_urls)),
            )
        )

    return ParsedSource(
        documents=documents,
        discovered_sources=discover_official_links(soup, source.url),
    )


def criterion_from_page(soup: BeautifulSoup) -> str | None:
    text = clean_text(soup.find(["h1", "h2"]))
    match = re.search(r"(\d+\.\d+\.\d+)", text)
    return match.group(1) if match else None


def parse_understanding(html: str, source: SourceDefinition) -> ParsedSource:
    soup = BeautifulSoup(html, "html.parser")
    title = clean_text(soup.find("h1")) or source.title
    criterion_id = criterion_from_page(soup)

    documents: list[IngestDocument] = []
    headings = soup.find_all(["h2", "h3"])
    if not headings:
        body_text = clean_text(soup.find("main") or soup.body or soup)
        if body_text:
            documents.append(
                IngestDocument(
                    doc_type="understanding",
                    source_url=source.url,
                    source_title=source.title,
                    title=title,
                    text=body_text,
                    wcag_version=source.wcag_version,
                    criterion_id=criterion_id,
                    principle=infer_principle(criterion_id),
                    guideline=infer_guideline(criterion_id),
                )
            )
    else:
        for heading in headings:
            heading_title = clean_text(heading)
            text = section_text(heading, {"h2", "h3"})
            if not text:
                continue
            documents.append(
                IngestDocument(
                    doc_type="understanding",
                    source_url=f"{source.url}#{heading.get('id')}" if heading.get("id") else source.url,
                    source_title=source.title,
                    title=f"{title} - {heading_title}",
                    text=text,
                    wcag_version=source.wcag_version,
                    criterion_id=criterion_id,
                    principle=infer_principle(criterion_id),
                    guideline=infer_guideline(criterion_id),
                )
            )

    return ParsedSource(
        documents=documents,
        discovered_sources=discover_official_links(soup, source.url),
    )


def parse_technique(html: str, source: SourceDefinition) -> ParsedSource:
    soup = BeautifulSoup(html, "html.parser")
    title = clean_text(soup.find("h1")) or source.title
    match = TECHNIQUE_RE.match(title) or FAILURE_RE.match(title)
    technique_id = match.group(1) if match else None
    doc_type = "failure" if technique_id and technique_id.startswith("F") else "technique"
    technology = None
    if technique_id:
        technology_prefix = re.match(r"^[A-Z]+", technique_id)
        technology = technology_prefix.group(0) if technology_prefix else None

    documents: list[IngestDocument] = []
    headings = soup.find_all(["h2", "h3"])
    for heading in headings:
        heading_title = clean_text(heading)
        text = section_text(heading, {"h2", "h3"})
        if not text:
            continue
        documents.append(
            IngestDocument(
                doc_type=doc_type,
                source_url=f"{source.url}#{heading.get('id')}" if heading.get("id") else source.url,
                source_title=source.title,
                title=f"{title} - {heading_title}",
                text=text,
                wcag_version=source.wcag_version,
                technique_id=technique_id,
                technology=technology,
            )
        )

    if not documents:
        body_text = clean_text(soup.find("main") or soup.body or soup)
        if body_text:
            documents.append(
                IngestDocument(
                    doc_type=doc_type,
                    source_url=source.url,
                    source_title=source.title,
                    title=title,
                    text=body_text,
                    wcag_version=source.wcag_version,
                    technique_id=technique_id,
                    technology=technology,
                )
            )

    return ParsedSource(
        documents=documents,
        discovered_sources=discover_official_links(soup, source.url),
    )


def parse_techniques_index(html: str, source: SourceDefinition) -> ParsedSource:
    soup = BeautifulSoup(html, "html.parser")
    return ParsedSource(
        documents=[],
        discovered_sources=discover_official_links(soup, source.url),
    )


def parse_aria_apg(html: str, source: SourceDefinition) -> ParsedSource:
    soup = BeautifulSoup(html, "html.parser")
    title = clean_text(soup.find("h1")) or source.title
    main = soup.find("main") or soup.body or soup
    text = clean_text(main)
    documents = []
    if text:
        documents.append(
            IngestDocument(
                doc_type="aria_pattern" if "/patterns/" in source.url else "reference",
                source_url=source.url,
                source_title=source.title,
                title=title,
                text=text,
                wcag_version=None,
            )
        )
    return ParsedSource(
        documents=documents,
        discovered_sources=discover_official_links(soup, source.url),
    )


def parse_source(html: str, source: SourceDefinition) -> ParsedSource:
    if source.source_type == "wcag_quickref":
        return parse_quickref(html, source)
    if source.source_type == "wcag_understanding":
        return parse_understanding(html, source)
    if source.source_type == "wcag_technique":
        return parse_technique(html, source)
    if source.source_type == "wcag_techniques_index":
        return parse_techniques_index(html, source)
    if source.source_type == "aria_apg":
        return parse_aria_apg(html, source)
    soup = BeautifulSoup(html, "html.parser")
    text = clean_text(soup.find("main") or soup.body or soup)
    return ParsedSource(
        documents=[
            IngestDocument(
                doc_type="reference",
                source_url=source.url,
                source_title=source.title,
                title=clean_text(soup.find("h1")) or source.title,
                text=text,
                wcag_version=source.wcag_version,
            )
        ] if text else [],
        discovered_sources=discover_official_links(soup, source.url),
    )
