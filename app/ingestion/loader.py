from pathlib import Path
from typing import Any

from app.config import DOCUMENTS_DIR, PAGE_TYPE, SDK_VERSION


def load_documents(
    folder_path: str | Path = DOCUMENTS_DIR,
    sdk_version: str = SDK_VERSION,
    page_type: str = PAGE_TYPE,
) -> list[dict[str, Any]]:
    """Load Markdown documentation and attach stable source metadata."""
    folder = Path(folder_path)
    if not folder.exists():
        raise FileNotFoundError(f"Documentation folder not found: {folder}")

    documents: list[dict[str, Any]] = []
    for file_path in sorted(folder.glob("*.md")):
        content = file_path.read_text(encoding="utf-8")
        documents.append(
            {
                "source_file": file_path.name,
                "page_id": file_path.stem,
                "sdk_version": sdk_version,
                "page_type": page_type,
                "text": content,
            }
        )

    if not documents:
        raise ValueError(f"No Markdown documents found in {folder}")

    return documents
