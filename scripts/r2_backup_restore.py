"""Encrypted OneCre8 volume backup/restore to private Cloudflare R2 (S3 API).

Environment: R2_ENDPOINT_URL, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET,
ONECRE8_BACKUP_ENCRYPTION_KEY (64 hex chars / 32 bytes). The encryption key is
independent of R2 credentials and must be stored safely outside R2.
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
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from backup_volume import create_volume_backup
from restore_volume import restore_volume_backup

MAGIC = b"ONECRE8R2\x01"
NONCE_SIZE = 12
TAG_SIZE = 16
CHUNK = 1024 * 1024


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
    return boto3.client("s3", endpoint_url=_env("R2_ENDPOINT_URL"),
        aws_access_key_id=_env("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=_env("R2_SECRET_ACCESS_KEY"), region_name="auto")


def _encrypt(source: Path, destination: Path, key: bytes) -> str:
    nonce = secrets.token_bytes(NONCE_SIZE)
    digest = hashlib.sha256()
    encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
    with source.open("rb") as src, destination.open("xb") as dst:
        dst.write(MAGIC + nonce)
        while chunk := src.read(CHUNK):
            digest.update(chunk)
            dst.write(encryptor.update(chunk))
        dst.write(encryptor.finalize())
        dst.write(encryptor.tag)
    return digest.hexdigest()


def _decrypt(source: Path, destination: Path, key: bytes) -> str:
    size = source.stat().st_size
    header = len(MAGIC) + NONCE_SIZE
    if size <= header + TAG_SIZE:
        raise ValueError("Encrypted backup file is too short.")
    with source.open("rb") as src:
        if src.read(len(MAGIC)) != MAGIC:
            raise ValueError("Encrypted backup format is invalid.")
        nonce = src.read(NONCE_SIZE)
        src.seek(-TAG_SIZE, os.SEEK_END)
        tag = src.read(TAG_SIZE)
        ciphertext_length = size - header - TAG_SIZE
        src.seek(header)
        decryptor = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
        digest = hashlib.sha256()
        with destination.open("xb") as dst:
            remaining = ciphertext_length
            while remaining:
                chunk = src.read(min(CHUNK, remaining))
                if not chunk:
                    raise ValueError("Encrypted backup is truncated.")
                remaining -= len(chunk)
                plain = decryptor.update(chunk)
                digest.update(plain)
                dst.write(plain)
            tail = decryptor.finalize()  # authenticates GCM tag
            digest.update(tail)
            dst.write(tail)
    return digest.hexdigest()


def backup(volume: Path) -> str:
    key, client, bucket = _key(), _s3(), _env("R2_BUCKET")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    object_key = f"backups/onecre8-volume-{stamp}.zip.enc"
    with tempfile.TemporaryDirectory(prefix="onecre8-r2-backup-") as folder:
        tmp = Path(folder)
        archive, encrypted = tmp / "volume.zip", tmp / "volume.zip.enc"
        create_volume_backup(volume, archive)
        sha = _encrypt(archive, encrypted, key)
        client.upload_file(str(encrypted), bucket, object_key,
            ExtraArgs={"Metadata": {"plaintext-sha256": sha, "encryption": "aes-256-gcm"}})
        head = client.head_object(Bucket=bucket, Key=object_key)
        if head.get("ContentLength") != encrypted.stat().st_size or head.get("Metadata", {}).get("plaintext-sha256") != sha:
            raise RuntimeError("Uploaded backup verification failed.")
    print(f"Verified encrypted backup uploaded: s3://{bucket}/{object_key}")
    print(f"Archive SHA-256: {sha}")
    return object_key


def restore(object_key: str, destination: Path) -> Path:
    key, client, bucket = _key(), _s3(), _env("R2_BUCKET")
    with tempfile.TemporaryDirectory(prefix="onecre8-r2-restore-") as folder:
        tmp = Path(folder)
        encrypted, archive = tmp / "volume.zip.enc", tmp / "volume.zip"
        client.download_file(bucket, object_key, str(encrypted))
        head = client.head_object(Bucket=bucket, Key=object_key)
        expected = head.get("Metadata", {}).get("plaintext-sha256")
        actual = _decrypt(encrypted, archive, key)
        if not expected or actual != expected:
            raise RuntimeError("Archive checksum verification failed; restore refused.")
        restored = restore_volume_backup(archive, destination)
    print(f"Restore verified at new destination: {restored}")
    return restored


def latest_object_key(client, bucket: str) -> str:
    paginator = client.get_paginator("list_objects_v2")
    candidates = []
    for page in paginator.paginate(Bucket=bucket, Prefix="backups/"):
        candidates.extend(page.get("Contents", []))
    if not candidates:
        raise RuntimeError("No backups found in R2.")
    return max(candidates, key=lambda item: item["LastModified"])["Key"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Encrypted R2 backup and restore for OneCre8.")
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("backup", help="Create, encrypt and upload a volume backup.")
    b.add_argument("volume", type=Path, help="Mounted data volume, e.g. /data")
    r = sub.add_parser("restore", help="Download, decrypt and restore into a new directory.")
    r.add_argument("destination", type=Path, help="New destination directory (must not exist).")
    r.add_argument("--object-key", help="Specific R2 object key; default restores latest.")
    sub.add_parser("generate-key", help="Print a new 32-byte hex encryption key.")
    args = parser.parse_args()
    if args.command == "backup":
        backup(args.volume)
    elif args.command == "restore":
        object_key = args.object_key or latest_object_key(_s3(), _env("R2_BUCKET"))
        restore(object_key, args.destination)
    else:
        print(secrets.token_hex(32))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
