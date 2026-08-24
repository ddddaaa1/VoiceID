"""FastAPI application factory for VoiceID API v1."""

from __future__ import annotations

from typing import Annotated

from fastapi import FastAPI, File, Path, Request, UploadFile
from starlette.concurrency import run_in_threadpool

from .container import ServiceContainer, build_default_container
from .errors import error_response, register_error_handlers
from .schemas import EnrollmentResponse, ErrorResponse, HealthResponse, VerificationResponse
from .uploads import read_upload, read_uploads

API_VERSION = "v1"
IdentityPath = Annotated[
    str,
    Path(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
        description="Caller-defined logical identity identifier",
    ),
]
ERROR_RESPONSES = {
    400: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    413: {"model": ErrorResponse},
    415: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}


def create_app(container: ServiceContainer | None = None) -> FastAPI:
    app = FastAPI(
        title="VoiceID API",
        summary="Speaker enrollment and verification research API",
        description=(
            "VoiceID exposes an experimental speaker-verification workflow. "
            "The current policy is provisional and anti-spoofing is not enabled."
        ),
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    app.state.container = container or build_default_container()
    register_error_handlers(app)

    @app.middleware("http")
    async def enforce_content_length(request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                size = int(content_length)
            except ValueError:
                return error_response(400, "invalid_content_length", "Content-Length is invalid.")
            if size < 0:
                return error_response(400, "invalid_content_length", "Content-Length is invalid.")
            if size > app.state.container.settings.max_request_bytes:
                return error_response(413, "request_too_large", "The request body is too large.")
        return await call_next(request)

    @app.get("/api/v1/health", response_model=HealthResponse, tags=["system"])
    async def health() -> HealthResponse:
        services: ServiceContainer = app.state.container
        return HealthResponse(
            status="ok",
            api_version=API_VERSION,
            persistence=services.persistence,
            speaker_model_id=services.speaker_model_id,
            verification_policy_id=services.verification_policy_id,
            anti_spoofing_enabled=services.anti_spoofing_enabled,
        )

    @app.post(
        "/api/v1/identities/{identity_id}/enroll",
        response_model=EnrollmentResponse,
        status_code=201,
        responses=ERROR_RESPONSES,
        tags=["speaker identity"],
    )
    async def enroll(
        identity_id: IdentityPath,
        samples: Annotated[
            list[UploadFile],
            File(description="Three to eight 16-bit PCM WAVE enrollment samples"),
        ],
    ) -> EnrollmentResponse:
        services: ServiceContainer = app.state.container
        payloads = await read_uploads(samples, services.settings)
        result = await run_in_threadpool(services.enrollment.enroll, identity_id, payloads)
        return EnrollmentResponse.from_result(result)

    @app.post(
        "/api/v1/identities/{identity_id}/verify",
        response_model=VerificationResponse,
        responses=ERROR_RESPONSES,
        tags=["speaker identity"],
    )
    async def verify(
        identity_id: IdentityPath,
        sample: Annotated[
            UploadFile,
            File(description="One 16-bit PCM WAVE probe sample"),
        ],
    ) -> VerificationResponse:
        services: ServiceContainer = app.state.container
        payload = await read_upload(sample, services.settings)
        attempt = await run_in_threadpool(services.verification.verify, identity_id, payload)
        return VerificationResponse.from_attempt(attempt)

    return app


app = create_app()
