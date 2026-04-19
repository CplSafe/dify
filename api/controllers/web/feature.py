from flask_restx import Resource

from controllers.web import web_ns
from services.feature_service import FeatureService


@web_ns.route("/system-features")
class SystemFeatureApi(Resource):
    @web_ns.doc(
        description="获取系统功能开关及配置（无需认证）。"
                    "Web 应用初始化时调用，用于判断当前系统启用了哪些功能特性。"
                    "此接口故意设计为公开接口，避免认证与初始化循环依赖，"
                    "仅返回非敏感配置数据。",
        responses={
            200: "成功，返回系统功能配置",
            500: "服务器内部错误",
        },
    )
    def get(self):
        """获取系统功能开关及配置"""
        return FeatureService.get_system_features().model_dump()
