
import os
import sqlite3
from pathlib import Path
from datetime import datetime

from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, abort, send_from_directory
)
from flask_login import (
    LoginManager, UserMixin, current_user,
    login_user, logout_user, login_required
)
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from uuid import uuid4
from mutagen.mp4 import MP4


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

volume_path = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")

if volume_path:
    DB = Path(volume_path) / "snapbook.db"
else:
    DB = Path(__file__).with_name("snapbook.db")

DB.parent.mkdir(parents=True, exist_ok=True)

# Persistent storage for provider portfolio uploads
PORTFOLIO_UPLOAD_FOLDER = (
    Path(volume_path) / "portfolio"
    if volume_path
    else Path(__file__).with_name("portfolio_uploads")
)
PORTFOLIO_UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

app.config["PORTFOLIO_UPLOAD_FOLDER"] = str(PORTFOLIO_UPLOAD_FOLDER)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024

DEFAULT_IMAGE = (
    "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=900"
)

# Nigerian state capitals and the Federal Capital Territory.
# The search field also accepts other cities and towns.
NIGERIAN_LOCATIONS = [
    ("Abia", "Umuahia"),
    ("Adamawa", "Yola"),
    ("Akwa Ibom", "Uyo"),
    ("Anambra", "Awka"),
    ("Bauchi", "Bauchi"),
    ("Bayelsa", "Yenagoa"),
    ("Benue", "Makurdi"),
    ("Borno", "Maiduguri"),
    ("Cross River", "Calabar"),
    ("Delta", "Asaba"),
    ("Ebonyi", "Abakaliki"),
    ("Edo", "Benin City"),
    ("Ekiti", "Ado-Ekiti"),
    ("Enugu", "Enugu"),
    ("Gombe", "Gombe"),
    ("Imo", "Owerri"),
    ("Jigawa", "Dutse"),
    ("Kaduna", "Kaduna"),
    ("Kano", "Kano"),
    ("Katsina", "Katsina"),
    ("Kebbi", "Birnin Kebbi"),
    ("Kogi", "Lokoja"),
    ("Kwara", "Ilorin"),
    ("Lagos", "Ikeja"),
    ("Nasarawa", "Lafia"),
    ("Niger", "Minna"),
    ("Ogun", "Abeokuta"),
    ("Ondo", "Akure"),
    ("Osun", "Osogbo"),
    ("Oyo", "Ibadan"),
    ("Plateau", "Jos"),
    ("Rivers", "Port Harcourt"),
    ("Sokoto", "Sokoto"),
    ("Taraba", "Jalingo"),
    ("Yobe", "Damaturu"),
    ("Zamfara", "Gusau"),
    ("FCT", "Abuja"),
]


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


