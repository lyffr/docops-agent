from __future__ import annotations

import re
from hashlib import sha1

from .models import DocumentChunk, ParsedSection

PARAGRAPH_SPLIT = re.compile(r"\n\s*\n+")


def _stable_chunk_id(document_id: str, page: int | None, index: int, content: str) -> str:
    digest = sha1(f"{document_id}:{page}:{index}:{content}".encode()).hexdigest()[:12]
    return f"chk-{digest}"


def split_text(text: str, max_chars: int = 520, overlap_chars: int = 80) -> list[str]:
    if max_chars <= 0 or overlap_chars < 0 or overlap_chars >= max_chars:
        raise ValueError("Require max_chars > overlap_chars >= 0")

    paragraphs = [item.strip() for item in PARAGRAPH_SPLIT.split(text) if item.strip()]
    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            step = max_chars - overlap_chars
            chunks.extend(
                paragraph[start : start + max_chars]
                for start in range(0, len(paragraph), step)
                if paragraph[start : start + max_chars].strip()
            )
            continue

        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
            continue

        chunks.append(current)
        overlap = current[-overlap_chars:] if overlap_chars else ""
        current = f"{overlap}\n\n{paragraph}".strip()

    if current:
        chunks.append(current)
    return chunks


def chunk_sections(
    document_id: str,
    title: str,
    sections: list[ParsedSection],
    max_chars: int = 520,
    overlap_chars: int = 80,
) -> list[DocumentChunk]:
    chunks: list[DocumentChunk] = []
    for section in sections:
        for content in split_text(section.text, max_chars, overlap_chars):
            index = len(chunks)
            chunks.append(
                DocumentChunk(
                    id=_stable_chunk_id(document_id, section.page, index, content),
                    document_id=document_id,
                    title=title,
                    content=content,
                    page=section.page,
                )
            )
    return chunks

