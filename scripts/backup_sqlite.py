"""Create and verify a consistent SQLite backup using SQLite's backup API.

Usage:
    python scripts/backup_sqlite.py /data/snapbook.db /safe/offsite/path/snapbook.db

The destination should be outside the source volume and copied to protected
off-site storage. This script does not upload to a cloud provider.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path


def create_backup(source_path: str | Path, destination_path: str | Path) -> Path:
    source = Path(source_path).expanduser().resolve()
    destination = Path(destination_path).expanduser().resolve()

    if not source.is_file():
        raise FileNotFoundError(f"Source database does not exist: {source}")
    if source == destination:
        raise ValueError("Backup destination must differ from the source database.")

    destination.parent.mkdir(parents=True, exist_ok=True)

    # Create exclusively with owner-only permissions; this also prevents a
    # race from silently overwriting a backup created by another process.
    try:
        file_descriptor = os.open(
            destination,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
    except FileExistsError:
        raise FileExistsError(
            f"Refusing to overwrite an existing backup: {destination}"
        ) from None
    else:
        os.close(file_descriptor)

    try:
        source_uri = source.as_uri() + "?mode=ro"
        with sqlite3.connect(source_uri, uri=True, timeout=30) as source_db:
            with sqlite3.connect(destination, timeout=30) as backup_db:
                source_db.backup(backup_db)
                result = backup_db.execute("PRAGMA integrity_check").fetchone()[0]
                if result != "ok":
                    raise sqlite3.DatabaseError(f"Backup integrity check failed: {result}")
    except Exception:
        destination.unlink(missing_ok=True)
        raise

    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description="Create and verify a SQLite database backup.")
    parser.add_argument("source", help="Path to the live SQLite database")
    parser.add_argument("destination", help="New backup file path; must not already exist")
    args = parser.parse_args()

    backup = create_backup(args.source, args.destination)
    print(f"Backup created and integrity-checked: {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
