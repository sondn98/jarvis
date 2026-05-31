import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from llm.exceptions import LLMError, ProviderError, TimeoutError

logger = logging.getLogger(__name__)


class UnsupportedFeatureError(Exception):
    """Raised when the client requests a feature not yet implemented."""


class AuthenticationError(Exception):
    """Raised when API key authentication fails."""


def _error_response(status: int, message: str, error_type: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"message": message, "type": error_type, "param": None, "code": None}},
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        logger.debug("Validation error: %s", exc.errors())
        return _error_response(422, f"Request validation failed: {exc.errors()}", "invalid_request_error")

    @app.exception_handler(UnsupportedFeatureError)
    async def unsupported_feature_handler(request: Request, exc: UnsupportedFeatureError) -> JSONResponse:
        return _error_response(400, str(exc), "unsupported_feature")

    @app.exception_handler(AuthenticationError)
    async def auth_error_handler(request: Request, exc: AuthenticationError) -> JSONResponse:
        return _error_response(401, str(exc), "authentication_error")

    @app.exception_handler(ProviderError)
    async def provider_error_handler(request: Request, exc: ProviderError) -> JSONResponse:
        logger.error("Provider error: %s", exc)
        return _error_response(502, "LLM provider returned an error.", "provider_error")

    @app.exception_handler(TimeoutError)
    async def timeout_error_handler(request: Request, exc: TimeoutError) -> JSONResponse:
        logger.error("LLM request timed out: %s", exc)
        return _error_response(504, "LLM request timed out.", "timeout_error")

    @app.exception_handler(LLMError)
    async def llm_error_handler(request: Request, exc: LLMError) -> JSONResponse:
        logger.error("LLM error: %s", exc)
        return _error_response(500, "An LLM error occurred.", "llm_error")

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error("Unexpected error: %s", exc, exc_info=True)
        return _error_response(500, "An unexpected error occurred.", "internal_error")
