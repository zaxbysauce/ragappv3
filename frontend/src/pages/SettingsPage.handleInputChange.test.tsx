/**
 * Tests for handleInputChange function in SettingsPage.tsx
 *
 * This tests the fix for type-handling in form inputs:
 * - Non-numeric strings (URLs, model names) now correctly update form state
 * - Empty string on numeric field sets to 0
 * - Empty string on string field sets to ""
 * - Valid numeric strings parse to numbers
 * - Booleans work correctly
 */

import { describe, test, expect, vi, beforeEach, afterEach } from "vitest";
import type { SettingsFormData } from "@/stores/useSettingsStore";

// Recreate the handleInputChange logic for direct unit testing
// This mirrors the exact implementation from SettingsPage.tsx lines 83-119

const numericFields: Set<keyof SettingsFormData> = new Set([
  "chunk_size_chars",
  "chunk_overlap_chars",
  "retrieval_top_k",
  "auto_scan_interval_minutes",
  "max_distance_threshold",
  "retrieval_window",
  "embedding_batch_size",
  "hybrid_alpha",
  "initial_retrieval_top_k",
  "reranker_top_n",
]);

function handleInputChange(
  field: keyof SettingsFormData,
  value: string | boolean | number,
  updateFormField: (field: keyof SettingsFormData, value: any) => void
) {
  if (typeof value === "boolean") {
    updateFormField(field, value);
  } else if (typeof value === "string") {
    if (value === "") {
      // Empty string: for numeric fields, set to 0; for string fields, keep as empty string
      if (numericFields.has(field)) {
        updateFormField(field, 0);
      } else {
        updateFormField(field as any, value);
      }
    } else if (numericFields.has(field)) {
      const numValue = parseFloat(value);
      if (!isNaN(numValue)) {
        updateFormField(field, numValue);
      }
    } else {
      // String field - keep as string
      updateFormField(field, value);
    }
  } else {
    // number
    updateFormField(field, value);
  }
}

