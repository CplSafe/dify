from typing import Any, cast

from controllers.common import fields
from controllers.console import console_ns
from controllers.console.app.error import AppUnavailableError
from controllers.console.explore.wraps import InstalledAppResource
from core.app.app_config.common.parameters_mapping import get_parameters_from_feature_dict
from models.model import AppMode, InstalledApp
from services.app_service import AppService


@console_ns.route("/installed-apps/<uuid:installed_app_id>/parameters", endpoint="installed_app_parameters")
class AppParameterApi(InstalledAppResource):
    """Resource for app variables."""

    def get(self, installed_app: InstalledApp):
        """Retrieve app parameters."""
        app_model = installed_app.app

        if app_model is None:
            raise AppUnavailableError()

        if app_model.mode in {AppMode.ADVANCED_CHAT, AppMode.WORKFLOW}:
            workflow = app_model.workflow
            if workflow is None:
                raise AppUnavailableError()

            features_dict: dict[str, Any] = workflow.features_dict
            user_input_form = workflow.user_input_form(to_old_structure=True)
        else:
            app_model_config = app_model.app_model_config
            if app_model_config is None:
                raise AppUnavailableError()

            features_dict = cast(dict[str, Any], app_model_config.to_dict())

            user_input_form = features_dict.get("user_input_form", [])

        parameters = get_parameters_from_feature_dict(features_dict=features_dict, user_input_form=user_input_form)
        return fields.Parameters.model_validate(parameters).model_dump(mode="json")


@console_ns.route("/installed-apps/<uuid:installed_app_id>/meta", endpoint="installed_app_meta")
class ExploreAppMetaApi(InstalledAppResource):
    def get(self, installed_app: InstalledApp):
        """Get app meta"""
        app_model = installed_app.app
        if not app_model:
            raise ValueError("App not found")
        return AppService().get_app_meta(app_model)


@console_ns.route(
    "/installed-apps/<uuid:installed_app_id>/runtime-graph",
    endpoint="installed_app_runtime_graph",
)
class InstalledAppRuntimeGraphApi(InstalledAppResource):
    """CR9: minimal draft-graph projection for the canvas runtime.

    Returns the node + edge skeleton with the ``show_in_canvas_runtime``
    flag exposed per node, so the runtime store can decide which nodes
    to render and which edges to pass through. We deliberately do NOT
    return prompts, model configs, or anything else from
    ``workflow.graph_dict`` so this stays cheap and avoids leaking
    author-side configuration through a creator-allowed route.
    """

    def get(self, installed_app: InstalledApp):
        app_model = installed_app.app
        if app_model is None:
            raise AppUnavailableError()
        if app_model.mode != AppMode.ADVANCED_CHAT:
            return {"nodes": [], "edges": []}
        workflow = app_model.workflow
        if workflow is None:
            raise AppUnavailableError()
        graph = workflow.graph_dict or {}

        nodes = []
        for n in graph.get("nodes", []) or []:
            data = n.get("data") or {}
            nodes.append(
                {
                    "id": n.get("id"),
                    # Node type + title used by the canvas runtime to render
                    # the full graph up-front (mode A) — runtime status is
                    # then layered on via SSE node_started/node_finished
                    # events. Keeps cards present even before the engine
                    # reaches them.
                    "type": data.get("type") or n.get("type"),
                    "title": data.get("title", ""),
                    "data": {
                        "show_in_canvas_runtime": data.get(
                            "show_in_canvas_runtime", True
                        ),
                        # CR10: surface per-node "allow user edit" toggles
                        # so the canvas-runtime UI knows when to render the
                        # 重跑 trigger on completed nodes. Defaults to false
                        # — author must opt the node in via the workflow editor.
                        "allow_user_edit_input": bool(data.get("allow_user_edit_input")),
                        "allow_user_edit_output": bool(data.get("allow_user_edit_output")),
                    },
                }
            )
        edges = [
            {"source": e.get("source"), "target": e.get("target")}
            for e in (graph.get("edges", []) or [])
        ]
        return {"nodes": nodes, "edges": edges}
