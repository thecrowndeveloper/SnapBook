"""Paystack sandbox checkout for accepted, fixed-price marketplace bookings.

Only Paystack test secret keys are accepted. Live payment activation is deliberately
outside this module and requires a separately reviewed launch decision.
"""
import hashlib
import hmac
import os
import re
import time
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

import requests
from flask import Blueprint, abort, current_app, flash, jsonify, redirect, request, url_for
from flask_login import current_user, login_required


def _test_secret_key():
    key = os.environ.get("PAYSTACK_SECRET_KEY", "").strip()
    if not key.startswith("sk_test_"):
        return None
    return key


def _amount_to_kobo(value):
    try:
        amount = (Decimal(str(value)) * 100).quantize(Decimal("1"))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("The service price is invalid.")
    if amount < 5000:
        raise ValueError("Paystack sandbox checkout requires a minimum of ₦50.")
    return int(amount)


def _verify_transaction(reference, secret_key):
    response = requests.get(
        "https://api.paystack.co/transaction/verify/" + quote(reference, safe=""),
        headers={"Authorization": "Bearer " + secret_key},
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("status") or not isinstance(payload.get("data"), dict):
        raise ValueError("Paystack could not verify this transaction.")
    return payload["data"]


def _valid_webhook_signature(raw_body, headers, secret_key):
    modern = headers.get("Paystack-Signature", "")
    if modern:
        webhook_secret = os.environ.get("PAYSTACK_WEBHOOK_SECRET", "").strip()
        if not webhook_secret.startswith("whsec_"):
            return False
        timestamp = None
        signatures = []
        for part in modern.split(","):
            key, separator, value = part.strip().partition("=")
            if not separator:
                continue
            if key == "t":
                timestamp = value
            elif key == "v1":
                key_id, colon, signature = value.partition(":")
                if colon and key_id.startswith("whk_"):
                    signatures.append(signature)
        if not timestamp or not timestamp.isdigit():
            return False
        if abs(int(time.time()) - int(timestamp)) > 300:
            return False
        expected = hmac.new(
            webhook_secret.encode("utf-8"),
            timestamp.encode("ascii") + b"." + raw_body,
            hashlib.sha512,
        ).hexdigest()
        return any(
            re.fullmatch(r"[0-9a-f]{128}", signature or "")
            and hmac.compare_digest(expected, signature)
            for signature in signatures
        )

    legacy = headers.get("x-paystack-signature", "")
    if not re.fullmatch(r"[0-9a-f]{128}", legacy or ""):
        return False
    expected = hmac.new(
        secret_key.encode("utf-8"), raw_body, hashlib.sha512
    ).hexdigest()
    return hmac.compare_digest(expected, legacy)


def create_payment_blueprint(connect, csrf_protect=None):
    payments = Blueprint("payments", __name__)

    def exempt_webhook(view):
        return csrf_protect.exempt(view) if csrf_protect is not None else view

    def verified_payment_matches(payment, verified):
        return (
            verified.get("reference") == payment["reference"]
            and verified.get("amount") == payment["amount_kobo"]
            and verified.get("currency") == "NGN"
            and verified.get("domain") == "test"
        )

    def record_verified_failure(payment, verified):
        if verified.get("status") not in ("failed", "abandoned", "reversed"):
            return False
        if not verified_payment_matches(payment, verified):
            return False
        with connect() as con:
            con.execute("BEGIN IMMEDIATE")
            con.execute(
                """UPDATE marketplace_payments SET status = 'failed'
                   WHERE id = ? AND status = 'pending'""",
                (payment["id"],),
            )
        return True

    def record_verified_success(payment, verified):
        if (
            verified.get("status") != "success"
            or not verified_payment_matches(payment, verified)
        ):
            return False

        metadata = verified.get("metadata") or {}
        if isinstance(metadata, dict) and metadata.get("booking_id") not in (
            None, str(payment["booking_id"]), payment["booking_id"]
        ):
            return False

        with connect() as con:
            con.execute("BEGIN IMMEDIATE")
            current = con.execute(
                "SELECT * FROM marketplace_payments WHERE id = ?",
                (payment["id"],),
            ).fetchone()
            if not current:
                return False
            if current["status"] == "success":
                return True
            if current["status"] != "pending":
                return False
            con.execute(
                """UPDATE marketplace_payments
                   SET status = 'success', paystack_transaction_id = ?,
                       paid_at = CURRENT_TIMESTAMP
                   WHERE id = ? AND status = 'pending'""",
                (str(verified.get("id", "")), payment["id"]),
            )
            return True

    @payments.post("/marketplace-booking/<int:booking_id>/pay")
    @login_required
    def start_marketplace_payment(booking_id):
        if current_user.role != "client":
            abort(403)
        secret_key = _test_secret_key()
        if not secret_key:
            abort(503, description="Paystack sandbox is not configured.")

        with connect() as con:
            con.execute("BEGIN IMMEDIATE")
            booking = con.execute(
                """SELECT b.*, s.title AS service_title, s.price,
                          s.pricing_mode, s.booking_mode, u.email AS client_email
                   FROM marketplace_bookings b
                   JOIN services s ON s.id = b.service_id
                   JOIN users u ON u.id = b.client_user_id
                   WHERE b.id = ? AND b.client_user_id = ?""",
                (booking_id, current_user.id),
            ).fetchone()
            if not booking:
                abort(404)
            if (
                booking["status"] != "Accepted"
                or booking["pricing_mode"] != "fixed"
                or booking["booking_mode"] != "booking"
            ):
                abort(409, description="Only accepted, fixed-price bookings can be paid.")
            try:
                amount_kobo = _amount_to_kobo(booking["price"])
            except ValueError:
                abort(400, description="The service price is not valid for checkout.")

            successful_payment = con.execute(
                """SELECT id FROM marketplace_payments
                   WHERE booking_id = ? AND status = 'success' LIMIT 1""",
                (booking_id,),
            ).fetchone()
            if successful_payment:
                abort(409, description="This booking has already been paid.")
            pending_payment = con.execute(
                """SELECT id FROM marketplace_payments
                   WHERE booking_id = ? AND status = 'pending' LIMIT 1""",
                (booking_id,),
            ).fetchone()
            if pending_payment:
                abort(409, description="A payment attempt is already pending for this booking.")
            reference = "ocm-" + os.urandom(16).hex()
            con.execute(
                """INSERT INTO marketplace_payments
                   (booking_id, client_user_id, reference, amount_kobo, currency, status)
                   VALUES (?, ?, ?, ?, 'NGN', 'pending')""",
                (booking_id, current_user.id, reference, amount_kobo),
            )
            payment_id = con.execute(
                "SELECT id FROM marketplace_payments WHERE reference = ?",
                (reference,),
            ).fetchone()["id"]

        try:
            response = requests.post(
                "https://api.paystack.co/transaction/initialize",
                headers={"Authorization": "Bearer " + secret_key},
                json={
                    "email": booking["client_email"],
                    "amount": str(amount_kobo),
                    "currency": "NGN",
                    "reference": reference,
                    "callback_url": url_for(
                        "payments.paystack_callback", _external=True
                    ),
                    "metadata": {
                        "booking_id": booking_id,
                        "payment_id": payment_id,
                        "platform": "OneCre8 Media",
                    },
                },
                timeout=15,
            )
            response.raise_for_status()
            payload = response.json()
            checkout_url = (payload.get("data") or {}).get("authorization_url")
            if not payload.get("status") or not checkout_url:
                raise ValueError("Paystack did not return a checkout link.")
        except (requests.RequestException, ValueError):
            current_app.logger.exception("Paystack sandbox checkout initialization failed.")
            with connect() as con:
                con.execute(
                    """UPDATE marketplace_payments SET status = 'failed'
                       WHERE id = ? AND status = 'pending'""",
                    (payment_id,),
                )
            flash("We could not start the sandbox payment. Please try again.", "error")
            return redirect(url_for("my_bookings"))

        return redirect(checkout_url)

    @payments.get("/payments/paystack/callback")
    @login_required
    def paystack_callback():
        reference = request.args.get("reference", "").strip()
        if not reference or len(reference) > 100:
            abort(400)
        secret_key = _test_secret_key()
        if not secret_key:
            abort(503, description="Paystack sandbox is not configured.")

        with connect() as con:
            payment = con.execute(
                """SELECT * FROM marketplace_payments
                   WHERE reference = ? AND client_user_id = ?""",
                (reference, current_user.id),
            ).fetchone()
        if not payment:
            abort(404)

        try:
            verified = _verify_transaction(reference, secret_key)
        except (requests.RequestException, ValueError):
            current_app.logger.exception("Paystack callback verification failed.")
            flash("We could not confirm the payment yet. Please check your bookings again.", "error")
            return redirect(url_for("my_bookings"))

        if record_verified_success(payment, verified):
            flash("Sandbox payment verified successfully. No real money was collected.", "success")
        elif record_verified_failure(payment, verified):
            flash("The sandbox payment did not complete. You can try again.", "error")
        else:
            flash("The payment has not been verified as successful. Your booking remains unpaid.", "error")
        return redirect(url_for("my_bookings"))

    @payments.post("/payments/paystack/webhook")
    @exempt_webhook
    def paystack_webhook():
        secret_key = _test_secret_key()
        if not secret_key:
            abort(503)
        raw_body = request.get_data(cache=True)
        if not _valid_webhook_signature(raw_body, request.headers, secret_key):
            abort(401)

        event = request.get_json(silent=True) or {}
        if event.get("event") != "charge.success":
            return jsonify({"received": True}), 200

        data = event.get("data") or {}
        reference = data.get("reference")
        if not isinstance(reference, str) or not reference:
            return jsonify({"received": True}), 200

        with connect() as con:
            payment = con.execute(
                "SELECT * FROM marketplace_payments WHERE reference = ?",
                (reference,),
            ).fetchone()
        if not payment or payment["status"] == "success":
            return jsonify({"received": True}), 200

        try:
            verified = _verify_transaction(reference, secret_key)
        except (requests.RequestException, ValueError):
            current_app.logger.exception("Paystack webhook transaction verification failed.")
            return jsonify({"received": False}), 503

        record_verified_success(payment, verified)
        return jsonify({"received": True}), 200

    return payments
