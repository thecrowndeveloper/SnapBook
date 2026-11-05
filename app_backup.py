from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
from pathlib import Path

app = Flask(__name__)
app.secret_key = "change-this-secret-key"
DB = Path(__file__).with_name("snapbook.db")

def connect():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS photographers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, city TEXT NOT NULL, specialty TEXT NOT NULL,
            bio TEXT NOT NULL, price REAL NOT NULL, max_sessions INTEGER NOT NULL,
            image TEXT NOT NULL, available_days TEXT NOT NULL
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            photographer_id INTEGER NOT NULL, client_name TEXT NOT NULL,
            email TEXT NOT NULL, session_date TEXT NOT NULL, session_time TEXT NOT NULL,
            sessions INTEGER NOT NULL, notes TEXT DEFAULT '',
            status TEXT DEFAULT 'Pending',
            FOREIGN KEY(photographer_id) REFERENCES photographers(id)
        )""")
        count = con.execute("SELECT COUNT(*) FROM photographers").fetchone()[0]
        if count == 0:
            seed = [
                ("Amara Okafor", "Abuja", "Portraits & Graduation",
                 "Natural, confident portraits for graduates, creatives and everyday milestones.",
                 35000, 4, "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=900",
                 "Monday, Tuesday, Wednesday, Thursday, Friday, Saturday"),
                ("Daniel James", "Lagos", "Fashion & Model Portfolio",
                 "Editorial-inspired fashion sessions and model portfolio photography.",
                 55000, 3, "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=900",
                 "Tuesday, Wednesday, Thursday, Friday, Saturday"),
                ("Zara Bello", "Abuja", "Events & Lifestyle",
                 "Warm lifestyle imagery, intimate celebrations and personal branding sessions.",
                 45000, 5, "https://images.unsplash.com/photo-1531123897727-8f129e1688ce?w=900",
                 "Monday, Wednesday, Friday, Saturday, Sunday"),
                ("Tobi Akin", "Port Harcourt", "Product & Creative",
                 "Clean product photography and creative images for small businesses and artists.",
                 40000, 4, "https://images.unsplash.com/photo-1506794778202-cad84cf45f1d?w=900",
                 "Monday, Tuesday, Thursday, Saturday")
            ]
            con.executemany("""INSERT INTO photographers
                (name,city,specialty,bio,price,max_sessions,image,available_days)
                VALUES (?,?,?,?,?,?,?,?)""", seed)

@app.route("/")
def home():
    city = request.args.get("city", "").strip()
    specialty = request.args.get("specialty", "").strip()
    query = "SELECT * FROM photographers WHERE 1=1"
    args = []
    if city:
        query += " AND city LIKE ?"; args.append(f"%{city}%")
    if specialty:
        query += " AND specialty LIKE ?"; args.append(f"%{specialty}%")
    with connect() as con:
        photographers = con.execute(query + " ORDER BY id DESC", args).fetchall()
    return render_template("index.html", photographers=photographers, city=city, specialty=specialty)

@app.route("/photographer/<int:photographer_id>")
def photographer(photographer_id):
    with connect() as con:
        person = con.execute("SELECT * FROM photographers WHERE id=?", (photographer_id,)).fetchone()
        bookings = con.execute("""SELECT session_date, session_time FROM bookings
            WHERE photographer_id=? AND status != 'Cancelled'""", (photographer_id,)).fetchall()
    if not person:
        return "Photographer not found", 404
    booked = [f"{b['session_date']}T{b['session_time']}" for b in bookings]
    return render_template("photographer.html", person=person, booked=booked)

@app.route("/book/<int:photographer_id>", methods=["POST"])
def book(photographer_id):
    name = request.form.get("client_name", "").strip()
    email = request.form.get("email", "").strip()
    date = request.form.get("session_date", "")
    time = request.form.get("session_time", "")
    try:
        sessions = int(request.form.get("sessions", "1"))
    except ValueError:
        sessions = 0
    notes = request.form.get("notes", "").strip()
    with connect() as con:
        person = con.execute("SELECT * FROM photographers WHERE id=?", (photographer_id,)).fetchone()
        conflict = con.execute("""SELECT id FROM bookings WHERE photographer_id=?
            AND session_date=? AND session_time=? AND status != 'Cancelled'""",
            (photographer_id, date, time)).fetchone()
        if not person:
            flash("Photographer not found.", "error")
        elif not name or not email or not date or not time:
            flash("Please complete your name, email, date and time.", "error")
        elif sessions < 1 or sessions > person["max_sessions"]:
            flash(f"Choose between 1 and {person['max_sessions']} sessions.", "error")
        elif conflict:
            flash("That time has already been requested. Please choose another slot.", "error")
        else:
            con.execute("""INSERT INTO bookings
                (photographer_id,client_name,email,session_date,session_time,sessions,notes)
                VALUES (?,?,?,?,?,?,?)""",
                (photographer_id,name,email,date,time,sessions,notes))
            flash("Your booking request has been submitted. The photographer can confirm it with you.", "success")
            return redirect(url_for("photographer", photographer_id=photographer_id))
    return redirect(url_for("photographer", photographer_id=photographer_id))

@app.route("/dashboard")
def dashboard():
    with connect() as con:
        bookings = con.execute("""SELECT bookings.*, photographers.name AS photographer,
            photographers.price FROM bookings JOIN photographers
            ON bookings.photographer_id=photographers.id ORDER BY bookings.id DESC""").fetchall()
    return render_template("dashboard.html", bookings=bookings)

@app.route("/booking/<int:booking_id>/status", methods=["POST"])
def booking_status(booking_id):
    status = request.form.get("status")
    if status in ("Confirmed", "Cancelled", "Pending"):
        with connect() as con:
            con.execute("UPDATE bookings SET status=? WHERE id=?", (status, booking_id))
    return redirect(url_for("dashboard"))

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
