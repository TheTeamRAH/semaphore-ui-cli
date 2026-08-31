"""Tests for shared validation primitives."""

import pytest

from semaphore_ui.validators import require_nonempty_string, require_positive_int


def test_require_positive_int_rejects_booleans_and_non_positive_values():
    assert require_positive_int(1, ValueError, "invalid id") == 1

    for value in (True, 0, -1, "1"):
        with pytest.raises(ValueError, match="invalid id"):
            require_positive_int(value, ValueError, "invalid id")


def test_require_nonempty_string_rejects_blank_and_non_string_values():
    assert require_nonempty_string("value", ValueError, "invalid name") == "value"

    for value in ("", " ", None, 1):
        with pytest.raises(ValueError, match="invalid name"):
            require_nonempty_string(value, ValueError, "invalid name")
