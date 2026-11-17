# OneCre8 Media — Windows development setup

This guide is for continuing the existing OneCre8 Media project on a new Windows 10 or Windows 11 computer. It does not create a new project or replace the live production database.

## What you need

Install:
1. Git for Windows: https://git-scm.com/download/win
2. Python 3.12 or a compatible version supported by the project: https://www.python.org/downloads/windows/
   - During installation, enable **Add Python to PATH**.
3. Visual Studio Code: https://code.visualstudio.com/

## Get the existing project

Open PowerShell and run:

```powershell
git clone https://github.com/thecrowndeveloper/SnapBook.git
cd SnapBook
```

## Create the Python environment

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell blocks activation, use this for the current terminal window only:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## Open the project

```powershell
code .
```

## Important: protect production data and secrets

- The GitHub repository contains the application source code and committed static assets.
- Railway hosts the live application. Its production volume is mounted at `/data`; it is separate from this Windows computer and is not downloaded by `git clone`.
- Do not delete, recreate, or overwrite the Railway volume when setting up a new computer.
- Do not commit `.env`, database files, uploaded customer media, API credentials, OAuth secrets, or the production `SECRET_KEY`.
- Keep credentials in a password manager and use Railway's Variables page for production values.
- A local development database is separate from production. Never point local experiments at the live database.

## Continue working

```powershell
git pull origin main
```

Create a feature branch before making changes:

```powershell
git switch -c feature/your-change
```

When the change is ready, push the branch and open a pull request on GitHub. Production should continue deploying from `main` through Railway.

## If Python or Git is not recognized

Close and reopen PowerShell after installation, then check:

```powershell
git --version
py --version
```
