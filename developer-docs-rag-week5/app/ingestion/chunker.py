from __future__ import annotations

import re
from typing import Any, Iterable


FENCE_RE = re.compile(r"^\s*(```+|~~~+)\s*(.*)$")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")


def _split_blocks(text: str) -> list[dict[str, str]]:
    """Parse Markdown into semantic blocks without splitting fenced code or tables."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks: list[dict[str, str]] = []
    paragraph: list[str] = []
    i = 0
    current_heading = ""

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            value = "\n".join(paragraph).strip()
            if value:
                blocks.append({"kind": "text", "text": value, "heading": current_heading})
            paragraph = []

    while i < len(lines):
        line = lines[i]
        fence = FENCE_RE.match(line)

        if fence:
            flush_paragraph()
            fence_marker = fence.group(1)
            fence_lines = [line]
            i += 1
            while i < len(lines):
                fence_lines.append(lines[i])
                if lines[i].lstrip().startswith(fence_marker[0] * len(fence_marker)):
                    i += 1
                    break
                i += 1
            blocks.append(
                {
                    "kind": "code",
                    "text": "\n".join(fence_lines).strip(),
                    "heading": current_heading,
                }
            )
            continue

        heading = HEADING_RE.match(line)
        if heading:
            flush_paragraph()
            current_heading = heading.group(2).strip()
            blocks.append(
                {"kind": "heading", "text": line.strip(), "heading": current_heading}
            )
            i += 1
            continue

        # Treat a Markdown table (header + separator + rows) as one indivisible block.
        if i + 1 < len(lines) and "|" in line and TABLE_SEPARATOR_RE.match(lines[i + 1]):
            flush_paragraph()
            table_lines = [line, lines[i + 1]]
            i += 2
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                table_lines.append(lines[i])
                i += 1
            blocks.append(
                {"kind": "table", "text": "\n".join(table_lines).strip(), "heading": current_heading}
            )
            continue

        if not line.strip():
            flush_paragraph()
            i += 1
            continue

        paragraph.append(line)
        i += 1

    flush_paragraph()
    return blocks


def _pack_blocks(
    blocks: list[dict[str, Any]],
    chunk_size: int,
    chunk_overlap: int,
) -> list[dict[str, Any]]:
    """Pack semantic blocks while never splitting a code fence or table."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be >= 0 and smaller than chunk_size")

    chunks: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    current_len = 0

    def emit(blocks_to_emit: list[dict[str, Any]]) -> None:
        if not blocks_to_emit:
            return
        text = "\n\n".join(block["text"] for block in blocks_to_emit).strip()
        if not text:
            return
        headings = [b["heading"] for b in blocks_to_emit if b.get("heading")]
        pages = [b["page"] for b in blocks_to_emit if b.get("page")]
        chunks.append(
            {
                "text": text,
                "section": headings[-1] if headings else "",
                "page": pages[0] if pages else 1,
                "block_kinds": sorted({b.get("kind", "text") for b in blocks_to_emit}),
            }
        )

    for block in blocks:
        block_len = len(block["text"])
        separator_len = 2 if current else 0

        # A protected block can exceed the target size. Keep it whole rather than
        # corrupting a code sample/table. This is an intentional structure-first trade-off.
        if current and current_len + separator_len + block_len > chunk_size:
            emit(current)

            overlap_blocks: list[dict[str, Any]] = []
            overlap_len = 0
            for previous in reversed(current):
                candidate_len = len(previous["text"]) + (2 if overlap_blocks else 0)
                if overlap_len + candidate_len > chunk_overlap:
                    break
                overlap_blocks.insert(0, previous)
                overlap_len += candidate_len

            current = overlap_blocks
            current_len = sum(len(b["text"]) for b in current) + max(0, len(current) - 1) * 2

        current.append(block)
        current_len += block_len + (2 if len(current) > 1 else 0)

    emit(current)
    return chunks



def chunk_documents(
    documents: Iterable[dict[str, Any]],
    chunk_size: int = 1200,
    chunk_overlap: int = 200,
    strategy: str = "structure",
) -> list[dict[str, Any]]:
    """Create chunks using either the baseline or structure-aware strategy."""
    if strategy == "baseline":
        return _baseline_chunks(documents, chunk_size, chunk_overlap)
    if strategy == "structure":
        return _structure_aware_chunks(documents, chunk_size, chunk_overlap)
    raise ValueError("strategy must be 'baseline' or 'structure'")


