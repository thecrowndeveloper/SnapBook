import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.backup_volume import create_volume_backup


class FullVolumeBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "volume"
        self.root.mkdir()
        self.destination_dir = Path(self.temp.name) / "external"
        self.destination_dir.mkdir()
        with sqlite3.connect(self.root / "snapbook.db") as connection:
            connection.execute("CREATE TABLE sample (value TEXT)")
            connection.execute("INSERT INTO sample VALUES ('preserved')")
        (self.root / "portfolio").mkdir()
        (self.root / "portfolio" / "photo.webp").write_bytes(b"portfolio-image")
        (self.root / "message-attachments").mkdir()
        (self.root / "message-attachments" / "private.webp").write_bytes(b"private-image")

    def tearDown(self):
        self.temp.cleanup()

    def test_archives_database_and_both_media_directories(self):
        destination = self.destination_dir / "backup.zip"
        create_volume_backup(self.root, destination)
        with zipfile.ZipFile(destination) as archive:
            self.assertEqual(
                set(archive.namelist()),
                {"snapbook.db", "portfolio/photo.webp", "message-attachments/private.webp"},
            )
            with tempfile.NamedTemporaryFile() as database_copy:
                database_copy.write(archive.read("snapbook.db"))
                database_copy.flush()
                with sqlite3.connect(database_copy.name) as connection:
                    self.assertEqual(
                        connection.execute("SELECT value FROM sample").fetchone()[0],
                        "preserved",
                    )
                    self.assertEqual(
                        connection.execute("PRAGMA integrity_check").fetchone()[0],
                        "ok",
                    )

    def test_refuses_destination_inside_source_volume(self):
        with self.assertRaises(ValueError):
            create_volume_backup(self.root, self.root / "backup.zip")

    def test_refuses_to_overwrite_existing_archive(self):
        destination = self.destination_dir / "backup.zip"
        destination.write_bytes(b"existing")
        with self.assertRaises(FileExistsError):
            create_volume_backup(self.root, destination)
        self.assertEqual(destination.read_bytes(), b"existing")


if __name__ == "__main__":
    unittest.main()
