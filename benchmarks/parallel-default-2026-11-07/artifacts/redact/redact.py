#!/usr/bin/env python3
"""Redact sensitive values inside JSON-compatible dict/list structures.

Standard library only. redact(value) returns a deep copy of dict/list
structures in which:

  * values stored under case-insensitive keys among
    {api_key, authorization, password, token, secret} become "[REDACTED]",
    regardless of the value's type;
  * other strings have each Bearer credential token replaced with
    "Bearer [REDACTED]" (case-insensitive "Bearer" + whitespace + a
    non-whitespace credential run).

Non-sensitive scalar values (bool/int/float/None and other opaque objects)
are preserved as-is. Input structures are never mutated.
"""

import re

__all__ = ("redact", "REDACTED", "SENSITIVE_KEYS")

REDACTED = "[REDACTED]"

SENSITIVE_KEYS = frozenset({"api_key", "authorization", "password", "token", "secret"})

# Case-insensitive "Bearer", then at least one whitespace character, then a
# maximal run of non-whitespace characters as the credential.
BEARER_RE = re.compile(r"Bearer\s+\S+", re.IGNORECASE)

_REPLACEMENT = "Bearer " + REDACTED


def _redact_string(text):
    return BEARER_RE.sub(_REPLACEMENT, text)


def redact(value):
    """Recursively copy JSON-compatible structures, redacting sensitive data."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if isinstance(key, str) and key.lower() in SENSITIVE_KEYS:
                out[key] = REDACTED
            else:
                out[key] = redact(item)
        return out
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return _redact_string(value)
    return value
