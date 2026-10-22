"""Small German date, time and party-size parser used by the demo assistant and the inbox."""
import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .config import settings

WEEKDAYS = ["montag", "dienstag", "mittwoch", "donnerstag", "freitag", "samstag", "sonntag"]
WEEKDAY_DE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]


def today() -> date:
    return datetime.now(ZoneInfo(settings.timezone)).date()


def parse_date(text: str, ref: date | None = None) -> date | None:
    ref = ref or today()
    t = text.lower()
    if "übermorgen" in t:
        return ref + timedelta(days=2)
    if "morgen" in re.sub(r"guten morgen", "", t):
        return ref + timedelta(days=1)
    if "heute" in t:
        return ref
    m = re.search(r"\b(\d{1,2})\.(\d{1,2})\.(\d{2,4})?", t)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
        year = (2000 + int(y) if len(y) == 2 else int(y)) if y else ref.year
        try:
            result = date(year, mo, d)
        except ValueError:
            return None
        if not y and result < ref:
            result = date(year + 1, mo, d)
        return result
    for i, name in enumerate(WEEKDAYS):
        if re.search(rf"\b{name}\b", t):
            delta = (i - ref.weekday()) % 7 or 7
            return ref + timedelta(days=delta)
    return None


def parse_time(text: str) -> time | None:
    t = text.lower()
    m = re.search(r"\b(\d{1,2})[:.](\d{2})\s*uhr", t) or re.search(r"\b(\d{1,2}):(\d{2})\b", t)
    if m:
        return time(int(m.group(1)), int(m.group(2)))
    m = re.search(r"\b(\d{1,2})\s*uhr", t)
    if m and int(m.group(1)) < 24:
        return time(int(m.group(1)), 0)
    return None


def parse_persons(text: str) -> int | None:
    t = text.lower()
    m = re.search(r"(\d{1,3})\s*(personen|person|leute|gäste|pers\.)", t) or re.search(r"\bfür\s+(\d{1,3})\b", t)
    return int(m.group(1)) if m else None


def fmt_date(d: date) -> str:
    return f"{WEEKDAY_DE[d.weekday()]}, {d.strftime('%d.%m.%Y')}"
