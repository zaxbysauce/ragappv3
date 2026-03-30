import { describe, it, expect } from "vitest";
import { getRelevanceLabel, type ScoreType } from "./relevance";

describe("getRelevanceLabel", () => {
  // ============================================
  // Distance score type tests (0=identical, higher=worse)
  // ============================================
  describe("distance score type", () => {
    it("test_distance_highly_relevant — getRelevanceLabel(0.1, 'distance').text === 'Highly Relevant'", () => {
      const result = getRelevanceLabel(0.1, "distance");
      expect(result.text).toBe("Highly Relevant");
    });

    it("test_distance_relevant — getRelevanceLabel(0.2, 'distance').text === 'Relevant'", () => {
      const result = getRelevanceLabel(0.2, "distance");
      expect(result.text).toBe("Relevant");
    });

    it("test_distance_related — getRelevanceLabel(0.4, 'distance').text === 'Related'", () => {
      const result = getRelevanceLabel(0.4, "distance");
      expect(result.text).toBe("Related");
    });

    it("test_distance_tangential — getRelevanceLabel(0.6, 'distance').text === 'Tangential'", () => {
      const result = getRelevanceLabel(0.6, "distance");
      expect(result.text).toBe("Tangential");
    });

    it("test_distance_boundary_015 — getRelevanceLabel(0.15, 'distance').text === 'Highly Relevant' (inclusive)", () => {
      const result = getRelevanceLabel(0.15, "distance");
      expect(result.text).toBe("Highly Relevant");
    });

    it("test_distance_boundary_03 — getRelevanceLabel(0.3, 'distance').text === 'Relevant' (inclusive)", () => {
      const result = getRelevanceLabel(0.3, "distance");
      expect(result.text).toBe("Relevant");
    });
  });

  // ============================================
  // Rerank score type tests (0-1, higher=better)
  // ============================================
  describe("rerank score type", () => {
    it("test_rerank_highly_relevant — getRelevanceLabel(0.8, 'rerank').text === 'Highly Relevant'", () => {
      const result = getRelevanceLabel(0.8, "rerank");
      expect(result.text).toBe("Highly Relevant");
    });

    it("test_rerank_tangential — getRelevanceLabel(0.1, 'rerank').text === 'Tangential'", () => {
      const result = getRelevanceLabel(0.1, "rerank");
      expect(result.text).toBe("Tangential");
    });
  });

  // ============================================
  // RRF score type tests (Reciprocal Rank Fusion)
  // ============================================
  describe("rrf score type", () => {
    it("test_rrf_top_match — getRelevanceLabel(0.6, 'rrf').text === 'Top Match'", () => {
      const result = getRelevanceLabel(0.6, "rrf");
      expect(result.text).toBe("Top Match");
    });

    it("test_rrf_weak_match — getRelevanceLabel(0.02, 'rrf').text === 'Weak Match'", () => {
      const result = getRelevanceLabel(0.02, "rrf");
      expect(result.text).toBe("Weak Match");
    });
  });

  // ============================================
  // Default behavior tests
  // ============================================
  describe("default behavior", () => {
    it("test_undefined_score_type_defaults_to_distance — getRelevanceLabel(0.1, undefined).text === 'Highly Relevant'", () => {
      const result = getRelevanceLabel(0.1, undefined);
      expect(result.text).toBe("Highly Relevant");
    });
  });

  // ============================================
  // Label structure tests
  // ============================================
  describe("label structure", () => {
    it("test_all_labels_have_color — Every label result should have a non-empty color string starting with 'text-'", () => {
      const testCases: Array<{ score: number; scoreType: ScoreType | undefined }> = [
        { score: 0.1, scoreType: "distance" },
        { score: 0.2, scoreType: "distance" },
        { score: 0.4, scoreType: "distance" },
        { score: 0.6, scoreType: "distance" },
        { score: 0.8, scoreType: "rerank" },
        { score: 0.1, scoreType: "rerank" },
        { score: 0.6, scoreType: "rrf" },
        { score: 0.02, scoreType: "rrf" },
        { score: 0.1, scoreType: undefined },
      ];

      testCases.forEach(({ score, scoreType }) => {
        const result = getRelevanceLabel(score, scoreType);
        expect(result.color).toBeTruthy();
        expect(result.color.startsWith("text-")).toBe(true);
      });
    });

    it("test_all_labels_have_text — Every label result should have non-empty text", () => {
      const testCases: Array<{ score: number; scoreType: ScoreType | undefined }> = [
        { score: 0.1, scoreType: "distance" },
        { score: 0.2, scoreType: "distance" },
        { score: 0.4, scoreType: "distance" },
        { score: 0.6, scoreType: "distance" },
        { score: 0.8, scoreType: "rerank" },
        { score: 0.1, scoreType: "rerank" },
        { score: 0.6, scoreType: "rrf" },
        { score: 0.02, scoreType: "rrf" },
        { score: 0.1, scoreType: undefined },
      ];

      testCases.forEach(({ score, scoreType }) => {
        const result = getRelevanceLabel(score, scoreType);
        expect(result.text).toBeTruthy();
        expect(result.text.length).toBeGreaterThan(0);
      });
    });
  });
});
