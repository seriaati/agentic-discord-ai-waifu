import datetime
import zoneinfo
from typing import TYPE_CHECKING

from opencc import OpenCC

from app.constants import UTC8

if TYPE_CHECKING:
    from app.db.models import User

# s2twp: Simplified -> Traditional (Taiwan) with common phrase conversion.
# No-op on text that is already Traditional, English, or Japanese.
_OPENCC = OpenCC("s2twp")


def get_utc8_now() -> datetime.datetime:
    return datetime.datetime.now(UTC8)


def get_user_tz(user: User) -> zoneinfo.ZoneInfo:
    return zoneinfo.ZoneInfo(user.timezone)


def get_user_now(user: User) -> datetime.datetime:
    return datetime.datetime.now(get_user_tz(user))


def to_traditional_chinese(text: str) -> str:
    return _OPENCC.convert(text)
