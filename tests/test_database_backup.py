import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.backup_sqlite import create_backup


class SQLiteBackupTests(unittest.TestCase):
    def test_backup_contains_committed_data_and_passes_integrity_check(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "live.db"
            destination = Path(directory) / "backups" / "verified.db"

            with sqlite3.connect(source) as con:
                con.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, value TEXT)")
                con.execute("INSERT INTO sample (value) VALUES ('preserve me')")

            create_backup(source, destination)

            with sqlite3.connect(destination) as backup:
                self.assertEqual(
                    backup.execute("SELECT value FROM sample").fetchone()[0],
                    "preserve me",
                )
                self.assertEqual(
                    backup.execute("PRAGMA integrity_check").fetchone()[0],
                    "ok",
                )

    def test_backup_refuses_to_overwrite_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "live.db"
            destination = Path(directory) / "backup.db"
            sqlite3.connect(source).close()
            destination.write_bytes(b"keep existing file")

            with self.assertRaises(FileExistsError):
                create_backup(source, destination)

            self.assertEqual(destination.read_bytes(), b"keep existing file")

    def test_backup_rejects_same_source_and_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "live.db"
            sqlite3.connect(source).close()

            with self.assertRaises(ValueError):
                create_backup(source, source)


if __name__ == "__main__":
    unittest.main()