def migrate_user_roles(con):
    """Allow provider accounts while preserving existing user records."""

    table_sql = con.execute("""
        SELECT sql
        FROM sqlite_master
        WHERE type = 'table' AND name = 'users'
    """).fetchone()["sql"]

    if "'provider'" in table_sql:
        return

    con.execute("PRAGMA foreign_keys = OFF")

    try:
        con.execute("BEGIN")

        con.execute("""
            CREATE TABLE users_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL
                    CHECK(role IN ('client', 'photographer', 'provider')),
                created_at TEXT NOT NULL
            )
        """)

        con.execute("""
            INSERT INTO users_new
                (id, name, email, password_hash, role, created_at)
            SELECT
                id, name, email, password_hash, role, created_at
            FROM users
        """)

        con.execute("DROP TABLE users")
        con.execute("ALTER TABLE users_new RENAME TO users")

        con.commit()

    except Exception:
        con.rollback()
        raise

    finally:
        con.execute("PRAGMA foreign_keys = ON")



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

        migrate_user_roles(con)

        # Marketplace categories
        con.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                slug TEXT NOT NULL UNIQUE,
                description TEXT DEFAULT ''
            )
        """)

        # Creative professionals and businesses
        con.execute("""
            CREATE TABLE IF NOT EXISTS providers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE,
                display_name TEXT NOT NULL,
                business_name TEXT DEFAULT '',
                bio TEXT DEFAULT '',
                city TEXT DEFAULT '',
                profile_image TEXT DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """)

        # Categories offered by each provider
        con.execute("""
            CREATE TABLE IF NOT EXISTS provider_categories (
                provider_id INTEGER NOT NULL,
                category_id INTEGER NOT NULL,
                PRIMARY KEY(provider_id, category_id),
                FOREIGN KEY(provider_id) REFERENCES providers(id)
                    ON DELETE CASCADE,
                FOREIGN KEY(category_id) REFERENCES categories(id)
                    ON DELETE CASCADE
            )
        """)

        # Services offered by providers
        con.execute("""
            CREATE TABLE IF NOT EXISTS services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_id INTEGER NOT NULL,
                category_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                pricing_mode TEXT NOT NULL
                    CHECK(pricing_mode IN ('fixed', 'quote')),
                booking_mode TEXT NOT NULL
                    CHECK(booking_mode IN ('booking', 'enquiry')),
                price REAL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(provider_id) REFERENCES providers(id),
                FOREIGN KEY(category_id) REFERENCES categories(id)
            )
        """)

        # Marketplace service bookings and enquiries.
        # Payment and review fields will be added only after gateway verification
        # and a confirmed completion workflow are implemented.
        con.execute("""
            CREATE TABLE IF NOT EXISTS marketplace_bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_id INTEGER NOT NULL,
                provider_id INTEGER NOT NULL,
                client_user_id INTEGER NOT NULL,
                requested_date TEXT NOT NULL,
                client_message TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Requested'
                    CHECK(status IN (
                        'Requested', 'Accepted', 'In Progress',
                        'Awaiting Client Confirmation', 'Completed',
                        'Cancelled'
                    )),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(service_id) REFERENCES services(id),
                FOREIGN KEY(provider_id) REFERENCES providers(id),
                FOREIGN KEY(client_user_id) REFERENCES users(id)
            )
        """)

        con.execute("""
            CREATE INDEX IF NOT EXISTS idx_marketplace_bookings_client
            ON marketplace_bookings(client_user_id)
        """)
        con.execute("""
            CREATE INDEX IF NOT EXISTS idx_marketplace_bookings_provider
            ON marketplace_bookings(provider_id)
        """)

        # Artwork for sale and costumes for rent
        con.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_id INTEGER NOT NULL,
                category_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                listing_type TEXT NOT NULL
                    CHECK(listing_type IN ('sale', 'rental')),
                price REAL NOT NULL,
                quantity_available INTEGER NOT NULL DEFAULT 1,
                image TEXT DEFAULT '',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(provider_id) REFERENCES providers(id),
                FOREIGN KEY(category_id) REFERENCES categories(id)
            )
        """)


                # Provider portfolio: images and videos of previous work
        con.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_id INTEGER NOT NULL,
                media_type TEXT NOT NULL
                    CHECK(media_type IN ('image', 'video')),
                filename TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(provider_id) REFERENCES providers(id)
                    ON DELETE CASCADE
            )
        """)

        con.execute("""
            CREATE INDEX IF NOT EXISTS idx_portfolio_provider
            ON portfolio_items(provider_id)
        """)

        # Notifications for photographers and marketplace providers
        con.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                notification_type TEXT NOT NULL,
                related_id INTEGER,
                is_read INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
                    ON DELETE CASCADE
            )
        """)

        # Add the initial marketplace categories
        categories = [
            ("Photography", "photography"),
            ("Videography", "videography"),
            ("Artwork", "artwork"),
            ("Photo Framing", "photo-framing"),
            ("Interior Design", "interior-design"),
            ("Costume Rentals", "costume-rentals"),
            ("Media Equipment", "media-equipment"),
            ("Spaces & Studios", "spaces-studios")
        ]

        con.executemany("""
            INSERT OR IGNORE INTO categories (name, slug)
            VALUES (?, ?)
        """, categories)


        # Add account ownership to existing records without deleting them.
        add_column_if_missing(
            con, "photographers", "user_id",
            "INTEGER REFERENCES users(id)"
        )
        add_column_if_missing(
            con, "bookings", "client_user_id",
            "INTEGER REFERENCES users(id)"
        )

        add_column_if_missing(
            con, "bookings", "viewed_at",
            "TEXT"
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
    category_slug = request.args.get("category", "").strip()

    photographer_query = "SELECT * FROM photographers WHERE 1=1"
    photographer_args = []

    if city:
        photographer_query += " AND city LIKE ?"
        photographer_args.append(f"%{city}%")

    if specialty:
        photographer_query += " AND specialty LIKE ?"
        photographer_args.append(f"%{specialty}%")

    provider_query = """
        SELECT DISTINCT providers.*, GROUP_CONCAT(categories.name, ', ')
            AS category_names
        FROM providers
        JOIN provider_categories
            ON provider_categories.provider_id = providers.id
        JOIN categories
            ON categories.id = provider_categories.category_id
        WHERE 1=1
    """
    provider_args = []

    if city:
        provider_query += " AND providers.city LIKE ?"
        provider_args.append(f"%{city}%")

    if category_slug:
        provider_query += " AND categories.slug = ?"
        provider_args.append(category_slug)

    provider_query += " GROUP BY providers.id ORDER BY providers.id DESC"

    with connect() as con:
        photographers = con.execute(
            photographer_query + " ORDER BY id DESC", photographer_args
        ).fetchall()
        creative_professionals = con.execute(
            provider_query, provider_args
        ).fetchall()
        categories = con.execute(
            "SELECT id, name, slug FROM categories ORDER BY name"
        ).fetchall()

    return render_template(
        "index.html",
        photographers=photographers,
        creative_professionals=creative_professionals,
        categories=categories,
        locations=NIGERIAN_LOCATIONS,
        city=city,
        specialty=specialty,
        category_slug=category_slug
    )



@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("home"))

    with connect() as con:
        categories = con.execute(
            "SELECT id, name FROM categories ORDER BY id"
        ).fetchall()

    role = request.args.get("role", "client")
    if role not in ("client", "provider", "photographer"):
        role = "client"

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "client")

        if role not in ("client", "provider", "photographer"):
            flash("Please choose a valid account type.", "error")
            return render_template(
                "register.html", role="client", categories=categories
            )

        if not name or not email or not password:
            flash("Please complete all required fields.", "error")
            return render_template(
                "register.html", role=role, categories=categories
            )

        if len(password) < 8:
            flash("Your password must contain at least 8 characters.", "error")
            return render_template(
                "register.html", role=role, categories=categories
            )

        provider_data = None
        selected_category_ids = []

        if role == "provider":
            city = request.form.get("city", "").strip()
            bio = request.form.get("bio", "").strip()
            business_name = request.form.get("business_name", "").strip()

            try:
                selected_category_ids = list({
                    int(value)
                    for value in request.form.getlist("category_ids")
                })
            except ValueError:
                flash("Please choose valid service categories.", "error")
                return render_template(
                    "register.html", role=role, categories=categories
                )

            valid_ids = {category["id"] for category in categories}

            if not city or not bio:
                flash("Please complete your provider profile.", "error")
                return render_template(
                    "register.html", role=role, categories=categories
                )

            if not selected_category_ids:
                flash("Please select at least one category.", "error")
                return render_template(
                    "register.html", role=role, categories=categories
                )

            if not set(selected_category_ids).issubset(valid_ids):
                flash("One or more selected categories are invalid.", "error")
                return render_template(
                    "register.html", role=role, categories=categories
                )

            provider_data = (name, business_name, bio, city)

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
                return render_template(
                    "register.html", role=role, categories=categories
                )

            if price <= 0 or max_sessions < 1:
                flash("Enter a valid price and session limit.", "error")
                return render_template(
                    "register.html", role=role, categories=categories
                )

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

                if provider_data:
                    provider_cursor = con.execute("""
                        INSERT INTO providers
                        (user_id, display_name, business_name, bio, city)
                        VALUES (?, ?, ?, ?, ?)
                    """, (user_id, *provider_data))

                    provider_id = provider_cursor.lastrowid

                    con.executemany("""
                        INSERT INTO provider_categories
                        (provider_id, category_id)
                        VALUES (?, ?)
                    """, [
                        (provider_id, category_id)
                        for category_id in selected_category_ids
                    ])

                user_row = con.execute(
                    "SELECT * FROM users WHERE id = ?", (user_id,)
                ).fetchone()

            login_user(User(user_row))
            flash("Your account has been created.", "success")

            if role == "photographer":
                return redirect(url_for("dashboard"))

            if role == "provider":
                return redirect(url_for("provider_dashboard"))

            return redirect(url_for("my_bookings"))
        except sqlite3.IntegrityError:
            flash("An account with that email already exists.", "error")

    return render_template(
        "register.html", role=role, categories=categories
    )


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

            if row["role"] == "provider":
                return redirect(url_for("provider_dashboard"))

            return redirect(url_for("my_bookings"))

            flash("Invalid email or password.", "error")

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

            booking_cursor = con.execute("""
                INSERT INTO bookings
                (photographer_id, client_name, email, session_date,
                 session_time, sessions, notes, client_user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                photographer_id, name, email, date,
                time, sessions, notes, client_user_id
            ))
            if person["user_id"]:
                con.execute("""
                    INSERT INTO notifications
                    (user_id, title, message, notification_type, related_id)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    person["user_id"],
                    "New photography booking",
                    f"{name} requested a session for {date} at {time}.",
                    "booking",
                    booking_cursor.lastrowid
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

        marketplace_bookings = con.execute("""
            SELECT
                marketplace_bookings.*,
                providers.display_name AS professional_name,
                providers.business_name,
                services.title AS service_title
            FROM marketplace_bookings
            JOIN providers
              ON providers.id = marketplace_bookings.provider_id
            JOIN services
              ON services.id = marketplace_bookings.service_id
            WHERE marketplace_bookings.client_user_id = ?
            ORDER BY marketplace_bookings.created_at DESC
        """, (current_user.id,)).fetchall()

    return render_template(
        "client_dashboard.html",
        bookings=bookings,
        marketplace_bookings=marketplace_bookings
    )


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

        notifications = con.execute("""
            SELECT *
            FROM notifications
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT 20
        """, (current_user.id,)).fetchall()

        unread_count = con.execute("""
            SELECT COUNT(*)
            FROM notifications
            WHERE user_id = ? AND is_read = 0
        """, (current_user.id,)).fetchone()[0]

    return render_template(
        "dashboard.html",
        bookings=bookings,
        notifications=notifications,
        unread_count=unread_count
    )


@app.route("/provider/services/create", methods=["POST"])
@login_required
def create_service():
    role_required("provider")

    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    pricing_mode = request.form.get("pricing_mode", "")
    booking_mode = request.form.get("booking_mode", "")

    try:
        category_id = int(request.form.get("category_id", ""))
    except ValueError:
        flash("Please select a valid category.", "error")
        return redirect(url_for("provider_dashboard"))

    if not title:
        flash("Please enter a service title.", "error")
        return redirect(url_for("provider_dashboard"))

    if pricing_mode not in ("fixed", "quote"):
        flash("Please select a valid pricing option.", "error")
        return redirect(url_for("provider_dashboard"))

    if booking_mode not in ("booking", "enquiry"):
        flash("Please select a valid booking option.", "error")
        return redirect(url_for("provider_dashboard"))

    if pricing_mode == "quote" and booking_mode != "enquiry":
        flash("Custom quotes must use the enquiry option.", "error")
        return redirect(url_for("provider_dashboard"))

    price = None

    if pricing_mode == "fixed":
        try:
            price = float(request.form.get("price", ""))
        except ValueError:
            flash("Please enter a valid service price.", "error")
            return redirect(url_for("provider_dashboard"))

        if price <= 0:
            flash("Service price must be greater than zero.", "error")
            return redirect(url_for("provider_dashboard"))

    with connect() as con:
        provider = con.execute("""
            SELECT id
            FROM providers
            WHERE user_id = ?
        """, (current_user.id,)).fetchone()

        if not provider:
            abort(404)

        category = con.execute("""
            SELECT categories.id
            FROM categories
            JOIN provider_categories
              ON categories.id = provider_categories.category_id
            WHERE categories.id = ?
              AND provider_categories.provider_id = ?
              AND categories.slug != 'costume-rentals'
        """, (category_id, provider["id"])).fetchone()

        if not category:
            flash("Please select one of your permitted service categories.", "error")
            return redirect(url_for("provider_dashboard"))

        con.execute("""
            INSERT INTO services (
                provider_id,
                category_id,
                title,
                description,
                pricing_mode,
                booking_mode,
                price
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            provider["id"],
            category_id,
            title,
            description,
            pricing_mode,
            booking_mode,
            price
        ))

    flash("Your service has been published.", "success")
    return redirect(url_for("provider_dashboard"))




@app.route("/service/<int:service_id>/request", methods=["POST"])
@login_required
def request_service(service_id):
    role_required("client")

    requested_date = request.form.get("requested_date", "").strip()
    client_message = request.form.get("client_message", "").strip()

    if not requested_date:
        flash("Please select your preferred service date.", "error")
        return redirect(request.referrer or url_for("home"))

    if len(client_message) > 2000:
        flash("Your message must not exceed 2,000 characters.", "error")
        return redirect(request.referrer or url_for("home"))

    with connect() as con:
        service = con.execute("""
            SELECT services.id, services.provider_id, services.booking_mode,
                   providers.user_id, services.title
            FROM services
            JOIN providers ON providers.id = services.provider_id
            WHERE services.id = ?
              AND services.is_active = 1
        """, (service_id,)).fetchone()

        if not service:
            abort(404)

        if service["user_id"] == current_user.id:
            flash("You cannot request your own service.", "error")
            return redirect(url_for(
                "public_provider", provider_id=service["provider_id"]
            ))

        existing = con.execute("""
            SELECT id
            FROM marketplace_bookings
            WHERE service_id = ?
              AND client_user_id = ?
              AND status NOT IN ('Cancelled', 'Completed')
        """, (service_id, current_user.id)).fetchone()

        if existing:
            flash("You already have an active request for this service.", "info")
            return redirect(url_for(
                "public_provider", provider_id=service["provider_id"]
            ))

        booking = con.execute("""
            INSERT INTO marketplace_bookings (
                service_id, provider_id, client_user_id,
                requested_date, client_message
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            service_id, service["provider_id"], current_user.id,
            requested_date, client_message
        ))

        if service["user_id"]:
            con.execute("""
                INSERT INTO notifications (
                    user_id, title, message, notification_type, related_id
                )
                VALUES (?, ?, ?, ?, ?)
            """, (
                service["user_id"],
                "New service request",
                f"{current_user.name} requested {service['title']} for {requested_date}.",
                "marketplace_booking",
                booking.lastrowid
            ))

    flash("Your service request has been sent to the creative professional.", "success")
    return redirect(url_for("my_bookings"))


@app.route("/marketplace-booking/<int:booking_id>/status", methods=["POST"])
@login_required
def marketplace_booking_status(booking_id):
    status = request.form.get("status", "")

    with connect() as con:
        booking = con.execute("""
            SELECT *
            FROM marketplace_bookings
            WHERE id = ?
        """, (booking_id,)).fetchone()

        if not booking:
            abort(404)

        if current_user.role == "provider":
            provider = con.execute("""
                SELECT id FROM providers WHERE user_id = ?
            """, (current_user.id,)).fetchone()

            if not provider or provider["id"] != booking["provider_id"]:
                abort(404)

            allowed = {
                "Requested": ("Accepted", "Cancelled"),
                "Accepted": ("In Progress", "Cancelled"),
                "In Progress": ("Awaiting Client Confirmation",)
            }

            if status not in allowed.get(booking["status"], ()):
                abort(400)

        elif current_user.role == "client":
            if booking["client_user_id"] != current_user.id:
                abort(404)

            if booking["status"] != "Awaiting Client Confirmation" or status != "Completed":
                abort(400)
        else:
            abort(403)

        con.execute("""
            UPDATE marketplace_bookings
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (status, booking_id))

    flash("Booking status updated.", "success")
    if current_user.role == "provider":
        return redirect(url_for("provider_dashboard"))
    return redirect(url_for("my_bookings"))


@app.route("/provider/portfolio/upload", methods=["POST"])
@login_required
def upload_portfolio():
    role_required("provider")

    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    uploaded_file = request.files.get("media")

    if not title or len(title) > 150:
        flash("Please enter a title of no more than 150 characters.", "error")
        return redirect(url_for("provider_dashboard"))

    if len(description) > 1000:
        flash("Description must not exceed 1000 characters.", "error")
        return redirect(url_for("provider_dashboard"))

    if not uploaded_file or not uploaded_file.filename:
        flash("Please choose an image or MP4 video.", "error")
        return redirect(url_for("provider_dashboard"))

    safe_original_name = secure_filename(uploaded_file.filename)
    suffix = Path(safe_original_name).suffix.lower()

    image_extensions = {".jpg", ".jpeg", ".png", ".webp"}

    if suffix not in image_extensions | {".mp4"}:
        flash("Unsupported file. Use JPG, PNG, WEBP or MP4.", "error")
        return redirect(url_for("provider_dashboard"))

    with connect() as con:
        provider = con.execute("""
            SELECT id
            FROM providers
            WHERE user_id = ?
        """, (current_user.id,)).fetchone()

    if not provider:
        abort(404)

    filename = uuid4().hex + suffix
    file_path = PORTFOLIO_UPLOAD_FOLDER / filename

    uploaded_file.save(file_path)

    try:
        if suffix in image_extensions:
            with file_path.open("rb") as media_file:
                signature = media_file.read(12)

            valid_image = (
                (suffix in {".jpg", ".jpeg"}
                 and signature.startswith(b"\xff\xd8\xff"))
                or
                (suffix == ".png"
                 and signature.startswith(b"\x89PNG\r\n\x1a\n"))
                or
                (suffix == ".webp"
                 and signature[:4] == b"RIFF"
                 and signature[8:12] == b"WEBP")
            )

            if not valid_image:
                raise ValueError("The uploaded image is invalid.")

            media_type = "image"

        else:
            video = MP4(str(file_path))

            if not video.info or not video.info.length:
                raise ValueError("Could not read the video duration.")

            if video.info.length > 120:
                raise ValueError("Videos must not exceed 2 minutes.")

            media_type = "video"

        with connect() as con:
            con.execute("""
                INSERT INTO portfolio_items (
                    provider_id,
                    media_type,
                    filename,
                    title,
                    description
                )
                VALUES (?, ?, ?, ?, ?)
            """, (
                provider["id"],
                media_type,
                filename,
                title,
                description
            ))

    except Exception as error:
        file_path.unlink(missing_ok=True)

        if isinstance(error, ValueError):
            flash(str(error), "error")
        else:
            flash("The file could not be validated. Please try another file.", "error")

        return redirect(url_for("provider_dashboard"))

    flash("Portfolio item uploaded successfully.", "success")
    return redirect(url_for("provider_dashboard"))


@app.route("/provider/portfolio/<int:item_id>/delete", methods=["POST"])
@login_required
def delete_portfolio_item(item_id):
    role_required("provider")

    with connect() as con:
        provider = con.execute("""
            SELECT id
            FROM providers
            WHERE user_id = ?
        """, (current_user.id,)).fetchone()

        if not provider:
            abort(404)

        item = con.execute("""
            SELECT *
            FROM portfolio_items
            WHERE id = ? AND provider_id = ?
        """, (item_id, provider["id"])).fetchone()

        if not item:
            abort(404)

        con.execute("""
            DELETE FROM portfolio_items
            WHERE id = ? AND provider_id = ?
        """, (item_id, provider["id"]))

    filename = Path(item["filename"]).name
    file_path = PORTFOLIO_UPLOAD_FOLDER / filename
    file_path.unlink(missing_ok=True)

    flash("Portfolio item deleted.", "success")
    return redirect(url_for("provider_dashboard"))


@app.route("/portfolio-media/<filename>")
def portfolio_media(filename):
    safe_filename = Path(filename).name

    with connect() as con:
        item = con.execute("""
            SELECT id
            FROM portfolio_items
            WHERE filename = ?
        """, (safe_filename,)).fetchone()

    if not item:
        abort(404)

    return send_from_directory(
        app.config["PORTFOLIO_UPLOAD_FOLDER"],
        safe_filename
    )




@app.route("/provider/<int:provider_id>")
def public_provider(provider_id):
    with connect() as con:
        provider = con.execute("""
            SELECT *
            FROM providers
            WHERE id = ?
        """, (provider_id,)).fetchone()

        if not provider:
            abort(404)

        categories = con.execute("""
            SELECT categories.name
            FROM categories
            JOIN provider_categories
              ON categories.id = provider_categories.category_id
            WHERE provider_categories.provider_id = ?
            ORDER BY categories.name
        """, (provider_id,)).fetchall()

        services = con.execute("""
            SELECT
                services.*,
                categories.name AS category_name
            FROM services
            JOIN categories
              ON services.category_id = categories.id
            WHERE services.provider_id = ?
              AND services.is_active = 1
            ORDER BY services.created_at DESC
        """, (provider_id,)).fetchall()

        portfolio_items = con.execute("""
            SELECT *
            FROM portfolio_items
            WHERE provider_id = ?
            ORDER BY created_at DESC
        """, (provider_id,)).fetchall()

    return render_template(
        "provider_public.html",
        provider=provider,
        categories=categories,
        services=services,
        portfolio_items=portfolio_items
    )

@app.route("/provider-dashboard")
@login_required
def provider_dashboard():
    role_required("provider")

    with connect() as con:
        provider = con.execute("""
            SELECT *
            FROM providers
            WHERE user_id = ?
        """, (current_user.id,)).fetchone()

        if not provider:
            abort(404)

        categories = con.execute("""
            SELECT categories.id, categories.name
            FROM categories
            JOIN provider_categories
              ON categories.id = provider_categories.category_id
            WHERE provider_categories.provider_id = ?
            ORDER BY categories.name
        """, (provider["id"],)).fetchall()
        service_categories = con.execute("""
            SELECT categories.id, categories.name
            FROM categories
            JOIN provider_categories
              ON categories.id = provider_categories.category_id
            WHERE provider_categories.provider_id = ?
              AND categories.slug != 'costume-rentals'
            ORDER BY categories.name
        """, (provider["id"],)).fetchall()
        services = con.execute("""
            SELECT
                services.*,
                categories.name AS category_name
            FROM services
            JOIN categories
              ON services.category_id = categories.id
            WHERE services.provider_id = ?
            ORDER BY services.created_at DESC
        """, (provider["id"],)).fetchall()

        portfolio_items = con.execute("""
            SELECT *
            FROM portfolio_items
            WHERE provider_id = ?
            ORDER BY created_at DESC
        """, (provider["id"],)).fetchall()

        marketplace_bookings = con.execute("""
            SELECT
                marketplace_bookings.*,
                users.name AS client_name,
                users.email AS client_email,
                services.title AS service_title
            FROM marketplace_bookings
            JOIN users
              ON users.id = marketplace_bookings.client_user_id
            JOIN services
              ON services.id = marketplace_bookings.service_id
            WHERE marketplace_bookings.provider_id = ?
            ORDER BY marketplace_bookings.created_at DESC
        """, (provider["id"],)).fetchall()

        notifications = con.execute("""
            SELECT *
            FROM notifications
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT 20
        """, (current_user.id,)).fetchall()

        unread_count = con.execute("""
            SELECT COUNT(*)
            FROM notifications
            WHERE user_id = ? AND is_read = 0
        """, (current_user.id,)).fetchone()[0]


        return render_template(
                "provider_dashboard.html",
                        provider=provider,
                categories=categories,
                service_categories=service_categories,
                services=services,
                portfolio_items=portfolio_items,
                marketplace_bookings=marketplace_bookings,
                notifications=notifications,
                unread_count=unread_count
    )
@app.route("/notifications/read", methods=["POST"])
@login_required
def mark_notifications_read():
    with connect() as con:
        con.execute("""
            UPDATE notifications
            SET is_read = 1
            WHERE user_id = ?
        """, (current_user.id,))

    flash("Notifications marked as read.", "success")

    if current_user.role == "photographer":
        return redirect(url_for("dashboard"))

    return redirect(url_for("provider_dashboard"))
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
