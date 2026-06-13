import math
import uuid
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_pandit, get_current_user
from app.models import BookingSlot, Pandit, PanditService, Service, User
from app.schemas import (
    AddNewServiceRequest,
    AddServiceRequest,
    AvailabilityResponse,
    DayAvailability,
    PanditCreate,
    PanditResponse,
    PanditServiceItem,
)

router = APIRouter(prefix="/pandits", tags=["pandits"])

ALL_SLOTS = ["morning", "midday", "evening"]
AVAILABILITY_HORIZON = 14  # days shown in booking calendar


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _build_pandit_response(pandit: Pandit, distance_km: Optional[float] = None) -> PanditResponse:
    poojas = [
        PanditServiceItem(
            service_id=ps.service_id,
            name=ps.service.name,
            price=ps.price,
            duration_slots=ps.service.duration_slots,
            duration_days=ps.service.duration_days,
            icon=ps.service.icon,
        )
        for ps in pandit.services
    ]
    resp = PanditResponse.model_validate(pandit)
    resp.poojas = poojas
    resp.distance_km = round(distance_km, 1) if distance_km is not None else None
    return resp


def _free_slots_on_day(occupied: dict, day: date) -> List[str]:
    taken = occupied.get(day, set())
    return [s for s in ALL_SLOTS if s not in taken]


def _get_occupied(db: Session, pandit_id: uuid.UUID, from_date: date, to_date: date) -> dict:
    """Return {date: set(slot_names)} for confirmed bookings in the date range."""
    rows = (
        db.query(BookingSlot)
        .filter(
            BookingSlot.pandit_id == pandit_id,
            BookingSlot.date >= from_date,
            BookingSlot.date <= to_date,
        )
        .all()
    )
    occupied: dict = {}
    for row in rows:
        occupied.setdefault(row.date, set()).add(row.slot)
    return occupied


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", response_model=List[PanditResponse])
def list_pandits(
    lat: Optional[float] = Query(None),
    lng: Optional[float] = Query(None),
    radius_km: Optional[float] = Query(None, alias="radius"),
    service: Optional[str] = Query(None, description="Filter by service name"),
    db: Session = Depends(get_db),
):
    """
    Return all pandits, optionally filtered by distance and/or service offered.

    Query params:
      lat, lng, radius  — centre-point + radius in km
      service           — service name substring match
    """
    query = db.query(Pandit)

    if service:
        query = (
            query.join(Pandit.services)
            .join(PanditService.service)
            .filter(Service.name.ilike(f"%{service}%"))
        )

    pandits = query.all()
    result = []

    for p in pandits:
        dist = None
        if lat is not None and lng is not None and p.lat is not None and p.lng is not None:
            dist = haversine_km(lat, lng, p.lat, p.lng)
            if radius_km is not None and dist > radius_km:
                continue
        result.append(_build_pandit_response(p, dist))

    # Sort by distance if provided, otherwise by rating desc
    if lat is not None:
        result.sort(key=lambda r: r.distance_km if r.distance_km is not None else 9999)
    else:
        result.sort(key=lambda r: r.rating or 0, reverse=True)

    return result


@router.get("/me", response_model=PanditResponse)
def get_my_pandit_profile(user: User = Depends(get_current_user)):
    """Return the authenticated user's pandit profile. Must come before /{pandit_id}."""
    if not user.pandit:
        raise HTTPException(status_code=404, detail="No pandit profile for this user")
    return _build_pandit_response(user.pandit)


@router.get("/{pandit_id}", response_model=PanditResponse)
def get_pandit(pandit_id: uuid.UUID, db: Session = Depends(get_db)):
    p = db.get(Pandit, pandit_id)
    if not p:
        raise HTTPException(status_code=404, detail="Pandit not found")
    return _build_pandit_response(p)


