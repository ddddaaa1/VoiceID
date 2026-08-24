"""FastAPI application factory for VoiceID API v1."""

from __future__ import annotations

from pathlib import Path as FileSystemPath
from typing import Annotated

from fastapi import FastAPI, File, Path, Query, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from .container import ServiceContainer, build_default_container
from .errors import ApiError, error_response, register_error_handlers
from .rate_limit import FixedWindowRateLimiter
from .schemas import (
    ConsentRequest,
    ConsentResponse,
    EnrollmentResponse,
    ErrorResponse,
    HealthResponse,
    RevocationResponse,
    VerificationResponse,
)
from .uploads import read_upload, read_uploads

API_VERSION = "v1"
DEFAULT_WEB_DIRECTORY = FileSystemPath(__file__).with_name("web")
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
    429: {"model": ErrorResponse},
}


def create_app(
    container: ServiceContainer | None = None,
    web_directory: FileSystemPath = DEFAULT_WEB_DIRECTORY,
) -> FastAPI:
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
    app.state.rate_limiter = FixedWindowRateLimiter(
        app.state.container.settings.rate_limit_requests,
        app.state.container.settings.rate_limit_window_seconds,
    )
    register_error_handlers(app)

    if not (web_directory / "index.html").is_file():
        raise RuntimeError(f"Web directory does not exist: {web_directory}")
    app.mount(
        "/assets",
        StaticFiles(directory=web_directory / "assets"),
        name="web-assets",
    )

    @app.middleware("http")
    async def enforce_content_length(request: Request, call_next):
        if request.url.path.startswith("/api/v1/") and request.method != "GET":
            client_host = request.client.host if request.client is not None else "unknown"
            allowed, retry_after = app.state.rate_limiter.consume(client_host)
            if not allowed:
                response = error_response(
                    429,
                    "rate_limit_exceeded",
                    "Too many requests; retry later.",
                )
                response.headers["Retry-After"] = str(retry_after)
                return response
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
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path == "/" or request.url.path.startswith("/assets/"):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; connect-src 'self'; img-src 'self' data:; "
                "media-src 'self' blob:; object-src 'none'; base-uri 'none'; "
                "frame-ancestors 'none'"
            )
            response.headers["Permissions-Policy"] = "microphone=(self)"
        return response

    @app.get("/", include_in_schema=False)
    async def web_experience() -> FileResponse:
        return FileResponse(web_directory / "index.html")

    @app.get("/api/v1/health", response_model=HealthResponse, tags=["system"])
    async def health() -> HealthResponse:
        services: ServiceContainer = app.state.container
        return HealthResponse(
            status="ok",
            api_version=API_VERSION,
            persistence=services.persistence,
            speaker_model_id=services.speaker_model_id,
            spoof_model_id=services.spoof_model_id,
            verification_policy_id=services.verification_policy_id,
            anti_spoofing_enabled=services.anti_spoofing_enabled,
        )

    @app.post(
        "/api/v1/identities/{identity_id}/consent",
        response_model=ConsentResponse,
        status_code=201,
        responses=ERROR_RESPONSES,
        tags=["identity governance"],
    )
    async def grant_consent(
        identity_id: IdentityPath,
        request: ConsentRequest,
    ) -> ConsentResponse:
        services: ServiceContainer = app.state.container
        if services.governance is None:
            raise ApiError(
                409,
                "governance_not_configured",
                "Durable identity governance is not configured for this process.",
            )
        try:
            grant = await run_in_threadpool(
                services.governance.grant_consent,
                identity_id,
                purpose=request.purpose,
                notice_version=request.notice_version,
                expires_at=request.expires_at,
            )
        except ValueError as error:
            raise ApiError(422, "invalid_consent", str(error)) from error
        return ConsentResponse.from_grant(grant)

    @app.delete(
        "/api/v1/identities/{identity_id}",
        response_model=RevocationResponse,
        responses=ERROR_RESPONSES,
        tags=["identity governance"],
    )
    async def revoke_identity(
        identity_id: IdentityPath,
        reason: str = Query(min_length=1, max_length=200),
    ) -> RevocationResponse:
        services: ServiceContainer = app.state.container
        if services.governance is None:
            raise ApiError(
                409,
                "governance_not_configured",
                "Durable identity governance is not configured for this process.",
            )
        try:
            result = await run_in_threadpool(
                services.governance.revoke_identity,
                identity_id,
                reason=reason,
            )
        except ValueError as error:
            raise ApiError(422, "invalid_revocation", str(error)) from error
        return RevocationResponse.from_result(result)

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
