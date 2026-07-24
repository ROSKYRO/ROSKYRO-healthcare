import re


def normalize_phone(raw: str | None) -> str:
    """Strip everything but digits and keep the last 10 (a plain Indian
    mobile number, regardless of how it was typed -- with/without +91,
    dashes, spaces, or a leading 0). Used so a user can log in or submit a
    password-reset request with "9800000001", "+91-9800000001",
    "+91 98000 00001" or "09800000001" and it still matches the same
    stored `phone` value on their user document."""
    digits = re.sub(r"\D", "", raw or "")
    return digits[-10:] if len(digits) >= 10 else digits
