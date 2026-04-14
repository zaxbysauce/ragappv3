#!/usr/bin/env python3
"""Migration: add_parent_window — add parent-document retrieval columns to LanceDB (Issue #12).

Adds four new columns to the LanceDB ``chunks`` table that are required for
parent-document / small-to-big retrieval:

- ``parent_doc_id``       (str, nullable) — denormalized file_id for query-time access
- ``parent_window_start`` (int, nullable) — char offset into source doc where parent window begins
- ``parent_window_end``   (int, nullable) — char offset into source doc where parent window ends
- ``chunk_position``      (int, nullable) — sequential chunk index within parent document

Existing rows are backfilled:
  - ``parent_doc_id``  ← ``file_id`` (already present on every chunk)
  - ``chunk_position`` ← ``chunk_index`` (already present on every chunk)
  - ``parent_window_start / end`` ← ``None`` (populated on next re-ingest)

Properties:
  - Idempotent: safe to run multiple times.
  - ``--dry-run`` mode reports rows that would be updated without writing.
  - Restores FTS and vector indices after table rewrite.

Usage:
    python -m app.migrations.add_parent_window [--dry-run] [--db-path PATH]

    Or via the VectorStore.migrate_add_parent_window() async method called from
    the lifespan hook or a management command.
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


async def run_migration(db_path: Path, dry_run: bool = False) -> int:
    """Run the parent window migration against a LanceDB database.

    Args:
        db_path: Path to the LanceDB directory.
        dry_run: If True, report affected rows without writing.

    Returns:
        Number of rows migrated (or that would have been migrated in dry-run).
    """
    # Import inside the function to allow standalone invocation without the
    # full application config being loaded.
    from app.services.vector_store import VectorStore

    store = VectorStore(db_path=db_path)
    await store.connect()

    count = await store.migrate_add_parent_window(dry_run=dry_run)

    mode = "[DRY RUN] " if dry_run else ""
    if count == 0:
        logger.info("%sMigration not needed — all rows already have parent window columns.", mode)
    else:
        logger.info("%sMigration complete: %d rows affected.", mode, count)

    return count


def main() -> None:
    """Entry point for CLI invocation."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Add parent_doc_id / parent_window_start / parent_window_end / chunk_position "
        "columns to the LanceDB chunks table."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report rows to be updated without making any changes.",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="Path to the LanceDB directory. Defaults to settings.lancedb_path.",
    )
    args = parser.parse_args()

    if args.db_path is None:
        try:
            from app.config import settings
            db_path = settings.lancedb_path
        except Exception as exc:
            print(
                f"ERROR: could not load settings to determine lancedb_path: {exc}\n"
                "Pass --db-path explicitly.",
                file=sys.stderr,
            )
            sys.exit(1)
    else:
        db_path = args.db_path

    count = asyncio.run(run_migration(db_path=db_path, dry_run=args.dry_run))

    if args.dry_run:
        print(f"[DRY RUN] {count} rows would be migrated.")
    else:
        print(f"Migration complete: {count} rows migrated.")


if __name__ == "__main__":
    main()
