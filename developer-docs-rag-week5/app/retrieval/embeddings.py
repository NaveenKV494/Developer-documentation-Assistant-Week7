from __future__ import annotations

import re
import time
from typing import Any

from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from google import genai
from google.genai import errors, types

from app.config import EMBED_BATCH_SIZE, EMBEDDING_MODEL, require_api_key


class CustomGeminiEmbeddingFunction(EmbeddingFunction):
    """Chroma embedding function backed by Gemini Embedding 2 with rate limit backoff."""

    def __init__(self, api_key: str | None = None):
        self.client = genai.Client(api_key=api_key or require_api_key())

    def __call__(self, input: Documents) -> Embeddings:
        if not input:
            return []

        embeddings: list[list[float]] = []
        batch_size = max(1, EMBED_BATCH_SIZE)

        # Gemini Embedding 2 has rate limits. Keep requests batched and retry 429/503.
        for start in range(0, len(input), batch_size):
            batch = input[start : start + batch_size]
            contents = [
                types.Content(parts=[types.Part.from_text(text=text)])
                for text in batch
            ]

            for attempt in range(5):
                try:
                    response = self.client.models.embed_content(
                        model=EMBEDDING_MODEL,
                        contents=contents,
                    )
                    break
                except errors.ClientError as exc:
                    if getattr(exc, "code", None) != 429 or attempt == 4:
                        raise
                    delay = min(60, 5 * (2 ** attempt))
                    message = str(exc)
                    match = re.search(r"retry in ([0-9]+(?:\.[0-9]+)?)s", message, re.I)
                    if match:
                        delay = min(60, max(delay, float(match.group(1))))
                    print(f"Gemini embedding quota/rate limit; waiting {delay:.1f}s before retry...")
                    time.sleep(delay)
            else:
                raise RuntimeError("Gemini embedding request failed after retries.")

            if len(response.embeddings) != len(batch):
                raise RuntimeError(
                    f"Embedding count mismatch for batch: sent {len(batch)}, "
                    f"received {len(response.embeddings)}."
                )
            embeddings.extend(embedding.values for embedding in response.embeddings)

        if len(embeddings) != len(input):
            raise RuntimeError(
                f"Embedding count mismatch: sent {len(input)}, received {len(embeddings)}."
            )
        return embeddings


def embed_texts(texts: list[str], api_key: str | None = None) -> list[list[float]]:
    """Generate embeddings for a list of strings."""
    fn = CustomGeminiEmbeddingFunction(api_key=api_key)
    return fn(texts)


def embed_query(query: str, api_key: str | None = None) -> list[float]:
    """Generate embedding for a single search query."""
    results = embed_texts([query], api_key=api_key)
    return results[0] if results else []
