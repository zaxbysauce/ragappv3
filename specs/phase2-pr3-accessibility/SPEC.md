# Phase 2 / PR 3 — Frontend Accessibility (WCAG 2.2 AA)

## Problem Statement

Six WCAG 2.2 AA violations were identified in the codebase review (issue #20, UI-A11Y-3/4/6/7/9/11).
Post-investigation, UI-A11Y-7 (dialog labelling) and UI-A11Y-11 (focus-visible rings) are already
correctly implemented. Four confirmed violations remain:

- **UI-A11Y-3**: The copy button in `MessageContent.tsx` is hidden with `opacity-0
  group-hover:opacity-100`. Keyboard users cannot see the button at rest; it only
  becomes visible on mouse hover, making it practically inaccessible to keyboard users.
- **UI-A11Y-4**: The `<Progress>` component is used in `UploadIndicator.tsx` and
  `DocumentsPage.tsx` with no `aria-label`, so screen readers cannot identify what is
  being tracked (upload progress, processing progress, etc.).
- **UI-A11Y-6**: `LoginPage.tsx`, `RegisterPage.tsx`, and `SetupPage.tsx` form inputs have
  no `aria-describedby` linking them to their error messages, and no `aria-invalid` when
  validation fails. Screen readers do not associate errors with their fields.
- **UI-A11Y-9**: Three icon-only buttons have no `aria-label`: the close button in
  `UploadIndicator.tsx`, and the delete buttons in `DocumentsPage.tsx` and `MemoryPage.tsx`.

## Already Confirmed Fixed (no action needed)

- **UI-A11Y-7**: All dialogs already have `aria-labelledby` pointing to their `<DialogTitle>`
  with matching `id` attributes.
- **UI-A11Y-11**: All `outline-none` classes have compensating `focus-visible:ring-*` classes.

## Goals

1. Make the copy button visible at rest for keyboard users (UI-A11Y-3).
2. Add `aria-label` to Progress call sites so screen readers can identify progress context (UI-A11Y-4).
3. Link form error messages to inputs via `aria-describedby`; mark invalid inputs with
   `aria-invalid` (UI-A11Y-6).
4. Add `aria-label` to the three icon-only buttons missing one (UI-A11Y-9).

## Non-Goals

- No changes to application logic, data flow, or backend.
- No new dependencies.
- No visual redesign beyond what is required by the accessibility fix (copy button visibility
  change is user-visible but intentional).
- UI-A11Y-7 and UI-A11Y-11 are already fixed — do not touch those areas.

## Acceptance Criteria

### UI-A11Y-3 — Copy button in MessageContent.tsx
- [ ] The copy button in `MessageContent.tsx` is visible at rest (not `opacity-0`).
- [ ] On mouse hover/focus the button remains or becomes more prominent (no regression for
  sighted mouse users).
- [ ] The button is reachable via Tab and activatable via Enter/Space (already true — verify
  unchanged).
- [ ] `aria-label` remains present on the button (already present — verify unchanged).

### UI-A11Y-4 — Progress aria-label at call sites
- [ ] `UploadIndicator.tsx` passes `aria-label` (e.g., `"Upload progress"`) to `<Progress>`.
- [ ] `DocumentsPage.tsx` passes `aria-label` (e.g., `"Processing progress"`) to `<Progress>`.
- [ ] TypeScript accepts the prop (Radix/shadcn Progress already accepts arbitrary props via
  `{...props}` — verify no type error).

### UI-A11Y-6 — Form error association
- [ ] `LoginPage.tsx`: each input that can display an error has `aria-describedby` pointing
  to the error element's `id`; the error element has a matching `id`; the input has
  `aria-invalid={!!error}`.
- [ ] `RegisterPage.tsx`: same for all validated fields (username, email, password, confirm
  password).
- [ ] `SetupPage.tsx`: same for all validated fields.
- [ ] Error messages remain visually unchanged.
- [ ] `aria-invalid` is absent (or `false`) when the field has no error.

### UI-A11Y-9 — Icon-only buttons
- [ ] `UploadIndicator.tsx` expand/collapse button has `aria-label` (e.g.,
  `"Collapse uploads"` / `"Expand uploads"` based on state, or `"Toggle uploads"`).
- [ ] `DocumentsPage.tsx` delete button has `aria-label` (e.g., `"Delete document"`).
- [ ] `MemoryPage.tsx` delete button has `aria-label` (e.g., `"Delete memory"`).
- [ ] The icon inside each button has `aria-hidden="true"`.

## Technical Design

### UI-A11Y-3 — `frontend/src/components/chat/MessageContent.tsx` (~line 78)

Change `opacity-0 group-hover:opacity-100 transition-opacity` to
`opacity-60 hover:opacity-100 focus-within:opacity-100 transition-opacity` (or simply
remove the opacity hiding entirely). The current CopyButton component already has
`aria-label` — no change needed there.

### UI-A11Y-4 — `UploadIndicator.tsx` and `DocumentsPage.tsx`

Pass `aria-label="Upload progress"` to `<Progress>` in `UploadIndicator.tsx` and
`aria-label="Processing progress"` in `DocumentsPage.tsx`. Radix `ProgressPrimitive.Root`
already emits `role="progressbar"`, `aria-valuenow`, `aria-valuemin`, `aria-valuemax` from
the `value` prop — no changes to `progress.tsx` itself are needed.

### UI-A11Y-6 — Form pages

Pattern for each input/error pair:
```tsx
// Give the error element a stable id
<p id="username-error" className="text-sm text-destructive">
  {errors.username}
</p>

// Link the input to the error
<Input
  id="username"
  aria-describedby={errors.username ? "username-error" : undefined}
  aria-invalid={!!errors.username}
  ...
/>
```

Apply to all validated fields in `LoginPage.tsx`, `RegisterPage.tsx`, and `SetupPage.tsx`.

### UI-A11Y-9 — Icon-only buttons

Add `aria-label` to the three buttons and `aria-hidden="true"` on their icon children:

- `UploadIndicator.tsx`: toggle button — `aria-label={isExpanded ? "Collapse uploads" : "Expand uploads"}`
- `DocumentsPage.tsx`: `aria-label="Delete document"`
- `MemoryPage.tsx`: `aria-label="Delete memory"`

## Files to Change

| File | Finding | Change |
|---|---|---|
| `frontend/src/components/chat/MessageContent.tsx` | UI-A11Y-3 | Remove/reduce `opacity-0` hiding on copy button |
| `frontend/src/components/shared/UploadIndicator.tsx` | UI-A11Y-4, UI-A11Y-9 | Add `aria-label` to Progress; add `aria-label` to toggle button |
| `frontend/src/pages/DocumentsPage.tsx` | UI-A11Y-4, UI-A11Y-9 | Add `aria-label` to Progress; add `aria-label` to delete button |
| `frontend/src/pages/MemoryPage.tsx` | UI-A11Y-9 | Add `aria-label` to delete button |
| `frontend/src/pages/LoginPage.tsx` | UI-A11Y-6 | `aria-describedby` + `aria-invalid` on inputs |
| `frontend/src/pages/RegisterPage.tsx` | UI-A11Y-6 | `aria-describedby` + `aria-invalid` on all validated fields |
| `frontend/src/pages/SetupPage.tsx` | UI-A11Y-6 | `aria-describedby` + `aria-invalid` on all validated fields |

## Test Plan

### Automated
- `cd frontend && npm run build` — no TypeScript errors from new props.
- `cd frontend && npm run test` — existing suite remains green.

### Manual
- Tab to the copy button in a chat message → button is visible and focusable.
- Screen reader on a chat page → copy button announces "Copy to clipboard".
- Screen reader on a progress bar → announces role=progressbar and label (e.g., "Upload progress").
- Screen reader on login page with a validation error → error is announced as associated with
  its input field.
- Tab through UploadIndicator toggle, document delete, memory delete → each announces its
  action label.