@router.post("", response_model=PanditResponse, status_code=status.HTTP_201_CREATED)
def enlist(
    body: PanditCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a pandit profile for the authenticated user."""
    if user.pandit:
        raise HTTPException(status_code=409, detail="Already enlisted as a pandit")

    pandit = Pandit(
        user_id=user.id,
        display_name=body.display_name,
        area=body.area,
        lat=body.lat,
        lng=body.lng,
        languages=body.languages,
        years_experience=body.years_experience,
    )
    user.is_pandit = True
    db.add(pandit)
    db.commit()
    db.refresh(pandit)
    return _build_pandit_response(pandit)


@router.post("/me/services", response_model=PanditResponse)
def add_service(
    body: AddServiceRequest,
    user: User = Depends(get_current_pandit),
    db: Session = Depends(get_db),
):
    """Add an existing catalogue service to the pandit's offerings."""
    pandit = user.pandit
    svc = db.get(Service, body.service_id)
    if not svc:
        raise HTTPException(status_code=404, detail="Service not found")

    existing = db.get(PanditService, (pandit.id, body.service_id))
    if existing:
        existing.price = body.price
    else:
        db.add(PanditService(pandit_id=pandit.id, service_id=body.service_id, price=body.price))

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Service already offered")

    db.refresh(pandit)
    return _build_pandit_response(pandit)


@router.post("/me/services/new", response_model=PanditResponse, status_code=status.HTTP_201_CREATED)
def add_new_service(
    body: AddNewServiceRequest,
    user: User = Depends(get_current_pandit),
    db: Session = Depends(get_db),
):
    """
    Create a brand-new catalogue entry and immediately add it to the
    pandit's offerings.  Mirrors "Offer something new" on the enlist page.
    """
    pandit = user.pandit

    existing_svc = db.query(Service).filter(Service.name == body.name).first()
    if existing_svc:
        raise HTTPException(
            status_code=409,
            detail=f"'{body.name}' already exists in the catalogue — use POST /pandits/me/services instead",
        )

    svc = Service(
        name=body.name,
        duration_slots=body.duration_slots,
        duration_days=body.duration_days,
        icon=body.icon,
    )
    db.add(svc)
    db.flush()  # get svc.id before committing

    db.add(PanditService(pandit_id=pandit.id, service_id=svc.id, price=body.price))
    db.commit()
    db.refresh(pandit)
    return _build_pandit_response(pandit)


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------

@router.get("/{pandit_id}/availability", response_model=AvailabilityResponse)
def get_availability(
    pandit_id: uuid.UUID,
    service_id: uuid.UUID = Query(...),
    from_date: date = Query(default_factory=date.today),
    to_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Port of the prototype's freeSlots / spanFree logic, now driven by real
    booking_slots data instead of the seeded pseudo-random busy map.

    Returns each date in the window tagged with which slots are free.
    For multi-day poojas (duration_days), only valid *start* dates where the
    full span is free are marked is_span_start=True.
    """
    pandit = db.get(Pandit, pandit_id)
    if not pandit:
        raise HTTPException(status_code=404, detail="Pandit not found")

    svc = db.get(Service, service_id)
    if not svc:
        raise HTTPException(status_code=404, detail="Service not found")

    if to_date is None:
        to_date = from_date + timedelta(days=AVAILABILITY_HORIZON - 1)

    occupied = _get_occupied(db, pandit_id, from_date, to_date)

    days = []
    current = from_date
    while current <= to_date:
        free = _free_slots_on_day(occupied, current)

        if svc.duration_days:
            # Multi-day: check if the full span from this date is free
            span_ok = all(
                len(_free_slots_on_day(occupied, current + timedelta(days=i))) == 3
                for i in range(svc.duration_days)
                if current + timedelta(days=i) <= to_date
            )
            days.append(DayAvailability(date=current, free_slots=free, is_span_start=span_ok))
        else:
            days.append(DayAvailability(date=current, free_slots=free))

        current += timedelta(days=1)

    return AvailabilityResponse(pandit_id=pandit_id, service_id=service_id, days=days)
