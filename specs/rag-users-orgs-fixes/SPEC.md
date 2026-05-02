# SPEC: RAG/Chat Correctness Fixes + Users/Groups/Organizations/Vaults Coherent Tenant Model

## Problem Statement

The RAGAPPv3 codebase had two classes of defects:

1. **RAG/Chat correctness bugs** — citation validation was broken (wrong import), memory updates left embeddings stale, streamed `<think>` blocks were not suppressed consistently, raw SSE fallback could forward reasoning content to users, and attachments could be sent while still indexing.

2. **Tenant model incoherence** — Vaults were created without `org_id`, making them invisible to group-vault assignment. Group-vault access had no explicit permission levels. Organization ownership transfer was not supported. Groups couldn't be assigned to organizations at creation time. Per-org roles in user-org assignments were hardcoded to a single `member` role. The eligible-member filter for groups wasn't enforced. Admin-only navigation items were visible to all users.

## Goals

### Part A — RAG/Chat Correctness

- A1: Fix citation repair function import in `chat.py`
- A2: Route memory content updates through `MemoryStore` to recompute dense embeddings
- A3: Add idempotent embedding backfill for existing memories (service + lifespan hook + admin endpoint)
- A4: Harden streaming `<think>` suppression (uppercase, attributes, fragmented tags)
- A5: Sanitize raw SSE fallback to drop reasoning/thinking patterns before forwarding
- A6: Block send while attachments are uploading/indexing; add "Send without these files" option

### Part B — Coherent Tenant Model

- B1: Vault creation infers/requires `org_id`; schema adds missing indexes
- B2: Group-vault access uses `VaultAccessItem[]` with explicit `read/write/admin` permissions
- B3: `POST /organizations/{org_id}/transfer-ownership` endpoint; OrgsPage shows owner badge + transfer dialog
- B4: GroupFormDialog sends `org_id` at creation time; backend validates and stores it
- B5: `PUT /users/{id}/organizations` accepts `{ memberships: [{org_id, role}] }` per-org roles; legacy `org_ids` still works
- B6: `GET /groups/{id}/eligible-members` endpoint returns only org-filtered users; ManageMembersSheet uses it
- B10: NavigationRail and MobileBottomNav filter admin-only items (groups, users, organizations) by user role

## Non-Goals

- Billing, payments, SSO, or federated identity
- Real-time websocket presence
- Email notifications for ownership transfer

## Acceptance Criteria

### A1 — Citation Repair
- `repair_against_sources_and_memories` is imported and called in both streaming and non-streaming chat paths
- Invalid `[S99]` / `[M99]` are repaired or stripped; valid `[S1] [M1]` pass through unchanged
- No `NameError` raised during citation repair

### A2 — Memory Embedding Staleness
- `PUT /memories/{id}` with content change triggers embedding recomputation via `MemoryStore`
- Semantic search reflects updated content immediately after update
- Metadata-only updates do not unnecessarily recompute embedding

### A3 — Memory Backfill
- `backfill_memory_embeddings()` embeds memories where `embedding IS NULL` or model is stale
- Called at startup; skipped gracefully if embedding service unavailable
- Admin endpoint available to trigger on demand

### A4 — Streaming Think Suppression
- `<THINK>hidden</THINK>visible` → only `visible` streamed
- `<think type="x">hidden</think>visible` → only `visible` streamed
- Fragmented tags across chunk boundaries suppressed correctly
- Unterminated `<think>` blocks suppressed until buffer limit

### A5 — SSE Fallback Sanitization
- Raw SSE payload containing `<think`, `reasoning_content`, `thinking_content` is dropped
- Normal raw payloads forwarded correctly

### A6 — Attachment Send Blocking
- Send button disabled while any attachment is `uploading`, `uploaded`, or `indexing`
- "Send without these files" action removes non-indexed attachments and enables send
- Only `indexed` state allows send

