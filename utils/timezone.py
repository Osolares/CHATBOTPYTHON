# utils/timezone.py
from datetime import datetime
import pytz

GUATEMALA_TZ = pytz.timezone("America/Guatemala")

def now():
    return datetime.now(GUATEMALA_TZ)
