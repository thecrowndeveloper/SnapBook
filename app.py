
import os
import sqlite3
from pathlib import Path
from datetime import datetime

from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, abort
)
from flask_login import (
    LoginManager, UserMixin, current_user,
    login_user, logout_user, login_required
)
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get(
    "SECRET_KEY",
    "local-development-secret-change-before-deployment"
)

csrf = CSRFProtect(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in to access that page."

DB = Path(__file__).with_name("snapbook.db")

DEFAULT_IMAGE = (
    "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=900"
)


def connect():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


class User(UserMixin):
    def __init__(self, row):
        self.id = row["id"]
        self.name = row["name"]
        self.email = row["email"]
        self.role = row["role"]
        self.password_hash = row["password_hash"]

    def get_id(self):
        return str(self.id)


@login_manager.user_loader
def load_user(user_id):
    with connect() as con:
        row = con.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()

    return User(row) if row else None


def add_column_if_missing(con, table, column, definition):
    columns = [
        row["name"]
        for row in con.execute(f"PRAGMA table_info({table})").fetchall()
    ]
    if column not in columns:
        con.execute(
            f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
        )


def init_db():
    with connect() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS photographers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                city TEXT NOT NULL,
                specialty TEXT NOT NULL,
                bio TEXT NOT NULL,
                price REAL NOT NULL,
                max_sessions INTEGER NOT NULL,
                image TEXT NOT NULL,
                available_days TEXT NOT NULL
            )
        """)

        con.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                photographer_id INTEGER NOT NULL,
                client_name TEXT NOT NULL,
                email TEXT NOT NULL,
                session_date TEXT NOT NULL,
                session_time TEXT NOT NULL,
                sessions INTEGER NOT NULL,
                notes TEXT DEFAULT '',
                status TEXT DEFAULT 'Pending',
                FOREIGN KEY(photographer_id) REFERENCES photographers(id)
            )
        """)

        con.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('client', 'photographer')),
                created_at TEXT NOT NULL
            )
        """)

        # Add account ownership to existing records without deleting them.
        add_column_if_missing(
            con, "photographers", "user_id",
            "INTEGER REFERENCES users(id)"
        )
        add_column_if_missing(
            con, "bookings", "client_user_id",
            "INTEGER REFERENCES users(id)"
        )

        con.execute("""
            CREATE INDEX IF NOT EXISTS idx_photographers_user
            ON photographers(user_id)
        """)
        con.execute("""
            CREATE INDEX IF NOT EXISTS idx_bookings_client
            ON bookings(client_user_id)
        """)

        count = con.execute(
            "SELECT COUNT(*) FROM photographers"
        ).fetchone()[0]

        if count == 0:
            seed = [
                (
                    "Amara Okafor", "Abuja", "Portraits & Graduation",
                    "Natural, confident portraits for graduates, creatives and everyday milestones.",
                    35000, 4,
                    "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=900",
                    "Monday, Tuesday, Wednesday, Thursday, Friday, Saturday"
                ),
                (
                    "Daniel James", "Lagos", "Fashion & Model Portfolio",
                    "Editorial-inspired fashion sessions and model portfolio photography.",
                    55000, 3,
                    "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=900",
                    "Tuesday, Wednesday, Thursday, Friday, Saturday"
                ),
                (
                    "Zara Bello", "Abuja", "Events & Lifestyle",
                    "Warm lifestyle imagery, intimate celebrations and personal branding sessions.",
                    45000, 5,
                    "https://images.unsplash.com/photo-1531123897727-8f129e1688ce?w=900",
                    "Monday, Wednesday, Friday, Saturday, Sunday"
                ),
                (
                    "Tobi Akin", "Port Harcourt", "Product & Creative",
                    "Clean product photography and creative images for small businesses and artists.",
                    40000, 4,
                    "https://images.unsplash.com/photo-1506794778202-cad84cf45f1d?w=900",
                    "Monday, Tuesday, Thursday, Saturday"
                )
            ]

            con.executemany("""
                INSERT INTO photographers
                (name, city, specialty, bio, price, max_sessions,
                 image, available_days)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, seed)


