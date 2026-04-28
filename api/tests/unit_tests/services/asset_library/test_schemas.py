"""Unit tests for prompt-variable Pydantic schemas."""

import pytest
from pydantic import ValidationError

from services.asset_library.schemas import PromptVariable, PromptVariableList


def test_valid_prompt_variable_string():
    pv = PromptVariable(name="product_name", type="string", default="", description="x")
    assert pv.name == "product_name"
    assert pv.type == "string"


def test_valid_prompt_variable_no_default():
    pv = PromptVariable(name="x", type="string")
    assert pv.default is None


def test_invalid_name_with_space_rejected():
    with pytest.raises(ValidationError):
        PromptVariable(name="bad name", type="string")


def test_invalid_name_with_punct_rejected():
    with pytest.raises(ValidationError):
        PromptVariable(name="bad-name!", type="string")


def test_name_starting_with_digit_rejected():
    with pytest.raises(ValidationError):
        PromptVariable(name="1abc", type="string")


def test_name_with_underscore_ok():
    PromptVariable(name="_a", type="string")


def test_invalid_type_rejected():
    with pytest.raises(ValidationError):
        PromptVariable(name="x", type="enum")


def test_default_string_mismatch_rejected():
    with pytest.raises(ValidationError):
        PromptVariable(name="x", type="string", default=123)


def test_default_number_mismatch_rejected():
    with pytest.raises(ValidationError):
        PromptVariable(name="x", type="number", default="not-a-number")


def test_default_number_bool_rejected():
    # bool is technically a subclass of int — must NOT be accepted as number
    with pytest.raises(ValidationError):
        PromptVariable(name="x", type="number", default=True)


def test_default_number_int_ok():
    PromptVariable(name="age", type="number", default=18)


def test_default_number_float_ok():
    PromptVariable(name="age", type="number", default=18.5)


def test_default_boolean_ok():
    PromptVariable(name="enabled", type="boolean", default=True)


def test_default_boolean_int_rejected():
    with pytest.raises(ValidationError):
        PromptVariable(name="enabled", type="boolean", default=1)


def test_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        PromptVariable(name="x", type="string", extra="nope")


def test_list_validates_items():
    pvl = PromptVariableList.model_validate(
        [{"name": "a", "type": "string"}, {"name": "b", "type": "number", "default": 1}]
    )
    assert len(pvl.root) == 2
    assert pvl.root[0].name == "a"


def test_list_rejects_duplicate_names():
    with pytest.raises(ValidationError):
        PromptVariableList.model_validate([{"name": "a", "type": "string"}, {"name": "a", "type": "number"}])


def test_list_empty_ok():
    pvl = PromptVariableList.model_validate([])
    assert pvl.root == []