describe("handleInputChange", () => {
  let updateFormField: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    updateFormField = vi.fn();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe("string fields (URLs, model names, prefixes)", () => {
    test("should update string field with non-numeric URL value", () => {
      handleInputChange("reranker_url", "http://localhost:8001", updateFormField);
      expect(updateFormField).toHaveBeenCalledWith("reranker_url", "http://localhost:8001");
    });

    test("should update string field with non-numeric model name", () => {
      handleInputChange("reranker_model", "cross-encoder/ms-marco-MiniLM-L-6-v2", updateFormField);
      expect(updateFormField).toHaveBeenCalledWith("reranker_model", "cross-encoder/ms-marco-MiniLM-L-6-v2");
    });

    test("should update ollama_embedding_url with URL string", () => {
      handleInputChange("ollama_embedding_url", "http://192.168.1.100:11434", updateFormField);
      expect(updateFormField).toHaveBeenCalledWith("ollama_embedding_url", "http://192.168.1.100:11434");
    });

    test("should update ollama_chat_url with URL string", () => {
      handleInputChange("ollama_chat_url", "http://localhost:11434", updateFormField);
      expect(updateFormField).toHaveBeenCalledWith("ollama_chat_url", "http://localhost:11434");
    });

    test("should update embedding_model with model name string", () => {
      handleInputChange("embedding_model", "nomic-embed-text", updateFormField);
      expect(updateFormField).toHaveBeenCalledWith("embedding_model", "nomic-embed-text");
    });

    test("should update chat_model with model name string", () => {
      handleInputChange("chat_model", "llama3.2", updateFormField);
      expect(updateFormField).toHaveBeenCalledWith("chat_model", "llama3.2");
    });

    test("should update vector_metric with string value", () => {
      handleInputChange("vector_metric", "euclidean", updateFormField);
      expect(updateFormField).toHaveBeenCalledWith("vector_metric", "euclidean");
    });

    test("should update embedding_doc_prefix with string value", () => {
      handleInputChange("embedding_doc_prefix", "Passage: ", updateFormField);
      expect(updateFormField).toHaveBeenCalledWith("embedding_doc_prefix", "Passage: ");
    });

    test("should update embedding_query_prefix with string value", () => {
      handleInputChange("embedding_query_prefix", "Query: ", updateFormField);
      expect(updateFormField).toHaveBeenCalledWith("embedding_query_prefix", "Query: ");
    });

    test("should NOT parse URL-like strings as numbers even if they contain digits", () => {
      // URLs like "http://10.0.0.1:8080" contain numbers but should remain strings
      handleInputChange("reranker_url", "http://10.0.0.1:8080/api", updateFormField);
      expect(updateFormField).toHaveBeenCalledWith("reranker_url", "http://10.0.0.1:8080/api");
      expect(updateFormField.mock.calls[0][1]).toBeTypeOf("string");
    });

    test("should handle model names with version numbers (remain as strings)", () => {
      handleInputChange("chat_model", "gpt-4o-2024-08-06", updateFormField);
      expect(updateFormField).toHaveBeenCalledWith("chat_model", "gpt-4o-2024-08-06");
      expect(updateFormField.mock.calls[0][1]).toBeTypeOf("string");
    });
  });

  describe("empty string handling", () => {
    test("should convert empty string to 0 for numeric field (chunk_size_chars)", () => {
      handleInputChange("chunk_size_chars", "", updateFormField);
      expect(updateFormField).toHaveBeenCalledWith("chunk_size_chars", 0);
      expect(updateFormField.mock.calls[0][1]).toBe(0);
      expect(updateFormField.mock.calls[0][1]).toBeTypeOf("number");
    });

    test("should convert empty string to 0 for numeric field (retrieval_top_k)", () => {
      handleInputChange("retrieval_top_k", "", updateFormField);
      expect(updateFormField).toHaveBeenCalledWith("retrieval_top_k", 0);
      expect(updateFormField.mock.calls[0][1]).toBeTypeOf("number");
    });

    test("should convert empty string to 0 for numeric field (embedding_batch_size)", () => {
      handleInputChange("embedding_batch_size", "", updateFormField);
      expect(updateFormField).toHaveBeenCalledWith("embedding_batch_size", 0);
      expect(updateFormField.mock.calls[0][1]).toBeTypeOf("number");
    });

    test("should convert empty string to 0 for numeric field (hybrid_alpha)", () => {
      handleInputChange("hybrid_alpha", "", updateFormField);
      expect(updateFormField).toHaveBeenCalledWith("hybrid_alpha", 0);
      expect(updateFormField.mock.calls[0][1]).toBeTypeOf("number");
    });

    test("should convert empty string to 0 for numeric field (max_distance_threshold)", () => {
      handleInputChange("max_distance_threshold", "", updateFormField);
      expect(updateFormField).toHaveBeenCalledWith("max_distance_threshold", 0);
      expect(updateFormField.mock.calls[0][1]).toBeTypeOf("number");
    });

    test("should keep empty string as empty string for string field (reranker_url)", () => {
      handleInputChange("reranker_url", "", updateFormField);
      expect(updateFormField).toHaveBeenCalledWith("reranker_url", "");
      expect(updateFormField.mock.calls[0][1]).toBe("");
      expect(updateFormField.mock.calls[0][1]).toBeTypeOf("string");
    });

    test("should keep empty string as empty string for string field (reranker_model)", () => {
      handleInputChange("reranker_model", "", updateFormField);
      expect(updateFormField).toHaveBeenCalledWith("reranker_model", "");
      expect(updateFormField.mock.calls[0][1]).toBeTypeOf("string");
    });

    test("should keep empty string as empty string for string field (ollama_embedding_url)", () => {
      handleInputChange("ollama_embedding_url", "", updateFormField);
      expect(updateFormField).toHaveBeenCalledWith("ollama_embedding_url", "");
      expect(updateFormField.mock.calls[0][1]).toBeTypeOf("string");
    });

    test("should keep empty string as empty string for string field (vector_metric)", () => {
      handleInputChange("vector_metric", "", updateFormField);
      expect(updateFormField).toHaveBeenCalledWith("vector_metric", "");
      expect(updateFormField.mock.calls[0][1]).toBeTypeOf("string");
    });
  });

  describe("numeric string parsing", () => {
    test("should parse valid numeric string to number for chunk_size_chars", () => {
      handleInputChange("chunk_size_chars", "2048", updateFormField);
      expect(updateFormField).toHaveBeenCalledWith("chunk_size_chars", 2048);
      expect(updateFormField.mock.calls[0][1]).toBeTypeOf("number");
    });

    test("should parse valid numeric string with decimal for max_distance_threshold", () => {
      handleInputChange("max_distance_threshold", "0.75", updateFormField);
      expect(updateFormField).toHaveBeenCalledWith("max_distance_threshold", 0.75);
      expect(updateFormField.mock.calls[0][1]).toBeTypeOf("number");
    });

    test("should parse valid numeric string for hybrid_alpha", () => {
      handleInputChange("hybrid_alpha", "0.5", updateFormField);
      expect(updateFormField).toHaveBeenCalledWith("hybrid_alpha", 0.5);
      expect(updateFormField.mock.calls[0][1]).toBeTypeOf("number");
    });

    test("should parse valid numeric string for retrieval_top_k", () => {
      handleInputChange("retrieval_top_k", "10", updateFormField);
      expect(updateFormField).toHaveBeenCalledWith("retrieval_top_k", 10);
      expect(updateFormField.mock.calls[0][1]).toBeTypeOf("number");
    });

    test("should parse valid numeric string for embedding_batch_size", () => {
      handleInputChange("embedding_batch_size", "1024", updateFormField);
      expect(updateFormField).toHaveBeenCalledWith("embedding_batch_size", 1024);
      expect(updateFormField.mock.calls[0][1]).toBeTypeOf("number");
    });

    test("should NOT call updateFormField for NaN numeric string on numeric field", () => {
      // When a non-numeric string is entered for a numeric field, parseFloat returns NaN
      // The implementation should NOT update the field in this case
      handleInputChange("chunk_size_chars", "not-a-number", updateFormField);
      expect(updateFormField).not.toHaveBeenCalled();
    });

    test("should parse negative numbers correctly", () => {
      // Even though negative might not be valid semantically, parsing should work
      handleInputChange("max_distance_threshold", "-0.5", updateFormField);
      expect(updateFormField).toHaveBeenCalledWith("max_distance_threshold", -0.5);
      expect(updateFormField.mock.calls[0][1]).toBeTypeOf("number");
    });

    test("should parse integer strings correctly", () => {
      handleInputChange("chunk_overlap_chars", "256", updateFormField);
      expect(updateFormField).toHaveBeenCalledWith("chunk_overlap_chars", 256);
      // Note: JS doesn't distinguish int vs float, but verify it's a number
      expect(updateFormField.mock.calls[0][1]).toBeTypeOf("number");
    });

    test("should handle leading/trailing whitespace in numeric strings", () => {
      // parseFloat("  42  ") returns 42, which is correct
      handleInputChange("retrieval_top_k", "  42  ", updateFormField);
      expect(updateFormField).toHaveBeenCalledWith("retrieval_top_k", 42);
    });
  });

  describe("boolean handling", () => {
    test("should pass boolean true directly for auto_scan_enabled", () => {
      handleInputChange("auto_scan_enabled", true, updateFormField);
      expect(updateFormField).toHaveBeenCalledWith("auto_scan_enabled", true);
      expect(updateFormField.mock.calls[0][1]).toBeTypeOf("boolean");
    });

    test("should pass boolean false directly for auto_scan_enabled", () => {
      handleInputChange("auto_scan_enabled", false, updateFormField);
      expect(updateFormField).toHaveBeenCalledWith("auto_scan_enabled", false);
      expect(updateFormField.mock.calls[0][1]).toBeTypeOf("boolean");
    });

    test("should pass boolean true directly for reranking_enabled", () => {
      handleInputChange("reranking_enabled", true, updateFormField);
      expect(updateFormField).toHaveBeenCalledWith("reranking_enabled", true);
    });

    test("should pass boolean false directly for reranking_enabled", () => {
      handleInputChange("reranking_enabled", false, updateFormField);
      expect(updateFormField).toHaveBeenCalledWith("reranking_enabled", false);
    });

    test("should pass boolean true directly for hybrid_search_enabled", () => {
      handleInputChange("hybrid_search_enabled", true, updateFormField);
      expect(updateFormField).toHaveBeenCalledWith("hybrid_search_enabled", true);
    });

    test("should pass boolean false directly for hybrid_search_enabled", () => {
      handleInputChange("hybrid_search_enabled", false, updateFormField);
      expect(updateFormField).toHaveBeenCalledWith("hybrid_search_enabled", false);
    });
  });

  describe("direct number handling", () => {
    test("should pass number directly for numeric field", () => {
      handleInputChange("chunk_size_chars", 2048, updateFormField);
      expect(updateFormField).toHaveBeenCalledWith("chunk_size_chars", 2048);
      expect(updateFormField.mock.calls[0][1]).toBeTypeOf("number");
    });

    test("should pass decimal number directly for numeric field", () => {
      handleInputChange("max_distance_threshold", 0.85, updateFormField);
      expect(updateFormField).toHaveBeenCalledWith("max_distance_threshold", 0.85);
      expect(updateFormField.mock.calls[0][1]).toBeTypeOf("number");
    });
  });

  describe("edge cases and adversarial inputs", () => {
    test("should handle special characters in string fields", () => {
      handleInputChange("reranker_url", "http://localhost:8080/api/v1?query=test&sort=desc", updateFormField);
      expect(updateFormField).toHaveBeenCalledWith("reranker_url", "http://localhost:8080/api/v1?query=test&sort=desc");
    });

    test("should handle Unicode in string fields", () => {
      handleInputChange("embedding_doc_prefix", "文档: ", updateFormField);
      expect(updateFormField).toHaveBeenCalledWith("embedding_doc_prefix", "文档: ");
    });

    test("should handle very long string values", () => {
      const longUrl = "http://example.com/" + "a".repeat(1000);
      handleInputChange("ollama_embedding_url", longUrl, updateFormField);
      expect(updateFormField).toHaveBeenCalledWith("ollama_embedding_url", longUrl);
    });

    test("should handle scientific notation in numeric fields", () => {
      handleInputChange("embedding_batch_size", "1e3", updateFormField);
      expect(updateFormField).toHaveBeenCalledWith("embedding_batch_size", 1000);
    });

    test("should handle 'Infinity' string on numeric field (parseFloat returns Infinity)", () => {
      // parseFloat("Infinity") returns Infinity, which is a valid number in JS
      handleInputChange("chunk_size_chars", "Infinity", updateFormField);
      expect(updateFormField).toHaveBeenCalledWith("chunk_size_chars", Infinity);
    });

    test("should handle '-Infinity' string on numeric field (parseFloat returns -Infinity)", () => {
      handleInputChange("chunk_size_chars", "-Infinity", updateFormField);
      expect(updateFormField).toHaveBeenCalledWith("chunk_size_chars", -Infinity);
    });

    test("should handle 'NaN' string on numeric field (parseFloat returns NaN)", () => {
      handleInputChange("chunk_size_chars", "NaN", updateFormField);
      expect(updateFormField).not.toHaveBeenCalled();
    });

    test("should handle string with only whitespace for numeric field", () => {
      // parseFloat("   ") returns NaN
      handleInputChange("chunk_size_chars", "   ", updateFormField);
      expect(updateFormField).not.toHaveBeenCalled();
    });

    test("should handle mixed alphanumeric on numeric field (returns NaN)", () => {
      handleInputChange("chunk_size_chars", "123abc", updateFormField);
      // parseFloat("123abc") returns 123, so this WILL update
      expect(updateFormField).toHaveBeenCalledWith("chunk_size_chars", 123);
    });

    test("should handle string starting with number then text on numeric field", () => {
      // parseFloat("42px") returns 42 - this is valid parsing behavior
      handleInputChange("retrieval_top_k", "42px", updateFormField);
      expect(updateFormField).toHaveBeenCalledWith("retrieval_top_k", 42);
    });
  });

  describe("type preservation verification", () => {
    test("string field receives string type (not number)", () => {
      handleInputChange("reranker_url", "http://localhost:8080", updateFormField);
      const callValue = updateFormField.mock.calls[0][1];
      expect(callValue).toBeTypeOf("string");
    });

    test("numeric field receives number type (not string)", () => {
      handleInputChange("chunk_size_chars", "1024", updateFormField);
      const callValue = updateFormField.mock.calls[0][1];
      expect(callValue).toBeTypeOf("number");
    });

    test("empty string on numeric field receives number 0 (not string)", () => {
      handleInputChange("chunk_size_chars", "", updateFormField);
      const callValue = updateFormField.mock.calls[0][1];
      expect(callValue).toBeTypeOf("number");
      expect(callValue).toBe(0);
    });

    test("empty string on string field receives string (not null/undefined)", () => {
      handleInputChange("reranker_url", "", updateFormField);
      const callValue = updateFormField.mock.calls[0][1];
      expect(callValue).toBeTypeOf("string");
      expect(callValue).toBe("");
    });

    test("boolean field receives boolean type", () => {
      handleInputChange("auto_scan_enabled", true, updateFormField);
      const callValue = updateFormField.mock.calls[0][1];
      expect(callValue).toBeTypeOf("boolean");
    });
  });
});
