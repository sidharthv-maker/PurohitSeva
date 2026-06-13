"""
Booking lifecycle:
  pending → awaiting_payment → confirmed → completed
                             ↘ expired  (payment window elapsed)
         ↘ declined
         ↘ cancelled  (user cancels; slots freed if confirmed)

Design notes
────────────
• Slot locking happens at ACCEPT time (not booking-request time).
  The UNIQUE constraint on booking_slots is the atomic guard — the second
  conflicting INSERT raises IntegrityError → 409.  No separate pre-check.

• Spam protection (Layer 1): a user cannot create a new booking while they
  have ANY booking in awaiting_payment status.

• Spam protection (Layer 2 / 36-h floor): booking requests for a pooja
  starting within 36 hours are rejected at request time.

• Lazy expiry: on any read that cares about freshness, we first flip
  awaiting_payment rows past their deadline to expired and delete their
  booking_slots.  No background worker needed for v1.

• Payment signature: HMAC-SHA256(order_id + "|" + payment_id, KEY_SECRET).
  The order_id used is ALWAYS the one stored in our DB — never the one
  the browser claims to have.
"""

import hashlib
import hmac
import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import List

import razorpay
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_pandit, get_current_user
from app.models import Booking, BookingSlot, BookingStatus, Payment, PanditService, User
from app.schemas import (
    BookingCreate,
    BookingResponse,
    CreatePaymentResponse,
    VerifyPaymentRequest,
)

router = APIRouter(tags=["bookings"])

ALL_SLOTS = ["morning", "midday", "evening"]

# Minimum lead time between booking request and pooja start
MIN_LEAD_HOURS = 36

# Payment window after pandit accepts
PAYMENT_WINDOW_HOURS = 48


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_booking_response(b: Booking) -> BookingResponse:
    resp = BookingResponse.model_validate(b)
    resp.pooja_name    = b.service.name            if b.service else None
    resp.pandit_name   = b.pandit.display_name     if b.pandit  else None
    resp.pandit_area   = b.pandit.area             if b.pandit  else None
    resp.user_name     = b.user.name               if b.user    else None
    resp.duration_days  = b.service.duration_days  if b.service else None
    resp.duration_slots = b.service.duration_slots if b.service else None
    return resp


def _slots_for_booking(booking: Booking) -> List[BookingSlot]:
    """
    Compute the BookingSlot rows to insert when a booking is confirmed.

    Slot-based poojas : the requested slots on start_date.
    Multi-day poojas  : all three slots on every day of the span.
    """
    svc  = booking.service
    rows = []

    if svc.duration_days:
        for i in range(svc.duration_days):
            day = booking.start_date + timedelta(days=i)
            for slot in ALL_SLOTS:
                rows.append(BookingSlot(
                    pandit_id=booking.pandit_id,
                    date=day,
                    slot=slot,
                    booking_id=booking.id,
                ))
    else:
        for slot in booking.slots:
            rows.append(BookingSlot(
                pandit_id=booking.pandit_id,
                date=booking.start_date,
                slot=slot,
                booking_id=booking.id,
            ))
    return rows


def _expire_stale_bookings(db: Session, user_id: uuid.UUID) -> None:
    """
    Flip any awaiting_payment booking whose payment_due_at has passed to
    'expired', and free its booking_slots so the pandit's calendar opens up.

    Called lazily — before any operation that reads or creates bookings for
    this user.  No background worker required for v1.
    """
    now = datetime.now(timezone.utc)
    stale = (
        db.query(Booking)
        .filter(
            Booking.user_id == user_id,
            Booking.status  == BookingStatus.awaiting_payment,
            Booking.payment_due_at <= now,
        )
        .all()
    )
    for b in stale:
        b.status = BookingStatus.expired
        for slot in b.booking_slots:
            db.delete(slot)
    if stale:
        db.commit()


def _razorpay_client() -> razorpay.Client:
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


# ---------------------------------------------------------------------------
# Create a booking request  (status: pending, no slots reserved yet)
# ---------------------------------------------------------------------------

