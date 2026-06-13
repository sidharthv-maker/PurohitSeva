"""
Razorpay webhook receiver.

The webhook fires independently of the browser — it's the reliable payment
confirmation channel.  The verify-payment endpoint is the happy-path for the
browser callback; this handler catches everything else (retries, network drops,
etc.) and confirms the booking idempotently.

Setup in Razorpay dashboard:
  URL      : https://your-domain/webhooks/razorpay
  Secret   : set RAZORPAY_WEBHOOK_SECRET in .env to this value
  Events   : payment.captured   (minimum)
"""

import hashlib
import hmac
import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Booking, BookingStatus, Payment

router = APIRouter(prefix="/webhooks", tags=["webhooks"], include_in_schema=False)


@router.post("/razorpay")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Verify the Razorpay webhook signature, then mark the booking confirmed.

    Signature: HMAC-SHA256(raw_body, WEBHOOK_SECRET) — different secret from
    the API key secret; set in the Razorpay dashboard webhook settings.

    Idempotent: if the booking is already confirmed (browser verify-payment
    beat the webhook), we return 200 silently — Razorpay retries otherwise.
    """
    body_bytes = await request.body()
    signature  = request.headers.get("X-Razorpay-Signature", "")

    if not settings.RAZORPAY_WEBHOOK_SECRET:
        # Webhook secret not configured — skip verification in dev if desired,
        # but log loudly so it's not forgotten.
        # In production this path should never be reached.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="RAZORPAY_WEBHOOK_SECRET not configured",
        )

    expected = hmac.new(
        settings.RAZORPAY_WEBHOOK_SECRET.encode("utf-8"),
        body_bytes,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook signature verification failed",
        )

    try:
        payload = json.loads(body_bytes)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event = payload.get("event", "")

    if event == "payment.captured":
        _handle_payment_captured(db, payload)

    # Always return 200 so Razorpay doesn't retry endlessly on unhandled events.
    return {"status": "ok"}


def _handle_payment_captured(db: Session, payload: dict) -> None:
    """Mark the matching booking confirmed when Razorpay confirms capture."""
    try:
        entity            = payload["payload"]["payment"]["entity"]
        razorpay_payment_id = entity["id"]
        order_id          = entity["order_id"]
    except (KeyError, TypeError):
        return  # malformed payload — ignore

    payment = (
        db.query(Payment)
        .filter(Payment.razorpay_order_id == order_id)
        .first()
    )
    if not payment:
        return  # unknown order — ignore

    # Idempotent: skip if already paid
    if payment.status == "paid":
        return

    payment.razorpay_payment_id = razorpay_payment_id
    payment.status              = "paid"

    booking = payment.booking
    if booking and booking.status == BookingStatus.awaiting_payment:
        booking.status = BookingStatus.confirmed

    db.commit()
