"""Unit tests for the shared fen→yuan amount helper."""

from __future__ import annotations

import pytest

from services.payment._amount import fen_to_yuan_string


@pytest.mark.parametrize(
    ("amount_fen", "expected"),
    [
        (0, "0.00"),
        (1, "0.01"),
        (9, "0.09"),
        (10, "0.10"),
        (100, "1.00"),
        (1234, "12.34"),
        (99999, "999.99"),
        (10_000_00, "10000.00"),
        (10_000_000_0, "1000000.00"),
    ],
)
def test_fen_to_yuan_string_precision(amount_fen: int, expected: str) -> None:
    # Act
    result = fen_to_yuan_string(amount_fen)

    # Assert
    assert result == expected
    assert isinstance(result, str)


def test_fen_to_yuan_string_returns_two_decimal_places_for_round_amount() -> None:
    # Act
    result = fen_to_yuan_string(500)

    # Assert — regression: must keep the trailing zeros ("5.00", not "5").
    assert result == "5.00"
    assert "." in result
    assert result.split(".")[1] == "00"