@router.post("/bookings", response_model=BookingResponse, status_code=status.HTTP_201_CREATED)
def create_booking(
    body: BookingCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Family requests a booking.

    Rejects early if:
    • the user already has a booking in awaiting_payment  (spam Layer 1), or
    • the pooja start is within 36 h of now               (36-h floor).

    Status stays 'pending' — slots are NOT reserved until the pandit accepts.
    """
    # Lazy expiry before the spam check so stale rows don't block the user.
    _expire_stale_bookings(db, user.id)

    # --- 36-h floor -----------------------------------------------------------
    now_utc       = datetime.now(timezone.utc)
    min_start     = (now_utc + timedelta(hours=MIN_LEAD_HOURS)).date()
    if body.start_date < min_start:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Bookings must be made at least {MIN_LEAD_HOURS} hours in advance",
        )

    # --- spam gate (Layer 1) --------------------------------------------------
    blocking = (
        db.query(Booking)
        .filter(
            Booking.user_id == user.id,
            Booking.status  == BookingStatus.awaiting_payment,
        )
        .first()
    )
    if blocking:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Complete payment for your accepted booking before making a new request",
        )

    # --- validate service offer -----------------------------------------------
    ps = db.get(PanditService, (body.pandit_id, body.service_id))
    if not ps:
        raise HTTPException(status_code=404, detail="This pandit does not offer that service")

    svc      = ps.service
    end_date = (
        body.start_date + timedelta(days=svc.duration_days - 1)
        if svc.duration_days
        else body.start_date
    )

    if not svc.duration_days and not body.slots:
        raise HTTPException(
            status_code=422,
            detail="slots is required for non-multi-day poojas",
        )

    booking = Booking(
        user_id    = user.id,
        pandit_id  = body.pandit_id,
        service_id = body.service_id,
        status     = BookingStatus.pending,
        start_date = body.start_date,
        end_date   = end_date,
        slots      = body.slots,
        price      = ps.price,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return _build_booking_response(booking)


# ---------------------------------------------------------------------------
# Pandit accepts a pending booking  →  awaiting_payment
# ---------------------------------------------------------------------------

@router.post("/bookings/{booking_id}/accept", response_model=BookingResponse)
def accept_booking(
    booking_id: uuid.UUID,
    user: User = Depends(get_current_pandit),
    db: Session = Depends(get_db),
):
    """
    Pandit accepts a pending booking.

    Atomic sequence (single transaction):
      1. Verify this pandit owns the booking.
      2. Check booking is still pending.
      3. INSERT all BookingSlot rows.
         ↳ UNIQUE(pandit_id, date, slot) violation → IntegrityError → 409.
      4. Set status = awaiting_payment.
      5. Set payment_due_at = min(now + 48h, pooja_start).
      6. Commit.

    Slots are locked immediately so the pandit's calendar is protected while
    the user pays.  If payment doesn't arrive by payment_due_at the lazy
    expiry frees the slots.
    """
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.pandit_id != user.pandit.id:
        raise HTTPException(status_code=403, detail="Not your booking to accept")
    if booking.status != BookingStatus.pending:
        raise HTTPException(
            status_code=409,
            detail=f"Booking is already {booking.status.value}",
        )

    # Compute payment deadline
    accept_time   = datetime.now(timezone.utc)
    deadline_48h  = accept_time + timedelta(hours=PAYMENT_WINDOW_HOURS)
    pooja_start   = datetime.combine(booking.start_date, time.min, tzinfo=timezone.utc)
    payment_due   = min(deadline_48h, pooja_start)

    slot_rows = _slots_for_booking(booking)

    try:
        db.add_all(slot_rows)
        booking.status         = BookingStatus.awaiting_payment
        booking.payment_due_at = payment_due
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="One or more slots are already taken — the pandit is no longer free at that time",
        )

    db.refresh(booking)
    return _build_booking_response(booking)


# ---------------------------------------------------------------------------
# Pandit declines a pending booking
# ---------------------------------------------------------------------------

@router.post("/bookings/{booking_id}/decline", response_model=BookingResponse)
def decline_booking(
    booking_id: uuid.UUID,
    user: User = Depends(get_current_pandit),
    db: Session = Depends(get_db),
):
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.pandit_id != user.pandit.id:
        raise HTTPException(status_code=403, detail="Not your booking to decline")
    if booking.status != BookingStatus.pending:
        raise HTTPException(
            status_code=409,
            detail=f"Booking is already {booking.status.value}",
        )

    booking.status = BookingStatus.declined
    db.commit()
    db.refresh(booking)
    return _build_booking_response(booking)


# ---------------------------------------------------------------------------
# User cancels their own booking
# ---------------------------------------------------------------------------

@router.post("/bookings/{booking_id}/cancel", response_model=BookingResponse)
def cancel_booking(
    booking_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your booking")
    if booking.status not in (BookingStatus.pending, BookingStatus.awaiting_payment):
        raise HTTPException(
            status_code=409,
            detail="Cannot cancel a completed, declined, or already cancelled booking",
        )

    booking.status = BookingStatus.cancelled
    for bs in booking.booking_slots:
        db.delete(bs)
    db.commit()
    db.refresh(booking)
    return _build_booking_response(booking)


# ---------------------------------------------------------------------------
# Create a Razorpay order for an awaiting-payment booking
# ---------------------------------------------------------------------------

@router.post("/bookings/{booking_id}/create-payment", response_model=CreatePaymentResponse)
def create_payment(
    booking_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Step 1 of the checkout flow: create a Razorpay order and persist it.

    The frontend receives the order_id + KEY_ID and opens the Razorpay popup.
    Price is always read from the DB — never trusted from the browser.
    """
    # Run lazy expiry first so a just-expired booking fails cleanly.
    _expire_stale_bookings(db, user.id)

    booking = db.get(Booking, booking_id)
    if not booking or booking.user_id != user.id:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.status != BookingStatus.awaiting_payment:
        raise HTTPException(
            status_code=409,
            detail=f"Booking is {booking.status.value} — only awaiting_payment bookings can be paid",
        )

    client = _razorpay_client()
    amount_paise = booking.price * 100  # Razorpay always uses smallest currency unit

    rz_order = client.order.create({
        "amount":   amount_paise,
        "currency": "INR",
        "receipt":  str(booking.id)[:40],   # max 40 chars per Razorpay docs
    })

    payment = Payment(
        booking_id        = booking.id,
        razorpay_order_id = rz_order["id"],
        amount            = amount_paise,
    )
    db.add(payment)
    db.commit()

    return CreatePaymentResponse(
        razorpay_order_id = rz_order["id"],
        amount            = amount_paise,
        razorpay_key      = settings.RAZORPAY_KEY_ID,
        booking_id        = str(booking.id),
        description       = (
            f"{booking.service.name} with {booking.pandit.display_name}"
            if booking.service and booking.pandit else "Pooja booking"
        ),
        prefill_name  = user.name,
        prefill_email = user.email,
        prefill_phone = user.phone or "",
    )


# ---------------------------------------------------------------------------
# Verify Razorpay payment signature  →  booking confirmed
# ---------------------------------------------------------------------------

@router.post("/bookings/{booking_id}/verify-payment", response_model=BookingResponse)
def verify_payment(
    booking_id: uuid.UUID,
    body: VerifyPaymentRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Step 2 of the checkout flow: verify the browser's payment callback.

    CRITICAL: we use the razorpay_order_id from OUR database, not from the
    browser — the browser could send a different (pre-paid) order_id.

    Verification: HMAC-SHA256(order_id + "|" + payment_id, KEY_SECRET)
    must match the signature Razorpay signed with the same secret.
    """
    booking = db.get(Booking, booking_id)
    if not booking or booking.user_id != user.id:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.status != BookingStatus.awaiting_payment:
        raise HTTPException(
            status_code=409,
            detail=f"Booking is {booking.status.value}",
        )

    payment = (
        db.query(Payment)
        .filter(Payment.booking_id == booking.id)
        .order_by(Payment.created_at.desc())
        .first()
    )
    if not payment:
        raise HTTPException(
            status_code=404,
            detail="No payment order found — call create-payment first",
        )

    # Recompute expected signature using DB order_id
    expected = hmac.new(
        settings.RAZORPAY_KEY_SECRET.encode("utf-8"),
        f"{payment.razorpay_order_id}|{body.razorpay_payment_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, body.razorpay_signature):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment signature verification failed",
        )

    payment.razorpay_payment_id = body.razorpay_payment_id
    payment.status              = "paid"
    booking.status              = BookingStatus.confirmed
    db.commit()
    db.refresh(booking)
    return _build_booking_response(booking)


# ---------------------------------------------------------------------------
# Read endpoints
# ---------------------------------------------------------------------------

@router.get("/me/bookings", response_model=List[BookingResponse])
def my_bookings(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """History page — all bookings for the authenticated user, newest first.
    Runs lazy expiry first so the user always sees fresh statuses."""
    _expire_stale_bookings(db, user.id)

    bookings = (
        db.query(Booking)
        .filter(Booking.user_id == user.id)
        .order_by(Booking.created_at.desc())
        .all()
    )
    return [_build_booking_response(b) for b in bookings]


@router.get("/me/requests", response_model=List[BookingResponse])
def my_requests(
    user: User = Depends(get_current_pandit),
    db: Session = Depends(get_db),
):
    """Pending Requests page — bookings awaiting this pandit's response."""
    pandit   = user.pandit
    bookings = (
        db.query(Booking)
        .filter(
            Booking.pandit_id == pandit.id,
            Booking.status    == BookingStatus.pending,
        )
        .order_by(Booking.created_at.asc())
        .all()
    )
    return [_build_booking_response(b) for b in bookings]


@router.get("/me/upcoming", response_model=List[BookingResponse])
def my_upcoming(
    user: User = Depends(get_current_pandit),
    db: Session = Depends(get_db),
):
    """Upcoming Services page — confirmed future bookings for the pandit."""
    pandit = user.pandit
    today  = date.today()
    bookings = (
        db.query(Booking)
        .filter(
            Booking.pandit_id  == pandit.id,
            Booking.status     == BookingStatus.confirmed,
            Booking.start_date >= today,
        )
        .order_by(Booking.start_date.asc())
        .all()
    )
    return [_build_booking_response(b) for b in bookings]
