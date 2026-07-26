"""Citation assembly.

Produces one stable :class:`Citation` per source document referenced by the
results, with a human-friendly display name and locator (page/slide/sheet/
section). Citation ids are assigned in order of first appearance so they are
stable for a given result set.
"""

from __future__ import annotations

from synology_rag.domain.models import Citation, RetrievedChunk


def build_citations(chunks: list[RetrievedChunk]) -> list[Citation]:
    order: list[str] = []
    grouped: dict[str, list[RetrievedChunk]] = {}
    for chunk in chunks:
        if chunk.document_id not in grouped:
            grouped[chunk.document_id] = []
            order.append(chunk.document_id)
        grouped[chunk.document_id].append(chunk)

    citations: list[Citation] = []
    for index, document_id in enumerate(order, start=1):
        doc_chunks = grouped[document_id]
        primary = [c for c in doc_chunks if not c.is_neighbour] or doc_chunks
        first = primary[0]
        citations.append(
            Citation(
                citation_id=f"src-{index}",
                document_id=document_id,
                chunk_ids=[c.chunk_id for c in doc_chunks],
                display_name=_display_name(first),
                locator=_locator(primary),
                source_uri=first.source_uri,
                modified_at=first.modified_at,
            )
        )
    return citations


def _display_name(chunk: RetrievedChunk) -> str:
    return chunk.filename or chunk.title or chunk.document_id


def _locator(chunks: list[RetrievedChunk]) -> str | None:
    pages = sorted({c.page_number for c in chunks if c.page_number is not None})
    if pages:
        return f"Page {pages[0]}" if len(pages) == 1 else "Pages " + ", ".join(map(str, pages))
    slides = sorted({c.slide_number for c in chunks if c.slide_number is not None})
    if slides:
        return f"Slide {slides[0]}" if len(slides) == 1 else "Slides " + ", ".join(map(str, slides))
    sheets = [c.sheet_name for c in chunks if c.sheet_name]
    if sheets:
        return f"Sheet '{sheets[0]}'"
    sections = [c.section for c in chunks if c.section]
    if sections:
        return f"Section: {sections[0]}"
    return None
