"""Safely restore a verified OneCre8 volume archive into a NEW directory.

This utility never overwrites an existing destination. Stop the application and
restore to a new/empty volume or staging directory, then follow the runbook.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

ALLOWED_ROOTS = ("portfolio/", "message-attachments/")


def _validate_member(info: zipfile.ZipInfo) -> str:
    name = info.filename
    if not name or "\\" in name:
        raise ValueError(f"Unsafe archive member: {name!r}")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError(f"Unsafe archive member: {name!r}")
    mode = info.external_attr >> 16
    if stat.S_ISLNK(mode):
        raise ValueError(f"Refusing symlink in archive: {name}")
    if name == "snapbook.db":
        return name
    if not info.is_dir() and any(name.startswith(root) for root in ALLOWED_ROOTS):
        return name
    if info.is_dir() and any(name.rstrip("/") == root.rstrip("/") for root in ALLOWED_ROOTS):
        return name
    raise ValueError(f"Unexpected archive member: {name}")


def restore_volume_backup(archive_path: str | Path, destination_path: str | Path) -> Path:
    archive_file = Path(archive_path).expanduser().resolve()
    destination = Path(destination_path).expanduser().resolve()
    if not archive_file.is_file():
        raise FileNotFoundError(f"Backup archive does not exist: {archive_file}")
    if destination.exists():
        raise FileExistsError(f"Restore destination already exists; refusing to overwrite: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="onecre8-restore-", dir=destination.parent) as temp:
        staging = Path(temp) / "restored"
        staging.mkdir(mode=0o700)
        seen_database = False
        with zipfile.ZipFile(archive_file, "r") as archive:
            corrupt = archive.testzip()
            if corrupt:
                raise zipfile.BadZipFile(f"Archive verification failed: {corrupt}")
            for info in archive.infolist():
                member = _validate_member(info)
                if info.is_dir():
                    continue
                if member == "snapbook.db":
                    if seen_database:
                        raise ValueError("Archive contains more than one database.")
                    seen_database = True
                target = staging.joinpath(*PurePosixPath(member).parts)
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                with archive.open(info, "r") as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
                os.chmod(target, 0o600)
        if not seen_database:
            raise ValueError("Archive does not contain snapbook.db.")
        database = staging / "snapbook.db"
        with sqlite3.connect(database) as connection:
            result = connection.execute("PRAGMA integrity_check").fetchone()[0]
            if result != "ok":
                raise sqlite3.DatabaseError(f"Restored database integrity check failed: {result}")
        staging.rename(destination)
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description="Safely restore a OneCre8 volume backup.")
    parser.add_argument("archive", help="Verified OneCre8 .zip backup")
    parser.add_argument("destination", help="New destination directory; must not exist")
    args = parser.parse_args()
    result = restore_volume_backup(args.archive, args.destination)
    print(f"Restore completed and SQLite integrity verified: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
