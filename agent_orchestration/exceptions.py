class AgentError(Exception):
    """Base exception for all agent orchestration errors."""


class PlanningError(AgentError):
    """Raised when the planner fails to produce a valid plan."""


class ToolExecutionError(AgentError):
    """Raised when a tool fails during execution."""


class ToolNotFoundError(AgentError):
    """Raised when a requested tool is not registered."""


class ToolValidationError(AgentError):
    """Raised when tool arguments fail schema validation."""


class ApprovalRequiredError(AgentError):
    """Raised internally when a tool requires user approval before execution."""


class ApprovalNotFoundError(AgentError):
    """Raised when an approval record cannot be found by ID."""


class CheckpointNotFoundError(AgentError):
    """Raised when a graph checkpoint cannot be found for a conversation."""


class MCPConfigError(AgentError):
    """Raised when the MCP server config file is missing, malformed, or references
    an undefined environment variable."""


class MCPConnectionError(AgentError):
    """Raised when an MCP server cannot be reached or fails to initialize."""
