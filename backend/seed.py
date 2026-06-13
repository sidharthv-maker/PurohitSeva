"""
Seed script — populates the database with the 9 prototype pandits,
the full services catalogue, and their pandit_services rows.

Run AFTER `alembic upgrade head`:
    python seed.py
"""

import sys
from pathlib import Path

# Make sure 'app' package is importable when running from backend/
sys.path.insert(0, str(Path(__file__).parent))

from app.core.security import hash_password
from app.database import SessionLocal
from app.models import Pandit, PanditService, Service, User

# ---------------------------------------------------------------------------
# Catalogue — mirrors DURATIONS + SVC_ICONS from the prototype
# ---------------------------------------------------------------------------

SERVICES = [
    {"name": "Namakaranam",          "duration_slots": 1, "icon": "👶"},
    {"name": "Annaprashana",         "duration_slots": 1, "icon": "🍚"},
    {"name": "Satyanarayana Vratam", "duration_slots": 1, "icon": "🙏"},
    {"name": "Ganapati Homam",       "duration_slots": 1, "icon": "🐘"},
    {"name": "Rudrabhishekam",       "duration_slots": 1, "icon": "🔱"},
    {"name": "Office Opening Pooja", "duration_slots": 1, "icon": "🏢"},
    {"name": "Navagraha Shanti",     "duration_slots": 2, "icon": "🪐"},
    {"name": "Vastu Shanti",         "duration_slots": 2, "icon": "🧭"},
    {"name": "Sudarshana Homam",     "duration_slots": 2, "icon": "🔥"},
    {"name": "Griha Pravesh",        "duration_slots": 3, "icon": "🏠"},
    {"name": "Vivaha (Wedding)",     "duration_days":  2, "icon": "💍"},
    {"name": "Upanayanam",           "duration_days":  4, "icon": "🧵"},
]

# ---------------------------------------------------------------------------
# Pandits — coordinates are approximate areas in Hyderabad
# ---------------------------------------------------------------------------

