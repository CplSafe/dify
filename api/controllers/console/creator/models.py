"""flask-restx Model 定义 — 供 creator 控制器的 Swagger 注解使用。

所有 Model 在模块级注册一次，各控制器 import 后直接用于
@console_ns.expect / @console_ns.marshal_with，避免重复注册导致
flask-restx 内部 dict 引用混乱（unhashable type 问题）。
"""

from flask_restx import fields

from controllers.console import console_ns

# ---------------------------------------------------------------------------
# balance 相关
# ---------------------------------------------------------------------------

balance_resp = console_ns.model(
    "CreatorBalanceResp",
    {
        "account_id": fields.String(description="用户账号 ID"),
        "balance": fields.String(description="可用余额（字符串形式的 Decimal）"),
        "currency": fields.String(description="货币单位，如 CNY"),
        "is_sufficient": fields.Boolean(description="余额是否充足（>0）"),
    },
)

admin_balance_item = console_ns.model(
    "CreatorAdminBalanceItem",
    {
        "account_id": fields.String(description="账号 ID"),
        "account_name": fields.String(description="账号名称"),
        "account_email": fields.String(description="账号邮箱"),
        "role": fields.String(description="角色：owner / member"),
        "tenant_id": fields.String(description="所属工作空间 ID"),
        "balance": fields.String(description="余额（字符串形式的 Decimal）"),
        "currency": fields.String(description="货币单位"),
        "is_sufficient": fields.Boolean(description="余额是否充足"),
        "updated_at": fields.String(description="最后更新时间 ISO8601，未创建时为空字符串"),
    },
)

admin_balance_list_resp = console_ns.model(
    "CreatorAdminBalanceListResp",
    {
        "data": fields.List(fields.Nested(admin_balance_item), description="余额列表"),
        "total": fields.Integer(description="总记录数"),
        "limit": fields.Integer(description="每页条数"),
        "offset": fields.Integer(description="偏移量"),
    },
)

admin_topup_req = console_ns.model(
    "CreatorAdminTopupReq",
    {
        "account_id": fields.String(required=True, description="目标用户账号 ID"),
        "amount": fields.Float(required=True, description="充值金额（支持小数）"),
        "description": fields.String(required=False, description="充值备注，默认为空"),
    },
)

billing_record_item = console_ns.model(
    "CreatorBillingRecordItem",
    {
        "id": fields.String(description="账单记录 ID"),
        "account_id": fields.String(description="用户账号 ID"),
        "amount": fields.String(description="变动金额（正=充值，负=消费）"),
        "balance_after": fields.String(description="变动后余额"),
        "type": fields.String(description="类型：topup / workflow_cost / rebate 等"),
        "description": fields.String(description="备注信息"),
        "created_at": fields.String(description="创建时间 ISO8601"),
    },
)

billing_record_list_resp = console_ns.model(
    "CreatorBillingRecordListResp",
    {
        "data": fields.List(fields.Nested(billing_record_item), description="账单列表"),
        "total": fields.Integer(description="总记录数"),
        "limit": fields.Integer(description="每页条数"),
        "offset": fields.Integer(description="偏移量"),
    },
)

topup_order_item = console_ns.model(
    "CreatorTopupOrderItem",
    {
        "id": fields.String(description="订单 ID"),
        "tenant_id": fields.String(description="工作空间 ID"),
        "account_id": fields.String(description="账号 ID"),
        "amount": fields.String(description="充值金额"),
        "status": fields.String(description="订单状态：pending / success / failed / expired"),
        "created_at": fields.String(description="创建时间 ISO8601"),
        "updated_at": fields.String(description="更新时间 ISO8601"),
    },
)

topup_order_list_resp = console_ns.model(
    "CreatorTopupOrderListResp",
    {
        "data": fields.List(fields.Nested(topup_order_item), description="充值订单列表"),
        "total": fields.Integer(description="总记录数"),
        "limit": fields.Integer(description="每页条数"),
        "offset": fields.Integer(description="偏移量"),
    },
)

# ---------------------------------------------------------------------------
# rebate 相关
# ---------------------------------------------------------------------------

rebate_config_resp = console_ns.model(
    "CreatorRebateConfigResp",
    {
        "id": fields.String(description="配置 ID"),
        "rebate_rate": fields.String(description="返佣比例（百分比，0-100）"),
        "cost_rate": fields.String(description="成本比例（百分比，0-100）"),
        "settlement_hour": fields.Integer(description="每日结算小时（0-23 UTC）"),
        "freeze_days": fields.Integer(description="冻结天数（0-90），0=下次解冻即释放"),
        "is_enabled": fields.Boolean(description="是否开启返佣功能"),
        "updated_by": fields.String(description="最后修改人账号 ID"),
    },
)

