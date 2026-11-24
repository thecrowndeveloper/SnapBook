"""Regression tests for safe OneCre8 volume backup restoration."""
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.restore_volume import restore_volume_backup


class RestoreVolumeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="onecre8-restore-tests-")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def make_database(self, path):
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE restore_check (value TEXT)")
            db.execute("INSERT INTO restore_check VALUES ('ok')")

    def test_restores_database_and_media_to_new_directory(self):
        db = self.root / "source.db"
        self.make_database(db)
        archive = self.root / "backup.zip"
        with zipfile.ZipFile(archive, "w") as output:
            output.write(db, "snapbook.db")
            output.writestr("portfolio/photo.webp", b"image-data")
            output.writestr("message-attachments/attachment.png", b"private-image")
        destination = self.root / "restored"
        restore_volume_backup(archive, destination)
        self.assertTrue((destination / "snapbook.db").is_file())
        self.assertEqual((destination / "portfolio/photo.webp").read_bytes(), b"image-data")
        self.assertEqual((destination / "message-attachments/attachment.png").read_bytes(), b"private-image")
        with sqlite3.connect(destination / "snapbook.db") as restored:
            self.assertEqual(restored.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_refuses_path_traversal_archive_member(self):
        db = self.root / "source.db"
        self.make_database(db)
        archive = self.root / "unsafe.zip"
        with zipfile.ZipFile(archive, "w") as output:
            output.write(db, "snapbook.db")
            output.writestr("../outside.txt", b"do-not-write")
        with self.assertRaisesRegex(ValueError, "Unsafe archive member"):
            restore_volume_backup(archive, self.root / "restored")
        self.assertFalse((self.root / "outside.txt").exists())

    def test_refuses_existing_destination(self):
        archive = self.root / "empty.zip"
        with zipfile.ZipFile(archive, "w") as output:
            pass
        destination = self.root / "already-there"
        destination.mkdir()
        with self.assertRaises(FileExistsError):
            restore_volume_backup(archive, destination)

    def test_requires_database_in_archive(self):
        archive = self.root / "no-database.zip"
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("portfolio/photo.webp", b"image")
        with self.assertRaisesRegex(ValueError, "does not contain snapbook.db"):
            restore_volume_backup(archive, self.root / "restored")


if __name__ == "__main__":
    unittest.main()
