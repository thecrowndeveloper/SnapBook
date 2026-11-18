# OneCre8 Media backups and recovery

## Current production storage

The production Railway volume is mounted at `/data` (500 MB, SFO). It holds:
- `/data/snapbook.db` — SQLite marketplace data;
- `/data/portfolio/` — creative professional portfolio uploads;
- `/data/message-attachments/` — private booking-message images.

The app currently runs one production replica. Keep one replica while SQLite is the production database. A Railway volume is persistent storage, not an independent backup: it does not protect against accidental deletion, volume loss, corruption, or project loss.

## Full-volume backup (recommended)

The new `scripts/backup_volume.py` utility creates a ZIP archive containing the database and both media directories. It uses SQLite's online backup API, checks database integrity, tests the ZIP archive, refuses to overwrite an existing archive, and refuses a destination inside the source volume.

**Pause application writes before starting this full-volume archive.** The database copy is transactionally consistent, but the portfolio and message files are copied individually; pausing writes prevents a file being added, removed, or changed during the archive. Do not run this by copying files directly from a live volume without a maintenance window.

On the Railway host, run:

```bash
python scripts/backup_volume.py /data /protected-external-storage/onecre8-YYYYMMDD-HHMMSS.zip
```

The destination path above is a placeholder. It must be on storage independent of the Railway volume. The script does not upload or encrypt the archive. After verification, encrypt it before transfer/storage, restrict access to named operators, and protect it in transit and at rest. The archive contains private user messages and portfolio images; treat it as confidential personal data. Never commit archives or credentials to Git.

The older `scripts/backup_sqlite.py` remains available for database-only snapshots. It does not include uploaded media.

## Restore procedure

1. Use a maintenance window and stop application writes.
2. Preserve the current database, WAL/SHM files, and media directories as an incident snapshot.
3. Decrypt the chosen archive into a separate temporary directory.
4. Test the ZIP with `python -m zipfile -t BACKUP.zip` and run `PRAGMA integrity_check` against the extracted database.
5. Restore the database and both media directories to the correct volume paths while the app is stopped. Preserve restrictive permissions on private message attachments.
6. Restart one replica and verify login, homepage, booking, listing, portfolio display, and participant-only message attachment access.
7. Keep the pre-restore snapshot until all checks pass.

Never test restoration over the only production copy. First restore to a separate test database or isolated environment. Do not expose private message attachments through public static paths.

## What is still needed for production-grade disaster recovery

- No independent off-site storage provider is configured.
- No scheduled backup, retention policy, or failure alert is active.
- No automated encryption/key-management workflow is configured.
- No restore drill has been recorded.
- The 500 MB volume capacity must be monitored as uploaded media grows.

Before automating, choose a separate private storage provider, retention period, encryption/key-access policy, backup schedule, and alert recipient. Do not add paid infrastructure or credentials without approval. Do not claim the backup process is operational until a real archive has been stored independently and a restore drill has passed.
