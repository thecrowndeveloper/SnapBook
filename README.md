# SnapBook — Photography Booking MVP

A small Flask + SQLite photography discovery and booking marketplace. The interface uses Manrope for headings and Inter for body text and controls.

## Run locally
1. Install Python 3.10+.
2. Open a terminal in this folder.
3. Create and activate a virtual environment:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

4. Install dependencies and start the app:

   ```bash
   pip install -r requirements.txt
   python app.py
   ```

5. Open http://127.0.0.1:5000

The database and four sample photographer profiles are created automatically on first run.

## Included
- Photographer directory with city and specialty filters
- Profile pages with pricing, working days and maximum sessions per request
- Booking request form with estimated total
- Duplicate date/time request prevention
- Booking dashboard with Pending / Confirmed / Cancelled status

## Important MVP limitations
This is a local demonstration, not a production marketplace. It does not yet include accounts, verified photographer ownership, email/SMS notifications, payment processing, recurring availability calendars, deployment, or production security configuration. Booking requests are not confirmed until the photographer follows up. Sample profiles and availability are demo data. Add authentication and authorization before exposing the dashboard publicly.
