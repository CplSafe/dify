"""Shared amount-format helpers for payment providers.

Alipay's ``price(12)`` type expects a **string** with exactly two decimal
places (e.g. ``"12.34"``). Using ``Decimal`` avoids float rounding errors
that would otherwise leak into signed payloads and trigger signature
mismatches downstream.

Kept private to :mod:`services.payment` — not part of the public provider
contract. Consumers are :class:`AlipayQrProvider` and
:class:`AlipayPageProvider`.
"""

from __future__ import annotations

from decimal import Decimal

# Quantum used to normalise yuan amounts to two decimal places ("12.34").
_YUAN_QUANTUM = Decimal("0.01")

# One yuan = 100 fen.
_FEN_PER_YUAN = Decimal(100)


def fen_to_yuan_string(amount_fen: int) -> str:
    """Convert an integer fen amount to Alipay's two-decimal yuan string.

    Examples
    --------
    >>> fen_to_yuan_string(1234)
    '12.34'
    >>> fen_to_yuan_string(1)
    '0.01'
    >>> fen_to_yuan_string(10000000)
    '100000.00'
    """
    yuan = (Decimal(amount_fen) / _FEN_PER_YUAN).quantize(_YUAN_QUANTUM)
    return format(yuan, "f")
