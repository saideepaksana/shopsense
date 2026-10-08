import os
from datetime import date

FROZEN_TODAY = date(2026, 10, 1)


def today() -> date:
    return date.fromisoformat(os.getenv("SHOPSENSE_TODAY", FROZEN_TODAY.isoformat()))
