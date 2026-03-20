"""Remove encrypted backups older than retention period."""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))


def cleanup_backups(directory: Path, retention_days: int) -> list[Path]:
    now = datetime.utcnow()
    retention_delta = timedelta(days=retention_days)
    removed: list[Path] = []
    for path in directory.glob("db_*_k*.enc"):
        try:
            mtime = datetime.utcfromtimestamp(path.stat().st_mtime)
        except FileNotFoundError:
            continue
        if now - mtime > retention_delta:
            try:
                path.unlink()
                removed.append(path)
            except (OSError, PermissionError, FileNotFoundError):
                # File may be locked or already deleted
                continue
    return removed


def main() -> None:
    parser = argparse.ArgumentParser(description="Cleanup old encrypted backups")
    parser.add_argument("--directory", type=Path, default=Path("backups"))
    parser.add_argument("--retention", type=int, default=30)
    args = parser.parse_args()

    args.directory.mkdir(parents=True, exist_ok=True)
    removed = cleanup_backups(args.directory, args.retention)
    if removed:
        for path in removed:
            print(f"Removed backup: {path}")


if __name__ == "__main__":
    main()
