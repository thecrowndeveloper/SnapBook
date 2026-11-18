# OneCre8 Media SQLite backups and recovery

## Current production database

The Flask application uses SQLite at `/data/snapbook.db` when the Railway
volume is mounted at `/data`. Keep a single application replica while this
SQLite database remains the production store.

A Railway persistent volume is not an independent backup. It does not by
itself protect against accidental deletion, volume failure, corruption, or
loss of the project.

## Create a consistent backup

Use the SQLite online backup API rather than copying the live database file
with a normal file-copy command. This matters because the database uses WAL
mode and recent committed changes may still be in the WAL file.

Run:

```bash
python scripts/backup_sqlite.py /data/snapbook.db /secure-offsite-location/snapbook-YYYYMMDD-HHMMSS.db
```

The destination must be a new file. The script:
- opens the source read-only;
- creates a transactionally consistent SQLite backup;
- runs `PRAGMA integrity_check` on the result;
- removes an incomplete backup if an error occurs;
- refuses to overwrite an existing backup.

**Important:** the example destination is a placeholder. Do not save the only
backup beside the live database on the same Railway volume. Copy verified
backups to a separate protected storage service, restrict access, and encrypt
them at rest and in transit. The script does not yet upload to cloud storage.

## Restore procedure

1. Put the application into maintenance mode or stop writes.
2. Preserve the current database and its WAL/SHM files as an incident snapshot.
3. Verify the backup with `sqlite3 BACKUP_FILE "PRAGMA integrity_check;"`.
4. Restore the verified backup as `/data/snapbook.db` while the app is stopped.
5. Confirm file ownership/permissions, restart one replica, and check login,
   homepage, booking, listing, and portfolio flows.
6. Keep the pre-restore copy until the restored service has been verified.

Never test restoration against the only production database. First restore to
a separate test database and verify application reads and key workflows.

## Operational gaps before calling backups production-ready

- No off-site storage provider or credentials are currently configured.
- No scheduled backup job or retention policy is active.
- No alerting for missed or failed backups is configured.
- A restore drill against a separate database has not yet been recorded.

Before automating, choose a separate private object-storage destination,
retention period, encryption/access policy, and alert recipient. Then wire the
job to those approved settings. Do not place storage credentials in source
control or application logs.
