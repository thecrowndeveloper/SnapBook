"""Create a verified, full-volume OneCre8 backup archive.

Run only while application writes are paused:
    python scripts/backup_volume.py /data /secure-offsite/onecre8-YYYYMMDD-HHMMSS.zip

The destination must be outside the source volume and on protected storage.
The archive contains the SQLite database plus portfolio and private message
image uploads. This script does not encrypt or upload the archive.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import tempfile
import zipfile
from pathlib import Path


MEDIA_DIRECTORIES = ("portfolio", "message-attachments")


def _sqlite_backup(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(f"Source database does not exist: {source}")
    source_uri = source.as_uri() + "?mode=ro"
    with sqlite3.connect(source_uri, uri=True, timeout=30) as source_db:
        with sqlite3.connect(destination, timeout=30) as backup_db:
            source_db.backup(backup_db)
            result = backup_db.execute("PRAGMA integrity_check").fetchone()[0]
            if result != "ok":
                raise sqlite3.DatabaseError(f"Backup integrity check failed: {result}")


def _iter_media_files(root: Path):
    for directory_name in MEDIA_DIRECTORIES:
        directory = root / directory_name
        if not directory.exists():
            continue
        if directory.is_symlink():
            raise ValueError(f"Refusing to archive symlink: {directory}")
        for path in sorted(directory.rglob("*")):
            if path.is_symlink():
                raise ValueError(f"Refusing to archive symlink: {path}")
            if path.is_file():
                yield path


def create_volume_backup(source_root: str | Path, destination_path: str | Path) -> Path:
    source = Path(source_root).expanduser().resolve()
    destination = Path(destination_path).expanduser().resolve()
    database = source / "snapbook.db"

    if not source.is_dir():
        raise NotADirectoryError(f"Volume directory does not exist: {source}")
    if destination == source or source in destination.parents:
        raise ValueError("Backup destination must be outside the source volume.")
    if destination.suffix.lower() != ".zip":
        raise ValueError("Backup destination must use the .zip extension.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise FileExistsError(f"Refusing to overwrite an existing backup: {destination}") from None
    else:
        os.close(descriptor)

    try:
        with tempfile.TemporaryDirectory(prefix="onecre8-backup-", dir=destination.parent) as temp:
            database_copy = Path(temp) / "snapbook.db"
            _sqlite_backup(database, database_copy)

            with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.write(database_copy, "snapbook.db")
                for media_file in _iter_media_files(source):
                    archive.write(media_file, media_file.relative_to(source).as_posix())

            with zipfile.ZipFile(destination, "r") as archive:
                corrupt_member = archive.testzip()
                if corrupt_member:
                    raise zipfile.BadZipFile(f"Archive verification failed: {corrupt_member}")
                extracted_db = Path(temp) / "verified-snapbook.db"
                with archive.open("snapbook.db") as archived_db, extracted_db.open("wb") as output:
                    while chunk := archived_db.read(1024 * 1024):
                        output.write(chunk)
                with sqlite3.connect(extracted_db) as check_db:
                    result = check_db.execute("PRAGMA integrity_check").fetchone()[0]
                    if result != "ok":
                        raise sqlite3.DatabaseError(f"Archived database integrity check failed: {result}")
        os.chmod(destination, 0o600)
    except Exception:
        destination.unlink(missing_ok=True)
        raise

    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a verified OneCre8 full-volume backup.")
    parser.add_argument("source", help="Mounted Railway volume directory, e.g. /data")
    parser.add_argument("destination", help="New ZIP archive path on protected external storage")
    args = parser.parse_args()
    result = create_volume_backup(args.source, args.destination)
    print(f"Verified full-volume backup created: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
