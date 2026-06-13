"""
Pydantic schemas — the contract between the API and its callers.

Rule of thumb used here:
  *Create  = what the caller sends
  *Response = what the API returns
  *Public   = safe to expose (no hashed_password, etc.)
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class SignupRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    email: EmailStr
    phone: Optional[str] = None
    password: str = Field(..., min_length=8)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str
    phone: Optional[str]
    is_pandit: bool
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic


# ---------------------------------------------------------------------------
# Services catalogue
# ---------------------------------------------------------------------------

class ServiceCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    duration_slots: Optional[int] = None  # 1, 2, or 3
    duration_days: Optional[int] = None   # 2, 4, …
    icon: Optional[str] = None


class ServiceBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    duration_slots: Optional[int]
    duration_days: Optional[int]
    icon: Optional[str]


class PanditMini(BaseModel):
    """Slim pandit summary used inside service catalogue responses."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    display_name: str
    area: str


class ServiceCatalogueItem(BaseModel):
    """One entry in GET /services — aggregated across all pandits."""
    id: uuid.UUID
    name: str
    duration_slots: Optional[int]
    duration_days: Optional[int]
    icon: Optional[str]
    min_price: int
    max_price: int
    pandit_count: int
    pandits: List[PanditMini]


# ---------------------------------------------------------------------------
# Pandits
# ---------------------------------------------------------------------------

class PanditServiceItem(BaseModel):
    """A single pooja + price row on a pandit's card."""
    model_config = ConfigDict(from_attributes=True)

    service_id: uuid.UUID
    name: str
    price: int
    duration_slots: Optional[int]
    duration_days: Optional[int]
    icon: Optional[str]


class PanditResponse(BaseModel):
    """Full pandit profile returned by GET /pandits and GET /pandits/{id}."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    display_name: str
    area: str
    lat: Optional[float]
    lng: Optional[float]
    languages: List[str]
    verified: bool
    years_experience: Optional[int]
    rating: Optional[float]
    review_count: int
    distance_km: Optional[float] = None  # injected after DB query
    poojas: List[PanditServiceItem] = []


class PanditCreate(BaseModel):
    display_name: str = Field(..., min_length=2, max_length=200)
    area: str = Field(..., min_length=2, max_length=200)
    lat: Optional[float] = None
    lng: Optional[float] = None
    languages: List[str] = Field(default_factory=list)
    years_experience: Optional[int] = None


class AddServiceRequest(BaseModel):
    """Add one service to the authenticated pandit's offerings."""
    service_id: uuid.UUID
    price: int = Field(..., gt=0)


class AddNewServiceRequest(BaseModel):
    """Create a brand-new catalogue entry and add it to the pandit's offerings."""
    name: str = Field(..., min_length=2, max_length=200)
    duration_slots: Optional[int] = None
    duration_days: Optional[int] = None
    icon: Optional[str] = None
    price: int = Field(..., gt=0)


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------

class DayAvailability(BaseModel):
    date: date
    free_slots: List[str]  # subset of ['morning', 'midday', 'evening']
    is_span_start: bool = False  # True when this date can start a multi-day pooja


class AvailabilityResponse(BaseModel):
    pandit_id: uuid.UUID
    service_id: uuid.UUID
    days: List[DayAvailability]


# ---------------------------------------------------------------------------
# Bookings
# ---------------------------------------------------------------------------

class BookingCreate(BaseModel):
    pandit_id: uuid.UUID
    service_id: uuid.UUID
    start_date: date
    slots: List[str] = Field(default_factory=list)  # empty for multi-day poojas


class BookingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    start_date: date
    end_date: date
    slots: List[str]
    price: int
    created_at: datetime
    payment_due_at: Optional[datetime] = None  # set on accept; drives frontend countdown

    # Flattened for frontend convenience
    pooja_name: Optional[str] = None
    pandit_name: Optional[str] = None
    pandit_area: Optional[str] = None
    user_name: Optional[str] = None
    duration_days: Optional[int] = None
    duration_slots: Optional[int] = None


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------

class CreatePaymentResponse(BaseModel):
    """Returned by POST /bookings/{id}/create-payment — all the data the
    Razorpay Checkout popup needs, assembled server-side."""
    razorpay_order_id: str
    amount: int          # paise
    currency: str = "INR"
    razorpay_key: str    # KEY_ID — safe to expose (public)
    booking_id: str
    description: str
    prefill_name: str
    prefill_email: str
    prefill_phone: str


class VerifyPaymentRequest(BaseModel):
    """Body of POST /bookings/{id}/verify-payment — sent by the browser after
    Razorpay's handler fires.  The backend recomputes the HMAC using the
    order_id from its OWN database, never from the browser."""
    razorpay_payment_id: str
    razorpay_signature: str


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------

class ReviewCreate(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    text: Optional[str] = None


class ReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    booking_id: uuid.UUID
    rating: int
    text: Optional[str]
    created_at: datetime
