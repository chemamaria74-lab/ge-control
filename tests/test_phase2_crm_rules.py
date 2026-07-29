import pytest
from fastapi import HTTPException

from services.commercial_rules import (
    validate_prospect_conversion,
    validate_prospect_transition,
    validate_task_transition,
)


def test_prospect_pipeline_allows_expected_progression():
    validate_prospect_transition("new", "contacted")
    validate_prospect_transition("contacted", "qualified")
    validate_prospect_transition("qualified", "proposal")
    validate_prospect_transition("proposal", "negotiation")
    validate_prospect_transition("negotiation", "won")


def test_prospect_pipeline_rejects_invalid_jump():
    with pytest.raises(HTTPException) as error:
        validate_prospect_transition("new", "won")
    assert error.value.status_code == 409


@pytest.mark.parametrize("stage", ["qualified", "proposal", "negotiation", "won"])
def test_qualified_prospect_can_convert(stage):
    validate_prospect_conversion(stage, None)


def test_unqualified_or_already_converted_prospect_cannot_convert():
    with pytest.raises(HTTPException):
        validate_prospect_conversion("new", None)
    with pytest.raises(HTTPException):
        validate_prospect_conversion("qualified", 9)


def test_tasks_are_terminal_after_completion():
    validate_task_transition("pending", "completed")
    with pytest.raises(HTTPException):
        validate_task_transition("completed", "pending")