def chunk_parsed_document(
    blocks: list[Any],
    document_id: str,
    filename: str,
    chunk_size: int = 1200,
    chunk_overlap: int = 200,
    strategy: str = "structure",
) -> list[dict[str, Any]]:
    """Chunk parsed document blocks into indexed chunk records."""
    raw_blocks: list[dict[str, Any]] = []
    for b in blocks:
        if hasattr(b, "__dict__"):
            raw_blocks.append({
                "text": b.text,
                "page": getattr(b, "page", 1),
                "heading": getattr(b, "section", ""),
                "kind": getattr(b, "kind", "text"),
            })
        elif isinstance(b, dict):
            raw_blocks.append({
                "text": b.get("text", ""),
                "page": b.get("page", 1),
                "heading": b.get("section", b.get("heading", "")),
                "kind": b.get("kind", "text"),
            })

    chunks: list[dict[str, Any]] = []

    if strategy == "baseline":
        full_text = "\n\n".join(b["text"] for b in raw_blocks if b.get("text"))
        start = 0
        index = 0
        while start < len(full_text):
            end = min(start + chunk_size, len(full_text))
            chunk_text = full_text[start:end]
            chunks.append(
                {
                    "chunk_id": f"{document_id}-chunk-{index}",
                    "document_id": document_id,
                    "filename": filename,
                    "source_file": filename,
                    "page": 1,
                    "page_id": "1",
                    "section": "",
                    "chunk_index": index,
                    "chunk_strategy": "baseline",
                    "block_kinds": ["raw"],
                    "text": chunk_text,
                }
            )
            index += 1
            if end == len(full_text):
                break
            start = end - chunk_overlap
        return chunks

    packed = _pack_blocks(raw_blocks, chunk_size, chunk_overlap)
    for index, item in enumerate(packed):
        chunks.append(
            {
                "chunk_id": f"{document_id}-chunk-{index}",
                "document_id": document_id,
                "filename": filename,
                "source_file": filename,
                "page": item.get("page", 1),
                "page_id": str(item.get("page", 1)),
                "section": item.get("section", ""),
                "chunk_index": index,
                "chunk_strategy": "structure",
                "block_kinds": item.get("block_kinds", ["text"]),
                "text": item.get("text", ""),
            }
        )
    return chunks


def _baseline_chunks(documents: Iterable[dict[str, Any]], chunk_size: int, chunk_overlap: int) -> list[dict[str, Any]]:
    if chunk_size <= 0 or chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("Invalid chunk_size/chunk_overlap")

    chunks: list[dict[str, Any]] = []
    for doc in documents:
        text = doc["text"]
        start = 0
        index = 0
        doc_id = doc.get("document_id", doc.get("page_id", "doc"))
        filename = doc.get("filename", doc.get("source_file", "unknown"))
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunk_text = text[start:end]
            chunks.append(
                {
                    "document_id": doc_id,
                    "filename": filename,
                    "source_file": doc.get("source_file", filename),
                    "page_id": str(doc.get("page_id", "1")),
                    "page": doc.get("page", 1),
                    "sdk_version": doc.get("sdk_version", ""),
                    "page_type": doc.get("page_type", ""),
                    "chunk_id": f"{doc.get('page_id', doc_id)}-{doc.get('sdk_version', 'v1')}-baseline-{index}",
                    "chunk_index": index,
                    "chunk_strategy": "baseline",
                    "section": "",
                    "block_kinds": ["raw"],
                    "text": chunk_text,
                }
            )
            index += 1
            if end == len(text):
                break
            start = end - chunk_overlap
    return chunks


def _structure_aware_chunks(documents: Iterable[dict[str, Any]], chunk_size: int, chunk_overlap: int) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for doc in documents:
        blocks = _split_blocks(doc["text"])
        packed = _pack_blocks(blocks, chunk_size, chunk_overlap)
        doc_id = doc.get("document_id", doc.get("page_id", "doc"))
        filename = doc.get("filename", doc.get("source_file", "unknown"))
        for index, item in enumerate(packed):
            chunks.append(
                {
                    "document_id": doc_id,
                    "filename": filename,
                    "source_file": doc.get("source_file", filename),
                    "page_id": str(doc.get("page_id", item.get("page", 1))),
                    "page": item.get("page", 1),
                    "sdk_version": doc.get("sdk_version", ""),
                    "page_type": doc.get("page_type", ""),
                    "chunk_id": f"{doc.get('page_id', doc_id)}-{doc.get('sdk_version', 'v1')}-structure-{index}",
                    "chunk_index": index,
                    "chunk_strategy": "structure",
                    "section": item["section"],
                    "block_kinds": item["block_kinds"],
                    "text": item["text"],
                }
            )
    return chunks



if __name__ == "__main__":
    from app.ingestion.loader import load_documents

    docs = load_documents()
    for strategy in ("baseline", "structure"):
        chunks = chunk_documents(docs, chunk_size=1200, chunk_overlap=200, strategy=strategy)
        print(f"{strategy}: {len(chunks)} chunks")
        for chunk in chunks[:3]:
            print("\n---", chunk["chunk_id"], "---")
            print(chunk["text"][:700])
