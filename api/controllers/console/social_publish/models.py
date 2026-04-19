"""flask-restx Model 定义 — 供 social-publish 控制器的 Swagger 注解使用。

所有 Model 在模块级注册一次，各控制器 import 后直接用于
@console_ns.expect / @console_ns.marshal_with，避免重复注册导致
flask-restx 内部 dict 引用混乱（unhashable type 问题）。
"""

from flask_restx import fields

from controllers.console import console_ns

# ---------------------------------------------------------------------------
# 账号相关
# ---------------------------------------------------------------------------

auth_start_req = console_ns.model(
    "SocialPublishAuthStartReq",
    {
        "platform": fields.String(
            required=True,
            description="平台标识，目前支持 douyin / xhs",
            example="douyin",
        ),
        "account_id": fields.String(
            required=False,
            description="重新授权时传入已有账号 ID，首次绑定不传",
            example="5328078b-c77c-43d9-a528-fd51e0ddfdb9",
        ),
    },
)

auth_start_resp = console_ns.model(
    "SocialPublishAuthStartResp",
    {
        "session_id": fields.String(description="授权会话 ID，用于后续轮询状态"),
        "qr_image_base64": fields.String(description="二维码图片 base64，前端直接渲染"),
        "expires_in": fields.Integer(description="二维码有效期（秒）"),
    },
)

account_item = console_ns.model(
    "SocialPublishAccount",
    {
        "id": fields.String(description="账号 ID"),
        "platform": fields.String(description="平台，douyin / xhs"),
        "platform_account_id": fields.String(description="平台侧账号唯一标识"),
        "name": fields.String(description="平台账号昵称"),
        "avatar": fields.String(description="头像 URL"),
        "status": fields.String(description="账号状态：active / expired"),
        "created_at": fields.String(description="绑定时间 ISO8601"),
    },
)

account_list_resp = console_ns.model(
    "SocialPublishAccountListResp",
    {
        "data": fields.List(fields.Nested(account_item), description="账号列表"),
    },
)

auth_status_resp = console_ns.model(
    "SocialPublishAuthStatusResp",
    {
        "status": fields.String(
            description="会话状态：pending（等待扫码）/ success（授权成功）"
                        "/ expired（已过期）/ failed（失败）"
        ),
        "account": fields.Raw(description="授权成功时返回账号信息，否则为 null"),
        "message": fields.String(description="错误或提示信息"),
        "challenge_session_id": fields.String(
            description="触发 SMS 二次验证时返回，前端需切换到短信验证弹窗"
        ),
    },
)

challenge_state_resp = console_ns.model(
    "SocialPublishChallengeStateResp",
    {
        "status": fields.String(
            description="challenge 状态：awaiting_user / completed / aborted"
        ),
        "kind": fields.String(description="验证类型，当前固定为 sms"),
        "result": fields.Raw(description="完成后的结果，包含 ok / detail 字段"),
    },
)

challenge_submit_req = console_ns.model(
    "SocialPublishChallengeSubmitReq",
    {
        "code": fields.String(
            required=True,
            description="用户收到的 4-8 位短信验证码",
            example="123456",
        ),
    },
)

challenge_action_resp = console_ns.model(
    "SocialPublishChallengeActionResp",
    {
        "ok": fields.Boolean(description="操作是否成功"),
        "detail": fields.String(description="详情描述，失败时说明原因"),
    },
)

# ---------------------------------------------------------------------------
# 任务相关
# ---------------------------------------------------------------------------

create_task_req = console_ns.model(
    "SocialPublishCreateTaskReq",
    {
        "account_id": fields.String(
            required=True,
            description="目标社交账号 ID（由 /social-publish/accounts 获取）",
            example="5328078b-c77c-43d9-a528-fd51e0ddfdb9",
        ),
        "work_id": fields.String(
            required=False,
            description="关联的创作者作品 ID，不传则仅发布不关联",
            example="a1b2c3d4-0000-0000-0000-000000000001",
        ),
        "title": fields.String(
            required=True,
            description="视频标题",
            example="我的第一条抖音",
        ),
        "tags": fields.List(
            fields.String,
            required=False,
            description="话题标签列表，不含 #",
            example=["旅行", "美食"],
        ),
        "desc": fields.String(
            required=False,
            description="视频简介",
            example="这是一段精彩的旅行记录",
        ),
        "platform_payload": fields.Raw(
            required=False,
            description="平台专属扩展参数（JSON 对象），"
                        "douyin 支持 location（地点名称字符串）",
            example={"location": "上海"},
        ),
    },
)

create_task_resp = console_ns.model(
    "SocialPublishCreateTaskResp",
    {
        "task_id": fields.String(description="任务 ID"),
        "status": fields.String(description="初始状态，通常为 pending"),
    },
)

batch_target = console_ns.model(
    "SocialPublishBatchTarget",
    {
        "account_id": fields.String(
            required=True,
            description="目标社交账号 ID",
        ),
        "platform_payload": fields.Raw(
            required=False,
            description="该账号专属平台参数，覆盖顶层 platform_payload",
        ),
    },
)

batch_create_task_req = console_ns.model(
    "SocialPublishBatchCreateTaskReq",
    {
        "work_id": fields.String(required=False, description="关联作品 ID"),
        "title": fields.String(required=True, description="视频标题"),
        "tags": fields.List(fields.String, required=False, description="话题标签列表"),
        "desc": fields.String(required=False, description="视频简介"),
        "targets": fields.List(
            fields.Nested(batch_target),
            required=True,
            description="发布目标列表，每项对应一个社交账号",
        ),
    },
)

batch_result_item = console_ns.model(
    "SocialPublishBatchResultItem",
    {
        "account_id": fields.String(description="目标账号 ID"),
        "success": fields.Boolean(description="是否创建成功"),
        "task_id": fields.String(description="成功时返回任务 ID，失败为 null"),
        "error_code": fields.String(description="失败错误码，成功为 null"),
        "error_message": fields.String(description="失败错误信息，成功为 null"),
    },
)

batch_create_task_resp = console_ns.model(
    "SocialPublishBatchCreateTaskResp",
    {
        "results": fields.List(
            fields.Nested(batch_result_item),
            description="每个目标账号的创建结果，无论成功失败都会返回",
        ),
    },
)

task_item = console_ns.model(
    "SocialPublishTask",
    {
        "id": fields.String(description="任务 ID"),
        "platform": fields.String(description="平台，douyin / xhs"),
        "account_id": fields.String(description="关联账号 ID"),
        "status": fields.String(
            description="任务状态：pending / queued / running / success / failed"
        ),
        "work_id": fields.String(description="关联作品 ID，无则为 null"),
        "result_url": fields.String(description="发布成功后的视频链接"),
        "error_code": fields.String(description="失败错误码"),
        "error_message": fields.String(description="失败错误信息"),
        "created_at": fields.String(description="创建时间 ISO8601"),
    },
)

task_list_resp = console_ns.model(
    "SocialPublishTaskListResp",
    {
        "data": fields.List(fields.Nested(task_item), description="任务列表"),
    },
)

task_status_resp = console_ns.model(
    "SocialPublishTaskStatusResp",
    {
        "task": fields.Nested(task_item, description="任务基本信息"),
        "result": fields.Raw(description="SAU 侧返回的原始结果，success 时包含 video_url 等"),
        "challenge_session_id": fields.String(
            description="SAU worker 触发 SMS 验证时返回，前端需打开短信验证弹窗"
        ),
    },
)
