from datetime import datetime, date, timedelta

WAT = timedelta(hours=1)  # Nigeria is UTC+1 all year, with no daylight saving

def now_wat() -> datetime:
    return datetime.utcnow() + WAT

def today_wat() -> date:
    return now_wat().date()

def day_range_utc(start: date, end: date):
    """Return (from, to) in UTC covering start..end inclusive, in Nigerian time."""
    s = datetime.combine(start, datetime.min.time()) - WAT
    e = datetime.combine(end + timedelta(days=1), datetime.min.time()) - WAT
    return s, e