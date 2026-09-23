from typing import Any
from pydantic import BaseModel, Field, model_validator


class Citation(BaseModel):
    chunk_id: str
    document_id: str | None = None
    filename: str = ""
    source_file: str = ""
    page: int | str | None = None
    page_id: str = ""
    section: str = ""

    @model_validator(mode="before")
    @classmethod
    def sync_filenames_and_pages(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Sync filename <-> source_file
            if not data.get("filename") and data.get("source_file"):
                data["filename"] = data["source_file"]
            elif not data.get("source_file") and data.get("filename"):
                data["source_file"] = data["filename"]

            # Sync page <-> page_id
            if data.get("page") is not None and not data.get("page_id"):
                data["page_id"] = str(data["page"])
            elif data.get("page_id") and data.get("page") is None:
                data["page"] = data["page_id"]
        return data


class RAGResponse(BaseModel):
    answer: str
    grounded: bool = Field(description="True only when the supplied context supports the answer.")
    citations: list[Citation] = Field(default_factory=list)


class DocumentMetadata(BaseModel):
    document_id: str
    filename: str
    file_type: str
    file_size: int = 0
    uploaded_at: str
    chunk_count: int = 0
    storage_path: str = ""

