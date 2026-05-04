/**
 * PR B: input-handling tests for the redesigned SettingsPage.
 *
 * Behavior change vs. legacy:
 *   - Empty numeric input is NO LONGER coerced to 0. Numeric fields use
 *     the NumberInput primitive which keeps a draft string locally and
 *     only commits on blur. A blank field remains blank in the draft and
 *     is never sent to the backend until it parses.
 *   - The page-level handler is now a thin pass-through to the store's
 *     `updateFormField`; type narrowing happens at the input edge
 *     (NumberInput), not the page level.
 *
 * Coverage:
 *   - Strings/URLs/model names round-trip unchanged.
 *   - Booleans round-trip unchanged.
 *   - Direct number commits round-trip unchanged.
 *   - NumberInput keeps the draft visually blank and does NOT commit
 *     until blur (the legacy "blank == 0" assertion is intentionally
 *     replaced).
 *   - On a blank blur, NumberInput commits `undefined` (the parent
 *     keeps the previous value rather than collapsing to 0).
 *   - On unparseable non-empty input, NumberInput surfaces invalid
 *     state and does NOT commit a value.
 */
import { describe, test, expect, vi, beforeEach, afterEach } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import type { SettingsFormData } from "@/stores/useSettingsStore";
import { NumberInput } from "@/components/settings/NumberInput";
import {
  handleSettingsInputChange,
  LEGACY_NUMERIC_FIELDS,
} from "@/components/settings/handleInputChange";

// Tests exercise the REAL handler used by SettingsPage. Earlier
// versions of this test mirrored the implementation inline, which
// silently drifts on every refactor. Importing the actual function
// guarantees the tests follow the page.
function handleInputChange(
  field: keyof SettingsFormData,
  value: string | boolean | number,
  updateFormField: (field: keyof SettingsFormData, value: unknown) => void,
) {
  // Cast so the test helper accepts the loose signature the legacy
  // components emit; the real handler does the same.
  handleSettingsInputChange(
    field,
    value,
    updateFormField as (k: keyof SettingsFormData, v: never) => void,
  );
}

describe("SettingsPage handleInputChange (loose pass-through)", () => {
  let updateFormField: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    updateFormField = vi.fn();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  test("string field round-trip", () => {
    handleInputChange(
      "reranker_url",
      "http://localhost:8001",
      updateFormField,
    );
    expect(updateFormField).toHaveBeenCalledWith(
      "reranker_url",
      "http://localhost:8001",
    );
  });

  test("model-name string round-trip preserves slashes / colons / hyphens", () => {
    handleInputChange(
      "embedding_model",
      "BAAI/bge-large-en-v1.5",
      updateFormField,
    );
    expect(updateFormField).toHaveBeenCalledWith(
      "embedding_model",
      "BAAI/bge-large-en-v1.5",
    );
  });

  test("empty string on a string field stays empty (no coercion)", () => {
    handleInputChange("reranker_url", "", updateFormField);
    expect(updateFormField).toHaveBeenCalledWith("reranker_url", "");
  });

  test("boolean field round-trip", () => {
    handleInputChange("reranking_enabled", true, updateFormField);
    handleInputChange("reranking_enabled", false, updateFormField);
    expect(updateFormField).toHaveBeenNthCalledWith(1, "reranking_enabled", true);
    expect(updateFormField).toHaveBeenNthCalledWith(2, "reranking_enabled", false);
  });

  test("direct number commit round-trip", () => {
    handleInputChange("retrieval_top_k", 42, updateFormField);
    expect(updateFormField).toHaveBeenCalledWith("retrieval_top_k", 42);
  });
});

