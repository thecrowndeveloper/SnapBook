"""Small, dependency-free regression checks for the public marketplace entry points."""

import os
import io
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse

# Give this test process an isolated SQLite database and upload directory.
_TEST_STORAGE = tempfile.TemporaryDirectory(prefix="onecre8-tests-")
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = _TEST_STORAGE.name
os.environ["SECRET_KEY"] = "onecre8-test-secret-not-for-production"

from app import app  # noqa: E402


class LocalImageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "img" and values.get("src"):
            self.urls.append(values["src"])
        if tag in ("img", "source") and values.get("srcset"):
            self.urls.extend(
                candidate.strip().split()[0]
                for candidate in values["srcset"].split(",")
                if candidate.strip()
            )


class HomepageRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config.update(TESTING=True)
        cls.client = app.test_client()

    def test_homepage_includes_baseline_security_headers(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(response.headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(
            response.headers.get("Referrer-Policy"),
            "strict-origin-when-cross-origin",
        )
        self.assertEqual(
            response.headers.get("Permissions-Policy"),
            "camera=(), microphone=(), geolocation=()",
        )

    def test_homepage_renders_all_eight_category_shelves(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("OneCre8 Media", html)
        self.assertIn('id="main-content"', html)
        for slug in (
            "photography", "videography", "media-equipment", "artwork",
            "costume-rentals", "spaces-studios", "photo-framing",
            "interior-design",
        ):
            self.assertIn(f'id="shelf-{slug}"', html)

    def test_homepage_local_images_exist(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        parser = LocalImageParser()
        parser.feed(response.get_data(as_text=True))
        missing = []
        for url in parser.urls:
            parsed = urlparse(url)
            if parsed.scheme or not parsed.path.startswith("/static/"):
                continue
            relative_path = unquote(parsed.path[len("/static/"):])
            asset = Path(app.static_folder) / relative_path
            if not asset.is_file():
                missing.append(relative_path)
        self.assertTrue(parser.urls, "Expected homepage image references.")
        self.assertEqual(missing, [], f"Missing local homepage images: {missing}")

    def test_registration_page_loads(self):
        response = self.client.get("/register")
        self.assertEqual(response.status_code, 200)

    def test_provider_dashboard_requires_login(self):
        response = self.client.get("/provider-dashboard")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers.get("Location", ""))

    def test_login_form_rejects_post_without_csrf_token(self):
        response = self.client.post(
            "/login",
            data={"email": "nobody@example.com", "password": "not-a-real-password"},
        )
        self.assertEqual(response.status_code, 400)

    def test_login_page_renders_csrf_token_field(self):
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)
        self.assertIn('name="csrf_token"', response.get_data(as_text=True))

    def test_production_startup_rejects_missing_secret_key(self):
        import subprocess
        import sys

        env = os.environ.copy()
        env.pop("SECRET_KEY", None)
        env["RAILWAY_PROJECT_ID"] = "test-production-project"
        env["RAILWAY_VOLUME_MOUNT_PATH"] = _TEST_STORAGE.name

        result = subprocess.run(
            [sys.executable, "-c", "import app"],
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SECRET_KEY must be configured", result.stderr)



class PortfolioUploadValidationTests(unittest.TestCase):
    def test_video_upload_rejects_empty_file(self):
        from types import SimpleNamespace
        from app import validate_video_upload_size

        uploaded = SimpleNamespace(stream=io.BytesIO(b""))
        with self.assertRaisesRegex(ValueError, "empty"):
            validate_video_upload_size(uploaded)

    def test_video_upload_rejects_file_over_50_mb(self):
        from types import SimpleNamespace
        from app import MAX_VIDEO_UPLOAD_BYTES, validate_video_upload_size

        uploaded = SimpleNamespace(
            stream=io.BytesIO(b"x" * (MAX_VIDEO_UPLOAD_BYTES + 1))
        )
        with self.assertRaisesRegex(ValueError, "50 MB"):
            validate_video_upload_size(uploaded)

    def test_video_upload_accepts_file_within_size_limit(self):
        from types import SimpleNamespace
        from app import validate_video_upload_size

        uploaded = SimpleNamespace(stream=io.BytesIO(b"valid-size-placeholder"))
        self.assertEqual(validate_video_upload_size(uploaded), 22)


if __name__ == "__main__":
    unittest.main()


class BookingAuthorizationRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import connect

        cls.connect = staticmethod(connect)
        with connect() as con:
            con.execute(
                "INSERT INTO users (name, email, password_hash, role, created_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
                ("Test Client One", "booking-client-one@example.test", "not-used", "client"),
            )
            cls.client_one_id = con.execute(
                "SELECT id FROM users WHERE email = ?", ("booking-client-one@example.test",)
            ).fetchone()["id"]
            con.execute(
                "INSERT INTO users (name, email, password_hash, role, created_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
                ("Test Client Two", "booking-client-two@example.test", "not-used", "client"),
            )
            cls.client_two_id = con.execute(
                "SELECT id FROM users WHERE email = ?", ("booking-client-two@example.test",)
            ).fetchone()["id"]
            con.execute(
                "INSERT INTO users (name, email, password_hash, role, created_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
                ("Test Professional One", "booking-provider-one@example.test", "not-used", "provider"),
            )
            cls.provider_user_one_id = con.execute(
                "SELECT id FROM users WHERE email = ?", ("booking-provider-one@example.test",)
            ).fetchone()["id"]
            con.execute(
                "INSERT INTO users (name, email, password_hash, role, created_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
                ("Test Professional Two", "booking-provider-two@example.test", "not-used", "provider"),
            )
            cls.provider_user_two_id = con.execute(
                "SELECT id FROM users WHERE email = ?", ("booking-provider-two@example.test",)
            ).fetchone()["id"]
            con.execute(
                "INSERT INTO categories (name, slug) VALUES (?, ?)",
                ("Booking Test Category", "booking-test-category"),
            )
            category_id = con.execute(
                "SELECT id FROM categories WHERE slug = ?", ("booking-test-category",)
            ).fetchone()["id"]
            con.execute(
                "INSERT INTO providers (user_id, display_name) VALUES (?, ?)",
                (cls.provider_user_one_id, "Test Professional One"),
            )
            cls.provider_one_id = con.execute(
                "SELECT id FROM providers WHERE user_id = ?", (cls.provider_user_one_id,)
            ).fetchone()["id"]
            con.execute(
                "INSERT INTO providers (user_id, display_name) VALUES (?, ?)",
                (cls.provider_user_two_id, "Test Professional Two"),
            )
            cls.provider_two_id = con.execute(
                "SELECT id FROM providers WHERE user_id = ?", (cls.provider_user_two_id,)
            ).fetchone()["id"]
            con.execute(
                """INSERT INTO services
                   (provider_id, category_id, title, pricing_mode, booking_mode)
                   VALUES (?, ?, ?, ?, ?)""",
                (cls.provider_one_id, category_id, "Test Service", "fixed", "booking"),
            )
            cls.service_id = con.execute(
                "SELECT id FROM services WHERE title = ?", ("Test Service",)
            ).fetchone()["id"]

    def create_booking(self, client_user_id=None, provider_id=None, status="Requested"):
        with self.connect() as con:
            cursor = con.execute(
                """INSERT INTO marketplace_bookings
                   (service_id, provider_id, client_user_id, requested_date, status)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    self.service_id,
                    provider_id or self.provider_one_id,
                    client_user_id or self.client_one_id,
                    "2030-01-15",
                    status,
                ),
            )
            return cursor.lastrowid

    def post_as(self, user_id, booking_id, status):
        from app import app

        old_csrf = app.config.get("WTF_CSRF_ENABLED", True)
        app.config["WTF_CSRF_ENABLED"] = False
        try:
            with app.test_client() as client:
                with client.session_transaction() as session:
                    session["_user_id"] = str(user_id)
                    session["_fresh"] = True
                return client.post(
                    f"/marketplace-booking/{booking_id}/status",
                    data={"status": status},
                )
        finally:
            app.config["WTF_CSRF_ENABLED"] = old_csrf

    def test_client_cannot_update_another_clients_booking(self):
        booking_id = self.create_booking(client_user_id=self.client_one_id)
        response = self.post_as(self.client_two_id, booking_id, "Completed")
        self.assertEqual(response.status_code, 404)

    def test_professional_cannot_update_another_professionals_booking(self):
        booking_id = self.create_booking(provider_id=self.provider_one_id)
        response = self.post_as(
            self.provider_user_two_id, booking_id, "Accepted"
        )
        self.assertEqual(response.status_code, 404)

    def test_professional_cannot_skip_booking_status_steps(self):
        booking_id = self.create_booking(status="Requested")
        response = self.post_as(
            self.provider_user_one_id, booking_id, "Completed"
        )
        self.assertEqual(response.status_code, 400)

    def post_review_as(self, user_id, booking_id, rating="5", review_text="Great work"):
        from app import app

        old_csrf = app.config.get("WTF_CSRF_ENABLED", True)
        app.config["WTF_CSRF_ENABLED"] = False
        try:
            with app.test_client() as client:
                with client.session_transaction() as session:
                    session["_user_id"] = str(user_id)
                    session["_fresh"] = True
                return client.post(
                    f"/marketplace-booking/{booking_id}/review",
                    data={"rating": rating, "review_text": review_text},
                )
        finally:
            app.config["WTF_CSRF_ENABLED"] = old_csrf

    def test_only_booking_owner_can_review_completed_work(self):
        booking_id = self.create_booking(
            client_user_id=self.client_one_id, status="Completed"
        )
        response = self.post_review_as(self.client_two_id, booking_id)
        self.assertEqual(response.status_code, 404)

    def test_reviews_require_completed_booking(self):
        booking_id = self.create_booking(
            client_user_id=self.client_one_id, status="Accepted"
        )
        response = self.post_review_as(self.client_one_id, booking_id)
        self.assertEqual(response.status_code, 400)

    def test_completed_booking_accepts_only_one_review(self):
        booking_id = self.create_booking(
            client_user_id=self.client_one_id, status="Completed"
        )
        first = self.post_review_as(self.client_one_id, booking_id, "5", "Excellent")
        second = self.post_review_as(self.client_one_id, booking_id, "4", "Another review")
        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 409)
        with self.connect() as con:
            reviews = con.execute(
                "SELECT COUNT(*) FROM marketplace_reviews WHERE booking_id = ?",
                (booking_id,),
            ).fetchone()[0]
        self.assertEqual(reviews, 1)

    def test_database_rejects_booking_service_owned_by_another_professional(self):
        import sqlite3
        from app import connect


        with self.assertRaises(sqlite3.IntegrityError):
            with connect() as con:
                con.execute(
                    """INSERT INTO marketplace_bookings
                       (service_id, provider_id, client_user_id, requested_date)
                       VALUES (?, ?, ?, ?)""",
                    (self.service_id, self.provider_two_id, self.client_one_id, "2030-01-15"),
                )

    def test_review_rating_must_be_between_one_and_five(self):
        booking_id = self.create_booking(
            client_user_id=self.client_one_id, status="Completed"
        )
        response = self.post_review_as(self.client_one_id, booking_id, "6")
        self.assertEqual(response.status_code, 400)
