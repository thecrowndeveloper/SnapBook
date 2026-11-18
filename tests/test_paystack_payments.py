"""Regression tests for the Paystack sandbox payment workflow."""
import hashlib
import hmac
import json
import os
import tempfile
import unittest
from unittest.mock import Mock, patch

_TEST_STORAGE = tempfile.TemporaryDirectory(prefix="onecre8-payments-")
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = _TEST_STORAGE.name
os.environ["SECRET_KEY"] = "onecre8-payment-tests-only"

from app import app, connect  # noqa: E402
from paystack_payments import (  # noqa: E402
    _amount_to_kobo,
    _test_secret_key,
    _valid_webhook_signature,
)


class PaystackSandboxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        cls.client = app.test_client()
        with connect() as con:
            con.execute(
                """INSERT INTO users
                   (name, email, password_hash, role, created_at)
                   VALUES (?, ?, ?, 'client', CURRENT_TIMESTAMP)""",
                ("Sandbox Client", "paystack-client@example.test", "unused"),
            )
            cls.client_id = con.execute(
                "SELECT id FROM users WHERE email = ?",
                ("paystack-client@example.test",),
            ).fetchone()["id"]
            con.execute(
                """INSERT INTO users
                   (name, email, password_hash, role, created_at)
                   VALUES (?, ?, ?, 'provider', CURRENT_TIMESTAMP)""",
                ("Sandbox Professional", "paystack-pro@example.test", "unused"),
            )
            cls.provider_user_id = con.execute(
                "SELECT id FROM users WHERE email = ?",
                ("paystack-pro@example.test",),
            ).fetchone()["id"]
            con.execute(
                "INSERT INTO providers (user_id, display_name) VALUES (?, ?)",
                (cls.provider_user_id, "Sandbox Professional"),
            )
            cls.provider_id = con.execute(
                "SELECT id FROM providers WHERE user_id = ?",
                (cls.provider_user_id,),
            ).fetchone()["id"]
            category_id = con.execute(
                "SELECT id FROM categories ORDER BY id LIMIT 1"
            ).fetchone()["id"]
            con.execute(
                """INSERT INTO services
                   (provider_id, category_id, title, pricing_mode, booking_mode, price)
                   VALUES (?, ?, ?, 'fixed', 'booking', ?)""",
                (cls.provider_id, category_id, "Sandbox Portrait Session", 75000),
            )
            cls.service_id = con.execute(
                "SELECT id FROM services WHERE title = ?",
                ("Sandbox Portrait Session",),
            ).fetchone()["id"]

    def setUp(self):
        with connect() as con:
            cursor = con.execute(
                """INSERT INTO marketplace_bookings
                   (service_id, provider_id, client_user_id, requested_date, status)
                   VALUES (?, ?, ?, ?, 'Accepted')""",
                (self.service_id, self.provider_id, self.client_id, "2030-06-01"),
            )
            self.booking_id = cursor.lastrowid
        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session["_user_id"] = str(self.client_id)
            session["_fresh"] = True

    @classmethod
    def tearDownClass(cls):
        _TEST_STORAGE.cleanup()

    def _verified_payload(self, reference, amount=7500000, domain="test"):
        return {
            "status": "success",
            "reference": reference,
            "amount": amount,
            "currency": "NGN",
            "domain": domain,
            "id": 123456789 + sum(reference.encode("utf-8")),
            "metadata": {"booking_id": self.booking_id},
        }

    def test_amount_is_converted_to_kobo_and_rejects_below_paystack_minimum(self):
        self.assertEqual(_amount_to_kobo("75000.00"), 7500000)
        with self.assertRaises(ValueError):
            _amount_to_kobo("49.99")

    def test_only_test_secret_key_is_accepted(self):
        with patch.dict(os.environ, {"PAYSTACK_SECRET_KEY": "sk_test_demo"}):
            self.assertEqual(_test_secret_key(), "sk_test_demo")
        with patch.dict(os.environ, {"PAYSTACK_SECRET_KEY": "sk_live_never"}):
            self.assertIsNone(_test_secret_key())

    def test_webhook_signature_uses_raw_body_and_timestamp(self):
        raw = b'{"event":"charge.success","data":{"reference":"ocm-test"}}'
        secret = "whsec_example"
        timestamp = "1760270400"
        signature = hmac.new(
            secret.encode(), timestamp.encode() + b"." + raw, hashlib.sha512
        ).hexdigest()
        headers = {"Paystack-Signature": f"t={timestamp},v1=whk_demo:{signature}"}
        with patch("paystack_payments.time.time", return_value=1760270400):
            with patch.dict(os.environ, {"PAYSTACK_WEBHOOK_SECRET": secret}):
                self.assertTrue(_valid_webhook_signature(raw, headers, "sk_test_demo"))
                self.assertFalse(_valid_webhook_signature(raw + b" ", headers, "sk_test_demo"))

    def test_non_client_cannot_start_checkout(self):
        provider_client = app.test_client()
        with provider_client.session_transaction() as session:
            session["_user_id"] = str(self.provider_user_id)
            session["_fresh"] = True
        with patch.dict(os.environ, {"PAYSTACK_SECRET_KEY": "sk_test_demo"}):
            response = provider_client.post(
                f"/marketplace-booking/{self.booking_id}/pay"
            )
        self.assertEqual(response.status_code, 403)

    def test_checkout_initializes_server_calculated_ngn_amount(self):
        fake = Mock()
        fake.raise_for_status.return_value = None
        fake.json.return_value = {
            "status": True,
            "data": {"authorization_url": "https://checkout.paystack.test/example"},
        }
        with patch.dict(os.environ, {"PAYSTACK_SECRET_KEY": "sk_test_demo"}):
            with patch("paystack_payments.requests.post", return_value=fake) as post:
                response = self.client.post(
                    f"/marketplace-booking/{self.booking_id}/pay"
                )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "https://checkout.paystack.test/example")
        sent = post.call_args.kwargs["json"]
        self.assertEqual(sent["amount"], "7500000")
        self.assertEqual(sent["currency"], "NGN")
        self.assertEqual(sent["metadata"]["booking_id"], self.booking_id)
        with connect() as con:
            payment = con.execute(
                "SELECT * FROM marketplace_payments WHERE booking_id = ?",
                (self.booking_id,),
            ).fetchone()
        self.assertEqual(payment["status"], "pending")
        self.reference = payment["reference"]

    def test_checkout_rejects_unaccepted_booking(self):
        with connect() as con:
            con.execute(
                "UPDATE marketplace_bookings SET status = 'Requested' WHERE id = ?",
                (self.booking_id,),
            )
        with patch.dict(os.environ, {"PAYSTACK_SECRET_KEY": "sk_test_demo"}):
            response = self.client.post(
                f"/marketplace-booking/{self.booking_id}/pay"
            )
        self.assertEqual(response.status_code, 409)

    def test_callback_verifies_amount_currency_and_test_domain_before_success(self):
        with connect() as con:
            con.execute(
                """INSERT INTO marketplace_payments
                   (booking_id, client_user_id, reference, amount_kobo, currency, status)
                   VALUES (?, ?, ?, 7500000, 'NGN', 'pending')""",
                (self.booking_id, self.client_id, "ocm-callback-test"),
            )
        verified = self._verified_payload("ocm-callback-test")
        fake = Mock()
        fake.raise_for_status.return_value = None
        fake.json.return_value = {"status": True, "data": verified}
        with patch.dict(os.environ, {"PAYSTACK_SECRET_KEY": "sk_test_demo"}):
            with patch("paystack_payments.requests.get", return_value=fake):
                response = self.client.get(
                    "/payments/paystack/callback?reference=ocm-callback-test"
                )
        self.assertEqual(response.status_code, 302)
        with connect() as con:
            payment = con.execute(
                "SELECT status FROM marketplace_payments WHERE reference = ?",
                ("ocm-callback-test",),
            ).fetchone()
        self.assertEqual(payment["status"], "success")

    def test_live_domain_transaction_cannot_mark_payment_successful(self):
        with connect() as con:
            con.execute(
                """INSERT INTO marketplace_payments
                   (booking_id, client_user_id, reference, amount_kobo, currency, status)
                   VALUES (?, ?, ?, 7500000, 'NGN', 'pending')""",
                (self.booking_id, self.client_id, "ocm-live-domain"),
            )
        fake = Mock()
        fake.raise_for_status.return_value = None
        fake.json.return_value = {
            "status": True,
            "data": self._verified_payload("ocm-live-domain", domain="live"),
        }
        with patch.dict(os.environ, {"PAYSTACK_SECRET_KEY": "sk_test_demo"}):
            with patch("paystack_payments.requests.get", return_value=fake):
                self.client.get("/payments/paystack/callback?reference=ocm-live-domain")
        with connect() as con:
            payment = con.execute(
                "SELECT status FROM marketplace_payments WHERE reference = ?",
                ("ocm-live-domain",),
            ).fetchone()
        self.assertEqual(payment["status"], "pending")

    def test_webhook_is_idempotent_and_verifies_with_paystack(self):
        with connect() as con:
            con.execute(
                """INSERT INTO marketplace_payments
                   (booking_id, client_user_id, reference, amount_kobo, currency, status)
                   VALUES (?, ?, ?, 7500000, 'NGN', 'pending')""",
                (self.booking_id, self.client_id, "ocm-webhook-test"),
            )
        body = json.dumps({
            "event": "charge.success",
            "data": {"reference": "ocm-webhook-test"},
        }, separators=(",", ":")).encode()
        secret = "whsec_example"
        timestamp = "1760270400"
        signature = hmac.new(
            secret.encode(), timestamp.encode() + b"." + body, hashlib.sha512
        ).hexdigest()
        headers = {
            "Paystack-Signature": f"t={timestamp},v1=whk_demo:{signature}",
            "Content-Type": "application/json",
        }
        fake = Mock()
        fake.raise_for_status.return_value = None
        fake.json.return_value = {
            "status": True,
            "data": self._verified_payload("ocm-webhook-test"),
        }
        with patch("paystack_payments.time.time", return_value=1760270400):
            with patch.dict(os.environ, {
                "PAYSTACK_SECRET_KEY": "sk_test_demo",
                "PAYSTACK_WEBHOOK_SECRET": secret,
            }):
                with patch("paystack_payments.requests.get", return_value=fake) as get:
                    first = self.client.post(
                        "/payments/paystack/webhook", data=body, headers=headers
                    )
                    second = self.client.post(
                        "/payments/paystack/webhook", data=body, headers=headers
                    )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(get.call_count, 1)
        with connect() as con:
            payment = con.execute(
                "SELECT status FROM marketplace_payments WHERE reference = ?",
                ("ocm-webhook-test",),
            ).fetchone()
        self.assertEqual(payment["status"], "success")


if __name__ == "__main__":
    unittest.main()