def role_required(role):
    if not current_user.is_authenticated:
        return redirect(url_for("login"))
    if current_user.role != role:
        abort(403)


@app.route("/")
def home():
    city = request.args.get("city", "").strip()
    specialty = request.args.get("specialty", "").strip()

    query = "SELECT * FROM photographers WHERE 1=1"
    args = []

    if city:
        query += " AND city LIKE ?"
        args.append(f"%{city}%")

    if specialty:
        query += " AND specialty LIKE ?"
        args.append(f"%{specialty}%")

    with connect() as con:
        photographers = con.execute(
            query + " ORDER BY id DESC", args
        ).fetchall()

    return render_template(
        "index.html",
        photographers=photographers,
        city=city,
        specialty=specialty
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("home"))

    role = request.args.get("role", "client")
    if role not in ("client", "photographer"):
        role = "client"

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "client")

        if role not in ("client", "photographer"):
            flash("Please choose a valid account type.", "error")
            return render_template("register.html", role="client")

        if not name or not email or not password:
            flash("Please complete all required fields.", "error")
            return render_template("register.html", role=role)

        if len(password) < 8:
            flash("Your password must contain at least 8 characters.", "error")
            return render_template("register.html", role=role)

        photographer_data = None

        if role == "photographer":
            city = request.form.get("city", "").strip()
            specialty = request.form.get("specialty", "").strip()
            bio = request.form.get("bio", "").strip()

            try:
                price = float(request.form.get("price", "0"))
                max_sessions = int(request.form.get("max_sessions", "1"))
            except ValueError:
                price = 0
                max_sessions = 0

            if not city or not specialty or not bio:
                flash("Please complete your photographer profile.", "error")
                return render_template("register.html", role=role)

            if price <= 0 or max_sessions < 1:
                flash("Enter a valid price and session limit.", "error")
                return render_template("register.html", role=role)

            photographer_data = (
                name, city, specialty, bio, price, max_sessions,
                DEFAULT_IMAGE,
                "Monday, Tuesday, Wednesday, Thursday, Friday, Saturday"
            )

        try:
            with connect() as con:
                cursor = con.execute("""
                    INSERT INTO users
                    (name, email, password_hash, role, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    name,
                    email,
                    generate_password_hash(password),
                    role,
                    datetime.utcnow().isoformat()
                ))

                user_id = cursor.lastrowid

                if photographer_data:
                    con.execute("""
                        INSERT INTO photographers
                        (name, city, specialty, bio, price, max_sessions,
                         image, available_days, user_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (*photographer_data, user_id))

                user_row = con.execute(
                    "SELECT * FROM users WHERE id = ?", (user_id,)
                ).fetchone()

            login_user(User(user_row))
            flash("Your account has been created.", "success")

            if role == "photographer":
                return redirect(url_for("dashboard"))
            return redirect(url_for("my_bookings"))

        except sqlite3.IntegrityError:
            flash("An account with that email already exists.", "error")

    return render_template("register.html", role=role)


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("home"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        with connect() as con:
            row = con.execute(
                "SELECT * FROM users WHERE email = ?", (email,)
            ).fetchone()

        if row and check_password_hash(row["password_hash"], password):
            login_user(User(row))
            flash("Welcome back.", "success")

            next_page = request.args.get("next", "")
            if next_page.startswith("/") and not next_page.startswith("//"):
                return redirect(next_page)

            if row["role"] == "photographer":
                return redirect(url_for("dashboard"))
            return redirect(url_for("my_bookings"))

        flash("Email or password is incorrect.", "error")

    return render_template("login.html")


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("home"))


@app.route("/photographer/<int:photographer_id>")
def photographer(photographer_id):
    with connect() as con:
        person = con.execute(
            "SELECT * FROM photographers WHERE id = ?",
            (photographer_id,)
        ).fetchone()

        bookings = con.execute("""
            SELECT session_date, session_time
            FROM bookings
            WHERE photographer_id = ? AND status != 'Cancelled'
        """, (photographer_id,)).fetchall()

    if not person:
        abort(404)

    booked = [
        f"{b['session_date']}T{b['session_time']}"
        for b in bookings
    ]

    return render_template(
        "photographer.html",
        person=person,
        booked=booked
    )


@app.route("/book/<int:photographer_id>", methods=["POST"])
def book(photographer_id):
    name = request.form.get("client_name", "").strip()
    email = request.form.get("email", "").strip().lower()
    date = request.form.get("session_date", "")
    time = request.form.get("session_time", "")

    try:
        sessions = int(request.form.get("sessions", "1"))
    except ValueError:
        sessions = 0

    notes = request.form.get("notes", "").strip()

    with connect() as con:
        person = con.execute(
            "SELECT * FROM photographers WHERE id = ?",
            (photographer_id,)
        ).fetchone()

        conflict = con.execute("""
            SELECT id FROM bookings
            WHERE photographer_id = ?
              AND session_date = ?
              AND session_time = ?
              AND status != 'Cancelled'
        """, (photographer_id, date, time)).fetchone()

        if not person:
            flash("Photographer not found.", "error")
        elif not name or not email or not date or not time:
            flash("Please complete your name, email, date and time.", "error")
        elif sessions < 1 or sessions > person["max_sessions"]:
            flash(
                f"Choose between 1 and {person['max_sessions']} sessions.",
                "error"
            )
        elif conflict:
            flash(
                "That time has already been requested. Please choose another slot.",
                "error"
            )
        else:
            client_user_id = (
                current_user.id
                if current_user.is_authenticated
                and current_user.role == "client"
                else None
            )

            con.execute("""
                INSERT INTO bookings
                (photographer_id, client_name, email, session_date,
                 session_time, sessions, notes, client_user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                photographer_id, name, email, date,
                time, sessions, notes, client_user_id
            ))

            flash(
                "Your booking request has been submitted. "
                "The photographer can confirm it with you.",
                "success"
            )

    if current_user.is_authenticated and current_user.role == "client":
        return redirect(url_for("my_bookings"))

    return redirect(url_for(
        "photographer", photographer_id=photographer_id
    ))


@app.route("/my-bookings")
@login_required
def my_bookings():
    role_required("client")

    with connect() as con:
        bookings = con.execute("""
            SELECT bookings.*, photographers.name AS photographer,
                   photographers.price
            FROM bookings
            JOIN photographers
              ON bookings.photographer_id = photographers.id
            WHERE bookings.client_user_id = ?
            ORDER BY bookings.id DESC
        """, (current_user.id,)).fetchall()

    return render_template("client_dashboard.html", bookings=bookings)


@app.route("/dashboard")
@login_required
def dashboard():
    role_required("photographer")

    with connect() as con:
        bookings = con.execute("""
            SELECT bookings.*, photographers.name AS photographer,
                   photographers.price
            FROM bookings
            JOIN photographers
              ON bookings.photographer_id = photographers.id
            WHERE photographers.user_id = ?
            ORDER BY bookings.id DESC
        """, (current_user.id,)).fetchall()

    return render_template("dashboard.html", bookings=bookings)


@app.route("/booking/<int:booking_id>/status", methods=["POST"])
@login_required
def booking_status(booking_id):
    role_required("photographer")

    status = request.form.get("status")

    if status not in ("Confirmed", "Cancelled", "Pending"):
        abort(400)

    with connect() as con:
        result = con.execute("""
            UPDATE bookings
            SET status = ?
            WHERE id = ?
              AND photographer_id IN (
                  SELECT id FROM photographers WHERE user_id = ?
              )
        """, (status, booking_id, current_user.id))

        if result.rowcount == 0:
            abort(404)

    flash("Booking status updated.", "success")
    return redirect(url_for("dashboard"))


# Create tables and safely add missing columns when the app starts.
init_db()


if __name__ == "__main__":
    app.run(debug=True)
