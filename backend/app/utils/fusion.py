"""Fusion utilities for combining search results."""

from typing import Any, Dict, List, Optional


def rrf_fuse(
    result_lists: List[List[Dict[str, Any]]],
    k: int = 60,
    limit: Optional[int] = None,
    recency_scores: Optional[Dict[str, float]] = None,
    recency_weight: float = 0.0,
) -> List[Dict[str, Any]]:
    """
    Reciprocal Rank Fusion (RRF) for combining multiple result lists.

    Args:
        result_lists: List of result lists, each from a different query/scale/source
        k: RRF constant (default 60)
        limit: Maximum results to return (None = return all)
        recency_scores: Optional dict mapping record id → normalized recency score (0.0-1.0,
            where 1.0 = most recent). When provided, recency is blended into the final score.
            Records missing from recency_scores receive a neutral score of 0.5.
        recency_weight: Weight for recency blending (0.0 = disabled, default 0.0).
            Final score = rrf_score * (1 - recency_weight) + recency_score * recency_weight.

    Returns:
        Deduplicated, scored results sorted by final score descending.
        Each result has '_rrf_score' field added.
    """
    rrf_scores: Dict[str, float] = {}
    id_to_record: Dict[str, Dict[str, Any]] = {}

    for results in result_lists:
        for rank, record in enumerate(results):
            uid = record.get("id", f"rank_{rank}")
            # RRF formula: 1 / (k + rank + 1)
            score = 1.0 / (k + rank + 1)
            rrf_scores[uid] = rrf_scores.get(uid, 0.0) + score
            if uid not in id_to_record:
                id_to_record[uid] = record

    # Apply recency blending when provided
    if recency_scores and recency_weight > 0.0:
        blended: Dict[str, float] = {}
        for uid, rrf_score in rrf_scores.items():
            rec_score = recency_scores.get(uid, 0.5)  # neutral for missing
            blended[uid] = (
                rrf_score * (1.0 - recency_weight) + rec_score * recency_weight
            )
        sorted_uids = sorted(blended.keys(), key=lambda u: blended[u], reverse=True)
        final_scores = blended
    else:
        sorted_uids = sorted(
            rrf_scores.keys(), key=lambda u: rrf_scores[u], reverse=True
        )
        final_scores = rrf_scores

    # Build result list
    fused = []
    for uid in sorted_uids[:limit] if limit else sorted_uids:
        record = dict(id_to_record[uid])
        record["_rrf_score"] = final_scores[uid]
        fused.append(record)

    return fused