describe("SettingsPage handler — legacy numeric coercion (real implementation)", () => {
  let updateFormField: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    updateFormField = vi.fn();
  });

  test("LEGACY_NUMERIC_FIELDS covers every store field the legacy components emit", () => {
    // Sanity check: if a future field gets added to the legacy
    // components without being added to the Set, this test gives a
    // clear failure rather than a confusing string-into-number bug.
    const expected = [
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
    ];
    for (const f of expected) {
      expect(LEGACY_NUMERIC_FIELDS.has(f as keyof SettingsFormData)).toBe(
        true,
      );
    }
  });

  test.each([
    ["chunk_size_chars", "2000", 2000],
    ["chunk_overlap_chars", "150", 150],
    ["retrieval_top_k", "8", 8],
    ["auto_scan_interval_minutes", "30", 30],
    ["max_distance_threshold", "0.65", 0.65],
    ["retrieval_window", "2", 2],
    ["embedding_batch_size", "16", 16],
    ["hybrid_alpha", "0.4", 0.4],
    ["initial_retrieval_top_k", "25", 25],
    ["reranker_top_n", "7", 7],
  ])(
    "coerces string '%s' on field %s -> number %s",
    (field, raw, expected) => {
      handleInputChange(
        field as keyof SettingsFormData,
        raw as string,
        updateFormField,
      );
      expect(updateFormField).toHaveBeenCalledTimes(1);
      expect(updateFormField).toHaveBeenCalledWith(field, expected);
      expect(typeof updateFormField.mock.calls[0][1]).toBe("number");
    },
  );

  test("blank string on numeric field DOES NOT mutate store (preserves last good value)", () => {
    handleInputChange("chunk_size_chars", "", updateFormField);
    expect(updateFormField).not.toHaveBeenCalled();
  });

  test("unparseable non-empty input DOES NOT mutate store", () => {
    handleInputChange("retrieval_top_k", "abc", updateFormField);
    expect(updateFormField).not.toHaveBeenCalled();
  });

  test("non-numeric string field still passes through unchanged", () => {
    handleInputChange(
      "ollama_chat_url",
      "http://localhost:11434",
      updateFormField,
    );
    expect(updateFormField).toHaveBeenCalledWith(
      "ollama_chat_url",
      "http://localhost:11434",
    );
  });
});

describe("NumberInput draft-string behavior (replaces legacy blank-to-0)", () => {
  test("blank field does NOT commit while the user is typing", () => {
    const onCommit = vi.fn();
    render(<NumberInput value={5} onCommit={onCommit} aria-label="x" />);
    const input = screen.getByLabelText("x") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "" } });
    // Still no commit — only on blur.
    expect(onCommit).not.toHaveBeenCalled();
    expect(input.value).toBe("");
  });

  test("blanking and blurring commits undefined (NOT zero)", () => {
    const onCommit = vi.fn();
    render(<NumberInput value={5} onCommit={onCommit} aria-label="x" />);
    const input = screen.getByLabelText("x") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "" } });
    fireEvent.blur(input);
    expect(onCommit).toHaveBeenCalledTimes(1);
    expect(onCommit).toHaveBeenCalledWith(undefined);
  });

  test("typing a valid number and blurring commits the parsed number", () => {
    const onCommit = vi.fn();
    render(<NumberInput value={5} onCommit={onCommit} aria-label="x" />);
    const input = screen.getByLabelText("x") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "12.5" } });
    fireEvent.blur(input);
    expect(onCommit).toHaveBeenCalledWith(12.5);
  });

  test("non-empty unparseable input does NOT commit and surfaces invalid", () => {
    const onCommit = vi.fn();
    render(<NumberInput value={5} onCommit={onCommit} aria-label="x" />);
    const input = screen.getByLabelText("x") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "abc" } });
    fireEvent.blur(input);
    expect(onCommit).not.toHaveBeenCalled();
    expect(input.getAttribute("data-invalid")).toBe("true");
  });

  test("Enter key triggers blur on the underlying input", () => {
    const onCommit = vi.fn();
    render(<NumberInput value={5} onCommit={onCommit} aria-label="x" />);
    const input = screen.getByLabelText("x") as HTMLInputElement;
    input.focus();
    expect(document.activeElement).toBe(input);
    fireEvent.change(input, { target: { value: "7" } });
    fireEvent.keyDown(input, { key: "Enter" });
    // The handler calls e.currentTarget.blur() — JSDOM moves focus
    // away. The native blur lifecycle may or may not fire the React
    // onBlur synchronously depending on the runtime; we assert focus
    // moved as the observable contract.
    expect(document.activeElement).not.toBe(input);
  });

  test("parseAs='int' truncates floats", () => {
    const onCommit = vi.fn();
    render(
      <NumberInput
        value={5}
        onCommit={onCommit}
        parseAs="int"
        aria-label="x"
      />,
    );
    const input = screen.getByLabelText("x") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "10.7" } });
    fireEvent.blur(input);
    expect(onCommit).toHaveBeenCalledWith(10);
  });

  test("parent-driven value updates resync the draft", () => {
    const onCommit = vi.fn();
    const { rerender } = render(
      <NumberInput value={5} onCommit={onCommit} aria-label="x" />,
    );
    const input = screen.getByLabelText("x") as HTMLInputElement;
    expect(input.value).toBe("5");
    rerender(<NumberInput value={42} onCommit={onCommit} aria-label="x" />);
    expect(input.value).toBe("42");
  });
});
