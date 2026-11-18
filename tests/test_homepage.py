"""Small, dependency-free regression checks for the public marketplace entry points."""

import os
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
