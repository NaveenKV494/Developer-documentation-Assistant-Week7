from __future__ import annotations

import re
from typing import Any

from app.llm.prompts import REFUSAL


REFUSAL_PATTERNS = [
    r"couldn't find that information",
    r"could not find that information",
    r"not mentioned in the provided documentation",
    r"not found in the provided documentation",
    r"no information provided",
]


def is_refusal(text: str) -> bool:
    """Check if the answer text corresponds to a standard refusal."""
    clean = text.lower().strip()
    return any(re.search(pat, clean) for pat in REFUSAL_PATTERNS)


def check_refusal_behavior(is_unsupported: bool, answer: str, grounded: bool) -> tuple[bool, str]:
    """Verify that unsupported questions are refused and supported questions are answered."""
    refused = is_refusal(answer)

    if is_unsupported:
        if refused and not grounded:
            return True, "Correctly refused unsupported question with grounded=False"
        elif refused and grounded:
            return False, "Refusal text returned, but grounded was incorrectly marked True"
        else:
            return False, f"Failed to refuse unsupported question: gave answer '{answer[:60]}...'"
    else:
        if refused:
            return False, "False refusal: question was supported by docs but assistant refused"
        if not grounded:
            return False, "Answer returned but grounded was marked False"
        return True, "Successfully answered supported question without refusing"


def check_citation_presence(is_unsupported: bool, citations: list[Any]) -> tuple[bool, str]:
    """Verify citation presence: 0 citations for refusals, >=1 citations for supported answers."""
    if is_unsupported:
        if len(citations) == 0:
            return True, "Correctly returned zero citations for refusal"
        return False, f"Returned {len(citations)} citations on an unsupported question (expected 0)"
    else:
        if len(citations) > 0:
            return True, f"Returned {len(citations)} citations for supported answer"
        return False, "Missing citations on a supported factual answer"


def check_citation_validity(citations: list[Any], retrieved_chunks: list[dict]) -> tuple[bool, str]:
    """Verify that every cited chunk_id actually exists in the retrieved context."""
    if not citations:
        return True, "No citations to validate"

    available_chunk_ids = {
        str(chunk.get("chunk_id", ""))
        for chunk in retrieved_chunks
        if chunk.get("chunk_id")
    }

    invalid_ids = []
    for c in citations:
        cid = getattr(c, "chunk_id", None) or (c.get("chunk_id") if isinstance(c, dict) else str(c))
        if cid not in available_chunk_ids:
            invalid_ids.append(cid)

    if invalid_ids:
        return False, f"Hallucinated chunk IDs not in context: {invalid_ids}"
    return True, f"All {len(citations)} citations strictly match retrieved context chunks"


def check_key_facts(is_unsupported: bool, answer: str, key_facts: list[str]) -> tuple[bool, str]:
    """Check if key required facts appear in the answer for supported questions."""
    if is_unsupported or not key_facts:
        return True, "N/A for unsupported or empty key facts"

    answer_lower = answer.lower()
    missing = []
    for fact in key_facts:
        if fact.lower() not in answer_lower:
            # Also test words individually if fact contains multiple keywords
            words = [w for w in re.split(r"\W+", fact.lower()) if len(w) > 3]
            if not any(w in answer_lower for w in words):
                missing.append(fact)

    if missing:
        return False, f"Missing expected key fact(s): {missing}"
    return True, "All key facts present in response"


def run_rule_assertions(
    test_case: dict[str, Any],
    rag_response: Any,
    retrieved_chunks: list[dict],
) -> dict[str, Any]:
    """Run all deterministic rule-based checks on a single test result."""
    is_unsupported = test_case.get("is_unsupported", False)
    answer = getattr(rag_response, "answer", "") or ""
    grounded = getattr(rag_response, "grounded", False)
    citations = getattr(rag_response, "citations", []) or []
    key_facts = test_case.get("key_facts", [])

    refusal_ok, refusal_msg = check_refusal_behavior(is_unsupported, answer, grounded)
    presence_ok, presence_msg = check_citation_presence(is_unsupported, citations)
    validity_ok, validity_msg = check_citation_validity(citations, retrieved_chunks)
    facts_ok, facts_msg = check_key_facts(is_unsupported, answer, key_facts)

    checks = {
        "refusal_behavior": {"passed": refusal_ok, "detail": refusal_msg},
        "citation_presence": {"passed": presence_ok, "detail": presence_msg},
        "citation_authenticity": {"passed": validity_ok, "detail": validity_msg},
        "key_facts_coverage": {"passed": facts_ok, "detail": facts_msg},
    }

    passed_count = sum(1 for c in checks.values() if c["passed"])
    total_count = len(checks)
    overall_passed = (passed_count == total_count)

    return {
        "passed": overall_passed,
        "passed_count": passed_count,
        "total_count": total_count,
        "pass_rate": round(passed_count / total_count, 3),
        "checks": checks,
    }
