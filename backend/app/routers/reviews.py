"""
Reviews — only allowed on completed bookings, one per booking.
Rating updates the pandit's denormalised rating + review_count using
a Bayesian average so pandits with 2 reviews aren't ranked equally
with pandits who have 200.

Bayesian formula:
  effective_rating = (n * mean + C * m) / (n + C)
  where n = review count, mean = average of actual reviews,
        C = confidence weight (5), m = prior mean (4.0).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Booking, BookingStatus, Review
from app.schemas import ReviewCreate, ReviewResponse

router = APIRouter(tags=["reviews"])

_BAYES_C = 5    # reviews needed before rating "fully counts"
_BAYES_M = 4.0  # prior mean (slightly optimistic)


def _update_pandit_rating(db: Session, pandit_id: uuid.UUID) -> None:
    """Recompute and persist the pandit's Bayesian rating after a new review."""
    row = (
        db.query(func.count(Review.id), func.avg(Review.rating))
        .join(Booking, Review.booking_id == Booking.id)
        .filter(Booking.pandit_id == pandit_id)
        .one()
    )
    n, mean = row
    if n == 0:
        return

    bayesian = (n * float(mean) + _BAYES_C * _BAYES_M) / (n + _BAYES_C)

    from app.models import Pandit  # local import to avoid circular
    pandit = db.get(Pandit, pandit_id)
    if pandit:
        pandit.rating = round(bayesian, 2)
        pandit.review_count = n


@router.post("/bookings/{booking_id}/review", response_model=ReviewResponse, status_code=status.HTTP_201_CREATED)
def create_review(
    booking_id: uuid.UUID,
    body: ReviewCreate,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Leave a review on a completed booking.

    The booking_id FK (not user_id + pandit_id) is what enforces:
      - only one review per booking (UNIQUE on booking_id)
      - only the booking's owner can review it
      - only completed bookings can be reviewed
    """
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your booking")
    if booking.status != BookingStatus.completed:
        raise HTTPException(status_code=409, detail="Can only review completed bookings")
    if booking.review:
        raise HTTPException(status_code=409, detail="Already reviewed")

    review = Review(booking_id=booking_id, rating=body.rating, text=body.text)
    db.add(review)
    db.flush()

    _update_pandit_rating(db, booking.pandit_id)
    db.commit()
    db.refresh(review)
    return review
