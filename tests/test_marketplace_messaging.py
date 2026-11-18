"""Security and access-control regression tests for OneCre8 booking messages."""
import os
import tempfile
import unittest

_STORAGE = tempfile.TemporaryDirectory(prefix="onecre8-messages-")
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = _STORAGE.name
os.environ["SECRET_KEY"] = "onecre8-message-tests-only"

from app import app, connect, detect_message_contact_violation  # noqa: E402


class MarketplaceMessagingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        with connect() as con:
            for name, email, role in (
                ("Message Client", "message-client@example.test", "client"),
                ("Message Pro", "message-pro@example.test", "provider"),
                ("Unrelated User", "message-outsider@example.test", "client"),
            ):
                con.execute(
                    """INSERT INTO users (name, email, password_hash, role, created_at)
                       VALUES (?, ?, 'unused', ?, CURRENT_TIMESTAMP)""",
                    (name, email, role),
                )
            cls.client_id = con.execute(
                "SELECT id FROM users WHERE email='message-client@example.test'"
            ).fetchone()["id"]
            cls.provider_user_id = con.execute(
                "SELECT id FROM users WHERE email='message-pro@example.test'"
            ).fetchone()["id"]
            cls.outsider_id = con.execute(
                "SELECT id FROM users WHERE email='message-outsider@example.test'"
            ).fetchone()["id"]
            con.execute(
                "INSERT INTO providers (user_id, display_name) VALUES (?, ?)",
                (cls.provider_user_id, "Message Pro"),
            )
            cls.provider_id = con.execute(
                "SELECT id FROM providers WHERE user_id = ?", (cls.provider_user_id,)
            ).fetchone()["id"]
            category_id = con.execute("SELECT id FROM categories LIMIT 1").fetchone()["id"]
            con.execute(
                """INSERT INTO services
                   (provider_id, category_id, title, pricing_mode, booking_mode, price)
                   VALUES (?, ?, 'Message Test Service', 'fixed', 'booking', 25000)""",
                (cls.provider_id, category_id),
            )
            cls.service_id = con.execute(
                "SELECT id FROM services WHERE title='Message Test Service'"
            ).fetchone()["id"]
            cursor = con.execute(
                """INSERT INTO marketplace_bookings
                   (service_id, provider_id, client_user_id, requested_date)
                   VALUES (?, ?, ?, '2026-12-01')""",
                (cls.service_id, cls.provider_id, cls.client_id),
            )
            cls.booking_id = cursor.lastrowid
            con.execute(
                "INSERT INTO marketplace_conversations (booking_id) VALUES (?)",
                (cls.booking_id,),
            )

    @classmethod
    def tearDownClass(cls):
        _STORAGE.cleanup()

    def logged_in(self, user_id):
        client = app.test_client()
        with client.session_transaction() as session:
            session["_user_id"] = str(user_id)
            session["_fresh"] = True
        return client

    def test_contact_details_and_external_payment_attempts_are_blocked(self):
        blocked = [
            "Call me on 08012345678",
            "Email me at person@example.com",
            "Find me at https://example.com/profile",
            "My Instagram: @creative_person",
            "Message me on WhatsApp",
            "Please pay outside the platform to my bank account",
        ]
        for message in blocked:
            with self.subTest(message=message):
                self.assertIsNotNone(detect_message_contact_violation(message))

    def test_legitimate_project_details_are_allowed(self):
        allowed = [
            "The shoot is on 2026-12-01 at 10:30am.",
            "My budget is ₦75,000 for 3 edited images.",
            "The frame should measure 60 by 90 cm.",
            "Please deliver 12 edited photographs.",
        ]
        for message in allowed:
            with self.subTest(message=message):
                self.assertIsNone(detect_message_contact_violation(message))

    def test_only_booking_participants_can_view_conversation(self):
        outsider = self.logged_in(self.outsider_id)
        self.assertEqual(
            outsider.get(f"/messages/{self.booking_id}").status_code, 404
        )

    def test_provider_can_view_participating_conversation(self):
        provider = self.logged_in(self.provider_user_id)
        response = provider.get(f"/messages/{self.booking_id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Message Test Service", response.data)

    def test_blocked_message_is_not_saved_and_policy_event_is_logged(self):
        client = self.logged_in(self.client_id)
        response = client.post(
            f"/messages/{self.booking_id}",
            data={"body": "Call me on 08012345678"},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Message not sent", response.data)
        with connect() as con:
            count = con.execute(
                "SELECT COUNT(*) FROM marketplace_messages"
            ).fetchone()[0]
            events = con.execute(
                "SELECT COUNT(*) FROM message_policy_events WHERE booking_id=?",
                (self.booking_id,),
            ).fetchone()[0]
        self.assertEqual(count, 0)
        self.assertEqual(events, 1)

    def test_valid_message_is_stored_and_notifies_other_participant(self):
        client = self.logged_in(self.client_id)
        response = client.post(
            f"/messages/{self.booking_id}",
            data={"body": "I would like 12 edited photos by 2026-12-01."},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        with connect() as con:
            message = con.execute(
                "SELECT body, sender_user_id FROM marketplace_messages"
            ).fetchone()
            notice = con.execute(
                """SELECT COUNT(*) FROM notifications
                   WHERE user_id=? AND notification_type='marketplace_message'""",
                (self.provider_user_id,),
            ).fetchone()[0]
        self.assertEqual(message["body"], "I would like 12 edited photos by 2026-12-01.")
        self.assertEqual(message["sender_user_id"], self.client_id)
        self.assertEqual(notice, 1)


if __name__ == "__main__":
    unittest.main()
