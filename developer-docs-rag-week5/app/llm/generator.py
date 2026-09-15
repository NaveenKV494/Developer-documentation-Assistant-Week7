import re
import time

from google import genai
from google.genai import types

from app.config import GENERATION_MODEL, require_api_key
from app.models.response import RAGResponse


REFUSAL = "I couldn't find that information in the provided documentation."

# Retry configuration
MAX_RETRIES = 5
INITIAL_BACKOFF_SECONDS = 2
MAX_BACKOFF_SECONDS = 75



def _get_status_code(exc: Exception) -> int | None:
    """Best-effort extraction of an HTTP/status code from a Gemini exception."""
    for attr in ("code", "status_code", "status"):
        value = getattr(exc, attr, None)

        if isinstance(value, int):
            return value

        if isinstance(value, str):
            match = re.search(r"\b(429|500|502|503|504)\b", value)
            if match:
                return int(match.group(1))

    return None


def _is_retryable_error(exc: Exception) -> bool:
    """
    Return True only for transient service/rate-limit errors.

    We intentionally do not retry arbitrary client errors because those are
    usually caused by invalid requests, authentication, bad configuration,
    or invalid model parameters.
    """
    status_code = _get_status_code(exc)

    if status_code in (503, 429):
        return True

    message = str(exc).lower()

    # Fallback for SDK exceptions where the status code is not exposed
    # directly on the exception object.
    if "503" in message or "unavailable" in message:
        return True

    if "429" in message or "resource_exhausted" in message:
        return True

    return False


def _get_retry_delay(exc: Exception, attempt: int) -> float:
    """
    Determine how long to wait before retrying.

    If Gemini provides an explicit retry delay (for example:
    'Please retry in 35.270241994s'), use it.

    Otherwise fall back to bounded exponential backoff:
    2s -> 4s -> 8s ...
    """
    message = str(exc)

    retry_match = re.search(
        r"retry(?:\s+in)?\s+([0-9]+(?:\.[0-9]+)?)\s*s",
        message,
        re.IGNORECASE,
    )

    if retry_match:
        provider_delay = float(retry_match.group(1))
        return min(provider_delay + 2.0, MAX_BACKOFF_SECONDS)


    exponential_delay = INITIAL_BACKOFF_SECONDS * (2 ** attempt)

    return min(exponential_delay, MAX_BACKOFF_SECONDS)


def _generate_content_with_retry(
    client: genai.Client,
    prompt: str,
):
    """
    Call Gemini with bounded retry handling and automatic model rotation
    if a daily free-tier model quota is exhausted.
    """
    models_to_try = [GENERATION_MODEL]
    for fallback in ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.5-flash"]:
        if fallback not in models_to_try:
            models_to_try.append(fallback)

    last_exc = None
    for model_name in models_to_try:
        for attempt in range(MAX_RETRIES + 1):
            try:
                return client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=RAGResponse,
                        temperature=0,
                    ),
                )
            except Exception as exc:
                last_exc = exc
                err_msg = str(exc).lower()
                # If daily quota exhausted for this model, rotate to next model immediately
                if "perday" in err_msg or "daily" in err_msg:
                    print(f"Model {model_name} daily quota exhausted. Rotating to next model...")
                    break
                if not _is_retryable_error(exc) or attempt >= MAX_RETRIES:
                    break
                delay = _get_retry_delay(exc, attempt)
                print(f"Gemini {model_name} rate limited; retrying in {delay:.1f}s...")
                time.sleep(delay)

    raise RuntimeError(f"Gemini generation failed across all available models: {last_exc}") from last_exc



def generate_answer(prompt: str) -> RAGResponse:
    client = genai.Client(api_key=require_api_key())

    response = _generate_content_with_retry(client, prompt)

    try:
        result = (
            RAGResponse.model_validate(response.parsed)
            if getattr(response, "parsed", None) is not None
            else RAGResponse.model_validate_json(response.text)
        )
    except Exception as exc:
        raise RuntimeError(
            f"Invalid structured model output: {exc}"
        ) from exc

    return result