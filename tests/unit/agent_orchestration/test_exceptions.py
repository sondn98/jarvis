from agent_orchestration.exceptions import (
    AgentError,
    ApprovalNotFoundError,
    CheckpointNotFoundError,
    PlanningError,
    ToolExecutionError,
    ToolNotFoundError,
    ToolValidationError,
)


def test_hierarchy():
    assert issubclass(PlanningError, AgentError)
    assert issubclass(ToolExecutionError, AgentError)
    assert issubclass(ToolNotFoundError, AgentError)
    assert issubclass(ToolValidationError, AgentError)
    assert issubclass(ApprovalNotFoundError, AgentError)
    assert issubclass(CheckpointNotFoundError, AgentError)
