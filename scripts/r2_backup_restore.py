"""Encrypted OneCre8 volume backup/restore to private Cloudflare R2 (S3 API).

Backup (run only while application writes are paused, from a trusted host with the
production volume mounted/accessed locally):
  python scripts/r2_backup_restore.py backup /data

Restore (downloads and decrypts to a verified archive, then restores into a NEW
directory; never point at production):
  python scripts/r2_backup_restore.py restore ./onecre8-restore-drill

Required environment:
  R2_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
  R2_ACCESS_KEY_ID=...
  R2_SECRET_ACCESS_KEY=...
  R2_BUCKET=onecre8-production-backups
  ONECRE8_BACKUP_ENCRYPTION_KEY=<64 hex characters / 32 bytes>

Encrypted files use AES-256-GCM. The key is independent of R2 credentials and
must be backed up securely outside this bucket. This script never prints secrets.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import secrets
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from backup_volume import create_volume_backup
from restore_volume import restore_volume_backup

MAGIC = b"ONECRE8R2\x01"
NONCE_SIZE = 12


def _env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Required environment variable is missing: {name}")
    return value


def _key() -> bytes:
    raw = _env("ONECRE8_BACKUP_ENCRYPTION_KEY")
    try:
        key = bytes.fromhex(raw)
    except ValueError as exc:
        raise RuntimeError("Encryption key must be 64 hexadecimal characters.") from exc
    if len(key) != 32:
        raise RuntimeError("Encryption key must be exactly 32 bytes (64 hex characters).")
    return key


def _s3():
    return boto3.client(
        "s3",
        endpoint_url=_env("R2_ENDPOINT_URL"),
        aws_access_key_id=_env("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=_env("R2_SECRET_ACCESS_KEY"),
        region_name="auto",
    )


def _encrypt(source: Path, destination: Path, key: bytes) -> str:
    nonce = secrets.token_bytes(NONCE_SIZE)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    ciphertext = AESGCM(key).encrypt(nonce, source.read_bytes(), MAGIC)
    with destination.open("xb") as output:
        output.write(MAGIC + nonce + ciphertext)
    return digest


def _decrypt(source: Path, destination: Path, key: bytes) -> str:
    payload = source.read_bytes()
    if not payload.startswith(MAGIC) or len(payload) <= len(MAGIC) + NONCE_SIZE:
        raise ValueError("Encrypted backup format is invalid.")
    nonce_start = len(MAGIC)
    nonce = payload[nonce_start:nonce_start + NONCE_SIZE]
    ciphertext = payload[nonce_start + NONCE_SIZE:]
    plaintext = AESGCM(key).decrypt(nonce, ciphertext, MAGIC)
    with destination.open("xb") as output:
        output.write(plaintext)
    return hashlib.sha256(plaintext).hexdigest()


def backup(source_volume: Path) -> str:
    key = _key()
    client = _s3()
    bucket = _env("R2_BUCKET")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    object_key = f"backups/onecre8-volume-{stamp}.zip.aes"
    with tempfile.TemporaryDirectory(prefix="onecre8-r2-backup-") as temp_dir:
        temp = Path(temp_dir)
        archive = temp / "volume.zip"
        encrypted = temp / "volume.zip.aes"
        create_volume_backup(source_volume, archive)
        plaintext_sha256 = _encrypt(archive, encrypted, key)
        client.upload_file(
            str(encrypted), bucket, object_key,
            ExtraArgs={"Metadata": {"plaintext-sha256": plaintext_sha256,
                                  "encryption": "aes-256-gcm"}}
        )
        remote = client.head_object(Bucket=bucket, Key=object_key)
        if remote.get("ContentLength") != encrypted.stat().st_size:
            raise RuntimeError("R2 upload size verification failed.")
        if remote.get("Metadata", {}).get("plaintext-sha256") != plaintext_sha256:
            raise RuntimeError("R2 metadata verification failed.")
    print(f"Backup uploaded and verified: s3://{bucket}/{object_key}")
    print(f"Plain archive SHA-256: {plaintext_sha256}")
    return object_key


def restore(object_key: str, destination: Path) -> Path:
    key = _key()
    client = _s3()
    bucket = _env("R2_BUCKET")
    with tempfile.TemporaryDirectory(prefix="onecre8-r2-restore-") as temp_dir:
        temp = Path(temp_dir)
        encrypted = temp / "backup.zip.aes"
        archive = temp / "backup.zip"
        client.download_file(bucket, object_key, str(encrypted))
        remote = client.head_object(Bucket=bucket, Key=object_key)
        expected = remote.get("Metadata", {}).get("plaintext-sha256")
        actual = _decrypt(encrypted, archive, key)
        if not expected or actual != expected:
            raise RuntimeError("Backup SHA-256 verification failed; refusing restore.")
        result = restore_volume_backup(archive, destination)
    print(f"Restore verified into new destination: {result}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Encrypted R2 backup and restore for OneCre8.")
    sub = parser.add_subparsers(dest="command", required=True)
    backup_parser = sub.add_parser("backup", help="Create, encrypt and upload a full-volume backup.")
    backup_parser.add_argument("volume", type=Path, help="Mounted volume root, e.g. /data")
    restore_parser = sub.add_parser("restore", help="Download, decrypt and restore a backup.")
    restore_parser.add_argument("destination", type=Path, help="New restore directory (must not exist).")
    restore_parser.add_argument("--object-key", help="R2 object key; omit to restore latest backup.")
    args = parser.parse_args()

    if args.command == "backup":
        backup(args.volume)
    else:
        object_key = args.object_key
        if not object_key:
            client = _s3()
            bucket = _env("R2_BUCKET")
            response = client.list_objects_v2(Bucket=bucket, Prefix="backups/")
            objects = sorted(response.get("Contents", []), key=lambda item: item["LastModified"], reverse=True)
            if not objects:
                raise RuntimeError("No backups found in R2.")
            object_key = objects[0]["Key"]
        restore(object_key, args.destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