### B1 — Org-Scoped Vaults
- Single-org user: vault creation infers `org_id` automatically
- Multi-org user without `org_id`: 400 error with clear message
- Multi-org user with `org_id`: vault assigned to specified org
- VaultResponse includes `org_id` and `organization_name`

### B2 — Explicit Group-Vault Permissions
- `PUT /groups/{id}/vaults` accepts `{ vault_access: [{vault_id, permission}] }`
- All inserts set `permission` column explicitly
- ManageVaultsSheet UI shows permission select per vault row (read/write/admin)

### B3 — Ownership Transfer
- `POST /organizations/{org_id}/transfer-ownership` atomically demotes old owner to admin and promotes new user to owner
- Only current owner or superadmin can transfer
- Cannot transfer to self or non-member
- OrgsPage shows "Owner" badge (read-only) and "Transfer" button for eligible users

### B4 — Group Org Assignment
- `POST /groups` accepts `org_id` in body; validates org exists; stores it
- GroupFormDialog auto-selects if single org; shows select if multiple; read-only if editing

### B5 — Per-Org Roles
- `memberships: [{org_id, role}]` format sets different roles per org
- Legacy `{org_ids: [...], role: "..."}` still works (applies single role to all)
- `memberships` takes precedence over `org_ids` when both present
- Invalid roles (`owner`, `superadmin`) return 400
- AdminUsersPage org list shows per-org role select

### B6 — Eligible Group Members
- `GET /groups/{id}/eligible-members` returns only users who are org members of the group's org
- ManageMembersSheet uses this endpoint instead of listing all users
- Non-admin access returns 403; nonexistent group returns 404

### B10 — Role-Filtered Navigation
- Groups, Users, Organizations nav items visible only to admin and superadmin
- Both NavigationRail (desktop) and MobileBottomNav filtered by role

## Technical Design

### Backend
- `chat.py`: correct import from `citation_validator.py`
- `memories.py`: `PUT` handler delegates to `MemoryStore.update_memory_content()`
- `memory_store.py`: `update_memory_content()`, `backfill_memory_embeddings()` methods
- `lifespan.py`: calls `backfill_memory_embeddings()` at startup (background, non-blocking)
- `llm_client.py`: stream-safe `<think>` state machine handling fragmented tags
- `vaults.py`: `org_id` inference/validation logic
- `groups.py`: `eligible-members` endpoint + org_id in group creation
- `organizations.py`: `transfer-ownership` endpoint
- `users.py`: `UserOrgsUpdateRequest` with `memberships` + `OrgMembershipItem` DTO
- `database.py`: schema adds new indexes (`idx_memories_vault_id`, `idx_memories_created_at`, `idx_users_locked_until`, etc.)

### Frontend
- `api.ts`: `getEligibleGroupMembers()`, updated `createGroup()`, `VaultAccessItem` type
- `ManageVaultsSheet.tsx`: permission select per vault row
- `ManageMembersSheet.tsx`: uses `getEligibleGroupMembers()`
- `GroupFormDialog.tsx`: org selector
- `OrgsPage.tsx`: owner badge, transfer dialog
- `AdminUsersPage.tsx`: per-org role select
- `NavigationRail.tsx` / `MobileBottomNav.tsx`: role-based item filtering
- `Composer.tsx`: attachment send blocking + "Send without" action

## Test Coverage

87 backend pytest tests pass across:
- `test_organizations_routes.py` — 29 tests including `TestTransferOwnership` (6 tests)
- `test_groups_new_features.py` — 18 tests including `TestEligibleMembers` (4 tests)
- `test_schema_unification.py` — updated to match current migration list
- `test_user_org_roles.py` — 12 new tests for per-org role assignment (B5)

## Migration / Backfill Strategy

- All schema changes are idempotent (`CREATE TABLE IF NOT EXISTS`, `ALTER TABLE` with try/except for existing columns)
- `org_id` backfill: vault 1 assigned to Default organization; NULL vaults reported via logs
- Memory embedding backfill: startup hook skips memories that already have current-model embeddings
