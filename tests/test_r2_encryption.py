import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from r2_backup_restore import _decrypt, _encrypt


class R2EncryptionTests(unittest.TestCase):
    def setUp(self):
        self.key = bytes(range(32))
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_round_trip_and_digest(self):
        original = self.root / "original.bin"
        encrypted = self.root / "encrypted.bin"
        decrypted = self.root / "decrypted.bin"
        original.write_bytes(b"OneCre8 backup test data" * 50000)
        digest = _encrypt(original, encrypted, self.key)
        recovered_digest = _decrypt(encrypted, decrypted, self.key)
        self.assertEqual(decrypted.read_bytes(), original.read_bytes())
        self.assertEqual(recovered_digest, digest)

    def test_tampered_ciphertext_is_rejected(self):
        original = self.root / "original.bin"
        encrypted = self.root / "encrypted.bin"
        decrypted = self.root / "decrypted.bin"
        original.write_bytes(b"backup data")
        _encrypt(original, encrypted, self.key)
        data = bytearray(encrypted.read_bytes())
        data[len(data) // 2] ^= 1
        encrypted.write_bytes(data)
        with self.assertRaises(Exception):
            _decrypt(encrypted, decrypted, self.key)

    def test_wrong_key_is_rejected(self):
        original = self.root / "original.bin"
        encrypted = self.root / "encrypted.bin"
        decrypted = self.root / "decrypted.bin"
        original.write_bytes(b"backup data")
        _encrypt(original, encrypted, self.key)
        with self.assertRaises(Exception):
            _decrypt(encrypted, decrypted, bytes(reversed(self.key)))


if __name__ == "__main__":
    unittest.main()
