
import os
import sqlite3
import hashlib
import smtplib
from email.message import EmailMessage
from pathlib import Path
from datetime import datetime, timedelta
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, abort, send_from_directory, session
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

try:
    from authlib.integrations.flask_client import OAuth
except ImportError:
    OAuth = None


app = Flask(__name__)
app.secret_key = os.environ.get(
    "SECRET_KEY",
    "local-development-secret-change-before-deployment"
)

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "true" if os.environ.get("RAILWAY_PROJECT_ID") else "false").lower() == "true",
)

csrf = CSRFProtect(app)

oauth = OAuth(app) if OAuth else None
google_oauth = None
if oauth and os.environ.get("GOOGLE_CLIENT_ID") and os.environ.get("GOOGLE_CLIENT_SECRET"):
    google_oauth = oauth.register(
        name="google",
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

LEGAL_VERSIONS = {
    "terms": "0.1-draft",
    "privacy": "0.1-draft",
    "client-policy": "0.1-draft",
    "professional-agreement": "0.1-draft",
    "content-policy": "0.1-draft",
}
LAUNCH_POLICY = {
    "commission_rate": 0.10,
    "subscription_price": 0,
    "delivery_review_hours": 72,
    "payment_processing_fees": "Displayed separately at checkout",
    "payments_enabled": False,
}

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
    # Give concurrent requests time to wait for a write instead of failing
    # immediately when another request briefly holds SQLite's write lock.
    con = sqlite3.connect(DB, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA busy_timeout = 30000")
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
        # WAL allows readers to continue while a request writes to the database.
        # Keep one Railway replica while SQLite is the active database.
        con.execute("PRAGMA journal_mode = WAL")
        con.execute("PRAGMA synchronous = NORMAL")

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

        add_column_if_missing(con, "users", "auth_provider", "TEXT NOT NULL DEFAULT 'email'")
        add_column_if_missing(con, "users", "google_subject", "TEXT")
        add_column_if_missing(con, "users", "email_verified_at", "TEXT")
        con.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_google_subject
            ON users(google_subject)
            WHERE google_subject IS NOT NULL
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS legal_acceptances (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                document_key TEXT NOT NULL,
                document_version TEXT NOT NULL,
                accepted_at TEXT NOT NULL,
                acceptance_method TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        con.execute("""
            CREATE INDEX IF NOT EXISTS idx_legal_acceptances_user
            ON legal_acceptances(user_id, accepted_at)
        """)

        con.execute("""
            CREATE TABLE IF NOT EXISTS account_email_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipient_hash TEXT NOT NULL,
                event_type TEXT NOT NULL,
                sent_at TEXT NOT NULL
            )
        """)
        con.execute("""
            CREATE INDEX IF NOT EXISTS idx_account_email_events_recipient
            ON account_email_events(recipient_hash, event_type, sent_at)
        """)

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


        # Index frequently filtered and sorted marketplace records.
        # These indexes are safe to create on existing databases.
        con.execute("""
            CREATE INDEX IF NOT EXISTS idx_photographers_city
            ON photographers(city)
        """)
        con.execute("""
            CREATE INDEX IF NOT EXISTS idx_bookings_photographer_status
            ON bookings(photographer_id, status)
        """)
        con.execute("""
            CREATE INDEX IF NOT EXISTS idx_services_provider_active_created
            ON services(provider_id, is_active, created_at)
        """)
        con.execute("""
            CREATE INDEX IF NOT EXISTS idx_notifications_user_created
            ON notifications(user_id, created_at)
        """)
        con.execute("""
            CREATE INDEX IF NOT EXISTS idx_providers_city
            ON providers(city)
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


def account_token_serializer():
    return URLSafeTimedSerializer(app.secret_key, salt="onecre8-account-security-v1")


def reserve_account_email(recipient, event_type, limit=3, window_minutes=60):
    """Limit account-security email sends to three per recipient per hour; hash addresses at rest."""
    recipient_hash = hashlib.sha256(
        recipient.strip().lower().encode("utf-8")
    ).hexdigest()
    now = datetime.utcnow()
    cutoff = (now - timedelta(minutes=window_minutes)).isoformat()
    with connect() as con:
        con.execute("BEGIN IMMEDIATE")
        con.execute(
            "DELETE FROM account_email_events WHERE sent_at < ?",
            ((now - timedelta(days=30)).isoformat(),)
        )
        count = con.execute("""
            SELECT COUNT(*) AS total
            FROM account_email_events
            WHERE recipient_hash = ? AND event_type = ? AND sent_at >= ?
        """, (recipient_hash, event_type, cutoff)).fetchone()["total"]
        if count >= limit:
            con.rollback()
            return False
        con.execute("""
            INSERT INTO account_email_events
                (recipient_hash, event_type, sent_at)
            VALUES (?, ?, ?)
        """, (recipient_hash, event_type, now.isoformat()))
    return True


def send_account_email(recipient, subject, body, event_type):
    """Send account security mail through configured SMTP; never log tokens."""
    host = os.environ.get("SMTP_HOST")
    username = os.environ.get("SMTP_USERNAME")
    password = os.environ.get("SMTP_PASSWORD")
    sender = os.environ.get("MAIL_FROM")
    if not all((host, username, password, sender)):
        app.logger.warning("Account email unavailable: SMTP settings are incomplete.")
        return False
    if not reserve_account_email(recipient, event_type):
        app.logger.warning("Account security email rate limit reached.")
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = recipient
    message.set_content(body)
    try:
        port = int(os.environ.get("SMTP_PORT", "587"))
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            smtp.starttls()
            smtp.login(username, password)
            smtp.send_message(message)
        return True
    except (OSError, smtplib.SMTPException, ValueError):
        app.logger.exception("Unable to send account security email.")
        return False


def send_verification_email(user):
    token = account_token_serializer().dumps(
        {"user_id": user["id"], "email": user["email"]},
        salt="verify-email"
    )
    link = url_for("verify_email", token=token, _external=True)
    return send_account_email(
        user["email"],
        "Verify your OneCre8 Media email",
        "Welcome to OneCre8 Media. Verify your email address using this secure link. "
        "The link expires in 24 hours. If you did not create this account, ignore this email.\n\n"
        + link,
        "verification"
    )


def send_password_reset_email(user):
    token = account_token_serializer().dumps(
        {
            "user_id": user["id"],
            "email": user["email"],
            "password_hash": user["password_hash"],
        },
        salt="reset-password"
    )
    link = url_for("reset_password", token=token, _external=True)
    return send_account_email(
        user["email"],
        "Reset your OneCre8 Media password",
        "A password reset was requested for your OneCre8 Media account. "
        "This secure link expires in 1 hour. If you did not request it, ignore this email.\n\n"
        + link,
        "password_reset"
    )


def record_legal_acceptances(con, user_id, role, method):
    document_keys = ["terms", "privacy", "content-policy"]
    document_keys.append(
        "professional-agreement" if role in ("provider", "photographer")
        else "client-policy"
    )
    accepted_at = datetime.utcnow().isoformat()
    con.executemany("""
        INSERT INTO legal_acceptances
            (user_id, document_key, document_version, accepted_at, acceptance_method)
        VALUES (?, ?, ?, ?, ?)
    """, [
        (user_id, key, LEGAL_VERSIONS[key], accepted_at, method)
        for key in document_keys
    ])


def legal_documents():
    return {
        "terms": {
            "title": "General Terms and Conditions",
            "intro": "DRAFT FOR NIGERIAN LEGAL REVIEW. These draft terms describe intended OneCre8 marketplace rules and must be reviewed and approved by qualified Nigerian counsel before being treated as final legal terms.",
            "sections": [
                ("1. Platform role", "OneCre8 provides an online marketplace for clients to discover and contact creative professionals. Unless a specific written agreement says otherwise, the professional and client remain responsible for agreeing and performing the underlying service."),
                ("2. Accounts", "Users must provide accurate information, protect sign-in credentials, keep account details current and promptly report suspected unauthorised access."),
                ("3. Marketplace conduct", "Users must not engage in fraud, impersonation, harassment, discrimination, threats, fake reviews, misleading listings or misuse of another person's personal data or intellectual property."),
                ("4. Launch fees", "The launch model is free to join with no mandatory subscription. The proposed OneCre8 commission is 10% of the eligible completed transaction amount. The commission base, taxes and payment-provider charges must be disclosed before a professional accepts a booking."),
                ("5. Payments", "Live payment collection, custody, split settlement and payouts are not enabled in this release. Any future payment flow requires payment-provider and legal approval and separately published payment terms."),
                ("6. Disputes", "Complaints will be reviewed individually using booking terms and available evidence. Nothing in these draft terms removes rights or remedies that cannot lawfully be excluded."),
                ("7. Suspension and appeals", "OneCre8 may investigate suspected policy violations and take proportionate action. Where reasonably possible, affected users will receive the reason and an opportunity to respond or appeal."),
                ("8. Changes", "Material changes will be communicated and, where required, users will be asked to accept the updated version.")
            ]
        },
        "privacy": {
            "title": "Privacy Policy",
            "intro": "DRAFT FOR NIGERIAN DATA-PROTECTION REVIEW. Complete this notice with OneCre8's legal identity, contact details, retention schedule, processors and approved lawful bases before launch.",
            "sections": [
                ("1. Information collected", "Account name, email, role, profile details, portfolio uploads, listings, booking details, messages, support records, security logs and payment references when payment features are later enabled."),
                ("2. Google sign-in", "Google sign-in requests OpenID Connect identity, email and basic profile scopes only. OneCre8 does not request permission to read, send or manage Gmail messages."),
                ("3. Uses", "Information is used to create and secure accounts, operate marketplace features, connect clients and professionals, respond to support requests, prevent fraud and meet legal obligations."),
                ("4. Sharing", "Information may be shared with the other party to a booking, service providers acting on OneCre8's instructions, approved payment providers when enabled, and authorities where legally required."),
                ("5. Security and retention", "OneCre8 will apply access controls and reasonable safeguards. Final retention periods and deletion procedures must be documented before launch."),
                ("6. User rights", "Users may have rights to request access, correction, deletion or other remedies under applicable data-protection law. A working privacy contact and request process must be published before launch.")
            ]
        },
        "client-policy": {
            "title": "Client Booking and Service Policy",
            "intro": "DRAFT FOR LEGAL REVIEW. This policy is intended to clarify booking expectations while preserving mandatory consumer rights.",
            "sections": [
                ("1. Before booking", "Review the scope, deliverables, price, date, location, revision allowance, cancellation terms and additional expenses before accepting."),
                ("2. Delivery", "The professional should deliver the agreed work or service by the agreed deadline and notify the client when it is ready for review."),
                ("3. Review period", "The intended review period is 72 hours after a valid delivery notification. Final rules must define when it starts, what counts as delivery, extensions and statutory-rights exceptions."),
                ("4. Complaints and refunds", "Refund and dispute requests are reviewed case by case using the agreed scope, communications, delivery evidence and applicable law. A blanket no-refund rule does not apply."),
                ("5. Client responsibilities", "Clients should provide accurate briefs, materials, access and feedback required by the agreed schedule.")
            ]
        },
        "professional-agreement": {
            "title": "Creative Professional Agreement",
            "intro": "DRAFT FOR NIGERIAN LEGAL REVIEW. Final terms must clarify professional status, platform responsibilities, payment-provider structure and consumer-law obligations.",
            "sections": [
                ("1. Free launch membership", "There is no mandatory monthly subscription at launch. Any future paid plan requires separate pricing and consent."),
                ("2. Commission", "The proposed OneCre8 commission is 10% of the eligible completed transaction amount. The calculation must be disclosed before a professional accepts a booking. Payment-provider charges and taxes are separate line items."),
                ("3. Professional obligations", "Keep listings accurate, honour accepted bookings, deliver the agreed scope, obtain permissions for portfolio materials and treat clients respectfully."),
                ("4. Scope changes", "Additional work, expenses, revisions or schedule changes should be agreed in writing before the extra work is undertaken."),
                ("5. Delivery and review", "The intended client review period is 72 hours after valid delivery notification. Payout eligibility is not active in this release and requires approved payment-provider arrangements."),
                ("6. Fair complaints process", "Professionals may respond to complaints and submit evidence. Decisions should be reasoned, proportionate and subject to a defined appeal process."),
                ("7. Intellectual property", "Ownership, licences, portfolio display and client usage rights should be agreed in each booking and must respect third-party rights.")
            ]
        },
        "content-policy": {
            "title": "Marketplace Content and Review Policy",
            "intro": "DRAFT FOR LEGAL REVIEW. This policy applies to listings, portfolio uploads, messages, ratings and public reviews.",
            "sections": [
                ("1. Rights and permissions", "Only upload content you own or are authorised to use. Obtain appropriate consent before publishing identifiable client images or private event footage."),
                ("2. Prohibited material", "Do not upload unlawful, deceptive, infringing, exploitative, harassing, discriminatory or privacy-invasive material."),
                ("3. Reviews", "Reviews must reflect genuine marketplace experiences. Fake, purchased, retaliatory or manipulated reviews are prohibited."),
                ("4. Reporting and moderation", "Users may report content or reviews. OneCre8 may investigate and restrict or remove material under a documented process with an appeal route.")
            ]
        }
    }


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

        service_query = """
            SELECT services.id, services.title, services.description,
                   services.pricing_mode, services.price,
                   categories.name AS category_name,
                   providers.id AS provider_id,
                   providers.display_name, providers.business_name,
                   providers.city, providers.profile_image
            FROM services
            JOIN categories ON categories.id = services.category_id
            JOIN providers ON providers.id = services.provider_id
            WHERE services.is_active = 1
        """
        service_args = []
        if city:
            service_query += " AND providers.city LIKE ?"
            service_args.append(f"%{city}%")
        if category_slug:
            service_query += " AND categories.slug = ?"
            service_args.append(category_slug)
        service_query += " ORDER BY services.created_at DESC LIMIT 24"
        marketplace_services = con.execute(
            service_query, service_args
        ).fetchall()

        # Small, category-specific homepage previews keep discovery curated.
        showcase_services = {}
        for slug in ("photography", "videography", "spaces-studios", "photo-framing", "interior-design"):
            showcase_services[slug] = con.execute("""
                SELECT services.id, services.title, services.description,
                       services.pricing_mode, services.price,
                       categories.name AS category_name,
                       providers.id AS provider_id,
                       providers.display_name, providers.business_name,
                       providers.city, providers.profile_image,
                       COALESCE(
                           (SELECT '/portfolio-media/' || portfolio_items.filename
                            FROM portfolio_items
                            WHERE portfolio_items.provider_id = providers.id
                              AND portfolio_items.media_type = 'image'
                            ORDER BY portfolio_items.created_at DESC
                            LIMIT 1),
                           providers.profile_image
                       ) AS preview_image
                FROM services
                JOIN categories ON categories.id = services.category_id
                JOIN providers ON providers.id = services.provider_id
                WHERE services.is_active = 1
                  AND categories.slug = ?
                  AND (? = '' OR providers.city LIKE ?)
                ORDER BY services.created_at DESC
                LIMIT 4
            """, (slug, city, f"%{city}%")).fetchall()

        showcase_products = {}
        for slug in ("media-equipment", "artwork", "costume-rentals"):
            showcase_products[slug] = con.execute("""
                SELECT products.id, products.title, products.description,
                       products.listing_type, products.price,
                       products.quantity_available, products.image,
                       categories.name AS category_name,
                       providers.id AS provider_id,
                       providers.display_name, providers.business_name,
                       providers.city, providers.profile_image
                FROM products
                JOIN categories ON categories.id = products.category_id
                JOIN providers ON providers.id = products.provider_id
                WHERE products.is_active = 1
                  AND categories.slug = ?
                  AND (? = '' OR providers.city LIKE ?)
                ORDER BY products.created_at DESC
                LIMIT 4
            """, (slug, city, f"%{city}%")).fetchall()

        categories = con.execute(
            "SELECT id, name, slug FROM categories ORDER BY name"
        ).fetchall()

    return render_template(
        "index.html",
        photographers=photographers,
        creative_professionals=creative_professionals,
        marketplace_services=marketplace_services,
        showcase_services=showcase_services,
        showcase_products=showcase_products,
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

        required_agreement = (
            "accept_professional_agreement"
            if role in ("provider", "photographer")
            else "accept_client_policy"
        )
        if not all(request.form.get(key) for key in (
            "accept_terms", "accept_privacy", "accept_content_policy",
            required_agreement
        )):
            flash("Please review and accept the required OneCre8 policies.", "error")
            return render_template(
                "register.html", role=role, categories=categories,
                legal_versions=LEGAL_VERSIONS,
                google_enabled=bool(google_oauth)
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

            provider_photo = request.files.get("profile_image")
            if provider_photo and provider_photo.filename:
                allowed_image_extensions = {".jpg", ".jpeg", ".png", ".webp"}
                photo_extension = Path(
                    secure_filename(provider_photo.filename)
                ).suffix.lower()
                if photo_extension not in allowed_image_extensions:
                    flash("Profile picture must be JPG, PNG or WebP.", "error")
                    return render_template(
                        "register.html", role=role, categories=categories
                    )
                provider_photo.stream.seek(0, os.SEEK_END)
                photo_size = provider_photo.stream.tell()
                provider_photo.stream.seek(0)
                if photo_size > 5 * 1024 * 1024:
                    flash("Profile pictures must be 5 MB or smaller.", "error")
                    return render_template(
                        "register.html", role=role, categories=categories
                    )
                signature = provider_photo.stream.read(12)
                provider_photo.stream.seek(0)
                valid_image = (
                    (photo_extension in {".jpg", ".jpeg"} and signature.startswith(b"\xff\xd8\xff"))
                    or (photo_extension == ".png" and signature.startswith(b"\x89PNG\r\n\x1a\n"))
                    or (photo_extension == ".webp" and signature[:4] == b"RIFF" and signature[8:12] == b"WEBP")
                )
                if not valid_image:
                    flash("The selected profile picture is not a valid image.", "error")
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
                    (name, email, password_hash, role, created_at, auth_provider)
                    VALUES (?, ?, ?, ?, ?, 'email_pending')
                """, (
                    name,
                    email,
                    generate_password_hash(password),
                    role,
                    datetime.utcnow().isoformat()
                ))

                user_id = cursor.lastrowid
                record_legal_acceptances(con, user_id, role, "email")

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

                    if provider_photo and provider_photo.filename:
                        photo_name = (
                            f"profile-{provider_id}-{uuid4().hex}"
                            f"{photo_extension}"
                        )
                        provider_photo.save(
                            Path(app.config["PORTFOLIO_UPLOAD_FOLDER"]) / photo_name
                        )
                        con.execute("""
                            UPDATE providers
                            SET profile_image = ?
                            WHERE id = ?
                        """, ("/profile-media/" + photo_name, provider_id))

                user_row = con.execute(
                    "SELECT * FROM users WHERE id = ?", (user_id,)
                ).fetchone()

            if send_verification_email(user_row):
                flash("Your account has been created. Check your email for a verification link before logging in.", "success")
            else:
                flash("Your account has been created, but email delivery is not configured yet. Please contact OneCre8 support to complete verification.", "error")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("An account with that email already exists.", "error")

    return render_template(
        "register.html", role=role, categories=categories,
        legal_versions=LEGAL_VERSIONS, google_enabled=bool(google_oauth)
    )


@app.route("/legal/<slug>")
def legal_document(slug):
    document = legal_documents().get(slug)
    if not document:
        abort(404)
    return render_template(
        "legal_document.html", document=document,
        version=LEGAL_VERSIONS[slug], slug=slug
    )


@app.route("/auth/google/start", methods=["POST"])
def google_start():
    if not google_oauth:
        flash("Google sign-in is not configured yet. Please use email and password.", "error")
        return redirect(url_for("register"))
    role = request.form.get("role", "client")
    if role not in ("client", "provider"):
        abort(400)
    role_doc = "accept_professional_agreement" if role == "provider" else "accept_client_policy"
    if not all(request.form.get(key) for key in (
        "accept_terms", "accept_privacy", "accept_content_policy", role_doc
    )):
        flash("Please review and accept the required OneCre8 policies first.", "error")
        return redirect(url_for("register", role=role))
    if role == "provider":
        city = request.form.get("city", "").strip()
        bio = request.form.get("bio", "").strip()
        try:
            category_ids = {int(value) for value in request.form.getlist("category_ids")}
        except ValueError:
            category_ids = set()
        with connect() as con:
            valid_ids = {item["id"] for item in con.execute("SELECT id FROM categories").fetchall()}
        if not city or not bio or not category_ids or not category_ids.issubset(valid_ids):
            flash("Creative professionals must provide a city, biography and at least one valid category.", "error")
            return redirect(url_for("register", role="provider"))

    session["pending_google_registration"] = {
        "role": role,
        "name": request.form.get("name", "").strip(),
        "business_name": request.form.get("business_name", "").strip(),
        "city": request.form.get("city", "").strip(),
        "bio": request.form.get("bio", "").strip(),
        "category_ids": request.form.getlist("category_ids"),
    }
    session["pending_google_acceptance"] = True
    return google_oauth.authorize_redirect(url_for("google_callback", _external=True))


@app.route("/auth/google/login")
def google_login():
    if not google_oauth:
        flash("Google sign-in is not configured yet.", "error")
        return redirect(url_for("login"))
    session.pop("pending_google_registration", None)
    session.pop("pending_google_acceptance", None)
    session["google_login_only"] = True
    return google_oauth.authorize_redirect(url_for("google_callback", _external=True))


@app.route("/auth/google/callback")
def google_callback():
    if not google_oauth:
        abort(503)
    token = google_oauth.authorize_access_token()
    identity = token.get("userinfo") or google_oauth.userinfo()
    email = (identity.get("email") or "").strip().lower()
    subject = identity.get("sub")
    verified = identity.get("email_verified") in (True, "true", "True", 1)
    if not email or not subject or not verified:
        flash("Google did not provide a verified email address.", "error")
        return redirect(url_for("register"))

    pending = session.pop("pending_google_registration", None)
    accepted = session.pop("pending_google_acceptance", False)
    login_only = session.pop("google_login_only", False)
    with connect() as con:
        row = con.execute("SELECT * FROM users WHERE google_subject = ?", (subject,)).fetchone()
        if not row and login_only:
            row = con.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            if not row:
                flash("No OneCre8 account is linked to that Google address. Please register first.", "error")
                return redirect(url_for("register"))
            con.execute("""
                UPDATE users SET google_subject = ?, auth_provider = 'google_linked',
                    email_verified_at = COALESCE(email_verified_at, ?)
                WHERE id = ?
            """, (subject, datetime.utcnow().isoformat(), row["id"]))
            row = con.execute("SELECT * FROM users WHERE id = ?", (row["id"],)).fetchone()
        elif not row and pending and accepted:
            row = con.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            if row:
                con.execute("""
                    UPDATE users SET google_subject = ?, auth_provider = 'google_linked',
                        email_verified_at = COALESCE(email_verified_at, ?)
                    WHERE id = ?
                """, (subject, datetime.utcnow().isoformat(), row["id"]))
                row = con.execute("SELECT * FROM users WHERE id = ?", (row["id"],)).fetchone()
            else:
                role = pending["role"]
                name = pending["name"] or identity.get("name") or email.split("@")[0]
                cursor = con.execute("""
                    INSERT INTO users
                        (name, email, password_hash, role, created_at,
                         auth_provider, google_subject, email_verified_at)
                    VALUES (?, ?, ?, ?, ?, 'google', ?, ?)
                """, (
                    name, email, generate_password_hash(uuid4().hex),
                    role, datetime.utcnow().isoformat(), subject,
                    datetime.utcnow().isoformat()
                ))
                user_id = cursor.lastrowid
                record_legal_acceptances(con, user_id, role, "google")
                if role == "provider":
                    provider_cursor = con.execute("""
                        INSERT INTO providers
                            (user_id, display_name, business_name, bio, city)
                        VALUES (?, ?, ?, ?, ?)
                    """, (user_id, name, pending["business_name"], pending["bio"], pending["city"]))
                    provider_id = provider_cursor.lastrowid
                    try:
                        category_ids = list({int(value) for value in pending["category_ids"]})
                    except (TypeError, ValueError):
                        category_ids = []
                    valid_ids = {item["id"] for item in con.execute("SELECT id FROM categories").fetchall()}
                    if category_ids and set(category_ids).issubset(valid_ids):
                        con.executemany("""
                            INSERT OR IGNORE INTO provider_categories (provider_id, category_id)
                            VALUES (?, ?)
                        """, [(provider_id, value) for value in category_ids])
                row = con.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        elif not row:
            flash("Please start Google registration from the create-account page.", "error")
            return redirect(url_for("register"))

    if not row:
        abort(403)
    login_user(User(row))
    flash("You are signed in to OneCre8.", "success")
    if row["role"] == "provider":
        return redirect(url_for("provider_dashboard"))
    if row["role"] == "photographer":
        return redirect(url_for("dashboard"))
    return redirect(url_for("my_bookings"))


@app.route("/verify-email/<token>")
def verify_email(token):
    try:
        payload = account_token_serializer().loads(
            token, salt="verify-email", max_age=86400
        )
    except SignatureExpired:
        flash("That verification link has expired. Request a new one.", "error")
        return redirect(url_for("resend_verification"))
    except BadSignature:
        abort(400)

    with connect() as con:
        user = con.execute(
            "SELECT * FROM users WHERE id = ? AND email = ?",
            (payload.get("user_id"), payload.get("email"))
        ).fetchone()
        if not user:
            abort(404)
        con.execute("""
            UPDATE users
            SET email_verified_at = ?, auth_provider = 'email'
            WHERE id = ?
        """, (datetime.utcnow().isoformat(), user["id"]))
    flash("Your email has been verified. You can now log in.", "success")
    return redirect(url_for("login"))


@app.route("/resend-verification", methods=["GET", "POST"])
def resend_verification():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        with connect() as con:
            user = con.execute(
                "SELECT * FROM users WHERE email = ?", (email,)
            ).fetchone()
        # Keep response generic to avoid disclosing whether an account exists.
        if user and user["auth_provider"] == "email_pending":
            send_verification_email(user)
        flash("If the account needs verification, a new link has been sent, it will arrive shortly.", "success")
        return redirect(url_for("login"))
    return render_template("resend_verification.html")


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        with connect() as con:
            user = con.execute(
                "SELECT * FROM users WHERE email = ?", (email,)
            ).fetchone()
        if user and user["auth_provider"] != "google":
            send_password_reset_email(user)
        flash("If an account exists for that email, password reset instructions have been sent.", "success")
        return redirect(url_for("login"))
    return render_template("forgot_password.html")


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    try:
        payload = account_token_serializer().loads(
            token, salt="reset-password", max_age=3600
        )
    except SignatureExpired:
        flash("That password reset link has expired. Request another one.", "error")
        return redirect(url_for("forgot_password"))
    except BadSignature:
        abort(400)

    with connect() as con:
        user = con.execute(
            "SELECT * FROM users WHERE id = ? AND email = ?",
            (payload.get("user_id"), payload.get("email"))
        ).fetchone()
    if not user or payload.get("password_hash") != user["password_hash"]:
        flash("That password reset link is no longer valid. Request a new one.", "error")
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirmation = request.form.get("confirm_password", "")
        if len(password) < 8:
            flash("Your new password must contain at least 8 characters.", "error")
        elif password != confirmation:
            flash("The passwords do not match.", "error")
        else:
            with connect() as con:
                con.execute(
                    "UPDATE users SET password_hash = ? WHERE id = ?",
                    (generate_password_hash(password), user["id"])
                )
            flash("Your password has been reset. Please log in.", "success")
            return redirect(url_for("login"))
    return render_template("reset_password.html")


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
            if row["auth_provider"] == "email_pending" and not row["email_verified_at"]:
                flash("Please verify your email before logging in.", "error")
                return redirect(url_for("resend_verification"))
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

    return render_template("login.html", google_enabled=bool(google_oauth))

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





@app.route("/service/<int:service_id>")
def service_detail(service_id):
    with connect() as con:
        service = con.execute("""
            SELECT services.*, categories.name AS category_name,
                   providers.id AS provider_id,
                   providers.display_name, providers.business_name,
                   providers.city, providers.bio, providers.profile_image
            FROM services
            JOIN categories ON categories.id = services.category_id
            JOIN providers ON providers.id = services.provider_id
            WHERE services.id = ? AND services.is_active = 1
        """, (service_id,)).fetchone()
    if not service:
        abort(404)
    return render_template("service_detail.html", service=service)


@app.route("/provider/profile/update", methods=["POST"])
@login_required
def update_provider_profile():
    role_required("provider")
    display_name = request.form.get("display_name", "").strip()
    business_name = request.form.get("business_name", "").strip()
    bio = request.form.get("bio", "").strip()
    city = request.form.get("city", "").strip()
    profile_image = request.form.get("profile_image", "").strip()
    profile_picture = request.files.get("profile_picture")
    new_picture_path = None

    if profile_picture and profile_picture.filename:
        suffix = Path(secure_filename(profile_picture.filename)).suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
            flash("Profile pictures must be JPG, PNG or WEBP.", "error")
            return redirect(url_for("provider_dashboard"))
        filename = "profile-" + uuid4().hex + suffix
        new_picture_path = PORTFOLIO_UPLOAD_FOLDER / filename
        profile_picture.save(new_picture_path)
        with new_picture_path.open("rb") as image_file:
            signature = image_file.read(12)
        valid = (
            (suffix in {".jpg", ".jpeg"} and signature.startswith(b"\xff\xd8\xff"))
            or (suffix == ".png" and signature.startswith(b"\x89PNG\r\n\x1a\n"))
            or (suffix == ".webp" and signature[:4] == b"RIFF" and signature[8:12] == b"WEBP")
        )
        if not valid:
            new_picture_path.unlink(missing_ok=True)
            flash("The selected profile picture is not a valid image.", "error")
            return redirect(url_for("provider_dashboard"))
        profile_image = "/profile-media/" + filename

    if not display_name or not city or not bio:
        flash("Your name, location and biography are required.", "error")
        return redirect(url_for("provider_dashboard"))
    if len(display_name) > 100 or len(business_name) > 120 or len(bio) > 1500 or len(city) > 100:
        flash("Please shorten one or more profile fields.", "error")
        return redirect(url_for("provider_dashboard"))
    if profile_image and not (profile_image.startswith("https://") or profile_image.startswith("/profile-media/")):
        flash("Profile image must be a secure HTTPS image address.", "error")
        return redirect(url_for("provider_dashboard"))

    with connect() as con:
        provider = con.execute(
            "SELECT id, profile_image FROM providers WHERE user_id = ?", (current_user.id,)
        ).fetchone()
        if not provider:
            abort(404)
        if not profile_image:
            profile_image = provider["profile_image"] or ""
        con.execute("""
            UPDATE providers
            SET display_name = ?, business_name = ?, bio = ?,
                city = ?, profile_image = ?
            WHERE id = ?
        """, (display_name, business_name, bio, city, profile_image, provider["id"]))
        con.execute("UPDATE users SET name = ? WHERE id = ?", (display_name, current_user.id))
    flash("Your Creative Professional profile has been updated.", "success")
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




@app.route("/profile-media/<filename>")
def profile_media(filename):
    safe_filename = Path(filename).name
    expected_path = "/profile-media/" + safe_filename
    with connect() as con:
        exists = con.execute(
            "SELECT id FROM providers WHERE profile_image = ?",
            (expected_path,)
        ).fetchone()
    if not exists:
        abort(404)
    return send_from_directory(app.config["PORTFOLIO_UPLOAD_FOLDER"], safe_filename)


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
