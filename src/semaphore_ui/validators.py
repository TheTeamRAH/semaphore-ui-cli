"""Shared primitive validators for Semaphore UI data contracts."""

from __future__ import annotations

from typing import Any


def require_positive_int(value: Any, error_type: type[Exception], message: str) -> int:
    """Return a positive integer or raise the caller's domain-specific error.

    Args:
        value: Candidate numeric value.
        error_type: Exception class appropriate to the calling layer.
        message: Safe, actionable validation message.

    Returns:
        The validated positive integer.

    Raises:
        Exception: An instance of ``error_type`` when the value is invalid.
    """
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise error_type(message)
    return value


def require_nonempty_string(value: Any, error_type: type[Exception], message: str) -> str:
    """Return a non-blank string or raise the caller's domain-specific error.

    Args:
        value: Candidate text value.
        error_type: Exception class appropriate to the calling layer.
        message: Safe, actionable validation message.

    Returns:
        The original non-blank string.

    Raises:
        Exception: An instance of ``error_type`` when the value is invalid.
    """
    if not isinstance(value, str) or not value.strip():
        raise error_type(message)
    return value
