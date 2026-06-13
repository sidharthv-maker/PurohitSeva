import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Enum as SAEnum,
    Float, ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import relationship

from app.database import Base


class BookingStatus(str, enum.Enum):
    pending           = "pending"
    awaiting_payment  = "awaiting_payment"   # pandit accepted, user must pay
    confirmed         = "confirmed"           # payment verified
    completed         = "completed"
    declined          = "declined"
    cancelled         = "cancelled"
    expired           = "expired"             # payment window elapsed


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(200), nullable=False)
    email = Column(String(200), unique=True, nullable=False, index=True)
    phone = Column(String(20), nullable=True)
    hashed_password = Column(String(200), nullable=False)
    is_pandit = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    pandit = relationship("Pandit", back_populates="user", uselist=False)
    bookings = relationship("Booking", foreign_keys="Booking.user_id", back_populates="user")


class Pandit(Base):
    __tablename__ = "pandits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True)
    display_name = Column(String(200), nullable=False)
    area = Column(String(200), nullable=False)
    lat = Column(Float, nullable=True)
    lng = Column(Float, nullable=True)
    languages = Column(ARRAY(String), nullable=False, default=list)
    verified = Column(Boolean, nullable=False, default=False)
    years_experience = Column(Integer, nullable=True)
    # Denormalised from reviews for cheap reads; updated on each new review.
    rating = Column(Float, nullable=True)
    review_count = Column(Integer, nullable=False, default=0)

    user = relationship("User", back_populates="pandit")
    services = relationship("PanditService", back_populates="pandit", cascade="all, delete-orphan")
    bookings = relationship("Booking", foreign_keys="Booking.pandit_id", back_populates="pandit")
    booking_slots = relationship("BookingSlot", back_populates="pandit")


class Service(Base):
    """Platform-wide catalogue of pooja types."""

    __tablename__ = "services"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(200), unique=True, nullable=False)
    # Exactly one of these is non-null — mirrors the prototype DURATIONS shape.
    duration_slots = Column(Integer, nullable=True)  # 1, 2, or 3 slots within one day
    duration_days = Column(Integer, nullable=True)   # consecutive fully-free days
    icon = Column(String(10), nullable=True)

    pandit_services = relationship("PanditService", back_populates="service")


class PanditService(Base):
    """
    Heart of the schema: many-to-many between pandits and services
    with a price payload column.  One row = "this pandit performs this
    pooja at this price".
    """

    __tablename__ = "pandit_services"

    pandit_id = Column(UUID(as_uuid=True), ForeignKey("pandits.id"), primary_key=True)
    service_id = Column(UUID(as_uuid=True), ForeignKey("services.id"), primary_key=True)
    price = Column(Integer, nullable=False)  # INR, no paise

    pandit = relationship("Pandit", back_populates="services")
    service = relationship("Service", back_populates="pandit_services")


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    pandit_id = Column(UUID(as_uuid=True), ForeignKey("pandits.id"), nullable=False)
    service_id = Column(UUID(as_uuid=True), ForeignKey("services.id"), nullable=False)
    status = Column(
        SAEnum(BookingStatus, name="bookingstatus"),
        nullable=False,
        default=BookingStatus.pending,
    )
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    # Which day-slots were requested, e.g. ['morning', 'midday'].
    # Empty for multi-day poojas (all 3 slots per day are implied).
    slots = Column(ARRAY(String), nullable=False, default=list)
    price = Column(Integer, nullable=False)  # snapshot of price at booking time
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    # Set on accept: min(accept_time + 48h, pooja_start). Null for non-payment flows.
    payment_due_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", foreign_keys=[user_id], back_populates="bookings")
    pandit = relationship("Pandit", foreign_keys=[pandit_id], back_populates="bookings")
    service = relationship("Service")
    review = relationship("Review", back_populates="booking", uselist=False)
    booking_slots = relationship("BookingSlot", back_populates="booking", cascade="all, delete-orphan")
    payment = relationship("Payment", back_populates="booking", uselist=False)


class BookingSlot(Base):
    """
    One row per occupied slot on a pandit's calendar.

    The UNIQUE constraint on (pandit_id, date, slot) is what prevents
    double-booking: the second conflicting INSERT raises IntegrityError,
    which we catch and turn into a 409 Conflict — no separate read-then-write
    check needed.
    """

    __tablename__ = "booking_slots"
    __table_args__ = (
        UniqueConstraint("pandit_id", "date", "slot", name="uq_pandit_date_slot"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pandit_id = Column(UUID(as_uuid=True), ForeignKey("pandits.id"), nullable=False)
    date = Column(Date, nullable=False)
    slot = Column(String(20), nullable=False)  # morning | midday | evening
    booking_id = Column(UUID(as_uuid=True), ForeignKey("bookings.id"), nullable=False)

    pandit = relationship("Pandit", back_populates="booking_slots")
    booking = relationship("Booking", back_populates="booking_slots")


class Review(Base):
    """
    Keyed on booking_id (not user_id + pandit_id) so the database itself
    enforces "only one review per booking" and "only completed bookings
    can be reviewed" — both via FK + application-layer check.
    """

    __tablename__ = "reviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    booking_id = Column(
        UUID(as_uuid=True), ForeignKey("bookings.id"), unique=True, nullable=False
    )
    rating = Column(Integer, nullable=False)  # 1–5
    text = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    booking = relationship("Booking", back_populates="review")


class Payment(Base):
    """
    One Razorpay order per booking attempt.

    razorpay_order_id  — created when user clicks "Pay" (create-payment endpoint)
    razorpay_payment_id — set after the browser POSTs the payment callback and
                          the backend verifies the HMAC signature.
    amount             — paise (₹ × 100); always read from the DB booking row,
                         never from the browser.
    status             — 'created' | 'paid' | 'failed'
    """

    __tablename__ = "payments"

    id                  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    booking_id          = Column(UUID(as_uuid=True), ForeignKey("bookings.id"), nullable=False, index=True)
    razorpay_order_id   = Column(String(100), nullable=False, unique=True)
    razorpay_payment_id = Column(String(100), nullable=True)
    amount              = Column(Integer, nullable=False)   # paise
    status              = Column(String(20), nullable=False, default="created")
    created_at          = Column(DateTime, nullable=False, default=datetime.utcnow)

    booking = relationship("Booking", back_populates="payment")
