import re
from datetime import date, datetime

# Upper bound on a source URL or event, kept from when they were CharField columns.
MAX_FIELD_LENGTH = 255

_SOURCE_URL = re.compile(r"^https?://\S+\.\S+$")


def is_source_url(text: str) -> bool:
    return _SOURCE_URL.search(text) is not None


def parse_source_date(text: str, today: date) -> date | None:
    """Read a YYMMDD source date; a date after `today` cannot be a source and is rejected."""
    try:
        parsed = datetime.strptime(text, "%y%m%d").date()
    except ValueError:
        return None
    return None if parsed > today else parsed
