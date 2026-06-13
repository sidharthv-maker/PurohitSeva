from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import PanditService, Service
from app.schemas import ServiceCatalogueItem, PanditMini

router = APIRouter(prefix="/services", tags=["services"])


@router.get("", response_model=List[ServiceCatalogueItem])
def list_services(db: Session = Depends(get_db)):
    """
    Derived catalogue — mirrors deriveServices() from the prototype.

    Instead of SELECT * and grouping in JS, this is now a proper aggregate:
    for each service, return the price range and which pandits offer it.
    """
    services = db.query(Service).all()
    result = []

    for svc in services:
        offerings = svc.pandit_services  # already loaded via relationship
        if not offerings:
            continue

        prices = [o.price for o in offerings]
        pandits = [PanditMini.model_validate(o.pandit) for o in offerings]

        result.append(
            ServiceCatalogueItem(
                id=svc.id,
                name=svc.name,
                duration_slots=svc.duration_slots,
                duration_days=svc.duration_days,
                icon=svc.icon,
                min_price=min(prices),
                max_price=max(prices),
                pandit_count=len(pandits),
                pandits=pandits,
            )
        )

    result.sort(key=lambda s: s.pandit_count, reverse=True)
    return result