rebate_config_update_req = console_ns.model(
    "CreatorRebateConfigUpdateReq",
    {
        "rebate_rate": fields.Float(required=False, description="返佣比例（0-100）"),
        "cost_rate": fields.Float(required=False, description="成本比例（0-100）"),
        "settlement_hour": fields.Integer(required=False, description="每日结算小时（0-23）"),
        "freeze_days": fields.Integer(required=False, description="冻结天数（0-90）"),
        "is_enabled": fields.Boolean(required=False, description="是否启用"),
    },
)

rebate_record_item = console_ns.model(
    "CreatorRebateRecordItem",
    {
        "id": fields.String(description="返佣记录 ID"),
        "inviter_account_id": fields.String(description="邀请人账号 ID"),
        "invitee_account_id": fields.String(description="被邀请人账号 ID"),
        "invitee_name": fields.String(description="被邀请人名称"),
        "consumption_amount": fields.String(description="被邀请人消费金额"),
        "rebate_amount": fields.String(description="返佣金额"),
        "status": fields.String(description="状态：pending / settled / cancelled"),
        "settlement_date": fields.String(description="结算日期"),
        "unfrozen_at": fields.String(description="解冻时间 ISO8601"),
        "created_at": fields.String(description="创建时间 ISO8601"),
    },
)

rebate_record_list_resp = console_ns.model(
    "CreatorRebateRecordListResp",
    {
        "data": fields.List(fields.Nested(rebate_record_item), description="返佣记录列表"),
        "total": fields.Integer(description="总记录数"),
        "page": fields.Integer(description="当前页码"),
        "per_page": fields.Integer(description="每页条数"),
    },
)

rebate_summary_resp = console_ns.model(
    "CreatorRebateSummaryResp",
    {
        "total_rebate": fields.String(description="累计返佣总额"),
        "total_consumption": fields.String(description="被邀请人累计消费总额"),
        "invitee_count": fields.Integer(description="已使用邀请码的被邀请人数量"),
        "currency": fields.String(description="货币单位"),
    },
)

# ---------------------------------------------------------------------------
# marketplace 相关
# ---------------------------------------------------------------------------

marketplace_app_item = console_ns.model(
    "CreatorMarketplaceAppItem",
    {
        "id": fields.String(description="Marketplace 记录 ID"),
        "app_id": fields.String(description="Dify App ID"),
        "is_default": fields.Boolean(description="是否为默认创作者首页应用"),
        "is_active": fields.Boolean(description="是否处于上架状态"),
        "published_by": fields.String(description="发布人账号 ID"),
        "created_at": fields.String(description="发布时间 ISO8601"),
    },
)

marketplace_app_list_resp = console_ns.model(
    "CreatorMarketplaceAppListResp",
    {
        "data": fields.List(fields.Raw(), description="已上架应用列表"),
        "total": fields.Integer(description="总数"),
    },
)

marketplace_publish_req = console_ns.model(
    "CreatorMarketplacePublishReq",
    {
        "app_id": fields.String(required=True, description="要上架的 Dify App ID"),
        "is_default": fields.Boolean(required=False, description="是否设为默认创作者首页，默认 false"),
    },
)

marketplace_status_resp = console_ns.model(
    "CreatorMarketplaceStatusResp",
    {
        "app_id": fields.String(description="App ID"),
        "is_published": fields.Boolean(description="是否已上架"),
    },
)

marketplace_install_resp = console_ns.model(
    "CreatorMarketplaceInstallResp",
    {
        "installed_app_id": fields.String(description="InstalledApp 记录 ID，用于跳转探索页"),
        "already_installed": fields.Boolean(description="是否已安装（true=复用旧记录）"),
    },
)

marketplace_default_app_req = console_ns.model(
    "CreatorMarketplaceDefaultAppReq",
    {
        "app_id": fields.String(required=True, description="要设为默认的 App ID"),
    },
)

marketplace_default_app_resp = console_ns.model(
    "CreatorMarketplaceDefaultAppResp",
    {
        "data": fields.Raw(description="当前默认应用信息，未设置时为 null"),
    },
)

# ---------------------------------------------------------------------------
# API key 相关
# ---------------------------------------------------------------------------

api_key_item = console_ns.model(
    "CreatorApiKeyItem",
    {
        "id": fields.String(description="API Key 记录 ID"),
        "account_id": fields.String(description="所属账号 ID"),
        "token": fields.String(description="密钥明文（仅创建时返回，查询时脱敏）"),
        "description": fields.String(description="备注描述"),
        "created_at": fields.String(description="创建时间 ISO8601"),
    },
)

api_key_resp = console_ns.model(
    "CreatorApiKeyResp",
    {
        "api_key": fields.Raw(description="API Key 信息，未创建时为 null；查询时 token 脱敏"),
    },
)

api_key_create_req = console_ns.model(
    "CreatorApiKeyCreateReq",
    {
        "description": fields.String(required=False, description="API Key 备注，默认为空"),
    },
)
