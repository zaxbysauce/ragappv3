/**
 * Pure handler used by the legacy DocumentProcessing / RAG / Retrieval
 * settings components. Extracted so the regression tests can import the
 * real implementation rather than a hand-mirrored copy that could drift
 * silently from the page.
 *
 * Numeric coercion contract:
 *   - Boolean / number values are passed through unchanged.
 *   - String values for `LEGACY_NUMERIC_FIELDS` are parsed with
 *     parseFloat. Empty input is intentionally NOT written to the store
 *     (preserves last good value rather than overwriting with NaN/0).
 *     Unparseable input is silently dropped — the legacy components
 *     do not surface invalid state, which is a known limitation; the
 *     Wiki & Curator tab uses the NumberInput primitive which does.
 *   - Any other string field passes through (URLs, model names, etc.).
 */
import type { SettingsFormData } from "@/stores/useSettingsStore";

export const LEGACY_NUMERIC_FIELDS: ReadonlySet<keyof SettingsFormData> =
  new Set([
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

export type UpdateFormFieldFn = <K extends keyof SettingsFormData>(
  field: K,
  value: SettingsFormData[K],
) => void;

export function handleSettingsInputChange(
  field: keyof SettingsFormData,
  value: string | boolean | number,
  updateFormField: UpdateFormFieldFn,
): void {
  if (typeof value === "boolean") {
    updateFormField(field, value as SettingsFormData[typeof field]);
    return;
  }
  if (typeof value === "string") {
    if (LEGACY_NUMERIC_FIELDS.has(field)) {
      if (value === "") {
        // Preserve last good value: don't write a string blank into a
        // numeric form field. The user can keep typing and the commit
        // happens once a parseable number lands.
        return;
      }
      const parsed = parseFloat(value);
      if (Number.isFinite(parsed)) {
        updateFormField(field, parsed as SettingsFormData[typeof field]);
      }
      return;
    }
    updateFormField(field, value as SettingsFormData[typeof field]);
    return;
  }
  updateFormField(field, value as SettingsFormData[typeof field]);
}
