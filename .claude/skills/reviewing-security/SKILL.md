---
name: reviewing-security
description: Inspect trust boundaries, validation, authn/authz, deserialization, command execution, path handling, secrets, and failure handling with an evidence-first security review.
---

# Reviewing Security

## Trust boundaries
Enumerate and inspect:
- HTTP inputs
- CLI args
- env vars
- file reads and writes
- subprocess invocations
- deserializers and parsers
- SQL and ORM boundaries
- IPC and queue inputs
- authn and authz checks
- template and rendering sinks

## Mandatory questions
- Is input validated at the actual boundary?
- Can user input reach filesystem, shell, SQL, template, or render sinks?
- Are privileged operations guarded where they execute?
- Are secrets or tokens logged, hardcoded, or exposed in examples?
- Are errors swallowed instead of handled?
- Are there security-relevant defaults that fail open?

## Hard fail conditions
- missing auth or authz on privileged path
- injection or path traversal risk
- unsafe deserialization or arbitrary code execution pattern
- secret exposure
- trust boundary with no meaningful validation
