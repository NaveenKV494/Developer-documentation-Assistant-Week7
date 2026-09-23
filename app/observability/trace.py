"""Complete request traces for error analysis and observability."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import json
import time
from typing import Any
import uuid


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RetrievedChunkTrace:
    rank: int
    score: float | None = None
    distance: float | None = None
    chunk_id: str | None = None
    document_id: str | None = None
    filename: str | None = None
    source_file: str | None = None
    page: int | str | None = None
    page_id: str | None = None
    section: str | None = None
    sdk_version: str | None = None
    page_type: str | None = None
    text: str = ""

    def __post_init__(self) -> None:
        if not self.filename and self.source_file:
            self.filename = self.source_file
        elif not self.source_file and self.filename:
            self.source_file = self.filename

        if self.page is not None and not self.page_id:
            self.page_id = str(self.page)
        elif self.page_id and self.page is None:
            self.page = self.page_id


@dataclass
class Trace:
    trace_id: str
    timestamp: str
    question: str
    retrieval_strategy: str = "structure"
    top_k: int = 5
    sdk_version_filter: str | None = None
    document_ids: list[str] = field(default_factory=list)
    document_names: list[str] = field(default_factory=list)
    retrieval_query: str = ""
    retrieved_chunks: list[RetrievedChunkTrace] = field(default_factory=list)
    retrieval_scores: list[float] = field(default_factory=list)
    generation_model: str | None = None
    answer: str | None = None
    grounded: bool | None = None
    citations: list[dict[str, Any]] = field(default_factory=list)
    latency: float | None = None
    latency_ms: float | None = None
    errors: str | None = None
    error: str | None = None
    _start_time: float = field(default=0.0, repr=False)

    @classmethod
    def new(
        cls,
        question: str,
        strategy: str = "structure",
        top_k: int = 5,
        sdk_version_filter: str | None = None,
        document_ids: list[str] | None = None,
        document_names: list[str] | None = None,
        retrieval_query: str | None = None,
    ) -> Trace:
        t = cls(
            trace_id=str(uuid.uuid4()),
            timestamp=utc_now_iso(),
            question=question,
            retrieval_strategy=strategy,
            top_k=top_k,
            sdk_version_filter=sdk_version_filter,
            document_ids=document_ids or [],
            document_names=document_names or [],
            retrieval_query=retrieval_query or question,
        )
        t.start_timer()
        return t

    def start_timer(self) -> None:
        self._start_time = time.perf_counter()

    def stop_timer(self) -> None:
        if self._start_time > 0:
            elapsed = time.perf_counter() - self._start_time
            self.latency = round(elapsed, 4)
            self.latency_ms = round(elapsed * 1000.0, 2)

    def set_error(self, err_msg: str) -> None:
        self.error = err_msg
        self.errors = err_msg

    def to_dict(self) -> dict[str, Any]:
        if self.error and not self.errors:
            self.errors = self.error
        elif self.errors and not self.error:
            self.error = self.errors
        data = asdict(self)
        data.pop("_start_time", None)
        return data


def save_trace(trace: Trace, path: str | Path = "traces/raw/traces.jsonl") -> None:
    trace.stop_timer()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(trace.to_dict(), ensure_ascii=False) + "\n")

