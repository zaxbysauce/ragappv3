---
name: reviewing-dependencies
description: Validate new and changed dependencies, imports, install commands, lockfile entries, and runtime tool assumptions for package hallucinations, slopsquatting, cross-ecosystem confusion, and version validity.
---

# Reviewing Dependencies

## Goal
Prevent package hallucinations, typosquatting, slopsquatting, version hallucinations, undeclared runtime tools, and import/install mismatches.

## Checklist
- Extract package names from imports, manifests, lockfiles, scripts, docs, install commands, examples, and comments that instruct installation.
- Verify each package in the canonical registry for the correct language ecosystem.
- Verify the pinned version exists.
- Check whether import name and install name differ and whether the project handles that correctly.
- Flag cross-ecosystem confusion.
- Flag suspicious generic package names such as `*-utils`, `*-helper`, `fast-*`, `*-wrapper`, `*-validator`, `*-manager`, or `*-advanced`, especially when newly published or low-signal.
- Flag imports not declared in manifests.
- Flag runtime dependence on tools, CLIs, or binaries not declared anywhere.
- Flag manifest changes that are not reflected in lockfiles when a lockfile is expected.

## Hard fail conditions
- package not found in canonical registry
- pinned version not found
- suspicious new package with no trust signal and no compelling reason
- package mentioned in docs/comments/examples but not represented in manifests or lockfiles when it should be
- cross-ecosystem dependency confusion that would break installation or runtime

## Output additions
Where relevant, include:
- canonical registry checked
- package name
- version checked
- mismatch type: phantom-package | version-hallucination | typosquat-risk | cross-ecosystem-confusion | undeclared-runtime-tool | import-install-mismatch
