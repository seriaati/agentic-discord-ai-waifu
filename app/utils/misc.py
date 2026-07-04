import datetime

from opencc import OpenCC

from app.constants import UTC8

# s2twp: Simplified -> Traditional (Taiwan) with common phrase conversion.
# No-op on text that is already Traditional, English, or Japanese.
_OPENCC = OpenCC("s2twp")


def get_utc8_now() -> datetime.datetime:
    return datetime.datetime.now(UTC8)


def to_traditional_chinese(text: str) -> str:
    return _OPENCC.convert(text)
