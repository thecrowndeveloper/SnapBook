"""Security and access-control regression tests for OneCre8 booking messages."""
import os
import tempfile
import unittest
from io import BytesIO

from PIL import Image

_STORAGE = tempfile.TemporaryDirectory(prefix="onecre8-messages-")
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = _STORAGE.name
os.environ["SECRET_KEY"] = "onecre8-message-tests-only"

from app import app, connect, detect_message_contact_violation, MESSAGE_ATTACHMENT_FOLDER  # noqa: E402


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
                """INSERT INTO users (name, email, password_hash, role, created_at)
                   VALUES ('OneCre8 Moderator', 'message-moderator@example.test',
                           'unused', 'client', CURRENT_TIMESTAMP)"""
            )
            cls.moderator_id = con.execute(
                "SELECT id FROM users WHERE email='message-moderator@example.test'"
            ).fetchone()["id"]
            os.environ["ONECRE8_MODERATOR_USER_IDS"] = str(cls.moderator_id)
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
            "Email me at person@\u200bexample.com",
            "Call me on 080\u200b12345678",
            "My email is person@example\u00ad.com",
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
        with connect() as con:
            previous_messages = con.execute(
                "SELECT COUNT(*) FROM marketplace_messages"
            ).fetchone()[0]
            previous_events = con.execute(
                "SELECT COUNT(*) FROM message_policy_events WHERE booking_id=?",
                (self.booking_id,),
            ).fetchone()[0]
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
        self.assertEqual(count, previous_messages)
        self.assertEqual(events, previous_events + 1)


    def make_png(self):
        image = Image.new("RGB", (32, 24), "white")
        stream = BytesIO()
        image.save(stream, format="PNG")
        stream.seek(0)
        return stream

    def test_valid_image_is_reencoded_and_only_participants_can_download(self):
        client = self.logged_in(self.client_id)
        response = client.post(
            f"/messages/{self.booking_id}",
            data={
                "body": "Here is the reference image for the project.",
                "attachment": (self.make_png(), "reference.png"),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        with connect() as con:
            attachment = con.execute(
                "SELECT id, filename, file_size FROM marketplace_message_attachments"
            ).fetchone()
        self.assertTrue(attachment["filename"].endswith(".webp"))
        self.assertGreater(attachment["file_size"], 0)
        self.assertTrue((MESSAGE_ATTACHMENT_FOLDER / attachment["filename"]).is_file())
        self.assertEqual(
            client.get(f"/messages/attachments/{attachment['id']}").status_code, 200
        )
        outsider = self.logged_in(self.outsider_id)
        self.assertEqual(
            outsider.get(f"/messages/attachments/{attachment['id']}").status_code,
            404,
        )

    def test_invalid_file_type_is_rejected_without_storing_attachment(self):
        client = self.logged_in(self.client_id)
        response = client.post(
            f"/messages/{self.booking_id}",
            data={
                "body": "Please see this file.",
                "attachment": (BytesIO(b"not an image"), "malware.svg"),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Only JPG, PNG or WEBP", response.data)
        with connect() as con:
            count = con.execute(
                "SELECT COUNT(*) FROM marketplace_message_attachments"
            ).fetchone()[0]
        self.assertEqual(count, 0)


    def test_participant_can_report_and_moderator_can_apply_temporary_restriction(self):
        with connect() as con:
            conversation_id = con.execute(
                "SELECT id FROM marketplace_conversations WHERE booking_id=?",
                (self.booking_id,),
            ).fetchone()["id"]
            cursor = con.execute(
                """INSERT INTO marketplace_messages (conversation_id, sender_user_id, body)
                   VALUES (?, ?, ?)""",
                (conversation_id, self.provider_user_id, "Please contact me outside the platform."),
            )
            message_id = cursor.lastrowid

        client = self.logged_in(self.client_id)
        response = client.post(
            f"/messages/{self.booking_id}/report/{message_id}",
            data={"reason": "contact_exchange", "details": "Attempts to move the conversation off-platform."},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        with connect() as con:
            report = con.execute(
                "SELECT id, status FROM marketplace_message_reports WHERE message_id=?",
                (message_id,),
            ).fetchone()
        self.assertEqual(report["status"], "open")

        moderator = self.logged_in(self.moderator_id)
        queue = moderator.get("/moderation/messages")
        self.assertEqual(queue.status_code, 200)
        self.assertIn(b"Message reports", queue.data)
        decision = moderator.post(
            f"/moderation/messages/{report['id']}",
            data={"action": "restrict_24h", "note": "Reviewed report; temporary messaging restriction."},
            follow_redirects=True,
        )
        self.assertEqual(decision.status_code, 200)
        with connect() as con:
            status = con.execute(
                "SELECT status FROM marketplace_message_reports WHERE id=?",
                (report["id"],),
            ).fetchone()["status"]
            restriction = con.execute(
                "SELECT user_id, active FROM marketplace_messaging_restrictions WHERE report_id=?",
                (report["id"],),
            ).fetchone()
        self.assertEqual(status, "actioned")
        self.assertEqual(restriction["user_id"], self.provider_user_id)
        self.assertEqual(restriction["active"], 1)

        provider = self.logged_in(self.provider_user_id)
        blocked = provider.post(
            f"/messages/{self.booking_id}",
            data={"body": "A new project message."},
            follow_redirects=True,
        )
        self.assertIn(b"Messaging is temporarily restricted", blocked.data)

    def test_non_moderator_cannot_open_moderation_queue(self):
        outsider = self.logged_in(self.outsider_id)
        self.assertEqual(outsider.get("/moderation/messages").status_code, 404)

    def make_restriction(self):
        with connect() as con:
            # Keep each test isolated from any prior restriction on this account.
            con.execute(
                "UPDATE marketplace_messaging_restrictions SET active=0 WHERE user_id=?",
                (self.provider_user_id,),
            )
            conversation_id = con.execute(
                "SELECT id FROM marketplace_conversations WHERE booking_id=?",
                (self.booking_id,),
            ).fetchone()["id"]
            message = con.execute(
                """INSERT INTO marketplace_messages (conversation_id, sender_user_id, body)
                   VALUES (?, ?, ?)""",
                (conversation_id, self.provider_user_id, "A report for appeal testing."),
            )
            report = con.execute(
                """INSERT INTO marketplace_message_reports
                   (booking_id, message_id, reporter_user_id, reported_user_id, reason)
                   VALUES (?, ?, ?, ?, 'other')""",
                (self.booking_id, message.lastrowid, self.client_id, self.provider_user_id),
            )
            restriction = con.execute(
                """INSERT INTO marketplace_messaging_restrictions
                   (user_id, report_id, moderator_user_id, reason, ends_at)
                   VALUES (?, ?, ?, 'Test restriction', datetime('now', '+1 day'))""",
                (self.provider_user_id, report.lastrowid, self.moderator_id),
            )
            return restriction.lastrowid

    def test_restriction_appeal_is_private_unique_and_can_lift_restriction(self):
        restriction_id = self.make_restriction()
        provider = self.logged_in(self.provider_user_id)
        conversation = provider.get(f"/messages/{self.booking_id}")
        self.assertEqual(conversation.status_code, 200)
        self.assertIn(b"Submit review request", conversation.data)
        self.assertNotIn(b'class="message-compose"', conversation.data)
        self.assertIn(b"messaging is unavailable while your restriction is active", conversation.data.lower())

        outsider = self.logged_in(self.outsider_id)
        denied = outsider.post(
            f"/messages/restrictions/{restriction_id}/appeal",
            data={"appeal_text": "I would like this restriction reviewed, please."},
        )
        self.assertEqual(denied.status_code, 404)

        appeal_data = {"appeal_text": "I believe this restriction was applied in error. Please review the conversation context."}
        submitted = provider.post(
            f"/messages/restrictions/{restriction_id}/appeal",
            data=appeal_data,
            follow_redirects=True,
        )
        self.assertEqual(submitted.status_code, 200)
        self.assertIn(b"review request has been submitted", submitted.data.lower())
        duplicate = provider.post(
            f"/messages/restrictions/{restriction_id}/appeal",
            data=appeal_data,
            follow_redirects=True,
        )
        self.assertIn(b"already been submitted", duplicate.data)

        with connect() as con:
            appeal = con.execute(
                "SELECT id, status FROM marketplace_messaging_appeals WHERE restriction_id=?",
                (restriction_id,),
            ).fetchone()
        self.assertEqual(appeal["status"], "open")

        outsider_queue = outsider.get("/moderation/appeals")
        self.assertEqual(outsider_queue.status_code, 404)
        moderator = self.logged_in(self.moderator_id)
        queue = moderator.get("/moderation/appeals")
        self.assertEqual(queue.status_code, 200)
        self.assertIn(b"Messaging restriction appeals", queue.data)

        decision = moderator.post(
            f"/moderation/appeals/{appeal['id']}",
            data={"action": "lift", "note": "Reviewed the context; restriction lifted."},
            follow_redirects=True,
        )
        self.assertEqual(decision.status_code, 200)
        with connect() as con:
            status = con.execute(
                "SELECT status FROM marketplace_messaging_appeals WHERE id=?",
                (appeal["id"],),
            ).fetchone()["status"]
            active = con.execute(
                "SELECT active FROM marketplace_messaging_restrictions WHERE id=?",
                (restriction_id,),
            ).fetchone()["active"]
        self.assertEqual(status, "lifted")
        self.assertEqual(active, 0)

        sent = provider.post(
            f"/messages/{self.booking_id}",
            data={"body": "I can now continue discussing the project."},
            follow_redirects=True,
        )
        self.assertIn(b"Message sent", sent.data)

    def test_appeal_must_have_minimum_explanation(self):
        restriction_id = self.make_restriction()
        provider = self.logged_in(self.provider_user_id)
        response = provider.post(
            f"/messages/restrictions/{restriction_id}/appeal",
            data={"appeal_text": "Too short"},
            follow_redirects=True,
        )
        self.assertIn(b"20 to 1,000 characters", response.data)
        with connect() as con:
            count = con.execute(
                "SELECT COUNT(*) FROM marketplace_messaging_appeals WHERE restriction_id=?",
                (restriction_id,),
            ).fetchone()[0]
        self.assertEqual(count, 0)

    def test_valid_message_is_stored_and_notifies_other_participant(self):
        client = self.logged_in(self.client_id)
        with connect() as con:
            previous_notices = con.execute(
                """SELECT COUNT(*) FROM notifications
                   WHERE user_id=? AND notification_type='marketplace_message'""",
                (self.provider_user_id,),
            ).fetchone()[0]
        response = client.post(
            f"/messages/{self.booking_id}",
            data={"body": "I would like 12 edited photos by 2026-12-01."},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        with connect() as con:
            message = con.execute(
                "SELECT body, sender_user_id FROM marketplace_messages ORDER BY id DESC LIMIT 1"
            ).fetchone()
            notice = con.execute(
                """SELECT COUNT(*) FROM notifications
                   WHERE user_id=? AND notification_type='marketplace_message'""",
                (self.provider_user_id,),
            ).fetchone()[0]
        self.assertEqual(message["body"], "I would like 12 edited photos by 2026-12-01.")
        self.assertEqual(message["sender_user_id"], self.client_id)
        self.assertEqual(notice, previous_notices + 1)


if __name__ == "__main__":
    unittest.main()
