#!/usr/bin/env python3
"""
Behavioral tests for init-review-run.py and validate-skill-package.py fixes.

Covers:
  F-005  datetime.utcnow()  -> datetime.now(timezone.utc)  (lines 107, 126)
  F-006  parse_frontmatter() wrapped in try/except with clean stderr
  F-007  WINDOWS_RESERVED set added; validate_run_id rejects reserved names
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path
from typing import Any

# Locate the scripts directory (../scripts relative to this test file)
_SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"


def _load_script_module(name: str, filename: str) -> Any:
    """
    Load a Python script that uses hyphens in its filename as a module.

    Scripts like 'init-review-run.py' can't be imported with a normal
    `import hyphened-name` because Python identifiers don't allow hyphens.
    We use importlib to load them by file path and assign an underscore
    name so the rest of the test can use the module naturally.
    """
    file_path = _SCRIPTS_DIR / filename
    spec = importlib.util.spec_from_file_location(name, file_path)
    assert spec is not None, f"Could not create spec for {file_path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


# Load the two helper scripts as modules
# (filenames use hyphens; we assign underscore names for Python use)
init_review_run = _load_script_module("init_review_run", "init-review-run.py")
validate_skill_package = _load_script_module("validate_skill_package", "validate-skill-package.py")

import unittest


class TestDatetimeFixes(unittest.TestCase):
    """F-005 – datetime.utcnow() replacements."""

    def setUp(self) -> None:
        self.repo_root = Path(
            subprocess.check_output(
                ["git", "rev-parse", "--show-toplevel"],
                text=True,
            ).strip()
        )
        self.run_id = f"test-dt-{os.getpid()}"
        self.created_dirs: list[Path] = []

    def tearDown(self) -> None:
        # Clean up any run directories we created
        runs_root = self.repo_root / ".swarm" / "review-v8" / "runs"
        for run_id in [self.run_id, "test-valid-123"]:
            p = runs_root / run_id
            if p.exists():
                shutil.rmtree(p, ignore_errors=True)

    def test_datetime_no_deprecation_warning(self) -> None:
        """Running the script with -W error:DeprecationWarning must not raise."""
        script = _SCRIPTS_DIR / "init-review-run.py"
        result = subprocess.run(
            [sys.executable, "-W", "error::DeprecationWarning", str(script), "--run-id", self.run_id],
            capture_output=True,
            text=True,
            cwd=str(self.repo_root),
        )
        self.assertEqual(
            result.returncode,
            0,
            f"Expected exit 0, got {result.returncode}\nstderr: {result.stderr}\nstdout: {result.stdout}",
        )

    def test_datetime_trailing_z_format(self) -> None:
        """metadata.json created_at_utc must end with 'Z' and match ISO 8601 pattern."""
        script = _SCRIPTS_DIR / "init-review-run.py"
        result = subprocess.run(
            [sys.executable, str(script), "--run-id", self.run_id],
            capture_output=True,
            text=True,
            cwd=str(self.repo_root),
        )
        self.assertEqual(
            result.returncode,
            0,
            f"Expected exit 0, got {result.returncode}\nstderr: {result.stderr}\nstdout: {result.stdout}",
        )

        run_dir = Path(result.stdout.strip())
        self.created_dirs.append(run_dir)
        self.assertTrue(run_dir.exists(), f"Run directory not created: {run_dir}")

        metadata_path = run_dir / "metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        created_at = metadata["created_at_utc"]

        # Must end with Z (not +00:00)
        self.assertTrue(
            created_at.endswith("Z"),
            f"created_at_utc does not end with Z: {created_at}",
        )

        # Must match strict ISO 8601 pattern: YYYY-MM-DDTHH:MM:SSZ
        ISO8601_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        self.assertIsNotNone(
            ISO8601_RE.fullmatch(created_at),
            f"created_at_utc does not match ISO 8601 pattern: {created_at}",
        )


class TestValidateSkillPackage(unittest.TestCase):
    """F-006 – parse_frontmatter error handling."""

    def test_parse_frontmatter_unclosed_raises_clean_error(self) -> None:
        """An SKILL.md without closing --- must exit 1 with clean stderr, no Traceback."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir)
            # Create a minimal skill structure with unclosed frontmatter
            skill_md = skill_dir / "SKILL.md"
            skill_md.write_text("name: foo\n", encoding="utf-8")

            # Touch required sibling files so we don't fail on missing files first
            for rel in validate_skill_package.REQUIRED:
                if rel == "SKILL.md":
                    continue
                p = skill_dir / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.touch()

            script = _SCRIPTS_DIR / "validate-skill-package.py"
            result = subprocess.run(
                [sys.executable, str(script), str(skill_dir)],
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 1, f"Expected exit 1, got {result.returncode}")
            self.assertIn("error:", result.stderr.lower(), f"stderr should contain 'error:': {result.stderr}")
            self.assertNotIn(
                "Traceback",
                result.stderr,
                f"stderr must not contain Traceback: {result.stderr}",
            )

    def test_parse_frontmatter_valid_passes(self) -> None:
        """validate-skill-package.py against the canonical skill dir must exit 0."""
        canonical = Path(__file__).parent.parent  # .../codebase-review-swarm
        script = _SCRIPTS_DIR / "validate-skill-package.py"
        result = subprocess.run(
            [sys.executable, str(script), str(canonical)],
            capture_output=True,
            text=True,
        )

        self.assertEqual(
            result.returncode,
            0,
            f"Expected exit 0, got {result.returncode}\nstderr: {result.stderr}",
        )
        self.assertIn(
            "skill package OK",
            result.stdout,
            f"stdout should contain 'skill package OK': {result.stdout}",
        )


