/**
 * NumberInput primitive — draft-string semantics.
 *
 * The legacy SettingsPage coerced empty input to 0 on every keystroke,
 * making numeric fields hostile to editing (you couldn't temporarily
 * blank a field to retype it). This primitive keeps the user's raw
 * string locally and only commits a coerced number on blur.
 *
 * Contract:
 *   - `value` (number | undefined) is the *committed* value held by the
 *     parent store. Undefined is treated as "no value yet".
 *   - On focus / typing, the input shows the user's draft string
 *     verbatim — including the empty string. The parent store is NOT
 *     updated until blur.
 *   - On blur, if the draft parses to a finite number, `onCommit` is
 *     called with that number. If the draft is blank, `onCommit` is
 *     called with `undefined` (so the parent can decide whether to
 *     treat blank as "use default" or "validation error").
 *   - If the draft is non-blank and unparseable, `onCommit` is NOT
 *     called and the field surfaces a `data-invalid` attribute the
 *     parent / styles can use to show an error.
 *   - Pressing Enter forces a blur (and therefore a commit).
 *
 * Tests for this primitive live in NumberInput.test.tsx.
 */
import { useEffect, useState, type InputHTMLAttributes } from "react";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export interface NumberInputProps
  extends Omit<
    InputHTMLAttributes<HTMLInputElement>,
    "value" | "onChange" | "type"
  > {
  /** Committed numeric value (or undefined for "blank"). */
  value: number | undefined;
  /**
   * Called on blur (or Enter) with the parsed number, or with
   * `undefined` if the field was blanked. Not called for unparseable
   * non-empty input.
   */
  onCommit: (value: number | undefined) => void;
  /** Use parseFloat (default) vs parseInt. */
  parseAs?: "float" | "int";
  /** Inline error message — sets data-invalid="true". */
  error?: string;
}

function formatForDisplay(value: number | undefined): string {
  if (value === undefined || value === null || Number.isNaN(value)) return "";
  return String(value);
}

export function NumberInput({
  value,
  onCommit,
  parseAs = "float",
  error,
  className,
  onBlur,
  onKeyDown,
  ...rest
}: NumberInputProps) {
  // draft is the raw string the user is typing; it can be "" or "12.3" or "-".
  const [draft, setDraft] = useState<string>(formatForDisplay(value));
  const [invalid, setInvalid] = useState(false);

  // When the parent updates the committed value (e.g. discard / load),
  // resync the draft. If the user is currently editing (draft and value
  // disagree but the draft parses to value), don't clobber.
  useEffect(() => {
    const next = formatForDisplay(value);
    setDraft((prev) => {
      const parsed = parseAs === "int" ? parseInt(prev, 10) : parseFloat(prev);
      if (!Number.isFinite(parsed) && prev === next) return prev;
      if (Number.isFinite(parsed) && parsed === value) return prev;
      return next;
    });
    setInvalid(false);
  }, [value, parseAs]);

  return (
    <Input
      {...rest}
      type="text"
      inputMode="decimal"
      data-invalid={error || invalid ? "true" : undefined}
      aria-invalid={error || invalid ? true : undefined}
      value={draft}
      className={cn(error || invalid ? "border-destructive" : undefined, className)}
      onChange={(e) => {
        setDraft(e.target.value);
        if (invalid) setInvalid(false);
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          e.currentTarget.blur();
        }
        onKeyDown?.(e);
      }}
      onBlur={(e) => {
        const raw = draft.trim();
        if (raw === "") {
          setInvalid(false);
          onCommit(undefined);
        } else {
          const parsed = parseAs === "int" ? parseInt(raw, 10) : parseFloat(raw);
          if (Number.isFinite(parsed)) {
            setInvalid(false);
            onCommit(parsed);
          } else {
            setInvalid(true);
            // Don't call onCommit — keep the parent state intact so the
            // user can correct without losing the previous value.
          }
        }
        onBlur?.(e);
      }}
    />
  );
}
