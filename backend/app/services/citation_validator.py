"""Citation validation and repair for assistant responses.

Parses ``[S#]`` (document) and ``[M#]`` (memory) citation labels from
assistant output, validates them against the available source/memory
labels, and repairs or strips invalid references before the response is
streamed to the client or persisted to chat history.

Design goals:
- Never modify content during token streaming (UX guarantee).
- Run a single repair pass on the *complete* assistant text before save.
- Be deterministic and side-effect free so unit tests remain stable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple

# Match [S<digits>] and [M<digits>] anywhere in text. Case-sensitive: S/M
# only — lowercase variants are treated as plain text.
_CITATION_RE = re.compile(r"\[(S|M)(\d+)\]")


@dataclass(frozen=True)
class CitationValidationResult:
    """Outcome of validating citations in an assistant response."""

    repaired_content: str
    valid_citations: Tuple[str, ...]
    invalid_citations: Tuple[str, ...]
    invalid_stripped: bool
    has_evidence: bool
    has_any_citation: bool
    uncited_factual_warning: bool


def _label_set(prefix: str, count: int) -> set[str]:
    """Build the set of labels available for the given prefix and count."""
    return {f"{prefix}{i}" for i in range(1, count + 1)}


def _looks_factual(content: str) -> bool:
    """Heuristic: does the content look like it contains factual claims?

    True when the content has more than two sentences and is not a "no-match"
    refusal. Used to decide whether an answer with zero citations should be
    flagged when document/memory evidence is present.
    """
    if not content or len(content) < 80:
        return False
    lower = content.lower()
    refusal_phrases = (
        "not available in the retrieved",
        "i don't have enough",
        "no relevant",
        "the retrieved documents",
    )
    if any(p in lower for p in refusal_phrases):
        return False
    # Count sentence-terminating punctuation.
    return sum(1 for ch in content if ch in ".!?") >= 2


def validate_and_repair_citations(
    content: str,
    *,
    source_count: int,
    memory_count: int,
) -> CitationValidationResult:
    """Validate ``[S#]`` and ``[M#]`` citations in ``content``.

    Args:
        content: Complete assistant response text.
        source_count: Number of document sources available (label range S1..SN).
        memory_count: Number of memories available (label range M1..MN).

    Returns:
        CitationValidationResult with the repaired content, the set of valid
        and invalid labels found, and flags about evidence/warning state.
    """
    if not content:
        return CitationValidationResult(
            repaired_content="",
            valid_citations=(),
            invalid_citations=(),
            invalid_stripped=False,
            has_evidence=source_count > 0 or memory_count > 0,
            has_any_citation=False,
            uncited_factual_warning=False,
        )

    valid_s = _label_set("S", source_count)
    valid_m = _label_set("M", memory_count)

    valid: List[str] = []
    invalid: List[str] = []

    def _replacer(match: re.Match) -> str:
        prefix, num = match.group(1), match.group(2)
        label = f"{prefix}{num}"
        is_valid = (
            (prefix == "S" and label in valid_s)
            or (prefix == "M" and label in valid_m)
        )
        if is_valid:
            valid.append(label)
            return match.group(0)
        invalid.append(label)
        # Strip the invalid citation. Leave a single space so words don't merge.
        return ""

    repaired = _CITATION_RE.sub(_replacer, content)
    # Collapse double spaces introduced by stripped citations.
    repaired = re.sub(r"  +", " ", repaired)
    # Drop spaces left before sentence punctuation when a citation was stripped
    # immediately before it (e.g. "claim . next" -> "claim. next").
    repaired = re.sub(r"\s+([.,;:!?])", r"\1", repaired)
    repaired = repaired.strip()

    has_evidence = source_count > 0 or memory_count > 0
    has_any_citation = bool(valid)
    uncited_factual_warning = (
        has_evidence
        and not has_any_citation
        and _looks_factual(repaired)
    )

    return CitationValidationResult(
        repaired_content=repaired,
        valid_citations=tuple(dict.fromkeys(valid)),
        invalid_citations=tuple(dict.fromkeys(invalid)),
        invalid_stripped=bool(invalid),
        has_evidence=has_evidence,
        has_any_citation=has_any_citation,
        uncited_factual_warning=uncited_factual_warning,
    )


def parse_citations(content: str) -> Tuple[List[str], List[str]]:
    """Return (sources_cited, memories_cited) labels as encountered, deduped.

    Useful for tests and for trace instrumentation. Order matches first
    occurrence in ``content``.
    """
    sources: List[str] = []
    memories: List[str] = []
    for m in _CITATION_RE.finditer(content or ""):
        label = f"{m.group(1)}{m.group(2)}"
        if m.group(1) == "S" and label not in sources:
            sources.append(label)
        elif m.group(1) == "M" and label not in memories:
            memories.append(label)
    return sources, memories


def labels_for_sources(sources: Iterable[dict]) -> List[str]:
    """Return the source_label values for an iterable of source dicts."""
    out: List[str] = []
    for s in sources:
        label = s.get("source_label") if isinstance(s, dict) else None
        if label:
            out.append(label)
    return out


def labels_for_memories(memories: Iterable[dict]) -> List[str]:
    """Return the memory_label values for an iterable of memory dicts."""
    out: List[str] = []
    for m in memories:
        label = m.get("memory_label") if isinstance(m, dict) else None
        if label:
            out.append(label)
    return out


def repair_against_sources_and_memories(
    content: str,
    sources: Sequence[dict],
    memories: Sequence[dict],
) -> CitationValidationResult:
    """Convenience: derive counts from source/memory dicts, then validate.

    Sources are expected to use 1-based ``source_label`` like ``S1``.
    Memories are expected to use 1-based ``memory_label`` like ``M1``.
    Counts default to the maximum index assigned across the inputs so
    sparse labelings (e.g. only S2 and S4) still validate correctly.
    """

    def _max_index(items: Sequence[dict], prefix: str) -> int:
        n = 0
        for it in items:
            if not isinstance(it, dict):
                continue
            label = it.get("source_label" if prefix == "S" else "memory_label")
            if not isinstance(label, str):
                continue
            if label.startswith(prefix) and label[1:].isdigit():
                n = max(n, int(label[1:]))
        return n

    return validate_and_repair_citations(
        content,
        source_count=_max_index(sources, "S"),
        memory_count=_max_index(memories, "M"),
    )


__all__ = [
    "CitationValidationResult",
    "validate_and_repair_citations",
    "parse_citations",
    "labels_for_sources",
    "labels_for_memories",
    "repair_against_sources_and_memories",
]
