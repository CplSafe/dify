"""Creator works endpoints.

GET  /creator/works               — 查询当前用户的作品列表（支持分页）
POST /creator/works               — 新建作品记录（关联工作流运行结果）
DELETE /creator/works/<id>        — 删除指定作品
POST /creator/works/<id>/publish  — 更新作品分享状态（发布到社交平台）
"""

from flask import request
from flask_restx import Resource, fields
from sqlalchemy import select

from controllers.console import console_ns
from controllers.console.wraps import account_initialization_required, setup_required
from libs.login import current_account_with_tenant, login_required
from models.creator import CreatorWork, CreatorWorkShareStatus
from models.engine import db

# ---------------------------------------------------------------------------
# Model 定义
# ---------------------------------------------------------------------------

_work_item = console_ns.model(
    "CreatorWorkItem",
    {
        "id": fields.String(description="作品 ID"),
        "title": fields.String(description="作品标题"),
        "file_key": fields.String(description="视频文件存储 key（OSS 路径或外部 URL）"),
        "file_type": fields.String(description="文件类型，默认 video"),
        "workflow_run_id": fields.String(description="关联的工作流运行 ID，可为空"),
        "app_id": fields.String(description="关联的应用 ID，可为空"),
        "share_status": fields.String(description="分享状态，如 none / published_tiktok / published_xhs"),
        "output_data": fields.Raw(description="工作流输出数据（JSON 对象）"),
        "created_at": fields.String(description="创建时间 ISO8601"),
    },
)

_works_list_resp = console_ns.model(
    "CreatorWorksListResp",
    {
        "data": fields.List(fields.Nested(_work_item), description="作品列表"),
        "total": fields.Integer(description="符合条件的总条数"),
        "limit": fields.Integer(description="本次查询的 limit"),
        "offset": fields.Integer(description="本次查询的 offset"),
    },
)

_create_work_req = console_ns.model(
    "CreatorWorkCreateReq",
    {
        "title": fields.String(
            required=False,
            description="作品标题，默认 Untitled",
            example="我的第一条视频",
        ),
        "workflow_run_id": fields.String(
            required=False,
            description="关联的工作流运行 ID，传入时若已存在则返回已有记录（幂等）",
            example="run-abc123",
        ),
        "app_id": fields.String(
            required=False,
            description="关联的应用 ID",
            example="app-xyz456",
        ),
        "file_key": fields.String(
            required=False,
            description="视频文件存储 key（OSS 路径或外部 URL）",
            example="upload_files/tenant-1/video.mp4",
        ),
        "file_type": fields.String(
            required=False,
            description="文件类型，默认 video",
            example="video",
        ),
        "output_data": fields.Raw(
            required=False,
            description="工作流输出数据（JSON 对象），前端透传",
        ),
    },
)

_publish_req = console_ns.model(
    "CreatorWorkPublishReq",
    {
        "platform": fields.String(
            required=True,
            description="目标平台，取值 tiktok / xhs",
            example="tiktok",
        ),
    },
)

# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------


