"""Payment provider abstractions and shared Alipay client.

This package contains:
- ``provider``: the :class:`PaymentProvider` Protocol that concrete channels
  (alipay_qr / alipay_page) implement.
- ``alipay_client``: a thin wrapper over ``python-alipay-sdk`` that loads
  credentials lazily and exposes RSA2 sign / verify / HTTP helpers.

Concrete provider implementations live in sibling modules added in later
phases (see Task 3.3).
"""

from services.payment.alipay_client import AlipayClient
from services.payment.provider import CreateOrderResult, PaymentProvider

__all__ = ["AlipayClient", "CreateOrderResult", "PaymentProvider"]
