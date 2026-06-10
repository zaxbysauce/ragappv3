---
name: codebase-review-swarm
description: Run a rigorous, quote-grounded codebase review or security/QA/accessibility/performance/AI-slop/enhancement audit. Adapter pointing to the canonical opencode-swarm skill; refer to that for the full protocol.
license: MIT
metadata:
  version: "8.2.0"
  adapter_for: ".opencode/skills/codebase-review-swarm/"
---

# Codebase Review Swarm (Codex adapter)

This is a thin pointer to the canonical skill at
`.opencode/skills/codebase-review-swarm/`. Codex runners should load
the canonical SKILL.md there for the full v8.2 protocol, schemas, and
helper scripts. Run Phase 0 inventory, stop for review-mode selection
unless preselected, and do not modify source files.