@console_ns.route("/creator/works")
class CreatorWorksApi(Resource):

    @setup_required
    @login_required
    @account_initialization_required
    @console_ns.doc(
        description="查询当前用户的创作者作品列表，按创建时间倒序排列，支持 limit/offset 分页。",
        params={
            "limit": "每页条数，最大 100，默认 20",
            "offset": "偏移量，默认 0",
        },
        responses={
            200: ("成功", _works_list_resp),
            401: "未登录",
        },
    )
    @console_ns.marshal_with(_works_list_resp)
    def get(self):
        """查询当前用户的创作者作品列表"""
        current_user, current_tenant_id = current_account_with_tenant()

        limit = min(int(request.args.get("limit", 20)), 100)
        offset = int(request.args.get("offset", 0))

        base_query = select(CreatorWork).where(CreatorWork.account_id == current_user.id)
        total = db.session.scalar(
            select(db.func.count()).select_from(base_query.subquery())
        ) or 0
        works = list(
            db.session.scalars(
                base_query.order_by(CreatorWork.created_at.desc()).limit(limit).offset(offset)
            ).all()
        )

        return {
            "data": [w.to_dict() for w in works],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    @setup_required
    @login_required
    @account_initialization_required
    @console_ns.doc(
        description="新建创作者作品记录。若传入 workflow_run_id 且该运行已有对应作品，"
                    "则直接返回已有记录（幂等，状态码 200）；否则创建后返回 201。",
        responses={
            200: ("作品已存在（幂等返回）", _work_item),
            201: ("创建成功", _work_item),
            401: "未登录",
        },
    )
    @console_ns.expect(_create_work_req, validate=False)
    def post(self):
        """新建创作者作品记录"""
        current_user, current_tenant_id = current_account_with_tenant()

        payload = request.get_json() or {}
        title = payload.get("title", "Untitled")
        workflow_run_id = payload.get("workflow_run_id")
        app_id = payload.get("app_id")
        file_key = payload.get("file_key")
        file_type = payload.get("file_type", "video")
        output_data = payload.get("output_data")

        if workflow_run_id:
            existing_work = db.session.scalar(
                select(CreatorWork).where(
                    CreatorWork.account_id == current_user.id,
                    CreatorWork.workflow_run_id == workflow_run_id,
                )
            )
            if existing_work:
                return existing_work.to_dict(), 200

        work = CreatorWork(
            account_id=current_user.id,
            tenant_id=current_tenant_id,
            workflow_run_id=workflow_run_id,
            app_id=app_id,
            title=title,
            file_key=file_key,
            file_type=file_type,
            output_data=output_data,
        )
        db.session.add(work)
        db.session.commit()

        return work.to_dict(), 201


@console_ns.route("/creator/works/<string:work_id>")
class CreatorWorkItemApi(Resource):

    @setup_required
    @login_required
    @account_initialization_required
    @console_ns.doc(
        description="删除指定作品。只有作品所有者可删除，作品不存在时返回 404。",
        responses={
            200: "删除成功",
            401: "未登录",
            404: "作品不存在",
        },
    )
    def delete(self, work_id: str):
        """删除创作者作品"""
        current_user, _ = current_account_with_tenant()
        work = db.session.scalar(
            select(CreatorWork).where(
                CreatorWork.id == work_id,
                CreatorWork.account_id == current_user.id,
            )
        )
        if not work:
            from werkzeug.exceptions import NotFound
            raise NotFound("Work not found")

        db.session.delete(work)
        db.session.commit()
        return {"result": "success"}


@console_ns.route("/creator/works/<string:work_id>/publish")
class CreatorWorkPublishApi(Resource):

    @setup_required
    @login_required
    @account_initialization_required
    @console_ns.doc(
        description="触发作品发布到社交平台。传入目标平台（tiktok / xhs），"
                    "更新作品的 share_status 字段并返回最新作品信息。",
        responses={
            200: ("发布成功，返回更新后的作品信息", _work_item),
            400: "不支持的平台",
            401: "未登录",
            404: "作品不存在",
        },
    )
    @console_ns.expect(_publish_req, validate=False)
    def post(self, work_id: str):
        """触发作品发布到社交平台"""
        current_user, _ = current_account_with_tenant()
        work = db.session.scalar(
            select(CreatorWork).where(
                CreatorWork.id == work_id,
                CreatorWork.account_id == current_user.id,
            )
        )
        if not work:
            from werkzeug.exceptions import NotFound
            raise NotFound("Work not found")

        payload = request.get_json() or {}
        platform = payload.get("platform", "")

        status_map = {
            "tiktok": CreatorWorkShareStatus.PUBLISHED_TIKTOK.value,
            "xhs": CreatorWorkShareStatus.PUBLISHED_XHS.value,
        }
        new_status = status_map.get(platform)
        if not new_status:
            from werkzeug.exceptions import BadRequest
            raise BadRequest(f"Unsupported platform: {platform}. Use 'tiktok' or 'xhs'.")

        work.share_status = new_status
        db.session.add(work)
        db.session.commit()

        return work.to_dict()
