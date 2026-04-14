#!/usr/bin/env python3
"""Migration: audit_vault_defaults — identify auto-assigned vault-1 documents (Issue #13).

The upload API previously accepted requests without a ``vault_id`` and silently
assigned ``vault_id=1`` (the "orphan" vault).  This migration queries the SQLite
``files`` table for documents that are likely to have been auto-assigned and logs
them for operator review.

It does NOT move or modify any documents — it only surfaces the situation so an
operator can decide whether to reassign them to the correct vault.

A document is flagged as a candidate for review when **all** of the following hold:
  1. ``vault_id = 1``
  2. ``source = 'upload'`` (not auto-scan or email ingestion which legitimately use vault 1)
  3. ``status = 'indexed'``

Operators should review the flagged list and manually move documents to the correct
vault if needed.

Properties:
  - Read-only: makes no changes to any data.
  - Idempotent: safe to run multiple times.
  - Output: logs one line per flagged document; also writes a summary to stdout.

Usage:
    python -m app.migrations.audit_vault_defaults [--db-path PATH] [--output-csv PATH]
"""

import argparse
import csv
import logging
import sqlite3
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def run_audit(db_path: Path, output_csv: Path | None = None) -> list[dict]:
    """Query SQLite for auto-assigned vault-1 documents.

    Args:
        db_path: Path to the SQLite database file (settings.sqlite_path).
        output_csv: Optional path to write results as CSV.

    Returns:
        List of row dicts for flagged documents.
    """
    if not db_path.exists():
        logger.warning("SQLite database not found at %s — no audit performed.", db_path)
        return []

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    try:
        # Verify the files table exists
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='files'"
        )
        if cursor.fetchone() is None:
            logger.info("'files' table does not exist — no audit needed.")
            return []

        # Check available columns (source column may not exist on old schemas)
        cursor = conn.execute("PRAGMA table_info(files)")
        columns = {row[1] for row in cursor.fetchall()}

        if "source" in columns:
            query = (
                "SELECT id, file_name, file_path, vault_id, source, status, created_at "
                "FROM files "
                "WHERE vault_id = 1 AND source = 'upload' AND status = 'indexed' "
                "ORDER BY created_at"
            )
        else:
            # Older schema without source column — flag all vault-1 indexed uploads
            logger.warning(
                "Column 'source' missing from files table — flagging all vault_id=1 indexed files."
            )
            query = (
                "SELECT id, file_name, file_path, vault_id, status, created_at "
                "FROM files "
                "WHERE vault_id = 1 AND status = 'indexed' "
                "ORDER BY created_at"
            )

        rows = conn.execute(query).fetchall()
        results = [dict(row) for row in rows]

        logger.info(
            "Audit complete: %d document(s) flagged as potential auto-assigned vault-1 uploads.",
            len(results),
        )

        for row in results:
            logger.warning(
                "FLAGGED: id=%s file=%r path=%r created_at=%s",
                row.get("id"),
                row.get("file_name"),
                row.get("file_path"),
                row.get("created_at"),
            )

        if output_csv and results:
            fieldnames = list(results[0].keys())
            with open(output_csv, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(results)
            logger.info("Results written to %s", output_csv)

        return results

    finally:
        conn.close()


def main() -> None:
    """Entry point for CLI invocation."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Audit SQLite files table for documents auto-assigned to vault_id=1."
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="Path to the SQLite database file. Defaults to settings.sqlite_path.",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=None,
        help="Optional path to write the flagged document list as a CSV file.",
    )
    args = parser.parse_args()

    if args.db_path is None:
        try:
            from app.config import settings
            db_path = settings.sqlite_path
        except Exception as exc:
            print(
                f"ERROR: could not load settings to determine sqlite_path: {exc}\n"
                "Pass --db-path explicitly.",
                file=sys.stderr,
            )
            sys.exit(1)
    else:
        db_path = args.db_path

    results = run_audit(db_path=db_path, output_csv=args.output_csv)

    print(f"\nAudit result: {len(results)} document(s) flagged.")
    if results:
        print(
            "\nThese documents were uploaded without an explicit vault_id and were "
            "auto-assigned to vault_id=1 (the orphan vault).\n"
            "Review the list and reassign documents to the correct vault if needed."
        )
    else:
        print("No auto-assigned vault-1 uploads found.")


if __name__ == "__main__":
    main()
