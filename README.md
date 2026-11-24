# OneCre8 Media

OneCre8 Media is a Nigerian creative-services marketplace built with Flask, SQLite and server-rendered templates. It supports client and creative-professional accounts, public portfolios, service discovery, booking requests, private booking conversations, notifications and verified reviews. The interface's existing black, gold, cream and white design is intentional and should be preserved during maintenance.

## Local development

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export SECRET_KEY="use-a-long-random-local-development-secret"
python app.py
```

### Windows PowerShell

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
$env:SECRET_KEY = "use-a-long-random-local-development-secret"
python app.py
```

Open http://127.0.0.1:5000. Never reuse the production SECRET_KEY on a development machine. Production must provide SECRET_KEY and a persistent volume mounted at `/data`; the application intentionally refuses to start in Railway production without its secret.

## Tests

```bash
python -m unittest discover -s tests -v
```

Run this after installing `requirements.txt`. Tests use isolated temporary storage and must not be pointed at the production database.

## Data and uploads

Production SQLite data is stored on the Railway volume mounted at `/data`. Portfolio images and private message attachments are stored on that same persistent volume. They are not included in GitHub. Do not delete, replace or detach the production volume during deployment or transfer.

## Backups and restore

- `scripts/backup_sqlite.py` creates a consistent, integrity-checked SQLite database backup.
- `scripts/backup_volume.py` creates a ZIP containing the database and supported portfolio/message attachment media. Pause application writes while creating this full-volume archive.
- `scripts/restore_volume.py` restores a ZIP into a **new destination directory only**, refuses to overwrite existing data, rejects unsafe archive paths and verifies SQLite integrity.

See [docs/PRETRANSFER-OPERATIONS.md](docs/PRETRANSFER-OPERATIONS.md) for the operational procedure. Keep encrypted offsite copies under access control; the scripts do not upload or encrypt backups.

## Production notes

- Railway is the current production host; preserve the existing production service, domain, environment variables and mounted volume.
- Paystack is sandbox-only. Do not enable live payment credentials without a separate approved launch review.
- The current SQLite deployment is configured for one Gunicorn worker. Do not scale to multiple application replicas without first migrating to a shared production database such as PostgreSQL and validating media storage.
- GitHub is the source of code, not the live database or uploaded user media.
