"""Refuses secrets before they reach the memory store.

Memory is long-lived and searchable, so it must never hold credentials or
payment data, even when the user asks. The check is deliberately broad: a
false positive only means "say it again without the secret part".
"""

import re

from jarvis.tools.accessibility import normalize_text


# Matched on normalized text (casefolded, accents stripped).
_SECRET_KEYWORDS = (
    "mot de passe",
    "mdp",
    "password",
    "passcode",
    "passphrase",
    "code pin",
    "pin code",
    "code secret",
    "code de securite",
    "code confidentiel",
    "code d'acces",
    "cvv",
    "cvc",
    "cryptogramme",
    "iban",
    "bic",
    "numero de carte",
    "carte bancaire",
    "carte de credit",
    "card number",
    "cle api",
    "api key",
    "apikey",
    "token",
    "secret key",
    "cle privee",
    "private key",
    "seed phrase",
    "phrase de recuperation",
    "numero de securite sociale",
    "securite sociale",
    "passeport",
    "passport",
)

_KEYWORD_PATTERN = re.compile(
    r"(?<![a-z0-9])(" + "|".join(re.escape(k) for k in _SECRET_KEYWORDS) + r")(?![a-z0-9])"
)

# IBAN: two letters, two check digits, then 11 to 30 alphanumerics.
_IBAN_PATTERN = re.compile(r"\b[a-z]{2}\d{2}(?:\s?[a-z0-9]){11,30}\b")

# Card-like digit runs (spaces or dashes allowed), validated with Luhn.
_DIGIT_RUN_PATTERN = re.compile(r"(?:\d[ -]?){13,19}")

# Credential-shaped tokens: long strings mixing letters and digits, or
# well-known key prefixes (sk-..., ghp_..., AKIA...).
_KEY_PREFIX_PATTERN = re.compile(r"\b(?:sk|pk|rk)[-_][a-z0-9_-]{16,}|\bghp_[a-z0-9]{20,}|\bakia[a-z0-9]{12,}")
_HIGH_ENTROPY_PATTERN = re.compile(r"\b(?=[a-z0-9_-]*\d)(?=[a-z0-9_-]*[a-z])[a-z0-9_-]{24,}\b")


def _luhn_ok(digits: str) -> bool:
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def contains_secret(*values: str | None, high_entropy: bool = True) -> bool:
    for value in values:
        if not value:
            continue

        text = normalize_text(value)

        if _KEYWORD_PATTERN.search(text):
            return True

        if _IBAN_PATTERN.search(text):
            return True

        if _KEY_PREFIX_PATTERN.search(text) or (high_entropy and _HIGH_ENTROPY_PATTERN.search(text)):
            return True

        for match in _DIGIT_RUN_PATTERN.finditer(text):
            digits = re.sub(r"\D", "", match.group())
            if 13 <= len(digits) <= 19 and _luhn_ok(digits):
                return True

    return False