PANDITS = [
    {
        "user": {
            "name": "Pt. Ramesh Sharma",
            "email": "ramesh.sharma@example.com",
            "password": "password123",
        },
        "profile": {
            "display_name": "Pt. Ramesh Sharma",
            "area": "Kukatpally",
            "lat": 17.4947, "lng": 78.3996,
            "languages": ["Telugu", "Hindi"],
            "rating": 4.9,
        },
        "poojas": [
            ("Griha Pravesh", 5100),
            ("Satyanarayana Vratam", 2100),
            ("Ganapati Homam", 3100),
            ("Namakaranam", 1500),
        ],
    },
    {
        "user": {
            "name": "Sri Venkatachary",
            "email": "venkatachary@example.com",
            "password": "password123",
        },
        "profile": {
            "display_name": "Sri Venkatachary",
            "area": "Ameerpet",
            "lat": 17.4374, "lng": 78.4482,
            "languages": ["Telugu", "Sanskrit"],
            "rating": 4.8,
        },
        "poojas": [
            ("Satyanarayana Vratam", 1800),
            ("Annaprashana", 1100),
            ("Vivaha (Wedding)", 21000),
            ("Sudarshana Homam", 7500),
        ],
    },
    {
        "user": {
            "name": "Pt. Anil Shastri",
            "email": "anil.shastri@example.com",
            "password": "password123",
        },
        "profile": {
            "display_name": "Pt. Anil Shastri",
            "area": "Madhapur",
            "lat": 17.4503, "lng": 78.3831,
            "languages": ["Hindi", "English"],
            "rating": 4.7,
        },
        "poojas": [
            ("Griha Pravesh", 4500),
            ("Rudrabhishekam", 3500),
            ("Navagraha Shanti", 4100),
            ("Office Opening Pooja", 2500),
        ],
    },
    {
        "user": {
            "name": "Sri Krishnamurthy Ghanapathi",
            "email": "krishnamurthy@example.com",
            "password": "password123",
        },
        "profile": {
            "display_name": "Sri Krishnamurthy Ghanapathi",
            "area": "Begumpet",
            "lat": 17.4421, "lng": 78.4642,
            "languages": ["Telugu", "Tamil", "Sanskrit"],
            "rating": 5.0,
        },
        "poojas": [
            ("Vivaha (Wedding)", 25000),
            ("Upanayanam", 11000),
            ("Sudarshana Homam", 8100),
            ("Rudrabhishekam", 4000),
        ],
    },
    {
        "user": {
            "name": "Pt. Suresh Joshi",
            "email": "suresh.joshi@example.com",
            "password": "password123",
        },
        "profile": {
            "display_name": "Pt. Suresh Joshi",
            "area": "Secunderabad",
            "lat": 17.4399, "lng": 78.4983,
            "languages": ["Hindi", "Marathi"],
            "rating": 4.6,
        },
        "poojas": [
            ("Satyanarayana Vratam", 1500),
            ("Ganapati Homam", 2800),
            ("Vastu Shanti", 3600),
            ("Namakaranam", 1200),
        ],
    },
    {
        "user": {
            "name": "Sri Bhargava Sarma",
            "email": "bhargava.sarma@example.com",
            "password": "password123",
        },
        "profile": {
            "display_name": "Sri Bhargava Sarma",
            "area": "Dilsukhnagar",
            "lat": 17.3688, "lng": 78.5247,
            "languages": ["Telugu"],
            "rating": 4.8,
        },
        "poojas": [
            ("Griha Pravesh", 4000),
            ("Navagraha Shanti", 3800),
            ("Annaprashana", 1300),
            ("Vastu Shanti", 3200),
        ],
    },
    {
        "user": {
            "name": "Pt. Devdutt Trivedi",
            "email": "devdutt.trivedi@example.com",
            "password": "password123",
        },
        "profile": {
            "display_name": "Pt. Devdutt Trivedi",
            "area": "Gachibowli",
            "lat": 17.4401, "lng": 78.3489,
            "languages": ["Hindi", "Gujarati", "English"],
            "rating": 4.9,
        },
        "poojas": [
            ("Office Opening Pooja", 3000),
            ("Satyanarayana Vratam", 2400),
            ("Griha Pravesh", 5500),
            ("Ganapati Homam", 3300),
        ],
    },
    {
        "user": {
            "name": "Sri Narasimha Avadhani",
            "email": "narasimha@example.com",
            "password": "password123",
        },
        "profile": {
            "display_name": "Sri Narasimha Avadhani",
            "area": "LB Nagar",
            "lat": 17.3497, "lng": 78.5478,
            "languages": ["Telugu", "Sanskrit"],
            "rating": 4.7,
        },
        "poojas": [
            ("Upanayanam", 9500),
            ("Rudrabhishekam", 3200),
            ("Sudarshana Homam", 6900),
            ("Vivaha (Wedding)", 19000),
        ],
    },
    {
        "user": {
            "name": "Pt. Mohan Dixit",
            "email": "mohan.dixit@example.com",
            "password": "password123",
        },
        "profile": {
            "display_name": "Pt. Mohan Dixit",
            "area": "Banjara Hills",
            "lat": 17.4156, "lng": 78.4347,
            "languages": ["Hindi", "English"],
            "rating": 4.5,
        },
        "poojas": [
            ("Namakaranam", 1800),
            ("Annaprashana", 1500),
            ("Navagraha Shanti", 4500),
            ("Vastu Shanti", 4000),
        ],
    },
]


def seed() -> None:
    db = SessionLocal()
    try:
        # Guard against double-seeding
        if db.query(Service).count() > 0:
            print("Database already seeded — skipping.")
            return

        print("Seeding services catalogue...")
        service_map: dict[str, Service] = {}
        for s in SERVICES:
            svc = Service(**s)
            db.add(svc)
            db.flush()  # get svc.id
            service_map[s["name"]] = svc

        print("Seeding pandits...")
        for data in PANDITS:
            user = User(
                name=data["user"]["name"],
                email=data["user"]["email"],
                hashed_password=hash_password(data["user"]["password"]),
                is_pandit=True,
            )
            db.add(user)
            db.flush()

            profile = data["profile"]
            pandit = Pandit(
                user_id=user.id,
                display_name=profile["display_name"],
                area=profile["area"],
                lat=profile["lat"],
                lng=profile["lng"],
                languages=profile["languages"],
                verified=True,
                rating=profile["rating"],
            )
            db.add(pandit)
            db.flush()

            for pooja_name, price in data["poojas"]:
                svc = service_map.get(pooja_name)
                if not svc:
                    print(f"  Warning: service '{pooja_name}' not found in catalogue")
                    continue
                db.add(PanditService(pandit_id=pandit.id, service_id=svc.id, price=price))

            print(f"  ✓ {profile['display_name']} ({profile['area']})")

        db.commit()
        print("\nSeed complete.")
        print("  Login with any pandit email + password 'password123'")
        print("  API docs: http://localhost:8000/docs")

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