class TestValidateRunId(unittest.TestCase):
    """F-007 – Windows reserved name rejection and path-segment checks."""

    def setUp(self) -> None:
        self.repo_root = Path(
            subprocess.check_output(
                ["git", "rev-parse", "--show-toplevel"],
                text=True,
            ).strip()
        )
        self._created: list[Path] = []

    def tearDown(self) -> None:
        for p in self._created:
            if p.exists():
                shutil.rmtree(p, ignore_errors=True)

    # -------------------------------------------------------------------------
    # In-process tests (import and call the function directly)
    # -------------------------------------------------------------------------

    def test_reserved_name_con_raises(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            init_review_run.validate_run_id("CON")
        self.assertIn("Windows reserved", str(ctx.exception))

    def test_reserved_name_con_lowercase_raises(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            init_review_run.validate_run_id("con")
        self.assertIn("Windows reserved", str(ctx.exception))

    def test_reserved_name_com1_raises(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            init_review_run.validate_run_id("COM1")
        self.assertIn("Windows reserved", str(ctx.exception))

    def test_reserved_name_lpt9_lowercase_raises(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            init_review_run.validate_run_id("lpt9")
        self.assertIn("Windows reserved", str(ctx.exception))

    def test_dotdot_raises(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            init_review_run.validate_run_id("..")
        self.assertIn("path segments", str(ctx.exception).lower())

    def test_dot_raises(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            init_review_run.validate_run_id(".")
        self.assertIn("path segments", str(ctx.exception).lower())

    def test_valid_run_id_returns_unchanged(self) -> None:
        result = init_review_run.validate_run_id("test-valid-123")
        self.assertEqual(result, "test-valid-123")

    # -------------------------------------------------------------------------
    # Subprocess tests (script-level behavior including exit codes / stderr)
    # -------------------------------------------------------------------------

    def _script_run_id(self, run_id: str) -> subprocess.CompletedProcess:
        script = _SCRIPTS_DIR / "init-review-run.py"
        return subprocess.run(
            [sys.executable, str(script), "--run-id", run_id],
            capture_output=True,
            text=True,
            cwd=str(self.repo_root),
        )

    def test_windows_reserved_names_rejected_subprocess(self) -> None:
        """CON, con, COM1, lpt9 must be rejected via subprocess with exit 2."""
        for name in ("CON", "con", "COM1", "lpt9"):
            with self.subTest(name=name):
                result = self._script_run_id(name)
                self.assertEqual(
                    result.returncode,
                    2,
                    f"--run-id {name!r} should exit 2; got {result.returncode}; stderr={result.stderr}",
                )
                self.assertIn(
                    f"Invalid --run-id '{name}'",
                    result.stderr,
                    f"stderr should mention the reserved name; got: {result.stderr}",
                )
                self.assertIn("Windows reserved", result.stderr)

    def test_dot_dotdot_rejected_subprocess(self) -> None:
        """`.` and `..` must be rejected via subprocess with exit 2."""
        for name in (".", ".."):
            with self.subTest(name=name):
                result = self._script_run_id(name)
                self.assertEqual(
                    result.returncode,
                    2,
                    f"--run-id {name!r} should exit 2; got {result.returncode}; stderr={result.stderr}",
                )
                self.assertIn("path segments", result.stderr.lower())

    def test_valid_run_id_still_works_subprocess(self) -> None:
        """A non-reserved run-id like 'test-valid-123' must succeed and create metadata.json."""
        run_id = "test-valid-123"
        result = self._script_run_id(run_id)
        self.assertEqual(
            result.returncode,
            0,
            f"Expected exit 0, got {result.returncode}\nstderr: {result.stderr}",
        )

        run_dir = Path(result.stdout.strip())
        self._created.append(run_dir)
        self.assertTrue((run_dir / "metadata.json").exists())
        self.assertTrue((run_dir / "artifacts").exists())
        self.assertTrue((run_dir / "ledgers").exists())


class TestReservedNameCheckUnconditional(unittest.TestCase):
    """F-007 – documentation test: check is unconditional (not platform-gated)."""

    def test_reserved_check_is_unconditional(self) -> None:
        """
        The WINDOWS_RESERVED check in validate_run_id is unconditional.
        The check reads `raw.upper() in WINDOWS_RESERVED` without any
        `if sys.platform == "win32"` guard, so it fires on all platforms.
        This is by design so that run-ids are portable and fail fast.
        """
        source = _SCRIPTS_DIR / "init-review-run.py"
        code = source.read_text(encoding="utf-8")

        # Ensure WINDOWS_RESERVED check exists
        self.assertIn("WINDOWS_RESERVED", code)

        # Find the validate_run_id function
        fn_match = re.search(r"def validate_run_id.*?(?=\ndef |\nclass |\Z)", code, re.DOTALL)
        self.assertIsNotNone(fn_match, "Could not find validate_run_id function")
        fn_body = fn_match.group()

        # The check must not be inside an `if sys.platform` or `if platform.system()` block
        platform_guard_patterns = [
            r"if\s+sys\.platform",
            r"if\s+platform\.",
            r"if\s+os\.name",
            r"if\s+sys\.win",
        ]
        for pattern in platform_guard_patterns:
            self.assertNotRegex(
                fn_body,
                pattern,
                f"validate_run_id must not platform-gate the WINDOWS_RESERVED check. "
                f"Found pattern {pattern!r} inside the function.",
            )


if __name__ == "__main__":
    unittest.main()
