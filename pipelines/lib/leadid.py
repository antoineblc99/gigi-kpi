"""Lead-id universel : sha256(lower(email) + e164(phone))."""
import hashlib
import re

DEFAULT_REGION = "FR"
COUNTRY_CODES = {
    "FR": "33",
    "BE": "32",
    "CH": "41",
    "CA": "1",
    "US": "1",
    "MA": "212",
    "DZ": "213",
    "TN": "216",
}


def normalize_email(email: str | None) -> str:
    if not email:
        return ""
    return email.strip().lower()


def normalize_phone(phone: str | None, default_region: str = DEFAULT_REGION) -> str:
    """Best-effort E.164 normalization without external deps.

    Strips spaces/punctuation, drops leading 0 when a country code is implied,
    prepends '+' + country code when missing. Returns '' if no digits.
    """
    if not phone:
        return ""
    raw = str(phone).strip()
    has_plus = raw.startswith("+")
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return ""
    if has_plus:
        return "+" + digits
    cc = COUNTRY_CODES.get(default_region, "33")
    if digits.startswith("00"):
        return "+" + digits[2:]
    if digits.startswith(cc):
        return "+" + digits
    if digits.startswith("0"):
        return "+" + cc + digits[1:]
    return "+" + cc + digits


def compute_lead_id(email: str | None, phone: str | None, default_region: str = DEFAULT_REGION) -> str | None:
    """Universal lead id = sha256(lower(email) + e164(phone)).

    Returns None if both email and phone are empty (no anchor → no stable id).
    """
    e = normalize_email(email)
    p = normalize_phone(phone, default_region)
    if not e and not p:
        return None
    return hashlib.sha256((e + p).encode("utf-8")).hexdigest()
