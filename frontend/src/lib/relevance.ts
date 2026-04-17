export type ScoreType = "distance" | "rerank" | "rrf";

export interface RelevanceLabel {
  text: string;
  color: string; // Tailwind text color class
}

/**
 * Returns a descriptive label and color for a relevance score based on score_type and value.
 * - distance: 0=identical, higher=worse. Labels: Highly Relevant, Relevant, Related, Tangential
 * - rerank: 0-1, higher=better. Labels: Highly Relevant, Relevant, Related, Tangential
 * - rrf: Reciprocal Rank Fusion score. Labels: Top Match, Strong Match, Moderate Match, Weak Match
 */
export function getRelevanceLabel(score: number, scoreType?: ScoreType): RelevanceLabel {
  if (!scoreType || scoreType === "distance") {
    // Distance: 0=identical, 0.25=close, 0.5=threshold, 0.75=far
    if (score <= 0.15) return { text: "Highly Relevant", color: "text-success" };
    if (score <= 0.3) return { text: "Relevant", color: "text-success-subdued" };
    if (score <= 0.5) return { text: "Related", color: "text-warning" };
    return { text: "Tangential", color: "text-destructive" };
  }
  if (scoreType === "rerank") {
    // Rerank: 0-1, higher=better
    if (score >= 0.7) return { text: "Highly Relevant", color: "text-success" };
    if (score >= 0.4) return { text: "Relevant", color: "text-success-subdued" };
    if (score >= 0.2) return { text: "Related", color: "text-warning" };
    return { text: "Tangential", color: "text-destructive" };
  }
  // RRF: lower values are less meaningful, use rank-based
  if (score >= 0.5) return { text: "Top Match", color: "text-success" };
  if (score >= 0.2) return { text: "Strong Match", color: "text-success-subdued" };
  if (score >= 0.05) return { text: "Moderate Match", color: "text-warning" };
  return { text: "Weak Match", color: "text-destructive" };
}
