"""Domain errors. Each maps to a clear HTTP response; none trigger a silent mock fallback."""
from __future__ import annotations


class TripAuraError(Exception):
    status_code = 400
    code = "tripaura_error"

    def __init__(self, message: str, *, details: dict | None = None, headers: dict[str, str] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.headers = headers or {}


class ProviderNotConfiguredError(TripAuraError):
    """Live mode was requested but credentials for an external provider are missing."""
    status_code = 503
    code = "provider_not_configured"


class ProviderRequestError(TripAuraError):
    """An external provider (e.g. Google) returned an error or could not be reached."""
    status_code = 502
    code = "provider_request_failed"


class LocationNotFoundError(TripAuraError):
    status_code = 422
    code = "location_not_found"


class UnsupportedInMockModeError(TripAuraError):
    status_code = 422
    code = "unsupported_in_mock_mode"


class NotFoundError(TripAuraError):
    status_code = 404
    code = "not_found"


class TripNotFoundError(NotFoundError):
    """Also returned for trips owned by someone else, so ids cannot be probed."""
    code = "trip_not_found"


# ---------------------------------------------------------------- auth / security
class NotAuthenticatedError(TripAuraError):
    status_code = 401
    code = "not_authenticated"


class CsrfError(TripAuraError):
    status_code = 403
    code = "csrf_failed"


class InvalidCodeError(TripAuraError):
    status_code = 400
    code = "invalid_code"


class RateLimitedError(TripAuraError):
    status_code = 429
    code = "rate_limited"

    def __init__(self, retry_after: int, message: str = "Too many requests, please slow down"):
        retry_after = max(1, int(retry_after))
        super().__init__(message, details={"retry_after": retry_after}, headers={"Retry-After": str(retry_after)})


class EmailNotConfiguredError(TripAuraError):
    status_code = 503
    code = "email_not_configured"


class EmailFailedError(TripAuraError):
    status_code = 502
    code = "email_failed"


class IdempotencyKeyRequiredError(TripAuraError):
    status_code = 400
    code = "idempotency_key_required"


class IdempotencyKeyReusedError(TripAuraError):
    status_code = 422
    code = "idempotency_key_reused"


class RequestInProgressError(TripAuraError):
    status_code = 409
    code = "request_in_progress"
