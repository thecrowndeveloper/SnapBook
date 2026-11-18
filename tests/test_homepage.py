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
