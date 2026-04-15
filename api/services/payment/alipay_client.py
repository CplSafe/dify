"""Shared Alipay RSA2 client.

Thin wrapper around ``python-alipay-sdk`` (github.com/fzlee/alipay) that:

- defers key-file loading until the first sign / verify / request call, so an
  application with ``ALIPAY_ENABLED=false`` boots without demanding PEM files;
- normalises asynchronous-notification verification to match the Alipay
  specification (strip ``sign`` + ``sign_type``; exclude empty values);
- provides a ``request`` helper that posts to the configured gateway and
  returns the business response body as a dict.

We reuse the upstream SDK for core RSA2 sign / verify primitives rather than
hand-rolling the signing loop — per the ``development-workflow.md`` rule of
preferring battle-tested libraries over hand-rolled crypto.
"""

from __future__ import annotations

import json
import logging
import pathlib
from datetime import datetime
from typing import Any
from urllib.parse import parse_qsl

import httpx
from alipay import AliPay  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

# Default HTTP timeout for the Alipay gateway (seconds).
# Alipay usually responds within 1s; we pad for TCP/TLS handshakes on cold paths.
_DEFAULT_TIMEOUT_SECONDS: float = 10.0


class AlipayClient:
    """Lazy-loaded RSA2 signing / verifying client for Alipay OpenAPI.

    Instantiate directly for tests; production code should call
    :meth:`AlipayClient.from_config` to wire dify_config fields in.
    """

    def __init__(
        self,
        *,
        enabled: bool,
        app_id: str,
        app_private_key_path: str,
        alipay_public_key_path: str,
        gateway: str,
        sign_type: str = "RSA2",
        notify_url: str = "",
        return_url: str = "",
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.enabled = enabled
        self._app_id = app_id
        self._app_private_key_path = app_private_key_path
        self._alipay_public_key_path = alipay_public_key_path
        self._gateway = gateway
        self._sign_type = sign_type
        self._notify_url = notify_url
        self._return_url = return_url
        self._timeout = timeout_seconds
        # Underlying SDK instance is created lazily so disabled installs don't
        # need PEM files on disk.
        self._sdk: AliPay | None = None

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------

    @classmethod
    def from_config(cls, cfg: Any) -> AlipayClient:
        """Build a client from a ``dify_config``-shaped object.

        Accepts any object exposing the ``ALIPAY_*`` attributes — duck-typed
        so tests can pass a lightweight mock.
        """
        return cls(
            enabled=bool(cfg.ALIPAY_ENABLED),
            app_id=str(cfg.ALIPAY_APP_ID or ""),
            app_private_key_path=str(cfg.ALIPAY_APP_PRIVATE_KEY_PATH or ""),
            alipay_public_key_path=str(cfg.ALIPAY_PUBLIC_KEY_PATH or ""),
            gateway=str(cfg.ALIPAY_GATEWAY or "https://openapi.alipay.com/gateway.do"),
            sign_type=str(cfg.ALIPAY_SIGN_TYPE or "RSA2"),
            notify_url=str(cfg.ALIPAY_NOTIFY_URL or ""),
            return_url=str(cfg.ALIPAY_RETURN_URL or ""),
        )

    # ------------------------------------------------------------------
    # Internal: lazy SDK access
    # ------------------------------------------------------------------

    def _require_enabled(self) -> None:
        if not self.enabled:
            raise RuntimeError("AlipayClient is not enabled (ALIPAY_ENABLED=false)")

    def _get_sdk(self) -> AliPay:
        """Load PEM keys on first use and cache the SDK instance."""
        self._require_enabled()
        if self._sdk is not None:
            return self._sdk

        app_private_key_string = pathlib.Path(self._app_private_key_path).read_text(encoding="utf-8")
        alipay_public_key_string = pathlib.Path(self._alipay_public_key_path).read_text(encoding="utf-8")

        self._sdk = AliPay(
            appid=self._app_id,
            app_notify_url=self._notify_url or None,
            app_private_key_string=app_private_key_string,
            alipay_public_key_string=alipay_public_key_string,
            sign_type=self._sign_type,
            debug=False,
        )
        # Override the SDK's gateway so we can point at the sandbox when requested.
        self._sdk._gateway = self._gateway  # pyright: ignore[reportPrivateUsage]
        return self._sdk

    # ------------------------------------------------------------------
    # Sign / verify primitives
    # ------------------------------------------------------------------

    def sign(self, payload: dict[str, Any]) -> str:
        """Produce a base64 RSA2 signature over the canonical form of ``payload``.

        Canonicalisation: keys are sorted lexicographically and joined with
        ``k=v&k2=v2`` (no URL encoding) — this matches the Alipay specification
        and the SDK's internal implementation.
        """
        self._require_enabled()
        sdk = self._get_sdk()
        ordered = sdk._ordered_data(dict(payload))  # pyright: ignore[reportPrivateUsage]
        raw = "&".join(f"{k}={v}" for k, v in ordered)
        return sdk._sign(raw)  # pyright: ignore[reportPrivateUsage]

    def verify(self, payload: dict[str, Any], signature: str) -> bool:
        """Verify ``signature`` against the canonical form of ``payload``.

        Returns False on signature mismatch; never raises for malformed input.
        """
        self._require_enabled()
        sdk = self._get_sdk()
        try:
            # SDK's verify() mutates its input (pops sign_type); pass a copy.
            return bool(sdk.verify(dict(payload), signature))
        except Exception:
            # Malformed base64, unknown sign_type, short signature, etc.
            logger.warning("Alipay signature verification raised; treating as invalid")
            return False

    def verify_notify(self, params: dict[str, str]) -> bool:
        """Validate an asynchronous notification body.

        Follows the Alipay spec:

        1. Extract ``sign`` and discard ``sign_type`` (do not sign them).
        2. Drop entries whose value is an empty string.
        3. Verify the remainder against the extracted signature.

        Returns False for disabled clients, missing ``sign`` values or
        mismatched signatures.
        """
        if not self.enabled:
            return False
        signature = params.get("sign")
        if not signature:
            return False

        # Spec: exclude sign / sign_type and empty values before signing.
        signing_params = {k: v for k, v in params.items() if k not in ("sign", "sign_type") and v not in (None, "")}
        return self.verify(signing_params, signature)

    # ------------------------------------------------------------------
    # HTTP request
    # ------------------------------------------------------------------

    def request(self, method: str, biz_content: dict[str, Any]) -> dict[str, Any]:
        """Post a signed request to the Alipay gateway and return the business body.

        Parameters
        ----------
        method:
            The Alipay API method name, e.g. ``alipay.trade.precreate``.
        biz_content:
            The method-specific business parameters.

        Returns
        -------
        dict
            The ``<method>_response`` body as a dict. Business errors (e.g.
            ``code == "40004"``) are returned as-is; the caller decides how
            to map them onto domain exceptions.
        """
        self._require_enabled()
        sdk = self._get_sdk()

        # Build the signed query string via the SDK so we inherit its
        # canonicalisation (ordered keys, url-encoded values, sign appended).
        signed_query = sdk.client_api(method, biz_content)
        form: dict[str, str] = dict(parse_qsl(signed_query, keep_blank_values=False))

        response = httpx.post(self._gateway, data=form, timeout=self._timeout)
        response.raise_for_status()

        body = json.loads(response.text)
        response_key = method.replace(".", "_") + "_response"
        # Normal shape: {"<method>_response": {...}, "sign": "..."}
        return dict(body.get(response_key) or body)

    # ------------------------------------------------------------------
    # Page-pay: signed redirect URL (no HTTP call)
    # ------------------------------------------------------------------

    def web_pay_url(
        self,
        biz_content: dict[str, Any],
        return_url: str | None = None,
    ) -> str:
        """Generate a signed redirect URL for ``alipay.trade.page.pay``.

        Unlike server-to-server methods (precreate, query, close), PC web
        checkout does not produce a JSON response — the SDK returns a fully
        signed GET URL the browser must navigate to so the user can complete
        payment in Alipay's hosted cashier.

        ``biz_content`` must contain the required fields ``out_trade_no``,
        ``total_amount`` (string with two decimal places), and ``subject``.
        Extra entries (e.g. ``product_code``, ``timeout_express``,
        ``business_params``) are forwarded to the SDK as ``**kwargs`` and
        merged into the Alipay ``biz_content`` payload.

        ``return_url`` — when supplied — overrides the client default so
        different topup contexts can land on different post-payment pages.
        The ``notify_url`` is fixed at client construction time (via
        ``app_notify_url`` on the underlying SDK).
        """
        self._require_enabled()
        sdk = self._get_sdk()

        # Pull out the required positional fields; everything else becomes
        # kwargs so the SDK folds them into biz_content verbatim.
        kwargs = dict(biz_content)
        out_trade_no = kwargs.pop("out_trade_no")
        total_amount = kwargs.pop("total_amount")
        subject = kwargs.pop("subject")
        notify_url_override = kwargs.pop("notify_url", None)

        effective_return_url = return_url or self._return_url or None
        effective_notify_url = notify_url_override or self._notify_url or None

        # ``api_alipay_trade_page_pay`` returns a signed query string WITHOUT
        # the gateway prefix (unlike ``api_alipay_trade_wap_pay``, which does
        # prepend it). Prepend it ourselves so callers get a navigable URL.
        signed_query = sdk.api_alipay_trade_page_pay(
            subject=subject,
            out_trade_no=out_trade_no,
            total_amount=total_amount,
            return_url=effective_return_url,
            notify_url=effective_notify_url,
            **kwargs,
        )
        return f"{self._gateway}?{signed_query}"

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    @property
    def app_id(self) -> str:
        return self._app_id

    @property
    def gateway(self) -> str:
        return self._gateway

    @property
    def notify_url(self) -> str:
        return self._notify_url

    @property
    def return_url(self) -> str:
        return self._return_url

    @staticmethod
    def now_timestamp() -> str:
        """Return the current timestamp in Alipay's expected format."""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ------------------------------------------------------------------
    # repr — NEVER include PEM material (security red line)
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"AlipayClient(enabled={self.enabled}, "
            f"app_id={self._app_id!r}, gateway={self._gateway!r}, "
            f"sign_type={self._sign_type!r})"
        )
