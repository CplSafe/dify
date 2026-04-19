"""Alipay async payment notification endpoint.

Alipay calls this URL after payment lifecycle events (TRADE_SUCCESS,
TRADE_CLOSED, etc.). It does NOT send any auth header — security relies
entirely on RSA signature verification inside
``PaymentService.handle_notify``.

Wire format
-----------

Alipay POSTs ``application/x-www-form-urlencoded`` with the trade
payload + ``sign`` + ``sign_type``. We must:

1. Read ALL form fields verbatim (including unknown keys) and pass them
   to ``handle_notify`` so it can reconstruct the canonical sign string.
2. Respond with PLAIN TEXT ``"success"`` (no JSON, no surrounding
   whitespace) when the credit was applied or the order was already
   paid; ``"fail"`` triggers an Alipay retry.
3. Never raise — any uncaught exception ends up as Alipay logging an
   error and retrying anyway, but a clean ``"fail"`` is friendlier to
   the operator.

This is a public endpoint by URL but signature-gated by content. Do not
add ``@login_required`` or any inner-API key check here — Alipay won't
send those headers.
"""

from __future__ import annotations

import logging

from flask import Response, request
from flask_restx import Resource, fields

from controllers.inner_api import inner_api_ns
from services.payment.payment_service import PaymentService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Swagger 模型定义（模块级）
# ---------------------------------------------------------------------------

alipay_notify_resp = inner_api_ns.model(
    "AlipayNotifyResp",
    {
        "result": fields.String(
            description="固定返回纯文本 success（处理成功）或 fail（处理失败），"
                        "支付宝收到 fail 会重试通知",
            example="success",
        ),
    },
)


def _plain_text(body: str) -> Response:
    """Alipay requires bare-string ``success`` / ``fail`` (no JSON)."""
    return Response(body, status=200, mimetype="text/plain")


@inner_api_ns.route("/payment/alipay/notify")
class AlipayNotifyApi(Resource):
    """Receive Alipay async payment notifications."""

    @inner_api_ns.doc(
        description=(
            "【内部接口】接收支付宝异步支付回调通知。"
            "支付宝以 application/x-www-form-urlencoded 格式 POST 交易参数和 RSA 签名，"
            "本接口验签后更新订单状态并为工作空间钱包入账。"
            "返回纯文本 success 表示处理成功；返回 fail 触发支付宝重试。"
            "该接口无需登录，安全性依赖 RSA 签名验证，不应对外暴露。"
        ),
        responses={
            200: "处理结果（纯文本 success 或 fail）",
        },
    )
    def post(self):
        # Alipay sends form-encoded params. We accept JSON too purely as a
        # convenience for local manual testing — production traffic from
        # Alipay is always form-encoded.
        if request.form:
            params = dict(request.form.items())
        else:
            params = request.get_json(silent=True) or {}

        if not params:
            logger.warning("Alipay notify with empty body from %s", request.remote_addr)
            return _plain_text("fail")

        try:
            ok = PaymentService.from_config().handle_notify(params)
        except Exception:
            # Defence in depth: never let a transient bug return 500 to
            # Alipay (which would prompt them to retry indefinitely with
            # the wrong assumption that we never received the payload).
            logger.exception(
                "Alipay notify handling crashed out_trade_no=%s",
                params.get("out_trade_no"),
            )
            return _plain_text("fail")

        return _plain_text("success" if ok else "fail")
