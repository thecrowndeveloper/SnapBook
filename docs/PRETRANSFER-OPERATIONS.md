# OneCre8 Media — pre-transfer operations runbook

## Current production data boundaries

The Railway production service mounts its persistent volume at `/data`. The SQLite database is `/data/snapbook.db`; portfolio media and private message attachments are stored under the volume. GitHub contains application code, not the production database or user-uploaded files.

Never delete, recreate, detach or replace the production volume as part of a code deployment or Windows transfer. Keep the existing Railway service, domain, variables and volume.

## Full backup procedure

A full backup includes the database and the supported media folders (`portfolio/` and `message-attachments/`). It does not include arbitrary files elsewhere on the volume.

1. Schedule a maintenance window and pause new bookings, messages, uploads and other writes. Do not stop the service or modify its volume until the backup method is agreed.
2. Choose a destination outside `/data` on encrypted, access-controlled storage with sufficient free space.
3. Run from a trusted environment with access to the mounted volume:

   ```bash
   python scripts/backup_volume.py /data /secure-offsite/onecre8-YYYYMMDD-HHMMSS.zip
   ```

4. Confirm the script reports a verified archive. Preserve the file's permissions and record its SHA-256 checksum.
5. Transfer the archive to the approved encrypted offsite location. Keep access limited because it contains personal data and private message attachments.
6. Resume application writes and verify the service.

The backup utility does not upload or encrypt the archive. Do not store the only backup on the same Railway volume.

## Restore test

Perform a restore drill on a separate local machine or isolated staging volume. Never test by restoring over production.

```bash
python scripts/restore_volume.py /secure-offsite/onecre8-YYYYMMDD-HHMMSS.zip ./onecre8-restore-drill
```

The destination must not already exist. The script rejects path traversal, unexpected archive members and symbolic links; it refuses to overwrite existing directories and runs SQLite `PRAGMA integrity_check`. Then verify expected media counts and sample files against the backup manifest/checksum records. Keep the restored drill isolated and delete it securely after the test is signed off.

## Windows handover

1. Clone the GitHub repository on Windows; do not copy the live SQLite database from a running service as a substitute for a consistent backup.
2. Install Python 3.10+ and create a virtual environment using the PowerShell instructions in the root README.
3. Install dependencies and run `python -m unittest discover -s tests -v`.
4. Use a separate local development database and a new local SECRET_KEY. Never put production secrets in Git, screenshots, or local example files.
5. If production data is needed for a test, use an approved, access-controlled restore copy and protect personal data. Do not point local development at the production volume.
6. Continue branch → pull request → checks → merge → Railway deployment. Do not commit directly to main.
7. Do not enable Paystack live mode or scale the SQLite service to multiple replicas as part of the transfer.

## Sign-off checklist

- [ ] Full-volume backup created outside Railway and encrypted at rest
- [ ] SHA-256 checksum recorded and backup stored offsite
- [ ] Restore drill completed on an isolated destination
- [ ] SQLite integrity and sample media verified after restore
- [ ] Windows dependencies installed and test suite passes
- [ ] Production volume, secrets, domain and service configuration preserved
- [ ] Production client and creative-professional journeys tested after deployment
- [ ] Live payments remain disabled pending separate approval

## Encrypted Cloudflare R2 offsite backup

The R2 bucket must remain private. Use a bucket-scoped R2 API token with Object Read & Write for `onecre8-production-backups` only. Never commit credentials or encryption keys.

Install updated requirements in a trusted machine/virtual environment. Set these environment variables (do not store them in Git):

- `R2_ENDPOINT_URL`: `https://<account-id>.r2.cloudflarestorage.com`
- `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`: bucket-restricted R2 credentials
- `R2_BUCKET`: `onecre8-production-backups`
- `ONECRE8_BACKUP_ENCRYPTION_KEY`: independent 32-byte AES key, 64 hexadecimal characters

Generate an encryption key using `python scripts/r2_backup_restore.py generate-key`. Store it in an offline password manager or other secure location separate from the R2 credentials and bucket. Losing this key makes backups unrecoverable; do not rotate it without retaining the old key for existing archives.

Back up only from a trusted host with access to the volume. Pause writes before full-volume archive creation:

```bash
python scripts/r2_backup_restore.py backup /data
```
The utility streams AES-256-GCM encryption, uploads to R2, and checks object size and metadata. It prints the object key and plaintext archive SHA-256. Verify the upload in the R2 dashboard. Do not upload an archive without encryption.

Restore the latest object to a brand-new isolated directory (never production):

```bash
python scripts/r2_backup_restore.py restore ./onecre8-restore-drill
```
Specify `--object-key backups/<exact-object-name>` to select an archive. Restore downloads, authenticates/decrypts, checks the archive hash, and calls the safe restore utility which verifies ZIP and SQLite integrity.

R2 credentials and encryption key are not required in Railway; do not add them to the production service unless a separately reviewed automated backup design explicitly needs them. Current procedure is manual from a trusted machine with volume access.
