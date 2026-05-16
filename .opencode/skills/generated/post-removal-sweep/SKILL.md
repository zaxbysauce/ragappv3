---
name: post-removal-sweep
description: "Exhaustive multi-pattern search after removing a code pattern to ensure no remnants remain in any code path."
generated_from_knowledge:
  - 79c669de-e985-4551-9f32-ab457d6ef096
  - 267d5ca2-f61f-4633-a906-7b0db0643972
  - c6fc3b48-7099-4254-afba-8ae2112f6027
confidence: 1.00
status: active
---

# Post-Removal Sweep

After removing a code pattern (e.g. a hardcoded default, a deprecated function, a config property), run an exhaustive sweep to ensure zero remnants remain across all code paths.

## Trigger

Use this skill when:
- Removing a hardcoded value that was used as a fallback or default
- Deleting a function, property, or module that was referenced in multiple places
- Finishing any task where the acceptance criteria includes "no references remain"
- A reviewer or council flags a pattern for a completeness sweep

## Pattern Derivation Guide

Before you start the sweep, identify ALL categories of the pattern. The removed pattern can appear in many forms:

| Category | Search variants | Example target |
|---|---|---|
| Direct assignment | `= value`, `= "value"`, `= 'value'` | `vault_id = 1` |
| Fallback/default | `.get(key, fallback)`, `?? fallback`, `\|\| fallback`, `or fallback` | `record.get("vault_id", "1")` |
| SQL/schema | `DEFAULT value`, `NOT NULL DEFAULT value` | `vault_id INTEGER NOT NULL DEFAULT 1` |
| String literal | `"value"`, `'value'`, `f"...{value}"` | `df["vault_id"] = "1"` |
| Backfill/migration | `.fillna(value)`, `COALESCE(col, value)` | `df["vault_id"].fillna("1")` |
| Return value | `return value` | `return 1` |
| Config property | Property name, getter method | `orphan_vault_id` |
| Interface field | TypeScript/Python field declaration | `is_default?: boolean` |
| Import reference | `import`, `from ... import` | `from app.migrations.audit_vault_defaults import run_audit` |

For each category, construct a search pattern appropriate to your removed value.

## Required Procedure

After the primary change is implemented, run ALL of the following checks:

### 1. Multi-variant grep for the removed pattern

Run EACH variant pattern separately — don't combine them into one regex.

Example for removing a hardcoded value like `1`:
```
# Direct assignment and defaults
grep -rn '= 1\b' --include="*.py" --include="*.ts" --include="*.tsx" <backend_dir/> <frontend_dir/>
grep -rn '= "1"' --include="*.py" --include="*.ts" --include="*.tsx" <backend_dir/> <frontend_dir/>

# Fallback/get patterns
grep -rn '\.get(' --include="*.py" <backend_dir/>
grep -rn '\?\?' --include="*.ts" --include="*.tsx" <frontend_dir/>
grep -rn '||' --include="*.ts" --include="*.tsx" <frontend_dir/>

# Property/field names you removed
grep -rn '<removed_property_name>' --include="*.py" --include="*.ts" --include="*.tsx" <backend_dir/> <frontend_dir/>
grep -rn '<removed_function_name>' --include="*.py" --include="*.ts" --include="*.tsx" <backend_dir/> <frontend_dir/>
```

Substitute `<backend_dir/>` `<frontend_dir/>` and the removed value for your project.

### 2. Check configuration and environment files

Search for the removed pattern in:
- `.env.example`, `.env`, environment templates
- `docker-compose.yml`, `docker-compose.*.yml`
- `config.yaml`, `config.toml`, `settings.*`
- CI workflow files (`.github/workflows/*.yml`)

### 3. Check database schemas and migrations

Search for the removed default/fallback in:
- Schema definitions (CREATE TABLE, ALTER TABLE)
- Migration scripts
- ORM model field definitions
- Seed data files

### 4. Check documentation for stale behavior

Search README.md, docs/, and any markdown files for:
- Descriptions of the old behavior
- Examples that reference the removed pattern
- Warning messages / log messages that no longer exist
- Configuration documentation that mentions the removed property

### 5. Check test assertions for old behavior

Search test files for:
- Assertions that expect the old behavior (e.g. assert vault_id == 1)
- Mock setup that references the removed property
- Test names that describe the now-removed behavior
- Test fixtures or factories that use the old default

### 6. Verify no imports remain

If a module was deleted, grep for any import of that module across ALL languages:

```bash
# Python
grep -rn "from <deleted_module>" --include="*.py"
grep -rn "import <deleted_module>" --include="*.py"

# TypeScript/JavaScript
grep -rn "import.*<deleted_module>" --include="*.ts" --include="*.tsx"
grep -rn "require.*<deleted_module>" --include="*.ts" --include="*.tsx" --include="*.js"
```

### 7. Verify CI passes with the changes

Run the full CI suite (lint + test + build). If CI was green before the removal, any new failure indicates a missed reference.

## Exit Criteria

The sweep is complete when:
- All search patterns return zero matches in production code
- Documentation is updated (no stale behavior descriptions)
- Configuration and environment files are clean
- Test files asserting old behavior are updated or deleted
- CI is green (lint + tests + build pass)

## Forbidden Shortcuts

- Do NOT rationalize any remaining reference as "intentional" or "migration-only". End-to-end removal means EVERY last reference.
- Do NOT skip documentation checks — doc drift silently creates operator confusion.
- Do NOT combine multiple search variants into one regex — each variant catches different usage patterns.
- Do NOT assume auto-generated test files should be kept — delete one-time verification tests after review.
- Do NOT skip environment/configuration files — hardcoded defaults often live there.

## Delegation Template

When delegating a sweep task:

```
SKILLS: file:.opencode/skills/generated/post-removal-sweep/SKILL.md
TASK: Sweep for remaining <pattern> references after <primary change>
SEARCH_PATTERNS:
  - <pattern 1> (e.g., = "1", = 1)
  - <pattern 2> (e.g., .get("vault_id", "1"))
  - <pattern 3> (e.g., fillna("1"))
FILES_TO_SCAN: <backend_dir>/, <frontend_dir>/, docs/
CHECK_DOCS: true
CHECK_CONFIG: true
```

## Reviewer Checks

- Verify each search pattern category from the Pattern Derivation Guide was covered
- Verify the result for each pattern — zero matches in production code
- Verify documentation was checked, not just production code
- Verify test files asserting old behavior were updated or deleted
- Verify configuration and environment files were swept
- Any remaining reference must be accompanied by a code comment with a GitHub issue reference
