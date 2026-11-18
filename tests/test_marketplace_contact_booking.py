"""Regression tests for OneCre8 pre-booking contact and session requests."""
import os
import tempfile
import unittest
from datetime import date, timedelta

_STORAGE = tempfile.TemporaryDirectory(prefix="onecre8-contact-booking-")
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = _STORAGE.name
os.environ["SECRET_KEY"] = "onecre8-contact-booking-tests-only"

from app import app, connect  # noqa: E402


class ContactAndBookingFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        with connect() as con:
            con.execute(
                """INSERT INTO users (name, email, password_hash, role, created_at)
                   VALUES ('Flow Client', 'flow-client@example.test', 'unused', 'client', CURRENT_TIMESTAMP)"""
            )
            cls.client_id = con.execute(
                "SELECT id FROM users WHERE email='flow-client@example.test'"
            ).fetchone()["id"]
            con.execute(
                """INSERT INTO users (name, email, password_hash, role, created_at)
                   VALUES ('Flow Professional', 'flow-pro@example.test', 'unused', 'provider', CURRENT_TIMESTAMP)"""
            )
            cls.provider_user_id = con.execute(
                "SELECT id FROM users WHERE email='flow-pro@example.test'"
            ).fetchone()["id"]
            con.execute(
                "INSERT INTO providers (user_id, display_name, city) VALUES (?, 'Flow Professional', 'Abuja')",
                (cls.provider_user_id,),
            )
            cls.provider_id = con.execute(
                "SELECT id FROM providers WHERE user_id=?", (cls.provider_user_id,)
            ).fetchone()["id"]
            cls.category_id = con.execute(
                "SELECT id FROM categories ORDER BY id LIMIT 1"
            ).fetchone()["id"]
            con.execute(
                """INSERT INTO services
                   (provider_id, category_id, title, description, pricing_mode, booking_mode, price)
                   VALUES (?, ?, 'Portrait Session', 'Studio portrait session', 'fixed', 'booking', 50000)""",
                (cls.provider_id, cls.category_id),
            )
            cls.booking_service_id = con.execute(
                "SELECT id FROM services WHERE title='Portrait Session'"
            ).fetchone()["id"]
            con.execute(
                """INSERT INTO services
                   (provider_id, category_id, title, description, pricing_mode, booking_mode)
                   VALUES (?, ?, 'Creative Consultation', 'Discuss a project', 'quote', 'enquiry')""",
                (cls.provider_id, cls.category_id),
            )
            cls.enquiry_service_id = con.execute(
                "SELECT id FROM services WHERE title='Creative Consultation'"
            ).fetchone()["id"]

    def logged_in(self, user_id):
        client = app.test_client()
        with client.session_transaction() as session:
            session["_user_id"] = str(user_id)
            session["_fresh"] = True
        return client

    def test_public_profile_exposes_contact_and_service_actions(self):
        response = app.test_client().get(f"/provider/{self.provider_id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Message professional", response.data)
        self.assertIn(b"Book this service", response.data)

    def test_client_can_start_prebooking_enquiry_and_professional_can_reply(self):
        client = self.logged_in(self.client_id)
        response = client.post(
            f"/provider/{self.provider_id}/contact",
            data={
                "service_id": str(self.enquiry_service_id),
                "body": "I would like to discuss a creative project.",
            },
        )
        self.assertEqual(response.status_code, 302)
        with connect() as con:
            booking = con.execute(
                """SELECT id, request_type, requested_date
                   FROM marketplace_bookings
                   WHERE client_user_id=? AND service_id=?""",
                (self.client_id, self.enquiry_service_id),
            ).fetchone()
            message = con.execute(
                """SELECT body FROM marketplace_messages
                   WHERE conversation_id=(SELECT id FROM marketplace_conversations WHERE booking_id=?)""",
                (booking["id"],),
            ).fetchone()
        self.assertEqual(booking["request_type"], "enquiry")
        self.assertEqual(booking["requested_date"], "")
        self.assertEqual(message["body"], "I would like to discuss a creative project.")

        professional = self.logged_in(self.provider_user_id)
        reply = professional.post(
            f"/messages/{booking['id']}",
            data={"body": "Thank you. Tell me more about the project."},
            follow_redirects=True,
        )
        self.assertEqual(reply.status_code, 200)
        self.assertIn(b"Message sent", reply.data)

    def test_booking_request_saves_requested_session_details(self):
        client = self.logged_in(self.client_id)
        requested_date = (date.today() + timedelta(days=7)).isoformat()
        response = client.post(
            f"/service/{self.booking_service_id}/request",
            data={
                "requested_date": requested_date,
                "requested_time": "10:30",
                "duration_minutes": "120",
                "session_count": "2",
                "participants": "3",
                "location": "Wuse 2, Abuja",
                "client_message": "Two portrait sessions for our team.",
            },
        )
        self.assertEqual(response.status_code, 302)
        with connect() as con:
            booking = con.execute(
                """SELECT requested_date, requested_time, duration_minutes,
                          session_count, participants, location, request_type
                   FROM marketplace_bookings
                   WHERE client_user_id=? AND service_id=?""",
                (self.client_id, self.booking_service_id),
            ).fetchone()
        self.assertEqual(booking["requested_date"], requested_date)
        self.assertEqual(booking["requested_time"], "10:30")
        self.assertEqual(booking["duration_minutes"], 120)
        self.assertEqual(booking["session_count"], 2)
        self.assertEqual(booking["participants"], 3)
        self.assertEqual(booking["location"], "Wuse 2, Abuja")
        self.assertEqual(booking["request_type"], "booking")

    def test_booking_service_requires_date_and_rejects_invalid_session_counts(self):
        client = self.logged_in(self.client_id)
        missing_date = client.post(
            f"/service/{self.booking_service_id}/request",
            data={"duration_minutes": "60", "session_count": "1", "participants": "1"},
            follow_redirects=True,
        )
        self.assertIn(b"Please select your preferred service date", missing_date.data)
        invalid_count = client.post(
            f"/service/{self.booking_service_id}/request",
            data={
                "requested_date": (date.today() + timedelta(days=7)).isoformat(),
                "duration_minutes": "60",
                "session_count": "99",
                "participants": "1",
            },
            follow_redirects=True,
        )
        self.assertIn(b"Choose a session duration", invalid_count.data)

    def test_only_clients_can_start_professional_enquiries(self):
        professional = self.logged_in(self.provider_user_id)
        response = professional.get(f"/provider/{self.provider_id}/contact")
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
