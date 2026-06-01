class LLMError(Exception):
    """Base exception for all LLM module errors."""


class ConfigurationError(LLMError):
    """Raised when configuration is invalid or missing."""


class ProviderError(LLMError):
    """Raised when the LLM provider returns an error or is unavailable."""


class TimeoutError(LLMError):
    """Raised when a provider request times out."""


class StructuredOutputError(LLMError):
    """Raised when structured output validation fails."""


class ToolCallParsingError(LLMError):
    """Raised when a tool-call response cannot be parsed."""


class StreamingNotSupportedError(LLMError):
    """Raised when a provider does not implement streaming."""
