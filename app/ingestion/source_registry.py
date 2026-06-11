from __future__ import annotations

from urllib.parse import urldefrag, urlsplit, urlunsplit

from app.ingestion.models import SourceDefinition

WCAG_QUICKREF_URL = "https://www.w3.org/WAI/WCAG22/quickref/"
WCAG_UNDERSTANDING_URL = "https://www.w3.org/WAI/WCAG22/Understanding/"
WCAG_TECHNIQUES_URL = "https://www.w3.org/WAI/WCAG22/Techniques/"
ARIA_APG_URL = "https://www.w3.org/WAI/ARIA/apg/"

WCAG_CORE_SOURCES = [
    SourceDefinition(
        url=WCAG_QUICKREF_URL,
        source_type="wcag_quickref",
        title="How to Meet WCAG 2.2 Quick Reference",
    ),
    SourceDefinition(
        url=WCAG_UNDERSTANDING_URL,
        source_type="wcag_understanding",
        title="Understanding WCAG 2.2",
    ),
    SourceDefinition(
        url=WCAG_TECHNIQUES_URL,
        source_type="wcag_techniques_index",
        title="All WCAG 2.2 Techniques",
    ),
]

APG_SOURCE = SourceDefinition(
    url=ARIA_APG_URL,
    source_type="aria_apg",
    title="ARIA Authoring Practices Guide",
    wcag_version=None,
)

DEFAULT_SOURCES = WCAG_CORE_SOURCES


def canonical_url(url: str) -> str:
    """Normalize URLs enough to avoid duplicate queue entries."""

    clean, fragment = urldefrag(url)
    split = urlsplit(clean)
    path = split.path
    if path.endswith("/index.html"):
        path = path[: -len("index.html")]
    clean = urlunsplit((split.scheme, split.netloc, path, "", ""))
    if fragment:
        return f"{clean}#{fragment}"
    return clean


def classify_url(url: str, title: str = "") -> SourceDefinition | None:
    """Return a source definition for supported W3C/WAI URLs."""

    clean = canonical_url(url).split("#", 1)[0]
    if not clean.startswith("https://www.w3.org/"):
        return None

    if clean.startswith(WCAG_UNDERSTANDING_URL) and clean != WCAG_UNDERSTANDING_URL:
        return SourceDefinition(
            url=clean,
            source_type="wcag_understanding",
            title=title or "Understanding WCAG 2.2",
        )

    if clean.startswith(WCAG_TECHNIQUES_URL) and clean != WCAG_TECHNIQUES_URL:
        return SourceDefinition(
            url=clean,
            source_type="wcag_technique",
            title=title or "WCAG 2.2 Technique",
        )

    if clean.startswith(ARIA_APG_URL) and clean != ARIA_APG_URL:
        return SourceDefinition(
            url=clean,
            source_type="aria_apg",
            title=title or "ARIA Authoring Practices Guide",
            wcag_version=None,
        )

    return None


def source_priority(source: SourceDefinition) -> int:
    order = {
        "wcag_quickref": 0,
        "wcag_techniques_index": 1,
        "wcag_technique": 2,
        "wcag_understanding": 3,
        "aria_apg": 4,
        "generic": 5,
    }
    return order.get(source.source_type, 99)
