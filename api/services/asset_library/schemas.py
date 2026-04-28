"""Pydantic v2 schemas for asset-library payloads.

Used by ``AssetLibraryService`` to validate ``prompt_variables`` input from
controllers before persisting to the ``asset_libraries.prompt_variables``
JSONB column. Schemas enforce:

- Variable names match an identifier pattern (safe for downstream
  template substitution like ``{{name}}``).
- ``default`` value type matches declared ``type``.
- Variable names within a list are unique.

Extras are forbidden; unknown fields raise ``ValidationError``.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, RootModel, field_validator, model_validator

_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
PromptVariableType = Literal["string", "number", "boolean"]


class PromptVariable(BaseModel):
    """A single variable definition for a prompt asset.

    Stored as a dict in the ``prompt_variables`` JSONB column. Validation
    happens both at create time and on update.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    type: PromptVariableType
    default: Any | None = None
    description: str | None = None

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        if not _NAME_RE.match(value):
            raise ValueError(
                "name must match [A-Za-z_][A-Za-z0-9_]{0,63}",
            )
        return value

    @model_validator(mode="after")
    def _validate_default_type(self) -> PromptVariable:
        if self.default is None:
            return self
        match self.type:
            case "string":
                if not isinstance(self.default, str):
                    raise ValueError("default must be str when type=string")
            case "number":
                # bool is a subclass of int — exclude it explicitly
                if isinstance(self.default, bool) or not isinstance(self.default, (int, float)):
                    raise ValueError("default must be number when type=number")
            case "boolean":
                if not isinstance(self.default, bool):
                    raise ValueError("default must be bool when type=boolean")
        return self


class PromptVariableList(RootModel[list[PromptVariable]]):
    """A list of prompt variables with global uniqueness on ``name``."""

    @model_validator(mode="after")
    def _unique_names(self) -> PromptVariableList:
        names = [pv.name for pv in self.root]
        if len(names) != len(set(names)):
            raise ValueError("prompt_variables names must be unique")
        return self
