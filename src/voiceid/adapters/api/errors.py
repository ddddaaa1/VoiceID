"""Stable HTTP error envelope and exception mapping."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from voiceid.application.enrollment import EnrollmentRejected
from voiceid.application.verification import VerificationUnavailable


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        details: Any = None,
    ) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def error_response(status_code: int, code: str, message: str, details: Any = None) -> JSONResponse:
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    return JSONResponse(status_code=status_code, content=body)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def handle_api_error(_request: Request, error: ApiError) -> JSONResponse:
        return error_response(error.status_code, error.code, error.message, error.details)

    @app.exception_handler(EnrollmentRejected)
    async def handle_enrollment_rejection(
        _request: Request, error: EnrollmentRejected
    ) -> JSONResponse:
        details = [
            {"sample_index": issue.sample_index, "reasons": list(issue.reasons)}
            for issue in error.sample_issues
        ]
        return error_response(
            422,
            error.code,
            "The enrollment request could not produce a valid voice template.",
            details or None,
        )

    @app.exception_handler(VerificationUnavailable)
    async def handle_verification_unavailable(
        _request: Request, error: VerificationUnavailable
    ) -> JSONResponse:
        status_code = {
            "active_template_not_found": 404,
            "speaker_model_mismatch": 409,
            "audio_pipeline_mismatch": 409,
            "embedding_dimension_mismatch": 409,
        }.get(error.code, 422)
        return error_response(
            status_code,
            error.code,
            "The verification request could not be processed.",
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request, error: RequestValidationError
    ) -> JSONResponse:
        details = [
            {
                "location": list(item["loc"]),
                "message": item["msg"],
                "type": item["type"],
            }
            for item in error.errors()
        ]
        return error_response(
            422,
            "request_validation_failed",
            "Request validation failed.",
            details,
        )
